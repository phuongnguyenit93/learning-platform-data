# DecimalFormat: phần trăm, phần nghìn và hệ số nhân

## 1. Mục tiêu và bài toán

Khi ứng dụng Java hiển thị một tỷ lệ, **giá trị dữ liệu** và **chuỗi người dùng nhìn thấy** thường có thang đo khác nhau:

- Tỷ lệ gốc `0.256` tương ứng `25.6%` (phần trăm).
- Cũng tỷ lệ gốc đó tương ứng `256‰` (phần nghìn, *per mille*).
- Nếu dữ liệu gốc đã là `25.6` và biểu thị “25,6 phần trăm” theo hợp đồng API, không được lại nhân 100 khi định dạng: kết quả sẽ sai thành `2560%`.

`java.text.DecimalFormat` cho phép định dạng số theo mẫu, xử lý dấu phân cách theo `Locale`, làm tròn theo số chữ số hiển thị và **nhân dữ liệu đầu vào bằng hệ số định dạng**. Khi phân tích chuỗi bằng `parse`, formatter thường **chia ngược theo hệ số nhân** để trả về giá trị số.

Bài này phân biệt ký hiệu `%` và `‰`, cách `DecimalFormat` tự thiết lập multiplier, cách dùng `setMultiplier`, tác động tới `format`/`parse`, giới hạn về độ chính xác, locale và các lỗi thường gặp.

**Điều quan trọng nhất:** `DecimalFormat` tạo biểu diễn phục vụ người đọc; nó **không nên thay đổi đơn vị hoặc ý nghĩa nghiệp vụ** của biến số trong model. Hãy thống nhất trước rằng dữ liệu gốc là **tỷ lệ thập phân** (ví dụ 0.256) hay **số phần trăm đã nhân 100** (ví dụ 25.6).

## 2. Từ tỷ lệ thập phân đến phần trăm và phần nghìn

Các đơn vị tỷ lệ cơ bản:

| Dữ liệu tỷ lệ gốc | Phần trăm (%) | Phần nghìn (‰) | Giải thích |
| ---: | ---: | ---: | --- |
| `0` | `0%` | `0‰` | Không có phần nào |
| `0.001` | `0.1%` | `1‰` | Một phần nghìn |
| `0.01` | `1%` | `10‰` | Một phần trăm |
| `0.125` | `12.5%` | `125‰` | Một phần tám |
| `0.256` | `25.6%` | `256‰` | Giá trị minh họa chính |
| `1` | `100%` | `1000‰` | Toàn bộ |
| `1.5` | `150%` | `1500‰` | Có thể hợp lệ khi tỷ lệ vượt 100% |

Công thức:

```text
percentage = ratio × 100
perMille   = ratio × 1000

ratio = percentage ÷ 100
ratio = perMille ÷ 1000
```

Một đơn vị phần trăm tương ứng **10 phần nghìn**: `1% = 10‰`. Trong thống kê, lãi suất hoặc biến động theo thời gian, **điểm phần trăm** là phép trừ giữa hai giá trị phần trăm, không phải phép nhân/định dạng. Chẳng hạn từ `20%` lên `25%` là tăng **5 điểm phần trăm**, còn tăng tương đối là `(25-20)/20 = 25%`. `DecimalFormat` không tự phân biệt hai khái niệm kinh doanh này.

Không nhầm **ký hiệu phần nghìn `‰` (U+2030)** với dấu phân cách hàng nghìn của số, ví dụ dấu phẩy trong `1,000` theo `Locale.US`.

## 3. Hai ký hiệu đặc biệt trong pattern

Khi `DecimalFormat` đọc một **pattern**, `%` và `‰` là ký hiệu mang ý nghĩa đặc biệt, không đơn thuần là ký tự trang trí:

| Mẫu | Hệ số ngầm định | Ý nghĩa trên tỷ lệ gốc `0.256` |
| --- | ---: | --- |
| `0.0%` | `100` | `25.6%` |
| `0%` | `100` | `26%` sau khi làm tròn |
| `0.0‰` | `1000` | `256.0‰` |
| `0.0` | `1` | `0.3` sau khi làm tròn |
| `0.0'%'` | `1` | `0.3%`, dấu % chỉ là literal |

Với ký hiệu `%` **không nằm trong vùng quote**, pattern khiến `DecimalFormat` dùng multiplier `100`; với `‰` không được quote, multiplier là `1000`. Dấu được in ra theo `DecimalFormatSymbols` của formatter. Trong Java, pattern có thể có prefix/suffix như `0.00 %`; tùy cách đặt và cú pháp quote, ký tự `%` vẫn mang hiệu ứng nhân 100, trong khi khoảng trắng là một phần literal của pattern.

**Cạm bẫy:** mẫu `0.0'%'` cố tình quote phần trăm thành ký tự bình thường, nên **không nhân 100**. Kết quả `0.3%` từ `0.256` là ký hiệu gây hiểu lầm nếu đọc như “0,3 phần trăm” trong nghiệp vụ. Chỉ dùng cách quote khi thật sự muốn in ký tự `%` mà không có ý nghĩa tỷ lệ.

Pattern `0`, `0.0`, `0.00` kiểm soát số chữ số tối thiểu/tối đa sau dấu thập phân trong các ví dụ này. `#` là chữ số tùy chọn, như `0.##%` (tối đa hai chữ số thập phân). Hãy tách bạch **mẫu độ chính xác hiển thị** với **hệ số nhân**; `0.0%` và `0%` cùng nhân 100 nhưng làm tròn khác nhau.

## 4. Ví dụ Java 17+ chạy độc lập: định dạng % và ‰

Tạo file `PercentPerMilleDemo.java`:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PercentPerMilleDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat percent =
                new DecimalFormat("0.0%", symbols);
        DecimalFormat perMille =
                new DecimalFormat("0.0‰", symbols);

        double ratio = 0.256;

        System.out.println("ratio: " + ratio);
        System.out.println("percent: " + percent.format(ratio));
        System.out.println("per mille: " + perMille.format(ratio));
        System.out.println("percent factor: " + percent.getMultiplier());
        System.out.println("per mille factor: " + perMille.getMultiplier());
    }
}
```

Biên dịch và chạy từ thư mục chứa file (lưu UTF-8):

```bash
javac -encoding UTF-8 PercentPerMilleDemo.java
java PercentPerMilleDemo
```

Stdout:

```text
ratio: 0.256
percent: 25.6%
per mille: 256.0‰
percent factor: 100
per mille factor: 1000
```

Giải thích:

1. `symbols` lấy từ `Locale.US` để ký tự phân cách và ký hiệu thống nhất với output minh họa.
2. Constructor `new DecimalFormat("0.0%", symbols)` tạo pattern định dạng có phần trăm và hệ số ngầm `100`.
3. Constructor `new DecimalFormat("0.0‰", symbols)` tạo pattern có phần nghìn và hệ số ngầm `1000`.
4. Cả hai nhận **cùng giá trị gốc 0.256**, nhưng hiển thị ở hai đơn vị khác nhau.
5. `getMultiplier()` là cách kiểm tra hệ số mà formatter hiện đang dùng; giá trị nằm ở object formatter, **không phải ở biến `ratio`**.

Nếu chuỗi `‰` có thể bị lỗi encoding trong trình biên dịch hoặc công cụ soạn thảo, bạn có thể dùng Unicode escape Java `"\u0030\u002e\u0030\u2030"` cho pattern `0.0‰`; nhưng trong dự án Java 17+ thông thường, lưu UTF-8 rõ ràng là cách đọc dễ hiểu hơn.

## 5. `setMultiplier`: nhân theo một hệ số không kèm ký hiệu đặc biệt

Có thể thiết lập hệ số nhân riêng bằng `setMultiplier(int)`, không cần dùng `%` hoặc `‰`. Ví dụ muốn in **số lượng trên 1.000 đơn vị** mà không có ký hiệu:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ManualMultiplierDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat formatter =
                new DecimalFormat("0.00", symbols);
        formatter.setMultiplier(1000);

        System.out.println("factor: " + formatter.getMultiplier());
        System.out.println("format: " + formatter.format(0.256));
        System.out.println("parse: " +
                formatter.parse("256.00").doubleValue());
    }
}
```

Để biên dịch, ví dụ cần xử lý checked exception `ParseException` của `parse`. Phiên bản hoàn chỉnh, có thể chạy, là:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class ManualMultiplierDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat formatter =
                new DecimalFormat("0.00", symbols);
        formatter.setMultiplier(1000);

        System.out.println("factor: " + formatter.getMultiplier());
        System.out.println("format: " + formatter.format(0.256));
        System.out.println("parse: " +
                formatter.parse("256.00").doubleValue());
    }
}
```

Lưu **chỉ phiên bản hoàn chỉnh thứ hai** vào `ManualMultiplierDemo.java`, rồi chạy:

```bash
javac -encoding UTF-8 ManualMultiplierDemo.java
java ManualMultiplierDemo
```

Stdout:

```text
factor: 1000
format: 256.00
parse: 0.256
```

Điểm khác với `‰`: formatter ở đây **không tự thêm ký hiệu phần nghìn**. `setMultiplier(1000)` thay đổi cách chuyển đổi giá trị, còn phần biểu diễn hậu tố phụ thuộc pattern. Nếu muốn ký hiệu `‰` ở đầu ra, nên dùng một pattern có `‰` phù hợp ngay từ đầu thay vì tự nối chuỗi sau khi format.

**Cần tránh:** gọi `setMultiplier(1000)` trên một formatter đang dùng pattern `0.0%`. Khi đó formatter có thể in dấu `%` nhưng nhân 1000; kết quả mang ý nghĩa “phần trăm” sai. Hệ số và ký hiệu phải nhất quán với hợp đồng dữ liệu.

## 6. Parse chuỗi có dấu % và ‰: vì sao giá trị bị chia ngược?

`DecimalFormat` không chỉ format số thành chuỗi; nó có thể parse chuỗi về số. Với formatter theo phần trăm, parser đọc phần số và ký hiệu rồi tính ra **tỷ lệ gốc** bằng cách chia 100. Tương tự, parser phần nghìn chia 1000.

Ví dụ độc lập:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class ParseScaleDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat percent = new DecimalFormat("0.0%", symbols);
        DecimalFormat perMille = new DecimalFormat("0.0‰", symbols);

        Number fromPercent = percent.parse("25.6%");
        Number fromPerMille = perMille.parse("256.0‰");

        System.out.println("from percent: " +
                fromPercent.doubleValue());
        System.out.println("from per mille: " +
                fromPerMille.doubleValue());
    }
}
```

Lưu `ParseScaleDemo.java` ở UTF-8, rồi chạy:

```bash
javac -encoding UTF-8 ParseScaleDemo.java
java ParseScaleDemo
```

Stdout:

```text
from percent: 0.256
from per mille: 0.256
```

Bảng đối chiếu:

| Formatter | Chuỗi để parse | Số thu về |
| --- | --- | ---: |
| `0.0%` | `"25.6%"` | `0.256` |
| `0.0‰` | `"256.0‰"` | `0.256` |
| `0.00` với multiplier `1000` | `"256.00"` | `0.256` |

**Lưu ý về parse:**

- `parse(String)` có thể ném `ParseException` khi không phân tích được; code phải xử lý ngoại lệ.
- Parser phụ thuộc `DecimalFormatSymbols` và cấu trúc pattern; chuỗi dùng dấu thập phân hoặc phần trăm của locale khác có thể bị hiểu sai/không đọc được.
- `DecimalFormat.parse` theo mặc định **không bắt buộc phải tiêu thụ toàn bộ input**. Nếu đang xác thực dữ liệu người dùng, có thể dùng overload `parse(String, ParsePosition)` và kiểm tra `position.getIndex() == input.length()`, cũng như kiểm tra `errorIndex`, trước khi chấp nhận. Tránh coi việc parse được một prefix là dữ liệu hợp lệ hoàn toàn.
- `format` có thể làm tròn; vì vậy `parse(format(x))` không nhất thiết bằng `x`. Ví dụ với `0%`, tỷ lệ `0.256` được hiển thị `26%`; parse lại `26%` trả khoảng `0.26`, không phải `0.256`.
- Nếu dùng tỷ lệ tiền tệ, lãi suất hoặc phép tính đòi hỏi độ chính xác decimal, hãy quản lý dữ liệu bằng `BigDecimal` và kiểm soát rounding. `DecimalFormat` chủ yếu giải quyết biểu diễn.

## 7. Phân biệt % được quote và % có tác dụng nhân

Mẫu `"0.0%"` và `"0.0'%'" ` trông gần giống nhau, nhưng hoàn toàn khác nghĩa.

Một chương trình rõ ràng:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LiteralPercentDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat scaled =
                new DecimalFormat("0.0%", symbols);
        DecimalFormat literal =
                new DecimalFormat("0.0'%'", symbols);

        System.out.println("scaled: " + scaled.format(0.256));
        System.out.println("scaled factor: " + scaled.getMultiplier());
        System.out.println("literal: " + literal.format(0.256));
        System.out.println("literal factor: " + literal.getMultiplier());
    }
}
```

Lưu `LiteralPercentDemo.java`, chạy:

```bash
javac -encoding UTF-8 LiteralPercentDemo.java
java LiteralPercentDemo
```

Stdout:

```text
scaled: 25.6%
scaled factor: 100
literal: 0.3%
literal factor: 1
```

Trường hợp quoted percent có thể dùng trong một vài nhãn kỹ thuật đặc biệt, nhưng **không** dùng để hiển thị tỷ lệ phần trăm từ dữ liệu ratio. Số `0.3%` trong kết quả trên thực chất chỉ là số `0.3` sau khi làm tròn cộng thêm dấu `%` theo nghĩa literal; nó không biểu diễn \(0.3\%\) của dữ liệu gốc theo cách hiểu thông thường.

Các ký hiệu ở ngoài dấu nháy đơn của pattern mang ý nghĩa định dạng; bên trong phần quote, chúng trở thành literal. Dấu nháy đơn được dùng trong cú pháp pattern, không phải ký tự Java tự in ra.

## 8. Pattern, độ chính xác và làm tròn

Ký hiệu `0` và `#` trong pattern quyết định cách hiển thị chữ số:

```text
0%       -> làm tròn đến đơn vị phần trăm
0.0%     -> một chữ số sau dấu thập phân
0.00%    -> hai chữ số sau dấu thập phân
0.##%    -> tối đa hai chữ số sau dấu thập phân
0.0‰     -> một chữ số sau dấu thập phân ở thang phần nghìn
```

Với cùng tỷ lệ `0.256`:

| Pattern | Kết quả theo Locale.US | Hệ số |
| --- | --- | ---: |
| `0%` | `26%` | 100 |
| `0.0%` | `25.6%` | 100 |
| `0.00%` | `25.60%` | 100 |
| `0.##%` | `25.6%` | 100 |
| `0.0‰` | `256.0‰` | 1000 |

`DecimalFormat` thường sử dụng `RoundingMode.HALF_EVEN` theo cấu hình mặc định đối với kiểu định dạng này; nhưng **đừng dựa vào mặc định** khi kết quả làm tròn mang ý nghĩa nghiệp vụ. Có thể cấu hình rõ:

```java
formatter.setRoundingMode(java.math.RoundingMode.HALF_UP);
```

Lệnh trên là một **đoạn mã minh họa** và yêu cầu có đối tượng `formatter` kiểu `DecimalFormat`. Chọn `HALF_UP`, `HALF_EVEN`, `DOWN` hoặc chế độ khác dựa trên quy tắc sản phẩm, không dựa vào “cách nhìn có vẻ đẹp”.

**Không làm tròn dữ liệu nguồn chỉ để format UI.** Khi có thể, giữ tỷ lệ gốc đủ chính xác trong tầng tính toán, còn `DecimalFormat` chỉ làm tròn **bản hiển thị**. Nếu lưu ngược giá trị đã format/parse, bạn có thể làm mất thông tin.

## 9. Locale điều khiển dấu số và ký hiệu phần trăm

Trong `DecimalFormat`, pattern dùng các dấu quy ước (`.`, `,`, `%`, `‰`) nhưng đầu ra được điều khiển thêm bởi `DecimalFormatSymbols` của locale. Vì thế cùng một tỷ lệ và cùng mục đích hiển thị có thể có cách phân cách chữ số, khoảng trắng và ký hiệu khác nhau giữa các locale.

Cách khởi tạo phổ biến:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat formatter = new DecimalFormat("0.0%", symbols);
String text = formatter.format(0.256);
```

Đoạn trên là **mã minh họa**, giả định import `Locale`, `DecimalFormatSymbols` và `DecimalFormat`. Kết quả định dạng cụ thể có thể tùy locale data/provider của bản JDK. Vì vậy khi giải thích chính xác stdout, các ví dụ độc lập trong bài chủ động dùng `Locale.US`.

Ngoài việc tự tạo `DecimalFormat`, bạn có thể dùng cách tạo formatter tỷ lệ do nền tảng cung cấp:

```java
java.text.NumberFormat percent =
        java.text.NumberFormat.getPercentInstance(Locale.US);
String text = percent.format(0.256);
```

`NumberFormat.getPercentInstance(locale)` chọn kiểu định dạng phần trăm thích hợp với locale. Kết quả có thể khác một pattern tự viết `0.0%` về số chữ số thập phân, khoảng trắng và vị trí ký hiệu. Không ép cast sang `DecimalFormat` nếu mục tiêu là portable code với các provider khác nhau; `NumberFormat` cung cấp API cần thiết cho `format` và `parse`.

**Cảnh báo về thang đo:** người dùng nhập `25.6%`, parse bằng formatter phần trăm sẽ ra khoảng `0.256`. Nếu sau đó đưa `0.256` vào formatter `0.0%`, sẽ ra `25.6%`. Nhưng nếu lưu trực tiếp `25.6` rồi format như ratio, kết quả thành `2560.0%`. Thang đo dữ liệu cần được mô tả trong tên trường/API, không thể suy ra chỉ từ formatter.

## 10. `DecimalFormatSymbols` và các ký hiệu tùy chỉnh

`DecimalFormatSymbols` lưu các ký hiệu được dùng khi format/parse, như dấu thập phân, phân nhóm, ký hiệu phần trăm và phần nghìn. Bạn có thể đọc hoặc tùy chỉnh chúng:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);

char percentSymbol = symbols.getPercent();
char perMilleSymbol = symbols.getPerMill();
```

Đó là **đoạn mã minh họa** dùng sau khi import `java.text.DecimalFormatSymbols` và `java.util.Locale`. `getPerMill()` trả ký hiệu phần nghìn, khác với dấu phân tách hàng nghìn (`getGroupingSeparator()`).

Những phương thức hữu ích gồm:

| API | Vai trò |
| --- | --- |
| `getPercent()` / `setPercent(char)` | Ký hiệu phần trăm của formatter |
| `getPerMill()` / `setPerMill(char)` | Ký hiệu phần nghìn |
| `getDecimalSeparator()` | Ký tự phân cách phần thập phân |
| `getGroupingSeparator()` | Ký tự phân nhóm chữ số |
| `getInstance(locale)` | Tạo symbols theo locale |

**Phân biệt rõ:** thay ký hiệu bằng `setPercent(char)` không có nghĩa đổi hệ số toán học từ 100 thành một giá trị khác. Tương tự, `setPerMill(char)` chỉ xử lý ký hiệu, không tự đổi cách dùng thang đo nghiệp vụ. Nếu pattern đang chứa `%`, formatter vẫn dùng ngữ nghĩa nhân 100, trừ khi bạn cố ý thay multiplier của chính `DecimalFormat`.

Nên hạn chế tùy chỉnh symbols chỉ vì muốn một output “trông giống mong đợi”; thường việc chọn đúng `Locale` và kiểu formatter đã đủ. Symbols có thể được cấu hình riêng khi cần giao thức hoặc kiểu hiển thị đặc thù có đặc tả rõ ràng.

## 11. `setMultiplier`, `applyPattern` và thứ tự cấu hình

`DecimalFormat` chứa trạng thái: pattern, ký hiệu, số chữ số, rounding mode và multiplier. Một số lệnh cấu hình có thể ảnh hưởng các thuộc tính khác. Vì vậy đừng trộn lẫn các bước một cách ngẫu nhiên.

Quy tắc thực dụng:

1. Chọn `Locale` và `DecimalFormatSymbols`.
2. Tạo formatter với pattern phù hợp với **đơn vị hiển thị**.
3. Chỉ gọi `setMultiplier` nếu nghiệp vụ cần một hệ số **khác** với hệ số ngầm định của pattern.
4. Cấu hình số chữ số và rounding mode.
5. Viết test cho cả `format` và `parse` (nếu ứng dụng cần parse).

`applyPattern` thay đổi pattern và có thể thiết lập lại multiplier theo ký hiệu `%`/`‰` có trong pattern mới. Nếu bạn phải dùng multiplier đặc biệt, nên định nghĩa lại thứ tự cấu hình một cách rõ ràng và xác nhận bằng `getMultiplier()`.

Đặc biệt, **không** dùng pattern `0.0%` kết hợp hệ số `1000` khi mục đích thực sự là phần nghìn: ký hiệu hiển thị và phép biến đổi đã lệch nhau. Muốn phần nghìn, hãy dùng mẫu có `‰` và hệ số mặc định tương ứng.

## 12. Parse nghiêm ngặt và dữ liệu bên ngoài

Nếu người dùng gửi chuỗi tỷ lệ qua ô nhập liệu, đầu vào có thể chứa khoảng trắng, ký hiệu khác locale hoặc hậu tố không hợp lệ. `parse(String)` có thể chỉ tiêu thụ một phần chuỗi, nên khi cần xác thực toàn bộ cần quản lý vị trí parse.

Một ví dụ độc lập:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class StrictPercentParseDemo {
    static double parseAll(String input) {
        DecimalFormat fmt = new DecimalFormat(
                "0.0%",
                DecimalFormatSymbols.getInstance(Locale.US));

        ParsePosition pos = new ParsePosition(0);
        Number number = fmt.parse(input, pos);

        if (number == null || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid percent input");
        }
        return number.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(parseAll("25.6%"));

        try {
            System.out.println(parseAll("25.6%extra"));
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Lưu `StrictPercentParseDemo.java` với UTF-8 và chạy:

```bash
javac -encoding UTF-8 StrictPercentParseDemo.java
java StrictPercentParseDemo
```

Stdout:

```text
0.256
Invalid percent input
```

Điều kiện `pos.getIndex() == input.length()` bảo đảm parser đã đọc hết đầu vào; `number == null` phát hiện không parse được. Tùy chính sách, bạn có thể kiểm tra thêm khoảng giá trị (ví dụ 0 đến 1 đối với một xác suất), `NaN`/vô cực, định dạng bắt buộc hoặc làm tròn. Đó là **kiểm tra nghiệp vụ**, không phải trách nhiệm ngầm của `DecimalFormat`.

Trường hợp nhập liệu tài chính có yêu cầu chữ số chính xác, có thể bật `fmt.setParseBigDecimal(true)` và dùng `BigDecimal`, kết hợp kiểm tra format/scale/rounding. Dù vậy, parse thành BigDecimal không thể tự khôi phục những chữ số đã bị làm tròn mất trong chuỗi đầu vào.

## 13. Khi nào không nên dùng DecimalFormat để biến đổi dữ liệu?

`DecimalFormat` là formatter **cho trình bày và đọc lại dữ liệu theo locale**. Những trường hợp không nên dựa vào text formatting:

- **Tính lãi suất và số tiền:** dùng công thức nghiệp vụ và kiểu số phù hợp (`BigDecimal` khi cần), sau đó mới format để hiển thị.
- **Giao thức máy–máy:** JSON number, CSV theo định dạng chuẩn, API payload, timestamp… cần kiểu dữ liệu và serializer theo đặc tả, không dùng chuỗi đã thêm `%`/ `‰` nếu hợp đồng không cho phép.
- **So sánh dữ liệu:** không so `"9.9%"` với `"10%"` bằng thứ tự từ điển; so giá trị tỷ lệ gốc.
- **Thay đổi thang đo lưu trữ:** không lấy kết quả format rồi xóa dấu `%` để lưu thành số mới. Việc chuyển ratio sang percentage points cần công thức dữ liệu được đặt tên tường minh.
- **Bảo mật và validation:** `DecimalFormat` không phải bộ xác thực toàn bộ input theo ngữ pháp nghiệp vụ, không thay thế kiểm tra phạm vi và kiểm soát nguồn dữ liệu.

Trong những hệ thống có nhiều locale, code tính toán nên độc lập locale. Chỉ khi hiển thị dữ liệu cho người dùng mới chọn `Locale` và mẫu định dạng phù hợp.

## 14. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Truyền `25.6` vào `0.0%` khi 25.6 đã là phần trăm | Hiện `2560.0%` | Chuẩn hóa dữ liệu ratio thành `0.256` hoặc đổi hợp đồng hiển thị |
| Dùng `%` thay cho `‰` | Sai hệ số 10 lần | Dùng đúng ký hiệu và hệ số ngầm định |
| Nghĩ dấu `‰` là dấu phân cách hàng nghìn | Nhầm ý nghĩa toán học | `‰` là tỷ lệ trên 1000, grouping separator là ký hiệu khác |
| Quote `%` mà tưởng vẫn nhân 100 | In `0.3%` từ `0.256` | Dùng `0.0%` để thực sự nhân 100 |
| Gọi `setMultiplier(1000)` trên pattern `%` | Nhân sai dù nhãn vẫn là % | Khớp multiplier với đơn vị/pattern |
| Tưởng `parse(format(x)) == x` tuyệt đối | Mất chữ số do làm tròn | Giữ giá trị nguồn và kiểm tra scale mong muốn |
| Chọn `Locale.getDefault()` tùy máy chủ | Chuỗi thay đổi theo môi trường | Truyền locale dự kiến của người dùng |
| Quên `ParseException` / parse một phần input | Chấp nhận chuỗi không hợp lệ | Xử lý exception và kiểm tra `ParsePosition` |
| Dùng `double` cho mọi phép tính tài chính | Sai số dấu phẩy động | Dùng `BigDecimal` với quy tắc rounding rõ |
| Chia sẻ một `DecimalFormat` mutable giữa các luồng | Trạng thái có thể bị thay đổi đồng thời | Tạo instance theo request/call hoặc có chiến lược đồng bộ an toàn |
| Dùng text đã format làm dữ liệu API | Phụ thuộc locale và ký hiệu | Giữ kiểu số/serializer chuẩn |

**Thread safety:** `DecimalFormat` là formatter mutable, không nên chia sẻ tự do giữa nhiều thread khi có thể bị cập nhật đồng thời. Nếu cần cache, cân nhắc bản sao hoặc quản lý thread/concurrency phù hợp.

## 15. Checklist kiểm thử và bài tập

Một bộ kiểm thử cơ bản cần ít nhất:

1. **Các đơn vị:** `0.256` -> `25.6%`, `256.0‰`; `getMultiplier()` bằng `100` và `1000`.
2. **Ranh giới:** `0`, `0.01`, `1`, `1.5`, số âm nếu nghiệp vụ cho phép.
3. **Độ chính xác:** `0%`, `0.0%`, `0.00%` cho cùng dữ liệu để thấy rounding khác nhau.
4. **Quote ký hiệu:** `0.0'%'` phải có multiplier `1`, không phải `100`.
5. **Custom multiplier:** `setMultiplier(1000)` với `0.00` format/parse nhất quán và không tự thêm dấu `‰`.
6. **Round-trip có điều kiện:** chỉ kỳ vọng parse ra đúng đến độ chính xác hiển thị; không mất dữ liệu nguồn.
7. **Locale:** xác minh đầu ra và parse với các locale ứng dụng thực sự hỗ trợ, không hard-code dấu thập phân từ `Locale.US` trong code đa ngôn ngữ.
8. **Input sai:** ký hiệu thiếu/sai, chuỗi dư hậu tố, ký tự không hợp lệ, giá trị ngoài phạm vi nghiệp vụ.
9. **Đồng thời:** tránh chia sẻ formatter mutable bị thay pattern giữa các request.

Bài tập thực hành:

- Viết formatter `"0.00%"` cho `ratio = 0.0425`. Dự đoán cách làm tròn và kiểm tra bằng Java.
- Thay `"0.0‰"` thành `"0‰"` cho `0.2568`; giải thích giá trị hiển thị và lượng thông tin bị bỏ.
- Tạo `DecimalFormat("0.00", symbols)`, gọi `setMultiplier(100)` và kiểm tra vì sao đầu ra không có `%` nếu pattern thiếu ký hiệu.
- Parse `"12.5%"` bằng formatter tỷ lệ, rồi nhân ngược 100 một lần để trình bày “số phần trăm”. Giải thích vì sao **không** tiếp tục nhân trong formatter tỷ lệ lần nữa.
- Tạo một input `"25.6%unexpected"`; kiểm tra `parse(String)` và `parse(String, ParsePosition)` để hiểu parse một phần.

## 16. Kết luận

Trong `DecimalFormat`, ký hiệu `%` và `‰` ở **pattern không được quote** lần lượt đặt hệ số `100` và `1000`. `setMultiplier` cho phép dùng hệ số khác mà không mặc nhiên thêm ký hiệu. Khi format, dữ liệu được nhân rồi hiển thị theo pattern; khi parse, giá trị được đổi ngược về thang gốc theo multiplier. Locale, ký hiệu, số chữ số và rounding cũng ảnh hưởng kết quả.

Để tránh sai số và sai đơn vị, hãy **định nghĩa thang đo của dữ liệu trước**, chọn pattern phù hợp để hiển thị, parse có validation khi nhận dữ liệu từ bên ngoài, và không dùng chuỗi đã format làm nguồn tính toán.

## Tài liệu tham khảo

- [Oracle Java 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Oracle Java 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html)
- [Oracle Java 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Oracle Java 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
