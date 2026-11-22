# Phương thức generic `static` và các hàm tiện ích trong Java

Trong Java, nhiều thao tác không cần gắn với một đối tượng cụ thể: lấy phần tử đầu tiên của một danh sách, đổi chỗ hai phần tử, tạo một cặp khóa–giá trị, trả lại dữ liệu đầu vào hoặc tìm giá trị lớn nhất. Những thao tác này rất phù hợp với **phương thức generic `static`** (*static generic method*): phương thức có thể áp dụng cho nhiều kiểu dữ liệu, đồng thời compiler vẫn kiểm tra quan hệ kiểu giữa đối số và kết quả.

Bài học đi từ cú pháp `static <T>` đến cách thiết kế một lớp hàm tiện ích, cách Java suy luận đối số kiểu ở mỗi lời gọi, việc khai báo nhiều tham số kiểu, giới hạn kiểu (`bound`), quy tắc với collection, và các sai lầm liên quan đến `static`, raw type, type erasure.

## 1. Một phương thức `static` generic là gì?

Xét phương thức trả lại chính đối tượng được truyền vào:

```java
public static <T> T identity(T value) {
    return value;
}
```

Cách đọc từ trái sang phải:

- `public`: phương thức có thể được gọi từ lớp khác.
- `static`: phương thức thuộc về **lớp khai báo**, nên có thể gọi qua tên lớp mà không cần tạo đối tượng chứa phương thức.
- `<T>`: **khai báo tham số kiểu của riêng phương thức**. Đây là dấu hiệu khiến phương thức trở thành generic.
- `T` đứng trước `identity`: kiểu trả về của phương thức.
- `T value`: kiểu tham số giá trị. Cùng ký hiệu `T` tạo quan hệ “trả ra cùng kiểu đã nhận” theo hợp đồng ở thời điểm biên dịch.

Nếu phương thức được đặt trong lớp `GenericUtils`, có thể gọi:

```java
// Đoạn minh họa nằm trong một phương thức khác:
String language = GenericUtils.identity("Java");
Integer version = GenericUtils.identity(17);
```

Trình biên dịch suy luận `T = String` ở lời gọi đầu và `T = Integer` ở lời gọi sau. Đây là **hai lần sử dụng của cùng một phương thức**; không cần định nghĩa riêng `identity(String)` và `identity(Integer)`.

Phương thức `static` bình thường không có `<T>`:

```java
public static String upper(String value) {
    return value.toUpperCase();
}
```

Phương thức này chỉ nhận `String` nên không phải phương thức generic.

Điểm khác biệt chính nằm ở **khai báo tham số kiểu của phương thức** và cách tham số đó liên kết những vị trí trong chữ ký, chứ không nằm riêng ở từ khóa `static`.

## 2. Vị trí chính xác của `<T>` trong khai báo phương thức

Cú pháp tổng quát:

```java
[modifiers] <TypeParameters> ReturnType methodName(parameters) {
    // body
}
```

Đây là **mẫu cú pháp**, không phải một đoạn Java biên dịch độc lập. Với một phương thức `static` cụ thể:

```java
static <T> T first(T a, T b) {
    return a;
}
```

Những hình thức khác cũng hợp lệ:

```java
static <T> void consume(T item) {
    System.out.println(item);
}

static <K, V> String describe(K key, V value) {
    return key + "=" + value;
}

static <N extends Number> double twice(N value) {
    return value.doubleValue() * 2;
}
```

Cả ba là **phương thức minh họa**, cần đặt trong thân một lớp hoặc record hợp lệ.

| Cú pháp | Ý nghĩa |
|---|---|
| `static <T> T first(T a, T b)` | Một tham số kiểu `T`; kết quả và hai đối số liên hệ qua `T`. |
| `static <T> void consume(T item)` | Phương thức vẫn generic dù trả về `void`. |
| `static <K,V> String describe(K key,V value)` | Hai tham số kiểu độc lập, kết quả là `String`. |
| `static <N extends Number> double twice(N value)` | `N` phải thỏa giới hạn kiểu `Number`. |

Không thể bỏ `<T>` rồi viết `static T identity(T x)` nếu `T` chưa được khai báo hợp lệ trong phạm vi phương thức. Việc có chữ `T` ở tham số hoặc giá trị trả về không tự động khai báo tham số kiểu.

Trong lời khai báo, danh sách `<T>` phải đứng **trước kiểu trả về** và sau các modifier như `public static`. Với phương thức generic, `<T>` thuộc về phương thức ấy, khác với `class Box<T>` vốn khai báo tham số kiểu cho cả lớp.

## 3. Lớp tiện ích: vì sao thường dùng `final` và constructor `private`?

Một lớp tập hợp các hàm `static` dùng chung có thể có dạng:

```java
public final class GenericUtils {
    private GenericUtils() {
        throw new AssertionError("Utility class");
    }

    public static <T> T identity(T value) {
        return value;
    }
}
```

Đây là lớp hoàn chỉnh nhưng mới có một phương thức. Những quyết định thiết kế:

1. `public final class`: lớp là nơi chứa các hàm tiện ích, không dự kiến mở rộng bằng kế thừa.
2. Constructor `private`: mã bên ngoài không thể tạo đối tượng `GenericUtils` chỉ để gọi các hàm `static`; thông báo lỗi trong constructor giúp bảo vệ ý định nếu có lời gọi không mong muốn từ chính bên trong lớp.
3. Phương thức `static`: gọi bằng `GenericUtils.identity(...)`, không cần đối tượng `new GenericUtils()`.
4. Tham số kiểu `<T>`: phạm vi nằm ở từng phương thức. **Không cần** khai báo `class GenericUtils<T>` để viết các utility method generic.

Đây là **quy ước thiết kế**, không phải một quy tắc bắt buộc của ngôn ngữ. Một lớp ứng dụng có trạng thái vẫn có thể chứa phương thức generic `static`. Chỉ dùng kiểu utility class khi các thao tác thực sự không phụ thuộc trạng thái của đối tượng.

## 4. Một bộ hàm tiện ích Java 17 hoàn chỉnh

Hãy tạo tệp **`GenericUtils.java`**:

```java
import java.util.List;
import java.util.Map;

public final class GenericUtils {
    private GenericUtils() {
        throw new AssertionError("Utility class");
    }

    // Giữ quan hệ kiểu giữa đầu vào và kết quả.
    public static <T> T identity(T value) {
        return value;
    }

    // Tạo danh sách một phần tử, không cho phép phần tử null.
    public static <T> List<T> only(T value) {
        return List.of(value);
    }

    // Chấp nhận danh sách chứa T hoặc kiểu con của T, chỉ đọc.
    public static <T> T firstOrThrow(List<? extends T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return items.get(0);
    }

    // Hoán đổi phần tử trong danh sách có thể chỉnh sửa.
    public static <T> void swap(List<T> items, int left, int right) {
        T previous = items.get(left);
        items.set(left, items.get(right));
        items.set(right, previous);
    }

    // So sánh theo thứ tự tự nhiên.
    public static <T extends Comparable<? super T>> T maximum(
            List<? extends T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }

        T best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            T candidate = items.get(i);
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    // Hai tham số kiểu độc lập.
    public static <K, V> Map.Entry<K, V> entry(K key, V value) {
        return Map.entry(key, value);
    }
}
```

Đây là một **lớp tiện ích thực sự có thể biên dịch trên Java 17**. Các phương thức không giữ trạng thái và không cần tạo instance `GenericUtils`.

### Cách chạy và kết quả

Tạo thêm tệp **`GenericUtilsDemo.java`** cùng thư mục:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class GenericUtilsDemo {
    public static void main(String[] args) {
        String name = GenericUtils.identity("spring");
        Integer count = GenericUtils.identity(7);
        List<String> one = GenericUtils.only("lesson");
        String first = GenericUtils.firstOrThrow(
                List.of("core", "generics"));

        List<String> colors = new ArrayList<>(
                List.of("red", "blue"));
        GenericUtils.swap(colors, 0, 1);

        Integer biggestNumber = GenericUtils.maximum(
                List.of(9, 4, 11));
        String biggestWord = GenericUtils.maximum(
                List.of("Go", "Java", "Kotlin"));

        Map.Entry<String, Integer> version =
                GenericUtils.entry("JDK", 17);

        System.out.println(name.toUpperCase());
        System.out.println(count);
        System.out.println(one);
        System.out.println(first);
        System.out.println(colors);
        System.out.println(biggestNumber);
        System.out.println(biggestWord);
        System.out.println(version.getKey() + "=" + version.getValue());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GenericUtils.java GenericUtilsDemo.java
java GenericUtilsDemo
```

`stdout`:

```text
SPRING
7
[lesson]
core
[blue, red]
11
Kotlin
JDK=17
```

Vì `List.of(...)` trả về danh sách không thể chỉnh sửa cấu trúc hoặc phần tử qua `set`, ví dụ tạo `new ArrayList<>(...)` trước khi gọi `swap`. Nếu truyền trực tiếp `List.of("red", "blue")` vào `swap` thì compiler vẫn có thể chấp nhận kiểu `List<String>`, nhưng chương trình sẽ ném `UnsupportedOperationException` khi gọi `set`. **Generics kiểm tra kiểu phần tử, không bảo đảm collection có thể sửa đổi.**

Các tiện ích `only` và `entry` sử dụng `List.of` và `Map.entry` trong JDK. Hai factory này không nhận đối số `null` và tạo đối tượng không sửa đổi được theo cách tương ứng; nếu truyền `null`, lời gọi có thể ném `NullPointerException`. Cần thể hiện rõ các điều kiện đầu vào trong API thay vì mặc định chúng được generics kiểm tra.

## 5. Mỗi lời gọi suy luận đối số kiểu thế nào?

Khi thấy:

```java
String text = GenericUtils.identity("Java");
Integer number = GenericUtils.identity(42);
```

trình biên dịch phân tích chữ ký `<T> T identity(T value)` cùng kiểu của đối số và **kiểu đích** nơi kết quả được sử dụng. Trong hai ví dụ, nó suy luận `T` lần lượt là `String` và `Integer`.

Ta có thể chỉ định đối số kiểu tường minh bằng **type witness**:

```java
String text = GenericUtils.<String>identity("Java");
Integer number = GenericUtils.<Integer>identity(42);
```

Dấu `<String>` được đặt **ngay trước tên phương thức**, sau dấu chấm của tên lớp. Cú pháp này khác với `new Box<String>(...)` của constructor và khác `new Box<>(...)` dùng diamond.

Một ví dụ có lỗi:

```java
// Integer broken = GenericUtils.<Integer>identity("Java");
```

Đây là mã lỗi được chú thích: nếu ép `T = Integer` một cách tường minh mà vẫn truyền chuỗi, compiler từ chối vì `String` không tương thích với tham số `Integer`.

### Khi nào nên viết type witness?

Hầu hết trường hợp **không cần** vì Java suy luận được kiểu. Type witness giúp minh họa hoặc làm rõ một lời gọi có ngữ cảnh suy luận phức tạp, đặc biệt khi có nhiều tham số generic, method overload hay type bound. Không nên viết type witness ở mọi lời gọi chỉ để lặp thông tin compiler đã biết.

Ví dụ một giá trị có kiểu rộng:

```java
Object value = "Java";
Object same = GenericUtils.identity(value);
```

Tại điểm gọi, **kiểu tĩnh** của `value` là `Object` nên quan hệ kiểu suy luận theo `Object`; phương thức không tự nhận ra đây chắc chắn là `String` chỉ vì đối tượng lúc chạy có lớp `String`.

## 6. Phân biệt tham số kiểu của lớp và của phương thức `static`

Một lớp generic có tham số kiểu riêng:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` được gắn với **một cách tham số hóa của lớp**, chẳng hạn `Box<String>`. Phương thức `static` lại thuộc về **lớp khai báo**, không thuộc riêng `Box<String>` hay `Box<Integer>`. Vì thế, trong lớp generic không thể dùng trực tiếp `T` của lớp ở một thành phần `static`:

```java
// Minh họa các khai báo sai khi đặt trong class Box<T>:
// private static T shared;
// static T readShared() { return null; }
```

Để xây dựng một phương thức tạo hộp `static`, khai báo **tham số kiểu riêng** cho phương thức:

```java
static <U> Box<U> of(U value) {
    return new Box<>(value);
}
```

Ở đây `<U>` thuộc về phương thức `of`, còn `Box<U>` mô tả kiểu trả về. Lớp không cần dùng chính ký hiệu `U`; một tên như `TValue` cũng hợp lệ miễn dùng nhất quán.

### Factory method chạy được

Tạo tệp **`StaticFactoryDemo.java`**:

```java
public class StaticFactoryDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }
    }

    public static void main(String[] args) {
        Box<String> language = Box.of("Java");
        Box<Integer> year = Box.of(2026);

        System.out.println(language.get().toUpperCase());
        System.out.println(year.get() + 1);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StaticFactoryDemo.java
java StaticFactoryDemo
```

`stdout`:

```text
JAVA
2027
```

Phương thức `of` có thể tạo `Box<String>` hay `Box<Integer>` từ cùng một định nghĩa. Đây là trường hợp quen thuộc của **generic static factory method**. Với thiết kế thư viện, phương thức factory còn có thể kiểm tra đầu vào, trả về các implementation khác nhau hoặc tái sử dụng đối tượng khi hợp đồng cho phép; những hành vi đó phải được cài đặt rõ, không tự đến từ tính generic.

## 7. Phương thức tiện ích có nhiều tham số kiểu

Không phải mọi tiện ích chỉ cần `T`. Để tạo cặp khóa–giá trị:

```java
public static <K, V> Map.Entry<K, V> entry(K key, V value) {
    return Map.entry(key, value);
}
```

`<K, V>` **khai báo hai tham số kiểu độc lập**. Với `GenericUtils.entry("JDK", 17)`:

- `K` tương ứng với `String`.
- `V` tương ứng với `Integer`.
- Kiểu trả về là `Map.Entry<String, Integer>`.

Tại đây `Map.Entry` là interface lồng trong API `java.util.Map`, có thể dùng làm đối tượng kết quả cho một cặp khóa–giá trị. Factory `Map.entry(...)` của JDK trả một entry không sửa đổi được bằng `setValue` và không cho phép khóa hoặc giá trị `null`.

Nếu tiện ích chỉ dùng một kiểu cho cả hai đối số:

```java
public static <T> boolean sameReference(T left, T right) {
    return left == right;
}
```

đây là **đoạn phương thức minh họa**, trả về so sánh **cùng tham chiếu**, không phải so sánh nội dung như `Objects.equals`. Compiler có thể suy luận một kiểu cha chung cho hai đối số khác kiểu; việc dùng cùng một chữ `T` không tự bảo đảm hai đối tượng cùng lớp runtime.

Chỉ tạo nhiều tham số kiểu khi cần biểu đạt **quan hệ kiểu có ý nghĩa**. Không cần generic nếu hàm không truyền hay dùng thông tin kiểu:

```java
public static int countCharacters(String text) {
    return text.length();
}
```

Hàm trên chỉ xử lý `String`; biến nó thành generic không đem lại lợi ích tự nhiên.

## 8. Ràng buộc kiểu cho thuật toán cần khả năng so sánh

Một phương thức `identity(T)` không yêu cầu thao tác riêng của `T`. Nhưng thuật toán tìm giá trị lớn nhất cần một cách so sánh. Chữ ký trong `GenericUtils`:

```java
public static <T extends Comparable<? super T>> T maximum(
        List<? extends T> items)
```

Đây là **chữ ký minh họa**, thân phương thức đã có trong tệp `GenericUtils.java`.

Các thành phần:

1. `<T extends Comparable<? super T>>` là một **bounded type parameter**: kiểu `T` phải có khả năng so sánh với giá trị kiểu `T` thông qua hợp đồng `Comparable` phù hợp.
2. `List<? extends T>` cho phép phương thức **đọc** các giá trị có kiểu phù hợp với `T`. Nó không cho phép tự do thêm một `T` tùy ý vào danh sách nguồn.
3. `T maximum(...)` trả về giá trị theo kiểu `T` mà compiler có thể xác định từ ngữ cảnh lời gọi.
4. `candidate.compareTo(best) > 0` thể hiện thứ tự tự nhiên được chính kiểu đối tượng cung cấp.

Ví dụ:

```java
Integer largest = GenericUtils.maximum(List.of(3, 8, 5));
String latest = GenericUtils.maximum(
        List.of("Alpha", "Beta", "Gamma"));
```

Đoạn nằm trong một phương thức và sử dụng tệp `GenericUtils.java` ở trên; cần import `java.util.List`. `largest` là `8`, `latest` là `"Gamma"` theo thứ tự từ điển của `String.compareTo`. Nếu dùng một loại đối tượng không triển khai quan hệ `Comparable` thích hợp, compiler không chấp nhận lời gọi theo chữ ký này.

### Trường hợp không có thứ tự tự nhiên

Nếu kiểu dữ liệu không có `Comparable` hoặc người dùng muốn một quy tắc thứ tự khác, tiện ích có thể nhận **`Comparator<? super T>`** thay vì bắt `T` có thứ tự tự nhiên:

```java
import java.util.Comparator;
import java.util.List;

public final class ComparisonUtils {
    private ComparisonUtils() { }

    public static <T> T maximumBy(
            List<? extends T> items,
            Comparator<? super T> comparator) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }

        T best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            T candidate = items.get(i);
            if (comparator.compare(candidate, best) > 0) {
                best = candidate;
            }
        }
        return best;
    }
}
```

Đây là lớp đầy đủ trong **`ComparisonUtils.java`**, độc lập với các ví dụ khác. Ví dụ gọi nằm trong một phương thức sau khi import `java.util.List` và `java.util.Comparator`:

```java
String longest = ComparisonUtils.maximumBy(
        List.of("A", "Java", "Code"),
        Comparator.comparingInt(String::length));
```

`longest` có giá trị `"Java"`: cả `"Java"` và `"Code"` đều dài 4 ký tự, nhưng thuật toán chỉ thay `best` khi giá trị so sánh **lớn hơn** (không thay khi bằng), vì vậy phần tử xuất hiện trước được giữ lại.

Đây vẫn là một **static generic utility** với tham số kiểu `<T>`. Việc dùng `Comparator` tách **thuật toán** ra khỏi **quy tắc so sánh**, phù hợp với các tiện ích có thể tái sử dụng.

## 9. Kiểu ở nơi đọc và nơi ghi: vì sao utility nên nghĩ tới wildcard?

Xét hai thao tác khác nhau:

- `firstOrThrow(List<? extends T>)` chỉ cần **đọc** một phần tử và trả về `T`.
- `swap(List<T>, int, int)` cần cả đọc và **ghi trở lại** các phần tử cùng danh sách.

Trong utility đầu, wildcard `? extends T` diễn đạt một nguồn chỉ cần cung cấp các giá trị thuộc `T` hoặc kiểu con. Trong utility thứ hai, ta dùng `List<T>` để đọc và đặt lại các giá trị đúng cùng một kiểu đã liên kết với danh sách.

Một phương thức chép phần tử từ nguồn sang đích có thể dùng nguyên tắc thường nhớ là **PECS: Producer Extends, Consumer Super**:

```java
public static <T> void copyAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

Đây là **đoạn phương thức minh họa**, phải khai báo trong lớp hợp lệ và import `java.util.List`. Ví dụ:

```java
List<Integer> numbers = List.of(1, 2, 3);
List<Number> output = new ArrayList<>();

copyAll(numbers, output);
System.out.println(output); // [1, 2, 3]
```

Đoạn trên cần nằm trong một phương thức của lớp chứa `copyAll`, đồng thời import `List` và `ArrayList`. `source` cung cấp `Integer`, còn `target` chấp nhận `Number`. Về trách nhiệm của utility, việc gắn quan hệ kiểu bằng `<T>` giúp compiler kiểm tra điều kiện tương thích mà không yêu cầu người gọi ép kiểu.

Không nên áp dụng wildcard máy móc. Nếu API cần chính xác một kiểu `T` ở nhiều vị trí, `List<T>` có thể rõ ràng hơn; nếu chỉ cần đọc hoặc chỉ cần ghi theo quan hệ phân cấp, wildcard giúp mở rộng phạm vi sử dụng hợp lệ.

## 10. Java đã có nhiều generic static utility

Trước khi viết lại một tiện ích, kiểm tra JDK có cung cấp sẵn không:

| API | Ví dụ sử dụng | Công dụng |
|---|---|---|
| `Collections.emptyList()` | `List<String> xs = Collections.emptyList();` | Danh sách rỗng có kiểu phần tử được suy luận; không thể sửa đổi. |
| `Collections.singletonList("x")` | `List<String> xs = Collections.singletonList("x");` | Danh sách một phần tử, không thể sửa đổi. |
| `List.of("a", "b")` | `List<String> xs = List.of("a", "b");` | Factory tạo danh sách không thể sửa đổi; từ chối phần tử `null`. |
| `Map.entry("k", 1)` | `Map.Entry<String, Integer> e = Map.entry("k", 1);` | Tạo entry theo hai đối số kiểu được suy luận. |
| `Comparator.comparingInt(...)` | `Comparator<String> c = Comparator.comparingInt(String::length);` | Tạo comparator từ hàm lấy khóa số nguyên. |
| `Optional.ofNullable(x)` | `Optional<String> o = Optional.ofNullable(x);` | Tạo optional có hoặc không có giá trị, cho phép đầu vào `null`. |

Các lời gọi trong bảng là **đoạn mã minh họa bên trong một phương thức**, với những import cần thiết từ `java.util`. Đây là các factory hoặc utility API của JDK, nhiều phương thức tự khai báo tham số kiểu nên tự suy luận được ở điểm gọi.

Lưu ý: `List.of(...)` và `Map.entry(...)` xuất hiện từ Java 9, nên có sẵn trong Java 17. Các tiện ích có thể trả về cấu trúc **không sửa đổi được**, chứ không phải mọi collection từ factory đều có thể thêm/xóa/sắp xếp tại chỗ. Hãy đọc hợp đồng mutability của API trước khi sử dụng.

## 11. Phương thức generic `static` và method reference

Một phương thức generic `static` cũng có thể được sử dụng thông qua **method reference** nếu ngữ cảnh cung cấp kiểu hàm mục tiêu.

Tạo tệp **`MethodReferenceDemo.java`**:

```java
import java.util.function.Function;

public class MethodReferenceDemo {
    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        Function<String, String> textIdentity =
                MethodReferenceDemo::identity;
        Function<Integer, Integer> numberIdentity =
                MethodReferenceDemo::identity;

        System.out.println(textIdentity.apply("Java"));
        System.out.println(numberIdentity.apply(17) + 1);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MethodReferenceDemo.java
java MethodReferenceDemo
```

`stdout`:

```text
Java
18
```

`Function<String, String>` và `Function<Integer, Integer>` là **hai kiểu đích khác nhau** cho cùng một method reference `MethodReferenceDemo::identity`. Trình biên dịch dựa vào kiểu đích để suy luận tham số kiểu của lần sử dụng tương ứng.

Một tiện ích generic hữu ích khi nhiều nơi gọi có các kiểu dữ liệu khác nhau nhưng vẫn chia sẻ được quy tắc tính toán. Tuy nhiên, không nên dùng generic để che mất nghĩa nghiệp vụ: ví dụ một phương thức thực sự chỉ hỗ trợ chuỗi thì chữ ký `String` cụ thể thường rõ hơn `<T>` kết hợp ép kiểu.

## 12. Giới hạn và lỗi thường gặp

### 12.1. `static` không được dùng tham số kiểu của instance class

Sai:

```java
class Box<T> {
    // static T cached;               // Sai
    // static T createDefault() { ... } // Sai
}
```

Một phương thức `static` cần khai báo tham số kiểu của chính nó (như `static <U> Box<U> of(U x)`) hoặc làm việc với kiểu cụ thể. Nguyên nhân không phải do thiếu constructor, mà vì `T` của `Box<T>` thuộc về phần kiểu của mỗi lần sử dụng lớp, còn thành phần `static` không gắn với một lần tham số hóa duy nhất.

### 12.2. Không thể tạo đối tượng từ `new T()` hoặc mảng trực tiếp `new T[n]`

Do Java dùng type erasure, phương thức generic không biết constructor của `T` chỉ nhờ tham số kiểu:

```java
// Trong một phương thức khai báo <T>:
// T object = new T();  // Không hợp lệ
// T[] values = new T[3]; // Không hợp lệ
```

Nếu thực sự cần tạo đối tượng kiểu `T`, có thể nhận một factory như `Supplier<? extends T>` từ người gọi. Ví dụ phương thức:

```java
public static <T> T create(
        java.util.function.Supplier<? extends T> factory) {
    return factory.get();
}
```

Phương thức trên cần đặt trong một lớp; người dùng cung cấp constructor reference hoặc lambda có thể tạo kiểu thích hợp. Các vấn đề liên quan tới tạo mảng generic thường cần xử lý thông qua mảng kiểu có thể kiểm tra runtime, API collection hoặc factory phù hợp; không nên ép kiểu mảng không được kiểm tra chỉ để tránh lỗi biên dịch.

### 12.3. Trùng chữ ký sau type erasure

Hai phương thức sau **không thể cùng khai báo** trong một lớp:

```java
// Ví dụ lỗi, không đặt vào mã chạy:
static <T> void show(T value) { }
static void show(Object value) { }
```

Vì `T` không có bound bị xóa về `Object`, hai chữ ký JVM trùng nhau sau *type erasure*. Một ví dụ khác:

```java
// Ví dụ lỗi: cả hai cùng erasure theo List.
static void process(List<String> input) { }
static void process(List<Integer> input) { }
```

Compiler phát hiện **name clash**. Muốn xử lý theo nhiều loại dữ liệu, hãy chọn chữ ký API không xung đột, tên phương thức khác hoặc thiết kế generic phù hợp. Không thể dùng mỗi đối số kiểu generic khác nhau làm tiêu chí overload ở runtime.

### 12.4. `List.of(...)` không thể dùng cho utility sửa đổi danh sách

```java
// GenericUtils.swap(List.of("A", "B"), 0, 1);
```

Dòng trên hợp lệ về **quan hệ kiểu**, nhưng khi thực thi sẽ ném `UnsupportedOperationException` do danh sách không hỗ trợ `set`. Để dùng `swap` ở ví dụ này, hãy tạo danh sách có thể sửa đổi:

```java
List<String> values = new ArrayList<>(List.of("A", "B"));
GenericUtils.swap(values, 0, 1);
```

Hai dòng cần import `List` và `ArrayList`, đồng thời chạy với lớp `GenericUtils` đã định nghĩa. Generic chỉ bảo đảm quan hệ kiểu, không bảo đảm mutability hay tính hợp lệ của chỉ số. Nếu `left` hoặc `right` ngoài biên, `get`/`set` ném `IndexOutOfBoundsException`.

### 12.5. Primitive và `null` vẫn cần lưu ý

Không thể dùng `<int>` làm đối số kiểu vì primitive không hợp lệ ở generic; thông thường dùng `Integer` và Java tự boxing/unboxing.

Còn `identity(null)` có thể hợp lệ khi compiler suy luận được kiểu phù hợp, và `identity` sẽ trả lại `null`. Ngược lại, `only(null)` sử dụng `List.of(null)` nên ném `NullPointerException`. Hai phương thức cùng generic nhưng **chính phần cài đặt và hợp đồng API** quyết định chúng xử lý `null` thế nào.

### 12.6. Raw type và ép kiểu không an toàn

Mã sử dụng `List` raw hoặc cast không được kiểm tra có thể phá ràng buộc phần tử, làm xuất hiện `ClassCastException` khi đọc. Nên biên dịch với những cảnh báo phù hợp, chẳng hạn:

```bash
javac -Xlint:rawtypes,unchecked GenericUtils.java GenericUtilsDemo.java
```

Lệnh này không thay đổi cách utility vận hành; nó yêu cầu compiler thông báo rõ hơn về các thao tác generic không an toàn nếu có.

## 13. Quy trình thiết kế một generic static utility

Khi muốn viết hàm dùng lại cho nhiều kiểu, có thể đi theo thứ tự:

1. **Xác định thao tác độc lập trạng thái:** ví dụ đọc phần tử đầu, đổi chỗ, tạo cặp, tìm giá trị lớn nhất.
2. **Xác định quan hệ kiểu trong API:** dữ liệu đầu vào và đầu ra dùng cùng `T`, hay phải có hai tham số `<K,V>`?
3. **Đặt `<T>` trước kiểu trả về:** `static <T> T identity(T value)`. Nếu phương thức trả `void` vẫn khai báo `<T>`.
4. **Thêm bound khi thuật toán thật sự cần:** `<T extends Comparable<? super T>>` cho thứ tự tự nhiên; đừng thêm bound tùy tiện.
5. **Xét chiều đọc/ghi của collection:** dùng `? extends T` cho nguồn đọc, `? super T` cho đích nhận dữ liệu khi phù hợp.
6. **Đưa điều kiện runtime vào hợp đồng:** danh sách có rỗng không, có sửa đổi được không, chỉ số có hợp lệ không, giá trị có được `null` không?
7. **Ưu tiên API JDK đã có:** `Collections`, `List.of`, `Map.entry` hoặc các tiện ích khác trước khi viết bản sao.
8. **Giữ chữ ký đơn giản và kiểm tra compiler:** tránh raw type, cast không kiểm tra và overload xung đột sau erasure.
9. **Dùng tên lớp khi gọi:** `GenericUtils.swap(...)` nói rõ phương thức thuộc lớp tiện ích, giúp mã dễ tìm và bảo trì.

Không cần chuyển mọi phương thức `static` thành generic. Nếu hàm chỉ xử lý `String` hoặc `int` theo nghiệp vụ riêng, một chữ ký kiểu cụ thể có thể đúng và dễ hiểu hơn.

## 14. Tự kiểm tra

**Câu 1.** Trong chữ ký `static <T> T identity(T value)`, tại sao có cả `<T>` lẫn `T` đứng trước tên phương thức?

**Câu 2.** Vì sao `GenericUtils.identity("Java")` và `GenericUtils.identity(42)` dùng cùng một định nghĩa phương thức mà kết quả có kiểu tĩnh khác nhau?

**Câu 3.** Với `class Holder<T>`, tại sao không thể khai báo `static T value;` nhưng có thể khai báo `static <U> Holder<U> of(U value)`?

**Câu 4.** Lợi ích của chữ ký `copyAll(List<? extends T> source, List<? super T> target)` là gì?

**Câu 5.** Tại sao `GenericUtils.swap(List.of("a", "b"), 0, 1)` gây lỗi khi chạy, dù Java Generics chấp nhận kiểu `List<String>`?

**Câu 6.** Vì sao `static <T> void show(T value)` và `static void show(Object value)` không thể cùng tồn tại trong một lớp?

**Gợi ý đáp án:** (1) `<T>` khai báo tham số kiểu của phương thức, `T` trước tên là kiểu trả về. (2) Java suy luận `T` riêng cho từng lời gọi dựa trên đối số và ngữ cảnh. (3) Thành phần `static` không thuộc một cách tham số hóa cụ thể của lớp; `<U>` là tham số kiểu độc lập của factory. (4) Diễn đạt mối quan hệ kiểu cho phép chép từ nguồn cung cấp `T` sang đích chấp nhận `T`, kể cả qua quan hệ kiểu cha–con hợp lệ. (5) `List.of` tạo danh sách không sửa đổi được; generic không đảm bảo hỗ trợ `set`. (6) Sau type erasure, `T` không bị ràng buộc được xóa về `Object`, gây trùng chữ ký.

**Ghi nhớ:** Một phương thức generic `static` kết hợp **hàm không phụ thuộc instance** với **kiểm tra quan hệ kiểu ở compile time**. Cú pháp `static <T>` cho phép mỗi lời gọi dùng kiểu phù hợp mà không phải tạo lớp hoặc overload riêng; chất lượng của utility nằm ở một hợp đồng kiểu rõ ràng, điều kiện runtime minh bạch và khả năng tái sử dụng mà không đánh mất an toàn kiểu.
