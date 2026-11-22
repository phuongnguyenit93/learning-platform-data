# Ma trận kiểm thử String: null, rỗng, trắng, một ký tự và chuỗi dài

## 1. Mục tiêu: kiểm thử các lớp đầu vào dễ gây lỗi

Với Java `String`, chỉ thử vài chuỗi “bình thường” là chưa đủ. Một hàm nhận chuỗi có thể hoạt động tốt với `"hello"` nhưng sai hoặc ném ngoại lệ khi nhận `null`, `""`, `" "`, một ký tự, ký tự Unicode ngoài BMP, hoặc một chuỗi rất dài. Bài này trình bày cách xây dựng **ma trận kiểm thử theo lớp tương đương và giá trị biên**, đọc đúng kết quả API Java và chọn trường hợp có giá trị thay vì thử ngẫu nhiên.

Các lớp đầu vào cốt lõi:

1. **`null`:** không có đối tượng `String` để gọi phương thức.
2. **Rỗng `""`:** đối tượng `String` tồn tại nhưng `length() == 0`.
3. **Chỉ gồm whitespace:** có ít nhất một ký tự, có thể gồm dấu cách, tab, LF hoặc ký tự Unicode khác; “blank” tùy vào quy tắc API.
4. **Một ký tự:** ranh giới nhỏ nhất của chuỗi không rỗng; cần phân biệt một `char` UTF-16 với một Unicode code point.
5. **Chuỗi dài:** kiểm tra tính đúng đắn, hiệu năng, cấp phát và các giả định về độ dài, nhưng không dùng dữ liệu quá lớn gây cạn bộ nhớ trong test thường ngày.

Việc phân lớp phải dựa trên **hợp đồng đầu vào của hàm đang kiểm thử**. Một chương trình có thể coi `null` là lỗi, một chương trình khác cho phép `null` như giá trị “chưa cung cấp”. Không có quy tắc chung buộc tất cả ứng dụng biến `null` thành `""`.

## 2. Ma trận đầu vào chuẩn

| Trường hợp | Ví dụ Java | `length()` | `isEmpty()` | `isBlank()` | Ý nghĩa |
| --- | --- | ---: | --- | --- | --- |
| Không có chuỗi | `null` | Không gọi được | Không gọi được | Không gọi được | Phải kiểm tra `null` trước |
| Chuỗi rỗng | `""` | 0 | `true` | `true` | Có đối tượng nhưng không có ký tự |
| Một dấu cách | `" "` | 1 | `false` | `true` | Chuỗi trắng nhưng không rỗng |
| Tab và LF | `"\t\n"` | 2 | `false` | `true` | Hai ký tự whitespace |
| Một chữ cái ASCII | `"Z"` | 1 | `false` | `false` | Một UTF-16 code unit và một code point |
| Một emoji `😀` | `"\uD83D\uDE00"` | 2 | `false` | `false` | Hai UTF-16 code units nhưng một code point |
| EM SPACE | `"\u2003"` | 1 | `false` | `true` | Unicode whitespace được `Character.isWhitespace` nhận diện |
| NBSP | `"\u00A0"` | 1 | `false` | `false` | Non-breaking space không được `isBlank()` tính là blank |
| Chuỗi dài | `"a".repeat(100_000)` | 100000 | `false` | `false` | Kiểm tra độ dài, thao tác và tài nguyên |

Bảng trên áp dụng cho **Java 17+** và quy tắc `String.isBlank()` của Java. Các ô ghi “không gọi được” có nghĩa gọi trực tiếp `s.length()`, `s.isEmpty()` hoặc `s.isBlank()` khi `s == null` sẽ gây `NullPointerException`; `null` không phải một biến thể của `String` có độ dài bằng không.

**Đừng đánh đồng** `null`, `""` và `" "`: chúng có ý nghĩa khác nhau ngay cả khi UI đôi khi hiển thị cả ba giống như không có chữ.

## 3. Phép phân loại an toàn khi giá trị có thể `null`

Kiểm tra `null` trước khi gọi bất kỳ instance method nào:

```java
static String state(String s) {
    if (s == null) return "NULL";
    if (s.isEmpty()) return "EMPTY";
    if (s.isBlank()) return "BLANK";
    return "TEXT";
}
```

Đây là **đoạn mã phương thức**, có thể đặt trong một class Java. Trật tự điều kiện rất quan trọng:

- Nếu `s == null`, trả trạng thái `NULL` và không gọi phương thức của đối tượng.
- Nếu `s.isEmpty()` là `true`, trả `EMPTY`.
- Nếu độ dài dương nhưng `s.isBlank()` là `true`, trả `BLANK`.
- Các giá trị còn lại là `TEXT`. Trạng thái `TEXT` ở đây chỉ nghĩa “không blank theo quy tắc `String.isBlank()`”, không nhất thiết là văn bản hợp lệ về mặt nghiệp vụ.

Ví dụ, một mã đơn hàng `"   "` có thể bị từ chối theo chính sách đầu vào; một mật khẩu chỉ chứa dấu cách có thể hợp lệ hoặc không, tùy sản phẩm. Không tự gọi `strip()` trước khi phân loại nếu nghiệp vụ coi khoảng trắng là dữ liệu cần giữ.

### Phân biệt các cách so sánh

- `s == null` là cách kiểm tra tham chiếu có `null` hay không.
- `"".equals(s)` là cách kiểm tra chuỗi rỗng an toàn khi `s` có thể null.
- `Objects.equals(a, b)` là so sánh nội dung an toàn với `null` ở hai phía.
- `a.equals(b)` có thể gây `NullPointerException` nếu `a == null`.
- `a == b` với hai tham chiếu `String` kiểm tra **cùng đối tượng**, không phải nội dung bằng nhau; không dùng nó để xác nhận kết quả xử lý chuỗi.

Nếu đặc tả cho phép `null` và `""` mang cùng một nghĩa, nên nói rõ điều đó trong API rồi chuẩn hóa có chủ đích. Không tự dùng `Objects.toString(value, "")` ở mọi nơi, vì thao tác ấy làm mất sự khác biệt giữa hai trạng thái.

## 4. Chọn đúng quy tắc whitespace trước khi kiểm thử

`isEmpty()` chỉ hỏi `length() == 0`; `isBlank()` nhận chuỗi rỗng hoặc toàn các code point thỏa `Character.isWhitespace`. `trim()` loại mã ký tự từ `U+0000` đến `U+0020` ở hai đầu, còn `strip()` loại Unicode whitespace ở hai đầu theo `Character.isWhitespace`. Vì vậy `"\u2003"` (EM SPACE) là blank và được strip nhưng không được trim; `"\u00A0"` (NBSP) không được `isBlank()` coi là blank và không bị `strip()` loại bỏ.

~~~java
String emWrapped = "\u2003Z\u2003";
System.out.println(emWrapped.trim().equals("Z"));  // false
System.out.println(emWrapped.strip().equals("Z")); // true
System.out.println("\u00A0".isBlank());            // false
~~~

Trong ma trận đầu vào, kiểm tra ít nhất SPACE, TAB, LF, EM SPACE và NBSP theo **quy tắc nghiệp vụ được công bố**; không tự coi tất cả ký tự trông giống khoảng trắng là tương đương. Khi cần phân biệt `lines()` và regex `\R` hay xử lý các kiểu xuống dòng, dùng các ca riêng cho CR/LF/CRLF và Unicode line separators.

## 5. Một ký tự và ranh giới UTF-16

Với chuỗi một code unit `"Z"`, `charAt(0)` hợp lệ, `charAt(1)` ném `StringIndexOutOfBoundsException`, và `substring(1)` hợp lệ nhưng trả `""`. Với chuỗi rỗng `""`, `charAt(0)` không hợp lệ trong khi `substring(0, 0)` trả rỗng. Hãy kiểm tra cả **phần tử cuối**, **ranh giới ngay sau phần tử cuối** và **khoảng rỗng**.

~~~java
String single = "Z";
System.out.println(single.substring(1).isEmpty()); // true
String emoji = "\uD83D\uDE00";
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
~~~

Một code point ngoài BMP có thể dùng hai UTF-16 code units, còn một chữ có dấu kết hợp có thể gồm nhiều code point. Chọn đơn vị đo rõ ràng (code units, code points, graphemes hoặc byte) trước khi viết giới hạn độ dài hay phép cắt; chỉ `length()` là chưa đủ cho mọi yêu cầu hiển thị.

## 6. Chuỗi dài: kiểm thử độ đúng, bộ nhớ và thời gian

Một ca dài có thể là:

```java
String longText = "a".repeat(100_000);

boolean correctLength = longText.length() == 100_000;
boolean prefix = longText.startsWith("aaa");
boolean suffix = longText.endsWith("aaa");
```

Ở đây, `100_000` là **kích thước thử nghiệm có kiểm soát**, không phải giới hạn tối đa của `String` hay giới hạn chung của JVM. Giới hạn thực tế còn phụ thuộc biểu diễn chuỗi, runtime, bộ nhớ, giới hạn đối tượng/mảng và tác vụ đang thực hiện. Một chuỗi cực lớn có thể gây `OutOfMemoryError` hoặc khiến thử nghiệm mất quá nhiều thời gian. Không nên tạo chuỗi hàng gigabyte trong bộ test chạy hàng ngày chỉ để nói rằng “có test chuỗi dài”.

Các câu hỏi có ích khi kiểm thử chuỗi dài:

1. Hàm có trả **kết quả chính xác** cho đầu vào lớn hơn bình thường, hoặc có cắt cụt/làm mất ký tự cuối?
2. Có giới hạn nghiệp vụ được công bố không (ví dụ số ký tự tối đa), và kết quả khi vượt giới hạn là gì?
3. Có lỗi chỉ số, tràn tính toán độ dài trung gian hoặc lỗi xử lý đầu/cuối không?
4. Có thuật toán lặp lại `+=` hoặc `substring`/`replace` làm sao chép nhiều lần dẫn đến chi phí quá lớn không?
5. Có vô tình ghi toàn bộ chuỗi nhạy cảm hoặc rất lớn vào log, phản hồi lỗi hay bộ nhớ cache không?

Với giới hạn nghiệp vụ `maxLength`, nên có các ca **`maxLength - 1`, `maxLength`, `maxLength + 1`** nếu phù hợp, cộng ca rỗng, một ký tự và số lượng Unicode code point/grapheme khi đó là đơn vị giới hạn. Đừng tự suy luận giới hạn theo byte nếu hợp đồng ghi “ký tự”: UTF-8 có thể cần nhiều byte cho cùng một số code point.

Với các thao tác nối nhiều phần tử, cân nhắc `StringBuilder`, `String.join` hoặc stream collector nếu đúng bài toán. Đo hiệu năng bằng benchmark phù hợp (ví dụ JMH) khi hiệu năng thực sự là tiêu chí; một phép đo `System.nanoTime()` đơn lẻ dễ sai lệch do JIT, GC và tối ưu runtime. Test chức năng không cần cố chứng minh thời gian tuyệt đối trên mọi máy.

## 7. Chương trình kiểm thử Java 17+ độc lập

Tạo file `StringBoundaryMatrix.java`:

```java
import java.util.Objects;

public class StringBoundaryMatrix {
    static String state(String s) {
        if (s == null) return "NULL";
        if (s.isEmpty()) return "EMPTY";
        if (s.isBlank()) return "BLANK";
        return "TEXT";
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        String[] names = {
            "null", "empty", "space", "tabsLF", "oneASCII",
            "emoji", "emSpace", "nbsp", "long"
        };
        String[] values = {
            null, "", " ", "\t\n", "Z",
            "\uD83D\uDE00", "\u2003", "\u00A0", "a".repeat(100_000)
        };

        System.out.printf("%-10s | %-5s | %6s | %8s%n",
                "Case", "State", "length", "codePts");
        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            String length = value == null ? "-" : "" + value.length();
            String codePoints = value == null ? "-"
                    : "" + value.codePointCount(0, value.length());
            System.out.printf("%-10s | %-5s | %6s | %8s%n",
                    names[i], state(value), length, codePoints);
        }

        require(!Objects.equals(null, ""), "null != empty");
        require("".isEmpty() && "".isBlank(), "empty is blank");
        require(!" ".isEmpty() && " ".isBlank(), "space is blank");
        require("\t\n".isBlank(), "tab and LF are blank");
        require(!"\u00A0".isBlank(), "NBSP is not isBlank whitespace");
        require("\u2003".isBlank(), "EM SPACE is blank");
        require("\u2003Z\u2003".strip().equals("Z"), "strip Unicode");
        require(!"\u2003Z\u2003".trim().equals("Z"), "trim differs");
        require("Z".charAt(0) == 'Z', "one ASCII char");
        require("\uD83D\uDE00".length() == 2, "emoji uses UTF-16 pair");
        require("\uD83D\uDE00".codePointCount(0, 2) == 1, "one code point");
        require(values[8].length() == 100_000, "long length");
        require(values[8].startsWith("aaa"), "long prefix");
        require(values[8].endsWith("aaa"), "long suffix");
        System.out.println("Checks: PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 StringBoundaryMatrix.java
java StringBoundaryMatrix
```

Stdout đã kiểm chứng:

```text
Case       | State | length |  codePts
null       | NULL  |      - |        -
empty      | EMPTY |      0 |        0
space      | BLANK |      1 |        1
tabsLF     | BLANK |      2 |        2
oneASCII   | TEXT  |      1 |        1
emoji      | TEXT  |      2 |        1
emSpace    | BLANK |      1 |        1
nbsp       | TEXT  |      1 |        1
long       | TEXT  | 100000 |   100000
Checks: PASS
```

Các dấu `-` ở trường `length`, `codePts` của ca `null` có nghĩa **không áp dụng**, không phải số âm hay độ dài bằng 0. Chương trình không in hết chuỗi 100.000 ký tự: nó chỉ in thông số, tránh làm nhiễu console và làm chậm test. Phép `require` chủ động ném `AssertionError` nếu bất kỳ điều kiện nào sai; không cần bật tùy chọn JVM `-ea` như với từ khóa `assert` thông thường.

Giải thích kết quả đáng chú ý:

- `empty`: `isEmpty()` và `isBlank()` đều đúng; phân loại ưu tiên `EMPTY` để không mất thông tin độ dài 0.
- `space` và `tabsLF`: có ký tự thật, được phân loại `BLANK`.
- `emoji`: độ dài theo UTF-16 là 2 nhưng chỉ có 1 code point.
- `emSpace` là blank, `nbsp` không blank, đúng theo `Character.isWhitespace`.
- `long` dài 100000 code units và code points vì chỉ lặp chữ ASCII `a`; dữ liệu Unicode ngoài BMP không nhất thiết có hai số bằng nhau.

## 8. Biến ma trận thành bộ kiểm thử có khả năng bắt lỗi

Một bảng kiểm thử tốt nên liên hệ từng ca với một **nguy cơ cụ thể**:

| Đầu vào | Lỗi hay bị lộ | Điều cần xác nhận |
| --- | --- | --- |
| `null` | `NullPointerException` ngoài ý muốn | Hợp đồng cho phép, từ chối hay chuẩn hóa `null` |
| `""` | `charAt(0)` / `substring` sai biên | Nhánh rỗng, kết quả mặc định và thông báo lỗi |
| `" "` / `"\t\n"` | Nhầm blank với empty | Phân loại, validate, chuẩn hóa có chủ đích |
| Unicode whitespace | Chỉ xử lý ASCII hoặc tin `trim` giống `strip` | Quy tắc `Character.isWhitespace`, NBSP, EM SPACE |
| Một ký tự `"Z"` | Giả định chuỗi có ít nhất hai ký tự | Chỉ số 0, chỉ số 1, cắt đầu/cuối |
| Emoji hoặc dấu kết hợp | Đồng nhất UTF-16 units với ký tự hiển thị | `codePointCount`, code point boundaries, grapheme nếu cần |
| Chuỗi dài | Cắt cụt, copy lặp, giới hạn sai đơn vị | Đầu/cuối, độ dài, tài nguyên và giới hạn đã công bố |

Cùng một input có thể kiểm tra nhiều phương thức, nhưng **kỳ vọng phải cụ thể**: “không ném ngoại lệ” chưa chứng minh hàm trả đúng. Với parser, thêm kiểm tra nội dung các trường; với validator, xác nhận mã lỗi; với formatter, kiểm tra chính xác ký tự whitespace và Unicode; với API web, thử cả field vắng mặt và field chứa chuỗi rỗng trong payload.

### Kiểm thử các cặp biên quan trọng

- **Có giá trị / không có giá trị:** `null` so với `""`.
- **Rỗng / trắng:** `""` so với `" "`.
- **Một / hai ký tự:** `"Z"` so với `"ZZ"` để bắt lỗi chỉ số và phép cắt chuỗi.
- **ASCII / Unicode:** `"Z"` so với `"😀"` hoặc ký tự có dấu kết hợp.
- **Whitespace thường / whitespace Unicode:** `" "`, `"\t"`, `"\u2003"`, `"\u00A0"`.
- **Sát giới hạn / vượt giới hạn:** `n-1`, `n`, `n+1` theo đơn vị mà hợp đồng công bố.

Khi một lỗi được tìm thấy, hãy giữ lại một ca **regression test** nhỏ nhất có thể tái hiện lỗi. Không cần tạo hàng nghìn biến thể dài giống nhau nếu chúng không khám phá thêm một nguy cơ độc lập.

## 9. Thiết kế hàm nhận String để dễ kiểm thử

Trước khi viết test, định nghĩa các chính sách:

1. `null` có được phép không? Nếu không, hàm ném loại ngoại lệ nào, ở ranh giới nào? Có dùng `Objects.requireNonNull` không?
2. `""` có hợp lệ hay là “bỏ trống”? Có giá trị mặc định nào không?
3. Khoảng trắng đầu/cuối có ý nghĩa không? Có nên `strip` hay giữ nguyên?
4. “Độ dài” đếm UTF-16 code units, Unicode code points, grapheme hay số byte sau khi mã hóa?
5. Có giới hạn đầu vào không, ví dụ `maxLength`? Nếu vượt giới hạn, trả lỗi gì và tránh cấp phát quá lớn ra sao?
6. Kết quả có phải bất biến theo locale/charset không? So sánh chữ thường/hoa hay encode/decode cần chọn quy tắc tường minh.

Ví dụ một chính sách “tên hiển thị không được chỉ chứa whitespace, giới hạn 100 code point” có thể kiểm tra `null`, blank, `strip()`, `codePointCount` theo thứ tự; nhưng nếu nghiệp vụ lại muốn giới hạn 100 **byte UTF-8**, phép kiểm tra phải đổi thành đếm byte đã encode. Không thể thay một chính sách bằng chính sách khác chỉ vì cùng dùng từ “độ dài”.

Với trường hợp xử lý dữ liệu nhạy cảm, tránh in toàn bộ input khi test thất bại; log nhãn case và độ dài là đủ trong nhiều tình huống. Với dữ liệu dài, đặt mức trần test để bộ kiểm thử chạy ổn định trong CI.

## 10. Lỗi thường gặp khi lập ma trận String

1. **Gọi `null.isEmpty()` hoặc `null.isBlank()`:** `null` không phải đối tượng String; phải kiểm tra null trước.
2. **Coi `""` và `" "` như nhau:** cái đầu có độ dài 0, cái sau có độ dài 1.
3. **Cho rằng `isBlank()` nhận diện mọi thứ trông giống khoảng trắng:** NBSP là ví dụ phản chứng.
4. **Dùng `trim()` và `strip()` thay thế nhau hoàn toàn:** chúng dùng tập ký tự khác nhau.
5. **Dùng `length()` để đếm emoji hoặc ký tự người dùng thấy:** `length()` đếm UTF-16 code units; `codePointCount` cũng chưa phải phép đếm grapheme tổng quát.
6. **Truy cập `charAt(0)` trước khi kiểm tra chuỗi rỗng:** gây `StringIndexOutOfBoundsException`.
7. **Dùng `==` để so nội dung `String`:** so tham chiếu, không phải bằng nhau về nội dung.
8. **Chỉ thử chuỗi dài rồi tuyên bố hiệu năng tốt:** phải đo trong điều kiện có kiểm soát, có giới hạn tài nguyên và workload đại diện.
9. **Chỉ thử số ký tự, quên số byte:** khi I/O hoặc giao thức giới hạn byte, cần kiểm tra độ dài sau encode theo charset đúng.
10. **Coi một ca “không lỗi” là test pass:** vẫn cần khẳng định output, hiệu ứng phụ, thứ tự và chính sách xử lý đầu vào.

## 11. Checklist khi bổ sung test cho hàm xử lý String

- Xác định hợp đồng cho `null`, rỗng, blank và whitespace đầu/cuối.
- Thêm ca một ký tự, hai ký tự và ca Unicode ngoài BMP nếu logic liên quan chỉ số/độ dài.
- Ghi rõ “độ dài” nghĩa là UTF-16, code point, grapheme hay byte; kiểm thử đúng đơn vị.
- Thêm chuỗi dài vừa đủ và các giá trị sát giới hạn được công bố.
- Khẳng định **kết quả mong đợi**, không chỉ “chạy được”; giữ test xác định và có thể chạy lặp lại.
- Khi phát hiện lỗi, thêm ca regression nhỏ nhất để ngăn lỗi tái diễn.

**Ghi nhớ:** ma trận **`null` → rỗng → blank → một ký tự → dài** là khung khởi đầu để kiểm thử `String`, không phải bộ ca cố định cho mọi nghiệp vụ. Giá trị của nó nằm ở việc phân biệt rõ các trạng thái và kiểm chứng những ranh giới mà mã Java rất dễ xử lý sai.