# DateTimeProvider và thời gian kiểm thử xác định

## 1. Tách nguồn thời gian khỏi logic auditing

Trong chương **Auditing** của module **SPRING_DATA_COMMONS**, các field như `createdAt` và `lastModifiedAt` thường được hạ tầng auditing tự gán.

Nếu kiểm thử so sánh chúng với một lần gọi `Instant.now()` khác, kết quả có thể chênh lệch vì hai lần đọc đồng hồ không diễn ra cùng lúc. Dùng `Thread.sleep(...)` để tạo khoảng cách giữa hai lần lưu cũng làm kiểm thử chậm và phụ thuộc môi trường.

`DateTimeProvider` cho phép cung cấp nguồn thời gian mà auditing sử dụng. Khi nối nó với `java.time.Clock`, ứng dụng có thể dùng đồng hồ thực trong production và đồng hồ được kiểm soát trong kiểm thử.

Mục tiêu không chỉ là làm assertion dễ viết. Kiểm thử cần phân biệt được:

- Thời gian tạo được gán khi entity mới được xử lý.
- Thời gian sửa được cập nhật khi có một lần thay đổi tiếp theo.
- Thời gian tạo không bị thay lại trong lần cập nhật.
- Giá trị được lưu và đọc lại đúng trong giới hạn độ chính xác của store.

Nguồn thời gian xác định giúp kiểm chứng các hành vi này mà không cần chờ thời gian thực trôi qua.

## 2. DateTimeProvider cung cấp gì?

Interface thuộc Spring Data Commons:

~~~java
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

public interface DateTimeProvider {

    Optional<TemporalAccessor> getNow();
}
~~~

Đây là chữ ký hợp đồng được trình bày để giải thích. Khi viết ứng dụng, dùng interface `org.springframework.data.auditing.DateTimeProvider` của thư viện, không tự tạo một interface cùng tên.

`getNow()` trả một giá trị thời gian nếu provider có thể cung cấp thời gian cho lần xử lý đó.

| Kết quả | Ý nghĩa cần hiểu |
| --- | --- |
| `Optional.of(instant)` | Có một giá trị thời gian để hạ tầng auditing sử dụng |
| `Optional.empty()` | Không cung cấp thời gian cho lần xử lý đó |
| `null` thay cho Optional | Vi phạm hợp đồng; không phải cách biểu diễn “không có thời gian” |

`Instant` triển khai `TemporalAccessor` nên phù hợp với hợp đồng này. Tuy nhiên, provider trả kiểu thời gian nào và field auditing nhận kiểu nào vẫn cần tương thích với cơ chế chuyển đổi của module.

### 2.1. Provider không tự lưu dữ liệu

`DateTimeProvider` chỉ là nguồn thời gian. Nó không:

- Tự tìm các field có `@CreatedDate`.
- Quyết định một entity mới hay đã tồn tại.
- Tự bật auditing.
- Tự ghi database hoặc mở transaction.

Các công việc đó thuộc metadata, auditing handler và điểm tích hợp lifecycle của store.

Luồng khái quát:

~~~mermaid
flowchart LR
    A["Điểm lifecycle có tích hợp auditing"] --> B["Auditing handler"]
    B --> C["DateTimeProvider.getNow()"]
    C --> D["Giá trị thời gian"]
    D --> E["Gán field auditing phù hợp"]
    E --> F["Pipeline persistence tiếp tục"]
~~~

Có bean provider chưa đủ; hạ tầng auditing thực tế phải được cấu hình sử dụng bean đó.

### 2.2. Thời gian và người thực hiện là hai nguồn riêng

`DateTimeProvider` cung cấp thời gian. `AuditorAware<T>` cung cấp thông tin người thực hiện theo hợp đồng auditing đồng bộ.

Trong hạ tầng reactive tương ứng, có thể có `ReactiveAuditorAware<T>` cho việc tìm auditor. Điều đó không làm `DateTimeProvider.getNow()` đổi thành phương thức trả `Mono`.

Nếu module reactive sử dụng provider này, phương thức lấy thời gian vẫn phải nhanh và không blocking. Không gọi mạng hoặc `block()` để lấy một timestamp trong provider.

## 3. Dùng Clock để kiểm soát thời gian

`Clock` là abstraction của Java cho nguồn thời gian và zone. Một provider dựa trên `Clock` có thể dùng cùng logic trong production và kiểm thử.

### 3.1. Implementation rõ kiểu thời gian

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.auditing.DateTimeProvider;

public final class ClockDateTimeProvider
        implements DateTimeProvider {

    private final Clock clock;

    public ClockDateTimeProvider(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.<TemporalAccessor>of(clock.instant());
    }
}
~~~

Mỗi lần `getNow()` được gọi, provider đọc đồng hồ được inject.

Không nên tính `clock.instant()` một lần trong constructor rồi giữ mãi kết quả đó nếu mục tiêu là dùng đồng hồ thực trong production.

### 3.2. Các loại Clock hữu ích

| Cách tạo | Hành vi | Mục đích |
| --- | --- | --- |
| `Clock.systemUTC()` | Đọc thời gian hệ thống, zone UTC | Nguồn thời gian thực cho ứng dụng |
| `Clock.fixed(t0, ZoneOffset.UTC)` | Luôn trả cùng Instant | Kiểm thử một mốc cố định |
| `Clock.offset(base, duration)` | Dịch thời gian của base clock | Mô phỏng một độ lệch có chủ đích |
| Clock điều chỉnh được trong test | Test chủ động đặt mốc hiện tại | Kiểm thử tạo ở t0, sửa ở t1 |

`Clock.offset(Clock.systemUTC(), ...)` vẫn phụ thuộc thời gian thực. Nó không tự làm kiểm thử xác định.

Nếu cần một mốc cố định có độ lệch, dùng một base clock cố định hoặc tính trực tiếp mốc `Instant` mong muốn.

### 3.3. UTC không phải thông tin zone nghiệp vụ

Khi provider dùng `clock.instant()`, kết quả là một thời điểm trên dòng thời gian.

`Clock.systemUTC()` không biến timestamp thành ngày lịch của mọi người dùng. Nó cũng không quyết định zone hiển thị của giao diện.

Ví dụ, cùng một `Instant` có thể được hiển thị theo `Asia/Ho_Chi_Minh` hoặc một vùng khác mà thời điểm không đổi.

Nếu field dùng `LocalDateTime` trong khi provider trả `Instant`, việc chuyển đổi có thể cần thêm quy tắc zone. Không nên suy ra dùng đồng hồ UTC đã loại bỏ mọi chuyển đổi ngầm ở các lớp tiếp theo.

Trong các ví dụ chính của bài, field auditing dùng `Instant` để giữ rõ ý nghĩa thời điểm.

## 4. Nối provider vào auditing của store

Cấu hình dưới đây minh họa phần auditing của một ứng dụng Spring Data JPA dùng Jakarta Persistence.

Nó giả định ứng dụng đã có JPA provider, datasource, entity/repository scanning và các phụ thuộc auditing tương ứng. Đây không phải cấu hình persistence đầy đủ.

~~~java
import java.time.Clock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true,
        setDates = true)
public class JpaAuditingConfiguration {

    @Bean("auditingClock")
    public Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean("auditingDateTimeProvider")
    public DateTimeProvider auditingDateTimeProvider(
            @Qualifier("auditingClock") Clock clock) {

        return new ClockDateTimeProvider(clock);
    }
}
~~~

`dateTimeProviderRef` chỉ rõ bean provider mà hạ tầng JPA auditing phải dùng. `@Qualifier` làm rõ clock được provider nhận khi ứng dụng có nhiều đồng hồ.

Chỉ thêm một bean `Clock.fixed(...)` vào test mà provider không sử dụng clock đó sẽ không đóng băng thời gian auditing.

Tương tự, tạo bean `DateTimeProvider` riêng nhưng cấu hình auditing vẫn trỏ đến nguồn khác thì assertion vẫn có thể nhận thời gian thực.

### 4.1. Entity minh họa

Khi áp dụng, mỗi public type trong bài được đặt trong một file Java riêng.

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class AuditNote {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected AuditNote() {
    }

    public AuditNote(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public void rename(String title) {
        this.title = title;
    }
}
~~~

Repository minh họa:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditNoteRepository
        extends JpaRepository<AuditNote, Long> {
}
~~~

`@Column(updatable = false)` là quy tắc mapping JPA cho cột thời gian tạo. Nó không thay thế auditing và không chứng minh handler không bao giờ sửa nhầm giá trị trong bộ nhớ.

Vì vậy, kiểm thử nên quan sát cả entity kết quả và dữ liệu đọc lại.

### 4.2. Các tùy chọn ảnh hưởng kỳ vọng

Trong ví dụ:

- `setDates = true` cho phép tự gán các field ngày giờ.
- `modifyOnCreate = true` cho phép gán cả thời gian sửa khi tạo mới.

Nếu chọn `modifyOnCreate = false`, không nên vẫn yêu cầu `lastModifiedAt` được gán như trong ví dụ tạo mới.

Nếu tắt việc gán ngày giờ, provider được cấu hình đúng cũng không có nghĩa field sẽ được cập nhật.

Các tùy chọn và annotation bật auditing thuộc module. Không chuyển nguyên `@EnableJpaAuditing` sang MongoDB hoặc R2DBC.

## 5. Kiểm thử đơn vị với một mốc cố định

Kiểm thử nhỏ sau kiểm tra provider sử dụng clock được truyền vào:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class ClockDateTimeProviderTest {

    @Test
    void returnsTheInstantFromTheInjectedClock() {
        Instant t0 =
                Instant.parse("2025-04-03T09:15:30.123Z");

        Clock clock = Clock.fixed(t0, ZoneOffset.UTC);
        ClockDateTimeProvider provider =
                new ClockDateTimeProvider(clock);

        assertEquals(Optional.of(t0), provider.getNow());
    }
}
~~~

Không cần ngủ, không cần sai số vài giây và không cần thay đổi đồng hồ hệ điều hành.

Kiểm thử này có phạm vi rõ: xác minh provider. Nó chưa chứng minh:

- Auditing đã được bật.
- Đúng provider được auditing handler sử dụng.
- Entity mới được nhận diện đúng.
- Field được lưu và đọc lại nguyên vẹn.

Những điểm đó cần kiểm chứng ở đường tích hợp phù hợp.

## 6. Điều chỉnh thời gian trong test mà không chờ thời gian thực

`Clock.fixed(...)` phù hợp cho một mốc cố định. Để kiểm thử tạo ở `t0` rồi sửa ở `t1` trong cùng context, có thể dùng một clock điều chỉnh được dành cho test.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public AdjustableClock(Instant initial, ZoneId zone) {
        this(
                new AtomicReference<>(
                        Objects.requireNonNull(initial, "initial")),
                zone);
    }

    private AdjustableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {

        this.current = current;
        this.zone = Objects.requireNonNull(zone, "zone");
    }

    public void setInstant(Instant instant) {
        current.set(Objects.requireNonNull(instant, "instant"));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(current, zone);
    }
}
~~~

Các clock được tạo bởi `withZone(...)` trong implementation này cùng nhìn một nguồn Instant có thể điều chỉnh. Đổi zone không tự dịch thời điểm.

Đây là công cụ kiểm thử. Production không cần một API để test tùy ý đặt lại “hiện tại”.

`AtomicReference` giúp việc đọc và đặt mốc nhất quán ở mức biến tham chiếu. Nó không giải quyết việc hai test đồng thời cùng thay đổi một clock dùng chung.

Cần giữ instance theo phạm vi test phù hợp và đặt lại mốc ở đầu mỗi test. Không dùng một biến static mutable làm nguồn thời gian cho toàn bộ bộ kiểm thử.

## 7. Cấu hình test dùng cùng implementation provider

Ví dụ tích hợp dưới đây dùng Spring Boot 3 test slice và JUnit 5. Nếu dự án dùng bộ test hoặc package annotation khác, điều chỉnh phần hạ tầng test tương ứng.

Cấu hình test vẫn tạo `ClockDateTimeProvider` như production, chỉ thay nguồn `Clock`:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@TestConfiguration
@EnableJpaAuditing(
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true,
        setDates = true)
public class JpaAuditingTestConfiguration {

    @Bean("auditingClock")
    public AdjustableClock auditingClock() {
        return new AdjustableClock(
                Instant.EPOCH, ZoneOffset.UTC);
    }

    @Bean("auditingDateTimeProvider")
    public DateTimeProvider auditingDateTimeProvider(
            @Qualifier("auditingClock") AdjustableClock clock) {

        return new ClockDateTimeProvider(clock);
    }
}
~~~

Cấu hình này dành cho context kiểm thử chỉ nạp cấu hình auditing tương ứng này.

Không import đồng thời nguyên cấu hình production có cùng bean name và cùng annotation bật auditing. Cần chọn rõ cấu hình nào được nạp, thay vì dựa vào thứ tự ghi đè bean.

Nếu test của dự án đã bật auditing qua một cấu hình khác, có thể giữ cấu hình đó và thay nguồn thời gian theo cơ chế test của dự án. Mục tiêu vẫn là kiểm chứng đường đi:

~~~text
auditing handler → provider đã chọn → clock kiểm thử
~~~

Chỉ đánh dấu một clock khác bằng `@Primary` chưa chắc thay được clock đã được chọn bằng `@Qualifier("auditingClock")`.

Tên bean, qualifier và `dateTimeProviderRef` phải nhất quán.

## 8. Kiểm thử tạo và cập nhật với hai mốc cụ thể

Kiểm thử sau giả định `AuditNote` và repository đã được test slice phát hiện, provider JPA hỗ trợ mapping `Instant` và database giữ được phần mili giây trong ví dụ.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(JpaAuditingTestConfiguration.class)
class AuditNoteAuditingTest {

    @Autowired
    private AuditNoteRepository repository;

    @Autowired
    private AdjustableClock auditingClock;

    @Autowired
    private EntityManager entityManager;

    @Test
    void keepsCreationTimeAndUpdatesModificationTime() {
        Instant t0 =
                Instant.parse("2025-04-03T09:15:30.123Z");

        Instant t1 = t0.plusSeconds(120);

        auditingClock.setInstant(t0);

        AuditNote created =
                repository.saveAndFlush(
                        new AuditNote("Initial title"));

        Long id = created.getId();

        assertEquals(t0, created.getCreatedAt());
        assertEquals(t0, created.getLastModifiedAt());

        entityManager.clear();

        AuditNote stored = repository.findById(id)
                .orElseThrow(AssertionError::new);

        assertEquals(t0, stored.getCreatedAt());
        assertEquals(t0, stored.getLastModifiedAt());

        auditingClock.setInstant(t1);
        stored.rename("Revised title");

        AuditNote updated = repository.saveAndFlush(stored);

        assertEquals(t0, updated.getCreatedAt());
        assertEquals(t1, updated.getLastModifiedAt());

        entityManager.clear();

        AuditNote reloaded = repository.findById(id)
                .orElseThrow(AssertionError::new);

        assertEquals("Revised title", reloaded.getTitle());
        assertEquals(t0, reloaded.getCreatedAt());
        assertEquals(t1, reloaded.getLastModifiedAt());
    }
}
~~~

Kết quả cần chứng minh:

| Giai đoạn | createdAt | lastModifiedAt |
| --- | --- | --- |
| Tạo mới ở t0 | t0 | t0 theo cấu hình modifyOnCreate |
| Đọc lại sau tạo | t0 | t0 |
| Sửa ở t1 | Giữ t0 | t1 |
| Đọc lại sau sửa | Giữ t0 | t1 |

Hai mốc cách nhau hai phút về mặt giá trị, nhưng test không phải chờ hai phút.

### 8.1. Vì sao cần thay đổi một field nghiệp vụ?

Trong JPA, lifecycle update liên quan đến việc persistence context phát hiện thay đổi và thực hiện flush.

Nếu chỉ gọi save một entity không thay đổi, không nên mặc định provider sẽ tạo một lần update và gọi auditing như mong muốn.

`stored.rename("Revised title")` tạo một thay đổi rõ ràng. Điều này giúp test kiểm chứng lần cập nhật thực sự, thay vì phụ thuộc một câu lệnh update không được bảo đảm xuất hiện.

### 8.2. Vì sao dùng flush và clear?

`save` không phải lúc nào cũng đồng nghĩa mọi bước SQL đã diễn ra ngay tại dòng gọi.

`saveAndFlush` buộc thực hiện flush ở ranh giới test mong muốn. `entityManager.clear()` loại entity đang được quản lý khỏi persistence context để lần tìm tiếp theo không chỉ trả lại cùng object trong bộ nhớ.

Nhờ đó, test phân biệt được:

- Auditing đã cập nhật entity.
- Dữ liệu đọc lại phản ánh cách persistence lưu và chuyển đổi giá trị.

Flush không đồng nghĩa commit. Test slice có thể vẫn chạy trong transaction sẽ rollback ở cuối test. Ví dụ này không kiểm chứng thời gian commit hoặc một listener after-commit.

### 8.3. Đặt mốc trước điểm auditing thực sự chạy

Mốc thời gian cần được đặt trước save/flush hoặc subscription tương ứng, tùy đường persistence.

Nếu tạo một publisher reactive ở `t0` nhưng subscribe sau khi đã đặt clock sang `t1`, không thể mặc định auditing phải nhận `t0`. Nó có thể đọc provider khi pipeline thực sự xử lý entity.

Tương tự, đặt clock sang `t1` trước khi lần flush đầu tiên xảy ra có thể khiến test không còn mô tả việc “tạo ở t0” như dự định.

Kiểm thử phải kiểm soát cả nguồn thời gian và ranh giới thực thi.

## 9. Những assertion dễ tạo ra kết quả sai

### 9.1. So sánh với một lần Instant.now khác

Mẫu dễ chập chờn:

~~~java
repository.save(entity);
assertEquals(Instant.now(), entity.getCreatedAt());
~~~

Lần gọi auditing và lần gọi assertion có thể nhận hai Instant khác nhau.

Một assertion “chênh không quá vài giây” có thể hữu ích trong một kiểm tra smoke về thời gian thực, nhưng không chứng minh auditing sử dụng đúng provider kiểm thử.

Với kiểm thử hành vi cần xác định, nên cung cấp mốc cụ thể và so đúng theo hợp đồng độ chính xác.

### 9.2. Dùng cùng mốc cho cả tạo và sửa

Nếu clock luôn cố định ở `t0`, test có thể thấy `lastModifiedAt == t0` sau cập nhật dù field chưa được cập nhật lần nào.

Dùng `t1` khác `t0` giúp phát hiện đường cập nhật không chạy.

### 9.3. Kiểm tra đúng số lần gọi provider

Một test gắn chặt vào “getNow phải được gọi đúng một lần” thường kiểm tra chi tiết điều phối hơn là yêu cầu dữ liệu.

Số lần gọi có thể thay đổi theo số entity, điểm lifecycle, lần flush và đường thực thi.

Nếu hợp đồng quan trọng là giá trị ngày giờ, hãy xác minh field và dữ liệu đọc lại. Chỉ kiểm tra số lần gọi khi đó thực sự là một yêu cầu thiết kế riêng.

### 9.4. Mock liên tiếp theo thứ tự gọi

Mẫu mock “lần đầu trả t0, lần thứ hai trả t1” có thể bị sai nếu framework gọi provider thêm một lần.

Clock điều chỉnh theo từng giai đoạn test thường thể hiện ý định tốt hơn: mọi lần đọc trong giai đoạn tạo đều thấy `t0`, mọi lần đọc trong giai đoạn sửa đều thấy `t1`.

## 10. Optional.empty không phải một timestamp mặc định

Provider có thể trả `Optional.empty()`. Điều đó có nghĩa nó không cung cấp một giá trị thời gian cho lần xử lý auditing đó.

Không hiểu kết quả này là:

- Tự dùng epoch.
- Tự dùng thời gian database.
- Tự xóa các field ngày giờ.
- Tắt mọi phần auditing, gồm cả thông tin người thực hiện.

Nếu một field đã có giá trị, không có thời gian mới không đồng nghĩa field phải bị đặt thành null. Hành vi gán cụ thể vẫn theo handler và đường tích hợp.

Nếu field bắt buộc ở schema nhưng entity mới không nhận được ngày giờ, lần ghi có thể thất bại do ràng buộc dữ liệu.

Với nguồn `Clock` thông thường, provider trong bài luôn trả một Instant. Chỉ dùng kết quả rỗng khi đó là một lựa chọn có ý nghĩa và đã được kiểm chứng, không dùng nó để che lỗi cấu hình clock.

## 11. Độ chính xác lưu trữ phải nằm trong kỳ vọng test

`Instant` có thể mang nano giây. Store, driver hoặc converter không nhất thiết giữ toàn bộ phần lẻ.

Ví dụ qua cầu nối `java.util.Date`:

~~~java
import java.time.Instant;
import java.util.Date;

Instant source =
        Instant.parse("2025-04-03T09:15:30.123456789Z");

Instant restored = Date.from(source).toInstant();
~~~

Ở phép chuyển đổi này, `restored` là:

~~~text
2025-04-03T09:15:30.123Z
~~~

Đây là mất độ chính xác nhỏ hơn mili giây, không phải đồng hồ kiểm thử chạy sai.

Đối với cột SQL, database document hoặc một kiểu lưu trữ khác, cần biết giới hạn và quy tắc cắt hay làm tròn thực tế.

Có ba cách xử lý hợp lý tùy mục tiêu:

1. Chọn mốc test nằm đúng trên độ chính xác được bảo toàn, như phần mili giây trong ví dụ.
2. Chuẩn hóa kỳ vọng theo hợp đồng chuyển đổi đã xác định.
3. Dùng độ chính xác cao hơn nếu nghiệp vụ thực sự yêu cầu và toàn bộ đường persistence hỗ trợ.

Không tự thêm sai số vài giây chỉ để mọi assertion đều qua. Sai số rộng có thể che việc dùng nhầm nguồn thời gian hoặc sai zone.

Nếu hợp đồng là cắt phần nhỏ hơn mili giây, có thể dùng `truncatedTo(ChronoUnit.MILLIS)` cho kỳ vọng. Không áp dụng máy móc cách này cho một store làm tròn hoặc có quy tắc khác.

Cũng cần phân biệt entity trong bộ nhớ trước khi đọc lại với dữ liệu thực sự được lưu. Entity có thể còn giữ phần nano giây mà database đã giảm độ chính xác.

## 12. Những nguồn thời gian DateTimeProvider không kiểm soát

Một clock kiểm thử chỉ kiểm soát những lời gọi đi qua nó.

| Nguồn | Provider trong bài có kiểm soát không? |
| --- | --- |
| `clock.instant()` trong ClockDateTimeProvider | Có |
| Lời gọi `Instant.now()` trực tiếp ở một service khác | Không |
| Default `CURRENT_TIMESTAMP` của database | Không |
| Trigger database tự cập nhật timestamp | Không |
| Thời điểm transaction commit | Không |
| Thời điểm hệ thống bên ngoài nhận thông báo | Không |
| Đồng hồ dùng để đo timeout hoặc scheduler khác | Không, nếu chưa được nối riêng |
| Thông tin người dùng từ AuditorAware | Không; đó là nguồn dữ liệu khác |

Nếu database và application cùng gán một field, cần xác định bên nào sở hữu giá trị.

Một field được auditing gán bằng `t0` nhưng trigger ghi đè bằng thời gian database sẽ không được kiểm thử đầy đủ chỉ bằng assertion trên entity trước khi đọc lại.

Nếu chủ động dùng timestamp do database sinh, hãy kiểm thử cơ chế đó theo hợp đồng của database. Không yêu cầu DateTimeProvider điều khiển một nguồn thời gian ngoài phạm vi của nó.

### 12.1. Thời gian auditing không tự là thời gian nghiệp vụ

`createdAt` do auditing gán thường nói về thời điểm entity đi qua điểm auditing của ứng dụng.

Một dữ liệu nhập từ hệ thống khác có thể có:

~~~text
occurredAt: thời điểm sự kiện gốc xảy ra
createdAt: thời điểm bản ghi được ứng dụng tạo
~~~

Hai field có thể khác nhau một cách hợp lệ.

Không ép một DateTimeProvider toàn cục trả thời gian sự kiện của từng bản ghi nếu đó là dữ liệu nghiệp vụ cần được giữ riêng.

Tương tự, timestamp auditing không phải số thứ tự đơn điệu. Đồng hồ thực có thể được điều chỉnh, nhiều entity có thể cùng timestamp và một transaction có thể hoàn tất theo thứ tự khác với lúc lấy thời gian.

## 13. Entity mới, lifecycle và phạm vi store

Nguồn thời gian đúng vẫn chưa đủ nếu hạ tầng xử lý entity như một trạng thái khác với kỳ vọng.

### 13.1. Nhận diện entity mới

Việc gán created date phụ thuộc đường auditing dành cho tạo mới hoặc cập nhật.

Nhận diện mới có thể liên quan ID, version, `Persistable` hoặc cơ chế của store. Không áp dụng quy tắc “ID khác null luôn là bản ghi cũ” cho mọi mô hình.

Nếu test đã gán ID cho entity nhưng store vẫn cần một chiến lược is-new riêng, phải cấu hình rõ. DateTimeProvider không sửa được lỗi phân loại đó.

### 13.2. API ghi trực tiếp có thể bỏ qua auditing

Một update SQL, JPQL bulk update hoặc đường driver trực tiếp có thể không đi qua entity listener/callback giống `save(entity)`.

Clock cố định không làm callback xuất hiện ở một đường thao tác vốn không tích hợp auditing.

Nếu ứng dụng có các đường cập nhật này, cần quyết định cách gán audit field cho từng đường, hoặc dùng một cơ chế dữ liệu khác phù hợp.

### 13.3. Cấu hình theo module

| Module | Điểm cần kiểm tra |
| --- | --- |
| Spring Data Commons | Hợp đồng DateTimeProvider và auditing infrastructure dùng chung |
| Spring Data JPA | Bật JPA auditing, đăng ký entity listener và quan sát thời điểm flush |
| Spring Data MongoDB | Bật auditing của module, kiểm tra callback mapping và kiểu thời gian lưu |
| Spring Data JDBC | Kiểm tra auditing theo aggregate và đường ghi của module |
| Spring Data R2DBC | Kiểm tra auditing reactive và thời điểm pipeline thực sự chạy |
| Module khác | Đối chiếu cơ chế bật auditing, kiểu field và đường lifecycle được hỗ trợ |

Không sao chép một test JPA dùng `EntityManager.clear()` sang MongoDB hay R2DBC. Mỗi store cần cách kiểm chứng đọc lại và ranh giới thực thi tương ứng.

Điểm có thể dùng chung là provider dựa trên `Clock` và ý tưởng tạo ở `t0`, sửa ở `t1`.

## 14. Tính độc lập của kiểm thử

Một clock có thể điều chỉnh là trạng thái mutable có chủ đích. Cần giới hạn nó để test không ảnh hưởng lẫn nhau.

Các nguyên tắc hữu ích:

- Đặt lại mốc ở đầu mỗi test.
- Không cho hai test song song điều khiển cùng một clock nếu chưa tách phạm vi.
- Không thay múi giờ mặc định hoặc đồng hồ hệ điều hành để kiểm thử provider.
- Không để fixture vô tình gọi save trước khi test đặt mốc mong muốn.
- Hoàn tất lần persistence thứ nhất ở ranh giới cần thiết trước khi đổi sang mốc thứ hai.

Nếu context Spring được tái sử dụng giữa các test, bean clock cũng có thể được tái sử dụng. Rollback dữ liệu không tự khôi phục trạng thái của clock.

Vì vậy, reset dữ liệu và reset nguồn thời gian là hai việc riêng.

Với publisher chạy bất đồng bộ, không đặt clock sang mốc mới khi công việc của giai đoạn cũ vẫn còn chạy mà test lại kỳ vọng nó dùng mốc cũ.

## 15. Liên hệ với repository và truy vấn

Auditing tự gán timestamp ảnh hưởng dữ liệu được query, không chỉ các assertion sau save.

### 15.1. Sắp xếp và phân trang

Một test cố định clock có thể tạo nhiều bản ghi cùng `createdAt`. Đây là tình huống hợp lệ giúp phát hiện việc phân trang phụ thuộc một khóa sort không duy nhất.

Nếu cần thứ tự ổn định, thiết kế thêm khóa phân biệt phù hợp, chẳng hạn ID theo khả năng sắp xếp của store.

Không dịch clock một lượng nhỏ cho từng bản ghi chỉ để che việc ứng dụng chưa có hợp đồng thứ tự ổn định.

### 15.2. Derived query theo khoảng thời gian

Với query dạng “được tạo từ t0 đến trước t1”, hãy đặt mốc dữ liệu kiểm thử rõ ràng và kiểm tra các giá trị đúng ở biên.

Provider kiểm soát thời điểm được gán cho dữ liệu. Nó không tự sửa toán tử biên trong tên derived query hoặc câu truy vấn.

Nếu query dựa trên ngày của người dùng, vẫn cần chuyển ngày đó thành khoảng thời gian theo zone nghiệp vụ trước khi so với `Instant`.

### 15.3. Query by Example và projection

Một probe tái sử dụng từ entity đã lưu có thể chứa các field auditing không null. Nếu không có chủ đích đối sánh chúng, cần cấu hình matcher hoặc xây probe phù hợp.

Một projection hiển thị ngày giờ theo zone người dùng cũng không làm thay đổi `Instant` lưu trong field auditing.

Không nên thay provider theo múi giờ hiển thị chỉ để DTO trông đúng. Giữ nguồn thời điểm và chuyển đổi trình bày thành các trách nhiệm riêng.

## 16. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Khả năng cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Vẫn nhận thời gian thực dù test có Clock.fixed | Auditing không dùng provider hoặc clock đó | Kiểm tra dateTimeProviderRef, bean name và qualifier |
| Field ngày giờ luôn null | Chưa bật auditing, thiếu listener/callback, tắt setDates hoặc provider rỗng | Kiểm tra cả đường tích hợp, không chỉ provider |
| lastModifiedAt null khi tạo | modifyOnCreate tắt hoặc đường tạo chưa đúng | Đối chiếu cấu hình và hợp đồng test |
| lastModifiedAt không đổi khi sửa | Entity chưa dirty, chưa flush hoặc update bỏ qua auditing | Tạo thay đổi thật và kiểm tra điểm thực thi |
| createdAt bị coi như mới trong lần cập nhật | Nhận diện entity mới không đúng | Kiểm tra ID, version và chiến lược is-new |
| Đúng trong entity nhưng sai sau đọc lại | Độ chính xác, converter hoặc database ghi đè | Kiểm tra giá trị lưu thực tế và nguồn sở hữu field |
| Test chạy riêng đúng, chạy chung sai | Clock mutable hoặc fixture dùng chung chưa reset | Cô lập trạng thái và kiểm soát thực thi song song |
| Reactive nhận t1 dù publisher được tạo ở t0 | Auditing đọc clock khi publisher thực thi | Đặt mốc theo ranh giới subscription cần kiểm chứng |
| Thêm Primary không thay clock | Provider đang chọn bean bằng qualifier cụ thể | Thay đúng dependency mà provider dùng |
| Trigger timestamp không theo mốc test | Nguồn thời gian nằm trong database | Kiểm thử cơ chế database riêng |

Đừng khắc phục lỗi bằng cách thêm sleep hoặc mở rộng sai số trước khi xác định nguồn thời gian thực sự đang được sử dụng.

Một chuỗi kiểm tra rõ ràng là:

~~~text
Auditing có chạy không?
Đúng provider có được chọn không?
Provider có đọc đúng clock không?
Mốc được đặt trước điểm thực thi chưa?
Dữ liệu lưu có bảo toàn độ chính xác đã cam kết không?
~~~

Các ví dụ và mã kiểm thử trong bài là tài liệu minh họa. Chúng không phải báo cáo đã chạy test hoặc xác nhận một cấu hình store cụ thể.

## 17. Tự kiểm tra kiến thức

**DateTimeProvider có tự bật auditing không?**

Không. Nó chỉ cung cấp thời gian. Module phải bật auditing và sử dụng provider đó trong đường lifecycle phù hợp.

**Vì sao chỉ thêm Clock.fixed vào context có thể chưa đủ?**

Vì provider có thể chưa nhận clock đó hoặc auditing handler đang dùng provider khác.

**Tại sao cần hai mốc t0 và t1?**

Để phân biệt việc tạo thời gian ban đầu với cập nhật thời gian sửa. Một mốc cố định duy nhất có thể che lỗi không cập nhật.

**Optional.empty có nghĩa là dùng thời gian database không?**

Không. Nó chỉ biểu thị provider không cung cấp thời gian cho lần xử lý đó.

**Clock cố định có kiểm soát CURRENT_TIMESTAMP hoặc trigger không?**

Không. Chúng là nguồn thời gian riêng của database.

**Flush và clear có chứng minh transaction đã commit không?**

Không. Chúng giúp kiểm chứng đường lưu và đọc lại trong phạm vi transaction, không thay thế kiểm chứng commit.

**Nguồn thời gian xác định có bảo đảm thứ tự duy nhất của bản ghi không?**

Không. Nhiều bản ghi có thể cùng timestamp. Query và phân trang vẫn cần khóa thứ tự phù hợp.

**Điều gì cần nhớ khi áp dụng trong Spring Data Commons?**

Tách nguồn thời gian thành một dependency rõ ràng, nối nó đúng vào auditing của store và kiểm thử giá trị qua các giai đoạn thực thi cụ thể. Sau đó đối chiếu độ chính xác, nhận diện entity mới và những đường ghi có thể bỏ qua auditing.
