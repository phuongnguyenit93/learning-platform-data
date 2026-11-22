# CharSequence.codePoints và ký tự ngoài BMP trong Java

## 1. Mục tiêu và tình huống thực tế

Trong Java, `String` và những lớp triển khai `CharSequence` biểu diễn văn bản dưới dạng **các đơn vị mã UTF-16** (`char` 16 bit). Đây không đồng nghĩa “mỗi ký tự Unicode chỉ chiếm một `char`”. Ví dụ emoji **😀** có code point **U+1F600**, nằm **ngoài Basic Multilingual Plane (BMP)** và cần hai đơn vị mã UTF-16, còn gọi là **surrogate pair**.

Nếu dùng `String.length()` để đếm số code point, dùng `substring` để cắt giữa cặp surrogate, hoặc chuyển `int` code point thành `char` bằng ép kiểu, ứng dụng có thể đếm sai, tạo dữ liệu Unicode lỗi, mất emoji hoặc làm hỏng text khi xuất sang UTF-8.

`CharSequence.codePoints()`, xuất hiện từ **Java 8** và vẫn có trong JDK hiện hành, là API tiện lợi để duyệt theo code point thay vì từng code unit:

```java
IntStream points = sequence.codePoints();
```

*Snippet giả định `sequence` là một `CharSequence` và đã import `java.util.stream.IntStream`.*

Bài học giúp bạn:

- Phân biệt **byte**, **UTF-16 code unit**, **Unicode code point**, **Unicode scalar value** và **grapheme cluster**.
- Biết chính xác `length`, `charAt`, `chars` và `codePoints` đo/trả gì.
- Duyệt, lọc, dựng chuỗi và cắt chuỗi đúng với supplementary characters.
- Hiểu vì sao **unpaired surrogate vẫn có thể xuất hiện trong kết quả `codePoints()`**.
- Chuyển từ UTF-16 index sang code-point ordinal và ngược lại.
- Phân biệt code point với chữ có dấu tổ hợp, emoji ZWJ, lá cờ (grapheme cluster).
- Phân biệt Unicode normalization với xử lý UTF-8 và Base64.
- Xử lý an toàn `StringBuilder`/`StringBuffer`/`CharBuffer` mutable, đặc biệt late-binding stream.
- Kiểm tra hiệu năng, tính đúng đắn và những trường hợp biên bằng Java 17+.

Các API cốt lõi vẫn được hỗ trợ. Ví dụ runnable sử dụng **Java 17+** (chẳng hạn `Stream.toList()` và `String.formatted()`), trong khi `CharSequence.codePoints()` đã có từ Java 8. Theo Special Note, nội dung không dùng API lỗi thời.

## 2. Bốn đơn vị dễ nhầm

| Đơn vị | Định nghĩa | Ví dụ `😀` |
| --- | --- | --- |
| Code point | Giá trị Unicode từ U+0000 đến U+10FFFF | U+1F600 |
| UTF-16 code unit | Một `char` 16 bit trong Java | **2 units:** U+D83D, U+DE00 |
| UTF-8 byte | Đơn vị byte khi mã hóa ra UTF-8 | **4 bytes:** F0 9F 98 80 |
| Grapheme cluster | Cụm người dùng thường coi như một ký tự hiển thị | Thường là 1 cụm |

Với `"A😀B"`: `length() = 4`, `codePoints().count() = 3`, kích cỡ UTF-8 là 6 bytes và trong trường hợp đơn giản có 3 grapheme clusters.

**BMP** là khoảng U+0000..U+FFFF. Ngoài BMP, từ U+10000 đến U+10FFFF, là **supplementary code points**. Không phải mọi ký tự ngoài BMP là emoji: còn có nốt nhạc, ký tự chữ viết lịch sử và ký hiệu toán học.

Trong BMP có hai vùng được dành riêng:

- **High surrogate:** U+D800..U+DBFF.
- **Low surrogate:** U+DC00..U+DFFF.

Khi high surrogate đứng ngay trước low surrogate hợp lệ, cặp đó mã hóa **một** supplementary code point. Nếu high/low xuất hiện riêng lẻ, đó là **unpaired surrogate**, không phải Unicode scalar value hợp lệ.

Khái niệm **Unicode scalar value** là một code point **không thuộc** vùng surrogate. Một số hàm `Character` chỉ kiểm tra dải giá trị code point, nên cần phân biệt scalar validation và kiểm tra giá trị số.

## 3. `chars()` và `codePoints()` khác nhau thế nào?

`CharSequence.chars()` trả `IntStream` các giá trị `char` được zero-extend thành int, **không ghép surrogate pair**.

`CharSequence.codePoints()` trả `IntStream` các code point, **ghép cặp high–low hợp lệ**, và trả các code unit khác (bao gồm unpaired surrogate) dưới dạng int.

Lưu `UnitsAndPointsDemo.java`:

```java
import java.util.List;

public class UnitsAndPointsDemo {
    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String music = new String(
                Character.toChars(0x1D11E));
        CharSequence text = "A" + emoji + music + "B";

        List<String> units = text.chars()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList();
        List<String> points = text.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList();

        System.out.println("utf16Length = " + text.length());
        System.out.println("charUnits = " + text.chars().count());
        System.out.println("codePoints = " +
                text.codePoints().count());
        System.out.println("units = " + units);
        System.out.println("points = " + points);
    }
}
```

```bash
javac UnitsAndPointsDemo.java
java UnitsAndPointsDemo
```

```text
utf16Length = 6
charUnits = 6
codePoints = 4
units = [U+0041, U+D83D, U+DE00, U+D834, U+DD1E, U+0042]
points = [U+0041, U+1F600, U+1D11E, U+0042]
```

Hai đơn vị U+D83D và U+DE00 đại diện cho một emoji; U+D834 và U+DD1E đại diện cho một ký hiệu âm nhạc. `char` không đủ rộng để lưu riêng những code point đó. **Giữ giá trị từ `codePoints()` trong `int`**, không ép xuống `char`.

### 3.1. Dùng API ở mức giao diện `CharSequence`

`String`, `StringBuilder`, `StringBuffer` và `CharBuffer` đều có thể dùng `codePoints()`. Các loại có thể trả cùng giá trị code point nhưng khác nhau về khả năng thay đổi nội dung.

Lưu `SequenceKindsDemo.java`:

```java
import java.nio.CharBuffer;

public class SequenceKindsDemo {
    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        String[] labels = {
                "String", "StringBuilder",
                "StringBuffer", "CharBuffer"
        };
        CharSequence[] sequences = {
                text,
                new StringBuilder(text),
                new StringBuffer(text),
                CharBuffer.wrap(text)
        };

        for (int i = 0; i < sequences.length; i++) {
            CharSequence cs = sequences[i];
            System.out.println(labels[i] + " = "
                    + cs.length() + "/"
                    + cs.codePoints().count());
        }
    }
}
```

```bash
javac SequenceKindsDemo.java
java SequenceKindsDemo
```

```text
String = 4/3
StringBuilder = 4/3
StringBuffer = 4/3
CharBuffer = 4/3
```

**Chú ý:** một `CharSequence` không nhất thiết immutable, cũng không có hợp đồng equality chung giữa các triển khai. Nếu cần lưu nội dung ổn định làm key, so sánh hoặc xử lý đồng thời, cân nhắc chuyển thành `String` dưới cơ chế đồng bộ/ownership phù hợp.

## 4. Chỉ số UTF-16 khác ordinal của code point

`String.charAt(index)`, `String.substring(begin,end)` và thậm chí `String.codePointAt(index)` đều nhận **index theo UTF-16 code unit**.

Ví dụ `"A😀B"`:

```text
UTF-16 index        0      1      2      3
UTF-16 unit         A    D83D   DE00     B
                         \     /
code point          A      😀            B
ordinal             0      1             2
```

`codePointAt(1)` trả **U+1F600**, nhưng `codePointAt(2)` (bắt đầu ở low surrogate) có thể trả **U+DE00**, **không** tự quay lại ghép high surrogate trước đó.

Để lấy vị trí sau n code point, dùng `String.offsetByCodePoints(startUtf16Index,n)`; muốn đếm trong một range dùng `String.codePointCount(beginUtf16,endUtf16)`.

Lưu `CodePointIndexDemo.java`:

```java
public class CodePointIndexDemo {
    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        System.out.println("utf16Length = " + text.length());
        System.out.println("pointCount = " +
                text.codePointCount(0, text.length()));
        System.out.println("at1 = U+%04X"
                .formatted(text.codePointAt(1)));
        System.out.println("at2 = U+%04X"
                .formatted(text.codePointAt(2)));
        System.out.println("before3 = U+%04X"
                .formatted(text.codePointBefore(3)));
        System.out.println("after2Points = " +
                text.offsetByCodePoints(0, 2));
        System.out.println("back2Points = " +
                text.offsetByCodePoints(text.length(), -2));
    }
}
```

```bash
javac CodePointIndexDemo.java
java CodePointIndexDemo
```

```text
utf16Length = 4
pointCount = 3
at1 = U+1F600
at2 = U+DE00
before3 = U+1F600
after2Points = 3
back2Points = 1
```

`offsetByCodePoints` có thể phải **duyệt** một phần chuỗi; không tự biến `String` thành cấu trúc random access theo code point có độ phức tạp O(1). Nếu truy cập ordinal nhiều lần, cân nhắc `int[] cps = s.codePoints().toArray()` hoặc bảng offset xây một lần.

## 5. Surrogate lẻ: `codePoints()` không phải validator

Nếu một high surrogate không được theo sau bởi low surrogate hoặc một low surrogate đứng lẻ, stream code point **vẫn trả các giá trị đó dưới dạng int**. Nó không mặc nhiên ném exception hay tự thay bằng U+FFFD.

`Character.isValidCodePoint` chỉ kiểm tra số nằm trong dải `0..0x10FFFF`. **U+D83D vẫn làm hàm này trả true**, dù đó không phải Unicode scalar value.

Lưu `UnpairedSurrogatesDemo.java`:

```java
import java.util.List;

public class UnpairedSurrogatesDemo {
    private static boolean isScalar(int cp) {
        return Character.isValidCodePoint(cp)
                && (cp < 0xD800 || cp > 0xDFFF);
    }

    public static void main(String[] args) {
        char high = Character.highSurrogate(0x1F600);
        char low = Character.lowSurrogate(0x1F600);
        String broken = "X" + high + "Y" + low;

        List<String> points = broken.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList();

        System.out.println("length = " + broken.length());
        System.out.println("points = " + points);
        System.out.println("numericValid = " +
                Character.isValidCodePoint(high));
        System.out.println("allScalars = " +
                broken.codePoints()
                        .allMatch(UnpairedSurrogatesDemo::isScalar));
    }
}
```

```bash
javac UnpairedSurrogatesDemo.java
java UnpairedSurrogatesDemo
```

```text
length = 4
points = [U+0058, U+D83D, U+0059, U+DE00]
numericValid = true
allScalars = false
```

**Phân biệt:** kiểm tra scalar value khác kiểm tra `Character.isDefined(cp)`. Một scalar chưa được gán ký tự trong phiên bản Unicode của JDK vẫn có thể là dữ liệu hợp lệ. Không tự từ chối toàn bộ code point chưa được `Character` biết nếu nghiệp vụ không có yêu cầu như vậy.

### 5.1. Quy tắc xử lý dữ liệu malformed

Định nghĩa rõ contract:

- **Reject**: không chấp nhận chuỗi có surrogate lẻ.
- **Replace**: chuyển surrogate lẻ thành U+FFFD.
- **Preserve**: giữ nguyên UTF-16 code units vì một mục đích tương thích đặc thù; không giả định truyền UTF-8 nguyên vẹn.

Ví dụ thay thế surrogate lẻ mà không động vào surrogate pair hợp lệ:

Lưu `ScalarSanitizerDemo.java`:

```java
public class ScalarSanitizerDemo {
    private static boolean isScalar(int cp) {
        return Character.isValidCodePoint(cp)
                && (cp < 0xD800 || cp > 0xDFFF);
    }

    static String sanitize(CharSequence cs) {
        StringBuilder result = new StringBuilder();
        cs.codePoints().forEach(cp -> {
            result.appendCodePoint(isScalar(cp) ? cp : 0xFFFD);
        });
        return result.toString();
    }

    public static void main(String[] args) {
        String bad = "A" +
                Character.highSurrogate(0x1F600) + "B";
        String clean = sanitize(bad);

        System.out.println("beforeValid = " +
                bad.codePoints().allMatch(
                        ScalarSanitizerDemo::isScalar));
        System.out.println("afterValid = " +
                clean.codePoints().allMatch(
                        ScalarSanitizerDemo::isScalar));
        System.out.println("replacementCount = " +
                clean.codePoints()
                        .filter(cp -> cp == 0xFFFD).count());
    }
}
```

```bash
javac ScalarSanitizerDemo.java
java ScalarSanitizerDemo
```

```text
beforeValid = false
afterValid = true
replacementCount = 1
```

**Không đồng nhất `Character.isValidCodePoint` với kiểm tra UTF-16 well-formed.** Khi input đến từ byte stream, còn cần chọn charset decoder và chính sách malformed input (ví dụ `CodingErrorAction.REPORT`).

## 6. Cắt chuỗi theo code point mà không bẻ đôi surrogate pair

`substring` lấy range UTF-16; nếu cắt `"A😀B"` sau hai code units thì mảnh đầu kết thúc bằng **high surrogate** và mảnh sau bắt đầu bằng **low surrogate**. Hai mảnh đứng riêng sẽ là dữ liệu malformed.

Cách cắt từ code point ordinal:

```java
int begin = s.offsetByCodePoints(0, startCp);
int end = s.offsetByCodePoints(begin, countCp);
String result = s.substring(begin, end);
```

*Snippet yêu cầu `s` là `String`, `startCp` và `countCp` không âm, nằm trong phạm vi.*

Lưu `SafeCodePointSliceDemo.java`:

```java
public class SafeCodePointSliceDemo {
    static String slice(String source,
                        int startCp, int countCp) {
        if (startCp < 0 || countCp < 0) {
            throw new IllegalArgumentException("negative range");
        }
        int begin = source.offsetByCodePoints(0, startCp);
        int end = source.offsetByCodePoints(begin, countCp);
        return source.substring(begin, end);
    }

    public static void main(String[] args) {
        String smile = new String(
                Character.toChars(0x1F600));
        String clef = new String(
                Character.toChars(0x1D11E));
        String text = "A" + smile + "B" + clef + "C";
        String middle = slice(text, 1, 3);

        System.out.println("sourceUnits = " + text.length());
        System.out.println("sourcePoints = " +
                text.codePoints().count());
        System.out.println("middleUnits = " + middle.length());
        System.out.println("middlePoints = " +
                middle.codePoints().count());
        System.out.println("sliceCorrect = " +
                middle.equals(smile + "B" + clef));
    }
}
```

```bash
javac SafeCodePointSliceDemo.java
java SafeCodePointSliceDemo
```

```text
sourceUnits = 7
sourcePoints = 5
middleUnits = 5
middlePoints = 3
sliceCorrect = true
```

`offsetByCodePoints` có thể ném `IndexOutOfBoundsException` nếu range nằm ngoài số code point. Nếu start/count đến từ API, cần validate dữ liệu hoặc chuyển exception thành lỗi domain rõ ràng. Cắt theo code point cũng **không** bảo đảm giữ nguyên các **grapheme cluster** có nhiều code point (dấu tổ hợp, emoji ZWJ).

### 6.1. Chia fragment theo giới hạn UTF-16

Nếu cần chia theo dung lượng code units (không phải ordinal code point), kiểm tra ranh giới giữa high và low:

```java
int cut = desiredEnd;
if (cut > 0 && cut < text.length()
        && Character.isHighSurrogate(text.charAt(cut - 1))
        && Character.isLowSurrogate(text.charAt(cut))) {
    cut--;
}
String left = text.substring(0, cut);
String right = text.substring(cut);
```

*Snippet yêu cầu `0 <= desiredEnd <= text.length()`; đây không phải chương trình độc lập.*

Lưu `SafeChunkBoundaryDemo.java`:

```java
public class SafeChunkBoundaryDemo {
    private static boolean wellFormed(String s) {
        return s.codePoints().noneMatch(
                cp -> cp >= 0xD800 && cp <= 0xDFFF);
    }

    public static void main(String[] args) {
        String smile = new String(
                Character.toChars(0x1F600));
        String text = "A" + smile + "B";

        String naiveLeft = text.substring(0, 2);
        String naiveRight = text.substring(2);

        int cut = text.offsetByCodePoints(0, 2);
        String safeLeft = text.substring(0, cut);
        String safeRight = text.substring(cut);

        System.out.println("naiveWellFormed = " +
                (wellFormed(naiveLeft) &&
                 wellFormed(naiveRight)));
        System.out.println("safeCut = " + cut);
        System.out.println("safeWellFormed = " +
                (wellFormed(safeLeft) &&
                 wellFormed(safeRight)));
        System.out.println("restored = " +
                (safeLeft + safeRight).equals(text));
    }
}
```

```bash
javac SafeChunkBoundaryDemo.java
java SafeChunkBoundaryDemo
```

```text
naiveWellFormed = false
safeCut = 3
safeWellFormed = true
restored = true
```

Nếu chuỗi đầu vào vốn có surrogate lẻ thì chọn điểm chia không thể tự sửa nội dung. Với một **stream dữ liệu** phân thành các buffer, high surrogate ở cuối buffer có thể phải chờ low surrogate ở buffer kế tiếp trước khi xử lý code point.

## 7. Duyệt vòng lặp thủ công khi cần vị trí UTF-16

`CharSequence.codePoints()` tiện cho stream pipeline. Nếu cần biết **UTF-16 offset** của từng code point để đánh dấu/tokenize text, dùng `Character.codePointAt` và `Character.charCount`:

```java
for (int index = 0; index < cs.length();) {
    int cp = Character.codePointAt(cs, index);
    // xử lý cp, index
    index += Character.charCount(cp);
}
```

*Snippet giả định `cs` không thay đổi trong lúc duyệt.*

Lưu `ManualCodePointIterationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ManualCodePointIterationDemo {
    public static void main(String[] args) {
        String smile = new String(
                Character.toChars(0x1F600));
        CharSequence text = "A" + smile + "B";

        List<Integer> positions = new ArrayList<>();
        List<Integer> values = new ArrayList<>();

        for (int i = 0; i < text.length();) {
            int cp = Character.codePointAt(text, i);
            positions.add(i);
            values.add(cp);
            i += Character.charCount(cp);
        }

        System.out.println("positions = " + positions);
        System.out.println("count = " + values.size());
        System.out.println("sameAsStream = " +
                values.equals(text.codePoints().boxed().toList()));
    }
}
```

```bash
javac ManualCodePointIterationDemo.java
java ManualCodePointIterationDemo
```

```text
positions = [0, 1, 3]
count = 3
sameAsStream = true
```

Đối với một surrogate lẻ, `Character.codePointAt` trả giá trị surrogate và `charCount` là 1. Muốn duyệt từ phải sang trái, `Character.codePointBefore(CharSequence,index)` kết hợp với `charCount` giúp tránh bắt đầu ở giữa cặp.

## 8. Tạo lại chuỗi từ code point

Một supplementary code point được chứa trong `int`. Các phương thức hiện hành:

- `Character.toChars(int cp)` tạo mảng một hoặc hai `char`.
- `StringBuilder.appendCodePoint(int cp)` thêm đúng UTF-16 units.
- `new String(int[] codePoints,int offset,int count)` dựng chuỗi từ mảng code point.

**Không** dùng `(char)0x1F600` vì ép kiểu làm mất bit cao.

Lưu `BuildFromCodePointsDemo.java`:

```java
public class BuildFromCodePointsDemo {
    public static void main(String[] args) {
        int emoji = 0x1F600;

        String byChars = "A" +
                new String(Character.toChars(emoji)) + "B";
        String byBuilder = new StringBuilder()
                .appendCodePoint('A')
                .appendCodePoint(emoji)
                .appendCodePoint('B')
                .toString();

        int[] points = {'A', emoji, 'B'};
        String byArray = new String(
                points, 0, points.length);

        boolean badRejected = false;
        try {
            Character.toChars(0x110000);
        } catch (IllegalArgumentException e) {
            badRejected = true;
        }

        System.out.println("utf16Units = " + byChars.length());
        System.out.println("pointCount = " +
                byChars.codePoints().count());
        System.out.println("sameStrings = " +
                (byChars.equals(byBuilder) &&
                 byBuilder.equals(byArray)));
        System.out.println("charCountEmoji = " +
                Character.charCount(emoji));
        System.out.println("invalidRejected = " + badRejected);
    }
}
```

```bash
javac BuildFromCodePointsDemo.java
java BuildFromCodePointsDemo
```

```text
utf16Units = 4
pointCount = 3
sameStrings = true
charCountEmoji = 2
invalidRejected = true
```

`Character.toChars` từ chối giá trị ngoài dải code point. Tuy nhiên, **code point trong vùng surrogate** vẫn cần được loại nếu ứng dụng yêu cầu Unicode scalar values; một constructor thành công không đồng nghĩa dữ liệu UTF-16 đã well-formed.

## 9. Dùng `IntStream` để lọc và thống kê

`codePoints()` là `IntStream` nên có thể kết hợp `filter`, `map`, `mapToObj`, `count`, `anyMatch`, `toArray` và `forEach`. Các hàm `Character.isLetterOrDigit(int cp)` hay `isSupplementaryCodePoint(int cp)` nhận trực tiếp `int`, không cần ép kiểu.

Lưu `CodePointFilteringDemo.java`:

```java
public class CodePointFilteringDemo {
    public static void main(String[] args) {
        String smile = new String(
                Character.toChars(0x1F600));
        String clef = new String(
                Character.toChars(0x1D11E));
        String text = "A" + smile + clef + "9";

        long supplementary = text.codePoints()
                .filter(Character::isSupplementaryCodePoint)
                .count();
        long alphanumeric = text.codePoints()
                .filter(Character::isLetterOrDigit)
                .count();

        StringBuilder filtered = new StringBuilder();
        text.codePoints()
                .filter(Character::isLetterOrDigit)
                .forEach(filtered::appendCodePoint);

        System.out.println("points = " +
                text.codePoints().count());
        System.out.println("supplementary = " +
                supplementary);
        System.out.println("alphanumeric = " + alphanumeric);
        System.out.println("filtered = " + filtered);
    }
}
```

```bash
javac CodePointFilteringDemo.java
java CodePointFilteringDemo
```

```text
points = 4
supplementary = 2
alphanumeric = 2
filtered = A9
```

**Không tự động loại combining marks, variation selectors, ZWJ** chỉ vì không được `isLetterOrDigit` nhận diện: làm vậy có thể thay đổi một chữ có dấu hoặc phá một emoji sequence. Chính sách xác thực tên người dùng, văn bản đa ngôn ngữ và tìm kiếm cần xét đúng Unicode category và ngữ cảnh nghiệp vụ.

Phân loại `Character` còn phụ thuộc phiên bản Unicode mà JDK đang hỗ trợ. Một ký tự mới có thể chưa được JDK cũ phân loại, dù vẫn là scalar hợp lệ.

## 10. Code point khác grapheme cluster

Ví dụ:

- `"e" + U+0301` = e và COMBINING ACUTE ACCENT, **2 code point** nhưng thường được hiển thị thành một chữ có dấu.
- WOMAN U+1F469 + ZWJ U+200D + LAPTOP U+1F4BB = **3 code point** nhưng thường hiển thị như một emoji nghề nghiệp.
- Cờ Việt Nam có thể được tạo từ **2 regional indicators**, thường hiển thị thành một lá cờ.

`codePoints().count()` **không thể đếm số ký tự hiển thị** trong mọi trường hợp. Java regex hiện hành hỗ trợ `\\X` cho một Unicode extended grapheme cluster. Cách phân đoạn chịu ảnh hưởng của Unicode version trong JDK; cách hiển thị cuối cùng còn phụ thuộc nền tảng và font.

Lưu `GraphemeCountDemo.java`:

```java
import java.util.regex.Pattern;

public class GraphemeCountDemo {
    static long graphemes(String text) {
        return Pattern.compile("\\X")
                .matcher(text).results().count();
    }

    public static void main(String[] args) {
        String accent = "e" + (char) 0x0301;
        String jobEmoji =
                new String(Character.toChars(0x1F469))
                + (char) 0x200D
                + new String(Character.toChars(0x1F4BB));
        String flag =
                new String(Character.toChars(0x1F1FB))
                + new String(Character.toChars(0x1F1F3));

        System.out.println("accent = " +
                accent.length() + "/" +
                accent.codePoints().count() + "/" +
                graphemes(accent));
        System.out.println("zwj = " +
                jobEmoji.length() + "/" +
                jobEmoji.codePoints().count() + "/" +
                graphemes(jobEmoji));
        System.out.println("flag = " +
                flag.length() + "/" +
                flag.codePoints().count() + "/" +
                graphemes(flag));
    }
}
```

```bash
javac GraphemeCountDemo.java
java GraphemeCountDemo
```

```text
accent = 2/2/1
zwj = 5/3/1
flag = 4/2/1
```

Các tỷ lệ là **UTF-16 units / code points / grapheme clusters**. Nếu cần chính xác một phiên bản Unicode/CLDR hoặc các quy tắc phân đoạn đặc thù, dùng bộ test phiên bản rõ ràng; có thể xem xét một thư viện Unicode chuyên sâu như ICU4J khi phạm vi JDK không đủ.

### 10.1. Đảo chuỗi mà không phá grapheme

`StringBuilder.reverse()` có logic giữ thứ tự high–low surrogate của các cặp hợp lệ, nhưng **không tự bảo toàn mọi grapheme**. Một combining mark có thể chuyển sang trước ký tự cơ sở.

Lưu `ReverseGraphemeDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.MatchResult;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class ReverseGraphemeDemo {
    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String accent = "e" + (char) 0x0301;
        String text = "A" + accent + emoji + "B";
        String expected = "B" + emoji + accent + "A";

        String reversedUnits =
                new StringBuilder(text).reverse().toString();

        List<String> clusters = Pattern.compile("\\X")
                .matcher(text).results()
                .map(MatchResult::group)
                .collect(Collectors.toCollection(ArrayList::new));
        Collections.reverse(clusters);
        String reversedClusters = String.join("", clusters);

        System.out.println("clusters = " + clusters.size());
        System.out.println("builderKeepsEmoji = " +
                (reversedUnits.codePoints()
                        .filter(cp -> cp == 0x1F600)
                        .count() == 1));
        System.out.println("builderCorrect = " +
                reversedUnits.equals(expected));
        System.out.println("clusterCorrect = " +
                reversedClusters.equals(expected));
    }
}
```

```bash
javac ReverseGraphemeDemo.java
java ReverseGraphemeDemo
```

```text
clusters = 4
builderKeepsEmoji = true
builderCorrect = false
clusterCorrect = true
```

Đảo theo code point cũng có thể làm hỏng grapheme nhiều code point. Với UI cần đảo chữ theo cách người dùng cảm nhận, phải chọn **grapheme** làm đơn vị, không chỉ “không bẻ đôi surrogate”.

## 11. Unicode normalization không tự diễn ra trong `codePoints()`

Một chữ hiển thị như “é” có thể được biểu diễn bằng:

- U+00E9: một **precomposed code point**.
- U+0065 và U+0301: chữ e và dấu tổ hợp, **hai code point**.

`String.equals` so UTF-16 units nên hai chuỗi chưa chắc bằng nhau trước normalization. `java.text.Normalizer` có `NFC` và `NFD` để thực hiện canonical normalization, cùng NFKC/NFKD cho compatibility normalization khi cần.

Lưu `UnicodeNormalizationDemo.java`:

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equalBefore = " +
                composed.equals(decomposed));
        System.out.println("composedCount = " +
                composed.codePoints().count());
        System.out.println("decomposedCount = " +
                decomposed.codePoints().count());

        String left = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("equalNFC = " +
                left.equals(right));
        System.out.println("equalNFD = " +
                Normalizer.normalize(composed,
                        Normalizer.Form.NFD).equals(
                Normalizer.normalize(decomposed,
                        Normalizer.Form.NFD)));
    }
}
```

```bash
javac UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

```text
equalBefore = false
composedCount = 1
decomposedCount = 2
equalNFC = true
equalNFD = true
```

Normalization có thể làm **thay đổi số code point**. Nó không tự đồng nghĩa case folding hay phòng chống homoglyph/confusable spoofing. Hãy xác định chính sách input, tìm kiếm và storage rõ ràng thay vì coi mọi chuỗi “trông giống nhau” đều phải bằng nhau.

## 12. `CharSequence` mutable và cơ chế late-binding

Javadoc nói stream từ `CharSequence.codePoints()` và `chars()` bind vào sequence **khi terminal stream operation bắt đầu**; với các sequence mutable, spliterator là late-binding. Nếu sequence bị sửa **trong lúc terminal operation đang đọc**, kết quả **undefined** theo contract.

Lưu `LateBindingDemo.java`:

```java
import java.util.stream.IntStream;

public class LateBindingDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");

        IntStream delayed = builder.codePoints();
        builder.appendCodePoint(0x1F600);

        long atTerminal = delayed.count();
        String snapshot = builder.toString();
        builder.append('B');

        System.out.println("atTerminal = " + atTerminal);
        System.out.println("snapshot = " +
                snapshot.codePoints().count());
        System.out.println("builderNow = " +
                builder.codePoints().count());
    }
}
```

```bash
javac LateBindingDemo.java
java LateBindingDemo
```

```text
atTerminal = 2
snapshot = 2
builderNow = 3
```

Đây là mutation **trước hoặc sau terminal operation**, không phải mutation đồng thời trong lúc stream duyệt. Không dùng ví dụ này để hợp thức hóa việc sửa `StringBuilder` từ thread khác khi `codePoints()` đang được tiêu thụ.

Khi cần nội dung ổn định, dùng immutable `String`. Nếu builder đang bị nhiều thread sửa mà không được phối hợp, ngay cả gọi `builder.toString()` có thể không cho một snapshot được đảm bảo nhất quán. Cần cơ chế ownership/synchronization thích hợp.

## 13. UTF-8, byte count và Base64 là tầng riêng

`codePoints()` cho các số Unicode bên trong Java, **không trả bytes**. `String.getBytes(StandardCharsets.UTF_8)` mã hóa thành byte, và `Base64` mã hóa byte thành ASCII. Ví dụ `"A😀B"` dài 4 UTF-16 units, 3 code points, **6 UTF-8 bytes**.

Với malformed Unicode như một unpaired surrogate, các convenience encoding methods thường dùng **replacement policy**. Nếu muốn **báo lỗi** thay vì mất thông tin, dùng `CharsetEncoder` có `CodingErrorAction.REPORT`.

Lưu `Utf8Base64Demo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Utf8Base64Demo {
    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        byte[] bytes = text.getBytes(
                StandardCharsets.UTF_8);
        String b64 = Base64.getEncoder()
                .encodeToString(bytes);
        String back = new String(
                Base64.getDecoder().decode(b64),
                StandardCharsets.UTF_8);

        String malformed = "A" +
                Character.highSurrogate(0x1F600) + "B";
        boolean reported = false;

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(malformed));
        } catch (CharacterCodingException e) {
            reported = true;
        }

        System.out.println("utf16 = " + text.length());
        System.out.println("points = " +
                text.codePoints().count());
        System.out.println("utf8Bytes = " + bytes.length);
        System.out.println("base64RoundTrip = " +
                text.equals(back));
        System.out.println("malformedReported = " +
                reported);
    }
}
```

```bash
javac Utf8Base64Demo.java
java Utf8Base64Demo
```

```text
utf16 = 4
points = 3
utf8Bytes = 6
base64RoundTrip = true
malformedReported = true
```

Base64 **không phải encryption**. Nếu yêu cầu thực tế là giới hạn số bytes tải lên, cần đo byte array (và có thể kích thước Base64 sau mã hóa), không dùng `String.length` hoặc số code point làm proxy.

## 14. Dựng mảng code point và tính chi phí

Khi muốn truy cập code point theo chỉ số nhiều lần:

```java
int[] points = text.codePoints().toArray();
String rebuilt = new String(points, 0, points.length);
```

*Snippet yêu cầu `text` có nội dung well-formed nếu đầu ra cần Unicode scalar hợp lệ.*

Lưu `CodePointArrayRoundTripDemo.java`:

```java
import java.util.Arrays;

public class CodePointArrayRoundTripDemo {
    public static void main(String[] args) {
        String smile = new String(
                Character.toChars(0x1F600));
        String music = new String(
                Character.toChars(0x1D11E));
        String text = "Q" + smile + music;

        int[] points = text.codePoints().toArray();
        String rebuilt = new String(
                points, 0, points.length);

        int unitsFromPoints = Arrays.stream(points)
                .map(Character::charCount).sum();

        System.out.println("arraySize = " + points.length);
        System.out.println("utf16Units = " + text.length());
        System.out.println("unitsFromPoints = " +
                unitsFromPoints);
        System.out.println("sameText = " +
                text.equals(rebuilt));
    }
}
```

```bash
javac CodePointArrayRoundTripDemo.java
java CodePointArrayRoundTripDemo
```

```text
arraySize = 3
utf16Units = 5
unitsFromPoints = 5
sameText = true
```

Với một lượt quét text, `codePoints()` thường đủ. Tạo `int[]` giúp random access theo ordinal nhưng có chi phí **cấp phát bộ nhớ**. Nếu liên tục gọi `offsetByCodePoints(0,i)` cho mọi `i` tăng dần, có thể khiến chương trình scan lặp lại; vòng lặp UTF-16 index hoặc tạo mảng một lần sẽ hợp lý hơn.

`String.length()` thường trả nhanh UTF-16 length nhưng không trả code point count. Với câu hỏi hiệu năng stream so với loop, **benchmark trên dữ liệu đại diện**, không suy đoán từ một ví dụ 3 ký tự.

## 15. Bài tập và lời giải

**Bài 1:** Với `"A😀B"`, tính `length`, `chars().count()` và `codePoints().count()`, rồi nêu rõ đơn vị của từng số.

**Bài 2:** Dùng `codePointAt(1)` và `codePointAt(2)` trên chuỗi trên. Vì sao một lời gọi nhận emoji còn lời gọi kia nhận low surrogate?

**Bài 3:** Tạo một chuỗi chứa high surrogate lẻ; kiểm tra `Character.isValidCodePoint` và tự viết predicate kiểm tra Unicode scalar.

**Bài 4:** Viết `substringByCodePoints` dùng `offsetByCodePoints`. Test với chuỗi chứa hai supplementary code point và một chữ ASCII ở giữa.

**Bài 5:** So sánh `"e\u0301"`, emoji ZWJ và lá cờ: unit count, code point count, grapheme cluster count. Chọn đơn vị cho một giới hạn chiều dài nhập liệu của UI.

**Bài 6:** Với `"\u00E9"` và `"e\u0301"`, giải thích vì sao `equals` trước normalization false nhưng sau NFC true.

**Bài 7:** Đảo chuỗi chứa dấu kết hợp, phân biệt `StringBuilder.reverse` với đảo theo regex `\\X`.

**Bài 8:** Mã hóa `"A😀B"` thành UTF-8 và Base64, rồi giải mã ngược. Khi gặp surrogate lẻ, làm thế nào để strict encoder báo lỗi?

### 15.1. Chương trình tổng kết

Lưu `CodePointsPracticeDemo.java`:

```java
public class CodePointsPracticeDemo {
    static boolean scalar(int cp) {
        return Character.isValidCodePoint(cp)
                && (cp < 0xD800 || cp > 0xDFFF);
    }

    static String slice(String text, int first, int count) {
        if (first < 0 || count < 0) {
            throw new IllegalArgumentException("negative range");
        }
        int begin = text.offsetByCodePoints(0, first);
        int end = text.offsetByCodePoints(begin, count);
        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        String emoji = new String(
                Character.toChars(0x1F600));
        String text = "A" + emoji + "B";
        String bad = "A" +
                Character.highSurrogate(0x1F600) + "B";

        System.out.println("length = " + text.length());
        System.out.println("points = " +
                text.codePoints().count());
        System.out.println("sliceCorrect = " +
                slice(text, 1, 1).equals(emoji));
        System.out.println("validText = " +
                text.codePoints().allMatch(
                        CodePointsPracticeDemo::scalar));
        System.out.println("validBroken = " +
                bad.codePoints().allMatch(
                        CodePointsPracticeDemo::scalar));
    }
}
```

```bash
javac CodePointsPracticeDemo.java
java CodePointsPracticeDemo
```

```text
length = 4
points = 3
sliceCorrect = true
validText = true
validBroken = false
```

Các bài còn lại có lời giải và chương trình tương ứng tại `CodePointIndexDemo`, `SafeCodePointSliceDemo`, `GraphemeCountDemo`, `ReverseGraphemeDemo`, `UnicodeNormalizationDemo` và `Utf8Base64Demo`.

## 16. Những lỗi phổ biến

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi `String.length()` là số Unicode characters | Đếm đôi supplementary | Dùng `codePointCount`/`codePoints().count()` |
| Dùng `chars()` để nhận emoji nguyên vẹn | Nhận 2 surrogate | Dùng `codePoints()` |
| Cast `int cp` thành `char` | Truncation với supplementary | Dùng `toChars`/`appendCodePoint` |
| Lấy code point thứ n bằng `codePointAt(n)` | n là UTF-16 index | Dùng `offsetByCodePoints` |
| Cắt `substring` giữa high/low surrogate | Tạo unpaired surrogate | Kiểm tra ranh giới/cắt theo cp |
| Nghĩ `codePoints()` validate text | Unpaired surrogate vẫn được trả | Scalar validation/strict encoder |
| Chỉ dùng `isValidCodePoint` | Surrogate nằm trong dải số hợp lệ | Loại U+D800..U+DFFF |
| Coi code point là một grapheme | Hỏng dấu/emoji ZWJ/flag | Regex `\\X` hoặc segmentation chuyên dụng |
| Dùng `StringBuilder.reverse` cho văn bản có dấu | Có thể đảo sai grapheme | Đảo theo cụm nếu cần |
| Filter bỏ dấu kết hợp/ZWJ | Hỏng hiển thị | Chính sách filter theo domain |
| So chuỗi khác normalization | Cùng kiểu hiển thị nhưng không equal | Normalizer theo contract |
| Đo size UTF-8 bằng `length` | Giới hạn bytes sai | `getBytes(UTF_8).length` |
| Nghĩ Base64 là bảo mật | Lộ dữ liệu nếu không có kiểm soát | HTTPS/encryption/permission riêng |
| Sửa StringBuilder trong terminal stream | Undefined theo Javadoc | Snapshot/ownership/synchronization |
| So benchmark từ một chuỗi ngắn | Suy ra hiệu năng sai | Đo workload thật, warmup, profiler |

## 17. Checklist trước khi sử dụng trong production

- Đơn vị yêu cầu là **UTF-8 byte**, UTF-16 code unit, code point hay grapheme?
- Có dữ liệu ngoài BMP và cặp surrogate? Có test bằng U+1F600/U+1D11E?
- `codePoints` có được dùng khi cần duyệt theo code point thay vì `chars`?
- Mọi index truyền vào `substring/charAt/codePointAt` có đúng là UTF-16 offset?
- Cắt chunk có tránh nằm giữa high/low surrogate?
- Có thể có unpaired surrogate từ dữ liệu ngoài hoặc việc cắt sai?
- Đã xác định **reject/replace/preserve** khi text malformed?
- Có kiểm tra vùng surrogate riêng nếu cần Unicode scalar values?
- Input đa ngôn ngữ/dấu tổ hợp/emoji ZWJ có cần grapheme segmentation?
- Có normalize theo quy tắc nhất quán giữa backend và frontend?
- `StringBuilder` hoặc `CharBuffer` có bị sửa trong lúc stream terminal operation chạy?
- Có dùng UTF-8 charset rõ ràng trước Base64/ghi file/gửi request?
- Có kiểm tra dữ liệu bị thay thế khi encode malformed UTF-16 không?
- Đang dùng hàm `Character.isLetter/Unicode` theo phiên bản JDK nào?
- Có tránh xây `int[]` không cần thiết hoặc scan ordinal nhiều lần?
- Ví dụ chạy trên Java 17+ và stdout không phụ thuộc font hiển thị emoji?

## 18. Nguồn Oracle chính thức

- `CharSequence` và `chars()/codePoints()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html
- `String`, `codePointAt`, `offsetByCodePoints`, UTF-16: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- `Character`, Unicode representation, surrogate helpers: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html
- `StringBuilder` và `reverse`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StringBuilder.html
- `Pattern`, grapheme cluster matcher `\\X`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html
- `Normalizer`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html
- `CharsetEncoder` và `CodingErrorAction`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `Base64`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html

**Tóm tắt:** `CharSequence.codePoints()` là cách hiện hành để đi qua các **code point** Java từ UTF-16, ghép đúng surrogate pair hợp lệ. Nó **không** tự sửa surrogate lẻ, **không** đếm grapheme cluster và **không** trả bytes UTF-8. Chọn đúng đơn vị cho đếm/cắt/validation, quy đổi index bằng `offsetByCodePoints`, dùng `Character` với `int`, và kiểm thử đủ các trường hợp ngoài BMP, dấu tổ hợp, chuỗi emoji và malformed input.