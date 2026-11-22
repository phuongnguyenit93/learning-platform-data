# `char` là đơn vị mã UTF-16 không dấu — Java 17+

Trong Java, `char` là một trong tám **kiểu nguyên thủy**. Nó lưu **đúng một đơn vị mã UTF-16 (UTF-16 code unit) 16 bit không dấu**, tức một giá trị nguyên từ **0 đến 65.535** (`0x0000` đến `0xFFFF`).

Điểm dễ nhầm: **một `char` không đồng nghĩa với một ký tự Unicode hoàn chỉnh hoặc một ký tự người dùng nhìn thấy**. Có Unicode code point được biểu diễn bằng hai đơn vị mã UTF-16, và có ký tự hiển thị được tạo từ nhiều code point.

## 1. `char` lưu gì?

| Biểu thức | Giá trị / ý nghĩa | Lưu ý |
| --- | --- | --- |
| `char c = 'A';` | Một `char` chứa mã `0x0041`, tức 65 | Nháy đơn tạo character literal |
| `char c = '\u00E9';` | Một `char` chứa mã `0x00E9`, tức 233 (é) | Unicode escape trong mã nguồn |
| `char min = Character.MIN_VALUE;` | `0` (`0x0000`) | Không có giá trị `char` âm |
| `char max = Character.MAX_VALUE;` | `65_535` (`0xFFFF`) | Không phải code point Unicode lớn nhất |
| `int n = 'A';` | `65` | Chuyển mở rộng `char` sang `int` |
| `int n = 'A' + 1;` | `66` | Phép toán số học thường nâng `char` thành `int` |
| `String s = "A";` | Chuỗi gồm một UTF-16 code unit | `String` là kiểu tham chiếu, khác `char` |

Khác với `byte`, `short`, `int` và `long` vốn là các kiểu nguyên **có dấu**, `char` là kiểu nguyên **không dấu**. Ép `char` sang `int` sẽ cho giá trị trong miền 0–65.535, không bị hiểu thành số âm.

Một `char` có thể chứa một **surrogate code unit** (`0xD800`–`0xDFFF`). Đơn vị mã này **không phải tự nó là một Unicode scalar value độc lập**; nó có thể là một nửa của cặp surrogate biểu diễn một code point ngoài BMP.

## 2. Chương trình Java 17+ chạy được

Tạo file UTF-8 tên **`CharUtf16Demo.java`**:

~~~java
public class CharUtf16Demo {
    public static void main(String[] args) {
        char letter = 'A';
        char accented = '\u00E9';
        char max = Character.MAX_VALUE;
        char wrapped = (char) (max + 1);

        int rocketCodePoint = 0x1F680;
        String rocket = new String(Character.toChars(rocketCodePoint));

        System.out.println("letter=" + letter);
        System.out.println("letterCode=" + (int) letter);
        System.out.println("accentedCode=" + (int) accented);
        System.out.println("charMin=" + (int) Character.MIN_VALUE);
        System.out.println("charMax=" + (int) max);
        System.out.println("wrapped=" + (int) wrapped);
        System.out.println("letterPlusOne=" + (letter + 1));

        System.out.println("rocketUnits=" + rocket.length());
        System.out.println(
                "rocketPoints=" + rocket.codePointCount(0, rocket.length()));
        System.out.println(
                "highSurrogate=" + Character.isHighSurrogate(rocket.charAt(0)));
        System.out.println(
                "lowSurrogate=" + Character.isLowSurrogate(rocket.charAt(1)));
        System.out.printf("rocketCodePoint=U+%X%n", rocket.codePointAt(0));

        String combining = "e\u0301";
        System.out.println("combiningUnits=" + combining.length());
        System.out.println(
                "combiningPoints="
                + combining.codePointCount(0, combining.length()));
    }
}
~~~

Mở **PowerShell (Windows)** hoặc **Bash (Linux/macOS)** trong thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CharUtf16Demo.java
java CharUtf16Demo
~~~

**Expected output:**

~~~text
letter=A
letterCode=65
accentedCode=233
charMin=0
charMax=65535
wrapped=0
letterPlusOne=66
rocketUnits=2
rocketPoints=1
highSurrogate=true
lowSurrogate=true
rocketCodePoint=U+1F680
combiningUnits=2
combiningPoints=2
~~~

**Giải thích kết quả:**

- `'A'` mang mã 65; `'\u00E9'` chuyển thành chữ é trước khi mã được phân tích, với đơn vị mã 233.
- `Character.MAX_VALUE + 1` được tính dưới dạng `int` cho 65.536; ép lại `char` lấy 16 bit thấp nên bằng `0`. Đây là **ép kiểu có mất thông tin**, không phải Java tự tạo một `char` âm.
- `letter + 1` có kiểu kết quả `int`, nên lệnh in số `66` thay vì chữ `B`.
- U+1F680 (🚀) lớn hơn `0xFFFF`; `Character.toChars` tạo **hai `char`**, một high surrogate và một low surrogate. Do vậy `String.length()` trả `2` nhưng `codePointCount` trả `1`.
- Chuỗi `"e\u0301"` gồm `e` và dấu sắc kết hợp (hai code point), có thể hiển thị như **một** ký tự. Vì vậy cả `length()` và `codePointCount()` đều bằng 2 dù mắt thường thấy một chữ có dấu.

Ví dụ cố ý chỉ in **ASCII, số và boolean** cho các giá trị Unicode đặc biệt để đầu ra dễ đối chiếu trên terminal có cấu hình phông chữ khác nhau.

## 3. Phân biệt code unit, code point và ký tự hiển thị

| Khái niệm | Đơn vị | Ví dụ |
| --- | --- | --- |
| **UTF-16 code unit** | Một giá trị 16 bit, đúng khả năng chứa của `char` | Chữ `A`: 1 unit; 🚀: 2 units |
| **Unicode code point** | Giá trị dạng `U+XXXX` hoặc `U+XXXXX/XXXXXX` | 🚀 là một code point `U+1F680` |
| **Grapheme cluster** (ký tự hiển thị) | Cụm được người dùng cảm nhận như một ký tự | `e` + dấu sắc kết hợp có thể hiển thị như một chữ é |

UTF-16 biểu diễn các code point từ **U+0000 đến U+FFFF** (Basic Multilingual Plane — BMP), trừ vùng surrogate, bằng **một code unit**. Code point **U+10000 đến U+10FFFF** được biểu diễn bằng **cặp hai code unit** (*surrogate pair*).

Công thức dành cho code point `cp` trong khoảng U+10000…U+10FFFF:

~~~text
v = cp - 0x10000
high = 0xD800 + (v >> 10)
low  = 0xDC00 + (v & 0x3FF)
~~~

Không cần tự viết phép tính trên khi làm việc bình thường: Java có API `Character.toChars(int codePoint)` và `String.codePointAt(int index)`.

### Các API nên chọn

| Muốn làm gì? | API / cách viết | Trả về |
| --- | --- | --- |
| Lấy số đơn vị mã UTF-16 của chuỗi | `text.length()` | Số code unit |
| Đọc một đơn vị mã | `text.charAt(i)` | `char`, có thể là surrogate |
| Đọc code point bắt đầu tại vị trí đơn vị mã | `text.codePointAt(i)` | `int` chứa code point |
| Đếm code point trong chuỗi | `text.codePointCount(0, text.length())` | Số code point |
| Chuyển code point thành UTF-16 | `Character.toChars(cp)` | Mảng `char[]` gồm 1 hoặc 2 phần tử |
| Duyệt code point | `text.codePoints()` | `IntStream` các code point |

**Quan trọng:** Chỉ số của `charAt` và `codePointAt` vẫn là **vị trí code unit UTF-16**, không phải chỉ số code point. Nếu cần đi qua chuỗi có emoji, dùng `codePoints()` hoặc `offsetByCodePoints(...)` để tránh tách đôi một surrogate pair.

`codePointCount` không có nghĩa là đếm đúng số *grapheme cluster*: một ký tự nhìn thấy có thể chứa nhiều code point (dấu kết hợp, các chuỗi emoji ghép). Nếu giao diện cần đếm cụm ký tự, phải chọn thuật toán phân đoạn văn bản phù hợp với yêu cầu sản phẩm.

## 4. Những lỗi dễ gặp

| Mã / suy nghĩ | Kết quả | Cách hiểu đúng |
| --- | --- | --- |
| `char c = 'A';` | Hợp lệ | Một code unit |
| `char c = 65;` | Hợp lệ | Hằng `int` trong miền `char` có thể gán khi khai báo |
| `char c = -1;` | Lỗi biên dịch | Ngoài miền 0–65.535 |
| `char c = 65536;` | Lỗi biên dịch | Vượt `Character.MAX_VALUE` |
| `char c = (char) -1;` | Hợp lệ, giá trị 65.535 | Ép kiểu lấy 16 bit thấp |
| `char c = 'AB';` | Lỗi biên dịch | Literal ký tự không chứa hai code unit |
| `char c = '🚀';` | Lỗi biên dịch | Code point này cần hai code unit |
| `char c = '\uD83D';` | Hợp lệ về cú pháp | Chỉ là **một high surrogate**, không phải toàn bộ 🚀 |
| `String s = "🚀";` | Hợp lệ | `s.length()` bằng 2 |
| `text.length()` bằng số ký tự nhìn thấy | Không luôn đúng | `length()` đếm code unit |

Vì `char` là một kiểu số nguyên nguyên thủy trong phép toán, kết quả của phép cộng/trừ trên `char` thường có kiểu `int`:

~~~java
char c = 'A';
int nextCode = c + 1;     // 66.
char nextChar = (char) (c + 1); // 'B'.
~~~

Không ép kiểu một cách vô thức nếu phép tính có thể vượt miền hoặc chia cắt surrogate pair.

### `char` khác gì `String`?

`'A'` là `char`, còn `"A"` là `String`. `String` có thể dài 0, 1 hoặc nhiều UTF-16 code unit; `char` luôn đúng **một** code unit. Bạn không thể gọi `.length()` trên `char` và không thể đặt một emoji ngoài BMP vào literal `char` duy nhất.

## 5. Bài tập

1. **Dự đoán:** `(int) 'A'` và `'A' + 2` cho kết quả gì?  
   *Đáp án:* 65 và 67.
2. **Giới hạn:** Vì sao `char c = 65535;` được phép nhưng `char c = 65536;` không?  
   *Đáp án:* `char` chỉ chứa 16 bit không dấu, tối đa 65.535.
3. **Emoji:** Vì sao `"🚀".length()` bằng 2 và `codePointCount` bằng 1?  
   *Đáp án:* U+1F680 được mã hóa bằng một surrogate pair, gồm hai code unit.
4. **Duyệt văn bản:** Để lấy một Unicode code point có thể nằm ngoài BMP, chọn `charAt` hay `codePointAt`?  
   *Đáp án:* `codePointAt` (với chỉ số code unit hợp lệ).
5. **Dấu kết hợp:** Một chuỗi hiển thị như một chữ nhưng có hai code point thì `codePointCount` chắc chắn trả 1 không?  
   *Đáp án:* Không; ví dụ `"e\u0301"` có hai code point.

## Checklist ghi nhớ

- [ ] `char` là **16-bit unsigned UTF-16 code unit**, miền 0–65.535.
- [ ] `char` khác Unicode code point và khác grapheme cluster.
- [ ] Surrogate pair tạo từ **hai `char`** có thể biểu diễn một code point ngoài BMP.
- [ ] `String.length()` đếm UTF-16 code unit, không mặc định đếm ký tự nhìn thấy.
- [ ] Phép toán với `char` thường nâng thành `int`; thu hẹp về `char` có thể mất thông tin.
- [ ] Biết dùng `Character.toChars`, `String.codePointAt` và `codePointCount` khi thao tác Unicode.

**Kết luận:** Khi cần lưu **một đơn vị mã UTF-16**, `char` là lựa chọn chính xác. Khi cần lưu **một Unicode code point bất kỳ**, dùng `int` kèm các API Unicode của `Character`; khi cần xử lý **văn bản**, dùng `String` và tránh giả định “một `char` = một ký tự mà mắt thấy”.
