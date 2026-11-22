# ResolverStyle.STRICT, SMART, LENIENT và phân tích ngày hợp lệ trong Java

## 1. Một chuỗi ngày đúng mẫu chưa chắc là ngày hợp lệ

Một ứng dụng nhập ngày sinh, ngày hẹn, hạn thanh toán hoặc ngày hiệu lực thường nhận chuỗi như `2024-02-29`. Việc chuỗi có đúng thứ tự và số lượng chữ số **không đủ** để kết luận ngày có tồn tại trong lịch.

Ví dụ:

| Chuỗi | Đúng hình dạng `uuuu-MM-dd`? | Ngày lịch ISO có tồn tại? |
| --- | --- | --- |
| `2024-02-29` | Có | Có: năm 2024 nhuận |
| `2023-02-29` | Có | Không: năm 2023 không nhuận |
| `2023-02-30` | Có | Không: tháng 2 không có ngày 30 |
| `2023-13-40` | Có (vẫn có 2 chữ số cho tháng/ngày) | Không: tháng/ngày vượt giới hạn |
| `2023-2-9` | Không, nếu mẫu yêu cầu chính xác `MM` và `dd` | Có thể diễn đạt ngày thực, nhưng **sai mẫu** |
| `abc` | Không | Không |

Java có `java.time.format.ResolverStyle` để quy định cách **giải quyết các trường ngày/giờ đã parse** thành đối tượng thời gian có nghĩa. Ba lựa chọn:

- `ResolverStyle.STRICT`: xác thực chặt chẽ theo lịch; từ chối ngày không tồn tại.
- `ResolverStyle.SMART`: điều chỉnh một số trường hợp thiếu chính xác theo quy tắc “hợp lý” của từng trường và từng lịch.
- `ResolverStyle.LENIENT`: chấp nhận nhiều giá trị vượt phạm vi khi resolve và chuẩn hóa bằng cộng/trừ thời gian.

**Điều quan trọng nhất:** cả ba đều là **chính sách phân giải ngày**, không phải ba kiểu biểu thức chính quy, không phải ba định dạng văn bản và không phải ba mức “an toàn” áp dụng chung cho mọi nghiệp vụ. Nếu người dùng nhập ngày sinh thực tế, `STRICT` thường hợp lý; nếu dữ liệu mô tả phép cộng ngày tương đối, `LENIENT` có thể hữu ích nhưng phải là lựa chọn có chủ đích.

## 2. Java parse theo hai giai đoạn

Với `DateTimeFormatter`, việc phân tích văn bản thực hiện theo hai pha:

1. **Parse văn bản theo cấu trúc formatter:** đọc chữ số, dấu phân cách, tên tháng, tùy chọn, vùng thời gian… thành các cặp `TemporalField → value` và thông tin liên quan. Ở pha này `"2023-02-29"` có thể được phân tích thành `YEAR=2023`, `MONTH_OF_YEAR=2`, `DAY_OF_MONTH=29`, dù tổ hợp đó không phải một ngày ISO hợp lệ.
2. **Resolve các trường thành ngày/giờ:** kiểm tra hoặc chuẩn hóa các trường theo `ResolverStyle` và `Chronology` đang áp dụng. Pha này quyết định ngày 29/02/2023 bị từ chối, được chỉnh thành 28/02 hoặc trở thành 01/03.

~~~text
Input "2023-02-29"
       |
       v
Pha 1: parse theo "uuuu-MM-dd"
       |
       +--> YEAR = 2023
       +--> MONTH_OF_YEAR = 2
       +--> DAY_OF_MONTH = 29
       |
       v
Pha 2: resolve theo ResolverStyle
       |
       +--> STRICT  : từ chối (2023 không nhuận)
       +--> SMART   : 2023-02-28
       +--> LENIENT : 2023-03-01
~~~

Vì `ResolverStyle` chỉ điều khiển **pha resolve**, thay sang `LENIENT` **không tự làm mọi chuỗi sai định dạng được chấp nhận**. Ví dụ pattern `uuuu-MM-dd` vẫn có thể từ chối `2023-2-9` do thiếu độ rộng cần thiết, và `abc` không chứa các trường số phù hợp.

Hai khái niệm cần tách bạch:

- `DateTimeFormatterBuilder.parseStrict()` / `parseLenient()` điều khiển **độ chặt ở pha đọc văn bản** trong builder.
- `DateTimeFormatter.withResolverStyle(...)` điều khiển **pha phân giải trường**. Đặt resolver `LENIENT` không tương đương tự động gọi `parseLenient()` cho builder.

Java còn cung cấp `parseUnresolved(...)` để xem phần dữ liệu sau pha 1 mà chưa resolve; đây là API cấp thấp hữu ích khi debug, **không** phải kết quả hợp lệ cuối cùng để nhập thẳng vào domain.

## 3. STRICT: từ chối ngày lịch không tồn tại

Với lịch ISO, `ResolverStyle.STRICT` yêu cầu giá trị trường nằm trong phạm vi hợp lệ và tổ hợp **năm–tháng–ngày phải có thật**.

~~~java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate valid = LocalDate.parse("2024-02-29", strict);
~~~

Đây là **đoạn minh họa bên trong một phương thức**; cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle` và `java.util.Locale`. Chương trình độc lập ở mục 7.

Kết quả:

- `2024-02-29` → ngày hợp lệ.
- `2023-02-29` → `DateTimeParseException`.
- `2023-02-30` → `DateTimeParseException`.
- `2023-13-40` → `DateTimeParseException`.
- `2023-00-10` → `DateTimeParseException`.

**Khi nào nên dùng?** Ngày sinh, ngày phát hành, hạn hợp đồng, ngày hóa đơn, input lịch làm việc, ngày kế toán hoặc bất kỳ trường hợp nào mà điều kiện quan trọng là **ngày đã nhập phải tồn tại**, không được âm thầm đổi ngày.

Tuy vậy, `STRICT` mới xác thực theo **lịch**; nó không xác thực mọi quy tắc nghiệp vụ. Một ngày `2099-12-31` có thể là ngày ISO hợp lệ nhưng nằm ngoài kỳ đăng ký, kỳ nghỉ, năm được hỗ trợ hoặc giới hạn tuổi cho phép. Sau parse vẫn phải kiểm tra **miền giá trị và quy tắc domain**.

## 4. SMART: hợp lý hóa một số ngày trong tháng, không tự sửa mọi trường

`ResolverStyle.SMART` là chính sách thông minh do **từng trường và chronology** quyết định. Trong trường hợp tổ hợp năm/tháng/ngày theo lịch ISO, Java kiểm tra ngày-of-month thuộc phạm vi tổng quát **1 đến 31**, nhưng nếu ngày đó lớn hơn ngày cuối cùng của **tháng cụ thể**, nó có thể chọn ngày cuối tháng.

Với pattern `uuuu-MM-dd`:

| Đầu vào | `SMART` | Giải thích |
| --- | --- | --- |
| `2024-02-29` | `2024-02-29` | Có thật, giữ nguyên |
| `2023-02-29` | `2023-02-28` | Điều chỉnh về cuối tháng 2 |
| `2023-02-30` | `2023-02-28` | Ngày 30 nằm trong 1–31 nhưng không tồn tại ở tháng 2 |
| `2023-02-32` | Từ chối | Ngày vượt phạm vi tổng quát 1–31 |
| `2023-13-40` | Từ chối | Tháng 13 và ngày 40 không hợp lệ |
| `2023-00-10` | Từ chối | Tháng 0 không hợp lệ |

**Không nên dùng `SMART` làm bộ kiểm tra tính đúng nguyên bản input** khi bản thân việc người dùng nhập `2023-02-29` là lỗi cần họ sửa. Trong ví dụ trên, `LocalDate.parse` không báo lỗi: ứng dụng sẽ thấy `2023-02-28`, mặc dù đầu vào khác ngày được lưu.

`SMART` có thể phù hợp nếu nghiệp vụ **có hợp đồng rõ ràng** rằng ngày vượt cuối tháng được dồn về ngày cuối tháng. Ví dụ một số quy tắc lập lịch tháng có thể mong muốn điều đó, nhưng thường nên diễn đạt chính sách bằng phép toán ngày như `YearMonth.atEndOfMonth()` hoặc `TemporalAdjusters.lastDayOfMonth()` thay vì dựa vào hệ quả ngầm của parse.

**Không khẳng định SMART luôn “làm tròn ngày”**: cách xử lý phụ thuộc trường, chronology và loại dữ liệu. Ví dụ một số tình huống giờ `24:00` được xử lý khác các giá trị ngày-of-month, nhưng cần kiểm tra hợp đồng cụ thể thay vì áp quy tắc tháng 2 cho mọi trường thời gian.

## 5. LENIENT: chuẩn hóa số tháng/ngày vượt phạm vi

`ResolverStyle.LENIENT` cho phép nhiều trường vượt phạm vi thông thường và giải quyết bằng phép cộng/trừ trong lịch.

Với lịch ISO và `uuuu-MM-dd`, có thể hình dung:

1. Bắt đầu từ ngày đầu tiên của năm/tháng được xác định sau chuẩn hóa.
2. Dịch chuyển theo giá trị tháng và ngày được đọc, kể cả vượt phạm vi.
3. Trả về một `LocalDate` có thực sau khi dịch chuyển.

Ví dụ đã kiểm thử:

| Đầu vào | `LENIENT` | Phân tích |
| --- | --- | --- |
| `2024-02-29` | `2024-02-29` | Ngày hợp lệ, không đổi |
| `2023-02-29` | `2023-03-01` | Ngày kế tiếp 28/02/2023 |
| `2023-02-30` | `2023-03-02` | Hai ngày sau 28/02/2023 |
| `2023-13-40` | `2024-02-09` | Tháng 13/2023 → 01/2024, ngày 40 → 09/02/2024 |
| `2023-00-10` | `2022-12-10` | Tháng 0 → tháng 12 năm trước |
| `2023-02-32` | `2023-03-04` | Ngày 32/02 vượt sang tháng 3 |
| `abc` | Từ chối | Không vượt qua pha parse văn bản |

`LENIENT` không có nghĩa “bỏ qua lỗi rồi dùng ngày hiện tại”. Nó **chuẩn hóa một số trường thành ngày khác** có thể cách xa ngày người dùng nghĩ mình đã nhập. Điều này đặc biệt nguy hiểm với hạn nộp, deadline, ngày sinh hoặc chứng từ: `2023-13-40` có thể thành `2024-02-09` mà người dùng không hề nhận ra input có vấn đề.

**Khi dùng?** Các công cụ biến đổi dữ liệu có quy tắc rollover đã công bố, kiểm thử lịch tự động, hoặc phép tính tương đối mà input là các trường có thể vượt phạm vi. Trong hầu hết API nhận **ngày tuyệt đối** do người dùng gõ, chọn `STRICT` và báo lỗi cụ thể sẽ ít gây ngạc nhiên hơn.

Nếu mục tiêu là cộng 40 ngày, nên dùng API tính ngày rõ nghĩa:

~~~java
LocalDate result = LocalDate.of(2024, 1, 1).plusDays(39);
~~~

Đây là đoạn minh họa, không phải file chạy độc lập. Cách này minh bạch hơn việc tạo chuỗi tháng 13/ngày 40 rồi phụ thuộc vào `LENIENT`.

## 6. Default resolver style và bẫy yyyy so với uuuu

### 6.1. Mặc định không phải formatter nào cũng STRICT

Java SE 17 có các factory/formatter với mặc định khác nhau:

| Formatter | Resolver style mặc định |
| --- | --- |
| `DateTimeFormatter.ofPattern("uuuu-MM-dd")` | **SMART** |
| `DateTimeFormatter.ofPattern("uuuu-MM-dd", locale)` | **SMART** |
| `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)` | **SMART** |
| `DateTimeFormatter.ISO_LOCAL_DATE` | **STRICT** |

Vì vậy:

~~~java
LocalDate parsed = LocalDate.parse(
        "2023-02-29",
        DateTimeFormatter.ofPattern("uuuu-MM-dd"));
~~~

Đây là đoạn minh họa. **Kết quả có thể là `2023-02-28`**, chứ không ném lỗi như nhiều người mong đợi. Đặt rõ resolver style nếu mục tiêu là xác thực ngày người dùng đã nhập.

~~~java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

`withResolverStyle` trả về **formatter mới** vì `DateTimeFormatter` bất biến; nếu gọi mà bỏ qua đối tượng trả về, cấu hình không thay đổi.

### 6.2. `yyyy` không đồng nghĩa `uuuu` trong STRICT

Đây là một lỗi phổ biến khác khi chuyển formatter từ `SMART` sang `STRICT`:

- `u` / `uuuu`: **proleptic year** (`ChronoField.YEAR`), có thể diễn đạt năm 0 và năm âm theo lịch ISO proleptic.
- `y` / `yyyy`: **year-of-era** (`ChronoField.YEAR_OF_ERA`), cần ngữ cảnh **era** (`G`) để xác định năm trên trục năm.
- `G`: tên/giá trị **era** (ví dụ AD/BC ở lịch ISO theo locale).

Đối chiếu với `ResolverStyle.STRICT`:

~~~java
DateTimeFormatter wrongForStrict = DateTimeFormatter
        .ofPattern("yyyy-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter correctForIso = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

Cả hai đoạn là minh họa. Với input `2024-02-29`:

- Formatter `uuuu-MM-dd` giải được `YEAR=2024`, `MONTH=2`, `DAY=29` → `LocalDate` hợp lệ.
- Formatter `yyyy-MM-dd` chỉ có `YEAR_OF_ERA=2024` mà **không có era**, nên trong `STRICT` không đủ dữ liệu để lấy `LocalDate`. Kết quả là `DateTimeParseException` ngay cả khi ngày lịch này thực sự hợp lệ.
- Nếu muốn dùng year-of-era, hãy cung cấp era như pattern `G yyyy-MM-dd` (ví dụ `AD 2024-02-29` ở locale tiếng Anh) hoặc cấu hình parse default cho era một cách có chủ đích.

**Với ngày ISO dạng số dùng làm dữ liệu đầu vào**, thường ưu tiên `uuuu-MM-dd` cùng `STRICT`, hoặc dùng sẵn `DateTimeFormatter.ISO_LOCAL_DATE`. Đừng đổi ngẫu nhiên `yyyy` thành `uuuu` ở mọi formatter hiển thị vì `yyyy` có ý nghĩa hợp lệ khi sử dụng năm theo niên hiệu.

### 6.3. Chronology có thể thay đổi kết quả resolve

Ví dụ trên dùng **lịch ISO** (`LocalDate`). Với các `Chronology` khác (Japanese, Hijrah, Thai Buddhist...), các trường lịch, leap year, era và giới hạn có thể khác. `ResolverStyle` là chính sách resolve, nhưng chính chronology thực hiện việc kết hợp các trường vào ngày.

Không nên kết luận `SMART` luôn chuyển `29/02` về ngày 28 cho **mọi chronology**; đó là kết quả ví dụ của **ISO**. Nếu yêu cầu một lịch cụ thể, hãy áp dụng chronology tường minh và kiểm thử các dữ liệu biên phù hợp.

## 7. Chương trình Java 17 hoàn chỉnh và kết quả kiểm chứng

Đặt nội dung sau trong tệp **`ResolverStyleDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    static DateTimeFormatter formatter(ResolverStyle style) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(style);
    }

    static String parse(ResolverStyle style, String input) {
        try {
            return LocalDate.parse(input, formatter(style)).toString();
        } catch (DateTimeParseException e) {
            return "REJECTED";
        }
    }

    static void show(String input) {
        System.out.println(input
                + " | STRICT=" + parse(ResolverStyle.STRICT, input)
                + " | SMART=" + parse(ResolverStyle.SMART, input)
                + " | LENIENT=" + parse(ResolverStyle.LENIENT, input));
    }

    public static void main(String[] args) {
        show("2024-02-29");
        show("2023-02-29");
        show("2023-02-30");
        show("2023-13-40");
        show("2023-00-10");
        show("abc");

        DateTimeFormatter yyyy = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter uuuu = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            System.out.println("STRICT yyyy="
                    + LocalDate.parse("2024-02-29", yyyy));
        } catch (DateTimeParseException e) {
            System.out.println("STRICT yyyy=REJECTED");
        }
        System.out.println("STRICT uuuu="
                + LocalDate.parse("2024-02-29", uuuu));

        System.out.println("ofPattern default="
                + DateTimeFormatter
                        .ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .getResolverStyle());
        System.out.println("ISO_LOCAL_DATE default="
                + DateTimeFormatter.ISO_LOCAL_DATE
                        .getResolverStyle());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 ResolverStyleDemo.java
java ResolverStyleDemo
~~~

**Stdout được kiểm tra** với ví dụ Java:

~~~text
2024-02-29 | STRICT=2024-02-29 | SMART=2024-02-29 | LENIENT=2024-02-29
2023-02-29 | STRICT=REJECTED | SMART=2023-02-28 | LENIENT=2023-03-01
2023-02-30 | STRICT=REJECTED | SMART=2023-02-28 | LENIENT=2023-03-02
2023-13-40 | STRICT=REJECTED | SMART=REJECTED | LENIENT=2024-02-09
2023-00-10 | STRICT=REJECTED | SMART=REJECTED | LENIENT=2022-12-10
abc | STRICT=REJECTED | SMART=REJECTED | LENIENT=REJECTED
STRICT yyyy=REJECTED
STRICT uuuu=2024-02-29
ofPattern default=SMART
ISO_LOCAL_DATE default=STRICT
~~~

Cách đọc output:

1. `2024-02-29` là ngày nhuận hợp lệ, ba mode cùng tạo ra một ngày.
2. `2023-02-29` bị `STRICT` từ chối; `SMART` dùng cuối tháng 2, `LENIENT` chuyển sang 1/3.
3. `2023-02-30` tiếp tục cho thấy `SMART` **dồn về 28/2**, nhưng `LENIENT` chuyển sang 2/3.
4. `2023-13-40` hoặc `2023-00-10` minh họa `LENIENT` chuẩn hóa cả tháng và ngày vượt phạm vi.
5. `abc` không cung cấp dữ liệu theo pattern nên ba mode đều từ chối ở pha parse văn bản.
6. `STRICT yyyy` bị từ chối do thiếu **era**, chứ không phải vì 29/2/2024 sai; `STRICT uuuu` thành công.
7. `ofPattern` mặc định `SMART`, còn `ISO_LOCAL_DATE` là `STRICT`.

Chương trình in `REJECTED` thay cho thông điệp ngoại lệ thật để kết quả ổn định giữa các phiên bản Java. Trong ứng dụng, bạn nên xử lý `DateTimeParseException` theo chính sách thông báo lỗi rõ ràng, không để stack trace nội bộ xuất hiện trực tiếp trước người dùng.

## 8. Xây hàm xác thực ngày nhập đáng tin cậy

### 8.1. Parse chặt theo mẫu ISO khi nguồn dữ liệu cần ngày thật

Với API nhận input `yyyy-MM-dd` theo cách đặt tên thông thường, mẫu Java thích hợp cho năm ISO **proleptic** là `uuuu-MM-dd`:

~~~java
public static LocalDate requireIsoDate(String raw) {
    DateTimeFormatter format = DateTimeFormatter
            .ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);
    return LocalDate.parse(raw, format);
}
~~~

Đây là **một phương thức minh họa**, không phải chương trình độc lập. Nó cần được đặt trong class có các import `LocalDate`, `DateTimeFormatter`, `ResolverStyle`, `Locale`. Người gọi cần bắt `DateTimeParseException` khi dữ liệu không hợp lệ và xử lý input `null` theo hợp đồng riêng.

Nếu giao thức **chỉ** cho phép định dạng ISO chuẩn, thường có thể dùng ngắn gọn:

~~~java
LocalDate date = LocalDate.parse(raw, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Đây là đoạn minh họa, `raw` là chuỗi đầu vào. `ISO_LOCAL_DATE` có resolver `STRICT` và chronology ISO được khai báo. Tuy nhiên, **`STRICT` không tự đồng nghĩa với "input chỉ gồm năm 4 chữ số không có dấu" trong mọi cách tạo formatter**; độ rộng, dấu cộng/trừ và chính sách lexical thuộc pattern/builder. Nếu API yêu cầu chính xác các byte hoặc ký tự trong một dạng khác, hãy kiểm tra theo hợp đồng giao thức và dùng pattern/builder tương ứng.

### 8.2. Tách xác thực lịch và xác thực nghiệp vụ

Sau khi có `LocalDate` hợp lệ, còn phải kiểm tra:

- Ngày có nằm trong **khoảng thời gian hệ thống hỗ trợ** hay không?
- Ngày có vượt deadline, cutoff, thời gian đặt trước hoặc ngày đóng sổ không?
- Ngày có phải ngày làm việc và có nằm trong lịch nghỉ/holiday được sản phẩm hỗ trợ không?
- Người dùng có quyền chọn ngày này không?
- Nếu là ngày giờ, có múi giờ, DST gap/overlap hoặc offset nào cần xử lý không?

Ví dụ:

~~~java
if (date.isBefore(LocalDate.of(2000, 1, 1))
        || date.isAfter(LocalDate.of(2100, 12, 31))) {
    throw new IllegalArgumentException("Date outside supported range");
}
~~~

Đây là đoạn minh họa, `date` đã parse thành công. **ResolverStyle không thay thế business validator**. Ngày `2024-02-29` hợp lệ theo lịch vẫn có thể bị từ chối nếu không thuộc miền ngày hợp đồng cho phép.

### 8.3. Parse và format là hai thao tác khác nhau

`DateTimeFormatter.withResolverStyle(...)` chỉ ảnh hưởng **parsing**, không thay đổi giá trị ngày khi formatter **format** một `LocalDate` đã hợp lệ. Trong khi đó, `withLocale` có thể đổi tên tháng, tên thứ hoặc pattern bản địa; `withChronology` và `withZone` mang ý nghĩa khác.

Không sử dụng `format(date)` rồi đọc chuỗi lại bằng `SMART` để “sửa” một dữ liệu nghiệp vụ đã sai. Dữ liệu thời gian cần được xác thực tại ranh giới nhập, lưu bằng kiểu `java.time` thích hợp và chỉ format ở tầng hiển thị.

## 9. Các trường hợp biên và lỗi hay gặp

| Hiểu lầm/lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng `ofPattern` mặc định `STRICT` | `2023-02-29` có thể thành `2023-02-28` | Gọi `withResolverStyle(STRICT)` |
| Dùng `yyyy` với `STRICT` nhưng không có era | Ngày đúng cũng không resolve được sang `LocalDate` | Dùng `uuuu` cho năm ISO hoặc cung cấp `G` |
| Dùng `LENIENT` cho ngày sinh/hạn hợp đồng | Input sai có thể bị chuyển sang ngày khác | Dùng `STRICT` và báo lỗi |
| Nghĩ `SMART` tự sửa mọi ngày/tháng | Tháng 13, ngày 32 vẫn có thể bị từ chối | Hiểu đúng quy tắc SMART của chronology |
| Nghĩ `LENIENT` chấp nhận mọi văn bản | Sai lexical pattern vẫn bị từ chối | Phân biệt parse phase và resolve phase |
| Đặt `formatter.withResolverStyle(STRICT)` nhưng bỏ kết quả | Formatter gốc vẫn `SMART` | Gán lại hoặc dùng formatter mới |
| Không phân biệt `parseStrict` với `ResolverStyle.STRICT` | Cấu hình sai giai đoạn | Chọn đúng parse lexical hoặc resolve |
| Xử lý mọi `DateTimeParseException` bằng default `LocalDate.now()` | Lỗi dữ liệu bị che, nghiệp vụ sai | Báo input không hợp lệ, yêu cầu chỉnh sửa |
| Cho rằng STRICT đảm bảo ngày hợp nghiệp vụ | Vẫn có thể ngoài khoảng, lịch nghỉ hoặc cutoff | Validate domain sau parse |
| Dùng `SimpleDateFormat` như `DateTimeFormatter` | Hai API có khác biệt về mặc định và thread safety | Ưu tiên `java.time` trong code mới |
| Thay locale/zone để “sửa” ngày sai | Không giải quyết được ngày lịch không tồn tại | Kiểm tra chronology, pattern, resolver |
| Bắt ngoại lệ rồi trả nguyên thông báo nội bộ cho UI | Lộ chi tiết implementation, khó bản địa hóa thông báo | Trả mã lỗi và message phù hợp locale |

### 9.1. Trường hợp tháng/ngày một chữ số

Với pattern cố định `uuuu-MM-dd`, input `2023-2-9` bị từ chối kể cả với `LENIENT` trong ví dụ JDK đã kiểm tra. Muốn hỗ trợ cách gõ một hoặc hai chữ số, hãy dùng formatter có pattern/builder phù hợp với input đó, rồi **vẫn** áp dụng `STRICT` khi nghiệp vụ cần ngày hợp lệ. Không biến `LENIENT` thành cách vá lỗi cú pháp.

### 9.2. Trường hợp trailing garbage

Input `2023-02-29extra` không thể được coi là một ngày hoàn chỉnh chỉ vì có tiền tố giống `uuuu-MM-dd`. Các overload `LocalDate.parse(text, formatter)` dùng để tạo đối tượng ngày và yêu cầu giải thích thích hợp toàn văn bản; hãy để lỗi parse được báo rõ.

Nếu dùng API thấp hơn với `ParsePosition`, phải kiểm tra phần text đã được tiêu thụ. Đừng nhận một chuỗi mà parser chỉ đọc được vài ký tự đầu rồi âm thầm bỏ phần còn lại.

### 9.3. Múi giờ, DST và thời điểm

`ResolverStyle.STRICT` kiểm tra trường lịch trong context của formatter, nhưng **không tự xác nhận** một `LocalDateTime` địa phương có thể ánh xạ một-một đến `Instant` tại `ZoneId` cho trước. Trong ngày chuyển giờ mùa hè (DST), có thể có giờ địa phương **không tồn tại** hoặc **trùng lặp**.

Nếu nghiệp vụ cần xác thực giờ họp, giờ thanh toán, giờ bay hoặc sự kiện theo một vùng, phải xác định `ZoneId` và xử lý gap/overlap bằng quy tắc cụ thể. `ResolverStyle` không thay thế việc xét `ZoneRules`.

### 9.4. Với SimpleDateFormat thì sao?

`java.text.SimpleDateFormat` có cơ chế `setLenient(boolean)` trên nền `Calendar`, không phải ba mode của `java.time.ResolverStyle`. Trong dự án mới, ưu tiên `java.time` để có formatter immutable, thread-safe và semantics parsing tường minh. Nếu tích hợp legacy, phải kiểm thử lại việc parse/normalize thay vì giả định `SimpleDateFormat.setLenient(false)` chính xác bằng mọi hành vi của `ResolverStyle.STRICT`.

## 10. Kiểm thử cần thiết

Một bộ test phù hợp cho input ngày thực tế nên có:

1. **Năm nhuận:** `2024-02-29` hợp lệ; `2023-02-29` phải bị `STRICT` từ chối.
2. **Ngày cuối tháng:** `2023-04-30` hợp lệ; `2023-04-31` phải bị `STRICT` từ chối.
3. **Tháng vượt biên:** `2023-13-10`, `2023-00-10` không được âm thầm chuẩn hóa trong API nhận ngày tuyệt đối.
4. **Ngày vượt biên:** `2023-02-30`, `2023-02-32`, giá trị âm nếu pattern cho phép; kiểm tra phân biệt SMART/LENIENT.
5. **Độ rộng/cú pháp:** `2023-2-9`, `2023/02/09`, khoảng trắng ở đầu/cuối và ký tự lạ.
6. **Năm và niên hiệu:** `uuuu` so với `yyyy` trong STRICT; nếu dùng era, cần kiểm tra `G`.
7. **Default formatter:** xác nhận `ofPattern` `SMART`, `ISO_LOCAL_DATE` `STRICT`.
8. **Locale:** tên tháng theo ngôn ngữ được yêu cầu, nhưng hiệu lực lịch/chronology phải được khai báo rõ ràng.
9. **Giới hạn nghiệp vụ:** ngày trước/sau miền cho phép, ngày lễ, ngày nghỉ, cutoff, quyền truy cập.
10. **DST và timezone:** khi dữ liệu là local date-time, test gap/overlap với `ZoneId` liên quan.
11. **Không sửa input:** ứng dụng phải lưu **ngày đã được người dùng xác nhận**, không tự làm lệch deadline vì SMART/LENIENT.
12. **Ngoại lệ:** `DateTimeParseException` được chuyển thành thông báo có thể hiểu; không lộ stack trace.

Với test tự động, hãy so **LocalDate** chính xác sau parse, không chỉ so việc hàm có ném exception hay không. Đặc biệt SMART có thể “thành công” bằng cách thay giá trị, nên test phải kiểm tra ngày cuối cùng.

## 11. Bài tập thực hành

- Thử ba mode với `2023-04-31`, giải thích vì sao `SMART` về 30/4 còn `LENIENT` sang 1/5.
- Thử `2024-02-30`: kiểm tra kết quả theo năm nhuận.
- Thay pattern `uuuu-MM-dd` bằng `yyyy-MM-dd` và giữ `STRICT`; suy luận vì sao lỗi xảy ra cả với `2024-02-29`.
- Thêm era qua `G yyyy-MM-dd` và thử `AD 2024-02-29` ở `Locale.US`; kiểm tra ngày trả về.
- Tạo formatter dùng `DateTimeFormatterBuilder` với cách parse linh hoạt về số chữ số, nhưng giữ `ResolverStyle.STRICT`; xác minh input một chữ số tháng vẫn được hiểu mà ngày sai vẫn bị bác bỏ.
- So `DateTimeFormatter.ISO_LOCAL_DATE` với `ofPattern("uuuu-MM-dd").withResolverStyle(STRICT)` trên ngày biên và pattern ký hiệu năm.
- Viết validator `requireDueDate(String input)` parse STRICT rồi so ngày với `LocalDate.now(clock)` được inject để test ổn định.
- Với lịch hẹn, thử một `LocalDateTime` ở ngày chuyển DST của một `ZoneId` cụ thể; phân biệt lỗi ngày lịch với việc thời điểm không tồn tại theo zone.

## 12. Tổng kết

`ResolverStyle` kiểm soát **pha resolve** của `DateTimeFormatter`, không tự thay đổi mọi quy tắc đọc ký tự. Với ngày ISO:

- **STRICT** chỉ nhận tổ hợp lịch thực sự hợp lệ.
- **SMART** có thể điều chỉnh ngày vượt cuối tháng về ngày cuối tháng, nhưng không chấp nhận mọi giá trị vô lý.
- **LENIENT** có thể chuẩn hóa tháng/ngày vượt phạm vi bằng rollover, vì vậy dễ tạo ra **ngày khác input**.

Đối với biểu mẫu cần một ngày thực đúng như người dùng nhập, hãy chọn `DateTimeFormatter.ISO_LOCAL_DATE` hoặc mẫu `uuuu-MM-dd` có `ResolverStyle.STRICT`, xử lý lỗi rõ ràng và tiếp tục kiểm tra ràng buộc nghiệp vụ. Đặc biệt nhớ **`yyyy` là year-of-era, `uuuu` là proleptic year**: khi dùng STRICT, khác biệt đó có thể quyết định một ngày hợp lệ có parse được hay không.

**Tài liệu tham khảo:**

- Java SE 17, `ResolverStyle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `DateTimeFormatterBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html
- Java SE 17, `LocalDate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
- Java SE 17, `DateTimeParseException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeParseException.html
