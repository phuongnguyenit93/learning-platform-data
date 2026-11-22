# char không luôn biểu diễn trọn một ký tự trong Java

## 1. Vấn đề: một “ký tự” không nhất thiết là một char

Trong một chương trình Java, đoạn mã `String.valueOf('A')` chứa một chữ cái Latin và `"A".length()` bằng `1`. Vì thế, người mới học thường cho rằng:

- `char` luôn biểu diễn một ký tự hoàn chỉnh;
- `String.length()` là số ký tự mà người dùng nhìn thấy;
- `charAt(i)` luôn lấy được một ký tự Unicode;
- `substring(i, i + 1)` luôn cắt đúng một ký tự.

Những giả định này **sai khi làm việc với Unicode**. Ví dụ, biểu tượng mặt cười **😀 (U+1F600)** là **một Unicode code point** nhưng phải dùng **hai đơn vị mã UTF-16** trong chuỗi Java. Chữ hiển thị như **é** cũng có thể được biểu diễn bằng **một code point** `U+00E9` hoặc **hai code point** `U+0065 U+0301` (chữ `e` cộng dấu sắc kết hợp). Ngoài ra, emoji gia đình và một số cụm chữ được tạo bởi **nhiều code point** nhưng thường được người dùng cảm nhận như một ký tự.

Vì vậy cần tách ít nhất ba tầng:

1. **UTF-16 code unit** — đơn vị `char` 16 bit mà Java dùng để đánh chỉ số trong `String`.
2. **Unicode code point** — mã số của một phần tử Unicode, thường được xử lý bằng `int`.
3. **Extended grapheme cluster** — chuỗi code point tạo một đơn vị ký tự theo quy tắc phân đoạn văn bản Unicode, gần với điều người dùng xem là một “ký tự”.

Đây là kiến thức nền quan trọng khi duyệt chuỗi quốc tế hóa, đếm giới hạn nhập liệu, cắt tên hiển thị, xử lý emoji, so sánh nội dung tiếng Việt, xây API và lưu trữ dữ liệu.

## 2. char là 16 bit, còn Unicode có nhiều hơn 65.536 code point

`char` trong Java là **kiểu nguyên không dấu 16 bit**, có giá trị từ `0` đến `65535` (hex `U+0000` đến `U+FFFF` trong cách ký hiệu code unit). Khi làm việc với `String`, mỗi `char` là **một đơn vị mã UTF-16**, không nhất thiết là một ký tự hoàn chỉnh.

Unicode gán các **code point** trong khoảng `U+0000` đến `U+10FFFF`. Chúng được chia thành:

| Phạm vi | Tên | UTF-16 biểu diễn |
| --- | --- | --- |
| `U+0000..U+FFFF`, trừ các giá trị surrogate | Basic Multilingual Plane (BMP) | Một `char` / một code unit |
| `U+10000..U+10FFFF` | Supplementary planes | **Hai `char` / một surrogate pair** |
| `U+D800..U+DFFF` | Vùng surrogate dành riêng của UTF-16 | Không phải Unicode scalar value độc lập |

Ví dụ:

- `'A'` là một `char` và một code point `U+0041`.
- `'é'` (dạng dựng sẵn `U+00E9`) là một `char` và một code point.
- `'中'` (`U+4E2D`) là một `char` và một code point.
- Emoji `😀` (`U+1F600`) **không thể chứa trọn trong một `char`**; cần hai `char`.
- Ký tự hiển thị tạo từ `e` + dấu sắc kết hợp có thể chứa **hai code point BMP**, dù mắt người thấy một chữ.

Vì thế, câu “Unicode ký tự luôn là 16 bit” là sai. Java vẫn cung cấp `char` 16 bit vì mô hình chuỗi dựa trên các đơn vị UTF-16; API code-point-aware mới xử lý trọn các mã ngoài BMP.

**Ghi chú triển khai:** từ Java 9, `String` có thể dùng biểu diễn bộ nhớ tối ưu (compact strings), nhưng **ngữ nghĩa API** của `length()`, `charAt()`, index và `substring()` vẫn dựa trên các **đơn vị UTF-16**. Không suy luận từ cấu trúc lưu trữ nội bộ để quyết định cách đếm chuỗi.

## 3. Surrogate pair: tại sao một emoji cần hai char?

UTF-16 biểu diễn một code point ngoài BMP bằng cặp:

- **High surrogate** trong khoảng `U+D800..U+DBFF`.
- **Low surrogate** trong khoảng `U+DC00..U+DFFF`.

Hai code unit liên tiếp theo đúng thứ tự tạo nên một code point supplementary. Chẳng hạn `U+1F600` được mã hóa thành `\uD83D\uDE00` trong UTF-16.

```java
String emoji = new String(Character.toChars(0x1F600));

System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.println(Character.isHighSurrogate(emoji.charAt(0))); // true
System.out.println(Character.isLowSurrogate(emoji.charAt(1)));  // true
```

Đây là **snippet** đặt trong một phương thức. `Character.toChars(int)` trả về một `char[]` dài 1 hoặc 2 tùy code point; `new String(...)` tạo chuỗi tương ứng. `Character.isSurrogatePair(high, low)` cho biết hai code unit có tạo thành cặp surrogate theo đúng cấu trúc hay không.

Nếu gọi `emoji.charAt(0)`, bạn chỉ lấy **high surrogate**, chưa phải code point `U+1F600`. Tương tự, `emoji.substring(0, 1)` tạo một `String` chỉ chứa nửa đầu của cặp surrogate. Chuỗi đó có thể vẫn tồn tại trong Java nhưng **không còn là một chuỗi Unicode scalar values hợp lệ** nếu diễn giải độc lập.

Một **char literal** như `'A'` hoặc `'中'` là hợp lệ vì chứa một code unit. Không thể dùng một literal `char` duy nhất để giữ toàn bộ emoji ngoài BMP. Dùng `String`, `int codePoint` hoặc các API hỗ trợ code point.

## 4. length, codePointCount và số ký tự hiển thị là ba đại lượng khác nhau

Xét văn bản được ghép bằng:

- `A` — `U+0041`;
- emoji mặt cười — `U+1F600`;
- chữ `e` — `U+0065`;
- dấu sắc kết hợp — `U+0301`.

Khi hiển thị thường thấy **ba cụm ký tự**: `A`, emoji và `é`. Nhưng các phép đếm cho kết quả khác:

| Đại lượng | Kết quả | Vì sao |
| --- | ---: | --- |
| `text.length()` | **5** | `A` 1 + emoji 2 + `e` 1 + dấu kết hợp 1 code unit |
| `text.codePointCount(0, text.length())` | **4** | `A`, emoji, `e`, dấu kết hợp là bốn code point |
| Số extended grapheme clusters | **3** | `e` và dấu sắc tạo một cụm; emoji này là một cụm |
| `text.getBytes(UTF_8).length` | **8** | Byte UTF-8: `A` 1 + emoji 4 + `e` 1 + dấu kết hợp 2 |

**Không có một phương thức `String.length()` nào tự trả “số ký tự người dùng nhìn thấy”** trong mọi tình huống. `String.length()` đếm **UTF-16 code units**. `codePointCount` đếm **code points** (cặp surrogate hợp lệ tính là một), còn phân đoạn grapheme là bài toán khác.

### Bảng API cần nhớ

| API | Đơn vị xử lý | Lưu ý |
| --- | --- | --- |
| `String.length()` | UTF-16 code units | Không phải số code point hay grapheme |
| `String.charAt(index)` | Một `char` | Có thể lấy một nửa surrogate pair |
| `String.chars()` | Stream các giá trị `char` được mở rộng thành `int` | **Không** gộp surrogate pair |
| `String.codePointAt(index)` | Code point tại **UTF-16 index** | Gộp high+low surrogate hợp lệ bắt đầu ở index đó |
| `String.codePoints()` | `IntStream` các code point | Gộp cặp surrogate hợp lệ; không gộp dấu kết hợp thành grapheme |
| `String.codePointCount(begin, end)` | Số code point trong khoảng **UTF-16 index** | Index vẫn tính theo code unit |
| `String.offsetByCodePoints(index, offset)` | Tìm **UTF-16 index** dịch theo số code point | Dùng để cắt chuỗi không chẻ surrogate pair |
| `Character.toChars(codePoint)` | Chuyển code point sang một hoặc hai `char` | Hữu ích khi dựng chuỗi từ code point |
| `StringBuilder.appendCodePoint(int)` | Nối một code point | Tránh tự ghép surrogate |
| `Pattern.compile("\\X")` | Extended grapheme cluster | Phù hợp phân đoạn gần với “ký tự” hiển thị; phụ thuộc phiên bản quy tắc Unicode/JDK |

Lưu ý quan trọng: các phương thức nhận **index** của `String` vẫn dùng **UTF-16 index** ngay cả khi tên có chữ `codePoint`. Ví dụ `codePointAt(1)` đọc code point bắt đầu tại **code unit index 1**, không có nghĩa “code point có số thứ tự 1 trong danh sách code point” đối với mọi chuỗi.

## 5. Ví dụ Java 17+ chạy độc lập: thấy rõ mọi tầng đếm

Tạo tệp **`UnicodeUnitsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeUnitsDemo {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String text = "A" + emoji + "e\u0301";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: "
                + text.getBytes(StandardCharsets.UTF_8).length);

        System.out.println("charAt(1) high surrogate: "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("codePointAt(1): U+"
                + Integer.toHexString(text.codePointAt(1))
                         .toUpperCase(Locale.ROOT));
        System.out.println("Index after 2 code points: "
                + text.offsetByCodePoints(0, 2));

        System.out.println("Grapheme clusters: "
                + Pattern.compile("\\X").matcher(text)
                         .results().count());
        System.out.println("Code points list: "
                + text.codePoints()
                      .mapToObj(cp -> String.format(
                              Locale.ROOT, "U+%04X", cp))
                      .toList());
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
```

**Stdout đã kiểm tra trên JDK 24:**

```text
UTF-16 units: 5
Code points: 4
UTF-8 bytes: 8
charAt(1) high surrogate: true
codePointAt(1): U+1F600
Index after 2 code points: 3
Grapheme clusters: 3
Code points list: [U+0041, U+1F600, U+0065, U+0301]
```

Diễn giải:

1. `text.length() == 5` vì emoji chiếm hai code unit.
2. `codePointCount(...) == 4` vì emoji là một code point nhưng dấu sắc kết hợp vẫn là code point riêng.
3. `getBytes(StandardCharsets.UTF_8).length == 8` cho thấy **độ dài byte** là đại lượng thứ tư. Không được dùng `length()` để dự đoán chính xác dung lượng dữ liệu sau khi UTF-8 encode.
4. `charAt(1)` trả high surrogate, còn `codePointAt(1)` kết hợp với low surrogate tiếp theo để trả `0x1F600`.
5. `offsetByCodePoints(0, 2)` trả UTF-16 index `3`: code point thứ nhất `A` chiếm index 0, code point thứ hai là emoji chiếm index 1 và 2.
6. Regex `\\X` trong Java source tạo biểu thức regex `\X`, nghĩa là một **Unicode extended grapheme cluster**, vì thế chuỗi ví dụ có ba cụm.

Phần code cố ý in **mã Unicode và số lượng bằng ASCII** thay vì bắt terminal phải render emoji đúng glyph; điều này giúp stdout dễ kiểm tra hơn trên nhiều môi trường.

## 6. Duyệt chuỗi: khi nào dùng char, khi nào dùng code point?

### 6.1. Duyệt theo char: chỉ đúng khi cần UTF-16 units

```java
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // Một vòng tương đương một UTF-16 code unit.
}
```

Đây là snippet. Nó phù hợp cho các tác vụ ở tầng UTF-16 (định dạng buffer, một số thuật toán cấp thấp), nhưng **không phải một vòng lặp duyệt đầy đủ từng Unicode code point**. Với emoji ngoài BMP, vòng lặp nhìn thấy **hai `char`**.

Nếu dùng `Character.isLetter(text.charAt(i))` hoặc các phép phân loại `char` đơn lẻ cho dữ liệu quốc tế, những ký tự supplementary có thể bị phân tích sai. `Character` cung cấp nhiều overload nhận `int codePoint`; hãy chọn overload phù hợp với loại đơn vị bạn muốn xử lý.

### 6.2. Duyệt theo code point bằng stream

```java
text.codePoints().forEach(cp -> {
    System.out.printf("U+%04X%n", cp);
});
```

`codePoints()` gộp surrogate pair hợp lệ thành một `int`. Trong ví dụ, dòng cho emoji là `U+1F600` chứ không phải hai dòng `U+D83D` và `U+DE00`.

Khác với `codePoints()`, `text.chars()` trả một `IntStream` của **từng `char`**. Hai tên API tương đối giống nhau nhưng không thay thế được cho nhau.

### 6.3. Duyệt theo code point không tạo stream

```java
for (int i = 0; i < text.length(); ) {
    int codePoint = text.codePointAt(i);
    System.out.printf("U+%04X%n", codePoint);
    i += Character.charCount(codePoint);
}
```

Với một chuỗi **UTF-16 hợp lệ**, `charCount` trả 1 cho code point thuộc BMP và 2 cho supplementary. Nhờ vậy chỉ số nhảy qua đúng hai code unit khi gặp emoji. Không viết `i++` thay thế trong vòng lặp này: điều đó sẽ đọc lại low surrogate như một đơn vị riêng.

**Giới hạn:** một `String` trong Java *có thể chứa surrogate đứng một mình*. Theo hợp đồng `String.codePointAt`/`codePoints`, surrogate không ghép thành cặp hợp lệ vẫn có thể được trả về dưới dạng số `int` tương ứng, chứ API không tự báo lỗi hoặc thay bằng ký tự thay thế. Nếu đầu vào cần là văn bản Unicode hợp lệ cho giao thức hoặc database, hãy có bước kiểm tra/chuẩn hóa dữ liệu phù hợp và chính sách xử lý chuỗi không hợp lệ.

## 7. Cắt chuỗi an toàn: substring dùng UTF-16 index

Giả sử `String s = "A" + emoji + "B";` với emoji `U+1F600`. Chuỗi có:

```text
UTF-16 index:      0       1(high)  2(low)   3
Mã/đơn vị:         A       high      low      B
Code point index:  0       1         1       2
```

Nếu gọi `s.substring(1, 2)`, kết quả chỉ chứa **high surrogate**, gây hỏng emoji. Muốn lấy emoji phải cắt từ `1` đến `3`. Tuy nhiên không nên hardcode rằng emoji luôn chiếm hai đơn vị khi viết logic cắt chung.

### Hàm cắt theo code point index

Tạo chương trình độc lập **`CodePointSliceDemo.java`**:

```java
import java.util.Locale;

public class CodePointSliceDemo {
    static String sliceByCodePoints(String text, int from, int to) {
        int count = text.codePointCount(0, text.length());
        if (from < 0 || to < from || to > count) {
            throw new IndexOutOfBoundsException("Invalid code-point range");
        }
        int begin = text.offsetByCodePoints(0, from);
        int end = text.offsetByCodePoints(begin, to - from);
        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        String selected = sliceByCodePoints(text, 1, 2);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code-point count: "
                + text.codePointCount(0, text.length()));
        System.out.println("Selected: U+"
                + Integer.toHexString(selected.codePointAt(0))
                         .toUpperCase(Locale.ROOT));
        System.out.println("Selected UTF-16 length: "
                + selected.length());

        String broken = text.substring(1, 2);
        System.out.println("Broken half is high surrogate: "
                + Character.isHighSurrogate(broken.charAt(0)));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CodePointSliceDemo.java
java CodePointSliceDemo
```

Stdout:

```text
UTF-16 length: 4
Code-point count: 3
Selected: U+1F600
Selected UTF-16 length: 2
Broken half is high surrogate: true
```

Hàm `sliceByCodePoints` tránh chẻ đôi một surrogate pair hợp lệ vì chuyển **code point index** thành **UTF-16 index** bằng `offsetByCodePoints`. Nhưng nó **chưa đảm bảo cắt đúng grapheme cluster**: nếu chỉ lấy chữ `e` trong `e + dấu sắc` thì vẫn có thể bỏ lại dấu sắc kết hợp. Muốn cắt theo “chữ người dùng cảm nhận”, phải xử lý thêm quy tắc grapheme.

## 8. Code point vẫn chưa tương đương với một ký tự hiển thị

### 8.1. Chữ có dấu và combining marks

Có ít nhất hai cách biểu diễn hình thức chữ `é`:

- **Precomposed:** `U+00E9`, một code point `é`.
- **Decomposed:** `U+0065` `U+0301`, hai code point `e` + dấu sắc kết hợp.

Cả hai có thể render giống nhau nhưng:

```java
String precomposed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(precomposed.length()); // 1
System.out.println(decomposed.length());  // 2
System.out.println(precomposed.equals(decomposed)); // false
```

**Đây là khác biệt về chuỗi mã Unicode**, không nhất thiết là khác biệt về chữ hiển thị. Tiếng Việt có nhiều chữ chứa dấu; một số ký tự có thể tồn tại ở dạng dựng sẵn, trong khi văn bản nhập từ các nguồn khác nhau có thể dùng dấu kết hợp.

Nếu công việc đòi hỏi so sánh theo chuẩn tương đương Unicode, có thể dùng `java.text.Normalizer` và chọn chuẩn như `Normalizer.Form.NFC`. Tuy nhiên, việc chuẩn hóa không tự giải quyết mọi vấn đề so sánh ngôn ngữ như viết hoa/thường, từ đồng nghĩa, sắp xếp theo vùng, hoặc ký tự nhìn gần giống nhau nhưng khác mã.

### 8.2. Emoji và cụm có Zero Width Joiner

Một số emoji hiển thị thành một biểu tượng duy nhất nhưng gồm nhiều code point nối bằng **Zero Width Joiner (ZWJ, U+200D)**. Các lá cờ emoji có thể dùng **hai regional indicator symbols**. Một số emoji còn có skin-tone modifier hoặc variation selector. Duyệt bằng `codePoints()` vẫn nhìn thấy từng thành phần chứ không tự đưa ra “một ký tự hiển thị”.

Khái niệm **extended grapheme cluster** trong Unicode (quy tắc phân đoạn UAX #29) được dùng khi cần tách các cụm ký tự người dùng có xu hướng nhận thức là một đơn vị. Trong Java hiện đại, regex `\X` của `java.util.regex.Pattern` là một công cụ để phân đoạn loại này.

### 8.3. Regex \X: đếm extended grapheme clusters

```java
import java.util.regex.Pattern;

String text = "e\u0301";
long clusters = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();

System.out.println(clusters); // 1
```

Đây là **snippet**; cần code nằm trong một phương thức/lớp. Trên Java 17+, `Pattern` hỗ trợ `\X`; khi viết chuỗi Java, cần escape thành `"\\X"` vì backslash thứ nhất dùng cho Java literal, backslash thứ hai đi tới regex engine.

Không đồng nhất grapheme cluster với **glyph render** hoặc bề rộng hiển thị: font có thể tạo ligature, biến thể chữ hoặc cách trình bày nhiều code point khác nhau; quy tắc Unicode được cập nhật theo phiên bản. Khi xây giới hạn nhập liệu hoặc vị trí con trỏ chính xác cho UI phức tạp, nên kiểm thử với engine hiển thị và tập emoji/ngôn ngữ thực tế, không chỉ một chuỗi demo.

Một lưu ý nữa: `java.text.BreakIterator.getCharacterInstance(locale)` cũng phục vụ phân đoạn ký tự, nhưng mức hỗ trợ các chuỗi emoji/ZWJ có thể phụ thuộc JDK và dữ liệu Unicode. Đừng mặc định mọi implementation/phiên bản trả cùng một ranh giới với mọi emoji mới.

## 9. Chuẩn hóa Unicode bằng Normalizer: giống khi nhìn không đồng nghĩa equals

Ví dụ **`UnicodeNormalizationDemo.java`** chạy độc lập:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Composed length: " + composed.length());
        System.out.println("Decomposed length: " + decomposed.length());
        System.out.println("Raw equals: " + composed.equals(decomposed));

        String normalizedA =
                Normalizer.normalize(composed, Normalizer.Form.NFC);
        String normalizedB =
                Normalizer.normalize(decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + normalizedA.equals(normalizedB));
        System.out.println("Decomposed graphemes: "
                + Pattern.compile("\\X").matcher(decomposed)
                         .results().count());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Kết quả:

```text
Composed length: 1
Decomposed length: 2
Raw equals: false
NFC equals: true
Decomposed graphemes: 1
```

Diễn giải:

- `equals` so sánh chuỗi theo đơn vị UTF-16; chuỗi dựng sẵn và chuỗi tách dấu khác nhau nên trả `false`.
- `Normalizer.Form.NFC` chuẩn hóa theo dạng tổ hợp chuẩn; hai biểu diễn tương đương về canonical representation sẽ so sánh bằng nhau.
- `Pattern.compile("\\X")` coi `e + dấu sắc` là một grapheme cluster trong ví dụ.
- Không nên tùy tiện chuẩn hóa mã định danh, chữ ký số, mật khẩu, token, hay dữ liệu có hợp đồng byte chính xác; hãy xác định quy ước đầu vào/so sánh trước. NFC không phải biện pháp bảo mật thay cho xác thực và không tự loại bỏ mọi ký tự dễ gây nhầm lẫn.

## 10. Khi nào nên dùng int code point, String và char?

| Trường hợp | API/kiểu nên cân nhắc | Tránh |
| --- | --- | --- |
| Lưu một ký tự ASCII hoặc một UTF-16 code unit | `char` | Tin rằng `char` luôn là ký tự hoàn chỉnh |
| Lưu một Unicode code point (bao gồm ngoài BMP) | `int`, `Character.toChars`, `appendCodePoint` | Ép code point supplementary xuống `char` |
| Duyệt code points | `String.codePoints()` hoặc `codePointAt` + `charCount` | `charAt(i)` với `i++` nếu cần duyệt từng code point |
| Lấy vị trí theo số code point | `offsetByCodePoints` | Dùng trực tiếp code point index trong `substring` |
| Đếm ký tự gần với cảm nhận người dùng | Quy tắc grapheme, `Pattern \X`, công cụ phân đoạn Unicode | `length()` hoặc `codePoints().count()` như số ký tự hiển thị |
| Đo số byte UTF-8 | `getBytes(StandardCharsets.UTF_8).length` | `length()` × 2 hoặc × 4 |
| So sánh hai biểu diễn dấu tương đương | `Normalizer` với form đã thống nhất | Tin rằng render giống nhau thì `equals` luôn `true` |
| Tìm và sắp xếp từ theo ngôn ngữ | API collation/bản địa hóa phù hợp | So sánh raw code units cho mọi ngôn ngữ |
| Tính chiều rộng ký tự trên màn hình | Engine font/layout của UI | Lấy số code point/grapheme làm số cột hiển thị |

### StringBuilder và char[]

Khi xây một chuỗi Unicode, có thể nối code point theo cách an toàn:

```java
int point = 0x1F600;
StringBuilder sb = new StringBuilder();
sb.appendCodePoint(point);
String emoji = sb.toString();
```

Hãy dùng `appendCodePoint` hoặc `Character.toChars` thay vì tự tính surrogate high/low từ code point nếu không thật sự cần viết thuật toán UTF-16. `StringBuilder.reverse()` của Java có xử lý surrogate pair hợp lệ để tránh đảo rời hai thành phần, **nhưng không có nghĩa đảo một chuỗi theo grapheme clusters**: dấu kết hợp và các chuỗi emoji nhiều code point vẫn có thể bị đảo sai theo nghĩa hiển thị.

### Đầu vào không hợp lệ và surrogate đứng một mình

Một `String` có thể tồn tại chứa một high surrogate không đi kèm low surrogate hoặc ngược lại. `length`, `charAt`, `codePointCount` vẫn vận hành theo hợp đồng của chúng; **không được suy luận rằng mọi `String` do Java tạo đều là chuỗi Unicode scalar values hợp lệ**.

Nếu xử lý dữ liệu từ byte, hãy quy định charset rõ ràng, ví dụ `StandardCharsets.UTF_8`, và lựa chọn chính sách phát hiện/thay thế dữ liệu UTF-8 hỏng. Với dữ liệu nhạy cảm về toàn vẹn, cần validation ở ranh giới hệ thống; không trông đợi `codePoints()` tự sửa mọi surrogate lẻ.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `text.length()` làm số chữ mà người dùng nhìn thấy | Emoji bị đếm đôi, dấu kết hợp bị đếm riêng | Xác định yêu cầu là code unit, code point hay grapheme |
| Gọi `text.charAt(i)` và coi kết quả là Unicode code point | Có thể chỉ đọc nửa surrogate | Dùng `codePointAt` hoặc `codePoints` |
| Lặp `for (i++)` với `codePointAt(i)` | Khi qua emoji sẽ đọc low surrogate thêm lần nữa | Tăng `i += Character.charCount(cp)` |
| Dùng `substring(0, max)` để giới hạn “max ký tự” | Có thể chẻ đôi surrogate pair hoặc grapheme | Đổi từ code point/grapheme index sang UTF-16 index trước khi cắt |
| Dùng `codePointCount` làm số ký tự hiển thị | `e + dấu sắc` vẫn đếm thành hai | Dùng quy tắc grapheme cho yêu cầu UI |
| Nghĩ UTF-8 dài bằng `String.length()` | Sai dung lượng truyền/lưu | Đếm byte sau encode theo charset đã chọn |
| Dùng `String.chars()` để lấy code point | Surrogate pair không được gộp | Dùng `String.codePoints()` |
| Dùng một `char` lưu emoji ngoài BMP | Mất code point hoặc lỗi literal | Dùng `String` hoặc `int` |
| So sánh raw text có dấu từ nhiều nguồn và thấy khác | Dạng NFC/NFD khác nhau | Thống nhất normalization theo hợp đồng |
| Cho rằng `Normalizer` giải quyết mọi tương đương ngôn ngữ | Case folding/collation/độ tương tự glyph là bài toán khác | Dùng API bản địa hóa và validation phù hợp |
| Cắt đúng code point rồi coi là đúng một ký tự hiển thị | Có thể chẻ cụm ZWJ/combining | Cân nhắc extended grapheme cluster |
| Dùng phiên bản Java không cố định Unicode và so sánh ranh giới emoji cực mới | Phân đoạn có thể đổi theo Unicode/JDK | Ghim phiên bản và kiểm thử bộ ký tự thật |

## 12. Bài tập và kiểm tra hiểu biết

**Bài 1.** Nếu `String s = new String(Character.toChars(0x1F600));`, giá trị `s.length()` và `s.codePointCount(0, s.length())` là bao nhiêu?

**Đáp án:** `2` UTF-16 code units nhưng chỉ `1` Unicode code point.

**Bài 2.** Chuỗi gồm `A + emoji U+1F600 + B` có độ dài bao nhiêu, và tại sao `substring(1, 2)` sai khi muốn lấy emoji?

**Đáp án:** `length() == 4`. Emoji ở hai code unit index 1 và 2. `substring(1, 2)` chỉ lấy high surrogate; phải lấy `substring(1, 3)` hoặc cắt qua `offsetByCodePoints`.

**Bài 3.** `String s = "e\u0301";` có bao nhiêu code point và bao nhiêu extended grapheme cluster?

**Đáp án:** Hai code point (`e` và dấu sắc kết hợp), nhưng thường được phân thành **một** extended grapheme cluster.

**Bài 4.** `new String(Character.toChars(0x1F600)).chars().count()` có bằng `codePoints().count()` không?

**Đáp án:** Không. `chars().count() == 2` vì đếm code units; `codePoints().count() == 1` vì cặp surrogate được gộp.

**Bài 5.** Hai chuỗi `"\u00E9"` và `"e\u0301"` hiển thị gần như giống nhau nhưng `equals` trả `false`. Có thể làm gì nếu ứng dụng yêu cầu canonical equivalence?

**Đáp án:** Chuẩn hóa hai chuỗi về một Unicode normalization form như `Normalizer.Form.NFC` trước khi so sánh, theo chính sách dữ liệu thống nhất.

**Bài 6.** Muốn giới hạn tên người dùng theo “20 ký tự hiển thị”, chỉ dùng `offsetByCodePoints` có đủ không?

**Đáp án:** Chưa đủ. Nó tránh chia surrogate pair nhưng không giữ nguyên mọi grapheme cluster gồm dấu kết hợp/emoji nhiều code point. Cần quy tắc phân đoạn grapheme và kiểm thử với thiết bị/Unicode version mục tiêu.

**Bài 7.** Một API giới hạn body tối đa 1.024 byte UTF-8. Dùng `String.length() <= 1024` có đảm bảo byte length không vượt quá 1.024 không?

**Đáp án:** Không. UTF-8 có độ dài byte biến thiên, khác số UTF-16 code units. Cần encode theo UTF-8 rồi đo byte thực, đồng thời xử lý dữ liệu UTF-16 không hợp lệ theo hợp đồng encode.

## 13. Tổng kết

- `char` trong Java là **một đơn vị mã UTF-16 16 bit**, không phải lúc nào cũng là một Unicode code point hoặc một “chữ” người dùng nhìn thấy.
- Code point ngoài BMP (ví dụ emoji `U+1F600`) được biểu diễn bằng **surrogate pair**, chiếm hai `char`.
- `String.length()`, `codePointCount`, `getBytes(UTF_8).length` và số grapheme clusters là **bốn đại lượng khác nhau**.
- Với tác vụ ở mức code point, dùng `codePoints()`, `codePointAt`, `Character.charCount`, `offsetByCodePoints`, `Character.toChars` hoặc `appendCodePoint`.
- Với thao tác theo ký tự hiển thị, cần xét **extended grapheme cluster**; Java hỗ trợ regex `\X`, nhưng vẫn phải kiểm thử văn bản thực tế.
- Với tiếng Việt và dữ liệu đa nguồn, hãy nhận biết **dấu kết hợp**, **Unicode normalization** và các giới hạn của so sánh raw `String.equals`.
- Xác định chính xác bạn muốn đếm **code units, code points, graphemes hay UTF-8 bytes** trước khi thiết kế kiểm tra độ dài, cắt chuỗi, lưu trữ hoặc API.

Tài liệu chính thức:

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Character](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Java SE 21 — Pattern (\X và grapheme boundary)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/)
