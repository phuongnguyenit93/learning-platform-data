# Phân biệt ký tự hiển thị, code point và đơn vị mã UTF-16

## 1. “Chuỗi có bao nhiêu ký tự?” chưa phải một câu hỏi đủ rõ

Người dùng có thể nhìn một biểu tượng và gọi nó là một ký tự. Unicode có thể biểu diễn biểu tượng đó bằng nhiều mã. Java lại có thể cần nhiều giá trị `char` để chứa các mã ấy.

Nếu bỏ qua sự khác biệt này, chương trình dễ:

- Giới hạn tên người dùng quá ngắn vì đếm sai đơn vị.
- Cắt một emoji thành hai nửa không còn hợp lệ.
- Xóa dấu của một chữ thay vì xóa cả chữ.
- Cho rằng hai chuỗi trông giống nhau phải có cùng `length()`.

Trong bài, cần phân biệt ba tầng:

```text
Cụm ký tự người dùng cảm nhận
           ↓ gồm một hoặc nhiều
       Mã Unicode (code point)
           ↓ biểu diễn bằng một hoặc hai đơn vị
       Đơn vị mã UTF-16 (code unit)
```

Đây là quan hệ biểu diễn, không phải công thức “mỗi ký tự bằng hai byte”. Một ví dụ ASCII đơn giản khiến các số đếm trùng nhau; chữ có dấu tổ hợp và emoji sẽ làm khác biệt hiện rõ.

## 2. Ba khái niệm chính

### 2.1. Ký tự hiển thị và cụm ký tự (grapheme cluster)

Trong xử lý văn bản, cụm ký tự mở rộng (extended grapheme cluster) là một đơn vị phân đoạn dùng để gần với điều người dùng cảm nhận là một ký tự. Ví dụ, một chữ cái kèm dấu tổ hợp thường được xem là một cụm.

Một cụm có thể chứa:

- Một mã Unicode, chẳng hạn chữ `A`.
- Chữ cơ sở và một hoặc nhiều dấu tổ hợp.
- Nhiều mã tạo thành một chuỗi emoji, chẳng hạn emoji gia đình hoặc cờ quốc gia.

Đây là mô hình phân đoạn văn bản. Nó không phải phép đếm các hình vẽ mà phông chữ thực sự tạo ra. Một glyph là hình dạng do hệ thống dựng chữ tạo ra; liên tự, phông chữ và công cụ hiển thị có thể khiến số glyph khác số cụm. Một cụm cũng không bảo đảm chiếm đúng một ô terminal hoặc một độ rộng cố định.

Trong bài, “ký tự hiển thị” được hiểu theo nghĩa gần với một đơn vị người dùng thao tác; khi cần tính toán cụ thể, ta nói rõ đang dùng cụm ký tự mở rộng. Unicode mô tả mô hình này trong [UAX #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/).

### 2.2. Mã Unicode (code point)

Mã Unicode là một giá trị trong không gian mã Unicode, thường viết dạng `U+XXXX`. Ví dụ:

| Cách viết | Ý nghĩa |
| --- | --- |
| `U+0041` | Chữ A |
| `U+0065` | Chữ e |
| `U+0302` | Dấu mũ tổ hợp |
| `U+0301` | Dấu sắc tổ hợp |
| `U+1EBF` | Chữ ế dựng sẵn |
| `U+1F600` | Emoji mặt cười |

Không gian mã chạy từ `U+0000` đến `U+10FFFF`. Không phải mọi giá trị trong đó đều là một chữ nhìn thấy được: còn có dấu tổ hợp, ký tự điều khiển, ký tự định dạng và vị trí chưa được gán.

Dải `U+D800` đến `U+DFFF` dành cho surrogate. Giá trị vô hướng Unicode (Unicode scalar value) là mã Unicode trừ dải surrogate này. Sự phân biệt hữu ích khi kiểm tra dữ liệu hợp lệ: một số nằm trong không gian mã không có nghĩa là nó biểu diễn một ký tự độc lập được phép mã hóa như văn bản Unicode hợp lệ.

Trong Java, dùng `int` khi cần chứa một mã Unicode bất kỳ; `char` không đủ để chứa một mã ngoài `U+FFFF`.

### 2.3. Đơn vị mã UTF-16 (code unit)

UTF-16 là một cách mã hóa Unicode. Một đơn vị mã UTF-16 có 16 bit. Kiểu `char` của Java chứa một đơn vị như vậy.

Với văn bản UTF-16 hợp lệ:

- Một giá trị vô hướng trong vùng BMP, tức dưới hoặc bằng `U+FFFF` và không thuộc dải surrogate, cần một đơn vị.
- Một giá trị ngoài BMP, từ `U+10000` đến `U+10FFFF`, cần hai đơn vị tạo thành một cặp surrogate.

Ví dụ `U+1F600` được biểu diễn bằng hai đơn vị `D83D` và `DE00`. Hai đơn vị này đi cùng nhau mới biểu diễn mã Unicode đó.

Trong các API chuỗi của Java, `String.length()` đếm đơn vị UTF-16; `charAt(i)` và chỉ số của `substring` cũng làm việc theo đơn vị ấy. Có thể đối chiếu định nghĩa tại [Character: Unicode Character Representations](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#unicode).

Điều này mô tả mô hình API, không phải cam kết mọi JDK đều lưu một `String` bằng một mảng `char[]` vật lý. Không suy ra dung lượng heap của chuỗi chỉ từ `length() * 2`.

## 3. So sánh trên dữ liệu thật

Bảng dưới giả sử cách phân đoạn cụm ký tự mở rộng thông thường cho các ví dụ đã nêu:

| Văn bản hoặc cấu tạo | Cụm ký tự | Mã Unicode | Đơn vị UTF-16 |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `ế` dựng sẵn: U+1EBF | 1 | 1 | 1 |
| `ế` dạng e + dấu mũ + dấu sắc | 1 | 3 | 3 |
| `😀`: U+1F600 | 1 | 1 | 2 |
| `🇻🇳`: hai mã chỉ báo vùng | 1 | 2 | 4 |
| `👩‍👩‍👧‍👦`: bốn người nối bằng ZWJ | 1 | 7 | 11 |

Ở dòng cuối, bốn mã biểu diễn người cần tổng cộng tám đơn vị UTF-16. Ba mã ZWJ, tức ký tự nối không độ rộng U+200D, cần thêm ba đơn vị. Kết quả là 7 mã Unicode và 11 đơn vị UTF-16, dù chuỗi thường được hiển thị như một emoji gia đình.

Nếu môi trường không có phông chữ phù hợp, emoji có thể hiện thành nhiều hình hoặc ô vuông. Dữ liệu mã Unicode không vì thế thay đổi; khả năng hiển thị và cấu tạo văn bản là hai vấn đề riêng.

## 4. Chương trình đo cả ba tầng

Java có thể đếm các đơn vị UTF-16 và mã Unicode trực tiếp. Với cụm ký tự, biểu thức chính quy `\X` khớp một cụm ký tự mở rộng; trong chuỗi nguồn Java phải viết `"\\X"`.

Lưu chương trình sau thành `UnicodeLayersDemo.java`:

```java
import java.util.regex.Pattern;

public class UnicodeLayersDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void show(String name, String text) {
        int units = text.length();
        int points = text.codePointCount(0, text.length());
        long clusters = GRAPHEME.matcher(text).results().count();

        System.out.println(name
                + ": units=" + units
                + ", codePoints=" + points
                + ", clusters=" + clusters);
    }

    public static void main(String[] args) {
        show("ASCII", "A");
        show("Vietnamese-precomposed", "\u1EBF");
        show("Vietnamese-decomposed", "e\u0302\u0301");
        show("Smile", "\uD83D\uDE00");
        show("Vietnam-flag", "\uD83C\uDDFB\uD83C\uDDF3");
        show("Family",
                "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                + "\uD83D\uDC67\u200D\uD83D\uDC66");
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 UnicodeLayersDemo.java
java UnicodeLayersDemo
```

Stdout:

```text
ASCII: units=1, codePoints=1, clusters=1
Vietnamese-precomposed: units=1, codePoints=1, clusters=1
Vietnamese-decomposed: units=3, codePoints=3, clusters=1
Smile: units=2, codePoints=1, clusters=1
Vietnam-flag: units=4, codePoints=2, clusters=1
Family: units=11, codePoints=7, clusters=1
```

Các chuỗi dùng escape Unicode để mã nguồn và đầu ra kiểm chứng không phụ thuộc việc terminal có hiển thị emoji đẹp hay không.

Hàm `codePointCount(0, text.length())` nhận ranh giới theo UTF-16 nhưng trả số mã Unicode trong khoảng đó. Đơn vị của tham số và đơn vị của kết quả không giống nhau.

Ký hiệu `\X` được mô tả trong [Pattern: Unicode Extended Grapheme matcher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html). Quy tắc phân đoạn và dữ liệu Unicode của thư viện phụ thuộc phiên bản JDK; không mặc định một JDK cũ đã biết mọi chuỗi emoji mới của Unicode mới nhất. Các ví dụ ở đây dùng những chuỗi đã được hỗ trợ trên các JDK nêu trên.

## 5. Một chỉ số Java không phải “ký tự thứ mấy người dùng thấy”

Xét văn bản gồm `A`, emoji U+1F600 và `B`. Cấu tạo UTF-16:

```text
Chỉ số:           0       1       2       3
Đơn vị UTF-16:  0041    D83D    DE00    0042
Mã Unicode:    U+0041   [ U+1F600 ]    U+0042
```

Chỉ số 1 trỏ tới phần cao của cặp surrogate. Chỉ số 2 trỏ tới phần thấp. Không có một `char` riêng lẻ nào chứa toàn bộ U+1F600.

Chương trình sau cho thấy sự khác biệt giữa duyệt đơn vị UTF-16 và duyệt mã Unicode. Lưu thành `UnicodeIndexDemo.java`:

```java
public class UnicodeIndexDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("unit[%d]=%04X%n",
                    i, (int) text.charAt(i));
        }

        for (int i = 0; i < text.length();) {
            int point = text.codePointAt(i);
            System.out.printf("point@%d=U+%04X%n", i, point);
            i += Character.charCount(point);
        }

        String half = text.substring(1, 2);
        System.out.println("halfUnits=" + half.length());
        System.out.println("halfIsHighSurrogate="
                + Character.isHighSurrogate(half.charAt(0)));

        int start = text.offsetByCodePoints(0, 1);
        int end = text.offsetByCodePoints(start, 1);
        String whole = text.substring(start, end);
        System.out.println("wholeUnits=" + whole.length());
        System.out.println("wholeCodePoints="
                + whole.codePointCount(0, whole.length()));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 UnicodeIndexDemo.java
java UnicodeIndexDemo
```

Stdout:

```text
unit[0]=0041
unit[1]=D83D
unit[2]=DE00
unit[3]=0042
point@0=U+0041
point@1=U+1F600
point@3=U+0042
halfUnits=1
halfIsHighSurrogate=true
wholeUnits=2
wholeCodePoints=1
```

Ở vòng lặp thứ hai, sau khi đọc U+1F600, chương trình tăng chỉ số thêm 2 nhờ `Character.charCount(point)`, nên lần đọc kế tiếp ở vị trí 3. Tăng `i++` sau mỗi lần `codePointAt(i)` sẽ đọc lại phần thấp của cặp thay vì chuyển tới mã kế tiếp.

`substring(1, 2)` không ném lỗi vì phạm vi chỉ số hợp lệ, nhưng kết quả chỉ chứa một phần của cặp surrogate. Java cho phép một `String` chứa surrogate không ghép cặp; “lệnh chạy được” không đồng nghĩa với “đã giữ nguyên văn bản Unicode hợp lệ”.

`offsetByCodePoints` giúp đổi số bước theo mã Unicode thành một chỉ số UTF-16 trước khi lấy đoạn. Nó giúp giữ trọn mã ngoài BMP, nhưng chưa giải quyết việc giữ trọn cụm ký tự: một cụm vẫn có thể gồm nhiều mã.

## 6. Cắt theo mã Unicode vẫn có thể tách một chữ

Với chuỗi `"e\u0302\u0301"`, cả ba đơn vị đều là các mã trong BMP:

```text
U+0065  +  U+0302  +  U+0301
   e       dấu mũ     dấu sắc
```

Lấy một mã đầu tiên chỉ được `e`. Chuỗi kết quả không có surrogate hỏng, nhưng người dùng đã mất hai dấu của chữ `ế`.

Tương tự, lấy một mã trong cờ quốc gia có thể chỉ còn một chỉ báo vùng. Lấy một phần của emoji gia đình có thể làm thay đổi biểu tượng được dựng. Vì thế:

- Muốn tránh cắt giữa cặp surrogate: chọn ranh giới mã Unicode.
- Muốn giữ cả đơn vị người dùng cảm nhận: chọn ranh giới cụm ký tự.
- Muốn giới hạn độ rộng một dòng: cần thêm quy tắc về phông chữ, môi trường dựng và cách đo độ rộng.

Ba yêu cầu này liên quan nhau nhưng không thay thế cho nhau.

Một hàm lấy cụm đầu tiên có thể viết như đoạn minh họa bên trong một lớp:

```java
private static String firstCluster(String text) {
    var matcher = Pattern.compile("\\X").matcher(text);
    return matcher.find() ? matcher.group() : "";
}
```

Đoạn này giả sử `text` khác `null` và lớp đã import `java.util.regex.Pattern`. Với nơi gọi lặp lại nhiều lần, có thể biên dịch `Pattern` một lần để dùng lại. Ví dụ chỉ minh họa cách lấy theo ranh giới cụm, không thay thế một bộ biên tập văn bản đầy đủ.

## 7. Hai chuỗi trông giống nhau có thể có cấu tạo khác nhau

Chữ `ế` dựng sẵn U+1EBF và chuỗi `e + U+0302 + U+0301` có thể hiển thị giống nhau. Nhưng `String.equals` so sánh chuỗi đơn vị UTF-16, không suy luận ý nghĩa thị giác.

Chuẩn hóa Unicode (normalization) có thể đưa các biểu diễn tương đương chuẩn tắc về cùng một dạng. Đây là bước xử lý riêng, không tự xảy ra khi đếm hoặc gọi `equals`; Java cung cấp [Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html) cho các dạng chuẩn hóa.

Lưu chương trình minh họa thành `UnicodeFormDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class UnicodeFormDemo {
    public static void main(String[] args) {
        String composed = "\u1EBF";
        String decomposed = "e\u0302\u0301";

        System.out.println("rawEqual=" + composed.equals(decomposed));
        System.out.println("composedUnits=" + composed.length());
        System.out.println("decomposedUnits=" + decomposed.length());

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("nfcEqual=" + composed.equals(normalized));
        System.out.println("nfcUnits=" + normalized.length());

        System.out.println("composedUtf8Bytes="
                + composed.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("decomposedUtf8Bytes="
                + decomposed.getBytes(StandardCharsets.UTF_8).length);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 UnicodeFormDemo.java
java UnicodeFormDemo
```

Stdout:

```text
rawEqual=false
composedUnits=1
decomposedUnits=3
nfcEqual=true
nfcUnits=1
composedUtf8Bytes=3
decomposedUtf8Bytes=5
```

Kết quả minh họa thêm một đơn vị khác: byte sau mã hóa UTF-8. Số byte không phải `length()`, số mã Unicode hoặc số cụm ký tự.

Chuẩn hóa không phải cách biến mọi emoji thành một mã Unicode. Không dùng NFC như một công thức tổng quát “mỗi ký tự còn đúng một code point”. Việc chọn có chuẩn hóa dữ liệu hay không phải là một phần hợp đồng xử lý văn bản của ứng dụng.

## 8. Chọn đơn vị theo yêu cầu

| Yêu cầu | Đơn vị hoặc công cụ phù hợp | Điều cần làm rõ |
| --- | --- | --- |
| Truy cập API chuỗi Java theo chỉ số | Đơn vị UTF-16 | Không nhầm với vị trí hiển thị |
| Duyệt từng mã Unicode | `codePointAt` và `Character.charCount`, hoặc `codePoints()` | Dữ liệu có thể chứa surrogate không ghép cặp |
| Đếm mã Unicode | `codePointCount` | Không phải đếm cụm ký tự |
| Giới hạn “20 ký tự” người dùng nhập | Quy định theo cụm ký tự nếu đó là ý nghĩa sản phẩm | Thống nhất với phía giao diện và phiên bản phân đoạn |
| Giới hạn kích thước tải lên | Số byte sau đúng bộ mã | Ghi rõ UTF-8 hoặc bộ mã khác |
| Cắt nhãn để vừa vùng hiển thị | Đo văn bản theo môi trường dựng | Cụm ký tự không có độ rộng cố định |

Tên biến nên thể hiện đơn vị khi có nhiều cách đếm: `utf16Length`, `codePointCount`, `clusterCount`, `utf8ByteCount`. Điều này giúp người đọc không truyền nhầm một số đếm sang API yêu cầu chỉ số theo đơn vị khác.

Nếu nhận một vị trí từ hệ thống khác, hãy xác minh nó là chỉ số byte, UTF-16, mã Unicode hay cụm ký tự trước khi dùng với `substring`. Hai phía cùng nói “index” chưa đủ để bảo đảm chúng nói cùng một đơn vị.

## 9. Những kết luận sai cần loại bỏ

- **“Java char là một ký tự Unicode bất kỳ.”** `char` chứa một đơn vị UTF-16; mã ngoài BMP cần hai đơn vị.
- **“length() là số chữ nhìn thấy.”** Nó đếm đơn vị UTF-16.
- **“Đếm code point là đã đếm đúng mọi emoji.”** Một emoji có thể là nhiều mã.
- **“Mọi thứ hiển thị như một hình đều là một code point.”** Việc dựng chữ có thể ghép nhiều mã.
- **“Chuỗi không ném lỗi khi substring thì không bị cắt hỏng.”** Chỉ số hợp lệ vẫn có thể nằm giữa cặp surrogate hoặc giữa một cụm.
- **“Một char chiếm hai byte, vậy String luôn tốn đúng length()*2 byte heap.”** Mô hình đơn vị API không phải công thức đo bố trí bộ nhớ.
- **“codePointCount xác nhận chuỗi Unicode hợp lệ.”** Java vẫn đếm surrogate không ghép cặp như một phần tử trong phép đếm đó; muốn kiểm tra tính hợp lệ phải dùng kiểm tra riêng.

## 10. Tự kiểm tra

1. `"A".length()` bằng bao nhiêu? Có trùng số cụm và số mã không?
2. U+1F600 là một mã Unicode. Vì sao Java cần hai `char`?
3. Một chữ `ế` dạng `e + dấu mũ + dấu sắc` có bao nhiêu mã, đơn vị UTF-16 và cụm?
4. Với chuỗi `A + U+1F600 + B`, chỉ số UTF-16 của `B` là gì?
5. Lấy một mã đầu tiên của một cụm có dấu tổ hợp có giữ nguyên chữ không?
6. Để kiểm tra giới hạn 100 byte UTF-8, có thể dùng `length() <= 100` không?
7. Một cặp surrogate nguyên vẹn có chắc đã là toàn bộ một cụm emoji không?

Đáp án:

1. Đều bằng 1 trong ví dụ này.
2. Mã nằm ngoài BMP; UTF-16 biểu diễn nó bằng một cặp surrogate.
3. Ba mã, ba đơn vị UTF-16 và một cụm theo cách phân đoạn đã mô tả.
4. Chỉ số 3.
5. Không bảo đảm; có thể mất các dấu.
6. Không; cần mã hóa UTF-8 và xét số byte.
7. Không; cụm có thể còn mã khác như dấu biến thể, mã nối hoặc thành phần emoji khác.

Trước khi đếm, cắt hoặc giới hạn văn bản, hãy gọi tên đơn vị cần xử lý. Phân biệt đúng ba tầng giúp lựa chọn API Java phù hợp và giữ nguyên ý nghĩa văn bản của người dùng.
