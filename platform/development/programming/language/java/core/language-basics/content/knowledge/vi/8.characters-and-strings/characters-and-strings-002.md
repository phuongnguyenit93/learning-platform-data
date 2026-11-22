# Đơn vị mã UTF-16, code point và ký tự ngoài BMP trong Java

> **Java core — language-basics / Ký tự và chuỗi**  
> **Yêu cầu:** Java 17+ với JDK; không cần thư viện bên ngoài.  
> **Mục tiêu:** Phân biệt `char`, đơn vị mã UTF-16, Unicode code point và ký tự ngoài BMP; hiểu surrogate pair, cách `String` đánh chỉ số và dùng API code point để không cắt đôi ký tự.

## 1. Ba khái niệm dễ nhầm

| Khái niệm | Ý nghĩa trong Java | Ví dụ |
| --- | --- | --- |
| **Unicode code point** | Một giá trị số định danh vị trí trong không gian mã Unicode, ký hiệu `U+...` | `U+0041` (A), `U+1F600` (😀) |
| **UTF-16 code unit** | Một đơn vị mã **16 bit** dùng để biểu diễn dữ liệu trong `String` | `0x0041`, `0xD83D` |
| **`char`** | Kiểu nguyên thủy Java chứa **một code unit UTF-16**, không nhất thiết là một code point hoàn chỉnh | `char letter = 'A';` |

Không gian **Unicode code point** trải từ `U+0000` đến `U+10FFFF` và **bao gồm cả** vùng surrogate `U+D800`–`U+DFFF`. Tuy nhiên, các code point surrogate **không phải Unicode scalar value hợp lệ**, nên không thể đứng độc lập như một ký tự Unicode được mã hóa đúng chuẩn. Một code point ngoài BMP cần hai `char` trong UTF-16.

- **BMP** (*Basic Multilingual Plane*): dải `U+0000`–`U+FFFF`; những code point hợp lệ trong BMP dùng **một** code unit UTF-16.
- **Ngoài BMP** (*supplementary code points*): dải `U+10000`–`U+10FFFF`; trong UTF-16, mỗi code point được biểu diễn bằng **hai** code unit (*surrogate pair*).
- Vùng surrogate nằm trong BMP về giá trị số, nhưng không phải Unicode scalar value và không được dùng một mình để mã hóa ký tự trong UTF-16 hợp lệ.

Ví dụ chữ `A` (U+0041) cần 1 `char`; emoji 😀 (U+1F600) cần **2 `char`** trong một `String` Java.

## 2. Surrogate pair được ghép như thế nào?

Với code point ngoài BMP, UTF-16 dùng:

- **High surrogate**: code unit trong dải `0xD800`–`0xDBFF`.
- **Low surrogate**: code unit trong dải `0xDC00`–`0xDFFF`.
- Một cặp high rồi low liên tiếp mã hóa một code point ngoài BMP.

Ví dụ cụ thể:

~~~text
Unicode code point: U+1F600 (😀)
High surrogate:      D83D
Low surrogate:       DE00
UTF-16 code units:   [D83D][DE00]
~~~

Công thức nếu muốn tự tính từ code point `cp >= 0x10000`:

~~~text
v    = cp - 0x10000
high = 0xD800 + (v >> 10)
low  = 0xDC00 + (v & 0x3FF)
~~~

Kết hợp ngược hai surrogate:

~~~text
cp = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
~~~

**Không** coi riêng `0xD83D` hoặc `0xDE00` là emoji hoàn chỉnh. Chúng chỉ là hai code unit phải đứng thành cặp theo đúng thứ tự.

## 3. `String.length()` và `charAt()` đếm đơn vị UTF-16

Cho chuỗi ba code point: `A`, `U+1F600`, `B`. Trong UTF-16:

| UTF-16 index | Code unit | Thuộc code point |
| ---: | --- | --- |
| 0 | `0041` | `U+0041` (A) |
| 1 | `D83D` | Nửa đầu của `U+1F600` |
| 2 | `DE00` | Nửa sau của `U+1F600` |
| 3 | `0042` | `U+0042` (B) |

Vì thế `length()` là **4**, còn `codePointCount(0, length())` là **3**. `charAt(1)` trả **high surrogate**, `charAt(2)` trả **low surrogate**; `codePointAt(1)` ghép cặp thành code point `0x1F600`.

| Java API | Đơn vị xử lý | Cách dùng |
| --- | --- | --- |
| `s.length()` | Code unit UTF-16 | Độ dài lưu trữ theo UTF-16 |
| `s.charAt(index)` | **Một** `char` | Đọc một code unit |
| `s.codePointAt(index)` | Một code point bắt đầu tại UTF-16 index đó, nếu có cặp hợp lệ | Đọc code point ở ranh giới đúng |
| `s.codePointCount(0, s.length())` | Code point | Đếm các code point |
| `s.offsetByCodePoints(start, count)` | Từ UTF-16 offset, tiến theo code point | Tìm biên chỉ số để cắt chuỗi |
| `s.codePoints()` | `IntStream` các code point | Duyệt theo code point |
| `Character.toChars(cp)` | Mảng `char[]` dài 1 hoặc 2 | Mã hóa một code point hợp lệ thành UTF-16 |

Các chỉ số truyền cho `charAt`, `substring` và `codePointAt` vẫn là **UTF-16 offset**, không phải vị trí code point thuần. Gọi `codePointAt(2)` ở giữa cặp trên **không** tự quay lui ghép với high surrogate ở chỉ số 1; vì thế nên duyệt bằng `codePoints()` hoặc offset hợp lệ.

## 4. Ví dụ Java 17+ chạy được: UnicodeUnitsDemo.java

Tạo tệp **UnicodeUnitsDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;

public final class UnicodeUnitsDemo {
    public static void main(String[] args) {
        int emoji = 0x1F600;
        String face = new String(Character.toChars(emoji));
        String sample = "A" + face + "B";

        System.out.println("utf16Units=" + sample.length());
        System.out.println("codePoints="
                + sample.codePointCount(0, sample.length()));
        System.out.println("utf8Bytes="
                + sample.getBytes(StandardCharsets.UTF_8).length);

        System.out.printf("unit1=%04X%n", (int) sample.charAt(1));
        System.out.printf("unit2=%04X%n", (int) sample.charAt(2));
        System.out.printf("point1=U+%X%n", sample.codePointAt(1));
        System.out.println("supplementary="
                + Character.isSupplementaryCodePoint(emoji));
        System.out.println("unitCount=" + Character.charCount(emoji));

        int afterTwoPoints = sample.offsetByCodePoints(0, 2);
        System.out.println("afterTwoPoints=" + afterTwoPoints);
        System.out.println("faceSlice="
                + sample.substring(1, afterTwoPoints).equals(face));
        System.out.println("splitPair="
                + Character.isHighSurrogate(sample.substring(1, 2).charAt(0)));

        StringBuilder labels = new StringBuilder();
        sample.codePoints().forEach(cp -> {
            if (labels.length() > 0) {
                labels.append(",");
            }
            labels.append(String.format("U+%X", cp));
        });
        System.out.println("sequence=" + labels);

        String combining = "e\u0301";
        System.out.println("combiningUnits=" + combining.length());
        System.out.println("combiningPoints="
                + combining.codePointCount(0, combining.length()));
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file bằng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
~~~

**Expected output (chính xác):**

~~~text
utf16Units=4
codePoints=3
utf8Bytes=6
unit1=D83D
unit2=DE00
point1=U+1F600
supplementary=true
unitCount=2
afterTwoPoints=3
faceSlice=true
splitPair=true
sequence=U+41,U+1F600,U+42
combiningUnits=2
combiningPoints=2
~~~

**Cách đọc kết quả:**

1. Chuỗi `A + 😀 + B` gồm ba code point nhưng chiếm 4 code unit UTF-16. Khi mã hóa thành UTF-8, `A` và `B` mỗi ký tự 1 byte, emoji này 4 byte, tổng **6 byte**.
2. Hai `char` ở UTF-16 index 1 và 2 có mã `D83D` và `DE00`. API `codePointAt(1)` trả đúng `U+1F600`.
3. `offsetByCodePoints(0, 2)` bằng **3**, vì đi qua A (1 code unit) và emoji (2 code unit).
4. `substring(1, 3)` tạo một chuỗi emoji hoàn chỉnh. `substring(1, 2)` lại **cắt đôi cặp surrogate**, để lại một high surrogate đứng đơn độc.
5. `codePoints()` duyệt ba code point `U+41`, `U+1F600`, `U+42`. Chuỗi `"e\u0301"` có `e` và dấu sắc kết hợp: **2 code point**, dù người đọc có thể nhìn thành **một ký tự hiển thị**.

## 5. Duyệt và cắt chuỗi an toàn ở ranh giới code point

**Không giả định** `for (int i = 0; i < s.length(); i++)` đang duyệt từng code point: vòng lặp đó duyệt **từng code unit**.

Duyệt theo code point khi cần phân tích Unicode:

~~~java
String s = "A" + new String(Character.toChars(0x1F600)) + "B";
s.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
~~~

Khi cần cắt từ **code point thứ 1** (0-based) và lấy **một code point**, hãy tính ranh giới UTF-16:

~~~java
int start = s.offsetByCodePoints(0, 1); // 1
int end = s.offsetByCodePoints(start, 1); // 3
String onlyEmoji = s.substring(start, end);
~~~

Đừng cắt tùy ý theo độ dài 1 bằng `s.substring(start, start + 1)`: nếu phần tử là code point ngoài BMP, bạn chỉ lấy một nửa surrogate pair.

`Character.charCount(cp)` cho biết code point cần **1 hay 2 code unit**; `Character.toChars(cp)` tạo đúng các code unit tương ứng. API `String.codePointAt`/`codePoints` giúp làm việc ở mức code point, nhưng **không thay thế kiểm tra dữ liệu Unicode bị lỗi**: một `String` Java có thể chứa surrogate đơn lẻ, và các API đó có quy tắc riêng khi gặp cặp không hợp lệ.

## 6. Code point chưa chắc là một ký tự người dùng nhìn thấy

Ba số đo phải được phân biệt:

| Đơn vị | Ví dụ `A😀B` | Ý nghĩa |
| --- | ---: | --- |
| UTF-16 code unit | 4 | Kết quả `String.length()` |
| Unicode code point | 3 | Kết quả `codePointCount` |
| UTF-8 byte | 6 | Kết quả `getBytes(StandardCharsets.UTF_8).length` |

Nhưng **ký tự hiển thị** (*grapheme cluster*) có thể gồm **nhiều code point**: ví dụ `"e\u0301"` (chữ e cộng dấu sắc kết hợp), emoji có skin-tone modifier hoặc các chuỗi emoji dùng zero-width joiner. Vì vậy đếm code point **không mặc nhiên là đếm số ký tự người dùng nhìn thấy**.

Với yêu cầu chọn vị trí con trỏ, cắt văn bản hiển thị hoặc giới hạn ký tự trong UI, cần thuật toán phân đoạn grapheme phù hợp Unicode, không chỉ `length()` hoặc `codePointCount()`. Còn với nhiều thao tác xử lý dữ liệu theo mã Unicode, code point chính là đơn vị phù hợp.

## 7. Những lỗi thường gặp

| Sai lầm | Giải thích / cách sửa |
| --- | --- |
| “Một `char` là một ký tự Unicode bất kỳ.” | Sai: `char` chứa một code unit 16 bit; code point ngoài BMP cần **hai** đơn vị. |
| “`String.length()` đếm code point.” | Sai: nó đếm code unit UTF-16. |
| “`substring(i, i+1)` luôn lấy một ký tự.” | Sai nếu `i` đứng tại high surrogate của code point ngoài BMP. Tính `end` bằng `offsetByCodePoints`. |
| “`charAt(1)` sẽ trả toàn bộ emoji.” | Sai: chỉ trả một surrogate. Dùng `codePointAt` ở ranh giới đúng. |
| “Độ dài UTF-8 bằng `String.length()`.” | Sai: byte UTF-8 và code unit UTF-16 là hai đơn vị đo khác nhau. |
| “Đếm code point chính là đếm grapheme.” | Sai: một grapheme có thể kết hợp nhiều code point. |
| “`String.codePoints()` tự sửa mọi UTF-16 hỏng.” | Sai: dữ liệu chứa surrogate lẻ cần được kiểm tra/xử lý theo chính sách đầu vào. |

## 8. Bài tập tự luyện

**Bài 1.** Giải thích vì sao `"A" + new String(Character.toChars(0x1F600)) + "B"` có `length() == 4`, nhưng `codePointCount(...) == 3`.

**Bài 2.** Dự đoán hai giá trị `(int) s.charAt(1)` và `(int) s.charAt(2)` trong chuỗi mẫu; đổi sang hệ 16 để đối chiếu với `D83D` và `DE00`.

**Bài 3.** Tạo `int cp = 0x1F680;` (🚀), dùng `Character.toChars(cp)` để tạo chuỗi, rồi in `length()` và `codePointCount`. Hai kết quả có giống nhau không?

**Bài 4.** Từ chuỗi `A😀B`, hãy cắt lấy chỉ emoji mà không cắt đôi surrogate pair, bằng `offsetByCodePoints` và `substring`.

**Bài 5.** Với `"e\u0301"`, dự đoán số code unit, code point và số ký tự hiển thị mà một người đọc có thể nhận thấy. Giải thích vì sao ba khái niệm này không luôn tương đương.

### Ghi nhớ

- **`char` = một UTF-16 code unit (16 bit)**, không phải mọi code point Unicode.
- **Ngoài BMP = hai code unit (high/low surrogate)**; ví dụ `U+1F600` ↔ `D83D DE00`.
- `String.length()` và chỉ số `charAt`/`substring` tính theo **UTF-16 code unit**.
- Dùng `codePointAt`, `codePoints`, `codePointCount` và `offsetByCodePoints` khi xử lý theo code point.
- **Code point khác grapheme cluster**, và UTF-8 byte count lại là phép đo khác.
