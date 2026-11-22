# Unicode, phân loại ký tự và biểu thức chính quy

Khi nâng cấp JDK, nhiều nhóm phát triển tập trung vào API bị loại bỏ, bytecode và cấu hình JVM nhưng bỏ qua một nguồn thay đổi hành vi ít rõ ràng hơn: **dữ liệu Unicode và các quy tắc phân loại ký tự** mà thư viện chuẩn Java sử dụng. Một regex từng từ chối một ký tự có thể bắt đầu chấp nhận ký tự đó trên JDK mới; một đoạn kiểm tra `Character.isLetter(...)` có thể cho kết quả khác với một code point vừa được Unicode bổ sung hoặc phân loại lại; thao tác tách từ, chuẩn hóa hay so khớp không phân biệt hoa thường cũng có thể tạo khác biệt ở ranh giới dữ liệu.

Các thay đổi này không nhất thiết làm chương trình lỗi khi biên dịch hoặc ném exception lúc chạy. Chúng có thể âm thầm ảnh hưởng đến **validation, tìm kiếm, tokenization, định danh người dùng, phân tích log, bảo mật đầu vào và kết quả nghiệp vụ**. Vì vậy, kiểm thử tương thích hành vi phải bao gồm ký tự ngoài ASCII, tổ hợp dấu, khoảng trắng Unicode và những trường hợp biểu thức chính quy dựa vào bảng dữ liệu Unicode của JDK.

Bài học giải thích mô hình Unicode trong Java, sự khác nhau giữa `char`, *code point* và ký tự người dùng nhìn thấy; cách `Character` phân loại ký tự; cách `java.util.regex.Pattern` hiểu các nhóm `\d`, `\w`, `\s`, `\p{...}`; tác động của normalization và các bước xây dựng regression test khi chuyển JDK.

## 1. Unicode là gì và vì sao phiên bản JDK có liên quan?

Unicode định nghĩa một không gian mã cho các ký tự và nhiều thuộc tính liên quan: chữ cái, chữ số, dấu kết hợp, dấu câu, khoảng trắng, hướng văn bản, script và các quy tắc xử lý khác. Mỗi giá trị mã được gọi là một **Unicode code point**, thường được viết dưới dạng `U+XXXX`.

Ví dụ:

| Ký tự | Code point | Ghi chú |
|---|---|---|
| `A` | U+0041 | Chữ Latin viết hoa. |
| `á` | U+00E1 | Chữ Latin có dấu được mã hóa thành một code point. |
| `中` | U+4E2D | Chữ Hán. |
| `١` | U+0661 | Chữ số Arabic-Indic một. |
| `😀` | U+1F600 | Emoji nằm ngoài Basic Multilingual Plane. |
| `◌́` | U+0301 | Dấu sắc kết hợp; cần một ký tự nền để hiển thị như chữ có dấu. |

JDK cung cấp các API như `java.lang.Character`, `java.lang.String`, `java.text.Normalizer` và `java.util.regex.Pattern`. Các API này có thể dựa vào dữ liệu Unicode được tích hợp trong phiên bản Java đang chạy. Khi JDK cập nhật phiên bản Unicode mà nó hỗ trợ, **tập ký tự và thuộc tính được công nhận có thể thay đổi** dù source code không thay đổi.

Điều này khác với một thay đổi API kiểu đổi tên method. Một lời gọi `Character.isLetter(cp)` vẫn tồn tại và chạy bình thường trên hai JDK, nhưng kết quả cho một code point cụ thể có thể khác nếu thông tin Unicode của code point đó thay đổi giữa hai phiên bản.

### 1.1. Không nên đồng nhất “Java version” với “Unicode version”

Java có lịch phát hành riêng và Unicode có lịch phát hành riêng. Mỗi bản JDK có thể tích hợp một phiên bản Unicode nhất định hoặc điều chỉnh hỗ trợ liên quan. Vì vậy, khi kiểm tra một khác biệt phân loại, cần đọc tài liệu của **đúng bản JDK và vendor** để xác định tập dữ liệu Unicode mà nó sử dụng.

Không nên suy luận rằng cứ tăng một bản Java thì tất cả ký tự đều thay đổi, hay một bản Java mới hơn luôn dùng Unicode mới nhất tại thời điểm hiện tại. Hãy tập trung vào những code point và hợp đồng validation thực sự có liên quan đến ứng dụng.

### 1.2. Tương thích mã nguồn không bảo đảm tương thích hành vi

Ví dụ, một dịch vụ kiểm tra `Character.isLetter(cp)` rồi cho phép ký tự hợp lệ vào mã định danh. Nếu một phiên bản Unicode mới bổ sung một chữ cái trong script chưa được JDK cũ nhận diện, cùng đoạn code có thể chấp nhận một tập đầu vào lớn hơn sau khi nâng JDK.

Điều này có thể là cải tiến đúng với tiêu chuẩn Unicode nhưng vẫn là **thay đổi hợp đồng nghiệp vụ** nếu hệ thống từng quy định chính xác tập ký tự được chấp nhận. Regression test không chỉ kiểm tra chương trình còn chạy; nó cần kiểm tra tập đầu vào nào được chấp nhận và đầu ra được chuẩn hóa ra sao.

## 2. Phân biệt code point, UTF-16 code unit và grapheme cluster

Một trong những sai lầm phổ biến nhất khi xử lý Unicode trong Java là xem mỗi `char` như một ký tự hoàn chỉnh mà người dùng nhìn thấy.

### 2.1. `char` là một UTF-16 code unit

Trong Java, `char` có độ rộng 16 bit. `String` được biểu diễn theo chuỗi UTF-16 code unit ở cấp API. Nhiều ký tự trong Basic Multilingual Plane (BMP) dùng một code unit; những code point bổ sung (supplementary code points) ngoài BMP được mã hóa thành **surrogate pair** gồm hai `char`.

Ví dụ:

```java
String emoji = "😀";

System.out.println(emoji.length());
// 2: hai UTF-16 code unit

System.out.println(emoji.codePointCount(0, emoji.length()));
// 1: một Unicode code point
```

`String.length()` trả về số UTF-16 code unit, **không phải số Unicode code point hoặc số ký tự hiển thị**. `charAt(0)` của `emoji` trả về high surrogate, không phải toàn bộ emoji.

Để duyệt code point, có thể dùng:

```java
String text = "A😀中";

text.codePoints().forEach(cp -> {
    System.out.printf("U+%04X%n", cp);
});
```

Kết quả về mặt mã điểm là `U+0041`, `U+1F600` và `U+4E2D`. Khi cần thao tác index, dùng các API `codePointAt`, `codePointBefore`, `offsetByCodePoints` và `codePointCount` thay vì mặc định tăng chỉ số UTF-16 thêm một đơn vị.

### 2.2. Một chữ cái Unicode có thể cần nhiều code point

Tiếng Việt cung cấp nhiều ví dụ quan trọng về **combining marks**. Ký tự `ắ` có thể được biểu diễn bằng một code point được dựng sẵn, hoặc bằng chữ `a` cộng hai dấu kết hợp.

```java
String composed = "ắ";              // U+1EAF
String decomposed = "a\u0306\u0301"; // a + combining breve + combining acute

System.out.println(composed.equals(decomposed));
// false: hai chuỗi UTF-16 khác nhau
```

Hai chuỗi có thể trông giống nhau khi hiển thị, nhưng `String.equals` so sánh chuỗi code unit, không tự áp dụng Unicode canonical normalization. Điều này ảnh hưởng đến tên người dùng, khóa lưu trữ, tìm kiếm và so sánh dữ liệu từ nhiều hệ thống nhập liệu.

### 2.3. Grapheme cluster là đơn vị ký tự người dùng thường nhận thức

Ngay cả code point cũng chưa luôn tương ứng với một ký tự hiển thị. Một tổ hợp có thể chứa chữ cái nền và nhiều dấu; một emoji có thể dùng nhiều code point nối bằng zero-width joiner.

Ví dụ, chuỗi `👩‍💻` thường được người dùng nhìn như một emoji, nhưng gồm các code point cho người phụ nữ, zero-width joiner và máy tính xách tay. Vì vậy:

```java
String s = "👩‍💻";

System.out.println(s.length());
// 5 UTF-16 code unit

System.out.println(s.codePointCount(0, s.length()));
// 3 code point
```

Nếu quy tắc nghiệp vụ là “tối đa 20 ký tự người dùng nhìn thấy”, cả `length()` lẫn `codePointCount(...)` có thể chưa đáp ứng yêu cầu. Cần dùng cơ chế phân đoạn grapheme cluster phù hợp với Unicode và yêu cầu sản phẩm; `Pattern` có cú pháp `\X` để so khớp extended grapheme cluster trên các JDK hỗ trợ. Quy tắc grapheme có thể tiến hóa theo dữ liệu Unicode và phiên bản runtime, vì vậy phải kiểm thử với đúng JDK triển khai.

### 2.4. Bảng chọn đơn vị đo phù hợp

| Yêu cầu | Đơn vị/API thường phù hợp | Lưu ý |
|---|---|---|
| Số code unit trong String | `length()` | Không phải số code point. |
| Duyệt Unicode code point | `codePoints()` / `codePointAt()` | Cần xử lý cẩn thận surrogate không ghép cặp nếu dữ liệu không hợp lệ. |
| Phân loại chữ, số, dấu ở từng code point | `Character` API nhận `int` | Tránh cắt đôi supplementary character. |
| Số ký tự người dùng nhận thức | Grapheme cluster segmentation | Có thể khác số code point, phụ thuộc quy tắc Unicode. |
| Giới hạn byte trong giao thức/file | Encode bằng charset cụ thể rồi đếm byte | Không dùng độ dài String để suy ra số byte UTF-8. |

## 3. Phân loại ký tự với `java.lang.Character`

`Character` cung cấp nhiều phương thức nhận dạng ký tự. Chúng không cùng định nghĩa và không thể thay thế nhau chỉ vì đều trả về `boolean`.

### 3.1. `isLetter`, `isDigit`, `isLetterOrDigit`

```java
int latin = 'A';
int han = '中';
int arabicDigit = '١';

System.out.println(Character.isLetter(latin));       // true
System.out.println(Character.isLetter(han));         // true
System.out.println(Character.isDigit(arabicDigit));  // true
```

`Character.isLetter(int)` nhận diện các code point thuộc nhóm chữ cái theo phân loại Unicode mà JDK hỗ trợ. `Character.isDigit(int)` nhận diện các chữ số thập phân Unicode theo tiêu chí của API, không chỉ `'0'` tới `'9'` trong ASCII.

Nếu quy tắc nghiệp vụ chỉ cho phép số ASCII, dùng điều kiện tường minh:

```java
boolean isAsciiDigit(int cp) {
    return cp >= '0' && cp <= '9';
}
```

Không nên dùng `Character.isDigit` rồi suy ra nó tương đương với regex `[0-9]`. Một quy tắc cố định ASCII và một quy tắc Unicode là hai hợp đồng khác nhau.

### 3.2. Tránh dùng overload `char` cho supplementary code point

Ví dụ U+10400 là chữ cái thuộc Deseret, nằm ngoài BMP:

```java
int codePoint = 0x10400;
String letter = new String(Character.toChars(codePoint));

System.out.println(letter.length());                     // 2
System.out.println(Character.isLetter(letter.charAt(0))); // false
System.out.println(Character.isLetter(letter.codePointAt(0))); // true
```

Khi gọi `isLetter` với `letter.charAt(0)`, method chỉ nhìn thấy một surrogate code unit. Overload nhận `int` cho phép kiểm tra toàn bộ code point. Nếu dự án cần hỗ trợ Unicode ngoài BMP, hãy ưu tiên API theo code point tại các ranh giới phân loại.

### 3.3. `getType`: biết loại Unicode cụ thể hơn

`Character.getType(int)` trả về category của code point. Các giá trị tiêu biểu gồm `UPPERCASE_LETTER`, `LOWERCASE_LETTER`, `OTHER_LETTER`, `DECIMAL_DIGIT_NUMBER`, `NON_SPACING_MARK`, `SPACE_SEPARATOR`, `CONTROL` và `OTHER_SYMBOL`.

```java
int mark = 0x0301; // Combining acute accent

System.out.println(Character.getType(mark)
    == Character.NON_SPACING_MARK); // true
```

Nếu bộ lọc tên người dùng chấp nhận chữ cái Unicode nhưng không chấp nhận combining marks, các chuỗi ở dạng NFD có thể bị loại dù hiển thị giống dạng NFC. Vì vậy, cần quyết định chính sách normalization và validation **cùng lúc**.

### 3.4. `isAlphabetic` không đồng nhất với `isLetter`

`Character.isAlphabetic(int)` dựa trên thuộc tính chữ cái theo định nghĩa Unicode rộng hơn so với một số kiểm tra category đơn giản. Nó không nên được thay thế máy móc bởi `isLetter` khi mục đích nghiệp vụ là chấp nhận toàn bộ ký tự có thuộc tính alphabetic.

Ngược lại, quy tắc mã định danh của một sản phẩm không nhất thiết phải dùng tất cả ký tự alphabetic của Unicode. Nhóm cần ghi cụ thể: chấp nhận chữ thuộc script nào, có cho phép dấu kết hợp và chữ số không, có chuẩn hóa hay không.

### 3.5. `isJavaIdentifierStart` và `isJavaIdentifierPart`

Java có quy tắc riêng cho ký tự được phép xuất hiện trong identifier ngôn ngữ Java:

```java
boolean canStart = Character.isJavaIdentifierStart(cp);
boolean canContinue = Character.isJavaIdentifierPart(cp);
```

Đây là quy tắc phục vụ cú pháp identifier Java, **không phải** quy tắc phù hợp mặc định cho username, domain name, tên công ty hay mã khách hàng. Cần tránh lấy chính sách của compiler Java làm chính sách nghiệp vụ mà không phân tích ý nghĩa và rủi ro bảo mật.

### 3.6. Unicode script và block

Đôi khi ứng dụng cần thống kê hoặc giới hạn một số nhóm chữ viết. `Character.UnicodeScript.of(cp)` giúp nhận biết script, còn `Character.UnicodeBlock.of(cp)` nhận biết block mà code point thuộc về.

```java
int cp = '中';

System.out.println(Character.UnicodeScript.of(cp));
System.out.println(Character.UnicodeBlock.of(cp));
```

**Script không đồng nghĩa block.** Block là khoảng mã được quy định trong Unicode; script mô tả hệ chữ viết. Một script có thể trải trên nhiều block, và một block có thể chứa nhiều loại ký tự. Nếu thiết kế bộ lọc script, cần dựa trên thuộc tính phù hợp thay vì suy ra mọi code point trong một block đều là chữ của cùng script.

## 4. Khoảng trắng Unicode: một nguồn thay đổi validation thường bị bỏ sót

Khoảng trắng không chỉ gồm dấu cách ASCII (`U+0020`), tab và xuống dòng. Unicode có nhiều space separator và ký tự điều khiển liên quan đến khoảng trắng. Java cũng cung cấp những định nghĩa khác nhau cho việc nhận diện và loại bỏ chúng.

### 4.1. `Character.isWhitespace` và `Character.isSpaceChar`

Hai method không có cùng tập ký tự:

```java
char regularSpace = ' ';
char nbsp = '\u00A0'; // NO-BREAK SPACE

System.out.println(Character.isWhitespace(regularSpace)); // true
System.out.println(Character.isSpaceChar(regularSpace));   // true

System.out.println(Character.isWhitespace(nbsp));         // false
System.out.println(Character.isSpaceChar(nbsp));          // true
```

NO-BREAK SPACE là ví dụ quan trọng: nó là ký tự phân cách dạng khoảng trắng theo Unicode, nhưng `Character.isWhitespace` loại trừ một số khoảng trắng không ngắt dòng. Vì vậy, không nên kết luận một chuỗi đã sạch mọi khoảng trắng chỉ vì đã lọc bằng một API cụ thể.

### 4.2. `String.trim()` và `String.strip()` khác nhau

`trim()` theo quy tắc lịch sử, chủ yếu loại bỏ các code unit ở đầu/cuối có giá trị không lớn hơn U+0020. `strip()` dùng khái niệm whitespace theo `Character.isWhitespace` và hỗ trợ nhiều ký tự ngoài ASCII.

```java
String s = "\u2003Hello\u2003"; // EM SPACE

System.out.println(s.trim().equals("Hello"));  // false
System.out.println(s.strip().equals("Hello")); // true
```

Nhưng `strip()` không tự loại bỏ mọi Unicode space separator, chẳng hạn NO-BREAK SPACE ở ví dụ trên. Nếu yêu cầu là loại bỏ các ký tự Unicode White_Space theo định nghĩa khác, cần xác định chính sách riêng và thử đầy đủ tập ký tự liên quan.

### 4.3. So sánh với `\s` của regex

Trong Java regex, `\s` mặc định thường là nhóm whitespace ASCII cơ bản. Khi bật `Pattern.UNICODE_CHARACTER_CLASS`, các predefined character class như `\s` theo quy tắc Unicode rộng hơn.

```java
import java.util.regex.Pattern;

String nbsp = "\u00A0";

System.out.println(Pattern.compile("\\s").matcher(nbsp).matches());
// false theo quy tắc mặc định

System.out.println(Pattern.compile(
    "\\s", Pattern.UNICODE_CHARACTER_CLASS
).matcher(nbsp).matches());
// true: Unicode White_Space bao gồm NO-BREAK SPACE
```

Điểm cần nhớ: **`Character.isWhitespace`, `Character.isSpaceChar`, `String.strip()` và regex `\s` không phải bốn cách viết tương đương**. Nếu dự án nâng JDK hoặc thay cờ regex, việc chuẩn hóa khoảng trắng có thể thay đổi và làm khác kết quả so sánh hoặc parse dữ liệu.

## 5. Cách Java regex phân loại ký tự

`java.util.regex.Pattern` hỗ trợ cú pháp dựa trên ASCII và Unicode. Muốn phân tích tác động migration, cần biết từng pattern đang yêu cầu tập ký tự nào.

### 5.1. `[A-Za-z]` và `[0-9]`: tập ASCII tường minh

```java
import java.util.regex.Pattern;

Pattern asciiCode = Pattern.compile("[A-Za-z0-9]+");

System.out.println(asciiCode.matcher("User123").matches()); // true
System.out.println(asciiCode.matcher("Tâm123").matches());   // false
```

Các range này diễn tả giá trị mã ASCII cụ thể. Nếu hợp đồng của một mã kỹ thuật chỉ cho phép ASCII, viết tường minh là lựa chọn dễ kiểm soát. Nhưng nếu dùng nó cho tên người hoặc nội dung tự nhiên đa ngôn ngữ, chính sách có thể loại bỏ dữ liệu hợp lệ của người dùng.

### 5.2. `\d`, `\w`, `\s`: predefined classes và cờ Unicode

Các predefined class của Java regex thường dùng:

| Regex | Ý nghĩa mặc định thường dùng | Khi bật `UNICODE_CHARACTER_CLASS` |
|---|---|---|
| `\d` | Chữ số ASCII `[0-9]` | Chữ số thập phân Unicode theo định nghĩa áp dụng. |
| `\w` | Word character ASCII, thường tương ứng chữ/số/underscore ASCII | Tập word character rộng hơn theo Unicode, gồm nhiều chữ, số, dấu kết hợp và một số ký tự liên quan. |
| `\s` | Một số whitespace ASCII như dấu cách, tab và xuống dòng | Unicode White_Space. |

Ví dụ với chữ số Arabic-Indic:

```java
import java.util.regex.Pattern;

String digits = "١٢٣"; // U+0661 U+0662 U+0663

Pattern defaultDigits = Pattern.compile("\\d+");
Pattern unicodeDigits = Pattern.compile(
    "\\d+", Pattern.UNICODE_CHARACTER_CLASS
);

System.out.println(defaultDigits.matcher(digits).matches()); // false
System.out.println(unicodeDigits.matcher(digits).matches()); // true
```

Ở đây source code không đổi nhưng việc bật/tắt flag tạo hợp đồng validation khác hẳn. Ngoài ra, nếu bảng Unicode trong JDK thay đổi, những predefined class theo Unicode cũng có thể nhận diện tập code point khác.

### 5.3. `(?U)` là cách bật Unicode character classes ngay trong pattern

Java regex hỗ trợ embedded flag `(?U)` tương đương bật `Pattern.UNICODE_CHARACTER_CLASS` cho phạm vi thích hợp của pattern.

```java
Pattern p1 = Pattern.compile("(?U)\\w+");

Pattern p2 = Pattern.compile(
    "\\w+", Pattern.UNICODE_CHARACTER_CLASS
);
```

Khi đọc một regex legacy, hãy kiểm tra cả flags truyền cho `Pattern.compile(...)` lẫn flags viết trong chính biểu thức. Một chuỗi regex `"\\w+"` không cho biết toàn bộ cách so khớp nếu bỏ qua cấu hình khi compile.

### 5.4. Các lớp Unicode viết tường minh với `\p{...}`

Java regex hỗ trợ nhiều Unicode property class. Ví dụ:

```java
Pattern letters = Pattern.compile("\\p{L}+");
Pattern marks = Pattern.compile("\\p{M}+");
Pattern decimalNumbers = Pattern.compile("\\p{Nd}+");
Pattern separators = Pattern.compile("\\p{Zs}+");
```

- `\p{L}`: các category chữ cái Unicode.
- `\p{M}`: các dấu kết hợp/mark Unicode.
- `\p{Nd}`: các chữ số thập phân Unicode.
- `\p{Zs}`: các space separator Unicode.

Pattern cũng hỗ trợ những property và cách ghi khác, chẳng hạn script hoặc block theo cú pháp được JDK hỗ trợ. Hãy tra cứu Javadoc của `java.util.regex.Pattern` ở đúng JDK đang dùng khi cần viết các property phức tạp.

Một regex như `\p{L}` không tự bao gồm mọi combining mark. Nếu validation dùng `\p{L}+` mà đầu vào ở dạng phân rã (NFD), chuỗi có dấu có thể bị từ chối ngay cả khi dạng dựng sẵn (NFC) được chấp nhận.

### 5.5. `\b` và ranh giới từ cần được kiểm thử riêng

Ranh giới từ `\b` phụ thuộc vào cách regex engine xác định vị trí chuyển giữa ký tự thuộc và không thuộc từ. Hành vi của word boundary và các Unicode-related classes đã có những khác biệt theo phiên bản, nên không nên mặc định `\b` luôn tương đương với một quy tắc tự viết dựa trên `\w` trong mọi JDK.

Ví dụ, tokenization dựa vào `"\\b\\w+\\b"` có thể không tương đương với yêu cầu “tách các từ tự nhiên trong tiếng Việt, tiếng Thái hoặc tiếng Nhật”. Với văn bản đa ngôn ngữ, cần định nghĩa rõ khái niệm *từ* và test các chuỗi đại diện. Regex word boundary không thay thế hoàn toàn thuật toán phân đoạn từ dành riêng cho ngôn ngữ.

### 5.6. `Pattern.CASE_INSENSITIVE` và `Pattern.UNICODE_CASE`

Việc so khớp không phân biệt hoa thường không phải bài toán ASCII đơn giản trong mọi script. Java regex có các flag:

```java
Pattern p = Pattern.compile(
    "somePattern",
    Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
```

`CASE_INSENSITIVE` bật so khớp không phân biệt hoa thường; `UNICODE_CASE` làm quy tắc này theo khả năng Unicode thay vì chỉ mặc định ASCII. `UNICODE_CHARACTER_CLASS` cũng kéo theo hành vi Unicode case folding khi thích hợp.

Không nên coi flag trên là cách so sánh chuỗi **theo locale**. Đặc biệt với tiếng Thổ Nhĩ Kỳ và các ngôn ngữ có quy tắc chữ hoa/thường đặc biệt, việc chuyển case, so sánh định danh và so khớp regex cần chính sách riêng.

### 5.7. Escaping trong chuỗi Java và regex

Regex cần được ghi trong string literal Java, nên dấu `\` thường phải được escape thêm một lần:

```java
String regex = "\\p{L}+"; // regex engine nhận \p{L}+
```

Nếu đọc cùng biểu thức từ file cấu hình, lớp escaping có thể khác:

```properties
# Trong file cấu hình, cách diễn giải backslash còn tùy bộ parser
name.regex=\\p{L}+
```

Ví dụ cấu hình trên chỉ minh họa rằng phải kiểm tra quy tắc escape của **định dạng và thư viện đọc cấu hình**; với `java.util.Properties`, backslash bản thân có ý nghĩa escape. Không nên sao chép string literal Java sang YAML/properties/JSON rồi giả định regex engine sẽ nhận cùng chuỗi. Cách an toàn là log hoặc test biểu thức **sau khi đã được parser cấu hình giải mã**, trong môi trường kiểm thử.

## 6. Unicode normalization và tính nhất quán khi so sánh

Unicode cho phép một số chuỗi có nhiều cách biểu diễn tương đương về mặt chuẩn tắc. Java cung cấp `java.text.Normalizer` để chuyển chuỗi sang các dạng normalization khác nhau.

### 6.1. NFC và NFD

- **NFC**: canonical composition, ưu tiên các dạng ký tự dựng sẵn khi có thể.
- **NFD**: canonical decomposition, tách các ký tự có thể phân rã thành các thành phần tương ứng.

Ví dụ:

```java
import java.text.Normalizer;

String a = "ắ";
String b = "a\u0306\u0301";

System.out.println(a.equals(b)); // false

String n1 = Normalizer.normalize(a, Normalizer.Form.NFC);
String n2 = Normalizer.normalize(b, Normalizer.Form.NFC);

System.out.println(n1.equals(n2)); // true
```

Nếu hệ thống dùng tên đã chuẩn hóa làm khóa tra cứu, cần thống nhất normalization ở **điểm nhập dữ liệu** và khi so sánh, tìm kiếm, lưu trữ, thay vì chỉ chuẩn hóa ở một service.

### 6.2. NFKC và NFKD không tương đương với NFC/NFD

`NFKC` và `NFKD` sử dụng compatibility normalization, có thể gộp các biểu diễn vốn khác nhau về mặt tương thích, ví dụ một số ký tự fullwidth hoặc ligature.

Đây có thể là điều mong muốn khi chuẩn hóa mã tìm kiếm, nhưng không nên áp dụng mặc định cho mọi dữ liệu. Compatibility normalization có thể làm mất phân biệt có ý nghĩa trong văn bản gốc, tên riêng hoặc dữ liệu cần giữ nguyên pháp lý/kỹ thuật.

Hãy xác định rõ mục tiêu: bảo toàn văn bản gốc, so sánh canonical-equivalent, tìm kiếm không phân biệt biến thể, hay chuẩn hóa identifier bảo mật. Mỗi mục tiêu có chính sách khác nhau.

### 6.3. Normalization trước hay sau validation?

Thứ tự xử lý có thể ảnh hưởng kết quả:

```text
Input
  |
  v
Giải mã bằng charset đã chỉ định
  |
  v
Normalization theo hợp đồng (nếu yêu cầu)
  |
  v
Validation theo code point/grapheme/regex
  |
  v
Lưu trữ hoặc sử dụng
```

Nếu validate bằng `\p{L}+` trước khi normalization, một chuỗi tiếng Việt decomposed có thể bị loại do có combining marks. Nếu normalize sang NFC trước, một số chữ có dấu trở thành code point chữ cái dựng sẵn. Tuy nhiên, không phải mọi chuỗi hợp lệ đều có thể gom về một code point, nên với dữ liệu đa ngôn ngữ thường vẫn cần quy tắc về dấu kết hợp.

### 6.4. Có nên dùng `Pattern.CANON_EQ`?

Java regex có cờ `CANON_EQ` liên quan đến canonical equivalence. Tuy nhiên, bật cơ chế này có chi phí và đặc điểm xử lý riêng; không nên coi nó là cách thay thế mặc định cho một pipeline normalization và validation được thiết kế rõ ràng.

Với hợp đồng dữ liệu cần ổn định, thường dễ kiểm soát hơn khi normalize đầu vào tường minh rồi chạy regex trên biểu diễn đã được chọn. Dù dùng cách nào, hãy test với dấu kết hợp và ký tự đa code point.

## 7. Những tình huống thực tế dễ phát sinh regression sau khi nâng JDK

### 7.1. Username validation thay đổi tập ký tự được chấp nhận

Giả sử một dịch vụ dùng:

```java
boolean valid = Pattern.compile("(?U)\\w+")
    .matcher(username)
    .matches();
```

Regex sử dụng Unicode word class của JDK. Khi JDK hỗ trợ thêm code point hoặc cập nhật thuộc tính Unicode, một số username trước đây bị từ chối có thể được chấp nhận. Nếu hệ thống bảo mật hoặc xử lý trùng tên dựa vào tập ký tự cũ, kết quả có thể lệch giữa node chạy JDK khác nhau.

Hướng xử lý là ghi thành **hợp đồng validation** rõ ràng: tập script được phép, độ dài đo theo đơn vị gì, normalization nào, cách xử lý case và khoảng trắng, cùng bộ test dữ liệu đại diện. Không nên dựa vào một regex ngắn rồi coi nó là chính sách đầy đủ.

### 7.2. Trích xuất số từ văn bản thay đổi do `\d`

```java
Pattern asciiOnly = Pattern.compile("\\d+");
Pattern unicode = Pattern.compile("(?U)\\d+");
```

Hai pattern có thể tìm các chuỗi khác nhau. Ví dụ văn bản chứa chữ số Arabic-Indic hoặc chữ số thập phân thuộc script khác. Nếu một trường dữ liệu yêu cầu mã giao dịch ASCII theo giao thức, nên dùng `[0-9]` và mô tả rõ. Nếu cần tiếp nhận chữ số Unicode để hiển thị hoặc phân tích ngôn ngữ tự nhiên, hãy xác định cách chuẩn hóa sang dạng lưu trữ và kiểm thử parse số.

Chú ý: việc regex chấp nhận ký tự là chữ số không chứng minh tất cả thư viện parse số hoặc hệ thống downstream chấp nhận cùng cách biểu diễn.

### 7.3. Dữ liệu tiếng Việt NFC/NFD cho kết quả regex khác nhau

```java
Pattern lettersOnly = Pattern.compile("\\p{L}+");

String composed = "ắ";
String decomposed = "a\u0306\u0301";

System.out.println(lettersOnly.matcher(composed).matches());
// true

System.out.println(lettersOnly.matcher(decomposed).matches());
// false: hai dấu kết hợp thuộc nhóm Mark, không phải Letter
```

Nếu một client gửi NFC còn một client khác gửi NFD, validation có thể cho kết quả khác trong cùng một JDK. Nâng JDK không phải nguyên nhân duy nhất; migration thường làm lộ vấn đề vì đổi thư viện đọc file, hệ điều hành hoặc pipeline chuẩn hóa.

### 7.4. Khoảng trắng không ngắt dòng trong dữ liệu copy/paste

Người dùng có thể sao chép một chuỗi chứa U+00A0 từ HTML. Code dùng `strip()` hoặc regex `\s` mặc định có thể không loại bỏ ký tự theo cách nhóm mong đợi. Ngược lại, bật Unicode mode của regex có thể làm thao tác tách token nhận diện thêm khoảng trắng.

Nếu một hệ thống thanh toán so sánh mã tham chiếu sau khi “trim whitespace”, cần định nghĩa chính xác những code point nào bị loại bỏ thay vì thay API tùy tiện giữa `trim`, `strip` và `replaceAll("\\s+", ...)`.

### 7.5. Case mapping phụ thuộc locale

```java
import java.util.Locale;

String key = "TITLE";

String defaultLower = key.toLowerCase();
String rootLower = key.toLowerCase(Locale.ROOT);
```

`toLowerCase()` không truyền locale có thể phụ thuộc default locale của tiến trình. Ở một số ngôn ngữ như tiếng Thổ Nhĩ Kỳ, chữ `I` có quy tắc chuyển case đặc biệt. Nếu JDK migration đi kèm thay đổi locale mặc định hoặc thay đổi môi trường container, kết quả có thể khác dù Unicode data không đổi.

Đối với mã kỹ thuật độc lập với ngôn ngữ tự nhiên, dùng locale được chỉ định theo chính sách; `Locale.ROOT` thường phù hợp hơn việc dùng default locale một cách ngẫu nhiên. Đối với tên người và văn bản tự nhiên, cần cân nhắc quy tắc ngôn ngữ, Unicode normalization và cách tìm kiếm riêng.

### 7.6. Tokenization và word boundary trong log hoặc tìm kiếm

Một hệ thống phân tích log có thể dùng:

```java
Pattern token = Pattern.compile("\\b\\w+\\b");
```

Kết quả có thể phụ thuộc vào định nghĩa word character và word boundary của regex engine, flags Unicode và phiên bản JDK. Nếu một hệ thống tạo index tìm kiếm trên nhiều node, không nên để một node chạy JDK cũ và node khác chạy JDK mới mà không so sánh output tokenization đối với dữ liệu đa ngôn ngữ.

Nếu yêu cầu thực chất là phân đoạn từ theo tiếng Việt hoặc một ngôn ngữ cụ thể, cần dùng giải pháp segmentation phù hợp hơn việc dựa vào `\b` một cách mặc định.

### 7.7. Ký tự giống nhau về hình thức nhưng khác mã

Unicode có các ký tự ở script khác nhau trông tương tự nhau (*confusables*). Normalization chuẩn tắc không giải quyết đầy đủ vấn đề giả mạo bằng ký tự nhìn giống nhau. Ví dụ, một số chữ Latin và Cyrillic có hình dạng rất gần nhau nhưng là code point khác.

Đối với username, domain, tên file hoặc định danh nhạy cảm, cần phân tích nguy cơ spoofing, mixed-script và chính sách identifier phù hợp. Không nên coi `\p{L}+` hoặc NFC là bộ lọc bảo mật hoàn chỉnh.

## 8. Xác định lỗi do Unicode data hay do chính sách ứng dụng

Khi quan sát kết quả khác nhau giữa hai môi trường, hãy phân loại nguyên nhân thay vì kết luận ngay “JDK mới đổi regex”.

| Khả năng | Dấu hiệu | Cách xác minh |
|---|---|---|
| Phiên bản Unicode của JDK khác | `Character.getType`, `isLetter` hoặc Unicode regex khác trên một code point | In code point và kết quả phân loại trên hai runtime. |
| Regex flags khác | `\d`, `\w`, `\s`, case-insensitive match khác | In pattern, flags và cấu hình build/runtime. |
| Chuỗi NFC/NFD khác | Văn bản nhìn giống nhau nhưng `equals` hoặc regex khác | In code point sequence và normalization form. |
| Charset giải mã khác | Ký tự vào JVM đã khác trước khi regex xử lý | Kiểm tra bytes nguồn và charset khi decode. |
| Default locale khác | Lowercase, uppercase hoặc phân loại theo locale khác | In locale thực tế và đặt locale tường minh khi cần. |
| Thư viện regex khác | Dự án chuyển giữa `java.util.regex`, ICU hoặc thư viện thứ ba | Xác nhận regex engine, phiên bản và quy tắc property. |
| Dữ liệu nhập thay đổi | Client hoặc hệ điều hành gửi chuỗi khác | Lưu code point của đầu vào mẫu, không chỉ screenshot. |
| Cấu hình khác | Profile bật/tắt Unicode mode hoặc pattern lấy từ config | Kiểm tra effective regex string/flags sau khi parse cấu hình. |

### 8.1. Chẩn đoán bằng code point thay vì nhìn log bằng mắt

Hai chuỗi nhìn gần như giống nhau trong console có thể có mã điểm khác. In giá trị hex sẽ giúp tránh đoán:

```java
static String codePoints(String text) {
    StringBuilder out = new StringBuilder();
    text.codePoints().forEach(cp ->
        out.append(String.format("U+%04X ", cp))
    );
    return out.toString().trim();
}
```

Với chuỗi `"ắ"` và `"a\u0306\u0301"`, kết quả code point sẽ khác nhau dù hình thức hiển thị có thể tương đồng. Khi ghi log dữ liệu thực tế, hãy tuân thủ chính sách bảo vệ dữ liệu cá nhân; trong test có thể dùng bộ ký tự tổng hợp.

### 8.2. Kiểm tra `Pattern.flags()` và nguồn regex

```java
Pattern p = Pattern.compile(
    "\\w+", Pattern.UNICODE_CHARACTER_CLASS
);

System.out.println(p.pattern());
System.out.println(p.flags());
```

Với regex lấy từ YAML/JSON/properties, cần kiểm tra chuỗi thực tế **sau khi parser cấu hình đã giải mã**. Một lớp escaping sai có thể gây khác biệt mà không liên quan đến Unicode version.

## 9. Thiết kế bộ kiểm thử hồi quy khi nâng JDK

Một bộ regression test tốt nên chạy cùng source, cùng dependency và cùng dữ liệu mẫu trên các JDK cần hỗ trợ. Ghi rõ phiên bản runtime để phân biệt khác biệt do JDK với khác biệt do build, locale hoặc dữ liệu.

### 9.1. Chọn dữ liệu đại diện

Đừng chỉ dùng `abc123`. Một ma trận mẫu có thể bao gồm:

| Nhóm | Mẫu | Điều cần kiểm tra |
|---|---|---|
| ASCII | `ABC`, `123`, `_` | Quy tắc ASCII có bị thay đổi do flag không? |
| Tiếng Việt dựng sẵn | `ắ`, `ế`, `ộ` | Letter category và validation. |
| Tiếng Việt decomposed | `a\u0306\u0301` | Normalization, combining marks. |
| Chữ Hán / chữ từ script khác | `中` | Unicode letter và `\w`. |
| Chữ số ngoài ASCII | `١٢٣` | `Character.isDigit` so với `\d` mặc định/Unicode. |
| Supplementary character | U+10400, `😀` | Code point vs UTF-16 code unit, category. |
| Whitespace | U+0020, U+00A0, U+2003, `\t`, `\n` | `isWhitespace`, `strip`, `\s`. |
| Case mapping | `I`, `İ`, `ı` | Locale và Unicode case-insensitive matching. |
| Grapheme đa code point | `👩‍💻` | Đếm hiển thị, tách grapheme, giới hạn độ dài. |
| Ký tự tổ hợp hiếm | Một số mark hoặc script được sản phẩm hỗ trợ | Thuộc tính Unicode theo JDK đích. |

Nên bổ sung dữ liệu thật đã được khử thông tin nhạy cảm, đặc biệt nếu ứng dụng hoạt động trên nhiều ngôn ngữ hoặc thị trường.

### 9.2. Chạy cùng một chương trình chẩn đoán trên hai JDK

Ví dụ chương trình ngắn để quan sát kết quả phân loại và regex:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeBehaviorProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("locale=" + Locale.getDefault());

        int[] points = { 'A', '中', '١', 0x0301, 0x10400, 0x00A0 };
        for (int cp : points) {
            System.out.printf(
                "U+%04X type=%d letter=%s digit=%s whitespace=%s spaceChar=%s%n",
                cp,
                Character.getType(cp),
                Character.isLetter(cp),
                Character.isDigit(cp),
                Character.isWhitespace(cp),
                Character.isSpaceChar(cp)
            );
        }

        String digits = "١٢٣";
        System.out.println("default \\d=" +
            Pattern.compile("\\d+").matcher(digits).matches());
        System.out.println("unicode \\d=" +
            Pattern.compile("\\d+", Pattern.UNICODE_CHARACTER_CLASS)
                .matcher(digits).matches());

        String a = "ắ";
        String b = "a\u0306\u0301";
        System.out.println("rawEqual=" + a.equals(b));
        System.out.println("nfcEqual=" +
            Normalizer.normalize(a, Normalizer.Form.NFC).equals(
                Normalizer.normalize(b, Normalizer.Form.NFC)));
    }
}
```

Biên dịch và chạy trên các runtime trong phạm vi hỗ trợ, ví dụ:

```bash
javac UnicodeBehaviorProbe.java
java UnicodeBehaviorProbe
```

Khi so sánh JDK khác nhau, cần kiểm soát **compiler target** và **runtime target**. Nếu dùng JDK mới để biên dịch nhưng vẫn muốn chạy trên JDK cũ, đặt `--release` phù hợp. Không dùng một class file yêu cầu Java mới hơn rồi suy luận sai khi JVM cũ từ chối nạp nó.

Chương trình minh họa trên chưa đại diện đầy đủ cho mọi data path; hãy mở rộng bằng mẫu đầu vào và regex production thực sự.

### 9.3. Kiểm thử theo hợp đồng, không chỉ snapshot implementation

Với các trường kỹ thuật chỉ nhận ASCII, test nên nêu quy tắc cố định, ví dụ mã gồm `[A-Z0-9]{8}`. Với tên người đa ngôn ngữ, test cần xác định chính sách Unicode rõ ràng thay vì chỉ assert một vài chuỗi tình cờ được chấp nhận.

Khi thay JDK, nếu kết quả mới khác cũ, cần phân loại:

1. Đây có phải một thay đổi được tiêu chuẩn Unicode/JDK dự kiến không?
2. Nó có đúng với hợp đồng sản phẩm không?
3. Dữ liệu đã lưu và dữ liệu gửi bởi client cũ có còn xử lý tương thích không?
4. Có rủi ro bảo mật, uniqueness hoặc thay đổi kết quả tìm kiếm không?
5. Cần cố định quy tắc, nâng phiên bản chính sách hay migration dữ liệu không?

Không phải mọi khác biệt đều là bug cần hoàn nguyên. Một số khác biệt là cải tiến hỗ trợ ngôn ngữ mới. Quyết định nên dựa trên hợp đồng dữ liệu và ảnh hưởng tới consumer.

### 9.4. Kiểm thử nhiều locale và nhiều vùng triển khai

Nếu sản phẩm phụ thuộc vào case conversion, word segmentation hoặc xử lý văn bản theo ngôn ngữ, cần thử những locale đại diện. Dùng `Locale.ROOT` chỉ khi muốn chính sách độc lập với ngôn ngữ; không nên ép mọi văn bản người dùng vào chính sách locale-neutral nếu nghiệp vụ thực sự cần quy tắc ngôn ngữ.

Trong CI, cần ghi locale và các biến môi trường liên quan, vì đổi image nền hoặc cấu hình hệ điều hành có thể tác động đến default locale hoặc charset đồng thời với việc nâng JDK.

## 10. Chính sách thiết kế để hạn chế rủi ro tương thích

### 10.1. Phân biệt quy tắc ASCII và Unicode một cách tường minh

Đối với protocol identifier, mã giao dịch hoặc token máy-máy chỉ chấp nhận ASCII, nên dùng `[A-Za-z0-9]`, `[0-9]` hoặc so sánh code point trong khoảng tường minh. Đối với văn bản tự nhiên, dùng các property Unicode phù hợp thay vì ép người dùng vào regex ASCII không có lý do.

Quan trọng là **ghi rõ lựa chọn**, không để một flag hoặc phiên bản JDK vô tình quyết định chính sách sản phẩm.

### 10.2. Chọn một normalization form theo hợp đồng

Nếu hệ thống cần so sánh canonical-equivalent, hãy chuẩn hóa trước khi kiểm tra uniqueness hoặc tra cứu. Lưu rõ dạng normalization, version chính sách và cách xử lý dữ liệu cũ. Với dữ liệu nhạy cảm cần lưu nguyên văn, có thể giữ bản gốc riêng và tạo khóa chuẩn hóa phục vụ tìm kiếm.

Không mặc định dùng NFKC cho mọi trường; compatibility normalization có thể làm thay đổi ý nghĩa ở một số ngữ cảnh.

### 10.3. Không dựa vào một regex để giải quyết toàn bộ an toàn Unicode

Regex có thể kiểm tra tập ký tự và cấu trúc, nhưng không giải quyết đầy đủ các bài toán như confusable characters, IDN, mixed-script, canonical equivalence, semantic validation và tính duy nhất của identifier. Đối với dữ liệu có yêu cầu bảo mật, cần chính sách chuyên biệt và kiểm thử rủi ro giả mạo.

### 10.4. Giữ regex flags và JDK version trong hồ sơ migration

Khi một regex được sử dụng rộng rãi trong validation, nên lưu:

| Mục | Giá trị cần ghi |
|---|---|
| Regex source | Java literal, config key hay framework annotation. |
| Effective pattern | Chuỗi regex sau khi mọi escaping được xử lý. |
| Flags | `UNICODE_CHARACTER_CLASS`, `CASE_INSENSITIVE`, `UNICODE_CASE`, v.v. |
| Input normalization | NFC/NFD/NFKC/NFKD hoặc không normalize. |
| Runtime | JDK version, vendor và locale liên quan. |
| Allowed examples | Bộ đầu vào hợp lệ và đầu vào phải bị từ chối. |
| Downstream contract | DB collation, API, index, parser và consumer. |

Thông tin này giúp so sánh chính xác trước/sau migration, đặc biệt trong hệ thống microservices có nhiều phiên bản runtime.

### 10.5. Tránh thay đổi nhiều biến trong cùng một thử nghiệm

Khi so sánh hai JDK, nên giữ nguyên input, dependency, regex flags, normalization và locale nếu có thể. Nếu đồng thời nâng framework, đổi regex, đổi hệ điều hành, đổi charset và đổi JDK, một khác biệt validation sẽ rất khó quy nguyên nhân.

Sau khi xác định tác động của JDK, mới đánh giá các thay đổi bổ sung theo các đợt riêng hoặc qua ma trận thử nghiệm có kiểm soát.

## 11. Những hiểu nhầm thường gặp

**“Một `char` là một ký tự Unicode.”** Không phải lúc nào cũng vậy. Một supplementary code point được biểu diễn bằng hai UTF-16 code unit; một grapheme cluster còn có thể gồm nhiều code point.

**“`String.length()` đếm ký tự mà người dùng nhìn thấy.”** Không. Nó đếm UTF-16 code unit. Muốn đếm code point hoặc grapheme phải dùng cơ chế tương ứng.

**“`Character.isDigit` và regex `\d` luôn cùng một tập ký tự.”** Không. Java `Character` phân loại số theo Unicode, còn `\d` mặc định của Java regex có quy tắc khác với `\d` khi bật Unicode character class.

**“`\p{L}` chấp nhận mọi biểu diễn của chữ tiếng Việt có dấu.”** Không nhất thiết. Decomposed combining marks thuộc nhóm `Mark`, không thuộc nhóm `Letter`.

**“`trim`, `strip`, `isWhitespace` và regex `\s` là tương đương.”** Không. Chúng dùng các tập ký tự/quy tắc khác nhau; NO-BREAK SPACE là ví dụ điển hình.

**“Bật Unicode regex chỉ giúp hỗ trợ thêm ngôn ngữ, không thay đổi hợp đồng.”** Không. Tập đầu vào được chấp nhận, cách tách token và word matching có thể đổi.

**“Hai chuỗi nhìn giống nhau luôn bằng nhau.”** Không. `String.equals` không tự normalization; các code point kết hợp có thể khác nhau.

**“`Locale.ROOT` xử lý đúng mọi ngôn ngữ.”** Không. Nó thích hợp cho những thao tác được định nghĩa là locale-independent, nhưng văn bản tự nhiên có thể cần locale riêng.

**“Nâng JDK không thể ảnh hưởng regex nếu source không sửa.”** Có thể ảnh hưởng khi regex hoặc `Character` phụ thuộc bảng thuộc tính Unicode đã được cập nhật. Cần xác minh trên dữ liệu và runtime mục tiêu.

**“NFC và NFKC là như nhau.”** Không. Compatibility normalization có thể gộp thêm các khác biệt; cần chọn theo ý nghĩa dữ liệu.

**“Regex Unicode đủ để chống giả mạo bằng ký tự giống nhau.”** Không. Confusables và mixed-script là những vấn đề riêng cần chính sách bảo mật phù hợp.

## 12. Checklist migration cho Unicode và regex

- [ ] Đã ghi chính xác JDK, vendor, bản cập nhật và locale của môi trường nguồn/đích.
- [ ] Đã xác định các điểm dùng `Character`, `String`, `Normalizer` và `Pattern` trong validation/parse dữ liệu.
- [ ] Đã phân biệt chỗ dùng UTF-16 `char`, code point và grapheme cluster.
- [ ] Đã kiểm tra các regex dùng `\d`, `\w`, `\s`, `\b`, `\p{...}` và flags Unicode.
- [ ] Đã xác nhận ý định dùng ASCII hay Unicode cho mỗi trường dữ liệu.
- [ ] Đã xác định normalization form và thứ tự normalize/validate.
- [ ] Đã thử dữ liệu tiếng Việt dựng sẵn và decomposed, chữ số ngoài ASCII, whitespace đặc biệt và supplementary code points.
- [ ] Đã kiểm tra xử lý case theo locale và case-insensitive regex nếu có.
- [ ] Đã so sánh kết quả trên các JDK cần hỗ trợ với cùng đầu vào và cấu hình.
- [ ] Đã xem tác động đến uniqueness, search index, parser, database collation và downstream consumers.
- [ ] Đã ghi nhận những thay đổi hành vi được chấp nhận và kế hoạch migrate dữ liệu nếu cần.
- [ ] Đã kiểm tra rủi ro confusables/mixed-script cho identifier nhạy cảm.
- [ ] Đã lưu regression test và bộ dữ liệu mẫu để các đợt nâng JDK sau có thể chạy lại.

## 13. Nguồn tài liệu kỹ thuật nên tham khảo

Khi cần xác nhận chính xác một regex property hoặc Unicode version mà JDK hỗ trợ, ưu tiên tài liệu của **đúng JDK mục tiêu** và đặc tả Unicode:

- Javadoc `java.lang.Character`: phân loại category, `isLetter`, `isDigit`, `isWhitespace`, `UnicodeScript`, `UnicodeBlock`.
- Javadoc `java.util.regex.Pattern`: predefined classes, Unicode properties, các flag `UNICODE_CHARACTER_CLASS`, `UNICODE_CASE`, `CASE_INSENSITIVE` và `CANON_EQ`.
- Javadoc `java.text.Normalizer`: NFC, NFD, NFKC, NFKD.
- Java Language Specification và Java Virtual Machine Specification: `char`, Unicode escapes, class file và những quy tắc liên quan.
- Unicode Standard và các phụ lục kỹ thuật liên quan đến normalization, grapheme cluster và thuộc tính ký tự.
- Release notes và migration guide của vendor JDK: thay đổi dữ liệu Unicode, regex engine, locale và hành vi thư viện chuẩn giữa các bản phát hành.

Đừng dùng một bảng Unicode tìm thấy trên Internet rồi mặc định đó là dữ liệu mà JDK đang chạy thực sự dùng. Nếu sự khác biệt ảnh hưởng sản phẩm, cần tái hiện bằng runtime, phiên bản và input cụ thể.

## 14. Kết luận

Unicode trong Java không chỉ là khả năng lưu chữ có dấu. `char` biểu diễn UTF-16 code unit; một code point có thể cần hai code unit; một ký tự hiển thị có thể gồm nhiều code point. Các API `Character`, normalization và regex cung cấp những cách hiểu khác nhau về chữ cái, chữ số, dấu kết hợp, khoảng trắng và ranh giới từ.

Trong Java Advance Compatibility Migration, **bảng thuộc tính Unicode của JDK, các regex flag, normalization và locale** đều có thể ảnh hưởng hành vi mà không tạo lỗi compile hay linkage. Cách phòng ngừa là định nghĩa rõ hợp đồng dữ liệu, chọn ASCII hoặc Unicode một cách chủ đích, đo độ dài theo đúng đơn vị, chuẩn hóa nhất quán và kiểm thử các chuỗi đa ngôn ngữ trên chính runtime mục tiêu. Khi đó nhóm có thể phân biệt một cải tiến Unicode được chấp nhận với một regression cần sửa trước khi triển khai JDK mới.
