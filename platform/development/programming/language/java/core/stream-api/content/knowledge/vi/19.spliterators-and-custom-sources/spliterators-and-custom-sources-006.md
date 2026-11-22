# Late binding, nguồn có thể thay đổi và giới hạn fail-fast

Trong **Java Stream API**, một pipeline thường được mô tả bằng các phép toán trung gian *lazy* như `filter` hoặc `map` và chỉ thực sự duyệt dữ liệu khi gặp terminal operation như `collect`, `forEach` hoặc `reduce`. Phía dưới nhiều nguồn stream là **`Spliterator<T>`**: đối tượng cung cấp phần tử bằng `tryAdvance` và, khi có thể, chia công việc qua `trySplit`.

Khi nguồn là một collection **có thể thay đổi**, xuất hiện ba câu hỏi dễ nhầm lẫn:

1. Spliterator **gắn với trạng thái nguồn** (*bind*) vào lúc nào?
2. Nếu nguồn thay đổi sau khi tạo stream, những phần tử mới có được nhìn thấy không?
3. Nếu nguồn bị thay đổi trong lúc duyệt, **fail-fast** có bảo đảm ném `ConcurrentModificationException` không?

Câu trả lời phụ thuộc vào hợp đồng nguồn và Spliterator, không chỉ vào việc pipeline là lazy. Bài này thuộc chương **Spliterator và nguồn tự định nghĩa**, tập trung vào *late binding*, nguyên tắc **non-interference**, các đặc tính `IMMUTABLE`/`CONCURRENT`, và giới hạn thật sự của cơ chế fail-fast.

## 1. Phân biệt tạo stream, binding và traversal

Ba thời điểm không đồng nghĩa:

| Thời điểm | Điều xảy ra | Điều **chưa thể** suy ra |
| --- | --- | --- |
| **Tạo stream** | Có đối tượng mô tả pipeline hoặc nguồn dữ liệu. | Chưa chắc các phần tử đã được đọc hoặc nguồn đã bị cố định. |
| **Binding** | Spliterator thiết lập trạng thái duyệt gắn với nguồn, ví dụ kích thước/kỳ vọng thay đổi của collection. | Chưa chắc toàn bộ phần tử đã được xử lý. |
| **Traversal** | `tryAdvance`, `forEachRemaining` hoặc terminal operation thực sự tiêu thụ phần tử. | Không đồng nghĩa nguồn được bảo vệ khỏi thay đổi đồng thời. |

Một **late-binding Spliterator** trì hoãn việc gắn với nguồn cho đến lúc duyệt lần đầu, chia lần đầu hoặc lần đầu truy vấn kích thước ước lượng, tùy hợp đồng và cách triển khai. Đặc tính này thường thu hẹp khoảng thời gian mà các sửa đổi nguồn có thể gây xung đột.

```text
Tạo source  --->  tạo Stream/Spliterator  --->  binding  --->  traversal
                    |                         |
                    | nguồn còn có thể đổi    | sửa nguồn sau đây
                    | trước khi bind          | có thể gây interference
                    v                         v
             chưa phải snapshot         fail-fast chỉ best-effort
```

**Late binding không phải snapshot**, và cũng **không phải** cơ chế đồng bộ đa luồng. Tính lazy của pipeline chỉ nói rằng nhiều thao tác được trì hoãn tới khi cần kết quả; nó không tự quy định chính xác thời điểm mỗi nguồn chốt trạng thái.

## 2. Ví dụ với `ArrayList`: sửa trước khi terminal operation

Spliterator của `ArrayList` trong JDK có tính **late-binding** và **fail-fast**. Với trường hợp tạo stream rồi thêm phần tử **trước khi bắt đầu terminal operation**, thay đổi này có thể được đưa vào lượt duyệt sau đó:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BeforeTraversal {
    public static void main(String[] args) {
        List<String> names =
            new ArrayList<>(Arrays.asList("An", "Binh"));

        Stream<String> pipeline = names.stream()
            .filter(name -> !name.isEmpty());

        names.add("Chi"); // Chưa bắt đầu terminal operation.

        List<String> result =
            pipeline.collect(Collectors.toList());

        System.out.println(result); // [An, Binh, Chi]
    }
}
```

Trong ví dụ này, `ArrayList` vẫn có thể thay đổi trong giai đoạn **trước khi Spliterator bind**. Khi terminal operation bắt đầu, nó nhìn thấy danh sách lúc ấy. Tuy nhiên, không suy rộng thành quy tắc “mọi stream luôn nhìn thấy mọi sửa đổi trước `collect`”: những nguồn **early-binding**, snapshot hoặc nguồn đặc biệt có hợp đồng khác.

Một nguồn có thể chốt trạng thái **sớm hơn terminal operation** nếu ai đó đã sử dụng Spliterator để truy vấn hoặc chia công việc. Cần đọc hợp đồng của nguồn cụ thể thay vì xem mọi collection như `ArrayList`.

## 3. Truy vấn `estimateSize` hoặc `trySplit` có thể kích hoạt binding

Với late-binding Spliterator, *first traversal* không phải thời điểm duy nhất có thể bind: truy vấn kích thước ước lượng hoặc thao tác chia cũng có thể khởi tạo trạng thái nội bộ.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Spliterator;

ArrayList<Integer> values =
    new ArrayList<>(Arrays.asList(10, 20, 30));

Spliterator<Integer> spliterator = values.spliterator();

long sizeBefore = spliterator.estimateSize(); // Có thể bind tại đây.
values.add(40); // Sửa cấu trúc sau khi Spliterator đã bind.

try {
    spliterator.forEachRemaining(System.out::println);
} catch (java.util.ConcurrentModificationException ex) {
    System.out.println("Phát hiện thay đổi nguồn");
}
```

Trong các phiên bản `ArrayList` thông dụng, `estimateSize()` khiến Spliterator ghi nhận trạng thái nguồn. Việc thêm phần tử sau đó có thể dẫn đến `ConcurrentModificationException` khi duyệt. **Đoạn mã này chỉ để minh họa rủi ro, không phải bài kiểm thử được phép yêu cầu ngoại lệ luôn xuất hiện.**

Tương tự, `trySplit()` có thể bind nguồn để biết ranh giới chia. Sau khi bắt đầu chia, các nhánh cần giữ được hợp đồng về phần tử đã phân công; thay đổi nguồn lúc đó càng khó dự đoán.

Lưu ý: gọi `estimateSize()` không nhất thiết tạo **snapshot của tất cả phần tử**. Nó chỉ cung cấp một số ước lượng theo trạng thái và đặc tính Spliterator. Với nguồn có thể thay đổi, kích thước và giá trị thực tế có thể khác nếu có can thiệp ngoài hợp đồng.

## 4. Fail-fast là phát hiện lỗi *best-effort*, không phải khóa bảo vệ

Một số iterator và Spliterator của collection như `ArrayList` cố gắng phát hiện **sửa đổi cấu trúc ngoài luồng duyệt** và ném `ConcurrentModificationException`. Ví dụ sửa đổi cấu trúc gồm thêm hoặc xóa phần tử, làm thay đổi số phần tử của `ArrayList`.

Nhưng fail-fast có giới hạn:

- Nó **không bảo đảm** phát hiện tất cả thay đổi khi nhiều thread truy cập không đồng bộ.
- Việc phát hiện có thể đến sau khi một số phần tử đã được xử lý; đừng dựa vào số phần tử được duyệt trước ngoại lệ.
- Không thấy `ConcurrentModificationException` **không chứng minh** truy cập đã an toàn.
- Một số thay đổi như `List.set(index, value)` **không thay đổi cấu trúc** và có thể không được cơ chế đếm sửa đổi phát hiện, dù kết quả duyệt vẫn bị ảnh hưởng.
- Nguồn có đặc tính `CONCURRENT` hoặc `IMMUTABLE` có hợp đồng duyệt khác: không mặc định dùng fail-fast.

`ConcurrentModificationException` không có nghĩa bắt buộc phải có **hai thread**. Một chương trình chạy tuần tự cũng có thể gây ngoại lệ nếu sửa collection sai cách trong lúc iterator/Spliterator đang duyệt. Tên ngoại lệ không phải bằng chứng về lỗi race đa luồng.

### Ví dụ sai: sửa nguồn ngay trong pipeline

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3));

// VÍ DỤ SAI: không chạy trong code nghiệp vụ.
numbers.stream().forEach(n -> {
    if (n == 2) {
        numbers.add(99); // Can thiệp cấu trúc nguồn đang duyệt.
    }
});
```

Trong nhiều triển khai, đoạn này có thể ném `ConcurrentModificationException`; cũng có thể xuất hiện hành vi không mong đợi khác. **Không dùng ngoại lệ như một cơ chế kiểm soát luồng**. Hãy mô tả phép biến đổi thành một collection mới:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3));

List<Integer> expanded = numbers.stream()
    .flatMap(n -> n == 2
        ? java.util.stream.Stream.of(n, 99)
        : java.util.stream.Stream.of(n))
    .collect(Collectors.toList());

System.out.println(expanded); // [1, 2, 99, 3]
```

Stream không được phép can thiệp nguồn trong các biểu thức hành vi (*behavioral parameters*) trừ khi hợp đồng nguồn cho phép truy cập đồng thời. Ngay cả khi **không có ngoại lệ**, một pipeline sửa nguồn trong `map`, `filter`, `peek` hay `forEach` vẫn có thể sai về ngữ nghĩa.

## 5. Non-interference và stateless: hai nguyên tắc riêng

Tài liệu Stream API đặt yêu cầu lên các hàm hành vi:

1. **Non-interfering:** không sửa nguồn dữ liệu trong khi pipeline đang thực thi, trừ trường hợp nguồn hỗ trợ truy cập đồng thời theo hợp đồng.
2. **Stateless:** kết quả của lambda không được phụ thuộc trạng thái mutable bên ngoài có thể thay đổi theo thời gian trong lúc pipeline chạy.

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", "Binh", "Chi");

// TỐT: lambda chỉ đọc tham số.
long count = names.stream()
    .filter(name -> name.length() >= 3)
    .count();

// KHÔNG NÊN: predicate phụ thuộc biến đếm thay đổi bên ngoài.
final int[] calls = {0};
long unstable = names.stream()
    .filter(name -> ++calls[0] % 2 == 0)
    .count();
```

Đoạn thứ hai có thể cho kết quả phụ thuộc vào số lần hoặc thứ tự gọi predicate. Trong stream song song, biến đếm ngoài còn có vấn đề tranh chấp dữ liệu. Một `AtomicInteger` có thể làm phép đếm nguyên tử, nhưng vẫn **không làm cho việc gắn phần tử với kết quả predicate trở nên xác định theo dữ liệu**.

Để kiểm thử ổn định và dễ mở rộng sang xử lý song song, nên dựa trên thuộc tính của **chính phần tử** hoặc tham số bất biến, không dựa trên lịch thực thi.

## 6. Đặc tính Spliterator giúp nhận biết loại nguồn

`Spliterator.characteristics()` trả về một tập cờ mô tả những tính chất mà người triển khai **cam kết**. Những cờ có ích cho chủ đề này gồm:

| Cờ | Ý nghĩa chính | Điều không được suy diễn |
| --- | --- | --- |
| `ORDERED` | Có encounter order xác định. | Không có nghĩa mọi thread xử lý theo thứ tự đó. |
| `SIZED` | Kích thước được biết chính xác khi không có can thiệp cấu trúc không được phép. | Không có nghĩa nguồn được đóng băng vĩnh viễn. |
| `SUBSIZED` | Spliterator và các phần tách cũng có kích thước xác định theo hợp đồng. | Không phải mọi nguồn đều chia đều hoặc dễ chia. |
| `IMMUTABLE` | Nguồn không thể bị sửa đổi cấu trúc theo phạm vi mà Spliterator duyệt. | Không bảo đảm **bất biến sâu** của từng đối tượng phần tử. |
| `CONCURRENT` | Nguồn hỗ trợ sửa đổi đồng thời an toàn trong quá trình duyệt theo hợp đồng riêng. | Không bảo đảm lượt duyệt là snapshot nhất quán tại một thời điểm. |
| `NONNULL` | Spliterator bảo đảm không phát ra `null`. | Không chứng minh trạng thái ngoài stream không có giá trị null. |
| `DISTINCT` | Các phần tử khác nhau theo quy tắc tương đương của nguồn. | Không bảo đảm được duyệt theo thứ tự sắp xếp. |
| `SORTED` | Có thứ tự sắp xếp theo comparator hoặc thứ tự tự nhiên. | Không chứng minh dữ liệu không thể thay đổi. |

Hai cờ `IMMUTABLE` và `CONCURRENT` có mục tiêu khác nhau: **không sửa đổi cấu trúc** so với **cho phép sửa đổi đồng thời**. Chúng không phải cách bật fail-fast. Nếu tự viết Spliterator, **không được gắn những cờ này chỉ để bỏ qua việc kiểm tra thay đổi nguồn**; phải thực sự thỏa hợp đồng mà cờ đại diện.

Kiểm tra cờ của một Spliterator:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Spliterator;

Spliterator<String> sp =
    new ArrayList<>(Arrays.asList("A", "B")).spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SIZED));   // true
```

Những ví dụ về cờ theo một loại collection cụ thể nên được kiểm tra theo **hợp đồng API của nguồn**, không suy ra từ việc thấy cờ xuất hiện ở một JDK riêng lẻ.

## 7. So sánh `ArrayList`, `CopyOnWriteArrayList` và `ConcurrentHashMap`

Cả ba đều có thể làm nguồn stream nhưng cách nhìn nhận thay đổi nguồn khác nhau:

| Nguồn | Kiểu duyệt đáng chú ý | Khi có thay đổi |
| --- | --- | --- |
| `ArrayList` | Spliterator late-binding, fail-fast theo nỗ lực tối đa | Sửa cấu trúc không đúng thời điểm có thể bị phát hiện và ném `ConcurrentModificationException`; không có bảo đảm an toàn đồng thời. |
| `CopyOnWriteArrayList` | Spliterator dựa trên **snapshot mảng**; thường báo `IMMUTABLE` | Các thay đổi sau lúc tạo snapshot không làm thay đổi những phần tử của lượt duyệt đã chụp. |
| `ConcurrentHashMap` | Spliterator `CONCURRENT`, lượt duyệt **weakly consistent** | Hỗ trợ cập nhật đồng thời; lượt duyệt có thể thấy một phần cập nhật và không thấy phần khác, không phải ảnh chụp nguyên tử. |

### Snapshot bằng `CopyOnWriteArrayList`

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

CopyOnWriteArrayList<String> source =
    new CopyOnWriteArrayList<>(Arrays.asList("A", "B"));

Spliterator<String> snapshot = source.spliterator();
source.add("C");

List<String> result = StreamSupport.stream(snapshot, false)
    .collect(Collectors.toList());

System.out.println(result); // [A, B]
System.out.println(source); // [A, B, C]
```

Snapshot ở đây được tạo khi lấy Spliterator; phần tử `C` thêm về sau không nằm trong snapshot. `CopyOnWriteArrayList` phù hợp khi đọc nhiều hơn ghi, nhưng việc sửa đổi thường phải sao chép mảng và có thể tốn bộ nhớ/thời gian nếu cập nhật liên tục.

**Snapshot của phần tử không phải deep copy:** nếu phần tử là đối tượng mutable, trạng thái bên trong đối tượng ấy vẫn có thể thay đổi. Ví dụ snapshot chứa các `StringBuilder` vẫn tham chiếu đến cùng các `StringBuilder` cũ.

### Lượt duyệt weakly consistent của `ConcurrentHashMap`

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

Map<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("A", 1);
counts.put("B", 2);

// Có thể đọc từ nguồn concurrent trong khi hệ thống tiếp tục cập nhật.
long numberOfKeys = counts.keySet().stream().count();
System.out.println(numberOfKeys); // 2, khi không có cập nhật đồng thời
```

Khi có thread khác thêm/xóa key trong lúc duyệt, **không được yêu cầu** `count()` hoặc `collect()` trả đúng tập key của một thời điểm duy nhất. Weak consistency cho phép duyệt an toàn theo hợp đồng mà **không cần fail-fast**; tính nhất quán nghiệp vụ vẫn cần được thiết kế riêng.

Nếu cần báo cáo chính xác tại một thời điểm, hãy xác định cơ chế snapshot hoặc đồng bộ phù hợp, chứ không chỉ thay `HashMap` thành `ConcurrentHashMap`.

## 8. Dùng `StreamSupport.stream(Supplier, ...)` để trì hoãn lấy nguồn

Khi tự xây stream từ Spliterator, `StreamSupport` có hai nhóm overload thường dùng:

```java
StreamSupport.stream(spliterator, parallel);

StreamSupport.stream(
    spliteratorSupplier,
    characteristics,
    parallel
);
```

Overload thứ nhất nhận một đối tượng Spliterator đã tạo. Overload thứ hai nhận **`Supplier<? extends Spliterator<T>>`**, cho phép trì hoãn lời gọi lấy Spliterator tới **sau khi terminal operation bắt đầu**. Điều này có thể giúp thu hẹp khoảng thời gian bị can thiệp giữa lúc có Spliterator và lúc bắt đầu xử lý.

Ví dụ với `ArrayList`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> source =
    new ArrayList<>(Arrays.asList("A", "B"));

Stream<String> lazySource = StreamSupport.stream(
    () -> source.spliterator(),
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

source.add("C"); // Chưa bắt đầu terminal operation.

List<String> result = lazySource.collect(Collectors.toList());
System.out.println(result); // [A, B, C]
```

Với `ArrayList.spliterator()`, các cờ `ORDERED | SIZED | SUBSIZED` phản ánh những đặc tính mà nguồn này báo. **Tham số `characteristics` của overload dùng supplier phải khớp với các characteristics của Spliterator mà supplier cung cấp**. Không được khai báo `IMMUTABLE` hay `CONCURRENT` nếu danh sách vẫn là `ArrayList` có thể sửa.

**Giới hạn quan trọng:** supplier chỉ giúp trì hoãn thời điểm lấy Spliterator. Nó **không làm cho các thay đổi trong lúc terminal operation đang chạy trở nên an toàn**, không tạo bản sao, và không thay thế đồng bộ hóa.

## 9. Ví dụ Spliterator tự định nghĩa: trì hoãn tạo Iterator

Giả sử ta có một nguồn `List<String>` và muốn điều khiển việc tạo `Iterator` để chỉ bắt đầu từ lần `tryAdvance` đầu tiên. Ví dụ sau minh họa một Spliterator đơn giản, duyệt tuần tự, không hỗ trợ chia:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class DeferredSourceExample {
    static final class DeferredListSpliterator<T>
            implements Spliterator<T> {
        private final List<T> source;
        private Iterator<T> iterator; // Chưa được tạo trong constructor.
        private boolean exhausted;

        DeferredListSpliterator(List<T> source) {
            this.source = Objects.requireNonNull(source);
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action);
            if (exhausted) {
                return false;
            }
            if (iterator == null) {
                iterator = source.iterator(); // Bắt đầu binding.
            }
            if (!iterator.hasNext()) {
                exhausted = true;
                return false;
            }
            action.accept(iterator.next());
            return true;
        }

        @Override
        public Spliterator<T> trySplit() {
            return null; // Không chia: chỉ thích hợp cho lượt duyệt tuần tự.
        }

        @Override
        public long estimateSize() {
            return exhausted ? 0L : Long.MAX_VALUE;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED;
        }
    }

    public static void main(String[] args) {
        List<String> rows =
            new ArrayList<>(Arrays.asList("A", "B"));

        Stream<String> pipeline = StreamSupport.stream(
            () -> new DeferredListSpliterator<String>(rows),
            Spliterator.ORDERED,
            false
        );

        rows.add("C"); // Trước terminal operation và trước lúc tạo iterator.

        List<String> result =
            pipeline.collect(Collectors.toList());
        System.out.println(result); // [A, B, C]
    }
}
```

Điểm cần hiểu trong thiết kế này:

- `DeferredListSpliterator` chưa tạo iterator trong constructor. Nó chỉ tạo iterator khi `tryAdvance` được gọi lần đầu.
- `StreamSupport.stream(Supplier, ...)` còn trì hoãn việc **khởi tạo Spliterator** tới lúc bắt đầu terminal operation.
- `trySplit()` trả `null`, do đó Spliterator **không hỗ trợ chia việc**; thêm `parallel()` không tạo ra khả năng chia hiệu quả.
- `estimateSize()` trả `Long.MAX_VALUE` khi chưa hết phần tử vì ví dụ **không duy trì kích thước chính xác**. Không được khai báo `SIZED` hoặc `SUBSIZED` với triển khai này.
- `Iterator` lấy từ `ArrayList` vẫn có thể fail-fast best-effort. Việc tạo iterator muộn **không cho phép sửa danh sách sau khi đã bắt đầu duyệt**.

Đây là ví dụ học thuật cho một nguồn tự định nghĩa, không phải cách triển khai tối ưu cho `List`: `ArrayList.spliterator()` đã có khả năng ước lượng kích thước và chia công việc tốt hơn. Khi viết Spliterator thật, cần thiết kế thêm `trySplit`, tính chính xác của `estimateSize`, cờ đặc tính và vòng đời tài nguyên.

## 10. Thận trọng với `SIZED`, `SUBSIZED` và tối ưu pipeline

Việc khai báo đặc tính sai có thể khiến Stream API tối ưu dựa trên **giả định không còn đúng**. Ví dụ, trên một nguồn `SIZED` với pipeline không làm thay đổi số phần tử, terminal operation `count()` có thể xác định số lượng mà không cần duyệt từng phần tử và không gọi `peek`:

```java
import java.util.Arrays;

long count = Arrays.asList("A", "B", "C")
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// Các dòng A, B, C không nhất thiết được in bởi peek.
```

Vì vậy, đừng đặt hành động bắt buộc như ghi log giao dịch hoặc cập nhật trạng thái trong `peek` rồi dựa vào `count()` để buộc hành động chạy. Trên một custom Spliterator, việc khai báo `SIZED` trong khi nguồn vẫn tăng/giảm không kiểm soát còn làm kích thước dự kiến thiếu tin cậy.

Với Spliterator có đặc tính `SIZED`, ước lượng kích thước được kỳ vọng là số phần tử chính xác **trong điều kiện không có can thiệp không được phép**. `SUBSIZED` còn đòi hỏi các Spliterator tạo ra sau khi chia cũng giữ tính chất kích thước tương ứng. Không nên gắn hai cờ chỉ để “được tối ưu”.

## 11. Chọn chiến lược an toàn cho nguồn có thể thay đổi

| Yêu cầu | Cách làm phù hợp | Giới hạn |
| --- | --- | --- |
| Nguồn thay đổi **trước khi** bắt đầu xử lý | Dùng một nguồn late-binding thích hợp hoặc supplier tạo Spliterator khi cần | Không được sửa tùy ý trong lúc terminal operation chạy. |
| Cần dữ liệu ổn định để xử lý và tái lập kiểm thử | Sao chép collection trước khi tạo pipeline | Sao chép collection thường chỉ là **shallow copy**. |
| Đọc nhiều, ghi ít, cần traversal snapshot tiện dụng | `CopyOnWriteArrayList` | Chi phí copy khi cập nhật có thể lớn. |
| Cần duyệt trong lúc cập nhật đồng thời | Nguồn hỗ trợ `CONCURRENT` như `ConcurrentHashMap` | Weak consistency không bảo đảm snapshot nguyên tử. |
| Collection dùng chung được đồng bộ bằng khóa | Khóa phù hợp quanh toàn bộ giai đoạn duyệt, nếu mọi tác nhân cùng tuân thủ | Không nên giữ khóa quá lâu hoặc thực hiện I/O chậm trong critical section. |
| Cần tạo nguồn Stream tùy chỉnh | `StreamSupport.stream` với Spliterator/supplier có hợp đồng thật | Phải tự bảo đảm characteristics, chia việc, binding và tài nguyên. |

### Tạo snapshot trước khi chạy pipeline

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> live =
    new ArrayList<>(Arrays.asList("A", "B"));

List<String> snapshot = new ArrayList<>(live);
live.add("C");

List<String> result = snapshot.stream()
    .map(String::toLowerCase)
    .collect(Collectors.toList());

System.out.println(result); // [a, b]
```

Kết quả không bị ảnh hưởng bởi việc thêm `C` **sau khi đã sao chép**. Nhưng thao tác `new ArrayList<>(live)` chỉ là một bước sao chép; nếu `live` đang bị thread khác sửa đồng thời mà không có phối hợp, **bản sao tạo ra không mặc nhiên là snapshot nhất quán**. Cần cơ chế đồng bộ hoặc nguồn hỗ trợ chụp nhất quán.

Khi dữ liệu phần tử là đối tượng mutable, một snapshot collection vẫn có thể nhìn thấy những thay đổi bên trong các phần tử ấy. Nếu cần bất biến sâu, sử dụng kiểu giá trị bất biến hoặc sao chép thích hợp ở cấp phần tử.

### Với `Collections.synchronizedList`

Một `List` được bọc bằng `Collections.synchronizedList` không khiến mọi chuỗi thao tác Stream tự động an toàn. Nếu cần duyệt trong lúc có các tác nhân khác, có thể phải đồng bộ **toàn bộ thời gian duyệt** trên đúng monitor theo hợp đồng wrapper:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

List<Integer> shared = Collections.synchronizedList(
    new ArrayList<>(Arrays.asList(1, 2, 3))
);

synchronized (shared) {
    long total = shared.stream()
        .mapToLong(Integer::longValue)
        .sum();
    System.out.println(total); // 6
}
```

Điều này chỉ có ý nghĩa nếu **mọi thao tác sửa nguồn** trong chương trình cũng tuân thủ cơ chế đồng bộ tương thích. Không giữ khóa lâu để thực thi pipeline có I/O hoặc callback bất định nếu có thể tạo bản sao an toàn rồi tính toán ngoài khóa.

## 12. Những lỗi thường gặp khi thiết kế nguồn tùy chỉnh

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Nghĩ “stream lazy” đồng nghĩa “source chưa bind” | Trạng thái bind phụ thuộc Spliterator và các truy vấn/split trước đó. | Phân biệt thời điểm tạo stream, binding, traversal. |
| Sửa `ArrayList` trong `forEach`/lambda của stream | Can thiệp nguồn đang duyệt, vi phạm non-interference. | Tạo kết quả mới hoặc tách bước cập nhật. |
| Dùng `ConcurrentModificationException` như kiểm tra đồng bộ | Fail-fast chỉ best-effort và không thay thế an toàn luồng. | Dùng snapshot, đồng bộ hoặc nguồn concurrent đúng hợp đồng. |
| Tưởng `List.set` luôn bị fail-fast phát hiện | Đây không nhất thiết là thay đổi cấu trúc. | Không sửa dữ liệu nguồn khi pipeline đang chạy. |
| Khai báo `IMMUTABLE` cho `ArrayList` có thể thêm/xóa | Cờ không phản ánh nguồn. | Chỉ khai báo đặc tính thực sự được bảo đảm. |
| Khai báo `CONCURRENT` để tránh ngoại lệ | Không làm cấu trúc nguồn trở nên thread-safe. | Chọn nguồn concurrent thật và hiểu weak consistency. |
| Khai báo `SIZED` nhưng `estimateSize` không chính xác | Stream có thể tối ưu dựa trên thông tin sai. | Sửa ước lượng/đặc tính; khi không chắc, đừng khai báo `SIZED`. |
| Supplier của `StreamSupport.stream` trả Spliterator có flags khác tham số khai báo | Vi phạm hợp đồng overload nhận supplier. | Đồng bộ đúng các characteristics thực tế. |
| `trySplit` không chia được nhưng mặc định kỳ vọng parallel nhanh | Framework không thể khai thác chia việc hiệu quả. | Thiết kế `trySplit` đúng hoặc chấp nhận tuần tự. |
| Mong một stream concurrent tạo snapshot nguyên tử | Lượt duyệt có thể weakly consistent. | Tạo snapshot/cơ chế nhất quán riêng theo nghiệp vụ. |

## 13. Nguồn gắn với I/O và giới hạn của late binding

Ví dụ `Files.lines` có thể tạo Stream đọc tệp, nhưng việc tạo stream và quá trình tiêu thụ vẫn liên quan đến **tài nguyên I/O**. Tính lazy không có nghĩa mọi thao tác khởi tạo I/O đều được trì hoãn tới khi đọc dòng đầu tiên, cũng không có nghĩa một tệp đang bị thay đổi sẽ được bảo vệ bởi fail-fast.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FirstLines {
    public static List<String> nonEmptyPrefix(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.filter(s -> !s.isEmpty())
                .limit(20)
                .collect(Collectors.toList());
        }
    }
}
```

`try-with-resources` bảo đảm đóng Stream và tài nguyên nguồn trong các đường thực thi thông thường, kể cả khi có ngoại lệ. Terminal operation `collect` hoặc `limit` **không tự động thay thế `close()`**. Khi tệp bị thay đổi trong lúc đọc, phải theo hợp đồng hệ thống tệp và API I/O, **không mặc định** có `ConcurrentModificationException` như với `ArrayList`.

Với nguồn I/O tự định nghĩa, hãy mô tả rõ việc quản lý tài nguyên, phương thức `close`, điều kiện kết thúc, xử lý lỗi và khả năng chia; một Spliterator tự viết chỉ xử lý `tryAdvance` chưa đủ để trở thành nguồn production-ready.

## 14. Cách kiểm thử đúng late binding và fail-fast

Cần tách hai loại kiểm thử:

**Kiểm thử hành vi có hợp đồng xác định:** với nguồn cụ thể hỗ trợ late binding, tạo pipeline, sửa nguồn *trước terminal operation*, rồi xác nhận tập phần tử theo hợp đồng. Hoặc với `CopyOnWriteArrayList`, tạo Spliterator snapshot trước khi thêm phần tử, rồi xác nhận snapshot không có phần tử mới.

**Kiểm thử phát hiện can thiệp:** không viết test yêu cầu `ConcurrentModificationException` **bắt buộc** xuất hiện sau mọi kiểu sửa đổi khi đang duyệt. Cơ chế fail-fast là best-effort, và lịch thực thi đa luồng không ổn định. Thay vào đó, kiểm tra code không thực hiện can thiệp trái hợp đồng, hoặc dùng chiến lược snapshot/đồng bộ mang kết quả xác định.

Ví dụ kiểm thử snapshot ổn định:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

CopyOnWriteArrayList<String> live =
    new CopyOnWriteArrayList<>(Arrays.asList("A", "B"));

Spliterator<String> fixed = live.spliterator();
live.add("C");

List<String> observed = StreamSupport.stream(fixed, false)
    .collect(Collectors.toList());

if (!observed.equals(Arrays.asList("A", "B"))) {
    throw new AssertionError("Snapshot bị thay đổi");
}
```

Khi kiểm tra một custom Spliterator, nên thử thêm: nguồn rỗng; chỉ một phần tử; `tryAdvance` sau khi hết dữ liệu; việc `trySplit` (nếu có) không mất hoặc lặp phần tử; `characteristics` khớp hành vi; và mọi phần tử được phát ra đúng một lần trong điều kiện **không có can thiệp**.

## 15. Bài tập thực hành

**Bài 1 — Ba thời điểm.** Cho `ArrayList` chứa `[1, 2]`. Tạo stream, thêm `3`, rồi `collect`. Giải thích vì sao kết quả của nguồn late-binding có thể chứa `3`. Sau đó dùng `list.spliterator().estimateSize()` trước khi thêm phần tử và giải thích vì sao sửa đổi sau binding là nguy hiểm.

**Bài 2 — Fail-fast best-effort.** Dùng `ArrayList` và thử thêm phần tử trong `forEach`. Quan sát hành vi, nhưng **không** viết bài kiểm thử với kỳ vọng ngoại lệ luôn phải ném. Nêu ít nhất hai lý do fail-fast không phải cơ chế an toàn luồng.

**Bài 3 — So sánh ba nguồn.** Tìm hiểu cơ chế duyệt của `ArrayList`, `CopyOnWriteArrayList` và `ConcurrentHashMap`. Nguồn nào thích hợp khi đọc snapshot? Nguồn nào có khả năng duyệt cùng lúc với cập nhật và có thể thấy một phần thay đổi? Nguồn nào không nên bị sửa trong lúc duyệt?

**Bài 4 — Supplier-based stream.** Dùng `StreamSupport.stream(() -> list.spliterator(), flags, false)` với một `ArrayList` cụ thể. Trình bày thời điểm supplier được gọi, vì sao flags phải khớp Spliterator và vì sao việc dùng supplier không cho phép thay đổi nguồn trong terminal operation.

**Bài 5 — Custom Spliterator.** Dựa trên `DeferredListSpliterator`, giải thích vì sao `trySplit()` trả `null` và `estimateSize()` trả `Long.MAX_VALUE` khi chưa hết. Nếu muốn bổ sung `SIZED` và hỗ trợ chia, bạn phải duy trì những bất biến nào về số phần tử còn lại?

**Bài 6 — Thiết kế an toàn.** Một hệ thống vừa nhận thêm sự kiện vừa tính báo cáo. So sánh ba hướng: khóa nguồn rồi sao chép, dùng nguồn có weak consistency, hoặc chụp snapshot bất biến. Chọn giải pháp khi báo cáo **bắt buộc nhất quán tại một thời điểm** và khi chỉ cần số liệu gần đúng để giám sát.

**Ghi nhớ:** *Late binding* trì hoãn thời điểm Spliterator gắn với nguồn; nó không tự tạo snapshot và không cho phép sửa nguồn tùy ý trong lúc duyệt. *Fail-fast* chỉ cố gắng phát hiện can thiệp bằng `ConcurrentModificationException`, **không phải bảo đảm an toàn đồng thời**. Khi thiết kế nguồn riêng, hãy khai báo `characteristics` trung thực, tôn trọng `non-interference` và chọn rõ giữa snapshot, đồng bộ hay nguồn concurrent theo yêu cầu nhất quán của ứng dụng.
