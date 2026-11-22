# Thiết kế lớp lưu giữ giá trị `Box<T>` trong Java Generics

Một nhu cầu đơn giản khi thiết kế API là **lưu một giá trị và lấy lại giá trị ấy với đúng kiểu đã khai báo**. Ta có thể viết riêng `StringBox`, `IntegerBox`, `CustomerBox` cho từng kiểu, nhưng các lớp sẽ lặp lại cùng cấu trúc. Ta cũng có thể dùng một trường `Object`, song người gọi thường phải ép kiểu thủ công và có nguy cơ gặp `ClassCastException`.

Java Generics cho phép định nghĩa **một lớp `Box<T>`**: `T` là *tham số kiểu* đại diện cho kiểu giá trị mà hộp lưu giữ. Khi sử dụng `Box<String>`, `Box<Integer>` hoặc `Box<Customer>`, trình biên dịch kiểm tra dữ liệu theo kiểu được chỉ định. Bài học này tập trung vào cách thiết kế lớp, constructor, trường, phương thức và hợp đồng sử dụng của `Box<T>`, cùng các quyết định thực tế như có cho phép `null` hay cho phép thay giá trị hay không.

## 1. Xác định hợp đồng của `Box<T>`

Một `Box<T>` tối thiểu cần trả lời các câu hỏi:

1. **Hộp lưu gì?** Một giá trị kiểu `T`.
2. **Giá trị được đưa vào bằng cách nào?** Qua constructor hoặc phương thức tạo (`factory method`).
3. **Lấy giá trị ra thế nào?** Phương thức `T get()` để người gọi nhận đúng kiểu đã khai báo.
4. **Có thay đổi giá trị sau khởi tạo không?** Ví dụ chính dùng trường `final` và không có setter, tức tham chiếu đến giá trị được cố định sau constructor.
5. **Có nhận `null` không?** Ví dụ chính **không nhận `null`**, nhằm giữ hợp đồng dễ hiểu. Đây là một quyết định thiết kế cụ thể, không phải yêu cầu của generics.

Đối với phiên bản đơn giản, API sẽ có dạng:

```java
public final class Box<T> {
    private final T value;

    public Box(T value) { /* lưu value */ }

    public T get() { /* trả về value */ }
}
```

Đây chỉ là **phác thảo chữ ký**. Phần tiếp theo là mã Java hoàn chỉnh. `T` không phải tên một lớp cụ thể và cũng không phải biến lưu dữ liệu. Nó là tham số kiểu được khai báo ở `<T>`; trong mỗi cách sử dụng như `Box<String>`, trình biên dịch diễn giải `T` theo đối số kiểu tương ứng.

## 2. Cài đặt hoàn chỉnh `Box<T>`

Tạo tệp **`Box.java`**:

```java
import java.util.Objects;

public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public T get() {
        return value;
    }

    public static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

### Giải thích từng thành phần

**`public final class Box<T>`:** `<T>` khai báo tham số kiểu trong phạm vi lớp; `final` ngăn lớp con kế thừa, giúp giữ thiết kế hộp đơn giản và cố định. Một lớp generic không bắt buộc phải `final`; đây là lựa chọn của ví dụ.

**`private final T value`:** trường có kiểu `T`, được che giấu khỏi mã bên ngoài bằng `private`. `final` bảo đảm tham chiếu này được gán trong quá trình khởi tạo và không được gán lại sau đó. `final` **không** tự khiến đối tượng mà trường trỏ tới trở nên bất biến.

**`public Box(T value)`:** constructor nhận đúng kiểu `T` mà nơi sử dụng lớp đã chỉ định. Ví dụ với `Box<String>`, truyền một `Integer` vào constructor sẽ không tương thích với hợp đồng đó.

**`Objects.requireNonNull(value, "value")`:** từ chối `null` tại nơi khởi tạo, ném `NullPointerException` với thông báo `value`. Quyết định này tránh việc một hộp hợp lệ theo API nhưng không có giá trị. Nếu bài toán cần biểu diễn “có thể không có giá trị”, nên thiết kế và ghi rõ hợp đồng khác, chẳng hạn một lớp cho phép `null` hoặc dùng `Optional<T>` khi phù hợp.

**`public T get()`:** trả về giá trị với kiểu `T` trên giao diện nguồn Java. Với `Box<String>`, người gọi dùng `get()` như một biểu thức `String` mà không cần ép kiểu tường minh.

**`public static <U> Box<U> of(U value)`:** đây là phương thức tạo tiện dụng và **bản thân nó là phương thức generic**. Phương thức `static` không thể sử dụng trực tiếp tham số kiểu `T` của lớp, nên nó khai báo riêng `<U>`. Lời gọi `Box.of("Java")` cho phép trình biên dịch suy luận `U` là `String` trong ngữ cảnh thích hợp.

Thiết kế có cả constructor lẫn factory để minh họa hai cách khởi tạo hợp lệ. Dự án thực tế có thể chọn một cách làm API chính, tùy nhu cầu.

## 3. Sử dụng `Box<T>` với các kiểu dữ liệu khác nhau

Tạo tệp **`BoxDemo.java`** cạnh `Box.java`:

```java
import java.util.List;

public class BoxDemo {
    public static void main(String[] args) {
        Box<String> language = new Box<>("Java");
        Box<Integer> count = Box.of(7);
        Box<List<String>> topics = Box.of(List.of("core", "generics"));
        Box<Double> ratio = Box.of(3.14);

        System.out.println(language.get().toUpperCase());
        System.out.println(count.get() + 5);
        System.out.println(String.join(" | ", topics.get()));
        System.out.println("Box contains: " + ratio.get());
    }
}
```

Chạy bằng **Java 17 trở lên** trong thư mục chứa hai tệp:

```bash
javac -encoding UTF-8 Box.java BoxDemo.java
java BoxDemo
```

Kết quả chuẩn (`stdout`):

```text
JAVA
12
core | generics
Box contains: 3.14
```

Diễn giải các lệnh:

- `new Box<>("Java")` dùng **diamond operator** `<>`. Kiểu đích `Box<String>` giúp trình biên dịch suy luận đối số kiểu của biểu thức khởi tạo.
- `Box.of(7)` suy luận `Integer` cho phương thức factory, bởi `7` có thể được đóng hộp tự động từ `int` sang `Integer`.
- `Box<List<String>>` cho thấy `T` có thể là một **kiểu tham số hóa khác**, không chỉ các lớp đơn giản.
- `Box<Double>` có thể nhận `3.14` qua autoboxing sang `Double`.
- `get()` được gọi qua các biến có kiểu rõ ràng; trình biên dịch xác định được phương thức của kết quả như `String.toUpperCase()` hoặc phép cộng số nguyên mà không cần người gọi viết cast.

Cả bốn cách sử dụng dùng chung **một định nghĩa `Box<T>`**. Ta không cần viết bốn lớp riêng có cùng nhiệm vụ.

## 4. Theo dấu một `T` xuyên suốt hợp đồng `Box`

Trong chính `Box<T>`, **một tham số kiểu** kết nối ba điểm: trường `private final T value` lưu đúng loại, constructor `Box(T value)` nhận đúng loại và getter `T get()` trả đúng loại. Ví dụ:

```java
Box<String> title = new Box<>("Generics");
String text = title.get();
```

Tại điểm dùng `Box<String>`, cả đối số constructor và kết quả getter đều phải tương thích với `String`. Nếu lớp cần setter, chữ ký nên là `void set(T value)` chứ không phải `set(Object)`; bản `Box` cố định giá trị ở bài này cố ý **không** cung cấp setter.

Đây là cách đọc **hợp đồng của hộp**, không phải toàn bộ quy tắc phạm vi type variable: khi thiết kế các lớp phức tạp hơn, còn cần xem `T` trong nhiều method parameters, interface, subclass, bounded type parameters và static generic methods. Những trường hợp đó không làm thay đổi ý chính: giữ cùng `T` ở những vị trí phải liên hệ kiểu, thay vì để rơi về `Object`.

## 5. So sánh với hộp sử dụng `Object`

Một cách cài đặt không dùng generic là:

```java
final class ObjectBox {
    private final Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Đây là **lớp minh họa độc lập**; nó không thuộc hai tệp của ví dụ `BoxDemo`. Khi sử dụng trong một phương thức:

```java
ObjectBox raw = new ObjectBox("Java");
String text = (String) raw.get();
```

người gọi phải ép kiểu từ `Object` về `String`. Nếu một nơi khác tạo `ObjectBox` chứa `Integer` mà người đọc vẫn ép sang `String`, lệnh ép có thể ném `ClassCastException` lúc chạy.

Trong phiên bản generic:

```java
Box<String> typed = Box.of("Java");
String text = typed.get();

// Box<String> wrong = Box.of(42); // Không biên dịch: hai kiểu không phù hợp
```

Kiểu dữ liệu sai có thể bị phát hiện tại thời điểm biên dịch, gần nơi tạo hoặc truyền giá trị. Generics đặc biệt có ích khi nhiều thành phần cùng dùng một API nhưng cần hợp đồng kiểu rõ ràng.

## 6. Các lựa chọn thiết kế quan trọng

### 6.1. Hộp cố định giá trị hay hộp cho phép thay thế?

Phiên bản chính dùng `private final T value` và chỉ có `get()`. Người dùng không thể gọi `set(...)` vì API không công bố phương thức thay giá trị. Điều này phù hợp với hộp chứa một giá trị đã xác lập tại lúc tạo.

Nếu yêu cầu bài toán là **thay thế giá trị theo thời gian**, một lớp khác có thể sử dụng trường không có `final` và setter nhận đúng kiểu `T`.

Ví dụ đầy đủ trong tệp **`MutableBox.java`**:

```java
import java.util.Objects;

public final class MutableBox<T> {
    private T value;

    public MutableBox(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public T get() {
        return value;
    }

    public void set(T newValue) {
        this.value = Objects.requireNonNull(newValue, "newValue");
    }
}
```

Ví dụ sử dụng **bên trong một phương thức**, sau khi khai báo lớp trên:

```java
MutableBox<String> status = new MutableBox<>("NEW");
status.set("DONE");
System.out.println(status.get()); // DONE
// status.set(10);                 // Lỗi biên dịch: 10 không phải String
```

Như vậy `set(T)` vẫn giữ được hợp đồng kiểu. Tuy nhiên, hộp có thể thay đổi giá trị đòi hỏi cân nhắc về đồng bộ nếu được chia sẻ giữa các luồng; phiên bản này **không được thiết kế là thread-safe**.

### 6.2. `final` ở trường không bảo đảm bất biến sâu

Xét trường hợp `T` là `List<String>` có thể sửa đổi. Tạo tệp **`AliasingDemo.java`** và dùng cùng `Box.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AliasingDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Box<List<String>> shared = Box.of(source);
        source.add("B");
        System.out.println(shared.get());

        Box<List<String>> snapshot = Box.of(List.copyOf(source));
        source.add("C");
        System.out.println(snapshot.get());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Box.java AliasingDemo.java
java AliasingDemo
```

`stdout`:

```text
[A, B]
[A, B]
```

Giải thích:

- `shared` chứa cùng một tham chiếu `ArrayList` với biến `source`. Dù trường `value` là `final`, việc `source.add("B")` vẫn làm thay đổi đối tượng danh sách mà cả hai tham chiếu cùng trỏ tới.
- `snapshot` chứa bản sao danh sách tạo bằng `List.copyOf(source)`. Khi thêm `"C"` vào `source` sau đó, danh sách trong `snapshot` không đổi. `List.copyOf` tạo danh sách không sửa được qua API danh sách; nó cũng không tự sao chép sâu các phần tử là đối tượng có thể thay đổi.

**Kết luận thiết kế:** `Box<T>` giữ cố định tham chiếu, nhưng không thể tự bảo đảm mọi `T` đều bất biến. Nếu muốn bảo vệ dữ liệu có thể thay đổi, hãy xác định rõ quy tắc tạo bản sao, quyền sở hữu dữ liệu hoặc chọn kiểu giá trị bất biến tại ranh giới sử dụng.

### 6.3. Có cho phép `null` không?

Ví dụ chính chủ ý dùng `Objects.requireNonNull`. Vì vậy:

```java
// Box<String> absent = new Box<>(null); // Biên dịch được, nhưng ném NullPointerException khi chạy
```

Bản thân tham số kiểu `String` không có nghĩa biến không thể chứa `null`; việc từ chối `null` đến từ **logic constructor**.

Một thiết kế khác có thể cho phép `null` bằng cách chỉ gán `this.value = value;`, nhưng khi đó API phải công bố ý nghĩa của việc giá trị vắng mặt. Không nên vừa cho phép `null` vừa ngầm giả định `get()` luôn trả về dữ liệu có thể gọi phương thức.

### 6.4. Có nên viết `equals()`, `hashCode()`, `toString()`?

`Box<T>` ở trên là một lớp thông thường kế thừa hành vi mặc định từ `Object`. Hai hộp chứa hai giá trị bằng nhau **không tự động được coi là bằng nhau theo nội dung**:

```java
Box<String> first = Box.of("Java");
Box<String> second = Box.of("Java");
System.out.println(first.equals(second)); // false với Box hiện tại
```

Nếu ứng dụng cần so sánh hộp theo giá trị, dùng làm khóa map hoặc hiển thị nội dung, có thể thiết kế thêm `equals()`, `hashCode()` và `toString()` theo một hợp đồng nhất quán. Điều này là quyết định về **ngữ nghĩa của đối tượng Box**, tách biệt với khả năng tham số hóa kiểu của generics. Không nên tự động giả định generic class có ngữ nghĩa so sánh giống record.

## 7. Kết hợp với interface generic

Một lớp lưu giữ giá trị có thể triển khai một **interface generic** mô tả khả năng đọc dữ liệu. Ví dụ kiến trúc:

```java
interface ValueSource<T> {
    T get();
}

final class ReadOnlyBox<T> implements ValueSource<T> {
    private final T value;

    ReadOnlyBox(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
```

Đây là **các khai báo lớp/interface minh họa**; chúng có thể đặt chung trong một tệp không công khai `public` hoặc tách thành các tệp phù hợp. `ReadOnlyBox<T> implements ValueSource<T>` nghĩa là đối số kiểu `T` được giữ nhất quán trong hợp đồng interface. Ví dụ `ValueSource<String> source = new ReadOnlyBox<>("Java");` cho phép mã phụ thuộc vào khả năng `get()` mà không cần biết cách lưu giá trị bên trong.

Không nhất thiết tạo interface cho một lớp duy nhất nếu không có nhu cầu trừu tượng hóa. Lựa chọn interface hữu ích khi có nhiều cách cung cấp giá trị chung một hợp đồng, chẳng hạn hộp có sẵn giá trị và một nguồn tính toán giá trị theo yêu cầu.

## 8. Những giới hạn cần hiểu khi thiết kế `Box<T>`

### 8.1. Chỉ được dùng kiểu tham chiếu làm đối số kiểu

`Box<int>` không hợp lệ vì `int` là kiểu nguyên thủy. Dùng lớp bao `Integer`:

```java
Box<Integer> number = Box.of(42);
int value = number.get(); // Tự unboxing Integer -> int
```

Java cũng có các lớp bao như `Long`, `Double`, `Boolean`. Nếu bài toán xử lý số nguyên hoặc số thực ở quy mô lớn, chi phí boxing và cấp phát đối tượng có thể ảnh hưởng hiệu năng; `Box<Integer>` không thay thế mọi trường hợp tối ưu hóa cho primitive.

### 8.2. Hai kiểu tham số hóa khác nhau không tự động tương thích

`String` là kiểu con của `Object`, nhưng **`Box<String>` không phải kiểu con của `Box<Object>`**. Generics Java mặc định **bất biến**:

```java
Box<String> stringBox = Box.of("Java");
// Box<Object> objectBox = stringBox; // Sai: incompatible types
```

Nếu một hàm chỉ cần **đọc** giá trị từ mọi loại hộp, có thể dùng wildcard `Box<?>`:

```java
static void printValue(Box<?> box) {
    System.out.println(box.get());
}
```

Đoạn `printValue` là **phương thức minh họa**, cần đặt trong một lớp. `Box<?>` biểu thị hộp có đối số kiểu chưa biết. Kiểu sử dụng của `box.get()` có thể xem như `Object`; không thể giả định đó là `String` hay `Integer`. Wildcard nên xuất hiện khi nó thật sự diễn đạt nhu cầu linh hoạt ở ranh giới API.

### 8.3. Tham số kiểu bị xóa phần lớn lúc chạy

Java generics chủ yếu được kiểm tra **tại thời điểm biên dịch** và thực thi với cơ chế `type erasure`. Chương trình không tạo ra một lớp runtime `Box<String>` hoàn toàn độc lập với `Box<Integer>`. Không thể viết:

```java
// if (someObject instanceof Box<String>) { ... } // Không hợp lệ
```

vì JVM không giữ thông tin kiểu `String` của `Box<String>` theo cách kiểm tra ấy. Có thể kiểm tra `instanceof Box<?>` để biết đối tượng là một `Box`, nhưng điều đó **không chứng minh** kiểu dữ liệu đang được hộp lưu giữ.

### 8.4. Raw type có thể phá vỡ hợp đồng kiểu

Mã nguồn cũ có thể bỏ đối số kiểu và dùng `Box` thay vì `Box<String>`. Raw type có thể dẫn đến cảnh báo và làm xuất hiện dữ liệu sai kiểu qua những thao tác không được kiểm tra đầy đủ. Hãy tránh:

```java
Box raw = Box.of(10); // Raw type; mất thông tin tham số kiểu tại nơi dùng
```

Thay bằng:

```java
Box<Integer> typed = Box.of(10);
```

Chạy `javac -Xlint:rawtypes,unchecked` giúp phát hiện nhiều đường dùng generic không an toàn. Generics làm giảm đáng kể lỗi cast, nhưng không thể bảo đảm an toàn nếu lập trình viên cố tình bỏ các cảnh báo hoặc dùng ép kiểu không được kiểm tra.

### 8.5. Không dùng `T` của lớp trực tiếp trong thành phần `static`

Đoạn sau là **mã sai**:

```java
class WrongBox<T> {
    // static T shared;        // Sai: static context không thể tham chiếu T của lớp
    // static T value() { ... } // Sai vì lý do tương tự
}
```

Một phương thức `static` generic cần khai báo tham số kiểu của **chính nó**, ví dụ `static <U> Box<U> of(U value)` trong `Box.java`. Điều đó giải thích vì sao factory `of` dùng `U` thay vì dùng trực tiếp `T` của lớp.

## 9. Lỗi phổ biến và cách sửa

| Tình huống | Vì sao có vấn đề? | Cách thiết kế tốt hơn |
|---|---|---|
| `class Box { Object value; }` và liên tục ép kiểu sau `get()` | Hợp đồng không chỉ ra kiểu giá trị ở vị trí sử dụng. | `class Box<T> { T value; }` và `T get()`. |
| `Box<String> b = Box.of(123);` | `Integer` không phù hợp với `String` trong hợp đồng đích. | Truyền `"123"` hoặc dùng `Box<Integer>` tùy dữ liệu thật. |
| `Box<int> b` | Generics yêu cầu kiểu tham chiếu. | `Box<Integer> b`. |
| `private Object value; public T get() { return (T) value; }` | Cài đặt tự tạo cast không được kiểm tra, dễ che giấu dữ liệu sai kiểu. | Lưu trực tiếp trường `T value`; dùng kiểm tra kiểu của compiler. |
| `Box raw = new Box("x");` | Bỏ đối số kiểu làm suy yếu kiểm tra kiểu và gây cảnh báo. | `Box<String> box = new Box<>("x");`. |
| Dùng `final T value` rồi nghĩ `List<T>` bên trong không thể đổi | `final` khóa tham chiếu, không khóa trạng thái đối tượng. | Chọn kiểu bất biến hoặc tạo bản sao phù hợp. |
| Constructor cho phép `null` nhưng getter giả định luôn khác `null` | Hợp đồng vắng mặt dữ liệu không rõ. | Quyết định rõ chính sách `null` ở constructor và API. |
| Kỳ vọng hai `Box` có cùng nội dung tự động `equals` | Generic không tự sinh so sánh theo nội dung. | Định nghĩa ngữ nghĩa giá trị nếu nghiệp vụ cần. |

Đặc biệt, không cần tạo một hệ thống generic phức tạp chỉ để lưu đúng một giá trị. `Box<T>` chỉ là ví dụ nhỏ cho thấy **kiểu dữ liệu trở thành một phần của hợp đồng công khai**; trong ứng dụng thật, chỉ nên thêm phương thức và trừu tượng hóa khi hành vi nghiệp vụ cần đến.

## 10. Tự kiểm tra

1. Trong khai báo `class Box<T>`, `T` đại diện cho điều gì? Nó được sử dụng ở đâu trong `private final T value`, `Box(T value)` và `T get()`?
2. Vì sao `Box<String> a = new Box<>("Java");` đúng, nhưng `Box<String> b = new Box<>(123);` không hợp lệ?
3. Trong phiên bản `Box` dùng `Objects.requireNonNull`, nếu gọi `Box.of(null)` thì lỗi xảy ra ở thời điểm nào và do đâu?
4. Vì sao `Box<List<String>>` có thể chứa một `ArrayList` thay đổi nội dung mặc dù trường `value` là `final`?
5. Vì sao factory `static <U> Box<U> of(U value)` phải khai báo `<U>` độc lập với `T` của lớp?
6. Nếu một hàm chỉ in giá trị của hộp mà không quan tâm kiểu cụ thể, chữ ký `void printValue(Box<?> box)` có lợi ích gì so với nhận `Box<String>`?

**Gợi ý đáp án:** (1) `T` là tham số kiểu của lớp, dùng đồng nhất cho dữ liệu được lưu, giá trị constructor nhận và kiểu getter trả ra. (2) Giá trị `123` không tương thích với `String` được yêu cầu. (3) Ném `NullPointerException` lúc thực thi constructor, vì chính sách không nhận `null` của lớp. (4) `final` không ngăn thay đổi nội dung đối tượng được tham chiếu. (5) Phương thức `static` không thuộc một thực thể `Box<T>` cụ thể nên phải có tham số kiểu riêng. (6) Wildcard biểu thị hàm đọc được mọi hộp mà không giả định loại dữ liệu bên trong.

Khi thiết kế một `Box<T>` tốt, hãy bắt đầu từ hợp đồng đơn giản: **lưu một giá trị đúng kiểu, trả lại đúng kiểu, che giấu trường dữ liệu, quyết định chính sách `null` và khả năng thay thế giá trị**. Generics bảo vệ quan hệ kiểu ở lúc biên dịch; các bảo đảm khác như bất biến sâu, so sánh theo nội dung và an toàn đa luồng cần được thiết kế riêng theo nhu cầu.
