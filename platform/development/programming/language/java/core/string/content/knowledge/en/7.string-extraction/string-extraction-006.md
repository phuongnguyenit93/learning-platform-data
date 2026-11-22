# Cắt chuỗi theo code point thay vì chia đôi surrogate pair trong Java

Khi trích xuất một phần chuỗi `String` chứa emoji, chữ viết hiếm hoặc ký tự Unicode ngoài Basic Multilingual Plane (BMP), cắt theo chỉ số `char` một cách tùy ý có thể tách đôi một **surrogate pair**. Kết quả vẫn là một đối tượng `String` hợp lệ ở cấp API Java nhưng chứa dãy UTF-16 không hoàn chỉnh, dễ bị hiển thị thành ký tự thay thế hoặc xử lý sai khi mã hóa.

Giải pháp là xác định ranh giới bằng **Unicode code point**, sau đó chuyển các vị trí code point thành **chỉ số UTF-16** phù hợp trước khi gọi `substring()`. Bài này tập trung vào cơ chế, cách cắt an toàn và giới hạn của cách tiếp cận đó.

## 1. Phân biệt `char`, UTF-16 code unit và Unicode code point

Java `String` cung cấp nhiều API đánh chỉ số bằng **UTF-16 code unit**, không phải bằng số ký tự mà người dùng nhìn thấy.

- **Unicode code point** là một giá trị từ `U+0000` đến `U+10FFFF`; các giá trị dành riêng cho surrogate (`U+D800`–`U+DFFF`) không phải *Unicode scalar value* hợp lệ để đại diện cho một ký tự độc lập.
- **UTF-16 code unit** là một đơn vị 16 bit. Giá trị Unicode thuộc BMP và không phải surrogate được mã hóa bằng một code unit. Giá trị nằm ngoài BMP được mã hóa bằng hai code unit, tạo thành một **surrogate pair**.
- **`char` trong Java** là kiểu giá trị 16 bit, biểu diễn **một code unit UTF-16**. Một `char` không đủ để giữ riêng một code point ngoài BMP.
- **`int`** thường được dùng khi làm việc với giá trị Unicode code point, ví dụ qua `String.codePointAt()`, `String.codePoints()` hoặc `Character.toChars()`.

Hai nửa của một surrogate pair thuộc các dải:

| Thành phần | Phạm vi |
| --- | --- |
| High surrogate (nửa đầu) | `U+D800`–`U+DBFF` |
| Low surrogate (nửa sau) | `U+DC00`–`U+DFFF` |
| Code point cần một cặp surrogate trong UTF-16 | `U+10000`–`U+10FFFF` |

Ví dụ emoji 😀 là code point `U+1F600`, được mã hóa UTF-16 bằng hai code unit `D83D DE00`. Vì vậy chuỗi `"A😀B"` có **4 code unit UTF-16** nhưng chỉ có **3 code point**: `A`, `😀`, `B`.

```text
Nội dung:          A         😀                B
Code point:      U+0041   U+1F600           U+0042
UTF-16 unit:     0041     D83D    DE00       0042
UTF-16 index:      0        1       2          3       (end = 4)
Code-point index:  0        1                  2       (end = 3)
```

Các vị trí của code point là **chỉ số logic theo code point**; `String.substring()` **không nhận trực tiếp** kiểu chỉ số đó.

## 2. Vì sao `length()`, `charAt()` và `substring()` có thể gây nhầm?

`String.length()` trả về số **code unit UTF-16**, còn `charAt(index)` trả về một `char` tại vị trí code unit tương ứng. `substring(beginIndex, endIndex)` cũng dùng hai chỉ số UTF-16, với `beginIndex` bao gồm và `endIndex` không bao gồm.

Với `"A😀B"`:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

System.out.println(text.length());                           // 4
System.out.println(text.codePointCount(0, text.length()));    // 3
System.out.println(Character.isHighSurrogate(text.charAt(1))); // true
System.out.println(Character.isLowSurrogate(text.charAt(2)));  // true
```

Đây là **đoạn minh họa trong thân một phương thức**. `Character.toChars(0x1F600)` tạo đúng hai `char` cho emoji; không cần phụ thuộc vào khả năng nhập emoji trực tiếp trong tệp mã nguồn.

### Lỗi: coi chỉ số code point là chỉ số UTF-16

Giả sử muốn lấy **hai code point đầu** (`A` và `😀`), rồi viết:

```java
String unsafe = text.substring(0, 2); // SAI nếu mục tiêu là hai code point
```

`substring(0, 2)` chỉ lấy code unit ở index 0 và 1: ký tự `A` cộng **high surrogate** `D83D`. Nó loại bỏ low surrogate `DE00`, làm chuỗi kết quả chứa một surrogate đơn lẻ. Java không tự sửa lỗi này khi `substring()`.

Tương tự, muốn lấy chỉ emoji mà dùng `text.substring(1, 2)` thì chỉ thu được high surrogate; khoảng đúng theo UTF-16 phải là `[1, 3)`.

Không nên chứng minh lỗi bằng cách in trực tiếp surrogate đơn lẻ ra console: cách nó hiển thị còn tùy encoding và terminal. Thay vào đó, có thể kiểm tra:

```java
String unsafe = text.substring(0, 2);

System.out.println(unsafe.length()); // 2
System.out.println(Character.isHighSurrogate(
        unsafe.charAt(unsafe.length() - 1))); // true
```

## 3. API Java phục vụ việc cắt theo code point

| API | Vai trò | Hệ chỉ số |
| --- | --- | --- |
| `s.length()` | Đếm code unit UTF-16 | Số lượng code unit |
| `s.charAt(i)` | Lấy một code unit | `i` là UTF-16 index |
| `s.substring(start, end)` | Trích xuất khoảng ký tự | `start`, `end` là UTF-16 index |
| `s.codePointCount(start, end)` | Đếm code point trong một khoảng UTF-16 | Tham số là UTF-16 index |
| `s.offsetByCodePoints(index, offset)` | Di chuyển `offset` code point từ một UTF-16 index | Trả về UTF-16 index |
| `s.codePointAt(index)` | Đọc code point bắt đầu ở vị trí UTF-16 `index` | Tham số là UTF-16 index; trả về `int` |
| `Character.charCount(cp)` | Số UTF-16 code unit để biểu diễn một code point | Thường 1 hoặc 2 |
| `s.codePoints()` | Duyệt các giá trị code point của chuỗi qua `IntStream` | Không cung cấp trực tiếp UTF-16 index |
| `StringBuilder.appendCodePoint(cp)` | Thêm giá trị code point vào builder | Không cần tự ghép nửa surrogate |

Điểm đặc biệt hữu ích là `offsetByCodePoints`. Ví dụ:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
int startUtf16 = text.offsetByCodePoints(0, 1);
int endUtf16 = text.offsetByCodePoints(0, 2);

System.out.println(startUtf16); // 1
System.out.println(endUtf16);   // 3
```

`startUtf16 = 1` đứng trước high surrogate, `endUtf16 = 3` đứng **sau** low surrogate. Do vậy `text.substring(1, 3)` trích xuất nguyên emoji và không phá cặp surrogate.

`offsetByCodePoints` có thể nhận `offset` âm để di chuyển lùi, nhưng vị trí và khoảng dịch chuyển phải hợp lệ; Java ném `IndexOutOfBoundsException` khi phạm vi vượt giới hạn.

## 4. Hàm cắt theo khoảng code point an toàn

Ta định nghĩa API rõ ràng: nhận `fromInclusive`, `toExclusive` theo **chỉ số code point tính từ đầu chuỗi**, cả hai theo quy tắc đầu bao gồm/cuối không bao gồm. Đây là lựa chọn phù hợp khi bên gọi cần trích xuất đoạn chuỗi theo số code point.

```java
import java.util.Objects;

public final class CodePointSlices {
    private CodePointSlices() {
    }

    public static String sliceByCodePoints(
            String source, int fromInclusive, int toExclusive) {

        Objects.requireNonNull(source, "source");

        int total = source.codePointCount(0, source.length());
        if (fromInclusive < 0
                || toExclusive < fromInclusive
                || toExclusive > total) {
            throw new IndexOutOfBoundsException(
                    "Invalid code-point range [" + fromInclusive
                    + ", " + toExclusive + "), total=" + total);
        }

        int startUtf16 = source.offsetByCodePoints(0, fromInclusive);
        int endUtf16 = source.offsetByCodePoints(
                startUtf16, toExclusive - fromInclusive);

        return source.substring(startUtf16, endUtf16);
    }
}
```

Đây là **một lớp tiện ích độc lập** có thể lưu trong tệp `CodePointSlices.java`. Cách hoạt động:

1. `codePointCount(0, source.length())` lấy tổng số code point trong toàn chuỗi.
2. Kiểm tra `0 <= fromInclusive <= toExclusive <= total` để tránh cắt vượt giới hạn và xác định rõ hành vi khi chỉ số không hợp lệ.
3. `offsetByCodePoints(0, fromInclusive)` chuyển vị trí code point đầu thành UTF-16 index.
4. Dịch thêm `toExclusive - fromInclusive` code point từ vị trí bắt đầu để có UTF-16 index cuối.
5. Dùng `substring(startUtf16, endUtf16)` trên các **ranh giới UTF-16 đúng**.

Điều kiện cho phép `fromInclusive == toExclusive`; khi đó trả về chuỗi rỗng. `source == null` được xử lý rõ bằng `NullPointerException` từ `Objects.requireNonNull`. Hàm không âm thầm sửa hay cắt bớt chỉ số không hợp lệ.

**Lưu ý về phạm vi bảo đảm:** Với chuỗi đầu vào có các surrogate pair hợp lệ, hàm sẽ không cắt **giữa hai code unit của một pair**. Nó không xác nhận hay sửa một chuỗi UTF-16 đã bị lỗi sẵn (có surrogate đơn lẻ). Phần 8 giải thích thêm.

## 5. Chương trình Java 17 đầy đủ và kết quả chính xác

Để có thể biên dịch và chạy trực tiếp một tệp, sử dụng phiên bản sau trong tệp `SafeCodePointSliceDemo.java`. Phần kết quả cố ý in code point dạng hexadecimal để không phụ thuộc cách terminal hiển thị emoji.

```java
import java.util.Objects;

public class SafeCodePointSliceDemo {
    static String sliceByCodePoints(
            String source, int fromInclusive, int toExclusive) {

        Objects.requireNonNull(source, "source");

        int total = source.codePointCount(0, source.length());
        if (fromInclusive < 0
                || toExclusive < fromInclusive
                || toExclusive > total) {
            throw new IndexOutOfBoundsException("Invalid code-point range");
        }

        int start = source.offsetByCodePoints(0, fromInclusive);
        int end = source.offsetByCodePoints(
                start, toExclusive - fromInclusive);
        return source.substring(start, end);
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";

        System.out.println("UTF-16 length = " + text.length());
        System.out.println("code points = "
                + text.codePointCount(0, text.length()));

        String broken = text.substring(0, 2);
        System.out.println("broken length = " + broken.length());
        System.out.println("broken ends high surrogate = "
                + Character.isHighSurrogate(
                        broken.charAt(broken.length() - 1)));

        int emojiStart = text.offsetByCodePoints(0, 1);
        int emojiEnd = text.offsetByCodePoints(0, 2);
        System.out.println("emoji UTF-16 range = ["
                + emojiStart + ", " + emojiEnd + ")");

        String emoji = sliceByCodePoints(text, 1, 2);
        System.out.printf("emoji code point = U+%X%n", emoji.codePointAt(0));

        String firstTwo = sliceByCodePoints(text, 0, 2);
        System.out.println("first two code points = "
                + firstTwo.codePointCount(0, firstTwo.length()));
        System.out.println("last code point = "
                + sliceByCodePoints(text, 2, 3));
        System.out.println("whole string unchanged = "
                + sliceByCodePoints(text, 0, 3).equals(text));
        System.out.println("empty slice length = "
                + sliceByCodePoints(text, 1, 1).length());
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac SafeCodePointSliceDemo.java
java SafeCodePointSliceDemo
```

Kết quả chuẩn:

```text
UTF-16 length = 4
code points = 3
broken length = 2
broken ends high surrogate = true
emoji UTF-16 range = [1, 3)
emoji code point = U+1F600
first two code points = 2
last code point = B
whole string unchanged = true
empty slice length = 0
```

Giải thích: Chuỗi gốc có 4 code unit nhưng 3 code point. Cắt `substring(0, 2)` để lại high surrogate đơn. Chuyển hai mốc code point `1` và `2` thành UTF-16 index `1` và `3` giúp lấy trọn emoji; các đoạn hợp lệ không phá cặp surrogate.

## 6. Các cách duyệt theo code point

Nếu không cần `substring` theo một khoảng xác định, có thể duyệt tuần tự bằng `codePointAt` và `Character.charCount`.

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

for (int utf16Index = 0; utf16Index < text.length();) {
    int cp = text.codePointAt(utf16Index);
    System.out.printf("U+%X%n", cp);
    utf16Index += Character.charCount(cp);
}
```

Kết quả:

```text
U+41
U+1F600
U+42
```

Lý do phải tăng `utf16Index` bằng `Character.charCount(cp)`: giá trị ngoài BMP chiếm hai code unit. Nếu dùng `utf16Index++` như vòng lặp `char`, bạn sẽ đi vào low surrogate và xử lý sai ranh giới.

Một cách khác ngắn gọn hơn là `String.codePoints()` (có từ Java 9):

```java
text.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
```

Kết quả ba dòng giống ví dụ trên. `codePoints()` cho các giá trị kiểu `int` nên thuận tiện để kiểm tra, lọc hoặc xây dựng đầu ra. Tuy nhiên, nếu muốn biết UTF-16 index của từng code point, bạn vẫn cần theo dõi độ dài code unit hoặc dùng `offsetByCodePoints`.

### Tạo chuỗi từ các code point mà không ghép surrogate bằng tay

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
StringBuilder result = new StringBuilder();

text.codePoints()
        .limit(2)
        .forEach(cp -> result.appendCodePoint(cp));

String prefix = result.toString(); // "A" + emoji U+1F600
System.out.println(prefix.codePointCount(0, prefix.length())); // 2
```

`appendCodePoint` làm phần mã hóa UTF-16 cho giá trị code point, tránh tự tạo hai nửa surrogate. Trong trường hợp chỉ cần cắt một khoảng, `offsetByCodePoints + substring` vẫn thường rõ ý định hơn; ví dụ với stream minh họa phương án *xây dựng* chuỗi theo code point.

## 7. Những trường hợp biên cần kiểm tra

| Đầu vào / yêu cầu | Kết quả nên hiểu |
| --- | --- |
| `source = ""`, cắt `[0, 0)` | Trả về `""` |
| `source = "ABC"`, cắt `[1, 3)` | Trả về `"BC"` |
| `source = "A😀B"`, cắt `[1, 2)` | Trả về trọn emoji 😀 |
| `source = "A😀B"`, cắt `[0, 2)` | Trả về `A` và trọn emoji 😀 |
| `source = "A😀B"`, cắt `[2, 3)` | Trả về `B` |
| `source = "A😀B"`, cắt `[2, 2)` | Trả về `""` |
| Chỉ số âm, đầu lớn hơn cuối, hoặc vượt tổng code point | Ném `IndexOutOfBoundsException` trong hàm ví dụ |
| `source = null` | Ném `NullPointerException` với thông báo liên quan `source` |

**Không trộn lẫn hai hệ chỉ số.** Nếu hệ thống lưu offset do `String.indexOf(...)` hoặc `Matcher.start()` trả về, đó thường là **UTF-16 index**; không đem giá trị này truyền như thể là thứ tự code point vào `sliceByCodePoints`. Ngược lại, `offsetByCodePoints` nhận **vị trí khởi đầu UTF-16** và **số code point muốn di chuyển**, không nhận hai code-point index thuần túy.

Nếu API bên ngoài dùng số “ký tự” thì trước hết phải làm rõ họ định nghĩa “ký tự” là UTF-16 code unit, Unicode code point hay **grapheme cluster** (ký tự được người dùng cảm nhận).

## 8. Hai giới hạn quan trọng: UTF-16 hỏng và grapheme cluster

### 8.1. Cắt theo code point không sửa chuỗi đã có surrogate lẻ

Java `String` có thể chứa code unit high surrogate hoặc low surrogate không ghép thành pair hợp lệ, ví dụ tạo một chuỗi chứa một `char` đơn:

```java
String malformed = new String(new char[] {'A', '\uD83D'});
System.out.println(malformed.length()); // 2
System.out.println(malformed.codePointCount(0, malformed.length())); // 2
```

API `codePointCount` tính surrogate chưa ghép thành một đơn vị khi đếm; `codePoints()` cũng sẽ trả về giá trị surrogate đơn đó dưới dạng `int` thay vì tự tạo code point emoji hợp lệ. Do đó, chọn ranh giới theo code point chỉ tránh **tự tạo thêm** pair bị chia đôi từ một pair hợp lệ. Nếu dữ liệu gốc đã lỗi, cần chính sách **kiểm tra, từ chối hoặc thay thế** dữ liệu không hợp lệ trước khi xử lý, tùy hợp đồng đầu vào.

Không nên dùng `new String(Character.toChars(...))` với một code point ngoài phạm vi Unicode. `Character.toChars(int)` sẽ ném `IllegalArgumentException` cho giá trị không phải code point hợp lệ; còn việc coi surrogate code point là ký tự độc lập cũng không tạo Unicode scalar value hợp lệ. Hãy xác định tiêu chuẩn hợp lệ của dữ liệu đầu vào.

### 8.2. Một code point chưa chắc là một “ký tự nhìn thấy”

Một số ký tự hiển thị được hình thành từ **nhiều code point**. Ví dụ chữ `e` cộng dấu sắc kết hợp:

```java
String combined = "e\u0301";
System.out.println(combined.length()); // 2
System.out.println(combined.codePointCount(0, combined.length())); // 2
```

Nội dung này thường hiển thị gần giống chữ “é”, nhưng là hai code point `U+0065` và `U+0301`. Cắt theo code point `[0, 1)` chỉ lấy `e` và tách dấu sắc kết hợp ra ngoài. Tương tự, nhiều emoji có skin-tone modifier, variation selector, hoặc chuỗi nối bằng zero-width joiner chứa nhiều code point dù được người dùng xem là **một cụm hiển thị**.

Vì vậy cần phân biệt hai mục tiêu:

- **Không chia đôi surrogate pair**: dùng các API code point như `offsetByCodePoints` để lấy ranh giới UTF-16 đúng.
- **Không chia cụm ký tự mà người dùng nhìn thấy**: cần một thuật toán phân đoạn **grapheme cluster** phù hợp với quy tắc Unicode và phiên bản Unicode của môi trường chạy. Đừng giả định cắt theo code point đủ cho thao tác chọn/xóa ký tự trong editor hoặc giới hạn số ký tự hiển thị.

`java.text.BreakIterator.getCharacterInstance(...)` có thể phục vụ việc xác định ranh giới văn bản theo API JDK, nhưng đặc điểm hỗ trợ grapheme phức tạp và emoji có thể phụ thuộc phiên bản JDK/dữ liệu Unicode. Nếu cần tuân thủ đầy đủ **extended grapheme cluster** và các chuỗi emoji hiện đại, hãy xác minh kết quả trên bộ dữ liệu thực tế hoặc dùng thư viện phân đoạn Unicode thích hợp.

## 9. Lưu ý về hiệu năng và thiết kế API

`offsetByCodePoints` có thể phải duyệt qua những code unit kể từ điểm bắt đầu để tìm vị trí tiếp theo; `codePointCount` cũng phải duyệt khoảng được đếm. Với vài phép cắt hoặc chuỗi thông thường, sự rõ ràng của hàm `sliceByCodePoints` là ưu tiên tốt. Nếu thực hiện rất nhiều truy vấn ngẫu nhiên trên cùng chuỗi rất dài, hãy đo hiệu năng và cân nhắc xây dựng trước bảng ánh xạ **code-point index → UTF-16 index** để tránh duyệt lại nhiều lần.

Khi công bố API, đặt tên tham số rõ ràng, ví dụ `fromCodePointIndex` và `toCodePointIndexExclusive`. Nếu lấy chỉ số UTF-16, đặt tên `beginUtf16Index`/`endUtf16Index`. Việc đặt tên rõ giúp tránh lỗi trộn chỉ số từ những API khác nhau.

Với các thao tác chỉ chọn **đầu/cuối theo code point**, có thể tối ưu lời gọi bằng `offsetByCodePoints` từ vị trí bắt đầu thích hợp. Không dùng phép toán `utf16Index + numberOfCodePoints` nếu đoạn đi qua emoji hoặc ký tự ngoài BMP, vì số code point không bằng số UTF-16 code unit.

## 10. Lỗi phổ biến và cách sửa

1. **Dùng `substring(0, n)` để lấy `n` code point.** `n` đang bị diễn giải thành số code unit. Sửa bằng `substring(0, s.offsetByCodePoints(0, n))` sau khi kiểm tra phạm vi hợp lệ.
2. **Dùng `s.length()` làm số lượng code point.** `length()` đếm UTF-16 code unit. Muốn đếm code point, dùng `s.codePointCount(0, s.length())`.
3. **Tăng chỉ số vòng lặp `i++` sau `codePointAt(i)`.** Với code point ngoài BMP, phải tăng theo `Character.charCount(cp)` để bỏ qua cả pair.
4. **Gọi `charAt(i)` rồi coi kết quả luôn là một ký tự Unicode đầy đủ.** Một `char` có thể chỉ là một nửa surrogate pair; dùng `codePointAt(i)` tại ranh giới code point.
5. **Đếm code point rồi truyền index vào `substring`.** Đây là hai hệ tọa độ khác nhau; chuyển bằng `offsetByCodePoints`.
6. **Cho rằng xử lý theo code point luôn giữ nguyên ký tự hiển thị.** Combining mark và emoji nhiều code point yêu cầu phân đoạn grapheme cluster nếu đó là mục tiêu.
7. **Cho rằng cắt theo code point khắc phục mọi UTF-16 không hợp lệ.** Nó không chữa surrogate đơn đã có trong đầu vào; cần kiểm tra riêng khi dữ liệu phải là Unicode scalar values hợp lệ.
8. **Không xác nhận biên và giá trị `null`.** Thông báo lỗi rõ và quy tắc khoảng nửa mở giúp các bên gọi API tránh lỗi off-by-one.

## 11. Tự kiểm tra

Với chuỗi `"X😀YZ"` gồm code point `X`, `😀`, `Y`, `Z`:

- `length()` bằng **5** (1 + 2 + 1 + 1 code unit).
- `codePointCount(0, length())` bằng **4**.
- Khoảng code point `[1, 3)` phải trả về **emoji 😀 rồi `Y`**.
- Tương ứng, hai chỉ số UTF-16 truyền cho `substring` là **1** và **4**.
- `substring(1, 3)` chỉ lấy emoji 😀 vì khoảng UTF-16 `[1, 3)` gồm hai nửa surrogate.
- `substring(0, 2)` sẽ lấy `X` cùng high surrogate và bỏ low surrogate: đây là kết quả cần tránh.

**Ghi nhớ:** `String` được đánh chỉ số bằng **UTF-16 code unit**, trong khi bài toán có thể đòi hỏi **Unicode code point**. Muốn trích xuất theo code point, hãy **chuyển biên code point sang UTF-16 index bằng `offsetByCodePoints`, rồi mới gọi `substring`**. Nếu cần giữ trọn ký tự người dùng cảm nhận, phải xét thêm ranh giới **grapheme cluster**.
