# Quan hệ giữa `String`, `char[]`, `CharSequence` và `Object` trong Java

## 1. Mục tiêu và bức tranh tổng thể

Trong Java, cùng một nội dung văn bản có thể xuất hiện dưới nhiều kiểu: đối tượng `String`, mảng `char[]`, một đối tượng triển khai `CharSequence`, hoặc một tham chiếu `Object`. Những kiểu này **không đồng nghĩa**, dù đôi khi cùng biểu diễn các ký tự giống nhau. Để sử dụng đúng cần phân biệt ba câu hỏi:

1. **Kiểu và quan hệ kế thừa:** gán một giá trị cho biến kiểu nào là hợp lệ?
2. **Khả năng thay đổi và sở hữu dữ liệu:** sửa đối tượng/mảng ban đầu có làm nội dung đang được quan sát thay đổi không?
3. **Ngữ nghĩa thao tác:** các phương thức `equals`, `toString`, `charAt`, `length` và chuyển đổi sẽ xử lý dữ liệu như thế nào?

Sơ đồ kiểu (Java 17+):

```text
java.lang.Object
  ├── java.lang.String (final)
  │      └── implements CharSequence, Comparable<String>, Serializable, ...
  ├── java.lang.StringBuilder (mutable, implements CharSequence)
  ├── java.lang.StringBuffer  (mutable, implements CharSequence)
  ├── java.nio.CharBuffer     (implements CharSequence)
  └── char[]                  (kiểu mảng; là Object, KHÔNG implements CharSequence)

java.lang.CharSequence là interface (hợp đồng đọc dãy char),
không phải lớp cha của Object và không phải kiểu mảng.
```

Mọi `String` và mọi mảng `char[]` đều là đối tượng Java, nên có thể được giữ trong một biến `Object`. Nhưng `char[]` **không** phải là `String` hay `CharSequence`; giữa chúng không có quan hệ gán kiểu trực tiếp. `String` vừa là một `Object` vừa là một `CharSequence` vì lớp này triển khai interface đó.

| Kiểu | Bản chất | Thay đổi nội dung qua chính giá trị đó? | Quan hệ nổi bật |
| --- | --- | --- | --- |
| `String` | Lớp `final` chứa chuỗi ký tự bất biến | Không | `extends Object`; `implements CharSequence` |
| `char[]` | Mảng phần tử `char` nguyên thủy | Có, bằng cách gán `array[i]` | Là `Object`; không triển khai `CharSequence` |
| `CharSequence` | Interface để đọc dãy `char` | Interface không có thao tác sửa; đối tượng thực tế *có thể* thay đổi | `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` triển khai |
| `Object` | Lớp gốc của đối tượng Java | Không quy định nội dung văn bản | Chỉ cung cấp hợp đồng đối tượng chung |

**Phân biệt biến với đối tượng:** `String name = "A"; name = "B";` là **gán lại tham chiếu** của biến `name`, không sửa nội dung đối tượng `String("A")`.

## 2. `String` là một `Object` và triển khai `CharSequence`

Khai báo rút gọn của Java 17 là:

```java
public final class String
        implements java.io.Serializable,
                   Comparable<String>,
                   CharSequence,
                   java.lang.constant.Constable,
                   java.lang.constant.ConstantDesc {
    // Nội dung phương thức được lược bỏ.
}
```

Đây chỉ là **chữ ký minh họa**, không phải lớp tự biên dịch: các phương thức/thuộc tính cài đặt đã bị lược bỏ. `String` kế thừa `Object` theo quy tắc của Java ngay cả khi khai báo không ghi `extends Object`.

Một đối tượng `String` có thể được nhìn qua nhiều kiểu tham chiếu:

```java
String text = "Hello";
CharSequence sequence = text; // upcast: hợp lệ
Object object = text;         // upcast: hợp lệ

System.out.println(sequence.length());     // 5
System.out.println(object instanceof String); // true
```

Khi kiểu tĩnh là `CharSequence`, chương trình chỉ được gọi các phương thức có trong hợp đồng `CharSequence` (cộng các phương thức của `Object`), dù đối tượng thực tế là `String`. Khi kiểu tĩnh là `Object`, `object.length()` không biên dịch vì `Object` không khai báo `length()`. Cần kiểm tra rồi ép kiểu:

```java
if (object instanceof String actual) {
    System.out.println(actual.length()); // 5
}
```

Một phép ép kiểu `(String) object` chỉ đúng khi đối tượng thực tế là `String` (hoặc `null`). Nếu `object` đang chứa `char[]` hay `StringBuilder`, ép sang `String` gây `ClassCastException`. Thao tác ép kiểu không thực hiện chuyển đổi nội dung.

## 3. `char[]`: mảng có thể sửa, không tự trở thành chuỗi

`char` là kiểu nguyên thủy 16 bit biểu diễn **đơn vị mã UTF-16**. `char[]` là **đối tượng mảng**, chứa nhiều giá trị `char`, có thuộc tính `length` (không phải phương thức `length()`), và cho phép sửa phần tử.

```java
char[] letters = {'J', 'a', 'v', 'a'};
letters[0] = 'K';
System.out.println(letters.length); // 4
```

`String` không cung cấp cú pháp gán `text[0] = 'K'` và không có phương thức thay đổi vị trí ký tự tại chỗ. Các thao tác như `replace`, `substring` hoặc `concat` tạo ra kết quả kiểu `String`, không sửa giá trị chuỗi hiện có; việc JVM có thể tái sử dụng đối tượng ở một số tình huống không làm thay đổi tính bất biến.

Chuyển đổi `char[]` sang `String` tạo nội dung văn bản từ **giá trị phần tử tại thời điểm chuyển đổi**:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = new String(letters);
letters[0] = 'K';
System.out.println(text);                // Java
System.out.println(new String(letters)); // Kava
```

Constructor `new String(char[])` **sao chép nội dung**. `String.valueOf(char[])` và `String.copyValueOf(char[])` cũng tạo chuỗi từ các ký tự của mảng. Thay đổi mảng nguồn sau đó không làm thay đổi `String` đã tạo. Theo chiều ngược lại, `text.toCharArray()` trả về mảng mới có thể sửa, không làm biến đổi chuỗi gốc:

```java
String text = "Java";
char[] copy = text.toCharArray();
copy[0] = 'K';
System.out.println(text);        // Java
System.out.println(new String(copy)); // Kava
```

Để lấy một đoạn ký tự vào mảng có sẵn, dùng `text.getChars(srcBegin, srcEnd, destination, dstBegin)` và bảo đảm đủ chỗ đích. Khi cần xử lý nhiều lần theo kiểu mảng, cân nhắc chi phí tạo bản sao và yêu cầu sở hữu dữ liệu.

**Lưu ý về bộ nhớ:** mô hình API của `String` diễn đạt một dãy đơn vị mã UTF-16; không suy ra Java bắt buộc lưu `String` bằng một `char[]` bên trong. Các JDK hiện đại có thể dùng cách lưu trữ tối ưu khác, và đó là chi tiết triển khai, không phải quan hệ kiểu Java.

## 4. `CharSequence`: hợp đồng đọc chuỗi ký tự, không cam kết bất biến

`CharSequence` cung cấp giao diện chung để thư viện có thể nhận văn bản mà không buộc người gọi phải tạo `String` ngay từ đầu. Các thao tác cốt lõi:

| API | Ý nghĩa |
| --- | --- |
| `length()` | Số đơn vị `char` (UTF-16) trong dãy |
| `charAt(index)` | Đọc một đơn vị `char` tại chỉ số từ 0 |
| `subSequence(start, end)` | Lấy đoạn `[start, end)`; kiểu trả về được khai báo là `CharSequence` |
| `toString()` | Biểu diễn dãy tại thời điểm gọi dưới dạng `String` |
| `isEmpty()` | Kiểm tra `length() == 0` |
| `chars()` | `IntStream` của các đơn vị UTF-16 |
| `codePoints()` | `IntStream` các Unicode code point, ghép cặp surrogate hợp lệ |

Những phương thức trên hỗ trợ **đọc**, nhưng interface không bảo đảm đối tượng bên dưới là bất biến. `String` bất biến; `StringBuilder` và `StringBuffer` có thể thay đổi; `CharBuffer` có thể phản ánh mảng dữ liệu nền và trạng thái vị trí/giới hạn. `StringBuffer` đồng bộ hóa nhiều phương thức riêng lẻ, nhưng điều đó không khiến hợp đồng chung `CharSequence` trở thành bất biến hoặc bảo đảm an toàn cho mọi chuỗi thao tác đa luồng.

Chẳng hạn:

```java
StringBuilder builder = new StringBuilder("Java");
CharSequence sequence = builder;
builder.append(" 17");
System.out.println(sequence); // Java 17
```

Tham chiếu `sequence` nhìn thấy thay đổi vì cả hai tham chiếu đang trỏ tới **cùng đối tượng `StringBuilder`**. Ngược lại, nếu cần lưu một bản chụp nội dung bất biến, có thể chuyển kiểu sang `String`, ví dụ `String snapshot = builder.toString();`. Phải xác định rõ thời điểm tạo snapshot và tránh thay đổi đồng thời khi đọc một nguồn mutable.

`char[]` không triển khai `CharSequence`, nên đoạn dưới là ví dụ **cố ý sai kiểu**:

```java
char[] raw = {'H', 'i'};
// CharSequence cs = raw; // LỖI BIÊN DỊCH: char[] không implements CharSequence
CharSequence copied = new String(raw); // Bản sao bất biến
```

Nếu cần một view có thể thấy thay đổi của mảng, dùng `java.nio.CharBuffer.wrap(raw)`. View này được hỗ trợ bởi chính mảng nguồn: sửa mảng có thể quan sát qua buffer, và vị trí/giới hạn của buffer cũng ảnh hưởng `CharSequence.length()`, `charAt()`, `subSequence()` khi làm việc với `CharBuffer`.

## 5. Ví dụ hoàn chỉnh: sao chép, upcast và quan sát giá trị

Lưu thành `StringRelationsDemo.java`:

```java
public class StringRelationsDemo {
    public static void main(String[] args) {
        char[] source = {'J', 'a', 'v', 'a'};
        String text = new String(source);
        CharSequence sequence = text;
        Object asObject = text;

        source[0] = 'K';
        System.out.println(text);
        System.out.println(new String(source));
        System.out.println(sequence.length());
        System.out.println(sequence.charAt(1));
        System.out.println(sequence.subSequence(1, 3));
        System.out.println(asObject instanceof String);

        char[] snapshot = text.toCharArray();
        snapshot[0] = 'X';
        System.out.println(text);

        Object arrayAsObject = source;
        System.out.println(arrayAsObject instanceof String);
        System.out.println(String.valueOf(source));
        System.out.println(
                String.valueOf((Object) source).startsWith("[C@"));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 StringRelationsDemo.java
java StringRelationsDemo
```

Kết quả chuẩn:

```text
Java
Kava
4
a
av
true
Java
false
Kava
true
```

Giải thích:
- Hai dòng đầu cho thấy `new String(source)` đã chụp nội dung ban đầu: thay mảng nguồn thành `Kava` không ảnh hưởng `text`.
- `sequence` vẫn trỏ đến `String("Java")`, nên `length()` là 4, `charAt(1)` là `a`, `subSequence(1,3)` là `av`.
- `asObject` chứa một `String` thực, trong khi `arrayAsObject` chứa một đối tượng `char[]`; cả hai là `Object` nhưng kết quả `instanceof String` khác nhau.
- `String.valueOf(source)` chọn overload nhận `char[]`, nên trả văn bản `Kava`. Ép `source` thành `Object` chọn overload `valueOf(Object)`: mảng dùng `Object.toString()` có dạng bắt đầu bằng `[C@`, sau đó là phần định danh không ổn định. Chỉ kiểm tra tiền tố để tránh phụ thuộc vào mã băm.

## 6. Viết API tổng quát nhận `CharSequence`

Một hàm chỉ cần đọc các ký tự có thể nhận `CharSequence` để làm việc với `String`, `StringBuilder` hoặc `CharBuffer`. Ví dụ sau là **chương trình độc lập**; lưu thành `SequenceApiDemo.java`:

```java
import java.nio.CharBuffer;

public class SequenceApiDemo {
    static String prefix(CharSequence input, int count) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        int end = Math.min(count, input.length());
        return input.subSequence(0, end).toString();
    }

    public static void main(String[] args) {
        CharSequence immutable = "Hello";
        StringBuilder builder = new StringBuilder("Builder");
        char[] raw = {'C', 'h', 'a', 'r'};
        CharSequence view = CharBuffer.wrap(raw);

        System.out.println(prefix(immutable, 2));
        System.out.println(prefix(builder, 3));
        System.out.println(prefix(view, 2));

        builder.append("!");
        raw[0] = 'X';
        System.out.println(builder);
        System.out.println(view);
    }
}
```

```bash
javac -encoding UTF-8 SequenceApiDemo.java
java SequenceApiDemo
```

```text
He
Bui
Ch
Builder!
Xhar
```

Ở đây `prefix` dùng hợp đồng chung của `CharSequence`; kết quả trả về `String`. `CharBuffer.wrap(raw)` **không tạo bản sao**, nên dòng cuối thấy ký tự `X` vừa sửa. Nếu yêu cầu đóng băng đầu vào tại một thời điểm, hãy tạo một `String` từ nội dung trước khi lưu trữ; nếu cần bảo đảm nhất quán khi nhiều luồng cùng sửa nguồn, phải phối hợp đồng bộ ở bên ngoài.

### Khi nào nên nhận `String`, khi nào nên nhận `CharSequence`?

- Dùng `String` khi API cần chuỗi bất biến để lưu lâu dài, làm khóa, so sánh theo quy tắc `String`, hoặc cần các phương thức chỉ có ở `String` như `replace`, `split`, `matches`.
- Dùng `CharSequence` khi thuật toán chỉ cần đọc `length`, `charAt`, `subSequence` hoặc luồng ký tự và muốn chấp nhận nhiều cách biểu diễn. Tài liệu API nên nêu rõ liệu hàm có giữ tham chiếu đầu vào sau khi trả về hay không.
- Dùng `char[]` khi thực sự cần thao tác tại chỗ với phần tử `char`, giao tiếp với API chấp nhận mảng hoặc chủ động quản lý bản sao. Không mặc định mảng nhanh hơn: hiệu năng phụ thuộc thao tác và mức cấp phát.
- Dùng `StringBuilder` để xây dựng văn bản thay đổi nhiều lần trong cùng ngữ cảnh; gọi `toString()` khi cần kết quả bất biến.

## 7. `Object`, `toString()`, overload và các kiểu so sánh

Vì `String` là `Object`, `Object ref = "Java";` là hợp lệ; tuy nhiên **kiểu tĩnh** của tham chiếu quyết định phương thức nào có thể gọi trực tiếp. `Object.toString()` là phương thức đa hình: `String.toString()` trả lại nội dung chuỗi; `StringBuilder.toString()` trả một chuỗi biểu diễn nội dung tại thời điểm gọi. Mảng `char[]` không ghi đè `Object.toString()` để in ký tự người đọc mong đợi.

Các overload dễ gây nhầm:

```java
char[] data = {'O', 'K'};
System.out.println(String.valueOf(data));          // OK
System.out.println(String.valueOf((Object) data)); // dạng [C@..., không phải "OK"
System.out.println(data);                          // OK, do println(char[])
System.out.println((Object) data);                 // dạng [C@..., do println(Object)
```

Đoạn trên là **snippet giải thích overload**, không định nghĩa một lớp `main` riêng. Không so sánh toàn bộ dạng `[C@...` với một chuỗi cố định: phần sau ký tự `@` phụ thuộc đối tượng/chạy chương trình.

Quan hệ kiểu không quyết định cách so sánh nội dung:

| Biểu thức | Kiểm tra | Khuyến nghị |
| --- | --- | --- |
| `a == b` với hai tham chiếu | Cùng đối tượng hay không | Dùng khi quan tâm identity |
| `stringA.equals(stringB)` | Nội dung của hai `String` | Dùng cho bình đẳng chuỗi |
| `Arrays.equals(charArrayA, charArrayB)` | Từng phần tử của hai mảng | Dùng cho bình đẳng mảng |
| `charArrayA.equals(charArrayB)` | Identity của mảng (kế thừa `Object`) | Không dùng để so nội dung |
| `string.contentEquals(sequence)` | Nội dung `String` so với một `CharSequence` | Dùng khi cần so khác lớp triển khai |

`CharSequence` **không quy định lại hợp đồng `equals`/`hashCode`** của `Object`. Vì thế không nên cho rằng hai `CharSequence` có nội dung giống nhau sẽ `equals` nhau, đặc biệt khi thuộc các lớp khác nhau. Một tập hợp `HashSet<CharSequence>` hoặc `Map<CharSequence, ...>` chỉ phù hợp khi đã chủ động chọn và kiểm soát quy tắc bình đẳng, bất biến của khóa. Với khóa văn bản, `String` thường an toàn và dễ dự đoán hơn.

Ví dụ độc lập, lưu `EqualityDemo.java`:

```java
import java.util.Arrays;

public class EqualityDemo {
    public static void main(String[] args) {
        String a = new String(new char[] {'h', 'i'});
        String b = new String(new char[] {'h', 'i'});
        char[] x = {'h', 'i'};
        char[] y = {'h', 'i'};
        CharSequence builder = new StringBuilder("hi");

        System.out.println(a.equals(b));
        System.out.println(a == b);
        System.out.println(Arrays.equals(x, y));
        System.out.println(x.equals(y));
        System.out.println(a.equals(builder));
        System.out.println(a.contentEquals(builder));
    }
}
```

```bash
javac -encoding UTF-8 EqualityDemo.java
java EqualityDemo
```

```text
true
false
true
false
false
true
```

`a` và `b` có nội dung bằng nhau nhưng là hai đối tượng `String` được tạo riêng. Hai mảng `x`, `y` bằng nhau về phần tử nhưng không trỏ đến cùng một mảng. `a.equals(builder)` là `false` vì đối số không phải `String`, trong khi `contentEquals` so các ký tự nên trả `true`. Với `String` literal, JVM có thể dùng string pool; vì vậy không dùng ví dụ `"hi" == "hi"` để suy ra quy tắc so sánh nội dung chung.

## 8. Unicode: `char`, ký tự Unicode và độ dài chuỗi không luôn trùng nhau

`char` của Java có kích thước 16 bit, đại diện một **đơn vị mã UTF-16**. Một Unicode code point nằm ngoài Basic Multilingual Plane (BMP) cần **hai** `char` (một cặp surrogate). Do đó:
- `String.length()`, `CharSequence.length()` và độ dài mảng `char[]` cùng đếm **đơn vị UTF-16** trong dãy tương ứng, không nhất thiết là số Unicode code point hoặc số ký tự người đọc cảm nhận.
- `charAt(i)` trả một đơn vị UTF-16; nó có thể là nửa của cặp surrogate.
- `codePointCount`, `codePointAt`, `offsetByCodePoints` và `codePoints()` hữu ích khi cần xử lý theo code point. Một *grapheme cluster* (ký tự hiển thị) vẫn có thể gồm nhiều code point, nên đếm code point không đồng nghĩa đếm ký tự người dùng nhìn thấy.

Ví dụ độc lập, lưu `UnicodeDemo.java` (tệp mã hóa UTF-8):

```java
public class UnicodeDemo {
    public static void main(String[] args) {
        String value = "A🙂B";
        System.out.println(value.length());
        System.out.println(value.toCharArray().length);
        System.out.println(value.codePointCount(0, value.length()));
        System.out.println(value.codePoints().count());
        System.out.println(value.offsetByCodePoints(0, 2));
    }
}
```

```bash
javac -encoding UTF-8 UnicodeDemo.java
java UnicodeDemo
```

```text
4
4
3
3
3
```

Chuỗi gồm `A` (một `char`), emoji `🙂` (hai `char`), và `B` (một `char`): tổng cộng bốn đơn vị UTF-16 nhưng ba code point. Chỉ số UTF-16 ngay sau hai code point đầu là 3. Nếu cắt bằng `substring`/`subSequence` giữa hai nửa surrogate, bạn có thể tạo dãy UTF-16 không hợp lệ; khi xử lý code point, hãy tính biên bằng `offsetByCodePoints` hoặc API Unicode phù hợp.

## 9. Lỗi thường gặp và cách xử lý

1. **Cho rằng `char[]` là `CharSequence`:** ép kiểu trực tiếp không tạo adapter; dùng `new String(array)` để sao chép hoặc `CharBuffer.wrap(array)` khi chủ ý chia sẻ mảng.
2. **Dùng `==` hay `char[].equals` để so nội dung:** chọn `String.equals`, `Arrays.equals` hoặc `String.contentEquals` tùy loại dữ liệu và quy tắc mong muốn.
3. **Tin rằng mọi `CharSequence` đều bất biến:** cần xem lớp triển khai và việc lưu tham chiếu. `StringBuilder`/`CharBuffer` có thể đổi nội dung trong lúc đọc.
4. **In mảng qua `Object.toString()` rồi tưởng đó là văn bản:** `String.valueOf((Object) array)` không chọn overload `char[]`; dùng `new String(array)` hoặc `String.valueOf(array)`.
5. **Nhầm `array.length` với `string.length()`:** mảng dùng thuộc tính, `String`/`CharSequence` dùng phương thức.
6. **Ép `Object` sang `String` khi thực tế chứa mảng:** kiểm tra bằng `instanceof` rồi xử lý theo loại; ép kiểu khác chuyển đổi.
7. **Coi `charAt` là một ký tự Unicode hoàn chỉnh:** với ký tự ngoài BMP, phải làm việc theo code point hoặc grapheme cluster tùy yêu cầu.
8. **Dùng `String` để ráp nhiều đoạn trong vòng lặp lớn:** `String` bất biến nên phép nối lặp có thể tạo nhiều đối tượng trung gian; `StringBuilder` thường phù hợp khi tích lũy văn bản.
9. **Dùng một `CharSequence` mutable làm khóa map/set:** biến đổi nội dung hay khác biệt `equals`/`hashCode` giữa lớp triển khai có thể gây kết quả khó dự đoán; thường nên chuẩn hóa thành `String` khi chọn khóa văn bản.
10. **Giả định `char[]` chứa bí mật thì có thể xóa sạch mọi bản sao:** có thể ghi đè mảng mình sở hữu, nhưng Java/JVM/API có thể tạo bản sao ở nơi khác. Không hứa bảo đảm xóa khỏi toàn bộ bộ nhớ chỉ bằng một lần `Arrays.fill`.

## 10. Quy tắc lựa chọn nhanh và tự kiểm tra

Hãy xác định yêu cầu trước khi chọn kiểu:

- **Cần một giá trị văn bản ổn định:** dùng `String`.
- **Cần tham số chỉ đọc để chấp nhận nhiều nguồn văn bản:** dùng `CharSequence`; quyết định rõ liệu dữ liệu có được chụp thành `String` khi lưu hay không.
- **Cần sửa từng phần tử dữ liệu UTF-16:** dùng `char[]` hoặc một buffer phù hợp.
- **Cần xây dựng/nối liên tục:** dùng `StringBuilder`, rồi lấy `String` khi hoàn tất.
- **Chỉ có tham chiếu `Object`:** kiểm tra kiểu thực tế và chuyển đổi có chủ đích; không kỳ vọng `Object.toString()` của mọi loại đều trả nội dung văn bản.

Câu hỏi ôn tập:
1. Vì sao thay `charArray[0]` sau `new String(charArray)` không làm đổi `String`, còn với `CharBuffer.wrap(charArray)` thì có thể quan sát thấy thay đổi?
2. Vì sao `CharSequence s = new StringBuilder("x");` là hợp lệ, còn `CharSequence s = new char[] {'x'};` không hợp lệ?
3. `String.valueOf(array)` khác `String.valueOf((Object) array)` ở bước chọn overload nào?
4. Vì sao `string.equals(builder)` và `string.contentEquals(builder)` có thể trả kết quả khác nhau?
5. Khi `text.length() == 4`, có thể kết luận chuỗi có đúng bốn Unicode code point hay bốn ký tự hiển thị không? Vì sao?

Nắm được **quan hệ kiểu**, **tính bất biến/sao chép**, **hợp đồng `CharSequence`** và **đơn vị UTF-16** sẽ giúp thiết kế API đúng, tránh lỗi ép kiểu/so sánh và chọn cấu trúc dữ liệu phù hợp.

## Tài liệu API chính thức (Java SE 17)

- [`String` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`CharSequence` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
- [`CharBuffer` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/CharBuffer.html)
- [`Arrays` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)
