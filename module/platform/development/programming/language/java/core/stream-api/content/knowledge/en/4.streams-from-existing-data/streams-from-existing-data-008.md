# Tạo IntStream từ String.chars và String.codePoints

Khi làm việc với chuỗi trong **Java Stream API**, có hai phương thức rất thuận tiện để đưa dữ liệu ký tự vào một pipeline: `String.chars()` và `String.codePoints()`. Cả hai trả về `IntStream`, nhưng **khác nhau về đơn vị dữ liệu**: một bên duyệt các đơn vị mã UTF-16 (*code unit*), một bên duyệt các điểm mã Unicode (*code point*).

Bài học thuộc phần **Tạo Stream từ dữ liệu có sẵn** của mô-đun **JAVA_STREAM_API**. Ngoài cách tạo nguồn Stream, chúng ta sẽ thực hành `filter`, `map`, `collect`, phép đếm và phép tái tạo chuỗi; đồng thời nhận diện ranh giới về Unicode, pipeline lazy, trạng thái và hiệu năng. Sự khác biệt giữa code unit, code point và ký tự người dùng nhìn thấy quyết định trực tiếp việc xử lý văn bản có đúng hay không.

## 1. Vì sao cần hai cách duyệt chuỗi?

Java biểu diễn nội dung của `String` theo các quy tắc UTF-16 ở cấp API. Phần lớn ký tự phổ biến, như `A`, `7`, `ắ` hoặc `中`, có thể biểu diễn bằng **một** đơn vị mã UTF-16. Những ký hiệu thuộc vùng Unicode bổ sung, chẳng hạn emoji `😀` (U+1F600), cần **một cặp surrogate** gồm hai đơn vị mã UTF-16.

Vì thế, có ba khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa | Ví dụ với `😀` |
| --- | --- | --- |
| UTF-16 code unit | Một giá trị 16 bit được Java thể hiện qua `char` | Hai giá trị: `0xD83D` và `0xDE00` |
| Unicode code point | Một giá trị được Unicode gán cho ký hiệu hoặc thành phần văn bản | Một giá trị: `U+1F600` |
| Grapheme cluster (cụm tự vị) | Đơn vị người dùng có thể cảm nhận là một ký tự | Thường nhìn thấy một emoji `😀` |

Một code point **không phải lúc nào cũng bằng** một grapheme cluster. Ví dụ `e` kết hợp với dấu sắc có thể được biểu diễn bằng hai code point, nhưng người đọc nhìn thành một ký tự có dấu. Emoji ghép bằng ký tự nối không độ rộng (*ZWJ*) cũng có thể gồm nhiều code point mà hiển thị như một hình.

Trong Java:

- `String.length()` đếm **đơn vị mã UTF-16**.
- `String.chars()` lần lượt đưa từng **đơn vị mã UTF-16** vào `IntStream` dưới dạng `int`.
- `String.codePoints()` lần lượt đưa từng **code point** vào `IntStream`, ghép các cặp surrogate hợp lệ thành một giá trị.
- `String.codePointCount(beginIndex, endIndex)` đếm số code point trong một phạm vi chỉ số UTF-16.

Đây là các API có sẵn từ Java 8 qua giao diện `CharSequence`. Các ví dụ đầy đủ trong bài dùng Java 17 để thuận tiện với `Stream.toList()`.

## 2. `String.chars()`: duyệt từng đơn vị mã UTF-16

`chars()` tạo một `IntStream` từ chuỗi. Mỗi phần tử là giá trị `char` được mở rộng thành `int` không dấu (khoảng `0` đến `65535`). Đối với emoji hoặc ký hiệu bổ sung, **mỗi nửa surrogate** được đưa vào luồng như một số riêng.

Ví dụ có thể chạy trực tiếp:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class StringCharsDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        try (IntStream units = text.chars()) {
            System.out.println(Arrays.toString(units.toArray()));
        }

        System.out.println(text.length());
    }
}
```

Kết quả:

```text
[65, 55357, 56832, 66]
4
```

Giải thích:

| Vị trí đơn vị mã UTF-16 | Biểu diễn | Giá trị thập phân |
| --- | --- | ---: |
| 0 | `A` (`U+0041`) | 65 |
| 1 | High surrogate (`0xD83D`) | 55357 |
| 2 | Low surrogate (`0xDE00`) | 56832 |
| 3 | `B` (`U+0042`) | 66 |

Hai giá trị `55357` và `56832` phối hợp để biểu diễn emoji `😀`. Nếu dùng `chars()` để đếm “ký tự” trong chuỗi này, kết quả là **4 đơn vị mã**, dù ta nhìn thấy ba ký hiệu đơn giản là `A`, `😀` và `B`.

### 2.1. Khi nào dùng `chars()`?

`chars()` hữu ích nếu nghiệp vụ thật sự hoạt động theo **đơn vị mã UTF-16** hoặc biết chắc dữ liệu chỉ dùng những ký tự cơ bản, chẳng hạn chuỗi mã ASCII do một giao thức quy định.

Ví dụ, kiểm tra mã sản phẩm có đúng quy ước **chỉ gồm chữ Latin không dấu viết hoa và chữ số ASCII**:

```java
String code = "AB12Z9";

boolean validAsciiCode = !code.isEmpty()
    && code.chars().allMatch(c ->
        (c >= 'A' && c <= 'Z')
        || (c >= '0' && c <= '9')
    );

System.out.println(validAsciiCode); // true
```

Phạm vi yêu cầu đã chủ động giới hạn vào ASCII; do đó duyệt theo `char` không làm sai ý nghĩa. Nếu đầu vào có chữ ngoài ASCII hoặc emoji, biểu thức sẽ từ chối theo đúng chính sách của ví dụ.

Ngược lại, khi đề bài yêu cầu **xử lý toàn bộ chữ cái Unicode** hoặc “duyệt từng ký hiệu Unicode”, `chars()` có thể cắt đôi một ký hiệu thuộc vùng bổ sung và làm phép kiểm tra sai.

## 3. `String.codePoints()`: duyệt theo điểm mã Unicode

`codePoints()` cũng trả về `IntStream`, nhưng khi gặp một **high surrogate đi liền low surrogate hợp lệ**, nó ghép hai đơn vị mã thành một code point.

```java
import java.util.Arrays;

public class StringCodePointsDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println(Arrays.toString(text.chars().toArray()));
        System.out.println(Arrays.toString(text.codePoints().toArray()));

        System.out.println("length = " + text.length());
        System.out.println("chars count = " + text.chars().count());
        System.out.println("codePoints count = " + text.codePoints().count());
        System.out.println(
            "codePointCount = " + text.codePointCount(0, text.length())
        );
    }
}
```

Kết quả:

```text
[65, 55357, 56832, 66]
[65, 128512, 66]
length = 4
chars count = 4
codePoints count = 3
codePointCount = 3
```

Số `128512` tương đương `0x1F600`, chính là code point của `😀`. Như vậy, với chuỗi này, `codePoints().count()` phù hợp hơn nếu mục tiêu là **đếm code point Unicode**.

Cần gọi đúng tên đại lượng: `codePoints().count()` đếm **code point**, không cam kết đếm đúng số ký tự mà người dùng cảm nhận. Trường hợp dấu kết hợp và emoji nhiều thành phần sẽ được xét ở mục 7.

### 3.1. So sánh hai phương thức

| Tiêu chí | `chars()` | `codePoints()` |
| --- | --- | --- |
| Kiểu trả về | `IntStream` | `IntStream` |
| Đơn vị được phát ra | Một UTF-16 code unit | Một Unicode code point khi có cặp surrogate hợp lệ |
| `A` | Một phần tử `65` | Một phần tử `65` |
| `😀` | Hai phần tử `55357`, `56832` | Một phần tử `128512` |
| Có tự gộp dấu kết hợp thành ký tự hiển thị? | Không | Không |
| Phù hợp nhất | Xử lý theo `char`/UTF-16 hoặc giao thức ASCII rõ ràng | Lọc, phân loại, biến đổi các code point Unicode |
| Có cần terminal operation để duyệt? | Có | Có |

**Lưu ý:** Ký tự cơ bản ngoài ASCII như `ê` thường chỉ chiếm một UTF-16 code unit, nhưng điều đó không khiến `chars()` trở thành công cụ Unicode tổng quát. Khác biệt thể hiện rõ nhất với các code point bổ sung.

## 4. Áp dụng `filter`, `map` và phép tổng hợp trên `IntStream`

Vì cả hai phương thức trả về `IntStream`, chúng hỗ trợ các thao tác chuyên cho giá trị nguyên thủy như `filter`, `map`, `mapToObj`, `distinct`, `count`, `anyMatch`, `toArray` và `collect`.

### 4.1. Đếm chữ cái và chữ số Unicode

Cho chuỗi gồm chữ Latin có dấu, chữ số và emoji. Ta có thể dùng `Character.isLetter(int)` và `Character.isDigit(int)` với từng code point:

```java
String input = "Học Java 17 😀";

long letters = input.codePoints()
    .filter(Character::isLetter)
    .count();

long digits = input.codePoints()
    .filter(Character::isDigit)
    .count();

boolean containsEmojiCodePoint = input.codePoints()
    .anyMatch(cp -> cp == 0x1F600);

System.out.println(letters);                  // 7
System.out.println(digits);                   // 2
System.out.println(containsEmojiCodePoint);   // true
```

Giải thích phép đếm chữ: `Học` có 3 chữ cái; `Java` có 4, tổng là **7**. Hai chữ số là `1` và `7`. Emoji không được tính là chữ cái hoặc chữ số.

`Character.isLetter(int)` làm việc trên code point; với `chars()`, một chữ cái Unicode ở vùng bổ sung sẽ bị chia thành surrogate và có thể **không** được nhận diện chính xác.

### 4.2. Chuyển một tập code point thành danh sách

Giả sử muốn lấy từng code point thành một `String` độc lập, để trình bày hoặc xử lý tiếp theo:

```java
import java.util.List;

String text = "A😀B";

List<String> symbols = text.codePoints()
    .mapToObj(cp -> new String(Character.toChars(cp)))
    .toList();

System.out.println(symbols); // [A, 😀, B]
```

`Character.toChars(int)` chuyển một code point hợp lệ thành một hoặc hai giá trị `char`. Hàm khởi tạo `new String(...)` sau đó tạo chuỗi tương ứng. Với dữ liệu Unicode hợp lệ, phương pháp này giữ nguyên những ký hiệu bổ sung.

Không thể thay cơ học bằng:

```java
// Sai nếu mục tiêu là giữ toàn vẹn ký hiệu bổ sung:
List<String> pieces = text.chars()
    .mapToObj(c -> String.valueOf((char) c))
    .toList();
```

Ở phiên bản `chars()`, emoji bị tách thành hai chuỗi chứa các surrogate riêng lẻ. Từng chuỗi đó không tự biểu diễn emoji hoàn chỉnh.

### 4.3. Lọc rồi tái tạo chuỗi bằng `collect`

Một quy tắc làm sạch đơn giản: chỉ giữ những **chữ cái hoặc chữ số Unicode**, bỏ dấu cách, dấu câu và emoji. Với chuỗi có ký tự đã được chuẩn hóa ở dạng dựng sẵn:

```java
String raw = "Café_2026 😀";

String cleaned = raw.codePoints()
    .filter(Character::isLetterOrDigit)
    .collect(
        StringBuilder::new,
        StringBuilder::appendCodePoint,
        StringBuilder::append
    )
    .toString();

System.out.println(cleaned); // Café2026
```

Trong `IntStream.collect(supplier, accumulator, combiner)`:

1. `StringBuilder::new` tạo bộ tích lũy kết quả.
2. `StringBuilder::appendCodePoint` thêm từng code point được giữ lại, kể cả code point cần cặp surrogate.
3. `StringBuilder::append` nối các bộ tích lũy khi cần kết hợp kết quả.

`StringBuilder` là đối tượng có trạng thái, nhưng trạng thái nằm **trong bộ tích lũy do phép collect quản lý**. Đây là mô hình khác với việc cập nhật tùy tiện một `StringBuilder` chung từ nhiều lambda song song. Đối với yêu cầu chuẩn hóa văn bản đầy đủ, cần bổ sung xử lý Unicode normalization và quy tắc nghiệp vụ; ví dụ trên chỉ mô tả cách lọc các loại code point.

### 4.4. `map` trên code point và giới hạn chuyển chữ hoa

`Character.toUpperCase(int)` có thể thực hiện ánh xạ **mỗi code point thành một code point**:

```java
String value = "abc";

String upper = value.codePoints()
    .map(Character::toUpperCase)
    .collect(
        StringBuilder::new,
        StringBuilder::appendCodePoint,
        StringBuilder::append
    )
    .toString();

System.out.println(upper); // ABC
```

Cách này minh họa `map` trong `IntStream`, nhưng **không thay thế đầy đủ** `String.toUpperCase(Locale)`. Một số quy tắc Unicode có thể chuyển **một ký tự thành nhiều ký tự** hoặc phụ thuộc ngôn ngữ; hàm `Character.toUpperCase(int)` chỉ cho một giá trị trả về. Khi mục tiêu là đổi chữ hoa cho văn bản thực tế, nên chọn API xử lý chuỗi với `Locale` phù hợp:

```java
import java.util.Locale;

String normalized = value.toUpperCase(Locale.ROOT);
```

## 5. Phân biệt kiểu `int` với `char` khi xử lý kết quả

`IntStream` chứa `int`, vì vậy phải quyết định một số đang biểu diễn **UTF-16 code unit** hay **Unicode code point** trước khi chuyển ngược thành chuỗi.

Ví dụ nguy hiểm:

```java
String text = "😀";

// Code point U+1F600 không vừa trong 16 bit của char.
int cp = text.codePoints().findFirst().orElseThrow();
char truncated = (char) cp;

System.out.println(cp);                         // 128512
System.out.println(Integer.toHexString(truncated)); // f600
```

Phép ép kiểu `(char) cp` bỏ phần bit cao; kết quả `0xF600` **không phải** ký hiệu `😀`. Khi cần tạo chuỗi từ code point, dùng `Character.toChars` hoặc `StringBuilder.appendCodePoint`.

Để in mã Unicode theo dạng dễ đọc:

```java
String text = "A😀B";

text.codePoints().forEachOrdered(cp ->
    System.out.printf("U+%04X%n", cp)
);
```

Kết quả:

```text
U+0041
U+1F600
U+0042
```

`forEachOrdered` bảo đảm thứ tự gặp của nguồn có thứ tự. Trong pipeline tuần tự, `forEach` thường cũng theo thứ tự; khi chuyển sang song song, `forEach` không cam kết thứ tự hành động, còn `forEachOrdered` đặt ràng buộc thứ tự.

## 6. Chỉ số của String vẫn tính theo UTF-16

`codePoints()` đưa ra một luồng code point nhưng **không làm thay đổi cách đánh chỉ số** của `String`. Các phương thức `charAt`, `substring`, `codePointAt` và `codePointCount` sử dụng chỉ số tính theo UTF-16 code unit ở những vị trí được mô tả trong API.

Xét chuỗi `"A😀B"`:

```java
String text = "A😀B";

System.out.println(text.length());      // 4
System.out.println(text.charAt(0));     // A

int emojiStartOffset = text.offsetByCodePoints(0, 1);
int letterBOffset = text.offsetByCodePoints(0, 2);

System.out.println(emojiStartOffset);   // 1
System.out.println(letterBOffset);      // 3
System.out.println(
    Integer.toHexString(text.codePointAt(emojiStartOffset))
);                                       // 1f600
System.out.println(text.charAt(letterBOffset)); // B
```

`offsetByCodePoints(beginIndex, codePointOffset)` giúp dịch một **số lượng code point** thành **chỉ số UTF-16**. Trong ví dụ, phần tử hiển thị thứ ba là `B` nhưng nằm tại vị trí `char` số `3`, vì emoji chiếm hai đơn vị mã.

Tránh giả định rằng vị trí thứ `k` trong `codePoints()` bằng `charAt(k)`. Nếu mã xử lý cần cắt chuỗi theo vị trí người dùng nhìn thấy, ngay cả chỉ số theo code point cũng có thể chưa đủ khi chuỗi chứa dấu kết hợp hoặc cụm emoji.

## 7. Hai giới hạn Unicode cần nhận diện

### 7.1. Code point không nhất thiết là ký tự hiển thị

Hai chuỗi dưới đây có thể hiển thị tương tự nhau:

```java
String composed = "\u00E9";      // é: một code point U+00E9
String decomposed = "e\u0301";   // e + dấu sắc kết hợp U+0301

System.out.println(composed.codePoints().count());   // 1
System.out.println(decomposed.codePoints().count()); // 2
System.out.println(composed.equals(decomposed));     // false
```

Vì `decomposed` có hai code point, phép `codePoints().filter(Character::isLetter)` có thể **loại dấu kết hợp**: `e` là chữ cái, nhưng `U+0301` là dấu (*mark*), không phải chữ cái theo phép kiểm tra đó. Kết quả có thể mất dấu nếu ta dùng bộ lọc chữ cái như một giải pháp “làm sạch” tổng quát.

Nếu ứng dụng cần so sánh chuỗi tương đương về dạng Unicode, có thể cân nhắc chuẩn hóa bằng `java.text.Normalizer`; nếu cần duyệt **grapheme cluster** như các ký tự người dùng nhìn thấy, cần thuật toán phân đoạn văn bản thích hợp, chẳng hạn `BreakIterator` hoặc thư viện hỗ trợ Unicode phù hợp với phiên bản ứng dụng. Không thể suy ra số grapheme cluster chỉ từ `codePoints().count()`.

### 7.2. Chuỗi chứa surrogate không ghép cặp

Java `String` có thể chứa một **surrogate đơn lẻ**, không ghép với đơn vị mã còn lại thành một cặp hợp lệ. Khi đó `codePoints()` **không thể** tạo một Unicode scalar value hợp lệ từ nó; theo hợp đồng của API, đơn vị mã không ghép cặp được đưa ra như một giá trị `int` riêng.

```java
String malformed = new String(new char[] {(char) 0xD83D});

int[] values = malformed.codePoints().toArray();
System.out.println(java.util.Arrays.toString(values)); // [55357]

boolean hasUnpairedSurrogate = malformed.codePoints()
    .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);

System.out.println(hasUnpairedSurrogate); // true
```

Dải `U+D800` đến `U+DFFF` được dành cho surrogate, **không phải giá trị Unicode scalar hợp lệ** khi đứng riêng. `Character.isValidCodePoint(int)` chỉ kiểm tra giá trị trong phạm vi Unicode code point, vì vậy **không đủ** để khẳng định đây là scalar value hợp lệ: các giá trị surrogate vẫn nằm trong phạm vi số đó. Nếu dữ liệu đầu vào có thể hỏng, cần xác định chính sách từ chối, thay thế hoặc xử lý riêng trước khi diễn giải và xuất Unicode ra định dạng khác.

## 8. Lazy pipeline, short-circuit và tài nguyên

`chars()` và `codePoints()` tạo nguồn `IntStream`. Các thao tác trung gian `filter`, `map` và `peek` diễn đạt các bước xử lý nhưng pipeline chỉ được tiêu thụ khi gọi **terminal operation** như `count`, `toArray`, `anyMatch` hoặc `collect`.

```java
String text = "A😀B";

var selected = text.codePoints()
    .filter(Character::isLetter); // Chưa tiêu thụ nguồn.

long numberOfLetters = selected.count(); // 2

// Không gọi selected.toArray() thêm lần nữa:
// Stream đã được tiêu thụ. Muốn đọc lại thì tạo text.codePoints() mới.
```

Một số terminal operation có thể **dừng sớm**. Ví dụ:

```java
String text = "A😀B";

boolean hasEmojiGrinningFace = text.codePoints()
    .anyMatch(cp -> cp == 0x1F600);
```

`anyMatch` có thể dừng khi đã tìm thấy code point phù hợp, không cần đi hết chuỗi. Vì vậy không gắn tác dụng phụ bắt buộc vào `filter`/`map` rồi giả định chúng luôn chạy với mọi phần tử.

Nguồn `String` thông thường không gắn với tài nguyên bên ngoài cần đóng, nên không cần `try-with-resources` chỉ để gọi `text.chars()` hoặc `text.codePoints()`. Điều này khác với các Stream mở từ tệp, ví dụ `Files.lines(...)`, vốn cần được đóng đúng cách. Các đoạn mã trong mục 2 dùng `try-with-resources` vẫn hợp lệ nhưng **không bắt buộc** với nguồn `String`.

## 9. Hiệu năng và các lựa chọn thay thế

`IntStream` là Stream cho kiểu nguyên thủy `int`, nhờ đó tránh boxing từng phần tử như `Stream<Integer>`. Dẫu vậy, pipeline vẫn có chi phí thiết lập và xử lý; không thể mặc định Stream nhanh hơn một vòng lặp.

| Bài toán | Lựa chọn đáng cân nhắc | Lưu ý |
| --- | --- | --- |
| Đếm code point Unicode | `text.codePoints().count()` hoặc `text.codePointCount(0, text.length())` | Gọi đúng tên đại lượng; không phải số grapheme cluster. |
| Xử lý mã ASCII theo từng đơn vị | `text.chars()` | Chỉ hợp lý khi yêu cầu thực sự giới hạn đầu vào. |
| Lọc code point theo thuộc tính Unicode | `text.codePoints().filter(Character::isLetter)` | Chú ý dấu kết hợp và các loại Unicode khác. |
| Sửa/đọc một số vị trí xác định | `charAt`, `codePointAt`, `offsetByCodePoints` hoặc vòng lặp | Xác định rõ chỉ số là UTF-16 hay code point. |
| Lấy danh sách từng code point | `codePoints().toArray()` | `int[]` tránh boxing; nếu cần đối tượng thì chuyển đổi có chủ đích. |
| Xây lại chuỗi | `StringBuilder.appendCodePoint` trong phép `collect` | Tránh ép kiểu `int` xuống `char` khi giá trị bổ sung. |
| Văn bản có cấu trúc thị giác/ngôn ngữ phức tạp | API phân đoạn/chuẩn hóa Unicode chuyên dụng | Code point không tương đương grapheme cluster. |

Với chuỗi ngắn và logic đơn giản, vòng lặp qua `char` có thể rõ ràng và nhẹ hơn. Với chuỗi chứa ký tự bổ sung mà cần xử lý code point, vòng lặp cũng có thể dùng `codePointAt` kết hợp `Character.charCount`; nó chỉ dài hơn một chút so với pipeline:

```java
String text = "A😀B";

for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    System.out.printf("U+%04X%n", cp);
    offset += Character.charCount(cp);
}
```

Vòng lặp trên duyệt từng code point theo đúng quy ước của `String.codePointAt`, kể cả cách xử lý các surrogate đơn lẻ. Nếu cần xử lý rất nhiều chuỗi trong đoạn mã nhạy hiệu năng, hãy so sánh bằng dữ liệu đại diện và benchmark đúng phương pháp, chẳng hạn **JMH**, sau khi JVM warm-up.

Không bật `parallel()` chỉ để xử lý một chuỗi ngắn. Chia dữ liệu, gom kết quả và duy trì thứ tự có thể đắt hơn thao tác trên từng code point. Các kỹ thuật như `Spliterator`, collector tùy chỉnh hoặc Stream Gatherers có giá trị ở bài toán phức tạp hơn, nhưng không cần thiết cho phần lớn ví dụ lọc ký tự trong bài này.

## 10. Lỗi phổ biến và cách khắc phục

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `chars().count()` rồi gọi đó là số ký tự Unicode | Đếm emoji bổ sung thành hai đơn vị | Dùng `codePoints().count()` nếu cần số code point; phân đoạn grapheme nếu cần ký tự hiển thị. |
| Dùng `(char) cp` cho mọi code point | Cắt mất bit cao của ký hiệu bổ sung | Dùng `Character.toChars` hoặc `appendCodePoint`. |
| Dùng `String.length()` làm chỉ số code point | Sai vị trí sau cặp surrogate | Dùng `offsetByCodePoints` hoặc duyệt code point đúng cách. |
| Dùng `Character.isLetter` rồi nghĩ đã giữ nguyên mọi từ có dấu | Mất dấu kết hợp trong một số chuỗi | Xét Unicode normalization và các nhóm mark theo yêu cầu. |
| Coi mọi giá trị `codePoints()` là Unicode scalar hợp lệ | Bỏ sót surrogate đơn lẻ từ chuỗi hỏng | Kiểm tra chính sách xử lý surrogate không ghép cặp. |
| Coi `Character.toUpperCase(int)` là chuyển chữ hoa hoàn chỉnh | Thiếu ánh xạ nhiều ký tự hoặc phụ thuộc ngôn ngữ | Dùng `String.toUpperCase(Locale)` cho văn bản thực. |
| Dùng lại cùng một `IntStream` cho nhiều terminal operation | `IllegalStateException` | Gọi lại `text.codePoints()` để tạo pipeline mới. |
| Chuyển `int` sang `Integer` hàng loạt dù chỉ cần đếm/lọc | Tăng boxing và có thể tốn bộ nhớ | Dùng các phép của `IntStream` trực tiếp. |

## 11. Bài tập thực hành

### Bài 1: So sánh đếm theo hai đơn vị

Với chuỗi `"A😀B🚀"`, dự đoán kết quả của `length()`, `chars().count()` và `codePoints().count()`. In các mảng `int[]` từ hai Stream và giải thích sự khác biệt. Kiểm chứng với `codePointCount(0, text.length())`.

### Bài 2: Quy tắc mã định danh

Thiết kế hàm nhận chuỗi mã, trả về `true` nếu mã **không rỗng** và chỉ có chữ viết hoa ASCII `A-Z` cùng chữ số `0-9`. Dùng `chars().allMatch(...)` và thử các giá trị `"AB12"`, `"A-B"`, `"É9"`, `""` và `"A😀"`. Giải thích vì sao đây là yêu cầu ASCII, khác với yêu cầu cho phép mọi chữ cái Unicode.

### Bài 3: Lọc theo code point

Cho chuỗi `"Lập trình Java 17 😀"`, dùng `codePoints()` để đếm chữ cái, chữ số và khoảng trắng. Viết một pipeline `filter` + `collect` để giữ lại chữ cái và chữ số, rồi quan sát cách xử lý dấu tiếng Việt trong dạng dựng sẵn và dạng kết hợp.

### Bài 4: Giữ nguyên các ký hiệu bổ sung

Cho chuỗi `"A🚀B😀C"`, chuyển từng code point thành một chuỗi nhỏ bằng `mapToObj` và kiểm tra danh sách kết quả. Thử làm cùng việc bằng `chars()` để chỉ ra tại sao emoji bị tách đôi.

### Bài 5: Văn bản không chuẩn hóa

So sánh `"\u00E9"` và `"e\u0301"` bằng `equals`, `codePoints().count()` và `Character.isLetter`. Giải thích khi nào cần Unicode normalization và vì sao một code point không nhất thiết tương ứng một ký tự trên màn hình.

### Bài 6: Dữ liệu đầu vào bất thường

Tạo một `String` chứa một high surrogate không đi cùng low surrogate. Quan sát `chars().toArray()` và `codePoints().toArray()`. Đề xuất cách phát hiện dữ liệu không có Unicode scalar hợp lệ trước khi xuất ra một hệ thống bên ngoài.

## 12. Tự kiểm tra kiến thức

- Vì sao `String.chars()` trả về `IntStream`, và các phần tử của nó đại diện cho cái gì?
- Với chuỗi chứa `😀`, `chars()` và `codePoints()` phát ra số lượng phần tử khác nhau thế nào?
- Tại sao không nên ép `int` của `codePoints()` về `char` để ghép lại chuỗi?
- Vì sao `codePoints().count()` không luôn bằng số ký tự người dùng nhìn thấy?
- Khi nào `chars()` là lựa chọn đơn giản, đúng đắn cho một quy tắc xử lý?
- Vì sao một pipeline lọc ký tự thường không cần `parallel()`?

**Ghi nhớ:** `String.chars()` duyệt **UTF-16 code units**, còn `String.codePoints()` duyệt **code points Unicode** bằng cách ghép những cặp surrogate hợp lệ. Chọn đơn vị xử lý theo yêu cầu; dùng `IntStream` để lọc và tổng hợp, nhưng nhớ rằng văn bản người dùng nhìn thấy có thể phức tạp hơn từng code point riêng lẻ.
