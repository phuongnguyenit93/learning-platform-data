# Chuyển đổi giây hoặc nano giây tính từ đầu ngày với LocalTime

Trong Java, `LocalTime` mô tả **giờ trong một ngày**: giờ, phút, giây và phần nano giây. Khi làm việc với bộ đếm **giây tính từ 00:00** (*second of day*) hoặc **nano giây tính từ 00:00** (*nano of day*), bạn có thể đổi trực tiếp giữa số nguyên và `LocalTime` mà không cần tự tách hoặc ghép từng thành phần giờ–phút–giây.

Bài này tập trung vào bốn phương thức tương ứng của `java.time.LocalTime`:

- `LocalTime.ofSecondOfDay(long)`: số giây từ đầu ngày → `LocalTime`.
- `LocalTime.ofNanoOfDay(long)`: số nano giây từ đầu ngày → `LocalTime`.
- `localTime.toSecondOfDay()`: `LocalTime` → số giây nguyên từ đầu ngày.
- `localTime.toNanoOfDay()`: `LocalTime` → tổng nano giây từ đầu ngày.

Các phép đổi này xử lý **giờ trong một ngày theo đồng hồ**, không chứa ngày lịch, múi giờ, thời điểm UTC hay một thời lượng kéo dài qua nhiều ngày.

## 1. Hiểu “tính từ đầu ngày”

Mốc đầu ngày là **00:00:00.000000000**. Từ mốc này, mỗi giây hoặc nano giây tương ứng với một vị trí trong khoảng 24 giờ theo mô hình `LocalTime`.

Một phút có **60 giây**, một giờ có **3.600 giây**, và một ngày theo mô hình giờ địa phương `LocalTime` có **86.400 giây danh nghĩa**. Một giây có **1.000.000.000 nano giây**.

| Giờ | Giây tính từ đầu ngày | Nano giây tính từ đầu ngày |
| --- | ---: | ---: |
| `00:00:00` | 0 | 0 |
| `00:00:01` | 1 | 1.000.000.000 |
| `00:01:00` | 60 | 60.000.000.000 |
| `01:00:00` | 3.600 | 3.600.000.000.000 |
| `12:00:00` | 43.200 | 43.200.000.000.000 |
| `12:34:56` | 45.296 | 45.296.000.000.000 |
| `12:34:56.123456789` | 45.296 | 45.296.123.456.789 |
| `23:59:59` | 86.399 | 86.399.000.000.000 |
| `23:59:59.999999999` | 86.399 | 86.399.999.999.999 |

**Chú ý:** `86_400` là tổng **số giây của cả 24 giờ**, đồng thời là **giá trị ngoài miền** của chỉ số giây tính từ đầu ngày. `86_400` giây sau 00:00 là mốc 00:00 **của ngày hôm sau**, không phải một giá trị `LocalTime` trong ngày đang xét. Đối với nano giây, giá trị `86_400_000_000_000L` cũng là cận trên *loại trừ*.

## 2. Các API chuyển đổi và miền giá trị

| Hướng | API | Kiểu số | Miền hợp lệ hoặc kết quả |
| --- | --- | --- | --- |
| Giây → giờ | `LocalTime.ofSecondOfDay(long secondOfDay)` | `long` | **0 đến 86.399**, bao gồm hai đầu |
| Nano giây → giờ | `LocalTime.ofNanoOfDay(long nanoOfDay)` | `long` | **0 đến 86.399.999.999.999**, bao gồm hai đầu |
| Giờ → giây | `time.toSecondOfDay()` | Trả `int` | 0 đến 86.399 |
| Giờ → nano giây | `time.toNanoOfDay()` | Trả `long` | 0 đến 86.399.999.999.999 |

Hai hàm `of…` là phương thức **static** để tạo `LocalTime`. Hai hàm `to…` là phương thức **instance** gọi trên một đối tượng `LocalTime` sẵn có.

### Tạo giờ từ giây tính từ 00:00

```java
import java.time.LocalTime;

LocalTime midnight = LocalTime.ofSecondOfDay(0);       // 00:00
LocalTime noon = LocalTime.ofSecondOfDay(43_200);      // 12:00
LocalTime example = LocalTime.ofSecondOfDay(45_296);   // 12:34:56
LocalTime lastSecond = LocalTime.ofSecondOfDay(86_399); // 23:59:59
```

Đây là **đoạn mã minh họa**, cần đặt trong một phương thức Java. Vì đầu vào chỉ có số giây nguyên, kết quả có **nano giây của giây hiện tại bằng 0**. Nếu bạn cần giữ phần lẻ của giây, hãy dùng `ofNanoOfDay`.

### Tạo giờ từ nano giây tính từ 00:00

```java
import java.time.LocalTime;

LocalTime precise = LocalTime.ofNanoOfDay(45_296_123_456_789L);
// 12:34:56.123456789

LocalTime lastNano = LocalTime.ofNanoOfDay(86_399_999_999_999L);
// 23:59:59.999999999
```

Hậu tố `L` cho literal số nguyên dài giúp bảo đảm kiểu `long`. Giá trị nano giây trong ngày lớn hơn miền `int`, vì vậy không được đưa vào một biến `int` hoặc thực hiện phép nhân nano giây bằng số nguyên 32-bit.

### Lấy số giây hoặc nano giây từ `LocalTime`

```java
import java.time.LocalTime;

LocalTime time = LocalTime.of(12, 34, 56, 123_456_789);

int secondOfDay = time.toSecondOfDay(); // 45296
long nanoOfDay = time.toNanoOfDay();    // 45296123456789
```

`toSecondOfDay()` trả **số giây đã hoàn tất từ đầu ngày**. Với `12:34:56.123456789`, giá trị là **45.296**, **không làm tròn** lên 45.297. Phần `123_456_789` nano giây vẫn nằm trong `LocalTime` gốc, nhưng bị bỏ qua trong **giá trị `int` được trả về**. `toNanoOfDay()` giữ đủ độ chính xác nano giây.

## 3. Công thức để hiểu kết quả

Với `hour` trong 0–23, `minute` trong 0–59 và `second` trong 0–59:

```text
secondOfDay = hour × 3600 + minute × 60 + second
nanoOfDay   = secondOfDay × 1_000_000_000 + nanoOfSecond
```

Trong đó `nanoOfSecond` là số nguyên từ 0 đến 999.999.999, thể hiện phần nhỏ hơn một giây. Ví dụ tại `12:34:56.123456789`:

```text
secondOfDay = 12 × 3600 + 34 × 60 + 56
            = 43_200 + 2_040 + 56
            = 45_296

nanoOfDay   = 45_296 × 1_000_000_000 + 123_456_789
            = 45_296_123_456_789
```

Nếu cần tự giải mã một giá trị giây **đã được xác thực hợp lệ**, có thể dùng phép chia nguyên và phần dư:

```java
long totalSeconds = 45_296L;
long hour = totalSeconds / 3_600;         // 12
long minute = (totalSeconds % 3_600) / 60; // 34
long second = totalSeconds % 60;         // 56
```

Đây là đoạn minh họa dùng cho bài toán học công thức. Trong nghiệp vụ, chọn `LocalTime.ofSecondOfDay(totalSeconds)` để Java chịu trách nhiệm kiểm tra ranh giới và chuyển đổi. Với nano giây, trước tiên lấy số giây nguyên bằng phép chia `1_000_000_000L`, rồi lấy phần nano trong giây bằng phép chia lấy dư cho `1_000_000_000L`.

Không nên tính `hour * 3_600_000_000_000` bằng `int` vì có thể tràn số **trước khi gán sang `long`**. Nếu buộc phải tự tính, dùng literal/biến `long` và ưu tiên `Math.addExact` / `Math.multiplyExact` nếu dữ liệu đầu vào có khả năng vượt miền số. Với một `LocalTime` hợp lệ, `toNanoOfDay()` đã tính chính xác và vừa trong `long`.

## 4. Ví dụ Java 17+ chạy hoàn chỉnh

Lưu tệp **`LocalTimeDayUnitsDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;

public class LocalTimeDayUnitsDemo {
    public static void main(String[] args) {
        long secondOfDay = 45_296L;
        long nanoOfDay = 45_296_123_456_789L;

        LocalTime wholeSecond = LocalTime.ofSecondOfDay(secondOfDay);
        LocalTime fractional = LocalTime.ofNanoOfDay(nanoOfDay);

        System.out.println("From seconds: " + wholeSecond);
        System.out.println("From nanos: " + fractional);
        System.out.println("Second of day: " + fractional.toSecondOfDay());
        System.out.println("Nano of day: " + fractional.toNanoOfDay());
        System.out.println("Round trip seconds: "
                + LocalTime.ofSecondOfDay(fractional.toSecondOfDay()));
        System.out.println("Truncate to seconds: "
                + fractional.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("Start of day: " + LocalTime.ofSecondOfDay(0));
        System.out.println("Last second: " + LocalTime.ofSecondOfDay(86_399));
        System.out.println("Last nanosecond: "
                + LocalTime.ofNanoOfDay(86_399_999_999_999L));
        printValidation("seconds=86400", () -> LocalTime.ofSecondOfDay(86_400));
        printValidation("nanos=-1", () -> LocalTime.ofNanoOfDay(-1));
    }

    private static void printValidation(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": VALID");
        } catch (DateTimeException ex) {
            System.out.println(label + ": INVALID");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LocalTimeDayUnitsDemo.java
java LocalTimeDayUnitsDemo
```

**stdout chính xác** (đã kiểm tra bằng `javac --release 17` và `java`):

```text
From seconds: 12:34:56
From nanos: 12:34:56.123456789
Second of day: 45296
Nano of day: 45296123456789
Round trip seconds: 12:34:56
Truncate to seconds: 12:34:56
Start of day: 00:00
Last second: 23:59:59
Last nanosecond: 23:59:59.999999999
seconds=86400: INVALID
nanos=-1: INVALID
```

Các điểm cần quan sát:

1. `ofSecondOfDay(45_296)` dựng `12:34:56` và không có phần nano.
2. `ofNanoOfDay(45_296_123_456_789L)` dựng `12:34:56.123456789`.
3. `fractional.toSecondOfDay()` trả `45296`, không chứa phần nano; `toNanoOfDay()` giữ đủ `45296123456789`.
4. `LocalTime.ofSecondOfDay(fractional.toSecondOfDay())` quay lại mốc **giây nguyên**, không giữ `.123456789`.
5. Giá trị đầu vào `86400` giây hoặc `-1` nano bị từ chối bằng `DateTimeException`. Ví dụ bắt lỗi chỉ để in nhãn đơn giản; mã sản xuất cần xử lý theo hợp đồng đầu vào.

## 5. Tính chính xác và khả năng chuyển đổi khứ hồi

Một chuyển đổi **khứ hồi** (*round trip*) là đổi đối tượng sang số rồi đổi về đối tượng.

### Khứ hồi qua nano giây: giữ nguyên toàn bộ giờ

```java
LocalTime original = LocalTime.of(12, 34, 56, 123_456_789);
long nanos = original.toNanoOfDay();
LocalTime restored = LocalTime.ofNanoOfDay(nanos);

System.out.println(original.equals(restored)); // true
```

Đoạn minh họa cần import `java.time.LocalTime`. Với mọi `LocalTime` hợp lệ, cặp `toNanoOfDay` → `ofNanoOfDay` có thể khôi phục **chính xác tới nano giây**.

### Khứ hồi qua giây: có thể mất phần lẻ

```java
LocalTime original = LocalTime.of(12, 34, 56, 123_456_789);
int seconds = original.toSecondOfDay();
LocalTime restored = LocalTime.ofSecondOfDay(seconds);

System.out.println(original.equals(restored)); // false
System.out.println(restored);                  // 12:34:56
```

Đoạn minh họa cần import `java.time.LocalTime`. Trường hợp này **không làm tròn** mà loại bỏ toàn bộ phần nano giây. `toSecondOfDay` phù hợp cho các quy tắc chỉ yêu cầu giờ–phút–giây; không phù hợp nếu bạn phải lưu và khôi phục thời gian có độ chính xác mili/micro/nano giây.

Để chủ động làm rõ ý định bỏ phần nhỏ hơn một giây, có thể dùng `time.truncatedTo(ChronoUnit.SECONDS)` trước khi so sánh hoặc ghi dữ liệu. Đừng nhầm việc **truncation** với chuyển đổi múi giờ hay làm tròn lên giây tiếp theo.

### Mili giây, micro giây và nano giây

Một số hệ thống bên ngoài dùng mili giây hoặc micro giây tính từ đầu ngày. Đây **không** phải đơn vị mà `ofNanoOfDay` nhận trực tiếp:

| Đơn vị nguồn | Hệ số sang nano giây | Ví dụ |
| --- | ---: | --- |
| Giây | `1_000_000_000L` | 1 giây → 1.000.000.000 nano |
| Mili giây | `1_000_000L` | 1 mili giây → 1.000.000 nano |
| Micro giây | `1_000L` | 1 micro giây → 1.000 nano |
| Nano giây | `1L` | Giữ nguyên |

Ví dụ **đúng** khi đầu vào là 12:34:56.123, tương ứng 45.296.123 mili giây từ đầu ngày:

```java
long millisOfDay = 45_296_123L;
long nanosOfDay = Math.multiplyExact(millisOfDay, 1_000_000L);
LocalTime fromMillis = LocalTime.ofNanoOfDay(nanosOfDay);
// 12:34:56.123
```

Đoạn minh họa cần import `java.time.LocalTime`. `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân vượt miền `long`; `ofNanoOfDay` vẫn cần kiểm tra đầu vào thuộc khoảng nano giây trong ngày. Nếu dữ liệu nguồn có phần nhỏ hơn đơn vị đang lưu, việc chuyển thành số giây/mili giây nguyên sẽ mất thông tin và không thể khôi phục bằng phép nhân ngược.

## 6. Giới hạn 0 đến trước 24:00 và xử lý giá trị sai

`LocalTime` hỗ trợ các giá trị từ **00:00:00.000000000** đến **23:59:59.999999999**. Không có giờ `24:00` dưới dạng một `LocalTime` riêng và không có chỉ số âm.

```java
LocalTime.ofSecondOfDay(0);                   // hợp lệ
LocalTime.ofSecondOfDay(86_399);              // hợp lệ
LocalTime.ofNanoOfDay(0L);                    // hợp lệ
LocalTime.ofNanoOfDay(86_399_999_999_999L);   // hợp lệ

LocalTime.ofSecondOfDay(-1);                  // DateTimeException
LocalTime.ofSecondOfDay(86_400);              // DateTimeException
LocalTime.ofNanoOfDay(-1L);                   // DateTimeException
LocalTime.ofNanoOfDay(86_400_000_000_000L);  // DateTimeException
```

Đây là **các lời gọi minh họa**, bốn dòng cuối cố ý tạo lỗi và không được thực hiện liên tiếp ngoài xử lý ngoại lệ trong một chương trình cần chạy tiếp. Nếu cần từ chối đầu vào trước khi gọi API, quy tắc là:

```java
boolean validSeconds = seconds >= 0 && seconds < 86_400L;
boolean validNanos = nanos >= 0 && nanos < 86_400_000_000_000L;
```

Hai biến `seconds` và `nanos` giả định đã được khai báo kiểu `long`. Trong hầu hết trường hợp, chỉ cần gọi API và xử lý `DateTimeException` phù hợp với hợp đồng thay vì viết một cơ chế kiểm tra song song.

### Khi nào được chuẩn hóa giá trị vượt ngày?

Một số bài toán điều khiển thiết bị hoặc đồng hồ vòng muốn coi giây `86_400` tương đương `00:00`, hoặc `-1` tương đương `23:59:59`. **Đây là chính sách chuẩn hóa chủ động**, khác với việc xác thực dữ liệu:

```java
long rawSeconds = -1L;
long normalized = Math.floorMod(rawSeconds, 86_400L); // 86399
LocalTime wrapped = LocalTime.ofSecondOfDay(normalized);
// 23:59:59
```

`Math.floorMod` cho kết quả không âm khi số chia dương, khác với phần dư `%` có thể âm trên số âm. Việc chuẩn hóa loại bỏ thông tin **đã trôi qua bao nhiêu ngày**. Nếu `rawSeconds` biểu thị khoảng thời gian thực tính từ một mốc, hãy dùng `Duration` hoặc kết hợp `LocalDate`/`LocalDateTime` với phép cộng thời gian; **đừng âm thầm đổi đầu vào ngoài miền thành giờ hợp lệ** nếu nghiệp vụ không yêu cầu.

Tương tự có thể dùng `Math.floorMod(rawNanos, 86_400_000_000_000L)` nếu rõ ràng cần đồng hồ vòng theo nano giây. Với bài toán xác thực dữ liệu, nên từ chối số ngoài miền.

## 7. Phân biệt giây từ đầu ngày, giây Unix và khoảng thời gian

Ba cách biểu diễn sau **khác nhau** dù đều có đơn vị “giây”:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `second of day` | `45_296` | Vị trí 12:34:56 bên trong một ngày theo `LocalTime` |
| `epoch second` | `Instant.getEpochSecond()` | Số giây theo thang Unix/Java từ mốc 1970-01-01T00:00:00Z |
| `Duration` | `Duration.ofSeconds(45_296)` | Độ dài khoảng thời gian, có thể vượt nhiều ngày hoặc âm |

`LocalTime.ofSecondOfDay` **không được dùng** với số giây Unix hoặc `Duration` tùy ý. Giây Unix thường vượt 86.399 nên sẽ ném `DateTimeException`, còn dù vô tình nằm trong miền cũng không đồng nghĩa với “giây từ đầu ngày” mong muốn.

Nếu có **epoch second** và cần giờ địa phương, phải tạo `Instant` rồi chuyển theo múi giờ:

```java
long epochSecond = 1_709_251_200L;
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalTime localTime = Instant.ofEpochSecond(epochSecond)
        .atZone(zone)
        .toLocalTime();
```

Đây là đoạn minh họa cần import `java.time.*`. Khi đổi từ thời điểm tuyệt đối thành giờ trong ngày, **`ZoneId` là bắt buộc để xác định giờ địa phương**. Trong khi đó, chính `LocalTime` không biết ngày, giờ UTC, offset hay múi giờ của giá trị mà nó đang mang.

## 8. Lưu ý lịch, DST và leap second

`LocalTime` là **giờ theo đồng hồ trong một ngày danh nghĩa 24 giờ**, không phải phép đo số giây thực sự đã trôi qua kể từ nửa đêm ở mọi nơi trên thế giới.

- Với vùng có thay đổi giờ mùa hè (*daylight saving time*, DST), một ngày địa phương có thể chỉ dài **23 giờ** hoặc dài **25 giờ** tính theo thời gian thực. Vì vậy, không thể dùng `toSecondOfDay()` để luôn tính chính xác số giây thực đã trôi qua từ mốc nửa đêm của ngày đó.
- Trong một lần chuyển DST, một giờ địa phương có thể **không tồn tại** hoặc **bị lặp**; `LocalTime.ofSecondOfDay` vẫn có thể tạo ra giờ đó bởi bản thân `LocalTime` không có ngày và vùng để kiểm tra quy tắc DST.
- `LocalTime` có giây từ 0 đến 59; nó không biểu diễn trực tiếp giây nhuận `23:59:60` (*leap second*) như một thành phần `second=60`.

Khi cần biết thời lượng thực từ nửa đêm ở một vùng và ngày cụ thể, phải kết hợp `LocalDate` và `ZoneId` rồi làm việc với `ZonedDateTime` / `Instant`:

```java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

Instant start = date.atStartOfDay(zone).toInstant();
Instant nextStart = date.plusDays(1).atStartOfDay(zone).toInstant();

long actualSeconds = Duration.between(start, nextStart).getSeconds();
// 82800 (23 giờ) trong ngày bắt đầu DST ở New York năm 2024
```

Đây là đoạn minh họa cần import `java.time.*`. `86_400` giây danh nghĩa của `LocalTime` vẫn đúng theo **tọa độ giờ trong ngày**; `82_800` giây ở ví dụ là **thời lượng thực giữa hai mốc nửa đêm**. Phân biệt hai phép đo là điều quan trọng khi tính ca làm, thanh toán theo giờ hoặc thời gian vận hành.

## 9. Chọn cách biểu diễn khi nhập, lưu và truyền dữ liệu

Khi dữ liệu có nghĩa là một **giờ trong ngày** (ví dụ quầy giao dịch mở lúc 09:30), `LocalTime` là kiểu phù hợp. Nếu giao thức bên ngoài dùng “giây tính từ đầu ngày”, có thể chuyển ở biên hệ thống:

```java
int openingSeconds = LocalTime.of(9, 30).toSecondOfDay(); // 34200
LocalTime opening = LocalTime.ofSecondOfDay(openingSeconds); // 09:30
```

Nếu giao thức muốn độ chính xác nano giây, dùng `long` và cặp `toNanoOfDay` / `ofNanoOfDay`. Nếu chỉ cần mili giây, thống nhất rõ tên trường và đơn vị (ví dụ `millisOfDay`), bởi nhầm mili giây thành nano giây làm sai thời điểm trong ngày nhiều bậc độ lớn.

Nếu cần **thời điểm xảy ra một sự kiện cụ thể** (ví dụ đã giao hàng lúc 09:30 ngày nào, ở múi giờ nào), chỉ `LocalTime` là **chưa đủ**. Phải dùng thông tin ngày và vùng hoặc lưu `Instant`. Nếu cần cộng dồn thời lượng nhiều ngày, chọn `Duration` thay vì `LocalTime`: một giờ trên mặt đồng hồ có thể quay vòng qua nửa đêm mà không lưu được số ngày.

## 10. Các lỗi thường gặp và cách tránh

1. **Cho phép đầu vào đúng 86.400 giây hoặc 86.400.000.000.000 nano giây.** Đây là cận trên loại trừ; giá trị cuối hợp lệ là 86.399 giây hoặc 86.399.999.999.999 nano giây.
2. **Giả định `toSecondOfDay()` làm tròn.** Nó bỏ phần nano của giây, nên `12:34:56.999999999` vẫn trả 45.296.
3. **Lưu nano giây trong `int`.** Giá trị có thể hơn 86 nghìn tỷ; dùng `long` và literal `L` khi cần.
4. **Nhầm “nano giây trong giây” với “nano giây từ đầu ngày”.** `time.getNano()` chỉ trả phần nano từ 0–999.999.999; `time.toNanoOfDay()` trả tổng kể từ 00:00.
5. **Nhầm giây Unix với giây trong ngày.** Với timestamp, đi qua `Instant` và `ZoneId` trước.
6. **Dùng số giây cố định để suy thời lượng thực của mọi ngày địa phương.** DST có thể làm ngày thực tế khác 24 giờ; dùng `ZonedDateTime` hoặc `Instant` cho bài toán thời lượng thực.
7. **Tự chia nhân số nguyên mà quên tràn số.** Thực hiện phép tính ở kiểu `long` hoặc gọi trực tiếp API có sẵn.
8. **Tự động `floorMod` mọi đầu vào sai.** Chỉ làm vậy khi định nghĩa bài toán là một đồng hồ vòng; với dữ liệu cần xác thực, phải từ chối.
9. **Mong `LocalTime` giữ ngày hoặc múi giờ.** `LocalTime` không mang ngữ cảnh ấy; dùng kiểu phù hợp hơn khi dữ liệu yêu cầu.

## 11. Checklist kiểm thử

| Ca | Giá trị đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Giây đầu ngày | `ofSecondOfDay(0)` | `00:00` |
| Giây cuối ngày | `ofSecondOfDay(86_399)` | `23:59:59` |
| Giây vượt cận | `ofSecondOfDay(86_400)` | `DateTimeException` |
| Giây âm | `ofSecondOfDay(-1)` | `DateTimeException` |
| Nano đầu ngày | `ofNanoOfDay(0)` | `00:00` |
| Nano cuối ngày | `ofNanoOfDay(86_399_999_999_999L)` | `23:59:59.999999999` |
| Nano vượt cận | `ofNanoOfDay(86_400_000_000_000L)` | `DateTimeException` |
| Nano âm | `ofNanoOfDay(-1L)` | `DateTimeException` |
| Lấy giây từ giờ lẻ | `12:34:56.123456789` | `toSecondOfDay() == 45296` |
| Lấy nano từ giờ lẻ | `12:34:56.123456789` | `toNanoOfDay() == 45296123456789L` |
| Khứ hồi nano | `ofNanoOfDay(time.toNanoOfDay())` | Bằng `time` gốc |
| Khứ hồi giây | `ofSecondOfDay(time.toSecondOfDay())` | Bằng `time` khi `getNano()==0`; nếu có nano thì mất phần lẻ |

Trong JUnit 5 có thể dùng `assertEquals` để kiểm tra giá trị chuyển đổi, và `assertThrows(DateTimeException.class, () -> LocalTime.ofSecondOfDay(86_400))` để xác thực miền đầu vào. Để kiểm tra khứ hồi, nên dùng nhiều giờ khác nhau, gồm 00:00, 12:00, sát cuối ngày và giờ có nano giây khác 0.

## 12. Ghi nhớ khi chọn API

| Nhu cầu | API phù hợp |
| --- | --- |
| Số giây trong một ngày → giờ | `LocalTime.ofSecondOfDay(long)` |
| Số nano giây trong một ngày → giờ | `LocalTime.ofNanoOfDay(long)` |
| Giờ → số giây nguyên từ đầu ngày | `LocalTime.toSecondOfDay()` |
| Giờ → tổng nano giây từ đầu ngày | `LocalTime.toNanoOfDay()` |
| Bỏ phần lẻ giây có chủ đích | `LocalTime.truncatedTo(ChronoUnit.SECONDS)` |
| Chuẩn hóa đồng hồ vòng có chủ đích | `Math.floorMod(raw, 86_400L)` trước khi tạo giờ |
| Chuyển timestamp tuyệt đối sang giờ tại vùng | `Instant.atZone(zone).toLocalTime()` |
| Đo thời lượng thực giữa hai thời điểm | `Duration.between(instant1, instant2)` |

**Nguyên tắc cốt lõi:** `ofSecondOfDay`/`toSecondOfDay` dùng **đơn vị giây nguyên**; `ofNanoOfDay`/`toNanoOfDay` dùng **đơn vị nano giây** và giữ độ chính xác cao hơn. Kiểm tra đúng khoảng **0 đến trước 24:00**, chọn `long` cho nano giây và luôn phân biệt **giờ trong ngày** với **thời điểm tuyệt đối** hoặc **thời lượng thực**.
