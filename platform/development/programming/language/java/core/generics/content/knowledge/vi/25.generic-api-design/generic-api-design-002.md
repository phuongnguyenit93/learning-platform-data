# Đặt tên và viết tài liệu cho quan hệ giữa các kiểu trong Java Generics

Khi thiết kế API Java dùng Generics, một chữ ký **đúng về mặt cú pháp** chưa chắc đã **dễ hiểu về mặt hợp đồng**. Những tên `T`, `E`, `K`, `V`, `R`; giới hạn `extends`; wildcard `? extends`/`? super`; và thông tin viết trong Javadoc cùng giúp trả lời:

- Kiểu nào là **đầu vào**, kiểu nào là **kết quả**?
- Hai tham số có **phải cùng một kiểu** hay chỉ có quan hệ subtype/supertype?
- Một tham số là **nguồn sản xuất dữ liệu** hay **đích tiêu thụ dữ liệu**?
- Giới hạn kiểu nằm ở **lớp**, **phương thức**, hay một wildcard dùng ở **vị trí tham số**?
- Điều gì được compiler bảo vệ và điều gì thuộc **hợp đồng runtime** như `null`, mutation, ownership và exception?

Ví dụ cùng một mục tiêu “chuyển từng phần tử từ nguồn sang dạng kết quả mới”:

```java
// Chữ ký đúng nhưng khó hiểu nếu thiếu tên vai trò:
static <T, U> java.util.List<U> transform(
        Iterable<? extends T> x,
        java.util.function.Function<? super T, ? extends U> y);

// Có thể đặt tên theo vai trò để dễ đọc:
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper);
```

Cả hai đều diễn đạt cùng **quan hệ kiểu** trong ví dụ: đầu vào kiểu `S`, kết quả kiểu `R`; nguồn cung cấp `S`; mapper nhận một supertype thích hợp của `S` và trả subtype thích hợp của `R`. Tuy nhiên, phiên bản sau cho biết mục đích qua tên method, biến `source`/`mapper` và ký hiệu `S`/`R` trước cả khi đọc Javadoc.

**Nguyên tắc chính:** **tên mô tả vai trò, chữ ký mô tả ràng buộc compiler, Javadoc giải thích ngữ nghĩa và hành vi không thể suy ra chỉ từ kiểu**. Không dùng lời chú thích để bù cho một chữ ký truyền tải sai quan hệ kiểu.

## 1. Quy ước tên type parameters trong Java

Java thường dùng **tên chữ in hoa ngắn**, nhất là khi vai trò đã trở thành quy ước chung:

| Tên | Vai trò thông dụng | Ngữ cảnh |
| --- | --- | --- |
| `T` | Type tổng quát | `Box<T>`, `List<T>`, phương thức generic đơn giản |
| `E` | Element | `Collection<E>`, `List<E>`, `Set<E>` |
| `K` | Key | `Map<K, V>` |
| `V` | Value | `Map<K, V>`, `Optional<T>` thì `T` |
| `R` | Result/Return | `Function<T, R>`, API map/convert |
| `U`, `S` | Kiểu thứ hai/nguồn | Phương thức liên hệ hai kiểu độc lập |
| `T1`, `T2` | Các kiểu cùng vai trò nhưng phân biệt vị trí | Một vài abstraction nhiều đối số |

Đây là **quy ước**, không phải các tên có ý nghĩa đặc biệt trong compiler. `class Box<T>` và `class Box<V>` đều có thể hợp lệ nếu mọi tham chiếu tương ứng được đổi nhất quán.

Với interface/map:

```java
interface Lookup<K, V> {
    V get(K key);
}
```

Tên `K` và `V` giúp đọc nhanh rằng `get` nhận **key** và trả về **value**. Một API dùng `<T,U>` cho cùng vai trò có thể biên dịch, nhưng làm người đọc phải đoán nhiều hơn.

### Khi nào dùng tên dài?

Nếu một API có nhiều type parameters với quan hệ phức tạp, có thể chọn tên rõ nghĩa như `<SOURCE, RESULT>`, `<INPUT, OUTPUT>` hoặc `<KEY, VALUE>` khi quy ước codebase cho phép. Java cho phép các định danh đó, dù trong thư viện Java chuẩn tên ngắn `T`, `U`, `R`, `K`, `V` phổ biến hơn.

Tên dài **không tự giải quyết được thiết kế sai**. Ví dụ `<INPUT, OUTPUT>` không mô tả an toàn kiểu nếu method vẫn thực hiện unchecked casts không có bằng chứng. Hãy giữ các type parameter names ngắn và nhất quán khi vai trò đã rõ; dùng tên giàu ngữ nghĩa khi sự tương phản thật sự giúp đọc một chữ ký khó.

### Tên của biến và method cũng quan trọng

So sánh:

```java
static <T> void f(java.util.List<? extends T> a,
                  java.util.List<? super T> b);

// Dễ hiểu hơn:
static <T> void copy(
        java.util.List<? extends T> source,
        java.util.List<? super T> destination);
```

Chữ ký đầu có quan hệ kiểu phù hợp nhưng không nêu mục đích; chữ ký sau làm nổi bật **hướng dữ liệu**. Trong code triển khai, tên `source`, `destination`, `mapper`, `predicate`, `comparator`, `factory`, `fallback` và `result` thường quan trọng không kém tên `T`.

## 2. Đọc quan hệ kiểu trước khi chọn tên

Một thiết kế generic thường xoay quanh bốn dạng quan hệ:

1. **Cùng kiểu:** nhiều vị trí sử dụng cùng type variable `T`, ví dụ `T choose(T left, T right)`.
2. **Hai kiểu độc lập nhưng có phép chuyển:** `<S,R> R convert(S source, Function<? super S,? extends R> mapper)`.
3. **Ràng buộc subtype:** `<T extends Number>` hoặc `<T extends Comparable<? super T>>`.
4. **Quan hệ biến thiên ở vị trí dùng:** `Collection<? extends T>` làm nguồn, `Collection<? super T>` làm đích.

Ví dụ đơn giản:

```java
static <T> T first(java.util.List<T> items) {
    return items.get(0);
}
```

Tên `T` xuất hiện ở `List<T>` và kiểu trả về `T`. Đây là một **mối liên hệ do compiler kiểm tra**: `List<String>` cho `String` khi gọi, `List<Integer>` cho `Integer` (theo quy tắc suy luận và kiểu tĩnh của lời gọi).

Nếu đổi kiểu trả về thành `Object`, method vẫn có thể chạy nhưng sẽ **mất liên hệ kiểu** ở chữ ký:

```java
static Object firstUnclear(java.util.List<?> items) {
    return items.get(0);
}
```

Đó có thể là API hợp lý khi ý định chỉ đọc một giá trị không biết kiểu, nhưng không thay thế được hợp đồng `<T> T first(List<T>)` nếu caller cần nhận kết quả mà không cast.

**Câu hỏi thiết kế:** có một quan hệ kiểu thực sự nào đáng được biểu diễn bằng **cùng type variable** không? Nếu có, đừng làm yếu chữ ký thành `Object` rồi viết Javadoc “caller tự cast kết quả”.

## 3. Scope của type parameter: thuộc class hay method?

Type parameter có một **nơi khai báo**. `T` ở cấp lớp và `T` ở một method riêng không tự động là cùng biến kiểu.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value; // T của class Box
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value); // U của static method of
    }
}
```

`Box<String>` giữ một `String` ở góc nhìn compiler. `Box<Integer>` giữ một `Integer`. Method `of` là **static generic method** tự khai báo `U`; nó không tham chiếu trực tiếp `T` của class trong static context.

Một lỗi API dễ gây nhầm:

```java
class Store<T> {
    // T của method bên dưới là T MỚI, không phải T của Store:
    <T> void accept(T value) { }
}
```

Đoạn này có thể biên dịch nhưng method-level `T` **che khuất tên** `T` của class. Nếu mục tiêu là chỉ nhận `T` mà store đang mang, hãy viết:

```java
class Store<T> {
    void accept(T value) { }
}
```

Nếu mục tiêu là một kiểu thứ hai độc lập, viết `<U>` và tài liệu hóa quan hệ giữa `U` và `T`.

**Không nên tái sử dụng cùng tên type parameter ở các scope lồng nhau chỉ vì compiler cho phép.** Người đọc khó phân biệt hợp đồng kiểu lớp và hợp đồng kiểu method, nhất là trong API nhiều overload.

## 4. Đừng khai báo type parameter khi không tạo ra mối liên hệ hữu ích

Xét một utility chỉ in ra collection:

```java
static <T> void printAll(java.util.Collection<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
```

Code này đúng, nhưng nếu `T` chỉ xuất hiện đúng một lần trong khai báo và method không cần mối liên hệ đặc biệt, một wildcard có thể đơn giản hơn:

```java
static void printAll(java.util.Collection<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Dấu `?` diễn đạt rằng method **không cần biết hoặc đặt tên** element type. Điều này phù hợp với những API chỉ quan sát, đếm, log hoặc lấy kích thước.

Tuy nhiên, **không phải cứ xuất hiện một lần là phải dùng wildcard**. Một generic method vẫn cần `T` khi liên hệ kiểu với return type, callback, bound, một khai báo ngoại lệ liên quan, hoặc khi API cần type inference theo ngữ cảnh. Quy tắc thực tế:

- **Cần đặt tên cho kiểu để ràng buộc nhiều vị trí?** Dùng type parameter `<T>`.
- **Chỉ cần chấp nhận một container của kiểu chưa biết?** Dùng `?` nếu không làm mất ý nghĩa.
- **Chỉ có một kiểu cố định của nghiệp vụ?** Đặt kiểu cụ thể, chẳng hạn `Collection<String>`, đừng tổng quát hóa không cần thiết.

Thiết kế tốt giảm số lượng type variables mà người dùng phải suy luận.

## 5. Quan hệ nguồn–đích: ghi ngay trong chữ ký bằng PECS

Trong Generics, **PECS** là nguyên tắc quen thuộc: *Producer Extends, Consumer Super*.

- Nguồn **sản xuất** các giá trị đọc như `T`: `Iterable<? extends T>`.
- Đích **tiêu thụ** các giá trị `T`: `Collection<? super T>`.

Một API sao chép:

```java
static <T> int copyInto(
        Iterable<? extends T> source,
        java.util.Collection<? super T> destination) {
    int accepted = 0;
    for (T item : source) {
        if (destination.add(item)) {
            accepted++;
        }
    }
    return accepted;
}
```

Với `List<Integer>` làm nguồn và `List<Number>` làm đích:

```java
java.util.List<Integer> integers = java.util.List.of(2, 4, 6);
java.util.List<Number> numbers = new java.util.ArrayList<>();

int accepted = copyInto(integers, numbers); // 3
```

Nếu viết `copyInto(List<T>, List<T>)`, API sẽ gò bó hơn cần thiết vì `List<Integer>` **không phải subtype** của `List<Number>`: generics Java **bất biến**.

### Điều PECS cho phép, và điều nó không hứa

- `? extends T` cho phép đọc những phần tử như `T`; không có nghĩa có thể thêm một `T` bất kỳ vào nguồn qua tham chiếu wildcard.
- `? super T` cho phép thêm `T` vào đích; đọc từ đích nói chung chỉ có thể dùng an toàn như `Object` nếu không biết kiểu chính xác của destination.
- PECS là quy tắc **tương thích kiểu**; nó không chứng minh rằng destination mutable, không cấm null, hoặc rằng `add` chắc chắn trả `true`. Các điểm này cần được tài liệu hóa theo hợp đồng collection cụ thể.

Với một `Set` đích có sẵn phần tử trùng, `add` có thể trả `false`. Do đó ví dụ `copyInto` trả **số lần `destination.add(item)` báo `true`**, không tuyên bố số phần tử nguồn đã duyệt hoặc số phần tử cuối cùng của mọi loại collection.

Nếu API muốn trả số phần tử *đã xử lý*, hãy đặt tên `processedCount` và tăng biến đếm theo mỗi lần duyệt. **Tên kết quả, Javadoc và logic phải khớp nhau.**

## 6. Quan hệ biến đổi: đặt tên `S` và `R` rõ đầu vào/đầu ra

Một phép `map` thường liên hệ **source type** `S` với **result type** `R`:

```java
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper) {
    java.util.List<R> result = new java.util.ArrayList<>();
    for (S item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

Phân tích chữ ký:

- `<S, R>`: hai type parameters độc lập, không yêu cầu `S` là subtype của `R`.
- `Iterable<? extends S>`: nguồn có thể cung cấp các subtype của `S`.
- `Function<? super S, ? extends R>`: callback chấp nhận kiểu phù hợp để xử lý `S` và có kết quả phù hợp để xem như `R`.
- `List<R>`: danh sách kết quả có element type `R`.

Lời gọi:

```java
java.util.List<Integer> ids = java.util.List.of(2, 4);
java.util.List<String> labels = map(ids, id -> "id-" + id);
```

Compiler suy luận mối liên hệ giữa `Integer` và `String` từ biểu thức lambda, target type và chữ ký `map`. Không cần ép kiểu `(List<String>)` hoặc đưa `Object` vào public API.

### Tại sao không chỉ dùng `Function<S,R>`?

`Function<S,R>` cũng hợp lệ nhưng thường **hẹp hơn** `Function<? super S, ? extends R>` trong những API cần nhận callback có kiểu đầu vào rộng hơn hoặc đầu ra hẹp hơn. Tuy nhiên, không nên rải wildcard theo thói quen: wildcard làm chữ ký dài hơn và đôi khi khiến suy luận kiểu/diagnostics phức tạp. Hãy dùng wildcard tại những vị trí API thực sự cần linh hoạt kiểu.

Với một interface đã được thiết kế có type parameters phù hợp, có thể chọn cách ngắn hơn để ưu tiên khả năng sử dụng. **Sự tổng quát phải phục vụ trường hợp sử dụng**, không phải mục tiêu tự thân.

## 7. Upper bounds: tên và Javadoc phải làm rõ ràng buộc

Một generic method cần so sánh các phần tử có thể dùng bound:

```java
static <T extends Comparable<? super T>> java.util.Optional<T>
greatest(Iterable<? extends T> source) {
    T best = null;
    boolean found = false;
    for (T item : source) {
        java.util.Objects.requireNonNull(item, "element");
        if (!found || item.compareTo(best) > 0) {
            best = item;
            found = true;
        }
    }
    return found ? java.util.Optional.of(best)
                 : java.util.Optional.empty();
}
```

`T extends Comparable<? super T>` nói rằng `T` có khả năng so sánh với chính `T` hoặc với một supertype thích hợp. Dạng này hữu ích hơn `Comparable<T>` trong một số mô hình kế thừa, vì một subtype có thể thừa hưởng khả năng so sánh được khai báo ở supertype.

**Đọc chính xác:** `extends` trong type parameter declaration `<T extends ...>` diễn đạt **upper bound**, kể cả bound là interface; `? super T` là **lower-bounded wildcard tại vị trí dùng**, không phải cú pháp khai báo type variable.

Javadoc của `greatest` cần giải thích cả các quyết định ngoài chữ ký:

- Với nguồn rỗng, trả `Optional.empty()` thay vì `null`.
- Với phần tử `null`, ném `NullPointerException`, vì ví dụ cấm null.
- Dựa vào **natural ordering** của từng giá trị `T`.
- Lấy phần tử lớn nhất trong dữ liệu hiện có; không sắp xếp hoặc sửa collection nguồn.
- Chưa cung cấp bảo đảm thread-safe/snapshot cho một nguồn mutable bị sửa đồng thời.

Bound chỉ chứng minh compiler có thể gọi `compareTo` phù hợp. Nó **không tự quyết định** hành vi với empty input hoặc null.

## 8. JavaDoc chuẩn: `@param <T>` khác `@param value`

Javadoc có cú pháp riêng để tài liệu hóa **type parameter**:

```java
/**
 * Creates a box containing one value.
 *
 * @param <T> type of the boxed value
 * @param value value to store; must be non-null
 * @return a box containing {@code value}
 * @throws NullPointerException if {@code value} is null
 */
static <T> Box<T> of(T value) { /* ... */ }
```

Phân biệt:

- `@param <T>`: mô tả **type parameter T** của method/class.
- `@param value`: mô tả **tham số giá trị `value`** của method.
- `@return`: mô tả kết quả và các điều kiện quan trọng của kết quả.
- `@throws` hoặc `@exception`: mô tả lỗi được API cố ý phát ra theo hợp đồng.

Các dấu `<T>` bên trong tag `@param` là **cú pháp Javadoc đặc biệt** cho type parameters. Chúng không tương đương với `@param T` (mô tả một formal parameter tên `T`, nếu có).

Javadoc hỗ trợ dùng `{@code ...}` cho đoạn mã, `{@link ...}` để liên kết API liên quan; sử dụng chúng để làm rõ thuật ngữ nhưng không cần lạm dụng markup.

### Javadoc cho class-level type parameter

```java
/**
 * Stores exactly one value.
 *
 * @param <T> type of the stored value
 */
public final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public T get() {
        return value;
    }
}
```

Nếu class có `<K,V>`, tài liệu hóa **cả hai**:

```java
/**
 * Associates keys with values.
 *
 * @param <K> type of keys used to locate values
 * @param <V> type of values stored in the association
 */
interface Registry<K, V> { /* ... */ }
```

Không chỉ ghi `@param <K> key` khi hợp đồng cần nêu thêm key equality/hash hoặc có cho phép null key không. Quy tắc Java generic `K`/**`V`** không tự mang những semantics đó; tác giả API phải mô tả ở tài liệu tương ứng.

## 9. Javadoc cho quan hệ `S` → `R`

Với `map`, Javadoc nên giải thích các mối liên hệ thay vì chỉ lặp nguyên văn signature:

```java
/**
 * Applies a mapper to each source element, in iteration order.
 *
 * @param <S> source element type
 * @param <R> resulting element type
 * @param source elements to transform; may contain null elements
 * @param mapper transformation applied once to each visited element
 * @return a new mutable list of mapped values, preserving source order
 * @throws NullPointerException if source or mapper is null
 */
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper) {
    java.util.Objects.requireNonNull(source, "source");
    java.util.Objects.requireNonNull(mapper, "mapper");
    java.util.List<R> result = new java.util.ArrayList<>();
    for (S value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Ở ví dụ này, `map` không cấm `null` trong nguồn và không từ chối mapper trả `null`, vì `ArrayList` cho phép null. Do đó tài liệu đúng có thể nói rõ **result may contain null elements** nếu điều này quan trọng với API công khai.

Nếu muốn trả list không sửa được, có thể chọn `List.copyOf(result)` khi hợp đồng cấm null, nhưng cần cập nhật **cả code và Javadoc**, bởi `List.copyOf` từ chối `null` và có semantics snapshot cấu trúc. Đừng mô tả “immutable result” trong Javadoc rồi thực tế trả một `ArrayList` mutable.

### Javadoc không thay thế chú thích wildcard từng ký tự

Không cần giải thích mọi dấu `? extends` và `? super` theo cách máy móc ở mọi method nếu tài liệu cấp module đã có. Thay vào đó, mô tả **vai trò**: nguồn đọc được, callback xử lý, kết quả được tạo mới, đích nhận dữ liệu. Nhưng với API khó hiểu, một `@apiNote` hoặc ví dụ lời gọi `List<Integer>` → `Collection<Number>` có thể giúp người sử dụng hiểu lý do wildcard tồn tại.

## 10. Ví dụ hoàn chỉnh Java 17+: các quan hệ kiểu và tên rõ ràng

Lưu vào **`GenericApiNamingDemo.java`**:

```java
import java.util.*;
import java.util.function.*;

public class GenericApiNamingDemo {
    /** A pair whose first and second components may differ in type. */
    record Pair<A, B>(A first, B second) {}

    /** A container carrying one value of type T. */
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
        }

        /**
         * Builds a box from an input value.
         *
         * @param <U> type of the input and stored value
         * @param value a non-null value
         * @return a box containing the value
         * @throws NullPointerException if value is null
         */
        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }
    }

    /**
     * Sends each element from a source into a destination.
     *
     * @param <T> type accepted from the source
     * @param source elements to read, in iteration order
     * @param destination collection receiving source elements
     * @return number of destination add calls that returned true
     * @throws NullPointerException if source or destination is null
     * @throws UnsupportedOperationException if destination rejects adds
     */
    static <T> int copyInto(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        int accepted = 0;
        for (T item : source) {
            if (destination.add(item)) {
                accepted++;
            }
        }
        return accepted;
    }

    /**
     * Transforms source elements into a new mutable list.
     *
     * @param <S> source element type
     * @param <R> resulting element type
     * @param source values to transform, in iteration order
     * @param mapper function mapping each S into a compatible R
     * @return new mutable list of mapped values in source order
     * @throws NullPointerException if source or mapper is null
     */
    static <S, R> List<R> map(
            Iterable<? extends S> source,
            Function<? super S, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(mapper, "mapper");
        List<R> result = new ArrayList<>();
        for (S value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    /**
     * Finds the greatest value under its natural ordering.
     *
     * @param <T> comparable element type
     * @param source non-null iterable containing no null elements
     * @return greatest element, or Optional.empty() if source is empty
     * @throws NullPointerException if source or any element is null
     */
    static <T extends Comparable<? super T>> Optional<T> greatest(
            Iterable<? extends T> source) {
        Objects.requireNonNull(source, "source");
        T best = null;
        boolean seen = false;
        for (T value : source) {
            Objects.requireNonNull(value, "element");
            if (!seen || value.compareTo(best) > 0) {
                best = value;
                seen = true;
            }
        }
        return seen ? Optional.of(best) : Optional.empty();
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(2, 4, 6);
        List<Number> numbers = new ArrayList<>();

        System.out.println("Copied: " + copyInto(ids, numbers));
        System.out.println("Numbers: " + numbers);

        List<String> labels = map(ids, x -> "id-" + x);
        System.out.println("Mapped: " + labels);

        System.out.println("Greatest: "
                + greatest(ids).orElseThrow());
        System.out.println("Empty maximum: "
                + greatest(List.<Integer>of()));

        Pair<String, Integer> pair = new Pair<>("age", 20);
        System.out.println("Pair: " + pair.first()
                + "=" + pair.second());

        Box<String> box = Box.of("Java");
        System.out.println("Box: " + box.get());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 -Xlint:all GenericApiNamingDemo.java
java GenericApiNamingDemo
```

Standard output:

```text
Copied: 3
Numbers: [2, 4, 6]
Mapped: [id-2, id-4, id-6]
Greatest: 6
Empty maximum: Optional.empty
Pair: age=20
Box: Java
```

Diễn giải về **quan hệ giữa các kiểu**, không chỉ kết quả tính toán:

1. `copyInto` nhận nguồn `List<Integer>` và đích `Collection<Number>`, vì `Integer` phù hợp `Number`. Compiler áp dụng PECS, không cần raw types.
2. `map` nhận các `Integer`, callback tạo `String`, và trả về `List<String>`. Hai type parameters `S` và `R` có vai trò khác nhau.
3. `greatest` dùng `Comparable<? super T>`, trả `Optional<T>`, nên loại dữ liệu đầu ra vẫn liên hệ chặt với đầu vào. Nguồn rỗng nhận `Optional.empty()`.
4. `Pair<A,B>` chỉ ra hai thành phần **có thể có kiểu khác nhau**, không ép chúng vào cùng một `T`.
5. `Box<T>` giữ quan hệ kiểu instance; static factory `Box.of` tự khai báo `U`, tạo box có type argument được suy luận.

Với `copyInto`, hợp đồng không hứa thao tác là **atomic**: nếu collection đích ném exception trong lúc duyệt, các phần tử trước đó có thể đã được thêm. Với nguồn/đích alias nhau hoặc bị sửa đồng thời, cần chính sách sử dụng riêng; ví dụ không hứa sao chép an toàn trên mọi loại collection trong tình huống ấy.

## 11. Phân biệt `T` giống nhau với hai kiểu có quan hệ khác nhau

Xét hai API:

```java
static <T> T choose(T first, T second) {
    return first;
}

static <A, B> Pair<A, B> pair(A first, B second) {
    return new Pair<>(first, second);
}
```

Ở `choose`, cùng type variable `T` cho phép compiler tìm một kiểu `T` phù hợp với cả hai đối số qua type inference. **Điều này không nhất thiết buộc hai object có cùng runtime class.** Ví dụ, khi truyền `String` và `Integer`, compiler có thể suy luận một common supertype phù hợp trong một ngữ cảnh nhất định. Nếu API thật sự yêu cầu “hai phần tử phải đúng cùng runtime class”, một chữ ký `<T> T choose(T,T)` **chưa tự bảo đảm** điều đó.

Ở `pair`, `A` và `B` được giữ độc lập, rõ rằng first và second có thể khác kiểu.

Cẩn trọng với tên `T1`, `T2`: chúng phân biệt các type variables, **không bắt buộc hai kiểu khác nhau**. Caller vẫn có thể sử dụng cùng `String` cho cả `T1` và `T2`. Nên tài liệu hóa vai trò “first component” và “second component”, không viết sai “must be distinct Java types” nếu chữ ký không có khả năng ép điều kiện ấy.

### Khi nào dùng tên `A`, `B`?

Với cấu trúc cặp độc lập `Pair<A,B>`, hai ký hiệu đơn giản, trung tính thường phù hợp. Với cặp khóa/giá trị, `Entry<K,V>` thường rõ nghĩa hơn. Chọn theo **semantics**, không chỉ theo số lượng type parameters.

## 12. Phân biệt upper bound, wildcard và hợp đồng nghiệp vụ

Ba chữ ký có vai trò khác nhau:

```java
static <T extends Number> void acceptNumber(T value) { }

static void readNumbers(List<? extends Number> numbers) { }

static <T> void append(T value, Collection<? super T> target) { }
```

- `<T extends Number>`: khai báo **named type variable** với upper bound; có thể tái sử dụng `T` ở nhiều vị trí trong chữ ký.
- `List<? extends Number>`: một **use-site wildcard**; tham số có thể là list của subtype Number nhưng phần tử chỉ đọc an toàn như `Number`.
- `Collection<? super T>`: wildcard cho consumer; có thể thêm `T`.

Không viết Javadoc dạng “`? extends Number` means every item must have runtime class Number”. Các subtype như `Integer`, `Double` phù hợp ở compile time, còn runtime data vẫn cần đúng invariant generic.

Một upper bound cũng không hàm ý API luôn “nhận mọi subclass” nếu method có thêm điều kiện runtime. Tương tự, wildcard không quyết định null policy: `List<? extends Number>` có thể chứa null nếu backing collection cho phép; type system không mặc định cấm null.

## 13. Quan hệ với callback: input `super`, output `extends`

Một kiểu callback điển hình:

```java
Function<? super T, ? extends R>
```

Nó kết hợp hai vai trò:

- **Tham số đầu vào** của function tiêu thụ một giá trị kiểu `T`: dùng `? super T` để chấp nhận function khai báo nhận một supertype phù hợp.
- **Kết quả** của function cung cấp một giá trị kiểu `R`: dùng `? extends R` để chấp nhận function trả subtype phù hợp.

Ví dụ:

```java
java.util.function.Function<Number, String> describe =
        number -> "n=" + number;

java.util.List<Integer> input = java.util.List.of(1, 2);
java.util.List<CharSequence> output = map(input, describe);
```

Trong một ngữ cảnh target typing phù hợp, `S` có thể là `Integer`, còn `R` là `CharSequence`: `Function<Number,String>` chấp nhận `Integer` như một `Number` và trả `String` là subtype của `CharSequence`. Điều này diễn tả tính linh hoạt mà `Function<S,R>` đúng chính xác có thể không cho phép.

**Nhưng hãy kiểm tra tính dễ dùng:** generics của Java có inference phức tạp khi lồng nhiều wildcard. Nếu người sử dụng thường phải thêm cast/type witness để gọi một API thường nhật, nên cân nhắc overload hoặc thay đổi chữ ký. API rộng nhất về lý thuyết không nhất thiết là API dễ sử dụng nhất.

## 14. Bảo đảm compile time và hợp đồng runtime: phải viết tách riêng

Một chữ ký như:

```java
static <T> void addAll(
        Collection<? extends T> source,
        Collection<? super T> destination)
```

cho compiler biết **quan hệ kiểu giữa các phần tử nguồn và đích**. Nhưng nó không nói:

- Destination có **mutable** và hỗ trợ `add` không?
- `null` có được chấp nhận không?
- Input có thể rỗng không?
- Khi gặp lỗi giữa chừng, destination có thể bị sửa một phần không?
- Thứ tự iteration của nguồn có được giữ lại ở đích không? `Set` có thể sắp xếp/loại bỏ trùng tùy implementation.
- Source và destination có được dùng chung đối tượng/alias không?
- Operation có thread-safe không? Có sao chép snapshot không?

Những điều này thuộc **semantic contract** và nên viết trong Javadoc của API có phạm vi công khai. Ví dụ:

> *Adds each source element to destination in iteration order. This operation may modify destination before throwing. The destination must support additions; null elements must be accepted by its contract.*

Trong README, câu này là **mẫu nội dung giải thích**, không phải lời khẳng định mọi `Collection` chấp nhận null hoặc thứ tự được lưu giữ. Ghi rõ điều kiện và hành vi cụ thể của method đang thiết kế.

### Nullness và generic type arguments

`List<String>` **không có nghĩa non-null list element** trong hệ thống kiểu Java tiêu chuẩn. Nếu API cấm null, ghi rõ trong tài liệu và kiểm tra ở boundary (`Objects.requireNonNull`) hoặc sử dụng một hệ nullness annotation đã được codebase quy định. Đừng dựa vào chữ `String` để suy ra điều compiler không bảo đảm.

### Ownership và mutability

`List<R>` trong chữ ký `map` không nói kết quả mutable hay unmodifiable. Nếu hàm trả `new ArrayList<>()`, Javadoc có thể nêu “new mutable list”; nếu trả `List.copyOf`, cần nêu chính sách null, tính không sửa được của container và bản chất shallow copy. Cập nhật Javadoc cùng lúc khi thay đổi implementation ảnh hưởng public contract.

## 15. Thể hiện lỗi và lựa chọn khi không có dữ liệu

Một method `max` có thể chọn giữa:

```java
static <T extends Comparable<? super T>> T maxNonEmpty(
        Collection<? extends T> elements) { /* ... */ }

static <T extends Comparable<? super T>> Optional<T> maxOptional(
        Collection<? extends T> elements) { /* ... */ }
```

Hai chữ ký cùng mô tả bound kiểu `T`, nhưng khác nhau về **hợp đồng dữ liệu rỗng**.

- `maxNonEmpty` có thể yêu cầu input không rỗng và ném `NoSuchElementException` hoặc `IllegalArgumentException` theo thiết kế.
- `maxOptional` có thể trả `Optional.empty()` nếu input rỗng.

Một README hoặc Javadoc tốt phải nêu chính xác lựa chọn của implementation, không chỉ khẳng định “trả về T lớn nhất”.

Cũng đừng dùng `Optional<T>` để tránh nói rõ null policy: `Optional` không được thiết kế như wrapper chứa `null`; cần quyết định hành vi nếu phần tử nguồn có null.

## 16. Overload, type inference và tên dễ hiểu

Một API “quá generic” có thể làm người gọi khó đọc lỗi compiler:

```java
static <A, B, C, D> D route(A a, B b,
        java.util.function.BiFunction<? super A, ? super B, ? extends C> f,
        java.util.function.Function<? super C, ? extends D> g) {
    return g.apply(f.apply(a, b));
}
```

Dù có thể hợp lệ, người sử dụng phải giải bốn type parameters và nhiều wildcard. Chỉ tạo mức tổng quát đó nếu có use case đáng giá. Nếu luồng nghiệp vụ luôn “parse → validate → save”, các tên class/domain và operation rõ nghĩa thường tốt hơn một hàm `route` bốn kiểu trừu tượng.

Khi method generic trả giá trị theo target type, đôi khi nên dùng biến kết quả có kiểu rõ ràng:

```java
List<String> names = map(List.of(1, 2), x -> "item-" + x);
```

Nếu type inference vẫn gặp khó ở một lời gọi phức tạp, có thể chọn lambda với tham số kiểu rõ hoặc cung cấp type witness phù hợp như `SomeClass.<Integer,String>map(...)`. Nhưng **đừng dùng unchecked cast như cách chữa mặc định**; đó có thể chỉ đẩy lỗi vào runtime.

### Tránh overload chỉ khác tên type parameter

```java
// KHÔNG THỂ cùng khai báo trong một class nếu erasure chữ ký trùng:
static <T> void process(List<T> values) {}
static <U> void process(List<U> values) {}
```

Đổi tên `T` thành `U` không tạo ra overload khác; cả hai có cùng erasure signature. Một public API phải phân biệt overload bằng **thông tin tham số thực sự khác**, không bằng chữ cái của type parameters.

## 17. Viết ví dụ Javadoc để chứng minh tính hữu dụng của wildcard

Với public API truyền dữ liệu từ nguồn sang đích, một ví dụ ngắn có giá trị hơn việc giải thích PECS trừu tượng nhiều lần:

```java
List<Integer> ids = List.of(1, 2);
List<Number> numbers = new ArrayList<>();

int accepted = copyInto(ids, numbers);
```

Nó cho người dùng biết:

- Nguồn `List<Integer>` được chấp nhận mặc dù đích là `List<Number>`.
- Không dùng `List<Object>` làm kiểu đích mặc định nếu không cần.
- `copyInto` ghi vào destination, chứ không tạo list output mới.
- Return value diễn đạt số lần destination chấp nhận phần tử theo hợp đồng của method.

Một Javadoc tốt nên đi kèm **ít nhất một ví dụ với các kiểu có quan hệ subtype** nếu sự linh hoạt của wildcard là tính năng chính. Nếu chỉ thử `List<String>` → `List<String>`, bạn chưa chứng minh ích lợi thực sự của `extends` và `super`.

## 18. Lỗi đặt tên và ghi tài liệu thường gặp

**Lỗi 1 — “Dùng `T` ở mọi vị trí đều là cùng một kiểu.”** Không. Scope của type parameter khác nhau, và type inference có thể chọn common supertype cho nhiều đối số.

**Lỗi 2 — “`E`, `K`, `V` là từ khóa bắt buộc.”** Không. Chúng là quy ước giúp diễn đạt element/key/value.

**Lỗi 3 — “Khi input và output khác nhau, cứ dùng cùng `T`.”** Không. Nếu hai vai trò cần có thể khác kiểu, dùng `<S,R>` hoặc tên tương ứng để giữ hợp đồng đúng.

**Lỗi 4 — “Cứ thêm `<T>` dù không cần vì trông generic hơn.”** Không. Với API chỉ quan sát collection không liên hệ kiểu, `Collection<?>` có thể rõ hơn `<T> Collection<T>`.

**Lỗi 5 — “`List<T>` và `List<? extends T>` tương đương.”** Không. Wildcard cho nguồn có tính linh hoạt về subtype mà dạng invariant không tự có.

**Lỗi 6 — “`? super T` ở nguồn giúp đọc chính xác T.”** Không. Nó thường phù hợp cho **consumer**; khi đọc qua wildcard super, kiểu giá trị an toàn có thể chỉ là `Object`.

**Lỗi 7 — “Javadoc có `@param T` là đủ cho type parameter.”** Không. Type parameter dùng cú pháp `@param <T>`.

**Lỗi 8 — “`@param <T>` thay được việc giải thích null/mutability.”** Không. Tag mô tả vai trò kiểu; semantic contract phải được ghi riêng.

**Lỗi 9 — “Trả `List<R>` tự động đồng nghĩa kết quả là unmodifiable.”** Không. Interface và generic type argument không quyết định mutability.

**Lỗi 10 — “`T extends Number` có nghĩa chỉ nhận runtime Number chính xác.”** Không. Subtype như `Integer` cũng phù hợp theo upper-bound rules.

**Lỗi 11 — “Một `Pair<A,B>` bắt buộc A và B khác nhau.”** Không. Hai type parameters độc lập có thể cùng được gắn với một kiểu.

**Lỗi 12 — “JavaDoc có thể hứa rằng unchecked cast an toàn dù mã không kiểm tra gì.”** Không. Javadoc không khiến một cast kiểm tra type argument bị erasure; hợp đồng cần được thiết kế và chứng minh bởi API.

**Lỗi 13 — “Tên source/destination không quan trọng vì compiler đã kiểm tra.”** Không. Compiler kiểm tra tính hợp lệ kiểu, còn người dùng cần biết **hướng side effects và ownership** để dùng API đúng.

## 19. Bài tập tự kiểm tra

**Câu 1.** Nếu API nhận một giá trị kiểu `T` và trả đúng cùng loại kiểu `T`, dùng `<T>` hay `<S,R>`?

Thường dùng `<T>` để thể hiện quan hệ cùng type variable, miễn đúng hợp đồng thực tế.

**Câu 2.** `Map<K,V>` có buộc key/value là hai runtime classes khác nhau không?

Không. `K` và `V` là hai type parameters độc lập; cùng một type argument có thể gắn cho cả hai.

**Câu 3.** Vì sao `copyInto(Iterable<? extends T>, Collection<? super T>)` chấp nhận `List<Integer>` và `Collection<Number>`?

Nguồn sản xuất `Integer` phù hợp `T`, còn đích có thể tiêu thụ `T` thông qua lower-bounded wildcard; `Integer` là subtype của `Number`.

**Câu 4.** `static <S,R> List<R> map(..., Function<? super S, ? extends R>)` cần giải thích gì trong Javadoc?

Vai trò source/result types, cách mapper được áp dụng, thứ tự duyệt, mutability/copy của kết quả, null policy và exceptions.

**Câu 5.** Tại sao `@param <T>` khác `@param value`?

Một tag mô tả **type parameter**, tag còn lại mô tả **formal value parameter**.

**Câu 6.** Một phương thức chỉ cần `Collection` để log từng phần tử, có nên dùng `<T>` không?

Nếu không cần liên hệ kiểu `T` với kết quả hay tham số khác, `Collection<?>` thường ngắn và diễn đạt chính xác hơn.

**Câu 7.** Khi API trả `Optional<T>`, kiểu có tự nói nguyên nhân empty không?

Không. Javadoc phải giải thích empty nghĩa là không có phần tử, không tìm thấy hay kết quả bị lọc theo một quy tắc nào đó.

**Câu 8.** `<T extends Comparable<? super T>>` đảm bảo gì?

Đảm bảo có khả năng so sánh phù hợp với `T` ở cấp kiểu, cho phép gọi `compareTo` theo hợp đồng. Nó không tự quyết định null policy hoặc hành vi với danh sách rỗng.

**Câu 9.** Nếu method trả `new ArrayList<R>()`, Javadoc nói “unmodifiable list” có đúng không?

Không. `ArrayList` mutable; tài liệu phải khớp việc triển khai hoặc phải thay đổi implementation.

**Câu 10.** Có thể phân biệt hai overload chỉ bằng `<T>` và `<U>` khi parameter types khác nhau duy nhất ở tên type variable không?

Không nếu erased signatures tương đương. Việc đổi tên type variables không tạo overload phân biệt.

## 20. Checklist khi review một generic API

Trước khi công bố/chỉnh sửa một public generic API, kiểm tra:

1. **Tên type parameters:** dùng `E/K/V/T/R/S/U` nhất quán; có cần tên dài hơn để tránh nhầm vai trò không?
2. **Nơi khai báo:** type variable ở class hay method? Có bị che tên bởi `<T>` lồng nhau không?
3. **Quan hệ cùng kiểu:** có giữ được `T` giữa tham số và kết quả, hay vô tình mất thành `Object`?
4. **Nguồn–đích:** wildcard `extends`/`super` có phản ánh chiều đọc/ghi không?
5. **Bound:** có thật sự cần `extends Number`, `Comparable<? super T>` hoặc một interface cụ thể không?
6. **Type inference:** các use case phổ biến gọi method có tự nhiên và dễ chẩn đoán lỗi không?
7. **Javadoc type parameters:** đã có `@param <T>`, `@param <R>` cho mọi type parameter công khai cần tài liệu chưa?
8. **Javadoc value parameters:** tham số tên `source`, `destination`, `mapper`, `comparator` được mô tả đúng vai trò chưa?
9. **Return/exception contracts:** tài liệu có nói rõ empty, null, mutability, ownership, partial failure, aliases và side effects khi quan trọng không?
10. **Ví dụ:** đã có một lời gọi thể hiện quan hệ kiểu thật (ví dụ `Integer` → `Number`, `Integer` → `String`) chưa?
11. **Đồng bộ tài liệu với code:** nếu thay `ArrayList` bằng `List.copyOf`, đổi null policy hoặc chỉ số đếm, Javadoc đã cập nhật chưa?
12. **An toàn trước cast/raw:** có tránh `@SuppressWarnings("unchecked")` làm phương tiện che quan hệ kiểu sai không?

**Kết luận:** Đặt tên type parameters trong Java là một phần của **thiết kế hợp đồng**, không chỉ vấn đề phong cách. Chọn `T` cho một kiểu có quan hệ nhất quán, `E` cho element, `K/V` cho key/value, `S/R` cho source/result khi hữu ích; dùng `? extends` và `? super` để mô tả rõ producer/consumer; khai báo bounds đủ để compiler bảo vệ các thao tác thực sự cần. Sau đó, dùng Javadoc `@param <T>`, `@param`, `@return` và `@throws` để ghi những điều chữ ký chưa thể nói: null, dữ liệu rỗng, mutation, ownership, side effects, partial failure và ý nghĩa của kết quả. Một generic API tốt cho người đọc thấy được **các quan hệ kiểu ngay trong chữ ký**, còn tài liệu làm rõ **hành vi thực tế**.