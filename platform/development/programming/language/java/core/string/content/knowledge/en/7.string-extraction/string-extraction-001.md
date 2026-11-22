# `String.substring(beginIndex)`: Trích xuất chuỗi từ một vị trí đến hết chuỗi trong Java

## 1. Bài toán và ý nghĩa của `substring(beginIndex)`

Khi đã có một chuỗi nhưng chỉ cần giữ phần **bắt đầu từ một vị trí xác định đến ký tự cuối cùng**, Java cung cấp phương thức:

```java
public String substring(int beginIndex)
```

Phương thức này thuộc lớp `java.lang.String`. Nó trả về một `String` đại diện cho **phần còn lại của chuỗi**, bắt đầu **tại** `beginIndex`, bao gồm ký tự ở vị trí đó (nếu có) và toàn bộ ký tự phía sau.

```java
String text = "Java Core";
String part = text.substring(5);

System.out.println(part); // Core
```

Chuỗi `"Java Core"` có các vị trí như sau:

```text
Ký tự:  J  a  v  a     C  o  r  e
Chỉ số: 0  1  2  3  4  5  6  7  8
```

Chỉ số `5` trỏ đến chữ `C`. Vì vậy `text.substring(5)` trả về `"Core"`.

**Cốt lõi:** `beginIndex` là chỉ số **bắt đầu lấy**, được tính từ `0`. Với phiên bản nhận **một tham số**, bạn không cần chỉ định điểm kết thúc: Java tự lấy đến hết chuỗi.

## 2. Cú pháp và giá trị trả về

Dạng thường dùng:

```java
String original = "abcdef";
String suffix = original.substring(2); // "cdef"
```

- **Đối tượng nhận:** `original` có kiểu `String`, không phải `null`.
- **Tham số:** `beginIndex` là một số nguyên `int`, biểu thị vị trí bắt đầu.
- **Kết quả:** Một giá trị `String` chứa các ký tự từ vị trí `beginIndex` đến cuối.
- **Chuỗi gốc:** Không bị thay đổi, vì `String` là đối tượng **bất biến** (*immutable*).

Trong cách nói bằng khoảng chỉ số, với `length = original.length()`, phần được chọn có khoảng **`[beginIndex, length)`**: có lấy vị trí bắt đầu, còn `length` là mốc kết thúc *không bao gồm*. Đây là ký hiệu khoảng nửa mở, không có ký tự ở vị trí `length`.

### Chỉ số hợp lệ

Phương thức yêu cầu:

\[
0 \leq \texttt{beginIndex} \leq \texttt{length()}
\]

| `beginIndex` | Kết quả | Lý do |
|---|---|---|
| `0` | Toàn bộ nội dung chuỗi | Bắt đầu từ ký tự đầu tiên |
| `1` đến `length() - 1` | Hậu tố bắt đầu từ chỉ số tương ứng | Bỏ qua phần đứng trước |
| `length()` | Chuỗi rỗng `""` | Không còn ký tự phía sau mốc bắt đầu |
| Số âm | Ném `StringIndexOutOfBoundsException` | Nằm trước đầu chuỗi |
| Lớn hơn `length()` | Ném `StringIndexOutOfBoundsException` | Vượt quá điểm kết thúc |

**Đừng nhầm `length()` với chỉ số của ký tự cuối.** Với chuỗi không rỗng, chỉ số của ký tự cuối là `length() - 1`. Nhưng `substring(length())` **vẫn hợp lệ** và trả về chuỗi rỗng.

Ví dụ, chuỗi `"Java"` có độ dài `4`:

```java
String s = "Java";

s.substring(0); // "Java"
s.substring(1); // "ava"
s.substring(2); // "va"
s.substring(3); // "a"
s.substring(4); // ""
// s.substring(5); // StringIndexOutOfBoundsException
```

Các dòng trên minh họa biểu thức bên trong một phương thức; chúng **không phải** một tệp Java độc lập.

## 3. Cơ chế từng bước

Xét:

```java
String word = "Programming";
String remainder = word.substring(7);
```

Đánh số theo chỉ số từ `0`:

```text
P  r  o  g  r  a  m  m  i  n  g
0  1  2  3  4  5  6  7  8  9  10
                     ^
                   index 7: m
```

`word.substring(7)` trả về `"ming"` (gồm các ký tự ở chỉ số 7, 8, 9 và 10). Phần `"Program"` đứng trước mốc bắt đầu không nằm trong kết quả. `word` vẫn giữ nguyên `"Programming"`.

Có thể hiểu bằng ba bước:

1. Xác định độ dài chuỗi (`word.length()` là `11`).
2. Kiểm tra `beginIndex` có nằm trong khoảng từ `0` đến `11`, kể cả `11`, hay không.
3. Trả về phần nội dung từ `beginIndex` đến hết; nếu bắt đầu tại `11`, kết quả là `""`.

Không cần gọi `.substring(beginIndex, word.length())` để thực hiện trường hợp phổ biến này; cách gọi một tham số thể hiện rõ ý định **lấy đến cuối**.

## 4. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Tạo tệp **`SubstringToEndDemo.java`**:

```java
public class SubstringToEndDemo {
    public static void main(String[] args) {
        String text = "Java Core";

        String suffix = text.substring(5);
        System.out.println("part=" + suffix);
        System.out.println("original=" + text);

        System.out.println("all=" + text.substring(0));
        System.out.println("atEnd=[" + text.substring(text.length()) + "]");

        String fileName = "report.csv";
        int lastDot = fileName.lastIndexOf('.');
        String extension = lastDot == -1
                ? "(none)"
                : fileName.substring(lastDot + 1);
        System.out.println("extension=" + extension);

        String path = "/users/42";
        int lastSlash = path.lastIndexOf('/');
        String lastSegment = path.substring(lastSlash + 1);
        System.out.println("lastSegment=" + lastSegment);

        String unicode = "A😀B";
        String afterA = unicode.substring(1);
        System.out.println("utf16Length=" + unicode.length());
        System.out.println("suffixCodePoints="
                + afterA.codePointCount(0, afterA.length()));

        try {
            text.substring(text.length() + 1);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("badIndex="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Trong thư mục chứa tệp, biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 SubstringToEndDemo.java
java SubstringToEndDemo
```

**Stdout dự kiến:**

```text
part=Core
original=Java Core
all=Java Core
atEnd=[]
extension=csv
lastSegment=42
utf16Length=4
suffixCodePoints=2
badIndex=StringIndexOutOfBoundsException
```

Giải thích các điểm đáng chú ý:

- `text.substring(5)` trả `"Core"`. Việc in lại `text` cho thấy chuỗi gốc không đổi.
- `text.substring(0)` lấy toàn bộ nội dung.
- `text.substring(text.length())` trả `""`, vì vậy khi kẹp trong `[...]` ta thấy `[]`.
- `lastIndexOf('.')` trả về vị trí dấu chấm cuối; `substring(lastDot + 1)` lấy phần **sau** dấu chấm, được `"csv"`.
- `lastIndexOf('/')` giúp xác định dấu phân tách cuối cùng của một đường dẫn minh họa, sau đó `substring(lastSlash + 1)` lấy `"42"`.
- Chuỗi `"A😀B"` có **4 UTF-16 code unit** (`A` = 1, emoji = 2, `B` = 1). Hậu tố sau `A` chứa **2 Unicode code point** (emoji và `B`).
- Chỉ số lớn hơn độ dài gây `StringIndexOutOfBoundsException`; ví dụ bắt ngoại lệ để phần trình diễn tiếp tục chạy.

> Chú ý: Ví dụ dùng `/` trong một chuỗi đường dẫn đơn giản để dạy cách trích xuất. Việc phân tích URL thật, đường dẫn hệ điều hành hay đường dẫn đã mã hóa cần API chuyên dụng tương ứng, tùy ngữ cảnh.

## 5. Trích xuất hậu tố sau ký tự phân cách

Một cách dùng thực tế là **tìm điểm bắt đầu rồi lấy toàn bộ phần còn lại**. Ví dụ:

```java
String record = "ID:12345";
int colon = record.indexOf(':');

if (colon >= 0) {
    String value = record.substring(colon + 1);
    System.out.println(value); // 12345
}
```

Tại sao phải `+ 1`? `indexOf(':')` trả về vị trí của dấu `:`. Nếu gọi `substring(colon)`, kết quả sẽ còn cả dấu phân cách (`":12345"`). Dùng `colon + 1` để bắt đầu ở ký tự kế tiếp.

Phải phân biệt hai mục tiêu:

```java
String text = "key=value";
int equal = text.indexOf('=');

String includingSeparator = text.substring(equal);     // "=value"
String excludingSeparator = text.substring(equal + 1); // "value"
```

Đây là những đoạn minh họa nằm trong phương thức, với chuỗi đầu vào chứa dấu `=` như đã biết. Nếu dấu phân cách **không chắc chắn tồn tại**, luôn kiểm tra kết quả tìm kiếm.

### Xử lý trường hợp không tìm thấy dấu phân cách

`indexOf(...)` và `lastIndexOf(...)` trả về `-1` khi không tìm thấy ký tự hoặc chuỗi cần tìm. Thông thường phải kiểm tra:

```java
static String valueAfterColon(String input) {
    int colon = input.indexOf(':');
    if (colon < 0) {
        return "";
    }
    return input.substring(colon + 1);
}
```

Phương thức trên trả `""` khi không có dấu `:`. Đây chỉ là **một lựa chọn thiết kế**; tùy bài toán, bạn cũng có thể muốn trả toàn bộ chuỗi, `Optional<String>` hoặc thông báo dữ liệu sai định dạng.

Một lỗi tinh tế cần tránh: nếu viết `substring(indexOf(':') + 1)` mà không kiểm tra, khi không tìm thấy dấu phân cách thì `indexOf` trả `-1`, cộng `1` thành `0`, và phương thức âm thầm trả về **toàn bộ chuỗi**. Nó không ném ngoại lệ nên dễ làm che giấu dữ liệu đầu vào sai.

## 6. Sử dụng độ dài để lấy N ký tự cuối

Để lấy **`n` UTF-16 code unit ở cuối**, điểm bắt đầu thường là:

\[
\texttt{start = text.length() - n}
\]

Ví dụ:

```java
String code = "INV-2026";
String year = code.substring(code.length() - 4);

System.out.println(year); // 2026
```

Vì `"INV-2026"` dài `8` code unit, `start = 8 - 4 = 4`; hậu tố từ chỉ số `4` là `"2026"`.

Để an toàn, cần đảm bảo `0 <= n <= text.length()`:

```java
static String lastUnits(String text, int n) {
    if (n < 0 || n > text.length()) {
        throw new IllegalArgumentException("n nằm ngoài độ dài chuỗi");
    }
    return text.substring(text.length() - n);
}
```

Phương thức `lastUnits` xử lý **code unit**, không đảm bảo luôn trích đúng `n` ký tự Unicode theo cảm nhận của con người. Với emoji hoặc ký tự bổ trợ được biểu diễn bằng cặp surrogate, điểm cắt có thể nằm giữa cặp. Phần tiếp theo giải thích cách tránh lỗi này.

## 7. Chỉ số của `String` sử dụng UTF-16

`String.length()` và các offset của `substring` đếm **UTF-16 code unit**, không nhất thiết là số Unicode code point hay ký tự hiển thị. Chẳng hạn, `"A😀B"` có độ dài `4`: emoji chiếm hai code unit. `substring(1)` bắt đầu đúng tại emoji, còn `substring(2)` bắt đầu giữa cặp surrogate và có thể để lại một nửa surrogate đứng lẻ.

Khi cần lấy đoạn theo **code point**, hãy chuyển số lượng code point thành offset UTF-16 bằng `offsetByCodePoints` trước khi cắt:

```java
String text = "A😀B";
int start = text.offsetByCodePoints(0, 2);
System.out.println(text.substring(start)); // B
```

Đây là ví dụ minh họa trong phương thức. Cắt theo code point vẫn có thể chia cụm chữ có dấu kết hợp hoặc emoji nhiều code point; những trường hợp hiển thị đó cần phân đoạn grapheme riêng.

## 8. Những trường hợp biên và lỗi thường gặp

### Lỗi A: Nghĩ rằng chỉ số bắt đầu từ 1

**Sai về ý định:**

```java
String s = "Java";
System.out.println(s.substring(1)); // ava
```

Để lấy cả `"Java"`, bắt đầu từ **`0`**, không phải `1`.

### Lỗi B: Cho rằng chỉ số bằng `length()` là không hợp lệ

```java
String s = "abc";
System.out.println("[" + s.substring(3) + "]"); // []
```

Chỉ số bằng độ dài là hợp lệ và trả chuỗi rỗng. Chỉ số **lớn hơn** `length()` mới vượt ranh giới.

### Lỗi C: Bỏ qua giá trị trả về

```java
String s = "abcdef";
s.substring(3);
System.out.println(s); // abcdef
```

`String` bất biến nên `substring` **không sửa tại chỗ**. Nếu muốn giữ hậu tố:

```java
s = s.substring(3);
System.out.println(s); // def
```

Việc gán lại thay đổi giá trị biến `s`, chứ không sửa nội dung đối tượng `String` ban đầu.

### Lỗi D: Dùng kết quả `indexOf` mà không kiểm tra

```java
String s = "no-separator";
int index = s.indexOf(':'); // -1
String part = s.substring(index + 1); // Chính là "no-separator"
```

Không có dấu `:` nhưng phép cộng `-1 + 1` thành `0`. Cần kiểm tra `index >= 0` nếu việc không có dấu phân cách là trường hợp cần xử lý riêng.

### Lỗi E: Truyền chỉ số âm hoặc vượt độ dài

```java
String s = "abc";
// s.substring(-1); // Ném StringIndexOutOfBoundsException
// s.substring(4);  // Ném StringIndexOutOfBoundsException
```

Có thể kiểm tra ranh giới trước khi gọi:

```java
static String fromIndex(String text, int beginIndex) {
    if (beginIndex < 0 || beginIndex > text.length()) {
        throw new IllegalArgumentException("beginIndex không hợp lệ");
    }
    return text.substring(beginIndex);
}
```

Phương thức bọc này minh họa cách chọn ngoại lệ của ứng dụng. Nếu gọi trực tiếp `substring` với chỉ số sai, Java ném `StringIndexOutOfBoundsException`.

### Lỗi F: Gọi phương thức trên `null`

```java
String s = null;
// s.substring(0); // Ném NullPointerException
```

`null` không phải một đối tượng `String`, nên không thể gọi phương thức trên nó. Đây là lỗi **khác** với chỉ số không hợp lệ. Kiểm tra đầu vào nếu `null` được phép xuất hiện trong thiết kế của chương trình.

### Lỗi G: Nhầm `substring(int)` với `substring(int, int)`

Hai cách gọi:

```java
String s = "abcdefgh";

s.substring(3);    // "defgh": từ 3 đến hết
s.substring(3, 6); // "def": lấy các chỉ số 3, 4, 5; không gồm 6
```

Dạng hai tham số cho phép chỉ định riêng điểm kết thúc (`endIndex` không bao gồm). Dạng một tham số **luôn** lấy tới hết, nên chọn dạng này khi đúng ý định và không phải tính toán chỉ số cuối một cách thừa thãi.

## 9. Phân biệt với những thao tác gần giống

| Bài toán | Phương thức phù hợp | Ví dụ |
|---|---|---|
| Lấy phần từ một chỉ số đến cuối | `substring(beginIndex)` | `"abcdef".substring(3)` → `"def"` |
| Lấy phần giữa hai mốc | `substring(beginIndex, endIndex)` | `"abcdef".substring(1, 4)` → `"bcd"` |
| Lấy vị trí bắt đầu của một đoạn | `indexOf(...)` | `"a:b".indexOf(':')` → `1` |
| Lấy vị trí xuất hiện cuối | `lastIndexOf(...)` | `"a:b:c".lastIndexOf(':')` → `3` |
| Tìm số lượng UTF-16 code unit | `length()` | `"Java".length()` → `4` |
| Trích từ vị trí tính theo code point | `offsetByCodePoints(...)` rồi `substring(...)` | Tránh cắt vào giữa surrogate pair |

`substring` chỉ **trích xuất một phạm vi đã xác định**. Nếu chưa biết điểm bắt đầu nằm ở đâu, thường kết hợp với `indexOf`/`lastIndexOf` hoặc một thuật toán tìm vị trí theo quy tắc dữ liệu.

## 10. Lưu ý về hiệu năng và đối tượng trả về

`substring` trả về một giá trị `String` bất biến; không có lời hứa công khai rằng kết quả luôn là instance mới, luôn là instance nguồn hay có cơ chế bộ nhớ cụ thể. Một triển khai có thể tối ưu trường hợp lấy toàn bộ chuỗi hoặc chuỗi rỗng. Vì vậy, khi so nội dung, hãy dùng `equals` thay vì `==`.

Đối với xử lý lượng lớn chuỗi, nên đo hiệu năng và mức cấp phát trên JDK cùng dữ liệu thực tế. Không tạo thêm bản sao chỉ vì giả định `substring` nhất định dùng chung hoặc sao chép vùng nhớ.

## 11. Bài tập và đáp án

**Bài 1.** Với `String s = "Hello World";`, hãy lấy `"World"`.

**Đáp án:**

```java
String result = s.substring(6);
```

Dấu cách nằm ở chỉ số `5`, chữ `W` ở chỉ số `6`.

**Bài 2.** Với `"ABC"`, ba kết quả của `substring(0)`, `substring(2)` và `substring(3)` là gì?

**Đáp án:** Lần lượt là `"ABC"`, `"C"` và `""`.

**Bài 3.** Với `"token:abc:def"`, lấy mọi ký tự sau **dấu `:` đầu tiên**.

**Đáp án:**

```java
String input = "token:abc:def";
int p = input.indexOf(':');
String value = p < 0 ? "" : input.substring(p + 1);
// value = "abc:def"
```

Nếu cần lấy sau dấu `:` **cuối cùng**, đổi `indexOf(':')` thành `lastIndexOf(':')`, khi đó giá trị là `"def"`.

**Bài 4.** Vì sao `"A😀B".substring(2)` cần thận trọng?

**Đáp án:** Chỉ số `2` rơi vào giữa hai UTF-16 code unit dùng để biểu diễn emoji, có thể làm vỡ surrogate pair. Nên xác định ranh giới code point (hoặc grapheme, tùy bài toán) trước khi cắt.

**Bài 5.** Đoạn sau in gì?

```java
String s = "12345";
s.substring(3);
System.out.println(s);
```

**Đáp án:** `12345`. Giá trị `"45"` được trả về nhưng đã bị bỏ qua, còn chuỗi gốc không đổi.

## 12. Ghi nhớ

`String.substring(beginIndex)` có thể được đọc là: **“Lấy chuỗi từ chỉ số `beginIndex` (bao gồm) đến hết”**. Chỉ số bắt đầu từ `0`, miền hợp lệ là **`0` đến `length()` (bao gồm cả hai đầu)**, bắt đầu ở `length()` cho chuỗi rỗng, còn ra ngoài miền thì ném `StringIndexOutOfBoundsException`. Kết quả là một giá trị `String` cần được lưu hoặc sử dụng, chuỗi gốc vẫn bất biến. Khi dữ liệu có emoji hoặc ký tự Unicode bổ trợ, hãy nhớ chỉ số `String` đo theo **UTF-16 code unit**, không mặc nhiên theo ký tự hiển thị.
