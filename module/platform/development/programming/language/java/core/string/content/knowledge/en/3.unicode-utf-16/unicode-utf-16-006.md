# `Character.toChars`, `charCount` và thao tác trên Unicode code point trong Java

## 1. Học xong bài này làm được gì?

Bạn sẽ chuyển đổi đúng giữa **Unicode code point** (`int`) và **UTF-16 code unit** (`char`), dùng `Character.toChars`/`Character.charCount` để xây dựng và duyệt chuỗi, rồi chọn đúng các API `String`, `Character` và `StringBuilder` khi xử lý văn bản có ký tự ngoài Basic Multilingual Plane (BMP). Bài cũng giải thích các lỗi phổ biến: dùng `charAt` như thể luôn trả về một ký tự đầy đủ, tăng index thêm 1 khi đi qua emoji, cắt đôi surrogate pair, và nhầm số code point với số ký tự người dùng nhìn thấy.

## 2. Nền tảng: code point khác `char`

Unicode gán **code point** có dạng `U+XXXX` cho các giá trị trong khoảng `U+0000` đến `U+10FFFF`. Java thường dùng `int` để giữ một giá trị code point. Trong khi đó, mỗi `char` là một **đơn vị mã UTF-16 rộng 16 bit** (code unit), có giá trị từ `0x0000` đến `0xFFFF`.

Trong UTF-16:

| Dải giá trị | Số `char` để biểu diễn | Ví dụ |
| --- | ---: | --- |
| BMP: `U+0000` đến `U+FFFF` (không tính tính hợp lệ riêng của surrogate khi dùng như ký tự độc lập) | 1 code unit | `U+0041` → `A`, `U+03A9` → `Ω` |
| Supplementary: `U+10000` đến `U+10FFFF` | 2 code unit tạo thành **surrogate pair** | `U+1F600` → 😀 |
| Giá trị ngoài `0x0000..0x10FFFF` | Không phải Unicode code point hợp lệ | `0x110000` |

Hai code unit của một surrogate pair có vai trò khác nhau:

- **High surrogate** nằm trong `U+D800..U+DBFF`.
- **Low surrogate** nằm trong `U+DC00..U+DFFF`.
- Cặp high trước, low sau mã hóa **một** supplementary code point. Ví dụ `U+1F600` → `U+D83D U+DE00`.
- Các code point ở dải `U+D800..U+DFFF` là **surrogate code points**: Java `Character.isValidCodePoint` vẫn coi giá trị số đó nằm trong dải code point hợp lệ, nhưng một surrogate đứng riêng **không phải Unicode scalar value**, không thể đại diện cho một ký tự Unicode độc lập hợp lệ khi trao đổi văn bản.

Phân biệt ba cách đếm:

| Câu hỏi | Java API | Với chuỗi `"A😀B"` |
| --- | --- | ---: |
| Có bao nhiêu UTF-16 code unit? | `s.length()` | 4 |
| Có bao nhiêu Unicode code point trong vùng? | `s.codePointCount(0, s.length())` | 3 |
| Người dùng nhìn thấy bao nhiêu cụm ký tự (grapheme cluster)? | Cần thuật toán phân cụm phù hợp | 3 trong ví dụ này |

Ví dụ `"e\u0301"` có hai code point (chữ `e` và dấu sắc kết hợp) dù thường hiển thị thành **một cụm ký tự**. Do đó code point không đồng nghĩa với grapheme cluster; `String.length()` càng không phải “độ dài theo ký tự người đọc”.

## 3. `Character.toChars(int codePoint)`: từ code point sang UTF-16

Phương thức:

~~~java
public static char[] Character.toChars(int codePoint)
~~~

Trả về một mảng `char[]` biểu diễn code point ở UTF-16:

- Nếu thuộc BMP, trả về mảng dài **1** với một code unit bằng giá trị code point.
- Nếu thuộc supplementary plane, trả về mảng dài **2**, theo thứ tự **high surrogate rồi low surrogate**.
- Nếu `codePoint` nằm ngoài `U+0000..U+10FFFF`, ném `IllegalArgumentException`.
- Trường hợp số code point là một giá trị surrogate BMP, phương thức vẫn trả về một `char` surrogate đơn lẻ; nó không tự kiểm tra yêu cầu “Unicode scalar value” trong dữ liệu cần trao đổi.

Ví dụ ngắn:

~~~java
char[] a = Character.toChars(0x0041);   // {'A'}, length = 1
char[] omega = Character.toChars(0x03A9); // {'Ω'}, length = 1
char[] face = Character.toChars(0x1F600); // {0xD83D, 0xDE00}, length = 2

String emojiText = new String(face);    // một code point, hai char UTF-16
String alsoEmoji = Character.toString(0x1F600); // có từ Java 11
~~~

Đừng ép `(char) 0x1F600` để “đổi emoji sang `char`”: phép ép làm mất các bit cao, không tạo surrogate pair đúng. Nếu mục tiêu là một `String`, sử dụng `new String(Character.toChars(cp))` hoặc `Character.toString(cp)` (Java 11+) thuận tiện hơn.

### Ghi vào mảng `char[]` có sẵn

Overload thứ hai:

~~~java
public static int Character.toChars(int codePoint, char[] dst, int dstIndex)
~~~

Nó ghi **1 hoặc 2** đơn vị UTF-16 bắt đầu tại `dstIndex` và trả về **số đơn vị thực sự đã ghi**, không trả về code point:

~~~java
char[] buffer = new char[4];
buffer[0] = '[';

int written = Character.toChars(0x1F600, buffer, 1); // written == 2
buffer[1 + written] = ']';

String wrapped = new String(buffer); // "[😀]"
~~~

Phải bảo đảm mảng đích có đủ chỗ, nhất là với supplementary code point. Overload này có thể ném `NullPointerException` nếu `dst` null, `IndexOutOfBoundsException` nếu index/capacity không hợp lệ và `IllegalArgumentException` nếu code point ngoài khoảng hợp lệ. Cách này thích hợp khi xây dựng bộ đệm UTF-16 có kiểm soát; với văn bản bình thường, `StringBuilder.appendCodePoint` thường đơn giản hơn.

## 4. `Character.charCount(int codePoint)`: cần bao nhiêu `char`?

`Character.charCount(cp)` trả về:

- `1` nếu `cp < 0x10000`.
- `2` nếu `cp >= 0x10000`.

Nó **không xác thực** `cp` có thuộc dải Unicode code point hay không:

~~~java
Character.charCount(0x0041);   // 1
Character.charCount(0x1F600);  // 2
Character.charCount(0x110000); // 2: vẫn trả về 2 dù giá trị không hợp lệ
Character.isValidCodePoint(0x110000); // false
~~~

Vì vậy `charCount` là hàm xác định **độ rộng UTF-16 dự kiến**, không phải hàm kiểm tra tính hợp lệ. Nếu `cp` lấy từ nguồn bên ngoài, hãy kiểm tra `Character.isValidCodePoint(cp)` trước khi gọi `toChars` hoặc `appendCodePoint`.

Khi `cp` được lấy bằng `s.codePointAt(offset)` tại một ranh giới code point hợp lệ, có thể dùng `offset += Character.charCount(cp)` để tiến sang code point tiếp theo.

## 5. Ví dụ Java 17+ đầy đủ, có thể biên dịch và chạy

Tạo tệp **`CodePointDemo.java`**:

~~~java
public class CodePointDemo {
    public static void main(String[] args) {
        int emoji = 0x1F600; // U+1F600, GRINNING FACE
        char[] pair = Character.toChars(emoji);
        String value = "A" + new String(pair) + "B";

        System.out.println("valid=" + Character.isValidCodePoint(emoji));
        System.out.println("supplementary=" + Character.isSupplementaryCodePoint(emoji));
        System.out.println("charCount=" + Character.charCount(emoji));
        System.out.printf("pair=U+%04X U+%04X%n", (int) pair[0], (int) pair[1]);
        System.out.println("pairValid=" + Character.isSurrogatePair(pair[0], pair[1]));
        System.out.printf("restored=U+%X%n", Character.toCodePoint(pair[0], pair[1]));

        System.out.println("length=" + value.length());
        System.out.println("codePointCount=" + value.codePointCount(0, value.length()));
        System.out.printf("at1=U+%X%n", value.codePointAt(1));
        System.out.printf("at2=U+%X%n", value.codePointAt(2));
        System.out.println("nextIndex=" + value.offsetByCodePoints(1, 1));

        for (int i = 0; i < value.length();) {
            int cp = value.codePointAt(i);
            System.out.printf("index=%d cp=U+%X%n", i, cp);
            i += Character.charCount(cp);
        }

        StringBuilder copy = new StringBuilder();
        value.codePoints().forEach(copy::appendCodePoint);
        System.out.println("roundTrip=" + value.contentEquals(copy));

        String decomposed = "e\u0301";
        System.out.println("combiningCodePoints="
                + decomposed.codePointCount(0, decomposed.length()));
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 CodePointDemo.java
java CodePointDemo
~~~

`stdout` đã kiểm tra khi biên dịch/chạy:

~~~text
valid=true
supplementary=true
charCount=2
pair=U+D83D U+DE00
pairValid=true
restored=U+1F600
length=4
codePointCount=3
at1=U+1F600
at2=U+DE00
nextIndex=3
index=0 cp=U+41
index=1 cp=U+1F600
index=3 cp=U+42
roundTrip=true
combiningCodePoints=2
~~~

Giải thích:

1. `0x1F600` là supplementary code point hợp lệ. `toChars` tạo hai code unit: high `D83D` và low `DE00`. `isSurrogatePair` xác nhận thứ tự đúng; `toCodePoint` ghép cặp thành `1F600`.
2. Với `"A😀B"`, các **chỉ số UTF-16** là `0: A`, `1: high surrogate`, `2: low surrogate`, `3: B`. Vì vậy `length() == 4` nhưng `codePointCount(...) == 3`.
3. `codePointAt(1)` đứng ở **high surrogate** nên ghép với low tiếp theo, trả `U+1F600`. `codePointAt(2)` đứng ở **low surrogate** nên chỉ trả giá trị `U+DE00`; API không tìm lùi để ghép cặp.
4. `offsetByCodePoints(1, 1)` di chuyển **một code point** từ chỉ số UTF-16 `1` và trả chỉ số UTF-16 `3`; do đó vòng lặp có index `0`, `1`, `3`.
5. `String.codePoints()` cung cấp luồng `IntStream` theo code point; `StringBuilder.appendCodePoint` mã hóa từng `int` trở lại UTF-16. `roundTrip=true` cho thấy chuỗi gốc được tái tạo.
6. `e` cộng dấu sắc kết hợp tạo hai code point dù mắt người thường thấy một cụm ký tự.

## 6. Các API đi cùng code point và cách chọn

| API | Input/chỉ số | Ý nghĩa |
| --- | --- | --- |
| `Character.isValidCodePoint(cp)` | `int` | `true` khi `0 <= cp <= 0x10FFFF`; **không loại trừ riêng surrogate code points** |
| `Character.isBmpCodePoint(cp)` | `int` | Trong `U+0000..U+FFFF`, bao gồm dải surrogate |
| `Character.isSupplementaryCodePoint(cp)` | `int` | Trong `U+10000..U+10FFFF` |
| `Character.toChars(cp)` | `int` | Code point → mảng 1 hoặc 2 `char` UTF-16 |
| `Character.charCount(cp)` | `int` | Trả 1/2 theo ngưỡng `0x10000`; không validate |
| `Character.isHighSurrogate(ch)` / `isLowSurrogate(ch)` | `char` | Kiểm tra từng nửa cặp surrogate |
| `Character.isSurrogatePair(hi, lo)` | hai `char` | Xác thực cặp high-low |
| `Character.toCodePoint(hi, lo)` | hai `char` | Ghép thành `int`; **không tự xác thực cặp** |
| `Character.highSurrogate(cp)` / `lowSurrogate(cp)` | `int` supplementary | Lấy hai nửa UTF-16; với cp không phải supplementary, kết quả không được quy định để sử dụng |
| `s.charAt(i)` | UTF-16 index | Trả **một code unit**, có thể chỉ là nửa surrogate |
| `s.codePointAt(i)` | UTF-16 index | Đọc code point bắt đầu tại `i`; ghép cặp nếu `i` là high có low liền sau |
| `s.codePointBefore(i)` | UTF-16 index **ngay sau** ký tự cần đọc | Đọc code point liền trước `i`; ghép nếu ngay trước là low có high liền trước |
| `s.codePointCount(begin, end)` | Hai UTF-16 offset, `end` exclusive | Đếm code point trong khoảng; surrogate lẻ tính thành một |
| `s.offsetByCodePoints(i, delta)` | UTF-16 index + số code point cần dịch | Trả về **UTF-16 index mới**, `delta` có thể âm |
| `s.chars()` / `s.codePoints()` | Không nhận index | `IntStream` lần lượt theo **code unit** / **code point** |
| `sb.appendCodePoint(cp)` | `int` | Nối code point vào `StringBuilder` thành 1/2 code unit |

### Chuyển từ surrogate pair về code point

Khi đã có hai `char`:

~~~java
char high = '\uD83D';
char low = '\uDE00';

if (Character.isSurrogatePair(high, low)) {
    int cp = Character.toCodePoint(high, low); // 0x1F600
}
~~~

`Character.toCodePoint` **không kiểm tra** cặp đầu vào. Nếu không chắc hai `char` đúng thứ tự high-low, gọi `isSurrogatePair` trước để tránh tạo ra số sai.

Công thức toán học đằng sau việc ghép cặp hợp lệ:

~~~text
codePoint = 0x10000
          + (high - 0xD800) * 0x400
          + (low  - 0xDC00)
~~~

Thông thường nên dùng API tiêu chuẩn thay vì tự viết công thức và xử lý các ca biên.

### Duyệt theo chiều ngược

Nếu cần đi từ cuối chuỗi đến đầu chuỗi theo code point, `codePointBefore` và `charCount` cho một mẫu đối xứng:

~~~java
String s = "A" + Character.toString(0x1F600) + "B";

for (int end = s.length(); end > 0;) {
    int cp = s.codePointBefore(end);
    System.out.printf("U+%X%n", cp);
    end -= Character.charCount(cp);
}
~~~

Đoạn này in lần lượt `U+42`, `U+1F600`, `U+41`. Chú ý tham số `end` của `codePointBefore` nằm **sau** đơn vị cần đọc, còn `codePointAt` nhận vị trí bắt đầu.

## 7. Cắt chuỗi và xử lý chỉ số cho đúng

Mọi index của `String` trong các API thông thường như `charAt`, `substring` và `length` vẫn là **vị trí UTF-16**. “Lấy hai code point đầu” không đồng nghĩa với `substring(0, 2)` nếu phần đầu có ký tự supplementary.

Ví dụ:

~~~java
String s = "A" + Character.toString(0x1F600) + "B";

// Hai code point đầu: 'A' và U+1F600.
int end = s.offsetByCodePoints(0, 2);
String firstTwoCodePoints = s.substring(0, end); // "A😀", end == 3
~~~

Mẫu tổng quát khi các chỉ số code point không âm và nằm trong phạm vi chuỗi:

~~~java
static String sliceByCodePoints(String s, int from, int count) {
    int start = s.offsetByCodePoints(0, from);
    int end = s.offsetByCodePoints(start, count);
    return s.substring(start, end);
}
~~~

Hàm trên sử dụng trực tiếp hợp đồng của API: nếu `from` hay `count` gây truy cập ngoài biên, `offsetByCodePoints` ném `IndexOutOfBoundsException`. Với yêu cầu bảo vệ dữ liệu đầu vào, hãy xác thực thêm `from >= 0` và `count >= 0` theo nghiệp vụ. Đầu mút cắt được tính từ ranh giới code point, tránh cắt ngang một cặp surrogate hợp lệ. Đây vẫn **không phải** thuật toán cắt theo grapheme cluster.

**Cảnh báo biên phạm vi:** `codePointCount(begin, end)` hoạt động trên đoạn UTF-16 cho sẵn. Nếu `begin` hoặc `end` cắt ngay giữa high/low surrogate, API chỉ thấy phần trong đoạn và có thể đếm surrogate lẻ như một code point. Khi dùng với giao diện theo code point, hãy chuyển đổi và giữ các ranh giới hợp lệ trước.

## 8. Dữ liệu sai chuẩn: validation và surrogate không ghép cặp

Các phương thức trong `Character` không có cùng chính sách lỗi.

~~~java
System.out.println(Character.isValidCodePoint(0x110000)); // false
System.out.println(Character.charCount(0x110000));        // 2, không validate
// Character.toChars(0x110000); // ném IllegalArgumentException

System.out.println(Character.isValidCodePoint(0xD800));   // true
System.out.println(Character.isSurrogate((char) 0xD800));  // true
~~~

Dải surrogate `0xD800..0xDFFF` nằm trong khoảng số code point mà `Character.isValidCodePoint` chấp nhận, nhưng từng giá trị đơn lẻ **không phải Unicode scalar value**. Để từ chối cả số ngoài miền Unicode và surrogate code points khi hệ thống yêu cầu một scalar value:

~~~java
static boolean isUnicodeScalarValue(int cp) {
    return Character.isValidCodePoint(cp)
            && (cp < 0xD800 || cp > 0xDFFF);
}
~~~

Một chuỗi Java có thể chứa `char` surrogate **không được ghép cặp** (ví dụ dữ liệu bị cắt ngang hoặc do tạo trực tiếp). `codePointAt`, `codePointBefore`, `codePoints()` và `codePointCount` có quy tắc xử lý chúng: các surrogate lẻ được đọc hoặc đếm như từng giá trị `char` đơn lẻ, **không tự sửa chuỗi thành UTF-16 chuẩn**. Nếu ứng dụng cần xuất dữ liệu Unicode nghiêm ngặt, cần quy tắc kiểm tra/thay thế dữ liệu lỗi theo giao thức đích.

Ngoài ra, `Character.highSurrogate(cp)` và `lowSurrogate(cp)` chỉ nên dùng khi `Character.isSupplementaryCodePoint(cp)` đúng; với đầu vào không supplementary, API không bảo đảm một nửa surrogate có ý nghĩa. Tương tự, trước khi `toCodePoint(high, low)` nên xác thực bằng `isSurrogatePair`.

## 9. Lỗi thường gặp và cách sửa

**Lỗi 1 — duyệt `String` bằng `charAt(i)` rồi coi mỗi `char` là một ký tự Unicode.**

Sai khi có emoji hoặc chữ ở supplementary plane, vì `charAt` chỉ trả một code unit. Nếu mục đích là duyệt code point:

~~~java
for (int i = 0; i < s.length();) {
    int cp = s.codePointAt(i);
    // Xử lý cp như một Unicode code point
    i += Character.charCount(cp);
}
~~~

Hoặc dùng `s.codePoints().forEach(cp -> ...)` nếu không cần chỉ số UTF-16.

**Lỗi 2 — dùng `new String(new char[] {(char) cp})` cho mọi `cp`.** Phép ép xuống `char` chỉ giữ 16 bit; dùng `new String(Character.toChars(cp))` để hỗ trợ supplementary code point.

**Lỗi 3 — dùng `charCount(cp)` để xác nhận đầu vào.** Hàm này không kiểm tra hợp lệ; áp dụng `isValidCodePoint` và, nếu cần, loại surrogate code points riêng.

**Lỗi 4 — kiểm tra loại ký tự bằng overload `char`.** Ví dụ `Character.isLetter(char)` không thể xem toàn bộ một code point supplementary. Với văn bản có Unicode ngoài BMP, ưu tiên overload `Character.isLetter(int cp)` sau khi đọc bằng `codePointAt` hoặc `codePoints()`.

**Lỗi 5 — đếm code point để suy ra “số ký tự hiển thị” hoặc giới hạn độ dài tên người dùng.** Tổ hợp chữ+dấu, emoji biến thể, chuỗi nối ZWJ và cờ có thể gồm nhiều code point nhưng hiển thị thành một grapheme cluster. Nếu yêu cầu là cắt/đếm theo cụm ký tự người dùng nhận biết, dùng thuật toán phân đoạn grapheme theo Unicode thích hợp; `codePointCount` giải quyết bài toán khác.

**Lỗi 6 — ghép cặp surrogate mà không kiểm tra thứ tự.** `Character.toCodePoint` không xác minh cặp; hãy gọi `Character.isSurrogatePair` trước hoặc đọc trực tiếp code point qua `String`.

## 10. Câu hỏi tự kiểm tra

1. **`Character.toChars(0x1F600).length` và `Character.charCount(0x1F600)` trả về gì?**  
   Đều là `2`; một code point supplementary cần hai UTF-16 code unit.
2. **Vì sao `"A😀B".length()` là 4 nhưng `codePointCount(0, length)` là 3?**  
   Hai chữ BMP chiếm 1 `char` mỗi chữ, emoji chiếm 2 `char` nhưng chỉ một code point.
3. **`Character.charCount(0x110000)` trả về gì và có bảo đảm số hợp lệ không?**  
   Trả `2`; **không**. `Character.isValidCodePoint(0x110000)` là `false`, `toChars` ném ngoại lệ.
4. **`String.codePointAt(i)` nhận chỉ số code point hay chỉ số `char`?**  
   Nhận **chỉ số UTF-16**. Với high surrogate, nó có thể ghép cặp với low kế tiếp; bắt đầu ở low surrogate thì không ghép lùi.
5. **Khi cần cắt 5 code point đầu trong `String`, dùng gì?**  
   `int end = s.offsetByCodePoints(0, 5);` rồi `s.substring(0, end)`, với điều kiện chuỗi đủ 5 code point.
6. **`Character.isValidCodePoint(0xD800)` có đủ để coi ký tự là Unicode scalar không?**  
   Không. Giá trị nằm trong dải surrogate và phải được loại riêng nếu cần scalar value.

## 11. Tài liệu chuẩn

- [Java SE 17 — `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `toChars`, `charCount`, `isValidCodePoint`, `isSurrogatePair`, `toCodePoint` và các overload nhận `int`.
- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `codePointAt`, `codePointBefore`, `codePointCount`, `offsetByCodePoints`, `chars` và `codePoints`.
- [Java SE 17 — `StringBuilder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `appendCodePoint`.
- [Unicode Standard — Encoding Forms](https://www.unicode.org/versions/latest/core-spec/chapter-3/): UTF-16, surrogate pairs, code points, scalar values.

**Ghi nhớ:** `char` là **một code unit UTF-16**, còn code point được biểu diễn bằng `int` và có thể cần **một hoặc hai** `char`. Dùng `toChars` để mã hóa, `charCount` để dịch chuyển đúng số code unit, `String.codePointAt`/`codePoints` để đọc và `offsetByCodePoints` để chuyển chỉ số trước khi cắt chuỗi.