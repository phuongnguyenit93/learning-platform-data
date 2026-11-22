# Không để test phụ thuộc thời gian thật trong Spring Batch

## 1. Vì sao test dữ liệu batch không nên dùng đồng hồ hiện tại?

Các job Spring Batch thường xử lý dữ liệu theo ngày nghiệp vụ, thời hạn lưu trữ, mốc hết hạn, cửa sổ đồng bộ, thời gian nhận file hoặc lịch chạy định kỳ. Khi test lấy thời gian trực tiếp từ hệ điều hành bằng `Instant.now()`, `LocalDate.now()` hoặc `System.currentTimeMillis()`, kết quả có thể thay đổi chỉ vì **lúc test chạy**.

Ví dụ, batch chỉ lấy đơn hàng tạo trong 24 giờ gần nhất. Test tạo đơn hàng “23 giờ 59 phút trước” so với `Instant.now()`, sau đó chạy batch. Nếu máy CI chậm hoặc công đoạn khởi tạo context mất lâu, item có thể vượt quá ngưỡng. Cùng một bộ mã, test có thể xanh hôm nay, đỏ ngày mai, hoặc chỉ lỗi gần 0 giờ.

Một test thời gian đáng tin cậy phải trả lời được ba câu hỏi:

1. **Thời gian tham chiếu nào?** Ví dụ “hôm nay tại Hà Nội” hay “2025-05-12T00:00:00Z”.
2. **Ai cung cấp thời gian đó?** Cấu hình job, tham số nghiệp vụ hay một đối tượng `Clock` có thể thay thế.
3. **Điều kiện biên là gì?** Trước ngưỡng, đúng ngưỡng và sau ngưỡng có được xử lý khác nhau không?

Mục tiêu là để test cho kết quả giống nhau khi chạy trên laptop, CI, máy chủ khác múi giờ, gần nửa đêm, hoặc khi chạy lại nhiều tháng sau.

### Các kiểu thời gian dễ bị nhầm lẫn

| Kiểu thời gian | Ví dụ | Nguồn nên dùng | Cách test |
|---|---|---|---|
| **Event time** | Đơn được tạo lúc nào | Trường `createdAt` trong dữ liệu đầu vào | Dùng `Instant` cố định ngay trong fixture |
| **Processing time** | Batch đang chạy vào lúc nào | `Clock` được inject | Dùng `Clock.fixed(...)` |
| **Business date** | Batch xử lý dữ liệu ngày nào | `JobParameters`, thường là chuỗi ngày ISO | Truyền ngày cố định như `2025-05-12` |
| **Batch metadata time** | `JobExecution` được tạo/kết thúc lúc nào | Spring Batch / `JobRepository` | Kiểm tra trạng thái, quan hệ và tính hợp lệ; tránh so bằng mili-giây tuyệt đối |
| **Database time** | Giá trị SQL `CURRENT_TIMESTAMP` | Đồng hồ database | Kiểm soát trong lớp persistence hoặc dùng test database có dữ liệu cố định |
| **Scheduler time** | Cron kích hoạt job lúc nào | Hệ thống scheduling | Test logic quyết định tham số riêng, không đợi cron thật |

**Quy tắc:** Dữ liệu test phải có mốc thời gian rõ ràng, còn mã nghiệp vụ cần lấy “bây giờ” qua một phụ thuộc có thể điều khiển.

## 2. Tạo nguồn thời gian có thể thay thế bằng `java.time.Clock`

Java đã cung cấp `Clock` trong thư viện chuẩn. Chúng ta có thể dùng đồng hồ hệ thống ở production, đồng hồ bất biến trong test.

### 2.1. Cấu hình thời gian cho production

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchTimeConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` dùng múi giờ UTC cho biểu diễn thời điểm. Nếu nghiệp vụ tính ngày theo múi giờ địa phương, inject thêm `ZoneId` nghiệp vụ, thay vì phụ thuộc múi giờ mặc định của máy đang chạy.

```java
import java.time.ZoneId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BusinessZoneConfiguration {

    @Bean
    ZoneId businessZone() {
        return ZoneId.of("Asia/Ho_Chi_Minh");
    }
}
```

Trong mã nghiệp vụ:

```java
Instant now = clock.instant();
LocalDate businessToday = LocalDate.now(clock.withZone(businessZone));
```

Đối tượng `Instant` mô tả một thời điểm trên trục UTC. `LocalDate` mô tả một ngày lịch; cùng một `Instant` có thể thuộc hai ngày khác nhau ở hai `ZoneId` khác nhau.

### 2.2. Đặt đồng hồ cố định trong test

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2025-05-12T00:00:00Z"),
        ZoneOffset.UTC
);
```

Mọi lời gọi `fixedClock.instant()` đều trả về thời điểm này, dù test chạy lúc 9 giờ sáng, sau nửa đêm, hoặc chạy lại trong năm sau. Không cần `Thread.sleep(...)` để chờ thời gian trôi qua.

Khi dùng Spring Boot test context đã có bean `Clock` của production, có thể thay bằng bean test được ưu tiên inject:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
public class FixedClockTestConfiguration {

    @Bean
    @Primary
    Clock fixedBatchClock() {
        return Clock.fixed(
                Instant.parse("2025-05-12T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Sau đó nạp cấu hình này vào `@SpringBootTest` qua `@Import(FixedClockTestConfiguration.class)` hoặc `classes` tương ứng. `@Primary` giúp chọn bean test khi có nhiều bean cùng kiểu. Đảm bảo tất cả thành phần cần kiểm soát thời gian **thực sự nhận `Clock` qua dependency injection**; thay bean không ảnh hưởng đến đoạn mã gọi thẳng `Instant.now()`.

## 3. Ví dụ thực tế: lọc bản ghi quá hạn trong processor

Giả sử batch giữ lại sự kiện được ghi nhận trong vòng 48 giờ, bỏ các sự kiện **cũ hơn** ngưỡng. Nếu xử lý tại thời điểm cố định `2025-05-12T00:00:00Z`, ngưỡng là `2025-05-10T00:00:00Z`.

### 3.1. Processor có thể kiểm thử

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.batch.item.ItemProcessor;

record BatchEvent(String id, Instant occurredAt) {}

public final class RecentEventFilter
        implements ItemProcessor<BatchEvent, BatchEvent> {

    private final Clock clock;
    private final Duration retention;

    public RecentEventFilter(Clock clock, Duration retention) {
        this.clock = Objects.requireNonNull(clock);
        this.retention = Objects.requireNonNull(retention);
        if (retention.isNegative()) {
            throw new IllegalArgumentException("retention must not be negative");
        }
    }

    @Override
    public BatchEvent process(BatchEvent item) {
        Instant cutoff = clock.instant().minus(retention);

        // Chỉ loại event cũ hơn cutoff; đúng cutoff vẫn được giữ.
        return item.occurredAt().isBefore(cutoff) ? null : item;
    }
}
```

Trong Spring Batch, `ItemProcessor.process(...)` trả `null` nghĩa là item được **filter**, không phải **skip do exception**. Vì vậy test nên xem `filterCount` chứ không dùng `processSkipCount` cho trường hợp này.

### 3.2. Unit test không dùng thời gian thật

```java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RecentEventFilterTest {

    private RecentEventFilter processor;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
                Instant.parse("2025-05-12T00:00:00Z"),
                ZoneOffset.UTC
        );

        processor = new RecentEventFilter(clock, Duration.ofHours(48));
    }

    @Test
    void shouldFilterEventOlderThan48Hours() throws Exception {
        BatchEvent oldEvent = new BatchEvent(
                "old",
                Instant.parse("2025-05-09T23:59:59Z")
        );

        assertNull(processor.process(oldEvent));
    }

    @Test
    void shouldKeepEventExactlyAtCutoff() throws Exception {
        BatchEvent boundaryEvent = new BatchEvent(
                "boundary",
                Instant.parse("2025-05-10T00:00:00Z")
        );

        assertSame(boundaryEvent, processor.process(boundaryEvent));
    }

    @Test
    void shouldKeepRecentEvent() throws Exception {
        BatchEvent recentEvent = new BatchEvent(
                "recent",
                Instant.parse("2025-05-11T12:00:00Z")
        );

        assertSame(recentEvent, processor.process(recentEvent));
    }
}
```

Các case này kiểm tra điều kiện biên **`isBefore` là nhỏ hơn nghiêm ngặt**. Đúng ngưỡng vẫn được giữ; nếu nghiệp vụ muốn loại item tại ngưỡng, cần đổi điều kiện và cập nhật test tương ứng. Thời điểm fixture đều là hằng số có ý nghĩa nghiệp vụ, không tính bằng `Instant.now().minus(...)`.

### 3.3. Một lỗi thiết kế thường gặp

**Phụ thuộc thời gian thật:**

```java
public BatchEvent process(BatchEvent item) {
    Instant cutoff = Instant.now().minus(Duration.ofHours(48));
    return item.occurredAt().isBefore(cutoff) ? null : item;
}
```

Cách viết này khiến unit test khó tạo lại cùng một mốc. Ngay cả khi test tính thời gian “hiện tại” trước khi gọi processor, đồng hồ vẫn tiếp tục chạy giữa hai thao tác.

**Có thể điều khiển trong test:**

```java
public BatchEvent process(BatchEvent item) {
    Instant cutoff = clock.instant().minus(Duration.ofHours(48));
    return item.occurredAt().isBefore(cutoff) ? null : item;
}
```

Nếu batch chạy rất lâu và mọi item phải dùng **cùng một ngưỡng**, còn tốt hơn là tính `cutoff` đúng một lần ở đầu execution rồi truyền một giá trị `Instant` bất biến cho processor. Inject `Clock` giải quyết khả năng kiểm thử, nhưng gọi lại `clock.instant()` cho mỗi item ở production vẫn có thể làm ngưỡng dịch chuyển trong lúc job chạy.

## 4. Kiểm thử step thật với bộ dữ liệu thời gian cố định

Unit test đủ để kiểm tra logic của `RecentEventFilter`. Integration test xác nhận processor được đăng ký trong step và Spring Batch tính các bộ đếm đúng.

Ví dụ sau sử dụng **Spring Boot 3.x, Spring Batch 5.x, Java 17, JUnit 5**. Các dependency test cần có `spring-batch-test`, `spring-boot-starter-test` và H2; ứng dụng cũng cần `spring-boot-starter-batch`. Test định nghĩa job và đồng hồ riêng, chạy step một lần bằng `JobLauncherTestUtils`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = FixedTimeBatchIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class FixedTimeBatchIntegrationTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void stepShouldFilterOldDataAgainstFixedTime() throws Exception {
        JobExecution jobExecution =
                testUtils.launchStep("filterEventsStep");

        StepExecution stepExecution = jobExecution
                .getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(3L, stepExecution.getReadCount());
        assertEquals(1L, stepExecution.getFilterCount());
        assertEquals(2L, stepExecution.getWriteCount());
        assertEquals(0L, stepExecution.getProcessSkipCount());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2025-05-12T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        @Bean
        @StepScope
        ListItemReader<BatchEvent> eventReader() {
            // Step-scoped: mỗi execution nhận reader mới.
            return new ListItemReader<>(List.of(
                    new BatchEvent("old",
                            Instant.parse("2025-05-09T23:59:59Z")),
                    new BatchEvent("boundary",
                            Instant.parse("2025-05-10T00:00:00Z")),
                    new BatchEvent("recent",
                            Instant.parse("2025-05-11T12:00:00Z"))
            ));
        }

        @Bean
        ItemProcessor<BatchEvent, BatchEvent> eventProcessor(Clock clock) {
            return new RecentEventFilter(clock, Duration.ofHours(48));
        }

        @Bean
        Step filterEventsStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ItemReader<BatchEvent> eventReader,
                ItemProcessor<BatchEvent, BatchEvent> eventProcessor) {

            return new StepBuilder("filterEventsStep", repository)
                    .<BatchEvent, BatchEvent>chunk(2, transactionManager)
                    .reader(eventReader)
                    .processor(eventProcessor)
                    .writer(chunk -> { /* Test writer không lưu dữ liệu */ })
                    .build();
        }

        @Bean
        Job filterEventsJob(JobRepository repository, Step filterEventsStep) {
            return new JobBuilder("filterEventsJob", repository)
                    .start(filterEventsStep)
                    .build();
        }
    }
}
```

Test này xác nhận số lượng item đi qua các giai đoạn, không xác nhận transaction commit ra bảng nghiệp vụ vì writer đang rỗng. Khi kiểm thử output thực, thay writer bằng writer ghi dữ liệu thử và assert bản ghi `boundary`, `recent` có mặt, `old` không có. Dùng database hỗ trợ transaction nếu cần kiểm chứng rollback/commit.

`@StepScope` trên reader giúp tránh giữ vị trí đọc cũ khi context được dùng lại cho nhiều execution. Tuy nhiên, việc mỗi run có reader mới không giải quyết lỗi tạo fixture từ `Instant.now()`: **tất cả mốc trong fixture vẫn phải cố định**.

Lưu ý về phiên bản: Spring Batch 5 dùng API `new StepBuilder(name, jobRepository)` và `.chunk(size, transactionManager)`. Với Spring Batch 6 hoặc ứng dụng có cấu hình Batch riêng, cần điều chỉnh import/bootstrap theo phiên bản thực tế.

## 5. Ngày nghiệp vụ nên là `JobParameters` ổn định

Với batch chạy theo ngày, câu hỏi quan trọng thường không phải “bây giờ là lúc nào?” mà là **“job đang xử lý ngày nghiệp vụ nào?”**.

Ví dụ job chạy lúc 01:00 ngày 13/05 để tổng hợp giao dịch ngày 12/05. Nếu reader tự gọi `LocalDate.now()`, chạy lại job vào 14/05 sẽ âm thầm đổi tập dữ liệu. Thay vào đó, tạo tham số định danh:

```java
import java.time.LocalDate;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

LocalDate businessDate = LocalDate.of(2025, 5, 12);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .toJobParameters();
```

Với `JobLauncher`, truyền `parameters` vào lúc launch. Với `JobLauncherTestUtils`, cũng có overload `launchJob(parameters)` hoặc `launchStep("stepName", parameters)`.

`.addString(..., true)` đánh dấu `businessDate` là **identifying parameter**, tham gia xác định `JobInstance`. Khi restart một job instance chưa hoàn tất, giữ nguyên ngày nghiệp vụ. Nếu job đã `COMPLETED`, chạy lại với cùng tập identifying parameters thường bị Spring Batch từ chối; đây là cơ chế kiểm soát vòng đời job, không phải lý do để thay ngày bằng đồng hồ thật trong test.

### 5.1. Đọc ngày vào bean step-scoped

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public ListItemReader<BatchEvent> datedEventReader(
        @Value("#{jobParameters['businessDate']}")
        String businessDateText) {

    LocalDate businessDate = LocalDate.parse(businessDateText);

    // Trả về dữ liệu mẫu hoặc dữ liệu đã query cho đúng businessDate.
    return new ListItemReader<>(
            fixtureEventsFor(businessDate)
    );
}
```

`fixtureEventsFor(...)` ở đây là hàm giả định trả về tập event theo ngày, để làm rõ cách truyền tham số. Trong test ứng dụng thực, thay bằng reader/query/fixture tương ứng. Nếu tham số thiếu hoặc sai dạng ISO-8601 (`yyyy-MM-dd`), nên để parse thất bại rõ ràng hoặc validate tại đầu job.

### 5.2. Tính khoảng ngày trong một múi giờ được chỉ định

Nếu đọc tất cả giao dịch của `2025-05-12` theo giờ Việt Nam, đừng dùng `LocalDateTime` trần rồi so với timestamp UTC. Tạo khoảng nửa mở `[startInclusive, endExclusive)`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.parse("2025-05-12");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
```

Khi truy vấn SQL, dùng điều kiện:

```sql
WHERE created_at >= :startInclusive
  AND created_at < :endExclusive
```

Khoảng nửa mở loại trừ khả năng đếm trùng sự kiện nằm đúng 00:00 của ngày tiếp theo, đồng thời tránh kiểu mốc `23:59:59.999` phụ thuộc độ chính xác cột database. Ở múi giờ có DST, một ngày lịch có thể dài 23 hoặc 25 giờ, nên không mặc định cộng `Duration.ofHours(24)` để lấy đầu ngày kế tiếp.

## 6. Kiểm thử thời điểm biên, múi giờ và DST

Một bộ test về thời gian cần chứa ví dụ ở ranh giới thực, thay vì chỉ một ngày “bình thường”.

| Trường hợp | Dữ liệu đầu vào | Kỳ vọng cần kiểm chứng |
|---|---|---|
| Trước cutoff | `2025-05-09T23:59:59Z` | Bị loại nếu cutoff là `2025-05-10T00:00:00Z` |
| Đúng cutoff | `2025-05-10T00:00:00Z` | Được giữ với điều kiện `isBefore` |
| Sau cutoff | `2025-05-10T00:00:01Z` | Được giữ |
| Đổi ngày ở múi giờ nghiệp vụ | Một `Instant` tương ứng 00:30 tại Việt Nam | Ngày nghiệp vụ là ngày mới, dù UTC có thể vẫn là ngày trước |
| DST tại múi giờ có chuyển giờ | Ngày 30/03/2025 ở `Europe/Paris` | Khoảng ngày có 23 giờ |
| Cuối tháng, cuối năm | 31/12 → 01/01; năm nhuận 29/02 | Khoảng ngày và tên partition đúng |
| Job restart nhiều ngày sau | `businessDate` không đổi | Vẫn đọc đúng ngày ban đầu, không lấy “hôm nay” |

Ví dụ test chuyển giờ DST không dùng đợi thời gian thật:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class DayBoundaryTest {

    @Test
    void daylightSavingDayCanBe23Hours() {
        ZoneId zone = ZoneId.of("Europe/Paris");
        LocalDate day = LocalDate.of(2025, 3, 30);

        Instant start = day.atStartOfDay(zone).toInstant();
        Instant end = day.plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        assertEquals(Duration.ofHours(23), Duration.between(start, end));
    }
}
```

Nếu ứng dụng chỉ phục vụ Việt Nam, `Asia/Ho_Chi_Minh` không chuyển giờ theo DST; tuy vậy code dùng ngày địa phương có thể tái sử dụng cho thị trường khác, nên tính theo `ZoneId` và `LocalDate` vẫn là lựa chọn rõ ràng hơn hard-code “một ngày = 24 giờ”.

### Dùng UTC để lưu, dùng múi giờ nghiệp vụ để diễn giải

Thực hành hữu ích là lưu các thời điểm dưới dạng `Instant` / timestamp UTC, còn ngày hiển thị và khoảng ngày được tính theo `ZoneId` nghiệp vụ. Tránh phụ thuộc `TimeZone.getDefault()` hoặc việc máy CI cấu hình `TZ` khác máy phát triển. Việc sửa global timezone ngay trong test cũng dễ ảnh hưởng test chạy song song; nên truyền `ZoneId` như dependency.

## 7. Không dùng `Thread.sleep` để test scheduler hoặc đợi quá hạn

Giả sử có job tổng hợp dữ liệu được kích hoạt bằng `@Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")`. Một test dùng `Thread.sleep(...)` chờ đến đúng 01:00 không phù hợp: chậm, có thể treo CI và không kiểm tra trực tiếp quy tắc chọn ngày.

Thay vào đó, để scheduler chỉ là lớp kích hoạt mỏng; tách logic chọn ngày nghiệp vụ thành một service có `Clock` và `ZoneId`.

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class DailyBatchDatePolicy {

    private final Clock clock;
    private final ZoneId businessZone;

    public DailyBatchDatePolicy(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public LocalDate targetDate() {
        // Job chạy đầu ngày để xử lý dữ liệu của ngày trước.
        return LocalDate.now(clock.withZone(businessZone)).minusDays(1);
    }
}
```

Unit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class DailyBatchDatePolicyTest {

    @Test
    void shouldChoosePreviousBusinessDate() {
        Clock clock = Clock.fixed(
                // UTC 18:00 ngày 12/05 = 01:00 ngày 13/05 ở Việt Nam.
                Instant.parse("2025-05-12T18:00:00Z"),
                ZoneOffset.UTC
        );

        DailyBatchDatePolicy policy = new DailyBatchDatePolicy(
                clock,
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        assertEquals(LocalDate.of(2025, 5, 12), policy.targetDate());
    }
}
```

Khi triển khai, phương thức `@Scheduled` chỉ gọi `batchLauncher.launch(policy.targetDate())`. Unit test kiểm tra đúng việc tính ngày; integration test riêng có thể kiểm tra adapter thực sự gọi launcher với tham số mong đợi. **`Clock.fixed` không tự điều khiển cơ chế kích hoạt của `@Scheduled`**: scheduling framework có đồng hồ và bộ lập lịch riêng.

Tương tự, nếu job có retry, backoff hoặc timeout, hãy kiểm tra điều kiện và kết quả retry qua cấu hình/policy thích hợp. Không assert rằng một công đoạn chắc chắn mất chính xác X mili-giây trên máy CI. Với xử lý bất đồng bộ, test có thể đợi một **điều kiện hoàn thành** với giới hạn thời gian hợp lý; điều đó khác với việc dùng thời gian thật làm **dữ liệu đầu vào quyết định nghiệp vụ**.

## 8. Time window, restart và dữ liệu nhất quán trong cả execution

Một vấn đề khó phát hiện xuất hiện khi batch bắt đầu lúc 23:59:59 và đọc dữ liệu qua 00:00:01:

```text
23:59:59 — item đầu tiên được lọc theo "hôm nay" là ngày 12
00:00:00 — ngày lịch đổi
00:00:01 — item tiếp theo được lọc theo "hôm nay" là ngày 13
```

Nếu item trong cùng execution dùng hai cửa sổ khác nhau thì output trở nên khó giải thích và restart có thể cho kết quả khác. Có hai cách phổ biến:

**Cách A — Dùng `businessDate` xác định từ lúc launch.** Reader và processor lấy ngày từ `JobParameters` và tính `startInclusive` / `endExclusive` một lần. Đây thường là lựa chọn rõ nhất cho batch chạy theo ngày.

**Cách B — Chụp một `Instant` hoặc `cutoff` tại đầu step.** Dùng `StepExecutionListener.beforeStep(...)` lưu chuỗi ISO vào `StepExecution.getExecutionContext()`, sau đó các thành phần đọc lại cùng giá trị. Ví dụ:

```java
import java.time.Clock;
import java.time.Duration;

import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class CutoffInitializer implements StepExecutionListener {

    private final Clock clock;

    public CutoffInitializer(Clock clock) {
        this.clock = clock;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String cutoff = clock.instant()
                .minus(Duration.ofHours(48))
                .toString();

        stepExecution.getExecutionContext()
                .putString("event.cutoff", cutoff);
    }
}
```

Khi dùng `ExecutionContext`, cần xét thời điểm metadata được persist và quy tắc restart. Nếu cửa sổ phải giữ nguyên **qua mọi lần restart của cùng một job instance**, đưa ngày/cutoff vào identifying `JobParameters` ngay từ đầu sẽ dễ bảo đảm ngữ nghĩa hơn việc tính lại từ đồng hồ ở `beforeStep`.

Trong unit test `CutoffInitializer`, tạo `StepExecution` bằng `MetaDataInstanceFactory.createStepExecution()`, inject `Clock.fixed(...)`, gọi `beforeStep` và assert chuỗi cutoff chính xác. Trong integration test, đăng ký `.listener(...)` rồi chạy step để xác nhận việc wiring và dữ liệu có thể đọc từ execution context.

## 9. Khi nguồn thời gian nằm ngoài code Java

Inject `Clock` giúp kiểm soát phần code chủ động dùng đồng hồ này. Nó **không đóng băng tất cả thời gian trong hệ thống**.

### 9.1. SQL `NOW()` hoặc `CURRENT_TIMESTAMP`

Ví dụ, câu query:

```sql
SELECT *
FROM orders
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '2 days'
```

vẫn phụ thuộc đồng hồ database; `Clock.fixed` của Java không tác động đến `CURRENT_TIMESTAMP`. Khi có thể, tính cutoff ở Java rồi truyền vào query:

```sql
SELECT *
FROM orders
WHERE created_at >= :cutoffInstant
```

Test đặt `:cutoffInstant` cố định và seed dữ liệu với timestamp cụ thể. Cú pháp kiểu `INTERVAL` khác nhau giữa các hệ quản trị, nhưng ý tưởng truyền tham số thời gian là độc lập database.

Nếu nghiệp vụ bắt buộc dựa trên thời gian database, hãy cô lập logic trong repository và test trên database phù hợp, bằng dữ liệu/transaction có thể kiểm soát. Đừng khẳng định DB đang theo fixed clock của JVM.

### 9.2. Timestamp do Spring Batch tạo

`JobExecution`, `StepExecution` và metadata trong `JobRepository` có các thời điểm hệ thống tự tạo. Test thường nên xác nhận job/step có trạng thái hợp lệ, metadata hiện diện theo vòng đời và các counter đúng. Tránh assert metadata phải đúng bằng `clock.instant()` từ bean nghiệp vụ hoặc chênh nhau “dưới 1 ms”.

### 9.3. Dịch vụ ngoài, file và message

Nếu API trả về `expiresAt` hoặc file chứa timestamp, fixture/mock phải trả giá trị cố định. Nếu hệ thống ngoài tự quyết định hết hạn bằng đồng hồ của nó, mock việc kiểm tra trong unit test và bổ sung integration test theo contract dịch vụ; đừng cố làm đồng hồ Java đại diện cho tất cả hệ thống.

Với Kafka/event stream, phân biệt **event time** do bản ghi mang theo và **processing time** khi batch nhận được bản ghi. Fixture nên ghi rõ cả hai khi logic phụ thuộc hai mốc này.

## 10. Các anti-pattern làm test dễ “flaky”

| Anti-pattern | Vấn đề | Cách thay thế |
|---|---|---|
| `LocalDate.now()` trong fixture tạo test data | Ngày đổi theo lúc chạy | Ghi `LocalDate.of(2025, 5, 12)` |
| `new Date()` trong test rồi so với `new Date()` trong code | Hai phép gọi dùng hai thời điểm | Inject `Clock.fixed` và assert một mốc |
| `Thread.sleep(1000)` để chờ item hết hạn | Chậm, phụ thuộc tải CI | Dùng hai fixed clock trong hai test riêng |
| `Thread.sleep(...)` để chờ job xong | Không đảm bảo tác vụ đã hoàn tất | Launcher đồng bộ hoặc đợi điều kiện kết thúc có timeout |
| Dùng `ZoneId.systemDefault()` để tính ngày nghiệp vụ | Phụ thuộc timezone máy | Inject `ZoneId` được cấu hình cụ thể |
| Dùng `LocalDateTime` cho timestamp UTC | Thiếu thông tin offset/zone | Dùng `Instant` hoặc `OffsetDateTime` theo ngữ nghĩa |
| Dùng `23:59:59.999` làm cuối ngày | Có thể sót dữ liệu có độ chính xác cao hơn | Khoảng `[start, nextDayStart)` |
| Chạy lại test batch đã `COMPLETED` cùng `JobParameters` | JobRepository chặn chạy lại JobInstance | Cô lập metadata hoặc dùng tham số run id test riêng |
| Recompute cutoff bằng `now()` cho từng item | Cửa sổ đổi khi job chạy dài | Chụp cutoff một lần hoặc truyền `businessDate` |
| Assert runtime phải bằng một số ms cố định | CPU/CI/scheduling biến động | Assert dữ liệu và trạng thái nghiệp vụ |

### Tránh phụ thuộc thời gian thật trong tên file và dữ liệu partition

Nếu batch tạo file `orders-YYYYMMDD.csv` hoặc ghi vào partition ngày, giá trị trong tên file phải lấy từ `businessDate` đã quyết định trước đó. Test nên assert `orders-20250512.csv` và đường dẫn test đã cô lập. Tránh tên file suy ra từ `LocalDate.now()` vì test có thể đổi output sau 0 giờ và restart vào ngày khác sẽ ghi nhầm partition.

### Phân biệt “dữ liệu cố định” với “môi trường hoàn toàn cố định”

Một test dùng `Clock.fixed` vẫn có thể không ổn định vì thứ tự đọc dữ liệu, test chạy song song, transaction isolation, mã sinh ngẫu nhiên hoặc race condition. Đồng hồ cố định giải quyết **một nguồn không xác định quan trọng**, còn các nguồn khác cần được kiểm soát riêng theo thiết kế.

## 11. Bài tập: kiểm thử job lưu trữ dữ liệu quá hạn

Giả sử job archive các invoice có `createdAt` **trước đầu ngày 12/05/2025 theo giờ Việt Nam**, còn invoice đúng lúc 00:00 ngày 12/05 vẫn giữ ở bảng hiện tại.

Yêu cầu thực hành:

1. Định nghĩa `businessDate=2025-05-12` từ `JobParameters` và `ZoneId.of("Asia/Ho_Chi_Minh")`; tính `cutoffInstant` từ đầu ngày nghiệp vụ.
2. Tạo test data với invoice trước cutoff 1 nano-giây, đúng cutoff và sau cutoff 1 nano-giây.
3. Unit test classifier/processor với cutoff cố định, không dùng `Instant.now()`.
4. Integration test chạy step bằng `JobLauncherTestUtils`, xác nhận chỉ bản ghi cũ được archive và các count trong `StepExecution` đúng logic thiết kế.
5. Chạy lại với cùng ngày nghiệp vụ nhưng execution test riêng; xác nhận không phải sửa tham số ngày theo “hôm nay” để test thành công.
6. Thử thêm ngày 30/03/2025 ở `Europe/Paris` để kiểm tra code dùng đầu ngày kế tiếp thay vì cộng cứng 24 giờ.

**Câu hỏi kiểm tra:** Nếu job đang chạy lúc 23:59 và kết thúc lúc 00:05, tập invoice được archive có nên thay đổi theo thời gian chạy không? Với batch archive theo ngày nghiệp vụ, câu trả lời mong đợi là **không**: cutoff cần được chốt từ ngày nghiệp vụ của job.

## 12. Tài liệu tham khảo

- [Java SE `Clock` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `systemUTC`, `fixed`, `offset` và các lựa chọn clock.
- [Java SE `LocalDate` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): phép toán ngày lịch và `atStartOfDay(ZoneId)`.
- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution` và identifying job parameters.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `StepScopeTestUtils`.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor` trả `null` để filter item.
