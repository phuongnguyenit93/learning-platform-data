# Quan hệ kiểu giữa nhiều đối số và giá trị trả về trong phương thức Generic của Java

Generic method không chỉ giúp viết một phương thức dùng được cho nhiều kiểu dữ liệu. Giá trị lớn hơn là **mô tả mối quan hệ kiểu giữa các tham số và kết quả ngay trong chữ ký**, để Java compiler kiểm tra từng lời gọi. Một phương thức `static <T> T first(T a, T b)` dùng chung biến kiểu `T` cho cả hai đối số và kết quả. Một phương thức `static <A, B, R> R combine(A a, B b, BiFunction<A, B, R> f)` cho phép kiểu của hai đầu vào khác nhau nhưng vẫn ràng buộc kiểu kết quả với phép biến đổi.

Bài này hướng dẫn đọc, thiết kế và kiểm chứng những quan hệ đó bằng Java 17+: **biến kiểu chung, nhiều biến kiểu độc lập, suy luận kiểu, kiểu đích, bounded type parameter, wildcard, collection, method reference, giới hạn ở runtime và các lỗi thường gặp**. Trọng tâm là chữ ký của **phương thức generic** và cách lời gọi buộc compiler tìm một phép gán kiểu hợp lệ.

## 1. Phương thức generic thực sự “liên kết” những gì?

Cấu trúc khai báo:

```java
static <T> T method(T first, T second)
```

Đây là chữ ký minh họa, chưa có thân. Hãy tách thành bốn phần:

- `static`: modifier của phương thức.
- `<T>`: khai báo **type parameter** mang tên `T` cho chính phương thức.
- `T` ở vị trí kiểu trả về: kết quả được xem có kiểu `T` tại điểm gọi.
- `T first, T second`: hai tham số cùng tham chiếu tới một biến kiểu `T`.

Điều này tạo các ràng buộc kiểu compile time. Nó **không** hứa hai đối số phải cùng lớp runtime, không hứa kết quả bằng đối số nào, và không làm `T` tồn tại như một class chuyên biệt ở JVM.

So sánh với:

```java
static Object selectObject(Object first, Object second)
```

Chữ ký `Object` chỉ cam kết kiểu trả về là `Object`; người gọi không giữ được mối quan hệ với một biến kiểu được suy luận. Vì vậy:

```java
String a = select("Lan", "Mai");      // Với <T> T select(T,T), hợp lệ.
Object b = selectObject("Lan", "Mai"); // Hợp lệ.
// String c = selectObject("Lan", "Mai"); // Lỗi nếu không cast.
```

Các dòng này minh họa việc sử dụng, giả sử `select`/`selectObject` đã được định nghĩa như chữ ký.

### Phương thức generic khác generic class

`class Box<T>` có `T` được gắn với cách sử dụng `Box<String>` hoặc `Box<Integer>`. Còn `static <T> T identity(T x)` khai báo `T` cho **từng invocation**. Cùng một method có thể được gọi lần lượt với `String` rồi `Integer`. Không cần có `Box<T>` hay một class generic mới viết được generic method.

## 2. Ví dụ chạy được: cùng một T liên kết hai đối số và kết quả

Tạo `ChooseDemo.java`:

```java
public class ChooseDemo {
    static <T> T first(T left, T right) {
        return left;
    }

    static <T> T last(T left, T right) {
        return right;
    }

    public static void main(String[] args) {
        String name = first("Lan", "Mai");
        Integer count = last(10, 20);

        System.out.println(name);
        System.out.println(count);
    }
}
```

Biên dịch, chạy:

```bash
javac ChooseDemo.java
java ChooseDemo
```

`stdout`:

```text
Lan
20
```

Lần theo kiểu của lời gọi đầu:

1. Đọc khai báo `<T>`: type parameter của method.
2. Đối số `"Lan"` và `"Mai"` đều có kiểu `String`.
3. Kiểu đích của biểu thức gán cũng là `String`.
4. `javac` có thể chọn `T = String` thỏa các ràng buộc.
5. Biểu thức `first(...)` được xem có kiểu `String`; không cần ép kiểu tường minh.

Lời gọi `last(10, 20)` dùng hai primitive `int`; boxing và type inference cho phép kết quả được sử dụng như `Integer`. Không có “phiên bản last riêng của Integer” được sinh ra theo kiểu chuyên biệt hóa generic.

**Điểm cần phân biệt:** vì thân `first` thật sự `return left` nên kết quả bằng giá trị `left`. Chữ ký `<T> T first(T,T)` tự nó chỉ bảo đảm **kiểu của kết quả**, không chứng minh kết quả bắt buộc bằng `left`. Một triển khai khác có thể trả `right` hoặc ném exception.

## 3. “Cùng T” không đồng nghĩa đối số phải có exact runtime class giống nhau

Một sai lầm phổ biến là nghĩ `<T> T choose(T a, T b)` chỉ nhận hai đối tượng có cùng class. Trên thực tế, **method type inference giải một hệ ràng buộc kiểu**; Java có thể tìm một kiểu cha chung hoặc một kiểu giao phù hợp cho các biểu thức truyền vào.

Ví dụ:

```java
static <T> T chooseFirst(T a, T b) {
    return a;
}

Number number = chooseFirst(1, 2.5);
```

Đây là đoạn minh họa đặt trong class; `1` được boxing thành kiểu thích hợp, `2.5` thành `Double`. Kiểu `Number` ở vế trái là một kiểu đích hợp lệ; compiler không yêu cầu `Integer.class == Double.class`. Giá trị thực của `number` vẫn là đối tượng mang giá trị `1`.

### Khi các đối số khác nhau và không có kiểu đích cụ thể

Cho:

```java
var value = chooseFirst("hello", 42);
```

Không nên tự suy luận rằng `value` chắc chắn có kiểu `String` hoặc `Integer`. Type inference có thể chọn một common supertype hay intersection type phù hợp, tùy các ràng buộc của invocation và cách biểu diễn kiểu cụ thể. Với `var`, kiểu biến được suy luận từ biểu thức khởi tạo, không phải từ một generic type argument mà bạn chỉ định sẵn.

Nếu nghiệp vụ cần “hai đối số phải có kiểu chính xác bằng nhau ở runtime”, một chữ ký dùng chung `T` **không** phải phép kiểm tra identity class. Bạn cần ràng buộc nghiệp vụ rõ hơn hoặc validation thích hợp; ngay cả một `<T>` chung có thể được suy luận thành supertype của hai đầu vào.

### Giới hạn của suy luận kiểu

Suy luận kiểu hoạt động từ **kiểu tĩnh** của biểu thức, quy tắc subtyping, khả năng áp dụng method và expected target type. Nó không đọc nội dung chuỗi, không biết một `Number` thực sự được gán từ `Integer` trước đó để “tự quyết định” kiểu nghiệp vụ cụ thể, và không duyệt dữ liệu trong một collection để bảo đảm đồng nhất phần tử.

## 4. Nếu muốn hai đối số độc lập, khai báo hai biến kiểu

Chữ ký:

```java
static <A, B> String describe(A first, B second)
```

cho phép hai tham số có kiểu độc lập. `A` và `B` đều được khai báo riêng; kiểu trả về cụ thể là `String` nên không phụ thuộc vào lựa chọn `A`/`B`.

Nếu kết quả cũng cần tham số hóa:

```java
static <A, B> Pair<A, B> pair(A first, B second)
```

thì kiểu trả về **giữ cả hai quan hệ**. Với `pair("Lan", 9)`, compiler suy luận `A=String`, `B=Integer` và kết quả có kiểu `Pair<String,Integer>`.

### Chương trình hoàn chỉnh: hai đầu vào, hai components trong kết quả

Tạo `PairFactoryDemo.java`:

```java
public class PairFactoryDemo {
    record Pair<A, B>(A first, B second) {
    }

    static <A, B> Pair<A, B> pair(A first, B second) {
        return new Pair<>(first, second);
    }

    public static void main(String[] args) {
        Pair<String, Integer> score = pair("Lan", 9);
        Pair<Long, Boolean> status = pair(100L, true);

        System.out.println(score.first());
        System.out.println(score.second() + 1);
        System.out.println(status.first() + ": " + status.second());
    }
}
```

Chạy:

```bash
javac PairFactoryDemo.java
java PairFactoryDemo
```

`stdout`:

```text
Lan
10
100: true
```

Bảng ràng buộc:

| Vị trí | Khai báo | Khi gọi `pair("Lan", 9)` |
| --- | --- | --- |
| `A` | Method `<A,B>` | `String` |
| `B` | Method `<A,B>` | `Integer` |
| `A first` | Tham số thứ nhất | Nhận `String` |
| `B second` | Tham số thứ hai | Nhận `Integer` |
| `Pair<A,B>` | Kiểu trả về | `Pair<String,Integer>` |

`Pair<A,B>` của record và `<A,B>` của static method là **hai nơi khai báo khác nhau**; tên trùng vì cách đặt trong ví dụ. Ở vị trí `Pair<A,B>` bên trong method, `A`/`B` là type arguments truyền cho record, lấy từ type parameters của **method**.

## 5. Liên kết đầu vào và đầu ra bằng ba biến kiểu: A, B, R

Nhiều thuật toán biến đổi **hai đầu vào thành một kết quả**. Nếu kết quả không cùng kiểu với một trong hai đầu vào, nên khai báo type parameter riêng cho kiểu kết quả.

Chữ ký nền tảng:

```java
static <A, B, R> R combine(
        A first,
        B second,
        java.util.function.BiFunction<? super A, ? super B, ? extends R> operation)
```

Ý nghĩa:

- `A`: kiểu đầu vào thứ nhất.
- `B`: kiểu đầu vào thứ hai.
- `R`: kiểu kết quả.
- `operation`: một hàm chấp nhận các giá trị `A`, `B` và trả về giá trị tương thích với `R`.
- `R combine(...)`: kết quả lời gọi giữ đúng kiểu `R` mà compiler suy luận.

Tạo `CombineDemo.java`:

```java
import java.util.function.BiFunction;

public class CombineDemo {
    static <A, B, R> R combine(
            A first,
            B second,
            BiFunction<? super A, ? super B, ? extends R> operation) {
        return operation.apply(first, second);
    }

    public static void main(String[] args) {
        String label = combine("ID-", 17, (prefix, number) -> prefix + number);
        Integer total = combine(4, 7, Integer::sum);

        System.out.println(label);
        System.out.println(total);
    }
}
```

Biên dịch/chạy:

```bash
javac CombineDemo.java
java CombineDemo
```

`stdout`:

```text
ID-17
11
```

Ở lời gọi thứ nhất, một nghiệm tự nhiên là `A=String`, `B=Integer`, `R=String`. Ở lời gọi thứ hai, `A=Integer`, `B=Integer`, `R=Integer`. Cùng một phương thức áp dụng cho hai quan hệ kiểu khác nhau.

### Tại sao `BiFunction<? super A, ? super B, ? extends R>` thay vì `BiFunction<A,B,R>`?

Cả hai có thể mô tả quan hệ cơ bản. Wildcard tăng khả năng nhận hàm có kiểu tham số rộng hơn hoặc kết quả hẹp hơn:

- `? super A`: hàm có thể chấp nhận `A` hoặc một supertype thích hợp của `A`.
- `? super B`: tương tự với đầu vào thứ hai.
- `? extends R`: hàm tạo giá trị kiểu `R` hoặc subtype của `R`.

Việc chọn wildcard là thiết kế API linh hoạt theo hướng **consumer super, producer extends**. Tại lớp học cơ bản, hãy nhận diện trước `A,B,R` liên kết ba vị trí; tiếp theo mới phân tích variance.

### Có phải R hoàn toàn độc lập?

`R` được khai báo độc lập nhưng ràng buộc bởi kiểu trả về của `operation` và kiểu mục tiêu của toàn lời gọi. Nếu hàm trả `String`, bạn không thể tùy ý gán trực tiếp kết quả cho `Integer` mà không có một phép chuyển đổi hợp lệ. Generic không tự biến một `String` thành `Integer` chỉ vì caller yêu cầu `R=Integer`.

## 6. Quan hệ đầu vào–đầu ra trong Generic Method làm việc với List

Generic method rất hữu ích khi container đầu vào và container đầu ra phải giữ quan hệ kiểu.

### 6.1. Trả về phần tử giữ nguyên kiểu nguồn

```java
static <T> T first(java.util.List<T> source) {
    if (source.isEmpty()) {
        throw new java.util.NoSuchElementException("Empty list");
    }
    return source.get(0);
}
```

Đây là method minh họa cần đặt trong class. Với `List<String>`, kiểu trả về ở điểm gọi là `String`; với `List<Integer>` là `Integer`. Nếu thay chữ ký bằng `Object first(List<?> source)`, caller chỉ nhận `Object` và đánh mất mối liên hệ kiểu đầu vào–đầu ra.

### 6.2. Hai danh sách cùng T: thêm giá trị từ nguồn sang đích

Một phiên bản đơn giản:

```java
static <T> void appendSame(
        java.util.List<T> target,
        java.util.List<T> source) {
    target.addAll(source);
}
```

Chữ ký này đòi quan hệ kiểu chặt hơn cần thiết. Nếu nguồn là `List<Integer>` và đích là `List<Number>`, API nghiệp vụ vẫn có thể thêm `Integer` vào `Number`, nhưng hai tham số `List<T>` cùng một `T` không chấp nhận hai generic instantiations đó vì `List<Integer>` và `List<Number>` bất biến.

Phiên bản linh hoạt:

```java
static <T> void append(
        java.util.List<? super T> target,
        java.util.List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

`source` cung cấp các phần tử tương thích với `T`; `target` nhận các phần tử `T`. Cùng named type parameter `T` **liên kết hai wildcard khác nhau**.

Tạo `AppendDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AppendDemo {
    static <T> void append(
            List<? super T> target,
            List<? extends T> source) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6);
        List<Number> target = new ArrayList<>();
        target.add(1.5);

        append(target, source);
        System.out.println(target);
    }
}
```

Chạy:

```bash
javac AppendDemo.java
java AppendDemo
```

`stdout`:

```text
[1.5, 2, 4, 6]
```

Điều quan trọng là **mối quan hệ cho phép truyền phần tử an toàn**, không phải ép mọi phần tử trở thành cùng runtime class. Ở lời gọi này có thể lấy `T=Integer`; `List<Integer>` làm producer, `List<Number>` làm consumer. `target` là mutable, còn `source` bất biến từ `List.of` nhưng chỉ bị đọc nên phù hợp.

### 6.3. Danh sách đầu vào kiểu T, danh sách kết quả kiểu R

Khi biến đổi từng phần tử, quan hệ đúng là `List<T>` → `List<R>` qua một hàm `T → R`.

Tạo `MapListDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class MapListDemo {
    static <T, R> List<R> map(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(3, 5, 8);
        List<String> labels = map(numbers, n -> "n=" + n);
        List<Integer> lengths = map(List.of("Java", "API"), String::length);

        System.out.println(labels);
        System.out.println(lengths);
    }
}
```

Chạy:

```bash
javac MapListDemo.java
java MapListDemo
```

`stdout`:

```text
[n=3, n=5, n=8]
[4, 3]
```

Chữ ký thể hiện:

| Ký hiệu | Nơi khai báo | Vị trí được ràng buộc |
| --- | --- | --- |
| `T` | `<T,R>` của method | Phần tử đọc từ `source`; tham số đầu vào của `mapper` |
| `R` | `<T,R>` của method | Kết quả `mapper`; phần tử `List<R>` trả về |
| `? extends T` | Wildcard dùng trong List | Cho phép nguồn có element type tương thích `T` |
| `? super T` | Wildcard dùng trong Function | Cho phép mapper xử lý một `T` |
| `? extends R` | Wildcard dùng trong Function | Cho phép mapper tạo ra subtype của `R` |

Cách tự hỏi: “Nếu caller truyền `List<Integer>` và mapper tạo `String`, liệu kiểu trả về của tôi giữ được `List<String>` không?” Với `List<R>`, có. Nếu khai báo `List<Object>`, thông tin quan hệ kiểu bị mất.

## 7. Liên hệ nhiều đối số với kiểu trả về bằng một record

Có lúc bạn muốn giữ cả hai giá trị và thêm kết quả tính toán. Mỗi phần có thể là một kiểu riêng; record tổng hợp cho phép biểu diễn quan hệ đó rõ ràng.

Tạo `EvaluationDemo.java`:

```java
import java.util.function.BiFunction;

public class EvaluationDemo {
    record Evaluation<A, B, R>(A first, B second, R result) {
    }

    static <A, B, R> Evaluation<A, B, R> evaluate(
            A first,
            B second,
            BiFunction<? super A, ? super B, ? extends R> function) {
        return new Evaluation<>(first, second, function.apply(first, second));
    }

    public static void main(String[] args) {
        Evaluation<String, Integer, String> e =
                evaluate("item-", 5, (s, n) -> s + n);

        System.out.println(e.first());
        System.out.println(e.second());
        System.out.println(e.result());
    }
}
```

Chạy:

```bash
javac EvaluationDemo.java
java EvaluationDemo
```

`stdout`:

```text
item-
5
item-5
```

`Evaluation<A,B,R>` **giữ cả ba quan hệ** giữa đối số đầu vào và kết quả. Cần phân biệt `<A,B,R>` trong khai báo method với `<A,B,R>` trong khai báo record: chúng được khai báo ở các phạm vi riêng; method dùng những biến kiểu của chính mình làm type arguments khi tạo `Evaluation`.

Ưu điểm của chữ ký `Evaluation<A,B,R>` so với `Object[]` hoặc `Map<String,Object>` là caller nhìn thấy kiểu chính xác của từng component bằng `first()`, `second()`, `result()` mà không phải đoán và cast.

## 8. Bounded type parameter: liên hệ kiểu và khả năng thao tác

Một type parameter có thể được ràng buộc bởi class/interface. Khi đó compiler vừa theo dõi quan hệ kiểu giữa nhiều đối số, vừa biết thao tác nào được phép.

Chữ ký:

```java
static <T extends Comparable<? super T>> T max(T left, T right)
```

Nghĩa là:

- `T` là một biến kiểu có tên, được khai báo tại method.
- Bound `Comparable<? super T>` cho phép so sánh một `T` với một `T` khác theo `compareTo`.
- Hai đối số `left`, `right` và kết quả cùng dùng `T`.
- Không phải mọi object đều thỏa bound; compiler từ chối các invocation không tìm được type argument hợp lệ.

Tạo `GenericMaxDemo.java`:

```java
public class GenericMaxDemo {
    static <T extends Comparable<? super T>> T max(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        Integer largerNumber = max(7, 12);
        String laterWord = max("apple", "banana");

        System.out.println(largerNumber);
        System.out.println(laterWord);
    }
}
```

Chạy:

```bash
javac GenericMaxDemo.java
java GenericMaxDemo
```

`stdout`:

```text
12
banana
```

Với `Integer`, `compareTo` so sánh số; với `String`, so sánh thứ tự từ điển theo `String.compareTo`. Compiler dùng bound để cho phép `left.compareTo(right)`. Hợp đồng kiểu **không bảo đảm cách sắp xếp phù hợp với mọi nghiệp vụ**: cách so sánh thực tế đến từ triển khai `Comparable`.

### Khi kết quả nên là kiểu Number, không phải T

So sánh hai chữ ký:

```java
static <T extends Number> T choose(T a, T b)
static <T extends Number> double average(T a, T b)
```

Đây là hai chữ ký minh họa. Ở `choose`, kiểu kết quả liên kết với `T`. Ở `average`, kết quả luôn là primitive `double`, mặc dù compiler chỉ chấp nhận đầu vào là kiểu con của `Number`. Hãy chọn kiểu trả về theo **hợp đồng thật**; không viết `T` chỉ vì phương thức đã có `<T>`.

Trong trường hợp có nhiều đầu vào kiểu số khác nhau, `<T extends Number>` có thể tìm nghiệm kiểu chung; nếu thuật toán chỉ cần gọi `doubleValue()` và luôn trả `double`, một chữ ký `double average(Number a, Number b)` có thể đơn giản hơn. Không nên làm phương thức generic khi không cần bảo toàn quan hệ kiểu.

## 9. Kiểu đích (target type) tham gia suy luận kiểu trả về

Một generic method có thể không nhận đối số nhưng vẫn suy luận được type parameter nhờ **expected type** của biểu thức.

Ví dụ JDK `Collections.emptyList()` có chữ ký gần với:

```java
public static <T> java.util.List<T> emptyList()
```

Khi viết:

```java
java.util.List<String> names = java.util.Collections.emptyList();
```

compiler dùng target type `List<String>` để suy luận `T=String`. Không cần phương thức nhận một `String` để biết `T` ở invocation này.

Tạo `TargetTypingDemo.java`:

```java
import java.util.Collections;
import java.util.List;

public class TargetTypingDemo {
    static <T> List<T> none() {
        return Collections.emptyList();
    }

    static <T> T require(T value) {
        if (value == null) {
            throw new IllegalArgumentException("null");
        }
        return value;
    }

    public static void main(String[] args) {
        List<String> words = none();
        List<Integer> numbers = TargetTypingDemo.<Integer>none();
        String value = require("Java");

        System.out.println(words.size());
        System.out.println(numbers.size());
        System.out.println(value);
    }
}
```

Chạy:

```bash
javac TargetTypingDemo.java
java TargetTypingDemo
```

`stdout`:

```text
0
0
Java
```

Điểm cần ghi nhớ:

1. `none()` khai báo `<T>` và trả `List<T>`.
2. Trong `List<String> words = none();`, kiểu mục tiêu giúp suy luận `T=String`.
3. Cú pháp `TargetTypingDemo.<Integer>none()` truyền **type witness** tường minh; đây là lựa chọn tại invocation.
4. `require("Java")` suy luận `T=String` từ đối số.
5. Chữ ký generic không tự cấm null; `require` kiểm tra null bằng logic runtime riêng.

### Explicit type witness khi nào cần?

Có thể viết `SomeClass.<String>method(args)` để buộc type parameter của method nhận giá trị `String`. Thông thường compiler suy luận được, nên type witness chỉ hữu ích khi làm rõ hoặc xử lý trường hợp ràng buộc phức tạp. Nếu witness không thỏa bound hoặc đối số, compilation thất bại.

### `var` và ngữ cảnh

`var x = none();` không có target type `List<String>` để buộc `T` như ví dụ trên; compiler có thể suy luận `List<Object>` trong trường hợp kiểu không bị ràng buộc cụ thể. Đừng dựa vào `var` để tự bảo toàn kiểu phần tử mong muốn khi initializer thiếu thông tin; dùng khai báo rõ `List<String>` hoặc type witness nếu cần.

## 10. Phân biệt “T được liên kết” với “method thực sự biến đổi đúng”

Một generic method có thể có chữ ký hợp lệ nhưng logic sai. Ví dụ:

```java
static <T> T choose(T first, T second, boolean pickFirst) {
    return pickFirst ? first : second;
}
```

Method trả đúng kiểu `T` nhưng chữ ký không nói nên chọn giá trị nào. Chỉ phần implementation định nghĩa quy tắc. Vì vậy khi đọc API phải tách:

- **Ràng buộc kiểu:** loại đối số và kiểu kết quả compiler chấp nhận.
- **Ràng buộc dữ liệu:** giá trị nào được chọn, điều kiện null, kích thước collection, thứ tự, ngữ nghĩa equals, ngoại lệ.
- **Đặc tính runtime:** mutable/immutable, side effect, tính thread-safe và type erasure.

Generic giúp trình biên dịch chứng minh một tập quan hệ kiểu; nó không chứng minh thuật toán nghiệp vụ đúng.

## 11. Vai trò của wildcard khi liên kết nhiều loại đối số

Phương thức generic và wildcard là hai công cụ bổ sung cho nhau.

### 11.1. Type parameter nối các vị trí

```java
static <T> void move(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source)
```

`T` là **điểm nối**: phần tử đọc từ source phải có thể truyền an toàn vào destination. Hai wildcard có thể đại diện cho hai type arguments cụ thể khác nhau.

### 11.2. Wildcard không phải một biến kiểu có tên

`List<?>` cho biết phần tử thuộc một kiểu chưa biết; hai lần dùng `?` ở hai tham số không tự đồng nghĩa cùng một kiểu. Nếu phương thức cần liên hệ nhiều vị trí với cùng một type, đặt tên cho type parameter thường rõ hơn.

So sánh:

```java
static <T> T getFirst(java.util.List<T> list)
static Object getFirstUnknown(java.util.List<?> list)
```

Chữ ký thứ nhất giữ quan hệ giữa kiểu phần tử và kiểu trả về. Chữ ký thứ hai chỉ bảo đảm trả `Object`, vì wildcard không xuất hiện như một biến có tên ở return type. Hai chữ ký này là minh họa và cần thêm thân phương thức để biên dịch độc lập.

### 11.3. PECS không phải luật “mọi tham số đều wildcard”

Nếu một method cần vừa lấy ra vừa đưa vào container chính xác kiểu `T`, `List<T>` có thể phù hợp hơn. Nếu method chỉ nhận nguồn để đọc và đích để ghi, `extends`/`super` thường làm API chấp nhận được nhiều type arguments mà vẫn an toàn.

Một method có thể kết hợp type parameter có tên cho **kết quả** và wildcard cho **đầu vào**. Chìa khóa là vai trò producer/consumer ở từng tham số, không phải làm chữ ký dài nhất có thể.

## 12. API JDK: đọc chữ ký quan hệ nhiều đối số và kết quả

### 12.1. `Collections.max` và Comparator

Một overload quan trọng của `Collections.max` có hình dạng:

```java
public static <T> T max(
        java.util.Collection<? extends T> coll,
        java.util.Comparator<? super T> comp)
```

Ý nghĩa: collection cung cấp các phần tử kiểu tương thích `T`; comparator có thể so sánh `T` hoặc một supertype phù hợp; kết quả là một phần tử được nhìn như `T` tại compile time. Nếu collection rỗng, method ném `NoSuchElementException`; nếu comparator không phù hợp logic nghiệp vụ, kiểu generic không sửa được thuật toán so sánh.

Tạo `CollectionsMaxDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class CollectionsMaxDemo {
    public static void main(String[] args) {
        List<String> words = List.of("tea", "java", "coffee");
        Comparator<String> byLength = Comparator.comparingInt(String::length);

        String longest = Collections.max(words, byLength);
        System.out.println(longest);
    }
}
```

Chạy `javac CollectionsMaxDemo.java` và `java CollectionsMaxDemo`:

```text
coffee
```

`T=String` liên kết collection, comparator và kết quả. Chữ ký không nói comparator phải so theo chữ cái; `Comparator.comparingInt(String::length)` mới định nghĩa thứ tự theo độ dài.

### 12.2. `Collections.copy`

Chữ ký:

```java
public static <T> void copy(
        java.util.List<? super T> dest,
        java.util.List<? extends T> src)
```

`src` sản xuất các giá trị `T`, `dest` tiêu thụ `T`. Chữ ký trả `void`, nghĩa là **không phải generic nào cũng liên kết T với kiểu trả về**. Hành vi của `Collections.copy` là thay các vị trí tương ứng ở danh sách đích, với điều kiện đích đủ lớn; nó không tự thêm vào một danh sách rỗng như `addAll`.

### 12.3. `Optional.map`

Bên trong `Optional<T>` có method dạng:

```java
public <U> java.util.Optional<U> map(
        java.util.function.Function<? super T, ? extends U> mapper)
```

`T` thuộc **generic class** `Optional<T>`, còn `U` thuộc **method** `map`. Một instance `Optional<String>` khi gọi `map(String::length)` có thể trả `Optional<Integer>`. Nếu mapper trả null, `Optional.map` tạo Optional rỗng theo API; generic type không tự cấm null.

### 12.4. `Map.computeIfAbsent`

`Map<K,V>` có method `V computeIfAbsent(K key, Function<? super K, ? extends V> mappingFunction)`.

- `K` và `V` là type parameters **của Map**, không do method này khai báo.
- Tham số `key` kiểu `K`, hàm mapping tiêu thụ `K`, sinh kết quả tương thích `V`.
- Method trả `V` theo type argument của Map hiện tại.

Ví dụ `Map<String,Integer> counts` có thể dùng `computeIfAbsent("key", String::length)` để tạo Integer nếu chưa có mapping phù hợp. Việc lưu kết quả, xử lý null và lời gọi mapping function phải theo hợp đồng `Map`/implementation; chữ ký kiểu không mô tả đầy đủ side effect.

### 12.5. `Comparator.comparing`

Overload phổ biến:

```java
public static <T, U extends Comparable<? super U>>
java.util.Comparator<T> comparing(
        java.util.function.Function<? super T, ? extends U> keyExtractor)
```

`T` là kiểu đối tượng đem so sánh, `U` là kiểu khóa trích ra. `U` phải có khả năng tự so sánh theo bound. Kết quả là `Comparator<T>`, vì comparator áp dụng cho **đối tượng nguồn**, không phải cho khóa `U`. Tách vai trò từng biến giúp đọc được các API có hai hoặc ba type parameters mà không nhầm kiểu đầu vào với kết quả.

## 13. Các lỗi biên dịch minh họa quan hệ kiểu

Đừng chạy nguyên các đoạn lỗi cùng ví dụ thành công; những dòng sau được comment để cho thấy compiler sẽ phản ứng ra sao.

### Lỗi 1: quên `<T>`

```java
// static T identity(T value) { return value; } // T chưa khai báo.
static <T> T identity(T value) { return value; }
```

Khi type parameter không được khai báo ở class/interface/method hay scope hợp lệ, tên `T` không có nghĩa.

### Lỗi 2: đòi kết quả khác kiểu mà chữ ký chưa cho phép

```java
static <T> T identity(T value) { return value; }

// Integer n = String.valueOf(identity("hello")); // Sai: String không gán Integer.
```

Phải dùng một phép biến đổi thật nếu muốn `String` → `Integer`; đừng ép generic inference làm công việc chuyển dữ liệu.

### Lỗi 3: gán hai List invariant

```java
java.util.List<Integer> ints = java.util.List.of(1, 2);
// java.util.List<Number> nums = ints; // Không hợp lệ.
java.util.List<? extends Number> numsView = ints;
```

`Integer extends Number` không làm `List<Integer>` là subtype của `List<Number>`. Wildcard `? extends Number` cho phép đọc mỗi phần tử như `Number`.

### Lỗi 4: hiểu sai kiểu trả về của function

Nếu `Function<T,R>` trả `R`, không thể mong `List<R>` tự trở thành `List<T>` khi `R` khác `T`. Đọc điểm dùng chung biến kiểu giữa mapper và kết quả: một API `map` đúng phải sử dụng cùng `R` ở `Function` và `List<R>`.

### Lỗi 5: gán `T` của class cho static method

```java
class Holder<T> {
    // static T echo(T value) { return value; } // Không được dùng class T.
    static <U> U echo(U value) { return value; }
}
```

`T` ở class thuộc ngữ cảnh tham số hóa instance; static method phải tự khai báo `<U>` nếu cần type parameter.

### Lỗi 6: raw type và unchecked conversion

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(123);
```

Đoạn này có thể biên dịch với cảnh báo, nhưng đưa `Integer` vào cấu trúc được caller tin là chứa `String`. Khi lấy ra thành `String` có thể ném `ClassCastException`. Tránh raw type để không phá quan hệ kiểu mà generic method dựa vào.

## 14. Type erasure và giới hạn của quan hệ kiểu

Generics Java chủ yếu dùng type erasure: type variable không có bound thường xóa thành `Object`, biến có upper bound xóa về cận đầu; compiler chèn cast khi cần và có thể tạo bridge method.

Ví dụ:

```java
static <T> T first(T a, T b) { return a; }
```

Về mặt diễn giải, runtime signature sau erasure dùng kiểu `Object` ở những vị trí liên quan, dù caller được compiler kiểm tra với type argument cụ thể. Vì thế một generic method có thể dùng chung bytecode cho các invocation `String` và `Integer` mà không tạo ra hai bản sao runtime.

Hệ quả:

- `<T>` không tạo `T.class` hoặc cho phép `new T()`.
- Không thể dựa vào `instanceof List<String>` để xác minh đối số kiểu của một List ở runtime; dùng `List<?>` để kiểm tra lớp/structure rồi xác thực dữ liệu nếu cần.
- Compiler có thể phát hiện lỗi kiểu ngay khi gọi method, nhưng runtime `ClassCastException` vẫn có thể xuất hiện khi hợp đồng bị phá bởi raw type, unchecked cast, reflection hoặc dữ liệu ngoại lai.
- Metadata generic của các **khai báo** có thể được phản chiếu qua Reflection; điều đó khác với việc mỗi đối tượng List mang type argument runtime riêng.

Một API nhận dữ liệu chưa được kiểm chứng từ bên ngoài không nên chỉ viết cast `(List<String>) value` và coi là an toàn. Cần kiểm tra các phần tử thực tế, xây dựng collection có kiểu rõ ràng, hoặc dùng cơ chế runtime checked phù hợp.

## 15. Khi nào nên dùng T chung, khi nào dùng A/B/R độc lập?

Đây là lựa chọn thiết kế quan trọng nhất của bài.

| Mục tiêu | Chữ ký phù hợp | Lý do |
| --- | --- | --- |
| Nhận một giá trị và trả cùng kiểu | `<T> T identity(T value)` | Nối đầu vào và kết quả bằng `T` |
| Chọn một trong hai giá trị tương thích | `<T> T choose(T a, T b)` | Hai tham số và kết quả cùng một nghiệm kiểu `T` |
| Đóng gói hai giá trị khác kiểu | `<A,B> Pair<A,B> pair(A a, B b)` | Giữ riêng hai kiểu trong kết quả |
| Tạo kết quả từ hai kiểu đầu vào | `<A,B,R> R combine(A a,B b,BiFunction<? super A,? super B,? extends R> fn)` | Kết quả `R` liên kết với mapper |
| Chuyển List<T> sang List<R> | `<T,R> List<R> map(List<? extends T> src,Function<? super T,? extends R> fn)` | T giữ input, R giữ output |
| Chuyển phần tử từ nguồn vào đích | `<T> void append(List<? super T> dst,List<? extends T> src)` | T kết nối producer/consumer |
| Tính trung bình của số | `double average(Number a,Number b)` | Không cần generic nếu kiểu trả về không cần liên kết với đầu vào |
| So sánh hai đối tượng có khả năng so sánh | `<T extends Comparable<? super T>> T max(T a,T b)` | Bound cấp khả năng `compareTo` và giữ kiểu kết quả |

**Quy tắc đọc:** nếu cùng tên `T` xuất hiện ở nhiều vị trí, hãy chỉ ra **quan hệ** mà nó diễn đạt. Nếu khai báo ba type parameters `A,B,R`, hãy chỉ ra **vai trò độc lập** và những đối số/hàm nào nối chúng. Nếu không có mối quan hệ cần bảo vệ, một kiểu cụ thể có thể rõ hơn generic.

## 16. Phương pháp phân tích chữ ký dài trong sáu bước

Lấy chữ ký:

```java
static <A, B, R> java.util.List<R> zip(
        java.util.List<? extends A> left,
        java.util.List<? extends B> right,
        java.util.function.BiFunction<? super A, ? super B, ? extends R> merger)
```

Đây là chữ ký minh họa cho thuật toán ghép hai danh sách theo vị trí; cần có thân method để chạy.

**Bước 1 — tìm nơi khai báo:** `<A,B,R>` thuộc method `zip`. Chúng độc lập ở đầu khai báo.

**Bước 2 — tìm từng vị trí xuất hiện:** `A` trong `left` và input thứ nhất của `merger`; `B` trong `right` và input thứ hai; `R` trong output của `merger` và kiểu phần tử danh sách trả về.

**Bước 3 — xác định vai trò wildcard:** `left` và `right` là producers; `merger` tiêu thụ một `A` và một `B`, sau đó tạo một `R`. Wildcard `extends` trên List và `super` trên đầu vào của function diễn đạt đúng chiều dữ liệu.

**Bước 4 — áp dụng một lời gọi:** Nếu `left` là `List<String>`, `right` là `List<Integer>` và merger tạo `String`, một nghiệm hợp lệ là `A=String`, `B=Integer`, `R=String`.

**Bước 5 — nhìn kiểu đích:** Caller có thể nhận `List<String>` mà không cần cast. Kiểu trả về không phải `List<Object>`, vì `R` giữ quan hệ với mapper.

**Bước 6 — không tự suy diễn hành vi ngoài chữ ký:** Chữ ký không nói nếu hai danh sách có độ dài khác nhau thì zip dừng ở bên ngắn, ném exception hay thêm phần tử mặc định. Điều đó phải được định nghĩa bởi triển khai và tài liệu API. Type system không tự quy định chính sách độ dài.

### Chương trình zip hoàn chỉnh

Tạo `ZipDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;

public class ZipDemo {
    static <A, B, R> List<R> zip(
            List<? extends A> left,
            List<? extends B> right,
            BiFunction<? super A, ? super B, ? extends R> merger) {
        int size = Math.min(left.size(), right.size());
        List<R> result = new ArrayList<>(size);

        for (int i = 0; i < size; i++) {
            result.add(merger.apply(left.get(i), right.get(i)));
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai", "An");
        List<Integer> scores = List.of(8, 9);
        List<String> summaries = zip(
                names, scores,
                (name, score) -> name + "=" + score);

        System.out.println(summaries);
    }
}
```

Chạy:

```bash
javac ZipDemo.java
java ZipDemo
```

`stdout`:

```text
[Lan=8, Mai=9]
```

Ở đây **thân method** chủ động dùng `Math.min` và chỉ ghép phần tử ở các vị trí tồn tại trong cả hai danh sách. Mẫu này minh họa rất rõ: chữ ký đảm bảo quan hệ kiểu giữa nguồn và kết quả; implementation quyết định cách xử lý chênh lệch kích thước.

## 17. Đánh giá chất lượng chữ ký khi thiết kế API

Khi viết generic method có nhiều đối số, hãy tự hỏi:

1. Có bao nhiêu **loại dữ liệu độc lập** cần biểu diễn? Nếu đầu vào thực sự khác loại, đừng ép chúng cùng `T` một cách không cần thiết.
2. Kết quả có phải cùng kiểu với một đầu vào không? Nếu có, hãy nối bằng cùng `T`. Nếu kết quả là kiểu mới, cân nhắc `R`.
3. Một tham số là producer hay consumer? Chọn `? extends T`/`? super T` để linh hoạt đúng hướng khi cần.
4. Thuật toán yêu cầu khả năng gì trên `T`? Nếu cần `compareTo` hoặc `doubleValue`, dùng bounded type parameter phù hợp.
5. Kiểu trả về có đủ cụ thể để caller không cần unchecked cast không? Một return `Object` không cần thiết thường là tín hiệu mất thông tin.
6. Có phụ thuộc vào subtype/invariance của collection không? `List<Integer>` không là `List<Number>`.
7. API có cần validation runtime độc lập với generic type không (null, size, mutable, dữ liệu ngoại lai)?
8. Dấu `<T>` có đang dùng chỉ để phức tạp hóa một method trả kiểu cụ thể? Nếu không có quan hệ kiểu thực sự, bỏ generic có thể tốt hơn.

Đừng tối ưu để chữ ký “trông thông minh”; ưu tiên loại ràng buộc mà caller có thể hiểu và compiler bảo vệ.

## 18. Bài tập tự kiểm tra kèm lời giải

### Bài 1 — Xác định T

```java
static <T> T second(T a, T b) {
    return b;
}
```

Hỏi: `String word = second("A","B")` có hợp lệ không? `Integer number = second(1,2)` thì sao? Kết quả là gì? Cả hai đều hợp lệ; `T` được suy luận tương ứng `String`, `Integer`; kết quả lần lượt `"B"` và `2`. `return b` là ý nghĩa của thân method, tách biệt với hợp đồng chữ ký.

### Bài 2 — Hai biến kiểu hay một?

Với mục tiêu giữ một `String` và một `Integer` trong cùng kết quả có accessor đúng kiểu, nên dùng `<T> T choose(T,T)` hay `<A,B> Pair<A,B> pair(A,B)`? Chọn `pair`: hai giá trị độc lập về kiểu và được giữ ở hai components khác nhau, còn `choose` chỉ trả một kết quả kiểu `T`.

### Bài 3 — Tìm một nghiệm inference

```java
static <T> T first(T a, T b) { return a; }
Number result = first(1, 2.5);
```

Đây là các đoạn minh họa. Vì sao không bắt buộc hai đối số cùng class runtime? Compiler tìm một `T` thỏa kiểu tĩnh của cả hai và target type `Number`; các wrapper số có thể cùng tương thích `Number`. Không cần runtime classes bằng nhau.

### Bài 4 — Liên kết collection

Hàm `append` nhận `List<? super T>` và `List<? extends T>`. Có thể gọi với đích `List<Number>` và nguồn `List<Integer>` không? Có. Nếu thay bằng hai `List<T>` thì sao? Vì invariance, không còn diễn đạt sự linh hoạt đó trực tiếp.

### Bài 5 — Kiểu kết quả mới

```java
static <T, R> java.util.List<R> map(
        java.util.List<T> src,
        java.util.function.Function<T, R> f)
```

Hỏi: với `List<String>` và `String::length`, kết quả kiểu gì? Compiler có thể suy luận `T=String`, `R=Integer`, trả `List<Integer>`. Nếu dùng `List<? extends T>` và `Function<? super T,? extends R>`, API chấp nhận được nhiều biến thể subtype hơn mà giữ quan hệ kết quả.

### Bài 6 — T có bound

Vì sao `<T extends Comparable<? super T>> T max(T,T)` có thể gọi `compareTo`, trong khi `<T> T max(T,T)` không được compiler bảo đảm? Vì bound cung cấp hợp đồng `Comparable`. Nếu bỏ bound, `T` có thể là kiểu không có `compareTo`.

### Bài 7 — Đọc chữ ký dài

Với `<A,B,R> List<R> zip(List<? extends A>,List<? extends B>,BiFunction<? super A,? super B,? extends R>)`, hãy ghi riêng: nguồn của `A`, nguồn của `B`, nơi `R` xuất hiện, chiều dữ liệu của wildcard và điều API **chưa** bảo đảm (ví dụ xử lý hai danh sách dài ngắn khác nhau). Đối chiếu với `ZipDemo` để kiểm tra.

## 19. Kết luận

Một generic method có thể biểu diễn những mối quan hệ kiểu mà các kiểu cụ thể hoặc `Object` không diễn đạt được: **một `T` nối nhiều tham số với kết quả; `A` và `B` giữ các kiểu đầu vào khác nhau; `R` nối kết quả của mapper với return type; wildcard mở rộng miền đối số có thể truyền an toàn; bound cho phép thao tác trên biến kiểu**.

Khi đọc chữ ký, luôn tìm **nơi khai báo từng biến kiểu, tất cả vị trí nó xuất hiện và nghiệm type inference ở một lời gọi cụ thể**. Khi thiết kế, giữ đúng mối quan hệ cần compiler bảo vệ, giải thích riêng hành vi runtime và tránh giả định rằng “cùng T” nghĩa là cùng lớp runtime. Làm được vậy, bạn có thể tự tin viết những API từ `identity`, `pair`, `combine` đến `append`, `map` và `zip` mà caller nhận được kiểu chính xác, không phải ép kiểu thủ công.