# Giảm boxing và unboxing bằng Stream nguyên thủy

> **Chương:** Hiệu năng và bộ nhớ  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện các giới hạn về trạng thái, tài nguyên và hiệu năng.

Java Stream API giúp xử lý dữ liệu theo pipeline, nhưng không phải mọi pipeline đều mang cùng chi phí. Khi tính toán hàng triệu giá trị số, việc liên tục chuyển `int` thành `Integer`, `long` thành `Long`, rồi lại chuyển về kiểu nguyên thủy có thể tạo thêm đối tượng, tăng áp lực bộ nhớ và khiến chương trình làm nhiều việc hơn cần thiết.

Java cung cấp ba loại Stream dành riêng cho số nguyên thủy — `IntStream`, `LongStream`, `DoubleStream` — để thể hiện rõ **dữ liệu số** và hỗ trợ những thao tác như `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` mà không phải mô tả mọi giá trị qua một wrapper trong `Stream<T>`.

Bài học này trình bày cách nhận diện boxing/unboxing, chọn đúng loại Stream, xử lý chuyển đổi ở ranh giới đối tượng–số, và đánh giá lợi ích bộ nhớ một cách có kiểm chứng. Các ví dụ độc lập sử dụng **Java 17+**.

## 1. Boxing và unboxing thực sự xảy ra ở đâu?

Trong Java:

- **Boxing:** chuyển một giá trị nguyên thủy thành đối tượng wrapper tương ứng, chẳng hạn `int → Integer`, `long → Long`, `double → Double`.
- **Unboxing:** lấy lại giá trị nguyên thủy từ wrapper, chẳng hạn `Integer → int`.
- **Autoboxing/unboxing:** trình biên dịch chèn thao tác chuyển đổi khi ngữ cảnh yêu cầu, thường qua các phương thức như `Integer.valueOf(...)` và `Integer.intValue()`.

Ví dụ:

```java
int primitive = 42;
Integer boxed = primitive;    // autoboxing
int again = boxed;            // unboxing

Integer explicit = Integer.valueOf(42);
int explicitValue = explicit.intValue();
```

Hai dạng trên biểu đạt cùng việc chuyển kiểu, dù JVM có thể tối ưu hoặc tái sử dụng một số đối tượng wrapper. **Không nên suy rằng mỗi lần autoboxing chắc chắn cấp phát một đối tượng mới**: cache wrapper, JIT, escape analysis và tối ưu hóa khác có thể làm giảm số allocation thực tế.

Vấn đề xuất hiện khi một phép xử lý số học phải đi qua kiểu đối tượng một cách không cần thiết:

```java
import java.util.List;

List<Integer> values = List.of(2, 3, 5);

Integer boxedTotal = values.stream()       // Stream<Integer>
        .map(n -> n * n)                    // unbox để nhân, có thể box kết quả
        .reduce(0, Integer::sum);           // kết hợp trên các Integer

System.out.println(boxedTotal);            // 38
```

Ở đây `Stream<Integer>` mang các giá trị dưới dạng **kiểu wrapper**. Lambda `n -> n * n` phải thực hiện phép nhân trên `int`, còn `map` trả lại `Stream<Integer>`. Với `reduce(0, Integer::sum)`, đầu vào và kết quả của `BinaryOperator<Integer>` cũng nằm ở ranh giới đối tượng.

Ta có thể diễn đạt cùng phép tính bằng một pipeline số nguyên thủy:

```java
int primitiveTotal = values.stream()
        .mapToInt(Integer::intValue)  // Stream<Integer> -> IntStream
        .map(n -> n * n)              // int -> int
        .sum();                       // terminal operation -> int

System.out.println(primitiveTotal); // 38
```

**Khác biệt cần nhớ:** `List<Integer>` vốn đã chứa các wrapper, nên bước đọc dữ liệu vẫn phải unbox. Lợi ích là **các giai đoạn số học sau `mapToInt`** có thể tiếp tục làm việc với `int` mà không cần tạo `Stream<Integer>` ở mỗi bước.

## 2. Ba primitive stream và các thao tác tương ứng

| Kiểu Stream | Phần tử | Nguồn ví dụ | Tổng hợp điển hình |
| --- | --- | --- | --- |
| `IntStream` | `int` | `IntStream.range(0, 10)`, `Arrays.stream(int[])` | `sum()` trả `int`, `average()` trả `OptionalDouble`. |
| `LongStream` | `long` | `LongStream.of(...)`, `Stream<T>.mapToLong(...)` | `sum()` trả `long`; phù hợp tổng số lượng lớn hơn `int`. |
| `DoubleStream` | `double` | `DoubleStream.of(...)`, `Stream<T>.mapToDouble(...)` | `sum()`, `average()`, `summaryStatistics()` trên `double`. |
| `Stream<Integer>` | `Integer` | `List<Integer>.stream()`, `IntStream.boxed()` | `reduce(...)` hoặc collector; số đi qua wrapper. |
| `Stream<Long>` | `Long` | `List<Long>.stream()`, `LongStream.boxed()` | `reduce(...)` hoặc collector; số đi qua wrapper. |

Một `Stream<T>` thông thường **không có** terminal operation `sum()`. Primitive stream có các phép tính số học chuyên dụng và trả trực tiếp kiểu số nguyên thủy khi phù hợp.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

int intSum = IntStream.of(2, 3, 5).sum();
long longSum = LongStream.of(2L, 3L, 5L).sum();
double doubleSum = DoubleStream.of(2.0, 3.0, 5.0).sum();

System.out.println(intSum);    // 10
System.out.println(longSum);   // 10
System.out.println(doubleSum); // 10.0
```

### `map` và `mapToInt` không giống nhau

Đối với một `Stream<Order>` hay `Stream<Product>`, ta chọn phương thức theo **kiểu đầu ra**:

```java
Stream<Product> products = ...;

// Object -> object:
Stream<String> names = products.map(Product::name);

// Object -> primitive int:
IntStream quantities = products.mapToInt(Product::quantity);

// Object -> primitive long:
LongStream cents = products.mapToLong(Product::priceCents);
```

Đây là minh họa chữ ký, không phải đoạn chạy độc lập: `Product` phải là kiểu do ứng dụng định nghĩa và mỗi biến `products` chỉ được dùng cho một terminal operation trong một pipeline. Trong chương trình đầy đủ ở mục 5, ta tạo **Stream mới từ danh sách** ở từng phép tính.

Với primitive stream cũng có cách đổi kiểu:

```java
IntStream ints = IntStream.of(1, 2, 3);
LongStream longs = ints.asLongStream(); // int -> long, không cần wrapper
System.out.println(longs.sum());       // 6
```

`IntStream.asLongStream()`, `IntStream.asDoubleStream()`, `IntStream.mapToLong(...)` và `LongStream.mapToDouble(...)` giúp tiếp tục ở miền nguyên thủy khi phải đổi kiểu số.

## 3. Tạo nguồn primitive đúng cách

Khi dữ liệu ban đầu đã là mảng `int[]`, hãy tránh tạo một lớp đối tượng trung gian chỉ để mở Stream:

```java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Stream;

int[] scores = {2, 5, 9};

IntStream fromArray = Arrays.stream(scores);
IntStream fromOf = IntStream.of(scores);

System.out.println(fromArray.sum()); // 16
System.out.println(fromOf.count());  // 3

// KHÁC: Stream.of(scores) có một phần tử kiểu int[].
long arrayObjects = Stream.of(scores).count();
System.out.println(arrayObjects);   // 1
```

Vì `Stream.of(scores)` nhận **toàn bộ mảng `int[]` làm một đối tượng**, kết quả là `Stream<int[]>` có một phần tử, không phải `IntStream` có ba số. Đây là lỗi thường gặp khi chuyển từ API làm việc với object sang primitive array.

Hai cách tạo dải giá trị số nguyên:

```java
IntStream.range(1, 5)       // 1, 2, 3, 4: không gồm cận trên
IntStream.rangeClosed(1, 5) // 1, 2, 3, 4, 5: gồm cận trên
```

Nếu dữ liệu được tạo bằng thuật toán và không cần tồn tại trước dưới dạng `List<Integer>`, việc bắt đầu từ `IntStream.range(...)` có thể tránh bước boxing của việc xây danh sách số.

### Cẩn thận với `Stream.of(1, 2, 3)`

```java
long boxedCount = Stream.of(1, 2, 3).count();  // Stream<Integer>
long primitiveCount = IntStream.of(1, 2, 3).count();

System.out.println(boxedCount);     // 3
System.out.println(primitiveCount); // 3
```

Hai nguồn có cùng số lượng, nhưng **kiểu pipeline khác nhau**. `Stream.of(1, 2, 3)` biểu diễn các phần tử như `Integer`; `IntStream.of(1, 2, 3)` giữ `int` trên các thao tác tiếp theo.

## 4. Chuyển đổi ở ranh giới: `mapToInt`, `mapToLong`, `boxed`, `mapToObj`

Cách giảm boxing hiệu quả thường không phải “tránh object bằng mọi giá”, mà là **chỉ chuyển sang object khi thật sự cần**.

| Nguồn | Phương thức | Kết quả | Khi dùng |
| --- | --- | --- | --- |
| `Stream<Integer>` | `mapToInt(Integer::intValue)` | `IntStream` | Sau khi đọc danh sách wrapper, cần tính số. |
| `Stream<Order>` | `mapToLong(Order::amountCents)` | `LongStream` | Mỗi đơn chuyển sang thành tiền nguyên thủy. |
| `IntStream` | `asLongStream()` | `LongStream` | Tổng có thể vượt miền `int`. |
| `IntStream` | `boxed()` | `Stream<Integer>` | API bên ngoài hoặc collector cần `Integer`. |
| `IntStream` | `mapToObj(n -> "ID-" + n)` | `Stream<String>` | Cần tạo đối tượng/chuỗi để hiển thị. |
| `LongStream` | `boxed()` | `Stream<Long>` | Cần danh sách hoặc Map có giá trị `Long`. |
| `DoubleStream` | `boxed()` | `Stream<Double>` | Cần truyền vào API dùng wrapper. |

Ví dụ từ dữ liệu số nguyên sang nhãn:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(id -> "ID-" + id)
        .toList();

System.out.println(labels); // [ID-1, ID-2, ID-3]
```

Ở đây việc tạo `String` **là yêu cầu nghiệp vụ**, không phải một lần boxing vô ích. Nếu muốn tính tổng các ID thì nên tính **trước khi `mapToObj`**, hoặc tạo pipeline riêng cho phép tính số.

```java
List<Integer> numbers = IntStream.rangeClosed(1, 3)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3]
```

`boxed()` là cần thiết nếu API đích yêu cầu `List<Integer>`; kết quả của `Stream.toList()` là danh sách không sửa được. Nhưng sau khi `boxed()`, các bước tiếp theo trở lại thế giới `Stream<Integer>`.

## 5. Ví dụ đầy đủ: tổng tiền dòng bán hàng bằng `LongStream`

Một cửa hàng lưu các dòng bán hàng với SKU, số lượng, đơn giá theo **xu** (đơn vị tiền nhỏ nhất, dùng `long`) và trạng thái đã thanh toán. Yêu cầu: chỉ tính **dòng đã thanh toán có số lượng từ 2 trở lên**, rồi cộng thành tiền của các dòng hợp lệ.

| SKU | Số lượng | Giá mỗi đơn vị (xu) | Đã thanh toán? | Có tính? | Thành tiền |
| --- | ---: | ---: | --- | --- | ---: |
| PEN | 3 | 1.299 | Có | Có | 3.897 |
| NOTE | 2 | 2.500 | Có | Có | 5.000 |
| BAG | 1 | 9.900 | Không | Không | — |
| CLIP | 5 | 199 | Có | Có | 995 |
| PEN | 1 | 1.299 | Có | Không | — |

**Tổng mong đợi:** `3_897 + 5_000 + 995 = 9_892L`.

Lưu tệp `PrimitiveStreamBoxingDemo.java`. Chương trình Java 17+ dưới đây có cả pipeline kiểu wrapper, pipeline `LongStream` và các phép tự kiểm thử, **không cần thư viện ngoài JDK**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamBoxingDemo {

    record SaleLine(
            String sku,
            int quantity,
            long unitPriceCents,
            boolean paid
    ) {
        SaleLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("SKU rỗng");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Dòng bán không hợp lệ");
            }
        }

        long amountCents() {
            return Math.multiplyExact((long) quantity, unitPriceCents);
        }
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("PEN", 3, 1_299L, true),
                new SaleLine("NOTE", 2, 2_500L, true),
                new SaleLine("BAG", 1, 9_900L, false),
                new SaleLine("CLIP", 5, 199L, true),
                new SaleLine("PEN", 1, 1_299L, true)
        );
    }

    static boolean eligible(SaleLine line) {
        return line.paid() && line.quantity() >= 2;
    }

    // Object pipeline: map trả Stream<Long>.
    static long boxedTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .map(SaleLine::amountCents)
                .reduce(0L, Long::sum);
    }

    // Primitive pipeline: mapToLong trả LongStream.
    static long primitiveTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .sum();
    }

    // Nếu nghiệp vụ yêu cầu phát hiện tràn tổng long.
    static long checkedTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .reduce(0L, Math::addExact);
    }

    static List<String> eligibleSkus(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .map(SaleLine::sku) // Ở đây cần String, map là đúng.
                .toList();
    }

    static int doubledPositiveStock(int[] changes) {
        return Arrays.stream(changes)
                .filter(delta -> delta > 0)
                .map(delta -> Math.multiplyExact(delta, 2))
                .sum();
    }

    static void check(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    static void selfTest() {
        List<SaleLine> data = sample();

        check(boxedTotal(data) == 9_892L, "Boxed total");
        check(primitiveTotal(data) == 9_892L, "Primitive total");
        check(checkedTotal(data) == 9_892L, "Checked total");
        check(boxedTotal(data) == primitiveTotal(data),
                "Hai pipeline khác kết quả");
        check(eligibleSkus(data).equals(
                List.of("PEN", "NOTE", "CLIP")), "Sai thứ tự SKU");

        // Không có dòng hợp lệ: tổng của cả hai pipeline bằng 0.
        check(boxedTotal(List.of()) == 0L, "Nguồn rỗng");
        check(primitiveTotal(List.of(
                new SaleLine("X", 1, 100L, true),
                new SaleLine("Y", 5, 100L, false)
        )) == 0L, "Nguồn bị filter hết");

        // Hai cách tạo IntStream từ mảng int[].
        int[] values = {2, 5, 9};
        check(Arrays.stream(values).sum() == 16, "Array IntStream");
        check(IntStream.of(values).count() == 3, "IntStream.of array");
        check(Stream.of(values).count() == 1,
                "Stream.of(int[]) chỉ có một phần tử int[]");
        check(IntStream.of(values).boxed().toList()
                .equals(List.of(2, 5, 9)), "Boxed list");

        // Thao tác tính toán trên IntStream.
        check(doubledPositiveStock(new int[] {4, -2, 6, 3}) == 26,
                "Tồn kho dương nhân đôi");
        check(IntStream.rangeClosed(1, 5).sum() == 15,
                "rangeClosed");
        check(IntStream.range(1, 5).sum() == 10, "range");

        // Kết quả tùy chọn cho trung bình/cực trị.
        OptionalDouble average = IntStream.of(values).average();
        check(average.isPresent(), "Thiếu average");
        check(Math.abs(average.orElseThrow() - 16.0 / 3.0) < 1e-12,
                "Sai average");
        check(IntStream.empty().average().isEmpty(),
                "Average rỗng không phải OptionalDouble.empty");

        OptionalInt minimum = IntStream.of(values).min();
        check(minimum.orElse(-1) == 2, "Sai min");
        check(IntStream.empty().min().isEmpty(),
                "Min rỗng không phải OptionalInt.empty");

        IntSummaryStatistics stats =
                IntStream.of(values).summaryStatistics();
        check(stats.getCount() == 3, "Count trong stats");
        check(stats.getSum() == 16, "Sum trong stats");
        check(stats.getMin() == 2, "Min trong stats");
        check(stats.getMax() == 9, "Max trong stats");

        // Dữ liệu wrapper có thể chứa null: lọc TRƯỚC unbox.
        List<Integer> nullable = Arrays.asList(4, null, 6);
        int filtered = nullable.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        check(filtered == 10, "Dữ liệu chứa null");

        // Nếu cần tổng vượt int, chuyển thành long trước khi cộng.
        long safe = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();
        check(safe == 2_147_483_648L, "Tổng long");

        boolean overflowDetected = false;
        try {
            LongStream.of(Long.MAX_VALUE, 1L)
                    .reduce(0L, Math::addExact);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }
        check(overflowDetected, "Phải phát hiện overflow long");

        // Pure pipeline: kết quả số học không đổi khi parallel.
        long parallelTotal = data.parallelStream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .sum();
        check(parallelTotal == 9_892L, "Sai tổng song song");

        // Đảo dữ liệu không đổi tổng, nhưng thay encounter order.
        List<SaleLine> reversed = new ArrayList<>(data);
        java.util.Collections.reverse(reversed);
        check(primitiveTotal(reversed) == 9_892L,
                "Tổng thay đổi khi đảo nguồn");
        check(eligibleSkus(reversed).equals(
                List.of("CLIP", "NOTE", "PEN")),
                "Thứ tự SKU sau đảo nguồn");
    }

    public static void main(String[] args) {
        List<SaleLine> data = sample();
        System.out.println("Boxed total: " + boxedTotal(data));
        System.out.println("Primitive total: " + primitiveTotal(data));
        System.out.println("Checked total: " + checkedTotal(data));
        System.out.println("Eligible SKUs: " + eligibleSkus(data));
        System.out.println("Positive restock x2: "
                + doubledPositiveStock(new int[] {4, -2, 6, 3}));
        System.out.println("Int array sum: "
                + Arrays.stream(new int[] {2, 5, 9}).sum());

        // Tự kiểm tra mà không cần bật cờ -ea.
        selfTest();
        System.out.println("ALL PRIMITIVE STREAM TESTS PASS");
    }
}
```

Biên dịch và chạy khi thực hành:

```text
javac PrimitiveStreamBoxingDemo.java
java PrimitiveStreamBoxingDemo
```

Kết quả dự kiến:

```text
Boxed total: 9892
Primitive total: 9892
Checked total: 9892
Eligible SKUs: [PEN, NOTE, CLIP]
Positive restock x2: 26
Int array sum: 16
ALL PRIMITIVE STREAM TESTS PASS
```

Hai phương thức `boxedTotal` và `primitiveTotal` dùng **cùng tập dữ liệu, cùng điều kiện lọc, cùng phép nhân và cùng phép cộng**. Mục đích là chứng minh chúng tương đương về giá trị, không tuyên bố một cách định lượng rằng phương thức nào nhanh hơn. Để khẳng định lợi ích hiệu năng cần đo benchmark trong môi trường thật.

## 6. Những chỗ boxing có thể trở lại trong pipeline

Ngay cả khi bắt đầu bằng primitive stream, chương trình vẫn có thể quay lại wrapper nếu áp dụng một thao tác cần object:

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, List<Integer>> grouped = IntStream.of(2, 3, 4, 5)
        .boxed()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "EVEN" : "ODD"));

System.out.println(grouped.get("EVEN")); // [2, 4]
```

`Collectors.groupingBy` nhận `Stream<T>`, không nhận trực tiếp `IntStream` như một `Stream<Integer>`; việc `boxed()` là một **ranh giới cần thiết** nếu muốn dùng collector đó. Các khóa và danh sách trong Map cũng là đối tượng, nên không thể hứa toàn bộ bài toán “không boxing”.

### Không box rồi lại unbox ngay

Đoạn sau thường tạo một vòng chuyển đổi không cần thiết:

```java
int total = IntStream.rangeClosed(1, 1_000)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();
```

Trong ví dụ này, có thể viết:

```java
int total = IntStream.rangeClosed(1, 1_000).sum();
```

Hãy nhìn vào **kiểu của từng stage**, không chỉ vào cú pháp. Một vài hàm tiện ích chung nhận `Stream<Integer>` có thể khiến pipeline phải box sớm hơn cần thiết; cân nhắc cung cấp overload nhận `IntStream` hoặc hàm tính toán trên primitive khi đây là đường xử lý nóng và API cho phép.

### Boxing không phải chỉ xảy ra ở `boxed()`

Các thao tác có kết quả là object, như `mapToObj(n -> new Event(n))`, vẫn phải tạo đối tượng `Event` nếu nghiệp vụ yêu cầu. Điều đó không giống việc boxing `int` thành `Integer` vô ích. Tránh tối ưu bằng cách “không tạo bất kỳ object nào” khi đầu ra thật sự phải là record, chuỗi hoặc Map.

Một số thao tác stateful như `distinct()`, `sorted()` có thể phải sử dụng vùng nhớ trung gian; chi tiết tối ưu bên trong phụ thuộc JDK. **Primitive stream không cam kết toàn bộ pipeline hoàn toàn không allocation**.

## 7. Bộ nhớ: mảng nguyên thủy, wrapper và vật hóa kết quả

So sánh ba dạng dữ liệu:

```java
int[] primitiveArray = {1, 2, 3};
List<Integer> boxedList = List.of(1, 2, 3);
int[] processed = IntStream.of(1, 2, 3)
        .map(n -> n * 2)
        .toArray();
```

Về mô hình lưu trữ:

- `int[]` chứa giá trị `int` trực tiếp trong mảng.
- `List<Integer>` lưu **tham chiếu đến các wrapper `Integer`**. Các đối tượng wrapper có thể được tái sử dụng/cached, nên không thể suy từ số phần tử rằng có đúng bấy nhiêu đối tượng vừa được cấp phát.
- `IntStream.toArray()` trả `int[]`, còn `IntStream.boxed().toList()` trả `List<Integer>`. Hai kết quả có khả năng sử dụng bộ nhớ khác nhau vì hình dạng dữ liệu khác nhau.

Đối với một pipeline số học không cần giữ tất cả đầu ra, `sum()`, `count()` hoặc `summaryStatistics()` có thể tránh việc tạo hẳn một danh sách kết quả. Nhưng một phép `sorted()` hoặc thao tác stateful có thể cần lưu trữ trung gian dù dùng primitive stream.

Không nên khẳng định cố định “mỗi `Integer` tốn X byte” trên mọi JVM: kích thước đối tượng phụ thuộc compressed references, alignment, phiên bản/runtime và tối ưu hóa. Khi bộ nhớ là vấn đề thật, hãy đo **allocation rate, GC, heap usage** bằng công cụ phù hợp thay vì chỉ suy từ chữ ký kiểu.

## 8. Tránh tràn số và hiểu đúng `sum()`

Chuyển sang `IntStream` không làm phép cộng `int` rộng ra:

```java
int overflow = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(overflow); // -2147483648, tràn int

long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
System.out.println(widened); // 2147483648
```

Nếu đầu vào là số lượng `int` nhưng tổng có thể lớn, `mapToLong` hoặc `asLongStream` giúp **mở rộng miền số trước khi cộng**. Nếu tổng vượt cả `long`, `LongStream.sum()` vẫn có thể tràn; khi cần phát hiện lỗi, dùng `reduce(0L, Math::addExact)` hoặc kiểu số lớn hơn theo yêu cầu.

### Cẩn thận với phép nhân trước khi đổi sang `long`

```java
int quantity = 100_000;
int price = 100_000;

long wrong = quantity * price;        // Tràn trong int trước khi gán.
long right = (long) quantity * price; // 10000000000.
```

`mapToLong(line -> line.quantity() * line.price())` **không bảo đảm** tránh tràn nếu cả hai phép lấy giá trị đều trả `int`: phép nhân trong lambda vẫn có thể diễn ra dưới kiểu `int`. Hãy ép kiểu **trước phép nhân**, hoặc dùng `Math.multiplyExact` theo đúng kiểu mong muốn.

Trong chương trình mẫu, `amountCents()` dùng `Math.multiplyExact((long) quantity, unitPriceCents)` để báo lỗi nếu phép nhân vượt miền `long`.

## 9. `null`, kết quả rỗng và các kiểu `Optional` nguyên thủy

`IntStream`, `LongStream`, `DoubleStream` **không có phần tử null**. Nhưng nguồn `Stream<Integer>` hoặc `List<Integer>` có thể chứa `null`, và unboxing null gây `NullPointerException`.

```java
import java.util.Arrays;
import java.util.Objects;

List<Integer> numbers = Arrays.asList(4, null, 6);

int total = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 10
```

Nếu null là lỗi nhập liệu, việc **lọc bỏ** null có thể che giấu dữ liệu sai; khi đó hãy validate trước hoặc báo lỗi có thông điệp rõ ràng. `List.of(...)` của Java không chấp nhận phần tử null, còn một số collection và nguồn bên ngoài thì có thể.

Các phép toán tổng hợp có kết quả tùy chọn:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalDouble average = IntStream.of(2, 5, 9).average();
OptionalInt minimum = IntStream.of(2, 5, 9).min();

System.out.println(average.orElse(0.0)); // 5.333333333333333
System.out.println(minimum.orElse(-1));  // 2

System.out.println(IntStream.empty().average().isEmpty()); // true
System.out.println(IntStream.empty().min().isEmpty());     // true
```

Với nguồn rỗng:

- `sum()` trả **0** của kiểu số tương ứng.
- `count()` trả `0L`.
- `average()` trả `OptionalDouble.empty()`.
- `min()` và `max()` trả `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` rỗng tùy loại Stream.

Không suy rằng `min()` của Stream rỗng là `0`: `0` ở đây chỉ có thể là giá trị do **người gọi** chọn qua `orElse(...)`, và có thể là một giá trị có nghĩa khác trong nghiệp vụ.

## 10. `summaryStatistics()`: nhiều chỉ số trong một lần duyệt

Khi cần cả số lượng, tổng, min, max và trung bình trên cùng một nguồn nguyên thủy, có thể dùng `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(2, 5, 9)
        .summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 16
System.out.println(stats.getMin());     // 2
System.out.println(stats.getMax());     // 9
System.out.println(stats.getAverage()); // 5.333333333333333
```

Điểm mạnh ở đây không chỉ là hạn chế boxing: **một terminal operation** có thể tính đủ các đại lượng, thay vì tạo nhiều Stream mới từ một nguồn khó duyệt hoặc vật hóa dữ liệu trung gian.

`IntSummaryStatistics` là một **đối tượng thống kê duy nhất**, không đồng nghĩa xử lý từng số phải chuyển sang `Integer`. Đây là ví dụ cho thấy có thể sử dụng object ở ranh giới kết quả trong khi phần dữ liệu được xử lý là primitive.

### Giới hạn cần biết

`IntSummaryStatistics` lưu tổng bằng `long`; nếu miền dữ liệu và số phần tử đủ lớn, cả `long` cũng có giới hạn. Với `DoubleSummaryStatistics`, kết quả `double` chịu quy tắc sai số dấu phẩy động. Nếu là tiền, không tự chuyển `BigDecimal` sang `double` chỉ để dùng được `DoubleStream`.

## 11. `DoubleStream` không phải lựa chọn mặc định cho tiền

`DoubleStream` thích hợp cho đo đạc, thống kê hoặc các bài toán số thực **chấp nhận sai số dấu phẩy động**:

```java
import java.util.stream.DoubleStream;

double averageTemperature = DoubleStream.of(28.5, 29.0, 30.5)
        .average()
        .orElseThrow();
System.out.println(averageTemperature); // 29.333333333333332 (xấp xỉ)
```

`DoubleStream.sum()` có thể sử dụng thuật toán cộng bù và cho sai số khác với phép cộng tuần tự đơn giản. Do tính chất dấu phẩy động, **không nên viết test dựa vào so sánh bit-for-bit** giữa mọi thứ tự/chiến lược song song mà chưa xác định hợp đồng số học. Hãy định nghĩa độ sai lệch chấp nhận được, cách làm tròn và các trường hợp `NaN`/`Infinity` theo miền dữ liệu.

Với tiền cần chính xác thập phân:

```java
import java.math.BigDecimal;
import java.util.List;

BigDecimal totalMoney = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(totalMoney); // 0.30
```

`BigDecimal` là đối tượng và `Stream<BigDecimal>` là lựa chọn phù hợp khi yêu cầu chính xác cao hơn việc giảm boxing. **Tính đúng đắn nghiệp vụ đứng trước tối ưu số lượng wrapper**.

## 12. Đo hiệu năng: kiểm chứng thay vì suy đoán

Hãy đặt một câu hỏi cụ thể: “Với dữ liệu `int[]` dài hàng triệu phần tử, pipeline `IntStream` có giảm lượng cấp phát và thời gian so với `Stream<Integer>` hay không?” Cần đo theo cùng **công việc** và cùng **điều kiện**:

1. Hai phiên bản phải áp dụng cùng phép lọc, phép ánh xạ và cùng quy tắc tính tổng.
2. Cố gắng kiểm soát chi phí **tạo dữ liệu đầu vào**. So sánh việc đọc từ `int[]` với việc tạo mới `List<Integer>` sẽ bao gồm cả chi phí xây danh sách; nếu mục tiêu đo riêng pipeline, hãy chuẩn bị dữ liệu trước.
3. Phân biệt phép đo **throughput, latency, allocation rate, GC**; không chỉ đo thời gian một lần chạy.
4. Cho JVM có điều kiện warm-up và tránh dead-code elimination; nếu dùng microbenchmark Java, ưu tiên **JMH** với phép kiểm tra kết quả rõ ràng.
5. Thử các kích thước dữ liệu và phép toán khác nhau: pipeline rất nhỏ có thể bị overhead chi phối; pipeline nặng CPU có thể không nhạy với chi phí wrapper bằng pipeline nhẹ.
6. Ghi lại JDK, JVM, heap, CPU, mức song song và cấu hình chạy; hiệu quả có thể khác khi đổi môi trường.

| Quan sát | Có thể gợi ý điều gì? | Chưa đủ để kết luận gì? |
| --- | --- | --- |
| Primitive pipeline ít allocation hơn | Wrapper hoặc danh sách trung gian trước đây gây chi phí. | Mọi pipeline primitive sẽ nhanh hơn. |
| Hai phiên bản có thời gian gần nhau | JVM tối ưu boxing tốt, hoặc chi phí khác chiếm ưu thế. | Boxing hoàn toàn miễn phí trong mọi trường hợp. |
| `parallel()` nhanh hơn một lần | Có thể nguồn đủ lớn hoặc máy nhiều lõi. | Tăng tốc ổn định dưới tải sản xuất. |
| `DoubleStream` nhanh hơn `BigDecimal` | Yêu cầu độ chính xác khác nhau. | Có thể thay kiểu tiền mà không ảnh hưởng nghiệp vụ. |

**Không tạo benchmark chỉ bằng `System.nanoTime()` chạy một lần rồi coi đó là chứng cứ.** Kết quả của một lượt có thể chịu ảnh hưởng JIT, GC, cache, tải máy hoặc tối ưu loại bỏ công việc không dùng đến.

## 13. Kiểu lỗi hay gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Stream<Integer>` để tính số nhưng mỗi bước lại `map` và `reduce` wrapper | Có thể tăng boxing/unboxing và chi phí xử lý. | Chuyển sang `IntStream` bằng `mapToInt` nếu đầu ra vẫn là số. |
| Tưởng `Stream.of(intArray)` là Stream các số | Thực tế chỉ có một phần tử kiểu `int[]`. | Dùng `Arrays.stream(intArray)` hoặc `IntStream.of(intArray)`. |
| `boxed()` rồi `mapToInt(Integer::intValue)` ngay | Chuyển qua lại kiểu không cần thiết. | Giữ pipeline nguyên thủy đến ranh giới API bắt buộc. |
| Cố dùng `Collectors.groupingBy` trực tiếp trên `IntStream` | Collector dành cho `Stream<T>`, không dùng trực tiếp cùng kiểu. | Dùng `boxed()` ở chỗ cần grouping hoặc thiết kế cách tổng hợp chuyên biệt. |
| Unbox phần tử `null` | `NullPointerException`. | Xác định chính sách null; lọc hoặc validate trước `mapToInt`. |
| Dùng `IntStream.sum()` cho tổng quá `int` | Có thể tràn số. | Chuyển `asLongStream()` trước khi cộng, hoặc dùng kiểu lớn hơn. |
| Hai số `int` nhân trước khi chuyển sang `long` | Tràn ngay trong biểu thức, dù kết quả được gán cho `long`. | Ép kiểu trước phép nhân hoặc dùng `Math.multiplyExact`. |
| Dùng `DoubleStream` cho tiền để giảm boxing | Sai số số thực, có thể sai nghiệp vụ. | Ưu tiên `BigDecimal` hoặc đơn vị nhỏ nhất dạng số nguyên. |
| Gọi `getAsInt()` trên `OptionalInt.empty()` | Ném `NoSuchElementException`. | Dùng `isPresent`, `orElse`, `orElseThrow` theo yêu cầu. |
| Tưởng primitive stream không bao giờ cấp phát | Có thể có trạng thái/array trung gian và kết quả object. | Đo allocation, phân biệt kiểu phần tử với chiến lược thực thi. |
| Dùng `parallelStream()` chỉ để “tránh boxing” | Không giải quyết boxing và có thể thêm chi phí chia/gộp. | Chọn kiểu primitive trước, rồi đo nhu cầu song song riêng. |
| Đo benchmark mà hai phiên bản làm công việc khác nhau | Kết luận hiệu năng không có ý nghĩa. | Xây ca kiểm thử chức năng tương đương và chuẩn hóa dữ liệu đầu vào. |

## 14. Bài tập tự luyện

**Bài 1 — Chuyển từ `Stream<Integer>` sang `IntStream`.** Cho `List.of(2, 3, 5)`, bình phương các số và tính tổng, không trả về `Stream<Integer>` sau phép bình phương.

```java
int sumSquares = List.of(2, 3, 5).stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * n)
        .sum();
System.out.println(sumSquares); // 38
```

**Bài 2 — Hai cận của dải số.** Dự đoán `IntStream.range(1, 4).sum()` và `IntStream.rangeClosed(1, 4).sum()`.

**Đáp án:** `range(1, 4)` là `1 + 2 + 3 = 6`; `rangeClosed(1, 4)` là `1 + 2 + 3 + 4 = 10`.

**Bài 3 — Mảng nguyên thủy.** Với `int[] data = {4, 6, 8}`, `Stream.of(data).count()` và `Arrays.stream(data).count()` trả bao nhiêu?

**Đáp án:** Lần lượt **1** và **3**. `Stream.of(data)` coi cả mảng là một phần tử; `Arrays.stream(data)` tạo `IntStream` duyệt ba số.

**Bài 4 — Tổng vượt miền `int`.** Cần tính `Integer.MAX_VALUE + 2` dưới dạng `long` mà không tràn `int`.

```java
long total = IntStream.of(Integer.MAX_VALUE, 2)
        .asLongStream()
        .sum();
System.out.println(total); // 2147483649
```

**Bài 5 — Nguyên nhân xuất hiện `Integer`.** Vì sao `IntStream.range(1, 5).boxed().collect(Collectors.toList())` phải có wrapper?

**Đáp án:** `boxed()` chuyển mỗi `int` thành `Integer` để đi qua `Stream<Integer>` và được lưu trong một `List<Integer>`. Khi danh sách đối tượng là đầu ra thực sự cần thiết, đó là chi phí mô hình dữ liệu chứ không phải lỗi lập trình.

**Bài 6 — Trung bình rỗng.** `IntStream.empty().average()` trả kiểu gì? Nếu nghiệp vụ quy định không có dữ liệu là “không có kết quả”, nên làm gì?

**Đáp án:** Trả `OptionalDouble.empty()`. Có thể giữ `OptionalDouble` và hiển thị một thông báo hoặc lỗi hợp lệ; không tự biến rỗng thành `0.0` nếu đó có thể bị hiểu là trung bình bằng 0.

**Bài 7 — Tổng doanh thu.** Viết lại `boxedTotal` trong ví dụ ở mục 5 bằng `LongStream`, sau đó thay `sum()` bằng phép cộng có phát hiện overflow. So sánh ba kết quả trên dữ liệu mẫu.

**Gợi ý:** `mapToLong(SaleLine::amountCents).reduce(0L, Math::addExact)`. Ba kết quả trên dữ liệu mẫu phải là `9892`; nếu dữ liệu vượt miền số, bản kiểm tra có thể ném `ArithmeticException`.

**Bài 8 — Quyết định kiểu Stream.** Một pipeline cần nhận dữ liệu đo nhiệt độ `double[]` và tìm trung bình; pipeline khác cần tổng tiền `BigDecimal` có quy tắc làm tròn. Chọn primitive stream nào?

**Đáp án:** Dùng `DoubleStream` cho nhiệt độ nếu sai số số thực được chấp nhận; **không chọn `DoubleStream` cho tiền** chỉ để giảm boxing — giữ `BigDecimal` và xác định quy tắc làm tròn.

## 15. Ghi nhớ

- `Stream<Integer>`, `Stream<Long>`, `Stream<Double>` mang kiểu wrapper; `IntStream`, `LongStream`, `DoubleStream` giúp các phép toán số **tránh nhiều chuyển đổi boxing/unboxing không cần thiết**.
- Khi nguồn là danh sách đối tượng, dùng `mapToInt`/`mapToLong`/`mapToDouble` **ở ranh giới chuyển sang phép tính số**; chỉ `boxed()` hoặc `mapToObj()` khi đầu ra thực sự cần object.
- Với `int[]`, dùng `Arrays.stream(array)` hoặc `IntStream.of(array)`, không nhầm với `Stream.of(array)` có một phần tử là cả mảng.
- Primitive stream cung cấp `sum`, `average`, `min`, `max`, `summaryStatistics`, nhưng vẫn phải xử lý **overflow, null ở nguồn wrapper và Optional rỗng**.
- `int`/`long` không thay `BigDecimal` trong mọi bài toán tiền; `DoubleStream` có sai số số thực. **Đúng nghiệp vụ trước, tối ưu sau**.
- Primitive stream không hứa **zero allocation** hoặc luôn nhanh hơn. Hãy dùng kiểm thử giá trị để bảo đảm tương đương, sau đó đo bằng benchmark và profiling nếu hiệu năng thật sự quan trọng.
