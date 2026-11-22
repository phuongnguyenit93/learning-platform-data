# Generics kết hợp với lớp, giao diện, phương thức và collection trong Java

Generics cho phép lớp, giao diện và phương thức nhận **kiểu dữ liệu như một tham số**. Nhờ đó, cùng một cấu trúc hoặc thuật toán có thể phục vụ nhiều kiểu mà vẫn được trình biên dịch kiểm tra tính đúng đắn. Trong Java Core, generics đặc biệt quan trọng khi thiết kế `List<E>`, `Set<E>`, `Map<K, V>`, các lớp bao dữ liệu, giao diện repository và phương thức xử lý collection.

Bài này sử dụng cú pháp tương thích **Java 17+**. Các đoạn mã ngắn dùng để minh họa từng quy tắc; cuối bài có chương trình `GenericsGuide.java` độc lập, biên dịch và chạy được.

## 1. Tư duy nền tảng: tham số kiểu thay cho `Object`

Một lớp chỉ dùng `Object` chứa được nhiều loại giá trị, nhưng người gọi phải ép kiểu và dễ gặp `ClassCastException` khi chạy:

```java
// Minh họa cách viết cũ, chưa có generics.
class ObjectBox {
    Object value;
    ObjectBox(Object value) { this.value = value; }
    Object get() { return value; }
}

// String name = (String) new ObjectBox(123).get();
// Biên dịch được, nhưng ép Integer thành String sẽ lỗi khi chạy.
```

Với lớp `Box<T>`, `T` đại diện cho kiểu do nơi sử dụng chọn:

```java
// Đoạn minh họa, được đặt trong một tệp Java thích hợp.
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> title = new Box<>("Java");
String text = title.get();           // Không cần ép kiểu.
Box<Integer> count = new Box<>(12);
Integer number = count.get();
// Box<String> wrong = new Box<>(12); // Lỗi ngay khi biên dịch.
```

Trong `Box<String>`, tham số `T` được thay bằng `String` trong cách trình biên dịch kiểm tra lời gọi. Việc kiểm tra diễn ra **lúc biên dịch**; đây không phải cam kết Java tạo riêng một lớp runtime mới cho mỗi `T`.

Quy ước tên thường gặp: `T` (type), `E` (element), `K` (key), `V` (value), `R` (result), `S` (source). Các chữ này là tên tham số kiểu, không phải từ khóa. Nên dùng tên dễ hiểu nếu cần nhiều tham số cùng lúc.

**Kiểu tham số phải là kiểu tham chiếu**: dùng `List<Integer>` thay vì `List<int>`, `Box<Boolean>` thay vì `Box<boolean>`. Autoboxing có thể chuyển `int` thành `Integer` khi thêm phần tử.

## 2. Generics trên lớp: một hoặc nhiều tham số kiểu

Khai báo `class ClassName<T>` đặt `T` trong phạm vi các thành viên instance của lớp. Khi cần quan hệ giữa hai kiểu, khai báo nhiều tham số:

```java
// Minh họa một lớp bất biến có hai tham số kiểu.
final class Pair<L, R> {
    private final L left;
    private final R right;

    Pair(L left, R right) {
        this.left = left;
        this.right = right;
    }

    L left() { return left; }
    R right() { return right; }
}

Pair<String, Integer> score = new Pair<>("Lan", 9);
String student = score.left();
int point = score.right();
```

`L` và `R` có thể giống hoặc khác nhau. Toán tử kim cương `<>` ở `new Pair<>(...)` cho phép trình biên dịch suy luận kiểu từ ngữ cảnh. Từ Java 16, có thể diễn đạt cặp dữ liệu ngắn hơn bằng `record Pair<L, R>(L left, R right) {}` khi phù hợp với thiết kế dữ liệu bất biến.

Một lớp generic có thể kế thừa hoặc triển khai cấu trúc generic theo hai cách:

```java
// Tiếp tục chuyển tham số kiểu từ lớp cha xuống lớp con.
class NamedBox<T> extends BoxBase<T> {
    NamedBox(T item) { super(item); }
}

// Cố định kiểu của lớp cha.
class StringBox extends BoxBase<String> {
    StringBox(String item) { super(item); }
}

class BoxBase<T> {
    private final T item;
    BoxBase(T item) { this.item = item; }
    T get() { return item; }
}
```

Trong `NamedBox<Integer>`, kiểu của `BoxBase<T>` tương ứng là `Integer`; trong `StringBox`, kiểu `String` đã cố định. Một lớp generic không được dùng chính tham số kiểu của lớp trong trường `static` hoặc phương thức `static` nếu phương thức đó không tự khai báo tham số kiểu: `T` phụ thuộc từng cách sử dụng lớp, còn thành viên `static` thuộc về lớp chung.

### Giới hạn tham số kiểu bằng `extends`

Nếu thuật toán cần thao tác chỉ có trên một loại đối tượng, đặt **upper bound**:

```java
// Minh họa phương thức generic có bound.
static <T extends Number> double total(java.util.Collection<T> items) {
    double sum = 0;
    for (T item : items) {
        sum += item.doubleValue();
    }
    return sum;
}
```

`T extends Number` nhận `Integer`, `Long`, `Double`... và cho phép gọi `doubleValue()`. Dù `Number` là lớp, từ khóa vẫn là `extends`; với interface cũng dùng `extends`, ví dụ `<T extends Comparable<T>>`.

Có thể đặt nhiều bound: `<T extends Number & Comparable<T>>`. Nếu có bound là lớp thì lớp phải đứng trước các interface. Bound không biến `List<Integer>` thành `List<Number>`; đó là vấn đề phương sai, sẽ xét riêng ở mục 6.

## 3. Generics trên giao diện: hợp đồng API có kiểu

Giao diện generic mô tả thao tác độc lập với loại khóa và dữ liệu, đồng thời giữ liên hệ giữa đầu vào và kết quả:

```java
// Các đoạn trong khối này minh họa cùng một API.
interface Repository<ID, E> {
    void save(ID id, E entity);
    java.util.Optional<E> findById(ID id);
}

final class InMemoryRepository<ID, E> implements Repository<ID, E> {
    private final java.util.Map<ID, E> data = new java.util.HashMap<>();

    @Override
    public void save(ID id, E entity) {
        data.put(id, entity);
    }

    @Override
    public java.util.Optional<E> findById(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}

Repository<Long, String> repo = new InMemoryRepository<>();
repo.save(1L, "Lan");
String found = repo.findById(1L).orElse("Không tìm thấy");
// repo.save("sai kiểu khóa", "Lan"); // Lỗi biên dịch.
```

`ID` bảo đảm khóa dùng ở `save` và `findById` có cùng kiểu; `E` bảo đảm giá trị lưu và giá trị trong `Optional<E>` có cùng kiểu. `Optional<E>` biểu diễn khả năng không có kết quả, giúp API tránh trả về `null` trực tiếp.

Một lớp cũng có thể cố định kiểu ngay khi triển khai, chẳng hạn `UserRepository implements Repository<Long, User>`. Khi đó các chữ ký phương thức phải tương ứng với `Long` và `User`.

Các interface chuẩn như `Comparable<T>`, `Comparator<T>`, `Iterable<T>`, `Function<T, R>` hay `Predicate<T>` đều áp dụng cùng nguyên lý: khai báo mối quan hệ kiểu tại nơi thiết kế, để nơi sử dụng được kiểm tra nhất quán.

## 4. Generics trên phương thức: phạm vi kiểu thuộc từng lời gọi

Một phương thức generic khai báo `<T>` **trước kiểu trả về**, độc lập với việc lớp chứa nó có generic hay không:

```java
// Minh họa các phương thức trong một lớp tiện ích.
static <T> T first(java.util.List<T> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException("empty list");
    }
    return items.get(0);
}

static <A, B> java.util.Map.Entry<A, B> entry(A key, B value) {
    return new java.util.AbstractMap.SimpleImmutableEntry<>(key, value);
}
```

Khi gọi `first(List<String>)`, kiểu trả về được suy luận là `String`; khi gọi `first(List<Integer>)`, kiểu trả về là `Integer`. Phương thức `static` hoàn toàn có thể generic vì nó **tự khai báo** `<T>`.

```java
// Minh họa lời gọi trong phương thức/chương trình Java.
String a = first(java.util.List.of("A", "B"));
Integer b = first(java.util.List.of(3, 4));
java.util.Map.Entry<String, Integer> grade = entry("Lan", 9);
```

Trình biên dịch thường suy luận được tham số kiểu, nhưng có thể chỉ định tường minh khi cần: `Collections.<String>emptyList()`. Cần phân biệt:

- `class Box<T>`: `T` thuộc lớp, được cố định theo từng `Box<String>` hoặc `Box<Integer>`.
- `<T> T first(List<T> xs)`: `T` thuộc riêng phương thức và được suy luận cho mỗi lời gọi.
- `static <T> ...`: hợp lệ; `static T get()` bên trong `class Box<T>` thì không hợp lệ vì `T` thuộc instance context của lớp.

Khi cần so sánh phần tử theo thứ tự tự nhiên, bound `<T extends Comparable<? super T>>` hữu ích hơn việc ép mọi phần tử về `Object`:

```java
// Minh họa một phương thức tổng quát.
static <T extends Comparable<? super T>> T maximum(
        java.util.List<? extends T> values) {
    if (values.isEmpty()) {
        throw new java.util.NoSuchElementException("empty list");
    }
    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

`Comparable<? super T>` chấp nhận cả trường hợp đối tượng `T` triển khai khả năng so sánh ở một lớp cha của `T`. Trong ứng dụng thực tế, ưu tiên hàm thư viện `Collections.max(...)` nếu đủ yêu cầu.

## 5. Generics kết hợp Java Collections Framework

Collection là nơi người học gặp generics thường xuyên nhất. Tham số kiểu biến ràng buộc dữ liệu thành một phần của API:

| Cấu trúc | Khai báo điển hình | Đặc điểm |
| --- | --- | --- |
| `List<E>` | `List<String>` | Có thứ tự vị trí, cho phép phần tử trùng; truy cập bằng chỉ số. |
| `Set<E>` | `Set<Long>` | Không chứa phần tử trùng theo quy tắc `equals`/`hashCode` hoặc comparator của triển khai. |
| `Queue<E>` | `Queue<Task>` | Mô hình hàng đợi; thứ tự lấy phụ thuộc triển khai. |
| `Collection<E>` | `Collection<Number>` | Giao diện chung cho nhóm phần tử; không có truy cập chỉ số chung. |
| `Map<K, V>` | `Map<String, Integer>` | Ánh xạ khóa đến giá trị; **`Map` không kế thừa `Collection`**. |

Ví dụ thao tác với collection có kiểu:

```java
// Minh họa lời gọi khi đã import java.util.*.
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
// names.add(42); // Lỗi biên dịch: phần tử phải là String.
String firstName = names.get(0);

Set<String> tags = new LinkedHashSet<>(List.of("java", "core", "java"));
// LinkedHashSet giữ thứ tự chèn, kết quả khi in: [java, core].

Map<String, List<Integer>> scores = new HashMap<>();
scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(9);
scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(8);
List<Integer> lanScores = scores.get("Lan"); // [9, 8]
```

`Map<String, List<Integer>>` là **generic lồng nhau**: khóa phải là `String`, mỗi giá trị là danh sách `Integer`. `computeIfAbsent` trả về giá trị đã có hoặc tạo giá trị mới khi khóa vắng mặt (hay đang ánh xạ tới `null`), rồi có thể gọi `add` trên danh sách tương ứng.

Một số tính chất của factory và implementation ảnh hưởng trực tiếp tới cách viết ví dụ:

- `List.of(...)`, `Set.of(...)`, `Map.of(...)` tạo collection **không sửa được**; các factory này không chấp nhận phần tử `null` (và `Set.of` không chấp nhận phần tử trùng).
- `new ArrayList<>(List.of(...))` tạo danh sách có thể sửa. `Arrays.asList(...)` tạo danh sách kích thước cố định: có thể thay phần tử bằng `set`, nhưng không `add/remove` để đổi kích thước.
- `HashMap` và `HashSet` không cam kết thứ tự duyệt; `LinkedHashMap` và `LinkedHashSet` giữ thứ tự chèn; `TreeMap` và `TreeSet` sắp xếp theo thứ tự hoặc comparator phù hợp.
- `Map.get(key)` trả `null` khi không có ánh xạ, nhưng cũng có thể trả `null` nếu map cho phép giá trị `null`. Dùng `containsKey` khi cần phân biệt.

Khi chỉ cần dùng hành vi của giao diện, nên khai báo phía trái là `List<E>`, `Set<E>` hoặc `Map<K,V>`, và chọn lớp triển khai ở phía phải. Cách này giữ API dễ thay đổi.

## 6. Invariance, wildcard và nguyên tắc PECS

Java generics **bất biến (invariant)**: dù `Integer extends Number`, `List<Integer>` **không phải** `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Lỗi biên dịch.
```

Nếu phép gán trên được phép thì `numbers.add(3.14)` sẽ đưa `Double` vào danh sách vốn chỉ nhận `Integer`. Thay vì nới quy tắc một cách không an toàn, Java cung cấp wildcard:

| Kiểu tham số | Có thể đọc an toàn như | Có thể thêm trực tiếp |
| --- | --- | --- |
| `List<T>` | `T` | Giá trị `T` |
| `List<? extends Number>` | `Number` | Không thêm giá trị `Number` cụ thể; có thể thêm `null` |
| `List<? super Integer>` | `Object` | `Integer` và lớp con của `Integer` (thực tế `Integer` là final); `null` |
| `List<?>` | `Object` | Không thêm phần tử không phải `null` |

### `? extends T`: nguồn để đọc

```java
// Minh họa phương thức đọc từ các loại collection số.
static double sumNumbers(List<? extends Number> source) {
    double result = 0;
    for (Number number : source) {
        result += number.doubleValue();
    }
    return result;
}

// sumNumbers(List.of(1, 2, 3));     // List<Integer>
// sumNumbers(List.of(1.5, 2.5));     // List<Double>
```

`source` có thể là `List<Integer>`, `List<Double>` hoặc `List<Number>`. Không thể `source.add(1)` vì kiểu phần tử thực tế của danh sách có thể là `Double`. Ngay cả `Number` cũng chưa đủ để quyết định kiểu có thể thêm.

### `? super T`: đích để ghi

```java
// Minh họa phương thức ghi.
static void addDefaults(List<? super Integer> target) {
    target.add(1);
    target.add(2);
}

// addDefaults(new ArrayList<Integer>());
// addDefaults(new ArrayList<Number>());
// addDefaults(new ArrayList<Object>());
```

Một đích `List<? super Integer>` nhận được `Integer`, nhưng khi lấy phần tử ra chỉ có thể giả định `Object`, vì danh sách có thể khai báo là `List<Object>`.

**PECS = Producer Extends, Consumer Super**: tham số cung cấp đối tượng kiểu `T` nên cân nhắc `? extends T`; tham số nhận đối tượng kiểu `T` nên cân nhắc `? super T`.

Ví dụ tổng hợp cả hai phía:

```java
// Minh họa phương thức sao chép không thay đổi nguồn.
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}

// List<Integer> src = List.of(1, 2);
// List<Number> dst = new ArrayList<>();
// appendAll(src, dst); // dst chứa [1, 2].
```

Nếu hai tham số phải có **quan hệ cùng một kiểu** hoặc phương thức cần **trả về đúng kiểu đó**, dùng tên tham số `<T>` như `appendAll` và `first`. Nếu chỉ đọc/in ra dữ liệu mà không cần nối quan hệ giữa các vị trí, `List<?>` thường đơn giản hơn:

```java
static void printAll(List<?> values) {
    for (Object item : values) {
        System.out.println(item);
    }
}
```

Wildcard không phải cơ chế "cho phép mọi thao tác". Nó mô tả những gì API biết về kiểu, nên trình biên dịch giới hạn thao tác đọc và ghi cho an toàn.

## 7. Collections và hàm nhận/trả về generic: thiết kế API thực tế

Giả sử cần chuyển đổi một danh sách `S` thành danh sách `R`. Chữ ký linh hoạt thường kết hợp method type parameter với wildcard của `Function`:

```java
// Minh họa phương thức; import java.util.* và java.util.function.*.
static <S, R> List<R> mapEach(
        Collection<? extends S> source,
        Function<? super S, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (S element : source) {
        result.add(mapper.apply(element));
    }
    return result;
}

// List<Integer> lengths = mapEach(List.of("a", "java"), String::length);
// lengths bằng [1, 4].
```

Nguồn sinh ra `S`, hàm chuyển đổi có thể nhận `S` hoặc một kiểu cha của `S`, và kết quả hàm là `R` hoặc kiểu con của `R`. Đây là lý do `Function<? super S, ? extends R>` xuất hiện trong nhiều API chuẩn.

Khi trả về collection từ public API, cân nhắc:

1. Nếu người gọi chỉ cần đọc, trả kiểu giao diện như `List<E>` và xác định rõ có thể sửa hay không; ví dụ `List.copyOf(source)` tạo bản sao không sửa được và không chấp nhận `null`.
2. Nếu phương thức chỉ duyệt phần tử, nhận `Iterable<? extends T>` hoặc `Collection<? extends T>` tùy thao tác thực sự cần; tránh ép mọi thứ thành `ArrayList<T>`.
3. Nếu cần giữ quan hệ key/value, dùng `Map<K,V>` và không thay bằng `Map<Object,Object>`.
4. Nếu cần sắp xếp, cân nhắc `Comparator<? super T>` để chấp nhận comparator của kiểu cha, hoặc bound `Comparable<? super T>` cho thứ tự tự nhiên.
5. Chọn tham số kiểu có ý nghĩa, tránh khai báo `<T>` không xuất hiện trong đầu vào/kết quả hoặc không mang quan hệ kiểu nào.

Ví dụ biến đổi bằng Stream cũng giữ generic xuyên suốt:

```java
// Minh họa khi đã import java.util.*.
List<String> words = List.of("A", "Java");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList(); // [1, 4], List không sửa được từ Stream.toList().
```

Ở đây `Stream<String>` đi qua `map` thành `Stream<Integer>`. `toList()` (Java 16+) tạo danh sách không sửa được; nếu cần bản có thể sửa, dùng `collect(Collectors.toCollection(ArrayList::new))`.

## 8. Type erasure: generics tồn tại như thế nào lúc chạy?

Java triển khai phần lớn generics bằng **type erasure** (xóa thông tin tham số kiểu trong biểu diễn runtime thông thường). Trình biên dịch kiểm tra kiểu, chèn cast cần thiết và ánh xạ tham số kiểu tới bound thích hợp; ví dụ `T` không có bound thường xóa về `Object`, còn `T extends Number` thường xóa về `Number`. Trình biên dịch có thể tạo **bridge method** để giữ đúng đa hình sau erasure.

Hệ quả quan trọng:

- `new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass()` là `true`: hai cách tham số hóa dùng cùng lớp runtime `ArrayList`.
- Không thể kiểm tra `value instanceof List<String>`; có thể kiểm tra `value instanceof List<?>` vì lúc chạy không xác nhận được tham số `String`.
- Không thể viết `new T()`, `new T[10]` hoặc trực tiếp tạo mảng generic `new List<String>[10]` trong những trường hợp thông thường. Nếu cần tạo đối tượng `T`, có thể truyền factory `Supplier<T>` hoặc `Class<T>` phù hợp.
- Không thể overload chỉ theo tham số kiểu bị xóa giống nhau, ví dụ hai phương thức `process(List<String>)` và `process(List<Integer>)` cùng tên sẽ xung đột erasure.
- `static` field không thể có kiểu `T` lấy từ tham số kiểu của class; mỗi cách tham số hóa không có bản sao field `static` riêng.

**Erasure không có nghĩa toàn bộ dấu vết generic biến mất khỏi metadata.** Chẳng hạn reflection có thể đọc kiểu khai báo generic ở trường, phương thức và lớp cha qua các API như `getGenericType()` hoặc `getGenericSuperclass()`; tuy nhiên tham số cụ thể của một `new ArrayList<String>()` thông thường không trở thành một đặc tính runtime có thể kiểm tra bằng `instanceof`.

### Raw type và cảnh báo unchecked

```java
// Minh họa mã cũ, không nên đưa vào API mới.
List raw = new ArrayList();
raw.add("Java");
raw.add(42);
List<String> names = raw; // Cảnh báo unchecked conversion.
String second = names.get(1); // ClassCastException khi chạy.
```

Raw type (`List` thay vì `List<String>`) bỏ qua một phần kiểm tra generic, thường chỉ cần khi tương tác code cũ. **`List<?>` khác raw `List`**: `List<?>` vẫn giữ ràng buộc kiểu an toàn và không cho thêm đối tượng bất kỳ. Không dùng `@SuppressWarnings("unchecked")` để che lỗi thiết kế; chỉ dùng khi có lý do kiểm chứng được và giới hạn phạm vi cảnh báo.

## 9. Ví dụ hoàn chỉnh: lớp + interface + phương thức + collection

Tạo tệp **`GenericsGuide.java`** chứa đúng chương trình sau. Các lớp lồng `static` ở đây được dùng để có một tệp chạy độc lập và cho thấy rõ mối liên hệ giữa các phần.

```java
import java.util.*;
import java.util.function.Function;

public class GenericsGuide {
    static final class Box<T> {
        private final T value;

        Box(T value) { this.value = value; }

        T get() { return value; }

        <R> Box<R> map(Function<? super T, ? extends R> f) {
            return new Box<>(f.apply(value));
        }
    }

    interface Repository<ID, E> {
        void save(ID id, E value);
        Optional<E> findById(ID id);
    }

    static final class MemoryRepository<ID, E> implements Repository<ID, E> {
        private final Map<ID, E> data = new LinkedHashMap<>();

        @Override
        public void save(ID id, E value) {
            data.put(id, value);
        }

        @Override
        public Optional<E> findById(ID id) {
            return Optional.ofNullable(data.get(id));
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("empty list");
        }
        return values.get(0);
    }

    static <T extends Number> double sum(Collection<T> values) {
        double result = 0;
        for (T value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        Box<String> word = new Box<>("Java");
        Box<Integer> length = word.map(String::length);
        System.out.println("Box: " + word.get() + " -> " + length.get());

        Repository<Long, String> users = new MemoryRepository<>();
        users.save(10L, "Lan");
        System.out.println("Repository: " + users.findById(10L).orElse("unknown"));

        List<Integer> scores = List.of(2, 3, 5);
        System.out.println("First: " + first(scores));
        System.out.println("Sum: " + sum(scores));
        List<Number> numbers = new ArrayList<>();
        appendAll(scores, numbers);
        System.out.println("Copied: " + numbers);

        Set<String> tags = new LinkedHashSet<>(List.of("java", "generics", "java"));
        System.out.println("Set: " + tags);
        Map<String, List<Integer>> grades = new LinkedHashMap<>();
        grades.put("Lan", List.of(8, 9));
        System.out.println("Map: " + grades.get("Lan"));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac GenericsGuide.java
java GenericsGuide
```

Kết quả stdout **chính xác** (đã kiểm chứng với Java 21, cú pháp hợp lệ từ Java 17):

```text
Box: Java -> 4
Repository: Lan
First: 2
Sum: 10.0
Copied: [2, 3, 5]
Set: [java, generics]
Map: [8, 9]
```

Diễn giải mối liên hệ trong chương trình:

- `Box<T>` là lớp generic: `Box<String>` chứa từ; phương thức generic `<R> map(...)` trả `Box<Integer>` khi nhận `String::length`.
- `Repository<ID,E>` là interface generic; `MemoryRepository<ID,E>` thực thi hợp đồng bằng `Map<ID,E>`; `Optional<E>` giữ kiểu dữ liệu tìm thấy.
- `first` là phương thức generic không cần bound; `sum` yêu cầu `T extends Number` vì sử dụng `doubleValue()`.
- `appendAll` dùng `? extends T` cho nguồn `List<Integer>` và `? super T` cho đích `List<Number>`. Đây là áp dụng PECS để sao chép an toàn.
- `List<Integer>`, `Set<String>`, `Map<String,List<Integer>>` chứng minh tham số kiểu xuyên suốt thao tác lưu, đọc, lặp và ánh xạ.

Lưu ý: `Set` in theo thứ tự ổn định ở ví dụ vì dùng `LinkedHashSet`; `List.of` là danh sách không sửa được nhưng vẫn đọc và sao chép bình thường.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `List<Number> x = new ArrayList<Integer>()` bị lỗi | Generics invariant | Dùng `List<? extends Number>` nếu chỉ đọc, hoặc khai báo kiểu phần tử thống nhất. |
| Không `add(1)` được vào `List<? extends Number>` | Không biết kiểu con cụ thể của danh sách | Dùng `List<? super Integer>` làm đích ghi hoặc `List<Number>` khi cần lưu nhiều kiểu số. |
| `new T()` không biên dịch | Type erasure; thiếu cách tạo `T` | Truyền `Supplier<T>`, factory hoặc constructor phù hợp. |
| `List<int>` không hợp lệ | Generic cần kiểu tham chiếu | Dùng `List<Integer>`. |
| `List raw` hoạt động nhưng cảnh báo unchecked | Đã bỏ kiểm tra tham số kiểu | Chuyển thành `List<E>`, hoặc `List<?>` nếu chưa biết `E`. |
| Ép `(List<String>)` từ `List<?>` | Không chứng minh phần tử thực sự là `String` | Kiểm tra/chuyển đổi từng phần tử có chủ đích; không ép collection mù quáng. |
| `add` vào `List.of(...)` ném `UnsupportedOperationException` | Factory trả danh sách không sửa được | Tạo `new ArrayList<>(List.of(...))` nếu cần sửa. |
| `static T value` trong `class Box<T>` bị lỗi | Tham số kiểu của lớp không thuộc `static` context | Dùng một kiểu cụ thể hoặc để phương thức `static` tự khai báo `<T>`. |
| Thêm phần tử sai kiểu vào raw list làm lỗi về sau | Mất kiểm tra compile-time, gây heap pollution | Tránh raw type và unchecked cast, chỉnh API tại nguồn. |

Không nên dùng wildcard trong mọi vị trí chỉ vì nó có vẻ linh hoạt. Nếu một `List<T>` thực sự cần cả đọc lẫn thêm `T`, kiểu chính xác `List<T>` thường thể hiện hợp đồng rõ hơn. Với các phương thức công khai, đặt giới hạn ở nơi cần thiết và để phần còn lại được suy luận tự nhiên.

## 11. Tự luyện tập và kiểm tra hiểu bài

**Bài 1 — Lớp:** Viết `Result<T>` chứa `T data` và `String message`. Tạo `Result<String>` và `Result<Integer>`. Câu hỏi tự kiểm tra: vì sao getter trả `T` giúp tránh cast?

**Bài 2 — Interface:** Thiết kế `Cache<K,V>` với `put(K,V)` và `Optional<V> get(K)`. Dùng `HashMap<K,V>` triển khai; tạo `Cache<String, Long>` rồi thử truyền khóa `Integer` để quan sát lỗi biên dịch.

**Bài 3 — Method + collection:** Viết `static <T> List<T> reversed(List<? extends T> source)` tạo danh sách mới theo thứ tự đảo ngược. Kiểm tra với `List<String>` và `List<Integer>`. Không sửa nguồn; phân biệt cách hoạt động này với `Collections.reverse`, vốn thay đổi danh sách truyền vào.

**Bài 4 — Chọn chữ ký:** Cần chuyển dữ liệu `List<Integer>` sang một `List<Number>`, nên nhận `List<Integer>`, `List<Number>`, `List<? extends Number>` hay `List<? super Integer>` tại mỗi phía? Giải thích bằng thao tác đọc và ghi, sau đó so sánh lời giải với chữ ký `appendAll`.

Để tự đánh giá, một lời giải đúng cần thể hiện: **tham số kiểu truyền qua lớp/giao diện/phương thức**, **compile-time type safety**, **invariance của collection**, và **lựa chọn `extends`/`super` theo hướng dữ liệu**. Đây là nền tảng để đọc hiểu các API generic trong thư viện Java và thiết kế collection API có thể tái sử dụng.
