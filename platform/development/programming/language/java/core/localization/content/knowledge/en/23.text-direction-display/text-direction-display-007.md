# Nhận diện vai trò NumericShaper và cơ chế nhập văn bản của Java SE

## 1. Bài toán: chữ số được hiển thị ra sao và người dùng nhập chữ như thế nào?

Ứng dụng Java hỗ trợ nhiều ngôn ngữ thường phải xử lý ít nhất ba việc khác nhau:

1. **Giá trị và biểu diễn số:** một giá trị như `123` phải được định dạng theo `Locale`, chẳng hạn dấu thập phân, dấu nhóm hàng nghìn và chữ số của hệ chữ được yêu cầu.
2. **Hiển thị chữ số trong dòng văn bản đa hệ chữ:** khi văn bản chứa chữ Latin và chữ Arabic, ứng dụng có thể cần thể hiện các chữ số ASCII `0–9` bằng các ký tự chữ số phù hợp với đoạn chữ xung quanh.
3. **Nhập văn bản từ bàn phím/bộ gõ (input method):** người dùng có thể gõ tiếng Việt có dấu, tiếng Nhật, tiếng Trung hoặc hệ chữ khác qua quá trình soạn thảo chưa chốt (*composition/preedit*), rồi mới xác nhận chuỗi vào ô nhập.

Java SE cung cấp những API có trách nhiệm riêng:

- `java.awt.font.NumericShaper`: **biến đổi chữ số ASCII** thành ký tự chữ số của hệ chữ được chọn, có thể theo ngữ cảnh.
- `java.awt.font.TextAttribute.NUMERIC_SHAPING`: gắn cách xử lý chữ số cho **văn bản có thuộc tính** trong các pipeline trình bày AWT/Java 2D.
- `java.awt.im.InputContext`, `java.awt.event.InputMethodEvent`, `java.awt.event.InputMethodListener` và các API liên quan: giúp cơ chế nhập văn bản phối hợp với thành phần giao diện AWT/Swing.
- `java.text.NumberFormat` và `DecimalFormat`: dùng khi **định dạng giá trị số theo locale**, không nên thay bằng `NumericShaper`.

**Điểm cốt lõi:** `NumericShaper` không phải bộ gõ và không tự định dạng tiền tệ; input method không phải một phép chuyển chữ số. Chúng có thể cùng xuất hiện trong một ứng dụng đa ngôn ngữ, nhưng hoạt động ở **những tầng khác nhau**.

## 2. Phân biệt dữ liệu số, văn bản và glyph

Giả sử ta có giá trị số nguyên:

```java
int count = 123;
```

Đây là **giá trị số**, không chứa ký tự `'1'`, `'2'`, `'3'`. Khi chuyển thành văn bản:

```java
String text = Integer.toString(count); // "123"
```

ta mới có các ký tự Unicode `U+0031 U+0032 U+0033`, tức chữ số ASCII/European. Nếu yêu cầu trình bày bằng chữ số Arabic-Indic, kết quả văn bản có thể dùng `U+0661 U+0662 U+0663`.

Cần phân biệt:

| Tầng | Đối tượng thường gặp | Trách nhiệm |
|---|---|---|
| Giá trị | `int`, `long`, `BigDecimal` | Phép tính, độ chính xác và quy tắc nghiệp vụ |
| Văn bản | `String`, `char[]` | Các code points/chữ số được lưu hoặc truyền |
| Shaping chữ số | `NumericShaper` | Chuyển `0–9` ASCII sang bộ chữ số đích |
| Định dạng locale | `NumberFormat` / `DecimalFormat` | Dấu nhóm, dấu thập phân, ký hiệu tiền, độ chính xác |
| Layout/bidi | Java 2D text layout, `Bidi` | Sắp đặt và biểu diễn dòng văn bản có hướng chữ |
| Nhập liệu | AWT/Swing input method framework | Tạo, sửa và xác nhận nội dung đang nhập |

**Shaping không thay giá trị số học**: `123` vẫn là số 123. Nhưng khi `NumericShaper.shape(...)` chạy trên `char[]`, nó **thay đổi mã ký tự văn bản trong mảng**, không chỉ đổi font hoặc hình dáng glyph. Một chuỗi `String` được dựng lại từ mảng đó sẽ chứa những chữ số Unicode khác.

Một tầng render có thể dùng thuộc tính shaping để điều khiển trình bày mà không bắt buộc bạn phải lưu bản văn bản đã biến đổi; đó là lý do cần phân biệt shaping trực tiếp trên mảng với shaping trong text-layout.

## 3. NumericShaper là gì?

`java.awt.font.NumericShaper` là lớp hỗ trợ thay các chữ số European/ASCII `'0'` đến `'9'` bằng chữ số tương ứng của một hệ chữ khác. Nó có hai chế độ chủ đạo:

- **Non-contextual shaping:** luôn chuyển các chữ số được gặp sang một hệ chữ đích cố định.
- **Contextual shaping:** chọn hệ chữ số dựa trên **ngữ cảnh văn bản** và các nhóm hệ chữ được cho phép.

Các factory hiện đại dễ đọc sử dụng enum `NumericShaper.Range`:

```java
NumericShaper fixed =
        NumericShaper.getShaper(NumericShaper.Range.ARABIC);

NumericShaper contextual =
        NumericShaper.getContextualShaper(
                EnumSet.of(
                        NumericShaper.Range.EUROPEAN,
                        NumericShaper.Range.ARABIC));
```

Đây là **đoạn mã minh họa**, cần import `java.awt.font.NumericShaper` và `java.util.EnumSet`. Các chương trình độc lập nằm ở mục sau.

Một số hệ chữ số được API hỗ trợ qua `Range`, ví dụ `ARABIC`, `EASTERN_ARABIC`, `DEVANAGARI`, `THAI`, `BENGALI` và các range khác. Không nên suy ra tất cả ngôn ngữ hay mọi numbering system Unicode đều có cùng mapping hoặc một quy tắc shaping duy nhất.

Java vẫn có API lịch sử dùng các bit mask `NumericShaper.ARABIC`, `NumericShaper.EUROPEAN` và các overload nhận `int`. Khi viết code mới, enum `NumericShaper.Range` và `Set<Range>` thường dễ đọc và tránh việc thao tác bit mask sai. Các API cũ vẫn có thể cần thiết khi duy trì ứng dụng kế thừa.

## 4. Non-contextual shaping: chuyển tất cả chữ số ASCII sang một bộ chữ số

Ví dụ:

```java
char[] characters = "Order 1203".toCharArray();

NumericShaper.getShaper(
        NumericShaper.Range.ARABIC)
        .shape(characters, 0, characters.length);
```

Trong mảng sau khi shaping, phần `1203` trở thành các code points:

```text
U+0661 U+0662 U+0660 U+0663
```

`U+0660` là Arabic-Indic digit zero, `U+0661` là digit one... Bộ chữ số đã đổi, nhưng **phần chữ `Order` không phải đối tượng của phép chuyển này**.

Phương thức `shape(char[] text, int start, int count)` thực hiện chuyển đổi **tại chỗ (in place)** trên một vùng của mảng:

- `text` là mảng ký tự có thể sửa.
- `start` là chỉ số bắt đầu, tính theo Java `char`/UTF-16.
- `count` là **số phần tử** được xử lý, không phải chỉ số kết thúc.
- `start + count` phải nằm trong độ dài mảng.

Lỗi phổ biến là gọi `shape(chars, 5, chars.length)` khi muốn xử lý từ vị trí 5 đến cuối: `count` đúng là `chars.length - 5`, không phải `chars.length`.

### NumericShaper xử lý những gì?

- Chuyển các ký tự chữ số European `'0'–'9'` khi nằm trong phạm vi được shape.
- Không tự dịch chữ cái, dấu câu, khoảng trắng, dấu phân nhóm hay dấu thập phân.
- Không làm tròn giá trị số, không xác thực số tiền và không tự xác định `Locale` đầu vào.
- Không tự biến mọi chữ số thuộc mọi hệ chữ về ASCII, cũng không phải bộ chuyển đổi ngược tổng quát.

Nếu bạn chỉ cần định dạng **một con số** theo locale, `NumberFormat` là API phù hợp hơn; nếu bạn cần chuyển chữ số **bên trong một dòng văn bản đa hệ chữ**, `NumericShaper` có thể hữu ích.

## 5. Ví dụ Java 17+ hoàn chỉnh: non-contextual NumericShaper

Lưu file `FixedNumericShaperDemo.java`:

```java
import java.awt.font.NumericShaper;
import java.util.Locale;
import java.util.stream.Collectors;

public class FixedNumericShaperDemo {
    private static String digitCodes(char[] characters) {
        return new String(characters)
                .codePoints()
                .filter(Character::isDigit)
                .mapToObj(cp ->
                        String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        char[] arabic = "Order 1203".toCharArray();

        NumericShaper.getShaper(NumericShaper.Range.ARABIC)
                .shape(arabic, 0, arabic.length);

        char[] thai = "Total 789".toCharArray();

        NumericShaper.getShaper(NumericShaper.Range.THAI)
                .shape(thai, 0, thai.length);

        System.out.println("arabic=" + digitCodes(arabic));
        System.out.println("thai=" + digitCodes(thai));
    }
}
```

Biên dịch và chạy:

```bash
javac FixedNumericShaperDemo.java
java FixedNumericShaperDemo
```

Đầu ra đã kiểm chứng với JDK (in mã Unicode để không phụ thuộc font console):

```text
arabic=U+0661 U+0662 U+0660 U+0663
thai=U+0E57 U+0E58 U+0E59
```

Kết quả cho thấy các chữ số nguồn `1,2,0,3` và `7,8,9` đã trở thành ký tự số theo các range. Chương trình cố tình **không in glyph Arabic/Thai trực tiếp** để stdout ổn định khi terminal thiếu font hoặc không hỗ trợ hệ chữ.

`String` trong Java là immutable, nên `shape(...)` không sửa một biến `String` gốc. Quy trình khi cần văn bản mới là lấy `toCharArray()`, shape mảng, rồi tạo `new String(chars)`. Nếu muốn giữ dữ liệu ASCII gốc trong database, **không ghi đè bằng văn bản đã shape** một cách vô điều kiện.

## 6. Contextual shaping: quyết định dựa trên chữ xung quanh

Trong dòng văn bản trộn Latin và Arabic, ứng dụng đôi khi muốn:

```text
abc 123 [chữ Arabic] 456
```

Kết quả mong muốn có thể là:

- `123` đứng trong ngữ cảnh Latin vẫn là các chữ số ASCII.
- `456` sau các ký tự Arabic mạnh chuyển thành Arabic-Indic digits.

Lúc này dùng `getContextualShaper(...)`. Contextual shaper xem xét bối cảnh chữ và các range được phép, thay vì ép toàn bộ chữ số về một range cố định.

```java
NumericShaper contextual =
        NumericShaper.getContextualShaper(
                EnumSet.of(
                        NumericShaper.Range.EUROPEAN,
                        NumericShaper.Range.ARABIC));
```

`Range.EUROPEAN` đại diện bộ chữ số European `0–9`; `Range.ARABIC` cung cấp Arabic-Indic digits. Các ký tự có hướng chữ mạnh (*strong directional characters*) có thể ảnh hưởng ngữ cảnh của những chữ số tiếp theo. Đây là một cơ chế quy tắc cụ thể, không phải mô hình ngôn ngữ hiểu nội dung văn bản.

API còn có các overload để chọn **ngữ cảnh bắt đầu**. Việc định nghĩa initial context là quan trọng nếu đoạn văn được shape từ giữa một dòng dài: chữ số trước khi có ký tự chữ mạnh có thể phụ thuộc ngữ cảnh ban đầu.

### Ví dụ Java 17+ độc lập

Lưu `ContextualNumericShaperDemo.java`:

```java
import java.awt.font.NumericShaper;
import java.util.EnumSet;
import java.util.Locale;
import java.util.stream.Collectors;

public class ContextualNumericShaperDemo {
    private static String digitCodes(String text) {
        return text.codePoints()
                .filter(Character::isDigit)
                .mapToObj(cp ->
                        String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String input =
                "abc 123 \u0627\u0644\u0639\u0631\u0628\u064A\u0629 456";

        char[] characters = input.toCharArray();

        NumericShaper shaper =
                NumericShaper.getContextualShaper(
                        EnumSet.of(
                                NumericShaper.Range.EUROPEAN,
                                NumericShaper.Range.ARABIC));

        shaper.shape(characters, 0, characters.length);

        System.out.println(
                "digits=" + digitCodes(new String(characters)));
    }
}
```

Biên dịch/chạy:

```bash
javac ContextualNumericShaperDemo.java
java ContextualNumericShaperDemo
```

Kết quả đã kiểm chứng:

```text
digits=U+0031 U+0032 U+0033 U+0664 U+0665 U+0666
```

Ba chữ số đầu vẫn là ASCII `1,2,3`; ba chữ số sau ký tự Arabic thuộc range Arabic-Indic. Kết quả đến từ **quy tắc ngữ cảnh của shaper**, không phải do một bộ gõ Arabic hay `Locale.getDefault()` tự tác động.

**Không đồng nhất contextual shaping với tự động phát hiện ngôn ngữ.** Nó không nhận ra mục đích ngữ nghĩa của số hoặc quốc gia người viết, mà dựa vào các range và bối cảnh ký tự. Một văn bản đa ngôn ngữ phức tạp cần test bằng dữ liệu thực.

## 7. Range và legacy bit mask

Hai họ factory khác nhau nên được đọc chính xác:

| API | Đầu vào | Gợi ý |
|---|---|---|
| `NumericShaper.getShaper(Range)` | Một `NumericShaper.Range` | Non-contextual, dễ hiểu |
| `NumericShaper.getContextualShaper(Set<Range>)` | Tập range | Contextual, kiểu an toàn hơn |
| `NumericShaper.getContextualShaper(Set<Range>, Range)` | Tập range và ngữ cảnh mặc định | Contextual với initial context rõ ràng |
| `NumericShaper.getShaper(int)` | Một bit mask legacy | Mã kế thừa |
| `NumericShaper.getContextualShaper(int)` | Mask các range legacy | Mã kế thừa |

Ví dụ legacy:

```java
NumericShaper oldStyle =
        NumericShaper.getContextualShaper(
                NumericShaper.EUROPEAN | NumericShaper.ARABIC);
```

Đây là mảnh mã minh họa. Không được nhầm `NumericShaper.Range.ARABIC` với hằng `NumericShaper.ARABIC`: cái trước là **enum**, cái sau là **int mask**.

Khi triển khai, dùng một cách nhất quán để tránh nhầm bit mask và enum, cũng như tránh vô tình bỏ range cần hỗ trợ. Một shaper contextual chỉ có các range bạn cho phép; không tự hỗ trợ mọi hệ chữ có mặt trong đầu vào.

## 8. TextAttribute.NUMERIC_SHAPING trong Java 2D

Numeric shaping còn có thể được dùng như một **thuộc tính định dạng văn bản** thay vì xử lý `char[]` một cách thủ công.

`java.awt.font.TextAttribute.NUMERIC_SHAPING` là khóa thuộc tính; giá trị của nó có thể là một đối tượng `NumericShaper`. Ví dụ:

```java
import java.awt.font.NumericShaper;
import java.awt.font.TextAttribute;
import java.text.AttributedString;

AttributedString attributed =
        new AttributedString("Price 123");

attributed.addAttribute(
        TextAttribute.NUMERIC_SHAPING,
        NumericShaper.getShaper(NumericShaper.Range.ARABIC));
```

Đây là **mảnh mã Java minh họa**. `AttributedString` cung cấp iterator có các thuộc tính để pipeline trình bày của Java 2D có thể sử dụng trong các API layout thích hợp, ví dụ `TextLayout`.

Điều quan trọng:

- Tạo `AttributedString` với `NUMERIC_SHAPING` **không phải** là phép gọi `shape(char[])` và không tự sửa chuỗi nguồn.
- Thuộc tính này đưa **chỉ dẫn shaping** cho hoạt động trình bày khi API layout tôn trọng thuộc tính.
- Glyph cuối cùng còn phụ thuộc font, cơ chế layout và khả năng render của môi trường.
- Nếu bạn ghi dữ liệu ra file hoặc gửi JSON, đừng giả định renderer đã biến dữ liệu nguồn thành ký tự số của hệ chữ đích.

`TextAttribute.NUMERIC_SHAPING` có ích ở tầng hiển thị; còn nếu cần chủ động biến đổi mảng ký tự thành chữ số cụ thể, dùng `NumericShaper.shape(...)` và hiểu rằng mã Unicode trong kết quả đã đổi.

## 9. NumericShaper không phải công cụ xử lý hướng chữ RTL/LTR

Trong văn bản Arabic/Hebrew xen Latin và số, có ít nhất **ba vấn đề độc lập**:

1. **Đổi chữ số:** NumericShaper có thể biến `0–9` thành chữ số của hệ chữ được chọn.
2. **Hướng chữ và sắp xếp trực quan:** thuật toán bidirectional (Bidi) xử lý hướng phải-sang-trái/trái-sang-phải của các run ký tự.
3. **Vẽ glyph và tổ hợp chữ:** engine tạo glyph, shaping chữ nối và font render văn bản thực tế.

`NumericShaper` giải quyết việc **đổi chữ số**, không tự đưa một đoạn Arabic sang đúng thứ tự trên màn hình và không định dạng chữ nối Arabic. Java SE còn có `java.text.Bidi` cùng các khả năng text layout của AWT/Java 2D cho những vấn đề khác, nhưng việc dựng UI đúng cũng phụ thuộc component và renderer đang dùng.

Ví dụ, không nên viết:

```java
new String(chars); // sau NumericShaper
```

rồi kết luận rằng ứng dụng đã “hỗ trợ RTL hoàn chỉnh”. Nó có thể chứa chữ số Arabic-Indic, nhưng chưa có bảo đảm về thứ tự hiển thị, font, con trỏ hoặc selection.

Khi dùng Swing với thành phần văn bản, cần test hướng component, thứ tự caret, selection, ký hiệu và phản ứng khi người dùng chuyển bộ gõ, thay vì tự đảo chuỗi bằng `StringBuilder.reverse()`.

## 10. NumericShaper khác NumberFormat/DecimalFormat

Nếu bài toán là trình bày số tiền, giá, tỷ lệ hoặc số thập phân theo locale, hãy dùng `NumberFormat` hoặc `DecimalFormat`.

Ví dụ:

```java
java.text.NumberFormat formatter =
        java.text.NumberFormat.getNumberInstance(
                java.util.Locale.forLanguageTag("ar-EG"));

String shown = formatter.format(1234.5);
```

Kết quả phụ thuộc locale, numbering system và dữ liệu/provider của JDK. Formatter có trách nhiệm lựa chọn **dấu phân nhóm, dấu thập phân, số chữ số và quy tắc làm tròn** theo cấu hình. NumericShaper không có đủ những thông tin đó; nó chỉ xử lý chữ số ASCII trong vùng văn bản được shape.

So sánh:

| Yêu cầu | Lựa chọn phù hợp |
|---|---|
| Format giá trị `1234.5` theo locale | `NumberFormat` / `DecimalFormat` |
| Chuyển chữ số ASCII trong câu sang một bộ chữ số cố định | `NumericShaper.getShaper(...)` |
| Chọn chữ số dựa trên ngữ cảnh các hệ chữ trong một câu | `NumericShaper.getContextualShaper(...)` |
| Đưa chỉ dẫn shaping vào text layout | `TextAttribute.NUMERIC_SHAPING` |
| Nhận ký tự từ IME, quản lý văn bản đang soạn | AWT/Swing input method API |
| Đọc/validate số Unicode từ input | Parser và kiểm tra đầu vào theo hợp đồng |

Không lấy chuỗi đã shape rồi mặc định có thể parse bằng `Integer.parseInt` hoặc qua mọi API máy-máy. Một số parser nhận Unicode decimal digits, nhưng giao thức có thể chỉ cho phép ASCII. **Bản địa hóa hiển thị** và **định dạng trao đổi dữ liệu** cần tách biệt.

## 11. Cơ chế nhập văn bản (*input method*) của Java SE

Một bộ gõ/IME có thể biến nhiều thao tác bàn phím thành một hoặc nhiều ký tự cuối cùng. Ví dụ người dùng nhập tiếng Việt bằng một phương thức gõ dấu, hoặc nhập tiếng Nhật bằng cách gõ chuỗi Latin để chọn ký tự Kanji.

Quá trình có thể gồm:

```text
Key events / thao tác thiết bị
            |
            v
  Input Method / IME
            |
            +--> Composed text (văn bản đang soạn, chưa xác nhận)
            |
            v
   Commit / xác nhận
            |
            v
   Text component/document
```

Vì vậy, **không đồng nhất `KeyEvent` với “một ký tự đã được người dùng nhập”**. Một phím có thể chưa tạo ký tự cuối, nhiều phím có thể tạo một ký tự, hoặc người dùng có thể chọn ứng viên trong bảng của IME.

Trong Java SE, AWT input method framework phối hợp IME với các thành phần nhập văn bản; Swing text components dựa trên cơ chế này để hỗ trợ composed text và committed text.

Đây là chuyện **nhận và xác nhận nội dung**. Nó không đồng nghĩa với NumericShaper, vốn xử lý chữ số trong văn bản đã có hoặc trong pipeline hiển thị.

## 12. Các API nhập văn bản cần nhận diện

| API | Vai trò |
|---|---|
| `java.awt.im.InputContext` | Quản lý ngữ cảnh sử dụng input method, lựa chọn/điều phối input method cho component |
| `java.awt.event.InputMethodEvent` | Sự kiện thay đổi văn bản đang nhập hoặc vị trí caret |
| `java.awt.event.InputMethodListener` | Listener nhận thông báo thay đổi composed text và caret |
| `java.awt.im.InputMethodRequests` | Giao diện để input method truy vấn vị trí text/caret, vùng được chọn và nội dung đã commit theo hợp đồng |
| `java.awt.font.TextHitInfo` | Biểu diễn thông tin vị trí trong văn bản cho các sự kiện/caret |
| `java.awt.im.spi.InputMethod` | SPI cho implementation input method tích hợp với Java |
| `java.awt.im.spi.InputMethodDescriptor` | Mô tả khả năng và cách tạo input method trong SPI |
| `javax.swing.text.JTextComponent` | Nền tảng các text component Swing như `JTextField`, `JTextArea` hỗ trợ nhập/chỉnh sửa văn bản |

`InputContext` không phải chuỗi text người dùng đã nhập. `InputMethodEvent` không phải sự kiện số học và không yêu cầu NumericShaper để hoạt động. `InputMethodRequests` hỗ trợ phối hợp giữa IME và vùng hiển thị text, đặc biệt trong **inline composition**.

API input method của Java SE là một phần của môi trường desktop/AWT. Trong ứng dụng server/headless, không thể giả định có bàn phím, cửa sổ hay IME tương tác. Nếu đang xử lý HTTP input từ browser, IME thường hoạt động ở **phía client**, còn server nhận chuỗi sau khi client gửi.

## 13. Composed text và committed text: khác nhau ở đâu?

Hai trạng thái quan trọng:

- **Composed text (preedit):** chuỗi đang được người dùng soạn qua IME; có thể thay đổi, bị hủy hoặc thay bởi một ứng viên khác.
- **Committed text:** phần ký tự IME đã xác nhận và chuyển đến ứng dụng. Đây mới là phần có thể đưa vào document theo chính sách component.

`InputMethodEvent.INPUT_METHOD_TEXT_CHANGED` cho biết có thay đổi văn bản nhập; `InputMethodEvent.CARET_POSITION_CHANGED` nói về sự thay đổi vị trí caret/selection trong nội dung đang nhập.

`InputMethodEvent.getText()` trả về `AttributedCharacterIterator` của văn bản theo sự kiện, có thể chứa cả phần đã commit và phần đang compose. `getCommittedCharacterCount()` cho biết số ký tự ở đầu chuỗi sự kiện đã được commit; phần còn lại là composed text. Với một số dạng sự kiện, `getText()` có thể là `null`, nên không được truy cập nó vô điều kiện.

Ví dụ logic:

```text
Event text:       abc
Committed count:    1
Committed:        a
Composing:         bc
```

Cần xử lý đúng cả hai phần. Nếu một listener ghi **toàn bộ event text** ngay vào database hoặc document khi IME chưa commit, các ký tự tạm thời có thể bị lưu nhầm hoặc chèn lặp.

## 14. Ví dụ Java 17+ độc lập: đọc trạng thái InputMethodEvent

Ví dụ sau tạo một **sự kiện giả lập để minh họa cấu trúc API**, không khởi động IME thật và không mô phỏng đầy đủ vòng đời bộ gõ.

Lưu thành `InputMethodEventDemo.java`:

```java
import java.awt.Canvas;
import java.awt.event.InputMethodEvent;
import java.awt.font.TextHitInfo;
import java.text.AttributedCharacterIterator;
import java.text.AttributedString;
import java.text.CharacterIterator;

public class InputMethodEventDemo {
    public static void main(String[] args) {
        AttributedCharacterIterator text =
                new AttributedString("abc").getIterator();

        InputMethodEvent event = new InputMethodEvent(
                new Canvas(),
                InputMethodEvent.INPUT_METHOD_TEXT_CHANGED,
                text,
                1,
                TextHitInfo.leading(1),
                null);

        AttributedCharacterIterator iterator = event.getText();
        int begin = iterator.getBeginIndex();
        int committedEnd =
                begin + event.getCommittedCharacterCount();

        StringBuilder committed = new StringBuilder();
        StringBuilder composing = new StringBuilder();

        for (char c = iterator.first();
             c != CharacterIterator.DONE;
             c = iterator.next()) {

            if (iterator.getIndex() < committedEnd) {
                committed.append(c);
            } else {
                composing.append(c);
            }
        }

        System.out.println("committed=" + committed);
        System.out.println("composing=" + composing);
        System.out.println(
                "caret=" + event.getCaret().getInsertionIndex());
    }
}
```

Biên dịch và chạy trong môi trường Java SE có module `java.desktop`:

```bash
javac InputMethodEventDemo.java
java InputMethodEventDemo
```

Kết quả kiểm chứng:

```text
committed=a
composing=bc
caret=1
```

Cần hiểu các giới hạn của ví dụ:

1. `AttributedString("abc")` chỉ tạo văn bản ví dụ; đây **không phải nội dung thật của bộ gõ**.
2. Constructor `InputMethodEvent` nhận một `Component` nguồn, loại sự kiện, iterator, số ký tự committed và thông tin caret.
3. `TextHitInfo.leading(1)` dùng trong ví dụ để cung cấp vị trí caret.
4. Việc tách committed/composing dựa trên **số ký tự đã xác nhận**, không dựa trên cách trông giống một từ đã hoàn chỉnh.
5. Ví dụ tạo sự kiện và đọc dữ liệu; nó **không dispatch sự kiện vào JTextField** và không chứng minh người dùng đã nhập thật.

Trên JVM tối giản thiếu `java.desktop`, các lớp AWT/IME sẽ không có sẵn. Trong môi trường desktop Java SE thông thường, chương trình chỉ tạo đối tượng nền tảng và không cần mở cửa sổ.

## 15. Swing text component và hỗ trợ input method

Các `JTextComponent` chuẩn như `JTextField` và `JTextArea` đã có các cơ chế hỗ trợ editing, caret, selection và input method. Khi tạo ứng dụng Swing, nên để **thành phần văn bản** xử lý nội dung đang compose thay vì tự viết một `KeyListener` biến phím thành ký tự.

Một ví dụ giao diện độc lập, chạy được trên máy có desktop UI:

```java
import java.awt.BorderLayout;
import java.awt.event.InputMethodEvent;
import java.awt.event.InputMethodListener;
import javax.swing.JFrame;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

public class SwingInputDemo {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java input method");
            frame.setDefaultCloseOperation(
                    JFrame.EXIT_ON_CLOSE);

            JTextField field = new JTextField(28);

            field.addInputMethodListener(
                    new InputMethodListener() {
                        @Override
                        public void inputMethodTextChanged(
                                InputMethodEvent event) {

                            System.out.println(
                                    "committedCount=" +
                                    event.getCommittedCharacterCount());
                        }

                        @Override
                        public void caretPositionChanged(
                                InputMethodEvent event) {
                            // Theo dõi caret nếu ứng dụng cần.
                        }
                    });

            frame.add(field, BorderLayout.CENTER);
            frame.pack();
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
```

Chạy trong môi trường có GUI:

```bash
javac SwingInputDemo.java
java SwingInputDemo
```

**Không có một stdout cố định** cho ví dụ này: nó phụ thuộc bộ gõ, thao tác người dùng, focus và cách runtime chuyển sự kiện. Mục đích là nhận biết listener, không phải thay thế hệ thống nhập văn bản của Swing.

Lưu ý thực hành:

- Listener trong ví dụ **chỉ quan sát**, không chèn toàn bộ `event.getText()` vào `JTextField` một lần nữa.
- Không dựa vào `KeyEvent.KEY_TYPED` như nguồn duy nhất của ký tự khi có IME.
- Công việc trên Swing component nên được thực hiện trên **Event Dispatch Thread**, như `SwingUtilities.invokeLater(...)`.
- Khi ứng dụng chỉ cần lấy giá trị cuối cùng sau người dùng nhập, sử dụng API document/field và validation thích hợp; không cần tự dựng bộ xử lý composition.
- Có thể cần xem xét focus, lựa chọn vùng text và tương tác bàn phím thật trên mỗi hệ điều hành.

**Chú ý:** chạy demo này trên môi trường headless sẽ không có cửa sổ tương tác; không nên thử giải thích một lỗi headless như lỗi của `NumericShaper`.

## 16. InputContext: điều phối bộ gõ, không tự tạo ký tự

`InputContext` đại diện cho ngữ cảnh input method trong AWT. Ví dụ, một component có thể truy cập input context của nó qua cơ chế component tương ứng, và ứng dụng có thể yêu cầu lựa chọn input method theo locale.

Mảnh code minh họa:

```java
java.awt.im.InputContext context =
        component.getInputContext();

if (context != null) {
    boolean selected = context.selectInputMethod(
            java.util.Locale.JAPANESE);
    // selected cho biết yêu cầu chọn input method
    // có thành công hay không trong môi trường đang chạy.
}
```

Biến `component` phải là một `java.awt.Component` đã được tạo trong ngữ cảnh GUI thích hợp. **Không được giả định** mọi môi trường đều có IME cho `Locale.JAPANESE`; kết quả phụ thuộc platform và các input methods được cài đặt.

API có thể hỗ trợ kích hoạt/vô hiệu hóa input method, quản lý composition theo các khả năng của component và bộ gõ. Nhưng `InputContext` không tự sửa chuỗi `String` do bạn truyền, không định dạng ngày giờ và không bảo đảm có thể chọn bất kỳ locale tùy ý nào.

Đặc biệt, **Locale để định dạng giao diện** và **Locale của input method** không buộc phải giống nhau. Một người dùng có thể đang sử dụng UI tiếng Việt nhưng nhập văn bản tiếng Nhật hoặc tiếng Anh trong cùng form.

## 17. InputMethodRequests và InputMethod SPI: dành cho trường hợp nâng cao

Phần lớn ứng dụng Swing sử dụng text components có sẵn, không cần trực tiếp triển khai `InputMethodRequests` hay tự viết một input method mới.

`java.awt.im.InputMethodRequests` quan trọng khi thành phần văn bản **tự xây dựng** cần hỗ trợ inline composition và IME phải truy vấn:

- Vị trí của chữ đang soạn trên màn hình.
- Vị trí caret/selection tương ứng với tọa độ hiển thị.
- Phần văn bản đã committed.
- Một số thao tác liên quan việc chuyển lại đoạn đã commit sang chế độ sửa (*reconversion*), khi được hỗ trợ.

`java.awt.im.spi.InputMethod` cùng `InputMethodDescriptor` thuộc **Service Provider Interface** cho nhà phát triển bộ gõ/IME tích hợp với AWT input method framework, không phải API mà mỗi form bình thường phải gọi.

Nhận diện ba tầng:

```text
Ứng dụng / JTextComponent
        |
        | InputMethodEvent, InputMethodRequests
        v
AWT InputContext / cơ chế điều phối
        |
        v
Input method / IME của platform hoặc provider
```

Từng platform có thể cung cấp cách tích hợp khác nhau. Việc phát triển một input method mới phải tuân theo SPI và yêu cầu focus, event dispatch, locale, lựa chọn ngôn ngữ và lifecycle; không nên bắt đầu bằng cách chỉ implement một `KeyListener`.

## 18. Ranh giới giữa trình bày và nhập liệu

Hãy xem chuỗi tác vụ sau:

1. Người dùng dùng IME nhập văn bản chứa chữ Arabic và số.
2. Text component nhận các sự kiện composition, rồi đưa văn bản đã commit vào document.
3. Ứng dụng kiểm tra và lưu văn bản theo hợp đồng dữ liệu.
4. Khi hiển thị, text layout có thể xử lý bidi, font và numeric shaping theo ngữ cảnh.

Ở đây:

- **IME** giải quyết việc người dùng **đưa nội dung vào ứng dụng**.
- **NumericShaper** giải quyết việc **chuyển chữ số ASCII** trong văn bản hoặc trong quy trình layout.
- **Bidi/text layout** giải quyết **thứ tự và hình dạng hiển thị**.
- **Validation/parser** giải quyết dữ liệu đó **có hợp lệ hay không**.

Không có một API đơn lẻ nào thay thế toàn bộ quá trình.

Một lỗi thiết kế là áp `NumericShaper` vào mọi văn bản ngay khi người dùng còn đang compose. Nếu ứng dụng thay mã Unicode của đoạn preedit giữa chừng, IME có thể mất khả năng quản lý vị trí và nội dung dự kiến. Nếu cần shape ở UI, ưu tiên tích hợp ở **tầng render** phù hợp, và chỉ biến đổi bản lưu sau khi chính sách dữ liệu yêu cầu rõ ràng.

## 19. Vấn đề hướng chữ, con trỏ, selection và Unicode

Java `String.length()` và nhiều event/caret API sử dụng **vị trí theo UTF-16 code units**. Trong văn bản Arabic, chữ có dấu kết hợp, emoji hoặc đoạn RTL:

- Một ký tự nhìn thấy không nhất thiết là một UTF-16 `char`.
- Thứ tự ký tự trong bộ nhớ không nhất thiết là thứ tự trái-sang-phải trên màn hình.
- Caret có thể liên quan đến **text hit/affinity** ở ranh giới glyph, nhất là văn bản bidirectional.
- Composition có thể chứa các thuộc tính để phân biệt phần đang chỉnh sửa và phần đã chọn.

`TextHitInfo` đại diện cho thông tin hit/caret ở tầng văn bản, không đơn giản là một số cột tính từ bên trái. Với UI hỗ trợ RTL, cần test navigation và selection thực tế.

Nếu ứng dụng tự chuyển đổi hoặc chuẩn hóa chuỗi sau khi đã tính vị trí con trỏ, các offset có thể không còn tương ứng với văn bản mới. `NumericShaper` có mục đích đổi ký tự số tương ứng, nhưng mọi bước xử lý văn bản khác như Unicode normalization có thể làm đổi số code units. Không dùng chỉ số từ một bản text để cắt hoặc highlight bản text khác khi chưa có ánh xạ phù hợp.

## 20. Đọc chữ số sau shaping: giá trị, kiểm tra và bảo mật

Sau khi NumericShaper đổi `"123"` thành chữ số của script khác, ứng dụng cần xác định **dữ liệu nhận được phải là văn bản hiển thị hay giá trị số**.

Trong Java, `Character.digit(codePoint, 10)` có thể nhận biết giá trị số thập phân của nhiều ký tự chữ số Unicode:

```java
int digit = Character.digit('\u0662', 10);
// digit == 2
```

Nhưng từ việc nhận ra một chữ số Unicode, **không suy ra mọi parser, regex hoặc giao thức đều chấp nhận chuỗi đó**. Ví dụ giao thức định nghĩa `[0-9]+` ASCII cần được kiểm tra đúng theo grammar đó; username, mã số hợp đồng hoặc chuỗi số thẻ có thể phải có quy tắc ngăn trộn script và ký tự dễ gây nhầm.

Nếu người dùng nhập số theo locale, nên dùng một parser như `NumberFormat` với `Locale` đã xác định, đồng thời kiểm tra toàn bộ input và miền giá trị. Nếu dữ liệu là máy-máy theo chuẩn ASCII, không được chỉ vì UI cần Arabic digits mà thay đổi bytes trong payload.

Một nguyên tắc an toàn:

- **Lưu giá trị số dưới kiểu số** khi dữ liệu thực sự là số.
- **Giữ nguyên văn bản nguồn** khi nghiệp vụ cần bảo toàn nội dung người dùng.
- **Định dạng tại biên hiển thị** theo locale và chính sách text shaping.
- **Xác thực rõ ràng** khi chấp nhận Unicode digits từ nguồn không đáng tin.
- **Không dùng shaping để xóa bỏ khác biệt Unicode**, chống giả mạo tên tài khoản hoặc làm canonicalization bí mật.

Shaping không phải một trình chuẩn hóa Unicode (`Normalizer`) và không phải một bộ lọc an ninh.

## 21. Những lỗi thường gặp

**1. Cho rằng NumericShaper là bộ gõ.** Nó xử lý chữ số đã tồn tại trong văn bản; không nhận chuỗi phím và không thực hiện composition.

**2. Dùng NumericShaper để định dạng tiền tệ.** Nó không tự thêm ký hiệu tiền, dấu nhóm, dấu thập phân hay làm tròn.

**3. Nhầm `Range.ARABIC` với mask `NumericShaper.ARABIC`.** Một bên là enum, một bên là hằng int theo API cũ.

**4. Nhầm tham số `count` thành chỉ số kết thúc.** `shape(chars,start,count)` nhận số phần tử, không phải end index.

**5. Cho rằng `shape(char[])` chỉ đổi glyph.** Lời gọi này sửa trực tiếp các `char` trong mảng; khi tạo chuỗi mới thì code points đã thay đổi.

**6. Cho rằng gắn `TextAttribute.NUMERIC_SHAPING` tự sửa `String` gốc.** Nó là thuộc tính dùng cho trình bày, không phải phép biến đổi trực tiếp trên string lưu trữ.

**7. Cho rằng contextual shaper biết ngôn ngữ người dùng.** Nó dùng quy tắc ngữ cảnh chữ và tập range, không phải ngữ nghĩa hay locale UI tổng quát.

**8. Cho rằng numeric shaping tự giải quyết RTL/Bidi.** Vấn đề hướng chữ và glyph layout cần cơ chế riêng.

**9. Lưu mọi số đã shape vào giao thức máy-máy.** Có thể vi phạm hợp đồng ASCII hoặc gây parser lỗi.

**10. Dùng `KeyListener` như nguồn duy nhất cho mọi ký tự IME.** Văn bản có thể đang composition qua nhiều thao tác trước khi commit.

**11. Chèn cả composed text vào document khi chưa commit.** Có nguy cơ trùng, sai nội dung hoặc mất trạng thái bộ gõ.

**12. Dùng `InputMethodEvent.getText()` mà không kiểm tra sự kiện/`null`.** Không phải mọi sự kiện đều có văn bản.

**13. Tự implement toàn bộ IME khi JTextField đã hỗ trợ.** Nên tận dụng input method framework và text component chuẩn.

**14. Giả định mọi máy có bộ gõ cho locale yêu cầu.** Khả năng phụ thuộc hệ điều hành, input method provider và trạng thái GUI.

**15. Chia sẻ mutable editor state/iterator giữa các luồng.** UI và event dispatch có quy tắc thread; Swing phải được xử lý trên EDT.

**16. Nhầm UTF-16 index với vị trí thị giác.** Văn bản RTL và glyph phức hợp có thể có caret khác thứ tự code units.

**17. Cho rằng chữ số Unicode là dữ liệu “an toàn” vì có thể đọc bằng Character.digit.** Input validation và security policy vẫn bắt buộc.

## 22. Tình huống chọn API đúng

| Tình huống | API/chính sách phù hợp |
|---|---|
| Hiển thị giá theo `ar-EG` | `NumberFormat` theo locale |
| Đổi `123` trong chuỗi thành Arabic-Indic digits cố định | `NumericShaper.getShaper(Range.ARABIC)` |
| Trộn Latin/Arabic và chọn chữ số theo đoạn chữ | `NumericShaper.getContextualShaper(...)` |
| Gắn shaping vào trình bày văn bản có thuộc tính | `TextAttribute.NUMERIC_SHAPING` |
| TextField nhận tiếng Việt/Japanese IME | `JTextField`/`JTextComponent` và input method framework |
| Quan sát preedit và số ký tự đã xác nhận | `InputMethodListener` / `InputMethodEvent` |
| Tự xây dựng component hỗ trợ inline IME | `InputMethodRequests`, text layout và event handling |
| Tạo input method provider | `java.awt.im.spi` |
| Xử lý ký tự RTL đúng hướng | Bidi/text layout cùng khả năng component |
| Kiểm tra số đã nhập có hợp lệ | Parser/validator theo grammar/locale |

Nếu một sản phẩm vừa có form nhập liệu vừa hiển thị văn bản Arabic/Latin, **có thể cần nhiều hàng trong bảng cùng lúc**. Không nên cố biến NumericShaper thành giải pháp tổng thể của localization.

## 23. Checklist kiểm thử thực tế

- **NumericShaper cố định:** `1203` thành `U+0661 U+0662 U+0660 U+0663` khi chọn range Arabic.
- **Range khác:** thử Thai/Devanagari, kiểm tra kết quả code points độc lập font.
- **Văn bản mixed-script:** chữ số Latin đầu dòng và chữ số sau đoạn Arabic có kết quả contextual mong đợi.
- **Phạm vi mảng:** kiểm tra `start/count`; vùng ngoài phạm vi không được sửa.
- **Dữ liệu gốc:** đối chiếu string ban đầu với chuỗi dựng từ char array sau shaping; biết nơi nào thực sự thay code points.
- **TextAttribute:** kiểm tra renderer có tôn trọng `NUMERIC_SHAPING` và font có glyph.
- **Bidi:** kiểm thử thứ tự hiển thị, caret/selection giữa Arabic và Latin.
- **IME:** gõ, chọn ứng viên, commit, hủy composition; không chèn văn bản tạm thời hai lần.
- **Focus:** chuyển qua lại giữa nhiều text fields, đổi bộ gõ, chọn văn bản, undo/redo.
- **Locale:** giao diện và input locale có thể khác; không phụ thuộc default locale của server.
- **Headless:** tách logic dữ liệu không cần AWT GUI khỏi test yêu cầu desktop.
- **Security:** số Unicode từ nguồn ngoài phải đáp ứng grammar của giao thức và quy tắc chống nhầm script.
- **Accessibility:** kiểm tra font, screen reader và hiển thị ký tự số đối với người dùng thực tế.
- **Version:** nâng cấp JDK/Unicode, thay font hoặc platform IME có thể làm khác kết quả trình bày.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `NumericShaper.getShaper(Range.ARABIC)` dùng để làm gì?  
**Đáp án:** Chuyển chữ số ASCII trong vùng văn bản được shape sang bộ chữ số Arabic-Indic, không tự định dạng giá trị tiền.

**Câu 2.** `getContextualShaper(...)` khác `getShaper(...)` thế nào?  
**Đáp án:** Contextual shaper chọn range theo ngữ cảnh chữ và tập range được phép; non-contextual shaper dùng một range cố định.

**Câu 3.** `shape(chars, 4, 3)` xử lý tới index 3 hay bao nhiêu phần tử?  
**Đáp án:** Ba phần tử bắt đầu từ index 4, tức các chỉ số 4, 5 và 6 nếu mảng đủ dài.

**Câu 4.** `TextAttribute.NUMERIC_SHAPING` có tự sửa `String` được dùng để tạo `AttributedString` không?  
**Đáp án:** Không. Nó gắn hướng dẫn shaping cho pipeline trình bày thích hợp.

**Câu 5.** NumericShaper có giải quyết bidi và mọi glyph Arabic không?  
**Đáp án:** Không. Nó là phép chuyển chữ số; bidi và layout là trách nhiệm khác.

**Câu 6.** Vì sao không nên dùng một `KeyEvent` để xác định một ký tự tiếng Nhật/Việt cuối cùng?  
**Đáp án:** Input method có thể cần nhiều thao tác, đoạn preedit và bước commit; `KeyEvent` không mô tả đầy đủ vòng đời đó.

**Câu 7.** Trong `InputMethodEvent` có 1 ký tự committed và 2 ký tự composing, có nên lưu cả 3 ngay không?  
**Đáp án:** Không mặc định. Cần tôn trọng cơ chế composition, và component chuẩn thường đã xử lý việc chèn text đã commit.

**Câu 8.** Khi nào dùng `NumberFormat` thay `NumericShaper`?  
**Đáp án:** Khi đang định dạng một **giá trị số** theo locale với dấu thập phân, dấu nhóm, độ chính xác hoặc ký hiệu tiền.

**Câu 9.** Có thể chọn IME tiếng Nhật bằng `InputContext.selectInputMethod(Locale.JAPANESE)` trên mọi máy không?  
**Đáp án:** Không bảo đảm; phụ thuộc platform và bộ gõ hiện có.

**Câu 10.** Vì sao cần validate chữ số đã shape nếu gửi sang API máy-máy?  
**Đáp án:** API có thể chỉ cho phép cú pháp ASCII/canonical riêng; shaping tạo các ký tự Unicode khác.

## 25. Tổng kết

`NumericShaper` giúp **đổi ký tự số ASCII sang chữ số của hệ chữ**, bằng cách cố định một range hoặc chọn theo ngữ cảnh. `TextAttribute.NUMERIC_SHAPING` đưa vai trò đó vào tầng trình bày văn bản; `NumberFormat` mới là công cụ phù hợp để định dạng **giá trị số** theo locale.

Cơ chế nhập văn bản của Java SE lại thuộc AWT/Swing: `InputContext` điều phối input method, `InputMethodEvent` mang thông tin text đang soạn và text đã xác nhận, còn các text components xử lý caret/document/focus. Khi xây dựng ứng dụng đa ngôn ngữ, hãy **tách dữ liệu, shaping, bidi/layout, IME và validation** để mỗi tầng có hợp đồng rõ ràng.

**Tài liệu chính thức:** [Java SE 17 — NumericShaper](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/NumericShaper.html) · [TextAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextAttribute.html) · [InputContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/InputContext.html) · [InputMethodEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/event/InputMethodEvent.html) · [InputMethodListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/event/InputMethodListener.html) · [InputMethodRequests](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/InputMethodRequests.html) · [InputMethod SPI](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/spi/package-summary.html).
