# Giới hạn tạo đối tượng bằng new T()

## 1. Vì sao new T() không hợp lệ?

Trong Java, một tham số kiểu như `T` mô tả quan hệ kiểu của dữ liệu; nó không phải tên một lớp cụ thể để trình biên dịch chọn hàm tạo.

Ví dụ sau không biên dịch:

```java
// Ví dụ cố ý không biên dịch.
class Maker<T> {
    T create() {
        return new T(); // Không hợp lệ.
    }
}
```

Đoạn trên cố ý giữ nguyên lỗi để chỉ rõ biểu thức bị cấm; đây không phải chương trình chạy độc lập.

Khi gặp `new SomeClass(...)`, Java cần xác định:

- Lớp cụ thể cần tạo có thể được khởi tạo hay không.
- Hàm tạo nào phù hợp với các đối số.
- Hàm tạo đó có được phép truy cập từ nơi gọi hay không.
- Những ngoại lệ nào cần được xử lý.

Một `T` tổng quát không cung cấp đủ các cam kết đó. Nó có thể là một lớp cần tham số khởi tạo, một lớp trừu tượng hoặc một interface.

Xóa kiểu (type erasure) là bối cảnh quan trọng: Java không tự tạo một bản mã riêng cho từng `T` với hàm tạo tương ứng. Nhưng đừng chỉ ghi nhớ “vì T thành Object”. **Vấn đề còn là hợp đồng generics không có ràng buộc hàm tạo kiểu `new()`.**

Cách giải quyết là truyền thêm **hành vi tạo đối tượng** hoặc **thông tin lớp và hàm tạo thực thi** một cách tường minh.

Các giải pháp trong bài dùng API hiện hành trên Java 17+. Không cần dùng raw type hoặc API reflection đã bị khuyến cáo ngừng sử dụng.

## 2. Cận kiểu không cam kết có hàm tạo không tham số

Một suy luận thường gặp là:

```java
class Maker<T extends Object> {
    // T create() { return new T(); } // Vẫn không hợp lệ.
}
```

`extends Object` không có nghĩa mọi lớp cụ thể thay cho `T` đều có hàm tạo không tham số truy cập được.

Ngay cả cận là một lớp do ta kiểm soát cũng không giải quyết điều đó:

```java
abstract class Shape {
    public Shape() {
    }
}

final class Circle extends Shape {
    Circle(double radius) {
    }
}
```

`Circle` là một kiểu phù hợp với `T extends Shape`, nhưng không có hàm tạo `Circle()`. Hàm tạo không được kế thừa từ lớp cha. Bản thân `Shape` còn là lớp trừu tượng.

Vì vậy:

```java
// <T extends Shape> T createShape() { return new T(); }
// Không biên dịch dù Shape có constructor public không tham số.
```

Cận `extends` cho phép sử dụng những thành viên thích hợp của kiểu cận trên giá trị `T`; nó không đặt ra một giao diện hàm tạo cho mọi kiểu con.

Thêm các cận interface cũng không tạo ra cam kết hàm tạo. Java không có cú pháp `<T extends Shape & new()>`.

## 3. Giải pháp thường dùng: truyền một Supplier

Nếu thuật toán cần “hãy cung cấp cho tôi một giá trị dùng được như `T`”, có thể nhận `Supplier<? extends T>`:

```java
static <T> T create(Supplier<? extends T> factory) {
    Objects.requireNonNull(factory, "factory");
    return Objects.requireNonNull(factory.get(), "created value");
}
```

Đoạn này giả định đã import `java.util.Objects` và `java.util.function.Supplier`.

Nơi gọi chọn cách tạo đối tượng:

```java
StringBuilder buffer = create(StringBuilder::new);
List<String> names = create(ArrayList<String>::new);
```

`StringBuilder::new` là tham chiếu hàm tạo (constructor reference). Trình biên dịch kiểm tra hàm tạo thật tại nơi viết tham chiếu; phương thức `create` chỉ cần biết cách gọi `get()`.

`? extends T` diễn tả factory cung cấp kết quả là `T` hoặc một kiểu con. Ta không truyền giá trị `T` vào factory, nên cận trên phù hợp với vai trò nguồn cung cấp.

Trong phiên bản này, `Objects.requireNonNull` là một quyết định hợp đồng: không nhận factory `null` và không chấp nhận kết quả `null`. Nếu bài toán cho phép kết quả `null`, có thể thiết kế hợp đồng khác; bản thân `Supplier` không tự cấm điều đó.

### 3.1. Khởi tạo cần cấu hình: dùng lambda

Một factory không bắt buộc phải gọi hàm tạo không tham số:

```java
Ticket ticket = create(() -> new Ticket("priority"));
```

Ở đây `Ticket` là lớp có hàm tạo nhận `String`, được định nghĩa trong ví dụ hoàn chỉnh bên dưới. Lambda giữ thông tin khởi tạo mà thuật toán tổng quát không cần biết.

Mẫu này giúp tách hai trách nhiệm:

```text
Nơi gọi: biết lớp cụ thể và cách tạo đúng
        ↓ truyền factory
Thuật toán tổng quát: biết lúc nào cần một giá trị T
```

Factory cũng có thể gọi một phương thức tạo đối tượng có tên, lấy đối tượng từ một thành phần khác, hoặc áp dụng logic khởi tạo riêng. Generics giữ quan hệ kiểu giữa kết quả factory và nơi sử dụng.

### 3.2. Dữ liệu thay đổi theo từng lần gọi: truyền Function

Nếu thuật toán cần truyền một đối số đầu vào cho thao tác tạo, có thể dùng `Function<A, T>` thay cho `Supplier<T>`:

```java
Function<String, Ticket> byLabel = Ticket::new;
Ticket ticket = byLabel.apply("custom");
```

Cần import `java.util.function.Function`.

Một `Supplier` không có tham số của `get()`; một `Function` nhận một tham số của `apply`. Hãy chọn theo thông tin mà thuật toán thực sự cần cung cấp, thay vì ép mọi quy trình tạo đối tượng vào một hàm không tham số.

Nếu hàm tạo ném ngoại lệ được kiểm tra (checked exception), tham chiếu hàm tạo phải phù hợp với kiểu hàm được chọn. `Supplier.get()` không khai báo ngoại lệ được kiểm tra; khi cần giữ hợp đồng ngoại lệ đó, hãy thiết kế một interface hàm có `throws` phù hợp hoặc xử lý ngoại lệ ở một nơi có đủ ngữ cảnh.

## 4. Supplier không tự bảo đảm đối tượng mới

Tên biến `factory` không thay đổi hợp đồng của `Supplier`. Một supplier có thể trả lại cùng một đối tượng qua nhiều lần gọi:

```java
StringBuilder shared = new StringBuilder();
Supplier<StringBuilder> reuse = () -> shared;

StringBuilder first = reuse.get();
StringBuilder second = reuse.get();

System.out.println(first == second); // true
```

Ngược lại:

```java
Supplier<StringBuilder> fresh = StringBuilder::new;

StringBuilder first = fresh.get();
StringBuilder second = fresh.get();

System.out.println(first == second); // false
```

Đây là hai đoạn minh họa độc lập.

Nếu thuật toán cần các phần tử có trạng thái độc lập, phải yêu cầu rõ factory trả đối tượng mới hoặc có cơ chế bảo đảm tương đương. Chỉ dùng `Supplier<T>` không thể chứng minh tính độc lập đó bằng hệ thống kiểu.

Một lỗi thực tế là tạo danh sách các bộ đệm nhưng mọi vị trí cùng trỏ vào một `StringBuilder`. Khi sửa phần tử đầu, các vị trí khác cũng phản ánh cùng thay đổi. Hãy phân biệt “gọi supplier nhiều lần” với “tạo đối tượng khác nhau nhiều lần”.

## 5. Khi cần thông tin lớp lúc chạy: truyền Class<T>

Một số hạ tầng phải chọn lớp theo cấu hình hoặc metadata và tìm hàm tạo lúc chạy. Khi đó có thể nhận một đối tượng `Class<T>`:

```java
static <T> T createFromClass(Class<T> type)
        throws ReflectiveOperationException {
    return type.getConstructor().newInstance();
}
```

Lời gọi:

```java
Ticket ticket = createFromClass(Ticket.class);
```

Ở đây `Ticket.class` cung cấp thông tin lớp thực thi thật. Đây là một đối số riêng do nơi gọi truyền vào; Java không tự biến biến kiểu `T` thành đối tượng lớp đó.

Hai bước có ý nghĩa khác nhau:

1. `getConstructor()` tìm hàm tạo **public không tham số**.
2. `newInstance()` trên đối tượng `Constructor` gọi hàm tạo vừa tìm được.

Đây không phải lời cam kết rằng mọi `Class<T>` đều tạo được `T`. Kiểm tra hàm tạo diễn ra lúc chạy.

| Tình huống | Kết quả thường gặp của đường gọi này |
| --- | --- |
| Không có hàm tạo public không tham số | `NoSuchMethodException` |
| Lớp là abstract nhưng tìm được hàm tạo | `InstantiationException` khi khởi tạo |
| Quyền truy cập không cho phép gọi | `IllegalAccessException` |
| Thân hàm tạo ném ngoại lệ | `InvocationTargetException`, nguyên nhân nằm trong `getCause()` |

Khởi tạo lớp cũng có thể làm phát sinh các lỗi khác, chẳng hạn lỗi từ quá trình khởi tạo static. Bảng tập trung vào các tình huống reflection thường cần xử lý, không phải danh sách mọi lỗi có thể xảy ra.

`getDeclaredConstructor()` có thể tìm hàm tạo được khai báo trong lớp với các mức truy cập khác nhau, nhưng việc tìm thấy không tự cấp quyền gọi. Không nên coi việc vô hiệu hóa kiểm tra truy cập là giải pháp mặc định; cần thiết kế API và ranh giới module phù hợp.

### 5.1. Class<T> không phải T.class

Trong một phương thức tổng quát, không thể viết:

```java
// Class<T> type = T.class; // Không biên dịch.
```

Phải nhận `Class<T>` từ nơi biết lớp cụ thể, ví dụ `Ticket.class`.

Cũng không có `List<String>.class`. Đối tượng lớp không biểu diễn đầy đủ mọi đối số kiểu của một kiểu có tham số. Nếu bài toán cần mô tả kiểu phức tạp như `List<String>`, một `Class<T>` đơn giản chưa đủ; không nên dùng cast để giả vờ rằng nó có thông tin đó.

### 5.2. Cần tham số hàm tạo thì phải chọn đúng chữ ký

Ví dụ hiện hành:

```java
Ticket ticket = Ticket.class
        .getConstructor(String.class)
        .newInstance("configured");
```

Không có bước tự động tìm một hàm tạo “gần đúng” theo mọi quy tắc nạp chồng như một lời gọi `new` trong mã nguồn. Khi tìm hàm tạo bằng `getConstructor`, cần cung cấp đúng các lớp tham số khai báo; `int.class` và `Integer.class` không phải cùng một chữ ký.

Khi lớp cụ thể và cách tạo đã biết ở thời điểm biên dịch, constructor reference hoặc lambda thường diễn đạt hợp đồng rõ hơn và được kiểm tra sớm hơn reflection.

## 6. Chương trình hoàn chỉnh

Lưu thành `GenericCreationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class GenericCreationDemo {
    public static final class Ticket {
        private final String label;

        public Ticket() {
            this("default");
        }

        public Ticket(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }

        public String label() {
            return label;
        }
    }

    static <T> T create(Supplier<? extends T> factory) {
        Objects.requireNonNull(factory, "factory");
        return Objects.requireNonNull(factory.get(), "created value");
    }

    static <T> List<T> repeat(int count, Supplier<? extends T> factory) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be non-negative");
        }
        Objects.requireNonNull(factory, "factory");

        List<T> result = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            result.add(create(factory));
        }
        return result;
    }

    static <T> T createFromClass(Class<T> type)
            throws ReflectiveOperationException {
        return type.getConstructor().newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        List<StringBuilder> buffers = repeat(2, StringBuilder::new);
        buffers.get(0).append("first");

        Ticket byFactory = create(() -> new Ticket("priority"));
        Function<String, Ticket> byLabel = Ticket::new;
        Ticket byFunction = byLabel.apply("custom");
        Ticket byReflection = createFromClass(Ticket.class);

        System.out.println("first buffer = " + buffers.get(0));
        System.out.println("second empty = "
                + (buffers.get(1).length() == 0));
        System.out.println("distinct buffers = "
                + (buffers.get(0) != buffers.get(1)));
        System.out.println("factory = " + byFactory.label());
        System.out.println("function = " + byFunction.label());
        System.out.println("reflection = " + byReflection.label());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all GenericCreationDemo.java
java GenericCreationDemo
```

Stdout chính xác:

```text
first buffer = first
second empty = true
distinct buffers = true
factory = priority
function = custom
reflection = default
```

`repeat` không biết hàm tạo của `StringBuilder`; nó biết cách gọi factory. Các bộ đệm độc lập trong lần chạy này vì `StringBuilder::new` thực sự tạo đối tượng mới mỗi lần.

Với `Ticket`, lambda giữ cấu hình cố định, `Function` nhận cấu hình từ đối số mỗi lần gọi, còn reflection tìm một hàm tạo public không tham số dựa trên `Ticket.class`. Ba cách cung cấp ba hợp đồng khởi tạo khác nhau, không làm `new T()` trở thành hợp lệ.

## 7. Những cách sửa sai cần tránh

### 7.1. Tạo Object rồi ép sang T

Việc viết một cast như `(T) new Object()` không tạo ra một đối tượng có lớp cụ thể mà nơi gọi mong muốn. Nó chỉ cố vượt qua kiểm tra kiểu, thường kéo theo cảnh báo chuyển kiểu không được kiểm tra và lỗi khi giá trị được dùng như kiểu cụ thể.

Nếu nơi gọi cần `Ticket`, hãy truyền một thao tác tạo `Ticket`; đừng dùng một `Object` làm giá trị thay thế giả.

### 7.2. Dùng lớp của một đối tượng mẫu để sao chép

`sample.getClass()` cho biết lớp thực tế của mẫu, nhưng không bảo đảm lớp đó có hàm tạo phù hợp. Nó cũng không tự cung cấp dữ liệu cần thiết để tạo một bản sao có cùng trạng thái.

Nếu cần sao chép, hãy dùng hợp đồng sao chép rõ ràng, chẳng hạn một hàm `Function<T, T>`, hàm tạo sao chép của lớp cụ thể hoặc phương thức sao chép có tên. Tạo đối tượng mới và sao chép trạng thái là hai yêu cầu khác nhau.

### 7.3. Thêm cận chỉ để “ép có constructor”

`T extends Runnable` hay `T extends SomeBase` ràng buộc quan hệ kiểu. Nó không buộc mọi kiểu phù hợp cung cấp một hàm tạo nhất định, cũng không biến interface hay lớp trừu tượng thành đối tượng có thể tạo trực tiếp.

### 7.4. Đổi tất cả sang reflection khi không cần

Reflection hữu ích khi lớp chỉ được biết lúc chạy. Nếu nơi gọi đã biết `Ticket::new` hoặc một lambda tạo đúng đối tượng, truyền factory thường giảm việc kiểm tra lúc chạy và tránh buộc API tổng quát phụ thuộc vào cấu trúc hàm tạo.

Nếu thuật toán chỉ cần dùng một đối tượng đã có, thậm chí không cần factory: nhận trực tiếp giá trị `T`. Đừng thêm trách nhiệm tạo mới khi bài toán không yêu cầu.

## 8. Chọn hợp đồng theo nhu cầu

| Nhu cầu thật | Hợp đồng phù hợp |
| --- | --- |
| Dùng một đối tượng đã tồn tại | Nhận trực tiếp `T` |
| Yêu cầu một kết quả không có đối số đầu vào | `Supplier<? extends T>` |
| Tạo kết quả từ một đầu vào kiểu `A` | `Function<? super A, ? extends T>` |
| Tạo bằng quy trình riêng hoặc có ngoại lệ được kiểm tra | Interface factory có hợp đồng rõ ràng |
| Tìm và gọi hàm tạo từ thông tin lớp lúc chạy | `Class<T>` kết hợp `Constructor<T>` |

Trước khi chọn, hãy trả lời ba câu: ai biết cách tạo đối tượng, thông tin khởi tạo đến từ đâu, và mỗi lần yêu cầu có cần một đối tượng mới độc lập hay không. Những câu trả lời đó quyết định chữ ký API tốt hơn việc tìm một mẹo thay thế `new T()`.

## Tài liệu đối chiếu

- [JLS §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9): xác định lớp và hàm tạo của biểu thức `new`.
- [Java Supplier API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Supplier.html): hợp đồng cung cấp kết quả, không tự bảo đảm kết quả mới mỗi lần.
- [Java Class API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html) và [Constructor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html): tìm hàm tạo và khởi tạo đối tượng bằng reflection.
