# LocalTime và giờ trong ngày trong Java

## 1. Mục tiêu: biểu diễn giờ trên đồng hồ, không phải một thời điểm tuyệt đối

`java.time.LocalTime` là lớp **bất biến (immutable), thread-safe** biểu diễn **giờ trong ngày** theo hệ đồng hồ 24 giờ: giờ, phút, giây và nano giây. Một giá trị như `09:30` hoặc `23:59:59.999999999` **không có ngày, không có múi giờ và không có UTC offset**. Java giới thiệu `LocalTime` trong Java 8, và đây vẫn là lựa chọn hiện hành trong API `java.time`.

Khi thiết kế phần mềm, cách phân biệt này rất quan trọng:

- **“Cửa hàng mở lúc 08:30 mỗi ngày”** → `LocalTime` là mô hình phù hợp cho *giờ lịch lặp lại*.
- **“Cuộc họp ngày 2026-03-15 bắt đầu lúc 08:30 tại Hà Nội”** → cần ít nhất **ngày, giờ và múi giờ**; dùng `LocalDateTime` kèm `ZoneId` hoặc `ZonedDateTime` theo quy tắc miền dữ liệu.
- **“Sự kiện xảy ra chính xác tại thời điểm nào trên timeline?”** → dùng `Instant`, có thể hiển thị bằng `ZonedDateTime` cho người dùng.
- **“Một tác vụ kéo dài 90 phút”** → dùng `Duration` (độ dài), không dùng `LocalTime` làm bộ đếm thời gian.
- **“Giờ hiện tại trên đồng hồ của người dùng”** → lấy `LocalTime.now(clock)` với `Clock`/`ZoneId` thích hợp, đặc biệt để test được.

Bài này tập trung vào **LocalTime và giờ trong ngày**: tạo, đọc, định dạng, phân tích chuỗi, so sánh, tính toán vòng qua 24 giờ, khoảng giờ, cách kết hợp với ngày/múi giờ, xử lý dữ liệu không hợp lệ và kiểm thử. Các API được mô tả vẫn áp dụng trong Java hiện đại. Chương trình đầy đủ chạy với **JDK 17+**; không cần thư viện ngày giờ cũ như `java.util.Date` hay `Calendar` để giải quyết những bài toán này.

## 2. Giới hạn giá trị và độ chính xác

Mỗi `LocalTime` có bốn thành phần:

| Thành phần | Miền giá trị hợp lệ | API đọc |
| --- | --- | --- |
| Giờ theo đồng hồ 24h | `0..23` | `getHour()` |
| Phút trong giờ | `0..59` | `getMinute()` |
| Giây trong phút | `0..59` | `getSecond()` |
| Nano giây trong giây | `0..999_999_999` | `getNano()` |

`LocalTime` hỗ trợ **độ chính xác biểu diễn tới nano giây**, nhưng điều đó **không** có nghĩa nguồn đồng hồ hệ thống, cơ sở dữ liệu hay cảm biến thực tế chính xác đến một nano giây. Độ chính xác được lưu và độ chính xác của dữ liệu đo là hai chuyện khác nhau.

Các hằng số chuẩn:

```java
LocalTime.MIN      // 00:00
LocalTime.MIDNIGHT // 00:00
LocalTime.NOON     // 12:00
LocalTime.MAX      // 23:59:59.999999999
```

`LocalTime.MIN.equals(LocalTime.MIDNIGHT)` là `true`. `MAX` **không phải** `24:00`. Không có biểu diễn hợp lệ cho “giờ 24” trong `LocalTime.of(24, 0)`; nếu nghiệp vụ dùng `24:00` để chỉ **nửa đêm ở cuối ngày**, hãy mô hình bằng **ngày hôm sau lúc 00:00** hoặc quy ước ranh giới riêng, không cố nhét vào một `LocalTime`.

Giá trị giây `60` cũng không hợp lệ trong `LocalTime.of(...)`; `LocalTime` là giờ dân dụng theo quy tắc của API, không phải cấu trúc dữ liệu để biểu diễn trực tiếp giây nhuận.

**LocalTime là value-based class.** Không nên dùng `==` để kiểm tra bằng nhau, không đồng bộ bằng `synchronized(time)` và không dựa vào object identity/cache của JVM. Dùng `equals`, `compareTo`, `isBefore`, `isAfter`.

## 3. Tạo LocalTime theo nguồn dữ liệu

### 3.1. `of(...)` với các thành phần số

Các factory thông dụng:

```java
LocalTime opening = LocalTime.of(8, 30);                // 08:30
LocalTime appointment = LocalTime.of(14, 5, 10);       // 14:05:10
LocalTime precise = LocalTime.of(9, 8, 7, 125_000_000); // 09:08:07.125
```

Đoạn này dùng `import java.time.LocalTime;`. Phương thức overload theo thứ tự **hour, minute, second, nanoOfSecond**; không phải millisecond ở đối số cuối. Ví dụ `125_000_000` nano giây = **125 millisecond**.

Khi thành phần vượt miền hợp lệ, Java ném một subtype của `DateTimeException`. Ví dụ:

```java
LocalTime.of(24, 0); // DateTimeException: hour ngoài 0..23
LocalTime.of(12, 60); // DateTimeException: minute ngoài 0..59
```

Đây là **đoạn minh họa lỗi có chủ đích**, không chạy chung với ví dụ happy path.

Nếu nhận input từ API hoặc form, nên xác thực định dạng và miền giá trị theo hợp đồng thay vì dựa vào một số giả định như “24:00 chắc Java chấp nhận”.

### 3.2. Từ số giây hoặc số nano giây tính từ đầu ngày

```java
LocalTime fromSeconds = LocalTime.ofSecondOfDay(34_200); // 09:30
LocalTime fromNanos = LocalTime.ofNanoOfDay(
        9L * 3_600_000_000_000L + 30L * 60_000_000_000L);
// 09:30
```

Đây là đoạn minh họa trong một method Java, không phải thao tác với Unix epoch. Giá trị đầu vào có ý nghĩa **đã trôi qua bao nhiêu đơn vị từ 00:00 cùng ngày**, không phải số giây từ năm 1970.

| API | Miền hợp lệ |
| --- | --- |
| `ofSecondOfDay(seconds)` | `0..86_399` |
| `ofNanoOfDay(nanos)` | `0..86_399_999_999_999` |
| `toSecondOfDay()` | Trả `int` trong `0..86_399` |
| `toNanoOfDay()` | Trả `long` trong `0..86_399_999_999_999` |

`toSecondOfDay()` **bỏ phần nano giây**. Nếu so sánh các thời điểm trong ngày chính xác đến nano giây, dùng `LocalTime.compareTo` hoặc `toNanoOfDay` thay vì chỉ so `toSecondOfDay`.

**Lỗi đơn vị:** Không lấy số Unix timestamp (epoch milliseconds/seconds) đưa thẳng vào `ofSecondOfDay`. Timestamp tuyệt đối cần được giải bằng `Instant` và múi giờ:

```java
Instant eventInstant = Instant.parse("2026-03-01T00:30:00Z");
LocalTime wallTime = LocalTime.ofInstant(
        eventInstant, ZoneId.of("Asia/Ho_Chi_Minh"));
// 07:30
```

Đoạn minh họa này cần `import java.time.*;`. `wallTime` chỉ là **giờ hiển thị trong ngày** sau chuyển múi giờ; nếu cần truy nguyên event, vẫn lưu `Instant` hoặc thông tin ngày/múi giờ phù hợp.

### 3.3. Lấy giờ hiện tại

```java
LocalTime machineDefault = LocalTime.now();
LocalTime inVietnam = LocalTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
```

- `now()` dùng clock và **múi giờ mặc định của JVM**, nên kết quả có thể khác giữa máy dev, server và container.
- `now(ZoneId)` sử dụng múi giờ đã chỉ định, rõ ràng hơn khi nghiệp vụ gắn với khu vực.
- `now(Clock)` nhận nguồn thời gian có thể thay thế, **rất phù hợp với unit test**.

Không hardcode `ZoneId.systemDefault()` nếu ứng dụng cần giờ của một địa điểm cụ thể mà server có thể chạy ở múi giờ khác.

## 4. LocalTime là bất biến: thao tác luôn trả giá trị mới

Không có `setHour(...)` thay đổi object cũ tại chỗ. Các phương thức `withHour`, `withMinute`, `withSecond`, `withNano`, `plus...`, `minus...`, `truncatedTo` đều trả một đối tượng `LocalTime` mô tả kết quả.

```java
LocalTime base = LocalTime.of(9, 15);

LocalTime changedHour = base.withHour(11); // 11:15
LocalTime shifted = base.plusMinutes(20);  // 09:35

// base vẫn là 09:15.
```

Điểm này giúp code dễ lý luận hơn khi dùng chung giữa các thread: `LocalTime` immutable và thread-safe. Tuy nhiên nếu nhiều thread cùng sửa **một biến tham chiếu** trỏ đến LocalTime, vẫn cần thiết kế đồng bộ phù hợp; tính bất biến của object không tự làm cập nhật biến tham chiếu thành transaction.

### 4.1. Cộng trừ giờ, phút, giây và nano

```java
LocalTime t = LocalTime.of(23, 50);
LocalTime later = t.plusMinutes(20);    // 00:10
LocalTime earlier = t.minusHours(2);    // 21:50

LocalTime nanoRollover = LocalTime.MAX.plusNanos(1);
// 00:00
```

**Điều bắt buộc hiểu:** Cộng/trừ trên `LocalTime` **quay vòng trong một ngày 24 giờ**. `23:50.plusMinutes(20)` trả `00:10` nhưng **không mang thông tin ngày hôm sau**. Trên màn hình chỉ giờ trong ngày, điều này có thể đúng; với deadline, lịch họp, thanh toán hoặc log cần giữ ngày, hãy thao tác trên `LocalDateTime`/`ZonedDateTime` thay vì làm mất ngày.

Ví dụ khác:

```java
LocalTime.of(8, 0).plusHours(24);  // 08:00
LocalTime.of(8, 0).plusMinutes(90); // 09:30
LocalTime.of(0, 5).minusMinutes(10); // 23:55
```

Số giờ/phút lớn được quy về vòng 24 giờ theo API. Nhưng đừng dùng kết quả `plusHours(48)` để suy luận “hai ngày đã đi qua”: thông tin ngày đã bị loại bỏ.

### 4.2. Đổi một thành phần không tương đương cộng vào thành phần đó

`withHour(10)` nghĩa là **đặt giờ thành 10** và giữ phút/giây/nano, còn `plusHours(10)` nghĩa là **cộng 10 giờ** (có thể quay vòng):

```java
LocalTime input = LocalTime.of(9, 30);
LocalTime settingHour = input.withHour(10); // 10:30
LocalTime addingHours = input.plusHours(10); // 19:30
```

Nếu input đến từ biểu mẫu sửa “giờ”, thường cần `withHour` hoặc tạo lại LocalTime; nếu input đến từ nhu cầu “sau 90 phút”, thường cần `plusMinutes` hoặc mô hình ngày giờ đầy đủ tùy bài toán.

### 4.3. Làm tròn khác với cắt phần nhỏ

`truncatedTo(ChronoUnit.MINUTES)` **loại bỏ** giây và nano giây, không làm tròn về phút gần nhất:

```java
LocalTime precise = LocalTime.of(9, 8, 59, 999_000_000);
LocalTime truncated = precise.truncatedTo(ChronoUnit.MINUTES);
// 09:08, không phải 09:09.
```

Nếu nghiệp vụ cần làm tròn theo quy tắc 5 phút, 15 phút hoặc một giờ, hãy định nghĩa riêng chính sách làm tròn và kiểm soát các trường hợp chạm ranh giới 00:00 / ngày hôm sau. Đừng đổi ý nghĩa `truncatedTo` thành “round”.

### 4.4. TemporalUnit: chỉ những đơn vị phù hợp

`LocalTime.plus(amount, unit)` và `truncatedTo(unit)` làm việc với các đơn vị thời gian được hỗ trợ (giờ, phút, giây, nano và những đơn vị chia đều ngày phù hợp). Không dùng `LocalTime.plus(1, ChronoUnit.DAYS)` với kỳ vọng nó mang ngày: `LocalTime` không lưu ngày. Nếu cần cộng ngày/tháng/năm, hãy đưa ngày vào kiểu dữ liệu.

## 5. Parse chuỗi giờ: không dựa vào đoán định dạng

### 5.1. ISO_LOCAL_TIME mặc định

`LocalTime.parse(text)` sử dụng formatter ISO local time. Các chuỗi thường hợp lệ:

```java
LocalTime.parse("08:30");                // 08:30
LocalTime.parse("08:30:15");             // 08:30:15
LocalTime.parse("08:30:15.123456789");   // nano precision
```

Các chuỗi không phù hợp với formatter mặc định có thể bị `DateTimeParseException`:

```java
LocalTime.parse("8:30");  // Không khớp ISO mặc định cần giờ hai chữ số
LocalTime.parse("24:00"); // Không phải giờ LocalTime hợp lệ
LocalTime.parse("25:10"); // Giờ ngoài miền
```

Đây là **anti-example cố ý gây lỗi**, không phải hướng dẫn chạy nối tiếp không có xử lý lỗi.

**Ghi chú về `24:00`:** Một số tiêu chuẩn hoặc hệ thống có ký hiệu `24:00` cho **kết thúc ngày**. `LocalTime` không đại diện giờ 24, và `LocalTime.parse("24:00")` mặc định từ chối. Một `DateTimeFormatter` tùy chỉnh với resolver style khác có thể có chính sách normalize khác; đừng dùng sự khác biệt đó để suy luận mọi đầu vào `24:00` đều hợp lệ theo nghiệp vụ. Khi ý nghĩa là “00:00 ngày kế tiếp”, cần giữ **thông tin ngày**.

### 5.2. Định dạng theo biểu mẫu

`DateTimeFormatter` là formatter immutable, thread-safe. Ví dụ:

```java
DateTimeFormatter twentyFour =
        DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);

String display = LocalTime.of(15, 7).format(twentyFour);
// "15:07"

LocalTime parsed = LocalTime.parse("15:07", twentyFour);
// 15:07
```

Các ký tự pattern thường gặp:

| Pattern | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `HH` | Giờ trong ngày (0–23), 2 chữ số | `09`, `23` |
| `H` | Giờ trong ngày (0–23), tối thiểu 1 chữ số | `9`, `23` |
| `mm` | Phút 2 chữ số | `05` |
| `ss` | Giây 2 chữ số | `07` |
| `SSS` | Phần giây, ba chữ số | `125` cho 125 ms |
| `hh` | Giờ theo đồng hồ 12 giờ, 01–12 | `03` |
| `a` | Ký hiệu AM/PM theo locale | `AM`, `PM` |

Đồng hồ 12 giờ:

```java
DateTimeFormatter twelve = DateTimeFormatter.ofPattern(
        "hh:mm a", Locale.ENGLISH);

String text = LocalTime.of(15, 7).format(twelve);
// "03:07 PM"

LocalTime value = LocalTime.parse("03:07 PM", twelve);
// 15:07
```

**Đừng nhầm `HH` và `hh`**: khi có `hh`, dữ liệu còn cần quy tắc AM/PM. `DateTimeFormatter.ofPattern("HH:mm")` không chứa múi giờ, vì bản thân `LocalTime` không có múi giờ.

### 5.3. Phân tích chuỗi từ UI/API là một bước xác thực

Giả sử API nhận chuỗi giờ “9:30”, “09:30” hoặc “09:30:00”. Phải quyết định **định dạng đầu vào cho phép** trước. Nếu hợp đồng cho đúng `HH:mm`, hãy parse bằng formatter đó và xử lý lỗi. Không tự trim/sửa/đoán mọi chuỗi nếu có thể khiến dữ liệu không hợp lệ trở thành hợp lệ sai ý nghĩa.

Ví dụ xử lý lỗi:

```java
try {
    LocalTime input = LocalTime.parse("25:10");
    System.out.println(input);
} catch (DateTimeParseException ex) {
    System.out.println("Giờ nhập không hợp lệ");
}
```

Đây là đoạn trong method đã import `java.time.*` và `java.time.format.*`. Trong hệ thống thật, **không in chính thông điệp lỗi của JVM như một hợp đồng API**, vì chi tiết văn bản có thể khác theo JDK. Thay vào đó trả lỗi validation chuẩn của ứng dụng.

### 5.4. Độ chính xác hiển thị không đồng nghĩa độ chính xác lưu trữ

Một `LocalTime` có nano giây khác 0 có thể được hiển thị thành “09:08” bằng `HH:mm`, nhưng object **vẫn giữ giây và nano**. Nếu mục đích thực sự là chuẩn hóa chỉ đến phút, dùng `truncatedTo(ChronoUnit.MINUTES)`; nếu chỉ hiển thị ngắn, **chỉ format** là đủ.

Đừng lấy `format("HH:mm")` rồi parse lại để làm phép tính chỉ vì “mất giây”. Việc mất độ chính xác nên là một **quyết định nghiệp vụ có chủ đích**.

## 6. So sánh và sắp xếp giờ trong cùng một ngày

`LocalTime` triển khai `Comparable<LocalTime>`. Nó so thứ tự theo **giờ trong ngày**, rồi phút, giây, nano:

```java
LocalTime morning = LocalTime.of(8, 30);
LocalTime afternoon = LocalTime.of(15, 0);

boolean before = morning.isBefore(afternoon); // true
boolean after = afternoon.isAfter(morning);   // true
boolean same = morning.equals(LocalTime.of(8, 30)); // true
int direction = morning.compareTo(afternoon); // số âm
```

`isBefore` và `isAfter` đều là **strict**, nên khi hai giờ giống nhau, cả hai trả false. Nếu muốn so có cả biên bằng, dùng `!a.isAfter(b)` / `!a.isBefore(b)` theo điều kiện rõ ràng.

Sắp danh sách:

```java
List<LocalTime> times = List.of(
        LocalTime.of(15, 0), LocalTime.of(8, 30));
List<LocalTime> ordered = times.stream().sorted().toList();
// [08:30, 15:00]
```

Đoạn này dùng Java 17+ với `Stream.toList()`. `LocalTime` bất biến nên có thể dùng làm phần tử trong List/Set/Map khi phù hợp, nhưng **nó không mang thông tin ngày**: `23:00` đứng sau `01:00` theo thứ tự giờ trong một ngày, kể cả trong một ca thực tế kéo qua nửa đêm.

**Bẫy nghiệp vụ:** Không dùng `LocalTime.isAfter(...)` để suy luận một sự kiện có thời gian sau sự kiện khác nếu chúng có thể nằm ở **hai ngày khác nhau**. Phải xét ngày và múi giờ, đặc biệt khi có DST.

### 6.1. Chú ý tới nano giây trong so sánh

`LocalTime.of(9,30,0,1)` đứng **sau** `LocalTime.of(9,30,0,0)`, dù cả hai đều có `toSecondOfDay()==34200`. Nếu hệ thống chỉ quan tâm tới phút, chuẩn hóa về phút trước khi so sánh hoặc dùng một policy làm tròn có kiểm soát.

## 7. Một khoảng giờ trong ngày: biên [start, end) và nửa đêm

Các quy tắc “mở cửa từ 09:00 đến 17:00” thường là **khoảng nửa mở**:

- **Bao gồm** giờ bắt đầu.
- **Không bao gồm** giờ kết thúc.

Lý do: hai ca liền kề `[09:00,12:00)` và `[12:00,17:00)` không tranh nhau điểm ranh giới `12:00`.

### 7.1. Khoảng không đi qua nửa đêm

```java
LocalTime start = LocalTime.of(9, 0);
LocalTime end = LocalTime.of(17, 0);
LocalTime now = LocalTime.NOON;

boolean open = !now.isBefore(start) && now.isBefore(end);
// true
```

Điều kiện trên chỉ đúng khi `start < end` và đã quyết định rằng ngày hiện tại là ngày hoạt động hợp lệ (không xét ngày nghỉ hay ngày trong tuần).

### 7.2. Khoảng đi qua nửa đêm

“Ca đêm từ 22:00 đến 06:00” không thể kiểm tra bằng một điều kiện `start <= now < end` thông thường, bởi `22:00 > 06:00` theo thứ tự LocalTime.

Với **một quy tắc giờ lặp lại hằng ngày**, có thể định nghĩa:

```java
static boolean inHalfOpenWindow(LocalTime now,
                                LocalTime start,
                                LocalTime end) {
    Objects.requireNonNull(now);
    Objects.requireNonNull(start);
    Objects.requireNonNull(end);

    // Chính sách của ví dụ: start==end là khoảng rỗng, KHÔNG phải 24 giờ.
    if (start.equals(end)) {
        return false;
    }
    if (start.isBefore(end)) {
        return !now.isBefore(start) && now.isBefore(end);
    }
    // Khoảng qua 00:00: [start, 24:00) U [00:00, end)
    return !now.isBefore(start) || now.isBefore(end);
}
```

Đây là **đoạn method** nằm trong chương trình hoàn chỉnh ở mục 12, cần `import java.util.Objects;`.

| Khoảng | Giờ kiểm tra | Kết quả |
| --- | --- | --- |
| `[09:00,17:00)` | `12:00` | `true` |
| `[09:00,17:00)` | `17:00` | `false` |
| `[22:00,06:00)` | `23:00` | `true` |
| `[22:00,06:00)` | `05:59` | `true` |
| `[22:00,06:00)` | `06:00` | `false` |
| `[22:00,06:00)` | `12:00` | `false` |
| `[08:00,08:00)` | bất kỳ | `false` theo chính sách ví dụ |

**Điểm quan trọng:** `start == end` có thể biểu diễn “khoảng rỗng” hoặc “mở 24 giờ” tùy sản phẩm. Hai nghĩa này **không thể phân biệt chỉ bằng hai LocalTime bằng nhau**. Nếu quy tắc “24/7” là hợp lệ, nên dùng một flag/trạng thái riêng hoặc policy được ghi rõ. Không tự đổi điều kiện `start==end` thành true cho mọi giờ.

### 7.3. Quy tắc theo ngày trong tuần và ngày nghỉ

Hàm trên chỉ xét **giờ trong ngày**. Nó **không tự quyết định** hôm nay cửa hàng có mở không. Nếu thứ Hai–Sáu có giờ khác thứ Bảy, hoặc có ngày nghỉ đặc biệt, cần đưa vào mô hình:

- Ngày đang xét theo `LocalDate` hoặc `ZonedDateTime`.
- Chính sách lịch lặp lại theo `DayOfWeek`.
- Ngày lễ/ngày đóng cửa ngoại lệ.
- Múi giờ cửa hàng để xác định ngày giờ địa phương từ `Instant`.

Ví dụ một ca `22:00–06:00` bắt đầu thứ Sáu và kết thúc thứ Bảy. Cần quyết định **ngày của ca** là ngày bắt đầu hay ngày kết thúc để áp chính sách lịch. `LocalTime` một mình không đủ.

## 8. Duration.between và bài toán đi qua nửa đêm

### 8.1. Hai LocalTime không thể tự nói một ngày đã qua

`Duration.between(start, end)` có thể nhận hai `LocalTime`, nhưng vì cả hai không chứa ngày, kết quả phản ánh sự chênh lệch theo **hai thời điểm trong cùng một mô hình 24 giờ**, không tự đoán ngày kế tiếp.

```java
LocalTime start = LocalTime.of(23, 50);
LocalTime end = LocalTime.of(0, 10);

long minutes = Duration.between(start, end).toMinutes();
// -1420, KHÔNG tự trở thành 20.
```

Vì theo thứ tự đồng hồ cùng ngày, `00:10` nằm **trước** `23:50`.

### 8.2. Nếu biết sự kiện kết thúc vào ngày hôm sau, giữ ngày

```java
LocalDate date = LocalDate.of(2026, 1, 1);

LocalDateTime startAt = start.atDate(date);
LocalDateTime endAt = end.atDate(date.plusDays(1));
long minutes = Duration.between(startAt, endAt).toMinutes();
// 20
```

Đây là đoạn minh họa tiếp nối `start` và `end` đã khai báo ở trên. `atDate(date)` tạo một `LocalDateTime` gồm ngày và giờ, vì vậy phép chênh lệch có căn cứ ngày.

**Lưu ý quan trọng:** Ví dụ này tính theo **ngày giờ cục bộ không múi giờ**. Trong một khu vực có chuyển giờ mùa (DST), “20 phút trên đồng hồ” không luôn bằng “20 phút elapsed theo timeline” khi thời gian đi qua khoảng thay đổi offset. Nếu cần thời gian thực trôi qua, hãy gắn múi giờ, giải các tình huống giờ bị thiếu/trùng, rồi so bằng `Instant` hoặc `ZonedDateTime` thích hợp.

### 8.3. Khi chỉ muốn “số phút đi tới trong chu kỳ 24h”

Đối với một **mô hình thuần đồng hồ 24h** (ví dụ tính số phút từ giờ bắt đầu đến giờ kết thúc trong chu kỳ kế tiếp, giả định không có DST):

```java
static long forwardMinutes(LocalTime start, LocalTime end) {
    long from = start.toSecondOfDay() / 60;
    long to = end.toSecondOfDay() / 60;
    return Math.floorMod(to - from, 24L * 60);
}
```

Đây là đoạn minh họa cố ý **giảm độ chính xác xuống phút** và cho `start==end` thành 0 phút. Nó chỉ phù hợp khi đầu vào đã được **chuẩn hóa đến phút**, và nghiệp vụ định nghĩa khoảng đi tới nhỏ hơn 24 giờ. Nếu có giây/nano, dùng đơn vị phù hợp; nếu có ngày/múi giờ thực tế, dùng date-time đầy đủ.

Đừng dùng `Math.abs(Duration.between(start,end).toMinutes())` để “sửa” ca qua nửa đêm. Nó làm mất dấu và không cho kết quả 20 phút trong ví dụ 23:50–00:10.

## 9. LocalTime, LocalDateTime, OffsetTime, ZonedDateTime, Instant: chọn đúng kiểu

| Kiểu | Chứa thông tin | Tình huống phù hợp |
| --- | --- | --- |
| `LocalTime` | Giờ:phút:giây:nano | Mốc giờ trong ngày, giờ mở cửa, giờ hẹn lặp lại |
| `LocalDate` | Ngày, không có giờ | Ngày sinh, ngày làm việc, lịch theo ngày |
| `LocalDateTime` | Ngày + giờ cục bộ, **không** zone/offset | Ý định lịch cục bộ trước khi xác định múi giờ |
| `OffsetTime` | Giờ trong ngày + UTC offset, **không có ngày** | Giao thức cần offset + giờ, không cần ngày |
| `OffsetDateTime` | Ngày + giờ + offset | Dữ liệu có offset rõ trong giao thức/API |
| `ZonedDateTime` | Ngày + giờ + `ZoneId` với quy tắc zone | Lịch gắn một khu vực địa lý, quy tắc DST |
| `Instant` | Thời điểm tuyệt đối trên timeline | Event log, timestamp, lưu trữ thời điểm |

**Một LocalTime không tự suy ra một Instant.** Để xác định một thời điểm tuyệt đối từ giờ địa phương, cần **ngày** và **thông tin zone/offset đủ để giải**. Nếu DST làm một giờ địa phương không tồn tại hoặc lặp lại hai lần, đôi khi còn phải xác định **chính sách giải mơ hồ**.

### 9.1. Từ LocalTime và LocalDate đến LocalDateTime

```java
LocalTime opening = LocalTime.of(8, 30);
LocalDate date = LocalDate.of(2026, 4, 1);

LocalDateTime planned = opening.atDate(date);
// 2026-04-01T08:30
```

Lời gọi `atDate` **không tự gắn múi giờ**. `planned` vẫn là thời gian cục bộ. Để gắn zone:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime scheduled = planned.atZone(zone);
Instant when = scheduled.toInstant();
```

Các đoạn trên trong một method đã import `java.time.*`. Với các khu vực áp dụng DST, một `LocalDateTime` có thể nằm trong gap/overlap khi thêm zone; `atZone` có quy tắc giải mặc định. Nếu hệ thống xử lý lịch vận hành hay tài chính cần độ chính xác cao, xác định chính sách gap/overlap theo nghiệp vụ và kiểm thử theo tzdb, đừng mặc định mọi giờ địa phương đều tồn tại duy nhất.

### 9.2. Không dùng LocalTime để so sự kiện ở nhiều múi giờ

Hai người cùng nhìn đồng hồ `09:00` ở hai múi giờ không nhất thiết đang ở cùng thời điểm. Khi so thứ tự toàn cục của sự kiện, chuyển sang `Instant`. Lưu `LocalTime` đơn lẻ trong database để biểu diễn **thời điểm tạo giao dịch** sẽ làm mất ngày và offset, dẫn tới nhầm lẫn khi log/đối soát.

### 9.3. LocalTime không lưu DST nhưng không làm DST biến mất

Một cuộc hẹn “02:30 mỗi ngày” hợp lệ như **một ý định LocalTime**, nhưng ở một số khu vực/ngày DST, giờ 02:30 **không tồn tại hoặc không duy nhất**. Khi thực thi lịch, kết hợp `LocalDate`, `LocalTime` và `ZoneId` rồi áp chính sách của hệ thống (dịch giờ, bỏ lượt, chọn offset...). `LocalTime` tự nó không thể ra quyết định này.

## 10. Clock và khả năng kiểm thử: tránh phụ thuộc thời gian hệ thống

Nếu code gọi trực tiếp `LocalTime.now()` ở nhiều nơi, test sẽ phụ thuộc thời điểm chạy và cấu hình zone của server. `java.time.Clock` cho phép đưa nguồn thời gian vào logic, đáp ứng yêu cầu kiểm thử **deterministic**.

Ví dụ dùng clock cố định:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = Instant.parse("2026-03-01T00:30:00Z");
Clock fixed = Clock.fixed(instant, zone);

LocalTime actual = LocalTime.now(fixed);
// 07:30
```

Với giờ Việt Nam trong ví dụ, UTC 00:30 đổi sang giờ địa phương 07:30 (UTC+07:00). Không dựa vào máy thật, nên output luôn dự đoán được. `Clock.fixed` là API hiện hành dùng rộng rãi cho test.

Trong mã production, có thể inject `Clock` qua constructor:

```java
final class DailyCutoff {
    private final Clock clock;
    private final LocalTime deadline;

    DailyCutoff(Clock clock, LocalTime deadline) {
        this.clock = Objects.requireNonNull(clock);
        this.deadline = Objects.requireNonNull(deadline);
    }

    boolean passed() {
        return !LocalTime.now(clock).isBefore(deadline);
    }
}
```

Đây là **lớp minh họa** cần `import java.time.*;` và `import java.util.Objects;`. Nó chỉ phù hợp với cutoff **trong cùng ngày đã được xác định theo lịch**. Nếu yêu cầu là “sau deadline hôm qua nhưng trước deadline hôm nay”, hoặc ca qua nửa đêm, chỉ so `LocalTime` như trên là không đủ; cần dữ liệu ngày/zone.

**Lưu ý:** `Clock.systemDefaultZone()` mang phụ thuộc cấu hình môi trường. Đối với hệ thống multi-tenant/đa khu vực, xác định ZoneId theo từng user/địa điểm trước khi lấy giờ.

## 11. Dùng LocalTime với dữ liệu lưu trữ, JSON và form

### 11.1. Database: SQL TIME không chứa ngày

Một cột kiểu SQL `TIME` thường có ngữ nghĩa giờ trong ngày (tùy hệ quản trị và dialect). `LocalTime` có thể là kiểu Java phù hợp khi dữ liệu thực sự là giờ trong ngày, nhưng cần kiểm tra cách JDBC driver/ORM mapping, precision, timezone conversion và serialization của hệ thống cụ thể.

**Đừng mặc định:** mọi SQL `TIME` đều có cùng độ chính xác nano, hoặc mọi driver giữ nguyên nanoseconds. Một số cơ sở dữ liệu chỉ lưu microseconds, milliseconds hoặc giây. Kiểm thử round-trip bằng dữ liệu biên như `09:08:07.123456789`.

Một thiết kế schema minh bạch thường phân biệt:

- `opening_time` / `daily_cutoff`: giờ lặp lại, có thể dùng LocalTime.
- `created_at` / `executed_at`: thời điểm thực, cần timestamp/Instant cùng chiến lược zone.
- `scheduled_local_date` + `scheduled_local_time` + `zone_id`: ý định lịch của một địa điểm.

### 11.2. JSON: quy định rõ định dạng hợp đồng

Ví dụ một API có thể trao đổi `"09:30"` hoặc `"09:30:15"` theo ISO. Cần quy định có cho phép giây/phần nano hay không, có cho phép thiếu số 0 ở đầu không, và liệu formatter nào dùng để parse. Thư viện JSON/ORM có thể có module/serializer riêng cho `java.time` — kiểm tra cấu hình của ứng dụng, không tự giả định một định dạng thống nhất trên mọi framework.

Một DTO giữ `LocalTime` sẽ không chứa zone; nếu API cần so sánh thời gian giữa nhiều khu vực, phải đưa ngày và zone/offset vào model thay vì chỉ gửi `"09:30"`.

### 11.3. Input hợp lệ nhưng không hợp lệ theo nghiệp vụ

`LocalTime.of(3, 0)` hợp lệ về mặt Java. Nhưng nếu lịch hẹn chỉ cho phép `08:00–17:00` và bước 15 phút, cần validate **quy tắc nghiệp vụ** riêng. Ví dụ:

```java
LocalTime t = LocalTime.of(9, 30);
boolean quarterHour = t.getMinute() % 15 == 0
        && t.getSecond() == 0 && t.getNano() == 0;
```

Đoạn này cho `true` với `09:30`. Nếu doanh nghiệp chỉ cho lịch hẹn vào thứ Hai–Sáu, xác thực ngày và lịch cần `LocalDate`; `LocalTime` không có khái niệm thứ trong tuần.

## 12. Chương trình Java 17+ hoàn chỉnh: tạo, parse, qua nửa đêm, Clock

Tạo tệp **`LocalTimeGuideDemo.java`** với nội dung sau. Chương trình không gọi `LocalTime.now()` theo đồng hồ thực trong các assertion, nên stdout ổn định.

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;
import java.util.*;

public class LocalTimeGuideDemo {
    static void require(boolean condition, String what) {
        if (!condition) {
            throw new AssertionError(what);
        }
    }

    // Quy tắc cho KHOẢNG GIỜ LẶP LẠI HẰNG NGÀY: [start, end).
    // start == end được định nghĩa là khoảng rỗng.
    static boolean inHalfOpenWindow(LocalTime now,
                                    LocalTime start, LocalTime end) {
        Objects.requireNonNull(now);
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);

        if (start.equals(end)) {
            return false;
        }
        if (start.isBefore(end)) {
            return !now.isBefore(start) && now.isBefore(end);
        }
        return !now.isBefore(start) || now.isBefore(end);
    }

    public static void main(String[] args) {
        LocalTime start = LocalTime.of(23, 50);
        LocalTime rollover = start.plusMinutes(20);

        require(start.equals(LocalTime.of(23, 50)), "immutable");
        require(rollover.equals(LocalTime.of(0, 10)), "rollover");
        System.out.println("original=" + start);
        System.out.println("plus20=" + rollover);
        System.out.println("maxPlusNano=" +
                LocalTime.MAX.plusNanos(1));

        LocalTime detailed = LocalTime.of(9, 8, 7, 125_000_000);
        DateTimeFormatter precise = DateTimeFormatter.ofPattern(
                "HH:mm:ss.SSS", Locale.ROOT);
        System.out.println("detailed=" + detailed.format(precise));
        require(LocalTime.parse("09:08:07.125", precise).equals(detailed),
                "parse fraction");

        DateTimeFormatter twelve = DateTimeFormatter.ofPattern(
                "hh:mm a", Locale.ENGLISH);
        String formatted = LocalTime.of(15, 7).format(twelve);
        require(LocalTime.parse(formatted, twelve)
                        .equals(LocalTime.of(15, 7)),
                "12 hour roundtrip");
        System.out.println("twelveHour=" + formatted);

        System.out.println("minuteTruncated=" +
                detailed.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("secondOfDay=" +
                LocalTime.of(9, 30).toSecondOfDay());
        System.out.println("fromSecondOfDay=" +
                LocalTime.ofSecondOfDay(34_200));
        System.out.println("minEqualsMidnight=" +
                LocalTime.MIN.equals(LocalTime.MIDNIGHT));

        System.out.println("overnightAt2300=" +
                inHalfOpenWindow(LocalTime.of(23, 0),
                        LocalTime.of(22, 0), LocalTime.of(6, 0)));
        System.out.println("overnightAt0559=" +
                inHalfOpenWindow(LocalTime.of(5, 59),
                        LocalTime.of(22, 0), LocalTime.of(6, 0)));
        System.out.println("overnightAt0600=" +
                inHalfOpenWindow(LocalTime.of(6, 0),
                        LocalTime.of(22, 0), LocalTime.of(6, 0)));
        System.out.println("daytimeAt1200=" +
                inHalfOpenWindow(LocalTime.NOON,
                        LocalTime.of(9, 0), LocalTime.of(17, 0)));
        System.out.println("equalBoundsEmpty=" +
                inHalfOpenWindow(LocalTime.NOON,
                        LocalTime.of(8, 0), LocalTime.of(8, 0)));

        long naive = Duration.between(start, rollover).toMinutes();
        LocalDate date = LocalDate.of(2026, 1, 1);
        LocalDateTime atStart = start.atDate(date);
        LocalDateTime atEnd = rollover.atDate(date.plusDays(1));
        long actual = Duration.between(atStart, atEnd).toMinutes();
        require(naive == -1420 && actual == 20, "cross midnight");
        System.out.println("durationSameDate=" + naive);
        System.out.println("durationWithDates=" + actual);
        System.out.println("endWithDate=" + atEnd);

        Clock clock = Clock.fixed(
                Instant.parse("2026-03-01T00:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("fixedClockLocalTime=" +
                LocalTime.now(clock));

        List<LocalTime> sorted = List.of(
                LocalTime.of(15, 0), LocalTime.of(8, 30))
                .stream().sorted().toList();
        System.out.println("sorted=" + sorted);

        boolean invalid = false;
        try {
            LocalTime.of(24, 0);
        } catch (DateTimeException ex) {
            invalid = true;
        }
        require(invalid, "invalid hour");
        System.out.println("invalidHourRejected=" + invalid);

        boolean badParse = false;
        try {
            LocalTime.parse("24:00");
        } catch (DateTimeParseException ex) {
            badParse = true;
        }
        require(badParse, "strict ISO parse");
        System.out.println("iso24Rejected=" + badParse);

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng **JDK 17 trở lên**:

```bash
javac LocalTimeGuideDemo.java
java LocalTimeGuideDemo
```

**Stdout chuẩn (đã xác minh bằng chạy thực tế):**

```text
original=23:50
plus20=00:10
maxPlusNano=00:00
detailed=09:08:07.125
twelveHour=03:07 PM
minuteTruncated=09:08
secondOfDay=34200
fromSecondOfDay=09:30
minEqualsMidnight=true
overnightAt2300=true
overnightAt0559=true
overnightAt0600=false
daytimeAt1200=true
equalBoundsEmpty=false
durationSameDate=-1420
durationWithDates=20
endWithDate=2026-01-02T00:10
fixedClockLocalTime=07:30
sorted=[08:30, 15:00]
invalidHourRejected=true
iso24Rejected=true
ALL CHECKS PASSED
```

### 12.1. Vì sao các kết quả là như vậy?

1. `original=23:50` và `plus20=00:10` cho thấy đối tượng cũ không đổi, còn kết quả cộng 20 phút được **quay vòng qua 00:00**. `LocalTime.MAX.plusNanos(1)` cũng trở về `00:00`.
2. `detailed=09:08:07.125` phản ánh 125 triệu nano giây; `minuteTruncated=09:08` chỉ **cắt** phần giây/nano.
3. `twelveHour=03:07 PM` dùng formatter 12h có `Locale.ENGLISH` và vẫn parse lại đúng 15:07.
4. `toSecondOfDay` và `ofSecondOfDay` cho cùng giá trị 34200 ↔ 09:30.
5. `minEqualsMidnight=true` vì `LocalTime.MIN` và `LocalTime.MIDNIGHT` đều diễn tả 00:00.
6. Khoảng ca đêm `22:00–06:00` chứa 23:00 và 05:59 nhưng không chứa 06:00 do **biên kết thúc exclusive**.
7. Khoảng `09:00–17:00` chứa 12:00; khoảng có hai đầu bằng nhau là **rỗng theo chính sách demo**, không đồng nghĩa tự động mở 24 giờ.
8. `Duration.between` chỉ thấy hai LocalTime cùng ngày nên ra `-1420` phút. Khi đưa vào `LocalDateTime` của hai ngày liên tiếp, thời gian là `20` phút và kết thúc `2026-01-02T00:10`.
9. `Clock.fixed` tạo nguồn thời gian ổn định cho phép kiểm tra giờ địa phương tại múi giờ Việt Nam là 07:30 mà không phụ thuộc giờ máy đang chạy.
10. `List<LocalTime>` sort theo giờ trong ngày, ra `[08:30, 15:00]`. Hai trường hợp không hợp lệ `LocalTime.of(24,0)` và `LocalTime.parse("24:00")` được bắt exception và xác nhận.

## 13. Checklist xử lý lỗi và các ngộ nhận phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `LocalTime` làm timestamp sự kiện | Mất ngày và zone | Dùng `Instant`/date-time có zone phù hợp |
| So giờ bằng `==` | Value-based class, identity không là hợp đồng | `equals` / `compareTo` |
| Nghĩ `23:50.plusMinutes(20)` cho thêm một ngày | LocalTime quay vòng 24h, không lưu ngày | Dùng `LocalDateTime` hoặc `ZonedDateTime` |
| Dùng `Duration.between(23:50,00:10)` và mong +20 phút | Hai LocalTime không biết ngày tiếp theo | Thêm ngày hoặc policy vòng 24h rõ ràng |
| Kiểm tra ca đêm bằng `start<=now && now<end` | Không hoạt động khi `start>end` | Phân nhánh khoảng qua nửa đêm |
| Nghĩ `start==end` luôn mở 24 giờ | Có thể là khoảng rỗng tùy nghiệp vụ | Dùng flag/policy minh bạch |
| Gọi `LocalTime.of(24,0)` | Giờ hợp lệ chỉ 0..23 | Đưa ranh giới sang ngày hôm sau |
| Parse mọi chuỗi giờ bằng formatter mặc định | Input có thể khác ISO | Khai báo pattern và chính sách lỗi |
| Nhầm `HH` với `hh` | 12h khác 24h, cần AM/PM | Chọn pattern có locale rõ |
| Dùng `truncatedTo(MINUTES)` để “làm tròn” | Nó loại bỏ phần giây | Viết quy tắc round riêng |
| So `toSecondOfDay` khi dữ liệu có nano | Mất phần nhỏ hơn giây | Dùng `compareTo` hoặc nano-of-day |
| Gọi `now()` trong mọi bài test | Test phụ thuộc clock/zone của máy | Inject `Clock`; dùng `Clock.fixed` |
| Lưu `LocalTime` rồi cho rằng nó mang zone | Nó không chứa offset/zone | Lưu `ZoneId`/ngày khi miền dữ liệu yêu cầu |
| Gắn ngày/zone rồi bỏ qua DST | Một số giờ địa phương không tồn tại hoặc trùng | Kiểm tra gap/overlap, policy nghiệp vụ |
| Dùng số Unix epoch làm `ofSecondOfDay` | Khác đơn vị và gốc thời gian | `Instant` rồi đổi zone |
| Dùng giờ thực tế từ server thay giờ cửa hàng | Default zone có thể khác | Dùng `ZoneId` xác định theo địa điểm |

### 13.1. Những ngoại lệ cần biết

- `DateTimeException`: tạo/biến đổi thời gian với trường không hợp lệ, ví dụ hour = 24.
- `DateTimeParseException` (subclass của `DateTimeException`): chuỗi không parse được theo formatter đã chọn.
- `UnsupportedTemporalTypeException`: cố thao tác trên một temporal field/unit không được `LocalTime` hỗ trợ.
- `NullPointerException`: truyền null vào các API yêu cầu đối tượng non-null như formatter/clock/zone tùy phương thức.
- `ArithmeticException`: có thể xảy ra trong phép tính số học/trung gian liên quan đến dữ liệu cực lớn theo hợp đồng API cụ thể; đừng tự giả định mọi phép `long` đều không thể tràn.

Với form/API, nên bắt lỗi **đúng phạm vi input** rồi chuyển thành lỗi validation có cấu trúc, không nuốt toàn bộ `RuntimeException`. Ví dụ người dùng nhập giờ 25:00 cần phản hồi “giờ phải từ 00 tới 23”, thay vì stack trace nội bộ.

### 13.2. Xử lý dữ liệu thiếu

Java `LocalTime` không có giá trị “đặc biệt” để nói “chưa nhập”; giá trị `00:00` là một giờ hợp lệ, không phải sentinel rỗng. Trong API Java, có thể biểu diễn thiếu bằng `Optional<LocalTime>` ở giá trị trả về hoặc một mô hình dữ liệu đã quy định rõ. Không tự lấy `LocalTime.MIDNIGHT` thay cho thiếu dữ liệu nếu nửa đêm là lịch hẹn hợp lệ.

**Nhớ:** một `LocalTime` bất biến không có nghĩa mọi đối tượng chứa nó là immutable. Một DTO mutable vẫn có thể được thay đổi field tham chiếu `LocalTime`.

## 14. Ma trận kiểm thử LocalTime

| Nhóm test | Dữ liệu | Điều cần kiểm tra |
| --- | --- | --- |
| Biên tối thiểu | `00:00` | `MIN` và `MIDNIGHT` bằng nhau |
| Biên tối đa | `23:59:59.999999999` | `MAX.plusNanos(1)` trở về 00:00 |
| Giờ invalid | `24:00` / `-1:00` | `of` ném exception |
| Phút invalid | `12:60` | `of` ném exception |
| Parse chuẩn | `"09:30"` | `LocalTime.parse` thành công |
| Parse sai ISO | `"24:00"` / `"25:10"` | `DateTimeParseException` |
| Formatter tùy chỉnh | `"03:07 PM"` | Parse–format round trip thành 15:07 |
| Nano giây | `09:08:07.125` | Không mất precision nếu formatter cho phép |
| Cộng qua nửa đêm | 23:50 + 20 phút | LocalTime thành 00:10, không mang ngày |
| Khoảng ban ngày | [09:00,17:00) | 09:00 true, 17:00 false |
| Khoảng ca đêm | [22:00,06:00) | 23:00 true; 05:59 true; 06:00 false |
| Khoảng hai biên bằng | [08:00,08:00) | Rỗng theo policy minh họa |
| Duration không ngày | 23:50 → 00:10 | Negative theo cùng mô hình ngày |
| Duration có ngày | 2026-01-01T23:50 → 2026-01-02T00:10 | 20 phút |
| Giờ theo zone | Instant UTC + `Asia/Ho_Chi_Minh` | Đổi ra đúng 07:30 |
| Clock cố định | `Clock.fixed(...)` | Test không phụ thuộc giờ thực |
| Giờ trong DB | Round-trip precision | Không tự mất nano do driver/column |
| DST gap/overlap | Ngày, zone có đổi offset | Policy giải giờ địa phương mơ hồ rõ ràng |

Không nên viết assertion dựa vào `LocalTime.now()` bằng một giờ cụ thể. Nếu phải test “trong khoảng hiện tại”, inject Clock và dùng một Instant xác định để test được cả ngay trước, ngay tại và ngay sau biên.

### 14.1. Kiểm tra hợp đồng thay vì chi tiết nội bộ

`LocalTime` là value-based; unit test nên so `equals`/`compareTo` và các field, không assert **identity** `a == b`. Tương tự, không phụ thuộc `toString()` luôn in đúng số chữ số phần nano mà UI mong muốn: `toString()` dùng cách xuất phù hợp với giá trị, còn định dạng giao tiếp nên được định nghĩa bằng `DateTimeFormatter`.

## 15. Bài tập tự luyện có lời giải

**Bài 1.** Tạo giờ 07:05 và chuyển sang chuỗi `HH:mm`.

```java
LocalTime t = LocalTime.of(7, 5);
String text = t.format(DateTimeFormatter.ofPattern("HH:mm"));
// "07:05"
```

Đây là đoạn minh họa trong method đã import `java.time.*` và `java.time.format.*`.

**Bài 2.** `LocalTime.of(23,55).plusMinutes(10)` bằng gì? Có biết ngày không?

**Đáp án:** `00:05`; không biết ngày. Nếu cần ngày kế tiếp, thao tác trên `LocalDateTime` hoặc `ZonedDateTime` có ngày.

**Bài 3.** Cửa hàng có ca `[22:00,06:00)`. Lúc 05:59 và 06:00 có thuộc ca không?

**Đáp án:** 05:59 thuộc ca; 06:00 không thuộc ca (end exclusive).

**Bài 4.** Trong hệ thống, `[08:00,08:00)` là mở 24 giờ hay đóng cả ngày?

**Đáp án:** Không thể suy luận chỉ từ hai LocalTime bằng nhau. Đó là **quyết định nghiệp vụ**. Ví dụ mục 7 định nghĩa nó là khoảng rỗng; nếu hệ thống hỗ trợ mở 24/7, hãy lưu trạng thái rõ ràng.

**Bài 5.** Vì sao `Duration.between(LocalTime.of(23,50),LocalTime.of(0,10))` không cho 20 phút?

**Đáp án:** Vì LocalTime không có ngày, và theo thứ tự thời gian trong cùng một ngày, 00:10 trước 23:50. Muốn 20 phút thì cần dữ liệu hai ngày liên tiếp hoặc policy quay vòng 24 giờ.

**Bài 6.** Giờ `09:08:07.125` gọi `truncatedTo(ChronoUnit.MINUTES)` trở thành bao nhiêu?

**Đáp án:** `09:08`. Đây là thao tác cắt, không làm tròn.

**Bài 7.** Muốn có giờ địa phương tương ứng một `Instant` ở khu vực `Asia/Ho_Chi_Minh`, dùng gì?

```java
LocalTime view = LocalTime.ofInstant(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đoạn minh họa cần biến `Instant instant` và import phù hợp. Không dùng `LocalTime.ofSecondOfDay(instant.getEpochSecond())`.

**Bài 8.** Hai LocalTime giống nhau theo `equals` có thể dùng `==` để kiểm tra không?

**Đáp án:** Không nên. Là value-based class, API yêu cầu so giá trị bằng `equals`; identity không phải điều cần dựa vào.

**Bài 9.** `LocalTime` có thể xác định “08:30 ở Paris ngày chuyển DST” là một Instant duy nhất không?

**Đáp án:** Một LocalTime không đủ. Cần ngày và `ZoneId`; với giờ thuộc gap/overlap, cần xem quy tắc zone và policy khi gắn ngày giờ.

**Bài 10.** Một app lưu `LocalTime.of(0,0)` để biểu diễn “chưa chọn giờ”. Có vấn đề gì?

**Đáp án:** Có: nửa đêm là giờ hợp lệ. Nên biểu diễn missing bằng trạng thái riêng hoặc `Optional<LocalTime>` ở API thích hợp.

**Bài 11.** `LocalTime.of(8,0).plusHours(24)` có khác `08:00` không?

**Đáp án:** Không; kết quả vẫn 08:00. Nó không ghi nhớ đã đi qua một ngày.

**Bài 12.** Vì sao khi kiểm thử `LocalTime.now()` nên inject `Clock`?

**Đáp án:** Để không phụ thuộc giờ và múi giờ JVM tại thời điểm chạy; dùng `Clock.fixed` tạo kết quả và dữ liệu biên lặp lại được.

## 16. Checklist quyết định trước khi đưa vào production

- [ ] Dữ liệu là **giờ trong ngày** hay **một event/timestamp có ngày**? Nếu là event, không dùng LocalTime đơn lẻ.
- [ ] Có cần múi giờ/UTC offset không? Nếu có, chọn kiểu date-time phù hợp và giữ ZoneId khi nghiệp vụ cần.
- [ ] Đầu vào `hour/minute/second/nano` đã hợp lệ, không dùng giờ 24 hoặc giây 60?
- [ ] Chuỗi đầu vào đã có formatter và hợp đồng rõ, không phụ thuộc ngẫu nhiên vào default locale/format?
- [ ] Đã phân biệt phần giây được **hiển thị** hay thực sự bị **cắt/round**?
- [ ] Phép cộng `plus`/`minus` có cần mang ngày không? Nếu có, chuyển sang date-time trước.
- [ ] Nếu có giờ mở/đóng, đã định nghĩa biên [start,end), ca qua nửa đêm và start==end?
- [ ] Nếu có ngày trong tuần, ngày nghỉ hoặc lịch theo địa điểm, đã đưa ngày và zone vào mô hình?
- [ ] Khi tính Duration thực tế, đã dùng ngày/zone hoặc Instant, đặc biệt với DST?
- [ ] Nếu lấy giờ hiện tại, đã chọn ZoneId và inject Clock cho phép test deterministic?
- [ ] Nếu lưu DB/JSON, đã xác nhận precision, format, zone assumptions và round-trip?
- [ ] Đã phân biệt LocalTime.MIDNIGHT với dữ liệu thiếu (null/Optional)?
- [ ] Đã kiểm tra các trường hợp rỗng, biên 00:00, 23:59:59.999999999, invalid parse và ca đêm?
- [ ] Test so **giá trị** (equals/compareTo), không dùng object identity?
- [ ] Không suy diễn rằng mọi ngày theo đồng hồ địa phương có đúng 24 giờ thực khi khu vực có DST?

## Tài liệu tham khảo chính thức còn áp dụng

- [Oracle JDK 25 — LocalTime: tạo, parse, plus/minus, so sánh, precision, atDate, atOffset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalTime.html)
- [Oracle JDK 25 — DateTimeFormatter và pattern cho giờ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle JDK 25 — Clock, cố định Instant cho unit test và lựa chọn ZoneId](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html)
- [Oracle JDK 25 — Duration: khoảng thời gian trên temporal types](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html)
- [Oracle JDK 25 — LocalDateTime và kết hợp ngày + giờ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html)
- [Oracle JDK 25 — ZoneId và quy tắc chuyển đổi từ Instant sang giờ khu vực](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html)
- [Oracle JDK 25 — ZonedDateTime và vấn đề zone rules / gap / overlap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html)

**Tóm ý cốt lõi:** `LocalTime` diễn tả **một vị trí trên đồng hồ trong ngày**, không phải “số giây từ epoch” và không phải một thời điểm tuyệt đối. Dùng nó cho giờ mở cửa, cutoff và lịch giờ lặp lại; kết hợp ngày/zone khi cần lịch thực, và dùng `Clock` cố định để kiểm thử một cách đáng tin.
