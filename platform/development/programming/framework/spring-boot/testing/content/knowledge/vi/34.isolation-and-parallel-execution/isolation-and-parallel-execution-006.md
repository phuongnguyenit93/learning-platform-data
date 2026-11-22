# Static field, system property, locale và timezone dùng chung

Trong nhóm **Cách ly và chạy song song** của module **Spring Boot - testing**, một bài test có thể đúng khi chạy riêng nhưng thất bại khi cả suite chạy cùng lúc. Một nguyên nhân thường gặp là **trạng thái nằm ngoài phạm vi test**: `static field` có thể tồn tại tới hết JVM, `System.setProperty` thay đổi cấu hình của mọi thread cùng process, còn `Locale.setDefault` và `TimeZone.setDefault` thay đổi mặc định được nhiều thư viện đọc ngầm. Spring còn có **TestContext cache**, singleton beans và resource lifecycle riêng; tạo một test instance mới không tự reset các trạng thái đó.

Ví dụ một test đặt `Locale.setDefault(Locale.FRANCE)` để kiểm tra định dạng số; test khác mong dấu thập phân theo US. Chạy lần lượt thì có thể pass, chạy song song thì lúc nào có dấu phẩy hay dấu chấm phụ thuộc thread scheduling. Tương tự, một test đổi `System.setProperty("app.feature.enabled", "true")` nhưng quên trả lại giá trị cũ sẽ thay đổi hành vi test khác. Một `static final AtomicInteger` tuy cập nhật thread-safe vẫn **chia sẻ giá trị giữa các tests** và gây rò state.

Bài học cung cấp phương pháp theo thứ tự ưu tiên:

1. **Tránh JVM global state** bằng dependency injection: truyền `Locale`, `ZoneId` và `Clock`, tạo service/sequence theo phạm vi thích hợp, inject cấu hình thay vì gọi `System.getProperty` sâu trong business logic.
2. Nếu test **bắt buộc** thay default JVM, chụp giá trị ban đầu, thay trong scope ngắn nhất và khôi phục trong `finally` hoặc `AutoCloseable.close()`, kể cả khi assertion thất bại.
3. Khi JUnit Jupiter chạy song song, khai báo `@ResourceLock` với `Resources.SYSTEM_PROPERTIES`, `Resources.LOCALE`, `Resources.TIME_ZONE` và chế độ `READ_WRITE` hoặc `READ` cho những tests có cùng tài nguyên; dùng `@Isolated` khi cần cô lập cả test class.
4. Hiểu **giới hạn phối hợp**: JUnit resource locks chỉ điều phối những tests khai báo cùng key trong cùng JUnit engine; không điều khiển threads tự tạo, test framework khác hoặc hai JVM forks.
5. Dùng `ApplicationContextRunner.withPropertyValues`, `@SpringBootTest(properties=...)` và `@TestPropertySource` cho Spring configuration, không sửa System properties toàn cục để “giả” mỗi environment.
6. Test formatting/time calculations với `java.time` và test fixtures tường minh, tránh phụ thuộc locale/timezone của laptop hay CI.
7. Phân biệt **thread safety**, **test isolation**, **determinism** và **cleanup**: một cơ chế không tự bảo đảm ba cơ chế còn lại.

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, Gradle**. Có mã Java SE chạy bằng `javac/java` cùng **stdout chính xác**, một số unit tests JUnit và các context tests cho Spring Boot. Các đoạn anti-pattern được gắn nhãn và không được xem là hướng dẫn production.

## 1. Ma trận nơi trạng thái được lưu

| Trạng thái | Phạm vi thật | Sống bao lâu? | Rủi ro khi chạy song song |
| --- | --- | --- | --- |
| Local variable | Một invocation/thread stack | Trong method | Thấp nếu không escape dưới dạng shared object |
| Instance field của test JUnit `PER_METHOD` | Một test instance | Mỗi method instance | Có thể giữ shared object được inject/cấp ngoài |
| Static mutable field | Classloader/JVM | Tới khi class unloaded/process kết thúc | State leak; data race nếu không đồng bộ |
| `System.getProperties()` | JVM-global `Properties` | Suốt process | Test ghi property ảnh hưởng test khác |
| `Locale.getDefault()` | JVM-global default | Tới khi thay/reset/JVM kết thúc | Number/date/case/format đổi bất ngờ |
| `Locale.Category.FORMAT/DISPLAY` | JVM-global category defaults | Tới khi thay | FORMAT khác DISPLAY/general |
| `TimeZone.getDefault()` | JVM default time zone, có cache | Tới khi thay/clear cache | Timestamps và legacy date output đổi |
| `ZoneId.systemDefault()` | Đọc JVM default time zone ở thời điểm gọi | Mỗi lần gọi có thể quan sát default khác | Test phụ thuộc máy/changes |
| Spring singleton bean | Một `ApplicationContext` | Tới context close/eviction | Cache context có thể chia sẻ mutable bean |
| Spring TestContext cache | Test JVM process, theo cache key | Giữa các test classes/contexts tương thích | Class khác có thể tái sử dụng context |
| Filesystem/DB/broker | Ngoài JVM | Theo resource ownership/TTL | `@ResourceLock` không khóa external service |
| Static `ThreadLocal` | Một giá trị trên mỗi thread | Có thể sống tới thread pool reuse | Rò principal/trace/MDC vào task tiếp theo |

**Phân biệt mutable và immutable static:** `static final String NAME = "catalog"` hoặc một immutable formatter có thể chia sẻ an toàn. `static final Map<String, String> CACHE = new HashMap<>()` vẫn mutable. Từ khóa `final` chỉ ngăn tham chiếu field được gán lại, **không tự biến object bên trong thành bất biến**.

## 2. Vì sao reset ở @BeforeEach vẫn có thể không đủ?

Một anti-pattern:

```java
class FlakyCounterTest {
    private static int counter;

    @BeforeEach
    void reset() {
        counter = 0;
    }

    @Test
    void first() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void second() {
        counter++;
        assertEquals(1, counter);
    }
}
```

Đây là **snippet lỗi minh họa**, cần JUnit imports. Chạy tuần tự có thể xanh, nhưng nếu JUnit thực thi hai methods đồng thời thì `@BeforeEach` của một test có thể reset counter khi test kia đang tăng. Thậm chí nếu dùng `AtomicInteger` để loại data race ở phép tăng, **hai tests vẫn cùng dùng một counter** và phá isolation.

Cần phân biệt:

- **Thread safety:** `AtomicInteger.incrementAndGet()` atomic; hai threads không làm mất update.
- **Test isolation:** mỗi test bắt đầu với một counter riêng. AtomicInteger static **không** cung cấp điều này.
- **Determinism:** một test không phụ thuộc thứ tự ngẫu nhiên các methods hoặc threads khác.
- **Cleanup:** dữ liệu sau test được hoàn trả đúng; cleanup cần cả khi test fail.

Giải pháp ưu tiên là **không tạo static mutable state** cho business/test fixture; dùng instance hoặc scope rõ ràng. Khi phải giữ static legacy state, dùng test isolation/lock và một API reset an toàn, hiểu đây là giải pháp quá độ, không phải thiết kế lý tưởng.

## 3. JUnit mặc định tạo test instance mới, không reset JVM

JUnit Jupiter mặc định `@TestInstance(Lifecycle.PER_METHOD)`: mỗi test method có một instance mới. Tuy nhiên, nó **không tạo JVM mới** và không reload class thông thường:

```text
JUnit test JVM
  |
  +-- SomeTest instance #1 -> @Test method A
  |
  +-- SomeTest instance #2 -> @Test method B
  |
  +-- shared MyClass.staticField
  +-- shared System.properties
  +-- shared Locale.default
  +-- shared TimeZone.default
  +-- potentially cached Spring ApplicationContext
```

Dùng `@TestInstance(PER_CLASS)` làm instance fields cũng được chia sẻ giữa methods và có additional concurrency/lifecycle considerations. JUnit thường không chạy song song các methods PER_CLASS trong một class trừ khi cấu hình/annotation phù hợp; đừng lấy đó làm cơ chế lock toàn suite.

**Không coi `@BeforeEach` là rollback tự động.** Nếu code test đổi system property hoặc default locale, JUnit không tự khôi phục chúng chỉ vì test instance bị hủy. `@AfterEach` có thể restore, nhưng nếu cleanup bị bỏ do lỗi nghiêm trọng (kill process) hoặc có unmanaged async tasks, state/resource vẫn có thể khác. Scope bằng try-with-resources đặt cleanup gần điểm mutation giúp giảm rủi ro.

## 4. System property là cấu hình JVM-wide

API chính:

```java
String old = System.getProperty("lesson.feature.enabled");

try {
    System.setProperty("lesson.feature.enabled", "true");
    // Kiểm tra behavior phụ thuộc property.
} finally {
    if (old == null) {
        System.clearProperty("lesson.feature.enabled");
    } else {
        System.setProperty("lesson.feature.enabled", old);
    }
}
```

**Lưu ý:**

- `System.setProperty` **không scoped theo thread**. Mọi code trong cùng JVM đọc cùng property key sẽ thấy giá trị mới, kể cả test chạy song song.
- `System.clearProperty` chỉ đúng khi trước đó property **không tồn tại**. Nếu property ban đầu có giá trị "false", cleanup phải trả lại "false" chứ không xóa.
- `System.setProperties(new Properties())` thay **toàn bộ** hệ property JVM và dễ xóa properties thiết yếu của Java/Spring/Gradle; không làm vậy để reset một key.
- System properties là một property source trong Spring `Environment`, nhưng điều kiện bean/constructor-bound configuration thường được evaluate lúc tạo context. Đổi property **sau** khi Spring context refresh không tự tạo bean mới hay rebind tất cả properties.
- Test muốn thay `user.timezone` không nên chỉ set property và giả định mọi date/time API đang dùng timezone mới: `TimeZone` có cache của riêng nó.

**An toàn hơn:** đưa property vào một `ApplicationContextRunner.withPropertyValues(...)` hoặc `@SpringBootTest(properties=...)`, không sửa toàn JVM.

## 5. Locale: general default và hai Category defaults

Java 17 có:

```java
Locale general = Locale.getDefault();

Locale display =
        Locale.getDefault(Locale.Category.DISPLAY);

Locale format =
        Locale.getDefault(Locale.Category.FORMAT);
```

- **General default**: `Locale.getDefault()`, nhiều API sử dụng khi không chỉ định.
- **DISPLAY**: locale mặc định dùng cho hiển thị tên ngôn ngữ/quốc gia và các trường hợp localization.
- **FORMAT**: locale dùng trong định dạng số/ngày/thời gian theo category.
- `Locale.setDefault(Locale.US)` đặt default chung và có ảnh hưởng đến các category defaults; nếu đã có overrides riêng, cần snapshot **cả ba** rồi khôi phục đúng thứ tự.
- `Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE)` thay category FORMAT, không có nghĩa general/display default cũng trở thành FR.
- Thay `System.setProperty("user.language", "vi")` **sau khi JVM đã khởi tạo default Locale** không tự cập nhật object Locale mặc định; phải hiểu khởi tạo/caching hoặc gọi `Locale.setDefault`. Tốt nhất không dựa vào default trong business logic.

**Bẫy format:**

```java
NumberFormat.getNumberInstance()
```

dùng một default locale; trên hai máy khác nhau separator có thể khác. Test không nên assert một string được format theo defaults của máy. Hãy dùng:

```java
NumberFormat.getNumberInstance(
        Locale.forLanguageTag("vi-VN"))
```

nếu ý định là format cho người dùng Việt Nam. Format phụ thuộc CLDR/JDK locale data vẫn có thể thay đổi chi tiết theo version, nên với snapshot tests hãy quyết định rõ contract và version policy.

**Case conversion:** `someText.toLowerCase()` có thể dùng default locale; với identifiers/protocol keys, thường dùng `toLowerCase(Locale.ROOT)` hoặc `equalsIgnoreCase` theo contract. Không dùng default locale để chuẩn hóa API key/slug mà không định nghĩa locale.

## 6. TimeZone.default, user.timezone và ZoneId

Java 17 có hai tầng dễ lẫn:

```java
String property = System.getProperty("user.timezone");
TimeZone zone = TimeZone.getDefault();
ZoneId zoneId = ZoneId.systemDefault();
```

- `user.timezone` là system property. JVM dùng nó khi tính default time zone nếu chưa có default cached hoặc đã được clear; nó không phải source-of-truth luôn được đọc lại mỗi lúc.
- `TimeZone.getDefault()` trả clone của default `TimeZone` đang cached; có thể thiết lập cached default bằng `TimeZone.setDefault(...)`.
- `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` thay JVM default time zone, **không tự thay property `user.timezone`**.
- Thay `System.setProperty("user.timezone", "Asia/Tokyo")` **không bảo đảm** `TimeZone.getDefault()` đổi ngay khi cached default còn tồn tại.
- `TimeZone.setDefault(null)` clear cached default khiến lần hỏi sau có thể tính lại từ system property/môi trường; việc này là **global mutation**, không nên dùng vô tội vạ trong test suite.
- `ZoneId.systemDefault()` lấy JVM default time zone lúc được gọi; một `ZoneId` được lưu trước đó không tự thay nội dung.
- `TimeZone.getTimeZone("Wrong/Zone")` có thể âm thầm fallback sang GMT; `ZoneId.of("Wrong/Zone")` ném exception, hữu ích khi muốn validate config nghiêm ngặt.

**Ưu tiên trong app:**

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime local = instant.atZone(zone);
```

Khi biểu diễn instant cho user/tenant, zone nên đến từ cấu hình hoặc profile dữ liệu, không từ máy CI. Nếu cần “bây giờ”, inject `Clock`; đừng gọi `Instant.now()` ở sâu trong code rồi giả định test có thể đóng băng thời gian.

## 7. Lịch DST và lý do không hardcode offset

`Asia/Ho_Chi_Minh` thường là UTC+07 theo thời điểm hiện đại của ví dụ, nhưng **ZoneId** là bộ quy tắc time zone theo thời gian, không chỉ một offset bất biến. Những vùng như `Europe/Berlin` có Daylight Saving Time (DST), nên chuyển giờ có thể xuất hiện local time mơ hồ hoặc không tồn tại.

- `Instant` biểu diễn thời điểm tuyệt đối; `LocalDateTime` **không chứa zone/offset**, không thể tự chuyển thành một instant đúng nếu chưa có policy cho zone/DST overlap/gap.
- `OffsetDateTime` chứa UTC offset cụ thể; `ZonedDateTime` có zone rules.
- `Clock.fixed(instant, zone)` tốt cho test “bây giờ”; `DateTimeFormatter.withZone(zone)` tốt cho deterministic formatting.
- Nếu yêu cầu xử lý DST, test **các thời điểm trước/sau transition** với `ZoneId` cụ thể và zone rules của JDK version. Không assert mọi ngày đều có đúng 24 giờ địa phương.
- Không dùng `TimeZone.getDefault()` để tính deadline tài chính hoặc scheduler theo một máy chạy CI tùy ý.

## 8. Nguyên tắc chuyển từ global state sang injection

Từ một thiết kế dễ test fail:

```java
public String createdAtLabel() {
    return LocalDateTime.now().toString()
            + " " + Locale.getDefault();
}
```

đến thiết kế có phụ thuộc tường minh:

```java
public final class TimestampLabel {
    private final Clock clock;
    private final ZoneId zone;
    private final Locale locale;

    public TimestampLabel(
            Clock clock, ZoneId zone, Locale locale) {
        this.clock = clock;
        this.zone = zone;
        this.locale = locale;
    }

    public String value() {
        ZonedDateTime value =
                ZonedDateTime.ofInstant(
                        clock.instant(), zone);
        return value.getYear() + "-"
                + value.getMonthValue() + " ["
                + locale.toLanguageTag() + "]";
    }
}
```

Đoạn trên là **snippet đầy đủ phần class** nhưng cần imports từ `java.time`/`java.util`. Bộ ví dụ hoàn chỉnh dưới đây đưa vào các files có package/imports và JUnit tests.

**Ý nghĩa:** test tự tạo `Clock.fixed(...)`, `ZoneId.of(...)` và `Locale.forLanguageTag(...)` mà không sửa globals. Hai test có thể chạy song song vì mỗi instance có các phụ thuộc riêng, miễn các collaborator không giữ mutable state khác.

## 9. Cấu trúc source và build.gradle

Cấu trúc một module Spring Boot Java 17:

```text
src/
├── main/java/example/isolation/
│   ├── IsolationApplication.java
│   ├── ReportSettings.java
│   ├── ReportConfiguration.java
│   ├── InvoicePrinter.java
│   ├── ReportStamp.java
│   ├── SequenceCounter.java
│   └── DefaultsDemo.java
├── test/java/example/isolation/
│   ├── InvoicePrinterTest.java
│   ├── SequenceCounterTest.java
│   ├── JvmDefaultsScope.java
│   ├── JvmSharedDefaultsTest.java
│   ├── ReportConfigurationRunnerTest.java
│   └── ReportContextTest.java
└── test/resources/
    └── junit-platform.properties
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
}
```

Dùng Spring Boot 3.5.x, JUnit Jupiter 5.x từ BOM của Boot và Java 17+. Plugin Gradle chỉ là lựa chọn demo; nếu dự án đã có Spring Boot plugin/BOM, dùng dependency versions thống nhất. Bộ tests không cần server, database, Docker hoặc account cloud. Các lệnh `./gradlew` yêu cầu Gradle wrapper tương thích đã tồn tại (file `build.gradle` không tự tạo wrapper).

**Không có cấu hình System properties toàn cục trong build file** để “ép” tất cả tests theo timezone một cách bí mật. Khi ứng dụng có policy UTC, nên cấu hình rõ, và kiểm thử những nơi phải hỗ trợ nhiều zones.

## 10. InvoicePrinter.java: locale/zone tường minh

Tạo `src/main/java/example/isolation/InvoicePrinter.java`:

```java
package example.isolation;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class InvoicePrinter {
    private final Locale locale;
    private final DateTimeFormatter formatter;

    public InvoicePrinter(Locale locale, ZoneId zone) {
        this.locale = locale;
        this.formatter = DateTimeFormatter
                .ofPattern("yyyy-MM-dd HH:mm XXX", locale)
                .withZone(zone);
    }

    public String render(Instant instant) {
        return formatter.format(instant)
                + " [" + locale.toLanguageTag() + "]";
    }
}
```

`DateTimeFormatter` bất biến và thread-safe; mỗi printer giữ một formatter được tạo với **Locale + ZoneId** rõ ràng. Nó không hỏi `Locale.getDefault()` hay `ZoneId.systemDefault()` lúc render, nên format không bị đổi bởi test khác sửa JVM globals.

**Ý nghĩa output:**

- Với instant `2024-02-29T17:00:00Z`, UTC biểu diễn `2024-02-29 17:00 Z`.
- Với `Asia/Ho_Chi_Minh`, cùng instant đó thành `2024-03-01 00:00 +07:00`.
- Dòng đính kèm `[en-US]` hoặc `[vi-VN]` là mã locale của instance, không phải system locale.
- Dùng date pattern số để stdout ổn định; các tên tháng/ngày tiếng bản địa trong CLDR có thể thay đổi giữa JDK/locale-provider versions nếu đó không phải phần hợp đồng cần khóa.

**Đừng thay thế bằng** `static SimpleDateFormat`: `SimpleDateFormat` mutable và không thread-safe; không phù hợp để chia sẻ qua nhiều threads. `DateTimeFormatter` là lựa chọn tốt cho Java 17.

## 11. Clock được inject để test thời điểm hiện tại

Tạo `src/main/java/example/isolation/ReportStamp.java`:

```java
package example.isolation;

import java.time.Clock;

public final class ReportStamp {
    private final Clock clock;
    private final InvoicePrinter printer;

    public ReportStamp(Clock clock, InvoicePrinter printer) {
        this.clock = clock;
        this.printer = printer;
    }

    public String nowLabel() {
        return printer.render(clock.instant());
    }
}
```

Production có thể tạo `Clock.systemUTC()` trong Spring configuration nếu cần. Test dùng `Clock.fixed(Instant.parse(...), ZoneOffset.UTC)`, không dùng sleep hoặc sửa system clock/timezone. Khi truyền cùng fixed instant, kết quả luôn như nhau dù JUnit chạy trên máy có default timezone khác.

## 12. SequenceCounter.java: thay static mutable bằng instance

Tạo `src/main/java/example/isolation/SequenceCounter.java`:

```java
package example.isolation;

import java.util.concurrent.atomic.AtomicInteger;

public final class SequenceCounter {
    private final AtomicInteger next = new AtomicInteger();

    public int next() {
        return next.incrementAndGet();
    }
}
```

Đây là counter thread-safe **trong một instance**, nhưng mỗi instance có state riêng. JUnit tạo một counter mới trong từng test, tránh static reset. Nếu production cần **global sequence cross-process**, AtomicInteger không đủ: dùng database sequence/ID generator và contract riêng.

Một anti-pattern cần tránh:

```java
public final class LeakySequence {
    private static final AtomicInteger NEXT =
            new AtomicInteger();

    public static int next() {
        return NEXT.incrementAndGet();
    }
}
```

Code này thread-safe về increment nhưng **không isolated giữa các tests**. Đừng thêm một `reset()` để test rồi chạy song song mà không coordination; tốt hơn thay thiết kế bằng instance hoặc inject một `SequenceCounter` có scope/lifecycle xác định.

## 13. ReportSettings và ReportConfiguration: binding không đụng globals

Tạo `src/main/java/example/isolation/ReportSettings.java`:

```java
package example.isolation;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportSettings(
        @DefaultValue("en-US") String localeTag,
        @DefaultValue("UTC") String zoneId) {
}
```

Tạo `src/main/java/example/isolation/ReportConfiguration.java`:

```java
package example.isolation;

import java.time.Clock;
import java.time.ZoneId;
import java.util.Locale;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportSettings.class)
public class ReportConfiguration {

    @Bean
    InvoicePrinter invoicePrinter(ReportSettings settings) {
        Locale locale =
                Locale.forLanguageTag(settings.localeTag());
        if (locale.getLanguage().isBlank()) {
            throw new IllegalArgumentException(
                    "invalid report locale");
        }

        ZoneId zone = ZoneId.of(settings.zoneId());
        return new InvoicePrinter(locale, zone);
    }

    @Bean
    Clock reportClock() {
        return Clock.systemUTC();
    }

    @Bean
    ReportStamp reportStamp(
            Clock reportClock, InvoicePrinter invoicePrinter) {
        return new ReportStamp(reportClock, invoicePrinter);
    }

    @Bean
    SequenceCounter sequenceCounter() {
        return new SequenceCounter();
    }
}
```

**Điểm cần hiểu:**

- Spring Boot binder đọc các values `app.report.locale-tag`/`app.report.zone-id` và tạo `ReportSettings`.
- Factory tạo `Locale` và `ZoneId` rõ ràng. Không gọi `Locale.setDefault` hoặc `TimeZone.setDefault`.
- `ZoneId.of("Wrong/Zone")` làm bean construction fail; tốt hơn âm thầm fallback GMT khi cấu hình sai.
- `Clock.systemUTC()` là production clock; unit tests có thể tự tạo `ReportStamp(Clock.fixed(...), ...)`. Đổi system timezone không ảnh hưởng việc lấy Instant từ Clock.systemUTC.
- `SequenceCounter` là singleton trong một Spring context theo default scope. Nó **không static**, nhưng nếu hai test classes dùng cùng cached Spring context thì vẫn có thể chia sẻ **cùng singleton counter**. Nếu cần per-test counter, tạo instance trực tiếp trong unit tests hoặc điều chỉnh bean scope/context lifecycle hợp đồng, không mặc định mỗi test class có một Spring singleton mới.

Tạo `src/main/java/example/isolation/IsolationApplication.java`:

```java
package example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                IsolationApplication.class, args);
    }
}
```

Spring Boot component scanning phát hiện `ReportConfiguration` trong cùng package. Bộ demo không dùng web dependencies; test với `@SpringBootTest(webEnvironment=NONE)` vẫn kiểm tra wiring thật.

## 14. InvoicePrinterTest.java: ba deterministic unit tests

Tạo `src/test/java/example/isolation/InvoicePrinterTest.java`:

```java
package example.isolation;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Locale;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InvoicePrinterTest {
    private static final Instant FIXED =
            Instant.parse("2024-02-29T17:00:00Z");

    @Test
    void utcUsesExplicitZone() {
        InvoicePrinter printer = new InvoicePrinter(
                Locale.US, ZoneOffset.UTC);

        assertEquals(
                "2024-02-29 17:00 Z [en-US]",
                printer.render(FIXED));
    }

    @Test
    void vietnamZoneDoesNotDependOnHostTimeZone() {
        InvoicePrinter printer = new InvoicePrinter(
                Locale.forLanguageTag("vi-VN"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                "2024-03-01 00:00 +07:00 [vi-VN]",
                printer.render(FIXED));
    }

    @Test
    void fixedClockMakesNowLabelDeterministic() {
        Clock clock = Clock.fixed(
                FIXED, ZoneOffset.UTC);

        ReportStamp stamp = new ReportStamp(
                clock,
                new InvoicePrinter(
                        Locale.US, ZoneOffset.UTC));

        assertEquals(
                "2024-02-29 17:00 Z [en-US]",
                stamp.nowLabel());
    }
}
```

**Ba methods**, không có `System.setProperty`, `Locale.setDefault`, `TimeZone.setDefault` hoặc `Thread.sleep`. Những tests này an toàn khi chạy song song với nhau vì chỉ dùng bất biến và các objects riêng.

Cách kiểm tra tốt không phải ép máy chạy `TZ=UTC` rồi nghĩ business hỗ trợ mọi timezone, mà là inject zone của case trực tiếp và kiểm tra output mong đợi theo instant cụ thể.

## 15. SequenceCounterTest.java: test isolation thực sự

Tạo `src/test/java/example/isolation/SequenceCounterTest.java`:

```java
package example.isolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SequenceCounterTest {

    @Test
    void firstTestGetsFreshSequence() {
        SequenceCounter counter = new SequenceCounter();

        assertEquals(1, counter.next());
        assertEquals(2, counter.next());
    }

    @Test
    void secondTestAlsoGetsFreshSequence() {
        SequenceCounter counter = new SequenceCounter();

        assertEquals(1, counter.next());
    }

    @Test
    void twoInstancesDoNotShareCounter() {
        SequenceCounter first = new SequenceCounter();
        SequenceCounter second = new SequenceCounter();

        assertEquals(1, first.next());
        assertEquals(1, second.next());
        assertEquals(2, first.next());
        assertEquals(2, second.next());
    }
}
```

**Ba methods**, không phụ thuộc JUnit method order. Chỉ một `AtomicInteger` thuộc từng instance, do đó concurrency **và** isolation đều đúng trong phạm vi class.

**Không chứng minh:** counter tạo ID duy nhất giữa các Spring instances, JVM processes hoặc cluster nodes. Nếu nghiệp vụ đòi unique IDs toàn hệ thống, cần contract với DB sequence/UUID/ULID hoặc distributed generator, không giải bằng static counter.

## 16. Khi phải đổi JVM globals: helper snapshot/restore

Một số legacy APIs chỉ đọc default Locale/TimeZone hoặc System properties nên test cần mutation có kiểm soát. Tạo helper **test-only** để snapshot đúng trạng thái và hoàn trả trong mọi đường thoát.

Tạo `src/test/java/example/isolation/JvmDefaultsScope.java`:

```java
package example.isolation;

import java.util.Locale;
import java.util.TimeZone;

final class JvmDefaultsScope implements AutoCloseable {
    private final String key;
    private final String oldKeyValue;
    private final String oldTimezoneProperty;
    private final Locale oldGeneral;
    private final Locale oldDisplay;
    private final Locale oldFormat;
    private final TimeZone oldZone;

    JvmDefaultsScope(String key) {
        this.key = key;
        this.oldKeyValue = System.getProperty(key);

        // Chụp property trước getDefault(): JDK có thể
        // khởi tạo default zone và điền user.timezone.
        this.oldTimezoneProperty =
                System.getProperty("user.timezone");

        this.oldGeneral = Locale.getDefault();
        this.oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        this.oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        this.oldZone = TimeZone.getDefault();
    }

    private static void restore(
            String property, String previous) {
        if (previous == null) {
            System.clearProperty(property);
        } else {
            System.setProperty(property, previous);
        }
    }

    @Override
    public void close() {
        try {
            restore(key, oldKeyValue);
        } finally {
            try {
                // setDefault(Locale) có thể ảnh hưởng cả
                // FORMAT/DISPLAY, nên phục hồi các category sau.
                Locale.setDefault(oldGeneral);
                Locale.setDefault(
                        Locale.Category.DISPLAY, oldDisplay);
                Locale.setDefault(
                        Locale.Category.FORMAT, oldFormat);
            } finally {
                try {
                    TimeZone.setDefault(oldZone);
                } finally {
                    restore(
                            "user.timezone", oldTimezoneProperty);
                }
            }
        }
    }
}
```

**Giải thích helper:**

1. Snapshot giá trị **của đúng property key** được test thay đổi, phân biệt **missing** với chuỗi "false".
2. Snapshot nguyên vẹn general Locale, DISPLAY Locale và FORMAT Locale; không giả định chúng luôn giống nhau.
3. Snapshot `user.timezone` trước `TimeZone.getDefault()` vì việc khởi tạo default zone có thể cập nhật property đó.
4. Snapshot `TimeZone.getDefault()` và restore bằng `TimeZone.setDefault(oldZone)`.
5. Mỗi block cleanup dùng `finally`, nên failure của bước trước không tự bỏ qua toàn bộ bước sau.
6. Helper không gọi `System.setProperties(...)` và không biến toàn bộ JVM property map thành một clone khác.
7. Helper này **không tạo sự cô lập thực sự giữa threads**. Nếu một test khác đọc cùng global trong lúc scope mở mà không khai báo lock, nó vẫn có thể thấy trạng thái tạm. Cần phối hợp JUnit locks hoặc process isolation.

**Cảnh báo:** nếu chính application có background worker đang đọc locale/timezone hoặc có test runner không hợp tác, snapshot/restore không giúp loại race trong khoảng giữa. Vì vậy phương án tốt nhất vẫn là **không mutate globals**.

## 17. JUnit @ResourceLock: phối hợp tài nguyên JVM-wide

JUnit Jupiter định nghĩa `@ResourceLock` và các constants trong `org.junit.jupiter.api.parallel.Resources`:

- `Resources.SYSTEM_PROPERTIES` cho Java System properties.
- `Resources.SYSTEM_OUT` và `Resources.SYSTEM_ERR` cho standard output/error streams bị thay đổi.
- `Resources.LOCALE` cho default locale.
- `Resources.TIME_ZONE` cho default time zone.
- `ResourceAccessMode.READ_WRITE`: loại trừ test khác khai báo READ hoặc READ_WRITE cùng key.
- `ResourceAccessMode.READ`: cho phép nhiều readers chạy song song, nhưng không chạy cùng writer cùng key.

**Đây là advisory coordination giữa các JUnit tests khai báo cùng key.** Test writer quên lock hoặc thread do test tạo tự truy cập globals có thể phá tính cô lập. Khi test đọc default Locale mà cần giá trị ổn định, nó cũng phải khai báo READ với cùng resource key; không chỉ writer khai báo READ_WRITE.

### JvmSharedDefaultsTest.java: ba cases ghi có cleanup

Tạo `src/test/java/example/isolation/JvmSharedDefaultsTest.java`:

```java
package example.isolation;

import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
@ResourceLock(
        value = Resources.LOCALE,
        mode = ResourceAccessMode.READ_WRITE)
@ResourceLock(
        value = Resources.TIME_ZONE,
        mode = ResourceAccessMode.READ_WRITE)
class JvmSharedDefaultsTest {
    private static final String KEY =
            "lesson.feature.enabled";

    @Test
    void systemPropertyIsRestoredByScope() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            System.setProperty(KEY, "true");

            assertEquals("true",
                    System.getProperty(KEY));
        }
    }

    @Test
    void localeFormatCategoryCanDifferFromGeneral() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.FRANCE);

            assertEquals(Locale.US, Locale.getDefault());
            assertEquals(
                    Locale.FRANCE,
                    Locale.getDefault(
                            Locale.Category.FORMAT));
            assertEquals(
                    Locale.US,
                    Locale.getDefault(
                            Locale.Category.DISPLAY));
        }
    }

    @Test
    void cachedTimezoneNeedNotFollowUserTimezoneProperty() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            TimeZone.setDefault(
                    TimeZone.getTimeZone("UTC"));

            System.setProperty(
                    "user.timezone", "Asia/Tokyo");

            // TimeZone cache được đặt rõ; property khác
            // không tự thay cached default trong JDK17.
            assertEquals("UTC",
                    ZoneId.systemDefault().getId());
            assertEquals(
                    "Asia/Tokyo",
                    System.getProperty("user.timezone"));
        }
    }
}
```

**Ba JUnit methods** sử dụng class-level resource locks. Khi JUnit chạy song song với những tests khác **cũng khai báo same locks**, không có writers/readers xung đột trong lúc callback/lifecycle của class giữ lock. `try-with-resources` gọi `JvmDefaultsScope.close()` ngay cả khi assertion ném lỗi.

**Không có assertion sau scope để so sánh với mặc định của một máy cụ thể**; scope restore theo snapshot, không cố gắng ép JUnit process về English/UTC vĩnh viễn. Nếu cần assert restore, chụp snapshots và kiểm tra trong cùng locked test, tránh tác động của test khác chưa hợp tác.

**Không dùng test này làm template để sửa default JVM trong mỗi test**. Nó minh họa cách kiểm tra legacy behavior, còn `InvoicePrinterTest` là mẫu thiết kế nên dùng mặc định.

## 18. @Isolated và @Execution: đọc đúng phạm vi bảo vệ

JUnit Jupiter có:

```java
@Isolated
class LegacyGlobalIntegrationTest {
    // Các @Test tác động nhiều resource toàn JVM.
}
```

Đây là **snippet**, cần import `org.junit.jupiter.api.parallel.Isolated`. `@Isolated` phù hợp khi một class test legacy liên quan nhiều global resources khó liệt kê, cần không chạy xen cùng các tests khác trong cùng JUnit Jupiter execution. Nhưng nó **không dừng** background threads đã được khởi động, không khóa JVM của Gradle fork khác và không bảo vệ database/file resource dùng ngoài process.

`@Execution(ExecutionMode.SAME_THREAD)` có thể ép các methods trong class chạy cùng thread/tuần tự theo cấu hình JUnit; tuy nhiên nó **không tự ngăn classes khác** chạy song song và sửa `System.properties`, `Locale` hay `TimeZone`. Đối với tài nguyên dùng chung, chọn `@ResourceLock`/`@Isolated` đúng mục tiêu.

**@TestInstance(PER_CLASS)** không thay thế `@ResourceLock`. Nó chỉ điều khiển vòng đời test instance, không tạo một lock trên toàn JVM-global state.

### ResourceLock trên một method

Nếu chỉ một method mutate system property, có thể scope lock tại method:

```java
@Test
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
void changesJvmPropertyTemporarily() {
    String old = System.getProperty("app.mode");

    try {
        System.setProperty("app.mode", "safe");
        assertEquals("safe",
                System.getProperty("app.mode"));
    } finally {
        if (old == null) {
            System.clearProperty("app.mode");
        } else {
            System.setProperty("app.mode", old);
        }
    }
}
```

Đây là **snippet** cần JUnit imports và test class. JUnit locks cũng bảo vệ lifecycle methods liên quan theo Jupiter contract. Khi nhiều tests **chỉ đọc** property, có thể dùng `mode=READ` để chúng chạy cùng nhau nhưng tránh writer. Đừng dùng một custom key cho writer và `Resources.SYSTEM_PROPERTIES` cho reader: **keys khác nhau không phối hợp**.

## 19. junit-platform.properties: bật parallel có chủ đích

Tạo `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

Với JUnit Jupiter, parallelism có thể bật qua configuration. Mode default concurrent làm tăng khả năng phát hiện các tests không cô lập. Nhưng chạy song song không bảo đảm một interleaving cụ thể và **không chứng minh code business không có race** chỉ bằng pass một lần.

**Những điều cần để mắt:**

- `@ResourceLock` là cơ chế Jupiter scheduler, có ý nghĩa khi chạy tests trong engine có nhận lock declarations. Nó không khóa toàn bộ process.
- Gradle `maxParallelForks > 1` có thể khởi chạy **nhiều JVM processes**. Mỗi process có System properties/Locale/TimeZone riêng nhưng JUnit locks **không được chia sẻ qua JVM**. File, shared database hoặc broker vẫn có thể tranh chấp.
- `forkEvery` hoặc một fork riêng giúp loại JVM-global state leak giữa nhóm tests, nhưng startup tốn thời gian và **không thay cleanup external resources**.
- Classes có `@TestInstance(PER_CLASS)`, method ordering hoặc các semantics đặc biệt có thể ảnh hưởng execution mode; đọc JUnit guide thay vì giả định toàn bộ methods sẽ chạy concurrent.
- Chạy `--tests ...` trong Gradle chỉ filter test classes, không tự thay property/locale/timezone.
- Tests sử dụng `System.out`/`System.err` replacement cần `Resources.SYSTEM_OUT`/`SYSTEM_ERR` riêng.

## 20. Spring Boot: dùng config properties thay System.setProperty

Đối với test một cấu hình Spring, cách **không nên**:

```java
@BeforeAll
static void turnOn() {
    System.setProperty("app.report.zone-id", "UTC");
}
```

Đây là anti-pattern vì JVM-global property có thể ảnh hưởng test khác và Spring context có thể đã được cache trước khi đổi.

**Đối với một full Spring Boot integration test**, khai báo:

```java
@SpringBootTest(
        properties = {
                "app.report.locale-tag=vi-VN",
                "app.report.zone-id=Asia/Ho_Chi_Minh"
        })
class ReportContextTest {
    // Assert bean được cấu hình theo test properties.
}
```

Đây là snippet; file runnable kế tiếp có import/class tương ứng. Test properties được Spring TestContext đưa vào context environment theo lifecycle của test, **không cần đổi JVM default locale/timezone**.

**Đối với ma trận** (nhiều configurations), `ApplicationContextRunner` thường nhanh và dễ cô lập hơn nhiều `@SpringBootTest` classes. Nó dựng/đóng context cho từng `run()`. Khi cần Testcontainers dynamic ports, `@DynamicPropertySource` phù hợp cho Spring TestContext; không dùng nó để sửa `TimeZone.setDefault` hay các JVM globals khác.

**Property resolution không giống global mutation:** một `Environment` của context có thể override system property bằng test property source. Tuy nhiên, code tự gọi `System.getProperty("app.report.zone-id")` ở sâu trong service sẽ **bỏ qua Spring Environment override**. Vì vậy business nên inject `ReportSettings`, không đọc System property trực tiếp.

## 21. ReportConfigurationRunnerTest.java: bốn tests context riêng

Tạo `src/test/java/example/isolation/ReportConfigurationRunnerTest.java`:

```java
package example.isolation;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class ReportConfigurationRunnerTest {
    private static final Instant FIXED =
            Instant.parse("2024-02-29T17:00:00Z");

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ReportConfiguration.class);

    @Test
    void defaultsUseUtcAndEnglishWithoutJVMDefaults() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(
                    "2024-02-29 17:00 Z [en-US]",
                    context.getBean(
                            InvoicePrinter.class)
                            .render(FIXED));
        });
    }

    @Test
    void customPropertiesBindLocaleAndZone() {
        runner.withPropertyValues(
                        "app.report.locale-tag=vi-VN",
                        "app.report.zone-id=Asia/Ho_Chi_Minh")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "2024-03-01 00:00 +07:00 [vi-VN]",
                            context.getBean(
                                    InvoicePrinter.class)
                                    .render(FIXED));
                });
    }

    @Test
    void derivedRunnerDoesNotMutateBaseline() {
        runner.withPropertyValues(
                        "app.report.zone-id=Asia/Ho_Chi_Minh")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "2024-03-01 00:00 +07:00 [en-US]",
                            context.getBean(
                                    InvoicePrinter.class)
                                    .render(FIXED));
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(
                    "2024-02-29 17:00 Z [en-US]",
                    context.getBean(
                            InvoicePrinter.class)
                            .render(FIXED));
        });
    }

    @Test
    void invalidZoneFailsFastInsteadOfSilentGmt() {
        runner.withPropertyValues(
                        "app.report.zone-id=Wrong/Zone")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                });
    }
}
```

**Bốn JUnit methods**. Mỗi `run(context -> ...)` tạo một context mới rồi đóng. Baseline runner không bị sửa bởi lần gọi `withPropertyValues`; test "derived runner" chạy cả override và baseline để chứng minh không rò property giữa scenarios.

Không dùng `Locale.setDefault`, `System.setProperty` hay `TimeZone.setDefault`. Đây là cách tốt nhất để test Spring configuration song song. Nó không khẳng định full production app đã được khởi động; chỉ kiểm tra cấu hình và bean graph được runner cung cấp.

## 22. ReportContextTest.java: full Spring context với test properties

Tạo `src/test/java/example/isolation/ReportContextTest.java`:

```java
package example.isolation;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = IsolationApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "app.report.locale-tag=vi-VN",
                "app.report.zone-id=Asia/Ho_Chi_Minh"
        })
class ReportContextTest {

    @Autowired
    InvoicePrinter printer;

    @Test
    void springTestPropertiesConfigurePrinter() {
        assertEquals(
                "2024-03-01 00:00 +07:00 [vi-VN]",
                printer.render(
                        Instant.parse("2024-02-29T17:00:00Z")));
    }
}
```

**Một JUnit method** tạo Spring Boot test context và inject bean thật. Test không thay global defaults. Nếu project production dùng thêm MVC/data/security configurations, full context có thể phát hiện wiring khác, nhưng bài này chỉ có các beans phục vụ formatting.

**Context cache caveat:** khi một class khác dùng Spring test config tương đương, Spring có thể tái sử dụng ApplicationContext (và các singleton beans bên trong). Nếu một test sửa singleton mutable state, method/class khác có thể thấy thay đổi. `@DirtiesContext` làm Spring loại/đóng context đã dirty, **nhưng không khôi phục System properties hoặc JVM default Locale/TimeZone**. Không lạm dụng nó như “xóa hết trạng thái” khi rò state nằm ngoài Spring.

## 23. DefaultsDemo.java: Java 17 chạy được và stdout chính xác

Tạo `src/main/java/example/isolation/DefaultsDemo.java`:

```java
package example.isolation;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Locale;

public class DefaultsDemo {
    public static void main(String[] args) {
        Instant fixed =
                Instant.parse("2024-02-29T17:00:00Z");

        InvoicePrinter vietnam =
                new InvoicePrinter(
                        Locale.forLanguageTag("vi-VN"),
                        ZoneId.of("Asia/Ho_Chi_Minh"));

        InvoicePrinter utc =
                new InvoicePrinter(
                        Locale.US, ZoneOffset.UTC);

        System.out.println(vietnam.render(fixed));
        System.out.println(utc.render(fixed));

        SequenceCounter counter =
                new SequenceCounter();

        System.out.println(
                "seq=" + counter.next() + ","
                        + counter.next());
    }
}
```

Dùng **JDK 17+** trong project root, không cần Gradle/Spring:

```bash
javac -d out src/main/java/example/isolation/InvoicePrinter.java src/main/java/example/isolation/SequenceCounter.java src/main/java/example/isolation/DefaultsDemo.java
java -cp out example.isolation.DefaultsDemo
```

Stdout **chính xác** với timezone database của Java 17 hỗ trợ Asia/Ho_Chi_Minh:

```text
2024-03-01 00:00 +07:00 [vi-VN]
2024-02-29 17:00 Z [en-US]
seq=1,2
```

**Vì sao deterministic?** Không đọc global locale/timezone hoặc wall clock, không tạo worker threads có thứ tự in ngẫu nhiên. Instant cố định, zone/locale được cấp rõ, counter là một instance local. Lệnh `javac` chỉ dùng các Java SE files; các Spring Boot classes không nằm trong lệnh nên không cần dependencies.

## 24. Tổng hợp 14 JUnit tests và cách chạy

| Test class | Methods | Phạm vi |
| --- | ---: | --- |
| `InvoicePrinterTest` | 3 | Locale/zone/Clock tường minh, không globals |
| `SequenceCounterTest` | 3 | Counter isolation, no static state |
| `JvmSharedDefaultsTest` | 3 | System property, locale category, cached timezone, ResourceLocks |
| `ReportConfigurationRunnerTest` | 4 | Spring property binding và context isolation |
| `ReportContextTest` | 1 | SpringBootTest wiring thực |
| **Tổng** | **14** | |

Chạy từng class với Gradle wrapper:

```bash
./gradlew test --tests example.isolation.InvoicePrinterTest
./gradlew test --tests example.isolation.SequenceCounterTest
./gradlew test --tests example.isolation.JvmSharedDefaultsTest
./gradlew test --tests example.isolation.ReportConfigurationRunnerTest
./gradlew test --tests example.isolation.ReportContextTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.isolation.InvoicePrinterTest"
.\gradlew.bat test --tests "example.isolation.SequenceCounterTest"
.\gradlew.bat test --tests "example.isolation.JvmSharedDefaultsTest"
.\gradlew.bat test --tests "example.isolation.ReportConfigurationRunnerTest"
.\gradlew.bat test --tests "example.isolation.ReportContextTest"
```

**14 là số methods trong mã nguồn ví dụ**, không phải bằng chứng đã chạy JUnit trong máy của người học. Gradle/JUnit console output phụ thuộc version/runner. Chỉ demo Java SE mục 23 có stdout xác định. Nếu chạy cả suite với parallel mode, những tests làm thay đổi globals cần lock hợp tác; tests còn lại dùng injection để giảm tranh chấp.

## 25. Spring TestContext cache và global state là hai vấn đề khác nhau

Một tình huống:

```text
TestClass A:
  @SpringBootTest(properties="app.report.zone-id=UTC")
  -> cached context #1

TestClass B:
  same merged configuration
  -> có thể reuse context #1, cùng singleton beans

TestClass C:
  @SpringBootTest(properties="app.report.zone-id=Asia/Ho_Chi_Minh")
  -> khác context cache key, thường context riêng

Unrelated JUnit test:
  TimeZone.setDefault(UTC)
  -> ảnh hưởng default JVM của mọi context đang tồn tại
     nếu bean/call đọc TimeZone.getDefault() lúc runtime
```

**Hệ quả:**

- `@SpringBootTest(properties=...)` là property source/context config. Nó không thay `user.timezone` JVM-wide hoặc `Locale.getDefault()` theo cơ chế của app trừ khi code ứng dụng tự làm.
- Context cache key có nhiều thành phần (class/config/profile/property/context customizers...), không chỉ properties; không cần dự đoán toàn bộ thuật toán cache để thiết kế test.
- Bean singleton có mutable cache/list/shared state nên có thể leak giữa test classes dùng chung context.
- `@DirtiesContext` chỉ đánh dấu context của TestContext framework là dirty để recreate khi cần; không “reset” static fields/System properties/locale/timezone.
- Trong một test-managed `@Transactional`, rollback DB thường gắn transaction vào thread của test; không quay lại static/Locale/Timezone và không tự rollback một `@Async` worker transaction ngoài thread.
- `@ActiveProfiles` và `@TestPropertySource` giúp tạo context với profile/properties khác, không thay thế resource lock cho JVM globals.
- `@DynamicPropertySource` đưa values động vào Spring context (ví dụ Testcontainers URL) nhưng không khóa mọi external resource; khi dynamic values thay theo subclass và context caching, cần lifecycle/context isolation tương ứng.

**Lỗi nguy hiểm:** test mở context trước, sau đó gọi `System.setProperty(...)` rồi kỳ vọng `@ConditionalOnProperty` tự đăng ký bean khác. Conditions thường được evaluate khi context xây dựng, không mỗi lần bạn gọi `getBean`.

## 26. Static cache, ThreadLocal, mockStatic và System.out

Ngoài ba globals chính còn các state leak hay gặp:

**Static cache:**

```java
private static final Map<String, String> CACHE =
        new HashMap<>();
```

Đây là snippet. Map có mutable contents dù reference final; thread safety và test isolation đều có thể lỗi. Nếu cache là phần production contract, test với một cache instance theo scope, có clear/evict API và ownership rõ. Đừng dựa vào test order để map empty.

**Static ThreadLocal:**

```java
private static final ThreadLocal<String> TENANT =
        new ThreadLocal<>();
```

ThreadLocal không chia sẻ cùng value giữa hai threads, nhưng nếu executor thread được reuse và code quên `remove()` trong finally, request/test sau trên **cùng thread** có thể thấy tenant trước đó. Tracing MDC, security context, transaction state cũng cần cleanup theo framework policy.

**Mockito static mocking:** khi dùng `Mockito.mockStatic(...)`, đóng `MockedStatic` trong try-with-resources. Static mock thường có scope theo thread mà nó được tạo/điều khiển, nhưng không được giả định nó tự áp dụng cho async worker khác. Tránh mock `System.getProperty`/JDK core methods một cách tùy tiện, vì dễ làm framework hoạt động sai.

**System.out/System.err:** test gọi `System.setOut(...)` hoặc `System.setErr(...)` đang sửa output streams **toàn JVM**. Dùng snapshot/restore và `Resources.SYSTEM_OUT`/`Resources.SYSTEM_ERR` nếu phải kiểm tra legacy printing. Thường tốt hơn là inject logger/output abstraction thay vì thay standard streams.

**Default charset:** `Charset.defaultCharset()` cũng có thể phụ thuộc JVM startup/configuration/runtime caching; đừng tin nó luôn UTF-8 trên mọi deployment. Dùng `StandardCharsets.UTF_8` tường minh để kiểm tra payload/CSV/HTTP text bytes.

## 27. Chạy song song không có nghĩa mọi tài nguyên tự an toàn

JUnit ResourceLock chỉ khóa những tasks trong phạm vi engine và cùng key. Các ngoại lệ cần phân biệt:

- **Background thread** do test tạo có thể vẫn chạy sau khi test method kết thúc và JUnit nhả lock. Nếu nó còn đọc/write globals, reader test khác có thể bị ảnh hưởng. Dùng `Future.get(timeout)`/thread join/cancellation/awaitTermination và đảm bảo cleanup trước khi test trả về.
- **Gradle forks** hoặc Maven Surefire forks là JVM khác nhau, nên static state/System properties/Locale/TimeZone riêng; nhưng file/database/broker/port có thể vẫn chia sẻ. ResourceLock không khóa cross-process.
- **Test engine khác** không nhất thiết tôn trọng khóa của JUnit Jupiter.
- **Production code** trong cùng JVM không tự đợi JUnit resource lock; nếu Spring background scheduler/consumer đang chạy, mutation của default Locale/TimeZone có thể ảnh hưởng nó.
- **Parallel Stream/ForkJoinPool** hoặc Servlet async work có thể dùng threads khác; snapshot/restore theo test thread không buộc những task khác ngừng.
- **Static mutable singleton** và Spring singleton cùng không biến thành per-test chỉ vì test class dùng @TestInstance(PER_METHOD).
- **JVM startup flags** như `-Duser.timezone=UTC` có ích để cố định môi trường CI, nhưng không thay được tests của app phải hỗ trợ multiple zones/locales.

Nếu buộc test global side effect và không điều khiển được threads/engine khác, chạy test trong **JVM fork riêng** (process isolation) là biện pháp mạnh hơn resource lock trong một engine; vẫn phải dọn external resources và ghi rõ chi phí startup.

## 28. Khi nào dùng @Isolated, @ResourceLock hay process fork?

| Tình huống | Lựa chọn ưu tiên |
| --- | --- |
| Business formatter xử lý locale người dùng | Inject Locale/ZoneId/Clock, không lock |
| Một test legacy đổi đúng một property key | Snapshot/restore + @ResourceLock(Resources.SYSTEM_PROPERTIES, READ_WRITE) |
| Nhiều tests chỉ đọc system properties | @ResourceLock(..., READ) nếu writer cùng key được quản lý |
| Test đổi Locale.Category.FORMAT | Snapshot cả general/display/format + Resources.LOCALE |
| Test đổi TimeZone.default | Snapshot TimeZone và user.timezone + Resources.TIME_ZONE và SYSTEM_PROPERTIES |
| Test class legacy đổi nhiều global state | @Isolated với cleanup; cân nhắc fork |
| Static cache được share trong một Spring singleton | Tách cache scope, reset có kiểm soát, @DirtiesContext nếu cần |
| Test 2 JVMs cùng ghi DB/file | External resource isolation/namespace/lock, không dựa @ResourceLock |
| API dùng static ThreadLocal qua thread pool | finally remove/propagation và test task reuse |
| Test toàn bộ localized output | Explicit inputs và snapshot version policy, không tin defaults |

**Không dùng @Isolated mặc định cho mọi test**: nó giảm concurrency nhưng có thể che thiết kế dùng global state. Ưu tiên sửa seam/injection; lock là cơ chế nhất thời cho code không thể thay ngay.

## 29. Debug lỗi flaky theo triệu chứng

**A. Test pass riêng, fail full suite:** tìm `static` mutable map/counter, `System.setProperty`, `Locale.setDefault`, `TimeZone.setDefault`, Spring singleton/cache và async tasks còn sống.

**B. Test chỉ fail trên laptop ngôn ngữ khác:** formatter dùng `Locale.getDefault()` hoặc text casing không dùng `Locale.ROOT` cho identifiers; inject locale của case.

**C. Test chỉ fail khác timezone/DST:** `ZoneId.systemDefault()`, `LocalDateTime.now()`, `Date.toString()` hoặc date parsing lệ thuộc máy; inject zone/Clock và so sánh Instant/ISO contract.

**D. set user.timezone rồi output không đổi:** TimeZone default cached hoặc formatter đã được tạo trước. Không trông đợi property được re-read; dùng ZoneId.of explicit.

**E. Static final AtomicInteger vẫn rò giữa tests:** atomic != isolated. Tạo counter riêng theo test hoặc reset có lock và ownership.

**F. @BeforeEach reset static nhưng chạy song song fail:** reset của một test ảnh hưởng test khác; tránh static hoặc dùng lock xử lý đúng phạm vi.

**G. @DirtiesContext không giải quyết lỗi:** rò System properties/Locale/TimeZone ngoài Spring context; rollback bean không thay global state.

**H. @ResourceLock không ngăn fail:** test khác dùng key khác/không lock, background thread, test engine khác hoặc Gradle fork khác.

**I. @TestInstance(PER_METHOD) nhưng bean còn state:** Spring singleton context được reuse, không phải test instance state.

**J. Locale FORMAT thay đổi nhưng display names không đổi:** FORMAT/DISPLAY là hai category riêng; assert đúng category.

**K. DateTimeFormatter output đổi dù đã inject ZoneId:** có thể pattern chứa localized month/day names và Locale chưa inject rõ, hoặc database time zone rules version khác; kiểm tra cả Locale, ZoneId và instant.

**L. Test JVM không thoát:** unmanaged executor/scheduled thread hoặc listener không dừng, không phải chỉ static field.

**M. Unit test dùng Clock.fixed nhưng integration code vẫn gọi Instant.now():** injection không đi hết call path; tìm hidden calls.

**N. MockStatic pass ở test thread, không có hiệu lực trong @Async:** scope thread khác, dùng injected collaborator thay static dependency.

## 30. Những lỗi cần tránh

1. Dùng `static final AtomicInteger` hoặc mutable map làm per-test fixture mà không reset/isolate.
2. Cho rằng @TestInstance(PER_METHOD) reset static fields và JVM defaults.
3. Reset static ở @BeforeEach rồi chạy concurrent methods không lock.
4. Dùng `System.setProperty` để config Spring test khi `@SpringBootTest(properties)`/runner đủ dùng.
5. Cleanup bằng `System.clearProperty` dù key trước test có giá trị.
6. Gọi `System.setProperties(new Properties())` để xóa một property.
7. Đổi `user.language` runtime và mong `Locale.getDefault()` tự refresh.
8. Chỉ snapshot general Locale, bỏ qua FORMAT/DISPLAY category overrides.
9. Đổi `user.timezone` và mặc định `TimeZone.getDefault()` sẽ re-read tức thì.
10. Gọi `TimeZone.getTimeZone(invalid)` mà không biết fallback GMT có thể che lỗi cấu hình.
11. Assert date theo `ZoneId.systemDefault()` của CI thay vì zone contract.
12. Dùng `LocalDateTime.now()` cho thời gian cần deterministic test thay vì Clock.
13. Share `SimpleDateFormat` static giữa nhiều worker threads.
14. Dùng `@Execution(SAME_THREAD)` rồi nghĩ khóa các test classes khác.
15. Dùng @ResourceLock khác key giữa reader/writer và nghĩ chúng phối hợp.
16. Tin @ResourceLock ngăn mọi background thread hoặc external process.
17. Quên restore trong finally, đặc biệt khi assertion fail.
18. Tin @DirtiesContext khôi phục JVM globals ngoài Spring.
19. Quên rằng Spring singleton có thể được shared bởi cached context.
20. Mock static API rồi không đóng MockedStatic, hoặc nghĩ mock áp vào async thread.
21. Cho static ThreadLocal trên executor reuse mà quên remove().
22. Đổi System.out toàn JVM để test log mà không dùng Resources.SYSTEM_OUT và cleanup.
23. Tạo assertion phụ thuộc thứ tự thread/test methods để đọc counter.
24. Dùng JVM fork để che race trong shared DB/file mà không cách ly external namespace.
25. Xem test pass một lần dưới concurrent mode là chứng minh thread safety.
26. Không test locale/timezone cụ thể theo nghiệp vụ, chỉ chọn UTC cho toàn CI.
27. Đưa property credentials/secrets vào test log hoặc committed config.
28. Giả định ResourceLock “phát hiện” race; nó chỉ serialize các tests hợp tác.

## 31. Checklist QA cuối cùng

**Kiến trúc:**

- Static mutable data có thật sự cần thiết không? Có thể thay bằng instance/config-injected collaborator?
- Formatter dùng Locale/ZoneId tường minh và DateTimeFormatter immutable?
- “Now” được lấy qua Clock inject thay vì Instant.now() ngầm?
- Sequence/caches có per-test/scope rõ ràng?
- ThreadLocal/MDC/security context được dọn bằng finally?

**Global mutation:**

- Nếu System property được thay, có snapshot **giá trị cũ hoặc null** đúng không?
- Có restore bằng setProperty hoặc clearProperty đúng theo snapshot không?
- Có tránh System.setProperties để không xóa global map không?
- Có snapshot general/DISPLAY/FORMAT Locale trước khi mutate?
- Có snapshot TimeZone và user.timezone cả hai không?
- Có restore tất cả trong finally/try-with-resources kể cả khi test fail?
- Scope mutation có ngắn nhất và không còn background worker đang đọc sau scope?

**JUnit parallel:**

- Test reader/writer cùng khai báo đúng resource key và READ/READ_WRITE?
- @ResourceLock áp cho locale/timezone/properties tương ứng?
- @Isolated chỉ dùng khi cần class-level isolation thực sự?
- Có biết ResourceLock không khóa background threads, engine khác hoặc JVM forks?
- Gradle maxParallelForks và JUnit mode có được cấu hình có chủ đích?
- Test không phụ thuộc thứ tự methods hoặc exact thread scheduling?

**Spring Boot:**

- Test config dùng `withPropertyValues`/`@SpringBootTest(properties)` thay JVM System.setProperty?
- Config record được bind và bean factory không đọc default Locale/TimeZone ngầm?
- Có kiểm tra cả baseline và overridden context bằng runner?
- Nếu singleton mutable state trong context cache, có teardown/reset đúng và context ownership rõ?
- Không xem @DirtiesContext như reset static/system property?
- Các @Async/@Scheduled tasks đã kết thúc/được dọn trước khi test kết thúc?

**Tính runnable và khẳng định:**

- Java package/class/file names và Gradle dependency nhất quán?
- Java SE demo có javac/java và stdout đúng trên JDK17?
- Số JUnit methods thực tế là 14 trong năm test classes?
- Các snippets anti-pattern có được đánh dấu để không copy làm production code?
- Đã phân biệt test runner behavior với app business correctness?

**Kết luận:** các đối tượng dùng chung của JVM **không biết ranh giới test**. `static` mutable state, `System.properties`, Locale và TimeZone defaults có thể làm test flaky dù mỗi method đúng khi chạy riêng. Phòng tránh tốt nhất là **truyền cấu hình và thời gian/locale/zone tường minh**, tạo state theo phạm vi phù hợp và không mutate JVM globals. Với legacy code bắt buộc đổi globals, dùng **snapshot/restore + JUnit @ResourceLock hoặc @Isolated**, nhớ những cơ chế này chỉ điều phối tests hợp tác, không thay thế process isolation hay cleanup tài nguyên bên ngoài JVM.

## 32. Tài liệu tham khảo

- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.10.0/user-guide/#writing-tests-parallel-execution): @Execution, @ResourceLock, @Isolated và parallel config.
- [JUnit Jupiter ResourceLock API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html): lock keys và READ/READ_WRITE semantics.
- [JUnit Jupiter Resources API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Resources.html): SYSTEM_PROPERTIES, SYSTEM_OUT, SYSTEM_ERR, LOCALE, TIME_ZONE.
- [Java SE 17 Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): getDefault/setDefault, DISPLAY/FORMAT categories.
- [Java SE 17 TimeZone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TimeZone.html): getDefault/setDefault, cached default và user.timezone.
- [Java SE 17 ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): timezone rules và systemDefault.
- [Java SE 17 Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): Clock.fixed/systemUTC và deterministic time.
- [Java SE 17 DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): immutable formatter, withZone và locale.
- [Spring Boot 3.5 Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringBootTest properties, TestContext cache và context runner.
- [Spring Framework TestContext caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): caching/eviction và context isolation.
- [Spring Boot 3.5 Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): @ConfigurationProperties, @DefaultValue và property precedence.
