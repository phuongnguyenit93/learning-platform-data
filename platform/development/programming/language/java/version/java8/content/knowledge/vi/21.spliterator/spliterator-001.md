# Spliterator và quan hệ với Iterator trong Java

## 1. Học gì từ bài này?

`Iterator<E>` và `Spliterator<T>` đều giúp **duyệt tuần tự các phần tử** của một nguồn dữ liệu. Điểm khác biệt có ý nghĩa nhất: `Spliterator` còn có khả năng **chia phần dữ liệu chưa xử lý** để phục vụ thuật toán xử lý song song, đồng thời công bố các đặc tính của nguồn như có thứ tự, biết chính xác kích thước hay không.

Sau bài này, bạn có thể:

- Giải thích hai hợp đồng duyệt dữ liệu và chọn `Iterator` hay `Spliterator` phù hợp.
- Dùng `hasNext()/next()`, `tryAdvance(...)`, `forEachRemaining(...)` và `trySplit()` đúng cách.
- Hiểu `estimateSize()`, `getExactSizeIfKnown()` và các cờ `characteristics()`.
- Liên hệ `Collection.spliterator()` với `StreamSupport.stream(...)` và parallel stream.
- Chuyển giữa `Iterator` và `Spliterator`, sử dụng `Spliterator.OfInt` để tránh boxing.
- Nhận biết giới hạn về thứ tự, thay đổi collection, chia sẻ giữa các thread và lỗi khi tự xây dựng Spliterator.

`Iterator` là API lâu đời của Java Collections, còn `Spliterator` và Java Stream được giới thiệu trong Java 8. **Cả hai vẫn là API hiện hành**. Các ví dụ độc lập trong bài sử dụng Java 17+ (cú pháp `List.of` và `Stream.toList` là các API hiện đại); phần cơ chế cốt lõi của `Spliterator` vẫn có từ Java 8.

## 2. Trực giác: duyệt từng phần tử và chia việc

Giả sử nguồn có sáu số:

```text
Nguồn: [10, 20, 30, 40, 50, 60]

Iterator
    hasNext()?  →  next() → 10
    hasNext()?  →  next() → 20
    ... cho đến hết

Spliterator
    tryAdvance(action) → áp dụng action cho tối đa một phần tử
    forEachRemaining(action) → xử lý toàn bộ phần còn lại
    trySplit() → nếu có thể, tách phần chưa duyệt thành hai vùng không trùng nhau
```

`Iterator` cung cấp giao thức **pull**: bên gọi hỏi còn phần tử không (`hasNext`), rồi lấy phần tử (`next`). `Spliterator` cung cấp giao thức **push-to-action**: bên gọi đưa một `Consumer`, còn Spliterator chuyển phần tử tới action khi gọi `tryAdvance`.

`trySplit()` bổ sung khả năng **phân rã công việc**. Một thuật toán song song có thể tiếp tục chia các phần dữ liệu rồi giao **mỗi Spliterator riêng** cho một worker. Không cần lập trình viên phải tự viết `trySplit` khi chỉ dùng Stream từ các collection chuẩn: thư viện Stream đã tích hợp cơ chế đó.

**Điểm quan trọng:** `Spliterator` là nền tảng cho việc triển khai Stream; nó **không đồng nghĩa** với một Stream và cũng **không tự tạo thread**. Gọi `trySplit()` chỉ trả thêm đối tượng duyệt nếu nguồn hỗ trợ chia, còn thực hiện song song là trách nhiệm của tầng thuật toán bên trên.

## 3. So sánh hợp đồng của `Iterator` và `Spliterator`

| Nội dung | `Iterator<E>` | `Spliterator<T>` |
| --- | --- | --- |
| Mục tiêu chính | Duyệt phần tử lần lượt | Duyệt và có thể chia phần chưa duyệt |
| Lấy từng phần tử | `hasNext()` rồi `next()` | `tryAdvance(Consumer)` |
| Duyệt toàn bộ phần còn lại | `forEachRemaining(Consumer)` (từ Java 8) | `forEachRemaining(Consumer)` |
| Cách báo hết dữ liệu | `hasNext() == false`; gọi `next()` sau đó ném `NoSuchElementException` | `tryAdvance(...) == false` |
| Chia dữ liệu | Không có API tương đương trong `Iterator` | `trySplit()`, có thể trả `null` |
| Kích thước/đặc tính | Không có contract trực tiếp | `estimateSize`, `getExactSizeIfKnown`, `characteristics` |
| Xóa phần tử qua đối tượng duyệt | `remove()` là **optional operation** | Không có `remove()` |
| Dùng với Stream | Có thể chuyển bằng `Spliterators` | Đưa trực tiếp vào `StreamSupport` |
| Song song | Bản thân API không tổ chức phân rã | Hỗ trợ phân rã; bản thân một Spliterator **không được giả định thread-safe** |

Cả hai là cơ chế tiêu thụ dữ liệu một lượt theo vị trí đang duyệt. Sau khi đã đọc hết một đối tượng `Iterator` hoặc `Spliterator`, muốn duyệt lại nguồn thì tạo đối tượng duyệt mới (nếu nguồn cho phép); không có API “reset” tổng quát.

`Iterator.remove()` không được mọi iterator hỗ trợ: ví dụ iterator của `List.of(...)` không cho phép xóa. `ListIterator` (mở rộng `Iterator`) còn hỗ trợ duyệt hai chiều và chỉnh sửa có điều kiện; đó là chức năng riêng, không phải mục tiêu của `Spliterator`.

## 4. Duyệt cơ bản: `hasNext()/next()` so với `tryAdvance()`

Lưu thành `IteratorAndSpliteratorDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.StringJoiner;

public class IteratorAndSpliteratorDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        Iterator<String> it = names.iterator();
        StringJoiner joined = new StringJoiner(", ");
        while (it.hasNext()) {
            joined.add(it.next());
        }
        System.out.println("Iterator: " + joined);

        Spliterator<String> sp = names.spliterator();
        boolean advanced = sp.tryAdvance(
                name -> System.out.println("first: " + name));
        System.out.println("advanced: " + advanced);

        sp.forEachRemaining(
                name -> System.out.println("rest: " + name));

        boolean hasMore = sp.tryAdvance(
                name -> System.out.println("unexpected: " + name));
        System.out.println("hasMore: " + hasMore);
    }
}
```

Biên dịch/chạy:

```bash
javac IteratorAndSpliteratorDemo.java
java IteratorAndSpliteratorDemo
```

Đầu ra chính xác:

```text
Iterator: An, Binh, Chi
first: An
advanced: true
rest: Binh
rest: Chi
hasMore: false
```

Giải thích:

1. `hasNext()` kiểm tra phần còn lại, `next()` trả đối tượng; vòng lặp thực hiện ba lần.
2. `sp.tryAdvance(action)` gọi action đúng một lần nếu còn phần tử rồi trả `true`. Vì nguồn `List` có encounter order, phần tử đầu là `An`.
3. `sp.forEachRemaining(action)` xử lý **phần chưa tiêu thụ** — chỉ còn `Binh` và `Chi`.
4. Sau khi hết, `tryAdvance` trả `false` và **không gọi action**.

`Consumer<? super T>` là đối số bắt buộc của `tryAdvance` và `forEachRemaining`. Truyền `null` sẽ ném `NullPointerException`. Nếu action ném exception, ngoại lệ được chuyển ra cho bên gọi, và theo hợp đồng `Spliterator`, hành vi tiếp theo sau ngoại lệ action không được xác định. Không dựa vào việc có thể “tiếp tục an toàn” từ một trạng thái còn lại.

Có thể viết `Iterator.forEachRemaining(System.out::println)` trên Iterator (đây là default method từ Java 8), nhưng nó vẫn **không** bổ sung khả năng chia hoặc công bố kích thước/chuyên tính như Spliterator.

## 5. `trySplit()` hoạt động như thế nào?

Chữ ký:

```java
Spliterator<T> trySplit();
```

Đây là chữ ký của interface, không phải chương trình biên dịch độc lập.

Khi thành công, `trySplit()` trả một Spliterator mới bao phủ **một phần các phần tử còn lại**, còn Spliterator hiện tại giữ phần còn lại không trùng nhau. Nếu nguồn có đặc tính `ORDERED` thì phần được trả ra phải là **prefix** nghiêm ngặt của phần chưa xử lý. Thuật toán có thể đưa hai đối tượng duyệt cho hai tác vụ khác nhau.

`trySplit()` có quyền trả `null`, kể cả khi vẫn còn phần tử, ví dụ nguồn không hỗ trợ chia hiệu quả hoặc đã duyệt một phần. **Không mặc định nó chia đúng 50/50** và không lấy kích thước phần con làm ràng buộc nghiệp vụ.

Minh họa:

```text
Trước: Spliterator A -> [10, 20, 30, 40, 50, 60]

A.trySplit() trả B (nếu chia thành công):

    B (prefix) -> [10, 20, 30]
    A          -> [40, 50, 60]

Sau khi duyệt B và A: đủ sáu phần tử, không bị lặp.
```

Hình là một **khả năng phân chia minh họa**, không phải một cam kết tỷ lệ chia. Chạy chương trình sau để thấy việc ghép các phần không mất dữ liệu mà không phụ thuộc cách chia cụ thể.

Lưu `SpliteratorSplitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSplitDemo {
    public static void main(String[] args) {
        List<Integer> original = List.of(10, 20, 30, 40, 50, 60);

        Spliterator<Integer> remainder = original.spliterator();
        Spliterator<Integer> prefix = remainder.trySplit();

        List<Integer> combined = new ArrayList<>();
        if (prefix != null) {
            prefix.forEachRemaining(combined::add);
        }
        remainder.forEachRemaining(combined::add);

        System.out.println("combined = " + combined);
        System.out.println("complete = " + combined.equals(original));
    }
}
```

```bash
javac SpliteratorSplitDemo.java
java SpliteratorSplitDemo
```

```text
combined = [10, 20, 30, 40, 50, 60]
complete = true
```

Trường hợp `trySplit() == null`, đối tượng `remainder` vẫn có thể duyệt toàn bộ dữ liệu. Trường hợp chia được, ta duyệt phần `prefix` **trước** `remainder` để duy trì encounter order (vì đây là Spliterator có thứ tự của `List`). Ví dụ là phép duyệt tuần tự để dễ quan sát; trong thuật toán parallel, hai Spliterator khác nhau có thể được xử lý đồng thời, rồi kết quả được kết hợp theo quy tắc của thuật toán.

Không gọi các thao tác split/traverse **đồng thời trên cùng một Spliterator**. Hợp đồng của Spliterator không yêu cầu chính đối tượng đó phải thread-safe. `CONCURRENT` (nếu có) mô tả khả năng thay đổi **nguồn dữ liệu** an toàn trong lúc duyệt, không phải giấy phép cho nhiều thread cùng điều khiển một con trỏ Spliterator.

## 6. Các phương thức để ước lượng kích thước

- `long estimateSize()`: ước lượng số phần tử còn lại. Khi không biết số lượng hoặc quá tốn chi phí để tính, có thể trả `Long.MAX_VALUE`.
- `long getExactSizeIfKnown()`: nếu Spliterator có `SIZED`, trả `estimateSize()` theo contract; nếu không có `SIZED`, trả `-1`.
- `boolean hasCharacteristics(int bits)`: kiểm tra có **đủ tất cả** các cờ yêu cầu hay không.
- `int characteristics()`: bitmask kết hợp các cờ nguồn/đặc tính có nghĩa.

Điều cần nhớ về `SIZED`: trước khi duyệt hoặc chia, ước lượng của một Spliterator có cờ này phải phản ánh chính xác số phần tử (ngoại lệ theo contract liên quan nguồn/đặc tính concurrency và sau một số thao tác). `SUBSIZED` đảm bảo các Spliterator con từ `trySplit` cũng có `SIZED` và `SUBSIZED`. Không suy luận rằng một Spliterator chỉ có `SIZED` sẽ luôn tách ra các phần con biết trước kích thước.

Ví dụ ổn định từ Spliterator của mảng số nguyên và từ iterator không biết trước độ dài. Lưu `SpliteratorSizeDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

public class SpliteratorSizeDemo {
    public static void main(String[] args) {
        Spliterator.OfInt known =
                Arrays.spliterator(new int[] {3, 5, 8});

        System.out.println("ordered = " +
                known.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("sized = " +
                known.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized = " +
                known.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("exact = " + known.getExactSizeIfKnown());

        Spliterator<Integer> unknown =
                Spliterators.spliteratorUnknownSize(
                        List.of(3, 5, 8).iterator(),
                        Spliterator.ORDERED);
        System.out.println("unknownExact = " +
                unknown.getExactSizeIfKnown());
    }
}
```

```bash
javac SpliteratorSizeDemo.java
java SpliteratorSizeDemo
```

```text
ordered = true
sized = true
subsized = true
exact = 3
unknownExact = -1
```

`Spliterators.spliteratorUnknownSize` không đặt `SIZED`/`SUBSIZED` khi kích thước đầu vào không biết trước. Giá trị `-1` của `getExactSizeIfKnown()` **không** phải số phần tử âm; nó nghĩa là contract chưa công bố kích thước chính xác.

## 7. Hiểu đúng tám characteristics

Cờ `Spliterator` mô tả nguồn và giúp Stream thực hiện các tối ưu hợp lệ. Khi viết custom Spliterator, chỉ khai báo cờ mà implementation thật sự đáp ứng.

| Cờ | Ý nghĩa thực dụng | Nhầm lẫn cần tránh |
| --- | --- | --- |
| `ORDERED` | Có encounter order xác định; `tryAdvance`/`forEachRemaining` tuân theo thứ tự này; phần split trả về là prefix | Không có nghĩa parallel `forEach` bắt buộc chạy action theo thứ tự |
| `DISTINCT` | Các phần tử là duy nhất theo `equals` | Không có nghĩa đã sắp xếp |
| `SORTED` | Các phần tử đã sắp xếp theo một comparator hoặc thứ tự tự nhiên; đồng thời phải `ORDERED` | Không phải cứ `ORDERED` là `SORTED` |
| `SIZED` | Biết chính xác số phần tử theo các điều kiện của contract | Không suy ra tất cả Spliterator con đều `SIZED` |
| `NONNULL` | Không chứa phần tử `null` | Không suy ra object phần tử là bất biến |
| `IMMUTABLE` | Nguồn không thể bị thay đổi **cấu trúc** trong khi duyệt | Không cam kết các trường bên trong từng object không thể thay đổi |
| `CONCURRENT` | Nguồn hỗ trợ sửa đổi đồng thời theo chính sách đã công bố | Không đảm bảo bản thân Spliterator an toàn khi nhiều thread gọi cùng lúc |
| `SUBSIZED` | Spliterator này và mọi con tạo từ `trySplit` đều `SIZED`/`SUBSIZED` | Không có nghĩa chiến lược split luôn cân bằng |

`SORTED` gắn với `getComparator()`: nếu có `SORTED` và thứ tự tự nhiên thì phương thức thường trả `null`; nếu có comparator riêng thì trả comparator; nếu không có `SORTED` thì `getComparator()` ném `IllegalStateException`. Giá trị `null` ở đây có ý nghĩa **natural ordering**, không phải “không biết” khi Spliterator đã được xác định là `SORTED`.

Các cờ có thể khác nhau theo **loại nguồn và implementation**. Không suy đoán “mọi `List` là `IMMUTABLE`”, “mọi `Set` là `SORTED`” hay “Stream parallel thì Spliterator có `CONCURRENT`”. `List.of(...)` không cho chỉnh sửa collection; tuy nhiên khi cần xác minh một cờ cụ thể của loại nguồn, hãy gọi `hasCharacteristics(...)` hoặc đọc hợp đồng của implementation.

Hệ quả cho code: nếu thuật toán thật sự cần dữ liệu tăng dần, hãy dùng `sorted()`/nguồn có contract sorted. Nếu cần thứ tự duyệt khi parallel, dùng terminal operation tôn trọng encounter order như `forEachOrdered` hoặc collector giữ thứ tự; **không chỉ kiểm tra `ORDERED` rồi gọi `forEach`**.

## 8. Quan hệ giữa `Spliterator` và Stream

Khi gọi `Collection.stream()` hoặc `parallelStream()`, thư viện tạo pipeline từ dữ liệu của collection, sử dụng Spliterator (hoặc nguồn tương đương có semantics phù hợp) trong triển khai. Đối với một nguồn tự viết, bạn có thể tạo Stream từ Spliterator bằng:

```java
Stream<T> StreamSupport.stream(Spliterator<T> spliterator, boolean parallel)
```

Đây là cách trình bày chữ ký API, không phải dòng code dùng trực tiếp. Tham số `parallel` chọn **kiểu pipeline**: `false` là tuần tự, `true` là song song. Không hứa rằng lời gọi sẽ tạo thread hay nhanh hơn; xử lý chỉ bắt đầu khi có terminal operation.

Lưu `SpliteratorStreamDemo.java`:

```java
import java.util.List;
import java.util.stream.StreamSupport;

public class SpliteratorStreamDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        int sum = StreamSupport
                .stream(numbers.spliterator(), true)
                .mapToInt(Integer::intValue)
                .sum();

        List<Integer> squares = StreamSupport
                .stream(numbers.spliterator(), true)
                .map(n -> n * n)
                .toList();

        System.out.println("sum = " + sum);
        System.out.println("squares = " + squares);
    }
}
```

```bash
javac SpliteratorStreamDemo.java
java SpliteratorStreamDemo
```

```text
sum = 10
squares = [1, 4, 9, 16]
```

`StreamSupport.stream(..., true)` cho phép Stream parallel; `sum` không phụ thuộc thứ tự ở các giá trị nhỏ này; `toList()` duy trì encounter order của một ordered Stream. `Stream.toList()` có từ **Java 16** và trả danh sách không thể chỉnh sửa; nếu cần biên dịch trên Java 8, thay `.toList()` bằng `.collect(Collectors.toList())`.

`StreamSupport` là utility cấp thấp, thường dành cho người viết thư viện hoặc nguồn dữ liệu riêng. Khi nguồn đã là `Collection`, cú pháp thông thường `numbers.stream()` hoặc `numbers.parallelStream()` ngắn gọn và rõ ràng hơn. Trực tiếp thao tác Spliterator có ích khi bạn cần hiểu hoặc kiểm soát cách dữ liệu được đưa vào Stream.

**Lưu ý:** Sau khi Spliterator được đưa vào một Stream và Stream được terminal operation tiêu thụ, không dùng lại chính Spliterator hoặc Stream đó để khởi chạy phép tính mới. Nếu cần tính lại, lấy Spliterator mới từ nguồn còn tồn tại.

## 9. Chuyển `Iterator` thành `Spliterator` và ngược lại

Một nguồn kiểu cũ hoặc API bên thứ ba có thể chỉ cung cấp `Iterator`. Trong Java hiện hành, sử dụng `Spliterators` để tạo adapter:

```java
Spliterator<T> Spliterators.spliteratorUnknownSize(
        Iterator<? extends T> iterator,
        int characteristics);

Iterator<T> Spliterators.iterator(Spliterator<? extends T> spliterator);
```

Đây là mô tả chữ ký, không phải chương trình độc lập. Cờ `characteristics` phải đúng với **nguồn thật**. `spliteratorUnknownSize` bỏ `SIZED` và `SUBSIZED` ngay cả khi bên gọi truyền các cờ đó; không suy diễn kích thước chính xác khi không có bằng chứng.

Lưu `SpliteratorAdapterDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.StringJoiner;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class SpliteratorAdapterDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi", "Anh");

        Iterator<String> sourceIterator = names.iterator();
        Spliterator<String> source =
                Spliterators.spliteratorUnknownSize(
                        sourceIterator, Spliterator.ORDERED);

        String selected = StreamSupport.stream(source, false)
                .filter(s -> s.length() >= 4)
                .collect(Collectors.joining(", "));
        System.out.println("selected = " + selected);

        Iterator<String> backToIterator =
                Spliterators.iterator(List.of("X", "Y").spliterator());
        StringJoiner joined = new StringJoiner(", ");
        while (backToIterator.hasNext()) {
            joined.add(backToIterator.next());
        }
        System.out.println("back = " + joined);
    }
}
```

```bash
javac SpliteratorAdapterDemo.java
java SpliteratorAdapterDemo
```

```text
selected = Binh
back = X, Y
```

Adapter này không biến một iterator vốn **đọc tuần tự** thành nguồn có khả năng tách tùy ý mà không tốn chi phí. `spliteratorUnknownSize` có thể gom từng đợt phần tử để cho phép một mức độ split, nhưng hiệu quả phụ thuộc bản chất nguồn, kích thước và độ tốn kém khi lấy từng phần tử.

Đặc biệt, sau khi trao `sourceIterator` cho `spliteratorUnknownSize(...)`, **không tiếp tục gọi `next()` trên iterator gốc** trong khi Spliterator hoạt động. API adapter quy định hành vi sẽ không xác định nếu vừa dùng iterator gốc vừa dùng Spliterator đã bọc nó. Tương tự, `Spliterators.iterator(spliterator)` chỉ tạo một cách điều khiển khác cho Spliterator, không sao chép dữ liệu nguồn.

Nếu biết trước kích thước chính xác và nguồn có semantics thích hợp, `Spliterators.spliterator(iterator, size, characteristics)` là overload khác. Không tự đặt `SIZED`/`SUBSIZED` cho một nguồn có thể thêm hoặc bớt phần tử tùy ý.

## 10. Primitive specialization: tránh boxing với số nguyên thủy

`Spliterator` có các phiên bản dành riêng cho primitive:

- `Spliterator.OfInt` kết hợp với `IntConsumer`.
- `Spliterator.OfLong` kết hợp với `LongConsumer`.
- `Spliterator.OfDouble` kết hợp với `DoubleConsumer`.

Tương ứng, `PrimitiveIterator.OfInt` có `nextInt()`, `PrimitiveIterator.OfLong` có `nextLong()`, `PrimitiveIterator.OfDouble` có `nextDouble()`. Các API này còn hoạt động trong Java hiện đại.

Lưu `PrimitiveSpliteratorDemo.java`:

```java
import java.util.PrimitiveIterator;
import java.util.Spliterator;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class PrimitiveSpliteratorDemo {
    public static void main(String[] args) {
        Spliterator.OfInt numbers =
                IntStream.rangeClosed(1, 4).spliterator();

        int[] total = {0};
        while (numbers.tryAdvance(
                (int value) -> total[0] += value)) {
            // Hành động cộng nằm trong IntConsumer bên trên.
        }
        System.out.println("manualSum = " + total[0]);

        int streamSum = StreamSupport.intStream(
                IntStream.rangeClosed(1, 4).spliterator(), true)
                .sum();
        System.out.println("streamSum = " + streamSum);

        PrimitiveIterator.OfInt it =
                IntStream.of(7, 8).iterator();
        System.out.println("iterator = " +
                it.nextInt() + ", " + it.nextInt());
    }
}
```

```bash
javac PrimitiveSpliteratorDemo.java
java PrimitiveSpliteratorDemo
```

```text
manualSum = 10
streamSum = 10
iterator = 7, 8
```

Lambda có tham số `int value` chọn overload nhận `IntConsumer`, tránh chuyển `int` thành `Integer` chỉ để gọi action. Tương tự, `StreamSupport.intStream(...)` tạo `IntStream` và có sẵn các reduction như `sum`, `average`, `summaryStatistics`.

`total[0]` trong đoạn duyệt **tuần tự** chỉ để minh họa cách nhận một giá trị primitive qua action; không dùng cùng mảng `total` làm biến tổng cộng có thể thay đổi từ nhiều thread. Trong chương trình thông thường, `IntStream.sum()` an toàn và diễn đạt mục đích rõ hơn. Cũng không cần tự dựng Spliterator khi chỉ muốn tính tổng một mảng số.

## 11. `Iterator.remove()`: khác biệt có ý nghĩa

`Iterator` hỗ trợ `remove()` như một thao tác **tùy chọn**, có thể xóa phần tử vừa được `next()` trả ra nếu nguồn và iterator hỗ trợ. `Spliterator` không có phương thức tương đương: nó thiên về duyệt để xử lý và chia nguồn, không điều khiển chỉnh sửa collection.

Ví dụ được phép xóa khi duyệt bằng Iterator của `ArrayList`. Lưu `IteratorRemoveDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveDemo {
    public static void main(String[] args) {
        List<String> labels =
                new ArrayList<>(List.of("keep", "remove", "keep2"));

        Iterator<String> it = labels.iterator();
        while (it.hasNext()) {
            if ("remove".equals(it.next())) {
                it.remove();
            }
        }
        System.out.println(labels);
    }
}
```

```bash
javac IteratorRemoveDemo.java
java IteratorRemoveDemo
```

```text
[keep, keep2]
```

Ở đây source là một `ArrayList` có thể chỉnh sửa. `List.of(...)` tạo danh sách không sửa được, nhưng đã được **sao chép** vào `ArrayList`. Nếu gọi `remove()` trên iterator của chính `List.of(...)`, thao tác không được hỗ trợ.

Khi muốn lọc/xóa nhiều phần tử theo điều kiện, có thể dùng `labels.removeIf("remove"::equals)` trên collection có hỗ trợ chỉnh sửa, hoặc giữ dữ liệu gốc rồi tạo một danh sách mới bằng `stream().filter(...).toList()` (Java 16+). Không sửa trực tiếp collection nguồn bên trong `forEachRemaining` của Spliterator hay Stream rồi trông chờ `ConcurrentModificationException` luôn phát hiện lỗi.

## 12. Quan hệ với parallel stream và encounter order

`Spliterator` là một yếu tố quan trọng giúp Stream tính toán song song: runtime có thể hỏi `trySplit()` để chia dữ liệu thành nhiều công việc. Mức độ hiệu quả còn phụ thuộc vào nguồn có chia nhanh/cân bằng được không, khối lượng xử lý mỗi phần tử, độ tốn kém khi ghép kết quả và cách quản lý task. Nếu nguồn không thể chia hiệu quả, `parallelStream()` có thể không nhanh hơn.

Một số nguyên tắc:

1. **`ORDERED` không ép `Stream.forEach` chạy đúng thứ tự.** Đối với parallel Stream, `forEach` là terminal operation **không bảo đảm thứ tự action**. Dùng `forEachOrdered` nếu thực sự cần thứ tự encounter.
2. **`trySplit` không biến các action thành concurrent.** Chỉ thuật toán sử dụng Spliterator mới quyết định giao phần nào cho thread nào.
3. **Mỗi Spliterator chỉ được một thread điều khiển tại một thời điểm.** Một thread có thể split rồi giao Spliterator con cho thread khác; không cùng lúc gọi `tryAdvance` trên cùng một đối tượng.
4. **Không giả định một số lần split xác định** hoặc thứ tự hoàn thành task. Kết quả reduction phải tuân thủ tính kết hợp/identity/collector contract.
5. **Nguồn có thể unordered:** Spliterator của một số `Set` hoặc cấu trúc concurrent không có encounter order; `forEachOrdered` không thể tự tạo thứ tự theo khóa khi nguồn không cung cấp thứ tự đó.

Ví dụ chứng minh kết quả có thứ tự với ordered source, lưu `SpliteratorOrderDemo.java`:

```java
import java.util.List;
import java.util.stream.StreamSupport;

public class SpliteratorOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);

        StreamSupport.stream(numbers.spliterator(), true)
                .forEachOrdered(System.out::print);
        System.out.println();

        int sum = StreamSupport.stream(
                numbers.spliterator(), true)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("sum = " + sum);
    }
}
```

```bash
javac SpliteratorOrderDemo.java
java SpliteratorOrderDemo
```

```text
12345
sum = 15
```

`forEachOrdered` giữ encounter order của `List` ngay cả khi pipeline có parallel flag, nhưng có thể làm mất một phần lợi ích song song do phải duy trì thứ tự action. Ví dụ dùng `forEach` thay thế có thể in các chữ số theo thứ tự bất kỳ; do đó không dùng stdout của `parallel().forEach(...)` làm bằng chứng chương trình có thứ tự.

## 13. Thay đổi nguồn, fail-fast và late binding

Điểm rất quan trọng khi tự cầm `Iterator`/`Spliterator`: **không phải mọi nguồn đều chịu được thay đổi cấu trúc khi đang duyệt**.

- Iterator và Spliterator của nhiều collection mutable như `ArrayList` thường có cơ chế **fail-fast** ở mức best effort, có thể ném `ConcurrentModificationException` khi phát hiện chỉnh sửa không hợp lệ. Fail-fast là **công cụ phát hiện lỗi**, không phải cơ chế an toàn dữ liệu hay bằng chứng thread-safe.
- Một số Spliterator là **late-binding**: chỉ gắn với nguồn khi bắt đầu duyệt, bắt đầu split hoặc lần đầu hỏi kích thước ước lượng. Ví dụ `ArrayList.spliterator()` có chính sách late-binding và fail-fast. Đừng dựa vào chi tiết này để cố sửa nguồn tùy tiện sau khi tạo Spliterator.
- Nguồn báo `IMMUTABLE` không bị thay đổi cấu trúc trong lúc duyệt; nguồn báo `CONCURRENT` cho phép sửa nguồn đồng thời theo **chính sách cụ thể** của collection. Hai đặc tính này có nghĩa khác nhau; không tự đánh dấu đồng thời `IMMUTABLE|CONCURRENT` cho một Spliterator nguồn cấp cao.
- Khi Stream đang xử lý, các hàm `filter`/`map`/`forEach` nên **non-interfering** với nguồn không thiết kế cho concurrent modification. Nếu cần chỉnh sửa, thực hiện trước hoặc sau khi duyệt, hay dùng API hỗ trợ hợp đồng sửa đổi đúng.
- Nếu action ném exception trong `tryAdvance`/`forEachRemaining`, không giả định trạng thái còn lại có thể tiếp tục tiêu thụ như cũ.

Một thực hành tốt là tạo **snapshot** dữ liệu nếu nghiệp vụ phải có tập phần tử ổn định trong khi bên khác có thể cập nhật, hoặc dùng cấu trúc concurrent có semantics được thiết kế rõ ràng nếu thực sự cần quan sát cập nhật. Chỉ dùng `synchronized` quanh kết quả in/log không làm một nguồn mutable tùy ý an toàn để nhiều thread sửa khi Spliterator đang duyệt.

## 14. Khi nào cần viết custom Spliterator?

Phần lớn ứng dụng chỉ cần `List.stream()`, `Arrays.stream(...)`, `Files.lines(...)` hoặc các Stream API có sẵn. **Custom Spliterator** là công cụ cấp thấp phù hợp khi bạn xây dựng thư viện/cấu trúc dữ liệu tự viết và muốn:

- Duyệt một cây, vùng mảng, trang dữ liệu hoặc bộ phát dữ liệu theo cách có kiểm soát.
- Chia thành các vùng **không chồng lắp** để parallel có thể xử lý.
- Công bố đúng `ORDERED`/`SIZED`/`SORTED`/các cờ khác cho nguồn.
- Trì hoãn truy cập nguồn hoặc dùng supplier theo thời điểm terminal operation bắt đầu.
- Giảm boxing nhờ `OfInt`/`OfLong`/`OfDouble` nếu phần tử là primitive.

Những ràng buộc quan trọng khi hiện thực:

1. `tryAdvance(action)` phải áp dụng action cho **tối đa một phần tử còn lại** và trả boolean đúng; không trả `true` khi thực tế không tiêu thụ phần tử nào.
2. `forEachRemaining(action)` phải xử lý đúng phần còn lại và tôn trọng `ORDERED` nếu công bố. Trong nhiều trường hợp có thể dựa vào default implementation gọi `tryAdvance` lặp lại.
3. `trySplit()` phải trả một Spliterator quản lý phần **không còn thuộc** Spliterator gốc sau khi split; nếu nguồn ordered thì phần con trả về là prefix.
4. Các cờ đặc tính phải nhất quán với dữ liệu: không gắn `SIZED` khi không biết chính xác kích thước, `DISTINCT` khi có thể trùng giá trị, hoặc `SORTED` nếu chưa bảo đảm thứ tự.
5. Nếu cần size chính xác cho các phần con, chỉ công bố `SUBSIZED` khi mọi phần con thực sự đáp ứng.
6. Mô tả rõ chính sách source binding và phát hiện structural interference nếu nguồn không `IMMUTABLE` hoặc `CONCURRENT`.
7. Sau khi chia, các Spliterator con phải có ownership rõ ràng, không chia sẻ con trỏ mutable khiến cùng phần tử bị phát ra hai lần.
8. Với Stream, ưu tiên reduction/collect đúng contract và tránh side effect làm thay đổi nguồn.

Java còn cung cấp `Spliterators.AbstractSpliterator<T>` và các biến thể primitive abstract để hỗ trợ tạo implementation; chúng có thể cung cấp cơ chế `trySplit` dựa trên gom lô và hữu ích cho nguồn khó chia đều. Tuy nhiên, việc implement `Spliterator` cần thực hiện theo đặc tính thực của nguồn chứ không chỉ “thêm interface là chạy song song nhanh”.

### `StreamSupport.stream(supplier, characteristics, parallel)`

Một overload hữu ích khi nguồn dễ bị ảnh hưởng bởi sửa đổi trước khi traversal:

```java
Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel);
```

Đây là chữ ký API minh họa. Supplier được gọi sau khi terminal operation bắt đầu (không quá một lần), giúp giảm khoảng thời gian nguồn có thể bị can thiệp giữa lúc tạo pipeline và lúc bắt đầu tiêu thụ. `characteristics` truyền vào **phải khớp** với Spliterator mà supplier cấp; nếu không, hành vi không được xác định. Không dùng overload này chỉ để biến stream thành “an toàn trước mọi cập nhật đồng thời”.

## 15. Những lỗi phổ biến khi chọn `Iterator`/`Spliterator`

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `next()` khi `hasNext() == false` | `NoSuchElementException` | Kiểm tra trước hoặc duyệt bằng `forEachRemaining` |
| Quên `tryAdvance` tiêu thụ một phần tử | `forEachRemaining` sau đó bắt đầu **từ phần còn lại** | Theo dõi số phần tử đã đọc |
| Gọi `trySplit` rồi chỉ duyệt Spliterator gốc | Bỏ qua phần tử đã chuyển sang Spliterator con | Xử lý cả phần con và phần gốc |
| Giả định `trySplit` luôn chia đôi | Lập lịch/khẳng định sai khi nguồn không chia được | Chấp nhận `null` và phân chia không cân bằng |
| Gắn `SIZED` hoặc `SORTED` sai | Stream có thể tối ưu dựa trên thông tin sai | Chỉ khai báo cờ đúng hợp đồng |
| Gọi `getComparator()` khi không có `SORTED` | `IllegalStateException` | Kiểm tra đặc tính trước |
| Cho hai thread gọi `tryAdvance` trên cùng Spliterator | Hành vi không xác định | Giao ownership từng Spliterator riêng |
| Gọi `Iterator.remove()` trên nguồn không hỗ trợ | `UnsupportedOperationException` | Dùng collection mutable hỗ trợ hoặc tạo kết quả lọc mới |
| Sửa `ArrayList` nguồn khi đang duyệt | Có thể lỗi hoặc kết quả không hợp lệ | Không can thiệp nguồn khi traversal |
| Dùng lại một Spliterator đã được Stream tiêu thụ | Không còn trạng thái duyệt ban đầu | Tạo Spliterator mới |
| Kỳ vọng `parallel` luôn nhanh | Có thể chậm do overhead, split kém | Đo đạc với workload thực |
| Tin `CONCURRENT` nghĩa chính Spliterator thread-safe | Race do nhiều caller cùng thao tác | Phân biệt nguồn concurrent với điều khiển đối tượng duyệt |

## 16. Bài tập tự kiểm tra

**Bài 1 — API tương ứng.** Từ một `List<String>`, hãy duyệt bằng `Iterator` và `Spliterator` rồi giải thích phần tử nào còn lại sau mỗi lần gọi `next`/`tryAdvance`.

**Bài 2 — Chia dữ liệu.** Cho `List<Integer>` có sáu phần tử, lấy Spliterator, gọi `trySplit` đúng một lần. Làm thế nào bảo đảm không bỏ sót phần tử dù `trySplit` trả `null` hoặc trả phần có kích thước bất kỳ?

**Bài 3 — Chuyển thành Stream.** Từ một Iterator có encounter order, tạo Spliterator và thu về danh sách chuỗi dài ít nhất 6 ký tự; không được dùng lại Iterator gốc sau khi bọc.

**Bài 4 — Tư duy concurrency.** Nếu nguồn Spliterator có `CONCURRENT`, liệu có được cho nhiều thread đồng thời gọi `tryAdvance` trên cùng Spliterator không? Giải thích từ hợp đồng ownership.

Lời giải tham khảo cho bài 2–3, lưu `SpliteratorPractice.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class SpliteratorPractice {
    public static void main(String[] args) {
        List<String> names =
                List.of("Java", "Stream", "API", "Spliterator");

        Spliterator<String> rest = names.spliterator();
        Spliterator<String> first = rest.trySplit();

        List<String> recovered = new ArrayList<>();
        if (first != null) {
            first.forEachRemaining(recovered::add);
        }
        rest.forEachRemaining(recovered::add);
        System.out.println("recovered = " + recovered);
        System.out.println("equal = " + recovered.equals(names));

        Iterator<String> it = names.iterator();
        Spliterator<String> source =
                Spliterators.spliteratorUnknownSize(
                        it, Spliterator.ORDERED);
        List<String> longNames = StreamSupport.stream(source, false)
                .filter(name -> name.length() >= 6)
                .collect(Collectors.toList());
        System.out.println("longNames = " + longNames);
    }
}
```

```bash
javac SpliteratorPractice.java
java SpliteratorPractice
```

```text
recovered = [Java, Stream, API, Spliterator]
equal = true
longNames = [Stream, Spliterator]
```

Bài 1: `Iterator.next()` lấy phần tử tiếp theo, còn `Spliterator.tryAdvance(action)` trao phần tử tiếp theo cho action. Dù cách nhận khác nhau, cả hai đều cập nhật vị trí duyệt và không tự quay lại đầu. Bài 4: **không được**; `CONCURRENT` mô tả nguồn dữ liệu có thể sửa đổi đồng thời, còn một đối tượng Spliterator không phải giao diện để nhiều thread cùng điều khiển một cursor.

## 17. Checklist khi áp dụng

- Tôi chỉ cần duyệt từng phần tử? `Iterator` hoặc vòng lặp `for-each` có đơn giản hơn không?
- Tôi cần đưa nguồn tự viết vào Stream hoặc hỗ trợ chia việc? `Spliterator`/`StreamSupport` có phù hợp không?
- Nếu gọi `trySplit`, đã xử lý cả đối tượng con và phần còn lại của đối tượng gốc?
- Có thật sự giữ encounter order hay tôi đang giả định thứ tự từ một nguồn unordered?
- Các cờ `ORDERED`/`SIZED`/`SUBSIZED`/`CONCURRENT` tôi dùng có đúng contract?
- Có vô tình thao tác đồng thời trên **cùng một Spliterator** hoặc tiếp tục dùng Iterator gốc đã được adapter bọc?
- Nguồn mutable có chính sách sửa đổi khi duyệt rõ ràng? Tôi có tránh side effect can thiệp nguồn?
- Nếu phần tử primitive, có nên dùng `Spliterator.OfInt`/`OfLong`/`OfDouble`?
- Việc viết custom Spliterator có thực sự cần thiết so với API Stream/Collection có sẵn?

## 18. Tài liệu Java hiện hành

- Oracle Java SE 26 — `Spliterator<T>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html
- Oracle Java SE 26 — `Iterator<E>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Iterator.html
- Oracle Java SE 26 — `Spliterators`, adapter giữa Iterator/Spliterator: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterators.html
- Oracle Java SE 26 — `StreamSupport`, tạo Stream từ Spliterator: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/StreamSupport.html
- Oracle Java SE 26 — `java.util.stream`, ordering/non-interference/parallelism: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html

**Kết luận:** `Iterator` có giao thức hỏi–lấy cho một đường duyệt; `Spliterator` bổ sung giao thức nhận action, chia phần dữ liệu chưa duyệt và báo đặc tính nguồn. Hiểu `trySplit`, encounter order và ownership sẽ giúp dùng Stream song song đúng đắn mà không phải tự quản lý mọi thread.