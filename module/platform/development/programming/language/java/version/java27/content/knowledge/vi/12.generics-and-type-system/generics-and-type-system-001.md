# Lớp, interface và phương thức generic trong Java 27

**Generics** cho phép khai báo lớp (class), interface, phương thức (method) và constructor có một hoặc nhiều *tham số kiểu* (*type parameters*). Thay vì lặp lại một cấu trúc cho từng kiểu dữ liệu, ta định nghĩa một hợp đồng kiểu tổng quát; trình biên dịch kiểm tra hợp đồng đó tại thời điểm biên dịch.

Trong Java 27, generics tiếp tục là cơ chế **kiểm tra kiểu tĩnh** của Java SE. Các ví dụ trong bài dùng cú pháp ổn định, không phụ thuộc preview hoặc các kỹ thuật raw type cũ. Phạm vi bài là cách **khai báo và sử dụng generic class, generic interface, generic method**; đồng thời giải thích những quy tắc của hệ thống kiểu mà lập trình viên cần nắm để thiết kế API đúng.

Các đoạn code chỉ gồm những lệnh khai báo biến hoặc gọi method là **mảnh ví dụ đặt bên trong thân một method** (chẳng hạn `main`). Những đoạn mã có khai báo `class`/`interface` đầy đủ được trình bày để có thể tách thành file nguồn tương ứng; khi đặt trong cùng project cần dùng tên class và package thống nhất.

## 1. Tại sao cần generics?

Giả sử ứng dụng phải lưu một giá trị, nhưng giá trị có thể là mã sách kiểu `String`, số lượng kiểu `Integer` hoặc một đối tượng nghiệp vụ.

Nếu một API chỉ nhận và trả về `Object`, người gọi phải ép kiểu và có thể phát hiện lỗi muộn:

```java
Object value = "Java 27";
Integer count = (Integer) value; // ClassCastException tại runtime
```

Với generic class, quan hệ giữa kiểu đầu vào và kiểu đầu ra được thể hiện rõ:

```java
Box<String> title = Box.of("Java 27");
String name = title.get(); // Compiler biết kết quả là String

// Integer count = title.get(); // Lỗi biên dịch: String không thể gán cho Integer
```

**Lợi ích chính:**

- **An toàn kiểu:** phát hiện nhiều phép gán hoặc lời gọi sai kiểu tại compile time thay vì chờ tới runtime.
- **Tái sử dụng:** một class/interface/method dùng được cho nhiều kiểu dữ liệu mà không sao chép logic.
- **API dễ hiểu:** `Repository<String, Book>` cho thấy rõ kiểu khóa và kiểu dữ liệu trả về.
- **Ít ép kiểu:** thao tác với `T` thông qua type argument cụ thể mà không phải viết cast ở mỗi điểm sử dụng.
- **Tích hợp thư viện hiện đại:** `List<E>`, `Map<K,V>`, `Optional<T>`, `Stream<T>` và các functional interface đều tận dụng generics.

Generics không đồng nghĩa với việc compiler tạo riêng một lớp runtime cho mỗi kiểu như `Box<String>` hay `Box<Integer>`. Java sử dụng cơ chế *type erasure*; giới hạn của nó được giải thích ở phần sau.

## 2. Đọc cú pháp type parameter và type argument

Ví dụ khai báo:

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

- `Box<T>` là **generic class declaration**.
- `T` là **type parameter**: tên đại diện cho một kiểu tham chiếu do người sử dụng cung cấp.
- `Box<String>` là **parameterized type**: kiểu `Box` với **type argument** `String`.
- `Box<Integer>` là một parameterization khác của cùng khai báo `Box<T>`.
- Một khai báo có thể có nhiều tham số kiểu: `Pair<K,V>`, `Mapper<I,O>` hoặc `Repository<ID,E>`.

Bảng quy ước thường gặp:

| Tên | Ý nghĩa thường dùng | Ví dụ |
| --- | --- | --- |
| `T` | Type — kiểu dữ liệu tổng quát | `Box<T>` |
| `E` | Element — phần tử tập hợp | `List<E>` |
| `K` | Key — khóa | `Map<K,V>` |
| `V` | Value — giá trị | `Map<K,V>` |
| `R` | Result — kiểu kết quả biến đổi | `<R> R map(...)` |
| `ID`, `SOURCE`, `TARGET` | Tên nhiều chữ cái mô tả vai trò rõ hơn | `Repository<ID,ENTITY>` |

Tên type parameter là identifier hợp lệ của Java, không nhất thiết chỉ gồm một chữ cái. Dùng tên ngắn khi vai trò đã rõ; với API nhiều tham số có thể dùng tên có ý nghĩa để tránh nhầm thứ tự.

**Quan trọng:** trong mô hình generics chuẩn của Java 27, type argument thông thường phải là kiểu tham chiếu, không phải primitive. Vì vậy viết `Box<Integer>` thay cho `Box<int>`. Khi đưa `int` vào nơi cần `Integer`, Java có thể tự động boxing.

## 3. Generic class: định nghĩa cấu trúc dùng lại

### 3.1. Ví dụ một tham số kiểu

Một generic class hoàn chỉnh, bất biến sau khi tạo:

```java
// Box.java
import java.util.Objects;
import java.util.function.Function;

public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public T get() {
        return value;
    }

    public <R> Box<R> map(Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(mapper, "mapper");
        return Box.of(mapper.apply(value));
    }

    public static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

Sử dụng:

```java
Box<String> title = new Box<>("Generics");
String text = title.get();

Box<Integer> quantity = Box.of(27);
int count = quantity.get(); // Unboxing Integer -> int

Box<String> label = quantity.map(number -> "Quantity = " + number);
System.out.println(label.get()); // Quantity = 27
```

Giải thích:

1. `T` có phạm vi trong phần instance phù hợp của class, nên có thể dùng làm kiểu của `value`, constructor parameter và kiểu trả về của `get()`.
2. Khi tạo `Box<String>`, compiler kiểm tra các thao tác trên `get()` theo kiểu `String`. Với `Box<Integer>`, kiểu trả về tương ứng là `Integer`.
3. `map` có **type parameter riêng** là `R`: nó có thể biến một `Box<T>` thành `Box<R>` mà không phải thay đổi khai báo class.
4. `of` là **generic static method** với `U` riêng; nó không dựa vào `T` của một đối tượng `Box<T>`.
5. Constructor hiện tại từ chối `null` bằng `Objects.requireNonNull`; đây là quyết định thiết kế của ví dụ, **không** phải ràng buộc chung của Java generics.

### 3.2. Nhiều type parameter

```java
record Pair<K, V>(K key, V value) {
}

class PairExample {
    public static void main(String[] args) {
        Pair<String, Integer> stock = new Pair<>("notebooks", 27);

        String product = stock.key();
        Integer amount = stock.value();

        System.out.println(product + ": " + amount);
    }
}
```

`record` có thể khai báo type parameters giống generic class thông thường. `Pair<String,Integer>` cho biết field `key` thuộc kiểu `String` và field `value` thuộc kiểu `Integer`.

Không thể đảo type argument tùy ý. Ví dụ `Pair<Integer,String>` là một kiểu sử dụng khác, và sẽ không tương thích với chỗ cần `Pair<String,Integer>`.

### 3.3. Suy luận kiểu bằng diamond `<>`

Khi type argument đã rõ từ **ngữ cảnh**, constructor có thể dùng toán tử diamond:

```java
Box<String> name = new Box<>("Java");
java.util.List<String> tags = new java.util.ArrayList<>();
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
```

Compiler suy luận `String` từ biến đích của `Box<String>` và `List<String>`, cũng như cặp `String,Integer` từ `Map<String,Integer>`.

**Không nhầm diamond với raw type:**

```java
java.util.List<String> good = new java.util.ArrayList<>(); // Generic, an toàn kiểu

// java.util.List<String> bad = new java.util.ArrayList();
// Dạng không có <> là raw type: có thể sinh unchecked warning.
```

Nếu dùng `var` mà bên phải không cung cấp đủ ràng buộc kiểu, kết quả suy luận có thể quá rộng:

```java
var values = new java.util.ArrayList<>();       // ArrayList<Object>
var names = new java.util.ArrayList<String>(); // ArrayList<String>
java.util.List<String> moreNames = new java.util.ArrayList<>();
```

Dùng kiểu đích rõ ràng khi API cần chắc chắn phần tử thuộc `String` hoặc một kiểu cụ thể khác.

## 4. Generic interface: khai báo hợp đồng độc lập triển khai

Một generic interface đặt type parameters sau tên interface. Các class triển khai phải đáp ứng hợp đồng với đúng kiểu tương ứng.

### 4.1. Functional interface generic

```java
@FunctionalInterface
interface Converter<I, O> {
    O convert(I input);
}

class ConverterExample {
    public static void main(String[] args) {
        Converter<String, Integer> parse = Integer::parseInt;
        Converter<Integer, String> label = n -> "Value: " + n;

        Integer number = parse.convert("27");
        String output = label.convert(number);

        System.out.println(output); // Value: 27
    }
}
```

`I` là kiểu đầu vào và `O` là kiểu đầu ra. Cùng một khai báo `Converter<I,O>` hoạt động với các cặp kiểu khác nhau. Lambda hoặc method reference được kiểm tra theo functional interface type cụ thể tại nơi gán.

### 4.2. Interface có nhiều vai trò kiểu và class triển khai

Ví dụ kho lưu dữ liệu theo kiểu khóa và kiểu entity:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

interface Repository<ID, E> {
    Optional<E> findById(ID id);
    void save(ID id, E entity);
}

final class InMemoryRepository<ID, E> implements Repository<ID, E> {
    private final Map<ID, E> values = new HashMap<>();

    @Override
    public Optional<E> findById(ID id) {
        return Optional.ofNullable(values.get(id));
    }

    @Override
    public void save(ID id, E entity) {
        values.put(
                Objects.requireNonNull(id, "id"),
                Objects.requireNonNull(entity, "entity")
        );
    }
}

record Book(String isbn, String title) {
}

class RepositoryExample {
    public static void main(String[] args) {
        Repository<String, Book> books = new InMemoryRepository<>();

        books.save("978-000", new Book("978-000", "Java 27"));
        Book book = books.findById("978-000").orElseThrow();

        System.out.println(book.title()); // Java 27
    }
}
```

Các điểm cần nhớ:

- `Repository<ID,E>` biểu diễn hợp đồng tổng quát; không bắt buộc biết kiểu khóa/entity cụ thể.
- `InMemoryRepository<ID,E>` giữ nguyên type parameters khi `implements Repository<ID,E>`.
- `Repository<String,Book>` cố định kiểu khóa là `String` và kiểu entity là `Book`, nên lời gọi `save(27, book)` không hợp lệ.
- `Optional<E>` diễn đạt rõ trường hợp không tìm thấy entity mà không ép caller phải giả định luôn có giá trị. Ví dụ chỉ minh họa type system; `HashMap` không tự bảo đảm thread safety.

Một class cũng có thể chọn type argument cụ thể tại thời điểm triển khai, ví dụ `class StringConverter implements Converter<Integer,String>`. Nếu tiếp tục dùng type parameter `T`, class phải tự khai báo `<T>`; nó không tự nhận type parameter từ interface.

### 4.3. Interface generic cũng có generic method

Một phương thức trên interface có thể khai báo type parameter **độc lập** với type parameters của interface:

```java
import java.util.Optional;
import java.util.function.Function;

interface ReadableStore<ID, E> {
    Optional<E> findById(ID id);

    default <R> Optional<R> findMapped(
            ID id, Function<? super E, ? extends R> mapper) {
        return findById(id).map(mapper);
    }
}
```

Ở đây `ID` và `E` thuộc về interface, trong khi `R` chỉ thuộc phương thức `findMapped`. Ví dụ với `ReadableStore<String,Book>`, caller có thể lấy `Optional<String>` bằng cách map entity `Book` sang tên sách, hoặc `Optional<Integer>` bằng cách map sang độ dài tên.

## 5. Generic method: đặt tham số kiểu ở đâu?

Một method là generic khi **chính method đó** khai báo ít nhất một type parameter. Phần `<T>` xuất hiện trước **kiểu trả về**:

```java
import java.util.List;

final class GenericMethods {
    private GenericMethods() {
    }

    static <T> T firstOrDefault(List<T> items, T fallback) {
        return items.isEmpty() ? fallback : items.get(0);
    }

    static <T> List<T> singleton(T item) {
        return List.of(item);
    }
}
```

Khi gọi:

```java
String first = GenericMethods.firstOrDefault(
        java.util.List.of("A", "B"), "(empty)");

Integer number = GenericMethods.firstOrDefault(
        java.util.List.of(10, 20), -1);

java.util.List<String> one = GenericMethods.singleton("Java");
```

Trong `firstOrDefault`, type parameter `T` nối quan hệ kiểu giữa phần tử của danh sách, giá trị dự phòng và giá trị trả về. Nếu viết trả về `Object` thay vì `T`, API không giữ được hợp đồng này.

**Cú pháp dễ nhầm:**

```java
static <T> T identity(T input) { return input; } // Generic method

// static T identity(T input) { return input; }
// Lỗi nếu method ở class không khai báo T và bản thân method cũng không khai báo <T>.
```

### 5.1. Generic method không nhất thiết nằm trong generic class

Một class thông thường như `GenericMethods` vẫn có thể có nhiều generic method. Ngược lại, method nằm trong generic class chưa chắc là generic method:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {                  // Dùng T của class, bản thân method không generic
        return value;
    }

    <R> R convert(java.util.function.Function<? super T, ? extends R> fn) {
        return fn.apply(value); // R do method tự khai báo
    }

    static <U> Holder<U> of(U value) {
        return new Holder<>(value);
    }
}
```

`get()` trả về `T` do class khai báo. `convert` có `R` riêng, và `of` có `U` riêng. **Static method không thể dùng type parameter `T` thuộc instance của generic class**; muốn generic, static method cần tự khai báo tham số kiểu của mình.

### 5.2. Explicit type arguments và type inference

Thông thường compiler suy luận type argument khi gọi method:

```java
String text = GenericMethods.firstOrDefault(
        java.util.List.of("first", "second"), "unknown");
```

Có thể chỉ rõ type argument khi cần:

```java
String text = GenericMethods.<String>firstOrDefault(
        java.util.List.of("first"), "unknown");

java.util.List<String> words = GenericMethods.<String>singleton("Java");
```

`<String>` trong lời gọi là **type argument**, không phải một type parameter declaration mới. Type inference xem xét tham số method, biểu thức đối số và trong các tình huống phù hợp cả kiểu đích (target type). Không nên cho rằng compiler sẽ luôn suy ra đúng kiểu mình muốn khi các đối số quá ít thông tin; hãy cung cấp khai báo biến/kiểu đích rõ ràng hoặc explicit type arguments khi cần.

Ví dụ `List.of()` không có phần tử nên thiếu bằng chứng kiểu từ nội dung:

```java
java.util.List<String> strings = java.util.List.of();
var noElements = java.util.List.of(); // Suy luận List<Object> nếu không có kiểu đích
```

### 5.3. Generic constructor là khái niệm liên quan

Constructor cũng có thể có type parameters riêng với class. Nó không phải method, nhưng cú pháp khai báo kiểu tương tự:

```java
final class Tagged<T> {
    private final String label;
    private final T value;

    <S extends CharSequence> Tagged(S label, T value) {
        this.label = java.util.Objects.requireNonNull(label).toString();
        this.value = value;
    }

    T value() {
        return value;
    }

    String label() {
        return label;
    }
}

class TaggedExample {
    public static void main(String[] args) {
        Tagged<Integer> tagged = new Tagged<>("requests", 27);
        System.out.println(tagged.label() + " = " + tagged.value());
    }
}
```

Trong ví dụ, `T` thuộc class còn `S` thuộc constructor. Compiler suy luận `S` là `String` từ đối số `"requests"`. Với constructor không generic, không cần khai báo thêm `<S>`.

## 6. Type bounds: giới hạn kiểu được chấp nhận

Type parameter mặc định có upper bound là `Object`. Nếu thuật toán cần gọi method của một interface hoặc class cụ thể, hãy khai báo bound:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}

NumericBox<Integer> count = new NumericBox<>(27);
NumericBox<java.math.BigDecimal> amount =
        new NumericBox<>(new java.math.BigDecimal("27.5"));

// NumericBox<String> invalid = new NumericBox<>("27");
// Lỗi: String không extends Number.
```

`<T extends Number>` giới hạn `T` trong các subtype của `Number`. Vì vậy `doubleValue()` hợp lệ trong body của class. Với interface cũng dùng từ khóa **`extends`**, không dùng `implements` trong type parameter bound.

### 6.1. Nhiều bound với ký hiệu `&`

```java
import java.math.BigDecimal;

final class Numbers {
    static <T extends Number & Comparable<T>> T larger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }
}

Integer greaterInt = Numbers.larger(10, 27);
BigDecimal greaterAmount = Numbers.larger(
        new BigDecimal("15.25"),
        new BigDecimal("27.50")
);
```

Giải thích:

- `Number` là class bound, phải đứng trước các interface bound.
- `Comparable<T>` là interface bound, cho phép gọi `compareTo` trên kiểu `T`.
- Khi có nhiều interface, dùng `T extends SomeClass & FirstInterface & SecondInterface` (với điều kiện các bound hợp lệ).
- Chỉ được có **tối đa một class bound**, ở vị trí đầu tiên. Một số bound có thể chỉ là interface, ví dụ `T extends CharSequence & Comparable<T>`.
- Phần `<T extends A & B>` là **intersection bound**; không phải toán tử bitwise `&` của biểu thức.

### 6.2. Bound với type parameter khác

Bounds cũng có thể phụ thuộc vào các type parameter đã khai báo:

```java
interface Entity<ID> {
    ID id();
}

final class EntityCache<ID, E extends Entity<ID>> {
    private final java.util.Map<ID, E> entries =
            new java.util.HashMap<>();

    void put(E entity) {
        entries.put(entity.id(), entity);
    }

    E find(ID id) {
        return entries.get(id);
    }
}
```

`E extends Entity<ID>` khẳng định mọi entity có method `id()` trả về đúng kiểu `ID`. Mối liên hệ này là một phần hợp đồng API, không chỉ là ghi chú tài liệu.

Với các kiểu tham gia quan hệ phức tạp, hãy dùng bound thể hiện đúng khả năng cần thiết và tránh ràng buộc quá cụ thể làm mất khả năng tái sử dụng. Khi chỉ cần đọc, viết hoặc so sánh, chọn abstraction tương ứng thay vì bắt caller phụ thuộc vào một implementation class.

## 7. Quan hệ kiểu: invariance và wildcard

Generic parameterization **không tự hiệp biến**. Dù `Integer extends Number`, `List<Integer>` **không** phải subtype của `List<Number>`:

```java
java.util.List<Integer> integers = java.util.List.of(1, 2, 3);

// java.util.List<Number> numbers = integers; // Lỗi biên dịch
java.util.List<? extends Number> numbers = integers; // Hợp lệ
```

Vì sao cần quy tắc này? Nếu `List<Integer>` được xem như `List<Number>`, mã khác có thể thêm `Double` vào danh sách vốn chỉ chứa `Integer`. Compiler ngăn việc mất an toàn kiểu này.

Nhưng `ArrayList<Integer>` vẫn là subtype của `List<Integer>`: generic invariance áp dụng cho **thay đổi type argument** (`Integer` sang `Number`), không phủ nhận quan hệ kế thừa giữa các collection class/interface cùng type argument.

### 7.1. `? extends T` để đọc, `? super T` để ghi

Wildcard cho phép API diễn đạt variance ở **vị trí sử dụng** (*use-site variance*):

```java
import java.util.List;

final class NumberOperations {
    static double sum(List<? extends Number> numbers) {
        double result = 0;
        for (Number number : numbers) {
            result += number.doubleValue();
        }
        return result;
    }

    static void addDefaults(List<? super Integer> destination) {
        destination.add(1);
        destination.add(2);
    }
}
```

Dùng thử:

```java
List<Integer> integers = List.of(3, 5, 7);
double total = NumberOperations.sum(integers); // 15.0

List<Number> values = new java.util.ArrayList<>();
NumberOperations.addDefaults(values);         // Được thêm Integer
```

- `List<? extends Number>`: phần tử có một kiểu nào đó là subtype của `Number`. Có thể đọc thành `Number`; thông thường **không được thêm** một `Integer` hoặc `Double` tùy ý (ngoại lệ có thể thêm `null`).
- `List<? super Integer>`: phần tử được khai báo với một kiểu nào đó là supertype của `Integer`. Có thể thêm `Integer`; khi đọc an toàn tổng quát, kiểu nhận được chỉ bảo đảm là `Object`.
- `List<?>`: không biết type argument cụ thể; đọc có thể nhận `Object`, không thể thêm phần tử khác `null` một cách an toàn.

Quy tắc ghi nhớ thường dùng: **PECS** (*Producer Extends, Consumer Super*). Nếu API chỉ tiêu thụ dữ liệu từ collection, ưu tiên `? extends T`; nếu chỉ ghi thêm giá trị kiểu `T`, ưu tiên `? super T`. Khi cần vừa đọc đúng `T` vừa ghi `T`, `List<T>` thường phù hợp hơn.

Trong Java, wildcard chỉ dùng làm **type argument** tại chỗ sử dụng, ví dụ `List<? extends Number>`. Không thể khai báo type parameter bằng cách viết `class Box<?>`.

### 7.2. Chọn type parameter hay wildcard?

Sử dụng **type parameter** khi cần đặt một cái tên để liên hệ nhiều vị trí kiểu:

```java
static <T> T firstOrDefault(java.util.List<T> list, T fallback) {
    return list.isEmpty() ? fallback : list.get(0);
}
```

Sử dụng **wildcard** khi chỉ muốn chấp nhận một nhóm kiểu mà không cần giữ tên type variable:

```java
static int countAll(java.util.Collection<?> items) {
    return items.size();
}
```

Việc chọn wildcard không thay thế việc khai báo một quan hệ kiểu giữa đầu vào và đầu ra. Nếu method trả lại đúng kiểu từ một tham số, phương thức generic với `<T>` thường diễn đạt hợp đồng tốt hơn kiểu trả về `Object`.

## 8. Type erasure và giới hạn cần biết

Generics trong Java 27 vẫn dựa trên **type erasure** (JLS §4.6). Nói đơn giản, tại compile time compiler kiểm tra các ràng buộc generic; khi hình thành bytecode, các type parameter được ánh xạ về erasure của bound tương ứng (mặc định là `Object`).

Ví dụ, đây là mô hình khái niệm để hiểu erasure, **không phải mã nguồn mà developer phải tự viết**:

```text
class Holder<T> { T value; }                 --> field có erasure Object
class NumericBox<T extends Number> { T v; }  --> field có erasure Number
ArrayList<String>                             --> runtime class java.util.ArrayList
ArrayList<Integer>                            --> runtime class java.util.ArrayList
```

Hệ quả:

1. Không tồn tại runtime class riêng biệt cho mỗi `Box<String>` và `Box<Integer>` chỉ vì type arguments khác nhau.
2. Không thể viết `new T()` hoặc `T.class` để tạo/truy cập runtime class của type parameter. Nếu cần tạo instance, truyền factory như `Supplier<? extends T>` hoặc một cơ chế tạo đối tượng được xác định rõ.
3. Không thể dùng `instanceof List<String>` để kiểm tra type argument chính xác ở runtime; `instanceof List<?>` hợp lệ.
4. Không thể tạo trực tiếp mảng có component type không *reifiable* như `new List<String>[10]` hoặc `new T[10]`. Thường dùng `List<List<String>>` hay collection phù hợp thay vì mảng generic.
5. Không thể overload hai method chỉ khác `List<String>` và `List<Integer>` vì sau erasure chúng có chữ ký xung đột.
6. Thông tin generic vẫn có thể tồn tại trong chữ ký khai báo để reflection hoặc công cụ phân tích đọc được; điều đó **không** làm cho `List<String>` và `List<Integer>` trở thành hai runtime class khác nhau.

Kiểm tra đúng khi không biết kiểu phần tử ở runtime:

```java
Object candidate = java.util.List.of("Java", "27");

if (candidate instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
    Object first = list.get(0);
    System.out.println(first);       // Java
}
```

Nếu chương trình cần kiểm tra từng phần tử, hãy kiểm tra riêng từng giá trị với pattern matching hoặc logic nghiệp vụ, thay vì thử ép cả collection thành `List<String>` mà không có bằng chứng.

### Raw type không còn là lựa chọn nên dùng cho API mới

Raw type là cách sử dụng một generic type mà không cung cấp type arguments (ví dụ viết `List` thay cho `List<String>`). Cơ chế này vẫn tồn tại để bảo đảm tương thích mã cũ, nhưng nó bỏ qua nhiều bước kiểm tra kiểu và thường phát sinh **unchecked warnings**.

**Trong mã Java 27 mới, khai báo đầy đủ type arguments hoặc wildcard thích hợp**, chẳng hạn `List<String>`, `List<?>`, `Map<String,Integer>`, và tránh sử dụng raw type chỉ để làm biến mất lỗi biên dịch. Không nên dùng `@SuppressWarnings("unchecked")` theo thói quen; khi tích hợp thư viện thiếu thông tin kiểu, hãy cô lập phép chuyển đổi không kiểm tra, xác minh điều kiện an toàn và chỉ giới hạn suppression trong phạm vi nhỏ nhất.

## 9. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Box<int>` không biên dịch | Primitive không là type argument hợp lệ trong generics chuẩn Java 27 | Dùng `Box<Integer>`, boxing/unboxing khi cần |
| `static T current;` trong `class Box<T>` bị lỗi | Thành viên static không có một instance type parameter `T` cụ thể | Dùng static generic method với tham số kiểu riêng, hoặc đặt state ở instance |
| `T value = new T();` bị lỗi | Type erasure không cung cấp constructor của `T` ở runtime | Truyền `Supplier<? extends T>`/factory hoặc instance đã tạo |
| Gán `List<Integer>` vào `List<Number>` bị lỗi | Generic type arguments là invariant | Dùng `List<? extends Number>` khi cần đọc, hoặc thiết kế API dùng wildcard phù hợp |
| Gọi `compareTo` trên `T` không bound | `T` mặc định chỉ bảo đảm hành vi của `Object` | Khai báo `T extends Comparable<? super T>` khi cần |
| Thứ tự bound `T extends Runnable & Number` bị lỗi | Nếu có class bound, class phải đứng trước interface | Viết `T extends Number & Runnable` khi kiểu thực sự có cả hai đặc tính |
| Method `T copy(T x)` không nhận diện `T` trong class không generic | Method chưa khai báo type parameter | Viết `<T> T copy(T x)` |
| Hai overload nhận `List<String>` và `List<Integer>` báo `name clash` | Hai chữ ký bị trùng sau erasure | Dùng tên method khác hoặc thiết kế hợp đồng đầu vào khác |
| `instanceof List<String>` hoặc `new T[10]` báo lỗi | Type argument không reifiable tại runtime | Kiểm tra `List<?>`, dùng collection thay cho generic array |
| Nhận `unchecked warning` từ việc dùng `List` trần | Raw type bỏ qua ràng buộc generics | Thay bằng type arguments/wildcard và loại bỏ ép kiểu không được kiểm chứng |
| `var items = new ArrayList<>()` cho kết quả không mong muốn | Thiếu target type, compiler suy luận `Object` | Khai báo `List<String> items = new ArrayList<>()` khi cần loại phần tử xác định |

Đừng giải quyết lỗi generics bằng cách ép kiểu sang `Object` hoặc dùng raw type mặc định. Lỗi thường báo rằng mối quan hệ kiểu của API chưa được thiết kế hoặc thể hiện đúng.

## 10. Thực hành thiết kế API generic

Bài toán: cần một method lấy phần tử đầu tiên trong danh sách, dùng giá trị dự phòng khi danh sách rỗng, đồng thời giữ đúng kiểu kết quả.

Một cách viết hạn chế tính an toàn:

```java
static Object firstOrDefault(
        java.util.List<?> items, Object fallback) {
    return items.isEmpty() ? fallback : items.get(0);
}
```

Caller phải xử lý `Object` và có thể truyền fallback không tương thích với phần tử. Dạng generic biểu diễn quan hệ rõ hơn:

```java
static <T> T firstOrDefault(
        java.util.List<T> items, T fallback) {
    return items.isEmpty() ? fallback : items.get(0);
}

String name = firstOrDefault(java.util.List.of("Lan", "Mai"), "(none)");
Integer score = firstOrDefault(java.util.List.of(27, 25), 0);
```

Lưu ý: nếu truyền các đối số thuộc nhiều kiểu khác nhau mà không có kiểu đích cụ thể, compiler đôi khi vẫn suy luận một supertype chung như `Object` cho `T`. Khai báo kiểu đích rõ ràng và giữ các type arguments nhất quán để bảo vệ ý nghĩa nghiệp vụ.

Các quy tắc nên áp dụng khi phát triển dự án:

1. **Đặt type parameter đúng cấp:** nếu trạng thái instance phải giữ cùng kiểu, khai báo ở class/interface; nếu chỉ một thao tác cần type variable, khai báo ở method.
2. **Dùng bounds nhỏ nhất có ích:** chỉ ràng buộc khả năng thật sự cần, ví dụ `Comparable<? super T>` khi so sánh hoặc `Number` khi xử lý số.
3. **Thể hiện quan hệ đầu vào–đầu ra:** dùng cùng `T` khi kết quả cùng kiểu với đối số; dùng `<R>` khi có bước biến đổi thành kiểu khác.
4. **Ưu tiên interface ở public API:** cho caller phụ thuộc vào `List<T>`/`Collection<T>` hoặc interface nghiệp vụ thay vì ép họ dùng class triển khai cụ thể.
5. **Chọn wildcard theo chiều dữ liệu:** `? extends T` để đọc; `? super T` để ghi; cân nhắc `T` khi cả hai chiều cần liên hệ chính xác.
6. **Không dùng raw type để né compiler:** xử lý ràng buộc sai hoặc xây adapter có kiểm tra rõ ràng ở ranh giới với mã cũ.
7. **Chọn tên dễ hiểu:** `K,V` thường đủ cho bản đồ khóa–giá trị, nhưng `ID,ENTITY` có thể dễ đọc hơn trong repository.
8. **Phân biệt compile-time với runtime:** khi cần runtime metadata, truyền rõ một type token hoặc factory; đừng mong erasure giữ nguyên mọi type argument trên từng object.
9. **Giữ ví dụ và cấu hình hiện hành:** Java 27 hỗ trợ generic class/interface/method, record generic, lambda, diamond và suy luận kiểu mà không yêu cầu `--enable-preview`.

## Tài liệu tham khảo chính thức

- [Java Language Specification — Java SE 27, §4.4 Type Variables](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.4) — type parameters, bounds và phạm vi kiểu.
- [Java Language Specification — Java SE 27, §4.5 Parameterized Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.5) — type arguments và parameterized types.
- [Java Language Specification — Java SE 27, §4.6 Type Erasure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.6) — cơ chế xóa kiểu khi biên dịch.
- [Java Language Specification — Java SE 27, §8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.1.2) — generic class và khai báo type parameters.
- [Java Language Specification — Java SE 27, §8.4.4 Generic Methods](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.4) — generic method và phạm vi tham số kiểu.
- [Java Language Specification — Java SE 27, §8.8.4 Generic Constructors](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8.4) — constructor có type parameters riêng.
- [Java Language Specification — Java SE 27, §9.1.2 Generic Interfaces and Type Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.1.2) — generic interface.
- [Java Language Specification — Java SE 27, Chapter 18 Type Inference](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-18.html) — quy tắc suy luận kiểu từ đối số và ngữ cảnh.
