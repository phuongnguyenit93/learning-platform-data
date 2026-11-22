# `StringBuilder`: `insert`, `delete`, `deleteCharAt` và `replace` trong Java

`StringBuilder` là một **chuỗi ký tự có thể thay đổi** (*mutable sequence of characters*). Không giống `String` (bất biến), `StringBuilder` cho phép **chèn, xóa và thay thế trực tiếp trên đối tượng đang có**. Bốn phương thức quan trọng để chỉnh sửa nội dung theo vị trí là:

- **`insert(index, value)`:** chèn dữ liệu **trước vị trí** `index`.
- **`delete(start, end)`:** xóa các đơn vị ký tự trong đoạn **`[start, end)`**.
- **`deleteCharAt(index)`:** xóa đúng **một đơn vị `char`** tại `index`.
- **`replace(start, end, str)`:** thay đoạn **`[start, end)`** bằng chuỗi `str`.

Các thao tác này làm **thay đổi chính `StringBuilder` đang gọi** và trả về tham chiếu đến builder đó để có thể gọi nối tiếp. Chỉ số dùng trong API của `StringBuilder` là **offset UTF-16 code unit**, không nhất thiết là số ký tự người dùng nhìn thấy.

## 1. Khác nhau giữa `String` và `StringBuilder`

```java
String text = "Java";
text.replace("Java", "Kotlin");
// text vẫn là "Java": String bất biến.

StringBuilder builder = new StringBuilder("Java");
builder.replace(0, 4, "Kotlin");
// builder hiện có nội dung "Kotlin".
```

Trong ví dụ, `String.replace(CharSequence, CharSequence)` tìm và thay **nội dung nguyên văn**, trả về một `String`; còn **`StringBuilder.replace(int, int, String)` thay đoạn theo chỉ số** và sửa builder tại chỗ. Hai phương thức cùng tên nhưng **không có cùng chữ ký hoặc cách chọn đoạn cần thay**.

| Phương thức | Đầu vào vị trí | Tác dụng | Trả về |
| --- | --- | --- | --- |
| `insert(offset, value)` | Một vị trí chèn, tính từ 0 | Chèn trước code unit tại offset | Chính `StringBuilder` |
| `delete(start, end)` | Đoạn nửa mở `[start, end)` | Xóa đoạn | Chính `StringBuilder` |
| `deleteCharAt(index)` | Vị trí một code unit | Xóa một code unit | Chính `StringBuilder` |
| `replace(start, end, str)` | Đoạn nửa mở `[start, end)` | Bỏ đoạn, đưa `str` vào chỗ đó | Chính `StringBuilder` |
| `toString()` | Không có | Tạo giá trị `String` có nội dung hiện tại | Một `String` |

`StringBuilder.length()` trả số **UTF-16 code unit hiện có**, thay đổi khi chèn/xóa/thay. `capacity()` là dung lượng bộ đệm dự trữ: nó **không** phải chiều dài văn bản và **không** phải chỉ số hợp lệ cho các thao tác này.

## 2. Quy tắc chỉ số: vị trí và khoảng `[start, end)`

Giả sử builder chứa `"ABCDE"`:

```text
Nội dung:    A   B   C   D   E
Code unit:   0   1   2   3   4
Vị trí:      0   1   2   3   4   5
             |---|---|---|---|---|

insert(2, "X")     -> ABXCDE
delete(1, 4)       -> AE
deleteCharAt(2)    -> ABDE
replace(1, 4, "X") -> AXE
```

Các dòng trên là **bốn thao tác độc lập**, đều bắt đầu từ `"ABCDE"`, **không** nối tiếp nhau.

- `insert(2, "X")` chèn trước `C` (code unit tại chỉ số 2), đẩy phần từ `C` trở đi sang phải.
- `delete(1, 4)` xóa `B`, `C`, `D` (chỉ số 1, 2, 3), giữ `A`, `E`.
- `deleteCharAt(2)` chỉ xóa `C` tại chỉ số 2.
- `replace(1, 4, "X")` thay toàn bộ `BCD` bằng `X`.

**Biên đầu được lấy, biên cuối không được lấy** đối với `delete` và `replace`. Vì vậy, khi `end - start == 3`, thao tác tác động lên ba code unit của đoạn gốc (nếu `end` không vượt chiều dài).

### Chỉ số hợp lệ

Với `n = builder.length()`:

- `insert(offset, value)` cho phép `0 <= offset <= n`. `offset == 0` là chèn đầu; `offset == n` là chèn cuối (tương tự append về vị trí).
- `delete(start, end)` yêu cầu `0 <= start <= n`, `start <= end`. Nếu `end > n`, Java **giới hạn biên cuối ở `n`**; không phải lỗi chỉ vì `end` vượt `n`.
- `replace(start, end, str)` tương tự với phạm vi: `0 <= start <= n`, `start <= end`; `end > n` được **giới hạn ở `n`**.
- `deleteCharAt(index)` yêu cầu `0 <= index < n`; `index == n` **không hợp lệ**, vì đó là vị trí sau ký tự cuối.
- Chỉ số âm, `start > n` hoặc `start > end` là lỗi phạm vi đối với `delete` và `replace`.

Với đầu vào không hợp lệ, các API ném ngoại lệ thuộc nhóm `IndexOutOfBoundsException` (cụ thể có thể là `StringIndexOutOfBoundsException` tùy phương thức/triển khai). `replace` còn ném `NullPointerException` nếu chuỗi thay `str` là `null`.

## 3. `insert()`: chèn ở đầu, giữa hoặc cuối

`insert` có nhiều overload để nhận các loại dữ liệu khác nhau, ví dụ:

```java
builder.insert(0, "Hi ");    // chèn String vào đầu
builder.insert(2, 'X');      // chèn char
builder.insert(3, 42);       // chèn số, dạng văn bản "42"
builder.insert(builder.length(), "!"); // chèn cuối
```

Đoạn này **minh họa những lời gọi đặt trong thân phương thức** với một builder đã tạo; nếu chạy lần lượt, chỉ số của mỗi lời gọi được hiểu theo **nội dung tại thời điểm gọi**, không theo nội dung ban đầu.

Một số overload thường dùng:

| Overload | Ý nghĩa |
| --- | --- |
| `insert(int offset, String str)` | Chèn nội dung của `String` |
| `insert(int offset, CharSequence s)` | Chèn một dãy ký tự (có thể là `String` hoặc `StringBuilder`) |
| `insert(int offset, char c)` | Chèn một `char` |
| `insert(int offset, int i)` | Chèn biểu diễn văn bản của số nguyên |
| `insert(int offset, boolean b)` | Chèn `"true"` hoặc `"false"` |
| `insert(int offset, char[] data)` | Chèn ký tự từ mảng |
| `insert(int dstOffset, CharSequence s, int start, int end)` | Chèn đoạn `[start, end)` của dãy nguồn `s` vào vị trí đích |

Với overload cuối, cần phân biệt **`dstOffset` trong builder đích** với **`start` và `end` trong `CharSequence` nguồn**. Chẳng hạn `new StringBuilder("XY").insert(1, "012345", 2, 5)` cho nội dung `"X234Y"`: lấy đoạn `234` từ nguồn rồi chèn giữa `X` và `Y`.

**Trường hợp null:** Một số overload của `insert` được đặc tả để chèn chữ `"null"` khi đối số `String`/`CharSequence` là null. Ví dụ `new StringBuilder("abc").insert(1, (String) null)` thành `"anullbc"`. Cần xác định chính sách dữ liệu của chương trình; không nên dựa vào việc tự động chèn chữ `"null"` nếu null biểu thị dữ liệu thiếu.

## 4. `delete()` và `deleteCharAt()`: xóa đúng đoạn

### 4.1. Xóa khoảng bằng `delete(start, end)`

`delete(start, end)` xóa từ **`start` bao gồm đến `end` không bao gồm**. Độ dài xóa thực tế là `min(end, length()) - start` nếu các biên đầu hợp lệ.

```java
StringBuilder sb = new StringBuilder("abcdef");
sb.delete(2, 5); // "abf" (xóa c, d, e)
```

Ở ví dụ này, chuỗi `"abcdef"` có chỉ số `0..5`; sau khi xóa chỉ số `2..4`, kết quả **`"abf"`** vì giữ `a, b, f`.

Đặc biệt:

- `delete(2, 2)`: đoạn rỗng, nội dung không thay đổi.
- `delete(0, length())`: xóa toàn bộ builder.
- `delete(1, 99)` trên builder `"abc"`: xóa từ chỉ số 1 đến hết vì `end` được giới hạn còn 3; kết quả `"a"`.
- `delete(length(), length())`: hợp lệ, không thay đổi.
- `delete(length() + 1, length() + 1)`: không hợp lệ vì `start` vượt chiều dài.

Lưu ý: biên cuối vượt chiều dài **được giới hạn**, nhưng biên đầu vượt chiều dài **không** được tự động giới hạn.

### 4.2. Xóa một code unit bằng `deleteCharAt(index)`

`deleteCharAt(index)` tương tự `delete(index, index + 1)` về việc xóa **một UTF-16 code unit**, khi `index` hợp lệ.

```java
StringBuilder sb = new StringBuilder("book");
sb.deleteCharAt(1);
// Kết quả: "bok"
```

Chỉ số cuối hợp lệ với `deleteCharAt` là `length() - 1`. Nếu builder rỗng, không có chỉ số nào hợp lệ để xóa một `char`.

**Cảnh báo Unicode:** `deleteCharAt` làm việc với từng code unit, có thể xóa một nửa **surrogate pair** của một emoji, khiến chuỗi còn lại chứa surrogate lẻ. Muốn xóa trọn một Unicode code point ngoài BMP, dùng `codePointAt` và `Character.charCount` như phần Unicode ở dưới. Muốn xóa cả một *grapheme cluster* (cụm ký tự người dùng xem là một) cần phân đoạn Unicode phù hợp; xóa một code point vẫn có thể tách dấu kết hợp hoặc emoji ZWJ.

## 5. `replace(start, end, str)`: thay đoạn bằng chuỗi mới

`StringBuilder.replace(int start, int end, String str)`:

1. Xác định đoạn `[start, end)` của builder hiện tại.
2. Bỏ đoạn đó (biên `end` vượt `length()` thì chỉ lấy đến hết).
3. Đưa nội dung `str` vào ngay vị trí `start`.

Ví dụ độc lập:

```java
StringBuilder sb = new StringBuilder("Hello world");
sb.replace(6, 11, "Java");
// Kết quả: "Hello Java"
```

`replace` là **thay theo vị trí**, **không tự tìm mọi lần xuất hiện của từ `"world"`**. Nếu không biết vị trí, trước tiên có thể gọi `indexOf("world")`, rồi dùng `replace(index, index + "world".length(), "Java")` sau khi kiểm tra index khác `-1`.

Những trường hợp biên thường hữu ích:

- `replace(k, k, "X")`: không xóa code unit nào, có tác dụng **chèn `"X"` vào k**.
- `replace(start, end, "")`: thay bằng chuỗi rỗng, có tác dụng **xóa đoạn**.
- `replace(length(), length(), "!")`: chèn `!` ở cuối.
- `replace(1, 99, "XY")` trên builder `"abc"`: thay từ `b` đến hết bằng `XY`, kết quả `"aXY"`.
- `replace(3, 99, "!")` trên builder `"abc"`: không xóa gì vì bắt đầu ở cuối, rồi chèn `!`, kết quả `"abc!"`.

**`str` không được là null:** `replace(start, end, null)` sẽ ném `NullPointerException`. Khác với một số overload của `insert`, `replace` không tự biến null thành `"null"`.

### Khác với `String.replace` và `replaceAll`

| API | Chọn phần cần thay | Thay đổi đối tượng nhận? |
| --- | --- | --- |
| `StringBuilder.replace(start, end, str)` | **Bằng chỉ số** của một đoạn | Có, sửa `StringBuilder` |
| `String.replace(oldText, newText)` | **Mọi lần khớp chuỗi literal, không chồng lấn** | Không, trả về `String` |
| `String.replaceAll(regex, replacement)` | **Mọi lần khớp regex** | Không, trả về `String` |

Không đưa regex như `"\\d+"` cho `StringBuilder.replace` và mong nó thay chữ số; overload của `StringBuilder` không nhận target regex hay chuỗi cần tìm, mà nhận **vị trí bắt đầu và kết thúc**.

## 6. Ví dụ tổng hợp có thể chạy trên Java 17+

Lưu tệp `BuilderOpsDemo.java`:

```java
public class BuilderOpsDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("Java");

        sb.insert(4, " Core");
        System.out.println(sb);

        sb.insert(0, "Learn ");
        System.out.println(sb);

        sb.insert(sb.length(), "!");
        System.out.println(sb);

        sb.delete(0, 6);
        System.out.println(sb);

        sb.delete(4, 9);
        System.out.println(sb);

        sb.deleteCharAt(4);
        System.out.println(sb);

        sb.replace(0, 4, "Kotlin");
        System.out.println(sb);

        System.out.println(sb.length());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BuilderOpsDemo.java
java BuilderOpsDemo
```

Kết quả:

```text
Java Core
Learn Java Core
Learn Java Core!
Java Core!
Java!
Java
Kotlin
6
```

Giải thích các mốc chính:

- Sau lần chèn thứ ba, nội dung `"Learn Java Core!"` dài 16 code unit.
- `delete(0, 6)` bỏ tiền tố `"Learn "` (6 code unit), được `"Java Core!"`.
- `delete(4, 9)` bỏ `" Core"`; biên 9 không lấy dấu `!`, nên còn `"Java!"`.
- `deleteCharAt(4)` xóa `!`, còn `"Java"`.
- `replace(0, 4, "Kotlin")` thay cả `Java` thành `Kotlin`, có chiều dài 6.

**Quan trọng:** Chỉ số ở mỗi lần thao tác được tính từ **nội dung hiện tại**, không phải nội dung khởi tạo `"Java"`. Mọi lần chèn hoặc xóa trước một vị trí đều có thể làm lệch các chỉ số về sau.

## 7. Bài chạy kiểm tra các trường hợp biên

Lưu tệp `BuilderBoundsDemo.java`:

```java
public class BuilderBoundsDemo {
    public static void main(String[] args) {
        StringBuilder a = new StringBuilder("abc");
        System.out.println(a.delete(1, 99));

        StringBuilder b = new StringBuilder("abc");
        System.out.println(b.replace(1, 99, "XY"));

        StringBuilder c = new StringBuilder("abc");
        System.out.println(c.replace(1, 1, "!"));

        StringBuilder d = new StringBuilder("abc");
        System.out.println(d.replace(3, 99, "!"));

        StringBuilder e = new StringBuilder("abc");
        System.out.println(e.insert(1, (String) null));

        StringBuilder f = new StringBuilder("abc");
        System.out.println(f.delete(1, 1));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderBoundsDemo.java
java BuilderBoundsDemo
```

Kết quả:

```text
a
aXY
a!bc
abc!
anullbc
abc
```

Điểm đáng nhớ: `end > length()` với `delete` hoặc `replace` không tự động gây lỗi; `start == end` tạo đoạn rỗng (xóa là không đổi, thay bằng chuỗi không rỗng sẽ chèn). Còn `insert(..., (String) null)` chèn chữ `null` theo quy tắc overload này, không đồng nghĩa `replace(..., null)` hợp lệ.

## 8. Làm việc an toàn với Unicode / UTF-16

`StringBuilder` cũng lưu và đánh chỉ số theo UTF-16 code unit. Emoji `😀` là một Unicode code point nhưng được biểu diễn bằng **hai `char`**. Chèn hoặc xóa ở giữa cặp surrogate có thể làm chuỗi thiếu tính hợp lệ Unicode.

Lưu `BuilderUnicodeDemo.java`:

```java
public class BuilderUnicodeDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder(
                "A\uD83D\uDE00B"); // A😀B

        System.out.println(text.length());
        System.out.println(
                Character.codePointCount(text, 0, text.length()));

        StringBuilder whole = new StringBuilder(text);
        whole.delete(1, 3);
        System.out.println(whole);

        StringBuilder broken = new StringBuilder(text);
        broken.deleteCharAt(1);
        System.out.println(
                Character.isLowSurrogate(broken.charAt(1)));
        System.out.println(broken.length());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderUnicodeDemo.java
java BuilderUnicodeDemo
```

Kết quả:

```text
4
3
AB
true
3
```

- `length() == 4` vì `A` và `B` mỗi ký tự chiếm 1 code unit, còn emoji cần 2 code unit.
- Có 3 Unicode code point: `A`, `😀`, `B`.
- `delete(1, 3)` xóa trọn cặp surrogate đại diện emoji, còn `AB`.
- `deleteCharAt(1)` chỉ xóa high surrogate tại index 1, để lại low surrogate lẻ. Vì vậy `Character.isLowSurrogate(broken.charAt(1))` trả `true`. Không nên coi chuỗi còn lại là Unicode hợp lệ.

Khi đang đứng ở **offset bắt đầu của một code point**, có thể xóa trọn code point đó bằng:

```java
int index = 1;
int point = text.codePointAt(index);
text.delete(index, index + Character.charCount(point));
```

Đây là đoạn minh họa bên trong phương thức sau khi `text` chứa `"A😀B"`; kết quả sẽ là `"AB"`. `Character.charCount(point)` trả `2` đối với `😀`. Nếu offset bắt đầu nằm **giữa** surrogate pair, thuật toán phải tìm lại ranh giới chính xác trước khi xử lý. Và nếu nghiệp vụ cần thao tác theo **ký tự hiển thị** (grapheme cluster), chỉ dựa vào code point vẫn chưa đủ với các tổ hợp dấu, modifier hoặc emoji có zero-width joiner.

## 9. Tìm theo nội dung trước khi chỉnh sửa vị trí

`StringBuilder.replace` yêu cầu **chỉ số**, không nhận target cần tìm. Nếu muốn thay một lần xuất hiện nguyên văn của một từ:

```java
StringBuilder sb = new StringBuilder("Hello world");
String target = "world";
int index = sb.indexOf(target);

if (index >= 0) {
    sb.replace(index, index + target.length(), "Java");
}

System.out.println(sb); // Hello Java
```

Đoạn này là mã minh họa đặt trong một phương thức. `indexOf` trả `-1` khi không tìm thấy; phải kiểm tra trước khi đưa vào `replace`.

Nếu cần thay **tất cả** lần xuất hiện literal bằng cách chỉnh builder trực tiếp, có thể duyệt vị trí tìm thấy. Ví dụ độc lập ở `BuilderReplaceAllDemo.java`:

```java
public class BuilderReplaceAllDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("red blue red");
        String target = "red";
        String replacement = "green";

        if (target.isEmpty()) {
            throw new IllegalArgumentException("target is empty");
        }

        int from = 0;
        while ((from = sb.indexOf(target, from)) >= 0) {
            sb.replace(from, from + target.length(), replacement);
            from += replacement.length();
        }

        System.out.println(sb);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BuilderReplaceAllDemo.java
java BuilderReplaceAllDemo
```

Kết quả:

```text
green blue green
```

Sau mỗi lần thay, `from` được chuyển qua **đoạn replacement vừa đưa vào**, tránh tìm lại các ký tự mới chèn ở lần thay hiện tại. Việc kiểm tra `target.isEmpty()` ngăn các trường hợp tìm đoạn rỗng vốn cần chính sách riêng.

Với bài toán đơn giản chỉ cần thay đoạn văn bản ở mọi vị trí, **`String.replace(target, replacement)` thường dễ đọc hơn**: `String result = sb.toString().replace("red", "green");`. Chỉ dùng vòng lặp chỉnh builder khi có lý do xử lý tại chỗ hoặc cần tích hợp nhiều phép biến đổi có trạng thái.

## 10. Khả năng nối phương thức, độ dài và hiệu năng

Cả bốn phương thức sửa nội dung đều trả lại builder, nên có thể **chain**:

```java
StringBuilder sb = new StringBuilder("abc");
StringBuilder same = sb.insert(1, "-");

System.out.println(sb == same); // true
System.out.println(sb);         // a-bc

sb.delete(1, 2).replace(1, 2, "B");
System.out.println(sb);         // aBc
```

`==` ở đây được dùng **có chủ đích để kiểm tra danh tính đối tượng `StringBuilder`**, không phải so sánh nội dung của hai `String`. Builder vẫn là một đối tượng; các lời gọi liên tiếp lần lượt sửa nội dung của nó.

Về chi phí:

- `insert` ở giữa chuỗi thường phải dịch chuyển phần đuôi sang phải; `delete` thường phải dịch chuyển dữ liệu còn lại sang trái.
- `replace` có thể khiến độ dài tăng hoặc giảm, tùy độ dài đoạn bị bỏ và `str` được chèn.
- `append` thường phù hợp hơn `insert` ở giữa nếu mục tiêu chỉ là xây dựng chuỗi từ trái sang phải.
- `StringBuilder` có bộ đệm có thể tăng dung lượng; `capacity()` và `ensureCapacity(...)` liên quan hiệu năng/dung lượng, **không thay đổi quy tắc vị trí**.
- `StringBuilder` **không đồng bộ hóa các phương thức** để dùng chung và sửa từ nhiều luồng; với truy cập đồng thời cần quản lý đồng bộ bên ngoài hoặc thiết kế không chia sẻ mutable builder.

Không nên khẳng định chắc số cấp phát hoặc độ phức tạp của toàn chương trình chỉ từ một phép nối; hiệu năng cần được đánh giá theo dữ liệu và JVM thực tế.

## 11. Lỗi thường gặp và cách tránh

1. **Nhầm biên cuối là bao gồm:** `delete(1, 4)` xóa chỉ số 1, 2, 3, không xóa chỉ số 4.
2. **Dùng chỉ số cũ sau khi chèn/xóa:** các code unit phía sau có thể bị dịch chuyển; tính lại vị trí trên builder hiện tại.
3. **Tưởng `end > length()` luôn ném lỗi:** với `delete` và `replace`, `end` lớn hơn chiều dài được **giới hạn về chiều dài**; nhưng `start > length()` vẫn là lỗi.
4. **Dùng `deleteCharAt(length())`:** không hợp lệ; ký tự cuối có chỉ số `length() - 1`, nếu builder không rỗng.
5. **Nhầm `replace(start, end, str)` với `String.replace(old, new)`:** phương thức của builder thay **một khoảng chỉ số**, không tự tìm và thay mọi lần xuất hiện.
6. **Dùng `replace(start, end, null)`:** tham số `str` null gây `NullPointerException`; nếu muốn xóa đoạn, dùng `delete` hoặc `replace(start, end, "")`.
7. **Giả định mọi thao tác theo “ký tự nhìn thấy”:** API dùng UTF-16 code unit; xóa một `char` có thể phá cặp surrogate.
8. **Cho rằng phương thức builder không thay đổi đối tượng nhận:** các phương thức này *mutate* chính builder; giữ tham chiếu `StringBuilder` ở nơi khác sẽ quan sát được nội dung thay đổi.
9. **So sánh nội dung hai builder bằng `==`:** `==` kiểm tra cùng tham chiếu. Dùng `toString().equals(...)` hoặc thuật toán so nội dung phù hợp nếu cần.
10. **Không kiểm tra kết quả `indexOf` trước khi `replace`:** nếu không tìm thấy, chỉ số `-1` không hợp lệ.
11. **Dùng chung một `StringBuilder` cho nhiều luồng sửa mà không đồng bộ:** có thể làm trạng thái và kết quả không nhất quán.

## 12. Tự kiểm tra

Cho mỗi tình huống dưới đây, **bắt đầu với một builder mới**, không sử dụng kết quả của dòng trước:

| Builder ban đầu | Thao tác | Kết quả |
| --- | --- | --- |
| `"ABCDE"` | `insert(0, ">")` | `">ABCDE"` |
| `"ABCDE"` | `insert(5, "!")` | `"ABCDE!"` |
| `"ABCDE"` | `delete(1, 4)` | `"AE"` |
| `"ABCDE"` | `delete(2, 2)` | `"ABCDE"` |
| `"ABCDE"` | `deleteCharAt(4)` | `"ABCD"` |
| `"ABCDE"` | `replace(1, 4, "x")` | `"AxE"` |
| `"ABCDE"` | `replace(2, 2, "x")` | `"ABxCDE"` |
| `"ABCDE"` | `replace(0, 5, "")` | `""` |
| `"ABCDE"` | `delete(2, 99)` | `"AB"` |

Câu hỏi kiểm tra:

- Với `"abc"`, `delete(1, 99)` cho gì? **`"a"`** vì `end` vượt chiều dài được giới hạn.
- Với `"abc"`, `replace(3, 99, "!")` cho gì? **`"abc!"`** vì `start` ở cuối và phần bị thay là rỗng.
- Tại sao `deleteCharAt(1)` có thể gây lỗi nội dung Unicode với `"A😀B"`? Vì xóa một `char`, có thể chỉ xóa **nửa cặp surrogate**.
- Nếu muốn thay mọi chữ `red` thành `green` thì `StringBuilder.replace` tự làm hết không? **Không**; phải xác định các khoảng cần thay, hoặc dùng `String.replace`.

**Ghi nhớ:** `insert` chèn tại một vị trí; `delete` xóa đoạn `[start, end)`; `deleteCharAt` xóa một code unit; `replace` thay đoạn `[start, end)`. Cả bốn **sửa chính `StringBuilder`**, trả về builder để có thể nối lời gọi, và dùng **offset UTF-16** — vì vậy kiểm tra biên cùng ranh giới Unicode trước khi thao tác.
