# Kế thừa và chuyển tiếp tham số kiểu trong Java Generics

Khi thiết kế một hệ thống class và interface generic, bạn thường không chỉ viết `class Box<T>` rồi dùng trực tiếp `Box<String>`. Một class con có thể **giữ nguyên type parameter** của class cha, **cố định type argument**, **đổi vị trí các type arguments** hoặc **tạo một generic type lồng nhau** để truyền lên. Tương tự, một generic interface có thể được kế thừa bởi interface khác hoặc được class triển khai với một type argument phù hợp.

Đây là ý nghĩa của **kế thừa và chuyển tiếp tham số kiểu** (*generic inheritance / forwarding type parameters*): quy tắc subtype của Java phải đi kèm với những phép thay thế kiểu nhất quán. Bài này giải thích cách đọc các quan hệ ấy, vì sao không được đồng nhất `Parent<ChildType>` với `Parent<ParentType>`, cách override sau khi type argument đã được chuyên biệt hóa và những lỗi phổ biến do type erasure.

Các chương trình đầy đủ dùng **Java 17+**. Mỗi ví dụ có public class được lưu trong tệp cùng tên; phần chỉ minh họa chữ ký sẽ được ghi chú riêng.

## 1. Ôn nhanh: type parameter và type argument không phải một

Xét hai khai báo:

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

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
```

Đây là các khai báo Java hợp lệ nhưng chưa có `main`.

- `T` trong `Box<T>` là **type parameter** do class `Box` khai báo.
- `String` trong `Box<String>` là **type argument** truyền cho `Box` khi khai báo superclass của `StringBox`.
- `StringBox` **không khai báo** một type parameter của riêng nó; nó kế thừa từ một cách sử dụng cụ thể của `Box`.
- Ở code nguồn, `StringBox.get()` được compiler xem như trả `String` vì `T` của `Box` đã được ràng buộc thành `String`.
- Java vẫn tạo một superclass/subclass theo ngữ nghĩa runtime thông thường; generic type argument không tạo một biến thể class JVM mới.

Đọc `extends Box<String>` như câu: “class hiện tại là subtype của `Box` với type argument `String`”. Đừng đọc `<String>` thành “khai báo type parameter String”.

## 2. Quy tắc cốt lõi của việc chuyển tiếp

Một lớp con **có thể khai báo type parameter mới** và dùng nó làm type argument cho cha:

```java
class Parent<T> {
    T value;
}

class Child<U> extends Parent<U> {
}
```

Ở đây:

1. `Parent<T>` khai báo biến kiểu `T`.
2. `Child<U>` khai báo một biến kiểu **riêng** `U`.
3. `extends Parent<U>` truyền `U` của `Child` làm **type argument** để áp dụng `Parent<T>`.
4. Đối với `Child<String>`, kiểu kế thừa là `Parent<String>`. Do đó field `value` của `Parent` có kiểu tĩnh `String` khi truy cập qua reference phù hợp.

Bạn cũng có thể viết `class Child<T> extends Parent<T>`. Lúc đó hai chữ `T` thuộc **hai khai báo khác nhau**, nhưng mệnh đề `extends Parent<T>` ánh xạ type parameter của cha sang type parameter của con. Tên giống nhau chỉ là quy ước, còn **mối quan hệ nằm trong phần `extends`**.

Một cách kiểm tra bằng bảng:

| Khai báo | Type parameter do ai sở hữu? | Mapping ở mệnh đề extends |
| --- | --- | --- |
| `Parent<T>` | `Parent` sở hữu `T` | Chưa có mapping |
| `Child<U>` | `Child` sở hữu `U` | `Parent.T ← Child.U` |
| `Child<String>` | Dùng `String` làm argument của Child | Suy ra `Parent.T = String` |
| `Child<Integer>` | Dùng `Integer` làm argument của Child | Suy ra `Parent.T = Integer` |

Phép ánh xạ được compiler áp dụng xuyên suốt field, method và các interface của class cha. Nếu lớp cha có `T get()` thì một `Child<String>` có method kế thừa mà caller sử dụng dưới dạng trả `String`.

## 3. Chuyển tiếp nguyên một type parameter: ví dụ chạy được

Tạo tệp `ForwardingDemo.java`:

```java
public class ForwardingDemo {
    static class Storage<T> {
        private T value;

        Storage(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    static final class AuditedStorage<E> extends Storage<E> {
        private int updates;

        AuditedStorage(E value) {
            super(value);
        }

        @Override
        void set(E value) {
            super.set(value);
            updates++;
        }

        int updates() {
            return updates;
        }
    }

    public static void main(String[] args) {
        AuditedStorage<String> names = new AuditedStorage<>("An");
        names.set("Binh");

        String name = names.get();
        Storage<String> baseView = names;

        System.out.println(name);
        System.out.println(baseView.get());
        System.out.println(names.updates());
    }
}
```

Biên dịch và chạy:

```bash
javac ForwardingDemo.java
java ForwardingDemo
```

Kết quả `stdout`:

```text
Binh
Binh
1
```

Điểm quan trọng:

- `Storage<T>` khai báo hợp đồng kiểu cho `value`, `get()` và `set(T)`.
- `AuditedStorage<E>` khai báo kiểu `E` của riêng nó và **chuyển tiếp** thành `Storage<E>`.
- Với `AuditedStorage<String>`, compiler nhìn `get()` trả `String` và `set(...)` nhận `String`.
- `@Override void set(E value)` tiếp tục đúng hợp đồng của cha với type argument đã được áp dụng.
- `Storage<String> baseView = names` hợp lệ: một subtype có thể được upcast sang **supertype với cùng cách tham số hóa**.
- Nếu viết `names.set(123)`, compilation thất bại vì yêu cầu `String`.

Lưu ý: kế thừa generic không có nghĩa constructor của cha được tự động kế thừa. Constructor `AuditedStorage(E)` gọi `super(value)` để khởi tạo trạng thái cha. `Storage<T>` có thể định nghĩa constructor và generic methods riêng; hai khái niệm đó không thay thế nhau.

## 4. Phân biệt chuyển tiếp và cố định type argument

Lớp con **không nhất thiết** phải generic. Nếu nó luôn chuyên xử lý chuỗi, thay vì khai báo `<U>` rồi chuyển `U` lên cha, nó có thể cố định type argument một lần:

```java
// Giả sử Storage<T> có constructor Storage(T) và T get() như mục 3.
class TextStorage extends Storage<String> {
    TextStorage(String initial) {
        super(initial);
    }
}
```

Với `TextStorage`, kiểu kế thừa là `Storage<String>`; `get()` trả String ở source level. Ngược lại, `AuditedStorage<E> extends Storage<E>` trong mục 3 vẫn giữ E để mỗi cách dùng `AuditedStorage<String>` hoặc `AuditedStorage<Integer>` có hợp đồng riêng.

Khác biệt cần đọc ở chính mệnh đề kế thừa: `Storage<String>` là **kiểu cố định**, còn `Storage<E>` là **chuyển tiếp tham số kiểu**. Constructor lớp con vẫn cần khởi tạo phần superclass qua `super(initial)` nếu cha không có constructor không tham số phù hợp. Kế thừa không tự tạo constructor mới.

Bài này dùng hai hình thức ấy để so sánh cơ chế *forwarding*; khi cần tự thiết kế lớp chuyên biệt cố định kiểu, hãy xác định nó thực sự mang hành vi/domain invariant gì thay vì tạo subclass chỉ để đổi tên `Storage<String>`.

## 5. Biến đổi type argument khi truyền lên class cha

Một lớp con có thể dùng type parameter của mình bên trong một **kiểu được tham số hóa** để truyền cho cha:

```java
class Parent<T> {
    T value;
}

class Group<E> extends Parent<java.util.List<E>> {
}
```

Mapping không còn là `Parent.T ← E` mà là **`Parent.T ← List<E>`**.

Với `Group<String>`, kiểu kế thừa là `Parent<List<String>>`. Bởi vậy field `value` của cha có kiểu tĩnh `List<String>`, không phải `String`.

Tạo `NestedForwardingDemo.java`:

```java
import java.util.List;

public class NestedForwardingDemo {
    static class Container<T> {
        private final T data;

        Container(T data) {
            this.data = data;
        }

        T get() {
            return data;
        }
    }

    static final class Batch<E> extends Container<List<E>> {
        Batch(List<E> items) {
            super(List.copyOf(items));
        }

        int count() {
            return get().size();
        }
    }

    public static void main(String[] args) {
        Batch<String> batch = new Batch<>(List.of("A", "B"));

        List<String> items = batch.get();
        Container<List<String>> base = batch;

        System.out.println(items);
        System.out.println(batch.count());
        System.out.println(base.get().get(0));
    }
}
```

Chạy:

```bash
javac NestedForwardingDemo.java
java NestedForwardingDemo
```

`stdout`:

```text
[A, B]
2
A
```

Phân tích:

1. `Batch<E>` sở hữu `E`.
2. `extends Container<List<E>>` dùng toàn bộ kiểu `List<E>` làm type argument cho `Container<T>`.
3. Với `Batch<String>`, compiler suy ra `Container<List<String>>`.
4. `get()` vì thế có kiểu trả về `List<String>`; người gọi mới có thể dùng tiếp `get(0)` để nhận `String`.
5. `List.copyOf` làm danh sách component không sửa được và từ chối phần tử null; đây là lựa chọn triển khai của `Batch`, **không** phải quy tắc tự động của generic inheritance.

Cách đọc kiểu lồng: **bắt đầu ở type parameter cha, thay biểu thức type argument được truyền, rồi tiếp tục thay từng parameter của con**.

## 6. Nhiều type parameters: chuyển tiếp, đổi vị trí và cố định một phần

Với kiểu cha `Pair<K,V>`, lớp con có nhiều cách áp dụng type arguments:

```java
class Pair<K, V> {
    K key;
    V value;
}

// Giữ nguyên thứ tự nhưng dùng tên khác:
class Same<A, B> extends Pair<A, B> {
}

// Đổi vị trí:
class Swapped<X, Y> extends Pair<Y, X> {
}

// Cố định khóa là String, chỉ để giá trị generic:
class NamedValue<T> extends Pair<String, T> {
}

// Bọc giá trị thành danh sách:
class MultiValue<T> extends Pair<String, java.util.List<T>> {
}
```

Đây là các khai báo minh họa, không có constructor/main riêng.

Bảng ánh xạ:

| Class con | Áp dụng type arguments của `Pair<K,V>` |
| --- | --- |
| `Same<Integer,String>` | `K=Integer`, `V=String` |
| `Swapped<Integer,String>` | `K=String`, `V=Integer` |
| `NamedValue<Double>` | `K=String`, `V=Double` |
| `MultiValue<Long>` | `K=String`, `V=List<Long>` |

Sự **đổi vị trí** nằm ở `extends Pair<Y,X>`, chứ không nằm ở tên `X` hay `Y`. Không tự hiểu `K` luôn là “type parameter đầu tiên của lớp con”: thứ tự và biểu thức được viết trong danh sách type arguments mới quyết định.

### Ví dụ đầy đủ về hoán đổi type arguments

Tạo `SwappedDemo.java`:

```java
public class SwappedDemo {
    static class Pair<K, V> {
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

    static final class Swapped<X, Y> extends Pair<Y, X> {
        Swapped(Y key, X value) {
            super(key, value);
        }
    }

    public static void main(String[] args) {
        Swapped<Integer, String> item =
                new Swapped<>("code", 42);

        String key = item.key();
        Integer value = item.value();

        System.out.println(key);
        System.out.println(value);
    }
}
```

Chạy `javac SwappedDemo.java` và `java SwappedDemo`:

```text
code
42
```

Ở `Swapped<Integer,String>`, `X=Integer` và `Y=String`. Do `extends Pair<Y,X>`, phương thức kế thừa `key()` trả `String` và `value()` trả `Integer`. Viết constructor theo `Swapped(Y key, X value)` là một cách giữ sự nhất quán với mapping; về API thực tế, tên `Swapped` chỉ nên dùng khi thứ tự ngữ nghĩa có lý do.

## 7. Chuỗi kế thừa nhiều tầng: áp dụng mapping từ tầng dưới lên

Khi có ba tầng, bạn phải tổng hợp các phép thay thế kiểu. Xét:

```java
class Base<A> {
}

class Middle<B> extends Base<java.util.List<B>> {
}

class Leaf<C> extends Middle<C> {
}
```

Với `Leaf<String>`:

1. `Leaf.C = String`.
2. `Leaf<C> extends Middle<C>` → `Middle.B = String`.
3. `Middle<B> extends Base<List<B>>` → `Base.A = List<String>`.
4. `Leaf<String>` vì thế là subtype của `Middle<String>` **và** `Base<List<String>>`.

Nếu tầng tiếp theo cố định `C=Integer`, class không generic đó sẽ là subtype của `Base<List<Integer>>`.

### Chương trình ba tầng có thể chạy

Tạo `InheritanceChainDemo.java`:

```java
import java.util.List;

public class InheritanceChainDemo {
    static class Base<T> {
        private final T value;

        Base(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class Middle<E> extends Base<List<E>> {
        Middle(List<E> value) {
            super(List.copyOf(value));
        }
    }

    static final class Leaf<X> extends Middle<X> {
        Leaf(List<X> value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Leaf<String> leaf = new Leaf<>(List.of("one", "two"));
        Middle<String> middle = leaf;
        Base<List<String>> base = leaf;

        System.out.println(leaf.get());
        System.out.println(middle.get().size());
        System.out.println(base.get().get(1));
    }
}
```

Chạy:

```bash
javac InheritanceChainDemo.java
java InheritanceChainDemo
```

`stdout`:

```text
[one, two]
2
two
```

Mẹo đọc code: vẽ một chuỗi `Leaf<X> → Middle<X> → Base<List<X>>`; sau đó thay `X=String`. Đừng nhảy thẳng từ `Leaf<String>` lên `Base<String>` — đó là kết luận sai vì tầng `Middle` đã bọc type argument trong `List`.

## 8. Generic interface được kế thừa và chuyển tiếp như thế nào?

Java cho phép một interface kế thừa interface generic khác. Có thể giữ nguyên parameter, cố định parameter, hoặc biến đổi nó thành một biểu thức kiểu khác.

```java
interface Source<T> {
    T read();
}

interface MutableSource<E> extends Source<E> {
    void write(E value);
}

interface TextSource extends Source<String> {
}

interface BatchSource<E> extends Source<java.util.List<E>> {
}
```

Ý nghĩa:

- `MutableSource<Integer>` là subtype của `Source<Integer>`; `read()` trả `Integer` và `write(...)` nhận `Integer`.
- `TextSource` không generic nhưng mọi implementation của nó phải đáp ứng `Source<String>`.
- `BatchSource<Double>` là subtype của `Source<List<Double>>`, vì `E` được bọc thành `List<E>` trước khi truyền.

Chú ý: một interface kế thừa interface khác bằng `extends`, không dùng `implements`. Class mới sử dụng `implements` khi thực thi giao diện.

### Ví dụ interface nhiều tầng và implementation

Tạo `InterfaceForwardingDemo.java`:

```java
public class InterfaceForwardingDemo {
    interface Reader<T> {
        T read();
    }

    interface NamedReader<T> extends Reader<T> {
        String name();
    }

    static final class IntReader implements NamedReader<Integer> {
        @Override
        public Integer read() {
            return 7;
        }

        @Override
        public String name() {
            return "counter";
        }
    }

    static <T> void print(Reader<T> reader) {
        System.out.println(reader.read());
    }

    public static void main(String[] args) {
        IntReader reader = new IntReader();
        Reader<Integer> general = reader;

        System.out.println(reader.name());
        print(general);
    }
}
```

Chạy `javac InterfaceForwardingDemo.java` rồi `java InterfaceForwardingDemo`:

```text
counter
7
```

Luồng type mapping là `IntReader implements NamedReader<Integer> extends Reader<Integer>`. Method `read()` có kiểu trả về `Integer` trong implementation và khi được truy cập qua `Reader<Integer>`.

## 9. Class generic implements generic interface và extends generic class

Một class có thể vừa kế thừa superclass vừa triển khai interface, dùng **cùng một type parameter** để đảm bảo quan hệ kiểu xuyên suốt hai nhánh.

Tạo `RepositoryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class RepositoryDemo {
    interface Repository<T> {
        void add(T value);
        List<T> all();
    }

    static class Named<T> {
        private final String name;

        Named(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class MemoryRepository<E>
            extends Named<E> implements Repository<E> {

        private final List<E> values = new ArrayList<>();

        MemoryRepository(String name) {
            super(name);
        }

        @Override
        public void add(E value) {
            values.add(value);
        }

        @Override
        public List<E> all() {
            return List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        MemoryRepository<String> repo =
                new MemoryRepository<>("languages");

        repo.add("Java");
        repo.add("Kotlin");

        Repository<String> api = repo;

        System.out.println(repo.name());
        System.out.println(api.all());
    }
}
```

Chạy:

```bash
javac RepositoryDemo.java
java RepositoryDemo
```

`stdout`:

```text
languages
[Java, Kotlin]
```

`MemoryRepository<E>` khai báo một biến kiểu `E`. Nó được dùng ở **hai nơi**: `extends Named<E>` và `implements Repository<E>`. Như vậy, khi tạo `MemoryRepository<String>`, cả contract kế thừa lẫn contract interface đều dùng `String`. `List.copyOf` trong `all()` là quyết định của implementation để trả snapshot không sửa được; type parameter `E` tự nó không áp đặt immutability hay chính sách null.

Một class cũng có thể chuyển tiếp type arguments khác nhau cho superclass và interface nếu thiết kế yêu cầu, ví dụ một type dùng cho khóa và một type cho dữ liệu; chỉ cần các chữ ký method tương thích và không tạo xung đột kế thừa.

## 10. Bound của type parameter khi chuyển tiếp

Nếu class cha yêu cầu type parameter thỏa **upper bound**, class con phải cung cấp type argument đáp ứng bound tại điểm khai báo `extends`.

Ví dụ:

```java
class NumericBox<N extends Number> {
    private final N number;

    NumericBox(N number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}
```

Một class con chuyển tiếp hợp lệ:

```java
class Measured<T extends Number> extends NumericBox<T> {
    Measured(T number) {
        super(number);
    }
}
```

`T extends Number` trên `Measured` bảo đảm mọi type argument của `Measured<T>` phù hợp yêu cầu `N extends Number` của `NumericBox`. Không thể viết một class con tổng quát `class Bad<T> extends NumericBox<T>` nếu `T` của Bad không có bound phù hợp: compiler không chứng minh được mọi `T` thỏa `Number`.

### Ví dụ đầy đủ

Tạo `BoundedInheritanceDemo.java`:

```java
public class BoundedInheritanceDemo {
    static class NumericBox<N extends Number> {
        private final N number;

        NumericBox(N number) {
            this.number = number;
        }

        double twice() {
            return number.doubleValue() * 2;
        }
    }

    static final class Measured<T extends Number>
            extends NumericBox<T> {
        Measured(T value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Measured<Integer> items = new Measured<>(5);
        Measured<Double> weight = new Measured<>(1.25);

        System.out.println(items.twice());
        System.out.println(weight.twice());
    }
}
```

Chạy `javac BoundedInheritanceDemo.java` và `java BoundedInheritanceDemo`:

```text
10.0
2.5
```

Bound **không cần viết giống hệt từng ký tự**, nhưng type argument phải thực sự thỏa tất cả các ràng buộc liên quan. Class con có thể dùng một bound **hẹp hơn** nếu cần, miễn là thỏa bound lớp cha. Ví dụ, `<T extends Integer>` hợp lệ dù `Integer` là lớp `final`: vì không có lớp con của `Integer`, `T` chỉ có thể là `Integer`. Tuy vậy, khi không cần tổng quát hóa, dùng trực tiếp `Integer` thường rõ hơn. Với interface bounds, có thể kết hợp nhiều contract bằng `&` khi cần.

### Kế thừa một type đã cố định bound

`class IntegerBox extends NumericBox<Integer>` hợp lệ, vì `Integer` kế thừa `Number`. Lớp này không cần tự khai báo biến kiểu nếu mục tiêu chỉ dùng `Integer`.

## 11. Override phương thức khi T đã được áp dụng

Khi lớp cha khai báo method sử dụng type parameter `T`, lớp con phải override **đúng hợp đồng kiểu sau khi áp dụng type argument**.

Tạo `OverrideGenericDemo.java`:

```java
public class OverrideGenericDemo {
    static class Formatter<T> {
        String format(T value) {
            return "base:" + value;
        }
    }

    static final class IntegerFormatter extends Formatter<Integer> {
        @Override
        String format(Integer value) {
            return "int:" + value;
        }
    }

    public static void main(String[] args) {
        Formatter<Integer> format = new IntegerFormatter();

        System.out.println(format.format(12));
    }
}
```

Chạy:

```bash
javac OverrideGenericDemo.java
java OverrideGenericDemo
```

`stdout`:

```text
int:12
```

- `Formatter<T>` khai báo `format(T)`.
- `IntegerFormatter extends Formatter<Integer>` chuyên biệt hóa `T = Integer`.
- `format(Integer)` là override hợp lệ ở source level. Dùng `@Override` giúp compiler phát hiện chữ ký không tương thích.
- Biến `Formatter<Integer>` giữ đối tượng `IntegerFormatter`, nên dynamic dispatch gọi implementation ở subclass.

**Sai lầm phổ biến:** viết `format(Object)` trong `IntegerFormatter` và nghĩ đó chắc chắn override `format(T)` sau khi erasure. Ở source level, khi superclass được nhìn qua `Formatter<Integer>`, chữ ký cần đáp ứng là `format(Integer)`; một `format(Object)` khai báo thêm có thể không override như tác giả mong đợi, thậm chí gây name clash tùy chữ ký. Luôn dùng `@Override` và kiểm tra compiler thay vì đoán dựa trên bytecode bị xóa kiểu.

### Return type cũng được chuyên biệt hóa

Nếu superclass có `T get()` và subclass extends `Parent<String>`, subclass có thể override bằng `String get()`. Nếu generic method hoặc superclass contract có kiểu trả về khác, Java cho phép covariant return theo quy tắc override áp dụng, nhưng không được trả kiểu không tương thích.

Ví dụ `Object get()` không phải là cách override hợp lệ của `String get()` khi hợp đồng của subtype yêu cầu trả `String`; kiểu trả về bị mở rộng sai hướng.

## 12. Bridge method: vì sao JVM vẫn gọi đúng override sau erasure?

Phần này giải thích cơ chế phía sau, không bắt buộc để viết các generic class thường ngày.

Ở mã nguồn, `Formatter<T>.format(T)` được chuyên biệt hóa ở subclass thành `format(Integer)`. Sau **type erasure**, method của superclass có dạng gần `format(Object)` trong bytecode, trong khi method do subclass viết nhận `Integer`. Để giữ quan hệ override/dynamic dispatch, compiler có thể tạo một **bridge method** tổng hợp `format(Object)` ở subclass, thực hiện cast và chuyển lời gọi tới `format(Integer)`.

Nhìn từ Java source, bạn chỉ cần override đúng kiểu. Không nên tự viết bridge method.

### Quan sát bridge bằng reflection

Tạo `BridgeMethodDemo.java`:

```java
import java.lang.reflect.Method;

public class BridgeMethodDemo {
    static class Parent<T> {
        T echo(T input) {
            return input;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String echo(String input) {
            return input.toUpperCase();
        }
    }

    public static void main(String[] args) {
        Parent<String> view = new Child();
        System.out.println(view.echo("java"));

        boolean bridgeFound = false;
        for (Method method : Child.class.getDeclaredMethods()) {
            if (method.getName().equals("echo") && method.isBridge()) {
                bridgeFound = true;
            }
        }
        System.out.println(bridgeFound);
    }
}
```

Chạy:

```bash
javac BridgeMethodDemo.java
java BridgeMethodDemo
```

`stdout` với `javac` từ JDK 17:

```text
JAVA
true
```

`Child` override `echo(String)`. Trong bytecode của subclass do `javac` tạo, bridge `echo(Object)` giữ dispatch đúng qua reference `Parent<String>`. Dùng `isBridge()` để nhận biết method do compiler sinh; ví dụ chỉ in một Boolean, tránh phụ thuộc thứ tự trả về của `getDeclaredMethods()`.

Nếu muốn khảo sát thủ công, có thể chạy `javap -p -c BridgeMethodDemo$Child` trong môi trường shell phù hợp; cú pháp quote tên class chứa `$` phụ thuộc shell. Bridge là hệ quả của erasure, không phải một type parameter mới cần chuyển tiếp trong mã nguồn.

## 13. Generic method có type parameter riêng: không nhầm với kế thừa T

Một class generic có thể kế thừa type parameter từ cha **và** khai báo generic method độc lập.

```java
class Repository<T> {
    T get() {
        return null;
    }

    <R> R convert(java.util.function.Function<? super T, ? extends R> fn) {
        return fn.apply(get());
    }
}
```

Ở đây:

- `T` thuộc class và được áp dụng khi subclass extends `Repository<String>`.
- `R` thuộc riêng phương thức `convert`. Mỗi lời gọi có thể suy luận kiểu `R` khác.
- `Function<? super T, ? extends R>` liên kết dữ liệu `T` đang được lưu với kiểu kết quả `R`.
- Nếu lớp con là `StringRepository extends Repository<String>` thì `convert(String::length)` có thể trả `Integer`, dù class con không generic.

**Đừng tự khai báo lại `<T>` trong method nếu muốn dùng T của class.** Ví dụ:

```java
class Box<T> {
    private T value;

    // <T> void set(T x) { value = x; } // T ở method che T của class.
    void set(T x) {
        value = x;
    }
}
```

Tình huống này thuộc **scope/shadowing**, không phải chuyển tiếp type parameter giữa parent và child. Nhưng nó thường xuất hiện trong cùng codebase nên cần phân biệt.

## 14. Chuyển tiếp type arguments không biến generics thành hiệp biến

Khi khai báo `Child<T> extends Parent<T>`, `Child<Integer>` là subtype của **`Parent<Integer>`**. Nó không tự trở thành subtype của `Parent<Number>` chỉ vì Integer extends Number: những cách tham số hóa của cùng generic type mặc định **invariant**.

```java
class Parent<T> {}
class Child<T> extends Parent<T> {}

// Trong một phương thức:
Child<Integer> child = new Child<>();
Parent<Integer> exact = child;
Parent<? extends Number> readView = child;
// Parent<Number> wrong = child; // Không hợp lệ.
```

`Parent<? extends Number>` phù hợp cho API **quan sát** một giá trị Number nếu Parent có getter trả T, nhưng không cho phép tùy tiện ghi Number vào một vùng có kiểu phần tử thực tế chưa biết. Không dùng raw type/cast unchecked để biến `Parent<Integer>` thành `Parent<Number>`: làm vậy phá quan hệ type safety mà forwarding vừa bảo toàn.

## 15. Không được kế thừa cùng generic interface với hai arguments bất tương thích

Một class không thể đồng thời trở thành subtype của **cùng một generic interface** với hai type arguments khác nhau thông qua hai nhánh kế thừa.

Ví dụ cố ý sai:

```java
interface Consumer<T> {
    void accept(T item);
}

class TextConsumer implements Consumer<String> {
    public void accept(String item) {}
}

// Không hợp lệ: một đường kế thừa Consumer<String>,
// đường kia lại đòi Consumer<Integer>.
// class Bad extends TextConsumer implements Consumer<Integer> {
//     public void accept(Integer item) {}
// }
```

Đoạn code có khai báo `TextConsumer` hợp lệ nhưng `Bad` được comment vì gây lỗi biên dịch. Một subtype không thể có đồng thời hai instantiations phân biệt của cùng generic interface trong supertype hierarchy.

Một dạng xung đột khác:

```java
interface StringSource extends java.util.function.Supplier<String> {}
interface IntegerSource extends java.util.function.Supplier<Integer> {}

// Không hợp lệ:
// class Both implements StringSource, IntegerSource {
//     ...
// }
```

Dù có thể viết các phương thức nhận/đưa dữ liệu khác loại riêng, hai nhánh `Supplier<String>` và `Supplier<Integer>` đều mô tả cùng generic interface bị kế thừa với type arguments khác nhau; Java từ chối.

Tương tự, đừng kỳ vọng một method overload phân biệt hai type arguments của cùng raw generic type:

```java
// Sai do cùng erasure:
// void use(java.util.List<String> xs) {}
// void use(java.util.List<Integer> xs) {}
```

Hai chữ ký đều xóa thành tham số kiểu `List`, gây name clash.

## 16. Type erasure và raw type: giữ quan hệ ở compile time

Generic inheritance được kiểm tra ở mã nguồn, nhưng JVM không tạo riêng những class như `ChildOfParentString` chỉ vì `extends Parent<String>`. Java generics chủ yếu dùng **type erasure**:

- Type parameter không có bound thường xóa về `Object`.
- Type parameter có bound sẽ xóa về bound đầu tiên.
- Compiler có thể chèn casts và bridge methods.
- Type arguments có thể còn xuất hiện dưới dạng **metadata generic của khai báo**; điều đó không có nghĩa mỗi instance mang tham số kiểu được kiểm tra đầy đủ ở runtime.

### Tránh extends raw superclass

```java
class Box<T> {
    T value;
}

// Không nên:
class RawChild extends Box {
}
```

Raw type `Box` làm mất thông tin `T` ở subtype declaration. Thao tác trên field/method có thể trở nên yếu kiểm tra kiểu, phát cảnh báo và đưa `ClassCastException` tới nơi đọc dữ liệu.

Sửa bằng một trong hai hướng, tùy API mong muốn:

```java
class TypedChild<U> extends Box<U> {
}

class StringChild extends Box<String> {
}
```

- `TypedChild<U>` chuyển tiếp `U`.
- `StringChild` cố định type argument.
- Cả hai giữ quan hệ kiểu có thể được compiler kiểm tra.

Không dùng `@SuppressWarnings("unchecked")` để che warning từ raw superclass nếu có thể biểu diễn quan hệ thực bằng type arguments.

### Ranh giới runtime

Một biến `Parent<String>` không đảm bảo tuyệt đối dữ liệu luôn là String nếu có raw alias, unchecked casts hoặc nguồn bên ngoài không kiểm chứng. Generics bảo vệ phần lớn thao tác **khi các API tuân thủ kiểu tĩnh**. Với dữ liệu deserialize hoặc reflection, cần validation runtime thích hợp; type arguments không phải hệ thống kiểm tra nghiệp vụ độc lập.

## 17. Reflection: nhìn thấy superclass type argument đã khai báo

Thông tin generic trong **khai báo superclass** thường có thể được đọc bằng reflection, dù runtime của một object không mang specialized class riêng cho mọi type argument.

Tạo `GenericSuperclassDemo.java`:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public class GenericSuperclassDemo {
    static class Parent<T> {
    }

    static final class StringChild extends Parent<String> {
    }

    static class ForwardChild<U> extends Parent<U> {
    }

    public static void main(String[] args) {
        Type fixed = StringChild.class.getGenericSuperclass();
        Type forwarded = ForwardChild.class.getGenericSuperclass();

        System.out.println(fixed.getTypeName());
        System.out.println(forwarded.getTypeName());
        System.out.println(fixed instanceof ParameterizedType);
    }
}
```

Chạy:

```bash
javac GenericSuperclassDemo.java
java GenericSuperclassDemo
```

`stdout` trên JDK 17, với các class lồng như ví dụ:

```text
GenericSuperclassDemo$Parent<java.lang.String>
GenericSuperclassDemo$Parent<U>
true
```

Giải thích:

- `StringChild` ghi rõ superclass `Parent<String>` nên generic superclass metadata thể hiện `String`.
- `ForwardChild<U>` truyền một **type variable U** cho `Parent`; metadata của declaration biểu diễn `Parent<U>`.
- `getGenericSuperclass()` trả mô tả `Type`; khi chứa type arguments, thường là `ParameterizedType`.
- Đây là cách đọc **khai báo**, không phải suy ra type argument runtime của mọi instance qua `getClass()`.

Ví dụ `new ForwardChild<String>().getClass()` trả `ForwardChild.class`. Kiểu `String` không được lưu thành một subclass runtime mới. Nếu framework cần biết type arguments sau nhiều tầng kế thừa, nó phải phân tích generic metadata kết hợp mapping type variables qua từng tầng, hoặc yêu cầu thêm thông tin type tại runtime.

## 18. Những mô hình kế thừa generic thường dùng trong Java Core

### 18.1. Generic base + specialized subclass

Mẫu:

```java
class Response<T> {
    // Holds T
}

class TextResponse extends Response<String> {
}
```

Phù hợp khi subtype `TextResponse` có hành vi, tên miền hoặc invariant đặc thù. Nếu không thêm giá trị thiết kế, có thể dùng trực tiếp `Response<String>` để tránh quá nhiều lớp.

### 18.2. Generic base + forwarding generic subclass

Mẫu:

```java
class BaseRepository<ID, E> {
}

class CachedRepository<K, V> extends BaseRepository<K, V> {
}
```

`CachedRepository<Long,User>` trở thành subtype của `BaseRepository<Long,User>`. Mẫu này hữu ích khi lớp con thêm caching, logging hay measurement nhưng **không thay hợp đồng kiểu của dữ liệu**.

### 18.3. Generic interface + implementation cố định kiểu

Mẫu:

```java
interface Parser<T> {
    T parse(String input);
}

class IntegerParser implements Parser<Integer> {
    @Override
    public Integer parse(String input) {
        return Integer.parseInt(input);
    }
}
```

`Parser<Integer>` cam kết phương thức trả `Integer`; implementation có thể dựa vào `Integer.parseInt`. Đây là cách rõ ràng để dùng cùng một interface chung với nhiều kiểu kết quả khác nhau.

### 18.4. Interface kế thừa có thay đổi cấu trúc type argument

Mẫu:

```java
interface Reader<T> {
    T read();
}

interface PageReader<T> extends Reader<java.util.List<T>> {
}
```

`PageReader<String>` là một `Reader<List<String>>`. Sự bọc `List<T>` chuyển ý nghĩa của `read()` từ “đọc một T” thành “đọc một danh sách T”, trong khi vẫn tuân thủ generic contract của interface cha.

### 18.5. Kế thừa generic với multiple bounds

Mẫu:

```java
interface Named {
    String name();
}

class Registry<T extends Named> {
}

class SortedRegistry<U extends Named & Comparable<U>>
        extends Registry<U> {
}
```

Lớp con thêm bound `Comparable<U>` đồng thời vẫn thỏa yêu cầu `Named` của cha. Sự tồn tại của bound mới không tự làm superclass trở thành một loại generic khác; `Registry.T` vẫn được ánh xạ từ `SortedRegistry.U`.

Không nên thêm bound chỉ để chữ ký phức tạp. Bound phải phục vụ một thao tác mà compiler cần chứng minh trong subclass hoặc API.

## 19. Các lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Coi `class Child<T> extends Parent<T>` là dùng **cùng một khai báo T** ở hai class | Mỗi class khai báo biến kiểu của riêng nó; mệnh đề `extends` tạo mapping | Ghi rõ `Parent.T ← Child.T` |
| Viết `class Child<T> extends Parent` | Dùng raw superclass, mất quan hệ kiểu | Viết `extends Parent<T>` hoặc cố định `Parent<String>` |
| Nghĩ `Child<String>` luôn là `Parent<String>` | Subclass có thể truyền `List<T>` hoặc đảo vị trí | Đọc **type arguments trong `extends`** |
| Gán `Child<Integer>` cho `Parent<Number>` | Generic invariance | Giữ `Parent<Integer>` hoặc dùng view `Parent<? extends Number>` nếu chỉ đọc |
| Không lặp bound khi truyền vào cha có bound | Compiler không chứng minh subtype đáp ứng bound | Khai báo `<T extends Number>` hay type argument cụ thể thỏa bound |
| Viết override bằng `Object` vì nghĩ T đã xóa | Source-level override phải tương thích sau áp dụng type arguments | Dùng `@Override` với kiểu đã chuyên biệt hóa |
| Tưởng constructor được kế thừa như method | Constructor không được thừa kế | Khai báo constructor con và gọi `super(...)` |
| Mong implement cùng interface generic theo hai kiểu khác nhau | Hai instantiations không thể đồng thời kế thừa vào cùng subtype | Tách abstraction hoặc thiết kế một mapping nhất quán |
| Nghĩ class generic runtime có instance riêng cho mỗi T | Java generics dùng erasure | Phân biệt compiler type argument và runtime class |
| Nhầm `<R>` của generic method với `T` của class | Hai type parameters thuộc scope khác nhau | Dùng tên theo vai trò và theo dõi nơi khai báo |
| Ép kiểu unchecked để vượt lỗi inheritance | Có thể gây heap pollution, ClassCastException | Sửa mệnh đề extends/implements và hợp đồng kiểu |
| Coi `List<Integer>` là subtype `List<Number>` vì phần tử kế thừa | Generic invariance | Dùng wildcard theo chiều đọc/ghi |

## 20. Cách phân tích một cây kế thừa generic bằng giấy hoặc IDE

Khi gặp một class thực tế có nhiều tầng, thực hiện sáu bước:

1. **Ghi các type parameters tại mỗi declaration.** Ví dụ `Base<K,V>`, `Middle<T>`, `Leaf<E>`.
2. **Ghi nguyên biểu thức ở extends/implements.** Đừng lược `List<E>` thành `E` hoặc đảo vị trí type arguments.
3. **Lập mapping từ con sang cha.** Ví dụ `Middle<T> extends Base<String,List<T>>` nghĩa là `Base.K=String`, `Base.V=List<T>`.
4. **Áp dụng type argument của caller.** Với `Leaf<Integer>` suy ra từng bước đến `Base<String,List<Integer>>`.
5. **Kiểm tra method và field kế thừa theo mapping.** Một method `V get()` của Base trả `List<Integer>` ở Leaf này, không trả `Integer`.
6. **Đọc thêm hợp đồng override, bound và runtime.** Kiểu trả về tĩnh đúng chưa đủ: method có side effect gì, null có được phép không, dữ liệu có mutable không?

Ví dụ sơ đồ:

```text
Base<K, V>
    ▲
    | extends Base<String, List<T>>
Middle<T>
    ▲
    | extends Middle<E>
Leaf<E>

Leaf<Integer>
    -> Middle<Integer>
    -> Base<String, List<Integer>>
```

Nếu trên IDE bạn thấy `Base<String,List<Integer>>` là một supertype của `Leaf<Integer>`, đó chính là kết quả của phép chuyển tiếp từng tầng. Chỉ cần tìm type argument expression ở mỗi cạnh là có thể tự suy luận, không cần đoán.

## 21. Bài tập tự kiểm tra có lời giải

### Bài 1 — Truyền nguyên type parameter

Cho:

```java
class P<T> {
    T get() { return null; }
}

class C<U> extends P<U> {
}
```

Hỏi `C<String>` có `get()` trả kiểu gì tại compile time? Có là subtype của `P<String>` không?

**Đáp án:** `String`; có, vì `P.T ← C.U` rồi `U=String`. Việc `get()` hiện trả null trong thân minh họa không thay kiểu tĩnh.

### Bài 2 — Cố định type argument

Cho `class Text extends P<String> {}`. Hỏi `Text` còn là generic class không và có dùng `P<Integer>` làm kiểu biến để trỏ tới `Text` được không?

**Đáp án:** `Text` không generic; nó kế thừa `P<String>`. Không thể gán `Text` vào `P<Integer>` vì các generic instantiations đó không tương thích.

### Bài 3 — Chuyển tiếp biểu thức type

```java
class Root<X> {}
class Middle<Y> extends Root<java.util.Map<String, Y>> {}
class End<Z> extends Middle<java.util.List<Z>> {}
```

Hãy suy luận kiểu Root của `End<Integer>`.

**Đáp án:** `End<Integer>` → `Middle<List<Integer>>` → `Root<Map<String,List<Integer>>>`. Không được bỏ lớp `List` của ánh xạ tầng End hay lớp `Map` của Middle.

### Bài 4 — Đổi thứ tự hai parameters

```java
class Pair<K,V> {}
class Flip<A,B> extends Pair<B,A> {}
```

Hỏi `Flip<String,Long>` là subtype của `Pair<String,Long>` hay `Pair<Long,String>`?

**Đáp án:** `Pair<Long,String>`, vì `A=String`, `B=Long` rồi cha được áp dụng `K=B=Long` và `V=A=String`.

### Bài 5 — Interface forwarding

```java
interface Source<T> { T read(); }
interface Many<E> extends Source<java.util.List<E>> {}
```

`Many<Double>.read()` có kiểu trả về nào?

**Đáp án:** `List<Double>`. Không phải `Double`, vì `Source.T ← List<E>`.

### Bài 6 — Bound

```java
class Numeric<T extends Number> {}
// class GenericBad<U> extends Numeric<U> {}
class GenericGood<U extends Number> extends Numeric<U> {}
```

Vì sao `GenericBad` gây lỗi? Vì `U` không có bound bảo đảm `U` là subtype của `Number`. `GenericGood` khẳng định quan hệ đó trong declaration.

### Bài 7 — Override

```java
class Base<T> {
    T echo(T x) { return x; }
}

class TextBase extends Base<String> {
    @Override
    String echo(String x) { return x.toUpperCase(); }
}
```

Vì sao method con override hợp lệ? Vì superclass đã được áp dụng `T=String`. Compiler có thể tạo bridge method vì erasure để giữ dispatch runtime.

### Bài 8 — Invariance

Cho `class C<T> extends P<T> {}` và `C<Integer> c = ...`. Phân biệt:

- `P<Integer> exact = c;` — **hợp lệ**.
- `P<Number> wider = c;` — **không hợp lệ**.
- `P<? extends Number> readable = c;` — **hợp lệ**.

Lý do: subtype relation đến `P<Integer>` được khai báo trực tiếp, còn `P<Number>` không có quan hệ subtype qua generic argument; wildcard upper bound phù hợp kiểu dữ liệu của `c`.

### Bài 9 — Tự thiết kế

Thiết kế `interface Loader<T> { T load(); }` và `class ListLoader<E> implements Loader<List<E>>`. Viết implementation lưu một `List<E>`, trả snapshot qua `List.copyOf`. Thử `ListLoader<String>` và kiểm tra `Loader<List<String>>` nhận được. Giải thích phần nào do generic mapping, phần nào do lựa chọn immutable snapshot.

### Bài 10 — Phát hiện raw type

Cho `class Child extends Parent {}` trong đó `Parent<T>` generic. Hãy viết hai phương án sửa:

1. `class Child<U> extends Parent<U>` — tiếp tục generic.
2. `class Child extends Parent<String>` — cố định kiểu.

Giải thích vì sao chọn phương án nào phụ thuộc hợp đồng API, không phải vì một cú pháp luôn tốt hơn.

## 22. Tóm tắt các quy tắc cần nhớ

- `class Child<U> extends Parent<U>`: **chuyển tiếp** type parameter của con để tham số hóa cha.
- `class Child extends Parent<String>`: **cố định** type argument ở superclass; con không nhất thiết generic.
- `class Child<T> extends Parent<List<T>>`: **biến đổi biểu thức type argument**; với `Child<String>`, kiểu cha là `Parent<List<String>>`.
- `class Flip<A,B> extends Pair<B,A>`: **đổi vị trí** hai type arguments của cha.
- `interface Child<E> extends Parent<E>`: generic interface cũng có thể chuyển tiếp type parameter.
- `class Impl<E> implements Service<E>`: class triển khai một generic interface theo mapping chỉ định.
- Qua nhiều tầng, phép thay thế được **hợp thành**: đọc từng cạnh `extends`/`implements` từ subtype lên supertype.
- Mọi bound của supertype phải được thỏa ở nơi truyền type argument. `@Override` giúp xác minh method sau khi chuyên biệt hóa.
- `Child<Integer>` có thể là `Parent<Integer>`, nhưng **không tự là `Parent<Number>`**. Dùng wildcard khi cần biểu diễn quan hệ đọc/ghi linh hoạt.
- Java generics dùng erasure: quan hệ kiểu là bảo đảm compile time; bridge method hoặc casts có thể giữ tương thích runtime, chứ không tạo JVM class chuyên biệt cho mỗi `T`.

Hãy luôn tự hỏi: **“Type parameter này được khai báo ở class nào, biểu thức nào được truyền qua cạnh kế thừa, và cuối cùng những method kế thừa có kiểu gì ở điểm sử dụng?”** Trả lời chính xác ba câu đó là bạn có thể đọc, viết và kiểm tra một cây kế thừa generic trong Java Core mà không dựa vào các cast thiếu an toàn.