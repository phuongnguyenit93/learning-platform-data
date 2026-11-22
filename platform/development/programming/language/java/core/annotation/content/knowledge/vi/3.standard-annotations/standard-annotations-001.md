# @Override trong Java: kiểm tra ghi đè và thực thi phương thức giao diện

## 1. @Override là gì?

`@Override` là annotation chuẩn thuộc gói `java.lang`, được viết ngay trước khai báo một **phương thức**. Khi dùng nó, lập trình viên yêu cầu `javac` kiểm tra rằng phương thức này thật sự **ghi đè (override)** phương thức phù hợp ở kiểu cha hoặc **hiện thực** một phương thức được khai báo trong interface theo quy tắc ngôn ngữ Java.

Ví dụ, bạn định ghi đè `send(String)` nhưng vô tình viết thành `send(Object)`. Nếu thiếu `@Override`, đây có thể chỉ là một overload mới: chương trình biên dịch được nhưng hành vi không như bạn nghĩ. Có `@Override`, lỗi bị phát hiện ngay lúc biên dịch.

Annotation này có `@Target(ElementType.METHOD)` và `@Retention(RetentionPolicy.SOURCE)`:

- **Được kiểm tra khi biên dịch:** nếu không có quan hệ override/implement hợp lệ, compiler báo lỗi.
- **Diễn đạt chủ ý:** người đọc nhận ra phương thức tuân theo hợp đồng từ kiểu cha hoặc interface.
- **Không tạo ra cơ chế đa hình:** dynamic dispatch vốn là quy tắc đối với các phương thức instance có thể ghi đè trong Java; thêm hay bỏ annotation không làm thay đổi phương thức nào được gọi lúc chạy.
- **Không phải bắt buộc trong mọi override:** Java cho phép override hợp lệ khi không gắn annotation, nhưng sử dụng `@Override` là thực hành tốt vì giúp kiểm tra sớm.

## 2. Ba tình huống thường gặp

### Ghi đè phương thức instance của superclass

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

`Cat.sound()` thay thế cách triển khai `Animal.sound()`. Nếu `Animal a = new Cat();`, biểu thức `a.sound()` trả về `"meow"` nhờ dynamic dispatch theo đối tượng thực tế.

### Hiện thực phương thức abstract từ interface

```java
interface PaymentMethod {
    String pay(int amount);
}

class CardPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "Paid " + amount + " by card";
    }
}
```

Mặc dù interface chỉ khai báo hợp đồng, `@Override` vẫn hợp lệ ở phương thức hiện thực của `CardPayment`. Phương thức interface thông thường là `public`, nên phương thức hiện thực phải là `public`. Đây là cách phổ biến để bắt compiler kiểm tra các class triển khai interface.

### Ghi đè default method của interface

Một interface có thể khai báo phương thức `default` mang sẵn phần thân. Class triển khai có thể ghi đè nó bằng `@Override`. Nếu nhiều interface đem tới default method xung đột cùng chữ ký, class phải giải quyết xung đột theo quy tắc Java; việc gắn `@Override` vào bản hiện thực cũng giúp làm rõ ý định.

Bạn còn có thể dùng annotation này khi ghi đè các phương thức hợp lệ của `Object`, như `toString()`, `equals(Object)` và `hashCode()`. Với `equals`, viết `equals(MyClass)` chỉ tạo overload, không ghi đè `equals(Object)`.

## 3. Ví dụ hoàn chỉnh Java 17+: interface, superclass và đa hình

Lưu **toàn bộ** chương trình sau vào tệp `OverrideDemo.java`:

```java
import java.util.Locale;

interface MessageFormatter {
    String format(String text);

    default String kind() {
        return "default";
    }
}

class UppercaseFormatter implements MessageFormatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    @Override
    public String kind() {
        return "uppercase";
    }
}

class BracketFormatter extends UppercaseFormatter {
    @Override
    public String format(String text) {
        return "[" + super.format(text) + "]";
    }
}

public class OverrideDemo {
    public static void main(String[] args) {
        MessageFormatter formatter = new BracketFormatter();

        System.out.println(formatter.format("java"));
        System.out.println(formatter.kind());
        System.out.println(new UppercaseFormatter().format("core"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 OverrideDemo.java
java OverrideDemo
```

Stdout chính xác:

```text
[JAVA]
uppercase
CORE
```

Phân tích:

1. `MessageFormatter` khai báo phương thức `format(String)` và định nghĩa sẵn `kind()` dạng `default`.
2. `UppercaseFormatter.format` **thực thi phương thức interface**; `UppercaseFormatter.kind` **ghi đè default method**.
3. `BracketFormatter.format` **ghi đè phương thức superclass**; lời gọi `super.format(text)` dùng lại bước viết hoa, sau đó thêm ngoặc.
4. Biến `formatter` có **kiểu tham chiếu** `MessageFormatter`, nhưng đối tượng thực tế là `BracketFormatter`. Gọi `format("java")` sẽ chạy `BracketFormatter.format`; gọi `kind()` chạy bản kế thừa từ `UppercaseFormatter`.

Bạn có thể xóa riêng các dòng `@Override` rồi biên dịch lại: stdout vẫn như trên. Điều này chứng minh annotation kiểm tra hợp đồng ở compile time, còn cơ chế đa hình là một quy tắc của Java runtime.

## 4. Quy tắc để override hợp lệ

| Yếu tố | Quy tắc |
| --- | --- |
| Tên và tham số | Phải có chữ ký override-compatible với phương thức cha. Tên giống nhưng kiểu hoặc số lượng tham số khác thường tạo **overload**. Generic có thêm quy tắc subsignature/erasure. |
| Return type | Kiểu trả về phải tương thích: cùng kiểu hoặc kiểu con thích hợp với kiểu tham chiếu (**covariant return**). Không được tùy ý đổi từ `int` sang `long`. |
| Access modifier | Không được giảm visibility. Ví dụ, override phương thức `public` phải tiếp tục là `public`. |
| Checked exceptions | Không được khai báo checked exception mới hoặc rộng hơn hợp đồng của phương thức cha; có thể bỏ hoặc thu hẹp chúng. Unchecked exceptions không bị hạn chế tương tự. |
| Instance / static | Instance method có thể override nếu thỏa điều kiện; `static` method thuộc cơ chế **hiding**, không phải overriding. |
| Kế thừa | Không được override `final` instance method. Phương thức `private` không được kế thừa để override; constructor cũng không phải phương thức được override. |

Ví dụ về **covariant return** (đây là đoạn định nghĩa class có thể ghép vào một tệp Java, không phải một chương trình có `main` riêng):

```java
class Counter {
    Number getValue() {
        return 1;
    }
}

class FixedCounter extends Counter {
    @Override
    Integer getValue() {
        return 42;
    }
}
```

`Integer` là subtype của `Number`, nên `FixedCounter.getValue()` override hợp lệ. Nếu sửa return type thành `String`, compiler sẽ từ chối.

## 5. Các lỗi @Override thường phát hiện

### 5.1. Nhầm override và overload

Ví dụ **cố ý sai**, không biên dịch thành công:

```java
class Printer {
    void print(String message) {}
}

class FancyPrinter extends Printer {
    @Override
    void print(Object message) {}
}
```

`print(Object)` không override `print(String)`. `javac` báo lỗi dạng `method does not override or implement a method from a supertype`. Nếu mục tiêu là ghi đè, sửa thành `print(String message)`; nếu chủ ý bổ sung overload, bỏ `@Override`.

Một bẫy tương tự là `equals(MyType)`: chỉ `equals(Object)` với kiểu trả về `boolean` mới override phương thức của `Object`.

### 5.2. Quên public khi implements interface

Đoạn sau **cố ý sai**:

```java
interface Greeter {
    void greet();
}

class BadGreeter implements Greeter {
    @Override
    void greet() {}
}
```

`Greeter.greet()` là `public`, còn `BadGreeter.greet()` chỉ có quyền package-private. Java không cho phép giảm visibility. Sửa thành `@Override public void greet() {}`.

### 5.3. Nhầm static hiding với override

Đoạn sau **cố ý sai**:

```java
class BaseTool {
    static void reset() {}
}

class Tool extends BaseTool {
    @Override
    static void reset() {}
}
```

Hai `static` method cùng tên thuộc cơ chế **method hiding**. `@Override` trên `Tool.reset()` không hợp lệ. Khi gọi static method, lựa chọn phương thức gắn với kiểu được dùng trong biểu thức theo quy tắc Java, khác với dynamic dispatch của instance method.

### 5.4. final, private và constructor

- Không thể override instance method có modifier `final`; bản thân khai báo override đã gây lỗi.
- `private` method ở lớp cha không được kế thừa để override. Một method trùng tên trong lớp con không trở thành override của private method đó.
- Constructor không phải method được kế thừa nên không gắn `@Override`.
- `@Override` cũng không biến field hiding thành method overriding.
- Chữ ký có thể trùng mà vẫn lỗi nếu return type không tương thích, giảm visibility hoặc mở rộng checked exception.

## 6. @Override với generic và interface kế thừa

Ví dụ dưới đây là những khai báo hợp lệ, có thể đặt cùng một tệp Java:

```java
interface Converter<T> {
    T convert(T value);
}

final class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
```

Khi class chọn `T = String`, hợp đồng được hiện thực bằng `convert(String)`. `@Override` kiểm tra quan hệ này theo quy tắc generic của Java. Sau **type erasure**, compiler có thể sinh **bridge method** trong bytecode để duy trì tính đa hình; bridge method là chi tiết compiler, bạn không tự khai báo `@Override` trên nó.

Interface có thể kế thừa interface khác. Một class hiện thực interface con vẫn phải đáp ứng các phương thức abstract kế thừa chưa được thực thi, trừ khi class được khai báo `abstract` hoặc kế thừa một implementation hợp lệ. `@Override` đánh dấu phương thức mà class thực sự cung cấp; không cần thêm một phương thức chỉ để gắn annotation nếu đã kế thừa sẵn implementation phù hợp.

## 7. Điều @Override không đảm bảo

`@Override` không bắt buộc class con override một method đã có implementation (khác với trách nhiệm hiện thực abstract method của class concrete); không kiểm chứng nghiệp vụ; không tự sinh code; không thay thế kiểm thử. Ví dụ, `equals(Object)` có chữ ký chính xác vẫn có thể viết sai quy tắc đối xứng hoặc không nhất quán với `hashCode()`.

Annotation cũng không can thiệp vào **overload resolution**: Java chọn overload phù hợp dựa trên kiểu biểu thức và tham số ở compile time; dynamic dispatch sau đó chọn implementation override của chữ ký đã chọn theo kiểu đối tượng lúc chạy.

## 8. Cách sử dụng trong thực tế

1. Bắt đầu từ hợp đồng của superclass/interface: xác định chữ ký, return type, visibility và checked exceptions.
2. Viết đúng phương thức cần hiện thực hoặc thay thế, gắn `@Override` ngay trên khai báo.
3. Chạy `javac` hoặc build của dự án: nếu interface/superclass đổi chữ ký, coi lỗi biên dịch là tín hiệu cần cập nhật implementation.
4. Test hành vi qua biến kiểu cha/interface để xác nhận dispatch đúng; chú ý các nhánh `super`, `default` method và generic.
5. Nếu nhận lỗi `@Override`, so sánh hợp đồng thật; đừng chỉ xóa annotation để khiến build xanh, vì như vậy có thể che mất một overload vô tình.

**Điểm cần nhớ:** `@Override` là một cách thể hiện chủ ý có kiểm tra tại compile time. Nó giúp tránh nhầm chữ ký khi ghi đè superclass hoặc hiện thực interface; chính quy tắc phương thức của Java mới quyết định việc override và dispatch thực tế.
