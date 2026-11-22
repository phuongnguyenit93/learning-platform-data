# Chữ số, chữ cái và thuộc tính Unicode qua Character

Trong Java, `java.lang.Character` không chỉ xử lý các chữ cái Latin như `A–Z` hay các chữ số ASCII như `0–9`. Nó cung cấp nhiều API để hỏi một **ký tự Unicode** thuộc loại nào: có phải **chữ cái**, **chữ số thập phân**, **ký tự có giá trị số**, **chữ hoa/chữ thường**, **dấu kết hợp**, **khoảng trắng**, **ký tự thuộc hệ chữ viết nào**, hoặc có những **thuộc tính Unicode** nào khác.

Điểm cần nắm từ đầu: **ký tự Java kiểu `char` không đồng nghĩa với một Unicode code point**, và **“có giá trị số” không đồng nghĩa “là chữ số thập phân”**. Một ký tự số La Mã có thể được xem là alphabetic nhưng không phải letter/digit theo nghĩa của `isLetter` và `isDigit`. Một chữ cái ngoài Basic Multilingual Plane (BMP) cần **hai `char` UTF-16**, nhưng chỉ là **một Unicode code point**.

Bài học này sử dụng Java 17+ để phân biệt:
- `Character.isDigit`, `isLetter`, `isLetterOrDigit` và `isAlphabetic`;
- `Character.digit` và `getNumericValue`;
- `Character.getType`, các category, `UnicodeScript` và `UnicodeBlock`;
- `char` so với code point `int`;
- chữ hoa/chữ thường, dấu kết hợp, khoảng trắng và các giới hạn khi kiểm tra dữ liệu địa phương hóa.

Mục tiêu là áp dụng đúng trong **Java core - localization**, đồng thời tránh những giả định ASCII hoặc giả định rằng chỉ một lệnh `Character.isLetterOrDigit` đủ cho mọi yêu cầu xác thực văn bản.

## 1. Ba cấp độ: đơn vị UTF-16, code point và ký tự người dùng nhìn thấy

Java lưu nội dung `String` dưới dạng **UTF-16**. Ba khái niệm cần phân biệt:

| Cấp độ | Ý nghĩa | API thường gặp |
| --- | --- | --- |
| **Code unit** | Một đơn vị UTF-16 16 bit, kiểu `char` | `charAt`, `length` |
| **Code point** | Một giá trị mã Unicode, kiểu `int` | `codePointAt`, `codePoints`, `Character.isLetter(int)` |
| **Grapheme cluster** | Một cụm ký tự mà người dùng thường cảm nhận là một đơn vị | Cần cơ chế phân đoạn văn bản, không chỉ `charAt` |

Ví dụ chữ **é** có thể được biểu diễn bằng:
- Một code point **U+00E9** (LATIN SMALL LETTER E WITH ACUTE).
- Hai code point **U+0065 + U+0301** (chữ e và COMBINING ACUTE ACCENT).

Hai biểu diễn có thể nhìn giống nhau nhưng **số code point khác nhau**. Chúng chưa chắc bằng nhau theo `String.equals` nếu chưa chuẩn hóa.

Ngoài ra, chữ **Deseret U+10400** ở ngoài BMP được mã hóa bằng **một surrogate pair**, tức **hai `char`**. Vì vậy `String.length()` có thể là 2 trong khi `codePointCount(...)` là 1.

### Quy tắc thực hành

Khi phân loại ký tự Unicode, ưu tiên overload nhận **`int codePoint`**:

~~~java
Character.isLetter(codePoint);
Character.isDigit(codePoint);
Character.getType(codePoint);
~~~

Khi lặp qua một chuỗi Unicode tùy ý, ưu tiên `String.codePoints()` hoặc duyệt bằng `codePointAt` và `Character.charCount`. Không mặc định mỗi lần `charAt(i)` lấy được một ký tự hoàn chỉnh.

## 2. `Character.isDigit`: chữ số thập phân Unicode

`Character.isDigit(int codePoint)` trả `true` nếu code point thuộc Unicode general category **DECIMAL_DIGIT_NUMBER (Nd)**.

Điều đó bao gồm nhiều hệ chữ số thập phân, không chỉ ASCII:

| Unicode code point | Ví dụ | `isDigit` | `getNumericValue` |
| --- | --- | --- | ---: |
| U+0035 | `5` ASCII | `true` | 5 |
| U+0665 | `٥` Arabic-Indic | `true` | 5 |
| U+096B | `५` Devanagari | `true` | 5 |
| U+FF15 | `５` Fullwidth | `true` | 5 |
| U+216B | `Ⅻ` số La Mã 12 | `false` | 12 |
| U+00B2 | `²` số mũ 2 | `false` | 2 |

**Quan trọng:** `isDigit` không có nghĩa “ký tự chỉ được phép trong số điện thoại/mã OTP/ID của sản phẩm”. Nó có nghĩa **là chữ số thập phân theo dữ liệu Unicode mà JDK sử dụng**.

Ví dụ runnable **`UnicodeDigitDemo.java`**:

~~~java
public class UnicodeDigitDemo {
    public static void main(String[] args) {
        int[] points = {
                0x0035,  // ASCII digit five
                0x0665,  // Arabic-Indic digit five
                0x096B,  // Devanagari digit five
                0xFF15,  // Fullwidth digit five
                0x216B,  // Roman numeral twelve
                0x00B2   // Superscript two
        };

        for (int cp : points) {
            System.out.printf(
                    "U+%04X digit=%s numeric=%d%n",
                    cp,
                    Character.isDigit(cp),
                    Character.getNumericValue(cp)
            );
        }
    }
}
~~~

~~~bash
javac UnicodeDigitDemo.java
java UnicodeDigitDemo
~~~

Kết quả:

~~~text
U+0035 digit=true numeric=5
U+0665 digit=true numeric=5
U+096B digit=true numeric=5
U+FF15 digit=true numeric=5
U+216B digit=false numeric=12
U+00B2 digit=false numeric=2
~~~

Ở hai dòng cuối, các ký tự có **giá trị số** nhưng không thuộc category **Nd**, nên `isDigit` vẫn là `false`. Nếu chỉ cần chữ số ASCII cho một giao thức cố định, điều kiện đúng thường là `cp >= '0' && cp <= '9'`, không phải `Character.isDigit(cp)`.

## 3. `Character.isLetter`: chữ cái thuộc Unicode

`Character.isLetter(int)` trả `true` nếu code point thuộc một trong những Unicode category sau:

- `UPPERCASE_LETTER (Lu)`;
- `LOWERCASE_LETTER (Ll)`;
- `TITLECASE_LETTER (Lt)`;
- `MODIFIER_LETTER (Lm)`;
- `OTHER_LETTER (Lo)`.

Vì vậy “letter” không chỉ là chữ Latin. Ví dụ chữ Hán `中` (U+4E2D), nhiều chữ thuộc hệ Ả Rập, Hy Lạp, Cyrillic, v.v. đều có thể được xác định là chữ cái.

Một số code point trông giống chữ hay biểu tượng chữ **không thuộc nhóm letter** theo quy tắc này. Chẳng hạn số La Mã `Ⅻ` (U+216B) thuộc **LETTER_NUMBER**, không phải năm category letter vừa liệt kê. Nó được `Character.isAlphabetic` chấp nhận nhưng `isLetter` không chấp nhận.

Ví dụ **`UnicodeLetterDemo.java`**:

~~~java
public class UnicodeLetterDemo {
    public static void main(String[] args) {
        int latin = 'A';
        int han = 0x4E2D;
        int romanNumber = 0x216B;
        int combiningAccent = 0x0301;

        System.out.println(Character.isLetter(latin));
        System.out.println(Character.isLetter(han));
        System.out.println(Character.isLetter(romanNumber));
        System.out.println(Character.isLetter(combiningAccent));
    }
}
~~~

~~~bash
javac UnicodeLetterDemo.java
java UnicodeLetterDemo
~~~

Kết quả:

~~~text
true
true
false
false
~~~

Dấu kết hợp U+0301 tự nó không phải letter. Nhưng một tên chứa **chữ e + combining acute accent** vẫn có thể là tên người hợp lệ. Điều này dẫn tới giới hạn quan trọng khi xác thực chuỗi: **“mọi code point phải là letter” có thể loại bỏ những văn bản tự nhiên đúng**.

## 4. `isAlphabetic` và `isLetter` không giống nhau

`Character.isAlphabetic(int)` xét thuộc tính Unicode **Alphabetic**. Nó bao gồm các chữ cái thuộc những category letter, đồng thời có thể chấp nhận một số code point khác được Unicode đánh dấu là alphabetic.

Vì vậy, hai biểu thức này **không luôn tương đương**:

~~~java
Character.isLetter(cp);
Character.isAlphabetic(cp);
~~~

Trường hợp minh họa U+216B (`Ⅻ`):

~~~text
isLetter   = false
isAlphabetic = true
~~~

Mặc dù đây là một **số La Mã**, Unicode vẫn coi nó có thuộc tính alphabetic. `isAlphabetic` không có nghĩa “chắc chắn là chữ cái trong bảng chữ cái Latin”; tên gọi API chỉ nói nó tuân theo một thuộc tính Unicode cụ thể.

Tạo **`AlphabeticDifferenceDemo.java`**:

~~~java
public class AlphabeticDifferenceDemo {
    public static void main(String[] args) {
        int romanTwelve = 0x216B;

        System.out.println(Character.isLetter(romanTwelve));
        System.out.println(Character.isAlphabetic(romanTwelve));
        System.out.println(Character.isLetterOrDigit(romanTwelve));
        System.out.println(Character.getNumericValue(romanTwelve));
    }
}
~~~

~~~bash
javac AlphabeticDifferenceDemo.java
java AlphabeticDifferenceDemo
~~~

Kết quả:

~~~text
false
true
false
12
~~~

Khi tạo bộ lọc đầu vào, hãy chọn thuộc tính **khớp chính sách sản phẩm**, không chọn `isAlphabetic` chỉ vì tên nghe có vẻ rộng hoặc an toàn hơn.

## 5. `isLetterOrDigit`: phép hợp, không phải “mọi ký tự chữ hoặc có số”

`Character.isLetterOrDigit(cp)` tương đương về ý nghĩa với **`isLetter(cp) || isDigit(cp)`**. Nó không tự bao gồm mọi category number hay các dấu kết hợp.

Ví dụ:

| Code point | `isLetter` | `isDigit` | `isLetterOrDigit` |
| --- | --- | --- | --- |
| `A` | true | false | true |
| `中` | true | false | true |
| `٥` | false | true | true |
| `Ⅻ` | false | false | false |
| `²` | false | false | false |
| U+0301 combining accent | false | false | false |
| Emoji U+1F600 | false | false | false |

Một ứng dụng cho phép **tên người** không thể chỉ dùng `isLetterOrDigit` rồi coi đã đúng: tên có thể chứa khoảng trắng, gạch nối, apostrophe, dấu kết hợp, ký tự khác theo văn hóa, v.v. Ngược lại, mã kỹ thuật có thể cần **ASCII-only**, và `isLetterOrDigit` lại quá rộng vì chấp nhận nhiều hệ chữ viết.

Cần xác định trước **mục đích dữ liệu**: người dùng nhập nội dung tự nhiên, định danh kỹ thuật, số thập phân, mã xác thực hay dữ liệu từ OCR. Mỗi loại cần chính sách khác nhau.

## 6. `getNumericValue`: giá trị số của một code point

`Character.getNumericValue(cp)` cố gắng lấy **giá trị số nguyên** gắn với code point theo Unicode. Nó có thể trả:

- **Số nguyên không âm**, ví dụ `5` hoặc `12`;
- **`-1`** nếu không có giá trị số được hỗ trợ;
- **`-2`** nếu có giá trị số nhưng **không thể biểu diễn bằng một `int` không âm** theo hợp đồng API, chẳng hạn một phân số.

Vì vậy `getNumericValue` **không phải** công cụ kiểm tra “có phải chữ số thập phân” và cũng không thay thế parser số.

Ví dụ **`NumericValueDemo.java`**:

~~~java
public class NumericValueDemo {
    public static void main(String[] args) {
        System.out.println(Character.getNumericValue('7'));
        System.out.println(Character.getNumericValue(0x216B));
        System.out.println(Character.getNumericValue(0x00B2));
        System.out.println(Character.getNumericValue(0x00BD));
        System.out.println(Character.getNumericValue('@'));
    }
}
~~~

~~~bash
javac NumericValueDemo.java
java NumericValueDemo
~~~

Kết quả:

~~~text
7
12
2
-2
-1
~~~

U+00BD là ký tự **½**, có giá trị số phân số, nên trả `-2`. Dùng `getNumericValue` để hiểu một thuộc tính Unicode; nếu cần đọc một biểu thức như `"12.5"` hoặc `"Ⅻ"` theo quy tắc nghiệp vụ, cần parser chuyên dụng và chính sách đầu vào cụ thể.

**Cảnh báo với input số:** `getNumericValue('A')` có thể trả giá trị 10 theo bảng ký số mở rộng, nên **không** được xem mọi giá trị số không âm là bằng chứng ký tự ban đầu là chữ số hợp lệ cho số thập phân.

## 7. `Character.digit` và cơ số

`Character.digit(codePoint, radix)` hỏi code point có thể biểu diễn **một chữ số theo cơ số được yêu cầu** hay không, rồi trả giá trị số hợp lệ hoặc `-1`.

Ví dụ:

~~~java
Character.digit('9', 10);       // 9
Character.digit('F', 16);       // 15
Character.digit('G', 16);       // -1
Character.digit(0x0665, 10);   // 5
Character.digit(0x216B, 10);   // -1
~~~

Đây là snippet đặt trong phương thức, không phải chương trình độc lập.

Một ví dụ runnable:

**`DigitRadixDemo.java`**

~~~java
public class DigitRadixDemo {
    public static void main(String[] args) {
        System.out.println(Character.digit('F', 16));
        System.out.println(Character.digit('G', 16));
        System.out.println(Character.digit(0x0665, 10));
        System.out.println(Character.digit(0x216B, 10));
    }
}
~~~

~~~bash
javac DigitRadixDemo.java
java DigitRadixDemo
~~~

Kết quả:

~~~text
15
-1
5
-1
~~~

Với các cơ số được hỗ trợ, chữ Latin `A–Z` có thể đóng vai trò chữ số giá trị 10–35, nhưng việc cho phép chúng ở vị trí chữ số phụ thuộc `radix`. Không dùng `getNumericValue` rồi tự giả định mọi ký tự có numeric value đều thuộc cú pháp số của một cơ số.

`Integer.parseInt` và các parser số khác có quy tắc riêng. Với Java, một số chữ số Unicode dạng Nd có thể được parser số nguyên chấp nhận, nên yêu cầu “chỉ số ASCII” phải được xác thực **trước** khi parse.

## 8. Java parser có thể nhận chữ số không phải ASCII

Ví dụ thay vì gõ trực tiếp các ký tự có khả năng bị lỗi encoding trên console, ta dựng chuỗi bằng code point U+0661 và U+0662, tương ứng hai chữ số Arabic-Indic có giá trị `1` và `2`.

Tạo **`UnicodeParseDemo.java`**:

~~~java
public class UnicodeParseDemo {
    public static void main(String[] args) {
        String arabicDigits = new String(
                new int[]{0x0661, 0x0662}, 0, 2);

        System.out.println(arabicDigits.codePointCount(
                0, arabicDigits.length()));
        System.out.println(Integer.parseInt(arabicDigits));

        boolean onlyAscii = arabicDigits.codePoints()
                .allMatch(cp -> cp >= '0' && cp <= '9');

        System.out.println(onlyAscii);
    }
}
~~~

~~~bash
javac UnicodeParseDemo.java
java UnicodeParseDemo
~~~

Kết quả:

~~~text
2
12
false
~~~

**Diễn giải:** Parser có thể hiểu những chữ số đó thành số nguyên `12`, nhưng chuỗi đầu vào không chứa chữ số ASCII. Nếu API nhận mã OTP, mã hóa đơn hoặc giá trị có định dạng giao thức ASCII bắt buộc, phải kiểm tra **ASCII policy**, không chỉ gọi `parseInt` thành công.

Ngược lại, trong giao diện đa ngôn ngữ hướng tới người dùng, việc chấp nhận chữ số địa phương có thể là yêu cầu đúng. Phải xác định đó là quyết định của sản phẩm, không suy đoán từ một API duy nhất.

## 9. Unicode general category qua `Character.getType`

`Character.getType(codePoint)` trả về **mã số int** của general category Unicode của code point, tương ứng những hằng như:

- `Character.UPPERCASE_LETTER`;
- `Character.LOWERCASE_LETTER`;
- `Character.OTHER_LETTER`;
- `Character.DECIMAL_DIGIT_NUMBER`;
- `Character.LETTER_NUMBER`;
- `Character.OTHER_NUMBER`;
- `Character.NON_SPACING_MARK`;
- `Character.SPACE_SEPARATOR`;
- `Character.OTHER_SYMBOL`;
- `Character.FORMAT`;
- `Character.UNASSIGNED`.

Đây là category Unicode, không phải thứ tự xếp hạng hay giá trị số của ký tự. Ví dụ `getType('5')` trả category `DECIMAL_DIGIT_NUMBER`, chứ không trả số 5. Muốn giá trị của chữ số, dùng `digit` hoặc `getNumericValue`.

Tạo **`UnicodeCategoryDemo.java`**:

~~~java
public class UnicodeCategoryDemo {
    public static void main(String[] args) {
        int asciiFive = '5';
        int roman = 0x216B;
        int superscript = 0x00B2;
        int accent = 0x0301;

        System.out.println(Character.getType(asciiFive)
                == Character.DECIMAL_DIGIT_NUMBER);
        System.out.println(Character.getType(roman)
                == Character.LETTER_NUMBER);
        System.out.println(Character.getType(superscript)
                == Character.OTHER_NUMBER);
        System.out.println(Character.getType(accent)
                == Character.NON_SPACING_MARK);
    }
}
~~~

~~~bash
javac UnicodeCategoryDemo.java
java UnicodeCategoryDemo
~~~

Kết quả:

~~~text
true
true
true
true
~~~

General category thường hữu ích hơn một điều kiện Boolean khi ứng dụng cần giải thích **tại sao một code point được chấp nhận hoặc bị từ chối**. Ví dụ một bộ lọc tên riêng có thể chủ động cho phép letter, combining mark và một số dấu câu, thay vì chỉ cho phép `isLetter`.

### Category không phải luật ngữ pháp của một ngôn ngữ

Không có general category nào nói rằng một từ tiếng Việt, tiếng Pháp hay tiếng Ả Rập “hợp lệ về ngữ pháp”. Category là thuộc tính Unicode của **code point riêng lẻ**, không có toàn bộ ngữ cảnh từ/câu.

Đối với kiểm tra chính tả, phân đoạn từ, xử lý văn bản hai chiều hoặc plural, cần cơ chế ngôn ngữ chuyên biệt hơn `Character.getType`.

## 10. `UnicodeScript` và `UnicodeBlock`: hai khái niệm khác nhau

Java cung cấp:

~~~java
Character.UnicodeScript.of(codePoint);
Character.UnicodeBlock.of(codePoint);
~~~

- **`UnicodeScript`** phản ánh thuộc tính script của code point, ví dụ `LATIN`, `CYRILLIC`, `ARABIC`, `HAN`, `DEVANAGARI`.
- **`UnicodeBlock`** phản ánh **khối mã Unicode**, một dải mã được đặt tên trong bảng mã.

Script và block không đồng nghĩa. Một script có thể trải trên nhiều block, và một block có thể chứa những ký tự với script `COMMON`, `INHERITED` hoặc những cách phân loại khác.

Ví dụ runnable **`UnicodeScriptDemo.java`**:

~~~java
public class UnicodeScriptDemo {
    public static void main(String[] args) {
        int[] points = {'A', 0x4E2D, 0x0665, 0x0301};

        for (int cp : points) {
            System.out.printf("U+%04X script=%s%n",
                    cp, Character.UnicodeScript.of(cp));
        }
    }
}
~~~

~~~bash
javac UnicodeScriptDemo.java
java UnicodeScriptDemo
~~~

Kết quả với bộ Unicode được JDK 17 hỗ trợ:

~~~text
U+0041 script=LATIN
U+4E2D script=HAN
U+0665 script=ARABIC
U+0301 script=INHERITED
~~~

Dấu kết hợp U+0301 có script `INHERITED` vì nó phụ thuộc ngữ cảnh ký tự đi cùng. Các chữ số hoặc dấu câu có thể mang script `COMMON`, `ARABIC` hoặc script khác tùy thuộc chính code point.

**Không dùng `UnicodeBlock` như bộ kiểm tra “có phải chữ Latin”**. Cũng không kết luận một chuỗi toàn chữ thuộc cùng script là chắc chắn an toàn hay có nghĩa: kiểm tra tên định danh chống nhầm lẫn ký tự (*confusables*) cần nhiều quy tắc hơn.

## 11. Code point ngoài BMP: tại sao overload `char` có thể sai?

Các API `Character` có nhiều overload:

~~~java
Character.isLetter(char ch);
Character.isLetter(int codePoint);
~~~

`char` chỉ chứa một đơn vị UTF-16. Với ký tự ngoài BMP, một code point được mã hóa bởi **hai surrogate code units**, nên mỗi `char` riêng lẻ không phải toàn bộ ký tự.

Ví dụ chữ Deseret U+10400:

**`SupplementaryLetterDemo.java`**

~~~java
public class SupplementaryLetterDemo {
    public static void main(String[] args) {
        int codePoint = 0x10400;
        String text = new String(Character.toChars(codePoint));

        System.out.println(Character.charCount(codePoint));
        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));

        System.out.println(Character.isLetter(text.charAt(0)));
        System.out.println(Character.isLetter(text.codePointAt(0)));
    }
}
~~~

~~~bash
javac SupplementaryLetterDemo.java
java SupplementaryLetterDemo
~~~

Kết quả:

~~~text
2
2
1
false
true
~~~

Dòng `isLetter(text.charAt(0))` chỉ nhận **high surrogate**, không phải chữ Deseret thực sự. Dòng `isLetter(text.codePointAt(0))` nhận đúng U+10400 nên trả `true`.

Khi chương trình cần hỗ trợ mọi hệ chữ viết Unicode, việc lặp qua `String` bằng `for (char ch : text.toCharArray())` rồi `isLetter(ch)` có thể vô tình loại bỏ chữ cái ngoài BMP. Dùng code point để kiểm tra.

### Lặp qua code point

Đây là ví dụ snippet trong một method:

~~~java
String text = new String(Character.toChars(0x10400)) + "A";

text.codePoints().forEach(cp -> {
    System.out.println(Character.isLetter(cp));
});
~~~

Kết quả:

~~~text
true
true
~~~

Hoặc duyệt thủ công:

~~~java
for (int i = 0; i < text.length();) {
    int cp = text.codePointAt(i);
    // Xử lý một code point hoàn chỉnh tại đây.
    i += Character.charCount(cp);
}
~~~

Đoạn thứ hai là snippet có biến `text` đã khai báo. Hãy nhớ **chỉ số `i` vẫn là chỉ số UTF-16 code unit**, vì `String.codePointAt` nhận vị trí theo `char`; còn `cp` là một code point.

## 12. `String.length()` không đo số “ký tự người dùng thấy”

Với `String` trong Java:

- `length()` trả số **UTF-16 code units**;
- `codePointCount(0, length())` đếm **Unicode code points**;
- cả hai **không nhất thiết bằng số grapheme clusters**.

Ví dụ một chữ `e` theo sau dấu kết hợp U+0301 có hai code point, nhưng nhiều giao diện xem đó như **một ký tự hiển thị**. Emoji có thể bao gồm nhiều code point nối bằng zero-width joiner; cắt giữa cụm đó có thể phá vỡ hình thức hiển thị.

Do đó:
- Để phân loại code point, dùng `Character` + `codePoints()`.
- Để giới hạn số byte khi gửi dữ liệu, đo byte sau khi encode, ví dụ UTF-8.
- Để giới hạn “số ký tự người dùng nhìn thấy”, cần thuật toán **grapheme segmentation** theo chuẩn phù hợp, không chỉ `String.length()` hay `codePointCount()`.

Không nên gộp ba quy tắc đếm thành một trong các màn hình nhập liệu đa ngôn ngữ.

## 13. Chữ hoa, chữ thường và Unicode case mapping

`Character` có những phương thức:

~~~java
Character.isUpperCase(cp);
Character.isLowerCase(cp);
Character.isTitleCase(cp);
Character.toUpperCase(cp);
Character.toLowerCase(cp);
Character.toTitleCase(cp);
~~~

Chúng xử lý hoặc nhận diện thuộc tính của **một code point**. Trong khi đó, chuyển toàn bộ `String` theo ngôn ngữ người dùng có thể cần **case mapping có ngữ cảnh và locale**, thậm chí sinh ra nhiều code point.

Ví dụ chữ Latin `I` thường được đổi thành `i` trong ánh xạ đơn giản; nhưng trong tiếng Thổ Nhĩ Kỳ, chữ hoa `I` đổi thành **ı** (dotless i).

Ví dụ **`LocaleCaseDemo.java`**:

~~~java
import java.util.Locale;

public class LocaleCaseDemo {
    public static void main(String[] args) {
        String turkishLower =
                "I".toLowerCase(Locale.forLanguageTag("tr-TR"));

        System.out.println(Character.toLowerCase('I') == 'i');
        System.out.println(turkishLower.codePointAt(0) == 0x0131);

        String sharpS = new String(Character.toChars(0x00DF));
        String upperWord = sharpS.toUpperCase(Locale.GERMAN);

        System.out.println(upperWord.equals("SS"));
        System.out.println(Character.toUpperCase(0x00DF) == 0x00DF);
    }
}
~~~

~~~bash
javac LocaleCaseDemo.java
java LocaleCaseDemo
~~~

Kết quả trên Java 17:

~~~text
true
true
true
true
~~~

Đối với chữ `ß`, `String.toUpperCase(Locale.GERMAN)` có thể mở rộng thành **hai chữ S**, còn `Character.toUpperCase(int)` không thể biểu diễn phép mở rộng thành hai code point bằng một `int`.

**Vì vậy:**
- Dùng `Character` cho phép kiểm tra/ánh xạ một code point khi yêu cầu đó là đúng.
- Dùng `String.toLowerCase(locale)` / `toUpperCase(locale)` cho chuyển đổi chuỗi có ngữ nghĩa ngôn ngữ.
- Với mã giao thức hoặc khóa kỹ thuật cần chuẩn hóa chữ hoa/thường không phụ thuộc người dùng, cân nhắc `Locale.ROOT`.
- Không coi chuyển đổi case là phép so sánh Unicode an toàn cho mọi định danh; còn có vấn đề normalization và các dạng tương đương.

## 14. Dấu kết hợp và `Normalizer`

Một tiếng Việt hoặc tiếng Pháp có dấu có thể được biểu diễn bằng code point dựng sẵn hoặc **chuỗi base letter + combining mark**. Phương thức `Character.isLetter` áp dụng **riêng từng code point**, nên sẽ trả `false` với dấu kết hợp `NON_SPACING_MARK` dù toàn bộ cụm là một chữ hợp lệ.

Ví dụ:

**`UnicodeNormalizationDemo.java`**

~~~java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String decomposed = new String(new int[]{
                0x0065, 0x0301
        }, 0, 2);

        String composed = new String(new int[]{
                0x00E9
        }, 0, 1);

        System.out.println(decomposed.equals(composed));

        String left = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                composed, Normalizer.Form.NFC);

        System.out.println(left.equals(right));
        System.out.println(Character.isLetter(0x0301));
        System.out.println(
                Character.getType(0x0301)
                        == Character.NON_SPACING_MARK);
    }
}
~~~

~~~bash
javac UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Kết quả:

~~~text
false
true
false
true
~~~

`Normalizer.Form.NFC` thực hiện chuẩn hóa canonical composition phù hợp Unicode; nó **không dịch ngôn ngữ** và không tự quyết định một tên là hợp lệ. Các dạng NFD, NFKC, NFKD có mục đích khác nhau, đặc biệt compatibility normalization có thể làm thay đổi cách diễn giải những ký tự trình bày.

**Hệ quả thực tiễn:** Nếu bộ kiểm tra tên chỉ chấp nhận `Character.isLetter` cho từng code point, nó có thể chấp nhận `é` dựng sẵn nhưng từ chối `e + U+0301` mặc dù hai chuỗi nhìn giống nhau. Cần thiết kế chính sách Unicode rõ ràng và xét normalization/combining marks khi phù hợp.

## 15. Khoảng trắng: `isWhitespace` và `isSpaceChar`

Trong văn bản địa phương hóa, khoảng trắng không chỉ là `U+0020`. Java có:

- `Character.isWhitespace(cp)`;
- `Character.isSpaceChar(cp)`.

Hai phương thức **không có cùng tập kết quả**. Chẳng hạn U+00A0 **NO-BREAK SPACE** được xem là **space character** nhưng `isWhitespace` trả `false`.

Tạo **`UnicodeSpaceDemo.java`**:

~~~java
public class UnicodeSpaceDemo {
    public static void main(String[] args) {
        int ordinarySpace = 0x0020;
        int noBreakSpace = 0x00A0;

        System.out.println(Character.isWhitespace(ordinarySpace));
        System.out.println(Character.isSpaceChar(ordinarySpace));
        System.out.println(Character.isWhitespace(noBreakSpace));
        System.out.println(Character.isSpaceChar(noBreakSpace));
    }
}
~~~

~~~bash
javac UnicodeSpaceDemo.java
java UnicodeSpaceDemo
~~~

Kết quả:

~~~text
true
true
false
true
~~~

Một bộ lọc chỉ dùng `String.trim()` hoặc `Character.isWhitespace` có thể không xử lý tất cả loại khoảng trắng Unicode mà ứng dụng cần. Ngược lại, xóa mọi khoảng trắng Unicode cũng có thể phá cách trình bày hợp lệ, ví dụ số tiền dùng khoảng trắng không ngắt để giữ ký hiệu và số trên cùng một dòng.

**Không tự tuyên bố mọi khoảng trắng “lạ” là dữ liệu độc hại**. Hãy xác định yêu cầu đầu vào, cách hiển thị và các thuộc tính Unicode cần cho từng loại văn bản.

## 16. Chữ số, số La Mã và ký hiệu: category khác cảm nhận

Một số ký tự có ý nghĩa số hoặc hình dạng giống số nhưng không phải `DECIMAL_DIGIT_NUMBER`:

- `Ⅻ` thuộc **LETTER_NUMBER**, có numeric value `12`;
- `²` thuộc **OTHER_NUMBER**, có numeric value `2`;
- `½` có giá trị số `1/2` và `getNumericValue` trả `-2`;
- Một biểu tượng emoji có thể nằm ở **OTHER_SYMBOL**;
- Chữ Hán hoặc ký tự alphabetic có thể có những thuộc tính số, dấu hoặc script khác nhau theo code point.

Do đó, không có một lệnh duy nhất trả lời đúng cả:
1. “Đây có phải chữ số thập phân không?”
2. “Đây có mang giá trị số không?”
3. “Đây có thể là chữ số trong một cơ số không?”
4. “Đây có phải token số hợp lệ theo cú pháp sản phẩm không?”

Ánh xạ phù hợp:

| Nhu cầu | Gợi ý API |
| --- | --- |
| Chữ số Unicode dạng decimal | `Character.isDigit(cp)` |
| Chữ số ASCII bắt buộc | `cp >= '0' && cp <= '9'` |
| Một chữ số theo cơ số 16 | `Character.digit(cp, 16)` |
| Numeric value Unicode của một code point | `Character.getNumericValue(cp)` |
| Đọc số nguyên đầy đủ | Parser số + xác thực policy |
| Đọc số theo locale người dùng | `NumberFormat`/`DecimalFormat` với locale và xác thực đầu vào |
| Biết category thực tế | `Character.getType(cp)` |

Trong giao tiếp máy giữa các hệ thống, thường nên lưu/trao đổi số ở dạng cấu trúc hoặc ký pháp không phụ thuộc locale. Dạng chữ số địa phương phù hợp cho **hiển thị hoặc đầu vào người dùng** khi sản phẩm chủ động hỗ trợ.

## 17. Thuộc tính định danh: không đồng nghĩa với chữ cái/digit

Java cung cấp:

~~~java
Character.isJavaIdentifierStart(cp);
Character.isJavaIdentifierPart(cp);
Character.isUnicodeIdentifierStart(cp);
Character.isUnicodeIdentifierPart(cp);
Character.isIdentifierIgnorable(cp);
~~~

Các API này trả lời câu hỏi về **khả năng tham gia một định danh theo quy tắc Java/Unicode**, không phải “người dùng có được phép đặt username này không”.

Chẳng hạn có những code point không phải letter/digit nhưng vẫn được Java cho phép tham gia định danh (ví dụ underscore) và có những code point có tính chất khác nhau giữa `isJavaIdentifierStart` và `isUnicodeIdentifierStart`.

Không dùng `isJavaIdentifierPart` trực tiếp làm bộ lọc mật khẩu, username hoặc tên người:
- Một số ký tự hợp lệ cho Java source code lại không phù hợp cho định danh công khai.
- Một số tên người hợp lệ theo ngôn ngữ tự nhiên có thể không được phép trong Java identifier.
- Một chuỗi thỏa Java identifier chưa chắc an toàn trước tấn công **homoglyph/confusable**, bi-directional control hay spoofing.
- `Character.isIdentifierIgnorable` mô tả một thuộc tính liên quan định danh, không nói rằng mọi ký tự trả `true` đều an toàn để bỏ qua trong văn bản.

Khi thiết kế định danh công khai, cần policy sản phẩm cụ thể, normalization, kiểm soát mixed scripts và các phép kiểm tra chống giả mạo phù hợp. Chỉ dựa vào một Boolean từ `Character` sẽ không đủ.

## 18. Thuộc tính hướng văn bản, ký tự mirror và ký tự control

`Character` còn nhiều API hữu ích khi xử lý Unicode:

- `Character.getDirectionality(cp)` — loại thuộc tính hướng văn bản theo dữ liệu Unicode;
- `Character.isMirrored(cp)` — ký tự có thuộc tính mirrored trong ngữ cảnh viết hai chiều;
- `Character.isISOControl(cp)` — một số ký tự điều khiển ISO;
- `Character.isDefined(cp)` — code point đã được định nghĩa trong dữ liệu Unicode của JDK;
- `Character.getName(cp)` — tên Unicode của code point khi có.

Ví dụ:

~~~java
System.out.println(Character.isMirrored('('));
System.out.println(Character.getDirectionality('A')
        == Character.DIRECTIONALITY_LEFT_TO_RIGHT);
~~~

Đây là snippet trong phương thức. Kết quả:

~~~text
true
true
~~~

Những thuộc tính trên giúp **phát hiện/classify** ký tự, nhưng chúng **không tự thực hiện toàn bộ thuật toán hiển thị văn bản hai chiều**. Khi xử lý tiếng Ả Rập hoặc tiếng Do Thái, còn cần khả năng render/bi-directional algorithm của giao diện hoặc thư viện phù hợp.

Đừng tự “đảo chuỗi” để hỗ trợ RTL; đảo code unit có thể phá surrogate pair và dấu kết hợp, trong khi thứ tự hiển thị chịu chi phối bởi thuật toán bidi, không phải phép đảo chuỗi đơn giản.

## 19. Phiên bản Unicode của JDK và dữ liệu thay đổi

`Character` dựa trên một **phiên bản dữ liệu Unicode** được JDK triển khai. Khi nâng JDK, một số code point mới có thể được gán category, script hoặc thuộc tính khác; những phương thức như `isLetter`, `isDigit` hoặc `isDefined` có thể cho kết quả mới với code point từng chưa được hỗ trợ.

Vì vậy:
- Không suy ra mọi phiên bản Java nhận diện cùng một bộ chữ mới nhất.
- Nếu dùng Unicode classification để quyết định **chính sách bảo mật hoặc xác thực định danh**, phải kiểm thử khi cập nhật JDK.
- Nếu cần tương thích chặt chẽ giữa các dịch vụ chạy các runtime khác nhau, có thể phải cố định chính sách dữ liệu và phiên bản Unicode hoặc dùng một thư viện được quản lý thống nhất.
- Không viết test kiểu “tất cả code point hiện chưa được định nghĩa mãi mãi sẽ `false`”.

Đối với bài học Java core, hãy coi các ví dụ U+0035, U+0665, U+216B, U+00B2, U+0301 và U+10400 là các tình huống đã được Java 17 nhận diện, và chủ động kiểm tra trên JDK triển khai của bạn khi logic phụ thuộc category/script.

## 20. Ví dụ tổng hợp: phân loại chuỗi theo code point

Tạo tệp **`UnicodeClassifier.java`**:

~~~java
public class UnicodeClassifier {
    private static String classify(int cp) {
        if (Character.isDigit(cp)) {
            return "DECIMAL_DIGIT";
        }
        if (Character.isLetter(cp)) {
            return "LETTER";
        }
        if (Character.isAlphabetic(cp)) {
            return "ALPHABETIC_OTHER";
        }
        if (Character.getNumericValue(cp) >= 0) {
            return "NUMERIC_OTHER";
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        int[] points = {
                'A',
                0x0665,
                0x216B,
                0x00B2,
                0x1F600
        };

        for (int cp : points) {
            System.out.printf("U+%04X %s%n", cp, classify(cp));
        }
    }
}
~~~

~~~bash
javac UnicodeClassifier.java
java UnicodeClassifier
~~~

Kết quả:

~~~text
U+0041 LETTER
U+0665 DECIMAL_DIGIT
U+216B ALPHABETIC_OTHER
U+00B2 NUMERIC_OTHER
U+1F600 OTHER
~~~

Ví dụ minh họa cách các thuộc tính có **tập giao nhau và khác nhau**; nhãn `ALPHABETIC_OTHER` là nhãn do chương trình đặt, không phải một category Unicode chính thức.

**Giới hạn ví dụ:** Phân loại một code point không thể quyết định toàn bộ quy tắc chấp nhận tên, mật khẩu, số tiền hay văn bản. Nếu ứng dụng cần chấp nhận combining mark, xem ngữ cảnh các code point đứng trước và sau, normalization, script và bộ quy tắc sản phẩm.

## 21. Ví dụ xác thực số ASCII và chữ cái Unicode một cách có chủ đích

Một mã tham chiếu kỹ thuật yêu cầu **chính xác sáu chữ số ASCII**:

~~~java
public static boolean isSixAsciiDigits(String input) {
    return input != null
            && input.length() == 6
            && input.chars().allMatch(
                    c -> c >= '0' && c <= '9');
}
~~~

Đây là **snippet trong class**. `String.chars()` ở đây phù hợp **vì policy đã giới hạn ASCII**, mỗi ký tự hợp lệ đều dùng một UTF-16 code unit. Nếu policy cho phép **Unicode decimal digits**, cần dùng code points và tiêu chí khác.

Một bộ lọc thô cho **chữ cái Unicode hoặc combining mark** có thể viết:

~~~java
public static boolean isLetterOrMark(int cp) {
    int type = Character.getType(cp);
    return Character.isLetter(cp)
            || type == Character.NON_SPACING_MARK
            || type == Character.COMBINING_SPACING_MARK
            || type == Character.ENCLOSING_MARK;
}
~~~

Đây là snippet trong class, **chưa phải bộ validator tên người hoàn chỉnh**. Nếu chỉ chấp nhận mọi dấu kết hợp ở mọi vị trí, một tên bắt đầu bằng dấu lẻ cũng có thể lọt qua. Cần bổ sung logic theo vị trí, dấu cách/dấu nối cho phép, chính sách chiều dài và kiểm soát nội dung theo nhu cầu.

### Chương trình kiểm tra hai chính sách khác nhau

Tạo **`UnicodeValidationDemo.java`**:

~~~java
public class UnicodeValidationDemo {
    static boolean asciiDigits(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(
                        cp -> cp >= '0' && cp <= '9');
    }

    static boolean unicodeDecimalDigits(String text) {
        return text != null
                && !text.isEmpty()
                && text.codePoints().allMatch(Character::isDigit);
    }

    public static void main(String[] args) {
        String ascii = "123";
        String arabic = new String(
                new int[]{0x0661, 0x0662, 0x0663}, 0, 3);

        System.out.println(asciiDigits(ascii));
        System.out.println(unicodeDecimalDigits(ascii));
        System.out.println(asciiDigits(arabic));
        System.out.println(unicodeDecimalDigits(arabic));
    }
}
~~~

~~~bash
javac UnicodeValidationDemo.java
java UnicodeValidationDemo
~~~

Kết quả:

~~~text
true
true
false
true
~~~

Hai cách kiểm tra đều đúng **trong phạm vi chính sách mà chúng công bố**, nhưng không thể thay thế cho nhau. Khi xác nhận số liệu nghiệp vụ, còn phải kiểm tra độ dài, giá trị hợp lệ, tràn số và kiểu dữ liệu sau parse.

## 22. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem `char` là mọi ký tự Unicode | Bỏ sót code point ngoài BMP | Dùng overload `int` và `String.codePoints()` |
| Coi `String.length()` là số chữ người dùng thấy | Đếm sai surrogate pair và grapheme cluster | Chọn phép đếm đúng yêu cầu |
| Coi `isDigit` là ASCII-only | Chấp nhận chữ số từ nhiều hệ chữ số | Kiểm tra `'0'..'9'` nếu policy chỉ ASCII |
| Coi `getNumericValue>=0` là decimal digit | Chấp nhận số La Mã/số mũ, thậm chí chữ Latin trong một số trường hợp | Dùng `isDigit` hoặc `digit` theo mục đích |
| Coi `isLetter` và `isAlphabetic` tương đương | Phân loại khác nhau với letter-number | Chọn đúng thuộc tính |
| Coi `isLetterOrDigit` là validator tên người | Loại bỏ dấu kết hợp, khoảng trắng và dấu nối hợp lệ | Thiết kế validation theo ngữ cảnh |
| Coi `UnicodeBlock` là script | Sai khi một script có nhiều block | Dùng `UnicodeScript` khi cần script |
| Dùng `Character.toUpperCase` cho toàn chuỗi cần locale | Bỏ qua chuyển đổi nhiều ký tự và quy tắc ngôn ngữ | Dùng `String.toUpperCase(locale)` |
| So sánh hai chuỗi Unicode nhìn giống nhau bằng `equals` rồi kết luận khác văn bản | Dạng composed/decomposed có thể khác bytes | Xem xét `Normalizer` |
| Coi mọi Unicode whitespace là `isWhitespace=true` | Bỏ sót NBSP | Phân biệt `isWhitespace`/`isSpaceChar` |
| Tin `isJavaIdentifierPart` là đủ cho username an toàn | Bỏ sót spoofing/mixed scripts/control | Policy định danh và kiểm tra chuyên biệt |
| Đảo chuỗi để hỗ trợ RTL | Phá Unicode và sai thuật toán bidi | Dùng engine bidi/render thích hợp |
| Nâng JDK mà không kiểm tra thuộc tính Unicode | Kết quả phân loại có thể thay đổi | Kiểm thử/ghi nhận phiên bản Unicode |

## 23. Checklist kiểm thử trong ứng dụng localization

Một bộ kiểm thử thực tế nên bao quát:

1. **ASCII Latin và số**: `A`, `z`, `0`, `9`.
2. **Chữ số địa phương**: Arabic-Indic, Devanagari, fullwidth.
3. **Numeric không phải digit**: `Ⅻ`, `²`, `½`.
4. **Chữ thuộc nhiều script**: Latin, Han, Cyrillic, Ả Rập.
5. **Chữ ngoài BMP**: một code point dạng surrogate pair, ví dụ U+10400.
6. **Dấu kết hợp**: chuỗi dựng sẵn và chuỗi base + combining mark.
7. **Khoảng trắng đặc biệt**: NBSP và narrow NBSP.
8. **Case theo locale**: ít nhất tiếng Thổ Nhĩ Kỳ và trường hợp `ß`.
9. **Mixed scripts/confusables** nếu dùng định danh công khai.
10. **Ký tự control và bidi** khi dữ liệu được hiển thị trong log/UI nhạy cảm.
11. **Runtime Unicode version** khi nâng JDK.
12. **Parser số và ranh giới ASCII** nếu giao thức yêu cầu ký pháp cố định.

Khi test, ưu tiên biểu diễn code point bằng `0xXXXX` hoặc `U+XXXX` thay vì phụ thuộc font/console có hiển thị đúng mọi hệ chữ viết hay không. `System.out.printf("U+%04X", cp)` giúp đối chiếu chính xác giá trị mã.

## 24. Bài tập có đáp án

**Câu 1.** `Character.isDigit(0x0665)` trả gì? Có đảm bảo đây là chữ số ASCII không?

**Đáp án:** Trả `true`, nhưng U+0665 là Arabic-Indic digit five, **không phải ASCII**.

**Câu 2.** Vì sao `Character.isDigit(0x216B)` trả `false` mà `getNumericValue(0x216B)` trả `12`?

**Đáp án:** U+216B là số La Mã thuộc category `LETTER_NUMBER`, không phải chữ số decimal `Nd`.

**Câu 3.** `isLetter(0x216B)` và `isAlphabetic(0x216B)` có cùng kết quả không?

**Đáp án:** Không. Lần lượt là `false` và `true`.

**Câu 4.** Vì sao `Character.isLetter(text.charAt(0))` có thể sai cho một chữ ngoài BMP?

**Đáp án:** `charAt(0)` chỉ lấy một surrogate code unit, không phải toàn bộ code point. Dùng `codePointAt(0)` và overload `int`.

**Câu 5.** `Character.getNumericValue(0x00BD)` trả `-2` nghĩa là gì?

**Đáp án:** Ký tự `½` có giá trị số phân số không biểu diễn được bằng một `int` không âm theo cách API này trả về.

**Câu 6.** Tại sao một tên chứa `e` + U+0301 có thể bị `isLetter` từ chối ở code point thứ hai?

**Đáp án:** U+0301 là `NON_SPACING_MARK`, không thuộc Unicode letter category; validation tên cần xét dấu kết hợp/normalization.

**Câu 7.** Dùng `Character.isLetterOrDigit` để cho phép tất cả tên người có hợp lý không?

**Đáp án:** Không; tên người có thể chứa dấu cách, dấu nối, apostrophe hoặc combining mark, và một số quy tắc tên không thể phân biệt chỉ qua category từng code point.

**Câu 8.** Khi chuyển chữ hoa toàn chuỗi cho người dùng Thổ Nhĩ Kỳ, nên dùng `Character` hay `String.toUpperCase(locale)`?

**Đáp án:** Dùng phép chuyển đổi chuỗi có `Locale` đúng ngôn ngữ, vì case mapping có thể phụ thuộc locale/ngữ cảnh và có thể thay đổi độ dài chuỗi.

**Câu 9.** Vì sao `Character.isWhitespace(0x00A0)` là `false` nhưng `isSpaceChar(0x00A0)` là `true`?

**Đáp án:** Chúng kiểm tra những tập thuộc tính Unicode khác nhau; NBSP thuộc loại space character nhưng bị loại khỏi định nghĩa whitespace của API.

**Câu 10.** Nếu bộ lọc mã OTP yêu cầu chính xác sáu chữ số ASCII, nên dùng `Character.isDigit` không?

**Đáp án:** Không dùng riêng `isDigit`. Kiểm tra chính xác độ dài và từng code point trong phạm vi `'0'` đến `'9'`.

## 25. Quy trình ứng dụng vào hệ thống Java thực tế

1. **Xác định yêu cầu dữ liệu**, đừng bắt đầu bằng cách chọn đại một phương thức `Character`.
2. **Chọn cấp độ xử lý**: code unit UTF-16, code point Unicode, hay grapheme cluster.
3. **Chọn thuộc tính chính xác**: `isDigit`, `isLetter`, `isAlphabetic`, general category, script hoặc một tổ hợp phù hợp.
4. **Nếu là dữ liệu số**, xác định ASCII-only, Unicode decimal digits hay parser theo locale; kiểm tra toàn chuỗi sau parse.
5. **Nếu là tên/định danh**, xét normalization, combining marks, dấu câu, mixed scripts và spoofing theo chính sách sản phẩm.
6. **Nếu chuyển case**, truyền `Locale` phù hợp hoặc dùng `Locale.ROOT` cho ngữ cảnh kỹ thuật cần độc lập locale.
7. **Nếu lưu/hiển thị**, tách bước phân loại ký tự khỏi encoding/escaping ở đầu ra; `Character` không tự bảo đảm an toàn HTML, SQL hay log.
8. **Nếu dùng thuộc tính Unicode trong luật bảo mật**, kiểm thử lại khi nâng Java/Unicode data.
9. **Nếu cần hỗ trợ RTL và grapheme cluster**, dùng công cụ thuật toán phù hợp thay vì đảo chuỗi hoặc cắt theo `char`.

**Ghi nhớ:** Trong Java, `Character` hỗ trợ **Unicode classification**, không chỉ ASCII. `isDigit` khác `getNumericValue`; `isLetter` khác `isAlphabetic`; `char` khác **code point**; và kiểm tra thuộc tính từng code point khác với việc xác thực **một chuỗi có ý nghĩa trong ngôn ngữ tự nhiên**. Kết hợp đúng API với `Locale`, `Normalizer`, parser và chính sách sản phẩm là nền tảng để xử lý văn bản đa ngôn ngữ đáng tin cậy.

**Tài liệu Java SE 17:** [Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html).