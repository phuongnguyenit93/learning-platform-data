# Lọc, đếm và biến đổi dữ liệu bằng IntStream trong Java String

## Mục tiêu bài học

Một `String` có thể tạo ra một `IntStream` để xử lý từng đơn vị ký tự dưới dạng số nguyên, từ đó lọc những phần tử cần giữ, đếm số phần tử thỏa điều kiện, tính tổng hoặc biến đổi dữ liệu. Sau bài này, bạn có thể:

- Dùng `String.chars()` và `String.codePoints()` đúng mục đích, hiểu sự khác nhau giữa **UTF-16 code unit** và **Unicode code point**.
- Tạo pipeline với `filter`, `map`, `mapToObj` và các phép kết thúc như `count`, `sum`, `collect`.
- Chuyển kết quả xử lý các code point về `String` bằng `StringBuilder.appendCodePoint`.
- Nhận diện bẫy của Unicode, phép đếm, luồng dùng một lần và các phép biến đổi chữ hoa/chữ thường.

## 1. IntStream là gì, và vì sao String trả về IntStream?

`java.util.stream.IntStream` là một *primitive stream*: nó biểu diễn một chuỗi giá trị `int`, hỗ trợ các thao tác xử lý theo pipeline mà không phải bọc từng phần tử thành `Integer`. Đây là stream xử lý dữ liệu **trong bộ nhớ**, không phải `InputStream` dùng để đọc byte từ tệp hoặc mạng.

`String` cung cấp hai phương thức quan trọng:

~~~java
IntStream utf16Units = text.chars();
IntStream unicodePoints = text.codePoints();
~~~

- `chars()` tạo luồng các **UTF-16 code unit** của chuỗi; mỗi giá trị được mở rộng từ `char` thành `int`. Một Unicode supplementary character (ví dụ emoji nhiều ký tự trong UTF-16) sẽ trở thành hai phần tử surrogate riêng.
- `codePoints()` tạo luồng các **Unicode code point**; hai surrogate hợp lệ liên tiếp được kết hợp thành một code point. Những code unit thông thường vẫn là một phần tử. Đây thường là lựa chọn phù hợp để lọc hoặc kiểm tra ký tự theo các phương thức `Character.isLetter(int)`, `Character.isDigit(int)`.
- Cả hai phương thức đều **không** tự động tách “chữ nhìn thấy trên màn hình” (*grapheme cluster*). Một ký tự hiển thị có thể gồm nhiều code point, chẳng hạn chữ cái cộng dấu kết hợp hoặc emoji nối bằng ký tự Zero Width Joiner.

Nếu chỉ làm việc với mã ASCII, kết quả của `chars()` và `codePoints()` thường trùng nhau; với nội dung đa ngôn ngữ, nên quyết định dựa trên đơn vị bạn cần xử lý.

### Ví dụ kiểm chứng UTF-16 và code point

Lưu vào `UnicodeStreamDemo.java`:

~~~java
import java.util.stream.Collectors;

public class UnicodeStreamDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println(text.length());
        System.out.println(text.chars().count());
        System.out.println(text.codePoints().count());

        String values = text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));
        System.out.println(values);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 UnicodeStreamDemo.java
java UnicodeStreamDemo
~~~

Kết quả:

~~~text
4
4
3
U+0041, U+1F600, U+0042
~~~

`"A😀B"` có ba Unicode code point nhưng bốn UTF-16 code unit, do `😀` được lưu bằng một cặp surrogate. `String.length()` và `chars().count()` đều phản ánh số code unit trong ví dụ; `codePoints().count()` phản ánh số code point. **Đừng gọi cả ba kết quả là “số ký tự người dùng nhìn thấy”.**

## 2. Pipeline gồm những bước nào?

Một pipeline thường có ba thành phần:

~~~text
String.codePoints()      // nguồn: IntStream của code point
  .filter(...)            // thao tác trung gian: giữ các giá trị thỏa điều kiện
  .map(...)               // thao tác trung gian: biến đổi int -> int
  .count()                // thao tác kết thúc: trả về long
~~~

Các phép trung gian như `filter`, `map`, `distinct`, `sorted`, `limit` thường tạo một luồng mới mô tả việc sẽ xử lý, nhưng chưa chạy toàn bộ dữ liệu ngay. Thao tác kết thúc như `count`, `sum`, `forEach` hoặc `collect` sẽ kích hoạt pipeline (ngoại trừ những tối ưu hóa hợp lệ của thư viện Stream). Mỗi stream chỉ được tiêu thụ một lần.

| Phép toán | Đặc điểm | Ví dụ trong bài |
| --- | --- | --- |
| `filter(IntPredicate)` | Giữ giá trị `int` khi predicate trả về `true` | Lọc chữ số với `Character::isDigit` |
| `map(IntUnaryOperator)` | Đổi mỗi `int` thành một `int` khác | Đổi code point thành chữ in hoa |
| `mapToObj(IntFunction<R>)` | Đổi từ `int` thành object | Biến code point thành chuỗi `"U+...."` |
| `distinct()` | Loại giá trị `int` trùng nhau | Lấy danh sách code point duy nhất |
| `sorted()` | Sắp xếp giá trị số nguyên | Sắp theo mã code point |
| `count()` | Trả về số phần tử kiểu `long` | Đếm chữ số |
| `sum()` | Tính tổng kiểu `int` | Cộng các chữ số ASCII sau khi đổi mã |
| `findFirst()` | Tìm phần tử đầu tiên, trả về `OptionalInt` | Tìm code point số đầu tiên |
| `collect(...)` | Gom kết quả bằng container mutable | Xây dựng `StringBuilder` |

`filter` không sửa `String` gốc: `String` là bất biến (*immutable*). Nếu cần kết quả thành chuỗi mới, bạn phải thu gom các phần tử còn lại vào cấu trúc hoặc đối tượng khác.

## 3. Lọc, đếm và tính tổng chữ số

Giả sử đầu vào là `"a1B2c3😀"`. Ta muốn đếm code point dạng chữ số, đếm dạng chữ cái và tính tổng **giá trị các chữ số ASCII**.

Lưu vào `FilterCountDemo.java`:

~~~java
public class FilterCountDemo {
    public static void main(String[] args) {
        String text = "a1B2c3😀";

        long digitCount = text.codePoints()
                .filter(Character::isDigit)
                .count();

        long letterCount = text.codePoints()
                .filter(Character::isLetter)
                .count();

        int asciiDigitSum = text.codePoints()
                .filter(cp -> cp >= '0' && cp <= '9')
                .map(cp -> cp - '0')
                .sum();

        System.out.println("Digits: " + digitCount);
        System.out.println("Letters: " + letterCount);
        System.out.println("ASCII digit sum: " + asciiDigitSum);
    }
}
~~~

Chạy bằng `javac -encoding UTF-8 FilterCountDemo.java` và `java FilterCountDemo`:

~~~text
Digits: 3
Letters: 3
ASCII digit sum: 6
~~~

Từng bước:

1. `codePoints()` tạo luồng gồm `a`, `1`, `B`, `2`, `c`, `3`, `😀` (đại diện dưới dạng `int`).
2. `filter(Character::isDigit)` chỉ giữ ba chữ số và `count()` cho `3L` (kiểu `long`).
3. `filter(Character::isLetter)` giữ `a`, `B`, `c` nên kết quả cũng là `3L`.
4. Bộ lọc `cp >= '0' && cp <= '9'` chủ động giới hạn ở **ASCII 0–9**. Sau đó `map(cp -> cp - '0')` đổi mã của `'1'`, `'2'`, `'3'` thành giá trị số 1, 2, 3, rồi `sum()` cho `6`.

**Cẩn thận:** `Character.isDigit(int)` có thể nhận diện chữ số của nhiều hệ chữ viết ngoài ASCII. Vì vậy, không được tùy tiện dùng `cp - '0'` cho tất cả code point mà `isDigit` chấp nhận. Nếu cần giá trị số của chữ số Unicode, dùng `Character.digit(cp, 10)` và xử lý kết quả `-1` khi không có giá trị ở hệ cơ số yêu cầu.

Ví dụ `codePoints().filter(Character::isDigit).count()` là phép **đếm số code point thuộc loại chữ số**, không tự động cho biết giá trị số, số chữ trong một chuỗi và cũng không xác thực rằng toàn bộ input là số. Muốn kiểm tra toàn chuỗi, có thể dùng `String.matches` với mẫu phù hợp hoặc kiểm tra tất cả code point và quy tắc độ dài riêng.

## 4. Biến đổi và giữ lại ký tự để tạo chuỗi mới

`map` trong `IntStream` trả về một `int` cho mỗi phần tử đầu vào. Khi làm việc với Unicode code point, phải tạo chuỗi đầu ra bằng thao tác hiểu **code point**, thay vì ép `int` thành `char`.

Ví dụ muốn lấy các code point thuộc chữ cái rồi đổi thành chữ in hoa. Lưu `TransformStreamDemo.java`:

~~~java
public class TransformStreamDemo {
    public static void main(String[] args) {
        String text = "a1B2c3😀";

        String result = text.codePoints()
                .filter(Character::isLetter)
                .map(Character::toUpperCase)
                .collect(
                        StringBuilder::new,
                        (builder, cp) -> builder.appendCodePoint(cp),
                        StringBuilder::append)
                .toString();

        System.out.println(result);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TransformStreamDemo.java
java TransformStreamDemo
~~~

Kết quả:

~~~text
ABC
~~~

Ý nghĩa các bước:

- `filter(Character::isLetter)` loại chữ số và emoji khỏi ví dụ, giữ `a`, `B`, `c`.
- `map(Character::toUpperCase)` biến mỗi code point thành code point in hoa tương ứng nếu có.
- `collect(supplier, accumulator, combiner)` tạo một `StringBuilder`, nối từng code point bằng `appendCodePoint` và cung cấp thao tác gộp các builder (nếu pipeline được xử lý theo nhánh song song); `toString()` lấy chuỗi kết quả.

Tại sao không dùng `(char) cp`? Vì phép ép kiểu đó chỉ giữ 16 bit thấp và có thể phá hỏng ký tự ngoài Basic Multilingual Plane. `StringBuilder.appendCodePoint(int)` bổ sung đúng một hoặc hai UTF-16 code unit cho code point hợp lệ.

**Giới hạn của phép đổi hoa bằng code point:** `Character.toUpperCase(int)` chỉ trả về **một** code point trên mỗi đầu vào và không xử lý đầy đủ những quy tắc đổi hoa phụ thuộc ngôn ngữ hoặc cần mở rộng thành nhiều ký tự. Nếu bài toán là chuyển **cả chuỗi** thành chữ in hoa theo ngôn ngữ, hãy cân nhắc `text.toUpperCase(locale)` và chính sách chuẩn hóa Unicode, thay vì cho rằng pipeline trên luôn cho cùng kết quả.

## 5. Dùng mapToObj khi muốn kết quả không còn là int

`mapToObj` hữu ích nếu mỗi code point cần được biểu diễn thành một object, chẳng hạn chuỗi nhãn hoặc đối tượng dữ liệu. Ví dụ:

~~~java
import java.util.stream.Collectors;

public class CodePointListDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        String names = text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));

        System.out.println(names);
    }
}
~~~

Lưu thành `CodePointListDemo.java`, biên dịch và chạy bằng `javac -encoding UTF-8 CodePointListDemo.java` rồi `java CodePointListDemo`. Kết quả:

~~~text
U+0041, U+1F600, U+0042
~~~

Ở đây `mapToObj` chuyển từng `int` thành `String`; sau đó `Collectors.joining(", ")` ghép các phần thành một chuỗi. Đây là hướng phù hợp khi cần hiển thị metadata cho từng code point. Nếu chỉ cần tạo lại chuỗi Unicode từ các code point đã được lọc/biến đổi, cách `collect(StringBuilder::new, ...appendCodePoint..., StringBuilder::append)` ở phần trước tránh tạo nhiều chuỗi trung gian nhỏ.

## 6. Khi nào nên dùng chars(), codePoints() hoặc IntStream.range()?

Ba cách đều có ích nhưng trả lời những câu hỏi khác nhau:

| Nguồn | Đơn vị duyệt | Phù hợp nhất |
| --- | --- | --- |
| `text.chars()` | UTF-16 code unit (`char` dạng `int`) | Xử lý mã ASCII, thao tác rõ ràng dựa trên `char` hoặc code unit |
| `text.codePoints()` | Unicode code point (`int`) | Lọc/đếm chữ cái, chữ số, ký tự Unicode và biến đổi theo `Character` |
| `IntStream.range(0, text.length())` | Chỉ số `char` 0 đến `length() - 1` | Khi cần **vị trí UTF-16** (offset) của ký tự theo `charAt` |

Ví dụ tìm chỉ số UTF-16 của chữ cái trong chuỗi ASCII:

~~~java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class IndexStreamDemo {
    public static void main(String[] args) {
        String text = "a1B2";

        String positions = IntStream.range(0, text.length())
                .filter(i -> Character.isLetter(text.charAt(i)))
                .mapToObj(i -> i + ":" + text.charAt(i))
                .collect(Collectors.joining(", "));

        System.out.println(positions);
    }
}
~~~

Lưu `IndexStreamDemo.java`, chạy `javac -encoding UTF-8 IndexStreamDemo.java` và `java IndexStreamDemo`. Kết quả:

~~~text
0:a, 2:B
~~~

Mẫu này phù hợp với `"a1B2"` vì toàn bộ dữ liệu ở ASCII. Với Unicode supplementary character, `charAt(i)` chỉ trả về một surrogate của cặp và chỉ số `i` là **offset code unit**, không phải chỉ số code point. Khi cần offset theo code point, hãy xem `String.offsetByCodePoints`, `String.codePointAt` hoặc cơ chế duyệt có quản lý offset. Không đánh đồng chỉ số code unit với vị trí “ký tự thứ N” trong văn bản hiển thị.

### Đếm code point không phải đếm grapheme cluster

Ví dụ ký tự `é` có thể được biểu diễn bằng một code point `U+00E9` hoặc hai code point `U+0065` và `U+0301` (chữ `e` kèm dấu kết hợp). `codePoints().count()` có thể cho số đếm khác nhau với hai chuỗi trông giống nhau. Với emoji có thành phần kết hợp, một hình hiển thị cũng có thể có nhiều code point.

Nếu yêu cầu của sản phẩm là đếm “ký tự người dùng nhìn thấy”, cắt chuỗi theo ranh giới grapheme hoặc áp giới hạn ký tự trên ô nhập, chỉ dùng `IntStream` theo code point là chưa đủ. Cần bộ phân đoạn Unicode phù hợp và cân nhắc chuẩn hóa văn bản cho bài toán cụ thể.

## 7. Pipeline được chạy một lần, và phép đếm không có tác dụng phụ mong muốn

Một lỗi thường gặp là lưu `IntStream` rồi cố dùng lại:

~~~java
// Minh họa lỗi: không phải chương trình hoàn chỉnh.
var stream = "A1B2".codePoints();
long count = stream.filter(Character::isDigit).count();
// stream.count(); // Sai: stream đã được tiêu thụ, sẽ ném IllegalStateException.
~~~

Tạo **stream mới** cho mỗi phép kết thúc:

~~~java
String text = "A1B2";
long digitCount = text.codePoints()
        .filter(Character::isDigit)
        .count();
long letterCount = text.codePoints()
        .filter(Character::isLetter)
        .count();
~~~

Không nhét side effect vào `filter`/`map` chỉ để đếm số lần gọi. Thư viện Stream có thể tối ưu hóa pipeline; ví dụ, `count()` trên nguồn có kích thước đã biết có thể trả về kết quả mà không cần chạy các phép trung gian không ảnh hưởng số lượng. Hãy dùng kết quả trả về từ thao tác kết thúc để xác định đầu ra, thay vì giả định mọi phép trung gian đều chạy đúng một lần cho mỗi phần tử.

`forEach` cũng không đảm bảo thứ tự quan sát trong stream song song; nếu thật sự cần thứ tự gặp phần tử (*encounter order*), có `forEachOrdered`. Với xử lý ký tự chuỗi thông thường, hãy ưu tiên pipeline tuần tự, ngắn và dễ hiểu trước khi cân nhắc parallelization.

## 8. Kỹ thuật bổ sung: tìm, loại trùng và giới hạn

Một số nhu cầu thực tế ngoài lọc/đếm/biến đổi:

~~~java
import java.util.OptionalInt;

public class MoreIntStreamDemo {
    public static void main(String[] args) {
        String text = "a1b2a3";

        OptionalInt firstDigit = text.codePoints()
                .filter(Character::isDigit)
                .findFirst();
        System.out.println(firstDigit.isPresent()
                ? Character.toString(firstDigit.getAsInt())
                : "Không có");

        long uniqueLetters = text.codePoints()
                .filter(Character::isLetter)
                .distinct()
                .count();
        System.out.println(uniqueLetters);
    }
}
~~~

Lưu `MoreIntStreamDemo.java` rồi chạy `javac -encoding UTF-8 MoreIntStreamDemo.java` và `java MoreIntStreamDemo`. Kết quả:

~~~text
1
2
~~~

`findFirst()` trả về `OptionalInt`, vì có thể không có phần tử phù hợp; nên dùng `isPresent`/`orElse`/`ifPresent` tùy ngữ cảnh thay vì gọi `getAsInt()` vô điều kiện. `distinct()` loại code point trùng nhau; trong ví dụ có hai chữ cái khác nhau là `a` và `b`. Phép này so sánh **giá trị code point**, không tự gom các cách viết Unicode tương đương hoặc so sánh không phân biệt hoa/thường.

`limit(n)` có thể giới hạn số phần tử đi tiếp trong stream, nhưng giới hạn `n` **code point** không nhất thiết là giới hạn `n` ký tự hiển thị trên UI. Với `sorted()`, thứ tự là thứ tự số nguyên của code point, không phải thứ tự bảng chữ cái theo `Locale`.

## 9. Lỗi thường gặp

**1. Chọn chars() cho văn bản đa ngôn ngữ rồi xem mỗi phần tử là một ký tự Unicode.** Surrogate pair bị tách làm hai, nên phép lọc theo `Character.isLetter(int)` hoặc khôi phục bằng cast `char` có thể sai. Dùng `codePoints()` khi xử lý code point.

**2. Đếm count() rồi nghĩ đó là số ký tự trên màn hình.** `chars().count()` là số UTF-16 code unit; `codePoints().count()` là số Unicode code point; không cách nào mặc nhiên đếm đúng grapheme cluster.

**3. Nhầm đếm với tổng.** `filter(...).count()` đếm số phần tử phù hợp; `filter(...).map(...).sum()` cộng các giá trị sau biến đổi. `count()` trả `long`; `sum()` của `IntStream` trả `int` và có khả năng tràn số khi giá trị quá lớn.

**4. Biến đổi mã code point bằng cast char.** `(char) cp` có thể làm mất phần mã cao. Dùng `appendCodePoint` hoặc `Character.toChars(cp)` khi xây chuỗi.

**5. Áp dụng cp - '0' cho mọi chữ số Unicode.** Phép trừ đơn giản chỉ đúng theo giả định mã chữ số ASCII liên tiếp. Nếu cần số Unicode, hãy dùng `Character.digit(cp, 10)` và xử lý ký tự không có giá trị số.

**6. Đòi dùng lại một stream đã kết thúc.** Sau `count()`, `sum()`, `collect()` hoặc `forEach()`, hãy gọi lại `text.codePoints()` để tạo pipeline mới.

**7. Đồng nhất toUpperCase(code point) với toUpperCase(Locale).** Chuyển từng code point có thể không xử lý biến thể theo ngôn ngữ hay phép đổi hoa một thành nhiều. Chọn API dựa trên yêu cầu chuyển đổi **ký tự** hay **văn bản**.

**8. Lạm dụng stream cho logic quá đơn giản.** Với kiểm tra một vị trí hoặc thao tác cố định, vòng lặp hay `String` API chuyên biệt có thể rõ ràng hơn. Stream hữu ích khi cần biểu đạt chuỗi phép lọc, biến đổi, kết hợp hoặc thống kê.

**9. Giả định lọc chữ cái sẽ giữ dấu kết hợp đi cùng chữ.** Một dấu combining mark có thể không thỏa `Character.isLetter` và bị xóa, làm thay đổi văn bản. Trước khi lọc ký tự Unicode, hãy định nghĩa chính sách với dấu kết hợp, chuẩn hóa và grapheme.

## 10. Bài tập tự kiểm tra

Cho chuỗi `"A7b0C3"`, dự đoán các biểu thức sau:

~~~java
String value = "A7b0C3";

long digits = value.codePoints()
        .filter(Character::isDigit)
        .count();

int sum = value.codePoints()
        .filter(cp -> cp >= '0' && cp <= '9')
        .map(cp -> cp - '0')
        .sum();

long differentLetters = value.codePoints()
        .filter(Character::isLetter)
        .map(Character::toLowerCase)
        .distinct()
        .count();
~~~

**Đáp án:** `digits = 3` vì có `7`, `0`, `3`; `sum = 10`; `differentLetters = 3` vì ba chữ cái `a`, `b`, `c` khác nhau sau khi đổi về chữ thường.

Bài mở rộng: sửa phép lọc để chỉ nhận chữ cái ASCII `A-Z` hoặc `a-z`; tiếp theo thử chuỗi có `😀` và một chữ có dấu kết hợp, rồi so sánh `length()`, `chars().count()`, `codePoints().count()`. Quan sát những khác biệt để lựa chọn đơn vị xử lý phù hợp.

## Checklist áp dụng vào dự án

1. Xác định đầu vào là ASCII, UTF-16 code unit, Unicode code point hay grapheme cluster.
2. Chọn đúng nguồn `chars()`, `codePoints()` hoặc `IntStream.range(...)` tùy đơn vị.
3. Viết rõ predicate của `filter`, tránh đồng nhất chữ số ASCII với toàn bộ chữ số Unicode.
4. Với `map` trên code point, giữ miền giá trị hợp lệ; khi xây chuỗi dùng `appendCodePoint`.
5. Chọn thao tác kết thúc thích hợp: `count` cho số phần tử, `sum` cho tổng, `findFirst` cho tìm kiếm, `collect` cho ghép chuỗi.
6. Mỗi phép kết thúc cần một stream mới; kiểm tra chuỗi rỗng, ký tự bổ sung, dấu kết hợp và input không phù hợp giả định.

## Tài liệu chính thức

- [Java SE 17 — String.chars() và String.codePoints()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Java SE 17 — StringBuilder.appendCodePoint(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#appendCodePoint(int))
- [Java SE 17 — Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)
