# Vì sao `uuuu` phù hợp hơn `yyyy` trong nhiều mẫu phân tích nghiêm ngặt?

## Một chuỗi hợp lệ vẫn có thể không tạo được `LocalDate`

Giả sử tệp nhập liệu ghi ngày theo dạng `2024-02-29`. Bạn tạo mẫu `yyyy-MM-dd`, bật `ResolverStyle.STRICT` để từ chối ngày sai, rồi thấy ngay cả ngày hợp lệ này cũng không phân tích được thành `LocalDate`.

Vấn đề không nằm ở dấu gạch ngang hay năm nhuận. Trong `java.time.format.DateTimeFormatter`, `yyyy` biểu diễn **năm trong kỷ nguyên**; còn `uuuu` biểu diễn **năm trên trục liên tục của hệ lịch**. Với mẫu chỉ gồm năm, tháng, ngày và không có kỷ nguyên, `uuuu-MM-dd` thường cung cấp đúng bộ trường mà việc tạo ngày ISO cần.

Bài này nói về `DateTimeFormatter` trong `java.time`, đầu vào ngày theo hệ lịch ISO và kết quả `LocalDate`. Không áp dụng máy móc cách đổi ký tự này cho `SimpleDateFormat` hoặc mọi hệ lịch khác.

## 1. Phân biệt ba khái niệm: năm, năm trong kỷ nguyên và kỷ nguyên

Trong cú pháp mẫu của `DateTimeFormatter`:

| Ký tự mẫu | Trường/khái niệm | Câu hỏi được trả lời |
| --- | --- | --- |
| `u`, thường viết `uuuu` | `YEAR`, năm theo trục liên tục (proleptic year) | Năm nào trên trục năm của hệ lịch? |
| `y`, thường viết `yyyy` | `YEAR_OF_ERA`, năm trong kỷ nguyên (year-of-era) | Năm thứ bao nhiêu trong kỷ nguyên? |
| `G` | `ERA`, kỷ nguyên (era) | Thuộc kỷ nguyên nào? |

Số lần lặp ký tự quyết định cách trình bày/đọc số, không làm `yyyy` chuyển thành trường `YEAR`. [Bảng ký tự mẫu `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Với hệ lịch ISO, hai kỷ nguyên là Công nguyên (CE/AD) và Trước Công nguyên (BCE/BC). Mối quan hệ có thể nhìn qua bảng:

| Ngày theo kỷ nguyên | `YEAR_OF_ERA` | `YEAR` trong `LocalDate` |
| --- | ---: | ---: |
| Năm 2024 Công nguyên | 2024 | 2024 |
| Năm 1 Công nguyên | 1 | 1 |
| Năm 1 Trước Công nguyên | 1 | 0 |
| Năm 2 Trước Công nguyên | 2 | -1 |

Trục năm ISO của `LocalDate` có năm `0`. Trong cách đánh số năm theo kỷ nguyên, năm đầu tiên của mỗi kỷ nguyên là `1`. Vì vậy, “năm thứ 1” nếu chưa biết kỷ nguyên vẫn chưa xác định cùng một năm trên trục liên tục. [Tài liệu trường ISO](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html), [tài liệu `ChronoField`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html)

Trong phần lớn dữ liệu đời sống hiện tại, giá trị `YEAR` và `YEAR_OF_ERA` trùng nhau về mặt con số. Chính sự trùng nhau ấy khiến người viết mẫu dễ tưởng hai ký tự tương đương.

## 2. Cơ chế: đọc đủ chữ số chưa chắc đã đủ thông tin tạo ngày

Phân tích ngày giờ có hai giai đoạn quan trọng:

1. Đọc văn bản theo mẫu thành các trường và giá trị.
2. Phân giải (resolve) các trường thành ngày giờ hoàn chỉnh.

`ResolverStyle` điều khiển giai đoạn phân giải. Với mẫu `yyyy-MM-dd`, chuỗi `2024-02-29` tạo ra các thông tin:

```text
YEAR_OF_ERA = 2024
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
ERA = chưa có
```

Khi chỉ có `YEAR_OF_ERA`, chế độ `STRICT` của hệ lịch ISO không tự giả định kỷ nguyên. Trong tình huống này, các trường chưa đủ để tạo `LocalDate`. Với `SMART` hoặc `LENIENT`, kỷ nguyên Công nguyên được giả định nếu thiếu. [Quy tắc phân giải của `IsoChronology`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle))

Ngược lại, mẫu `uuuu-MM-dd` cung cấp:

```text
YEAR = 2024
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
```

Bộ ba này xác định trực tiếp một ngày ISO; chế độ nghiêm ngặt có thể kiểm tra ngày 29 có hợp lệ trong tháng 02 của năm 2024 hay không.

Điểm cần hiểu là **một lỗi do thiếu thông tin để phân giải** khác với **một lỗi do ngày không tồn tại**. Cả hai có thể xuất hiện dưới dạng `DateTimeParseException` khi gọi `LocalDate.parse`, nhưng cách sửa không giống nhau.

## 3. Chương trình hoàn chỉnh chứng minh từng trường hợp

Lưu dưới tên `StrictYearDemo.java`. Chương trình dùng thư viện chuẩn và biên dịch với Java 17 trở lên:

```java
import java.time.LocalDate;
import java.time.chrono.IsoEra;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class StrictYearDemo {
    private static void show(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeParseException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter strictU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter strictY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter smartY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT);

        DateTimeFormatter smartU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

        show("strictUValid", "2024-02-29", strictU);
        show("strictUInvalid", "2023-02-29", strictU);
        show("strictYWithoutEra", "2024-02-29", strictY);
        show("smartYValid", "2024-02-29", smartY);
        show("smartUInvalid", "2023-02-29", smartU);

        TemporalAccessor fields = strictY.parse("2024-02-29");
        System.out.println("hasYear="
                + fields.isSupported(ChronoField.YEAR));
        System.out.println("hasYearOfEra="
                + fields.isSupported(ChronoField.YEAR_OF_ERA));

        DateTimeFormatter strictWithEra =
                DateTimeFormatter.ofPattern("yyyy-MM-dd G", Locale.ENGLISH)
                        .withResolverStyle(ResolverStyle.STRICT);

        show("strictYWithAD", "2024-02-29 AD", strictWithEra);
        show("strictYWithBC", "0001-01-01 BC", strictWithEra);
        show("strictUYearZero", "0000-01-01", strictU);
        show("strictUNegativeYear", "-0001-01-01", strictU);
        show("strictYZeroWithAD", "0000-01-01 AD", strictWithEra);

        DateTimeFormatter strictDefaultCE =
                new DateTimeFormatterBuilder()
                        .appendPattern("yyyy-MM-dd")
                        .parseDefaulting(ChronoField.ERA, IsoEra.CE.getValue())
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        show("strictYDefaultCE", "2024-02-29", strictDefaultCE);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 StrictYearDemo.java
java StrictYearDemo
```

Stdout:

```text
strictUValid=2024-02-29
strictUInvalid=REJECTED
strictYWithoutEra=REJECTED
smartYValid=2024-02-29
smartUInvalid=2023-02-28
hasYear=false
hasYearOfEra=true
strictYWithAD=2024-02-29
strictYWithBC=0000-01-01
strictUYearZero=0000-01-01
strictUNegativeYear=-0001-01-01
strictYZeroWithAD=REJECTED
strictYDefaultCE=2024-02-29
```

Các nhãn `REJECTED` do chương trình tự in để kết quả ổn định; chương trình không phụ thuộc toàn văn thông báo ngoại lệ của một phiên bản JDK.

## 4. Đọc kết quả: `uuuu` và `STRICT` giải quyết hai việc riêng

Nhóm đầu cho thấy:

- `strictUValid`: có trường năm trực tiếp và ngày tồn tại, nên thành công.
- `strictUInvalid`: trường năm đã đủ, nhưng năm 2023 không có ngày 29/02, nên bị từ chối.
- `strictYWithoutEra`: ngày theo cách hiểu Công nguyên là hợp lệ, nhưng cấu hình nghiêm ngặt không tự bổ sung kỷ nguyên còn thiếu.
- `smartYValid`: cấu hình mặc định của `ofPattern` là `SMART`, nên ví dụ có thể thành công nhờ giả định kỷ nguyên.
- `smartUInvalid`: chỉ đổi sang `uuuu` mà không bật `STRICT` vẫn có thể nhận ngày 29/02/2023 và điều chỉnh thành 28/02/2023.

Do đó, nếu mục tiêu là nhập ngày ISO không có kỷ nguyên và từ chối ngày không tồn tại, cần cả hai lựa chọn:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Đây là đoạn trích cấu hình, dùng các import như chương trình hoàn chỉnh.

`uuuu` chọn đúng **ý nghĩa trường năm**; `STRICT` chọn **quy tắc phân giải nghiêm ngặt**. Không lựa chọn nào tự thay thế lựa chọn kia. Hành vi điều chỉnh ngày trong chế độ `SMART` và kiểm tra ngày trong `STRICT` được mô tả ở [tài liệu `ResolverStyle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).

## 5. Vì sao `formatter.parse(text)` có thể chưa ném lỗi?

Trong chương trình, dòng:

```java
TemporalAccessor fields = strictY.parse("2024-02-29");
```

không yêu cầu kết quả phải là một `LocalDate`. Nó có thể trả về đối tượng giữ những trường đã đọc nhưng chưa phân giải thành ngày. Kết quả kiểm tra:

```text
hasYear=false
hasYearOfEra=true
```

cho thấy chữ số `2024` đã được đọc, nhưng nó đang nằm trong `YEAR_OF_ERA`, không phải `YEAR`.

Khi gọi:

```java
LocalDate.parse("2024-02-29", strictY);
```

bạn yêu cầu thêm bước tạo ngày cụ thể, và yêu cầu đó thất bại trong cấu hình thiếu kỷ nguyên này.

Vì vậy, một phép kiểm tra chỉ gọi `formatter.parse(text)` rồi kết luận “chuỗi chắc chắn là ngày hợp lệ” có thể kiểm tra chưa đúng đầu ra mà ứng dụng cần. Nếu cần ngày, hãy kiểm chứng việc tạo `LocalDate`, rồi kiểm tra giá trị nhận được.

## 6. `yyyy` vẫn phù hợp khi dữ liệu thực sự nói về kỷ nguyên

Có hai hướng hợp lệ nếu hợp đồng dữ liệu có ý nghĩa năm-trong-kỷ-nguyên.

### Đầu vào cung cấp kỷ nguyên

Mẫu `yyyy-MM-dd G` đi cùng `Locale.ENGLISH` trong chương trình đọc được:

```text
2024-02-29 AD
0001-01-01 BC
```

Kết quả thứ hai là `0000-01-01` khi chuyển sang cách biểu diễn năm liên tục của `LocalDate`. Nó không có nghĩa chương trình tự trừ sai một năm: hai cách đánh số đang mô tả cùng năm.

Ký hiệu kỷ nguyên dạng văn bản phụ thuộc ngôn ngữ của bộ định dạng. Chọn `Locale` đúng với dữ liệu, không giả định `AD`/`BC` phù hợp với mọi ngôn ngữ.

### Hợp đồng chủ động mặc định một kỷ nguyên

Nếu một giao diện cố ý dùng năm-trong-kỷ-nguyên và quy định mọi năm thiếu kỷ nguyên đều là Công nguyên, có thể cấu hình rõ:

```java
DateTimeFormatter formatter =
        new DateTimeFormatterBuilder()
                .appendPattern("yyyy-MM-dd")
                .parseDefaulting(ChronoField.ERA, IsoEra.CE.getValue())
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Đây là đoạn trích từ chương trình hoàn chỉnh. Lựa chọn này bổ sung thông tin mặc định có chủ đích; nó không làm `yyyy` có nghĩa giống `uuuu`.

Với một giao diện đơn giản nhận ngày ISO `năm-tháng-ngày`, không mang khái niệm kỷ nguyên riêng, dùng năm trực tiếp thường dễ hiểu hơn việc bổ sung một giá trị mặc định chỉ để mẫu `yyyy` chạy được.

## 7. Phân tích hợp lệ chưa thay thế quy tắc nghiệp vụ

Trong chương trình, `strictUYearZero` và `strictUNegativeYear` đều thành công. Đây là khả năng của mô hình lịch, không tự động là dữ liệu phù hợp với mọi ứng dụng.

Ví dụ hệ thống chỉ cho lịch học từ năm 2000 đến 2099 cần kiểm tra riêng sau khi phân tích:

```java
static LocalDate parseCourseDate(String text) {
    LocalDate date = LocalDate.parse(
            text,
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT));

    if (date.getYear() < 2000 || date.getYear() > 2099) {
        throw new IllegalArgumentException("Nam hoc ngoai pham vi 2000..2099");
    }
    return date;
}
```

Đây là hàm minh họa, cần đặt trong một lớp và dùng các import như chương trình đầy đủ. Ở mã dùng nhiều lần, có thể khai báo bộ định dạng thành hằng dùng chung.

Hai lớp kiểm tra cần được phân biệt:

- **Hợp lệ theo lịch:** trường đọc được và tạo thành ngày tồn tại.
- **Hợp lệ theo nghiệp vụ:** ngày nằm trong khoảng và điều kiện mà hệ thống cho phép.

Cũng không nên hiểu bốn chữ `u` là một quy tắc nghiệp vụ bắt buộc năm thuộc `0000..9999`. Quy tắc về độ rộng và dấu của năm thuộc cú pháp mẫu; khoảng năm được phép của sản phẩm phải được quy định và kiểm chứng riêng nếu có yêu cầu.

## 8. Những cách sửa dễ che mất nguyên nhân

| Cách sửa | Vấn đề | Cách xử lý có ý nghĩa |
| --- | --- | --- |
| Bỏ `STRICT` để ngày hợp lệ không còn lỗi | Có thể làm ngày sai bị điều chỉnh trong `SMART` | Chọn đúng trường năm, giữ quy tắc phân giải cần thiết |
| Đổi mọi `yyyy` thành `uuuu` trong mọi API | Các API có thể định nghĩa ký tự khác nhau | Xác nhận thư viện và hợp đồng trước |
| Chuyển sang `YYYY` vì nghĩ chữ hoa “chuẩn hơn” | `Y` là năm theo tuần, không phải năm lịch thông thường | Dùng `u` hoặc `y` theo đúng ý nghĩa |
| Chỉ thử một ngày giữa năm | Không phát hiện ngày nhuận, năm 0 hoặc thiếu kỷ nguyên | Có ca hợp lệ, không hợp lệ và ranh giới phù hợp |
| Chỉ thử định dạng ngày ra chuỗi | Ngày hiện đại có thể in giống nhau với `uuuu` và `yyyy` | Kiểm tra đúng chiều phân tích thành kiểu đích |

Riêng `SimpleDateFormat` của API cũ dùng `u` cho số thứ trong tuần. Không sao chép nguyên mẫu `uuuu-MM-dd` của `DateTimeFormatter` sang API đó. [Bảng mẫu `SimpleDateFormat`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html)

Nếu đầu vào vốn là ngày ISO mặc định, `LocalDate.parse(text)` đã là lựa chọn trực tiếp; không bắt buộc tự tạo lại một mẫu chỉ để thể hiện `uuuu`. Mẫu tùy chỉnh cần có lý do từ định dạng dữ liệu.

## 9. Tự kiểm tra

1. Vì sao `yyyy-MM-dd` với `STRICT` có thể từ chối `2024-02-29` dù ngày đó tồn tại?
2. Chỉ đổi `yyyy` thành `uuuu` mà vẫn giữ `SMART` có bảo đảm từ chối `2023-02-29` không?
3. Khi đầu vào là `0001-01-01 BC`, nên dùng trường năm trực tiếp hay năm-trong-kỷ-nguyên đi với kỷ nguyên?
4. `formatter.parse(text)` không ném lỗi đã chứng minh tạo được `LocalDate` chưa?

Gợi ý đáp án:

1. Vì có `YEAR_OF_ERA` nhưng thiếu `ERA`; chế độ nghiêm ngặt không tự giả định kỷ nguyên.
2. Không; chương trình cho thấy `SMART` có thể điều chỉnh thành `2023-02-28`.
3. Dữ liệu này biểu đạt năm-trong-kỷ-nguyên, nên `yyyy` đi với `G` là lựa chọn có ý nghĩa.
4. Chưa; cần kiểm tra kết quả ở đúng kiểu mà ứng dụng sử dụng.

Khi viết bộ phân tích ngày không có kỷ nguyên, hãy chọn trường năm mà dữ liệu thực sự mang, giữ chế độ phân giải phù hợp và kiểm tra cả việc tạo ngày lẫn điều kiện nghiệp vụ.
