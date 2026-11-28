# DateTimeProvider, múi giờ và thời gian kiểm thử xác định

Bài học này thuộc chương **Auditing** của module **SPRING_DATA_NEO4J**. Khi Spring Data Neo4j ghi một entity, auditing có thể tự điền thời điểm tạo và cập nhật thông qua `@CreatedDate` và `@LastModifiedDate`. Nguồn thời gian được cung cấp bởi `DateTimeProvider`, một SPI của Spring Data Commons. Việc chọn nguồn thời gian và kiểu dữ liệu thời gian quyết định audit có nhất quán giữa các môi trường hay không và có thể kiểm thử chính xác hay không.

Một cấu hình phù hợp cho timestamp audit thường dùng `Instant` và một `Clock` được inject. Ứng dụng production dùng `Clock.systemUTC()`, còn kiểm thử dùng `Clock.fixed(...)` hoặc một clock có thể điều khiển. Cách này loại bỏ phụ thuộc vào múi giờ mặc định của máy chạy ứng dụng và không cần chờ thời gian thực trôi qua trong test.

## 1. DateTimeProvider nằm ở đâu trong auditing?

Spring Data Neo4j dùng hạ tầng auditing chung của Spring Data. Khi entity được lưu qua repository hoặc template, auditing đọc metadata trên entity và điền các trường thời gian theo cấu hình.

Hai annotation thường dùng cho thời gian:

- `@CreatedDate`: thời điểm entity được tạo.
- `@LastModifiedDate`: thời điểm entity được cập nhật gần nhất.

`DateTimeProvider` cung cấp giá trị thời gian cho các trường này. Interface có một phương thức:

```java
package org.springframework.data.auditing;

import java.time.temporal.TemporalAccessor;
import java.util.Optional;

public interface DateTimeProvider {

    Optional<TemporalAccessor> getNow();
}
```

`getNow()` trả `Optional<TemporalAccessor>`, cho phép provider cung cấp một kiểu thời gian thuộc Java Time API. Spring Data mặc định dùng `CurrentDateTimeProvider`. Provider mặc định tạo `LocalDateTime` mới cho mỗi lần gọi.

Nếu ứng dụng cần kiểm soát múi giờ, thống nhất timestamp giữa nhiều máy hoặc cố định thời gian trong test, hãy cung cấp `DateTimeProvider` riêng và kết nối nó với `@EnableNeo4jAuditing` qua `dateTimeProviderRef`.

## 2. Bật auditing cho Spring Data Neo4j

Các annotation auditing được đặt trong `org.springframework.data.annotation`:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Document")
public class Document {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    public Document() {
    }

    public Document(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
```

Khai báo repository:

```java
import com.example.graph.domain.Document;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface DocumentRepository extends Neo4jRepository<Document, Long> {
}
```

Auditing phải được bật trong cấu hình Spring:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
```

Nếu chưa bật `@EnableNeo4jAuditing`, chỉ đặt `@CreatedDate` hoặc `@LastModifiedDate` trên entity không đủ để Spring tự điền các trường đó.

Các trường thời gian có thể dùng các kiểu ngày giờ JDK như `Instant`, `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime`, `LocalDate`, `LocalTime`, `OffsetTime`, cùng `long`, `Long` và các kiểu legacy như `Date`, `Calendar`. Nên chọn kiểu theo ý nghĩa nghiệp vụ thay vì chỉ theo định dạng hiển thị.

## 3. Cấu hình DateTimeProvider qua dateTimeProviderRef

`@EnableNeo4jAuditing` có thuộc tính `dateTimeProviderRef` để chỉ định tên bean cung cấp thời gian. Ví dụ:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(
    dateTimeProviderRef = "auditDateTimeProvider",
    modifyOnCreate = true
)
public class Neo4jAuditingConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.<TemporalAccessor>of(Instant.now(auditClock));
    }
}
```

Hai thành phần có vai trò khác nhau:

- `Clock` là nguồn cung cấp thời gian. `Clock.systemUTC()` lấy thời điểm hiện tại theo UTC.
- `DateTimeProvider` chuyển nguồn thời gian thành `Optional<TemporalAccessor>` mà Spring Data auditing sử dụng.

Tên `auditDateTimeProvider` trong `dateTimeProviderRef` phải khớp tên bean. Việc inject `Clock` giúp có thể thay nguồn thời gian trong test mà không phải thay đổi entity hoặc code nghiệp vụ.

Nếu chỉ theo dõi ngày tạo và ngày cập nhật, không cần khai báo `AuditorAware`. `AuditorAware<T>` chỉ cần khi entity có `@CreatedBy` hoặc `@LastModifiedBy` để lấy người dùng hoặc tiến trình đã thực hiện thay đổi.

## 4. Ý nghĩa của modifyOnCreate và setDates

`@EnableNeo4jAuditing` có hai thuộc tính liên quan đến việc ghi thời gian:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---:|---|
| `modifyOnCreate` | `true` | Ghi cả thông tin sửa đổi ngay khi tạo entity |
| `setDates` | `true` | Cho phép auditing điền các trường ngày giờ |

Với `modifyOnCreate = true`, lúc tạo entity, cả `@CreatedDate` và `@LastModifiedDate` có thể nhận cùng một thời điểm. Đây là hành vi phù hợp khi ứng dụng muốn trường `lastModifiedAt` luôn có giá trị sau lần lưu đầu tiên.

Nếu nghiệp vụ định nghĩa `lastModifiedAt` chỉ xuất hiện sau lần cập nhật đầu tiên sau khi tạo, dùng `modifyOnCreate = false`:

Đây là cấu hình thay thế cho cấu hình ở phần trước; giữ bean `Clock` và `DateTimeProvider` hiện có trong cùng cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(
    dateTimeProviderRef = "auditDateTimeProvider",
    modifyOnCreate = false
)
public class Neo4jAuditingConfiguration {
    // Clock và DateTimeProvider được khai báo như ví dụ trước.
}
```

`setDates = false` tắt việc auditing tự điền các trường ngày giờ. Chỉ chọn cấu hình này khi ứng dụng có cơ chế khác chịu trách nhiệm ghi các giá trị đó, chẳng hạn callback riêng hoặc logic ở database. Không tắt `setDates` nếu đang mong đợi `@CreatedDate` và `@LastModifiedDate` được tự động cập nhật.

## 5. CurrentDateTimeProvider và múi giờ mặc định

`CurrentDateTimeProvider` mặc định tạo `LocalDateTime`. `LocalDateTime` biểu diễn ngày và giờ trên đồng hồ, nhưng không lưu múi giờ hoặc offset. Khi tạo bằng `LocalDateTime.now()` mà không truyền `Clock`, Java sử dụng system clock cùng múi giờ mặc định của máy.

Điều này có thể tạo ra khác biệt giữa các môi trường. Ví dụ, một node ứng dụng chạy với múi giờ UTC có thể ghi `2026-05-10T03:00`, trong khi node khác chạy với múi giờ Việt Nam có thể ghi `2026-05-10T10:00` cho cùng một thời điểm thực tế. Hai giá trị `LocalDateTime` này không chứa thông tin để xác định chúng có cùng instant hay không.

Khi ứng dụng chạy trên nhiều container, máy chủ hoặc vùng triển khai, không nên để timestamp audit phụ thuộc vào cấu hình múi giờ mặc định của từng máy. Hãy chọn một chính sách thống nhất và thể hiện chính sách đó trong kiểu dữ liệu cùng `DateTimeProvider`.

## 6. Phân biệt Instant, LocalDateTime và ZonedDateTime

Ba kiểu thường gặp thể hiện ba ý nghĩa khác nhau:

| Kiểu | Ý nghĩa | Có thông tin múi giờ? | Trường hợp phù hợp |
|---|---|---|---|
| `Instant` | Một điểm duy nhất trên dòng thời gian | Không lưu ZoneId; biểu diễn thời điểm UTC | Audit log, thời điểm tạo/cập nhật, sự kiện |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương | Không | Lịch mở cửa, giờ hẹn địa phương khi zone được quản lý riêng |
| `ZonedDateTime` | Ngày giờ cùng múi giờ và quy tắc zone | Có | Lịch nghiệp vụ cần giữ vùng thời gian như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` |

Với audit timestamp, `Instant` thường là lựa chọn dễ so sánh nhất. Nó biểu diễn thời điểm trên cùng một timeline, không phụ thuộc vào nơi ứng dụng đang chạy.

`LocalDateTime` không thể tự xác định một instant nếu thiếu zone hoặc offset. Ví dụ `2026-05-10T10:00` có thể tương ứng với nhiều thời điểm khác nhau tùy múi giờ. Không dùng `LocalDateTime` làm timestamp toàn hệ thống nếu các thành phần cần so sánh thời điểm giữa nhiều vùng.

`ZonedDateTime` phù hợp khi chính vùng thời gian là một phần của dữ liệu nghiệp vụ. Ví dụ lịch hẹn lúc 09:00 tại `Asia/Ho_Chi_Minh` cần giữ quy tắc của zone, đặc biệt khi xử lý lịch ở những khu vực có thay đổi giờ mùa hè. Một offset cố định như `+07:00` không thay thế đầy đủ một `ZoneId` có quy tắc lịch sử và tương lai.

## 7. Vì sao Clock.systemUTC và Instant phù hợp cho audit?

Trong cấu hình production:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
```

`Clock.systemUTC()` cung cấp nguồn thời gian theo UTC. `Instant.now(clock)` lấy một thời điểm tuyệt đối từ nguồn đó. Khi nhiều instance ứng dụng dùng cùng chính sách, các timestamp có thể so sánh trực tiếp mà không cần đoán múi giờ của máy đã ghi chúng.

`Clock.systemUTC()` chỉ thống nhất cách biểu diễn thời điểm, không đồng bộ đồng hồ vật lý giữa các máy. Với hệ thống nhiều instance, hạ tầng vẫn cần đồng bộ system clock bằng NTP hoặc dịch vụ thời gian tương đương. Nếu đồng hồ một node chạy nhanh hơn node khác, timestamp do hai node tạo vẫn có thể lệch nhau dù đều dùng UTC.

Nếu cần hiển thị cho người dùng tại Việt Nam, chuyển đổi ở lớp trình bày:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant recordedAt = document.getCreatedAt();
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime displayTime = recordedAt.atZone(userZone);
```

Giá trị lưu trữ vẫn là `Instant`; chỉ cách hiển thị được chuyển sang múi giờ người dùng. Không cộng thủ công bảy giờ vào `Instant` để tạo giờ địa phương.

Nếu cần giữ zone gốc trong dữ liệu, dùng `ZonedDateTime` hoặc lưu thêm `ZoneId` thành property riêng. Spring Data Neo4j ánh xạ `ZonedDateTime` sang Cypher `DateTime`; `Instant` cũng được ánh xạ sang Cypher `DateTime`. `LocalDateTime` được ánh xạ sang Cypher `LocalDateTime`, vốn không có thông tin zone.

## 8. Cấu hình provider cho nghiệp vụ cần múi giờ cụ thể

Nếu audit field cần mang một vùng thời gian thay vì một instant, hãy tạo `Clock` với zone rõ ràng và trả về kiểu tương ứng:

Đây là một cấu hình thay thế, trong đó auditing sử dụng provider trả về `ZonedDateTime`:

```java
import java.time.Clock;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(dateTimeProviderRef = "businessDateTimeProvider")
class BusinessTimeConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }

    @Bean
    DateTimeProvider businessDateTimeProvider(Clock businessClock) {
        return () -> Optional.<TemporalAccessor>of(ZonedDateTime.now(businessClock));
    }
}
```

Entity sử dụng `ZonedDateTime` cho trường audit tương ứng:

```java
import java.time.ZonedDateTime;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

// Các trường này nằm trong entity @Node.
@CreatedDate
private ZonedDateTime createdAt;

@LastModifiedDate
private ZonedDateTime lastModifiedAt;
```

Không cần tạo provider riêng cho từng múi giờ chỉ để định dạng dữ liệu khi trả API. Với audit toàn hệ thống, giữ `Instant` thường đơn giản hơn; chuyển sang zone người dùng khi hiển thị. Chỉ dùng `ZonedDateTime` khi zone có ý nghĩa cần lưu cùng sự kiện.

## 9. Kiểm thử DateTimeProvider bằng Clock.fixed

`Clock.fixed(...)` luôn trả cùng một instant. Đây là cách đơn giản để test không phụ thuộc đồng hồ hệ thống:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

import static org.assertj.core.api.Assertions.assertThat;

class AuditDateTimeProviderTest {

    @Test
    void shouldReturnTheConfiguredInstant() {
        Instant expected = Instant.parse("2026-05-10T03:00:00Z");
        Clock fixedClock = Clock.fixed(expected, ZoneOffset.UTC);

        DateTimeProvider provider = () ->
            Optional.<TemporalAccessor>of(Instant.now(fixedClock));

        assertThat(provider.getNow()).contains(expected);
    }
}
```

Test này xác nhận provider trả đúng thời điểm đã định nghĩa. Nó không cần chờ, không cần `Thread.sleep()` và không bị ảnh hưởng bởi múi giờ mặc định của máy chạy test.

## 10. Dùng Clock có thể điều khiển để kiểm thử cả tạo và cập nhật

Để kiểm thử `@CreatedDate` và `@LastModifiedDate` qua nhiều lần lưu trong cùng application context, có thể tạo một `Clock` test cho phép thay instant hiện tại. Ví dụ dưới đây dùng `AtomicReference` để cập nhật thời gian an toàn giữa các bước test:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.atomic.AtomicReference;

final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    AdjustableClock(Instant initialInstant, ZoneId zone) {
        this(new AtomicReference<>(initialInstant), zone);
    }

    private AdjustableClock(AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    void setInstant(Instant instant) {
        current.set(instant);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(current, zone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

Trong test configuration, cung cấp clock này làm bean `@Primary`. Bean `DateTimeProvider` trong cấu hình auditing sẽ nhận clock test thay vì `Clock.systemUTC()`:

```java
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class AdjustableAuditTimeConfiguration {

    @Bean
    @Primary
    AdjustableClock testAuditClock() {
        return new AdjustableClock(
            Instant.parse("2026-05-10T03:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Test có thể kiểm tra thời gian tạo và cập nhật:

```java
import java.time.Instant;

import com.example.graph.domain.Document;
import com.example.graph.repository.DocumentRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.neo4j.test.Neo4jIntegrationTest;

import static org.assertj.core.api.Assertions.assertThat;

@Neo4jIntegrationTest
@DataNeo4jTest
@Import({Neo4jAuditingConfiguration.class, AdjustableAuditTimeConfiguration.class})
class DocumentAuditingIntegrationTest {

    @Autowired
    DocumentRepository repository;

    @Autowired
    AdjustableClock testAuditClock;

    @Test
    void shouldKeepCreationTimeAndAdvanceModificationTime() {
        Instant createdAt = Instant.parse("2026-05-10T03:00:00Z");
        Instant modifiedAt = Instant.parse("2026-05-10T03:05:00Z");

        testAuditClock.setInstant(createdAt);
        Document saved = repository.save(new Document("Draft"));

        assertThat(saved.getCreatedAt()).isEqualTo(createdAt);
        assertThat(saved.getLastModifiedAt()).isEqualTo(createdAt);

        testAuditClock.setInstant(modifiedAt);
        Document loaded = repository.findById(saved.getId()).orElseThrow();
        loaded.setTitle("Published");
        Document updated = repository.save(loaded);

        assertThat(updated.getCreatedAt()).isEqualTo(createdAt);
        assertThat(updated.getLastModifiedAt()).isEqualTo(modifiedAt);
    }
}
```

Đây là ví dụ integration test: `DocumentRepository`, `Neo4jAuditingConfiguration` và `AdjustableAuditTimeConfiguration` cần được nạp trong test context cùng Neo4j test database. Nếu dùng `@DataNeo4jTest`, import các cấu hình auditing và test clock vào slice test bằng `@Import`. `@Primary` giúp provider chọn clock test khi có cả bean production và bean test.

Với `modifyOnCreate = true`, lần lưu đầu đặt cả hai trường bằng `createdAt`. Lần lưu tiếp theo giữ nguyên `createdAt` và cập nhật `lastModifiedAt` theo instant mới. Nếu cấu hình `modifyOnCreate = false`, điều chỉnh expectation của lần lưu đầu để phù hợp với quy tắc nghiệp vụ.

## 11. Không dùng thời gian thực để so sánh trong test

Một test như sau dễ chập chờn:

```java
import java.time.Instant;

import com.example.graph.domain.Document;
import com.example.graph.repository.DocumentRepository;

import static org.assertj.core.api.Assertions.assertThat;

// Đoạn mã nằm trong test dùng AdjustableAuditTimeConfiguration ở phần trước.
Instant beforeSave = Instant.now();
Document saved = repository.save(new Document("Draft"));
Instant afterSave = Instant.now();

assertThat(saved.getCreatedAt()).isBetween(beforeSave, afterSave);
```

Test phụ thuộc vào thời điểm thực, độ phân giải đồng hồ, thời gian thực thi và cách chuyển đổi timestamp. Khi chạy chậm, song song hoặc trên máy có clock khác nhau, lỗi có thể khó tái hiện.

Với clock test được đặt tại một instant mong đợi, test có một giá trị chính xác để so sánh. Đoạn mã sau nằm trong test dùng `AdjustableAuditTimeConfiguration` ở phần trước:

```java
Instant expected = Instant.parse("2026-05-10T03:00:00Z");
testAuditClock.setInstant(expected);

Document saved = repository.save(new Document("Draft"));

assertThat(saved.getCreatedAt()).isEqualTo(expected);
```

Tránh dùng `Thread.sleep()` để đợi `lastModifiedAt` khác `createdAt`. Điều khiển clock trực tiếp giúp test nhanh, ổn định và diễn đạt đúng điều kiện cần xác minh.

## 12. Kiểm tra kiểu thời gian sau khi lưu vào Neo4j

Auditing cập nhật thuộc tính trên entity trước khi SDN ghi dữ liệu. SDN có bộ chuyển đổi để ánh xạ các kiểu Java sang kiểu Cypher tương ứng:

| Kiểu Java | Kiểu Cypher trong SDN |
|---|---|
| `Instant` | `DateTime` |
| `ZonedDateTime` | `DateTime` |
| `OffsetDateTime` | `DateTime` |
| `LocalDateTime` | `LocalDateTime` |
| `LocalDate` | `Date` |
| `LocalTime` | `LocalTime` |
| `OffsetTime` | `Time` |

Với `Instant`, ứng dụng lưu một thời điểm. Với `ZonedDateTime`, dữ liệu có thêm thông tin zone. Với `LocalDateTime`, database nhận giá trị ngày giờ không có zone. Hãy chọn kiểu Java đúng trước khi thiết kế query hoặc kiểm thử dữ liệu được lưu.

Có thể xác minh kiểu và giá trị bằng một truy vấn Cypher trong integration test:

```cypher
MATCH (d:Document {title: $title})
RETURN d.createdAt AS createdAt,
       d.lastModifiedAt AS lastModifiedAt,
       valueType(d.createdAt) AS createdAtType
```

Tên property trong graph phụ thuộc mapping của entity. Nếu dùng tên khác hoặc `@Property`, điều chỉnh query theo mapping đó. Việc kiểm tra trực tiếp hữu ích khi cần xác nhận dữ liệu có kiểu `DateTime` thay vì chuỗi ISO được tự ghép.

## 13. DateTimeProvider và auditing reactive

Spring Data Neo4j cũng hỗ trợ auditing cho reactive infrastructure. Bật auditing reactive bằng `@EnableReactiveNeo4jAuditing`:

Trong cấu hình reactive, dùng annotation này thay cho `@EnableNeo4jAuditing` imperative. Bean `DateTimeProvider` vẫn có thể dùng cách tạo từ `Clock` ở phần trước.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableReactiveNeo4jAuditing;

@Configuration
@EnableReactiveNeo4jAuditing(dateTimeProviderRef = "auditDateTimeProvider")
class ReactiveNeo4jAuditingConfiguration {
}
```

`DateTimeProvider` vẫn cung cấp giá trị thời gian cho các trường ngày giờ. Nếu entity còn dùng `@CreatedBy` hoặc `@LastModifiedBy`, reactive infrastructure cần `ReactiveAuditorAware<T>` thay cho `AuditorAware<T>` để lấy principal từ reactive context.

Ví dụ `ReactiveAuditorAware` dùng Spring Security reactive:

```java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

class SecurityReactiveAuditorAware implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .mapNotNull(context -> context.getAuthentication())
            .filter(authentication -> authentication.isAuthenticated())
            .map(authentication -> authentication.getName());
    }
}
```

Không đọc `SecurityContextHolder` imperative trong reactive flow. Việc lấy auditor cần theo reactive context để không phụ thuộc thread đang thực thi publisher.

## 14. Khi nào cần BeforeBindCallback?

`DateTimeProvider` là lựa chọn chuẩn khi mục tiêu là cung cấp thời gian cho `@CreatedDate` và `@LastModifiedDate`. Nếu cần logic phức tạp hơn trước khi entity được ghi, Spring Data Neo4j cho phép khai báo `BeforeBindCallback<T>`; reactive có `ReactiveBeforeBindCallback<T>`.

Callback có thể chỉnh entity hoặc trả về một instance mới trước khi SDN bind dữ liệu vào graph. Nhiều callback có thể được sắp thứ tự bằng `Ordered` hoặc `@Order`. Chỉ dùng callback cho quy tắc nghiệp vụ thực sự cần thiết; không tự triển khai lại `DateTimeProvider` bằng callback nếu chỉ cần thay nguồn thời gian.

Một truy vấn Cypher thô qua `Neo4jClient` không đi qua quy trình lưu entity của repository/template. Nếu cập nhật audit bằng Cypher trực tiếp, câu query cần tự đặt timestamp hoặc gọi một luồng ghi entity có auditing. Không giả định annotation trên class tự động chạy cho mọi câu lệnh Cypher thủ công.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@CreatedDate` luôn null | Chưa bật `@EnableNeo4jAuditing` hoặc auditing không chạy qua SDN entity persistence | Bật auditing và lưu qua repository/template |
| Các server ghi timestamp khác nhau | Dùng `LocalDateTime` với timezone mặc định khác nhau | Dùng `Instant` và `Clock.systemUTC()` |
| Test lúc pass lúc fail | So sánh với `Instant.now()` hoặc dùng `Thread.sleep()` | Inject `Clock.fixed()` hoặc clock điều khiển được |
| Mất múi giờ gốc | Dùng `Instant` hoặc `LocalDateTime` trong khi nghiệp vụ cần ZoneId | Dùng `ZonedDateTime` hoặc lưu `ZoneId` riêng |
| `@LastModifiedDate` có giá trị ngay lúc tạo | `modifyOnCreate` mặc định là `true` | Đặt `modifyOnCreate = false` nếu nghiệp vụ yêu cầu |
| Không có tên người sửa | Có `@CreatedBy`/`@LastModifiedBy` nhưng chưa cấu hình auditor provider | Cung cấp `AuditorAware` hoặc `ReactiveAuditorAware` |
| Test dùng nhầm clock production | Provider không inject `Clock` hoặc test clock không phải bean được chọn | Inject `Clock` theo constructor/bean và dùng `@Primary` trong test |
| Timestamp dùng làm thứ tự tuyệt đối | Clock hệ thống có thể lệch hoặc hai thao tác có cùng timestamp | Dùng version, sequence hoặc ID riêng nếu cần thứ tự/định danh nghiêm ngặt |

## 16. Nguyên tắc cần nhớ

- `DateTimeProvider#getNow()` trả `Optional<TemporalAccessor>` cho Spring Data auditing.
- `CurrentDateTimeProvider` mặc định tạo `LocalDateTime`; giá trị này không mang múi giờ.
- Bật auditing bằng `@EnableNeo4jAuditing` và chỉ định provider bằng `dateTimeProviderRef`.
- Nếu chỉ ghi thời gian, không cần `AuditorAware`.
- Dùng `Instant` cho timestamp audit cần so sánh trên một timeline chung.
- Dùng `Clock.systemUTC()` trong production và inject `Clock` thay vì gọi `Instant.now()` trực tiếp trong provider.
- Dùng `ZonedDateTime` hoặc lưu `ZoneId` riêng khi zone là dữ liệu nghiệp vụ cần giữ.
- Dùng `Clock.fixed()` cho test xác định; dùng clock điều khiển được khi cần kiểm thử nhiều lần cập nhật.
- `modifyOnCreate` mặc định là `true`; đặt `false` khi không muốn `@LastModifiedDate` được điền lúc tạo.
- Không dùng timestamp làm khóa duy nhất hoặc bộ đếm thứ tự tuyệt đối.

Khi cấu hình auditing, hãy quyết định rõ dữ liệu cần lưu là một instant hay một giờ địa phương có zone. `DateTimeProvider` cùng `Clock` cho phép tách chính sách thời gian khỏi code persistence, giúp mọi instance ghi timestamp nhất quán và giúp kiểm thử ngày giờ mà không phụ thuộc vào đồng hồ thực.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 – FAQ: How do I audit entities?](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j 8.2 – Auditing](https://docs.spring.io/spring-data/neo4j/reference/auditing.html)
- [Spring Data Neo4j 8.2 – Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Commons – DateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)
- [Spring Data Commons – CurrentDateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/CurrentDateTimeProvider.html)
- [Java SE – java.time package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html)
- [Java SE – Clock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)
- [Neo4j Java Driver – Data types and mapping to Cypher types](https://neo4j.com/docs/java-manual/current/data-types/)
