# Trường hợp biên âm, vượt độ dài hoặc đảo thứ tự khi trích xuất chuỗi

Khi trích xuất một phần nội dung bằng `String.substring(...)` trong Java, lỗi dễ gặp nhất không nằm ở ký tự cần lấy mà ở **phạm vi chỉ số**: vị trí bắt đầu âm, vị trí kết thúc vượt quá độ dài hoặc hai vị trí bị đảo ngược. Những trường hợp này cần được phân biệt với các phạm vi **hợp lệ nhưng rỗng**, cũng như phạm vi hợp lệ theo UTF-16 nhưng cắt giữa một ký tự Unicode.

Bài học tập trung vào quy tắc biên của `substring(beginIndex)`, `substring(beginIndex, endIndex)` và `subSequence(start, end)`, cách đọc lỗi, cách kiểm tra dữ liệu đầu vào và những tình huống thực tế như lấy hậu tố, dùng kết quả `indexOf()` hoặc trích xuất văn bản có emoji.

## 1. Quy ước chỉ số cần giữ trước khi kiểm tra lỗi

`substring(begin, end)` lấy khoảng nửa mở `[begin, end)` tính theo UTF-16 code unit: lấy `begin`, bỏ `end`, và có độ dài `end - begin` khi hợp lệ. Với nguồn dài `n`, các **biên** hợp lệ có thể nhận giá trị từ `0` đến `n`, dù chỉ số ký tự cuối là `n - 1`.

```java
String s = "Java";
System.out.println(s.substring(1, 3)); // av
System.out.println(s.substring(4, 4).isEmpty()); // true
```

Trọng tâm xử lý lỗi là phân biệt **biên hợp lệ nhưng rỗng** với biên âm, vượt độ dài và đảo thứ tự. `substring(begin)` tương đương về nội dung với `substring(begin, s.length())` khi hợp lệ.

## 2. Ba điều kiện bắt buộc của phạm vi `[begin, end)`

Công thức hợp lệ cho `text.substring(begin, end)` là:

```text
0 <= begin <= end <= text.length()
```

Chỉ cần **một** trong các điều kiện sau xảy ra, phạm vi đã sai:

1. **Chỉ số âm:** `begin < 0`, hoặc `end < 0`. Ví dụ `substring(-1, 2)`, `substring(0, -1)`.
2. **Vượt độ dài:** `end > length()` hoặc `begin > length()`. Ví dụ chuỗi dài 4 nhưng yêu cầu `substring(0, 5)`, `substring(5)`.
3. **Đảo thứ tự:** `begin > end`, kể cả khi cả hai đều nằm trong khoảng từ 0 đến `length()`. Ví dụ `substring(3, 1)`.

Java báo lỗi **`IndexOutOfBoundsException`** khi vi phạm hợp đồng chỉ số của `substring`. Chi tiết thông báo ngoại lệ có thể khác nhau theo phiên bản JDK; không nên viết logic nghiệp vụ dựa vào chuỗi thông báo đó. Ngoại lệ xảy ra **tại lời gọi trích xuất**, trước khi nhận được bất kỳ chuỗi kết quả nào.

Để kiểm tra nhanh, có thể dùng biểu thức:

```java
boolean valid = begin >= 0
        && begin <= end
        && end <= text.length();
```

Đây là **đoạn mã minh họa**, giả sử `text != null`. Nếu cả ba mệnh đề đều đúng thì `begin` và `end` đều nằm trong ranh giới hợp lệ; không cần thêm điều kiện `begin <= text.length()` vì nó đã suy ra từ `begin <= end <= text.length()`. Nếu `text == null` thì truy cập `text.length()` sẽ ném `NullPointerException`, một lỗi khác lỗi chỉ số.

### Không đồng nhất phạm vi sai với phạm vi rỗng

- `begin == end` là **hợp lệ**, cho kết quả `""`.
- `begin > end` là **không hợp lệ**, Java ném ngoại lệ.
- Chuỗi nguồn `""` có độ dài 0 nên chỉ có một phạm vi hợp lệ: `substring(0, 0)`; riêng phiên bản một tham số thì `substring(0)`.
- `substring(0, length())` luôn là một phạm vi hợp lệ nếu chuỗi nguồn không null.
- `substring(length(), length())` cũng luôn hợp lệ; nhiều thuật toán cần trường hợp này để mô tả “phần đuôi không có ký tự”.

## 3. Ví dụ Java 17+ kiểm tra từng trường hợp biên

Lưu tệp sau thành **`SubstringBoundsDemo.java`**:

```java
public class SubstringBoundsDemo {
    private static void test(String source, int begin, int end) {
        try {
            String part = source.substring(begin, end);
            System.out.println("[" + begin + "," + end + ") -> <"
                    + part + "> (length=" + part.length() + ")");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("[" + begin + "," + end + ") -> INVALID");
        }
    }

    public static void main(String[] args) {
        String value = "Java";
        System.out.println("source length: " + value.length());

        test(value, 0, 4);
        test(value, 1, 3);
        test(value, 2, 2);
        test(value, 4, 4);

        test(value, -1, 2);
        test(value, 0, -1);
        test(value, 0, 5);
        test(value, 5, 5);
        test(value, 3, 2);

        test("", 0, 0);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac SubstringBoundsDemo.java
java SubstringBoundsDemo
```

**Stdout:**

```text
source length: 4
[0,4) -> <Java> (length=4)
[1,3) -> <av> (length=2)
[2,2) -> <> (length=0)
[4,4) -> <> (length=0)
[-1,2) -> INVALID
[0,-1) -> INVALID
[0,5) -> INVALID
[5,5) -> INVALID
[3,2) -> INVALID
[0,0) -> <> (length=0)
```

Trong ví dụ, chỉ bắt `IndexOutOfBoundsException` để **minh họa phân loại** các trường hợp. Trong ứng dụng thật, tốt hơn nên kiểm tra tham số hoặc xác định chính sách lỗi trước khi gọi `substring()`; bắt rồi bỏ qua mọi ngoại lệ có thể che mất lỗi lập trình.

## 4. So sánh miền chỉ số để tránh dùng sai API

| API | Điều kiện hợp lệ | Điểm cần kiểm tra |
| --- | --- | --- |
| `s.substring(begin)` | `0 <= begin <= n` | `begin == n` cho chuỗi rỗng |
| `s.substring(begin, end)` | `0 <= begin <= end <= n` | Thứ tự hai biên phải đúng |
| `s.subSequence(begin, end)` | `0 <= begin <= end <= n` | Trả kiểu khai báo `CharSequence` |
| `s.charAt(index)` | `0 <= index < n` | `charAt(n)` không hợp lệ |

Cùng một offset `n` có thể hợp lệ cho **ranh giới** của `substring` nhưng không hợp lệ cho `charAt`. Tương tự, `substring(k, k)` không đọc code unit ở `k`; nó trả đoạn rỗng, còn `substring(k, k + 1)` chỉ lấy một code unit nếu `k < n`. Các phương thức không tự điều chỉnh chỉ số sai.

## 5. Lỗi off-by-one: `end` bị loại trừ

Lỗi lệch một đơn vị (*off-by-one*) thường xảy ra vì nhầm `end` là vị trí ký tự cuối **được lấy**. Ví dụ muốn lấy ký tự ở vị trí 1, 2 và 3 của `"Java"`:

```java
"Java".substring(1, 3); // "av": chỉ lấy vị trí 1 và 2
"Java".substring(1, 4); // "ava": lấy vị trí 1, 2, 3
```

Mọi biểu thức trên là đoạn mã minh họa.

Nếu chỉ số kết thúc **bao gồm** theo yêu cầu bên ngoài là `lastInclusive`, phép trích xuất có thể dùng `substring(begin, lastInclusive + 1)` **chỉ sau khi** đã xác minh `lastInclusive` là chỉ số phần tử có thật, tức `0 <= lastInclusive < length`, và `begin <= lastInclusive`. Không nên tự cộng 1 cho một giá trị bất kỳ vì có thể vượt `length()` hoặc gây tràn số nguyên với giá trị rất lớn.

Một kiểu yêu cầu khác là “lấy **count** code unit từ vị trí **start**”. Dạng tự nhiên là `substring(start, start + count)`, nhưng cần bảo vệ:

- `start >= 0`;
- `count >= 0`;
- `start <= length()`;
- `count <= length() - start`.

Cách kiểm tra bằng `count <= length() - start` tránh phải tính `start + count` trước khi bảo đảm không tràn số nguyên. Chỉ tính tổng sau khi đã xác thực.

## 6. Kiểm tra đầu vào trước khi trích xuất

Có hai cách hợp lý tùy hợp đồng nghiệp vụ: **từ chối phạm vi sai** bằng ngoại lệ có thông điệp rõ ràng, hoặc **chấp nhận điều chỉnh phạm vi** nếu yêu cầu bài toán cho phép. Không nên âm thầm ép mọi chỉ số sai vào khoảng hợp lệ khi người gọi cần được biết dữ liệu đầu vào có lỗi.

### 6.1. Chính sách nghiêm ngặt: phạm vi sai phải báo lỗi

**`StrictSliceDemo.java`**

```java
import java.util.Objects;

public class StrictSliceDemo {
    private static String slice(String text, int begin, int end) {
        Objects.requireNonNull(text, "text");

        if (begin < 0 || end < begin || end > text.length()) {
            throw new IllegalArgumentException(
                    "Invalid slice: [" + begin + "," + end
                    + ") for length " + text.length());
        }

        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        System.out.println("<" + slice("Java", 1, 3) + ">");
        System.out.println("<" + slice("Java", 4, 4) + ">");
        System.out.println("<" + slice("", 0, 0) + ">");

        try {
            slice("Java", 3, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected reversed bounds");
        }

        try {
            slice("Java", -1, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected negative begin");
        }
    }
}
```

```bash
javac StrictSliceDemo.java
java StrictSliceDemo
```

**Stdout:**

```text
<av>
<>
<>
Rejected reversed bounds
Rejected negative begin
```

Trong phương thức `slice`, điều kiện gộp đã đủ để chặn `begin` âm, `end` nằm trước `begin`, hoặc `end` vượt độ dài. Nếu `begin > length` thì không thể đồng thời thỏa `end >= begin` và `end <= length`, nên cũng bị chặn. Ở đây mã **chủ động** ném `IllegalArgumentException` cho tham số không đạt hợp đồng của hàm trợ giúp; đây không phải lời khẳng định `substring` tự ném ngoại lệ đó. Một API có thể lựa chọn loại ngoại lệ hoặc kiểu kết quả khác cho phù hợp thiết kế.

### 6.2. Chính sách giới hạn phạm vi: chỉ khi đề bài cho phép

Giả sử yêu cầu là “lấy tối đa `maxUnits` code unit đầu tiên”; nếu `maxUnits` lớn hơn độ dài thì chỉ lấy toàn bộ chuỗi, nhưng giá trị âm vẫn là đầu vào không hợp lệ:

**`PrefixLimitDemo.java`**

```java
import java.util.Objects;

public class PrefixLimitDemo {
    private static String prefixAtMost(String text, int maxUnits) {
        Objects.requireNonNull(text, "text");
        if (maxUnits < 0) {
            throw new IllegalArgumentException("maxUnits must be >= 0");
        }

        int end = Math.min(maxUnits, text.length());
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        System.out.println("<" + prefixAtMost("Java", 2) + ">");
        System.out.println("<" + prefixAtMost("Java", 10) + ">");
        System.out.println("<" + prefixAtMost("Java", 0) + ">");
        System.out.println("<" + prefixAtMost("", 3) + ">");
    }
}
```

```bash
javac PrefixLimitDemo.java
java PrefixLimitDemo
```

**Stdout:**

```text
<Ja>
<Java>
<>
<>
```

`Math.min(maxUnits, text.length())` phù hợp vì tên và hợp đồng của hàm nói rõ **“tối đa”**. Nếu người gọi yêu cầu **chính xác 10 ký tự** mà chuỗi chỉ dài 4, cắt còn 4 một cách lặng lẽ có thể che lỗi dữ liệu. Không nên đảo `begin/end`, lấy trị tuyệt đối chỉ số âm hoặc tự ý đưa mọi phạm vi về giới hạn mà không được phép theo yêu cầu nghiệp vụ.

## 7. Trường hợp âm xuất hiện từ phép tính và API tìm kiếm

### 7.1. Lấy `n` ký tự cuối khi `n` lớn hơn độ dài

Mẫu quen thuộc:

```java
String tail = text.substring(text.length() - n);
```

Chỉ đúng khi `0 <= n <= text.length()`. Nếu `text = "Java"` và `n = 5`, điểm bắt đầu là `4 - 5 = -1`, gây ngoại lệ. Nếu `n = -1`, điểm bắt đầu là `5`, cũng vượt chiều dài. Với `n = 0`, kết quả hợp lệ là `""`.

Bản có kiểm tra nghiêm ngặt:

**`SuffixBoundsDemo.java`**

```java
import java.util.Objects;

public class SuffixBoundsDemo {
    private static String lastUnits(String text, int n) {
        Objects.requireNonNull(text, "text");
        if (n < 0 || n > text.length()) {
            throw new IllegalArgumentException("Invalid suffix length: " + n);
        }
        return text.substring(text.length() - n);
    }

    public static void main(String[] args) {
        System.out.println("<" + lastUnits("Java", 2) + ">");
        System.out.println("<" + lastUnits("Java", 4) + ">");
        System.out.println("<" + lastUnits("Java", 0) + ">");

        try {
            lastUnits("Java", 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected suffix longer than source");
        }
    }
}
```

```bash
javac SuffixBoundsDemo.java
java SuffixBoundsDemo
```

**Stdout:**

```text
<va>
<Java>
<>
Rejected suffix longer than source
```

Tên `lastUnits` nói rõ `n` là **số code unit UTF-16**, chưa chắc là số ký tự mà người dùng nhìn thấy; ở phần Unicode bên dưới sẽ chỉ ra giới hạn này.

### 7.2. `indexOf()` trả `-1` khi không tìm thấy

Nhiều lỗi biên âm xuất phát từ việc lấy kết quả `indexOf()` rồi đưa thẳng vào `substring()`:

```java
String line = "name=value";
int separator = line.indexOf(':'); // -1 vì không có dấu ':'
String head = line.substring(0, separator); // sai: end = -1
```

Đây là đoạn mã minh họa cố tình sai, không phải chương trình hoàn chỉnh. `-1` là **giá trị báo không tìm thấy**, không phải một chỉ số hợp lệ. Hãy xử lý trước:

**`DelimiterDemo.java`**

```java
public class DelimiterDemo {
    private static void showAfterColon(String line) {
        int separator = line.indexOf(':');
        if (separator < 0) {
            System.out.println("No delimiter");
            return;
        }

        String value = line.substring(separator + 1);
        System.out.println("Value=<" + value + ">");
    }

    public static void main(String[] args) {
        showAfterColon("user:admin");
        showAfterColon("user:");
        showAfterColon("user=admin");
        showAfterColon(":start");
    }
}
```

```bash
javac DelimiterDemo.java
java DelimiterDemo
```

**Stdout:**

```text
Value=<admin>
Value=<>
No delimiter
Value=<start>
```

Khi dấu phân cách nằm ở cuối, `separator + 1 == length()` vẫn là ranh giới hợp lệ, cho chuỗi rỗng. Khi ở đầu, `substring(1)` hợp lệ nếu chuỗi có một hoặc nhiều code unit. Chỉ khi không tìm thấy mới cần trả trạng thái khác hoặc báo lỗi theo yêu cầu ứng dụng.

## 8. Biên số học đúng chưa chắc là biên Unicode đúng

Kiểm tra `0 <= begin <= end <= length` chỉ bảo vệ phạm vi UTF-16. Với `"A😊B"`, `length() == 4` và `substring(1, 2)` hoàn toàn **hợp lệ về chỉ số**, nhưng chỉ lấy high surrogate của emoji. Nếu muốn lấy trọn một code point tại vị trí UTF-16 `1`, có thể viết:

```java
String text = "A😊B";
int end = text.offsetByCodePoints(1, 1);
String emoji = text.substring(1, end); // lấy đúng emoji
```

Khi xác thực đầu vào, hãy tách câu hỏi **“offset có nằm trong phạm vi hợp lệ?”** khỏi câu hỏi **“offset có chia đôi code point hoặc grapheme cluster không?”**. API code point xử lý surrogate pair; phân đoạn grapheme giải quyết thêm dấu kết hợp và emoji nhiều code point.

## 9. Cách thiết kế và kiểm thử các trường hợp biên

### 9.1. Xác định chính sách trước khi triển khai

Trước mỗi hàm trích xuất, nên trả lời:

1. Tham số là **offset UTF-16**, số code point hay số cụm ký tự hiển thị?
2. Vị trí kết thúc là **exclusive** hay người gọi đang cung cấp chỉ số cuối **inclusive**?
3. Nếu đầu vào âm, vượt độ dài hoặc đảo chiều, hàm sẽ **ném ngoại lệ**, trả kết quả thể hiện thất bại, hay cắt tới biên gần nhất?
4. Chuỗi rỗng và phạm vi `begin == end` có hợp lệ theo yêu cầu hay không?
5. Nếu ranh giới số học đúng nhưng cắt nửa surrogate/grapheme, hàm có phải từ chối hay điều chỉnh ranh giới không?

Cùng một `substring` có thể được dùng cho API nghiêm ngặt hay API “lấy tối đa”; chính sách đầu vào do hàm bao ngoài quyết định. Nếu văn bản đến từ người dùng hay hệ thống ngoài, cần tránh biến một chỉ số không tin cậy thành ngoại lệ không được xử lý. Nếu chỉ số đến từ mã nội bộ mà đáng lẽ luôn đúng, ngoại lệ có thể là tín hiệu phát hiện lỗi lập trình hữu ích.

### 9.2. Ma trận kiểm thử nhanh

Với `text = "Java"`, `n = 4`, các ca kiểm tra thiết yếu gồm:

| Trường hợp | Input | Kết quả mong đợi |
|---|---|---|
| Toàn bộ chuỗi | `[0, 4)` | `"Java"` |
| Đoạn giữa | `[1, 3)` | `"av"` |
| Phạm vi rỗng giữa chuỗi | `[2, 2)` | `""` |
| Phạm vi rỗng tại cuối | `[4, 4)` | `""` |
| Chỉ số âm ở đầu | `[-1, 2)` | Ngoại lệ |
| Chỉ số âm ở cuối | `[0, -1)` | Ngoại lệ |
| Vượt chiều dài ở cuối | `[0, 5)` | Ngoại lệ |
| Cả hai vượt chiều dài | `[5, 5)` | Ngoại lệ |
| Đảo thứ tự | `[3, 2)` | Ngoại lệ |
| Chuỗi rỗng | `""` và `[0, 0)` | `""` |
| Chuỗi rỗng, index 1 | `""` và `[0, 1)` | Ngoại lệ |
| Ký tự ngoài BMP | `"A😊B"`, `[1, 2)` | Phạm vi hợp lệ, nhưng cắt đôi surrogate |

Các kiểm thử này kiểm tra **ranh giới**, **trường hợp rỗng**, **độ dài**, và **tính đúng đắn Unicode** riêng biệt. Đừng coi việc `substring()` không ném ngoại lệ là bằng chứng phần cắt phù hợp với ý nghĩa “ký tự” của sản phẩm.

### 9.3. Bẫy hay gặp khi sửa lỗi

- **Tự đảo tham số** nếu `begin > end`: không thể biết người gọi gõ nhầm hay cố ý truyền phạm vi đảo; sửa âm thầm có thể thay đổi ý nghĩa kết quả.
- **Đổi chỉ số âm thành 0** khi lỗi đến từ `indexOf() == -1`: điều đó có thể khiến chương trình trích dữ liệu sai thay vì nhận ra dấu phân cách không tồn tại.
- **Cắt tối đa `length`** trong hàm yêu cầu chính xác số ký tự: dữ liệu thiếu sẽ bị che giấu. Chỉ clamp khi hợp đồng hàm cho phép.
- **Dùng `charAt(length)` vì `substring(length)` hợp lệ**: hai API có miền chỉ số khác nhau.
- **Quên kết thúc loại trừ**: `substring(0, length - 1)` bỏ ký tự cuối; `substring(0, length + 1)` vượt biên.
- **Dùng `length()` làm số “ký tự hiển thị”**: chuỗi có surrogate pair hoặc dấu kết hợp làm phép tính lệch với cách người đọc cảm nhận.

## 10. Tự kiểm tra

Đoán kết quả hoặc trường hợp ném ngoại lệ khi `s = "ABCD"`:

```java
String s = "ABCD";

System.out.println("<" + s.substring(1, 1) + ">");
System.out.println("<" + s.substring(s.length()) + ">");
System.out.println("<" + s.substring(0, s.length()) + ">");

// Xét riêng từng dòng bên dưới:
// s.substring(-1, 2);
// s.substring(2, 5);
// s.substring(3, 2);
// s.substring(4, 4);
// s.charAt(4);
```

**Đáp án:**

- Ba lệnh `println` lần lượt in `<>`, `<>` và `<ABCD>`.
- `substring(-1, 2)` sai vì bắt đầu âm.
- `substring(2, 5)` sai vì `end = 5 > length = 4`.
- `substring(3, 2)` sai vì `begin > end`.
- `substring(4, 4)` hợp lệ, trả `""`.
- `charAt(4)` sai vì miền hợp lệ của `charAt` chỉ là `0..3`.

**Quy tắc nhớ nhanh:**

```text
substring(begin, end):
    0 <= begin <= end <= length

substring(begin):
    0 <= begin <= length

charAt(index):
    0 <= index < length
```

Cần nhớ thêm một bước: các bất đẳng thức trên bảo vệ **phạm vi UTF-16**; muốn trích đúng một code point hoặc cụm ký tự hiển thị, phải dùng ranh giới Unicode tương ứng. Khi ứng dụng phân biệt rõ chỉ số âm, chỉ số vượt độ dài, thứ tự đảo, phạm vi rỗng và giới hạn Unicode, các thao tác trích xuất trở nên dễ kiểm tra và khó phát sinh lỗi dữ liệu âm thầm.
