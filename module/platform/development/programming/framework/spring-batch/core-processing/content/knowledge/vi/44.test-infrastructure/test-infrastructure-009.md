# Clock và thời gian kiểm thử trong Spring Batch

## 1. Vì sao thời gian là một phần của test infrastructure?

Trong ứng dụng Spring Batch, rất nhiều quy tắc xử lý phụ thuộc vào thời điểm chạy:

- Job chỉ lấy đơn hàng có `dueAt` trước thời điểm chốt số liệu.
- Job tổng hợp giao dịch của **ngày nghiệp vụ** (business date) trong múi giờ của công ty.
- Một item bị coi là quá hạn nếu đã vượt `expiresAt`.
- Job tải dữ liệu “24 giờ vừa qua” hoặc xử lý các bản ghi nằm trong một khoảng thời gian.
- Dữ liệu được gắn `createdAt`, `processedAt` hoặc `exportedAt` khi writer lưu.
- Retry, restart, cửa sổ chạy ban đêm và quy tắc chốt ngày tạo thêm các trường hợp biên.

Nếu logic gọi trực tiếp `Instant.now()`, `LocalDate.now()`, `new Date()` hoặc `System.currentTimeMillis()`, đầu ra test có thể thay đổi theo ngày, theo múi giờ máy chạy CI và theo tốc độ thực thi. Test chạy đúng lúc 23:59:59 hoặc 00:00:00 dễ cho kết quả khác nhau dù code không đổi.

**Clock** của Java là một điểm trừu tượng hóa thời gian từ package `java.time`. Thay vì mỗi thành phần tự hỏi đồng hồ hệ thống “bây giờ là mấy giờ?”, ta tiêm một `Clock` đã biết vào logic xử lý. Trong môi trường production, đồng hồ có thể đọc thời gian thật; trong test, nó trả về một thời điểm được cố định hoặc được điều chỉnh có chủ đích.

Mục tiêu của bài học là thiết kế **hạ tầng kiểm thử thời gian có tính xác định** cho Spring Batch, đồng thời hiểu rõ những thứ một `Clock` tự viết **không kiểm soát được**.

## 2. Những kiểu thời gian cần phân biệt

Java Time API cung cấp nhiều kiểu dữ liệu khác nhau. Chọn sai kiểu là nguồn gốc của nhiều lỗi test.

| Kiểu | Ý nghĩa | Thường dùng ở đâu |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối trên dòng thời gian UTC | Audit event, thời hạn, timestamp trao đổi giữa hệ thống |
| `LocalDate` | Một ngày theo lịch, không mang giờ hoặc múi giờ | Business date, kỳ báo cáo, partition theo ngày |
| `LocalDateTime` | Ngày và giờ theo lịch nhưng **không có timezone/offset** | Giao diện nội bộ hoặc dữ liệu lịch địa phương khi biết rõ zone ở nơi khác |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | API và dữ liệu cần giữ offset của thời điểm |
| `ZonedDateTime` | Ngày giờ kèm `ZoneId` và quy tắc DST | Giờ làm việc, lịch chạy theo địa phương |
| `ZoneId` | Múi giờ có quy tắc lịch sử và DST | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `Duration` | Khoảng thời gian theo giây/nano | Timeout, độ trễ, “sau 30 phút” |
| `Period` | Khoảng cách theo ngày/tháng/năm trên lịch | “Sau một tháng”, chu kỳ báo cáo theo tháng |
| `Clock` | Nguồn cung cấp thời điểm hiện tại và zone mặc định khi dùng các API `now(clock)` | Dependency trong processor, service và test fixture |

Hai dòng sau có ý nghĩa khác nhau:

```java
Instant currentInstant = clock.instant();
LocalDate businessDate = LocalDate.now(clock);
```

`clock.instant()` cho biết **một thời điểm**, còn `LocalDate.now(clock)` suy ra **ngày lịch theo zone của Clock**. Cùng một `Instant` có thể thuộc hai ngày khác nhau ở UTC và Việt Nam.

Ví dụ:

```java
Instant instant = Instant.parse("2026-03-31T17:00:00Z");

LocalDate utcDay = instant.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate vietnamDay = instant
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();

// utcDay:     2026-03-31
// vietnamDay: 2026-04-01
```

Khi test job tổng hợp doanh thu ngày 1 tháng 4 theo giờ Việt Nam, dùng `LocalDate.now(Clock.systemUTC())` sẽ không cho cùng business date tại thời điểm trên.

## 3. Ba Clock quan trọng nhất khi kiểm thử

### 3.1. Clock.systemUTC() và Clock.system(zone)

Đây là clock chạy theo thời gian thực, thường dùng trong production:

```java
Clock utcClock = Clock.systemUTC();
Clock vietnamClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant a = utcClock.instant();
Instant b = vietnamClock.instant(); // Cùng một dòng thời gian thực
```

Zone chỉ ảnh hưởng cách biểu diễn ngày giờ địa phương, không làm thời gian UTC chạy nhanh hay chậm hơn.

Tránh `Clock.systemDefaultZone()` cho business rules quan trọng trừ khi timezone của máy chủ thực sự là một phần của contract. Trên laptop người phát triển, container, CI và server triển khai, giá trị mặc định có thể khác nhau.

### 3.2. Clock.fixed(): đóng băng thời điểm

```java
Instant frozenAt = Instant.parse("2026-05-01T10:00:00Z");
Clock fixedClock = Clock.fixed(frozenAt, ZoneOffset.UTC);

System.out.println(fixedClock.instant()); // Luôn là 2026-05-01T10:00:00Z
System.out.println(fixedClock.instant()); // Vẫn y hệt
```

Đây là lựa chọn phổ biến nhất cho unit test. Dù test chạy trong vài mili giây hay vài phút, logic vẫn quan sát cùng một thời điểm.

### 3.3. Clock.offset(): kiểm tra trước/sau một thời hạn

```java
Clock baseline = Clock.fixed(
        Instant.parse("2026-05-01T10:00:00Z"),
        ZoneOffset.UTC
);

Clock afterThirtyMinutes =
        Clock.offset(baseline, Duration.ofMinutes(30));

assertEquals(
        Instant.parse("2026-05-01T10:30:00Z"),
        afterThirtyMinutes.instant()
);
```

`Clock.offset(...)` tạo một clock mới lệch thời gian so với clock nền. Nếu nền là `fixed`, clock mới cũng không tự chạy; nó rất hữu ích để lập hai test case trước và sau deadline.

`Clock.tick(...)` làm tròn thời gian theo độ phân giải chỉ định, ví dụ từng giây hoặc từng phút. Nó **không phải bộ điều khiển thời gian** và không tự đẩy thời gian về phía trước theo bước test mong muốn. Chỉ dùng khi ứng dụng thực sự yêu cầu độ chính xác thời gian thấp hơn.

## 4. Đưa Clock thành dependency của ứng dụng

### 4.1. Đăng ký bean cho production

```java
import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Ứng dụng có thể đọc tên timezone từ cấu hình môi trường để phù hợp từng thị trường; ví dụ dùng `app.business-zone=Asia/Ho_Chi_Minh`. Điều quan trọng là **zone được khai báo rõ ràng** và được dùng nhất quán.

Các component sử dụng constructor injection:

```java
import java.time.Clock;
import java.time.LocalDate;
import org.springframework.stereotype.Service;

@Service
public class BusinessDateService {
    private final Clock clock;

    public BusinessDateService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

Vì `Clock` là dependency, test có thể thay nó bằng `Clock.fixed(...)` mà không đổi logic nghiệp vụ. Cấu trúc này cũng giúp mọi thành phần quyết định ngày nghiệp vụ theo cùng một nguồn thời gian.

### 4.2. Tránh lời gọi thời gian nằm rải rác

Không nên:

```java
public boolean isExpired(Invoice invoice) {
    return invoice.expiresAt().isBefore(Instant.now());
}
```

Nên:

```java
public boolean isExpired(Invoice invoice) {
    return invoice.expiresAt().isBefore(clock.instant());
}
```

Khác biệt chỉ là nguồn thời gian, nhưng chính thay đổi này cho phép test xác minh chính xác ba mốc: **trước hạn, đúng hạn và sau hạn**.

Đừng tạo `Clock.systemUTC()` bên trong mỗi lần gọi method: làm như vậy vẫn gắn logic với thời gian thực. Cũng không nên giữ `Instant.now()` trong một trường `static final` để mô phỏng một “ngày hiện tại”, vì thời điểm đó được khóa cứng theo lúc nạp class và có thể rò trạng thái giữa test.

## 5. Ví dụ: unit test cho ItemProcessor theo thời gian

Giả sử một batch step xử lý hóa đơn đến hạn. Business rule: **hóa đơn có `dueAt <= now` được chọn**, hóa đơn chưa đến hạn bị filter khỏi luồng xử lý.

Model:

```java
import java.time.Instant;

public record Invoice(String id, Instant dueAt) {}
```

Processor:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import org.springframework.batch.item.ItemProcessor;

public final class DueInvoiceProcessor
        implements ItemProcessor<Invoice, Invoice> {

    private final Clock clock;

    public DueInvoiceProcessor(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public Invoice process(Invoice invoice) {
        Instant now = clock.instant();
        return invoice.dueAt().isAfter(now) ? null : invoice;
    }
}
```

Trong Spring Batch, một `ItemProcessor` trả về `null` có nghĩa là **filter item**. Đây không phải exception và không làm tăng skip count. Nếu reader trả về 3 invoice, 1 invoice chưa đến hạn và mọi bước còn lại đều thành công, bạn thường kỳ vọng `readCount=3`, `filterCount=1`, `writeCount=2`.

JUnit 5 test không cần khởi động Spring context:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DueInvoiceProcessorTest {

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-05-01T10:00:00Z"),
            ZoneOffset.UTC
    );

    private final DueInvoiceProcessor processor =
            new DueInvoiceProcessor(clock);

    @Test
    void processesInvoiceBeforeDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-1",
                Instant.parse("2026-05-01T09:59:59Z")
        );

        assertNotNull(processor.process(invoice));
    }

    @Test
    void processesInvoiceExactlyAtDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-2",
                Instant.parse("2026-05-01T10:00:00Z")
        );

        assertNotNull(processor.process(invoice));
    }

    @Test
    void filtersInvoiceAfterDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-3",
                Instant.parse("2026-05-01T10:00:01Z")
        );

        assertNull(processor.process(invoice));
    }
}
```

Ba test trên xác nhận trực tiếp ý nghĩa của toán tử so sánh: deadline **bao gồm** thời điểm bằng `now`. Nếu quy tắc nghiệp vụ là “chỉ nhận trước hạn” (`dueAt < now`), kỳ vọng test tại ranh giới sẽ đảo lại.

### Test thời gian thay đổi mà không chờ đợi

```java
@Test
void invoiceBecomesDueAfterThirtyMinutes() throws Exception {
    Clock startClock = Clock.fixed(
            Instant.parse("2026-05-01T10:00:00Z"),
            ZoneOffset.UTC
    );
    Invoice invoice = new Invoice(
            "INV-LATER",
            Instant.parse("2026-05-01T10:30:00Z")
    );

    assertNull(new DueInvoiceProcessor(startClock).process(invoice));

    Clock later = Clock.offset(startClock, Duration.ofMinutes(30));
    assertNotNull(new DueInvoiceProcessor(later).process(invoice));
}
```

Ví dụ này cần import `java.time.Duration`. Không gọi `Thread.sleep(...)` để chờ đến hạn; test vẫn tức thời, chạy lặp lại được và không phụ thuộc tốc độ CI.

## 6. Điểm quan trọng của batch: một job run cần mốc thời gian ổn định

`Clock.fixed(...)` cho unit test là chưa đủ để giải quyết một vấn đề production: một batch job có thể chạy **hàng phút hoặc hàng giờ**, băng qua ranh giới ngày hoặc giờ chốt.

Giả sử job lấy dữ liệu “trước ngày hôm nay”:

```java
LocalDate today = LocalDate.now(clock);
```

Nếu câu lệnh trên được gọi lại trong mỗi item, một job bắt đầu 23:59 có thể xử lý phần đầu file theo ngày D và phần sau theo ngày D+1. Khi restart vào hôm sau, cùng một `JobInstance` có thể áp dụng quy tắc lọc khác lần chạy trước.

Có hai hướng thiết kế thường gặp:

1. **Snapshot một lần khi job bắt đầu:** lưu `asOf` hoặc `businessDate` vào execution context hoặc truyền cho component xử lý, không đọc lại thời gian hiện tại cho mỗi item.
2. **Đưa thời gian chốt vào JobParameters:** launcher xác định `businessDate`/`asOf` trước khi chạy; step đọc cùng giá trị trong mọi chunk và trong các lần restart.

Với batch cần **restart có kết quả nhất quán**, cách dùng tham số thời gian rõ ràng thường dễ kiểm tra nhất.

### Ví dụ: step scoped processor dùng asOf cố định

Giả sử launcher truyền:

```text
asOf = 2026-05-01T10:00:00Z
```

Processor được tạo một lần trong scope của `StepExecution` và sử dụng giá trị này:

```java
import java.time.Instant;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InvoiceStepConfiguration {

    @Bean
    @StepScope
    ItemProcessor<Invoice, Invoice> dueInvoiceProcessor(
            @Value("#{jobParameters['asOf']}") String asOfText) {

        Instant asOf = Instant.parse(asOfText);
        return invoice -> invoice.dueAt().isAfter(asOf)
                ? null
                : invoice;
    }
}
```

Không cần gọi `Clock` trong từng item. Cách dùng này quyết định cutoff một lần, có thể tái hiện bằng cùng dữ liệu input và cùng tham số `asOf`.

Ở **Spring Batch 5.x**, khi launch job có thể xây tham số như sau:

```java
Instant asOf = clock.instant();

JobParameters parameters = new JobParametersBuilder()
        .addString("asOf", asOf.toString(), true)
        .addString("businessDate", LocalDate.now(clock).toString(), true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, parameters);
```

Đoạn trên giả định đã có `JobLauncher`, `Job`, `Clock` và các import tương ứng từ Spring Batch 5.x. Cờ `true` đánh dấu **identifying parameter**. Tên job cộng các identifying parameters xác định `JobInstance`.

**Quan hệ với restart:**

- Lần chạy mới cho một business date khác có thể mang tham số khác.
- Khi restart một instance thất bại, cần dùng **cùng bộ identifying parameters** và giữ nguyên cutoff của lần chạy đó.
- Không tự sinh `asOf = Instant.now()` mới trong mỗi lần restart vì như vậy có thể biến một restart thành instance mới hoặc thay đổi dữ liệu đầu vào được chọn.
- Một instance đã `COMPLETED` không được chạy lại với đúng bộ identifying parameters như một execution mới thông thường; muốn tái xử lý chủ đích cần chính sách rerun riêng.

Nếu business date là identity của công việc, thường chỉ `businessDate` cần identifying, còn `asOf` được chọn khi khởi chạy và phải **cố định giữa các lần thực thi cùng instance**. Phải thiết kế cặp tham số phù hợp với logic restart; không dùng tham số non-identifying có thể bị thay đổi tùy tiện để thay cutoff cho cùng một instance.

## 7. Chuẩn bị Clock trong Spring Boot integration test

### 7.1. TestConfiguration cung cấp thời gian cố định

Khi cần chạy cả Spring context, có thể cung cấp một bean `Clock` chỉ cho test:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BusinessClockIntegrationTest {

    @TestConfiguration
    static class FixedTimeConfiguration {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(
                    Instant.parse("2026-03-31T17:00:00Z"),
                    ZoneId.of("Asia/Ho_Chi_Minh")
            );
        }
    }

    @Autowired
    private BusinessDateService businessDateService;

    @Test
    void resolvesBusinessDateFromConfiguredZone() {
        assertEquals(
                LocalDate.of(2026, 4, 1),
                businessDateService.today()
        );
    }
}
```

Đoạn test cần import `java.time.LocalDate`. `@Primary` giúp Spring chọn bean thời gian của test khi ứng dụng đã khai báo một bean `Clock` production.

**Lưu ý về quản lý bean:** nếu application context có nhiều bean `Clock` với qualifier riêng, `@Primary` chưa chắc thay thế đúng bean mà component cần; hãy dùng cùng qualifier hoặc thay thế bean theo chiến lược của phiên bản Spring Boot dự án. Không tạo một Clock cố định dùng chung rồi cố mutate nó cho nhiều test chạy song song; mỗi kịch bản nên có cấu hình và trạng thái rõ ràng.

### 7.2. Dùng Spring Batch Test để chạy job

Với **Spring Batch 5.x**, `spring-batch-test` cung cấp `@SpringBatchTest` và `JobLauncherTestUtils` để chạy job/step trong test. Một integration test có thể:

1. Khởi tạo database test, bảng metadata batch và fixture đầu vào.
2. Tiêm `Clock.fixed(...)` để xác định thời điểm khởi chạy.
3. Tạo `JobParameters` với `asOf` và `businessDate` cố định.
4. Chạy job bằng `JobLauncherTestUtils.launchJob(parameters)`.
5. Kiểm tra `BatchStatus`, số item đọc/lọc/ghi và dữ liệu output cuối cùng.
6. Dọn metadata, bảng/file output và fixture chỉ trong môi trường test.

Ví dụ phần thực thi trong một test đã cấu hình `@SpringBatchTest`, có job cụ thể được gán cho launcher:

```java
var parameters = new JobParametersBuilder()
        .addString("asOf", "2026-05-01T10:00:00Z")
        .addString("businessDate", "2026-05-01")
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
// Tiếp tục assert dữ liệu nghiệp vụ và các bộ đếm StepExecution.
```

Đây là phần test minh họa, không phải một test class độc lập: nó cần cấu hình job, repository, database và fixture tương ứng. Nếu dự án sử dụng **Spring Batch 6.x**, API dùng để launch job trong test là `JobOperatorTestUtils`, đồng thời một số package Spring Batch đã thay đổi; cần sử dụng tài liệu cùng version để điều chỉnh import và phần khởi chạy.

### 7.3. Ngăn job tự chạy khi test context khởi động

Trong Spring Boot, cấu hình:

```properties
spring.batch.job.enabled=false
```

giúp các bài integration test chủ động chọn thời điểm và `JobParameters` thay vì để job tự chạy ngay khi context khởi tạo. Cấu hình này chỉ điều khiển **auto-launch của Spring Boot**, không phải một cơ chế đóng băng đồng hồ hoặc vô hiệu hóa mọi `@Scheduled` của ứng dụng.

## 8. Kiểm thử thời gian theo múi giờ và ranh giới ngày

### 8.1. Đóng băng Instant, chọn ZoneId tường minh

```java
Instant point = Instant.parse("2026-11-16T17:30:00Z");

Clock utc = Clock.fixed(point, ZoneOffset.UTC);
Clock hcm = Clock.fixed(
        point,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

assertEquals(LocalDate.of(2026, 11, 16), LocalDate.now(utc));
assertEquals(LocalDate.of(2026, 11, 17), LocalDate.now(hcm));
```

Cùng một thời điểm nhưng `LocalDate.now(...)` khác nhau. Đây là một test regression tốt cho job tổng hợp theo ngày địa phương khi hệ thống chạy trên máy chủ đặt ở UTC.

### 8.2. Khoảng thời gian nên dùng [start, end)

Giả sử job lấy các event xảy ra trong business date `2026-04-01` theo giờ Việt Nam:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 4, 1);

Instant startInclusive = date.atStartOfDay(zone).toInstant();
Instant endExclusive = date.plusDays(1).atStartOfDay(zone).toInstant();
```

Khi truy vấn, dùng nửa khoảng mở:

```sql
SELECT event_id, occurred_at
FROM payment_event
WHERE occurred_at >= :startInclusive
  AND occurred_at <  :endExclusive;
```

Ưu điểm:

- Không phải tự tạo “23:59:59.999999…” phụ thuộc độ chính xác cột timestamp.
- Một event đúng tại nửa đêm ngày kế tiếp thuộc **một** cửa sổ duy nhất.
- Các khoảng ngày nối tiếp nhau không bị chồng lấn hoặc bỏ sót.

Nếu database lưu timestamp kiểu `TIMESTAMP WITHOUT TIME ZONE`, phải xác định rõ quy ước dữ liệu (ví dụ giá trị UTC đã bỏ timezone) trước khi truyền tham số. Tốt hơn, khi phù hợp, sử dụng kiểu dữ liệu có semantics rõ ràng về thời điểm như PostgreSQL `timestamptz`.

### 8.3. Daylight Saving Time (DST)

Không phải ngày lịch nào cũng dài chính xác 24 giờ. Ở các múi giờ có DST, ngày chuyển giờ có thể có 23 hoặc 25 giờ.

Ví dụ `Europe/Berlin` chuyển sang giờ mùa hè vào **2026-03-29**:

```java
ZoneId berlin = ZoneId.of("Europe/Berlin");
LocalDate businessDate = LocalDate.of(2026, 3, 29);

Instant start = businessDate.atStartOfDay(berlin).toInstant();
Instant end = businessDate.plusDays(1).atStartOfDay(berlin).toInstant();

assertEquals(Duration.ofHours(23), Duration.between(start, end));
```

Nếu tính end bằng `start.plus(Duration.ofHours(24))`, test có thể ăn sang một giờ của ngày tiếp theo. Với **cửa sổ theo ngày lịch**, hãy tính ranh giới bằng `LocalDate` và `ZoneId` rồi mới chuyển sang `Instant`.

Ở chiều ngược lại, khi DST kết thúc, một giờ địa phương có thể xảy ra hai lần. `LocalDateTime` không tự xác định được lần nào. Với event thực tế, lưu `Instant` hoặc offset rõ ràng; với lịch chạy, cần policy cho thời điểm địa phương nhập nhằng/không tồn tại.

### 8.4. Duration khác Period

“Cách đây 24 giờ” khác “ngày hôm qua theo lịch địa phương”:

```java
Instant last24Hours = clock.instant().minus(Duration.ofHours(24));

LocalDate yesterday = LocalDate.now(clock).minusDays(1);
```

Nếu job báo cáo **ngày hôm qua**, nên lấy `startOfDay` của `yesterday` và `today` trong business zone; nếu job thực sự cần **24 giờ gần nhất**, dùng `Duration` trên `Instant`.

## 9. Retry và restart: không để đồng hồ làm đổi luật giữa hai lần thử

### 9.1. Retry một item

Giả sử processor kiểm tra event đã quá hạn chưa:

```java
boolean expired = item.expiresAt().isBefore(clock.instant());
```

Nếu writer bị lỗi tạm thời, framework có thể retry item hoặc chunk. Trong lúc retry, thời gian thật tiến lên; một item chưa hết hạn ban đầu có thể trở thành hết hạn sau đó. Như vậy **cùng một item**, trong **cùng một job run**, có thể nhận kết quả khác nhau.

Đây không phải bug của `Clock`, mà là do quyết định nghiệp vụ phụ thuộc vào giá trị `now` biến thiên. Nếu hệ thống yêu cầu kết quả ổn định trong run, xác định `asOf` một lần, truyền vào processor và dùng nó cho mọi retry/restart. Nếu yêu cầu thật sự là “xét deadline ở đúng thời điểm gửi API”, thời gian động mới hợp lý; test cần diễn tả rõ chính sách ấy.

### 9.2. Restart sau nửa đêm

Ví dụ một job xử lý dữ liệu ngày D:

```text
23:55 ngày D:    JobInstance bắt đầu, businessDate = D
23:59 ngày D:    Chunk 1 commit thành công
00:01 ngày D+1:  Chunk 2 thất bại
08:00 ngày D+1:  Job restart từ checkpoint
```

Nếu restart gọi `LocalDate.now(clock)` để chọn input, công việc có thể chuyển sang ngày D+1 mà không ai chủ đích yêu cầu. Khi `businessDate` là `JobParameter` ổn định, job vẫn xử lý dữ liệu ngày D.

Để test restart:

- Khởi chạy job với `businessDate=D` và `asOf` cố định.
- Gây lỗi có kiểm soát sau khi một số chunk đã commit.
- Giữ nguyên metadata `JobRepository` và dữ liệu checkpoint.
- Khởi động lại cùng `JobInstance` theo API restart của version đang dùng.
- Kiểm tra phần dữ liệu còn lại được xử lý theo **cùng businessDate/cutoff**, không tạo output trùng.

Không gọi thao tác xóa toàn bộ `JobExecution` trước khi restart, vì metadata và `ExecutionContext` là một phần của trạng thái khôi phục.

### 9.3. Clock không phải bộ điều khiển transaction

Đóng băng `Clock` của processor không tự làm dừng timeouts, retry backoff, transaction manager hoặc scheduler. Những thành phần này có thể dựa vào đồng hồ hệ thống, bộ đo thời gian đơn điệu hoặc API riêng. Muốn test retry/backoff một cách nhanh và có tính xác định, cần kiểm soát **cơ chế retry/scheduler cụ thể** (ví dụ truyền strategy, fake scheduler hoặc cấu hình backoff bằng 0 trong test), không giả định một `Clock.fixed(...)` sẽ làm tất cả dừng lại.

## 10. Giới hạn cần biết: Clock của bạn kiểm soát những gì?

| Thành phần | Clock được inject có tác dụng? | Lý do |
| --- | --- | --- |
| Service gọi `clock.instant()` | Có | Sử dụng trực tiếp dependency |
| Processor gọi `LocalDate.now(clock)` | Có | Dùng zone và instant của Clock |
| Writer tự đặt `processedAt = clock.instant()` | Có | Thời điểm gắn dữ liệu do application quản lý |
| Code gọi `Instant.now()` không tham số | Không | Truy cập đồng hồ hệ thống |
| SQL gọi `CURRENT_TIMESTAMP` | Không | Database quyết định thời gian |
| Timestamp metadata do Spring Batch tự cấp | Không bảo đảm | Framework có cơ chế thời gian riêng |
| Job được kích hoạt bởi `@Scheduled` | Không tự động | Scheduler có clock và cơ chế kích hoạt riêng |
| HTTP service trả về thời gian của server khác | Không | Nguồn thời gian nằm ngoài application |
| `Thread.sleep` hoặc timeout dựa trên elapsed time | Không tự động | Không phụ thuộc Clock của logic nghiệp vụ |
| `JobParameters` chứa `businessDate` đã được truyền | Clock không thay đổi giá trị | Đó là input bất biến của job execution theo thiết kế |

Ví dụ, nếu writer dùng:

```sql
INSERT INTO invoice_log(invoice_id, created_at)
VALUES (:invoiceId, CURRENT_TIMESTAMP);
```

thì `created_at` sẽ phản ánh thời gian database, dù Java test đã inject `Clock.fixed(...)`. Nếu test muốn assert thời điểm cụ thể, có thể cho writer truyền timestamp từ Java:

```java
Instant processedAt = clock.instant();
```

và dùng `processedAt` làm tham số SQL. Lúc này phải thống nhất cách driver/JDBC mapping `Instant` sang kiểu timestamp của database.

Tương tự, metadata như thời điểm bắt đầu/kết thúc `JobExecution` do Spring Batch quản lý không bắt buộc trùng với bean `Clock` do ứng dụng tự tạo. Test không nên assert bằng tuyệt đối thời điểm “đóng băng” nếu nguồn metadata không dùng clock đó. Với metadata framework, thường phù hợp hơn khi assert trạng thái, sự hiện diện của timestamp và các quan hệ thứ tự hợp lệ, có xét đến precision của hệ thống lưu trữ.

## 11. Thiết kế fixture thời gian đầy đủ

Đối với job lấy các invoice có `dueAt <= asOf`, chuẩn bị bộ dữ liệu biên:

| ID | dueAt so với asOf | Kỳ vọng |
| --- | --- | --- |
| INV-001 | Trước 1 ngày | Chọn |
| INV-002 | Trước 1 nano giây | Chọn nếu dữ liệu lưu giữ được độ chính xác đó |
| INV-003 | Bằng chính xác asOf | Chọn nếu quy tắc là `<=` |
| INV-004 | Sau 1 nano giây | Không chọn |
| INV-005 | Sau 1 ngày | Không chọn |
| INV-006 | `null` | Xử lý theo chính sách validation, không mặc định là quá hạn |

Khi test với database, độ chính xác lưu trữ timestamp có thể chỉ tới microsecond hoặc millisecond. Nếu ghi hai mốc lệch 1 nano giây rồi đọc lại, database có thể làm tròn khiến chúng bằng nhau. Nên điều chỉnh độ lệch fixture theo độ chính xác thực tế của storage và giữ một test thuần Java cho phép so sánh ở độ chính xác nano.

Đối với job tổng hợp theo ngày:

| Trường hợp | Kiểu test |
| --- | --- |
| Event ngay trước start of day | Không thuộc kỳ báo cáo |
| Event đúng start of day | Thuộc kỳ báo cáo |
| Event ngay trước end exclusive | Thuộc kỳ báo cáo |
| Event đúng end exclusive | Thuộc kỳ tiếp theo |
| Job bắt đầu sát nửa đêm | Business date vẫn ổn định |
| UTC ngày D, local đã là D+1 | Sử dụng đúng `ZoneId` |
| DST tăng/giảm giờ | Cửa sổ dựa trên ngày lịch, không cộng cứng 24 giờ |
| Restart vào hôm sau | Giữ nguyên tham số kỳ báo cáo |

Ngoài output, một integration test nên kiểm tra `BatchStatus`, dữ liệu được ghi, các bộ đếm `StepExecution` có liên quan và trạng thái checkpoint nếu đang kiểm thử restart. Nhưng trạng thái `COMPLETED` đơn lẻ không chứng minh job đã chọn đúng ngày hoặc đúng khoảng thời gian.

## 12. Clock trong test song song và môi trường CI

### Tránh mutable state chung

`Clock.fixed(...)` là immutable nên phù hợp cho test song song khi tất cả test dùng cùng một mốc. Tuy nhiên, nếu bạn tự viết `MutableClock` có thể tăng giờ bằng method `advance(...)`, rồi đăng ký nó như singleton cho toàn bộ test suite, hai test chạy song song có thể thay đổi thời gian của nhau.

Những lựa chọn ổn định hơn:

- Dùng `Clock.fixed(...)` khác nhau cho từng unit test hoặc từng test context.
- Truyền `asOf`/`businessDate` riêng theo từng job execution khi kiểm thử nhiều run đồng thời.
- Nếu bắt buộc phải có mutable clock, giới hạn nó trong một test và điều phối access/thread safety rõ ràng.
- Với các job đa tiến trình, bảo đảm cách tính cutoff không phụ thuộc đồng hồ riêng của từng worker.

### Tránh phụ thuộc múi giờ CI

Không dựa vào:

```java
LocalDate today = LocalDate.now();
ZoneId zone = ZoneId.systemDefault();
```

Trong test business date, thay bằng:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock clock = Clock.fixed(
        Instant.parse("2026-03-31T17:00:00Z"),
        zone
);
LocalDate date = LocalDate.now(clock);
```

CI có thể đặt `TZ=UTC`; nhiều container cũng dùng UTC. Định nghĩa zone tại boundary nghiệp vụ giúp test không phụ thuộc host.

### Phân biệt “wall clock” và “elapsed time”

`Clock` diễn tả thời gian lịch và các thời điểm. Để đo độ dài thực thi trong một process, `System.nanoTime()` thường phù hợp hơn vì đây là bộ đo khoảng thời gian (monotonic elapsed time theo ý nghĩa sử dụng), trong khi đồng hồ lịch có thể bị điều chỉnh bởi hệ thống. Dùng `Clock.fixed(...)` để test logic “đã tới hạn chưa”, không dùng nó để benchmark hoặc kết luận một chunk mất bao nhiêu mili giây.

Với timeout, test lý tưởng thường điều khiển fake scheduler hoặc tín hiệu bất đồng bộ thay vì `Thread.sleep(...)` và so sánh một deadline sát thời gian thực. Những bài test thật sự kiểm tra hiệu năng nên tách khỏi unit test logic thời gian.

## 13. Các lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Test chỉ fail quanh nửa đêm | Gọi `LocalDate.now()` ở nhiều thời điểm khác nhau | Dùng `Clock.fixed` trong test; snapshot cutoff trong một run |
| Kết quả khác giữa laptop và CI | `ZoneId.systemDefault()` khác nhau | Khai báo business zone tường minh |
| Test đúng ở UTC nhưng sai ở Việt Nam | Nhầm `Instant` và `LocalDate` | Chuyển qua `atZone(businessZone)` rồi lấy ngày |
| Bỏ sót dữ liệu ngày DST | Tính end = start + 24 giờ | Tính start of day cho ngày kế tiếp trong zone |
| Restart chọn file ngày mới | Tính lại `businessDate` theo thời gian restart | Lưu ngày/cutoff trong `JobParameters` hoặc checkpoint |
| Freeze Clock nhưng `created_at` vẫn thay đổi | SQL `CURRENT_TIMESTAMP` do DB cung cấp | Truyền timestamp từ Java hoặc điều chỉnh mong đợi test |
| Freeze Clock nhưng metadata Batch vẫn dùng giờ thật | Framework không dùng bean Clock của ứng dụng | Kiểm tra contract timestamp, tránh assert giá trị fixed không được bảo đảm |
| Test timeout chạy chậm | Dùng `Thread.sleep`/real scheduler | Fake scheduler, backoff test hoặc điều khiển sự kiện |
| Test làm thay đổi giờ của test khác | Mutable Clock singleton dùng chung | Cô lập clock theo test, bỏ mutable state global |
| Test “qua hạn” lúc pass lúc fail | Deadline đặt rất gần `Instant.now()` | Dùng fixed baseline và test riêng từng ranh giới |
| Job chạy lại nhưng sai kỳ | Dùng `run.id` mới và tính lại business date không kiểm soát | Xác định rõ kỳ nghiệp vụ và tham số identity |

## 14. Bài tập thực hành

**Bài 1 – Processor quá hạn.** Viết `ItemProcessor<Invoice, Invoice>` chỉ chọn hóa đơn đến hạn. Dùng `Clock.fixed(...)` để kiểm tra ba trường hợp: trước cutoff, đúng cutoff và sau cutoff. Thử đổi chính sách thành `dueAt < now` và cập nhật kỳ vọng tại ranh giới.

**Bài 2 – Tổng hợp theo ngày tại Việt Nam.** Cho `Instant.parse("2026-03-31T17:00:00Z")`. Viết test xác minh rằng business date ở `Asia/Ho_Chi_Minh` là `2026-04-01`. Tạo query dùng khoảng `[startOfDay, nextStartOfDay)` và kiểm tra event ngay ranh giới.

**Bài 3 – Một job qua nửa đêm.** Giả lập job bắt đầu trước nửa đêm rồi restart vào hôm sau. Truyền `businessDate` và `asOf` cố định qua `JobParameters`; kiểm tra dữ liệu đầu ra vẫn thuộc cùng kỳ. Không xóa `JobRepository` giữa hai lần thực thi nếu muốn test restart thật.

**Bài 4 – DST.** Dùng `Europe/Berlin` với ngày `2026-03-29`. Kiểm tra khoảng giữa hai `atStartOfDay(zone)` là 23 giờ và giải thích vì sao cộng 24 giờ không phải cách chọn “một ngày nghiệp vụ”.

**Bài 5 – Phạm vi Clock.** Viết một writer lưu `processedAt` từ `clock.instant()` và một writer lưu bằng SQL `CURRENT_TIMESTAMP`. Đóng băng Clock, chạy integration test trên database riêng và xác minh hai nguồn thời gian có thể khác nhau.

## 15. Kết luận

Trong Spring Batch, thời gian nên được coi là **đầu vào có thể kiểm soát** của logic nghiệp vụ. `java.time.Clock` giúp tách code khỏi đồng hồ hệ thống, còn `Clock.fixed(...)` cho phép unit test tái hiện chính xác một thời điểm và các trường hợp biên. Đối với batch kéo dài hoặc có restart, không chỉ inject Clock là đủ: cần cố định `businessDate`/`asOf` trong suốt vòng đời của một job instance. Kết hợp **Instant cho thời điểm tuyệt đối**, **ZoneId cho ngày lịch nghiệp vụ**, **khoảng [start, end)** cho cửa sổ dữ liệu và **test fixture độc lập** giúp job chạy nhất quán ở local, CI và production.

### Tài liệu tham khảo

- [Java SE – Clock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
- [Java SE – Instant API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE – ZoneId API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [Spring Batch – JobParameters](https://docs.spring.io/spring-batch/reference/domain.html#jobParameters)
- [Spring Batch – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch – Restarting a Job](https://docs.spring.io/spring-batch/reference/job.html)
