# Chẩn đoán lỗi ambiguous default, kiểu trả về và erasure

## 1. Nhận diện ba nhóm lỗi

- **Ambiguous default:** nhiều interface không liên quan cung cấp cùng một phương thức `default`, khiến compiler không thể tự chọn phần triển khai.
- **Kiểu trả về không tương thích:** các khai báo cùng tên và danh sách tham số nhưng yêu cầu kiểu trả về không thể cùng được thỏa mãn.
- **Erasure/name clash:** các khai báo khác nhau ở tham số generic nhưng sau khi xóa kiểu lại có cùng chữ ký.

Đây là lỗi thời điểm biên dịch. Cần kiểm tra hợp đồng được kế thừa, chữ ký sau khi thay tham số kiểu, quy tắc covariance và type erasure thay vì chỉ nhìn dòng gọi gây lỗi.

## 2. Ambiguous default method

Từ Java 8, interface có thể cung cấp phần thân cho phương thức `default`. Nếu một lớp triển khai hai interface không liên quan và cả hai định nghĩa cùng một phương thức mặc định, lớp nhận hai ứng viên ngang nhau và phải giải quyết xung đột.

Ví dụ cố ý không biên dịch:

```java
interface Left {
    default void ping() { System.out.println("Left"); }
}
interface Right {
    default void ping() { System.out.println("Right"); }
}
class Broken implements Left, Right {
    // Compile error: inherits unrelated defaults for ping()
}
```

### Cách sửa: ghi đè tường minh

Lớp có thể tự định nghĩa phương thức rồi gọi một hoặc cả hai phần thân mặc định qua `InterfaceName.super.method()`:

```java
class Combined implements Left, Right {
    @Override
    public void ping() {
        Left.super.ping();
        Right.super.ping();
        System.out.println("Combined");
    }
}
```

`Left.super.ping()` và `Right.super.ping()` gọi phần triển khai mặc định tương ứng. Chỉ gọi một bên nếu đó là hành vi mong muốn; gọi cả hai có thể lặp tác dụng phụ.

### Quy tắc ưu tiên

1. Phương thức instance phù hợp được kế thừa từ lớp cha thường ưu tiên hơn default của interface. Tuy nhiên, khai báo abstract trong lớp cha có thể buộc lớp concrete cung cấp phần triển khai.
2. Nếu subinterface ghi đè default, định nghĩa ở interface cụ thể hơn được dùng.
3. Hai default không liên quan yêu cầu lớp concrete ghi đè để giải quyết xung đột.
4. Subinterface có thể khai báo lại phương thức abstract, buộc lớp triển khai cung cấp phần thân.

Đừng nhầm xung đột default với overload. Overload có danh sách tham số khác nhau; lỗi này xuất hiện khi cùng một chữ ký được thừa hưởng từ nhiều interface.

## 3. Kiểu trả về không tương thích

### Kiểu trả về không tạo overload

Java không cho khai báo hai phương thức chỉ khác kiểu trả về:

```java
class ReturnOnly {
    int value() { return 1; }
    // Compile error: same name and parameters, different return type
    String value() { return "one"; }
}
```

Tên phương thức và danh sách tham số phân biệt overload; compiler không chọn overload dựa trên kiểu trả về.

### Covariant return

Kiểu trả về reference của phương thức ghi đè có thể là kiểu con của kiểu trong hợp đồng:

```java
interface NumberSource { Number value(); }
interface IntegerSource { Integer value(); }

final class CountSource implements NumberSource, IntegerSource {
    @Override
    public Integer value() { return 42; }
}
```

Đoạn trên hợp lệ vì `Integer` là kiểu con của `Number`. Nếu hai interface yêu cầu `String value()` và `Integer value()`, không có kiểu trả về nào thỏa mãn đồng thời hai kiểu reference không liên quan. Không thể khai báo hai phương thức để phân biệt bằng return type; cần thiết kế lại API hoặc tách hợp đồng.

Với kiểu nguyên thủy như `int` và `long`, không có covariance. Không thể dùng `int` để override phương thức trả về `long` chỉ vì có chuyển đổi số.

### Generic return type

Khi đọc lỗi API generic, hãy thay tham số kiểu vào khai báo trước khi so sánh. Nếu `Source<T>` có `T value()` và được dùng dưới dạng `Source<String>`, kiểu sau substitution là `String`. Override phải đáp ứng hợp đồng đã thay thế và quy tắc return-type-substitutability.

## 4. Type erasure và name clash

Java generics chủ yếu được triển khai bằng **type erasure**. Tham số kiểu bị xóa hoặc thay bằng bound; `T` không có bound tường minh thường được xóa thành `Object`. Metadata generic có thể còn để reflection đọc, nhưng chữ ký bytecode tuân theo quy tắc erasure.

`List<String>` và `List<Integer>` đều có erasure là `List`. Không thể overload chỉ bằng đối số generic này:

```java
import java.util.List;
class Handler {
    void handle(List<String> values) { }
    // Compile error: same erasure as the method above
    void handle(List<Integer> values) { }
}
```

Compiler không thể phân biệt hai phương thức JVM bằng kiểu `String` hoặc `Integer` bên trong `List`, vì tham số kiểu đó không tạo ra hai chữ ký đã xóa khác nhau.

Name clash cũng có thể xảy ra khi hai khai báo sau erasure có cùng chữ ký nhưng không tạo thành quan hệ override hợp lệ. Một trường hợp liên quan là cố triển khai cùng generic interface hai lần với hai tham số kiểu khác nhau, như `Repository<String>` và `Repository<Integer>`; Java không cho phép lớp kế thừa cùng generic interface theo hai cách không tương thích.

### Cách xử lý

- Đổi tên phương thức nếu hai thao tác khác nhau về ý nghĩa.
- Dùng một phương thức generic như `<T> void handle(List<T> values)` nếu thao tác giống nhau cho mọi `T`.
- Dùng wrapper như `StringBatch` và `IntegerBatch` nếu cần hai overload riêng biệt.
- Sửa hierarchy generic để lớp chỉ kế thừa một cách nhất quán cùng hợp đồng generic.
- Không sửa name clash bằng cách chỉ đổi kiểu trả về hoặc tên biến tham số; chúng không đổi erasure.

## 5. Bridge method do compiler sinh

Khi lớp triển khai phương thức generic bằng kiểu cụ thể, compiler có thể sinh **bridge method** để giữ tính đa hình sau erasure. Bridge thường có cờ `bridge` và `synthetic`; lập trình viên không nên tự viết nó.

Ví dụ `Box<T>` khai báo `put(T value)`, còn `StringBox implements Box<String>` triển khai `put(String value)`. Sau erasure, hợp đồng có dạng `put(Object)`, còn lớp cụ thể có `put(String)`. Compiler sinh bridge `put(Object)` để lời gọi qua `Box` được chuyển tiếp đúng tới phương thức cụ thể.

```java
Box<String> box = new StringBox();
box.put("hello");
```

Khi dùng reflection, `Class.getDeclaredMethods()` có thể trả về cả phương thức source lẫn bridge. Kiểm tra `Method.isBridge()` và `Method.isSynthetic()` để phân biệt chúng. Framework và bộ phân tích bytecode cũng cần lưu ý điều này.

## 6. Ví dụ Java 17 hoàn chỉnh

Chương trình sau minh họa cách giải quyết hai default method, kiểu trả về covariant và bridge method do compiler sinh. Lưu toàn bộ code thành `Main.java`:

```java
import java.lang.reflect.Method;
import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        new Combined().ping();
        System.out.println("covariant value = " + new TextProvider().value());

        Box<String> box = new StringBox();
        box.put("hello");

        boolean hasBridge = Arrays.stream(StringBox.class.getDeclaredMethods())
                .anyMatch(Method::isBridge);
        System.out.println("bridge method generated = " + hasBridge);
    }
}

interface Left {
    default void ping() { System.out.println("Left.ping"); }
}
interface Right {
    default void ping() { System.out.println("Right.ping"); }
}
final class Combined implements Left, Right {
    @Override
    public void ping() {
        Left.super.ping();
        Right.super.ping();
        System.out.println("Combined.ping");
    }
}

interface ValueProvider { Object value(); }
final class TextProvider implements ValueProvider {
    @Override
    public String value() { return "Java 17"; }
}

interface Box<T> { void put(T value); }
final class StringBox implements Box<String> {
    @Override
    public void put(String value) { System.out.println("stored: " + value); }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac --release 17 Main.java
java Main
```

Stdout chính xác:

```text
Left.ping
Right.ping
Combined.ping
covariant value = Java 17
stored: hello
bridge method generated = true
```

Kết quả bridge được tính bằng `Method.isBridge()`, không phụ thuộc thứ tự reflection trả về các method.

## 7. Quy trình chẩn đoán

1. **Đọc lỗi đầu tiên.** Ghi lại lớp, tên phương thức, interface liên quan và cụm từ compiler như `inherits unrelated defaults`, `return type is incompatible`, `name clash` hoặc `same erasure`.
2. **Viết lại chữ ký.** Ghi tên, kiểu tham số sau substitution và erasure. Không dùng return type để phân biệt overload.
3. **Kiểm tra hierarchy.** Xác định phương thức đến từ superclass, interface cụ thể hơn hay hai interface không liên quan.
4. **Kiểm tra return type.** Xem kiểu reference con có thỏa mãn mọi hợp đồng hay không; phân biệt covariance với chuyển đổi primitive.
5. **Tính erasure.** Thay type variables bằng bound tương ứng rồi so sánh chữ ký. Nếu hai phương thức trở thành cùng chữ ký, đổi tên hoặc tái thiết kế API.
6. **Tạo ví dụ tối thiểu.** Giữ lại các interface, superclass và chữ ký gây lỗi; biên dịch riêng bằng `javac --release 17`.
7. **Chạy lại kiểm thử.** Kiểm tra lời gọi qua cả kiểu cụ thể và interface/base type. Với generic override, xác minh đa hình vẫn đúng.

## 8. Bảng tra nhanh

| Dấu hiệu compiler | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `inherits unrelated defaults` | Hai interface không liên quan có cùng default | Override và chọn hành vi; có thể gọi `InterfaceName.super.method()` |
| `return type is incompatible` | Kiểu trả về không thỏa hợp đồng override | Kiểm tra covariance, substitution và thiết kế lại hợp đồng nếu cần |
| Hai phương thức chỉ khác return type | Java không overload theo kiểu trả về | Đổi tên phương thức hoặc thay thiết kế kiểu |
| `name clash` / `same erasure` | Chữ ký generic trùng sau erasure | Đổi tên hoặc thiết kế API generic/wrapper hợp lệ |
| `Method.isBridge() == true` | Compiler sinh bridge để giữ đa hình | Thường không cần sửa; lọc bridge khi phân tích method source |

## 9. Checklist

- Đã đọc khai báo interface và superclass liên quan, không chỉ dòng gọi gây lỗi.
- Đã phân biệt default, abstract và phương thức kế thừa từ lớp cha.
- Đã kiểm tra return type theo quy tắc tương thích, không dựa vào ép kiểu ở nơi gọi.
- Đã tính erasure trước khi thêm overload cho kiểu generic.
- Đã hiểu bridge method là mã compiler sinh và kiểm tra bằng reflection khi cần.
- Đã biên dịch và kiểm thử qua interface/base type sau khi sửa.

Khi chẩn đoán nhóm lỗi này, hãy bắt đầu từ hợp đồng và chữ ký phương thức sau kế thừa, substitution và erasure. Cách đó giúp xác định liệu lỗi nằm ở xung đột ngôn ngữ hay ở thiết kế API.
