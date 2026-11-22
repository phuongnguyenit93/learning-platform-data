# Vì sao `String` là lớp `final` và có tính bất biến trong Java?

`String` là kiểu tham chiếu dùng để biểu diễn chuỗi ký tự trong Java. Khai báo của lớp trong Java 17+ có dạng `public final class String ...`. Tài liệu Java xác định rõ: **giá trị của một đối tượng `String` không thể thay đổi sau khi đối tượng được tạo** (*immutable*). Hai đặc điểm `final` và *immutable* bổ trợ nhau để chuỗi có thể được chia sẻ an toàn, có hành vi ổn định và được tối ưu hiệu quả.

Sau bài này, bạn cần phân biệt được `final` của lớp, `final` của biến tham chiếu và tính bất biến của đối tượng; giải thích tại sao các thao tác trên chuỗi không sửa chuỗi gốc; và vận dụng điều đó khi so sánh chuỗi, sử dụng String Pool, làm khóa `HashMap` hoặc xử lý chuỗi trong chương trình đa luồng.

## 1. `final` và immutable là hai khái niệm khác nhau

| Khái niệm | Điều được đảm bảo | Điều **không** tự động được đảm bảo |
| --- | --- | --- |
| `final class` | Không thể khai báo lớp con kế thừa lớp đó. | Đối tượng của lớp không nhất thiết bất biến. |
| `final` trên biến tham chiếu | Không thể gán lại biến để trỏ đến đối tượng khác sau khi khởi tạo. | Đối tượng mà biến trỏ tới vẫn có thể thay đổi nếu loại của nó cho phép. |
| Đối tượng immutable | Trạng thái có thể quan sát của đối tượng không đổi sau khi tạo. | Bản thân lớp không bắt buộc phải khai báo `final` trong mọi thiết kế. |

**`String` là `final`** nghĩa là đoạn `class MyString extends String` không hợp lệ: trình biên dịch báo lỗi vì không thể kế thừa lớp final. Đây là một ràng buộc ở cấp **kiểu dữ liệu**.

**`String` là immutable** nghĩa là sau khi tạo `String s = "Java";`, nội dung của đối tượng `"Java"` không thể bị thay thành `"Kava"` qua API thông thường. Đây là một cam kết về **trạng thái đối tượng**.

Ví dụ sau minh họa rằng `final class` một mình không khiến đối tượng bất biến (đoạn định nghĩa lớp, không có hàm `main`):

```java
final class Counter {
    private int value;

    void increment() {
        value++; // Trạng thái của Counter vẫn thay đổi.
    }

    int value() {
        return value;
    }
}
```

Ngược lại, dù không viết `final String s`, đối tượng `String` vẫn bất biến:

```java
String s = "Java";
s = "Kotlin"; // Hợp lệ: biến s được gán sang một đối tượng String khác.
```

Nếu khai báo `final String s = "Java";` thì `s = "Kotlin";` là lỗi biên dịch do **gán lại tham chiếu**. Nó không làm đối tượng `"Java"` “bất biến hơn” vì đối tượng đó vốn đã bất biến. Tương tự, `final StringBuilder builder = new StringBuilder("A");` vẫn cho phép `builder.append("B")`, bởi `StringBuilder` có trạng thái thay đổi được.

## 2. `String` giữ tính bất biến bằng cách nào?

Một lớp muốn cung cấp tính bất biến cần bảo vệ trạng thái nội tại và không cung cấp đường sửa trạng thái đó từ bên ngoài. `String` thực hiện điều này thông qua hợp đồng API và cách cài đặt của thư viện Java:

1. **Không cung cấp phương thức sửa nội dung tại chỗ.** Không có `setCharAt`, `append` hay `delete` trên `String`. Các phương thức `concat`, `replace`, `substring`, `toUpperCase`, `toLowerCase`… trả về kết quả dạng `String`; chúng không đổi nội dung của đối tượng nhận lời gọi.
2. **Không để mã gọi can thiệp vào bộ nhớ chứa nội dung chuỗi.** Chẳng hạn, hàm tạo `String(char[])` sao chép nội dung mảng truyền vào. `toCharArray()` trả về một mảng mới; sửa mảng đầu vào hay đầu ra đó không sửa được chuỗi.
3. **Chặn kế thừa bằng `final`.** Không có lớp con nào có thể thêm trạng thái biến đổi hoặc ghi đè hành vi để phá vỡ hợp đồng của `String` khi đối tượng được dùng qua kiểu `String`.
4. **Giữ trạng thái nội tại dưới quyền kiểm soát của thư viện/JVM.** Ở các JDK hiện đại, biểu diễn nội bộ có thể được tối ưu mà không làm thay đổi ý nghĩa của API công khai.

`final` **không tự tạo ra tính bất biến**; thiết kế không có đường sửa giá trị mới là nền tảng. Tuy vậy, `final` giúp Java đảm bảo mọi đối tượng có kiểu `String` đều tuân theo đúng hợp đồng của lớp, tránh việc mã phía ngoài tạo một lớp con có hành vi bất ngờ.

### Biểu diễn nội bộ không phải hợp đồng công khai

Nhiều tài liệu Java 8 mô tả `String` chứa mảng `char[]`. Kể từ Java 9, OpenJDK áp dụng **Compact Strings** (JEP 254): nội dung có thể lưu bằng `byte[]` cùng thông tin mã hóa Latin-1 hoặc UTF-16 để giảm bộ nhớ khi thích hợp. Đây là chi tiết cài đặt; **không nên suy luận tính bất biến chỉ từ việc tồn tại `final byte[]`**. Một biến `final` trỏ đến mảng vẫn có thể trỏ tới mảng có các phần tử bị sửa nếu quyền truy cập không được bảo vệ. Tính bất biến của `String` đến từ toàn bộ thiết kế và hợp đồng của nó.

## 3. Thực nghiệm: thao tác tạo kết quả mới, chuỗi gốc giữ nguyên

Tạo tệp `StringImmutabilityDemo.java`:

```java
import java.util.Locale;

public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String source = "Java";
        String extended = source.concat(" 17");

        System.out.println("source = " + source);
        System.out.println("extended = " + extended);
        System.out.println("same object = " + (source == extended));

        String lower = source.toLowerCase(Locale.ROOT);
        System.out.println("lower = " + lower);
        System.out.println("source after toLowerCase = " + source);

        char[] input = {'J', 'a', 'v', 'a'};
        String copied = new String(input);
        input[0] = 'X';
        System.out.println("copied after input changed = " + copied);

        char[] output = copied.toCharArray();
        output[0] = 'Y';
        System.out.println("copied after output changed = " + copied);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

Kết quả:

```text
source = Java
extended = Java 17
same object = false
lower = java
source after toLowerCase = Java
copied after input changed = Java
copied after output changed = Java
```

Diễn giải:

- `source.concat(" 17")` trả về chuỗi có nội dung khác. `source` vẫn là `"Java"`, còn `extended` chứa `"Java 17"`; vì khác nội dung, chúng chắc chắn không phải cùng một đối tượng.
- `toLowerCase(Locale.ROOT)` trả về kết quả chữ thường mà không sửa `source`. Với các phương thức có kết quả **không đổi** (ví dụ nối chuỗi rỗng), cài đặt **có thể trả lại chính đối tượng hiện tại**. Vì thế không được khẳng định “mỗi lệnh trên `String` luôn cấp phát một đối tượng mới”.
- Thay đổi `input` sau hàm tạo, hay thay đổi mảng do `toCharArray()` trả về, đều không ảnh hưởng đến `copied`. Đây là ví dụ trực tiếp về việc không để lộ trạng thái nội bộ có thể sửa.

Câu lệnh `s += "!"` cũng cần được hiểu đúng: nó tương đương về kết quả với `s = s + "!"`, nghĩa là biểu thức tạo giá trị chuỗi đã nối rồi **gán lại biến `s`**; đối tượng chuỗi cũ không bị thay đổi. Nếu nhiều biến cùng tham chiếu chuỗi cũ, chúng vẫn thấy nội dung cũ.

## 4. Vì sao Java thiết kế `String` vừa `final` vừa immutable?

### 4.1. Chia sẻ chuỗi và String Pool an toàn

Java sử dụng **String Pool** để tái sử dụng các đối tượng biểu diễn cùng hằng chuỗi, đặc biệt là các literal như `"java"`. Nếu một bên có thể sửa nội dung của một đối tượng đã được chia sẻ, những nơi khác dùng chung đối tượng đó sẽ bị ảnh hưởng ngoài ý muốn. Tính bất biến khiến việc chia sẻ trở nên an toàn.

Ví dụ hoàn chỉnh, lưu dưới tên `StringPoolDemo.java`:

```java
public class StringPoolDemo {
    public static void main(String[] args) {
        String a = "java";
        String b = "java";
        String c = new String("java");
        String canonical = c.intern();

        System.out.println("a == b: " + (a == b));
        System.out.println("a == c: " + (a == c));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("a == canonical: " + (a == canonical));
    }
}
```

Chạy:

```bash
javac StringPoolDemo.java
java StringPoolDemo
```

Kết quả:

```text
a == b: true
a == c: false
a.equals(c): true
a == canonical: true
```

- Hai literal `"java"` trong ví dụ cùng trỏ đến đối tượng chuỗi đã được intern.
- `new String("java")` tạo một đối tượng `String` khác có **cùng nội dung**.
- `intern()` trả về tham chiếu chuẩn của chuỗi tương ứng trong pool.
- Dùng `equals()` để kiểm tra **nội dung**; `==` so sánh **tham chiếu**. Đừng dùng `==` để so sánh nội dung chuỗi lấy từ dữ liệu người dùng, file hay API.

Lưu ý: biểu thức nối **hằng chuỗi lúc biên dịch** có thể trở thành một literal; nối từ dữ liệu ở thời điểm chạy có cơ chế tạo kết quả khác. Không suy đoán kết quả `==` chỉ dựa vào cách viết biểu thức nối.

### 4.2. Khóa `HashMap` và `HashSet` có ý nghĩa ổn định

Cấu trúc băm dùng `hashCode()` và `equals()` để tổ chức và tra cứu phần tử. Khi một `String` được dùng làm khóa, nội dung không đổi nên giá trị băm và kết quả so sánh theo nội dung của khóa cũng ổn định. Nhờ đó, một khóa không “đổi chỗ” về mặt logic sau khi đưa vào bảng băm.

Ví dụ nhỏ trong một phương thức Java:

```java
Map<String, Integer> counts = new HashMap<>();
String key = "user:42";
counts.put(key, 1);

key = key.concat(":active"); // Gán biến key sang chuỗi khác.
System.out.println(counts.get("user:42"));    // 1
System.out.println(counts.get(key));          // null
```

Đoạn này cần `import java.util.Map;` và `import java.util.HashMap;` nếu đặt trong một lớp độc lập. Bản thân khóa `"user:42"` trong `counts` vẫn nguyên vẹn. Việc lưu mã băm để tái sử dụng trong một số cài đặt `String` cũng khả thi vì nội dung không đổi; cách cache cụ thể là chi tiết triển khai.

Với **một đối tượng khóa có trường dùng trong `equals()/hashCode()` bị sửa sau khi đưa vào `HashMap`**, phép tra cứu có thể thất bại. `String` tránh hẳn nhóm lỗi này ở mức nội dung chuỗi.

### 4.3. Dễ chia sẻ giữa các luồng

Nhiều luồng có thể đồng thời **đọc và dùng chung cùng một đối tượng `String`** mà không cần khóa để bảo vệ việc sửa nội dung: không luồng nào có thể đổi nội dung đối tượng đó qua API bình thường. Điều này giúp giảm số tình huống race condition liên quan đến trạng thái của đối tượng.

Nhưng **immutable không đồng nghĩa toàn bộ chương trình tự động thread-safe**. Ví dụ, nếu hai luồng cùng gán lại một trường `String currentName`, việc công bố giá trị mới, tính nhìn thấy giữa luồng và các thao tác nhiều bước vẫn có thể cần `volatile`, `synchronized` hoặc cơ chế đồng bộ thích hợp. Tính bất biến chỉ đảm bảo nội dung của **từng đối tượng `String`** không bị sửa.

### 4.4. Duy trì hợp đồng API và hạn chế thay đổi dữ liệu ngoài ý muốn

`String` thường biểu diễn tên tệp, đường dẫn, khóa cấu hình, URL, định danh hoặc tham số đã được kiểm tra. Một hàm nhận `String` có thể tin rằng **nội dung chính đối tượng ấy** không bị caller lặng lẽ sửa sau khi truyền vào. Nếu cho phép lớp con thay đổi cách hành xử hoặc cho phép sửa trạng thái, các giả định của API, mã băm và nơi chia sẻ tham chiếu đều có thể bị phá vỡ.

Lợi ích này không thay thế việc kiểm tra đầu vào, phân quyền hoặc đồng bộ khi có dữ liệu mới được gán vào biến. Tính bất biến cũng không tự làm cho giá trị người dùng nhập trở nên an toàn.

## 5. Khi làm việc với `String`, nên chọn API nào?

| Nhu cầu | Phù hợp | Lý do |
| --- | --- | --- |
| Giá trị văn bản ổn định, truyền giữa các hàm, key của map | `String` | Dễ chia sẻ, không có phép sửa nội dung tại chỗ. |
| Tạo một vài biểu thức nối đơn giản | Toán tử `+` với `String` | Rõ ràng, trình biên dịch/JVM có thể tối ưu; không cần tự tối ưu sớm. |
| Ghép nhiều phần trong vòng lặp hoặc dựng văn bản từng bước | `StringBuilder` | Có `append`, `insert`, `delete` thay đổi vùng đệm; thường tránh tạo nhiều giá trị trung gian. |
| Bộ đệm văn bản mutable dùng chung giữa các luồng và cần phương thức đồng bộ | `StringBuffer` trong ngữ cảnh thích hợp | Các phương thức chính có đồng bộ; thao tác ghép nhiều bước vẫn cần xét tính nguyên tử. |

Ví dụ dựng chuỗi qua vòng lặp bằng `StringBuilder`:

```java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append(", ");
    }
    builder.append(i);
}
String result = builder.toString(); // "1, 2, 3"
```

`StringBuilder` thay đổi trạng thái trong lúc dựng kết quả. `toString()` trả về `String` bất biến để dùng hoặc chia sẻ tiếp. `StringBuilder` không tự bảo đảm an toàn khi nhiều luồng cùng sửa một instance.

## 6. Các ngộ nhận và lỗi phổ biến

1. **“`final` là đủ để một đối tượng bất biến.”** Sai: ví dụ `Counter` ở trên là lớp `final` nhưng có trường `value` được tăng.
2. **“`final String s` có nghĩa là nội dung mới bất biến.”** Sai: mọi `String` đều bất biến; `final` trên `s` chỉ cấm gán lại tham chiếu.
3. **“`replace()` hoặc `toUpperCase()` sẽ sửa biến gốc.”** Sai: phải nhận kết quả nếu muốn sử dụng, ví dụ `s = s.replace("a", "b");`. Gọi mà bỏ giá trị trả về không thay chuỗi đang giữ.
4. **“Mọi phương thức xử lý `String` đều tạo instance mới.”** Sai: phương thức có thể trả về chính instance nếu kết quả không khác (và literal được pool chia sẻ).
5. **“Hai chuỗi bằng nội dung thì `==` luôn `true`.”** Sai: `==` hỏi có cùng tham chiếu không; `equals()` mới so sánh nội dung theo API của `String`.
6. **“String Pool là nguyên nhân khiến `String` bất biến.”** Quan hệ thực tế đi theo hướng ngược lại: tính bất biến **cho phép** pool chia sẻ đối tượng mà không sợ bên dùng này sửa dữ liệu bên dùng kia.
7. **“Có `String` thì không cần quan tâm đồng bộ.”** Sai với những biến hoặc cấu trúc dữ liệu tham chiếu đến `String` bị nhiều luồng cập nhật.
8. **“Độ dài `String` luôn bằng số ký tự người dùng nhìn thấy.”** `length()` đếm **UTF-16 code units**; một ký tự Unicode ngoài BMP có thể chiếm hai đơn vị. Dùng `codePointCount(0, s.length())` khi cần đếm code point; ký tự hiển thị với dấu ghép vẫn là vấn đề riêng.
9. **“Mật khẩu luôn nên lưu trong `String`.”** Vì nội dung `String` không thể xóa tại chỗ, ứng dụng xử lý bí mật nhạy cảm có thể ưu tiên `char[]` hoặc `byte[]` khi giao thức/thư viện cho phép xóa vùng đệm sau sử dụng. Việc đó vẫn phải đi kèm quản lý vòng đời dữ liệu và cơ chế bảo mật phù hợp.

## 7. Cách tự kiểm tra mức độ hiểu

Xét đoạn mã:

```java
String x = "Hi";
String y = x;
x = x.concat(" Java");

System.out.println(x);
System.out.println(y);
System.out.println(x == y);
```

Kết quả là:

```text
Hi Java
Hi
false
```

Giải thích: lúc đầu `x` và `y` cùng tham chiếu `"Hi"`. Phép nối tạo giá trị `"Hi Java"`; chỉ biến `x` được gán tham chiếu kết quả. `y` tiếp tục giữ chuỗi `"Hi"` và đối tượng cũ không thay đổi.

**Ghi nhớ ba tầng:** `final class String` chặn kế thừa; tính bất biến bảo vệ nội dung từng đối tượng; còn `final String variable` chỉ bảo vệ việc gán lại một biến tham chiếu. Thiết kế kết hợp này giúp `String` chia sẻ an toàn trong pool và giữa các luồng, giữ khóa băm ổn định và khiến luồng dữ liệu văn bản dễ suy luận hơn.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): khai báo `final`, đặc tính bất biến, hàm tạo, `equals`, `intern` và các API chuỗi.
- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254): thay đổi biểu diễn nội bộ từ Java 9; không thay đổi giao diện hoặc hợp đồng bất biến.
