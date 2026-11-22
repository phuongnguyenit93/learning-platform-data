# Record generic và các thành phần được tham số hóa trong Java

`record` trong Java là một cách khai báo lớp chuyên dùng để mang dữ liệu. **Generic record** kết hợp cấu trúc record với **type parameter**, giúp cùng một khuôn dữ liệu áp dụng cho nhiều loại giá trị mà compiler vẫn kiểm tra quan hệ kiểu. Ví dụ, `Pair<String, Integer>` giữ một khóa kiểu `String` và một giá trị kiểu `Integer`, còn `Pair<Long, String>` dùng chính khai báo record ấy với hai type arguments khác.

Bài học này tập trung vào **cách khai báo record generic, ý nghĩa của các record components được tham số hóa, các thành viên compiler tạo ra, quan hệ giữa type parameter và constructor/accessor, việc implement generic interface, kiểm tra dữ liệu và các giới hạn cần biết khi chạy**. Các ví dụ chạy được bằng Java 17 trở lên.

## 1. Record là gì và vì sao kết hợp với Generics?

Một record khai báo *state description* ở phần header, tức một dãy **record components** có tên và kiểu:

```java
record User(String name, int age) {
}
```

Đây là đoạn khai báo minh họa, chưa có `main`. Từ danh sách components, Java cung cấp những thành viên cần thiết để dùng record như một dữ liệu có cấu trúc: trường thành phần `private final`, accessor có tên đúng bằng component (`name()`, `age()`), canonical constructor, `equals`, `hashCode` và `toString`, trừ khi một số thành viên đó được khai báo tường minh theo quy tắc của record.

Nếu thay mỗi component bằng `Object` để tái sử dụng cho nhiều dữ liệu, caller phải ép kiểu và compiler không còn biết quan hệ giữa phần tử đầu vào/đầu ra. Generic record giải quyết việc đó:

```java
record Box<T>(T value) {
}
```

Ở đây:

- `Box<T>` là **khai báo generic record**; `T` là type parameter của record.
- `T value` là **record component được tham số hóa**: component `value` có kiểu phụ thuộc `T`.
- `Box<String>` và `Box<Integer>` là hai cách **sử dụng** record, cung cấp type arguments cho `T`.
- `value()` của `Box<String>` có kiểu biểu thức `String`; `value()` của `Box<Integer>` có kiểu biểu thức `Integer` ở điểm gọi.
- Hai instantiations không tạo hai lớp JVM khác nhau; Java dùng type erasure cho generics.

Một record thông thường cũng không tự làm dữ liệu bất biến sâu (*deeply immutable*): trường component là final nhưng đối tượng được tham chiếu bởi component có thể vẫn mutable. Đây là điểm rất quan trọng với component kiểu `List<T>`, `Map<K,V>` hoặc mảng.

## 2. Cú pháp cơ bản của generic record

Dạng tổng quát:

```java
record RecordName<T1, T2>(T1 first, T2 second) {
    // Constructor, validation, method hoặc static member nếu cần.
}
```

Đoạn trên là mẫu cú pháp, không phải class Java chạy độc lập. `T1` và `T2` là type parameters khai báo ngay sau tên record. Trong danh sách components, chúng được dùng như các kiểu thông thường.

### Ví dụ hoàn chỉnh: Pair với hai biến kiểu

Tạo tệp `GenericPairDemo.java`:

```java
public class GenericPairDemo {
    record Pair<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("Lan", 9);
        Pair<Long, String> status = new Pair<>(100L, "OK");

        String student = score.key();
        Integer mark = score.value();

        System.out.println(student + ": " + mark);
        System.out.println(status.key() + " -> " + status.value());
        System.out.println(score);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac GenericPairDemo.java
java GenericPairDemo
```

`stdout`:

```text
Lan: 9
100 -> OK
Pair[key=Lan, value=9]
```

Giải thích:

1. `Pair<K,V>` khai báo hai type parameters độc lập: `K` là kiểu của component `key`, `V` là kiểu của component `value`.
2. `Pair<String,Integer>` ràng buộc `K=String`, `V=Integer` cho biến `score`. Compiler cho phép gán `score.key()` cho `String`, `score.value()` cho `Integer`.
3. `Pair<Long,String>` là cùng một record được sử dụng với loại dữ liệu khác.
4. Cú pháp diamond `new Pair<>(...)` giúp compiler suy luận type arguments từ ngữ cảnh và đối số constructor.
5. Accessor của record là `key()` và `value()`, **không tự tạo** `getKey()` hoặc `getValue()`.
6. `toString()` do record sinh hiển thị tên record và từng component theo cấu trúc được khai báo; ở ví dụ này là `Pair[key=Lan, value=9]`.

Nếu thay `new Pair<>("Lan", 9)` bằng `new Pair<>(9, "Lan")` mà vẫn gán vào `Pair<String,Integer>` thì compiler từ chối vì hai type arguments không tương thích hợp đồng tại điểm gán.

## 3. Lần theo type parameter ở từng record component

Một generic record có thể dùng type parameter ở một hoặc nhiều components, và có thể kết hợp với component kiểu cụ thể:

```java
record Event<ID, P>(
        ID id,
        String topic,
        P payload,
        java.time.Instant createdAt) {
}
```

Đây là phần khai báo minh họa. Lập bảng đọc chữ ký:

| Thành phần | Kiểu khai báo | Phụ thuộc vào |
| --- | --- | --- |
| `id` | `ID` | Type argument thứ nhất của `Event<ID,P>` |
| `topic` | `String` | Kiểu cố định, không phụ thuộc type argument |
| `payload` | `P` | Type argument thứ hai của `Event<ID,P>` |
| `createdAt` | `Instant` | Kiểu cố định |
| `id()` | `ID` | Cùng `ID` với component `id` |
| `payload()` | `P` | Cùng `P` với component `payload` |

Với `Event<Long, String>`, compiler xem `id()` trả `Long` và `payload()` trả `String`. Với `Event<String, byte[]>`, `id()` trả `String` còn `payload()` trả `byte[]`. Dù type argument của `Event` khác nhau, `topic()` luôn trả `String` và `createdAt()` luôn trả `Instant`.

**Cách đọc:** mỗi lần gặp `T` hoặc tên biến kiểu khác trong header, hãy tìm khai báo `<T>` ngay sau tên record. Những vị trí dùng cùng một `T` trong record cùng chịu một lựa chọn kiểu. Một component không sử dụng biến kiểu vẫn có kiểu đã khai báo như bình thường.

### Thành phần generic lồng nhau

Có thể khai báo các record components như:

```java
record Batch<T>(
        String label,
        java.util.List<T> items,
        java.util.Map<String, T> index) {
}
```

`T` được sử dụng ở hai generic type arguments: `List<T>` và giá trị `V` của `Map<String,T>`. Với `Batch<Integer>`, phương thức `items()` có kiểu `List<Integer>` và `index()` có kiểu `Map<String,Integer>`. Không phải các generic trong component khai báo lại một `T` mới: chúng đang dùng `T` đã có ở header record.

Một component có thể là `List<List<T>>`, `Map<String, List<T>>` hay `Optional<T>`; đọc từ generic bên ngoài vào bên trong.

## 4. Các thành viên Java cung cấp từ generic record components

Xét:

```java
record Box<T>(T value) {
}
```

Ở mức mô hình đọc API, bạn có thể hình dung các thành viên tương ứng:

```java
// Đây chỉ là mô hình giải thích, không phải cách
// Java chuyển record thành source code.
final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T value() {
        return value;
    }

    // equals(Object), hashCode(), toString() được cung cấp.
}
```

Mô hình trên **không thay thế toàn bộ ngữ nghĩa của record**, nhưng giúp thấy rõ generic type parameter đi từ component tới constructor và accessor.

### 4.1. Component field là final

Mỗi record component tương ứng với một trường instance `private final`. Sau khi canonical constructor hoàn tất, không được gán lại trường đó:

```java
record Count<T>(T value) {
    // void replace(T x) {
    //     this.value = x; // Lỗi: trường component là final.
    // }
}
```

Generic typing và final field là hai tính chất độc lập. `T` kiểm tra **loại giá trị**, còn `final` ngăn **đổi tham chiếu trong trường**. Nếu `T` là một kiểu đối tượng mutable, caller vẫn có thể thay đổi trạng thái bên trong đối tượng mà record đang giữ.

### 4.2. Accessor có kiểu phụ thuộc type argument

Với `record Box<T>(T value)`, accessor `value()` có kiểu trả về `T`. Do đó:

```java
Box<String> a = new Box<>("Java");
String text = a.value();

// Integer wrong = a.value(); // Lỗi biên dịch.
```

Đây là các dòng sử dụng minh họa; để chạy, đặt trong class/method có khai báo `Box<T>`. Không cần viết cast `(String) a.value()` ở code sử dụng có kiểu đúng.

### 4.3. Canonical constructor có danh sách tham số theo components

Record `Pair<K,V>(K key,V value)` có canonical constructor tương ứng hai component, theo đúng thứ tự. Có thể đọc quan hệ constructor như `Pair(K key, V value)`. Đây là quan hệ type ở nguồn, không phải hai constructor runtime khác nhau cho `String` và `Integer`.

Một record có thể khai báo constructor bổ sung, nhưng constructor không chuẩn (*non-canonical*) phải ủy quyền tới constructor khác của cùng record thông qua `this(...)` để tất cả components được khởi tạo đúng cách.

### 4.4. equals, hashCode và toString

Record cung cấp so sánh dựa trên kiểu record và giá trị components, cùng hàm băm và biểu diễn văn bản tương ứng. Với `record Pair<K,V>(K key,V value)`, `Pair<String,Integer>` và `Pair<String,Number>` vẫn là các tham số hóa khác nhau của **cùng lớp runtime Pair**. Khi components thực chứa các giá trị bằng nhau, `equals` có thể trả true dù khai báo generic ở hai biến khác nhau.

Ngược lại, nếu component là một mảng, phép so sánh component reference của mảng không tự biến thành so sánh từng phần tử mảng. Nếu cần value equality theo nội dung mảng, phải thiết kế xử lý phù hợp (chẳng hạn dùng một cấu trúc immutable với `equals` theo nội dung hoặc tự hiện thực các method record một cách nhất quán).

## 5. Canonical constructor và compact constructor trong generic record

Record có thể kiểm tra điều kiện của components trước khi gán vào trường. Cú pháp **compact constructor** đặc biệt hữu ích vì không cần lặp lại danh sách tham số.

### Ví dụ hoàn chỉnh: bản sao List bất biến

Tạo `GenericBatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericBatchDemo {
    record Batch<T>(String name, List<T> items) {
        Batch {
            Objects.requireNonNull(name, "name");
            items = List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>(
                List.of("Java", "Kotlin"));

        Batch<String> batch = new Batch<>("languages", mutable);
        mutable.add("Scala");

        System.out.println(batch.name());
        System.out.println(batch.items());
        System.out.println(mutable);
    }
}
```

Chạy:

```bash
javac GenericBatchDemo.java
java GenericBatchDemo
```

`stdout`:

```text
languages
[Java, Kotlin]
[Java, Kotlin, Scala]
```

Giải thích:

- `Batch<T>` khai báo một component kiểu cụ thể `String name` và một component generic lồng `List<T> items`.
- `Batch { ... }` là compact canonical constructor; nó được đặt trong thân record, **không** có danh sách tham số tường minh.
- Trong compact constructor, tên `name` và `items` tham chiếu tới các **tham số ngầm** tương ứng với record components. Gán `items = List.copyOf(items)` thay đổi giá trị tham số sẽ được lưu vào trường `items` sau phần thân constructor.
- `List.copyOf` tạo danh sách không sửa được và, khi cần, một bản sao chứa các phần tử đang có. Do đó sửa `mutable` sau khi tạo `Batch` không thay đổi số phần tử trong `batch.items()`.
- `List.copyOf` không chấp nhận phần tử null; nếu input null hoặc chứa null, thao tác có thể ném `NullPointerException`. Đây là hành vi của API, **không** phải do `T` tự ngăn null.
- Bản sao trên là **shallow copy**: nếu `T` là một đối tượng mutable (ví dụ `StringBuilder`), việc thay đổi nội dung object đó vẫn có thể quan sát qua danh sách trong record.

Trong compact constructor, **không** gán trực tiếp `this.items = ...`. Việc khởi tạo component fields được thực hiện sau khi compact constructor body hoàn tất, dùng các tham số tương ứng.

### Canonical constructor tường minh

Nếu muốn tự khai báo canonical constructor với đầy đủ tham số, phải khởi tạo các component fields chính xác:

```java
import java.util.Objects;

record NonNullValue<T>(T value) {
    NonNullValue(T value) {
        this.value = Objects.requireNonNull(value);
    }
}
```

Đây là đoạn khai báo Java hợp lệ; không có `main`. Canonical constructor chứa đúng danh sách component parameters. Không được vừa khai báo compact canonical constructor vừa khai báo một canonical constructor khác trong cùng record.

### Kiểm tra ràng buộc trong constructor

Một generic record `Range<T>` không tự biết mọi `T` có thể so sánh. Nếu constructor cần so sánh endpoints, khai báo bound ngay tại type parameter:

```java
record Range<T extends Comparable<? super T>>(T start, T end) {
    Range {
        java.util.Objects.requireNonNull(start);
        java.util.Objects.requireNonNull(end);
        if (start.compareTo(end) > 0) {
            throw new IllegalArgumentException("start > end");
        }
    }
}
```

Bound `Comparable<? super T>` cho compiler biết `T` có khả năng so sánh với một `T` khác, trong phạm vi quan hệ tương thích. Nếu `T` không có bound thích hợp, lời gọi `start.compareTo(end)` không được compiler bảo đảm.

## 6. Bounded type parameter trên generic record

Có thể khai báo các ràng buộc tại chính record header:

```java
record Measurement<N extends Number>(String unit, N value) {
    double asDouble() {
        return value.doubleValue();
    }
}
```

Ở đây:

1. `N` được khai báo tại `Measurement<N extends Number>`.
2. `Number` là cận trên: `N` phải phù hợp quan hệ subtype với `Number`.
3. Component `value` dùng `N`; accessor `value()` trả `N` tại compile time.
4. Instance method `asDouble()` trả primitive `double`, không phải `N`. Compiler cho phép gọi `doubleValue()` vì bound đã cam kết điều đó.

Ví dụ chạy được trong `BoundedRecordDemo.java`:

```java
public class BoundedRecordDemo {
    record Measurement<N extends Number>(String unit, N value) {
        double asDouble() {
            return value.doubleValue();
        }
    }

    record Range<T extends Comparable<? super T>>(T start, T end) {
        Range {
            if (start.compareTo(end) > 0) {
                throw new IllegalArgumentException("start > end");
            }
        }
    }

    public static void main(String[] args) {
        Measurement<Integer> count = new Measurement<>("items", 12);
        Measurement<Double> weight = new Measurement<>("kg", 2.5);
        Range<Integer> interval = new Range<>(1, 10);

        System.out.println(count.asDouble());
        System.out.println(weight.asDouble());
        System.out.println(interval.start() + ".." + interval.end());
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
12.0
2.5
1..10
```

`Measurement<String>` không hợp lệ vì `String` không kế thừa `Number`. Trường hợp `Range<Integer>` hợp lệ vì `Integer` có quan hệ `Comparable<Integer>` tương ứng.

### Multiple bounds

Bạn có thể dùng nhiều bound cho một type parameter:

```java
record Ranked<T extends Number & Comparable<T>>(T value) {
}
```

Nếu có cận class, nó phải đứng trước các cận interface; các cận interface nối bằng `&`. `extends` dùng cho cả class và interface bound trong khai báo type parameter. Khi chỉ mới cần giữ dữ liệu mà không gọi hành vi đặc thù, **không cần** áp đặt bound cho mọi `T`.

## 7. Generic record implements generic interface

Record không được `extends` một class tùy ý; nó trực tiếp kế thừa `java.lang.Record` và là final. Tuy vậy, record **có thể implements interface**, kể cả generic interface, và nhờ đó tham gia hợp đồng trừu tượng.

Tạo `GenericRecordInterfaceDemo.java`:

```java
public class GenericRecordInterfaceDemo {
    interface Identified<ID> {
        ID id();
    }

    record Entity<ID, T>(ID id, T payload)
            implements Identified<ID> {
    }

    static <ID> void printId(Identified<ID> value) {
        System.out.println(value.id());
    }

    public static void main(String[] args) {
        Entity<Long, String> message =
                new Entity<>(42L, "queued");

        printId(message);
        System.out.println(message.payload());
    }
}
```

Chạy:

```bash
javac GenericRecordInterfaceDemo.java
java GenericRecordInterfaceDemo
```

`stdout`:

```text
42
queued
```

Giải thích:

- `Identified<ID>` khai báo hợp đồng `ID id()`.
- `Entity<ID,T>` khai báo hai type parameters riêng của record.
- `implements Identified<ID>` **truyền** type parameter `ID` của record làm type argument của interface.
- Record component `ID id` tạo accessor `id()` tương ứng và đáp ứng method trong interface; không phải viết thêm `getId()`.
- Method `printId` khai báo type parameter `ID` riêng; khi nhận `Entity<Long,String>`, compiler có thể suy luận kiểu tương ứng của ID.
- Không phải interface nào cũng được record đáp ứng tự động chỉ bằng component. Tên, kiểu trả về và hợp đồng method phải thật sự tương thích; nếu interface yêu cầu `getId()`, component `id` không sinh ra method đó.

Một record cũng có thể implement nhiều interfaces. Vì bản thân record là final, không thể viết `class Derived extends Entity<...>` để kế thừa nó.

## 8. Generic instance method trong record

Ngoài dùng type parameter của record, một instance method còn có thể khai báo **type parameter mới** ở phạm vi phương thức. Điểm này cho phép record mang `T` nhưng một phép biến đổi tạo ra `R`.

Tạo `GenericRecordMethodDemo.java`:

```java
import java.util.function.Function;

public class GenericRecordMethodDemo {
    record Box<T>(T value) {
        <R> Box<R> map(Function<? super T, ? extends R> converter) {
            return new Box<>(converter.apply(value));
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");
        Box<Integer> size = text.map(String::length);
        Box<String> description = size.map(n -> "length=" + n);

        System.out.println(size.value());
        System.out.println(description.value());
    }
}
```

Chạy:

```bash
javac GenericRecordMethodDemo.java
java GenericRecordMethodDemo
```

`stdout`:

```text
4
length=4
```

Đọc từng ràng buộc:

| Ký hiệu | Được khai báo ở | Ý nghĩa tại lời gọi `text.map(String::length)` |
| --- | --- | --- |
| `T` | `record Box<T>` | Kiểu của giá trị đang giữ: `String` |
| `R` | `<R> Box<R> map(...)` | Kiểu kết quả phép biến đổi: `Integer` |
| `? super T` | Wildcard dùng trong `Function` | Hàm nhận được giá trị kiểu `T` |
| `? extends R` | Wildcard dùng trong `Function` | Hàm cho giá trị tương thích `R` |

`Box<String>` và `Box<Integer>` là cùng khai báo record, nhưng lời gọi `map` tạo một đối tượng mới mang một type argument khác ở compile time. Điều này không làm thay đổi đối tượng `text`.

### Static method và type parameter của record

Method static không thể trực tiếp dùng `T` của `record Box<T>` làm kiểu độc lập vì `T` gắn với instantiation của record, còn method static thuộc lớp. Nếu muốn một static factory generic, khai báo type parameter của **method**:

```java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

Đoạn trên hợp lệ nhưng không có `main`. Ví dụ `Box.of("hello")` có thể suy luận `U=String`. `U` tại method là một biến kiểu khác với `T` ở record; type argument của `Box<U>` được xác định từ `U` khi tạo kết quả.

## 9. Type inference khi tạo generic record

Giống generic class khác, generic record có thể dùng diamond `<>` để Java suy luận type arguments. Có hai nguồn suy luận quan trọng: **kiểu mục tiêu** và **đối số constructor**.

### Chọn kiểu theo target

```java
record Pair<K, V>(K key, V value) {}

Pair<String, Integer> p = new Pair<>("A", 1);
```

Compiler dùng kiểu mục tiêu `Pair<String,Integer>` và dữ liệu truyền vào để áp dụng `K=String`, `V=Integer`. Nếu thay tham số thành kiểu không tương thích, `javac` báo lỗi.

### Chọn kiểu theo initializer

```java
var p = new Pair<>("A", 1);
```

Với Java 17, `var` suy luận kiểu biến cục bộ từ initializer; ở đây có thể suy ra `Pair<String,Integer>`. `var` không làm kiểu biến trở thành dynamic và không khai báo thêm type parameter. Một khi suy luận xong, compiler vẫn kiểm tra các accessor của `p` theo kiểu tĩnh đã xác định.

### Explicit type arguments và raw type

```java
Pair<String, Integer> a = new Pair<String, Integer>("A", 1);
Pair<String, Integer> b = new Pair<>("A", 1);
```

Hai cách này khai báo hợp đồng kiểu như nhau cho `a` và `b`. Cách viết diamond ngắn hơn.

Tránh kiểu raw:

```java
Pair raw = new Pair("A", 1);
```

Raw type làm suy giảm kiểm tra kiểu của generics và có thể phát cảnh báo `rawtypes`/`unchecked`. Đừng xem record là ngoại lệ: generic record vẫn chịu quy tắc raw types như generic class thông thường.

### Không hỗ trợ primitive type argument

`Pair<int, double>` sai cú pháp về kiểu generic. Cần dùng wrapper `Pair<Integer, Double>`; boxing/unboxing giúp chuyển các primitive values tại nơi phù hợp.

## 10. Generic record chứa collection và kiểu lồng nhau

Generic record không chỉ có component trực tiếp `T`; nó có thể giữ generic collection với các type arguments được liên kết.

Tạo `NestedGenericRecordDemo.java`:

```java
import java.util.List;
import java.util.Map;

public class NestedGenericRecordDemo {
    record Catalog<K, V>(
            Map<K, List<V>> entries,
            String label) {
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> scores = Map.of(
                "Lan", List.of(8, 9),
                "Mai", List.of(7));

        Catalog<String, Integer> catalog =
                new Catalog<>(scores, "scores");

        List<Integer> lan = catalog.entries().get("Lan");
        System.out.println(catalog.label());
        System.out.println(lan);
        System.out.println(lan.get(0));
    }
}
```

Chạy:

```bash
javac NestedGenericRecordDemo.java
java NestedGenericRecordDemo
```

`stdout`:

```text
scores
[8, 9]
8
```

Đọc kiểu theo từng tầng:

1. `Catalog<K,V>` khai báo `K` và `V`.
2. Component `entries` có kiểu `Map<K,List<V>>`.
3. Với `Catalog<String,Integer>`, accessor `entries()` có kiểu `Map<String,List<Integer>>`.
4. Phương thức `Map.get(Object)` trả `V` của map, lúc này là `List<Integer>`; lưu ý `Map.get` nhận `Object` theo API Java, dù key của map được khai báo `String`.
5. `List<Integer>.get(0)` có kiểu biểu thức `Integer`.

Tương tự, component `Optional<T>` giúp biểu diễn việc có/không có giá trị thông qua API `Optional`, nhưng generic type tự nó không cấm component null; muốn cấm null cần kiểm tra riêng hoặc chọn invariant.

## 11. Tính bất biến của generic type arguments

Dù `Integer extends Number`, không thể gán trực tiếp `Pair<String,Integer>` sang `Pair<String,Number>`:

```java
record Pair<K, V>(K key, V value) {}

Pair<String, Integer> integerPair = new Pair<>("A", 7);
// Pair<String, Number> numberPair = integerPair; // Sai.
```

Generic type arguments của Java về cơ bản **invariant**. Điều này vẫn đúng với record dù các component fields là final và record không có setter; compiler áp dụng quy tắc kiểu generic của `Pair<K,V>`, không tự chuyển thành covariance chỉ vì record immutable ở cấp trường.

### Dùng wildcard khi cần đọc linh hoạt

```java
Pair<String, ? extends Number> numberView = integerPair;
Number number = numberView.value();
```

Đây là các dòng minh họa đặt trong phạm vi có `Pair<K,V>` và `integerPair`. Wildcard `? extends Number` cho phép nhận record có value là một subtype của `Number`. Khi đọc `numberView.value()`, compiler cho phép coi kết quả là `Number`.

Không thể tùy ý thay đổi kiểu component của một record đã tạo vì không có setter; khi cần một record khác, hãy tạo đối tượng mới với kiểu đích phù hợp. Nếu muốn chấp nhận nhiều kiểu khi **thiết kế method**, wildcard trên tham số có thể hữu ích, ví dụ `Pair<String, ? extends Number>` hoặc `Pair<?, ?>`.

### Raw record không phải “mọi Pair hợp lệ”

`Pair` raw bỏ mất quan hệ kiểu compile time. `Pair<?,?>` giữ thông tin rằng record có hai type parameters không biết cụ thể và giúp tránh nhiều thao tác unchecked. Nếu chỉ cần in record hoặc đọc components dưới dạng `Object`, wildcard phù hợp hơn raw type.

## 12. equals và type arguments: phải xét dữ liệu runtime

Generic typing kiểm tra ở compile time, nhưng hai cách tham số hóa cùng một record không làm Java tạo lớp runtime riêng. Ví dụ:

Tạo `RecordEqualityDemo.java`:

```java
public class RecordEqualityDemo {
    record Pair<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Pair<String, Integer> exact = new Pair<>("A", 1);
        Pair<String, Number> wide = new Pair<>("A", 1);

        System.out.println(exact.getClass().equals(wide.getClass()));
        System.out.println(exact.equals(wide));
        System.out.println(exact.hashCode() == wide.hashCode());
    }
}
```

Chạy `javac RecordEqualityDemo.java` và `java RecordEqualityDemo`:

```text
true
true
true
```

Hai đối tượng cùng runtime class `Pair`, với components chứa chuỗi `"A"` và số nguyên boxed `Integer(1)` bằng nhau. Việc một biến có type argument `V=Integer`, biến khác có `V=Number` không buộc `equals` trả false.

**Không suy rộng** điều này thành “hai loại generic record khác tên nhưng components giống nhau sẽ bằng nhau”: record equality chỉ so với đối tượng của cùng record class. Cũng không suy luận `Integer(1)` và `Long(1L)` bằng nhau theo `equals`; chúng là wrapper khác kiểu với `equals` không tương đương.

### Những trường hợp không bất biến sâu

- Component là `ArrayList<T>`: không thể gán lại component field, nhưng có thể `add` qua tham chiếu nếu list mutable.
- Component là `Map<K,V>`: key/value có thể được thay đổi qua mutable map, trừ khi đã sao chép/bọc với chính sách thích hợp.
- Component là `T[]`: mảng có thể bị thay đổi phần tử, nên muốn bảo vệ cần clone khi nhận và khi trả.
- Component là bản thân một object `T` mutable: việc giữ final reference không đóng băng trạng thái của object đó.

Khi record là DTO chia sẻ giữa nhiều phần của chương trình, hãy công bố rõ tính mutable của component và dùng **defensive copy** ở ranh giới phù hợp.

## 13. Defensive copy và giới hạn “immutable record”

Đây là lỗi phổ biến nhất khi record component là collection generic:

```java
record BadSnapshot<T>(java.util.List<T> items) {}
```

Tạo `BadSnapshot<String> snapshot = new BadSnapshot<>(mutableList)` không tự sao chép danh sách. `snapshot.items()` trả đúng tham chiếu đã lưu. Nếu caller còn giữ danh sách và thay đổi nó, snapshot sẽ quan sát thấy thay đổi đó.

### Thiết kế tốt hơn cho component `List<T>`

```java
record Snapshot<T>(java.util.List<T> items) {
    Snapshot {
        items = java.util.List.copyOf(items);
    }
}
```

`List.copyOf` tạo danh sách không sửa được; đồng thời đầu vào không được null và không được chứa phần tử null. Nếu đầu vào đã là danh sách immutable phù hợp, triển khai có thể tái sử dụng thay vì luôn cấp phát bản sao; hợp đồng đáng tin là snapshot kết quả không thay đổi khi sửa source list thông qua alias.

Tuy nhiên, nếu từng `T` là đối tượng mutable, `List.copyOf` chỉ bảo vệ cấu trúc danh sách, **không clone từng phần tử**. Cần clone sâu hoặc biểu diễn immutable của từng phần tử nếu yêu cầu bài toán thực sự là deep immutability.

### Với mảng, cần phòng vệ ở cả hai đầu

```java
record Bytes(byte[] data) {
    Bytes {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

Đoạn này là khai báo hợp lệ nhưng không có `main`. Constructor clone dữ liệu lúc nhận; accessor clone lần nữa để caller không sửa trực tiếp mảng nội bộ. Trường hợp array component còn đặt ra vấn đề `equals`/`hashCode` của record: mặc định chúng không tự so sánh nội dung mảng; nếu muốn dùng record làm giá trị có equality theo byte, cần thiết kế overrides nhất quán hoặc chọn biểu diễn khác.

Bài học: **type parameter T**, **component final** và **immutability của object graph** là ba khái niệm khác nhau.

## 14. Type erasure và reflection đối với generic record

Record là class ở JVM; generic record chịu **type erasure** giống các generic class khác. `Box<String>` và `Box<Integer>` không có hai class runtime chuyên biệt. Tuy nhiên metadata generic của **khai báo record và components** có thể được reflection đọc.

Tạo `RecordReflectionDemo.java`:

```java
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordReflectionDemo {
    record Container<T>(List<T> values) {
    }

    public static void main(String[] args) {
        Container<String> a = new Container<>(List.of("A"));
        Container<Integer> b = new Container<>(List.of(1));

        System.out.println(a.getClass().equals(b.getClass()));
        System.out.println(Container.class.isRecord());

        RecordComponent component =
                Container.class.getRecordComponents()[0];

        System.out.println(component.getName());
        System.out.println(component.getType().getTypeName());
        System.out.println(component.getGenericType().getTypeName());
    }
}
```

Chạy:

```bash
javac RecordReflectionDemo.java
java RecordReflectionDemo
```

`stdout`:

```text
true
true
values
java.util.List
java.util.List<T>
```

Giải thích:

- `getClass()` cho thấy hai objects cùng class `Container`.
- `Class.isRecord()` cho phép nhận biết class này là record.
- `Class.getRecordComponents()` trả các `RecordComponent` theo thứ tự components khai báo. Ví dụ chỉ có `values` nên lấy index `0`.
- `getName()` trả tên component.
- `getType()` trả class runtime của kiểu component đã xóa, ở đây là `java.util.List`.
- `getGenericType()` mô tả generic type đã khai báo `List<T>`, vì chữ ký generic của khai báo có thể được ghi trong class file.

Reflection đọc `java.util.List<T>` không có nghĩa instance `a` mang `T=String` hay instance `b` mang `T=Integer` để JVM tự cưỡng chế kiểu phần tử. Type erasure vẫn áp dụng tại runtime; metadata khai báo và type argument của từng tham chiếu là hai nguồn thông tin khác nhau.

Đừng dùng `getClass()` để phân biệt `Container<String>` và `Container<Integer>`. Nếu một cơ chế serialization cần hiểu `List<String>` hay kiểu lồng sâu, thường phải truyền metadata kiểu đích phù hợp bằng `Type`, type token hoặc API của thư viện đó.

## 15. Generic record so với generic class

Cả hai dùng type parameters và cùng tuân theo type erasure. Khác biệt quan trọng đến từ **cơ chế record**, không đến từ Generics:

| Khía cạnh | Generic record | Generic class thông thường |
| --- | --- | --- |
| Khai báo | `record Pair<K,V>(K key,V value)` | `class Pair<K,V> { ... }` |
| Components/state | Header là bản mô tả trạng thái chuẩn; component fields final | Tự chọn các trường, có thể mutable/final |
| Accessor | Java tạo `key()`, `value()` theo tên component | Tự viết accessor nếu muốn |
| Constructor chuẩn | Canonical constructor có tham số theo component | Tự thiết kế constructor |
| equals/hashCode/toString | Được cung cấp theo components (trừ khi override hợp lệ) | Thừa hưởng từ `Object` nếu không tự định nghĩa |
| Kế thừa lớp | Record final và không extends class tùy ý | Có thể kế thừa theo quy tắc Java |
| Interface | Có thể implements generic interface | Có thể implements generic interface |
| Type parameter/erasure | Áp dụng quy tắc Java Generics | Áp dụng quy tắc Java Generics |
| Bất biến sâu | **Không tự bảo đảm** khi component tham chiếu mutable | Phụ thuộc thiết kế |

**Chọn generic record** khi đối tượng chủ yếu biểu diễn một tập giá trị, muốn API ngắn gọn và semantics của components phù hợp. **Chọn class** khi cần kế thừa một superclass khác, trạng thái nội bộ khác danh sách components, vòng đời có nhiều thay đổi, hoặc muốn kiểm soát hoàn toàn mô hình trạng thái. Đừng chọn record chỉ vì code ngắn nếu API thực sự cần encapsulation khác.

## 16. Một ví dụ tổng hợp: record làm kết quả xử lý có kiểu

Một API thường phải trả nhiều giá trị có liên hệ. Generic record là cấu trúc phù hợp để gom kết quả, vẫn giữ type rõ ràng.

Tạo `GenericResultDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class GenericResultDemo {
    record Result<T>(T value, List<String> warnings) {
        Result {
            value = Objects.requireNonNull(value);
            warnings = List.copyOf(warnings);
        }

        <R> Result<R> map(Function<? super T, ? extends R> mapper) {
            return new Result<>(mapper.apply(value), warnings);
        }
    }

    public static void main(String[] args) {
        Result<String> input =
                new Result<>("Java", List.of("normalized"));

        Result<Integer> length = input.map(String::length);

        System.out.println(input.value());
        System.out.println(length.value());
        System.out.println(length.warnings());
    }
}
```

Chạy:

```bash
javac GenericResultDemo.java
java GenericResultDemo
```

`stdout`:

```text
Java
4
[normalized]
```

Phân tích kiểu:

1. `Result<T>` giữ dữ liệu chính bằng component `T value` và metadata bằng `List<String> warnings`.
2. `Result<String>` áp dụng `T=String`, nên `input.value()` có kiểu `String`.
3. `map` khai báo type parameter **phương thức** `<R>`. Với `String::length`, `R` suy luận `Integer`, vì vậy `Result<R>` trở thành `Result<Integer>` tại điểm gọi.
4. `warnings` không phụ thuộc `T` hay `R`; cả input và result có thể chia sẻ một unmodifiable list phù hợp vì constructor thực hiện `List.copyOf`.
5. Không thể gán `Result<Integer>` trực tiếp cho `Result<String>`. Type parameter được compiler giữ nhất quán.
6. `Objects.requireNonNull(value)` và `List.copyOf(warnings)` thể hiện các invariant runtime bổ sung. Nếu mapper trả null, constructor của `Result<R>` sẽ ném `NullPointerException`; Generics tự nó không ngăn null.
7. `Result` là record nên việc tạo kết quả mới không thay đổi `input`.

Ví dụ này chỉ phục vụ bài học về generic record và các components được tham số hóa. Nếu ứng dụng cần mô hình kết quả có nhánh thành công/thất bại, có thể thiết kế các kiểu riêng với sealed interface và record ở một bài học nâng cao.

## 17. Các ràng buộc cú pháp cần nhớ

| Tình huống | Có hợp lệ? | Giải thích |
| --- | --- | --- |
| `record Box<T>(T value) {}` | Có | Record khai báo type parameter. |
| `record Pair<K,V>(K key,V value) {}` | Có | Nhiều biến kiểu. |
| `record Metrics<N extends Number>(N value) {}` | Có | Type parameter có bound. |
| `record Items<T>(List<T> data) {}` | Có, nếu import List | Component generic lồng sử dụng `T`. |
| `record ArrayBox<T>(T[] values) {}` | Có | Component dạng mảng của `T`; cần chú ý mutability. |
| `record Bad<T>(T value) { T extra; }` | Không | Record không được khai báo instance field mới bên ngoài components. |
| `record Bad<T>(T value) extends Parent {}` | Không | Record không extends superclass tùy ý. |
| `class Child extends Box<String> {}` | Không nếu Box là record | Record mặc nhiên final. |
| `record Bad<T>(T value) { static T shared; }` | Không | Static member không dùng được type parameter instance của record. |
| `record Bad(int x, ...)` với biến kiểu nguyên thủy `T=int` | Không | Generics đòi reference type làm type argument, không dùng `int` như argument. |
| `record Pair<K,V>(K key,V value) implements Serializable {}` | Có nếu import/ghi đầy đủ interface | Record có thể implement interface; không mặc định implements `Serializable`. |

Các ví dụ `Bad` được viết để **minh họa lỗi compiler**; không ghép chúng vào một file thực thi rồi mong biên dịch thành công.

### Generic varargs cần thận trọng

Record header có thể dùng component varargs ở vị trí cuối giống constructor varargs, nhưng nếu varargs phụ thuộc generic non-reifiable type (như `T...`), compiler có thể cảnh báo về khả năng heap pollution. Đừng xem việc record có final fields là lý do bỏ qua unchecked/varargs warning. Với API công khai, thường dễ thiết kế an toàn hơn bằng component `List<T>` kết hợp defensive copy.

### Null, equals và serialization

- `record Pair<K,V>(K key,V value)` mặc định có thể chứa null ở component reference; muốn cấm null phải kiểm tra trong canonical constructor.
- Generated `equals`/`hashCode` dựa vào component values, không kiểm tra type arguments từng instance.
- Record **không tự động** implements `Serializable` chỉ vì là record. Nếu cần serialization Java, có thể khai báo implement interface và hiểu cơ chế serialization dành riêng cho record; không suy diễn từ generic type.
- Annotation liên quan đến component có thể tác động tới record component, field, accessor hoặc constructor parameter tùy các annotation targets; cơ chế này độc lập với cú pháp type parameter cơ bản.

## 18. Lỗi thường gặp và cách khắc phục

### Lỗi 1: nghĩ accessor luôn là getX()

`record Pair<K,V>(K key,V value)` cung cấp `key()`/`value()`. Gọi `getKey()` sẽ không biên dịch nếu bạn không tự khai báo method đó.

### Lỗi 2: bỏ type arguments khi dùng record

`Pair raw = new Pair("A", 1)` đánh mất thông tin kiểu, tạo raw/unchecked warnings. Dùng `Pair<String,Integer>` hoặc `var pair = new Pair<>("A",1)` khi kiểu suy luận rõ ràng. Nếu thật sự không biết các kiểu, dùng `Pair<?,?>` thay vì raw type.

### Lỗi 3: tin rằng final component làm collection bất biến sâu

`record Box<T>(List<T> values)` chỉ có trường final, không tự clone list và không làm các phần tử bất biến. Cân nhắc `List.copyOf`, kiểm tra null và sao chép sâu khi nhu cầu nghiệp vụ yêu cầu.

### Lỗi 4: hiểu sai bất biến kiểu của record

`Pair<String,Integer>` không là subtype của `Pair<String,Number>`. Khi cần một view linh hoạt để đọc `Number`, cân nhắc `Pair<String,? extends Number>`. Đừng dùng cast unchecked chỉ để loại bỏ compile error.

### Lỗi 5: quên điều kiện của bound

`Measurement<N extends Number>` không nhận `String` làm type argument. Nếu algorithm cần `Comparable`, hãy khai báo bound phù hợp; không cast bừa sang `Comparable`.

### Lỗi 6: nhầm type parameter của record và của method

`record Box<T>(T value) { <R> Box<R> map(...) { ... } }` có `T` thuộc record và `R` thuộc method. Mỗi invocation của `map` có thể suy luận `R` khác, trong khi `T` của receiver đã xác định tại kiểu của `Box<T>`.

### Lỗi 7: mong runtime biết `Pair<String,Integer>`

`getClass()` trả cùng record class bất kể type arguments. Metadata declaration có thể đọc bằng reflection nhưng không bảo đảm JVM kiểm tra từng đối tượng theo `K=String`, `V=Integer`.

### Lỗi 8: tạo constructor mà không hoàn tất khởi tạo components

Canonical constructor tường minh phải gán component fields. Compact constructor được compiler hoàn tất phần gán ngầm sau body; không gán `this.component` bên trong compact constructor. Non-canonical constructors phải gọi constructor khác của record bằng `this(...)`.

### Lỗi 9: đặt instance state không nằm trong header

Record không cho khai báo thêm instance fields tùy ý. Nếu cần trạng thái mutable ngoài components, class thường phù hợp hơn. Static constants hoặc helper methods có thể được khai báo theo quy tắc Java.

## 19. Bài thực hành tự kiểm tra

### Bài 1 — Dự đoán kiểu

Với `record Pair<K,V>(K key,V value) {}`, hãy dự đoán:

```java
Pair<String, Long> p = new Pair<>("order", 10L);
String a = p.key();
Long b = p.value();
// Integer wrong = p.value();
```

Đáp án: `a` và `b` hợp lệ; dòng `wrong` lỗi biên dịch vì accessor trả `Long`, không phải `Integer`.

### Bài 2 — Viết record có validation

Viết `record NonBlank<T>(String name, T payload)` với compact constructor kiểm tra `name` không null/blank và `payload` không null. Thử `NonBlank<Integer>`; mô tả rõ những ràng buộc nào do compiler generic kiểm tra, những ràng buộc nào do constructor kiểm tra runtime.

Gợi ý: `Objects.requireNonNull(payload)` và `name.isBlank()`, sau khi xác thực `name` không null. Hãy ném `IllegalArgumentException` cho chuỗi rỗng theo hợp đồng bạn chọn.

### Bài 3 — Interface generic

Viết `interface Identified<ID> { ID id(); }` và `record Task<ID,T>(ID id,T data) implements Identified<ID> {}`. Giải thích vì sao `Task<Long,String>` tự đáp ứng method `id()`, nhưng không đáp ứng interface đòi `getId()` nếu không bổ sung method.

### Bài 4 — Defensive copy

Dùng `record Group<T>(List<T> members)` để chứa `List<String>`. Hãy sửa canonical constructor để biến nó thành snapshot, sau đó thay đổi danh sách đầu vào. Kiểm tra snapshot không đổi; tiếp tục thử với `StringBuilder` để giải thích tại sao phần tử mutable có thể vẫn đổi.

### Bài 5 — Bounded record

Viết `record Interval<T extends Comparable<? super T>>(T start,T end)` và bắt lỗi nếu start lớn hơn end. Thử với `Integer` và `String`. Vì sao `T` phải có bound khi gọi `compareTo`?

### Bài 6 — Reflection

Dùng `RecordComponent.getGenericType()` để tìm kiểu khai báo của component `List<T> values`. Sau đó tạo `Container<String>` và `Container<Integer>`, so sánh runtime classes. Giải thích sự khác nhau giữa **metadata khai báo** và **đối số kiểu của một tham chiếu**.

### Bài 7 — Phân tích equality

Tạo hai `Pair<String,Number>` và `Pair<String,Integer>` có component values thực sự bằng nhau. Dự đoán `equals`. Tiếp theo thử record có component `int[]` chứa cùng nội dung nhưng hai array instances khác nhau; giải thích vì sao không nên mặc định mong deep equality.

## 20. Checklist khi thiết kế generic record

Khi chuẩn bị tạo một generic record cho dự án, trả lời các câu sau:

1. Record có thực sự đại diện cho **tập components mang dữ liệu** không? Nếu cần lifecycle/state tùy biến sâu, cân nhắc class.
2. Type parameter `T`, `K`, `V` được khai báo ở đâu và ràng buộc các components nào? Có cần bound?
3. Accessor do record sinh trả kiểu gì tại mỗi concrete type argument?
4. Constructor cần bảo vệ invariant nào (null, range, empty list, quan hệ giữa components)?
5. Có component tham chiếu mutable không? Cần defensive copy, deep copy hay API immutable?
6. Thao tác nào nên là instance method, thao tác nào cần một generic method `<R>` khác với type parameter của record?
7. Record có cần implement generic interface để phù hợp một contract chung không?
8. Caller có cần wildcard `? extends`/`? super` để nhận nhiều type arguments, hay kiểu cụ thể là đủ?
9. Có cần custom equality/hashCode do component chứa mảng hoặc quan hệ bình đẳng nghiệp vụ khác mặc định không?
10. Có đang phụ thuộc vào runtime generic type argument mà type erasure không cung cấp không?

Generic record đem lại sự gọn gàng ở khai báo **và** sự an toàn kiểu ở compile time. Hãy luôn lần theo type parameter từ record header tới từng component, accessor và constructor; sau đó đánh giá các ràng buộc runtime độc lập như null, mutability và equality. Cách đọc đó giúp dùng record cho DTO, value object, cặp dữ liệu và kết quả xử lý mà vẫn giữ API chính xác, dễ hiểu và dễ kiểm chứng.