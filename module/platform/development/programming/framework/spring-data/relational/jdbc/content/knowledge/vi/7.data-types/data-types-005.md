# LocalDate, LocalTime, LocalDateTime và quy ước múi giờ

## 1. Tại sao chọn đúng kiểu thời gian lại quan trọng?

Một hệ thống dùng Spring Data JDBC thường lưu những dữ liệu rất khác nhau nhưng đều trông giống “ngày giờ”:

- Ngày sinh của khách hàng: **ngày trên lịch**, không phụ thuộc múi giờ.
- Giờ cửa hàng mở mỗi ngày: **giờ trên đồng hồ địa phương**, chưa chỉ ra một thời điểm duy nhất.
- Lịch hẹn lúc 09:30 ngày 13/11 ở TP.HCM: **ngày giờ địa phương**, cần thêm múi giờ để suy ra thời điểm toàn cầu.
- Thời điểm một thanh toán thực sự diễn ra: **một instant cụ thể trên trục thời gian**, cần dùng được khi hệ thống chạy tại nhiều khu vực.

Nếu tất cả đều được lưu bằng một kiểu `LocalDateTime`, ứng dụng dễ nhầm ngày lịch với thời điểm thực, gặp lỗi khi đổi múi giờ máy chủ hoặc xử lý giờ mùa hè (*daylight saving time* – DST). Vấn đề không nằm ở JDBC có ghi được giá trị hay không, mà ở **ý nghĩa của dữ liệu khi được ghi, đọc, so sánh và truyền giữa các hệ thống**.

Trong bài này, ta sẽ:

1. Phân biệt `LocalDate`, `LocalTime` và `LocalDateTime` theo ngữ nghĩa.
2. Ánh xạ chúng sang `DATE`, `TIME`, `TIMESTAMP` khi dùng Spring Data JDBC.
3. Xác định rõ lúc nào phải bổ sung `ZoneId`, `ZoneOffset` hoặc `Instant`.
4. Viết một ví dụ entity/repository có thể lưu rồi đọc lại ba kiểu thời gian.
5. Thiết lập các quy ước để dữ liệu nhất quán giữa database, backend, API và người dùng ở nhiều múi giờ.

## 2. Ba kiểu `java.time` biểu diễn điều gì?

Java 8 trở lên cung cấp API `java.time`. Ba kiểu trong tiêu đề đều **không chứa thông tin múi giờ hay UTC offset**.

| Kiểu Java | Thông tin có trong giá trị | Thông tin không có | SQL thường dùng | Ví dụ nghiệp vụ |
| --- | --- | --- | --- | --- |
| `LocalDate` | Năm, tháng, ngày | Giờ, múi giờ, offset | `DATE` | Ngày sinh, ngày kế toán, ngày áp dụng chính sách |
| `LocalTime` | Giờ, phút, giây, phần nhỏ của giây | Ngày, múi giờ, offset | `TIME WITHOUT TIME ZONE` hoặc `TIME` | Giờ mở cửa mỗi ngày, giờ báo thức định kỳ |
| `LocalDateTime` | Ngày và giờ địa phương | Múi giờ, offset, thời điểm tuyệt đối | `TIMESTAMP WITHOUT TIME ZONE` hoặc `TIMESTAMP` | Lịch hẹn được nhập theo đồng hồ của một địa điểm |
| `Instant` | Thời điểm trên trục thời gian UTC | Múi giờ hiển thị của người dùng | Cột instant phù hợp với dialect, ví dụ PostgreSQL `TIMESTAMPTZ` | Thời điểm thanh toán, thời gian ghi nhận sự kiện |
| `OffsetDateTime` | Ngày giờ và UTC offset cố định | Quy tắc lịch sử/tương lai của múi giờ địa lý | Cần đối chiếu SQL type và driver | Dữ liệu từ API có `+07:00` hoặc `Z` |
| `ZonedDateTime` | Ngày giờ, offset và một `ZoneId` như `Europe/Paris` | Không có bảo đảm database lưu nguyên zone ID | Thường phải lưu instant và zone ID theo chính sách | Lịch hẹn gắn với vùng có DST |

Ba kiểu đầu biểu diễn giá trị **local** theo lịch và đồng hồ. Không thể suy ra thời điểm UTC duy nhất từ `2026-11-13T09:30:00` nếu chưa biết người dùng muốn nói 09:30 ở đâu.

### `LocalDate`: ngày lịch

```java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1998, 5, 12);
LocalDate businessDay = LocalDate.parse("2026-11-13");

System.out.println(birthday);  // 1998-05-12
System.out.println(businessDay); // 2026-11-13
```

Ngày sinh 12/05/1998 không nên tự đổi thành 11/05 hoặc 13/05 khi người dùng đi từ Việt Nam sang nước khác. `LocalDate` lưu đúng ý nghĩa “ngày” mà không tạo ra thời điểm nửa đêm giả định.

### `LocalTime`: giờ trên đồng hồ

```java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(8, 30);
LocalTime closingTime = LocalTime.parse("18:00:00");

System.out.println(openingTime); // 08:30
```

`08:30` không nói rằng cửa hàng mở lúc 08:30 UTC. Nếu đây là giờ mở cửa của cửa hàng ở TP.HCM, ta còn cần **địa điểm/múi giờ của cửa hàng** và **ngày cụ thể** khi muốn tính thời điểm mở cửa tương ứng.

### `LocalDateTime`: ngày cộng giờ, vẫn chưa có múi giờ

```java
import java.time.LocalDateTime;

LocalDateTime appointment =
        LocalDateTime.of(2026, 11, 13, 9, 30);

System.out.println(appointment); // 2026-11-13T09:30
```

Giá trị này là “09:30 theo đồng hồ địa phương vào ngày 13/11/2026”. Nó **chưa phải UTC**, cũng không có offset ngầm định. Nếu không lưu hoặc nhận được múi giờ đi kèm, những ứng dụng chạy ở quốc gia khác có thể hiểu khác nhau.

## 3. Ánh xạ ba kiểu local với cột SQL trong Spring Data JDBC

Spring Data JDBC sử dụng cơ chế mapping của Spring Data Relational và hạ tầng JDBC. Với một cơ sở dữ liệu/driver thông dụng có hỗ trợ JDBC 4.2, các kiểu `java.time` local thường được ánh xạ như sau:

```text
Java domain model                 Cột SQL
----------------------------------------------
LocalDate                         DATE
LocalTime                         TIME
LocalDateTime                     TIMESTAMP
```

Tên kiểu thực tế của database có thể là `TIME WITHOUT TIME ZONE` hoặc `TIMESTAMP WITHOUT TIME ZONE`. Số chữ số phần giây được lưu phụ thuộc định nghĩa cột và khả năng của database/driver. Ví dụ, nếu ứng dụng ghi nanosecond nhưng cột chỉ lưu microsecond, dữ liệu đọc lại có thể bị làm tròn hoặc cắt phần nhỏ của giây.

**Lưu ý quan trọng:** `TIMESTAMP` không có một ý nghĩa giống hệt nhau ở mọi database. Ví dụ, PostgreSQL phân biệt `TIMESTAMP WITHOUT TIME ZONE` với `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`), còn MySQL có khác biệt đáng kể giữa `DATETIME` và `TIMESTAMP` về xử lý múi giờ của session. Vì thế, cần đọc tài liệu của **database + JDBC driver + dialect** đang dùng trước khi áp dụng một quy ước cho toàn hệ thống.

### Ví dụ thiết kế bảng

Giả sử hệ thống tổ chức các buổi tham quan. Mỗi lịch có:

- `visitDate`: ngày tham quan theo lịch tại địa điểm.
- `doorOpensAt`: giờ mở cửa địa phương trong ngày đó.
- `registrationDeadlineLocal`: hạn đăng ký tính theo đồng hồ địa phương của địa điểm.
- `timeZoneId`: múi giờ của địa điểm, ví dụ `Asia/Ho_Chi_Minh`.

Schema tối giản trên H2:

```sql
CREATE TABLE "visit_schedules" (
    "id" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "visit_date" DATE NOT NULL,
    "door_opens_at" TIME NOT NULL,
    "registration_deadline_local" TIMESTAMP NOT NULL,
    "time_zone_id" VARCHAR(64) NOT NULL
);
```

Ta quote tên bảng và cột nhất quán để ví dụ dễ đối chiếu với các tên mapping rõ ràng. Khi làm việc với PostgreSQL hoặc database khác, hãy áp dụng quy tắc đặt tên/quote phù hợp dialect của dự án; không phụ thuộc vào việc driver tự chuyển chữ hoa/chữ thường giống H2.

**Điểm cần phân biệt:** database đang giữ nguyên các thành phần ngày và giờ trong ba cột local. Cột `time_zone_id` là metadata nghiệp vụ cho biết phải hiểu những thành phần đó theo múi giờ nào; bản thân `TIMESTAMP` ở đây không chứa timezone ID.

## 4. Ví dụ Spring Data JDBC: lưu và đọc dữ liệu ngày giờ

Ví dụ dùng Java 21 và Spring Boot có hỗ trợ Spring Data JDBC. Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đặt `schema.sql` ở `src/main/resources/schema.sql` và cấu hình:

```properties
spring.datasource.url=jdbc:h2:mem:date_time_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Quan sát câu lệnh SQL do hạ tầng Spring JDBC thực thi
logging.level.org.springframework.jdbc=DEBUG
```

### 4.1. Định nghĩa aggregate root

Tạo `src/main/java/com/example/datetime/VisitSchedule.java`:

```java
package com.example.datetime;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("visit_schedules")
public record VisitSchedule(
        @Id Long id,
        @Column("visit_date") LocalDate visitDate,
        @Column("door_opens_at") LocalTime doorOpensAt,
        @Column("registration_deadline_local")
        LocalDateTime registrationDeadlineLocal,
        @Column("time_zone_id") String timeZoneId
) {
}
```

`@Table` và `@Column` chỉ rõ tên bảng/cột. `@Id` là annotation của `org.springframework.data.annotation`, không phải `jakarta.persistence.Id`. Record phù hợp với ví dụ vì các giá trị được biểu diễn bất biến; Spring Data JDBC có thể tạo instance khi đọc dữ liệu và trả instance chứa ID sau khi insert.

Trong hệ thống thật, cần kiểm tra tính hợp lệ của `timeZoneId` bằng `ZoneId.of(...)`, so sánh hạn đăng ký với ngày tham quan và bảo vệ các quy tắc nghiệp vụ tại model hoặc service phù hợp.

### 4.2. Repository

Tạo `src/main/java/com/example/datetime/VisitScheduleRepository.java`:

```java
package com.example.datetime;

import java.time.LocalDate;
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface VisitScheduleRepository
        extends CrudRepository<VisitSchedule, Long> {

    List<VisitSchedule> findByVisitDate(LocalDate visitDate);
}
```

`findByVisitDate(...)` là một derived query với tham số `LocalDate`. Không cần tự chuyển giá trị ngày thành chuỗi `"2026-11-13"` để truyền cho repository.

### 4.3. Chạy ví dụ bằng `CommandLineRunner`

Tạo `src/main/java/com/example/datetime/DateTimeApplication.java`:

```java
package com.example.datetime;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DateTimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DateTimeApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(VisitScheduleRepository repository) {
        return args -> {
            VisitSchedule newSchedule = new VisitSchedule(
                    null,
                    LocalDate.of(2026, 11, 13),
                    LocalTime.of(8, 30),
                    LocalDateTime.of(2026, 11, 12, 20, 0),
                    "Asia/Ho_Chi_Minh"
            );

            VisitSchedule saved = repository.save(newSchedule);
            VisitSchedule loaded = repository.findById(saved.id())
                    .orElseThrow();

            System.out.println("Ngay tham quan: "
                    + loaded.visitDate());
            System.out.println("Gio mo cua: "
                    + loaded.doorOpensAt());
            System.out.println("Han dang ky local: "
                    + loaded.registrationDeadlineLocal());

            ZoneId venueZone = ZoneId.of(loaded.timeZoneId());
            Instant deadlineInstant = loaded.registrationDeadlineLocal()
                    .atZone(venueZone)
                    .toInstant();
            System.out.println("Han dang ky UTC: " + deadlineInstant);

            repository.findByVisitDate(LocalDate.of(2026, 11, 13))
                    .forEach(System.out::println);
        };
    }
}
```

Chạy ở thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Kết quả mong đợi về mặt giá trị (trình bày minh họa):

```text
Ngay tham quan: 2026-11-13
Gio mo cua: 08:30
Han dang ky local: 2026-11-12T20:00
Han dang ky UTC: 2026-11-12T13:00:00Z
```

Đối với `Asia/Ho_Chi_Minh`, ngày giờ trong ví dụ tương ứng offset `+07:00`, nên `20:00` địa phương bằng `13:00Z` cùng ngày. Lệnh `save` tạo `INSERT`, `findById` và `findByVisitDate` tạo các truy vấn `SELECT` thích hợp. Văn bản trên là kết quả minh họa, không phải log thực tế thu thập từ một lần chạy trong bài này.

**Điều quan trọng:** `LocalDateTime` lấy ra từ database vẫn là `2026-11-12T20:00`. Phép chuyển thành `Instant` chỉ thực hiện **khi ứng dụng cung cấp `ZoneId` và yêu cầu chuyển đổi**. Đọc một cột `TIMESTAMP WITHOUT TIME ZONE` không tự bổ sung thông tin `Asia/Ho_Chi_Minh`.

## 5. `ZoneId`, `ZoneOffset` và `Instant` khác nhau ra sao?

Ba khái niệm sau thường bị nhầm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `ZoneId` | `Asia/Ho_Chi_Minh`, `America/New_York` | Tên vùng múi giờ kèm quy tắc offset thay đổi theo lịch sử và thời điểm. |
| `ZoneOffset` | `+07:00`, `-05:00`, `Z` | Chênh lệch cố định so với UTC tại một thời điểm; không mang toàn bộ quy tắc DST của một vùng. |
| `Instant` | `2026-11-13T02:30:00Z` | Một thời điểm cụ thể trên trục thời gian; không mang cách trình bày ở múi giờ người xem. |

Ví dụ:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local = LocalDateTime.of(2026, 11, 13, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);   // 2026-11-13T09:30+07:00[Asia/Ho_Chi_Minh]
System.out.println(instant); // 2026-11-13T02:30:00Z
```

Cùng một instant có thể hiển thị thành những giờ địa phương khác nhau:

```java
Instant eventTime = Instant.parse("2026-11-13T02:30:00Z");

System.out.println(
        eventTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
); // 2026-11-13T09:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(
        eventTime.atZone(ZoneId.of("UTC"))
); // 2026-11-13T02:30Z[UTC]
```

**Một `ZoneOffset` như `+07:00` không tương đương hoàn toàn với một `ZoneId`.** Ở những vùng có DST, offset phụ thuộc ngày cụ thể. Nếu một sự kiện diễn ra định kỳ lúc 09:00 theo giờ địa phương, chỉ lưu offset của lần tổ chức đầu tiên có thể làm các lần sau sai giờ.

## 6. Quy tắc chọn kiểu theo nghiệp vụ

Hãy chọn kiểu thời gian dựa trên **điều gì phải bất biến khi người dùng đổi múi giờ**, rồi mới nghĩ đến tên cột SQL.

### 6.1. Ngày sinh, ngày nghỉ, ngày kế toán → `LocalDate`

```java
LocalDate dateOfBirth = LocalDate.of(1998, 5, 12);
```

Không tự đổi `LocalDate` thành `Instant` “lúc 00:00 UTC” nếu ngày lịch là dữ liệu gốc. Người dùng ở UTC-08 có thể thấy ngày trước đó sau khi đổi từ midnight UTC sang giờ địa phương. Ngày lịch nên giữ nguyên cho dù đọc trên máy chủ đặt ở đâu.

### 6.2. Giờ mở cửa mỗi ngày → `LocalTime` kèm múi giờ của địa điểm

```java
LocalTime opensAt = LocalTime.of(8, 30);
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
```

Nếu một cửa hàng mở lúc 08:30 theo đồng hồ địa phương mỗi ngày, hãy lưu giờ mở cửa theo `LocalTime` và biết múi giờ của cửa hàng. Khi cần lên lịch cho **ngày cụ thể**, mới ghép thêm `LocalDate` rồi chuyển sang `Instant`:

```java
LocalDate date = LocalDate.of(2026, 11, 13);
Instant openingInstant = date.atTime(opensAt)
        .atZone(storeZone)
        .toInstant();
```

Đối với giờ mở cửa trải qua nửa đêm, ví dụ 22:00–02:00, chỉ so sánh `opensAt.isBefore(closesAt)` sẽ sai. Phải định nghĩa rõ giờ đóng thuộc **ngày kế tiếp** và áp dụng lịch của địa điểm.

### 6.3. Lịch hẹn địa phương → `LocalDateTime` + `ZoneId`

Nếu khách đặt lịch tại một chi nhánh vào 09:30 ngày 13/11/2026, ta cần lưu/biết cả ngày giờ theo chi nhánh và vùng múi giờ của chi nhánh.

```text
appointment_local = 2026-11-13 09:30:00
zone_id           = Asia/Ho_Chi_Minh
```

Cặp thông tin này cho phép tính instant tương ứng và vẫn giữ được **ý định lịch địa phương**. Nếu một lịch được ấn định vĩnh viễn tại một instant cụ thể, hệ thống cũng có thể lưu instant đó (trong cột phù hợp) để tìm kiếm và kích hoạt chính xác, đồng thời giữ zone ID để hiển thị đúng ý định người tổ chức.

### 6.4. Thời điểm sự kiện xảy ra → `Instant`

`createdAt`, `paidAt`, `processedAt` và các sự kiện hệ thống thường trả lời câu hỏi **“xảy ra vào khoảnh khắc nào?”**. `Instant` biểu diễn câu trả lời này tốt hơn `LocalDateTime`:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant paidAt = Instant.now(clock);
```

Khi lưu instant, nên chọn SQL type và converter/driver có ngữ nghĩa tương ứng. Với PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`) là lựa chọn thường gặp để lưu instant; PostgreSQL **không lưu tên zone ID gốc** trong giá trị này. Với hệ quản trị khác, cần xem quy tắc múi giờ của type, driver và session.

Không nên thay `Instant` bằng `LocalDateTime.now()` rồi ngầm giả định rằng toàn bộ các máy trong hệ thống luôn chạy ở UTC. Ngay cả khi quy ước lưu “UTC trong TIMESTAMP không có timezone”, đó vẫn là một **quy ước ứng dụng phải duy trì và kiểm chứng tường minh**, chứ không phải đặc tính được kiểu cột bảo đảm.

## 7. Chuyển đổi ngày giờ: điểm nào cần múi giờ?

Đối với một ngày giờ địa phương, thao tác sau cần múi giờ:

```java
LocalDateTime localDateTime =
        LocalDateTime.of(2026, 11, 13, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant = localDateTime.atZone(zone).toInstant();
```

Chiều ngược lại, từ một thời điểm tuyệt đối sang cách trình bày của người dùng:

```java
Instant instant = Instant.parse("2026-11-13T02:30:00Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime localForUser =
        LocalDateTime.ofInstant(instant, userZone);
```

Hai thao tác có tính chất khác nhau:

- **Local → Instant** cần xác định zone và xử lý trường hợp DST có giờ không tồn tại/giờ lặp.
- **Instant → Local** với một zone hợp lệ cho ra một giá trị local xác định tại instant đó. Tuy nhiên, chuyển ngược local về instant sau khi **đánh mất offset** có thể mơ hồ ở ngày đổi DST.

### Tại sao không dùng `ZoneId.systemDefault()` tùy tiện?

```java
LocalDateTime.now();       // Lấy theo múi giờ mặc định của JVM
LocalDate.now();           // Ngày hiện tại theo múi giờ mặc định của JVM
ZoneId.systemDefault();   // Có thể khác nhau theo máy/container
```

Nếu một máy chạy tại Việt Nam và một container chạy UTC, `LocalDateTime.now()` ở cùng một instant sẽ cho ra các giá trị local khác nhau. Từ đó có thể xuất hiện lỗi thống kê “ngày hôm nay”, cutoff hoặc hết hạn.

Quy ước tốt hơn là chỉ rõ nguồn thời gian và zone:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.systemUTC();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate todayForBusiness =
        LocalDate.now(clock.withZone(businessZone));
```

Tiêm `Clock` qua constructor vào service cũng giúp kiểm thử điều kiện hạn chót, ngày lễ và thời điểm chuyển năm bằng thời gian cố định.

## 8. DST: một ngày giờ địa phương có thể không tồn tại hoặc có hai lần

Một số vùng như `America/New_York` điều chỉnh đồng hồ theo mùa. Điều này tạo ra hai tình huống mà Việt Nam thường không gặp trong lịch hiện đại.

### 8.1. Giờ bị bỏ qua (gap)

Khi đồng hồ chuyển từ 01:59 lên 03:00, khoảng 02:00–02:59 trong ngày chuyển đổi **không tồn tại** theo giờ địa phương. Nếu người dùng nhập 02:30 trong khoảng đó, hệ thống phải có chính sách: từ chối, yêu cầu chọn lại hoặc điều chỉnh theo một quy tắc đã công bố.

### 8.2. Giờ lặp lại (overlap)

Khi đồng hồ quay từ 02:00 về 01:00, giá trị 01:30 xảy ra **hai lần** với hai UTC offset khác nhau. `LocalDateTime.of(..., 1, 30)` cộng `ZoneId` vẫn có thể chưa đủ để chọn một instant nếu không có quy tắc xử lý overlap.

API `atZone(...)` có hành vi mặc định để giải quyết gap/overlap; vì vậy dùng nó có thể **âm thầm điều chỉnh** một giờ không tồn tại hoặc chọn một trong hai offset. Với lịch hẹn cần độ chính xác, hãy phát hiện tình huống trước:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class LocalTimeResolver {
    private LocalTimeResolver() {}

    public static Instant requireUnambiguousInstant(
            LocalDateTime local,
            ZoneId zone
    ) {
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local date-time does not exist in this zone");
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Local date-time occurs twice; choose an offset");
        }
        return local.toInstant(offsets.get(0));
    }
}
```

Đoạn code trên cố ý từ chối cả gap và overlap, phù hợp với ứng dụng muốn người dùng xác nhận. Một hệ thống khác có thể chọn “offset sớm hơn”, “offset muộn hơn” hoặc dịch sang thời điểm hợp lệ đầu tiên, nhưng phải ghi rõ **quy tắc nghiệp vụ** và bảo đảm code dùng cùng chính sách đó ở mọi luồng.

Nếu lịch là “09:00 mỗi ngày theo giờ New York”, cần lưu `LocalTime` và `ZoneId`/quy tắc định kỳ rồi tính instant theo **từng ngày**. Không cộng cố định 24 giờ vào instant của hôm trước trong thời gian có thể đổi DST.

## 9. Quy ước thiết kế cột và API

Một dự án nên ghi thành quy ước thống nhất thay vì để mỗi nhóm tự hiểu `timestamp` theo cách riêng.

### Quy ước gợi ý

| Loại dữ liệu | Biểu diễn trong domain | Cột database | JSON/API | Quy tắc |
| --- | --- | --- | --- | --- |
| Ngày lịch | `LocalDate` | `DATE` | `"2026-11-13"` | Không ép thành 00:00 UTC. |
| Giờ địa phương | `LocalTime` | `TIME` không timezone | `"08:30:00"` | Tên trường phải nói rõ lịch/ngữ cảnh giờ áp dụng. |
| Ngày giờ địa phương | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` | `"2026-11-13T09:30:00"` | Đi kèm `zoneId` khi cần suy ra instant. |
| Thời điểm tuyệt đối | `Instant` | Kiểu cột lưu instant phù hợp dialect | `"2026-11-13T02:30:00Z"` | Đối chiếu driver và cơ chế mapping, hiển thị theo zone của người xem. |
| Múi giờ địa điểm | `ZoneId` trong domain; có thể lưu ID dạng `String` | `VARCHAR(64)` | `"Asia/Ho_Chi_Minh"` | Kiểm tra bằng `ZoneId.of(...)`; dùng tên vùng IANA. |

Ví dụ JSON rõ nghĩa cho một lịch hẹn:

```json
{
  "appointmentLocal": "2026-11-13T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Nếu phía API muốn gửi instant đã xác định, có thể dùng:

```json
{
  "appointmentInstant": "2026-11-13T02:30:00Z",
  "displayZoneId": "Asia/Ho_Chi_Minh"
}
```

Hai hợp đồng trên có thể cùng hợp lệ nhưng **không tương đương về mục đích**:

- Hợp đồng local + zone bảo tồn “lịch lúc 09:30 tại TP.HCM”.
- Hợp đồng instant + display zone nhấn mạnh “sự kiện xảy ra tại instant này”.

Nếu API chỉ trả `"2026-11-13T09:30:00"` và client hiểu đó là UTC hoặc tự gán zone của trình duyệt, người dùng ở nơi khác có thể thấy sai giờ.

Với Jackson của Spring Boot, các kiểu `java.time` có thể được biểu diễn theo dạng ISO-8601 khi module tương ứng được cấu hình qua starter JSON. Dù serializer hoạt động, **dạng chuỗi không có offset vẫn không tự mang thông tin múi giờ**. Tránh dùng cấu hình JSON như một cách chữa lỗi semantic của dữ liệu được lưu trong JDBC.

## 10. Quy ước truy vấn theo ngày và khoảng thời gian

### 10.1. Tìm dữ liệu theo `LocalDate`

Nếu bảng lưu ngày nghiệp vụ là `DATE`, câu truy vấn đơn giản:

```sql
SELECT *
FROM "visit_schedules"
WHERE "visit_date" = ?;
```

Repository có thể nhận trực tiếp `LocalDate`:

```java
List<VisitSchedule> schedules =
        repository.findByVisitDate(LocalDate.of(2026, 11, 13));
```

Không cần tự biến ngày thành một khoảng `2026-11-13T00:00:00Z` đến 24 giờ sau nếu dữ liệu gốc thực sự là ngày lịch.

### 10.2. Lọc các sự kiện theo ngày ở một múi giờ

Giả sử bảng sự kiện lưu các **instant** và người dùng yêu cầu “mọi thanh toán trong ngày 13/11 theo giờ TP.HCM”. Hãy chuyển **hai biên ngày địa phương** sang instant:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate targetDay = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        targetDay.atStartOfDay(zone).toInstant();

Instant endExclusive =
        targetDay.plusDays(1).atStartOfDay(zone).toInstant();
```

SQL về mặt ý nghĩa:

```sql
SELECT *
FROM payments
WHERE paid_at >= :start_inclusive
  AND paid_at <  :end_exclusive;
```

Ở đây `paid_at` được giả định là cột lưu instant theo quy ước đã thiết kế, chẳng hạn `TIMESTAMPTZ` trong PostgreSQL. Cú pháp tham số có tên `:start_inclusive` và `:end_exclusive` thuộc cách truyền qua `NamedParameterJdbcTemplate` hoặc API hỗ trợ named parameters; đó không phải cú pháp dùng trực tiếp cho mọi SQL client.

**Vì sao khoảng nửa mở `[start, end)`?** Một sự kiện đúng đầu ngày hôm sau sẽ thuộc ngày hôm sau; không cần đoán “thời điểm cuối ngày” với độ chính xác phần giây tùy database.

**Vì sao lấy đầu ngày hôm sau thay vì cộng 24 giờ?** Ở vùng có DST, một ngày lịch có thể dài 23 hoặc 25 giờ. `targetDay.plusDays(1).atStartOfDay(zone)` biểu diễn đúng biên ngày theo lịch địa phương; cộng một khoảng 24 giờ cố định vào instant bắt đầu ngày có thể cho ra biên sai.

### 10.3. So sánh khoảng thời gian phải cùng ngữ nghĩa

`LocalDateTime.isBefore(...)` và `isAfter(...)` chỉ so sánh các thành phần năm-tháng-ngày-giờ. Nếu hai giá trị đến từ **hai múi giờ khác nhau**, việc so sánh chúng trực tiếp không chứng minh sự kiện nào diễn ra trước trên trục thời gian.

Ví dụ:

```java
LocalDateTime hcm = LocalDateTime.parse("2026-11-13T09:30:00");
LocalDateTime tokyo = LocalDateTime.parse("2026-11-13T10:00:00");
```

Theo đồng hồ, `09:30` nhỏ hơn `10:00`. Nhưng `09:30` ở TP.HCM tương ứng `02:30Z`, còn `10:00` ở Tokyo tương ứng `01:00Z`, nghĩa là sự kiện Tokyo **xảy ra sớm hơn**. Muốn so thứ tự thực tế, trước tiên phải chuyển từng giá trị sang `Instant` theo zone tương ứng.

## 11. Những lỗi thường gặp khi làm việc với Spring Data JDBC

### Lỗi 1: lưu thời điểm thực bằng `LocalDateTime.now()` mà không có hợp đồng về zone

Một server chạy UTC ghi `2026-11-13T02:30`, server khác chạy UTC+07 ghi `2026-11-13T09:30` cho cùng instant. Nếu cả hai ghi vào một cột `TIMESTAMP` không timezone, dữ liệu sẽ có ý nghĩa không nhất quán.

**Cách làm:** với thời điểm sự kiện, dùng `Instant` và chọn cột/driver có semantics thích hợp; khi phải lưu local timestamp, xác định tường minh zone và quy ước.

### Lỗi 2: cho rằng `LocalDateTime` luôn là UTC

`LocalDateTime` không chứa UTC offset. Giá trị này không thể chuyển thành `Instant` bằng một phép ép kiểu đơn thuần. Nếu hệ thống quy định dữ liệu local ở UTC, đó là quy ước nằm ngoài kiểu Java và cần được thực thi ở mọi điểm ghi/đọc.

**Cách làm:** đặt tên biến/cột rõ ràng (`createdAtInstant`, `appointmentLocal`) và không che giấu `ZoneId` trong một helper dùng timezone mặc định.

### Lỗi 3: lưu một offset cố định thay cho tên vùng

`+01:00` có thể đúng cho một ngày nhưng không đúng cho những ngày khác ở cùng thành phố. Một lịch lặp vào mùa hè và mùa đông cần quy tắc múi giờ theo lịch.

**Cách làm:** lưu ID vùng dạng `Europe/Paris`, `America/New_York`... khi cần giữ ý định giờ địa phương; cân nhắc lưu thêm instant đã xác nhận cho từng lịch cụ thể.

### Lỗi 4: dùng `DATE`/`TIME` hoặc `TIMESTAMP` nhưng giả định database lưu lại `ZoneId`

Các kiểu không timezone không tự giữ tên múi giờ. Ngay cả PostgreSQL `TIMESTAMPTZ` cũng không giữ nguyên zone ID gốc đã gửi; nó đại diện instant và có thể hiển thị theo cấu hình session.

**Cách làm:** nếu cần hiển thị lại “đúng vùng địa lý mà người dùng chọn”, lưu `zone_id` thành cột riêng.

### Lỗi 5: bị thay đổi phần giây sau khi đọc lại

Java `LocalTime` và `LocalDateTime` có thể có nanosecond. Một database hoặc cột `TIME(0)`/`TIMESTAMP(3)` có độ chính xác thấp hơn.

**Cách làm:** chọn precision cho cột theo nghiệp vụ và thống nhất yêu cầu khi serialize/compare; không mặc định mọi nanosecond đều được bảo toàn khi round-trip.

### Lỗi 6: giả định cấu hình hệ thống sẽ tự sửa tất cả

Thiết lập múi giờ JVM, session database hoặc serializer có thể ảnh hưởng những đoạn code và JDBC type nhất định, nhưng không làm một `LocalDateTime` trở thành kiểu mang zone. Cấu hình riêng của JPA/Hibernate cũng không thể mặc định áp dụng cho Spring Data JDBC.

**Cách làm:** quy định ngữ nghĩa theo từng trường dữ liệu, kiểm tra cách driver bind/read của database cụ thể và kiểm thử từ API xuống tới database.

### Lỗi 7: chuyển ngày thành epoch bằng `atStartOfDay(ZoneOffset.UTC)` cho mọi trường hợp

Ngày sinh, ngày kế toán hoặc ngày mở cửa của cửa hàng không phải một instant UTC mặc định.

**Cách làm:** giữ `LocalDate` khi dữ liệu chỉ có ý nghĩa ngày lịch. Chỉ chuyển thành khoảng instant khi một use case đòi hỏi và biết múi giờ của ngữ cảnh đó.

## 12. Khi nào cần custom converter?

Với `LocalDate`, `LocalTime` và `LocalDateTime`, hãy bắt đầu bằng mapping chuẩn của Spring Data JDBC và driver phù hợp. Không nên tạo converter chỉ vì muốn đổi kiểu Java thành chuỗi.

Converter có thể cần khi:

- Driver hoặc dialect không hỗ trợ trực tiếp kiểu `java.time` mong muốn.
- Legacy schema lưu ngày giờ trong `VARCHAR`, epoch milliseconds, cột số hoặc một kiểu riêng của database.
- Ứng dụng có một value object chuyên dụng cần ánh xạ nhiều cách, ví dụ `BusinessZoneId`.
- Quy ước lưu `Instant`/`OffsetDateTime` cần chuyển đổi có kiểm soát sang loại JDBC driver chấp nhận.

Spring Data Relational hỗ trợ đăng ký custom conversions, nhưng phải xác định rõ **chiều đọc**, **chiều ghi**, **kiểu JDBC trung gian**, **dialect** và **ngữ nghĩa múi giờ**. Không nên viết converter dạng “nhận `LocalDateTime` rồi tự gán timezone mặc định của máy chủ” vì kết quả sẽ phụ thuộc môi trường.

Ví dụ nếu một hệ thống legacy lưu epoch milliseconds trong cột `BIGINT`, quy tắc rõ ràng là:

```java
import java.time.Instant;

long storedEpochMillis = 1_800_000_000_000L;
Instant instant = Instant.ofEpochMilli(storedEpochMillis);

long valueToStore = instant.toEpochMilli();
```

Số epoch là một instant, không phải một ngày giờ địa phương. Nếu schema legacy lưu `2026-11-13 09:30` nhưng không lưu zone, **không thể khôi phục instant chính xác chỉ từ giá trị đó** nếu chưa có quy ước cũ về timezone.

## 13. Kiểm thử quy ước múi giờ

Nên có những trường hợp kiểm thử xác nhận ý nghĩa dữ liệu, nhất là khi hệ thống đa vùng hoặc chuẩn bị chuyển database. Ví dụ kiểm tra nghiệp vụ thuần Java bằng JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class DateTimeConventionTest {

    @Test
    void localAppointmentInHoChiMinhResolvesToUtcInstant() {
        LocalDateTime appointment =
                LocalDateTime.of(2026, 11, 13, 9, 30);

        Instant actual = appointment
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();

        assertEquals(
                Instant.parse("2026-11-13T02:30:00Z"),
                actual
        );
    }

    @Test
    void dateOfBirthIsCalendarDate() {
        LocalDate birth = LocalDate.parse("1998-05-12");
        assertEquals(LocalDate.of(1998, 5, 12), birth);
    }
}
```

Với lớp persistence thực tế, nên kiểm tra riêng việc ghi/đọc `DATE`, `TIME`, `TIMESTAMP` và precision qua database/driver đang triển khai. Khi thay H2 bằng PostgreSQL hoặc MySQL, kiểm tra sự khác nhau về SQL type, session timezone, cách JDBC bind tham số và kết quả round-trip. Điều quan trọng là kiểm thử **ngữ nghĩa của trường**, không chỉ kiểm tra câu SQL chạy thành công.

Đối với lịch đặt ở những vùng có DST, kiểm thử thêm thời điểm giờ bị bỏ qua và giờ lặp; đối với báo cáo theo ngày, kiểm tra những ngày dài 23/25 giờ; đối với hệ thống chạy trong container, xác nhận code không phụ thuộc vào timezone mặc định.

## 14. Bài tập tự thực hành

**Bài tập 1 — Ngày không đổi theo múi giờ.** Thêm trường `customerBirthday` kiểu `LocalDate` vào một aggregate và cột `DATE` tương ứng. Ghi một ngày sinh, đọc lại rồi thử chạy ứng dụng trong môi trường có timezone mặc định khác. Giải thích vì sao dữ liệu ngày vẫn phải giữ đúng ngày lịch.

**Bài tập 2 — Đổi cách hiển thị lịch hẹn.** Từ `LocalDateTime.of(2026, 11, 13, 9, 30)` tại `Asia/Ho_Chi_Minh`, tính `Instant` rồi hiển thị cùng instant tại `Europe/Paris`. So sánh hai giá trị local và giải thích vì sao chúng là cùng một sự kiện.

**Bài tập 3 — Giờ mở cửa qua nửa đêm.** Một cửa hàng mở lúc 22:00 và đóng lúc 02:00 ngày hôm sau. Thiết kế hàm nhận `LocalDate`, hai `LocalTime` và `ZoneId` để tính cặp instant mở/đóng. Tại sao không thể dùng một phép so sánh `LocalTime.isBefore` để quyết định mọi trường hợp?

**Bài tập 4 — Khoảng báo cáo theo ngày.** Viết hàm tính `startInclusive` và `endExclusive` từ một `LocalDate` và `ZoneId`. Thử với ngày đổi DST tại `America/New_York` rồi so sánh khoảng thời gian với cách cộng cố định 24 giờ.

**Bài tập 5 — Định nghĩa hợp đồng API.** Hệ thống cần trả về thời điểm thanh toán và một lịch mở cửa định kỳ. Chọn kiểu Java, cột SQL và trường JSON cho từng dữ liệu; giải thích vì sao một trường dùng instant còn trường kia dùng local time + zone.

## 15. Ghi nhớ

**`LocalDate` là ngày lịch; `LocalTime` là giờ trên đồng hồ; `LocalDateTime` là ngày cộng giờ địa phương. Cả ba đều không chứa timezone hoặc UTC offset.** Trong Spring Data JDBC, chúng thường ánh xạ với `DATE`, `TIME` và `TIMESTAMP` không timezone; kiểu cột cụ thể và precision phụ thuộc database/driver.

Khi cần biết **một sự kiện xảy ra vào instant nào**, dùng `Instant` hoặc chuyển từ local date-time bằng một `ZoneId` đã được chọn rõ. Khi cần giữ **ý định lịch địa phương**, lưu cả giờ/ngày địa phương và zone ID; xử lý công khai quy tắc DST. Một quy ước nhất quán từ mô hình Java, schema SQL, repository đến hợp đồng API sẽ ngăn những lỗi lệch ngày, lệch giờ và không thể đối chiếu sự kiện giữa nhiều múi giờ.

### Tài liệu tham khảo

- [Java 21 – `LocalDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), [`LocalTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html), [`LocalDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)
- [Java 21 – `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html), [`Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)
- [Spring Data Relational – Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
