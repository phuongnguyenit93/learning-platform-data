# Locale, FormatStyle và định dạng tiếng Việt

## 1. Cùng một ngày, nhiều cách trình bày

Một giá trị `LocalDate` như ngày 25 tháng 10 năm 2026 không mang sẵn ngôn ngữ hiển thị. Nó lưu năm, tháng, ngày; còn chuỗi người dùng nhìn thấy được tạo ra bởi `DateTimeFormatter`.

Chẳng hạn, người dùng ở Việt Nam thường đọc ngày theo thứ tự ngày/tháng/năm, còn giao diện tiếng Anh Mỹ có thể viết tên tháng trước ngày. Không cần tạo hai giá trị ngày khác nhau: giữ nguyên ngày và chọn cách trình bày phù hợp với người đọc.

Ba khái niệm phối hợp với nhau:

| Thành phần | Trả lời câu hỏi nào? | Ví dụ |
|---|---|---|
| Giá trị ngày giờ | Đang biểu diễn ngày/giờ nào? | `LocalDate.of(2026, 10, 25)` |
| `Locale` | Theo ngôn ngữ và quy ước vùng nào? | `Locale.forLanguageTag("vi-VN")` |
| `FormatStyle` | Cần mức độ chi tiết nào? | `FULL`, `LONG`, `MEDIUM`, `SHORT` |

`DateTimeFormatter` kết hợp các lựa chọn để tạo chuỗi. `Locale` có thể ảnh hưởng tên thứ, tên tháng, thứ tự ngày/tháng/năm và dấu phân cách khi dùng kiểu định dạng theo vùng. Việc đổi cách hiển thị không làm thay đổi ngày gốc.

## 2. Chọn Locale một cách rõ ràng

Với tiếng Việt tại Việt Nam, dùng thẻ ngôn ngữ BCP 47 `vi-VN`:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Locale us = Locale.US;
```

`vi` là ngôn ngữ tiếng Việt, `VN` là vùng Việt Nam. `vi-VN` dùng dấu gạch ngang theo cú pháp thẻ ngôn ngữ; đừng nhầm với chuỗi hiển thị nội bộ như `vi_VN`. Trong ví dụ cần tương thích Java 17 trở lên, `Locale.forLanguageTag` là lựa chọn rõ ràng.

### Không phụ thuộc ngầm vào máy chạy

Nếu không chỉ định, nhiều phương thức tạo bộ định dạng dùng `Locale` mặc định của nhóm `Locale.Category.FORMAT`. Máy lập trình, máy kiểm thử và máy chủ có thể có cấu hình khác nhau. Vì vậy một đoạn mã chạy đúng vẫn có thể sinh các chuỗi khác nhau giữa môi trường.

Với giao diện đã biết ngôn ngữ, hãy truyền `Locale` tường minh:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("vi-VN"));
```

Không cần gọi `Locale.setDefault` để phục vụ riêng một màn hình hay một yêu cầu. Thay đổi mặc định là thay đổi trạng thái dùng chung của tiến trình và có thể ảnh hưởng những chức năng khác đang chạy đồng thời.

`DateTimeFormatter` là bất biến. `withLocale` trả về một bộ định dạng mới; cần dùng hoặc lưu giá trị trả về. Có thể tái sử dụng các bộ định dạng cấu hình sẵn cho những yêu cầu cùng ngôn ngữ mà không khóa đồng bộ.

## 3. Hiểu đúng bốn mức FormatStyle

| Mức | Ý định trình bày | Tình huống có thể phù hợp |
|---|---|---|
| `FULL` | Nhiều chi tiết nhất; ngày có thể kèm tên thứ | Tiêu đề lịch, thông báo trang trọng |
| `LONG` | Tên tháng và ngày đầy đủ, nhiều chi tiết | Mô tả sự kiện trong đoạn văn |
| `MEDIUM` | Độ dài vừa phải, có thể viết tắt tên tháng | Danh sách nội dung |
| `SHORT` | Gọn, thường thiên về chữ số | Bảng nhiều dòng hoặc vùng hẹp |

Đây là **mức độ chi tiết**, không phải bốn mẫu cố định cho mọi quốc gia. `SHORT` không có nghĩa luôn là `dd/MM/uuuu`, cũng không đảm bảo năm có bốn chữ số. Hình thức cụ thể do dữ liệu vùng của Java quyết định; khi đổi `Locale`, cùng một mức có thể có thứ tự và cách viết khác.

Ví dụ minh họa trong một phương thức Java:

```java
LocalDate date = LocalDate.of(2026, 10, 25);
DateTimeFormatter viLong = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("vi-VN"));
String label = date.format(viLong);
```

Muốn viết một dòng có cả ngày và giờ, dùng `ofLocalizedDateTime`. Có thể dùng cùng mức cho cả hai phần hoặc chọn riêng:

```java
DateTimeFormatter appointment = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)
        .withLocale(Locale.forLanguageTag("vi-VN"));
```

Đoạn trên là khai báo bộ định dạng, cần áp dụng vào giá trị có đủ ngày và giờ, chẳng hạn `LocalDateTime`. `LocalDate` chỉ có ngày; `LocalTime` chỉ có giờ. Dùng một bộ định dạng đòi hỏi trường không có trong giá trị sẽ gây lỗi thay vì tự bổ sung dữ liệu.

Đặc biệt, kiểu giờ `FULL` hoặc `LONG` thường yêu cầu thông tin múi giờ. Khi cần chúng, dùng giá trị có múi giờ như `ZonedDateTime`, hoặc cấu hình múi giờ phù hợp cho bộ định dạng. Không mặc định rằng `LocalTime` hay `LocalDateTime` luôn đủ dữ liệu cho mọi mức giờ.

## 4. Định dạng theo vùng hay mẫu do sản phẩm quy định?

Hai cách này phục vụ hai nhu cầu khác nhau.

**Tự chọn theo quy ước vùng:** `ofLocalizedDate(FormatStyle.LONG).withLocale(vi)` cho phép Java chọn mẫu ngày dài phù hợp. Đây là lựa chọn tốt khi sản phẩm muốn thích nghi với ngôn ngữ/vùng của người dùng.

**Mẫu cố định:** nếu yêu cầu thiết kế là luôn có ngày và tháng hai chữ số, năm bốn chữ số, có thể dùng:

```java
DateTimeFormatter numeric = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));
```

Khi đó ngày 25 tháng 10 năm 2026 sẽ được viết `25/10/2026`. `Locale` không tự đảo mẫu vừa chỉ định thành thứ tự khác. Với mẫu chỉ có chữ số như trên, ảnh hưởng về ngôn ngữ không rõ bằng mẫu chứa tên tháng hoặc tên thứ.

Ví dụ mẫu `EEEE, dd MMMM uuuu` có trường tên thứ và tên tháng; lúc này `Locale` tham gia chọn các tên tương ứng. Những chữ cố định viết trong dấu nháy đơn của mẫu là nguyên văn, không được bộ định dạng tự dịch.

Phân biệt một số ký hiệu dễ nhầm:

- `M` là tháng, `m` là phút.
- `d` là ngày trong tháng; `D` là ngày thứ bao nhiêu trong năm.
- `u` là năm theo lịch; `y` là năm trong kỷ nguyên, còn `Y` là năm theo tuần và có thể khác năm lịch gần đầu/cuối năm.

Với mẫu ngày lịch thông dụng trong ví dụ này, dùng `uuuu`. Không dùng `YYYY` vì trông giống bốn chữ số năm. Nếu muốn kiểm tra ngày nhập theo mẫu cố định thật chặt, cấu hình thêm `withResolverStyle(ResolverStyle.STRICT)`; `Locale` không tự quyết định mức nghiêm ngặt của phép phân tích.

## 5. Locale không phải múi giờ

`vi-VN` là lựa chọn ngôn ngữ/vùng; nó không tự gắn múi giờ Việt Nam vào giá trị. Múi giờ được biểu diễn bằng `ZoneId`, chẳng hạn `Asia/Ho_Chi_Minh`.

Một người dùng đọc giao diện tiếng Việt vẫn có thể muốn xem thời gian theo múi giờ Tokyo. Hai lựa chọn ngôn ngữ và múi giờ phải được cấu hình độc lập.

Ví dụ minh họa việc trình bày một thời điểm đã có sẵn:

```java
DateTimeFormatter display = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("vi-VN"))
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
String label = display.format(Instant.parse("2026-10-25T02:05:00Z"));
```

Ở đây `Instant` cung cấp thời điểm, `ZoneId` xác định cách chuyển sang giờ địa phương, còn `Locale` chọn cách viết. Đoạn này cần các import tương ứng từ `java.time`, `java.time.format` và `java.util`. Nó là minh họa riêng, không phải chương trình độc lập.

Không suy ra múi giờ từ `Locale`, và không gắn múi giờ máy chủ vào dữ liệu chỉ vì máy chủ đang ở Việt Nam. Cũng không dùng `Locale` để tự chuyển đổi hệ lịch; bộ định dạng vùng do `ofLocalizedDate` tạo trong phạm vi bài này sử dụng hệ lịch ISO.

## 6. Chương trình chạy đầy đủ

Lưu mã sau vào `VietnameseDateDemo.java`. Chương trình dùng Java 17 trở lên và không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class VietnameseDateDemo {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale en = Locale.US;
        LocalDate date = LocalDate.of(2026, 10, 25);

        System.out.println("locale=" + vi.toLanguageTag());
        for (FormatStyle style : FormatStyle.values()) {
            DateTimeFormatter formatter =
                    DateTimeFormatter.ofLocalizedDate(style).withLocale(vi);
            System.out.println(style + "=" + date.format(formatter));
        }

        DateTimeFormatter usLong = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG).withLocale(en);
        System.out.println("en-US=" + date.format(usLong));

        DateTimeFormatter numeric = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", vi);
        System.out.println("numeric=" + date.format(numeric));
        System.out.println("parsed=" + LocalDate.parse("25/10/2026", numeric));

        DateTimeFormatter fullVi = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.FULL).withLocale(vi);
        String localized = date.format(fullVi);
        System.out.println("roundTrip="
                + date.equals(LocalDate.parse(localized, fullVi)));

        DateTimeFormatter dateTime = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.SHORT).withLocale(vi);
        LocalDateTime meeting = date.atTime(9, 5);
        System.out.println("meeting=" + meeting.format(dateTime));

        ZonedDateTime zoned = meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("isoZoned=" + zoned);
    }
}
```

Biên dịch và chạy:

```shell
javac VietnameseDateDemo.java
java VietnameseDateDemo
```

Một lần chạy đã kiểm chứng trên Zulu OpenJDK 24.0.2, dùng dữ liệu vùng mặc định của bản JDK đó, cho kết quả:

```text
locale=vi-VN
FULL=Chủ Nhật, 25 tháng 10, 2026
LONG=25 tháng 10, 2026
MEDIUM=25 thg 10, 2026
SHORT=25/10/26
en-US=October 25, 2026
numeric=25/10/2026
parsed=2026-10-25
roundTrip=true
meeting=09:05 25/10/26
isoZoned=2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]
```

Các dòng ngày theo vùng và dòng `meeting` có thể khác về dấu câu, khoảng trắng, cách viết hoa hay mẫu giữa các phiên bản JDK và bộ cung cấp dữ liệu vùng. Ví dụ này ghi rõ môi trường để không biến một kết quả quan sát thành cam kết rằng mọi Java 17+ sẽ in giống từng ký tự. Hãy chạy trên JDK đang dùng khi cần đối chiếu chính xác.

Cách đọc kết quả:

1. Bốn dòng `FULL` đến `SHORT` giữ cùng ngày, chỉ thay mức chi tiết.
2. Dòng `en-US` đổi ngôn ngữ/vùng sang tiếng Anh Mỹ.
3. `numeric` tuân theo mẫu cố định có năm bốn chữ số, trong khi mẫu `SHORT` ở lần chạy này có năm hai chữ số.
4. `parsed` cho thấy chuỗi `25/10/2026` đã được đọc bằng chính bộ định dạng số; `LocalDate.toString()` sau đó in dạng ISO.
5. `roundTrip=true` kiểm tra một chuỗi vừa định dạng có thể được đọc lại trong cùng môi trường và cùng bộ định dạng.
6. `meeting` dùng dữ liệu có đủ ngày và giờ; `isoZoned` cho thấy múi giờ được gắn tường minh, độc lập với lựa chọn `vi-VN`.

## 7. Đọc chuỗi tiếng Việt và chọn ranh giới lưu trữ

Khi chuỗi chứa tên tháng hoặc tên thứ tiếng Việt, bộ định dạng dùng để đọc phải có `Locale` phù hợp. Chỉ thay `Locale` lúc hiển thị mà quên cấu hình ở bước đọc có thể gây `DateTimeParseException`. Ngoài ngôn ngữ, chuỗi còn phải khớp mẫu, chữ hoa/thường và dấu câu mà bộ định dạng chấp nhận.

Vòng chuyển đổi trong chương trình kiểm tra một chuỗi được chính Java tạo ra. Nó không chứng minh rằng mọi cách viết tự do của người dùng đều đọc được. Ví dụ, một giao diện muốn nhận thêm các biến thể viết tắt hoặc không phân biệt chữ hoa/thường phải thiết kế quy tắc nhận dữ liệu riêng, có thể cần `DateTimeFormatterBuilder`; không nên suy ra rằng `withLocale(vi)` tự hỗ trợ tất cả.

Nên tách hai ranh giới:

| Ranh giới | Lựa chọn hợp lý |
|---|---|
| Hiển thị cho người đọc | Bộ định dạng theo `Locale` và mức chi tiết phù hợp |
| API, cấu hình hoặc dữ liệu cần trao đổi ổn định | Kiểu ngày/giờ có ngữ nghĩa rõ ràng và hợp đồng chuỗi xác định, thường là ISO |

Đừng lấy chuỗi như `25 thg 10, 2026` làm khóa sắp xếp, định danh hay hợp đồng API chỉ vì nó đẹp trên giao diện. Sắp xếp và tính toán trên giá trị ngày giờ; chỉ định dạng ở biên hiển thị. Chuỗi ngày theo vùng có thể thay đổi khi nâng JDK dù dữ liệu nghiệp vụ vẫn là cùng một ngày.

## 8. Kiểm tra và lỗi thường gặp

- **Đã tạo Locale tiếng Việt nhưng vẫn in tiếng Anh:** kiểm tra đối tượng `DateTimeFormatter` thực sự được dùng; gọi `withLocale(vi)` rồi bỏ giá trị trả về không đổi bộ định dạng ban đầu.
- **Đặt `SHORT` nhưng năm chỉ có hai chữ số:** đây có thể là mẫu hợp lệ của vùng. Dùng mẫu cố định nếu yêu cầu bắt buộc bốn chữ số.
- **Đổi Locale mà giờ không đổi theo Việt Nam:** kiểm tra `ZoneId`; thay ngôn ngữ không chuyển múi giờ.
- **Định dạng giờ dài bị lỗi:** kiểm tra giá trị có thông tin múi giờ cần thiết hay không.
- **Kiểm thử chuỗi hỏng sau nâng JDK:** phân biệt lỗi dữ liệu với thay đổi dữ liệu vùng. Với kiểm thử đòi hỏi chuỗi chính xác, cố định JDK/bộ cung cấp dữ liệu vùng hoặc chọn mẫu đầu ra do sản phẩm quy định rõ.
- **Tiếng Việt mất dấu:** kiểm tra mã hóa tệp nguồn, đầu ra tiến trình và nơi hiển thị. Chọn đúng `Locale` không sửa được chuỗi đã bị giải mã sai; khi cần chỉ định mã hóa nguồn, dùng `javac -encoding UTF-8 VietnameseDateDemo.java`.

Để tự thực hành, đổi ngày thành `LocalDate.of(2026, 1, 5)`, chạy lại cả bốn mức cho `vi-VN`, rồi thay bằng `Locale.UK` và `Locale.US`. Hãy chỉ ra phần nào do giá trị ngày quyết định, phần nào do vùng quyết định, và vì sao `dd/MM/uuuu` vẫn giữ thứ tự đã viết khi thay `Locale`.

Tài liệu tham khảo: [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), [FormatStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/FormatStyle.html) và [Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html) trong Java SE 21.
