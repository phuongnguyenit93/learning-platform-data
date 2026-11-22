# Kết hợp và chuyển kiểu bằng `at...()` và `to...()` trong `java.time`

Khi lập trình ngày giờ, ta thường có các mảnh dữ liệu khác nhau: người dùng chọn một ngày, nhập giờ hẹn, chọn địa điểm, rồi ứng dụng cần lưu thời điểm thực tế của cuộc hẹn. Java cung cấp các phương thức như `atTime()`, `atDate()`, `atZone()`, `atOffset()`, `toLocalDate()`, `toLocalTime()` và `toInstant()` để **ghép thông tin hoặc chuyển giữa các cách biểu diễn**.

Các tên `at...()` và `to...()` là một cách gợi nhớ, nhưng không phải hai quy tắc cú pháp thay thế cho nhau. Mỗi phương thức thuộc **một lớp cụ thể**, nhận tham số cụ thể và trả về một kiểu cụ thể. Điều quan trọng là hiểu phép chuyển đó **thêm thông tin gì, giữ điều gì và có làm mất thông tin không**.

Bài này thuộc phần **Làm quen `java.time`** và tập trung vào các phép kết hợp/chuyển kiểu thường dùng, cách đọc kết quả, những rủi ro về múi giờ và cách kiểm chứng bằng Java 17+.

## 1. Nhắc lại các kiểu dữ liệu cần ghép/chuyển

| Kiểu | Chứa thông tin gì? | Thiếu thông tin gì? |
| --- | --- | --- |
| `LocalDate` | Năm, tháng, ngày | Giờ, offset, múi giờ |
| `LocalTime` | Giờ, phút, giây, nano giây nếu có | Ngày, offset, múi giờ |
| `LocalDateTime` | Ngày + giờ địa phương | Offset/múi giờ để xác định duy nhất một thời điểm |
| `ZoneOffset` | Độ lệch UTC cụ thể, ví dụ `+07:00` | Các quy tắc múi giờ theo khu vực |
| `ZoneId` | Định danh vùng, ví dụ `Asia/Ho_Chi_Minh` | Một giờ cụ thể; phải kết hợp với ngày/giờ hoặc instant |
| `OffsetDateTime` | Ngày giờ + offset cụ thể | Định danh/quy tắc múi giờ khu vực |
| `ZonedDateTime` | Ngày giờ + `ZoneId` và offset đã giải quyết | Không thiếu thông tin để suy ra một instant |
| `Instant` | Một mốc duy nhất trên dòng thời gian | Cách trình bày theo lịch/múi giờ của người dùng |

Ví dụ chuỗi `2026-10-24 09:30` mới là ngày giờ địa phương. Nếu biết đó là `Asia/Ho_Chi_Minh`, Java có thể áp dụng quy tắc vùng để suy ra `2026-10-24T02:30:00Z`. Ngược lại, khi đã có một `Instant`, phải cung cấp múi giờ mới hiển thị đúng ngày và giờ cho người dùng.

Có hai hướng chuyển quan trọng:

~~~text
LocalDate + LocalTime
         │ atTime() / atDate()
         ▼
   LocalDateTime + ZoneId
         │ atZone()
         ▼
    ZonedDateTime
         │ toInstant()
         ▼
       Instant
         │ atZone(ZoneId)
         ▼
    ZonedDateTime
         │ toLocalDate() / toLocalTime() / toLocalDateTime()
         ▼
   Thành phần lịch để hiển thị
~~~

Các mũi tên **không** có nghĩa mọi bước đều giữ đủ thông tin để đảo ngược. `toLocalDate()` bỏ giờ và vùng; muốn quay lại cùng instant thì không thể dựa vào một ngày đơn lẻ.

## 2. `at...()`: kết hợp thông tin hoặc đặt một giá trị vào ngữ cảnh

### 2.1. `LocalDate.atTime()` và `LocalTime.atDate()`

Khi có ngày và giờ riêng, kết hợp chúng thành `LocalDateTime`:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime a = date.atTime(time);
LocalDateTime b = time.atDate(date);

// Cả a và b đều là 2026-10-24T09:30.
~~~

Hai cách tạo cùng **ngày giờ địa phương**. Dù một phương thức bắt đầu từ ngày, phương thức kia bắt đầu từ giờ, **cả hai đều chưa tạo một instant**. Chương trình vẫn cần xác định vùng hoặc offset nếu muốn biết 09:30 đó tương ứng với mốc nào trên dòng thời gian.

`LocalDate` còn có overload `atTime(int hour, int minute)`, `atTime(int hour, int minute, int second)` và `atTime(OffsetTime)`. Với `OffsetTime`, kết quả là `OffsetDateTime` vì giờ đã chứa offset; không phải lúc nào tên `atTime` cũng trả về `LocalDateTime`.

### 2.2. `atStartOfDay()` và `atStartOfDay(ZoneId)`

Một ngày không chứa giờ. Đôi khi cần ranh giới đầu ngày:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

LocalDateTime localMidnight = date.atStartOfDay();
ZonedDateTime firstValidTime =
        date.atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`atStartOfDay()` không có đối số trả về `LocalDateTime` tại `00:00`. Trong khi đó, `atStartOfDay(ZoneId)` trả về **`ZonedDateTime` tại thời điểm bắt đầu ngày hợp lệ theo quy tắc vùng**. Có những nơi/từng giai đoạn lịch sử mà nửa đêm nằm trong khoảng giờ bị bỏ qua; vì vậy biến có vùng không nhất thiết hiện đúng `00:00`.

Cách có vùng thích hợp để xác định biên truy vấn “các sự kiện của ngày D tại địa phương X”.

### 2.3. `LocalDateTime.atZone(ZoneId)`

Khi có lịch hẹn theo giờ địa phương và **biết địa điểm/múi giờ**, gắn nó với `ZoneId`:

~~~java
LocalDateTime appointment = LocalDateTime.of(2026, 10, 24, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localAppointment = appointment.atZone(zone);
Instant eventTime = localAppointment.toInstant();
~~~

Trong ví dụ, `eventTime` là `2026-10-24T02:30:00Z`. `atZone` dùng quy tắc vùng để chọn offset hợp lệ cho ngày giờ được cung cấp; nó không đơn thuần gắn chuỗi tên múi giờ vào giá trị.

**Lưu ý:** ở vùng có giờ mùa hè, một giờ địa phương có thể bị bỏ qua hoặc lặp lại. `atZone` có cách xử lý mặc định, vì thế hệ thống đặt lịch cần xem xét chính sách DST ở phần dưới.

### 2.4. `LocalDateTime.atOffset(ZoneOffset)`

Khi **biết chính xác offset** của giờ địa phương, có thể tạo `OffsetDateTime`:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);
OffsetDateTime datedWithOffset =
        local.atOffset(ZoneOffset.ofHours(7));

Instant sameMoment = datedWithOffset.toInstant();
~~~

Kết quả `datedWithOffset` là `2026-10-24T09:30+07:00`, suy ra cùng instant `2026-10-24T02:30:00Z`. `ZoneOffset` nói rõ khoảng lệch cố định, nhưng **không chứng minh** offset đó là đúng cho một vùng như New York vào ngày đang xét. Khi nghiệp vụ chỉ cho tên khu vực, nên dùng `atZone(ZoneId)`.

### 2.5. Các tổ hợp khác hữu ích

`LocalTime.atOffset(ZoneOffset)` tạo `OffsetTime`, tức giờ đồng hồ có offset nhưng vẫn **chưa có ngày**. Khi có thêm ngày, `OffsetTime.atDate(LocalDate)` trả về `OffsetDateTime`.

~~~java
LocalTime opening = LocalTime.of(8, 0);
OffsetTime timeWithOffset = opening.atOffset(ZoneOffset.ofHours(7));

LocalDate date = LocalDate.of(2026, 10, 24);
OffsetDateTime fullValue = timeWithOffset.atDate(date);

// fullValue = 2026-10-24T08:00+07:00
~~~

Tương tự, `date.atTime(timeWithOffset)` cũng tạo `OffsetDateTime`. Hai chiều kết hợp này giúp chọn cách viết phù hợp khi thành phần ngày/giờ đã có sẵn.

`Instant.atZone(ZoneId)` và `Instant.atOffset(ZoneOffset)` lại là một trường hợp khác: chúng bắt đầu từ **instant đã biết** rồi tạo cách biểu diễn theo vùng/offset, do đó **giữ nguyên thời điểm tuyệt đối**.

~~~java
Instant recorded = Instant.parse("2026-10-24T02:30:00Z");

ZonedDateTime vnView =
        recorded.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
OffsetDateTime offsetView = recorded.atOffset(ZoneOffset.ofHours(7));

// vnView    = 2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
// offsetView = 2026-10-24T09:30+07:00
~~~

Cùng là tên `atZone` nhưng **`LocalDateTime.atZone` phải diễn giải giờ địa phương**, còn **`Instant.atZone` chỉ chuyển cách hiển thị của một instant đã xác định**.

## 3. `to...()`: lấy thành phần hoặc chuyển cách biểu diễn

### 3.1. Từ `LocalDateTime` về ngày và giờ

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDate day = local.toLocalDate(); // 2026-10-24
LocalTime time = local.toLocalTime(); // 09:30
~~~

`toLocalDate()` và `toLocalTime()` **tách một phần** của `LocalDateTime`. Nếu chỉ giữ `day` thì đã mất 09:30; chỉ giữ `time` thì không biết ngày 24/10. Hai phép tách này phục vụ trình bày và xử lý thành phần lịch, không phải chuyển múi giờ.

### 3.2. Từ `ZonedDateTime` sang `Instant`

~~~java
ZonedDateTime scheduled =
        LocalDateTime.of(2026, 10, 24, 9, 30)
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant moment = scheduled.toInstant();
~~~

`toInstant()` giữ **chính xác điểm trên dòng thời gian**, nhưng kết quả không còn mang tên vùng hay giờ địa phương. Khi hiển thị lại cho người dùng, cần cung cấp `ZoneId`.

Từ `ZonedDateTime` có thể gọi:

- `toLocalDate()` để lấy ngày lịch.
- `toLocalTime()` để lấy giờ trên đồng hồ.
- `toLocalDateTime()` để lấy cả ngày và giờ, nhưng **bỏ thông tin vùng/offset**.
- `toOffsetDateTime()` để lấy ngày giờ và **offset đang áp dụng**, nhưng bỏ định danh quy tắc vùng.
- `toInstant()` để lấy mốc tuyệt đối, bỏ biểu diễn lịch và vùng.

Các phép `toLocal...()` hoặc `toOffsetDateTime()` có thể làm mất ngữ cảnh cần thiết để tái hiện lịch lặp lại trong tương lai. Không coi chúng là thao tác chuyển đổi “không mất thông tin”.

### 3.3. Từ `OffsetDateTime` sang `Instant` và các kiểu khác

~~~java
OffsetDateTime input =
        OffsetDateTime.parse("2026-10-24T09:30:00+07:00");

Instant stored = input.toInstant();
LocalDateTime shownWithoutOffset = input.toLocalDateTime();
ZonedDateTime withFixedOffsetZone = input.toZonedDateTime();
~~~

`input.toInstant()` cho `2026-10-24T02:30:00Z`. `input.toLocalDateTime()` cho `2026-10-24T09:30` và **mất offset**. `toZonedDateTime()` tạo `ZonedDateTime` dùng chính offset của giá trị làm zone; nó **không tự khôi phục** vùng địa lý gốc như `Asia/Ho_Chi_Minh`.

`OffsetDateTime` biết instant vì có offset, nhưng không biết địa phương gốc chỉ từ `+07:00`. Muốn gắn một vùng thật **và giữ nguyên instant**, dùng `input.atZoneSameInstant(zone)`.

### 3.4. `LocalDateTime.toInstant(ZoneOffset)`

`LocalDateTime` **không có** `toInstant()` không tham số. Khi đã biết offset cụ thể, Java cho phép:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);

Instant moment = local.toInstant(ZoneOffset.ofHours(7));
long epochSeconds = local.toEpochSecond(ZoneOffset.ofHours(7));
~~~

`toInstant(ZoneOffset)` trực tiếp sử dụng offset mà caller cung cấp; nó **không tra quy tắc của `ZoneId`**. Nếu đầu vào là giờ địa phương của một vùng có DST, cần xác nhận offset cho ngày đó, thường qua `atZone(zone).toInstant()`.

## 4. Bảng tra nhanh các phép ghép và chuyển kiểu

| Bắt đầu từ | Phương thức | Kiểu trả về | Tác động đến thông tin |
| --- | --- | --- | --- |
| `LocalDate` | `atTime(LocalTime)` | `LocalDateTime` | Thêm giờ vào ngày |
| `LocalTime` | `atDate(LocalDate)` | `LocalDateTime` | Thêm ngày vào giờ |
| `LocalDate` | `atStartOfDay()` | `LocalDateTime` | Chọn 00:00 địa phương, chưa có vùng |
| `LocalDate` | `atStartOfDay(ZoneId)` | `ZonedDateTime` | Tìm đầu ngày hợp lệ tại vùng |
| `LocalTime` | `atOffset(ZoneOffset)` | `OffsetTime` | Thêm offset vào giờ, chưa có ngày |
| `OffsetTime` | `atDate(LocalDate)` | `OffsetDateTime` | Thêm ngày vào giờ có offset |
| `LocalDateTime` | `atOffset(ZoneOffset)` | `OffsetDateTime` | Gán offset do caller cung cấp |
| `LocalDateTime` | `atZone(ZoneId)` | `ZonedDateTime` | Giải quyết offset theo quy tắc vùng |
| `Instant` | `atZone(ZoneId)` | `ZonedDateTime` | Giữ instant, biểu diễn theo vùng |
| `Instant` | `atOffset(ZoneOffset)` | `OffsetDateTime` | Giữ instant, biểu diễn theo offset |
| `ZonedDateTime` | `toInstant()` | `Instant` | Giữ instant; bỏ cách hiển thị/vùng |
| `ZonedDateTime` | `toOffsetDateTime()` | `OffsetDateTime` | Giữ instant và offset hiện tại; bỏ ZoneId |
| `ZonedDateTime` | `toLocalDateTime()` | `LocalDateTime` | Giữ ngày giờ trên đồng hồ; bỏ vùng/offset |
| `ZonedDateTime` | `toLocalDate()` / `toLocalTime()` | `LocalDate` / `LocalTime` | Chỉ giữ thành phần được lấy |
| `OffsetDateTime` | `toInstant()` | `Instant` | Giữ instant; bỏ biểu diễn giờ/offset |
| `OffsetDateTime` | `toLocalDateTime()` | `LocalDateTime` | Giữ giờ địa phương; bỏ offset |
| `LocalDateTime` | `toInstant(ZoneOffset)` | `Instant` | Suy ra instant bằng offset chỉ định |

Không phải mọi kiểu đều có mọi phương thức trong bảng. Hãy dựa vào kiểu biến ở **vế trái** của phép gọi, không suy diễn từ tên phương thức rồi áp lên một kiểu khác.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Chương trình sau minh họa ghép ngày + giờ, gắn khu vực, chuyển thành instant và chuyển sang khu vực khác, rồi lấy lại các thành phần:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AtToConversionDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30);

        LocalDateTime local = day.atTime(time);
        LocalDateTime sameLocal = time.atDate(day);

        ZoneId vietnamZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime vietnam = local.atZone(vietnamZone);
        Instant instant = vietnam.toInstant();

        ZonedDateTime tokyo =
                instant.atZone(ZoneId.of("Asia/Tokyo"));
        OffsetDateTime withOffset = vietnam.toOffsetDateTime();

        System.out.println("local=" + local);
        System.out.println("sameLocal=" + sameLocal);
        System.out.println("vietnam=" + vietnam);
        System.out.println("instant=" + instant);
        System.out.println("tokyo=" + tokyo);
        System.out.println("date=" + vietnam.toLocalDate());
        System.out.println("time=" + vietnam.toLocalTime());
        System.out.println("offset=" + withOffset);
        System.out.println("roundTrip=" +
                instant.atZone(vietnamZone).toLocalDateTime());
    }
}
~~~

Lưu file `AtToConversionDemo.java` và chạy:

~~~bash
javac AtToConversionDemo.java
java AtToConversionDemo
~~~

Kết quả dự kiến khi sử dụng dữ liệu múi giờ chuẩn tương ứng:

~~~text
local=2026-10-24T09:30
sameLocal=2026-10-24T09:30
vietnam=2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
instant=2026-10-24T02:30:00Z
tokyo=2026-10-24T11:30+09:00[Asia/Tokyo]
date=2026-10-24
time=09:30
offset=2026-10-24T09:30+07:00
roundTrip=2026-10-24T09:30
~~~

**Giải thích chuỗi chuyển đổi:**

1. `day.atTime(time)` và `time.atDate(day)` tạo cùng `LocalDateTime`; ở bước này **chưa có instant**.
2. `local.atZone(vietnamZone)` áp dụng quy tắc vùng và tạo `ZonedDateTime` với offset `+07:00` ở ngày đã chọn.
3. `vietnam.toInstant()` đưa mốc đó về biểu diễn độc lập múi giờ: `02:30 UTC`.
4. `instant.atZone(Asia/Tokyo)` cho `11:30` tại Tokyo **cùng một thời điểm**, thay vì giữ 09:30.
5. `toLocalDate()`, `toLocalTime()`, `toOffsetDateTime()` lấy các cách nhìn/nhóm thông tin khác nhau từ cùng giá trị.
6. Chuyển trở lại Việt Nam bằng `instant.atZone(vietnamZone)` cho đúng ngày giờ địa phương ban đầu vì ví dụ dùng một giờ hợp lệ và một vùng không có DST tại ngày đó.

Chương trình không gọi `now()`, do đó kết quả không phụ thuộc thời điểm thực thi.

## 6. Hai thao tác nhìn giống nhau nhưng khác nghiệp vụ

### 6.1. Chuyển vùng nhưng giữ nguyên instant

Từ `ZonedDateTime`, dùng `withZoneSameInstant(newZone)`:

~~~java
ZonedDateTime vietnam =
        LocalDateTime.of(2026, 10, 24, 9, 30)
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime sameMomentInTokyo =
        vietnam.withZoneSameInstant(ZoneId.of("Asia/Tokyo"));

// 2026-10-24T11:30+09:00[Asia/Tokyo]
~~~

Chuyển vùng ở đây làm thay đổi giờ trên đồng hồ nhưng giữ nguyên thời điểm thực tế. Đây là việc ta thường muốn khi hiển thị lịch sử giao dịch, sự kiện hoặc lịch hẹn cho người dùng ở múi giờ khác. Cách tương đương là `vietnam.toInstant().atZone(targetZone)`.

### 6.2. Đổi vùng nhưng cố giữ ngày giờ địa phương

`withZoneSameLocal(newZone)` cố giữ cùng **ngày và giờ trên đồng hồ**, rồi diễn giải chúng ở vùng mới:

~~~java
ZonedDateTime sameClockTimeInTokyo =
        vietnam.withZoneSameLocal(ZoneId.of("Asia/Tokyo"));

// 2026-10-24T09:30+09:00[Asia/Tokyo]
~~~

Giờ 09:30 Tokyo là một **instant khác** so với 09:30 Việt Nam. Cách này chỉ đúng nếu yêu cầu thật sự muốn thay đổi địa điểm của một giờ hẹn và vẫn giữ giờ đồng hồ. Tại các vùng có gap/overlap, Java có thể phải điều chỉnh giờ/offset để có thời điểm hợp lệ.

Tương tự, `OffsetDateTime.atZoneSameInstant(zone)` giữ instant; `atZoneSimilarLocal(zone)` cố giữ giờ địa phương nếu có thể. Đừng dùng `atZoneSimilarLocal` để hiển thị một sự kiện đã ghi cho người ở múi giờ mới.

## 7. Vì sao `atZone()` cần chú ý DST?

Khi gắn một `ZoneId` cho `LocalDateTime`, Java phải xử lý ngày giờ dựa trên **quy tắc múi giờ**. Với khu vực áp dụng giờ mùa hè:

- **Gap:** một đoạn giờ địa phương không tồn tại vì đồng hồ nhảy tiến. `atZone` mặc định đẩy thời gian địa phương về phía trước theo độ dài khoảng nhảy.
- **Overlap:** một đoạn giờ địa phương xảy ra hai lần khi đồng hồ lùi. `atZone` mặc định chọn offset sớm hơn trong overlap; ứng dụng có thể chọn offset muộn hơn.

Ví dụ tại New York (theo quy tắc DST hiện hành cho năm 2026):

~~~java
ZoneId ny = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
ZonedDateTime shifted = gap.atZone(ny);
// 2026-03-08T03:30-04:00[America/New_York]

LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
ZonedDateTime earlier = overlap.atZone(ny);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

// earlier: 2026-11-01T01:30-04:00[America/New_York]
// later:   2026-11-01T01:30-05:00[America/New_York]
~~~

Đây là các đoạn minh họa, cần import `java.time.*` trong một chương trình độc lập. Với gap, input 02:30 thành 03:30; với overlap, cùng 01:30 có thể tương ứng hai instant cách nhau một giờ. Quy tắc `ZoneRules.getValidOffsets(localDateTime)` trả về danh sách offset hợp lệ: 0 phần tử = gap, 1 = bình thường, 2 = overlap.

**Hệ quả:** `local.atZone(zone).toInstant()` là phép chuyển đúng về API, nhưng nếu đầu vào là lịch hẹn người dùng nhập ở vùng DST, nghiệp vụ cần quyết định có chấp nhận giờ bị dời hay bắt người dùng chọn rõ lần 01:30 nào. Không tự suy ra rằng mỗi `LocalDateTime` tương ứng duy nhất một `Instant`.

## 8. Những chuyển đổi dễ sai

### 8.1. Mất thông tin rồi giả định khôi phục được

~~~java
ZonedDateTime original = /* lịch hẹn có ZoneId */;
LocalDateTime localOnly = original.toLocalDateTime();
~~~

Đây là **đoạn minh họa, không phải chương trình độc lập**. `localOnly` không giữ `ZoneId`, offset hoặc lựa chọn offset trong DST overlap. Nếu chuyển ngược bằng `atZone(ZoneId.systemDefault())`, kết quả có thể là instant khác khi máy chạy ở vùng khác hoặc người dùng thay đổi vùng.

Nếu cần bảo toàn sự kiện, lưu `Instant`. Nếu cần bảo toàn “09:00 thứ Hai ở Paris”, giữ ngày giờ cục bộ, định danh vùng và quy tắc lập lịch tương ứng.

### 8.2. Dùng sai offset của một địa phương

~~~java
LocalDateTime newYorkWinter =
        LocalDateTime.of(2026, 12, 1, 9, 0);

Instant byZone = newYorkWinter
        .atZone(ZoneId.of("America/New_York"))
        .toInstant();

Instant byWrongOffset =
        newYorkWinter.toInstant(ZoneOffset.ofHours(-4));
~~~

Trong tháng 12/2026, New York sử dụng `-05:00` theo quy tắc hiện hành. Giá trị `byWrongOffset` lệch **một giờ** so với `byZone` vì caller giả định nhầm `-04:00`. Nếu được cung cấp tên khu vực, cần tra bằng `ZoneId` ở ngày giờ cụ thể.

### 8.3. Nghĩ `toLocalDate()` nghĩa là “lấy ngày theo múi giờ của người dùng”

`Instant` là thời điểm toàn cầu, không có khái niệm ngày theo địa phương. Muốn lấy **ngày người dùng nhìn thấy**, hãy làm:

~~~java
Instant createdAt = Instant.parse("2026-10-24T23:30:00Z");

LocalDate vietnamDate =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDate();

// vietnamDate = 2026-10-25
~~~

`toLocalDate()` lấy ngày của **giá trị đang có ngữ cảnh vùng**; kết quả phụ thuộc vùng đã chọn trước đó. Không thể suy ra ngày hiển thị của người dùng từ `Instant` nếu không biết vùng người dùng hoặc vùng nghiệp vụ.

### 8.4. Nhầm `parse/format` với `at/to`

`LocalDate.parse("2026-10-24")` chuyển **chuỗi có định dạng phù hợp** thành giá trị ngày. `date.format(formatter)` chuyển giá trị ngày thành **chuỗi để hiển thị**. Trong khi đó, `date.atTime(time)` tạo giá trị Java khác bằng cách ghép thông tin; `zoned.toInstant()` thay đổi mô hình biểu diễn thời gian. Việc in `toString()` hay format một giá trị **không thay thế** cho giải quyết offset/múi giờ.

### 8.5. Phụ thuộc `ZoneId.systemDefault()` ngoài ý muốn

Nếu dữ liệu gắn với múi giờ nghiệp vụ, hãy lấy `ZoneId` từ cấu hình, hồ sơ người dùng hoặc địa điểm sự kiện. Giá trị `ZoneId.systemDefault()` có thể khác giữa laptop, máy chủ và container. Cùng một `LocalDateTime` được `atZone` ở hai zone mặc định khác nhau có thể tạo hai instant khác nhau.

## 9. Quy tắc thiết kế cho dữ liệu ngày giờ

**Nhận lịch hẹn địa phương:** đọc `LocalDate`, `LocalTime` và `ZoneId` do nghiệp vụ quyết định → dùng `atTime` rồi `atZone` → kiểm tra DST → lưu instant nếu cần xác định sự kiện tuyệt đối, giữ nguyên zone/quy tắc nếu lịch tái diễn.

**Hiển thị mốc đã lưu:** đọc `Instant` → `atZone(userZone)` → format ngày giờ cho người dùng. Không sửa instant gốc chỉ để đổi timezone.

**Lọc giao dịch theo ngày địa phương:** lấy đầu ngày và đầu ngày tiếp theo bằng `LocalDate.atStartOfDay(zone).toInstant()`; truy vấn khoảng **[startInclusive, endExclusive)** để tránh bỏ sót nano giây cuối ngày hay trùng giao dịch tại ranh giới.

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate reportingDay = LocalDate.of(2026, 10, 24);

Instant startInclusive =
        reportingDay.atStartOfDay(businessZone).toInstant();
Instant endExclusive =
        reportingDay.plusDays(1).atStartOfDay(businessZone).toInstant();
~~~

**Lưu “thời gian lúc tạo”:** `Instant.now(clock)` là mốc; `Instant.atZone(...)` chỉ là hiển thị. Đừng đổi qua `LocalDateTime` rồi đoán lại vùng sau khi lưu.

**Viết test:** sử dụng ngày cố định như ví dụ, test kết quả trước/sau khi đổi vùng; test gap/overlap nếu nghiệp vụ có lịch địa phương; test ở nhiều zone khác nhau; kiểm tra rằng những phép chuyển được tuyên bố là “giữ instant” thực sự cho `toInstant()` bằng nhau. Tránh chỉ kiểm tra chuỗi `toString()` nếu mục tiêu thực là tính đúng thời điểm.

## 10. Tự luyện tập

1. Cho `LocalDate.of(2026, 10, 24)` và `LocalTime.of(9, 30)`. Viết hai cách tạo `LocalDateTime` bằng `atTime` và `atDate`; giải thích vì sao chưa có instant.
2. Cho `Instant.parse("2026-10-24T02:30:00Z")`. Hãy hiển thị giờ tại `Asia/Ho_Chi_Minh` và `Asia/Tokyo` bằng `atZone`; dùng `toInstant` chứng minh hai giá trị chỉ cùng một mốc.
3. Cho `ZonedDateTime` tại Việt Nam. So sánh `withZoneSameInstant(Asia/Tokyo)` với `withZoneSameLocal(Asia/Tokyo)`. Phép nào phù hợp khi hiển thị một giao dịch cho người Tokyo?
4. Cho lịch hẹn 09:00 ở New York ngày 01/12/2026. Vì sao dùng `LocalDateTime.toInstant(ZoneOffset.ofHours(-4))` là rủi ro?
5. Sau `zoned.toLocalDateTime()`, có thể khôi phục chắc chắn đúng instant ban đầu nếu không lưu zone/offset hay không? Xét cả DST overlap.
6. Đầu ngày 24/10 ở Việt Nam và đầu ngày 24/10 ở Tokyo có trùng instant không? Hãy dùng `atStartOfDay(zone).toInstant()` để chứng minh.

**Ghi nhớ:** `at...()` thường giúp **kết hợp hoặc đặt một giá trị trong ngữ cảnh**; `to...()` thường lấy **một biểu diễn hoặc thành phần khác**. Trước mỗi phép gọi, hãy xác định **kiểu đầu vào, kiểu trả về, thông tin được bổ sung/bị loại và việc instant có được giữ nguyên không**. Với `LocalDateTime`, chỉ khi đã có offset hoặc quy tắc `ZoneId` thích hợp mới suy ra một mốc tuyệt đối trên dòng thời gian.