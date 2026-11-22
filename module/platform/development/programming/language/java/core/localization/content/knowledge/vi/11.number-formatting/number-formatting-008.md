# Định dạng số có vị trí trường bằng FieldPosition và AttributedCharacterIterator trong Java

## 1. Khi chuỗi đã định dạng vẫn chưa đủ

`NumberFormat.format(...)` thường dùng để chuyển một số thành chuỗi phù hợp với `Locale`, ví dụ `1234567.89` thành `1,234,567.89` với `Locale.US`. Nhưng đôi khi ứng dụng cần biết **vị trí từng phần trong chuỗi kết quả** để tô màu, đặt con trỏ, đọc bằng công nghệ hỗ trợ tiếp cận, hoặc tách phần nguyên và thập phân mà không đoán bằng ký tự dấu phẩy/dấu chấm.

Java cung cấp hai cách bổ sung thông tin vị trí:

- **`java.text.FieldPosition`:** yêu cầu một vị trí `[beginIndex, endIndex)` của một trường cụ thể trong quá trình format vào `StringBuffer`. Hữu ích nếu chỉ cần một trường, ví dụ phần nguyên hoặc phần thập phân.
- **`java.text.AttributedCharacterIterator`:** duyệt toàn bộ chuỗi cùng các **thuộc tính (attributes)** gắn trên từng khoảng ký tự; hữu ích khi cần nhiều trường, những trường xuất hiện nhiều lần hoặc các thuộc tính chồng lấp.

Đối với định dạng số, các thuộc tính được khai báo trong `NumberFormat.Field`, ví dụ `INTEGER`, `FRACTION`, `GROUPING_SEPARATOR`, `DECIMAL_SEPARATOR`, `SIGN`, `CURRENCY`, `PERCENT` và `EXPONENT`.

Lưu ý: `FieldPosition` và `AttributedCharacterIterator` **không tự tạo quy tắc định dạng**. Chính `NumberFormat` hoặc `DecimalFormat` chọn dấu phân tách, nhóm chữ số, đơn vị tiền và chữ số theo `Locale`; hai API trên giúp xác định **trường nào nằm ở đâu** trong kết quả.

## 2. Những thành phần có thể xuất hiện trong một số đã định dạng

Với `Locale.US` và mẫu số có hai chữ số sau dấu thập phân, xét:

```text
1,234,567.89
```

Ta có thể chia thành các trường:

| Phần văn bản | Trường `NumberFormat.Field` | Phạm vi trong chuỗi |
|---|---|---|
| `1,234,567` | `INTEGER` | `[0,9)` |
| Dấu `,` thứ nhất | `GROUPING_SEPARATOR` | `[1,2)` |
| Dấu `,` thứ hai | `GROUPING_SEPARATOR` | `[5,6)` |
| Dấu `.` | `DECIMAL_SEPARATOR` | `[9,10)` |
| `89` | `FRACTION` | `[10,12)` |

**Các trường có thể chồng lấp.** Dấu phẩy nhóm chữ số nằm trong khoảng `INTEGER`, đồng thời mỗi dấu phẩy có thuộc tính `GROUPING_SEPARATOR` riêng. Vì vậy không nên hình dung mọi thuộc tính đều phân hoạch chuỗi thành những đoạn không giao nhau.

Từ đây xuất hiện hai nhu cầu:

1. Nếu chỉ muốn biết **toàn bộ phần nguyên** `1,234,567`, một `FieldPosition(NumberFormat.Field.INTEGER)` là đủ.
2. Nếu cần đánh dấu **từng dấu phẩy** và phần thập phân, `AttributedCharacterIterator` phù hợp hơn vì có thể có nhiều run cho cùng thuộc tính.

Các khoảng ở đây đếm bằng **chỉ số ký tự UTF-16 theo Java** (`String`/`StringBuffer`), bắt đầu từ `0` và kết thúc **không bao gồm** `endIndex`. Chúng không phải byte offset UTF-8 và không bảo đảm trùng với chỉ số grapheme người dùng nhìn thấy.

## 3. FieldPosition: một trường và cặp chỉ số đầu/cuối

Một `FieldPosition` được tạo từ trường quan tâm:

```java
FieldPosition position =
        new FieldPosition(NumberFormat.Field.INTEGER);
```

Sau đó truyền nó vào overload định dạng có ba tham số:

```java
StringBuffer buffer = new StringBuffer();
formatter.format(1234567.89, buffer, position);
```

Khi format hoàn tất, đọc:

- `position.getBeginIndex()` — chỉ số bắt đầu, **bao gồm** ký tự này.
- `position.getEndIndex()` — chỉ số kết thúc, **loại trừ** ký tự tại vị trí này.

Dùng `buffer.substring(begin, end)` để lấy phần được định vị. Chính vì cuối là exclusive nên độ dài của vùng là `end - begin`.

### Ví dụ Java 17+ độc lập

Tạo tệp `NumberFieldPositionDemo.java`:

```java
import java.text.FieldPosition;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberFieldPositionDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        FieldPosition integerPosition =
                new FieldPosition(NumberFormat.Field.INTEGER);
        StringBuffer integerBuffer = new StringBuffer();

        formatter.format(1234567.89, integerBuffer, integerPosition);
        System.out.println("text=" + integerBuffer);
        System.out.printf(
                "integer=[%d,%d) value=%s%n",
                integerPosition.getBeginIndex(),
                integerPosition.getEndIndex(),
                integerBuffer.substring(
                        integerPosition.getBeginIndex(),
                        integerPosition.getEndIndex()));

        FieldPosition fractionPosition =
                new FieldPosition(NumberFormat.Field.FRACTION);
        StringBuffer fractionBuffer = new StringBuffer();

        formatter.format(1234567.89, fractionBuffer, fractionPosition);
        System.out.printf(
                "fraction=[%d,%d) value=%s%n",
                fractionPosition.getBeginIndex(),
                fractionPosition.getEndIndex(),
                fractionBuffer.substring(
                        fractionPosition.getBeginIndex(),
                        fractionPosition.getEndIndex()));
    }
}
```

Biên dịch và chạy:

```bash
javac NumberFieldPositionDemo.java
java NumberFieldPositionDemo
```

Kết quả được kiểm chứng với JDK:

```text
text=1,234,567.89
integer=[0,9) value=1,234,567
fraction=[10,12) value=89
```

`FieldPosition` không tạo chuỗi kết quả mới; chuỗi được append vào chính `StringBuffer` đã truyền. Vì vậy, muốn định vị thêm một trường, ta tạo một `FieldPosition` khác và gọi format lần nữa. Một lời gọi chỉ cập nhật vị trí của **trường được yêu cầu**.

## 4. Ý nghĩa của chỉ số khi StringBuffer đã có tiền tố

Một lỗi phổ biến là tưởng `beginIndex` luôn bắt đầu đếm tại phần số mới được nối vào. Thực tế, nó là **chỉ số trong StringBuffer kết quả đầy đủ**, bao gồm phần đã có trước khi format.

Ví dụ:

```java
StringBuffer buffer = new StringBuffer("PRE:");
FieldPosition position =
        new FieldPosition(NumberFormat.Field.INTEGER);
formatter.format(1234567.89, buffer, position);
```

Đoạn này giả định biến `formatter` được tạo và cấu hình như ví dụ trước. Sau khi chạy:

```text
buffer  = PRE:1,234,567.89
integer = [4,13)
```

Bốn ký tự `PRE:` đã chiếm các vị trí `0` đến `3`. Phần nguyên bắt đầu tại `4`. Nếu một ứng dụng xây dựng thông báo dài dần và muốn tô màu phần nguyên của số, nên sử dụng trực tiếp chỉ số do `FieldPosition` trả về, **không tự trừ/đoán độ dài tiền tố**.

Lưu ý có hai cách phân biệt `FieldPosition` qua các overload constructor:

- `new FieldPosition(NumberFormat.Field.INTEGER)`: dùng đối tượng thuộc tính được định nghĩa trong `NumberFormat.Field`.
- `new FieldPosition(NumberFormat.INTEGER_FIELD)` hoặc `new FieldPosition(NumberFormat.FRACTION_FIELD)`: cách dùng dựa trên hằng `int` lịch sử.

Với mã mới, nên dùng `NumberFormat.Field` vì rõ ngữ nghĩa và bao quát nhiều trường hơn. Không đánh đồng `NumberFormat.INTEGER_FIELD` (int field ID) với `NumberFormat.Field.INTEGER` (đối tượng thuộc tính).

## 5. Những giới hạn của FieldPosition

### Một đối tượng FieldPosition theo dõi một loại trường

`FieldPosition` không trả toàn bộ các trường trong cùng một lần định dạng. Nếu bạn muốn phần nguyên, phần thập phân, dấu âm và từng dấu phân nhóm, phải thực hiện các lần format cần thiết hoặc chuyển sang `AttributedCharacterIterator`.

### Trường xuất hiện nhiều lần: chỉ một vị trí được ghi nhận

Ví dụ `1,234,567.89` có **hai** dấu `,`. Với:

```java
FieldPosition grouping =
        new FieldPosition(NumberFormat.Field.GROUPING_SEPARATOR);
StringBuffer output = new StringBuffer();
formatter.format(1234567.89, output, grouping);
```

`FieldPosition` được thiết kế cho **một** cặp vị trí, và formatter thông thường báo vị trí lần xuất hiện đầu của trường. Trên `NumberFormat` của Java 17+ với `Locale.US`, kết quả cho dấu nhóm là `[1,2)`; nó **không trả danh sách** `[1,2)` và `[5,6)`. Đây là lý do dùng iterator khi cần các vị trí lặp.

### Trường không xuất hiện

Ví dụ nếu format số thường không có ký hiệu tiền tệ, hỏi `NumberFormat.Field.CURRENCY` có thể cho `beginIndex=0` và `endIndex=0`. Trong thực tế đó là tín hiệu “không tìm thấy trường” theo cách xử lý thông dụng, không phải vùng văn bản hữu ích.

Đừng gọi `substring(begin, end)` rồi kết luận mọi trường rỗng đều hợp lệ. Với các trường thực tế mong muốn có ký tự, hãy kiểm tra `end > begin` trước khi tô màu. Nếu cần biết chắc thuộc tính có mặt, sử dụng `AttributedCharacterIterator` để kiểm tra attribute tương ứng.

### Cẩn thận khi tái sử dụng

`FieldPosition` là đối tượng mutable vì formatter ghi chỉ số vào nó. Tạo đối tượng mới cho từng yêu cầu định vị sẽ rõ ràng hơn so với tái sử dụng giữa các lượt format. Tương tự, `StringBuffer` được append; nếu không muốn giữ kết quả cũ, hãy tạo một buffer mới.

Không chia sẻ một đối tượng `NumberFormat` mutable cho nhiều thread mà không đồng bộ hoặc chiến lược quản lý instance thích hợp; Java không bảo đảm các formatters này thread-safe.

## 6. AttributedCharacterIterator: xem toàn bộ các trường trong một lần định dạng

`NumberFormat.formatToCharacterIterator(Object)` trả về một `AttributedCharacterIterator`: nó duyệt các ký tự đã định dạng, đồng thời báo những **`AttributedCharacterIterator.Attribute`** nào gắn tại từng vùng.

```java
AttributedCharacterIterator iterator =
        formatter.formatToCharacterIterator(1234567.89);
```

Mỗi thuộc tính có thể được lấy bằng:

- `iterator.getAttribute(NumberFormat.Field.INTEGER)`: giá trị attribute tại vị trí hiện tại, hoặc `null` khi không có.
- `iterator.getAttributes()`: bản đồ các attributes tại vị trí hiện tại.
- `iterator.getRunStart(attribute)` / `iterator.getRunLimit(attribute)`: khoảng lớn nhất liên tục mà **giá trị của attribute đó không thay đổi**.
- `iterator.getRunStart()` / `iterator.getRunLimit()`: khoảng mà **toàn bộ tập attributes** không thay đổi.
- `iterator.first()`, `next()`, `setIndex(index)`, `getBeginIndex()` và `getEndIndex()`: API điều hướng ký tự.

Một *run* không nhất thiết trùng với một đơn vị ngôn ngữ; nó là một khoảng liên tục của các vị trí có cùng thuộc tính hoặc tập thuộc tính được xét.

### Tại sao getRunLimit(attribute) hữu ích?

Nếu một vùng có `INTEGER` xuyên qua dấu phân nhóm, `getRunLimit(NumberFormat.Field.INTEGER)` có thể trả một vùng lớn bao phủ toàn phần nguyên. Trong khi đó, `getRunLimit(NumberFormat.Field.GROUPING_SEPARATOR)` tách riêng từng dấu phẩy vì thuộc tính grouping chỉ hiện diện tại đúng dấu phân nhóm.

Khi cần tô màu một trường cụ thể, **lấy giới hạn theo chính thuộc tính đó**. Nếu dùng `getRunLimit()` không truyền đối số, các thay đổi của **bất kỳ thuộc tính nào** cũng khiến một run bị chia nhỏ; ví dụ phần nguyên sẽ bị cắt thêm tại dấu nhóm.

## 7. Ví dụ Java 17+ độc lập: duyệt mọi vị trí nhóm chữ số

Tạo tệp `NumberAttributedDemo.java`:

```java
import java.text.AttributedCharacterIterator;
import java.text.CharacterIterator;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberAttributedDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        AttributedCharacterIterator iterator =
                formatter.formatToCharacterIterator(1234567.89);

        StringBuilder builder = new StringBuilder();
        for (char c = iterator.first();
             c != CharacterIterator.DONE;
             c = iterator.next()) {
            builder.append(c);
        }
        String text = builder.toString();

        System.out.println("text=" + text);
        showField(iterator, text,
                NumberFormat.Field.INTEGER, "integer");
        showField(iterator, text,
                NumberFormat.Field.FRACTION, "fraction");
        showField(iterator, text,
                NumberFormat.Field.GROUPING_SEPARATOR, "grouping");
        showField(iterator, text,
                NumberFormat.Field.DECIMAL_SEPARATOR, "decimal");
    }

    private static void showField(
            AttributedCharacterIterator iterator,
            String text,
            AttributedCharacterIterator.Attribute field,
            String name) {

        for (int index = iterator.getBeginIndex();
             index < iterator.getEndIndex();) {
            iterator.setIndex(index);
            int limit = iterator.getRunLimit(field);

            if (iterator.getAttribute(field) != null) {
                System.out.printf(
                        "%s [%d,%d) = <%s>%n",
                        name, index, limit,
                        text.substring(index, limit));
            }

            index = limit;
        }
    }
}
```

Biên dịch và chạy:

```bash
javac NumberAttributedDemo.java
java NumberAttributedDemo
```

Kết quả kiểm chứng:

```text
text=1,234,567.89
integer [0,9) = <1,234,567>
fraction [10,12) = <89>
grouping [1,2) = <,>
grouping [5,6) = <,>
decimal [9,10) = <.>
```

Chương trình thực hiện các bước:

1. Dùng `formatToCharacterIterator(...)` tạo chuỗi định dạng kèm thông tin thuộc tính.
2. Duyệt từ `first()` đến `CharacterIterator.DONE` để dựng chuỗi hiển thị.
3. Với mỗi thuộc tính cần tìm, duyệt các run bằng `getRunLimit(field)`.
4. Chỉ in những run có `getAttribute(field) != null`.
5. Mỗi lần dịch `index` tới `limit` để không bỏ sót hay lặp lại đoạn ký tự.

Ví dụ dùng iterator do `NumberFormat` tạo ra, có `getBeginIndex() == 0`, nên các chỉ số có thể dùng trực tiếp với `String.substring`. Với một `AttributedCharacterIterator` tổng quát có begin index khác 0, cần điều chỉnh chỉ số khi tự sao chép nội dung sang chuỗi mới bắt đầu tại 0.

### Vì sao dấu nhóm vẫn nằm trong INTEGER?

Quan sát `integer [0,9)` bao gồm cả hai dấu phẩy, trong khi `grouping` có hai run riêng. Một ký tự có thể cùng lúc thuộc phần nguyên và là dấu nhóm. Việc dùng hai thuộc tính không mâu thuẫn; một thuộc tính diễn tả vùng **phần nguyên tổng thể**, thuộc tính kia nêu vai trò **dấu phân nhóm**.

## 8. Kết hợp thuộc tính để tạo kiểu hiển thị

Giả sử màn hình muốn:

- In phần nguyên `1,234,567` đậm.
- Tô riêng dấu nhóm `,` bằng màu khác.
- Làm phần thập phân `89` nhỏ hơn.

Nếu chỉ dùng `FieldPosition.INTEGER`, bạn biết phạm vi phần nguyên nhưng **không có danh sách các dấu nhóm**. Với `AttributedCharacterIterator`, tại từng ký tự có thể kiểm tra `iterator.getAttributes()` để quyết định nhiều lớp kiểu cùng lúc.

Tại `1,234,567.89`, ví dụ vị trí:

| Index | Ký tự | Thuộc tính chính |
|---:|---|---|
| 0 | `1` | `INTEGER` |
| 1 | `,` | `INTEGER` và `GROUPING_SEPARATOR` |
| 2–4 | `234` | `INTEGER` |
| 5 | `,` | `INTEGER` và `GROUPING_SEPARATOR` |
| 6–8 | `567` | `INTEGER` |
| 9 | `.` | `DECIMAL_SEPARATOR` |
| 10–11 | `89` | `FRACTION` |

Có thể tạo danh sách các span rồi áp dụng trong GUI, tài liệu hoặc rich-text API. Nhưng cần xác định quy tắc khi các span **chồng lên nhau**, ví dụ màu dấu phẩy được ưu tiên hơn màu của toàn phần nguyên.

Một đoạn mã minh họa kiểm tra thuộc tính trên một vị trí đã biết (đặt trong phương thức có biến `iterator` từ ví dụ trên):

```java
iterator.setIndex(1); // dấu ',' đầu tiên
boolean integer = iterator.getAttribute(
        NumberFormat.Field.INTEGER) != null;
boolean grouping = iterator.getAttribute(
        NumberFormat.Field.GROUPING_SEPARATOR) != null;
System.out.println(integer && grouping); // true
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Nó cho thấy dấu nhóm có thể mang hai thuộc tính đồng thời. Đừng thử gán kiểu vào chính iterator; nó dùng để **đọc**. Mã render nên chuyển các run/attributes thành định dạng mà thư viện UI thực tế hỗ trợ.

## 9. Thuộc tính số âm, tiền tệ và phần trăm

Ngoài `INTEGER`, `FRACTION`, `GROUPING_SEPARATOR` và `DECIMAL_SEPARATOR`, `NumberFormat.Field` còn mô tả các thành phần khác tùy kiểu formatter:

| Thuộc tính | Vai trò |
|---|---|
| `SIGN` | Dấu cộng hoặc trừ khi có trong kết quả |
| `CURRENCY` | Vùng ký hiệu/đơn vị tiền tệ khi định dạng tiền |
| `PERCENT` | Dấu phần trăm |
| `PERMILLE` | Dấu phần nghìn |
| `EXPONENT` | Chữ số của số mũ |
| `EXPONENT_SIGN` | Dấu số mũ |
| `EXPONENT_SYMBOL` | Ký hiệu đánh dấu phần số mũ |

Ví dụ:

```java
NumberFormat currency =
        NumberFormat.getCurrencyInstance(Locale.US);
String text = currency.format(-1234.5);
```

Với quy ước US điển hình, kết quả có thể giống `-$1,234.50`; vị trí dấu trừ, ký hiệu tiền và các dấu phân cách chịu ảnh hưởng của locale, bộ dữ liệu locale và cấu hình formatter. Thay vì tự tìm `"$"` bằng `indexOf` hoặc giả định luôn có dấu `-` tại index 0, hãy tìm `SIGN` và `CURRENCY` trên attributed iterator của **kết quả đã format**.

Tương tự, `NumberFormat.getPercentInstance(Locale.US)` có thể đặt dấu phần trăm tại vị trí khác so với các locale khác. Phần trăm còn có quy tắc nhân 100 khi format; thuộc tính `PERCENT` chỉ xác định vùng ký hiệu chứ không thay đổi quy tắc tính.

Với các trường **không xuất hiện** trong kết quả, iterator sẽ không có run nào chứa attribute tương ứng. Phải xử lý tình huống này bình thường thay vì truy cập phần tử đầu của một danh sách rỗng.

## 10. So sánh FieldPosition và AttributedCharacterIterator

| Tiêu chí | `FieldPosition` | `AttributedCharacterIterator` |
|---|---|---|
| API chính | `format(number, StringBuffer, position)` | `formatToCharacterIterator(number)` |
| Kết quả chính | Cặp `beginIndex/endIndex` của một trường | Chuỗi có attributes và nhiều runs |
| Số trường mỗi lượt | Một loại trường yêu cầu | Nhiều trường có thể duyệt |
| Trường lặp như grouping | Thường chỉ ghi một vị trí | Lấy được nhiều vùng |
| Thuộc tính chồng lấp | Không diễn đạt đầy đủ | Có thể đọc các thuộc tính cùng vị trí |
| Chi phí sử dụng | Đơn giản cho một span | Phức tạp hơn nhưng giàu thông tin |
| Ứng dụng | Chọn phần nguyên/phần thập phân | Tô kiểu, đánh dấu nhiều dấu phân cách, đọc rich-text |

Chọn theo nhu cầu thay vì luôn dùng cách phức tạp. Nếu chỉ cần chuỗi, `formatter.format(number)` là đủ. Nếu chỉ cần một vùng để đặt con trỏ, `FieldPosition` đơn giản. Nếu cần nhiều thành phần hoặc sự chồng lấp, dùng `AttributedCharacterIterator`.

## 11. Những điểm cần kiểm thử khi thay đổi Locale hoặc cấu hình

Kết quả như `1,234,567.89` và các offset ở trên được kiểm tra với `Locale.US`, grouping bật và hai chữ số thập phân. Không nên áp nguyên các chỉ số này lên locale khác:

- `de-DE` thường dùng dấu `.` để nhóm và `,` cho thập phân.
- `fr-FR` có thể dùng dấu cách không ngắt hoặc dấu cách hẹp để nhóm; ký tự và độ dài có thể thay đổi theo JDK/dữ liệu locale.
- Một số hệ số sử dụng ký tự chữ số khác ASCII.
- Tiền tệ có thể có dấu và ký hiệu ở trước hoặc sau phần số.
- `setMaximumFractionDigits(...)`, `setMinimumFractionDigits(...)`, `setGroupingUsed(false)` ảnh hưởng đến văn bản và sự tồn tại của các trường.

Vì vậy, **định dạng một lần theo locale thực tế rồi đọc metadata của chính kết quả đó**. Không cố tính offset từ số chữ số ban đầu hoặc cắt bằng dấu phân tách giả định.

### UTF-16 và khả năng hiển thị

Các index `beginIndex`, `endIndex` là chỉ số Java UTF-16. Ký tự ngoài BMP có thể gồm hai code units; ký tự kết hợp hoặc grapheme phức tạp có thể gồm nhiều code points. Để lấy substring trong cùng chuỗi Java, index này phù hợp. Nhưng nếu chuyển sang API giao diện dùng offset theo UTF-8 bytes, Unicode code points hay grapheme clusters, cần chuyển đổi hệ chỉ số đúng cách.

### Hành vi trên nhiều luồng

Các instance `NumberFormat` và `DecimalFormat` thường mutable và không được thiết kế để chia sẻ đồng thời giữa threads mà không đồng bộ. Khi ứng dụng cần định dạng theo người dùng/locale trên server, tạo formatter theo request hoặc dùng cơ chế quản lý thread an toàn. `FieldPosition` và iterator cũng mang trạng thái vị trí đang được đọc/ghi, nên không tái sử dụng tùy tiện giữa các tác vụ chạy đồng thời.

## 12. Lỗi thường gặp

1. **Nhầm endIndex là inclusive.** Thực tế vùng là `[begin,end)`; dùng `substring(begin,end)`, không cộng thêm 1.
2. **Nhầm chỉ số tương đối với phần vừa append.** `FieldPosition` đếm trên `StringBuffer` đầy đủ, bao gồm tiền tố sẵn có.
3. **Cho rằng INTEGER chỉ gồm chữ số.** Trong nhiều formatter, dấu grouping cũng nằm trong khoảng INTEGER và đồng thời có thuộc tính GROUPING_SEPARATOR.
4. **Dùng FieldPosition để tìm mọi dấu phẩy.** Nó không chứa danh sách các vị trí lặp; dùng attributed iterator.
5. **Dùng getRunLimit() không tham số và mong một span INTEGER duy nhất.** Run có thể bị tách bởi thay đổi ở thuộc tính khác. Dùng `getRunLimit(NumberFormat.Field.INTEGER)` khi chỉ quan tâm thuộc tính đó.
6. **Cho rằng bất kỳ attribute nào cũng hiện diện.** Nếu không có phân số, currency hoặc dấu âm, run tương ứng có thể không tồn tại.
7. **Cắt chuỗi theo index hardcode từ US.** Locale, cách nhóm số và số chữ số thập phân làm thay đổi offset.
8. **Dùng split hoặc indexOf(',') để suy ra trường.** Dấu nhóm và dấu thập phân thay đổi theo locale; metadata của formatter chính xác hơn.
9. **Bỏ qua phần đầu do dấu âm/đơn vị tiền.** Vùng INTEGER có thể bắt đầu sau dấu âm hoặc ký hiệu tiền.
10. **Tưởng FieldPosition và NumberFormat.Field là một.** `FieldPosition` mang một kết quả vị trí; `NumberFormat.Field` định danh loại trường.
11. **Tái sử dụng một StringBuffer/FieldPosition như trạng thái mới hoàn toàn.** Buffer append và position mutable; tạo mới để tránh sai offset/lẫn lượt.
12. **Quên định vị theo UTF-16.** Index Java không tự đồng nhất với byte offset hoặc grapheme index của hệ khác.

## 13. Bài tập thực hành

**Bài 1.** Cho văn bản `1,234,567.89` với index bắt đầu từ 0, đâu là vùng `FRACTION`?

Đáp án: `[10,12)`, văn bản `89`. Dấu thập phân `.` tại `[9,10)` không thuộc vùng FRACTION.

**Bài 2.** Với văn bản trên, `FieldPosition(NumberFormat.Field.INTEGER)` trả về gì?

Đáp án: `[0,9)`, tương ứng `1,234,567`; dấu nhóm nằm trong vùng này.

**Bài 3.** Vì sao `AttributedCharacterIterator` phát hiện được hai dấu phẩy còn một `FieldPosition(GROUPING_SEPARATOR)` không trả hai khoảng?

Đáp án: `FieldPosition` có một cặp begin/end; attributed iterator ghi thuộc tính theo từng vị trí và có thể duyệt nhiều run `GROUPING_SEPARATOR`.

**Bài 4.** Nếu `StringBuffer` đã có tiền tố `PRE:`, phần nguyên của `1,234,567.89` có index nào?

Đáp án: `[4,13)`, vì bốn ký tự của tiền tố nằm trước số.

**Bài 5.** Trong iterator, tại dấu `,` của chuỗi US, hai thuộc tính nào có thể cùng hiện diện?

Đáp án: `NumberFormat.Field.INTEGER` và `NumberFormat.Field.GROUPING_SEPARATOR`.

**Bài 6.** Khi đổi sang một locale có quy tắc dấu nhóm khác, có được giữ nguyên `[1,2)` và `[5,6)` không?

Đáp án: Không. Cần format bằng locale mới, sau đó đọc các run và chỉ số của kết quả mới.

## 14. Ghi nhớ

- `FieldPosition` cung cấp một vùng `[begin,end)` khi bạn **đã biết trường muốn tìm**. Nó dễ dùng với `NumberFormat.format(..., StringBuffer, FieldPosition)`.
- `AttributedCharacterIterator` cung cấp **các vùng thuộc tính trên cả chuỗi**, hỗ trợ nhiều occurrences, nhiều trường và các thuộc tính chồng lấp.
- Các vị trí được tính trên **chuỗi thực tế sau khi format**, nên phải xét `Locale`, ký hiệu số, tiền tệ và cấu hình format.
- `getRunLimit(field)` giúp duyệt đúng phạm vi của một thuộc tính; `getRunLimit()` dùng toàn bộ các thuộc tính, có thể chia span thành những đoạn nhỏ hơn.
- Khi cần render hoặc xử lý từng phần của một số đã bản địa hóa, dựa vào metadata của formatter đáng tin cậy hơn việc tự tách theo dấu `.` hoặc `,`.

**Tài liệu chính thức:** [Java SE 17 — FieldPosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/FieldPosition.html) · [Java SE 17 — AttributedCharacterIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/AttributedCharacterIterator.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — NumberFormat.Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.Field.html).
