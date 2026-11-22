# Tạo `String` từ mảng code point trong Java

## 1. Mục tiêu

Khi dữ liệu văn bản được biểu diễn dưới dạng các giá trị Unicode code point (`int[]`), Java cho phép tạo trực tiếp một `String` bằng constructor `String(int[] codePoints, int offset, int count)`. Cách này đặc biệt hữu ích khi xử lý ký tự ngoài Basic Multilingual Plane (BMP), ví dụ nhiều emoji, mà không cần tự ghép các cặp `char` của UTF-16.

Sau bài này, bạn có thể:
- Phân biệt **Unicode code point**, **UTF-16 code unit (`char`)** và độ dài `String`.
- Tạo chuỗi từ toàn bộ hoặc một đoạn của `int[]`.
- Hiểu ý nghĩa và giới hạn của `offset` / `count`, các lỗi có thể xảy ra và cách kiểm tra đầu vào.
- Chuyển đổi hai chiều giữa `String` và mảng code point khi cần.

## 2. Code point khác `char` như thế nào?

Một **Unicode code point** là giá trị nguyên dùng để định danh một vị trí mã Unicode, thường viết dạng `U+XXXX` hoặc `U+XXXXX`, ví dụ:

| Ký tự | Code point | Giá trị `int` trong Java | Số `char` UTF-16 |
| --- | --- | --- | --- |
| `A` | `U+0041` | `0x0041` | 1 |
| `ế` (dạng dựng sẵn) | `U+1EBF` | `0x1EBF` | 1 |
| `🚀` | `U+1F680` | `0x1F680` | 2 |
| `😀` | `U+1F600` | `0x1F600` | 2 |

Java sử dụng **UTF-16** cho các thao tác theo chỉ số `char` của `String`. Một `char` là một *code unit* 16 bit:
- Code point thuộc BMP (từ `U+0000` đến `U+FFFF`) thường chiếm một code unit. Riêng vùng surrogate `U+D800..U+DFFF` không phải ký tự Unicode độc lập.
- Code point bổ sung (từ `U+10000` đến `U+10FFFF`) cần **hai** code unit, gọi là *surrogate pair*.
- Vì vậy `String.length()` đếm `char` UTF-16, **không phải** số code point và cũng không phải số ký tự người dùng cảm nhận. Một cụm chữ có dấu kết hợp hoặc emoji ghép có thể gồm nhiều code point.

Ví dụ mảng `{0x0041, 0x1F680, 0x0042}` chứa **3 code point** tạo thành `A🚀B`, nhưng `"A🚀B".length()` bằng **4**.

## 3. Constructor `String(int[] codePoints, int offset, int count)`

Cú pháp:

```java
String text = new String(codePoints, offset, count);
```

| Tham số | Ý nghĩa |
| --- | --- |
| `codePoints` | Mảng `int[]` lưu các giá trị Unicode code point theo thứ tự mong muốn. |
| `offset` | Chỉ số **phần tử đầu tiên** được lấy trong `codePoints` (đếm từ 0). |
| `count` | **Số phần tử `int`** cần lấy, không phải chỉ số cuối và không phải số `char` UTF-16. |

Constructor chuyển từng phần tử của đoạn `codePoints[offset .. offset + count)` sang biểu diễn chuỗi. Với code point bổ sung như `0x1F680`, Java tự sinh surrogate pair tương ứng.

Để dùng cả mảng:

```java
int[] points = {0x0048, 0x0069, 0x0021};
String greeting = new String(points, 0, points.length); // "Hi!"
```

Không có constructor `new String(int[])`; phải truyền đủ ba đối số. Điều kiện về chỉ số là `offset >= 0`, `count >= 0` và `offset + count <= codePoints.length`. Với `count == 0` và vị trí hợp lệ, kết quả là chuỗi rỗng. Mảng nguồn được chuyển thành nội dung chuỗi tại thời điểm tạo; thay đổi `int[]` sau đó không làm đổi `String`.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu đoạn sau vào file `CodePointStringDemo.java`:

```java
public class CodePointStringDemo {
    public static void main(String[] args) {
        // H, i, khoảng trắng, rocket, dấu chấm than.
        int[] points = {0x0048, 0x0069, 0x0020, 0x1F680, 0x0021};
        String text = new String(points, 0, points.length);

        System.out.println(text);
        System.out.println("length() = " + text.length());
        System.out.println("codePointCount() = "
                + text.codePointCount(0, text.length()));
        System.out.printf("codePointAt(3) = U+%X%n", text.codePointAt(3));

        // Bỏ hai dấu sao đầu/cuối; chọn 5 code point từ vị trí 1.
        int[] padded = {0x2605, 0x004A, 0x0061, 0x0076, 0x0061, 0x1F680, 0x2605};
        String selected = new String(padded, 1, 5);
        System.out.println("selected = " + selected);

        padded[1] = 0x0058; // Đổi 'J' trong mảng thành 'X'.
        System.out.println("after array change = " + selected);

        System.out.println("empty = [" + new String(points, 0, 0) + "]");
    }
}
```

Biên dịch và chạy (terminal hỗ trợ Unicode):

```bash
javac -encoding UTF-8 CodePointStringDemo.java
java CodePointStringDemo
```

Kết quả chuẩn:

```text
Hi 🚀!
length() = 6
codePointCount() = 5
codePointAt(3) = U+1F680
selected = Java🚀
after array change = Java🚀
empty = []
```

**Giải thích:**
1. `points` có 5 phần tử, nhưng `🚀` chiếm 2 code unit UTF-16: `text.length() == 6` trong khi `text.codePointCount(0, text.length()) == 5`.
2. `codePointAt(3)` nhận **chỉ số `char`**, tại vị trí 3 bắt đầu surrogate pair của `🚀`, nên trả về `0x1F680`. Không nhầm chỉ số của `String` với chỉ số trong `int[]`.
3. `new String(padded, 1, 5)` lấy 5 code point ở các chỉ số 1, 2, 3, 4, 5, thu được `Java🚀`; dấu `★` ở đầu/cuối bị loại.
4. Kết quả không đổi sau khi sửa mảng vì `String` là bất biến và constructor không giữ mảng `int[]` làm dữ liệu sống.

## 5. Xử lý code point và chỉ số đúng cách

Một vài API liên quan:

| API | Tác dụng |
| --- | --- |
| `text.length()` | Số code unit UTF-16. |
| `text.codePointCount(0, text.length())` | Số code point trong chuỗi (surrogate đơn lẻ cũng được tính riêng). |
| `text.codePointAt(charIndex)` | Lấy code point bắt đầu tại một chỉ số UTF-16. |
| `text.offsetByCodePoints(charIndex, delta)` | Di chuyển theo số code point và trả về chỉ số UTF-16 mới. |
| `text.codePoints().toArray()` | Lấy `int[]` code point từ `String`. |
| `Character.toChars(codePoint)` | Chuyển một code point thành một hoặc hai `char`. |
| `StringBuilder.appendCodePoint(codePoint)` | Nối từng code point khi xây dựng chuỗi dần dần. |

Ví dụ chuyển đổi hai chiều:

```java
String original = "A🚀B";
int[] cps = original.codePoints().toArray();
String copy = new String(cps, 0, cps.length);

System.out.println(java.util.Arrays.toString(cps));
System.out.println(copy.equals(original));
System.out.println(copy.length() + " / " + cps.length);
```

Kết quả của đoạn minh họa khi chạy bên trong một phương thức (ví dụ `main`):

```text
[65, 128640, 66]
true
4 / 3
```

`String.codePoints()` cung cấp `IntStream`. Không sử dụng vòng lặp `for (char c : text.toCharArray())` nếu yêu cầu xử lý từng code point: vòng lặp đó có thể tách một ký tự bổ sung thành hai surrogate code unit.

Nếu cần cắt theo **số code point** của một chuỗi đang có, hãy chuyển vị trí đầu/cuối bằng `offsetByCodePoints` rồi dùng `substring`; các đối số của `substring` vẫn là chỉ số UTF-16. Còn `offset` và `count` trong constructor nhận `int[]` thì trực tiếp đếm phần tử của mảng.

## 6. Kiểm tra dữ liệu và lỗi thường gặp

Các tình huống với constructor:

| Đầu vào | Hành vi |
| --- | --- |
| `new String(new int[]{0x41}, 0, 1)` | `"A"`. |
| `new String(new int[]{0x41}, 1, 0)` | Chuỗi rỗng; `offset == length` được phép khi `count == 0`. |
| `new String(new int[]{0x41}, 0, 2)` | `IndexOutOfBoundsException`: vượt phạm vi mảng. |
| `new String(new int[]{0x41}, -1, 1)` | `IndexOutOfBoundsException`: `offset` âm. |
| `new String(new int[]{0x110000}, 0, 1)` | `IllegalArgumentException`: vượt code point tối đa `U+10FFFF`. |
| `new String((int[]) null, 0, 0)` | `NullPointerException` khi mảng code point là `null`. |

Lời gọi `new String(null, 0, 0)` **không biên dịch** vì mơ hồ giữa các overload nhận `int[]`, `char[]` và `byte[]`; ép kiểu `(int[]) null` mới chọn constructor đang xét.

**Phân biệt code point hợp lệ theo Java với Unicode scalar value:** `Character.isValidCodePoint(cp)` kiểm tra `0 <= cp <= 0x10FFFF`, nên **cả giá trị surrogate** `0xD800..0xDFFF` cũng vượt qua phép kiểm tra phạm vi này. Một `String` Java có thể chứa surrogate đơn lẻ, nhưng đó không phải văn bản Unicode well-formed. Nếu đầu vào cần biểu diễn văn bản chuẩn để trao đổi/ghi ra ngoài, nên từ chối surrogate code point riêng lẻ.

Hàm tiện ích sau có thể dùng khi dữ liệu `int[]` đến từ nguồn không tin cậy và bạn muốn chỉ nhận Unicode scalar value. Đây là phương thức hỗ trợ, đặt bên trong một lớp Java:

```java
static String fromUnicodeScalars(int[] points, int offset, int count) {
    java.util.Objects.requireNonNull(points, "points");
    java.util.Objects.checkFromIndexSize(offset, count, points.length);

    for (int i = offset; i < offset + count; i++) {
        int cp = points[i];
        boolean surrogate = cp >= 0xD800 && cp <= 0xDFFF;
        if (!Character.isValidCodePoint(cp) || surrogate) {
            throw new IllegalArgumentException(
                    String.format("Invalid Unicode scalar: U+%X", cp));
        }
    }
    return new String(points, offset, count);
}
```

`Objects.checkFromIndexSize` kiểm tra đoạn chọn (Java 9+). Constructor cơ bản đã tự kiểm tra code point vượt phạm vi; phần kiểm tra bổ sung ở đây dành cho yêu cầu **không chấp nhận surrogate lẻ**.

Đừng lẫn `int[]` code point với `byte[]` UTF-8: nếu dữ liệu là byte được mã hóa, cần giải mã bằng charset rõ ràng, chẳng hạn `new String(bytes, java.nio.charset.StandardCharsets.UTF_8)`. Cũng đừng chuyển mọi code point sang `(char)`: phép ép kiểu sẽ cắt mất phần cao của giá trị lớn hơn `0xFFFF`.

## 7. Chọn giải pháp theo tình huống

- **Đã có `int[]` code point:** dùng `new String(points, offset, count)` trực tiếp; không cần tự tạo surrogate pair.
- **Có từng code point được sinh liên tục:** dùng `StringBuilder.appendCodePoint(cp)`, sau đó `toString()`, giúp tránh nối `String` nhiều lần trong vòng lặp.
- **Đang có một `String` và muốn thao tác từng code point:** dùng `codePoints()`, `codePointAt`, `codePointCount` và `offsetByCodePoints` khi phù hợp.
- **Đang có `char[]`:** `new String(chars)` nhận code unit UTF-16, khác ngữ nghĩa so với mảng `int[]` code point.
- **Dữ liệu là byte UTF-8/UTF-16:** giải mã bằng API charset, không coi mỗi byte là một code point.

Các lỗi tư duy phổ biến là cho rằng `count` là chỉ số cuối, tin rằng một code point luôn chiếm một `char`, dùng `length()` để đếm code point, hoặc giả định một code point luôn tương ứng một *ký tự hiển thị* (grapheme cluster). Ví dụ chữ `e` theo sau bởi dấu sắc kết hợp có thể là hai code point nhưng trông như một chữ; các emoji ghép cũng có thể chứa nhiều code point.

## 8. Tự kiểm tra kiến thức

Cho mảng:

```java
int[] cps = {0x0058, 0x0041, 0x1F600, 0x0042, 0x0059};
String s = new String(cps, 1, 3);
```

1. `s` bằng gì? **`A😀B`**, vì lấy các phần tử chỉ số 1, 2, 3.
2. `s.length()` bằng mấy? **4** code unit UTF-16, vì `😀` chiếm hai `char`.
3. `s.codePointCount(0, s.length())` bằng mấy? **3** code point.
4. Nếu sửa `cps[1] = 0x005A` sau đó, `s` có đổi không? **Không**, vì `String` đã được tạo độc lập với mảng nguồn.
5. `new String(cps, 3, 3)` có hợp lệ không? **Không**, vì cần ba phần tử từ chỉ số 3 trong mảng dài 5.

## Tài liệu tham khảo

- [Java SE 17 — `String(int[] codePoints, int offset, int count)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#%3Cinit%3E(int%5B%5D,int,int))
- [Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
