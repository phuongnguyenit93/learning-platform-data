# Ánh xạ ngày giờ theo ngữ nghĩa của kiểu Java và SQL

Trong ứng dụng Java sử dụng Jakarta Persistence (JPA), kiểu dữ liệu ngày giờ không chỉ quyết định định dạng hiển thị. Nó xác định **giá trị mang ý nghĩa gì**, liệu có xác định được một thời điểm duy nhất trên dòng thời gian hay không, và cơ sở dữ liệu phải lưu thông tin nào để đọc lại đúng giá trị đó.

Ví dụ, ngày sinh **15/11/1998**, giờ cửa hàng mở **08:30**, lịch hẹn **09:00 ngày 20/06 tại Hà Nội** và thời điểm giao dịch được ghi nhận **2026-11-15T02:00:00Z** đều liên quan đến thời gian, nhưng không thể mô hình hóa bằng một kiểu Java duy nhất mà vẫn giữ đúng ngữ nghĩa.

Trong JPA, sự lựa chọn thường trải qua ba lớp:

1. **Kiểu Java** biểu diễn điều gì: ngày lịch, giờ trong ngày, ngày giờ địa phương, thời điểm tuyệt đối, offset hay vùng thời gian?
2. **Kiểu cột SQL** lưu điều gì: DATE, TIME, TIMESTAMP, TIMESTAMP WITH TIME ZONE hay định dạng đặc thù?
3. **JPA provider, JDBC driver và DBMS** chuyển đổi giá trị qua ranh giới Java–SQL như thế nào, đặc biệt khi có múi giờ, precision và quy tắc daylight saving time (DST)?

Chọn kiểu theo ngữ nghĩa nghiệp vụ trước, sau đó mới quyết định mapping JPA và schema SQL. Chỉ nhìn tên kiểu dữ liệu rồi chọn cột có tên tương tự thường chưa đủ.

## 1. Phân loại giá trị thời gian theo ngữ nghĩa

| Câu hỏi nghiệp vụ | Giá trị ví dụ | Kiểu Java thường phù hợp | Điều cần bảo toàn |
| --- | --- | --- | --- |
| Ngày sinh hoặc ngày nghỉ lễ là ngày nào? | 1998-11-15 | `LocalDate` | Ngày lịch, không có giờ và múi giờ |
| Cửa hàng mở lúc mấy giờ mỗi ngày? | 08:30 | `LocalTime` | Giờ trên đồng hồ, không gắn ngày |
| Người dùng nhập lịch hẹn theo đồng hồ địa phương? | 2027-04-20 09:00 | `LocalDateTime` | Ngày và giờ địa phương |
| Một sự kiện đã xảy ra chính xác lúc nào? | 2026-11-15T02:00:00Z | `Instant` | Một thời điểm tuyệt đối |
| Thời điểm kèm độ lệch UTC được nhập là gì? | 2026-11-15T09:00:00+07:00 | `OffsetDateTime` | Ngày giờ và offset cụ thể |
| Lịch 09:00 tại một khu vực địa lý nào? | 09:00, Asia/Ho_Chi_Minh | `LocalDateTime` + `ZoneId` | Giờ địa phương và quy tắc múi giờ vùng |
| Khoảng dài chính xác bao lâu? | 90 phút | `Duration` | Độ dài dựa trên giây/nanosecond |
| Kỳ thanh toán bao nhiêu tháng? | 3 tháng | `Period` | Khoảng theo lịch, không cố định số giây |

**Hai nhóm quan trọng nhất:**

- **Local/civil time:** biểu diễn những gì xuất hiện trên lịch và đồng hồ tại một nơi, chưa chắc chỉ ra thời điểm duy nhất trên timeline.
- **Instant/absolute time:** biểu diễn một điểm thời gian duy nhất; có thể chuyển sang nhiều múi giờ để hiển thị mà không thay đổi sự kiện thực tế.

Chẳng hạn, `LocalDateTime.of(2027, 4, 20, 9, 0)` tự nó **không xác định** 09:00 ở Việt Nam, Nhật Bản hay Đức. Ngược lại, `Instant.parse("2027-04-20T02:00:00Z")` chỉ rõ một thời điểm; hiển thị ở Việt Nam là 09:00 nếu quy tắc múi giờ tại thời điểm đó tương ứng UTC+07:00.

## 2. Các kiểu chính trong `java.time`

Từ Java 8, API `java.time` cung cấp các kiểu **bất biến (immutable)**, đặt tên theo ngữ nghĩa và an toàn hơn nhiều cách xử lý cũ dựa trên `java.util.Date`, `Calendar`. Đây thường là lựa chọn ưu tiên cho mã Java mới.

### 2.1. `LocalDate` — chỉ một ngày lịch

~~~java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1998, 11, 15);
LocalDate dueDate = LocalDate.parse("2027-03-31");

System.out.println(birthday);  // 1998-11-15
~~~

`LocalDate` chứa năm, tháng và ngày. Nó **không có giờ, offset hay múi giờ**. Các dữ liệu như ngày sinh, ngày hiệu lực hợp đồng, ngày lập hóa đơn hoặc ngày nghỉ thường thuộc nhóm này.

Không nên chuyển ngày sinh sang `Instant` chỉ để lưu. Khi chọn nửa đêm theo một múi giờ rồi hiển thị lại ở múi giờ khác, ngày có thể dịch sang hôm trước hoặc hôm sau.

### 2.2. `LocalTime` — giờ đồng hồ, không có ngày

~~~java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(8, 30);
LocalTime closingTime = LocalTime.of(21, 0);
~~~

`LocalTime` phù hợp cho giờ mở cửa, giờ bắt đầu ca lặp lại hằng ngày hoặc một quy tắc dạng “đến 17:00 mỗi ngày”. Nó không đủ để xác định một thời điểm tuyệt đối vì thiếu ngày và vùng thời gian.

Với giờ cửa hàng ở địa điểm cụ thể, ứng dụng có thể cần lưu thêm `ZoneId` của cửa hàng và quy tắc ngày áp dụng để tính thành thời điểm cụ thể.

### 2.3. `LocalDateTime` — ngày giờ trên đồng hồ địa phương

~~~java
import java.time.LocalDateTime;

LocalDateTime appointment =
        LocalDateTime.of(2027, 4, 20, 9, 0);
~~~

`LocalDateTime` chứa năm, tháng, ngày, giờ, phút và phần giây nhưng **không chứa offset hoặc vùng thời gian**. Vì vậy nó phù hợp với lịch hẹn địa phương, nội dung lịch do người dùng nhập hoặc dữ liệu của hệ thống cũ vốn định nghĩa thời gian theo “giờ tại chỗ”.

Không nên xem mọi `LocalDateTime` là UTC. Cách hiểu “cứ lưu `LocalDateTime` rồi mặc định đó là UTC” chỉ là **quy ước ngoài kiểu dữ liệu**; nếu không được thực thi nhất quán, rất dễ gây lỗi khi triển khai nhiều máy chủ và nhiều vùng.

### 2.4. `Instant` — thời điểm trên dòng thời gian

~~~java
import java.time.Instant;

Instant createdAt = Instant.now();
Instant eventAt = Instant.parse("2026-11-15T02:00:00Z");
~~~

`Instant` biểu diễn một thời điểm tuyệt đối bằng số giây/nanosecond tính từ epoch. Nó không tự mang múi giờ hiển thị, nhưng có thể được biểu diễn thành ngày giờ ở một vùng:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime localView =
        eventAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đối với `createdAt`, `updatedAt`, thời điểm giao dịch hoặc dấu mốc hệ thống, `Instant` thường diễn đạt mục đích tốt nhất. Tuy nhiên, **khả năng ánh xạ trực tiếp `Instant`** và SQL type cụ thể cần được xác nhận theo phiên bản Jakarta Persistence, provider và DBMS mà dự án sử dụng; không nên mặc định mọi thế hệ JPA đều xử lý giống nhau.

### 2.5. `OffsetDateTime` và `OffsetTime` — chứa độ lệch UTC

~~~java
import java.time.OffsetDateTime;
import java.time.OffsetTime;

OffsetDateTime paidAt =
        OffsetDateTime.parse("2026-11-15T09:00:00+07:00");

OffsetTime callTime = OffsetTime.parse("09:00:00+07:00");
~~~

`OffsetDateTime` gồm ngày giờ và **offset cố định so với UTC**, ví dụ `+07:00` hoặc `-05:00`. Do có ngày và offset, nó xác định được một `Instant`:

~~~java
Instant sameInstant = paidAt.toInstant();
// 2026-11-15T02:00:00Z
~~~

`OffsetTime` có giờ và offset nhưng không có ngày. Nó không đủ để xác định một `Instant`, đồng thời không biểu diễn đầy đủ quy tắc DST của một vùng địa lý. Kiểu `TIME WITH TIME ZONE` cũng không được hỗ trợ đồng nhất giữa các DBMS, vì vậy cần cân nhắc tính di động trước khi sử dụng nó để ánh xạ.

### 2.6. `ZonedDateTime` và `ZoneId` — quy tắc của một vùng

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Europe/Berlin");
ZonedDateTime meeting = ZonedDateTime.of(
        2027, 1, 15, 10, 0, 0, 0, zone);
~~~

`ZoneId` như `Europe/Berlin` hoặc `Asia/Ho_Chi_Minh` chỉ đến **hệ thống quy tắc lịch sử và tương lai** về offset và DST. Ngược lại, `+01:00` chỉ là offset, không diễn tả khi nào vùng sẽ đổi sang `+02:00`.

Một cột SQL tên `TIMESTAMP WITH TIME ZONE` **không tự bảo đảm lưu lại ZoneId gốc**. Nhiều DBMS chuẩn hóa dữ liệu theo thời điểm tuyệt đối hoặc lưu offset theo cơ chế riêng. Nếu cần biết người dùng đã chọn vùng nào để tổ chức lịch tương lai, hãy lưu **mã ZoneId IANA trong cột riêng**.

## 3. Kiểu SQL: tên gần giống nhưng ngữ nghĩa không hoàn toàn giống

Các kiểu SQL phổ biến:

| Kiểu cột SQL | Giá trị muốn biểu diễn | Kiểu Java gợi ý | Cảnh báo |
| --- | --- | --- | --- |
| `DATE` | Ngày lịch | `LocalDate` | Không gắn giờ/múi giờ |
| `TIME [WITHOUT TIME ZONE]` | Giờ trong ngày | `LocalTime` | Không chỉ ra một thời điểm |
| `TIMESTAMP [WITHOUT TIME ZONE]` | Ngày giờ địa phương | `LocalDateTime` | Không có đủ thông tin để xác định UTC |
| `TIMESTAMP WITH TIME ZONE` | Ngày giờ có thông tin thời điểm/offset theo DBMS | `OffsetDateTime` hoặc `Instant` nếu provider hỗ trợ | DBMS có thể chuẩn hóa và không lưu offset/ZoneId ban đầu |
| `TIME WITH TIME ZONE` | Giờ và offset | `OffsetTime` nếu stack hỗ trợ | Tính di động hạn chế, không có quy tắc vùng theo ngày |
| `BIGINT` lưu epoch | Số giây/millisecond/nanosecond theo quy ước ứng dụng | `Instant` qua converter | Phải thống nhất đơn vị và precision; DB không tự hiểu đó là ngày giờ |
| `VARCHAR` lưu ZoneId | Tên vùng như `Asia/Ho_Chi_Minh` | `String` hoặc `ZoneId` qua converter | Cần kiểm tra mã vùng; không tương đương với offset |

Những ánh xạ trên phản ánh **ý nghĩa thiết kế**, không phải bảo đảm provider luôn chọn đúng SQL type một cách tự động. Mapping mặc định, dialect, phiên bản Jakarta Persistence, JDBC driver và khả năng DBMS đều ảnh hưởng đến loại cột thực tế.

### Đặc biệt: TIMESTAMP không nói lên “UTC” hay “local” nếu thiếu ngữ cảnh

Ví dụ hai chuỗi:

~~~text
2026-11-15 09:00:00
2026-11-15T09:00:00+07:00
~~~

Chuỗi đầu tiên chỉ có ngày giờ. Chuỗi thứ hai xác định một instant là `2026-11-15T02:00:00Z`. Nếu cột chỉ giữ `2026-11-15 09:00:00`, chương trình không thể tự suy ra offset `+07:00` khi đọc lại.

Ngược lại, một cột timestamp có timezone có thể giữ **cùng thời điểm tuyệt đối** nhưng trả giá trị hiển thị ở múi giờ session của database. Vì thế, hiển thị khác không nhất thiết nghĩa là lưu sai; phải so sánh theo instant khi kiểm tra dữ liệu thời điểm.

## 4. Sự khác nhau giữa các hệ quản trị cơ sở dữ liệu

Không nên coi các tên kiểu SQL là hoàn toàn tương đương trên mọi database.

### PostgreSQL

PostgreSQL có hai kiểu đặc biệt dễ nhầm:

- `timestamp without time zone`: giữ các thành phần ngày giờ; không tự ghi một múi giờ.
- `timestamp with time zone` (bí danh `timestamptz`): xử lý một điểm thời gian và hiển thị theo timezone session; **không giữ tên vùng IANA hoặc offset gốc như dữ liệu riêng**.

Ví dụ hai biểu diễn dưới đây chỉ cùng một instant:

~~~text
2026-11-15T09:00:00+07:00
2026-11-15T02:00:00Z
~~~

Nếu lưu vào `timestamptz`, chúng tương đương về thời điểm. Không thể yêu cầu cột này tự nhớ người dùng đã nhập `+07:00`.

### MySQL

MySQL có `DATE`, `TIME`, `DATETIME` và `TIMESTAMP`. `DATETIME` phù hợp với ngày giờ không kèm vùng thời gian; kiểu `TIMESTAMP` có cơ chế chuyển đổi theo timezone session khi ghi/đọc. Giới hạn phạm vi giá trị, precision và cách chuyển đổi phụ thuộc phiên bản và cấu hình. Đừng giả định `DATETIME` tương đương `timestamptz` của PostgreSQL.

### SQL Server, Oracle và các hệ khác

SQL Server có `datetimeoffset` có thể lưu offset, trong khi Oracle có các kiểu `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE` với hành vi khác nhau. Một số hệ dùng chuỗi hoặc số để lưu thời gian thay vì kiểu timestamp phong phú. Do vậy, **giữ nguyên local date/time, giữ instant, giữ offset và giữ ZoneId** là bốn yêu cầu cần được đánh giá riêng.

Trong dự án dùng nhiều DBMS hoặc muốn thay database, cần xác định mức tương thích chính xác qua tài liệu dialect, mapping provider và schema migration tương ứng.

## 5. Ví dụ ánh xạ JPA: mỗi thuộc tính có ngữ nghĩa riêng

Giả sử hệ thống đặt lịch dịch vụ lưu:

- Ngày áp dụng giá dịch vụ (ngày lịch).
- Giờ cắt đăng ký hằng ngày theo đồng hồ chi nhánh.
- Ngày giờ bắt đầu mà người dùng nhìn thấy ở địa phương.
- Mã vùng thời gian của chi nhánh.
- Thời điểm bắt đầu thực tế để so sánh, sắp xếp và gửi thông báo.

Một entity có thể được thiết kế như sau:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

@Entity
@Table(name = "service_appointments")
public class ServiceAppointment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Ngày lịch: không gắn timezone.
    @Column(name = "price_effective_date", nullable = false)
    private LocalDate priceEffectiveDate;

    // Giờ lặp lại theo đồng hồ chi nhánh.
    @Column(name = "daily_cutoff", nullable = false)
    private LocalTime dailyCutoff;

    // Ngày giờ tại địa phương mà khách đã chọn.
    @Column(name = "start_local", nullable = false)
    private LocalDateTime startLocal;

    // Vùng địa lý dùng để hiểu startLocal.
    @Column(name = "zone_id", nullable = false, length = 64)
    private String zoneId;

    // Thời điểm để so sánh toàn hệ thống, chuẩn hóa theo UTC.
    @Column(name = "starts_at", nullable = false)
    private OffsetDateTime startsAt;

    protected ServiceAppointment() {
    }

    public ServiceAppointment(
            LocalDate priceEffectiveDate,
            LocalTime dailyCutoff,
            LocalDateTime startLocal,
            String zoneId,
            OffsetDateTime startsAt) {
        this.priceEffectiveDate = priceEffectiveDate;
        this.dailyCutoff = dailyCutoff;
        this.startLocal = startLocal;
        this.zoneId = zoneId;
        this.startsAt = startsAt;
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getStartLocal() {
        return startLocal;
    }

    public String getZoneId() {
        return zoneId;
    }

    public OffsetDateTime getStartsAt() {
        return startsAt;
    }
}
~~~

Tất cả annotation ánh xạ đều đặt trên field, tương ứng với **field access** của JPA do `@Id` nằm trên field. Các field `LocalDate`, `LocalTime`, `LocalDateTime` sử dụng ngữ nghĩa tương ứng. `OffsetDateTime` diễn đạt instant kèm offset; chương trình chọn offset UTC để thống nhất cách ghi.

Ví dụ DDL trong **PostgreSQL**:

~~~sql
CREATE TABLE service_appointments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    price_effective_date DATE NOT NULL,
    daily_cutoff TIME WITHOUT TIME ZONE NOT NULL,
    start_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    zone_id VARCHAR(64) NOT NULL,
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_service_appointments_starts_at
    ON service_appointments(starts_at);
~~~

**DDL là một phần của quyết định thiết kế.** Chỉ viết `@Column(name = "starts_at")` chưa đảm bảo provider tự tạo đúng cột `TIMESTAMP WITH TIME ZONE` trên mọi DBMS. Dự án nên quản lý schema bằng migration và kiểm tra mapping/dialect thực tế. Nếu provider không hỗ trợ ánh xạ `OffsetDateTime` theo cách mong muốn, cần cấu hình hoặc converter thích hợp với stack đang sử dụng.

### Tạo lịch hẹn với chuyển đổi có kiểm soát

Đối với một thời điểm địa phương, cần vùng thời gian để xác định instant:

~~~java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

ZoneId branchZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime localStart =
        LocalDateTime.of(2027, 4, 20, 9, 0);

List<ZoneOffset> validOffsets =
        branchZone.getRules().getValidOffsets(localStart);

if (validOffsets.size() != 1) {
    throw new IllegalArgumentException(
            "Giờ địa phương không hợp lệ hoặc bị trùng do DST");
}

OffsetDateTime startAtUtc = OffsetDateTime
        .of(localStart, validOffsets.get(0))
        .withOffsetSameInstant(ZoneOffset.UTC);

System.out.println(startAtUtc);
// 2027-04-20T02:00Z (với quy tắc Asia/Ho_Chi_Minh hiện hành)
~~~

Với địa điểm không thay đổi offset trong khoảng ví dụ, kết quả rất trực tiếp. Nhưng cách viết kiểm tra `validOffsets` còn hữu ích khi sản phẩm mở rộng sang vùng có DST. Nếu danh sách có 0 phần tử, giờ địa phương nằm trong khoảng bị bỏ qua khi đồng hồ chuyển tới. Nếu có 2 offset, giờ địa phương xuất hiện hai lần khi đồng hồ quay lùi. Ứng dụng phải có chính sách rõ ràng cho những trường hợp đó.

Không nên dùng `ZoneId.systemDefault()` để ngầm đoán múi giờ của khách hàng hoặc địa điểm, vì timezone của máy chủ có thể thay đổi giữa môi trường phát triển, container và production.

## 6. Ngữ nghĩa timezone: offset khác vùng thời gian

Giả sử một cửa hàng ở vùng có DST cung cấp lịch 09:00 hằng ngày. Trong mùa đông offset có thể là `+01:00`, còn mùa hè là `+02:00`.

Nếu chỉ lưu:

~~~text
09:00 +01:00
~~~

thì ứng dụng không biết khi nào phải đổi sang `+02:00`. Cần lưu thông tin vùng, ví dụ:

~~~text
local_time = 09:00
zone_id    = Europe/Berlin
~~~

Khi tính phiên giao dịch ở một ngày cụ thể, kết hợp `LocalDate`, `LocalTime` và `ZoneId` để xác định offset đúng theo ngày:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDate serviceDate = LocalDate.of(2027, 7, 10);
LocalTime localTime = LocalTime.of(9, 0);
ZoneId zone = ZoneId.of("Europe/Berlin");

ZonedDateTime scheduled =
        ZonedDateTime.of(serviceDate, localTime, zone);

System.out.println(scheduled.toInstant());
~~~

Một dữ liệu có thể cần giữ **cả hai dạng**:

- `start_local` + `zone_id` để bảo toàn ý định “09:00 theo giờ địa phương tại Berlin”.
- `starts_at` (instant) để sắp xếp công việc, kích hoạt thông báo hoặc so sánh các sự kiện từ nhiều vùng.

Lưu cả hai làm phát sinh yêu cầu **đồng bộ bất biến**: khi người dùng đổi thời gian hoặc vùng, phải tính lại instant. Đồng thời, nếu chính quyền thay đổi quy tắc múi giờ trong tương lai và dữ liệu lịch hẹn còn xa, ứng dụng phải quyết định có tính lại instant theo quy tắc mới hay giữ nguyên thời điểm đã chốt. Đây là **quy tắc nghiệp vụ**, không phải thứ JPA có thể tự quyết định.

## 7. DST: giờ không tồn tại và giờ xuất hiện hai lần

Ở vùng có daylight saving time, đồng hồ có thể nhảy từ 01:59 lên 03:00 hoặc quay từ 02:59 về 02:00. Khi đó:

- **Gap:** thời gian 02:30 tại địa phương có thể hoàn toàn không tồn tại.
- **Overlap:** thời gian 02:30 có thể xảy ra hai lần với hai offset khác nhau.

Do vậy, chuyển `LocalDateTime` sang `Instant` không phải một phép toán luôn xác định duy nhất nếu chỉ có vùng IANA. Đoạn sau diễn đạt chính sách **chỉ chấp nhận thời điểm không mơ hồ**:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public static Instant resolveUnambiguous(
        LocalDateTime local,
        ZoneId zone) {
    List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(local);

    if (offsets.isEmpty()) {
        throw new IllegalArgumentException(
                "Thời gian không tồn tại trong vùng đã chọn");
    }
    if (offsets.size() > 1) {
        throw new IllegalArgumentException(
                "Thời gian bị trùng: cần chọn offset rõ ràng");
    }
    return local.toInstant(offsets.get(0));
}
~~~

Nếu nghiệp vụ muốn tự đẩy giờ trong gap tới thời điểm hợp lệ hoặc ưu tiên offset sớm/muộn trong overlap, phải ghi rõ chính sách và truyền đạt cho người dùng. Phương thức `LocalDateTime.atZone(zone)` có chính sách giải quyết gap/overlap riêng; dùng nó mà không hiểu quy tắc có thể tạo lịch khác với thời gian người dùng dự kiến.

**Một ngày lịch không phải lúc nào cũng có đúng 24 giờ theo instant.** Ngày tại vùng có DST có thể có 23 hoặc 25 giờ. Điều đó ảnh hưởng đến truy vấn báo cáo “trong ngày” và phép cộng ngày.

## 8. Lọc sự kiện theo ngày địa phương

Giả sử bảng lưu thời điểm tuyệt đối trong `starts_at` nhưng người dùng muốn xem mọi lịch hẹn của **ngày 20/04/2027 theo giờ địa phương của chi nhánh**.

Không nên chuyển sang UTC rồi luôn cộng 24 giờ. Hãy xác định **đầu ngày này và đầu ngày kế tiếp trong cùng vùng thời gian**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate selectedDate = LocalDate.of(2027, 4, 20);
ZoneId branchZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant fromInclusive =
        selectedDate.atStartOfDay(branchZone).toInstant();

Instant toExclusive =
        selectedDate.plusDays(1)
                .atStartOfDay(branchZone)
                .toInstant();
~~~

Sử dụng điều kiện khoảng **đóng đầu, mở cuối**:

~~~sql
SELECT *
FROM service_appointments
WHERE starts_at >= :from_inclusive
  AND starts_at <  :to_exclusive
ORDER BY starts_at;
~~~

Trong JPQL, nếu entity lưu instant dưới dạng `OffsetDateTime`, có thể tạo biên theo cùng kiểu:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;

OffsetDateTime from = fromInclusive.atOffset(ZoneOffset.UTC);
OffsetDateTime to = toExclusive.atOffset(ZoneOffset.UTC);

List<ServiceAppointment> items = em.createQuery(
        "SELECT a FROM ServiceAppointment a "
      + "WHERE a.startsAt >= :from AND a.startsAt < :to "
      + "ORDER BY a.startsAt",
        ServiceAppointment.class)
    .setParameter("from", from)
    .setParameter("to", to)
    .getResultList();
~~~

Cách truy vấn này tránh phụ thuộc vào số chữ số phần giây cuối ngày và dễ tận dụng index trên `starts_at`. Nó cũng xử lý đúng những ngày có DST khác 24 giờ nếu biên ngày được tính theo `ZoneId` trước khi chuyển sang instant.

Truy vấn kiểu `DATE(starts_at) = ...` có thể khiến database phải chuyển đổi từng hàng hoặc khó tận dụng index thường. Khi cần quy tắc ngày địa phương, hãy xác định rõ vùng và truy vấn bằng khoảng giá trị thời điểm.

## 9. Legacy mapping: `java.util.Date`, `Calendar` và `@Temporal`

Các dự án JPA cũ thường sử dụng `java.util.Date` hoặc `java.util.Calendar`. Trong mã cũ, annotation `@Temporal` được dùng để chỉ mục đích ánh xạ SQL:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Temporal;
import jakarta.persistence.TemporalType;
import java.util.Date;

@Entity
public class LegacyRecord {
    @Id
    private Long id;

    @Temporal(TemporalType.DATE)
    @Column(name = "business_date")
    private Date businessDate;

    @Temporal(TemporalType.TIME)
    @Column(name = "cutoff_time")
    private Date cutoffTime;

    @Temporal(TemporalType.TIMESTAMP)
    @Column(name = "created_at")
    private Date createdAt;

    protected LegacyRecord() {
    }
}
~~~

Ý nghĩa các giá trị:

| `TemporalType` | Loại thời gian muốn ánh xạ | Kiểu SQL tương ứng thường gặp |
| --- | --- | --- |
| `DATE` | Phần ngày | `DATE` |
| `TIME` | Phần giờ | `TIME` |
| `TIMESTAMP` | Ngày và giờ | `TIMESTAMP` |

`java.util.Date` về bản chất biểu diễn thời điểm theo epoch, nhưng khi dùng `@Temporal(DATE)` hoặc `@Temporal(TIME)` chỉ có một phần thông tin được biểu diễn ở cột. Việc chuyển đổi có thể chịu ảnh hưởng múi giờ và JDBC, làm loại dữ liệu cũ dễ gây nhầm lẫn hơn với `LocalDate` / `LocalTime`.

**Không áp dụng `@Temporal` cho `LocalDate`, `LocalTime`, `LocalDateTime` hoặc `OffsetDateTime`.** Các kiểu `java.time` đã mang ngữ nghĩa thời gian trong chính tên và cấu trúc của chúng; việc ánh xạ do JPA/provider hỗ trợ theo loại dữ liệu tương ứng. Dùng `@Temporal` với `java.time` là sai mục đích và có thể bị provider từ chối.

Những lớp như `java.sql.Date`, `java.sql.Time` và `java.sql.Timestamp` vẫn có thể xuất hiện trong JDBC hoặc dự án cũ. Với code JPA mới, thông thường nên ưu tiên `java.time` và chỉ chuyển sang legacy type tại biên tích hợp khi thật sự cần.

## 10. Chuyển đổi giữa `java.time` và các kiểu SQL

### 10.1. Chuyển `LocalDateTime` sang `Instant` cần một quy tắc timezone

Sai về ngữ nghĩa khi không có thông tin vùng:

~~~java
LocalDateTime local = LocalDateTime.of(2027, 4, 20, 9, 0);
// Chưa thể xác định duy nhất Instant chỉ từ local.
~~~

Đúng khi có `ZoneId` và chính sách giải quyết DST:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(zone).toInstant();
~~~

Đoạn thứ hai phù hợp với dữ liệu địa điểm trong vùng không có tình huống DST gây mơ hồ tại thời điểm đã chọn; với các vùng có DST, cần cân nhắc chính sách được giải thích ở mục 7.

### 10.2. Chuyển `Instant` sang giờ hiển thị phải nêu vùng

~~~java
Instant eventAt = Instant.parse("2026-11-15T02:00:00Z");

LocalDateTime inVietnam = LocalDateTime.ofInstant(
        eventAt, ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime inTokyo = LocalDateTime.ofInstant(
        eventAt, ZoneId.of("Asia/Tokyo"));
~~~

Hai giá trị `LocalDateTime` có thể khác nhau nhưng đều biểu diễn cách hiển thị của **cùng một sự kiện**. Không nên ghi đè instant bằng local time rồi quên vùng hiển thị.

### 10.3. Tránh ép kiểu ngầm qua timezone của máy chủ

Một số đoạn mã cũ dùng `Timestamp.valueOf(localDateTime)`, `Date.from(instant)` hoặc chuyển qua `Calendar`. Mỗi phép chuyển có giả định và cách diễn giải riêng, đặc biệt ở vùng biên Java/JDBC. Khi chuyển dữ liệu thời gian:

1. Xác định giá trị có chứa instant hay không.
2. Chọn vùng thời gian rõ ràng nếu phải dịch giữa local và instant.
3. Tránh lấy múi giờ mặc định của JVM làm quy tắc nghiệp vụ vô hình.
4. Bảo đảm binder/reader JDBC và provider dùng quy tắc tương thích.

## 11. Lưu ZoneId bằng `AttributeConverter`

Vùng IANA cần được lưu như dữ liệu nghiệp vụ khi lịch phải gắn với địa điểm. Cách đơn giản và dễ di chuyển giữa các DBMS là dùng cột `VARCHAR` cho chuỗi như `Asia/Ho_Chi_Minh`.

Có thể khai báo entity field kiểu `String` và tạo `ZoneId` khi dùng. Nếu muốn domain model sử dụng `ZoneId` trực tiếp, định nghĩa converter:

~~~java
package com.example.persistence;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.time.ZoneId;

@Converter
public class ZoneIdConverter
        implements AttributeConverter<ZoneId, String> {

    @Override
    public String convertToDatabaseColumn(ZoneId zone) {
        return zone == null ? null : zone.getId();
    }

    @Override
    public ZoneId convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : ZoneId.of(dbValue);
    }
}
~~~

Sử dụng trong entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.ZoneId;

@Entity
public class Branch {
    @Id
    private Long id;

    @Convert(converter = ZoneIdConverter.class)
    @Column(name = "zone_id", nullable = false, length = 64)
    private ZoneId zoneId;

    protected Branch() {
    }
}
~~~

Converter thay đổi **biểu diễn khi ghi/đọc cột**, không biến cột VARCHAR thành kiểu timezone của DBMS và không tự kiểm tra yêu cầu nghiệp vụ về địa điểm. Nếu cần giữ chính xác offset người dùng nhập, hãy lưu thông tin đó **tách biệt** với ZoneId, vì nhiều chuỗi offset hoặc vùng có thể quy về cùng một instant.

### Trường hợp cần lưu Instant dưới dạng số

Một số hệ thống không dùng cột timestamp cho thời điểm tuyệt đối, mà lưu epoch milliseconds trong `BIGINT`. Có thể triển khai converter cho `Instant`:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.time.Instant;

@Converter
public class InstantEpochMillisConverter
        implements AttributeConverter<Instant, Long> {

    @Override
    public Long convertToDatabaseColumn(Instant instant) {
        return instant == null ? null : instant.toEpochMilli();
    }

    @Override
    public Instant convertToEntityAttribute(Long value) {
        return value == null ? null : Instant.ofEpochMilli(value);
    }
}
~~~

Áp dụng tường minh bằng `@Convert(converter = InstantEpochMillisConverter.class)` trên field cần chuyển. Đây là **một quyết định kiến trúc cụ thể**, có đánh đổi:

- Dễ biểu diễn instant độc lập timezone.
- Cần thống nhất đơn vị milliseconds; không được lẫn với seconds.
- Mất precision nhỏ hơn millisecond; giá trị `Instant` có nanoseconds có thể không round-trip nguyên vẹn.
- Các hàm thời gian SQL và khả năng hiển thị/kiểm tra cột trở nên kém tự nhiên hơn so với timestamp native.
- Các giá trị epoch trong cột BIGINT không tự mang ngữ nghĩa timezone hay định dạng.

Nếu database có kiểu timestamp phù hợp và provider hỗ trợ nhất quán, sử dụng kiểu native thường dễ vận hành hơn.

## 12. Precision: Java nanosecond, SQL có thể chỉ microsecond

Nhiều lớp `java.time` có phần nanosecond (9 chữ số), nhưng cột SQL và driver có thể hỗ trợ độ chính xác thấp hơn:

~~~java
import java.time.Instant;

Instant value =
        Instant.parse("2026-11-15T02:00:00.123456789Z");
~~~

Nếu database lưu tối đa microsecond, giá trị đọc lại có thể chỉ tương đương `.123456` hoặc được làm tròn theo chính sách của DBMS. **Không thể mặc định toàn bộ chín chữ số được giữ nguyên**.

Ví dụ PostgreSQL cho phép lựa chọn precision của timestamp:

~~~sql
CREATE TABLE processing_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
~~~

`TIMESTAMP(6)` diễn đạt precision phần giây đến microsecond; mapping Java phải chấp nhận giới hạn này. Nếu use case đòi hỏi độ chính xác thực sự đến nanosecond, cần kiểm tra khả năng DBMS hoặc mô hình lưu khác.

Tránh so sánh timestamp vừa ghi và đọc lại bằng phép bằng tuyệt đối nếu đường lưu trữ có thể thay đổi precision. Với thời điểm được dùng làm khóa nghiệp vụ, điều kiện unique hoặc mốc phân trang, chọn precision thống nhất ngay từ schema và tầng ứng dụng.

## 13. Kiểu dữ liệu ngày giờ và truy vấn JPQL

JPA cho phép dùng field thời gian trong truy vấn theo entity. Giả sử `ServiceAppointment.startsAt` là `OffsetDateTime`:

~~~java
OffsetDateTime begin =
        OffsetDateTime.parse("2026-11-15T00:00:00Z");
OffsetDateTime end =
        OffsetDateTime.parse("2026-11-16T00:00:00Z");

List<ServiceAppointment> result = em.createQuery(
        "SELECT a FROM ServiceAppointment a "
      + "WHERE a.startsAt >= :begin AND a.startsAt < :end",
        ServiceAppointment.class)
    .setParameter("begin", begin)
    .setParameter("end", end)
    .getResultList();
~~~

Trong ví dụ này, `begin` và `end` là **instant boundary theo UTC**. Nếu mục tiêu thật sự là một ngày theo vùng giờ địa phương, cần tính lại biên theo vùng như mục 8.

Với ngày hiệu lực không chứa giờ, dùng `LocalDate`:

~~~java
LocalDate targetDay = LocalDate.of(2027, 1, 1);

List<ServiceAppointment> matches = em.createQuery(
        "SELECT a FROM ServiceAppointment a "
      + "WHERE a.priceEffectiveDate = :day",
        ServiceAppointment.class)
    .setParameter("day", targetDay)
    .getResultList();
~~~

Không cần tự ghép chuỗi ISO vào JPQL. Sử dụng tham số được bind để provider/driver áp dụng kiểu dữ liệu phù hợp, tránh xử lý chuỗi ngày giờ thủ công và sai lệch do định dạng.

### So sánh theo ngày khi cột lưu timestamp

Nếu cột lưu instant, không nên chỉ lấy phần ngày sau khi đổi sang timezone mặc định của database rồi so sánh với ngày mà người dùng chọn. Hai phía có thể đang dùng hai vùng khác nhau.

Giải pháp dễ hiểu là quy đổi ngày đích thành khoảng hai instant rồi sử dụng phép so sánh. Cách này cũng tránh phụ thuộc vào những hàm SQL ngày giờ khác nhau giữa các hệ quản trị.

## 14. Ai là nguồn thời gian: JVM hay DBMS?

Có ít nhất hai cách gán thời điểm tạo bản ghi:

~~~java
Instant createdAt = Instant.now();   // Đồng hồ JVM.
~~~

hoặc:

~~~sql
created_at TIMESTAMP WITH TIME ZONE
    DEFAULT CURRENT_TIMESTAMP
~~~

Cách thứ nhất lấy thời gian theo đồng hồ máy chạy ứng dụng; cách thứ hai lấy theo ngữ nghĩa hàm thời gian của DBMS. Chúng có thể khác nhau vì:

- Độ lệch hoặc đồng bộ đồng hồ hệ thống.
- Thời điểm gọi trong transaction.
- Độ chính xác và quy tắc làm tròn.
- Ngữ nghĩa của hàm DBMS như CURRENT_TIMESTAMP so với thời gian thực tại từng câu lệnh.

Ứng dụng cần chọn rõ nguồn thời gian cho từng use case. Với audit và ordering, nên đồng bộ đồng hồ hạ tầng và hiểu điều gì là **thời điểm yêu cầu**, **thời điểm ghi** và **thời điểm commit**. JPA không thể bảo đảm các giá trị đó luôn trùng nhau.

Một annotation hoặc callback JPA để điền thời gian, ví dụ `@PrePersist`, chỉ kích hoạt theo vòng đời entity tương ứng; nó không phải bằng chứng về thời gian commit chính xác. Trigger và default ở database cũng phải được tính đến nếu dữ liệu có thể được ghi ngoài ứng dụng JPA.

## 15. Khi nào phải lưu cả local time, instant và timezone?

Không phải lúc nào cũng cần ba giá trị. Hãy nhìn vào cam kết nghiệp vụ:

| Bài toán | Nên lưu chính | Có cần vùng thời gian? |
| --- | --- | --- |
| Ngày sinh | `LocalDate` / `DATE` | Không |
| Giờ mở cửa cố định mỗi ngày tại cửa hàng | `LocalTime` / `TIME` | Có nếu phải tính thời điểm thực tế trên nhiều vùng |
| Ngày giờ khách đặt lịch tại chi nhánh | `LocalDateTime` + mã `ZoneId` | Có |
| Timestamp tạo bản ghi để audit | `Instant` hoặc `OffsetDateTime` chuẩn hóa UTC | Không cần lưu ZoneId gốc nếu chỉ quan tâm instant |
| Thời điểm giao dịch có yêu cầu lưu offset nhập gốc | Instant và offset gốc ở cột riêng, hoặc mô hình được DBMS hỗ trợ có kiểm chứng | Có thể cần cả offset lẫn instant |
| Cuộc họp 09:00 hằng tuần theo giờ vùng | Quy tắc lặp, local time, ZoneId | Có; tính từng occurrence theo lịch |
| Hạn thanh toán “cuối ngày tại chi nhánh” | `LocalDate` + `ZoneId`; quy tắc chốt ngày | Có để tính instant hết hạn |

**Lịch tương lai** đặc biệt nhạy cảm với thay đổi quy tắc múi giờ. Nếu chỉ giữ instant đã tính ở thời điểm đặt lịch, một thay đổi luật DST sau này có thể khiến giờ hiển thị không còn là 09:00 địa phương. Nếu chỉ giữ local time mà không lưu ZoneId, ứng dụng không thể tái dựng instant ổn định. Mô hình đúng phải xuất phát từ yêu cầu: **giữ chính xác thời điểm hay giữ chính xác giờ trên đồng hồ tại vùng?**

## 16. Những lỗi ánh xạ thường gặp

### Lỗi 1: dùng `LocalDateTime` cho timestamp audit nhưng tưởng rằng đó là UTC

`LocalDateTime` không có dấu hiệu UTC. Nếu các instance ứng dụng đặt timezone khác nhau hoặc cấu hình JDBC khác nhau, việc chuyển đổi có thể không đồng nhất.

**Hướng xử lý:** dùng `Instant` hoặc `OffsetDateTime` theo khả năng provider/DBMS, chuẩn hóa UTC ở ranh giới hệ thống và định nghĩa SQL type phù hợp.

### Lỗi 2: dùng `Instant` cho sinh nhật

Ngày sinh là giá trị lịch, không phải một khoảnh khắc. Cùng instant có thể xuất hiện ở hai ngày khác nhau tùy múi giờ.

**Hướng xử lý:** `LocalDate` và cột `DATE`.

### Lỗi 3: tin rằng `TIMESTAMP WITH TIME ZONE` tự lưu tên vùng người dùng

Ở một số DBMS, giá trị được chuẩn hóa thành instant; ZoneId và offset nhập ban đầu có thể không còn.

**Hướng xử lý:** lưu `ZoneId` hoặc offset gốc ở cột riêng khi nghiệp vụ cần.

### Lỗi 4: dùng timezone của máy chủ để chuyển lịch hẹn

Môi trường chạy ứng dụng có thể ở UTC còn khách hàng ở Việt Nam. Lịch 09:00 có thể biến thành 16:00 hoặc một giá trị khác ngoài ý muốn.

**Hướng xử lý:** truyền `ZoneId` theo chi nhánh/người dùng, không phụ thuộc `systemDefault`.

### Lỗi 5: cộng 24 giờ để tìm cuối ngày địa phương

Ngày có DST có thể có 23 hoặc 25 giờ. Khi lọc một ngày, phép cộng 24 giờ có thể bỏ sót hoặc lấy thừa sự kiện.

**Hướng xử lý:** tính đầu ngày và đầu ngày kế tiếp theo cùng vùng.

### Lỗi 6: sử dụng `@Temporal` trên kiểu `java.time`

`@Temporal` thuộc mô hình legacy Date/Calendar, không phải cách chọn DATE/TIME/TIMESTAMP cho LocalDate/LocalTime/LocalDateTime.

**Hướng xử lý:** dùng kiểu `java.time` đúng ngữ nghĩa và kiểm tra mapping JPA/provider.

### Lỗi 7: dùng `@Column(columnDefinition = "...")` như lời bảo đảm portable

`columnDefinition` chứa SQL DDL cụ thể cho database, có thể khác giữa PostgreSQL, MySQL, SQL Server và Oracle.

**Hướng xử lý:** quản lý schema bằng migration theo DBMS, chỉ sử dụng columnDefinition khi chủ đích chấp nhận phụ thuộc dialect.

### Lỗi 8: lưu epoch không khai báo đơn vị

Giá trị `1731655200` có thể là epoch seconds, trong khi `1731655200000` là milliseconds. Nhầm lẫn hai đơn vị tạo lệch rất lớn.

**Hướng xử lý:** đặt tên cột như `created_at_epoch_ms`, tài liệu hóa precision và viết converter thống nhất.

### Lỗi 9: làm tròn precision nhưng vẫn so sánh nanosecond nguyên bản

Lưu xuống timestamp precision 6 rồi đọc lại không nhất thiết giữ được 9 chữ số của Java.

**Hướng xử lý:** thống nhất precision tại API, database và logic so sánh.

### Lỗi 10: cập nhật local time nhưng quên cập nhật instant

Nếu entity có `start_local`, `zone_id` và `starts_at`, thay đổi một giá trị mà không tính lại những giá trị liên quan gây dữ liệu mâu thuẫn.

**Hướng xử lý:** gom cập nhật vào phương thức nghiệp vụ duy nhất và ranh giới transaction rõ ràng; cân nhắc tính một trường dẫn xuất thay vì lưu trùng nếu không cần hiệu năng truy vấn.

## 17. Quy trình thiết kế ánh xạ ngày giờ

Khi thêm một thuộc tính thời gian mới vào entity, có thể đi theo thứ tự:

1. **Viết lại ý nghĩa nghiệp vụ.** Giá trị là ngày lịch, giờ đồng hồ, local timestamp, instant hay lịch lặp?
2. **Xác định chủ thể của múi giờ.** Vùng của người dùng, chi nhánh, tổ chức hay múi giờ hệ thống?
3. **Chọn kiểu Java.** Ưu tiên `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant` hoặc `OffsetDateTime` theo ngữ nghĩa; bổ sung `ZoneId` khi cần.
4. **Chọn cột SQL thực tế.** Quy định rõ DATE/TIME/TIMESTAMP và khả năng WITH TIME ZONE của DBMS; xác định precision.
5. **Kiểm tra hỗ trợ JPA/provider/JDBC.** Phiên bản Jakarta Persistence và dialect khác nhau có thể ánh xạ các kiểu nâng cao không giống nhau.
6. **Thiết kế quy tắc DST và chuyển đổi.** Không cho timezone của máy chủ tự quyết định thay nghiệp vụ.
7. **Quy định cách truy vấn.** Với instant theo ngày địa phương, dùng khoảng đầu ngày/đầu ngày kế tiếp.
8. **Quy định cách hiển thị và truyền qua API.** Sử dụng ISO 8601 và gửi rõ offset hoặc ZoneId khi cần.
9. **Quản lý schema và migration.** Không trông chờ annotation tự sửa mọi cột và ràng buộc.
10. **Định nghĩa tình huống biên.** Các ngày DST, thời gian không tồn tại/bị trùng, precision, đổi timezone session và dữ liệu legacy.

Trong phát triển thực tế, các tình huống biên này nên được phản ánh thành kiểm thử tích hợp với đúng provider và database dự kiến. Bài học hiện tại mô tả nguyên tắc ánh xạ; hành vi chi tiết phải được kiểm chứng ở stack cụ thể.

## 18. Câu hỏi tự luyện

**Câu 1.** Hệ thống quản lý nhân sự lưu ngày sinh của nhân viên. Chọn `Instant` hay `LocalDate`?

**Gợi ý:** ngày sinh là ngày lịch, không phải instant. Chọn `LocalDate` kết hợp cột `DATE`.

**Câu 2.** Một API nhận `2026-11-15T09:00:00+07:00`. Có thể xác định thời điểm UTC không?

**Gợi ý:** có. Ngày giờ kèm offset đủ để chuyển thành `2026-11-15T02:00:00Z`; kiểu `OffsetDateTime` biểu diễn đúng thông tin này.

**Câu 3.** Lịch hẹn hiển thị 09:00 tại Berlin vào một ngày trong tương lai. Chỉ lưu `LocalDateTime` có đủ không?

**Gợi ý:** chưa đủ để xác định instant; cần vùng IANA và quy tắc xử lý gap/overlap khi áp dụng.

**Câu 4.** Một cột PostgreSQL `timestamptz` lưu 09:00+07:00. Khi truy vấn trong session UTC thấy 02:00. Dữ liệu có bị sai không?

**Gợi ý:** hai biểu diễn có thể cùng một instant; `timestamptz` không giữ riêng offset gốc.

**Câu 5.** Vì sao khoảng dữ liệu trong một ngày địa phương nên viết `>= startOfDay` và `< nextStartOfDay`?

**Gợi ý:** không phải tính “cuối ngày” phụ thuộc precision; phạm vi cũng phù hợp những ngày có DST khác 24 giờ.

**Câu 6.** Có nên đặt `@Temporal(TemporalType.TIMESTAMP)` trên `LocalDateTime` không?

**Gợi ý:** không. `@Temporal` dành cho các kiểu legacy Date/Calendar trong JPA, không dành cho `java.time`.

**Câu 7.** Nếu chương trình lưu `Instant` xuống `BIGINT`, cần ghi rõ điều gì?

**Gợi ý:** đơn vị epoch (seconds/milliseconds/...), precision, converter và cách đọc lại ở mọi thành phần.

**Câu 8.** Một đơn hàng được tạo lúc 15:00 theo đồng hồ JVM nhưng database default sinh 15:00:01. Đây có chắc là lỗi JPA?

**Gợi ý:** không. Hai nguồn thời gian được lấy ở những thời điểm khác nhau, có độ lệch đồng hồ và precision/semantics khác nhau; cần quyết định nguồn thời gian và ý nghĩa nghiệp vụ.

## Kết luận

**Ánh xạ ngày giờ đúng bắt đầu từ ngữ nghĩa, sau đó mới đến annotation và tên cột SQL.** `LocalDate` diễn tả ngày lịch, `LocalTime` là giờ đồng hồ, `LocalDateTime` là ngày giờ chưa gắn vùng, `Instant` là thời điểm tuyệt đối, còn `OffsetDateTime` chứa ngày giờ và offset. `ZoneId` chứa quy tắc của vùng địa lý mà một offset cố định không thể thay thế.

JPA và provider kết nối các kiểu Java với dữ liệu SQL, nhưng **DBMS, driver và cấu hình timezone** quyết định nhiều chi tiết quan trọng khi ghi/đọc. Hãy chọn loại cột phù hợp, thống nhất precision, xác định rõ quy tắc UTC và DST, lưu ZoneId khi lịch cần gắn với địa phương, đồng thời tránh dùng cách chuyển đổi ngầm qua timezone máy chủ. Đó là cơ sở để dữ liệu ngày giờ được lưu, truy vấn và hiển thị đúng trong các hệ thống có nhiều người dùng, nhiều vùng thời gian và nhiều môi trường triển khai.
