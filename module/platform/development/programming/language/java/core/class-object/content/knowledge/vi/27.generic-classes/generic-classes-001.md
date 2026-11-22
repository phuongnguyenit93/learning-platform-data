# Lớp generic và mục đích tham số hóa kiểu dữ liệu trong Java

> **Module:** Java Core – class/object  
> **Nhóm:** Lớp generic  
> **Chủ đề trọng tâm:** Lớp generic và mục đích tham số hóa kiểu dữ liệu  
> **Phiên bản:** Java 17+ (generics đã tồn tại từ Java 5; nội dung áp dụng được cho Java hiện đại).

## 1. Vấn đề cốt lõi: một cấu trúc, nhiều kiểu dữ liệu nhưng vẫn kiểm tra kiểu

Giả sử ứng dụng cần một hộp chứa dữ liệu. Hộp có thể chứa `String`, `Integer`, một object `User` hoặc một loại dữ liệu riêng trong tương lai.

Nếu mỗi kiểu phải có một class:

~~~java
class StringBox {
    private String value;

    StringBox(String value) {
        this.value = value;
    }

    String get() {
        return value;
    }
}

class IntegerBox {
    private Integer value;

    IntegerBox(Integer value) {
        this.value = value;
    }

    Integer get() {
        return value;
    }
}
~~~

đây là hai **class fragments** với logic giống nhau, khác kiểu field, constructor parameter và return type. Cách viết ấy gây trùng lặp, dễ sai khi bảo trì.

Một cách cũ là dùng `Object`:

~~~java
class ObjectBox {
    private Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
~~~

ObjectBox chứa được nhiều loại reference values, nhưng compiler không biết giá trị dự kiến là `String` hay `Integer`. Caller phải cast và có thể gặp `ClassCastException` khi chạy.

**Generic class** giải quyết bằng việc **tham số hóa kiểu dữ liệu**:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Bây giờ:

~~~java
Box<String> message = new Box<>("Hello");
String text = message.get();

Box<Integer> count = new Box<>(10);
Integer number = count.get();
~~~

Cùng một class definition được dùng với nhiều **type arguments**. Compiler biết `message.get()` trả `String`, `count.get()` trả `Integer`. Nhiều phép gán kiểu sai bị chặn **trước khi chạy**, không phải đợi tới lúc cast thất bại.

**Mục đích quan trọng nhất của generics không phải làm code trông ngắn hơn; đó là diễn đạt và kiểm tra mối quan hệ kiểu ở compile time trong những API tái sử dụng được.**

## 2. Thuật ngữ đúng về generic class

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Generic class declaration | `class Box<T>` | Class khai báo type parameter T |
| Type parameter | `T` | Biến kiểu được định nghĩa trong generic declaration |
| Parameterized type | `Box<String>` | Dùng Box với một type argument cụ thể |
| Type argument | `String` | Type thực tế cung cấp cho T |
| Generic instance | `new Box<>("A")` | Một object được tạo từ generic class |
| Raw type | `Box raw` | Bỏ type arguments, thường do legacy compatibility |
| Bounded parameter | `T extends Number` | Chỉ các type arguments thỏa bound |
| Unbounded wildcard | `Box<?>` | Một Box của kiểu chưa biết |
| Upper-bounded wildcard | `List<? extends Number>` | Dùng data của một loại Number hoặc subtype |
| Lower-bounded wildcard | `List<? super Integer>` | Dùng container của Integer hoặc supertype |
| Type erasure | `T` thường thành bound/Object ở runtime | Cách compiler chuyển generics thành bytecode tương thích |

### 2.1. Ký tự T không phải một kiểu Java cụ thể

`T` chỉ là tên do người viết generic class đặt cho type parameter. Nó không mặc định là một class có tên T, không phải runtime Class object và không phải giá trị kiểu có thể in ra.

Thông lệ đặt tên thường gặp:

- `T` — Type.
- `E` — Element.
- `K` — Key.
- `V` — Value.
- `R` — Result.
- `N` — Number.
- `S` hoặc `U` — type parameter bổ sung.

Có thể dùng tên dài, ví dụ `class Converter<Source, Target>`; tên rõ hơn đôi khi giúp các API có nhiều type parameters dễ đọc.

### 2.2. Một generic class không phải được copy nguyên source cho từng type argument

`Box<String>` và `Box<Integer>` không khiến Java tạo hai class definitions độc lập như hai bản sao `StringBox` và `IntegerBox`. Java generics triển khai chủ yếu qua **type erasure**, cho phép compiler kiểm tra kiểu và chèn casts/bridges cần thiết mà không tạo một class runtime riêng cho mỗi reference-type argument.

### 2.3. Generic parameter là type, không phải value

`Box<String>` chọn kiểu của data được lưu; nó không yêu cầu Box chứa String "String". Type argument không phải một tham số constructor như `new Box<>("Hello")`.

## 3. Chương trình hoàn chỉnh 1: Object + cast so với generic class

Tệp **`GenericVsObjectDemo.java`**:

~~~java
public class GenericVsObjectDemo {
    static final class ObjectSlot {
        private Object value;

        ObjectSlot(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }

        void set(Object value) {
            this.value = value;
        }
    }

    static final class Slot<T> {
        private T value;

        Slot(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        ObjectSlot old = new ObjectSlot("Java");
        String first = (String) old.get();
        System.out.println("Object value = " + first);

        old.set(42);
        try {
            String wrong = (String) old.get();
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("Wrong cast rejected");
        }

        Slot<String> safe = new Slot<>("Java");
        String second = safe.get();
        System.out.println("Generic value = " + second);

        safe.set("Core");
        System.out.println("Updated = " + safe.get());

        Slot<Integer> numeric = new Slot<>(17);
        System.out.println("Number = " + numeric.get());

        // safe.set(42); // Cố ý không hợp lệ ở compile time.
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericVsObjectDemo.java
java GenericVsObjectDemo
~~~

**Stdout chính xác:**

~~~text
Object value = Java
Wrong cast rejected
Generic value = Java
Updated = Core
Number = 17
~~~

### 3.1. Rủi ro của ObjectSlot

`ObjectSlot` có setter `set(Object)` nên cả String và Integer đều hợp lệ với compiler. Variable `old` ban đầu chứa String nhưng có thể được gán Integer sau đó. Cast `(String) old.get()` thất bại ở runtime.

### 3.2. Giá trị của Slot<String>

`Slot<String>` ràng buộc `set` nhận String và `get` trả String theo source-level type checking. Lệnh `safe.set(42)` (nếu bỏ chú thích) **không biên dịch**; lỗi được phát hiện gần nơi đưa dữ liệu sai vào container.

### 3.3. Generic code vẫn không thay thế validation

Một `Slot<String>` có thể chứa chuỗi trống, null hoặc dữ liệu không đúng định dạng nếu class/API cho phép. Type safety bảo đảm **phạm vi kiểu**, không tự bảo đảm business invariants như độ dài, regex hoặc trạng thái hợp lệ.

## 4. Cú pháp khai báo một generic class

Một generic class có cú pháp cơ bản:

~~~java
class Holder<T> {
    private T item;

    Holder(T initialValue) {
        this.item = initialValue;
    }

    public T get() {
        return item;
    }

    public void set(T next) {
        item = next;
    }
}
~~~

`<T>` sau tên Holder **khai báo type parameter**. T có thể được dùng trong instance fields, instance methods, constructor parameters và return types.

### 4.1. T ở constructor không phải type parameter riêng

`Holder(T initialValue)` sử dụng T **đã được khai báo bởi Holder<T>**. Constructor không cần và không nên khai báo lại `<T>` trừ khi bạn thực sự muốn một independent constructor type parameter với semantics khác.

### 4.2. Khi tạo object, type argument được chọn như thế nào?

~~~java
Holder<String> title = new Holder<String>("Java");
Holder<Integer> amount = new Holder<>(20);
~~~

Dạng đầu viết đầy đủ type arguments cả ở variable và construction expression. Dạng sau dùng toán tử **diamond `<>`** để compiler suy luận constructor type arguments từ target type và context.

### 4.3. Type parameter có scope nào?

`T` thuộc generic class declaration, được dùng cho instance member signatures. Nó không trở thành một Java runtime variable.

Ví dụ `private T item` là field của từng Holder object, không phải một field có runtime type String trong Holder<String> và Integer trong Holder<Integer> theo cách class file chuyên biệt hóa.

### 4.4. Không thể gán arbitrary type cho T

`Holder<String>.set(Integer)` không được chấp nhận chỉ vì Integer cũng là Object. Type arguments phải hợp với generic API contract. Nếu bạn thật sự cần lưu heterogeneous values, hãy thiết kế `Holder<Object>` hoặc một abstraction typed union/sealed hierarchy phù hợp; hiểu rằng compiler sẽ ít thông tin hơn khi đọc.

## 5. Chương trình hoàn chỉnh 2: generic Box có get, set và factory

Tệp **`GenericBoxDemo.java`**:

~~~java
public class GenericBoxDemo {
    static final class Box<T> {
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

        static <E> Box<E> of(E value) {
            return new Box<>(value);
        }
    }

    public static void main(String[] args) {
        Box<String> word = Box.of("Java");
        Box<Integer> year = Box.of(17);

        System.out.println("Word = " + word.get());
        System.out.println("Year = " + year.get());

        word.set("Generics");
        year.set(year.get() + 1);

        System.out.println("Updated word = " + word.get());
        System.out.println("Updated year = " + year.get());
        System.out.println("Word length = " + word.get().length());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericBoxDemo.java
java GenericBoxDemo
~~~

**Stdout chính xác:**

~~~text
Word = Java
Year = 17
Updated word = Generics
Updated year = 18
Word length = 8
~~~

### 5.1. Factory static không dùng T của class

`static <E> Box<E> of(E value)` khai báo một **method type parameter E riêng**. Static method không có một instance Box<T> cụ thể để sử dụng T của class, nên phải khai báo type parameter riêng nếu muốn factory generic.

### 5.2. Trình biên dịch suy luận kiểu ở đâu?

`Box.of("Java")` suy luận E = String; `Box.of(17)` áp dụng autoboxing thành Integer. Target variable type còn cung cấp context cho inference. Trong code phức tạp, bạn có thể viết `Box.<String>of("Java")` để cung cấp explicit method type argument.

### 5.3. Tại sao `word.get().length()` hợp lệ?

Compiler biết kiểu trả về của `word.get()` là String, nên method `String.length()` có thể gọi trực tiếp không cast. Với `Box<Object>`, gọi `get().length()` không compile vì Object không khai báo method length().

### 5.4. Thêm validation ở generic constructor

Một Box có thể reject null bằng `Objects.requireNonNull(value)` nếu contract yêu cầu. Nhưng không nên bắt mọi generic Box phải non-null mặc định nếu use cases cần biểu diễn empty optional state. Hãy chọn invariant và mô tả nó trong API.

## 6. Một lớp có nhiều tham số kiểu: `Pair<K,V>`

Generics không giới hạn một type parameter:

~~~java
class Pair<K, V> {
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
~~~

`Pair<String,Integer>` nghĩa là key String, value Integer. `Pair<Integer,String>` là parameterized type khác về kiểm tra kiểu, dù cả hai đều dùng cùng generic class Pair ở runtime sau erasure.

### 6.1. Tại sao cần hai parameters?

Một container Map entry, tuple, converter, result wrapper hoặc message envelope thường có hai hoặc nhiều thành phần khác kiểu. Viết `Pair<Object,Object>` sẽ làm mất quan hệ kiểu của từng vị trí, khiến caller phải cast.

### 6.2. K và V là độc lập

`K` không bắt buộc giống `V`. Hai type parameters cho phép compiler kiểm tra key và value riêng. Cũng có thể khai báo `Pair<String,String>` nếu cả hai vị trí đều String.

### 6.3. Khi nào dùng record thay class?

Trong Java 17:

~~~java
record Pair<K, V>(K key, V value) {
}
~~~

là **generic record**, có canonical constructor, component accessors `key()`/`value()`, generated equality/hashCode/toString. Nếu data carrier đơn giản và value-style semantics phù hợp, generic record có thể gọn hơn ordinary generic class.

Nhưng nếu holder cần mutable setters/lifecycle, ordinary generic class có thể phù hợp hơn.

## 7. Chương trình hoàn chỉnh 3: generic Pair và generic record

Tệp **`GenericPairDemo.java`**:

~~~java
public class GenericPairDemo {
    static final class Pair<K, V> {
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

        Pair<V, K> swapped() {
            return new Pair<>(value, key);
        }
    }

    record Entry<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("Lan", 9);
        Pair<Integer, String> inverse = score.swapped();

        System.out.println("Key = " + score.key());
        System.out.println("Value = " + score.value());
        System.out.println("Swapped = " + inverse.key()
                + ":" + inverse.value());

        Entry<String, Boolean> flag = new Entry<>("ready", true);
        System.out.println("Record = " + flag);
        System.out.println("Record key = " + flag.key());
        System.out.println("Record value = " + flag.value());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericPairDemo.java
java GenericPairDemo
~~~

**Stdout chính xác:**

~~~text
Key = Lan
Value = 9
Swapped = 9:Lan
Record = Entry[key=ready, value=true]
Record key = ready
Record value = true
~~~

### 7.1. `swapped()` giữ chính xác quan hệ kiểu

Với `Pair<K,V>`, method trả `Pair<V,K>`. Lúc gọi trên `Pair<String,Integer>`, compiler suy ra return type `Pair<Integer,String>`. Không cast, không xử lý runtime type tag.

### 7.2. Generic record cũng có type arguments

`Entry<String,Boolean>` có K String và V Boolean. Record's fields vẫn final; nếu K/V là mutable object thì record không tự deep-copy.

### 7.3. Những loại nào được truyền làm type argument?

Reference types như String, Integer, Boolean, List<String>, User, Interface và parameterized types đều hợp lệ nếu thỏa bounds. Primitive types `int`, `boolean` không thể trực tiếp là type arguments; dùng wrappers và autoboxing khi phù hợp.

## 8. Type safety ở thời điểm biên dịch — mục đích số một

Điểm mạnh của generic class không nằm ở việc JVM tạo loại object “siêu an toàn”, mà ở **compiler kiểm tra thống nhất type arguments tại các vị trí có quan hệ**.

Ví dụ:

~~~java
Box<String> title = Box.of("Core");
// title.set(123);          // Không biên dịch: Integer không phải String.
String text = title.get();  // Không cần cast.

Box<Integer> count = Box.of(5);
// String wrong = count.get(); // Không biên dịch.
~~~

Các dòng lỗi đều là compile-time type mismatch.

### 8.1. Không thay runtime business validation

`Box<String>` vẫn có thể chứa chuỗi không đúng định dạng; generic không kiểm tra "Số tài khoản phải có 10 chữ số". Dùng validation, value objects hoặc constructor invariants cho business constraints.

### 8.2. Loại bỏ cast không cần thiết

Với Object container, mỗi lần đọc một giá trị cần biết external convention rồi cast. Generic container đưa thông tin loại dữ liệu vào API, giảm casts và nguy cơ `ClassCastException` do sai kỳ vọng.

### 8.3. “Compile-time safe” không đồng nghĩa tuyệt đối không thể lỗi

Raw types, unchecked casts, reflection và deserialization không kiểm soát có thể tạo **heap pollution**: một parameterized variable trỏ đến object chứa dữ liệu không đúng type argument. Vì vậy cần tránh unchecked operations hoặc giữ chúng ở một boundary được kiểm soát và kiểm thử.

### 8.4. Type parameter khác generic declaration of value restrictions

Một API `Repository<ID,Entity>` có thể diễn đạt rằng save(ID,Entity) phải phối hợp đúng ID/Entity types; nhưng nó không bảo đảm ID tồn tại, Entity thuộc customer nào hoặc database transaction thành công. Compile-time type constraints là một tầng của correctness.

## 9. Generic class và generic method là hai khái niệm khác

`class Box<T>` khai báo **type parameter cấp class** T. Mọi instance methods/fields liên quan T của object đó dựa trên type argument của Box.

Một **generic method** có type parameter riêng:

~~~java
static <U> U identity(U value) {
    return value;
}
~~~

Method này có thể xuất hiện trong class generic hoặc non-generic. `<U>` đứng trước return type và thuộc scope của method declaration.

### 9.1. Method dùng T từ class

~~~java
class Envelope<T> {
    private final T value;

    Envelope(T value) {
        this.value = value;
    }

    T read() {
        return value;
    }
}
~~~

`read()` không cần `<T>` ở declaration, vì T đã là class type parameter.

### 9.2. Method có independent U

~~~java
class Envelope<T> {
    private final T value;

    Envelope(T value) {
        this.value = value;
    }

    <U> String joinWith(U other) {
        return value + "|" + other;
    }
}
~~~

Ở đây T do Envelope instance quyết định, còn U được inference từ mỗi invocation `joinWith`. Nó có thể là String, Integer hoặc arbitrary reference type ở các lần gọi khác nhau.

### 9.3. Static methods không dùng class T

Một static method thuộc class, không thuộc riêng `Box<String>` hay `Box<Integer>` instance; do vậy **không thể dùng unbound class type parameter T** trong static method/field declaration.

Sai:

~~~java
class Invalid<T> {
    static T current; // Không biên dịch.
    static T create() { return null; } // Không biên dịch.
}
~~~

Đúng là tạo **method type parameter**:

~~~java
class Factory {
    static <T> T first(T left, T right) {
        return left;
    }
}
~~~

## 10. Chương trình hoàn chỉnh 4: type parameters của class và method

Tệp **`GenericMethodScopeDemo.java`**:

~~~java
public class GenericMethodScopeDemo {
    static final class Envelope<T> {
        private final T item;

        Envelope(T item) {
            this.item = item;
        }

        T read() {
            return item;
        }

        <U> String join(U other) {
            return item + "|" + other;
        }

        static <E> Envelope<E> of(E item) {
            return new Envelope<>(item);
        }
    }

    static <A> A choose(boolean pickFirst, A first, A second) {
        return pickFirst ? first : second;
    }

    public static void main(String[] args) {
        Envelope<String> letter = Envelope.of("A");

        System.out.println("Item = " + letter.read());
        System.out.println("Join number = " + letter.join(3));
        System.out.println("Join text = " + letter.join("B"));
        System.out.println("Choose = "
                + choose(false, "left", "right"));

        Envelope<Integer> count = Envelope.of(9);
        System.out.println("Count = " + count.read());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericMethodScopeDemo.java
java GenericMethodScopeDemo
~~~

**Stdout chính xác:**

~~~text
Item = A
Join number = A|3
Join text = A|B
Choose = right
Count = 9
~~~

### 10.1. U thay đổi theo từng method invocation

Một Envelope<String> có thể gọi `join(3)` với U=Integer và `join("B")` với U=String. Điều này không biến Envelope<String> thành Envelope<Object>.

### 10.2. E của static factory là independent

Factory dùng `<E>` để chọn type argument cho object được tạo. Không có `this` hoặc instance T trong static method.

### 10.3. Generic method có thể nằm ngoài generic class

`choose` khai báo `<A>` trong ordinary class GenericMethodScopeDemo; class wrapper không cần tự generic. Đây là lý do cần phân biệt “lớp generic” với “phương thức generic”.

## 11. Bounded type parameters: giới hạn T phải là một nhóm kiểu

Một unbounded `T` được xem có upper bound mặc định Object. Compiler chỉ cho phép gọi methods được bảo đảm bởi bound, không cho dùng methods dành riêng cho một type arbitrary.

Ví dụ sai:

~~~java
class Metric<T> {
    double twice(T value) {
        return value.doubleValue() * 2; // Không compile.
    }
}
~~~

`T` không bảo đảm có `doubleValue()`. Muốn ràng buộc T là Number hoặc subtype:

~~~java
class Metric<T extends Number> {
    private final T number;

    Metric(T number) {
        this.number = number;
    }

    double twice() {
        return number.doubleValue() * 2;
    }
}
~~~

### 11.1. `extends` trong generic bound dùng với cả interfaces

Cú pháp `T extends Comparable<T>` không có nghĩa T phải extends một class tên Comparable; Comparable là interface. `extends` ở type bound diễn đạt subtype constraint cho class **hoặc interface**.

### 11.2. Multiple bounds

~~~java
class OrderedNumber<T extends Number & Comparable<T>> {
    private final T value;

    OrderedNumber(T value) {
        this.value = value;
    }

    boolean greaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
~~~

Bound đầu có thể là class, các bounds tiếp theo phải là interfaces, và class bound nếu có phải đứng trước interface bounds. T phải đồng thời là Number subtype và implement Comparable<T>.

### 11.3. Bound không phải type argument

`<T extends Number>` là **type parameter declaration** với bound, không phải `<Number>` ở chỗ dùng. Client có thể truyền Integer, Double hoặc một Number subtype đáp ứng bound.

### 11.4. Bound không có nghĩa mọi Number có thể so sánh

`Number` không khai báo `compareTo`. Nếu algorithm thực sự cần so ordering, thêm Comparable bound hoặc truyền Comparator; đừng cast Number tùy tiện rồi dựa vào runtime type.

## 12. Chương trình hoàn chỉnh 5: Number bound và multiple bounds

Tệp **`GenericBoundedDemo.java`**:

~~~java
public class GenericBoundedDemo {
    static final class NumericBox<N extends Number> {
        private final N number;

        NumericBox(N number) {
            this.number = number;
        }

        double doubled() {
            return number.doubleValue() * 2;
        }
    }

    static <N extends Number & Comparable<N>>
    N larger(N left, N right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        NumericBox<Integer> integer = new NumericBox<>(7);
        NumericBox<Double> decimal = new NumericBox<>(2.5);

        System.out.println("Integer doubled = " + integer.doubled());
        System.out.println("Double doubled = " + decimal.doubled());
        System.out.println("Larger int = " + larger(4, 9));
        System.out.println("Larger decimal = " + larger(3.0, 1.5));

        // NumericBox<String> bad = new NumericBox<>("7");
        // Không biên dịch: String không extends Number.
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericBoundedDemo.java
java GenericBoundedDemo
~~~

**Stdout chính xác:**

~~~text
Integer doubled = 14.0
Double doubled = 5.0
Larger int = 9
Larger decimal = 3.0
~~~

### 12.1. Double và Integer đều là reference types

`NumericBox<Integer>` và `NumericBox<Double>` là hợp lệ; `NumericBox<int>` không hợp lệ vì primitive không thể là type argument. Autoboxing giúp chuyển `7` sang Integer khi tạo object.

### 12.2. Type inference của larger

Khi gọi `larger(4,9)`, compiler chọn Integer, đáp ứng Number và Comparable<Integer>. Với `larger(3.0,1.5)`, chọn Double.

### 12.3. Vì sao `doubleValue()` không trả exact monetary amount?

Number.doubleValue có thể mất độ chính xác đối với một số kiểu/giá trị. Với tiền, nên dùng BigDecimal và phép toán domain-specific phù hợp. Example chỉ minh họa bound và method access, không phải thư viện tính tiền.

## 13. Quan hệ kế thừa: subtype không tự chuyển thành subtype của generic class

Một trong những quy tắc quan trọng nhất của Java generics là **invariance**:

~~~java
Integer integer = 1;
Number number = integer; // Hợp lệ: Integer extends Number.
~~~

nhưng:

~~~java
java.util.List<Integer> integers =
        new java.util.ArrayList<>();

java.util.List<Number> numbers = integers; // Cố ý không biên dịch.
~~~

Dù Integer là subtype của Number, **List<Integer> không phải subtype của List<Number>**.

### 13.1. Tại sao Java không cho phép?

Giả sử code trên được phép:

~~~java
List<Integer> ints = new ArrayList<>();
List<Number> nums = ints; // Giả định sai.
nums.add(3.14);           // Double cũng là Number.
Integer value = ints.get(0); // Lúc này bị phá type safety!
~~~

Invariance ngăn ta đưa Double vào một List<Integer> thông qua alias List<Number>. Đây là lý do logic chứ không chỉ là compiler bất tiện.

### 13.2. Generic class của subtype và class inheritance là hai trục khác nhau

`Integer extends Number` thuộc hierarchy của type argument. `Box<Integer>` và `Box<Number>` là parameterized types khác, và không tự có subclass relationship.

Bạn có thể tạo một ordinary subclass:

~~~java
class IntegerBox extends Box<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
~~~

Đây là fragment với Box có accessible constructor. IntegerBox **is-a Box<Integer>**, không phải Box<Number>.

### 13.3. Dùng wildcards cho variance ở API boundaries

Nếu method chỉ đọc dữ liệu Number:

~~~java
static double sum(List<? extends Number> items)
~~~

nó có thể nhận List<Integer>, List<Double>, List<BigDecimal>... mà không cần List<Number>.

Nếu method cần nơi nhận Integer:

~~~java
static void addOne(List<? super Integer> destination)
~~~

nó có thể nhận List<Integer>, List<Number> hoặc List<Object>. Phần sau giải thích cụ thể.

## 14. Wildcards và quy tắc PECS: Producer Extends, Consumer Super

**Wildcard** `?` không phải tên của một type parameter giống T; nó là một **unknown type argument** với bound tùy trường hợp.

Ba dạng thường dùng:

- `List<?>`: List của một kiểu element chưa biết. Có thể đọc phần tử dưới type Object; không thể thêm arbitrary non-null element vì unknown element type.
- `List<? extends Number>`: Một List của một subtype nào đó của Number. Đọc phần tử như Number an toàn; không thể thêm arbitrary Number.
- `List<? super Integer>`: Một List của một supertype nào đó của Integer. Có thể thêm Integer; đọc phần tử tổng quát nhất an toàn là Object.

### 14.1. Producer Extends

Khi API **đọc values** từ source container:

~~~java
static double sum(List<? extends Number> source) {
    double result = 0;
    for (Number n : source) {
        result += n.doubleValue();
    }
    return result;
}
~~~

Nếu source là List<Integer>, List<Double>, compiler vẫn biết mọi elements là Number subtype, nên `Number.doubleValue()` hợp lệ.

**Không thể tự do thêm Number**:

~~~java
List<? extends Number> source = new ArrayList<Integer>();
// source.add(3.14); // Không biên dịch.
~~~

Compiler không biết actual element type là Integer, Double hay subtype nào. Cho thêm Double vào List<Integer> sẽ phá type safety.

### 14.2. Consumer Super

Khi API **ghi Integer values** vào destination:

~~~java
static void addDefaults(List<? super Integer> destination) {
    destination.add(1);
    destination.add(2);
}
~~~

`List<Integer>`, `List<Number>` và `List<Object>` đều có thể nhận Integer. Nhưng đọc `destination.get(0)` chỉ được xem là Object nếu không biết type argument chính xác.

### 14.3. Unbounded wildcard

`List<?>` thích hợp cho APIs chỉ cần iteration, size, contains và không cần giả định element type. Nó không đồng nghĩa với `List<Object>`.

### 14.4. PECS không phải thay thế toàn bộ T

Wildcard đặc biệt hữu ích tại method signatures. Nếu method cần thiết lập quan hệ giữa hai vị trí kiểu (ví dụ source và target cùng T), **named type parameter `<T>`** diễn đạt quan hệ rõ hơn `?` độc lập.

## 15. Chương trình hoàn chỉnh 6: đọc và ghi với wildcards

Tệp **`GenericVarianceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericVarianceDemo {
    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    static void addIntegers(List<? super Integer> output) {
        output.add(3);
        output.add(4);
    }

    static <T> void copy(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> ints = List.of(1, 2);
        List<Number> numbers = new ArrayList<>();

        addIntegers(numbers);
        System.out.println("After add = " + numbers);
        System.out.println("Sum integers = " + sum(ints));

        copy(numbers, ints);
        System.out.println("After copy = " + numbers);
        System.out.println("Total = " + sum(numbers));

        List<Object> objects = new ArrayList<>();
        copy(objects, ints);
        System.out.println("Objects = " + objects);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericVarianceDemo.java
java GenericVarianceDemo
~~~

**Stdout chính xác:**

~~~text
After add = [3, 4]
Sum integers = 3.0
After copy = [3, 4, 1, 2]
Total = 10.0
Objects = [1, 2]
~~~

### 15.1. Vì sao copy cần vừa extends vừa super?

`source` sản xuất T values → `? extends T`. `destination` nhận T values → `? super T`. Đây là một ứng dụng thực tế của **PECS** trong generic method. Không phải lúc nào cả hai args đều phải có type parameter chính xác như `List<T>`.

### 15.2. Vì sao `numbers` chứa Integer trong List<Number>?

Integer là subtype Number, nên thêm Integer vào List<Number> hợp lệ. Nhưng List<Integer> không thể được gán nguyên reference vào biến List<Number>. **Thêm một element subtype** khác hoàn toàn với **chuyển một parameterized container type**.

### 15.3. Wildcard không phải immutable view

Một variable `List<? extends Number>` không thể gọi add(Number) tùy ý, nhưng referent list vẫn có thể mutable thông qua alias khác, và một số operations như remove/clear vẫn có thể hợp lệ. Read-only theo generic add restriction **không đồng nghĩa object List immutable**.

## 16. Generic class kế thừa và triển khai generic interface

Generic type parameters có thể được **giữ lại**, **chuyên biệt hóa**, hoặc **được truyền sang generic superclass/interface**.

### 16.1. Kế thừa mà vẫn generic

~~~java
class Base<T> {
    T value;

    Base(T value) {
        this.value = value;
    }
}

class Child<T> extends Base<T> {
    Child(T value) {
        super(value);
    }
}
~~~

Child<T> tiếp tục là generic class. `Child<String>` là subtype của `Base<String>`.

### 16.2. Kế thừa với type argument cố định

~~~java
class TextChild extends Base<String> {
    TextChild(String text) {
        super(text);
    }
}
~~~

TextChild không generic; nó cố định superclass type argument là String. Một `TextChild` có thể được gán cho `Base<String>`, không phải `Base<Integer>`.

### 16.3. Generic interface

~~~java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}

class UserRepository implements Repository<Long, User> {
    @Override
    public User find(Long id) {
        return ...;
    }
}
~~~

Đây là **conceptual fragment**, dấu ellipsis biểu diễn body chưa viết nên không độc lập. Ý nghĩa là UserRepository cố định ID=Long, ENTITY=User khi implement interface; `find` dùng Long input và User output. Chương trình chạy đầy đủ ở phần sau sử dụng Optional và Map.

### 16.4. Không được implement cùng generic interface với hai args không tương thích

Một class không thể simultaneously implement `Comparable<String>` và `Comparable<Integer>` như hai instantiations độc lập nếu gây same erasure/interface conflict. Java type system tránh một object có hai conflicting specialized methods trên cùng erased signature.

## 17. Chương trình hoàn chỉnh 7: generic inheritance

Tệp **`GenericInheritanceDemo.java`**:

~~~java
public class GenericInheritanceDemo {
    static class Store<T> {
        private final T value;

        Store(T value) {
            this.value = value;
        }

        T read() {
            return value;
        }
    }

    static final class TextStore extends Store<String> {
        TextStore(String value) {
            super(value);
        }

        int length() {
            return read().length();
        }
    }

    static final class FlexibleStore<T> extends Store<T> {
        FlexibleStore(T value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Store<String> text = new TextStore("Core");
        Store<Integer> count = new FlexibleStore<>(7);

        System.out.println("Text = " + text.read());
        System.out.println("Integer = " + count.read());
        System.out.println("Length = "
                + new TextStore("Java").length());
        System.out.println("Different runtime classes = "
                + (text.getClass() != count.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericInheritanceDemo.java
java GenericInheritanceDemo
~~~

**Stdout chính xác:**

~~~text
Text = Core
Integer = 7
Length = 4
Different runtime classes = true
~~~

### 17.1. Hai runtime classes khác nhau vì **hai class declarations**

TextStore và FlexibleStore là những classes khác nhau. Điều đó **không phủ định type erasure**. Nếu tạo `new FlexibleStore<String>` và `new FlexibleStore<Integer>`, cả hai có cùng raw runtime class FlexibleStore.

### 17.2. Compile-time inherited return type

`Store<String>.read()` được type-checked như trả String, dù erased method implementation có thể dùng Object. Compiler thêm bridges/casts khi cần để bảo đảm type system semantics.

### 17.3. Không gán giữa hai Store argument types

`Store<String>` và `Store<Object>` không tự có subtype relation. Nếu muốn read-only API chấp nhận nhiều Store<T>, có thể dùng `Store<?>` hoặc generic bound, tùy operation.

## 18. Type erasure: một declaration, nhiều type arguments

Với Java generics, compiler **kiểm tra kiểu khi biên dịch**, sau đó thực hiện *type erasure*. `Box<String>` và `Box<Integer>` không trở thành hai Java runtime classes khác nhau. Unbounded `T` thường bị xóa về `Object` trong field/method signatures; bound phù hợp có thể thay đổi erased type. Compiler có thể thêm casts và bridge methods để bảo toàn semantics; metadata generic trên declarations vẫn có thể đọc qua reflection.

## 19. Chương trình chạy: quan sát runtime class của hai Box

Lưu **`GenericRuntimeBasicsDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class GenericRuntimeBasicsDemo {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    public static void main(String[] args) throws Exception {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(17);
        Field field = Box.class.getDeclaredField("value");

        System.out.println(text.get());
        System.out.println(number.get());
        System.out.println(text.getClass() == number.getClass());
        System.out.println(field.getType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRuntimeBasicsDemo.java
java GenericRuntimeBasicsDemo
~~~

~~~text
Java
17
true
Object
~~~

Vì field có type variable `T` không bound, reflective erased field type là `Object`. Dù runtime class của hai Box giống nhau, compiler vẫn biết `text.get()` trả `String` và `number.get()` trả `Integer` từ type arguments trong source. Reflection có thể cho biết class **khai báo T**, chứ không suy được type argument riêng của một plain Box instance chỉ qua `getClass()`.

## 20. Raw type và unchecked là lối tắt có rủi ro

`Box raw = typedBox` sử dụng *raw type* vì tương thích legacy code. Qua raw alias, lời gọi như `raw.set(42)` có thể phát sinh unchecked warning và đưa sai element type vào Box vốn được sử dụng qua `Box<String>`. `ClassCastException` có thể xuất hiện muộn tại một typed read. `Box<?>` biểu diễn box với element type không rõ một cách type-safe hơn raw Box khi chỉ cần đọc như Object; nó **không** sửa được dữ liệu đã bị làm bẩn trước đó.

## 21. Kiểm tra warning trước khi bỏ kiểm kiểu

Hãy dùng `javac -Xlint:rawtypes -Xlint:unchecked File.java` để xem vị trí legacy API không an toàn. Chỉ dùng `@SuppressWarnings("unchecked")` trong scope hẹp khi đã chứng minh invariant ở boundary và có tests cho dữ liệu sai kiểu. Cơ chế bridge methods, raw invocation, erasure và heap pollution có nhiều edge cases được học sâu riêng; trong bài giới thiệu này, điều cần nắm là **compile-time generic safety khác runtime class identity**.

## 22. Một số giới hạn cú pháp quan trọng của generic class

Type arguments phải là reference types: `Box<Integer>` hợp lệ còn `Box<int>` không hợp lệ. Java không cho dùng erased type variable `T` như runtime constructor/class literal/array component trực tiếp:

~~~java
class Invalid<T> {
    // T obj = new T();                      // Lỗi biên dịch.
    // T[] arr = new T[5];                   // Lỗi biên dịch.
    // Class<T> type = T.class;              // Lỗi biên dịch.
    // static T shared;                      // Lỗi biên dịch.
}
// List<String>[] a = new List<String>[3];   // Lỗi biên dịch.
~~~

Đây là **snippet minh họa các trường hợp sai được comment lại**, không phải chương trình runnable thể hiện lỗi compiler. Các giải pháp tùy nhu cầu: nhận sẵn object, truyền `Supplier<? extends T>` hoặc factory, dùng `List<T>`, array factory hoặc `Class<T>` type token. Generic method ở ngữ cảnh static cần type parameter **riêng** (`static <U> U identity(U x)`). `instanceof List<String>` cũng không dùng như phép kiểm runtime element type tổng quát.

## 23. Runtime type token: chọn khi có external Object input

Nếu API thật sự cần runtime validation, có thể nhận `Class<T>` và sử dụng `type.cast(candidate)`:

~~~java
final class CheckedBox<T> {
    private final T value;
    CheckedBox(Class<T> type, Object candidate) {
        this.value = type.cast(candidate);
    }
    T get() { return value; }
}
~~~

Đây là **mảnh khai báo**, không có `main`. Token `String.class` kiểm được String, nhưng `Class<List<String>>` không có một runtime Class object reify nested generic arguments. Reflection/type descriptors phức tạp hơn chỉ cần khi use case đòi hỏi. Type token **không vô hiệu hóa type erasure**; nó bổ sung kiểm tra theo API contract. Những ràng buộc `new T()`, generic arrays, `T.class` và runtime checks sẽ được triển khai sâu trong bài riêng, còn ví dụ Box cơ bản chỉ cần biết **khi nào không thể dựa vào T ở runtime**.

## 24. Generic API: repository, ID và entity

Một use case phổ biến trong domain services:

~~~java
interface Repository<ID, ENTITY> {
    void save(ID id, ENTITY entity);
    java.util.Optional<ENTITY> find(ID id);
}
~~~

Hai type parameters giúp compiler ràng buộc:

- ID type, ví dụ Long hoặc String.
- ENTITY type, ví dụ User hoặc Order.
- `save` nhận đúng cặp type.
- `find` trả Optional<ENTITY>, không phải Object.
- Caller không cần cast từ Object về User.

### 24.1. Tại sao dùng Optional<ENTITY>?

Tra cứu theo ID có thể không tìm thấy object. Trả Optional mô tả missing value trực tiếp trong API thay vì dùng null mơ hồ. Đây là một design choice; không bắt buộc mọi generic repository đều dùng Optional.

### 24.2. Khi nào nên thêm bounds?

Nếu mọi IDs phải là Comparable, có thể khai báo `ID extends Comparable<ID>`, nhưng chỉ thêm bound nếu implementation thực sự cần compareTo. Nếu dùng HashMap ID keys, yêu cầu phù hợp là equals/hashCode semantics của keys, không nhất thiết Comparable.

### 24.3. Generic type safety không sửa business ownership

Repository<String,User> đảm bảo type của ID và Entity ở compile time; nó không tự bảo đảm quyền truy cập user, transaction boundaries hoặc entity lifecycle. Những concerns đó cần application/services policy.

## 25. Chương trình hoàn chỉnh 11: generic Repository<ID,ENTITY>

Tệp **`GenericRepositoryDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class GenericRepositoryDemo {
    interface Repository<ID, ENTITY> {
        void save(ID id, ENTITY entity);
        Optional<ENTITY> find(ID id);
    }

    static final class MemoryRepository<ID, ENTITY>
            implements Repository<ID, ENTITY> {
        private final Map<ID, ENTITY> rows = new HashMap<>();

        @Override
        public void save(ID id, ENTITY entity) {
            rows.put(id, entity);
        }

        @Override
        public Optional<ENTITY> find(ID id) {
            return Optional.ofNullable(rows.get(id));
        }
    }

    record User(String name) {
    }

    public static void main(String[] args) {
        Repository<String, User> users = new MemoryRepository<>();

        users.save("u-1", new User("Lan"));

        System.out.println("Found = " + users.find("u-1"));
        System.out.println("Missing = " + users.find("u-2"));

        User result = users.find("u-1").orElseThrow();
        System.out.println("Name = " + result.name());

        // users.save(1, new User("An")); // Không biên dịch.
        // users.save("u-3", "An"); // Không biên dịch.
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericRepositoryDemo.java
java GenericRepositoryDemo
~~~

**Stdout chính xác:**

~~~text
Found = Optional[User[name=Lan]]
Missing = Optional.empty
Name = Lan
~~~

### 25.1. ID và ENTITY có vai trò riêng

`Repository<String,User>` định nghĩa ID=String và ENTITY=User. Cả `save` lẫn `find` dùng cùng ID type và ENTITY type ở API; đổi ID thành Integer hoặc Entity thành String bị compiler từ chối.

### 25.2. Implementation vẫn generic

`MemoryRepository<ID,ENTITY>` giữ hai type parameters, và `Map<ID,ENTITY>` sử dụng cùng quan hệ kiểu. Bạn có thể tạo một repository khác cho `Long,Order` mà không cần copy source implementation.

### 25.3. Output không phụ thuộc HashMap iteration order

Demo chỉ thực hiện `get` theo exact keys, không duyệt HashMap entries. Kết quả vì thế deterministic cho data đã lưu.

### 25.4. Null behavior

`Optional.ofNullable(rows.get(id))` trả empty nếu mapping không có hoặc value null. HashMap có thể lưu null, nhưng API ở đây có thể muốn reject null entities trong `save` để phân biệt missing với present-null. Một production repository nên công bố rõ invariant này.

## 26. Tái sử dụng code generic vẫn cần thiết kế object tốt

Một generic class nên mang **một abstraction thực sự**, không chỉ quấn mọi object trong `Holder<T>` bất kể mục đích.

### 26.1. Tái sử dụng có kiểm soát

Ví dụ reusable cache interface:

~~~java
interface Cache<K, V> {
    void put(K key, V value);
    V get(K key);
}
~~~

Đây là fragment. Generic type parameters mô tả relation key→value. Những concerns như eviction, expiry, null contract và concurrency vẫn cần định nghĩa trong implementation.

### 26.2. Đừng dùng Object khi generic diễn đạt được quan hệ kiểu

Một `Map<Object,Object>` có thể chứa bất cứ thứ gì nhưng làm suy yếu checks. Nếu domain có IDs String và entities User, dùng `Map<String,User>` giúp tránh đưa sai key/value.

### 26.3. Đừng generic hóa domain vô ích

`class Invoice<T>` không có ý nghĩa nếu T không dùng để diễn đạt invariant/capability thật. Mỗi type parameter làm API phức tạp hơn, có thể gây inference khó và error messages dài. Type parameter chỉ nên có khi **kiểu khác nhau vẫn cùng abstraction hợp lý**.

### 26.4. Generic ở boundary, domain ở bên trong

Bạn có thể dùng generic framework classes (`Repository<ID,T>`, `Result<T>`), nhưng domain model `User`/`Order` vẫn có fields và business rules riêng. Đừng ép mọi domain class extends một generic base có state/lifecycle không cần thiết.

### 26.5. Constructor validation và defensive copying

Một `Container<List<String>>` không tự chụp snapshot; generic class có thể giữ mutable List reference như bình thường. Nếu cần snapshot, dùng `List.copyOf` ở API boundary, chú ý mutable elements. Generics kiểm tra **type**, không bảo đảm **immutability**.

## 27. Generic class, record, interface và enum trong Java 17

### 27.1. Generic record

~~~java
record Response<T>(int status, T body) {
}
~~~

Hợp lệ. `Response<String>` chứa body String; `Response<User>` chứa User.

### 27.2. Generic interface

~~~java
interface Mapper<S, T> {
    T map(S source);
}
~~~

Hợp lệ. Một class có thể implements `Mapper<String,Integer>` và trả Integer từ String theo logic.

### 27.3. Enum không khai báo generic type parameters

Không thể khai báo `enum State<T> { ... }` như generic enum type trong Java. Enum constants là tập values của một enum type cố định. Tuy nhiên enum vẫn có thể implements một **generic interface với concrete type arguments**, nếu hợp lệ:

~~~java
interface Coded<T> {
    T code();
}

enum Flag implements Coded<Integer> {
    OFF(0), ON(1);

    private final int value;

    Flag(int value) {
        this.value = value;
    }

    public Integer code() {
        return value;
    }
}
~~~

Đây là declaration fragment. Flag không trở thành `Flag<Integer>`; nó chỉ implement Coded<Integer> contract.

### 27.4. Generic class có thể là sealed hoặc final

~~~java
sealed interface Result<T> permits Success, Failure {
}

record Success<T>(T value) implements Result<T> {
}

record Failure<T>(String error) implements Result<T> {
}
~~~

Đây là fragment minh họa một **generic sealed interface** có generic record variants. Java type parameter T có vai trò về payload; `sealed` có vai trò về direct subtype permissions. Hai cơ chế độc lập.

### 27.5. Generic bounds với interfaces và records

Record `Success<T>` có thể có T arbitrary reference type; nếu cần Number-specific behavior, bound `T extends Number` sẽ hạn chế clients. Không cần bound chỉ vì type là record.

## 28. Type inference, diamond và target typing

Java có thể suy luận generic type arguments khi đủ context.

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.Map<String, Integer> counts =
        new java.util.HashMap<>();
~~~

`<>` là diamond operator. Nó giảm việc lặp String/Integer ở cả hai phía, nhưng type relationship không thay đổi.

### 28.1. `var` không làm mất generic type

Trong Java 17:

~~~java
var names = new java.util.ArrayList<String>();
names.add("Lan");
~~~

Compiler inference cho names có type `ArrayList<String>`. Nó không thành raw ArrayList chỉ vì `var`.

Nhưng:

~~~java
var names = new java.util.ArrayList<>();
~~~

không có target type đủ cụ thể nên type có thể được suy ra là `ArrayList<Object>`. Nếu muốn String, hãy ghi explicit constructor type argument hoặc typed target declaration.

### 28.2. `List.of` là generic static factory

~~~java
var names = java.util.List.of("Lan", "Mai");
~~~

Compiler có thể suy luận List<String>. Đây là unmodifiable List theo API `List.of`, không phải do generics tự khiến List immutable.

### 28.3. Target typing hỗ trợ lambdas

Generic methods và functional interfaces thường suy luận type arguments từ target type:

~~~java
java.util.function.Function<String, Integer> length =
        String::length;
~~~

Đây là một use case rộng hơn của Java type inference. Generic class tham số hóa giúp method references và lambdas có signatures typed, giảm casts trong pipelines.

### 28.4. Inference có giới hạn

Một expression có nhiều overloads, wildcards và nested generics có thể khiến compiler không tìm được type argument phù hợp. Có thể khai báo local variables với types rõ ràng hoặc dùng explicit method type arguments thay vì ép compiler đoán.

## 29. Sai lầm phổ biến khi mới dùng generic class

1. **Dùng `Object` dù API có relation kiểu rõ:** làm mất compile-time checks.
2. **Tưởng type parameter T là runtime Class object:** generics chủ yếu erased.
3. **Tưởng tạo `Box<String>` sinh một runtime class riêng:** không phải với ordinary Java generics.
4. **Dùng primitive `int` làm type argument:** sai; dùng Integer.
5. **Quên diamond operator:** không sai nhưng lặp type info không cần thiết.
6. **Dùng diamond mà không có target type rõ rồi kỳ vọng String:** inference có thể chọn Object.
7. **Gọi String-specific method trên unbounded T:** compiler chỉ biết bound Object.
8. **Viết `static T field` trong generic class:** class T không dùng trong static context.
9. **Không phân biệt generic class T và method U:** gây confusing API signatures.
10. **Viết `new T()`:** không thể do erased type.
11. **Viết `new T[10]` hoặc `new List<String>[10]`:** generic array creation restrictions.
12. **Dùng `instanceof List<String>`:** type argument không reifiable.
13. **Đọc List<?> rồi cast tùy tiện:** wildcard không bảo đảm element type.
14. **Cho `List<Integer>` gán sang `List<Number>`:** invariance ngăn heap pollution.
15. **Lạm dụng `? extends T` rồi cố add T:** compiler không biết actual producer element subtype.
16. **Dùng `? super T` rồi đọc trực tiếp T:** chỉ đọc an toàn ở Object nếu không có thông tin khác.
17. **Hiểu nhầm PECS là immutable/mutable:** wildcard giới hạn type-safe operations, không làm object immutable.
18. **Dùng raw types để tránh lỗi compiler:** tạo unchecked risks.
19. **Suppress toàn bộ unchecked warnings:** che đi nơi xảy ra heap pollution.
20. **Dùng generic interface hai lần với type arguments xung đột:** erasure conflicts.
21. **Overload methods chỉ bằng List<String>/List<Integer>:** same erasure.
22. **Dùng T cho mọi type parameter dù vai trò khác:** Pair nên dùng K,V rõ ràng.
23. **Generic hóa entity domain vô cớ:** tăng độ phức tạp.
24. **Tưởng `Box<String>` không thể chứa null:** null contract độc lập generic type.
25. **Tưởng generics tự defensive-copy mutable List:** không.
26. **Tưởng generic record deep immutable:** chỉ final component fields, mutable referent vẫn có thể thay.
27. **Dựa vào getClass() để tìm T=String từ Box<String> instance:** runtime class không mang type arg reified.
28. **Dùng Class<List<String>> như một runtime type literal:** không có List<String>.class.
29. **Quên type bounds khi cần Comparable/Number operations:** code không compile hoặc phải cast sai.
30. **Thêm bounds quá chặt không cần thiết:** giảm khả năng tái sử dụng API.
31. **Không phân biệt runtime exceptions với compile errors:** type safety giảm lỗi, không loại bỏ tất cả runtime faults.
32. **Không viết tests cho raw/legacy boundaries:** external data cần validation.
33. **Không nghĩ về equality/hash semantics của keys khi làm Map<K,V>:** K generic không bảo đảm value semantics.
34. **Sử dụng mutable objects làm map keys:** state thay có thể phá lookups dù type vẫn hợp lệ.
35. **Dùng unchecked casts như giải pháp mặc định:** ưu tiên typed factory, Class<T>, bounds hoặc explicit converters khi cần.

## 30. Bảng quyết định: nên chọn loại API nào?

| Bài toán | Thiết kế thường hợp lý | Lý do |
| --- | --- | --- |
| Hộp cho một kiểu reference tùy chọn | `Box<T>` | Giữ type quan hệ giữa set/get |
| Cặp key/value khác type | `Pair<K,V>` / generic record | Kiểm tra kiểu ở từng vị trí |
| Lưu User theo String ID | `Repository<String,User>` | Typed IDs/entities |
| Method copy giữa Lists liên quan subtype | `<T> copy(List<? super T>, List<? extends T>)` | PECS |
| Method chỉ đọc Number values | `List<? extends Number>` | Nhận nhiều Number subtypes |
| Method chỉ thêm Integer | `List<? super Integer>` | Chấp nhận multiple consumers |
| Một List chưa biết element type | `List<?>` | An toàn hơn raw List |
| Numeric wrapper cần `doubleValue` | `T extends Number` | Compiler biết API của Number |
| Utility static chọn value | `static <T> T choose(...)` | Method-specific parameter |
| Runtime check candidate Object | `Class<T>` token với `cast` | Validation explicit tại boundary |
| Immutable result payload | `record Result<T>(T value)` | Value-style record generic |
| Heterogeneous hierarchy có finite variants | Sealed interface + typed records | Closed variants và typed payload |
| Runtime-configurable arbitrary type IDs | Interface/value class/registry | Generic enum không được phép |
| Primitive numeric hot path | `int[]` / primitive-specialized APIs | Tránh boxing overhead khi cần |

Bảng là heuristic, không phải compiler rule cho mọi kiến trúc. Hãy đánh giá state ownership, lifecycle, extensibility, null contracts và hiệu năng thực tế.

## 31. Bài tập tự kiểm tra có đáp án

**Câu 1.** Mục đích chính của `class Box<T>` là gì?

**Đáp án:** Cho phép một implementation dùng nhiều reference types mà vẫn giữ compile-time relationship giữa fields/method inputs/outputs, giảm casts và lỗi kiểu.

**Câu 2.** `Box<String>` có thể gọi `set(123)` nếu setter nhận T không?

**Đáp án:** Không; 123 được boxed thành Integer, không phải String.

**Câu 3.** `Box<Integer>` có dùng chung class source với `Box<String>` không?

**Đáp án:** Có; một generic class declaration được parameterize với type arguments khác nhau.

**Câu 4.** `T` trong `Box<T>` là String object hay type parameter?

**Đáp án:** Type parameter.

**Câu 5.** Type argument là gì trong `Box<User>`?

**Đáp án:** User.

**Câu 6.** `Box<int>` hợp lệ không?

**Đáp án:** Không; type arguments phải là reference types phù hợp. Dùng Box<Integer>.

**Câu 7.** `Box<?>` có giống raw Box không?

**Đáp án:** Không; wildcard vẫn duy trì generic safety với unknown type, raw bỏ type information và có unchecked risks.

**Câu 8.** Có cần cast `(String) box.get()` khi box có type Box<String> không?

**Đáp án:** Không trong source code bình thường, vì compiler biết return type String.

**Câu 9.** Static method có dùng T của `class Box<T>` trực tiếp không?

**Đáp án:** Không. Static generic method khai báo type parameter của chính method, ví dụ `static <E> Box<E> of(E e)`.

**Câu 10.** `class Pair<K,V>` có thể có K=String và V=Integer không?

**Đáp án:** Có, các type parameters độc lập.

**Câu 11.** Method `Pair<V,K> swapped()` của Pair<String,Integer> trả parameterized type nào?

**Đáp án:** Pair<Integer,String>.

**Câu 12.** Generic method khác class generic thế nào?

**Đáp án:** Method tự khai báo `<U>` cho invocation; class khai báo `<T>` dùng xuyên qua instance API.

**Câu 13.** Vì sao `T extends Number` hữu ích?

**Đáp án:** Compiler biết T là Number subtype, có thể gọi doubleValue/intValue và các members của Number.

**Câu 14.** `T extends Comparable<T>` nghĩa là T phải extends một class Comparable?

**Đáp án:** Không; Comparable là interface, `extends` cũng dùng cho interface bounds.

**Câu 15.** Có thể gán `List<Integer>` vào `List<Number>` không?

**Đáp án:** Không, generic parameterized types là invariant theo quan hệ này.

**Câu 16.** Vì sao List<Integer> không là List<Number>?

**Đáp án:** Nếu được, có thể add Double qua List<Number> alias vào List<Integer>, phá type safety.

**Câu 17.** Khi đọc Number values từ nhiều numeric List types, dùng gì?

**Đáp án:** `List<? extends Number>`.

**Câu 18.** Có thể add Double tùy ý vào `List<? extends Number>` không?

**Đáp án:** Không, actual element subtype có thể là Integer.

**Câu 19.** Khi thêm Integer vào List<Integer>, List<Number> hoặc List<Object>, dùng gì?

**Đáp án:** `List<? super Integer>`.

**Câu 20.** Đọc element từ `List<? super Integer>` dưới type nào là tổng quát an toàn?

**Đáp án:** Object.

**Câu 21.** `List<?>` có cho add một String bất kỳ không?

**Đáp án:** Không, vì không biết actual element type argument.

**Câu 22.** `? extends T` trong PECS mang ý nghĩa gì?

**Đáp án:** Container producer values typed as T (hoặc subtypes), thuận cho đọc.

**Câu 23.** `? super T` trong PECS mang ý nghĩa gì?

**Đáp án:** Container consumer có thể nhận T values, thuận cho ghi.

**Câu 24.** `Box<String>.getClass()` có khác `Box<Integer>.getClass()` không?

**Đáp án:** Không đối với instances cùng generic Box class, do type erasure.

**Câu 25.** Một unbounded T thường erase thành gì?

**Đáp án:** Object.

**Câu 26.** Reflection `Box.class.getTypeParameters()` cho biết T=String ở một instance không?

**Đáp án:** Không; nó cho biết class khai báo một type variable T.

**Câu 27.** Có tạo `new T()` được không?

**Đáp án:** Không; cần Supplier<T>/factory/Class<T> token tùy mục đích.

**Câu 28.** Có tạo `new List<String>[10]` được không?

**Đáp án:** Không, vì generic array creation restrictions với non-reifiable parameterized type.

**Câu 29.** Có dùng `value instanceof List<String>` được không?

**Đáp án:** Không; có thể check `List<?>` và validate elements riêng.

**Câu 30.** Raw `List` có thể khiến List<String> chứa Integer không?

**Đáp án:** Có qua unchecked operations/heap pollution; đọc String về sau có thể ném ClassCastException.

**Câu 31.** `@SuppressWarnings("unchecked")` có kiểm tra runtime type không?

**Đáp án:** Không; chỉ tắt compiler warnings ở scope áp dụng.

**Câu 32.** Generic record có hợp lệ ở Java 17 không?

**Đáp án:** Có, ví dụ `record Result<T>(T data) {}`.

**Câu 33.** Generic enum `enum E<T>` có hợp lệ không?

**Đáp án:** Không, nhưng enum có thể implements generic interface với concrete arguments.

**Câu 34.** `var list = new ArrayList<String>()` có là raw List không?

**Đáp án:** Không; compiler suy ra ArrayList<String>.

**Câu 35.** `var list = new ArrayList<>()` không có target typed context có thể suy ra gì?

**Đáp án:** Thường ArrayList<Object>; ghi type rõ nếu muốn String.

**Câu 36.** Generic class có tự làm List component immutable không?

**Đáp án:** Không; generic type safety và mutability/ownership là hai concern khác nhau.

**Câu 37.** `Repository<String,User>` có bảo đảm user có quyền truy cập entity không?

**Đáp án:** Không; nó chỉ kiểm tra type quan hệ ID và entity. Authorization là business logic.

**Câu 38.** Khi cần runtime check Object candidate là String, có thể dùng gì?

**Đáp án:** `String.class.cast(candidate)` hoặc một Class<T> token với cast/validation boundary.

**Câu 39.** `Class<List<String>>` có được biểu diễn bằng `List<String>.class` không?

**Đáp án:** Không; nested type arguments không reified qua class literal như vậy.

**Câu 40.** Điều nên nhớ nhất khi học generic class?

**Đáp án:** Type parameters làm một class reusable mà vẫn liên kết kiểu inputs/outputs ở compile time, giảm casts và tránh trộn data sai loại; dùng bounds/wildcards khi cần linh hoạt, tránh raw types và hiểu type erasure.

## 32. Bài tập thực hành nâng dần

### Bài 1 — tự xây Box<T>

Tạo `Box<T>` có constructor, `get`, `set` và `map(Function<? super T,? extends R>)` trả Box<R>. Viết demo Box<String> → Box<Integer> bằng String.length. Kiểm tra compile errors khi cố set Integer vào Box<String>.

**Gợi ý:** `<R> Box<R> map(...)` là generic instance method có independent R. Function upper/lower wildcard giúp nhận linh hoạt consumer/producer của types.

### Bài 2 — key/value typed pair

Viết `Pair<K,V>` với `swap()` trả Pair<V,K>. Tạo Pair<String,Boolean>, swap và đọc hai component values không cast.

**Gợi ý:** Giữ K/V ở fields, constructor và return type; không dùng Object ở public API.

### Bài 3 — repository nhiều loại entity

Triển khai generic `Repository<ID,T>` với Map<ID,T>. Tạo một Repository<String,User> và một Repository<Long,Order>. Kiểm tra compiler chặn save(Integer,User) ở repository đầu.

**Gợi ý:** Tránh iteration order dependency; kiểm tra missing values với Optional.

### Bài 4 — bounds

Viết `NumericSummary<N extends Number>` trả double sum cho List<N>. Thử Integer/Double, xem String không thỏa bound. Nêu rủi ro precision khi doubleValue dùng cho tiền.

**Gợi ý:** Dùng List<? extends Number> nếu method chỉ đọc mà không cần class có một fixed N.

### Bài 5 — invariance và PECS

Cho List<Integer>, List<Number>, List<Object>. Viết generic copy method nhận producer/consumer wildcards. Thử gán List<Integer> sang List<Number> và giải thích compile error.

**Gợi ý:** `<T> copy(List<? super T>, List<? extends T>)`.

### Bài 6 — runtime token

Xây `CheckedBox<T>` giữ Class<T> và dùng cast tại boundary nhận Object. Kiểm tra case đúng/sai và phân tích vì sao không thể chỉ dùng T.class.

**Gợi ý:** `Class<T>.cast` và catch ClassCastException đúng vị trí.

### Bài 7 — legacy raw type audit

Lấy một API raw List, bổ sung generic type arguments khi có contract. Dùng `javac -Xlint:unchecked` để xem cảnh báo và thay thế raw references bằng `List<?>`/typed List khi phù hợp.

**Gợi ý:** Đừng dùng suppressWarnings như bước đầu tiên; tìm nơi data type relation bị mất.

### Bài 8 — generic type erasure

Tạo Box<String> và Box<Integer>, so getClass, xem `Box.class.getDeclaredField("value").getType()`. Giải thích vì sao metadata `getTypeParameters()` còn T nhưng instance không tự biết concrete T.

**Gợi ý:** Phân biệt generic declaration signature với runtime object class.

## 33. Checklist review generic class trước khi dùng trong project

1. Class có abstraction chung thật sự để parameterize không?
2. Type parameter T/K/V đã đặt tên phản ánh vai trò chưa?
3. Cần một hay nhiều independent type parameters?
4. Các input/output fields/methods đã dùng đúng quan hệ kiểu chưa?
5. Có Object và cast ở public API mà generic thay thế được không?
6. Có dùng raw types hoặc unchecked operations cần cô lập không?
7. Đã thử misuse compilation để bảo đảm API chặn dữ liệu sai loại chưa?
8. Có thêm bounds chỉ khi implementation cần methods tương ứng không?
9. Có dùng wildcards khi method cần variance không?
10. Có phân biệt producer extends và consumer super không?
11. Có tránh gán List<Integer> sang List<Number> không?
12. Có hiểu wildcard không làm List immutable không?
13. Có biết static methods cần type parameters riêng không?
14. Có tránh static T fields và new T() không?
15. Có xử lý primitive types bằng wrappers hoặc primitive-specialized structures không?
16. Có nhớ generics erased và không dùng instanceof parameterized type sai không?
17. Có tránh generic arrays/casts không kiểm soát không?
18. Có runtime Class<T> token khi thật sự cần validation từ Object không?
19. Có dùng type inference/diamond rõ ràng, không tạo ArrayList<Object> ngoài ý muốn không?
20. Có biết type parameters của generic class và generic method độc lập không?
21. Có thiết kế null contract rõ, không giả định generic non-null không?
22. Có defensive copy nếu class giữ mutable data và cần snapshot không?
23. Có kiểm soát equals/hashCode của generic key types khi dùng Map<K,V> không?
24. Có kiểm tra thread-safety của mutable generic container không?
25. Có tránh overloads gây same-erasure clash không?
26. Có dùng code compile errors để dạy type safety thay vì bỏ qua compiler warnings không?
27. Có integration tests cho boundary giữa typed Java code và raw/legacy deserialization không?
28. Có thể dùng generic record cho value carrier đơn giản không?
29. Có biết enum không generic dù có thể implement generic interface không?
30. Có tránh generic hóa một domain class không có nhu cầu tham số hóa thật không?

## Kết luận

**Lớp generic trong Java cho phép một class biểu diễn một abstraction dùng lại với nhiều reference types, đồng thời liên kết kiểu của dữ liệu đầu vào, fields và giá trị trả về bằng kiểm tra ở compile time.** `Box<T>`, `Pair<K,V>` và `Repository<ID,ENTITY>` đều thể hiện mục đích ấy rõ hơn `Object` + casts.

Hiểu generic class cần đi cùng các giới hạn: type arguments là **reference types**, parameterized classes **invariant** đối với inheritance của type arguments, wildcard `extends`/`super` hỗ trợ APIs linh hoạt theo PECS, và type erasure giải thích vì sao runtime thường không mang type arguments của mỗi generic instance. Bounded parameters giới hạn T để có thể gọi methods đặc thù; generic methods có type parameters riêng; raw types/unchecked operations có thể phá bảo đảm type.

Generics **không tự làm dữ liệu immutable, non-null, hợp lệ về nghiệp vụ hoặc thread-safe**. Chúng giải quyết một vấn đề cụ thể nhưng cực kỳ quan trọng: **tái sử dụng cấu trúc chương trình mà không đánh mất sự an toàn kiểu**. Khi chọn đúng generic abstraction, API vừa linh hoạt vừa phát hiện sai sót sớm, giảm duplication, casts và runtime `ClassCastException` trong Java 17+.
