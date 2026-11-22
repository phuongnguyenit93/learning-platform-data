# Phân biệt `MM` với `mm`, `dd` với `DD` trong Java

Trong `DateTimeFormatter`, các ký hiệu định dạng ngày giờ **phân biệt chữ hoa và chữ thường**. Chỉ đổi kiểu chữ có thể làm dữ liệu sai mà không gây lỗi cú pháp: `MM` là **tháng**, `mm` là **phút**; `dd` là **ngày trong tháng**, còn `DD` là **ngày thứ bao nhiêu trong năm**.

Ví dụ ngày `2025-02-03` và giờ `16:07:09`:

| Pattern | Nghĩa | Kết quả |
| --- | --- | --- |
| `MM/dd/yyyy` | Tháng / ngày trong tháng / năm | `02/03/2025` |
| `HH:mm:ss` | Giờ / phút / giây | `16:07:09` |
| `dd / DD` với ngày 03/02/2025 | Ngày trong tháng / ngày trong năm | `03 / 34` |
| `M / MM` | Tháng không đệm số 0 / có đệm | `2 / 02` |
| `m / mm` | Phút không đệm số 0 / có đệm | `7 / 07` |

Bởi vậy, pattern trông quen thuộc như `yyyy-mm-dd` là sai nếu mục tiêu là ngày theo định dạng năm-tháng-ngày: trường `mm` sẽ là phút, không phải tháng. Dùng `yyyy-MM-dd` cho ngày lịch, hoặc ưu tiên `DateTimeFormatter.ISO_LOCAL_DATE` khi hợp đồng yêu cầu ngày ISO `uuuu-MM-dd`.

## 1. Bốn ký hiệu cần phân biệt

### `M` và `MM` — tháng

- `M`: số tháng không bắt buộc có số 0 ở đầu, ví dụ tháng 2 in là `2`.
- `MM`: tháng với độ rộng hai chữ số, ví dụ tháng 2 in là `02`.
- `MMM`: tên tháng dạng rút gọn theo locale, ví dụ tiếng Anh thường là `Feb`.
- `MMMM`: tên tháng đầy đủ theo locale, ví dụ tiếng Anh `February`.

Các ký hiệu `M` viết hoa nói về **tháng trong năm**. Khi parse, `MM` là giá trị số tháng, không phải phút.

### `m` và `mm` — phút

- `m`: phút không đệm số 0, ví dụ phút 7 in là `7`.
- `mm`: phút có đệm số 0, ví dụ phút 7 in là `07`.

Chữ `m` thường là phút, khác với chữ `M` viết hoa là tháng. Một thời điểm 16:07 không được viết phút bằng `MM`; pattern chính xác cho giờ/phút thường là `HH:mm` hoặc `H:mm` tùy cách hiển thị mong muốn.

### `d` và `dd` — ngày trong tháng

- `d`: ngày trong tháng không đệm số 0, ví dụ ngày 3 in là `3`.
- `dd`: ngày trong tháng có đệm số 0, ví dụ ngày 3 in là `03`.

Chữ `d` viết thường biểu diễn ngày trong tháng, thường trong miền 1–28/29/30/31 tùy tháng và năm. Đây là trường phù hợp khi cần hiển thị một ngày lịch thông thường.

### `D` và `DD` — ngày thứ bao nhiêu trong năm

- `D`: ngày trong năm không đệm số 0, ví dụ ngày thứ 34 in là `34`.
- `DD`: ngày trong năm được đệm tối thiểu hai chữ số; ngày thứ 34 vẫn là `34`, ngày thứ 3 là `03`.
- `DDD`: độ rộng ba chữ số, thường dùng để thể hiện ngày trong năm từ `001` tới `365` hoặc `366`.

Chữ `D` viết hoa **không phải ngày trong tháng**. Nó là ngày thứ bao nhiêu kể từ đầu năm: ngày 1 tháng 1 là `1`, ngày 3 tháng 2 năm 2025 là ngày thứ `34`.

## 2. Vì sao `dd` và `DD` cho kết quả khác nhau?

Ngày 03/02/2025 (ngày 3 tháng 2) có thể biểu diễn theo hai cách:

```java
LocalDate date = LocalDate.of(2025, 2, 3);

DateTimeFormatter dayInMonth =
        DateTimeFormatter.ofPattern("dd", Locale.ROOT);
DateTimeFormatter dayInYear =
        DateTimeFormatter.ofPattern("DD", Locale.ROOT);

System.out.println(date.format(dayInMonth)); // 03
System.out.println(date.format(dayInYear));  // 34
```

Đoạn này cần `import java.time.*;` và `import java.time.format.DateTimeFormatter;` cùng `import java.util.Locale;`. Hai formatter nhận cùng một `LocalDate` nhưng yêu cầu hai trường khác nhau: ngày trong tháng và ngày trong năm.

Ngày thứ bao nhiêu trong năm thay đổi phụ thuộc năm nhuận. Ví dụ:

| Ngày | `dd` — ngày trong tháng | `DDD` — ngày trong năm |
| --- | ---: | ---: |
| 2025-01-01 | 01 | 001 |
| 2025-02-03 | 03 | 034 |
| 2024-02-29 | 29 | 060 |
| 2025-12-31 | 31 | 365 |
| 2024-12-31 | 31 | 366 |

Năm 2024 là năm nhuận nên có 366 ngày, còn 2025 có 365 ngày. Khi cần **định dạng ngày lịch**, gần như luôn dùng `dd` cho ngày trong tháng, không dùng `DD` trừ khi nghiệp vụ thực sự muốn ngày thứ bao nhiêu của năm (ví dụ báo cáo theo ngày thứ 034).

## 3. Ví dụ đầy đủ Java 17+: quan sát sự khác biệt trực tiếp

Lưu chương trình sau đúng tên **`DateTimePatternCaseDemo.java`**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DateTimePatternCaseDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 2, 3);
        LocalTime time = LocalTime.of(16, 7, 9);
        LocalDateTime dateTime = LocalDateTime.of(date, time);

        System.out.println("MM/dd/yyyy       : "
                + date.format(DateTimeFormatter.ofPattern(
                        "MM/dd/yyyy", Locale.ROOT)));
        System.out.println("HH:mm:ss         : "
                + time.format(DateTimeFormatter.ofPattern(
                        "HH:mm:ss", Locale.ROOT)));
        System.out.println("Combined         : "
                + dateTime.format(DateTimeFormatter.ofPattern(
                        "yyyy-MM-dd HH:mm:ss", Locale.ROOT)));
        System.out.println("dd / DD          : "
                + date.format(DateTimeFormatter.ofPattern(
                        "dd / DD", Locale.ROOT)));
        System.out.println("M / MM           : "
                + date.format(DateTimeFormatter.ofPattern(
                        "M / MM", Locale.ROOT)));
        System.out.println("m / mm           : "
                + time.format(DateTimeFormatter.ofPattern(
                        "m / mm", Locale.ROOT)));
        System.out.println("Day-of-year parse: "
                + LocalDate.parse("2025-034",
                        DateTimeFormatter.ofPattern(
                                "yyyy-DDD", Locale.ROOT)));
        System.out.println("ISO safe pattern : "
                + dateTime.format(
                        DateTimeFormatter.ISO_LOCAL_DATE_TIME));

        DateTimeFormatter localized =
                DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);
        System.out.println("Locale text      : "
                + date.format(localized));
        System.out.println("Month/day/year   : "
                + date.format(DateTimeFormatter.ofPattern(
                        "MM/dd/yyyy", Locale.US)));
        System.out.println("Day/month/year   : "
                + date.format(DateTimeFormatter.ofPattern(
                        "dd/MM/yyyy", Locale.US)));
        System.out.println("Week-based year  : "
                + date.format(DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.US)));
        System.out.println("Calendar year    : "
                + date.format(DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac DateTimePatternCaseDemo.java
java DateTimePatternCaseDemo
```

Đầu ra đã được kiểm chứng bằng cách biên dịch và chạy chương trình:

```text
MM/dd/yyyy       : 02/03/2025
HH:mm:ss         : 16:07:09
Combined         : 2025-02-03 16:07:09
dd / DD          : 03 / 34
M / MM           : 2 / 02
m / mm           : 7 / 07
Day-of-year parse: 2025-02-03
ISO safe pattern : 2025-02-03T16:07:09
Locale text      : 3 February 2025
Month/day/year   : 02/03/2025
Day/month/year   : 03/02/2025
Week-based year  : 2025-W06-2
Calendar year    : 2025-02-03
```

Những dòng quyết định:

- `MM/dd/yyyy` in `02/03/2025`, tức tháng 2, ngày 3, năm 2025.
- `HH:mm:ss` in `16:07:09`. Ở đây chữ `mm` viết thường giữ phút 07.
- `dd / DD` in `03 / 34`. Ngày trong tháng là 3; ngày thứ 34 trong năm là một giá trị khác.
- `M / MM` cho thấy khác biệt đệm số 0: `2` và `02`.
- `m / mm` cho thấy phút 7 in lần lượt `7` và `07`.
- `ISO_LOCAL_DATE_TIME` tạo chuỗi ISO như `2025-02-03T16:07:09` mà không cần tự chọn pattern.

## 4. Mẫu định dạng đúng cho những nhu cầu thường gặp

| Mục tiêu | Pattern ví dụ | Kết quả với ngày 03/02/2025, lúc 16:07:09 |
| --- | --- | --- |
| Ngày ISO | `uuuu-MM-dd` | `2025-02-03` |
| Ngày/tháng/năm | `dd/MM/uuuu` | `03/02/2025` |
| Tháng/ngày/năm | `MM/dd/uuuu` | `02/03/2025` |
| Giờ 24 giờ và phút | `HH:mm` | `16:07` |
| Giờ, phút, giây | `HH:mm:ss` | `16:07:09` |
| Ngày giờ dễ đọc | `dd/MM/uuuu HH:mm:ss` | `03/02/2025 16:07:09` |
| Ngày thứ trong năm | `DDD` | `034` |
| Tên tháng đầy đủ | `d MMMM uuuu` với `Locale.US` | `3 February 2025` |

Đối với dữ liệu máy hoặc hợp đồng API, ưu tiên một định dạng đã chuẩn hóa như `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_LOCAL_TIME` hoặc `ISO_LOCAL_DATE_TIME` nếu phù hợp với kiểu dữ liệu. Các pattern như `dd/MM/uuuu` hữu ích cho giao diện nhưng cần được quy định rõ để tránh nhầm lẫn khi dữ liệu đi qua vùng có định dạng ngày khác nhau.

**Lưu ý:** mẫu ngày/tháng/năm và tháng/ngày/năm có thể gây hiểu nhầm khi cả hai thành phần đều từ 1 đến 12. Ví dụ chuỗi `03/02/2025` có thể được đọc là ngày 3 tháng 2 hoặc ngày 2 tháng 3 tùy quy ước. Hãy thống nhất hợp đồng định dạng giữa bên gửi và bên nhận, đừng dựa vào locale mặc định của máy.

## 5. Cẩn thận với `yyyy`, `uuuu` và `YYYY`

Mặc dù chủ đề chính là `MM/mm` và `dd/DD`, các chữ hoa/thường trong pattern còn có các trường dễ nhầm khác:

- `yyyy`: năm theo **era** (year-of-era).
- `uuuu`: năm theo trục số năm của lịch ISO (proleptic year). Đây thường là lựa chọn rõ ràng cho định dạng lịch ISO, đặc biệt khi muốn cách diễn giải ổn định ở các miền năm ngoài Công nguyên.
- `YYYY`: **week-based year**, tức năm theo hệ tuần; không đồng nghĩa `yyyy` hay `uuuu`.
- `ww`: số tuần theo hệ tuần và locale/temporal field tương ứng.
- `e`/`E`: các ký hiệu liên quan ngày trong tuần, nhưng ý nghĩa hiển thị số/tên khác nhau tùy ký hiệu và locale.

Vì năm theo tuần có thể chuyển sang năm kế tiếp trước ngày 1 tháng 1 hoặc còn thuộc năm trước ở những ngày cuối tháng 12, `YYYY-MM-dd` không phải mẫu ngày thông thường nên dùng. Chẳng hạn các ngày sát đầu/cuối năm có thể được định dạng với week-based year khác với năm lịch.

Với ngày ISO thông thường, dùng `uuuu-MM-dd`; ví dụ `2025-02-03`. Dùng `YYYY` chỉ khi nghiệp vụ thực sự cần trường **năm theo tuần**, thường đi kèm mẫu tuần được định nghĩa rõ.

## 6. Phân tích pattern từng phần, không đoán theo hình thức

Khi đọc `DateTimeFormatter.ofPattern(pattern, locale)`, đừng nhìn chuỗi mẫu như một văn bản thường rồi đoán nghĩa. Mỗi ký hiệu có trường dữ liệu cụ thể:

| Ký hiệu | Trường | Gợi ý |
| --- | --- | --- |
| `M`, `MM` | Tháng trong năm | Chữ M viết hoa. |
| `m`, `mm` | Phút trong giờ | Chữ m viết thường. |
| `d`, `dd` | Ngày trong tháng | d thường; thường dùng cho lịch hàng ngày. |
| `D`, `DD`, `DDD` | Ngày trong năm | D hoa; giá trị 1–365/366. |
| `H`, `HH` | Giờ trong ngày theo chu kỳ 0–23 | H hoa biểu thị hệ 24 giờ. |
| `h`, `hh` | Giờ trong chu kỳ 1–12 | Thường kết hợp ký hiệu AM/PM. |
| `s`, `ss` | Giây trong phút | s thường, không phải mili giây. |
| `S`, `SSS` | Phần giây theo độ rộng ký hiệu | S hoa, không phải giây trong phút. |
| `a` | Dấu AM/PM | Ý nghĩa phụ thuộc locale và kiểu giờ. |
| `z` / `VV` | Thông tin vùng theo kiểu pattern tương ứng | Đừng nhầm với offset cố định hay tên kiểu dữ liệu địa phương. |
| `X` / `x` | Các kiểu biểu diễn offset | Kết quả khác nhau theo số lượng ký tự pattern. |

Bảng này là bản định hướng, không thay cho quy tắc pattern đầy đủ; khi dùng ký hiệu đặc biệt, hãy chọn pattern rõ ràng, kiểm tra bằng ví dụ và dùng locale được chỉ định.

### Lỗi sai phổ biến: `yyyy-mm-dd`

Với `LocalDateTime`, `yyyy-mm-dd` sẽ trộn trường năm, **phút** và ngày trong tháng. Chẳng hạn định dạng `2025-02-03` theo pattern này có thể xuất ra `2025-07-03` nếu formatter được áp dụng lên ngày giờ có phút 7, bởi `mm` chính là phút. Việc in ra một chuỗi có vẻ là ngày không chứng minh trường tháng đúng.

Mẫu đúng là:

```java
DateTimeFormatter safeDate =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
DateTimeFormatter safeDateTime =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm:ss", Locale.ROOT);
```

Đoạn mã cần `import java.time.format.DateTimeFormatter;` và `import java.util.Locale;`. Dùng `MM` cho tháng, `mm` cho phút là quy tắc phải kiểm tra mỗi khi có chữ M/m trong pattern.

## 7. Dùng locale có chủ đích

Locale ảnh hưởng các tên chữ như tháng viết tắt/đầy đủ, tên ngày trong tuần và cách biểu diễn một số trường dạng chữ. Nếu formatter dùng tên tháng:

```java
LocalDate date = LocalDate.of(2025, 2, 3);
DateTimeFormatter us = DateTimeFormatter.ofPattern(
        "d MMMM uuuu", Locale.US);
DateTimeFormatter french = DateTimeFormatter.ofPattern(
        "d MMMM uuuu", Locale.FRANCE);

System.out.println(date.format(us));
System.out.println(date.format(french));
```

Đây là đoạn minh họa Java cần `import java.time.*;`, `import java.time.format.DateTimeFormatter;` và `import java.util.Locale;`. Tên chữ phụ thuộc locale đã chọn. Đối với giá trị chỉ gồm số, locale thường không đổi quy tắc `MM` là tháng và `mm` là phút, nhưng locale vẫn có vai trò khi dùng ký hiệu chữ và khi định nghĩa quy tắc tuần như `YYYY`.

Locale không tự sửa một pattern sai: `yyyy-mm-dd` vẫn là năm-phút-ngày, dù locale là Việt Nam hay Hoa Kỳ. Hãy kiểm tra riêng ý nghĩa ký hiệu và locale hiển thị.

## 8. Parse chuỗi cũng dùng cùng phân biệt hoa/thường

`DateTimeFormatter` dùng được cho cả **format** (đối tượng thành chuỗi) và **parse** (chuỗi thành đối tượng). Chữ hoa/thường quyết định trường cần đọc khi parse, không chỉ cách trình bày.

Ví dụ đọc ngày thứ 34 trong năm 2025:

```java
DateTimeFormatter ordinalDate = DateTimeFormatter.ofPattern(
        "uuuu-DDD", Locale.ROOT);
LocalDate parsed = LocalDate.parse("2025-034", ordinalDate);
// parsed = 2025-02-03
```

Ở đây `DDD` đúng vì đầu vào là ngày-thứ-trong-năm. Nếu chuỗi đầu vào là năm-tháng-ngày, dùng `uuuu-MM-dd` thay thế. Không đổi pattern tùy tiện trong quá trình parse; đầu vào `2025-034` và `2025-02-03` có cấu trúc khác nhau.

Các chuỗi ngày nhập từ người dùng nên được kiểm tra lỗi parse và chuyển thành thông báo phù hợp. Đừng cố sửa dữ liệu bằng cách thay toàn bộ chữ M thành m hoặc ngược lại, vì nó có thể đổi ngữ nghĩa của những pattern khác.

## 9. An toàn khi chọn formatter cố định cho API

- **Định dạng giao diện:** chọn pattern theo quy ước của sản phẩm, ví dụ `dd/MM/uuuu HH:mm`, và có thể dùng locale được chỉ định để hiển thị tên tháng.
- **Định dạng trao đổi máy:** ưu tiên ISO formatter khi nó phù hợp với kiểu dữ liệu; đừng tạo format phụ thuộc locale mặc định rồi mong hệ thống khác đoán đúng.
- **Mốc tuyệt đối:** khi dữ liệu là `Instant` hoặc một kiểu có offset/zone, cần giữ thông tin đó nếu hợp đồng API yêu cầu timestamp toàn cầu. Pattern chỉ có `uuuu-MM-dd HH:mm:ss` làm mất offset và có thể làm đầu ra mơ hồ.
- **Ngày lịch:** `LocalDate` phù hợp với ngày không có giờ; pattern `uuuu-MM-dd` không biến ngày thành một thời điểm UTC.
- **Giờ đồng hồ:** `LocalTime` dùng pattern như `HH:mm:ss`; nó không thêm ngày hoặc múi giờ.
- **Kiểm thử pattern:** dùng một ngày và giờ có giá trị dễ phân biệt, ví dụ tháng 2, ngày 3, phút 7. Đừng chỉ test khi tháng và phút trùng số nhau, vì lỗi `MM/mm` có thể bị che khuất.

`DateTimeFormatter` là bất biến và an toàn cho nhiều luồng. Nên tạo formatter một lần rồi tái sử dụng nếu ứng dụng thường xuyên format/parse với cùng pattern và locale.

## 10. Các lỗi thường gặp

1. **Viết `mm` thay cho `MM` khi muốn tháng.** Kết quả dùng phút, không dùng tháng.
2. **Viết `DD` thay cho `dd` khi muốn ngày trong tháng.** Kết quả trở thành ngày thứ bao nhiêu trong năm.
3. **Dùng `yyyy-mm-dd` cho ngày.** Pattern trộn năm, phút, ngày; dùng `uuuu-MM-dd` hoặc ISO formatter phù hợp.
4. **Dùng `YYYY` thay `yyyy`/`uuuu`.** `YYYY` là năm theo tuần; các ngày sát đầu/cuối năm có thể cho năm khác.
5. **Kiểm thử chỉ trên các số tình cờ giống nhau.** Tháng 7 và phút 7 có thể khiến lỗi bị che giấu; hãy dùng tháng 2, phút 7.
6. **Không ghi rõ locale khi cần tên tháng/ngày.** Kết quả chữ có thể thay đổi theo môi trường.
7. **Giả định locale sẽ sửa pattern.** Locale không thay nghĩa các ký hiệu M/m và d/D.
8. **Parse ngày-thứ-trong-năm bằng pattern tháng/ngày.** Định dạng phải phù hợp cấu trúc thực của đầu vào.
9. **Định dạng một mốc có zone thành chuỗi không có offset rồi xem như timestamp đầy đủ.** Ngày giờ hiển thị vẫn có thể mơ hồ khi gửi qua hệ thống.
10. **Tự thay chữ trong pattern bằng thao tác văn bản hàng loạt.** Có thể phá những ký hiệu hợp lệ khác, ví dụ chữ `S`/`s` hay `H`/`h` cũng phân biệt ý nghĩa.
11. **Không kiểm tra trường dữ liệu được định dạng.** Hãy biết đầu vào là `LocalDate`, `LocalTime`, `LocalDateTime` hay kiểu có zone; không phải mọi kiểu đều chứa tất cả trường.
12. **Nhầm số thứ tự ngày với ngày tháng.** `DDD` hữu ích cho dữ liệu ngày-trong-năm nhưng không tương đương `dd`.

## 11. Bài tập tự kiểm tra

**Câu 1.** Với ngày `2025-02-03` và pattern `MM/dd/uuuu`, kết quả là gì?

**Đáp án:** `02/03/2025`. `MM` là tháng 2, `dd` là ngày 3.

**Câu 2.** Với giờ `16:07:09`, pattern `HH:mm:ss` hiển thị ra sao?

**Đáp án:** `16:07:09`. `mm` là phút 07.

**Câu 3.** Với ngày `2025-02-03`, tại sao `DD` cho 34?

**Đáp án:** Vì 03/02/2025 là ngày thứ 34 của năm 2025; `DD` là ngày-trong-năm, không phải ngày trong tháng.

**Câu 4.** Pattern `yyyy-mm-dd` có ý nghĩa gì sai?

**Đáp án:** Trường giữa là phút, vì `mm` viết thường. Đối với ngày lịch, dùng `uuuu-MM-dd` hoặc formatter ISO.

**Câu 5.** `YYYY` và `uuuu` có thể dùng thay thế nhau cho mọi ngày không?

**Đáp án:** Không. `YYYY` là week-based year, còn `uuuu` là năm theo trục số năm của lịch; ngày sát ranh giới năm có thể khác nhau.

**Câu 6.** Năm nhuận có thể có ngày thứ bao nhiêu lớn nhất là bao nhiêu?

**Đáp án:** `366`. Ngày 31/12 của năm nhuận có `DDD` bằng 366.

## Ghi nhớ

Trong pattern của `DateTimeFormatter`, **chữ hoa và chữ thường quyết định các trường khác nhau**: `MM` là tháng, `mm` là phút; `dd` là ngày trong tháng, `DD` là ngày trong năm. Đối với ngày lịch thông thường, ưu tiên `uuuu-MM-dd`; với giờ, dùng `HH:mm:ss`. Cũng cần phân biệt `YYYY` (năm theo tuần) với `yyyy`/`uuuu` (năm lịch theo quy tắc tương ứng). Chọn pattern theo kiểu dữ liệu, ghi rõ locale khi cần chữ, và kiểm chứng bằng ví dụ có tháng, ngày, phút khác nhau để tránh lỗi định dạng âm thầm.
