# Character, UnicodeScript và dữ liệu Unicode theo JDK (Java 15+)

## 1. Mục tiêu: Java nhận diện Unicode bằng dữ liệu của JDK

`java.lang.Character` là API chuẩn của Java để phân loại chữ cái, chữ số, dấu, tên và các thuộc tính của Unicode code point. Enum lồng `Character.UnicodeScript` cho biết một code point mang **Unicode Script property** nào, chẳng hạn `LATIN`, `CYRILLIC`, `HAN`, `COMMON` hoặc `INHERITED`.

**Kết quả một số API phụ thuộc phiên bản JDK đang chạy.** Mỗi JDK tích hợp một phiên bản Unicode Character Database (UCD). Khi Unicode bổ sung code point hoặc sửa thuộc tính, các kết quả như `Character.isDefined`, `getType`, `isLetter` và `UnicodeScript.of` có thể thay đổi giữa các JDK. Vì vậy, “Java 15” là phiên bản Java, **không phải Unicode 15**: Java 15 dùng Unicode **13.0**.

Để áp dụng chính xác:

1. Hiểu **`char` (đơn vị UTF-16) khác code point `int`**.
2. Dùng `Character.UnicodeScript` để đọc thuộc tính **Script** của từng code point, không đoán ngôn ngữ từ một ký tự.
3. Phân biệt `UnicodeScript`, `UnicodeBlock`, `Character.getType` và `Character.isDefined`.
4. Tra phiên bản Unicode trong tài liệu `Character` của **đúng bản JDK** dùng để chạy ứng dụng.
5. Khi xử lý văn bản Unicode thực tế, tính đến dấu kết hợp, normalization, nhiều code point tạo một ký tự hiển thị và dữ liệu Unicode được cập nhật.

Các API dưới đây vẫn phù hợp với Java hiện đại; ví dụ dùng những cơ chế hỗ trợ từ Java 15 trở đi.

## 2. `char` là đơn vị UTF-16, code point thường được biểu diễn bằng `int`

Một Unicode **code point** được ghi là `U+XXXX`, có giá trị số trong `U+0000`–`U+10FFFF`. `String` Java sử dụng các đơn vị mã UTF-16:

- Code point thuộc **Basic Multilingual Plane** (BMP, nhỏ hơn hoặc bằng `U+FFFF` và không phải surrogate) cần một đơn vị mã 16 bit.
- Code point **bổ sung** (supplementary, lớn hơn `U+FFFF`) cần hai đơn vị mã: high surrogate và low surrogate.
- Một **grapheme cluster** mà mắt người xem là “một ký tự” vẫn có thể chứa nhiều code point, như `e` + dấu sắc kết hợp hoặc một emoji gồm nhiều thành phần.

Do đó, `String.length()` trả về **số đơn vị UTF-16**, không phải số code point hay số ký tự nhìn thấy.

Ví dụ với chữ Deseret `U+10400`:

```java
String deseret = new String(Character.toChars(0x10400));

System.out.println(deseret.length()); // 2
System.out.println(
        deseret.codePointCount(0, deseret.length())
); // 1
System.out.println(
        Character.isLetter(deseret.charAt(0))
); // false: chi la high surrogate
System.out.println(
        Character.isLetter(deseret.codePointAt(0))
); // true: code point U+10400
```

Nếu xử lý Unicode tổng quát, **ưu tiên phương thức `Character` nhận `int`** như `isLetter(int)`, `isDigit(int)` và `getType(int)`. Bản chỉ nhận `char` không thể xử lý một code point bổ sung trong một lần gọi.

### 2.1. Duyệt đúng từng code point

`String.codePoints()` tạo `IntStream` gồm các code point:

```java
String text = "A" + new String(Character.toChars(0x10400));

text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp)
);
```

Đầu ra:

```text
U+0041
U+10400
```

Khi cần biết offset trong `String`:

```java
for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    System.out.printf("offset=%d cp=U+%04X%n", offset, cp);
    offset += Character.charCount(cp);
}
```

`offset` đo theo **UTF-16**; `Character.charCount(cp)` tăng 1 cho BMP và 2 cho code point bổ sung. Ngoài ra có thể dùng `String.offsetByCodePoints` để chuyển đổi vị trí.

**Lưu ý dữ liệu lỗi:** Java `String` có thể chứa surrogate **đơn lẻ** khi dữ liệu UTF-16 không hợp lệ. `codePoints()` giữ đơn vị surrogate đơn lẻ dưới dạng giá trị `int`, không bảo đảm rằng mỗi phần tử là Unicode scalar value. Khi nguồn dữ liệu phải hợp lệ, cần kiểm tra encoding/surrogate và có chính sách xử lý lỗi.

### 2.2. `isValidCodePoint` không có nghĩa “đã được định nghĩa”

`Character.isValidCodePoint(cp)` chỉ kiểm tra phạm vi số mã mà API `Character` chấp nhận. Nó không bảo đảm code point đã được Unicode gán ký tự; nó cũng **không loại bỏ dải surrogate**:

```java
System.out.println(Character.isValidCodePoint(0x0378)); // true
System.out.println(Character.isDefined(0x0378));        // false
System.out.println(Character.isValidCodePoint(0xD800)); // true
System.out.println(Character.isValidCodePoint(0x110000)); // false
```

`U+0378` nằm trong phạm vi mã nhưng chưa được gán một ký tự Unicode. `U+D800` là surrogate code point hợp phạm vi số nhưng **không phải Unicode scalar value độc lập**; phải loại `U+D800`–`U+DFFF` nếu yêu cầu scalar value.

## 3. Các API `Character` thường dùng

| API | Dùng để làm gì? | Điều phải hiểu đúng |
| --- | --- | --- |
| `Character.isLetter(int)` | Kiểm tra thuộc loại chữ cái Unicode. | Có chữ cái không có hoa/thường; dấu kết hợp thường không là letter. |
| `Character.isAlphabetic(int)` | Kiểm tra thuộc tính Alphabetic. | Không hoàn toàn giống `isLetter`; có thêm thuộc tính Unicode liên quan. |
| `Character.isDigit(int)` | Kiểm tra chữ số thập phân Unicode. | Không chỉ là chữ số ASCII `0`–`9`. |
| `Character.getType(int)` | Đọc Unicode General Category. | Ví dụ `UPPERCASE_LETTER`, `NON_SPACING_MARK`, `OTHER_SYMBOL` hoặc `UNASSIGNED`. |
| `Character.isDefined(int)` | Kiểm tra có gán/định nghĩa trong dữ liệu Unicode của JDK. | Không chứng minh font có thể vẽ ký tự. |
| `Character.getName(int)` | Lấy tên Unicode của code point. | Có thể `null` nếu không có tên được xác định. |
| `Character.UnicodeScript.of(int)` | Lấy thuộc tính Script. | Có `COMMON`, `INHERITED`, `UNKNOWN`. |
| `Character.UnicodeBlock.of(int)` | Lấy khối dải mã Unicode. | Khối khác script; một điểm trong block chưa chắc được gán ký tự. |
| `Character.isJavaIdentifierStart/Part(int)` | Kiểm tra hợp lệ ở vị trí định danh Java. | Khác với quy tắc tên tài khoản hoặc security policy. |
| `Character.isUnicodeIdentifierStart/Part(int)` | Kiểm tra theo profile Unicode Identifier của Java. | Không phải bộ lọc chống ký tự nhìn giống nhau. |

**Ví dụ:** chữ `A` có `isLetter == true` và script `LATIN`, chữ `Ж` có `isLetter == true` và script `CYRILLIC`, chữ số `5` có `isDigit == true` nhưng script `COMMON`. Script chỉ là **một thuộc tính trong nhiều thuộc tính**.

## 4. `Character.UnicodeScript` và ba giá trị đặc biệt

Dùng `Character.UnicodeScript.of(int codePoint)` để nhận Script property của **một** code point:

```java
System.out.println(
        Character.UnicodeScript.of('A')
); // LATIN

System.out.println(
        Character.UnicodeScript.of('Ж')
); // CYRILLIC

System.out.println(
        Character.UnicodeScript.of('中')
); // HAN
```

Không phải code point nào cũng gắn với một hệ chữ cụ thể:

- **`COMMON`:** thường gặp ở chữ số, dấu câu, một số ký hiệu và emoji được dùng chung; ví dụ `'5'` hay `U+1F642`.
- **`INHERITED`:** dấu kết hợp (combining mark) có thuộc tính script phụ thuộc ngữ cảnh; ví dụ `U+0301` (COMBINING ACUTE ACCENT).
- **`UNKNOWN`:** chưa có Script cụ thể được gán; thường gặp với code point chưa được định nghĩa, ví dụ `U+0378`.

Với `"e\u0301"`, `e` có script `LATIN` trong khi dấu sắc kết hợp có script `INHERITED`. Điều này không có nghĩa từ tiếng Việt có dấu kết hợp thuộc “hai ngôn ngữ”.

### 4.1. `forName`, alias và `valueOf`

`UnicodeScript` là enum. Bạn có thể lấy hằng bằng tên Unicode/alias hoặc tên enum:

```java
System.out.println(
        Character.UnicodeScript.forName("Latn")
); // LATIN

System.out.println(
        Character.UnicodeScript.forName("latin")
); // LATIN

System.out.println(
        Character.UnicodeScript.valueOf("LATIN")
); // LATIN
```

`forName("Latn")` chấp nhận alias tên Script theo Unicode; `valueOf("LATIN")` yêu cầu tên hằng enum **chính xác**. `valueOf("Latn")` không phải cách lấy alias và sẽ ném `IllegalArgumentException`.

`UnicodeScript.forName` cũng có thể ném `IllegalArgumentException` nếu tên không có trong Unicode data của runtime và `NullPointerException` khi nhận `null`. Khi đọc tên script do người dùng nhập, xử lý lỗi này và không giả định mọi script mới xuất hiện trong mọi JDK.

`UnicodeScript.of` ném `IllegalArgumentException` cho giá trị ngoài phạm vi Unicode, chẳng hạn `0x110000`. Có thể dùng `Character.isValidCodePoint` để kiểm tra dải số đầu vào trước.

### 4.2. `UnicodeScript` không giống `UnicodeBlock`

`UnicodeBlock` nói code point nằm **trong dải vị trí mã** nào; `UnicodeScript` nói về **thuộc tính hệ chữ**. Hai cách phân loại không thay thế nhau:

```java
int cp = 0x0378; // chua gan ky tu Unicode

System.out.println(Character.UnicodeBlock.of(cp));  // GREEK
System.out.println(Character.UnicodeScript.of(cp)); // UNKNOWN
System.out.println(Character.isDefined(cp));        // false
```

`U+0378` nằm trong block `GREEK` nhưng chưa được Unicode gán ký tự nên Script là `UNKNOWN`. Vì vậy, **nằm trong block không đồng nghĩa đã có ký tự hoặc có script tương ứng**.

Một code point `HAN` cũng không đủ để khẳng định đó là tiếng Trung hay tiếng Nhật: nhiều ngôn ngữ cùng sử dụng một số chữ viết. `Script` là thuộc tính code point; nếu cần nhận diện ngôn ngữ, phải dùng phương pháp có ngữ cảnh.

## 5. Chương trình Java hoàn chỉnh và đầu ra kiểm chứng

Lưu nội dung dưới đây trong **`UnicodeScriptDemo.java`**:

```java
import java.text.Normalizer;

public class UnicodeScriptDemo {
    private static void show(String label, int cp) {
        System.out.printf("%s U+%04X script=%s letter=%b defined=%b%n",
                label, cp,
                Character.UnicodeScript.of(cp),
                Character.isLetter(cp), Character.isDefined(cp));
    }

    public static void main(String[] args) {
        String deseret = new String(Character.toChars(0x10400));
        System.out.println("units=" + deseret.length());
        System.out.println("codePoints=" +
                deseret.codePointCount(0, deseret.length()));
        System.out.println("charLetter=" +
                Character.isLetter(deseret.charAt(0)));
        System.out.println("pointLetter=" +
                Character.isLetter(deseret.codePointAt(0)));

        show("Latin", 'A');
        show("Cyrillic", 'Ж');
        show("Han", '中');
        show("Digit", '5');
        show("Combining", 0x0301);
        show("Deseret", 0x10400);
        show("Unassigned", 0x0378);

        System.out.println("alias=" +
                Character.UnicodeScript.forName("Latn"));
        System.out.println("block=" +
                Character.UnicodeBlock.of(0x0378));
        System.out.println("typeUnassigned=" +
                (Character.getType(0x0378) == Character.UNASSIGNED));
        System.out.println("emoji=" +
                Character.UnicodeScript.of(0x1F642));

        String decomposed = "e\u0301";
        String composed = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("decomposedPoints=" +
                decomposed.codePointCount(0, decomposed.length()));
        System.out.println("composedPoints=" +
                composed.codePointCount(0, composed.length()));
        System.out.println("equalBeforeNfc=" +
                decomposed.equals(composed));
        System.out.println("sameAfterNfc=" +
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                composed, Normalizer.Form.NFC)));
    }
}
```

Biên dịch và chạy với JDK 17+ (đoạn mã chỉ sử dụng API đã có trong Java 15):

```bash
javac -encoding UTF-8 UnicodeScriptDemo.java
java UnicodeScriptDemo
```

Đầu ra đã kiểm chứng bằng `javac` và `java` trên **JDK 24**:

```text
units=2
codePoints=1
charLetter=false
pointLetter=true
Latin U+0041 script=LATIN letter=true defined=true
Cyrillic U+0416 script=CYRILLIC letter=true defined=true
Han U+4E2D script=HAN letter=true defined=true
Digit U+0035 script=COMMON letter=false defined=true
Combining U+0301 script=INHERITED letter=false defined=true
Deseret U+10400 script=DESERET letter=true defined=true
Unassigned U+0378 script=UNKNOWN letter=false defined=false
alias=LATIN
block=GREEK
typeUnassigned=true
emoji=COMMON
decomposedPoints=2
composedPoints=1
equalBeforeNfc=false
sameAfterNfc=true
```

Ý nghĩa kết quả:

1. **`units=2`, `codePoints=1`:** một ký tự Deseret bổ sung chiếm hai đơn vị UTF-16.
2. **`charLetter=false`, `pointLetter=true`:** chỉ nhìn high surrogate bằng `charAt(0)` làm sai kết quả phân loại; `codePointAt(0)` cho code point đầy đủ.
3. **`Digit ... COMMON`:** thuộc tính Script khác thuộc tính “có phải chữ số”.
4. **`Combining ... INHERITED`:** dấu kết hợp cần ngữ cảnh và không được mặc định là script Latin.
5. **`Unassigned ... UNKNOWN` và `block=GREEK`:** block chỉ là vùng mã, không bảo đảm ký tự đã gán.
6. **`decomposedPoints=2` và `composedPoints=1`:** chuẩn hóa NFC có thể thay số code point trong một chuỗi được xem là tương đương về mặt Unicode.
7. **`sameAfterNfc=true`:** sau khi chuẩn hóa hai chuỗi theo cùng một quy tắc, `equals` có thể xác nhận chúng giống nhau. `equals` không tự làm normalization.

## 6. Dữ liệu Unicode thay đổi thế nào giữa các JDK?

Các phương thức `Character` dựa vào dữ liệu Unicode của **bản Java runtime**. Dưới đây là các mốc hỗ trợ trong tài liệu chính thức:

| Java/JDK | Phiên bản Unicode của `Character` | Ghi chú |
| --- | --- | --- |
| Java 15 | **13.0** | Nền tảng của module Java 15. |
| Java 17 | **13.0** | Cùng mức Unicode Character data với Java 15. |
| Java 21 | **15.0** | Nhận diện những code point mới hơn Unicode 13. |
| Java 24 và 25 | **16.0** | Dùng UCD của Unicode 16. |
| Java 26 và 27 | **17.0** | Dùng UCD của Unicode 17. |

Đây là những mốc **đã được công bố** để giải thích tính tương thích, không phải quy tắc đoán bản Unicode cho các JDK tương lai. Tra mục *Unicode Conformance* trong JavaDoc `Character` của phiên bản đang triển khai để kiểm tra chính xác.

Khi JDK cập nhật cơ sở dữ liệu Unicode, các kết quả có thể đổi theo dữ liệu mới:

- `Character.isDefined(cp)` từ `false` thành `true` đối với một code point vừa được gán.
- `Character.getType(cp)`, `isLetter(cp)`, `isAlphabetic(cp)` có thể trả thuộc tính mới.
- `UnicodeScript.of(cp)` có thể trả một script cụ thể thay vì `UNKNOWN`.
- Các hằng enum `UnicodeScript` và alias mà `forName` nhận biết có thể tăng khi Unicode có thêm script.
- Những API khác dùng dữ liệu Unicode, như normalization hay regex Unicode property, cũng cần kiểm tra tài liệu của **từng API**.

### 6.1. Ví dụ code point được Unicode bổ sung sau Java 15

`U+1FAE0`, tên **MELTING FACE**, được bổ sung trong **Unicode 14.0**, tức sau Unicode 13.0 mà Java 15 hỗ trợ.

```java
int cp = 0x1FAE0;

System.out.println("JDK=" + Runtime.version().feature());
System.out.println("defined=" + Character.isDefined(cp));
System.out.println("script=" + Character.UnicodeScript.of(cp));
```

Trên **JDK 15** (Unicode 13): `defined=false` và `script=UNKNOWN`. Trên **JDK 24** (Unicode 16): `defined=true` và `script=COMMON`. Sự khác biệt là **dữ liệu đã được cập nhật**, không phải lỗi của `Character`.

Không nhầm `isDefined(cp) == true` với “máy có font để hiển thị glyph”. `Character` chỉ làm việc với dữ liệu ký tự Unicode của runtime; việc vẽ chữ phụ thuộc môi trường font và rendering.

### 6.2. Đảm bảo kết quả ổn định trong dự án

Nếu ứng dụng lưu các quyết định phân loại ký tự, lọc dữ liệu người dùng hoặc kiểm tra tên có ràng buộc chính xác:

1. **Chốt phiên bản JDK** cho các môi trường cần tương thích và lưu thông tin runtime trong logs khi cần truy vết.
2. Kiểm thử code point bổ sung, dấu kết hợp, script mới, code point chưa gán, và văn bản hỗn hợp script **trên đúng JDK đích**.
3. Không hard-code một danh sách script rồi cho rằng nó đầy đủ với mọi bản Unicode tương lai.
4. Khi nghiệp vụ đòi **cùng phiên bản Unicode bất kể JDK**, quản lý riêng một bộ dữ liệu/thư viện Unicode cố định, kiểm thử tính nhất quán.
5. Sau khi nâng cấp runtime, chạy lại các bài test dữ liệu Unicode quan trọng.

`Runtime.version().feature()` cho biết phiên bản tính năng của Java runtime; không có API công khai chuẩn trong `Character` mang tên `getUnicodeVersion()` để trả trực tiếp phiên bản Unicode. Hãy tra JavaDoc của JDK đang chạy.

## 7. Ứng dụng: thống kê các script xuất hiện trong chuỗi

Có thể dùng `UnicodeScript.of` kết hợp `codePoints()` để liệt kê những script **cụ thể** trong chuỗi, rồi bỏ qua `COMMON`, `INHERITED` và `UNKNOWN` nếu bài toán chỉ cần danh sách script xác định.

Ví dụ độc lập **`ScriptSummary.java`**:

```java
import java.util.EnumSet;
import java.util.Set;

public class ScriptSummary {
    static Set<Character.UnicodeScript> specificScripts(String text) {
        EnumSet<Character.UnicodeScript> result =
                EnumSet.noneOf(Character.UnicodeScript.class);

        text.codePoints()
                .mapToObj(Character.UnicodeScript::of)
                .filter(script ->
                        script != Character.UnicodeScript.COMMON
                        && script != Character.UnicodeScript.INHERITED
                        && script != Character.UnicodeScript.UNKNOWN)
                .forEach(result::add);

        return result;
    }

    public static void main(String[] args) {
        System.out.println(specificScripts("Java 15!"));
        System.out.println(specificScripts("AЖ"));
        System.out.println(specificScripts("123!?"));
    }
}
```

Đầu ra theo thứ tự enum:

```text
[LATIN]
[LATIN, CYRILLIC]
[]
```

**Giới hạn cần hiểu rõ:**

- Đây là thống kê **Script property theo code point**, không phải chương trình phát hiện ngôn ngữ.
- `COMMON` / `INHERITED` có thể mang ý nghĩa phụ thuộc ngữ cảnh. Unicode còn có thuộc tính **Script_Extensions** cho các ký tự sử dụng trong nhiều hệ chữ; `UnicodeScript.of` không thay cho phân tích Script_Extensions.
- Tập có nhiều script **không tự động là dữ liệu bất thường**: văn bản hỗn hợp script có thể hợp lệ.
- Để phòng chống giả mạo định danh bằng ký tự nhìn giống nhau (*confusables*) cần chính sách bảo mật Unicode riêng, chẳng hạn dựa trên **UTS #39** và yêu cầu sản phẩm. Một phép kiểm tra `UnicodeScript.of` không đủ để kết luận tên an toàn hay không.

## 8. Dấu tiếng Việt, normalization và nhiều code point

Một chữ có dấu có thể được viết bằng **code point dựng sẵn** hoặc **ký tự nền + dấu kết hợp**:

```java
import java.text.Normalizer;

String precomposed = "\u00E9"; // U+00E9: e co dau sac
String decomposed = "e\u0301"; // e + U+0301

System.out.println(precomposed.equals(decomposed)); // false
System.out.println(
        Normalizer.normalize(precomposed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC))
); // true
```

Kết quả ban đầu `false` vì `String.equals` so sánh dãy đơn vị UTF-16 và hai chuỗi có số code point khác nhau. `Normalizer.Form.NFC` đưa hai giá trị về dạng chuẩn hóa tương thích với phép so sánh canonical phù hợp trong ví dụ.

Khi phân loại chuỗi `"e\u0301"`:

- `e` có `UnicodeScript.LATIN` và là letter.
- Dấu `U+0301` có `UnicodeScript.INHERITED`, thường có category `NON_SPACING_MARK`.
- Nếu lọc chữ cái bằng `Character.isLetter` rồi loại mọi dấu kết hợp, ứng dụng có thể xóa dấu của dữ liệu tiếng Việt dù người dùng nhập văn bản hợp lệ.

NFC **không** tự giải quyết việc xác định ngôn ngữ, chuyển hoa/thường theo locale hoặc chống ký tự confusable. Định nghĩa rõ chính sách normalization cho từng nghiệp vụ; không âm thầm biến đổi dữ liệu nếu yêu cầu bảo toàn nguyên văn.

Với chuyển hoa/thường **cả chuỗi**, các API `String.toUpperCase(Locale)` / `toLowerCase(Locale)` thường phù hợp hơn `Character.toUpperCase(int)` / `toLowerCase(int)` vì có thể xử lý locale, ngữ cảnh và những phép đổi một ký tự thành nhiều ký tự. Tránh dùng bảng chuyển đổi code point đơn giản cho mọi ngôn ngữ.

## 9. Những lỗi hay gặp

| Tình huống | Vì sao sai? | Cách tránh |
| --- | --- | --- |
| Dùng `Character.isLetter(text.charAt(i))` để xử lý mọi Unicode | `charAt` có thể chỉ là nửa surrogate pair. | Duyệt `codePoints()` hoặc `codePointAt`, gọi overload nhận `int`. |
| Dùng `String.length()` làm số ký tự hiển thị | Đo đơn vị UTF-16, chưa tính grapheme cluster. | `codePointCount` cho số code point; thuật toán grapheme khi cần cụm hiển thị. |
| Cho rằng `isValidCodePoint` chứng minh đã có ký tự Unicode | Chỉ kiểm tra phạm vi, vẫn có code point chưa gán và surrogate. | Phân biệt `isDefined`, Unicode scalar và phạm vi số. |
| Dùng `UnicodeBlock` như `UnicodeScript` | Block là dải mã, script là thuộc tính chữ viết. | Chọn đúng loại thuộc tính cần tra. |
| Tự gán `COMMON` hoặc `INHERITED` thành Latin | Các giá trị này có ý nghĩa riêng, thường cần ngữ cảnh. | Giữ nguyên thuộc tính và xử lý ở cấp chuỗi/cụm ký tự nếu cần. |
| Coi script là ngôn ngữ | Một script có thể dùng trong nhiều ngôn ngữ. | Dùng công cụ xác định ngôn ngữ khi nhiệm vụ thật sự yêu cầu. |
| Dùng `UnicodeScript.valueOf("Latn")` | `valueOf` yêu cầu chính xác tên hằng enum. | `UnicodeScript.forName("Latn")` cho alias Unicode. |
| Giả định mọi JDK có cùng Script enum và `isDefined` | Dữ liệu Unicode thay đổi theo release. | Chốt JDK, tra Unicode Conformance, chạy test sau nâng cấp. |
| Dùng `isDefined` để kết luận có glyph/font | API không kiểm tra font. | Kiểm tra môi trường hiển thị độc lập. |
| Coi kiểm tra mixed-script là đủ để bảo vệ username | Có confusable, Script_Extensions, ký tự chung và dấu kết hợp. | Dùng chính sách Unicode security có kiểm thử. |

## 10. Tự kiểm tra

**1. Vì sao `Character.isLetter(deseret.charAt(0))` là `false` còn `Character.isLetter(deseret.codePointAt(0))` là `true`?**

Vì `charAt(0)` chỉ đọc high surrogate của code point `U+10400`; `codePointAt(0)` đọc được cả cặp UTF-16.

**2. Tại sao `UnicodeBlock.of(0x0378)` là `GREEK` còn `UnicodeScript.of(0x0378)` là `UNKNOWN`?**

Vì `U+0378` nằm trong block Greek nhưng chưa được Unicode gán ký tự. Block cho biết vùng mã, script là thuộc tính gắn với code point.

**3. `UnicodeScript.INHERITED` của dấu sắc có nghĩa chuỗi `"e\u0301"` không phải văn bản Latin?**

Không. Đây là thuộc tính của **dấu kết hợp**; cần xét ký tự nền, chuẩn hóa và ngữ cảnh.

**4. Vì sao `Character.isDefined(0x1FAE0)` khác nhau giữa JDK 15 và JDK 24?**

Vì Unicode 14.0 mới bổ sung code point này, trong khi JDK 15 dùng Unicode 13.0, JDK 24 dùng Unicode 16.0.

**5. Khi nào dùng `forName("Latn")` thay vì `valueOf("LATIN")`?**

Dùng `forName` khi nhận tên/alias script Unicode; dùng `valueOf` khi bạn đã có đúng tên hằng enum.

## Ghi nhớ

- **`char` là 16-bit UTF-16 code unit; `int` có thể mang một Unicode code point đầy đủ.** Không bỏ qua surrogate pair.
- **`UnicodeScript` khác `UnicodeBlock`, `getType` và `isDefined`.** Cần xác định chính xác thuộc tính mình đang hỏi.
- **`COMMON`, `INHERITED` và `UNKNOWN` đều là kết quả có ý nghĩa**, không phải lỗi API.
- **Dữ liệu Unicode của `Character` phụ thuộc bản JDK.** Java 15 hỗ trợ Unicode 13, còn những bản JDK mới hơn đã cập nhật chuẩn.
- **Script không phải ngôn ngữ; normalization, grapheme và bảo mật định danh là các vấn đề khác**, cần quy tắc riêng.

### Tài liệu còn áp dụng

- [Oracle Java 15 – Character](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/Character.html) — dữ liệu Unicode 13 của Java 15, UTF-16 và API Character.
- [Oracle Java 27 – Character](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html) — Unicode Conformance và dữ liệu Character ở JDK mới.
- [Oracle Java 27 – Character.UnicodeScript](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.UnicodeScript.html) — Script, `of`, `forName`, các giá trị enum.
- [Oracle Java 27 – Character.UnicodeBlock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.UnicodeBlock.html) — định nghĩa Unicode block.
- [Oracle Java – Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html) — NFC và các dạng chuẩn hóa Unicode.
- [Unicode Standard Annex #24 – Script](https://www.unicode.org/reports/tr24/) — Script và Script_Extensions.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/) — cơ chế bảo mật Unicode chuyên biệt.
