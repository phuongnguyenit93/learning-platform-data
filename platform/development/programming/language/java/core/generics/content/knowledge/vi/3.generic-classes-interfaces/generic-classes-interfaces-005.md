# Triển khai giao diện bằng đối số kiểu cụ thể trong Java Generics

Một **giao diện generic** định nghĩa hợp đồng hành vi bằng tham số kiểu, chẳng hạn `Processor<T>`, `Converter<I, O>` hoặc `Repository<E>`. Khi một lớp viết `implements Processor<String>`, lớp ấy chọn **đối số kiểu cụ thể** `String` để thực hiện hợp đồng: các vị trí vốn dùng `T` trong phương thức của giao diện sẽ được hiểu theo `String` ở API kiểu nguồn.

Kỹ thuật này giúp một giao diện có thể phục vụ nhiều kiểu dữ liệu nhưng mỗi lớp triển khai vẫn có chữ ký rõ ràng, được trình biên dịch kiểm tra. Bài học giải thích cú pháp `implements Interface<ConcreteType>`, cách viết `@Override` đúng, trường hợp nhiều tham số kiểu, khác biệt với lớp triển khai vẫn generic và những giới hạn liên quan đến kế thừa, bất biến kiểu và *type erasure*.

## 1. Đọc đúng cú pháp `implements Interface<ConcreteType>`

Giả sử ta muốn một hợp đồng chuyển dữ liệu thành chuỗi:

```java
interface Renderer<T> {
    String render(T value);
}
```

`T` là **tham số kiểu** được khai báo ở giao diện. Bản thân `Renderer<T>` chưa yêu cầu một kiểu dữ liệu cụ thể. Một lớp xử lý chuỗi có thể chọn `String`:

```java
final class UppercaseRenderer implements Renderer<String> {
    @Override
    public String render(String value) {
        return value.toUpperCase();
    }
}
```

Phân tích:

- `implements Renderer<String>`: lớp `UppercaseRenderer` cam kết triển khai giao diện `Renderer` với **đối số kiểu** `String`.
- `String render(String value)`: phương thức ở lớp triển khai khớp hợp đồng sau khi thay tham số kiểu `T` bằng `String`.
- `@Override`: yêu cầu trình biên dịch xác minh phương thức thực sự ghi đè hoặc triển khai phương thức có thể ghi đè của kiểu cha; rất hữu ích khi phát hiện sai chữ ký.
- `UppercaseRenderer` là lớp thông thường, **không phải lớp generic**, vì nó không khai báo `<T>` sau tên lớp. Nó luôn thực hiện `Renderer<String>`, không nhận đối số kiểu mới ở nơi tạo đối tượng.

Điều quan trọng: `implements Renderer<String>` không biến chữ `T` trong định nghĩa giao diện thành một biến toàn cục; nó **ràng buộc vai trò kiểu** trong hợp đồng mà lớp đang thực hiện. Một lớp khác có thể độc lập viết `implements Renderer<Integer>` và cung cấp `render(Integer value)`.

## 2. Chương trình Java 17 hoàn chỉnh: một giao diện, nhiều lớp chuyên biệt

Lưu thành tệp **`ConcreteInterfaceDemo.java`**:

```java
public class ConcreteInterfaceDemo {
    interface Renderer<T> {
        String render(T value);
    }

    static final class UppercaseRenderer implements Renderer<String> {
        @Override
        public String render(String value) {
            return value.toUpperCase();
        }
    }

    static final class IntegerRenderer implements Renderer<Integer> {
        @Override
        public String render(Integer value) {
            return "Số: " + value;
        }
    }

    public static void main(String[] args) {
        Renderer<String> text = new UppercaseRenderer();
        Renderer<Integer> number = new IntegerRenderer();

        System.out.println(text.render("java"));
        System.out.println(number.render(25));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ConcreteInterfaceDemo.java
java ConcreteInterfaceDemo
```

Kết quả chính xác (`stdout`):

```text
JAVA
Số: 25
```

Trong biến `text`, trình biên dịch hiểu `render(...)` nhận `String`; trong biến `number`, phương thức nhận `Integer`. Giá trị `25` kiểu `int` được Java đóng hộp (`autoboxing`) sang `Integer` khi gọi.

Nếu thêm lệnh sau vào `main`:

```java
// text.render(25); // Lỗi biên dịch: Renderer<String> yêu cầu String
```

trình biên dịch sẽ bác bỏ lời gọi. **Không cần dùng `instanceof` hay ép kiểu thủ công** ở nơi gọi vì kiểu của giá trị đầu vào đã được diễn đạt trong giao diện.

Cần phân biệt kiểu của **biến** và kiểu của **đối tượng**:

```java
Renderer<String> renderer = new UppercaseRenderer();
```

Biến có kiểu giao diện `Renderer<String>`; đối tượng thực tế có lớp `UppercaseRenderer`. Người gọi chỉ phụ thuộc vào hợp đồng của giao diện nên có thể thay bằng một lớp triển khai `Renderer<String>` khác mà không phải thay mọi nơi gọi.

## 3. Chữ ký phương thức phải khớp đối số kiểu đã chọn

Trong `Renderer<T>`, phương thức là:

```java
String render(T value);
```

Sau khi một lớp chọn `Renderer<String>`, **chữ ký triển khai phù hợp** là:

```java
@Override
public String render(String value) {
    return value.toUpperCase();
}
```

Đoạn trên là **một phương thức minh họa**, phải nằm trong một lớp `implements Renderer<String>`. Không thể chỉ thay tham số kiểu bằng `Object` rồi coi đó là triển khai tương đương:

```java
// Ví dụ cố ý sai; không dùng làm chương trình chạy:
final class WrongRenderer implements Renderer<String> {
    @Override
    public String render(Object value) {
        return value.toString();
    }
}
```

`render(Object)` không ghi đè phương thức `render(String)` được yêu cầu theo hợp đồng `Renderer<String>`. Vì vậy có lỗi biên dịch: `WrongRenderer` không triển khai phương thức abstract bắt buộc và `@Override` cũng không khớp. Ngay cả nếu bỏ `@Override`, phương thức nhận `Object` vẫn không tự biến thành phương thức đáp ứng `Renderer<String>`.

**Quy tắc thực hành:** mở khai báo interface, thay từng tham số kiểu bằng đối số kiểu được chọn trong `implements`, rồi viết chính xác phương thức cần triển khai. Đối với giao diện có nhiều phương thức, phải thực hiện tất cả các phương thức abstract còn lại hoặc khai báo lớp là `abstract`.

Về phạm vi truy cập, phương thức khai báo trong interface thông thường là `public` theo ngữ nghĩa Java. Do đó khi triển khai phương thức `render`, cần ghi `public`; không thể giảm quyền truy cập xuống `protected` hay package-private.

## 4. Triển khai giao diện có nhiều tham số kiểu

Một giao diện có thể biểu diễn cả kiểu đầu vào và kiểu đầu ra:

```java
interface Converter<I, O> {
    O convert(I input);
}
```

`I` là tham số kiểu đầu vào, `O` là tham số kiểu đầu ra. Lớp triển khai xác định cả hai đối số theo đúng thứ tự:

```java
final class TextLengthConverter implements Converter<String, Integer> {
    @Override
    public Integer convert(String input) {
        return input.length();
    }
}
```

Tham số kiểu `I` tương ứng `String`; `O` tương ứng `Integer`. Vì vậy phương thức nhận `String` và trả `Integer`.

### Ví dụ chạy được

Lưu tệp **`MultiTypeInterfaceDemo.java`**:

```java
public class MultiTypeInterfaceDemo {
    interface Converter<I, O> {
        O convert(I input);
    }

    static final class TextLengthConverter
            implements Converter<String, Integer> {
        @Override
        public Integer convert(String input) {
            return input.length();
        }
    }

    static final class NumberLabelConverter
            implements Converter<Integer, String> {
        @Override
        public String convert(Integer input) {
            return "ID-" + input;
        }
    }

    public static void main(String[] args) {
        Converter<String, Integer> length = new TextLengthConverter();
        Converter<Integer, String> label = new NumberLabelConverter();

        Integer size = length.convert("Generics");
        String code = label.convert(42);

        System.out.println(size);
        System.out.println(code);
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 MultiTypeInterfaceDemo.java
java MultiTypeInterfaceDemo
```

`stdout`:

```text
8
ID-42
```

Hai lớp dùng **cùng một interface** nhưng chọn hai tập đối số kiểu khác nhau. Việc đảo vị trí `<String, Integer>` thành `<Integer, String>` làm thay đổi ý nghĩa và chữ ký bắt buộc, chứ không chỉ thay đổi cách trình bày mã.

| Kiểu giao diện | Kiểu nhận của `convert` | Kiểu trả về của `convert` |
|---|---|---|
| `Converter<String, Integer>` | `String` | `Integer` |
| `Converter<Integer, String>` | `Integer` | `String` |
| `Converter<String, String>` | `String` | `String` |

Lưu ý `int` là kiểu nguyên thủy nên không được dùng trực tiếp làm đối số generic; ta dùng lớp bao `Integer`. Biểu thức `input.length()` trả `int` và được đóng hộp thành `Integer` ở phương thức trả về.

## 5. So sánh lớp triển khai kiểu cụ thể và lớp triển khai vẫn generic

Hai dạng sau có mục đích khác nhau.

**Lớp triển khai cố định kiểu:**

```java
final class StringEcho implements Echo<String> {
    @Override
    public String echo(String value) {
        return value;
    }
}
```

**Lớp triển khai chuyển tiếp tham số kiểu:**

```java
final class GenericEcho<T> implements Echo<T> {
    @Override
    public T echo(T value) {
        return value;
    }
}
```

Cả hai snippet trên giả định có giao diện:

```java
interface Echo<T> {
    T echo(T value);
}
```

`StringEcho` đã chốt `String`; nơi sử dụng viết `new StringEcho()` và **không** thể viết `new StringEcho<Integer>()` vì lớp không khai báo tham số kiểu.

`GenericEcho<T>` vẫn mang tham số kiểu `T`; nơi sử dụng có thể viết `new GenericEcho<String>()` hoặc `new GenericEcho<Integer>()`. Cú pháp `implements Echo<T>` chuyển tiếp quan hệ kiểu từ lớp sang interface.

### Ví dụ so sánh hoàn chỉnh

Lưu tệp **`ConcreteVsGenericDemo.java`**:

```java
public class ConcreteVsGenericDemo {
    interface Echo<T> {
        T echo(T value);
    }

    static final class StringEcho implements Echo<String> {
        @Override
        public String echo(String value) {
            return value.toUpperCase();
        }
    }

    static final class GenericEcho<T> implements Echo<T> {
        @Override
        public T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Echo<String> stringOnly = new StringEcho();
        Echo<String> genericString = new GenericEcho<>();
        Echo<Integer> genericNumber = new GenericEcho<>();

        System.out.println(stringOnly.echo("java"));
        System.out.println(genericString.echo("Java"));
        System.out.println(genericNumber.echo(17));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConcreteVsGenericDemo.java
java ConcreteVsGenericDemo
```

`stdout`:

```text
JAVA
Java
17
```

Nên chọn cách nào?

- Dùng `implements Echo<String>` nếu lớp thực hiện nghiệp vụ riêng cho **một kiểu đã xác định**, ví dụ xử lý chuỗi hoặc thực thể `Customer`.
- Dùng `class GenericEcho<T> implements Echo<T>` nếu thuật toán có thể hoạt động giống nhau với nhiều kiểu và bản thân lớp không cần biết `T` là kiểu nào.
- Có thể kết hợp: `class Child<U> implements Converter<String, U>` chốt kiểu đầu vào là `String` nhưng vẫn cho phép kiểu đầu ra `U` thay đổi. Chỉ dùng khi nghiệp vụ thật sự cần tính linh hoạt ấy.

Đây là quyết định về **mức độ tổng quát của lớp**, không phải về kiểu đối tượng runtime được nhân bản theo từng `T`.

## 6. Interface generic vẫn cho phép nhiều phương thức và phương thức mặc định

Một giao diện không chỉ có một phương thức. Khi khai báo `implements Repository<String>`, mọi vị trí `T` trong hợp đồng cần được hiểu đồng nhất theo `String`.

Ví dụ:

```java
interface Repository<T> {
    void save(T item);
    T latest();

    default String describe(T item) {
        return "Value: " + item;
    }
}
```

Một lớp chọn `String` sẽ phải cài đặt `save(String)` và `String latest()`; `describe(String)` là phương thức `default` đã có thân, nên lớp có thể kế thừa cách cài đặt mà không phải ghi đè. Nếu ghi đè, chữ ký vẫn phải khớp kiểu đã chọn.

Lưu tệp **`RepositoryDemo.java`**:

```java
public class RepositoryDemo {
    interface Repository<T> {
        void save(T item);
        T latest();

        default String describe(T item) {
            return "Value: " + item;
        }
    }

    static final class LastTextRepository implements Repository<String> {
        private String latest;

        @Override
        public void save(String item) {
            latest = item;
        }

        @Override
        public String latest() {
            return latest;
        }
    }

    public static void main(String[] args) {
        Repository<String> repository = new LastTextRepository();
        repository.save("Generics");

        System.out.println(repository.latest());
        System.out.println(repository.describe("Java"));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 RepositoryDemo.java
java RepositoryDemo
```

`stdout`:

```text
Generics
Value: Java
```

Trong ví dụ, `Repository<String>` không tự lưu dữ liệu hoặc tự thêm cơ chế truy cập database. `LastTextRepository` chỉ cất một giá trị trong bộ nhớ để minh họa quan hệ kiểu; tên `Repository` ở đây mô tả hợp đồng học tập, không phải kho lưu trữ bền vững.

Đặc biệt, phần cài đặt phải đảm bảo ý nghĩa phương thức; generics chỉ xác nhận **kiểu** của dữ liệu, không kiểm tra các yêu cầu nghiệp vụ như dữ liệu có tồn tại, có hợp lệ hoặc có cần đồng bộ giữa luồng hay không.

## 7. Ví dụ thực tế: `Comparable<Product>`

Một kiểu sử dụng phổ biến của triển khai interface generic với đối số kiểu cụ thể là `Comparable<T>`. Lớp có thể ghi `implements Comparable<Product>` để mô tả cách so sánh hai đối tượng `Product`.

Lưu tệp **`ProductSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ProductSortDemo {
    record Product(String code, int price) implements Comparable<Product> {
        @Override
        public int compareTo(Product other) {
            int byPrice = Integer.compare(price, other.price());
            return byPrice != 0 ? byPrice : code.compareTo(other.code());
        }
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
            new Product("B", 20),
            new Product("A", 10),
            new Product("C", 20)
        ));

        products.sort(null);

        for (Product product : products) {
            System.out.println(product.code() + ":" + product.price());
        }
    }
}
```

Chạy Java 17+:

```bash
javac -encoding UTF-8 ProductSortDemo.java
java ProductSortDemo
```

`stdout`:

```text
A:10
B:20
C:20
```

Với `Comparable<Product>`, phương thức bắt buộc là `int compareTo(Product other)`. Nếu giá thấp hơn, phương thức trả giá trị âm; cao hơn thì trả dương; bằng giá sẽ so thêm `code` để có thứ tự xác định. `List.sort(null)` dùng thứ tự tự nhiên do `Comparable` của phần tử cung cấp.

Ví dụ `record` ở trên là kiểu dữ liệu Java hỗ trợ từ trước Java 17; cú pháp `record Product(...) implements Comparable<Product>` hoàn toàn hợp lệ. Cần phân biệt `Comparable<T>`: đối tượng tự định nghĩa thứ tự tự nhiên của nó; còn `Comparator<T>` là một giao diện khác để mô tả quy tắc so sánh bên ngoài đối tượng.

Đối số `Product` trong `Comparable<Product>` giúp trình biên dịch ngăn việc truyền sai kiểu đối tượng cho `compareTo` thông qua API được kiểm tra kiểu.

## 8. Kế thừa và nhiều interface: giới hạn cần nhớ

### 8.1. Một lớp có thể triển khai nhiều giao diện generic khác nhau

Ví dụ:

```java
interface Named {
    String name();
}

interface Identifiable<T> {
    T id();
}

final class Account implements Named, Identifiable<Long> {
    @Override
    public String name() {
        return "Primary";
    }

    @Override
    public Long id() {
        return 100L;
    }
}
```

Đây là **nhóm khai báo minh họa**, có thể đặt trong một tệp cùng package. `Account` triển khai `Named` và `Identifiable<Long>`. Interface không có tham số kiểu và interface có tham số kiểu có thể được kết hợp bình thường, miễn các hợp đồng không xung đột.

### 8.2. Không được kế thừa cùng một giao diện generic với hai đối số kiểu khác nhau

Xét:

```java
interface Handler<T> {
    void handle(T value);
}

interface TextHandler extends Handler<String> { }
interface NumberHandler extends Handler<Integer> { }

// Sai:
// final class Both implements TextHandler, NumberHandler { ... }
```

Dù có thể nghĩ rằng chỉ cần viết `handle(String)` và `handle(Integer)`, Java không cho một kiểu cùng kế thừa hai cách tham số hóa khác nhau của **cùng một giao diện generic** như `Handler<String>` và `Handler<Integer>`. Sau *type erasure*, các quan hệ kiểu này còn có vấn đề xung đột; quy tắc ngôn ngữ loại bỏ cách kế thừa ấy ngay khi biên dịch.

Nếu ứng dụng thực sự cần xử lý hai kiểu, có thể khai báo hai phương thức có **tên khác nhau** trong các interface độc lập, hoặc dùng một giao diện nhận một kiểu bao quát hơn với logic phân loại rõ ràng. Không nên bỏ generics rồi dùng raw type để che lỗi thiết kế này.

### 8.3. Một lớp có thể kế thừa lớp cơ sở và triển khai interface

Trong Java, một lớp chỉ `extends` được một lớp cha nhưng có thể `implements` nhiều interface:

```java
abstract class Base {
    String prefix() {
        return "ID:";
    }
}

interface Formatter<T> {
    String format(T value);
}

final class IntegerFormatter extends Base implements Formatter<Integer> {
    @Override
    public String format(Integer value) {
        return prefix() + value;
    }
}
```

Các khai báo trên là **mã minh họa độc lập**. Thứ tự đúng là `extends Base implements Formatter<Integer>`. Giao diện generic vẫn được triển khai bằng một đối số kiểu cụ thể `Integer`.

## 9. Bất biến kiểu (`invariance`) vẫn áp dụng cho giao diện generic

Một lỗi phổ biến là nghĩ rằng vì `String extends Object` nên `Renderer<String>` có thể truyền vào nơi cần `Renderer<Object>`. Trong Java, quan hệ này **không tồn tại mặc định**:

```java
Renderer<String> strings = new UppercaseRenderer();

// Renderer<Object> allObjects = strings; // Sai: không tương thích kiểu
```

`Renderer<String>` và `Renderer<Object>` là hai cách tham số hóa khác nhau của `Renderer`; generic Java mặc định bất biến. Việc cho phép phép gán trên sẽ khiến người gọi có thể đưa vào những `Object` không phải `String`, phá hợp đồng lớp triển khai.

Đối với interface chỉ **tiêu thụ** giá trị kiểu `T` như `Renderer<T>`, wildcard `? super String` có thể hữu ích trong chữ ký API nhận những renderer có thể xử lý `String`; đối với interface chỉ **cung cấp** giá trị kiểu `T`, wildcard `? extends T` thường phù hợp hơn. Đây là hướng mở rộng khi thiết kế API tiêu thụ hoặc sản xuất dữ liệu; chưa cần áp dụng wildcard vào lớp `UppercaseRenderer` để nó triển khai đúng `Renderer<String>`.

## 10. Điều gì xảy ra khi chạy: type erasure và bridge method

Generics Java chủ yếu tạo ra các kiểm tra kiểu **khi biên dịch**. Sau quá trình *type erasure*, JVM không có một bản sao runtime riêng của giao diện cho mỗi đối số như `Renderer<String>` và `Renderer<Integer>`.

Xét ví dụ thu gọn:

```java
interface Source<T> {
    T get();
}

final class StringSource implements Source<String> {
    @Override
    public String get() {
        return "Java";
    }
}
```

Ở mức mã nguồn, `Source<String>.get()` trả về `String`. Sau erasure, chữ ký giao diện về cơ bản trở thành `Object get()`. Để giữ tính đa hình của phương thức đã ghi đè, trình biên dịch Java có thể tạo **bridge method** tổng hợp trong lớp triển khai, thường có chữ ký `Object get()` và chuyển tiếp tới `String get()`.

Bridge method là cơ chế tự động để giữ hành vi override đúng khi erasure làm thay đổi chữ ký JVM, **không phải** phương thức người lập trình phải tự viết. Có thể quan sát bằng cách lưu hai khai báo trên trong `StringSource.java` (không khai báo `public`), rồi chạy:

```bash
javac -encoding UTF-8 StringSource.java
javap -p -c StringSource
```

Kết quả `javap` gồm mã bytecode và các phương thức đã biên dịch; trong trường hợp này sẽ thấy một phương thức `get()` trả `java.lang.String` và phương thức cầu nối `get()` trả `java.lang.Object`. Tùy tùy chọn hiển thị, dùng `javap -v StringSource` để xem cờ `ACC_BRIDGE`, `ACC_SYNTHETIC`.

Từ góc độ sử dụng API, điểm quan trọng vẫn là: khai báo `implements Source<String>` giúp trình biên dịch kiểm tra `String` tại nơi gọi. Tuy nhiên, khi mã cũ dùng raw type hoặc thực hiện ép kiểu không được kiểm tra, vẫn có thể xảy ra `ClassCastException`. Vì thế nên tránh raw type và kiểm tra cảnh báo `unchecked`.

## 11. Các lỗi phổ biến khi `implements` kiểu cụ thể

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `implements Renderer<String>` nhưng viết `render(Object)` | Sai chữ ký cần triển khai: `render(String)`. | Ghi đè `public String render(String value)` và thêm `@Override`. |
| `implements Converter<String, Integer>` nhưng trả `String` | Kiểu trả về không đúng đối số thứ hai `Integer`. | Trả `Integer` hoặc điều chỉnh các đối số kiểu của hợp đồng. |
| Viết `class X implements Renderer<T>` khi lớp không khai báo `T` | `T` không tự tồn tại trong phạm vi lớp. | Dùng `class X<T> implements Renderer<T>` hoặc chốt `Renderer<String>`. |
| Viết `implements Renderer<int>` | Generic chỉ chấp nhận đối số là kiểu tham chiếu. | Dùng `Renderer<Integer>`. |
| Viết `new UppercaseRenderer<String>()` | `UppercaseRenderer` không phải lớp generic. | Dùng `new UppercaseRenderer()`. |
| Để phương thức triển khai có quyền package-private | Không được giảm quyền truy cập của phương thức interface public. | Khai báo phương thức `public`. |
| Nghĩ `Renderer<String>` gán được cho `Renderer<Object>` | Java generics bất biến. | Giữ đúng hợp đồng hoặc thiết kế wildcard ở nơi tiêu thụ nếu thật sự cần. |
| Cùng `implements Handler<String>` và `Handler<Integer>` qua các nhánh kế thừa | Không được kế thừa cùng generic interface với hai đối số kiểu khác nhau. | Thiết kế interface độc lập hoặc thay đổi mô hình xử lý. |
| Bỏ đối số kiểu: `implements Renderer` | Raw type làm mất lợi ích kiểm tra kiểu và có thể sinh cảnh báo. | Chỉ định `Renderer<String>` hay một tham số kiểu khai báo hợp lệ. |
| Cho rằng `implements Interface<String>` giúp runtime kiểm tra toàn bộ tham số generic | Type erasure làm phần lớn thông tin kiểu không còn cho phép kiểm tra `instanceof Interface<String>`. | Giữ an toàn ở compile time, xác thực dữ liệu ở ranh giới không tin cậy. |

Nếu một lớp không ghi đè đủ các phương thức abstract đúng hợp đồng, trình biên dịch yêu cầu lớp phải là `abstract` hoặc bổ sung các phương thức còn thiếu. Không nên vô hiệu hóa cảnh báo, dùng ép kiểu không kiểm tra hoặc bỏ `@Override` để che lỗi.

## 12. Quy trình triển khai một interface generic đúng cách

Khi gặp yêu cầu “viết lớp thực hiện `SomeInterface<ConcreteType>`”, thực hiện lần lượt:

1. **Đọc khai báo giao diện**: xác định số lượng tham số kiểu, thứ tự, các giới hạn như `T extends Number` và danh sách phương thức abstract/default.
2. **Chọn đối số kiểu có ý nghĩa nghiệp vụ**: ví dụ `String`, `Order`, `Integer`, `Converter<Request, Response>`. Phải dùng kiểu tham chiếu và thỏa mọi bound.
3. **Viết `implements` với đầy đủ đối số kiểu**: `class TextHandler implements Handler<String>`.
4. **Thay kiểu trong hợp đồng**: mọi vị trí của `T` ở phương thức được hiểu theo `String`; với `<I,O>` thay theo đúng thứ tự của hai đối số.
5. **Triển khai các phương thức bắt buộc**: ghi `public`, `@Override`, chữ ký đúng và xử lý nghiệp vụ bên trong.
6. **Sử dụng qua kiểu giao diện** ở bên gọi nếu phù hợp: `Handler<String> handler = new TextHandler();`.
7. **Biên dịch và kiểm tra cảnh báo**: `javac -Xlint:rawtypes,unchecked ...`; chú ý lỗi signature, raw type, bound và các đường ép kiểu không an toàn.
8. **Thử cả giá trị hợp lệ và sai kiểu ở biên dịch**: sai kiểu phải bị bác bỏ tại nơi gọi API được ràng buộc kiểu; runtime vẫn cần kiểm soát `null` và các quy tắc nghiệp vụ riêng.

### Bài tập tự kiểm tra

**Câu 1.** Với `interface Mapper<I, O> { O map(I input); }`, phương thức nào phải có trong một lớp `implements Mapper<String, Long>`?

**Câu 2.** Vì sao `class TextMapper implements Mapper<String, Long>` không thể chỉ khai báo `Object map(Object x)`?

**Câu 3.** `class CommonMapper<T> implements Mapper<T, String>` có phải lớp generic không? Nơi sử dụng có thể khai báo `CommonMapper<Integer>` không?

**Câu 4.** Vì sao Java không chấp nhận một lớp vừa là `Handler<String>` vừa là `Handler<Integer>` thông qua hai interface kế thừa?

**Câu 5.** `StringSource` ở phần *type erasure* có phải tự viết `Object get()` để được dùng qua `Source<String>` không?

**Đáp án định hướng:** (1) `public Long map(String input)`. (2) Chữ ký sau khi ràng buộc kiểu yêu cầu tham số `String` và kết quả `Long`; `Object` không đáp ứng hợp đồng đó. (3) Có; `T` vẫn là tham số kiểu của lớp, còn đầu ra đã chốt `String`. (4) Cùng giao diện generic không được kế thừa với hai đối số kiểu khác nhau. (5) Không; trình biên dịch xử lý bridge method cần thiết khi biên dịch.

**Ghi nhớ:** `implements Interface<ConcreteType>` là cách **chuyên biệt hóa hợp đồng của một giao diện generic tại lớp triển khai**. Hãy thay tham số kiểu bằng đối số kiểu đã chọn trong chữ ký phương thức, dùng `public` và `@Override`, sau đó sử dụng đối tượng qua kiểu giao diện được tham số hóa để compiler bảo vệ quan hệ kiểu ngay từ khi viết mã.
