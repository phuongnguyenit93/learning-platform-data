# `subSequence` và hợp đồng `CharSequence` trong Java

Khi cần lấy một phần của văn bản, Java có cả `String.substring(start, end)` và `subSequence(start, end)`. Điểm đáng học ở `subSequence` không chỉ là hai chỉ số cắt chuỗi: đây là **phương thức của giao diện `CharSequence`**, nên cùng một lời gọi có thể áp dụng cho `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` hoặc lớp khác triển khai giao diện này.

Điều quan trọng là phân biệt **hợp đồng chung của `CharSequence`** với **hành vi cụ thể của từng implementation**. Giao diện quy định những ký tự mà đoạn con phải biểu diễn và ý nghĩa của chỉ số; nó **không hứa** rằng kết quả luôn là `String`, luôn là bản sao độc lập, luôn là view hay luôn bất biến.

## 1. `CharSequence` là gì?

`java.lang.CharSequence` là giao diện trừu tượng cho một chuỗi có thể đọc được theo **các đơn vị `char` (UTF-16 code unit)**. Các thao tác cốt lõi là:

| Phương thức | Ý nghĩa |
| --- | --- |
| `int length()` | Số đơn vị `char` (UTF-16 code unit), không nhất thiết bằng số ký tự Unicode mà người đọc cảm nhận |
| `char charAt(int index)` | Đọc đơn vị `char` ở chỉ số `index`, đánh số từ 0 |
| `CharSequence subSequence(int start, int end)` | Lấy một dãy con theo khoảng chỉ số `[start, end)` |
| `String toString()` | Tạo biểu diễn `String` có các đơn vị ký tự theo đúng thứ tự của dãy |
| `boolean isEmpty()` | Với Java 17+, kiểm tra `length() == 0`; đây là phương thức mặc định của giao diện |
| `IntStream chars()` / `IntStream codePoints()` | Duyệt các UTF-16 code unit hoặc Unicode code point; ý nghĩa không giống nhau với ký tự ngoài BMP |

Các lớp thường gặp:

- `String`: nội dung bất biến; thích hợp cho kết quả văn bản ổn định.
- `StringBuilder`: nội dung thay đổi được, không bảo đảm thread-safe.
- `StringBuffer`: nội dung thay đổi được, nhiều thao tác được đồng bộ hóa; điều này không có nghĩa mọi workflow nhiều bước tự động nguyên tử.
- `CharBuffer` trong `java.nio`: bộ đệm ký tự, có `position`/`limit` và có thể tạo các đoạn nhìn vào vùng dữ liệu dùng chung.
- Một lớp do ứng dụng tự viết cũng có thể triển khai `CharSequence`.

Ví dụ phương thức nhận `CharSequence`:

```java
static void show(CharSequence text) {
    System.out.println("Length: " + text.length());
    System.out.println(text.subSequence(0, Math.min(3, text.length())));
}
```

Đây là **đoạn minh họa phương thức**, cần đặt trong một lớp để biên dịch. Lời gọi `show("Java")` hoặc `show(new StringBuilder("Java"))` đều hợp lệ. Khi chỉ cần đọc các ký tự, khai báo tham số là `CharSequence` giúp API nhận nhiều kiểu đầu vào. Nếu cần các tính năng riêng của `String`, hãy khai báo `String` hoặc chuyển đổi có chủ đích.

## 2. Hợp đồng của `subSequence(start, end)`

Trong giao diện, phương thức có chữ ký:

```java
CharSequence subSequence(int start, int end);
```

Khoảng được hiểu là **nửa mở** (*half-open interval*):

- `start` là chỉ số ký tự **được lấy**, bắt đầu từ 0.
- `end` là vị trí **dừng, không lấy ký tự tại đó**.
- Độ dài đoạn con bằng `end - start`.
- Ký tự thứ `i` của đoạn con tương ứng với ký tự thứ `start + i` của dãy gốc, xét tại thời điểm dữ liệu không có thay đổi gây xung đột.
- Khoảng hợp lệ cần `0 <= start <= end <= length()`.
- Nếu chỉ số không hợp lệ, lời gọi ném `IndexOutOfBoundsException` hoặc ngoại lệ con của nó.
- `start == end` là hợp lệ và tạo dãy con rỗng, kể cả khi cả hai bằng `length()`.

Ví dụ với `"ABCDE"`, đánh số:

```text
Ký tự:    A   B   C   D   E
Chỉ số:   0   1   2   3   4
Ranh giới:0   1   2   3   4   5

subSequence(1, 4) --> "BCD"
subSequence(0, 5) --> "ABCDE"
subSequence(2, 2) --> ""
subSequence(5, 5) --> ""
subSequence(4, 2) --> lỗi
```

Sự nhất quán của khoảng `[start, end)` giúp tính độ dài và cắt các đoạn liên tiếp dễ dàng: `text.subSequence(0, cut)` và `text.subSequence(cut, text.length())` phủ toàn bộ dãy nếu `cut` hợp lệ, không lặp và không bỏ vị trí nào.

### Ví dụ 1: kiểm tra các ranh giới

Tạo tệp `SubSequenceBoundsDemo.java`:

```java
public class SubSequenceBoundsDemo {
    public static void main(String[] args) {
        CharSequence text = "ABCDE";

        CharSequence middle = text.subSequence(1, 4);
        CharSequence empty = text.subSequence(5, 5);

        System.out.println(middle);
        System.out.println(middle.length());
        System.out.println(empty.isEmpty());
        System.out.println("[" + empty + "]");

        try {
            text.subSequence(4, 2);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("Invalid range");
        }
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac SubSequenceBoundsDemo.java
java SubSequenceBoundsDemo
```

Kết quả:

```text
BCD
3
true
[]
Invalid range
```

Không nên phụ thuộc vào chính xác tên lớp ngoại lệ con hay thông điệp lỗi do `String`, `CharBuffer` hoặc implementation khác tạo ra. Nếu cần tự kiểm tra dữ liệu đầu vào để báo lỗi riêng, điều kiện `0 <= start && start <= end && end <= text.length()` là điều kiện cốt lõi.

## 3. Với `String`, `subSequence` và `substring` liên quan thế nào?

`String` triển khai `CharSequence`. Với một `String`, hai phương thức:

```java
text.substring(start, end)
text.subSequence(start, end)
```

trả về cùng **nội dung** đoạn chuỗi. API `String.subSequence` được quy định hoạt động như `String.substring`; trong Java 17, kết quả thực tế của `subSequence` trên `String` là một đối tượng kiểu `String`, dù chữ ký khai báo trả về `CharSequence`.

Điểm khác dễ nhìn thấy nhất ở nơi gọi là **kiểu trả về tại thời điểm biên dịch**:

- `String.substring(int, int)` khai báo trả về `String`; có thể gọi tiếp `String` API trực tiếp.
- `String.subSequence(int, int)` khai báo trả về `CharSequence`; chỉ những thành viên của `CharSequence` và `Object` được nhìn thấy qua kiểu này, trừ khi chuyển đổi kiểu phù hợp.

### Ví dụ 2: nội dung bằng nhau nhưng kiểu khai báo khác nhau

Tạo `StringSubSequenceDemo.java`:

```java
public class StringSubSequenceDemo {
    public static void main(String[] args) {
        String source = "Programming";

        String bySubstring = source.substring(3, 7);
        CharSequence bySubSequence = source.subSequence(3, 7);

        System.out.println(bySubstring);
        System.out.println(bySubSequence);
        System.out.println(bySubstring.equals(bySubSequence));
        System.out.println(bySubSequence instanceof String);

        String converted = bySubSequence.toString();
        System.out.println(converted.toUpperCase());
    }
}
```

```bash
javac StringSubSequenceDemo.java
java StringSubSequenceDemo
```

Kết quả:

```text
gram
gram
true
true
GRAM
```

Từng bước:

1. `substring(3, 7)` đọc các chỉ số `3, 4, 5, 6` của `Programming`, cho ra `"gram"`.
2. `subSequence(3, 7)` trên chính `String` cho ra dãy tương đương.
3. `bySubstring.equals(bySubSequence)` trả về `true` vì đối tượng thực tế ở phía `bySubSequence` là `String` có cùng nội dung trong ví dụ này.
4. `instanceof String` đúng **đối với implementation `String` này**. Nó không phải một bảo đảm cho mọi kết quả `CharSequence.subSequence`.
5. `toString()` cung cấp giá trị `String` nếu nơi sử dụng cần API như `toUpperCase`.

Dùng `substring` thường trực quan hơn khi biết chắc mình đang thao tác trên `String` và cần một `String`. Dùng `subSequence` khi thiết kế API tổng quát có ý nghĩa trên các lớp triển khai `CharSequence`.

## 4. Kết quả có phải bản sao, view hay bất biến không?

**Không có một câu trả lời chung cho mọi `CharSequence`.** Đây là điểm quan trọng của hợp đồng giao diện.

Một số triển khai tạo chuỗi mới, trong khi triển khai khác có thể trả về một đối tượng biểu diễn **vùng nhìn (view)** trên dữ liệu có thể thay đổi. Do vậy, không được suy luận «đã gọi `subSequence` thì dữ liệu chắc chắn tách khỏi nguồn» hoặc «đoạn con luôn phản ánh mọi thay đổi của nguồn».

Ví dụ về hành vi cụ thể:

| Đối tượng nguồn | Hành vi đáng biết trong Java 17 | Có thể coi kết quả là bản sao `String` độc lập? |
| --- | --- | --- |
| `String` | `subSequence` tương đương `substring` về nội dung, trả về `String` bất biến | Có thể dựa vào nội dung bất biến; không dựa vào identity hoặc cấu trúc bộ nhớ nội bộ |
| `StringBuilder` | Implementation chuẩn trả về kết quả giống `substring`, là `String` | Có đối với implementation này; đừng áp đặt quy tắc đó cho mọi `CharSequence` |
| `StringBuffer` | Implementation chuẩn trả về `String` từ đoạn được chỉ định | Có đối với implementation này |
| `CharBuffer` | `subSequence` tạo buffer mới chia sẻ nội dung với buffer nguồn (view theo vùng tương ứng) | **Không**; nguồn/buffer dùng chung có thể bị sửa |
| `CharSequence` tự cài đặt | Do implementation quyết định trong giới hạn hợp đồng | Không được giả định nếu chưa biết hợp đồng cụ thể |

**Cẩn thận với tính bất biến:** dù giao diện có chữ `CharSequence`, nó **không đồng nghĩa với `String`**. Tham chiếu có kiểu `CharSequence` có thể trỏ tới một đối tượng mutable.

### Ví dụ 3: `StringBuilder` và `CharBuffer` có thể cho trải nghiệm khác nhau

Tạo `SubSequenceImplementationsDemo.java`:

```java
import java.nio.CharBuffer;

public class SubSequenceImplementationsDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("ABCDE");
        CharSequence builderSlice = builder.subSequence(1, 4);

        builder.setCharAt(2, 'x');
        System.out.println(builder);
        System.out.println(builderSlice);

        char[] chars = {'A', 'B', 'C', 'D', 'E'};
        CharBuffer buffer = CharBuffer.wrap(chars);
        CharSequence bufferSlice = buffer.subSequence(1, 4);

        chars[2] = 'x';
        System.out.println(buffer);
        System.out.println(bufferSlice);
    }
}
```

```bash
javac SubSequenceImplementationsDemo.java
java SubSequenceImplementationsDemo
```

Kết quả trên JDK 17:

```text
ABxDE
BCD
ABxDE
BxD
```

Với `StringBuilder`, đoạn `builderSlice` là kết quả `String` của lời gọi `subSequence` trước khi builder bị sửa, nên vẫn hiện `BCD`. Với `CharBuffer.wrap(chars)`, buffer giữ vùng dữ liệu dùng chung với `chars`; đoạn `bufferSlice` là một buffer khác nhìn vào một phần vùng dữ liệu ấy. Khi `chars[2]` đổi từ `'C'` thành `'x'`, view cũng thấy `BxD`.

Đừng khái quát kết quả «`builderSlice` giữ nguyên» thành quy tắc bất biến cho toàn giao diện. Cũng đừng khái quát kết quả «`bufferSlice` thay đổi» thành quy tắc mọi `subSequence` đều trả về view.

**Nếu cần một văn bản bất biến ổn định**, chuyển đổi đoạn cần dùng thành `String` ở ranh giới phù hợp:

```java
static String stableSlice(CharSequence source, int start, int end) {
    return source.subSequence(start, end).toString();
}
```

Đây là **đoạn minh họa phương thức**, không phải chương trình độc lập. Với `StringBuilder` hoặc `CharBuffer` chuẩn, `toString()` trả về giá trị `String` biểu diễn nội dung tại thời điểm chuyển đổi. Nếu nguồn có thể bị các luồng khác sửa đồng thời, việc tạo snapshot nhất quán cần cơ chế đồng bộ phù hợp với nguồn; giao diện `CharSequence` không tự bảo đảm an toàn luồng.

## 5. Chỉ số `CharSequence` là UTF-16 code unit

Hợp đồng `CharSequence` mô tả dãy `char`, tức các UTF-16 code unit. `subSequence(start, end)` có thể tạo đoạn chứa surrogate lẻ nếu một biên cắt giữa hai nửa của code point ngoài BMP. Ví dụ, `"A😀B".subSequence(1, 2)` chỉ chứa high surrogate, còn `subSequence(1, 3)` chứa đủ cặp.

Khác với `String`, giao diện `CharSequence` **không cung cấp trực tiếp** `offsetByCodePoints`. Nếu một thuật toán cần ranh giới code point trên đầu vào tổng quát, có thể chuyển nội dung sang `String` rồi dùng API code point của `String`; với nguồn mutable, xác định rõ lúc lấy snapshot và cách đồng bộ khi có truy cập đồng thời. Ranh giới code point vẫn chưa chắc là ranh giới cụm ký tự hiển thị.

## 6. `CharSequence` không tự quy định cách so sánh nội dung

Một sai lầm khác là dùng `equals` của hai đối tượng bất kỳ triển khai `CharSequence` rồi mặc định đây là phép so sánh dãy ký tự. Giao diện `CharSequence` **không đặt ra một hợp đồng `equals` chung dựa trên nội dung** cho mọi implementation.

Ví dụ `String` ghi đè `equals` để so sánh với **một `String` khác** có cùng nội dung. Trong khi đó, `StringBuilder` dùng `equals` theo identity (kế thừa từ `Object`).

### Ví dụ 5: cùng nội dung chưa chắc `equals` bằng nhau

Tạo `CharSequenceEqualityDemo.java`:

```java
public class CharSequenceEqualityDemo {
    public static void main(String[] args) {
        CharSequence a = "abc";
        CharSequence b = new StringBuilder("abc");

        System.out.println(a.toString().equals(b.toString()));
        System.out.println(a.equals(b));
        System.out.println("abc".contentEquals(b));
        System.out.println(a.length() == b.length());
    }
}
```

```bash
javac CharSequenceEqualityDemo.java
java CharSequenceEqualityDemo
```

Kết quả:

```text
true
false
true
true
```

Hai lần `toString()` tạo ra giá trị `String` có cùng nội dung nên `equals` trả `true`. Nhưng `a.equals(b)` là lời gọi tới `String.equals`, và `b` là `StringBuilder`, nên nhận `false`. `String.contentEquals(CharSequence)` dùng để so sánh nội dung với một `CharSequence`, trả về `true` trong ví dụ.

Chỉ kiểm tra `length()` bằng nhau thì **chưa đủ**: hai dãy có cùng độ dài vẫn có thể chứa ký tự khác nhau. Nếu cần so sánh nội dung của hai `CharSequence` tổng quát, có thể dùng `CharSequence.compare(a, b) == 0` trên Java 17 (so sánh từ điển theo UTF-16 code unit), hoặc chuyển sang `String` và so sánh nội dung khi phù hợp với hiệu năng và mục đích. Cần quy định xử lý `null` riêng.

## 7. Thiết kế API khi muốn nhận `CharSequence`

Giả sử cần lấy mã ngắn từ một đầu vào văn bản. Nếu chỉ đọc chiều dài, lấy ký tự và trích đoạn, chữ ký này đủ tổng quát:

```java
static String extractCode(CharSequence text, int start, int end) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    if (start < 0 || end < start || end > text.length()) {
        throw new IndexOutOfBoundsException("Invalid range");
    }
    return text.subSequence(start, end).toString();
}
```

Đây là **phương thức minh họa** có thể đặt trong lớp Java. Các quyết định thiết kế:

1. Nhận `CharSequence` để cho phép `String`, `StringBuilder` và các implementation tương thích.
2. Kiểm tra đầu vào và khoảng cắt có chủ đích; thông điệp lỗi có thể được tùy chỉnh theo API của ứng dụng.
3. Trả về `String` nếu hợp đồng của phương thức hứa một **giá trị văn bản bất biến** thay vì một đoạn `CharSequence` có thể phản ánh thay đổi ở dữ liệu nguồn.
4. Không suy luận rằng implementation của tham số luôn là `String`. Ép kiểu `(String) text.subSequence(...)` có thể ném `ClassCastException` với implementation trả về `CharBuffer` hoặc một loại `CharSequence` khác.

Nếu API chủ đích giữ một **view** để tránh sao chép, hãy mô tả rõ thời hạn sử dụng, trách nhiệm sở hữu dữ liệu, khả năng thấy thay đổi, và an toàn luồng theo implementation cụ thể. Không hứa hiệu năng O(1), không cấp phát, hoặc tách bộ nhớ cho `subSequence` khi kiểu nguồn chưa được xác định: hợp đồng giao diện không áp đặt các chi tiết đó.

### Ví dụ 6: một phương thức làm việc với nhiều implementation

Tạo tệp `GenericSubSequenceDemo.java`:

```java
import java.nio.CharBuffer;

public class GenericSubSequenceDemo {
    static String extractCode(CharSequence text, int start, int end) {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        if (start < 0 || end < start || end > text.length()) {
            throw new IndexOutOfBoundsException("Invalid range");
        }
        return text.subSequence(start, end).toString();
    }

    public static void main(String[] args) {
        String text = "ID-4567";
        StringBuilder builder = new StringBuilder("ID-4567");
        CharBuffer buffer = CharBuffer.wrap("ID-4567".toCharArray());

        System.out.println(extractCode(text, 3, 7));
        System.out.println(extractCode(builder, 3, 7));
        System.out.println(extractCode(buffer, 3, 7));
    }
}
```

```bash
javac GenericSubSequenceDemo.java
java GenericSubSequenceDemo
```

Kết quả:

```text
4567
4567
4567
```

Cùng hợp đồng `CharSequence.subSequence` cho ra dãy ký tự đúng từ các loại đầu vào khác nhau. Việc **chuyển đoạn con sang `String`** ở bước trả kết quả tạo ra cách sử dụng thống nhất, không buộc phía gọi phải quan tâm lớp hiện thực cụ thể của `subSequence`.

## 8. Lỗi thường gặp và cách tránh

**Lỗi 1 — tưởng `end` được lấy:** `subSequence(1, 3)` lấy chỉ số `1` và `2`; không lấy `3`. Kiểm tra bằng độ dài `end - start`.

**Lỗi 2 — cắt quá giới hạn:** `subSequence(0, text.length() + 1)` không hợp lệ. Nếu vị trí được tính từ dữ liệu ngoài, hãy xác thực điều kiện ranh giới và xử lý ngoại lệ có mục đích.

**Lỗi 3 — giả định mọi kết quả là `String`:** phương thức có kiểu trả về `CharSequence`, và implementation khác nhau có thể trả về các lớp khác nhau. Khi thật sự cần `String`, sử dụng `toString()` theo hợp đồng; không ép kiểu mù.

**Lỗi 4 — giả định mọi kết quả là view:** `StringBuilder` chuẩn có thể trả về `String` snapshot. Không dựa vào thay đổi của nguồn sẽ phản ánh trên đoạn con nếu hợp đồng implementation không nói rõ.

**Lỗi 5 — giả định mọi kết quả bất biến:** `CharBuffer` có thể trả về view chia sẻ dữ liệu mutable. Nếu cần giữ văn bản bất biến, chuyển đổi thành `String` và xác định chính sách đồng bộ/ownership phù hợp.

**Lỗi 6 — nhầm độ dài với Unicode code point:** `length()` và chỉ số của `subSequence` theo UTF-16 code unit. Khi xử lý emoji hoặc ký tự ngoài BMP, hãy tính ranh giới code point cẩn thận; grapheme cluster còn có thể phức tạp hơn.

**Lỗi 7 — dùng `equals` giữa các kiểu `CharSequence` để kết luận hai dãy bằng nhau:** không có hợp đồng equality chung. Dùng `String.contentEquals`, `CharSequence.compare` hay chuyển sang `String` khi phù hợp.

**Lỗi 8 — hiểu `subSequence` tự bảo đảm thread-safe:** giao diện không cung cấp bảo đảm đó. Nếu dữ liệu nguồn mutable được sửa bởi luồng khác, phải dựa vào cơ chế đồng bộ và tính chất cụ thể của implementation.

**Lỗi 9 — dùng `subSequence` thay cho `substring` chỉ vì tên «tổng quát hơn»:** khi kiểu nguồn đã là `String` và cần `String`, `substring` thường trực tiếp và rõ hơn; `subSequence` hữu ích khi muốn lập trình theo giao diện.

## 9. Tự kiểm tra

### Bài 1 — ranh giới nửa mở

Cho `CharSequence s = "spring";`. Dự đoán:

```java
System.out.println(s.subSequence(0, 3));
System.out.println(s.subSequence(3, 6));
System.out.println(s.subSequence(6, 6).isEmpty());
```

Kết quả:

```text
spr
ing
true
```

Chỉ số `end` không được lấy; hai đoạn `[0,3)` và `[3,6)` ghép lại đúng `spring`. Lấy đoạn rỗng ở vị trí cuối là hợp lệ.

### Bài 2 — nội dung có ổn định không?

Với Java 17:

```java
StringBuilder builder = new StringBuilder("hello");
CharSequence sub = builder.subSequence(1, 4);
builder.replace(1, 4, "XYZ");

System.out.println(builder);
System.out.println(sub);
```

Kết quả:

```text
hXYZo
ell
```

Trong implementation `StringBuilder` chuẩn, `subSequence` tạo kết quả `String` của đoạn `"ell"` ở thời điểm gọi. Đừng áp dụng giả định snapshot này cho mọi implementation của `CharSequence`.

### Bài 3 — code point và code unit

Cho:

```java
String text = "A\uD83D\uDE00B";
System.out.println(text.length());
System.out.println(text.subSequence(1, 3).length());
```

Kết quả:

```text
4
2
```

Đoạn `subSequence(1, 3)` chứa một code point U+1F600 nhưng hai UTF-16 code unit.

### Bài 4 — thiết kế chữ ký

Một phương thức cần chấp nhận `String`, `StringBuilder` và `CharBuffer`, đồng thời trả về một giá trị văn bản bất biến. Nên khai báo gì?

**Gợi ý:** tham số `CharSequence source`; kết quả `String`; dùng `source.subSequence(start, end).toString()` sau khi kiểm tra chỉ số. Nếu đầu vào có thể bị sửa đồng thời, phải xác định thêm cách đồng bộ và thời điểm lấy dữ liệu.

## Kết luận

**`subSequence(start, end)` là hợp đồng đọc một đoạn theo chỉ số UTF-16 nửa mở `[start, end)` trên giao diện `CharSequence`.** Hợp đồng cho biết đoạn con cần chứa những ký tự nào, nhưng không bảo đảm lớp kết quả, snapshot hay view, tính bất biến hoặc chi phí thực hiện. Với `String`, nó tương đương `substring` về nội dung; với các implementation khác, cần dựa vào đặc điểm cụ thể. Thiết kế API đúng phải phân biệt **nội dung đoạn con**, **kiểu trả về**, **quyền sở hữu dữ liệu** và **khả năng thay đổi của nguồn**.