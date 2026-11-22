# Ánh xạ thời gian bằng LocalDate, LocalDateTime, Instant và múi giờ trong Spring Data JPA

Ứng dụng Java thường phải lưu ngày sinh, ngày thanh toán, giờ mở cửa, thời điểm tạo bản ghi và lịch hẹn theo múi giờ của người dùng. Các giá trị này trông giống nhau nhưng biểu diễn những khái niệm khác nhau. Chọn sai kiểu thời gian có thể khiến dữ liệu lệch ngày, sai giờ khi triển khai ở máy chủ có múi giờ khác hoặc sai lịch khi khu vực chuyển sang giờ mùa hè (Daylight Saving Time - DST).

Java cung cấp API ngày giờ hiện đại trong package java.time. Spring Data JPA làm việc với các kiểu này thông qua JPA provider, thường là Hibernate. Bài học này giải thích cách chọn kiểu, ánh xạ xuống database, chuyển đổi múi giờ, viết entity/repository và kiểm thử.

## 1. Phân biệt ngày, giờ địa phương và thời điểm tuyệt đối

Trước khi chọn kiểu Java, hãy xác định ý nghĩa nghiệp vụ của dữ liệu.

- Ngày sinh như 2000-05-20 chỉ là một ngày trên lịch. Không cần múi giờ.
- Giờ mở cửa như 08:30 là giờ trên đồng hồ địa phương. Cần biết địa điểm hoặc múi giờ nếu muốn chuyển thành thời điểm cụ thể.
- Thời điểm một giao dịch được tạo là một điểm duy nhất trên dòng thời gian. Có thể biểu diễn bằng Instant.
- Lịch hẹn lúc 09:00 tại Ho Chi Minh City mang ý nghĩa giờ địa phương tại một khu vực. Nếu lưu lịch hẹn trong tương lai, nên giữ cả ngày giờ địa phương và ZoneId để áp dụng đúng quy tắc múi giờ.

Bốn kiểu quan trọng:

| Kiểu Java | Biểu diễn | Có chứa múi giờ/offset? | Trường hợp phù hợp |
|---|---|---|---|
| LocalDate | Ngày lịch, ví dụ 2026-11-09 | Không | Ngày sinh, ngày hóa đơn, ngày nghỉ |
| LocalTime | Giờ trên đồng hồ, ví dụ 09:30 | Không | Giờ mở cửa, giờ bắt đầu trong ngày |
| LocalDateTime | Ngày và giờ địa phương, ví dụ 2026-11-09T09:30 | Không | Giờ địa phương cần kết hợp với một ZoneId riêng |
| Instant | Một thời điểm tuyệt đối trên timeline UTC | Không lưu múi giờ hiển thị; giá trị là instant | Thời điểm tạo, cập nhật, thanh toán, log sự kiện |

Các kiểu liên quan khác:

- OffsetDateTime chứa ngày giờ cùng offset cố định như +07:00.
- ZonedDateTime chứa ngày giờ cùng ZoneId có quy tắc múi giờ như Asia/Ho_Chi_Minh hoặc Europe/Paris.
- ZoneId đại diện vùng địa lý và bộ quy tắc thay đổi offset theo thời gian.
- ZoneOffset là độ lệch UTC cụ thể, ví dụ +07:00 hoặc -05:00.

Không nên xem LocalDateTime là Instant. LocalDateTime không cho biết nó thuộc múi giờ nào nên không thể xác định một thời điểm tuyệt đối nếu thiếu ZoneId hoặc offset.

## 2. Quy tắc chọn kiểu dữ liệu

Có thể sử dụng các quy tắc sau:

1. Chỉ cần ngày: dùng LocalDate.
2. Chỉ cần giờ trên đồng hồ: dùng LocalTime.
3. Cần giữ giờ địa phương nhưng ngữ cảnh múi giờ được quản lý riêng: dùng LocalDateTime và lưu ZoneId.
4. Cần ghi nhận một thời điểm đã xảy ra: dùng Instant.
5. Cần giữ offset mà client gửi: cân nhắc OffsetDateTime.
6. Cần biểu diễn thời gian theo quy tắc của một vùng địa lý: dùng ZonedDateTime trong tầng ứng dụng; nếu phải lưu ZoneId, hãy lưu rõ ZoneId vì database không phải lúc nào cũng giữ nguyên vùng địa lý đó.

Ví dụ:

~~~java
LocalDate birthday = LocalDate.of(2000, 5, 20);
LocalTime openingTime = LocalTime.of(8, 30);
LocalDateTime localMeeting = LocalDateTime.of(2026, 11, 9, 9, 30);
Instant createdAt = Instant.now();
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meetingInZone = localMeeting.atZone(zone);
Instant meetingInstant = meetingInZone.toInstant();
~~~

LocalDate, LocalTime và LocalDateTime không tự chứa timezone. Không dùng ZoneId.systemDefault() để suy đoán múi giờ nghiệp vụ, vì kết quả có thể thay đổi giữa máy phát triển, máy chủ và môi trường triển khai.

## 3. Ánh xạ java.time xuống kiểu SQL

Hibernate và JDBC provider ánh xạ các kiểu ngày giờ sang kiểu dữ liệu SQL tương ứng. Bảng dưới đây mô tả ánh xạ thường gặp; kiểu SQL cụ thể và cách lưu offset có thể phụ thuộc database, dialect, JDBC driver và phiên bản Hibernate.

| Kiểu Java | Kiểu SQL thường dùng | Ý nghĩa |
|---|---|---|
| LocalDate | DATE | Ngày lịch, không có giờ |
| LocalTime | TIME | Giờ trong ngày, không có ngày/múi giờ |
| LocalDateTime | TIMESTAMP | Ngày giờ dạng local, không chứa timezone |
| Instant | Kiểu timestamp biểu diễn UTC, Hibernate 6 có kiểu JDBC TIMESTAMP_UTC | Thời điểm tuyệt đối |
| OffsetDateTime | Timestamp có offset hoặc được chuẩn hóa theo cấu hình/provider | Ngày giờ kèm offset |
| ZonedDateTime | Phụ thuộc dialect và chiến lược lưu timezone của Hibernate | Ngày giờ kèm ZoneId trong Java |

Một số khác biệt ở database:

- PostgreSQL: timestamp with time zone (timestamptz) lưu một instant và hiển thị theo timezone của session; nó không giữ lại ZoneId gốc như Europe/Paris. timestamp without time zone chỉ lưu ngày giờ local.
- MySQL: TIMESTAMP chuyển đổi theo timezone của session khi ghi/đọc; DATETIME lưu giá trị ngày giờ mà không tự chuyển đổi timezone.
- H2: hỗ trợ các kiểu ngày giờ SQL, nhưng hành vi và độ chính xác cần kiểm tra theo phiên bản H2/JDBC đang dùng.

Vì vậy, không nên chỉ nhìn tên kiểu SQL để kết luận database đang giữ múi giờ ban đầu. Nếu cần biết người dùng đã chọn vùng nào, hãy lưu ZoneId riêng, chẳng hạn Asia/Ho_Chi_Minh.

## 4. Ánh xạ trong entity JPA

JPA hiện đại hỗ trợ các kiểu java.time phổ biến. Hibernate trong Spring Boot hỗ trợ trực tiếp LocalDate, LocalTime, LocalDateTime và Instant. Thông thường không cần AttributeConverter cho những kiểu này.

Ví dụ entity:

~~~java
package com.example.appointment;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "appointments")
public class Appointment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "service_date", nullable = false)
    private LocalDate serviceDate;

    @Column(name = "opening_time", nullable = false)
    private LocalTime openingTime;

    @Column(name = "local_start", nullable = false)
    private LocalDateTime localStart;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Appointment() {
    }

    public Appointment(
            LocalDate serviceDate,
            LocalTime openingTime,
            LocalDateTime localStart,
            Instant createdAt) {
        this.serviceDate = serviceDate;
        this.openingTime = openingTime;
        this.localStart = localStart;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public LocalDate getServiceDate() {
        return serviceDate;
    }

    public LocalTime getOpeningTime() {
        return openingTime;
    }

    public LocalDateTime getLocalStart() {
        return localStart;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Các điểm cần nhớ:

- @Entity đánh dấu lớp được JPA quản lý.
- @Column cho phép đặt tên cột và ràng buộc nullability.
- LocalDate thường ánh xạ thành DATE.
- LocalTime thường ánh xạ thành TIME.
- LocalDateTime thường ánh xạ thành TIMESTAMP không có timezone.
- Instant được Hibernate ánh xạ như một thời điểm UTC; kiểu SQL vật lý phụ thuộc dialect và database.
- Constructor không tham số với visibility public hoặc protected là yêu cầu của JPA.
- Không dùng @Temporal cho LocalDate, LocalTime, LocalDateTime hoặc Instant. @Temporal dành cho các kiểu legacy như java.util.Date và Calendar.

Không nên thêm columnDefinition tùy tiện chỉ để ép một kiểu timestamp cụ thể. Nếu schema phải dùng kiểu SQL riêng, hãy đồng bộ entity mapping, migration và database dialect rồi kiểm thử với đúng hệ quản trị.

## 5. Lưu thời điểm tuyệt đối bằng Instant

Instant biểu diễn một điểm trên dòng thời gian, độc lập với timezone hiển thị. Ví dụ cùng một Instant có thể được trình bày thành giờ khác nhau tại Việt Nam, Nhật Bản hoặc Mỹ.

~~~java
Instant now = Instant.now();

System.out.println(now);
System.out.println(now.toEpochMilli());
~~~

Kết quả sẽ phụ thuộc thời điểm chạy. Chuỗi Instant thường có hậu tố Z, biểu thị UTC, ví dụ:

~~~text
2026-11-09T02:30:00Z
~~~

Để hiển thị cùng thời điểm tại một vùng:

~~~java
Instant instant = Instant.parse("2026-11-09T02:30:00Z");

ZonedDateTime vietnamTime =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime tokyoTime =
        instant.atZone(ZoneId.of("Asia/Tokyo"));

System.out.println(vietnamTime);
System.out.println(tokyoTime);
~~~

Hai kết quả có cùng instant nhưng giờ địa phương khác nhau. Đừng lưu giờ hiển thị của một vùng vào cột Instant; hãy lưu Instant và chuyển đổi ở ranh giới API/UI.

### Tự động gán thời điểm tạo

Có thể dùng Clock để việc ghi nhận thời gian dễ kiểm thử:

~~~java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Service sử dụng Clock:

~~~java
@Service
public class AppointmentService {

    private final AppointmentRepository repository;
    private final Clock clock;

    public AppointmentService(
            AppointmentRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Appointment create(
            LocalDate date,
            LocalTime time,
            LocalDateTime localStart) {
        Appointment appointment = new Appointment(
                date,
                time,
                localStart,
                clock.instant()
        );
        return repository.save(appointment);
    }
}
~~~

Clock.systemUTC() giúp nguồn thời gian rõ ràng và có thể thay bằng Clock.fixed() trong test. Không nên phụ thuộc trực tiếp vào timezone mặc định của máy chủ để tạo timestamp nghiệp vụ.

## 6. LocalDateTime không tự mang timezone

LocalDateTime chỉ lưu năm, tháng, ngày, giờ, phút, giây và phần thập phân giây. Ví dụ:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 9, 9, 30);
~~~

Giá trị này chỉ có nghĩa "09:30 ngày 09/11/2026". Nó không cho biết 09:30 tại Ho Chi Minh City, London hay Tokyo.

Khi ghi LocalDateTime vào cột TIMESTAMP không timezone, database lưu đúng các thành phần ngày giờ. Khi đọc lại, ứng dụng nhận được LocalDateTime tương ứng. Không có chuyển đổi UTC tự động nào có thể suy ra đúng ý nghĩa nghiệp vụ nếu thiếu ZoneId.

Sai lầm thường gặp:

~~~java
// Không đủ thông tin để coi local là một instant.
Instant wrongAssumption = local.toInstant(ZoneOffset.UTC);
~~~

Đoạn code trên giả định giá trị local vốn là UTC. Chỉ dùng khi nghiệp vụ xác định rõ localStart được nhập theo UTC. Nếu người dùng nhập giờ địa phương, cần ZoneId:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant correctInstant = local.atZone(zone).toInstant();
~~~

## 7. Chuyển đổi giữa LocalDateTime, ZonedDateTime và Instant

Các thao tác chuyển đổi phổ biến:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime local =
        LocalDateTime.of(2026, 11, 9, 9, 30);

// Gắn quy tắc vùng múi giờ vào ngày giờ local.
ZonedDateTime zoned = local.atZone(zone);

// Chuyển thành instant tuyệt đối.
Instant instant = zoned.toInstant();

// Từ instant chuyển lại giờ địa phương.
LocalDateTime convertedBack =
        instant.atZone(zone).toLocalDateTime();

// Lấy offset cụ thể tại thời điểm đó.
ZoneOffset offset = zoned.getOffset();
~~~

Ý nghĩa:

- atZone(zone) diễn giải LocalDateTime trong vùng múi giờ đã chọn.
- toInstant() chuyển thời điểm đã có timezone thành instant UTC.
- instant.atZone(zone) trình bày instant theo quy tắc của vùng.
- getOffset() trả về độ lệch UTC áp dụng tại thời điểm cụ thể đó.

Một ZoneId có thể có nhiều ZoneOffset theo lịch sử và quy tắc DST. Không thay ZoneId bằng một offset cố định nếu ứng dụng cần xử lý lịch tương lai.

## 8. Múi giờ và giờ mùa hè (DST)

ZoneId như Europe/Paris chứa quy tắc thay đổi offset theo thời gian. Trong khi đó ZoneOffset như +01:00 chỉ là độ lệch cố định, không biết khi nào chuyển sang +02:00.

Khi đồng hồ địa phương chuyển sang giờ mùa hè, có hai tình huống đặc biệt:

1. Gap: một khoảng giờ địa phương không tồn tại vì đồng hồ nhảy tới trước. Ví dụ một thời điểm 02:30 có thể bị bỏ qua.
2. Overlap: một khoảng giờ địa phương xuất hiện hai lần vì đồng hồ lùi lại. Cùng một LocalDateTime có thể tương ứng với hai instant khác nhau.

Java xử lý mặc định khi gọi LocalDateTime.atZone(zone): gap được điều chỉnh về thời điểm hợp lệ tiếp theo; overlap chọn offset sớm hơn theo quy tắc của API. Hành vi mặc định có thể không phù hợp với nghiệp vụ đặt lịch cần chính xác.

Có thể kiểm tra các offset hợp lệ trước khi chuyển đổi:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

List<ZoneOffset> validOffsets =
        zone.getRules().getValidOffsets(local);

if (validOffsets.isEmpty()) {
    throw new DateTimeException(
            "Giờ địa phương không tồn tại do chuyển DST");
}

if (validOffsets.size() > 1) {
    // Người dùng hoặc quy tắc nghiệp vụ phải chọn offset.
    throw new DateTimeException(
            "Giờ địa phương bị lặp; cần chọn offset");
}

Instant instant = local.atOffset(validOffsets.get(0)).toInstant();
~~~

Trong ví dụ, ngày và vùng được chọn để minh họa; số lượng offset hợp lệ phụ thuộc dữ liệu timezone của ngày đó. Khi ứng dụng hỗ trợ nhiều vùng địa lý, cần xác định chính sách cho gap và overlap thay vì để mặc định quyết định thay người dùng.

## 9. Lưu lịch hẹn tương lai: lưu cả giờ local và ZoneId

Đối với một sự kiện đã xảy ra, Instant thường là dữ liệu chuẩn nhất. Đối với lịch hẹn trong tương lai, chỉ lưu Instant có thể không đủ nếu quy tắc địa phương thay đổi hoặc nghiệp vụ muốn giữ nguyên "09:00 giờ địa phương".

Một mô hình thường dùng là lưu:

- scheduledLocalTime: ngày giờ người dùng chọn.
- timeZoneId: vùng địa lý, ví dụ Asia/Ho_Chi_Minh.
- scheduledAt: instant đã tính theo quy tắc timezone tại thời điểm tạo hoặc xác nhận.
- createdAt: thời điểm bản ghi được tạo.

Ví dụ entity:

~~~java
@Entity
@Table(name = "bookings")
public class Booking {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "scheduled_local_time", nullable = false)
    private LocalDateTime scheduledLocalTime;

    @Column(name = "time_zone_id", nullable = false, length = 64)
    private String timeZoneId;

    @Column(name = "scheduled_at", nullable = false)
    private Instant scheduledAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Booking() {
    }

    public Booking(
            LocalDateTime scheduledLocalTime,
            String timeZoneId,
            Instant scheduledAt,
            Instant createdAt) {
        this.scheduledLocalTime = scheduledLocalTime;
        this.timeZoneId = timeZoneId;
        this.scheduledAt = scheduledAt;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getScheduledLocalTime() {
        return scheduledLocalTime;
    }

    public String getTimeZoneId() {
        return timeZoneId;
    }

    public Instant getScheduledAt() {
        return scheduledAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Repository:

~~~java
public interface BookingRepository extends JpaRepository<Booking, Long> {

    List<Booking> findByScheduledAtGreaterThanEqualAndScheduledAtLessThan(
            Instant from,
            Instant to);
}
~~~

Service chuyển đổi giờ địa phương sang instant:

~~~java
@Service
public class BookingService {

    private final BookingRepository repository;
    private final Clock clock;

    public BookingService(BookingRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Booking create(
            LocalDateTime localStart,
            String zoneIdText) {
        ZoneId zone = ZoneId.of(zoneIdText);
        ZonedDateTime zonedStart = localStart.atZone(zone);

        Booking booking = new Booking(
                localStart,
                zone.getId(),
                zonedStart.toInstant(),
                clock.instant()
        );

        return repository.save(booking);
    }
}
~~~

Đoạn service sử dụng quy tắc mặc định của atZone(). Với hệ thống đặt lịch cần xử lý DST nghiêm ngặt, hãy kiểm tra gap/overlap như phần trước và yêu cầu lựa chọn offset khi cần.

Lưu cả local time và instant giúp đáp ứng hai nhu cầu: hiển thị đúng giờ người dùng đã chọn và sắp xếp/thực thi lịch theo timeline. Cần xác định chính sách nếu cơ quan quản lý thay đổi quy tắc timezone sau khi lịch được tạo: giữ instant đã xác nhận hay tính lại theo giờ địa phương. Đây là quyết định nghiệp vụ, không phải quyết định tự động của JPA.

## 10. Truy vấn dữ liệu theo ngày địa phương

Giả sử muốn tìm các booking diễn ra trong một ngày tại một vùng cụ thể. Không nên cộng cố định 24 giờ vào instant bắt đầu vì ngày DST có thể dài 23 hoặc 25 giờ.

Hãy tính đầu ngày và đầu ngày tiếp theo theo cùng ZoneId:

~~~java
LocalDate date = LocalDate.of(2026, 11, 9);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = date.atStartOfDay(zone).toInstant();
Instant to = date.plusDays(1).atStartOfDay(zone).toInstant();

List<Booking> bookings =
        repository.findByScheduledAtGreaterThanEqualAndScheduledAtLessThan(
                from, to);
~~~

Khoảng truy vấn là [from, to): bao gồm đầu ngày, không bao gồm đầu ngày kế tiếp. Cách này tránh một bản ghi đúng nửa đêm bị tính vào hai ngày liền kề. Dùng atStartOfDay(zone) để Java áp dụng quy tắc timezone của ngày tương ứng.

Nếu dữ liệu nghiệp vụ được lưu thuần LocalDateTime theo một vùng duy nhất, có thể truy vấn trực tiếp theo LocalDateTime. Tuy nhiên, không trộn LocalDateTime của nhiều múi giờ trong cùng một cột mà không có ZoneId đi kèm.

## 11. Cấu hình timezone cho JDBC và Hibernate

Trong Spring Boot, có thể đặt timezone cho thao tác JDBC timestamp:

~~~properties
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
~~~

Cấu hình này yêu cầu Hibernate sử dụng timezone UTC khi làm việc với các JDBC timestamp có hỗ trợ timezone/calendar. Nó giúp giảm sai lệch do timezone mặc định của JVM/JDBC driver trong các tình huống phù hợp.

Cần hiểu rõ giới hạn:

- Thuộc tính này không biến LocalDateTime thành Instant.
- Nó không thêm ZoneId vào cột TIMESTAMP không timezone.
- Nó không bảo đảm database lưu lại timezone gốc của OffsetDateTime hoặc ZonedDateTime.
- Cần kiểm thử với đúng database, JDBC driver và dialect đang triển khai.

Hibernate 6 còn có các chiến lược lưu timezone cho ZonedDateTime và OffsetDateTime. Tùy database/dialect, provider có thể lưu dưới dạng timestamp chuẩn hóa, kiểu native có timezone hoặc thêm cột phụ. Nếu cần giữ nguyên ZoneId, lưu một cột riêng kiểu String là cách rõ ràng và dễ di chuyển hơn. Không nên giả định việc lưu ZonedDateTime tự động giữ được tên vùng như Europe/Paris trên mọi database.

Cũng cần phân biệt timezone của ba lớp:

1. JVM timezone: cấu hình mặc định của tiến trình Java.
2. JDBC/database session timezone: ảnh hưởng cách driver hoặc database diễn giải timestamp.
3. Business timezone: vùng thời gian mà nghiệp vụ muốn áp dụng, ví dụ timezone của cửa hàng hoặc người đặt lịch.

Ba giá trị này có thể khác nhau. Hãy cấu hình và truyền business ZoneId một cách tường minh.

## 12. JSON API và định dạng ngày giờ

Spring Boot thường cấu hình Jackson để serialize/deserialize các kiểu java.time bằng định dạng ISO-8601.

Ví dụ request:

~~~json
{
  "localStart": "2026-11-09T09:30:00",
  "timeZoneId": "Asia/Ho_Chi_Minh"
}
~~~

Đây là giờ địa phương, chưa có offset. Server phải dùng timeZoneId để diễn giải.

Một Instant trong JSON thường có dạng:

~~~json
{
  "createdAt": "2026-11-09T02:30:00Z"
}
~~~

OffsetDateTime có thể được gửi với offset:

~~~json
{
  "occurredAt": "2026-11-09T09:30:00+07:00"
}
~~~

Các định dạng nên dùng:

| Kiểu | JSON ISO-8601 thường gặp |
|---|---|
| LocalDate | "2026-11-09" |
| LocalTime | "09:30:00" |
| LocalDateTime | "2026-11-09T09:30:00" |
| Instant | "2026-11-09T02:30:00Z" |
| OffsetDateTime | "2026-11-09T09:30:00+07:00" |

Không nên gửi LocalDateTime cho API khi phía nhận cần biết chính xác một instant mà không gửi kèm timezone hoặc offset. Nếu API nhận lịch hẹn theo giờ địa phương, gửi cả LocalDateTime và ZoneId. Nếu API nhận thời điểm đã xác định, ưu tiên Instant hoặc OffsetDateTime.

## 13. Độ chính xác và giới hạn của database

Java time có thể giữ phần thập phân giây tới nano giây. Database và JDBC driver có thể chỉ hỗ trợ độ chính xác thấp hơn, ví dụ micro giây hoặc mili giây.

Hệ quả:

- Giá trị ghi vào có thể bị cắt hoặc làm tròn phần nano giây.
- So sánh bằng chính xác hai Instant có thể thất bại sau round-trip nếu database thay đổi precision.
- Nên thống nhất precision của schema và chuẩn hóa giá trị trong test.
- Khi truy vấn theo khoảng, ưu tiên khoảng [from, to) thay vì tự cộng 1 nano giây để tìm cuối ngày.

Có thể dùng @Column(columnDefinition=...) để chỉ rõ kiểu SQL, nhưng điều đó làm mapping phụ thuộc database. Ưu tiên kiểu chuẩn và migration có kiểm soát; chỉ tùy chỉnh khi có yêu cầu rõ ràng.

## 14. Kiểm thử thời gian ổn định

Không nên để test phụ thuộc thời gian thật hoặc timezone mặc định của máy. Dùng Clock.fixed() để tạo thời điểm có thể lặp lại:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-09T02:30:00Z"),
        ZoneOffset.UTC
);

Instant now = fixedClock.instant();
assert now.equals(Instant.parse("2026-11-09T02:30:00Z"));
~~~

Với JUnit, nên dùng assertion của thư viện test thay vì Java assert:

~~~java
@Test
void usesFixedClock() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-09T02:30:00Z"),
            ZoneOffset.UTC
    );

    assertThat(clock.instant())
            .isEqualTo(Instant.parse("2026-11-09T02:30:00Z"));
}
~~~

Các nhóm test nên có:

- Kiểm tra persist và đọc lại LocalDate, LocalTime, LocalDateTime và Instant.
- Kiểm tra timestamp không bị lệch khi JVM timezone khác UTC.
- Kiểm tra API serialize Instant với hậu tố Z và LocalDateTime không có offset.
- Kiểm tra lịch trong timezone có DST, gồm gap và overlap.
- Kiểm tra độ chính xác sau khi lưu và đọc từ database thật.
- Kiểm tra truy vấn đầu ngày/cuối ngày theo ZoneId.

H2 phù hợp cho test nhanh, nhưng không thay thế hoàn toàn MySQL hoặc PostgreSQL. Nếu ứng dụng phụ thuộc vào kiểu timestamp, timezone session hoặc hàm SQL riêng, hãy chạy integration test trên đúng database mục tiêu.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Giờ bị lệch khi deploy | Dùng timezone mặc định của máy hoặc chuyển LocalDateTime không rõ zone | Dùng Instant cho thời điểm tuyệt đối và ZoneId rõ ràng cho giờ địa phương |
| Ngày bị lùi hoặc tiến một ngày | Chuyển instant sang timezone khác rồi lấy LocalDate | Xác định timezone nghiệp vụ trước khi lấy ngày |
| LocalDateTime bị hiểu nhầm là UTC | LocalDateTime không có timezone | Gắn ZoneId hoặc offset theo ngữ cảnh trước khi chuyển sang Instant |
| OffsetDateTime đọc lại khác offset ban đầu | Provider/database chuẩn hóa timestamp | Lưu offset hoặc ZoneId riêng nếu cần bảo toàn |
| Lịch hẹn sai khi đổi DST | Dùng offset cố định hoặc cộng 24 giờ | Dùng ZoneId và tính đầu ngày tiếp theo theo lịch |
| Test lúc qua lúc không | Dùng Instant.now() hoặc timezone mặc định | Inject Clock và dùng Clock.fixed() |
| Timestamp mất phần nano giây | Database có precision thấp hơn Java | Chuẩn hóa precision và so sánh theo độ chính xác schema |
| Query theo ngày bỏ sót bản ghi | Dùng ranh giới ngày theo UTC thay vì business zone | Tính from/to bằng atStartOfDay(zone) |
| Không tìm thấy kiểu SQL mong đợi | Dialect hoặc migration tạo kiểu khác | Kiểm tra schema thực tế và JDBC driver |

## 16. Nguyên tắc thiết kế thực tế

- Dùng Instant để ghi nhận thời điểm sự kiện, audit log, thời gian tạo và cập nhật.
- Dùng LocalDate cho ngày lịch không phụ thuộc múi giờ.
- Dùng LocalTime cho giờ trên đồng hồ; luôn xác định ngữ cảnh địa điểm khi chuyển đổi thành instant.
- Dùng LocalDateTime cùng ZoneId khi lưu lịch theo giờ địa phương.
- Lưu ZoneId dạng chuỗi như Asia/Ho_Chi_Minh khi phải giữ quy tắc vùng địa lý.
- Không dùng timezone mặc định của JVM làm dữ liệu nghiệp vụ.
- Không giả định timestamp trong database tự lưu tên vùng hoặc offset ban đầu.
- Cấu hình Hibernate/JDBC nhất quán và kiểm thử round-trip với database thật.
- Dùng migration để quản lý kiểu cột, precision và thay đổi schema.
- Xác định rõ chính sách cho lịch tương lai khi quy tắc timezone thay đổi.

## 17. Checklist tự đánh giá

- [ ] Phân biệt được LocalDate, LocalTime, LocalDateTime và Instant.
- [ ] Giải thích được vì sao LocalDateTime không xác định một instant.
- [ ] Biết kiểu SQL thường dùng cho từng kiểu java.time.
- [ ] Ánh xạ được java.time vào entity JPA mà không dùng @Temporal.
- [ ] Chuyển đổi LocalDateTime sang Instant với ZoneId phù hợp.
- [ ] Chuyển Instant sang giờ địa phương bằng atZone().
- [ ] Hiểu ZoneId khác ZoneOffset.
- [ ] Xử lý được gap và overlap khi chuyển DST.
- [ ] Biết lưu ZoneId riêng nếu cần giữ vùng địa lý của lịch hẹn.
- [ ] Biết dùng hibernate.jdbc.time_zone=UTC và hiểu giới hạn.
- [ ] Thiết kế JSON API rõ ràng cho giờ địa phương và instant.
- [ ] Dùng Clock.fixed() để kiểm thử thời gian ổn định.
- [ ] Kiểm tra precision và timezone round-trip trên database mục tiêu.

## 18. Kết luận

Chọn kiểu ngày giờ theo ý nghĩa nghiệp vụ là bước quan trọng nhất khi lưu thời gian bằng Spring Data JPA. LocalDate phù hợp với ngày lịch, LocalTime với giờ trên đồng hồ, LocalDateTime với ngày giờ địa phương chưa có timezone và Instant với thời điểm tuyệt đối.

Múi giờ là quy tắc của một vùng địa lý, không chỉ là một con số offset. Khi xử lý lịch tương lai, lưu LocalDateTime cùng ZoneId và xác định chính sách DST. Khi ghi nhận sự kiện đã xảy ra, lưu Instant và chuyển sang timezone hiển thị ở tầng ứng dụng. Cách phân chia này giúp dữ liệu nhất quán giữa máy chủ, database và người dùng ở nhiều khu vực.
