# Định danh, thời gian, múi giờ và locale có thể lặp lại

## 1. Mục tiêu: một bộ test chạy lúc nào, ở đâu cũng cho cùng kết quả

Trong module **Spring Boot - testing**, nhóm **Dữ liệu kiểm thử**, một nguyên nhân phổ biến của test *flaky* là dữ liệu phụ thuộc môi trường: ID ngẫu nhiên, đồng hồ hiện tại, múi giờ hệ điều hành hoặc locale mặc định của máy chạy CI.

Ví dụ code có thể PASS trên máy cá nhân nhưng FAIL lúc gần nửa đêm, khi CI đặt `TZ=UTC` hoặc khi JVM chạy dưới locale `tr-TR`:

~~~java
// Phản ví dụ minh họa, không phải class biên dịch độc lập.
UUID id = UUID.randomUUID();
Instant issuedAt = Instant.now();
LocalDate today = LocalDate.now();
String key = "ID".toLowerCase();
~~~

Vì dữ liệu được tạo từ môi trường ngầm, expected result không còn chỉ phụ thuộc input của test. Cách sửa đúng không phải là thêm `Thread.sleep`, hard-code ngày hôm nay hay đổi `TimeZone.setDefault` cho toàn JVM, mà là **đưa các nguồn biến thiên thành dependency có thể điều khiển**:

1. Tạo ID qua `IdGenerator`, dùng fake cố định hoặc dãy xác định trong test.
2. Đọc thời gian qua `java.time.Clock`, dùng `Clock.fixed`/`Clock.offset`.
3. Tính ngày theo `ZoneId` nghiệp vụ đã khai báo, không lấy từ hệ điều hành.
4. Chọn `Locale` theo input/request; dùng `Locale.ROOT` cho technical keys và `MessageSource` cho text bản địa hóa.
5. Seed và cleanup database bằng fixture riêng; không assert cứng database sequence mà mình không kiểm soát.
6. Bảo vệ test trong môi trường song song và khác JDK/CLDR/tzdb.

Bài có ví dụ **Java 17 / Spring Boot 3.5.16** độc lập: REST API tạo biên nhận minh họa, hai lớp JUnit kiểm tra ID/time/zone/locale (unit và HTTP thật), cùng các lưu ý dành cho JPA, DST, JSON và CI.

## 2. Định nghĩa “lặp lại” không phải “mọi ID luôn giống nhau”

| Đối tượng | Cách kiểm soát phù hợp | Điều không nên làm |
| --- | --- | --- |
| UUID của một output | Inject generator trả UUID đã chọn | Assert ID bất kỳ được `UUID.randomUUID()` tạo ở lần trước |
| Hai record cần hai ID | Fake generator trả dãy ID cố định **khác nhau** | Dùng cùng một UUID cho hai insert trong database |
| ID do DB sequence cấp | Sử dụng ID thực trả về, kiểm tra quan hệ/business key | Assert sequence luôn bắt đầu tại 1 |
| Mốc `createdAt` | Inject `Clock`, lấy một `Instant` duy nhất | Gọi `Instant.now()` nhiều lần rồi so sánh bằng nhau |
| TTL | Tính bằng `Duration` từ thời điểm đã kiểm soát | Chờ hết TTL bằng `Thread.sleep` |
| Ngày nghiệp vụ | `instant.atZone(businessZone).toLocalDate()` | Dùng `LocalDate.now()` mặc định của máy |
| Text bản địa hóa | `MessageSource` với `Locale` tường minh | Phụ thuộc `Locale.getDefault()` |
| JSON timestamp | Quy định format/precision, test raw JSON | Dựa vào default khác nhau giữa các thư viện |
| Database fixtures | Seed/reset rõ ràng, schema/index riêng | Phụ thuộc dữ liệu do test trước để lại |

ID cố định trong unit test **không phải** ID production. Generator production vẫn phải đáp ứng uniqueness/concurrency/độ khó đoán nếu yêu cầu. Một UUID được dùng làm public identifier **không tự thay thế authorization**.

Determinism còn đòi hỏi cách assert đúng. Test có thể hoàn toàn ổn định khi **ID là ngẫu nhiên** nếu nó kiểm tra rằng ID hợp lệ, là duy nhất, và foreign key trỏ đến **ID thật được trả về**, thay vì đòi một chuỗi UUID cụ thể.

## 3. Chọn đúng kiểu thời gian của java.time

| Kiểu Java | Nó biểu diễn | Ví dụ mục đích |
| --- | --- | --- |
| `Instant` | Một mốc tuyệt đối trên timeline | Created/updated timestamp, audit event, expiry |
| `LocalDate` | Một ngày lịch, không kèm zone hay giờ | Ngày kinh doanh, ngày sinh |
| `LocalTime` | Giờ trên đồng hồ, chưa có ngày | Giờ mở cửa |
| `LocalDateTime` | Ngày+giờ địa phương, **chưa có zone/offset** | Input lịch cần diễn giải theo khu vực |
| `OffsetDateTime` | Ngày giờ có offset `+07:00` hoặc `Z` | API yêu cầu explicit offset |
| `ZonedDateTime` | Ngày giờ kèm IANA `ZoneId` và DST rules | Lịch hẹn ở `Europe/Paris` |
| `Duration` | Độ dài trên timeline theo giây/nanos | Timeout, TTL 60 phút |
| `Period` | Chênh lệch năm/tháng/ngày trên lịch | Hết hạn sau một tháng lịch |
| `Clock` | Nguồn thời gian được inject | Freeze/advance time trong test |

Giả sử `Instant` là `2025-01-01T00:30:00Z`:

~~~text
UTC:                    2025-01-01 00:30
Asia/Ho_Chi_Minh:       2025-01-01 07:30
America/Los_Angeles:    2024-12-31 16:30
~~~

Đó là **cùng một thời điểm**, nhưng tính ra hai ngày khác nhau theo business zone. Nếu test đang kiểm tra “ngày chốt sổ ở Việt Nam”, phải nói rõ `Asia/Ho_Chi_Minh`, không lấy zone từ cấu hình OS.

**Tránh dùng `LocalDateTime` cho một timestamp tuyệt đối**: `2025-01-01T00:30` không cho biết là UTC, Hà Nội hay Los Angeles. Cần `ZoneId`/`ZoneOffset` để chuyển nó thành một `Instant`.

## 4. Clock: làm thời gian có thể test được

Production bean:

~~~java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
~~~

Test setup:

~~~java
Instant base = Instant.parse("2025-01-01T00:30:00Z");
Clock fixed = Clock.fixed(base, ZoneOffset.UTC);
Clock plusTwoHours = Clock.offset(fixed, Duration.ofHours(2));
~~~

Đây là các đoạn Java minh họa, cần imports `java.time.Clock`, `Instant`, `ZoneOffset`, `Duration`. Với fixed clock, `fixed.instant()` luôn trả cùng `base`; với offset clock, thời gian có thể được mô phỏng **tiến thêm hai giờ mà không ngủ**.

Một service có logic TTL nên:

~~~java
Instant createdAt = clock.instant();
Instant expiresAt = createdAt.plus(Duration.ofHours(1));
~~~

Thay vì:

~~~java
// Phản ví dụ: hai lần đọc system clock có thể lệch nhau.
Instant createdAt = Instant.now();
Instant expiresAt = Instant.now().plus(Duration.ofHours(1));
~~~

**Không khởi tạo Clock.fixed trong code production** trừ khi domain chủ ý cần một giờ giả lập. Test thay Clock bằng `@Primary`/bean test; source production giữ `Clock.systemUTC`.

Clock injection **không sửa được** thời gian do DB `CURRENT_TIMESTAMP`, triggers, Kafka, scheduler riêng hoặc external system tạo ra. Những nguồn đó phải được kiểm tra bằng phương pháp riêng, không được suy rằng fixed Java Clock làm đồng hồ toàn hệ thống đứng yên.

## 5. Múi giờ: ZoneId khác offset

- `ZoneOffset.ofHours(7)` là offset cố định.
- `ZoneId.of("Asia/Ho_Chi_Minh")` là IANA timezone có lịch sử/quy tắc riêng.
- `ZoneId.of("America/New_York")` có DST: -05:00 vào mùa đông, -04:00 vào mùa hè theo quy tắc năm 2025.

Với lịch theo khu vực, dùng **`ZoneId`**, không hard-code offset của tháng hiện tại. Ngược lại, một `Instant` lưu UTC có thể không cần timezone địa phương nếu ứng dụng chỉ tính expiry 60 phút trên timeline.

### Một ngày không luôn bằng 24 giờ địa phương

- `instant.plus(Duration.ofDays(1))` tăng chính xác **24 giờ**.
- `zonedDateTime.plusDays(1)` tăng **một ngày lịch**, có thể tương ứng 23 hoặc 25 giờ khi vượt DST.

Hãy xác định contract: “TTL sau 24 giờ” khác với “đúng 09:00 ngày mai theo giờ Paris”. Test nên có ca qua ngày chuyển DST nếu ứng dụng đặt lịch theo local time.

### DST gap/overlap

`ZoneRules.getValidOffsets(localDateTime)` phân loại:

| New York năm 2025 | Số offset hợp lệ | Hệ quả |
| --- | --- | --- |
| `2025-03-09T02:30` | 0 | Gap: giờ này không tồn tại |
| `2025-11-02T01:30` | 2 | Overlap: giờ này tồn tại hai lần |
| `2025-01-15T09:00` | 1 | Trường hợp bình thường |

Code JUnit ở phần 13 kiểm tra hai ranh giới DST này. Nếu user đặt một cuộc hẹn vào giờ gap/overlap, ứng dụng cần **policy tường minh**: từ chối, chuyển tới giờ hợp lệ hoặc yêu cầu chọn offset; không dựa vào cách thư viện mặc định giải mơ hồ.

Quy tắc tzdb được cập nhật theo luật quốc gia. Với kịch bản tương lai đặc biệt nhạy cảm, quản lý JDK/tzdb của CI, hoặc kiểm tra invariant thay vì giả định chính sách DST sẽ không bao giờ thay đổi.

## 6. Locale: khác timezone, ảnh hưởng ngôn ngữ và format

`Locale.forLanguageTag("vi-VN")` biểu diễn ưu tiên tiếng Việt ở Việt Nam; `Locale.forLanguageTag("en-US")` là tiếng Anh Mỹ; `Locale.ROOT` là locale trung tính phục vụ xử lý dữ liệu kỹ thuật.

**Locale không cho biết timezone.** Header `Accept-Language: vi-VN` không chứng minh người dùng đang ở Việt Nam; người dùng Việt ở California hoàn toàn có thể chọn giao diện tiếng Việt nhưng ngày nghiệp vụ được tính theo chi nhánh Mỹ.

Những tác động cần test:

1. **Thông báo:** `MessageSource.getMessage(key, args, locale)` đọc resource bundles, không dùng string hard-coded trong mỗi controller.
2. **Số:** `NumberFormat.getNumberInstance(locale)` khác dấu phân nhóm và dấu thập phân.
3. **Tiền tệ:** cần `Currency`/currency code nghiệp vụ, không chỉ suy ra từ locale.
4. **Ngày hiển thị:** `DateTimeFormatter.ofLocalizedDate(...)` có ngữ cảnh ngôn ngữ.
5. **Chuẩn hóa kỹ thuật:** `toLowerCase(Locale.ROOT)` để tránh bẫy Turkish-I.

Ví dụ Turkish-I:

~~~java
assertEquals("id", "ID".toLowerCase(Locale.ROOT));
assertEquals(
        "ıd",
        "ID".toLowerCase(Locale.forLanguageTag("tr-TR"))
);
~~~

Đây là code body JUnit minh họa, không phải file độc lập; ký tự `ı` là dotless-i khác chữ `i` thông thường. **Không** dùng `toLowerCase()` không tham số cho protocol keys hoặc stable identifiers.

### JDK/CLDR không đảm bảo mọi ký tự format bất biến

Một chuỗi `NumberFormat` cho `fr-FR` có thể sử dụng NBSP hoặc narrow NBSP, trông gần giống space thường. Assertion exact localized text có thể thay đổi khi nâng JDK/CLDR. Nếu hợp đồng chỉ cần **giá trị số**, hãy assert numeric JSON hoặc parse với locale cụ thể; nếu hợp đồng đòi **chuỗi chính xác**, hãy pin formatter, runtime và ký tự phân cách mong đợi.

Locale fallback phải chủ động cấu hình. Spring Boot chỉ auto-config `MessageSource` khi có resource bundle gốc `messages.properties` (trừ cấu hình khác); nếu chỉ có `messages_vi.properties` mà thiếu gốc, đừng giả định Boot đã tạo đúng MessageSource.

## 7. Bài thực hành: một REST response có ID/time/locale xác định

Ta tạo biên nhận **không ghi database** để quan sát rõ các dependency. Request:

~~~http
POST /api/receipts
Content-Type: application/json
Accept-Language: vi-VN

{"sku":"SKU-7"}
~~~

Response mong đợi trong test:

~~~json
{
  "id": "00000000-0000-4000-8000-000000000007",
  "sku": "SKU-7",
  "createdAt": "2025-01-01T00:30:00Z",
  "expiresAt": "2025-01-01T01:30:00Z",
  "businessDate": "2025-01-01",
  "languageTag": "vi-VN",
  "message": "Đã tạo"
}
~~~

Cùng Instant, nếu zone là `America/Los_Angeles`, `businessDate` thành `2024-12-31`. Với `Accept-Language: en-US` và zone vẫn ở Việt Nam, `message` trở thành `Created` nhưng `createdAt`/`businessDate` không đổi.

Hợp đồng cụ thể:

- Production ID từ `UUID.randomUUID()` qua interface `IdGenerator`; test fake ID đã biết.
- Production time từ `Clock.systemUTC()`; test `Clock.fixed`.
- Business zone từ `app.business-zone=Asia/Ho_Chi_Minh`, không dùng systemDefault.
- Message từ `MessageSource` và locale của request.
- Json date/time là ISO strings, không trả format phụ thuộc locale.
- Request SKU phải `@NotBlank`, nên input trống bị từ chối 400.

Mã gồm các tệp:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/deterministic/
  DeterministicDataApplication.java
  IdGenerator.java
  InfrastructureConfig.java
  ReceiptRequest.java
  ReceiptResponse.java
  ReceiptService.java
  ReceiptController.java
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
src/test/java/com/example/deterministic/
  ReceiptServiceTimeTest.java
  ReceiptHttpTest.java
~~~

## 8. Gradle và cấu hình message/timezone

**`settings.gradle`:**

~~~groovy
rootProject.name = 'deterministic-data-tests'
~~~

**`build.gradle` (Groovy DSL, Java 17):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
app.business-zone=Asia/Ho_Chi_Minh
spring.messages.basename=messages
spring.messages.fallback-to-system-locale=false
spring.messages.encoding=UTF-8
spring.jackson.serialization.write-dates-as-timestamps=false
~~~

Những properties này pin **business ZoneId**, chọn message resource bundle và fallback rõ ràng, đồng thời yêu cầu Jackson serialize Java date/time bằng chuỗi ISO theo cấu hình này. `spring.messages.fallback-to-system-locale=false` tránh fallback âm thầm sang ngôn ngữ mặc định OS.

Spring Boot 3.5.16 được chọn để code/imports và BOM đồng nhất; đó không có nghĩa mọi phiên bản Boot tương lai dùng import/test dependency giống hệt. Dự án cần Gradle Wrapper/JDK 17+; các lệnh chạy nằm cuối bài.

## 9. Application, ID generator và production infrastructure

**`src/main/java/com/example/deterministic/DeterministicDataApplication.java`:**

~~~java
package com.example.deterministic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DeterministicDataApplication {
    public static void main(String[] args) {
        SpringApplication.run(DeterministicDataApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/deterministic/IdGenerator.java`:**

~~~java
package com.example.deterministic;

import java.util.UUID;

@FunctionalInterface
public interface IdGenerator {
    UUID next();
}
~~~

**`src/main/java/com/example/deterministic/InfrastructureConfig.java`:**

~~~java
package com.example.deterministic;

import java.time.Clock;
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InfrastructureConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    IdGenerator idGenerator() {
        return UUID::randomUUID;
    }
}
~~~

Trong production, `Clock` đọc thời điểm thật và generator sinh UUID mới. Service chỉ biết hai dependency, vì vậy test có thể thay cả hai qua constructor hoặc `@TestConfiguration`.

**Không mock tĩnh `Instant.now()`/`UUID.randomUUID()` khi đã có injection seam đơn giản.** Static mocking có thêm rủi ro do thread, scope và library instrumentation; Clock thật được freeze là một fake ít ma sát hơn.

## 10. DTOs và service không dùng environment global

**`src/main/java/com/example/deterministic/ReceiptRequest.java`:**

~~~java
package com.example.deterministic;

import jakarta.validation.constraints.NotBlank;

public record ReceiptRequest(@NotBlank String sku) {
}
~~~

**`src/main/java/com/example/deterministic/ReceiptResponse.java`:**

~~~java
package com.example.deterministic;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public record ReceiptResponse(
        UUID id,
        String sku,
        Instant createdAt,
        Instant expiresAt,
        LocalDate businessDate,
        String languageTag,
        String message
) {
}
~~~

**`src/main/java/com/example/deterministic/ReceiptService.java`:**

~~~java
package com.example.deterministic;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Locale;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Service;

@Service
public class ReceiptService {
    private final Clock clock;
    private final IdGenerator ids;
    private final MessageSource messages;
    private final ZoneId businessZone;

    public ReceiptService(
            Clock clock,
            IdGenerator ids,
            MessageSource messages,
            @Value("${app.business-zone:Asia/Ho_Chi_Minh}")
            String configuredBusinessZone
    ) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.ids = Objects.requireNonNull(ids, "ids");
        this.messages = Objects.requireNonNull(messages, "messages");
        this.businessZone = ZoneId.of(configuredBusinessZone);
    }

    public ReceiptResponse issue(String sku, Locale locale) {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(locale, "locale");

        Instant createdAt = clock.instant();
        LocalDate businessDate = createdAt.atZone(businessZone)
                .toLocalDate();

        String message = messages.getMessage(
                "receipt.created", null, locale
        );

        return new ReceiptResponse(
                ids.next(),
                sku,
                createdAt,
                createdAt.plus(Duration.ofHours(1)),
                businessDate,
                locale.toLanguageTag(),
                message
        );
    }
}
~~~

**Điểm cần học:**

- `clock.instant()` chỉ đọc một lần, rồi expiry được tính từ cùng thời điểm.
- `@Value` lấy business-zone rõ ràng; `ZoneId.of` từ chối zone ID sai thay vì âm thầm dùng OS zone.
- `Locale` được truyền từ phía caller, không gọi `Locale.getDefault()` trong service.
- Message được lấy từ bundle, không hard-code theo language trong business logic.
- ID được sinh từ interface, không gọi random trực tiếp trong service.

### Bản dịch

**`src/main/resources/messages.properties`:**

~~~properties
receipt.created=Created
~~~

**`src/main/resources/messages_vi.properties`:**

~~~properties
receipt.created=Đã tạo
~~~

Với locale `vi-VN`, Spring tìm bundle cho tiếng Việt; với `en-US` không có bundle tiếng Anh riêng, default `messages.properties` cung cấp `Created`. Đây là **fallback theo cấu hình**, không theo `Locale.getDefault` của máy.

## 11. HTTP controller dùng Locale của request

**`src/main/java/com/example/deterministic/ReceiptController.java`:**

~~~java
package com.example.deterministic;

import java.util.Locale;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/receipts")
public class ReceiptController {
    private final ReceiptService service;

    public ReceiptController(ReceiptService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ReceiptResponse create(
            @Valid @RequestBody ReceiptRequest request,
            Locale locale
    ) {
        return service.issue(request.sku().trim(), locale);
    }
}
~~~

Spring MVC resolve `Locale` theo `LocaleResolver`. Trong cấu hình mặc định thường dùng `Accept-Language`; test HTTP sẽ gửi header tường minh. Điều này không hề thay `ZoneId` nghiệp vụ.

Controller trả `200 OK` vì demo chỉ tạo response và **không lưu DB**. Nếu production thực sự tạo resource và lưu nó, có thể thiết kế `201 Created` + `Location` và transaction riêng. Trạng thái HTTP là một contract khác, không liên quan tới việc fake ID hay Clock.

`@Valid` và `@NotBlank` giúp Spring trả 400 cho request SKU trống hoặc toàn khoảng trắng. Cần starter validation, đã khai báo ở build.gradle.

## 12. JUnit unit test: kiểm soát ID, giờ, zone, locale

**`src/test/java/com/example/deterministic/ReceiptServiceTimeTest.java`:**

~~~java
package com.example.deterministic;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Locale;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReceiptServiceTimeTest {
    private static final Instant BASE =
            Instant.parse("2025-01-01T00:30:00Z");
    private static final UUID ID = UUID.fromString(
            "00000000-0000-4000-8000-000000000007"
    );

    private StaticMessageSource messages() {
        StaticMessageSource source = new StaticMessageSource();
        source.addMessage(
                "receipt.created",
                Locale.forLanguageTag("vi-VN"),
                "Đã tạo"
        );
        source.addMessage(
                "receipt.created",
                Locale.forLanguageTag("en-US"),
                "Created"
        );
        return source;
    }

    private Clock fixed() {
        return Clock.fixed(BASE, ZoneOffset.UTC);
    }

    private ReceiptService service(String zone, Clock clock) {
        return new ReceiptService(
                clock, () -> ID, messages(), zone
        );
    }

    @Test
    void fixedClockAndIdGiveExactOutput() {
        ReceiptResponse receipt = service(
                "Asia/Ho_Chi_Minh", fixed()
        ).issue("SKU-7", Locale.forLanguageTag("vi-VN"));

        assertEquals(ID, receipt.id());
        assertEquals("SKU-7", receipt.sku());
        assertEquals(BASE, receipt.createdAt());
        assertEquals(
                Instant.parse("2025-01-01T01:30:00Z"),
                receipt.expiresAt()
        );
        assertEquals(LocalDate.of(2025, 1, 1), receipt.businessDate());
        assertEquals("vi-VN", receipt.languageTag());
        assertEquals("Đã tạo", receipt.message());
    }

    @Test
    void sameInstantCanHaveDifferentCalendarDates() {
        ReceiptResponse hcm = service(
                "Asia/Ho_Chi_Minh", fixed()
        ).issue("SKU-7", Locale.forLanguageTag("en-US"));

        ReceiptResponse la = service(
                "America/Los_Angeles", fixed()
        ).issue("SKU-7", Locale.forLanguageTag("en-US"));

        assertEquals(hcm.createdAt(), la.createdAt());
        assertEquals(LocalDate.of(2025, 1, 1), hcm.businessDate());
        assertEquals(LocalDate.of(2024, 12, 31), la.businessDate());
    }

    @Test
    void offsetClockSimulatesFutureWithoutSleeping() {
        Clock later = Clock.offset(fixed(), Duration.ofHours(2));

        ReceiptResponse receipt = service(
                "Asia/Ho_Chi_Minh", later
        ).issue("SKU-7", Locale.forLanguageTag("en-US"));

        assertEquals(
                Instant.parse("2025-01-01T02:30:00Z"),
                receipt.createdAt()
        );
        assertEquals(
                Instant.parse("2025-01-01T03:30:00Z"),
                receipt.expiresAt()
        );
    }

    @Test
    void newYorkSpringForwardGapHasNoOffset() {
        ZoneId ny = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2025, 3, 9, 2, 30);

        assertTrue(ny.getRules().getValidOffsets(gap).isEmpty());
    }

    @Test
    void newYorkFallBackOverlapHasTwoOffsets() {
        ZoneId ny = ZoneId.of("America/New_York");
        LocalDateTime overlap = LocalDateTime.of(2025, 11, 2, 1, 30);

        assertEquals(
                2, ny.getRules().getValidOffsets(overlap).size()
        );
    }

    @Test
    void localeChangesMessageButNotInstant() {
        ReceiptService service = service("Asia/Ho_Chi_Minh", fixed());
        ReceiptResponse vi = service.issue(
                "SKU-7", Locale.forLanguageTag("vi-VN")
        );
        ReceiptResponse en = service.issue(
                "SKU-7", Locale.forLanguageTag("en-US")
        );

        assertEquals("Đã tạo", vi.message());
        assertEquals("Created", en.message());
        assertEquals(vi.createdAt(), en.createdAt());
        assertEquals(vi.businessDate(), en.businessDate());
    }

    @Test
    void technicalKeysMustUseLocaleRoot() {
        assertEquals("id", "ID".toLowerCase(Locale.ROOT));
        assertEquals(
                "ıd",
                "ID".toLowerCase(Locale.forLanguageTag("tr-TR"))
        );
    }

    @Test
    void wrongIanaZoneFailsEarly() {
        assertThrows(
                java.time.DateTimeException.class,
                () -> service("Not/A_Real_Zone", fixed())
        );
    }
}
~~~

Có **8 test methods** không cần Spring context, server, DB hoặc sleep. `StaticMessageSource` cho phép gắn bản dịch vào test bằng Java để tách khỏi resource bundles production. Tất cả kết quả thời gian đều có giá trị cụ thể, và test DST kiểm tra bằng `ZoneRules` thay vì phỏng đoán theo đồng hồ máy.

Lưu ý: khi đổi sang source thời gian có scheduler (ví dụ Reactor `Flux.interval`), `Clock.fixed` không tự điều khiển mọi scheduler; phải dùng virtual scheduler/time API tương ứng.

## 13. HTTP integration test: @Primary beans, Accept-Language và JSON

**`src/test/java/com/example/deterministic/ReceiptHttpTest.java`:**

~~~java
package com.example.deterministic;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Import(ReceiptHttpTest.FixedTimeAndIds.class)
class ReceiptHttpTest {
    private static final Instant BASE =
            Instant.parse("2025-01-01T00:30:00Z");
    private static final UUID EXPECTED_ID = UUID.fromString(
            "00000000-0000-4000-8000-000000000007"
    );

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTimeAndIds {
        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(BASE, ZoneOffset.UTC);
        }

        @Bean
        @Primary
        IdGenerator fixedIds() {
            return () -> EXPECTED_ID;
        }
    }

    @Autowired
    TestRestTemplate http;

    private <T> ResponseEntity<T> post(
            String languageTag,
            String sku,
            Class<T> responseType
    ) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAcceptLanguageAsLocales(
                List.of(Locale.forLanguageTag(languageTag))
        );

        return http.exchange(
                "/api/receipts",
                HttpMethod.POST,
                new HttpEntity<>(new ReceiptRequest(sku), headers),
                responseType
        );
    }

    @Test
    void vietnameseRequestHasFixedValues() {
        ResponseEntity<ReceiptResponse> response =
                post("vi-VN", "SKU-7", ReceiptResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());

        ReceiptResponse result = response.getBody();
        assertEquals(EXPECTED_ID, result.id());
        assertEquals("SKU-7", result.sku());
        assertEquals(BASE, result.createdAt());
        assertEquals(
                Instant.parse("2025-01-01T01:30:00Z"),
                result.expiresAt()
        );
        assertEquals(LocalDate.of(2025, 1, 1), result.businessDate());
        assertEquals("vi-VN", result.languageTag());
        assertEquals("Đã tạo", result.message());
    }

    @Test
    void englishLocaleChangesLanguageButNotBusinessTime() {
        ResponseEntity<ReceiptResponse> response =
                post("en-US", "SKU-7", ReceiptResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());

        ReceiptResponse result = response.getBody();
        assertEquals(EXPECTED_ID, result.id());
        assertEquals(BASE, result.createdAt());
        assertEquals(LocalDate.of(2025, 1, 1), result.businessDate());
        assertEquals("en-US", result.languageTag());
        assertEquals("Created", result.message());
    }

    @Test
    void jsonDatesHaveStableIsoRepresentation() {
        ResponseEntity<String> response =
                post("en-US", "SKU-7", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        String json = response.getBody();

        assertTrue(json.contains(
                "\"createdAt\":\"2025-01-01T00:30:00Z\""
        ));
        assertTrue(json.contains(
                "\"expiresAt\":\"2025-01-01T01:30:00Z\""
        ));
        assertTrue(json.contains(
                "\"businessDate\":\"2025-01-01\""
        ));
    }

    @Test
    void blankSkuReturns400FromBeanValidation() {
        ResponseEntity<String> response =
                post("vi-VN", "   ", String.class);

        assertEquals(
                HttpStatus.BAD_REQUEST,
                response.getStatusCode()
        );
    }
}
~~~

**Bốn test methods** ở đây dùng server Spring Boot thật trên cổng ngẫu nhiên và `TestRestTemplate`, không chỉ gọi service như unit test. Điều chúng chứng minh:

- Bean `@Primary Clock`/`@Primary IdGenerator` ở `@TestConfiguration` thực sự được inject vào service.
- Spring MVC xử lý `Accept-Language` thành `Locale` và `MessageSource` lấy bản dịch đúng.
- Jackson xuất `Instant`/`LocalDate` với định dạng ISO contract, không phụ thuộc timestamp epoch hay thứ tự JSON fields.
- Input SKU trống bị Bean Validation từ chối trước khi tạo biên nhận.

**Demo không lưu DB**, nên cùng fixed UUID qua nhiều request chỉ phục vụ assertion, không sinh duplicate primary key. Nếu thêm repository, fake generator phải trả dãy unique có thể lặp lại và test phải seed/reset database.

`@TestConfiguration` chỉ tồn tại trong test source; production vẫn dùng generator ngẫu nhiên và `Clock.systemUTC`. Cấu hình `@Primary` rõ ràng hơn việc dùng `@MockBean` rồi quên stub `Clock.instant()`, điều có thể làm service nhận `null`.

## 14. Nhiều ID: fake theo dãy có thứ tự thay vì một hằng số

Khi test tạo nhiều entity, một ID cố định duy nhất là không đủ. Có thể dùng generator theo dãy:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.UUID;

final class SequenceIdGenerator implements IdGenerator {
    private final Iterator<UUID> values;

    SequenceIdGenerator(List<UUID> ids) {
        values = List.copyOf(ids).iterator();
    }

    @Override
    public UUID next() {
        if (!values.hasNext()) {
            throw new AssertionError("Unexpected extra ID request");
        }
        return values.next();
    }
}
~~~

Đây là **class minh họa**, đặt trong package phù hợp và cần `IdGenerator` của phần 9; không nằm trong file runnable của demo chính. Với hai ID phân biệt:

~~~java
IdGenerator ids = new SequenceIdGenerator(
        List.of(
                UUID.fromString("00000000-0000-4000-8000-000000000001"),
                UUID.fromString("00000000-0000-4000-8000-000000000002")
        )
);
~~~

Đây là đoạn setup minh họa, cần imports `List` và `UUID`. Fake dựa trên `Iterator` **không thread-safe**; không nên dùng một singleton mutable generator chung giữa các test chạy song song. Hãy dùng fake riêng từng test, hoặc thiết kế ID derivation/namespace phù hợp với concurrency.

Nếu ID đến từ DB `@GeneratedValue`/sequence: chỉ assert **quan hệ** dựa vào ID được DB trả về, không mặc định rằng sequence được reset về 1 trước mỗi test. Khi database có nhiều test song song, một giá trị sequence chính xác là artifact của trạng thái DB, không phải hợp đồng nghiệp vụ.

## 15. Database timestamps, timezone JDBC và độ chính xác

Nguồn thời gian không chỉ ở Java:

- `Clock` kiểm soát code nào gọi `clock.instant()`.
- DB `CURRENT_TIMESTAMP`/trigger dùng đồng hồ của **database server**.
- Một message broker có thể tự gắn timestamp của broker.
- Hibernate/JDBC có cách chuyển đổi giữa `Instant`, `LocalDateTime`, timezone session và cột `TIMESTAMP` tùy database.
- Database có thể lưu độ chính xác microsecond hoặc millisecond, không giữ đủ nanosecond.

Chiến lược test:

1. Nếu service tạo timestamp, **inject fixed Clock**, persist `Instant`, assert round-trip với precision thực tế đã quy định.
2. Nếu DB tự phát sinh timestamp, không hứa rằng fixed Clock điều khiển DB. Test khoảng hợp lệ hoặc dùng test DB clock/fixture nếu hạ tầng hỗ trợ.
3. Nếu dùng Hibernate, thuộc tính `spring.jpa.properties.hibernate.jdbc.time_zone=UTC` có thể cấu hình JDBC timezone theo phiên bản/driver; nó **không thay thế Clock** và không biến mọi DB local datetime thành một instant rõ ràng.
4. Với hành vi database quan trọng, dùng Testcontainers database cùng loại production thay vì suy ra từ H2.
5. Nếu assertion cần thứ tự các events ở cùng millisecond, dùng sequence/biz ordering tường minh; đừng dựa riêng timestamp để giải quyết tie.

### @DataJpaTest cũng cần fixture riêng

`@DataJpaTest` thường có test-managed transaction và rollback, nhưng một service `REQUIRES_NEW` hoặc server HTTP ở thread khác có thể commit ngoài transaction test. Với dữ liệu cố định cần cleanup/reset phù hợp. Tránh giả định mọi row tự biến mất sau test bất kể code gọi transaction nào.

Khi seed nhiều row, dùng primary/business keys theo case và không rely vào thứ tự repository `findAll()` nếu query không có `ORDER BY`. Tính lặp lại của expected **không thể bảo đảm** nếu kết quả không có thứ tự contract.

## 16. Format số/ngày và locale không cố định của CI

Các định dạng bản địa hóa có thể thay đổi theo JDK/CLDR. Ví dụ:

~~~java
NumberFormat fr = NumberFormat.getNumberInstance(
        Locale.forLanguageTag("fr-FR")
);
String formatted = fr.format(12345.67);
~~~

Đây là đoạn minh họa, cần `java.text.NumberFormat` và `java.util.Locale`. Ký tự nhóm nghìn có thể là non-breaking space hoặc narrow no-break space. Nếu API phải trả **số**, tốt hơn dùng JSON number và định dạng tại UI; đừng convert số thành text localized ở backend chỉ vì JVM default locale.

Với currency, hãy chỉ định `Currency.getInstance("VND")` hoặc currency code theo contract; locale không thay thế đơn vị tiền. Với ngày hiển thị theo locale, hãy truyền `DateTimeFormatter.withLocale(locale)`, đồng thời kiểm soát zone trước khi tạo `LocalDate`.

Không thay `Locale.setDefault`/`TimeZone.setDefault` trong một unit test thông thường. Đây là **trạng thái toàn JVM**; các test khác có thể bị ảnh hưởng dù test của bạn hoàn tất xanh. Nếu legacy code bắt buộc cần test thay default, dùng `try/finally` restore và không chạy song song với tests khác; đó là giải pháp tương thích tạm, không thay thế design injection.

## 17. Độ lặp lại dưới chạy song song và trên CI

Những nguyên nhân test chạy riêng PASS nhưng chạy suite FAIL:

- Test A thay `Locale.setDefault`; Test B đang format chuỗi ở thread khác.
- Hai test dùng chung static fake `Clock` mutable.
- Một `IdGenerator` singleton đếm số thứ tự trong context cache, nên thứ tự test thay đổi output.
- Test DB dùng cùng primary key, một test xóa data khi test khác đọc.
- HTTP server chạy thread khác, commit DB riêng nhưng test client nghĩ transaction rollback đã cleanup.
- CI nâng JDK/tzdb/CLDR, làm địa phương hóa hoặc DST rules khác.
- Test hard-code host/port/đường dẫn phụ thuộc môi trường.

Cách giảm rủi ro:

- Fake immutable `Clock.fixed`, generator per-test hoặc stateless; không mutate singleton giữa test methods.
- Dữ liệu giả có namespace mỗi test/CI worker, cleanup hoặc database/schema riêng.
- Không sleep để chờ event/time; dùng Clock.offset, virtual scheduler, latch/barrier/await có điều kiện.
- Pin toolchain JDK, Spring Boot BOM, TZ/locale của CI nếu cần **như một hàng rào hỗ trợ**, nhưng không để code nghiệp vụ phụ thuộc vào default đó.
- Có thể chạy suite thêm một lượt với `-Duser.language=tr`, `-Duser.country=TR` và `-Duser.timezone=America/Los_Angeles` để tìm những chỗ còn phụ thuộc ambient state.
- Với ngày trong tương lai ở vùng DST, quản lý tzdb, không hứa rules không thay đổi theo luật địa phương.

## 18. Những lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Sửa đúng |
| --- | --- | --- |
| Assert literal UUID tạo bằng `UUID.randomUUID()` | Expected thay đổi ngẫu nhiên | Inject generator hoặc assert structure |
| Dùng một fixed ID cho nhiều DB inserts | Duplicate PK | Dùng deterministic sequence khác nhau |
| Assert DB-generated sequence bằng 1 | Fail khi sequence không reset | Dùng ID trả về, assert quan hệ |
| Gọi `Instant.now()` trực tiếp trong nghiệp vụ | Test phụ thuộc đồng hồ CI | Inject Clock |
| Đọc đồng hồ hai lần cho created/expiry | Lệch vài millis | Lấy một Instant rồi cộng Duration |
| `Thread.sleep` chờ thời gian hết hạn | Chậm/flaky | Clock.offset hoặc virtual time đúng scheduler |
| Dùng `LocalDate.now()` không chỉ rõ zone | Qua nửa đêm trả ngày khác | Instant + explicit ZoneId |
| Dùng `ZoneId.systemDefault()` | CI/laptop khác | Business zone từ config/tenant |
| Locale ngầm `Locale.getDefault()` | Khác language/format | Locale explicit và message bundles |
| Dùng `toLowerCase()` cho technical key | Turkish-I | Locale.ROOT |
| Suy ra timezone từ Accept-Language | Ngày nghiệp vụ sai | ZoneId riêng với locale |
| Dùng fixed offset cho vùng DST | Sai giờ khi đổi mùa | IANA timezone, test gap/overlap |
| Dùng LocalDateTime như timestamp UTC | Mơ hồ không có offset | Instant/OffsetDateTime |
| Assert raw localized separators không pin CLDR | Thay JDK thì FAIL | Assert semantics hoặc pin runtime |
| Fixed Clock nhưng DB `CURRENT_TIMESTAMP` | DB vẫn ghi now thật | Test nguồn DB timestamp riêng |
| Đổi `TimeZone.setDefault` toàn suite | Tests khác bị nhiễu | Inject Clock/ZoneId |
| Mock Clock nhưng không stub instant | NullPointerException | Clock.fixed thật |
| Chia sẻ mutable test generator | Fail theo thứ tự test | Fake per test |
| Mặc định HTTP test rollback server writes | Dữ liệu còn sót | Seed/cleanup ngoài test transaction |
| Không assert JSON ISO contract | Clients decode sai | Test raw JSON và precision |

## 19. Checklist code review và QA

- [ ] ID được kiểm soát qua generator hoặc dùng ID thật trả về khi assert?
- [ ] Nếu nhiều records, fake generator không trả trùng ID?
- [ ] Code nghiệp vụ không đọc `Instant.now()`/`UUID.randomUUID()` ngoài lớp infrastructure?
- [ ] Clock được inject ở production và replace bằng fixed clock trong test?
- [ ] Thời gian liên quan được tính từ **một** mốc Instant?
- [ ] TTL dùng Duration và được test không cần sleep?
- [ ] Business date có IANA ZoneId rõ ràng, không dựa system default?
- [ ] Các calendar operations qua DST có test gap/overlap khi phù hợp?
- [ ] Locale cho text/format lấy từ input hoặc cấu hình rõ ràng?
- [ ] Technical identifiers normalize bằng Locale.ROOT?
- [ ] Resource bundle mặc định tồn tại, fallback locale được kiểm tra?
- [ ] Request Accept-Language được gửi rõ trong HTTP test?
- [ ] JSON timestamps có ISO/offset/precision contract?
- [ ] DB-generated timestamps không bị nhầm với Java Clock?
- [ ] Database fixtures seed/cleanup và tách test song song?
- [ ] Test không thay Locale/TimeZone process-global?
- [ ] Test không giả định thứ tự query DB khi chưa có ORDER BY?
- [ ] JDK/tzdb/CLDR được quản lý nếu output localized byte-for-byte là contract?
- [ ] Test được phân biệt unit, HTTP integration và DB integration đúng phạm vi?

## 20. Chạy test, kết quả dự kiến và tài liệu

Với Gradle Wrapper và JDK 17+:

~~~bash
./gradlew test --tests "com.example.deterministic.ReceiptServiceTimeTest"
./gradlew test --tests "com.example.deterministic.ReceiptHttpTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.deterministic.ReceiptServiceTimeTest"
.\gradlew.bat test --tests "com.example.deterministic.ReceiptHttpTest"
~~~

Bộ ví dụ gồm **8 unit tests + 4 HTTP integration tests = 12 JUnit methods**. Expected theo logic:

~~~text
ID:                 00000000-0000-4000-8000-000000000007
Fixed instant:      2025-01-01T00:30:00Z
Expiry +1h:         2025-01-01T01:30:00Z
Business HCM date:  2025-01-01
Business LA date:   2024-12-31
Locale vi-VN:       Đã tạo
Locale en-US:       Created
~~~

Đây là **expected data**, không phải JUnit stdout đã chạy. Mã không có `System.out.println`, và chưa thực thi Gradle/JUnit trong quá trình soạn. Để chạy trọn vẹn cần dependencies từ Maven Central và project Gradle Wrapper. Không thể dùng `javac` thuần với một file test nếu không cung cấp Spring/JUnit classpath.

**Kết luận:** Một bộ test có thể lặp lại phải **kiểm soát những nguồn không xác định** thay vì chỉ hard-code expected result. Inject ID generator/Clock; chọn ZoneId và Locale tường minh; ổn định serialization và database fixtures; bảo vệ test khỏi mutable globals, concurrency và thay đổi runtime. Khi các nguồn này được quản lý, failure mới thể hiện sai lệch nghiệp vụ thay vì sự khác nhau giữa máy hoặc thời điểm.

### Tài liệu tham khảo chính thức

- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
- [Java SE 17 — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
- [Spring Framework — Spring MVC LocaleResolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Servlet applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)