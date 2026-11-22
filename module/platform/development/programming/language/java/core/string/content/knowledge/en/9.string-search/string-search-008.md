# `String.indexOf` với `beginIndex` và `endIndex` từ Java 21

Trong Java 21, `java.lang.String` bổ sung hai overload `indexOf` cho phép **giới hạn tìm kiếm trong một khoảng của chuỗi gốc**. Nhờ đó, có thể tìm ký tự/code point hoặc chuỗi con trong đoạn `[beginIndex, endIndex)` mà không phải tự tạo `substring` để khoanh vùng. Kết quả vẫn là **vị trí trong chuỗi gốc**, không phải vị trí tương đối trong đoạn được tìm.

Hai overload mới:

```java
// Có từ Java 21:
int indexOf(int ch, int beginIndex, int endIndex);
int indexOf(String str, int beginIndex, int endIndex);
```

Đây là các **chữ ký phương thức để tra cứu**, không phải khai báo có thể đặt độc lập trong một lớp tùy ý. Để gọi được chúng cần **biên dịch và chạy bằng JDK 21 trở lên**. Hai dạng cũ `indexOf(int ch, int fromIndex)` và `indexOf(String str, int fromIndex)` chỉ chọn điểm bắt đầu; không có tham số giới hạn điểm kết thúc.

## 1. Hiểu đúng khoảng `[beginIndex, endIndex)`

Cú pháp khoảng **nửa mở** được dùng xuyên suốt các API tìm kiếm này:

- `beginIndex`: vị trí bắt đầu, **bao gồm**.
- `endIndex`: vị trí kết thúc, **không bao gồm**.
- Khoảng hợp lệ thỏa `0 <= beginIndex <= endIndex <= s.length()`.
- Chỉ số dùng đơn vị **UTF-16 code unit** (giống `String.length()` và `substring()`), không phải số Unicode code point hay số ký tự người dùng nhìn thấy.
- Trả về vị trí đầu tiên khớp trong phạm vi hoặc `-1` nếu không thấy; kết quả khớp là chỉ số **tuyệt đối của `s`**.

Ví dụ chuỗi `"cat|dog|cat|owl"` có độ dài 15:

```text
Nội dung:       c a t | d o g | c a t | o w l
UTF-16 index:   0 1 2 3 4 5 6 7 8 9 10 11 12 13 14
                                                  end = 15

Khoảng [4, 11): d o g | c a t       (vị trí 4..10)
Khoảng [4, 10): d o g | c a         (thiếu chữ t ở index 10)
```

Vì vậy:

```java
String s = "cat|dog|cat|owl";

System.out.println(s.indexOf("cat", 4, 11)); // 8
System.out.println(s.indexOf("cat", 4, 10)); // -1
System.out.println(s.indexOf('|', 4, 11));   // 7
System.out.println(s.indexOf('|', 8, 11));   // -1
```

Ở dòng đầu, `"cat"` tại vị trí 8–10 nằm **trọn vẹn** trong khoảng `[4, 11)` nên kết quả là `8`. Ở dòng thứ hai, khoảng dừng trước index 10, không chứa trọn `"cat"` nên kết quả `-1`. Ký tự phân cách tại vị trí 11 cũng không thuộc khoảng có `endIndex = 11`.

## 2. Tìm chuỗi con: `indexOf(String str, beginIndex, endIndex)`

Đây là overload dùng khi muốn tìm **một chuỗi con hoàn chỉnh** trong một cửa sổ của chuỗi.

```java
String s = "abc---abc---xyz";

System.out.println(s.indexOf("abc", 0, 3));   // 0
System.out.println(s.indexOf("abc", 3, 9));   // 6
System.out.println(s.indexOf("abc", 3, 8));   // -1
System.out.println(s.indexOf("xyz", 9, 15));  // 12
```

Phép gọi thứ ba trả về `-1` vì cửa sổ `[3,8)` chỉ chứa các vị trí `3,4,5,6,7`; chuỗi `"abc"` bắt đầu ở 6 nhưng ký tự cuối nằm ở index 8, ngoài phạm vi.

### Quy tắc so khớp chính xác

Với `s.indexOf(str, beginIndex, endIndex)`, nếu `str` **không rỗng**, Java tìm chỉ số nhỏ nhất `k` thỏa:

- `k >= beginIndex`;
- `k + str.length() <= endIndex`;
- `s.startsWith(str, k)` trả về `true`.

Nếu không có `k` hợp lệ thì trả về `-1`. Do vậy, **toàn bộ chuỗi con** phải nằm trong cửa sổ.

Theo Java 21 API, kết quả tương đương về mặt giá trị với:

```java
String window = s.substring(beginIndex, endIndex);
int local = window.indexOf(str);
int result = local < 0 ? -1 : beginIndex + local;
```

Đoạn trên là **mã minh họa trong thân phương thức** khi các biến đã tồn tại; nó cố ý tạo `window` để làm rõ việc quy đổi chỉ số. Overload ba tham số cho phép viết trực tiếp:

```java
int result = s.indexOf(str, beginIndex, endIndex);
```

Theo tài liệu API, overload này không cần tạo đối tượng `substring` trung gian chỉ để tìm kiếm. Đó là lợi thế về sự rõ ràng và tránh việc tạo chuỗi tạm không cần thiết; không suy diễn rằng mọi tình huống chắc chắn nhanh hơn hoặc không phát sinh bất kỳ cấp phát nội bộ nào.

### Kết quả là vị trí trong chuỗi ban đầu

```java
String s = "0123Java789";
System.out.println(s.indexOf("Java", 4, 8)); // 4
```

`Java` là nội dung của cửa sổ `[4,8)`, nhưng kết quả là `4`, **không phải 0**. Đây là điểm rất dễ nhầm khi chuyển từ cách `s.substring(begin,end).indexOf(...)`.

## 3. Tìm ký tự / Unicode code point: `indexOf(int ch, beginIndex, endIndex)`

Overload có tham số đầu là `int ch` dùng để tìm một giá trị ký tự/code point. Java nhận cả biểu thức `char` thông thường vì `char` tự chuyển được thành `int`:

```java
String s = "alpha|beta|gamma";

System.out.println(s.indexOf('|', 0, 10)); // 5
System.out.println(s.indexOf('|', 6, 10)); // -1
System.out.println(s.indexOf('a', 6, 10)); // 9
```

Ở ví dụ này, ký tự `'a'` đầu tiên trong đoạn `[6,10)` nằm tại index 9.

Với giá trị `ch` trong dải BMP (`0x0000` đến `0xFFFF`), Java so sánh với từng code unit qua `charAt(k)`. Với giá trị ngoài BMP, Java tìm code point qua `codePointAt(k)`. Trong cả hai trường hợp, **chỉ số trả về là vị trí UTF-16 bắt đầu của lần xuất hiện**, không phải thứ tự code point.

Ví dụ emoji 😀 (`U+1F600`) chiếm hai code unit UTF-16:

```java
String emoji = new String(Character.toChars(0x1F600));
String s = "A" + emoji + "B"; // UTF-16 length = 4

System.out.println(s.length());                       // 4
System.out.println(s.indexOf(0x1F600, 0, s.length())); // 1
System.out.println(s.indexOf(emoji, 0, s.length()));    // 1
```

Hai lần tìm trên cùng chuỗi cho kết quả `1`, vị trí high surrogate của emoji. **Lưu ý về ranh giới:** overload `int ch` xác định code point tại chỉ số bắt đầu nằm trong khoảng; overload `String str` yêu cầu toàn bộ chuỗi con nằm trong khoảng. Khi một `endIndex` cắt ngang surrogate pair, không nên coi hai overload có cùng quy tắc “độ dài mẫu” — muốn giới hạn **trọn một ký tự Unicode**, trước hết phải đặt cửa sổ theo ranh giới code point hợp lệ (có thể tính bằng `offsetByCodePoints`).

## 4. So sánh overload cũ và mới

| Lệnh | Cách tìm | Java |
| --- | --- | --- |
| `s.indexOf("cat")` | Tìm trong toàn chuỗi | Trước Java 21 |
| `s.indexOf("cat", fromIndex)` | Tìm từ một vị trí về cuối, không có `endIndex` | Trước Java 21 |
| `s.indexOf("cat", beginIndex, endIndex)` | Tìm chuỗi con **nằm trọn trong cửa sổ** | Từ Java 21 |
| `s.indexOf('c')` | Tìm ký tự đầu tiên trong toàn chuỗi | Trước Java 21 |
| `s.indexOf('c', fromIndex)` | Tìm ký tự từ `fromIndex` trở đi | Trước Java 21 |
| `s.indexOf('c', beginIndex, endIndex)` | Chỉ xét vị trí bắt đầu trong cửa sổ | Từ Java 21 |

Các dạng một tham số hoặc hai tham số dùng `fromIndex` có thể xử lý chỉ số ngoài phạm vi khá “thoáng”: chỉ số âm được xử lý như tìm từ đầu, và chỉ số vượt quá độ dài thường cho kết quả `-1` đối với mẫu không rỗng. Trong khi đó, **overload ba tham số kiểm tra nghiêm ngặt**:

```java
String s = "abc";

System.out.println(s.indexOf("a", -3)); // 0
System.out.println(s.indexOf("a", 99)); // -1

// s.indexOf("a", -3, 3); // Ném StringIndexOutOfBoundsException
// s.indexOf("a",  0, 4); // Ném StringIndexOutOfBoundsException
// s.indexOf("a",  2, 1); // Ném StringIndexOutOfBoundsException
```

Do đó overload mới giúp phân biệt rõ **“không thấy mẫu trong cửa sổ hợp lệ”** (`-1`) với **“người gọi truyền ranh giới không hợp lệ”** (exception).

## 5. Ví dụ hoàn chỉnh Java 21+ có thể biên dịch và chạy

Lưu toàn bộ chương trình sau vào `BoundedIndexOfDemo.java`:

```java
public class BoundedIndexOfDemo {
    public static void main(String[] args) {
        String s = "cat|dog|cat|owl";

        System.out.println("length = " + s.length());
        System.out.println("cat in [4,11) = " + s.indexOf("cat", 4, 11));
        System.out.println("cat in [4,10) = " + s.indexOf("cat", 4, 10));
        System.out.println("dog in [4,7) = " + s.indexOf("dog", 4, 7));
        System.out.println("pipe in [4,11) = " + s.indexOf('|', 4, 11));
        System.out.println("pipe in [8,11) = " + s.indexOf('|', 8, 11));
        System.out.println("empty in [6,6) = " + s.indexOf("", 6, 6));
        System.out.println("empty in [15,15) = " + s.indexOf("", 15, 15));
        System.out.println("missing = " + s.indexOf("fox", 0, 15));

        try {
            s.indexOf("cat", -1, 5);
            System.out.println("unexpected success");
        } catch (StringIndexOutOfBoundsException expected) {
            System.out.println("invalid range rejected");
        }

        String emoji = new String(Character.toChars(0x1F600));
        String unicode = "A" + emoji + "B";
        System.out.println("UTF-16 length = " + unicode.length());
        System.out.println("emoji code point index = "
                + unicode.indexOf(0x1F600, 0, unicode.length()));
        System.out.println("emoji string index = "
                + unicode.indexOf(emoji, 0, unicode.length()));
    }
}
```

Biên dịch/chạy với **JDK 21 hoặc mới hơn**:

```bash
javac BoundedIndexOfDemo.java
java BoundedIndexOfDemo
```

Kết quả chuẩn:

```text
length = 15
cat in [4,11) = 8
cat in [4,10) = -1
dog in [4,7) = 4
pipe in [4,11) = 7
pipe in [8,11) = -1
empty in [6,6) = 6
empty in [15,15) = 15
missing = -1
invalid range rejected
UTF-16 length = 4
emoji code point index = 1
emoji string index = 1
```

Hãy đặc biệt quan sát việc `indexOf("", 6, 6)` trả về `6`. Mẫu rỗng có thể khớp tại chính vị trí bắt đầu của một cửa sổ rỗng. Ngược lại, tìm một mẫu không rỗng hoặc ký tự bình thường trong cửa sổ rỗng sẽ cho `-1`.

## 6. Quy tắc biên, lỗi và các ca dễ nhầm

### 6.1. Khoảng rỗng và mẫu rỗng

Với `String str` là **chuỗi rỗng**, có một kết quả hợp lệ tại `beginIndex`, kể cả khi `beginIndex == endIndex`, hoặc khi cả hai bằng `s.length()`:

```java
String s = "abc";
System.out.println(s.indexOf("", 0, 0)); // 0
System.out.println(s.indexOf("", 2, 2)); // 2
System.out.println(s.indexOf("", 3, 3)); // 3
System.out.println(s.indexOf("a", 2, 2)); // -1
System.out.println(s.indexOf('a', 2, 2)); // -1
```

Không có “vị trí ký tự” nằm trong `[2,2)`, nhưng mẫu rỗng có thể khớp ở một ranh giới hợp lệ. Đừng vô tình dùng `indexOf("", ...)` khi ý định là tìm một dấu phân cách không rỗng.

### 6.2. Ranh giới không hợp lệ

Cả hai overload Java 21 ba tham số đều ném `StringIndexOutOfBoundsException` nếu:

- `beginIndex < 0`;
- `endIndex > s.length()`;
- `beginIndex > endIndex`.

Khi xét xử lý đầu vào, cũng phải đảm bảo bản thân biến `s` không phải `null`. Với overload nhận `String str`, `str == null` gây `NullPointerException`; một tham số `int ch` không có trạng thái `null`. Chọn rõ chính sách với tham số `null` thay vì biến lỗi truy cập thành kết quả “không tìm thấy”.

Ví dụ minh họa cách kiểm tra trước trong một phương thức ứng dụng:

```java
static int boundedSearch(String text, String needle, int begin, int end) {
    java.util.Objects.requireNonNull(text, "text");
    java.util.Objects.requireNonNull(needle, "needle");

    if (begin < 0 || begin > end || end > text.length()) {
        throw new IllegalArgumentException("Invalid search window");
    }
    return text.indexOf(needle, begin, end); // Cần Java 21+
}
```

Đây là **phương thức minh họa để đặt bên trong một lớp**, không phải chương trình độc lập. Ta chủ động chuyển lỗi giới hạn thành `IllegalArgumentException` theo hợp đồng riêng của API; nếu muốn giữ nguyên exception chuẩn từ `String.indexOf`, có thể bỏ phần kiểm tra này.

### 6.3. So khớp phân biệt hoa thường, không tự chuẩn hóa Unicode

Các overload mới chỉ **thu hẹp cửa sổ tìm kiếm**. Chúng không tự bỏ dấu cách, không chuyển `"A"` thành `"a"`, không chuẩn hóa Unicode, cũng không so khớp theo ngôn ngữ tự nhiên:

```java
String s = "Java java";
System.out.println(s.indexOf("java", 0, s.length())); // 5
System.out.println(s.indexOf("JAVA", 0, s.length())); // -1
```

Nếu ứng dụng cần tìm không phân biệt hoa thường hay xử lý Unicode phức tạp, đó là một yêu cầu khác, phải xác định quy tắc chuẩn hóa/collation phù hợp. Không nên mặc nhiên xử lý bằng `toLowerCase()` không chọn locale rồi coi là đúng cho mọi ngôn ngữ.

## 7. Ứng dụng thực tế: tìm trong một trường hoặc một đoạn thông điệp

Xét một thông điệp có các trường ngăn bởi dấu `;`:

```text
id=7;role=user;token=abc
```

Bài toán: kiểm tra trường `role=user` có nằm **bên trong đoạn ở giữa dấu chấm phẩy thứ nhất và thứ hai** hay không, và tránh việc một kết quả nằm trong trường khác bị nhận nhầm.

Chương trình độc lập `FieldWindowDemo.java`:

```java
public class FieldWindowDemo {
    public static void main(String[] args) {
        String input = "id=7;role=user;token=abc";

        int firstSeparator = input.indexOf(';'); // 4
        int secondSeparator = input.indexOf(';', firstSeparator + 1); // 14

        int begin = firstSeparator + 1; // 5
        int end = secondSeparator;       // 14

        int role = input.indexOf("role=user", begin, end);
        int token = input.indexOf("token", begin, end);
        System.out.println("role offset = " + role);
        System.out.println("token offset = " + token);
    }
}
```

Chạy:

```bash
javac FieldWindowDemo.java
java FieldWindowDemo
```

Kết quả:

```text
role offset = 5
token offset = -1
```

`role` nằm trong `[5,14)` và được trả về theo chỉ số gốc `5`. Từ khóa `token` nằm **ngoài cửa sổ**, nên trả về `-1` dù xuất hiện trong toàn thông điệp.

Trong ví dụ này, ta đã biết chắc có hai dấu `;`. Nếu đầu vào thực tế có thể thiếu dấu phân cách, **phải kiểm tra kết quả `-1` trước khi dùng để xây dựng khoảng tìm**, và xác định hành vi khi dữ liệu lỗi. Không nên lấy các con số ở ví dụ làm chỉ số cứng cho mọi bản ghi.

Đây chỉ là ví dụ về tìm chuỗi theo đoạn; khi parse định dạng phức tạp, đặc biệt có escape, dấu phân cách lồng nhau hoặc biểu diễn có cấu trúc, cần dùng parser đúng hợp đồng định dạng thay vì tìm chuỗi đơn giản.

## 8. Dùng overload mới khi nào?

**Nên cân nhắc** khi đã có một vùng `[beginIndex, endIndex)` xác định và chỉ muốn tìm trong vùng đó: nội dung giữa hai dấu phân cách, một section của tài liệu, một token trong phần tiêu đề, hoặc kiểm tra mẫu xuất hiện hoàn chỉnh trong một đoạn.

Việc viết:

```java
int found = text.indexOf(needle, beginIndex, endIndex);
```

làm rõ mục đích hơn cách tạo chuỗi tạm để tìm trong một cửa sổ rồi cộng offset. Nó cũng ngăn một mẫu bắt đầu trong cửa sổ nhưng **kéo dài ra ngoài `endIndex`** đối với overload `String str`.

**Không nhất thiết phải dùng** nếu bạn cần tìm từ một điểm đến tận cuối chuỗi: `indexOf(str, fromIndex)` vẫn đơn giản và tương thích JDK cũ hơn. Nếu dự án còn phải biên dịch/chạy trên **Java 17**, các overload ba tham số **chưa tồn tại**, nên không dùng trực tiếp. Giải pháp tương thích Java 17 có thể là `substring` theo phạm vi đã xác minh hoặc một thuật toán tự tìm trong khoảng; nếu viết giải pháp thay thế, nhớ điều chỉnh chỉ số cục bộ trở lại chỉ số gốc.

### Lưu ý với chỉ số UTF-16 và code point

Một emoji nằm ngoài BMP chiếm hai code unit; vì vậy `endIndex` và `beginIndex` không phải thứ tự code point. Nếu nhận vị trí theo code point từ API khác, hãy đổi sang UTF-16 index bằng `offsetByCodePoints` trước khi gọi `indexOf`. Cũng cần nhớ một Unicode grapheme cluster có thể gồm nhiều code point; các overload `indexOf` không tự phân đoạn văn bản theo cụm hiển thị.

## 9. Những lỗi thường gặp

1. **Cho rằng chỉ số trả về tính từ `beginIndex`.** Sai: `indexOf` trả về UTF-16 index trên chuỗi gốc, không cần cộng thêm `beginIndex`.
2. **Hiểu `endIndex` là bao gồm.** Sai: biên phải bị loại trừ. Mẫu chuỗi con phải khớp trọn trong vùng.
3. **Truyền chỉ số code point vào tham số UTF-16 index.** Sai với các chuỗi có surrogate pair; cần chuyển hệ chỉ số.
4. **Đánh đồng overload tìm `int ch` và tìm `String str` trong mọi tình huống Unicode.** Với code point ngoài BMP, cần hiểu phép kiểm tra vị trí bắt đầu của `int ch` và độ dài toàn mẫu của `String str`.
5. **Bỏ qua ngoại lệ khi khoảng không hợp lệ.** Overload ba tham số không âm thầm chấp nhận chỉ số âm, `endIndex` vượt `length()` hoặc `beginIndex > endIndex`.
6. **Kỳ vọng mẫu rỗng trả về `-1`.** `""` khớp tại `beginIndex`, kể cả cửa sổ rỗng hợp lệ.
7. **Dùng trên JDK 17 rồi tưởng là lỗi logic của `indexOf`.** Đây là API được thêm trong Java 21; cần đúng JDK và cấu hình build/runtime.
8. **Quên kiểm tra `-1` của phép tìm dấu phân cách trước khi tính cửa sổ.** Có thể tạo ra khoảng sai hoặc ném exception không mong muốn.
9. **Cho rằng phương thức tự tìm không phân biệt chữ hoa/thường.** Nó tìm chính xác theo nội dung; yêu cầu so khớp ngôn ngữ cần giải pháp riêng.

## 10. Tự kiểm tra

Với `String s = "red|blue|red";`, hãy tính kết quả:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `s.indexOf("red", 0, 8)` | `0` | Tìm thấy lần đầu trong vùng |
| `s.indexOf("red", 4, 12)` | `9` | Chỉ lần xuất hiện thứ hai nằm trọn trong vùng |
| `s.indexOf("red", 4, 11)` | `-1` | Mẫu thứ hai cần ký tự tại index 11, nhưng biên phải bị loại trừ |
| `s.indexOf('|', 4, 8)` | `8`? | **Bẫy kiểm tra:** index 8 bị loại trừ, đáp án đúng là `-1` |
| `s.indexOf("", 8, 8)` | `8` | Mẫu rỗng khớp tại ranh giới hợp lệ |

Trong bảng, dòng có dấu hỏi là câu hỏi tự kiểm tra; **kết quả thực sự là `-1`**. Đừng dùng đáp án giả `8` như một đầu ra chương trình.

**Ghi nhớ:** Java 21 thêm `indexOf` ba tham số để tìm kiếm trong `[beginIndex, endIndex)`. Với `String str`, mẫu phải nằm trọn trong khoảng; với `int ch`, chỉ số xuất hiện được xác định theo giá trị ký tự/code point. Kết quả là **UTF-16 index của chuỗi gốc**, và phạm vi không hợp lệ sẽ bị từ chối bằng exception.

**Tài liệu chính thức:** [Java SE 21 — `String` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html).
