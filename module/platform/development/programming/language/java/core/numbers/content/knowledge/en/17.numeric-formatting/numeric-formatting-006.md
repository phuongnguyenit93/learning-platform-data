# NumberFormat cho số thường, phần trăm và tiền tệ trong Java

## 1. Vì sao cần NumberFormat?

Một giá trị số có thể được **biểu diễn khác nhau tùy ngôn ngữ và quốc gia**, dù giá trị toán học không đổi. Ví dụ **12345.67** trong giao diện Mỹ thường là **12,345.67**, còn trong giao diện Đức là **12.345,67**. Số phần trăm, giá tiền còn thêm quy tắc về dấu %, ký hiệu tiền tệ, chữ số thập phân và khoảng trắng.

Trong Java, **java.text.NumberFormat** là API định dạng và phân tích (*format/parse*) số theo **Locale**. Đây là một lớp trừu tượng, thường lấy phiên bản cụ thể qua các phương thức factory.

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
String shown = number.format(12345.67); // "12,345.67"
~~~

Đoạn trên là mã minh họa đặt trong phương thức Java. API không nhằm thay đổi **giá trị** đầu vào mà chuyển giá trị sang **chuỗi hiển thị**; khi phân tích chuỗi đầu vào, phải dùng cùng quy ước Locale phù hợp.

Mục tiêu bài học:

- Phân biệt **getNumberInstance**, **getIntegerInstance**, **getPercentInstance** và **getCurrencyInstance**.
- Hiểu vai trò của **Locale**, chữ số thập phân, phân nhóm và số chữ số được hiển thị.
- Biết tỷ lệ **0.125** có thể hiển thị thành **12.5%**, không phải **0.125%**.
- Biết format tiền tệ là **định dạng**, không phải **chuyển đổi tỷ giá**.
- Làm tròn có chủ đích, phân biệt **giá trị lưu trữ** và **chuỗi đã làm tròn**.
- Parse chuỗi theo Locale, dùng **ParsePosition**, **DecimalFormat.setParseBigDecimal(true)** khi cần số thập phân chính xác.
- Nhận diện sai lầm trong ứng dụng nhiều luồng, tiền tệ, dữ liệu máy và dữ liệu không đáng tin.

**Phạm vi:** ví dụ sử dụng Java 17+, ưu tiên **Locale.US** để stdout dễ kiểm chứng. Với Locale khác, ký hiệu và khoảng trắng có thể khác theo dữ liệu địa phương hóa của JDK.

## 2. Các factory method quan trọng

| API | Loại chuỗi cần hiển thị | Ví dụ ở Locale.US |
| --- | --- | --- |
| **NumberFormat.getNumberInstance(locale)** | Số thường | **12,345.67** |
| **NumberFormat.getInstance(locale)** | Tương đương định dạng số thường | **12,345.67** |
| **NumberFormat.getIntegerInstance(locale)** | Số nguyên, format phần thập phân về số nguyên | **12,346** từ 12345.6 |
| **NumberFormat.getPercentInstance(locale)** | Phần trăm | **12%** từ 0.12 |
| **NumberFormat.getCurrencyInstance(locale)** | Tiền tệ | **$1,234.56** từ 1234.56 |

Các factory trả về **NumberFormat**, một API bao quát chung, không nhất thiết trả đối tượng của đúng một subclass trên mọi JDK/provider. Trên các JDK phổ biến, những dạng số thường, phần trăm, tiền tệ thường là **DecimalFormat**; nếu cần API riêng của DecimalFormat, hãy kiểm tra **instanceof** trước khi ép kiểu.

Để hiển thị gọn số lớn, Java 12+ còn có **getCompactNumberInstance(locale, style)**, nhưng đây là chức năng bổ sung, không thay thế các ba dạng định dạng chính của bài.

### Không truyền Locale thì dùng Locale nào?

~~~java
NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit = NumberFormat.getNumberInstance(Locale.US);
~~~

Biến implicit dùng **Locale mặc định thuộc Locale.Category.FORMAT** của môi trường chạy. Locale này có thể phụ thuộc máy chủ, JVM, container hoặc cấu hình ứng dụng; vì vậy stdout và UI có thể khác nhau giữa các môi trường.

Trong sản phẩm đa ngôn ngữ, nên **truyền Locale đã xác định** theo lựa chọn người dùng hoặc cấu hình giao diện. Không giả định JVM của mọi máy đều có Locale.US, và không đặt một Locale mặc định toàn tiến trình chỉ để xử lý một request.

## 3. Format số thường

~~~java
NumberFormat f = NumberFormat.getNumberInstance(Locale.US);
System.out.println(f.format(12345.67)); // "12,345.67"
~~~

Với Locale.US, dấu phẩy thường chia nhóm hàng nghìn, dấu chấm đánh dấu phần thập phân. Với Locale.GERMANY, hai vai trò đảo ngược: **12.345,67**.

Các phương thức điều chỉnh:

| API | Chức năng |
| --- | --- |
| **setGroupingUsed(true/false)** | Bật/tắt phân nhóm chữ số, không thay đổi số |
| **setMinimumIntegerDigits(n)** | Số chữ số nguyên tối thiểu, có thể thêm zero đầu |
| **setMaximumIntegerDigits(n)** | Số chữ số nguyên tối đa trong chuỗi format; phải hiểu nguy cơ cắt phần đầu |
| **setMinimumFractionDigits(n)** | Số chữ số thập phân hiển thị tối thiểu, thêm zero nếu cần |
| **setMaximumFractionDigits(n)** | Số chữ số thập phân hiển thị tối đa, có thể làm tròn |
| **setRoundingMode(mode)** | Quy tắc làm tròn khi cần bỏ bớt chữ số |

Ví dụ điều khiển hiển thị:

~~~java
NumberFormat f = NumberFormat.getNumberInstance(Locale.US);
f.setGroupingUsed(true);
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(2);
f.setRoundingMode(java.math.RoundingMode.HALF_UP);

System.out.println(f.format(12345.678)); // "12,345.68"
System.out.println(f.format(12));        // "12.00"
~~~

**setMinimumFractionDigits(2)** buộc luôn có ít nhất hai chữ số sau dấu thập phân. **setMaximumFractionDigits(2)** giới hạn tối đa hai chữ số; khi giá trị có chữ số tiếp theo, việc format có thể làm tròn theo RoundingMode. Bản thân giá trị **12345.678** truyền vào không bị sửa.

### Thứ tự thiết lập min/max

Giá trị minimum fraction digits không được lớn hơn maximum fraction digits. Trong các subclass chuẩn, nếu đặt min vượt max hiện hành, maximum có thể được tự điều chỉnh tương ứng; tương tự khi đặt max nhỏ hơn min. Do đó nên đặt **cả hai** theo cấu hình rõ ràng và kiểm tra getMinimumFractionDigits/getMaximumFractionDigits nếu tái sử dụng một formatter được truyền từ nơi khác.

**setGroupingUsed(false)** chủ yếu phù hợp với hiển thị muốn bỏ nhóm chữ số, nhưng chưa đủ để đảm bảo cú pháp dữ liệu máy độc lập Locale: dấu thập phân vẫn theo Locale.

## 4. Số nguyên: getIntegerInstance không có nghĩa đầu vào là int

~~~java
NumberFormat f = NumberFormat.getIntegerInstance(Locale.US);
String result = f.format(12345.6); // "12,346"
~~~

Formatter cho số nguyên **làm tròn biểu diễn đầu ra** theo quy tắc được cấu hình. Theo Java 17, factory integer mặc định dùng **RoundingMode.HALF_EVEN** khi format số thực; vì vậy đừng giả sử luôn cắt phần thập phân về 0.

Quan trọng:

- **getIntegerInstance** nhận cả double/long và các Number phù hợp; đây là **phong cách định dạng**, không phải phép kiểm tra kiểu dữ liệu đầu vào.
- Khi **parse**, formatter integer được cấu hình để chỉ phân tích phần nguyên (*parseIntegerOnly*). Đừng dùng nó để parse đầy đủ một chuỗi tiền hoặc số thập phân mà không kiểm tra.
- Nếu mục tiêu là ép kiểu số học, dùng chuyển đổi có kiểm tra giới hạn, không suy ra kiểu dữ liệu mới chỉ từ chuỗi đã format.

Đối với các trường hợp phải kiểm soát cách làm tròn số nguyên như RoundingMode.DOWN, UP, HALF_EVEN hoặc HALF_UP, chọn quy tắc theo yêu cầu nghiệp vụ và gọi **setRoundingMode** khi subclass hỗ trợ.

## 5. Percent: phần trăm nhân giá trị với 100 khi hiển thị

**getPercentInstance(locale)** thể hiện một tỷ lệ dưới dạng phần trăm. Giá trị đầu vào thường ở dạng **0..1** khi nói tới tỷ lệ từ 0% đến 100%:

| Giá trị số | Chuỗi phần trăm kỳ vọng ở Locale.US |
| ---: | --- |
| 0 | **0%** |
| 0.12 | **12%** |
| 0.5 | **50%** |
| 1 | **100%** |
| 1.25 | **125%** |

Nó không giới hạn giá trị đầu vào vào đoạn [0,1]. Tỷ lệ tăng trưởng 125% có thể hợp lệ theo bài toán; tỷ lệ âm cũng có thể biểu diễn được.

~~~java
NumberFormat pct = NumberFormat.getPercentInstance(Locale.US);
pct.setMinimumFractionDigits(1);
pct.setMaximumFractionDigits(1);
pct.setRoundingMode(java.math.RoundingMode.HALF_UP);

System.out.println(pct.format(0.1234)); // "12.3%"
System.out.println(pct.format(1.0));    // "100.0%"
~~~

**Bẫy phổ biến:** nếu dữ liệu đã lưu **12.5** với ý nghĩa **12.5%**, gọi **format(12.5)** sẽ hiển thị **1250%**. Cần chuyển về tỷ lệ **0.125** trước hoặc định nghĩa lại hợp đồng dữ liệu.

Cách xử lý đúng cần bắt đầu từ **nghĩa của trường dữ liệu**:

- Hợp đồng **fraction/rate**: 0.125 biểu thị 12.5%, dùng percent formatter trực tiếp.
- Hợp đồng **percentage points**: 12.5 biểu thị 12.5%; muốn dùng percent formatter phải chuyển thành 0.125 bằng phép chia 100, hoặc định dạng theo một cách rõ ràng khác.

### Làm tròn tỷ lệ

Nếu maximum fraction digits bằng 1, giá trị **0.12345** có thể hiển thị **12.3%** dù giá trị chính xác tương ứng là 12.345%. Chuỗi hiển thị không còn chứa mọi chữ số ban đầu. Không nên lưu lại tỷ lệ bằng cách parse chuỗi đã được làm tròn và coi đó là dữ liệu gốc.

### Parse chuỗi phần trăm

Một percent formatter thường phân tích **"12.5%"** thành giá trị tỷ lệ **0.125** theo quy tắc Locale tương ứng. Cần phân biệt thao tác này với parse số thường **"12.5"**. Cũng phải kiểm tra dấu %, khoảng trắng và cách ghi số được Locale sử dụng; không suy rằng mọi quốc gia cùng ghi ký hiệu % ở cùng vị trí.

## 6. Currency: định dạng tiền tệ không phải đổi ngoại tệ

~~~java
NumberFormat usd = NumberFormat.getCurrencyInstance(Locale.US);
System.out.println(usd.format(1234.56)); // "$1,234.56"
~~~

Formatter tiền tệ sử dụng cách đặt ký hiệu, dấu nhóm, dấu thập phân và số chữ số theo thông tin của Locale/currency formatter.

Với Locale.US, tiền tệ mặc định thường là **USD** và hiển thị ký hiệu **$**. Ở Locale khác, ký hiệu có thể đứng **sau số**, cách số bằng dấu cách không ngắt dòng, hoặc dùng dạng tiền tệ khác theo cấu hình địa phương hóa. Không nối thủ công **"$" + formattedNumber** và giả sử đúng với mọi quốc gia.

### Rounding và số chữ số tiền tệ

Mỗi tiền tệ có thể có số chữ số thập phân thông dụng khác nhau (ví dụ USD thường 2; JPY thường 0). **Currency.getDefaultFractionDigits()** cung cấp thông tin theo đơn vị tiền tệ; tuy nhiên nó **không phải toàn bộ quy tắc làm tròn của giao dịch**. Thanh toán, thuế, tiền mặt, quy định pháp lý có thể có các quy tắc riêng.

Ví dụ khi muốn xuất USD với 2 chữ số, dùng:

~~~java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.US);
money.setMinimumFractionDigits(2);
money.setMaximumFractionDigits(2);
money.setRoundingMode(java.math.RoundingMode.HALF_UP);

String shown = money.format(new java.math.BigDecimal("1234.567"));
// "$1,234.57"
~~~

**Không dùng chuỗi đã format làm nơi lưu giá trị tiền.** Trong ví dụ, giá trị BigDecimal vẫn là 1234.567, nhưng chuỗi hiển thị chỉ có 2 chữ số sau dấu thập phân.

### Currency.getInstance và setCurrency

~~~java
java.util.Currency euro = java.util.Currency.getInstance("EUR");
NumberFormat formatter = NumberFormat.getCurrencyInstance(Locale.US);
formatter.setCurrency(euro);
~~~

Lệnh **setCurrency(euro)** thay thông tin tiền tệ được dùng bởi formatter, **không thực hiện quy đổi tỷ giá từ USD sang EUR**. Giá trị 100 vẫn là 100 theo dữ liệu được truyền. Muốn quy đổi phải có tỷ giá, thời điểm, chính sách làm tròn và nghiệp vụ tương ứng.

**Lưu ý API quan trọng:** **NumberFormat.setCurrency(...) không tự cập nhật minimum/maximum fraction digits**. Nếu đổi Currency của formatter đã tạo, cần xem xét và thiết lập lại số chữ số khi cần, thay vì mong nó tự đổi theo đồng tiền mới.

### Mã ISO và ký hiệu không đồng nhất

**Currency.getCurrencyCode()** trả mã như **USD**, **EUR** hoặc **VND**. Ký hiệu **$** có thể mang nghĩa khác nhau ở nhiều quốc gia. Khi dữ liệu lưu chuyển qua dịch vụ/API, hãy truyền **mã tiền tệ ISO** như một trường riêng, không dùng duy nhất ký hiệu được hiển thị cho người dùng.

## 7. Locale chi phối ngữ nghĩa hiển thị và parse

`NumberFormat.getNumberInstance(Locale.US)` thường dùng dấu phẩy nhóm và dấu chấm thập phân; `Locale.GERMANY` thường dùng dấu chấm nhóm và dấu phẩy thập phân. Không sử dụng `Locale.getDefault()` cho dữ liệu có hợp đồng cố định hoặc test cần lặp lại. Với đầu vào có dấu phân cách theo vùng, `Double.parseDouble` không tự hiểu locale. Cách kiểm chứng dấu, ký tự số, dấu âm và grouping chuyên sâu nằm ở bài `Locale, dấu thập phân, nhóm chữ số và dấu âm`.

## 8. Chữ số và làm tròn khi format

`setMinimumFractionDigits`/`setMaximumFractionDigits`, `setMinimumIntegerDigits`, `setGroupingUsed` và `setRoundingMode` thay đổi cách in **giá trị**, không sửa số gốc. Ví dụ `getNumberInstance(Locale.US)` được đặt tối đa hai chữ số phần lẻ có thể in `12.35` từ nguồn `12.345` theo mode phù hợp, nhưng biến nguồn vẫn `12.345`. Số chữ số hiển thị khác độ chính xác nhị phân của `double` và khác scale của `BigDecimal`. Hai bài về giới hạn chữ số và `RoundingMode` trình bày chi tiết chính sách này.

## 9. Parse qua NumberFormat cần hợp đồng dữ liệu

`NumberFormat.parse(String)` có thể tiêu thụ một **tiền tố hợp lệ** và bỏ phần đuôi mà không ném `ParseException`. Khi một trường nhập chỉ chứa số, dùng `parse(text, new ParsePosition(0))` và kiểm tra `result != null` cùng `position.getIndex() == text.length()`; kiểm tra này chưa bảo đảm grouping luôn đúng yêu cầu nghiêm ngặt.

```java
java.text.ParsePosition pos = new java.text.ParsePosition(0);
java.text.NumberFormat nf = java.text.NumberFormat.getNumberInstance(java.util.Locale.US);
String input = "123abc";
Number n = nf.parse(input, pos);
System.out.println(n != null && pos.getIndex() == input.length()); // false
```

Bài `ParsePosition và kiểm tra toàn bộ chuỗi` đi sâu về vị trí lỗi, chỉ số UTF-16 và validation chặt.

## 10. Khi cần decimal chính xác

`NumberFormat.parse` trả về `Number`, có thể là `Long`, `Double` hoặc kiểu khác theo cấu hình. Khi cần parse trực tiếp thành `BigDecimal` hữu hạn từ chuỗi localized, `DecimalFormat.setParseBigDecimal(true)` là một lựa chọn; cần kiểm tra actual subtype vì token NaN/Infinity có thể trả `Double`. Không chuyển qua `doubleValue()` trước khi tạo decimal cần chính xác. Bài `setParseBigDecimal và giới hạn an toàn khi dùng formatter đồng thời` bàn kỹ về loại trả về, -0.0 và an toàn giữa các thread.

## 11. Chương trình Java 17+ có thể biên dịch/chạy

Tạo tệp **NumberFormatDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberFormatDemo {
    static BigDecimal parseWhole(String text, DecimalFormat format) {
        ParsePosition pos = new ParsePosition(0);
        Number parsed = format.parse(text, pos);
        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid localized number");
        }
        return (BigDecimal) parsed;
    }

    public static void main(String[] args) {
        NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
        number.setGroupingUsed(true);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(2);
        number.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("number: " + number.format(12345.678));

        NumberFormat noGrouping = NumberFormat.getNumberInstance(Locale.US);
        noGrouping.setGroupingUsed(false);
        noGrouping.setMaximumFractionDigits(0);
        System.out.println("no grouping: " + noGrouping.format(12345));

        NumberFormat integer = NumberFormat.getIntegerInstance(Locale.US);
        System.out.println("integer: " + integer.format(12345.6));

        NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
        percent.setMinimumFractionDigits(1);
        percent.setMaximumFractionDigits(1);
        percent.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("percent: " + percent.format(0.1234));
        System.out.println("percent one: " + percent.format(1.0));

        NumberFormat money = NumberFormat.getCurrencyInstance(Locale.US);
        money.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("currency: "
                + money.format(new BigDecimal("1234.567")));
        System.out.println("currency code: "
                + money.getCurrency().getCurrencyCode());

        NumberFormat candidate = NumberFormat.getNumberInstance(Locale.US);
        if (!(candidate instanceof DecimalFormat)) {
            throw new IllegalStateException("DecimalFormat is required");
        }
        DecimalFormat parser = (DecimalFormat) candidate;
        parser.setParseBigDecimal(true);

        BigDecimal parsed = parseWhole("1,234.50", parser);
        System.out.println("parsed exact: " + parsed.toPlainString());
        try {
            parseWhole("1,234.50 xyz", parser);
        } catch (IllegalArgumentException e) {
            System.out.println("trailing text: rejected");
        }

        BigDecimal precise = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal sum: " + number.format(precise));

        NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
        german.setMinimumFractionDigits(2);
        german.setMaximumFractionDigits(2);
        System.out.println("de number: " + german.format(12345.67));
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 NumberFormatDemo.java
java NumberFormatDemo
~~~

Stdout đã kiểm tra trên JDK với các Locale nêu trên:

~~~text
number: 12,345.68
no grouping: 12345
integer: 12,346
percent: 12.3%
percent one: 100.0%
currency: $1,234.57
currency code: USD
parsed exact: 1234.50
trailing text: rejected
decimal sum: 0.30
de number: 12.345,67
~~~

Các phần cần lý giải:

- **number**: phân nhóm hàng nghìn, giữ chính xác hai chữ số khi hiển thị và làm tròn HALF_UP từ 12345.678.
- **integer**: factory integer tạo chuỗi không có phần thập phân, nhưng nhận một double đầu vào.
- **percent**: tỷ lệ 0.1234 được nhân theo ngữ nghĩa phần trăm rồi hiển thị 12.3%.
- **currency**: bản thân BigDecimal("1234.567") không bị thay đổi; formatter xuất hai chữ số cho USD.
- **parsed exact**: DecimalFormat trả lại BigDecimal giữ 1234.50 (bao gồm scale phù hợp với chuỗi được parse trong trường hợp này).
- **trailing text**: parse có thể dừng trước ký tự cuối, và parseWhole chủ động từ chối vì không tiêu thụ hết chuỗi.
- **decimal sum**: BigDecimal("0.1") + BigDecimal("0.2") cho 0.3 chính xác; cấu hình number với minimum 2 chữ số xuất 0.30.
- **de number**: dấu nhóm và dấu thập phân được đảo vị trí so với Locale.US.

Với Locale đặc thù hoặc provider tùy biến, chính tả và khoảng trắng có thể khác. Khi viết bài kiểm thử thực tế, cố định Locale và hiểu dữ liệu địa phương hóa của runtime.

## 12. NumberFormat và tiền chính xác: trách nhiệm tách biệt

Một hệ thống tài chính thường cần phân biệt:

1. **Giá trị nghiệp vụ**: số thập phân chính xác, đơn vị tiền tệ, scale/precision, cách quy đổi khi có.
2. **Tính toán và làm tròn theo luật nghiệp vụ**: ví dụ làm tròn giá đơn vị, thuế, tổng hóa đơn theo thứ tự cụ thể.
3. **Hiển thị**: dùng NumberFormat/DecimalFormat phù hợp Locale để tạo chuỗi người dùng đọc được.
4. **Phân tích đầu vào từ giao diện**: parse theo Locale và kiểm tra có đúng đơn vị tiền tệ, miền và quy tắc đã đặt hay không.

Nếu tính toán bằng double, số thập phân thường không biểu diễn chính xác hoàn toàn; định dạng ra chuỗi đẹp không sửa sai số đã phát sinh. Với tiền, có thể dùng **BigDecimal từ chuỗi** và **RoundingMode** theo hợp đồng, rồi NumberFormat chỉ đảm nhận hiển thị.

Đừng nhầm hai thao tác:

- **format(new BigDecimal("1.235"))** thành **"1.24"** theo HALF_UP với hai chữ số: **làm tròn ở khâu trình bày**.
- **value.setScale(2, HALF_UP)**: tạo **BigDecimal giá trị mới** làm tròn theo quy tắc nghiệp vụ để sử dụng trong tính toán/ghi dữ liệu.

Hai thao tác có thể cho cùng số hiện trên màn hình, nhưng thời điểm áp dụng quy tắc trong hệ thống có thể rất khác. Mọi dữ liệu phải thỏa chính sách tiền tệ trước khi ghi sổ.

## 13. Formatter là đối tượng mutable

`NumberFormat` và `DecimalFormat` có nhiều setter, nên không chia sẻ một instance mutable giữa các request đồng thời nếu không đồng bộ phù hợp. Dùng instance cục bộ, cơ chế riêng theo thread hoặc đồng bộ được thiết kế rõ. Bài `setParseBigDecimal và giới hạn an toàn khi dùng formatter đồng thời` nêu mã và đánh đổi của từng cách.

## 14. Định dạng hiển thị khác định dạng truyền dữ liệu

Chuỗi in theo locale như `1,234.56` hoặc `1.234,56` phù hợp UI, nhưng một giao thức machine-to-machine phải quy định cú pháp và kiểu số tường minh. Đừng tự dùng `NumberFormat` để tạo JSON number/CSV canonical. Bài `Không dùng chuỗi đã định dạng cho người đọc làm dạng trao đổi dữ liệu mặc định` giải thích đầy đủ về schema và serializer.

## 15. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Dùng NumberFormat không có Locale cố định cho snapshot test | Máy chạy có Locale mặc định khác | Truyền Locale tường minh |
| Dùng getNumberInstance để hiển thị phần trăm | Không tự nhân tỷ lệ với 100/không thêm % | Dùng getPercentInstance nếu dữ liệu là tỷ lệ |
| Truyền 12.5 vào percent formatter khi muốn 12.5% | Sẽ thành 1250% | Đưa vào 0.125 hoặc thống nhất hợp đồng dữ liệu |
| Ghép ký hiệu "$" với số đã format | Sai vị trí/ký hiệu ở nhiều quốc gia | Dùng getCurrencyInstance(locale) |
| Gọi setCurrency và nghĩ đã chuyển tỷ giá | Nó chỉ thay metadata/biểu diễn | Quy đổi tiền trong nghiệp vụ riêng |
| Đổi Currency rồi nghĩ fraction digits tự đổi | setCurrency không cập nhật min/max fraction digits | Thiết lập lại số chữ số thích hợp |
| Mặc định rằng format không làm tròn | Giới hạn chữ số có thể làm tròn | Chọn RoundingMode và max digits rõ ràng |
| Dùng double để tính tiền chính xác thập phân | Sai số nhị phân có thể tích lũy | BigDecimal + quy tắc làm tròn |
| Parse chuỗi rồi bỏ qua phần còn lại | "123abc" có thể được parse một phần | Kiểm tra ParsePosition.getIndex() |
| Tin rằng ParsePosition đủ để xác thực mọi cú pháp | Parser có thể lenient với grouping | Bổ sung kiểm tra business grammar |
| Ép kết quả NumberFormat.parse sang BigDecimal | Kết quả có thể là Long/Double | DecimalFormat.setParseBigDecimal hoặc parser riêng |
| Chia sẻ một NumberFormat mutable cho mọi thread | Không bảo đảm thread safety | Một instance mỗi thread/request |
| Chuyển số thành chuỗi UI rồi lưu làm số gốc | Mất chữ số/scale và phụ thuộc Locale | Lưu dữ liệu số theo mô hình miền |
| Thay dấu chấm và dấu phẩy bằng String.replace | Có thể đảo nhầm decimal/grouping separator | Parse bằng Locale đúng |

## 16. Bài tập tự kiểm tra

**Bài 1:** **getPercentInstance(Locale.US).format(0.25)** có ý nghĩa gì? Nếu nhập 25 thì sao?

*Đáp án:* 0.25 biểu diễn 25%. Nhập 25 là 2500%, vì formatter coi tham số là tỷ lệ gốc và nhân với 100 ở bước định dạng.

**Bài 2:** **getNumberInstance(Locale.US)** và **getNumberInstance(Locale.GERMANY)** khác điều gì khi format 12345.67?

*Đáp án:* US dùng **12,345.67**, Đức thường dùng **12.345,67**. Cùng giá trị số nhưng khác cách trình bày.

**Bài 3:** Một giá trị BigDecimal("1234.567") được format USD thành "$1,234.57". BigDecimal ban đầu thay đổi không?

*Đáp án:* Không. Format tạo **chuỗi** hiển thị đã làm tròn; BigDecimal bất biến vẫn biểu diễn 1234.567.

**Bài 4:** Vì sao gọi setCurrency(EUR) trên currency formatter đang biểu diễn USD không có nghĩa đã đổi 100 USD thành EUR?

*Đáp án:* API chỉ đổi tiền tệ dùng cho nhãn/định dạng; nó không có tỷ giá hoặc phép tính quy đổi.

**Bài 5:** Tại sao NumberFormat.parse("1,234.50 extra") không đủ cho yêu cầu xác thực toàn bộ chuỗi?

*Đáp án:* Parser có thể dừng ở cuối phần số và bỏ phần dư. Dùng **ParsePosition** để kiểm tra đã đọc toàn bộ, sau đó vẫn kiểm tra cú pháp/miền theo nghiệp vụ.

**Bài 6:** Khi cần parse chữ số thập phân thành BigDecimal, dùng phương thức nào?

*Đáp án:* Trên DecimalFormat, gọi **setParseBigDecimal(true)**; kiểm tra kết quả parse và toàn bộ input. Không thể giả định mọi NumberFormat trả DecimalFormat hay parse mặc định luôn trả BigDecimal.

**Bài 7:** Trong server nhiều luồng, tại sao không nên sửa cấu hình một NumberFormat static mỗi request?

*Đáp án:* Formatter mutable và nhìn chung không đồng bộ hóa; các luồng có thể quan sát trạng thái đang bị sửa. Sử dụng instance riêng theo luồng/request.

**Bài 8:** Muốn ghi số vào JSON và CSV để máy khác đọc, có nên dùng NumberFormat theo locale người dùng làm cấu trúc truyền dữ liệu không?

*Đáp án:* Không nên. Dùng kiểu/chuỗi chuẩn do giao thức quy định và serializer phù hợp; NumberFormat dành cho trình bày theo Locale.

## 17. Tài liệu gốc

- [NumberFormat Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): factory theo Locale, NumberFormat, percent, currency, parse, rounding và đồng bộ hóa.
- [DecimalFormat Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): ký hiệu định dạng, DecimalFormatSymbols, setParseBigDecimal, parsing.
- [ParsePosition Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): vị trí parse, kiểm tra phần văn bản còn lại.
- [Currency Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): mã tiền tệ và default fraction digits.
- [RoundingMode Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) và [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): cách làm tròn thập phân và mô hình số thập phân chính xác.
