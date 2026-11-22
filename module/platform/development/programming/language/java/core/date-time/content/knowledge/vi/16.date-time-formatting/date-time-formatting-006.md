# Giờ 12 tiếng, 24 tiếng và ký hiệu AM/PM trong Java

## 1. Hai cách biểu diễn giờ

Java cung cấp `java.time.LocalTime` để biểu diễn giờ trong ngày độc lập với ngày lịch và múi giờ. Một giá trị như `LocalTime.of(13, 5, 9)` lưu giờ 13, phút 5, giây 9. Khi hiển thị, ứng dụng có thể chọn dạng **24 tiếng** (13:05:09) hoặc **12 tiếng kèm AM/PM** (01:05:09 PM).

Hai cách biểu diễn chỉ là hai kiểu trình bày của cùng một giờ:

| Giờ 24 tiếng | Giờ 12 tiếng | Ký hiệu |
|---|---|---|
| 00:00 | 12:00 AM | Nửa đêm |
| 01:00 | 01:00 AM | Một giờ sáng |
| 11:59 | 11:59 AM | Trước buổi trưa |
| 12:00 | 12:00 PM | Buổi trưa |
| 12:01 | 12:01 PM | Sau buổi trưa |
| 13:00 | 01:00 PM | Một giờ chiều |
| 23:59 | 11:59 PM | Trước nửa đêm |

Trong định dạng 24 tiếng, trường giờ thường nằm trong `00..23`. Trong định dạng 12 tiếng, giờ trên mặt đồng hồ nằm trong `1..12`, còn AM/PM xác định nửa ngày. **12 AM là nửa đêm; 12 PM là buổi trưa.** Đừng chỉ lấy `hour % 12` rồi quên bổ sung AM/PM, vì cách đó biến cả 00:00 lẫn 12:00 thành 12:00 và làm mất thông tin cần thiết.

Bài học dùng `DateTimeFormatter` để chuyển đổi định dạng, đọc các mẫu quan trọng, parse chuỗi 12 tiếng thành một giá trị `LocalTime`, xử lý locale và kiểm tra các lỗi thường gặp.

## 2. Các ký tự pattern quan trọng

`DateTimeFormatter` dùng pattern chữ hoa/thường để chọn trường giờ. Với định dạng giờ, bốn ký tự dễ nhầm nhất là `H`, `h`, `K` và `k`:

| Pattern | Tên trường | Miền giờ | Nửa đêm | Buổi trưa |
|---|---|---:|---|---|
| `H` / `HH` | Hour-of-day, 24 tiếng | 0–23 | 0 / 00 | 12 / 12 |
| `h` / `hh` | Clock-hour-of-am-pm, 12 tiếng | 1–12 | 12 | 12 |
| `K` / `KK` | Hour-of-am-pm, 12 tiếng bắt đầu từ 0 | 0–11 | 0 | 0 |
| `k` / `kk` | Clock-hour-of-day, 24 tiếng theo miền 1–24 | 1–24 | 24 | 12 |

Trong đa số giao diện phổ thông, dùng `HH:mm` cho giờ 24 tiếng và `hh:mm a` cho giờ 12 tiếng có AM/PM. `H` phù hợp khi giờ 0 cần được hiển thị là `0` thay vì `00`; `HH` đảm bảo hai chữ số khi format. Tương tự, `h` cho giờ 1–12 không đệm số 0, `hh` hiển thị 01–12.

`K` và `k` hợp lệ nhưng ít phổ biến trong giao diện thông thường. `K` đếm 0–11 trong nửa ngày; `k` đếm 1–24 trong ngày và thể hiện nửa đêm là 24. Với dữ liệu hiển thị hoặc trao đổi, chỉ dùng các dạng đó khi hợp đồng định dạng yêu cầu đúng ngữ nghĩa tương ứng.

Ký hiệu bổ sung:

| Pattern | Ý nghĩa | Ví dụ |
|---|---|---|
| `m` / `mm` | Phút | `5` / `05` |
| `s` / `ss` | Giây | `9` / `09` |
| `a` | Ký hiệu AM/PM theo locale | `AM` / `PM` trong Locale.US |
| `'text'` | Văn bản literal được trích dẫn | `hh 'giờ' mm` |
| `'T'` | Chữ T literal | Có thể dùng khi tự ghép ngày và giờ ISO |

**Cẩn thận:** `MM` là **tháng**, còn `mm` là **phút**. `HH` là giờ 24 tiếng, `hh` là giờ 12 tiếng; khác nhau chỉ ở chữ hoa/thường nhưng kết quả hoàn toàn khác.

## 3. Format giờ 24 tiếng

Để hiển thị giờ theo dạng 24 tiếng:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalTime time = LocalTime.of(13, 5, 9);
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);

System.out.println(time.format(formatter));
~~~

Stdout:

~~~text
13:05:09
~~~

`HH:mm:ss` có nghĩa:

- `HH`: giờ 00–23, luôn đủ hai chữ số khi format.
- `mm`: phút 00–59.
- `ss`: giây 00–59.

Một vài thời điểm:

~~~java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
System.out.println(LocalTime.MIDNIGHT.format(f));
System.out.println(LocalTime.NOON.format(f));
System.out.println(LocalTime.of(9, 7).format(f));
~~~

Stdout:

~~~text
00:00
12:00
09:07
~~~

`LocalTime.MIDNIGHT` biểu diễn `00:00`; `LocalTime.NOON` biểu diễn `12:00`. Với định dạng 24 tiếng, không thêm `a` vì ký hiệu AM/PM không cần thiết và thường không thuộc định dạng này.

Trong ứng dụng cần chuẩn hóa dữ liệu máy đọc, một định dạng 24 tiếng như `HH:mm:ss` giúp tránh sự mơ hồ về AM/PM. Nếu cần phần nano giây, hãy dùng formatter có phần thập phân tương ứng, chẳng hạn `HH:mm:ss.SSSSSSSSS`; điều đó chỉ định dạng phần nano đã lưu, không làm tăng độ chính xác của đồng hồ nguồn.

## 4. Format giờ 12 tiếng với AM/PM

Mẫu thường dùng:

~~~java
DateTimeFormatter twelveHour =
        DateTimeFormatter.ofPattern("hh:mm:ss a", Locale.US);

LocalTime time = LocalTime.of(13, 5, 9);
System.out.println(time.format(twelveHour));
~~~

Stdout:

~~~text
01:05:09 PM
~~~

`hh` chuyển sang trường giờ 1–12, `mm` là phút, `ss` là giây, `a` tạo ký hiệu AM/PM theo locale. Có thể bỏ giây khi giao diện chỉ cần giờ và phút:

~~~java
DateTimeFormatter shortTwelve =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
System.out.println(LocalTime.of(9, 5).format(shortTwelve));
System.out.println(LocalTime.of(13, 5).format(shortTwelve));
~~~

Stdout:

~~~text
9:05 AM
1:05 PM
~~~

`h:mm a` không đệm số 0 trước giờ; `hh:mm a` có đệm 0. Hãy chọn mẫu theo thiết kế giao diện và hợp đồng dữ liệu. Khi parse, đừng phụ thuộc vào số lượng chữ số hiển thị để xác định một thời điểm; dùng formatter rõ ràng để diễn giải trường giờ và ký hiệu AM/PM.

### 4.1. Nửa đêm và buổi trưa

Đây là các trường hợp cần kiểm tra riêng:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

System.out.println(LocalTime.MIDNIGHT.format(f));
System.out.println(LocalTime.NOON.format(f));
System.out.println(LocalTime.of(0, 1).format(f));
System.out.println(LocalTime.of(12, 1).format(f));
~~~

Stdout:

~~~text
12:00 AM
12:00 PM
12:01 AM
12:01 PM
~~~

Quy tắc chuyển đổi giờ có thể hình dung như sau:

- Giờ 00 trong dạng 24 tiếng → 12 AM.
- Giờ 01–11 → giữ nguyên giờ, AM.
- Giờ 12 → 12 PM.
- Giờ 13–23 → trừ 12 để có 01–11 PM.

Để đổi ngược từ giờ 12 tiếng sang giờ 24 tiếng, dựa vào giờ và AM/PM: với AM, 12 giờ trở thành 0; với PM, giờ 1–11 được cộng 12, còn 12 PM vẫn là 12. Khi parse, nên để `DateTimeFormatter` xử lý quy tắc thay vì tự chia chuỗi hoặc viết các phép toán số rời rạc.

## 5. Parse chuỗi 12 tiếng thành LocalTime

`LocalTime.parse(text, formatter)` cho phép đọc chuỗi với định dạng đã nêu. Ví dụ:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter inputFormat =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);

LocalTime morning = LocalTime.parse("9:05 AM", inputFormat);
LocalTime afternoon = LocalTime.parse("1:05 PM", inputFormat);

System.out.println(morning);
System.out.println(afternoon);
~~~

Stdout:

~~~text
09:05
13:05
~~~

Sau khi parse, `LocalTime` lưu giá trị giờ 24 tiếng nội bộ theo trường giờ từ 0 đến 23. `toString()` hiển thị biểu diễn ISO dạng local time, nên `13:05` xuất hiện thay vì chuỗi `1:05 PM`. Muốn hiển thị lại theo 12 tiếng, format giá trị đó với formatter 12 tiếng.

### 5.1. Parse giờ 12 tiếng và kiểm tra sai dữ liệu

Lưu ví dụ độc lập thành **`TimeFormatDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class TimeFormatDemo {
    public static void main(String[] args) {
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);
        DateTimeFormatter twentyFour =
                DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);

        LocalTime midnight = LocalTime.parse("12:00 AM", twelve);
        LocalTime noon = LocalTime.parse("12:00 PM", twelve);
        LocalTime afternoon = LocalTime.parse("01:05 PM", twelve);

        System.out.println("Midnight: " + midnight.format(twentyFour));
        System.out.println("Noon: " + noon.format(twentyFour));
        System.out.println("Afternoon: " + afternoon.format(twentyFour));
        System.out.println("Back to 12-hour: " + afternoon.format(twelve));

        try {
            LocalTime.parse("13:05 PM", twelve);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid 12-hour time rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TimeFormatDemo.java
java TimeFormatDemo
~~~

Stdout:

~~~text
Midnight: 00:00:00
Noon: 12:00:00
Afternoon: 13:05:00
Back to 12-hour: 01:05 PM
Invalid 12-hour time rejected
~~~

Ví dụ kiểm tra `13:05 PM`: giờ 13 là dạng 24 tiếng, trong khi mẫu đầu vào đang yêu cầu giờ 12 tiếng cùng AM/PM. Formatter không nên được dùng như một phép đoán ý định; cần xác định định dạng nhận vào và báo lỗi khi đầu vào không tuân theo hợp đồng.

## 6. Locale ảnh hưởng AM/PM

`DateTimeFormatter.ofPattern(pattern, locale)` dùng locale để biểu diễn các trường phụ thuộc ngôn ngữ, bao gồm ký hiệu AM/PM. Với `Locale.US`, mẫu `h:mm a` thường hiển thị như `1:05 PM`. Locale khác có thể sử dụng chữ viết hoặc cách trình bày khác.

~~~java
LocalTime time = LocalTime.of(13, 5);
DateTimeFormatter us =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
DateTimeFormatter root =
        DateTimeFormatter.ofPattern("h:mm a", Locale.ROOT);

System.out.println(time.format(us));
System.out.println(time.format(root));
~~~

Locale.ROOT chủ yếu phù hợp cho dạng ổn định, không mang ngữ nghĩa ngôn ngữ; với dữ liệu AM/PM dành cho người dùng, hãy chọn locale theo yêu cầu giao diện. Không giả định mọi locale sẽ luôn in đúng hai chữ cái ASCII `AM` và `PM`. Đầu ra phụ thuộc dữ liệu locale của JDK và mẫu được sử dụng.

Trong sản phẩm đa ngôn ngữ, phân biệt rõ:

- **Định dạng giao diện:** dùng locale người dùng, có thể dịch ký hiệu và thay đổi quy ước.
- **Định dạng lưu trữ hoặc giao tiếp:** dùng mẫu đã thống nhất, thường là định dạng chuẩn hóa 24 tiếng/ISO, tránh phụ thuộc locale.
- **Đầu vào từ người dùng:** biết locale/định dạng được chấp nhận, parse theo formatter phù hợp, rồi xác nhận giá trị hợp lệ.

Không dùng chuỗi đã dịch theo locale làm khóa dữ liệu hoặc so sánh văn bản cứng với `"AM"`/`"PM"` khi ứng dụng hỗ trợ nhiều ngôn ngữ.

## 7. DateTimeFormatter là bất biến và có thể tái sử dụng

`DateTimeFormatter` là immutable và thread-safe, do đó có thể khai báo formatter dùng chung:

~~~java
private static final DateTimeFormatter DISPLAY_12H =
        DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

private static final DateTimeFormatter STORAGE_24H =
        DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);
~~~

Các khai báo này phải nằm trong thân lớp Java; không đặt `private static final` trực tiếp trong phương thức `main`. Tái sử dụng formatter giúp tránh tạo cùng một mẫu lặp đi lặp lại và làm rõ quy ước định dạng.

Không nhầm `DateTimeFormatter` với `SimpleDateFormat` của API cũ. `DateTimeFormatter` có thiết kế bất biến nên phù hợp dùng chung; `SimpleDateFormat` không thread-safe nếu chia sẻ mà không có cơ chế bảo vệ.

## 8. Pattern h/H và các lỗi thường gặp

### 8.1. Dùng H với a

`HH:mm a` kết hợp giờ 24 tiếng với AM/PM. Mẫu có thể tạo chuỗi khó hiểu như `13:05 PM`; tránh dùng cách kết hợp này trong một giao diện phổ thông nếu mục tiêu là định dạng giờ 12 tiếng.

Dùng:

~~~text
HH:mm       → 13:05
hh:mm a     → 01:05 PM
h:mm a      → 1:05 PM
~~~

### 8.2. Nhầm tháng với phút

`MM` là tháng, `mm` là phút. Pattern `hh:MM a` có thể in một trường tháng trong chỗ mà người viết tưởng đang hiển thị phút. Khi làm với `LocalTime`, trường tháng không có sẵn và formatter có thể báo lỗi vì kiểu nguồn không cung cấp trường đó.

### 8.3. Quên AM/PM khi parse

Chuỗi `01:05` không xác định rõ là sáng hay chiều trong đồng hồ 12 tiếng. Nếu dữ liệu thật là giờ 12 tiếng thì cần nhận ký hiệu AM/PM hoặc có quy tắc mặc định rõ ràng; không thể tự suy ra từ chuỗi đơn lẻ.

### 8.4. Nhầm 12 AM và 12 PM

`12:00 AM` là `00:00` trong đồng hồ 24 tiếng. `12:00 PM` là `12:00`. Kiểm thử riêng hai giá trị này và các thời điểm ngay hai bên, ví dụ `11:59 AM`, `12:01 PM`.

### 8.5. Dùng giờ địa phương làm thời điểm tuyệt đối

`LocalTime` chỉ lưu giờ trong ngày. `13:05` không cho biết ngày nào hoặc múi giờ nào; nó không đủ thông tin để xác định một instant. Nếu dữ liệu là thời điểm sự kiện, dùng `Instant` hoặc kiểu ngày giờ có offset/zone phù hợp, rồi chọn formatter theo zone đã xác định.

### 8.6. Hiểu pattern như một ngôn ngữ không có quy tắc

Các chữ cái pattern có ý nghĩa riêng, chữ hoa/thường khác nhau. Nếu mẫu đến từ cấu hình, nên kiểm tra tính hợp lệ khi khởi tạo ứng dụng; mẫu sai có thể gây `IllegalArgumentException`. Lỗi parse văn bản thường là `DateTimeParseException` (lớp con của `DateTimeException`); nên báo lỗi đầu vào rõ ràng thay vì dùng giờ hiện tại thay thế.

## 9. Ví dụ nhanh với bảng quy đổi

Bảng sau giúp so lại các giá trị phổ biến khi đổi định dạng:

| `LocalTime` | `HH:mm` | `hh:mm a` (Locale.US) |
|---|---|---|
| `00:00` | `00:00` | `12:00 AM` |
| `00:15` | `00:15` | `12:15 AM` |
| `06:30` | `06:30` | `06:30 AM` |
| `11:59` | `11:59` | `11:59 AM` |
| `12:00` | `12:00` | `12:00 PM` |
| `12:45` | `12:45` | `12:45 PM` |
| `13:05` | `13:05` | `01:05 PM` |
| `23:59` | `23:59` | `11:59 PM` |

Định dạng trình bày không thay đổi giá trị `LocalTime`. Cùng một object có thể được format qua nhiều formatter mà không cần tạo object khác.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Pattern nào dùng cho giờ 24 tiếng có hai chữ số?

**Đáp án:** `HH:mm` hoặc `HH:mm:ss`. `HH` biểu diễn giờ 00–23.

**Câu 2.** Pattern nào biểu diễn giờ 12 tiếng với AM/PM?

**Đáp án:** Ví dụ `hh:mm a` để có giờ được đệm 0; `h:mm a` nếu không muốn đệm 0. `a` đưa ký hiệu AM/PM theo locale.

**Câu 3.** Trong giờ 12 tiếng, `12:00 AM` và `12:00 PM` tương ứng với giá trị nào?

**Đáp án:** `12:00 AM → 00:00`; `12:00 PM → 12:00`.

**Câu 4.** Vì sao `LocalTime.parse("1:05 PM", formatter)` có thể trả object mà `toString()` hiển thị `13:05`?

**Đáp án:** `LocalTime` lưu giờ bằng trường giờ 0–23, không giữ cách gõ ban đầu hay ký hiệu AM/PM. Muốn hiển thị lại 12 tiếng, phải format với formatter 12 tiếng.

**Câu 5.** Khác biệt giữa `HH` và `hh` là gì?

**Đáp án:** `HH` dùng giờ 0–23; `hh` dùng giờ 1–12 và thường ghép `a` để phân biệt sáng/chiều.

**Câu 6.** Vì sao cần truyền Locale vào `ofPattern`?

**Đáp án:** Locale quyết định văn bản phụ thuộc ngôn ngữ như AM/PM. Điều này quan trọng với giao diện đa ngôn ngữ và khi parse văn bản theo locale.

**Câu 7.** Có nên dùng `hh:mm a` làm định dạng dữ liệu trao đổi mặc định giữa các hệ thống?

**Đáp án:** Chỉ khi hợp đồng hai bên quy định rõ định dạng và locale. Với giao tiếp máy–máy, một định dạng ổn định như ISO local time/24 tiếng thường ít mơ hồ hơn.

## 11. Quy tắc thực hành

- Dùng `HH:mm:ss` cho giờ 24 tiếng; `hh:mm:ss a` hoặc `h:mm a` cho giờ 12 tiếng có AM/PM.
- Đọc đúng hoa/thường: `H` = 0–23, `h` = 1–12, `K` = 0–11, `k` = 1–24, `m` = phút, `M` = tháng.
- Luôn kiểm thử nửa đêm và buổi trưa, vì quy tắc `12 AM/PM` dễ bị đảo.
- Parse theo định dạng đầu vào đã biết, chỉ định locale phù hợp, và xử lý `DateTimeParseException` khi chuỗi không hợp lệ.
- Tách **giá trị thời gian** khỏi **chuỗi hiển thị**: parse về `LocalTime`, giữ giá trị typed, rồi format theo giao diện cần thiết.
- Với sự kiện thực tế, nhớ rằng `LocalTime` không chứa ngày hay múi giờ; chọn kiểu thời gian giàu thông tin hơn nếu cần một thời điểm duy nhất.

`DateTimeFormatter` cho phép ứng dụng đổi giữa giờ 12 tiếng và 24 tiếng mà không thay đổi giá trị thời gian. Chọn đúng pattern và locale, xử lý chuẩn các trường hợp 12 AM/PM và thống nhất định dạng đầu vào/đầu ra sẽ tránh được phần lớn lỗi hiển thị giờ.
