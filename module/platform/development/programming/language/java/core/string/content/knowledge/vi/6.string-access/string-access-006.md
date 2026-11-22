# `String.getChars()`: sao chép một vùng của chuỗi sang `char[]`

## 1. Mục tiêu

`String.getChars(int srcBegin, int srcEnd, char[] dst, int dstBegin)` sao chép **một vùng liên tiếp của `String` vào mảng ký tự `char[]` do người gọi cung cấp**. API hữu ích khi bạn cần đưa một phần văn bản vào bộ đệm có sẵn, giữ nguyên phần khác của bộ đệm, hoặc tích hợp với một API nhận `char[]`.

Điểm quan trọng nhất: các chỉ số của `String` và độ dài vùng sao chép được tính bằng **UTF-16 code unit** (`char`), không phải bằng số Unicode code point hay số ký tự người dùng nhìn thấy. Cần biết điều này để không vô tình chia đôi một ký tự ngoài BMP như `🚀`.

Sau bài này, bạn sẽ biết:
- Ý nghĩa chính xác của bốn tham số và ranh giới **`[srcBegin, srcEnd)`**.
- Cách kiểm tra vùng nguồn, vị trí đích và dung lượng mảng.
- Vì sao `getChars` có thể sao chép *một nửa surrogate pair*.
- Cách sao chép theo ranh giới code point một cách có chủ đích.
- Khi nào nên dùng `getChars` thay vì `toCharArray()`, `substring()` hoặc `getBytes()`.

## 2. Cú pháp và cơ chế

Phương thức trên đối tượng `String`:

```java
public void getChars(int srcBegin, int srcEnd,
                     char[] dst, int dstBegin)
```

Ví dụ ngắn:

```java
String source = "Java Core";
char[] buffer = {'_', '_', '_', '_', '_', '_', '_', '_'};

source.getChars(0, 4, buffer, 2);
System.out.println(new String(buffer)); // "__Java__"
```

Giải thích:
1. Từ chuỗi nguồn `"Java Core"`, lấy vùng **`[0, 4)`**, tức bốn code unit `J`, `a`, `v`, `a`.
2. Ghi bắt đầu ở phần tử **`buffer[2]`**. Các phần tử `buffer[2]` đến `buffer[5]` được thay bằng `J`, `a`, `v`, `a`.
3. Các phần tử `buffer[0]`, `buffer[1]`, `buffer[6]`, `buffer[7]` giữ nguyên dấu `_`.
4. Phương thức trả về **`void`**: nó **sửa nội dung mảng đích**; không trả về một mảng mới và không sửa `String` nguồn.

### Ý nghĩa bốn tham số

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `srcBegin` | Chỉ số UTF-16 đầu tiên trong chuỗi nguồn, **bao gồm**. | `0` lấy từ đầu chuỗi. |
| `srcEnd` | Chỉ số UTF-16 ngay sau phần cuối cần lấy, **không bao gồm**. | `4` lấy đến trước vị trí 4. |
| `dst` | Mảng `char[]` đích đã tồn tại; các phần tử được ghi đè trong vùng nhận. | `buffer` |
| `dstBegin` | Chỉ số trong mảng đích để bắt đầu ghi. | `2` ghi từ `buffer[2]`. |

Số phần tử được sao chép là:

\[
n = \text{srcEnd} - \text{srcBegin}
\]

Với `i` chạy từ `0` đến `n - 1`, hiệu ứng tương đương về mặt nội dung:

```java
dst[dstBegin + i] = source.charAt(srcBegin + i);
```

Đây là diễn giải thao tác, **không phải** yêu cầu phải tự viết vòng lặp. Dùng trực tiếp `getChars` giúp thể hiện rõ ý định sao chép một vùng.

## 3. Chỉ số đầu/cuối và vị trí đích

Hãy nhìn vào ví dụ `"Java Core"` theo từng vị trí `char`:

| Chỉ số UTF-16 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ký tự | J | a | v | a | dấu cách | C | o | r | e |

Gọi `source.getChars(5, 9, buffer, 0)` sẽ lấy **`"Core"`** bởi `srcEnd = 9` là ranh giới **sau** chữ `e`. Với nguồn dài `9`, `srcEnd == source.length()` hoàn toàn hợp lệ.

### Những trường hợp biên thường gặp

- `source.getChars(0, source.length(), dst, 0)`: sao chép toàn bộ chuỗi, với điều kiện `dst` có đủ chỗ.
- `source.getChars(2, 2, dst, 0)`: vùng nguồn rỗng, **không ghi ký tự nào**.
- `source.getChars(source.length(), source.length(), dst, dst.length)`: vùng rỗng tại cuối chuỗi và cuối mảng cũng hợp lệ.
- `source.getChars(2, 5, dst, 4)`: sao chép `3` `char` vào các vị trí đích `4, 5, 6`; mảng đích phải có tối thiểu `7` phần tử.

Đừng nhầm `srcEnd` là số phần tử cần sao chép. Nếu muốn sao chép `count` phần tử bắt đầu từ `start`, dùng `srcBegin = start` và `srcEnd = start + count`, sau khi kiểm tra phạm vi.

## 4. Điều kiện hợp lệ và ngoại lệ

Với `int n = srcEnd - srcBegin`, các điều kiện về chỉ số là:

```text
0 <= srcBegin <= srcEnd <= source.length()
0 <= dstBegin <= dst.length
n <= dst.length - dstBegin
```

Trong đó, `n` được tính theo số **`char` UTF-16** cần ghi. Điều kiện cuối tránh ghi vượt kích thước mảng đích.

| Tình huống | Ví dụ | Kết quả |
| --- | --- | --- |
| Vùng nguồn hợp lệ | `"abc".getChars(0, 2, new char[2], 0)` | Sao chép `a`, `b`. |
| `srcBegin` âm | `"abc".getChars(-1, 2, new char[3], 0)` | `IndexOutOfBoundsException`. |
| `srcBegin > srcEnd` | `"abc".getChars(2, 1, new char[3], 0)` | `IndexOutOfBoundsException`. |
| `srcEnd` vượt độ dài | `"abc".getChars(0, 4, new char[4], 0)` | `IndexOutOfBoundsException`. |
| `dstBegin` âm | `"abc".getChars(0, 1, new char[3], -1)` | `IndexOutOfBoundsException`. |
| Thiếu chỗ ở đích | `"abc".getChars(0, 3, new char[3], 1)` | `IndexOutOfBoundsException`. |
| Mảng đích `null` | `"abc".getChars(0, 1, null, 0)` | `NullPointerException`. |
| Sao chép rỗng | `"abc".getChars(3, 3, new char[0], 0)` | Không sao chép; hợp lệ. |

Khi **nhiều điều kiện cùng sai**, không nên dựa vào thông báo ngoại lệ cụ thể hoặc thứ tự kiểm tra nội bộ. Tài liệu API nêu hợp đồng; chương trình của bạn nên xác thực cả giới hạn vùng nguồn và dung lượng đích.

Lưu ý: nếu tính `start + count` từ dữ liệu nguyên rất lớn, phép cộng kiểu `int` có thể tràn. Có thể kiểm tra không tràn bằng `Objects.checkFromIndexSize(start, count, source.length())` (Java 9+) trước khi tính ranh giới, rồi kiểm tra vùng đích tương tự.

## 5. Chương trình Java 17+ chạy độc lập

Lưu mã sau vào file `GetCharsDemo.java`:

```java
import java.util.Arrays;

public class GetCharsDemo {
    public static void main(String[] args) {
        String text = "A🚀B";
        char[] target = {'_', '_', '_', '_', '_', '_'};

        // Chép toàn bộ emoji, gồm hai code unit UTF-16.
        text.getChars(1, 3, target, 2);

        System.out.println("original = " + text);
        System.out.println("length = " + text.length());
        System.out.println("copied = [" + new String(target) + "]");
        System.out.println("target length = " + target.length);
        System.out.printf("dst[2] = U+%04X%n", (int) target[2]);
        System.out.printf("dst[3] = U+%04X%n", (int) target[3]);

        // Một vùng không an toàn: chỉ chép high surrogate.
        char[] partial = new char[1];
        text.getChars(1, 2, partial, 0);
        System.out.println("partial high surrogate = "
                + Character.isHighSurrogate(partial[0]));

        // Khoảng rỗng không thay đổi mảng đích.
        char[] unchanged = {'?', '?', '?'};
        text.getChars(2, 2, unchanged, 1);
        System.out.println("empty region = "
                + Arrays.toString(unchanged));
    }
}
```

Biên dịch và chạy trong terminal hỗ trợ Unicode:

```bash
javac -encoding UTF-8 GetCharsDemo.java
java GetCharsDemo
```

Đầu ra kỳ vọng:

```text
original = A🚀B
length = 4
copied = [__🚀__]
target length = 6
dst[2] = U+D83D
dst[3] = U+DE80
partial high surrogate = true
empty region = [?, ?, ?]
```

**Vì sao kết quả như vậy?**
- Chuỗi hiển thị là `A🚀B`, nhưng `length() == 4` vì emoji `🚀` là code point `U+1F680`, có hai code unit UTF-16: **high surrogate `U+D83D`** ở chỉ số `1` và **low surrogate `U+DE80`** ở chỉ số `2`.
- `getChars(1, 3, target, 2)` lấy vùng `[1, 3)`, tức **hai `char`** của emoji, đặt vào `target[2]` và `target[3]`. Hai dấu gạch dưới đầu và hai dấu gạch dưới cuối vẫn nguyên vẹn.
- `getChars(1, 2, partial, 0)` chỉ lấy **high surrogate**. Phương thức sao chép theo code unit nên không tự ghép hoặc bổ sung low surrogate còn thiếu.
- Khi `srcBegin == srcEnd`, số phần tử sao chép là `0`; `unchanged` vẫn giữ ba dấu hỏi.

Chương trình cố ý kiểm tra code unit bằng `%04X` thay vì in riêng từng nửa surrogate, vì một surrogate đơn lẻ có thể hiển thị như ký tự thay thế hoặc dấu hỏi tùy môi trường.

## 6. `getChars` sao chép `char`, không tự sao chép theo code point

Để hiểu quy tắc chỉ số, xét chuỗi `"A🚀B"`:

| UTF-16 index | `0` | `1` | `2` | `3` |
| --- | --- | --- | --- | --- |
| `charAt(index)` | `'A'` | `'\uD83D'` | `'\uDE80'` | `'B'` |

Ranh giới code point đầy đủ là `0, 1, 3, 4`. Vị trí `2` nằm **giữa** surrogate pair của emoji.

`String.getChars` **không xác thực ranh giới surrogate pair** và không có chế độ tự dịch chỉ số code point:

```java
String text = "A🚀B";

char[] correct = new char[2];
text.getChars(1, 3, correct, 0); // Cả hai char của 🚀.

char[] broken = new char[1];
text.getChars(1, 2, broken, 0); // Chỉ high surrogate.
```

Bởi vậy:
- Dùng chỉ số trực tiếp nếu mục tiêu thực sự là **UTF-16 code unit**.
- Nếu mục tiêu là **Unicode code point**, trước tiên tính ra ranh giới UTF-16 đúng.
- Nếu mục tiêu là một **ký tự hiển thị** (grapheme cluster) gồm nhiều code point, thao tác theo code point vẫn có thể tách cụm; cần quy tắc phân đoạn văn bản phù hợp.

### Chuyển khoảng code point thành khoảng UTF-16 rồi mới gọi `getChars`

Đoạn sau là một **phương thức hỗ trợ** đặt trong lớp Java:

```java
static char[] copyCodePoints(String text, int from, int count) {
    java.util.Objects.requireNonNull(text, "text");

    int total = text.codePointCount(0, text.length());
    java.util.Objects.checkFromIndexSize(from, count, total);

    int startUtf16 = text.offsetByCodePoints(0, from);
    int endUtf16 = text.offsetByCodePoints(startUtf16, count);

    char[] result = new char[endUtf16 - startUtf16];
    text.getChars(startUtf16, endUtf16, result, 0);
    return result;
}
```

Ví dụ gọi từ một `main`:

```java
String text = "A🚀B";
char[] rocket = copyCodePoints(text, 1, 1);
System.out.println(new String(rocket)); // 🚀
System.out.println(rocket.length);       // 2
```

Giải thích: `from = 1` bắt đầu tại code point thứ hai (`🚀`). `offsetByCodePoints` đổi vị trí code point sang chỉ số UTF-16: đầu `1`, cuối `3`. Mảng cần `3 - 1 = 2` `char` để giữ trọn emoji.

**Giới hạn:** `codePointCount` và `offsetByCodePoints` xem surrogate đơn lẻ có trong chuỗi là một code point theo cách xử lý của `String`. Chúng không tự sửa văn bản Unicode vốn đã có surrogate không ghép cặp và cũng không phân đoạn grapheme cluster.

## 7. Bộ đệm đích: ghi đè đúng vùng, phần khác giữ nguyên

`getChars` có lợi khi bạn cần tái sử dụng một mảng hoặc tạo thông điệp gồm nhiều phần. Ví dụ:

```java
String source = "học Java";
char[] destination = "........".toCharArray();

source.getChars(4, 8, destination, 2);
System.out.println(new String(destination)); // "..Java.."
```

Mảng đích ban đầu gồm tám dấu chấm. Bốn code unit của `"Java"` ghi vào các ô `2, 3, 4, 5`; các ô khác không bị ghi đè.

Để tránh lỗi khi tái sử dụng:
1. Tính `n = srcEnd - srcBegin` (sau khi kiểm tra chỉ số hợp lệ).
2. Bảo đảm `dstBegin + n` không vượt `dst.length` (có thể kiểm tra bằng `n <= dst.length - dstBegin` để tránh tràn số).
3. Theo dõi riêng **độ dài dữ liệu thật** đang nằm trong buffer. `new String(dst)` tạo chuỗi từ **toàn bộ** mảng, kể cả `char` chưa ghi (`'\u0000'` trong mảng vừa tạo bằng `new char[size]`).
4. Nếu chỉ muốn chuyển phần vừa ghi thành `String`, dùng `new String(dst, dstBegin, n)` hoặc quản lý các đoạn hợp lệ theo nhu cầu.

Ví dụ:

```java
char[] buffer = new char[10];
String text = "Hello";
text.getChars(0, text.length(), buffer, 3);

String copiedOnly = new String(buffer, 3, text.length());
System.out.println(copiedOnly); // Hello
```

`new String(buffer, 3, 5)` lấy đúng năm code unit đã ghi vào mảng. Trái lại, `new String(buffer)` sẽ chứa cả những phần tử `'\u0000'` chưa được ghi; chúng thường không hiển thị rõ trên console.

Mảng `char[]` **mutable**. Nếu nhiều luồng cùng viết vào cùng mảng, các luồng cần đồng bộ hoặc phân chia vùng không xung đột và kiểm soát việc công bố/kết hợp dữ liệu. Việc `String` nguồn bất biến **không** làm cho bộ đệm đích an toàn đa luồng.

## 8. So sánh với các API thường dùng

| API | Đầu ra hoặc tác động | Khi nên dùng |
| --- | --- | --- |
| `text.getChars(begin, end, dst, dstBegin)` | Ghi `end - begin` code unit vào mảng **có sẵn**; trả `void`. | Cần sao chép một vùng vào buffer tại vị trí xác định. |
| `text.toCharArray()` | Trả về `char[]` **mới** chứa toàn bộ code unit UTF-16 của chuỗi. | Muốn một bản mảng của toàn bộ chuỗi. |
| `text.substring(begin, end)` | Trả về một `String` chứa vùng chỉ định theo chỉ số UTF-16. | Muốn tiếp tục xử lý kết quả dạng `String`. |
| `text.getBytes(StandardCharsets.UTF_8)` | Trả về `byte[]` với dữ liệu **đã mã hóa UTF-8**. | Ghi file/gửi dữ liệu byte với charset được chỉ định. |
| `text.codePoints().toArray()` | Trả về `int[]` theo code point (kết hợp surrogate pair hợp lệ). | Cần giá trị code point thay vì các đơn vị `char`. |

Ví dụ đối chiếu:

```java
String text = "A🚀B";

char[] chars = text.toCharArray(); // 4 char UTF-16.
int[] points = text.codePoints().toArray(); // 3 code point.

System.out.println(chars.length);  // 4
System.out.println(points.length); // 3
```

Đừng dùng `getChars` để “giải mã UTF-8”: nó không nhận `byte[]` và cũng không thực hiện chuyển đổi charset. Đối với byte, hãy sử dụng API mã hóa/giải mã thích hợp.

Về hiệu năng, `getChars` tránh yêu cầu tạo một `char[]` mới **nếu bạn đã có mảng đích**. Nó không bảo đảm lúc nào cũng nhanh hơn các API khác; nên chọn theo yêu cầu về kiểu kết quả, phân bổ bộ nhớ, khả năng bảo trì và đo hiệu năng trong bối cảnh thực tế.

## 9. Lỗi phổ biến và cách khắc phục

**Lỗi 1: Nhầm `srcEnd` với số lượng.**

```java
String text = "abcdef";
char[] dst = new char[3];
text.getChars(2, 5, dst, 0); // Đúng: "cde", 3 char.
```

`srcEnd = 5` là **chỉ số cuối loại trừ**; số lượng bằng `5 - 2 = 3`, không phải `5`.

**Lỗi 2: Tạo mảng nhỏ hơn đoạn cần chép.**

```java
String text = "Hello";
char[] tooSmall = new char[3];
// text.getChars(0, 5, tooSmall, 0); // IndexOutOfBoundsException.
```

Mảng cần ít nhất **5 phần tử trống** từ `dstBegin = 0` để chứa cả `"Hello"`.

**Lỗi 3: Dùng số code point làm số `char`.**

```java
String text = "A🚀B";
int pointCount = text.codePointCount(0, text.length()); // 3
char[] tooShortForWholeString = new char[pointCount];  // 3
// text.getChars(0, text.length(), tooShortForWholeString, 0);
// Không đủ: đoạn nguồn có 4 code unit.
```

Nếu chép toàn chuỗi, mảng cần `text.length()` phần tử, **không nhất thiết bằng** `codePointCount`.

**Lỗi 4: Cắt đôi surrogate pair.**

```java
String text = "A🚀B";
char[] half = new char[1];
text.getChars(1, 2, half, 0); // Chỉ high surrogate.
```

Nếu muốn trọn một code point ngoài BMP, phải xác định khoảng UTF-16 bao gồm cả high và low surrogate, chẳng hạn `[1, 3)` trong ví dụ.

**Lỗi 5: In toàn bộ mảng đích rồi hiểu nhầm phần chưa ghi.**

`new char[10]` chứa mười ký tự `'\u0000'` trước khi gán giá trị. Nếu chỉ chép ba code unit, các phần tử còn lại không tự biến mất. Lưu số ký tự hợp lệ hoặc tạo chuỗi từ đúng đoạn dữ liệu đã ghi bằng `new String(dst, offset, count)`.

**Lỗi 6: Giả định nội dung `String` bị thay đổi.**

`getChars` ghi vào **mảng đích**. Ghi đè một phần tử của `dst` sau đó cũng không làm thay đổi `String` đã dùng làm nguồn hoặc chuỗi mới đã được tạo độc lập từ mảng.

## 10. Bài tập tự kiểm tra

### Bài 1: Dự đoán vùng đích

```java
String text = "abcdef";
char[] out = {'-', '-', '-', '-', '-', '-'};
text.getChars(1, 4, out, 2);
System.out.println(new String(out));
```

**Đáp án:** `"--bcd-"`. Nguồn `[1, 4)` lấy `"bcd"` (3 `char`), ghi vào các phần tử `2..4`; hai phần tử đầu và phần tử cuối vẫn là `'-'`.

### Bài 2: Sao chép chuỗi có emoji

```java
String text = "Hi😀!";
char[] out = new char[2];
text.getChars(2, 4, out, 0);
System.out.println(new String(out));
```

**Đáp án:** `"😀"`. Emoji `😀` chiếm hai `char` UTF-16 ở vị trí `2` và `3`, nên vùng `[2, 4)` lấy trọn.

### Bài 3: Đủ dung lượng hay không?

```java
String text = "Hello";
char[] out = new char[5];
text.getChars(1, 5, out, 2);
```

**Đáp án:** Không đủ. Cần chép `4` code unit bắt đầu từ `dstBegin = 2`, tức cần vị trí đích `2, 3, 4, 5`, nhưng mảng dài `5` chỉ có các vị trí `0..4`. Lời gọi ném `IndexOutOfBoundsException`.

### Bài 4: Sao chép rỗng

```java
char[] out = {'x', 'y'};
"abc".getChars(3, 3, out, 2);
System.out.println(java.util.Arrays.toString(out));
```

**Đáp án:** `[x, y]`. Cả vị trí nguồn `3` và vị trí đích `2` là ranh giới hợp lệ tại cuối; số phần tử cần chép bằng `0`.

### Bài 5: Chép theo code point

Cho `String text = "A🚀B";`. Muốn chép **code point thứ hai** (đếm từ 1) vào `char[]` mà không viết cứng chỉ số UTF-16 thì làm gì?

**Đáp án:** Lấy `int from = text.offsetByCodePoints(0, 1);`, `int to = text.offsetByCodePoints(from, 1);`, cấp phát `char[] out = new char[to - from];` rồi gọi `text.getChars(from, to, out, 0);`. Kết quả là mảng dài `2` lưu cả hai đơn vị của `🚀`.

## 11. Ghi nhớ

- `getChars(srcBegin, srcEnd, dst, dstBegin)` sao chép **`srcEnd - srcBegin` code unit UTF-16** vào mảng đã có.
- Đoạn nguồn là **`[srcBegin, srcEnd)`**: có đầu, không có cuối.
- Việc ghi bắt đầu tại `dst[dstBegin]`; phần đích nằm ngoài đoạn ghi không bị thay đổi.
- Phương thức trả `void`, sửa `char[]` đích và **không làm thay đổi `String` nguồn**.
- Kiểm tra cả **giới hạn nguồn** lẫn **dung lượng đích**; vùng rỗng là hợp lệ nếu chỉ số hợp lệ.
- Với ký tự ngoài BMP, một code point có thể chiếm **hai `char`**. Nếu xử lý theo code point, chuyển ranh giới bằng `offsetByCodePoints` trước khi sao chép.

## Tài liệu tham khảo

- [Java SE 17 — `String.getChars(int, int, char[], int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#getChars(int,int,char%5B%5D,int))
- [Java SE 17 — `String`, các phương thức `length` và `offsetByCodePoints`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character` và UTF-16 surrogate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
