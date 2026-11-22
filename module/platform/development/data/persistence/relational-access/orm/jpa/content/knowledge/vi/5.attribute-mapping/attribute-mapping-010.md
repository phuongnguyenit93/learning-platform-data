# Làm việc với kiểu thời gian cũ và Temporal khi cần

Trong JPA/Hibernate, một thuộc tính thời gian của entity có thể mang ý nghĩa **chỉ ngày**, **chỉ giờ**, hoặc **ngày và giờ**. Với mã Java cũ sử dụng `java.util.Date` hay `java.util.Calendar`, annotation `@Temporal` cho JPA biết phải ánh xạ thuộc tính đó tới dạng SQL nào: `DATE`, `TIME` hoặc `TIMESTAMP`. Hiểu chính xác lựa chọn này giúp tránh mất giờ khi lưu ngày, lưu sai ngày do múi giờ, và sai kết quả khi truy vấn theo khoảng thời gian.

Trong ứng dụng mới, nên ưu tiên kiểu rõ nghĩa của `java.time` như `LocalDate`, `LocalTime`, `LocalDateTime` và `Instant`. Tuy nhiên, khi bảo trì hệ thống legacy, bạn vẫn cần hiểu `Date`, `Calendar`, `java.sql.*` và cách dùng `@Temporal` một cách có chủ đích.

## 1. Phân loại dữ liệu thời gian từ góc nhìn nghiệp vụ

Trước khi viết annotation, hãy hỏi: giá trị mà ứng dụng cần lưu thực sự là gì?

| Thông tin | Bản chất | Java hiện đại | SQL điển hình |
|---|---|---|---|
| Ngày sinh | Một ngày trên lịch, không có giờ | `LocalDate` | `DATE` |
| Giờ cửa hàng mở cửa hằng ngày | Giờ trong ngày, không có ngày | `LocalTime` | `TIME` |
| Lịch hẹn lúc 09:00 ngày 15/11 tại một địa điểm | Ngày và giờ theo khu vực; cần biết múi giờ nơi hẹn khi chuyển thành mốc toàn cầu | `LocalDateTime` + `ZoneId`, hoặc `ZonedDateTime` theo domain | Timestamp và khi cần thêm zone ID |
| Thời điểm đơn hàng được tạo | Mốc thời gian đã xảy ra, so sánh được giữa nhiều hệ thống | `Instant` | Timestamp với chính sách lưu instant rõ ràng |
| Giờ địa phương của một lịch làm việc lặp lại | Giờ trên đồng hồ gắn với quy tắc vùng địa lý | `LocalTime` và `ZoneId` | `TIME` và khi cần cột zone |
| Hạn cuối của một ngày | Biên ngày theo timezone nghiệp vụ | `LocalDate`, chuyển thành biên giờ khi truy vấn | `DATE` hoặc timestamp tùy mô hình |

Ba khái niệm SQL nền tảng:

- **`DATE`** lưu năm, tháng, ngày; không chứa giờ.
- **`TIME`** lưu giờ, phút, giây và phần giây nếu DBMS hỗ trợ; không chứa ngày.
- **`TIMESTAMP`** lưu cả ngày lẫn giờ. Chuyện offset/timezone được lưu, diễn giải hay chuẩn hóa như thế nào phụ thuộc kiểu timestamp của DBMS và quá trình bind dữ liệu.

Đừng đồng nhất một chuỗi `2026-11-15 09:00` với một instant. Nếu chưa biết zone hoặc quy tắc diễn giải, nó chưa xác định duy nhất một mốc thời gian toàn cầu.

## 2. Các kiểu thời gian legacy trong Java

### 2.1. java.util.Date

`java.util.Date` đại diện cho mốc thời gian qua số mili giây kể từ Unix epoch; nó **không giữ một ZoneId hay TimeZone riêng**. Phương thức `toString()` hiển thị theo timezone mặc định của JVM nên dễ khiến người đọc nhầm rằng `Date` có timezone.

~~~java
import java.util.Date;

Date now = new Date();
long millis = now.getTime();

System.out.println(millis);
System.out.println(now);
~~~

Các đặc điểm quan trọng:

1. `Date` có thể chứa đủ thời điểm đến mili giây, chứ không chỉ có phần ngày như tên gọi gợi ý.
2. `Date` mutable; người có reference có thể gọi `setTime(...)` để thay đổi đối tượng.
3. Nhiều constructor và phương thức cũ thao tác từng trường ngày giờ của `Date` đã bị deprecated.
4. Khi đọc cùng một instant trong các timezone khác nhau, **ngày và giờ hiển thị có thể khác nhau** dù số epoch milliseconds không đổi.

Vì vậy dùng `Date` để biểu diễn ngày sinh là một nhượng bộ tương thích legacy, không phải lựa chọn diễn đạt domain tốt nhất.

### 2.2. java.util.Calendar

`Calendar` là API lịch cũ có trường năm, tháng, ngày, giờ và một `TimeZone` dùng để tính toán.

~~~java
import java.util.Calendar;
import java.util.TimeZone;

Calendar meeting = Calendar.getInstance(
    TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);
meeting.set(2026, Calendar.NOVEMBER, 15, 9, 30, 0);
meeting.set(Calendar.MILLISECOND, 0);

Date pointInTime = meeting.getTime();
~~~

Không tự viết số tháng 10 để ám chỉ tháng 11 nếu người đọc không biết `Calendar` đánh số tháng từ 0; dùng hằng số `Calendar.NOVEMBER` rõ ràng hơn.

`Calendar` cũng mutable; có thông tin timezone ở object Java không đồng nghĩa với việc trường timezone đó sẽ được lưu nguyên vẹn vào cột SQL.

### 2.3. Các kiểu java.sql.Date, Time, Timestamp

JDBC có các lớp legacy chuyên biệt:

| Kiểu | Chủ yếu liên quan tới | Lưu ý |
|---|---|---|
| `java.sql.Date` | `DATE` | Ngữ nghĩa chỉ ngày; `toInstant()` không được hỗ trợ |
| `java.sql.Time` | `TIME` | Ngữ nghĩa thời gian trong ngày, không phải instant đầy đủ |
| `java.sql.Timestamp` | `TIMESTAMP` | Hỗ trợ phần nano giây; API kế thừa và hợp đồng so sánh có những bất tiện lịch sử |

Các lớp `java.sql.*` hỗ trợ tương tác JDBC. Đừng nhầm `java.sql.Date` với `java.util.Date` chỉ vì tên lớp giống nhau. Nếu cùng dùng trong một file, nên ghi rõ package khi cần.

**Quy tắc quan trọng:** `@Temporal` dành cho `java.util.Date` và `java.util.Calendar`, không phải công cụ để biến một trường `java.sql.Date` hay `java.time.LocalDate` thành kiểu khác.

## 3. @Temporal: chỉ định phần thời gian cần lưu

Với Jakarta Persistence, import:

~~~java
import jakarta.persistence.Temporal;
import jakarta.persistence.TemporalType;
~~~

Dự án dùng JPA đời cũ có thể sử dụng `javax.persistence.Temporal` và `javax.persistence.TemporalType`. Các package này thuộc các thế hệ API khác nhau; phải dùng đồng bộ với version của ứng dụng và provider.

Có ba lựa chọn:

| Cách khai báo | Ý nghĩa khi ánh xạ legacy Date/Calendar | Cột SQL thường tương ứng |
|---|---|---|
| `@Temporal(TemporalType.DATE)` | Lưu phần **ngày** | `DATE` |
| `@Temporal(TemporalType.TIME)` | Lưu phần **giờ** | `TIME` |
| `@Temporal(TemporalType.TIMESTAMP)` | Lưu **ngày và giờ** | `TIMESTAMP` |

Ví dụ:

~~~java
@Entity
public class LegacyEvent {
    @Id
    private Long id;

    @Temporal(TemporalType.DATE)
    private Date eventDate;

    @Temporal(TemporalType.TIME)
    private Date openingTime;

    @Temporal(TemporalType.TIMESTAMP)
    private Date recordedAt;
}
~~~

Dù ba thuộc tính cùng là `Date` tại runtime, dữ liệu được lưu có **ý nghĩa khác nhau**. Khi bảo trì entity chứa `Date`/`Calendar`, nên khai báo `@Temporal` tường minh để tránh phụ thuộc giả định của người đọc hoặc khác biệt về cách provider xử lý mapping legacy.

### 3.1. @Temporal không biến java.util.Date thành LocalDate

~~~java
@Temporal(TemporalType.DATE)
private Date birthday;
~~~

Sau khi load, getter vẫn trả `java.util.Date`. Vì `DATE` chỉ lưu ngày, JPA/JDBC phải chuyển ngày đó thành một object `Date` vốn biểu diễn mốc thời gian. Giờ xuất hiện khi in object thường là hệ quả của cách chuyển đổi và timezone; **nó không phải dữ liệu giờ đã được lưu trong cột DATE**.

Tương tự, với `@Temporal(TIME)`, phần ngày giả định trong object `Date` không phải dữ liệu nghiệp vụ được bảo toàn qua cột `TIME`.

### 3.2. TIMESTAMP không đồng nghĩa tự động lưu timezone

~~~java
@Temporal(TemporalType.TIMESTAMP)
private Date createdAt;
~~~

Annotation trên chọn ngày cộng giờ. Nó không có nghĩa “bắt buộc UTC”, “tự biết giờ của người dùng”, hay “bảo toàn tên timezone gốc”. Những quy tắc đó được xác định ở thiết kế domain, schema và cách provider/JDBC driver chuyển đổi.

Chẳng hạn trên PostgreSQL:

- `TIMESTAMP WITHOUT TIME ZONE` lưu ngày/giờ không mang offset.
- `TIMESTAMP WITH TIME ZONE` biểu diễn mốc thời gian theo semantics của PostgreSQL, được chuẩn hóa, nhưng không lưu lại tên zone gốc như `Asia/Ho_Chi_Minh`.

Các DBMS khác có thể xử lý `DATETIME`, `TIMESTAMP` và timezone khác nhau. Vì vậy, kiểm tra kiểu cột thực tế trước khi quyết định chiến lược đọc/ghi.

### 3.3. Field access hay property access?

Nếu entity đặt `@Id` trên field, nên đặt `@Temporal` trên field tương ứng:

~~~java
@Id
private Long id;

@Temporal(TemporalType.DATE)
private Date startDate;
~~~

Nếu entity dùng property access với `@Id` trên getter, annotation mapping sẽ đặt trên getter:

~~~java
@Id
public Long getId() {
    return id;
}

@Temporal(TemporalType.DATE)
public Date getStartDate() {
    return startDate;
}
~~~

Đừng kết hợp field/getter mapping tùy tiện; cần dùng `@Access` có chủ đích nếu muốn thay đổi chiến lược mặc định.

## 4. Ví dụ thực tế: ánh xạ một bảng lịch làm việc legacy

Giả sử bảng `legacy_schedules` cần lưu ngày áp dụng, giờ bắt đầu làm việc, và thời điểm cập nhật bản ghi. Chương trình cũ sử dụng `Date` cho cả ba.

~~~java
package com.example.legacy;

import jakarta.persistence.*;
import java.util.Date;
import java.util.Objects;

@Entity
@Table(name = "legacy_schedules")
public class LegacySchedule {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Temporal(TemporalType.DATE)
    @Column(name = "effective_date", nullable = false)
    private Date effectiveDate;

    @Temporal(TemporalType.TIME)
    @Column(name = "start_time", nullable = false)
    private Date startTime;

    @Temporal(TemporalType.TIMESTAMP)
    @Column(name = "updated_at", nullable = false)
    private Date updatedAt;

    protected LegacySchedule() {
        // Constructor không tham số dành cho JPA.
    }

    public LegacySchedule(Date effectiveDate, Date startTime) {
        this.effectiveDate = copy(effectiveDate);
        this.startTime = copy(startTime);
        this.updatedAt = new Date();
    }

    public Long getId() {
        return id;
    }

    public Date getEffectiveDate() {
        return copy(effectiveDate);
    }

    public Date getStartTime() {
        return copy(startTime);
    }

    public Date getUpdatedAt() {
        return copy(updatedAt);
    }

    public void changeStartTime(Date newStartTime) {
        this.startTime = copy(newStartTime);
        this.updatedAt = new Date();
    }

    private static Date copy(Date input) {
        return new Date(Objects.requireNonNull(input).getTime());
    }
}
~~~

Mỗi thuộc tính có mapping khác nhau:

- `effectiveDate` → ngày theo lịch; giờ của object Date không được dùng để lưu.
- `startTime` → giờ trong ngày; phần ngày của object Date không được dùng để lưu.
- `updatedAt` → ngày và giờ của mốc cập nhật, với chính sách timezone của hệ thống phải rõ ràng.

### 4.1. Schema cơ bản

Ví dụ DDL PostgreSQL:

~~~sql
CREATE TABLE legacy_schedules (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    effective_date DATE NOT NULL,
    start_time TIME NOT NULL,
    updated_at TIMESTAMP(3) WITHOUT TIME ZONE NOT NULL
);
~~~

Cột `updated_at` đang là timestamp **không có timezone**, nên khi coi nó là mốc tuyệt đối cần đặt rõ quy ước: giá trị được ghi theo UTC hay theo giờ địa phương nào. Nếu môi trường có nhiều timezone và cần lưu sự kiện tuyệt đối, hãy thiết kế kiểu cột/chuyển đổi phù hợp. Không mặc định rằng mọi DBMS dùng cùng cú pháp hoặc precision như PostgreSQL.

### 4.2. Bảo vệ Date mutable bằng defensive copy

Nếu entity giữ trực tiếp reference `Date` từ bên ngoài, caller có thể sửa object đã truyền vào:

~~~java
Date supplied = new Date();
LegacySchedule schedule = new LegacySchedule(supplied, supplied);

supplied.setTime(0L); // Không được vô tình thay đổi dữ liệu nội bộ.
~~~

Ví dụ entity sử dụng `new Date(input.getTime())` và getter trả bản sao để ngăn caller chỉnh mutable object đang được giữ trong entity. Một API cho phép caller gọi `entity.getUpdatedAt().setTime(...)` trực tiếp dễ dẫn tới trạng thái khó kiểm soát. Với kiểu bất biến như `Instant`, vấn đề này giảm đáng kể.

### 4.3. Với Calendar thì sao?

Nếu ứng dụng cũ dùng `Calendar`:

~~~java
import java.util.Calendar;

@Temporal(TemporalType.TIMESTAMP)
@Column(name = "scheduled_at")
private Calendar scheduledAt;
~~~

`Calendar` có TimeZone trong bộ nhớ, nhưng cột SQL timestamp thông thường không tự lưu tên vùng thời gian; nếu cần tái tạo nơi hẹn chính xác, phải thiết kế lưu vùng thời gian rõ ràng. `Calendar` cũng mutable, nên getter/setter có thể cần clone hoặc chuyển sang kiểu `java.time`.

## 5. Lưu và đọc dữ liệu với EntityManager

Giả sử `EntityManagerFactory` đã cấu hình và ứng dụng Java SE dùng transaction kiểu `RESOURCE_LOCAL`:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Date effective = java.sql.Date.valueOf("2026-11-15");
    Date start = java.sql.Time.valueOf("09:00:00");

    LegacySchedule row = new LegacySchedule(effective, start);
    em.persist(row);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

`java.sql.Date` và `java.sql.Time` là subclass của `java.util.Date`, nên có thể truyền vào constructor. Ví dụ trên chỉ dùng chúng để tạo giá trị tương thích legacy; trong code mới, nên dùng `LocalDate` và `LocalTime`.

Đọc lại bằng một context khác:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
try {
    LegacySchedule loaded = em.find(LegacySchedule.class, rowId);
    if (loaded != null) {
        Date day = loaded.getEffectiveDate();
        Date hour = loaded.getStartTime();
        Date timestamp = loaded.getUpdatedAt();
    }
} finally {
    em.close();
}
~~~

**Không suy luận thời gian đầy đủ từ `day` hoặc `hour`**, dù cả hai đều được biểu diễn bằng `Date` trong Java. Database chỉ lưu thành phần tương ứng với cột.

## 6. Bind tham số thời gian trong JPQL

Ngoài annotation trên entity, JPA còn có overload nhận `Date` hoặc `Calendar` kèm `TemporalType` khi bind tham số:

~~~java
query.setParameter("day", dateValue, TemporalType.DATE);
query.setParameter("from", timestampValue, TemporalType.TIMESTAMP);
~~~

Đây là một cơ chế khác với `@Temporal` của field: nó thông báo cách diễn giải **tham số truy vấn** kiểu legacy.

### 6.1. Tìm bản ghi theo cột DATE

~~~java
Date requestedDay = java.sql.Date.valueOf("2026-11-15");

List<LegacySchedule> rows = em.createQuery(
        """
        SELECT s FROM LegacySchedule s
        WHERE s.effectiveDate = :day
        """,
        LegacySchedule.class
    )
    .setParameter("day", requestedDay, TemporalType.DATE)
    .getResultList();
~~~

Vì `effectiveDate` ánh xạ SQL `DATE`, sử dụng `TemporalType.DATE` cho tham số là lựa chọn phù hợp.

### 6.2. Tìm bản ghi timestamp trong một ngày

Nếu dữ liệu là timestamp, không so sánh thẳng bằng một `Date` đại diện đầu ngày. Hãy xác định khoảng `[startOfDay, nextStartOfDay)` theo múi giờ nghiệp vụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate targetDay = LocalDate.of(2026, 11, 15);

Instant start = targetDay
    .atStartOfDay(zone)
    .toInstant();

Instant endExclusive = targetDay
    .plusDays(1)
    .atStartOfDay(zone)
    .toInstant();

List<LegacySchedule> rows = em.createQuery(
        """
        SELECT s FROM LegacySchedule s
        WHERE s.updatedAt >= :start
          AND s.updatedAt < :end
        ORDER BY s.updatedAt
        """,
        LegacySchedule.class
    )
    .setParameter("start", Date.from(start), TemporalType.TIMESTAMP)
    .setParameter("end", Date.from(endExclusive), TemporalType.TIMESTAMP)
    .getResultList();
~~~

Khoảng **đầu bao gồm, cuối không bao gồm** tránh phải đoán “cuối ngày” ở `23:59:59.999`. Nó cũng phù hợp với database có precision nhỏ hơn/lớn hơn mili giây và tránh đếm trùng biên giữa hai ngày.

**Lưu ý thiết yếu:** cách bind `Date` và kiểu cột `updated_at` phải theo cùng một quy ước timezone. Nếu dữ liệu `TIMESTAMP WITHOUT TIME ZONE` đang được ghi theo giờ địa phương, dùng instant biên UTC mà không cấu hình chuyển đổi thống nhất có thể cho kết quả sai. Cần biết dữ liệu đã được lưu theo quy ước nào trước khi áp dụng truy vấn.

Đối với timezone có daylight saving time, khoảng giữa đầu hai ngày liên tiếp có thể dài 23 hoặc 25 giờ; vì vậy tính mỗi biên bằng `atStartOfDay(zone)`, không cộng cố định 24 giờ.

### 6.3. Calendar làm tham số truy vấn

~~~java
Calendar cutoff = Calendar.getInstance(
    java.util.TimeZone.getTimeZone("UTC")
);
cutoff.set(2026, Calendar.NOVEMBER, 15, 0, 0, 0);
cutoff.set(Calendar.MILLISECOND, 0);

List<LegacySchedule> rows = em.createQuery(
        "SELECT s FROM LegacySchedule s WHERE s.updatedAt >= :cutoff",
        LegacySchedule.class
    )
    .setParameter("cutoff", cutoff, TemporalType.TIMESTAMP)
    .getResultList();
~~~

Cách bind `Calendar` này dùng `TemporalType.TIMESTAMP`. Bản thân `Calendar` có timezone không bảo đảm database lưu lại `ZoneId`.

### 6.4. Phân biệt Temporal của JPA và Spring Data JPA

Một số phiên bản Spring Data JPA hỗ trợ annotation `org.springframework.data.jpa.repository.Temporal` trên tham số repository kiểu `Date` để chọn temporal binding. Đây **không phải** `jakarta.persistence.Temporal` gắn trên thuộc tính entity.

| Vị trí | Cơ chế | Mục đích |
|---|---|---|
| Field/getter của entity dùng Date/Calendar | `jakarta.persistence.Temporal` | Cách ánh xạ thuộc tính xuống SQL |
| JPQL `Query#setParameter` | `TemporalType` trong overload của `setParameter` | Cách bind tham số Date/Calendar |
| Repository parameter của Spring Data JPA | `org.springframework.data.jpa.repository.Temporal` khi phiên bản hỗ trợ | Hỗ trợ bind tham số Date ở tầng repository |

Nếu thấy hai annotation cùng tên `Temporal`, hãy kiểm tra import và nơi sử dụng trước khi chỉnh sửa.

## 7. Những cách sử dụng sai phổ biến

### 7.1. Gắn @Temporal lên kiểu java.time

~~~java
// Không nên viết:
@Temporal(TemporalType.DATE)
private LocalDate birthDate;

@Temporal(TemporalType.TIMESTAMP)
private LocalDateTime updatedAt;
~~~

`@Temporal` chỉ dành cho `java.util.Date` và `java.util.Calendar`. Với kiểu `java.time` được JPA/provider hỗ trợ, dùng mapping phù hợp và **không gắn `@Temporal`**:

~~~java
@Column(name = "birth_date")
private LocalDate birthDate;

@Column(name = "updated_at")
private LocalDateTime updatedAt;
~~~

Khi dùng `Instant` hoặc `ZonedDateTime`, phải biết provider, phiên bản Jakarta Persistence và dialect đang ánh xạ thế nào. Đừng coi mọi tính năng riêng của Hibernate là portable trên tất cả JPA provider.

### 7.2. Lưu thời điểm sự kiện bằng TemporalType.DATE

~~~java
@Temporal(TemporalType.DATE)
private Date paymentAt;
~~~

Nếu `paymentAt` cần giờ/phút/giây, `DATE` không đủ thông tin. Phần giờ có thể bị mất sau roundtrip qua database. Với legacy Date biểu diễn instant, `TIMESTAMP` phù hợp hơn, đồng thời cần quy định timezone. Trong mã mới, `Instant` thường biểu diễn ý nghĩa rõ hơn.

### 7.3. Lưu ngày sinh như một timestamp

Ngày sinh theo lịch không nên mặc nhiên bị “đổi giờ” theo timezone người xem. Nếu lưu timestamp đại diện nửa đêm ở một vùng, người ở vùng khác có thể nhìn thành ngày trước đó. Dữ liệu như ngày sinh nên là `LocalDate`/SQL `DATE`; với legacy Date dùng `@Temporal(DATE)` và chú ý cách diễn giải timezone khi chuyển đổi.

### 7.4. Cho rằng Date chứa timezone

~~~java
Date when = new Date();
// Không có thuộc tính ZoneId bên trong java.util.Date.
~~~

Giữ giá trị instant và chuyển nó sang zone khi hiển thị:

~~~java
String text = when.toInstant()
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .format(java.time.format.DateTimeFormatter.ISO_ZONED_DATE_TIME);
~~~

Đừng cộng/trừ số giờ thủ công vào epoch milliseconds chỉ để “sửa lệch múi giờ”. Hãy dùng `ZoneId` và API chuyển đổi đúng.

### 7.5. So sánh timestamp bằng một chuỗi DATE

~~~sql
-- Câu dưới có thể chỉ so sánh với mốc đầu ngày:
SELECT * FROM legacy_schedules
WHERE updated_at = '2026-11-15';
~~~

Muốn tìm mọi bản ghi trong ngày, truy vấn theo khoảng từ đầu ngày đến đầu ngày sau. Cách SQL literal được implicit cast phụ thuộc DBMS, nên tốt nhất là bind tham số có kiểu rõ ràng.

### 7.6. Coi precision của Date và database như nhau

`java.util.Date` lưu độ phân giải mili giây, còn nhiều DBMS có phần giây đến microsecond; `java.sql.Timestamp` và các kiểu `java.time` có thể biểu diễn nano giây. Provider và JDBC driver có thể làm tròn hoặc cắt bớt, vì vậy không phụ thuộc việc đọc lại chính xác từng nanosecond khi schema không hỗ trợ.

### 7.7. Dùng Date mutable trong equals/hashCode

Một `Date` mutable tham gia `equals()`/`hashCode()` của entity có thể làm giá trị hash thay đổi khi object bị sửa. Nếu entity đã ở trong `HashSet`, hành vi tra cứu có thể bất ngờ. Với `Date`/`Calendar`, nên giới hạn mutation và thiết kế định danh entity tách khỏi các giá trị thời gian dễ đổi.

## 8. Chuyển sang java.time trong thiết kế mới

Các kiểu `java.time` tách rõ ý nghĩa domain:

| Java type | Ngữ nghĩa | Mapping thường gặp |
|---|---|---|
| `LocalDate` | Ngày trên lịch | SQL `DATE` |
| `LocalTime` | Giờ trong ngày | SQL `TIME` |
| `LocalDateTime` | Ngày và giờ địa phương không gắn offset | SQL `TIMESTAMP` không có timezone |
| `Instant` | Mốc thời gian trên trục UTC | Timestamp theo cơ chế provider/schema rõ ràng |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Kiểu timestamp phù hợp nếu provider/DBMS hỗ trợ; offset gốc không luôn được giữ |
| `ZonedDateTime` | Ngày giờ gắn với vùng và quy tắc timezone | Cần cơ chế mapping/provider hoặc lưu thêm zone ID |

JPA 2.2 đã hỗ trợ các kiểu Java 8 phổ biến như `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetTime` và `OffsetDateTime`. Các kiểu khác như `Instant` hay `ZonedDateTime` cần xét phiên bản đặc tả/provider đang dùng; Hibernate ORM hiện đại có hỗ trợ riêng cho nhiều kiểu trong số đó.

### 8.1. Entity hiện đại tương đương ví dụ legacy

~~~java
package com.example.modern;

import jakarta.persistence.*;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;

@Entity
@Table(name = "opening_schedules")
public class OpeningSchedule {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "effective_date", nullable = false)
    private LocalDate effectiveDate;

    @Column(name = "start_time", nullable = false)
    private LocalTime startTime;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected OpeningSchedule() {}

    public OpeningSchedule(
        LocalDate effectiveDate,
        LocalTime startTime,
        Instant updatedAt
    ) {
        this.effectiveDate = effectiveDate;
        this.startTime = startTime;
        this.updatedAt = updatedAt;
    }

    public LocalDate getEffectiveDate() {
        return effectiveDate;
    }

    public LocalTime getStartTime() {
        return startTime;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Ví dụ giả định JPA provider hỗ trợ `Instant` với mapping được cấu hình tương thích database. Không có `@Temporal` vì kiểu Java đã mô tả rõ ý nghĩa của từng field.

Một lợi ích quan trọng: `LocalDate`, `LocalTime` và `Instant` là immutable. Những thao tác như `date.plusDays(1)` tạo giá trị mới, không sửa object cũ, nhờ vậy API entity tránh được nhiều vấn đề do `Date`/`Calendar` mutable.

### 8.2. LocalDateTime không phải Instant

`LocalDateTime.of(2026, 11, 15, 9, 0)` chỉ nói “9 giờ ngày 15/11”, chưa nói đó là 9 giờ ở Hà Nội, Tokyo hay New York. Nếu phải tạo instant, cần thêm vùng hoặc offset:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 11, 15, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant = local.atZone(zone).toInstant();
~~~

Việc ghép một local date-time với zone còn cần xử lý những giờ bị thiếu hoặc trùng lặp trong khu vực có daylight saving time. Nếu lập lịch cho các địa điểm như vậy, cần quyết định nghiệp vụ cho những thời điểm không tồn tại hoặc mơ hồ.

## 9. Các phép chuyển đổi legacy thường gặp

### 9.1. Date ↔ Instant

~~~java
Date legacy = new Date();

Instant instant = legacy.toInstant();
Date again = Date.from(instant);
~~~

Đây là phép chuyển đổi phù hợp khi Date thực sự biểu diễn một instant. `Date` chỉ giữ mili giây, nên chuyển một `Instant` có nano giây sang Date có thể mất phần nhỏ hơn mili giây.

### 9.2. Date → LocalDate

Cần xác định zone, vì một instant có thể rơi vào hai ngày lịch khác nhau ở hai nơi:

~~~java
Date legacy = new Date();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate date = legacy.toInstant()
    .atZone(businessZone)
    .toLocalDate();
~~~

Chiều ngược:

~~~java
LocalDate date = LocalDate.of(2026, 11, 15);

Date legacyAtDayStart = Date.from(
    date.atStartOfDay(businessZone).toInstant()
);
~~~

Dùng một instant để thay cho LocalDate là một **quy ước biểu diễn**, không có nghĩa ngày lịch vốn chứa timezone hoặc giờ.

Với `java.sql.Date` lấy trực tiếp từ JDBC:

~~~java
java.sql.Date sqlDate = resultSet.getDate("effective_date");
LocalDate localDate = sqlDate.toLocalDate();
~~~

Không gọi `sqlDate.toInstant()`; phương thức đó không được hỗ trợ trên `java.sql.Date`.

### 9.3. Calendar → ZonedDateTime

~~~java
Calendar legacyCalendar = Calendar.getInstance(
    java.util.TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);

ZonedDateTime zoned = legacyCalendar.toInstant()
    .atZone(legacyCalendar.getTimeZone().toZoneId());
~~~

Cách chuyển giữ instant đang có và diễn giải theo TimeZone của Calendar. Nếu Calendar được tạo với timezone sai từ đầu, phép chuyển không tự đoán lại zone đúng.

### 9.4. Timestamp → Instant

~~~java
java.sql.Timestamp legacyTimestamp = java.sql.Timestamp.from(
    Instant.parse("2026-11-15T02:00:00Z")
);
Instant instant = legacyTimestamp.toInstant();
~~~

Khả năng bảo toàn phần nano giây phụ thuộc cột SQL và JDBC driver. Nếu qua `java.util.Date`, có thể bị mất precision.

## 10. Timezone: chọn cách lưu nhất quán

### 10.1. Mốc sự kiện toàn cầu

Ví dụ `createdAt`, `paidAt`, `updatedAt` là những mốc đã xảy ra. Trong domain, `Instant` thường phù hợp. Khi hiển thị cho người dùng, chuyển sang zone của họ. Không được lẫn lộn việc **lưu instant** và **hiển thị giờ địa phương**.

### 10.2. Giờ lặp lại theo địa điểm

Ví dụ “cửa hàng mở cửa 09:00 mỗi ngày tại Hà Nội”. Đó không phải một instant cố định, mà là `LocalTime 09:00` gắn với `ZoneId Asia/Ho_Chi_Minh` nếu cần chuyển thành các mốc ngày cụ thể. Lưu một `Instant` duy nhất sẽ không mô tả đúng lịch lặp lại.

### 10.3. Cấu hình timezone của Hibernate

Một cấu hình quen thuộc:

~~~properties
hibernate.jdbc.time_zone=UTC
~~~

Tùy phiên bản/provider và kiểu JDBC, tùy chọn trên có thể ảnh hưởng cách Hibernate bind/extract giá trị thời gian. Nó **không làm cột `TIMESTAMP WITHOUT TIME ZONE` có thể lưu zone ID**; cũng không sửa được dữ liệu cũ từng ghi theo timezone khác.

Để dùng đúng, phải biết cả bốn yếu tố: kiểu Java, kiểu SQL thực tế, quy tắc dữ liệu hiện hữu và cách provider/JDBC driver chuyển đổi. Đừng chỉ thêm cấu hình UTC rồi mặc định mọi timestamp sẽ đúng.

## 11. Di chuyển dữ liệu từ Date/Calendar sang java.time

Thay đổi khai báo Java có thể rất dễ:

~~~java
// Legacy
@Temporal(TemporalType.DATE)
private Date birthday;

// Hiện đại
private LocalDate birthday;
~~~

Nếu schema đã là SQL `DATE` và ý nghĩa nghiệp vụ đúng là ngày lịch, thay đổi này thường trực tiếp. Nhưng nếu schema đang là `TIMESTAMP`, chỉ đổi kiểu Java có thể **làm mất thông tin** hoặc **chuyển lệch ngày**.

Ví dụ các trường hợp phải làm rõ:

| Dữ liệu cũ | Điều cần xác định trước khi migrate |
|---|---|
| `birthday TIMESTAMP` | Ngày được nhập theo zone nào, phần giờ có mang ý nghĩa thật không? |
| `created_at TIMESTAMP WITHOUT TIME ZONE` | Dữ liệu được lưu theo UTC hay theo local time? Có nhiều service với quy tắc khác nhau không? |
| `daily_start TIMESTAMP` | Phần ngày là ngày thật hay một ngày giả được dùng để chứa giờ? |
| `expiration_date DATE` | Hết hạn vào đầu hay cuối ngày? Theo timezone của ai? |
| `schedule_at TIMESTAMP` | Địa điểm lịch hẹn ở đâu? Có cần giữ nguyên zone ID và quy tắc DST không? |

Nếu cần chuyển schema, nên dùng migration có kiểm soát như Flyway/Liquibase, xác định quy tắc trước khi cập nhật dữ liệu và đảm bảo các phiên bản ứng dụng chạy song song không ghi theo hai timezone khác nhau.

**Không có annotation nào khôi phục được timezone đã thất lạc** hoặc phần giờ đã bị cắt đi vì lưu vào SQL `DATE`. Đừng kỳ vọng đổi `TemporalType.DATE` thành `TIMESTAMP` sẽ tự làm dữ liệu cũ đầy đủ hơn.

### 11.1. Chọn nguồn tạo createdAt

Có thể cấp giá trị từ service với `Clock` được inject, từ `Instant.now()` trong code, từ callback `@PrePersist`, hoặc default/trigger ở database. Nhưng phải chọn chính sách rõ ràng để tránh các mốc tạo bản ghi được ghi theo các clock/timezone không nhất quán.

Ví dụ:

~~~java
@PrePersist
void assignCreationTime() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
~~~

Trong hệ thống cần kiểm thử thời gian chủ động, dùng `Clock` được cung cấp bởi service giúp đơn giản hóa kiểm soát nguồn thời gian.

## 12. Những câu hỏi thường gặp

### Có phải trường thời gian nào cũng cần @Temporal?

Không. `@Temporal` dành cho mapping JPA của `java.util.Date`/`java.util.Calendar` legacy. Với `java.time` được provider hỗ trợ, dùng các mapping tương ứng mà không gắn annotation này.

### @Temporal(TIMESTAMP) có luôn lưu UTC?

Không. Nó xác định ngày + giờ, không định nghĩa mọi khía cạnh timezone. Cần xác định loại cột DB và cách provider/JDBC diễn giải giá trị.

### Vì sao trường @Temporal(DATE) đọc lại vẫn in ra giờ?

Vì trong Java nó vẫn là `Date`, một object biểu diễn mốc thời gian. Provider phải biến SQL date-only thành một Date instance theo một cách phù hợp. Phần giờ hiển thị không phải giờ nghiệp vụ đã lưu trong cột DATE.

### Có dùng TemporalType.TIME với Date không?

Có trong legacy mapping, khi nghiệp vụ chỉ yêu cầu giờ trong ngày. Tuy nhiên `LocalTime` diễn đạt ý nghĩa này tốt hơn cho code mới.

### Calendar có lưu timezone vào cột TIMESTAMP không?

Không tự động. Object Calendar có TimeZone, nhưng kiểu cột SQL thường không lưu zone ID gốc. Nếu domain cần giữ zone theo khu vực, phải có mapping/schema riêng.

### Nếu hai server ở timezone khác nhau thì Date có bằng nhau không?

Nếu chúng đại diện cùng instant, giá trị epoch milliseconds vẫn có thể bằng nhau. Nhưng chuỗi hiển thị và cách lưu/đọc một SQL timestamp không mang timezone có thể khác, tùy cấu hình chuyển đổi.

### Vì sao không truy vấn created_at bằng equals cho một ngày?

Vì SQL timestamp chứa cả giờ. Equality có thể chỉ khớp một thời điểm đầu ngày; muốn lấy toàn bộ một ngày hãy dùng khoảng `[start, end)` theo zone nghiệp vụ và schema thực tế.

## 13. Bài tập thực hành

**Bài 1:** Hệ thống cũ có:

~~~java
private Date birthDate;
private Date officeOpenTime;
private Date lastLoginAt;
~~~

Hãy chọn `@Temporal` phù hợp cho từng trường và giải thích phần dữ liệu nào không được lưu lại. Gợi ý: `DATE`, `TIME` và `TIMESTAMP` tương ứng với ngày lịch, giờ trong ngày và mốc ngày giờ.

**Bài 2:** Chuyển ba trường trên sang các kiểu `java.time` phù hợp. Giải thích vì sao không cần `@Temporal` cho các kiểu mới và trường nào cần quy định timezone.

**Bài 3:** Viết JPQL tìm tất cả bản ghi có `createdAt` nằm trong ngày 15/11/2026 theo zone `Asia/Ho_Chi_Minh`. Dùng hai tham số timestamp và cận trên mở, đồng thời chỉ ra điều kiện cần biết về kiểu cột và quy tắc lưu dữ liệu.

**Bài 4:** Một bảng lưu `birthday TIMESTAMP`, đa số hàng có giờ `00:00` nhưng một số hàng có `07:00`. Trước khi đổi sang `LocalDate` và `DATE`, cần kiểm tra timezone và quy tắc nhập liệu nào để không làm sai ngày?

**Bài 5:** Giả sử lịch hẹn diễn ra lúc 09:00 ở một quốc gia có daylight saving time. Vì sao chỉ lưu `LocalDateTime` hoặc một offset cố định có thể chưa đủ để tính đúng mốc thời gian của lịch trong tương lai?

## 14. Nguyên tắc ghi nhớ

- **`@Temporal` dành cho `java.util.Date` và `java.util.Calendar`**: chọn `DATE`, `TIME` hoặc `TIMESTAMP` theo ngữ nghĩa nghiệp vụ.
- `DATE` mất phần giờ, `TIME` mất phần ngày; `TIMESTAMP` có ngày và giờ nhưng không tự bảo đảm lưu zone ID.
- Khi bind tham số JPQL kiểu `Date`/`Calendar`, có thể dùng overload `setParameter(..., TemporalType.XXX)`.
- Với cột timestamp, tìm theo một ngày bằng khoảng nửa mở xác định từ timezone nghiệp vụ, tránh so sánh một timestamp với một ngày.
- `Date`/`Calendar` mutable; bảo vệ trạng thái entity và đừng đưa object mutable vào so sánh/hashing thiếu kiểm soát.
- **Code mới ưu tiên `java.time`**. `LocalDate`, `LocalTime`, `LocalDateTime` và `Instant` có ý nghĩa khác nhau và không cần `@Temporal`.
- Múi giờ, precision, SQL dialect và JDBC driver là các phần của thiết kế lưu trữ; annotation đơn lẻ không thay thế việc xác định và kiểm soát chúng.

Khi làm việc với ứng dụng JPA cũ, hãy đọc ý nghĩa dữ liệu trước, đối chiếu kiểu cột thật, rồi mới chọn hoặc sửa `@Temporal`. Khi phát triển mới, mô hình hóa bằng kiểu `java.time` đúng với domain để tránh phải dùng một `Date` đa nghĩa cho mọi thông tin thời gian.
