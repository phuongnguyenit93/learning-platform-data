# Tạo Stream bằng StreamSupport với Supplier của Spliterator

Java Stream API cho phép tạo pipeline từ `Collection`, mảng và các nguồn quen thuộc. Khi nguồn dữ liệu do ứng dụng tự định nghĩa, `Spliterator` mô tả cách duyệt và chia phần tử cho xử lý song song, còn `StreamSupport` biến nguồn đó thành `Stream`. Một overload đặc biệt nhận **`Supplier<? extends Spliterator<T>>`** thay vì nhận sẵn một `Spliterator`. Lựa chọn này giúp **trì hoãn việc lấy Spliterator đến khi terminal operation bắt đầu**, qua đó giảm khoảng thời gian nguồn có thể bị can thiệp trước khi duyệt.

Bài thuộc chương **Spliterator và nguồn tự định nghĩa** trong mô-đun **JAVA_STREAM_API**. Nội dung tập trung vào overload sử dụng Supplier, tham số đặc tính `characteristics`, thời điểm khởi tạo, tính đúng của nguồn tự viết và khả năng chia nguồn. Ta cũng kết nối với pipeline lazy (`filter`, `map`, `reduce`, `collect`), xử lý song song, tài nguyên I/O và cách tránh lỗi về trạng thái, hiệu năng.

## 1. Tình huống: tại sao không luôn truyền Spliterator trực tiếp?

Giả sử ta muốn tạo Stream từ dữ liệu mà thời điểm bắt đầu duyệt mới xác định được: danh sách có thể được bổ sung **trước khi** chạy terminal operation, hoặc một nguồn tùy chỉnh chỉ nên được khởi tạo khi thật sự cần xử lý.

`StreamSupport` có hai overload cho `Stream<T>`:

```java
public static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
);

public static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
);
```

Điểm khác biệt:

| Tiêu chí | Truyền `Spliterator` | Truyền `Supplier` |
| --- | --- | --- |
| Đối tượng Spliterator | Được cung cấp khi tạo Stream | Được lấy qua `supplier.get()` khi terminal operation bắt đầu |
| Lập kế hoạch tạo nguồn | Caller tạo/chọn Spliterator trước | Caller mô tả cách tạo/lấy Spliterator về sau |
| Cờ `characteristics` | Lấy từ Spliterator đã cung cấp | Caller **phải khai báo trước** và bảo đảm phù hợp với Spliterator thực tế |
| Phù hợp khi | Nguồn đã có sẵn, việc tạo Spliterator rẻ và an toàn | Muốn trì hoãn việc tạo Spliterator hoặc thu hẹp khoảng thời gian có thể bị can thiệp |
| Tự động lặp lại Stream? | Không | **Không** |
| Tự động đóng nguồn I/O? | Không | **Không** |

Với overload Supplier, đặc tả Java quy định `Supplier.get()` được gọi **không quá một lần** và **chỉ sau khi terminal operation của pipeline bắt đầu**. “Không quá một lần” khác với “luôn luôn đúng một lần” trong mọi trường hợp sử dụng: ví dụ một Stream được tạo rồi bỏ đi mà không có terminal operation thì Supplier chưa cần được gọi.

### Một sơ đồ thời gian

```text
Tạo Stream
    |
    | StreamSupport.stream(supplier, characteristics, false)
    v
Xây pipeline lazy
    |
    | filter(...).map(...)
    | Chưa yêu cầu supplier.get()
    v
Gọi terminal operation
    |
    | supplier.get()  →  Spliterator
    |                         |
    |                         v
    |                     tryAdvance(...)
    |                     trySplit(...) nếu phù hợp
    v
Nhận kết quả từ count()/toList()/reduce()/collect()
```

Sơ đồ chỉ minh họa các bước có thể xảy ra: một terminal operation có thể được tối ưu nhờ thông tin kích thước, nên không được giả định số lần gọi `tryAdvance`; với nguồn không chia được, `trySplit` có thể không được gọi hoặc trả về `null`.

## 2. Chữ ký của overload Supplier và ba tham số

```java
StreamSupport.stream(supplier, characteristics, parallel)
```

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `supplier` | `Supplier<? extends Spliterator<T>>` | Trả về một Spliterator dùng làm nguồn của Stream |
| `characteristics` | `int` | Các cờ đặc tính **phải đúng với Spliterator do Supplier trả về** |
| `parallel` | `boolean` | Yêu cầu Stream ban đầu là tuần tự (`false`) hay song song (`true`) |

Các cờ lấy từ `java.util.Spliterator` và ghép bằng toán tử bitwise OR `|`:

```java
import java.util.Spliterator;

int flags = Spliterator.ORDERED
          | Spliterator.SIZED
          | Spliterator.SUBSIZED;
```

**Hợp đồng cốt lõi:** Giá trị `characteristics` truyền vào `StreamSupport.stream` **phải bằng đúng** `supplier.get().characteristics()`. Nếu không khớp, hành vi khi bắt đầu terminal operation có thể không được xác định theo đặc tả API. Không coi tham số này là “một vài cờ gợi ý” hoặc “chọn càng nhiều càng nhanh”.

Supplier phải cung cấp một Spliterator hợp lệ, không phải `null`. Việc tạo Spliterator cũng phải nhất quán với ranh giới dữ liệu mà ứng dụng muốn duyệt.

### Đặt tên để tránh nhầm

Trong đoạn:

```java
Supplier<Spliterator<String>> source = names::spliterator;
Stream<String> stream = StreamSupport.stream(source, flags, false);
```

`source` không phải một Stream để tiêu thụ. Nó là một **hàm tạo/lấy nguồn duyệt**. `stream` vẫn chỉ dùng được một lần dù `source.get()` có thể tạo Spliterator mới trong những lần gọi độc lập ngoài pipeline đó.

## 3. Ví dụ nền tảng: Supplier tạo Spliterator muộn từ ArrayList

Với `ArrayList` thông thường, Spliterator có các đặc tính `ORDERED`, `SIZED` và `SUBSIZED`. Ví dụ Java 17+:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class SupplierBindingDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Bình"));

        AtomicInteger suppliersCalled = new AtomicInteger();

        Supplier<Spliterator<String>> source = () -> {
            suppliersCalled.incrementAndGet();
            return names.spliterator();
        };

        int flags = Spliterator.ORDERED
                  | Spliterator.SIZED
                  | Spliterator.SUBSIZED;

        Stream<String> stream = StreamSupport.stream(source, flags, false)
            .filter(name -> !name.isBlank())
            .map(String::toUpperCase);

        System.out.println(suppliersCalled.get()); // 0

        // Thay đổi danh sách TRƯỚC khi terminal operation bắt đầu.
        names.add("Chi");

        List<String> result = stream.toList();

        System.out.println(suppliersCalled.get()); // 1
        System.out.println(result);                 // [AN, BÌNH, CHI]
    }
}
```

Điều ví dụ minh họa:

1. Khi mới xây pipeline, `supplier.get()` chưa được gọi.
2. Sau khi bổ sung `"Chi"` **trước terminal operation**, Supplier mới trả `names.spliterator()` của danh sách hiện tại.
3. `toList()` tiêu thụ pipeline một lần, tạo kết quả theo thứ tự gặp của `ArrayList`.
4. `supplier.get()` được gọi một lần trong lần tiêu thụ này.

Không suy ra rằng ứng dụng được phép sửa danh sách **trong lúc terminal operation đang chạy**. `ArrayList` không phải một nguồn concurrent; sửa cấu trúc danh sách giữa lúc duyệt có thể gây `ConcurrentModificationException` hoặc kết quả không được bảo đảm.

**Lưu ý về late binding:** Một số Spliterator của thư viện chuẩn, chẳng hạn của `ArrayList`, vốn đã có cơ chế liên kết muộn (*late-binding*) riêng. Overload Supplier mang lại cơ chế trì hoãn ở mức `StreamSupport` và đặc biệt hữu ích khi **quá trình tạo Spliterator của nguồn tùy chỉnh** cần được trì hoãn; không phải mọi danh sách đều cần Supplier để hoạt động đúng.

## 4. Đặc tính của Spliterator: cam kết về nguồn, không phải tùy chọn trang trí

Mỗi Spliterator công bố các cờ bằng `characteristics()`. `StreamSupport` cần biết những cờ này trước khi gọi Supplier.

| Cờ | Ý nghĩa | Điểm cần kiểm tra |
| --- | --- | --- |
| `ORDERED` | Nguồn có encounter order có ý nghĩa | Nguồn và `trySplit` phải bảo toàn thứ tự khi chia |
| `DISTINCT` | Các phần tử của nguồn là duy nhất theo quy tắc bằng nhau | Không đặt nếu dữ liệu có thể trùng |
| `SORTED` | Các phần tử đã được sắp theo một thứ tự nhất định | `getComparator()` phải phản ánh đúng comparator; trả `null` cho natural ordering |
| `SIZED` | `estimateSize()` báo số phần tử còn lại chính xác theo hợp đồng | Không đặt cho nguồn không biết trước kích thước |
| `NONNULL` | Nguồn không phát ra phần tử `null` | Không đặt khi có thể phát ra `null` |
| `IMMUTABLE` | Nguồn không thể bị sửa cấu trúc trong quá trình duyệt | Không đặt chỉ vì có biến tham chiếu `final` |
| `CONCURRENT` | Nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng | Không đặt cho `ArrayList` thông thường |
| `SUBSIZED` | Spliterator và các phần sau khi chia đều thỏa `SIZED` và `SUBSIZED` | Chỉ đặt khi có thể bảo đảm kích thước chính xác cho mọi nhánh |

Một vài nguyên tắc quan trọng:

- `ORDERED` liên quan **encounter order của nguồn**, không có nghĩa mọi kết quả Map sau `collect` có thứ tự.
- `SORTED` là cam kết mạnh hơn `ORDERED`; nếu khai báo `SORTED`, cách so sánh của nguồn phải được diễn đạt đúng qua `getComparator()`.
- `SIZED` cho phép tối ưu tính toán từ kích thước đã biết; khai báo sai có thể khiến các terminal operation như `count()` trả kết quả không mong muốn.
- `IMMUTABLE` nói về khả năng sửa cấu trúc **nguồn**, không đồng nghĩa các đối tượng phần tử bên trong đều bất biến sâu.
- `CONCURRENT` nói về đặc tính của **nguồn duyệt**, không phải khả năng mọi lambda `map`/`filter` cập nhật biến dùng chung.
- Các cờ phải đúng trên **nguồn Spliterator được cấp**, không được suy từ các thao tác `map` hay `filter` viết sau đó.

### Tự kiểm tra một nguồn khi phát triển

```java
import java.util.ArrayList;
import java.util.Spliterator;

Spliterator<String> spliterator =
    new ArrayList<>(java.util.List.of("A", "B")).spliterator();

int actual = spliterator.characteristics();

System.out.println(spliterator.hasCharacteristics(
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
)); // true với Spliterator của ArrayList
```

`hasCharacteristics(...)` chỉ xác nhận **các cờ được yêu cầu có mặt**, không xác nhận rằng hai bitmask bằng nhau. Khi kiểm tra hợp đồng Supplier của `StreamSupport`, so sánh **toàn bộ** `actual == declaredFlags`, không chỉ `hasCharacteristics`.

## 5. Khi nào Supplier hữu ích hơn một Spliterator tạo sẵn?

Có ba tình huống thường gặp.

### 5.1. Nguồn cần được xác định tại thời điểm bắt đầu tiêu thụ

Ví dụ danh sách được chuẩn bị thêm dữ liệu trước khi chạy báo cáo:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));

Supplier<Spliterator<Integer>> source = numbers::spliterator;

Stream<Integer> pending = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

numbers.add(3); // Trước terminal operation.

int sum = pending.mapToInt(Integer::intValue).sum();

System.out.println(sum); // 6
```

Không thay đổi nguồn trong lúc `sum()` đang xử lý.

### 5.2. Tránh tạo Spliterator đắt đỏ khi không có terminal operation

Với một nguồn tự định nghĩa, việc tạo Spliterator có thể cần thiết lập cursor, ánh xạ metadata hoặc chuẩn bị công cụ duyệt. Trì hoãn bằng Supplier nghĩa là quá trình này **không cần chạy chỉ vì mã đã xây một pipeline rồi không dùng**.

```java
Supplier<Spliterator<String>> source = () -> {
    System.out.println("Bắt đầu chuẩn bị nguồn duyệt");
    return List.of("x", "y").spliterator();
};

Stream<String> unused = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

// Chưa gọi terminal operation: supplier có thể chưa được gọi.
unused.close();
```

Ví dụ dùng danh sách nhỏ chỉ để minh họa thời điểm tạo nguồn. Không nên dựa vào `close()` để buộc Supplier chạy; đóng một pipeline không yêu cầu phải gọi `supplier.get()`.

### 5.3. Thu hẹp thời gian nguồn có thể bị can thiệp

Nếu Spliterator tùy chỉnh *eagerly binds* với trạng thái nguồn khi được tạo, truyền nó quá sớm có thể khiến giữa lúc tạo Stream và lúc tiêu thụ có một khoảng thời gian dài mà dữ liệu nền đã thay đổi. Truyền Supplier giúp khởi tạo Spliterator muộn hơn, sát thời điểm thực thi.

Nhưng Supplier **không phải khóa đồng bộ** và không phải snapshot tự động. Nếu nhiều luồng cùng thay đổi một nguồn mutable, phải dùng cấu trúc concurrent, snapshot, khóa hoặc chính sách nhất quán riêng theo yêu cầu.

## 6. Nguồn kích thước không biết trước: dùng Spliterators.spliteratorUnknownSize

Không phải lúc nào nguồn cũng biết được số phần tử. Một `Iterator` có thể được chuyển thành Spliterator:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> events = List.of("START", "READ", "END");

Supplier<Spliterator<String>> source = () -> {
    Iterator<String> iterator = events.iterator();

    return Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
    );
};

Stream<String> stream = StreamSupport.stream(
    source,
    Spliterator.ORDERED | Spliterator.NONNULL,
    false
);

System.out.println(stream.toList()); // [START, READ, END]
```

Ở đây:

- `events.iterator()` được tạo **bên trong Supplier**, khi terminal operation yêu cầu nguồn.
- `spliteratorUnknownSize` có thể làm việc với iterator không biết trước số lượng phần tử.
- Không khai báo `SIZED` và `SUBSIZED` vì nguồn dùng cơ chế không biết kích thước.
- `NONNULL` chỉ hợp lệ vì `List.of(...)` trong ví dụ không chứa `null`.

`Spliterators.spliteratorUnknownSize` có cơ chế `trySplit` riêng, nhưng việc chia một Iterator thường có chi phí khác nguồn truy cập ngẫu nhiên và không bảo đảm tăng tốc khi chạy song song.

**Không được dùng một Iterator đã được tạo trước và chia sẻ cho nhiều Supplier/Stream độc lập** nếu ý định là mỗi lần phải duyệt từ đầu. Iterator có trạng thái vị trí; nguồn dùng một lần phải được mô tả đúng như nguồn dùng một lần.

## 7. Tự viết Spliterator có thể chia: ví dụ dải số nguyên

Khi thật sự cần nguồn tùy chỉnh, ta có thể tự cài đặt các phương thức cốt lõi:

- `tryAdvance(action)`: lấy tối đa một phần tử tiếp theo.
- `trySplit()`: tách một phần nguồn (hoặc trả `null` nếu không chia được).
- `estimateSize()`: ước lượng hoặc cung cấp kích thước chính xác.
- `characteristics()`: khai báo các bảo đảm của nguồn.
- `getComparator()`: cần đúng hợp đồng nếu nguồn có `SORTED`.

Ví dụ dưới xây một `Spliterator.OfInt` biểu diễn dải `[startInclusive, endExclusive)`, giới hạn đầu vào ở các số nguyên không âm. Nó không tạo sẵn một mảng số, cho phép chia dải thành **tiền tố** và **hậu tố** để xử lý song song.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class SupplierIntStreamDemo {
    static final int FLAGS =
          Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.SIZED
        | Spliterator.NONNULL
        | Spliterator.IMMUTABLE
        | Spliterator.SUBSIZED;

    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int endExclusive;

        IntRangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive < 0 || endExclusive < startInclusive) {
                throw new IllegalArgumentException("Invalid non-negative range");
            }
            this.cursor = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);

            if (cursor >= endExclusive) {
                return false;
            }

            int value = cursor++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = cursor;
            int mid = lo + ((endExclusive - lo) >>> 1);

            if (mid <= lo) {
                return null;
            }

            // Trả về tiền tố [lo, mid); this giữ hậu tố [mid, end).
            cursor = mid;
            return new IntRangeSpliterator(lo, mid);
        }

        @Override
        public long estimateSize() {
            return (long) endExclusive - cursor;
        }

        @Override
        public int characteristics() {
            return FLAGS;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // SORTED theo natural order.
            return null;
        }
    }

    public static void main(String[] args) {
        AtomicInteger end = new AtomicInteger(8);
        AtomicInteger supplierCalls = new AtomicInteger();

        Supplier<Spliterator.OfInt> source = () -> {
            supplierCalls.incrementAndGet();
            return new IntRangeSpliterator(0, end.get());
        };

        IntStream numbers = StreamSupport.intStream(
            source,
            FLAGS,
            true
        );

        System.out.println(supplierCalls.get()); // 0

        // Cập nhật bound trước khi terminal operation bắt đầu.
        end.set(10);

        int[] squares = numbers.map(n -> n * n).toArray();

        System.out.println(Arrays.toString(squares));
        // [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

        System.out.println(supplierCalls.get()); // 1
    }
}
```

### 7.1. Vì sao ví dụ đúng các characteristic đã khai báo?

- `ORDERED`: nguồn phát theo thứ tự số tăng; `trySplit` trả ra **tiền tố**, giữ hậu tố ở đối tượng hiện tại.
- `DISTINCT`: không số nào lặp trong dải.
- `SORTED`: tăng dần theo natural ordering; `getComparator()` trả `null` để biểu diễn natural order.
- `SIZED`: `estimateSize()` chính xác bằng số lượng phần tử còn lại.
- `SUBSIZED`: hai nửa sau khi chia tiếp tục giữ kích thước chính xác và cùng các cờ.
- `NONNULL`: Stream nguyên thủy `int` không có phần tử `null`.
- `IMMUTABLE`: dải số cố định trong mỗi Spliterator; biến `end` chỉ được lấy giá trị khi Supplier tạo Spliterator, không còn được dùng để sửa dải trong quá trình duyệt.

`FLAGS` truyền vào `StreamSupport.intStream` **giống hệt** `characteristics()` của `IntRangeSpliterator`. Khi chia, mỗi Spliterator con cũng trả về cùng bộ cờ.

### 7.2. Những lỗi chia dải dễ xảy ra

Một `trySplit` không đúng có thể gây:

- **Mất phần tử** nếu khoảng [lo, mid) hoặc [mid, hi) bị bỏ trống.
- **Trùng phần tử** nếu hai nhánh duyệt vùng giao nhau.
- **Sai encounter order** nếu trả hậu tố trong khi hứa trả tiền tố.
- **Sai `SIZED`** nếu kích thước khai báo không khớp số phần tử còn lại.
- **Vòng lặp hoặc chia vô hạn** nếu split không thu hẹp phạm vi.

Ví dụ trả `null` khi dải còn 0 hoặc 1 phần tử là cách dừng chia phù hợp. Kích thước phải giảm đúng sau `tryAdvance` và được chia đúng sau `trySplit`.

### 7.3. Tại sao không luôn viết Spliterator riêng?

Nếu đầu vào là danh sách hoặc mảng và chỉ cần dải số đơn giản, `IntStream.range(start, end)` ngắn và dễ bảo trì hơn ví dụ tự viết. Mục đích ở đây là **học hợp đồng source Spliterator** và cách truyền nó bằng Supplier, không phải thay thế mọi nguồn chuẩn.

## 8. Các overload Supplier cho Primitive Stream

`StreamSupport` còn hỗ trợ `IntStream`, `LongStream` và `DoubleStream` bằng các Spliterator chuyên biệt:

```java
StreamSupport.intStream(
    Supplier<? extends Spliterator.OfInt> supplier,
    int characteristics,
    boolean parallel
);

StreamSupport.longStream(
    Supplier<? extends Spliterator.OfLong> supplier,
    int characteristics,
    boolean parallel
);

StreamSupport.doubleStream(
    Supplier<? extends Spliterator.OfDouble> supplier,
    int characteristics,
    boolean parallel
);
```

Đây là cách tránh boxing không cần thiết khi nguồn vốn đã là số nguyên thủy. Ví dụ một Supplier phát một dải `int` qua Spliterator thư viện chuẩn:

```java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

int flags = Spliterator.ORDERED | Spliterator.SIZED
          | Spliterator.SUBSIZED | Spliterator.IMMUTABLE
          | Spliterator.NONNULL;

Supplier<Spliterator.OfInt> numbers = () ->
    Spliterators.spliterator(
        new int[] {10, 20, 30},
        Spliterator.ORDERED | Spliterator.IMMUTABLE | Spliterator.NONNULL
    );

// Spliterators.spliterator(int[], flags) còn bổ sung SIZED và SUBSIZED.
int total = StreamSupport.intStream(numbers, flags, false).sum();

System.out.println(total); // 60
```

Trong ví dụ, `Spliterators.spliterator(int[], characteristics)` bổ sung cờ `SIZED` và `SUBSIZED` cho nguồn mảng. Vì vậy `flags` phía ngoài phải chứa cả hai cờ, dù các cờ truyền vào lúc tạo Spliterator từ mảng chỉ cung cấp các đặc tính bổ sung.

**Lưu ý:** Nếu kiểu nguồn không đảm bảo `IMMUTABLE` (ví dụ mảng có thể bị luồng khác sửa trong lúc duyệt), không nên đặt cờ đó chỉ vì ví dụ hiện tại không sửa mảng. Với dữ liệu thư viện chuẩn, hãy xác minh chính xác characteristic của Spliterator mà factory trả về.

## 9. Những nhầm lẫn phổ biến về Supplier và tính lazy

### 9.1. Supplier không làm Stream dùng lại được

```java
Supplier<Spliterator<String>> factory =
    () -> List.of("A", "B").spliterator();

int flags = Spliterator.ORDERED | Spliterator.SIZED
          | Spliterator.SUBSIZED;

Stream<String> stream = StreamSupport.stream(factory, flags, false);

System.out.println(stream.count()); // 2
// stream.toList(); // Không hợp lệ: Stream đã được tiêu thụ.
```

Supplier có thể được dùng để **tạo một Stream mới** mỗi khi cần chạy lại:

```java
java.util.function.Supplier<Stream<String>> freshStream = () ->
    StreamSupport.stream(factory, flags, false);

System.out.println(freshStream.get().count()); // 2
System.out.println(freshStream.get().toList()); // [A, B]
```

Điều này chỉ an toàn khi Supplier Spliterator có thể tạo một nguồn mới hoặc nguồn cho phép duyệt lại. Với kết nối, Iterator chỉ dùng một lần hay giao dịch I/O, không thể giả định dữ liệu có thể được đọc lại.

### 9.2. “Late-binding Supplier” không đồng nghĩa snapshot

Nếu Supplier đọc danh sách mutable, thay đổi **trước** terminal operation có thể được phản ánh trong nguồn được lấy muộn. Nhưng nếu một luồng khác thay đổi danh sách **trong lúc duyệt**, vẫn có nguy cơ can thiệp. Muốn snapshot ổn định, có thể tạo một bản sao **trong Supplier**, nếu chi phí bộ nhớ và yêu cầu nghiệp vụ cho phép:

```java
List<String> mutable = new ArrayList<>(List.of("A", "B"));

Supplier<Spliterator<String>> snapshotSource = () ->
    List.copyOf(mutable).spliterator();
```

Với nguồn ảnh chụp này, các thay đổi sau lúc bản sao được tạo không làm thay đổi tập phần tử của Spliterator đã nhận. Tuy nhiên, nếu dữ liệu được cập nhật đồng thời **ngay trong lúc tạo bản sao** mà không có đồng bộ, việc copy nguồn mutable chưa chắc an toàn; snapshot đúng cần cách đồng bộ hoặc cấu trúc lưu trữ phù hợp.

**Chú ý đặc tính:** Khi thay `ArrayList.spliterator()` bằng `List.copyOf(...).spliterator()`, không được tự suy bộ cờ từ Spliterator cũ. Cần bảo đảm `characteristics` truyền cho `StreamSupport` đúng với thực thể mới.

### 9.3. Supplier chỉ trì hoãn *lấy Spliterator*, không nhất thiết trì hoãn mọi tài nguyên

Nếu bên ngoài đã mở tệp hoặc kết nối và chỉ gói `reader` đang mở bằng Supplier, tài nguyên đó vẫn được mở sớm. Muốn trì hoãn cả việc mở tài nguyên, logic mở phải nằm ở thời điểm thích hợp **và** cần thiết kế cơ chế đóng, xử lý ngoại lệ khi khởi tạo thất bại.

Không gọi một pipeline là “không giữ tài nguyên” chỉ vì nó dùng Supplier.

## 10. Quản lý tài nguyên khi Spliterator tự định nghĩa đọc I/O

`StreamSupport.stream(supplier, flags, parallel)` **không tự biến một nguồn I/O thành tài nguyên tự giải phóng sau terminal operation**. Nếu Spliterator duyệt tệp, socket, kết nối hoặc một cursor phải đóng, API phải xác định quyền sở hữu và thời điểm đóng.

Đối với tệp văn bản thông thường, thường nên dùng nguồn chuẩn:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("input.txt"))) {
    long count = lines
        .filter(s -> !s.isBlank())
        .count();

    System.out.println(count);
}
```

Nếu buộc phải dùng Spliterator tùy chỉnh, có thể gắn `onClose` cho Stream trả về để giải phóng tài nguyên; **bên gọi vẫn phải đóng Stream**, lý tưởng bằng `try-with-resources`. Một thiết kế đúng phải xét cả trường hợp:

1. Terminal operation xử lý hết phần tử.
2. Terminal operation dừng sớm (`findFirst`, `anyMatch`, `limit`).
3. Supplier/`tryAdvance` ném ngoại lệ.
4. Stream được đóng khi Supplier **chưa được gọi**.
5. Có lỗi ở bước mở nguồn hoặc khi close handler thực thi.

Ví dụ `onClose` cơ bản với một nguồn không có I/O:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

AtomicInteger closeCount = new AtomicInteger();

try (Stream<String> items = StreamSupport.stream(
        () -> List.of("x", "y").spliterator(),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
        false
    ).onClose(closeCount::incrementAndGet)) {
    System.out.println(items.findFirst().orElse("none")); // x
}

System.out.println(closeCount.get()); // 1
```

Handler ở đây chỉ đếm việc đóng để minh họa; nó **không đại diện** cho cơ chế đóng tệp. Với tài nguyên thật, gắn close handler phù hợp và có cơ chế tránh rò rỉ trong trường hợp Supplier khởi tạo thất bại. `onClose` không tự chạy sau `sum()`, `count()` hoặc `toList()` nếu không có `close()`.

## 11. Xử lý song song: Supplier không thay thế `trySplit`

Tham số `parallel = true` là yêu cầu tạo một parallel Stream, không cam kết nguồn chia được tốt hoặc chắc chắn nhanh hơn.

Để phân chia hiệu quả, `trySplit` cần:

- Trả về một Spliterator chứa **một phần phần tử chưa duyệt**, không trùng lặp với phần còn lại.
- Tiến gần đến bài toán nhỏ hơn sau mỗi lần chia; tránh split quá nhỏ hoặc không cân bằng.
- Giữ các đặc tính đã khai báo, đặc biệt `ORDERED`, `SIZED` và `SUBSIZED` nếu có.
- Không dùng cùng một cursor mutable từ nhiều nhánh mà không có cơ chế an toàn phù hợp.

Một Spliterator không chia được có thể cài đặt:

```java
@Override
public Spliterator<T> trySplit() {
    return null;
}
```

Nguồn như vậy vẫn tạo được Stream với `parallel = true`, nhưng khả năng khai thác nhiều tác vụ song song sẽ bị hạn chế.

### Khi nào `CONCURRENT` có ý nghĩa?

Chỉ khai báo `Spliterator.CONCURRENT` khi **nguồn** hỗ trợ sửa đổi đồng thời theo đúng ngữ nghĩa dữ liệu. Cờ này không làm `ArrayList` trở thành thread-safe, cũng không cho phép accumulator của `reduce`/`collect` sửa một biến dùng chung thiếu đồng bộ.

Nếu dùng `collect` trên nguồn tự viết, các collector vẫn phải tuân thủ hợp đồng về identity, associativity, supplier/accumulator/combiner và trạng thái chia sẻ. Sự có mặt của Supplier Spliterator không thay đổi các hợp đồng đó.

### Phối hợp với Stream Gatherers

Stream Gatherers phù hợp cho những biến đổi trung gian có trạng thái ở các JDK hỗ trợ, còn Spliterator chịu trách nhiệm **nguồn phát phần tử** và khả năng tách nguồn. Không cần triển khai Gatherer chỉ để tạo Stream từ một Spliterator. Nên lựa chọn cấu trúc đơn giản nhất đáp ứng yêu cầu nguồn và pipeline.

## 12. Kiểm tra tính đúng của nguồn tự định nghĩa

Khi phát triển Spliterator tùy chỉnh, nên kiểm tra trước các thuộc tính về **tập phần tử**, **thứ tự**, **kích thước** và **chia nguồn** rồi mới xét hiệu năng.

### 12.1. So sánh tuần tự và song song

Với ví dụ `SupplierIntStreamDemo`, cùng một dải số phải cho cùng danh sách phần tử nếu giữ `ORDERED`:

```java
int[] sequential = StreamSupport.intStream(
    () -> new SupplierIntStreamDemo.IntRangeSpliterator(0, 100),
    SupplierIntStreamDemo.FLAGS,
    false
).toArray();

int[] parallel = StreamSupport.intStream(
    () -> new SupplierIntStreamDemo.IntRangeSpliterator(0, 100),
    SupplierIntStreamDemo.FLAGS,
    true
).toArray();

System.out.println(java.util.Arrays.equals(sequential, parallel)); // true
System.out.println(sequential.length); // 100
```

Thử tương tự với các độ dài 0, 1, 2, 3, 10, 1000 và các điểm chia lẻ để bắt lỗi `trySplit`.

### 12.2. Kiểm tra chính xác flags

```java
Spliterator.OfInt actual =
    new SupplierIntStreamDemo.IntRangeSpliterator(0, 10);

if (actual.characteristics() != SupplierIntStreamDemo.FLAGS) {
    throw new IllegalStateException("Declared characteristics differ");
}
```

Không nên kiểm tra bằng cách gọi `supplier.get()` thêm lần nữa rồi mặc định lần gọi ấy là “của Stream”; việc kiểm tra bên ngoài có thể tạo nguồn thừa hoặc gây tác dụng phụ. Với một factory được thiết kế riêng, có thể xây instance kiểm tra độc lập trong thử nghiệm.

### 12.3. Kiểm tra việc gọi Supplier

```java
AtomicInteger calls = new AtomicInteger();

Supplier<Spliterator<String>> factory = () -> {
    calls.incrementAndGet();
    return List.of("A", "B").spliterator();
};

Stream<String> stream = StreamSupport.stream(
    factory,
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

System.out.println(calls.get()); // 0
System.out.println(stream.toList()); // [A, B]
System.out.println(calls.get()); // 1
```

Chỉ quan sát số lần gọi Supplier; **không dùng tác dụng phụ của `tryAdvance` để chứng minh tất cả terminal operation đã duyệt từng phần tử**, bởi một số terminal operation có thể dựa vào kích thước đã biết hoặc tối ưu pipeline.

## 13. Hiệu năng và đánh đổi thiết kế

| Chọn lựa | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Truyền Spliterator trực tiếp | Ngắn gọn, không cần biết trước flags trong call site | Spliterator đã được tạo trước khi Stream bắt đầu |
| Truyền Supplier | Tạo/lấy nguồn muộn, giảm cửa sổ bị can thiệp trước terminal | Phải cung cấp flags chính xác và thiết kế source factory cẩn thận |
| Spliterator `SIZED`/`SUBSIZED` đúng hợp đồng | Có thể hỗ trợ lập kế hoạch chia và tối ưu terminal operations | Sai flags làm kết quả không đáng tin |
| Spliterator chia dải cân bằng | Dễ phân phối công việc trên nhiều nhánh | Code nguồn phức tạp hơn và cần thử kỹ edge cases |
| Spliterator từ Iterator không biết size | Dễ tạo nguồn từ iterator tùy chỉnh | Khó dự đoán kích thước; split có thể tốn chi phí |
| Materialize thành `List` rồi gọi `stream()` | Dễ dùng, dựa vào nguồn chuẩn | Cần bộ nhớ cho toàn bộ dữ liệu và phải tải trước |
| Đọc I/O lazy với Stream | Giảm bộ nhớ khi xử lý tuần tự | Phải quản lý close, lỗi duyệt và vòng đời cursor |

Không có lợi ích hiệu năng mặc định chỉ vì dùng Supplier. Khi đã có `List`, lời gọi `list.stream()` thường đơn giản và phù hợp hơn. Chỉ dùng `StreamSupport` nếu cần nguồn riêng hoặc kiểm soát rõ hành vi `Spliterator`.

Đối với workload lớn, đo thời gian, số phần tử thực sự duyệt, mức độ chia, bộ nhớ và độ tranh chấp bằng phép đo đại diện như JMH. Đừng giả định xử lý song song luôn nhanh: chi phí chia/gộp và đặc tính nguồn có thể lớn hơn lợi ích.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `characteristics = 0` chỉ vì không biết flags trong khi Supplier trả nguồn có flags khác 0 | Vi phạm hợp đồng đặc tính bằng nhau | Cung cấp bitmask đúng với `spliterator.characteristics()` |
| Khai báo `SIZED` cho Iterator không biết kích thước | Tối ưu sai, kết quả không đáng tin | Không khai báo `SIZED` khi không bảo đảm số phần tử |
| Khai báo `IMMUTABLE` cho nguồn mutable có thể sửa đồng thời | Diễn giải sai tính ổn định nguồn | Bỏ flag hoặc thiết kế snapshot/nguồn bất biến đúng nghĩa |
| Khai báo `SORTED` nhưng `getComparator` không tuân thủ | Vi phạm hợp đồng `Spliterator` | Trả comparator hợp lệ hoặc `null` khi natural ordering |
| Cho rằng `Supplier.get()` chạy ngay lúc `StreamSupport.stream(...)` | Logic khởi tạo bị đặt sai thời điểm | Chờ terminal operation; kiểm tra bằng phép đếm Supplier |
| Cho rằng Supplier làm Stream dùng lại nhiều lần | `IllegalStateException` khi tiêu thụ lại | Tạo Stream mới cho mỗi lượt xử lý |
| Dùng cùng một Iterator/cursor cho hai Stream độc lập | Nguồn bị tiêu thụ từ lượt đầu | Tạo cursor mới khi nguồn cho phép hoặc ghi rõ one-shot source |
| Chia dải nhưng trùng/bỏ phần tử ở `trySplit` | Sai kết quả, nhất là khi song song | Kiểm tra dải chia không trùng, không mất |
| Dùng `parallel = true` dù `trySplit()` luôn trả `null` rồi kỳ vọng tăng tốc | Song song bị hạn chế | Thiết kế split hiệu quả hoặc dùng tuần tự |
| Sửa `ArrayList` trong lúc Stream đang chạy | Concurrent modification hoặc hành vi không bảo đảm | Kết thúc cập nhật trước terminal hoặc dùng nguồn phù hợp |
| Coi nguồn I/O tự đóng sau `count()`/`findFirst()` | Rò rỉ tài nguyên | Dùng `try-with-resources`, `onClose` đúng ownership |
| Tạo Supplier mở tệp mà không có cơ chế cleanup khi lỗi | Rò rỉ trong bước khởi tạo hoặc duyệt | Thiết kế vòng đời và xử lý ngoại lệ đầy đủ |
| Cho rằng `Spliterator.CONCURRENT` cho phép mọi lambda sửa biến chung | Race condition trong các giai đoạn pipeline | Tách hợp đồng nguồn với hợp đồng trạng thái collector |
| Dùng `tryAdvance` để đếm các lần terminal operation phải chạy | Sai khi có tối ưu nhờ `SIZED` | Đánh giá qua kết quả, không dựa tác dụng phụ duyệt |

## 15. Bài tập thực hành

### Bài 1: Xác định thời điểm Supplier chạy

Tạo một `Supplier<Spliterator<String>>` tăng `AtomicInteger`, dùng `StreamSupport.stream(supplier, flags, false)` rồi thêm `filter`, `map`. Dự đoán bộ đếm trước và sau `toList()`. Vì sao Supplier không cần chạy khi chỉ xây pipeline?

### Bài 2: So sánh hai overload

Viết hai Stream từ cùng một `ArrayList`: một Stream nhận `list.spliterator()` và một Stream nhận `list::spliterator`. Cho danh sách thay đổi **trước** terminal operation; giải thích giới hạn của mỗi thiết kế. Tránh khẳng định mọi Spliterator trực tiếp luôn bị cố định dữ liệu ở thời điểm tạo.

### Bài 3: Khai báo flags chính xác

Xây Supplier dùng `Spliterators.spliteratorUnknownSize(iterator, ORDERED | NONNULL)`. Xác định `characteristics` cần truyền cho `StreamSupport.stream`. Vì sao không nên đặt `SIZED`?

### Bài 4: Tạo dải số có thể chia

Dựa trên `IntRangeSpliterator`, thử dải [0, 0), [0, 1), [0, 2), [0, 7) và [5, 20). So sánh kết quả tuần tự/song song; xác minh không mất hoặc trùng số và kích thước cuối bằng số phần tử dự kiến.

### Bài 5: Bắt lỗi khai báo `SORTED`

Tạo một Spliterator phát giá trị theo thứ tự 3, 1, 2 nhưng khai báo `SORTED`. Giải thích vì sao đây là vi phạm hợp đồng, kể cả khi Stream có thêm `sorted()` sau đó. Nêu cách sửa flags hoặc sửa logic nguồn.

### Bài 6: Nguồn dữ liệu thay đổi trước và trong terminal operation

Tạo Supplier dựa trên `ArrayList`. Bổ sung một phần tử trước `toList()` và quan sát kết quả. Sau đó phân tích **trên giấy** rủi ro nếu một luồng khác sửa danh sách khi pipeline đang chạy; không cần tạo một thử nghiệm race condition không ổn định.

### Bài 7: Thiết kế nguồn I/O

Mô tả một API trả `Stream<String>` từ Spliterator đọc tệp: ai mở, ai đóng, nơi gắn `onClose`, làm gì khi `supplier.get()` ném lỗi, và lý do `findFirst()` không tự thay thế `close()`. So sánh với `Files.lines(path)`.

### Bài 8: Chọn nguồn và cách xử lý

Với 1 triệu số nguyên đã nằm sẵn trong `int[]`, chọn giữa `Arrays.stream(array)`, `StreamSupport.intStream(arraySpliterator, false)` và tự viết Spliterator + Supplier. Khi nào lựa chọn phức tạp hơn có giá trị? Nêu điều kiện phải đo trước khi bật parallel.

## 16. Tự kiểm tra kiến thức

- Overload `StreamSupport.stream(Supplier, characteristics, parallel)` khác overload nhận Spliterator trực tiếp ở thời điểm nào?
- `Supplier.get()` được phép gọi tối đa bao nhiêu lần cho một Stream?
- Vì sao `characteristics` bên ngoài phải bằng đúng `supplier.get().characteristics()`?
- `ORDERED` và `SORTED` khác nhau ra sao? Khi nào `getComparator()` được trả `null`?
- `SIZED` và `SUBSIZED` tạo yêu cầu gì đối với `estimateSize()` và `trySplit()`?
- Vì sao Supplier không tự biến nguồn mutable thành snapshot an toàn?
- `trySplit()` phải chia phần tử thế nào để không trùng, mất hoặc sai encounter order?
- Khi nào chọn `Spliterator.OfInt` và `StreamSupport.intStream`?
- Vì sao không được sử dụng lại cùng Stream sau khi đã gọi `sum()` hoặc `collect()`?
- Dùng Supplier có thay đổi trách nhiệm đóng nguồn I/O không?
- Vì sao `parallel = true` không đủ để bảo đảm tăng tốc?
- Có thể kiểm tra thời điểm gọi Supplier mà không phụ thuộc các tác dụng phụ của `tryAdvance` bằng cách nào?

**Ghi nhớ:** Overload `StreamSupport.stream(supplier, characteristics, parallel)` trì hoãn việc **lấy Spliterator** tới lúc bắt đầu terminal operation, nhưng **không** làm Stream tái sử dụng được, không tự tạo snapshot và không tự đóng I/O. Quan trọng nhất là khai báo `characteristics` **đúng bằng** đặc tính của Spliterator thực tế và bảo đảm `tryAdvance`, `trySplit`, kích thước, thứ tự, quyền sở hữu và trạng thái nguồn tuân thủ hợp đồng. Khi nguồn chuẩn đã đáp ứng đủ, hãy ưu tiên API tạo Stream đơn giản thay vì tự viết Spliterator.
