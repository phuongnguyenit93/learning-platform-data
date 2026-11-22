# Làm phẳng bằng flatMapToInt, flatMapToLong và flatMapToDouble

## 1. Khi nào cần làm phẳng dữ liệu số?

Trong Java Stream API, dữ liệu có sẵn thường được xử lý theo pipeline lazy gồm các thao tác như `filter`, `map`, `reduce` và `collect`. Một tình huống thường gặp là **mỗi phần tử đầu vào chứa nhiều số**, trong khi kết quả cần là một dãy số liên tục để tính tổng, tìm cực trị hoặc thống kê.

Ví dụ, mỗi đợt giao hàng chứa một mảng số lượng sản phẩm:

```text
Stream<int[]>                        IntStream
  [2, 3]  ─────────────────────────► 2, 3
  [4]     ── flatMapToInt(...) ────► 4
  []      ─────────────────────────► (không có phần tử)

Kết quả sau khi làm phẳng: 2, 3, 4
```

Ba phương thức **`flatMapToInt`, `flatMapToLong` và `flatMapToDouble`** giúp chuyển một `Stream<T>` thành luồng số nguyên thủy tương ứng:

- `flatMapToInt` tạo `IntStream` gồm các giá trị `int`.
- `flatMapToLong` tạo `LongStream` gồm các giá trị `long`.
- `flatMapToDouble` tạo `DoubleStream` gồm các giá trị `double`.

Khác với ánh xạ một-một, mỗi phần tử đầu vào được phép sinh **không có phần tử, một phần tử hoặc nhiều phần tử** đầu ra. Các Stream con được nối thành một luồng nguyên thủy duy nhất.

Bài học thuộc chương **Stream kiểu nguyên thủy** và tập trung vào cách chọn đúng phương thức, cách tổ chức mapper, an toàn dữ liệu, cách thu thập kết quả và những giới hạn về hiệu năng của việc làm phẳng.

Sau khi học, bạn có thể tự viết pipeline để:

1. Trải phẳng danh sách mảng số nguyên, danh sách mã `long` hoặc tập mẫu đo `double`.
2. Kết hợp `filter`, `flatMapToX` và các terminal operation `sum`, `average`, `summaryStatistics`, `toArray`.
3. Phân biệt `mapToX` với `flatMapToX`, và `Stream.flatMapToX` với `IntStream.flatMap`/`LongStream.flatMap`/`DoubleStream.flatMap`.
4. Xử lý tập con rỗng, `null`, lỗi parse, Stream vô hạn và dữ liệu mutable.
5. Đánh giá chi phí tạo Stream con, boxing, xử lý song song và độ chính xác số học.

Các ví dụ hoàn chỉnh dùng **Java 17+**. Ba phép `flatMapToX` đã có từ Java 8; những ví dụ dùng `List.of` cần Java 9+, `record` và `Stream.toList()` cần Java 16+.

## 2. Hợp đồng của ba phương thức

Trên `Stream<T>`, Java cung cấp:

```java
IntStream flatMapToInt(
        Function<? super T, ? extends IntStream> mapper);

LongStream flatMapToLong(
        Function<? super T, ? extends LongStream> mapper);

DoubleStream flatMapToDouble(
        Function<? super T, ? extends DoubleStream> mapper);
```

Các chữ ký trên minh họa những phương thức riêng của `Stream<T>`. `mapper` nhận **một phần tử `T`** và trả về **một Stream nguyên thủy**, thay vì trả về trực tiếp một số.

| Phương thức trên `Stream<T>` | Mapper trả về | Kết quả của thao tác | Ví dụ nguồn thường gặp |
| --- | --- | --- | --- |
| `flatMapToInt(...)` | `IntStream` | `IntStream` | `int[]`, danh sách số lượng sản phẩm |
| `flatMapToLong(...)` | `LongStream` | `LongStream` | `long[]`, danh sách thời lượng hoặc mã lớn |
| `flatMapToDouble(...)` | `DoubleStream` | `DoubleStream` | `double[]`, chuỗi số đo |

Quá trình diễn ra về mặt logic như sau:

1. Pipeline lấy một phần tử từ Stream ngoài.
2. `mapper` tạo Stream con thuộc đúng kiểu primitive.
3. Các giá trị từ Stream con được đưa vào kết quả đã trải phẳng.
4. Pipeline tiếp tục với phần tử tiếp theo của Stream ngoài khi cần.

Đây là những thao tác **trung gian lazy**. Việc viết `source.stream().flatMapToInt(...)` mới dựng pipeline; terminal operation mới kích hoạt việc duyệt.

Theo hợp đồng API, **Stream con do mapper trả về được đóng sau khi nội dung của nó được đưa vào Stream kết quả**. Mapper trả về `null` được xem như trả về Stream rỗng, tuy vậy nên trả về `IntStream.empty()`, `LongStream.empty()` hoặc `DoubleStream.empty()` một cách tường minh để làm rõ ý định.

Các hàm mapper phải **không can thiệp vào nguồn** (*non-interfering*) và **không phụ thuộc trạng thái mutable thay đổi khi xử lý các phần tử khác** (*stateless*).

## 3. flatMapToInt: nối nhiều dãy int

Giả sử mỗi nhóm có số lượng đơn hàng riêng:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<int[]> orderCounts = List.of(
        new int[] {2, 3},
        new int[] {4},
        new int[] {}
);

int[] allCounts = orderCounts.stream()
        .flatMapToInt(group -> Arrays.stream(group))
        .toArray();

System.out.println(Arrays.toString(allCounts)); // [2, 3, 4]
```

Trong ví dụ, nguồn có kiểu `Stream<int[]>`. Hàm `Arrays.stream(int[])` tạo `IntStream` cho từng mảng; `flatMapToInt` nối các Stream con thành một `IntStream`. Mảng rỗng không sinh phần tử nào.

Có thể dùng method reference:

```java
int total = orderCounts.stream()
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 9
```

`sum()` là terminal operation của `IntStream`. Nếu chỉ cần tổng, không nhất thiết phải gọi `toArray()` và giữ toàn bộ kết quả trong bộ nhớ.

### Một phần tử đầu vào có thể sinh 0, 1 hoặc nhiều số

Mapper có thể quyết định số phần tử đầu ra theo điều kiện:

```java
record Group(boolean enabled, int[] numbers) {}

List<Group> groups = List.of(
        new Group(true, new int[] {1, 2}),
        new Group(false, new int[] {100}),
        new Group(true, new int[] {7})
);

int[] enabledNumbers = groups.stream()
        .flatMapToInt(group -> group.enabled()
                ? Arrays.stream(group.numbers())
                : IntStream.empty())
        .toArray();

System.out.println(Arrays.toString(enabledNumbers)); // [1, 2, 7]
```

Điều kiện có thể đặt ngoài mapper nếu nó là thuộc tính của phần tử nguồn:

```java
int[] sameResult = groups.stream()
        .filter(Group::enabled)
        .flatMapToInt(group -> Arrays.stream(group.numbers()))
        .toArray();
```

Trong trường hợp này, `filter` trước `flatMapToInt` thể hiện rõ rằng ta loại **cả nhóm**, sau đó trải phẳng những nhóm được chọn.

## 4. flatMapToLong: xử lý dãy số long

`long` phù hợp với những giá trị nguyên vượt phạm vi `int`, chẳng hạn mã định danh dạng số hoặc số lượng mili giây lớn. Ví dụ, các lô dữ liệu chứa ID sự kiện:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.LongStream;

record EventBatch(String name, long[] ids) {}

List<EventBatch> batches = List.of(
        new EventBatch("A", new long[] {2_147_483_648L, 3_000_000_000L}),
        new EventBatch("B", new long[] {}),
        new EventBatch("C", new long[] {4_000_000_000L})
);

long[] eventIds = batches.stream()
        .flatMapToLong(batch -> Arrays.stream(batch.ids()))
        .toArray();

System.out.println(Arrays.toString(eventIds));
// [2147483648, 3000000000, 4000000000]
```

Các số trên lớn hơn giới hạn của `int` nhưng vẫn nằm trong miền của `long`. Hậu tố `L` trong literal Java làm rõ kiểu dữ liệu.

Cũng có thể tính tổng thời lượng theo đơn vị mili giây:

```java
List<long[]> durationsBySession = List.of(
        new long[] {1_200L, 800L},
        new long[] {3_000L}
);

long totalMillis = durationsBySession.stream()
        .flatMapToLong(Arrays::stream)
        .sum();

System.out.println(totalMillis); // 5000
```

**Chú ý phạm vi số:** `LongStream.sum()` vẫn có thể tràn `long` khi tổng vượt `Long.MAX_VALUE` hoặc dưới `Long.MIN_VALUE`. Việc chọn `flatMapToLong` không tự tạo ra số nguyên có độ chính xác vô hạn; với yêu cầu tổng rất lớn, cân nhắc `BigInteger` và chiến lược reduction tương ứng.

## 5. flatMapToDouble: trải phẳng các mẫu đo

Với số thực, có thể dùng `DoubleStream` để tính trung bình, tổng, cực trị và thống kê:

```java
import java.util.Arrays;
import java.util.List;
import java.util.DoubleSummaryStatistics;

record SensorBatch(String sensorId, double[] readings) {}

List<SensorBatch> readingsBySensor = List.of(
        new SensorBatch("S1", new double[] {1.5, 2.5}),
        new SensorBatch("S2", new double[] {}),
        new SensorBatch("S3", new double[] {3.0})
);

DoubleSummaryStatistics statistics = readingsBySensor.stream()
        .flatMapToDouble(batch -> Arrays.stream(batch.readings()))
        .summaryStatistics();

System.out.println(statistics.getCount());   // 3
System.out.println(statistics.getSum());     // 7.0
System.out.println(statistics.getAverage()); // xấp xỉ 2.3333333333333335
```

`summaryStatistics()` thực hiện một lần duyệt để thu thập số lượng, tổng, min, max và trung bình. Một lựa chọn đơn giản hơn:

```java
double average = readingsBySensor.stream()
        .flatMapToDouble(batch -> Arrays.stream(batch.readings()))
        .average()
        .orElse(Double.NaN);
```

`average()` trả về `OptionalDouble` vì có thể không có mẫu nào sau khi làm phẳng. Ở ví dụ này, `Double.NaN` được chọn để **biểu thị không có giá trị trung bình** thay vì âm thầm đưa ra số 0; ứng dụng có thể chọn cách xử lý khác.

### NaN, Infinity và độ chính xác số thực

`DoubleStream` không tự bỏ `NaN` hay giá trị vô hạn. Với dữ liệu đo cần thống kê hữu hạn, hãy lọc tường minh:

```java
double[] readings = {2.5, Double.NaN, 4.0, Double.POSITIVE_INFINITY};

double finiteAverage = Arrays.stream(readings)
        .filter(Double::isFinite)
        .average()
        .orElse(Double.NaN);

System.out.println(finiteAverage); // 3.25
```

Phép toán `double` có sai số biểu diễn và phép cộng không kết hợp tuyệt đối; trong xử lý song song, thứ tự kết hợp có thể thay đổi một vài chữ số thập phân. Với **tiền tệ** hoặc yêu cầu thập phân chính xác, nên dùng `BigDecimal` và mô hình thu thập phù hợp thay vì `DoubleStream`.

## 6. So sánh mapToInt, flatMapToInt và flatMap

Đây là khác biệt quan trọng nhất khi đọc chữ ký phương thức:

| Phương thức trên `Stream<T>` | Mỗi phần tử `T` sinh | Kiểu kết quả | Khi dùng |
| --- | --- | --- | --- |
| `mapToInt(ToIntFunction<T>)` | **Đúng một** `int` | `IntStream` | Tính chiều dài chuỗi, lấy một số lượng của mỗi đơn hàng. |
| `flatMapToInt(Function<T, IntStream>)` | **0 đến nhiều** `int` | `IntStream` | Mỗi nhóm chứa nhiều số nguyên cần trải phẳng. |
| `map(Function<T, R>)` | **Đúng một** giá trị `R` | `Stream<R>` | Biến đổi một đối tượng thành một đối tượng khác. |
| `flatMap(Function<T, Stream<R>>)` | **0 đến nhiều** `R` | `Stream<R>` | Trải phẳng dữ liệu đối tượng, ví dụ tên từ nhiều nhóm. |

Chữ ký ở bảng được viết ngắn gọn để so sánh, không thể hiện đầy đủ wildcard generic.

Xét một nguồn gồm hai mảng:

```java
List<int[]> blocks = List.of(
        new int[] {3, 5},
        new int[] {7}
);

int[] lengths = blocks.stream()
        .mapToInt(block -> block.length)
        .toArray();
// [2, 1]: mỗi mảng sinh đúng một độ dài

int[] values = blocks.stream()
        .flatMapToInt(Arrays::stream)
        .toArray();
// [3, 5, 7]: mỗi mảng sinh các số bên trong
```

Sai lầm dễ gặp là dùng `map` khi mapper trả về Stream con:

```java
Stream<IntStream> nested = blocks.stream()
        .map(Arrays::stream);

// nested chứa hai IntStream, chưa phải luồng int đã làm phẳng.
```

Để lấy số nguyên trực tiếp, dùng `flatMapToInt`. Nếu dữ liệu nguồn đã là những danh sách `List<Integer>` thay vì mảng, có thể viết:

```java
List<List<Integer>> nestedLists = List.of(
        List.of(3, 5),
        List.of(),
        List.of(7)
);

int[] flattened = nestedLists.stream()
        .flatMapToInt(list -> list.stream()
                .mapToInt(Integer::intValue))
        .toArray();

System.out.println(Arrays.toString(flattened)); // [3, 5, 7]
```

Ở ví dụ sau, `List<Integer>` đã lưu các số dưới dạng đối tượng boxed. `flatMapToInt` giúp pipeline đầu ra làm việc với `int` nhưng **không loại bỏ chi phí boxing đã có trong cấu trúc đầu vào**. Với dữ liệu số lớn và đặc biệt nhạy hiệu năng, cấu trúc `int[]` hoặc primitive stream có thể hợp lý hơn.

Tương ứng với `long` và `double`, thao tác ánh xạ một-một là `mapToLong` và `mapToDouble`; thao tác làm phẳng là `flatMapToLong` và `flatMapToDouble`.

## 7. Đừng nhầm với flatMap trên primitive stream

Nhóm phương thức `flatMapToX` **chỉ nằm trên `Stream<T>` đầu vào dạng đối tượng**. Nếu đã có `IntStream`, bạn sử dụng `IntStream.flatMap`:

```java
int[] values = IntStream.of(1, 3)
        .flatMap(n -> IntStream.rangeClosed(1, n))
        .toArray();

System.out.println(Arrays.toString(values)); // [1, 1, 2, 3]
```

Tương tự:

- `LongStream.flatMap(LongFunction<? extends LongStream>)` làm phẳng `LongStream` thành `LongStream`.
- `DoubleStream.flatMap(DoubleFunction<? extends DoubleStream>)` làm phẳng `DoubleStream` thành `DoubleStream`.

Không thể gọi `flatMapToInt` trên một `IntStream` vì phương thức đó không thuộc API của nó. Có thể chuyển giữa các kiểu primitive bằng những phương thức phù hợp, như `IntStream.asLongStream()`, `IntStream.asDoubleStream()`, `LongStream.mapToDouble(...)` hoặc `IntStream.boxed()` khi thật sự cần quay lại Stream đối tượng.

## 8. Kết hợp filter, flatMapToX và các phép tổng hợp

Vị trí của `filter` quyết định **lọc nhóm trước** hay **lọc các số sau khi trải phẳng**.

Giả sử chỉ muốn lấy số lượng ở những nhóm còn hoạt động, và trong mỗi nhóm chỉ giữ số lượng dương:

```java
record InventoryGroup(boolean active, int[] quantities) {}

List<InventoryGroup> inventory = List.of(
        new InventoryGroup(true, new int[] {3, 0, -1, 5}),
        new InventoryGroup(false, new int[] {100}),
        new InventoryGroup(true, new int[] {2})
);

int[] acceptedQuantities = inventory.stream()
        .filter(InventoryGroup::active)             // Lọc theo nhóm
        .flatMapToInt(group -> Arrays.stream(group.quantities()))
        .filter(quantity -> quantity > 0)           // Lọc theo từng số
        .toArray();

System.out.println(Arrays.toString(acceptedQuantities)); // [3, 5, 2]
```

Về ý nghĩa:

1. `filter` trên `Stream<InventoryGroup>` có thể loại toàn bộ nhóm không hoạt động mà chưa cần tạo Stream con.
2. `flatMapToInt` nối các mảng `quantities` của nhóm còn lại.
3. `filter` trên `IntStream` chỉ giữ các số dương.

Sau khi làm phẳng, các terminal operation thường dùng gồm:

| Terminal operation | Trả về | Mục đích |
| --- | --- | --- |
| `sum()` | `int`/`long`/`double` tương ứng | Cộng toàn bộ giá trị. |
| `average()` | `OptionalDouble` | Trung bình, có thể rỗng. |
| `count()` | `long` | Đếm các số sau làm phẳng. |
| `min()`, `max()` | `OptionalInt`/`OptionalLong`/`OptionalDouble` | Cực trị. |
| `summaryStatistics()` | `IntSummaryStatistics`/`LongSummaryStatistics`/`DoubleSummaryStatistics` | Thống kê nhiều đại lượng trong một lượt duyệt. |
| `toArray()` | `int[]`, `long[]` hoặc `double[]` | Lưu toàn bộ kết quả khi thật sự cần. |

Một Stream đã được tiêu thụ bởi terminal operation thì không được dùng lại. Nếu cần cả `sum` và `max` trên cùng bộ dữ liệu, có thể gọi `summaryStatistics()` một lần hoặc dựng **pipeline mới từ nguồn**.

## 9. Ánh xạ từ chuỗi thô thành nhiều số

Không phải nguồn nào cũng chứa sẵn primitive array. Chẳng hạn, mỗi dòng CSV chứa một nhóm số:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> rows = List.of("12, 8", "", "5, 9, 10");

int[] numbers = rows.stream()
        .flatMapToInt(row -> {
            if (row.isBlank()) {
                return IntStream.empty();
            }
            return Arrays.stream(row.split(","))
                    .map(String::trim)
                    .mapToInt(Integer::parseInt);
        })
        .toArray();

System.out.println(Arrays.toString(numbers)); // [12, 8, 5, 9, 10]
```

Đây là pipeline qua nhiều lớp: `Stream<String>` của các dòng → `Stream<String>` của các token trong mỗi dòng → `IntStream` sau parse → một `IntStream` phẳng.

**Giới hạn của ví dụ:** `Integer.parseInt` ném `NumberFormatException` nếu token không hợp lệ hoặc số nằm ngoài phạm vi `int`. `flatMapToInt` không tự bỏ token sai.

Nếu yêu cầu **bỏ qua token không parse được**, có thể thể hiện chính sách bằng một hàm:

```java
static IntStream parseIfValid(String token) {
    try {
        return IntStream.of(Integer.parseInt(token.trim()));
    } catch (NumberFormatException exception) {
        return IntStream.empty();
    }
}

// Ví dụ đặt trong cùng lớp chứa parseIfValid:
int[] accepted = List.of("3", "abc", "7").stream()
        .flatMapToInt(MyClass::parseIfValid)
        .toArray();

// [3, 7]
```

Trong minh họa, thay `MyClass` bằng tên lớp chứa `parseIfValid`. Việc bỏ qua dữ liệu sai chỉ phù hợp khi nghiệp vụ cho phép; nếu cần kiểm toán, hãy giữ lại token lỗi và nguyên nhân trong một cấu trúc báo cáo riêng.

Với số `long`, dùng `Long.parseLong` để tạo `LongStream`; với `double`, dùng `Double.parseDouble` và quyết định rõ có chấp nhận `NaN` hoặc vô hạn không.

## 10. Nguồn null, Stream rỗng và quy tắc xử lý dữ liệu thiếu

Primitive stream không chứa tham chiếu `null`, nhưng **nguồn đối tượng** vẫn có thể có phần tử `null` hoặc trường mảng `null`.

```java
record Packet(int[] values) {}

List<Packet> packets = java.util.Arrays.asList(
        new Packet(new int[] {1, 2}),
        new Packet(null),
        null,
        new Packet(new int[] {})
);

int[] valid = packets.stream()
        .filter(java.util.Objects::nonNull)
        .flatMapToInt(packet -> packet.values() == null
                ? IntStream.empty()
                : Arrays.stream(packet.values()))
        .toArray();

System.out.println(Arrays.toString(valid)); // [1, 2]
```

Ở đây có hai quyết định:

- `filter(Objects::nonNull)` bỏ **phần tử Packet null** từ nguồn.
- `IntStream.empty()` biểu diễn **Packet hợp lệ nhưng không có dãy số**.

Nếu mapper trả về `null`, `flatMapToInt` xem như Stream rỗng theo hợp đồng; dùng `empty()` vẫn dễ hiểu và tránh mã mơ hồ hơn.

Với primitive stream đầu ra, không cần `filter(Objects::nonNull)` sau `flatMapToInt` vì kiểu `int` không thể là `null`. Cũng không nên tự ý biến dữ liệu thiếu thành số `0` trừ khi đó thật sự là quy tắc nghiệp vụ.

## 11. Lazy, tài nguyên và vòng đời Stream con

Các thao tác `flatMapToInt`, `flatMapToLong`, `flatMapToDouble` đều lazy: chúng không cần dựng trước một danh sách chứa toàn bộ giá trị trải phẳng. Việc duyệt được dẫn dắt bởi terminal operation.

```java
Stream<int[]> pipeline = Stream.of(
        new int[] {1, 2},
        new int[] {3}
);

IntStream flattened = pipeline.flatMapToInt(values -> {
    System.out.println("Tạo IntStream con");
    return Arrays.stream(values);
});

// Chưa có terminal operation nên chưa bắt đầu làm phẳng.
int[] result = flattened.toArray(); // Kích hoạt xử lý.
```

Điểm mạnh của lazy pipeline là có thể xử lý giá trị theo nhu cầu mà không lưu toàn bộ kết quả. Các terminal operation như `findFirst` và `limit` cho phép **dừng sớm** trong nhiều pipeline:

```java
int[] firstThree = Stream.of(
                new int[] {4, 5},
                new int[] {6, 7, 8}
        )
        .flatMapToInt(Arrays::stream)
        .limit(3)
        .toArray();

System.out.println(Arrays.toString(firstThree)); // [4, 5, 6]
```

Tuy nhiên, **không được dựa vào số lần mapper được gọi, thứ tự gọi hoặc tác dụng phụ**. Tối ưu của pipeline, đặc điểm nguồn và xử lý song song có thể ảnh hưởng mức độ xử lý trước khi dừng. Đặc biệt nên thận trọng với một Stream con vô hạn hoặc nguồn đầu vào có thể chặn: đừng giả định mọi terminal operation đều hoàn thành ngay.

### Ai chịu trách nhiệm đóng Stream?

`flatMapToX` đóng **Stream con do mapper cung cấp** sau khi sử dụng chúng theo hợp đồng. Nhưng nếu **Stream ngoài** được tạo từ tài nguyên cần đóng (ví dụ `Files.lines`), vẫn phải quản lý tài nguyên ngoài bằng `try-with-resources`:

```java
// Ví dụ định hướng: lines là một Stream<String> liên kết với tệp.
// try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
//     long count = lines.flatMapToInt(MyClass::parseLineToInts).count();
// }
```

Đóng Stream con tự động không thay thế việc quản lý nguồn, luồng I/O hoặc kết nối từ các lớp khác. Tránh tự tái sử dụng một Stream con cho nhiều phần tử đầu vào: Stream chỉ nên được tiêu thụ một lần.

## 12. Trạng thái dùng chung, song song và hiệu năng

### Mapper phải không can thiệp và không trạng thái

Một cách viết sai là cập nhật chính collection nguồn trong mapper:

```java
List<int[]> source = new java.util.ArrayList<>();
source.add(new int[] {1, 2});
source.add(new int[] {3});

// SAI: sửa source trong khi source.stream() đang duyệt.
int[] invalid = source.stream()
        .flatMapToInt(group -> {
            source.add(new int[] {99});
            return Arrays.stream(group);
        })
        .toArray();
```

Ví dụ này vi phạm **non-interference**; có thể dẫn đến `ConcurrentModificationException` hoặc hành vi không đáng tin cậy. Tương tự, mapper phụ thuộc vào biến đếm dùng chung cũng không phù hợp với hợp đồng stateless và khó dự đoán khi chạy song song.

Nếu cần cập nhật nguồn, hoàn tất terminal operation trước rồi thực hiện cập nhật trong một giai đoạn riêng.

### Khi nào cần parallel?

`parallelStream()` có thể phân việc trên nhiều thread, nhưng không phải luôn nhanh:

```java
long total = durationsBySession.parallelStream()
        .flatMapToLong(Arrays::stream)
        .sum();
```

Giá trị số học nguyên hợp lệ có thể được tổng hợp từ nhiều nhánh, nhưng độ lớn dữ liệu, chi phí tạo Stream con và việc chia tách nguồn quyết định hiệu năng. Với rất nhiều nhóm cực nhỏ, chi phí mapper và điều phối có thể lớn hơn phần tính toán.

Nếu Stream ngoài có encounter order và mỗi Stream con cũng có thứ tự, các phần tử của kết quả phẳng giữ thứ tự logic của các nhóm trong những thao tác yêu cầu thứ tự, chẳng hạn `toArray()`. **Thứ tự thực thi của mapper** trên các thread lại không được bảo đảm. Với phép cộng `double`, thay đổi thứ tự tính có thể làm kết quả khác chút ít vì sai số dấu phẩy động.

### Boxing, Stream con và mapMultiToX

Việc dùng primitive stream giúp tránh boxed values **ở phần pipeline kết quả**. Nó không biến một `List<Integer>` thành mảng primitive miễn phí.

Với ánh xạ một-một, nên dùng `mapToInt` thay vì viết `flatMapToInt(x -> IntStream.of(...))` chỉ để tạo đúng một số, vì cách sau phải tạo Stream con.

Khi mỗi phần tử sinh ít số và việc tạo nhiều Stream con trở thành điểm nghẽn, Java 16+ còn có `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble`. Các phương thức này đưa giá trị trực tiếp cho consumer:

```java
List<int[]> groups = List.of(
        new int[] {2, 3},
        new int[] {},
        new int[] {4}
);

int[] flattened = groups.stream()
        .mapMultiToInt((group, consumer) -> {
            for (int value : group) {
                consumer.accept(value);
            }
        })
        .toArray();

System.out.println(Arrays.toString(flattened)); // [2, 3, 4]
```

`mapMultiToX` là một lựa chọn đáng cân nhắc khi cần phát 0 đến nhiều giá trị mà không muốn tạo Stream con; hãy ưu tiên cách diễn đạt rõ ràng, sau đó đo hiệu năng trên khối lượng dữ liệu thực tế.

## 13. Ví dụ hoàn chỉnh: thống kê các lô vận chuyển

Bài toán: mỗi lô có danh sách số lượng kiện (`int[]`), quãng đường từng chặng tính bằng mét (`long[]`) và các mẫu khối lượng (`double[]`). Chỉ tính những lô được chấp nhận, sau đó tạo ba thống kê độc lập.

Ví dụ chạy được trên Java 17+:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

public class PrimitiveFlatMapDemo {
    record Batch(
            String id,
            boolean accepted,
            int[] itemCounts,
            long[] distancesMeters,
            double[] weightsKg
    ) {}

    public static void main(String[] args) {
        List<Batch> batches = List.of(
                new Batch("B01", true,
                        new int[] {2, 3},
                        new long[] {1_200L, 800L},
                        new double[] {1.0, 2.0}),
                new Batch("B02", false,
                        new int[] {100},
                        new long[] {99_999L},
                        new double[] {99.0}),
                new Batch("B03", true,
                        new int[] {4},
                        new long[] {3_000L},
                        new double[] {3.0}),
                new Batch("B04", true,
                        new int[] {},
                        new long[] {},
                        new double[] {})
        );

        int totalItems = batches.stream()
                .filter(Batch::accepted)
                .flatMapToInt(batch -> Arrays.stream(batch.itemCounts()))
                .sum();

        long totalDistance = batches.stream()
                .filter(Batch::accepted)
                .flatMapToLong(batch -> Arrays.stream(batch.distancesMeters()))
                .sum();

        DoubleSummaryStatistics weightStats = batches.stream()
                .filter(Batch::accepted)
                .flatMapToDouble(batch -> Arrays.stream(batch.weightsKg()))
                .summaryStatistics();

        System.out.println("Tổng số kiện: " + totalItems);         // 9
        System.out.println("Tổng quãng đường (m): " + totalDistance); // 5000
        System.out.println("Số mẫu khối lượng: " + weightStats.getCount()); // 3
        System.out.println("Khối lượng TB (kg): " + weightStats.getAverage()); // 2.0
    }
}
```

Lý do chọn cách viết:

1. `filter(Batch::accepted)` loại hoàn toàn lô `B02` trước khi trải phẳng.
2. `flatMapToInt` nối các mảng số kiện, rồi `sum` tính tổng là `9`.
3. `flatMapToLong` nối các quãng đường `long`, rồi `sum` cho kết quả `5000` mét.
4. `flatMapToDouble` nối các mẫu khối lượng và `summaryStatistics` thống kê ba mẫu với trung bình `2.0` kg.
5. Lô `B04` chứa ba mảng rỗng và không sinh số nào; chương trình vẫn hoạt động bình thường.
6. Mỗi phép thống kê tạo **pipeline mới từ danh sách nguồn**, thay vì cố dùng lại một Stream đã bị terminal operation tiêu thụ.

Ở ứng dụng thật, nếu cần ba thống kê với một lượt duyệt dữ liệu, có thể xây dựng collector/accumulator riêng hoặc vòng lặp được thiết kế và kiểm soát rõ ràng. Các pipeline độc lập ở đây ưu tiên dễ đọc và thể hiện đúng chức năng của từng `flatMapToX`.

## 14. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không gọi được `flatMapToInt` | Nguồn hiện là `IntStream`, không còn `Stream<T>`. | Dùng `IntStream.flatMap` hoặc xem lại kiểu của pipeline. |
| Lambda trả về một `int` thay vì `IntStream` | Nhầm `flatMapToInt` với `mapToInt`. | Trả về `IntStream` hoặc đổi sang `mapToInt` cho ánh xạ một-một. |
| Kết quả là `Stream<IntStream>` | Đã gọi `map(x -> IntStream...)`. | Dùng `flatMapToInt` để trải phẳng. |
| `NumberFormatException` khi đọc token | Không kiểm tra dữ liệu đầu vào trước `parseInt`. | Xác định chính sách báo lỗi hoặc bỏ token sai. |
| `NullPointerException` khi gọi `Arrays.stream` | Mảng/trường trong nguồn là `null`. | Kiểm tra và dùng primitive stream rỗng khi phù hợp. |
| Không gọi được `toList()` trên `IntStream` | Primitive stream không có `Stream.toList()`. | Dùng `toArray()` hoặc `boxed().toList()`. |
| Kết quả trung bình không có giá trị | Không có số nào sau làm phẳng. | Xử lý `OptionalDouble` theo nghiệp vụ. |
| Tổng `int`/`long` sai khi dữ liệu quá lớn | Tràn phạm vi kiểu nguyên. | Chọn mô hình số có phạm vi phù hợp; kiểm tra overflow. |
| Tổng hoặc trung bình `double` lệch nhỏ | Giới hạn độ chính xác số thực và thứ tự cộng. | Xác định sai số chấp nhận, dùng `BigDecimal` nếu cần. |
| Pipeline song song chậm hơn | Chi phí chia việc/ghép và tạo nhiều Stream con. | Đo thực tế; cân nhắc tuần tự hoặc `mapMultiToX`. |
| Dữ liệu nguồn bị thay đổi bất ngờ | Mapper có tác dụng phụ lên nguồn hoặc đối tượng chia sẻ. | Giữ mapper không trạng thái, chỉ đọc nguồn. |

## 15. Bài tập thực hành

Cho dữ liệu:

```java
List<String> integerRows = List.of("1,2,3", "", "4,5");

List<long[]> sessions = List.of(
        new long[] {1_000L, 2_000L},
        new long[] {},
        new long[] {3_000L}
);

List<double[]> grades = List.of(
        new double[] {7.5, 8.0},
        new double[] {},
        new double[] {9.5}
);
```

**Yêu cầu:**

1. Dùng `flatMapToInt` đọc các số từ `integerRows` và tạo `int[]` theo đúng thứ tự.
2. Dùng `flatMapToLong` tính tổng các khoảng thời gian trong `sessions`.
3. Dùng `flatMapToDouble` tính trung bình các điểm trong `grades`.
4. Giải thích vì sao `mapToLong(session -> session.length)` không thay thế `flatMapToLong(Arrays::stream)` trong câu 2.
5. Nếu một `grades` entry là mảng rỗng, nó ảnh hưởng thế nào đến số mẫu và trung bình?

**Lời giải tham khảo:**

```java
int[] allIntegers = integerRows.stream()
        .flatMapToInt(row -> row.isEmpty()
                ? IntStream.empty()
                : Arrays.stream(row.split(","))
                        .mapToInt(Integer::parseInt))
        .toArray();
// [1, 2, 3, 4, 5]

long totalTime = sessions.stream()
        .flatMapToLong(Arrays::stream)
        .sum();
// 6000

double gradeAverage = grades.stream()
        .flatMapToDouble(Arrays::stream)
        .average()
        .orElse(Double.NaN);
// (7.5 + 8.0 + 9.5) / 3 = 8.333333333333334 (xấp xỉ)
```

Ở câu 4, `mapToLong(session -> session.length)` tạo một số bằng **độ dài mảng** cho mỗi session, nên tổng chỉ phản ánh số lượng phần tử; `flatMapToLong` phát ra các thời lượng **bên trong mảng** để cộng chúng. Ở câu 5, mảng rỗng không tạo mẫu nào; mẫu số để tính trung bình vẫn là ba giá trị `7.5`, `8.0` và `9.5`.

## Ghi nhớ

`flatMapToInt`, `flatMapToLong` và `flatMapToDouble` làm phẳng các Stream con thuộc kiểu primitive từ mỗi phần tử của một `Stream<T>`. Chọn phương thức theo kiểu số đầu ra; mỗi đầu vào có thể sinh **0, 1 hoặc nhiều số**. Kết quả có thể dùng trực tiếp với `sum`, `average`, `summaryStatistics` hoặc `toArray` mà không cần boxing lại. `mapToX` chỉ phù hợp khi mỗi phần tử sinh đúng một số, còn khi nguồn đã là primitive stream thì sử dụng `flatMap` tương ứng.

Hãy làm rõ cách xử lý dữ liệu rỗng hoặc sai, giữ mapper stateless và không can thiệp nguồn, quản lý nguồn I/O đúng vòng đời, tránh dùng lại Stream đã tiêu thụ. Với bài toán nặng, cân nhắc độ chính xác số, chi phí tạo Stream con, khả năng chạy song song và `mapMultiToX` khi cần tối ưu có căn cứ.
