# Chọn nguồn thời gian, múi giờ và kiểm thử thời gian

Auditing trong Spring Data R2DBC ghi lại các mốc như thời điểm tạo và cập nhật bản ghi, cùng người thực hiện thao tác. Những giá trị này tưởng đơn giản nhưng có thể trở nên khó kiểm soát nếu mỗi nơi tự gọi `Instant.now()`, server chạy ở múi giờ khác nhau, database dùng kiểu timestamp không lưu timezone hoặc test phụ thuộc đồng hồ thật.

Muốn auditing nhất quán, cần quyết định ba điều: **ai là nguồn thời gian có thẩm quyền**, **giá trị được biểu diễn và lưu theo múi giờ nào**, và **làm sao kiểm thử mà không phụ thuộc thời điểm chạy test**. Trong ứng dụng Spring, `Clock` và `DateTimeProvider` giúp tập trung nguồn thời gian; `@EnableR2dbcAuditing` kết hợp `@CreatedDate` và `@LastModifiedDate` để gắn mốc thời gian vào entity. Việc chọn application clock hay database clock cần dựa trên yêu cầu đồng bộ giữa các writer, khả năng kiểm thử và semantics của database.

## 1. Auditing thời gian trong Spring Data R2DBC

Spring Data Relational hỗ trợ auditing để tự điền metadata khi entity được tạo hoặc thay đổi. Các annotation thường dùng:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedDate` | Thời điểm entity được tạo |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất |
| `@CreatedBy` | Tác nhân tạo entity |
| `@LastModifiedBy` | Tác nhân sửa entity gần nhất |

Ví dụ entity:

```java
@Table("article")
public class Article {

    @Id
    private Long id;

    private String title;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    // Constructor, getter và các phương thức nghiệp vụ.
}
```

Khi auditing được bật, callback của Spring Data có thể điền các trường này trong vòng đời ghi entity. `@CreatedDate` biểu thị thời điểm tạo; `@LastModifiedDate` biểu thị thời điểm sửa gần nhất. Các trường auditor tương ứng lưu tác nhân, ví dụ username hoặc service account.

Auditing không tự xác định một múi giờ nghiệp vụ cho ứng dụng. Nó sử dụng nguồn thời gian được cấu hình và kiểu dữ liệu của thuộc tính. Vì vậy, cần thiết kế nguồn thời gian và kiểu timestamp trước khi bật auditing trên nhiều service.

## 2. Bật auditing cho R2DBC

Kích hoạt auditing bằng `@EnableR2dbcAuditing` trong cấu hình Spring:

```java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

Khi đó, Spring Data đăng ký các callback auditing để điền những thuộc tính có annotation tương ứng khi entity được ghi qua các API mapping của Spring Data.

Nếu cần chỉ định nguồn thời gian hoặc auditor cụ thể, cấu hình các bean tương ứng:

```java
@Configuration
@EnableR2dbcAuditing(
    dateTimeProviderRef = "auditingDateTimeProvider",
    auditorAwareRef = "auditorAware"
)
public class R2dbcAuditingConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
```

Ví dụ trên dùng `Clock.systemUTC()` làm nguồn thời gian và lấy tên người dùng từ reactive security context. Nếu thao tác chạy trong background job không có security context, `ReactiveAuditorAware` có thể hoàn tất rỗng; khi đó các trường `@CreatedBy`/`@LastModifiedBy` không được điền từ nguồn này. Ứng dụng có thể cung cấp một service identity mặc định theo chính sách, chẳng hạn `batch-worker`, thay vì gán một username người dùng giả.

`DateTimeProvider` trả về `Optional<TemporalAccessor>`; `ReactiveAuditorAware<T>` trả về `Mono<T>`. Đây là hai hợp đồng khác nhau: nguồn thời gian được cung cấp qua `DateTimeProvider`, còn auditor có thể được xác định bất đồng bộ theo reactive context.

Nếu chỉ cần timestamp, không cần khai báo auditor. Nếu cần auditor nhưng không có Spring Security, có thể triển khai `ReactiveAuditorAware` từ request context hoặc service identity của ứng dụng.

## 3. Chọn nguồn thời gian: application clock hay database clock?

Có hai nơi phổ biến có thể tạo timestamp:

**Application clock:** ứng dụng lấy thời gian từ hệ điều hành của máy chạy service, thường qua `Clock` và `DateTimeProvider`, rồi ghi giá trị vào database.

**Database clock:** câu SQL, default hoặc trigger lấy thời gian từ server database và gán vào cột.

| Tiêu chí | Application clock | Database clock |
|---|---|---|
| Nguồn | Đồng hồ của application instance | Đồng hồ của database server |
| Kiểm thử | Dễ thay bằng `Clock.fixed` hoặc clock giả | Cần database test hoặc cơ chế kiểm soát thời gian trong DB |
| Nhiều service ghi cùng bảng | Có thể lệch nếu các máy không đồng bộ | Một database có nguồn thời gian chung cho các writer |
| Giá trị được gán khi nào | Thường trước khi gửi câu lệnh ghi | Trong lúc database thực hiện câu lệnh hoặc trigger |
| Tích hợp auditing | Tự nhiên với `DateTimeProvider` | Cần để database sở hữu cột và đọc lại giá trị nếu cần |
| Phụ thuộc cấu hình | Đồng bộ đồng hồ máy/VM/container | Đồng bộ đồng hồ database và semantics riêng của hệ quản trị |

Không có lựa chọn đúng cho mọi hệ thống. Application clock thuận tiện cho domain logic và kiểm thử. Database clock hữu ích khi nhiều ứng dụng hoặc công cụ cùng ghi vào một bảng và cần một nguồn thời gian thống nhất ở phía database.

Điều quan trọng là chọn một chủ sở hữu cho mỗi cột audit. Nếu application callback ghi `created_at` và database trigger cũng ghi đè cột đó, cần xác định giá trị nào là nguồn sự thật và cách lấy lại giá trị cuối cùng. Tránh để cả hai tầng cùng cập nhật một cột mà không có quy tắc rõ.

## 4. Dùng Clock thay vì gọi Instant.now() rải rác

`Clock` là abstraction của nguồn thời gian trong Java. Nó cho phép code production dùng đồng hồ hệ thống, còn test có thể thay bằng đồng hồ cố định hoặc đồng hồ điều khiển được.

Khai báo bean dùng UTC:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Service dùng Clock qua constructor:

```java
@Service
public class PublicationService {

    private final Clock clock;
    private final ArticleRepository repository;

    public PublicationService(Clock clock, ArticleRepository repository) {
        this.clock = clock;
        this.repository = repository;
    }

    public Mono<Article> publish(Article article) {
        Instant publishedAt = clock.instant();
        return repository.save(article.withPublishedAt(publishedAt));
    }
}
```

Không gọi `Instant.now()` trực tiếp ở nhiều nơi nếu logic cần kiểm thử thời điểm. Khi inject `Clock`, test có thể điều khiển giá trị trả về mà không phải thay đổi code nghiệp vụ.

`Clock.systemUTC()` không làm thay đổi đồng hồ vật lý của máy. Nó tạo clock hệ thống biểu diễn thời điểm hiện tại theo UTC. Điều này tránh phụ thuộc default timezone của JVM khi lấy instant.

## 5. Tùy chỉnh DateTimeProvider cho auditing

`DateTimeProvider` là nguồn thời gian mà Spring Data auditing sử dụng để lấy giá trị hiện tại. Kết hợp nó với `Clock` giúp cả code nghiệp vụ và auditing dùng cùng một abstraction:

```java
@Configuration
@EnableR2dbcAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class AuditingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }
}
```

Khi cần dùng một kiểu thời gian khác, `DateTimeProvider` có thể trả về một `TemporalAccessor` tương thích với thuộc tính audit. Ví dụ:

```java
@Bean
DateTimeProvider auditingDateTimeProvider(Clock clock) {
    return () -> Optional.of(OffsetDateTime.now(clock));
}
```

Tuy nhiên, nên thống nhất kiểu dữ liệu cho toàn hệ thống. `Instant` thường phù hợp cho thời điểm audit vì nó biểu diễn một điểm duy nhất trên timeline, không gắn với timezone hiển thị của người dùng.

Đừng tạo một `Clock.systemDefaultZone()` cho một bean, rồi ở nơi khác gọi `Instant.now()` hoặc `LocalDateTime.now()` theo default timezone. Cách đó làm cho logic thời gian phụ thuộc cấu hình môi trường và khó tái lập trong test.

## 6. Instant, OffsetDateTime, ZonedDateTime và LocalDateTime

Chọn kiểu Java dựa trên ý nghĩa của dữ liệu, không chỉ dựa trên kiểu cột SQL.

| Kiểu Java | Ý nghĩa | Phù hợp với |
|---|---|---|
| `Instant` | Một điểm tuyệt đối trên timeline UTC | Created/modified timestamp, event time, audit log |
| `OffsetDateTime` | Ngày giờ cùng offset UTC tại thời điểm đó | Giao tiếp API hoặc dữ liệu cần giữ offset đã biết |
| `ZonedDateTime` | Ngày giờ cùng `ZoneId` và quy tắc timezone | Lịch theo múi giờ địa lý, chuyển đổi DST |
| `LocalDateTime` | Ngày giờ địa phương, không có offset/timezone | Thời gian trên đồng hồ địa phương khi ngữ cảnh timezone được quản lý riêng |
| `LocalDate` | Ngày lịch, không có giờ | Ngày sinh, ngày hóa đơn, ngày nghỉ |
| `LocalTime` | Giờ trong ngày, không có ngày | Giờ mở cửa, thời điểm lặp hàng ngày |

Đối với `created_at` và `last_modified_at`, `Instant` thường là lựa chọn dễ hiểu nhất. Hai sự kiện ở hai server khác múi giờ vẫn có thể so sánh trực tiếp vì đều là instant.

`LocalDateTime` không xác định được một instant nếu thiếu timezone hoặc offset. Ví dụ `2026-11-15T09:00` có thể tương ứng với nhiều thời điểm khác nhau tùy nơi. Không nên dùng `LocalDateTime` làm audit timestamp toàn hệ thống nếu sau này cần đối chiếu log từ nhiều region.

`ZonedDateTime` chứa `ZoneId`, nhưng nhiều kiểu cột SQL không lưu tên vùng như `Asia/Ho_Chi_Minh`. Nếu nghiệp vụ cần nhớ timezone gốc của lịch hẹn, có thể lưu instant hoặc local date-time cùng một cột zone ID riêng.

## 7. Lưu UTC và chuyển sang múi giờ hiển thị

Một quy ước phổ biến là lưu audit timestamp dưới dạng instant và hiển thị theo timezone của người dùng ở tầng API/UI.

Ví dụ:

```java
Instant createdAt = Instant.parse("2026-11-15T02:00:00Z");

ZonedDateTime vietnamTime = createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime londonTime = createdAt.atZone(ZoneId.of("Europe/London"));
```

Hai giá trị `ZonedDateTime` biểu diễn cùng một instant nhưng hiển thị theo hai timezone khác nhau. Dữ liệu audit không cần đổi chỉ vì người dùng xem ở một múi giờ khác.

Khi trả API, có thể serialize `Instant` dưới dạng ISO-8601 UTC, ví dụ `2026-11-15T02:00:00Z`. Client có thể định dạng theo locale và timezone của người dùng. Nếu API nhận một thời điểm do người dùng nhập, cần yêu cầu offset hoặc timezone rõ ràng khi đó là thời điểm tuyệt đối.

Không nên lưu chuỗi thời gian đã format như `15/11/2026 09:00` vào cột timestamp. Chuỗi hiển thị phụ thuộc locale, không thể so sánh hoặc sắp xếp an toàn như kiểu thời gian.

## 8. Chọn kiểu cột SQL phù hợp

Kiểu timestamp của database có semantics khác nhau giữa các hệ quản trị. Cần hiểu kiểu cột trước khi chọn kiểu Java.

### PostgreSQL

- `TIMESTAMP WITH TIME ZONE` (tên ngắn `timestamptz`) biểu diễn một instant. PostgreSQL chuẩn hóa thời điểm khi lưu; nó không giữ nguyên tên timezone hoặc offset gốc của input. Khi hiển thị, giá trị được chuyển theo timezone của session.
- `TIMESTAMP WITHOUT TIME ZONE` lưu các thành phần ngày giờ như một local date-time, không mang timezone.
- `DATE` lưu ngày lịch, không lưu thời gian trong ngày.

Với audit timestamp, `timestamptz` thường phù hợp hơn `timestamp without time zone` nếu cần biểu diễn thời điểm toàn cầu.

### MySQL

- `TIMESTAMP` có quy tắc chuyển đổi theo timezone của session/server khi lưu và đọc.
- `DATETIME` lưu các thành phần ngày giờ mà không tự biểu diễn một instant có timezone.

Hãy cấu hình timezone của connection/session nhất quán và kiểm tra mapping của R2DBC MySQL driver.

### SQL Server

- `datetimeoffset` lưu ngày giờ cùng offset.
- `datetime2` lưu ngày giờ không có offset.

Nếu cần giữ một instant và offset gốc, `datetimeoffset` có thể phù hợp; nếu lưu UTC theo quy ước, `datetime2` cũng có thể được dùng nhưng phải có hợp đồng rõ rằng giá trị luôn là UTC.

### Quy tắc chọn kiểu

| Ý nghĩa dữ liệu | Kiểu cột gợi ý |
|---|---|
| Audit event, created/modified instant | Kiểu timestamp có timezone/instant theo database |
| Ngày lịch, không có giờ | `DATE` |
| Giờ địa phương không gắn ngày | `TIME` |
| Lịch hẹn địa phương cần giữ giờ và zone | Lưu local date-time cùng zone ID, hoặc lưu instant cùng zone ID tùy nghiệp vụ |
| Timestamp do database sinh | Cột timestamp có default/trigger phù hợp và mapping read-only khi cần |

Tên kiểu SQL không bảo đảm driver luôn ánh xạ sang cùng một lớp Java. Hãy xác nhận kiểu trả về của R2DBC driver và dùng converter nếu cần.

## 9. Múi giờ của JVM, database và session

Một ứng dụng có thể chạy với timezone mặc định khác database server. Ngoài ra, mỗi connection database có thể có timezone session riêng. Điều này đặc biệt quan trọng khi dùng kiểu timestamp không có timezone hoặc khi database chuyển đổi lúc đọc/ghi.

Các nguyên tắc hữu ích:

- Dùng `Clock.systemUTC()` cho nguồn thời gian của application audit.
- Lưu audit timestamp theo instant hoặc kiểu cột có semantics tương đương.
- Cấu hình session timezone nhất quán nếu database driver có chuyển đổi theo session.
- Không phụ thuộc timezone mặc định của JVM để diễn giải timestamp.
- Chuyển sang `ZoneId` của người dùng ở tầng hiển thị.
- Nếu lưu lịch địa phương, lưu kèm zone ID thay vì chỉ lưu `LocalDateTime`.

Đừng nghĩ rằng đặt `-Duser.timezone=UTC` tự sửa mọi vấn đề. Nó thay đổi default timezone của JVM, nhưng không tự cấu hình database session, không thay đổi semantics của cột SQL và không đồng bộ đồng hồ giữa các máy.

## 10. Daylight Saving Time và giờ địa phương mơ hồ

Một số timezone có Daylight Saving Time (DST), tức đồng hồ địa phương chuyển tiến hoặc lùi theo mùa. Khi đồng hồ chuyển tiến, có thể tồn tại khoảng giờ địa phương không xảy ra. Khi đồng hồ chuyển lùi, một khoảng giờ có thể xuất hiện hai lần.

Ví dụ với một timezone có DST:

- Một local time nằm trong khoảng bị bỏ qua khi đồng hồ nhảy tới có thể không ánh xạ thành instant hợp lệ.
- Một local time trong khoảng lặp có thể tương ứng với hai instant khác nhau.

Java `ZoneId` và `ZoneRules` cung cấp thông tin để phát hiện những trường hợp này. Khi nhận lịch hẹn địa phương, ứng dụng cần quy định cách xử lý giờ không tồn tại hoặc giờ xuất hiện hai lần: từ chối, chọn offset trước/sau, hoặc yêu cầu người dùng chọn rõ.

Audit timestamp là thời điểm một sự kiện đã xảy ra; dùng `Instant` giúp tránh sự mơ hồ DST. Lịch hẹn trong tương lai lại có thể mang ý nghĩa “9 giờ sáng theo giờ địa phương”, vì vậy lưu `LocalDateTime` và `ZoneId` có thể đúng hơn việc chỉ lưu instant nếu quy tắc timezone thay đổi.

Không tự cộng hoặc trừ một giờ để xử lý DST. Quy tắc timezone thay đổi theo quốc gia và có thể được cập nhật theo dữ liệu IANA. Dùng `ZoneId`/`ZoneRules` thay vì hard-code offset.

## 11. Độ chính xác timestamp và sai khác khi round-trip

`Instant` có độ chính xác nanosecond trong Java, nhưng database hoặc driver có thể lưu ít chữ số phần thập phân hơn. PostgreSQL timestamp thường hỗ trợ tối đa microsecond precision; các database khác có precision và cấu hình riêng.

Ví dụ, ứng dụng tạo `2026-11-15T02:00:00.123456789Z`, nhưng cột chỉ lưu microseconds nên giá trị đọc lại có thể là `2026-11-15T02:00:00.123457Z` hoặc bị cắt theo quy tắc của database/driver.

Trong test, không nên so sánh nanosecond chính xác nếu schema chỉ lưu microseconds. Có thể chuẩn hóa độ chính xác trước khi so sánh:

```java
Instant expected = clock.instant().truncatedTo(ChronoUnit.MICROS);
```

Quy tắc làm tròn hay cắt phụ thuộc database. Hãy kiểm tra round-trip thực tế với driver đang dùng và chọn precision phù hợp trong schema.

## 12. Đồng bộ đồng hồ giữa các instance

Nếu dùng application clock, các instance cần có đồng hồ hệ điều hành được đồng bộ. Trong môi trường cloud hoặc container, đồng hồ thường dựa vào host/virtualization layer, nhưng vẫn cần giám sát clock skew và cấu hình NTP/chrony phù hợp.

Nếu instance A lệch nhanh 4 giây và instance B lệch chậm 3 giây, hai request được ghi liên tiếp có thể tạo timestamp đảo thứ tự so với thứ tự commit thực tế. Điều này ảnh hưởng báo cáo, audit trail và xử lý event nếu ứng dụng giả định timestamp là thứ tự tuyệt đối.

Ngay cả khi dùng database clock, cần đồng bộ đồng hồ database server và các node trong cluster. Database clock giúp tập trung nguồn thời gian cho một database, nhưng không tự bảo đảm thời gian vật lý chính xác nếu máy chủ database bị lệch.

Timestamp không nên được dùng làm khóa duy nhất hoặc bằng chứng tuyệt đối về thứ tự commit. Nếu cần thứ tự nghiệp vụ, dùng sequence, version, event offset hoặc khóa sắp thứ tự phù hợp. `created_at` có thể trùng nhau do độ chính xác của clock/database.

## 13. Cấu hình auditing với application clock UTC

Một cấu hình điển hình cho R2DBC:

```java
@Configuration
@EnableR2dbcAuditing(
    dateTimeProviderRef = "auditingDateTimeProvider",
    auditorAwareRef = "auditorAware"
)
public class AuditingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .defaultIfEmpty("system");
    }
}
```

`defaultIfEmpty("system")` là chính sách minh họa cho request không có người dùng đăng nhập. Trong ứng dụng thực tế, nên phân biệt system job, anonymous request và user request bằng identity phù hợp. Không dùng một auditor mặc định chung nếu cần audit trail có thể truy vết.

Schema tương ứng:

```sql
CREATE TABLE article (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(150),
    last_modified_by VARCHAR(150)
);
```

Trong mô hình này, application auditing là chủ sở hữu các cột thời gian và auditor. Không khai báo default hoặc trigger khác để ghi đè chúng nếu không có yêu cầu rõ ràng.

## 14. `@CreatedDate` và `@LastModifiedDate` được cập nhật khi nào?

Khi auditing được bật và entity được ghi qua cơ chế mapping Spring Data, callback auditing có thể điền các thuộc tính:

- `@CreatedDate` được thiết lập khi entity được nhận diện là mới.
- `@LastModifiedDate` được thiết lập khi entity được tạo hoặc sửa theo cấu hình `modifyOnCreate`.
- `@CreatedBy` được lấy từ `AuditorAware`/`ReactiveAuditorAware` khi tạo.
- `@LastModifiedBy` được cập nhật theo auditor hiện tại khi sửa.

`@EnableR2dbcAuditing` có tùy chọn như `modifyOnCreate` và `setDates`. Nếu muốn `@LastModifiedDate` được điền ngay lúc tạo, dùng mặc định `modifyOnCreate = true`; nếu muốn chỉ đặt trường này ở lần sửa sau, có thể cấu hình khác theo API của phiên bản Spring Data đang dùng.

Auditing callback chạy trong luồng lưu entity, không phải trigger database. Giá trị thời gian thường được xác định trước khi câu SQL ghi được thực thi. Vì vậy `@CreatedDate` không nhất thiết là thời điểm database commit; nó là thời điểm ứng dụng tạo metadata cho thao tác ghi.

## 15. Auditing callback không tự áp dụng cho mọi SQL trực tiếp

Nếu dùng `ReactiveCrudRepository` hoặc `R2dbcEntityTemplate`, Spring Data mapping callbacks có thể áp dụng auditing. Nhưng khi gọi SQL trực tiếp bằng `DatabaseClient`, ứng dụng đang kiểm soát câu SQL và không nên giả định các annotation auditing trên entity sẽ tự chạy.

Ví dụ SQL trực tiếp:

```java
public Mono<Long> insertArticle(String title, String actor, Instant now) {
    return databaseClient.sql("""
            INSERT INTO article (
                title, created_at, last_modified_at, created_by, last_modified_by
            )
            VALUES (
                :title, :createdAt, :modifiedAt, :createdBy, :modifiedBy
            )
            """)
        .bind("title", title)
        .bind("createdAt", now)
        .bind("modifiedAt", now)
        .bind("createdBy", actor)
        .bind("modifiedBy", actor)
        .fetch()
        .rowsUpdated();
}
```

Ở đây code phải cung cấp audit columns tường minh. Có thể inject `Clock` và `ReactiveAuditorAware` vào custom repository để dùng cùng nguồn thời gian/auditor, nhưng phải gọi chúng rõ ràng. Nếu database là chủ sở hữu timestamp, bỏ các cột khỏi câu insert để default/trigger thực hiện.

Không trộn `DatabaseClient` raw SQL với giả định `@CreatedDate` sẽ tự điền. Đây là nguồn lỗi thường gặp khi một phần repository dùng entity mapping và phần khác dùng SQL trực tiếp.

## 16. Chọn database clock khi cần một nguồn chung

Nếu nhiều ứng dụng hoặc công cụ ghi cùng một bảng và cần database làm nguồn thời gian, có thể dùng default:

```sql
CREATE TABLE audit_event (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Ứng dụng insert mà không cung cấp `created_at`:

```sql
INSERT INTO audit_event (event_type)
VALUES (:eventType)
RETURNING id, created_at;
```

Trong PostgreSQL, `CURRENT_TIMESTAMP`/`now()` trả thời điểm bắt đầu transaction, không phải lúc từng statement bắt đầu. Nếu cần thời điểm bắt đầu statement, PostgreSQL có `statement_timestamp()`; nếu cần đồng hồ wall-clock tại thời điểm hàm được gọi, có `clock_timestamp()`. Ba khái niệm này có semantics khác nhau khi transaction kéo dài.

Ví dụ trigger/default hoặc câu insert phải chọn đúng hàm theo yêu cầu. Nếu audit timestamp cần đại diện thời điểm transaction bắt đầu, `CURRENT_TIMESTAMP` có thể phù hợp. Nếu cần thời điểm của từng statement trong một transaction dài, `statement_timestamp()` có ý nghĩa khác. Không dùng `clock_timestamp()` chỉ vì tên nghe chính xác hơn; hãy xác định ý nghĩa nghiệp vụ trước.

Với SQL Server, có thể dùng `SYSUTCDATETIME()` hoặc hàm thời gian phù hợp; MySQL có các hàm `CURRENT_TIMESTAMP`/`UTC_TIMESTAMP` với semantics theo server/session. Đây là các ví dụ database-specific, không phải cú pháp portable.

## 17. Khi nào nên dùng trigger cho auditing?

Trigger có thể tự gán `created_at` hoặc `last_modified_at` cho mọi câu SQL ghi vào bảng, kể cả ghi từ ứng dụng khác không dùng Spring Data. Điều này hữu ích khi database là nguồn sự thật và có nhiều writer.

Ưu điểm:

- Mọi writer được áp dụng cùng quy tắc.
- Ứng dụng không cần tự điền timestamp ở từng câu SQL.
- Có thể bảo vệ cột audit khỏi việc ứng dụng ghi giá trị tùy ý.

Đổi lại:

- Logic thời gian nằm trong database, cần quản lý migration và kiểm thử trigger.
- Giá trị trigger tạo ra có thể không được trả tự động vào entity sau insert/update.
- Hành vi trigger khác giữa hệ quản trị.
- Nếu trigger ghi đè giá trị application auditing, cần hiểu rõ nguồn nào là chủ sở hữu.

Nếu cần giá trị trigger ngay trong response, dùng `RETURNING`/`OUTPUT` khi database hỗ trợ hoặc đọc lại hàng sau thao tác ghi. Đánh dấu cột read-only trong mapping khi ứng dụng không được ghi cột đó, nhưng không nhầm annotation này với cơ chế tự lấy giá trị sau ghi.

## 18. Tránh trộn application clock và database clock không có quy tắc

Một thiết kế dễ gây khó hiểu là:

- `@CreatedDate` dùng `Clock.systemUTC()`.
- `created_at` có default `CURRENT_TIMESTAMP`.
- Trigger lại ghi đè `created_at`.
- Một số repository dùng `DatabaseClient` tự truyền `LocalDateTime.now()`.

Kết quả có thể khác nhau tùy đường ghi. Có hàng được ghi theo clock của application, hàng khác theo database, một số timestamp không có timezone, số khác lại mang semantics instant.

Hãy lập quy ước cho từng cột:

| Cột | Chủ sở hữu đề xuất | Quy tắc |
|---|---|---|
| `created_at` | Application hoặc database, chọn một | Không để hai tầng ghi đè lẫn nhau |
| `last_modified_at` | Application hoặc database, chọn một | Cùng quy tắc với mọi đường update |
| `created_by` | Application/security context | Database thường không biết user nghiệp vụ |
| `last_modified_by` | Application/security context | Dùng auditor nhất quán cho API và background job |
| `scheduled_local_time` | Domain/application | Lưu local time cùng `ZoneId` nếu cần bảo toàn lịch địa phương |

Database clock có thể là nguồn cho timestamp, còn application vẫn là nguồn cho auditor. Đây là kết hợp hợp lý nếu hợp đồng cột được ghi rõ. Không nhất thiết tất cả metadata phải cùng một nguồn, nhưng mỗi loại cần một chủ sở hữu xác định.

## 19. Kiểm thử với Clock.fixed

`Clock.fixed` trả về cùng một instant trong mọi lần gọi. Đây là cách đơn giản để kiểm thử logic thời gian:

```java
@Test
void createsArticleWithExpectedTimestamp() {
    Instant fixedInstant = Instant.parse("2026-11-15T02:00:00Z");
    Clock fixedClock = Clock.fixed(fixedInstant, ZoneOffset.UTC);

    DateTimeProvider provider = () -> Optional.of(fixedClock.instant());

    assertThat(provider.getNow()).contains(fixedInstant);
}
```

Test này kiểm tra nguồn thời gian, chưa kiểm tra toàn bộ auditing callback. Với integration test, hãy inject fixed clock vào Spring context rồi lưu entity qua Repository và xác nhận các trường `@CreatedDate`/`@LastModifiedDate` đúng giá trị.

`Clock.fixed` phù hợp khi test chỉ cần một thời điểm. Nếu cần kiểm tra thời gian thay đổi giữa lần tạo và lần cập nhật, dùng một clock có thể điều chỉnh được.

## 20. Tạo AdjustableClock để kiểm thử created/modified time

Một clock test có thể giữ instant trong `AtomicReference` và cho phép test tiến thời gian:

```java
public final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public AdjustableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(initial), zone);
    }

    private AdjustableClock(AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    public void set(Instant instant) {
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

Ví dụ kiểm thử auditing end-to-end với Repository:

```java
@Test
void auditingUsesClockForCreateAndUpdate() {
    Instant created = Instant.parse("2026-11-15T02:00:00Z");
    Instant modified = Instant.parse("2026-11-15T03:00:00Z");
    AtomicReference<Long> articleId = new AtomicReference<>();
    adjustableClock.set(created);

    StepVerifier.create(articleRepository.save(new Article("First title")))
        .assertNext(saved -> {
            articleId.set(saved.getId());
            assertThat(saved.getCreatedAt()).isEqualTo(created);
            assertThat(saved.getLastModifiedAt()).isEqualTo(created);
        })
        .verifyComplete();

    adjustableClock.set(modified);

    StepVerifier.create(articleRepository.findById(articleId.get())
        .flatMap(article -> {
            article.setTitle("Updated title");
            return articleRepository.save(article);
        }))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isEqualTo(created);
            assertThat(saved.getLastModifiedAt()).isEqualTo(modified);
        })
        .verifyComplete();
}
```

Đây là khung test cần được điều chỉnh theo constructor, kiểu entity, repository và fixture của dự án. Test context phải dùng đúng `AdjustableClock` bean mà `DateTimeProvider` đang inject. Ví dụ giữ ID được sinh từ kết quả insert trong `AtomicReference` để dùng cho bước cập nhật tiếp theo.

## 21. Kiểm thử auditor theo reactive security context

Nếu `ReactiveAuditorAware` đọc Spring Security context, test cần thiết lập context trong Reactor chain. Không nên chỉ đặt `SecurityContextHolder` imperative rồi mong reactive context tự nhận giá trị.

Ví dụ khung test:

```java
Authentication authentication =
    new UsernamePasswordAuthenticationToken("alice", "n/a", List.of());

Mono<Article> save = articleRepository.save(new Article("Audited"))
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication));

StepVerifier.create(save)
    .assertNext(saved -> assertThat(saved.getCreatedBy()).isEqualTo("alice"))
    .verifyComplete();
```

Để test đúng, auditor provider phải dùng `ReactiveSecurityContextHolder` và entity phải có `@CreatedBy`. Nếu request không có authentication, kiểm tra chính sách fallback hoặc trường hợp không có auditor.

## 22. StepVerifier virtual time không tự điều khiển Clock

`StepVerifier.withVirtualTime(...)` và `VirtualTimeScheduler` điều khiển thời gian của các toán tử Reactor dựa trên scheduler, ví dụ `delay`, `interval` hoặc `timeout`. Chúng không tự làm `Clock.systemUTC()` chạy nhanh hoặc dừng lại.

Ví dụ:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
    )
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

Đoạn test này tiến virtual scheduler một giờ mà không chờ thật. Nếu code bên trong gọi `clock.instant()`, nó vẫn nhận giá trị từ clock bean. Muốn kiểm soát auditing timestamp, hãy inject `Clock.fixed` hoặc `AdjustableClock` riêng.

Đây là hai khái niệm khác nhau:

- Reactor virtual time: điều khiển lịch phát tín hiệu của scheduler.
- Java Clock test double: điều khiển giá trị ngày giờ mà domain/auditing đọc.

Không dùng `Thread.sleep()` để chờ thời gian trong test. Dùng virtual time cho toán tử Reactor và clock giả cho logic thời gian nghiệp vụ.

## 23. Kiểm thử round-trip với database thật

Unit test với fixed clock chưa xác nhận database lưu và trả timestamp đúng. Integration test cần kiểm tra:

- `Instant` được ghi vào đúng kiểu cột.
- Giá trị đọc lại biểu diễn cùng instant.
- Timezone của session không làm thay đổi ý nghĩa thời điểm.
- Precision của cột không làm test thất bại do nanosecond/microsecond khác nhau.
- Default/trigger database có được áp dụng khi bỏ cột khỏi câu insert.
- Generated timestamp được trả qua `RETURNING`/`OUTPUT` hoặc được đọc lại đúng cách.
- `@ReadOnlyProperty` không đưa cột database-managed vào insert/update.
- `DatabaseClient` raw SQL không vô tình bỏ qua auditing mà ứng dụng cần.

Khi test cột do database sinh, không nhất thiết phải so sánh với một instant cố định của application clock. Có thể ghi thời điểm trước/sau thao tác và xác nhận giá trị nằm trong khoảng hợp lý, đồng thời kiểm tra default/trigger bằng query trực tiếp. Nếu cần tính xác định tuyệt đối, hãy thiết kế SQL hoặc trigger test có thể kiểm soát đầu vào thay vì dựa vào đồng hồ thật.

## 24. Kiểm thử timezone và DST

Đối với audit timestamp, test nên xác nhận cùng một instant được chuyển đổi chính xác qua các timezone:

```java
Instant instant = Instant.parse("2026-11-15T02:00:00Z");

ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime utc = instant.atZone(ZoneOffset.UTC);

assertThat(hcm.toInstant()).isEqualTo(instant);
assertThat(utc.toInstant()).isEqualTo(instant);
```

Với lịch địa phương, test các thời điểm quanh chuyển đổi DST của timezone có áp dụng DST. Dùng `ZoneRules.getValidOffsets(localDateTime)` để biết local time có 0, 1 hay 2 offset hợp lệ:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
```

Trong ví dụ, ngày/giờ cần được chọn phù hợp với bộ timezone database của môi trường test. Không hard-code giả định rằng mọi năm hoặc mọi vùng đều đổi DST cùng ngày. Test nên lấy `ZoneRules` làm nguồn sự thật.

Nếu local time không có offset hợp lệ, ứng dụng phải có chính sách xử lý. Nếu có hai offset, cần chọn rõ một offset hoặc yêu cầu input xác định. Audit event đã xảy ra nên dùng `Instant`, không dùng local time mơ hồ.

## 25. Test auditing khi dùng DatabaseClient trực tiếp

Các lệnh SQL trực tiếp không tự chạy auditing callback của entity. Vì vậy, nếu custom repository tự ghi audit column, hãy test giá trị được bind:

```java
public Mono<Long> insertEvent(String type, String actor) {
    Instant now = clock.instant();

    return databaseClient.sql("""
            INSERT INTO audit_event(event_type, created_at, created_by)
            VALUES (:type, :createdAt, :createdBy)
            """)
        .bind("type", type)
        .bind("createdAt", now)
        .bind("createdBy", actor)
        .fetch()
        .rowsUpdated();
}
```

Test có thể inject fixed clock, gọi method, rồi query lại `audit_event` để xác nhận `created_at` và `created_by`. Nếu SQL dùng default database clock, test phải xác nhận cột bị bỏ khỏi insert và database tự sinh giá trị.

Đừng chỉ test `@CreatedDate` trên entity rồi suy ra mọi câu `DatabaseClient.sql(...)` đều được audit. Mỗi đường ghi cần được kiểm tra theo cơ chế thực tế của nó.

## 26. Timestamp audit không phải thứ tự commit tuyệt đối

Hai transaction có thể được cấp timestamp gần như cùng lúc, nhưng commit theo thứ tự khác nhau. Application clock có thể lệch giữa instance; database clock có thể có độ chính xác giới hạn; timestamp transaction-start có thể sớm hơn thời điểm commit đáng kể.

Nếu cần thứ tự thay đổi của một entity, dùng `@Version` hoặc một sequence/version phù hợp. Nếu cần thứ tự sự kiện trong một log phân tán, dùng event offset, sequence theo partition hoặc metadata của hệ thống message. Không dùng `created_at` làm cơ chế concurrency control.

`@LastModifiedDate` hữu ích để hiển thị thời điểm cập nhật gần nhất và lọc dữ liệu thay đổi gần đây. Nó không thay thế optimistic locking và không chứng minh rằng một update là update mới nhất nếu nhiều writer cạnh tranh.

## 27. Lưu ý khi dùng auditing trong batch và bulk update

Khi lưu từng entity qua Repository hoặc Template, auditing callback có thể được áp dụng theo từng entity. Nhưng một câu bulk update bằng `DatabaseClient` như:

```sql
UPDATE article
SET status = :status
WHERE status = :oldStatus;
```

không tự chạy callback `@LastModifiedDate` cho từng entity. Nếu cần cập nhật audit timestamp, câu SQL phải cập nhật `last_modified_at` rõ ràng hoặc database trigger phải đảm nhận.

Với bulk update lớn, database clock có thể thuận tiện để tất cả hàng được cập nhật cùng một mốc thời gian. Nếu dùng application clock, bind cùng một `Instant` vào câu lệnh để tất cả hàng có timestamp giống nhau. Chọn semantics theo yêu cầu báo cáo và audit.

Đối với nhiều batch, nếu mỗi batch gọi `clock.instant()` riêng, timestamp có thể khác nhau giữa các nhóm. Điều đó thường hợp lý nếu muốn ghi thời điểm xử lý từng batch. Nếu toàn bộ import cần một mốc chung, lấy instant một lần ở đầu job và truyền vào mọi batch; cần phân biệt `job_started_at` với `row_created_at`.

## 28. Các lỗi thường gặp khi chọn nguồn thời gian

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Timestamp lệch vài giờ khi hiển thị | Nhầm instant với local time hoặc session timezone khác | Lưu instant/UTC và chuyển đổi ở tầng hiển thị |
| Test lúc pass lúc fail | Dùng clock thật và so sánh chính xác thời điểm | Inject `Clock.fixed` hoặc `AdjustableClock` |
| `@CreatedDate` không được điền | Chưa bật auditing hoặc entity không đi qua callback mapping | Kiểm tra `@EnableR2dbcAuditing`, entity metadata và đường ghi |
| `DatabaseClient` insert thiếu audit fields | Raw SQL không tự chạy entity auditing callback | Bind audit values hoặc dùng default/trigger database |
| Cột default nhận null | Câu insert truyền null tường minh | Bỏ cột khỏi insert hoặc dùng `DEFAULT` đúng dialect |
| Cột generated bị lỗi khi insert | Ứng dụng cố ghi vào generated column | Đánh dấu read-only và bỏ cột khỏi câu ghi |
| Timestamp khác nhau giữa instance | Clock skew hoặc timezone/default configuration khác | Đồng bộ NTP, dùng UTC và cân nhắc database clock |
| So sánh timestamp thất bại sau khi đọc lại | Database giảm precision | Chuẩn hóa precision trong test và schema |
| Lịch hẹn sai một giờ quanh DST | Lưu local time mà không giữ zone/offset | Lưu `ZoneId` và xác định chính sách DST |
| `LastModifiedDate` không đổi khi bulk update | Bulk SQL bỏ qua auditing callback | Cập nhật cột trong SQL hoặc dùng trigger |

## 29. Quy trình thiết kế auditing thời gian

Khi triển khai auditing cho một ứng dụng R2DBC, hãy thực hiện theo trình tự:

**Bước 1 — Xác định ý nghĩa cột.** Phân biệt audit instant, ngày nghiệp vụ, giờ địa phương và lịch hẹn.

**Bước 2 — Chọn nguồn có thẩm quyền.** Quyết định application clock hay database clock cho từng cột; không để nhiều tầng ghi đè nhau không có quy tắc.

**Bước 3 — Chọn kiểu Java và SQL.** Dùng `Instant` cho audit event; chọn kiểu timestamp SQL phù hợp và xác nhận mapping driver.

**Bước 4 — Chuẩn hóa UTC.** Dùng `Clock.systemUTC()`, đồng bộ đồng hồ host/database và chuyển đổi sang timezone người dùng khi hiển thị.

**Bước 5 — Bật auditing.** Cấu hình `@EnableR2dbcAuditing`, `DateTimeProvider`, `ReactiveAuditorAware` và các annotation trên entity.

**Bước 6 — Xác định đường ghi.** Repository/Template có callback auditing; raw SQL cần tự cung cấp audit fields hoặc dùng database default/trigger.

**Bước 7 — Kiểm thử thời gian.** Dùng `Clock.fixed` hoặc clock điều khiển được; dùng virtual time riêng cho Reactor scheduler.

**Bước 8 — Kiểm thử database.** Xác nhận round-trip, timezone session, precision, default và trigger trên database/driver thực tế.

**Bước 9 — Kiểm tra vận hành.** Theo dõi clock skew, timezone configuration và quy tắc retention/audit.

## 30. Kết luận

Auditing thời gian đáng tin cậy bắt đầu từ việc xác định rõ nguồn thời gian và ý nghĩa của dữ liệu. Với Spring Data R2DBC, `@EnableR2dbcAuditing`, `@CreatedDate`, `@LastModifiedDate` và `DateTimeProvider` giúp ứng dụng điền timestamp theo một nguồn tập trung; `ReactiveAuditorAware` cung cấp người thực hiện trong reactive context. Inject `Clock` thay vì gọi đồng hồ hệ thống rải rác giúp test có thể điều khiển thời gian.

Với audit event, `Instant` và quy ước UTC thường dễ trao đổi giữa nhiều service hơn local date-time. Hãy chọn kiểu cột theo semantics database, hiểu timezone session và precision của driver, đồng thời tách lịch địa phương khỏi thời điểm tuyệt đối. Application clock thuận tiện và dễ test; database clock hữu ích khi cần một nguồn chung cho nhiều writer. Chọn một chủ sở hữu cho từng cột audit và kiểm thử cả callback Spring Data lẫn các đường SQL trực tiếp để timestamp không bị thiếu hoặc ghi đè ngoài ý muốn.
