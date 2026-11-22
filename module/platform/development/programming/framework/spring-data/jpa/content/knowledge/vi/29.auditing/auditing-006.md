# DateTimeProvider, múi giờ và đồng hồ có thể kiểm thử

## 1. DateTimeProvider giải quyết vấn đề gì?

Spring Data JPA Auditing tự động ghi nhận thời điểm tạo và cập nhật Entity thông qua các annotation như `@CreatedDate` và `@LastModifiedDate`. Nếu để auditing tự lấy thời gian hiện tại, kết quả phụ thuộc vào đồng hồ hệ thống của tiến trình đang chạy. Điều đó gây khó khăn khi kiểm thử chính xác timestamp, mô phỏng thời gian tương lai/quá khứ hoặc bảo đảm các thành phần trong ứng dụng dùng cùng một nguồn thời gian.

`DateTimeProvider` là điểm mở rộng cho phép cung cấp giá trị thời gian mà Spring Data Auditing sử dụng. Kết hợp nó với `java.time.Clock`, ứng dụng có thể:

- Dùng một nguồn thời gian thống nhất cho auditing.
- Chọn UTC hoặc một múi giờ nghiệp vụ có chủ đích.
- Dùng đồng hồ cố định trong unit/integration test để kết quả xác định.
- Thay đồng hồ trong test để kiểm tra cập nhật timestamp mà không phải chờ thời gian thực.

`Clock` cung cấp thời điểm hiện tại; `DateTimeProvider` chuyển thời điểm đó thành giá trị mà Spring Data Auditing hiểu. Hai API có vai trò liên quan nhưng không thay thế nhau.

## 2. Bật JPA Auditing

Trước tiên, bật auditing và đăng ký `AuditingEntityListener` trên Entity hoặc mapped superclass:

```java
@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
```

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;
}
```

`@CreatedDate` ghi thời điểm tạo; `@LastModifiedDate` ghi thời điểm cập nhật gần nhất. `@EntityListeners(AuditingEntityListener.class)` kết nối Entity với listener của Spring Data. Nếu thiếu listener hoặc chưa bật `@EnableJpaAuditing`, các trường auditing có thể không được điền.

Trong ví dụ, `Instant` biểu diễn một thời điểm tuyệt đối trên timeline. `updatable = false` giúp JPA không đưa `createdAt` vào câu UPDATE thông thường. Với nhiều Entity dùng chung audit fields, có thể chuyển các trường và listener vào một `@MappedSuperclass`.

## 3. Đăng ký Clock và DateTimeProvider

Để auditing lấy thời gian từ một `Clock` do ứng dụng quản lý, tạo hai bean:

```java
@Configuration
@EnableJpaAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JpaAuditingConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider auditingDateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }
}
```

`DateTimeProvider#getNow()` trả về `Optional<TemporalAccessor>`. `Instant` triển khai `TemporalAccessor`, vì vậy có thể trả trực tiếp `applicationClock.instant()`. `dateTimeProviderRef` phải khớp tên bean `auditingDateTimeProvider`.

`Clock.systemUTC()` tạo clock dùng thời gian hệ thống với zone UTC. Khi gọi `instant()`, kết quả là thời điểm tuyệt đối; nó không phụ thuộc vào timezone mặc định của máy chủ. Nếu ứng dụng có nhiều bean `Clock`, hãy dùng `@Qualifier` hoặc `@Primary` để Spring biết bean nào cần inject.

Chỉ cấu hình `@EnableJpaAuditing` một lần trong application context. Nếu cấu hình đã bật auditing ở nơi khác, thêm một cấu hình thứ hai có thể gây xung đột hoặc đăng ký auditing không như mong đợi.

## 4. DateTimeProvider và kiểu thời gian được lưu

`DateTimeProvider` trả về `TemporalAccessor`, nhưng kiểu trường trong Entity quyết định cách thời gian được biểu diễn và ánh xạ xuống database.

| Kiểu Java | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối trên timeline | Audit timestamp, thời điểm tạo/cập nhật, event time |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Khi cần giữ offset của giá trị đầu vào và provider/database hỗ trợ mapping phù hợp |
| `LocalDateTime` | Ngày giờ trên đồng hồ địa phương, không chứa zone/offset | Giờ nghiệp vụ địa phương khi zone được quản lý riêng |
| `LocalDate` | Ngày lịch, không có giờ hoặc zone | Ngày sinh, ngày hiệu lực theo lịch |
| `ZonedDateTime` | Ngày giờ cùng ZoneId và quy tắc múi giờ | Khi logic ứng dụng cần zone; cần xác minh cách provider lưu/khôi phục |

Với audit timestamp, `Instant` thường là lựa chọn rõ ràng nhất vì nó không bị nhập nhằng khi ứng dụng chạy ở nhiều máy chủ hoặc nhiều múi giờ.

`LocalDateTime` không tự cho biết giá trị thuộc múi giờ nào. Ví dụ `2026-11-09T09:00` có thể là 09:00 ở Hà Nội, Tokyo hoặc London; nếu cần quy đổi sang một thời điểm tuyệt đối, phải biết `ZoneId` đi kèm.

`OffsetDateTime` giữ offset như `+07:00`, nhưng offset không tương đương một múi giờ có quy tắc DST. `ZonedDateTime` chứa ZoneId, song không phải database/provider nào cũng lưu và khôi phục đầy đủ zone ID. Nếu nghiệp vụ cần nhớ cả thời điểm và vùng giờ gốc, có thể lưu `Instant` cùng một cột `ZoneId` riêng.

## 5. Phân biệt UTC, offset và múi giờ

Ba khái niệm thường bị nhầm:

- **UTC:** chuẩn tham chiếu thời gian toàn cầu. `Instant` có thể được biểu diễn theo UTC.
- **Offset:** độ lệch cố định so với UTC tại một thời điểm, ví dụ `+07:00`.
- **ZoneId:** tên vùng giờ có quy tắc lịch sử và DST, ví dụ `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`.

Ví dụ:

```java
Instant instant = Instant.parse("2026-11-09T02:00:00Z");
ZonedDateTime vietnamTime = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
OffsetDateTime offsetTime = instant.atOffset(ZoneOffset.ofHours(7));

System.out.println(instant);
System.out.println(vietnamTime);
System.out.println(offsetTime);
```

Với Java 17+, kết quả:

```text
2026-11-09T02:00:00Z
2026-11-09T09:00+07:00[Asia/Ho_Chi_Minh]
2026-11-09T09:00+07:00
```

Ba giá trị biểu diễn cùng một thời điểm, nhưng `ZonedDateTime` còn mang ZoneId. Offset `+07:00` tự nó không chứa toàn bộ quy tắc của `Asia/Ho_Chi_Minh`.

## 6. Không dùng timezone mặc định của máy chủ làm quy tắc nghiệp vụ

Tránh gọi trực tiếp `LocalDateTime.now()` rải rác trong service, listener hoặc Entity. Kết quả phụ thuộc timezone mặc định của JVM và làm test khó kiểm soát.

Không nên dựa vào:

```java
LocalDateTime now = LocalDateTime.now();
```

Thay vào đó, inject `Clock`:

```java
public class OrderDeadlineService {
    private final Clock clock;

    public OrderDeadlineService(Clock clock) {
        this.clock = clock;
    }

    public Instant calculateDeadline(Duration duration) {
        return clock.instant().plus(duration);
    }
}
```

Nếu cần giờ lịch địa phương, truyền zone một cách tường minh:

```java
LocalDateTime localNow = LocalDateTime.now(clock);
ZonedDateTime businessNow = ZonedDateTime.now(
    clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
);
```

Đối với audit event, lưu `Instant` và chỉ chuyển sang zone khi hiển thị. Đối với lịch hẹn hoặc giờ mở cửa, lưu quy tắc địa phương cùng `ZoneId` phù hợp; đừng biến giờ địa phương thành UTC khi chưa xác định zone.

## 7. Giờ mùa hè (DST) và giờ địa phương không tồn tại hoặc bị lặp

Một số vùng giờ có daylight saving time. Khi chuyển sang giờ mùa hè, một khoảng giờ địa phương có thể không tồn tại; khi chuyển ngược lại, một khoảng giờ có thể xuất hiện hai lần.

Ví dụ một lịch hẹn được lưu chỉ bằng `LocalDateTime` có thể trở nên nhập nhằng nếu zone áp dụng DST. Khi tạo lịch theo giờ địa phương:

1. Lưu ngày giờ địa phương mà người dùng chọn.
2. Lưu `ZoneId` của địa điểm/nghiệp vụ.
3. Dùng `ZoneRules` để phát hiện thời gian nằm trong gap hoặc overlap.
4. Xác định chính sách nghiệp vụ: từ chối giờ không tồn tại, tự điều chỉnh, hoặc yêu cầu người dùng chọn offset khi giờ bị lặp.

Với sự kiện đã xảy ra, lưu `Instant` là rõ nhất. Với sự kiện tương lai theo giờ địa phương, lưu cả local date-time và ZoneId có thể cần thiết vì quy tắc múi giờ có thể thay đổi theo luật.

## 8. Cấu hình timezone cho JDBC/Hibernate

Chọn `Instant` và `Clock.systemUTC()` là bước quan trọng, nhưng cần hiểu database và JDBC driver vẫn có quy tắc ánh xạ timestamp riêng. Với Hibernate, có thể cấu hình timezone dùng khi bind/extract JDBC timestamp:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

Cấu hình này giúp Hibernate dùng UTC khi tương tác với các JDBC timestamp API có timezone parameter. Nó không tự biến cột `TIMESTAMP WITHOUT TIME ZONE` thành kiểu lưu timezone, cũng không bảo đảm database giữ nguyên ZoneId đầu vào.

Kiểu cột và semantics khác nhau giữa database. Ví dụ một số database có timestamp with time zone lưu một instant đã chuẩn hóa nhưng không giữ zone ID gốc; kiểu timestamp không timezone thường lưu các trường ngày giờ mà không tự mang thông tin zone. Hãy kiểm tra dialect, schema migration, JDBC driver và cách dữ liệu được đọc lại.

Nếu schema đã được quản lý bằng Flyway/Liquibase, thay đổi kiểu cột phải đi qua migration phù hợp. `@Column` hoặc kiểu Java không tự bảo đảm schema production được chuyển đổi an toàn.

## 9. Kiểm soát độ chính xác timestamp

Java `Instant` có độ chính xác tới nanosecond, trong khi cột database có thể chỉ lưu microsecond hoặc millisecond. Sau khi persist và đọc lại, giá trị có thể bị truncate/round theo độ chính xác của database.

Vì vậy, khi viết test:

- Không mặc định mọi database giữ nguyên nanosecond.
- Dùng precision của cột phù hợp với ứng dụng.
- So sánh timestamp sau khi chuẩn hóa theo precision thực tế, hoặc chọn giá trị test có precision tương thích.
- Kiểm tra cả timezone lẫn độ chính xác khi migrate database.

Không tự cộng/trừ một số mili giây tùy ý để làm test pass; xác định chính xác precision mà schema/provider đang sử dụng.

## 10. Dùng Clock.fixed để test DateTimeProvider

`Clock.fixed(...)` luôn trả về cùng một thời điểm, giúp test không phụ thuộc đồng hồ thực:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T08:30:00Z"),
    ZoneOffset.UTC
);

DateTimeProvider provider = () -> Optional.of(fixedClock.instant());

Instant supplied = (Instant) provider.getNow().orElseThrow();
System.out.println(supplied);
```

Java 17+ stdout:

```text
2026-01-15T08:30:00Z
```

Đây là unit test cho adapter `Clock` sang `DateTimeProvider`. Để kiểm tra auditing thật sự, cần đưa clock test vào Spring context đang bật `@EnableJpaAuditing` rồi persist Entity qua repository.

## 11. Inject Clock cố định trong integration test

Có thể cung cấp một `Clock` test với `@Primary`, để `DateTimeProvider` tự động dùng clock đó:

```java
@TestConfiguration
public class FixedClockTestConfiguration {
    @Bean
    @Primary
    public Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T08:30:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Test tích hợp:

```java
@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void populatesAuditDatesFromInjectedClock() {
        PurchaseOrder order = repository.saveAndFlush(new PurchaseOrder());

        Instant expected = Instant.parse("2026-01-15T08:30:00Z");
        assertEquals(expected, order.getCreatedAt());
        assertEquals(expected, order.getLastModifiedAt());
    }
}
```

Ví dụ giả định auditing đã được bật, Entity có listener, các getter tồn tại và `modifyOnCreate` giữ giá trị mặc định `true`. Khi đó `@LastModifiedDate` cũng được điền lúc tạo mới. Nếu ứng dụng cấu hình `modifyOnCreate = false`, không nên kỳ vọng trường modified được gán trong lần insert.

## 12. Kiểm thử cả lần cập nhật bằng MutableClock

`Clock.fixed` rất phù hợp để kiểm tra insert, nhưng không thể tiến thời gian. Để kiểm tra `@LastModifiedDate` thay đổi khi Entity được update, có thể dùng một Clock test có thể điều chỉnh:

```java
public final class MutableClock extends Clock {
    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(initial), zone);
    }

    private MutableClock(AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    public void setInstant(Instant instant) {
        current.set(instant);
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
        return new MutableClock(current, zone);
    }
}
```

Đăng ký `MutableClock` làm bean `@Primary` trong test, rồi kiểm tra insert và update:

```java
@Test
void createdDateStaysFixedAndModifiedDateAdvances() {
    Instant first = Instant.parse("2026-01-15T08:30:00Z");
    testClock.setInstant(first);

    PurchaseOrder order = repository.saveAndFlush(new PurchaseOrder());
    assertEquals(first, order.getCreatedAt());
    assertEquals(first, order.getLastModifiedAt());

    Instant later = first.plusSeconds(90);
    testClock.setInstant(later);
    order.setStatus(OrderStatus.PAID);
    repository.saveAndFlush(order);

    assertEquals(first, order.getCreatedAt());
    assertEquals(later, order.getLastModifiedAt());
}
```

Đoạn test giả định Entity có setter `setStatus`, getter audit fields, repository và `MutableClock` được inject. `saveAndFlush` buộc JPA flush để lifecycle auditing chạy trước khi assertion. Nếu Entity không dirty hoặc không phát sinh UPDATE, `@PreUpdate`/auditing update có thể không chạy.

## 13. @CreatedBy và @LastModifiedBy

Auditing có thể ghi cả người tạo và người cập nhật. Cơ chế này dùng `AuditorAware<T>`, độc lập với `DateTimeProvider`:

```java
@Configuration
@EnableJpaAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditingDateTimeProvider"
)
public class JpaAuditingConfiguration {
    // Clock và DateTimeProvider beans được khai báo tại đây.

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

Đoạn trên chỉ minh họa một auditor cố định. Trong ứng dụng Spring Security, `AuditorAware` thường lấy principal đã xác thực từ SecurityContext. Với tác vụ nền hoặc batch, cần quy định rõ auditor hệ thống; không giả định luôn có HTTP user.

Entity có thể khai báo:

```java
@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

`DateTimeProvider` trả lời câu hỏi “bây giờ là lúc nào?”; `AuditorAware` trả lời “ai đang thực hiện thay đổi?”. Hai nguồn này nên được kiểm thử độc lập và có thể dùng chung trong một auditing configuration.

## 14. modifyOnCreate và thời điểm cập nhật audit

`@EnableJpaAuditing` có tùy chọn `modifyOnCreate`. Giá trị mặc định là `true`, nên `@LastModifiedDate` và `@LastModifiedBy` có thể được gán ngay cả khi Entity được tạo mới. Nếu đặt `modifyOnCreate = false`, các trường modified chỉ được cập nhật khi Entity thay đổi sau khi tạo.

Audit timestamp được gán trong lifecycle persist/update mà auditing listener tham gia. Nó không phải cam kết chính xác thời điểm transaction commit. Transaction có thể commit muộn hơn, rollback hoặc flush nhiều lần. Nếu nghiệp vụ cần ghi nhận thời điểm commit hoặc phát event sau commit, phải dùng cơ chế transaction/event phù hợp thay vì diễn giải `@LastModifiedDate` là commit timestamp.

Đối với một lần update, `@LastModifiedDate` chỉ có ý nghĩa khi JPA thực sự phát hiện thay đổi và thực hiện update. Gọi setter với cùng giá trị có thể không làm Entity dirty tùy dirty-checking và mapping.

## 15. Clock ứng dụng và thời gian database

Trong một hệ thống có thể tồn tại hai nguồn thời gian:

- Clock của ứng dụng được dùng bởi `DateTimeProvider`.
- Clock của database được dùng bởi `CURRENT_TIMESTAMP`, default column hoặc trigger.

Không trộn hai nguồn mà không có chính sách rõ. Nếu `createdAt` do ứng dụng ghi nhưng `updatedAt` do trigger database ghi, chênh lệch đồng hồ giữa application node và database có thể tạo thứ tự timestamp bất ngờ.

Chọn một nguồn chuẩn cho từng nhóm timestamp. Nếu audit được quản lý bởi Spring Data, dùng Clock được inject và đồng bộ NTP cho các node. Nếu database là nguồn chuẩn, để database sinh timestamp và không đồng thời ghi đè bằng application auditing cho cùng field.

Clock có thể kiểm soát thời gian trong process, nhưng không tự sửa clock hệ thống sai. Production vẫn cần đồng bộ thời gian máy chủ và giám sát clock drift.

## 16. Lỗi thường gặp và cách xử lý

**`@CreatedDate` hoặc `@LastModifiedDate` vẫn null.** Kiểm tra `@EnableJpaAuditing`, `AuditingEntityListener`, dependency Spring Data JPA và field access/mapping của Entity.

**DateTimeProvider không được dùng.** Kiểm tra tên `dateTimeProviderRef` khớp tên bean và bean trả về `Optional<TemporalAccessor>` có giá trị.

**Ứng dụng báo thiếu hoặc có nhiều Clock bean.** Đánh dấu một bean `@Primary` hoặc dùng `@Qualifier` trong DateTimeProvider.

**Test timestamp lúc pass lúc fail.** Không dùng `Instant.now()` hoặc `LocalDateTime.now()` trực tiếp trong assertion. Inject `Clock.fixed` hoặc Clock có thể điều khiển.

**`@LastModifiedDate` không đổi.** Kiểm tra Entity có dirty và có phát sinh UPDATE khi flush hay không; gọi `save` với cùng giá trị không bảo đảm có update.

**Timestamp lệch giờ giữa môi trường.** Kiểm tra kiểu Java, timezone JVM, JDBC driver, Hibernate `hibernate.jdbc.time_zone`, session timezone và kiểu cột database.

**Timestamp đọc lại khác nanosecond.** Database có thể lưu precision thấp hơn Java Instant. So sánh theo precision schema và kiểm tra migration.

**LocalDateTime bị nhập nhằng khi DST.** Lưu ZoneId cùng local time hoặc dùng Instant cho event đã xảy ra; xác định chính sách gap/overlap.

**Audit timestamp bị ghi bởi cả ứng dụng và trigger.** Chọn một nguồn chuẩn cho mỗi field và tránh hai bên ghi đè lẫn nhau.

## 17. Checklist triển khai

- Bật `@EnableJpaAuditing` và đăng ký `AuditingEntityListener` trên Entity/mapped superclass.
- Tạo bean `Clock` và custom `DateTimeProvider`; trỏ `dateTimeProviderRef` đúng tên.
- Ưu tiên `Instant` cho audit event timestamp và dùng UTC làm quy ước.
- Chỉ dùng `LocalDateTime` khi nghiệp vụ thực sự là giờ địa phương và zone được quản lý riêng.
- Phân biệt UTC offset với ZoneId; không giả định database lưu được zone ID.
- Kiểm tra Hibernate/JDBC timezone và kiểu cột qua migration.
- Xác định timestamp precision của database.
- Dùng `Clock.fixed` cho test insert; dùng MutableClock hoặc clock có thể điều khiển cho test update.
- Kiểm tra `modifyOnCreate` và semantics của `@LastModifiedDate`.
- Nếu dùng `@CreatedBy`/`@LastModifiedBy`, cấu hình và test `AuditorAware` riêng.
- Không trộn clock ứng dụng và database cho cùng một field audit.

`DateTimeProvider` cho phép Spring Data Auditing nhận thời gian từ một nguồn có thể kiểm soát. Kết hợp với `Clock`, chọn `Instant`/UTC cho audit timestamp và quản lý ZoneId rõ ràng cho giờ nghiệp vụ, ứng dụng có thể ghi nhận thời gian nhất quán và kiểm thử insert/update một cách xác định.