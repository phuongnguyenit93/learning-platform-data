# Type inference, diamond operator và chọn kiểu tham số trong Java 27

Trong chương **Generics và hệ thống kiểu** của Java 27, một kỹ năng quan trọng là viết mã generic **đủ an toàn về kiểu nhưng không lặp lại những thông tin mà compiler đã biết**. Java có thể suy luận kiểu khi gọi phương thức generic, khởi tạo lớp generic bằng toán tử **diamond** (`<>`), và khai báo biến cục bộ bằng `var`. Cả ba đều là cơ chế **xác định kiểu tại thời điểm biên dịch**, không phải kiểu động.

Tuy nhiên, khả năng suy luận có giới hạn: kết quả còn phụ thuộc vị trí biểu thức, các đối số, kiểu đích (*target type*), ràng buộc generic và overload. Một `var` hoặc diamond đặt sai chỗ có thể làm kiểu bị suy luận rộng thành `Object`; còn một tham số kiểu `<T>` được thêm vào API không đúng mục đích có thể khiến người dùng khó hiểu hơn.

Bài này áp dụng các quy tắc hiện hành của **Java SE 27**, sử dụng các API hiện đại như `List.of`, `List.copyOf`, record, stream, method reference và tránh raw type/unchecked cast nếu không thực sự cần thiết.

## 1. Phân biệt type parameter, type argument và type inference

Ba thuật ngữ có liên quan nhưng không đồng nghĩa:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Type parameter** | Biến kiểu do lớp, interface hoặc phương thức khai báo | `<T>` trong `class Box<T>` |
| **Type argument** | Kiểu cụ thể truyền vào chỗ type parameter | `<String>` trong `Box<String>` |
| **Type inference** | Compiler suy ra type argument/kiểu biểu thức từ ràng buộc và ngữ cảnh | `new Box<>("Hi")`, `List.of(1, 2)` |

Ví dụ:

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

Box<String> greeting = new Box<>("Hello");
String text = greeting.get();
```

`T` được khai báo tại `Box<T>`. Trong `Box<String>`, type argument là `String`. Cú pháp `new Box<>("Hello")` để compiler suy ra type argument của **lời gọi constructor** thay vì viết lại `new Box<String>(...)`.

**Quan trọng:** Sau khi suy luận, `greeting` vẫn có kiểu tĩnh `Box<String>`; việc dùng diamond không khiến Java kiểm tra kiểu lúc chạy như một ngôn ngữ dynamic. Compiler vẫn từ chối `greeting = new Box<>(42)` vì kiểu không tương thích.

### 1.1. Sơ đồ tư duy

```text
Khai báo kiểu / phương thức generic
          │
          ├── T, K, V, E, R: các type parameter
          │
          v
Lời gọi hoặc biểu thức tạo đối tượng
          │
          ├── Type argument được ghi rõ: <String>
          └── Type argument được suy luận: <>, lời gọi generic method
          │
          v
Compiler tính ràng buộc + xem ngữ cảnh cần thiết
          │
          v
Kiểu tĩnh của biểu thức được xác định
```

## 2. Type inference khi gọi phương thức generic

Một phương thức generic tự khai báo các type parameter, ngay trước kiểu trả về:

```java
import java.util.List;

public class GenericMethodExample {
    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("List must not be empty");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        String name = first(List.of("An", "Bình"));
        Integer id = first(List.of(101, 102));

        System.out.println(name); // An
        System.out.println(id);   // 101
    }
}
```

Compiler suy ra `T = String` trong lời gọi thứ nhất và `T = Integer` trong lời gọi thứ hai. Không cần viết `GenericMethodExample.<String>first(...)` hay `GenericMethodExample.<Integer>first(...)`.

Một generic method có thể được khai báo bên trong lớp không generic; ngược lại, một lớp generic vẫn có thể khai báo generic method với **type parameter riêng**.

### 2.1. Những thông tin compiler dùng để suy luận

Type inference khi gọi phương thức có thể dựa vào:

1. **Kiểu đối số** được truyền vào, bao gồm ràng buộc từ generic argument khác.
2. **Khai báo phương thức**, giới hạn trên của type parameter (`extends`) và quan hệ giữa các tham số.
3. **Ngữ cảnh đích** trong những trường hợp lời gọi là *poly expression*, ví dụ vế phải của phép gán, `return`, hoặc một đối số của lời gọi khác.
4. **Quy tắc overload**, boxing/unboxing, lambda và method reference nếu có.

Không phải biểu thức Java nào cũng được target-typed; compiler chỉ dùng kiểu đích tại những vị trí và loại biểu thức được đặc tả cho phép.

### 2.2. Target typing: kết quả ảnh hưởng đến kiểu suy luận

`Collections.emptyList()` là một phương thức generic khai báo gần như sau:

```java
public static <T> List<T> emptyList();
```

Trong hai lời gọi dưới đây, compiler có thể dùng kiểu đích để chọn type argument:

```java
import java.util.Collections;
import java.util.List;

List<String> names = Collections.emptyList();
List<Integer> ids = Collections.emptyList();
```

Lời gọi thứ nhất được suy luận thành `List<String>`, còn lời gọi thứ hai tương thích với `List<Integer>`. Từ Java 9, khi không cần một factory đặc biệt, có thể dùng `List.of()` để tạo list rỗng không thể sửa:

```java
List<String> tags = List.of();
```

Type inference không phải một phép ép kiểu tùy ý. Ví dụ `List<String>` không thể được chuyển thành `List<Integer>` chỉ vì ta muốn kết quả mang kiểu đó.

### 2.3. Explicit type witness khi cần giải quyết mơ hồ

Thông thường nên để compiler suy luận. Nhưng Java cho phép cung cấp type argument tường minh trước tên phương thức:

```java
List<String> a = Collections.<String>emptyList();
List<Long> b = Collections.<Long>emptyList();
```

Cú pháp `<String>` này gọi là **explicit type witness**. Hữu ích khi lời gọi nằm ở vị trí không cung cấp đủ ràng buộc, hoặc khi cần thể hiện chủ đích một cách rõ ràng. Nếu không cần, viết `Collections.emptyList()` ngắn hơn và vẫn type-safe.

Ví dụ với factory do ta tự viết:

```java
import java.util.ArrayList;
import java.util.List;

class GenericFactories {
    static <T> List<T> mutableEmptyList() {
        return new ArrayList<>();
    }

    static void demonstrate() {
        List<String> labels = mutableEmptyList();
        var strings = GenericFactories.<String>mutableEmptyList();
        strings.add("Java");
    }
}
```

`labels` và `strings` đều là `List<String>`. Ở lời gọi đầu, target từ biến `labels` giúp inference; ở lời gọi thứ hai, `<String>` chỉ định kiểu tường minh nên `var` suy ra `List<String>` dù không có target kiểu khai báo bên trái.

## 3. Diamond operator `<>` khi tạo đối tượng generic

Diamond được dùng tại vị trí **type arguments của class instance creation expression**: compiler suy luận các đối số kiểu của lớp đang khởi tạo. Đây không phải cú pháp để khai báo một lớp hoặc phương thức generic.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

List<String> names = new ArrayList<>();
Map<String, List<Integer>> index = new HashMap<>();
```

Trong `new ArrayList<>()`, compiler dùng target type `List<String>` để suy ra `ArrayList<String>`. Trong `new HashMap<>()`, compiler dùng target type `Map<String, List<Integer>>` để xác định `HashMap<String, List<Integer>>`.

Cách viết tương đương nhưng dài hơn:

```java
List<String> names = new ArrayList<String>();
Map<String, List<Integer>> index =
    new HashMap<String, List<Integer>>();
```

### 3.1. Diamond hoàn toàn khác raw type

```java
List<String> safe = new ArrayList<>();     // Generic với diamond

// List<String> raw = new ArrayList();    // Raw type: unchecked conversion
```

`new ArrayList<>()` có `<>` rỗng nhưng compiler vẫn suy luận một type argument cụ thể. `new ArrayList()` bỏ hoàn toàn type argument nên là **raw type** và có thể dẫn đến unchecked warning, mất an toàn kiểu ở những chỗ khác.

Tránh raw type trong mã Java 27 mới. Nếu bắt buộc tương tác với API raw cũ, đặt ranh giới kiểm tra và chuyển đổi rõ ràng thay vì để unchecked cast lan khắp codebase.

### 3.2. Diamond với nhiều type parameter

```java
record Pair<A, B>(A first, B second) { }

Pair<String, Integer> pair = new Pair<>("Java", 27);
System.out.println(pair.first());  // Java
System.out.println(pair.second()); // 27
```

Compiler suy luận **cả hai** type argument. Diamond có thể xuất hiện trong constructor invocation của generic record hoặc generic class; không phải chỉ dành cho `ArrayList`.

### 3.3. Diamond với anonymous class hiện đại

Từ Java 9, diamond có thể được sử dụng với một anonymous class khi kiểu suy luận thỏa điều kiện của ngôn ngữ:

```java
import java.util.Comparator;

Comparator<String> byLength = new Comparator<>() {
    @Override
    public int compare(String a, String b) {
        return Integer.compare(a.length(), b.length());
    }
};
```

Không cần viết lại `new Comparator<String>() { ... }`. Tuy nhiên, khi dùng diamond trong anonymous class, các phương thức **không `private`** do class body khai báo phải tuân thủ quy tắc như thể được gắn `@Override`, và type argument suy luận phải thuộc loại có thể biểu diễn hợp lệ (*denotable*). Vì vậy, không nên thêm một phương thức package-private tùy ý vào anonymous class dùng diamond và mong nó luôn biên dịch.

Với một `Comparator` đơn giản, cách Java hiện đại thường rõ hơn là:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

## 4. `var`: suy luận kiểu biến cục bộ, không phải kiểu động

`var` cho phép compiler suy ra kiểu của **biến cục bộ từ biểu thức khởi tạo**. Nó không khai báo một kiểu generic mới và không làm Java trở thành ngôn ngữ dynamic.

```java
var count = 42;                    // int
var title = "Java 27";            // String
var ids = List.of(10, 20, 30);    // List<Integer>
var text = new StringBuilder();    // StringBuilder

// count = "forty two";           // Sai kiểu: count đã là int
```

`var` xác định kiểu tĩnh ngay khi biên dịch; việc gán lại về sau phải tuân thủ kiểu đó. Nó không phải `Object` và không phải cơ chế suy luận lại sau mỗi phép gán.

### 4.1. `var` và diamond suy luận từ hai phía khác nhau

```java
List<String> explicit = new ArrayList<>();

var precise = new ArrayList<String>();

var tooBroad = new ArrayList<>();
tooBroad.add("A");
tooBroad.add(123); // Hợp lệ: đã suy luận ArrayList<Object>
```

- Dòng `explicit`: target type của biến là `List<String>`; diamond suy ra `String`.
- Dòng `precise`: type argument `String` được viết rõ ở biểu thức `new`; `var` suy ra biến là `ArrayList<String>`.
- Dòng `tooBroad`: cả hai phía đều không có `String` làm ràng buộc, nên suy luận ra `ArrayList<Object>`.

Đây là lỗi thiết kế khó phát hiện nếu chỉ nhìn việc code biên dịch. Danh sách có thể chấp nhận nhiều loại object ngoài ý định. Khi `var` đi cùng constructor generic không có dữ liệu gợi kiểu, hãy **ghi rõ type argument ở phía `new`**:

```java
var users = new ArrayList<String>();
var counters = new HashMap<String, Long>();
```

Nếu mục tiêu của API là expose interface thay vì implementation, khai báo tường minh cũng thường dễ đọc hơn:

```java
List<String> users = new ArrayList<>();
Map<String, Long> counters = new HashMap<>();
```

### 4.2. Những trường hợp `var` không hợp lệ

```java
// var missing;             // Sai: phải có initializer
// var absent = null;       // Sai: không có kiểu suy luận được từ null
// var a = 1, b = 2;        // Sai: nhiều declarator trong một khai báo var
// var numbers = {1, 2};   // Sai: array initializer trực tiếp
// var handler = s -> s;    // Sai: lambda không có target functional interface

var numbers = new int[] {1, 2}; // Hợp lệ: int[]
```

`var` chủ yếu dùng cho local variable, biến vòng lặp và resource trong try-with-resources. Không dùng `var` làm kiểu field, kiểu trả về của method hoặc tham số method thông thường. Một trường hợp riêng được hỗ trợ từ Java 11 là viết `var` cho tham số lambda (xem phần 6).

### 4.3. So sánh ba cách khai báo

| Code | Kiểu tĩnh được chọn | Nhận xét |
| --- | --- | --- |
| `List<String> a = new ArrayList<>();` | `List<String>` | Đọc rõ contract theo interface; diamond có target |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | Kiểu implementation lộ ra ở biến local |
| `var a = new ArrayList<>();` | `ArrayList<Object>` | Dễ rộng hơn ý định nếu list ban đầu rỗng |
| `List<String> a = List.of();` | `List<String>` | Empty list có target type |
| `var a = List.of();` | `List<Object>` | Không có dữ kiện về phần tử |
| `var a = List.of("A", "B");` | `List<String>` | Phần tử giúp suy luận kiểu |

## 5. Target typing và việc suy luận kiểu quá rộng

Java suy luận **type argument phù hợp với các ràng buộc**, không nhất thiết là kiểu người viết nghĩ đến nếu không có thông tin rõ ràng.

```java
List<Number> numbers = List.of(1, 2.5);

var mixed = List.of(1, 2.5);
```

Dòng đầu có target `List<Number>` nên `List.of` có thể được suy luận sao cho tương thích với `List<Number>`. Dòng thứ hai **không có target `List<Number>`**. Khi nhiều loại đối số có quan hệ kế thừa phức tạp, compiler có thể suy ra một kiểu giao (*intersection type*) hoặc một least upper bound phức tạp hơn `Number`; không nên đoán chính xác kiểu khai báo của `mixed` chỉ qua hình dạng biến.

Nếu downstream API mong muốn `List<Number>`, viết rõ điều đó ở ranh giới dữ liệu:

```java
List<Number> values = List.of(1, 2.5);

var explicitValues = List.<Number>of(1, 2.5);
```

### 5.1. Inference trong phép gán, return và lời gọi lồng nhau

```java
static List<String> defaultNames() {
    return List.of();           // Target từ kiểu trả về
}

static void printNames(List<String> names) {
    names.forEach(System.out::println);
}

printNames(List.of("An", "Bình")); // Target từ tham số phương thức
```

Lời gọi generic method có thể là *poly expression*, nhận thông tin kiểu từ ngữ cảnh chứa nó. Nhưng trong một số biểu thức trung gian, target type không còn truyền ngược đến nơi ta nghĩ. Khi gặp lỗi suy luận, hãy tách lời gọi thành biến local được khai báo kiểu rõ ràng hoặc dùng explicit type witness thay vì ép kiểu một cách mù quáng.

### 5.2. Type inference không làm generic trở thành covariant

`Integer` là subtype của `Number`, nhưng `List<Integer>` **không** là subtype của `List<Number>`:

```java
List<Integer> integers = List.of(1, 2, 3);

// List<Number> invalid = integers; // Không biên dịch

List<? extends Number> readable = integers; // Hợp lệ
Number first = readable.get(0);
```

Việc compiler có thể suy ra `List<Number>` cho **một lời gọi mới** như `List.of(1, 2.5)` không có nghĩa mọi `List<Integer>` đang tồn tại đều được phép gán thành `List<Number>`. Generic type trong Java thông thường **invariant** theo type argument.

## 6. Lambda, method reference và inference theo functional interface

Lambda và method reference thường cần một **target functional interface** để xác định kiểu tham số và kết quả.

```java
import java.util.Comparator;
import java.util.List;
import java.util.function.Predicate;

Predicate<String> nonBlank = value -> !value.isBlank();
Comparator<String> byLength = Comparator.comparingInt(String::length);

List<String> names = List.of("An", "", "Bình");
List<String> cleaned = names.stream()
    .filter(nonBlank)
    .map(String::strip)
    .toList();

System.out.println(cleaned); // [An, Bình]
```

Trong `filter`, target type là `Predicate<? super String>` thích hợp; compiler biết `value` là `String`. Trong `map(String::strip)`, compiler suy luận kiểu phần tử đầu ra là `String`. `Stream.toList()` trả một list không thể sửa; nó không giống một lời hứa rằng kết quả là `ArrayList` mutable.

`var` không thể được dùng trực tiếp để khai báo một lambda khi không có target:

```java
// var predicate = value -> !value.isBlank(); // Không biên dịch

Predicate<String> predicate = value -> !value.isBlank();
```

### 6.1. `var` trong danh sách tham số lambda

Java hỗ trợ `var` ở **tham số lambda** để viết đồng nhất với những modifier hoặc annotation được phép áp dụng:

```java
import java.util.function.BiFunction;

BiFunction<String, String, Integer> totalLength =
    (var left, var right) -> left.length() + right.length();

System.out.println(totalLength.apply("Java", "27")); // 6
```

Kiểu của `left` và `right` vẫn được suy luận **từ target `BiFunction<String, String, Integer>`**, không phải `Object`. Nếu chọn cú pháp `var`, tất cả tham số trong cùng một lambda phải dùng nhất quán kiểu đó; không trộn `(var a, String b)` hoặc `(var a, b)`.

Khi không cần annotation hay modifier ở lambda parameters, cú pháp `(a, b) -> ...` thường đủ rõ và ngắn hơn.

## 7. Chọn kiểu tham số cho lớp và phương thức

Điểm xuất phát của thiết kế generic không phải là “càng nhiều `<T>` càng tổng quát”, mà là câu hỏi **những giá trị nào phải có quan hệ kiểu với nhau?**

### 7.1. Khi type parameter thuộc về cả đối tượng

Nếu một instance lưu trữ và xử lý **cùng một loại dữ liệu** qua nhiều phương thức, type parameter nên nằm ở cấp lớp/interface:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}

Box<String> message = Box.of("Java 27");
var number = Box.of(27); // Box<Integer>
```

`T` là type parameter của **instance `Box<T>`**. Phương thức `static` không thể dùng trực tiếp `T` của class làm type parameter cho riêng nó, nên factory `of` khai báo `<U>` riêng. Trong `Box.of("Java 27")`, compiler suy luận `U = String`, và bên trong `new Box<>(value)` dùng diamond để suy luận đối số kiểu của `Box`.

### 7.2. Khi quan hệ kiểu chỉ có trong một lời gọi

Nếu kiểu chỉ liên kết **đầu vào và đầu ra** của một phương thức, hãy khai báo type parameter ở cấp phương thức:

```java
import java.util.List;

static <T> T last(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(values.size() - 1);
}

String lastName = last(List.of("An", "Bình"));
Integer lastId = last(List.of(10, 20));
```

`T` biểu diễn lời hứa rằng giá trị trả về có cùng loại phần tử với danh sách được truyền vào. Việc thay `T` bằng `Object` làm yếu hợp đồng và buộc người gọi cast.

### 7.3. Khi không cần `<T>`

Nếu phương thức chỉ đọc/sử dụng phần tử mà không cần thể hiện quan hệ giữa nhiều vị trí kiểu, wildcard thường là lựa chọn rõ ràng hơn:

```java
static void printAll(List<?> values) {
    values.forEach(System.out::println);
}
```

Không cần viết `static <T> void printAll(List<T> values)` chỉ vì có một tham số là `List`. Nếu `T` không giúp liên kết đầu vào với đầu ra, không gắn ràng buộc hoặc không mang ý nghĩa của thuật toán, wildcard làm API ngắn hơn mà vẫn cho phép nhận `List<String>`, `List<Integer>` và nhiều kiểu khác.

**Quy tắc thực hành:** Dùng **một type parameter khi cần giữ một quan hệ kiểu**, dùng **wildcard khi chỉ cần mô tả vị trí đọc/ghi**, dùng **kiểu cụ thể khi nghiệp vụ thật sự chỉ chấp nhận kiểu đó**.

## 8. Bounded type parameters: giới hạn những kiểu hợp lệ

`<T>` không có bound tường minh có upper bound mặc định là `Object`. Nếu một thuật toán cần khả năng cụ thể như so sánh, không nên dùng `<T>` rồi ép kiểu bên trong. Hãy biểu diễn yêu cầu trong khai báo type parameter.

```java
static <T extends Comparable<? super T>> T largest(List<? extends T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }

    T best = values.get(0);
    for (T candidate : values) {
        if (candidate.compareTo(best) > 0) {
            best = candidate;
        }
    }
    return best;
}

String greatestName = largest(List.of("An", "Bình", "Chi"));
Integer greatestId = largest(List.of(7, 12, 3));
```

`Comparable<? super T>` biểu diễn rằng `T` có thể được so sánh với một giá trị kiểu `T` thông qua hợp đồng `Comparable`. Đây là bound linh hoạt hơn `Comparable<T>` trong một số hệ phân cấp kiểu, vì một lớp con có thể kế thừa khả năng so sánh với lớp cha.

### 8.1. Bound theo class hoặc interface

```java
static <T extends Number> double doubled(T value) {
    return value.doubleValue() * 2;
}

double a = doubled(12);   // Integer -> Number
double b = doubled(2.5);  // Double -> Number
```

Method này minh họa bound nhưng **không nhất thiết cần generic**: nếu API chỉ đọc `doubleValue()` và trả về `double`, chữ ký `static double doubled(Number value)` có thể đơn giản hơn. Dùng `<T extends Number>` khi cần giữ quan hệ kiểu giữa tham số và kết quả hoặc giữa nhiều tham số, không chỉ vì muốn nhận nhiều subtype.

### 8.2. Nhiều bound

Java cho phép dùng một class bound (nếu có, phải đặt đầu tiên) và các interface bound theo sau:

```java
static <T extends Number & Comparable<T>> T larger(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}

Integer winner = larger(15, 27); // 27
```

Ví dụ yêu cầu `T` vừa là `Number`, vừa là `Comparable<T>`. `Integer` đáp ứng cả hai. Đừng thêm các bound chỉ để chứng minh API tổng quát; mỗi bound làm hẹp tập kiểu được phép truyền vào và cần phản ánh yêu cầu thực sự.

### 8.3. Type parameter cho khóa và giá trị

Hai type parameter độc lập nên có tên và ý nghĩa rõ ràng:

```java
import java.util.Map;

static <K, V> Map<K, V> oneEntry(K key, V value) {
    return Map.of(key, value);
}

Map<String, Integer> counts = oneEntry("java", 27);
Map<Integer, String> labels = oneEntry(27, "java");
```

`K` và `V` có quan hệ với từng vị trí nhưng không cần cùng kiểu. Nếu dùng một `<T>` cho cả key và value, API có thể ép caller vào kiểu chung rộng hơn ngoài mong muốn.

## 9. Wildcard và nguyên tắc PECS khi thiết kế tham số

Type parameter và wildcard phục vụ những mục đích khác nhau:

- **`List<T>`**: danh sách phần tử có kiểu `T` được liên kết với các vị trí `T` khác trong cùng API.
- **`List<? extends T>`**: danh sách có phần tử thuộc một subtype chưa biết của `T`, thường dùng làm **nguồn đọc**.
- **`List<? super T>`**: danh sách có phần tử thuộc một supertype chưa biết của `T`, thường dùng làm **đích ghi**.
- **`List<?>`**: không cần biết cụ thể type argument, có thể đọc phần tử như `Object`.

Nguyên tắc ghi nhớ **PECS: Producer Extends, Consumer Super**. Nó giúp chọn kiểu tham số dựa trên hướng dữ liệu.

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> integers = List.of(1, 2, 3);

List<? extends Number> source = integers;
Number value = source.get(0); // Đọc thành Number
// source.add(4);             // Không biên dịch: subtype cụ thể chưa biết

List<? super Integer> destination = new ArrayList<Number>();
destination.add(4);           // Có thể ghi Integer
Object item = destination.get(0); // Đọc an toàn chỉ dưới dạng Object
```

`? extends` **không đồng nghĩa collection bất biến**: nó chỉ giới hạn những thao tác có thể được compiler chứng minh là type-safe từ tham chiếu wildcard đó. Đối tượng nguồn vẫn có thể mutable thông qua tham chiếu khác.

### 9.1. Khi cần dùng `<T>` để nối hai wildcard

Một hàm sao chép nhiều loại dữ liệu cần quan hệ giữa kiểu phần tử đầu vào và kiểu của destination:

```java
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}

List<Number> numbers = new ArrayList<>();
List<Integer> ints = List.of(10, 20, 30);

appendAll(numbers, ints);
System.out.println(numbers); // [10, 20, 30]
```

Ở đây `<T>` thực sự có ích: nó diễn đạt rằng kiểu từ `source` phải được phép ghi vào `destination`. Compiler có thể chọn `T = Integer` để chấp nhận `List<Integer>` ở nguồn và `List<Number>` ở đích.

Nếu phương thức chỉ nhận một danh sách để in/log, `List<?>` đã đủ. Nếu chỉ nhận một danh sách các `Number` để tính tổng, `List<? extends Number>` thường thích hợp hơn `<T extends Number>` khi không cần trả lại chính kiểu `T`.

### 9.2. Quyết định qua bảng lựa chọn

| Mục tiêu của API | Chữ ký gợi ý | Vì sao |
| --- | --- | --- |
| In tất cả phần tử, không sửa | `void log(List<?> items)` | Không cần type parameter có tên |
| Cộng các số có subtype khác nhau | `double sum(List<? extends Number> xs)` | Đọc `Number` từ nhiều loại list |
| Lấy phần tử và giữ kiểu đầu ra | `<T> T first(List<T> xs)` | Ràng buộc kiểu trả về với phần tử |
| Ghi `Integer` vào container rộng hơn | `void addOne(List<? super Integer> out)` | Đích chấp nhận `Integer` |
| Sao chép generic giữa source và target | `<T> void copy(List<? super T> out, List<? extends T> in)` | Nối quan hệ kiểu hai tham số |
| Xử lý riêng danh sách `String` | `void validate(List<String> names)` | Domain yêu cầu đúng kiểu `String` |

Wildcard không phải lựa chọn duy nhất. Nếu API thật sự cho caller thao tác hai chiều trên cùng một tập kiểu, một type parameter có tên có thể truyền tải ý nghĩa tốt hơn.

## 10. Inference khi dùng stream và API theo chuỗi

Suy luận kiểu rất hữu ích trong pipeline: kiểu phần tử của một bước ràng buộc kiểu đầu vào của bước tiếp theo.

```java
import java.util.Comparator;
import java.util.List;

record User(String name, int score) { }

List<User> users = List.of(
    new User("An", 95),
    new User("Bình", 70),
    new User("Chi", 90)
);

List<String> excellentNames = users.stream()
    .filter(user -> user.score() >= 90)
    .sorted(Comparator.comparing(User::name))
    .map(User::name)
    .toList();

System.out.println(excellentNames); // [An, Chi]
```

`users.stream()` tạo `Stream<User>`; `filter` giữ nguyên kiểu phần tử; `sorted` dùng `Comparator<User>`; `map(User::name)` chuyển sang `Stream<String>`; `toList()` trả `List<String>`. Kết quả có thể được suy luận bằng `var`:

```java
var excellentNames = users.stream()
    .filter(user -> user.score() >= 90)
    .map(User::name)
    .toList();
```

Trong ví dụ thay thế này, biến local được suy luận thành `List<String>`. Tuy nhiên, với API public hoặc nơi cần thể hiện kiểu contract, `List<String>` tường minh có thể dễ bảo trì hơn `var`.

### 10.1. Khi lambda quá dài hoặc inference khó đọc

Ví dụ có nhiều cấp generic và method reference, việc tách pipeline có thể giúp người đọc thấy luồng kiểu:

```java
List<User> topUsers = users.stream()
    .filter(user -> user.score() >= 90)
    .toList();

List<String> topNames = topUsers.stream()
    .map(User::name)
    .toList();
```

Không có quy tắc phải thay mọi kiểu local bằng `var`. Ưu tiên khả năng hiểu được domain và kiểu tại mỗi ranh giới, nhất là khi pipeline phức tạp hoặc thông báo lỗi compiler khó phân tích.

## 11. Type erasure: suy luận kiểu không giữ mọi thông tin lúc runtime

Java generics phần lớn được thực thi theo cơ chế **type erasure**. Type inference xác định thông tin cho kiểm tra kiểu lúc biên dịch, nhưng không có nghĩa mọi type argument còn nguyên tại runtime.

Ví dụ:

```java
List<String> strings = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(strings.getClass() == numbers.getClass()); // true
```

Trong ví dụ, cả hai là instance của `ArrayList`. Lớp runtime không biến thành hai lớp riêng `ArrayList<String>` và `ArrayList<Integer>` chỉ vì type argument khác nhau.

Các thao tác sau **không hợp lệ** hoặc cần thiết kế khác:

```java
// if (obj instanceof List<String>) { ... } // Không hợp lệ
// T object = new T();                       // Không hợp lệ với type variable T
// T[] values = new T[10];                   // Không thể tạo generic array như vậy
// void process(List<String> x) { }
// void process(List<Integer> x) { }         // Không thể overload chỉ bằng type argument
```

Có thể kiểm tra tham chiếu có phải `List<?>` hay không:

```java
if (obj instanceof List<?> list) {
    System.out.println("Elements: " + list.size());
}
```

Nhưng từ `List<?>` không thể suy ra rằng **mọi phần tử** là `String` nếu chưa kiểm tra từng phần tử. Không được thay thế kiểm tra bằng unchecked cast tùy tiện:

```java
// List<String> unsafe = (List<String>) obj; // Có thể gây unchecked warning
```

Nếu cần khởi tạo một giá trị của kiểu `T`, hãy nhận factory như `Supplier<? extends T>` hoặc `Class<T>` khi phù hợp, thay vì tưởng compiler có thể tự tạo `new T()` sau khi suy luận.

```java
import java.util.function.Supplier;

static <T> T create(Supplier<? extends T> factory) {
    return factory.get();
}

StringBuilder builder = create(StringBuilder::new);
```

### 11.1. Kiểu nguyên thủy với generics

Trong cú pháp generic Java 27 thông thường, type argument phải là kiểu tham chiếu, không phải primitive:

```java
List<Integer> counts = List.of(1, 2, 3); // Hợp lệ
// List<int> counts = ...;                 // Không hợp lệ
```

Compiler thực hiện boxing/unboxing khi tương tác với `Integer` nếu phù hợp. Với xử lý số lượng lớn mà hiệu năng và boxing là vấn đề, cân nhắc `int[]`, `IntStream` và các API primitive phù hợp. Không nhầm tính năng preview **primitive types trong patterns, `instanceof`, `switch`** của Java 27 với việc hỗ trợ primitive type argument cho mọi generic class.

## 12. Lỗi suy luận kiểu thường gặp

Thông báo như *cannot infer type arguments*, *incompatible types* hoặc *inference variable has incompatible bounds* thường cho biết compiler không thể tìm một phép gán kiểu thỏa mọi ràng buộc.

| Trường hợp | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `var list = new ArrayList<>()` rồi nhận cả `String` lẫn `Integer` | Inference chọn `Object` khi không có target | Viết `List<String> list = new ArrayList<>()` hoặc `var list = new ArrayList<String>()` |
| `var list = List.of()` | Không có kiểu phần tử để suy ra cụ thể | Khai báo `List<String> list = List.of()` hoặc `List.<String>of()` |
| `var fn = x -> x` | Lambda không có target functional interface | Khai báo `Function<String, String> fn = x -> x` |
| `List<Number> xs = List.<Integer>of(1, 2)` | Explicit witness khóa kết quả thành `List<Integer>`, vốn không phải `List<Number>` | Bỏ witness nếu muốn compiler dùng target `List<Number>`; hoặc chọn wildcard nếu chỉ cần đọc |
| `List<Number> xs = integerList` | Generics invariant | Dùng wildcard hoặc tạo danh sách mới với kiểu đích |
| `new ArrayList()` | Raw type, unchecked conversion | Dùng `new ArrayList<>()` |
| `new T()` trong phương thức generic | Không có khả năng tạo instance từ type variable đã bị erasure | Truyền `Supplier<T>` hoặc factory |
| Overload hai method chỉ khác `List<String>`/`List<Integer>` | Hai chữ ký có cùng erasure | Đổi tên, thêm tham số phân biệt hoặc thiết kế API khác |
| `List<String> xs = new ArrayList<Integer>()` | Hai type arguments xung đột | Đồng nhất kiểu hoặc thay model dữ liệu |

### 12.1. Đọc lỗi theo chuỗi ràng buộc

Khi compiler báo không suy luận được kiểu, hãy lần lượt kiểm tra:

1. Type parameter nào cần tìm (`T`, `U`, `K`, `V`)?
2. Các đối số thật có kiểu nào? Có `null`, lambda, method reference hoặc raw type không?
3. Vị trí biểu thức có target type không? Nếu dùng `var`, target type ban đầu thường không có.
4. Bound nào (`extends`, wildcard, `Comparable`) đang loại trừ kiểu được mong đợi?
5. Có overload cạnh tranh khiến compiler chọn hoặc không chọn được một phương thức thích hợp không?
6. Có thể tách biểu thức ra một biến kiểu tường minh để làm ràng buộc rõ hơn không?

Phương án tốt thường là **thêm đúng thông tin kiểu ở ranh giới** hoặc điều chỉnh chữ ký API, không phải dùng cast hay `@SuppressWarnings("unchecked")` để che lỗi suy luận.

### 12.2. Kiểu tĩnh và overload

Java chọn overload tại thời điểm biên dịch theo kiểu tĩnh của biểu thức và quy tắc phân giải overload. `var` không khiến Java tự tìm overload theo kiểu runtime của object:

```java
static String describe(Number value) {
    return "number";
}

static String describe(Integer value) {
    return "integer";
}

Number explicit = Integer.valueOf(42);
var inferred = Integer.valueOf(42);

System.out.println(describe(explicit)); // number
System.out.println(describe(inferred)); // integer
```

`explicit` có kiểu tĩnh `Number`, còn `inferred` có kiểu tĩnh `Integer`. Cả hai cùng chứa một đối tượng `Integer`, nhưng compiler chọn overload khác nhau. Đây là lý do việc chọn `var` hay khai báo kiểu tường minh đôi khi ảnh hưởng đến API được gọi, dù bản thân object không thay đổi.

## 13. Nguyên tắc chọn kiểu tham số và mức suy luận trong API

Khi thiết kế một generic API mới, nên ưu tiên **ý nghĩa của quan hệ kiểu** trước khi nghĩ đến việc viết ngắn. Một type parameter được đặt tên nên phục vụ mục tiêu cụ thể, không chỉ xuất hiện để phương thức trông tổng quát.

### 13.1. Cấp độ lựa chọn

| Bài toán | Lựa chọn đầu tiên nên cân nhắc | Tránh |
| --- | --- | --- |
| Trả về một giá trị cùng kiểu với đầu vào | `<T> T transform(T item)` | Trả về `Object` rồi cast |
| Một instance giữ một kiểu dữ liệu xuyên suốt vòng đời | `Repository<T>`, `Box<T>` | Để mọi API nhận `Object` |
| Chỉ đọc một collection bất kỳ | `Collection<?>` | Khai báo `<T>` không cần thiết |
| Đọc các subtype của một kiểu nền | `Collection<? extends Number>` | Ép caller về đúng `Collection<Number>` |
| Ghi phần tử có kiểu `T` vào đích | `Collection<? super T>` | Dùng `Collection<T>` làm API hẹp vô cớ |
| Đồng bộ quan hệ kiểu nguồn và đích | `<T> copy(Collection<? super T>, Collection<? extends T>)` | Hai wildcard không có quan hệ |
| Cần hỗ trợ hành vi như so sánh | `<T extends Comparable<? super T>>` | Cast về `Comparable` ở runtime |
| Domain chỉ chấp nhận `String` | `String`, `List<String>` | `<T>` khiến input không liên quan cũng hợp lệ |

### 13.2. Đặt tên type parameter

Các chữ thường dùng trong Java là `T` (một kiểu dữ liệu), `E` (element), `K` (key), `V` (value), `R` (result), `U` (một type parameter khác). Chúng là quy ước, không phải từ khóa đặc biệt.

Nếu phương thức có nhiều type parameter, hãy chọn tên phù hợp với vai trò:

```java
import java.util.function.Function;

static <T, R> R mapValue(T input, Function<? super T, ? extends R> mapper) {
    return mapper.apply(input);
}

Integer length = mapValue("Java 27", String::length);
```

`T` diễn đạt kiểu input, `R` diễn đạt kiểu result. Chữ ký sử dụng variance của `Function` để chấp nhận hàm nhận supertypes của `T` và trả subtypes của `R` khi an toàn.

### 13.3. Để inference làm việc, nhưng đừng ẩn contract

```java
// Thường tốt: kiểu contract của biến dễ đọc
List<String> tags = new ArrayList<>();

// Cũng tốt ở code local, initializer cho biết rõ kiểu
var tagsCopy = new ArrayList<String>();

// Cần cân nhắc: compiler suy ra Object thay vì String
var tagsUnknown = new ArrayList<>();
```

`var` hữu ích khi kiểu đã hiển nhiên hoặc quá dài ở một scope nhỏ. Ngược lại, ở nơi tên biến `data`, `value`, `result` chưa giúp hiểu domain, việc khai báo tường minh có thể giảm chi phí đọc code. Không nên biến nguyên tắc “ít gõ” thành mục tiêu cao hơn type safety và API clarity.

## 14. Ví dụ tổng hợp: type inference, diamond, `var` và PECS

Đoạn chương trình sau có thể đặt trong file `GenericsInferenceDemo.java` và chạy với Java 27. Nó minh họa một generic record, factory suy luận kiểu, diamond, `var`, generic copy với PECS và generic method có bound.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericsInferenceDemo {
    record Result<T>(T value, List<String> warnings) {
        Result {
            Objects.requireNonNull(value, "value");
            warnings = List.copyOf(warnings);
        }
    }

    static <T> Result<T> success(T value) {
        return new Result<>(value, List.of());
    }

    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T item : source) {
            destination.add(item);
        }
    }

    static <T extends Comparable<? super T>> T greatest(
            List<? extends T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }

        T best = values.get(0);
        for (T candidate : values) {
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Integer> scores = List.of(10, 20, 30);

        // T được suy luận từ đối số List<Integer>.
        // Diamond ở new Result<>(...) nhận kiểu từ constructor context.
        var result = success(scores); // Result<List<Integer>>

        // Không dùng var new ArrayList<>(): thiếu thông tin Integer.
        var work = new ArrayList<Integer>();
        appendAll(work, result.value());

        // Có thể ghi Integer vào một List<Number>.
        List<Number> numbers = new ArrayList<>();
        appendAll(numbers, work);

        Integer maximum = greatest(work);
        var labels = work.stream()
            .map(score -> "score:" + score)
            .toList(); // List<String>

        System.out.println("scores=" + work);
        System.out.println("numbers=" + numbers);
        System.out.println("maximum=" + maximum);
        System.out.println("labels=" + labels);
    }
}
```

Kết quả:

```text
scores=[10, 20, 30]
numbers=[10, 20, 30]
maximum=30
labels=[score:10, score:20, score:30]
```

Những điểm quan trọng trong chương trình:

1. `success(scores)` suy luận `T = List<Integer>` nên có kiểu trả về `Result<List<Integer>>`.
2. Trong `success`, `new Result<>(value, List.of())` sử dụng diamond và ràng buộc từ đối số/kiểu trả về để khởi tạo `Result<T>`.
3. `var work = new ArrayList<Integer>()` giữ kiểu phần tử `Integer`; đây là lựa chọn rõ ràng khi muốn dùng `var` với constructor collection rỗng.
4. `appendAll(numbers, work)` được chấp nhận dù `numbers` là `List<Number>` và `work` là `List<Integer>`, vì chữ ký dùng **PECS** và liên kết hai vị trí bằng `<T>`.
5. `greatest(work)` giữ kiểu trả về `Integer` vì `T` được ràng buộc bởi danh sách đầu vào và `Comparable`.
6. `.map(score -> "score:" + score).toList()` suy luận `List<String>` cho `labels`.

Ví dụ không cần preview feature của Java 27 và không dựa vào raw type. Khi triển khai trong project, thêm kiểm thử với dữ liệu rỗng, `null` và các kiểu đầu vào khác để xác thực hợp đồng từng phương thức.

## 15. Checklist khi dùng type inference trong Java 27

- [ ] Type parameter có biểu diễn một **quan hệ kiểu thực sự** giữa tham số, kết quả hoặc trạng thái đối tượng không?
- [ ] Nếu phương thức chỉ đọc `Collection`, có thể dùng `Collection<?>` hoặc `Collection<? extends X>` thay vì `<T>` không cần thiết không?
- [ ] Nếu dữ liệu được ghi vào một collection, chữ ký có dùng `? super T` hợp lý không?
- [ ] Với diamond `<>`, compiler có đủ dữ kiện về type argument từ target hoặc constructor arguments không?
- [ ] Nếu dùng `var` cho collection rỗng, kiểu có vô tình thành `Object` không?
- [ ] Có raw type nào (`new ArrayList()`, `List` không tham số hóa) cần loại bỏ không?
- [ ] Khi dùng lambda hoặc method reference, target functional interface có rõ ràng không?
- [ ] Có overload nào mà sự khác biệt giữa kiểu tĩnh và kiểu runtime dẫn đến kết quả bất ngờ không?
- [ ] Bound của `T` đã phản ánh đúng khả năng thuật toán cần dùng chưa?
- [ ] Có unsafe cast nào đang che lỗi suy luận kiểu thay vì sửa chữ ký API không?
- [ ] Nếu dùng `var` trong public-facing logic, người đọc có dễ nhận ra kiểu và contract không?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai dòng dưới đây có được compiler suy ra cùng một kiểu không? Vì sao?

```java
List<String> first = new ArrayList<>();
var second = new ArrayList<>();
```

*Gợi ý:* `first` cung cấp target `List<String>` cho diamond. `second` không cung cấp target; kiểu phần tử được suy luận rộng thành `Object`.

**Câu 2.** Vì sao `List<Integer>` không thể gán trực tiếp cho `List<Number>` dù `Integer extends Number`?

*Gợi ý:* Generic class `List<E>` thông thường invariant theo `E`. Nếu phép gán hợp lệ, `List<Number>` có thể cho phép thêm `Double` vào một list thực tế chỉ được khai báo chứa `Integer`.

**Câu 3.** Khi nào nên viết `static void logAll(List<?> xs)` và khi nào cần `static <T> T first(List<T> xs)`?

*Gợi ý:* `logAll` không cần liên kết kiểu với kết quả. `first` phải giữ kiểu kết quả theo kiểu phần tử đầu vào.

**Câu 4.** `var task = x -> x.toString()` có hợp lệ không? Làm thế nào để sửa?

*Gợi ý:* Lambda cần target functional interface, ví dụ `Function<String, String> task = x -> x.toString();`.

**Câu 5.** Với một phương thức sao chép từ `List<Integer>` sang `List<Number>`, vì sao `List<? extends T>` ở nguồn và `List<? super T>` ở đích thường hữu ích hơn hai `List<T>`?

*Gợi ý:* Nguồn cung cấp `T` hoặc subtype; đích phải chấp nhận `T`. Hai list không cần có cùng type argument.

**Câu 6.** Một method generic có tham số `<T extends Comparable<? super T>>` giải quyết vấn đề gì?

*Gợi ý:* Compiler chỉ chấp nhận những loại `T` có khả năng so sánh tương thích với `T`, nên không cần cast nguy hiểm trong thân phương thức.

## Tài liệu tham khảo chính thức

- [Java Language Specification 27 — Chapter 18: Type Inference](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-18.html): ràng buộc và các bước suy luận kiểu cho generic methods.
- [Java Language Specification 27 — §15.9: Class Instance Creation Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.9): diamond, target typing và anonymous classes.
- [Java Language Specification 27 — §15.12: Method Invocation Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.12): chọn overload và kiểu lời gọi phương thức.
- [Java Language Specification 27 — §14.4: Local Variable Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.4): suy luận kiểu với `var` và các trường hợp bị cấm.
- [Java Language Specification 27 — §4.5: Parameterized Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.5): type arguments, wildcards và type containment.
- [Java Language Specification 27 — §8.4.4: Generic Methods](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.4): khai báo type parameters cho method.
- [Java SE 27 API — List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): generic collections và factory methods.
- [Java SE 27 API — Comparator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): so sánh và factory với method reference.
- [Java SE 27 API — Stream.toList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html#toList()): danh sách trả về từ stream.
- [Java SE 27 Language Updates](https://docs.oracle.com/en/java/javase/27/language/index.html): bối cảnh những tính năng ngôn ngữ đã ổn định và preview.
