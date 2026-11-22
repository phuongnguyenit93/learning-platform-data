# Dùng reduce với identity và accumulator

Trong Java Stream API, **`reduce`** là thao tác *rút gọn* (*reduction*): biến nhiều phần tử thành một kết quả bằng cách kết hợp các phần tử theo một quy tắc. Với dạng `reduce(identity, accumulator)`, lập trình viên cung cấp **giá trị trung hòa** (*identity*) và **phép kết hợp** (*accumulator*). Hai thành phần này quyết định cả kết quả khi Stream rỗng lẫn khả năng xử lý đúng khi Stream chạy song song.

Bài học thuộc chương **Phép rút gọn với reduce** của mô-đun **JAVA_STREAM_API**. Kiến thức này tiếp nối cách xây dựng pipeline lazy với `filter`, `map`, `reduce` và `collect`, đồng thời đặt nền tảng cho các bài tổng hợp, nhóm dữ liệu, collector tùy chỉnh, xử lý song song và đánh giá giới hạn về trạng thái, kiểu số, tài nguyên và hiệu năng.

## 1. Tư duy rút gọn: từ nhiều phần tử về một giá trị

Giả sử ta có ba số `[4, 6, 10]` và cần tính tổng. Vòng lặp quen thuộc:

```java
import java.util.List;

List<Integer> numbers = List.of(4, 6, 10);

int total = 0;
for (int number : numbers) {
    total += number;
}

System.out.println(total); // 20
```

Cùng ý nghĩa bằng Stream:

```java
int total = numbers.stream()
    .reduce(0, Integer::sum);

System.out.println(total); // 20
```

Trong biểu thức `reduce(0, Integer::sum)`:

- **`0` là identity**: giá trị trung hòa của phép cộng. `0 + x = x` và `x + 0 = x`.
- **`Integer::sum` là accumulator**: quy tắc lấy hai số nguyên và trả về tổng của chúng.
- **`20` là kết quả**: một giá trị được tạo ra từ toàn bộ Stream.

Ta có thể hình dung một cách thực thi tuần tự như sau:

```text
identity = 0
0  -- cộng 4  -->  4
4  -- cộng 6  --> 10
10 -- cộng 10 --> 20
                     |
                     v
                 kết quả = 20
```

Hình này giúp hiểu phép rút gọn **tuần tự**, nhưng không có nghĩa JVM luôn phải gọi accumulator đúng theo cây tính toán đó. Đặc biệt khi song song, các phần tử có thể được rút gọn thành nhiều kết quả từng phần rồi kết hợp lại.

## 2. Chữ ký API và vai trò của hai tham số

Với Stream đối tượng, phiên bản cần học có dạng:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

`BinaryOperator<T>` là functional interface trong `java.util.function`, nhận **hai giá trị cùng kiểu `T`** và trả lại một giá trị **cùng kiểu `T`**. Nó là một trường hợp chuyên biệt của `BiFunction<T, T, T>`.

```java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> add = (left, right) -> left + right;
BinaryOperator<Integer> max = Integer::max;

System.out.println(add.apply(4, 6)); // 10
System.out.println(max.apply(4, 6)); // 6
```

| Thành phần | Kiểu | Vai trò |
| --- | --- | --- |
| Nguồn `Stream<T>` | Các phần tử kiểu `T` | Cung cấp giá trị cần rút gọn |
| `identity` | `T` | Giá trị trung hòa, đồng thời là kết quả khi Stream rỗng |
| `accumulator` | `BinaryOperator<T>` | Ghép hai giá trị kiểu `T` thành một giá trị kiểu `T` |
| Kết quả `reduce` | `T` | Giá trị rút gọn cuối cùng |

Các Primitive Stream cũng có dạng tương ứng:

| Nguồn | Dạng `reduce` | Kiểu kết quả |
| --- | --- | --- |
| `IntStream` | `reduce(int identity, IntBinaryOperator accumulator)` | `int` |
| `LongStream` | `reduce(long identity, LongBinaryOperator accumulator)` | `long` |
| `DoubleStream` | `reduce(double identity, DoubleBinaryOperator accumulator)` | `double` |

Ví dụ:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int intTotal = IntStream.of(4, 6, 10)
    .reduce(0, Integer::sum);

long longTotal = LongStream.of(4L, 6L, 10L)
    .reduce(0L, Long::sum);

System.out.println(intTotal);  // 20
System.out.println(longTotal); // 20
```

`reduce` là **terminal operation**: nó kích hoạt quá trình tiêu thụ pipeline. Một Stream đã dùng cho `reduce` không được dùng lại cho terminal operation khác.

## 3. Chọn identity: giá trị trung hòa, không phải “số khởi tạo tùy ý”

Điều kiện quan trọng nhất của identity là: với mọi giá trị `x` hợp lệ trong miền dữ liệu, phép kết hợp với identity phải giữ nguyên ý nghĩa của `x`.

```text
accumulator(identity, x) = x
```

Với các phép rút gọn thường gặp, identity còn là phần tử trung hòa cả hai phía:

```text
accumulator(identity, x) = x
accumulator(x, identity) = x
```

Ví dụ:

| Mục tiêu | Identity | Accumulator | Vì sao |
| --- | --- | --- | --- |
| Tính tổng | `0` | `Integer::sum` | Cộng 0 không làm thay đổi số |
| Tính tích | `1` | `(a, b) -> a * b` | Nhân 1 không làm thay đổi số |
| Ghép chuỗi | `""` | `String::concat` | Ghép chuỗi rỗng không thêm nội dung |
| Lấy giá trị lớn nhất trong miền `int` | `Integer.MIN_VALUE` | `Integer::max` | Mọi `int` đều lớn hơn hoặc bằng giá trị nhỏ nhất |
| Lấy giá trị nhỏ nhất trong miền `int` | `Integer.MAX_VALUE` | `Integer::min` | Mọi `int` đều nhỏ hơn hoặc bằng giá trị lớn nhất |
| Tổng logic “tất cả đúng” trên `Boolean` | `true` | `(a, b) -> a && b` | `true && x` bằng `x` |
| Tổng logic “có ít nhất một đúng” trên `Boolean` | `false` | `(a, b) -> a \|\| b` | `false \|\| x` bằng `x` |

Với các phép `min`/`max`, chọn giá trị biên như trên chỉ hợp lý khi **toàn bộ miền dữ liệu đã được xác định**. Kết quả của Stream rỗng sẽ là giá trị biên đó, có thể gây nhầm lẫn với một phần tử thật bằng giá trị biên. Khi cần phân biệt **không có dữ liệu**, dạng `reduce` không identity hoặc `min()`/`max()` trả về `Optional` thường phù hợp hơn.

### 3.1. Ví dụ với tích

```java
import java.util.List;

List<Integer> factors = List.of(2, 3, 4);

int product = factors.stream()
    .reduce(1, (left, right) -> left * right);

System.out.println(product); // 24
```

Nếu dùng `0` làm identity cho phép nhân, kết quả luôn bằng `0` trong quá trình rút gọn tuần tự và mất hoàn toàn thông tin đầu vào.

### 3.2. Sai lầm: dùng một giá trị khởi tạo không trung hòa

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// Sai nếu muốn tính "tổng các phần tử".
int misleading = values.stream()
    .reduce(10, Integer::sum);

System.out.println(misleading); // 16 trong pipeline tuần tự
```

Trong phép cộng, `10` không phải identity. Với xử lý tuần tự, ví dụ trên tính `10 + 1 + 2 + 3`, tức **tổng cộng thêm 10**, chứ không phải tổng các phần tử. Khi song song, giá trị `10` có thể được dùng cho nhiều kết quả từng phần, khiến chênh lệch lớn hơn và phụ thuộc cách chia dữ liệu.

Nếu thật sự cần **phụ phí 10 sau tổng**, hãy biểu diễn ý định một cách tường minh:

```java
int totalWithSurcharge = values.stream()
    .reduce(0, Integer::sum) + 10;

System.out.println(totalWithSurcharge); // 16
```

Ở đây `reduce(0, Integer::sum)` là phép rút gọn hợp lệ; phép thêm phụ phí được thực hiện **sau** khi đã có kết quả.

## 4. Accumulator cần có tính kết hợp (*associativity*)

Để một phép rút gọn có thể được chia thành nhiều nhóm mà vẫn giữ kết quả, accumulator phải **có tính kết hợp**:

```text
accumulator(accumulator(a, b), c)
    =
accumulator(a, accumulator(b, c))
```

Với phép cộng số nguyên (khi kết quả được hiểu theo ngữ nghĩa số nguyên Java), ta có:

```text
(2 + 3) + 4 = 2 + (3 + 4) = 9
```

**Phép trừ** không có tính kết hợp:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Vì thế đoạn sau không phải một thiết kế rút gọn đúng đắn cho xử lý song song:

```java
import java.util.stream.IntStream;

int sequential = IntStream.of(10, 3, 2)
    .reduce(0, (left, right) -> left - right);

System.out.println(sequential); // -15 với cách thực thi tuần tự
```

Kết quả rút gọn bằng phép trừ có thể thay đổi khi cách nhóm phần tử thay đổi. Đừng dùng `parallel()` với accumulator không có tính kết hợp rồi kỳ vọng kết quả giống cách tính tuần tự.

### 4.1. Tính kết hợp khác tính giao hoán

Hai khái niệm thường bị nhầm:

- **Kết hợp:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Giao hoán:** `a ⊕ b = b ⊕ a`.

`String::concat` là phép kết hợp, nhưng không giao hoán:

```java
import java.util.List;

List<String> letters = List.of("A", "B", "C");

String joined = letters.stream()
    .reduce("", String::concat);

System.out.println(joined); // ABC
```

`"A" + "B"` khác `"B" + "A"`. Với nguồn có thứ tự và phép rút gọn hợp lệ, Stream có thể kết hợp các phần mà vẫn giữ thứ tự gặp theo ngữ nghĩa của phép rút gọn. Tuy nhiên, `reduce` không phải giải pháp hiệu quả nhất để nối nhiều chuỗi, vì phép nối chuỗi lặp đi lặp lại có thể tạo nhiều đối tượng tạm. Khi mục tiêu là ghép chuỗi, thường dùng `Collectors.joining()`.

Không nên gắn tác dụng phụ (ví dụ ghi log, tăng bộ đếm dùng chung) vào accumulator rồi dựa vào thứ tự hoặc số lần hàm được gọi. Khi chạy song song, cách nhóm và số lần kết hợp có thể khác.

## 5. Stream rỗng: kết quả chính là identity

Đặc điểm quan trọng của phiên bản **hai tham số** là luôn trả về `T`, kể cả khi nguồn không có phần tử. Lúc đó kết quả chính là identity.

```java
import java.util.List;

List<Integer> emptyNumbers = List.of();

int sum = emptyNumbers.stream()
    .reduce(0, Integer::sum);

int product = emptyNumbers.stream()
    .reduce(1, (a, b) -> a * b);

System.out.println(sum);     // 0
System.out.println(product); // 1
```

Đây là ngữ nghĩa hợp lệ: **tổng của tập rỗng được định nghĩa bằng 0**, còn **tích của tập rỗng được định nghĩa bằng 1**, tương ứng với phần tử trung hòa của mỗi phép toán.

Nhưng `reduce(identity, accumulator)` không nói liệu kết quả đến từ tập rỗng hay từ các phần tử thật:

```java
List<Integer> zeroSum = List.of(2, -2);
List<Integer> noData = List.of();

int a = zeroSum.stream().reduce(0, Integer::sum);
int b = noData.stream().reduce(0, Integer::sum);

System.out.println(a); // 0: có dữ liệu nhưng tổng bằng 0
System.out.println(b); // 0: không có dữ liệu
```

Nếu yêu cầu nghiệp vụ cần phân biệt hai trường hợp, hãy thiết kế kết quả bao gồm trạng thái tồn tại dữ liệu hoặc dùng dạng `reduce` trả về `Optional`.

### 5.1. So sánh với `reduce(accumulator)` không có identity

`Stream<T>` còn cung cấp:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

Đây là phiên bản **không có identity**. Khi Stream rỗng, kết quả là `Optional.empty()`.

```java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of();

Optional<Integer> maxValue = numbers.stream()
    .reduce(Integer::max);

System.out.println(maxValue.isPresent()); // false

Optional<Integer> withData = List.of(-5, -2, -9)
    .stream()
    .reduce(Integer::max);

System.out.println(withData.orElseThrow()); // -2
```

Để lấy giá trị lớn nhất, `stream.max(Integer::compare)` diễn đạt rõ hơn mục đích; ví dụ trên chỉ minh họa khác biệt về kết quả trên Stream rỗng.

| Phiên bản | Stream rỗng | Trường hợp nên dùng |
| --- | --- | --- |
| `reduce(identity, accumulator)` | Trả về `identity` | Có phần tử trung hòa hợp lệ, muốn luôn nhận giá trị `T` |
| `reduce(accumulator)` | `Optional.empty()` | Không có identity thích hợp hoặc cần biết tập rỗng |
| `sum()` của Primitive Stream | Trả về `0` đúng kiểu số | Chỉ cần cộng các giá trị nguyên thủy |
| `min()` / `max()` của Primitive Stream | `OptionalInt` / `OptionalLong` / `OptionalDouble` rỗng | Tìm cực trị và cần phản ánh thiếu dữ liệu |

## 6. Kết hợp `filter`, `map` và `reduce` trong một bài toán

Pipeline thực tế thường có dạng:

```text
Nguồn         Các thao tác trung gian (lazy)       Terminal operation
List<Sale> --> filter(paid) --> map(amount) --> reduce(0, sum)
                   |                |                   |
               chọn đơn        lấy giá trị         tổng doanh thu
```

Giả sử chỉ tính doanh thu các đơn đã thanh toán, đơn giá và số lượng được ghi bằng số nguyên `long` theo đơn vị VND:

```java
import java.util.List;

public class RevenueReduceDemo {
    record Sale(String id, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S-01", 1_500_000L, true),
            new Sale("S-02",   800_000L, false),
            new Sale("S-03", 2_000_000L, true)
        );

        long revenue = sales.stream()
            .filter(Sale::paid)             // Stream<Sale>
            .mapToLong(Sale::amountVnd)     // LongStream
            .reduce(0L, Long::sum);         // long

        System.out.println(revenue);        // 3500000
    }
}
```

Ở đây, `LongStream.reduce(0L, Long::sum)` là một phép giảm rõ ràng. Vì mục tiêu chỉ là tổng, `.sum()` cũng tương đương về ý định và ngắn hơn:

```java
long revenue = sales.stream()
    .filter(Sale::paid)
    .mapToLong(Sale::amountVnd)
    .sum();
```

Khi cần một quy tắc giảm *khác* các thao tác tích hợp sẵn, `reduce` có giá trị hơn. Ví dụ lấy giá trị lớn nhất nhưng chủ động chọn `Long.MIN_VALUE` làm identity:

```java
long largestAmount = sales.stream()
    .mapToLong(Sale::amountVnd)
    .reduce(Long.MIN_VALUE, Long::max);
```

Với danh sách rỗng, ví dụ trả về `Long.MIN_VALUE`. Nếu cần biểu diễn “không có đơn hàng”, nên dùng `mapToLong(...).max()` và xử lý `OptionalLong`, thay vì dùng một giá trị đặc biệt có thể trùng với dữ liệu thực.

## 7. Identity phải phù hợp với chính kiểu của phần tử đang reduce

Ở phiên bản hai tham số của `Stream<T>`, identity và accumulator sử dụng cùng `T`. Điều này ảnh hưởng cách tổ chức pipeline.

Ví dụ `Stream<Order>` không thể giảm thẳng thành `long` bằng **phiên bản hai tham số**:

```java
// Giả sử Sale là record đã định nghĩa trong ví dụ RevenueReduceDemo.
// Sai kiểu: Stream<Sale>.reduce(T identity, BinaryOperator<T>)
// không nhận một identity kiểu long để trả ra long:
//
// long total = sales.stream().reduce(0L,
//     (sum, sale) -> sum + sale.amountVnd());
```

Để tổng hợp tiền, chuyển kiểu phần tử trước:

```java
long total = sales.stream()
    .mapToLong(Sale::amountVnd)
    .reduce(0L, Long::sum);
```

Hoặc chuyển thành đối tượng `BigInteger` nếu miền `long` không đủ:

```java
import java.math.BigInteger;

BigInteger totalExact = sales.stream()
    .map(sale -> BigInteger.valueOf(sale.amountVnd()))
    .reduce(BigInteger.ZERO, BigInteger::add);
```

Trong Java còn có dạng `Stream<U>.reduce(identity, accumulator, combiner)` với **ba tham số**, cho phép kết quả kiểu khác phần tử nguồn và định nghĩa rõ cách hợp nhất kết quả từng phần. Đó là một hợp đồng khác, đặc biệt cần chú ý tính tương thích giữa accumulator và combiner; không nên lẫn nó với phiên bản hai tham số đang học.

## 8. Accumulator nên là phép kết hợp thuần và không sửa trạng thái chung

Một accumulator phù hợp cho `reduce` có các đặc điểm:

1. **Không can thiệp nguồn** (*non-interfering*): không thay đổi bộ sưu tập đang được Stream duyệt.
2. **Không phụ thuộc trạng thái có thể thay đổi** (*stateless*): kết quả phụ thuộc vào hai toán hạng, không phụ thuộc số lần gọi hay thời điểm.
3. **Có tính kết hợp** (*associative*): cách nhóm phép kết hợp không làm đổi kết quả theo ngữ nghĩa đã chọn.
4. **Dùng identity hợp lệ**: ghép với identity không làm đổi giá trị.

Ví dụ `BigInteger::add` là một phép kết hợp thích hợp: `BigInteger` bất biến, `add` tạo một kết quả mới và có phần tử trung hòa `BigInteger.ZERO`.

Ngược lại, một accumulator cố sửa một container bên ngoài rất dễ phá vỡ các giả định của Stream:

```java
// Không nên làm:
int[] sumOutside = {0};

int result = java.util.stream.IntStream.of(1, 2, 3)
    .reduce(0, (acc, value) -> {
        sumOutside[0] += value;  // Tác dụng phụ.
        return acc + value;
    });
```

Đoạn này có thể tạo hai giá trị tổng trong các đường thực thi khác nhau; `sumOutside` không phải sản phẩm chính thức của phép `reduce`. Với `parallel()`, cập nhật không đồng bộ còn có thể gây race condition. Cách đúng là lấy kết quả do `reduce` trả về.

### 8.1. Vì sao không dùng `reduce` để thay `collect` cho cấu trúc có thể thay đổi?

Giả sử muốn gộp nhiều danh sách thành một danh sách. Mã sau **không an toàn để dùng làm phép rút gọn**, đặc biệt khi song song:

```java
import java.util.ArrayList;
import java.util.List;

List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C")
);

// Không nên dùng: accumulator sửa trực tiếp đối tượng left,
// trong đó identity là một ArrayList có thể thay đổi.
List<String> unsafe = groups.stream()
    .reduce(
        new ArrayList<>(),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Phép thay đổi trực tiếp `left` có thể sửa cả identity dùng chung giữa các nhánh xử lý song song, dẫn tới kết quả lặp hoặc race condition. Ngay cả khi ví dụ có thể cho kết quả mong muốn trong một lượt duyệt tuần tự, đây vẫn là mô hình không nên áp dụng cho `reduce`.

Đối với mục tiêu này, có hai cách thể hiện đúng hơn:

```java
List<String> flattened = groups.stream()
    .flatMap(List::stream)
    .toList();

List<String> mutableFlattened = groups.stream()
    .flatMap(List::stream)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

`toList()` trả danh sách không thể sửa; `toCollection(ArrayList::new)` tạo danh sách cho phép thêm/xóa phần tử. Trong `collect`, các bộ tích lũy có thể thay đổi được quản lý bằng **supplier, accumulator và combiner** theo hợp đồng của collector. Còn `reduce` được thiết kế cho các phép kết hợp mà toán hạng không bị sửa đổi.

### 8.2. Nối chuỗi: phép giảm hợp lệ chưa chắc hiệu quả

```java
List<String> words = List.of("Java", "Stream", "API");

String joinedByReduce = words.stream()
    .reduce("", String::concat);

String joinedByCollector = words.stream()
    .collect(java.util.stream.Collectors.joining());

System.out.println(joinedByReduce);    // JavaStreamAPI
System.out.println(joinedByCollector); // JavaStreamAPI
```

Cả hai cho cùng nội dung, nhưng `Collectors.joining()` thường phù hợp hơn khi ghép nhiều chuỗi vì cách tích lũy tránh việc tạo chuỗi trung gian theo phép nối lặp lại. Chọn `reduce` khi mục tiêu là hiểu hoặc cần một phép kết hợp bất biến có ý nghĩa.

## 9. Song song: identity có thể tham gia nhiều lần

Trong Stream tuần tự, ví dụ cộng tổng có thể được hiểu như một phép tích lũy từ trái sang phải. Với Stream song song, framework có thể chia nguồn thành nhiều nhóm, rút gọn mỗi nhóm từ identity, rồi kết hợp các kết quả.

Minh họa phép cộng với identity đúng:

```text
Dữ liệu: [2, 3, 4, 5]

Nhánh A: identity 0 -> cộng 2 -> cộng 3 = 5
Nhánh B: identity 0 -> cộng 4 -> cộng 5 = 9
Kết hợp 5 và 9 = 14

Toàn bộ: 2 + 3 + 4 + 5 = 14
```

Đây chỉ là một cách nhóm để giải thích; cách chia thực tế do Stream implementation quyết định. Với identity `0` và `Integer::sum`, phép tính có ngữ nghĩa hợp lệ dưới cách nhóm này.

Nếu nhầm `identity = 10` là “cộng thêm 10 chỉ một lần”, mỗi nhánh có thể được cộng thêm 10, rồi khi kết hợp sẽ nhận sai khác so với xử lý tuần tự. Vì vậy identity phải là **phần tử trung hòa**, không phải tham số chứa điều chỉnh nghiệp vụ.

```java
import java.util.stream.IntStream;

int total = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0, Integer::sum);

System.out.println(total); // 500500
```

**Quan trọng:** `parallel()` không tự làm phép toán nhanh hoặc chính xác hơn. Hiệu năng phụ thuộc số phần tử, chi phí của accumulator, khả năng tách nguồn (`Spliterator`), overhead chia/ghép và tài nguyên máy. Với phép cộng nhỏ, tuần tự thường là lựa chọn đơn giản hơn. Một accumulator có tác dụng phụ hay không kết hợp không trở nên đúng chỉ vì chương trình dùng nhiều luồng.

## 10. Tính lazy, short-circuit và tài nguyên

`filter`, `map` và `mapToLong` là các thao tác trung gian thường được đánh giá **lazy**; `reduce` là terminal operation kích hoạt quá trình xử lý:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

var prepared = numbers.stream()
    .filter(n -> n % 2 == 1)
    .map(n -> n * n); // Chưa tính tổng.

int squaredOddTotal = prepared
    .reduce(0, Integer::sum);

System.out.println(squaredOddTotal); // 1 + 9 + 25 = 35
```

`reduce` thông thường cần duyệt tất cả phần tử **do các bước trung gian chuyển tới**, trái với `anyMatch` hoặc `findFirst` có thể dừng sớm khi đã có câu trả lời. Không nên dựa vào tác dụng phụ bên trong các thao tác trung gian để khẳng định chúng đã chạy đúng một lần trên mọi phần tử; các tối ưu và cách thực thi có thể thay đổi khi pipeline khác đi.

Nếu nguồn Stream gắn với tài nguyên như `Files.lines(path)`, phải đóng nguồn phù hợp bằng `try-with-resources`, ngay cả khi terminal operation là `reduce`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Đặt trong phương thức có khai báo throws IOException, hoặc xử lý ngoại lệ.
Path path = Path.of("numbers.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long sum = lines
        .filter(s -> !s.isBlank())
        .mapToLong(Long::parseLong)
        .reduce(0L, Long::sum);

    System.out.println(sum);
}
```

Bản thân phép `reduce` không tự biến mọi nguồn I/O thành một tài nguyên tự đóng. Đồng thời, một Stream đã tiêu thụ bởi `reduce` không thể sử dụng lại; nếu cần phép tính khác từ cùng tệp, phải thiết kế việc đọc và lưu/duyệt lại theo yêu cầu tài nguyên.

## 11. Độ chính xác và giới hạn hiệu năng

Dù phép cộng có identity đúng và tính kết hợp, kết quả số nguyên vẫn có thể **tràn kiểu**.

```java
import java.util.stream.IntStream;

int overflowed = IntStream.of(Integer.MAX_VALUE, 1)
    .reduce(0, Integer::sum);

long widened = IntStream.of(Integer.MAX_VALUE, 1)
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(overflowed); // -2147483648
System.out.println(widened);    // 2147483648
```

Việc khai báo `long widened = intStream.reduce(0, Integer::sum)` **không sửa được tràn số**, vì phép cộng bằng `int` đã diễn ra trước khi gán. Phải mở rộng **trước** khi rút gọn.

Khi yêu cầu tổng số nguyên chính xác vượt cả `long`, có thể dùng `BigInteger`:

```java
import java.math.BigInteger;
import java.util.stream.LongStream;

BigInteger exact = LongStream.of(Long.MAX_VALUE, 1L)
    .mapToObj(BigInteger::valueOf)
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 9223372036854775808
```

Nếu muốn **phát hiện** tràn số trong phép cộng một kiểu hữu hạn, `Math.addExact` có thể được dùng làm accumulator, nhưng nó ném ngoại lệ khi **tổng trung gian** bị tràn. Một tổng cuối nằm trong giới hạn vẫn có thể có trung gian vượt giới hạn ở một cách nhóm nhất định. Khi yêu cầu là tổng toán học chính xác rồi mới kiểm tra có vừa kiểu đích hay không, hãy dùng kiểu đủ rộng hoặc `BigInteger` và chuyển ngược bằng `intValueExact()`/`longValueExact()`.

Với số thực `double`, phép cộng dấu phẩy động **không kết hợp chính xác theo toán học máy tính** do quy tắc làm tròn. Thứ tự gom nhóm trong pipeline song song có thể dẫn tới khác biệt ở các chữ số cuối. Khi nghiệp vụ yêu cầu thập phân chính xác (ví dụ tiền), cân nhắc `BigDecimal` với quy tắc `scale`/làm tròn phù hợp.

Ở đường chạy nhạy hiệu năng, `IntStream.sum()` hoặc `LongStream.sum()` thường diễn đạt trực tiếp nhu cầu tổng hơn `reduce(0, ...)`. Hãy đo với JMH và dữ liệu đại diện trước khi kết luận về chênh lệch tốc độ; tránh boxing hoặc tạo các đối tượng trung gian không cần thiết chỉ để trình bày phép cộng đơn giản.

## 12. Khi nào dùng `reduce` và khi nào dùng `collect`?

| Yêu cầu | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| Tổng `int`/`long`/`double` thông thường | `sum()` trên Primitive Stream | Có API chuyên biệt, rõ mục đích |
| Phép kết hợp bất biến có identity và tính kết hợp | `reduce(identity, accumulator)` | Diễn đạt trực tiếp quy tắc kết hợp |
| Tìm cực trị và cần biết nguồn rỗng | `min()`, `max()` hoặc `reduce(accumulator)` | Trả `Optional` khi không có phần tử |
| Thu thập thành `List`/`Set`/`Map` | `collect(...)` hoặc `toList()` | Dùng cơ chế tích lũy thích hợp cho container |
| Nhóm theo khóa và tính tổng nhóm | `groupingBy` kèm collector downstream | Giữ được khóa và kết quả theo nhóm |
| Ghép chuỗi có phân cách | `Collectors.joining(delimiter)` | Đúng mục đích, dễ đọc hơn phép nối thủ công |
| Phép tính theo trạng thái của phần tử trước, cần nhiều kết quả trung gian | Vòng lặp hoặc công cụ xử lý trạng thái chuyên dụng | `reduce` chỉ cho một kết quả cuối, không cung cấp toàn bộ diễn tiến |

Trong phần chuyên sâu của Java Stream API, collector tùy chỉnh, `Spliterator` và Stream Gatherers có thể giúp giải các bài toán cần tích lũy, tách nguồn hoặc biến đổi trạng thái phức tạp. Tuy vậy, khi bài toán chỉ cần **một phép kết hợp có identity đúng**, `reduce` thường là điểm khởi đầu đủ rõ ràng.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chọn `10` làm identity của phép cộng | Không trung hòa; song song có thể cộng nhiều lần | Dùng `0`, thực hiện cộng phụ phí sau phép giảm |
| Chọn `0` làm identity của phép nhân | Tích luôn bằng 0 trong tính toán tuần tự | Dùng `1` |
| Dùng phép trừ hoặc phép chia làm accumulator tùy ý | Không kết hợp; kết quả phụ thuộc cách nhóm | Thiết kế phép kết hợp có tính kết hợp hoặc dùng thuật toán tuần tự phù hợp |
| Dùng `reduce(Integer.MIN_VALUE, Integer::max)` và diễn giải đó là dữ liệu thật | Không phân biệt Stream rỗng với phần tử biên | Dùng `max()` trả `Optional` nếu cần phản ánh rỗng |
| Dùng accumulator có tác dụng phụ trên biến ngoài | Sai số lần tính, mất an toàn khi song song | Trả về kết quả qua accumulator và giá trị trả về của `reduce` |
| Sửa `ArrayList` làm identity của reduce | Nguy cơ chia sẻ/mutate trạng thái giữa nhánh song song | Dùng `collect` hoặc `flatMap(...).toList()` |
| Muốn tính `long` trực tiếp từ `Stream<Order>` bằng reduce hai tham số | Không khớp kiểu `T` của overload | Dùng `mapToLong` trước khi reduce hoặc overload ba tham số phù hợp |
| Dùng `reduce(0, Integer::sum)` cho tổng có thể vượt `int` | Tràn số âm thầm | Mở rộng trước bằng `asLongStream` hoặc dùng `BigInteger` |
| Gọi lại `reduce` trên cùng Stream | Stream đã tiêu thụ | Tạo Stream mới từ nguồn |
| Tưởng `reduce` tự đóng Stream từ tệp | Rò rỉ tài nguyên nguồn I/O | Dùng `try-with-resources` với nguồn cần đóng |

## 14. Bài tập thực hành

### Bài 1: Identity theo phép toán

Với `List<Integer> values = List.of(2, 3, 5)`, hãy viết `reduce` để tính tổng, tích và giá trị lớn nhất. Giải thích vì sao ba phép toán cần ba identity khác nhau. Sau đó thử với danh sách rỗng và ghi nhận kết quả.

### Bài 2: Sửa phép rút gọn không đúng khi song song

Đoạn sau dùng để “cộng thêm phí xử lý 50”:

```java
long amount = java.util.stream.LongStream.rangeClosed(1, 100)
    .parallel()
    .reduce(50L, Long::sum);
```

Vì sao `50L` không phải identity? Viết lại để kết quả là tổng các giá trị `1` đến `100` **cộng đúng một lần** `50`, không phụ thuộc mức độ song song.

### Bài 3: Chọn overload và xử lý rỗng

Cho `List<Integer>` có thể rỗng. Cần tìm số nhỏ nhất và phân biệt “không có dữ liệu” với số nhỏ nhất hợp lệ bằng `Integer.MAX_VALUE`. Vì sao `reduce(Integer.MAX_VALUE, Integer::min)` chưa đủ? Hãy dùng `reduce(Integer::min)` và xử lý `Optional<Integer>`.

### Bài 4: Rà soát tính kết hợp

Phân loại các accumulator sau theo tính kết hợp và identity thích hợp:

```java
Integer::sum
(a, b) -> a * b
(a, b) -> a - b
String::concat
Integer::max
```

Trong câu trả lời, phân biệt tính kết hợp với tính giao hoán, giải thích vì sao phép nối chuỗi giữ thứ tự vẫn có thể được kết hợp thành các nhóm.

### Bài 5: Tổng doanh thu với nhiều miền giá trị

Cho `List<Order>` có `amountVnd` kiểu `long` và `paid` kiểu `boolean`. Dùng `filter`, `mapToLong` và `reduce(0L, Long::sum)` để tính doanh thu đã thanh toán. Thử dữ liệu vượt `Long.MAX_VALUE`; sau đó viết lại bằng `BigInteger.ZERO` và `BigInteger::add`. Vì sao `BigInteger` cần được áp dụng **trước** phép tổng?

### Bài 6: Khi nào nên dùng collect?

Có danh sách các đoạn văn bản, cần ghép chúng bằng ký tự `", "` hoặc gom thành `List<String>` có thể sửa. So sánh `reduce` với `Collectors.joining(", ")` và `Collectors.toCollection(ArrayList::new)`. Giải thích vì sao dùng container mutable làm identity của `reduce` là nguy hiểm.

### Bài 7: Nguồn rỗng và giải thích nghiệp vụ

Một nhóm không có giao dịch. Cần phân biệt “tổng giao dịch bằng 0” với “chưa có giao dịch để tính tổng”. Hãy thiết kế đầu ra phù hợp bằng `Optional` hoặc một cấu trúc chứa `count` và `sum`; đừng mặc định rằng kết quả `0` từ `reduce(0, Long::sum)` đủ mô tả nghiệp vụ.

## 15. Tự kiểm tra kiến thức

- `reduce(identity, accumulator)` nhận kiểu dữ liệu gì và trả về gì?
- Điều kiện nào phải đúng để một giá trị là identity hợp lệ?
- Vì sao phép trừ không phải accumulator thích hợp cho reduce song song?
- “Có tính kết hợp” có đồng nghĩa “có tính giao hoán” hay không?
- Tại sao Stream rỗng trả về identity của phiên bản `reduce` hai tham số?
- Điểm khác biệt của `reduce(accumulator)` trả về `Optional` là gì?
- Vì sao giá trị khởi tạo cộng phụ phí không nên đưa vào identity?
- Vì sao nên dùng `collect` để tạo danh sách có thể thay đổi?
- Vì sao `reduce(0, Integer::sum)` vẫn có nguy cơ tràn số?
- Khi nào nên dùng `sum()`, `reduce` hoặc `Collectors.joining()`?

**Ghi nhớ:** Với `reduce(identity, accumulator)`, **identity phải là phần tử trung hòa** và **accumulator phải là phép kết hợp có tính kết hợp, không phụ thuộc trạng thái ngoài**. Hai điều kiện đó bảo đảm phép rút gọn có ý nghĩa đúng khi Stream rỗng hoặc được chia để xử lý song song. Chọn `sum()` cho phép cộng số học đơn giản, `reduce` cho một giá trị tổng hợp bất biến, và `collect` khi cần xây dựng container kết quả.
