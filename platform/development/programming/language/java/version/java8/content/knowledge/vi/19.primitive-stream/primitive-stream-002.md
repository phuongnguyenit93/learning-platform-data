# Boxing, unboxing và chi phí xử lý số trong Primitive Stream (Java 8)

> **Phạm vi:** `IntStream`, `LongStream`, `DoubleStream` và cách chuyển đổi với `Stream<Integer>`, `Stream<Long>`, `Stream<Double>`. Đây là API được giới thiệu từ Java 8 và **vẫn còn áp dụng trên Java hiện đại**. Trọng tâm là hiểu chính xác việc boxing/unboxing, ảnh hưởng tới bộ nhớ và phép tính số, cùng cách kiểm chứng hiệu năng đúng phương pháp. Các đoạn mã Java sử dụng API tương thích Java 8, chạy với JDK 17+.

## 1. Cần phân biệt: giá trị nguyên thủy và đối tượng bao

Trong Java, `int` là **kiểu nguyên thủy** (primitive), còn `Integer` là **kiểu tham chiếu** (wrapper). Tương tự với `long/Long` và `double/Double`.

- **Boxing:** chuyển một giá trị nguyên thủy sang wrapper, ví dụ `int` → `Integer`.
- **Unboxing:** lấy giá trị nguyên thủy từ wrapper, ví dụ `Integer` → `int`.
- **Autoboxing / auto-unboxing:** trình biên dịch tự chèn các phép chuyển đổi phù hợp vào biểu thức và lời gọi hàm; điều đó không bảo đảm chi phí bằng 0 khi chạy.

```java
int primitive = 42;
Integer wrapped = primitive; // Autoboxing: tương đương Integer.valueOf(primitive)
int again = wrapped;         // Unboxing: tương đương wrapped.intValue()

Integer missing = null;
// int broken = missing;      // Ném NullPointerException nếu thực thi.
```

Nhìn bề ngoài các biến đều chứa “42”, nhưng mô hình khác nhau:

| Thuộc tính | `int` | `Integer` |
| --- | --- | --- |
| Bản chất | Giá trị nguyên thủy 32-bit có dấu | Đối tượng/tham chiếu kiểu wrapper |
| Có thể nhận `null`? | Không | Có |
| Thao tác số học | Trực tiếp trên kiểu nguyên thủy | Thường cần unbox để thực hiện phép tính |
| Dùng trong generic `List<T>` / `Stream<T>` | Không thể dùng trực tiếp `T=int` | Dùng `Integer` |
| Nơi lưu trữ | Phụ thuộc vị trí biến và tối ưu JVM | Có tham chiếu; đối tượng có thể được tạo/giữ tùy ngữ cảnh |

**Không suy luận rằng mỗi lần autoboxing chắc chắn cấp phát một đối tượng mới.** Wrapper có thể được cache, và JVM hiện đại có thể tối ưu một số allocation qua escape analysis/scalar replacement. Chi phí thực tế tùy mã, dữ liệu và cấu hình runtime. Tuy nhiên, dữ liệu dạng `List<Integer>` vẫn là một collection **các tham chiếu tới `Integer`**, khác với `int[]` chứa các `int`.

### Autoboxing xuất hiện ở đâu trong Stream?

```java
Stream<Integer> boxedStream = Stream.of(1, 2, 3);
// Stream<T> yêu cầu T là reference type, nên các int trở thành Integer.

int total = boxedStream
        .mapToInt(Integer::intValue)
        .sum(); // 6
```

`Stream<Integer>` xử lý các phần tử tham chiếu kiểu `Integer`. Phép `mapToInt(Integer::intValue)` chuyển lại các phần tử sang `int`; nếu nguồn đã là danh sách wrapper, ta không “xóa” được chi phí lưu trữ wrapper trước đó chỉ bằng cách unbox trong một bước sau.

## 2. Vì sao Java có `IntStream`, `LongStream` và `DoubleStream`?

`Stream<T>` dùng generics, mà generics Java không nhận kiểu nguyên thủy `int`, `long`, `double` làm đối số kiểu trực tiếp. Java cung cấp ba **primitive specialization** của Stream:

| Primitive stream | Kiểu phần tử | Một số terminal operation đặc trưng |
| --- | --- | --- |
| `IntStream` | `int` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `LongStream` | `long` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `DoubleStream` | `double` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |

Các pipeline này dùng primitive-specialized functional interface như `IntPredicate`, `IntUnaryOperator`, `IntConsumer`, `ToIntFunction<T>` thay vì yêu cầu `Integer` tại mỗi bước.

Ví dụ so sánh cùng một phép tổng:

```java
// Xử lý kiểu wrapper; reduce có thể kéo theo chuyển đổi wrapper/primitive.
int boxedTotal = Stream.of(1, 2, 3, 4, 5)
        .reduce(0, Integer::sum);

// Pipeline primitive giữ kiểu int từ nguồn đến terminal.
int primitiveTotal = IntStream.of(1, 2, 3, 4, 5)
        .sum();
// Cả hai đều có kết quả 15.
```

Với nhu cầu xử lý hàng loạt số, `IntStream` có thể tránh các thao tác boxing ở nhiều điểm trên pipeline. Đây là lý do thiết kế đáng cân nhắc, **không phải bảo đảm mọi chương trình dùng `IntStream` đều nhanh hơn** một vòng `for` hay một pipeline boxed trong mọi điều kiện.

**Lưu ý loại số:** Java Stream API không có `FloatStream`, `ByteStream`, `ShortStream` hoặc `CharStream` chuyên biệt. Với `byte`, `short`, `char`, nhiều phép tính có thể mở rộng lên `int` và xử lý bằng `IntStream`. Chuyển đổi cần xét quy tắc dấu/độ rộng và ý nghĩa dữ liệu.

## 3. Các cổng chuyển đổi quan trọng trong pipeline

### 3.1. Tạo primitive stream từ nguồn primitive

```java
int[] values = {1, 2, 3, 4, 5};

IntStream byArray = Arrays.stream(values);
IntStream byOf = IntStream.of(1, 2, 3, 4, 5);
IntStream byRange = IntStream.range(1, 6);          // 1..5, loại trừ 6
IntStream byClosed = IntStream.rangeClosed(1, 5);  // 1..5, gồm cả 5
```

Các dòng trên minh họa **bốn cách tạo stream riêng**; mỗi stream dùng một lần để chạy terminal. `Arrays.stream(int[])` và `IntStream.of(int...)` cho `IntStream` trực tiếp. `range` phù hợp cho dãy số/giá trị chỉ số; tránh tạo `List<Integer>` chỉ để có các số liên tiếp.

Một bẫy về kiểu:

```java
long one = Stream.of(values).count();     // 1: Stream<int[]> chứa một mảng.
long five = Arrays.stream(values).count(); // 5: IntStream chứa năm int.
```

`Stream.of(int[])` **không phải** là cách trải mảng `int[]` thành `Stream<Integer>`. Nếu cần đi từ mảng sang wrapper stream, dùng `Arrays.stream(values).boxed()`.

### 3.2. `boxed()`: primitive → wrapper stream

```java
IntStream ints = IntStream.rangeClosed(1, 3);
Stream<Integer> objects = ints.boxed(); // Stream<Integer>: 1, 2, 3
```

`boxed()` cũng tồn tại trên `LongStream` và `DoubleStream`, cho `Stream<Long>` và `Stream<Double>` tương ứng. Hãy đặt `boxed()` gần **ranh giới thật sự cần object**, chẳng hạn giao API `List<Integer>`, dùng collector cho kiểu reference hoặc gộp với nguồn object.

```java
List<Integer> ids = IntStream.rangeClosed(1, 3)
        .boxed()
        .collect(Collectors.toList());
// ids = [1, 2, 3] (Collectors.toList là API Java 8)
```

Chú ý: `boxed()` không bảo đảm tạo mới một object cho mỗi giá trị; runtime có thể dùng cache hoặc tối ưu. Điều có thể khẳng định từ kiểu là sau phép gọi này pipeline có dạng `Stream<Integer>`, và API phía sau xử lý kiểu tham chiếu.

### 3.3. `mapToInt`, `mapToLong`, `mapToDouble`: object → primitive

```java
List<Integer> ids = Arrays.asList(1, 2, 3);
int total = ids.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 6

List<String> names = Arrays.asList("Java", "Stream", "API");
int lengthSum = names.stream()
        .mapToInt(String::length)
        .sum(); // 4 + 6 + 3 = 13
```

Trường hợp `names` đáng chú ý: nguồn là object `String` nhưng **kết quả mapper là `int`**; ta có thể duy trì pipeline primitive từ phép biến đổi đó cho tới terminal, không phải tạo `Integer` trung gian.

Chọn hàm tạo kiểu rộng đủ lớn nếu kết quả có thể vượt giới hạn `int`:

```java
long totalLength = names.stream()
        .mapToLong(String::length)
        .sum();
```

### 3.4. `mapToObj`: primitive → object không nhất thiết qua wrapper

```java
List<String> labels = IntStream.range(1, 4)
        .mapToObj(n -> "item-" + n)
        .collect(Collectors.toList());
// [item-1, item-2, item-3]
```

`mapToObj` gọi `IntFunction<? extends U>` để tạo object kiểu `U`. Đây là chuyển đổi **có chủ đích sang kiểu object cần thiết**; ở ví dụ này `U=String` nên không phải “box `int` thành `Integer` rồi mới tạo `String`” theo hợp đồng API.

### 3.5. Mở rộng primitive trước khi cộng

```java
long total = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2_147_483_648L
```

`asLongStream()` chuyển từng `int` sang `long` trên pipeline; nó phù hợp để tránh tràn tổng 32-bit khi kết quả nằm trong phạm vi `long`. Phải mở rộng **trước** terminal `sum()`: nếu `IntStream.sum()` đã tràn thì gán kết quả sau đó vào `long` không khôi phục được giá trị đúng.

## 4. Ví dụ hoàn chỉnh: thấy rõ các phép chuyển đổi và kết quả số

Chương trình có các nhánh tách biệt: tổng primitive, boxing thành List, unboxing lại khi cộng, tính bình phương/thống kê, xử lý `null`, mở rộng `int` thành `long` và cảnh báo nguồn kiểu mảng.

Lưu nguyên vẹn vào tệp **`PrimitiveBoxingDemo.java`**:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PrimitiveBoxingDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3, 4, 5};

        // Giữ pipeline primitive và mở rộng sang long khi cộng.
        long sumPrimitive = Arrays.stream(raw).asLongStream().sum();

        // Chỉ chuyển sang Integer khi cần một List<Integer>.
        List<Integer> boxed = Arrays.stream(raw)
                .boxed()
                .collect(Collectors.toList());

        // Nguồn đã là List<Integer>; cần unbox khi tính số học.
        long sumAfterUnboxing = boxed.stream()
                .mapToInt(Integer::intValue)
                .asLongStream()
                .sum();

        int sumOfSquares = IntStream.rangeClosed(1, 5)
                .map(n -> n * n)
                .sum();

        OptionalDouble average = Arrays.stream(raw).average();
        IntSummaryStatistics stats = Arrays.stream(raw).summaryStatistics();

        // Cùng dữ liệu, khác độ rộng của phép cộng.
        int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();

        // Unbox null sẽ NPE; lọc null trước khi mapToInt.
        List<Integer> nullable = Arrays.asList(7, null, 9);
        int withoutNull = nullable.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();

        // Một int[] là một phần tử trong Stream<int[]>.
        long arrayAsSingleObject = Stream.of(raw).count();
        long arrayAsPrimitiveElements = Arrays.stream(raw).count();

        // Chuyển sang object ở đúng nơi thật sự cần String.
        List<String> labels = IntStream.range(1, 4)
                .mapToObj(n -> "item-" + n)
                .collect(Collectors.toList());

        System.out.println("Primitive sum: " + sumPrimitive);
        System.out.println("Boxed list: " + boxed);
        System.out.println("Unboxed sum: " + sumAfterUnboxing);
        System.out.println("Squares sum: " + sumOfSquares);
        System.out.println("Average: " + average.orElse(Double.NaN));
        System.out.println("Statistics: count=" + stats.getCount()
                + ", sum=" + stats.getSum()
                + ", min=" + stats.getMin()
                + ", max=" + stats.getMax());
        System.out.println("Int overflow sum: " + overflowed);
        System.out.println("Long sum: " + widened);
        System.out.println("Non-null sum: " + withoutNull);
        System.out.println("Stream.of(int[]) count: " + arrayAsSingleObject);
        System.out.println("Arrays.stream(int[]) count: " + arrayAsPrimitiveElements);
        System.out.println("Labels: " + labels);

        if (sumPrimitive != 15 || sumAfterUnboxing != 15
                || !boxed.equals(Arrays.asList(1, 2, 3, 4, 5))
                || sumOfSquares != 55
                || average.orElse(Double.NaN) != 3.0
                || stats.getCount() != 5 || stats.getSum() != 15
                || stats.getMin() != 1 || stats.getMax() != 5
                || overflowed != Integer.MIN_VALUE
                || widened != 2147483648L || withoutNull != 16
                || arrayAsSingleObject != 1 || arrayAsPrimitiveElements != 5
                || !labels.equals(Arrays.asList("item-1", "item-2", "item-3"))) {
            throw new AssertionError("Unexpected result");
        }
        System.out.println("Checks passed.");
    }
}
```

Chạy bằng JDK 17+; cờ `--release 8` xác nhận mã chỉ dùng cú pháp/API phù hợp Java 8:

```bash
javac --release 8 PrimitiveBoxingDemo.java
java PrimitiveBoxingDemo
```

**Stdout của ví dụ (đã chạy trên OpenJDK 24):**

```text
Primitive sum: 15
Boxed list: [1, 2, 3, 4, 5]
Unboxed sum: 15
Squares sum: 55
Average: 3.0
Statistics: count=5, sum=15, min=1, max=5
Int overflow sum: -2147483648
Long sum: 2147483648
Non-null sum: 16
Stream.of(int[]) count: 1
Arrays.stream(int[]) count: 5
Labels: [item-1, item-2, item-3]
Checks passed.
```

**Cách đọc kết quả:**

- `sumPrimitive` và `sumAfterUnboxing` đều là **15**: boxing/unboxing không tự làm thay đổi kết quả số nguyên của những phép tính hợp lệ; sự khác biệt là kiểu dữ liệu và các chi phí *có thể* phát sinh.
- `boxed` thực sự có kiểu `List<Integer>`; còn `raw` là `int[]`.
- `average` trả `OptionalDouble` vì nguồn rỗng không có trung bình; `summaryStatistics` cho `count/sum/min/max` bằng **5/15/1/5**.
- `overflowed` thành **-2147483648** do cộng trong `int` bị tràn; `widened` thành **2147483648** vì chuyển sang `LongStream` trước khi cộng.
- `withoutNull` trả **16** sau khi bỏ `null`; nếu gọi `Integer::intValue` trên `null` sẽ ném `NullPointerException`.
- `arrayAsSingleObject` là **1** vì `Stream.of(raw)` có một phần tử kiểu `int[]`; `arrayAsPrimitiveElements` là **5** vì `Arrays.stream(raw)` trải năm số nguyên.

Chương trình cố ý dùng các stream **mới** cho từng phép tính; Stream đã chạy terminal (`sum`, `collect`, `count`, v.v.) không được tái sử dụng.

## 5. Chi phí xử lý số đến từ đâu?

### 5.1. Chi phí boxing

Với nguồn có nhiều giá trị `int`, pipeline tạo wrapper có thể cần biểu diễn mỗi giá trị bằng `Integer` thay vì primitive. Tùy trường hợp, chi phí có thể gồm:

1. **Tạo/giữ object:** một số wrapper cần được cấp phát; GC có thể phải quản lý những object còn sống.
2. **Vùng nhớ và tham chiếu:** `List<Integer>` thường có mảng tham chiếu cùng các object wrapper; `int[]` lưu trực tiếp các `int` liên tiếp trong mảng, nên có thể tiết kiệm bộ nhớ và tăng tính cục bộ dữ liệu.
3. **Truy cập gián tiếp:** đọc một phần tử `Integer` thường cần lấy tham chiếu rồi đọc giá trị; với `int[]` có thể truy cập primitive tại vị trí tương ứng.
4. **Unboxing và kiểm tra null:** khi API chờ `int`, giá trị wrapper phải được chuyển; nếu là `null` sẽ lỗi.

Đây là **các nguồn chi phí có thể phát sinh**, không phải công thức “mỗi boxing = một allocation + một cache miss”. JVM có cache và các tối ưu hóa khác nhau. Kết quả phụ thuộc dữ liệu, cách dùng wrapper, hot path, phiên bản JDK/JIT và môi trường đo.

### 5.2. Chi phí lambda/Stream cũng cần được tính

Một pipeline `IntStream` không có boxing do `Stream<Integer>` gây ra ở mỗi phần tử, nhưng vẫn có chi phí xây pipeline, dispatch, traversal và thao tác trung gian. HotSpot có thể inline/fuse nhiều bước, nhưng mức độ tối ưu hóa không được API đảm bảo.

Với số phần tử ít, một vòng `for` đơn giản có thể cạnh tranh hoặc nhanh hơn pipeline Stream. Với khối lượng lớn, pipeline primitive đôi khi có ưu thế rõ rệt trước boxed pipeline; tuy vậy **không có thứ tự hiệu năng tuyệt đối** chỉ dựa trên tên API.

### 5.3. Khi boxing là điều hợp lý

Không nên “né wrapper bằng mọi giá”. `Integer` vẫn cần thiết hoặc tự nhiên trong các tình huống:

- API/collection công khai nhận `List<Integer>`, `Map<Integer, ...>` hay `Stream<Integer>`;
- Kết quả cần phân biệt **không có giá trị** bằng `null` ở boundary đã định nghĩa (cẩn thận xử lý null);
- Đầu ra cần đối tượng có hành vi/generic API phù hợp;
- Chi phí xử lý nghiệp vụ khác áp đảo chi phí chuyển đổi, và phép đo cho thấy tối ưu hóa không đáng kể.

Cách thiết kế thường hợp lý là **giữ số ở primitive càng lâu càng đúng với ý nghĩa tính toán, rồi boxing khi đi vào API cần object**; tránh liên tục `boxed().mapToInt(...).boxed()` không có lý do.

## 6. Những vấn đề đúng sai còn quan trọng hơn tốc độ

### 6.1. Null khi unboxing

```java
List<Integer> numbers = Arrays.asList(5, null, 7);

// Sai khi có null:
// int total = numbers.stream().mapToInt(Integer::intValue).sum();

int total = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
// total == 12
```

Bỏ `null` là **quyết định nghiệp vụ**, không phải mặc định bắt buộc: có nơi phải báo lỗi dữ liệu, có nơi phải thay giá trị bằng 0, có nơi cần thống kê riêng số giá trị thiếu. Đừng âm thầm lọc null nếu điều đó làm sai nghĩa kết quả.

### 6.2. Tràn số nguyên xảy ra cả với primitive stream

```java
int wrong = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 do tràn 32-bit.

long correctForTheseInputs = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648
```

`IntStream.sum()` trả `int`, còn `LongStream.sum()` trả `long`. `IntSummaryStatistics.getSum()` trả `long`, tuy nhiên `long` cũng có giới hạn và không bảo đảm tránh mọi trường hợp tràn. Nếu cần phép cộng **báo lỗi khi tràn**, cân nhắc `Math.addExact` trên `long`; với tổng lớn hơn `long`, cân nhắc `BigInteger` hoặc mô hình dữ liệu khác.

**Phân biệt:** cast sau phép tính `(long) intSum` không sửa được kết quả `intSum` đã tràn. Cần cast/mở rộng **trước khi phép cộng xảy ra**.

### 6.3. Số thực và độ chính xác

`DoubleStream` giúp tránh boxing giữa các bước số thực, nhưng vẫn dùng quy tắc dấu phẩy động `double`:

- Không thể biểu diễn chính xác mọi phân số thập phân ở dạng nhị phân.
- Phép cộng số thực có thể cho kết quả khác khi đổi cách nhóm/thứ tự do làm tròn; các quy luật toán học trên số thực lý tưởng không luôn giữ ở mức bit.
- Không dùng `double` để lưu và cộng tiền tệ cần độ chính xác thập phân tuyệt đối; chọn mô hình đơn vị nhỏ nhất dạng số nguyên hoặc `BigDecimal`, có chính sách làm tròn rõ ràng.

Primitive stream tối ưu kiểu dữ liệu số, **không thay đổi các giới hạn toán học của `int/long/double`**.

### 6.4. Stream rỗng và kiểu Optional chuyên biệt

`IntStream.min()` / `max()` trả `OptionalInt`; `IntStream.average()` trả `OptionalDouble`. Khác với `Optional<Integer>` và `Optional<Double>`, các wrapper tùy chọn chuyên biệt có thể chứa giá trị primitive trực tiếp theo API.

```java
OptionalDouble avg = IntStream.empty().average();
if (avg.isPresent()) {
    System.out.println(avg.getAsDouble());
} else {
    System.out.println("Không có phần tử để tính trung bình");
}
```

Không gọi `getAsInt()` hoặc `getAsDouble()` khi optional rỗng. `sum()` của stream rỗng là 0 theo identity phép cộng, nhưng điều đó **không đồng nghĩa** rằng dữ liệu đã có một phần tử bằng 0.

## 7. Cách chọn pipeline thực tế

### Trường hợp A — nguồn là `int[]` và cần tính toán số

```java
int[] samples = {2, 4, 6, 8};

long total = Arrays.stream(samples)
        .filter(n -> n > 2)
        .asLongStream()
        .sum(); // 18
```

Giữ pipeline primitive, không cần boxing thành `Integer`.

### Trường hợp B — nguồn là `List<Integer>`

```java
List<Integer> samples = Arrays.asList(2, 4, 6, 8);

long total = samples.stream()
        .mapToLong(Integer::longValue)
        .sum(); // 20
```

Nguồn đã có wrapper. `mapToLong` chuyển trực tiếp sang primitive `long` để tiếp tục tính; không tạo thêm `List<Long>` trung gian. Đoạn này giả định các phần tử khác `null`.

### Trường hợp C — nguồn là object, cần tính trường số

```java
List<String> labels = Arrays.asList("one", "two", "three");

long totalChars = labels.stream()
        .mapToLong(String::length)
        .sum(); // 3 + 3 + 5 = 11
```

`String` vốn là object; không cần bắt nguồn bằng `IntStream`, chỉ chuyển sang primitive khi phép biến đổi xuất ra số.

### Trường hợp D — cần nhóm, sắp xếp/thu thập object

```java
Map<Integer, Long> frequencies = IntStream.of(1, 2, 2, 3)
        .boxed()
        .collect(Collectors.groupingBy(
                Integer::intValue,
                Collectors.counting()));
// {1=1, 2=2, 3=1}; thứ tự Map không cam kết.
```

Ở biên giới `Map<Integer,Long>`, kiểu khóa và kiểu giá trị bắt buộc là object trong Java generics. Boxing tại điểm này có lý do; nếu bài toán chỉ cần tổng, tránh tạo Map không cần thiết.

### Trường hợp E — tránh một vòng boxing rồi unboxing

```java
// Vòng chuyển đổi thừa khi chỉ cần tổng:
int wasteful = IntStream.range(1, 1000)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();

// Giữ primitive:
int betterShape = IntStream.range(1, 1000).sum();
// Cả hai cho 499500.
```

Đặt tên `betterShape` nói về **cấu trúc API hợp lý hơn**, không khẳng định tốc độ đo được. JVM có thể tối ưu round-trip boxed/unboxed trong một số bối cảnh, nhưng viết kiểu primitive xuyên suốt khiến ý đồ và giới hạn kiểu rõ ràng.

## 8. Đo chi phí boxing đúng cách với JMH

Nếu câu hỏi là “`IntStream` hay `Stream<Integer>` nhanh hơn bao nhiêu?” thì **chỉ nhìn source code chưa đủ**. Dùng **JMH (Java Microbenchmark Harness)** của OpenJDK để thiết kế benchmark có kiểm soát.

Một thí nghiệm có giá trị nên so sánh **đúng điều kiện**:

| Biến cần kiểm soát | Cách xử lý |
| --- | --- |
| Cùng dữ liệu thực tế | Cùng phân bố giá trị, kích thước nguồn, tỷ lệ giá trị null nếu có |
| Cùng ý nghĩa kết quả | Hai đường tính phải cho cùng tổng; xác minh trước khi đo |
| Có/không tính chi phí tạo nguồn | Đo riêng `int[]` với `List<Integer>`, và nếu cần, đo thêm chi phí chuyển đổi giữa hai dạng |
| JIT/warmup | Dùng warmup, nhiều lần chạy và process fork của JMH |
| Tránh phép tính bị tối ưu bỏ | Để benchmark trả giá trị hoặc dùng `Blackhole` theo hướng dẫn JMH |
| GC và allocation | Quan sát allocation/GC bên cạnh thời gian/throughput; không chỉ đo CPU |
| Môi trường | Ghi JDK/JVM, thiết bị, tải nền, cờ chạy, kích thước heap |
| Parallel | Đo riêng song song với mức độ song song và nguồn phù hợp; không coi parallel là mặc định nhanh hơn |

**Thiết kế đề xuất** (hai benchmark đối chiếu):

- `primitiveSum` đọc cùng mảng `int[]`, tính tổng bằng `Arrays.stream(data).asLongStream().sum()`.
- `boxedSum` đọc nguồn `List<Integer>` đã chuẩn bị sẵn, tính tổng bằng `list.stream().mapToLong(Integer::longValue).sum()`.
- Nếu mục đích là đo **phí boxing từ primitive sang danh sách**, thêm benchmark thứ ba bao gồm `Arrays.stream(data).boxed().collect(Collectors.toList())`. Đó là bài đo **khác** với việc chỉ tiêu thụ một danh sách đã có.

Không dùng một lần `System.nanoTime()` quanh hai pipeline rồi tuyên bố “nhanh gấp N lần”; phép đo đó dễ bị ảnh hưởng bởi JIT compilation, warmup, OS scheduling, GC, dead-code elimination và tối ưu hóa đặc thù dữ liệu. JMH giúp giảm nhiều sai lệch, nhưng vẫn cần benchmark thiết kế đúng và kiểm tra kết quả.

Với ứng dụng thật, ngoài microbenchmark hãy đo **độ trễ cuối tới cuối, allocation, GC, throughput** ở đường xử lý thực tế. Đôi khi phần chi phí lớn nhất nằm ở I/O, parsing, truy vấn dữ liệu hay logic nghiệp vụ, không phải boxing.

## 9. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Muốn `Stream<int>` nhưng trình biên dịch báo lỗi | Generic type không nhận primitive | Dùng `IntStream` hoặc `Stream<Integer>` tùy bài toán |
| `Stream.of(intArray).count()` trả 1 | Luồng gồm một object kiểu `int[]` | Dùng `Arrays.stream(intArray)` hoặc `IntStream.of(intArray)` |
| `List<Integer>` có `null` gây `NullPointerException` | Unboxing khi `mapToInt(Integer::intValue)` | Xử lý dữ liệu thiếu có chủ đích |
| `IntStream.sum()` âm dù mọi phần tử dương | Tràn `int` | Mở rộng sang `LongStream` trước khi cộng; xét giới hạn `long` |
| `Stream<Integer>.reduce(...)` nhìn dài và khó đọc | Dùng generic wrapper cho phép tính số đơn giản | Cân nhắc `mapToInt(...).sum()` |
| `boxed().mapToInt(...)` chỉ để cộng | Round-trip kiểu không cần thiết | Giữ pipeline primitive khi có thể |
| Đếm/giá trị trung bình cho stream rỗng bị xử lý sai | Nhầm `OptionalInt/OptionalDouble` với số mặc định | Kiểm tra `isPresent` hoặc dùng `orElse` có chủ đích |
| Quan sát kết quả benchmark thay đổi bất thường | Warmup/JIT/GC/nguồn dữ liệu chưa được kiểm soát | Đo bằng JMH, đối chiếu ứng dụng thực tế |
| `parallel()` làm chậm hơn | Chi phí chia tác vụ và gom kết quả lớn hơn lợi ích | Dùng tuần tự làm đường chuẩn, benchmark riêng |
| So sánh `Integer` bằng `==` cho kết quả khó hiểu | So sánh tham chiếu object thay vì giá trị | Dùng `equals`/`Objects.equals`, tránh phụ thuộc cache wrapper |

## 10. Bài tập tự kiểm tra

1. Cho `int[] data = {3, 4, 5}`. Viết pipeline tính tổng bình phương **không dùng `boxed()`**. Đáp án: `Arrays.stream(data).map(n -> n*n).sum()` trả `50`.
2. Vì sao `IntStream.range(1, 4).boxed()` có kiểu `Stream<Integer>` chứ không phải `Stream<int>`? Đáp án: `Stream<T>` yêu cầu đối số kiểu tham chiếu; `Integer` là wrapper.
3. Với `List<Integer> data = Arrays.asList(2, null, 8)`, vì sao `data.stream().mapToInt(Integer::intValue).sum()` lỗi? Nêu chính sách xử lý `null` phù hợp trong ứng dụng của bạn.
4. Tính kết quả `IntStream.of(Integer.MAX_VALUE, 1).sum()` và khi thêm `asLongStream()` trước `sum()`. Đáp án lần lượt là `-2147483648` và `2147483648L`.
5. `Stream.of(new int[]{1,2,3}).count()` trả bao nhiêu? Đáp án: `1`; vì stream có một phần tử kiểu mảng.
6. Có thể kết luận `IntStream` luôn nhanh hơn vòng `for` hay `Stream<Integer>` trên mọi JDK không? Đáp án: không; cần benchmark có kiểm soát và kiểm tra end-to-end.
7. Khi cần output `List<Integer>`, có nên `boxed()` không? Có thể có: định dạng kết quả đòi wrapper thì việc boxing ở boundary là hợp lý.
8. `IntStream.empty().average()` biểu diễn gì? Đáp án: `OptionalDouble.empty()`; không coi “không có dữ liệu” mặc nhiên là trung bình 0.

## Tài liệu chính thức và còn áp dụng

- [Java SE 25 — `IntStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): `boxed`, `mapToObj`, `asLongStream`, `sum`, `average`, `summaryStatistics`.
- [Java SE 25 — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `mapToInt`, `mapToLong`, phép toán trên object stream và quy tắc xử lý pipeline.
- [Java SE 25 — `LongStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/LongStream.html), [`DoubleStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/DoubleStream.html): các primitive stream tương ứng.
- [Oracle Java — Autoboxing và Unboxing](https://docs.oracle.com/javase/tutorial/java/data/autoboxing.html): cơ chế boxing/unboxing căn bản từ Java 5, vẫn còn đúng về mặt ngôn ngữ Java hiện đại.
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh): dự án benchmark chính thức, giải thích cách khởi tạo, chạy và thiết kế bài đo.

**Điểm cần ghi nhớ:** `IntStream/LongStream/DoubleStream` giúp duy trì các phép toán trên primitive, tránh đưa wrapper vào những bước **không cần** kiểu object. Chọn đúng điểm `boxed()`/`mapToInt()`/`mapToLong()`, kiểm soát `null` và tràn số, đồng thời đo bằng JMH trước khi đưa ra kết luận về tốc độ.
