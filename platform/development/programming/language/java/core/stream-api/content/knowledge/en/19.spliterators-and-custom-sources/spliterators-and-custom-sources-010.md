# Kiểm chứng dữ liệu, thứ tự và tính đúng của các lần chia nguồn

## 1. Tại sao `Spliterator` sai có thể làm sai cả pipeline?

Trong module **JAVA_STREAM_API**, chúng ta thường nhìn thấy pipeline ở dạng:

```java
long count = source.stream()
    .filter(item -> item.active())
    .map(Item::price)
    .reduce(0L, Long::sum);
```

Các thao tác `filter`, `map` và `reduce` chỉ đúng khi **nguồn cung cấp đúng các phần tử cần xử lý**. Với collection chuẩn, Java đã cung cấp cơ chế duyệt phù hợp. Nhưng khi tự xây nguồn thông qua `Spliterator<T>` và `StreamSupport.stream(...)`, lập trình viên phải chịu trách nhiệm về **tính đúng của dữ liệu, thứ tự duyệt và việc chia nguồn**.

Hãy tưởng tượng một nguồn có các ID:

```text
Nguồn gốc:           [0, 1, 2, 3, 4, 5, 6, 7]
Mong muốn chia:      [0, 1, 2, 3] | [4, 5, 6, 7]

Lỗi chồng lấn:       [0, 1, 2, 3, 4] | [4, 5, 6, 7]
                                             ^
                                     ID 4 bị xử lý hai lần

Lỗi để hở khoảng:    [0, 1, 2] | [4, 5, 6, 7]
                                     ^
                               ID 3 bị mất
```

Trong pipeline tuần tự, một lỗi ở `trySplit()` có thể không lộ ra vì Java không nhất thiết gọi phương thức chia nguồn. Đến khi thêm `parallel()`, framework mới chia thành nhiều công việc và **tổng tiền, số bản ghi hoặc dữ liệu đầu ra có thể sai**.

Mục tiêu bài học thuộc chương **Spliterator và nguồn tự định nghĩa**:

1. Hiểu hợp đồng của `tryAdvance`, `forEachRemaining`, `trySplit`, `estimateSize` và `characteristics`.
2. Chứng minh mỗi phần tử gốc xuất hiện **đúng một lần** sau các lần chia, không bị mất hoặc xử lý trùng.
3. Phân biệt **encounter order** với thứ tự thực thi của các worker song song.
4. Khai báo chính xác `ORDERED`, `SIZED`, `SUBSIZED`, `NONNULL`, `IMMUTABLE` và các characteristic khác.
5. Viết một `Spliterator` tùy chỉnh có thể chia theo khoảng chỉ số và kiểm chứng cả tuần tự lẫn song song.
6. Đánh giá rủi ro với nguồn có thể thay đổi, I/O, kích thước không biết trước, hiệu năng và tài nguyên.

Điểm cốt lõi là **đúng trước, nhanh sau**: đặc tính chia được và khả năng chạy song song không có giá trị nếu làm mất dữ liệu.

## 2. `Spliterator<T>` là gì?

`java.util.Spliterator<T>` là giao diện dùng để **duyệt và có thể phân chia** một tập phần tử. Tên gọi kết hợp ý tưởng *split* và *iterator*, nhưng nó không chỉ là `Iterator` có thêm một phương thức: nó mang thông tin về kích thước, thứ tự và khả năng duyệt, để Java Stream API lập kế hoạch xử lý.

Các phương thức quan trọng:

| Phương thức | Hợp đồng cần hiểu |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Giao cho action **một phần tử kế tiếp**, trả `true`; nếu đã hết, trả `false` |
| `void forEachRemaining(Consumer<? super T> action)` | Duyệt các phần tử còn lại; mặc định có thể lặp `tryAdvance` |
| `Spliterator<T> trySplit()` | Trả spliterator mới quản lý **một phần** phần tử còn lại, hoặc `null` nếu không chia |
| `long estimateSize()` | Ước lượng số phần tử còn lại; với `SIZED`, là số lượng chính xác theo hợp đồng |
| `int characteristics()` | Mô tả những tính chất nguồn mà implementation **cam kết** |
| `long getExactSizeIfKnown()` | Trả kích thước chính xác nếu có `SIZED`, ngược lại thường là `-1` |
| `Comparator<? super T> getComparator()` | Chỉ có ý nghĩa khi khai báo `SORTED` |

Đây là cơ chế đứng sau rất nhiều nguồn Stream. Ví dụ:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

List<String> names = List.of("An", "Bình", "Chi");
Spliterator<String> spliterator = names.spliterator();

List<String> copied = StreamSupport
    .stream(spliterator, false)
    .toList();

System.out.println(copied); // [An, Bình, Chi]
```

`StreamSupport.stream(spliterator, false)` tạo stream tuần tự; truyền `true` thì tạo stream có chế độ song song. **Spliterator là nguồn tiêu thụ một lượt**, không phải collection có thể dùng lại: muốn duyệt lại hãy tạo spliterator mới từ nguồn thích hợp.

Tham khảo Javadoc:

- [`Spliterator`, Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html)
- [`StreamSupport`, Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/StreamSupport.html)
- [Package `java.util.stream`: parallelism và non-interference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)

## 3. Hợp đồng `tryAdvance`: không được tự ý mất hoặc nhân bản phần tử

`tryAdvance(action)` có nhiệm vụ chuyển giao **tối đa một phần tử** còn lại và tiến trạng thái duyệt:

```text
cursor = 0, fence = 3
source = [A, B, C]

tryAdvance(action) -> action(A), true;  cursor = 1
tryAdvance(action) -> action(B), true;  cursor = 2
tryAdvance(action) -> action(C), true;  cursor = 3
tryAdvance(action) ->           false; cursor = 3
```

Các kiểm chứng cơ bản:

- Với nguồn có `n` phần tử, duyệt đến hết phải gọi action `n` lần nếu không có lỗi.
- Khi trả `false` vì hết nguồn, không được phát thêm một phần tử.
- Một lần trả `true` phải tương ứng với **một phần tử** được chuyển cho action.
- Sau khi đến cuối, các lần gọi tiếp trên trạng thái không đổi tiếp tục cho biết nguồn đã hết.
- `action` phải khác `null`; implementation có thể kiểm tra bằng `Objects.requireNonNull(action)`.

Không được bỏ qua một phần tử chỉ vì phần tử đó là `null` hoặc không hợp lệ theo nghiệp vụ, trừ khi **nguồn đã được định nghĩa là nguồn có lọc**. Nếu yêu cầu loại bản ghi không hợp lệ, thông thường đặt một bước `filter` hoặc bước kiểm tra dữ liệu tường minh bên trên Spliterator.

**Lưu ý ngoại lệ:** khi action ném ngoại lệ, không nên suy luận rằng một thao tác duyệt thất bại có thể được chạy lại mà không có rủi ro. Hãy thiết kế chính sách lỗi ở mức pipeline và nguồn.

## 4. Hợp đồng `trySplit`: chia hai miền không chồng lấn

`trySplit()` không đơn giản là “trả về một bản sao”. Với spliterator có các phần tử còn lại `S`, sau khi chia:

```text
Trước:
    current -> S

Sau:
    prefix = current.trySplit()
    prefix  -> S_left
    current -> S_right

Yêu cầu:
    S_left ∩ S_right = ∅     (theo VỊ TRÍ phần tử nguồn)
    S_left ∪ S_right = S
```

Với nguồn **`ORDERED`**, `trySplit` phải trả spliterator duyệt một **tiền tố** của các phần tử còn lại và giữ một **hậu tố** trong spliterator ban đầu. Do đó:

```text
Nguồn:             [A, B, C, D, E, F, G]
trySplit trả:      [A, B, C]
current còn lại:           [D, E, F, G]
Ghép theo thứ tự:  [A, B, C, D, E, F, G]
```

Một phần tử có cùng **giá trị** với phần tử khác vẫn là một **vị trí nguồn khác**. Bởi vậy, không thể chỉ kiểm tra `Set` của đầu ra để tìm lỗi trùng hoặc mất:

```text
Nguồn hợp lệ: [7, 2, 7]
Sai:         [7, 2]       // mất một vị trí có giá trị 7
Set cả hai:  {2, 7}      // cùng Set, không chứng minh đúng
```

**Hai phép kiểm tra phải có:**

1. **Độ bao phủ đúng một lần:** số phần tử và số lần xuất hiện của từng giá trị phải khớp nguồn.
2. **Thứ tự đúng:** nếu báo `ORDERED`, thứ tự kết hợp các phần chia theo tiền tố → hậu tố phải khớp encounter order.

`trySplit()` được phép trả `null` nếu không thể hoặc không muốn chia thêm; không có yêu cầu mọi nguồn đều phải chia đôi hoàn hảo. Nhưng nếu trả một spliterator khác `null`, phần chia phải có **tiến triển** và không được giữ lại cùng tập phần tử ở cả hai đối tượng.

## 5. Kích thước: `estimateSize`, `SIZED` và `SUBSIZED`

Khi nguồn có kích thước chính xác, bộ xử lý song song có thể phân phối công việc tốt hơn. Tuy nhiên, khai báo kích thước sai sẽ phá vỡ giả định của các thao tác như `toArray` hoặc `count`.

### 5.1. `SIZED` là lời cam kết, không phải “ước lượng khá đúng”

Nếu spliterator có characteristic `SIZED`, `estimateSize()` phải phản ánh **số phần tử còn lại chính xác** trước khi xử lý, trừ những ngoại lệ liên quan nguồn thay đổi đồng thời theo hợp đồng JDK.

Ví dụ nguồn gồm `8` phần tử:

```text
Trước khi duyệt:  estimateSize() = 8
Sau 1 tryAdvance: estimateSize() = 7
Sau 3 tryAdvance: estimateSize() = 5
Sau khi duyệt hết: estimateSize() = 0
```

`getExactSizeIfKnown()` trả kích thước khi `SIZED` có mặt; nếu không có, nó trả `-1` theo mặc định.

### 5.2. `SUBSIZED` mở rộng cam kết sang mọi phần con

`SUBSIZED` cho biết spliterator hiện tại và **mọi spliterator được sinh bởi các lần chia tiếp theo** đều `SIZED` và `SUBSIZED`. Đây là lời hứa mạnh hơn `SIZED`.

Ví dụ hợp lệ:

```text
parent [0..10): 10 phần tử
   │ trySplit()
   ├─ prefix [0..5):  5 phần tử
   └─ current [5..10): 5 phần tử

prefix.trySplit():
   ├─ prefix [0..2): 2 phần tử
   └─ current [2..5): 3 phần tử
```

Mỗi phần con biết chính xác độ dài của chính nó. Các lần chia duy trì:

\[
\operatorname{size}(\text{trước chia})
=\operatorname{size}(\text{prefix})
+\operatorname{size}(\text{current còn lại})
\]

Đừng gắn `SUBSIZED` cho một nguồn mà spliterator con cần dò đến EOF mới biết kích thước.

### 5.3. Nguồn có kích thước không xác định

Một tệp văn bản đọc dòng, luồng socket hoặc iterator sinh dữ liệu theo điều kiện động thường **không biết trước chính xác số phần tử**. Nếu chưa chứng minh được, bỏ `SIZED` và `SUBSIZED`; `estimateSize` có thể trả một ước lượng hợp lệ hoặc `Long.MAX_VALUE` nếu không xác định.

Với `Spliterators.spliteratorUnknownSize(iterator, characteristics)`, không nên truyền `SIZED`/`SUBSIZED` như thể nguồn đã biết kích thước. Một phần con đã materialize dữ liệu vẫn có thể biết kích thước riêng; điều đó không có nghĩa nguồn tổng thể ban đầu có kích thước chính xác.

## 6. Khai báo `characteristics` phải dựa trên bằng chứng

`Spliterator` định nghĩa các bit đặc tính quan trọng:

| Characteristic | Ý nghĩa cần bảo đảm | Lỗi thường gặp |
| --- | --- | --- |
| `ORDERED` | Có encounter order xác định, và `trySplit` trả tiền tố | Trả hậu tố mà vẫn báo ORDERED |
| `SIZED` | Biết số phần tử còn lại chính xác theo hợp đồng | Trả kích thước ban đầu sau khi đã duyệt |
| `SUBSIZED` | Mọi phần con được chia đều SIZED và SUBSIZED | Dựa vào nguồn có độ dài thay đổi |
| `NONNULL` | Không phát ra phần tử `null` | Nguồn cho phép null nhưng vẫn khai báo |
| `DISTINCT` | Không có hai phần tử bằng nhau theo `equals` | Lẫn lộn vị trí độc lập với giá trị trùng |
| `SORTED` | Dữ liệu theo thứ tự comparator hoặc thứ tự tự nhiên | Có ORDERED nhưng không thật sự sắp |
| `IMMUTABLE` | Nguồn không thể bị sửa cấu trúc khi duyệt | Dùng collection có thể sửa không bảo vệ |
| `CONCURRENT` | Nguồn cho phép thay đổi đồng thời theo hợp đồng | Tự cho là thread-safe vì dùng parallel stream |

Ví dụ kiểm tra bit:

```java
int properties = spliterator.characteristics();

boolean ordered = (properties & Spliterator.ORDERED) != 0;
boolean sized = spliterator.hasCharacteristics(Spliterator.SIZED);
boolean subSized = spliterator.hasCharacteristics(Spliterator.SUBSIZED);
```

**Đặc tính là cam kết về nguồn**, không phải nút bật “tăng tốc”. Khai báo nhiều bit hơn thực tế có thể khiến Stream framework dùng những tối ưu hóa không hợp lệ.

### 6.1. `SORTED` không phải `ORDERED`

`ORDERED` chỉ nói có một thứ tự gặp phần tử, không nói giá trị được sắp tăng. Nếu khai `SORTED`, spliterator còn phải tuân hợp đồng thứ tự và `getComparator()`:

- Có `SORTED` với thứ tự tự nhiên: `getComparator()` trả `null`.
- Có `SORTED` theo comparator riêng: trả comparator phù hợp.
- Không có `SORTED`: `getComparator()` thông thường ném `IllegalStateException`.

Không đánh dấu `SORTED` chỉ vì danh sách trong một lần thử tình cờ đã được sắp.

### 6.2. `IMMUTABLE` khác bất biến sâu của đối tượng

Một danh sách snapshot không cho thêm/xóa phần tử có thể hỗ trợ đặc tính `IMMUTABLE` về **cấu trúc nguồn**. Nhưng nếu mỗi phần tử là object mutable, các field bên trong vẫn có thể đổi và ảnh hưởng `filter` hoặc `map`. Với nguồn snapshot, cần phân biệt:

- **Không đổi tập phần tử và thứ tự**: bảo vệ quyền duyệt.
- **Không đổi nội dung đối tượng**: là cam kết bổ sung của mô hình dữ liệu, không tự có chỉ vì nguồn là list không thể sửa.

### 6.3. `CONCURRENT` không đồng nghĩa “spliterator này thread-safe”

`CONCURRENT` là đặc tính của nguồn có hỗ trợ thay đổi đồng thời khi được duyệt; nó không cấp phép gọi đồng thời `tryAdvance` trên **cùng một đối tượng spliterator tùy chỉnh không đồng bộ**. Mô hình chia nguồn thông thường là mỗi nhánh sở hữu một spliterator và duyệt vùng độc lập.

## 7. Ví dụ hoàn chỉnh: spliterator chia theo khoảng chỉ số

Để kiểm chứng rõ ràng, ta thiết kế nguồn **snapshot từ `List`**:

1. Dữ liệu gốc được chuyển thành danh sách không thể sửa đổi bằng `List.copyOf`.
2. Mỗi spliterator nắm một đoạn **nửa mở** `[cursor, fence)`.
3. `tryAdvance` đọc đúng vị trí `cursor` rồi tăng chỉ số.
4. `trySplit` trả **nửa đầu của đoạn còn lại** và cập nhật spliterator hiện tại để giữ nửa sau.
5. `estimateSize` luôn bằng `fence - cursor`.
6. Nguồn không chứa `null` do `List.copyOf` từ chối null; có thể khai `NONNULL`.

Toàn bộ chương trình sau dùng **JDK 17+**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public final class IndexedSpliteratorDemo {

    private IndexedSpliteratorDemo() {}

    static final class IndexRangeSpliterator<T> implements Spliterator<T> {
        private final List<T> values;
        private int cursor;
        private final int fence;

        IndexRangeSpliterator(List<T> values, int start, int end) {
            this.values = Objects.requireNonNull(values, "values");
            if (start < 0 || end < start || end > values.size()) {
                throw new IllegalArgumentException("Khoảng chỉ số không hợp lệ");
            }
            this.cursor = start;
            this.fence = end;
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");
            if (cursor >= fence) {
                return false;
            }

            T value = values.get(cursor);
            cursor++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator<T> trySplit() {
            int lo = cursor;
            int remaining = fence - lo;
            if (remaining < 2) {
                return null;
            }

            int mid = lo + remaining / 2;
            cursor = mid; // Spliterator hiện tại giữ [mid, fence).
            return new IndexRangeSpliterator<>(values, lo, mid);
            // Spliterator trả về giữ tiền tố [lo, mid).
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
        }
    }

    static <T> Spliterator<T> from(List<T> source) {
        // Snapshot cấu trúc, đồng thời từ chối phần tử null.
        List<T> snapshot = List.copyOf(
            Objects.requireNonNull(source, "source")
        );
        return new IndexRangeSpliterator<>(
            snapshot, 0, snapshot.size()
        );
    }

    static <T> Stream<T> stream(List<T> source, boolean parallel) {
        return StreamSupport.stream(from(source), parallel);
    }

    public static void main(String[] args) {
        List<Integer> input = IntStream.range(0, 9)
            .boxed().toList();

        List<Integer> sequential = stream(input, false).toList();
        List<Integer> parallel = stream(input, true).toList();

        System.out.println(sequential); // [0, 1, 2, 3, 4, 5, 6, 7, 8]
        System.out.println(parallel);   // [0, 1, 2, 3, 4, 5, 6, 7, 8]

        Spliterator<Integer> suffix = from(input);
        Spliterator<Integer> prefix = suffix.trySplit();

        List<Integer> firstPart = new ArrayList<>();
        List<Integer> secondPart = new ArrayList<>();
        Objects.requireNonNull(prefix).forEachRemaining(firstPart::add);
        suffix.forEachRemaining(secondPart::add);

        System.out.println(firstPart);  // [0, 1, 2, 3]
        System.out.println(secondPart); // [4, 5, 6, 7, 8]
    }
}
```

### 7.1. Vì sao các khoảng không chồng lấn?

Giả sử trạng thái trước chia là `[lo, fence)` với độ dài `n = fence - lo`. Khi `n >= 2`:

```text
mid = lo + n / 2

Con được trả: [lo, mid)
Cha còn lại:  [mid, fence)
```

Hai khoảng **không giao nhau** do một bên loại `mid`, bên còn lại bắt đầu ở `mid`; hợp của chúng đúng bằng `[lo, fence)`. Mỗi khoảng nhỏ hơn khoảng trước, nên các lần chia tiếp theo có tiến triển. Khi chỉ còn 0 hoặc 1 phần tử, `trySplit` trả `null`.

### 7.2. Vì sao đặc tính trong ví dụ là hợp lệ?

| Đặc tính | Bằng chứng |
| --- | --- |
| `ORDERED` | Từng khoảng duyệt theo chỉ số tăng; `trySplit` trả tiền tố |
| `SIZED` | `estimateSize() == fence - cursor` luôn chính xác |
| `SUBSIZED` | Mọi phần con đều có đoạn chỉ số xác định và báo đúng độ dài |
| `IMMUTABLE` | Mỗi nhánh dùng snapshot cấu trúc do `List.copyOf` tạo |
| `NONNULL` | `List.copyOf` từ chối phần tử `null` |
| Không `DISTINCT` | Danh sách có thể chứa nhiều giá trị bằng nhau |
| Không `SORTED` | Thứ tự nguồn là thứ tự chỉ số, không phải thứ tự so sánh |
| Không `CONCURRENT` | Không có hợp đồng cho thay đổi cấu trúc nguồn đồng thời |

`List.copyOf` không sao chép sâu từng đối tượng. Nếu `T` là object có field mutable, việc thay đổi field từ bên ngoài vẫn có thể ảnh hưởng hành vi mapper. Dùng record hoặc mô hình bất biến khi cần snapshot nội dung, không chỉ snapshot cấu trúc.

### 7.3. Quyền sở hữu spliterator sau khi chia

Một spliterator không phải thứ nên bị nhiều worker gọi `tryAdvance` đồng thời. Sau khi `trySplit` trả tiền tố, mỗi nhánh có **một đối tượng spliterator** điều khiển đoạn không chồng lấn. Hai đối tượng dùng chung list snapshot để đọc, nhưng không chia sẻ `cursor`; đây là điều kiện quan trọng để chạy song song đúng.

## 8. Kiểm thử thủ công mọi nhánh chia trước khi chạy song song

Một phép thử chỉ gọi `StreamSupport.stream(spliterator, false)` chưa đủ, vì có thể **không hề chạy `trySplit`**. Hãy viết hàm cố tình chia đệ quy đến khi không chia tiếp được, duyệt **nhánh tiền tố trước** rồi **nhánh hậu tố sau**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

static <T> List<T> collectEverySplit(Spliterator<T> current) {
    Spliterator<T> prefix = current.trySplit();
    if (prefix == null) {
        List<T> result = new ArrayList<>();
        current.forEachRemaining(result::add);
        return result;
    }

    List<T> result = collectEverySplit(prefix);
    result.addAll(collectEverySplit(current));
    return result;
}
```

Đây là đoạn mã phương thức trợ giúp đặt trong một lớp Java bất kỳ. Nó đặc biệt phù hợp với spliterator **`ORDERED` có thể chia thành các khoảng tiến triển**. Nếu custom spliterator trả một phần chia không tiến triển (ví dụ trả chính nó), thuật toán đệ quy có thể lặp vô hạn — đó là một lỗi cần phát hiện và sửa trong `trySplit`, không phải một kết quả hợp lệ.

Ví dụ kỳ vọng:

```java
List<Integer> source = List.of(7, 2, 7, 9, 2);
List<Integer> result = collectEverySplit(
    IndexedSpliteratorDemo.from(source)
);

System.out.println(result); // [7, 2, 7, 9, 2]
```

Phép so sánh **danh sách đầy đủ** bắt được cả việc trùng giá trị hợp lệ lẫn việc mất/trùng **vị trí dữ liệu** do chia sai. Đối với nguồn được đánh dấu `UNORDERED`, có thể so sánh **bảng tần suất của các phần tử** và số lượng thay vì áp đặt thứ tự.

### 8.1. Kiểm chứng bằng phương pháp độc lập

Một bộ kiểm thử đáng tin nên có ít nhất ba cách quan sát:

1. **Nguồn chuẩn**: dữ liệu từ một `List` biết trước.
2. **Duyệt không chia**: `forEachRemaining` trên một spliterator mới.
3. **Duyệt đã chia nhiều lần**: `collectEverySplit`.

Sau đó thêm **pipeline tuần tự** và **pipeline song song** dùng các spliterator mới, rồi đối chiếu với nguồn chuẩn.

Đừng tái sử dụng spliterator đã bị tiêu thụ trong nhiều phép thử; chính nó đã thay đổi `cursor` và không có thao tác “rewind” chuẩn.

## 9. JUnit 5: kiểm tra bao phủ, thứ tự, kích thước và dữ liệu biên

Những test sau dùng lớp `IndexedSpliteratorDemo` ở mục 7 và phương thức `collectEverySplit` ở mục 8 (đặt hàm trợ giúp vào lớp test). Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class IndexedSpliteratorDemoTest {

    private static <T> List<T> collectEverySplit(
        Spliterator<T> current
    ) {
        Spliterator<T> prefix = current.trySplit();
        if (prefix == null) {
            List<T> values = new ArrayList<>();
            current.forEachRemaining(values::add);
            return values;
        }
        List<T> values = collectEverySplit(prefix);
        values.addAll(collectEverySplit(current));
        return values;
    }

    @Test
    void emptyAndSingletonSourcesCannotBeSplit() {
        Spliterator<Integer> empty =
            IndexedSpliteratorDemo.from(List.of());
        assertEquals(0L, empty.estimateSize());
        assertNull(empty.trySplit());

        Spliterator<Integer> one =
            IndexedSpliteratorDemo.from(List.of(99));
        assertEquals(1L, one.estimateSize());
        assertNull(one.trySplit());
        assertEquals(List.of(99), collectEverySplit(one));
    }

    @Test
    void splitReturnsPrefixAndPreservesAllElements() {
        List<Integer> source = IntStream.range(0, 9)
            .boxed().toList();
        Spliterator<Integer> suffix =
            IndexedSpliteratorDemo.from(source);

        long before = suffix.estimateSize();
        Spliterator<Integer> prefix = suffix.trySplit();

        assertTrue(prefix != null);
        assertEquals(before,
            prefix.estimateSize() + suffix.estimateSize());
        assertEquals(4L, prefix.getExactSizeIfKnown());
        assertEquals(5L, suffix.getExactSizeIfKnown());

        List<Integer> merged = new ArrayList<>();
        prefix.forEachRemaining(merged::add);
        suffix.forEachRemaining(merged::add);
        assertEquals(source, merged);
        assertEquals(0L, prefix.estimateSize());
        assertEquals(0L, suffix.estimateSize());
    }

    @Test
    void recursiveSplitsNeverLoseOrRepeatPositions() {
        List<Integer> source = IntStream.range(0, 4_097)
            .boxed().toList();

        assertEquals(source, collectEverySplit(
            IndexedSpliteratorDemo.from(source)
        ));
    }

    @Test
    void duplicateValuesArePreservedWithMultiplicity() {
        List<Integer> source = List.of(7, 2, 7, 9, 2);

        assertEquals(source, collectEverySplit(
            IndexedSpliteratorDemo.from(source)
        ));
        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, true).toList());
    }

    @Test
    void sequentialAndParallelToListPreserveEncounterOrder() {
        List<Integer> source = IntStream.range(0, 20_000)
            .boxed().toList();

        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, false).toList());
        assertEquals(source,
            IndexedSpliteratorDemo.stream(source, true).toList());
    }

    @Test
    void characteristicsMatchActualContract() {
        Spliterator<Integer> s =
            IndexedSpliteratorDemo.from(List.of(2, 2, 1));

        assertTrue(s.hasCharacteristics(Spliterator.ORDERED));
        assertTrue(s.hasCharacteristics(Spliterator.SIZED));
        assertTrue(s.hasCharacteristics(Spliterator.SUBSIZED));
        assertTrue(s.hasCharacteristics(Spliterator.IMMUTABLE));
        assertTrue(s.hasCharacteristics(Spliterator.NONNULL));
        assertFalse(s.hasCharacteristics(Spliterator.DISTINCT));
        assertFalse(s.hasCharacteristics(Spliterator.SORTED));
        assertEquals(3L, s.getExactSizeIfKnown());
        assertThrows(IllegalStateException.class, s::getComparator);
    }

    @Test
    void sourceSnapshotIsIndependentOfListStructure() {
        ArrayList<Integer> mutable =
            new ArrayList<>(List.of(1, 2, 3));
        Spliterator<Integer> snapshot =
            IndexedSpliteratorDemo.from(mutable);

        mutable.add(4);
        mutable.remove(0);

        List<Integer> actual = new ArrayList<>();
        snapshot.forEachRemaining(actual::add);
        assertEquals(List.of(1, 2, 3), actual);
    }

    @Test
    void rejectsNullSourceElements() {
        List<Integer> nullable = new ArrayList<>();
        nullable.add(1);
        nullable.add(null);

        assertThrows(NullPointerException.class, () ->
            IndexedSpliteratorDemo.from(nullable)
        );
    }
}
```

**Vì sao dùng `4_097` phần tử trong test?** Độ dài lẻ khiến những lần chia không thể lúc nào cũng chia đôi bằng nhau, giúp phát hiện lỗi off-by-one ở `mid`. Hãy tiếp tục thử các độ dài `0`, `1`, `2`, `3`, `7`, `8`, `9` và các mốc lớn.

Ngoài việc so sánh kết quả, kiểm thử **trạng thái sau mỗi thao tác**: `tryAdvance` làm kích thước giảm đúng một; `trySplit` bảo toàn tổng kích thước; mọi nhánh mới đều báo `SUBSIZED` đúng nếu nguồn công bố đặc tính đó.

## 10. Kiểm chứng chính xác bằng chỉ số khi giá trị có thể trùng

`List.equals` bắt được sai lệch trên nguồn ordered, nhưng với nguồn unordered và nhiều giá trị bằng nhau, nên xây một phép thử **tần suất**.

Ví dụ:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static <T> Map<T, Long> frequency(List<T> values) {
    return values.stream()
        .collect(Collectors.groupingBy(
            Function.identity(),
            Collectors.counting()
        ));
}

List<Integer> input = List.of(1, 2, 1, 2, 2);
List<Integer> output = List.of(2, 1, 2, 1, 2);

System.out.println(frequency(input).equals(frequency(output))); // true
```

Trên nguồn unordered, test nên xác nhận **tần suất** và **số lượng tổng**, thay vì dùng `Set` vì `Set` loại thông tin về số lần xuất hiện. Với đối tượng không có `equals`/`hashCode` theo định danh nghiệp vụ, có thể gắn mỗi phần tử một **ID duy nhất** trong dữ liệu thử hoặc ánh xạ sang ID trước khi so sánh.

Nếu custom spliterator tự tạo đối tượng mới trong `tryAdvance`, hãy xác định tính đúng dựa trên **bản ghi logic** (ID, vị trí, nội dung) thay vì bắt buộc so sánh tham chiếu object.

### 10.1. Vì sao tổng `count` riêng lẻ chưa đủ?

Nguồn `[1,2,3,4]` và đầu ra sai `[1,2,2,4]` đều có `count == 4`. Tổng số phần tử đúng nhưng ID `3` đã mất và ID `2` bị lặp. Cần kết hợp:

- Đếm phần tử.
- Đếm tần suất từng ID.
- Kiểm tra thứ tự khi có `ORDERED`.
- Kiểm tra tính nhất quán khi chia nhiều cấp.

## 11. Thứ tự dữ liệu khác thứ tự chạy song song

Đặc tính `ORDERED` khẳng định **encounter order** của các phần tử, không phải thứ tự thực thi lambda ở các thread.

```java
List<Integer> input = java.util.stream.IntStream.range(0, 100)
    .boxed().toList();

List<Integer> orderedResult =
    IndexedSpliteratorDemo.stream(input, true)
        .map(n -> n * 2)
        .toList();

System.out.println(orderedResult.get(0)); // 0
System.out.println(orderedResult.get(1)); // 2
```

Với stream ordered, `toList()` bảo toàn encounter order trong kết quả, kể cả khi các phần được thực thi đồng thời. Nhưng:

```java
IndexedSpliteratorDemo.stream(input, true)
    .forEach(System.out::println);
// Thứ tự in ra không được bảo đảm là 0, 1, 2, ..., 99.
```

`forEach` trên parallel stream không bảo đảm encounter order; `forEachOrdered` yêu cầu quan sát phần tử theo encounter order nhưng có thể phải đánh đổi chi phí phối hợp.

**Không** dùng log thời điểm chạy `map` hoặc `peek` làm bằng chứng rằng custom spliterator giữ đúng thứ tự. Hãy kiểm tra **kết quả đầu ra theo hợp đồng**, ví dụ `toList()` hoặc một lần duyệt tiền tố → hậu tố bằng tay.

### 11.1. `findFirst` và `findAny`

Với stream ordered:

- `findFirst` tìm phần tử đầu tiên theo encounter order.
- `findAny` có thể trả phần tử bất kỳ, đặc biệt khi chạy song song.

Nếu `trySplit` trả **hậu tố** nhưng spliterator vẫn khai `ORDERED`, những phép phụ thuộc thứ tự như `findFirst`, `limit` hoặc `takeWhile` có thể cho kết quả sai.

### 11.2. `sorted` không sửa được mọi lỗi của nguồn

`sorted` sắp xếp **các phần tử nó nhận được**. Nếu spliterator nguồn đã bỏ sót bản ghi hay phát trùng một ID, `sorted` chỉ sắp xếp tập dữ liệu **đã sai**; nó không thể tái tạo phần tử bị mất.

## 12. Các lỗi phổ biến khi cài đặt `trySplit`

### 12.1. Quên di chuyển biên của spliterator hiện tại

Sai:

```java
// Ý tưởng lỗi: tạo tiền tố nhưng current vẫn giữ nguyên [cursor, fence).
// return new IndexRangeSpliterator<>(values, cursor, mid);
```

Sau khi trả tiền tố `[cursor, mid)`, spliterator ban đầu vẫn duyệt lại từ `cursor`, gây **trùng phần tử**. Phải cập nhật `cursor = mid` khi tách, giống ví dụ đầy đủ.

### 12.2. Bỏ sót phần tử tại biên

Sai:

```java
// Ý tưởng lỗi:
// current.cursor = mid + 1;
// return new IndexRangeSpliterator<>(values, lo, mid);
```

Cả nhánh tiền tố `[lo, mid)` lẫn hậu tố `[mid+1, fence)` đều không chứa phần tử tại chỉ số `mid`. Độ dài đầu ra giảm một so với nguồn.

### 12.3. Trả hậu tố khi đã khai `ORDERED`

Với ordered spliterator, nhánh trả từ `trySplit` phải là **tiền tố** của các phần tử còn lại. Nếu trả hậu tố rồi giữ tiền tố ở đối tượng hiện tại, tổng phần tử có thể vẫn đủ, nhưng phép xử lý cần encounter order sẽ gặp kết quả không đúng hợp đồng.

### 12.4. Trả chính `this` như một phần chia

Trả cùng một object hoặc hai spliterator cùng quản lý một con trỏ làm mất **ownership độc lập**, gây trùng, mất hoặc race khi hai nhánh chạy song song. `trySplit` phải trả một spliterator con đại diện cho phần dữ liệu **không chồng lấn**.

### 12.5. Trả `SIZED` nhưng không cập nhật `estimateSize`

Nếu `tryAdvance` đã duyệt ba phần tử mà `estimateSize` vẫn trả kích thước ban đầu, đặc tính `SIZED` bị khai báo sai. Các phép tối ưu hóa dựa trên kích thước có thể bị ảnh hưởng.

### 12.6. Khai `DISTINCT` dù dữ liệu nguồn có bản ghi trùng

Nếu input có hai phần tử bằng nhau theo `equals`, khai `DISTINCT` là sai, dù hai phần tử đến từ hai vị trí hoặc hai nguồn khác nhau. Các phép như `distinct()` có thể dựa vào characteristic nguồn để tối ưu; kết quả không còn đúng khi tuyên bố sai.

### 12.7. Lạm dụng `IMMUTABLE` hoặc `CONCURRENT`

Khi phần tử bị thêm/xóa trong lúc duyệt mà implementation không hỗ trợ, nguồn có thể thiếu, trùng hoặc ném lỗi. Không khai `IMMUTABLE` cho một `ArrayList` mutable chưa snapshot; không khai `CONCURRENT` chỉ vì ứng dụng muốn chạy `parallelStream()`.

## 13. Mutation, late binding và quyền sở hữu nguồn

Nguồn collection có thể thay đổi theo thời gian. Khi tùy chỉnh spliterator, bạn nên quyết định rõ một trong những mô hình:

1. **Snapshot bất biến:** sao chép cấu trúc trước khi duyệt; dễ chứng minh `SIZED` và `SUBSIZED`.
2. **Late-binding:** chỉ ràng buộc vào tập phần tử khi bắt đầu duyệt hoặc chia, nhưng phải mô tả rõ khả năng quan sát thay đổi trước đó và chính sách với thay đổi sau khi đã bắt đầu.
3. **Nguồn thay đổi đồng thời:** yêu cầu cấu trúc và thuật toán thực sự hỗ trợ traversal trong điều kiện concurrent modification.

Ví dụ `IndexedSpliteratorDemo.from` cố ý chọn **snapshot**, khiến việc thêm/xóa phần tử trong `List` ban đầu **không đổi kết quả duyệt**. Đây là cách đánh đổi thêm bộ nhớ để đơn giản hóa hợp đồng và tránh lỗi race ở cấu trúc nguồn.

### 13.1. Supplier overload của `StreamSupport`

`StreamSupport` còn có overload nhận supplier spliterator:

```java
static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
)
```

Supplier được dùng để tạo spliterator khi terminal operation bắt đầu, giúp giảm khoảng thời gian giữa việc gắn nguồn và lúc duyệt. **Những characteristic truyền vào `stream` phải khớp với spliterator mà supplier trả về**; không được khai một tập bit khác để mong tối ưu.

Ví dụ minh họa:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<Integer> original = List.of(4, 5, 6);
Supplier<Spliterator<Integer>> supplier =
    () -> IndexedSpliteratorDemo.from(original);

int flags = Spliterator.ORDERED | Spliterator.SIZED
    | Spliterator.SUBSIZED | Spliterator.IMMUTABLE
    | Spliterator.NONNULL;

Stream<Integer> stream = StreamSupport.stream(
    supplier, flags, false
);

System.out.println(stream.toList()); // [4, 5, 6]
```

**Cẩn trọng:** supplier overload không tự làm nguồn mutable trở nên thread-safe. Nếu `original` bị sửa đồng thời ngay khi supplier copy, vẫn cần đồng bộ hoặc chính sách snapshot phù hợp. Với dữ liệu nguồn lớn, chi phí snapshot cũng phải được cân nhắc.

## 14. Nguồn I/O và kích thước không biết trước

Một file văn bản có bao nhiêu dòng thường **không biết trước** khi mở. Không nên giả định có thể chia theo khoảng byte như chia một `List` theo chỉ số, bởi:

- Mã hóa văn bản có thể dùng số byte khác nhau cho một ký tự.
- Ranh giới dòng có thể nằm giữa các đoạn dữ liệu.
- Phân chia byte không khéo có thể cắt một dòng thành hai hoặc bỏ mất dòng.
- Nguồn có thể thay đổi hoặc gặp lỗi đọc khi đang duyệt.

Với nguồn tuần tự dùng `Iterator`, có thể sử dụng tiện ích chuẩn:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long countLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        Iterator<String> iterator = reader.lines().iterator();
        Spliterator<String> spliterator =
            Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED | Spliterator.NONNULL
            );

        Stream<String> lines = StreamSupport.stream(
            spliterator, false
        );
        return lines.count();
    }
}
```

Ví dụ này giữ `BufferedReader` mở cho đến sau terminal operation rồi đóng bằng `try-with-resources`. `Spliterators.spliteratorUnknownSize` không được quảng cáo nguồn tổng thể là `SIZED`; nếu cần đọc nhiều tệp, phải định nghĩa thêm quyền sở hữu từng reader/stream con.

**Điều không nên làm:** dùng `Files.size(path)` (số **byte**) làm số phần tử của một spliterator phát **dòng** rồi khai `SIZED`. Số byte không phải số dòng. Một số nguồn có thể cung cấp metadata đủ tin cậy để biết chính xác số bản ghi, nhưng cần kiểm chứng metadata đó thật sự tương ứng với phép duyệt.

### 14.1. `StreamSupport.stream` không tự quản lý close của nguồn I/O

`StreamSupport.stream(spliterator, ...)` tạo một stream dựa trên spliterator nhưng không tự biết phải đóng `BufferedReader` hoặc file descriptor nào do ứng dụng sở hữu. Terminal operation như `count` không phải là lệnh đóng tài nguyên. Hãy dùng `try-with-resources` với owner thích hợp; nếu tạo stream có vòng đời riêng, có thể dùng `onClose`, nhưng caller vẫn phải đóng stream.

## 15. Tính đúng khi song song: ba loại kiểm chứng riêng

Một custom spliterator có thể cho kết quả đúng tuần tự mà vẫn sai khi song song. Khi đánh giá, chia vấn đề thành ba loại:

### 15.1. Kiểm chứng chức năng

So sánh danh sách/tần suất/ID với một **oracle** đáng tin như `List` nguồn, kể cả:

- Nguồn rỗng và singleton.
- Số phần tử chẵn và lẻ.
- Giá trị trùng nhau.
- Nhiều lần chia sâu.
- Các trường hợp ở biên `start`, `mid`, `fence`.
- Nguồn thay đổi trước/sau khi tạo spliterator (theo mô hình đã chọn).

### 15.2. Kiểm chứng hợp đồng thứ tự

Nếu báo `ORDERED`:

- `trySplit` phải trả tiền tố.
- Duyệt các phần chia theo thứ tự tiền tố → hậu tố phải đúng dãy gốc.
- `StreamSupport.stream(spliterator, true).toList()` phải tương ứng dãy gốc.
- Không dùng thứ tự in log của `forEach` làm bằng chứng.

Với nguồn unordered, chỉ kiểm chứng **tần suất và nội dung**, không áp thứ tự không được cam kết.

### 15.3. Kiểm chứng về hiệu năng và tài nguyên

Sau khi chứng minh đúng, mới đo:

| Chỉ số | Vì sao cần xem? |
| --- | --- |
| Thời gian pipeline tuần tự/song song | Xác định song song có thực sự có lợi không |
| Kích thước các phần chia | Phát hiện phân hoạch cực lệch, tạo mất cân bằng |
| Số phần chia | Tránh tạo quá nhiều tác vụ nhỏ |
| CPU và bộ nhớ | Nhận diện allocation và chi phí quản lý snapshot |
| Độ trễ nguồn I/O | Nguồn chậm có thể làm chia thêm không có lợi |
| Số file/tài nguyên đang mở | Không được rò rỉ do nguồn tùy chỉnh |

Đừng giả định `trySplit` cân bằng hoàn hảo hoặc số lời gọi tương ứng với số luồng CPU. Framework có quyền chọn cách phân công. Một benchmark đáng tin phải có warm-up, đầu vào đại diện và cách đo phù hợp (ví dụ JMH ở quy trình tối ưu chuyên biệt).

## 16. Một bản đồ tư duy khi thiết kế nguồn tùy chỉnh

| Câu hỏi | Quyết định và kiểm chứng |
| --- | --- |
| Mỗi vị trí nguồn sẽ được phát mấy lần? | Đúng **một lần**, không mất/trùng |
| Nếu chia nguồn, các phần con quản lý phần nào? | Hợp không thiếu; giao không chồng lấn theo vị trí |
| Nguồn có encounter order không? | Nếu có, trả **tiền tố** từ `trySplit` |
| Kích thước có chính xác không? | Chỉ khai `SIZED` khi thật sự biết |
| Các phần con đều có kích thước chính xác không? | Chỉ khai `SUBSIZED` khi chứng minh được |
| Nguồn có phần tử `null` không? | Chỉ khai `NONNULL` nếu bảo đảm không phát null |
| Dữ liệu đã sắp chưa? | Chỉ khai `SORTED` và trả comparator đúng hợp đồng |
| Có giá trị trùng nhau không? | Đừng khai `DISTINCT` nếu có |
| Cấu trúc nguồn có đổi khi duyệt không? | Chọn snapshot, late-binding hoặc concurrent semantics rõ ràng |
| Có tài nguyên ngoài cần đóng không? | Xác định owner, `try-with-resources` và close handler |
| Có thể dùng chung một spliterator giữa thread không? | Không mặc định; chia thành các object sở hữu miền độc lập |
| Test tuần tự đã đủ chưa? | Chưa; ép chia thủ công nhiều cấp và so sánh chạy song song |
| Chỉ `count` khớp đã chứng minh đúng chưa? | Chưa; kiểm tần suất, thứ tự, kích thước và các biên |
| Có nên thêm `parallel()` không? | Chỉ sau khi đúng và có benchmark |

## 17. Bài tập thực hành

**Bài 1 — Tìm lỗi chồng lấn.** Một spliterator xử lý `[start,end)`, khi chia trả `[start,mid)` nhưng quên cập nhật `start` của đối tượng hiện tại. Dùng dãy ID `0..7` để chỉ ra phần tử nào bị lặp, sửa lại `trySplit` và viết test đếm tần suất từng ID.

**Bài 2 — Lỗi mất phần tử ở biên.** Sau khi chia tại `mid`, một lập trình viên đặt `start = mid + 1` cho đối tượng gốc. Viết test cho các độ dài `1,2,3,7,8,9` để phát hiện phần tử bị bỏ. Giải thích lý do các khoảng **nửa mở** là mô hình hữu ích.

**Bài 3 — Khai báo đặc tính.** Với danh sách snapshot `[3,1,3]` được duyệt theo chỉ số, chọn các bit phù hợp trong `ORDERED`, `SIZED`, `SUBSIZED`, `DISTINCT`, `SORTED`, `NONNULL` và `IMMUTABLE`. Giải thích vì sao `ORDERED` không kéo theo `SORTED`.

**Bài 4 — Kiểm chứng song song.** Dùng `IndexedSpliteratorDemo.stream(source,true)` trên `20_000` ID duy nhất, so với `source` bằng `toList`. Sau đó kiểm thử nguồn có các ID lặp; chỉ so sánh `Set` có phát hiện mọi lỗi không? Viết cách dùng tần suất.

**Bài 5 — `estimateSize`.** Tạo spliterator có `9` phần tử, chia một lần rồi tính tổng `estimateSize` của hai nhánh. Duyệt hai phần tử ở nhánh tiền tố, kiểm tra kích thước còn lại. Giải thích khi nào được khai `SIZED` và `SUBSIZED`.

**Bài 6 — Comparator và `SORTED`.** Tạo một spliterator duyệt danh sách các số theo thứ tự `[1,2,3,4]` và công bố `SORTED`. Nêu yêu cầu của `getComparator`. Sau đó đổi dữ liệu thành `[1,3,2,4]` và phân tích vì sao không thể tiếp tục báo `SORTED`.

**Bài 7 — Nguồn I/O không biết độ dài.** Dùng `BufferedReader.lines()` và `Spliterators.spliteratorUnknownSize` để đếm dòng. Xác định tài nguyên nào phải được đóng, vì sao số byte của file không phải số phần tử, và khác biệt giữa nguồn rỗng với lỗi đọc file.

**Bài 8 — Kiểm thử tính bất biến nguồn.** Tạo `ArrayList<Integer>`, sinh spliterator snapshot, sau đó thêm và xóa phần tử từ `ArrayList` gốc. Kiểm chứng kết quả snapshot giữ đúng dữ liệu đã sao chép. Giải thích vì sao nội dung object mutable vẫn có thể thay đổi dù cấu trúc đã snapshot.

**Bài 9 — Chi phí phân chia.** Với nguồn có `1_000_000` phần tử và mỗi mapper chỉ thực hiện một phép cộng đơn giản, so sánh tuần tự và song song. Theo dõi thời gian, allocation và số phần chia; giải thích vì sao việc tạo quá nhiều tác vụ có thể làm xử lý chậm đi.

## 18. Kết luận và nguyên tắc áp dụng

`Spliterator` là nơi Java Stream API nhận **các phần tử và những lời cam kết về nguồn**. Khi tự cài đặt, điều quan trọng không phải chỉ là viết `trySplit` có trả một đối tượng mới, mà là chứng minh rằng **mọi phần chia tạo ra một phân hoạch chính xác, không chồng lấn, không bỏ sót và bảo toàn encounter order nếu nguồn đã khai `ORDERED`**.

Hãy bắt đầu từ một nguồn nhỏ có dữ liệu chuẩn, kiểm thử `tryAdvance` và `estimateSize`, sau đó cố tình gọi `trySplit` nhiều cấp và đối chiếu đầu ra với nguồn gốc. Chỉ khi các đặc tính `SIZED`, `SUBSIZED`, `NONNULL`, `IMMUTABLE` hoặc `SORTED` được chứng minh đúng mới công bố chúng. Cuối cùng mới đánh giá xử lý song song, quản lý tài nguyên và hiệu năng. Quy trình đó giúp các pipeline khai báo với `filter`, `map`, `reduce`, `collect` và các collector nhiều tầng nhận đúng dữ liệu ngay từ bước nguồn.
