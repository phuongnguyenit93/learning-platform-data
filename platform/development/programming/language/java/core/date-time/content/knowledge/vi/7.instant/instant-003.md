# Tạo `Instant` từ epoch giây, epoch mili giây và phần nano giây

`java.time.Instant` biểu diễn **một thời điểm trên trục thời gian Java**, không mang múi giờ, ngày giờ địa phương hay định dạng hiển thị cố định. Khi một API, cơ sở dữ liệu hoặc thiết bị gửi timestamp dạng số, ta thường phải dựng `Instant` từ **epoch seconds**, **epoch milliseconds** hoặc **giây cộng phần nano giây**. Chọn đúng đơn vị và hiểu quy tắc chuẩn hóa là điều kiện để không làm lệch thời điểm.

Mục tiêu của bài:

- Hiểu mốc epoch và cách `Instant` lưu giây cùng phần nano.
- Sử dụng chính xác `Instant.ofEpochSecond(long)`, `ofEpochMilli(long)`, `ofEpochSecond(long, long)`.
- Giải thích cách xử lý phần nano vượt một giây, số âm và thời điểm trước epoch.
- Đọc ngược `getEpochSecond()`, `getNano()`, `toEpochMilli()` và nhận biết mất độ chính xác.
- Phân biệt biểu diễn UTC với thời gian địa phương khi hiển thị.

## 1. Epoch là mốc nào?

Trong các API epoch phổ biến của Java, mốc bắt đầu là:

```text
1970-01-01T00:00:00Z  =  Unix/Java epoch
epochSecond           =  0
epochMilli            =  0
```

`Z` nghĩa là offset UTC+00:00. Với một thời điểm **sau** epoch, số đếm thường dương; với thời điểm **trước** epoch, số đếm âm. Chẳng hạn:

| Dữ liệu đầu vào | Đơn vị và ý nghĩa | `Instant` tương ứng |
| --- | --- | --- |
| `0` giây | Ngay mốc epoch | `1970-01-01T00:00:00Z` |
| `1` giây | Một giây sau epoch | `1970-01-01T00:00:01Z` |
| `-1` giây | Một giây trước epoch | `1969-12-31T23:59:59Z` |
| `1000` mili giây | Một giây sau epoch | `1970-01-01T00:00:01Z` |
| `-1` mili giây | Một mili giây trước epoch | `1969-12-31T23:59:59.999Z` |

**Một timestamp số chỉ có nghĩa khi biết đơn vị.** Giá trị `1_700_000_000` theo giây là một thời điểm trong năm 2023; nếu nhầm nó là mili giây, kết quả nằm gần mốc đầu năm 1970. Đừng đoán đơn vị chỉ bằng số chữ số khi thiết kế giao diện lâu dài: hãy công bố schema rõ ràng như `createdAtEpochSeconds` hoặc `createdAtEpochMillis`.

### Cấu trúc giá trị của `Instant`

Một `Instant` về bản chất chứa hai phần:

1. **`epochSecond`** (kiểu `long`): số giây Java nguyên từ `1970-01-01T00:00:00Z`.
2. **`nano`** (kiểu `int`): phần nano giây *trong giây đó*, luôn nằm trong khoảng **0 đến 999.999.999**.

Ví dụ `2023-11-14T22:13:20.123456789Z` gồm `epochSecond = 1_700_000_000` và `nano = 123_456_789`. Độ phân giải biểu diễn tới nano giây **không bảo đảm** đồng hồ hệ thống đo được chính xác tới nano giây.

Java Time-Scale tính mỗi ngày lịch bằng 86.400 giây danh nghĩa. Giây nhuận UTC không được giữ như một trường “giây 60” riêng trong `Instant`; nếu tích hợp nguồn thời gian khoa học/chuyên dụng cần tính leap second vật lý, phải xử lý bằng quy tắc thang thời gian của nguồn đó.

## 2. Tạo từ epoch giây: `Instant.ofEpochSecond(long)`

Dùng phương thức này khi đầu vào được xác định là **số giây tính từ epoch**, không có phần lẻ:

```java
import java.time.Instant;

Instant epoch = Instant.ofEpochSecond(0);
Instant oneSecondLater = Instant.ofEpochSecond(1);
Instant oneSecondEarlier = Instant.ofEpochSecond(-1);
Instant event = Instant.ofEpochSecond(1_700_000_000L);

System.out.println(epoch);            // 1970-01-01T00:00:00Z
System.out.println(oneSecondLater);   // 1970-01-01T00:00:01Z
System.out.println(oneSecondEarlier); // 1969-12-31T23:59:59Z
System.out.println(event);            // 2023-11-14T22:13:20Z
```

`Instant.ofEpochSecond(seconds)` tương đương tạo một instant với `getEpochSecond() == seconds` và `getNano() == 0` (miễn là số giây nằm trong phạm vi `Instant` hỗ trợ).

Số giây thực tế trong hệ thống thường lớn, nên dùng `long`; hậu tố `L` trong ví dụ nhấn mạnh kiểu số dài. Nếu dữ liệu gửi dưới dạng chuỗi, hãy kiểm tra hợp lệ rồi chuyển thành `long`, và xử lý ngoại lệ khi số nằm ngoài miền hỗ trợ.

### Không suy ra múi giờ từ epoch giây

`Instant.ofEpochSecond(1_700_000_000L)` trả cùng một instant ở mọi máy. Lệnh `toString()` xuất dạng ISO UTC với `Z`. Nếu muốn hiển thị giờ địa phương, phải **chọn vùng**:

```java
Instant event = Instant.ofEpochSecond(1_700_000_000L);
System.out.println(event.atZone(
        java.time.ZoneId.of("Asia/Ho_Chi_Minh")));
// 2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
```

Giá trị `Instant` không đổi; chỉ cách hiển thị ngày giờ theo vùng thay đổi. Không tự cộng `7 * 3600` vào timestamp để “đổi sang giờ Việt Nam”: làm thế sẽ thay đổi chính thời điểm.

## 3. Tạo từ epoch mili giây: `Instant.ofEpochMilli(long)`

**Một mili giây (millisecond) = 1/1.000 giây = 1.000.000 nano giây.**

Dùng `ofEpochMilli` với số nguyên tính theo **mili giây từ epoch**, thường gặp ở các API timestamp, `System.currentTimeMillis()` và `java.util.Date.getTime()`.

```java
Instant fromMillis = Instant.ofEpochMilli(1_700_000_000_000L);
Instant fromSeconds = Instant.ofEpochSecond(1_700_000_000L);

System.out.println(fromMillis);               // 2023-11-14T22:13:20Z
System.out.println(fromMillis.equals(fromSeconds)); // true
```

Một mili giây sau số giây tròn:

```java
Instant milliseconds = Instant.ofEpochMilli(1_700_000_000_123L);
System.out.println(milliseconds);
// 2023-11-14T22:13:20.123Z
System.out.println(milliseconds.getNano()); // 123000000
```

Nếu dữ liệu `epochMillis` do một thành phần gửi, hãy lưu hoặc khai báo trường **có đơn vị rõ**: ví dụ `timestampMillis`, không chỉ `timestamp`.

### Giá trị âm trước epoch rất quan trọng

```java
Instant beforeEpoch = Instant.ofEpochMilli(-1);

System.out.println(beforeEpoch);                 // 1969-12-31T23:59:59.999Z
System.out.println(beforeEpoch.getEpochSecond()); // -1
System.out.println(beforeEpoch.getNano());        // 999000000
```

Thoạt nhìn có vẻ lạ: `-1 ms` được biểu diễn thành **-1 giây nguyên + 999 ms bên trong giây đó**, vì `getNano()` không âm. Nếu tách số mili giây bằng chia nguyên/trừ dư tùy tiện theo cách làm tròn về 0, bạn có thể tạo kết quả sai ở các thời điểm âm.

Ví dụ `Instant.ofEpochMilli(-1001)` biểu diễn `1969-12-31T23:59:58.999Z`, gồm `epochSecond=-2`, `nano=999_000_000`.

## 4. Tạo từ epoch giây và phần nano: `ofEpochSecond(long, long)`

Overload thứ hai:

```java
Instant.ofEpochSecond(long epochSecond, long nanoAdjustment)
```

Nhận một số giây nguyên và **phần điều chỉnh theo nano giây**. Tham số thứ hai là số `long` có thể dương, âm hoặc lớn hơn 999.999.999; Java **chuẩn hóa** về một giây nguyên và phần nano hợp lệ.

```java
Instant precise = Instant.ofEpochSecond(
        1_700_000_000L, 123_456_789L);

System.out.println(precise);
// 2023-11-14T22:13:20.123456789Z
System.out.println(precise.getEpochSecond()); // 1700000000
System.out.println(precise.getNano());        // 123456789
```

Với đầu vào chuẩn, `nanoAdjustment` thường thuộc **0–999.999.999**. Ví dụ:

| `epochSecond` | `nanoAdjustment` | Giá trị kết quả |
| ---: | ---: | --- |
| 10 | 0 | `1970-01-01T00:00:10Z` |
| 10 | 1 | `1970-01-01T00:00:10.000000001Z` |
| 10 | 500.000.000 | `1970-01-01T00:00:10.500Z` |
| 10 | 1.500.000.000 | `1970-01-01T00:00:11.500Z` |
| 10 | -1 | `1970-01-01T00:00:09.999999999Z` |
| -1 | 500.000.000 | `1969-12-31T23:59:59.500Z` |

### Chuẩn hóa nano giây không phải lỗi đầu vào

```java
Instant carry = Instant.ofEpochSecond(10, 1_500_000_000L);
Instant borrow = Instant.ofEpochSecond(10, -1);

System.out.println(carry);  // 1970-01-01T00:00:11.500Z
System.out.println(borrow); // 1970-01-01T00:00:09.999999999Z
```

`1_500_000_000` nano tương đương **1,5 giây**, nên cộng thêm 1 giây và giữ 500.000.000 nano. `-1` nano làm lùi sang giây trước, còn phần nano của giây trước trở thành 999.999.999.

Có thể hình dung quy tắc chuẩn hóa (tính theo phép chia có làm tròn xuống và số dư không âm):

```text
extraSeconds = floorDiv(nanoAdjustment, 1_000_000_000)
finalSeconds = epochSecond + extraSeconds
finalNanos   = floorMod(nanoAdjustment, 1_000_000_000)
```

Đây là mô hình giải thích, không bắt buộc tự triển khai thay cho API. Với `nanoAdjustment=-1`, `floorDiv(-1, 1_000_000_000)=-1` và `floorMod(...) = 999_999_999`. Phép cộng giây hoặc kết quả `Instant` ngoài phạm vi hợp lệ có thể ném exception.

**Chú ý:** `getNano()` trả giá trị luôn chuẩn hóa (0–999.999.999); nó không phản ánh nguyên văn tham số `nanoAdjustment` truyền vào. Các giá trị `Instant.ofEpochSecond(10, 1_000_000_000L)` và `Instant.ofEpochSecond(11)` bằng nhau theo `equals()`.

## 5. Chuyển ngược về số giây, mili giây và nano giây

Khi đã có một `Instant`:

| Phương thức | Trả về | Độ chính xác / ý nghĩa |
| --- | --- | --- |
| `getEpochSecond()` | `long` | Giây nguyên, có thể âm |
| `getNano()` | `int` | Phần nano của giây, từ 0 đến 999.999.999 |
| `toEpochMilli()` | `long` | Mili giây nguyên từ epoch, **bỏ độ chính xác nhỏ hơn mili giây** |
| `toString()` | `String` | Biểu diễn văn bản ISO-8601 UTC, có `Z` |

```java
Instant value = Instant.ofEpochSecond(
        1_700_000_000L, 123_456_789);

long seconds = value.getEpochSecond(); // 1700000000
int nanos = value.getNano();           // 123456789
long millis = value.toEpochMilli();    // 1700000000123
```

`toEpochMilli()` không thể khôi phục phần `456_789` nano còn dư sau 123 mili giây. Nếu cần lưu đầy đủ độ chính xác nano giây, lưu **hai trường** `(epochSecond, nano)`, hoặc dùng định dạng văn bản ISO chuẩn cùng quy định độ phân giải.

### Mất chính xác khi quy về mili giây

```java
Instant original = Instant.ofEpochSecond(5, 123_456_789);
Instant restored = Instant.ofEpochMilli(original.toEpochMilli());

System.out.println(original); // 1970-01-01T00:00:05.123456789Z
System.out.println(restored); // 1970-01-01T00:00:05.123Z
System.out.println(original.equals(restored)); // false
```

Bởi mili giây chỉ chứa 3 chữ số thập phân, trong khi nano giây chứa đến 9 chữ số. Khi xuất dữ liệu từ cơ sở dữ liệu hoặc API, hãy chọn kiểu lưu và độ phân giải theo yêu cầu thực tế, không tự mặc định toàn bộ thời gian là mili giây.

### `toEpochMilli()` và timestamp âm có phần lẻ

Với instant `1969-12-31T23:59:59.999999999Z` (một nano giây trước epoch), giá trị `toEpochMilli()` là **-1**, không phải 0: khi diễn giải trên trục epoch, kết quả mili giây nằm ở đơn vị **trước** mốc 0. Không tự tính `getEpochSecond() * 1000 + getNano()/1_000_000` rồi giả định biểu thức đó luôn có ngữ nghĩa giống phép cắt phần lẻ của tổng số giây về 0; với đầu vào âm, phải xác định chính sách làm tròn chính xác.

Nếu cần lưu nano giây nguyên duy nhất từ epoch, phép nhân `epochSecond * 1_000_000_000L + nano` có thể **tràn `long`** đối với nhiều `Instant` hợp lệ. Lưu cặp số nguyên hoặc dùng `BigInteger` khi phạm vi dữ liệu thực sự yêu cầu; không để phép nhân tràn âm thầm.

## 6. Phân biệt giây, mili, micro và nano khi nhận dữ liệu

| Đơn vị timestamp | Ký hiệu thường gặp | Số đơn vị trong 1 giây | Cách tạo `Instant` |
| --- | --- | ---: | --- |
| Giây | `s`, `seconds` | 1 | `ofEpochSecond(seconds)` |
| Mili giây | `ms`, `millis` | 1.000 | `ofEpochMilli(millis)` |
| Micro giây | `µs`, `micros` | 1.000.000 | Tách thành giây + nano |
| Nano giây | `ns`, `nanos` | 1.000.000.000 | Tách thành giây + nano |

Ví dụ một đối tác cung cấp timestamp theo **micro giây** từ epoch:

```java
long epochMicros = -1L;

long seconds = Math.floorDiv(epochMicros, 1_000_000L);
long microsWithinSecond = Math.floorMod(epochMicros, 1_000_000L);

Instant instant = Instant.ofEpochSecond(
        seconds, microsWithinSecond * 1_000L);

System.out.println(instant);
// 1969-12-31T23:59:59.999999Z
```

Với số âm, `floorDiv`/`floorMod` đảm bảo phần nano không âm. Tương tự, khi nhận một `long` lưu **nanoseconds since epoch**:

```java
long epochNanos = -1L;
Instant instant = Instant.ofEpochSecond(
        Math.floorDiv(epochNanos, 1_000_000_000L),
        Math.floorMod(epochNanos, 1_000_000_000L));
```

Giá trị `-1` nano tạo `1969-12-31T23:59:59.999999999Z`. Lưu ý `long` biểu diễn tổng nano giây từ epoch chỉ bao phủ khoảng vài trăm năm quanh 1970, hẹp hơn nhiều so với phạm vi `Instant`.

**Không thử đoán** số đầu vào là micro/nano chỉ từ số chữ số: đây là hợp đồng của nguồn dữ liệu, cần xác nhận qua tài liệu, schema và test biên.

## 7. Phạm vi hỗ trợ và xử lý lỗi

`Instant` có phạm vi biểu diễn rộng (xấp xỉ từ một tỷ năm trước đến một tỷ năm sau mốc hiện đại), nhưng **không phải mọi số `long` đều là epoch giây hợp lệ**. Các phương thức tạo có thể ném `DateTimeException` nếu kết quả ngoài phạm vi `Instant`; trong một số thao tác chuẩn hóa/tính toán lớn có thể có `ArithmeticException` khi tràn số. `toEpochMilli()` cũng có thể ném `ArithmeticException` khi kết quả mili giây vượt phạm vi `long`.

Ví dụ một `Instant` hợp lệ vẫn có thể không chuyển được thành `long` mili giây:

```java
Instant farFuture = Instant.MAX;

try {
    long millis = farFuture.toEpochMilli();
    System.out.println(millis);
} catch (ArithmeticException ex) {
    System.out.println("out of long millisecond range");
}
```

Đoạn trên là ví dụ minh họa chạy trong một `main` hoặc phương thức có import `java.time.Instant`. Không nên “chữa lỗi” bằng cách ép kiểu hay cắt bớt chữ số: làm vậy thay đổi giá trị thời gian. Hãy xác định phạm vi ngày hợp lệ của nghiệp vụ và validate đầu vào trước khi lưu.

### `int`, `long` và JSON number

- Epoch mili giây hiện đại thường lớn hơn giới hạn `int`, nên dùng `long`.
- JavaScript/JSON client dùng số dấu phẩy động có thể mất độ chính xác nguyên vượt **2^53 - 1**. Đặc biệt timestamp nano giây hiện đại tính từ epoch lớn hơn rất nhiều giới hạn này; hãy thống nhất cách truyền `string`, cặp `seconds + nanos` hoặc chuẩn timestamp phù hợp.
- Nếu hệ thống lưu timestamp ở mili giây nhưng khách hàng gửi nano giây, phải chọn chính sách **làm tròn hoặc cắt độ chính xác** và ghi rõ, thay vì ngầm giả định hai bên cùng đơn vị.

## 8. Chương trình Java 17+ chạy độc lập

Tạo tệp **`InstantEpochDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;

public class InstantEpochDemo {
    public static void main(String[] args) {
        Instant epoch = Instant.ofEpochSecond(0);
        Instant fromSeconds = Instant.ofEpochSecond(1_700_000_000L);
        Instant fromMillis = Instant.ofEpochMilli(1_700_000_000_000L);
        Instant precise = Instant.ofEpochSecond(
                1_700_000_000L, 123_456_789L);

        System.out.println("epoch = " + epoch);
        System.out.println("seconds = " + fromSeconds);
        System.out.println("millis = " + fromMillis);
        System.out.println("seconds match millis = "
                + fromSeconds.equals(fromMillis));
        System.out.println("precise = " + precise);
        System.out.println("precise seconds = " + precise.getEpochSecond());
        System.out.println("precise nanos = " + precise.getNano());
        System.out.println("precise epoch millis = " + precise.toEpochMilli());

        Instant carry = Instant.ofEpochSecond(10, 1_500_000_000L);
        Instant borrow = Instant.ofEpochSecond(10, -1L);
        System.out.println("carry = " + carry);
        System.out.println("borrow = " + borrow);

        Instant minusOneMilli = Instant.ofEpochMilli(-1);
        System.out.println("minus one millis = " + minusOneMilli);
        System.out.println("minus one second part = "
                + minusOneMilli.getEpochSecond());
        System.out.println("minus one nano part = "
                + minusOneMilli.getNano());

        Instant source = Instant.ofEpochSecond(5, 123_456_789);
        Instant roundedMillis = Instant.ofEpochMilli(source.toEpochMilli());
        System.out.println("original nanos = " + source);
        System.out.println("restored from millis = " + roundedMillis);
        System.out.println("exact round trip = "
                + source.equals(roundedMillis));

        System.out.println("Vietnam display = "
                + fromSeconds.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
    }
}
```

Biên dịch/chạy:

```bash
javac InstantEpochDemo.java
java InstantEpochDemo
```

Kết quả dự kiến:

```text
epoch = 1970-01-01T00:00:00Z
seconds = 2023-11-14T22:13:20Z
millis = 2023-11-14T22:13:20Z
seconds match millis = true
precise = 2023-11-14T22:13:20.123456789Z
precise seconds = 1700000000
precise nanos = 123456789
precise epoch millis = 1700000000123
carry = 1970-01-01T00:00:11.500Z
borrow = 1970-01-01T00:00:09.999999999Z
minus one millis = 1969-12-31T23:59:59.999Z
minus one second part = -1
minus one nano part = 999000000
original nanos = 1970-01-01T00:00:05.123456789Z
restored from millis = 1970-01-01T00:00:05.123Z
exact round trip = false
Vietnam display = 2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
```

Chương trình không sử dụng đồng hồ hiện tại hoặc múi giờ mặc định. Các giá trị là hằng số, nên kết quả ổn định trên JDK 17+ với bộ quy tắc múi giờ có `Asia/Ho_Chi_Minh` tại năm 2023.

## 9. Đối chiếu với các nguồn timestamp quen thuộc

### `System.currentTimeMillis()`

```java
long nowMillis = System.currentTimeMillis();
Instant instant = Instant.ofEpochMilli(nowMillis);
```

Đây là cách chuyển từ **số mili giây do đồng hồ hệ thống báo** sang `Instant`. Giá trị trả về không có bảo đảm đo chính xác tới mili giây ở mọi nền tảng, và đồng hồ hệ thống có thể bị điều chỉnh. Nếu chỉ cần lấy một instant hiện tại theo API hiện đại, dùng `Instant.now()` hoặc `Instant.now(clock)`.

### `java.util.Date`

```java
java.util.Date legacy = new java.util.Date(1_700_000_000_123L);
Instant instant = legacy.toInstant();
Instant same = Instant.ofEpochMilli(legacy.getTime());

System.out.println(instant.equals(same)); // true
```

`Date.getTime()` có đơn vị mili giây; việc chuyển qua `Instant` **không tự tạo lại phần nano giây đã không tồn tại** trong dữ liệu `Date`.

### `LocalDateTime` là một đại lượng khác

`LocalDateTime` lưu ngày giờ địa phương **không có offset**. Do đó không thể tự tính “epoch giây” chính xác từ `LocalDateTime` nếu chưa biết offset hoặc zone của sự kiện. Ví dụ:

```java
Instant instant = Instant.ofEpochSecond(1_700_000_000L);
LocalDateTime vietnamTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDateTime();
```

Muốn đi chiều ngược, phải cung cấp offset/vùng hợp lệ cho ngày giờ tương ứng; nếu vùng có DST, cần giải quyết giờ không tồn tại hoặc giờ trùng. **Không mặc định epoch timestamp là giờ địa phương**.

## 10. Lỗi phổ biến

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `ofEpochSecond(epochMillis)` | Timestamp lệch nhiều năm hoặc vượt phạm vi | Dùng `ofEpochMilli` khi nguồn là mili giây |
| Gọi `ofEpochMilli(epochSeconds)` | Thời điểm bị kéo gần về 1970 | Dùng `ofEpochSecond` khi nguồn là giây |
| Truyền `123` vào nano adjustment để biểu diễn 123 ms | Chỉ tạo **123 nano giây** | 123 ms = `123_000_000` nano |
| Nghĩ nano adjustment bắt buộc trong 0–999.999.999 | Bỏ qua quy tắc chuẩn hóa | `ofEpochSecond` hỗ trợ điều chỉnh âm hoặc vượt 1 tỷ nano |
| Nghĩ `getNano()` có thể âm trước epoch | Sai mô hình lưu giá trị | `getNano()` luôn 0–999.999.999 |
| Chia/tách epoch âm với quy tắc làm tròn sai | Lệch 1 giây hoặc 1 ms gần epoch | Sử dụng `ofEpochMilli`, `floorDiv`/`floorMod` |
| Chuyển nano sang `long` mili giây rồi mong giữ nguyên | Mất độ chính xác dưới mili giây | Lưu cặp `seconds + nanos` nếu cần round-trip |
| Nhân `epochSecond * 1_000_000_000L` vô điều kiện | Có thể tràn `long` | Kiểm tra giới hạn hoặc dùng `BigInteger` |
| Cho rằng `Instant` tự mang timezone | Hiển thị sai ngày/giờ địa phương | Khi hiển thị dùng `atZone(ZoneId)` |
| Lấy số timestamp của đối tác mà không kiểm tra đơn vị | Dữ liệu sai hàng loạt | Định nghĩa rõ s/ms/µs/ns trong schema và test |
| Nghĩ `Instant.now()` luôn chính xác nano giây | Đánh đồng cách lưu với chất lượng clock | Kiểm tra nguồn thời gian/độ chính xác thực tế |

## 11. Bài tập tự kiểm tra

**1.** Hai cách tạo nào trỏ đến cùng một thời điểm?

```java
Instant.ofEpochSecond(1_700_000_000L)
Instant.ofEpochMilli(1_700_000_000_000L)
```

→ **Cùng một thời điểm**, vì 1 giây = 1.000 mili giây.

**2.** `Instant.ofEpochSecond(10, -1)` có `epochSecond` và `nano` là bao nhiêu?

→ `epochSecond = 9`, `nano = 999_999_999`.

**3.** `Instant.ofEpochMilli(-1)` có `getEpochSecond() == 0` không?

→ **Không**. Giá trị là `-1`, `getNano() = 999_000_000`; tổng giá trị đúng bằng âm một mili giây.

**4.** Vì sao `Instant.ofEpochSecond(5,123_456_789)` không thể round-trip nguyên vẹn qua `toEpochMilli()`?

→ Phần `456_789` nano vượt quá độ phân giải mili giây bị bỏ; cần giữ cặp giây và nano để không mất thông tin.

**5.** Có thể gọi `LocalDateTime.of(...)` rồi lấy epoch seconds mà không có offset không?

→ Không xác định được instant tuyệt đối khi thiếu offset/vùng. Phải xác định ngữ cảnh múi giờ đúng.

**6.** Nếu API gửi timestamp tính bằng micro giây, có nên truyền nguyên giá trị đó vào `ofEpochMilli` không?

→ Không. Phải đổi đúng đơn vị, ví dụ tách `floorDiv(micros,1_000_000)` giây và `floorMod(micros,1_000_000)*1_000` nano.

### Tài liệu tham khảo

- [Oracle Java SE 21 — `Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): `ofEpochSecond`, `ofEpochMilli`, `getEpochSecond`, `getNano`, `toEpochMilli` và phạm vi hỗ trợ.
- [Oracle Java SE 21 — `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): biểu diễn instant theo vùng giờ.
- [Oracle Java SE 21 — `Date`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html): chuyển tiếp giữa kiểu legacy `Date` và `Instant`.

**Ghi nhớ:** Epoch seconds đếm theo **giây**, epoch milliseconds đếm theo **mili giây**, và overload `ofEpochSecond(seconds,nanoAdjustment)` giúp biểu diễn **phần nano giây** chính xác, bao gồm cả chuẩn hóa số âm hoặc vượt một giây. Khi chuyển về mili giây, dữ liệu dưới mili giây bị mất; khi hiển thị giờ địa phương, phải chọn timezone một cách tường minh.
