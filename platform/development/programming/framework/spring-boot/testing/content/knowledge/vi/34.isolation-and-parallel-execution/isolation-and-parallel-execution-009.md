# Clock, random seed và khả năng tái hiện một lần chạy thất bại

## 1. Bài toán: test chạy xanh hôm qua nhưng đỏ hôm nay

Trong nhóm **Cách ly và chạy song song** của Spring Boot testing, một bài kiểm thử có thể pass trên laptop rồi fail ở CI dù mã nguồn chưa đổi. Hai nguồn không xác định thường gặp là:

- **Thời gian thực:** code gọi `Instant.now()`, `LocalDate.now()`, `System.currentTimeMillis()` hoặc dựa vào timezone mặc định. Chạy sát nửa đêm, giờ đổi mùa, hạn TTL hoặc deadline tạo kết quả khác.
- **Ngẫu nhiên:** code gọi `new Random()`, `Math.random()`, `ThreadLocalRandom.current()`, `UUID.randomUUID()` hay thư viện random fixture mà không lưu seed. Khi fail, người khác không tạo lại đúng inputs đã gây lỗi.

Trong test chạy song song, bài toán phức tạp hơn: một `Random` instance chia sẻ giữa nhiều threads có thể an toàn về mặt race ở implementation cụ thể nhưng **thứ tự tiêu thụ các giá trị** vẫn phụ thuộc scheduling. Một process-level seed duy nhất cũng chưa đủ để replay một case nếu mỗi thread rút số theo thứ tự khác.

Bài học hướng dẫn ba lớp kiểm soát:

1. **Đồng hồ có thể inject:** dùng `java.time.Clock`, `Clock.fixed(...)`, `Clock.offset(...)` và test-only mutable clock; không phụ thuộc thời gian thật của CI.
2. **Nguồn ngẫu nhiên có thể seed:** dùng `java.util.random.RandomGenerator` (Java 17), `new Random(seed)` và mỗi test/case có generator riêng.
3. **Replay một lỗi cụ thể:** ghi **root seed, case index, derived case seed, instant, zone, test selector, versions và môi trường**, rồi đưa ra lệnh Gradle tái chạy đúng case.

Ví dụ đầy đủ dùng **Java 17, Spring Boot 3.3.0, JUnit Jupiter, Gradle**. Có một ứng dụng Spring nhận `Clock` và `RandomGenerator` qua constructor injection; bộ unit tests kiểm tra ngày/giờ, deadline, chuỗi random, cách ly đồng thời; một test tạo nhiều scenarios từ root seed với khả năng chạy lại riêng case số N; và một `@SpringBootTest` xác minh test bean override đúng. **Expected results** được phân biệt với kết quả thực thi: tài liệu không tuyên bố Gradle đã chạy.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt thời gian hệ thống thực, đồng hồ giả, lịch/ngày theo timezone, monotonic elapsed time và thời gian ảo của scheduler.
2. Dùng `Clock.systemUTC()` làm default application dependency thay cho hardcode `Instant.now()` trong business code.
3. Dùng `Clock.fixed(Instant,ZoneId)` để cố định hoàn toàn thời gian quan sát được.
4. Dùng `Clock.offset(base, Duration)` để mô phỏng tương lai/quá khứ; hiểu offset trên system clock vẫn tiếp tục chạy.
5. Viết `MutableClock extends Clock` với `AtomicReference<Instant>` để advance thời gian không dùng `Thread.sleep`.
6. Kiểm tra boundary ở trước deadline, đúng deadline và sau deadline.
7. Kiểm tra cùng `Instant` nhưng hai timezone tạo `LocalDate` khác.
8. Hiểu tại sao `Instant.now(clock)` và `LocalDate.now(clock)` khác mục đích.
9. Phân biệt `RandomGenerator` interface và `Random` implementation Java 17.
10. Giải thích cùng seed + cùng algorithm + cùng chuỗi method calls tạo cùng chuỗi giả ngẫu nhiên.
11. Biết không thể chỉ ghi seed nếu code đã thay algorithm, số lần rút hoặc thứ tự rút.
12. Không dùng `Random(seed)` để tạo password/token/cryptographic keys; dùng `SecureRandom` và policies an toàn.
13. Không dùng một shared seeded `Random` cho parallel tests rồi tin rằng kết quả từng test sẽ cố định.
14. Thiết kế mỗi test/case có random state riêng; không phụ thuộc thứ tự chạy case.
15. Tạo case seed ổn định từ root seed + case index với phép tính thuần không chia sẻ trạng thái.
16. Cho phép JUnit replay đúng một case bằng Gradle `-PreproSeed` và `-PreproCaseIndex`.
17. Ghi rõ lệnh replay và case metadata trong exception khi assertion fail.
18. Sử dụng JUnit `TestReporter` để công bố seed trong report, không chỉ println bị test runner ẩn.
19. Kiểm chứng Spring Boot `@TestConfiguration`/`@Primary` override `Clock` và `RandomGenerator`.
20. Hiểu mặt trái của singleton random generator trong một shared Spring ApplicationContext.
21. Phân biệt Java test RNG với random fixture generator thuộc jqwik/QuickTheories/Instancio (có cơ chế seed riêng).
22. Biết test order, JUnit parallel, Gradle forks và external DB/HTTP vẫn có thể làm replay lệch dù seed giống.
23. Lưu JDK, timezone/tzdb, locale, dependency versions, CI runner và input snapshot khi điều tra flaky failures.
24. Biết `Clock.fixed` không tự làm scheduler, retry backoff, Redis TTL hay database server time tiến lên.
25. Xây dựng quy trình reproducing/red-green diagnosis thay vì “rerun cho đến khi xanh”.
26. Viết tests có invariants và negative cases, không cần hardcode literal random numbers dễ lỗi.
27. Nhận diện failure vốn do production bug với failure bị che do test giả lập quá nhiều.
28. Đề xuất mức cô lập phù hợp cho cùng JVM, nhiều forks và CI shards.

## 3. Ba loại không xác định cần phân biệt

| Nguồn | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| Wall clock | `Instant.now()`, current date, deadline | Inject `Clock`, fixed/mutable test clock |
| PRNG state | `Random.nextInt()`, fixture generation | Ghi seed, algorithm, draw order; generator per case |
| Scheduling/external state | Parallel threads, database, network, timezone, brokers | Isolation, deterministic scheduler/clock khi phù hợp, test resources cố định, event ordering rõ |

**Seed chỉ điều khiển PRNG**, không điều khiển DB đang có những rows nào hoặc thread nào hoàn tất trước. **Clock.fixed chỉ điều khiển code gọi đúng Clock được inject**, không điều khiển `System.currentTimeMillis()` trong thư viện khác, Redis server TTL hoặc task scheduler mặc định.

Một bài kiểm thử tái hiện được tốt cần làm rõ **những gì đã được kiểm soát** và **những gì vẫn có thể biến thiên**.

## 4. Clock: đưa thời gian thành dependency

Anti-pattern:

```java
@Service
class ExpiryService {
    boolean expired(Instant deadline) {
        return Instant.now().isAfter(deadline);
    }
}
```

Đây là snippet minh họa (chưa có imports). Hai vấn đề:

1. `Instant.now()` đọc system clock; test sát boundary có thể chạy qua deadline vào giữa assertion.
2. `isAfter` trả false **khi bằng đúng deadline**. Nếu hợp đồng là “expired ngay khi now >= deadline”, code sai ở điểm biên.

Thiết kế có thể kiểm thử:

```java
@Service
public class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }
}
```

Đây là snippet rút gọn; runnable file cùng class đầy đủ ở chương 12. Logic dùng `now >= deadline` bằng cách phủ định `isBefore`, rõ ràng ở boundary.

### 4.1. Clock.systemUTC()

```java
Clock productionClock = Clock.systemUTC();
```

Đây là source thời gian hiện tại trong UTC. Khi cần lưu timestamp/so sánh thời điểm toàn cầu, `Instant`/UTC thường giúp tránh mơ hồ timezone.

### 4.2. Clock.fixed()

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-12-31T23:30:00Z"),
        ZoneOffset.UTC);
```

Mọi lần `fixed.instant()` trả cùng một `Instant`. Đây là lựa chọn tốt cho đa số unit tests kiểm tra logic tại một thời điểm xác định. **Không dùng Clock.fixed với vòng polling chờ thời gian trôi** nếu vòng loop chỉ kết thúc khi clock tiến lên.

### 4.3. Clock.offset()

```java
Clock tomorrow = Clock.offset(
        Clock.systemUTC(),
        Duration.ofDays(1));
```

Offset cộng thêm một duration vào clock nguồn. Nếu nguồn là system clock, kết quả vẫn chạy theo thời gian thực và chỉ bị dịch một ngày — **không deterministic tuyệt đối**. Muốn deterministic, offset một `Clock.fixed`:

```java
Clock fixedTomorrow = Clock.offset(
        fixed,
        Duration.ofDays(1));
```

### 4.4. Clock.tick()

`Clock.tick(baseClock, Duration.ofSeconds(1))` làm thời gian chỉ thay đổi theo từng “tick”, phù hợp một số giao diện/metrics. Nó không tự tạo một virtual scheduler và có thể có caching/truncation semantics. Không dùng `Clock.tick` để kiểm tra chính xác timer latency ở mức nano giây.

## 5. Instant, LocalDate, ZoneId và timezone boundary

Cùng một thời điểm vật lý có thể rơi vào hai ngày lịch khác nhau:

```java
Instant instant =
        Instant.parse("2026-12-31T23:30:00Z");

Clock utc = Clock.fixed(
        instant, ZoneOffset.UTC);

Clock vietnam = Clock.fixed(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate utcDate = LocalDate.now(utc);
LocalDate vnDate = LocalDate.now(vietnam);
```

Kết quả có thể xác định chính xác:

```text
utcDate = 2026-12-31
vnDate  = 2027-01-01
```

Vì Việt Nam đang ở UTC+07 trong khoảng thời gian ví dụ, `23:30Z` đã là `06:30` ngày hôm sau tại TP.HCM.

### 5.1. Không gọi đồng hồ hai lần nếu muốn một snapshot nhất quán

Code:

```java
Instant at = clock.instant();
LocalDate date = LocalDate.now(clock);
```

có thể nhận hai snapshots khác nhau nếu `clock` là system clock và giữa hai calls xảy ra qua midnight. Với receipt cần một consistency snapshot, chọn:

```java
Instant at = clock.instant();
LocalDate date =
        LocalDate.ofInstant(at, clock.getZone());
```

Trong runnable `ReservationService`, ta đọc `clock.instant()` **một lần**, rồi suy ra `LocalDate` từ chính instant đó.

### 5.2. LocalDate.now() không có Clock

`LocalDate.now()` dùng system default timezone. Đây là mutable process-global configuration và khác giữa máy dev/CI. Trong business services, sử dụng `LocalDate.now(clock)` hoặc `LocalDate.ofInstant(instant,businessZone)`.

### 5.3. Timezone database/tzdb

`ZoneId.of("America/New_York")` chứa các quy tắc DST theo tzdb của JDK. Quy tắc lịch sử/tương lai có thể thay đổi giữa JDK/tzdb versions. Với “replay chính xác trên mọi máy”, cần ghi **JDK vendor/version, tzdb**, zone và instant. `Asia/Ho_Chi_Minh` trong ví dụ đơn giản hơn vì không có DST trong khoảng được xét, nhưng không thay thế yêu cầu version pinning cho tests phức tạp.

## 6. MutableClock: tiến thời gian mà không chờ thật

Khi muốn kiểm thử các mốc `T-1ms`, `T` và `T+1ms`, `Clock.fixed` cho một snapshot; có thể tạo ba fixed clocks khác nhau. Nếu một service giữ Clock reference, ta cũng có thể dùng test-only `MutableClock`:

```text
MutableClock starts at T - 90 seconds
       |
       +-- DeadlineService.isExpired(T) -> false
       |
       +-- clock.advance(90 seconds)
       |
       +-- DeadlineService.isExpired(T) -> true
       |
       +-- clock.advance(1 second)
       |
       +-- DeadlineService.isExpired(T) -> true
```

Không cần `Thread.sleep(90000)`; chạy nhanh và deterministic.

### 6.1. Clock mutable cần cẩn thận với concurrency

Test-only clock có thể dùng `AtomicReference<Instant>` để tránh data race trên thời điểm. Tuy vậy, việc thread A advance khi thread B đọc vẫn tạo **interleaving-dependent results**. Một test song song cần mỗi case một clock hoặc điều phối bằng latch/barrier, không chia sẻ một mutable clock toàn suite.

### 6.2. MutableClock không thay virtual scheduler

Nếu hệ thống dùng `@Scheduled`, Reactor `Schedulers`, Netty event loop, Redis TTL hoặc database `CURRENT_TIMESTAMP`, chỉ advance một Java Clock không khiến những hệ thống này tự “đánh thức” task. Cần dedicated virtual-time scheduler, fake executor, Testcontainers/server clock phù hợp hoặc test boundary khác. Không khẳng định `Clock.fixed` tự rút ngắn các retry/backoff thực.

## 7. Seed là gì? Khi nào cùng seed cho cùng kết quả?

`java.util.Random` là PRNG. Với cùng `long seed` và **cùng thứ tự gọi các phương thức random**, hai `Random` instances tạo cùng chuỗi. Đặc tính thuật toán của `java.util.Random` được Java SE 17 quy định cho portability.

```java
Random left = new Random(20261108L);
Random right = new Random(20261108L);

for (int i = 0; i < 5; i++) {
    assertEquals(
            left.nextInt(1_000_000),
            right.nextInt(1_000_000));
}
```

Snippet cần JUnit static import `assertEquals`. Đây là **repeatability**, không phải bảo mật. `Random` là thuật toán LCG với state nhỏ và có thể dự đoán; không sử dụng cho token, password reset link, cryptographic nonce hoặc secret key.

### 7.1. Điều kiện để tái hiện chuỗi

Một run thất bại dùng random phải ghi:

- PRNG **implementation/algorithm** (`java.util.Random`, `SplittableRandom`, algorithm name).
- Seed **giá trị đầy đủ**.
- **Thứ tự và số lần** gọi generator (`nextInt(100)` khác `nextInt(1000)`).
- Cách chia seed khi có nhiều cases/threads.
- Input dữ liệu bên ngoài random, timezone và clock.
- Test code/dependency/JDK version.

Nếu thêm một lời gọi `random.nextBoolean()` trước `nextInt(...)`, cùng seed có thể cho output khác vì state đã advance.

### 7.2. RandomGenerator trên Java 17

`java.util.random.RandomGenerator` là interface thống nhất cho các PRNGs; `java.util.Random` implement interface đó từ Java 17. Business service có thể inject `RandomGenerator`, còn test chọn `new Random(seed)`.

Điểm mạnh: dễ thay algorithm trong cấu hình. Điểm cần cẩn trọng: **seed giống nhưng implementation khác** không bảo đảm chuỗi giống. Vì vậy replay metadata phải ghi cả algorithm hoặc luôn dùng một implementation cố định.

### 7.3. SplittableRandom/ThreadLocalRandom

`SplittableRandom` có thể tạo các generator độc lập theo cấu trúc split, phù hợp thiết kế parallel. Nhưng nếu shared parent được split theo thứ tự scheduling khác, assignment của seed con vẫn khác. `ThreadLocalRandom.current()` tiện cho production parallel throughput nhưng không cho người học set seed tùy ý để replay bằng public API; đừng dùng nó khi test yêu cầu exact seed control.

### 7.4. SecureRandom là một câu chuyện khác

`SecureRandom` dành cho security-sensitive randomness. Không thay nó bằng `new Random(42)` trong production chỉ vì unit test cần deterministic. Khi test token/security boundary, mock/fake entropy source **chỉ trong test** với ownership rõ, còn integration/security tests dùng nguồn entropy thật và assert policy/invariants thay vì exact secret bytes.

## 8. Vì sao shared seeded Random vẫn không tái hiện được parallel test?

Giả sử có một `Random shared = new Random(123)`, hai threads A và B cùng gọi `nextInt()`:

```text
Run 1: Thread A draws #1; Thread B draws #2
Run 2: Thread B draws #1; Thread A draws #2
```

Dù tổng chuỗi random #1/#2 giống nhau, **case nhận số nào** phụ thuộc scheduler. `java.util.Random` có thể thread-safe nhưng thread safety không có nghĩa deterministic assignment theo task.

Điều cần làm:

- Mỗi test method tạo `new Random(ownSeed)`.
- Mỗi **scenario/case** tạo một PRNG riêng, seed được tính bằng hàm deterministic từ root seed + case index/id.
- Không dùng global counter hoặc `AtomicLong.incrementAndGet()` gán case seed theo thứ tự threads chạy.
- Không dùng `Collections.shuffle(list)` với RNG global và để parallel threads mutate list.
- Không kỳ vọng thay JUnit execution order vẫn giữ kết quả nếu mỗi case tiêu thụ từ cùng Random instance.

### 8.1. Per-case derived seed

Một phép dẫn xuất ổn định đơn giản cho lab:

```java
static long caseSeed(long rootSeed, int caseIndex) {
    return rootSeed ^
            (0x9E3779B97F4A7C15L *
                    (caseIndex + 1L));
}
```

Hàm thuần này không có mutable state: với cùng root + index, output seed bằng nhau dù case chạy đầu/cuối. Hằng số chỉ là mixing/scrambling theo integer arithmetic của Java; **không phải KDF cryptographic**, không hứa không có collision trên mọi input.

Trong project đầy đủ, mỗi case dùng **một Random cho input generation** và **một Random cho service**; cả hai có derived seeds riêng. Không để việc sinh input tiêu thụ cùng generator của business service, vì thêm một input field mới sẽ làm tất cả random values của service thay đổi ngoài ý muốn.

### 8.2. Root seed và case index khác nhau

Root seed đại diện **một tập scenarios**. Case index xác định **một scenario trong tập**. Nếu case 47 fail:

```text
rootSeed = 20261108
caseIndex = 47
caseSeed = derived(rootSeed,47)
```

Đây là sơ đồ, không phải caseSeed đã được tính/sinh trong một run thực. Replay chỉ case 47 phải tái tạo inputs từ `rootSeed, index`, không cần chạy lại 0–46 để “tiêu thụ đủ random trước”.

## 9. Tái hiện một lần thất bại: replay contract

Một failure report đủ tốt trả lời:

1. **Test nào?** `example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex`.
2. **Root seed?** Ví dụ `20261108`.
3. **Case index?** Ví dụ `47`.
4. **Derived seed?** Được tính lại từ root/index; in thêm để chẩn đoán.
5. **Instant/zone?** Ví dụ base instant + deterministic offset.
6. **Command nào?** Một dòng Gradle có `--tests` và `-P...` flags.
7. **Build environment?** JDK, Gradle, dependencies, OS/timezone, parallel forks.
8. **Input snapshot?** Nếu có DTO/HTTP payload/DB fixtures, lưu an toàn và có thể khôi phục.
9. **Kết quả expected/actual?** Assertion có thông điệp rõ ràng.
10. **Lỗi có tái hiện 100%?** Nếu không, xác định nguồn nondeterminism còn thiếu.

Trong lab, replay theo một method và đúng case:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=20261108 -PreproCases=80 -PreproCaseIndex=47
```

Các flags này được Gradle chuyển thành JVM system properties cho test process. Nếu thêm caseIndex chưa tồn tại (`index >= cases`), test fail sớm với validation message, không silently run zero cases.

### 9.1. Ghi seed ở đâu?

- JUnit `TestReporter.publishEntry(...)`: entry của test reporting.
- Assertion failure message: chứa seed/case index/replay command, giúp CI logs cho đúng failure.
- CI build metadata hoặc test artifact: để người khác copy lệnh.
- Structured logs: seed and scenario ID nếu không nhạy cảm.

**Không lưu secret tokens/real customer PII trong replay manifests.** Seed của synthetic PRNG thường không nhạy cảm; nếu seed có nguồn từ bí mật thực, phải bảo vệ dữ liệu và không log raw secret.

### 9.2. Không dùng “test failed, rerun until green” thay reproduction

Một rerun pass có thể chỉ cho thấy scheduler/millis/random data đã đổi. Ghi lại seed, time và environment để chạy lại **đúng failure input**; khi fix xong, thêm regression test ở case cụ thể hoặc invariant tổng quát, không xóa case khỏi suite.

## 10. Dự án Java 17 + Spring Boot 3.3

Cấu trúc file:

```text
reproducible-tests-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/repro/
    │   ├── ReproLabApplication.java
    │   ├── ReservationReceipt.java
    │   ├── ReservationService.java
    │   └── DeadlineService.java
    └── test/java/example/repro/
        ├── MutableClock.java
        ├── ReservationServiceTest.java
        ├── SeedReplayTest.java
        └── ReproBootTest.java
```

Mục tiêu lab chỉ là time/random/test reproducibility. Không cần H2, Docker, HTTP server hoặc remote message broker. Một ReservationReceipt được mô phỏng từ requestId, thời điểm và một nonsecurity pseudorandom suffix.

### 10.1. settings.gradle

```groovy
rootProject.name = 'reproducible-tests-lab'
```

### 10.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'repro.seed',
            providers.gradleProperty('reproSeed')
                    .orElse('20261108')
                    .get()

    systemProperty 'repro.cases',
            providers.gradleProperty('reproCases')
                    .orElse('80')
                    .get()

    systemProperty 'repro.caseIndex',
            providers.gradleProperty('reproCaseIndex')
                    .orElse('-1')
                    .get()

    // One JVM is sufficient to observe Spring-managed wiring.
    maxParallelForks = 1
}
```

**Giải thích:**

- `spring-boot-starter` cung cấp Spring core/auto-configuration; không khởi tạo HTTP server.
- `spring-boot-starter-test` đưa JUnit Jupiter và Spring Test.
- Không cần Mockito để tạo Clock/Random fake: Java built-ins tốt hơn.
- `repro.seed`, `repro.cases` và `repro.caseIndex` là **test JVM properties**, lấy từ Gradle project properties `-P...` để replay.
- `-PreproCaseIndex=-1` nghĩa là chạy mọi cases. Chọn một index khác để replay riêng.
- `maxParallelForks=1` giới hạn số test worker JVM, không đồng nghĩa mọi JUnit method luôn chạy tuần tự nếu project bật JUnit parallel globally; các pure unit tests vẫn được thiết kế độc lập.

**Không đưa seed cố định vào production security random configuration.** Seed test chỉ dùng để tái hiện pseudorandom business simulation.

## 11. ReproLabApplication.java — dependencies cho production

**src/main/java/example/repro/ReproLabApplication.java**

```java
package example.repro;

import java.time.Clock;
import java.util.Random;
import java.util.random.RandomGenerator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReproLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReproLabApplication.class, args);
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public RandomGenerator applicationRandom() {
        return new Random();
    }
}
```

Đây là một demo service dùng nonsecurity PRNG. Production `RandomGenerator` singleton vẫn có state chia sẻ giữa requests: sequence mỗi request phụ thuộc interleaving khi chạy đồng thời. Nếu business thực yêu cầu reproducible per-request outcomes, nên thiết kế per-request generator/factory hoặc deterministic key-based derivation; nếu chỉ cần random cân bằng không bảo mật, concurrency semantics có thể là yêu cầu khác.

**Không** dùng Spring bean `RandomGenerator` dựa vào fixed test seed trong cấu hình production mặc định; test có `@Primary` riêng ở phần sau.

## 12. ReservationReceipt.java và ReservationService.java

### 12.1. ReservationReceipt.java

**src/main/java/example/repro/ReservationReceipt.java**

```java
package example.repro;

import java.time.Instant;
import java.time.LocalDate;

public record ReservationReceipt(
        String requestId,
        String confirmationCode,
        Instant createdAt,
        LocalDate businessDate) {}
```

Record immutable dễ so sánh bằng `assertEquals`; tất cả fields được tạo từ một business call. Suffix random ở lab chỉ là display/example, **không bảo đảm globally unique ID** và không phải security token.

### 12.2. ReservationService.java

**src/main/java/example/repro/ReservationService.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.random.RandomGenerator;

import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final Clock clock;
    private final RandomGenerator random;

    public ReservationService(
            Clock clock,
            RandomGenerator random) {
        this.clock = Objects.requireNonNull(clock);
        this.random = Objects.requireNonNull(random);
    }

    public ReservationReceipt reserve(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                    "requestId must not be blank");
        }

        // Take exactly one clock snapshot.
        Instant at = clock.instant();

        // Derive local business date from the same instant.
        LocalDate date = LocalDate.ofInstant(
                at, clock.getZone());

        // Nonsecurity pseudorandom suffix, 0..999999.
        int draw = random.nextInt(1_000_000);

        return new ReservationReceipt(
                requestId,
                requestId + "-" + draw,
                at,
                date);
    }
}
```

### 12.3. Những quyết định quan trọng

1. Constructor injection giúp test tạo `new ReservationService(testClock,new Random(seed))` mà không cần Spring.
2. Validation chạy **trước** khi dùng random, nên invalid input không làm generator consume state.
3. Đồng hồ được đọc một lần để `createdAt` và `businessDate` nhất quán ngay cả khi system clock qua nửa đêm.
4. `getZone()` của Clock là business zone; trong production ví dụ dùng UTC, test có thể override sang châu Á.
5. `nextInt(1_000_000)` cho một value từ 0 đến 999.999. Nó **không** là unique ID generator hoặc secret token.
6. Nếu nhiều threads cùng dùng singleton instance, global order của random draws khác nhau; unit tests sẽ dùng instance riêng per case.

### 12.4. Vì sao không assert một literal random value từ trí nhớ?

Với same-seed tests, expected được tạo bằng **một Random độc lập có cùng seed**. Nhờ vậy test không phụ thuộc số random do người viết tự ước lượng/sao chép sai. Nếu business method thêm một random draw hoặc thay bound, test sẽ phát hiện sequence mismatch.

Tuy nhiên một test so hai instances dùng cùng algorithm không chứng minh sự phân phối ngẫu nhiên là “đủ tốt” về thống kê hoặc bảo mật; đó là bài test khác.

## 13. DeadlineService.java — deadline chính xác tại biên

**src/main/java/example/repro/DeadlineService.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class DeadlineService {

    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(
                deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }
}
```

Contract: khi `now < deadline` chưa hết hạn; khi `now == deadline` hoặc `now > deadline` đã hết hạn. Đó là lý do code dùng `!isBefore` thay vì `isAfter`.

### 13.1. Nếu deadline phụ thuộc business timezone?

Một absolute `Instant deadline` không có timezone ambiguity. Nếu yêu cầu là “hết hạn lúc 23:59:59 theo Asia/Ho_Chi_Minh”, phải chuyển business local date/time với ZoneId và quy tắc DST thích hợp thành một Instant rồi so sánh. Đừng để time-zone mặc định của CI quyết định deadline.

### 13.2. Wall time vs elapsed time

Deadline theo timestamp wall clock có thể bị ảnh hưởng khi system clock được NTP điều chỉnh. Khi chỉ đo thời lượng thực hiện hoặc timeout tương đối, `System.nanoTime()`/monotonic timer hoặc test scheduler có thể phù hợp hơn. `Clock` của `java.time` là **wall-time source**, không tự là monotonic stopwatch. Test cần biết đang kiểm tra absolute deadline hay elapsed timeout.

## 14. MutableClock.java — test-only clock có thể advance

**src/test/java/example/repro/MutableClock.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(
                new AtomicReference<>(
                        Objects.requireNonNull(initial)),
                zone);
    }

    private MutableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {
        this.current = Objects.requireNonNull(current);
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(
                current, newZone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    public void advance(Duration amount) {
        Objects.requireNonNull(amount);
        if (amount.isNegative()) {
            throw new IllegalArgumentException(
                    "Use a nonnegative duration");
        }
        current.updateAndGet(
                instant -> instant.plus(amount));
    }
}
```

Vì `withZone(...)` dùng chung `AtomicReference<Instant>`, một clock view mới với timezone khác vẫn thấy cùng absolute instant. `advance` là atomic update trên timestamp để tránh lost-update giữa threads nếu được gọi đồng thời. Nhưng việc hai test threads quan sát instant trước/sau update vẫn phụ thuộc execution order; cách tốt nhất là **không share MutableClock giữa independent tests**.

**Đây là file dưới `src/test`**, không là một clock thay cho system time trong production. Nếu cần “freeze all external time” như SQL server time/Redis TTL, phải mock/control các nguồn riêng.

## 15. ReservationServiceTest.java — 8 unit tests

**src/test/java/example/repro/ReservationServiceTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Random;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReservationServiceTest {

    private static final long SEED = 987654L;

    private static final Instant FIXED =
            Instant.parse("2026-12-31T23:30:00Z");

    private static final ZoneId HCM =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static Clock clock() {
        return Clock.fixed(FIXED, HCM);
    }

    @Test
    void fixedClockMakesTimeDeterministic() {
        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationReceipt receipt =
                service.reserve("A");

        assertEquals(FIXED, receipt.createdAt());
        assertEquals(
                LocalDate.of(2027, 1, 1),
                receipt.businessDate());

        int expected = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "A-" + expected,
                receipt.confirmationCode());
    }

    @Test
    void sameSeedProducesSameFirstReceipt() {
        ReservationService first =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationService second =
                new ReservationService(
                        clock(), new Random(SEED));

        assertEquals(
                first.reserve("SAME"),
                second.reserve("SAME"));
    }

    @Test
    void sequenceAdvanceIsPredictable() {
        Random expected = new Random(SEED);

        int draw1 = expected.nextInt(1_000_000);
        int draw2 = expected.nextInt(1_000_000);

        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationReceipt first =
                service.reserve("X");
        ReservationReceipt second =
                service.reserve("Y");

        assertEquals(
                "X-" + draw1,
                first.confirmationCode());
        assertEquals(
                "Y-" + draw2,
                second.confirmationCode());
    }

    @Test
    void zoneChangesBusinessDateNotInstant() {
        Clock utc = Clock.fixed(
                FIXED, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                FIXED, HCM);

        ReservationReceipt a =
                new ReservationService(
                        utc, new Random(SEED))
                        .reserve("ZONE");

        ReservationReceipt b =
                new ReservationService(
                        hcm, new Random(SEED))
                        .reserve("ZONE");

        assertEquals(a.createdAt(), b.createdAt());
        assertEquals(
                a.confirmationCode(),
                b.confirmationCode());

        assertEquals(
                LocalDate.of(2026, 12, 31),
                a.businessDate());

        assertEquals(
                LocalDate.of(2027, 1, 1),
                b.businessDate());
    }

    @Test
    void deadlineBoundaryIsInclusive() {
        Instant deadline =
                FIXED.plusSeconds(30);

        DeadlineService before =
                new DeadlineService(
                        Clock.fixed(
                                deadline.minusNanos(1),
                                ZoneOffset.UTC));

        DeadlineService at =
                new DeadlineService(
                        Clock.fixed(
                                deadline,
                                ZoneOffset.UTC));

        DeadlineService after =
                new DeadlineService(
                        Clock.fixed(
                                deadline.plusNanos(1),
                                ZoneOffset.UTC));

        assertFalse(before.isExpired(deadline));
        assertTrue(at.isExpired(deadline));
        assertTrue(after.isExpired(deadline));
    }

    @Test
    void mutableClockMovesTimeWithoutSleeping() {
        MutableClock mutable = new MutableClock(
                FIXED, ZoneOffset.UTC);

        DeadlineService service =
                new DeadlineService(mutable);

        Instant deadline =
                FIXED.plusSeconds(90);

        assertFalse(service.isExpired(deadline));

        mutable.advance(Duration.ofSeconds(90));
        assertTrue(service.isExpired(deadline));

        mutable.advance(Duration.ofSeconds(1));
        assertTrue(service.isExpired(deadline));
    }

    @Test
    void invalidRequestDoesNotConsumeRandomness() {
        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> service.reserve("  "));

        assertEquals(
                "requestId must not be blank",
                ex.getMessage());

        int firstDraw = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "VALID-" + firstDraw,
                service.reserve("VALID")
                        .confirmationCode());
    }

    @Test
    void independentGeneratorsDoNotShareStateAcrossThreads()
            throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        try {
            Callable<ReservationReceipt> job =
                    () -> new ReservationService(
                            clock(),
                            new Random(SEED))
                            .reserve("PARALLEL");

            Future<ReservationReceipt> first =
                    pool.submit(job);
            Future<ReservationReceipt> second =
                    pool.submit(job);

            ReservationReceipt expected =
                    new ReservationService(
                            clock(),
                            new Random(SEED))
                            .reserve("PARALLEL");

            assertEquals(
                    expected,
                    first.get(15, TimeUnit.SECONDS));
            assertEquals(
                    expected,
                    second.get(15, TimeUnit.SECONDS));
        }
        finally {
            pool.shutdownNow();
        }
    }
}
```

### 15.1. Ý nghĩa của tám tests

| JUnit method | Bằng chứng |
| --- | --- |
| `fixedClockMakesTimeDeterministic` | Exact Instant + business date + first PRNG draw |
| `sameSeedProducesSameFirstReceipt` | Hai Random cùng seed, cùng call order có cùng result |
| `sequenceAdvanceIsPredictable` | Lần rút 1/2 giữ thứ tự deterministic |
| `zoneChangesBusinessDateNotInstant` | Same instant/PRNG, khác LocalDate do timezone |
| `deadlineBoundaryIsInclusive` | T-1ns false, T true, T+1ns true |
| `mutableClockMovesTimeWithoutSleeping` | Advance clock 90s không ngủ thật |
| `invalidRequestDoesNotConsumeRandomness` | Invalid input không rút số, first valid call vẫn là draw #1 |
| `independentGeneratorsDoNotShareStateAcrossThreads` | Mỗi callable có Clock và Random riêng, kết quả không phụ thuộc thứ tự threads |

### 15.2. Vì sao test concurrency không sử dụng một Random dùng chung?

Mỗi callable tạo `new Random(SEED)`; cả hai tạo và tiêu thụ state riêng. Cho dù task thứ hai được scheduler chạy trước, nó vẫn nhận **first draw của generator riêng**, nên receipt giống nhau. Test này chứng minh isolation design, **không** chứng minh hiệu năng/throughput của parallel RNG.

### 15.3. Vì sao deadline test dùng ±1 nanosecond?

Thời điểm là `Instant` hỗ trợ nanosecond resolution. Boundary logic `isBefore`/`isAfter` nên test ba trạng thái sát nhất thay vì ngủ 1 giây để chờ expiry. Nếu production persistence DB chỉ lưu milliseconds, boundary tests còn phải xét rounding/truncation của data source.

### 15.4. Vì sao không assert hai random draws phải khác?

Trong một bounded random range, hai successive draws **có thể bằng nhau theo xác suất**. `sequenceAdvanceIsPredictable` kiểm tra output của đúng PRNG sequence theo algorithm, không khẳng định hai draws luôn khác. Đây là cách tránh test flaky do một event ngẫu nhiên hợp lệ.

## 16. SeedReplayTest.java — root seed + case index

**src/test/java/example/repro/SeedReplayTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SeedReplayTest {

    private static final Instant BASE =
            Instant.parse("2026-12-27T00:00:00Z");

    private static final long INPUT_MIX =
            0xD1B54A32D192ED03L;

    private static long rootSeed() {
        return Long.parseLong(
                System.getProperty(
                        "repro.seed", "20261108"));
    }

    private static int caseCount() {
        return Integer.parseInt(
                System.getProperty(
                        "repro.cases", "80"));
    }

    private static int selectedCase() {
        return Integer.parseInt(
                System.getProperty(
                        "repro.caseIndex", "-1"));
    }

    private static long caseSeed(
            long root, int index) {
        return root ^
                (0x9E3779B97F4A7C15L *
                        (index + 1L));
    }

    private record Scenario(
            String id,
            Instant instant,
            ZoneId zone,
            long seed) {}

    private static Scenario scenario(
            long root, int index) {
        long seed = caseSeed(root, index);

        // Separate PRNG stream for scenario inputs.
        Random input = new Random(seed ^ INPUT_MIX);

        Instant instant = BASE.plusSeconds(
                input.nextInt(7 * 24 * 60 * 60));

        ZoneId zone = input.nextBoolean()
                ? ZoneOffset.UTC
                : ZoneId.of("Asia/Ho_Chi_Minh");

        return new Scenario(
                "CASE-" + index,
                instant,
                zone,
                seed);
    }

    private static ReservationReceipt execute(
            Scenario scenario) {
        Clock clock = Clock.fixed(
                scenario.instant(),
                scenario.zone());

        return new ReservationService(
                clock,
                new Random(scenario.seed()))
                .reserve(scenario.id());
    }

    @Test
    void scenarioOrderDoesNotChangeCaseResults() {
        long root = rootSeed();

        Map<Integer, ReservationReceipt> before =
                new HashMap<>();

        for (int index = 0; index < 10; index++) {
            before.put(
                    index,
                    execute(scenario(root, index)));
        }

        for (int index = 9; index >= 0; index--) {
            assertEquals(
                    before.get(index),
                    execute(scenario(root, index)));
        }
    }

    @Test
    void replaySingleCaseFromRootSeedAndIndex(
            TestReporter reporter) {
        long root = rootSeed();
        int count = caseCount();
        int onlyIndex = selectedCase();

        assertTrue(
                count >= 1 && count <= 100_000,
                "repro.cases must be in [1,100000]");

        assertTrue(
                onlyIndex >= -1 && onlyIndex < count,
                "repro.caseIndex must be -1 or " +
                "a valid index below repro.cases");

        reporter.publishEntry(
                "repro.seed", Long.toString(root));

        reporter.publishEntry(
                "repro.cases", Integer.toString(count));

        reporter.publishEntry(
                "repro.caseIndex",
                Integer.toString(onlyIndex));

        for (int index = 0; index < count; index++) {
            if (onlyIndex >= 0 && onlyIndex != index) {
                continue;
            }

            Scenario s = scenario(root, index);

            try {
                ReservationReceipt receipt =
                        execute(s);

                int expectedDraw =
                        new Random(s.seed())
                                .nextInt(1_000_000);

                assertEquals(
                        s.id() + "-" + expectedDraw,
                        receipt.confirmationCode());

                assertEquals(
                        s.instant(),
                        receipt.createdAt());

                assertEquals(
                        LocalDate.ofInstant(
                                s.instant(), s.zone()),
                        receipt.businessDate());
            }
            catch (AssertionError | RuntimeException ex) {
                String command =
                        "./gradlew test --tests " +
                        "example.repro.SeedReplayTest." +
                        "replaySingleCaseFromRootSeedAndIndex" +
                        " -PreproSeed=" + root +
                        " -PreproCases=" + count +
                        " -PreproCaseIndex=" + index;

                throw new AssertionError(
                        "Reproduce with: " + command +
                        "; derivedCaseSeed=" + s.seed() +
                        "; instant=" + s.instant() +
                        "; zone=" + s.zone(),
                        ex);
            }
        }
    }
}
```

**Hai phương thức JUnit**:

- `scenarioOrderDoesNotChangeCaseResults` chạy indexes 0–9 theo thứ tự tăng rồi giảm; mỗi case derive seed riêng nên output cùng index không đổi.
- `replaySingleCaseFromRootSeedAndIndex` chạy mặc định 80 cases, hoặc chỉ case được chọn. Khi fail, exception được bao thêm lệnh Gradle cụ thể + derived seed + instant + timezone. Nó không biến failure thành success; wrapper vẫn throw AssertionError.

### 16.1. Tách input RNG và service RNG

`scenario(...)` dùng `new Random(caseSeed ^ INPUT_MIX)` để sinh một timestamp và zone. `execute(...)` dùng `new Random(caseSeed)` riêng cho ReservationService. Nếu sau này cần thêm một input field, thay đổi số draws của input RNG có thể làm **inputs** sau đó thay đổi, nhưng không âm thầm đẩy service RNG sang draw #N+1.

Muốn cross-version reproduction tuyệt đối, vẫn cần giữ nguyên seed derivation/input generation algorithm, timezone rules và code/dependencies.

### 16.2. Vì sao các case không phụ thuộc index trước đó?

Mỗi case chỉ cần `root` và `index` để tái tạo seed. Chạy `caseIndex=47` không cần chạy 0–46 trước để advance global PRNG. Điều này giảm thời gian điều tra và làm replay đúng trong một parallel suite.

### 16.3. Có nên hardcode seed mặc định?

Có một **seed mặc định ổn định** để smoke/regression runs có thể tái hiện. Bên cạnh đó, CI có thể tạo thêm các root seeds mới và lưu chúng trong build metadata. Không thay fixed regression seed bằng một timestamp mới rồi bỏ mất khả năng chạy lại các failures đã phát hiện.

### 16.4. TestReporter không phải console logging

JUnit Jupiter inject `TestReporter` vào method, có thể lưu reporting entries theo runner. Gradle console có thể ẩn output nếu chưa cấu hình reporting/testLogging; vì vậy failure message cũng chứa replay command. Không dựa duy nhất vào `System.out.println` khi CI test runner có thể chỉ hiển thị stdout của failed tests.

## 17. ReproBootTest.java — override Clock/RandomGenerator trong Spring context

**src/test/java/example/repro/ReproBootTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Random;
import java.util.random.RandomGenerator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ReproLabApplication.class,
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
@Import(ReproBootTest.FixedTestBeans.class)
class ReproBootTest {

    private static final Instant FIXED =
            Instant.parse("2026-12-31T23:30:00Z");

    private static final ZoneId ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final long SEED = 314159L;

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTestBeans {

        @Bean
        @Primary
        Clock testClock() {
            return Clock.fixed(FIXED, ZONE);
        }

        @Bean
        @Primary
        RandomGenerator testRandom() {
            return new Random(SEED);
        }
    }

    @Autowired
    ReservationService reservationService;

    @Autowired
    DeadlineService deadlineService;

    @Autowired
    Clock clock;

    @Test
    void springUsesPrimaryTestClockAndRandomGenerator() {
        assertNotNull(reservationService);
        assertNotNull(deadlineService);
        assertEquals(FIXED, clock.instant());

        ReservationReceipt receipt =
                reservationService.reserve("BOOT");

        int expectedDraw = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "BOOT-" + expectedDraw,
                receipt.confirmationCode());

        assertEquals(FIXED, receipt.createdAt());

        assertEquals(
                LocalDate.of(2027, 1, 1),
                receipt.businessDate());

        assertTrue(
                deadlineService.isExpired(FIXED));
    }
}
```

### 17.1. Vì sao @TestConfiguration + @Primary?

Main app có production beans `Clock.systemUTC()` và `new Random()`. Test import thêm `FixedTestBeans` với hai beans cùng type và đánh dấu `@Primary`. Spring lựa chọn primary test beans để inject vào `ReservationService`/`DeadlineService`.

Đây là test-specific wiring, không sửa production code để dùng hardcoded seed hoặc frozen clock.

### 17.2. @Import bảo đảm test config được nạp

Nested `@TestConfiguration` có thể được Spring Boot phát hiện theo patterns nhất định; dùng `@Import(ReproBootTest.FixedTestBeans.class)` làm phạm vi rõ và dễ đọc. Bean config có thể ảnh hưởng Spring TestContext cache key; nếu nhiều test classes import các test configurations khác nhau, contexts có thể không được share.

### 17.3. Cẩn thận với singleton RandomGenerator

`@Bean RandomGenerator testRandom()` tạo singleton stateful generator trong Spring context. Demo chỉ có **một Boot integration method** dùng nó một lần. Nếu thêm nhiều methods vào class, hoặc context được reuse qua test classes, random state có thể đã advance, làm test khó tái hiện.

Với integration tests phức tạp, cân nhắc inject `ObjectProvider<RandomGenerator>` với prototype supplier, hoặc thiết kế `RandomSourceFactory` tạo independent generator theo test/case/request seed. Không gọi `Random.setSeed(...)` trên singleton đang được dùng bởi parallel test threads rồi coi như isolation.

### 17.4. Có cần @MockBean?

Không. Clock và RandomGenerator có thể inject bằng bean override. `@MockBean` thường có ích để thay external collaborator, nhưng dùng Mockito mock của Clock rồi stub toàn bộ `instant()/getZone()` dễ bỏ sót behavior và làm test yếu đi. `Clock.fixed` thể hiện thời gian chính xác, rõ ràng và không yêu cầu network.

## 18. Chạy bộ lab

Cần JDK 17, Gradle Wrapper tương thích Spring Boot 3.3 (ví dụ Gradle 8.7), và khả năng tải dependencies từ Maven Central/cache. Nếu chưa có wrapper, tạo wrapper phù hợp trước; chỉ copy `build.gradle` không tự sinh ra `gradlew`.

Linux/macOS — chạy tất cả:

```bash
./gradlew test
```

Chạy một class:

```bash
./gradlew test --tests example.repro.ReservationServiceTest
./gradlew test --tests example.repro.SeedReplayTest
./gradlew test --tests example.repro.ReproBootTest
```

Chạy 80 deterministic cases với root seed tùy chọn:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=-1
```

Chạy lại case 47 duy nhất:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47
```

**Kết quả dự kiến:** 11 phương thức JUnit pass trong code đúng: 8 unit tests, 2 replay tests, 1 Spring Boot integration test. Test replay có vòng lặp 80 cases **bên trong một JUnit method**; JUnit method count vẫn là 11, không biến 80 iterations thành 80 test methods riêng.

| Test class | Số @Test methods | Có Spring context? |
| --- | ---: | --- |
| `ReservationServiceTest` | 8 | Không |
| `SeedReplayTest` | 2 | Không |
| `ReproBootTest` | 1 | Có |
| **Tổng** | **11** | Theo class |

**Không tuyên bố đã chạy Gradle** trong bài viết này. Khi chạy, xem `build/test-results/test` (JUnit XML) và Gradle console/HTML report để biết pass/fail/skipped thật. Không in giả output như “BUILD SUCCESSFUL” hoặc seed values được đo nếu chưa thực thi.

## 19. Kịch bản cố ý gây lỗi để học cách replay

Một cách học hiệu quả là đưa **bug giả trong sandbox branch**, không commit vào production:

1. Chạy `SeedReplayTest` với `-PreproSeed=1357911` và `-PreproCases=80`, ghi version/branch.
2. Sửa `ReservationService.reserve(...)` để sai business date, ví dụ dùng `LocalDate.now(Clock.systemUTC())` thay vì suy ra từ injected instant/zone.
3. Một số cases với zone Asia/Ho_Chi_Minh gần midnight có thể fail; assertion wrapper chứa replay command.
4. Copy lệnh đó, chọn `-PreproCaseIndex=N` được in trong exception.
5. Chạy lại chính case N với cùng source branch/JDK/tzdb/seed.
6. Sửa bug bằng `LocalDate.ofInstant(at,clock.getZone())`.
7. Chạy lại case N (regression), sau đó toàn bộ root seed suite.
8. Lưu case N thành một regression test hoặc giữ seed trong CI seed corpus.

**Lưu ý:** bug minh họa ở bước 2 phụ thuộc timestamp/zone của scenario; không cam kết mọi seed tạo đúng một failure. Nếu một seed cụ thể không tạo failure, tạo case gần boundary bằng một unit test fixed Clock như `zoneChangesBusinessDateNotInstant` rồi kiểm chứng. Không phát biểu “đã reproduce bug” nếu chưa thực chạy.

### 19.1. Tái hiện lỗi không có nghĩa chỉ cần seed

Nếu lỗi do race, DB transaction isolation, I/O, CPU scheduling hoặc network, chạy lại root+case seed có thể vẫn pass. Khi đó cần lưu event ordering, request payloads, DB snapshot, container versions và test scheduler/parallel settings. Seed là **một phần** của reproduction contract, không phải toàn bộ.

## 20. Một failure artifact nên có gì?

Ghi đủ thông tin phục vụ đồng đội/CI:

```yaml
# Illustrative failure report, not measured output.
test: example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex
rootSeed: 1357911
caseIndex: 47
caseCount: 80
prngAlgorithm: java.util.Random
sourceRevision: "the exact commit used by the failing run"
jdk: "record java -version output"
gradle: "record gradle wrapper version"
timeZone: "UTC or explicit ZoneId used by case"
instant: "record generated Instant"
locale: "record Locale if formatting matters"
execution:
  forks: 1
  junitParallel: false
fixtures: "reference sanitized fixture snapshot"
failure: "expected vs actual assertion output"
replay: "./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47"
```

Đây là **template**, không phải môi trường thực đã được đo. Trong CI nên tự điền `sourceRevision`, JDK, Gradle, OS/arch, container image digests và exact failure. Không ghi secrets/tokens/customer PII dưới dạng raw fixture.

### 20.1. Ghi TestReporter entries có đủ không?

Nó giúp lưu root/case metadata, nhưng còn phải chắc test runner thu thập artifacts. Gradle console mặc định có thể không in mọi report entry. Vì vậy failure wrapper chứa một **lệnh replay có thể copy** trực tiếp trong AssertionError.

### 20.2. Tạo regression corpus

Lưu một tập seeds/case indexes đã từng làm lộ bug. CI chạy default deterministic seeds trước, sau đó optional nightly fuzz seeds mới, và lưu seed của các failures mới để replay. Không xóa các seeds cũ sau khi fix vì chúng trở thành regression input.

## 21. Đổi seed nhưng giữ algorithm và thứ tự gọi

Muốn mở rộng coverage, chạy nhiều root seeds. Nhưng với một root seed cố định:

```text
root seed 20261108
  case 0 -> derive s0 -> fixed clock and Random(s0)
  case 1 -> derive s1 -> fixed clock and Random(s1)
  case 2 -> derive s2 -> fixed clock and Random(s2)
  ...
  case 79 -> derive s79 -> fixed clock and Random(s79)
```

Thứ tự thực thi các cases có thể đảo mà kết quả **của từng index** không đổi. Đây là điểm quan trọng khi bật JUnit parallel hoặc chia suite thành CI shards.

### 21.1. Khi case IDs là strings

Nếu dùng case key như `tenant:invoice:123` thay vì index, cần một stable hash/seed derivation rõ version và encoding. **Không** dùng `Objects.hash(...)` có input chứa mutable values hoặc hash function phụ thuộc environment mà không kiểm chứng stability; tránh dùng random salt được thay mỗi process.

Một gợi ý là dùng SHA-256 trên bytes UTF-8 của `rootSeed + canonicalCaseId` để derive PRNG seed; nhưng đó là seed derivation cho test cases, **không biến java.util.Random thành cryptographic generator**.

### 21.2. Không gán seed bằng global counter chạy song song

`AtomicLong.getAndIncrement()` thread-safe nhưng thứ tự thread nào nhận seed N vẫn phụ thuộc scheduling. Nếu muốn stable assignment, dùng index/key của case làm đầu vào, không dựa vào thời điểm task bắt đầu.

### 21.3. Không share fixture objects

Clock có thể immutable như `Clock.fixed`, nhưng Random mutable. Kể cả cùng Clock, không share `List` mutable hoặc in-memory repository giữa cases nếu tests thay state. Mỗi case nên tạo dependencies thích hợp, đảm bảo không leak.

## 22. Test parallel: JVM, threads và process state

Có ít nhất ba phạm vi chạy song song:

1. **JUnit parallel methods** trong một JVM.
2. **Gradle/Maven test forks** nhiều JVM processes.
3. **CI shards/agents** ở nhiều containers/machines.

Một local static `Random` hoặc static `Clock` chỉ thuộc JVM đó. Hai Gradle forks sẽ không chia sẻ static state, nhưng có thể cùng ghi **external database/Redis topic** nếu dùng chung connections.

### 22.1. JUnit parallel methods

Nếu bật `junit.jupiter.execution.parallel.enabled=true`, independent unit tests của lab vẫn dùng mỗi method một new Random/Clock nên có thể chạy song song. Nhưng Spring Boot test với singleton `RandomGenerator` và tests khác chia sẻ cùng context cần cô lập hoặc serialize riêng.

JUnit `@Execution(ExecutionMode.SAME_THREAD)`/resource locks có thể giảm concurrency ở nhóm tests chia state; không phải dùng nó để che thiếu isolation rồi bật parallel trên toàn repo.

### 22.2. Gradle maxParallelForks

`maxParallelForks=1` trong lab giữ một worker JVM. Tăng forks có thể tăng throughput nhưng cache Spring ApplicationContext ở mỗi JVM là riêng; seed/root metadata cần được truyền như nhau tới workers. Nếu case index được chia theo shards, mỗi shard cần danh sách indices cụ thể chứ không dùng một shared PRNG tuần tự.

### 22.3. Process-global TimeZone, Locale và system properties

Các lệnh kiểu:

```java
TimeZone.setDefault(
        TimeZone.getTimeZone("UTC"));
Locale.setDefault(Locale.US);
System.setProperty("feature.flag", "true");
```

là **mutations global trong JVM**; tests chạy song song có thể ghi đè nhau. Ưu tiên truyền `Clock`, `ZoneId`, `Locale`, config properties qua dependency injection hoặc parameter. Nếu buộc phải mutate globals, restore chúng trong finally và dùng synchronization/test resource lock thích hợp; chưa chắc an toàn nếu framework đọc chúng ở thread khác.

### 22.4. External state

Một replay seed không reset Redis, PostgreSQL, Kafka offsets, S3 objects, file system hay fake HTTP server state. Muốn tái hiện lỗi, phải quản lý fixture initialization/cleanup và container lifecycle riêng. Đừng nhầm `@DirtiesContext` với xóa dữ liệu external provider.

## 23. Spring Boot test configuration và context cache

Trong Spring Boot 3.3, `@TestConfiguration` và `@Import` cho test override dependencies rõ ràng. Nhưng Spring TestContext cache dùng merged configuration key: nếu test class A có một fixed clock config, class B có một config khác hoặc `@MockBean` definitions khác, Spring có thể tạo context riêng.

### 23.1. Không để random state rò qua reused context

`RandomGenerator` là stateful. Một singleton bean có thể sống xuyên nhiều JUnit methods/classes do cached Spring context. Nếu test A đã draw #1 và test B mong draw #1 của cùng seed, B sẽ nhận draw #2.

Phương án:

- Unit: tạo service/Random mới per test.
- Spring integration: cung cấp factory tạo generator mới per business operation hoặc per test scope; dùng test-only bean có lifecycle phù hợp.
- Khi không tránh được singleton, có thể đo baseline sequence/snapshot state, serialize tests và kiểm soát reset an toàn; nhưng đừng reset `Random.setSeed` khi parallel requests khác đang dùng.
- `@DirtiesContext` sau test có thể làm registry/beans được tạo lại nhưng tốn startup, không giải quyết mọi external state. Dùng có chủ đích, không mặc định.

### 23.2. Clock.fixed là immutable nên có thể share

Một `Clock.fixed` không có state advancing và an toàn chia sẻ; tuy nhiên business date vẫn phụ thuộc zone. `MutableClock` là mutable và không nên share giữa parallel tests, trừ khi test đang cố kiểm tra coordinated advances.

### 23.3. @MockBean, @MockitoBean và version boundary

Spring Boot 3.3 `@MockBean` là annotation test support truyền thống; các Boot/Spring Framework versions mới có thể dùng `@MockitoBean` với semantics/version khác. Bài dùng @TestConfiguration/@Primary nên không phụ thuộc migrate annotations. Khi nâng Boot, vẫn phải test cache key, context initialization và test bean resolution.

## 24. Test data generation libraries và property-based testing

Khi dùng jqwik, QuickTheories, Instancio hoặc custom random fixtures:

- Tìm cơ chế **seed/report/replay chính thức của thư viện**.
- Ghi seed của framework/test engine, không tự nghĩ rằng Gradle `repro.seed` đã điều khiển RNG internal của thư viện.
- Một số framework có shrinker để thu nhỏ failing case. Replay nên lưu **shrunk input** và root seed ban đầu.
- Khi test thực sự ngẫu nhiên nhiều lần, hãy có deterministic regression suite và fuzz suite riêng.
- Không coi “lần này chạy 10.000 cases không fail” là proof không có race/bug.
- Khi phụ thuộc test runner, JUnit parallel, scheduler, cố định root seed chưa chắc cố định execution ordering.

### 24.1. Test invariants vs exact output

Một invariant tốt:

- Confirmation code luôn có prefix requestId.
- Number nằm trong khoảng 0..999.999.
- CreatedAt luôn là instant mà Clock trả.
- BusinessDate được chuyển từ cùng instant theo ZoneId.

Nếu app business không yêu cầu exact random sequence, test invariants bền hơn assert literal số. Nhưng **khi mục tiêu là replay một sequence defect**, assert expected PRNG sequence ở một test riêng vẫn có giá trị.

### 24.2. Shrinking một failure

Nếu randomized case 47 tạo một payload phức tạp, thu nhỏ dữ liệu để tìm minimal counterexample; sau đó thêm regression test với fixed data. Seed vẫn hữu ích để tái tạo đường discovery, nhưng minimal deterministic case thường dễ review và đáng tin hơn cho CI lâu dài.

## 25. Các lỗi phổ biến

### 25.1. Clock.systemUTC() được gọi trong service thay vì inject

Test inject fixed Clock nhưng business code tiếp tục dùng `Instant.now()`/`Clock.systemUTC()` tự tạo. Test không thể kiểm soát thời gian; sát midnight fail. Đưa Clock vào constructor và assert exact createdAt.

### 25.2. Gọi Clock hai lần cho một business snapshot

Đọc timestamp một lần rồi `LocalDate.now(clock)` ở lần khác có thể qua midnight. Sửa: derive cả fields từ một Instant.

### 25.3. Dùng timezone mặc định

Test ở máy UTC pass, máy Asia/Ho_Chi_Minh fail. Dùng explicit `ZoneId` và `LocalDate.ofInstant`.

### 25.4. Dùng Thread.sleep để chờ deadline

`Thread.sleep(1000)` có thể không đủ hoặc gây suite chậm. Dùng fixed/mutable Clock và check T-1/T/T+1.

### 25.5. Offset system clock nhưng tưởng frozen

`Clock.offset(Clock.systemUTC(),Duration.ofDays(1))` vẫn chạy. Nếu muốn fixed, dùng `Clock.fixed` trước rồi offset.

### 25.6. Cùng seed nhưng khác draw order

Một developer thêm `nextBoolean()` trước `nextInt()`; sequence sau thay đổi. Ghi algorithm/call order và test contract cụ thể.

### 25.7. Shared seeded Random trong parallel

Java Random thread-safe nhưng task assignment phụ thuộc scheduler. Dùng per-case generator, derived seed từ index/key.

### 25.8. Dùng ThreadLocalRandom rồi ghi root seed

Không có public set-seed path để replay theo root như `new Random(seed)`. Đừng hứa exact replay với ThreadLocalRandom nếu không kiểm soát generator.

### 25.9. Gán seed bằng currentTimeMillis

`new Random(System.currentTimeMillis())` làm thất bại không replay được nếu không log seed. Tốt hơn dùng configuration seed cho tests; production seed không nên lộ thông tin bảo mật.

### 25.10. Random(seed) để tạo token thực

Có thể dự đoán; dùng SecureRandom và security design đúng. Test-only seeded PRNG không được leak sang production secrets.

### 25.11. Không log case index khi fail

Một test 10.000 scenarios fail giữa vòng lặp nhưng log chỉ “expected vs actual”. Thêm seed/index/command vào assertion wrapper, lưu input snapshot.

### 25.12. Đặt seed trong JVM A nhưng test chạy JVM B

Gradle forks/CI shards có separate JVM props/processes. Kiểm tra Gradle task forwarding and reporting, không chỉ shell env var một process.

### 25.13. Reproduce random input nhưng DB chưa reset

Cùng seed + same time, dữ liệu database khác làm assertion khác. Test fixture/transaction cleanup bắt buộc khi DB involved.

### 25.14. Thay đổi dependency/JDK khi replay

Random algorithm, timezone rules, JSON serializer hoặc sorting behavior có thể khác. Pin JDK/runtime versions và report source revision.

### 25.15. Test chạy lại pass thì xóa failure

Một flaky race có thể mất khi scheduling đổi. Lưu artifact và tìm nguyên nhân, thêm deterministic regression/barrier-based concurrency tests.

### 25.16. Đổi system default Zone/Locale trong parallel suite

Global process state có thể ảnh hưởng tests khác. Inject explicit ZoneId/Locale hoặc resource locking.

### 25.17. Fixed Clock nhưng Redis TTL vẫn thật

Redis server tự expire theo wall time của Redis; advance Java Clock không làm Redis key biến mất. Sử dụng Redis tests hoặc fake cache TTL provider clock theo mục tiêu.

### 25.18. Clock.fixed dẫn đến vòng chờ vô hạn

Code poll until `clock.instant().isAfter(end)` với fixed Clock sẽ không kết thúc. Thiết kế test advances time explicitly hoặc inject scheduler/ticker cho elapsed operations.

### 25.19. Random output expected hardcode sai

Đoán giá trị `nextInt` từ seed mà không tính theo thuật toán, khiến test đỏ vô lý. Dùng independent generator same seed cho expected, hoặc golden vector đã được kiểm chứng.

### 25.20. Coi reproducible input là reproducible scheduling

Một race về check-then-act vẫn phụ thuộc interleaving. Dùng barriers/latches, deterministic scheduler hoặc concurrency model checking thay vì chỉ tăng số seeds.

## 26. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân chính | Hướng kiểm tra |
| --- | --- | --- |
| Test fail chỉ gần nửa đêm | LocalDate.now()/timezone default | Fixed Clock + explicit ZoneId |
| CI và laptop khác businessDate | System timezone/tzdb | Pin ZoneId, JDK/tzdb |
| Deadline exactly T không expired | Dùng isAfter thay vì >= | Test T-1ns/T/T+1ns |
| Test Clock không tác động | Service dùng Instant.now() trực tiếp | Constructor injection |
| Random same seed nhưng khác result | Draw order/algorithm thay đổi | Lock call sequence/implementation |
| Một test pass một mình, fail trong suite | Shared PRNG/Clock/DB/context | Fresh dependencies and cleanup |
| Parallel test dùng cùng seed nhưng case khác | Shared PRNG scheduling | Derive per case index |
| Repro command chạy zero cases | Invalid caseIndex/count | Validate bounds early |
| Không thấy seed trong console | TestReporter entry không được render | Failure message + CI artifact |
| Replay case khác case gốc | Tái tạo input qua sequential global RNG | Pure per-case seed derivation |
| Spring integration test random đổi mỗi lần | Production bean được inject thay test bean | @Primary/@Import |
| Boot test thứ hai nhận draw #2 | Cached context singleton RNG | Per-test factory/prototype |
| UUID.randomUUID không replay theo seed | SecureRandom/internal entropy | Inject deterministic test-only ID factory |
| Timezone fixed nhưng scheduler vẫn chờ thật | Clock không điều khiển scheduler | Virtual-time scheduler/fake executor |
| DB CURRENT_TIMESTAMP khác Java Clock | Database/server clock khác | Provider test/explicit injected timestamps |
| Test gần DST chuyển sai | ZoneRules/tzdb semantics | Zone-specific tests, version pinning |
| CI re-run xanh sau failure | Race hoặc changed external data | Save seed, environment, event order |
| Test nhận cùng random draw hai lần | Hợp lệ về xác suất | Test range/algorithm, không assert unique |
| Fixed clock khiến polling loop treo | Clock không advance | MutableClock/test ticker |
| Test dùng wrong -P flag | Gradle properties không forwarded | Inspect build.gradle systemProperty mapping |
| Random seed bị lộ như secret | Dùng seeded PRNG tạo security token | SecureRandom and secret policy |

## 27. Chiến lược kiểm thử theo lớp

### 27.1. Pure unit: phần lớn clock/seed tests

Tạo service bằng `new` với fixed/mutable Clock và `new Random(seed)`. Không cần Spring context; tests chạy nhanh và có isolation tốt. Chỉ test logic boundary/invariants.

### 27.2. Spring integration: injection/configuration

Dùng `@SpringBootTest`, `@TestConfiguration`/`@Primary`, assert injected service thật dùng Clock và generator của test. Không lạm dụng context restart để reset random state nếu có thể tạo factory/test scope.

### 27.3. Provider integration: external time/random consumers

Nếu logic phụ thuộc DB `CURRENT_TIMESTAMP`, Redis expiration, Kafka scheduling, network retries, hãy test provider boundary riêng. Seed của Java service không điều khiển external server. Testcontainers có thể cô lập resources; không tự làm thời gian của chúng trở nên ảo.

### 27.4. Full E2E và chaos/concurrency

Cần metadata, event traces, user inputs, jitter, timeouts, host scheduling và external failure injection. Cùng root seed chỉ chứng minh data generator; không chứng minh toàn deployment deterministic.

## 28. Bài tập thực hành

1. Đổi `Clock.fixed` từ 2026-12-31T23:30Z thành 2027-01-01T00:30Z. Giải thích business dates UTC/HCM.
2. Đổi zone HCM sang America/New_York, bổ sung DST boundary test với ZoneId rõ.
3. Sửa DeadlineService dùng `clock.instant().isAfter(deadline)`. Test đúng deadline phải fail; sửa lại.
4. Thử `Clock.offset(Clock.fixed(...),Duration.ofDays(1))`. Assert returned Instant tăng một ngày mà không có sleep.
5. Dùng `MutableClock.advance(Duration.ofMillis(1))` và kiểm tra milliseconds boundary.
6. Gọi `reserve("X")` hai lần với cùng Random, so expected draw #1/#2, không assert outputs khác nhau.
7. Thêm một `random.nextBoolean()` trong ReservationService trước nextInt; quan sát test sequence fail.
8. Bỏ validation trước random draw, làm invalidRequestDoesNotConsumeRandomness test fail.
9. Thay injected Clock bằng `Instant.now()` trực tiếp, xem fixedClockMakesTimeDeterministic fail.
10. Đổi root seed từ 20261108 thành 1357911 và chạy lại tất cả SeedReplayTest cases.
11. Chọn `-PreproCaseIndex=47`, bảo đảm chỉ index này được chạy trong vòng lặp.
12. Chọn `-PreproCaseIndex=1000` khi count=80, kiểm tra test fail sớm thay vì âm thầm bỏ qua.
13. Dùng input PRNG và service PRNG chung một instance; quan sát thêm input draw làm service output thay đổi.
14. Chạy case indexes theo thứ tự ngược, xác minh outcomes theo index vẫn như trước.
15. Thử một shared Random trên hai threads, giải thích sự khác biệt thread safety và deterministic assignment.
16. Đưa production RandomGenerator bean thành singleton vào nhiều tests Spring; quan sát sequence leakage nếu context reuse. Đề xuất factory/prototype design.
17. Bật JUnit parallel cho pure unit tests, chạy lặp và xác minh chúng không dùng shared MutableClock.
18. Tăng Gradle maxParallelForks và ghi nhận JVM boundaries/tác động Spring TestContext cache.
19. Dùng TestReporter và CI artifacts để lưu root/case seed.
20. Tạo sandbox bug về timezone/localDate, copy replay command từ error và sửa regression.
21. Tạo sandbox bug về deadline equality, viết fixed-clock regression test không cần random.
22. Với database external, thêm fixture reset để cùng seed/time có cùng dữ liệu.
23. Với test data library, tìm flag seed/shrink của framework thay vì giả định Gradle repro.seed điều khiển được nó.
24. Đo real performance bằng monotonic timer riêng, không cố dùng Clock.fixed cho elapsed.
25. Viết failure artifact gồm exact JDK/build/CI branch, timezone, seed, case index, inputs và error text.

## 29. Checklist trước khi merge

- [ ] Business code nhận Clock qua dependency injection, không dùng Instant.now() hardcode ở logic thời gian.
- [ ] Cùng một operation dùng một time snapshot để sinh Instant/LocalDate.
- [ ] Timezone explicit; không phụ thuộc host default zone khi không chủ đích.
- [ ] Deadline có tests ở trước, đúng và sau boundary.
- [ ] Test dùng Clock.fixed hoặc MutableClock thay cho sleep không cần thiết.
- [ ] Đã phân biệt wall clock và monotonic elapsed time/scheduler.
- [ ] RandomGenerator/Random implementation và seed được biết khi replay.
- [ ] Seed không được dùng làm production security entropy.
- [ ] PRNG state riêng cho mỗi test/case; không chia sẻ mutable RNG giữa parallel methods.
- [ ] Case seed được derive theo root+index/id, không gán theo scheduling order.
- [ ] Input RNG stream tách khỏi business RNG stream.
- [ ] Không assert hai random draws luôn khác nhau.
- [ ] Test capture root seed, case index, derived seed, zone, instant khi fail.
- [ ] Có lệnh replay Gradle chính xác với test method selector.
- [ ] Gradle chuyển -P properties sang JVM system properties.
- [ ] Có validation cho caseCount/index, không chạy zero cases im lặng.
- [ ] JUnit TestReporter hoặc artifact ghi seed, error message chứa replay command.
- [ ] Unit test không dùng static Random/MutableClock shared giữa methods.
- [ ] Boot integration test @TestConfiguration/@Primary có scope rõ và assert injected values.
- [ ] Không reset singleton PRNG giữa parallel tests qua Random.setSeed.
- [ ] Spring TestContext cache reuse và RNG singleton state được xét.
- [ ] JUnit/Gradle forks, CI shards và parallel settings được ghi khi điều tra flaky.
- [ ] DB/Redis/network fixtures được khởi tạo/cleanup riêng, không trông cậy seed.
- [ ] JDK, tzdb, dependency versions, OS/arch và source revision được ghi.
- [ ] Không log PII/tokens/secret values trong failure manifest.
- [ ] Bản vá lỗi được xác nhận bằng exact replay rồi full suite.
- [ ] “Expected tests pass” không được báo là executed PASS nếu chưa chạy.
- [ ] Property-based framework có seed/shrink contract riêng được tôn trọng.

## 30. Quy trình quyết định

```text
Test không tái hiện được?
      |
      +-- Phụ thuộc "now"/ngày?
      |      -> Inject Clock; fixed/mutable boundary test.
      |
      +-- Phụ thuộc random inputs?
      |      -> Log algorithm + rootSeed + caseIndex.
      |         Derive per-case PRNG independently.
      |
      +-- Chạy song song?
      |      -> No shared mutable RNG/Clock/state.
      |         Check JUnit workers/forks/order.
      |
      +-- Spring integration context?
      |      -> @TestConfiguration/@Primary beans.
      |         Beware cached singleton PRNG state.
      |
      +-- Có DB/Redis/broker/server timestamps?
      |      -> Isolate provider fixtures/time/scheduler.
      |
      +-- Lỗi vẫn không replay với same seed?
      |      -> Inspect race/interleaving, external data,
      |         timezone/JDK/dependencies/CI settings.
      |
      +-- Đã bắt được một failing case?
             -> Copy exact Gradle replay command;
                minimize input; add regression test;
                rerun full suite.
```

**Kết luận:** `Clock` giúp điều khiển business time, `RandomGenerator` + explicit seed giúp điều khiển pseudo-random inputs, còn **derived seed per case** giúp replay một lỗi mà không phụ thuộc test scheduling. Test đáng tin không dùng một shared global Random/Clock mutable, không dựa `Thread.sleep` cho deadline và không để timezone host quyết định kết quả. Để tái hiện **toàn bộ** failure, cần thêm environment/fixture/runtime metadata; seed không thể thay thế việc kiểm soát DB, thread interleavings hoặc external provider clocks.

## 31. Tài liệu chính thức

- Java SE 17 — Clock, fixed/offset/tick/ZoneId semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java SE 17 — Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java SE 17 — LocalDate, now(Clock), ofInstant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
- Java SE 17 — java.util.Random, seeded algorithm portability and security warning: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html
- Java SE 17 — RandomGenerator interface: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html
- Java SE 17 — Random generator algorithm groups: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html
- Java SE 17 — SecureRandom: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html
- Java SE 17 — ThreadLocalRandom: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html
- Spring Boot 3.3 — Testing Spring Applications, @TestConfiguration and @Import: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-applications.html
- Spring Boot 3.3 — Test configuration and auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Framework — TestContext Framework context cache: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — TestReporter, parameter resolution, parallel execution: https://docs.junit.org/current/user-guide/
- Gradle — Testing Java & JVM projects, test --tests, JVM properties, forks: https://docs.gradle.org/current/userguide/java_testing.html
