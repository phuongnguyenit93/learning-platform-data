# Quan hệ giữa `InstantSource`, `Clock` và múi giờ trong Java 17

Java 17 bổ sung interface `java.time.InstantSource` để tách việc **lấy một thời điểm trên dòng thời gian** khỏi việc **diễn giải thời điểm đó theo múi giờ**. Lớp `java.time.Clock` triển khai `InstantSource` và bổ sung thông tin múi giờ. Hai API này liên hệ chặt chẽ nhưng có trách nhiệm khác nhau.

Có thể nhớ bằng ba ý:

- **`Instant`** biểu diễn một thời điểm tuyệt đối trên dòng thời gian, độc lập với múi giờ.
- **`InstantSource`** cung cấp `Instant` hiện tại theo một nguồn có thể thay thế hoặc kiểm soát được, rất hữu ích khi kiểm thử.
- **`Clock`** là một `InstantSource` có thêm `ZoneId` để các API ngày giờ tạo ra kết quả theo múi giờ được chọn.

Múi giờ không làm thay đổi một `Instant`. Nó chỉ quyết định ngày và giờ địa phương tương ứng với thời điểm đó. Nắm rõ quan hệ này giúp tránh lỗi khi chạy ứng dụng trên server ở múi giờ khác, viết kiểm thử thời gian ổn định và xử lý ngày giờ có daylight saving time (DST).

> **Phiên bản:** `InstantSource` được thêm trong Java 17. Các ví dụ dưới đây dùng API chuẩn của Java 17, không cần preview feature.

## 1. Bắt đầu từ ba khái niệm thời gian khác nhau

Trước khi so sánh hai API, cần phân biệt thời điểm tuyệt đối, ngày giờ địa phương và múi giờ.

### 1.1. `Instant` — thời điểm trên dòng thời gian

`Instant` biểu diễn một điểm trên timeline, được tính tương đối với epoch `1970-01-01T00:00:00Z`. Hậu tố `Z` nghĩa là UTC.

```java
import java.time.Instant;

Instant moment = Instant.parse("2025-03-08T10:15:30Z");

System.out.println(moment);
```

Kết quả:

```text
2025-03-08T10:15:30Z
```

`Instant` không chứa múi giờ như `Asia/Ho_Chi_Minh` hay `Europe/Paris`. Nó cũng không phải “giờ của máy tính”. Nó là một thời điểm xác định, có thể được biểu diễn ở nhiều múi giờ khác nhau.

### 1.2. `LocalDateTime` — ngày giờ trên đồng hồ địa phương

`LocalDateTime` chứa ngày và giờ như `2025-03-08T17:15:30`, nhưng **không chứa múi giờ và không xác định được một Instant duy nhất**.

```java
import java.time.LocalDateTime;

LocalDateTime local = LocalDateTime.of(2025, 3, 8, 17, 15, 30);

System.out.println(local);
```

Kết quả:

```text
2025-03-08T17:15:30
```

Nếu không biết địa điểm/múi giờ, ta không thể kết luận giờ địa phương này tương ứng với thời điểm UTC nào. Ở những nơi có DST, một giờ địa phương thậm chí có thể xuất hiện hai lần hoặc không tồn tại vào ngày chuyển đổi.

### 1.3. `ZoneId` — quy tắc múi giờ dùng để chuyển đổi

`ZoneId` xác định quy tắc chuyển đổi giữa `Instant` và ngày giờ địa phương. Ví dụ:

```java
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId utc = ZoneOffset.UTC;
```

Hai nhóm zone phổ biến:

| Nhóm | Ví dụ | Đặc điểm |
|---|---|---|
| Múi giờ theo vùng địa lý | `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York` | Có bộ quy tắc lịch sử và quy tắc thay đổi offset theo thời điểm; có thể áp dụng DST |
| Offset cố định | `UTC`, `+07:00`, `-05:00` | Độ lệch với UTC cố định, không tự thay đổi theo mùa |

`ZoneId` kiểu vùng địa lý dựa trên dữ liệu múi giờ của nền tảng (IANA Time Zone Database/TZDB). Quy tắc có thể được cập nhật khi chính phủ thay đổi giờ pháp định.

`ZoneOffset` là một dạng `ZoneId` mô tả độ lệch cố định so với UTC. Ví dụ `ZoneOffset.of("+07:00")` luôn có offset `+07:00`; nó không đại diện đầy đủ quy tắc lịch sử hoặc DST của một vùng địa lý.

## 2. `InstantSource` là gì?

`InstantSource` là interface trong `java.time`, được giới thiệu từ **Java 17**. Nó cung cấp một phương thức cốt lõi:

```java
Instant instant();
```

Phương thức này trả về thời điểm theo định nghĩa của nguồn. Interface còn có phương thức mặc định `millis()` và `withZone(ZoneId)`, cùng các factory method tạo nguồn thời gian.

Mục đích quan trọng của `InstantSource` là **tách phụ thuộc vào đồng hồ hệ thống**. Thay vì gọi `Instant.now()` hoặc `System.currentTimeMillis()` trực tiếp ở mọi nơi, ứng dụng nhận một nguồn thời gian qua constructor hoặc tham số. Khi kiểm thử, ta có thể thay nguồn hệ thống bằng nguồn cố định.

Ví dụ:

```java
import java.time.Instant;
import java.time.InstantSource;

InstantSource source = InstantSource.system();
Instant now = source.instant();

System.out.println(now);
```

`InstantSource.system()` trả về nguồn dựa trên đồng hồ hệ thống tốt nhất hiện có. Nguồn này không gắn với múi giờ cụ thể.

### 2.1. `InstantSource` chỉ quan tâm đến thời điểm

Interface không có `getZone()`. Điều này là chủ ý: lấy một `Instant` không cần biết người dùng đang ở đâu.

```java
InstantSource source = InstantSource.system();

Instant current = source.instant();
long epochMillis = source.millis();
```

`millis()` trả số mili giây từ epoch UTC. Tuy nhiên, API khuyến nghị phần lớn ứng dụng nên dùng `Instant` thay vì giá trị số mili giây thô, trừ khi có lý do hiệu năng cụ thể.

Một `InstantSource` cũng không bảo đảm kết quả luôn là thời gian thực chính xác từ một đồng hồ vật lý. Nó cho phép ứng dụng cung cấp **góc nhìn có kiểm soát về thời gian**, chẳng hạn thời điểm cố định trong test hoặc nguồn thời gian từ hệ thống bên ngoài.

### 2.2. `InstantSource` là functional interface

`InstantSource` chỉ có một phương thức trừu tượng `instant()`, vì vậy có thể dùng lambda:

```java
import java.time.Instant;
import java.time.InstantSource;

InstantSource source =
        () -> Instant.parse("2025-01-01T00:00:00Z");

System.out.println(source.instant());
```

Trong ứng dụng thực tế, `InstantSource.fixed(...)` thường diễn đạt ý định rõ hơn lambda:

```java
InstantSource source =
        InstantSource.fixed(Instant.parse("2025-01-01T00:00:00Z"));
```

Lambda hữu ích để hiểu tính chất functional interface hoặc mô phỏng một nguồn tùy chỉnh; factory method là lựa chọn dễ đọc cho các trường hợp phổ biến.

## 3. `Clock` là gì và quan hệ với `InstantSource`?

`Clock` là một **abstract class** trong `java.time`, triển khai interface `InstantSource`. Ngoài việc cung cấp `instant()`, `Clock` còn có `ZoneId`:

```java
public abstract class Clock implements InstantSource {
    public abstract ZoneId getZone();
    public abstract Clock withZone(ZoneId zone);
    public abstract Instant instant();
}
```

Đoạn trên chỉ minh họa các phương thức cốt lõi liên quan đến bài học, không phải toàn bộ khai báo API.

Có thể hình dung quan hệ:

```text
           InstantSource
           (interface)
                ^
                |
           implements
                |
              Clock
          (abstract class)
           /          \
       instant()     getZone()
          |             |
      thời điểm       múi giờ
```

Do `Clock` là một `InstantSource`, mọi nơi nhận `InstantSource` đều có thể nhận một `Clock`:

```java
InstantSource source = Clock.systemUTC();
Instant now = source.instant();
```

Nhưng chiều ngược lại không tự động đúng: một `InstantSource` bất kỳ có thể không có múi giờ và không phải `Clock`. Khi cần một `Clock` từ nguồn đó, dùng `withZone(ZoneId)`.

### 3.1. Bảng so sánh

| Đặc điểm | `InstantSource` | `Clock` |
|---|---|---|
| Là loại gì? | Interface | Abstract class |
| Có từ | Java 17 | Java 8 |
| Cung cấp `instant()` | Có | Có, triển khai `InstantSource` |
| Có `millis()` | Có, default method | Có, kế thừa/ghi đè |
| Có múi giờ `getZone()` | Không | Có |
| Có `withZone(ZoneId)` | Có, trả về `Clock` | Có, trả về `Clock` |
| Nguồn cố định | `InstantSource.fixed(instant)` | `Clock.fixed(instant, zone)` |
| Dùng tốt khi | Chỉ cần biết thời điểm | Cần thời điểm và ngữ cảnh múi giờ |

**Cách chọn:** nếu logic chỉ cần biết “đã đến hạn chưa?” hoặc “sự kiện xảy ra trước thời điểm nào?”, `InstantSource` thường đủ. Nếu logic cần “hôm nay là ngày nào tại chi nhánh?”, `Clock` phù hợp hơn vì có zone để diễn giải thời điểm.

## 4. Tạo `InstantSource` và `Clock` từ hệ thống

### 4.1. Nguồn thời gian không gắn zone

```java
InstantSource source = InstantSource.system();

Instant now = source.instant();
System.out.println(now);
```

Nguồn này trả `Instant` hiện tại theo đồng hồ hệ thống tốt nhất có sẵn. Nó không chọn một múi giờ để chuyển đổi thành ngày hoặc giờ địa phương.

### 4.2. Clock theo UTC

```java
Clock utcClock = Clock.systemUTC();

Instant instant = utcClock.instant();
ZoneId zone = utcClock.getZone();

System.out.println(instant);
System.out.println(zone); // Z
```

Dùng UTC khi cần một đồng hồ rõ ràng không phụ thuộc múi giờ mặc định của máy. `Instant` trả về vẫn là một thời điểm trên timeline; zone của clock sẽ được các API như `LocalDate.now(clock)` dùng khi cần tạo ngày địa phương.

### 4.3. Clock theo zone được chỉ định

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

Instant now = businessClock.instant();
LocalDate today = LocalDate.now(businessClock);
LocalTime time = LocalTime.now(businessClock);

System.out.println(now);
System.out.println(today);
System.out.println(time);
```

`Clock.system(zone)` dùng nguồn thời gian hệ thống và zone được chỉ định. Cùng một thời điểm có thể tạo ra ngày/giờ địa phương khác nhau khi dùng hai clock có zone khác nhau.

### 4.4. Clock theo zone mặc định của máy

```java
Clock defaultClock = Clock.systemDefaultZone();

System.out.println(defaultClock.getZone());
```

API này lấy múi giờ mặc định của JVM/máy. Nó tiện cho chương trình nhỏ hoặc công cụ phụ thuộc cấu hình máy, nhưng có thể làm hành vi ứng dụng thay đổi khi chuyển server, container hoặc khi cấu hình timezone hệ thống thay đổi.

Javadoc Java 17 khuyến nghị tránh phụ thuộc mặc định này khi có thể chỉ định một zone cụ thể. Với nghiệp vụ, nên chọn zone theo cấu hình nghiệp vụ hoặc người dùng thay vì ngầm lấy zone của máy chủ.

## 5. `InstantSource.withZone` tạo ra `Clock` như thế nào?

Đây là mối liên hệ trực tiếp giữa hai API.

`InstantSource` có phương thức mặc định:

```java
Clock withZone(ZoneId zone);
```

Nó tạo một `Clock` kết hợp nguồn instant hiện có với zone được chỉ định.

Ví dụ:

```java
InstantSource source = InstantSource.system();

Clock hcmClock = source.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Clock utcClock = source.withZone(ZoneOffset.UTC);

System.out.println(hcmClock.getZone());
System.out.println(utcClock.getZone());
```

Hai clock được tạo từ cùng nguồn instant nhưng dùng hai zone khác nhau.

- `hcmClock.instant()` và `utcClock.instant()` lấy thời điểm từ nguồn tương ứng.
- `LocalDate.now(hcmClock)` diễn giải thời điểm theo `Asia/Ho_Chi_Minh`.
- `LocalDate.now(utcClock)` diễn giải theo UTC.
- Chọn zone không dịch chuyển thời điểm trên timeline; nó chỉ thay đổi cách chuyển đổi sang ngày/giờ địa phương.

Với một nguồn cố định, khác biệt này dễ quan sát hơn:

```java
Instant fixedInstant = Instant.parse("2025-01-01T00:30:00Z");
InstantSource fixedSource = InstantSource.fixed(fixedInstant);

Clock hcm = fixedSource.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock utc = fixedSource.withZone(ZoneOffset.UTC);

System.out.println(hcm.instant());
System.out.println(utc.instant());

System.out.println(LocalDate.now(hcm));
System.out.println(LocalDate.now(utc));
```

Kết quả:

```text
2025-01-01T00:30:00Z
2025-01-01T00:30:00Z
2025-01-01
2025-01-01
```

Trong ví dụ này, cả hai ngày vẫn là 1/1 vì thời điểm được chọn chưa vượt qua ranh giới ngày ở hai zone. Để thấy khác biệt ngày, đổi thời điểm thành `2024-12-31T20:00:00Z`: tại UTC vẫn là 31/12/2024, còn tại Việt Nam đã là 1/1/2025.

`InstantSource.withZone` rất hữu ích khi một thư viện hoặc service chỉ yêu cầu abstraction đơn giản để lấy thời điểm, nhưng một tầng khác cần tạo `Clock` có zone.

## 6. `Clock.withZone` thay đổi zone, không đổi thời điểm

`Clock` cũng có `withZone(ZoneId)`. Phương thức trả về một clock dựa trên clock hiện tại nhưng dùng zone mới:

```java
Clock original = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Clock vietnam = original.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(original.instant());
System.out.println(vietnam.instant());

System.out.println(original.getZone());
System.out.println(vietnam.getZone());
```

Kết quả:

```text
2025-01-01T00:00:00Z
2025-01-01T00:00:00Z
Z
Asia/Ho_Chi_Minh
```

Hai clock có cùng thời điểm do nguồn fixed, nhưng zone khác nhau. Không nên nhầm `withZone` với việc cộng thêm bảy giờ vào `Instant`.

### 6.1. `withZone` khác `Instant.atZone`

Hai thao tác thường xuất hiện cạnh nhau nhưng trả về hai loại đối tượng khác nhau:

```java
Clock clock = Clock.systemUTC();

Clock localClock = clock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Instant instant = clock.instant();
ZonedDateTime localDateTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

- `clock.withZone(zone)` tạo **Clock mới** có zone mới.
- `instant.atZone(zone)` chuyển một **Instant cụ thể** thành `ZonedDateTime` tại zone đó.

Nếu chỉ có một thời điểm đã biết và muốn hiển thị theo múi giờ, `Instant.atZone` là thao tác trực tiếp. Nếu muốn một nguồn thời gian để nhiều phép `now(clock)` dùng chung zone, chọn `Clock.withZone` hoặc `Clock.system(zone)`.

## 7. ZoneId theo vùng và ZoneOffset cố định

`ZoneId` có thể đại diện vùng địa lý hoặc offset cố định. Hai cách này không tương đương về quy tắc thời gian.

### 7.1. Zone theo vùng địa lý

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
```

Vùng địa lý dùng bộ quy tắc theo ngày tháng. Ví dụ Paris có thể là UTC+01:00 vào mùa đông và UTC+02:00 vào mùa hè. New York có quy tắc riêng, không nên suy ra offset của nó bằng cách lấy offset Paris.

Khi cần xử lý lịch làm việc, lịch hẹn hoặc sự kiện theo địa điểm, hãy lưu zone ID có ý nghĩa như `Europe/Paris` thay vì chỉ lưu offset hiện tại.

### 7.2. Offset cố định

```java
ZoneOffset utc = ZoneOffset.UTC;
ZoneOffset vietnamOffset = ZoneOffset.of("+07:00");
ZoneOffset minusFive = ZoneOffset.of("-05:00");
```

Offset cố định phù hợp khi giao thức hoặc dữ liệu quy định một độ lệch cụ thể. Nó không biết quy tắc DST của một thành phố hoặc vùng.

Ví dụ, `-05:00` có thể là offset của một số nơi vào một thời điểm trong năm, nhưng không thể đại diện đầy đủ cho `America/New_York` quanh cả năm.

### 7.3. Chọn loại zone nào?

| Yêu cầu | Nên dùng |
|---|---|
| Thời điểm tuyệt đối để lưu/log/truyền giữa hệ thống | `Instant`, thường ghi theo UTC |
| Ngày làm việc của văn phòng ở Paris | `ZoneId.of("Europe/Paris")` |
| Lịch người dùng ở Việt Nam | `ZoneId.of("Asia/Ho_Chi_Minh")` |
| Giao thức quy định chính xác offset `+07:00` | `ZoneOffset.of("+07:00")` |
| Chỉ cần tính toán UTC | `ZoneOffset.UTC` |
| Lấy zone cấu hình máy chủ một cách có chủ ý | `ZoneId.systemDefault()` |

**Không dùng offset hiện tại để thay thế zone vùng địa lý** nếu nghiệp vụ cần lịch sử hoặc quy tắc thay đổi theo mùa.

## 8. Chuyển đổi giữa Instant và giờ địa phương

### 8.1. Từ Instant sang ZonedDateTime

```java
Instant instant = Instant.parse("2025-03-08T10:00:00Z");

ZonedDateTime hcmTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

ZonedDateTime parisTime = instant.atZone(
        ZoneId.of("Europe/Paris")
);

System.out.println(hcmTime);
System.out.println(parisTime);
```

Cùng một `Instant` được hiển thị ở hai zone khác nhau. Thời điểm tuyệt đối vẫn giữ nguyên.

### 8.2. Từ LocalDateTime sang Instant

Muốn chuyển ngược, cần cung cấp zone:

```java
LocalDateTime local = LocalDateTime.of(2025, 3, 8, 17, 0);

Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();

System.out.println(instant);
```

Nếu dùng `ZoneOffset.of("+07:00")` thay vì `Asia/Ho_Chi_Minh`, phép chuyển đổi cũng tạo ra một thời điểm cho local time đó, nhưng chỉ dựa trên offset cố định.

### 8.3. Từ Clock sang ngày giờ địa phương

Các factory method `now(Clock)` của các lớp ngày giờ nhận `Clock`:

```java
Clock clock = Clock.system(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
LocalDateTime dateTime = LocalDateTime.now(clock);
ZonedDateTime zoned = ZonedDateTime.now(clock);
```

`Instant.now(clock)` lấy thời điểm; `LocalDate.now(clock)`, `LocalTime.now(clock)` và các API tương tự dùng zone của clock để tạo giá trị địa phương.

Nếu chỉ có `InstantSource`, có thể lấy instant trực tiếp bằng `source.instant()`. Khi cần `LocalDate.now(clock)`, chuyển nguồn sang clock bằng `source.withZone(zone)`.

## 9. DST: vì sao zone địa lý không chỉ là một offset?

Một số vùng thay đổi offset theo mùa (daylight saving time). Điều này tạo ra hai trường hợp đặc biệt cho `LocalDateTime`:

- **Gap:** đồng hồ nhảy tới phía trước; một số giờ địa phương không tồn tại.
- **Overlap:** đồng hồ lùi lại; một số giờ địa phương xuất hiện hai lần.

### 9.1. Gap — giờ địa phương không tồn tại

Ví dụ tại Paris vào ngày chuyển sang giờ mùa hè, đồng hồ nhảy từ 02:00 lên 03:00. `02:30` trong ngày đó không tồn tại theo quy tắc zone.

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime localGap = LocalDateTime.of(2025, 3, 30, 2, 30);

ZonedDateTime resolved = localGap.atZone(paris);

System.out.println(resolved);
```

`LocalDateTime.atZone` điều chỉnh giờ địa phương nằm trong gap tiến lên theo độ dài gap. Với ví dụ này, kết quả được điều chỉnh tới khoảng `03:30+02:00[Europe/Paris]`.

Đây là hành vi tự động của API; nếu nghiệp vụ yêu cầu từ chối một giờ không tồn tại, cần kiểm tra quy tắc zone và xác thực đầu vào thay vì mặc định chấp nhận điều chỉnh.

### 9.2. Overlap — giờ địa phương xuất hiện hai lần

Khi đồng hồ lùi lại, cùng một giờ địa phương có thể ứng với hai offset khác nhau:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime localOverlap =
        LocalDateTime.of(2025, 10, 26, 2, 30);

ZonedDateTime first = localOverlap.atZone(paris);
ZonedDateTime later = first.withLaterOffsetAtOverlap();

System.out.println(first);
System.out.println(later);
System.out.println(first.toInstant());
System.out.println(later.toInstant());
```

Hai `ZonedDateTime` có cùng ngày giờ địa phương `02:30` nhưng offset khác nhau, vì vậy chúng đại diện cho **hai Instant khác nhau**. Mặc định `atZone` chọn offset sớm hơn trong overlap; có thể dùng `withLaterOffsetAtOverlap()` để chọn lần xuất hiện sau.

### 9.3. Khi cần xác thực nghiêm ngặt

Nếu ứng dụng nhận đồng thời local date-time, zone và offset từ bên ngoài, có thể dùng `ZonedDateTime.ofStrict` để yêu cầu offset phải hợp lệ cho zone tại thời điểm đó:

```java
ZonedDateTime validated = ZonedDateTime.ofStrict(
        localDateTime,
        suppliedOffset,
        zone
);
```

Nếu local time rơi vào gap hoặc offset không hợp lệ trong overlap, API từ chối bằng exception thay vì tự điều chỉnh. Đây là lựa chọn phù hợp khi dữ liệu lịch hẹn phải được xác thực chính xác.

## 10. Dùng InstantSource để tách phụ thuộc thời gian trong ứng dụng

Một lợi ích lớn của `InstantSource` là không buộc service phải đọc đồng hồ hệ thống trực tiếp.

Ví dụ service kiểm tra hạn:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class ExpirationService {
    private final InstantSource timeSource;

    public ExpirationService(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(Instant expiresAt) {
        return !timeSource.instant().isBefore(expiresAt);
    }
}
```

Ứng dụng production có thể truyền:

```java
ExpirationService service =
        new ExpirationService(InstantSource.system());
```

Test có thể truyền thời điểm cố định:

```java
Instant fixedNow = Instant.parse("2025-01-01T10:00:00Z");

ExpirationService service = new ExpirationService(
        InstantSource.fixed(fixedNow)
);

boolean expired = service.isExpired(
        Instant.parse("2025-01-01T09:59:59Z")
);

System.out.println(expired); // true
```

Không cần chờ thời gian thực hoặc mock static method. Mỗi lần gọi `timeSource.instant()` trong test đều trả đúng thời điểm đã chọn.

### 10.1. Khi chỉ cần InstantSource

Các logic sau thường chỉ cần `InstantSource`:

- Kiểm tra token hoặc session đã hết hạn chưa.
- Ghi thời điểm tạo bản ghi.
- So sánh sự kiện trước/sau một deadline đã biểu diễn bằng `Instant`.
- Đo thời điểm xử lý một nghiệp vụ có timestamp tuyệt đối.
- Gắn thời gian vào audit event.

Ví dụ:

```java
Instant createdAt = timeSource.instant();
```

Không cần zone chỉ để ghi một thời điểm tuyệt đối.

### 10.2. Khi cần Clock

Nếu logic phụ thuộc ngày hoặc giờ địa phương, nhận `Clock`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public class BillingService {
    private final Clock clock;

    public BillingService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate billingDate() {
        return LocalDate.now(clock);
    }
}
```

Khi tạo service, cấu hình zone nghiệp vụ:

```java
Clock billingClock = Clock.system(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

BillingService service = new BillingService(billingClock);
```

Test dùng clock cố định:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-01T16:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

BillingService service = new BillingService(fixedClock);
System.out.println(service.billingDate()); // 2025-01-01
```

Nếu thay zone thành UTC, cùng instant đó có thể thuộc ngày địa phương khác. Đó chính là lý do zone cần được đưa vào thiết kế khi nghiệp vụ phụ thuộc lịch.

## 11. Các nguồn thời gian cố định, lệch và theo nhịp

Cả `InstantSource` và `Clock` có các factory method hữu ích cho test và ứng dụng.

### 11.1. `fixed` — thời gian luôn cố định

`InstantSource`:

```java
InstantSource fixedSource = InstantSource.fixed(
        Instant.parse("2025-01-01T00:00:00Z")
);
```

`Clock`:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
```

Mọi lần gọi đều trả cùng một instant. Đây là lựa chọn tốt để test deadline, ngày hóa đơn, ngày hết hạn hoặc các quy tắc ranh giới.

### 11.2. `offset` — dịch nguồn thời gian theo Duration

Có thể tạo nguồn trả thời điểm lệch so với nguồn cơ sở:

```java
InstantSource source = InstantSource.system();

InstantSource twoHoursLater = InstantSource.offset(
        source,
        Duration.ofHours(2)
);

System.out.println(twoHoursLater.instant());
```

Với `Clock`:

```java
Clock clock = Clock.systemUTC();

Clock simulated = Clock.offset(
        clock,
        Duration.ofDays(1)
);
```

Đây là dịch chuyển thời gian mô phỏng, hữu ích cho test hoặc một số tình huống đặc biệt. Không dùng `offset` để sửa timezone; muốn thay zone thì dùng `withZone`.

### 11.3. `tick` — làm tròn thời điểm theo nhịp

`tick` tạo nguồn chỉ thay đổi theo các mốc thời gian đã cắt cụt theo một duration:

```java
InstantSource source = InstantSource.tick(
        InstantSource.system(),
        Duration.ofSeconds(1)
);

System.out.println(source.instant());
```

`Clock` cũng có factory method tương ứng:

```java
Clock secondClock = Clock.tick(
        Clock.systemUTC(),
        Duration.ofSeconds(1)
);
```

Tick clock hữu ích khi ứng dụng không cần độ phân giải nhỏ hơn một nhịp cụ thể. Không giả định mọi lần gọi sẽ quan sát được đúng thời điểm chuyển nhịp; API có thể dùng chiến lược cache.

`tickDuration` phải dương. Với duration nhỏ hơn một mili giây, quy tắc chia vào một giây phải thỏa điều kiện của API. Hãy xem Javadoc Java 17 nếu chọn độ phân giải đặc biệt.

### 11.4. So sánh factory method

| Mục tiêu | InstantSource | Clock |
|---|---|---|
| Lấy thời gian hệ thống | `InstantSource.system()` | `Clock.system(zone)` / `Clock.systemUTC()` |
| Cố định thời gian | `InstantSource.fixed(instant)` | `Clock.fixed(instant, zone)` |
| Dịch thời gian | `InstantSource.offset(source, duration)` | `Clock.offset(clock, duration)` |
| Cắt theo nhịp | `InstantSource.tick(source, duration)` | `Clock.tick(clock, duration)` |
| Gắn zone | `source.withZone(zone)` trả `Clock` | `clock.withZone(zone)` |

## 12. Clock không phải đồng hồ đo thời lượng đơn điệu

`InstantSource` và `Clock` dùng để lấy **thời điểm theo đồng hồ lịch** (wall-clock time). Đồng hồ hệ thống có thể bị điều chỉnh bởi đồng bộ thời gian, quản trị viên hoặc môi trường ảo hóa. Vì vậy thời điểm quan sát được có thể nhảy tiến hoặc lùi.

Nếu cần đo **thời lượng đã trôi qua** (elapsed time) hoặc timeout chính xác trong cùng tiến trình, thường dùng `System.nanoTime()`:

```java
long start = System.nanoTime();

// Thực hiện công việc cần đo.
doWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println(elapsed);
```

Không dùng phép trừ hai `Instant` từ system clock để thay thế bộ đếm đơn điệu cho timeout. `InstantSource` có thể thay thế nguồn thời gian trong test, nhưng không hứa hẹn đồng hồ đơn điệu.

Cần phân biệt:

- **Thời điểm thực tế theo lịch:** `Instant`, `InstantSource`, `Clock`.
- **Khoảng thời gian giữa hai thao tác:** `Duration` và đồng hồ đơn điệu như `System.nanoTime()`.

## 13. Lưu và truyền dữ liệu thời gian giữa các hệ thống

Một thiết kế thường gặp là lưu sự kiện theo `Instant`, còn zone được dùng khi hiển thị hoặc tính lịch nghiệp vụ.

Ví dụ:

```java
Instant createdAt = Instant.now(Clock.systemUTC());

// Lưu createdAt dưới dạng timestamp UTC hoặc ISO-8601 có Z.
String serialized = createdAt.toString();

// Khi hiển thị cho người dùng:
ZonedDateTime displayTime = createdAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

Lợi ích:

- Dữ liệu sự kiện giữ một mốc tuyệt đối nhất quán.
- Mỗi client có thể hiển thị theo zone của người dùng.
- Server không phải giả định timezone của hệ điều hành.
- So sánh và sắp xếp sự kiện dễ dàng bằng Instant.

### 13.1. Khi nghiệp vụ cần giữ giờ địa phương đã đặt

Một lịch hẹn “09:00 giờ Paris vào ngày 1/4” có ý nghĩa khác với một sự kiện đã xảy ra tại một Instant cụ thể.

Nếu người dùng đặt lịch theo giờ địa phương và lịch phải tuân theo thay đổi DST trong tương lai, dữ liệu thường cần lưu:

- `LocalDateTime` mà người dùng đã chọn.
- `ZoneId` của địa điểm (ví dụ `Europe/Paris`).
- Quy tắc xử lý gap/overlap nếu nghiệp vụ cần quyết định rõ.

Sau đó ứng dụng mới xác định `Instant` tương ứng theo quy tắc zone tại thời điểm cần tính. Chỉ lưu offset hiện tại có thể làm mất ý nghĩa lịch khi quy tắc DST thay đổi.

Nếu lịch hẹn đã được xác nhận thành một thời điểm tuyệt đối, lưu thêm `Instant` là hữu ích để giữ đúng mốc đã chốt. Việc có cần lưu cả local time và zone hay không phụ thuộc hợp đồng nghiệp vụ.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Cùng code nhưng ngày khác trên server | Dùng zone mặc định của máy | Truyền `Clock` với zone nghiệp vụ tường minh |
| Nghĩ `InstantSource` có múi giờ | Nhầm source với Clock | `InstantSource` chỉ cung cấp instant; dùng `withZone` để tạo Clock |
| Nghĩ `withZone` cộng giờ vào instant | Nhầm thay đổi zone với dịch thời gian | So sánh `instant()` trước/sau; zone chỉ ảnh hưởng diễn giải |
| Dùng `+07:00` thay cho zone thành phố | Offset cố định không có quy tắc vùng/DST | Dùng `ZoneId` vùng địa lý khi nghiệp vụ phụ thuộc địa điểm |
| Test phụ thuộc thời gian thực | Gọi `Instant.now()` hoặc `LocalDate.now()` trực tiếp trong logic | Inject `InstantSource` hoặc `Clock` và dùng `fixed` trong test |
| Giờ địa phương không tồn tại hoặc lặp lại | DST gap/overlap | Xác thực bằng zone rules hoặc dùng `ofStrict` khi cần |
| Đo timeout bằng hai Instant | Wall-clock có thể bị điều chỉnh | Dùng `System.nanoTime()` để đo elapsed time |
| Múi giờ ứng dụng đổi sau khi deploy | Dựa vào system default | Đưa zone nghiệp vụ vào cấu hình và truyền rõ ràng |

### 14.1. Không dùng viết tắt zone mơ hồ

Các chuỗi như `PST`, `CST` hoặc `IST` có thể chỉ những vùng khác nhau tùy ngữ cảnh. Hãy ưu tiên ID vùng rõ ràng theo dạng `Area/Location` như `America/Los_Angeles` hoặc `Asia/Ho_Chi_Minh`.

### 14.2. Không tự cộng offset để đổi giờ

Tránh:

```java
// Không nên tự cộng 7 giờ để "đổi sang Việt Nam".
Instant vietnamTime = Instant.now().plus(Duration.ofHours(7));
```

Đoạn này tạo **Instant mới ở tương lai 7 giờ**, không chuyển cách hiển thị sang timezone Việt Nam. Đúng hơn:

```java
ZonedDateTime vietnamTime = Instant.now()
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Kết quả là cùng thời điểm được trình bày theo zone Việt Nam.

## 15. Ví dụ hoàn chỉnh: service nhận InstantSource và Clock

Ví dụ sau thể hiện hai nhu cầu trong một ứng dụng: kiểm tra hạn bằng instant và lấy ngày hóa đơn theo zone nghiệp vụ.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class TimeService {
    private final InstantSource instantSource;
    private final Clock businessClock;

    public TimeService(InstantSource instantSource, Clock businessClock) {
        this.instantSource = Objects.requireNonNull(instantSource);
        this.businessClock = Objects.requireNonNull(businessClock);
    }

    public boolean isPastDeadline(Instant deadline) {
        return !instantSource.instant().isBefore(deadline);
    }

    public LocalDate businessDate() {
        return LocalDate.now(businessClock);
    }

    public static void main(String[] args) {
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

        // Production: cùng một nguồn hệ thống, gắn zone cho nghiệp vụ.
        InstantSource source = InstantSource.system();
        Clock clock = source.withZone(businessZone);

        TimeService service = new TimeService(source, clock);

        System.out.println("Business date: " + service.businessDate());
        System.out.println(
                "Deadline passed: "
                        + service.isPastDeadline(
                                Instant.parse("2025-01-01T00:00:00Z")
                        )
        );
    }
}
```

Trong test, thay cả hai dependency bằng nguồn fixed để kết quả có thể lặp lại:

```java
Instant fixedInstant = Instant.parse("2025-01-01T00:30:00Z");
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

InstantSource fixedSource = InstantSource.fixed(fixedInstant);
Clock fixedClock = fixedSource.withZone(businessZone);

TimeService service = new TimeService(fixedSource, fixedClock);

System.out.println(service.businessDate()); // 2025-01-01
System.out.println(
        service.isPastDeadline(
                Instant.parse("2025-01-01T00:00:00Z")
        )
); // true
```

Ví dụ này có thể đơn giản hóa bằng cách chỉ inject `Clock` nếu mọi logic đều cần cả instant và zone, vì `Clock` cũng là `InstantSource`. Tách thành hai dependency chỉ hợp lý khi hai phần của ứng dụng có nhu cầu khác nhau hoặc muốn thể hiện rõ contract.

## 16. Bài tập tự luyện

### Bài 1 — InstantSource hay Clock?

Một service chỉ kiểm tra xem thời điểm hiện tại có vượt qua `expiresAt` chưa. Nó không cần biết múi giờ.

**Đáp án:** Inject `InstantSource`. So sánh `source.instant()` với `expiresAt`. Khi test, dùng `InstantSource.fixed(...)`.

### Bài 2 — Vì sao hai ngày có thể khác nhau?

```java
Instant instant = Instant.parse("2024-12-31T20:00:00Z");

LocalDate utcDate = instant.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate hcmDate = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
).toLocalDate();
```

**Đáp án:** UTC là `2024-12-31`, Việt Nam là `2025-01-01`. Đây là cùng một instant được diễn giải theo hai zone khác nhau.

### Bài 3 — withZone có đổi Instant không?

```java
Clock fixed = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Clock hcm = fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

**Đáp án:** Không. Cả hai clock trả cùng `Instant` cố định. `getZone()` khác nhau, nên các phép chuyển sang ngày/giờ địa phương có thể khác.

### Bài 4 — Chọn zone cho lịch hẹn Paris

Người dùng đặt lịch `09:00` ở Paris vào một ngày trong tương lai. Vì sao chỉ lưu `+01:00` có thể sai?

**Đáp án:** Paris có thể áp dụng offset khác theo quy tắc DST và ngày cụ thể. Lưu `ZoneId.of("Europe/Paris")` giữ được quy tắc vùng; offset cố định không đủ để diễn giải mọi ngày.

### Bài 5 — Đo thời gian chạy

Một đoạn code cần đo thời lượng thực thi để ghi metric. Nên dùng `Clock` hay `System.nanoTime()`?

**Đáp án:** Dùng `System.nanoTime()` để đo khoảng thời gian đơn điệu trong tiến trình. `Clock`/`InstantSource` phục vụ thời điểm theo lịch, không bảo đảm đơn điệu.

## 17. Ghi nhớ

- `Instant` là thời điểm tuyệt đối; bản thân nó không có múi giờ.
- `InstantSource` (Java 17) là abstraction cung cấp `Instant`, giúp thay nguồn thời gian trong kiểm thử.
- `Clock` triển khai `InstantSource` và bổ sung `ZoneId`.
- `InstantSource.withZone(zone)` tạo `Clock`; `Clock.withZone(zone)` tạo clock khác zone dựa trên cùng nguồn thời gian.
- `Clock.system(zone)` phù hợp khi cần thời gian hệ thống và zone nghiệp vụ rõ ràng.
- `Clock.fixed` và `InstantSource.fixed` giúp test thời gian có tính xác định.
- `ZoneId` vùng địa lý mang quy tắc lịch sử/DST; `ZoneOffset` là độ lệch cố định.
- `Instant.atZone(zone)` thay đổi cách biểu diễn thời điểm, không thay đổi chính Instant.
- Dùng `System.nanoTime()` để đo thời lượng; dùng `InstantSource`/`Clock` cho thời điểm theo lịch.
- Không dựa vào timezone mặc định của máy cho nghiệp vụ cần kết quả nhất quán giữa các môi trường.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `java.time.InstantSource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html).
- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).
- [Java SE 17 API — `java.time.Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).
- [Java SE 17 API — `java.time.ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html).
- [Java SE 17 API — `java.time.ZoneOffset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html).
- [Java SE 17 API — `java.time.ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).
- [Java SE 17 API — `java.time.LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

