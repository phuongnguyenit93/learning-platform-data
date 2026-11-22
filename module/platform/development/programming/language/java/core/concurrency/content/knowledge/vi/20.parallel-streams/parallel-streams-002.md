# Spliterator và khả năng chia nguồn dữ liệu trong Parallel Streams

`Spliterator<T>` (thuộc `java.util`) là giao diện hỗ trợ **duyệt** và **chia** nguồn phần tử. `Iterator` chủ yếu duyệt tuần tự; `Spliterator` có thêm `trySplit()` để giao những phần chưa duyệt cho các tác vụ khác. Đây là một cơ chế quan trọng giúp Java Stream API thực thi pipeline song song.

**Ý chính:** `parallelStream()` hoặc `stream().parallel()` mới chỉ yêu cầu xử lý song song; nguồn phải chia được thành những phần độc lập với chi phí hợp lý thì việc song song mới có cơ hội mang lại lợi ích. Spliterator là mô tả về nguồn dữ liệu và cách chia việc; tự nó không tạo hay quản lý thread.

Bài nằm trong **Parallel Streams** của Java concurrency, chỉ dùng API Java nói chung và không đưa các cơ chế của framework vào.

## 1. Spliterator nằm ở đâu trong parallel stream?

```text
Nguồn: mảng / ArrayList / Set / range / nguồn tùy chỉnh
                         |
                    Spliterator
                         |
                    trySplit()
                   /          \
              phần A          phần B
               /                 \
          trySplit()          trySplit()
           /    \              /    \
         A1     A2            B1     B2
           \    /              \    /
             kết quả xử lý / reduction
                         |
                   kết quả cuối
```

Khi có terminal operation, triển khai stream mới thực sự duyệt nguồn. Trong parallel pipeline, JDK có thể phân rã công việc thành các tác vụ Fork/Join và xử lý các phần đã chia trên những worker phù hợp. Việc sử dụng `ForkJoinPool.commonPool()` là hành vi phổ biến của triển khai JDK, không phải cam kết mỗi chunk sẽ có một thread riêng. Cây phân chia trong sơ đồ chỉ minh họa; số lần split, kích thước chunk và thời điểm thực thi tùy vào nguồn, pipeline và hệ thống.

Một stream vẫn có thể chạy đúng dù Spliterator không chia được, nhưng khi ấy lợi ích xử lý nhiều phần tử song song có thể rất nhỏ hoặc không có.

## 2. Các phương thức cốt lõi

| Phương thức | Công dụng và hợp đồng |
|---|---|
| `boolean tryAdvance(Consumer<? super T> action)` | Nếu còn phần tử, chuyển một phần tử vào `action` và trả `true`; nếu hết, trả `false` |
| `void forEachRemaining(Consumer<? super T> action)` | Tiêu thụ toàn bộ phần tử còn lại; có thể tối ưu tốt hơn lặp từng phần tử |
| `Spliterator<T> trySplit()` | Trả về Spliterator mới sở hữu một phần phần tử **chưa duyệt**, giữ phần còn lại ở đối tượng gốc; có thể trả `null` |
| `long estimateSize()` | Ước lượng số phần tử còn lại; có thể trả `Long.MAX_VALUE` nếu kích thước không biết |
| `int characteristics()` | Bitmask mô tả đặc tính của nguồn và thứ tự duyệt |
| `long getExactSizeIfKnown()` | Kích thước chính xác khi có đặc tính `SIZED`; nếu không có, trả `-1` |
| `boolean hasCharacteristics(int flags)` | Kiểm tra các đặc tính có trong bitmask |
| `Comparator<? super T> getComparator()` | Với nguồn mang `SORTED` trả comparator (`null` nếu theo thứ tự tự nhiên); nếu không sorted, thường ném `IllegalStateException` |

Các thao tác `tryAdvance()`, `forEachRemaining()` và `trySplit()` đều thay đổi tập phần tử **còn do Spliterator quản lý**. Không dùng cùng một Spliterator để chạy độc lập nhiều lần rồi chờ kết quả giống nhau. Khi cần duyệt lại từ đầu, hãy lấy Spliterator mới từ nguồn.

Java còn có `Spliterator.OfInt`, `OfLong`, `OfDouble` với consumer primitive để tránh boxing không cần thiết trong phép tính số.

## 3. trySplit() phân vùng như thế nào?

Giả sử một nguồn có encounter order:

```text
trước khi split: [1, 2, 3, 4, 5, 6, 7, 8]
                       |
                    trySplit()
                /                \
trả về prefix: [1, 2, 3, 4]   gốc còn: [5, 6, 7, 8]
```

Với Spliterator có `ORDERED`, đối tượng được trả về bởi `trySplit()` phải chứa **prefix** của tập phần tử chưa duyệt; đối tượng gốc giữ suffix còn lại. Các tập sau chia phải không trùng, không bỏ sót, và hợp lại phải đúng tập phần tử chưa duyệt ban đầu.

**Không có quy tắc API rằng phải chia chính giữa.** Một nguồn có thể tách một block, một node, một batch kích thước tăng dần hoặc trả `null` nếu không thể/không đáng chia. Với nguồn không có `ORDERED`, không có khái niệm tiền tố theo một encounter order phải giữ.

### Ví dụ chạy được: chia một ArrayList

Lưu thành `ListSplitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class ListSplitDemo {
    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(List.of(1, 2, 3, 4, 5, 6, 7, 8));

        Spliterator<Integer> remainder = values.spliterator();
        Spliterator<Integer> prefix = remainder.trySplit();

        if (prefix == null) {
            throw new IllegalStateException("Unexpected unsplittable list");
        }

        System.out.println("Prefix size: " + prefix.getExactSizeIfKnown());
        System.out.println("Remainder size: "
                + remainder.getExactSizeIfKnown());

        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining(left::add);
        remainder.forEachRemaining(right::add);

        System.out.println("Prefix: " + left);
        System.out.println("Remainder: " + right);
        System.out.println("Total: " + (left.size() + right.size()));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac ListSplitDemo.java
java ListSplitDemo
```

Kết quả:

```text
Prefix size: 4
Remainder size: 4
Prefix: [1, 2, 3, 4]
Remainder: [5, 6, 7, 8]
Total: 8
```

Spliterator của `ArrayList` có thể chia theo chỉ số nên chia gần đều, duy trì encounter order. `getExactSizeIfKnown()` cho kích thước chính xác của hai phần nhờ đặc tính `SIZED`. Trong ví dụ này, việc duyệt sau khi split được thực hiện **tuần tự** để minh họa; `trySplit()` không đồng nghĩa tạo thread hay thực thi code trên thread khác.

## 4. estimateSize(), SIZED và SUBSIZED

Để phân chia công việc hiệu quả, thuật toán cần ước lượng xem còn bao nhiêu phần tử. Những cờ kích thước cần hiểu chính xác:

- `SIZED`: kích thước báo bởi `estimateSize()` là chính xác theo hợp đồng nguồn (trong điều kiện không bị can thiệp trái phép). `getExactSizeIfKnown()` có thể trả con số này.
- `SUBSIZED`: Spliterator hiện tại **và tất cả Spliterator phát sinh từ việc split** đều đáp ứng cả `SIZED` lẫn `SUBSIZED`.
- Không có `SIZED`: `estimateSize()` chỉ là ước lượng; `getExactSizeIfKnown()` trả `-1`.
- Có `SIZED` nhưng không có `SUBSIZED`: không thể tự suy mọi nhánh phát sinh đều có kích thước chính xác.

Một nguồn 16 phần tử có thể được chia theo cây cân bằng:

```text
16
├── 8
│   ├── 4
│   └── 4
└── 8
    ├── 4
    └── 4
```

Nhưng chia **cân bằng số phần tử** không bảo đảm cân bằng **thời gian xử lý**: một chunk có thể chứa thao tác tốn 100 ms, chunk khác chỉ 1 ms. Khi đó sẽ có nhánh chậm gây nghẽn (*straggler*), dù số phần tử bằng nhau.

Cũng không có “ngưỡng chunk tối ưu” áp dụng chung cho mọi nguồn. Nếu mỗi phần tử rất rẻ, overhead phân rã/lập lịch/gộp có thể lớn hơn thời gian tính toán. Nếu phép toán nặng và các nhánh cân bằng, song song có thể mang lại lợi ích đáng kể.

## 5. Tám characteristics và ảnh hưởng tới Stream

`characteristics()` ghép các cờ bằng bitwise OR (`|`). Chúng là **cam kết về hành vi**, để các thao tác Stream có thể lựa chọn tối ưu an toàn:

| Cờ | Nghĩa | Điểm dễ hiểu sai |
|---|---|---|
| `ORDERED` | Nguồn có encounter order; split phải giữ đúng prefix | Không có nghĩa tác vụ song song chạy theo thời gian tăng dần |
| `DISTINCT` | Các phần tử phân biệt theo `equals()` | Hữu ích cho tối ưu `distinct()`; không khai báo nếu có trùng |
| `SORTED` | Duyệt theo một thứ tự sắp xếp | Phải thực hiện đúng hợp đồng `getComparator()` |
| `SIZED` | Kích thước chính xác | Không được ước lượng sai mà vẫn khai báo |
| `NONNULL` | Không có phần tử `null` | Không phù hợp nguồn có thể chứa null |
| `IMMUTABLE` | Nguồn không thể bị can thiệp cấu trúc trong khi duyệt | Không cam kết tất cả object phần tử bất biến |
| `CONCURRENT` | Nguồn hỗ trợ thay đổi cấu trúc đồng thời theo hợp đồng của nguồn | **Không** có nghĩa nhiều thread được gọi thao tác trên cùng một Spliterator |
| `SUBSIZED` | Kích thước của mọi nhánh split vẫn chính xác | Mạnh hơn chỉ `SIZED` ở gốc |

Ví dụ điển hình:

- `ArrayList` có encounter order và kích thước biết trước, có Spliterator thuận tiện cho chia theo đoạn chỉ số; thông thường mang `ORDERED`, `SIZED`, `SUBSIZED`.
- `HashSet` có tính duy nhất nhưng không bảo đảm encounter order giống `List`. Cách chia phụ thuộc cấu trúc tập và có thể không đều.
- Các collection đồng thời như `ConcurrentHashMap.keySet()` có chính sách duyệt và can thiệp cấu trúc khác `ArrayList`; `CONCURRENT` mô tả nguồn, không cấp quyền dùng chung một Spliterator object một cách vô hạn.

Khi tự viết Spliterator, việc khai báo sai có thể khiến Stream chọn cách tối ưu dựa trên dữ kiện giả, dẫn tới thiếu phần tử, sai thứ tự hoặc kết quả không đúng. Nếu không thể bảo đảm đặc tính, đừng công bố cờ đó.

## 6. Tự cài đặt Spliterator.OfInt chia khoảng số nguyên

Nguồn dạng khoảng liên tiếp phù hợp cho parallel: không cần giữ danh sách lớn, mỗi nhánh có hai biên, kích thước chính xác và có thể chia nhanh theo midpoint.

Bất biến khi chưa duyệt:

```text
Gốc quản lý: [index, fence)
trySplit():
    trả về [index, mid)  // prefix
    gốc giữ [mid, fence) // suffix
```

Lưu đoạn chương trình sau vào `RangeSplitDemo.java`:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class RangeSplitDemo {
    static final class IntRange implements Spliterator.OfInt {
        private int index;
        private final int fence;

        IntRange(int fromInclusive, int toExclusive) {
            if (fromInclusive > toExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            index = fromInclusive;
            fence = toExclusive;
        }

        @Override
        public OfInt trySplit() {
            int size = fence - index;
            if (size <= 1) {
                return null;
            }

            int middle = index + size / 2;
            IntRange prefix = new IntRange(index, middle);
            index = middle;
            return prefix;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (index >= fence) {
                return false;
            }
            action.accept(index++);
            return true;
        }

        @Override
        public long estimateSize() {
            return (long) fence - index;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE;
        }
    }

    public static void main(String[] args) {
        Spliterator.OfInt remaining = new IntRange(1, 9);
        Spliterator.OfInt first = remaining.trySplit();

        System.out.println("First: "
                + StreamSupport.intStream(first, false).boxed().toList());
        System.out.println("Remaining: "
                + StreamSupport.intStream(remaining, false).boxed().toList());

        long sumSquares = StreamSupport
                .intStream(new IntRange(1, 1001), true)
                .mapToLong(x -> (long) x * x)
                .sum();

        System.out.println("Sum of squares: " + sumSquares);
    }
}
```

Chạy trên Java 17+:

```bash
javac RangeSplitDemo.java
java RangeSplitDemo
```

Kết quả xác định:

```text
First: [1, 2, 3, 4]
Remaining: [5, 6, 7, 8]
Sum of squares: 333833500
```

**Giải thích thiết kế:**

1. Mỗi Spliterator quản lý đoạn nửa mở riêng, không chồng lấn. `trySplit()` tạo đối tượng mới chứa nửa đầu và cập nhật `index` của gốc; không bị bỏ sót phần tử.
2. `tryAdvance()` tiêu thụ đúng một giá trị nếu còn; khi hết trả `false`. `Objects.requireNonNull` từ chối consumer null.
3. `estimateSize()` luôn tính từ biên, nên `SIZED` và `SUBSIZED` là chính xác cho các khoảng hợp lệ. `ORDERED` phù hợp vì split trả prefix; `IMMUTABLE` phù hợp nguồn số nguyên tổng hợp bất biến cấu trúc.
4. `StreamSupport.intStream(..., true)` tạo parallel `IntStream` từ Spliterator. Tổng bình phương dùng `long` để tránh tràn `int` và có reduction thích hợp cho tính toán song song.
5. Chính lịch phân công task có thể khác nhau giữa các lần chạy, nhưng kết quả tổng không thay đổi vì các nhánh không trùng, không thiếu phần tử.

**Giới hạn ví dụ:** biến `size` ở `trySplit()` là `int` nên có thể overflow nếu biên cách nhau lớn hơn `Integer.MAX_VALUE`. Ví dụ chỉ dùng khoảng nhỏ; một thư viện tổng quát phải tính hiệu bằng `long` và midpoint an toàn. Đối tượng Spliterator này không thread-safe cho việc cùng lúc gọi phương thức từ nhiều thread; mẫu dùng đúng là **chia rồi giao từng đối tượng nhánh cho một task**.

Với mảng, `ArrayList` hoặc `IntStream.range`/`rangeClosed`, JDK đã có Spliterator phù hợp. Tự viết chỉ đáng cân nhắc khi sở hữu cấu trúc nguồn đặc biệt, như block hoặc cây phân vùng, và phép đo xác nhận cần cách chia riêng.

## 7. Nguồn từ Iterator: có thể chia nhưng không phải lúc nào cũng tốt

Khi chỉ có một `Iterator` tiến tuần tự, có thể chuyển sang Spliterator:

```java
Spliterator<String> spliterator =
        java.util.Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);

java.util.stream.Stream<String> stream =
        java.util.stream.StreamSupport.stream(spliterator, true);
```

Đây là mã minh họa **đặt trong method đã có** biến `iterator` kiểu `Iterator<String>` và import `java.util.Spliterator`. Adapter `spliteratorUnknownSize` không biết chính xác kích thước từ đầu, nhưng triển khai JDK **có thể gom batch** để chia. Vì thế không nên kết luận rằng Spliterator từ Iterator “không bao giờ split được”; hạn chế là việc lấy dữ liệu tuần tự để tạo batch có thể trở thành nút cổ chai.

Ngoài overload `StreamSupport.stream(spliterator, parallel)`, Java có overload nhận `Supplier<? extends Spliterator<T>>`, `characteristics` và cờ `parallel` để trì hoãn việc lấy nguồn cho tới khi terminal operation chạy. Điều này có ích khi tránh gắn vào nguồn mutable quá sớm, nhưng **characteristics đưa cho StreamSupport phải đúng với Spliterator được supplier cấp**.

## 8. Hệ quả với thứ tự, hiệu năng và concurrency

### Encounter order khác thứ tự thực thi

Một nguồn `ORDERED` vẫn có thể xử lý các phần tử trên nhiều worker với thứ tự chạy không cố định. Ví dụ:

```java
java.util.List.of(1, 2, 3, 4)
        .parallelStream()
        .forEach(System.out::print);
```

Có thể in thứ tự khác `1234`. Thay `forEach` bằng `forEachOrdered` sẽ giữ encounter order khi in (đối với nguồn danh sách này là `1234`), nhưng có thể tăng chi phí đồng bộ và làm bớt cơ hội song song ở bước terminal. Tránh dựa vào thứ tự của các side effect trong `forEach`.

### Vì sao split tốt vẫn có thể chậm?

Chia được là điều kiện quan trọng, nhưng hiệu suất còn phụ thuộc:

- **Độ hạt:** task quá nhỏ gây overhead lập lịch, chia và gộp. Một phép cộng rẻ trên danh sách ngắn thường không đáng chạy parallel.
- **Phân bố chi phí:** hai nhánh có cùng số lượng nhưng một nhánh xử lý khó gấp nhiều lần sẽ dẫn đến straggler.
- **Kiểu phép toán:** pipeline chỉ có phép biến đổi stateless, độc lập thường dễ song song hơn `sorted`, `distinct` hoặc các phép phụ thuộc thứ tự.
- **Độ lớn và cấu trúc nguồn:** phân chia mảng/range theo chỉ số thường rẻ, còn linked structures, Iterator tuần tự hoặc nguồn không biết kích thước có thể phải trả nhiều chi phí để tìm điểm chia.
- **Chi phí giảm/gộp:** reduction dùng trạng thái mutable chia sẻ hoặc lock chung có thể triệt tiêu parallel speedup.
- **Tài nguyên thực:** số lõi, cache, allocation, GC, common pool đang bận, thao tác blocking I/O hoặc giới hạn hệ thống ngoài đều ảnh hưởng.

Tưởng tượng thời gian xử lý như tổng chi phí chia + phần việc của nhánh chậm nhất + chi phí kết hợp + scheduling/đồng bộ. Đây là mô hình định tính, không phải công thức thời gian chính xác.

### Không dùng side effect chia sẻ tùy tiện

Sai lầm phổ biến:

```java
List<Integer> output = new ArrayList<>();
input.parallelStream().forEach(output::add);
```

Đoạn trên chỉ là **ví dụ phản diện trong một method**, với `input` là `Collection<Integer>`. `ArrayList` không thread-safe, nên các thao tác `add` cạnh tranh có thể làm sai dữ liệu. Hãy dùng collector phù hợp hoặc reduction không chia sẻ trạng thái:

```java
List<Integer> output = input.parallelStream().toList();
```

Đoạn này tạo kết quả sau terminal operation, để cơ chế Stream xử lý việc thu gom; nếu cần mutable list, chọn collector có ngữ nghĩa phù hợp. Không xem `SIZED` hay `CONCURRENT` của Spliterator là lý do để bỏ qua thread-safety của accumulator.

### Can thiệp nguồn trong lúc stream đang chạy

`ArrayList` và nhiều collection mutable có Spliterator late-binding và kiểm tra fail-fast ở mức **best effort**. Thay đổi cấu trúc nguồn sau khi traversal đã gắn vào nguồn có thể gây `ConcurrentModificationException` hoặc hành vi khó đoán; fail-fast không phải công cụ đồng bộ thread.

Nguồn như `ConcurrentHashMap` công bố chính sách duyệt phù hợp khi có thay đổi đồng thời; đọc được ở đây không đồng nghĩa có snapshot cố định của mọi key tại một thời điểm. Với nguồn không hỗ trợ can thiệp đồng thời, hãy giữ dữ liệu ổn định trong lúc duyệt, hoặc tạo snapshot thích hợp trước khi tạo stream.

**Quan trọng:** Spliterator nhìn chung không được bảo đảm thread-safe; thuật toán song song nên giao mỗi đối tượng Spliterator cho một thread tại một thời điểm sau khi chia. `CONCURRENT` nói về **nguồn dữ liệu**, không phải khả năng hai worker cùng gọi `tryAdvance()` trên đúng một đối tượng Spliterator.

## 9. Cách kiểm tra khả năng chia của một nguồn cụ thể

Trước khi tối ưu, đọc các dữ kiện sau trên **một Spliterator mới**:

1. `characteristics()` và `hasCharacteristics(...)`: có `ORDERED`, `SIZED`, `SUBSIZED` không?
2. `estimateSize()`, `getExactSizeIfKnown()`: nguồn biết kích thước hay chỉ có ước lượng?
3. `trySplit()`: có trả về nhánh con không; phần con và phần gốc có kích thước/cấu trúc thế nào?
4. Có thể split lặp lại hiệu quả hay chỉ một lần tách rất lệch?
5. Pipeline thật sự có đủ việc CPU-bound độc lập để bù chi phí chia và gộp không?

Ví dụ kiểm tra chỉ đọc metadata (mã minh họa trong method có `numbers` là `Collection<Integer>`):

```java
Spliterator<Integer> s = numbers.spliterator();

System.out.println("Estimate: " + s.estimateSize());
System.out.println("SIZED: " + s.hasCharacteristics(Spliterator.SIZED));
System.out.println("SUBSIZED: "
        + s.hasCharacteristics(Spliterator.SUBSIZED));
System.out.println("ORDERED: "
        + s.hasCharacteristics(Spliterator.ORDERED));
```

Nếu muốn thực sự split để kiểm tra, dùng một Spliterator riêng cho phép thử. `trySplit()` thay đổi quyền sở hữu phần tử; không split đối tượng đã chuẩn bị đưa vào pipeline thật rồi tưởng nó còn đại diện nguyên vẹn cho nguồn.

Để đánh giá tốc độ, so sánh sequential/parallel trên **cùng loại dữ liệu, cùng tải, nhiều kích thước và sau warm-up**. Ưu tiên JMH khi cần benchmark đáng tin; một lần đo `System.nanoTime()` dễ bị JIT, GC và tải hệ thống làm sai lệch.

## 10. Các lỗi phổ biến

1. **Tưởng `parallel()` luôn nhanh hơn.** Nguồn khó split hoặc mỗi phần tử quá rẻ có thể khiến chạy chậm hơn.
2. **Tưởng `trySplit()` luôn chia đúng 50/50.** API cho phép trả `null` và tách theo batch hoặc cách khác.
3. **Tưởng `trySplit()` tự tạo OS thread.** Nó chỉ chia nguồn; runtime lập lịch task.
4. **Cho hai thread đồng thời sử dụng một đối tượng Spliterator.** Phải chia thành các đối tượng con rồi bàn giao ownership.
5. **Đặt cờ `SIZED` hoặc `SUBSIZED` sai.** Những tối ưu dựa trên metadata có thể cho kết quả sai.
6. **Đánh đồng `ORDERED` với thứ tự chạy của `forEach`.** Encounter order không ép scheduler thực thi tuần tự.
7. **Lạm dụng `CONCURRENT` để biện minh accumulator dùng chung không thread-safe.** Cờ này chỉ nói về cấu trúc nguồn.
8. **Thay đổi cấu trúc của nguồn mutable khi đang duyệt.** Có thể gây interference và kết quả không xác định.
9. **Đo kích thước bằng cách tự duyệt tất cả phần tử rồi tiếp tục dùng cùng Spliterator.** Duyệt đã tiêu thụ dữ liệu; hãy dùng metadata khi phù hợp.
10. **Coi bottleneck I/O là lý do cứ bật parallel stream.** Blocking tác vụ Fork/Join có thể gây chậm các việc khác và không tăng được connection/throughput ngoại vi.

## 11. Chọn Spliterator phù hợp

Một Spliterator có khả năng chia tốt thường có bốn yếu tố: **phân chia đầy đủ không chồng lắp**, **chi phí split thấp**, **kích thước/characteristics chính xác** và **phân bố việc đủ cân bằng**. Nhưng ngay cả khi đủ bốn yếu tố, cần đo workload thật để quyết định dùng parallel stream.

Bắt đầu bằng những Spliterator chuẩn của `ArrayList`, mảng hoặc `IntStream.range`; tự cài đặt chỉ khi cấu trúc nguồn mới hoặc tổ chức dữ liệu theo block đòi hỏi logic chia riêng. Bản chất của `trySplit()` là trao một phần nguồn chưa duyệt cho tác vụ khác; hiệu quả song song xuất hiện khi các phần độc lập đủ lớn để xử lý và gộp với chi phí thấp.

Tham khảo API chính thức:

- [Oracle Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 21 — StreamSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/StreamSupport.html)
- [Oracle Java SE 21 — java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
