# Kiểm thử chỉ số đầu–cuối và khoảng trích xuất trong Java String

## 1. Mục tiêu và vấn đề cần kiểm thử

Khi tách một phần văn bản bằng `substring`, `subSequence`, `charAt` hoặc chép ký tự với `getChars`, chỉ cần lệch một đơn vị chỉ số là có thể thu được nội dung sai, làm mất ký tự hoặc phát sinh ngoại lệ. Lỗi thường không xuất hiện ở trường hợp bình thường mà lộ ra với chuỗi rỗng, chỉ số bằng độ dài, khoảng có hai đầu bằng nhau hoặc ký tự Unicode dùng nhiều UTF-16 code unit.

Bài này hướng dẫn cách **định nghĩa khoảng chỉ số**, **tạo bộ ca kiểm thử bao phủ ranh giới**, **kiểm tra cả kết quả lẫn ngoại lệ**, và **kiểm thử một hàm trích xuất tự viết**. Đối tượng nghiên cứu chính là `java.lang.String` trên Java 17+, có mở rộng sang `CharSequence` và các thao tác liên quan khi cần.

Sau bài học, bạn có thể:

- Diễn giải chính xác quy ước `[beginIndex, endIndex)`.
- Phân biệt phạm vi hợp lệ của `substring`, `charAt`, `codePointAt` và `getChars`.
- Thiết kế các ca kiểm thử cho **đầu, giữa, cuối, rỗng, vượt biên, đảo đầu–cuối**.
- Đối chiếu độ dài theo **UTF-16 code unit** với Unicode code point.
- Viết chương trình kiểm thử độc lập, mở rộng thành unit test JUnit và suy luận các thuộc tính đúng cho một khoảng trích xuất.

## 2. Cơ sở: chỉ số trong String là chỉ số UTF-16

Trong Java, `String.length()` trả **số UTF-16 code unit**. Với văn bản ASCII như `"ABCDE"`, mỗi ký tự chiếm một code unit:

```text
Chuỗi:     A  B  C  D  E
Chỉ số:    0  1  2  3  4
Ranh giới: 0  1  2  3  4  5
                                 length() = 5
```

Phần tử tại chỉ số `i` được truy cập bằng `charAt(i)`; chỉ số cuối cùng có thể truy cập là `length() - 1` khi chuỗi không rỗng. Trong khi đó, một **ranh giới cắt** hoàn toàn có thể nằm tại vị trí `length()` (ngay sau ký tự cuối).

Không được đồng nhất hai loại chỉ số:
- **Chỉ số phần tử:** phải có `0 <= i < length()`.
- **Chỉ số ranh giới khoảng:** có thể có `0 <= boundary <= length()`.

Chính vì vậy `"ABCDE".charAt(5)` không hợp lệ nhưng `"ABCDE".substring(5, 5)` lại hợp lệ và trả `""`.

**UTF-16 không đồng nhất với ký tự người dùng nhìn thấy.** Một code point ngoài Basic Multilingual Plane, chẳng hạn emoji `😀`, cần **hai code unit** (cặp surrogate). Kết quả của `length()` và vị trí mà `substring` nhận vào đều tính theo code unit, không tính theo số code point hay grapheme cluster.

## 3. Hợp đồng API quan trọng

### 3.1. substring(beginIndex, endIndex)

Chữ ký:

```java
public String substring(int beginIndex, int endIndex);
```

Khoảng được lấy là **nửa mở**, ký hiệu toán học `[beginIndex, endIndex)`: **bao gồm beginIndex, loại trừ endIndex**.

Điều kiện hợp lệ:

```text
0 <= beginIndex <= endIndex <= s.length()
```

Kết quả chứa `endIndex - beginIndex` UTF-16 code unit, bắt đầu ở `beginIndex` và dừng trước `endIndex`.

```java
String s = "ABCDE";

System.out.println(s.substring(1, 4)); // BCD
System.out.println(s.substring(0, 5)); // ABCDE
System.out.println(s.substring(3, 3).isEmpty()); // true
System.out.println(s.substring(5, 5).isEmpty()); // true
```

`substring(1, 4)` lấy vị trí 1, 2, 3; **không lấy** vị trí 4. Nếu muốn lấy cả phần tử cuối ở vị trí 4, truyền `endIndex = 5`.

Một khoảng **rỗng** như `[3, 3)` hoàn toàn hợp lệ; kết quả là `""`. Hai đầu bằng nhau không phải lỗi.

### 3.2. substring(beginIndex)

Overload một tham số:

```java
public String substring(int beginIndex);
```

Lấy từ `beginIndex` đến hết chuỗi:

```java
String s = "ABCDE";

System.out.println(s.substring(2));  // CDE
System.out.println(s.substring(5));  // Dòng trống vì kết quả là ""
```

Điều kiện hợp lệ: `0 <= beginIndex <= s.length()`. Giá trị bằng `length()` được phép và trả chuỗi rỗng; giá trị lớn hơn `length()` hoặc âm thì không hợp lệ.

### 3.3. subSequence(start, end)

`String` triển khai `CharSequence` và hỗ trợ:

```java
public CharSequence subSequence(int start, int end);
```

Phạm vi **`[start, end)`** giống `substring(start, end)`. Khi gọi trên đối tượng `String`, nội dung kết quả bằng với nội dung được `substring` trả về:

```java
String s = "ABCDE";
CharSequence part = s.subSequence(1, 4);
System.out.println(part); // BCD
```

Tuy nhiên, biến `part` có kiểu khai báo `CharSequence`; phương thức của những lớp cài đặt `CharSequence` khác không nhất thiết có cùng cách lưu bộ nhớ hoặc vòng đời như `String`. Kiểm thử theo **hợp đồng của đối tượng thực sự đang dùng**.

### 3.4. charAt(index)

`charAt` truy cập một UTF-16 code unit **tại một vị trí**, không trích xuất khoảng:

```java
String s = "ABCDE";
System.out.println(s.charAt(0)); // A
System.out.println(s.charAt(4)); // E
// s.charAt(5); // StringIndexOutOfBoundsException
```

Điều kiện hợp lệ là `0 <= index < s.length()`. Trên chuỗi rỗng, không có chỉ số hợp lệ cho `charAt`.

### 3.5. Ngoại lệ khi chỉ số không hợp lệ

`substring` và những thao tác liên quan thuộc họ ngoại lệ `IndexOutOfBoundsException` khi biên vượt phạm vi. OpenJDK/HotSpot thường ném `StringIndexOutOfBoundsException` đối với nhiều lỗi `String`, nhưng **bài kiểm thử portable** có thể kiểm tra lớp ngoại lệ theo hợp đồng API (`IndexOutOfBoundsException`) thay vì phụ thuộc từng chi tiết thông báo.

Thông báo của ngoại lệ (ví dụ `begin 6, end 5, length 5`) có thể thay đổi theo phiên bản JDK. Không nên so khớp nguyên văn exception message khi chỉ cần xác nhận ranh giới sai bị từ chối.

## 4. Ma trận ca kiểm thử chuẩn cho substring

Dùng chuỗi `"ABCDE"` có `length() = 5` để đối chiếu:

| Trường hợp | Lời gọi | Kỳ vọng |
| --- | --- | --- |
| Đầu chuỗi | `substring(0, 1)` | `"A"` |
| Giữa chuỗi | `substring(1, 4)` | `"BCD"` |
| Ký tự cuối | `substring(4, 5)` | `"E"` |
| Toàn bộ chuỗi | `substring(0, 5)` | `"ABCDE"` |
| Khoảng rỗng đầu | `substring(0, 0)` | `""` |
| Khoảng rỗng giữa | `substring(3, 3)` | `""` |
| Khoảng rỗng cuối | `substring(5, 5)` | `""` |
| Suffix từ giữa | `substring(2)` | `"CDE"` |
| Suffix rỗng | `substring(5)` | `""` |
| Begin âm | `substring(-1, 2)` | Ném `IndexOutOfBoundsException` |
| End âm | `substring(0, -1)` | Ném `IndexOutOfBoundsException` |
| Begin lớn hơn end | `substring(4, 3)` | Ném `IndexOutOfBoundsException` |
| End lớn hơn length | `substring(1, 6)` | Ném `IndexOutOfBoundsException` |
| Begin lớn hơn length | `substring(6)` | Ném `IndexOutOfBoundsException` |

Ma trận phải có **hai loại kiểm tra**: kết quả chính xác cho khoảng hợp lệ và ngoại lệ cho khoảng sai. Việc chỉ kiểm tra “không bị lỗi” chưa đủ để phát hiện lệch một ký tự.

Một cách tổ chức thực tế là luôn chọn các giá trị quanh biên `0` và `length()`: `-1`, `0`, `1`, `length()-1`, `length()`, `length()+1` (khi chúng có ý nghĩa). Với chuỗi rỗng, `length()-1 = -1` là chỉ số bất hợp lệ; đây chính là ca cần kiểm thử.

## 5. Chuỗi rỗng và các khoảng có hai đầu trùng nhau

Đây là nguồn lỗi phổ biến khi code tự thêm hoặc bớt `1`:

```java
String empty = "";

System.out.println(empty.substring(0, 0).isEmpty()); // true
System.out.println(empty.substring(0).isEmpty());    // true

// empty.charAt(0);      // Không hợp lệ: không có phần tử
// empty.substring(0, 1); // Không hợp lệ: end > length
```

Với một chuỗi bất kỳ `s`, tất cả khoảng dạng `s.substring(i, i)` đều cho chuỗi rỗng **nếu** `0 <= i <= s.length()`. Điều này có nghĩa khoảng rỗng ở cuối chuỗi có thể hợp lệ.

Cần phân biệt **khoảng rỗng** với **giá trị nguồn rỗng**:
- `"ABCDE".substring(2, 2)` rỗng dù nguồn không rỗng.
- `"".substring(0, 0)` rỗng vì cả nguồn lẫn khoảng rỗng.
- `"".substring(1, 1)` vẫn sai vì ranh giới 1 nằm ngoài độ dài 0.

Hàm tạo slice có thể cho phép khoảng rỗng (thường hợp lý), hoặc cấm theo quy tắc nghiệp vụ. Nếu cấm, phải ghi rõ đó là **ràng buộc riêng của hàm nghiệp vụ**, không gán nhầm cho `String.substring`.

## 6. Tự viết một hàm trích xuất với quy tắc kiểm tra rõ ràng

Giả sử muốn viết hàm `slice` xử lý theo khoảng `[begin, end)`:

```java
static String slice(String source, int begin, int end) {
    if (source == null) {
        throw new IllegalArgumentException("source must not be null");
    }

    int length = source.length();
    if (begin < 0 || end < begin || end > length) {
        throw new IndexOutOfBoundsException(
                "Invalid range [" + begin + ", " + end
                        + ") for length " + length);
    }

    return source.substring(begin, end);
}
```

Đây là **đoạn phương thức minh họa**, cần đặt bên trong một lớp Java trước khi biên dịch. Hàm chủ động ném `IllegalArgumentException` khi `source == null`. Quyết định này thuộc thiết kế `slice`; bản thân `String.substring` được gọi trên một tham chiếu null sẽ gặp `NullPointerException` trước khi vào phương thức.

Điều kiện kiểm tra gộp chính xác ba lỗi:
- `begin < 0`: chỉ số bắt đầu âm.
- `end < begin`: khoảng bị đảo ngược; cũng bao phủ một số giá trị end âm.
- `end > length`: điểm kết thúc vượt khỏi chuỗi; đồng thời ngăn begin lớn hơn length nếu `end >= begin`.

Có thể kiểm tra tường minh thêm `begin > length` để thông báo dễ hiểu, nhưng về tính hợp lệ, ba mệnh đề trên đã đủ do điều kiện `begin <= end`.

Lưu ý quan trọng khi **tự tạo hàm chuyển khoảng inclusive thành exclusive**: nếu end-inclusive bằng `Integer.MAX_VALUE`, cộng `1` có thể tràn số nguyên. Cần xác nhận end nằm trong phạm vi chuỗi **trước khi cộng** hoặc dùng cách kiểm tra không gây overflow.

## 7. Chương trình Java 17+ kiểm thử tự động, độc lập

Ví dụ sau có bộ kiểm thử nhỏ không phụ thuộc JUnit. Nó giúp thấy rõ cách kiểm tra giá trị trả về, ngoại lệ và độ dài Unicode.

Tạo tệp `StringRangeTest.java`, lưu bằng UTF-8:

```java
import java.util.Objects;

public class StringRangeTest {
    private static int passed = 0;

    private static void equal(Object expected, Object actual, String name) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    private static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
    }

    private static void throwsType(
            Class<? extends Throwable> type,
            Runnable action,
            String name) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                passed++;
                return;
            }
            throw new AssertionError(name + " wrong exception", error);
        }
        throw new AssertionError(name + " did not throw");
    }

    public static void main(String[] args) {
        String s = "ABCDE";

        equal("BCD", s.substring(1, 4), "middle");
        equal("ABCDE", s.substring(0, 5), "whole");
        equal("", s.substring(3, 3), "empty middle");
        equal("", s.substring(5, 5), "empty end");
        equal("", "".substring(0, 0), "empty source");
        equal("CDE", s.substring(2), "one-argument suffix");
        equal("BCD", s.subSequence(1, 4).toString(), "subSequence");
        equal('E', s.charAt(4), "last char");

        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(-1, 2), "negative begin");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(1, 6), "end after length");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(4, 3), "reversed range");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(6), "one-argument invalid begin");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.charAt(5), "charAt at length");

        String unicode = "A😀B";
        equal("😀", unicode.substring(1, 3), "full surrogate pair");
        equal(2, unicode.substring(1, 3).length(),
                "emoji code-unit length");
        equal(1, unicode.codePointCount(1, 3),
                "emoji code-point count");
        check(Character.isHighSurrogate(
                unicode.substring(1, 2).charAt(0)),
                "partial surrogate boundary");

        System.out.println("PASS: " + passed + " tests");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StringRangeTest.java
java StringRangeTest
```

Kết quả stdout nếu mọi kiểm tra thành công:

```text
PASS: 17 tests
```

Chương trình sử dụng bộ so sánh `Objects.equals` để kiểm tra cả giá trị trả về, dùng `throwsType` để chấp nhận ngoại lệ **đúng họ** và dùng `check` cho thuộc tính Unicode. Không cần bật cờ `-ea`, vì các helper chủ động ném `AssertionError` khi thất bại.

Một test bị lỗi sẽ ném `AssertionError` và dừng chương trình, nhờ đó kết quả “PASS” không che giấu sai lệch ở các bước trước. Trên dự án thật, nên sử dụng framework unit test (ví dụ JUnit 5) để thu thập báo cáo đầy đủ và chạy tự động trong CI.

## 8. Kiểm thử UTF-16 và khoảng cắt qua surrogate pair

Xét chuỗi chứa emoji ngoài BMP:

```java
String text = "A😀B";
System.out.println(text.length()); // 4
```

Vị trí UTF-16 như sau:

```text
index 0 : 'A'
index 1 : high surrogate của 😀
index 2 : low surrogate của 😀
index 3 : 'B'
boundary: 0 | 1 | 2 | 3 | 4
```

Vì vậy:
- `text.substring(1, 3)` lấy **đủ hai code unit** và biểu diễn emoji hoàn chỉnh.
- `text.substring(1, 2)` lấy **một high surrogate đơn lẻ**. Lời gọi hợp lệ về mặt chỉ số, nhưng kết quả chứa một surrogate chưa ghép cặp.
- `text.substring(2, 3)` chỉ lấy low surrogate, cũng tạo chuỗi không hoàn chỉnh về mặt cặp surrogate.
- `text.substring(3, 4)` lấy `"B"`.

**Java String cho phép chứa các surrogate đơn lẻ.** `substring` chỉ thực thi hợp đồng chỉ số UTF-16, không tự xác minh rằng điểm cắt trùng với ranh giới code point hay ranh giới ký tự hiển thị.

Nếu yêu cầu là “lấy hai Unicode code point đầu” thay vì “lấy hai code unit đầu”, hãy đổi chỉ số theo code point:

```java
String text = "A😀B";
int end = text.offsetByCodePoints(0, 2);
String firstTwoCodePoints = text.substring(0, end);

System.out.println(end); // 3
System.out.println(firstTwoCodePoints); // A😀
```

`offsetByCodePoints(beginIndex, codePointOffset)` giúp dịch một số lượng code point thành một chỉ số UTF-16. Thao tác này vẫn **không đồng nghĩa tách grapheme cluster**: ký tự + dấu kết hợp, chuỗi emoji có ZWJ hoặc cờ emoji có thể gồm nhiều code point nhưng được hiển thị như một cụm. Với yêu cầu theo *ký tự người dùng nhìn thấy*, cần thuật toán phân đoạn văn bản phù hợp với Unicode, locale và nhu cầu thực tế.

## 9. getChars: kiểm tra khoảng nguồn và vị trí đích

Ngoài `substring`, `String.getChars(srcBegin, srcEnd, dst, dstBegin)` chép **vùng `[srcBegin, srcEnd)`** sang mảng đích:

```java
String s = "ABCDE";
char[] dst = {'_', '_', '_', '_', '_'};

s.getChars(1, 4, dst, 1);

System.out.println(String.valueOf(dst)); // _BCD_
```

Khoảng nguồn `[1,4)` dài **3**; nó được chép vào `dst[1]`, `dst[2]` và `dst[3]`. Kiểm thử `getChars` phải xét **cả hai hệ chỉ số**:

- Nguồn: `0 <= srcBegin <= srcEnd <= s.length()`.
- Đích: `dstBegin >= 0` và `dstBegin + (srcEnd - srcBegin) <= dst.length`, với phép cộng được thực hiện an toàn để không tràn số nếu tự viết hàm kiểm tra.
- Mảng `dst` phải tồn tại; nếu null, việc sử dụng mảng có thể gây `NullPointerException`.

Để tránh tràn số trong logic kiểm tra tự viết, sau khi xác nhận `0 <= dstBegin <= dst.length` có thể kiểm tra `copyCount <= dst.length - dstBegin`.

Các ca kiểm thử đáng có:
1. Sao chép vào giữa mảng và xác nhận các vị trí ngoài vùng không bị thay đổi.
2. Sao chép vùng rỗng với `srcBegin == srcEnd`.
3. `srcEnd > s.length()` hoặc `srcBegin < 0`.
4. `dstBegin < 0` hoặc vùng đích không đủ sức chứa.
5. Kết quả với surrogate pair, vì `getChars` cũng chép theo UTF-16 code unit.

Điểm khác biệt: `substring` tạo ra một kết quả `String`, trong khi `getChars` **thay đổi nội dung mảng đích** theo vùng chọn. Vì vậy phải kiểm tra cả tính chính xác của vùng chép và tính toàn vẹn của những ô mảng nằm ngoài vùng.

## 10. Trích xuất dựa trên indexOf: đừng tự tạo lỗi +1/-1

Trường hợp thực tế thường tìm ranh giới động:

```java
String input = "user=alice;role=admin";
int begin = input.indexOf('=') + 1;
int end = input.indexOf(';');
String user = input.substring(begin, end);

System.out.println(user); // alice
```

Ví dụ hoạt động với định dạng cụ thể này, nhưng **không an toàn cho mọi đầu vào**. Nếu không có dấu `=`, `indexOf('=')` trả `-1` và cộng 1 thành `0`; lỗi thiếu delimiter có thể bị che khuất. Nếu thiếu dấu `;`, `end = -1` và `substring` ném ngoại lệ.

Thiết kế kiểm tra trước khi trích xuất:

```java
static String extractBeforeSemicolon(String input) {
    if (input == null) {
        throw new IllegalArgumentException("input is null");
    }

    int equal = input.indexOf('=');
    if (equal < 0) {
        throw new IllegalArgumentException("Missing '='");
    }

    int begin = equal + 1;
    int end = input.indexOf(';', begin);
    if (end < 0) {
        throw new IllegalArgumentException("Missing ';'");
    }

    return input.substring(begin, end);
}
```

Đây là phương thức minh họa, cần đặt bên trong lớp Java. Với quy tắc này, đầu vào `"user=;role=admin"` cho chuỗi rỗng hợp lệ vì `begin == end`; nếu nghiệp vụ cấm giá trị rỗng thì phải thêm kiểm tra riêng.

Nên kiểm thử:
- Delimiter ở vị trí bình thường.
- `=` ngay trước `;` (giá trị rỗng).
- Thiếu `=`, thiếu `;`.
- Dấu `;` xuất hiện trước `=`: nhờ `indexOf(';', begin)`, hàm tìm dấu kết thúc **sau** dấu `=`.
- Đầu vào không có ký tự hoặc `null`.
- Có nhiều dấu `=` hoặc `;`: xác định rõ quy tắc chọn delimiter đầu tiên/hợp lệ của nghiệp vụ.

Đừng viết test chỉ cho một chuỗi “đẹp”; điều cần xác minh là **giả định về vị trí delimiter** trước khi truyền chỉ số cho `substring`.

## 11. Unit test với JUnit 5

Trong dự án có **JUnit Jupiter** trên test classpath, có thể dùng `assertEquals`, `assertThrows` và `assertAll`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringBoundsTest {
    @Test
    void extractsHalfOpenRange() {
        String s = "ABCDE";

        assertEquals("BCD", s.substring(1, 4));
        assertEquals("", s.substring(5, 5));
        assertEquals("E", s.substring(4, 5));
    }

    @Test
    void rejectsInvalidBounds() {
        String s = "ABCDE";

        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(-1, 2));
        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(4, 3));
        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(0, 6));
    }

    @Test
    void countsUtf16UnitsNotCodePoints() {
        String s = "A😀B";

        assertEquals(4, s.length());
        assertEquals("😀", s.substring(1, 3));
        assertEquals(2, s.substring(1, 3).length());
    }
}
```

Đây là **lớp test dành cho dự án đã cấu hình JUnit 5**, không phải một chương trình độc lập chỉ cần `javac` mặc định. JUnit phải có trong dependencies/classpath và test được chạy bằng Maven, Gradle hoặc IDE theo thiết lập của dự án. Phần Java chạy độc lập không cần dependency đã có tại mục 7.

Kiểm thử tham số hóa với `@ParameterizedTest` và `@CsvSource` phù hợp khi cùng một quy tắc được áp dụng cho nhiều cặp begin/end. Tuy nhiên, hãy giữ riêng nhóm **ca hợp lệ** và **ca ném ngoại lệ**, để thông báo thất bại rõ ràng.

## 12. Kiểm thử theo thuộc tính (property-based thinking)

Ngoài các ví dụ đơn lẻ, hãy kiểm tra những **bất biến** sau cho mọi `String s` và mọi cặp `begin, end` hợp lệ:

1. **Độ dài:** `s.substring(begin, end).length() == end - begin`.
2. **Phần tử khớp vị trí:** với mọi `i` trong `[0, end - begin)`, `slice.charAt(i) == s.charAt(begin + i)`.
3. **Khoảng rỗng:** `s.substring(i, i).isEmpty()` cho mọi `0 <= i <= s.length()`.
4. **Ghép lại giữ nội dung:** `s.substring(0, begin) + s.substring(begin, end) + s.substring(end)` bằng `s` về nội dung.
5. **Khoảng toàn bộ:** `s.substring(0, s.length()).equals(s)`.
6. **Bảo toàn chuỗi nguồn:** gọi `substring` không sửa `s` vì `String` immutable.

Các thuộc tính này cũng áp dụng cho chuỗi có surrogate pair nếu đo và chọn ranh giới theo **UTF-16 code unit**. Chúng không đảm bảo mọi lát cắt có cặp surrogate đầy đủ, vì đó là yêu cầu bổ sung ở tầng Unicode.

Có thể tạo các ca **randomized tests** với generator sinh `String` và hai chỉ số hợp lệ, ví dụ chọn `begin` trong `[0, length]` rồi chọn `end` trong `[begin, length]`. Với ca bất hợp lệ, hãy sinh các cặp ra ngoài phạm vi. Khi dùng random, lưu seed khi phát hiện lỗi để tái lập được.

Để tránh bài test “kiểm tra bằng chính hàm đang kiểm tra”, phần lớn các thuộc tính nên được xác minh độc lập bằng `length()`, `charAt()` và một mô hình oracle đơn giản, hoặc đối chiếu với quy tắc dữ liệu ban đầu. Không cần dùng random cho một hàm cực nhỏ nếu ma trận biên đã đủ; đây là kỹ thuật bổ sung hữu ích cho bộ tách nội dung tự viết.

## 13. Chỉ số inclusive của nghiệp vụ và API exclusive của Java

Một số tài liệu nghiệp vụ nói “lấy từ vị trí 2 **đến cả** vị trí 4”. Nếu hai đầu đều inclusive thì cần chuyển sang Java `substring(2, 5)`, không phải `substring(2, 4)`.

Ví dụ:

```java
String s = "ABCDEFG";
int firstInclusive = 2;
int lastInclusive = 4;

String result = s.substring(firstInclusive, lastInclusive + 1);
// CDE
```

Cách cộng 1 chỉ an toàn sau khi xác nhận `lastInclusive` là vị trí ký tự hợp lệ, nghĩa là `0 <= lastInclusive < s.length()`. Kiểm thử logic chuyển đổi phải bao gồm:
- `firstInclusive == lastInclusive` (lấy đúng một ký tự).
- `lastInclusive == s.length() - 1` (lấy đến ký tự cuối).
- `firstInclusive > lastInclusive` (phạm vi sai).
- `lastInclusive < 0` hoặc `lastInclusive >= s.length()` (ngoài phạm vi).
- Chuỗi rỗng: **không có phần tử** nào để áp dụng khoảng inclusive gồm ít nhất một ký tự.

Một nguồn lỗi tương tự là **đếm vị trí từ 1** trong tài liệu hoặc giao diện, trong khi Java dùng chỉ số từ 0. Nếu người dùng chọn “ký tự thứ 3 đến thứ 5” theo cách đếm 1-based và bao gồm cả hai đầu, khoảng Java tương ứng là `substring(2, 5)`. Các quy tắc quy đổi phải được viết rõ trong API và test.

## 14. Phân biệt khoảng nguồn và khoảng mảng, offset/count

Không phải mọi API Java dùng cặp `begin, end`. Một số API dùng **offset và count**: điểm bắt đầu và **số phần tử**. Ví dụ:

```java
char[] chars = {'A', 'B', 'C', 'D', 'E'};

String a = String.valueOf(chars, 1, 3); // "BCD"
String b = new String(chars, 1, 3);      // "BCD"
```

Ở hai lệnh trên, tham số thứ ba là `count = 3`, **không phải `endIndex = 3`. Nếu nhầm hai quy ước, một bài test có thể đậu ngẫu nhiên ở trường hợp `offset = 0` nhưng hỏng ngay khi `offset > 0`.

| API | Tham số chỉ số | Ý nghĩa |
| --- | --- | --- |
| `s.substring(begin, end)` | `begin, end` | Chọn `[begin, end)` |
| `s.subSequence(start, end)` | `start, end` | Chọn `[start, end)` |
| `s.getChars(srcBegin, srcEnd, dst, dstBegin)` | `srcBegin, srcEnd` | Chọn `[srcBegin, srcEnd)` của nguồn |
| `String.valueOf(chars, offset, count)` | `offset, count` | Chọn `count` ký tự từ `offset` |
| `new String(chars, offset, count)` | `offset, count` | Chọn `count` ký tự từ `offset` |
| `s.charAt(index)` | `index` | Chọn một UTF-16 code unit tại `index` |

Khi thiết kế test, trước hết xác định **tham số thứ hai mang ý nghĩa gì**; không lấy công thức `end - begin` áp dụng cho `count` hoặc ngược lại.

## 15. Sai lầm phổ biến trong bài kiểm thử chỉ số

**1. Tưởng `endIndex` được bao gồm.** Điều này làm mất phần tử cuối hoặc gây `end + 1` sai. Với `substring`, điểm cuối luôn **exclusive**.

**2. Nghĩ `substring(length, length)` là lỗi.** Đây là khoảng rỗng hợp lệ. Nhưng `charAt(length)` vẫn là lỗi.

**3. Bỏ qua nguồn rỗng.** Trên `""`, chỉ `substring(0, 0)` hoặc `substring(0)` là các cách lấy khoảng rỗng hợp lệ trong phạm vi này.

**4. Test chỉ trường hợp có dữ liệu.** Lệch `+1/-1` thường lộ ở biên, khoảng một ký tự hoặc khoảng rỗng.

**5. So sánh thông báo exception nguyên văn.** Dạng message có thể khác giữa JDK; ưu tiên kiểm tra kiểu ngoại lệ theo hợp đồng và điều kiện gây lỗi.

**6. Dùng `length()` như số ký tự người dùng nhìn thấy.** Đây là số UTF-16 code unit. Cắt giữa hai surrogate hợp lệ về mặt index nhưng có thể hỏng dữ liệu hiển thị.

**7. Không kiểm tra `indexOf` trả `-1`.** Cộng 1 quá sớm biến `-1` thành `0`, khiến một số lỗi thiếu delimiter trở nên khó phát hiện.

**8. Bỏ qua null.** `source.substring(...)` trên tham chiếu null ném `NullPointerException` trước khi kiểm tra khoảng. Hàm wrapper có thể chủ động xác định ngoại lệ/giá trị mặc định riêng.

**9. Nhầm offset/count với begin/end.** Truyền `String.valueOf(chars, 2, 5)` như thể muốn đến chỉ số 5 thực ra yêu cầu lấy **5** phần tử từ 2, có thể vượt biên.

**10. Kiểm tra ngoại lệ quá rộng.** Bắt mọi `Exception` có thể che lỗi hoàn toàn khác. Khi kiểm thử hành vi cụ thể, kiểm tra họ ngoại lệ thích hợp và không bỏ qua sai lệch.

## 16. Checklist kiểm thử trước khi hoàn thành

Với mỗi hàm tách chuỗi, xác nhận các câu hỏi dưới đây:

- Khoảng sử dụng **`[begin, end)`**, **inclusive/inclusive** hay **offset/count**?
- `length()` được hiểu là UTF-16 code unit hay chương trình thực sự yêu cầu code point/grapheme?
- Các mốc **`0`**, **`length()`**, **`length()-1`** đã được kiểm tra đúng vị trí chưa?
- Có test cho chuỗi rỗng, khoảng rỗng đầu/giữa/cuối, ký tự đầu/cuối và toàn chuỗi không?
- Đã test begin âm, end vượt biên, begin lớn hơn end, và ô đầu vào null nếu API nhận tham chiếu chưa?
- Nếu ranh giới được tính từ delimiter, đã kiểm tra kết quả `indexOf == -1` và delimiter trùng nhau/chồng lấn chưa?
- Nếu mảng đích bị thay đổi, đã kiểm tra **nội dung ngoài vùng ghi vẫn giữ nguyên** chưa?
- Nếu cần Unicode chính xác, đã test surrogate pair và định nghĩa đơn vị “ký tự” chưa?
- Khi sai phạm vi, test kiểm tra **kiểu lỗi phù hợp**, và khi hợp lệ, test so sánh **nội dung chính xác** chứ không chỉ “không lỗi” chưa?

## 17. Ghi nhớ

- Java `String.substring(begin, end)`, `subSequence(start, end)` và `getChars(srcBegin, srcEnd, ...)` dùng **khoảng nửa mở `[begin, end)`**.
- **Khoảng hợp lệ:** `0 <= begin <= end <= length()`. **Ký tự hợp lệ:** `0 <= index < length()`.
- `end == length()` và `begin == end` là các trường hợp **hợp lệ** của `substring`; dữ liệu trả có thể rỗng.
- Kiểm thử phải bao phủ **kết quả đúng** và **ngoại lệ đúng** ở cả hai đầu phạm vi.
- Chỉ số của `String` dựa trên **UTF-16 code unit**; một emoji có thể dài 2 code unit và có thể bị cắt giữa cặp surrogate.
- Các API dùng `offset, count` phải được kiểm thử khác với API dùng `begin, end`.
- Khi tính biên từ `indexOf`, luôn xử lý giá trị `-1` trước khi cắt.
- Với hàm trích xuất tự viết, dùng các thuộc tính như độ dài `end - begin`, bảo toàn nội dung và kiểm tra ngoại lệ để ngăn lỗi lệch một đơn vị.

Tài liệu tham khảo chính thức: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html), [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
