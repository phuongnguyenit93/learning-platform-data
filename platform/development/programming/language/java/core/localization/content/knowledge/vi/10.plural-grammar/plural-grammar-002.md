# ChoiceFormat và lựa chọn thông điệp theo khoảng số

## 1. Vì sao một con số có thể làm thay đổi câu thông báo?

Khi một chương trình hiển thị số lượng tệp, thông báo tiếng Anh không nên luôn nối chuỗi `count + " files"`:

- `0` → “no files”.
- `1` → “one file”.
- `2` → “2 files”.

Một bài toán khác không liên quan số nhiều là phân hạng đơn hàng: dưới 10 điểm hiển thị “basic”, từ 10 đến dưới 20 là “silver”, từ 20 trở lên là “gold”. Cả hai đều là **lựa chọn văn bản theo một giá trị số**.

Java cung cấp `java.text.ChoiceFormat` để ánh xạ các **khoảng số** vào **chuỗi kết quả**. Lớp này thường được dùng chung với `java.text.MessageFormat` khi một nhánh cần chứa các tham số như `{0}`. Tuy nhiên, nó chỉ thực hiện **quy tắc khoảng số do lập trình viên định nghĩa**; không tự hiểu ngữ pháp số nhiều của từng ngôn ngữ.

Bài học tập trung vào cách xác định khoảng, khai báo pattern, chọn thông điệp, kết hợp `MessageFormat`, xử lý biên, định dạng và kiểm thử. Các ví dụ đều dùng Java 17+.

## 2. ChoiceFormat là gì và hoạt động theo quy tắc nào?

`ChoiceFormat` thuộc package `java.text`, là subclass của `NumberFormat`. Khi tạo một `ChoiceFormat`, ta cung cấp dãy **ngưỡng `double` tăng dần** cùng dãy **chuỗi được chọn**.

Ví dụ:

| Ngưỡng bắt đầu | Chuỗi | Giá trị số thuộc nhánh |
| --- | --- | --- |
| 0 | `"none"` | Từ 0 đến dưới 1 |
| 1 | `"one"` | Từ 1 đến trước số `double` ngay sau 1 |
| Số `double` ngay sau 1 | `"many"` | Lớn hơn 1 |

Với các ngưỡng `limit[0] < limit[1] < …`, nhánh `j` được dùng khi:

\[
\mathrm{limit}[j] \leq x < \mathrm{limit}[j+1]
\]

Nhánh cuối áp dụng từ ngưỡng cuối trở lên. Nếu giá trị nhỏ hơn ngưỡng đầu, Java vẫn dùng **nhánh đầu tiên**; nếu lớn hơn tất cả ngưỡng, Java dùng **nhánh cuối cùng**. `Double.NaN` cũng được xử lý như giá trị thấp hơn mọi ngưỡng, tức chọn nhánh đầu tiên.

Vì vậy `ChoiceFormat` không phải công cụ kiểm tra dữ liệu đầu vào: nếu nghiệp vụ chỉ chấp nhận số lượng tệp **nguyên, không âm**, hãy xác thực ràng buộc đó **trước khi format**. Nếu đưa `-3` vào quy tắc dành cho `0, 1, nhiều`, nó cũng có thể xuất nhánh “none” dù số âm là dữ liệu không hợp lệ.

Đặc biệt, `ChoiceFormat` không có factory `getInstance(locale)`. Bản thân nó **không chứa bộ quy tắc ngữ pháp theo `Locale`**. Những cụm từ “none”, “one”, “many” do bạn cung cấp, không phải bản dịch được Java tự chọn.

## 3. Tạo ChoiceFormat từ mảng ngưỡng và chuỗi

Constructor nhận hai mảng tương ứng:

```java
ChoiceFormat format = new ChoiceFormat(
        new double[] {
                0,
                1,
                ChoiceFormat.nextDouble(1)
        },
        new String[] {
                "none",
                "one",
                "many"
        }
);
```

Các phần tử có **cùng chỉ số** tạo thành một lựa chọn. Hai mảng phải có cùng số phần tử; các giới hạn phải tăng dần để việc chọn nhánh đúng. Đừng truyền mảng ngưỡng tùy ý chưa sắp xếp: kết quả có thể sai. Khi dữ liệu ngưỡng xây động, xác thực thứ tự và số lượng trước khi tạo formatter.

### Vì sao không dùng {0, 1, 2} cho câu “0 / 1 / lớn hơn 1”?

Với **số lượng nguyên, không âm**, mảng `{0, 1, 2}` là hợp lý vì các giá trị hợp lệ tiếp theo sau 1 là 2. Nhưng `ChoiceFormat` làm việc trên **double**, không giới hạn ở số nguyên. Nếu dùng `{0, 1, 2}` thì giá trị `1.5` vẫn thuộc nhánh “one”. Nếu bài toán cần quan hệ **lớn hơn 1** cho số thực, dùng:

```java
ChoiceFormat.nextDouble(1)
```

Phương thức trên trả về số `double` có thể biểu diễn **nhỏ nhất và lớn hơn 1** (tương đương `Math.nextUp(1.0)`). Do đó có thể phân biệt `x == 1` với `x > 1` mà không tự cộng một epsilon thiếu chính xác.

`ChoiceFormat.previousDouble(d)` là phương thức tương ứng để tìm số `double` ngay dưới `d`. Không dùng `nextDouble`/`previousDouble` như quy tắc làm tròn tiền tệ hoặc so sánh dữ liệu có độ chính xác thập phân: chúng phục vụ ranh giới biểu diễn số thực nhị phân.

Các phương thức đáng biết:

| API | Ý nghĩa |
| --- | --- |
| `new ChoiceFormat(double[], String[])` | Tạo formatter từ các ngưỡng và chuỗi |
| `new ChoiceFormat(String)` | Tạo formatter bằng pattern |
| `format(double)`, `format(long)` | Chọn và trả chuỗi theo số |
| `setChoices(double[], String[])` | Thay toàn bộ ngưỡng và chuỗi trên instance |
| `getLimits()`, `getFormats()` | Xem cấu hình các ngưỡng/đầu ra |
| `applyPattern(String)` | Thay cấu hình bằng pattern mới |
| `toPattern()` | Xuất pattern biểu diễn cấu hình |
| `nextDouble(double)`, `previousDouble(double)` | Xác định số `double` sát ranh giới |
| `parse(String, ParsePosition)` | Parse một chuỗi lựa chọn thành ngưỡng tương ứng, **không khôi phục giá trị số ban đầu** |

`format(long)` bên trong làm việc dựa trên `double`. Với các số nguyên `long` cực lớn vượt vùng biểu diễn nguyên chính xác của `double`, việc kiểm tra chính xác những ranh giới gần nhau có thể không đáng tin; nếu đó là dữ liệu nghiệp vụ quan trọng, hãy so sánh số nguyên/`BigDecimal` bằng logic riêng.

## 4. Viết pattern: #, < và ký hiệu |

Một cách phổ biến là khai báo:

```java
ChoiceFormat files = new ChoiceFormat(
        "0#no files|1#one file|1<many files"
);
```

Cú pháp tổng quát:

```text
ngưỡng#thông điệp|ngưỡng#thông điệp|ngưỡng<thông điệp
```

- `#`: **bao gồm ngưỡng**. `1#one file` bắt đầu áp dụng từ `1`.
- `<`: **không bao gồm ngưỡng**. `1<many files` bắt đầu áp dụng ở số `double` đầu tiên lớn hơn `1`.
- `|`: phân tách các nhánh.
- `≤` (ký tự Unicode đơn U+2264) cũng biểu thị quan hệ bao gồm ngưỡng; đó **không phải** chuỗi hai ký tự `<=`.
- Các ngưỡng được xử lý theo thứ tự tăng dần. Phần bên phải mỗi quan hệ là **chuỗi chọn**.

Áp dụng mẫu `0#no files|1#one file|1<many files` cho các giá trị:

| Giá trị | Chuỗi được chọn | Lý do |
| ---: | --- | --- |
| 0 | `no files` | Nhánh bắt đầu từ 0 |
| 0.5 | `no files` | Nằm trong khoảng `[0, 1)` |
| 1 | `one file` | Nhánh 1 bao gồm 1 |
| 1.5 | `many files` | Lớn hơn 1 |
| 2 | `many files` | Lớn hơn 1 |
| -1 | `no files` | Nhỏ hơn mọi ngưỡng nên dùng nhánh đầu |
| `Double.NaN` | `no files` | NaN được xử lý như dưới ngưỡng đầu |
| `Double.POSITIVE_INFINITY` | `many files` | Thuộc nhánh cuối |

Điều này cho thấy mẫu ba nhánh **chỉ có ý nghĩa nghiệp vụ với số lượng nguyên, không âm**; nó không phải quy tắc đảm bảo đúng ngữ pháp nếu đầu vào có số lẻ hoặc âm.

### Ví dụ phân bậc thực tế

```java
ChoiceFormat tier = new ChoiceFormat(
        "0#basic|10#silver|20#gold"
);

System.out.println(tier.format(9));  // basic
System.out.println(tier.format(10)); // silver
System.out.println(tier.format(19)); // silver
System.out.println(tier.format(20)); // gold
```

Ở đây quan hệ `#` thể hiện các ngưỡng `x >= 0`, `x >= 10`, `x >= 20`; mỗi nhánh được chọn tới trước ngưỡng kế tiếp. Số âm cũng sẽ thành `basic`, vì vậy ứng dụng phải xác định có chấp nhận đầu vào đó hay không.

### Escape ký tự đặc biệt

Trong pattern, `|`, `#`, `<` và dấu nháy đơn có ý nghĩa cú pháp. Khi muốn xuất chúng như một phần của thông điệp, dùng quy tắc **single quote** của `ChoiceFormat`; hai dấu nháy đơn liên tiếp biểu diễn một dấu nháy đơn thật.

```java
ChoiceFormat quoted = new ChoiceFormat(
        "0#'|'|1#ready"
);
System.out.println(quoted.format(0)); // |
```

Khi pattern còn được đưa qua `MessageFormat`, có **thêm** quy tắc escape cho ngoặc nhọn và dấu nháy; phải kiểm thử pattern sau mỗi tầng phân tích, nhất là bản dịch chứa apostrophe. Đừng tùy tiện nối nội dung do người dùng nhập thành một pattern.

## 5. ChoiceFormat và MessageFormat xử lý những phần khác nhau

`ChoiceFormat` chọn **chuỗi của một nhánh**. Nó không tự thay thế `{0}` hay `{1}` trong chuỗi nhánh.

Ví dụ:

```java
ChoiceFormat choice = new ChoiceFormat(
        "0#no files|1#one file|1<{0,number,integer} files"
);

System.out.println(choice.format(2));
// {0,number,integer} files
```

Dòng trên trả về **mẫu chứa tham số**. Khi kết hợp với `MessageFormat`, Java có thể phân tích lại kết quả nhánh có dấu `{` như một message pattern và định dạng tham số trong ngữ cảnh hiện tại.

Cách kết hợp rõ ràng, dễ bảo trì:

1. Tạo thông điệp khung bằng `MessageFormat`.
2. Tạo `ChoiceFormat` để lựa chọn lời văn theo số.
3. Gắn formatter vào **chỉ số đối số** tương ứng bằng `setFormatByArgumentIndex`.
4. Gọi `format(Object[])` với dữ liệu, kiểm tra cả giá trị 0, 1 và nhiều.

Cách này cho phép số lượng xuất hiện ở vị trí phù hợp trong toàn câu, thay vì nối nhiều đoạn câu cố định theo cấu trúc tiếng Anh.

## 6. Ví dụ Java 17+ chạy độc lập: thông báo theo số lượng tệp

Tạo một file UTF-8 tên **`ChoiceFormatDemo.java`**:

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceFormatDemo {
    public static void main(String[] args) {
        ChoiceFormat choices = new ChoiceFormat(
                "0#no files|1#one file|1<{0,number,integer} files"
        );

        MessageFormat message = new MessageFormat(
                "Folder contains {0}.", Locale.US
        );
        message.setFormatByArgumentIndex(0, choices);

        for (int count : new int[] {0, 1, 2, 5}) {
            if (count < 0) {
                throw new IllegalArgumentException("Negative file count");
            }
            System.out.println(count + " -> "
                    + message.format(new Object[] {count}));
        }

        System.out.println("ChoiceFormat only: "
                + choices.format(2));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ChoiceFormatDemo.java
java ChoiceFormatDemo
```

**Stdout chính xác:**

```text
0 -> Folder contains no files.
1 -> Folder contains one file.
2 -> Folder contains 2 files.
5 -> Folder contains 5 files.
ChoiceFormat only: {0,number,integer} files
```

Phân tích:

- Đối số của message là `count` ở vị trí `0`.
- `0` chọn `no files`; `1` chọn `one file`; số lớn hơn `1` chọn mẫu `{0,number,integer} files`.
- `MessageFormat` thấy nhánh được chọn chứa `{0,...}` và tiếp tục xử lý tham số `0`, tạo ra `2 files` hay `5 files`. Formatter `number,integer` định dạng theo `Locale.US` đã truyền vào `MessageFormat`.
- Gọi `choices.format(2)` trực tiếp chỉ trả về chuỗi pattern như đã chỉ rõ; không có vòng thay thế tham số của `MessageFormat`.
- Vòng lặp nhận số nguyên không âm, nên ba nhánh phản ánh đúng yêu cầu ví dụ. Dấu kiểm tra âm ở ví dụ thể hiện hợp đồng đầu vào; các giá trị lấy từ request hoặc database phải được kiểm tra ở nơi nhận dữ liệu.

Mẫu này minh họa một lựa chọn đơn giản thường gặp trong **tiếng Anh**. Với số liệu lớn, cách hiển thị nhóm chữ số phụ thuộc locale của `MessageFormat` và dữ liệu quốc tế hóa của JDK; không nên mặc định mọi locale dùng dấu phẩy như `Locale.US`.

## 7. Ví dụ thứ hai: cấu hình bằng mảng và nextDouble

Đây là một chương trình khác, độc lập với ví dụ trước. Tạo **`ChoiceBoundariesDemo.java`**:

```java
import java.text.ChoiceFormat;

public class ChoiceBoundariesDemo {
    public static void main(String[] args) {
        double[] limits = {
                0,
                1,
                ChoiceFormat.nextDouble(1)
        };
        String[] labels = {
                "none",
                "one",
                "many"
        };
        ChoiceFormat format = new ChoiceFormat(limits, labels);

        for (double value : new double[] {0, 0.5, 1, 1.5, 2}) {
            System.out.println(value + " -> " + format.format(value));
        }
        System.out.println("NaN -> " + format.format(Double.NaN));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ChoiceBoundariesDemo.java
java ChoiceBoundariesDemo
```

Kết quả:

```text
0.0 -> none
0.5 -> none
1.0 -> one
1.5 -> many
2.0 -> many
NaN -> none
```

Vì `ChoiceFormat.nextDouble(1)` là ngưỡng bắt đầu nhánh “many”, các số lớn hơn 1 được phân loại đúng về mặt khoảng **double**. Đặc biệt, `0.5` vẫn là “none”; bài toán đếm số lượng tệp phải dùng số nguyên và không âm.

Constructor dùng mảng phù hợp khi các ngưỡng/chuỗi được xây từ dữ liệu đã kiểm tra. Constructor pattern ngắn gọn khi bảng ngưỡng là hằng dễ đọc. Cả hai đều có cùng mô hình chọn theo khoảng số.

## 8. Dùng ChoiceFormat với thông điệp bản địa hóa

Giả sử một UI hỗ trợ tiếng Việt và tiếng Anh. **Không dùng chung một chuỗi pattern tiếng Anh** cho mọi ngôn ngữ rồi thay vài từ. Hãy lưu toàn bộ thông điệp trong tài nguyên theo locale, ví dụ các key:

```properties
# messages_en.properties
folder.summary=Folder contains {0}.
folder.count=0#no files|1#one file|1<{0,number,integer} files
```

```properties
# messages_vi.properties
folder.summary=Thư mục có {0}.
folder.count=0#không có tệp|1#một tệp|1<{0,number,integer} tệp
```

Sau đó, ở lớp trình bày, dùng `ResourceBundle.getBundle("messages", locale)` để lấy thông điệp đã dịch, tạo `ChoiceFormat` từ `folder.count` và gắn vào `MessageFormat` được khởi tạo bằng `folder.summary` cùng `locale`.

Ví dụ snippet (đặt trong phương thức có biến `locale` kiểu `Locale`, import `java.util.ResourceBundle`, `java.text.MessageFormat`, `java.text.ChoiceFormat`):

```java
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

ChoiceFormat countChoice =
        new ChoiceFormat(bundle.getString("folder.count"));
MessageFormat sentence = new MessageFormat(
        bundle.getString("folder.summary"), locale);
sentence.setFormatByArgumentIndex(0, countChoice);

String result = sentence.format(new Object[] {5});
```

Snippet này cần file properties nằm trên classpath và có key tương ứng. Với `Locale.forLanguageTag("vi-VN")` và tài nguyên tiếng Việt hợp lệ, `result` sẽ mang ý nghĩa “Thư mục có 5 tệp.”. Với locale tiếng Anh, nó dùng toàn câu tiếng Anh.

Đây là cách tổ chức có ích vì một bản dịch có thể đổi **thứ tự lời văn**, chứ không chỉ thay các danh từ. Tuy nhiên:

- `ChoiceFormat` không tự dịch; người dịch phải cung cấp pattern cho từng locale.
- Phải bảo toàn cú pháp đặc biệt của `ChoiceFormat` và `MessageFormat`, gồm `|`, `#`, `<`, `{0}` và dấu nháy.
- Khi có nhiều dạng plural, giới từ, giới tính hay yêu cầu ngữ pháp phức tạp, một chuỗi ba nhánh là **không đủ**.

**Quan trọng về số nhiều quốc tế:** Tiếng Anh thường có dạng số ít và số nhiều, nhưng một số ngôn ngữ có dạng ứng với `0, 1, 2, few, many, other` hoặc quy tắc dựa trên chữ số cuối, phần thập phân và ngữ cảnh. `ChoiceFormat` không tự lấy quy tắc plural theo CLDR và không bảo đảm đúng nếu áp dụng `count == 1` trên mọi ngôn ngữ. Khi cần số nhiều toàn cầu, cân nhắc ICU MessageFormat/CLDR plural rules hoặc hệ thống localization có hỗ trợ các quy tắc đó, kết hợp biên dịch viên và kiểm thử. Đừng tự xem 0/1/>1 là quy tắc cho mọi locale.

## 9. Những vấn đề về khoảng số cần kiểm thử

### 9.1. Ranh giới bao gồm và loại trừ

So sánh:

```java
new ChoiceFormat("0#low|10#high"); // 10 thuộc high
new ChoiceFormat("0#low|10<high"); // chỉ lớn hơn 10 mới thuộc high
```

Giá trị chính xác tại ngưỡng là trường hợp thường bị bỏ sót. Với `10<`, Java tìm số `double` nhỏ nhất lớn hơn 10 làm ngưỡng thực. Chọn `#` hay `<` phải xuất phát từ quy tắc nghiệp vụ (“từ 10 trở lên” hay “trên 10”), không dựa vào việc hai kết quả trông giống nhau ở một vài giá trị thử.

### 9.2. Giá trị dưới ngưỡng đầu và số đặc biệt

Nếu ngưỡng đầu là 0 thì `-5` vẫn chọn nhánh của 0; `NaN` cũng chọn nhánh đầu, còn dương vô cực chọn nhánh cuối. Điều này chỉ thể hiện **cơ chế fallback** của formatter, không chứng minh dữ liệu đầu vào hợp lệ. Trước khi format số lượng, kiểm tra số không âm và nguyên; với các điều kiện đo lường, quyết định riêng cách xử lý `NaN`/infinity.

### 9.3. Giá trị số thực và độ chính xác

`ChoiceFormat` dùng `double`. Khi cần phân loại tiền ở mức chính xác thập phân (ví dụ số tiền có phần xu), không nên xây ngưỡng dựa trên phép cộng epsilon thập phân; cân nhắc so sánh `BigDecimal.compareTo` theo nghiệp vụ rồi chọn thông điệp phù hợp. Đối với `long` rất lớn, `format(long)` nội bộ chuyển sang `double`, nên có thể không phân biệt hai số nguyên liền nhau sau giới hạn độ chính xác của double.

### 9.4. Sự thay đổi của định dạng số

Nếu một nhánh chứa `{0,number,integer}`, đầu ra cuối cùng là kết quả của `MessageFormat` và `NumberFormat` phụ thuộc locale. Nếu cần kiểm thử chuỗi chính xác, cố định `Locale` trong test và cân nhắc khác biệt dữ liệu locale giữa các phiên bản JDK. Đừng lấy giá trị được format rồi parse ngược như nguồn sự thật cho tính toán nghiệp vụ.

## 10. Parse của ChoiceFormat không khôi phục lại con số ban đầu

`ChoiceFormat` kế thừa khả năng parse, nhưng ý nghĩa của `parse` khác với parse số thông thường. Nó cố gắng khớp **chuỗi thông điệp đã được chọn** rồi trả về **ngưỡng** tương ứng, không trả về số `count` đã format lúc đầu.

Ví dụ, nếu nhiều giá trị `2, 3, 10` đều được format thành `"many"`, không có cách xác định lại số gốc chỉ từ `"many"`. Trong ví dụ có `{0,number,integer}`, parse của `ChoiceFormat` không phải cơ chế đảo ngược toàn bộ logic lồng nhau của `MessageFormat`.

`parse(String, ParsePosition)` làm việc trên nội dung text và cập nhật vị trí parse; cần kiểm tra cả giá trị trả về, `ParsePosition.getIndex()` và `getErrorIndex()` khi dùng. Không dùng kết quả parse từ nhãn đã dịch để khôi phục số lượng đơn hàng hay trạng thái nghiệp vụ. **Lưu và truyền số gốc bằng kiểu số**, chỉ format tại tầng hiển thị.

## 11. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Dùng `count + " files"` cho mọi tình huống | Câu bị sai khi count là 0/1, không tùy biến theo ngôn ngữ | Chọn thông điệp hoàn chỉnh theo ngữ cảnh |
| Cho rằng `ChoiceFormat` tự biết quy tắc số nhiều của locale | Formatter không có plural rules của CLDR | Cung cấp rule phù hợp hoặc dùng ICU/plural framework |
| Viết `1#one|2#many` và tin rằng 1.5 là many | 1.5 vẫn nhỏ hơn ngưỡng 2 | Dùng `1<` hoặc `ChoiceFormat.nextDouble(1)` nếu cần số thực |
| Dùng `10<` nhưng mong 10 đã thuộc nhánh sau | `<` loại trừ ngưỡng | Dùng `10#` cho “từ 10” |
| Chỉ kiểm thử các giá trị rất xa ngưỡng | Không phát hiện lỗi ở biên | Test ngay trước, tại và ngay sau ngưỡng |
| Gọi `ChoiceFormat.format(2)` rồi đợi `{0}` được thay | ChoiceFormat chỉ trả chuỗi nhánh | Kết hợp `MessageFormat` khi cần chèn tham số |
| Nhét thông điệp có dấu `|`, `#`, `<` vào pattern mà không escape | Parser hiểu thành cú pháp | Dùng quote thích hợp, kiểm thử pattern thật |
| Dùng số âm/NaN làm số lượng hợp lệ | Formatter vẫn cho một nhánh nhưng nghiệp vụ sai | Xác thực đầu vào trước khi format |
| Dùng kết quả `parse` như số gốc | Các nhánh có thể đại diện cho vô số giá trị | Giữ số gốc trong model, không đọc ngược text |
| Dùng một mẫu số nhiều tiếng Anh cho mọi locale | Quy tắc ngữ pháp khác nhau giữa các ngôn ngữ | Dịch thông điệp theo ngữ cảnh và dùng plural rules khi cần |
| Dùng một `MessageFormat` mutable chung rồi đổi pattern theo mọi request | Trạng thái format có thể lẫn giữa luồng | Tạo formatter theo ngữ cảnh hoặc quản lý lifecycle/thread-safety rõ ràng |
| Tin rằng format số là kết quả tính tiền | Formatter chỉ quyết định chuỗi | Tính toán bằng kiểu số/logic nghiệp vụ trước khi hiển thị |

## 12. Kiểm thử và thực hành

Với một bảng lựa chọn có ranh giới `0`, `1`, `10`, hãy kiểm tra tối thiểu các giá trị ngay trước và sau từng ngưỡng, cùng các giá trị đặc biệt nếu đầu vào cho phép. Một ma trận nhỏ:

| Nhóm ca | Giá trị ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Biên thấp | `-1`, `0`, `0.5` | Trạng thái dưới ngưỡng, số âm không bị chấp nhận sai |
| Biên đơn vị | `1`, `ChoiceFormat.nextDouble(1)`, `2` | Phân biệt “bằng 1” với “lớn hơn 1” |
| Biên phân hạng | `9.99`, `10`, `10.01` | Chính sách bao gồm/loại trừ ngưỡng |
| Số đặc biệt | `NaN`, `-Infinity`, `+Infinity` | Cách ứng dụng xác thực và phản hồi |
| Tham số lồng nhau | `0`, `1`, `2`, `5` | `MessageFormat` thay đúng `{0}` |
| Locale khác | `en-US`, `vi-VN` và những locale sản phẩm hỗ trợ | Văn bản/định dạng số phù hợp, cú pháp pattern không hỏng |
| Biến thể dịch thuật | Thông điệp có apostrophe, pipe hoặc ngoặc nhọn | Escape hoạt động và không phá bố cục |

Nếu muốn biến bài tập thành code, hãy tạo thêm một `ChoiceFormat` phân loại điểm: `0–9` “basic”, `10–19` “silver”, từ `20` “gold”; kiểm tra `9`, `10`, `19` và `20`. Sau đó thử thay `10#` bằng `10<` để thấy tại sao giới hạn bao gồm/loại trừ rất quan trọng.

## 13. Ghi nhớ

- `ChoiceFormat` chọn **chuỗi theo khoảng số `double`**, theo các ngưỡng tăng dần. Mỗi nhánh biểu diễn một khoảng nửa mở; giá trị dưới ngưỡng đầu vẫn lấy nhánh đầu.
- Pattern dùng `#` cho **bao gồm ngưỡng**, `<` cho **lớn hơn ngưỡng** và `|` để tách nhánh. `ChoiceFormat.nextDouble` hỗ trợ các ranh giới strict trên `double`.
- `ChoiceFormat` không tự chèn tham số lồng nhau; `MessageFormat` có thể xử lý chuỗi nhánh chứa `{0,number,...}` sau khi lựa chọn.
- Đây là công cụ chọn theo **ngưỡng**, không phải bộ quy tắc plural toàn cầu. Với ngữ pháp số nhiều phức tạp, dùng công cụ localization hỗ trợ plural rules theo ngôn ngữ và kiểm thử đầy đủ.
- Xác thực số đầu vào trước khi format, giữ số gốc ở tầng dữ liệu, và kiểm thử các giá trị ở sát ranh giới.

**Tài liệu chính thức:**

- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
