# `new String` và vì sao thường không cần sao chép một `String` đã có

Trong Java, khi đã có một giá trị `String`, ta thường chỉ cần dùng lại tham chiếu tới nó. Viết `new String(existing)` tạo **đối tượng `String` khác nhưng có cùng nội dung** với `existing`. Vì `String` bất biến, việc tạo đối tượng mới này thường không giúp dữ liệu an toàn hơn và có thể gây chi phí cấp phát không cần thiết.

Bài học phân biệt rõ **biến tham chiếu**, **danh tính đối tượng (identity)**, **giá trị nội dung**, và các trường hợp constructor `String` thật sự hữu ích.

## 1. Gán tham chiếu khác với gọi `new String(...)`

```java
String original = "Java";
String alias = original;
String copy = new String(original);
```

- `original` tham chiếu đến một đối tượng `String` mang nội dung `"Java"`. Chuỗi literal được quản lý trong *string pool*.
- `alias = original` sao chép **giá trị tham chiếu**. `original` và `alias` cùng trỏ đến một đối tượng; không tạo thêm `String`.
- `copy = new String(original)` gọi constructor `String(String original)`. Nó tạo một đối tượng mới, có **nội dung bằng** `original` nhưng **danh tính khác**.

```text
original ──┐
           ├────────> đối tượng A: String "Java"
alias ─────┘

copy ────────────────> đối tượng B: String "Java"
```

Lưu ý kỹ: «đối tượng mới» không đồng nghĩa với «chắc chắn sao chép toàn bộ mảng byte lưu trữ nội bộ». Java bảo đảm ngữ nghĩa tạo một đối tượng `String` mới; cách JVM lưu hay chia sẻ dữ liệu nội bộ là chi tiết triển khai, không phải cam kết của API.

### Ví dụ chạy được trên Java 17+

Tạo tệp `StringCopyDemo.java`:

```java
public class StringCopyDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String copy = new String(original);

        System.out.println(original == alias);
        System.out.println(original == copy);
        System.out.println(original.equals(copy));
        System.out.println(copy.equals("Java"));
    }
}
```

Biên dịch và chạy:

```bash
javac StringCopyDemo.java
java StringCopyDemo
```

Kết quả chuẩn:

```text
true
false
true
true
```

Giải thích: `==` trên hai biến tham chiếu kiểm tra **cùng đối tượng hay không**, còn `String.equals` kiểm tra **cùng dãy ký tự hay không**. Vì thế `original == copy` sai nhưng `original.equals(copy)` đúng.

Khi so sánh nội dung, ưu tiên `a.equals(b)`. Nếu `a` có thể `null`, dùng `Objects.equals(a, b)` sau khi import `java.util.Objects`; hoặc đặt hằng ở vế trái như `"Java".equals(a)`. Không dựa vào `==` chỉ vì một số literal có thể cùng nằm trong pool.

## 2. `String` bất biến: vì sao không cần sao chép phòng vệ?

Đối tượng `String` là *immutable*. API công khai thông thường không cung cấp thao tác chỉnh sửa dãy ký tự đã lưu bên trong đối tượng đó. Các phương thức `replace`, `concat`, `trim`, `substring`, `toUpperCase`… tạo hoặc trả về một **giá trị chuỗi kết quả**; chúng không làm biến đổi nội dung đối tượng nguồn. Một phương thức có thể trả về cùng tham chiếu khi không có gì thay đổi, tùy hợp đồng của phương thức.

Xét ví dụ `StringImmutabilityDemo.java`:

```java
public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String original = "cat";
        String alias = original;
        String modified = original.replace('c', 'b');

        System.out.println(original);
        System.out.println(alias);
        System.out.println(modified);

        original = "dog";
        System.out.println(alias);
        System.out.println(original);
    }
}
```

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

```text
cat
cat
bat
cat
dog
```

Ở ba dòng đầu, `replace` cho ra chuỗi `"bat"` còn cả `original` và `alias` vẫn thấy `"cat"`. Sau đó, lệnh `original = "dog"` chỉ đổi tham chiếu lưu trong **biến** `original`; `alias` vẫn trỏ đến đối tượng `"cat"` cũ. **Gán lại biến khác với sửa nội dung đối tượng.**

Vì thế, khi viết lớp chứa một trường `String`, ta thường không cần sao chép trong constructor và getter:

```java
public final class UserLabel {
    private final String label;

    public UserLabel(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
```

Đây là một lớp minh họa dùng trong chương trình khác, không có `main` riêng. Hai cách viết `this.label = new String(label)` và `return new String(label)` thường chỉ tạo thêm đối tượng mà không tăng mức bảo vệ nội dung. `final` bảo đảm trường `label` không bị gán lại sau khi khởi tạo; tính bất biến của chính đối tượng `String` là tính chất riêng.

Nếu nghiệp vụ yêu cầu `label` không được `null` hoặc không được rỗng, phải **kiểm tra giá trị đầu vào** phù hợp; việc bọc `new String(label)` không thay thế kiểm tra hợp lệ.

## 3. Tác động của String pool

*String pool* cho phép JVM dùng lại tham chiếu chuẩn tắc của literal và chuỗi đã intern. Ví dụ:

```java
String a = "hello";
String b = "hello";
String c = new String("hello");

System.out.println(a == b);      // true
System.out.println(a == c);      // false
System.out.println(a.equals(c));  // true
```

Ở đây `a` và `b` cùng trỏ tới literal đã intern, còn `new String("hello")` tạo đối tượng khác. Không cần viết `new String("hello")` để «kích hoạt» pool: literal đã thuộc cơ chế pool từ đầu.

Phương thức `intern()` trả về tham chiếu chuẩn tắc của chuỗi có nội dung tương ứng trong pool; nó có mục đích khác với `new String(String)`. Dùng `intern()` để ép `==` hoạt động trong logic nghiệp vụ thường gây ràng buộc thừa. `equals` diễn đạt đúng ý định so sánh nội dung.

Nhớ rằng **không phải mọi chuỗi có cùng nội dung đều cùng tham chiếu**. Chuỗi được tính toán lúc chạy, đọc từ tệp, lấy từ API hoặc tạo từ các đối tượng khác có thể bằng nhau về nội dung nhưng khác identity.

## 4. Hệ quả khi lạm dụng `new String(existing)`

Cùng một nhu cầu đặt tên biến mới:

```java
String source = "Java Core";
String first = source;             // Ưu tiên.
String second = new String(source); // Thường dư thừa.
```

Cả `first` và `second` đều cho nội dung `"Java Core"`. Tuy nhiên:

1. **Đối tượng mới**: theo ngữ nghĩa Java, biểu thức `new` tạo một đối tượng riêng, kéo theo khả năng cấp phát và thu gom rác thêm. JIT có thể tối ưu bỏ cấp phát khi không quan sát được, nên không thể khẳng định một mức overhead cố định trong mọi lần chạy.
2. **Danh tính thay đổi**: `first == second` là `false` mặc dù `first.equals(second)` là `true`. Khi code vô tình phụ thuộc vào identity, bản sao mới có thể khiến hành vi khác đi.
3. **Làm mờ ý nghĩa của code**: người đọc có thể nghĩ cần tách hai chuỗi để ngăn một bên sửa nội dung bên kia, trong khi `String` vốn bất biến.
4. **Không xử lý `null` tốt hơn**: phép gán `String alias = source` chấp nhận `source == null`; ngược lại `new String((String) null)` ném `NullPointerException`. Ép kiểu trong ví dụ làm rõ overload `String(String)`.

Hiếm khi một thiết kế thật sự cần *identity* riêng của `String`. Nếu có, yêu cầu này phải được diễn đạt cụ thể và xem xét cẩn thận vì so sánh, đồng bộ hoặc cấu trúc dữ liệu dựa trên identity của chuỗi dễ gây lỗi. Với dữ liệu văn bản thông thường, giá trị nội dung mới là điều quan trọng.

## 5. Khi nào dùng constructor `new String(...)`?

Phân biệt loại đầu vào:

| Cách viết | Đầu vào / mục tiêu | Đánh giá |
| --- | --- | --- |
| `String b = a;` | `a` đã là `String`; dùng lại giá trị bất biến | **Nên dùng** trong trường hợp thường gặp |
| `new String(a)` | `a` đã là `String`; tạo identity mới cùng nội dung | **Hầu như không cần** |
| `new String(chars)` | `char[]` có thể bị thay đổi; chụp nội dung ký tự | **Có ích** khi chuyển mảng thành chuỗi |
| `new String(bytes, StandardCharsets.UTF_8)` | Giải mã `byte[]` theo charset cụ thể | **Có ích** khi xử lý bytes |
| `builder.toString()` | Lấy chuỗi từ `StringBuilder` | **Phù hợp**, không cần bọc `new String(...)` |
| `new String()` | Tạo chuỗi rỗng | Dùng `""` đơn giản hơn |

### Vì sao mảng ký tự là trường hợp khác?

`char[]` có thể thay đổi, còn `String` thì bất biến. Tạo `String` từ mảng lấy nội dung ở thời điểm gọi; dùng lại một tham chiếu `String` đã có không cần bước này. Ví dụ sau so sánh trực tiếp hai trường hợp:

Tạo tệp `StringSourceChoiceDemo.java`:

```java
public class StringSourceChoiceDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String redundant = new String(original);
        char[] letters = {'J', 'a', 'v', 'a'};
        String fromArray = new String(letters);
        letters[0] = 'K';

        System.out.println(original == alias);
        System.out.println(original == redundant);
        System.out.println(original.equals(redundant));
        System.out.println(fromArray);
        System.out.println(new String(letters));
    }
}
```

Chạy `javac -encoding UTF-8 StringSourceChoiceDemo.java` rồi `java StringSourceChoiceDemo`:

```text
true
false
true
Java
Kava
```

`alias` chỉ sao chép tham chiếu, `redundant` tạo đối tượng chuỗi riêng dù nội dung bằng nhau. `fromArray` giữ giá trị `"Java"` sau khi mảng đổi thành `Kava`. Đó là lý do chuyển từ mảng có ý nghĩa, còn sao chép một `String` đã có thường dư thừa. Các bài về `char[]`, `byte[]` và `StringBuilder` trước đó trình bày chi tiết từng cơ chế chuyển đổi.

## 6. Chọn cách viết đúng theo mục tiêu

### Trường hợp A: dùng lại chuỗi sẵn có

```java
String title = "Java";
String displayTitle = title;
```

Dùng lại tham chiếu. Không có nguy cơ một phép nối chuỗi sau đó làm sửa đối tượng cũ.

### Trường hợp B: tạo giá trị văn bản đã biến đổi

```java
String raw = " java ";
String normalized = raw.trim().toUpperCase();
```

`raw` vẫn có nội dung `" java "`, còn `normalized` có nội dung `"JAVA"`. Ta gọi phương thức xử lý để lấy **giá trị khác**, không sao chép `raw` rồi mong nó tự thay đổi.

### Trường hợp C: xây dựng chuỗi qua nhiều bước

```java
StringBuilder builder = new StringBuilder();
builder.append("Hello");
builder.append(", ");
builder.append("Java");
String message = builder.toString();
```

`message` chứa `"Hello, Java"`. `StringBuilder` thích hợp khi có nhiều lần bổ sung ký tự; `toString()` kết thúc việc xây dựng và cung cấp giá trị `String` bất biến. Không cần thêm `new String(message)`.

### Trường hợp D: cần kiểm tra tham số `String`

```java
import java.util.Objects;

public final class Greeting {
    private final String message;

    public Greeting(String message) {
        this.message = Objects.requireNonNull(message, "message");
    }

    public String message() {
        return message;
    }
}
```

Đây là lớp minh họa độc lập về thiết kế, không có `main`. `Objects.requireNonNull` đặt ra điều kiện đầu vào khác với vấn đề sao chép. Lưu trực tiếp và trả trực tiếp `String` là hợp lý vì `String` bất biến.

## 7. Những nhầm lẫn dễ gặp

**«`b = a` thì sửa `b` sẽ sửa `a`?»** Không. Không có API sửa nội dung đối tượng `String` tại chỗ. Viết `b = b + "!"` làm `b` nhận giá trị/tham chiếu mới; `a` không bị thay đổi.

**«`new String(a)` chắc chắn deep copy dữ liệu nội bộ?»** Không có bảo đảm công khai như vậy. Điều quan trọng ở cấp ngôn ngữ là object identity mới và nội dung chuỗi tương ứng. Không nên dựa vào cách JVM biểu diễn các ký tự trong bộ nhớ.

**«Hai chuỗi cùng chữ thì `==` phải đúng?»** Sai. `equals` dùng để so nội dung. `==` có thể đúng với cùng literal hoặc cùng tham chiếu, nhưng không phải quy tắc tổng quát cho giá trị văn bản.

**«Constructor của một lớp cần phòng vệ tham số `String` bằng `new String(name)`?»** Thường không. Gán lại biến của người gọi không thay đổi chuỗi được trường lưu giữ. Nếu tham số là `char[]` hay đối tượng mutable thì vấn đề khác.

**«Hàm Java có thể thay đổi chuỗi của người gọi do truyền tham chiếu?»** Java truyền **giá trị** của tham số; với đối tượng, giá trị đó là tham chiếu. Gán lại biến tham số trong hàm không gán lại biến của người gọi, và chuỗi không có phương thức sửa nội dung tại chỗ.

**«`new String()` tốt hơn `""` vì tạo giá trị rỗng riêng?»** Với nhu cầu chuỗi rỗng thông thường, literal `""` ngắn, rõ nghĩa và tránh chủ động tạo wrapper thừa.

## 8. Tự kiểm tra

Dự đoán bốn dòng đầu ra:

```java
String first = "core";
String second = first;
String third = new String(first);

second = second.concat("-java");

System.out.println(first);
System.out.println(second);
System.out.println(first == third);
System.out.println(first.equals(third));
```

Đáp án:

```text
core
core-java
false
true
```

`second` được gán lại kết quả `concat`; `first` vẫn là `"core"`. `third` là đối tượng khác vì `new`, nhưng nội dung vẫn bằng `first`.

Hai câu hỏi tự đánh giá:

1. Trong getter trả về một trường `private final String name`, `return new String(name)` có làm dữ liệu an toàn hơn không? **Không:** `String` đã bất biến.
2. Có thể thay `new String(bytes, StandardCharsets.UTF_8)` bằng `String text = bytes` khi cần đọc dữ liệu mạng không? **Không:** `byte[]` không phải `String`; cần giải mã bytes theo charset thích hợp.

**Ghi nhớ:** `String b = a` dùng lại một giá trị bất biến; `new String(a)` tạo đối tượng `String` mới cùng nội dung, thường dư thừa. Constructor `String` hữu ích hơn khi đầu vào là **mảng ký tự, bytes hoặc dữ liệu phải chuyển đổi thành chuỗi**.