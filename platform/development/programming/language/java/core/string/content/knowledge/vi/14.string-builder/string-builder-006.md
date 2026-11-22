# `StringBuilder.setCharAt()` và `setLength()` trong Java

## 1. Mục tiêu bài học

`StringBuilder` là đối tượng chứa một dãy đơn vị ký tự UTF-16 **có thể thay đổi**. Khác với `String` bất biến, `StringBuilder` cho phép sửa trực tiếp nội dung đang tích lũy mà không cần gán lại đối tượng mỗi lần biến đổi.

Hai phương thức trong bài phục vụ hai nhiệm vụ khác nhau:

- `setCharAt(int index, char ch)`: **thay đúng một đơn vị `char`** tại vị trí đã tồn tại. Phương thức không thêm hoặc bớt ký tự nên **`length()` không đổi**.
- `setLength(int newLength)`: thay đổi **độ dài logic** của dãy. Nếu giảm, các ký tự cuối bị loại khỏi nội dung logic; nếu tăng, các vị trí mới được điền bằng **ký tự NUL `'\u0000'`**. Phương thức không tự điền khoảng trắng và không khôi phục các ký tự đã cắt trước đó.

Cả hai đều thay đổi chính đối tượng `StringBuilder` và có kiểu trả về `void`, không giống nhiều phương thức dạng `append`/`insert` trả lại builder để gọi nối tiếp.

Ví dụ nhìn nhanh:

```java
StringBuilder sb = new StringBuilder("Java");

sb.setCharAt(1, 'O'); // Nội dung: "JOva", length = 4.
sb.setLength(2);      // Nội dung: "JO", length = 2.
sb.setLength(5);      // Nội dung: "JO\0\0\0", length = 5.
```

Đây là đoạn mã minh họa trong thân một phương thức. `\0` trong phần bình luận và các ví dụ ký hiệu cho **một đơn vị UTF-16 có giá trị bằng 0**, không phải hai ký tự `\` và `0`.

## 2. Phân biệt `length` với `capacity` và vùng chỉ số hợp lệ

Một `StringBuilder` có hai đại lượng khác nhau:

| Khái niệm | API | Ý nghĩa |
| --- | --- | --- |
| **Độ dài logic** | `sb.length()` | Số đơn vị `char` đang thuộc nội dung của builder |
| **Dung lượng lưu trữ** | `sb.capacity()` | Số đơn vị `char` mà builder có thể chứa mà không nhất thiết cần tăng vùng lưu trữ |
| **Truy cập/sửa nội dung** | `sb.charAt(i)`, `sb.setCharAt(i,ch)` | Chỉ số phải thỏa **`0 <= i < length()`** |
| **Đổi độ dài logic** | `sb.setLength(n)` | `n >= 0`; có thể ngắn hơn hoặc dài hơn độ dài hiện tại |

Đừng lấy `capacity()` làm giới hạn hợp lệ của `setCharAt`. Ví dụ builder có `length() == 2` nhưng `capacity() == 18` thì chỉ số `2` **vẫn không hợp lệ** cho `setCharAt`, vì đó là vị trí *sau* nội dung hiện có. Muốn ghi vào chỉ số 2 bằng `setCharAt`, phải tăng `length` lên ít nhất 3 trước, hoặc dùng `append` để thêm dữ liệu như ý định.

`capacity()` là chi tiết năng lực lưu trữ được công khai bởi API, còn nội dung hợp lệ luôn được xác định theo `length()`. Khi tăng `length` vượt `capacity`, builder có thể phải cấp thêm dung lượng. Giảm `length` không có nghĩa dung lượng cũng bị giảm tương ứng; nếu muốn chủ động yêu cầu thu gọn, xem `trimToSize()`, nhưng đó là quyết định hiệu năng/bộ nhớ khác với ngữ nghĩa hai phương thức đang học.

## 3. `setCharAt(index, ch)`: sửa một phần tử, không thay đổi độ dài

Chữ ký:

```java
public void setCharAt(int index, char ch)
```

- `index`: vị trí của một **đơn vị mã UTF-16** đang nằm trong dãy, đánh số từ 0.
- `ch`: giá trị `char` mới ghi đè lên đơn vị đó.
- Kết quả trả về: **`void`**.
- Điều kiện chỉ số: `0 <= index < length()`. Vi phạm gây `IndexOutOfBoundsException` (một số triển khai dùng lớp con `StringIndexOutOfBoundsException`).

Ví dụ:

```java
StringBuilder name = new StringBuilder("Jovo");
name.setCharAt(1, 'a');
name.setCharAt(3, 'a');
System.out.println(name);          // Java
System.out.println(name.length()); // 4
```

Đây là snippet đặt trong `main`. Chỉ có các vị trí 1 và 3 bị sửa; độ dài vẫn là 4. Phương thức **không tìm tất cả ký tự khớp**, mà sửa đúng chỉ số được chỉ định. Nếu muốn thay tất cả chữ `'o'`, bạn có thể duyệt các vị trí và gọi `setCharAt` khi `charAt(i) == 'o'`, hoặc dùng một API thay thế phù hợp với nhu cầu.

Lưu thành `SetCharAtDemo.java`:

```java
public class SetCharAtDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        String original = builder.toString();

        builder.setCharAt(1, 'O');
        builder.setCharAt(3, '!');
        System.out.println(builder);
        System.out.println(builder.length());
        System.out.println(original);

        builder.setCharAt(1, builder.charAt(1));
        System.out.println(builder);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SetCharAtDemo.java
java SetCharAtDemo
```

```text
JOv!
4
Java
JOv!
```

`original` là `String` bất biến có nội dung chụp từ builder trước khi sửa; nó vẫn là `Java`. `setCharAt` sửa builder tại chỗ; dòng gán lại chính ký tự đang có không tạo khác biệt nội dung.

### Không thể gọi nối chuỗi với `setCharAt`

`append` thường trả builder, nhưng `setCharAt` trả `void`:

```java
StringBuilder sb = new StringBuilder("abc");
sb.setCharAt(0, 'A');
sb.append('!'); // Hợp lệ.

// sb.setCharAt(0, 'Z').append('!'); // KHÔNG biên dịch: setCharAt trả void.
```

Đây là snippet minh họa và dòng cuối đã được chú thích để chương trình hợp lệ. Đừng xây dựng API chain dựa trên giả định mọi phương thức `StringBuilder` trả chính builder.

## 4. `setLength(newLength)`: ba trường hợp

Chữ ký:

```java
public void setLength(int newLength)
```

`newLength` phải **không âm**. Khi gọi, sẽ xảy ra một trong ba tình huống:

| So với độ dài cũ | Hành vi |
| --- | --- |
| `newLength < oldLength` | Cắt bỏ phần nội dung logic từ chỉ số `newLength` đến cuối |
| `newLength == oldLength` | Nội dung không thay đổi |
| `newLength > oldLength` | Tăng độ dài; mọi vị trí mới nhận `'\u0000'` (NUL), không phải `' '` hoặc `'0'` |

Ví dụ:

```java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(3); // "ABC"
sb.setLength(5); // "ABC\0\0", KHÔNG phải "ABCDE"
```

Việc giảm xuống 3 khiến `D` và `E` không còn thuộc nội dung logic. Sau đó tăng lên 5, API điền **hai giá trị NUL mới**, không phục hồi hai chữ cũ. Điều này có thể khó thấy nếu chỉ in bằng `System.out.println`, vì ký tự NUL không hiển thị như chữ bình thường.

### Vì sao cần đặc biệt lưu ý ký tự NUL?

`'\u0000'` là ký tự mã 0; nó **khác**:
- `'0'`: chữ số zero, mã `U+0030`.
- `' '`: dấu cách, mã `U+0020`.
- `'\n'`: xuống dòng, mã `U+000A`.
- Chuỗi rỗng `""`: không có đơn vị `char` nào.

Khi `StringBuilder` bị tăng độ dài bằng `setLength`, nội dung logic có chứa các ký tự NUL. Một số công cụ in, hệ thống lưu trữ, giao thức hoặc ứng dụng ngoài JVM có thể xử lý NUL khác nhau; đừng tưởng những vị trí đó là khoảng trắng hoặc không tồn tại.

## 5. Ví dụ độc lập: quan sát NUL mà không in ký tự điều khiển thẳng ra màn hình

Để output rõ ràng và tái lập, ta tạo hàm `visible` in NUL thành hai ký tự hiển thị `\` và `0`, thay vì ghi mã 0 trực tiếp lên terminal.

Lưu thành `SetLengthDemo.java`:

```java
public class SetLengthDemo {
    static String visible(CharSequence text) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '\0') {
                out.append("\\0");
            } else {
                out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("ABCDE");
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(3);
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(5);
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setCharAt(3, 'X');
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(0);
        System.out.println("empty=" + (sb.length() == 0));

        sb.append("Hi");
        System.out.println(visible(sb) + " / " + sb.length());
    }
}
```

```bash
javac -encoding UTF-8 SetLengthDemo.java
java SetLengthDemo
```

```text
ABCDE / 5
ABC / 3
ABC\0\0 / 5
ABCX\0 / 5
empty=true
Hi / 2
```

Giải thích:
1. Bắt đầu ở độ dài 5.
2. `setLength(3)` bỏ phần `DE` khỏi dãy logic.
3. `setLength(5)` thêm hai vị trí NUL.
4. `setCharAt(3, 'X')` ghi lên **một** vị trí mới (lúc này chỉ số 3 hợp lệ), vị trí 4 vẫn là NUL.
5. `setLength(0)` đặt dãy logic về rỗng.
6. `append("Hi")` bắt đầu thêm từ đầu dãy logic hiện tại, nên builder mới hiển thị `Hi` với length 2.

**Lưu ý bảo mật:** `setLength(0)` thay đổi độ dài logic; nó **không phải API bảo đảm xóa an toàn tất cả bản sao dữ liệu nhạy cảm trong bộ nhớ**. Nếu muốn xử lý bí mật, không dựa vào `StringBuilder.setLength(0)` để kết luận dữ liệu đã được xóa sạch.

## 6. Ngoại lệ và điều kiện biên

### `setCharAt` dùng chỉ số phần tử đang có, không phải vị trí chèn

Nếu builder có độ dài `n`:
- `setCharAt(0, ch)` hợp lệ khi `n > 0`.
- `setCharAt(n - 1, ch)` hợp lệ khi `n > 0`.
- `setCharAt(n, ch)` **không hợp lệ**: đây là vị trí sau phần tử cuối.
- `setCharAt(-1, ch)` không hợp lệ.
- Với builder rỗng, **không có bất kỳ chỉ số nào** hợp lệ cho `setCharAt`.

Muốn thêm vào cuối hãy dùng `append(ch)` thay vì `setCharAt(length(), ch)`.

### `setLength` cho phép 0, nhưng không cho phép số âm

- `sb.setLength(0)` hợp lệ, làm nội dung logic rỗng.
- `sb.setLength(sb.length())` giữ nguyên nội dung.
- `sb.setLength(sb.length() + 1)` kéo dài thêm một `'\u0000'`, không phải tự thêm một ký tự hữu ích.
- `sb.setLength(-1)` ném `IndexOutOfBoundsException` (cụ thể có thể là lớp con `StringIndexOutOfBoundsException`).
- Nếu cố tăng lên kích thước không thể đáp ứng, ứng dụng có thể gặp vấn đề giới hạn bộ nhớ hoặc kích thước mảng; đừng nhận độ dài không giới hạn trực tiếp từ đầu vào không tin cậy.

Ví dụ độc lập, lưu `BuilderBoundsDemo.java`:

```java
public class BuilderBoundsDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("AB");

        try {
            sb.setCharAt(2, 'X');
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("Invalid character index");
        }

        try {
            sb.setLength(-1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("Invalid length");
        }

        sb.setLength(3);
        sb.setCharAt(2, 'C');

        System.out.println(sb);
        System.out.println(sb.length());
    }
}
```

```bash
javac -encoding UTF-8 BuilderBoundsDemo.java
java BuilderBoundsDemo
```

```text
Invalid character index
Invalid length
ABC
3
```

Đây là ví dụ minh họa cách sử dụng chỉ số đúng, **không phải khuyến nghị dùng ngoại lệ để điều khiển luồng bình thường**. Nếu chỉ số hay độ dài đến từ dữ liệu bên ngoài, nên kiểm tra ranh giới rõ ràng trước khi gọi.

## 7. `setCharAt` và `setLength` không thay thế `append`, `insert`, `delete` hay `replace`

Mỗi API có ngữ nghĩa riêng:

| API | Sửa gì? | Tác động đến `length()` |
| --- | --- | --- |
| `setCharAt(index,ch)` | Ghi đè đúng một `char` ở chỉ số có sẵn | Không đổi |
| `setLength(n)` | Cắt phần cuối hoặc tăng nội dung bằng NUL | Đặt lại thành `n` |
| `append(value)` | Nối biểu diễn của giá trị vào cuối | Thường tăng theo độ dài nội dung nối |
| `insert(index,value)` | Chèn dữ liệu, đẩy phần phía sau sang phải | Tăng theo độ dài phần chèn |
| `delete(start,end)` | Xóa đoạn `[start,end)` | Giảm theo số đơn vị bị xóa |
| `replace(start,end,str)` | Thay **đoạn** bằng một `String` | Có thể tăng, giảm hoặc giữ nguyên |
| `charAt(index)` | Chỉ đọc một `char` | Không đổi |

Ví dụ, nếu muốn biến `abc` thành `abXc`, **`setCharAt(2,'X')` là sai** vì nó cho `abX`, làm mất `c`. Phương thức thích hợp là `insert(2,'X')`. Ngược lại, nếu muốn `abc` thành `abX` mà vẫn giữ độ dài 3, `setCharAt(2,'X')` là đúng.

`setLength` thường hữu ích khi:
- Muốn cắt phần cuối của buffer sau khi xác định một độ dài hợp lệ.
- Tái sử dụng builder bằng `setLength(0)` rồi tiếp tục `append`.
- Cần đặt độ dài cố định và **chủ động** điền/ghi lại mọi vị trí trước khi xem nội dung là văn bản hoàn chỉnh.

Nếu nhu cầu là “thêm nội dung”, `append` thể hiện ý định rõ hơn việc `setLength(oldLength + k)` rồi điền từng ô, vì tăng độ dài tự tạo ra NUL trước khi được ghi đè.

## 8. Tạo vùng ký tự cố định và ghi vào các vị trí mới

Khi muốn xây dựng một dãy có độ dài xác định rồi gán từng `char`, có thể dùng `setLength` trước để mọi chỉ số đích nằm trong phạm vi hợp lệ:

```java
StringBuilder slots = new StringBuilder();
slots.setLength(3); // Ba vị trí NUL.

slots.setCharAt(0, 'A');
slots.setCharAt(1, 'B');
slots.setCharAt(2, 'C');

System.out.println(slots); // ABC
```

Đây là snippet hợp lệ bên trong `main`. Nếu quên điền một ô thì vị trí còn trống thực chất chứa NUL, không phải “chưa có phần tử”. Một mô hình có kiểu dữ liệu rõ hơn đôi khi là dùng `char[]`, `Arrays.fill` hoặc một cấu trúc buffer phù hợp; lựa chọn phụ thuộc API và mục đích.

Ví dụ đầy đủ, lưu `FixedSlotsDemo.java`:

```java
public class FixedSlotsDemo {
    public static void main(String[] args) {
        StringBuilder slots = new StringBuilder();
        slots.setLength(4);

        for (int i = 0; i < slots.length(); i++) {
            slots.setCharAt(i, (char) ('A' + i));
        }

        System.out.println(slots);
        System.out.println(slots.length());

        slots.setLength(2);
        slots.append('!');
        System.out.println(slots);
    }
}
```

```bash
javac -encoding UTF-8 FixedSlotsDemo.java
java FixedSlotsDemo
```

```text
ABCD
4
AB!
```

Ở vòng lặp, phép `(char) ('A' + i)` đổi biểu thức số nguyên thành đơn vị `char`. Với `i` từ 0 đến 3, ta thu `A`, `B`, `C`, `D`. Khi cắt về độ dài 2 và nối `!`, nội dung trở thành `AB!`. Những ký tự `CD` đã bị loại khỏi dãy logic, không tự trở lại khi nối thêm.

## 9. UTF-16: một `char` không luôn là một ký tự Unicode hiển thị

Một điểm quan trọng khi sửa dữ liệu văn bản: `StringBuilder` lưu các đơn vị **UTF-16**. Một Unicode code point ngoài BMP như `🙂` (`U+1F642`) được biểu diễn bởi **hai `char`**: *high surrogate* và *low surrogate*. Vì vậy:
- `builder.length()` đếm các đơn vị `char`, không nhất thiết bằng số Unicode code point hay số ký tự người dùng nhìn thấy.
- `setCharAt(i,ch)` chỉ thay **một đơn vị UTF-16**. Nó **không tự xác định** cặp surrogate và không bảo đảm giữ nguyên một code point ngoài BMP.
- `setLength(n)` có thể cắt chuỗi **giữa** high surrogate và low surrogate nếu `n` đặt vào ranh giới không phù hợp.
- Một chuỗi `String` hoặc `StringBuilder` có thể chứa surrogate lẻ, nhưng dữ liệu đó không biểu diễn một dãy Unicode scalar value hợp lệ.

Lưu `SurrogateBuilderDemo.java`:

```java
public class SurrogateBuilderDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("A🙂B");

        System.out.println(text.length());
        System.out.println(
                text.codePointCount(0, text.length()));

        text.setCharAt(0, 'X');
        System.out.println(text);

        text.setLength(3); // Ranh giới đúng sau emoji.
        System.out.println(text);
        System.out.println(
                text.codePointCount(0, text.length()));
    }
}
```

```bash
javac -encoding UTF-8 SurrogateBuilderDemo.java
java SurrogateBuilderDemo
```

```text
4
3
X🙂B
X🙂
2
```

Chuỗi đầu có 4 đơn vị UTF-16 nhưng chỉ có 3 code point. Sau khi thay `A` thành `X`, cấu trúc surrogate của emoji vẫn nguyên vẹn. `setLength(3)` cắt chữ `B` ở cuối mà không chia đôi emoji, nên `X🙂` có 3 đơn vị UTF-16 và 2 code point.

Ngược lại, nếu gọi `setLength(2)` từ `"A🙂B"`, nội dung giữ `A` và **high surrogate** của emoji nhưng cắt mất low surrogate. Đây không phải cách cắt văn bản Unicode ở ranh giới code point. Nếu muốn di chuyển theo code point, dùng `offsetByCodePoints` hoặc `codePointAt`/`Character.charCount` để tính ranh giới UTF-16 trước khi dùng `setLength`. Nếu cần thay cả emoji bằng một emoji khác, cân nhắc `replace(start,end,replacement)` với hai ranh giới UTF-16 đúng thay vì `setCharAt` một ô.

### Cắt đúng số code point

Đoạn snippet:

```java
StringBuilder sb = new StringBuilder("A🙂B");
int endUtf16 = sb.offsetByCodePoints(0, 2);
sb.setLength(endUtf16);
System.out.println(sb); // A🙂
```

`offsetByCodePoints(0,2)` trả chỉ số UTF-16 `3`, vì `A` chiếm một `char` và `🙂` chiếm hai. Nhờ đó `setLength(3)` giữ nguyên cặp surrogate. Các phương thức này tính theo **code point**, vẫn chưa đủ để bảo đảm không cắt *grapheme cluster* (ví dụ dấu kết hợp hoặc emoji nối bằng ZWJ); nếu yêu cầu liên quan đến con trỏ người dùng hay số ký tự hiển thị, cần logic phân đoạn grapheme tương ứng.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `setCharAt(sb.length(),ch)` để nối cuối | Lỗi chỉ số ngoài phạm vi | Dùng `append(ch)` |
| Dùng `capacity()` để kiểm tra chỉ số của `setCharAt` | Có thể chạm vị trí ngoài **độ dài logic** | Kiểm tra `0 <= index < length()` |
| Tưởng `setCharAt` thay toàn bộ ký tự giống nhau | Nó chỉ sửa **một vị trí** | Duyệt/đổi từng vị trí nếu cần thay hàng loạt |
| Viết `sb.setCharAt(...).append(...)` | Không biên dịch vì `setCharAt` trả `void` | Gọi thành hai câu lệnh |
| Tưởng `setLength` trả builder để chain | Không biên dịch vì `setLength` trả `void` | Gọi riêng |
| Tăng `setLength` rồi tưởng có dấu cách hoặc chữ 0 | Các vị trí mới là **NUL U+0000** | Chủ động điền đủ dữ liệu |
| Cắt ngắn rồi tăng lại mong khôi phục ký tự cũ | Ký tự bị cắt không nằm trong kết quả logic | Giữ bản gốc nếu muốn phục hồi |
| Tưởng `setLength(0)` giải phóng bộ nhớ hoặc xóa sạch bí mật | Nó thay đổi length, không hứa về việc xóa/cấp lại buffer | Chọn kỹ thuật quản lý dữ liệu nhạy cảm phù hợp |
| Dùng `setLength` cắt giữa surrogate pair | Có thể tạo high/low surrogate lẻ | Tính ranh giới code point trước |
| Dùng `setCharAt` để thay toàn bộ emoji ngoài BMP | Một `char` không đủ biểu diễn emoji đó | Thay cả đoạn hai code unit hoặc xử lý code point |
| Cho rằng builder cũng bất biến như `String` | Các alias đều thấy thay đổi của cùng builder | Sao chép hoặc không chia sẻ builder mutable |
| Dùng chung builder từ nhiều luồng không đồng bộ | Race condition và kết quả không xác định | Dùng ownership riêng hoặc đồng bộ phù hợp |

## 11. Bài tập tự kiểm tra

### Bài 1. Thay đúng vị trí

Với `StringBuilder sb = new StringBuilder("java");`, hãy viết hai lời gọi `setCharAt` để biến nội dung thành `"Java!"`. Bẫy: độ dài ban đầu là 4, độ dài kết quả là 5. Bạn có thể chỉ dùng `setCharAt` để tạo dấu `!` ở vị trí 4 không?

**Đáp án:** `sb.setCharAt(0,'J'); sb.append('!');`. Chỉ `setCharAt` không thể làm tăng độ dài từ 4 lên 5. Cách khác là `setLength(5)` rồi `setCharAt(4,'!')`, nhưng `append` rõ nghĩa hơn.

### Bài 2. Cắt ngắn rồi kéo dài

Dự đoán giá trị số nguyên của hai vị trí cuối sau các lệnh:

```java
StringBuilder sb = new StringBuilder("HELLO");
sb.setLength(3);
sb.setLength(5);
System.out.println((int) sb.charAt(3));
System.out.println((int) sb.charAt(4));
```

**Đáp án:**

```text
0
0
```

Hai vị trí mới chứa `'\u0000'`, không phải `L`/`O`. Các chữ đã bị cắt không tự trở lại.

### Bài 3. Phạm vi hợp lệ

Nếu builder có `length() == 3` và `capacity() == 18`, các chỉ số nào hợp lệ khi gọi `setCharAt`?

**Đáp án:** Chỉ số 0, 1, 2. Chỉ số 3 trở lên không hợp lệ dù capacity đủ lớn.

### Bài 4. Kiểm tra Unicode

Với `StringBuilder sb = new StringBuilder("A🙂B");`:
- `sb.length()` bằng bao nhiêu?
- Gọi `sb.setLength(3)` có giữ nguyên emoji không?
- Gọi `sb.setLength(2)` có còn giữ cặp surrogate đầy đủ không?

**Đáp án:** Độ dài là 4 `char`; cắt về 3 giữ `A🙂`, nhưng cắt về 2 làm mất low surrogate của emoji và để lại high surrogate lẻ. Muốn cắt đúng theo code point, tính chỉ số UTF-16 bằng `offsetByCodePoints` trước.

### Bài 5. Trả về và biến đổi

Lệnh sau có hợp lệ không?

```java
StringBuilder sb = new StringBuilder("abc");
// sb = sb.setLength(2); // Không biên dịch.
sb.setLength(2);
System.out.println(sb);
```

**Đáp án:** `setLength` có kiểu `void` nên không thể gán kết quả cho `sb`. Sau khi gọi riêng, chương trình in `ab`.

## 12. Ghi nhớ

- `setCharAt(index,ch)` **ghi đè một `char` đã tồn tại**; cần `0 <= index < length()`, độ dài không đổi, kiểu trả về `void`.
- `setLength(n)` thay đổi **độ dài logic**. Giảm độ dài sẽ cắt bỏ phần cuối; tăng độ dài thêm `'\u0000'` vào mọi vị trí mới; `n` âm không hợp lệ.
- **`length()` khác `capacity()`.** Có dung lượng lưu trữ chưa đồng nghĩa có phần tử hợp lệ tại chỉ số đó.
- Cắt ngắn rồi kéo dài **không khôi phục** dữ liệu cũ. `setLength(0)` làm rỗng logic, không hứa xóa bí mật khỏi bộ nhớ.
- Chỉ số `setCharAt` và `setLength` đếm **đơn vị UTF-16**; cần thận trọng với cặp surrogate và grapheme.
- `StringBuilder` có thể thay đổi tại chỗ, khác `String` bất biến; khi chia sẻ tham chiếu hoặc làm việc đa luồng phải quản lý quyền sửa và đồng bộ.

## Tài liệu chính thức (Java SE 17)

- [`StringBuilder`: `setCharAt`, `setLength`, `length`, `capacity`, `append`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`AbstractStringBuilder` và `CharSequence`: vị trí UTF-16 và các thao tác dãy ký tự](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
- [`Character`: Unicode code point, `charCount` và surrogate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
