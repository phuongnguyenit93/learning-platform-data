# Tạo nguồn nguyên thủy từ mảng, khoảng số và bộ sinh

Trong chương trình Java, chúng ta thường xử lý những dãy số như điểm kiểm tra, số lượng sản phẩm, chỉ số phần tử, mốc thời gian hoặc dữ liệu đo lường. Với **Java Stream API**, thay vì luôn chuyển chúng thành `List<Integer>` hay `List<Double>`, có thể tạo trực tiếp **Stream kiểu nguyên thủy** từ **mảng**, **khoảng số**, hoặc **bộ sinh giá trị** (*generator*).

Bài này thuộc chương **Stream kiểu nguyên thủy** của module **JAVA_STREAM_API**. Bạn sẽ học cách lựa chọn giữa `IntStream`, `LongStream` và `DoubleStream`, tạo nguồn hữu hạn hoặc không giới hạn, nối nguồn với pipeline `filter`, `map`, `reduce` và `collect`, đồng thời nhận diện những giới hạn về trạng thái, tài nguyên và hiệu năng. Đây là cơ sở để hiểu sâu hơn về `Spliterator`, xử lý song song và các cơ chế mở rộng pipeline như Stream Gatherers.

## 1. Ba kiểu Stream nguyên thủy trong Java

`java.util.stream` cung cấp ba giao diện chuyên biệt cho kiểu số nguyên thủy:

| Kiểu Stream | Kiểu phần tử | Ví dụ nguồn | Một số phép toán hữu ích |
|---|---|---|---|
| `IntStream` | `int` | `IntStream.of(1, 2)` | `sum()`, `average()`, `min()`, `max()` |
| `LongStream` | `long` | `LongStream.range(1L, 5L)` | `sum()`, `average()`, `min()`, `max()` |
| `DoubleStream` | `double` | `DoubleStream.of(1.5, 2.5)` | `sum()`, `average()`, `min()`, `max()` |

**Không có `FloatStream`, `ShortStream` hoặc `ByteStream` trong API chuẩn.** Những giá trị nhỏ hơn `int` có thể được xử lý bằng `IntStream`; giá trị `float` có thể được đưa vào `DoubleStream` khi phù hợp, với lưu ý về biểu diễn số thực.

So với `Stream<Integer>`, `Stream<Long>` và `Stream<Double>`, các Stream nguyên thủy cho phép nhiều phép toán số học làm việc trực tiếp trên giá trị `int`, `long` và `double`. Điều này thường tránh được chi phí **boxing/unboxing** khi biến số nguyên thủy thành đối tượng wrapper. Lợi ích hiệu năng cụ thể vẫn phụ thuộc vào pipeline và dữ liệu thực tế.

Ví dụ:

~~~java
import java.util.stream.IntStream;

int sum = IntStream.of(10, 20, 30)
    .filter(n -> n >= 20)
    .sum();

System.out.println(sum); // 50
~~~

`IntStream.of(...)` là **nguồn**; `filter(...)` là thao tác **trung gian**; `sum()` là thao tác **kết thúc**. Các quy tắc pipeline lazy và vòng đời sử dụng một lần vẫn áp dụng như với `Stream<T>`.

## 2. Bản đồ các cách tạo nguồn

Có ba nhóm chính trong phạm vi bài học:

~~~mermaid
flowchart TD
    A["Nguồn Stream nguyên thủy"] --> B["Từ mảng hoặc giá trị có sẵn"]
    A --> C["Từ khoảng số nguyên liên tiếp"]
    A --> D["Từ quy tắc sinh giá trị"]
    B --> E["Arrays.stream / of"]
    C --> F["IntStream.range / rangeClosed"]
    C --> G["LongStream.range / rangeClosed"]
    D --> H["iterate: phần tử kế tiếp từ phần tử trước"]
    D --> I["generate: lấy giá trị từ Supplier"]
    E --> J["filter / map / sum / average / toArray"]
    F --> J
    G --> J
    H --> J
    I --> J
~~~

| Nhu cầu | API ưu tiên | Loại nguồn |
|---|---|---|
| Đã có mảng `int[]`, `long[]` hoặc `double[]` | `Arrays.stream(array)` | Hữu hạn |
| Chỉ có vài số cố định | `IntStream.of(...)`, `LongStream.of(...)`, `DoubleStream.of(...)` | Hữu hạn |
| Cần các chỉ số từ 0 đến `size - 1` | `IntStream.range(0, size)` | Hữu hạn |
| Cần các số từ 1 đến `n`, gồm cả `n` | `IntStream.rangeClosed(1, n)` | Hữu hạn |
| Mỗi phần tử kế tiếp phụ thuộc phần tử trước | `IntStream.iterate(seed, next)` | Có thể vô hạn |
| Cần dãy lặp đến một điều kiện dừng | `IntStream.iterate(seed, hasNext, next)` (Java 9+) | Có điều kiện kết thúc |
| Mỗi phần tử do một nguồn cung cấp độc lập | `DoubleStream.generate(supplier)` | Có thể vô hạn |
| Cần số ngẫu nhiên với khoảng và kích thước xác định | `Random.ints(size, origin, bound)` hoặc họ tương ứng | Hữu hạn |

**Lưu ý:** `range` và `rangeClosed` chỉ có trên **`IntStream` và `LongStream`**. Không tồn tại `DoubleStream.range()` trong Java Stream API chuẩn.

## 3. Tạo Stream từ mảng nguyên thủy bằng Arrays.stream

Cách phổ biến nhất khi dữ liệu đã được lưu trong mảng là dùng các overload của `java.util.Arrays.stream`:

~~~java
import java.util.Arrays;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int[] quantities = {2, 4, 6};
long[] timestamps = {1_000L, 2_000L, 3_000L};
double[] temperatures = {21.5, 22.0, 20.5};

IntStream quantitiesStream = Arrays.stream(quantities);
LongStream timestampsStream = Arrays.stream(timestamps);
DoubleStream temperaturesStream = Arrays.stream(temperatures);

System.out.println(quantitiesStream.sum());           // 12
System.out.println(timestampsStream.max().orElse(-1L)); // 3000
System.out.println(temperaturesStream.average().orElse(Double.NaN)); // 21.3333...
~~~

Mỗi dòng `Arrays.stream(array)` trả về Stream có kiểu phần tử tương ứng với loại mảng. Cùng một mảng có thể tạo **nhiều Stream độc lập**, nhưng mỗi đối tượng Stream chỉ nên được tiêu thụ **một lần**.

### 3.1. Chỉ đọc một đoạn của mảng

`Arrays.stream` còn có các overload nhận `startInclusive` và `endExclusive`:

~~~java
import java.util.Arrays;

int[] scores = {10, 20, 30, 40, 50};

int sum = Arrays.stream(scores, 1, 4)
    .sum();

System.out.println(sum); // 20 + 30 + 40 = 90
~~~

Khoảng chỉ số `[1, 4)` gồm các vị trí **1, 2, 3**. Vị trí 4 không được lấy.

- `Arrays.stream(array, 0, array.length)` lấy toàn bộ mảng.
- `Arrays.stream(array, 2, 2)` trả về Stream rỗng.
- Giới hạn không hợp lệ (ví dụ `from > to` hoặc ngoài phạm vi mảng) gây lỗi kiểm tra chỉ số, chứ không tự co lại thành đoạn hợp lệ.

Đây là quy tắc ranh giới **nửa mở** tương tự `IntStream.range(start, end)` và thường giúp giảm lỗi lệch chỉ số (*off-by-one*).

### 3.2. Tránh nhầm Stream<int[]> với IntStream

`Stream.of(array)` có hành vi khác với `Arrays.stream(array)` khi `array` là mảng nguyên thủy:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int[] values = {1, 2, 3};

long wrongCount = Stream.of(values).count(); // 1
long rightCount = Arrays.stream(values).count(); // 3

System.out.println(wrongCount); // 1: một phần tử kiểu int[]
System.out.println(rightCount); // 3: ba phần tử kiểu int
~~~

`Stream.of(values)` ở đây tạo **`Stream<int[]>`** chứa cả mảng như **một phần tử**. Nếu muốn xử lý từng số `int`, hãy dùng `Arrays.stream(values)` hoặc `IntStream.of(values)`.

### 3.3. Mảng nguồn và thay đổi trạng thái

`Arrays.stream(array)` tạo nguồn dựa trên mảng đã cung cấp; đừng giả định nó là bản sao dữ liệu bất biến. Sửa mảng trong lúc pipeline đang duyệt có thể vi phạm yêu cầu **non-interference** và gây kết quả khó đoán, đặc biệt với xử lý song song.

Nếu cần dữ liệu chụp tại một thời điểm, sao chép trước rồi tạo nguồn từ bản sao:

~~~java
import java.util.Arrays;

int[] measurements = {5, 7, 9};
int[] snapshot = Arrays.copyOf(measurements, measurements.length);

int total = Arrays.stream(snapshot).sum(); // 21
~~~

Việc sao chép có chi phí bộ nhớ tương ứng kích thước mảng. Chỉ dùng khi cần ổn định dữ liệu nguồn hoặc bảo vệ trước các thay đổi bên ngoài.

## 4. Tạo Stream từ các giá trị có sẵn: of và empty

Khi chỉ cần vài giá trị trực tiếp, `of(...)` gọn hơn việc tạo mảng riêng:

~~~java
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int totalItems = IntStream.of(2, 3, 5).sum();             // 10
long largestId = LongStream.of(10L, 20L, 30L).max()
    .orElse(-1L);                                           // 30
double totalWeight = DoubleStream.of(0.5, 1.25, 2.0).sum(); // 3.75

System.out.println(totalItems);
System.out.println(largestId);
System.out.println(totalWeight);
~~~

`of` có overload nhận một giá trị và overload nhận **varargs**. Bạn cũng có thể truyền mảng đúng kiểu:

~~~java
int[] values = {4, 5, 6};
int[] copyOfValuesAsResult = IntStream.of(values).toArray();

System.out.println(java.util.Arrays.toString(copyOfValuesAsResult)); // [4, 5, 6]
~~~

Để biểu diễn nguồn không có phần tử:

~~~java
long count = IntStream.empty().count(); // 0
int sum = IntStream.empty().sum();      // 0
boolean hasValue = IntStream.empty().findFirst().isPresent(); // false
~~~

`IntStream.empty()`, `LongStream.empty()` và `DoubleStream.empty()` tránh phải tạo một mảng rỗng. Tuy nhiên, một phép tổng hợp trên Stream rỗng không phải lúc nào cũng trả số 0: `average()`, `min()` và `max()` trả các loại `Optional` không có giá trị.

## 5. Tạo khoảng số bằng range và rangeClosed

`IntStream` và `LongStream` có nguồn khoảng số liên tiếp với bước tăng **1**.

~~~java
IntStream.range(int startInclusive, int endExclusive)
IntStream.rangeClosed(int startInclusive, int endInclusive)

LongStream.range(long startInclusive, long endExclusive)
LongStream.rangeClosed(long startInclusive, long endInclusive)
~~~

Trong ký hiệu toán học:

- `range(a, b)` tạo các số từ `a` đến **trước `b`**, ứng với `[a, b)`.
- `rangeClosed(a, b)` tạo các số từ `a` đến **cả `b`**, ứng với `[a, b]`.

| Ví dụ | Giá trị | Số phần tử |
|---|---|---|
| `IntStream.range(1, 5)` | `1, 2, 3, 4` | 4 |
| `IntStream.rangeClosed(1, 5)` | `1, 2, 3, 4, 5` | 5 |
| `IntStream.range(5, 5)` | Rỗng | 0 |
| `IntStream.rangeClosed(5, 5)` | `5` | 1 |
| `LongStream.rangeClosed(-2L, 1L)` | `-2, -1, 0, 1` | 4 |
| `IntStream.rangeClosed(6, 3)` | Rỗng | 0 |

Khi `start >= end`, `range` trả dãy rỗng; khi `start > end`, `rangeClosed` trả dãy rỗng. Cả hai **không tự tạo dãy giảm** khi điểm bắt đầu lớn hơn điểm kết thúc.

### 5.1. Đánh số chỉ số trong danh sách

Vị trí hợp lệ của một `List` có `n` phần tử là `0` đến `n - 1`. Vì vậy, `range(0, n)` đặc biệt phù hợp cho xử lý theo chỉ số:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> names = Arrays.asList("An", "Bình", "Chi");

IntStream.range(0, names.size())
    .mapToObj(index -> (index + 1) + ". " + names.get(index))
    .forEach(System.out::println);
~~~

Kết quả:

~~~text
1. An
2. Bình
3. Chi
~~~

Không dùng `rangeClosed(0, names.size())` cho chỉ số: nó phát thêm `names.size()` và sẽ gây `IndexOutOfBoundsException` khi truy cập phần tử cuối giả định đó.

Với `List` có truy cập chỉ số chậm như `LinkedList`, gọi `get(index)` nhiều lần có thể kém hiệu quả. Nếu không cần vị trí, `names.stream()` thường rõ ràng và phù hợp hơn.

### 5.2. Tạo các giá trị số thứ tự, kể cả giá trị cuối

~~~java
int sum1To5 = IntStream.rangeClosed(1, 5).sum(); // 15
long count = LongStream.range(100L, 105L).count(); // 5

System.out.println(sum1To5);
System.out.println(count);
~~~

Dùng `rangeClosed` khi nghiệp vụ nói “từ 1 **đến hết** 5”, hoặc “các ngày từ 1 **đến ngày cuối tháng**”.

### 5.3. Giới hạn kiểu số và tràn số

Không nên mô phỏng khoảng đóng bằng cách luôn viết `range(start, end + 1)`, vì `end + 1` có thể tràn tại `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE`.

~~~java
import java.util.stream.IntStream;

int last = Integer.MAX_VALUE;

int[] tail = IntStream.rangeClosed(last - 2, last)
    .toArray();

System.out.println(java.util.Arrays.toString(tail));
// [2147483645, 2147483646, 2147483647]
~~~

Cần phân biệt **khả năng mô tả nguồn** với **khả năng thu thập hoặc tổng hợp toàn bộ nguồn**. Một khoảng cực lớn là hợp lệ, nhưng `toArray()` có thể không phù hợp do giới hạn bộ nhớ/kích thước mảng.

Đặc biệt, `IntStream.sum()` trả `int` và `LongStream.sum()` trả `long`: cả hai đều có thể tràn khi tổng vượt miền biểu diễn. Ví dụ muốn cộng nhiều giá trị `int` với tổng lớn hơn `int`, hãy chuyển sang `long` **trước** khi tính:

~~~java
long safeSum = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum();

System.out.println(safeSum); // 5000050000
~~~

`asLongStream()` mở rộng từng giá trị `int` thành `long`; nó không làm `long` trở thành số nguyên vô hạn độ chính xác. Nếu tổng vẫn có thể vượt `long`, cần phương pháp và kiểu số khác (ví dụ `BigInteger`).

## 6. iterate: sinh phần tử tiếp theo từ phần tử trước

Khi muốn một **cấp số cộng có bước nhảy khác 1**, một **cấp số nhân** hoặc một chuỗi số mà phần tử tiếp theo phụ thuộc phần tử trước, dùng `iterate`.

Các overload hai tham số có từ **Java 8**:

~~~java
IntStream.iterate(int seed, IntUnaryOperator next)
LongStream.iterate(long seed, LongUnaryOperator next)
DoubleStream.iterate(double seed, DoubleUnaryOperator next)
~~~

`seed` là giá trị đầu tiên. Hàm `next` tính giá trị tiếp theo dựa trên giá trị trước đó. Dạng này mô tả **nguồn tuần tự, có thứ tự và có thể không giới hạn**: không có điều kiện dừng nội tại.

### 6.1. Cấp số cộng

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] evens = IntStream.iterate(0, n -> n + 2)
    .limit(6)
    .toArray();

System.out.println(Arrays.toString(evens)); // [0, 2, 4, 6, 8, 10]
~~~

Giá trị được sinh theo chuỗi:

~~~text
seed = 0
next(0) = 2
next(2) = 4
next(4) = 6
...
limit(6) -> chỉ lấy 6 giá trị
~~~

**`limit(6)` rất quan trọng**: nếu gọi `toArray()` trên một nguồn `iterate` không giới hạn mà không có phép giới hạn, pipeline sẽ không thể thu đủ dãy và có thể tiêu tốn tài nguyên cho đến khi gặp lỗi.

### 6.2. Cấp số nhân

~~~java
long[] powersOfTwo = LongStream.iterate(1L, n -> n * 2)
    .limit(6)
    .toArray();

System.out.println(java.util.Arrays.toString(powersOfTwo));
// [1, 2, 4, 8, 16, 32]
~~~

Ví dụ giới hạn sáu phần tử nên không xảy ra tràn số; nếu tiếp tục nhân mà không giới hạn, `long` cuối cùng có thể tràn.

### 6.3. iterate có điều kiện dừng (Java 9+)

Java 9 bổ sung overload ba tham số:

~~~java
IntStream.iterate(int seed, IntPredicate hasNext, IntUnaryOperator next)
LongStream.iterate(long seed, LongPredicate hasNext, LongUnaryOperator next)
DoubleStream.iterate(double seed, DoublePredicate hasNext, DoubleUnaryOperator next)
~~~

`hasNext` được kiểm tra đối với giá trị ứng viên để quyết định **có đưa giá trị đó vào Stream hay không**. Khi sai, Stream kết thúc, giá trị không được phát ra.

~~~java
int[] numbers = IntStream.iterate(
        3,               // seed
        n -> n <= 15,    // chỉ phát giá trị <= 15
        n -> n + 3       // phần tử kế tiếp
    )
    .toArray();

System.out.println(java.util.Arrays.toString(numbers));
// [3, 6, 9, 12, 15]
~~~

Khác biệt với `rangeClosed(3, 15)` là `iterate` trên có bước nhảy **3**, không phải bước nhảy 1. Nếu đã biết một khoảng số liên tục tăng từng đơn vị, `range` hoặc `rangeClosed` thường ngắn và rõ nghĩa hơn.

**Cảnh giác với điều kiện dừng và overflow:** nếu hàm `next` tràn số trước khi `hasNext` có thể chặn, giá trị tiếp theo có thể trở nên bất ngờ. Với dữ liệu gần giới hạn số nguyên, hãy chọn biểu thức chuyển bước có thể kiểm tra được hoặc kiểm soát tổng số phần tử trước bằng một khoảng chỉ số an toàn.

### 6.4. Vì sao không dùng DoubleStream.iterate để đếm bước chính xác?

~~~java
double[] fractions = DoubleStream.iterate(0.0, x -> x + 0.1)
    .limit(4)
    .toArray();
~~~

Dãy này biểu diễn các số `0.0, 0.1, 0.2, 0.3` theo logic, nhưng số thực nhị phân có thể tạo biểu diễn như `0.30000000000000004`. Nếu **số bước** phải xác định chính xác, nên tạo chỉ số nguyên trước, rồi ánh xạ:

~~~java
double[] values = IntStream.range(0, 4)
    .mapToDouble(i -> i / 10.0)
    .toArray();
~~~

Cách sau có đúng bốn bước và không tích lũy sai số qua phép cộng lặp, nhưng bản thân `double` **vẫn không thể biểu diễn chính xác mọi số thập phân**. Với tiền hoặc phép tính yêu cầu thập phân chính xác, cần quy ước đơn vị số nguyên hoặc `BigDecimal`.

## 7. generate: lấy từng giá trị từ Supplier

`generate` phù hợp khi giá trị được cung cấp bởi một **hàm nguồn** (*supplier*). Không có tham số phần tử trước như `iterate`:

~~~java
IntStream.generate(IntSupplier supplier)
LongStream.generate(LongSupplier supplier)
DoubleStream.generate(DoubleSupplier supplier)
~~~

Mỗi supplier trả về một giá trị nguyên thủy tương ứng thông qua `getAsInt()`, `getAsLong()` hoặc `getAsDouble()`.

### 7.1. Sinh một giá trị cố định

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] defaults = IntStream.generate(() -> -1)
    .limit(4)
    .toArray();

System.out.println(Arrays.toString(defaults)); // [-1, -1, -1, -1]
~~~

`generate(() -> -1)` tạo nguồn **không giới hạn**, nhưng `limit(4)` khiến pipeline chỉ thu bốn giá trị cần thiết.

Nguồn sinh bởi `generate` là **sequential, unordered** theo hợp đồng API. `unordered` ở đây không có nghĩa kết quả hiển thị luôn bị xáo ngẫu nhiên; nó có nghĩa API không hứa một *encounter order* để các phép toán về sau phải giữ.

### 7.2. Dữ liệu mô phỏng từ bộ sinh ngẫu nhiên

~~~java
import java.util.Random;

Random random = new Random(42L);

int[] diceRolls = IntStream.generate(() -> random.nextInt(6) + 1)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(diceRolls));
// Năm giá trị từ 1 đến 6 (có thể lặp).
~~~

`Random(42L)` sử dụng seed xác định, hữu ích khi muốn ví dụ hoặc kiểm thử có thể tái lập. Với yêu cầu sinh **mẫu ngẫu nhiên cố định số phần tử và khoảng giá trị**, `Random.ints(...)` trong mục tiếp theo thường ngắn hơn.

Vì `Random` chia sẻ trạng thái, **không nên tự động bật `parallel()` cho supplier dùng chung một đối tượng mutable** và kỳ vọng thứ tự/số lần gọi giống pipeline tuần tự. Với luồng song song, hãy chọn bộ sinh và kiến trúc an toàn cho nhiều luồng; đồng thời không sử dụng các bộ sinh ngẫu nhiên thông thường cho token bảo mật hoặc mật khẩu.

### 7.3. Phân biệt iterate và generate

| Đặc điểm | `iterate` | `generate` |
|---|---|---|
| Bắt đầu bằng | `seed` | `Supplier` |
| Giá trị kế tiếp | Hàm nhận giá trị trước đó | Supplier trả giá trị mới |
| Encounter order | Có thứ tự | Unordered |
| Nguồn mặc định | Có thể không giới hạn | Không giới hạn |
| Cách giới hạn | `limit` hoặc overload có `hasNext` | `limit`, `takeWhile` hoặc phép toán dừng sớm phù hợp |
| Thích hợp | Dãy toán học, quy tắc truy hồi | Giá trị mặc định, mô phỏng, nguồn cấp dữ liệu |

`takeWhile` (Java 9+) có thể cắt nguồn theo điều kiện, nhưng với nguồn **unordered**, tính chất chọn phần tử của nó khác với nguồn ordered. Khi cần “đếm đúng N giá trị”, `limit(N)` là lựa chọn rõ ràng hơn.

## 8. Sinh số ngẫu nhiên bằng các API nguồn chuyên dụng

`java.util.Random` cung cấp các phương thức tạo Stream nguyên thủy từ Java 8:

~~~java
Random.ints()
Random.ints(long streamSize)
Random.ints(long streamSize, int randomNumberOrigin, int randomNumberBound)

Random.longs(...)
Random.doubles(...)
~~~

Các overload tương ứng có thể sinh nguồn **không giới hạn** hoặc nguồn **hữu hạn theo `streamSize`**. Với overload nhận `origin` và `bound`, khoảng giá trị thường là **`[origin, bound)`**: lấy đầu dưới, loại đầu trên.

Ví dụ đầy đủ:

~~~java
import java.util.Arrays;
import java.util.Random;

public class RandomPrimitiveSources {
    public static void main(String[] args) {
        Random random = new Random(123L);

        // 6 lần gieo xúc xắc: mỗi số thuộc [1, 7), tức 1..6.
        int[] rolls = random.ints(6, 1, 7).toArray();

        // 3 giá trị double thuộc [0.0, 1.0).
        double[] samples = random.doubles(3, 0.0, 1.0).toArray();

        System.out.println(Arrays.toString(rolls));
        System.out.println(Arrays.toString(samples));
    }
}
~~~

Lời gọi `ints(6, 1, 7)` trả `IntStream` **6 phần tử**, và `doubles(3, 0.0, 1.0)` trả `DoubleStream` **3 phần tử**. Giá trị cụ thể phụ thuộc seed và trình tự lấy số; các phần tử có thể trùng nhau. Đây là sinh mẫu ngẫu nhiên, không bảo đảm “sáu giá trị khác nhau”.

Ngoài `Random`, Java có `SplittableRandom` với các phương thức `ints`, `longs` và `doubles`, được thiết kế để có khả năng chia các bộ sinh khi xây dựng thuật toán song song. Việc chọn bộ sinh nên dựa vào yêu cầu thống kê, khả năng tái lập, an toàn luồng và mức độ bảo mật; **`Random` và `SplittableRandom` không phải bộ sinh mật mã**.

## 9. Nguồn Stream và các phép biến đổi sang kiểu nguyên thủy

Không phải lúc nào dữ liệu cũng có sẵn dưới dạng `int[]` hay `double[]`. Đôi khi nguồn là `Stream<T>` chứa các đối tượng nghiệp vụ:

~~~java
import java.util.Arrays;
import java.util.List;

class Order {
    private final long amount;

    Order(long amount) {
        this.amount = amount;
    }

    long amount() {
        return amount;
    }
}

List<Order> orders = Arrays.asList(
    new Order(120_000L),
    new Order(80_000L),
    new Order(50_000L)
);

long total = orders.stream()
    .mapToLong(Order::amount)
    .sum();

System.out.println(total); // 250000
~~~

`mapToLong` chuyển một Stream đối tượng thành `LongStream`; `mapToInt` và `mapToDouble` cũng có vai trò tương ứng. Đây là **nguồn tiếp nối từ pipeline có sẵn**, không phải mảng/khoảng/bộ sinh ban đầu, nhưng là cách kết nối quan trọng khi học xử lý dữ liệu khai báo.

Nếu cần quay lại Stream đối tượng:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> boxed = IntStream.rangeClosed(1, 3)
    .boxed()
    .collect(Collectors.toList());

System.out.println(boxed); // [1, 2, 3]
~~~

`boxed()` chuyển `IntStream` thành `Stream<Integer>`; tương tự với `long` và `double`. Boxing có thể tốn thêm bộ nhớ và chi phí cấp phát; hãy giữ Stream nguyên thủy khi mục đích chỉ là tính toán số.

## 10. Lazy evaluation, giới hạn và vòng đời nguồn

Tạo nguồn **không có nghĩa mọi phần tử đã được tính**. Các thao tác trung gian thường *lazy*, và phép toán kết thúc mới yêu cầu dữ liệu cần thiết:

~~~java
import java.util.stream.IntStream;

IntStream pipeline = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 5 == 0)
    .limit(3);

System.out.println("Đã khai báo pipeline");

int[] result = pipeline.toArray();
System.out.println(java.util.Arrays.toString(result));
~~~

Kết quả:

~~~text
Đã khai báo pipeline
[5, 10, 15]
~~~

Pipeline được mô tả trước; `toArray()` mới kích hoạt việc tính ra ba số chia hết cho 5.

### 10.1. Chọn điểm đặt limit cẩn thận

~~~java
int[] a = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .toArray(); // [2, 4, 6]

int[] b = IntStream.iterate(1, n -> n + 1)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .toArray(); // [2]
~~~

Cả hai đều kết thúc, nhưng **`filter → limit`** lấy ba kết quả thỏa điều kiện, còn **`limit → filter`** chỉ xét ba phần tử đầu nguồn rồi lọc.

### 10.2. Một số pipeline không thể hoàn thành

Những ví dụ dưới đây **không nên chạy** nếu không có cơ chế dừng hoặc giới hạn tài nguyên:

~~~java
// Nguồn vô hạn, terminal muốn đếm mọi phần tử:
// IntStream.generate(() -> 1).count();

// Sắp xếp toàn bộ nguồn vô hạn trước khi lấy vài phần tử:
// IntStream.iterate(0, n -> n + 1)
//     .sorted()
//     .limit(5)
//     .toArray();
~~~

`limit(5)` **đặt sau** `sorted()` không cứu được trường hợp nguồn vô hạn: `sorted` cần xét đủ nguồn trước khi có thể trả kết quả sắp xếp. Với nguồn không giới hạn, hãy xác định phép toán trung gian có trạng thái và vị trí cắt nguồn thật cẩn thận.

### 10.3. Không tái sử dụng Stream đã tiêu thụ

~~~java
IntStream stream = IntStream.rangeClosed(1, 5);
int sum = stream.sum(); // 15

// Sai: dùng lại cùng đối tượng Stream đã kết thúc.
// long count = stream.count();

// Đúng: tạo Stream mới từ nguồn có thể tạo lại.
long count = IntStream.rangeClosed(1, 5).count(); // 5
~~~

Một Stream chỉ dùng cho một pipeline kết thúc. Nếu muốn đọc nhiều lần từ mảng, hãy tạo nhiều Stream từ mảng; nếu nguồn do bộ sinh có trạng thái, mỗi lần tạo lại có thể sinh **dữ liệu khác**. Khi yêu cầu so sánh cùng dữ liệu, phải quản lý snapshot hoặc seed/chiến lược tạo dữ liệu phù hợp.

## 11. Hiệu năng, trạng thái và xử lý song song

Stream nguyên thủy thường giảm boxing, nhưng **không tự bảo đảm nhanh hơn vòng lặp**. Thời gian và bộ nhớ còn phụ thuộc cách tạo nguồn, số phần tử, phép toán, khả năng dừng sớm và thực tế triển khai JDK.

### 11.1. Nguồn hữu hạn và nguồn không giới hạn

- `Arrays.stream(array)` duyệt mảng đã có; chi phí lưu dữ liệu chính đã tồn tại trong mảng.
- `range` và `rangeClosed` biểu diễn dãy toán học, không cần tạo trước mảng chứa mọi số.
- `iterate` sinh giá trị từ giá trị trước; khi cần tính theo phụ thuộc tuần tự, mức độ song song hóa có thể bị giới hạn.
- `generate` lấy dữ liệu từ supplier; nếu supplier lưu trạng thái mutable hoặc dùng tài nguyên bên ngoài, phải kiểm soát tính đúng đắn và khả năng dừng.

Không nên thu một nguồn rất lớn thành `toArray()` chỉ để đếm hoặc tính tổng: `count()` hay `sum()` thường rõ mục đích và không cần lưu toàn bộ kết quả. Dù vậy, `sum()` vẫn có giới hạn tràn số và phép tính dấu phẩy động có sai số.

### 11.2. Tác dụng phụ trong supplier và mapper

Với Stream, không nên dựa vào việc supplier hoặc lambda trung gian được gọi **chính xác bao nhiêu lần**, **theo thứ tự nào**, hay **trên luồng nào** nếu không có hợp đồng bảo đảm điều đó.

Ví dụ sau có rủi ro nếu dùng như bộ phát mã ID nghiệp vụ:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger();

int[] ids = IntStream.generate(counter::incrementAndGet)
    .parallel()
    .limit(10)
    .toArray();
~~~

Dù `AtomicInteger` giúp tăng biến an toàn theo nguyên tắc atomic, dùng bộ đếm chia sẻ trong nguồn unordered song song vẫn khiến nội dung và thứ tự kết quả khó dự đoán. Khi cần chính xác `1..10`, **`IntStream.rangeClosed(1, 10)`** biểu diễn yêu cầu trực tiếp và dễ kiểm tra hơn.

### 11.3. Khi nào cân nhắc parallel?

`IntStream.range(...)` và `LongStream.range(...)` thường thuận lợi cho chia nhỏ nguồn vì biết ranh giới. Tuy nhiên, việc bật `parallel()` có chi phí lập lịch, phối hợp và kết hợp kết quả. Chỉ cân nhắc khi phép toán đủ lớn, ít tác dụng phụ, có thể phân chia độc lập và đã đo được lợi ích.

Với một bộ sinh ngẫu nhiên hoặc nguồn I/O, không nên suy luận rằng bật parallel luôn tăng thông lượng. Nếu công việc phụ thuộc vào thứ tự hoặc trạng thái nguồn, cách xử lý có thể phải thay đổi về thiết kế trước khi có lợi ích hiệu năng.

## 12. Ví dụ ứng dụng hoàn chỉnh: phân tích dữ liệu đo cảm biến

Giả sử ứng dụng nhận mảng nhiệt độ từ một cảm biến, cần tính trung bình, lọc các giá trị vượt ngưỡng và sinh một dãy chỉ số đọc mẫu. Ta sử dụng ba cách tạo nguồn: mảng, khoảng số, và bộ sinh mô phỏng.

**Ví dụ Java 17+** (mã dùng các API Stream đã có từ Java 8):

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;

public class PrimitiveStreamSourcesDemo {
    public static void main(String[] args) {
        double[] temperatures = {21.5, 23.0, 19.5, 25.0, 22.0};

        // 1. Từ mảng: tính trung bình, có xử lý trường hợp rỗng.
        double average = Arrays.stream(temperatures)
            .average()
            .orElse(Double.NaN);

        // 2. Từ mảng: lọc các số đo từ 23 độ C trở lên.
        double[] hotReadings = Arrays.stream(temperatures)
            .filter(t -> t >= 23.0)
            .toArray();

        // 3. Từ khoảng số: mỗi phần tử tương ứng một chỉ số mảng.
        String[] labels = IntStream.range(0, temperatures.length)
            .mapToObj(i -> "Lần " + (i + 1) + ": " + temperatures[i])
            .toArray(String[]::new);

        // 4. Từ bộ sinh: tạo 3 giá trị mặc định phục vụ minh họa.
        double[] defaults = DoubleStream.generate(() -> 20.0)
            .limit(3)
            .toArray();

        System.out.printf(Locale.ROOT, "Trung bình: %.2f%n", average);
        System.out.println("Vượt ngưỡng: " + Arrays.toString(hotReadings));
        System.out.println("Nhãn: " + Arrays.toString(labels));
        System.out.println("Mặc định: " + Arrays.toString(defaults));
    }
}
~~~

Kết quả:

~~~text
Trung bình: 22.20
Vượt ngưỡng: [23.0, 25.0]
Nhãn: [Lần 1: 21.5, Lần 2: 23.0, Lần 3: 19.5, Lần 4: 25.0, Lần 5: 22.0]
Mặc định: [20.0, 20.0, 20.0]
~~~

Cùng một bộ dữ liệu được sử dụng qua **ba pipeline riêng** tạo từ `Arrays.stream(temperatures)` và `IntStream.range(...)`, còn `DoubleStream.generate(...)` là nguồn mô phỏng độc lập. Không tái sử dụng một Stream sau khi đã gọi terminal operation.

Trong xử lý cảm biến thật, phải xác định liệu các giá trị `NaN`, vô cực, dữ liệu thiếu hoặc ngoại lệ I/O có được chấp nhận không; không nên coi `Double.NaN` là giá trị nhiệt độ hợp lệ nếu nghiệp vụ yêu cầu dữ liệu sạch.

## 13. Bài tập thực hành và lời giải

**Bài 1 — Từ mảng:** Cho `int[] numbers = {3, 5, 7, 9, 11};`. Hãy lấy ba phần tử ở vị trí 1, 2, 3 và tính tổng.

~~~java
int[] numbers = {3, 5, 7, 9, 11};

int sum = java.util.Arrays.stream(numbers, 1, 4)
    .sum();

System.out.println(sum); // 5 + 7 + 9 = 21
~~~

**Bài 2 — Từ khoảng số:** Tạo các số chẵn từ 2 đến 12, kể cả 12. Có thể dùng `rangeClosed` kết hợp `filter`:

~~~java
int[] evens = IntStream.rangeClosed(2, 12)
    .filter(n -> n % 2 == 0)
    .toArray();

System.out.println(java.util.Arrays.toString(evens));
// [2, 4, 6, 8, 10, 12]
~~~

**Bài 3 — Từ iterate:** Tạo năm lũy thừa của 3 bắt đầu bằng 1:

~~~java
int[] powers = IntStream.iterate(1, n -> n * 3)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(powers));
// [1, 3, 9, 27, 81]
~~~

**Bài 4 — Từ generate:** Tạo bốn giá trị `2.5`:

~~~java
double[] values = DoubleStream.generate(() -> 2.5)
    .limit(4)
    .toArray();

System.out.println(java.util.Arrays.toString(values));
// [2.5, 2.5, 2.5, 2.5]
~~~

**Câu hỏi tự kiểm tra:**

1. `Arrays.stream(new int[] {1, 2}).count()` trả bao nhiêu? — **2**.
2. `Stream.of(new int[] {1, 2}).count()` trả bao nhiêu? — **1** vì phần tử là một `int[]`.
3. `IntStream.range(2, 5)` và `rangeClosed(2, 5)` khác nhau ở đâu? — Trường hợp đầu **loại 5**, trường hợp sau **giữ 5**.
4. Có `DoubleStream.range(0, 10)` không? — **Không** trong Java Stream API chuẩn.
5. `IntStream.iterate(1, n -> n * 2)` có tự kết thúc không? — **Không**, dạng này cần giới hạn phù hợp.
6. `IntStream.generate(() -> 3).limit(4)` sinh mấy số? — **4**, đều là số 3.
7. `average()` trên Stream nguyên thủy rỗng trả gì? — Một **`OptionalDouble` rỗng**.
8. `IntStream.rangeClosed(1, 100_000).sum()` có đáng tin cậy để tính tổng chính xác không? — **Không**, tổng vượt khả năng biểu diễn của `int`; hãy cân nhắc `asLongStream().sum()`.

## 14. Ghi nhớ và lựa chọn nguồn

Hãy chọn nguồn theo **bản chất của dữ liệu cần tạo**:

- **Có sẵn dữ liệu trong mảng:** `Arrays.stream(int[]/long[]/double[])` hoặc `IntStream.of(array)`.
- **Có một vài giá trị cố định:** `of(...)`; không có giá trị thì `empty()`.
- **Có khoảng số nguyên liên tiếp:** `IntStream.range`, `rangeClosed` hoặc phiên bản `LongStream`.
- **Có quy tắc từ phần tử trước:** `iterate(seed, next)`; nếu cần điều kiện dừng, dùng overload ba tham số từ Java 9.
- **Có nguồn cung cấp từng giá trị độc lập:** `generate(supplier)`; với số ngẫu nhiên, cân nhắc `Random.ints/longs/doubles` và overload hữu hạn.

Dù nguồn nào, bạn vẫn cần quyết định **điều kiện kết thúc**, **kiểu số và nguy cơ tràn**, **trạng thái/tác dụng phụ của lambda**, và **chi phí của terminal operation**. Nắm được các yếu tố này sẽ giúp kết hợp đúng các phép toán `filter`, `map`, `reduce`, `collect`, rồi tiến đến grouping, collector tùy chỉnh, `Spliterator`, parallel Stream và Stream Gatherers một cách có kiểm soát.
