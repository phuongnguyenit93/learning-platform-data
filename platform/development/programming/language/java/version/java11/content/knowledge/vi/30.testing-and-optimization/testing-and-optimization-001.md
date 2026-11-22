# Chuỗi, mảng, khoảng chỉ số và các giá trị rỗng — Kiểm thử và tối ưu Java 11

## 1. Mục tiêu và phạm vi

Khi xử lý `String`, `T[]` hoặc các đoạn dữ liệu theo chỉ số, lỗi nguy hiểm thường không nằm trong thuật toán lớn mà ở những trường hợp rất nhỏ: **null**, **chuỗi rỗng**, **chỉ có khoảng trắng**, **mảng dài 0**, **lát cắt rỗng ở cuối**, **off-by-one**, **Unicode supplementary character**, **số nguyên tràn khi cộng offset + length**, hoặc **API tự đệm dữ liệu thiếu thay vì báo lỗi**. Những sai sót này thường xuất hiện trong parser, import CSV, HTTP payload, file I/O, giao diện người dùng, bộ nhớ đệm và các đường code hiệu năng cao.

Bài nằm trong nhóm **Kiểm thử và tối ưu**: không chỉ nêu phương thức Java, mà trình bày **hợp đồng input/output, kiểm thử biên, kiểm thử ngẫu nhiên có seed, lỗi phổ biến và quyết định tối ưu sau khi đo**. Các API chính đều tồn tại trong **Java 11** và tiếp tục được hỗ trợ trong JDK hiện đại. Ví dụ chính biên dịch được bằng `javac --release 11`, không sử dụng các API nội bộ hay thói quen lỗi thời.

Sau bài học, bạn có thể:

1. Phân biệt `null`, `""`, chuỗi chỉ chứa white space, chuỗi literal `"null"`, mảng `null` và mảng dài 0.
2. Hiểu `String.isEmpty()` so với `isBlank()`, `trim()` so với `strip()`, và tại sao **NBSP U+00A0** không được `Character.isWhitespace` coi là whitespace.
3. Hiểu Java `String` được lập chỉ số theo **UTF-16 code units**: `length()`, `charAt`, `substring` khác `codePointCount`, `codePoints` và ký tự người dùng nhìn thấy.
4. Viết điều kiện **half-open ranges `[fromInclusive, toExclusive)`** và offset-size an toàn bằng `Objects.checkIndex`, `checkFromToIndex`, `checkFromIndexSize`.
5. Biết `Arrays.copyOfRange` có thể **tự đệm 0/null khi to > length**, không luôn ném exception; sử dụng wrapper kiểm bounds khi cần slice nghiêm ngặt.
6. Kiểm thử `System.arraycopy` cho trường hợp đoạn nhớ chồng nhau, `Arrays.equals`, `Arrays.mismatch`, sao chép sâu/nông và mutability.
7. Tránh mất giá trị trống cuối chuỗi với `String.split(regex, -1)`, hiểu `String.lines()` cho chuỗi kết thúc bằng line terminator.
8. Kiểm thử thứ tự và biên ở dữ liệu rỗng, chỉ 1 phần tử, đầu/cuối, malformed index, Unicode và fuzz có seed tái lập.
9. Chọn `StringBuilder`, `StandardCharsets.UTF_8`, pre-validation và JMH khi thực sự cần tối ưu, thay vì microbenchmark thiếu warm-up.
10. Có chương trình Java 11 độc lập chứa 12 nhóm kiểm thử tự xác nhận kết quả.

**Special Note:** chỉ lấy kiến thức còn áp dụng đến hiện giờ. `String.isBlank/strip/lines/repeat` đã có từ Java 11; `Objects.checkIndex`, `Arrays.mismatch` và API Unicode vẫn được sử dụng hiện hành. Không hướng dẫn `sun.*`, các hacks truy cập private String storage hoặc mẹo microbenchmark cũ.

## 2. Bảng khái niệm trước khi viết code

| Giá trị/biểu thức | Ý nghĩa | Điều cần kiểm |
| --- | --- | --- |
| `String value = null` | Không có đối tượng `String` | Gọi `value.length()` ném `NullPointerException` |
| `String value = ""` | String hiện diện, có **0 UTF-16 code units** | `isEmpty() == true`; `isBlank() == true` |
| `" \t\n"` | Không rỗng, nhưng chỉ có Java whitespace | `isEmpty() == false`; `isBlank() == true` |
| `"null"` | Bốn ký tự `n,u,l,l` | Không giống giá trị `null` |
| `new int[0]` | Mảng tồn tại, độ dài 0 | Lấy `a[0]` lỗi; slice `[0,0)` hợp lệ |
| `int[] a = null` | Không có object mảng | `a.length` ném NPE; không đồng nghĩa `new int[0]` |
| `[from,to)` | Bao gồm from, loại trừ to | `0 <= from <= to <= length` |
| `(offset,count)` | Vị trí bắt đầu và số phần tử | `0 <= offset`, `0 <= count`, `offset+count <= length` sau kiểm overflow |
| UTF-16 index | Vị trí `char`/code unit | Supplementary emoji thường dài 2 code units |
| Unicode code point | Scalar value (hoặc unpaired surrogate trong chuỗi không well-formed) | Không luôn tương ứng một glyph/grapheme |
| User-perceived grapheme | Ký tự hiển thị có thể gồm nhiều code points | Emoji ZWJ/combining marks cần segmenter đúng phiên bản Unicode |

**Nguyên tắc thiết kế API:** quyết định rõ đầu vào **cho phép null hay không**, khoảng chỉ số có thể **rỗng hay không**, và khi dữ liệu thiếu thì **báo lỗi hay tự pad**. Không được để hành vi đó phụ thuộc tình cờ vào một phương thức tiện ích.

## 3. String: null, empty, blank và Unicode whitespace

### 3.1. isEmpty chỉ đo length == 0

~~~java
String a = "";
String b = " ";
String c = null;

// a.isEmpty() == true
// b.isEmpty() == false
// c.isEmpty() => NullPointerException
~~~

Đây là **đoạn minh họa**, không phải một file `main`. Muốn kiểm một giá trị nullable không có nội dung, trước tiên **định nghĩa hợp đồng**:

~~~java
static boolean isNullOrEmpty(String value) {
    return value == null || value.isEmpty();
}

static boolean isNullOrBlank(String value) {
    return value == null || value.isBlank();
}
~~~

Hai phép kiểm khác nhau: `" "` là **không rỗng** nhưng **blank**. Không dùng `String.valueOf(null)` để biểu diễn dữ liệu thiếu theo cách máy đọc: nó tạo **literal `"null"`**, dễ nhầm với một chuỗi thực sự chứa bốn ký tự đó.

### 3.2. isBlank và strip là Java 11

`String.isBlank()` và `String.strip()` dựa vào `Character.isWhitespace(int)`; `trim()` cắt các code units có giá trị **≤ U+0020**, nên không tương đương Unicode-aware whitespace logic.

~~~java
"\u2003".isBlank()            // true: EM SPACE U+2003
"\u2003Hi\u2003".strip()       // "Hi"
"\u2003".trim().isEmpty()     // false
"\u00A0".isBlank()            // false: NBSP U+00A0
"\u00A0Hi\u00A0".strip()       // giữ nguyên NBSP
~~~

Các literal dùng Java Unicode escapes để có hành vi tái lập. **U+00A0 NBSP**, **U+2007 FIGURE SPACE** và **U+202F NARROW NO-BREAK SPACE** là những space separators **không được `Character.isWhitespace` coi là whitespace** theo Java. Đừng khẳng định `strip()` loại bỏ **mọi** ký tự mà Unicode White_Space property có thể liệt kê.

`stripLeading()` và `stripTrailing()` cho phép chỉ cắt một đầu. Nếu đang đọc dữ liệu có khoảng trắng mang ý nghĩa (mật khẩu, text editor, CSV quoted fields), **không tự ý strip**. Nếu đang chuẩn hóa tên hiển thị, cần chính sách rõ ràng cho NBSP, Unicode normalization và locale, không âm thầm biến mọi chuỗi thành blank.

### 3.3. Hợp đồng null rõ hơn fallback tùy tiện

~~~java
Objects.requireNonNull(input, "input");                // fail fast
String safe = Objects.requireNonNullElse(input, "");    // explicit default
boolean same = Objects.equals(left, right);             // null-safe equality
~~~

- `requireNonNull` phù hợp khi **null là lỗi lập trình** và phương thức phải nhận chuỗi có thật.
- `requireNonNullElse` phù hợp khi contract **chủ động cho phép default**; default không được null.
- `Objects.equals` hữu ích khi hai references có thể null; lưu ý nó **không** thay `Arrays.equals` để so nội dung mảng.

Không biến **null** thành empty ở mọi tầng nếu việc đó làm mất nghĩa «chưa được cung cấp» đối lập «được cung cấp nhưng rỗng». Với API public, định nghĩa bằng JavaDoc/validation và test rõ.

## 4. String indexing: UTF-16 không phải số ký tự người nhìn thấy

### 4.1. Code units, code points và grapheme clusters

Java `String.length()` trả **số UTF-16 code units**. Ví dụ:

~~~text
String = "A" + U+1F642 (🙂) + "e" + U+0301 (combining acute) + "B"

UTF-16 code units:
  'A'       = 1
  🙂        = 2 (surrogate pair)
  'e'       = 1
  U+0301    = 1
  'B'       = 1
  total     = 6

Unicode code points: 5
User-perceived graphemes (thường): 4
~~~

Bởi vậy `charAt(1)` của chuỗi trên là **high surrogate**, không phải một emoji đầy đủ; `substring(1,2)` có thể tạo chuỗi chỉ chứa **một surrogate chưa ghép cặp**.

Sử dụng:
- `codePointAt(indexUtf16)` khi cần code point tại một **UTF-16 index**.
- `codePointCount(0, s.length())` để đếm code points.
- `offsetByCodePoints(0, n)` để đổi vị trí code point sang UTF-16 offset.
- `s.codePoints()` để duyệt các code points.
- `substring(fromUtf16,toUtf16)` khi đã xác định **offsets UTF-16** chính xác.

**Code points cũng chưa luôn là graphemes:** chuỗi `e + U+0301` thường hiển thị thành một ký tự có dấu nhưng là 2 code points. Một số emoji có multiple code points nối bằng ZWJ. Nếu cắt theo user-visible grapheme, cần một cơ chế Unicode grapheme boundary phù hợp với version/data của ứng dụng; đừng dùng `substring` hoặc `codePoints` rồi tuyên bố chúng luôn cắt đúng glyph.

### 4.2. Slicing theo code point mà không cắt đôi surrogate pair

~~~java
static String codePointSlice(String value, int from, int to) {
    Objects.requireNonNull(value, "value");
    int length = value.codePointCount(0, value.length());
    Objects.checkFromToIndex(from, to, length);
    int beginUtf16 = value.offsetByCodePoints(0, from);
    int endUtf16 = value.offsetByCodePoints(0, to);
    return value.substring(beginUtf16, endUtf16);
}
~~~

Đây là **đoạn minh họa** (đã được đưa nguyên lý vào chương trình hoàn chỉnh ở dưới), không phải hàm segment grapheme. Ví dụ `codePointSlice("A🙂B",1,2)` trả emoji đúng; index 1 là **code-point position**, không phải UTF-16 position.

Nếu cần cắt liên tục nhiều đoạn trong một string cực dài, gọi `codePointCount` và `offsetByCodePoints` lặp lại có thể tốn thêm duyệt chuỗi. Tối ưu sau khi profile: có thể precompute offsets cho cấu trúc ổn định hoặc xử lý một lần theo code point stream, thay vì tự viết arithmetic trên surrogate offsets.

### 4.3. Unicode normalization cho so sánh nội dung

~~~java
String composed = "\u00E9";     // é: one code point
String decomposed = "e\u0301";  // e + combining acute

composed.equals(decomposed);    // false

Normalizer.normalize(composed, Normalizer.Form.NFC)
    .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)); // true
~~~

Đây là mã minh họa, cần `java.text.Normalizer`. `String.equals` so code units, không tự canonical normalize. Tùy ngữ cảnh, normalized form (ví dụ **NFC**) hỗ trợ so sánh tên/tag có dấu. Nhưng normalization **không thay thế** locale-aware collation, Unicode confusable detection hoặc luật bảo mật identifier. Với mật khẩu/token đã có đặc tả bytes, tự normalize có thể làm sai giao thức.

## 5. Khoảng chỉ số: một quy ước, nhiều API

### 5.1. Half-open [from,to)

Trong Java, các API như `substring(begin,end)`, `Arrays.copyOfRange(a,from,to)` và `List.subList(from,to)` thường dùng **start inclusive, end exclusive**. Đối với mảng/string dài `n`:

~~~text
0 <= from <= to <= n

[0,n)      => toàn bộ n phần tử
[0,0)      => empty range ở đầu
[n,n)      => empty range ở cuối
[i,i)      => empty range giữa chuỗi/mảng
[n-1,n)    => đúng phần tử cuối
[n,n+1)    => vượt bounds
[-1,0)     => chỉ số âm
[2,1)      => range đảo ngược
~~~

**Index của một phần tử khác endpoint của một range.** `charAt(n)` hoặc `a[n]` không hợp lệ, nhưng `substring(n,n)` hay `Arrays.copyOfRange(a,n,n)` có thể hợp lệ. Điều này là nguồn gây lỗi off-by-one phổ biến.

### 5.2. Kiểm biên bằng Objects hiện hành

Java 11 có sẵn:

~~~java
Objects.checkIndex(index, length);
Objects.checkFromToIndex(fromInclusive, toExclusive, length);
Objects.checkFromIndexSize(offset, count, length);
~~~

- `checkIndex` hợp lệ khi `0 <= index < length`.
- `checkFromToIndex` hợp lệ khi `0 <= from <= to <= length`.
- `checkFromIndexSize` hợp lệ khi `offset >= 0`, `count >= 0` và toán học `offset + count <= length`.
- Các hàm trả lại index/from value khi hợp lệ, ném `IndexOutOfBoundsException` khi không hợp lệ.
- **checkFromIndexSize kiểm tránh integer overflow**; không tự viết `if (offset + count > length)` khi `offset + count` có thể tràn `int` thành âm.

Ví dụ khi `offset = Integer.MAX_VALUE-3`, `count = 10`, `length=Integer.MAX_VALUE`, phép cộng int vượt giới hạn. `Objects.checkFromIndexSize` vẫn **từ chối** range này đúng nghĩa, trong khi kiểm bằng phép cộng int đơn giản có thể sai.

### 5.3. Range (offset,count) khác range [from,to)

API I/O hoặc buffer thường nhận `offset, length`; API `substring` nhận `from,to`. Trộn hai kiểu dẫn đến lỗi:

~~~java
// Sai nếu size là số phần tử:
array = Arrays.copyOfRange(source, offset, size);

// Đúng khi đã validate offset/count:
Objects.checkFromIndexSize(offset, size, source.length);
array = Arrays.copyOfRange(source, offset, offset + size);
~~~

Sau validation thì `offset + size <= source.length` nên phép cộng an toàn. Với dữ liệu không tin cậy, validate **trước** khi allocate mảng kết quả; không để attacker tự chọn offset/length quá lớn gây `OutOfMemoryError` hoặc bypass bounds check.

## 6. Arrays: copy chính xác, zero-padding và mutability

### 6.1. Arrays.copyOfRange có một bẫy

`Arrays.copyOfRange(original,from,to)` **cho phép `to > original.length`** trong nhiều overloads. Nó tạo mảng mới dài `to-from` và **đệm các phần tử thiếu**:

- `int[]`, `byte[]`, `long[]`: đệm **0**.
- `boolean[]`: đệm **false**.
- `char[]`: đệm **U+0000**.
- `Object[]`: đệm **null**.

Ví dụ:

~~~java
int[] source = {7, 8};
int[] padded = Arrays.copyOfRange(source, 1, 4);
// padded = [8, 0, 0]
~~~

Nếu parser coi thiếu 2 elements là **malformed input**, không được dùng `copyOfRange` trần rồi chấp nhận 0 như dữ liệu thật. Wrapper nghiêm ngặt:

~~~java
static int[] copyExact(int[] source, int from, int to) {
    Objects.requireNonNull(source, "source");
    Objects.checkFromToIndex(from, to, source.length);
    return Arrays.copyOfRange(source, from, to);
}
~~~

**`Arrays.copyOfRange(source,source.length,source.length)` hợp lệ** và trả mảng rỗng. Ngược lại, `from > source.length` lỗi; `from > to` lỗi. `Arrays.copyOf` cũng có thể đệm khi tăng newLength. Sự khác biệt giữa **slice đã kiểm bounds** và **copy-with-padding** phải có trong hợp đồng API.

### 6.2. System.arraycopy và các mảng đè nhau

~~~java
int[] values = {1, 2, 3, 4};
System.arraycopy(values, 0, values, 1, 3);
// values = [1, 1, 2, 3]
~~~

`System.arraycopy` xử lý được hai vùng source/destination **chồng nhau** theo semantics như thông qua bản sao tạm; không cần tự viết vòng for từ trái sang phải vốn có thể ghi đè dữ liệu chưa đọc.

Đầu vào phải có source/dest khác null, kiểu tương thích và indices/count hợp lệ. Với reference arrays, Java vẫn kiểm type compatibility và có thể ném `ArrayStoreException` khi copy vào component type không phù hợp; không cố nuốt lỗi rồi giữ mảng đích đã sửa một phần.

### 6.3. ==, equals, mismatch, clone

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

a == b;                 // false: khác object
Arrays.equals(a, b);    // true: bằng giá trị
Arrays.mismatch(a, b);  // -1: không có index khác nhau
~~~

`Arrays.mismatch` có từ Java 9, hiện vẫn dùng được; trả index đầu tiên khác, hoặc `-1` nếu cùng nội dung (với mảng cùng kiểu). `Arrays.compare` hữu ích khi cần lexicographical ordering, nhưng không dùng khi chỉ cần equality.

`a.clone()` hoặc `Arrays.copyOf(a,a.length)` tạo mảng mới; với **primitive array**, các giá trị được copy. Với **Object[]**, copy là **shallow**: references trong hai mảng vẫn trỏ tới các objects con. Với `int[][]`, `clone()` chỉ copy outer array; nested arrays vẫn chia sẻ. Muốn kiểm nested-array contents có thể dùng `Arrays.deepEquals` hoặc viết logic clone deep tùy contract.

### 6.4. Arrays.asList và List.of không giống nhau

~~~java
String[] backing = {"a", "b"};
List<String> view = Arrays.asList(backing);
view.set(0, "x");       // backing[0] trở thành "x"
view.add("c");          // UnsupportedOperationException

List<String> fixed = List.of("a", "b");
fixed.set(0, "x");      // UnsupportedOperationException
List.of((String)null);  // NullPointerException
~~~

Đây là **mã minh họa**, các dòng lỗi có chủ đích, không chạy liền trong production. `Arrays.asList` trả **fixed-size list backed by array**, có thể `set` nhưng không `add/remove`. `List.of` trả unmodifiable list và **không cho null**. `Arrays.asList(new int[]{1,2})` tạo list có **một phần tử là int[]**, không phải `List<Integer>` hai phần tử.

Nếu cần list có thể thêm/xóa, dùng `new ArrayList<>(Arrays.asList(...))` hoặc tạo collection phù hợp, không cố ép view fixed-size thành mutable bằng cast.

## 7. Giá trị rỗng trong parser, split và lines

### 7.1. split mặc định loại trailing empty fields

~~~java
"a,,".split(",");       // ["a"]
"a,,".split(",", -1);   // ["a", "", ""]
~~~

Vì `split(regex)` tương đương `split(regex,0)`, **trailing empty strings bị bỏ**. Với TSV/CSV-like dữ liệu nơi trường rỗng ở cuối là hợp lệ, dùng **negative limit** khi muốn giữ chúng. Tuy nhiên `String.split` **không phải CSV parser đầy đủ**: quoted commas, escaped quotes, multi-line quoted fields phải xử lý bằng parser có contract đúng.

`split` nhận **regular expression**, không phải delimiter literal trong mọi trường hợp. Ví dụ tách theo dấu chấm cần `split("\\.")` trong Java source; `split(".")` nghĩa là regex dấu chấm match gần như mọi ký tự.

### 7.2. String.lines() của Java 11

`String.lines()` trả `Stream<String>` của các lines, hiểu line terminators **LF (`\n`)**, **CR (`\r`)** và **CRLF (`\r\n`)**, loại bỏ terminator khỏi element.

~~~java
"".lines().count();          // 0
"a\n".lines().count();       // 1, không thêm dòng rỗng cuối
"\n".lines().count();        // 1, một dòng rỗng
"a\r\nb\r".lines().count();  // 2
~~~

`lines()` có thể xử lý lazy, phù hợp chia line khi không cần materialize một mảng lớn. Nhưng nó **không** giữ nguyên dấu terminator hoặc trailing empty-line artifact; nếu cần bảo toàn bytes/line-ending chính xác, giữ raw string/bytes và định nghĩa parser khác.

### 7.3. Các loại empty nên xuất hiện trong test matrix

| Đầu vào | Phép kiểm |
| --- | --- |
| `null` | Fail-fast hay explicit fallback đúng contract? |
| `""` | Empty string không bị nhầm với absent? |
| `" "`, `"\t"`, `"\n"` | Blank nhưng non-empty? |
| `"\u2003"` | Java whitespace, strip được? |
| `"\u00A0"` | NBSP không được coi như Java whitespace? |
| `"a,,"` | Có giữ trailing empty fields? |
| `"\n"` | Một empty line? |
| Mảng 0 phần tử | `[0,0)` hợp lệ, `a[0]` lỗi? |
| Mảng 1 phần tử | Phần tử cuối và end-exclusive đúng? |
| Range `[n,n)` | Empty-at-end hợp lệ? |
| Range `[n,n+1)` | Báo lỗi, không âm thầm pad? |
| Cộng offset/count rất lớn | Tránh integer overflow? |
| Emoji, combining marks, tiếng Việt | Có cắt đôi surrogate, mất normalization? |

## 8. Chương trình Java 11 độc lập: kiểm thử 12 nhóm

File `StringsArraysRangesLab.java` kiểm **null/blank**, Unicode, normalization, String ranges, `Objects` checks, array copy/overlap, list mutability, split/lines, và các phép kiểm ngẫu nhiên **deterministic seeded**. Không dùng JUnit hoặc thư viện ngoài để ai cũng chạy được với JDK 11. `check(...)` ném `AssertionError` ngay cả khi không bật `-ea`.

Các assertions về exception dùng `expect(type, Runnable, caseName)`: nếu **không có exception** hoặc **sai loại**, test fail ngay. Với các phép random, chỉ số được chọn trong khoảng hợp lệ; kết quả được so với một cách xây dựng độc lập, giúp phát hiện lỗi index không lặp lại cùng thuật toán.

### 8.1. File đầy đủ: StringsArraysRangesLab.java

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class StringsArraysRangesLab {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void expect(Class<? extends Throwable> type,
                               Runnable operation, String scenario) {
        try {
            operation.run();
        } catch (Throwable cause) {
            if (type.isInstance(cause)) return;
            throw new AssertionError(scenario + ": expected " + type.getName()
                    + ", got " + cause.getClass().getName(), cause);
        }
        throw new AssertionError(scenario + ": expected " + type.getName());
    }

    private static int[] copyExact(int[] values, int from, int to) {
        Objects.requireNonNull(values, "values");
        Objects.checkFromToIndex(from, to, values.length);
        return Arrays.copyOfRange(values, from, to);
    }

    private static byte[] copyByOffset(byte[] values, int offset, int count) {
        Objects.requireNonNull(values, "values");
        Objects.checkFromIndexSize(offset, count, values.length);
        return Arrays.copyOfRange(values, offset, offset + count);
    }

    private static String codePointSlice(String value, int from, int to) {
        Objects.requireNonNull(value, "value");
        int length = value.codePointCount(0, value.length());
        Objects.checkFromToIndex(from, to, length);
        int startUtf16 = value.offsetByCodePoints(0, from);
        int endUtf16 = value.offsetByCodePoints(0, to);
        return value.substring(startUtf16, endUtf16);
    }

    private static void testNullAndEmpty() {
        String absent = null;
        String empty = "";
        String blank = " \t\n";
        String literal = "null";
        check(absent == null && empty != null && empty.isEmpty(), "null vs empty");
        check(!literal.isEmpty() && !literal.isBlank(), "literal null string");
        check(blank.isBlank() && !blank.isEmpty(), "blank vs empty");
        check(Objects.equals(absent, null) && !Objects.equals(absent, empty),
                "null-safe equality");
        check("fallback".equals(Objects.requireNonNullElse(absent, "fallback")),
                "explicit fallback");
        expect(NullPointerException.class, () -> Objects.requireNonNull(absent),
                "fail-fast null");
        expect(NullPointerException.class, () -> absent.length(), "null access");
        check(new int[0].length == 0 && new String[0].length == 0,
                "zero-length arrays");
        check(!Arrays.equals((int[]) null, new int[0]),
                "null array differs from empty");
        System.out.println("PASS null versus empty and blank contracts");
    }

    private static void testWhitespace() {
        String emSpace = "\u2003";
        String nbSpace = "\u00A0";
        check(emSpace.isBlank() && emSpace.strip().isEmpty(),
                "EM SPACE is Java whitespace");
        check(!nbSpace.isBlank() && nbSpace.strip().equals(nbSpace),
                "no-break space is not Java whitespace");
        check(emSpace.trim().equals(emSpace),
                "trim removes only code units <= U+0020");
        check("\u2003Hi\u2003".strip().equals("Hi"), "Unicode strip");
        check("  Hi  ".stripLeading().equals("Hi  "), "stripLeading");
        check("  Hi  ".stripTrailing().equals("  Hi"), "stripTrailing");
        check(" \t\n".isBlank() && "".isBlank(), "Java 11 isBlank");
        System.out.println("PASS Unicode whitespace and strip boundaries");
    }

    private static void testUnicode() {
        String value = "A\uD83D\uDE42e\u0301B";
        check(value.length() == 6, "UTF-16 code units");
        check(value.codePointCount(0, value.length()) == 5, "code point count");
        check(Character.isHighSurrogate(value.charAt(1)), "high surrogate");
        check(Character.isLowSurrogate(value.charAt(2)), "low surrogate");
        check(value.codePointAt(1) == 0x1F642, "supplementary code point");
        check(value.substring(1, 2).length() == 1,
                "UTF-16 substring may split surrogate pair");
        check(codePointSlice(value, 1, 2).equals("\uD83D\uDE42"),
                "code-point safe emoji slice");
        check(codePointSlice(value, 2, 4).equals("e\u0301"),
                "base plus combining mark");
        check(codePointSlice(value, 0, 0).isEmpty(), "empty code-point slice");
        check(codePointSlice(value, 5, 5).isEmpty(), "end code-point slice");
        expect(IndexOutOfBoundsException.class,
                () -> codePointSlice(value, 0, 6), "invalid code point range");
        System.out.println("PASS UTF-16 code units versus code points");
    }

    private static void testNormalization() {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        check(!composed.equals(decomposed),
                "canonically equivalent strings can differ");
        check(Normalizer.normalize(composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)),
                "NFC normalization");
        check(composed.codePointCount(0, composed.length()) == 1
                && decomposed.codePointCount(0, decomposed.length()) == 2,
                "grapheme not always code-point count");
        System.out.println("PASS canonical Unicode normalization");
    }

    private static void testStringRanges() {
        String value = "abc";
        check(value.charAt(0) == 'a' && value.charAt(2) == 'c',
                "valid element indices");
        check(value.substring(0, 3).equals("abc"), "full half-open range");
        check(value.substring(3, 3).isEmpty(), "empty end range");
        check(value.substring(1, 1).isEmpty(), "empty middle range");
        expect(StringIndexOutOfBoundsException.class, () -> value.charAt(3),
                "element index equals length");
        expect(StringIndexOutOfBoundsException.class,
                () -> value.substring(2, 1), "reversed half-open range");
        expect(StringIndexOutOfBoundsException.class,
                () -> value.substring(0, 4), "end exceeds string length");
        System.out.println("PASS half-open String index boundaries");
    }

    private static void testObjectsChecks() {
        check(Objects.checkIndex(2, 3) == 2, "valid element index");
        check(Objects.checkFromToIndex(0, 0, 0) == 0, "empty zero range");
        check(Objects.checkFromToIndex(0, 3, 3) == 0, "full range");
        check(Objects.checkFromIndexSize(2, 1, 3) == 2,
                "valid offset and size");
        check(Objects.checkFromIndexSize(3, 0, 3) == 3,
                "empty slice at end");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkIndex(3, 3), "index equals bound");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkIndex(-1, 3), "negative index");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkFromToIndex(3, 2, 4), "reversed range");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkFromIndexSize(3, 1, 3), "past end");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkFromIndexSize(
                        Integer.MAX_VALUE - 3, 10, Integer.MAX_VALUE),
                "sum overflow avoided");
        expect(IndexOutOfBoundsException.class,
                () -> Objects.checkFromIndexSize(0, -1, 3), "negative size");
        System.out.println("PASS Objects range checks and overflow safety");
    }

    private static void testArrayRanges() {
        int[] original = {7, 8};
        check(Arrays.equals(copyExact(original, 0, 2), original),
                "exact full array range");
        check(copyExact(original, 2, 2).length == 0, "empty array end slice");
        check(Arrays.equals(copyExact(original, 1, 2), new int[]{8}),
                "single element slice");
        expect(IndexOutOfBoundsException.class,
                () -> copyExact(original, 1, 3),
                "strict caller range rejects overrun");
        check(Arrays.equals(Arrays.copyOfRange(original, 1, 4),
                new int[]{8, 0, 0}), "JDK copyOfRange pads with zeros");
        check(Arrays.equals(copyByOffset(new byte[]{3, 4, 5}, 1, 2),
                new byte[]{4, 5}), "validated offset and length");
        expect(IndexOutOfBoundsException.class,
                () -> copyByOffset(new byte[]{1, 2}, 2, 1),
                "offset plus size out of bounds");
        int[] overlap = {1, 2, 3, 4};
        System.arraycopy(overlap, 0, overlap, 1, 3);
        check(Arrays.equals(overlap, new int[]{1, 1, 2, 3}),
                "System.arraycopy handles overlap");
        int[] copy = original.clone();
        copy[0] = 99;
        check(original[0] == 7, "clone makes independent primitive array");
        check(Arrays.mismatch(new int[]{1, 2}, new int[]{1, 3}) == 1,
                "mismatch first differing index");
        check(Arrays.mismatch(new int[]{1, 2}, new int[]{1, 2}) == -1,
                "mismatch returns -1 for equal arrays");
        System.out.println("PASS array slices, padding, overlap, and mismatch");
    }

    private static void testArrayListViews() {
        String[] backing = {"a", "b"};
        List<String> view = Arrays.asList(backing);
        view.set(0, "x");
        check(backing[0].equals("x"), "Arrays.asList writes through");
        expect(UnsupportedOperationException.class, () -> view.add("c"),
                "Arrays.asList has fixed size");
        List<String> immutable = List.of("a", "b");
        expect(UnsupportedOperationException.class,
                () -> immutable.set(0, "x"), "List.of unmodifiable");
        expect(NullPointerException.class, () -> List.of((String) null),
                "List.of rejects null");
        check(Arrays.asList(new int[]{1, 2}).size() == 1,
                "primitive array is one List element");
        List<String> growable = new ArrayList<>(view);
        growable.add("c");
        check(growable.size() == 3 && view.size() == 2,
                "copy for resizable list");
        System.out.println("PASS fixed-size, unmodifiable, and resizable lists");
    }

    private static void testSplitAndLines() {
        check(Arrays.equals("a,,".split(","), new String[]{"a"}),
                "default split drops trailing empty fields");
        check(Arrays.equals("a,,".split(",", -1),
                new String[]{"a", "", ""}), "negative limit retains empties");
        check("".lines().count() == 0, "empty string has zero lines");
        check("a\n".lines().count() == 1, "terminator adds no extra line");
        check("\n".lines().count() == 1, "one empty terminated line");
        check("a\r\nb\r".lines().count() == 2,
                "CRLF and CR terminators");
        check("ab".repeat(3).equals("ababab"), "Java 11 repeat");
        System.out.println("PASS split, lines, and repeat edge cases");
    }

    private static void testRandomArraySlices() {
        Random random = new Random(20261107L);
        for (int iteration = 0; iteration < 10_000; iteration++) {
            int length = random.nextInt(33);
            int[] source = new int[length];
            for (int i = 0; i < length; i++) source[i] = random.nextInt();
            int from = random.nextInt(length + 1);
            int to = from + random.nextInt(length - from + 1);
            int[] actual = copyExact(source, from, to);
            int[] expected = new int[to - from];
            System.arraycopy(source, from, expected, 0, expected.length);
            check(Arrays.equals(actual, expected),
                    "random array slice iteration " + iteration);
            check(source.length == length, "input not resized");
        }
        System.out.println("PASS 10000 seeded array range cases");
    }

    private static void testRandomUnicodeSlices() {
        int[] alphabet = {'A', '\u1EAF', 0x1F642, 'e', 0x0301, 0x2003, '\n'};
        Random random = new Random(3452026L);
        for (int iteration = 0; iteration < 5_000; iteration++) {
            int count = random.nextInt(19);
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < count; i++) {
                builder.appendCodePoint(alphabet[random.nextInt(alphabet.length)]);
            }
            String value = builder.toString();
            int from = random.nextInt(count + 1);
            int to = from + random.nextInt(count - from + 1);
            int[] codePoints = value.codePoints().toArray();
            int[] expected = Arrays.copyOfRange(codePoints, from, to);
            String expectedString = new String(expected, 0, expected.length);
            check(codePointSlice(value, from, to).equals(expectedString),
                    "random Unicode slice iteration " + iteration);
        }
        System.out.println("PASS 5000 seeded Unicode range cases");
    }

    private static void testBuilderAndUtf8() {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < 1000; i++) builder.append('x');
        check(builder.length() == 1000, "builder length");
        check(builder.toString().equals("x".repeat(1000)),
                "builder and repeat agree");
        String text = "\u00E9\uD83D\uDE42";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        check(bytes.length == 6 && text.length() == 3,
                "UTF-8 byte count differs from UTF-16 length");
        check(new String(bytes, StandardCharsets.UTF_8).equals(text),
                "explicit UTF-8 roundtrip");
        System.out.println("PASS StringBuilder and UTF-8 roundtrip");
    }

    public static void main(String[] args) {
        testNullAndEmpty();
        testWhitespace();
        testUnicode();
        testNormalization();
        testStringRanges();
        testObjectsChecks();
        testArrayRanges();
        testArrayListViews();
        testSplitAndLines();
        testRandomArraySlices();
        testRandomUnicodeSlices();
        testBuilderAndUtf8();
        System.out.println("ALL STRING ARRAY RANGE TESTS PASSED");
    }
}
~~~


### 8.2. Biên dịch và chạy

Với **JDK 11 trở lên**, lưu code trong file tên đúng `StringsArraysRangesLab.java`:

~~~bash
javac --release 11 -encoding UTF-8 StringsArraysRangesLab.java
java StringsArraysRangesLab
~~~

**Stdout chính xác khi toàn bộ assertions PASS:**

~~~text
PASS null versus empty and blank contracts
PASS Unicode whitespace and strip boundaries
PASS UTF-16 code units versus code points
PASS canonical Unicode normalization
PASS half-open String index boundaries
PASS Objects range checks and overflow safety
PASS array slices, padding, overlap, and mismatch
PASS fixed-size, unmodifiable, and resizable lists
PASS split, lines, and repeat edge cases
PASS 10000 seeded array range cases
PASS 5000 seeded Unicode range cases
PASS StringBuilder and UTF-8 roundtrip
ALL STRING ARRAY RANGE TESTS PASSED
~~~

**Vì sao không dùng một kết quả ngẫu nhiên trên từng máy?** Hai phép test sinh dữ liệu dùng `new Random(20261107L)` và `new Random(3452026L)`, cùng seed nên có thể tái lập cùng dãy dữ liệu khi debug. Tuy nhiên **seed cố định không chứng minh mọi input đều đúng**. Chạy thêm seeds khác, input do fuzzer/property-based framework sinh và corpus lỗi production đã redacted khi áp vào một thư viện thật.

### 8.3. Mỗi nhóm kiểm thử xác minh điều gì?

1. **Null/empty/blank:** phân biệt NPE với string rỗng, blank; `Objects.equals` và `requireNonNullElse` giữ nghĩa null được xác định rõ.
2. **Unicode whitespace:** kiểm `EM SPACE U+2003` được `isBlank/strip` nhận ra, `NBSP U+00A0` không được coi là Java whitespace; phân biệt `trim`.
3. **UTF-16:** sử dụng emoji U+1F642 để chắc chắn 2 code units, kiểm high/low surrogate, slicing theo code point không cắt đôi emoji.
4. **Normalization:** `é` precomposed và `e + combining acute` không bằng nhau dưới `String.equals`, nhưng trở thành tương đương sau NFC.
5. **String ranges:** `[0,n)`, `[n,n)`, `[i,i)` hợp lệ; `charAt(n)`, `substring(2,1)`, `substring(0,n+1)` ném exception.
6. **Objects bounds:** xác nhận boundaries 0, n, negative, reversed, invalid offset+length, và trường hợp **integer overflow**.
7. **Arrays:** strict wrapper từ chối overrun; `copyOfRange` đơn lẻ có zero-padding; `System.arraycopy` xử lý overlap; clone array không cùng reference; `Arrays.mismatch` xác định index đầu khác.
8. **Array-backed list:** `Arrays.asList` có thể `set` và ghi ngược vào mảng nhưng không thể `add`; `List.of` bất biến và từ chối null; primitive array là một phần tử của List.
9. **split/lines:** `split(",", -1)` giữ trailing blanks; `lines()` không tự thêm empty line cuối; `repeat` Java 11.
10. **10.000 random array slices:** so `copyExact` với kết quả từ `System.arraycopy` trên dữ liệu kích thước 0..32 và các range hợp lệ.
11. **5.000 random Unicode slices:** xây Unicode string từ code points (bao gồm dấu tiếng Việt, emoji, combining mark), so với `new String(codePointsSubset,0,count)`.
12. **Builder/UTF-8:** `StringBuilder` xây chuỗi lặp; rõ ràng 2 ký tự Unicode `é🙂` có **3 UTF-16 code units nhưng 6 UTF-8 bytes** và roundtrip với `StandardCharsets.UTF_8`.

### 8.4. Kiểm thử invalid inputs phải là «first-class»

Một bài test input hợp lệ duy nhất sẽ không tìm được phần lớn lỗi. Với hàm `slice(source,from,to)`, test table tối thiểu:

| Trường hợp | Kỳ vọng |
| --- | --- |
| `source = null` | NPE với message hợp đồng. |
| `source.length = 0, [0,0)` | Trả mảng dài 0. |
| `source.length = 0, [0,1)` | IndexOutOfBoundsException. |
| `source.length = 1, [0,1)` | Giữ phần tử duy nhất. |
| `source.length = 1, [1,1)` | Trả mảng rỗng. |
| `[-1,0)` | Exception. |
| `[1,0)` | Exception. |
| `[0,n+1)` | Exception nếu contract strict. |
| `[n,n)` | Hợp lệ. |
| `offset=Integer.MAX_VALUE-3,count=10` | Exception trước khi cộng dẫn đến overflow. |
| Input array sau khi copy | **Không** bị thay đổi. |
| Range full `[0,n)` | Kết quả có nội dung bằng mảng gốc, nhưng **object mới** nếu gọi copy. |

Nếu contract của ứng dụng **chủ động muốn zero-pad** (ví dụ chuẩn bị fixed-size binary frame), test phải diễn đạt rõ sự khác biệt và không dùng strict wrapper. **Một API tốt không phải lúc nào cũng ném exception; điều quan trọng là nhất quán với hợp đồng.**

## 9. Tối ưu: đo trước, giữ correctness

### 9.1. Đừng tối ưu bằng cách bỏ range validation tùy tiện

Một phép `Objects.checkFromToIndex` có vẻ là vài dòng code thừa, nhưng nó bảo vệ API trước dữ liệu sai, tình huống `offset+count` overflow và hành vi pad ngoài ý muốn. Trong nhiều trường hợp JIT đã có thể inline/loại bỏ kiểm tra dư khi range được chứng minh hợp lệ; **không tự kết luận** rằng bỏ validation làm chương trình nhanh hơn nếu chưa benchmark đúng workload.

Hành vi exception cũng là một phần contract. Bỏ kiểm soát bounds có thể biến `IndexOutOfBoundsException` rõ ràng thành dữ liệu bị copy/pad mà không báo lỗi, khiến corruption xuất hiện xa nguồn gốc.

### 9.2. StringBuilder và allocation

`String` là immutable. Ghép chuỗi lặp liên tục bằng `result += part` trong một số đường code có thể tạo nhiều intermediate strings, nhưng compiler/JIT cũng có tối ưu riêng, nhất là với concatenation expressions. Đừng mặc định mọi `+` là chậm; đối với một biểu thức ngắn, `+` thường dễ đọc và có hiệu năng tốt.

Khi xây một chuỗi dài trong vòng lặp:

~~~java
StringBuilder builder = new StringBuilder();
for (String element : elements) {
    builder.append(element);
}
String result = builder.toString();
~~~

Đây là **đoạn minh họa**, giả định `elements` đã có; trong chương trình chạy thật ở trên, builder được kiểm với 1.000 ký tự và `String.repeat`. `StringBuilder` không thread-safe; không chia sẻ cùng instance mutable giữa nhiều threads trừ khi có đồng bộ hóa thích hợp.

Nếu biết kích thước gần đúng, có thể `new StringBuilder(estimatedCapacity)` để giảm resize, nhưng không tính capacity bằng phép cộng int không kiểm overflow. Với input từ user, giới hạn số phần tử/tổng độ dài để tránh memory DoS. `String.repeat(n)` có thể tốn bộ nhớ lớn; cũng cần giới hạn n khi không tin cậy.

### 9.3. UTF-8 bytes không phải String length

~~~java
String text = "\u00E9\uD83D\uDE42"; // é🙂
int utf16Units = text.length(); // 3
int byteCount = text.getBytes(StandardCharsets.UTF_8).length; // 6
~~~

Nếu protocol/file/network buffer quy định **byte length**, không dùng `String.length()` để allocate buffer, build Content-Length hoặc tính offset. Encode/decode với charset tường minh (`StandardCharsets.UTF_8`), phù hợp từ Java 11 tới hiện hành. Nếu đang xử lý binary data, ưu tiên `byte[]` hoặc `ByteBuffer` với byte offsets, không trộn byte indices và String UTF-16 indices.

### 9.4. Khi nào nên dùng streams?

`String.codePoints()` và `String.lines()` trả streams có lợi cho pipeline có tính biểu đạt. Nhưng nếu code chạy trong hot loop trên input ngắn, stream/lambda/boxing có thể có chi phí khác so với vòng lặp; Java JIT và escape analysis thay đổi theo JDK. Dùng **JMH** và profiling thật để so:

- Throughput hoặc latency với input đại diện cho production.
- Phân bố lengths: 0, 1, 16, 1KiB, 1MiB; nhiều emoji/combining marks.
- Garbage allocation rate, GC pressure, heap peak.
- Warm-up, forks, isolation, Blackhole, OS/JVM flags, số threads.
- Chạy với cùng JDK version/vendor và cùng GC khi so microbenchmark.

**Không** chạy `System.nanoTime()` quanh một lời gọi `substring()` rồi dùng một số ns duy nhất làm bằng chứng. JVM có JIT warm-up, dead-code elimination, constant folding, GC và scheduler noise. Bài này kiểm **tính đúng** bằng runnable tests; phần hiệu năng phải đo thêm với harness được thiết kế cho mục tiêu đó.

### 9.5. Đừng tạo hoặc copy mảng nếu không cần

Mỗi `Arrays.copyOfRange` cấp phát **mảng mới**. Khi throughput cần cao, đôi khi nên truyền tuple `(array,offset,length)` hoặc `ByteBuffer.slice()` thay vì copy. Tuy nhiên slice/view **chia sẻ bộ nhớ** với dữ liệu gốc, gây các vấn đề:
- Caller có thể chỉnh sửa backing array sau khi gửi.
- Thread khác có thể thấy dữ liệu thay đổi.
- Giữ view tham chiếu tới backing array lớn làm tăng memory retention.
- Index của slice phụ thuộc position/limit/offset semantics khác String.

Quyết định **copy vs view** bằng hợp đồng ownership/immutability và đo allocation rate. **Không** tránh copy rồi vô tình gây race hoặc lộ private data từ một vùng buffer được dùng lại.

### 9.6. JFR và Memory profiling

Khi nghi ngờ cải tiến String/array làm tăng GC:
- Xem JFR allocation events, GC statistics và profiler CPU flamegraphs.
- Quan sát p95/p99 latency của application, không chỉ thời gian mỗi phép copy.
- Theo dõi allocation rate, object size, số instances, retention và GC pauses.
- Tách cost của UTF-8 encode/decode, normalization, regex, arraycopy và data structure overhead.
- Thử dưới workload thực tế, không chỉ chuỗi ASCII nhỏ.
- Không suy từ một lần chạy rằng Unicode algorithms luôn chậm hơn regex, hoặc loop luôn nhanh hơn stream.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `s.isEmpty()` khi `s == null` | NPE | Fail-fast hoặc explicit nullable contract. |
| Dùng `isEmpty()` để từ chối toàn khoảng trắng | `"   "` không empty | `isBlank()` nếu Java whitespace là nghĩa mong muốn. |
| Tin `strip()` cắt NBSP | NBSP không là Java `isWhitespace` | Định nghĩa normalization policy riêng. |
| Dùng `trim()` để xử lý toàn bộ Unicode whitespace | `trim` chỉ cắt code units ≤ U+0020 | `strip` nếu đúng yêu cầu, thêm test Unicode. |
| Đồng nhất `null` với `""` ở mọi nơi | Mất tín hiệu absent vs provided-empty | Quy định hợp đồng và test cả hai. |
| Dùng `String.length()` làm số graphemes | Đếm UTF-16 units | Dùng code points hoặc grapheme boundary API thích hợp. |
| `substring` cắt giữa emoji | Cắt theo UTF-16 code unit | Đổi từ code-point index với `offsetByCodePoints`. |
| Coi code point = glyph | Combining marks/ZWJ sequences | Dùng grapheme cluster segmenter khi UI cần. |
| So `é` và `e + combining acute` bằng `equals` rồi kết luận luôn khác nghĩa | Canonical forms khác | Normalize NFC/NFD theo contract. |
| Lấy `a[a.length]` | Index hợp lệ chỉ `0..n-1` | `Objects.checkIndex`. |
| Từ chối `substring(n,n)` dù là empty range hợp lệ | Nhầm element index với exclusive endpoint | Kiểm `checkFromToIndex`. |
| Lấy `Arrays.copyOfRange(a,0,n+1)` như strict slice | API có thể pad | Strict wrapper check bounds trước. |
| Dùng `offset+count <= length` mà không kiểm overflow | Int có thể wrap | `Objects.checkFromIndexSize`. |
| Quên kiểm size âm | Range invalid | Validate before allocate/copy. |
| Tự copy overlap bằng for thuận | Ghi đè phần chưa đọc | `System.arraycopy`. |
| So `int[]` bằng `==` hoặc `Objects.equals` | So reference | `Arrays.equals` / `mismatch`. |
| Chỉ clone outer `int[][]` | Nested arrays vẫn shared | Deep copy phù hợp, kiểm ownership. |
| Dùng `Arrays.asList` rồi `add` | Fixed-size view | `new ArrayList<>(view)`. |
| Dùng `List.of` với null | `List.of` ném NPE | Không chứa null hoặc chọn cấu trúc có contract rõ. |
| `Arrays.asList(intArray)` mong `List<Integer>` | Primitive array là một element | Boxing có chủ đích. |
| `split(",")` mất cột rỗng cuối | Default limit 0 drop trailing empties | `split(",",-1)`; CSV thật cần parser riêng. |
| `String.lines()` làm mất line separator | Trả line content không gồm separator | Giữ original text khi cần roundtrip chính xác. |
| Dùng `String.length()` làm size UTF-8 bytes | Byte count khác UTF-16 length | `getBytes(UTF_8).length`. |
| Kết luận performance từ một lần `nanoTime()` | JIT/GC/noise/DCE | JMH và production profiling. |
| Bỏ qua empty arrays trong fuzz | Không tìm ra `[0,0)` boundary bugs | Random lengths gồm 0 và explicit edge tests. |
| Test random không có seed | Khó tái lập lỗi | Log/giữ seed, shrink failing case. |

## 11. Bài tập thực hành

**Bài 1 — Strict string slice:** Viết hàm `strictSubstring(s,from,to)` nhận non-null `String` và **UTF-16 offsets**, từ chối `from<0`, `to<from`, `to>length`. So test với `substring`, nhưng khi input chứa surrogate pair cần ghi rõ API **có thể cắt giữa code points**.

**Bài 2 — Unicode-safe masking:** Cho String có emoji supplementary và combining marks, thay các code points nằm trong đoạn `[from,to)` bằng dấu `*` mà không cắt surrogate. Viết test 0-length, 1 code point, end-of-string và invalid bounds. Nếu hiển thị cho người dùng, mở rộng yêu cầu sang grapheme-aware, vì code-point masking vẫn có thể tách base khỏi combining mark.

**Bài 3 — Strict byte-frame reader:** Đọc `byte[] bytes` với `offset,size`, yêu cầu `0 <= offset <= length` và `size <= length-offset`. Kiểm overflow với `Integer.MAX_VALUE`, size âm, buffer dài 0; so `System.arraycopy` với `Arrays.copyOfRange` sau validation.

**Bài 4 — Empty fields:** Tách `"id,,active,"` thành đúng 4 cột; so `split(",")` và `split(",",-1)`. Thêm ca có quoted comma để lý giải vì sao `String.split` không đủ cho CSV production.

**Bài 5 — Mutability:** Tạo `String[] a`, `List<String> view = Arrays.asList(a)`, chỉnh phần tử qua view và qua array. Sau đó copy `new ArrayList<>(view)`; kiểm chúng độc lập khi thay đổi size. Thử `List.of(null)` với `expect`.

**Bài 6 — Performance measurement:** So `StringBuilder` với concatenation trong vòng lặp ở nhiều lengths với **JMH**, warm-up/forks hợp lý và dữ liệu không bị constant folded; báo both time/op và allocation bytes/op, giải thích kết quả theo JDK.

**Bài 7 — Random properties:** Dùng seeded generator tạo 50.000 arrays có kích thước 0..128 và ranges hợp lệ. Bất biến:
- `copy.length == to - from`.
- Mỗi `copy[i] == source[from+i]`.
- Source không bị mutate.
- `copyExact(source,n,n)` trả empty.
- Invalid ranges luôn ném `IndexOutOfBoundsException`, không zero-pad.

## 12. Câu hỏi tự đánh giá

**1.** `null` và `""` khác nhau thế nào? — `null` không có object, `""` là một String có độ dài UTF-16 bằng 0.

**2.** `" ".isEmpty()` và `" ".isBlank()`? — `false` và `true`.

**3.** `"\u00A0".isBlank()` trong Java 11? — `false`; NBSP không được `Character.isWhitespace` coi là whitespace.

**4.** Tại sao `"A🙂B".length()` bằng 4? — Emoji supplementary chiếm 2 UTF-16 code units.

**5.** `String.codePointCount` có bằng số ký tự nhìn thấy không? — Không luôn; combining marks và ZWJ sequences có thể nhiều code points trong một grapheme.

**6.** `substring(3,3)` trên `"abc"` hợp lệ? — Có, empty range ở cuối.

**7.** `charAt(3)` trên `"abc"` hợp lệ? — Không, element index nằm trong `[0,3)`.

**8.** `Arrays.copyOfRange(new int[]{7,8},1,4)` trả gì? — `[8,0,0]`, tự pad zeros.

**9.** Cách tạo strict slice không pad? — `Objects.checkFromToIndex(from,to,a.length)` trước `Arrays.copyOfRange`.

**10.** Vì sao không tự dùng `offset+size` để kiểm bounds? — Cộng `int` có thể overflow. `Objects.checkFromIndexSize` an toàn và mô tả contract rõ.

**11.** `System.arraycopy` có xử lý overlap trong cùng array không? — Có.

**12.** `Arrays.equals(a,b)` và `a==b` khác gì? — So nội dung mảng so với so identity.

**13.** `Arrays.asList(new int[]{1,2}).size()` bằng mấy? — Bằng 1, phần tử duy nhất là int[].

**14.** `List.of(null)` có chấp nhận không? — Không, ném NPE.

**15.** `"a,,".split(",")` khác `split(",",-1)`? — Mặc định bỏ các trường rỗng cuối; -1 giữ cả 3.

**16.** `"a\n".lines().count()` là bao nhiêu? — 1, không thêm dòng empty cuối.

**17.** `é🙂` có `length()` và UTF-8 bytes thế nào? — 3 UTF-16 units và 6 UTF-8 bytes.

**18.** Vì sao cần seed khi random testing? — Để tái lập cùng case lỗi và debug dễ hơn; vẫn cần nhiều seeds/corpus.

**19.** Dùng `StringBuilder` có luôn nhanh hơn `+` không? — Không thể kết luận tuyệt đối; phải benchmark workload thực tế với JMH/GC allocation measurement.

**20.** Khi nào được trả về empty thay vì ném lỗi? — Khi **hợp đồng API nói rõ** empty là kết quả hợp lệ; không tự biến dữ liệu malformed thành empty.

## 13. Checklist trước khi merge code

- [ ] Xác định rõ nullable, non-null, blank và empty contracts.
- [ ] Dùng `isBlank/strip` theo đúng nghĩa `Character.isWhitespace`; kiểm NBSP nếu input có Unicode đặc biệt.
- [ ] Không dùng `String.length()` làm số grapheme hoặc byte length.
- [ ] Có ca emoji supplementary, combining marks và normalization nếu xử lý tên/chuỗi tiếng Việt.
- [ ] Dùng `[from,to)` nhất quán; cho phép `[n,n)` khi contract nói empty slice hợp lệ.
- [ ] Dùng `Objects.checkIndex/checkFromToIndex/checkFromIndexSize`, tránh int overflow.
- [ ] Biết `copyOfRange` có zero/null padding ngoài end; không âm thầm chấp nhận malformed input.
- [ ] Kiểm `System.arraycopy` overlap và array mutability/copy semantics.
- [ ] So nội dung mảng bằng `Arrays.equals`/`deepEquals` theo đúng dimension.
- [ ] Kiểm `Arrays.asList` fixed-size backed view, `List.of` unmodifiable/no null.
- [ ] Với fields rỗng cuối, dùng `split(regex,-1)` hoặc parser hợp lệ cho data format.
- [ ] Viết unit tests cho null, empty, one element, start/end, negative, reversed, out-of-bounds, overflow.
- [ ] Dùng seeded randomized/property tests có cách tái lập và so với oracle độc lập.
- [ ] Khi cần tối ưu, dùng JMH/JFR/GC profiler, không đánh đổi correctness lấy microbenchmark cảm tính.
- [ ] Test thực tế bằng `javac --release 11`, chạy đúng 12 nhóm PASS và all-tests PASS.
- [ ] Với sản phẩm baseline Java 11, chạy thêm suite trên **JDK 11 runtime** bên cạnh JDK mới.

## 14. Tài liệu chính thức, còn áp dụng

1. [Java SE 11 String API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html) — `length`, `isBlank`, `strip`, `lines`, `substring`, `repeat`, `codePoints` và `split`.
2. [Java SE 26 String API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html) — đối chiếu API hiện hành.
3. [Java SE 11 Character API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html) — `isWhitespace`, surrogate pair, code points.
4. [Java SE 11 Objects API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Objects.html) — `checkIndex`, `checkFromToIndex`, `checkFromIndexSize`, `requireNonNullElse`.
5. [Java SE 11 Arrays API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Arrays.html) — `copyOfRange` padding, `equals`, `mismatch` và `asList`.
6. [Java SE 11 System.arraycopy API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).
7. [Java SE 11 Normalizer API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/text/Normalizer.html) — NFC/NFD.
8. [Java SE 11 StandardCharsets API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html) — UTF-8 encoding.
9. [Java SE 11 List API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/List.html) — `List.of`.
10. [Java SE 11 Random API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Random.html) — deterministic seeded tests.
11. [OpenJDK JMH project](https://openjdk.org/projects/code-tools/jmh/) — phương pháp microbenchmark JVM hiện đại.
12. [Java SE 26 Arrays API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html) — đối chiếu behavior slicing và mismatch hiện hành.
