# Suy luận đối số kiểu từ tham số của lời gọi trong Java Generics

## 1. Bài toán: vì sao có thể gọi phương thức generic mà không ghi `<T>`?

Trong Java, một phương thức generic khai báo tham số kiểu trong cặp dấu `<...>` trước kiểu trả về:

```java
static <T> T identity(T value) {
    return value;
}
```

Ta có thể chỉ định `T` tường minh:

```java
String result = Example.<String>identity("Java");
```

Nhưng thông thường chỉ cần:

```java
String result = Example.identity("Java");
```

Trình biên dịch nhìn vào **đối số thực tế của lời gọi** (ở đây là biểu thức `"Java"`) và kiểu tham số hình thức (ở đây là `T`) để suy luận cách dùng tham số kiểu `T`. Cơ chế này gọi là *method type inference* hoặc *invocation type inference*.

Trong ví dụ đơn giản, `T` có thể được suy luận phù hợp với `String`. Với lời gọi `identity(42)`, biểu thức `42` thuộc kiểu nguyên thủy `int` và có thể được boxing thành `Integer`, cho phép suy luận đối số kiểu tham chiếu thích hợp.

**Điểm chính:** trình biên dịch suy luận từ **kiểu tĩnh của biểu thức đối số**, các **ràng buộc do chữ ký phương thức đặt ra**, và đôi khi cả **kiểu đích của ngữ cảnh lời gọi**. Nó không nhìn vào phần tử thực tế bên trong danh sách ở runtime để đoán lại `T`.

Bài này tập trung vào các ràng buộc xuất phát từ **tham số và đối số của lời gọi**, đồng thời giải thích những trường hợp kiểu đích có thể tham gia để tránh suy luận sai.

## 2. Ba vai trò cần phân biệt

Xét khai báo:

```java
static <T> void append(List<T> destination, T value) {
    destination.add(value);
}
```

Trong lời gọi:

```java
List<String> names = new ArrayList<>();
append(names, "An");
```

các vai trò là:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Tham số kiểu** (*type parameter*) | `T` trong `<T>` | Biến kiểu được khai báo bởi phương thức |
| **Tham số hình thức** (*formal parameter*) | `List<T> destination`, `T value` | Vị trí và kiểu mà phương thức mong đợi |
| **Đối số thực tế** (*actual argument*) | `names`, `"An"` | Biểu thức được truyền khi gọi phương thức |
| **Đối số kiểu được suy luận** (*inferred type argument*) | Kiểu phù hợp với `String` | Kết quả giải các ràng buộc áp dụng cho `T` |

Không nên gọi `"An"` là “tham số kiểu”. Đây là **giá trị đối số**; từ kiểu tĩnh của nó, trình biên dịch thiết lập điều kiện cho tham số kiểu `T`.

Một tham số kiểu có thể xuất hiện ở nhiều vị trí của chữ ký, do đó việc suy luận **không diễn ra độc lập cho từng vị trí**. Cùng một `T` phải đáp ứng tất cả điều kiện có liên quan.

## 3. Trường hợp cơ bản: một tham số T, một đối số

Ví dụ:

```java
static <T> T echo(T value) {
    return value;
}
```

Lời gọi:

```java
String text = echo("hello");
Integer number = echo(10);
```

Ở lời gọi thứ nhất, đối số là biểu thức có kiểu `String`, vì thế compiler tìm một `T` thích hợp để phương thức nhận được `String`. Trong ngữ cảnh gán cho `String`, lời gọi hợp lệ và giá trị trả về giữ kiểu tương thích với `String`.

Ở lời gọi thứ hai, `10` có kiểu `int`; vì generics không thể sử dụng kiểu nguyên thủy làm đối số kiểu, phép boxing cho phép dùng kiểu wrapper `Integer`.

Những trường hợp khác:

```java
Object object = echo("hello"); // Hợp lệ
Number value = echo(10);       // Hợp lệ
```

Không nên khẳng định rằng `T` **luôn luôn** chính xác bằng kiểu cụ thể nhất của đối số. Ngữ cảnh đích `Object` hoặc `Number` có thể bổ sung ràng buộc, và thuật toán suy luận của Java có thể tìm một kiểu phù hợp rộng hơn khi cần.

Suy luận kiểu là quá trình giải các điều kiện hợp lệ theo ngôn ngữ, không phải phép tra bảng cố định “đối số là X thì T bắt buộc là X”.

## 4. Khi cùng T xuất hiện ở nhiều tham số

Xét:

```java
static <T> T choose(T first, T second, boolean pickFirst) {
    return pickFirst ? first : second;
}
```

Với hai đối số cùng kiểu:

```java
String selected = choose("A", "B", true);
```

Cả `"A"` và `"B"` đều tương thích với `String`, nên việc suy luận rất tự nhiên.

Với hai đối số khác kiểu:

```java
Number selected = choose(1, 2.5, true);
```

`1` được boxing thành `Integer`; `2.5` được boxing thành `Double`. Cả hai đều thuộc họ `Number`, nên một kiểu `T` phù hợp có thể đáp ứng những điều kiện cần thiết trong lời gọi này.

Tuy nhiên:

```java
Integer selected = choose(1, 2.5, true); // LỖI BIÊN DỊCH
```

Không có lý do gì để khẳng định kết quả luôn là `Integer` khi nhánh có thể trả `Double`. Kiểu đích `Integer` tạo thêm điều kiện không tương thích với khả năng nhận cả hai đối số.

**Lưu ý về kiểu chung:** trong các trường hợp phức tạp, Java có thể sử dụng kiểu chung nhỏ nhất hợp lệ theo quan hệ kiểu (*least upper bound*) và các kiểu giao (*intersection types*). Vì thế, không nên tự diễn giải kiểu `T` thành đúng một lớp cha cụ thể khi không có thông tin biên dịch đủ rõ. Quan trọng là biểu thức có tương thích với kiểu đích và các bound hay không.

## 5. `List<T>` tạo ràng buộc chặt hơn một đối số T đơn lẻ

Phương thức:

```java
static <T> void append(List<T> destination, T value) {
    destination.add(value);
}
```

Khi gọi:

```java
List<Integer> numbers = new ArrayList<>();
append(numbers, 7); // Đúng
```

`destination` có kiểu `List<Integer>`, nên vị trí `List<T>` tạo ràng buộc chặt rằng `T` phải phù hợp với tham số kiểu của danh sách này. Đối số `7` có thể boxing thành `Integer`, do đó các điều kiện tương thích.

Ngược lại:

```java
List<Integer> numbers = new ArrayList<>();
Number value = 2.5;
append(numbers, value); // LỖI BIÊN DỊCH
```

Nếu compiler coi `T` là `Integer`, đối số `value` có kiểu tĩnh `Number` chưa chắc là `Integer`. Nếu coi `T` là `Number`, `List<Integer>` lại không chuyển thành `List<Number>`, bởi generic mặc định **bất biến** (*invariant*).

Lỗi của `javac` thường có dạng:

```text
reason: inference variable T has incompatible bounds
```

Kèm các điều kiện như “equality constraints: Integer” và “lower bounds: Number”. Đây là mô tả kỹ thuật của các ràng buộc suy luận mâu thuẫn, không có nghĩa `T` được khai báo bằng cú pháp `<T super Number>`.

Trong khi đó:

```java
List<Number> numbers = new ArrayList<>();
append(numbers, 7);   // Đúng: Integer là Number
append(numbers, 2.5); // Đúng: Double là Number
```

`List<Number>` yêu cầu tham số kiểu `T` tương thích với `Number`; đối số `Integer` hoặc `Double` đều có thể chuyển thành `Number`. Đây là khác biệt rất quan trọng giữa **kiểu đối số giá trị** và **đối số kiểu của một List**.

## 6. Bound của phương thức cũng góp phần vào suy luận

Không phải `T` nào cũng không có giới hạn. Xét:

```java
static <T extends Number> double average(T left, T right) {
    return (left.doubleValue() + right.doubleValue()) / 2;
}
```

Các lời gọi hợp lệ:

```java
double a = average(2, 4);
double b = average(2, 4.5);
```

Với `average(2, 4.5)`, compiler phải tìm một `T` phù hợp với các đối số `Integer`, `Double` và giới hạn trên `Number`. Giá trị được sử dụng như `Number` trong thân phương thức, do đó cả hai đối số đều gọi được `doubleValue()`.

Lời gọi không hợp lệ:

```java
average("2", "4"); // LỖI: String không thỏa bound Number
```

Với một bound phức tạp hơn:

```java
static <T extends Comparable<? super T>> int compare(T a, T b) {
    return a.compareTo(b);
}
```

Compiler phải bảo đảm kiểu `T` còn đáp ứng khả năng so sánh do bound yêu cầu. Không phải hai đối số có một kiểu cha chung bất kỳ là đủ.

Một nguyên tắc quan trọng: **kiểu chung cần thỏa toàn bộ bound** đã khai báo. Nếu tập ràng buộc không có nghiệm hợp lệ, lời gọi không biên dịch dù về runtime các đối tượng đều có thể được lưu dưới `Object`.

## 7. Kiểu tĩnh của đối số quan trọng hơn giá trị runtime

```java
static <T> T identity(T value) {
    return value;
}
```

Ví dụ:

```java
Number n = Integer.valueOf(10);
Number result = identity(n);
```

Biểu thức đối số `n` có **kiểu khai báo `Number`**. Compiler không suy luận kiểu bằng cách kiểm tra đối tượng hiện tại có phải `Integer` hay không. Ở runtime, `n` có thể chứa `Integer`, `Double` hoặc một subclass khác của `Number`.

Do đó:

```java
Integer i = identity(n); // Không biên dịch: Number không bảo đảm Integer
```

Muốn nhận `Integer`, đầu vào cần có kiểu tĩnh phù hợp hoặc phải có bước kiểm tra kiểu rõ ràng:

```java
if (n instanceof Integer i) {
    Integer copy = identity(i); // Đúng: i có kiểu Integer sau pattern matching
}
```

`instanceof` ở đây là phép kiểm tra runtime để thu hẹp kiểu một cách an toàn; nó **không** có nghĩa generics tự suy luận lại kiểu từ đối tượng runtime.

## 8. Đối số không phải nguồn ràng buộc duy nhất

Đối số của lời gọi cung cấp thông tin ban đầu về T, nhưng trong **poly method invocation**, kiểu đích cũng có thể đưa thêm điều kiện. Ví dụ:

```java
static <T> List<T> box(T value) {
    return new ArrayList<>(List.of(value));
}

List<Integer> a = box(42);
List<Number> b = box(42);
List<Object> c = box(42);
```

Ba lần gọi dùng cùng giá trị 42 nhưng mục tiêu `List<T>` khác nhau. Với `b`, kiểu đích buộc kết quả tương thích `List<Number>`; đối số Integer vẫn gán được cho Number. Điều đó **không** có nghĩa `List<Integer>` đã tạo trước có thể gán cho `List<Number>`.

Ngược lại, không phải biểu thức nào cũng nhận target type và compiler không dự đoán ý định runtime. Nếu `T` chỉ xuất hiện ở tham số, hãy theo dõi kiểu tĩnh của từng đối số; nếu còn xuất hiện ở kết quả, cần xét thêm ngữ cảnh trả về và các bounds. Ngữ cảnh gán, truyền đối số và ranh giới poly expression được phân tích sâu ở bài **kiểu đích** tiếp theo.

## 9. Có thể truyền đối số kiểu tường minh khi cần kiểm soát

Cú pháp:

```java
List<Number> numbers = Example.<Number>box(42);
```

`<Number>` ở vị trí này là **đối số kiểu tường minh của lời gọi phương thức generic**, không phải khai báo tham số kiểu mới.

Với phương thức static, viết `Example.<Number>box(42)`. Với lời gọi trực tiếp trong cùng lớp có thể viết `Example.<Number>box(42)` hoặc dạng phù hợp khác tùy vị trí gọi.

Ví dụ giới hạn trên:

```java
static <T extends Number> T same(T value) {
    return value;
}
```

Hợp lệ:

```java
Number n = Example.<Number>same(1);
```

Không hợp lệ:

```java
Example.<String>same("x"); // String không thỏa bound Number
```

Chỉ định `T` tường minh **không bỏ qua quy tắc an toàn kiểu**. Nếu lựa chọn không thỏa bound hoặc đối số truyền vào không chuyển được sang kiểu yêu cầu, lời gọi vẫn bị từ chối.

Thông thường nên để compiler suy luận; chỉ định kiểu tường minh khi nó làm rõ hợp đồng hoặc giúp xử lý một tình huống khó đọc.

## 10. Tương tác với wildcard ở vị trí tham số

Khi nguồn và đích khác vai trò, một phương thức generic có thể cần wildcard:

```java
static <T> void copyAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Ví dụ:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
copyAll(integers, numbers);
```

Compiler có thể chọn `T` thỏa `List<Integer>` phù hợp với `List<? extends T>`, đồng thời `List<Number>` phù hợp với `List<? super T>`.

Đây là quy tắc **PECS** (*Producer Extends, Consumer Super*) ứng dụng cùng với suy luận `T`.

Ngược lại, nếu khai báo quá chặt:

```java
static <T> void copyStrict(List<T> source, List<T> destination) {
    destination.addAll(source);
}
```

Lời gọi `copyStrict(List<Integer>, List<Number>)` không hợp lệ, do `List<Integer>` và `List<Number>` không có cùng tham số kiểu. Suy luận không biến generics thành hiệp biến; compiler phải tôn trọng quan hệ bất biến của `List<T>`.

### Trường hợp wildcard capture

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

List<? extends Number> source = List.of(3, 5);
Number n = first(source);
```

Compiler có thể *capture* wildcard chưa biết trong `source` để suy luận một `T` phù hợp tại lời gọi `first(source)`. Phần tử trả về vẫn dùng an toàn dưới `Number`.

Không thể từ đây suy ra có thể thêm `Number` bất kỳ vào `source`; wildcard chỉ bảo đảm **đọc** với giới hạn trên.

## 11. Boxing, kiểu nguyên thủy và varargs

Java generic type arguments phải là **kiểu tham chiếu**:

```java
static <T> T echo(T value) {
    return value;
}

Integer x = echo(1);  // int được boxing thành Integer
Double y = echo(2.5); // double được boxing thành Double
```

Không được viết:

```java
// Không hợp lệ:
List<int> numbers = new ArrayList<>();
// Tương tự, <int>echo(1) không phải đối số kiểu generic hợp lệ.
```

Cũng cần phân biệt phương thức varargs generic:

```java
@SafeVarargs
static <T> List<T> asList(T... values) {
    return List.of(values);
}
```

Ví dụ phương thức này là `static` và có thể được đánh dấu `@SafeVarargs` khi thân phương thức thực sự không làm hỏng kiểu mảng varargs; nhưng annotation là **cam kết của người viết**, không phải cơ chế làm varargs generic an toàn tự động. Các phương thức varargs với `T...` có thể phát sinh cảnh báo về mảng có kiểu phần tử không reifiable. Khi chỉ cần tạo danh sách, ưu tiên `List.of(...)` hoặc các API chuẩn.

Suy luận `T` trong lời gọi varargs phải xét kiểu từng đối số, kiểu mảng được truyền và các quy tắc áp dụng fixed-arity/variable-arity. Đừng suy ra từ sự tương đồng hình thức rằng một mảng `T[]` được tạo tùy ý ở runtime.

## 12. Chương trình Java 17+ đầy đủ và kết quả chính xác

Tạo file `InferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InferenceDemo {
    static <T> List<T> box(T value) {
        return new ArrayList<>(List.of(value));
    }

    static <T> void append(List<T> destination, T value) {
        destination.add(value);
    }

    static <T> T pickFirst(List<T> list) {
        return list.get(0);
    }

    static <T> T choose(T left, T right, boolean pickLeft) {
        return pickLeft ? left : right;
    }

    static <T extends Number> double average(T a, T b) {
        return (a.doubleValue() + b.doubleValue()) / 2;
    }

    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words = box("Java");
        System.out.println("Words: " + words);

        List<Number> fromTarget = box(42);
        System.out.println("Target: " + fromTarget);

        List<Number> numbers = new ArrayList<>();
        append(numbers, 7);
        append(numbers, 2.5);
        System.out.println("Appended: " + numbers);

        List<? extends Number> source = List.of(3, 5);
        Number first = pickFirst(source);
        System.out.println("First: " + first);

        Number chosen = choose(1, 2.5, true);
        System.out.println("Chosen: " + chosen);

        System.out.println("Average: " + average(2, 4.5));

        copyAll(List.of(10, 20), numbers);
        System.out.println("Copied: " + numbers);

        List<Number> explicit = InferenceDemo.<Number>box(99);
        System.out.println("Explicit: " + explicit);
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```bash
javac -encoding UTF-8 InferenceDemo.java
java InferenceDemo
```

Kết quả:

```text
Words: [Java]
Target: [42]
Appended: [7, 2.5]
First: 3
Chosen: 1
Average: 3.25
Copied: [7, 2.5, 10, 20]
Explicit: [99]
```

**Phân tích cụ thể:**

1. `box("Java")` tạo danh sách chứa `String` và được gán cho `List<String>`.
2. `box(42)` đặt vào `List<Number>` hợp lệ vì compiler kết hợp ràng buộc từ đối số với kiểu đích; nó không biến một `List<Integer>` đã tồn tại thành `List<Number>`.
3. `append(numbers, 7)` và `append(numbers, 2.5)` đều dùng được cùng danh sách `List<Number>` vì mỗi lời gọi phải tương thích với `T` của chữ ký.
4. `pickFirst(source)` thực hiện wildcard capture để đọc được dưới kiểu `Number`.
5. `choose(1, 2.5, true)` chấp nhận hai kiểu số khác nhau và kết quả tương thích với `Number`.
6. `average(2, 4.5)` đáp ứng `T extends Number`; giá trị `3.25` là kết quả trung bình của `2.0` và `4.5`.
7. `copyAll` tận dụng PECS: nguồn cung cấp `Integer` và đích có thể nhận `Number`.
8. `InferenceDemo.<Number>box(99)` cho thấy cú pháp chỉ định đối số kiểu tường minh.

## 13. Các thông báo lỗi suy luận kiểu thường gặp

### 13.1. `inference variable T has incompatible bounds`

```java
static <T> void append(List<T> target, T value) {
    target.add(value);
}

List<Integer> integers = new ArrayList<>();
Number n = 1.5;
append(integers, n); // Không biên dịch
```

Vị trí `List<T>` buộc `T` phù hợp với `Integer`, còn đối số `n` có kiểu tĩnh `Number`. Do bất biến của generic, compiler không tìm được cách chọn `T` thỏa cả hai.

**Khắc phục:** truyền giá trị thật sự thuộc `Integer`, thay kiểu đích thành `List<Number>` nếu cần chứa nhiều kiểu số, hoặc thiết kế lại API bằng wildcard khi đúng hợp đồng nghiệp vụ. Không ép kiểu mù sang `Integer`.

### 13.2. `inferred type does not conform to upper bound`

```java
static <T extends Number> T same(T value) {
    return value;
}

String s = same("hello"); // Không biên dịch
```

`String` không phải `Number`. Đây là vi phạm bound, không phải lỗi do thiếu thông tin về `T`.

### 13.3. Hiểu sai giá trị trả về

```java
static <T> T choose(T a, T b, boolean left) {
    return left ? a : b;
}

Integer result = choose(1, 2.5, true); // Không biên dịch
```

Cần chọn kiểu đích có thể đại diện cho cả hai nhánh, ví dụ `Number`. Việc ở runtime nhánh `true` trả một `Integer` không giúp lời gọi trả về kiểu tĩnh `Integer` khi nhánh còn lại có thể là `Double`.

### 13.4. Dùng raw type hoặc unchecked cast để vượt suy luận

```java
List<Integer> values = new ArrayList<>();
List raw = values;
raw.add("bad");
```

Đây không phải cách “sửa lỗi inference”. Raw type làm mất kiểm tra generic, có thể tạo *heap pollution* rồi dẫn đến `ClassCastException` ở nơi đọc.

Không nên gắn `@SuppressWarnings("unchecked")` chỉ để ẩn cảnh báo của một lệnh ép kiểu thiếu chứng cứ.

### 13.5. Tưởng `var` tự chọn kiểu theo cách mình muốn

```java
var values = List.of(1, 2, 3);
```

`var` suy luận kiểu của **biến cục bộ** từ kiểu kết quả biểu thức khởi tạo. Đây là một bước khác với suy luận đối số kiểu của lời gọi `List.of(...)`. Không nên giả định `var` luôn tạo `List<Number>` hoặc luôn chọn một kiểu người lập trình mong muốn cho mọi tập hợp đối số hỗn hợp.

Khi API cần một hợp đồng cụ thể, khai báo kiểu đích rõ ràng:

```java
List<Number> values = List.of(1, 2.5);
```

## 14. Bài tập: suy luận từ những đối số nào?

Các đoạn sau **độc lập**, giả sử đã import `java.util.*;`. Phương thức `static` phải được đặt trong một lớp hợp lệ. Hãy nhận định biên dịch được hay không.

**A — Cùng T qua List và giá trị**

```java
static <T> void add(List<T> list, T value) {
    list.add(value);
}
List<String> texts = new ArrayList<>();
add(texts, "Java");
```

**B — Kiểu tĩnh Number vào List<Integer>**

```java
List<Integer> integers = new ArrayList<>();
Number n = 5;
add(integers, n);
```

**C — Kiểu tĩnh Integer vào List<Number>**

```java
List<Number> numbers = new ArrayList<>();
add(numbers, Integer.valueOf(5));
```

**D — Hai kiểu số và kết quả Number**

```java
static <T> T pick(T x, T y) {
    return x;
}
Number n = pick(10, 3.5);
```

**E — Bound Number với chuỗi**

```java
static <T extends Number> T unchanged(T x) {
    return x;
}
String s = unchanged("10");
```

**F — Kiểu đích của List<T>**

```java
static <T> List<T> singleton(T value) {
    return new ArrayList<>(List.of(value));
}
List<Number> numbers = singleton(10);
```

**G — Wildcard source và type inference**

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
List<? extends Number> source = List.of(1, 2);
Number result = first(source);
```

**H — Hai List<T> bất biến**

```java
static <T> void merge(List<T> source, List<T> target) {
    target.addAll(source);
}
List<Integer> ints = List.of(1);
List<Number> nums = new ArrayList<>();
merge(ints, nums);
```

**Đáp án giải thích:**

- **A:** Hợp lệ, các ràng buộc phù hợp với `String`.
- **B:** Không hợp lệ: kiểu tĩnh `Number` không bảo đảm `Integer`; `List<Integer>` không thể coi là `List<Number>`.
- **C:** Hợp lệ: `Integer` chuyển được thành `Number`, và đích là `List<Number>`.
- **D:** Hợp lệ: có thể dùng kiểu chung phù hợp với `Integer`, `Double` và kiểu đích `Number`.
- **E:** Không hợp lệ: `String` không thỏa `T extends Number`.
- **F:** Hợp lệ: kiểu đích `List<Number>` tham gia cùng ràng buộc đầu vào.
- **G:** Hợp lệ: wildcard capture cho phép phương thức generic đọc một phần tử dưới dạng `Number`.
- **H:** Không hợp lệ: cùng một `List<T>` không thể lần lượt là `List<Integer>` và `List<Number>`. Dùng `List<? extends T>` ở nguồn, `List<? super T>` ở đích nếu muốn quan hệ đó.

## 15. Quy trình đọc chữ ký khi compiler báo không suy luận được T

Hãy kiểm tra theo thứ tự:

1. **Tìm chỗ khai báo `<T>`** và các giới hạn, ví dụ `<T extends Number>`.
2. **Ghi lại mọi chỗ xuất hiện `T`** trong tham số hình thức: `T`, `List<T>`, `List<? extends T>`, `List<? super T>`.
3. **Xác định kiểu tĩnh của đối số thực tế**, kể cả boxing, chuyển kiểu tham chiếu và wildcard; không dựa vào giá trị runtime.
4. **Xem có kiểu đích không**, ví dụ gán kết quả vào `List<Number>` hay `Integer`, và ngữ cảnh đó có tham gia suy luận không.
5. **Kiểm tra các ràng buộc có mâu thuẫn không**. `List<Integer>` cần đúng tham số kiểu `Integer`, trong khi đối số giá trị kiểu `Number` có thể quá rộng.
6. **Kiểm tra bound**, ví dụ `T extends Number`: một nghiệm suy luận không thỏa bound vẫn bị từ chối.
7. Nếu API đang mô tả **nguồn/đích khác vai trò**, cân nhắc cặp `? extends T` / `? super T`, thay vì ép mọi tham số có cùng `List<T>`.
8. Chỉ viết đối số kiểu tường minh khi nó thể hiện lựa chọn hợp lệ, không sử dụng cast unchecked để né lỗi.

### Ghi nhớ

**Suy luận đối số kiểu từ tham số của lời gọi** là việc compiler kết hợp kiểu tĩnh của các đối số với cấu trúc tham số hình thức để giải một hệ ràng buộc cho `T`. Cùng một `T` phải thỏa tất cả vị trí sử dụng và bound; trong những ngữ cảnh phù hợp, kiểu đích cũng có thể bổ sung điều kiện. Cơ chế này giúp gọi các phương thức generic ngắn gọn, đồng thời giữ an toàn kiểu mà không cần ép kiểu hoặc raw type.
