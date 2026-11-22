# CharSequence.chars() và codePoints() — tạo IntStream đúng với Unicode

## Mục tiêu học tập

Trong Java 8, interface **CharSequence** cung cấp hai phương thức tạo nguồn **IntStream** trực tiếp từ một chuỗi ký tự:

- **chars()**: tạo luồng các **UTF-16 code units** (các giá trị **char**, mỗi giá trị được mở rộng không dấu thành **int**).
- **codePoints()**: tạo luồng các **Unicode code points** bằng cách kết hợp những **surrogate pair hợp lệ** thành một giá trị int.

Hai luồng này có thể cho kết quả giống nhau với chữ ASCII, nhưng khác nhau với ký tự nằm ngoài **Basic Multilingual Plane (BMP)**, chẳng hạn nhiều emoji và một số chữ viết hiếm. Khác biệt này ảnh hưởng trực tiếp tới **đếm ký tự**, lọc chữ/số, xử lý chuỗi và xây dựng văn bản Unicode an toàn.

Sau bài học, bạn sẽ biết:

1. CharSequence liên quan thế nào tới String, StringBuilder và StringBuffer.
2. Vì sao **String.length()** đếm đơn vị UTF-16, không phải luôn đếm Unicode code points hoặc ký tự người dùng nhìn thấy.
3. Cách sử dụng **chars()**, **codePoints()**, **IntStream**, **Character** và **StringBuilder.appendCodePoint(...)**.
4. Cách phát hiện và xử lý trường hợp surrogate ghép cặp hoặc **unpaired surrogate**.
5. Phân biệt **code point**, **code unit**, **grapheme cluster** và **UTF-8 byte**.
6. Cách xử lý dữ liệu Unicode từ CharSequence **có thể thay đổi** mà không dựa vào kết quả không được bảo đảm.
7. Các lỗi hay gặp khi cast int sang char, chuyển một code point thành String, hay dùng Character.isLetter / isDigit.

Đây là API từ Java 8 và **vẫn được sử dụng trong Java hiện đại**, bao gồm JDK 17, 21 và các bản mới hơn. Tất cả chương trình độc lập trong bài đều dùng API tương thích **Java 8**, có tên tệp, lệnh biên dịch/chạy và stdout xác định.

---

## 1. CharSequence là gì?

**java.lang.CharSequence** là interface cho một dãy giá trị **char** có thể được đọc theo vị trí. Những triển khai quen thuộc gồm:

- **String**: dãy ký tự bất biến (immutable).
- **StringBuilder**: dãy ký tự có thể sửa, thường dùng trong logic đơn luồng.
- **StringBuffer**: dãy ký tự có thể sửa, với nhiều phương thức được đồng bộ hóa; không có nghĩa mọi pipeline Stream trên nó tự an toàn khi sửa đồng thời.
- **CharBuffer**: một abstraction cho bộ đệm ký tự.

Các phương thức cốt lõi của CharSequence là **length()**, **charAt(int)**, **subSequence(int,int)** và **toString()**. Từ Java 8, interface bổ sung hai default methods:

~~~java
default java.util.stream.IntStream chars();

default java.util.stream.IntStream codePoints();
~~~

Đây là **chữ ký API minh họa**, không phải code bạn cần tự implement. Vì chúng nằm trên CharSequence, các kiểu triển khai có thể được dùng qua cùng một kiểu interface:

~~~java
CharSequence sequence = new StringBuilder("ABC");

long units = sequence.chars().count();
long points = sequence.codePoints().count();
~~~

Đây là đoạn minh họa cần đặt trong method; với "ABC", cả hai kết quả đều bằng **3**.

**IntStream** là primitive stream chứa các giá trị **int**. Java không có **CharStream** chuẩn tương đương. chars() và codePoints() trả IntStream vì cần biểu diễn giá trị số:

- UTF-16 code unit có giá trị từ **0** đến **65535**.
- Unicode code point có thể lớn hơn **65535**, tối đa **0x10FFFF** về mặt mã số.

Do đó, một phần tử int trả về từ **codePoints()** không nên mặc định bị ép sang char; nó có thể cần **hai char UTF-16** để biểu diễn.

## 2. UTF-16: code unit khác code point

Java **String** dùng các giá trị **char 16 bit** để biểu diễn nội dung ký tự theo UTF-16. Một đơn vị char có thể là:

- Một ký tự thuộc **BMP** không phải surrogate, được biểu diễn bằng một code unit.
- Một **high surrogate** (giá trị **U+D800** đến **U+DBFF**).
- Một **low surrogate** (giá trị **U+DC00** đến **U+DFFF**).

Một Unicode code point thuộc vùng bổ sung, từ **U+10000** trở lên, được mã hóa UTF-16 bằng **hai code units liên tiếp**: high surrogate theo sau bởi low surrogate.

Ví dụ emoji mặt cười **U+1F600** có hai code units:

~~~text
Unicode code point: U+1F600   (decimal 128512)
UTF-16 high surrogate: U+D83D (decimal 55357)
UTF-16 low surrogate:  U+DE00 (decimal 56832)
~~~

**Một code point** ở đây tương ứng với **hai char**. Vì vậy phép đếm số lượng char và số lượng code point có thể khác nhau.

Ví dụ minh họa:

~~~java
String value = "A\uD83D\uDE00B";

System.out.println(value.length());  // 4 UTF-16 code units
System.out.println(value.codePointCount(0, value.length()));  // 3
~~~

Kết quả là **4** và **3**. Chuỗi gồm A, U+1F600, B. A và B mỗi chữ chiếm một code unit; emoji chiếm hai.

### Ba mức độ cần tránh nhầm

| Đại lượng | Ý nghĩa | Ví dụ A + U+1F600 + B |
| --- | --- | --- |
| **UTF-16 code units** | Số giá trị char 16-bit | 4 |
| **Unicode code points** | Số giá trị mã Unicode sau khi ghép surrogate pairs | 3 |
| **Grapheme clusters** | Đơn vị chữ người dùng thường cảm nhận | Trong ví dụ đơn giản thường là 3; không phải kết quả chung của codePoints() |

**codePoints() không phải bộ đếm mọi ký tự hiển thị theo cách người dùng nhìn thấy.** Một chữ có dấu có thể được biểu diễn thành ký tự cơ sở và combining mark, tức nhiều code points nhưng có thể hiển thị như một grapheme cluster. Một emoji phức hợp dùng zero-width joiner cũng có thể chứa nhiều code points.

## 3. chars() hoạt động thế nào?

**CharSequence.chars()** trả một **IntStream** theo thứ tự các giá trị **char** trong chuỗi. Mỗi char được **zero-extend** sang int: các bit của char được giữ, không có chuyển dấu làm giá trị âm.

Ví dụ ASCII:

~~~java
int[] values = "ABC".chars().toArray();
// [65, 66, 67]
~~~

Trong trường hợp này, mỗi char cũng chính là một Unicode code point trong BMP, nên chars() và codePoints() cho cùng các số.

Với một code point bổ sung như **U+1F600**, chars() không ghép hai surrogate lại. Nó xuất ra **hai giá trị int riêng**:

~~~java
int[] units = "\uD83D\uDE00".chars().toArray();
// [55357, 56832]
~~~

Dãy **[55357,56832]** là hai UTF-16 code units, **không** phải hai Unicode scalar values độc lập thể hiện hai ký tự hiển thị.

### Vì sao tên chars() dễ gây hiểu nhầm?

Trong văn nói, “character” thường có nghĩa ký tự bạn thấy trên màn hình. Nhưng trong API Java, **char là một đơn vị 16-bit**. Một code point bổ sung cần hai char. Vì vậy:

- **chars().count()** phù hợp khi bạn thật sự muốn đếm **UTF-16 code units**.
- **chars().filter(...)** phù hợp cho logic thao tác trên từng code unit, ví dụ xử lý ASCII hoặc một giao thức nội bộ định nghĩa theo char.
- **chars()** thường không phù hợp nếu bạn muốn thao tác độc lập trên mỗi Unicode code point, đặc biệt khi văn bản có ký tự ngoài BMP.

Nếu muốn “mỗi ký tự Unicode” theo nghĩa **code point**, hãy bắt đầu với codePoints().

## 4. codePoints() hoạt động thế nào?

**CharSequence.codePoints()** trả **IntStream** gồm các giá trị Unicode code point:

- Ký tự BMP không nằm trong surrogate pair: giá trị code point được đưa trực tiếp vào stream.
- High surrogate + low surrogate **liền kề và đúng thứ tự**: được kết hợp thành **một** code point bổ sung, như khi gọi **Character.toCodePoint(high, low)**.
- Các UTF-16 code units khác, kể cả **unpaired surrogate**, được chuyển thành int riêng, **không tự động biến thành U+FFFD**.

Ví dụ:

~~~java
int[] points = "A\uD83D\uDE00B".codePoints().toArray();
// [65, 128512, 66]
~~~

**So sánh trực tiếp:**

~~~text
Input: A + U+1F600 + B

chars()      -> [65, 55357, 56832, 66]
codePoints() -> [65, 128512, 66]

chars().count()      -> 4
codePoints().count() -> 3
~~~

**Không phải codePoints() “chuyển chuỗi sang UTF-32”.** API trả một Stream các giá trị int. Việc lưu một mảng int hay mã hóa thành bytes là những bước riêng nếu ứng dụng cần.

## 5. Ví dụ hoàn chỉnh: UTF-16 units và Unicode code points

Tạo tệp **CharSequenceUnitsDemo.java**:

~~~java
import java.util.Arrays;

public class CharSequenceUnitsDemo {

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00\u00E9";

        int[] units = text.chars().toArray();
        int[] points = text.codePoints().toArray();

        System.out.println("String.length: " + text.length());
        System.out.println("chars count: " + text.chars().count());
        System.out.println("codePoints count: " +
            text.codePoints().count());

        System.out.println("UTF-16 units: " +
            Arrays.toString(units));
        System.out.println("Code points: " +
            Arrays.toString(points));

        System.out.println("String.codePointCount: " +
            text.codePointCount(0, text.length()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CharSequenceUnitsDemo.java
java CharSequenceUnitsDemo
~~~

Stdout:

~~~text
String.length: 4
chars count: 4
codePoints count: 3
UTF-16 units: [65, 55357, 56832, 233]
Code points: [65, 128512, 233]
String.codePointCount: 3
~~~

**Giải thích:**

1. Text chứa "A" (U+0041), U+1F600 và "é" (U+00E9).
2. **String.length()** là 4 vì A chiếm 1 code unit, emoji chiếm 2 và é (dạng composed) chiếm 1.
3. **chars()** xuất ra giá trị 65, 55357, 56832, 233 — chính là bốn đơn vị UTF-16.
4. **codePoints()** ghép 55357/56832 thành **128512** nên chỉ còn ba phần tử.
5. **String.codePointCount(0, text.length())** đếm code point trên khoảng chỉ số UTF-16 được yêu cầu; kết quả khớp với số phần tử codePoints() ở toàn chuỗi.
6. Mỗi terminal operation sử dụng **một Stream mới**. Không gọi lại chars() hay codePoints() trên **cùng đối tượng Stream đã tiêu thụ**.

Việc dùng escape **\uD83D\uDE00** giúp tệp nguồn thể hiện rõ surrogate pair. Khi hiển thị emoji trực tiếp, biên tập viên và font cũng cần hỗ trợ ký tự tương ứng; nhưng giá trị Unicode về mặt API không thay đổi.

---

## 6. IntStream là primitive stream, không phải Stream<Character>

Cả hai phương thức trả **IntStream**, không trả **Stream<Character>** hoặc **Stream<String>**.

Điều này cho phép sử dụng các terminal operations như:

~~~java
long count = text.codePoints().count();

int[] points = text.codePoints().toArray();

int max = text.codePoints().max().orElse(-1);

int total = text.chars().sum();
~~~

Đây là các đoạn minh họa giả định biến text là String. **sum()** cộng giá trị số các UTF-16 units; nó hiếm khi là một phép toán văn bản có ý nghĩa, nhưng ví dụ cho thấy cách IntStream xử lý giá trị int.

### Chuyển từ IntStream sang Stream<String>

Nếu muốn **mỗi code point thành một String riêng**:

~~~java
java.util.List<String> symbols = text.codePoints()
    .mapToObj(cp -> new String(Character.toChars(cp)))
    .collect(java.util.stream.Collectors.toList());
~~~

Ở đây:

- **codePoints()** phát ra int tương ứng với code point.
- **Character.toChars(cp)** chuyển code point thành **char[]** UTF-16: một char với BMP, hai char với code point bổ sung.
- **new String(char[])** tạo một String biểu diễn phần tử đó.
- **mapToObj** biến IntStream thành Stream<String>.

**Tránh viết:**

~~~java
java.util.List<String> broken = text.codePoints()
    .mapToObj(cp -> String.valueOf((char) cp))
    .collect(java.util.stream.Collectors.toList());
~~~

Đây là đoạn **minh họa cách làm không đúng cho Unicode bổ sung**. Với code point **128512**, phép cast sang char **làm mất phần bit quan trọng**, không thể tạo lại emoji. Chỉ dùng cast int -> char nếu bạn **biết chắc** giá trị nằm trong phạm vi đơn vị char và muốn đúng một code unit.

### Ghép lại String bằng appendCodePoint

Bạn không nhất thiết phải tạo một String trung gian cho mỗi code point. Có thể thu IntStream vào StringBuilder:

~~~java
String rebuilt = text.codePoints().collect(
    StringBuilder::new,
    (builder, cp) -> builder.appendCodePoint(cp),
    (left, right) -> left.append(right)
).toString();
~~~

Đây là đoạn minh họa Java 8. **StringBuilder.appendCodePoint(int)** biết cách mã hóa code point thành một hoặc hai char UTF-16. Lựa chọn này giúp tránh việc cast thu hẹp code point.

**Giới hạn:** với dữ liệu chứa **unpaired surrogate**, không nên coi kết quả là một chuỗi Unicode scalar values hoàn chỉnh chỉ vì codePoints() đã được gọi. Nếu ứng dụng yêu cầu văn bản Unicode well-formed, cần thêm bước validation.

## 7. Ví dụ hoàn chỉnh: lọc chữ, số và dựng lại văn bản

Tạo tệp **CodePointPipelineDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CodePointPipelineDemo {

    public static void main(String[] args) {
        String input = "A\uD83D\uDE00B9";

        long letters = input.codePoints()
            .filter(Character::isLetter)
            .count();

        long digits = input.codePoints()
            .filter(Character::isDigit)
            .count();

        List<String> symbols = input.codePoints()
            .mapToObj(cp ->
                new String(Character.toChars(cp)))
            .collect(Collectors.toList());

        String rebuilt = input.codePoints().collect(
            StringBuilder::new,
            (builder, cp) -> builder.appendCodePoint(cp),
            (left, right) -> left.append(right)
        ).toString();

        System.out.println("Code points: " +
            Arrays.toString(input.codePoints().toArray()));
        System.out.println("Letters: " + letters);
        System.out.println("Digits: " + digits);
        System.out.println("Symbol count: " + symbols.size());
        System.out.println("Rebuilt equals input: " +
            rebuilt.equals(input));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CodePointPipelineDemo.java
java CodePointPipelineDemo
~~~

Stdout:

~~~text
Code points: [65, 128512, 66, 57]
Letters: 2
Digits: 1
Symbol count: 4
Rebuilt equals input: true
~~~

**Phân tích:**

- A và B là chữ nên **Character.isLetter** đếm 2.
- Ký tự số "9" là một digit nên **Character.isDigit** đếm 1.
- Emoji U+1F600 không được Character.isLetter hoặc isDigit coi là chữ/số trong trường hợp này.
- **Character.toChars(128512)** tạo surrogate pair hợp lệ; symbols có bốn String phần tử theo bốn code points.
- **appendCodePoint** dựng lại đúng chuỗi ban đầu; kiểm tra equals trả true.
- Mỗi thao tác gọi **input.codePoints() mới**, vì IntStream cũng tuân theo nguyên tắc **single-use** như các Stream khác.

Trong ứng dụng xử lý Unicode rộng hơn, **Character.isLetter** và **isDigit** phân loại theo đặc tính Unicode, không chỉ ký tự tiếng Anh/ASCII. Nếu hợp đồng chỉ chấp nhận ASCII, bạn nên viết điều kiện rõ như **cp >= '0' && cp <= '9'**.

### Khi nào dùng Character methods?

Các method có overload nhận int như **Character.isLetter(int)**, **isDigit(int)**, **isWhitespace(int)**, **getType(int)** được thiết kế để thao tác với các giá trị code point. Dùng codePoints() giúp những method này nhận đúng một code point bổ sung thay vì từng surrogate riêng lẻ.

Nhưng **code point classification không phải mọi dạng xử lý ngôn ngữ**: tách từ, từ điển, viết hoa theo locale hay grapheme segmentation có thể cần API hoặc thư viện khác.

---

## 8. Surrogate pair phải đúng thứ tự và liền kề

Một **high surrogate** và **low surrogate** chỉ được ghép khi chúng tạo thành **một cặp hợp lệ theo thứ tự UTF-16**. Một high surrogate đứng một mình hoặc một low surrogate không có high surrogate ngay trước là **unpaired surrogate**.

Ví dụ có ba char:

~~~text
A + high surrogate U+D83D + B
~~~

Do không có low surrogate ngay sau high surrogate, **codePoints()** không ghép U+D83D với B. Nó phát ra:

~~~text
[65, 55357, 66]
~~~

Điều này quan trọng vì Java String **có thể chứa các giá trị char surrogate không ghép cặp**, dù chuỗi ấy không đại diện cho một dãy Unicode scalar values well-formed.

### codePoints() có tự thay thế U+FFFD không?

**Không.** Theo hợp đồng API, những code units không thuộc surrogate pair hợp lệ, bao gồm unpaired surrogate, được đưa ra như những giá trị int riêng.

Do đó, đừng cho rằng gọi **codePoints()** tự động sửa text lỗi thành Unicode hợp lệ hoặc loại bỏ surrogate. Nếu bạn đang kiểm tra tính well-formed Unicode, phải phát hiện unpaired surrogates và quyết định **từ chối**, **thay thế**, hay **báo lỗi** theo hợp đồng dữ liệu.

### isValidCodePoint(int) chưa đủ để phát hiện surrogate

Một chi tiết thường bị bỏ qua: **Character.isValidCodePoint(int)** kiểm tra giá trị có nằm trong miền mã code point 0..0x10FFFF hay không. Các giá trị thuộc vùng surrogate cũng nằm trong khoảng số này, dù chúng **không phải Unicode scalar values** hợp lệ độc lập.

Nếu muốn cấm surrogate code point trong dữ liệu đầu ra, hãy kiểm tra rõ miền **0xD800..0xDFFF** bên cạnh giới hạn số. Không dùng một mình isValidCodePoint để kết luận text được tạo từ một chuỗi UTF-16 well-formed.

## 9. Chương trình hoàn chỉnh: unpaired surrogate

Tạo tệp **UnpairedSurrogateDemo.java**:

~~~java
import java.util.Arrays;

public class UnpairedSurrogateDemo {

    public static void main(String[] args) {
        char unpairedHigh = (char) 0xD83D;
        char unpairedLow = (char) 0xDE00;

        String text = new String(
            new char[]{'A', unpairedHigh, 'B', unpairedLow});

        int[] units = text.chars().toArray();
        int[] points = text.codePoints().toArray();

        long isolatedSurrogates = text.codePoints()
            .filter(cp -> cp >= 0xD800 && cp <= 0xDFFF)
            .count();

        System.out.println("Units: " + Arrays.toString(units));
        System.out.println("Points: " + Arrays.toString(points));
        System.out.println("Unit count: " + text.length());
        System.out.println("Point count: " +
            text.codePoints().count());
        System.out.println("Isolated surrogates: " +
            isolatedSurrogates);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
~~~

Stdout:

~~~text
Units: [65, 55357, 66, 56832]
Points: [65, 55357, 66, 56832]
Unit count: 4
Point count: 4
Isolated surrogates: 2
~~~

**Giải thích:**

1. High surrogate U+D83D không đứng cạnh một low surrogate; giữa nó và U+DE00 là ký tự B.
2. Vì không có cặp surrogate hợp lệ, codePoints() đưa ra bốn giá trị như chars().
3. Hai giá trị **55357** và **56832** thuộc vùng surrogate; chúng không được thay thế bằng U+FFFD.
4. **isolatedSurrogates** đếm 2, minh họa một phép kiểm tra đơn giản trên dãy codePoints.
5. Code này **không tuyên bố String tự động mất dữ liệu lỗi**; nó cho thấy bạn phải tự chọn chính sách dữ liệu không hợp lệ.

Trong hệ thống thật, với dữ liệu có thể bị lỗi encoding, nên kiểm tra tại ranh giới đọc/ghi dữ liệu, không dựa vào một bước chuyển sang codePoints() như một sanitizer.

## 10. Phân biệt UTF-16 code unit, Unicode code point và grapheme cluster

### 10.1. Ví dụ chữ có dấu

Hai chuỗi có thể hiển thị gần giống nhau:

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";
~~~

- **composed** là code point U+00E9 (é), một UTF-16 code unit.
- **decomposed** gồm U+0065 (e) và U+0301 (combining acute accent), hai UTF-16 code units và hai code points.

Kết quả:

~~~text
composed.length()          = 1
composed.codePoints().count() = 1

decomposed.length()        = 2
decomposed.codePoints().count() = 2
~~~

Nhưng hai chuỗi có thể được xem là **tương đương Unicode về mặt chuẩn hóa**, và người dùng có thể cảm nhận như **một chữ có dấu**.

**codePoints() không tự chuẩn hóa** hai dạng biểu diễn này. Nếu nhu cầu là so sánh văn bản tương đương chuẩn hóa, hãy cân nhắc **java.text.Normalizer**.

### 10.2. Ví dụ emoji phức hợp

Một emoji được tạo từ nhiều code points với **zero-width joiner (ZWJ)** có thể hiển thị như một hình thống nhất trên nhiều nền tảng. **codePoints().count()** vẫn đếm từng code point riêng, không tự ghép chúng thành một grapheme cluster.

Vì vậy những yêu cầu sau **không tương đương**:

- Đếm số đơn vị UTF-16: String.length() hoặc chars().count().
- Đếm số Unicode code points: codePoints().count() hoặc String.codePointCount(...).
- Đếm số ký tự người dùng nhìn thấy: cần xử lý **grapheme clusters** theo quy tắc Unicode/locale phù hợp.

Trong Java 8, **java.text.BreakIterator** có thể hỗ trợ một số nhu cầu boundary analysis; nhưng không nên mặc nhiên coi mọi implementation/version là bộ phân đoạn extended grapheme cluster đầy đủ cho mọi emoji ZWJ mới. Nếu yêu cầu Unicode text segmentation nghiêm ngặt, hãy xác nhận thuật toán và phiên bản Unicode của thư viện sử dụng.

## 11. Chương trình hoàn chỉnh: normalization không phải code point counting

Tạo tệp **UnicodeNormalizationDemo.java**:

~~~java
import java.text.Normalizer;
import java.util.Arrays;

public class UnicodeNormalizationDemo {

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(
            "Composed UTF-16 units: " + composed.length());
        System.out.println(
            "Decomposed UTF-16 units: " + decomposed.length());

        System.out.println(
            "Composed code points: " +
            composed.codePoints().count());

        System.out.println(
            "Decomposed code points: " +
            decomposed.codePoints().count());

        System.out.println("Composed values: " +
            Arrays.toString(composed.codePoints().toArray()));
        System.out.println("Decomposed values: " +
            Arrays.toString(decomposed.codePoints().toArray()));

        System.out.println("Raw equal: " +
            composed.equals(decomposed));

        String normalized = Normalizer.normalize(
            decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equal: " +
            composed.equals(normalized));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Stdout:

~~~text
Composed UTF-16 units: 1
Decomposed UTF-16 units: 2
Composed code points: 1
Decomposed code points: 2
Composed values: [233]
Decomposed values: [101, 769]
Raw equal: false
NFC equal: true
~~~

**Giải thích:**

- Hai chuỗi có dãy code points khác nhau và **String.equals** so sánh nội dung theo UTF-16 code units nên ban đầu không bằng nhau.
- **Normalizer.Form.NFC** chuẩn hóa thành composed form khi phép ghép tương ứng tồn tại, nên chuỗi normalized bằng composed.
- chars()/codePoints() chỉ **duyệt dữ liệu đang có**, không tự chuẩn hóa hay đo các grapheme clusters.
- Không nên normalize mù quáng dữ liệu cần giữ nguyên bytes/chuỗi gốc, chẳng hạn chữ ký số hoặc định danh có hợp đồng so sánh byte-level; chọn chính sách phù hợp.

---

## 12. Vấn đề index: char index không phải code point index

**String.charAt(int)** và **String.substring(int,int)** sử dụng **chỉ số UTF-16 code unit**, không phải vị trí code point. Vì vậy sau một code point bổ sung, index UTF-16 tăng **2**, không phải 1.

Ví dụ:

~~~java
String text = "A\uD83D\uDE00B";
~~~

Chỉ số UTF-16:

~~~text
Index 0: 'A'
Index 1: high surrogate U+D83D
Index 2: low surrogate  U+DE00
Index 3: 'B'
~~~

Nếu muốn tìm vị trí UTF-16 của code point thứ k, dùng:

~~~java
int utf16Index = text.offsetByCodePoints(0, k);
~~~

Với k = 2 (bỏ qua A và U+1F600), kết quả là **3**. Vì vậy:

~~~java
int index = text.offsetByCodePoints(0, 2);
String tail = text.substring(index); // "B"
~~~

**Không viết** text.substring(2) với ý nghĩ “bỏ hai Unicode ký tự” trong ví dụ này: index 2 nằm ở **low surrogate**, có thể tạo một String chứa unpaired surrogate.

### codePointAt và codePointBefore

Ngoài stream, String có:

- **codePointAt(utf16Index)**: đọc code point từ chỉ số UTF-16.
- **codePointBefore(utf16Index)**: đọc code point ngay trước một chỉ số UTF-16.
- **offsetByCodePoints(index, offset)**: dịch chuyển theo số code points nhưng trả về chỉ số UTF-16.
- **codePointCount(beginIndex,endIndex)**: đếm số code points trên khoảng chỉ số UTF-16.

Các API này vẫn hữu ích khi cần truy cập vị trí cụ thể thay vì duyệt cả chuỗi.

## 13. Chương trình hoàn chỉnh: di chuyển index theo code point

Tạo tệp **CodePointIndexDemo.java**:

~~~java
public class CodePointIndexDemo {

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        int thirdIndex = text.offsetByCodePoints(0, 2);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code point count: " +
            text.codePointCount(0, text.length()));
        System.out.println("Third index: " + thirdIndex);
        System.out.println("Tail: " + text.substring(thirdIndex));
        System.out.println("Second code point: " +
            text.codePointAt(1));
        System.out.println("Before third index: " +
            text.codePointBefore(thirdIndex));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CodePointIndexDemo.java
java CodePointIndexDemo
~~~

Stdout:

~~~text
UTF-16 length: 4
Code point count: 3
Third index: 3
Tail: B
Second code point: 128512
Before third index: 128512
~~~

**Phân tích:** ký tự thứ ba theo code points là B; nó bắt đầu tại UTF-16 index 3 vì emoji đứng trước chiếm hai code units. **codePointAt(1)** và **codePointBefore(3)** cùng đọc U+1F600. Điều này giải thích tại sao phải dùng **offsetByCodePoints** khi chuyển đổi từ chỉ số code point sang vị trí để truyền cho substring.

---

## 14. Nguồn CharSequence có thể thay đổi: tránh sửa khi Stream đang được đọc

**String** là immutable, nên bạn không thể sửa nội dung String đã có bằng append hoặc setCharAt. Ngược lại, **StringBuilder**, **StringBuffer** và một số CharSequence khác có thể thay đổi.

Theo hợp đồng của **CharSequence.chars()** và **codePoints()**, nếu **CharSequence bị thay đổi trong khi Stream đang được đọc**, kết quả là **không được xác định** theo contract. Bạn không được dựa vào việc nó “luôn thấy bản mới”, “luôn thấy bản cũ”, “luôn ném exception” hoặc “tự đồng bộ hóa”.

### Cách tốt: chụp snapshot trước khi tạo Stream

~~~java
StringBuilder buffer = new StringBuilder("AB");

String snapshot = buffer.toString();
int[] fixed = snapshot.codePoints().toArray();

buffer.append("C");

int[] current = buffer.codePoints().toArray();
~~~

Đoạn minh họa này **không sửa buffer trong khi một Stream đang được duyệt**. Snapshot là String bất biến.

**Kết quả:**

- fixed = [65,66], phản ánh nội dung "AB" lúc chụp snapshot.
- current = [65,66,67], phản ánh buffer sau khi đã thêm C, với **Stream mới**.
- Việc tạo mới một stream không tự tạo snapshot dữ liệu nguồn mutable nếu bạn vẫn đọc từ cùng đối tượng đang thay đổi.

### Không nhầm tính synchronized của StringBuffer

StringBuffer có những phương thức được đồng bộ hóa, nhưng điều đó không cho phép bạn mặc nhiên vừa sửa buffer vừa duyệt Stream và đòi một snapshot nhất quán. Nếu cần chia sẻ giữa threads, hãy thiết kế cơ chế khóa/snapshot phù hợp trước khi mở pipeline.

### Khi nguồn là CharBuffer

CharBuffer có trạng thái position/limit và có thể là view của bộ nhớ. Khi tạo Stream từ một CharSequence kiểu CharBuffer, phải hiểu contract của nguồn và tránh sửa trong khi đang duyệt. Nếu cần kết quả độc lập, **toString()** để có snapshot phần ký tự quan sát được thường đơn giản hơn.

## 15. Chương trình hoàn chỉnh: snapshot và cập nhật nguồn

Tạo tệp **MutableCharSequenceDemo.java**:

~~~java
import java.util.Arrays;

public class MutableCharSequenceDemo {

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("AB");

        String snapshot = builder.toString();
        int[] first = snapshot.codePoints().toArray();

        builder.append("C");
        int[] second = builder.codePoints().toArray();

        System.out.println("Snapshot: " +
            Arrays.toString(first));
        System.out.println("Current: " +
            Arrays.toString(second));
        System.out.println("Snapshot text: " + snapshot);
        System.out.println("Current text: " + builder);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MutableCharSequenceDemo.java
java MutableCharSequenceDemo
~~~

Stdout:

~~~text
Snapshot: [65, 66]
Current: [65, 66, 67]
Snapshot text: AB
Current text: ABC
~~~

**Giải thích:**

1. builder ban đầu chứa AB.
2. **builder.toString()** tạo một String snapshot bất biến.
3. Sau khi snapshot đã được duyệt, chương trình thêm C vào builder.
4. **builder.codePoints()** được gọi mới sau khi cập nhật, nên phản ánh ABC.
5. Không có thay đổi trong quá trình terminal operation; ví dụ không dựa vào hành vi không được xác định.
6. Nếu xử lý song song hoặc nguồn bị cập nhật bởi thread khác, cần kiểm soát việc sửa nguồn trong suốt quá trình đọc — **không** chỉ thêm synchronized ở một terminal operation riêng lẻ.

## 16. chars()/codePoints() và quy tắc Stream dùng một lần

Cả hai phương thức trả **IntStream**, và IntStream cũng là một Stream pipeline dùng một lần.

Sai:

~~~java
java.util.stream.IntStream stream = text.codePoints();

long count = stream.count();
int[] values = stream.toArray(); // Dùng lại Stream đã tiêu thụ.
~~~

Đây là đoạn minh họa sai. Sau count(), không được dùng chính đối tượng stream để gọi toArray().

Đúng:

~~~java
long count = text.codePoints().count();
int[] values = text.codePoints().toArray();
~~~

Mỗi lời gọi **text.codePoints()** tạo một đối tượng IntStream mới cho lượt xử lý riêng. Nếu nguồn là String immutable, hai lượt đọc cùng nội dung. Nếu là CharSequence mutable bị thay đổi giữa các lượt, hai kết quả có thể khác.

**Không dựa vào exception để biết một Stream có reusable hay không.** Trên nhiều implementation, dùng lại có thể ném IllegalStateException, nhưng API Stream không bảo đảm mọi trường hợp vi phạm đều được phát hiện. Cấu trúc code phải tuân theo single-use ngay từ đầu.

## 17. Đếm ký tự, lọc ASCII và Unicode classification

### Chỉ đếm ASCII digits

~~~java
long asciiDigits = text.codePoints()
    .filter(cp -> cp >= '0' && cp <= '9')
    .count();
~~~

Cách này định nghĩa rõ phạm vi chỉ là 0..9 theo ASCII.

### Đếm các Unicode digits

~~~java
long unicodeDigits = text.codePoints()
    .filter(Character::isDigit)
    .count();
~~~

**Character.isDigit(int)** có thể nhận diện chữ số thuộc các hệ chữ viết khác theo Unicode, tùy dữ liệu Unicode được JDK hỗ trợ. Nó không đồng nghĩa một regex hoặc một validation policy dành riêng cho ASCII.

### Đếm letter code points

~~~java
long letters = text.codePoints()
    .filter(Character::isLetter)
    .count();
~~~

Đây là số lượng **code points** được Character coi là letter. Nó **không phải số lượng từ**, không phải số grapheme clusters, và không đương nhiên là độ dài hiển thị của trường tên người dùng.

### Chuyển case không luôn 1:1

**Character.toUpperCase(int)** trả một code point tương ứng cho phép chuyển đổi theo API, nhưng **full string case mapping** có thể phức tạp hơn một phép ánh xạ 1 code point -> 1 code point. Ví dụ một số ngôn ngữ/ký tự có thể có thay đổi độ dài khi chuyển case toàn chuỗi.

Nếu mục tiêu là chữ hoa của toàn bộ String, hãy cân nhắc:

~~~java
String uppercase = text.toUpperCase(java.util.Locale.ROOT);
~~~

hoặc locale nghiệp vụ thích hợp. Đừng tự viết **text.codePoints().map(Character::toUpperCase)** rồi khẳng định kết quả luôn tương đương String.toUpperCase(Locale...) cho mọi ngôn ngữ.

## 18. UTF-8 byte không phải code point

Code point là một **giá trị mã Unicode**. UTF-8 là **cách mã hóa** những code point thành **bytes**. Java String cung cấp UTF-16 code units; khi gửi qua mạng hoặc ghi file UTF-8, số byte có thể khác cả length() và codePoints().count().

Ví dụ **"A" + U+1F600**:

- **String.length()** = 3 UTF-16 code units.
- **codePoints().count()** = 2 Unicode code points.
- **UTF-8 encoding** có 1 byte cho A và 4 bytes cho U+1F600, tổng 5 bytes.

### Ví dụ hoàn chỉnh: ba phép đo khác nhau

Tạo tệp **UnicodeEncodingSizesDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class UnicodeEncodingSizesDemo {

    public static void main(String[] args) {
        String value = "A\uD83D\uDE00";

        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-16 units: " + value.length());
        System.out.println("Code points: " +
            value.codePoints().count());
        System.out.println("UTF-8 bytes: " + utf8.length);
        System.out.println("Points: " +
            Arrays.toString(value.codePoints().toArray()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnicodeEncodingSizesDemo.java
java UnicodeEncodingSizesDemo
~~~

Stdout:

~~~text
UTF-16 units: 3
Code points: 2
UTF-8 bytes: 5
Points: [65, 128512]
~~~

Điều này đặc biệt hữu ích khi thiết kế giới hạn độ dài:

- Một protocol có giới hạn **byte count** không thể dùng String.length() thay thế.
- Một yêu cầu UI giới hạn **số ký tự hiển thị** không thể đơn giản dùng codePoints().count() trong mọi ngôn ngữ.
- Một thuật toán thao tác theo **UTF-16 offsets** phải dùng char indices, ngay cả khi hiển thị văn bản theo code points.

Phân biệt đúng đại lượng trước khi chọn API là quan trọng hơn việc cố gắng sử dụng Stream cho mọi phép đo.

---

## 19. So sánh những API liên quan

| API | Đơn vị/kết quả | Khi nào dùng |
| --- | --- | --- |
| **CharSequence.length()** | Số UTF-16 code units | Chỉ số char, buffer length |
| **CharSequence.charAt(i)** | Một char UTF-16 | Truy cập một code unit |
| **CharSequence.chars()** | IntStream của các char values | Duyệt code units |
| **CharSequence.codePoints()** | IntStream các code point values | Duyệt Unicode code points |
| **String.codePointCount(a,b)** | Số code points trong khoảng UTF-16 | Đếm mà không cần pipeline |
| **String.codePointAt(i)** | Code point tại UTF-16 index | Đọc một code point |
| **String.offsetByCodePoints(i,k)** | UTF-16 index sau khi đi k code points | Chuyển chỉ số |
| **Character.toChars(cp)** | char[] UTF-16 cho code point | Dựng String đúng với bổ sung |
| **StringBuilder.appendCodePoint(cp)** | Append mã code point thành UTF-16 | Ghép text từ int stream |
| **String.getBytes(UTF_8)** | byte[] theo UTF-8 | Đếm/gửi/ghi bytes |
| **Normalizer.normalize(...)** | Chuỗi được chuẩn hóa Unicode | So sánh dạng composed/decomposed khi phù hợp |

**Nên dùng String.codePointCount hay codePoints().count()?** Nếu chỉ cần đếm code points của String trong một khoảng UTF-16, **codePointCount** biểu đạt ý định trực tiếp. Nếu đồng thời cần lọc, map hoặc tổng hợp các thuộc tính code point, **codePoints()** kết hợp IntStream thường tự nhiên hơn.

### Về tên gọi char và character

Một người học có thể đọc “char” thành “ký tự”; nhưng khi xử lý Unicode, từ đó mơ hồ. Trong tài liệu kỹ thuật, hãy phân biệt rõ:

- **char** = UTF-16 code unit trong Java.
- **code point** = giá trị mã Unicode, có thể cần một hoặc hai code units.
- **grapheme cluster** = nhóm code points mà người dùng nhìn nhận như một ký tự hiển thị, theo quy tắc phân đoạn.

Việc gọi codePoints() không tự giải quyết toàn bộ vấn đề Unicode text processing, nhưng nó là bước đúng nếu thuật toán thật sự hoạt động trên code points.

## 20. Những sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| **chars()** được hiểu là mỗi ký tự hiển thị | chars() phát UTF-16 code units | Dùng codePoints() nếu cần code points |
| **String.length()** được hiểu là số Unicode code points | UTF-16 surrogate pair cần 2 chars | Dùng codePointCount/codePoints |
| **codePoints()** được hiểu là số grapheme clusters | Combining marks/ZWJ có thể tạo nhiều code points cho một grapheme | Dùng segmentation phù hợp |
| Cast **(char) cp** cho mọi code point | Mất thông tin với cp > U+FFFF | Character.toChars / appendCodePoint |
| Giả định codePoints() tự sửa unpaired surrogate | API phát giá trị surrogate không ghép như int | Validate/replace theo chính sách |
| Chỉ dùng **isValidCodePoint** để kiểm tra well-formed scalar | Surrogate range vẫn nằm trong miền số code point | Kiểm tra cả surrogate range |
| Dùng **Character.isDigit** mà nghĩ chỉ nhận 0..9 ASCII | Unicode digit classification rộng hơn | Viết rõ ASCII range nếu cần |
| Dùng Character.toUpperCase cho toàn bộ case mapping | Một số mapping có thể cần nhiều ký tự/locale | Dùng String.toUpperCase(Locale) |
| Dùng chars().filter(Character::isLetter) cho mọi Unicode | Surrogate bổ sung bị tách | Dùng codePoints().filter(...) |
| Chỉ số substring được hiểu là code point index | substring dùng UTF-16 offsets | offsetByCodePoints |
| Sửa StringBuilder khi Stream đang được duyệt | Hành vi không được xác định theo API | Snapshot hoặc kiểm soát việc sửa |
| Nghĩ StringBuffer synchronized nên Stream tự là snapshot | Đồng bộ từng phương thức không tạo contract snapshot | Chụp String trước khi stream |
| Gọi count và toArray trên cùng IntStream | Stream single-use | Gọi codePoints() mới mỗi lần |
| Nhầm UTF-8 byte với String.length | Hai đơn vị mã hóa khác nhau | getBytes(UTF_8).length khi cần bytes |
| Dùng **Stream<Character>** như kiểu trả về của chars() | chars() trả IntStream | Nhận IntStream hoặc mapToObj |
| Hiển thị String từ một surrogate riêng và mong emoji đúng | Một surrogate không phải code point bổ sung hoàn chỉnh | Ghép cặp đúng hoặc dùng codePoints() |
| Xây pipeline có side effects và mong luôn chạy mỗi phần tử | Stream lazy, short-circuit, optimizer | Dùng phép tổng hợp có hợp đồng rõ |

## 21. Đọc CharSequence không đồng nghĩa giải mã encoding

**CharSequence.chars()** và **codePoints()** hoạt động trên các giá trị char mà CharSequence đã biểu diễn. Nếu dữ liệu đầu vào là **bytes từ UTF-8**, trước tiên bạn cần giải mã bytes bằng charset phù hợp để có văn bản Java.

Không nên lấy từng byte UTF-8 rồi cast sang char để tạo String khi dữ liệu có ký tự ngoài ASCII; cách này có thể làm hỏng Unicode và codePoints() sau đó không thể khôi phục nội dung gốc từ một bước giải mã sai.

Ví dụ đúng với dữ liệu UTF-8:

~~~java
String text = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);

int[] points = text.codePoints().toArray();
~~~

Đây là đoạn minh họa cần biến bytes kiểu byte[]. Với dữ liệu byte không hợp lệ, các decoder có chính sách lỗi/thay thế khác nhau; nếu ứng dụng cần phát hiện encoding lỗi thay vì âm thầm thay thế, hãy cấu hình decoder/CharsetDecoder thích hợp.

Ngược lại, từ String sang bytes:

~~~java
byte[] bytes = text.getBytes(
    java.nio.charset.StandardCharsets.UTF_8);
~~~

Đây là bước **encoding**, khác với codePoints() vốn chỉ trả các giá trị int của văn bản đã được biểu diễn trong Java.

## 22. Unicode và hiệu năng: đừng tối ưu bằng cách phá đúng kiểu

**chars()** có thể xử lý ít logic hơn codePoints() ở vài trường hợp vì không cần ghép surrogate pairs; tuy nhiên, điều này **không** khiến chars() phù hợp để thay thế codePoints() trong thuật toán đếm code points. Một tối ưu sai đơn vị dữ liệu sẽ cho kết quả sai.

Một số gợi ý thực hành:

- Nếu dữ liệu được xác định chắc là ASCII, chars() hoặc các phép duyệt trực tiếp trên char có thể đơn giản.
- Nếu yêu cầu về Unicode code points, dùng codePoints() dù phải xử lý surrogate pairs.
- Nếu chỉ cần count code points của String, **String.codePointCount(...)** có thể diễn đạt rõ hơn việc dựng một stream.
- Nếu cần một danh sách String của từng code point, **mapToObj(cp -> new String(Character.toChars(cp)))** là cách rõ nghĩa, nhưng có tạo đối tượng mới.
- Nếu chỉ cần cộng, lọc hoặc thống kê số, giữ **IntStream** lâu nhất có thể để tránh boxing không cần thiết.
- Nếu cần dựng lại một chuỗi, **appendCodePoint** vào StringBuilder có thể tự nhiên hơn việc tạo nhiều String trung gian.
- Với dữ liệu lớn, hãy đo benchmark trong môi trường thực và không suy luận hiệu năng từ một ví dụ vài ký tự.

Đặc biệt, việc dùng **parallel()** không tự làm xử lý văn bản Unicode nhanh hơn. Truy cập nguồn, thao tác thứ tự, chi phí phân tách và mức độ phức tạp của pipeline đều ảnh hưởng hiệu quả. Trước khi song song hóa, hãy bảo đảm thuật toán đúng ở chế độ tuần tự.

## 23. Bài tập thực hành có đáp án

### Bài 1 — ASCII

Với String "ABC", **chars().toArray()** và **codePoints().toArray()** khác nhau không?

**Đáp án:** không. Cả hai đều cho **[65, 66, 67]**, vì mỗi ký tự ASCII cũng là một code point BMP một code unit.

### Bài 2 — Một emoji bổ sung

Với String chứa chỉ U+1F600 bằng cặp surrogate U+D83D U+DE00, count của hai stream là bao nhiêu?

**Đáp án:** **chars().count() = 2** và **codePoints().count() = 1**.

### Bài 3 — Đếm chuỗi A + emoji + B

Với **"A\uD83D\uDE00B"**, String.length(), codePoints().count() và codePointCount(0,length()) cho gì?

**Đáp án:** **4, 3, 3**.

### Bài 4 — Cast int sang char

Vì sao **(char) 128512** không thể dùng để tạo đúng String của emoji U+1F600?

**Đáp án:** char chỉ có 16 bit; cast làm mất thông tin cao của code point. Dùng **Character.toChars(128512)** hoặc **StringBuilder.appendCodePoint(128512)**.

### Bài 5 — Unpaired surrogate

Nếu chuỗi có một high surrogate không có low surrogate liền kề, codePoints() có tự thay bằng U+FFFD không?

**Đáp án:** **không**. Nó đưa ra giá trị surrogate đó như một int. Muốn thay thế/cấm phải có quy tắc validation riêng.

### Bài 6 — isValidCodePoint

**Character.isValidCodePoint(0xD83D)** có đủ để kết luận đây là một Unicode scalar value độc lập không?

**Đáp án:** không. Vùng surrogate nằm trong miền số được kiểm tra bởi phương thức này nhưng không phải một scalar value độc lập; kiểm tra thêm vùng U+D800..U+DFFF.

### Bài 7 — Chuỗi có dấu

Vì sao **"\u00E9"** và **"e\u0301"** có thể hiển thị giống nhau nhưng codePoints().count() khác?

**Đáp án:** chúng là hai biểu diễn Unicode khác nhau: một composed code point và hai code points gồm ký tự gốc + combining mark. Cần chính sách normalization nếu muốn so sánh tương đương chuẩn hóa.

### Bài 8 — Dời vị trí

Từ chuỗi **"A\uD83D\uDE00B"**, muốn lấy substring bắt đầu sau hai code points đầu tiên, index UTF-16 cần là bao nhiêu?

**Đáp án:** **3**, có thể tính bằng **offsetByCodePoints(0,2)**. Index 2 là low surrogate, không phải ranh giới sau emoji.

### Bài 9 — Character.isLetter

Trong văn bản có chữ ngoài BMP, nên dùng chars().filter(Character::isLetter) hay codePoints().filter(Character::isLetter)?

**Đáp án:** **codePoints()** nếu yêu cầu là đếm các **Unicode letter code points**, vì chars() có thể tách một ký tự bổ sung thành hai surrogate.

### Bài 10 — Nguồn mutable

Nếu StringBuilder bị sửa trong lúc terminal operation đọc một Stream từ builder.codePoints(), có thể dự đoán kết quả nào?

**Đáp án:** không; hợp đồng CharSequence cho biết kết quả không được xác định nếu sequence bị thay đổi trong lúc Stream được đọc. Dùng snapshot **builder.toString()** hoặc kiểm soát việc sửa nguồn.

### Bài 11 — Hai lần terminal

Một IntStream lấy từ text.codePoints() đã gọi count(); có thể gọi lại toArray() trên chính IntStream đó không?

**Đáp án:** không. Tạo Stream mới bằng **text.codePoints()** cho lượt tiếp theo.

### Bài 12 — Byte count

Với String "A" + U+1F600, vì sao UTF-8 bytes có thể nhiều hơn số code points?

**Đáp án:** UTF-8 là encoding nhiều byte cho một code point bổ sung. Ví dụ có **2 code points**, **3 UTF-16 code units**, nhưng **5 UTF-8 bytes**.

### Bài 13 — Stream<String> từ codePoints

Để biểu diễn mỗi Unicode code point thành một String riêng, cần dùng cách nào?

**Đáp án:**

~~~java
List<String> pieces = text.codePoints()
    .mapToObj(cp -> new String(Character.toChars(cp)))
    .collect(Collectors.toList());
~~~

Đây là đoạn minh họa cần import List và Collectors. Cách này giữ được code point bổ sung, khác với cast trực tiếp sang char.

### Bài 14 — Code points và giao diện người dùng

Có thể dùng **codePoints().count()** làm độ dài hiển thị của mọi emoji ZWJ hoặc mọi chữ có dấu không?

**Đáp án:** không. Một grapheme cluster có thể gồm nhiều code points. Nếu ứng dụng cần giới hạn số ký tự hiển thị, cần thuật toán segmentation theo grapheme phù hợp, không chỉ đếm code points.

### Bài 15 — Chọn API

Khi nào chỉ dùng String.codePointCount(...) thay vì một IntStream?

**Đáp án:** khi cần **đếm** code points trong một khoảng String mà không có filter/map/collect. Nếu cần phân loại, biến đổi hoặc tổng hợp theo code point, **codePoints()** là nguồn stream thích hợp.

## 24. Checklist khi xử lý text Unicode bằng Stream

**Xác định yêu cầu dữ liệu:**

- Đang đếm **UTF-16 code units**, **Unicode code points**, **grapheme clusters** hay **UTF-8 bytes**?
- Dữ liệu có thể chứa surrogate pairs, combining marks hoặc emoji ZWJ không?
- Source là String immutable hay CharSequence có thể thay đổi?
- Nếu có dữ liệu UTF-16 lỗi, chính sách là reject, replace hay giữ nguyên?

**Chọn API:**

- chars() khi làm việc với các **char values/code units**.
- codePoints() khi cần các **Unicode code point values**.
- codePointCount nếu chỉ đếm trên String.
- offsetByCodePoints để chuyển vị trí code point về **UTF-16 index**.
- Character.toChars/appendCodePoint để dựng lại supplementary characters.
- String.getBytes(StandardCharsets.UTF_8) khi cần byte length thật.
- Normalizer khi cần quan hệ tương đương chuẩn hóa Unicode, theo hợp đồng dữ liệu.

**Kiểm tra an toàn:**

- Không cast int code point sang char một cách mù quáng.
- Không coi codePoints() là bộ sửa unpaired surrogate.
- Không sửa CharSequence mutable trong lúc Stream đang đọc.
- Không dùng lại IntStream sau terminal operation.
- Không nhầm Unicode digit/letter classification với validation ASCII-only.
- Không nhầm code point count với số grapheme clusters.

**Đánh giá kết quả:**

- Test ASCII đơn giản.
- Test một code point bổ sung U+1F600.
- Test composed/decomposed text.
- Test unpaired high và low surrogate.
- Test các chỉ số UTF-16 sau một surrogate pair.
- Test dữ liệu nguồn mutable qua snapshot.
- Test Unicode bytes nếu dữ liệu được gửi qua mạng hoặc lưu file.

## Tổng kết

**CharSequence.chars()** và **CharSequence.codePoints()** là hai cách tạo **IntStream từ văn bản** được bổ sung ở Java 8 và vẫn quan trọng trên JDK hiện đại.

**chars()** phát ra từng **UTF-16 code unit**, được mở rộng thành int. **codePoints()** phát ra từng **Unicode code point**, ghép đúng high/low surrogate pairs thành một giá trị lớn hơn U+FFFF. Vì vậy một ký tự bổ sung có thể tạo **hai phần tử trong chars()** nhưng chỉ **một phần tử trong codePoints()**.

Khi xử lý Unicode, hãy phân biệt **code unit**, **code point**, **grapheme cluster** và **byte encoding**. Đừng cast code point lớn sang char, đừng coi codePoints() tự sửa surrogate lỗi, và đừng sửa CharSequence mutable khi Stream đang được đọc. Dùng **Character.toChars**, **appendCodePoint**, **offsetByCodePoints**, **Normalizer** hoặc các công cụ phân đoạn Unicode khi bài toán thật sự yêu cầu.

Nếu biết rõ đơn vị mà thuật toán cần thao tác và chọn API cho đúng đơn vị đó, bạn sẽ tránh được nhiều lỗi Unicode tinh vi trong xử lý chuỗi bằng Java Stream.