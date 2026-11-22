# `String` dùng chỉ số theo đơn vị `char` của UTF-16

## 1. Mục tiêu và ý chính

Trong Java, các chỉ số của `String` như tham số của `charAt`, `substring`, `indexOf` và `codePointAt` được tính theo **UTF-16 code unit** (đơn vị `char` 16 bit), không mặc nhiên theo Unicode code point hoặc ký tự mà người đọc nhìn thấy.

Ví dụ, chuỗi `"A🚀B"` có 3 Unicode code point, nhưng `length() == 4`, vì ký tự `🚀` cần hai code unit UTF-16. Do đó, vị trí của `B` trong chuỗi là **3**, không phải **2**.

Bài học giúp bạn đọc và thao tác đúng với chỉ số Java, tránh cắt đôi surrogate pair và chuyển đổi vị trí khi muốn xử lý theo code point.

## 2. Ba khái niệm cần phân biệt

- **UTF-16 code unit:** một đơn vị 16 bit. Kiểu `char` của Java chứa đúng một code unit, giá trị từ `0x0000` đến `0xFFFF`.
- **Unicode code point:** giá trị nguyên dùng để nhận diện một vị trí mã Unicode, ví dụ `U+0041` (`A`) và `U+1F680` (`🚀`). Một code point thuộc dải bổ sung `U+10000..U+10FFFF` được biểu diễn bằng **hai** code unit UTF-16 gọi là *surrogate pair*.
- **Grapheme cluster:** cụm ký tự người đọc thường xem như một ký tự hiển thị. Một cluster có thể chứa nhiều code point, ví dụ chữ cái + dấu kết hợp hoặc emoji ghép bằng dấu nối.

| Văn bản | Số code unit UTF-16 (`length`) | Số code point | Ý nghĩa |
| --- | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | Mỗi ký tự ASCII chiếm một `char`. |
| `"A🚀B"` | 4 | 3 | `🚀` cần hai `char`. |
| `"é"` (U+00E9) | 1 | 1 | Dấu có sẵn trong một code point. |
| `"e\u0301"` (U+0065 + U+0301) | 2 | 2 | Chữ `e` và dấu sắc kết hợp; có thể nhìn giống `é`. |

Java lưu chuỗi bất biến và cung cấp API thao tác dựa trên **các đơn vị UTF-16**. Chú ý: cách lưu vật lý nội bộ của JVM có thể được tối ưu (ví dụ Compact Strings), nhưng **hành vi chỉ số công khai vẫn theo UTF-16**.

## 3. Sơ đồ chỉ số: `"A🚀B"`

Mã Unicode của rocket là `U+1F680`, được mã hóa bằng cặp surrogate `\uD83D` và `\uDE80`:

| Chỉ số `char` (UTF-16) | Giá trị `charAt(index)` | Ý nghĩa |
| ---: | --- | --- |
| 0 | `U+0041` | `A` |
| 1 | `U+D83D` | *High surrogate* của `🚀` |
| 2 | `U+DE80` | *Low surrogate* của `🚀` |
| 3 | `U+0042` | `B` |

Ranh giới để cắt chuỗi theo các code point hoàn chỉnh là `0 | A | 1 | 🚀 | 3 | B | 4`. **Vị trí 2 nằm giữa surrogate pair** và không phải ranh giới an toàn để chia rocket thành hai chuỗi.

Từ ví dụ này:
- `text.length()` → `4`: số code unit UTF-16.
- `text.codePointCount(0, text.length())` → `3`: số code point.
- `text.charAt(1)` → một `char` có giá trị `U+D83D`; **không phải** toàn bộ rocket.
- `text.codePointAt(1)` → `U+1F680`, vì chỉ số 1 bắt đầu một surrogate pair hợp lệ.
- `text.codePointAt(2)` → `U+DE80`: bắt đầu ở low surrogate nên **không ghép ngược** với phần tử trước.
- `text.indexOf("B")` → `3`: chỉ số UTF-16 của `B`.
- `text.substring(1, 3)` → `"🚀"`: vùng `[1, 3)` lấy trọn hai code unit.

Nếu sử dụng `substring(1, 2)`, kết quả chỉ có high surrogate. Java vẫn cho phép tạo chuỗi chứa surrogate đơn lẻ, nhưng văn bản này không biểu diễn một Unicode scalar value hoàn chỉnh; cách hiển thị, mã hóa khi xuất ra ngoài có thể không như mong muốn.

## 4. Các API dùng chỉ số UTF-16

| API | Đối số hoặc kết quả theo đơn vị nào? | Ví dụ với `"A🚀B"` |
| --- | --- | --- |
| `length()` | Trả về **số `char`** UTF-16. | `4` |
| `charAt(index)` | `index` là vị trí `char` trong `[0, length())`. | `charAt(1) == '\uD83D'` |
| `substring(beginIndex, endIndex)` | Hai đầu mút là vị trí UTF-16, đầu cuối loại trừ. | `substring(1, 3)` là `🚀` |
| `subSequence(start, end)` | Hai đầu mút là vị trí UTF-16. | `subSequence(1, 3)` là `🚀` |
| `indexOf(String)` và `lastIndexOf(String)` | Trả về vị trí **`char`** của chuỗi khớp, hoặc `-1`. | `indexOf("B") == 3` |
| `indexOf(int codePoint)` | Đối số là code point nhưng **kết quả là chỉ số UTF-16**. | `indexOf(0x1F680) == 1` |
| `codePointAt(index)` | `index` là vị trí UTF-16; đọc code point bắt đầu tại đó khi có cặp hợp lệ. | `codePointAt(1) == 0x1F680` |
| `codePointBefore(index)` | `index` là ranh giới UTF-16; đọc code point ngay trước đó. | `codePointBefore(3) == 0x1F680` |
| `codePointCount(begin, end)` | Phạm vi `[begin, end)` được chỉ định **theo UTF-16**; kết quả là số code point. | `codePointCount(0, 4) == 3` |
| `offsetByCodePoints(index, offset)` | Nhận `index` UTF-16 và khoảng dịch **số code point**; trả về **chỉ số UTF-16** mới. | `offsetByCodePoints(0, 2) == 3` |

Một số API có overload nhận `fromIndex`, như `indexOf(ch, fromIndex)` hoặc `lastIndexOf(str, fromIndex)`. `fromIndex` cũng là chỉ số UTF-16. Các API thao tác vùng như `StringBuilder.delete(start, end)` và các vị trí được báo về từ `java.util.regex.Matcher.start()/end()` cũng thường dùng chỉ số UTF-16.

Không nên mặc định rằng một chỉ số bất kỳ là ranh giới code point. `offsetByCodePoints` dịch qua các code point tính từ vị trí bạn cung cấp; nếu vị trí đầu đã nằm *giữa* surrogate pair, việc dịch chuyển đó không tự sửa đoạn chuỗi đã bị tách đôi.

## 5. Chương trình Java 17+ minh họa

Lưu file `Utf16IndexDemo.java` với nội dung:

```java
import java.util.Arrays;

public class Utf16IndexDemo {
    public static void main(String[] args) {
        String text = "A🚀B";

        System.out.println("length = " + text.length());
        System.out.println("code points = "
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("charAt(%d) = U+%04X%n",
                    i, (int) text.charAt(i));
        }

        System.out.printf("codePointAt(1) = U+%X%n",
                text.codePointAt(1));
        System.out.printf("codePointAt(2) = U+%X%n",
                text.codePointAt(2));
        System.out.println("indexOf(B) = " + text.indexOf("B"));
        System.out.println("indexOf(rocket) = " + text.indexOf("🚀"));

        int begin = text.offsetByCodePoints(0, 1);
        int end = text.offsetByCodePoints(begin, 1);
        System.out.println("slice = " + text.substring(begin, end));
        System.out.println("slice range = " + begin + ".." + end);

        String brokenHalf = text.substring(1, 2);
        System.out.println("high surrogate only = "
                + Character.isHighSurrogate(brokenHalf.charAt(0)));
        System.out.println("codePoints array = "
                + Arrays.toString(text.codePoints().toArray()));
    }
}
```

Biên dịch và chạy trong môi trường hiển thị UTF-8:

```bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
```

Kết quả mong đợi:

```text
length = 4
code points = 3
charAt(0) = U+0041
charAt(1) = U+D83D
charAt(2) = U+DE80
charAt(3) = U+0042
codePointAt(1) = U+1F680
codePointAt(2) = U+DE80
indexOf(B) = 3
indexOf(rocket) = 1
slice = 🚀
slice range = 1..3
high surrogate only = true
codePoints array = [65, 128640, 66]
```

**Điều cần quan sát:** cặp `charAt(1)` và `charAt(2)` là hai nửa của một code point; `substring(1, 3)` hợp lệ vì chứa cả hai, còn `substring(1, 2)` cắt đôi cặp. `indexOf("🚀")` và `indexOf(0x1F680)` đều chỉ tới vị trí UTF-16 **1**, còn `indexOf("B")` trả **3**.

## 6. Cắt chuỗi theo code point mà không cắt đôi surrogate pair

Khi yêu cầu là “lấy `count` code point, bắt đầu từ code point thứ `from`”, **không** gọi trực tiếp `substring(from, from + count)`. Trước tiên cần đổi chỉ số tính theo code point thành chỉ số UTF-16.

Phương thức hỗ trợ sau là **một phần của lớp Java** (ví dụ đặt bên trong `Utf16IndexDemo`), chưa phải file chạy độc lập:

```java
static String sliceByCodePoints(String text, int from, int count) {
    java.util.Objects.requireNonNull(text, "text");

    int total = text.codePointCount(0, text.length());
    java.util.Objects.checkFromIndexSize(from, count, total);

    int beginUtf16 = text.offsetByCodePoints(0, from);
    int endUtf16 = text.offsetByCodePoints(beginUtf16, count);
    return text.substring(beginUtf16, endUtf16);
}
```

Ví dụ gọi bên trong `main`:

```java
String text = "A🚀B";
System.out.println(sliceByCodePoints(text, 1, 1)); // 🚀
System.out.println(sliceByCodePoints(text, 1, 2)); // 🚀B
System.out.println(sliceByCodePoints(text, 3, 0).isEmpty()); // true
```

Giải thích:
1. `codePointCount` tính tổng code point, dùng để xác nhận đoạn `[from, from + count)` nằm trong phạm vi hợp lệ.
2. `offsetByCodePoints(0, from)` tìm ranh giới UTF-16 sau `from` code point đầu tiên.
3. `offsetByCodePoints(beginUtf16, count)` tìm ranh giới sau `count` code point nữa.
4. `substring(beginUtf16, endUtf16)` cắt bằng **đúng loại chỉ số** mà API này yêu cầu.

Hàm giữ nguyên code point bổ sung khi chuỗi đầu vào có surrogate pair hợp lệ. Nếu đầu vào đã chứa surrogate đơn lẻ, Java có thể đếm surrogate đơn lẻ như một code point khi dùng các API này; hàm không phải bộ kiểm tra tính well-formed của văn bản Unicode.

## 7. Duyệt chuỗi: `char` hay code point?

**Duyệt theo UTF-16 code unit** khi xử lý các vị trí thấp cấp hoặc tương tác API đòi chỉ số `char`:

```java
String text = "A🚀B";
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // Một vòng lặp có thể nhận riêng high/low surrogate.
}
```

**Duyệt theo Unicode code point** khi cần xử lý các điểm mã nguyên vẹn:

```java
String text = "A🚀B";
text.codePoints().forEach(cp ->
        System.out.printf("U+%X%n", cp));
```

Kết quả đoạn thứ hai:

```text
U+41
U+1F680
U+42
```

`text.chars()` trả về `IntStream` của **các code unit UTF-16**, còn `text.codePoints()` trả về `IntStream` của **các code point** (kết hợp surrogate pair hợp lệ). Vì thế, `chars()` và `codePoints()` không thể hoán đổi cho nhau khi chuỗi chứa ký tự ngoài BMP.

Nếu cần duy trì **cả vị trí UTF-16 lẫn code point**, duyệt theo bước nhảy:

```java
String text = "A🚀B";
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    System.out.printf("UTF-16 index %d -> U+%X%n", i, cp);
    i += Character.charCount(cp);
}
```

Kết quả:

```text
UTF-16 index 0 -> U+41
UTF-16 index 1 -> U+1F680
UTF-16 index 3 -> U+42
```

`Character.charCount(cp)` trả về `2` khi code point nằm ngoài BMP, ngược lại là `1`. Cách duyệt này giữ chỉ số ở đầu mỗi code point nếu bắt đầu từ ranh giới hợp lệ.

## 8. “Một ký tự hiển thị” có thể vẫn là nhiều code point

Không nên thay mọi bài toán “ký tự” bằng cách đếm code point một cách máy móc. Ví dụ:

```java
String composed = "\u00E9"; // é: một code point
String decomposed = "e\u0301"; // e + dấu sắc kết hợp: hai code point

System.out.println(composed.length()); // 1
System.out.println(decomposed.length()); // 2
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
System.out.println(composed.equals(decomposed)); // false
```

Hai chuỗi có thể hiển thị giống nhau nhưng khác chuỗi code unit và code point. Nếu cần so sánh các dạng Unicode tương đương, có thể cân nhắc chuẩn hóa bằng `java.text.Normalizer`, ví dụ `Normalizer.normalize(text, Normalizer.Form.NFC)`. Chuẩn hóa không biến các API chỉ số thành API grapheme cluster.

Nếu nghiệp vụ cần di chuyển con trỏ hoặc giới hạn độ dài **theo ký tự người dùng nhìn thấy**, cần thuật toán phân đoạn grapheme cluster tuân theo quy tắc Unicode tương ứng. Không lấy `length()` hoặc `codePointCount()` làm câu trả lời mặc định cho mọi ngôn ngữ và emoji ghép.

## 9. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Giả định `length()` là số code point. | Đếm thừa với `🚀`, `😀` và nhiều ký tự ngoài BMP. | Dùng `codePointCount` nếu thật sự cần số code point. |
| Lấy `charAt(i)` để duyệt “từng ký tự Unicode”. | Surrogate pair bị chia thành hai lần đọc. | Dùng `codePointAt` cùng bước nhảy `Character.charCount` hoặc `codePoints()`. |
| Dùng chỉ số code point trực tiếp cho `substring`. | Cắt sai vị trí hoặc cắt đôi surrogate pair. | Đổi ranh giới bằng `offsetByCodePoints` rồi mới `substring`. |
| Nghĩ `indexOf` trả về vị trí code point. | Chỉ số bị lệch sau các ký tự bổ sung. | Xem kết quả là chỉ số UTF-16, tương thích với `substring` / `charAt`. |
| Gọi `codePointAt` tại low surrogate của cặp hợp lệ. | Chỉ nhận riêng giá trị low surrogate. | Trỏ tới high surrogate (đầu code point) hoặc duyệt từ đầu. |
| Giả định “1 code point = 1 ký tự hiển thị”. | Xử lý sai dấu kết hợp, emoji có bộ chọn biến thể/dấu nối. | Xác định bài toán theo code unit, code point hay grapheme cluster trước khi chọn API. |

Các lời gọi như `charAt(-1)`, `charAt(length())` và `substring` với chỉ số không hợp lệ sẽ ném ngoại lệ chỉ số (`IndexOutOfBoundsException` hoặc lớp con). Dù một chỉ số nằm trong giới hạn, nó **vẫn có thể nằm giữa hai surrogate**, nên kiểm tra giới hạn chưa đủ bảo đảm ranh giới Unicode hợp lý.

## 10. Bài tập tự kiểm tra

Cho đoạn mã:

```java
String s = "Hi😀!";
```

1. `s.length()` là bao nhiêu? **5**: `H` và `i` là 2 `char`, `😀` là 2 `char`, `!` là 1 `char`.
2. `s.codePointCount(0, s.length())` là bao nhiêu? **4**.
3. `s.indexOf("!")` trả về bao nhiêu? **4**, vì đây là chỉ số UTF-16.
4. `s.substring(2, 4)` trả về gì? **`"😀"`**, gồm đúng hai code unit của surrogate pair.
5. `s.substring(2, 3)` có lấy trọn emoji không? **Không**, chỉ lấy high surrogate.
6. `s.offsetByCodePoints(0, 3)` là bao nhiêu? **4**, ranh giới sau code point thứ ba.
7. Nếu muốn lấy code point thứ ba (chỉ số code point bằng `2`), nên làm gì? Dùng `int start = s.offsetByCodePoints(0, 2); int end = s.offsetByCodePoints(start, 1);` rồi `s.substring(start, end)`.

## Tài liệu tham khảo

- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
