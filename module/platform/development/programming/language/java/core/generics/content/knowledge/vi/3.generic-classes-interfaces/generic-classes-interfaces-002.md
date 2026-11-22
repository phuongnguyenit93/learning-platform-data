# Dùng `T` cho trường, tham số, giá trị trả về và constructor trong Java

## 1. Vì sao một lớp cần tham số kiểu `T`?

Trong Java, **generic class** nhận tham số kiểu để nhiều đối tượng có cùng cách hoạt động nhưng giữ được hợp đồng dữ liệu khác nhau. Ví dụ, một ô lưu giá trị có thể chứa `String` ở nơi này và `Integer` ở nơi khác mà không cần tạo hai lớp gần giống nhau.

```java
// Mảnh minh họa; đặt trong một lớp hoặc tệp Java thích hợp.
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}

Box<String> title = new Box<>("Java");
String text = title.get();
title.set("Generics");
// title.set(123); // Lỗi biên dịch: Box<String> chỉ nhận String.

Box<Integer> count = new Box<>(3);
int n = count.get(); // Unboxing từ Integer.
```

`T` là **tên tham số kiểu** (*type parameter*), khai báo sau tên lớp ở `class Box<T>`. `T` không phải từ khóa hay một lớp cụ thể; compiler sử dụng nó để liên kết kiểu của trường, constructor, tham số phương thức và giá trị trả về. Khi sử dụng `Box<String>`, những vị trí mang `T` được kiểm tra nhất quán theo `String`. Với `Box<Integer>`, chúng được kiểm tra theo `Integer`.

Một lớp có thể có nhiều tham số kiểu, chẳng hạn `Pair<K, V>`; `T` chỉ là quy ước phổ biến cho một kiểu chung. Các quy ước khác gồm `E` (element), `K` (key), `V` (value), `R` (result). Hãy dùng tên dễ hiểu nếu quan hệ giữa nhiều kiểu khó theo dõi.

**Bốn vị trí quan trọng nhất của `T` trong một lớp:**

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Trường (field) | `private T value;` | Đối tượng lưu một giá trị của kiểu `T`. |
| Tham số phương thức | `void set(T value)` | Chỉ chấp nhận đối số tương thích `T`. |
| Giá trị trả về | `T get()` | Người gọi nhận giá trị đúng kiểu của đối tượng generic. |
| Tham số constructor | `Box(T initialValue)` | Giá trị ban đầu phải tương thích kiểu `T` của đối tượng mới. |

Đây là quan hệ có tính nhất quán: cùng một tham số kiểu xuất hiện ở nhiều vị trí bảo đảm dữ liệu đi vào và đi ra được kiểm tra theo **một hợp đồng**.

## 2. Phạm vi của `T` trong khai báo lớp

Cú pháp nền tảng là:

```java
class ClassName<T> {
    // Có thể sử dụng T ở các trường và phương thức instance.
}
```

`T` thuộc phạm vi khai báo của lớp và có thể xuất hiện trong:

- Kiểu của trường instance: `T value`, `List<T> items`, `Optional<T> result`.
- Tham số của constructor và phương thức instance: `Box(T value)`, `void set(T value)`.
- Kiểu trả về: `T get()`, `List<T> snapshot()`.
- Kiểu tham số hóa khác: `Comparable<T>`, `Function<T, String>` hay `Map<String, T>`.
- Khai báo type bound hoặc việc triển khai/kế thừa kiểu generic, theo những quy tắc riêng ở các mục tiếp theo.

Kiểu `T` chỉ được biết cụ thể khi mã nguồn dùng lớp, ví dụ `Box<String>`. Ở phần thân `Box<T>`, trình biên dịch phải bảo đảm mọi thao tác hợp lệ cho **mọi kiểu `T` được phép**, không chỉ cho `String`. Vì thế:

```java
// Mảnh minh họa bên trong class Box<T>:
// value.length();          // Sai: không biết T có length().
// value.toString();        // Hợp lệ khi value không null vì mọi reference đều có toString().
// T another = value;       // Hợp lệ.
```

Giới hạn này rất có ích: nó ngăn một lớp generic phụ thuộc nhầm vào API chỉ có ở một kiểu dữ liệu cụ thể.

### `T` là kiểu tham chiếu

Generic type arguments phải là **reference types**. Không thể viết `Box<int>` hoặc `List<boolean>`; hãy viết `Box<Integer>` hoặc `List<Boolean>`. Java tự boxing/unboxing trong nhiều ngữ cảnh:

```java
Box<Integer> number = new Box<>(42); // int được boxing thành Integer.
int result = number.get();           // Integer được unboxing thành int.
```

Boxing không biến `T` thành primitive thật bên trong lớp; cần cân nhắc hiệu năng và `null` khi dữ liệu dạng primitive xuất hiện với tần suất cao.

## 3. Dùng `T` làm kiểu của trường

Trường `private T value;` buộc giá trị được lưu phải thuộc kiểu của từng đối tượng `Box<T>`. Trường nên để `private` và chỉ cung cấp thao tác hợp lệ thông qua phương thức:

```java
final class Slot<T> {
    private T value;

    Slot(T initial) {
        this.value = initial;
    }

    T get() {
        return value;
    }

    void set(T replacement) {
        value = replacement;
    }
}
```

Trường của đối tượng `Slot<String>` mang ràng buộc `String` ở mức compile-time. Việc khai báo `private` không tự tạo tính bất biến; `set` vẫn có thể thay thế dữ liệu. Nếu lớp chỉ lưu giá trị cố định, có thể thiết kế trường `private final T value` và bỏ setter:

```java
final class ImmutableBox<T> {
    private final T value;

    ImmutableBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`final` bảo đảm **tham chiếu trường không được gán lại sau khi khởi tạo**, không bảo đảm đối tượng được tham chiếu luôn bất biến. Nếu `T` là một `ArrayList` hoặc đối tượng mutable khác, người giữ tham chiếu vẫn có thể sửa nội dung. Muốn snapshot an toàn cho collection, cần xem xét sao chép phòng vệ.

Một trường chứa collection generic cũng có thể sử dụng `T` làm kiểu phần tử:

```java
// Mảnh minh họa, import java.util.*.
final class Bag<T> {
    private final List<T> items = new ArrayList<>();

    void add(T item) {
        items.add(item);
    }

    List<T> snapshot() {
        return List.copyOf(items);
    }
}
```

Ở đây `List<T>` nghĩa là danh sách phần tử `T`, khác với `List<?>` (kiểu phần tử chưa biết) và raw `List` (bỏ thông tin generic). `List.copyOf` tạo danh sách không sửa được và từ chối phần tử `null`, vì vậy hợp đồng `Bag` cần xử lý/chặn `null` nhất quán khi thêm.

## 4. Dùng `T` trong constructor

Constructor thiết lập trạng thái hợp lệ lúc tạo đối tượng. Với lớp generic, constructor có thể nhận tham số `T` và gán vào trường cùng kiểu:

```java
final class Message<T> {
    private final T payload;

    Message(T payload) { // T lấy từ Message<T>.
        this.payload = payload;
    }

    T payload() {
        return payload;
    }
}

Message<String> hello = new Message<>("Xin chào");
Message<Integer> status = new Message<>(200);
// Message<Integer> wrong = new Message<>("OK"); // Không tương thích Integer.
```

**Điểm cú pháp dễ nhầm:** khai báo constructor là `Message(T payload)`, **không phải** `Message<T>(T payload)`. Tham số kiểu của lớp đã được khai báo ở `class Message<T>`. Dấu diamond `<>` chỉ xuất hiện ở **biểu thức tạo đối tượng**, ví dụ `new Message<>("Xin chào")`, để trình biên dịch suy luận type argument.

Có thể viết rõ cả hai phía:

```java
Message<String> a = new Message<String>("Xin chào");
Message<String> b = new Message<>("Xin chào"); // Diamond từ Java 7.
```

Hai biến đều mang hợp đồng `Message<String>`. Tránh dạng raw `new Message("Xin chào")` vì dễ phát sinh cảnh báo unchecked và làm yếu việc kiểm tra kiểu.

### Constructor nhận kiểu có quan hệ với `T`

Một lớp chứa `List<T>` có thể muốn nhận nguồn là collection của một kiểu con `T`. Khi constructor chỉ **đọc** đầu vào, wildcard `? extends T` thường linh hoạt hơn:

```java
// Mảnh minh họa, import java.util.*.
final class Basket<T> {
    private final List<T> items;

    Basket(Collection<? extends T> source) {
        this.items = new ArrayList<>(source);
    }

    List<T> snapshot() {
        return List.copyOf(items);
    }
}

Basket<Number> numbers = new Basket<>(List.of(1, 2, 3));
// Mỗi phần tử Integer được chấp nhận làm Number.
```

`Collection<? extends T>` có thể cung cấp phần tử thuộc `T` hoặc kiểu con của `T`. Trình biên dịch cho phép sao chép chúng vào `List<T>`. Đây là hướng **producer extends**. Khi thiết kế constructor, cần phân biệt rõ yêu cầu sở hữu dữ liệu: `this.items = new ArrayList<>(source)` tạo bản sao danh sách, tránh việc sửa collection nguồn tác động trực tiếp đến dữ liệu trong lớp.

Không nên nhầm constructor thông thường dùng `T` của lớp với **generic constructor có tham số kiểu riêng**:

```java
// Mảnh minh họa; import java.util.function.Function.
final class ConvertedBox<T> {
    private final T value;

    <U> ConvertedBox(U source, Function<? super U, ? extends T> convert) {
        this.value = convert.apply(source);
    }

    T get() {
        return value;
    }
}

// Trong một phương thức:
ConvertedBox<Integer> length = new ConvertedBox<>("Java", String::length);
int n = length.get(); // 4
```

`T` thuộc `ConvertedBox<T>`, còn `U` chỉ thuộc constructor, được suy luận từ đối số `"Java"`. Constructor generic này vẫn là constructor của `ConvertedBox<Integer>` vì `convert` tạo ra `Integer`. Không khai báo lại `<T>` cho constructor chỉ để dùng `T` của lớp: tên cùng chữ có thể **che khuất** tham số kiểu của lớp, gây hiểu sai hợp đồng.

## 5. Dùng `T` làm kiểu tham số phương thức

Setter, update và thao tác thêm vào collection có thể nhận `T` để cấm dữ liệu sai kiểu ngay lúc biên dịch:

```java
final class MutableBox<T> {
    private T value;

    MutableBox(T initial) {
        value = initial;
    }

    void set(T replacement) {
        value = replacement;
    }

    T swap(T replacement) {
        T old = value;
        value = replacement;
        return old;
    }
}

MutableBox<String> label = new MutableBox<>("A");
label.set("B");
String old = label.swap("C"); // old là "B".
// label.set(123);            // Lỗi: Integer không phải String.
```

Ở `swap(T replacement)`, `T` vừa là **kiểu của đầu vào**, vừa là **kiểu kết quả**; đây là quan hệ mà việc thay hết bằng `Object` sẽ làm mất. Compiler biết `MutableBox<String>.swap(...)` trả `String` và chỉ nhận dữ liệu tương thích `String`.

Một tham số `T` không có nghĩa là chỉ được truyền **đúng một lớp runtime**. Nếu `T` là `Number`, có thể truyền các lớp con hợp lệ:

```java
MutableBox<Number> box = new MutableBox<>(1);
box.set(2.5);                // Double là Number.
Number stored = box.swap(3L); // Long là Number.
```

Tuy nhiên `MutableBox<Integer>` không tự động là `MutableBox<Number>`. Generic class Java mặc định **bất biến** (*invariant*). Quy tắc này ngăn việc đưa một `Double` vào đối tượng vốn cam kết chứa `Integer`.

### Không sử dụng `T` như một kiểu chưa có thao tác

Nếu phương thức muốn cộng/trừ giá trị, `T` không tự có toán tử số học:

```java
// Không hợp lệ trong class Accumulator<T>:
// T add(T a, T b) { return a + b; }
```

Phải mô hình hóa đúng thao tác thông qua bound, đối số hàm hoặc chiến lược cộng:

```java
import java.util.function.BinaryOperator;

final class Combiner<T> {
    private final BinaryOperator<T> combine;

    Combiner(BinaryOperator<T> combine) {
        this.combine = combine;
    }

    T join(T a, T b) {
        return combine.apply(a, b);
    }
}

// Combiner<Integer> adder = new Combiner<>(Integer::sum);
// int total = adder.join(2, 3); // 5
```

`BinaryOperator<T>` mô tả cách kết hợp hai giá trị kiểu `T` thành một kết quả cũng kiểu `T`, không phụ thuộc phép toán cụ thể.

## 6. Dùng `T` làm kiểu trả về

Getter và phương thức tính toán có thể trả trực tiếp `T`:

```java
T get() {
    return value;
}
```

Nếu biến tham chiếu là `Box<String>`, biểu thức `get()` được compiler kiểm tra như `String`; caller không cần tự ép từ `Object`:

```java
Box<String> textBox = new Box<>("Generics");
String upper = textBox.get().toUpperCase();
// int impossible = textBox.get(); // Lỗi biên dịch.
```

Getter không nhất thiết phải trả đúng một `T`; nó có thể trả cấu trúc chứa `T` để giữ thông tin phần tử:

```java
// Mảnh minh họa trong class Bag<T>.
List<T> snapshot() {
    return List.copyOf(items);
}
```

Vì kiểu trả về là `List<T>`, người dùng `Bag<String>` nhận `List<String>` và không phải cast từng phần tử. Đây là lợi ích trực tiếp khi kết hợp generics với Java Collections Framework.

### Giá trị có thể vắng mặt

Nếu nghiệp vụ cho phép chưa có dữ liệu, cân nhắc một hợp đồng rõ ràng:

```java
// Mảnh minh họa khi class có field T value, import java.util.Optional.
Optional<T> find() {
    return Optional.ofNullable(value);
}
```

`Optional.ofNullable` trả empty khi `value == null`; `Optional.of(value)` lại ném `NullPointerException` với `null`. Đừng dùng `Optional<T>` cho mọi getter theo thói quen: hãy chọn khi **khả năng vắng mặt** là ý nghĩa thực sự của API. Với constructor và setter, `Objects.requireNonNull(value)` có thể phù hợp nếu lớp không cho phép null.

## 7. `T` trên interface và lớp triển khai

Interface generic diễn đạt hợp đồng cho nhiều kiểu dữ liệu. Interface không có constructor của riêng nó nhưng có thể khai báo phương thức nhận/trả `T`; lớp triển khai mới sở hữu trường và constructor.

```java
interface Store<T> {
    void put(T value);
    T get();
}

final class MemoryStore<T> implements Store<T> {
    private T value;

    MemoryStore(T initialValue) {
        value = initialValue;
    }

    @Override
    public void put(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
```

Người gọi sử dụng interface với kiểu cụ thể:

```java
Store<String> welcome = new MemoryStore<>("Xin chào");
welcome.put("Tạm biệt");
String message = welcome.get();
// welcome.put(123); // Lỗi biên dịch.
```

Interface cho phép triển khai khác nhau giữ cùng hợp đồng, chẳng hạn lưu trong bộ nhớ, đọc từ file hoặc cache. Khi triển khai, có thể **truyền tiếp tham số kiểu** như `class MemoryStore<T> implements Store<T>` hoặc **chốt kiểu** như `class StringStore implements Store<String>`. Nếu chốt kiểu, các phương thức triển khai phải nhận/trả `String`.

Interface thường nên định nghĩa hành vi độc lập với implementation; đừng dùng `Object` cho tham số rồi buộc caller cast chỉ vì nhiều kiểu dữ liệu cùng tham gia.

## 8. `T` qua lớp cha, lớp con và nhiều tham số kiểu

Khi kế thừa generic class, lớp con có thể tiếp tục giữ `T`:

```java
class BaseHolder<T> {
    private final T value;

    BaseHolder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NamedHolder<T> extends BaseHolder<T> {
    private final String name;

    NamedHolder(String name, T value) {
        super(value);
        this.name = name;
    }

    String name() {
        return name;
    }
}
```

`NamedHolder<Integer>` kế thừa `BaseHolder<Integer>`. Lời gọi `super(value)` truyền đúng kiểu `T` tới constructor của lớp cha. Một lớp con cũng có thể cố định type argument:

```java
class TextHolder extends BaseHolder<String> {
    TextHolder(String value) {
        super(value);
    }
}
```

Khi cần mô tả hai loại dữ liệu liên quan, dùng hai tham số kiểu riêng thay vì ép tất cả về một `T`:

```java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> result = new Pair<>("Tuổi", 20);
String label = result.left();
Integer age = result.right();
```

`record` generic (Java 17+) tạo thành phần bất biến theo tham chiếu, constructor chuẩn và accessor có kiểu `L`/`R`. Với record, khai báo thành phần trong ngoặc của tên record xác định trạng thái; compiler sinh accessor `left()`, `right()` trả đúng kiểu đã khai báo.

## 9. Bound: khi `T` phải hỗ trợ một API cụ thể

Với `class DataBox<T>` không có bound, compiler chỉ biết `T` là một reference type. Nếu logic cần khả năng chuyển số thành `double`, dùng **upper bound**:

```java
final class NumberBox<T extends Number> {
    private final T number;

    NumberBox(T number) {
        this.number = number;
    }

    T get() {
        return number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}

NumberBox<Integer> a = new NumberBox<>(7);
NumberBox<Double> b = new NumberBox<>(2.5);
// NumberBox<String> wrong = new NumberBox<>("7"); // Lỗi bound.
```

Nhờ `T extends Number`, compiler cho phép gọi `doubleValue()` trên trường `number`. Kiểu trả về của `get()` vẫn là kiểu `T` cụ thể, vì vậy `NumberBox<Integer>.get()` trả `Integer` tại compile-time.

Bound có thể là interface: `<T extends Comparable<T>>`, không dùng từ khóa `implements` trong danh sách type parameter. Có thể kết hợp lớp và interface như `<T extends Number & Comparable<T>>`, trong đó bound lớp (nếu có) phải đứng trước các bound interface.

Cần chọn bound theo **hành vi thật sự cần**. Bound quá rộng làm mất sức mạnh kiểm tra kiểu; bound quá hẹp khiến API không nhận các loại dữ liệu có thể xử lý hợp lệ.

## 10. Phân biệt `T` của lớp, phương thức generic và thành viên `static`

Một lớp generic không buộc mọi phương thức bên trong dùng `T`. Phương thức có thể khai báo **tham số kiểu riêng**:

```java
final class Helper<T> {
    private final T value;

    Helper(T value) {
        this.value = value;
    }

    T get() { return value; } // T thuộc Helper<T>.

    static <U> U choose(U first, U second) {
        return first;
    }
}
```

`U` của `choose` thuộc phương thức. Điều này cũng giải thích vì sao phương thức `static` có thể generic:

```java
String word = Helper.choose("A", "B");
Integer number = Helper.choose(1, 2);
```

Ngược lại, kiểu `T` khai báo ở `class Helper<T>` **không được tham chiếu từ ngữ cảnh static của lớp**:

```java
class Wrong<T> {
    // static T shared;         // Lỗi biên dịch.
    // static T build() { ... } // Lỗi: T thuộc lớp generic.
}
```

Lý do: thành viên `static` thuộc về lớp chung, không được nhân bản theo `Helper<String>` và `Helper<Integer>`. Muốn một phương thức static hoạt động với nhiều kiểu, khai báo tham số kiểu riêng, như `static <U> U identity(U value)`.

**Lưu ý về trùng tên:** Có thể viết `<T> T method(T arg)` trong `class Helper<T>`, nhưng `T` mới của phương thức sẽ che khuất `T` của lớp và dễ gây hiểu lầm. Hãy dùng một tên khác (`U`, `R`) khi chúng là hai tham số kiểu độc lập.

## 11. Khi constructor và phương thức làm việc với collection chứa `T`

Một lỗi rất thường gặp là giả sử mọi cấu trúc mang phần tử có kiểu con đều gán được cho cấu trúc kiểu cha:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> nums = integers; // Sai: generics là invariant.
```

Để chỉ **đọc** dữ liệu cho constructor hoặc phương thức, sử dụng `Collection<? extends T>`. Để **ghi** giá trị `T` vào một đích được truyền từ ngoài, dùng `Collection<? super T>` khi thích hợp:

```java
// Mảnh minh họa nằm trong một lớp utility, import java.util.*.
static <T> void copy(
        Collection<? extends T> source,
        Collection<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}

// Trong một phương thức:
List<Integer> source = List.of(2, 4, 6);
List<Number> destination = new ArrayList<>();
copy(source, destination);
```

Nguyên tắc **PECS (Producer Extends, Consumer Super)** giải thích hai phía:

- `source` sinh ra `T`, nên `? extends T` cho phép đọc an toàn.
- `destination` nhận `T`, nên `? super T` cho phép thêm phần tử `T`.

Nếu lớp của bạn muốn vừa đọc, vừa cập nhật giá trị một cách nhất quán, dùng tham số chính xác `T` ở field, setter và getter vẫn là lựa chọn rõ ràng. Wildcard chỉ nên thêm ở nơi nó thực sự mở rộng phạm vi đối số mà không phá hợp đồng.

Một chi tiết thiết kế: `List<T> snapshot()` được trả về từ lớp và là bản sao không sửa được thì caller không thể trực tiếp thay đổi trạng thái bên trong. Nhưng nếu `T` là một đối tượng mutable, có thể vẫn cần sao chép sâu hoặc loại dữ liệu bất biến để ngăn sửa qua alias của từng phần tử.

## 12. Các giới hạn cần hiểu: erasure, tạo đối tượng và mảng

Java generics sử dụng **type erasure** trong biểu diễn runtime thông thường. Compiler kiểm tra ràng buộc kiểu rồi có thể chèn cast/bridge method khi cần. Một lớp `Box<T>` không sinh ra lớp runtime mới riêng cho mỗi `T`.

Vì vậy, đoạn sau không hợp lệ trong một generic class không có công cụ tạo giá trị:

```java
class CannotConstruct<T> {
    // T value = new T();           // Không thể khởi tạo T trực tiếp.
    // Class<T> type = T.class;      // Không có class literal T.class.
    // T[] values = new T[10];      // Không được tạo mảng T trực tiếp.
    // boolean test = value instanceof T; // T không reifiable.
}
```

Muốn constructor tự tạo một giá trị `T`, hãy **truyền factory** có kiểu, chẳng hạn `Supplier<? extends T>`:

```java
import java.util.Objects;
import java.util.function.Supplier;

final class FactoryBox<T> {
    private final T value;

    FactoryBox(Supplier<? extends T> supplier) {
        value = Objects.requireNonNull(supplier.get());
    }

    T get() { return value; }
}

// FactoryBox<StringBuilder> box =
//     new FactoryBox<>(StringBuilder::new);
```

`Supplier<? extends T>` chịu trách nhiệm tạo giá trị thuộc `T` hoặc kiểu con của `T`. Khi cần phản ánh constructor runtime theo `Class<T>`/reflection, cũng phải truyền thông tin kiểu tường minh và xử lý exceptions; không thể suy ra constructor chỉ từ tên tham số kiểu `T` đã bị erase.

Một hạn chế khác là không thể dùng tham số kiểu để phân biệt hai overload nếu sau erasure chúng có chữ ký trùng nhau:

```java
// Không thể khai báo đồng thời trong cùng một lớp:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
// Hai tham số đều erase thành List, gây name clash.
```

Không lạm dụng raw type hoặc unchecked cast để lách hạn chế này: cần đổi tên hoặc thiết kế một phương thức generic thực sự.

## 13. Ví dụ chạy được: trường, constructor, tham số, kết quả và interface

Chương trình sau gom các kiểu thành viên `T` vào một tệp độc lập. Nó đồng thời minh họa trường mutable, lớp chỉ nhận giá trị ban đầu, interface generic, factory và bound.

Tạo tệp **`GenericMembersDemo.java`** với toàn bộ nội dung:

```java
import java.util.*;
import java.util.function.Supplier;

public class GenericMembersDemo {
    interface Store<T> {
        void put(T value);
        T get();
    }

    static final class Slot<T> implements Store<T> {
        private T value;

        Slot(T initialValue) {
            this.value = Objects.requireNonNull(initialValue);
        }

        @Override
        public void put(T value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public T get() {
            return value;
        }

        T swap(T replacement) {
            T previous = value;
            put(replacement);
            return previous;
        }
    }

    static final class Basket<T> {
        private final List<T> items;

        Basket(Collection<? extends T> initial) {
            items = new ArrayList<>(initial);
        }

        void add(T value) {
            items.add(Objects.requireNonNull(value));
        }

        List<T> snapshot() {
            return List.copyOf(items);
        }
    }

    record Person(String name) {}

    static final class FactoryBox<T> {
        private final T value;

        FactoryBox(Supplier<? extends T> factory) {
            value = Objects.requireNonNull(factory.get());
        }

        T get() { return value; }
    }

    static final class NumberBox<T extends Number> {
        private final T number;

        NumberBox(T number) { this.number = number; }
        double asDouble() { return number.doubleValue(); }
    }

    static <U> U select(U first, U second, boolean chooseSecond) {
        return chooseSecond ? second : first;
    }

    public static void main(String[] args) {
        Slot<String> name = new Slot<>("Lan");
        System.out.println("initial: " + name.get());
        System.out.println("previous: " + name.swap("Mai"));
        System.out.println("current: " + name.get());

        Slot<Integer> count = new Slot<>(3);
        count.put(5);
        System.out.println("count: " + count.get());

        Basket<Number> numbers = new Basket<>(List.of(1, 2, 3));
        numbers.add(2.5);
        System.out.println("basket: " + numbers.snapshot());

        FactoryBox<Person> person = new FactoryBox<>(() -> new Person("An"));
        System.out.println("factory: " + person.get().name());

        NumberBox<Integer> numberBox = new NumberBox<>(7);
        System.out.println("asDouble: " + numberBox.asDouble());
        System.out.println("select: " + select("first", "second", true));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac -Xlint:all GenericMembersDemo.java
java GenericMembersDemo
```

Kết quả stdout chính xác (đã chạy với JDK 21; không có cảnh báo khi biên dịch bằng `-Xlint:all`):

```text
initial: Lan
previous: Lan
current: Mai
count: 5
basket: [1, 2, 3, 2.5]
factory: An
asDouble: 7.0
select: second
```

Giải thích các liên hệ kiểu:

1. `Slot<T>` khai báo `private T value`: constructor `Slot(T)` nhận giá trị ban đầu, `put(T)` cập nhật, `get(): T` đọc và `swap(T): T` trả giá trị cũ. Tất cả cùng chung tham số kiểu của **lớp**.
2. `Store<T>` giữ hợp đồng phương thức không phụ thuộc cách lưu; `Slot<String>` thực thi `Store<String>` mà không dùng cast.
3. `Basket<T>` giữ trường `List<T>`, constructor nhận nguồn `Collection<? extends T>`, getter `snapshot()` trả `List<T>` là một bản sao không sửa được.
4. `FactoryBox<T>` lấy giá trị từ `Supplier<? extends T>` thay vì cố gọi `new T()`; constructor đảm bảo factory trả giá trị không null.
5. `NumberBox<T extends Number>` hạn chế `T` để có quyền gọi `doubleValue()`.
6. `select` là **static generic method**, tự khai báo `<U>`, độc lập với các tham số kiểu của các lớp lồng ở trên.

Ví dụ dùng `Objects.requireNonNull` với `Slot` và `FactoryBox` để quy định không chấp nhận null. Với `Basket`, constructor giả định collection nguồn có phần tử không null vì `snapshot()` dùng `List.copyOf`; trong thiết kế production, nên thống nhất chính sách null ngay lúc nhận nguồn, ví dụ kiểm tra từng phần tử đầu vào.

## 14. Lỗi phổ biến và cách tự kiểm tra

| Sai lầm | Vì sao sai hoặc rủi ro | Cách giải quyết |
| --- | --- | --- |
| `class Box { Object value; }` rồi cast ở getter | Mất quan hệ kiểu giữa đầu vào/đầu ra, dễ `ClassCastException` | Dùng `class Box<T>`, `T value` và `T get()`. |
| `class Box<T> { Box<T>(T value) {} }` | Constructor không ghi type arguments sau tên constructor | Viết `Box(T value)`. |
| `new Box("Java")` | Tạo đối tượng dạng raw, có thể sinh cảnh báo và làm yếu kiểm tra kiểu | Dùng `new Box<>("Java")` với kiểu đích hoặc `new Box<String>("Java")`. |
| `Box<int>` | Generics nhận reference type | Dùng `Box<Integer>`. |
| `static T cache;` trong `class Box<T>` | `T` của lớp không dùng được trong static context | Dùng field instance hoặc phương thức static tự khai báo `<U>`. |
| `T v = new T();` | Không thể tạo `T` trực tiếp vì type erasure | Truyền `Supplier<? extends T>` hoặc factory khác. |
| Getter trả `Object` dù trường là `T` | Người dùng buộc cast và mất type safety | Trả trực tiếp `T` hoặc container `List<T>`/`Optional<T>`. |
| Setter nhận `Object` | Cho phép giá trị không đúng hợp đồng của đối tượng | Dùng `void set(T value)`. |
| Trả thẳng trường `List<T>` mutable | Người gọi có thể sửa trạng thái nội bộ không qua API | Cân nhắc bản sao `List.copyOf` và quản lý phần tử mutable. |
| Sử dụng `List<Integer>` ở nơi yêu cầu `List<Number>` | Generics bất biến | Dùng kiểu thống nhất hoặc wildcard đúng hướng khi chỉ đọc/ghi. |
| `T extends Number` nhưng cố gọi API chỉ có trên `Integer` | Bound chỉ bảo đảm thành viên của `Number` | Đổi API, kiểm tra runtime có chủ đích hoặc chọn bound phù hợp. |
| Dùng `<T>` trên phương thức với cùng tên `T` của lớp | Tham số kiểu mới che khuất tham số lớp | Đặt tên khác (`<U>`), chỉ khai báo generic method khi cần. |
| Getter có thể trả `null` nhưng caller giả định luôn có dữ liệu | Dễ ném `NullPointerException` | Quy định invariant từ constructor hoặc biểu diễn sự vắng mặt bằng `Optional<T>` khi phù hợp. |

Một cách rà soát nhanh lớp generic là vẽ luồng: **giá trị truyền vào constructor/setter → trường `T` → getter hoặc phương thức xử lý → giá trị trả về `T`**. Nếu ở bất kỳ bước nào bạn buộc phải cast từ `Object`, hãy xem xét có chỗ nào đang làm mất tham số kiểu.

## 15. Bài tập thực hành và tiêu chí tự đánh giá

**Bài 1 — Lớp bất biến.** Viết `final class ReadOnlyBox<T>` với trường `private final T value`, constructor `ReadOnlyBox(T value)` và getter `T get()`. Tạo đối tượng `ReadOnlyBox<String>` và `ReadOnlyBox<Integer>`. Thử truyền `String` vào `ReadOnlyBox<Integer>` để quan sát lỗi biên dịch.

**Bài 2 — Setter và giá trị cũ.** Mở rộng `MutableBox<T>` bằng phương thức `T replace(T next)`, trả về giá trị cũ trước khi cập nhật. Thử gọi với `MutableBox<String>`; giải thích vì sao kiểu trả về chính xác là `String` thay vì `Object`.

**Bài 3 — Interface generic.** Định nghĩa `interface Cache<K, V>` với `void put(K key, V value)` và `Optional<V> find(K key)`. Viết implementation dựa trên `Map<K,V>`. Kiểm tra `Cache<String, Integer>` loại bỏ lời gọi có khóa hoặc giá trị sai kiểu ngay lúc biên dịch. Lưu ý `Map<K,V>` dùng hai tham số vì khóa và giá trị là hai loại dữ liệu khác nhau.

**Bài 4 — Constructor với wildcard.** Viết `class Numbers<T extends Number>` có constructor nhận `Collection<? extends T>`. Tạo `Numbers<Number>` từ `List<Integer>`, sau đó trả về tổng dạng `double` bằng cách duyệt các phần tử và gọi `doubleValue()`. Giải thích tại sao `Collection<T>` trong constructor kém linh hoạt hơn khi nhận các nguồn kiểu con.

**Bài 5 — Không thể `new T()`.** Viết `class LazyValue<T>` nhận `Supplier<? extends T>` ở constructor và tạo đối tượng khi lần đầu gọi `T get()`. Tự quyết định cách cache kết quả và liệu có chấp nhận null hay không; phải mô tả rõ hợp đồng của class.

Sau khi làm bài, người học cần trả lời chắc chắn bốn câu: **`T` được khai báo ở đâu? Trường giữ kiểu gì? Constructor và setter nhận kiểu gì? Getter đảm bảo trả kiểu gì?** Khi cả bốn cùng tham chiếu một tham số kiểu, Java có thể kiểm tra trọn tuyến dữ liệu lúc biên dịch, giúp thiết kế lớp và giao diện tổng quát mà vẫn giữ an toàn kiểu.
