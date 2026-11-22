# Tạo Stream bằng `StreamSupport` trong Java

## 1. Khi nào cần `StreamSupport`?

Hầu hết chương trình Java lấy Stream từ những nguồn có sẵn:

```java
List<String> names = List.of("Lan", "Minh", "An");
Stream<String> namesStream = names.stream();

IntStream numbers = IntStream.rangeClosed(1, 5);
Stream<String> codes = Stream.of("A01", "A02");
```

Nhưng có những trường hợp dữ liệu **không phải một `Collection`** có sẵn `stream()`: một `Iterable` tùy chỉnh, một `Iterator` từ thư viện cũ, một kiểu dữ liệu tự quản lý cấu trúc, một dãy tính toán theo quy luật riêng, hoặc nguồn mà bạn muốn kiểm soát khả năng chia công việc khi xử lý song song.

`java.util.stream.StreamSupport` là lớp tiện ích để xây Stream từ **`Spliterator`** — đối tượng mô tả cách đi qua các phần tử và, khi có thể, chia nguồn ra các phần nhỏ.

Ví dụ phổ biến:

```java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Stream<String> result =
        StreamSupport.stream(iterable.spliterator(), false);
```

Ở đây `iterable` được giả định đã khai báo và cung cấp một `Spliterator<String>`. Tham số `false` chỉ định tạo **stream tuần tự**. Để hiểu cách xây nguồn tốt và tránh lỗi khó phát hiện, cần nắm ba thành phần:

- **Nguồn dữ liệu:** phần tử đến từ đâu, có sẵn trong bộ nhớ hay được sinh khi cần?
- **`Spliterator<T>`:** làm thế nào để đi qua phần tử tiếp theo, ước lượng kích thước và (nếu phù hợp) chia nguồn?
- **`StreamSupport`:** nối `Spliterator` vào Stream pipeline; các phép `filter`, `map`, `flatMap`, `collect` vẫn hoạt động như thông thường.

**Quan trọng:** `StreamSupport` không phải thư viện mới để tự động biến mọi `Iterator` thành cấu trúc chạy song song hiệu quả. Chất lượng, tính đúng đắn và đặc tính nguồn phụ thuộc vào `Spliterator` bạn cung cấp.

## 2. Các overload quan trọng

`StreamSupport` có các overload cho object stream và ba loại primitive stream:

```java
// Stream đối tượng:
static <T> Stream<T> stream(
        Spliterator<T> spliterator, boolean parallel);

static <T> Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel);

// IntStream:
static IntStream intStream(
        Spliterator.OfInt spliterator, boolean parallel);

static IntStream intStream(
        Supplier<? extends Spliterator.OfInt> supplier,
        int characteristics,
        boolean parallel);

// LongStream:
static LongStream longStream(
        Spliterator.OfLong spliterator, boolean parallel);

static LongStream longStream(
        Supplier<? extends Spliterator.OfLong> supplier,
        int characteristics,
        boolean parallel);

// DoubleStream:
static DoubleStream doubleStream(
        Spliterator.OfDouble spliterator, boolean parallel);

static DoubleStream doubleStream(
        Supplier<? extends Spliterator.OfDouble> supplier,
        int characteristics,
        boolean parallel);
```

Đây là bản trình bày chữ ký API theo Java 17, không phải mã có thể dán ngoài lớp để biên dịch độc lập.

**Tham số `parallel`**:

- `false`: tạo Stream tuần tự theo mặc định.
- `true`: tạo Stream có chế độ parallel. Tính song song hiệu quả hay không phụ thuộc cách `Spliterator.trySplit()` phân chia dữ liệu, đặc tính của pipeline, độ lớn nguồn và workload.

**Hai cách cung cấp nguồn**:

1. Truyền **`Spliterator` đã có**.
2. Truyền **`Supplier<Spliterator>` và tập `characteristics`** để trì hoãn việc lấy Spliterator cho đến khi terminal operation bắt đầu.

Overload supplier đặc biệt có ích khi muốn **giới hạn thời gian từ lúc nguồn bị ràng buộc đến lúc duyệt**, giúp giảm cửa sổ can thiệp của nguồn có thể thay đổi. Nhưng nó không tự đảm bảo thread-safe hay chống lại mọi sửa đổi đồng thời.

## 3. `Spliterator` là gì?

Tên `Spliterator` ghép từ *splittable iterator*: một đối tượng có thể tiến qua phần tử và, nếu hỗ trợ, chia một phần nguồn cho xử lý song song.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `tryAdvance(Consumer<? super T> action)` | Nếu còn phần tử, áp dụng action lên **một** phần tử và trả `true`; nếu hết, trả `false` |
| `forEachRemaining(Consumer<? super T> action)` | Duyệt các phần tử còn lại |
| `trySplit()` | Cố tách một phần nguồn thành Spliterator khác, hoặc trả `null` nếu không tách được |
| `estimateSize()` | Ước lượng số phần tử còn lại; có thể là `Long.MAX_VALUE` nếu không biết |
| `characteristics()` | Bit flags mô tả những thuộc tính được đảm bảo của nguồn |
| `hasCharacteristics(flags)` | Kiểm tra một hoặc nhiều thuộc tính |
| `getExactSizeIfKnown()` | Trả kích thước chính xác nếu có `SIZED`, ngược lại `-1` |
| `getComparator()` | Có ý nghĩa với nguồn mang `SORTED`; nếu sorted theo thứ tự tự nhiên thì trả `null` |

`Spliterator` không nhất thiết biết tất cả phần tử từ trước. Ví dụ một `Spliterator.OfInt` có thể tự sinh số 1,2,3... khi được hỏi, thay vì lưu số vào `ArrayList`.

### Thao tác một phần tử bằng `tryAdvance`

```java
Spliterator<String> spliterator =
        List.of("A", "B").spliterator();

boolean first = spliterator.tryAdvance(System.out::println);
boolean second = spliterator.tryAdvance(System.out::println);
boolean third = spliterator.tryAdvance(System.out::println);

System.out.println(first + "/" + second + "/" + third);
```

Output:

```text
A
B
true/true/false
```

Đoạn này được đặt trong phương thức có `import java.util.*;`. Mỗi lời gọi `tryAdvance` tiêu thụ tối đa một phần tử. Sau khi hai phần tử đã được duyệt, lần gọi thứ ba trả `false` và không gọi action.

**Cảnh báo:** đừng tự gọi `tryAdvance` trên một Spliterator rồi đưa **chính Spliterator đó** vào Stream mà vẫn kỳ vọng toàn bộ nguồn ban đầu. Nó đã thay đổi vị trí duyệt; Stream sẽ chỉ còn phần tử chưa được tiêu thụ.

## 4. Cách đơn giản: từ `Iterable` sang Stream

`Iterable<T>` có phương thức `spliterator()`. Vì thế, với một biến được khai báo kiểu `Iterable` (không nhất thiết là `Collection`), bạn có thể viết:

```java
Iterable<String> names = List.of("Lan", "Minh", "An");

List<String> result = StreamSupport
        .stream(names.spliterator(), false)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, MINH, AN]
```

Trong ví dụ, đối tượng thực là `List.of(...)` nên `spliterator()` có thứ tự duyệt phù hợp với danh sách.

Tại sao không viết `names.stream()`? Vì **kiểu giao diện `Iterable<T>` không khai báo `stream()`**; `stream()` là phương thức được cung cấp bởi `Collection` và các API tương ứng. Dù object runtime có thể là List, khi biến khai báo `Iterable`, compiler chỉ cho phép gọi những phương thức tồn tại trên `Iterable`.

### Dùng với `Iterable` tự định nghĩa

```java
Iterable<Integer> odds = () ->
        List.of(1, 3, 5, 7).iterator();

List<Integer> values = StreamSupport
        .stream(odds.spliterator(), false)
        .filter(n -> n > 3)
        .toList();

System.out.println(values); // [5, 7]
```

Đây là cách gọn khi một lớp chỉ cung cấp `iterator()`.

**Lưu ý về thứ tự:** default `Iterable.spliterator()` dựa trên `iterator()` và có thể không quảng bá đặc tính `ORDERED` dù iterator thường trả phần tử theo một thứ tự quan sát được. Nếu encounter order là hợp đồng quan trọng, hãy thiết kế/ghi rõ `Spliterator` trả về để khai báo đúng `ORDERED`, hoặc chuyển qua một cấu trúc `List` có thứ tự khi phù hợp.

## 5. Từ `Iterator`: `Spliterators.spliteratorUnknownSize`

`Iterator<T>` **không trực tiếp cung cấp `spliterator()`**. JDK có lớp tiện ích `java.util.Spliterators` để tạo Spliterator từ iterator:

```java
Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> spliterator =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

List<String> values = StreamSupport.stream(spliterator, false)
        .map(String::toLowerCase)
        .toList();

System.out.println(values); // [a, b, c]
```

`spliteratorUnknownSize` có ý nghĩa “kích thước không biết trước”. Nó **không** có đặc tính `SIZED` hoặc `SUBSIZED`, kể cả khi bạn biết rằng Iterator ví dụ cuối cùng đi qua ba phần tử. Nếu dữ liệu gốc thật sự có kích thước xác định, dùng API factory khác phù hợp thay vì cố khai báo SIZED không đúng.

### Iterator thường là nguồn một lần

Sau khi đã tiêu thụ `iterator` bằng Stream, bạn không thể quay lại đầu như List thông thường. Nếu cần nhiều kết quả độc lập, hãy cung cấp một **Iterator mới** mỗi lần hoặc tạo một collection snapshot theo giới hạn bộ nhớ cho phép.

### Phải khai báo flags đúng sự thật

`Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED)` nói rằng phần tử được gặp theo thứ tự iterator. Nếu nguồn lấy từ một nguồn không định nghĩa thứ tự, đừng quảng bá `ORDERED` chỉ để làm output có vẻ xác định.

Không khai báo `DISTINCT` nếu nguồn có thể lặp giá trị, `NONNULL` nếu phần tử có thể null, hoặc `IMMUTABLE` nếu nguồn có thể bị thay đổi trong quá trình duyệt. Flags là **hợp đồng**, không phải gợi ý vô hại.

## 6. Cơ chế lazy: tạo Stream chưa duyệt toàn bộ nguồn

`StreamSupport.stream(...)` trả một stream mà những phép toán trung gian thường **chưa thực hiện** cho đến khi có terminal operation.

```java
Iterable<Integer> source = List.of(2, 4, 6);

Stream<Integer> mapped = StreamSupport
        .stream(source.spliterator(), false)
        .map(n -> n * 10);

// Đến đây chưa phải một List đã tính xong.
List<Integer> values = mapped.toList();

System.out.println(values); // [20, 40, 60]
```

`toList` là terminal operation, làm pipeline được tiêu thụ. Sau khi gọi, không tái sử dụng `mapped`.

**Quan trọng:** tạo Stream bằng overload trực tiếp truyền Spliterator có thể truy cập một số metadata nguồn sớm. Đừng xây code dựa trên giả định tuyệt đối rằng không có bất kỳ phương thức nào của Spliterator bị hỏi trước terminal. Điều nên dựa vào là các phần tử được **duyệt theo mô hình lazy** của Stream pipeline, và overload supplier có bảo đảm riêng về thời điểm gọi supplier.

### `StreamSupport` không tự quản lý tài nguyên

Nếu Spliterator đọc file, socket hay cursor database, Stream chỉ là pipeline duyệt dữ liệu. Bạn phải xác định ai sở hữu tài nguyên và **đóng tài nguyên đúng cách**. Không cho rằng `stream.toList()` hoặc `stream.count()` tự gọi `close()` trên stream; trong JDK, Stream thường không phải tài nguyên cần đóng, nhưng stream gắn tài nguyên I/O có thể yêu cầu `try-with-resources` hoặc `onClose` do nguồn thiết kế.

Ví dụ `Files.lines(path)` là Stream có tài nguyên file và phải đóng bằng `try-with-resources`. Nếu tự xây Spliterator trên nguồn có tài nguyên, cần cung cấp chiến lược đóng nguồn thích hợp; `StreamSupport` không tự đoán cách đóng một cursor tùy chỉnh.

## 7. Các đặc tính `Spliterator` thường gặp

`characteristics()` trả bitmask các cờ. Mỗi cờ mang ý nghĩa để Stream framework lập kế hoạch xử lý:

| Đặc tính | Ý nghĩa chính | Lưu ý thực tế |
| --- | --- | --- |
| `ORDERED` | Nguồn có encounter order được định nghĩa | `forEachOrdered`/`toList` có thể giữ thứ tự |
| `DISTINCT` | Theo `equals`, các phần tử không trùng lặp | Không tự khai nếu nguồn có thể trùng |
| `SORTED` | Các phần tử có thứ tự sắp xếp được xác định | Phải tuân thủ `getComparator()` |
| `SIZED` | Biết chính xác kích thước còn lại trước khi duyệt theo contract | Không khai với nguồn kích thước không ổn định/không biết |
| `SUBSIZED` | Mỗi Spliterator sinh ra bằng `trySplit` cũng là `SIZED` và `SUBSIZED` | Hữu ích cho phân vùng parallel |
| `NONNULL` | Không có phần tử tham chiếu null | Chỉ khai khi thật sự đảm bảo |
| `IMMUTABLE` | Nguồn phần tử không thể bị thay đổi cấu trúc theo cách ảnh hưởng duyệt | Không có nghĩa mọi object phần tử bất biến sâu |
| `CONCURRENT` | Nguồn có cơ chế cho phép cập nhật đồng thời theo hợp đồng | Không gắn tùy tiện cho ArrayList |
| `SORTED` + `ORDERED` | Spliterator SORTED phải ORDERED | Nếu sorted tự nhiên, `getComparator()` trả null |

Các đặc tính là bit flags, ghép bằng toán tử OR `|`:

```java
int characteristics =
        Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED;
```

**Không chỉ khai `SIZED` để làm `count()` nhanh hơn.** Nếu khai sai kích thước, một số tối ưu có thể cho kết quả không đúng hoặc làm lộ bug khó phát hiện. Chỉ khai những tính chất bạn chắc chắn giữ được trong cả hành vi của `tryAdvance`, `trySplit` và quá trình duyệt.

### `SORTED` đòi hỏi hợp đồng bổ sung

Nếu Spliterator khai `SORTED`, nó phải tuân thủ quy tắc `getComparator()`. Trả `null` chỉ khi thứ tự tự nhiên là hợp đồng, hoặc trả comparator tương ứng. Nếu nguồn **không sorted**, đừng khai `SORTED` chỉ vì muốn Stream tự sắp xếp; dùng `stream.sorted(...)` khi có yêu cầu.

## 8. Overload dùng `Supplier<Spliterator<T>>`

Đây là overload:

```java
Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel);
```

Khác với truyền một Spliterator đã có, overload này **trì hoãn việc gọi `supplier.get()` cho tới khi terminal operation bắt đầu**. Vì thế phù hợp khi nguồn được gắn với trạng thái có thể thay đổi và bạn muốn giảm khoảng thời gian giữa lúc lấy Spliterator và lúc dùng nó.

Ví dụ:

```java
AtomicInteger created = new AtomicInteger();

int flags = Spliterator.ORDERED | Spliterator.SIZED
        | Spliterator.SUBSIZED | Spliterator.NONNULL;

Supplier<Spliterator<String>> supplier = () -> {
    created.incrementAndGet();
    return Spliterators.spliterator(
            new String[] {"A", "B", "C"},
            Spliterator.ORDERED | Spliterator.NONNULL);
};

Stream<String> stream =
        StreamSupport.stream(supplier, flags, false);

System.out.println(created.get());  // 0
System.out.println(stream.toList()); // [A, B, C]
System.out.println(created.get());  // 1
```

Đây là đoạn minh họa trong phương thức cần import `java.util.Spliterator`, `java.util.Spliterators`, `java.util.function.Supplier`, `java.util.concurrent.atomic.AtomicInteger`, `java.util.stream.Stream` và `StreamSupport`. `Spliterators.spliterator(array, flags)` tự cung cấp `SIZED` và `SUBSIZED` cho mảng, cùng những cờ bổ sung `ORDERED`/`NONNULL`, nên `flags` được chọn nhất quán với nguồn tạo ra.

**Quy tắc quan trọng:** tham số `characteristics` khi tạo Stream bằng supplier **phải khớp** với `supplier.get().characteristics()` của Spliterator thật. Nếu khai hai bộ cờ mâu thuẫn, hành vi pipeline có thể không dự đoán được.

Không dùng supplier để lén trả nguồn khác loại hoặc thỉnh thoảng một Spliterator có tính chất khác với khai báo. Trong ví dụ, supplier tạo một mảng mới độc lập cho một lần duyệt. Stream vẫn **chỉ được tiêu thụ một lần**; muốn duyệt lại, tạo Stream mới từ supplier, không gọi lại terminal operation trên cùng một Stream.

## 9. Vì sao `Supplier` có thể giảm nguy cơ can thiệp nguồn?

Giả sử bạn có một tập dữ liệu có thể thay đổi:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
```

Nếu lấy Spliterator sớm rồi sau đó sửa `source`, hành vi phụ thuộc vào cơ chế *late-binding* và *fail-fast* cụ thể của Spliterator nguồn. Với một số collection, việc chỉnh sửa trong quá trình duyệt có thể ném `ConcurrentModificationException`; với nguồn khác có thể có hợp đồng concurrent riêng.

Dùng supplier làm rõ lúc lấy Spliterator:

```java
Stream<String> stream = StreamSupport.stream(
        source::spliterator,
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
        false);

// Chỉ nên thay đổi nguồn TRƯỚC khi terminal operation bắt đầu.
source.add("C");
List<String> values = stream.toList();
```

Đây là ví dụ theo điều kiện `source` là `ArrayList`; hãy đối chiếu đầy đủ đặc tính Spliterator thật khi dùng overload supplier. Trước lúc terminal bắt đầu, supplier chưa được gọi. Tuy nhiên, **điều đó không biến việc sửa source trong khi terminal đang duyệt thành an toàn**. Sau khi terminal bắt đầu, phải tuân theo quy tắc non-interference và khả năng cập nhật đồng thời của nguồn.

Nếu cần một snapshot bất biến, hãy tạo một snapshot như `List.copyOf(source)` ở ranh giới rõ ràng trước khi tính toán; supplier không tự tạo deep snapshot và không giải quyết mọi race.

## 10. Viết `Spliterator` tùy chỉnh cho dãy số

Ta có thể xây một nguồn không cần lưu danh sách toàn bộ phần tử. Ví dụ một dãy số nguyên thuộc khoảng **[startInclusive, endExclusive)**:

```text
[1, 6)  =>  1, 2, 3, 4, 5
[3, 3)  =>  nguồn rỗng
```

Một `Spliterator.OfInt` tùy chỉnh có thể duyệt một số tại mỗi lần `tryAdvance`. Với xử lý song song, `trySplit` tách khoảng còn lại làm hai khoảng không chồng nhau.

Cơ chế:

```text
Nguồn ban đầu: [1, 9)
                      |
                trySplit()
                /          \
        [1, 5)             [5, 9)
      (spliterator mới)     (spliterator hiện tại)
```

- Hai nhánh **không chồng lấn**, không bỏ sót giá trị.
- `estimateSize()` là số phần tử chưa được duyệt.
- `tryAdvance` tăng vị trí sau khi phát đúng một giá trị.
- `trySplit` có thể trả `null` nếu phạm vi còn quá nhỏ để tách.
- Các cờ `SIZED`/`SUBSIZED` chỉ đúng khi ước lượng và split luôn giữ số lượng chính xác.

Ví dụ Java 17 đầy đủ ở phần tiếp theo hiện thực tất cả các yếu tố này.

## 11. Ví dụ Java 17 đầy đủ, có thể biên dịch và chạy

Tạo tệp **`StreamSupportDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class StreamSupportDemo {
    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;

        IntRangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (current >= fence) {
                return false;
            }
            action.accept(current++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int start = current;
            int half = (fence - start) / 2;
            if (half == 0) {
                return null;
            }
            int middle = start + half;
            current = middle; // Spliterator hiện tại giữ nửa sau.
            return new IntRangeSpliterator(start, middle);
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED
                    | IMMUTABLE | NONNULL | DISTINCT;
        }
    }

    public static void main(String[] args) {
        // 1. Iterable có thể được đưa vào StreamSupport.
        Iterable<String> colors = List.of("red", "green", "blue");
        List<String> upper = StreamSupport
                .stream(colors.spliterator(), false)
                .map(value -> value.toUpperCase(Locale.ROOT))
                .toList();
        System.out.println("Iterable: " + upper);

        // 2. Tạo Spliterator từ Iterator chưa biết kích thước.
        Iterator<String> iterator =
                List.of("Lan", "Minh", "An").iterator();
        Spliterator<String> unknown =
                Spliterators.spliteratorUnknownSize(
                        iterator, Spliterator.ORDERED);
        System.out.println("Unknown SIZED: "
                + unknown.hasCharacteristics(Spliterator.SIZED));

        List<String> names = StreamSupport.stream(unknown, false)
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("Iterator: " + names);

        // 3. Supplier chưa được gọi khi tạo Stream.
        AtomicInteger created = new AtomicInteger();
        int flags = Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED | Spliterator.NONNULL;

        Supplier<Spliterator<String>> supplier = () -> {
            created.incrementAndGet();
            return Spliterators.spliterator(
                    new String[] {"A", "B", "C"},
                    Spliterator.ORDERED | Spliterator.NONNULL);
        };

        Stream<String> deferred =
                StreamSupport.stream(supplier, flags, false);
        System.out.println("Supplier before: " + created.get());
        System.out.println("Supplier values: " + deferred.toList());
        System.out.println("Supplier after: " + created.get());

        // 4. Spliterator.OfInt tùy chỉnh, không cần tạo List nguồn.
        List<Integer> firstFive = StreamSupport.intStream(
                new IntRangeSpliterator(1, 6), false)
                .boxed()
                .toList();
        System.out.println("Range: " + firstFive);

        // 5. Dùng Spliterator.OfInt khi cần xử lý song song.
        int sum = StreamSupport.intStream(
                new IntRangeSpliterator(1, 1001), true)
                .sum();
        System.out.println("Parallel sum: " + sum);

        // 6. Quan sát chính xác việc chia khoảng.
        Spliterator.OfInt right =
                new IntRangeSpliterator(1, 6);
        System.out.println("Size before split: "
                + right.estimateSize());
        Spliterator.OfInt left = right.trySplit();

        System.out.println("Split left: "
                + StreamSupport.intStream(left, false)
                        .boxed().toList());
        System.out.println("Split right: "
                + StreamSupport.intStream(right, false)
                        .boxed().toList());

        // 7. Nguồn rỗng cũng hoạt động.
        long count = StreamSupport.intStream(
                new IntRangeSpliterator(3, 3), false)
                .count();
        System.out.println("Empty count: " + count);

        // 8. Phiên bản LongStream từ Spliterator.OfLong.
        long longSum = StreamSupport.longStream(
                Spliterators.spliterator(
                        new long[] {5L, 10L},
                        Spliterator.ORDERED),
                false)
                .sum();
        System.out.println("Long sum: " + longSum);

        // 9. Phiên bản DoubleStream từ Spliterator.OfDouble.
        double avg = StreamSupport.doubleStream(
                Spliterators.spliterator(
                        new double[] {1.0, 2.0},
                        Spliterator.ORDERED),
                false)
                .average()
                .orElseThrow();
        System.out.println("Double average: " + avg);
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 StreamSupportDemo.java
java StreamSupportDemo
```

**Stdout dự kiến chính xác:**

```text
Iterable: [RED, GREEN, BLUE]
Unknown SIZED: false
Iterator: [Lan, Minh]
Supplier before: 0
Supplier values: [A, B, C]
Supplier after: 1
Range: [1, 2, 3, 4, 5]
Parallel sum: 500500
Size before split: 5
Split left: [1, 2]
Split right: [3, 4, 5]
Empty count: 0
Long sum: 15
Double average: 1.5
```

### Phân tích từng kết quả

**`Iterable`:** đối tượng thực là `List.of` có encounter order. `StreamSupport.stream(..., false)` duyệt tuần tự, `map` chuyển chữ hoa theo `Locale.ROOT`, nên kết quả giữ red, green, blue theo thứ tự.

**`Iterator`:** factory `spliteratorUnknownSize` không quảng bá `SIZED`. `filter` giữ Lan (3 ký tự) và Minh (4 ký tự), loại An (2 ký tự).

**`Supplier`:** `created` là 0 sau khi chỉ tạo Stream; khi `deferred.toList()` bắt đầu, supplier được gọi một lần để trả Spliterator thực, nên bộ đếm thành 1. Mảng ba phần tử được duyệt đúng thứ tự A, B, C.

**`IntRangeSpliterator`:** nguồn [1,6) chứa 5 số. `StreamSupport.intStream(..., false)` lấy phần tử từ `tryAdvance`. Khi tính tổng song song cho [1,1001), tất cả số 1 đến 1000 được cộng; tổng là `1000 × 1001 / 2 = 500500`. Phép cộng không đổi kết quả dù phân chia giữa nhiều nhánh.

**`trySplit`:** với [1,6), độ dài 5, nửa đầu có độ dài 2 là [1,3), còn Spliterator hiện tại giữ [3,6). Vì vậy left chứa 1,2 và right chứa 3,4,5, không trùng và không mất phần tử.

**Nguồn rỗng:** [3,3) không chứa phần tử nên `count()` trả 0. Với cờ `SIZED` chính xác, Stream có thể tối ưu `count()` bằng kích thước đã biết, không bắt buộc gọi `tryAdvance` cho từng phần tử.

**Primitive:** `StreamSupport.longStream` và `doubleStream` hoạt động với `OfLong`/`OfDouble` tương ứng. Dữ liệu [5,10] cộng 15; trung bình [1.0,2.0] là 1.5.

### Lưu ý về độ dài khoảng và overflow

Trong `trySplit` demo, phép `fence - start` dùng `int`. Vì các khoảng được thử có kích thước nhỏ, không overflow. Nếu thiết kế Spliterator cho toàn bộ miền `int` (ví dụ từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`), phép trừ `int` có thể overflow. Một Spliterator production cần tính khoảng cách theo `long`:

```java
long remaining = (long) fence - current;
long half = remaining / 2;
long middle = (long) current + half;
```

Đây là **đoạn minh họa cách tính an toàn**, cần kiểm tra chuyển về `int` theo điều kiện miền và hợp đồng riêng. Không sao chép nguyên bộ `trySplit` nhỏ của demo để quảng bá hỗ trợ mọi khoảng số nguyên cực trị.

## 12. `tryAdvance`: quy tắc cần giữ khi tự hiện thực

Một Spliterator tùy chỉnh phải đảm bảo rằng khi `tryAdvance(action)` trả `true`:

1. Nó áp dụng `action` cho một phần tử hiện tại.
2. Nó cập nhật trạng thái để **không phát lại cùng phần tử ngoài ý muốn**.
3. Nó không bỏ qua phần tử khác nếu nguồn định nghĩa phải duyệt mọi phần tử.
4. Khi hết dữ liệu, nó trả `false` và không gọi action.

Một ví dụ sai:

```java
@Override
public boolean tryAdvance(IntConsumer action) {
    action.accept(current); // Quên tăng current.
    return true;             // Không có trạng thái dừng.
}
```

Đây là **phản ví dụ**, không phải chương trình hợp lệ độc lập. Nếu đưa vào `StreamSupport.intStream` và gọi `toList()` không giới hạn, Stream có thể lặp mãi một giá trị và gây cạn tài nguyên. Trước khi dùng `Spliterator` tùy chỉnh với terminal thu thập toàn bộ, hãy kiểm tra ranh giới kết thúc.

### Phát sinh side effect ở action hay ở nguồn?

`tryAdvance` chịu trách nhiệm **cung cấp dữ liệu**. Không nên âm thầm ghi file/gửi email trong `tryAdvance` khi mục tiêu của nguồn chỉ là đọc các phần tử. Vì Stream có thể duyệt một phần hoặc bỏ qua những bước không cần thiết dựa trên pipeline và terminal, không nên dựa vào `tryAdvance` để thực hiện các side effect bắt buộc đúng một lần cho mọi dữ liệu nguồn.

Nếu Spliterator thực sự đọc từ thiết bị hoặc file, thao tác đọc là I/O có side effect kỹ thuật. Hãy làm rõ hợp đồng mở/đóng tài nguyên, lỗi I/O, quyền sở hữu và khả năng tái duyệt; đừng giả định nguồn là thuần chỉ vì được gọi qua Stream API.

## 13. `trySplit` và xử lý song song đúng cách

`trySplit()` trả một Spliterator mới bao phủ **một phần các phần tử chưa duyệt**, còn Spliterator hiện tại giữ phần còn lại. Với nguồn ordered, phần được trả thường là **prefix** của phần còn lại.

Ví dụ từ [1,9):

```text
Ban đầu: 1 2 3 4 5 6 7 8
                     |
                 trySplit()
                  /     \
Trả về:          1 2 3 4   | Giữ lại: 5 6 7 8
```

Các bất biến quan trọng:

- **Không trùng lặp phần tử.**
- **Không bỏ sót phần tử.**
- Với nguồn `SIZED`/`SUBSIZED`, kích thước các nhánh phù hợp với kích thước trước tách.
- Với nguồn `ORDERED`, thứ tự duyệt của các nhánh sau kết hợp phải tương thích thứ tự nguồn.
- Mỗi Spliterator con quản lý phạm vi/địa chỉ duyệt của nó; tránh dùng cùng một biến mutable không đồng bộ giữa các nhánh.
- Khi quá ít phần tử hoặc không chia được, `trySplit` có thể trả `null`.

### Parallel không đồng nghĩa thứ tự các lambda được thực thi

```java
List<String> labels = StreamSupport.intStream(
        new IntRangeSpliterator(1, 6), true)
        .mapToObj(n -> "N" + n)
        .toList();

System.out.println(labels); // [N1, N2, N3, N4, N5]
```

Nguồn quảng bá `ORDERED` và `toList()` giữ encounter order, nên thứ tự **kết quả** là N1..N5. Tuy nhiên, phép biến đổi `n -> "N" + n` có thể chạy trên nhiều thread không theo thứ tự tuyến tính 1..5. Đừng cập nhật `ArrayList` chia sẻ hay ghi log nghiệp vụ dựa trên thứ tự thực thi của mapper.

### Khi nào parallel không có lợi?

Nguồn chỉ có vài phần tử, `trySplit()` luôn trả null, nguồn đọc I/O tuần tự, hoặc mapper quá nhẹ có thể khiến chi phí phân chia/đồng bộ lớn hơn lợi ích. Không đặt `parallel=true` chỉ vì thấy `trySplit()` tồn tại; đo thời gian thực tế với workload đại diện.

## 14. `SIZED`, `SUBSIZED` và kích thước chính xác

Khi Spliterator quảng bá `SIZED`, `estimateSize()` có hợp đồng tương ứng với kích thước của phần chưa duyệt. Với `SUBSIZED`, các Spliterator con phát sinh từ `trySplit` cũng phải mang đặc tính kích thước thích hợp.

Một phép thử:

```java
Spliterator.OfInt s = new IntRangeSpliterator(1, 6);

System.out.println(s.hasCharacteristics(Spliterator.SIZED)); // true
System.out.println(s.getExactSizeIfKnown());                // 5
```

Dùng `SIZED` chính xác có thể giúp Stream tối ưu những thao tác như `count` hoặc cấp phát kết quả. Nhưng không đoán rằng mọi terminal sẽ buộc gọi `tryAdvance`: tối ưu dựa trên metadata là hợp lệ khi đủ điều kiện.

**Nếu bạn cung cấp kích thước sai**, ví dụ báo 100 phần tử nhưng chỉ phát 3, một số phép tối ưu có thể bị ảnh hưởng nặng và kết quả trở nên sai hoặc có lỗi. Đặc tính Spliterator là lời hứa của bên triển khai, cần được unit test.

### Kích thước chưa biết

Nếu nguồn là iterator đầu vào hoặc cursor, `estimateSize()` có thể trả `Long.MAX_VALUE` khi không biết số phần tử, và không quảng bá `SIZED`. Điều đó hoàn toàn hợp lệ; việc tạo Stream từ nguồn chưa biết kích thước không đòi hỏi tạo toàn bộ List trước.

## 15. Dùng `Spliterators` để giảm lượng code tự viết

Không phải lúc nào cũng cần tự triển khai `Spliterator`. `java.util.Spliterators` đã cung cấp các factory:

```java
// Từ iterator không biết kích thước:
Spliterator<String> unknown =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

// Từ mảng đối tượng:
Spliterator<String> array =
        Spliterators.spliterator(
                new String[] {"A", "B"},
                Spliterator.ORDERED);

// Từ mảng int:
Spliterator.OfInt ints =
        Spliterators.spliterator(
                new int[] {1, 2, 3},
                Spliterator.ORDERED);
```

Các đoạn giả định `iterator` tồn tại và cần import `Spliterator`/`Spliterators`. Mảng có kích thước biết trước nên factory có thể cung cấp `SIZED`/`SUBSIZED`; iterator không biết kích thước thì không.

Trường hợp đầu vào đã là `Collection`, đa phần **`collection.stream()` hoặc `collection.parallelStream()` là cách rõ ràng hơn**. Tạo StreamSupport thủ công chỉ đáng giá khi nguồn không có API Stream thuận tiện hoặc bạn cần điều khiển hành vi Spliterator.

## 16. Hợp đồng thứ tự và dữ liệu không có thứ tự

`forEachOrdered` và `Stream.toList()` có thể giữ thứ tự nếu nguồn **có encounter order**. Nếu Spliterator không quảng bá `ORDERED`, bạn không nên giả định thứ tự phần tử luôn như lần chạy thử.

Ví dụ:

```java
Spliterator<String> source =
        Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

StreamSupport.stream(source, false)
        .forEachOrdered(System.out::println);
```

Đây là đoạn minh họa với `iterator` cung cấp một thứ tự đã được nguồn cam kết. Nếu iterator đến từ một cấu trúc unordered, việc gắn `ORDERED` có thể không phản ánh hợp đồng nguồn. Khi cần thứ tự nghiệp vụ, có thể tạo `List`/`sorted` hoặc chọn một nguồn đã xác định thứ tự.

Không lẫn **thứ tự phần tử trong kết quả** với **thứ tự thực thi mapper** trong parallel pipeline.

## 17. Tính bất biến và can thiệp nguồn

Stream API khuyến nghị các nguồn không concurrent không bị chỉnh sửa khi pipeline đang hoạt động. Nếu dùng một `ArrayList` đang bị thread khác sửa, Spliterator có thể phát hiện thay đổi và ném `ConcurrentModificationException` hoặc có các hiệu ứng không nên dựa vào.

**Không chữa vấn đề bằng cách khai `CONCURRENT` giả.** Cờ `CONCURRENT` dành cho nguồn thực sự hỗ trợ cập nhật đồng thời theo hợp đồng, ví dụ một số concurrent collections, không phải cách bật một tính năng không tồn tại.

Với một generator không phụ thuộc collection như `IntRangeSpliterator`, `IMMUTABLE` có thể phù hợp vì dãy số đã được xác định bởi khoảng. Nhưng đối với danh sách mutable, đừng khai `IMMUTABLE` chỉ vì bạn mong caller sẽ không sửa; phải dựa trên contract của nguồn.

Nếu cần tạo snapshot cố định cho xử lý nhiều bước, có thể dùng `List.copyOf(source)` hoặc mô hình immutable phù hợp tại ranh giới. Đây là quyết định ở lớp dữ liệu, không do `StreamSupport` tự thực hiện.

## 18. Checked exception từ nguồn I/O

`Spliterator.tryAdvance` nhận `Consumer` và **không khai báo checked `IOException`** trong chữ ký. Vì vậy một Spliterator trực tiếp đọc tệp/network thường phải tự bắt checked exception hoặc thiết kế adapter để chuyển lỗi theo hợp đồng.

Ví dụ hướng xử lý:

```java
// Trong một phương thức tryAdvance của Spliterator tùy chỉnh:
try {
    String line = reader.readLine();
    if (line == null) {
        return false;
    }
    action.accept(line);
    return true;
} catch (IOException ex) {
    throw new UncheckedIOException(ex);
}
```

Đây là **đoạn minh họa**, cần có `reader`/`action` và import `IOException`/`UncheckedIOException`, không phải một chương trình độc lập. Việc bọc giữ nguyên nhân gốc ở `getCause()` nhưng **không tự đóng `reader`**. Chủ sở hữu nguồn vẫn phải đóng bằng cơ chế phù hợp.

Khi terminal operation ném `UncheckedIOException`, caller cần chính sách xử lý lỗi và có thể phải rollback/bù trừ những side effect đã thực hiện trước đó. Tạo Stream bằng StreamSupport không đảm bảo atomicity hay retry.

## 19. Primitive Spliterator và tránh boxing

`StreamSupport.intStream(...)`, `longStream(...)`, `doubleStream(...)` nhận các Spliterator chuyên biệt:

| Loại nguồn | Stream nhận được | Kiểu action |
| --- | --- | --- |
| `Spliterator.OfInt` | `IntStream` | `IntConsumer` |
| `Spliterator.OfLong` | `LongStream` | `LongConsumer` |
| `Spliterator.OfDouble` | `DoubleStream` | `DoubleConsumer` |
| `Spliterator<T>` | `Stream<T>` | `Consumer<T>` |

Điều này tránh yêu cầu phải boxing một `int` thành `Integer` khi nguồn bản chất chỉ sinh số. Ví dụ:

```java
long sum = StreamSupport.intStream(
        new IntRangeSpliterator(1, 1001), false)
        .asLongStream()
        .sum();

System.out.println(sum); // 500500
```

Với dữ liệu nhỏ như ví dụ, hiệu năng không phải lý do chính; khi xử lý hàng triệu số, primitive stream có thể giảm overhead. Tuy nhiên hãy đánh giá overflow, độ chính xác và tính đúng đắn trước khi tối ưu.

### Tại sao không có `StreamSupport.floatStream`?

Java Stream API chuyên biệt có `IntStream`, `LongStream` và `DoubleStream`, **không có `FloatStream`** riêng trong JDK 17. Khi xử lý `float`, có thể dùng `DoubleStream` với chuyển đổi cần thiết hoặc `Stream<Float>` tùy hợp đồng.

## 20. Kết hợp với `map`, `filter`, `flatMap` và collector

Sau khi có Stream, nó hoạt động như các Stream khác:

```java
List<String> result = StreamSupport
        .stream(iterable.spliterator(), false)
        .filter(s -> !s.isBlank())
        .map(s -> s.trim().toUpperCase(Locale.ROOT))
        .distinct()
        .sorted()
        .toList();
```

`iterable` được giả định là `Iterable<String>` có các chuỗi hợp lệ; nếu có `null`, gọi `isBlank()` sẽ ném `NullPointerException`, nên cần validate hoặc lọc null theo quy tắc nghiệp vụ.

Ví dụ từ nguồn cấu trúc lồng:

```java
Iterable<List<Integer>> groups = List.of(
        List.of(1, 2), List.of(), List.of(3));

List<Integer> flat = StreamSupport
        .stream(groups.spliterator(), false)
        .flatMap(List::stream)
        .toList();

System.out.println(flat); // [1, 2, 3]
```

**StreamSupport chỉ thay đổi cách tạo nguồn**, không thay đổi hợp đồng của `map`, `flatMap`, `sorted`, `collect` hay `toList`.

## 21. Những lỗi thường gặp khi tạo Stream bằng `StreamSupport`

| Sai lầm | Vì sao nguy hiểm/sai | Hướng sửa |
| --- | --- | --- |
| Gọi `iterable.stream()` khi biến chỉ có kiểu `Iterable` | `Iterable` không khai báo `stream()` | Dùng `StreamSupport.stream(iterable.spliterator(), false)` |
| Truyền trực tiếp `Iterator` vào `stream` | Overload cần `Spliterator`/`Supplier` | Dùng `Spliterators.spliteratorUnknownSize` |
| Nghĩ `parallel=true` sẽ tự chia nguồn tối ưu | Phụ thuộc `trySplit` và workload | Triển khai split đúng rồi benchmark |
| `tryAdvance` luôn trả true | Có thể tạo nguồn không kết thúc | Cập nhật vị trí và điều kiện dừng |
| `trySplit` trả vùng trùng lặp | Phần tử có thể bị xử lý hai lần | Kiểm tra bất biến không trùng/không bỏ sót |
| Quảng bá `SIZED` khi kích thước không biết | Metadata sai, tối ưu hóa có thể sai | Không gắn `SIZED` |
| Quảng bá `SORTED` nhưng không sorted | Vi phạm contract | Chỉ khai nếu nguồn thật sorted |
| Gắn `CONCURRENT` cho `ArrayList` | Không làm ArrayList thread-safe | Tuân theo nguồn thật hoặc tạo snapshot |
| Không xác định `ORDERED` mà kỳ vọng đúng encounter order | Hợp đồng thứ tự không rõ | Dùng nguồn/flags phù hợp |
| Tái sử dụng Stream đã terminal | Stream chỉ tiêu thụ một lần | Tạo Stream mới từ nguồn |
| Dùng lại Iterator đã cạn | Không quay lại đầu dữ liệu | Tạo Iterator mới |
| Tạo stream I/O mà quên đóng nguồn | Rò rỉ file/socket/cursor | `try-with-resources` hoặc close hook rõ |
| Cho mapper có side effect bắt buộc | Lazy/short-circuit/parallel khó kiểm soát | Tách tính toán khỏi I/O |
| Tuyên bố supplier characteristics khác Spliterator thật | Vi phạm hợp đồng overload supplier | Đồng bộ flags với nguồn |
| Lạm dụng StreamSupport cho `List` đã có `stream()` | Thêm code không cần thiết | Dùng API stream của collection |
| Dùng `int` tính kích thước khoảng rất lớn | Tràn số khi trừ hoặc chia | Dùng `long` và kiểm tra phạm vi |
| Nghĩ `count()` luôn gọi `tryAdvance` | Với nguồn SIZED có thể tối ưu | Test giá trị, không dựa vào side effect |
| Lạm dụng `parallel()` trên I/O | Race, rate limit, order không ổn định | Điều phối I/O riêng, hạn chế concurrency |

## 22. Bài tập thực hành

1. Cho `Iterable<String> data = List.of("a","b","c")`. Dùng `StreamSupport.stream(data.spliterator(), false)` để nhận `List<String>` chữ hoa; xác định vì sao không gọi trực tiếp `data.stream()` được.
2. Tạo `Iterator<Integer>` từ `List.of(1,2,3)` và bọc bằng `Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED)`. Tính tổng bằng `mapToInt(Integer::intValue).sum()`.
3. Kiểm tra `hasCharacteristics(Spliterator.SIZED)` của một Spliterator từ `spliteratorUnknownSize`. Giải thích vì sao kết quả false ngay cả khi số phần tử bạn biết là ba.
4. Sửa `IntRangeSpliterator` trong ví dụ để tạo khoảng [5,10). Dự đoán `List` là [5,6,7,8,9].
5. Với `new IntRangeSpliterator(1,6)`, gọi `trySplit` rồi duyệt cả hai Spliterator riêng. Vì sao kết quả là [1,2] và [3,4,5]?
6. Viết một test so sánh tổng phần tử trước split với tổng hai nhánh sau split. Bảo đảm không trùng/không bỏ sót.
7. Xây một Spliterator chỉ trả `null` ở `trySplit`. Nó vẫn tạo Stream tuần tự đúng không? Parallel stream có thể tối ưu chia việc được không?
8. Tạo nguồn không có `SIZED`, thử `count()` và quan sát sự khác nhau giữa `estimateSize` và kích thước thực tế.
9. Dùng overload supplier và `AtomicInteger` đếm số lần gọi supplier. Xác minh 0 trước terminal và 1 khi `toList()` chạy.
10. Thử gắn đặc tính `SORTED` cho một dãy không được sắp. Giải thích **không nên chạy mã như một giải pháp hợp lệ** và vì sao Stream có thể tối ưu theo cờ sai.
11. Tạo `Spliterator.OfLong` từ mảng `long[]` bằng `Spliterators.spliterator`, rồi `StreamSupport.longStream(..., false).sum()`.
12. Tạo `Spliterator.OfDouble` từ mảng `double[]` và tính `average().orElseThrow()`, kiểm tra trường hợp mảng rỗng cần xử lý `OptionalDouble`.
13. Viết ví dụ StreamSupport từ `Iterable<List<Integer>>` rồi `flatMap(List::stream)`, chứng minh cách tạo nguồn không làm thay đổi ý nghĩa `flatMap`.
14. Nêu một tình huống cần tự quản lý I/O khi đọc file qua custom Spliterator và cách gắn trách nhiệm đóng tài nguyên vào API sử dụng.
15. Với nguồn Ordered, so sánh `forEach` và `forEachOrdered` khi gọi `parallel=true`. Vì sao thứ tự action không nên suy ra chỉ từ kết quả một lần chạy?
16. Đề xuất unit test cho custom Spliterator gồm: đầu vào rỗng, một phần tử, nhiều phần tử, split nhiều lần, kích thước, cờ đặc tính và không bỏ sót.
17. Viết một phiên bản `trySplit` tính khoảng còn lại bằng `long` để tránh overflow khi start/fence gần giới hạn `int`.

## 23. Checklist kiểm tra trước khi dùng trong dự án

- Có thật sự cần nguồn tùy chỉnh hay `collection.stream()`/`Stream.of()` đã đủ?
- Nguồn có dạng `Iterable`, `Iterator`, collection, array, generator hay I/O cursor?
- Đang chọn đúng overload `StreamSupport.stream` hoặc `intStream`/`longStream`/`doubleStream`?
- Với nguồn chưa biết kích thước, đã dùng `spliteratorUnknownSize` và tránh khai `SIZED` sai chưa?
- `tryAdvance` có phát đúng một phần tử và có điểm dừng đúng không?
- `trySplit` có phân chia chính xác, không trùng/không thiếu và giữ thứ tự nếu khai `ORDERED` không?
- `estimateSize` và `SIZED`/`SUBSIZED` có khớp thực tế không?
- Các flags `ORDERED`/`DISTINCT`/`SORTED`/`NONNULL`/`IMMUTABLE`/`CONCURRENT` có trung thực không?
- Nếu dùng Supplier, các `characteristics` truyền vào có khớp Spliterator thật không?
- Có phân biệt **tạo stream** với **tiêu thụ bằng terminal operation** không?
- Có đang tái sử dụng Iterator/Stream đã tiêu thụ không?
- Với nguồn có thể sửa hoặc concurrent, đã xác định chính sách non-interference và thread-safety chưa?
- Với nguồn I/O, ai mở/đóng file/socket/cursor và xử lý exception?
- Nếu đặt `parallel=true`, có benchmark và kiểm thử parallel traversal thay vì giả định nhanh hơn không?
- Có unit test đầu ra, số lượng, thứ tự, split, kích thước và trường hợp rỗng không?

**Kết luận:** `StreamSupport` là cầu nối từ `Spliterator` sang `Stream` (hoặc `IntStream`, `LongStream`, `DoubleStream`). Dùng `Iterable.spliterator()`, `Spliterators.spliteratorUnknownSize` hoặc một Spliterator tùy chỉnh để định nghĩa chính xác cách duyệt và chia nguồn. Hãy đặt tính đúng đắn của `tryAdvance`, `trySplit`, `estimateSize` và các characteristics lên trước việc bật `parallel`; Stream pipeline phía sau vẫn tuân thủ cơ chế lazy, terminal operation và quy tắc quản lý side effect/tài nguyên của Java Stream API.
