# Kiểm tra generics, suy luận kiểu và trường hợp không suy luận được trong Java

Java kiểm tra tính hợp lệ của kiểu ở **thời điểm biên dịch**. Với generics, nhiệm vụ này không chỉ là so sánh hai tên class: trình biên dịch còn phải xác định các **type argument**, áp dụng **ràng buộc (bounds)**, kiểm tra khả năng gán/đối số, phân giải overload và nhiều khi tự tìm type argument của lời gọi generic method hoặc constructor. Quá trình tự tìm đó gọi là **type inference**.

Khi inference thành công, chương trình thường ngắn và vẫn an toàn về kiểu. Khi thất bại, `javac` có thể báo `cannot infer type arguments`, `cannot infer type-variable(s)` hoặc `inference variable ... has incompatible bounds`. Muốn sửa đúng, phải biết compiler đang thu thập ràng buộc nào và tại sao không có kiểu nào thỏa mãn chúng.

Bài học sử dụng Java 17+ và các quy tắc của Java Language Specification (JLS). Những ví dụ cố ý gây lỗi đều được đánh dấu riêng; không đưa chúng vào cùng một chương trình runnable.

## 1. Generics là gì và compiler kiểm tra những gì?

Một generic declaration khai báo **tham số kiểu** để định nghĩa class, interface, record hoặc method theo kiểu tổng quát:

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

`T` là *type parameter* của `Box`. Khi dùng `Box<String>`, `String` là *type argument*. Compiler có thể biết rằng `get()` trả về `String` ở phía sử dụng, thay vì buộc người lập trình ép kiểu từ `Object`.

Generics giúp kiểm tra các quan hệ như:

- `Box<String>` nhận `String` khi tạo và trả kết quả theo kiểu `String`.
- `List<Integer>` không được gán trực tiếp sang `List<Number>` vì generic type thông thường là **invariant**.
- `<T extends Number>` chỉ cho phép type argument thỏa bound `Number`.
- `List<? extends Number>` và `List<? super Integer>` mô tả những tập hợp kiểu có quan hệ khác nhau; cách đọc/ghi vào chúng khác nhau.
- Overload, generic methods, lambda và method reference có thể cần **target type** để xác định biểu thức hợp lệ.

Việc một lời gọi không có `<String>` hoặc `<Integer>` viết tường minh **không** có nghĩa là bỏ kiểm tra kiểu. Compiler phải suy luận các type argument sao cho ràng buộc của lời gọi thỏa mãn.

## 2. Phân biệt ba trường hợp: kiểu được khai báo, kiểu được suy luận và kiểu lúc chạy

```java
List<String> words = new ArrayList<>();
```

`List<String>` là kiểu khai báo của biến. `ArrayList<>` sử dụng **diamond operator**, để compiler suy ra type argument phù hợp với ngữ cảnh, ở đây là `String`.

```java
var words = new ArrayList<String>();
```

`var` cho phép compiler suy ra **kiểu của biến cục bộ** từ biểu thức khởi tạo; kết quả ở đây là `ArrayList<String>`. `var` không tạo ra biến “dynamic” và không tắt generic checking.

```java
var values = new ArrayList<>();
values.add("A");
values.add(10);
```

Với không có target type cụ thể hơn, constructor diamond ở ví dụ này suy ra kiểu phần tử `Object`. Cả `String` và `Integer` đều gán được vào `Object`. Compiler không thay đổi type argument của `values` thành `String` chỉ sau khi thấy lệnh `add("A")`.

Cuối cùng, runtime JVM dùng cơ chế **type erasure** cho phần lớn generic type parameter. Thông tin kiểu tĩnh được compiler kiểm tra trước khi sinh bytecode; điều này không có nghĩa mỗi `List<String>` sở hữu một class runtime khác với `List<Integer>`. Bởi vậy `instanceof List<String>` không hợp lệ: loại kiểm tra phần tử cụ thể này không được bảo đảm ở runtime bởi erasure.

**Ba câu hỏi khác nhau:** kiểu khai báo là gì; compiler suy ra type argument nào; runtime thật sự mang class/object nào? Không nên trộn ba tầng để diễn giải lỗi.

## 3. Generic method và các nguồn tạo ràng buộc cho inference

Một generic method khai báo tham số kiểu trước kiểu trả về:

```java
static <T> T identity(T value) {
    return value;
}
```

Ở lời gọi `String name = identity("Lan");`, compiler tìm `T` sao cho đối số `"Lan"` hợp lệ với tham số `T`, đồng thời kết quả dùng được ở nơi cần `String`. Trong trường hợp này, `T = String` là lựa chọn phù hợp.

Có ba nguồn ràng buộc thường gặp:

1. **Đối số truyền vào:** `identity(42)` tạo quan hệ từ kiểu `Integer` của biểu thức đối số tới tham số `T`.
2. **Bound đã khai báo:** `<T extends Number>` yêu cầu giá trị suy ra phải thuộc phạm vi kiểu cho phép bởi `Number`.
3. **Ngữ cảnh kết quả (*target type*):** phép gán, `return`, một số ngữ cảnh đối số và lambda có thể ràng buộc kiểu trả về của generic invocation.

Ví dụ:

```java
static <T> List<T> singleton(T element) {
    return List.of(element);
}

List<String> a = singleton("x");
List<Number> b = singleton(42);
```

Trong `b`, compiler có thể dùng target type `List<Number>` để chọn `T = Number`, đồng thời chấp nhận đối số `Integer` vì `Integer` là subtype của `Number`. **Không có quy tắc chung rằng inference luôn lấy đúng runtime class của đối số làm `T`.** Target type, bounds và tương thích kiểu cùng tham gia quyết định.

JLS mô tả thuật toán inference của generic method qua việc hình thành và giải hệ ràng buộc trong ``18`. Đây là một cơ chế có quy tắc, không phải compiler đoán dựa trên tên biến hay dữ liệu lúc chạy.

## 4. Ví dụ hoàn chỉnh Java 17+: inference và type checking

Lưu tệp `GenericInferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;

public class GenericInferenceDemo {
    static <T> List<T> singleton(T element) {
        return List.of(element);
    }

    static <T extends Number> double twice(T number) {
        return number.doubleValue() * 2;
    }

    static <T extends Comparable<? super T>> T greatest(
            List<? extends T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty values");
        }
        T best = values.get(0);
        for (T candidate : values) {
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    static <T> void copy(List<? super T> destination,
                         List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    record Pair<A, B>(A first, B second) {}

    public static void main(String[] args) {
        List<String> names = singleton("Lan");
        System.out.println("names=" + names);

        System.out.println("twice=" + twice(4));
        System.out.println("greatest=" + greatest(List.of(3, 9, 2)));

        List<Number> numbers = new ArrayList<>();
        copy(numbers, List.of(3, 5));
        System.out.println("copy=" + numbers);

        Pair<String, Integer> pair = new Pair<>("id", 7);
        System.out.println("pair=" + pair.first() + ":" + pair.second());

        List<String> empty = Collections.emptyList();
        System.out.println("emptySize=" + empty.size());

        Function<String, Integer> length = String::length;
        System.out.println("length=" + length.apply("Java"));
    }
}
```

Biên dịch/chạy từ thư mục chứa file với JDK 17 trở lên:

```bash
mkdir out
javac -encoding UTF-8 -d out GenericInferenceDemo.java
java -cp out GenericInferenceDemo
```

Stdout chính xác:

```text
names=[Lan]
twice=8.0
greatest=9
copy=[3, 5]
pair=id:7
emptySize=0
length=4
```

Giải thích từng phần:

- `singleton("Lan")` suy luận `T = String` và trả `List<String>` theo target type.
- `twice(4)` boxing `int` thành `Integer` để phù hợp generic type parameter `T extends Number`; phương thức trả về primitive `double`.
- `greatest(List.of(3, 9, 2))` dùng kiểu phần tử có thể so sánh qua `Comparable<? super T>`; kết quả là `9`.
- `copy` diễn đạt quan hệ đọc từ `List<? extends T>` và ghi vào `List<? super T>`; `Integer` phù hợp đích `List<Number>`.
- `new Pair<>("id", 7)` sử dụng diamond để suy luận type arguments của generic record constructor trong ngữ cảnh `Pair<String, Integer>`.
- `Collections.emptyList()` là generic method trả về `List<T>`; target `List<String>` cho phép suy luận `T = String` dù method không có đối số.
- `String::length` là method reference cần target functional interface `Function<String, Integer>` để compiler xác định chữ ký lời gọi.

Không có tham số kiểu nào được “phát hiện” bằng cách đọc dữ liệu của `List` lúc runtime. Mọi quyết định ở ví dụ được kiểm tra từ chữ ký, kiểu biểu thức và ngữ cảnh compile time.

## 5. Bounds: điều kiện bắt buộc của type parameter

Generic declaration có thể giới hạn type argument:

```java
static <T extends Number> double squared(T value) {
    return value.doubleValue() * value.doubleValue();
}
```

`squared(3)` và `squared(2.5)` hợp lệ vì `Integer` và `Double` kế thừa `Number`. `squared("3")` không hợp lệ: `String` không thuộc bound `Number`.

Bound có thể bao gồm một class hoặc interface, và nhiều interface:

```java
static <T extends Number & Comparable<T>> T retain(T value) {
    return value;
}
```

Trong Java, nếu có class bound thì nó phải đứng trước các interface bound sau dấu `&`. Ví dụ này có thể nhận `Integer` vì `Integer extends Number` và triển khai `Comparable<Integer>`; không nên kết luận mọi subclass của `Number` đều hợp lệ cho bound này.

Một dạng đặc biệt hay dùng:

```java
static <T extends Comparable<? super T>> T chooseMax(
        T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Dấu `? super T` hỗ trợ kiểu triển khai `Comparable` của một supertype phù hợp. Ví dụ điển hình là `Collections.max` có ràng buộc kiểu theo hướng này. Đây là trường hợp **bound được khai báo trong chữ ký method**, khác với wildcard trong tham số của một biến.

Nếu compiler báo `incompatible bounds`, đừng chỉ thêm cast: hãy hỏi liệu các ràng buộc từ input, target type và `extends` có thể đồng thời đúng không.

## 6. Tính bất biến của generic type: List<Integer> không phải List<Number>

`Integer` là subtype của `Number`, nhưng **`List<Integer>` không phải subtype của `List<Number>`**. Ví dụ cố tình không biên dịch:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = integers; // lỗi: incompatible types
```

Nếu phép gán được cho phép, người gọi có thể thêm `Double` vào danh sách vốn tuyên bố chỉ chứa `Integer`. Generics chặn điều đó tại compile time.

Hai thiết kế đúng tùy mục đích:

- **Chỉ đọc theo dạng Number:** nhận `List<? extends Number>`. Có thể lấy phần tử với kiểu `Number`, nhưng không thể tùy ý thêm một `Integer` hay `Double` vào danh sách.
- **Muốn một danh sách lưu nhiều subtype của Number:** tạo `List<Number> numbers = new ArrayList<>();` rồi thêm `Integer` và `Double` vào danh sách ấy.

Ví dụ:

```java
List<? extends Number> source = List.of(1, 2);
Number first = source.get(0); // hợp lệ
// source.add(3);              // không hợp lệ

List<Number> mixed = new ArrayList<>();
mixed.add(1);
mixed.add(2.5);
```

Các snippet trong mục này dùng import `java.util.List` và `java.util.ArrayList`; chúng minh họa các dòng nằm trong một phương thức, không phải file độc lập. Khả năng ghi vào wildcard phụ thuộc cả kiểu phần tử lẫn loại wildcard, không được suy từ subtype của `Number` một cách cơ học.

## 7. Wildcard, capture và nguyên tắc PECS

Một wildcard là đại diện cho một kiểu chưa biết nhưng chịu giới hạn:

| Kiểu | Đọc ra an toàn | Ghi giá trị vào an toàn |
| --- | --- | --- |
| `List<? extends Number>` | `Number` | Không thêm một `Number` cụ thể tùy ý; chỉ `null` |
| `List<? super Integer>` | `Object` | Có thể thêm `Integer` (và subtype phù hợp) |
| `List<?>` | `Object` | Không thêm giá trị cụ thể khác `null` |
| `List<Number>` | `Number` | Có thể thêm các giá trị là subtype của `Number` |

Quy tắc gợi nhớ **PECS: Producer Extends, Consumer Super**. Nếu một tham số chủ yếu **sản xuất** các giá trị kiểu `T` để ta đọc, cân nhắc `? extends T`. Nếu một tham số chủ yếu **tiêu thụ** các giá trị kiểu `T` mà ta ghi vào, cân nhắc `? super T`. Đây là mẹo thiết kế API, không thay thế việc kiểm tra chính xác yêu cầu đọc/ghi.

Trường hợp lỗi nổi tiếng là **capture of ?**:

```java
static void replaceFirst(List<?> values, Object element) {
    values.set(0, element); // không hợp lệ
}
```

Compiler không biết kiểu phần tử được wildcard đại diện. Một `List<?>` có thể thực chất là `List<String>`, nên không thể cho phép đặt một `Object` tùy ý vào đó. Cast mù hoặc chuyển sang raw type có thể tạo lỗi lúc chạy.

Khi cần giữ nguyên chính kiểu phần tử chưa biết của cùng một danh sách, dùng **capture helper**:

```java
import java.util.List;

public class CaptureDemo {
    static void swapFirstTwo(List<?> list) {
        swapCaptured(list);
    }

    private static <T> void swapCaptured(List<T> list) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words = new java.util.ArrayList<>(
                List.of("a", "b", "c"));
        swapFirstTwo(words);
        System.out.println(words);
    }
}
```

Chạy tệp `CaptureDemo.java`:

```bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
```

Stdout:

```text
[b, a, c]
```

Khi gọi `swapCaptured(list)`, compiler coi wildcard ở lần gọi ấy như một **capture type** cụ thể nhưng không lộ tên; helper `<T>` giữ hai phép `get`/`set` nhất quán. Chương trình không thêm một đối tượng có kiểu không phù hợp vào danh sách.

Một lưu ý khác: tính bất biến của `List<T>` và sự khác nhau của wildcard không được bỏ qua bằng việc suy luận `T` là `Object` khi chữ ký method cần một `List<T>` cụ thể.

## 8. Type inference từ ngữ cảnh: target typing và poly expression

Xét:

```java
List<String> names = java.util.Collections.emptyList();
```

`emptyList()` không có đối số, nên chỉ nhìn vào input không đủ để quyết định `T`. Phép gán cung cấp **target type** `List<String>`; lời gọi generic method có thể dùng ngữ cảnh đó để chọn `T = String`.

Nếu viết:

```java
var names = java.util.Collections.emptyList();
```

không có target `List<String>` từ một khai báo kiểu tường minh, nên kiểu suy ra có thể là `List<Object>`. Do `emptyList()` trả một danh sách bất biến, việc cố `add` vào nó còn gây `UnsupportedOperationException` lúc runtime; đây là vấn đề **khác** với inference.

Lambda và method reference cũng có bản chất **poly expression** trong các ngữ cảnh được ngôn ngữ quy định:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

Kiểu của tham số `text` được xác định từ target functional interface, không phải từ một annotation `String` trong lambda. Đổi target type có thể làm cùng một lambda hợp lệ hoặc không hợp lệ.

Ví dụ khai báo generic method:

```java
static <T, R> R transform(
        T input,
        java.util.function.Function<? super T, ? extends R> f) {
    return f.apply(input);
}

int length = transform("Java", String::length);
```

Method reference `String::length`, kiểu đầu vào `String`, kiểu trả về `int` và phép gán tới `int` giúp compiler xác định kiểu phù hợp, gồm boxing khi cần. Không nên coi generic method inference và overload resolution là hai quá trình luôn độc lập: các quy tắc về applicability và target typing có thể tương tác qua nhiều bước.

## 9. Overload và inference tương tác với nhau

Một method name có thể có nhiều overload. Trước khi chọn được lời gọi hợp lệ, compiler xét khả năng áp dụng của các candidate, conversion, generic bounds và độ đặc hiệu (*most specific*).

Ví dụ đơn giản:

```java
static String show(Integer value) {
    return "Integer";
}

static String show(Number value) {
    return "Number";
}

// Trong một phương thức:
String result = show(3); // "Integer"
```

Lời gọi dùng literal `3` có thể boxing thành `Integer`, khiến overload `show(Integer)` đặc hiệu hơn overload `show(Number)` cho ví dụ này. Với generic overload và lambda, việc lựa chọn candidate còn phức tạp hơn; inference có thể tham gia ở các giai đoạn xác định applicability và kết quả.

Trường hợp **mơ hồ** cố ý không biên dịch:

```java
static void pick(java.io.Serializable value) {}
static void pick(Cloneable value) {}

// pick(null); // lỗi: ambiguous reference
```

`null` có thể chuyển sang cả hai kiểu tham chiếu, và ở tình huống này không có candidate nào đặc hiệu hơn candidate kia. Đây là lỗi overload resolution; không phải mọi lỗi “không suy luận được” đều do thiếu type argument của generics.

Một cách sửa là làm rõ ý định:

```java
pick((java.io.Serializable) null);
```

Trong mã thực tế, cast chỉ nên xuất hiện khi nó phản ánh contract thật. Không thêm ép kiểu để che một API overload thiếu rõ ràng.

## 10. Vì sao compiler báo không suy luận được?

Dưới đây là các nhóm lỗi thường gặp. Mỗi đoạn được đánh dấu **cố tình không biên dịch**; trình biên dịch có thể sử dụng cách diễn đạt diagnostic khác nhau giữa các phiên bản.

### 10.1 Ràng buộc từ List<T> và đối số mâu thuẫn

```java
static <T> void addValue(List<T> target, T value) {
    target.add(value);
}

// Trong một phương thức:
List<String> words = new ArrayList<>();
addValue(words, 123); // không hợp lệ
```

Từ `List<String>`, compiler có một ràng buộc buộc `T` phù hợp với phần tử `String`. Đối số `123` cần boxing sang `Integer` và đòi tương thích với `T`. Không có một `T` thỏa cả hai khi chữ ký dùng `List<T>` invariant. Chọn `T = Object` không làm `List<String>` trở thành `List<Object>`.

Nếu method chỉ đọc một tập phần tử và nhận giá trị tương thích ở mức một supertype, hãy thiết kế lại chữ ký đúng nhu cầu. Nếu method thực sự thêm `Integer`, phải truyền vào một danh sách có thể chứa `Integer`; không nên chuyển `List<String>` sang raw type để “ép qua” lỗi.

### 10.2 Type argument vi phạm bound

```java
static <T extends Number> T same(T value) {
    return value;
}

String text = same("hello"); // không hợp lệ
```

Kiểu `String` không thỏa `T extends Number`; target type `String` cũng không thể khiến bound biến mất. Hướng sửa là dùng loại dữ liệu thuộc bound hoặc thay đổi contract của method khi business logic thực sự không yêu cầu `Number`.

### 10.3 Kết quả không hợp target type

```java
static <T> T identity(T value) {
    return value;
}

String text = identity(123); // không hợp lệ
```

Đối số đưa vào là `Integer`; kết quả được gán cho `String`. Không có conversion hợp lệ thỏa yêu cầu đó. Đây là lỗi kiểu hợp lý, không phải thiếu “gợi ý” cho compiler. Viết `GenericClass.<String>identity(123)` (nếu method ở lớp tương ứng) vẫn không làm số nguyên trở thành chuỗi.

### 10.4 Wildcard capture không cho ghi một giá trị tùy ý

```java
List<? extends Number> numbers = List.of(1, 2);
numbers.add(3); // không hợp lệ
```

`? extends Number` có thể đại diện cho `Integer`, `Double` hoặc một subtype khác. Compiler không thể bảo đảm giá trị `3` luôn phù hợp với danh sách thực tế. Dùng một API chỉ đọc, hoặc đổi kiểu destination thành `List<Number>` nếu cần chấp nhận nhiều subtype.

### 10.5 Không có target type đủ cụ thể

```java
var list = new ArrayList<>();
```

Đoạn này **hợp lệ**, nhưng compiler suy luận `ArrayList<Object>`, có thể rộng hơn loại người viết mong muốn. Nếu mục tiêu là một danh sách chỉ chứa `String`, hãy viết:

```java
List<String> list = new ArrayList<>();
// Hoặc, khi muốn biến có kiểu ArrayList<String>:
var other = new ArrayList<String>();
```

**Thiếu target type không nhất thiết gây lỗi biên dịch; đôi khi nó dẫn tới kiểu được suy luận quá rộng.** Cần đọc kết quả inference trong IDE hoặc dựa vào assignment phù hợp, thay vì giả sử compiler sẽ đoán từ các lệnh sau.

### 10.6 Lambda và method reference thiếu ngữ cảnh chức năng

```java
// var action = x -> x.toString(); // không hợp lệ
```

Một lambda không tự có kiểu độc lập để `var` lấy làm kiểu từ initializer. Cần functional interface đích:

```java
java.util.function.Function<Object, String> action =
        x -> x.toString();
```

Tương tự, method reference cần target functional interface hoặc ngữ cảnh generic invocation có thể cung cấp nó. Viết rõ kiểu tham số lambda, hoặc đưa kết quả vào biến kiểu tường minh, có thể giúp compiler giải quyết tham chiếu.

## 11. Cách sửa theo nguyên nhân: signature, target type hay explicit type witness?

Đừng mặc định rằng mọi lỗi inference đều nên giải bằng cast. Thử lần lượt các hướng có cơ sở:

**A. Sửa kiểu đầu vào phù hợp contract.** Với `<T extends Number>`, truyền `Integer`/`Double` thay vì `String`. Với `List<String>`, chỉ thêm `String`.

**B. Dùng target type cụ thể khi cần.** Đổi `var empty = Collections.emptyList()` thành `List<String> empty = Collections.emptyList()` nếu mục đích là danh sách `String`.

**C. Viết type witness tường minh.** Đôi khi generic method không thể rút ra type argument mà bạn định dùng chỉ từ ngữ cảnh:

```java
List<String> names = java.util.Collections.<String>emptyList();
```

Dạng `ClassName.<Type>method(...)` có thể giải thích ý định. Với static import hoặc method call phức tạp, qualifier và cú pháp phải tuân theo ngữ pháp Java. Type witness chỉ hợp lệ khi **mọi bound và đối số vẫn tương thích**; nó không có quyền bỏ qua type checking.

**D. Thiết kế lại generic method.** Nếu một method vừa đọc từ danh sách nguồn vừa ghi vào đích có quan hệ subtype, thường nên dùng:

```java
static <T> void copy(List<? super T> target,
                     List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

Với Java Collections, công cụ tương đương thường đã có sẵn như `Collections.copy`, nhưng contract của `Collections.copy` còn đòi kích thước destination ít nhất bằng source và **ghi đè vị trí** chứ không append. Phương thức tự viết ở đây chỉ để minh họa PECS/inference; không đồng nhất hành vi hai API.

**E. Tách biểu thức lớn thành các biến trung gian có kiểu.** Đặc biệt hữu ích với pipeline Stream, `Comparator.comparing`, lambda và method reference. Việc khai báo `Function<Person, String> keyExtractor = Person::name;` có thể giúp chỉ ra chính xác phần nào compiler không suy ra được.

**F. Kiểm tra overload và import.** Nếu có nhiều candidate hợp lệ/mơ hồ, sửa chữ ký, đổi tên method hoặc chỉ định rõ target thay vì thêm generic cast vào vị trí không liên quan.

## 12. Stream, Comparator và method reference: trường hợp thực tế

Một ví dụ Java 17+ độc lập:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorInferenceDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        List<Person> people = List.of(
                new Person("Minh", 23),
                new Person("Lan", 21)
        );

        List<String> names = people.stream()
                .sorted(Comparator.comparingInt(Person::age))
                .map(Person::name)
                .toList();

        System.out.println(names);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ComparatorInferenceDemo.java
java ComparatorInferenceDemo
```

Stdout:

```text
[Lan, Minh]
```

Vì Stream có kiểu phần tử `Person`, compiler có thể suy ra rằng `Person::age` là hàm lấy `int` của một `Person`. `Comparator.comparingInt` cung cấp functional interface đích, `sorted` nhận một comparator hợp lệ cho phần tử stream, `map(Person::name)` cho ra `Stream<String>`, và `toList()` trả `List<String>` (không được dùng để thêm phần tử mới sau đó vì danh sách này không hỗ trợ các thao tác sửa đổi).

Nếu thay `Person::age` bằng một method reference không khớp kiểu tham số hoặc kết quả, compiler có thể báo lỗi inference trong một lời gọi “ở bên ngoài” dù nguyên nhân là một method reference sâu bên trong. Khi đó tách chain thành nhiều khai báo có kiểu rõ:

```java
Comparator<Person> byAge = Comparator.comparingInt(Person::age);
List<Person> sorted = people.stream().sorted(byAge).toList();
```

Đây là hai câu lệnh minh họa **bên trong một phương thức có biến `people`**, không phải file độc lập. Cách tách làm diagnostic chính xác và dễ hiểu hơn, đồng thời không thay đổi ý định tính toán.

## 13. Lỗi unchecked, raw types và giới hạn do type erasure

Có những trường hợp code biên dịch với cảnh báo nhưng không bảo đảm an toàn về kiểu:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;      // raw type: mất kiểm tra phần tử kiểu String
        raw.add(123);         // unchecked call, compiler có thể cảnh báo

        String first = words.get(0); // ClassCastException khi chạy
        System.out.println(first);
    }
}
```

Chương trình này **cố ý gây lỗi runtime**, không có stdout thành công. `raw.add(123)` có thể biên dịch với *unchecked warning*, nhưng đã đưa `Integer` vào nơi nhìn từ `List<String>`. Khi lấy phần tử qua reference có generic type `List<String>`, cast ngầm tới `String` thất bại.

Để xem cảnh báo rõ hơn, chạy:

```bash
javac -Xlint:rawtypes,unchecked RawTypeDemo.java
java RawTypeDemo
```

Không nên cố định nguyên văn diagnostic hoặc stack trace cho mọi JDK. Cảnh báo `unchecked` có ý nghĩa: compiler không thể chứng minh một phần của chuyển đổi/gọi method là type-safe.

Một ví dụ khác do erasure: không thể viết `new T[10]` trong phần thân generic method theo cách thông thường; không thể dùng `new List<String>[10]` hoặc `instanceof List<String>` vì kiểu tham số hóa ấy không reifiable. Có những ngoại lệ/đường thay thế an toàn bằng collection, `Class<T>` token, array factory hoặc generic helper, nhưng không nên che hạn chế bằng raw cast vô điều kiện.

**Điểm mấu chốt:** generic inference hoạt động ở compile time, trong khi JVM cần kiểm tra các kiểu runtime mà nó thực sự giữ lại được. Đó là nguyên nhân nhiều thao tác có vẻ tự nhiên đối với generic array hoặc runtime type check lại bị từ chối.

## 14. Suy luận kiểu không phải là “tìm kiểu chung tùy ý”

Ở những lời gọi nhiều đối số, compiler có thể tìm một supertype chung hoặc một kiểu giao (*intersection type*) trong quá trình giải ràng buộc. Nhưng không thể suy ra rằng mọi cặp đối số đều nên gom thành `Object`: kết quả còn bị giới hạn bởi chữ ký method, type bound, generic invariance và target context.

Ví dụ:

```java
static <T> List<T> pair(T left, T right) {
    return List.of(left, right);
}

// Có thể chọn T đủ rộng để nhận cả Integer và Double:
List<Number> values = pair(1, 2.5);
```

Lời gọi này **hợp lệ**: compiler có thể chọn một `T` tương thích với cả hai đối số và target `List<Number>`. Điều này khác với ví dụ `addValue(List<String>, 123)` vì `List<String>` ở vị trí input bất biến buộc type argument theo một cách chặt hơn.

Nếu viết `List<String> values = pair(1, 2.5);` thì không thể chỉ dùng target `String` để khiến cả `Integer` và `Double` tương thích với `String`.

Với bounded type parameter, compiler còn phải bảo đảm subtype relationship với upper bound. Ví dụ `<T extends Number>` sẽ không được suy thành `Object` để chấp nhận bất kỳ đối số nào, vì `Object` không đáp ứng bound `Number`.

## 15. Chữ ký generic API có thể khiến inference dễ hoặc khó

Xét hai cách khai báo một hàm đọc phần tử:

```java
static <T> void printAll(List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}

static void printNumbers(List<? extends Number> values) {
    for (Number value : values) {
        System.out.println(value);
    }
}
```

`printAll` có thể nhận nhiều loại `List<T>` khác nhau trong **mỗi lời gọi**. Nhưng nếu method không cần thể hiện hay liên kết `T` ở nơi khác trong chữ ký, wildcard `List<?>` cũng có thể diễn đạt ý định chỉ đọc. `printNumbers` chỉ chấp nhận các list có phần tử phù hợp Number; wildcard cho phép `List<Integer>` hoặc `List<Double>`.

Quy tắc thiết kế thực tế:

- Dùng **type parameter `<T>`** khi cần duy trì một quan hệ kiểu giữa hai hay nhiều vị trí (tham số, kết quả, callback, destination, source) hoặc khi logic body cần tên kiểu đó.
- Dùng **wildcard** khi cần thể hiện hướng đọc/ghi hoặc sự chấp nhận một họ kiểu nhưng không cần đặt tên mối quan hệ.
- Tránh **raw type** trừ khi tương tác với API legacy và có biện pháp kiểm tra/cô lập hợp lý.
- Chọn **bound thực sự cần thiết**; `<T extends Comparable<? super T>>` cung cấp khả năng so sánh, nhưng cũng thu hẹp các kiểu được phép dùng.
- Đừng dùng `<T> T convert(Object value)` rồi cast bên trong như thể compiler có thể bảo đảm conversion có thật. Một chữ ký generic không có liên hệ giữa input và output có thể che rủi ro runtime.

Kiểu tốt giúp inference đủ thông tin và lỗi xuất hiện ở đúng vị trí. Chữ ký mơ hồ khiến compiler phải chọn kiểu rộng hơn dự định hoặc không thể tìm lời giải.

## 16. Cách đọc lỗi `javac` theo quá trình kiểm tra ngữ nghĩa

Khi gặp thông báo liên quan inference, hãy nhìn các thành phần sau:

| Thành phần diagnostic | Câu hỏi cần trả lời |
| --- | --- |
| `required` / `found` | Compiler kỳ vọng kiểu gì, biểu thức đang cung cấp kiểu gì? |
| `cannot infer type-variable(s)` | Generic method/constructor có type parameter nào đang cần giải? |
| `inference variable T has incompatible bounds` | Các upper/lower/equality constraints nào xung đột? |
| `equality constraints` | Quan hệ nào buộc một type variable khớp với một type argument nhất định? |
| `upper bounds` | Kiểu suy ra phải là subtype của những kiểu nào? |
| `lower bounds` | Kiểu suy ra phải là supertype của những kiểu nào? |
| `capture of ?` | Wildcard đang đại diện cho một kiểu cụ thể nhưng không biết tên? |
| `reference to ... is ambiguous` | Có nhiều overload mà compiler không thể xác định một candidate tối ưu? |
| `unchecked conversion` | Compiler đang thiếu bằng chứng type-safe do raw type/erasure? |

Ví dụ minh họa một lỗi inference:

```java
static <T> void addValue(List<T> list, T value) {
    list.add(value);
}

List<String> words = new ArrayList<>();
addValue(words, 123);
```

Có thể diễn giải: `List<T>` cần tương thích với `List<String>` (làm `T` gắn chặt với `String`), trong khi đối số `123` có kiểu `int` và được boxing thành `Integer`, không gán được vào `String`. Thông báo lỗi thực tế có thể khác chữ, nhưng xung đột kiểu nằm ở chính quan hệ này.

Đừng sửa bằng cách xóa generic, thêm cast raw hoặc vô hiệu hóa warning. Hãy sửa **logic dữ liệu** hoặc chữ ký API phù hợp với quan hệ kiểu mong muốn.

## 17. Một phương pháp gỡ lỗi inference từng bước

1. **Rút gọn lời gọi lỗi.** Giữ lại một generic method/constructor và các biểu thức đối số liên quan; bỏ chain và annotation không cần thiết.
2. **Ghi chữ ký đầy đủ.** Liệt kê type parameters, upper bounds, kiểu từng tham số và kiểu trả về.
3. **Ghi kiểu tĩnh của từng đối số.** Phân biệt literal primitive, boxing, wildcard, raw type, generic parameter, lambda và method reference.
4. **Ghi target type nếu có.** Phép gán `List<String> x = ...` khác `var x = ...`; gọi generic method trong đối số của method khác có thể có ngữ cảnh riêng.
5. **Thử type argument cụ thể trên giấy.** Ví dụ `T = String` có hợp bound và tất cả đối số không? `T = Number` có phá invariance `List<String>` không?
6. **Kiểm tra wildcard/capture.** Có đang muốn ghi vào producer `? extends T` hoặc lấy kiểu quá cụ thể từ consumer `? super T`?
7. **Tách lambda, method reference và chain.** Dùng biến trung gian có kiểu để xác định lỗi ở tầng nào.
8. **Chỉ định type witness khi ý định hợp lệ.** Nếu compiler vẫn báo lỗi với type witness, đó có thể là xung đột thật, không phải một việc “suy luận kém”.
9. **Bật cảnh báo phù hợp.** `javac -Xlint:unchecked,rawtypes` có thể chỉ ra đoạn code làm mất an toàn kiểu.
10. **Kiểm tra phiên bản JDK và cấu hình compiler.** Cơ chế target typing và API thư viện tiến hóa theo phiên bản Java; luôn biên dịch với đúng `--release`/toolchain của dự án trước khi kết luận.

## 18. Bài tập tự kiểm tra

**Bài 1.** Tại sao `List<Number> n = new ArrayList<Integer>();` không hợp lệ? Vì generic type invariant; nếu cho phép, reference `List<Number>` có thể chèn `Double` vào list chỉ chứa `Integer`.

**Bài 2.** Với `static <T> T identity(T value)`, câu `String s = identity(42);` có hợp lệ không? Không. Kiểu của đối số và target không đồng thời tương thích với một `T` đáp ứng các phép chuyển đổi theo chữ ký.

**Bài 3.** `List<String> xs = Collections.emptyList();` có cần viết `<String>` trước `emptyList` không? Không, target typing thường đủ. Viết tường minh `Collections.<String>emptyList()` vẫn hợp lệ.

**Bài 4.** Vì sao `List<? extends Number>` không cho thêm `Integer`? Vì wildcard có thể thực tế đại diện cho `Double` hoặc một subtype `Number` khác; chỉ đọc dưới kiểu `Number` là an toàn.

**Bài 5.** Dự đoán output `GenericInferenceDemo`: danh sách một tên, `twice(4) = 8.0`, `greatest` trả `9`, destination được append `3` và `5`, record giữ `id:7`, danh sách rỗng có size `0` và `"Java".length() = 4`.

**Bài 6.** Khi API chỉ muốn nhận source `List<Integer>` và ghi kết quả vào destination `List<Number>`, dùng `<T> void copy(List<? super T>, List<? extends T>)` hay `<T> void copy(List<T>, List<T>)`? Chọn chữ ký đầu nếu contract thật sự là copy theo hướng producer/consumer; chữ ký sau bị invariance giới hạn danh sách khác type argument.

## 19. Ghi nhớ và tài liệu chuẩn

Suy luận kiểu chỉ tự động tìm type argument cho một **hệ ràng buộc tĩnh**. Những ràng buộc đó đến từ kiểu khai báo, đối số, upper bound, wildcard, target type, lambda/method reference và overload. Compiler không có nghĩa vụ chọn kiểu “mà người viết có vẻ định dùng” nếu không có đủ bằng chứng; càng không được bỏ qua invariance, bounds hoặc an toàn kiểu.

Khi một lỗi liên quan generics xuất hiện, nên hỏi theo thứ tự: **generic method/class yêu cầu quan hệ kiểu gì; compiler biết gì về đối số và target; ràng buộc nào xung đột; cần sửa dữ liệu, chữ ký hay ngữ cảnh?** Câu trả lời thường rõ ràng hơn sau khi tách lời gọi thành vài biến có kiểu cụ thể.

Tham khảo để đối chiếu quy tắc chính thức:

- [JLS `4 — Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html): type parameter, type argument, wildcard, erasure, reifiable types.
- [JLS `5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html): chuyển đổi khi gán và khi gọi phương thức.
- [JLS `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): applicability, overload, target typing.
- [JLS `18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html): hình thành, rút gọn và giải hệ constraints.
- [Java Tutorial — Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html): ví dụ producer/consumer và wildcard capture; xem JLS là nguồn chuẩn về ngữ nghĩa.
