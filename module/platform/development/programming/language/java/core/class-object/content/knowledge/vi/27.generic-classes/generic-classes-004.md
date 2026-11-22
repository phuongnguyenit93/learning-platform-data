# Lớp generic trong Java: giới hạn kiểu với `extends` và nhiều ràng buộc

## 1. Tại sao generic cần giới hạn kiểu?

Một lớp generic có thể viết:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Đoạn trên là khai báo class hợp lệ. Với `T` không bị giới hạn, compiler không biết object kiểu `T` có phương thức như `doubleValue()`, `compareTo()` hay một giao diện nghiệp vụ `code()`. Compiler chỉ có những khả năng chung của `Object`.

Nếu lớp thực sự cần xử lý một **đối tượng thuộc một họ type xác định**, ta khai báo **upper bound**:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    double doubled() {
        return value.doubleValue() * 2;
    }
}
```

Ở đây `T extends Number` có nghĩa **đối số kiểu T phải là subtype của Number**, nên trong thân lớp có thể gọi những methods mà type Number cho phép truy cập. Từ khóa `extends` dùng cho cả **class bound** và **interface bound** của type parameter, kể cả khi type thực tế triển khai một interface bằng `implements`.

Khi một type phải đáp ứng **nhiều hợp đồng cùng lúc**, Java hỗ trợ **nhiều ràng buộc**:

```java
class RankedBox<T extends Number & Comparable<T>> {
    private final T value;

    RankedBox(T value) {
        this.value = value;
    }

    int compareTo(T other) {
        return value.compareTo(other);
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T` ở đây phải vừa là `Number`, vừa đáp ứng `Comparable<T>`. Nhờ đó, class có thể **gọi methods của cả hai bound types** mà không ép kiểu thủ công.

> **Điểm nhớ:** Giới hạn kiểu không “lấy object rồi gắn thêm khả năng” ở runtime. Nó là **hợp đồng compile-time**: chỉ các type arguments phù hợp mới được sử dụng và compiler cho phép truy cập members được ràng buộc bảo đảm.

Bài này tập trung vào cú pháp `extends`, điều kiện type argument hợp lệ, **multiple bounds `A & B & C`**, thứ tự lớp/interface, sử dụng trong generic class và method, cùng hệ quả tới erasure, variance, thiết kế API và lỗi thường gặp. Các chương trình đầy đủ biên dịch với Java 17+.

## 2. Ví dụ chạy đầu tiên: một giới hạn kiểu bằng class

Tạo file **`BoundedNumberBoxDemo.java`**:

```java
class NumberBox<T extends Number> {
    private final T number;

    NumberBox(T number) {
        this.number = number;
    }

    double twice() {
        return number.doubleValue() * 2;
    }

    T get() {
        return number;
    }
}

public class BoundedNumberBoxDemo {
    public static void main(String[] args) {
        NumberBox<Integer> integers = new NumberBox<>(7);
        NumberBox<Double> decimals = new NumberBox<>(2.5);

        System.out.println(integers.twice());
        System.out.println(decimals.twice());
        System.out.println(integers.get());
    }
}
```

Biên dịch/chạy:

```bash
javac BoundedNumberBoxDemo.java
java BoundedNumberBoxDemo
```

Standard output:

```text
14.0
5.0
7
```

### Phân tích

- `Integer` và `Double` đều là subclasses của `Number`, nên là type arguments hợp lệ cho `NumberBox<T extends Number>`.
- `T get()` vẫn trả đúng type argument tại call site: `Integer` hoặc `Double`; giới hạn không làm mất thông tin static generic type.
- Trong class, `number.doubleValue()` hợp lệ vì method được bảo đảm bởi `Number`.
- `new NumberBox<>(7)` sử dụng diamond operator để compiler suy luận type argument.
- `String` không phải subtype của `Number`, nên `NumberBox<String>` **không hợp lệ**.

### Giới hạn là điều kiện về type, không phải điều kiện về giá trị

`NumberBox<Integer>` chấp nhận các giá trị Integer có nhiều độ lớn khác nhau, kể cả âm; bound `extends Number` **không tự kiểm** range, overflow, số dương hay nghiệp vụ. Muốn đặt điều kiện giá trị, thêm constructor validation hoặc domain value object riêng.

## 3. Trường hợp không dùng bound: compiler không biết method

Đoạn mã sau **cố ý không biên dịch**:

```java
class BadBox<T> {
    T value;

    double twice() {
        return value.doubleValue() * 2;
        // Sai: Object không bảo đảm doubleValue().
    }
}
```

Sửa bằng cách khai báo `class GoodBox<T extends Number>` rồi viết body tương ứng. Compiler khi đó cho phép `doubleValue()`.

**Không nên** dùng ép kiểu `((Number) value).doubleValue()` trên một `T` không bị bound nếu class chỉ có nghĩa với Number. Cast đẩy lỗi sang runtime và làm chữ ký API thiếu thông tin. Một bound đúng chuyển phần lớn kiểm tra đó sang compile time.

## 4. `extends` với interface không có nghĩa là lớp Java phải `extends` interface

Khai báo:

```java
class Holder<T extends Comparable<T>> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    boolean lessThan(T other) {
        return value.compareTo(other) < 0;
    }
}
```

`Comparable<T>` là **interface**, nhưng ràng buộc vẫn phải viết `extends`, **không viết `implements`** trong danh sách type parameters.

Một class cụ thể như `String` implements `Comparable<String>`, nên `Holder<String>` hợp lệ.

Tạo **`InterfaceBoundDemo.java`**:

```java
class Holder<T extends Comparable<T>> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    boolean comesBefore(T other) {
        return value.compareTo(other) < 0;
    }
}

public class InterfaceBoundDemo {
    public static void main(String[] args) {
        Holder<String> words = new Holder<>("apple");
        Holder<Integer> numbers = new Holder<>(2);

        System.out.println(words.comesBefore("banana"));
        System.out.println(numbers.comesBefore(1));
    }
}
```

```bash
javac InterfaceBoundDemo.java
java InterfaceBoundDemo
```

```text
true
false
```

### Ý nghĩa

`T extends Comparable<T>` ràng buộc `T` có thể so sánh với **cùng T** qua `compareTo(T)`. Mỗi method call vẫn được compiler kiểm type parameter tương ứng.

Không phải class nào “có khái niệm so sánh” cũng implements `Comparable<T>`. Nếu domain dùng `Comparator<T>` bên ngoài thay vì natural order, thiết kế nên nhận comparator và có thể không cần comparable bound.

## 5. Khi có nhiều bound, dùng `&` thay vì dấu phẩy

Cú pháp:

```java
class Example<T extends BaseClass & InterfaceOne & InterfaceTwo> {
}
```

Đây là **mẫu cú pháp**; các types được đặt tên giả định phù hợp.

Dấu `&` thể hiện **intersection of constraints**: một type argument phải đáp ứng **đồng thời tất cả** các bound types. Đây **không phải phép toán bitwise AND** ở runtime, dù cũng dùng ký tự `&`.

**Không dùng**:

```java
// class Wrong<T extends Number, Comparable<T>> { }
// Sai: dấu phẩy ngăn cách type parameters,
// không ngăn cách các bounds của một type parameter.
```

Cú pháp đúng:

```java
class NumericComparable<T extends Number & Comparable<T>> {
}
```

Có thể viết nhiều type parameters riêng bằng dấu phẩy, mỗi parameter có bound riêng:

```java
class Pair<K extends Comparable<K>, V extends Number> {
}
```

### Phân biệt dấu

- `,` giữa `K` và `V`: **hai type parameters khác nhau**.
- `&` giữa Number và Comparable: **nhiều bounds của cùng một T**.
- `extends` xuất hiện **một lần trước danh sách bounds của mỗi type parameter**.

## 6. Ví dụ chạy: Number và Comparable cùng lúc

Tạo **`MultipleBoundsDemo.java`**:

```java
class NumericRange<T extends Number & Comparable<T>> {
    private final T minimum;
    private final T maximum;

    NumericRange(T minimum, T maximum) {
        if (minimum.compareTo(maximum) > 0) {
            throw new IllegalArgumentException(
                    "min must not exceed max");
        }
        this.minimum = minimum;
        this.maximum = maximum;
    }

    boolean contains(T value) {
        return minimum.compareTo(value) <= 0
                && value.compareTo(maximum) <= 0;
    }

    double widthAsDouble() {
        return maximum.doubleValue()
                - minimum.doubleValue();
    }
}

public class MultipleBoundsDemo {
    public static void main(String[] args) {
        NumericRange<Integer> integers =
                new NumericRange<>(1, 5);
        NumericRange<Double> decimals =
                new NumericRange<>(1.5, 4.0);

        System.out.println(integers.contains(3));
        System.out.println(integers.contains(9));
        System.out.println(decimals.widthAsDouble());
    }
}
```

```bash
javac MultipleBoundsDemo.java
java MultipleBoundsDemo
```

```text
true
false
2.5
```

Giải thích:

1. `Integer` và `Double` đều là subtypes của Number và implement `Comparable` với chính type tương ứng.
2. `minimum.compareTo(maximum)` dùng hợp đồng từ `Comparable<T>`.
3. `doubleValue()` dùng hợp đồng từ `Number`.
4. Compiler kiểm cả hai yêu cầu **trên cùng type argument**.
5. Constructor còn kiểm **điều kiện về giá trị** `minimum <= maximum`. Bound chỉ kiểm type, nên constructor validation vẫn cần.

### Giới hạn ví dụ

`doubleValue()` có thể mất độ chính xác đối với một số Number subtypes. `widthAsDouble` ở đây là phép đo minh họa, không phải thuật toán chính xác cho mọi numeric domain, tiền tệ hoặc big integers. Generic bounds không bảo đảm không overflow, không NaN và không lỗi số học.

## 7. Quy tắc thứ tự quan trọng: class bound phải đứng đầu

Nếu một type parameter có cả class bound và interface bounds, **class bound phải là phần tử đầu tiên**:

```java
class Good<T extends Number & Comparable<T>> {
}
```

Đoạn sau **cố ý sai**:

```java
// class Bad<T extends Comparable<T> & Number> { }
// Sai: Number là class nhưng đứng sau interface.
```

Compiler không cho đưa một class type vào các additional bounds sau `&`.

**Có thể chỉ có interfaces:**

```java
class Worker<T extends Runnable & AutoCloseable> {
}
```

Đây là khai báo hợp lệ: Runnable và AutoCloseable đều là interfaces, dù class thực tế cung cấp implementation cho chúng có thể phức tạp.

**Không được dùng hai superclass bất kỳ:**

```java
// class Impossible<T extends java.util.ArrayList<String>
//                    & java.util.HashSet<String>> { }
// Sai: không thể có class bound thứ hai sau &.
```

Java chỉ cho phép một class bound ở đầu; các bounds bổ sung phải là interface types. Điều này phù hợp nguyên tắc Java **không hỗ trợ đa kế thừa classes**.

## 8. Vì sao chỉ một class bound nhưng nhiều interfaces?

Một class Java chỉ có thể extends **một class** ở một thời điểm; nhưng có thể implements nhiều interfaces. Multiple bounds diễn tả điều tương tự ở mức type parameter.

Ví dụ `T extends AbstractEntity & Auditable & Serializable` có nghĩa:

- T là subtype của AbstractEntity.
- T cũng implement Auditable.
- T cũng đáp ứng Serializable.
- Compiler có thể dùng các members được accessible từ các bounds ấy.

Chữ ký không buộc T phải là chính AbstractEntity; một **subclass** của AbstractEntity triển khai các interfaces phù hợp cũng được chấp nhận.

**Không nhầm với composition:** Multiple bounds chỉ mô tả type capabilities; nó không tự sinh object, add method hay inject services.

## 9. Ví dụ đầy đủ: một class bound và hai interface bounds

Tạo **`EntityBoundsDemo.java`**:

```java
import java.io.Serializable;

abstract class BaseEntity {
    private final long id;

    BaseEntity(long id) {
        this.id = id;
    }

    public long id() {
        return id;
    }
}

interface Named {
    String name();
}

final class Customer extends BaseEntity
        implements Named, Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;

    Customer(long id, String name) {
        super(id);
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

class EntityBox<
        T extends BaseEntity & Named & Serializable> {
    private final T value;

    EntityBox(T value) {
        this.value = value;
    }

    String summary() {
        return value.id() + ":" + value.name();
    }

    boolean isSerializable() {
        return value instanceof Serializable;
    }
}

public class EntityBoundsDemo {
    public static void main(String[] args) {
        EntityBox<Customer> box =
                new EntityBox<>(new Customer(7, "An"));

        System.out.println(box.summary());
        System.out.println(box.isSerializable());
    }
}
```

```bash
javac EntityBoundsDemo.java
java EntityBoundsDemo
```

```text
7:An
true
```

**Đọc bound từng phần:**

- `BaseEntity` là **class bound**, đứng đầu.
- `Named` là interface có `name()`.
- `Serializable` là marker interface; không có method nghiệp vụ phải gọi nhưng vẫn giới hạn type arguments.
- `Customer` extends BaseEntity và implements Named/Serializable, nên hợp lệ.
- Trong `summary()`, `value.id()` và `value.name()` được compiler cho phép.
- `instanceof Serializable` chỉ là kiểm minh họa; generic declaration đã bảo đảm type parameter thỏa interface này ở compile time với cách sử dụng type-safe.

**Cẩn thận về Serializable:** Implements Serializable không tự có nghĩa serializing mọi object sẽ thành công. Object graph và quy tắc serialization riêng vẫn quyết định runtime behavior.

## 10. Multiple interface bounds: giao điểm các khả năng

Nếu không cần class bound, ta có thể viết:

```java
class Screen<T extends Named & Described> {
}
```

Hai interfaces có thể dùng theo mọi thứ tự hợp lệ (với các constraints về erasure/conflicts và generic signatures), nhưng **bound đầu tiên vẫn có ý nghĩa trong type erasure**, sẽ nói ở phần sau.

Tạo **`InterfaceIntersectionDemo.java`**:

```java
interface Named {
    String name();
}

interface Described {
    String description();
}

record Product(String name, String description)
        implements Named, Described {
}

class DetailView<T extends Named & Described> {
    private final T value;

    DetailView(T value) {
        this.value = value;
    }

    String render() {
        return value.name() + " - "
                + value.description();
    }
}

public class InterfaceIntersectionDemo {
    public static void main(String[] args) {
        DetailView<Product> view = new DetailView<>(
                new Product("Book", "Java"));

        System.out.println(view.render());
    }
}
```

```bash
javac InterfaceIntersectionDemo.java
java InterfaceIntersectionDemo
```

```text
Book - Java
```

`Product` là record final implement cả hai interfaces. `DetailView<T>` không cần biết concrete class Product để gọi `name()` hoặc `description()`.

**Lợi ích thiết kế:** Thay vì tạo interface ghép chỉ để dùng tại một chỗ, intersection bounds có thể diễn đạt “phải thỏa cả hai hợp đồng” ngay tại generic API. Nhưng nếu tổ hợp đó là một **khái niệm domain lặp lại**, một interface có tên như `CatalogItem extends Named, Described` có thể dễ đọc và bảo trì hơn.

## 11. Intersection bound khác việc chọn một trong hai type

`T extends A & B` có nghĩa T phải thỏa **A và B**, không phải A **hoặc** B. Java generics không có syntax union kiểu:

```java
// class Either<T extends A | B> { }
// Không có cú pháp union type parameter như vậy.
```

Nếu API chấp nhận hai loại độc lập, xem xét common interface, overloads, sealed hierarchy, hay thiết kế hai generic methods.

### Hình dung bằng bảng

| Type argument | Implements A | Implements B | Hợp lệ cho `T extends A & B` |
| --- | --- | --- | --- |
| First | Có | Có | Có |
| Second | Có | Không | Không |
| Third | Không | Có | Không |
| Fourth | Không | Không | Không |

**Tính hữu dụng:** Compiler ngăn việc tạo `DetailView<Something>` nếu Something không cung cấp đủ cả hai capabilities.

## 12. Ràng buộc không tự bảo đảm mọi method đều public

Bound cho phép truy cập những members thực sự **accessible** ở vị trí dùng generic class. Một private method của class bound **không** trở thành callable chỉ vì T extends class đó.

Ví dụ:

```java
class Base {
    public void open() {
    }

    private void secret() {
    }
}

class Wrapper<T extends Base> {
    void invoke(T value) {
        value.open();
        // value.secret(); // Lỗi: private method.
    }
}
```

Đây là khai báo hợp lệ khi dòng sai vẫn được comment.

Access modifiers của methods/fields vẫn áp dụng đầy đủ. **Bound không bỏ qua encapsulation**.

Đối với interface methods, contract thường là public; một concrete class implementing interface phải cung cấp public implementation cho methods công khai.

## 13. Type argument phải thỏa toàn bộ bound, không chỉ một phần

Với:

```java
class NumericComparable<T extends Number & Comparable<T>> {
}
```

Những đối số thường hợp lệ:

- `Integer`: extends Number, implements Comparable<Integer>.
- `Double`: extends Number, implements Comparable<Double>.
- `Long`: extends Number, implements Comparable<Long>.
- `BigDecimal`: extends Number, implements Comparable<BigDecimal>.

Những đối số không hợp lệ:

- `String`: implements Comparable<String> nhưng không extends Number.
- `Number`: là class bound nhưng **không implements Comparable<Number>**.
- Một Number subclass chỉ implement Comparable với type không phù hợp `T` có thể không đáp ứng bound này.

**Ví dụ lỗi có chủ đích:**

```java
// NumericComparable<String> first; // String không là Number.
// NumericComparable<Number> second; // Number không là Comparable<Number>.
```

Lưu ý `Number` làm bound không có nghĩa **chính Number** chắc chắn thỏa tất cả các interface bounds. Compiler kiểm type argument **theo toàn giao điểm**.

## 14. Bound trên generic method chứ không chỉ class

Một generic method có thể khai báo type parameter ngay trước return type:

```java
static <T extends Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là **mảnh method minh họa** trong một class.

`<T extends Comparable<T>>` là phần khai báo generic type parameter của method. Nó **không** là phần của return type T và không phải phép cast.

Tạo **`BoundedMethodDemo.java`**:

```java
public class BoundedMethodDemo {
    static <T extends Number & Comparable<T>>
    T larger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        System.out.println(larger(7, 3));
        System.out.println(larger(2.5, 4.0));
    }
}
```

```bash
javac BoundedMethodDemo.java
java BoundedMethodDemo
```

```text
7
4.0
```

Ở mỗi lần gọi, compiler suy ra T phù hợp từ arguments và ràng buộc. Method dùng Comparable<T>; Number bound ở ví dụ này còn biểu đạt miền kiểu numeric, dù body hiện chỉ cần compareTo. Nếu chỉ so sánh generic objects, có thể dùng một Comparable bound không kèm Number.

### Chú ý inference

Nếu truyền hai objects khác type như Integer và Double, compiler **không** tự bảo đảm sẽ tìm được cùng T thỏa `Comparable<T>` để lời gọi hợp lệ. Hãy định nghĩa rõ có chấp nhận so numeric khác types hay không. So sánh hỗn hợp có thể cần `Comparator<Number>` hoặc chuyển sang một type chung với precision policy rõ.

## 15. Static method có type parameter riêng, không dùng class-level T

Một generic class:

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    // static T twice(T input) { return input; }
    // Sai: static context không dùng class-level T.

    static <U extends Number> double twice(U input) {
        return input.doubleValue() * 2;
    }
}
```

Static method `twice` tự khai báo `U`, vì static member tồn tại ở mức class chứ không gắn riêng với mỗi `Box<Integer>` hay `Box<Double>`.

Tạo **`StaticBoundedMethodDemo.java`**:

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U extends Number> double twice(U input) {
        return input.doubleValue() * 2;
    }
}

public class StaticBoundedMethodDemo {
    public static void main(String[] args) {
        Box<Integer> box = new Box<>(5);

        System.out.println(box.get());
        System.out.println(Box.twice(2.5));
    }
}
```

```bash
javac StaticBoundedMethodDemo.java
java StaticBoundedMethodDemo
```

```text
5
5.0
```

**Hai phạm vi độc lập:** T là parameter của class; U là parameter của static generic method. Dùng cùng chữ cái cho cả hai cũng có thể tạo shadowing khó đọc, nên đặt tên tách bạch khi có giá trị.

## 16. Một lớp có nhiều type parameters với bounds khác nhau

Một class có thể nhận nhiều type arguments độc lập:

```java
class Pair<
        K extends Comparable<K>,
        V extends Number> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
```

`K` bị giới hạn bởi Comparable<K>; `V` bị giới hạn bởi Number; **không có yêu cầu K và V phải là cùng type**.

Tạo **`TwoParametersBoundDemo.java`**:

```java
class Pair<K extends Comparable<K>, V extends Number> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    boolean before(K other) {
        return key.compareTo(other) < 0;
    }

    double numericValue() {
        return value.doubleValue();
    }
}

public class TwoParametersBoundDemo {
    public static void main(String[] args) {
        Pair<String, Integer> pair = new Pair<>("A", 7);

        System.out.println(pair.before("B"));
        System.out.println(pair.numericValue());
    }
}
```

```bash
javac TwoParametersBoundDemo.java
java TwoParametersBoundDemo
```

```text
true
7.0
```

Đọc dấu phẩy như **ranh giới hai type parameters**. Khi muốn mỗi một trong hai parameters có nhiều bounds, viết `K extends A & B` và `V extends C & D` trong cùng angle brackets.

## 17. Một type parameter có thể ràng buộc bằng type parameter khác

Không nhất thiết upper bound là một class hay interface có tên cố định. Java hỗ trợ các ràng buộc phụ thuộc:

```java
class Choice<T, U extends T> {
    private final T broad;
    private final U specific;

    Choice(T broad, U specific) {
        this.broad = broad;
        this.specific = specific;
    }

    T broad() {
        return broad;
    }

    U specific() {
        return specific;
    }
}
```

`U extends T` nói rằng U phải là subtype của T. Ở đây `extends T` là một single type-variable bound, không kết hợp nhiều additional bounds phía sau theo cú pháp JLS `TypeBound` cho type variable.

Tạo **`DependentTypeParameterDemo.java`**:

```java
class Choice<T, U extends T> {
    private final T first;
    private final U second;

    Choice(T first, U second) {
        this.first = first;
        this.second = second;
    }

    T first() {
        return first;
    }

    T secondAsT() {
        return second;
    }
}

public class DependentTypeParameterDemo {
    public static void main(String[] args) {
        Choice<Number, Integer> choice =
                new Choice<>(2.5, 7);

        System.out.println(choice.first());
        System.out.println(choice.secondAsT());
    }
}
```

```bash
javac DependentTypeParameterDemo.java
java DependentTypeParameterDemo
```

```text
2.5
7
```

**Giới hạn:** Viết `<T, U extends T>` khác với việc gộp hai type parameters thành một. U giữ type riêng; compiler chỉ biết U thuộc họ T.

## 18. F-bounded polymorphism: bound tham chiếu chính T

Mẫu thường gặp:

```java
interface SelfOrdered<T extends SelfOrdered<T>> {
    int compare(T other);
}
```

Đây là dạng **recursive type bound** (*F-bounded polymorphism*). Một type argument thường có khả năng tuân theo contract parameterized bởi chính nó.

Một use case phổ biến hơn là:

```java
class SortedBox<T extends Comparable<T>> {
}
```

Nó cho compiler biết đối tượng T có compareTo(T) thay vì chỉ compareTo(Object) theo raw types.

### Không quá tải mô hình

Một recursive bound phức tạp có thể làm thông báo lỗi dài và khó hiểu. Nếu mục tiêu chỉ cần một phép so dựa trên external ordering policy, nhận `Comparator<? super T>` có thể đơn giản hơn buộc mọi loại domain implement Comparable.

## 19. Vì sao `Comparable<? super T>` đôi khi linh hoạt hơn `Comparable<T>`?

Một subclass có thể kế thừa khả năng so sánh với **supertype**, không implement `Comparable<Subclass>` trực tiếp.

Giả sử:

```java
class Person implements Comparable<Person> {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    @Override
    public int compareTo(Person other) {
        return Integer.compare(age, other.age);
    }
}

final class Student extends Person {
    Student(int age) {
        super(age);
    }
}
```

`Student` implements `Comparable<Person>` thông qua Person, không phải `Comparable<Student>`.

Bound:

```java
<T extends Comparable<T>>
```

có thể loại Student, còn:

```java
<T extends Comparable<? super T>>
```

có thể nhận Student vì Comparable<Person> chấp nhận kiểu Person, là supertype của Student.

Tạo **`ComparableSuperBoundDemo.java`**:

```java
class Person implements Comparable<Person> {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    @Override
    public int compareTo(Person other) {
        return Integer.compare(age, other.age);
    }
}

final class Student extends Person {
    Student(int age) {
        super(age);
    }
}

public class ComparableSuperBoundDemo {
    static <T extends Comparable<? super T>>
    T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Student older = larger(new Student(22),
                               new Student(19));

        System.out.println(
                older.compareTo(new Person(20)) > 0);
    }
}
```

```bash
javac ComparableSuperBoundDemo.java
java ComparableSuperBoundDemo
```

```text
true
```

**Đọc kỹ wildcard ở đây:** Bound của T vẫn bắt đầu bằng `extends Comparable<...>`, còn `? super T` nằm **bên trong type argument** của Comparable. Đây không phải cú pháp khai báo `T super Person` (Java không có dạng lower-bounded type parameter như vậy).

## 20. `T extends Number` không giống `List<? extends Number>`

Hai cách viết nhìn giống nhau nhưng giải quyết hai loại vấn đề khác:

- `<T extends Number>`: **khai báo một type parameter có tên T** và upper bound.
- `List<? extends Number>`: **sử dụng wildcard argument** với một upper bound; tên type cụ thể bị ẩn.

Ví dụ:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Bên cạnh một method:

```java
static double sum(java.util.List<? extends Number> values) {
    double total = 0;
    for (Number number : values) {
        total += number.doubleValue();
    }
    return total;
}
```

Method `sum` có thể nhận `List<Integer>` hoặc `List<Double>` và chỉ cần **đọc như Number**. Nhưng `List<? extends Number>` không cho thêm một Integer bất kỳ, vì list thực tế có thể là List<Double>.

**Nhớ rằng `List<Integer>` không phải subtype của `List<Number>`**. Java generics là invariant về type argument; wildcard cung cấp cách biểu diễn variance ở call sites.

## 21. Chương trình: named bound và upper-bounded wildcard

Tạo **`NamedBoundVersusWildcardDemo.java`**:

```java
import java.util.List;

public class NamedBoundVersusWildcardDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(sum(List.of(1, 2, 3)));
        System.out.println(sum(List.of(1.5, 2.5)));
    }
}
```

```bash
javac NamedBoundVersusWildcardDemo.java
java NamedBoundVersusWildcardDemo
```

```text
6.0
6.0
4.0
```

`twice` cần một type parameter T có thể dùng ở nhiều vị trí trong signature. `sum` chỉ cần đọc mỗi element như Number, nên wildcard thuận tiện.

**Không dùng named T máy móc** khi method chỉ cần one-off wildcard. Ngược lại, khi cần liên kết kiểu giữa parameters/return type, named type parameter có thể cần thiết.

## 22. `? super` là lower bound của wildcard, không khai báo T

Java cho phép:

```java
java.util.List<? super Integer> destination;
```

Nó có thể tham chiếu List<Integer>, List<Number> hay List<Object>. Ta **có thể thêm Integer** vào list đó; đọc ra chỉ bảo đảm được Object.

Không thể khai báo:

```java
// class Wrong<T super Integer> { }
// Sai: type parameter declarations không dùng super.
```

Tạo **`WildcardSuperDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardSuperDemo {
    static void addNumbers(List<? super Integer> values) {
        values.add(2);
        values.add(3);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        addNumbers(numbers);

        System.out.println(numbers);
        System.out.println(numbers.get(0) instanceof Integer);
    }
}
```

```bash
javac WildcardSuperDemo.java
java WildcardSuperDemo
```

```text
[2, 3]
true
```

**PECS:** “Producer Extends, Consumer Super” là một mẹo về wildcards: nguồn chỉ đọc từ họ T dùng `? extends T`; đích nhận T dùng `? super T`. Đây **không phải thay thế** việc xác định type parameters của generic class.

## 23. Bounded class generic không làm các parameterizations có quan hệ kế thừa

Ví dụ:

```java
class NumberBox<T extends Number> {
    T value;

    NumberBox(T value) {
        this.value = value;
    }
}
```

`Integer` là subtype của `Number`, nhưng `NumberBox<Integer>` **không phải** subtype của `NumberBox<Number>`.

Điều này quan trọng vì generic classes **invariant** đối với type arguments, dù type parameter bị giới hạn.

**Mã cố tình sai:**

```java
NumberBox<Integer> integers = new NumberBox<>(1);
// NumberBox<Number> numbers = integers; // Sai.
```

Muốn viết API nhận mọi hộp với type argument thuộc Number, cân nhắc:

```java
static void inspect(NumberBox<? extends Number> box) {
    System.out.println(box.value.doubleValue());
}
```

Đây là **mảnh method minh họa** khi lớp NumberBox và quyền truy cập field phù hợp trong cùng ngữ cảnh. Ở một API thực tế, nên dùng getter thay vì truy cập package-private field.

**Tóm lại:** Type parameter bound hạn chế type arguments; wildcard quyết định cách **một parameterized type** có thể được dùng linh hoạt tại call site.

## 24. Type erasure: bound đầu tiên ảnh hưởng bytecode

Java generics phần lớn được hiện thực bằng **type erasure**. Một type variable khi erased được thay bằng **erasure của leftmost bound**:

- `T` không có bound tường minh → erased về `Object`.
- `T extends Number` → erased về `Number`.
- `T extends Number & Comparable<T>` → erased về `Number`.
- `T extends Named & Described` → erased về `Named` nếu Named đứng đầu.

Khi cần dùng members từ các bounds phía sau, compiler có thể phát sinh casts/bridge methods hoặc bytecode cần thiết để duy trì đúng ngữ nghĩa.

**Quan trọng:** Multiple bounds không làm runtime JVM tự tạo một class “NumberAndComparable” riêng. Đây là **intersection constraint ở compile time**.

Thứ tự interfaces sau bound đầu tiên không thay đổi ý nghĩa bắt buộc “thỏa tất cả”, nhưng có thể ảnh hưởng **erased signature** nếu một interface khác trở thành leftmost bound. Đừng sắp xếp lại bounds công khai tùy tiện mà không xét binary/API compatibility.

## 25. Reflection minh họa erasure của bound đầu tiên

Tạo **`BoundErasureReflectionDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.TypeVariable;

class NumberHolder<T extends Number & Comparable<T>> {
    T value;
}

public class BoundErasureReflectionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field =
                NumberHolder.class.getDeclaredField("value");
        TypeVariable<?> parameter =
                NumberHolder.class.getTypeParameters()[0];

        System.out.println(field.getType() == Number.class);
        System.out.println(parameter.getBounds().length);
        System.out.println(
                parameter.getBounds()[0] == Number.class);
    }
}
```

```bash
javac BoundErasureReflectionDemo.java
java BoundErasureReflectionDemo
```

```text
true
2
true
```

- Field declared với type variable T có runtime raw field type `Number` khi quan sát qua `Field.getType()`.
- Reflection vẫn có thể đọc generic declaration bằng `getTypeParameters/getBounds`.
- Hai bounds tồn tại trong generic metadata: Number và Comparable<T>, nhưng erased field type là leftmost Number.

Không nhầm giữa **runtime erasure** và **generic type checking lúc biên dịch**. Compiler vẫn kiểm `NumberHolder<String>` sai dù runtime metadata của field không lưu mỗi concrete type argument.

## 26. Thứ tự bounds có thể ảnh hưởng method overloading sau erasure

Nhìn hai methods sau:

```java
class ErasureClash {
    <T extends Number> void process(T value) {
    }

    // void process(Number value) {
    // }
}
```

Đây là **đoạn minh họa**: nếu bỏ comment của method thứ hai, hai signatures clash sau erasure, vì method generic đầu tiên erase parameter T thành Number.

**Không giải quyết bằng đổi tên T thành U**. Erasure dựa trên bounds và signatures, không dựa tên type parameter.

### Cách sửa

- Dùng tên method khác nhau khi hai operations có semantics khác.
- Hoặc chọn thiết kế chỉ một overload hợp lệ.
- Tránh tạo generic method chỉ vì “trông linh hoạt” khi signature erased chồng với method cần có.

**Nguyên tắc review:** Với public APIs, các bounds có thể ảnh hưởng overloaded methods, bridge methods và compatibility; không chỉ giới hạn tại source level.

## 27. `new T()` vẫn không hợp lệ dù T có class bound

Ngay cả khi:

```java
class Factory<T extends Number> {
    // T create() {
    //     return new T(); // Sai.
    // }
}
```

compiler không biết constructor nào của một concrete T và erasure không giữ kiểu khởi tạo cần thiết. Bound **không** tạo ra constructor guarantee.

### Cách làm với `Supplier<T>`

Tạo **`BoundedFactoryDemo.java`**:

```java
import java.util.Objects;
import java.util.function.Supplier;

class Factory<T extends Number> {
    private final Supplier<? extends T> creator;

    Factory(Supplier<? extends T> creator) {
        this.creator = Objects.requireNonNull(creator);
    }

    T create() {
        return creator.get();
    }
}

public class BoundedFactoryDemo {
    public static void main(String[] args) {
        Factory<Integer> factory = new Factory<>(() -> 7);

        System.out.println(factory.create());
    }
}
```

```bash
javac BoundedFactoryDemo.java
java BoundedFactoryDemo
```

```text
7
```

`Supplier<? extends T>` biểu diễn một nguồn trả T hoặc subtype của T. Điều kiện `T extends Number` vẫn được giữ; factory không cần reflection hoặc giả định constructor không tham số.

## 28. `instanceof T` cũng không là một phép kiểm runtime khả dụng

Mã sau **cố tình sai**:

```java
class Tester<T extends Number> {
    boolean accepts(Object value) {
        // return value instanceof T; // Sai: T không reifiable.
        return value instanceof Number;
    }
}
```

`value instanceof Number` hợp lệ vì Number là class type tồn tại runtime, nhưng nó chỉ kiểm **Number**, không phân biệt `T=Integer` hay `T=Double`.

### Khi cần kiểm đúng T tại runtime

Một thiết kế là nhận `Class<T>` token:

Tạo **`RuntimeTypeTokenDemo.java`**:

```java
import java.util.Objects;

class TypedBox<T extends Number> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = Objects.requireNonNull(type);
    }

    boolean accepts(Object candidate) {
        return type.isInstance(candidate);
    }
}

public class RuntimeTypeTokenDemo {
    public static void main(String[] args) {
        TypedBox<Integer> box = new TypedBox<>(Integer.class);

        System.out.println(box.accepts(5));
        System.out.println(box.accepts(5.0));
    }
}
```

```bash
javac RuntimeTypeTokenDemo.java
java RuntimeTypeTokenDemo
```

```text
true
false
```

Class token phù hợp khi T là một reifiable class type như Integer. Nó không giải quyết đầy đủ việc kiểm `List<String>` vs `List<Integer>` tại runtime do type erasure của nested generic arguments.

## 29. Array creation với T vẫn bị giới hạn

Mã sai:

```java
class ArrayFactory<T extends Number> {
    // T[] create(int size) {
    //     return new T[size]; // Sai: generic array creation.
    // }
}
```

Bound không biến T thành một reifiable runtime array component type. Có thể dùng `IntFunction<T[]>` do caller cung cấp, hoặc reflection có kiểm soát.

Tạo **`BoundedArrayFactoryDemo.java`**:

```java
import java.util.function.IntFunction;

class ArrayFactory<T extends Number> {
    private final IntFunction<T[]> maker;

    ArrayFactory(IntFunction<T[]> maker) {
        this.maker = maker;
    }

    T[] create(int size) {
        return maker.apply(size);
    }
}

public class BoundedArrayFactoryDemo {
    public static void main(String[] args) {
        ArrayFactory<Integer> factory =
                new ArrayFactory<>(Integer[]::new);

        Integer[] values = factory.create(3);

        System.out.println(values.length);
        System.out.println(
                values.getClass().getComponentType()
                        == Integer.class);
    }
}
```

```bash
javac BoundedArrayFactoryDemo.java
java BoundedArrayFactoryDemo
```

```text
3
true
```

Method reference `Integer[]::new` mang thông tin runtime array component type, trong khi `new T[size]` không hợp lệ.

## 30. Primitive không thể làm trực tiếp generic type argument

Mã sai:

```java
// NumberBox<int> box;
// Generic arguments không nhận primitive int.
```

Dùng wrapper `Integer`:

```java
NumberBox<Integer> box = new NumberBox<>(5);
```

Đoạn này là mảnh minh họa trong scope có NumberBox đã khai báo. Autoboxing giúp chuyển primitive `5` thành Integer.

**Giới hạn của bound:** `Integer extends Number` đáp ứng upper bound, nhưng `int` vẫn không được trực tiếp làm type argument. Generic type arguments là reference types.

## 31. Có thể có bounds rỗng về mặt thực tiễn dù cú pháp hợp lệ

Một declaration hợp lệ về cú pháp có thể quá hẹp khiến hầu như không có concrete type thỏa toàn bộ constraints.

Ví dụ:

```java
class Strange<T extends Number & Runnable> {
}
```

Khai báo nhiều bound class+interface này hợp lệ về cấu trúc, nhưng các wrapper numeric tiêu chuẩn như Integer/Double không implements Runnable. API có thể không có type argument hữu ích trong domain.

**Không nói compiler tự tạo implementation cho thiếu capability.** Một candidate type phải thật sự là subtype của tất cả bounds.

### Dùng các interfaces có chủ đích

Nếu chỉ muốn số có thể convert ra double, `T extends Number` là đủ. Nếu còn cần ordering, bổ sung Comparable bound. Nếu cần auditing, bổ sung interface Auditable. **Mỗi bound nên diễn tả một yêu cầu sử dụng thực tế**, không phải trang trí.

## 32. Hai interface bounds có thể xung đột với nhau

Compiler không chấp nhận một type variable buộc trở thành subtype của hai parameterizations không tương thích của **cùng generic interface**.

Mã **cố tình sai**:

```java
// class Bad<T extends Comparable<String>
//             & Comparable<Integer>> {
// }
```

Cùng generic interface `Comparable` xuất hiện với các type arguments khác nhau, dẫn đến xung đột erasure và contract.

Tương tự, không thể liệt kê trùng các interface bounds mà compiler thấy chúng có cùng erasure.

### Hướng xử lý

- Chọn **một Comparable contract** thống nhất.
- Hoặc nhận `Comparator` bên ngoài cho policy so sánh.
- Nếu domain thật sự có hai phép so khác nhau, tạo **hai interfaces có tên khác nhau** và methods khác tên.

Không thể “buộc compiler chấp nhận” bằng raw types hoặc unchecked casts mà vẫn giữ type safety.

## 33. Một bound được thỏa trực tiếp hoặc gián tiếp

Nếu class `Employee` extends `PersonBase` và `PersonBase` implements `Named`, thì Employee vẫn là subtype của Named dù không viết `implements Named` ngay tại declaration Employee.

Bound kiểm **quan hệ subtype**, không yêu cầu text trong class declaration phải chứa trực tiếp tên mỗi interface.

Tạo **`InheritedInterfaceBoundDemo.java`**:

```java
interface Named {
    String name();
}

class PersonBase implements Named {
    private final String name;

    PersonBase(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

final class Employee extends PersonBase {
    Employee(String name) {
        super(name);
    }
}

class NameBox<T extends Named> {
    private final T value;

    NameBox(T value) {
        this.value = value;
    }

    String show() {
        return value.name();
    }
}

public class InheritedInterfaceBoundDemo {
    public static void main(String[] args) {
        NameBox<Employee> box =
                new NameBox<>(new Employee("Lan"));

        System.out.println(box.show());
    }
}
```

```bash
javac InheritedInterfaceBoundDemo.java
java InheritedInterfaceBoundDemo
```

```text
Lan
```

`Employee` thỏa Named thông qua superclass PersonBase. Đây là quan hệ kế thừa thông thường; type argument không cần implement interface **trực tiếp** trong cùng source line.

## 34. Bounds không phải runtime validation của từng instance

Ngay cả khi `T extends Number`, code có thể truyền `null` tại runtime:

```java
NumberBox<Integer> box = new NumberBox<>(null);
```

Đây là một câu lệnh hợp lệ nếu NumberBox constructor không cấm null. Sau đó gọi `box.twice()` có thể ném `NullPointerException` vì truy cập method trên null.

**Bound không đảm bảo non-null.** Khi domain cấm null, dùng `Objects.requireNonNull(value)` ở constructor.

Tương tự, một Number object có thể chứa NaN/Infinity nếu kiểu và giá trị cho phép. `T extends Number & Comparable<T>` không xác nhận precision, range hay business invariants.

### Kiểu dữ liệu và validation có nhiệm vụ khác nhau

- Bound → **kiểu nào có thể được dùng**.
- Constructor validation → **giá trị nào hợp lệ**.
- Immutability/copying → **state có thể đổi từ đâu**.
- Domain methods → **logic nghiệp vụ**.

Đừng thay validation bằng một generic bound quá chung.

## 35. Khi nào chỉ cần interface bound?

Nếu API chỉ gọi `name()`, dùng:

```java
interface Named {
    String name();
}

class NamePrinter<T extends Named> {
    void print(T value) {
        System.out.println(value.name());
    }
}
```

Thay vì đòi `T extends SomeBaseClass & Named` khi SomeBaseClass không phục vụ gì, interface bound nhẹ hơn, cho phép các implementations là records/final classes hoặc subclasses của superclass khác.

**Lợi ích về API:** Interface hướng tới capability, tránh khóa class inheritance tree của người dùng. Trong Java, class chỉ có một superclass, nên thêm một class bound vào API public có thể hạn chế clients đáng kể.

## 36. Khi nào nhiều bounds có ích hơn tạo một interface mới?

Giả sử helper chỉ hoạt động với objects vừa `Named` vừa `Timed`. Nếu yêu cầu chỉ xuất hiện tại một vài generic methods, viết:

```java
static <T extends Named & Timed> String label(T value) {
    return value.name() + ":" + value.time();
}
```

Đây là **mảnh code minh họa**, cần các interfaces `Named` và `Timed` trong ứng dụng.

Nếu rất nhiều APIs cùng cần tổ hợp ấy, có thể định nghĩa:

```java
interface TimedNamed extends Named, Timed {
}
```

Sau đó dùng `T extends TimedNamed`.

**Lưu ý về thiết kế:** Hai approaches không hoàn toàn thay thế về tập type arguments. `T extends Named & Timed` chấp nhận bất kỳ class implement cả Named và Timed, **không cần** khai báo implements TimedNamed. Ngược lại, `T extends TimedNamed` chỉ chấp nhận types thuộc interface TimedNamed. Chọn theo ý nghĩa contract và khả năng áp dụng.

## 37. Multiple bounds và dependency vào implementations của thư viện khác

Giả sử library công bố:

```java
class Handler<T extends FrameworkBase & PluginCapability> {
}
```

Đây là **mẫu minh họa** với FrameworkBase là class, PluginCapability là interface.

Nó yêu cầu plugin objects phải vừa extends FrameworkBase vừa implement PluginCapability. Điều này có thể làm khó client nếu plugin class đã cần extends một superclass khác.

Một cách ít ràng buộc hơn:

```java
class Handler<T extends PluginCapability> {
}
```

hoặc một non-generic interface parameter nếu không cần liên hệ return type.

**Quy tắc API design:** Không thêm class bound chỉ để sử dụng một method tiện lợi của class ấy nếu interface có thể biểu diễn đúng capability và giúp API linh hoạt hơn.

## 38. Ràng buộc quá mạnh có thể khiến type inference thất bại

Giả sử method yêu cầu:

```java
static <T extends Number & Comparable<T>>
T min(T first, T second) {
    return first.compareTo(second) <= 0 ? first : second;
}
```

`min(1,2)` hợp lệ vì cả hai Integer. `min(1.5,2.0)` hợp lệ vì cả hai Double. Nhưng lời gọi `min(1,2.0)` không thể giả định compiler sẽ tự chọn một common T có đầy đủ các ràng buộc; type inference có thể báo lỗi.

**Không giải quyết bằng raw type cast** để né type safety. Nếu business cần hỗn hợp numeric types, chọn một representation chung và conversion policy cụ thể:

- Convert sang `BigDecimal` nếu cần decimal semantics phù hợp và đầu vào có quy tắc chuyển đổi.
- Dùng `double` nếu chấp nhận mất precision và đặc biệt NaN/Infinity.
- Nhận `Comparator` và kiểu dữ liệu domain cố định nếu ordering không tự nhiên.

Generic bounds chỉ nói **một type đáp ứng hợp đồng**, không thực hiện numeric promotion giống biểu thức arithmetic primitive cho mọi trường hợp.

## 39. Generic method có `Comparator<? super T>` thay cho Comparable bound

Khi type không có natural ordering, caller có thể cung cấp so sánh.

Tạo **`ComparatorAlternativeDemo.java`**:

```java
import java.util.Comparator;

record Task(String title, int priority) {
}

public class ComparatorAlternativeDemo {
    static <T> T larger(T a, T b,
                         Comparator<? super T> comparator) {
        return comparator.compare(a, b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);

        Task result = larger(
                new Task("A", 2),
                new Task("B", 5),
                byPriority);

        System.out.println(result.title());
    }
}
```

```bash
javac ComparatorAlternativeDemo.java
java ComparatorAlternativeDemo
```

```text
B
```

`Task` không implements Comparable. Method `larger` vẫn hoạt động vì caller cấp Comparator<? super T>. Type parameter T **không cần extends Comparable<T>**.

**So sánh thiết kế:**

- `Comparable` bound: yêu cầu **natural order** được định nghĩa trên type.
- `Comparator` parameter: cho phép **nhiều order policies** bên ngoài type.
- Với nhiều views/orderings, Comparator có thể rõ hơn và tránh buộc domain classes implement interface không cần thiết.

## 40. Bounded generic constructor cũng tồn tại

Không chỉ class/method mới có type parameters; constructor có thể khai báo generic parameter riêng.

Tạo **`GenericConstructorDemo.java`**:

```java
class Reading {
    private final double number;

    <T extends Number> Reading(T number) {
        this.number = number.doubleValue();
    }

    double number() {
        return number;
    }
}

public class GenericConstructorDemo {
    public static void main(String[] args) {
        Reading a = new Reading(5);
        Reading b = new Reading(2.5);

        System.out.println(a.number());
        System.out.println(b.number());
    }
}
```

```bash
javac GenericConstructorDemo.java
java GenericConstructorDemo
```

```text
5.0
2.5
```

Constructor `<T extends Number> Reading(T number)` có type parameter T riêng. Bản thân class Reading **không phải generic**. Đây là cơ chế hữu ích nếu chỉ operation khởi tạo cần giới hạn type; không nhất thiết biến toàn bộ class thành `Reading<T>`.

## 41. Type-variable bounds và boxing ở call site

Java generic classes không nhận primitive type arguments:

```java
// NumberBox<int> invalid; // Sai.
NumberBox<Integer> valid = new NumberBox<>(7);
```

Trong chương trình, autoboxing cho phép biểu thức int `7` được đóng hộp thành Integer khi truyền tới constructor nhận T = Integer.

**Không suy ra rằng generic T trở thành primitive ở runtime.** Generics vẫn dùng reference types và có type erasure, mặc dù compiler có thể hỗ trợ boxing/unboxing tại call site.

Nếu xử lý nhiều số lượng primitive với hiệu năng quan trọng, cân nhắc primitive-specialized APIs như `IntStream` hoặc các collections chuyên biệt, không mong bounded generics tự tránh boxing.

## 42. Type parameter tự tham chiếu và lớp con: cẩn thận với semantics

Mẫu:

```java
class Base<T extends Base<T>> {
    T self() {
        throw new UnsupportedOperationException();
    }
}
```

là một self-referential bound hợp lệ về cú pháp. Nó diễn đạt một hạn chế về type relationship, nhưng không tự đảm bảo mọi subclass sẽ “khai báo chính mình” theo cách lý tưởng, nếu người viết cố ý chọn type argument khác vẫn thỏa bound.

Khi xây public APIs, đừng dùng F-bounded generics như một phép chứng minh runtime rằng `T` đúng bằng actual subclass. Nó là một static relation, không phải type token hay reflection proof.

**Hướng dùng có trách nhiệm:** Chỉ chọn recursive bound khi nó thực sự làm fluent builder/comparison API type-safe hơn và tests đảm bảo class-specific behavior.

## 43. Intersection bounds có thể xuất hiện cùng wildcard

Ví dụ:

```java
class Summary<T extends Number & Comparable<T>> {
    // ...
}
```

Ở nơi nhận generic instances, vẫn có thể dùng wildcard phù hợp:

```java
static void show(Summary<?> summary) {
    // T bị ẩn tại call site, nhưng T vẫn bị bound ở declaration.
}
```

Đây là **các mảnh minh họa**, class Summary phải được khai báo đầy đủ khi chạy.

Wildcard không bỏ những ràng buộc đã định nghĩa trên T: `Summary<String>` vẫn không hợp lệ. Nhưng từ phía method nhận `Summary<?>`, việc không biết chính xác T làm giảm những operations type-safe có thể thực hiện với T.

**Chốt:** Bound kiểm các type arguments ngay tại generic declaration; wildcard điều khiển cách sử dụng parameterized types tại call site. Hai cơ chế phối hợp, không thay thế nhau.

## 44. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `class C<T implements Runnable>` | Type parameter bound dùng `extends` | `T extends Runnable` |
| `T extends A, B` | Dấu phẩy ngăn type parameters | `T extends A & B` |
| `T extends Runnable & Number` | Class bound Number ở vị trí sau | `T extends Number & Runnable` |
| `T extends ClassA & ClassB` | Không thể có class thứ hai sau `&` | Một class trước, thêm interfaces |
| `T super Number` | Không có lower-bound type parameter | `? super Number` cho wildcard tại vị trí phù hợp |
| `NumberBox<String>` | String không subtype của Number | Dùng đúng type argument |
| `NumericComparable<Number>` | Number không implements Comparable<Number> | Dùng Integer/Double hoặc đổi bound |
| `new T()` | T bị erased và không biết constructor | `Supplier<T>` hoặc factory |
| `new T[10]` | Không thể tạo generic array trực tiếp | `IntFunction<T[]>` hoặc reflection có kiểm soát |
| `x instanceof T` | T không reifiable | Dùng runtime type token |
| `static T method(...)` với class-level T | Static không gắn với parameterization | Tạo `static <U extends ...>` |
| Mong List<Integer> gán vào List<Number> | Generics invariant | Dùng wildcard/API phù hợp |
| Coi `? extends Number` giống `T extends Number` | Wildcard và type parameter khác vai trò | Chọn theo nhu cầu liên hệ types |
| Chỉ cần Number methods mà thêm Comparable | Giới hạn thừa làm API kém linh hoạt | Bound tối thiểu |
| Multiple bounds với conflicting generic interfaces | Erasure/generic contract xung đột | Dùng một contract phù hợp |
| Đổi leftmost bound tùy tiện | Có thể thay erased signature | Kiểm compatibility |
| Dùng raw type để né bound | Mất kiểm tra compile time/unchecked warnings | Giữ parameterized types |
| Bound Number tự validate value | Bound chỉ kiểm type | Validate null/range/domain |
| Bound Comparable<T> khi subclass so theo parent | Quá chặt so với cần thiết | Cân nhắc Comparable<? super T> |
| Muốn hỗn hợp Integer và Double tự compare | Không có cùng T phù hợp đơn giản | Chọn conversion/comparator policy |
| Dùng class bound khi interface là đủ | Khóa superclass của client | Interface capability nhỏ |
| Coi erasure làm mất mọi compile-time safety | Compiler vẫn kiểm generic declarations/usages | Phân biệt compile time và runtime |

## 45. Self-test: kiểm một generic type có multiple bounds

Tạo **`MultipleBoundsSelfTest.java`**:

```java
class Range<T extends Number & Comparable<T>> {
    private final T low;
    private final T high;

    Range(T low, T high) {
        if (low.compareTo(high) > 0) {
            throw new IllegalArgumentException("invalid");
        }
        this.low = low;
        this.high = high;
    }

    boolean contains(T value) {
        return low.compareTo(value) <= 0
                && value.compareTo(high) <= 0;
    }

    double width() {
        return high.doubleValue() - low.doubleValue();
    }
}

public class MultipleBoundsSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Range<Integer> a = new Range<>(2, 8);
        Range<Double> b = new Range<>(1.5, 4.0);

        check(a.contains(5), "integer in range");
        check(!a.contains(9), "integer out of range");
        check(b.contains(2.5), "double in range");
        check(b.width() == 2.5, "width");

        boolean invalid = false;
        try {
            new Range<>(5, 2);
        } catch (IllegalArgumentException ex) {
            invalid = true;
        }
        check(invalid, "constructor validation");

        System.out.println("multiple bounds PASS");
    }
}
```

```bash
javac MultipleBoundsSelfTest.java
java MultipleBoundsSelfTest
```

```text
multiple bounds PASS
```

`check` ném AssertionError trực tiếp khi false, không cần bật JVM `-ea`. Test sử dụng giá trị Double 2.5 biểu diễn nhị phân chính xác để không mang đến bẫy rounding trong so sánh của ví dụ.

**Kiểm bổ sung nên có:** null policy, NaN/Infinity với Double, các type arguments khác, benchmark nếu conversion doubleValue có quan trọng, và kiểm những methods cần interface capabilities riêng.

## 46. Bài tập 1: thêm một interface bound

Yêu cầu: một `Report<T>` chỉ chấp nhận type vừa có `title()` vừa có `score()`. Không có superclass chung.

### Lời giải tham khảo chạy được

Tạo **`ReportIntersectionExercise.java`**:

```java
interface Titled {
    String title();
}

interface Scored {
    int score();
}

record Exam(String title, int score)
        implements Titled, Scored {
}

class Report<T extends Titled & Scored> {
    private final T value;

    Report(T value) {
        this.value = value;
    }

    String summary() {
        return value.title() + ":" + value.score();
    }
}

public class ReportIntersectionExercise {
    public static void main(String[] args) {
        Report<Exam> report =
                new Report<>(new Exam("Java", 9));

        System.out.println(report.summary());
    }
}
```

```bash
javac ReportIntersectionExercise.java
java ReportIntersectionExercise
```

```text
Java:9
```

**Giải thích:** Exam implements hai interfaces. Report không cần biết cụ thể Exam mà vẫn gọi members được bảo đảm từ intersection bound.

Nếu một class chỉ implements Titled mà không Scored, `Report<ThatClass>` không biên dịch.

## 47. Bài tập 2: tìm lỗi trong ba declarations

Xét các dòng **cố tình sai**:

```java
// class A<T implements Runnable> {}
// class B<T extends Runnable & Number> {}
// class C<T extends Number, Comparable<T>> {}
```

Sửa:

```java
class A<T extends Runnable> {}

class B<T extends Number & Runnable> {}

class C<T extends Number & Comparable<T>> {}
```

Ba declarations sau **hợp lệ về cú pháp**; việc tạo type argument cụ thể vẫn phải đáp ứng từng bound.

**Lý do:** Type parameter dùng extends; nếu có class bound thì đứng trước; nhiều bounds của một T nối bằng `&`, không phải `,`.

## 48. Bài tập 3: lựa chọn bound tối thiểu

Một class chỉ cần method `close()`. Các lựa chọn:

```java
class A<T extends java.io.Closeable> {}
class B<T extends java.io.Closeable
        & java.io.Serializable> {}
```

Nếu không lưu object bằng Java serialization hoặc không có contract cần Serializable, **A thường tốt hơn**: ít constraints và nhận nhiều type arguments hơn.

Nhưng nếu serialization là yêu cầu quan trọng của API (và được thiết kế/test đầy đủ), B có thể hợp lý. Marker interface chỉ là một phần điều kiện; không bảo đảm serialize toàn bộ nested state thành công.

## 49. Bài tập 4: xử lý một subtype có Comparable của parent

Có `Person implements Comparable<Person>` và `Student extends Person`. Bound `<T extends Comparable<T>>` có thể không nhận Student. Cách diễn đạt linh hoạt hơn là:

```java
<T extends Comparable<? super T>>
```

**Tại sao?** Comparable<Person> vẫn nhận Student khi gọi compareTo vì Student là subtype của Person. Wildcard lower bound nằm trong argument của Comparable, không phải là lower-bound syntax cho chính T.

## 50. Checklist rà soát generic bounds

- [ ] API có thật sự cần bound hay `T` không bound là đủ?
- [ ] Bound là **class** hay **interface** và đã dùng `extends` đúng chỗ?
- [ ] Nếu nhiều bounds, đã dùng `&`?
- [ ] Nếu có class bound, class ở **đầu tiên**, phía sau chỉ interfaces?
- [ ] Không có hai class bounds hoặc các generic interfaces xung đột?
- [ ] Type arguments mẫu có thỏa **toàn bộ** constraints?
- [ ] Compiler có thể gọi đúng methods được bảo đảm từ bounds?
- [ ] Methods private/protected có được truy cập đúng Java access rules?
- [ ] Có hiểu bound không tự validate `null` hay miền giá trị?
- [ ] Không mong `new T()`, `new T[]` hay `instanceof T` hoạt động?
- [ ] Nếu cần runtime type, đã xem xét `Class<T>` hoặc factory?
- [ ] Nếu cần arrays, đã nghĩ đến `IntFunction<T[]>`?
- [ ] Nếu static generic method, đã khai báo **type parameter riêng**?
- [ ] Nếu method chỉ đọc collection, đã cân nhắc wildcard `? extends`?
- [ ] Nếu method chỉ ghi collection, đã cân nhắc `? super`?
- [ ] Có hiểu `List<Integer>` không phải subtype `List<Number>`?
- [ ] Bound `Comparable<T>` có quá chặt so với `Comparable<? super T>`?
- [ ] Nếu ordering là strategy thay đổi được, có nên nhận `Comparator<? super T>`?
- [ ] Thứ tự bound đầu tiên có ảnh hưởng erased signature không?
- [ ] Có nguy cơ method signature clash sau erasure không?
- [ ] Mỗi additional bound có thật sự phục vụ một capability cần thiết?
- [ ] API có bị khóa vào superclass quá cụ thể không?
- [ ] Có type argument hợp lệ thực tế, không tạo constraints vô ích?
- [ ] Có unit tests cho cả type relationships và runtime invariants?
- [ ] Code đầy đủ có file name/public class đúng, lệnh `javac`/`java` và stdout ổn định?

## 51. Câu hỏi ôn tập có đáp án

**1.** `<T extends Number>` giới hạn điều gì?

*Chỉ cho phép type arguments là subtypes của Number; trong thân generic có thể dùng accessible members của Number.*

**2.** Có thể viết `<T implements Runnable>` không?

*Không. Type parameter bound phải dùng extends, dù bound là interface.*

**3.** Nhiều bounds của cùng T nối bằng dấu gì?

*Dấu `&`.*

**4.** Nếu có class bound và interface bounds thì thứ tự?

*Class bound phải đứng đầu; các bounds còn lại phải là interfaces.*

**5.** Có thể `T extends ClassA & ClassB` với hai classes không?

*Không.*

**6.** `T extends A & B` có nghĩa A hoặc B?

*Không; phải thỏa cả hai.*

**7.** Vì sao `NumberBox<String>` sai?

*String không subtype của Number.*

**8.** Vì sao `NumberBox<Integer>` đúng?

*Integer extends Number.*

**9.** `NumericComparable<Number>` có chắc hợp lệ không?

*Không; Number không implements Comparable<Number>.*

**10.** `T extends Comparable<T>` cho phép gọi method gì?

*`compareTo(T)` theo interface contract và access rules.*

**11.** Có thể có nhiều type parameters với bounds khác nhau không?

*Có, ví dụ `<K extends Comparable<K>, V extends Number>`.*

**12.** Bound được khai báo ở generic method có cú pháp thế nào?

*`<T extends Bound> ReturnType method(T value)`.*

**13.** Static method có dùng T của generic class trực tiếp được không?

*Không. Static generic method phải khai báo type parameter riêng nếu cần.*

**14.** Bounded T có thể `new T()` không?

*Không.*

**15.** `instanceof T` có hợp lệ không?

*Không, vì type variable T không reifiable.*

**16.** `new T[10]` có hợp lệ không?

*Không; cần array factory hoặc một cách thiết kế khác.*

**17.** `T extends Number` và `? extends Number` khác gì?

*T khai báo named type parameter; wildcard biểu diễn unknown type argument ở usage site.*

**18.** `List<Integer>` có phải subtype của `List<Number>`?

*Không, do generic invariance.*

**19.** `? super Integer` được dùng cho việc gì?

*Wildcard lower bound, thuận tiện khi cần consumer nhận Integer.*

**20.** Có thể khai báo `<T super Integer>` không?

*Không.*

**21.** Erasure của `T extends Number & Comparable<T>` là gì?

*Number, leftmost bound.*

**22.** Erasure của T không có bound tường minh?

*Object.*

**23.** Đổi thứ tự interface bounds có thể ảnh hưởng điều gì?

*Leftmost erasure và binary signatures, ngoài các ràng buộc nguồn.*

**24.** Một class implementing hai interfaces qua superclass có thỏa intersection bound không?

*Có nếu thực sự là subtype của cả hai.*

**25.** `Comparable<? super T>` hữu ích khi nào?

*Khi T có thể được so bằng Comparable của một supertype, ví dụ Student kế thừa Comparable<Person>.*

**26.** Dùng `Comparator<? super T>` khi nào?

*Khi thứ tự do caller định nghĩa, không muốn bắt type có Comparable.*

**27.** Bound có chặn null không?

*Không; constructor/logic phải validate.*

**28.** Bound có bảo đảm một Number dương không?

*Không, bound chỉ kiểm type.*

**29.** Có cần Serializable bound chỉ để gọi name() không?

*Không; Named interface là đủ.*

**30.** Mục tiêu lớn nhất của multiple bounds là gì?

*Bảo đảm một type argument đồng thời đáp ứng nhiều capabilities ở compile time, để generic implementation gọi members an toàn mà không cast.*

## 52. Tài liệu tham khảo tiêu chuẩn

- *Java Language Specification, Java SE 17, `4.4 Type Variables`*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4 — định nghĩa bound, multiple bound, canonical grammar, members của type variable.
- *Java Language Specification, Java SE 17, `4.6 Type Erasure`*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6 — leftmost bound quyết định erasure.
- *Oracle Java Tutorials, Bounded Type Parameters:* https://docs.oracle.com/javase/tutorial/java/generics/bounded.html — ví dụ cơ bản về extends/multiple bounds (hướng dẫn cũ, kiểm JLS Java 17 cho chi tiết phiên bản).

---

**Ghi nhớ cuối bài:** Với generic class/method, **`<T extends Bound>`** buộc type argument đáp ứng **upper bound** và cho compiler biết những members có thể dùng trên T. Nếu một T phải đáp ứng nhiều hợp đồng, dùng **`T extends ClassBound & InterfaceA & InterfaceB`**: mọi điều kiện đều phải đúng, **class bound đứng đầu** nếu có, các additional bounds là interfaces. Dấu `&` nối bounds của một parameter; dấu `,` phân tách nhiều type parameters. Bounds không tự tạo object, không bảo đảm giá trị hợp lệ, không làm generics covariant và vẫn chịu **type erasure**, trong đó **leftmost bound** quyết định erased type. Phân biệt **named type parameter `T extends`** với wildcard **`? extends`/`? super`** ở nơi sử dụng, và chỉ áp đặt những bounds thực sự cần cho API để giữ type safety mà không giới hạn người dùng quá mức.