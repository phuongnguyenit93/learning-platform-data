# BMP, ký tự bổ sung và surrogate pair trong Java String

Java lưu và xử lý văn bản theo mô hình Unicode, trong đó mỗi **code point** được nhận diện bằng một giá trị như `U+0041` (chữ A), `U+4E2D` (chữ 中) hoặc `U+1F600` (😀). Tuy nhiên, một phần lớn API `String` của Java sử dụng **UTF-16 code unit** làm đơn vị đếm và chỉ số. Vì thế, một ký tự Unicode có thể chiếm **hai phần tử `char`** trong `String`.

Hiểu rõ Basic Multilingual Plane (BMP), ký tự bổ sung (supplementary character) và surrogate pair giúp bạn xử lý đúng `length()`, `charAt()`, `substring()`, vòng lặp và việc chuyển đổi giữa `char`, `int` và `String`.

## 1. Phân biệt code point, code unit và ký tự người dùng nhìn thấy

- **Unicode code point**: một vị trí mã trong không gian `U+0000` đến `U+10FFFF`; thường viết dạng `U+XXXX` hoặc `U+XXXXX`/`U+XXXXXX`. Trong Java, nên lưu một code point bằng `int`.
- **Unicode scalar value**: code point **không nằm trong** vùng surrogate `U+D800`–`U+DFFF`. Mỗi scalar value có thể được biểu diễn hợp lệ bằng UTF-16.
- **UTF-16 code unit**: đơn vị 16 bit. Kiểu nguyên thủy `char` của Java chứa **một** UTF-16 code unit (giá trị `0x0000`–`0xFFFF`). Một `char` không nhất thiết tương đương một code point hoàn chỉnh.
- **Grapheme cluster** (cụm ký tự hiển thị): thứ người đọc thường nhận là một ký tự; có thể được tạo từ nhiều code point, ví dụ `e` + dấu sắc kết hợp hoặc một emoji ghép bằng ký tự nối.

Ba phép đếm này không luôn bằng nhau. `String.length()` đếm **UTF-16 code unit**, `String.codePointCount(...)` đếm **code point theo cách xử lý UTF-16 của Java**, còn số cụm ký tự hiển thị cần quy tắc phân đoạn grapheme chuyên biệt.

Ví dụ nhanh:

| Văn bản | Các code point | UTF-16 code unit | `String.length()` |
| --- | --- | ---: | ---: |
| `A` | `U+0041` | 1 | 1 |
| `中` | `U+4E2D` | 1 | 1 |
| `😀` | `U+1F600` | 2 | 2 |
| `é` (chữ e + dấu sắc kết hợp) | `U+0065`, `U+0301` | 2 | 2 |

Hàng cuối có hai code point trong BMP nhưng thường hiển thị thành một chữ có dấu. Vì vậy **đếm code point vẫn không đồng nghĩa đếm ký tự mà người dùng cảm nhận**.

## 2. BMP và supplementary planes

Unicode chia không gian code point thành **17 plane**, mỗi plane có khả năng chứa 65.536 vị trí mã:

| Phân vùng | Dải giá trị | Ý nghĩa |
| --- | --- | --- |
| BMP (plane 0) | `U+0000`–`U+FFFF` | Chứa phần lớn chữ cái, ký hiệu phổ biến và cả vùng mã dành riêng cho surrogate |
| Các supplementary planes (plane 1–16) | `U+10000`–`U+10FFFF` | Chứa nhiều chữ viết lịch sử, ký hiệu âm nhạc, emoji và các bộ ký tự khác |
| Surrogate code points (nằm trong BMP) | `U+D800`–`U+DFFF` | Giá trị **dành riêng cho UTF-16**, không được dùng làm Unicode scalar value độc lập |

**BMP không có nghĩa mọi vị trí trong BMP đều là ký tự hợp lệ để hiển thị.** Các vị trí surrogate là code point được dành riêng và không phải Unicode scalar value; ngoài ra còn có vị trí chưa gán hoặc không dành cho ký tự văn bản thông thường.

Một Unicode scalar value thuộc BMP (trừ vùng surrogate) được mã hóa bằng **một UTF-16 code unit**. Một code point thuộc supplementary planes được mã hóa bằng **hai UTF-16 code unit**, gọi là **surrogate pair**. Không có code point Unicode hợp lệ lớn hơn `U+10FFFF`.

Ví dụ:

- `U+0061` (a), `U+00E9` (é), `U+4E2D` (中): đều thuộc BMP; mỗi code point chiếm một `char`.
- `U+1F600` (😀), `U+1D11E` (𝄞, ký hiệu khóa Sol âm nhạc): đều thuộc supplementary planes; mỗi code point cần hai `char`.

## 3. Surrogate pair được ghép như thế nào?

UTF-16 dùng hai nhóm mã dành riêng:

- **High surrogate (leading surrogate):** `U+D800`–`U+DBFF`.
- **Low surrogate (trailing surrogate):** `U+DC00`–`U+DFFF`.

Với code point `cp` từ `U+10000` đến `U+10FFFF`, quá trình mã hóa được mô tả như sau:

1. Tính `x = cp - 0x10000` (giá trị 20 bit).
2. Lấy 10 bit cao: `high = 0xD800 + (x >> 10)`.
3. Lấy 10 bit thấp: `low = 0xDC00 + (x & 0x3FF)`.
4. Lưu lần lượt **high surrogate rồi low surrogate**.

Để giải mã một cặp hợp lệ:

```text
codePoint = 0x10000
          + ((high - 0xD800) << 10)
          +  (low  - 0xDC00)
```

Ví dụ với emoji 😀 (`U+1F600`):

```text
Code point           : U+1F600
UTF-16 high surrogate: U+D83D
UTF-16 low surrogate : U+DE00
Trong Java String    : [\uD83D] [\uDE00]  (2 code unit/char)
```

Chỉ khi **high surrogate đứng ngay trước low surrogate** thì Java mới có thể kết hợp hai đơn vị thành một supplementary code point. Một high surrogate đứng lẻ, low surrogate đứng lẻ, hoặc hai surrogate sai thứ tự là **chuỗi UTF-16 không hợp lệ về mặt cặp mã** (ill-formed UTF-16). Kiểu `String` của Java vẫn có khả năng chứa các code unit lẻ như vậy; ứng dụng không được mặc định mọi `String` đều có UTF-16 được ghép cặp đầy đủ.

Các API liên quan trong `Character`:

| Phương thức | Công dụng |
| --- | --- |
| `Character.isHighSurrogate(char)` | Kiểm tra một `char` thuộc vùng high surrogate |
| `Character.isLowSurrogate(char)` | Kiểm tra một `char` thuộc vùng low surrogate |
| `Character.isSurrogatePair(high, low)` | Kiểm tra đúng thứ tự cặp high + low |
| `Character.toCodePoint(high, low)` | Ghép **cặp surrogate hợp lệ** thành code point dạng `int` |
| `Character.toChars(int)` | Mã hóa một code point thành mảng `char[]` dài 1 hoặc 2 |
| `Character.charCount(int)` | Trả về 2 nếu code point thuộc supplementary range, ngược lại trả về 1 |

Lưu ý: `Character.toCodePoint()` giả định đầu vào là cặp phù hợp; nếu nhận dữ liệu không chắc chắn, hãy gọi `isSurrogatePair()` trước.

## 4. Ví dụ Java: cùng một code point nhưng có hai char

Tệp `UnicodeBasics.java` (Java 17+):

```java
public class UnicodeBasics {
    public static void main(String[] args) {
        String bmp = "\u4E2D"; // U+4E2D: một ký tự thuộc BMP
        String supplementary = new String(Character.toChars(0x1F600));

        System.out.printf(
                "BMP: length=%d, codePoints=%d%n",
                bmp.length(), bmp.codePointCount(0, bmp.length())
        );
        System.out.printf(
                "Supplementary: length=%d, codePoints=%d%n",
                supplementary.length(),
                supplementary.codePointCount(0, supplementary.length())
        );

        char high = supplementary.charAt(0);
        char low = supplementary.charAt(1);

        System.out.printf("charAt(0)=U+%04X%n", (int) high);
        System.out.printf("charAt(1)=U+%04X%n", (int) low);
        System.out.println("valid pair=" + Character.isSurrogatePair(high, low));
        System.out.printf("codePointAt(0)=U+%X%n",
                supplementary.codePointAt(0));
        System.out.printf("toCodePoint=U+%X%n",
                Character.toCodePoint(high, low));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 UnicodeBasics.java
java UnicodeBasics
```

Kết quả chuẩn:

```text
BMP: length=1, codePoints=1
Supplementary: length=2, codePoints=1
charAt(0)=U+D83D
charAt(1)=U+DE00
valid pair=true
codePointAt(0)=U+1F600
toCodePoint=U+1F600
```

Ở đây `String.length()` của emoji trả về **2**, bởi nó đếm hai UTF-16 code unit. Trong khi đó `codePointCount(0, length())` trả về **1** vì cặp surrogate hợp lệ là một code point.

`charAt(0)` và `charAt(1)` chỉ trả về từng phần của cặp mã. Không được giả định một `charAt(index)` luôn là ký tự Unicode hoàn chỉnh. `String.codePointAt(index)` có thể ghép cặp khi `index` đứng tại **high surrogate** và ngay sau là **low surrogate**; nếu gọi bắt đầu từ low surrogate, nó không tự nhìn lùi để ghép với phần high phía trước.

Có thể tạo cùng emoji bằng escape trong string literal:

```java
String smile = "\uD83D\uDE00";
```

Chuỗi escape trên cung cấp hai UTF-16 code unit. Dùng `new String(Character.toChars(0x1F600))` thường giúp thể hiện rõ hơn rằng ta bắt đầu từ một **code point**.

## 5. Chỉ số char khác vị trí code point

Các API như `charAt(int)`, `substring(int, int)`, `indexOf(...)` theo các overload nhận/trả chỉ số, và `String.length()` làm việc với **chỉ số UTF-16 code unit**. Nhưng một code point supplementary chiếm hai chỉ số liên tiếp.

Xét chuỗi `A😀B`:

```text
Chỉ số UTF-16:  0         1          2         3
Code unit    : 'A'    high D83D   low DE00    'B'
Code point   : U+0041        U+1F600         U+0042
Vị trí code point: 0              1             2
```

Tổng cộng `length() == 4` nhưng chỉ có **3 code point**.

Đây là ví dụ duyệt đúng theo code point bằng `codePointAt()` kết hợp `Character.charCount()`:

Tệp `CodePointIteration.java`:

```java
public class CodePointIteration {
    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";

        System.out.println("length=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));

        for (int charIndex = 0; charIndex < text.length();) {
            int codePoint = text.codePointAt(charIndex);
            System.out.printf("charIndex=%d -> U+%X%n", charIndex, codePoint);
            charIndex += Character.charCount(codePoint);
        }

        int afterTwoCodePoints = text.offsetByCodePoints(0, 2);
        System.out.println("offsetByCodePoints(0, 2)=" + afterTwoCodePoints);

        String emojiOnly = text.substring(1, 3);
        System.out.printf("substring(1, 3)=U+%X%n",
                emojiOnly.codePointAt(0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CodePointIteration.java
java CodePointIteration
```

Kết quả:

```text
length=4
codePoints=3
charIndex=0 -> U+41
charIndex=1 -> U+1F600
charIndex=3 -> U+42
offsetByCodePoints(0, 2)=3
substring(1, 3)=U+1F600
```

Vòng lặp tăng chỉ số UTF-16 lên **1** cho code point thuộc BMP, và lên **2** cho code point supplementary. Lời gọi `offsetByCodePoints(0, 2)` chuyển vị trí **hai code point** tính từ chỉ số UTF-16 số 0 thành chỉ số UTF-16 số **3**; kết quả này hữu ích khi cần cắt chuỗi tại ranh giới code point.

Có thể duyệt ngắn gọn bằng `text.codePoints()`, trả về `IntStream` chứa giá trị dạng `int`:

```java
text.codePoints().forEach(cp ->
        System.out.printf("U+%X%n", cp)
);
```

Đoạn trên là phần minh họa cần đặt trong phương thức có biến `text` đã khai báo. Với chuỗi `A😀B`, nó lần lượt in `U+41`, `U+1F600`, `U+42` (mỗi giá trị trên một dòng).

**Phân biệt `chars()` và `codePoints()`:**

- `text.chars()` tạo luồng các giá trị `int` đại diện **từng UTF-16 code unit**. Với `A😀B`, luồng có **4** phần tử: `0x41`, `0xD83D`, `0xDE00`, `0x42`.
- `text.codePoints()` cố gắng ghép **các surrogate pair hợp lệ**; cùng ví dụ trên, luồng có **3** phần tử: `0x41`, `0x1F600`, `0x42`.

Nếu chuỗi có surrogate đứng lẻ, `codePoints()` vẫn có thể phát ra chính giá trị surrogate chưa ghép dưới dạng `int`; đừng mặc định tất cả phần tử đều là Unicode scalar value hợp lệ.

## 6. Cắt chuỗi mà không làm hỏng surrogate pair

Hai chỉ số của `substring(beginIndex, endIndex)` là vị trí UTF-16, **begin bao gồm, end không bao gồm**. Với chuỗi `A😀B`, `substring(1, 3)` giữ trọn emoji; còn `substring(1, 2)` chỉ lấy **high surrogate** và tạo ra chuỗi UTF-16 bị tách cặp.

Nếu nghiệp vụ cần lấy **n code point đầu tiên**, hãy chuyển số code point sang chỉ số UTF-16 trước khi gọi `substring()`:

```java
public class SafeSubstring {
    static String firstCodePoints(String text, int count) {
        int end = text.offsetByCodePoints(0, count);
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";
        String firstTwo = firstCodePoints(text, 2);

        System.out.println("UTF16 length=" + firstTwo.length());
        System.out.println("codePoints=" +
                firstTwo.codePointCount(0, firstTwo.length()));
        System.out.printf("lastCodePoint=U+%X%n",
                firstTwo.codePointBefore(firstTwo.length()));
    }
}
```

Lưu thành `SafeSubstring.java`, biên dịch và chạy bằng `javac -encoding UTF-8 SafeSubstring.java` và `java SafeSubstring`. Kết quả:

```text
UTF16 length=3
codePoints=2
lastCodePoint=U+1F600
```

`offsetByCodePoints()` có thể ném `IndexOutOfBoundsException` khi số code point cần dịch nằm ngoài phạm vi hợp lệ. Ví dụ sử dụng thực tế nên kiểm tra `count >= 0` và `count <= text.codePointCount(0, text.length())` trước khi cắt, hoặc quy định rõ cách xử lý đầu vào không hợp lệ.

Giải pháp trên bảo vệ ranh giới **code point**, nhưng chưa chắc bảo toàn một **grapheme cluster**. Ví dụ cắt giữa `e` và dấu kết hợp `U+0301` vẫn có thể phá trải nghiệm hiển thị mặc dù không cắt surrogate pair.

## 7. Kiểm tra surrogate đứng lẻ và giá trị mã không hợp lệ

Một `String` có thể lưu riêng một high surrogate mà không có low surrogate kèm theo:

```java
String broken = "\uD83D";
System.out.println(broken.length());                     // 1
System.out.println(Character.isHighSurrogate(broken.charAt(0))); // true
System.out.printf("U+%X%n", broken.codePointAt(0));      // U+D83D
```

Đây là các câu lệnh minh họa để đặt trong một phương thức Java. `codePointAt()` trả về giá trị code unit chưa ghép khi không có một cặp surrogate hợp lệ, vì vậy kết quả `U+D83D` ở đây **không phải Unicode scalar value**. Khi ghi dữ liệu dạng này sang một encoding hoặc một hệ thống khác, cách xử lý ký tự lỗi có thể phụ thuộc encoder và cấu hình xử lý lỗi. Không nên dựa vào việc surrogate đứng lẻ được truyền đi nguyên dạng.

Để nhận biết surrogate pair khi duyệt bằng `char`:

```java
static boolean hasWellFormedUtf16(String text) {
    for (int i = 0; i < text.length(); i++) {
        char current = text.charAt(i);

        if (Character.isHighSurrogate(current)) {
            if (i + 1 >= text.length() ||
                    !Character.isLowSurrogate(text.charAt(i + 1))) {
                return false;
            }
            i++; // Bỏ qua low surrogate vừa ghép cùng high surrogate
        } else if (Character.isLowSurrogate(current)) {
            return false; // Low surrogate đứng lẻ
        }
    }
    return true;
}
```

Đây là **phương thức minh họa**, cần đặt bên trong một lớp. Nó kiểm tra tính đúng đắn của **các cặp UTF-16**, không kiểm tra việc một code point đã được Unicode gán ký tự cụ thể hay chưa.

Ngoài ra:

- `Character.isValidCodePoint(cp)` chỉ kiểm tra số nguyên nằm trong dải `U+0000`–`U+10FFFF`; kiểm tra này **không loại riêng vùng surrogate**. Muốn nhận một Unicode scalar value, phải loại thêm `U+D800`–`U+DFFF`.
- `Character.isSupplementaryCodePoint(cp)` nhận biết dải `U+10000`–`U+10FFFF`.
- `Character.toChars(cp)` sẽ từ chối giá trị ngoài dải Unicode bằng `IllegalArgumentException`, nhưng không nên dùng nó một mình như bộ kiểm tra scalar value. Với giá trị surrogate, nó vẫn có thể tạo ra một `char` surrogate đứng lẻ.
- Ký tự nằm trong BMP không đồng nghĩa đã được Unicode gán ý nghĩa hiển thị. Mặt khác, sự tồn tại của glyph còn phụ thuộc font và môi trường hiển thị.

## 8. Không đồng nhất code point với độ dài byte hay ký tự hiển thị

Cần phân biệt ba lớp biểu diễn:

| Câu hỏi | API/khái niệm phù hợp |
| --- | --- |
| Chuỗi có bao nhiêu UTF-16 code unit? | `text.length()` |
| Có bao nhiêu code point theo quy tắc ghép surrogate của Java? | `text.codePointCount(0, text.length())` hoặc `text.codePoints().count()` |
| Một code point ở chỉ số UTF-16 nào? | `text.codePointAt(charIndex)` |
| Dịch n code point từ một chỉ số UTF-16? | `text.offsetByCodePoints(charIndex, n)` |
| UTF-8 của chuỗi có bao nhiêu byte? | `text.getBytes(StandardCharsets.UTF_8).length` với lưu ý dữ liệu UTF-16 lỗi có thể bị thay thế khi encode |
| Người dùng thấy bao nhiêu “ký tự”? | Phân đoạn grapheme cluster theo quy tắc Unicode phù hợp |

Ví dụ `😀` chiếm **2 UTF-16 code unit** nhưng **4 byte UTF-8** khi mã hóa hợp lệ. `String.length()` không phải số byte của file hay request HTTP; cũng không phải kích thước bộ nhớ nội bộ của đối tượng `String`. JVM có thể tối ưu lưu trữ chuỗi bằng biểu diễn nội bộ khác, nhưng hợp đồng công khai của API vẫn dựa trên chỉ số UTF-16.

Với dấu kết hợp:

```java
String decomposed = "e\u0301"; // e + COMBINING ACUTE ACCENT
String composed = "\u00E9";   // é dạng tiền tổ hợp

System.out.println(decomposed.length()); // 2
System.out.println(composed.length());   // 1
```

Hai chuỗi có thể hiển thị tương tự nhưng khác chuỗi code point và không `equals()` nhau nếu chưa chuẩn hóa theo quy tắc thích hợp. **Unicode normalization** là chủ đề liên quan nhưng độc lập với việc ghép surrogate pair.

## 9. Lỗi phổ biến

**Lỗi 1 — Coi `char` là một ký tự Unicode hoàn chỉnh.** `char` chỉ là code unit 16 bit. Một supplementary code point cần hai `char` liên tiếp.

**Lỗi 2 — Dùng `length()` làm số code point.** Khi có ký tự bổ sung, `length()` lớn hơn số code point; hãy dùng `codePointCount()` để đếm code point theo mô hình của Java.

**Lỗi 3 — Tăng chỉ số `i++` rồi gọi `codePointAt(i)`.** Vòng lặp có thể dừng tại low surrogate và xử lý nhầm từng nửa của ký tự. Tăng bằng `Character.charCount(codePoint)` hoặc duyệt `codePoints()`.

**Lỗi 4 — Cắt `substring()` giữa cặp surrogate.** Sử dụng `offsetByCodePoints()` để chuyển vị trí code point sang chỉ số UTF-16 trước khi cắt. Nếu thao tác hiển thị yêu cầu giữ cụm grapheme, cần giải pháp phân đoạn ở mức cao hơn.

**Lỗi 5 — Tin rằng surrogate nào cũng thuộc một cặp hợp lệ.** `String` có thể chứa surrogate đứng lẻ. Dữ liệu nhập từ bên ngoài cần được xác thực hoặc quy định cách xử lý ký tự lỗi khi cần.

**Lỗi 6 — Nhầm số code unit, code point, grapheme cluster và byte.** Bốn đại lượng phục vụ các nhu cầu khác nhau: chỉ số API Java, mã Unicode, trải nghiệm văn bản và lưu trữ/truyền tải.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `"😀".length()` bằng 2 nhưng `"😀".codePointCount(0, "😀".length())` bằng 1?

**Trả lời:** Emoji `U+1F600` là supplementary code point, nên UTF-16 biểu diễn bằng hai code unit `U+D83D` và `U+DE00`. `length()` đếm hai code unit; `codePointCount()` nhận ra một cặp hợp lệ và đếm một code point.

**Câu 2.** `charAt(1)` trong chuỗi `A😀B` trả về gì?

**Trả lời:** High surrogate `U+D83D`, không phải toàn bộ code point `U+1F600`. Để đọc toàn bộ emoji, dùng `codePointAt(1)` và nhận giá trị `int`.

**Câu 3.** Tại sao `substring(1, 2)` trên `A😀B` có vấn đề, còn `substring(1, 3)` thì không?

**Trả lời:** Chỉ số của `substring()` tính theo UTF-16 code unit. Đoạn `[1,2)` chỉ lấy high surrogate; đoạn `[1,3)` lấy đủ cả high và low surrogate.

**Câu 4.** Một `String` có 5 code point có chắc hiển thị thành 5 ký tự không?

**Trả lời:** Không. Các dấu kết hợp, variation selector hoặc chuỗi emoji ghép có thể chứa nhiều code point nhưng hiển thị thành ít cụm grapheme hơn.

**Ghi nhớ:** BMP scalar value dùng **một** UTF-16 code unit; supplementary code point dùng **hai** code unit tạo thành **high + low surrogate**. Trong Java, `char` và chỉ số của `String` thuộc mức UTF-16 code unit; khi cần xử lý trọn vẹn code point, ưu tiên `int`, `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `Character.charCount()` hoặc `codePoints()`.
