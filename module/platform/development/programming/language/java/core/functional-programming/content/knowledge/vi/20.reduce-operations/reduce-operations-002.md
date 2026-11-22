# `reduce()` không có giá trị khởi đầu và kết quả `Optional` trong Java Stream

Trong Java Stream, **reduction** (rút gọn) là quá trình kết hợp nhiều phần tử thành một kết quả, ví dụ tính tổng, tìm giá trị lớn nhất, hoặc ghép chuỗi. Điểm quan trọng của overload **`reduce(BinaryOperator<T>)` không có giá trị khởi đầu (*identity*)** là kết quả của nó có kiểu **`Optional<T>`**, không phải `T`.

Lý do: nếu stream **rỗng**, không có phần tử đầu tiên để làm kết quả hay khởi điểm kết hợp; Java cần cách biểu diễn “không có kết quả”. `Optional.empty()` giải quyết tình huống đó mà không buộc API bịa ra một giá trị mặc định như `0`, `""` hay một đối tượng giả. Nếu stream có **một phần tử**, phép rút gọn trả chính phần tử đó trong `Optional`, không cần gọi hàm kết hợp.

Ví dụ ngắn:

~~~java
Optional<Integer> sum = java.util.stream.Stream.of(2, 3, 5)
        .reduce(Integer::sum); // Optional[10]
~~~

Đây là đoạn minh họa trong một phương thức đã import `java.util.Optional`. Cách đọc: `Stream<Integer> → reduce(BinaryOperator<Integer>) → Optional<Integer>`.

## 1. Chữ ký phương thức và các overload dễ nhầm

Trong `java.util.stream.Stream<T>`, hai overload cơ bản là:

~~~java
// Chữ ký API được lược bớt để học; không phải lớp Java độc lập.
Optional<T> reduce(BinaryOperator<T> accumulator);
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

Bên cạnh đó còn overload ba đối số:

~~~java
<U> U reduce(U identity,
             BiFunction<U, ? super T, U> accumulator,
             BinaryOperator<U> combiner);
~~~

Bài này tập trung vào **overload một tham số**. Bảng so sánh:

| Cách gọi | Kiểu trả về | Khi nguồn rỗng |
| --- | --- | --- |
| `stream.reduce(accumulator)` | `Optional<T>` | `Optional.empty()` |
| `stream.reduce(identity, accumulator)` | `T` | Trả `identity` |
| `stream.reduce(identity, accumulator, combiner)` | `U` | Trả `identity`, với các yêu cầu tính đúng của identity/combiner |
| `intStream.reduce(operator)` | `OptionalInt` | `OptionalInt.empty()` |
| `intStream.reduce(identity, operator)` | `int` | Trả `identity` |

Trong overload một tham số, `BinaryOperator<T>` là functional interface nhận **hai giá trị cùng kiểu `T`** và trả về một giá trị `T`:

~~~java
T apply(T left, T right);
~~~

Vì thế `Stream<Integer>.reduce(Integer::sum)` trả `Optional<Integer>`. `Stream<String>.reduce(String::concat)` trả `Optional<String>`. `Stream<Order>.reduce(...)` trả `Optional<Order>`, chứ không thể tự biến thành `Optional<Integer>` nếu hàm rút gọn chỉ nhận và trả `Order`.

## 2. Ví dụ chạy được: stream rỗng, một phần tử và nhiều phần tử

Tạo file `ReduceWithoutIdentityDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceWithoutIdentityDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(4, 7, 2);

        Optional<Integer> sum = values.stream()
                .reduce(Integer::sum);
        Optional<Integer> maximum = values.stream()
                .reduce(Integer::max);

        Optional<Integer> empty = Stream.<Integer>empty()
                .reduce(Integer::sum);
        Optional<Integer> single = Stream.of(9)
                .reduce(Integer::sum);

        System.out.println("sum=" + sum);
        System.out.println("maximum=" + maximum);
        System.out.println("empty=" + empty);
        System.out.println("single=" + single);
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac --release 17 ReduceWithoutIdentityDemo.java
java ReduceWithoutIdentityDemo
~~~

Stdout:

~~~text
sum=Optional[13]
maximum=Optional[7]
empty=Optional.empty
single=Optional[9]
~~~

Giải thích:

1. Nguồn `[4, 7, 2]`: `Integer::sum` kết hợp thành 13; `Integer::max` chọn 7. Hai kết quả đều được bọc bằng `Optional`.
2. Nguồn **rỗng**: không có phần tử nào để tạo kết quả; `Optional.empty()` báo rõ sự vắng mặt.
3. Nguồn **một phần tử**: không cần kết hợp với phần tử khác, kết quả là `Optional[9]`.
4. Mỗi phép `reduce` lấy **một stream mới** từ `values` hoặc `Stream.of`. Stream đã chạy terminal operation không được dùng lại.

Không nhầm `Optional[13]` với một chuỗi chứa dấu ngoặc vuông: đó là cách `Optional.toString()` biểu diễn một `Optional` có giá trị; mã nghiệp vụ nên dùng API của `Optional` thay vì phân tích chuỗi này.

## 3. Mô hình rút gọn khi không có identity

Với một **stream tuần tự có thứ tự**, có thể hình dung:

~~~text
Nguồn: [2, 3, 4, 5]

Bắt đầu:      current = 2
Phần tử 3:    current = accumulator(2, 3)  → 5
Phần tử 4:    current = accumulator(5, 4)  → 9
Phần tử 5:    current = accumulator(9, 5)  → 14

Kết quả:      Optional[14]
~~~

Với danh sách chỉ chứa `[2]`, kết quả là `Optional[2]`, không gọi accumulator. Với danh sách `[]`, không có `current` ban đầu và kết quả là `Optional.empty()`.

Đây là **mô hình tư duy** cho trường hợp tuần tự, không phải cam kết rằng mọi `reduce` luôn thực thi theo chuỗi bên trái như vậy. Java cho phép rút gọn theo cách kết hợp lại các phần dữ liệu, đặc biệt với parallel stream. Để kết quả đúng, accumulator phải phù hợp yêu cầu tính kết hợp.

Ví dụ quan sát thứ tự trong **stream tuần tự**. Tạo file `ReduceTraceDemo.java`:

~~~java
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceTraceDemo {
    public static void main(String[] args) {
        Optional<Integer> result = Stream.of(2, 3, 4)
                .reduce((left, right) -> {
                    System.out.println(
                            "combine " + left + " + " + right);
                    return left + right;
                });
        System.out.println("result=" + result);
    }
}
~~~

~~~bash
javac --release 17 ReduceTraceDemo.java
java ReduceTraceDemo
~~~

Stdout trên pipeline tuần tự cụ thể:

~~~text
combine 2 + 3
combine 5 + 4
result=Optional[9]
~~~

Dấu vết này để **học cơ chế**, không phải mẫu thiết kế nên dùng trong production: không phụ thuộc side effect trong accumulator hoặc giả định tất cả phép giảm đều gọi hàm theo thứ tự đó.

## 4. Vì sao không thể trả một `T` mặc định cho mọi trường hợp?

Giả sử muốn lấy phần tử lớn nhất trong `Stream<Integer>`:

~~~java
Optional<Integer> max =
        numbers.stream().reduce(Integer::max);
~~~

Trên danh sách `[-9, -3, -12]`, giá trị lớn nhất là `-3`; trên danh sách `[]`, **không có giá trị lớn nhất**. Nếu chọn bừa `0` làm identity và gọi `reduce(0, Integer::max)`, kết quả của danh sách toàn số âm lại là `0`: sai dữ liệu vì identity đó không phù hợp với phép `max` trên miền các số âm.

Ví dụ sai theo ý định “tìm max”:

~~~java
// numbers là List<Integer> có thể chứa số âm.
int wrongMax = numbers.stream().reduce(0, Integer::max);
~~~

Với `numbers = List.of(-9, -3, -12)`, `wrongMax == 0` dù nguồn không hề có `0`. Trong khi đó, `numbers.stream().reduce(Integer::max)` trả `Optional[-3]`.

Khác biệt cốt lõi:

- **Không identity**: cho phép nói “chưa có kết quả”, không áp đặt giá trị giả định cho nguồn rỗng.
- **Có identity đúng**: phù hợp khi tồn tại một phần tử đơn vị hợp lệ cho phép toán và kiểu dữ liệu (ví dụ `0` cho tổng số nguyên, `1` cho tích số nguyên).
- **Identity sai**: có thể làm méo kết quả **ngay cả khi stream không rỗng**.

Không chọn overload theo thói quen; phải xem phép toán có phần tử đơn vị đúng về mặt toán học và nghiệp vụ hay không.

## 5. Phân biệt `Optional.empty()` và `Optional.of(0)`

Hai kết quả có thể được in hoặc quy đổi ra cùng con số sau khi dùng `orElse(0)`, nhưng **ý nghĩa trước khi quy đổi khác nhau**:

~~~java
Optional<Integer> empty =
        java.util.stream.Stream.<Integer>empty()
                .reduce(Integer::sum);

Optional<Integer> zero =
        java.util.stream.Stream.of(-3, 3)
                .reduce(Integer::sum);
~~~

Ở đây:

- `empty` là `Optional.empty()`: **không có phần tử và không có kết quả rút gọn**.
- `zero` là `Optional[0]`: **có dữ liệu**, tổng thực sự bằng 0.
- `empty.orElse(0)` và `zero.orElse(0)` cùng trả `0`, làm **mất khả năng phân biệt không có dữ liệu và dữ liệu có tổng 0**.

Nếu nghiệp vụ cần biết “có giao dịch hay không”, đừng tự động `orElse(0)` mà không cân nhắc. Khi chỉ cần tổng số học và 0 là identity hợp lệ, overload `reduce(0, Integer::sum)` hoặc `IntStream.sum()` thường đơn giản hơn.

## 6. Làm gì với `Optional<T>` sau `reduce`?

Kết quả `Optional<T>` cho phép xử lý “có/không có” bằng các API có chủ ý:

| API | Cách dùng | Ý nghĩa |
| --- | --- | --- |
| `isPresent()` | `result.isPresent()` | Kiểm tra kết quả có giá trị không. |
| `isEmpty()` | `result.isEmpty()` | Kiểm tra không có kết quả (Java 11+). |
| `ifPresent(consumer)` | `result.ifPresent(System.out::println)` | Chỉ chạy hành vi khi có giá trị. |
| `map(fn)` | `result.map(Object::toString)` | Chuyển đổi kết quả nếu có giá trị. |
| `orElse(fallback)` | `result.orElse(0)` | Trả giá trị dự phòng khi rỗng. |
| `orElseGet(supplier)` | `result.orElseGet(() -> loadDefault())` | Chỉ gọi supplier khi rỗng. |
| `orElseThrow()` | `result.orElseThrow()` | Nếu rỗng, ném `NoSuchElementException`. |
| `orElseThrow(supplier)` | `result.orElseThrow(() -> new IllegalStateException("empty"))` | Nếu rỗng, ném lỗi nghiệp vụ. |

Đoạn `loadDefault()` trong bảng là **tên hàm minh họa**, không phải API Java có sẵn.

Tạo file `HandleReducedOptionalDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class HandleReducedOptionalDemo {
    static String describe(List<Integer> values) {
        Optional<Integer> total =
                values.stream().reduce(Integer::sum);
        return total.map(n -> "Tổng = " + n)
                .orElse("Không có dữ liệu");
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of(2, 3)));
        System.out.println(describe(List.of()));
        System.out.println(describe(List.of(-3, 3)));
    }
}
~~~

~~~bash
javac --release 17 HandleReducedOptionalDemo.java
java HandleReducedOptionalDemo
~~~

Stdout:

~~~text
Tổng = 5
Không có dữ liệu
Tổng = 0
~~~

Ví dụ bảo toàn khác biệt giữa **nguồn rỗng** và **tổng bằng không**. `Optional.map` chỉ chạy khi Optional có giá trị; `orElse` cung cấp thông điệp khi rỗng.

Tránh gọi `result.get()` trước khi chắc chắn có giá trị: trên `Optional.empty()`, `get()` ném `NoSuchElementException`. `orElseThrow()` thể hiện rõ hơn mong muốn phải có kết quả và cho phép đưa thông điệp lỗi nghiệp vụ.

### `orElse` và `orElseGet`: eager vs lazy

Trong:

~~~java
// Đoạn minh họa trong một phương thức.
String value = optional.orElse(expensiveFallback());
~~~

Java phải đánh giá `expensiveFallback()` **trước khi** gọi `orElse`, ngay cả khi `optional` đã có giá trị. Với:

~~~java
String value = optional.orElseGet(() -> expensiveFallback());
~~~

supplier chỉ được gọi khi `optional` rỗng. Cả hai đoạn cần một phương thức `expensiveFallback()` và biến `optional` hợp lệ trong ngữ cảnh thực; chúng không phải chương trình độc lập.

## 7. Một bài toán nên trả `Optional` hay giá trị mặc định?

Giả sử một repository trả danh sách số điểm và hàm nghiệp vụ cần **điểm cao nhất**. Dùng:

~~~java
Optional<Integer> highest =
        scores.stream().reduce(Integer::max);
~~~

Người gọi có thể quyết định:

- Không có điểm → hiển thị “chưa chấm”, trả HTTP 404/204 tùy hợp đồng API, hoặc ném lỗi.
- Có điểm → dùng giá trị thực, kể cả `0` hoặc số âm.

Nếu thay vì `Optional<Integer>` API trả `int` với `0` khi empty, trạng thái “chưa có điểm” có thể bị nhập nhằng với điểm hợp lệ `0`.

Tương tự, **giá trị nhỏ nhất**, **đơn hàng có giá cao nhất**, **chuỗi đã ghép từ danh sách** có thể không có kết quả nếu nguồn trống. Một số phép toán vẫn có identity tự nhiên (ví dụ ghép chuỗi có `""` làm identity), nhưng việc chọn “không có kết quả” hay “chuỗi rỗng” phải dựa vào **ngữ nghĩa nghiệp vụ**.

Nếu yêu cầu cụ thể là tìm min/max trên `Stream<T>`, Java đã cung cấp `stream.min(comparator)` và `stream.max(comparator)`, cũng trả `Optional<T>`; thường diễn đạt mục đích rõ ràng hơn `reduce` tự viết. `reduce` đặc biệt có giá trị khi cần một phép kết hợp tổng quát chưa có terminal operation chuyên biệt.

## 8. Ví dụ: rút gọn một đối tượng có kiểu tùy chọn

Overload không identity giữ nguyên kiểu phần tử `T`. Giả sử stream chứa `Order`, có thể chọn đơn hàng lớn nhất bằng một hàm kết hợp hai `Order`, không cần bịa “đơn hàng số 0”.

Tạo file `ReduceOrderDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceOrderDemo {
    record Order(String id, int amount) {}

    static Optional<Order> mostExpensive(List<Order> orders) {
        return orders.stream().reduce(
                (left, right) ->
                        left.amount() >= right.amount() ? left : right);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 60),
                new Order("B", 140),
                new Order("C", 95)
        );

        System.out.println(mostExpensive(orders)
                .map(Order::id)
                .orElse("none"));
        System.out.println(mostExpensive(List.of())
                .map(Order::id)
                .orElse("none"));
    }
}
~~~

~~~bash
javac --release 17 ReduceOrderDemo.java
java ReduceOrderDemo
~~~

Stdout:

~~~text
B
none
~~~

Đường đi kiểu dữ liệu:

~~~text
List<Order>
  .stream()                           → Stream<Order>
  .reduce(BinaryOperator<Order>)      → Optional<Order>
  .map(Order::id)                     → Optional<String>
  .orElse("none")                     → String
~~~

Nếu muốn **tổng `amount`** thay vì chọn một đối tượng `Order`, `Stream<Order>.reduce((a,b) -> a.amount() + b.amount())` là **sai kiểu** vì `BinaryOperator<Order>` phải trả `Order`, còn tổng là `int`. Một cách phù hợp là `orders.stream().mapToInt(Order::amount).sum()` cho tổng kiểu `int`, hoặc `orders.stream().map(Order::amount).reduce(Integer::sum)` nếu muốn `Optional<Integer>` phân biệt nguồn trống với tổng bằng 0.

## 9. Các yêu cầu của accumulator: tính kết hợp và không có side effect

Theo hợp đồng Stream reduction, accumulator phải là hàm **associative** (*có tính kết hợp*), **non-interfering** (*không can thiệp nguồn*), và **stateless** (*không phụ thuộc trạng thái mutable bên ngoài*).

Với ba giá trị `a`, `b`, `c`, tính kết hợp nghĩa là:

~~~text
op(op(a, b), c) == op(a, op(b, c))
~~~

Những ví dụ điển hình thích hợp:

- `Integer::sum` cho phép cộng `int` (theo ngữ nghĩa số nguyên Java, kể cả overflow dạng wraparound).
- `Integer::max` hoặc `Integer::min` cho tìm cực trị.
- `String::concat` có tính kết hợp về nội dung ghép khi các chuỗi không null, dù thứ tự phần tử vẫn quan trọng.

**Không dùng phép trừ** nếu cần phép rút gọn hợp lệ để có cùng ý nghĩa khi phân nhóm:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Hai cách nhóm cho kết quả khác nhau nên `(a,b) -> a - b` không thỏa tính kết hợp. Một phép chạy tuần tự có thể có kết quả nhìn “đúng”, nhưng parallel reduction có quyền phân chia và kết hợp theo cách khác.

Không lấy một `ArrayList` mutable bên ngoài rồi thêm phần tử từ accumulator. Cách đó tạo side effect và nguy cơ lỗi khi parallel. Nếu cần thu phần tử vào collection, dùng `collect(Collectors.toList())`, `Stream.toList()`, hoặc collector phù hợp; không cố dùng `reduce` để thay thế một collector có mutable container.

Ngoài ra, số lần accumulator được gọi và cách gom nhóm không phải hợp đồng để thực hiện logging, cập nhật database hoặc tăng counter nghiệp vụ. Khi cần side effect được kiểm soát, tách nó khỏi phép rút gọn và tuân theo cơ chế xử lý phù hợp.

## 10. So sánh kết quả tuần tự và song song khi phép toán đúng

Tạo file `ParallelReduceDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;

public class ParallelReduceDemo {
    public static void main(String[] args) {
        List<Integer> values = IntStream.rangeClosed(1, 1000)
                .boxed()
                .toList();

        Optional<Integer> sequential = values.stream()
                .reduce(Integer::sum);
        Optional<Integer> parallel = values.parallelStream()
                .reduce(Integer::sum);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 ParallelReduceDemo.java
java ParallelReduceDemo
~~~

Stdout:

~~~text
sequential=Optional[500500]
parallel=Optional[500500]
~~~

Vì `Integer::sum` có tính kết hợp theo ngữ nghĩa cộng `int`, việc nhóm lại không làm đổi giá trị rút gọn của dữ liệu này. **Không suy ra** rằng mọi hàm hai tham số đều cho kết quả giống nhau trên stream tuần tự và song song. Phép trừ, thao tác phụ thuộc thứ tự gọi hoặc dùng biến chia sẻ mutable là những cảnh báo điển hình.

Đối với phép ghép chuỗi, dù nối chuỗi có tính kết hợp nhưng **không giao hoán** (`"A" + "B"` khác `"B" + "A"`). Encounter order của nguồn vẫn quan trọng. Không tùy ý gọi `unordered()` khi kết quả cần giữ một thứ tự có nghĩa.

## 11. Quy tắc `null`: không trả kết quả reducer bằng `null`

`Optional` **không đại diện cho một giá trị “present null”**. Tài liệu Java quy định `reduce(BinaryOperator<T>)` ném `NullPointerException` nếu kết quả rút gọn là `null`. Vì vậy, **đừng dùng `null` để biểu diễn “loại bỏ phần tử” hoặc “không tính được”** từ accumulator.

Ví dụ này **cố ý vi phạm hợp đồng**, không dùng trong production:

~~~java
// Minh họa lỗi: accumulator trả null khi được gọi.
java.util.stream.Stream.of("A", "B")
        .reduce((left, right) -> null); // NullPointerException
~~~

`Optional.empty()` dành cho **trường hợp không có giá trị rút gọn**, không phải cách tự động chữa `null` mà accumulator đã trả. Nếu cần loại phần tử trước khi rút gọn, dùng `filter`. Nếu cần biến kết quả tính toán có thể null, hãy quyết định hợp đồng riêng, xử lý trước hoặc sau reduction; đừng đánh đồng nó với một kết quả reducer null.

Với **phần tử đầu vào null**, `Stream` có thể cho phép chứa null, nhưng nhiều phép toán như `Integer::sum` sẽ ném lỗi do unboxing hoặc dereference. Mặt khác `List.of(...)` không cho phần tử null. Thực hành an toàn là quy định dữ liệu đầu vào và kiểm tra/loại null **trước khi gọi `reduce`**, chẳng hạn:

~~~java
// Minh họa trong ngữ cảnh Stream<Integer> source.
Optional<Integer> sum = source
        .filter(java.util.Objects::nonNull)
        .reduce(Integer::sum);
~~~

Lưu ý: nếu tất cả phần tử bị `filter` loại, `sum` sẽ là `Optional.empty()`. Đó là một thay đổi tập dữ liệu có chủ ý. Nếu dữ liệu null phải bị từ chối như lỗi thay vì bỏ qua, hãy validate đầu vào và fail-fast; không lọc âm thầm.

## 12. Primitive stream: `OptionalInt`, `OptionalLong`, `OptionalDouble`

Các primitive stream có overload reduce **không identity** riêng để tránh boxing:

| Stream | Hàm kết hợp | Kết quả không identity |
| --- | --- | --- |
| `IntStream` | `IntBinaryOperator` | `OptionalInt` |
| `LongStream` | `LongBinaryOperator` | `OptionalLong` |
| `DoubleStream` | `DoubleBinaryOperator` | `OptionalDouble` |

Tạo file `PrimitiveReduceDemo.java`:

~~~java
import java.util.stream.IntStream;

public class PrimitiveReduceDemo {
    public static void main(String[] args) {
        System.out.println("max="
                + IntStream.of(3, 7, 2).reduce(Integer::max));
        System.out.println("empty="
                + IntStream.empty().reduce(Integer::sum));
        System.out.println("default="
                + IntStream.empty().reduce(Integer::sum).orElse(-1));
        System.out.println("sumWithIdentity="
                + IntStream.empty().reduce(0, Integer::sum));
    }
}
~~~

~~~bash
javac --release 17 PrimitiveReduceDemo.java
java PrimitiveReduceDemo
~~~

Stdout:

~~~text
max=OptionalInt[7]
empty=OptionalInt.empty
default=-1
sumWithIdentity=0
~~~

`OptionalInt` không giống `Optional<Integer>` về kiểu tĩnh; tuy nhiên cả hai đều thể hiện trạng thái có/không có kết quả, và có các thao tác như `isPresent`, `orElse`, `orElseThrow`.

Trong Java, nếu mục tiêu chỉ là tổng của `IntStream`, `sum()` thường ngắn và rõ hơn `reduce(0, Integer::sum)`. Nếu cần **phân biệt không có phần tử với tổng bằng 0**, `IntStream.reduce(Integer::sum)` trả `OptionalInt` là một lựa chọn thích hợp.

## 13. `reduce`, `min/max`, `sum` và `collect`: chọn đúng terminal operation

Không phải mọi công việc tổng hợp đều nên dùng `reduce` thủ công:

| Mục tiêu | Cách thường nên chọn | Kết quả khi nguồn rỗng |
| --- | --- | --- |
| Rút gọn một phép kết hợp bất kỳ, không có identity phù hợp | `stream.reduce(op)` | `Optional.empty()` |
| Tổng `int` với 0 được chấp nhận | `intStream.sum()` | `0` |
| Tổng `int` nhưng cần biết nguồn có dữ liệu | `intStream.reduce(Integer::sum)` | `OptionalInt.empty()` |
| Tìm phần tử lớn/nhỏ nhất theo tiêu chí | `stream.max(comparator)` / `stream.min(comparator)` | `Optional.empty()` |
| Thu phần tử thành danh sách | `stream.toList()` hoặc `collect(toList())` | Danh sách rỗng |
| Tạo `Map`/grouping hoặc mutable reduction | `collect(collector)` | Giá trị do collector quy định |
| Đếm phần tử | `stream.count()` | `0L` |

Không nhầm `reduce(BinaryOperator<T>)` với `findFirst()`: cả hai có thể trả `Optional<T>`, nhưng `findFirst()` chỉ chọn một phần tử theo thứ tự gặp nếu có, còn `reduce` kết hợp dữ liệu bằng phép toán cung cấp.

Trong một số tình huống, `Collectors.reducing(...)` cũng xuất hiện như một downstream collector, nhưng đó là API khác với overload `Stream.reduce` đang bàn. Khi cần nhóm rồi rút gọn từng nhóm, hãy chọn collector phù hợp và đọc rõ kiểu trả về — có thể lồng `Optional` trong giá trị của `Map`.

## 14. Rủi ro với nguồn vô hạn và xử lý lại stream

`reduce` không identity là **terminal operation** và **không phải short-circuit theo ý nghĩa thông thường**: để biết kết quả của một phép tổng hợp tổng quát, nó phải xử lý các phần tử cần thiết của nguồn cho đến khi nguồn kết thúc. Với một stream vô hạn không có điểm dừng, gọi `reduce` để thu kết quả có thể không bao giờ hoàn tất.

Ví dụ tránh thực thi:

~~~java
// Đoạn cố ý minh họa trường hợp không có điểm dừng.
// Không chạy pipeline này rồi mong sẽ nhận một Optional hữu hạn:
// java.util.stream.Stream.iterate(1, n -> n + 1)
//         .reduce(Integer::sum);
~~~

Nếu dữ liệu được giới hạn theo nghiệp vụ, có thể dùng `limit(n)` **trước** `reduce`, nhưng cần hiểu rằng đó là phép rút gọn trên **phần dữ liệu bị giới hạn**, không phải trên toàn bộ nguồn ban đầu.

Cũng không gọi nhiều terminal operations trên một stream:

~~~java
// Minh họa sai nếu tiếp tục dùng lại chính instance s.
java.util.stream.Stream<Integer> s =
        java.util.stream.Stream.of(1, 2, 3);
java.util.Optional<Integer> sum = s.reduce(Integer::sum);
// s.count(); // Không hợp lệ vì s đã được tiêu thụ.
~~~

Nếu cần vừa `count` vừa `sum`, cân nhắc primitive `summaryStatistics()`, collector tổng hợp, hoặc tạo lại stream từ nguồn có thể đọc lại. Đối với nguồn một lần như I/O, database cursor hoặc dữ liệu động, không giả định có thể đọc lại mà không có chi phí hoặc sai khác.

## 15. Kiểm tra triệt để các trường hợp biên

Với một hàm rút gọn quan trọng, tối thiểu nên kiểm tra:

| Dữ liệu | Trường hợp muốn xác minh |
| --- | --- |
| `[]` | `Optional.empty()`, không có giá trị bị bịa ra. |
| `[9]` | `Optional[9]`, accumulator không cần chạy. |
| `[2, 3, 4]` | `Optional[9]` cho phép cộng. |
| `[-9, -3, -12]` | Max thực sự là `-3`, không phải identity giả `0`. |
| `[-3, 3]` | Tổng là `Optional[0]`, **khác** empty. |
| Nhiều bản ghi cùng khóa max | Quy tắc hòa ổn định và phù hợp nghiệp vụ. |
| Nguồn song song, phép toán kết hợp hợp lệ | Kết quả có ý nghĩa như nguồn tuần tự. |
| Hàm rút gọn trả `null` | Đây là lỗi hợp đồng, không phải “empty”. |
| Dữ liệu có null | Có chính sách lọc/từ chối null rõ ràng. |
| Nguồn rất lớn hoặc vô hạn | Giới hạn và mức sử dụng tài nguyên phù hợp. |

Không tự động coi `Optional.empty()` là lỗi. Đôi khi stream rỗng là kết quả bình thường của truy vấn sau `filter`. Trách nhiệm của tầng nghiệp vụ là quyết định biểu diễn trạng thái vắng mặt thành giá trị mặc định, thông báo, hoặc ngoại lệ.

## 16. Các lỗi thường gặp khi viết `reduce()` không identity

1. **Gán trực tiếp kết quả vào `T`:** `int sum = stream.reduce(Integer::sum)` là sai kiểu; kết quả thực là `Optional<Integer>`.
2. **Gọi `get()` vô điều kiện:** `Optional.empty().get()` ném `NoSuchElementException`. Dùng `orElse`, `orElseThrow`, `ifPresent` hoặc xử lý Optional theo hợp đồng.
3. **Coi empty bằng `0`:** một stream rỗng và stream có tổng bằng 0 là hai tình trạng khác nhau.
4. **Chọn identity sai cho phép `max/min`:** `reduce(0, Integer::max)` làm sai kết quả khi mọi số âm.
5. **Viết accumulator không có tính kết hợp:** phép trừ hoặc logic phụ thuộc thứ tự nhóm có thể cho kết quả không ổn định khi chạy parallel.
6. **Trả `null` từ accumulator:** overload này yêu cầu kết quả reduction hợp lệ; null có thể gây `NullPointerException`.
7. **Tưởng `Stream<Order>.reduce(...)` có thể trả số nguyên:** reducer một tham số phải nhận và trả cùng kiểu phần tử `Order`.
8. **Dùng accumulator để thay một collector mutable:** dễ có side effect và dữ liệu chia sẻ không an toàn.
9. **Dùng lại stream sau `reduce`:** terminal operation tiêu thụ stream; cần tạo stream mới nếu nguồn hỗ trợ.
10. **Bỏ qua số lượng phần tử:** reducer không gọi accumulator khi nguồn rỗng hoặc một phần tử, nên chỉ kiểm thử nhiều phần tử có thể bỏ sót lỗi.
11. **Cho rằng reducer luôn chạy lần lượt từ trái sang phải:** thực thi song song có thể nhóm khác; chỉ dựa vào hợp đồng associative và stateless.
12. **Dùng reduce trên nguồn vô hạn không có điều kiện kết thúc:** có thể không trả kết quả.
13. **Nhầm `Optional<T>` với `OptionalInt`:** chọn đúng API của `Stream<T>` hay primitive stream.
14. **Dùng `orElse(expensive())` và tưởng fallback lazy:** đối số được đánh giá trước; dùng `orElseGet` khi cần trì hoãn.

## 17. Checklist trước khi chọn overload `reduce`

1. Hàm rút gọn có đúng kiểu `T × T → T` không?
2. Trên **nguồn rỗng**, nghiệp vụ muốn “không có kết quả” hay một identity cụ thể?
3. Nếu không có identity, người gọi đã xử lý `Optional<T>` chưa?
4. Accumulator có **associative**, không can thiệp nguồn và không phụ thuộc mutable state không?
5. Accumulator có thể trả `null`, ném lỗi, hoặc nhận phần tử null không?
6. Nếu chạy parallel, kết quả có còn đúng với các cách nhóm khác nhau không?
7. Phép tổng hợp này đã có terminal operation chuyên biệt rõ nghĩa hơn, như `sum`, `min`, `max` hay `collect` chưa?
8. Đã kiểm thử nguồn rỗng, một phần tử, giá trị biên, và giá trị thực bằng identity mặc định chưa?

**Ghi nhớ:** `Stream<T>.reduce(BinaryOperator<T>)` **không có identity** nên trả `Optional<T>`: stream rỗng → `Optional.empty()`, một phần tử → `Optional` chứa phần tử đó, nhiều phần tử → `Optional` chứa giá trị rút gọn nếu phép toán hợp lệ. Hãy để `Optional` biểu diễn trạng thái không có dữ liệu và dùng `orElse`/ `orElseThrow` chỉ khi đã chọn rõ chính sách nghiệp vụ; không thay bằng identity tùy tiện hay trả `null` từ accumulator.
