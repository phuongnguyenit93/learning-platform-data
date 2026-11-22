# Phương thức generic trong lớp generic hoặc lớp thông thường (Java)

## 1. Khái niệm và mục đích

**Phương thức generic** (*generic method*) là phương thức **tự khai báo một hoặc nhiều tham số kiểu** như `<T>`, `<K,V>` hay `<T extends Number>`. Tham số kiểu ấy chỉ có phạm vi trong khai báo phương thức và được compiler suy luận hoặc xác định theo từng lần gọi. Một phương thức generic có thể nằm trong:

- Lớp thông thường (không khai báo tham số kiểu);
- Lớp generic, đồng thời dùng hoặc không dùng tham số kiểu của lớp;
- Lớp tiện ích với phương thức `static`;
- Interface (bao gồm phương thức abstract, default hoặc static), miễn là chữ ký phù hợp.

Ví dụ đặc trưng:

```java
// Đoạn minh họa; đặt trong một lớp có import java.util.List.
static <T> T first(List<T> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException("Empty list");
    }
    return items.get(0);
}
```

Ký hiệu `<T>` **đứng trước kiểu trả về** `T`. Nó **khai báo** tham số kiểu của phương thức. `List<T>` liên kết kiểu đầu vào với kiểu kết quả: đưa vào `List<String>` sẽ nhận `String`; đưa vào `List<Integer>` sẽ nhận `Integer`. Trình biên dịch kiểm tra các quan hệ này trước khi chạy.

```java
// Trong một phương thức/chương trình Java:
String name = first(List.of("Lan", "Mai"));
Integer score = first(List.of(8, 9));
// String wrong = first(List.of(8, 9)); // Lỗi vì không tương thích String.
```

Trong phần trên, `first` không cần biết lớp chứa nó có generic hay không. Điều quan trọng là **chính phương thức khai báo `<T>`**. Ngược lại, một phương thức chỉ tham chiếu `T` được khai báo bởi lớp không tự động trở thành generic method.

Bài học sử dụng cú pháp chạy được trên **Java 17+**, phân biệt các mảnh minh họa với ví dụ đầy đủ `GenericMethodLesson.java` ở mục 11.

## 2. Cú pháp: tham số kiểu, kiểu trả về và danh sách tham số

Phương thức có thể khai báo type parameters dù **class chứa nó có hoặc không có `<T>`**:

```java
static <T> T first(java.util.List<T> xs) {
    return xs.get(0);
}

static <K, V> java.util.Map.Entry<K, V> pair(K k, V v) {
    return java.util.Map.entry(k, v);
}
```

Trong cả hai chữ ký, phần `<...>` đặt trước return type **thuộc riêng method**. Đừng nhầm `List<T>`/`Map.Entry<K,V>` với nơi khai báo type parameter: chúng là vị trí sử dụng type variables. Trọng tâm tiếp theo là nơi method được đặt — lớp thường, lớp generic hoặc interface — và scope của từng type variable.

## 3. Phương thức generic trong lớp thông thường

Lớp không có tham số kiểu vẫn có thể sở hữu nhiều phương thức generic, mỗi phương thức tự quyết định tham số của mình. Cách này phù hợp các thao tác tiện ích, factory hoặc chuyển đổi dữ liệu.

```java
import java.util.*;

final class CollectionTools {
    private CollectionTools() {}

    static <T> List<T> singletonMutable(T element) {
        List<T> result = new ArrayList<>();
        result.add(element);
        return result;
    }

    static <K, V> Map<K, V> oneEntry(K key, V value) {
        Map<K, V> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    static <T> T last(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("Empty list");
        }
        return values.get(values.size() - 1);
    }
}
```

Các lời gọi:

```java
List<String> words = CollectionTools.singletonMutable("java");
List<Integer> numbers = CollectionTools.singletonMutable(42);
Map<String, Integer> stock = CollectionTools.oneEntry("book", 5);
String lastWord = CollectionTools.last(List.of("A", "B")); // "B"
```

`singletonMutable` trả danh sách có thể sửa, khác với `List.of(element)` là factory tạo list không sửa được. Việc xây dựng `new ArrayList<>()` vẫn an toàn: kiểu `T` của phương thức cung cấp ràng buộc cho danh sách mới.

`oneEntry` cho thấy nhiều tham số kiểu có ý nghĩa: `K` (key) và `V` (value) được suy luận độc lập. Nếu khai báo `Map<T,T>` thay vì `Map<K,V>`, ta sẽ làm mất khả năng diễn tả rõ quan hệ hai kiểu khác nhau hoặc buộc compiler tìm một kiểu chung rộng hơn.

Một lớp thông thường còn có **phương thức instance generic**:

```java
class Formatter {
    <T> String describe(T item) {
        return "Value: " + item;
    }
}

String s = new Formatter().describe(100); // "Value: 100"
```

`Formatter` không có `<T>` sau tên lớp, nhưng `describe` có `<T>` trước `String` nên vẫn là generic method. Ở đây type parameter không bắt buộc để tạo chuỗi vì có thể nhận `Object`; nếu không cần ràng buộc kiểu nào, chọn `Object` có thể đơn giản hơn. Generic đem lại giá trị cao nhất khi **liên kết nhiều vị trí kiểu** hoặc cho phép bound bảo đảm thao tác cần thiết.

## 4. Ba loại phương thức có thể có trong một lớp generic

Trong một lớp generic, bạn có thể gặp ba trường hợp:

```java
class Container<T> {
    private final T value;
    Container(T value) { this.value = value; }

    T get() { return value; }                  // Dùng T của class.
    <U> U echo(U input) { return input; }       // Tự khai báo U.
    static <V> V staticEcho(V x) { return x; }  // Static generic method.
}
```

| Dạng | Phạm vi type variable | Điểm đáng chú ý |
| --- | --- | --- |
| `T get()` | `T` của class | **Không** tự khai báo generic method |
| `<U> U echo(U)` | `U` của method | Lời gọi có thể suy luận `U` độc lập với `T` |
| `static <V> V staticEcho(V)` | `V` của method | Không thể dùng trực tiếp instance type variable của class |

Vì vậy, `Container<String>` có thể gọi `echo(42)`, nhưng `get()` vẫn trả kiểu tĩnh `String`. Đây là so sánh cần thiết để tiếp tục đọc các ví dụ trong **lớp thường** và **lớp generic** mà không lẫn phạm vi.

## 5. Không nhầm `T` của lớp với `T` của phương thức

Một method có thể khai báo type parameter **trùng tên** với type parameter của class. Trong method đó, tên mới che khuất tên ở phạm vi class:

```java
class ConfusingBox<T> {
    T original;
    ConfusingBox(T value) { original = value; }
    <T> T echo(T input) { return input; }
}
```

`ConfusingBox<String>` vẫn lưu `String` trong `original`, nhưng `echo(123)` có thể suy luận `Integer` cho **method-level `T`**. Đây không phải thay đổi kiểu của class. Trong code production, chọn tên `<U>` cho method để không gây hiểu nhầm. Bài đối chiếu phạm vi ở chương này tiếp tục phân tích rõ cả việc kết hợp `T` của class và `R` của method.

## 6. Suy luận tham số kiểu tại từng lời gọi

Compiler xem **kiểu đối số** và khi thích hợp **target type** để suy luận type parameters của generic method:

```java
static <T> java.util.List<T> singleton(T x) {
    return java.util.List.of(x);
}
java.util.List<String> a = singleton("Java");
java.util.List<Number> b = singleton(42);
```

Hai phép gán minh họa target typing; hãy đặt lời gọi trong một method và khai báo `singleton` ở class phù hợp. Khi suy luận không biểu đạt rõ kiểu mong muốn, caller có thể chọn type witness như `SomeClass.<Number>singleton(42)` (nếu tên class đúng). Việc chỉ định `<Number>` không ép kiểu một object sai thành `Number`.

Điều quan trọng đối với bài này: **sự suy luận của method không phụ thuộc vào việc class chứa nó có generic hay không**. Cú pháp và tình huống dùng explicit type arguments được trình bày riêng trong chương.

## 7. Generic method có bound: giới hạn khả năng của `T`

Phương thức `<T> T identity(T value)` chỉ giả định `T` là reference type. Nếu thuật toán cần gọi API đặc thù, khai báo **upper bound**:

```java
import java.util.*;

final class NumberMath {
    static <T extends Number> double sum(Collection<T> values) {
        double total = 0;
        for (T v : values) {
            total += v.doubleValue();
        }
        return total;
    }
}

// Trong một phương thức:
double a = NumberMath.sum(List.of(1, 2, 3));      // 6.0
double b = NumberMath.sum(List.of(1.5, 2.5));     // 4.0
// NumberMath.sum(List.of("A", "B"));              // Lỗi bound.
```

`T extends Number` bảo đảm có `doubleValue()`. Dù `Number` là lớp, ở danh sách type parameter vẫn dùng từ khóa `extends`. Nếu cần nhiều bound, ví dụ `<T extends Number & Comparable<T>>`, bound lớp phải đứng trước các interface.

### Tìm giá trị lớn nhất theo thứ tự tự nhiên

```java
// Minh họa; trong một lớp Java đã import java.util.*.
static <T extends Comparable<? super T>> T maximum(Collection<? extends T> items) {
    Iterator<? extends T> it = items.iterator();
    if (!it.hasNext()) {
        throw new NoSuchElementException("Empty collection");
    }
    T best = it.next();
    while (it.hasNext()) {
        T next = it.next();
        if (next.compareTo(best) > 0) {
            best = next;
        }
    }
    return best;
}

// Integer highest = maximum(List.of(4, 9, 3)); // 9
```

`Comparable<? super T>` linh hoạt hơn `Comparable<T>` khi một kiểu con kế thừa khả năng so sánh được định nghĩa cho kiểu cha. `Collection<? extends T>` cho phép đọc phần tử là `T` hoặc kiểu con; ở đây chúng chỉ được duyệt, không thêm vào nguồn. Nếu nhu cầu thông thường chỉ là lấy max, hãy dùng API chuẩn `Collections.max`.

Đừng tạo bound chỉ để tránh viết cast khi thiết kế chưa rõ: bound phải biểu diễn **hành vi thuật toán thực sự cần**.

## 8. Generic method và wildcard: thể hiện luồng dữ liệu

Khi phương thức chỉ đọc và đưa dữ liệu sang đích, có thể kết hợp type parameter với wildcard:

```java
// Minh họa trong lớp có import java.util.List.
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}

List<Integer> numbers = List.of(1, 2);
List<Number> results = new ArrayList<>();
appendAll(numbers, results);  // results = [1, 2].
```

Đây là nguyên tắc **PECS — Producer Extends, Consumer Super**:

- `source` chỉ cung cấp phần tử `T`: `? extends T` cho phép nguồn có phần tử kiểu con của `T`;
- `destination` nhận phần tử `T`: `? super T` cho phép nơi nhận có phần tử `T` hoặc một kiểu cha thích hợp;
- tham số kiểu `<T>` nối quan hệ giữa hai bên, giúp compiler kiểm tra thao tác sao chép.

Không thể thay trực tiếp `List<Integer>` bằng `List<Number>` vì Java generics mặc định **invariant**: mặc dù `Integer extends Number`, `List<Integer>` không kế thừa `List<Number>`.

### Khi nào dùng type parameter, khi nào dùng wildcard?

So sánh hai chữ ký:

```java
static void printEach(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}

static <T> T getFirst(List<T> items) {
    if (items.isEmpty()) throw new NoSuchElementException();
    return items.get(0);
}
```

`printEach` không cần giữ quan hệ kiểu giữa đầu vào và đầu ra, nên `List<?>` đủ rõ. `getFirst` cần bảo đảm kiểu trả về khớp phần tử đầu vào, nên dùng `<T>`.

Một quy tắc thực hành: **khai báo tham số kiểu khi có quan hệ cần giữ**, ví dụ giữa hai tham số, giữa đầu vào với kết quả, hoặc khi một bound cần giới hạn API. Nếu chỉ đọc một collection không biết kiểu rồi xử lý như `Object`, wildcard thường đơn giản hơn.

## 9. Generic method trong interface, implement và override

Interface **không cần là generic** để chứa phương thức generic:

```java
interface Converter {
    <T> String stringify(T value);

    static <T> T keep(T value) {
        return value;
    }
}

final class DefaultConverter implements Converter {
    @Override
    public <T> String stringify(T value) {
        return String.valueOf(value);
    }
}
```

Chữ ký `<T> String stringify(T value)` thuộc về từng lời gọi; một implementation phải tuân thủ hợp đồng generic khi override. Với ví dụ này, vì kết quả luôn `String` và logic chỉ cần `Object`, interface `String stringify(Object value)` cũng là một thiết kế hợp lý nếu không cần giữ generic contract; phần minh họa ở đây nhấn mạnh rằng **interface bình thường vẫn được khai báo generic method**.

Một interface generic cũng có thể có phương thức dùng type parameter của interface và một generic method riêng:

```java
interface Processor<T> {
    T read();

    <R> R transform(java.util.function.Function<? super T, ? extends R> mapper);
}

final class FixedProcessor<T> implements Processor<T> {
    private final T value;

    FixedProcessor(T value) { this.value = value; }

    @Override
    public T read() { return value; }

    @Override
    public <R> R transform(java.util.function.Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}
```

Ở `FixedProcessor<String>`, `read()` trả `String`; `transform(String::length)` suy luận `R = Integer`. Việc override phải bảo toàn quan hệ tham số kiểu trong chữ ký. Thay bằng raw type hoặc cast không kiểm soát có thể gây cảnh báo unchecked và lỗi runtime.

### Có thể overload theo `T` hay không?

Không thể khai báo đồng thời trong cùng một lớp:

```java
// Sai: sau type erasure cả hai có cùng chữ ký runtime.
// static void process(List<String> values) {}
// static void process(List<Integer> values) {}
```

Generics dùng **type erasure** nên hai overload sẽ gây *name clash*. Nếu logic thực sự khác nhau, đặt tên phương thức khác hoặc thêm dấu hiệu phân biệt có ý nghĩa; nếu logic giống nhau, dùng một generic method, ví dụ `static <T> void process(List<T> values)`.

## 10. Type erasure, static và những hạn chế khi triển khai

Với một method khai báo `<T>`, Java 17 kiểm tra generic constraints ở source rồi dùng **type erasure** trong bytecode. `T` không bound thường erased thành `Object`; bounded `T` sử dụng bound thích hợp. Điều này có một số giới hạn có liên quan tới mọi loại class:

- Không được dùng `new T()`, `T.class` hoặc trực tiếp tạo `new T[n]` khi `T` chưa reifiable. Có thể truyền `Supplier<T>`, `Class<T>` hoặc array factory.
- Type arguments không tạo overload khác nhau nếu **cùng erased parameter signature**.
- Generic varargs với non-reifiable types cần chú ý heap pollution và compiler warning.
- Trong generic class, một method `static` không thể trực tiếp sử dụng type parameter **của class**, nhưng nó có thể tự khai báo `<U>`.

Những điều này giúp đọc compiler diagnostics, nhưng **không định nghĩa generic method theo lớp chứa**: một generic method vẫn là method tự khai báo type parameters, dù nằm ở class thường, class generic hay interface.

## 11. Chương trình hoàn chỉnh chạy với Java 17+

Tạo đúng tệp **`GenericMethodLesson.java`** dưới đây. Chương trình so sánh phương thức generic trong lớp thông thường, generic method trong lớp generic, phương thức instance dùng `T` của lớp, phương thức `static` độc lập, bounded generic method và wildcard sao chép.

```java
import java.util.*;
import java.util.function.Function;

public class GenericMethodLesson {
    static final class Utility {
        private Utility() {}

        static <T> List<T> singletonMutable(T value) {
            List<T> result = new ArrayList<>();
            result.add(value);
            return result;
        }

        static <T> T first(List<T> items) {
            if (items.isEmpty()) {
                throw new NoSuchElementException("Empty list");
            }
            return items.get(0);
        }

        static <T extends Comparable<? super T>> T maximum(List<? extends T> items) {
            if (items.isEmpty()) {
                throw new NoSuchElementException("Empty list");
            }
            T best = items.get(0);
            for (T item : items) {
                if (item.compareTo(best) > 0) {
                    best = item;
                }
            }
            return best;
        }

        static <T> void copy(
                List<? extends T> source,
                List<? super T> destination) {
            for (T item : source) {
                destination.add(item);
            }
        }
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        // Dùng tham số kiểu T của lớp; không khai báo <T> mới.
        T get() {
            return value;
        }

        // Generic method của riêng lớp, U độc lập với T.
        <U> Holder<U> map(Function<? super T, ? extends U> mapper) {
            return new Holder<>(mapper.apply(value));
        }

        <U> U apply(Function<? super T, ? extends U> mapper) {
            return mapper.apply(value);
        }

        // Phương thức static generic không phụ thuộc type T của Holder.
        static <V> V echo(V item) {
            return item;
        }
    }

    public static void main(String[] args) {
        List<String> words = Utility.singletonMutable("Java");
        words.add("Generics");
        System.out.println("utility: " + words);
        System.out.println("first: " + Utility.first(words));

        Holder<String> original = new Holder<>("Hello");
        Holder<Integer> length = original.map(String::length);
        System.out.println("holder: " + original.get());
        System.out.println("mapped: " + length.get());
        System.out.println("applied: " + original.apply(String::toUpperCase));
        System.out.println("static: " + Holder.echo(42));

        List<Integer> scores = List.of(3, 9, 5);
        System.out.println("max: " + Utility.maximum(scores));

        List<Number> copied = new ArrayList<>();
        Utility.copy(scores, copied);
        System.out.println("copied: " + copied);
    }
}
```

Lưu mã nguồn bằng UTF-8, biên dịch và chạy:

```bash
javac -Xlint:all GenericMethodLesson.java
java GenericMethodLesson
```

Stdout dự kiến chính xác:

```text
utility: [Java, Generics]
first: Java
holder: Hello
mapped: 5
applied: HELLO
static: 42
max: 9
copied: [3, 9, 5]
```

**Phân tích từng luồng kiểu:**

- `Utility` là lớp thông thường. `singletonMutable`, `first`, `maximum` và `copy` đều là các phương thức static generic **tự khai báo tham số kiểu**.
- `Utility.singletonMutable("Java")` suy luận `T = String`; `words.add("Generics")` hợp lệ, còn `words.add(123)` sẽ bị từ chối ở compile-time.
- `Holder<String>` quyết định `T = String` cho getter `get()`. Phương thức generic `map` có tham số kiểu **`U` mới**, được suy luận là `Integer` từ `String::length`, do đó trả `Holder<Integer>`.
- `original.apply(String::toUpperCase)` suy luận `U = String`, nhưng `original.apply(String::length)` có thể suy luận `U = Integer` ở một lời gọi khác; không có mâu thuẫn với `T = String` của lớp.
- `Holder.echo(42)` tự suy luận `V = Integer` mà không cần đối tượng `Holder<T>`.
- `maximum` có bound `Comparable<? super T>` để gọi `compareTo` và xác định phần tử lớn nhất.
- `copy` nhận nguồn `List<Integer>` rồi ghi vào đích `List<Number>`. Hai wildcard giữ ràng buộc an toàn theo hướng đọc/ghi.

Không có cast thủ công trong chương trình. Mọi ràng buộc được mô tả bằng kiểu của lớp hoặc phương thức; đó là lợi ích lớn nhất của việc thiết kế API generic rõ ràng.

## 12. Trường hợp lỗi và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `static T first(T value)` trong lớp thông thường báo không tìm thấy `T` | Phương thức chưa khai báo type parameter | Viết `static <T> T first(T value)`. |
| `static T get()` trong `class Box<T>` không biên dịch | Tham số kiểu của lớp không dùng được trong static context | Cho phương thức khai báo type parameter riêng hoặc dùng kiểu cụ thể. |
| `<T> T echo(T value)` bên trong `Box<T>` gây hiểu nhầm | `T` của phương thức che khuất `T` của lớp | Đổi tên tham số kiểu của phương thức thành `<U>`. |
| Caller phải cast sau khi gọi hàm trả `Object` | Chữ ký không giữ quan hệ kiểu đầu vào–đầu ra | Dùng `<T> T first(List<T>)` nếu mục đích yêu cầu trả đúng kiểu phần tử. |
| Lời gọi `List<Number> xs = List<Integer>` thất bại | Generics invariant | Dùng wildcard `? extends T`/`? super T` theo hướng xử lý. |
| Generic method dùng `t.compareTo(x)` nhưng compiler báo không tồn tại | `T` không có bound bảo đảm `Comparable` | Khai báo `<T extends Comparable<? super T>>` phù hợp. |
| Phương thức tạo `new T()` bị lỗi | Type erasure không cho biết constructor của `T` | Nhận `Supplier<? extends T>` hoặc một factory khác. |
| Overload `method(List<String>)` và `method(List<Integer>)` bị name clash | Cùng chữ ký sau erasure | Đổi tên, thiết kế overload khác biệt thực sự hoặc hợp nhất logic. |
| Generic method trả `null`, caller gặp `NullPointerException` | Type parameter không đảm bảo non-null | Định nghĩa hợp đồng null rõ ràng; dùng validation hoặc `Optional<T>` khi có ý nghĩa. |
| Compiler cảnh báo unchecked khi dùng `List` raw | Mất tham số kiểu tại một điểm của luồng dữ liệu | Dùng `List<T>`, `List<?>` hoặc kiểm tra/chuyển đổi dữ liệu legacy. |
| Generic varargs phát cảnh báo | Mảng và generic có quy tắc reification khác nhau | Ưu tiên collection hoặc thiết kế varargs an toàn, đánh giá `@SafeVarargs` đúng điều kiện. |
| Phương thức `<T> void print(T value)` gây khó hiểu nhưng không tạo quan hệ kiểu | Tham số kiểu có thể thừa | Dùng `Object` nếu chỉ xử lý object chung, giữ generic khi thực sự có ràng buộc/quan hệ. |

### Quy trình đọc một chữ ký generic

Gặp phương thức sau:

```java
static <T extends Number, R> List<R> mapNumbers(
        List<? extends T> values,
        Function<? super T, ? extends R> converter);
```

Hãy đọc từ trái sang phải:

1. `<T extends Number, R>` khai báo **hai tham số kiểu thuộc phương thức**; `T` là một kiểu con của `Number`.
2. `List<R>` là kiểu trả về; mỗi phần tử kết quả mang kiểu `R`.
3. `List<? extends T>` là nguồn chỉ cần đọc như `T`.
4. `Function<? super T, ? extends R>` nhận một giá trị `T` (hoặc theo kiểu cha thích hợp) và trả `R` (hoặc kiểu con).
5. Compiler nối các điều kiện ở một lần gọi cụ thể, ví dụ nguồn `List<Integer>` cùng bộ chuyển `Number::doubleValue` có thể tạo kết quả được yêu cầu theo `Double`.

Không cần ghi nhớ mọi kiểu thư viện cùng lúc. Hãy tìm nơi **khai báo** type parameter, nơi nó được **sử dụng**, và mối quan hệ nào compiler đang bảo vệ.

## 13. Bài tập củng cố

**Bài 1 — Lớp thường, phương thức generic.** Trong một lớp `ArrayTools` không generic, viết `static <T> T last(List<T> items)` có kiểm tra danh sách rỗng. Gọi với `List<String>` và `List<Long>`. Giải thích vì sao một lớp thông thường không ngăn cản phương thức khai báo `<T>`.

**Bài 2 — Kiểu lớp và kiểu phương thức.** Viết `Result<T>` có `T value`, `T get()` và `<R> Result<R> map(Function<? super T, ? extends R>)`. Với `Result<String>` chứa `"123"`, biến đổi bằng `Integer::parseInt` rồi kiểm tra kết quả có kiểu `Result<Integer>`. Nêu rõ `T` và `R` thuộc về đâu.

**Bài 3 — Phương thức static generic.** Tạo `static <K,V> Map<K,V> singleMap(K key, V value)`. Gọi bằng khóa `String` và giá trị `Integer`. Giải thích vì sao không cần chuyển `Map<Object,Object>` rồi cast.

**Bài 4 — Bounded type.** Viết `static <T extends Comparable<? super T>> T min(List<? extends T> items)` trả phần tử nhỏ nhất của danh sách không rỗng. Dùng `compareTo`, thử với `List<Integer>` và `List<String>`.

**Bài 5 — PECS.** Viết `static <T> void moveAll(Collection<? extends T> from, Collection<? super T> into)`. Dùng `Collection<Integer>` làm nguồn và `Collection<Number>` làm đích. Hỏi vì sao `Collection<Number>` không nhận trực tiếp một `Collection<Integer>` ở mọi API.

**Bài 6 — Phân tích lỗi.** Dự đoán điều gì xảy ra với đoạn này:

```java
class Box<T> {
    T value;
    Box(T value) { this.value = value; }

    <T> T echo(T item) { return item; }
    // static T missing() { return null; }
}

Box<String> b = new Box<>("Java");
Integer i = b.echo(10);
```

Định hướng: `b.echo(10)` hợp lệ vì `T` của phương thức là type parameter mới; `missing` (nếu bỏ comment) sẽ không biên dịch vì sử dụng `T` của lớp trong `static` context.

Kết thúc phần học, hãy tự giải thích được ba trường hợp: **phương thức dùng `T` đã được lớp khai báo**, **phương thức tự khai báo `<U>` độc lập**, và **phương thức generic `static` trong lớp thường hoặc lớp generic**. Đây là chìa khóa để viết các hàm tái sử dụng mà compiler vẫn kiểm tra được quan hệ kiểu.
