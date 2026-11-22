# Giới hạn bằng lớp hoặc giao diện trong Java Generics

Trong Java Generics, một type parameter không có giới hạn tường minh như `<T>` có thể đại diện cho nhiều reference types khác nhau. Điều đó giúp tái sử dụng mã, nhưng compiler chỉ bảo đảm những thao tác có trên kiểu `Object`. Nếu thuật toán phải gọi `doubleValue()`, `compareTo()`, `run()` hoặc một phương thức thuộc interface cụ thể, bạn cần **ràng buộc kiểu (type bound)** ngay tại nơi khai báo type parameter.

Cú pháp cơ bản là `<T extends Bound>`. `Bound` có thể là **class** hoặc **interface**; trong cả hai trường hợp Java đều dùng từ khóa `extends`. Với nhiều yêu cầu đồng thời, có thể dùng các cận nối bằng `&`, chẳng hạn `<T extends Number & Comparable<T>>`. Những giới hạn này được kiểm tra chủ yếu **lúc biên dịch** và cùng tham gia quá trình suy luận kiểu ở mỗi lời gọi.

Bài này giải thích cơ chế, cú pháp, cách áp dụng trên class, interface, record và generic method, multiple bounds, generic inheritance, ví dụ chạy Java 17+, điểm liên hệ với wildcard và type erasure, cùng các lỗi dễ gặp. Mục tiêu là biết **khi nào cần bound, compiler chứng minh được gì nhờ bound, và khi nào không nên làm API phức tạp hơn mức cần thiết**.

## 1. Lựa chọn giữa class bound và interface bound

Nếu không có bound, type variable `T` thông thường chỉ được bảo đảm các khả năng của `Object`; vì thế không thể gọi `value.doubleValue()` trên mọi `T`. Với `<T extends Number>`, compiler biết phương thức `doubleValue()` tồn tại, nhưng điều này cũng **thu hẹp tập type arguments** xuống những kiểu phù hợp với `Number`.

Bài này tập trung trả lời câu hỏi thiết kế: **khi nào nên chọn một lớp làm bound, khi nào chọn interface và việc chọn đó thay đổi API ra sao?**

- **Class bound** như `Number`: tái sử dụng hợp đồng đã có, đồng thời yêu cầu quan hệ kế thừa với lớp.
- **Interface bound** như `Runnable`: yêu cầu một năng lực mà các lớp ở nhiều họ kế thừa khác nhau có thể triển khai.
- **Parameterized interface bound** như `Identified<ID>`: bảo toàn quan hệ kiểu của kết quả hoặc định danh qua một hợp đồng generic.

Nếu chỉ cần `double twice(Number value)` không có mối quan hệ `T` nào phải bảo toàn, chữ ký nhận trực tiếp `Number` có thể đơn giản hơn. Trong các mục tiếp theo, so sánh class/interface được kiểm chứng bằng những chương trình Java 17 độc lập.

## 2. Bound bằng class: `<T extends Number>`

Chương trình đầu tiên cho thấy cùng một generic method làm việc với hai subtype của `Number`.

Tạo `ClassBoundDemo.java`:

```java
public class ClassBoundDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static <T extends Number> T chooseFirst(T first, T second) {
        return first;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(twice(2.5));

        Integer selected = chooseFirst(10, 20);
        System.out.println(selected);
    }
}
```

Biên dịch và chạy:

```bash
javac ClassBoundDemo.java
java ClassBoundDemo
```

Kết quả `stdout`:

```text
6.0
5.0
10
```

### Đọc từng ràng buộc

**`twice(T value)`:** compiler cho phép gọi `doubleValue()` trên `value` vì `T` bị giới hạn bởi `Number`. Lời gọi `twice(3)` sử dụng boxing khi cần để có reference type; generic type arguments không nhận primitive `int` trực tiếp. Kết quả của hàm là primitive `double`.

**`chooseFirst(T first, T second)`:** hai tham số và kiểu trả về đều dùng **cùng một type variable T**. Với hai đối số `Integer`, một lựa chọn kiểu hợp lệ là `T=Integer`; caller có thể nhận `Integer` mà không phải cast.

Bound `Number` chỉ đòi các giá trị phù hợp với `Number`; nó **không** bắt hai đối số phải có exact runtime class giống nhau. Nếu hai kiểu khác nhau, compiler có thể giải các ràng buộc để tìm kiểu thích hợp (ví dụ một supertype chung) tùy target context. Không dùng `<T extends Number>` làm cơ chế kiểm tra “hai lớp runtime phải bằng nhau”.

### Class bound cho phép những thao tác nào?

Với `<T extends Number>`, compiler có thể cho phép các instance methods công khai thích hợp từ `Number` như `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`. Nhưng nó **không** tự cho phép gọi phương thức chỉ có ở `Integer` hoặc `BigDecimal` mà không nằm trong hợp đồng của `Number`.

Chẳng hạn, `value.compareTo(other)` không được bảo đảm chỉ từ bound `Number`. `Number` không khai báo `compareTo`. Nếu thuật toán còn cần so sánh, phải bổ sung một interface bound hoặc nhận riêng một `Comparator`.

### Những kiểu nào thỏa cận Number?

`Integer`, `Long`, `Double`, `Float`, `Short`, `Byte`, `java.math.BigDecimal` và `java.math.BigInteger` đều là các ví dụ subtype của `Number`. `String` không phải subtype của `Number`, dù bạn có thể chuyển chuỗi số thành số bằng phương thức parse.

`Number` là abstract class nhưng vẫn hoàn toàn hợp lệ làm bound; một type argument có thể chính là `Number` hoặc một subtype phù hợp. **Bound không yêu cầu phải gọi `new Number()`**, và abstract class không phải lý do cản trở generic constraint.

## 3. Bound bằng interface: vẫn dùng `extends`

Khai báo generic:

```java
static <T extends Runnable> void execute(T task) {
    task.run();
}
```

Từ khóa `extends` ở đây áp dụng cho **interface `Runnable`**, mặc dù class cụ thể thực thi interface sẽ dùng `implements Runnable`. Hai vị trí cú pháp khác nhau:

- `class Job implements Runnable`: một **class** triển khai interface.
- `<T extends Runnable>`: một **type parameter** có cận trên là interface.
- Không viết `<T implements Runnable>`; đó là cú pháp sai.

### Ví dụ với Runnable

Tạo `InterfaceBoundDemo.java`:

```java
public class InterfaceBoundDemo {
    static final class Printer implements Runnable {
        private final String message;

        Printer(String message) {
            this.message = message;
        }

        @Override
        public void run() {
            System.out.println(message);
        }
    }

    static <T extends Runnable> void execute(T task) {
        task.run();
    }

    public static void main(String[] args) {
        execute(new Printer("running"));
        execute(() -> System.out.println("lambda"));
    }
}
```

Biên dịch và chạy:

```bash
javac InterfaceBoundDemo.java
java InterfaceBoundDemo
```

`stdout`:

```text
running
lambda
```

`Printer` implements `Runnable` nên hợp lệ làm đối số của `execute`. Java cũng suy luận được cách gọi `execute` bằng lambda, vì ngữ cảnh tham số generic mang cận interface chức năng `Runnable`.

Nếu truyền một đối tượng không implement `Runnable`, compiler không chứng minh được bound và sẽ từ chối lời gọi. Generic method không tự biến đối tượng tùy ý thành `Runnable`; phải có quan hệ kiểu thích hợp.

### Một interface tự khai báo generic

Giới hạn không nhất thiết phải là interface không generic. Ví dụ:

```java
interface Identified<ID> {
    ID id();
}

static <ID, T extends Identified<ID>> ID extractId(T value) {
    return value.id();
}
```

Đây là phần khai báo minh họa (method phải đặt trong class thích hợp). Trong `<ID, T extends Identified<ID>>`, cả `ID` và `T` đều là type parameters của method; `T` bị giới hạn bởi **một interface đã áp dụng type argument `ID`**. Vì thế `extractId` trả chính kiểu `ID` tương ứng với giá trị đầu vào.

Điểm mấu chốt không phải tên biến `ID` hay `T` mà là **quan hệ được viết trong bound**: `T` phải thực thi `Identified<ID>` theo một cách tham số hóa tương thích.

## 4. Một chương trình đầy đủ: bound bằng generic interface

Tạo `GenericInterfaceBoundDemo.java`:

```java
public class GenericInterfaceBoundDemo {
    interface Identified<ID> {
        ID id();
    }

    record User(Long id, String name) implements Identified<Long> {
    }

    record Product(String id, String title)
            implements Identified<String> {
    }

    static <ID, T extends Identified<ID>> ID extractId(T item) {
        return item.id();
    }

    public static void main(String[] args) {
        User user = new User(42L, "Lan");
        Product product = new Product("P-5", "Book");

        Long userId = extractId(user);
        String productId = extractId(product);

        System.out.println(userId);
        System.out.println(productId);
    }
}
```

Chạy:

```bash
javac GenericInterfaceBoundDemo.java
java GenericInterfaceBoundDemo
```

`stdout`:

```text
42
P-5
```

Phân tích:

1. `Identified<ID>` là generic interface; `ID` biểu diễn kiểu định danh.
2. `User` cố định interface thành `Identified<Long>`; `Product` cố định thành `Identified<String>`.
3. `<ID, T extends Identified<ID>>` khai báo hai type parameters và liên kết chúng.
4. `extractId(user)` có thể suy luận kết quả phù hợp với `Long`; `extractId(product)` phù hợp với `String`.
5. Generic bound cho phép gọi `item.id()` và giữ quan hệ return type với interface. Nó không xác minh giá trị ID có tồn tại trong database hay không; đó là yêu cầu nghiệp vụ khác.

Một method chỉ nhận `Identified<ID>` cũng có thể đủ cho bài toán này:

```java
static <ID> ID extractId(Identified<ID> item) {
    return item.id();
}
```

Chữ ký ngắn hơn vẫn giữ quan hệ `ID`. Chỉ cần thêm `T extends Identified<ID>` khi chính xác kiểu con `T` cần xuất hiện ở nơi khác trong method hoặc trong hợp đồng trả về.

## 5. Multiple bounds: một type parameter phải thỏa nhiều yêu cầu

Nếu thuật toán vừa cần một base class vừa cần một interface, có thể viết **multiple bounds**:

```java
<T extends SomeClass & SomeInterface>
```

Dấu `&` tại đây biểu diễn **giao các giới hạn**: `T` phải tương thích với cả hai cận. Quy tắc cú pháp:

1. Chỉ có **tối đa một class bound tường minh**, và nếu có thì **phải đứng đầu**.
2. Sau class bound có thể là một hoặc nhiều interface bounds.
3. Nếu toàn interface, bạn có thể bắt đầu bằng interface bất kỳ rồi nối các interface khác với `&`.
4. Dùng `extends` **một lần** trước danh sách bounds; các bounds còn lại nối bằng `&`.
5. Bound không phải phép hợp `|`; `T` phải đáp ứng **tất cả** điều kiện, không phải chỉ một.

Ví dụ hợp lệ:

```java
<T extends Number & Comparable<T>>
<T extends Runnable & AutoCloseable>
<T extends java.io.Serializable & Comparable<T>>
```

Các dòng trên là mẫu khai báo type-parameter list (không phải chương trình chạy độc lập). Ngược lại, `<T extends Runnable & Number>` là không hợp lệ vì nếu `Number` làm class bound thì nó phải đứng đầu.

### Tại sao `Number` chưa đủ để so sánh?

`Number` cung cấp các phép chuyển đổi sang primitive numeric types nhưng không khai báo `compareTo`. Khi cần trả về giá trị lớn hơn theo một quy tắc tự nhiên, phải bảo đảm cả khả năng nhận giá trị kiểu `T` và khả năng so sánh.

```java
static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`Integer`, `Long`, `Double` đều phù hợp với chữ ký này trong các lời gọi riêng vì mỗi wrapper triển khai `Comparable` với kiểu tương ứng. `java.math.BigDecimal` cũng thỏa. Nhưng một class con `Number` tự tạo mà không implement `Comparable<T>` sẽ không phù hợp, dù có đủ `doubleValue()`.

## 6. Ví dụ class bound kết hợp interface bound

Tạo `MultipleBoundDemo.java`:

```java
public class MultipleBoundDemo {
    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T extends Number & Comparable<T>> double doubledMax(
            T a, T b) {
        return larger(a, b).doubleValue() * 2;
    }

    public static void main(String[] args) {
        Integer topScore = larger(8, 12);
        Double topPrice = larger(2.5, 1.5);

        System.out.println(topScore);
        System.out.println(topPrice);
        System.out.println(doubledMax(3, 7));
    }
}
```

Chạy:

```bash
javac MultipleBoundDemo.java
java MultipleBoundDemo
```

`stdout`:

```text
12
2.5
14.0
```

Trong `larger`:

- `Number` cho phép xử lý như một đối tượng Number, nhưng riêng method này chỉ dùng `compareTo`.
- `Comparable<T>` cho phép gọi `a.compareTo(b)` với `b` kiểu `T`.
- Return type `T` bảo toàn quan hệ kiểu với hai tham số.
- `doubledMax` cần cả `compareTo` để tìm phần tử lớn hơn và `doubleValue()` để trả `double`.

Các ví dụ riêng lẻ với `Integer` và `Double` không có nghĩa generic method có thể tùy ý so sánh `Integer` với `Double` bằng cách gọi `compareTo`. Hai wrapper implement `Comparable` với các type arguments khác nhau; một lời gọi lẫn hai loại không tự đáp ứng bound `Comparable<T>` một cách tùy tiện. Nếu mục tiêu là so sánh nhiều loại Number hỗn hợp, hãy định nghĩa một chiến lược so sánh cụ thể (chẳng hạn chuyển sang `double` với lưu ý về mất độ chính xác) thay vì giả định một natural order chung.

### Khi nào chọn `Comparable<? super T>`?

Một chữ ký thường linh hoạt hơn là:

```java
static <T extends Comparable<? super T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`Comparable<? super T>` chấp nhận trường hợp một kiểu `T` có khả năng so sánh với **một supertype của T**, chẳng hạn thông qua interface `Comparable<Base>` được một subtype kế thừa. Cách viết này phổ biến trong Java Collections API. Nó không yêu cầu `T` là `Number`; `String` cũng có thể được so sánh.

Chữ ký `<T extends Number & Comparable<? super T>>` dùng khi **đồng thời** cần hành vi `Number` và so sánh tự nhiên. Chọn bound tối thiểu nhưng đúng để không loại bỏ những kiểu hợp lệ khác.

## 7. Multiple interface bounds: không cần class bound

Nếu thuật toán cần hai hợp đồng độc lập từ interface, có thể ràng buộc `T` bằng cả hai:

```java
static <T extends Runnable & AutoCloseable> void executeAndClose(T task)
        throws Exception {
    try (task) {
        task.run();
    }
}
```

Đây là method Java 17 hợp lệ khi đặt trong class. `Runnable` bảo đảm `run()`; `AutoCloseable` cho phép dùng task trong try-with-resources để đóng sau khi thực thi, kể cả lúc `run` ném lỗi.

### Chương trình hoàn chỉnh

Tạo `InterfaceIntersectionDemo.java`:

```java
public class InterfaceIntersectionDemo {
    static final class Job implements Runnable, AutoCloseable {
        @Override
        public void run() {
            System.out.println("running");
        }

        @Override
        public void close() {
            System.out.println("closed");
        }
    }

    static <T extends Runnable & AutoCloseable> void executeAndClose(T task)
            throws Exception {
        try (task) {
            task.run();
        }
    }

    public static void main(String[] args) throws Exception {
        executeAndClose(new Job());
    }
}
```

Biên dịch và chạy:

```bash
javac InterfaceIntersectionDemo.java
java InterfaceIntersectionDemo
```

`stdout`:

```text
running
closed
```

`Job` phải implement **cả** `Runnable` và `AutoCloseable`. Một đối tượng chỉ implements `Runnable` không thỏa bound còn lại. Thứ tự cận interface có thể thay đổi ở mức khả năng của compiler chứng minh các thành viên, nhưng thứ tự cận có ý nghĩa trong **type erasure**, vì cận đầu tiên được dùng khi xóa biến kiểu.

Lưu ý: `AutoCloseable.close()` có thể khai báo ném `Exception`, nên ví dụ cho phép ngoại lệ bằng `throws Exception`. Đây là hợp đồng exception thông thường, không phải đặc quyền của Generic.

## 8. Generic class với bound bằng class

Bound không chỉ áp dụng cho generic method. Bạn có thể khai báo trực tiếp ở class:

```java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

Đây là class minh họa, không có `main`. `T extends Number` có phạm vi trong instance members của `NumericBox`: component/field `value` có kiểu `T`, `get()` trả `T`, và `asDouble()` gọi method có trên `Number`.

Với `NumericBox<Integer>`, `get()` có kiểu biểu thức `Integer`; với `NumericBox<java.math.BigDecimal>`, nó có kiểu `BigDecimal`. Cả hai có thể gọi `asDouble()`.

### Ví dụ đầy đủ

Tạo `BoundedClassDemo.java`:

```java
public class BoundedClassDemo {
    static final class NumericBox<T extends Number> {
        private final T value;

        NumericBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> count = new NumericBox<>(6);
        NumericBox<Double> weight = new NumericBox<>(1.25);

        Integer countValue = count.get();

        System.out.println(countValue);
        System.out.println(count.twice());
        System.out.println(weight.twice());
    }
}
```

Chạy `javac BoundedClassDemo.java` rồi `java BoundedClassDemo`:

```text
6
12.0
2.5
```

`NumericBox<String>` là lỗi biên dịch vì `String` không thỏa `Number`. Java không tự parse một chuỗi như `"6"` thành số để thỏa generic bound.

Nếu class có nhiều type parameters, chỉ ràng buộc những biến cần thiết:

```java
class Measurement<ID, N extends Number> {
    private final ID id;
    private final N value;

    Measurement(ID id, N value) {
        this.id = id;
        this.value = value;
    }

    ID id() { return id; }
    N value() { return value; }
}
```

Ở đây `ID` không có bound tường minh; `N` bị giới hạn bởi `Number`. Có thể dùng `Measurement<String,Integer>` hay `Measurement<Long,Double>`. Bound của `N` không áp dụng cho `ID`.

## 9. Generic interface và record với bound

Một generic interface có thể ràng buộc type parameter của chính nó:

```java
interface NumericSource<T extends Number> {
    T read();
}
```

Mọi class triển khai `NumericSource<T>` phải truyền type argument phù hợp bound. Nếu class con còn generic, cần chuyển tiếp điều kiện đó.

Một record cũng hỗ trợ bound:

```java
record Range<T extends Comparable<? super T>>(T from, T to) {
    Range {
        if (from.compareTo(to) > 0) {
            throw new IllegalArgumentException("from > to");
        }
    }
}
```

Record components `from` và `to` cùng kiểu `T`. Bound `Comparable<? super T>` cho phép compiler gọi `compareTo`; compact constructor bảo vệ **bất biến nghiệp vụ** “from không lớn hơn to”. Generic type bound tự nó không bảo đảm thứ tự hai giá trị — chính câu lệnh kiểm tra trong constructor mới làm việc đó.

Tạo `BoundedRecordDemo.java`:

```java
public class BoundedRecordDemo {
    record Range<T extends Comparable<? super T>>(T from, T to) {
        Range {
            if (from.compareTo(to) > 0) {
                throw new IllegalArgumentException("from > to");
            }
        }
    }

    public static void main(String[] args) {
        Range<Integer> pageRange = new Range<>(1, 5);
        Range<String> nameRange = new Range<>("A", "Z");

        System.out.println(pageRange.from() + ".." + pageRange.to());
        System.out.println(nameRange.from() + ".." + nameRange.to());
    }
}
```

Chạy:

```bash
javac BoundedRecordDemo.java
java BoundedRecordDemo
```

`stdout`:

```text
1..5
A..Z
```

Nếu `from` hoặc `to` null, ví dụ sẽ ném `NullPointerException` khi gọi `compareTo`. Bạn có thể bổ sung `Objects.requireNonNull` nếu muốn lỗi và thông báo rõ hơn; generic bound không tự cấm null.

## 10. Bound và kế thừa: class con phải chuyển tiếp đúng ràng buộc

Giả sử superclass yêu cầu `T extends Number`:

```java
class NumericStore<T extends Number> {
    final T value;

    NumericStore(T value) {
        this.value = value;
    }
}
```

Một subclass vẫn generic phải cung cấp type argument luôn thỏa bound của superclass:

```java
class AuditedStore<N extends Number> extends NumericStore<N> {
    AuditedStore(N value) {
        super(value);
    }
}
```

Đây là khai báo hợp lệ; `AuditedStore<Integer>` trở thành một `NumericStore<Integer>`, còn `AuditedStore<Double>` thành `NumericStore<Double>`. `N` thuộc subclass và được **chuyển tiếp** làm type argument của cha.

Ngược lại:

```java
// Không biên dịch:
// class BadStore<U> extends NumericStore<U> {
//     BadStore(U value) { super(value); }
// }
```

Vì `U` chưa có bound, compiler không thể chứng minh `U` luôn tương thích với `Number`. Bạn có thể sửa bằng `U extends Number` hoặc cố định subclass thành `extends NumericStore<Integer>` khi ý nghĩa nghiệp vụ chỉ cần `Integer`.

### Ví dụ chạy hoàn chỉnh

Tạo `BoundedInheritanceDemo.java`:

```java
public class BoundedInheritanceDemo {
    static class NumericStore<T extends Number> {
        private final T value;

        NumericStore(T value) {
            this.value = value;
        }

        double doubleValue() {
            return value.doubleValue();
        }
    }

    static final class AuditedStore<N extends Number>
            extends NumericStore<N> {
        private final String label;

        AuditedStore(String label, N value) {
            super(value);
            this.label = label;
        }

        void print() {
            System.out.println(label + "=" + doubleValue());
        }
    }

    public static void main(String[] args) {
        AuditedStore<Integer> items = new AuditedStore<>("items", 3);
        AuditedStore<Double> weight = new AuditedStore<>("kg", 2.5);

        items.print();
        weight.print();
    }
}
```

Chạy:

```bash
javac BoundedInheritanceDemo.java
java BoundedInheritanceDemo
```

`stdout`:

```text
items=3.0
kg=2.5
```

Bound không cần lặp lại bằng **đúng cùng chữ tên** như ở cha: `NumericStore<T>` và `AuditedStore<N>` khai báo hai type parameters thuộc hai class khác nhau. Mệnh đề `extends NumericStore<N>` cùng bound của `N` bảo đảm ánh xạ hợp lệ.

## 11. Bound không tạo quan hệ subtype giữa các cách tham số hóa

Ngay cả khi `Integer extends Number`, thì:

```java
NumericBox<Integer> integers = new NumericBox<>(5);
// NumericBox<Number> numbers = integers; // Không hợp lệ.
```

Dòng minh họa trên giả sử `NumericBox<T extends Number>` đã được khai báo.

Generic types thường **invariant** theo type arguments. Bound `T extends Number` chỉ giới hạn **những kiểu nào có thể dùng làm T**, chứ không biến `NumericBox<Integer>` thành subtype của `NumericBox<Number>`.

Muốn một method đọc giá trị từ nhiều loại `NumericBox` khác nhau, có thể nhận wildcard:

```java
static void printValue(NumericBox<? extends Number> box) {
    Number n = box.get();
    System.out.println(n);
}
```

`? extends Number` ở đây là **upper-bounded wildcard** dùng làm type argument, khác với `<T extends Number>` là **khai báo named type parameter**. Hai cú pháp đều diễn đạt giới hạn phía trên nhưng đảm nhiệm hai vai trò khác nhau.

### Khi nào dùng type parameter, khi nào dùng wildcard?

- Dùng `<T extends Number>` nếu cần **đặt tên kiểu T và liên kết T giữa nhiều vị trí**, ví dụ `T min(T a,T b)`.
- Dùng `List<? extends Number>` khi một tham số chủ yếu **cung cấp** các giá trị đọc như `Number` mà không cần đưa kiểu cụ thể của phần tử vào kết quả.
- Dùng `List<? super Integer>` khi cần **thêm Integer** vào một danh sách có thể chứa Integer hoặc supertype của Integer; đây là lower-bounded wildcard, không phải một multiple bound của type parameter.
- Tránh dùng raw type chỉ để lách giới hạn compile time.

Đặc biệt, Java **không khai báo lower-bound cho named type parameter** dưới dạng `<T super Number>`. Cú pháp đó không hợp lệ. `super` xuất hiện ở **wildcard type argument**, ví dụ `List<? super Number>`.

## 12. Recursive bounds và Comparable

Một số interface generic mô tả kiểu đối tượng có thể thao tác với chính kiểu đó. Java cho phép type parameter xuất hiện trong bound của nó:

```java
<T extends Comparable<T>>
```

Đây là **recursive bound**, không phải vòng lặp runtime. Nó nói rằng kiểu `T` phải phù hợp với `Comparable<T>`. Khi viết generic method cần tính thứ tự, `Comparable` là lựa chọn quen thuộc.

### Tại sao `Comparable<? super T>` linh hoạt hơn?

Giả sử class `Animal` implements `Comparable<Animal>`; một subtype `Dog extends Animal` kế thừa khả năng so sánh với `Animal`. `Dog` không nhất thiết implements riêng `Comparable<Dog>`. Vì vậy:

```java
<T extends Comparable<? super T>>
```

có thể chấp nhận `Dog` thông qua `Comparable<Animal>` — loại so sánh cho một **supertype** của `Dog`. Đây là lý do nhiều chữ ký trong JDK dùng mẫu `Comparable<? super T>` thay vì `Comparable<T>`.

### Ví dụ chứng minh

Tạo `ComparableBoundDemo.java`:

```java
public class ComparableBoundDemo {
    static class Animal implements Comparable<Animal> {
        private final int weight;

        Animal(int weight) {
            this.weight = weight;
        }

        @Override
        public int compareTo(Animal other) {
            return Integer.compare(weight, other.weight);
        }

        @Override
        public String toString() {
            return "Animal(" + weight + ")";
        }
    }

    static final class Dog extends Animal {
        Dog(int weight) {
            super(weight);
        }
    }

    static <T extends Comparable<? super T>> T greater(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Dog light = new Dog(5);
        Dog heavy = new Dog(9);

        Dog winner = greater(light, heavy);
        System.out.println(winner);
    }
}
```

Chạy:

```bash
javac ComparableBoundDemo.java
java ComparableBoundDemo
```

`stdout`:

```text
Animal(9)
```

`Dog` thỏa `Comparable<? super Dog>` vì nó kế thừa `Comparable<Animal>`, và `Animal` là supertype của `Dog`. Kết quả vẫn có thể được sử dụng dưới kiểu tĩnh `Dog` khi inference chọn `T=Dog`.

Không suy luận rằng mọi subtype của một kiểu implements Comparable đều có total order phù hợp nghiệp vụ. Nếu định nghĩa `compareTo` mâu thuẫn với `equals` hoặc không bắc cầu, thuật toán sắp xếp và tập có thứ tự có thể hoạt động khó đoán. Bound chỉ chứng minh **khả năng gọi method**, không chứng minh tính đúng đắn của thuật toán so sánh.

## 13. Multiple bounds và các thành viên trùng chữ ký

Nếu các bound có các method trùng tên, compiler phải xác định có một hợp đồng method được kế thừa **tương thích**. Multiple bounds không phải cơ chế hợp nhất các API tùy ý có return types xung đột.

Ví dụ hai interface có method cùng chữ ký tương thích:

```java
interface Named {
    String name();
}

interface Labeled {
    String name();
}

static <T extends Named & Labeled> String display(T value) {
    return value.name();
}
```

Đây là trích khai báo minh họa: hai interface khai báo cùng method `String name()` nên một implementation có thể đáp ứng cả hai bằng một method.

Nếu hai interface định nghĩa các method có cùng parameter signature nhưng kiểu trả về không tương thích, không thể giả định intersection bound hợp lệ. Java áp dụng các quy tắc xung đột phương thức kế thừa và kiểu trả về.

Một lưu ý nữa: chỉ một class bound tường minh và cận class phải ở đầu. Cú pháp kiểu `<T extends ClassA & ClassB>` với hai class bounds không hợp lệ, kể cả khi ClassB có quan hệ kế thừa với ClassA. Nếu cần hợp đồng kết hợp, thường đặt một class ở đầu và interface theo sau.

## 14. Type erasure: bound ảnh hưởng đến kiểu sau xóa

Java Generics dùng **type erasure** khi biên dịch. Kiểm tra bound thực hiện ở compile time; type variable không giữ nguyên làm một kiểu runtime chuyên biệt cho mỗi type argument.

Các quy tắc cần nhớ:

1. Type parameter không có bound tường minh thường bị xóa thành `Object`.
2. `<T extends Number>` bị xóa thành `Number`.
3. `<T extends Runnable & AutoCloseable>` bị xóa thành **cận đầu tiên là `Runnable`**; compiler vẫn bảo đảm các bound khác trong mã nguồn và có thể chèn cast cần thiết.
4. Generic type `List<Integer>` và `List<String>` không biến thành hai runtime `ArrayList` classes khác nhau chỉ bởi type arguments.
5. Compiler có thể tạo bridge methods hoặc casts để duy trì hợp đồng generic và đa hình sau erasure.

### Quan sát bound bằng reflection

Tạo `ErasureBoundDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class ErasureBoundDemo {
    static <T extends Number> double doubleValue(T number) {
        return number.doubleValue();
    }

    public static void main(String[] args) throws Exception {
        Method method = ErasureBoundDemo.class
                .getDeclaredMethod("doubleValue", Number.class);
        TypeVariable<?> type = method.getTypeParameters()[0];

        System.out.println(type.getName());
        System.out.println(type.getBounds()[0].getTypeName());
        System.out.println(method.getParameterTypes()[0].getTypeName());
    }
}
```

Biên dịch/chạy:

```bash
javac ErasureBoundDemo.java
java ErasureBoundDemo
```

`stdout`:

```text
T
java.lang.Number
java.lang.Number
```

`getTypeParameters()` đọc metadata type parameter `T` của **khai báo method**. `getBounds()` cho biết upper bound `Number`. Tham số runtime của method đã được erasure về `Number`, nên reflection tìm method bằng `Number.class`, không phải bằng một `T.class` không tồn tại.

Điều này **không** có nghĩa reflection có thể khôi phục chính xác type argument được suy luận tại từng invocation của method. Metadata khai báo generic khác với việc mỗi lời gọi tạo một method runtime chuyên biệt.

### Không overload chỉ dựa trên bound/type arguments đã xóa

Ví dụ:

```java
// Không được đặt cả hai trong một class:
// void add(java.util.List<String> list) {}
// void add(java.util.List<Integer> list) {}
```

Hai tham số đều erasure thành `List`, gây name clash. Tương tự, hai generic methods có parameter signatures trùng sau erasure không thể phân biệt chỉ bằng tên type variables `T` và `U`.

## 15. Class token và factory: bound không cho phép `new T()`

Dù `T extends Number` hoặc `T extends Runnable`, Java vẫn không cho phép viết:

```java
// Không hợp lệ trong generic method/class:
// T value = new T();
// Class<T> runtimeType = T.class;
```

Bound bảo đảm **quan hệ kiểu và tập phương thức**, không bảo đảm có một constructor được gọi trực tiếp qua `T`, cũng không tạo class token runtime mang tên `T`.

Nếu cần tạo giá trị của kiểu `T`, nên **nhận một factory hoặc Supplier** từ caller:

Tạo `BoundedFactoryDemo.java`:

```java
import java.util.function.Supplier;

public class BoundedFactoryDemo {
    static final class Task implements Runnable {
        @Override
        public void run() {
            System.out.println("task");
        }
    }

    static <T extends Runnable> T createAndRun(
            Supplier<? extends T> factory) {
        T task = factory.get();
        task.run();
        return task;
    }

    public static void main(String[] args) {
        Task task = createAndRun(Task::new);
        System.out.println(task.getClass().getSimpleName());
    }
}
```

Chạy:

```bash
javac BoundedFactoryDemo.java
java BoundedFactoryDemo
```

`stdout`:

```text
task
Task
```

`Supplier<? extends T>` tạo ra một giá trị có kiểu tương thích `T`, và bound `T extends Runnable` cho phép gọi `run()`. Đây là cách kết hợp factory với generic bound mà không vi phạm `new T()`.

Nếu factory trả `null`, `task.run()` sẽ ném `NullPointerException`; nếu cần thông báo rõ hơn, bổ sung `Objects.requireNonNull(factory.get())`. Generic bound không bảo đảm non-null.

## 16. Bounds có thể là kiểu generic được tham số hóa

Cận trên có thể là một generic interface đã áp dụng type argument:

```java
<T extends Comparable<T>>
<T extends Comparable<? super T>>
<T extends java.lang.Iterable<String>>
```

Ví dụ `<T extends Iterable<String>>` cho compiler biết mỗi `T` có thể được duyệt và từng phần tử trả ra thuộc kiểu `String` ở mức mã nguồn. Một implementation của `Iterable<String>`, chẳng hạn `List<String>`, phù hợp.

Tạo `ParameterizedInterfaceBoundDemo.java`:

```java
import java.util.List;

public class ParameterizedInterfaceBoundDemo {
    static <T extends Iterable<String>> int totalLength(T values) {
        int total = 0;
        for (String value : values) {
            total += value.length();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(totalLength(List.of("Java", "Core")));
    }
}
```

Chạy:

```bash
javac ParameterizedInterfaceBoundDemo.java
java ParameterizedInterfaceBoundDemo
```

`stdout`:

```text
8
```

`List<String>` implements `Iterable<String>` và thỏa bound. `List<Integer>` không thỏa `Iterable<String>`. Đây là giới hạn về **cách interface generic được tham số hóa**, không chỉ về tên raw interface.

Hãy phân biệt:

- `T extends Iterable<String>`: named type parameter `T` phải triển khai một interface có element type `String`.
- `Iterable<? extends CharSequence>`: wildcard cho phép producer có kiểu phần tử là một subtype của `CharSequence`.
- `Iterable<T>`: khi `T` đã được khai báo ở một nơi khác, đây là **type argument usage**, không tự tạo một biến kiểu mới.

## 17. Quy tắc thực tế để chọn cận phù hợp

| Nhu cầu thuật toán | Bound/cách khai báo phù hợp | Lý do |
| --- | --- | --- |
| Chỉ nhận đối tượng số và gọi `doubleValue` | `<T extends Number>` hoặc trực tiếp `Number` | Compiler biết phương thức của Number |
| Nhận task và gọi `run` | `<T extends Runnable>` hoặc `Runnable` | Yêu cầu hành vi của interface |
| Vừa `run` vừa `close` | `<T extends Runnable & AutoCloseable>` | Phải có đồng thời hai khả năng |
| Giữ đúng kiểu số trả về | `<T extends Number> T choose(T a,T b)` | Return gắn cùng named T |
| So sánh tự nhiên nhiều kiểu | `<T extends Comparable<? super T>>` | So sánh T với T qua Comparable |
| Vừa Number vừa Comparable | `<T extends Number & Comparable<? super T>>` | Hợp đồng gồm numeric conversion và ordering |
| Đọc danh sách nhiều loại số | `List<? extends Number>` | Wildcard đủ nếu không cần đặt tên kiểu phần tử |
| Cho phép thêm Integer vào danh sách đích | `List<? super Integer>` | Lower-bounded wildcard ở vị trí consumer |
| Chỉ tính trung bình hai Number | `double average(Number a,Number b)` | Không nhất thiết phải generic |
| Trả kết quả mapping có kiểu khác nguồn | `<T,R> R convert(T input,Function<? super T,? extends R> f)` | T nối đầu vào, R nối kiểu kết quả |

Không nên thêm bound chỉ vì “mọi generic method trông chuyên nghiệp hơn khi có extends”. Mỗi cận làm **thu hẹp tập type arguments có thể dùng**, vì vậy nên có lý do liên quan đến thao tác hay quan hệ kiểu thật sự.

### Cận quá rộng và quá hẹp

- Quá rộng: dùng `<T>` nhưng thân cần `doubleValue()` → compiler không cho gọi.
- Vừa đủ: dùng `<T extends Number>` khi thật sự cần `doubleValue()`.
- Quá hẹp: dùng `<T extends Integer>` khi chỉ cần `Number` → về cú pháp là **hợp lệ**, nhưng `Integer` là final nên bound này không cho thêm subtype ngoài `Integer`; thường dùng trực tiếp `Integer` rõ hơn.
- Quá phức tạp: dùng multiple bounds khi thuật toán chỉ sử dụng phương thức từ một cận → API khó tái sử dụng hơn cần thiết.

Dù một final class vẫn có thể xuất hiện làm bound, nó thường không mang lợi ích tái sử dụng kiểu; “final class” **không làm cú pháp `<T extends FinalClass>` tự động sai**.

## 18. Lỗi thường gặp khi giới hạn type parameter

### 18.1. Dùng `implements` thay `extends` ở type parameter

Sai:

```java
// <T implements Runnable> // Không hợp lệ.
```

Đúng:

```java
<T extends Runnable>
```

`implements` dùng trong khai báo class implement interface; type parameter dùng `extends` bất kể upper bound là class hay interface.

### 18.2. Đặt class bound sau interface

Sai:

```java
// <T extends Runnable & Number> // Sai thứ tự class/interface.
```

Đúng nếu bạn thực sự cần hai cận và có type phù hợp:

```java
<T extends Number & Runnable>
```

`Number` là class bound nên đứng đầu. Ví dụ cú pháp không khẳng định các wrapper số chuẩn của JDK đều implement `Runnable`; một class Number tùy biến có thể triển khai Runnable để thỏa yêu cầu.

### 18.3. Lặp từ khóa extends cho mỗi bound

Sai:

```java
// <T extends Number extends Comparable<T>>
```

Đúng:

```java
<T extends Number & Comparable<T>>
```

Giữa các bounds dùng `&`, không lặp `extends`.

### 18.4. Giả định Number hỗ trợ compareTo

`Number` không có `compareTo`. Nếu thuật toán gọi method đó, cần `Comparable` bound hoặc nhận `Comparator` phù hợp. Đừng cast toàn bộ Number sang `Comparable` để né compiler; không phải mọi Number subtype đều có natural ordering.

### 18.5. Nhầm bound với wildcard

`<T extends Number>` **khai báo T**. `List<? extends Number>` **dùng wildcard**. Hai cú pháp ở hai vị trí khác nhau, không hoán đổi tùy ý. Không có dạng `<T super Number>` hợp lệ.

### 18.6. Không chuyển tiếp bound khi extends generic class

Nếu cha đòi `T extends Number` thì con `Child<U> extends Parent<U>` phải bảo đảm `U` thỏa cận tương ứng. Thêm `U extends Number` hoặc dùng type argument cụ thể phù hợp.

### 18.7. Cho rằng bound khiến mọi T đều có thể khởi tạo

`new T()` không hợp lệ chỉ dựa trên bound; cần factory, supplier hoặc thông tin kiểu runtime. Bound không bảo đảm no-arg constructor.

### 18.8. Nghĩ T không thể nhận null vì đã có bound

`T extends Number` vẫn là reference type; null có thể thỏa kiểm tra kiểu tĩnh. Một lời gọi method trên giá trị null ném `NullPointerException`. Nếu cần non-null, kiểm tra runtime hoặc dùng chính sách API riêng.

### 18.9. Trộn loại Number không tương thích khi so sánh

`Integer` và `Double` cùng extends `Number`, nhưng không có một `Comparable<Number>` chung được mỗi wrapper hiện thực. Một bound `<T extends Number & Comparable<T>>` không tự biến việc so sánh hai wrapper khác loại thành hợp lệ. Chọn kiểu so sánh hoặc comparator rõ ràng.

### 18.10. Che lỗi bằng raw type/unchecked cast

Bound giúp compiler phát hiện vi phạm hợp đồng; raw types và unchecked casts có thể đánh mất những bảo đảm đó. Nếu bắt gặp warning, lần theo API rồi sửa generic declaration/type argument thay vì tắt warning vô điều kiện.

## 19. Bài tập có đáp án

### Bài 1 — Class bound

Cho:

```java
static <T extends Number> double triple(T value) {
    return value.doubleValue() * 3;
}
```

`triple(4)`, `triple(1.5)` có hợp lệ không? `triple("4")` thì sao?

**Đáp án:** Hai lời gọi số hợp lệ và trả `12.0`, `4.5`. `String` không kế thừa `Number` nên lời gọi chuỗi bị lỗi biên dịch. Đây là method trích để học, chưa có `main`.

### Bài 2 — Interface bound

Cho:

```java
static <T extends CharSequence> int length(T value) {
    return value.length();
}
```

Vì sao `String` và `StringBuilder` hợp lệ? Vì cả hai implement `CharSequence`. Một `Integer` không có quan hệ interface đó nên không hợp lệ.

### Bài 3 — Class và interface đồng thời

```java
static <T extends Number & Comparable<T>> T smaller(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b;
}
```

Giải thích: `Number` đảm bảo tập numeric methods, `Comparable<T>` bảo đảm `compareTo`, `T` giữ kiểu trả về. `smaller(3,7)` trả giá trị `3`; `smaller(2.0,1.5)` trả `1.5`.

### Bài 4 — Hai interface

Viết một class `Task` implements `Runnable` và `AutoCloseable`. Truyền object vào `<T extends Runnable & AutoCloseable> void executeAndClose(T)`. Nếu class chỉ implements `Runnable`, điều gì xảy ra? Compiler không chấp nhận vì thiếu `AutoCloseable`. Nếu có cả hai, try-with-resources gọi `close` sau `run`.

### Bài 5 — Bound trong class

Cho `class Holder<T extends Number>`. Tại sao `Holder<Integer>` hợp lệ còn `Holder<String>` không? Vì type argument phải thỏa upper bound `Number`. Đưa một giá trị chuỗi có chữ số vào constructor không thể sửa lỗi kiểu bằng boxing hay tự động parse.

### Bài 6 — Kế thừa bound

```java
class Parent<T extends Number> {}
class Good<U extends Number> extends Parent<U> {}
// class Bad<U> extends Parent<U> {}
```

Vì sao Good hợp lệ còn Bad không? Good bảo đảm mọi `U` của nó là subtype Number; Bad không thể đưa ra bảo đảm ấy cho superclass.

### Bài 7 — Named bound hay wildcard?

Một method chỉ cộng tất cả phần tử trong danh sách số. Bạn sẽ nhận `List<Number>` hay `List<? extends Number>`? Nên dùng wildcard upper bound nếu muốn chấp nhận cả `List<Integer>`, `List<Double>`... để **đọc** như Number. Không cần tự khai báo `<T extends Number>` nếu return type không nối với một T cụ thể và wildcard đã đủ.

### Bài 8 — Recursive bound

Một class `Base` implements `Comparable<Base>`; class `Derived extends Base`. Vì sao `<T extends Comparable<? super T>>` có thể phù hợp với Derived? Vì Derived có thể so sánh với Base là supertype của Derived thông qua interface kế thừa.

### Bài 9 — Thứ tự cận

Phân loại:

```java
<T extends Number & Comparable<T>>     // Hợp lệ.
<T extends Runnable & AutoCloseable>   // Hợp lệ.
<T extends Runnable & Number>          // Không hợp lệ: class đứng sau.
<T extends Number & Runnable>          // Hợp lệ về thứ tự.
```

Một khai báo hợp lệ về **cú pháp bounds** chưa chắc mọi type có sẵn đều thỏa; phải xét class/interface cụ thể làm type argument.

### Bài 10 — Sửa API quá generic

Bạn thấy:

```java
static <T extends Number> double plus(T a, T b) {
    return a.doubleValue() + b.doubleValue();
}
```

Nếu API chỉ cần cộng hai Number và trả double, viết `static double plus(Number a, Number b)` có được không? Có. Chữ ký cụ thể này cũng chấp nhận hai đối số Number khác subtype, rõ ràng hơn khi không cần bảo toàn một named T giữa input và output.

## 20. Checklist khi thiết kế một giới hạn kiểu

Trước khi thêm `extends` vào type parameter, hãy kiểm tra:

1. Phương thức hoặc class cần gọi **method nào** trên T? Method đó có thuộc Object, một class, hay interface?
2. Một cận class đã đủ chưa, hay thật sự cần thêm interface bounds?
3. Nếu có nhiều bounds, **class đứng đầu**, sau đó mới tới các interfaces?
4. Bound có yêu cầu **tất cả** contract đúng như nghiệp vụ, hay đang vô tình hạn chế các type arguments hữu ích?
5. Type parameter có xuất hiện ở **nhiều vị trí cần liên kết kiểu** không? Nếu không, dùng một kiểu cụ thể hoặc wildcard có thể đơn giản hơn.
6. Nếu method nằm trong generic class, đang dùng T của class hay vô tình khai báo một T mới ở method?
7. Nếu subclass chuyển tiếp type parameter cho superclass, các bounds của cha đã được đáp ứng chưa?
8. Caller có định truyền các generic containers với type arguments khác nhau? Nhớ quy tắc invariance, cân nhắc wildcard cho producer/consumer.
9. Có đang nhầm compile-time bound với runtime validation, non-null, factory hay constructor không?
10. Khi có raw type/unchecked warning, đã sửa quan hệ kiểu thay vì ép cast thiếu cơ sở chưa?

## 21. Tổng kết

**Giới hạn bằng lớp hoặc giao diện** là cách Java compiler biết một biến kiểu generic có những khả năng nào. `<T extends Number>` cấp quyền sử dụng các thao tác do `Number` bảo đảm; `<T extends Runnable>` yêu cầu hợp đồng interface `Runnable`; `<T extends Number & Comparable<T>>` kết hợp class bound với interface bound; `<T extends Runnable & AutoCloseable>` yêu cầu đồng thời nhiều interfaces.

Bound có hiệu lực ở **khai báo generic**, được kiểm tra khi áp dụng type arguments và tham gia inference. Nó không cho tạo `new T()`, không tự cấm null, không làm generic type trở thành covariant, và không chứng minh thuật toán nghiệp vụ đúng. Hãy chọn cận **nhỏ nhất đủ bảo đảm những thao tác thật sự cần**, giữ type parameter có tên khi phải liên kết nhiều vị trí, và dùng wildcard hoặc kiểu cụ thể khi điều đó đơn giản hơn.