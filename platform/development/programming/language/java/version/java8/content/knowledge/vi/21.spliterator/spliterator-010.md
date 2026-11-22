# StreamSupport và kiểm thử nguồn chạy song song (Java 8+)

Khi một cấu trúc dữ liệu không có sẵn phương thức `stream()` hoặc cần xây dựng nguồn stream riêng, Java cung cấp lớp tiện ích **`StreamSupport`**. Nó biến một **`Spliterator`** thành `Stream<T>`, `IntStream`, `LongStream` hoặc `DoubleStream`, đồng thời cho phép chọn chế độ tuần tự hay song song.

Điểm khó không nằm ở việc truyền `parallel = true`, mà ở **hợp đồng nguồn dữ liệu**: `trySplit()` có chia đúng phần tử không, các nhánh có trùng hoặc bỏ sót không, thứ tự có được giữ theo `ORDERED` không, `estimateSize()` có khớp cờ `SIZED/SUBSIZED` không, và dữ liệu có bị thay đổi trái quy tắc khi terminal operation đang chạy không?

Bài học trình bày cách dùng `StreamSupport`, thiết kế một `Spliterator.OfInt` có thể chia đều, **kiểm thử tính đúng đắn của nguồn trong cả hai chế độ**, cùng những giới hạn cần hiểu trước khi tối ưu hiệu năng. API sử dụng trong ví dụ đã tồn tại từ Java 8 và vẫn được hỗ trợ trong các JDK hiện đại; chương trình tương thích Java 17+.

## 1. Khi nào thực sự cần `StreamSupport`?

Với danh sách hoặc tập hợp thông thường, lựa chọn rõ ràng thường là:

```java
List<String> names = Arrays.asList("Lan", "An", "Binh");
Stream<String> sequential = names.stream();
Stream<String> parallel = names.parallelStream();
```

Đây là ví dụ minh họa với `import java.util.*;` và `import java.util.stream.*;`.

Đối với `Collection`, thường **không cần gọi `StreamSupport` thủ công** vì `stream()` / `parallelStream()` đã sử dụng `Spliterator` của collection. `StreamSupport` hữu ích hơn khi:

- Viết một **kiểu collection hoặc nguồn dữ liệu tùy biến** muốn cung cấp stream mà không cần cài cả interface `Collection`.
- Đang có `Spliterator<T>` (hoặc `Spliterator.OfInt/OfLong/OfDouble`) và muốn biến nó thành pipeline của Stream API.
- Muốn kiểm soát rõ **cách tạo spliterator tại lúc terminal bắt đầu** bằng overload nhận `Supplier`.
- Cần kiểm thử một spliterator tự viết ở chế độ tuần tự và song song để phát hiện sai sót trong `trySplit`, kích thước, thứ tự hoặc cờ đặc tính.

Lưu ý: `StreamSupport` là API cấp thấp, phần lớn dành cho **tác giả thư viện và cấu trúc dữ liệu**. Với một mảng số liên tiếp, `IntStream.range(...)` thường dễ hiểu hơn tự viết Spliterator. Custom Spliterator chỉ nên được dùng khi nguồn có đặc tính hoặc cách duyệt thực sự riêng.

## 2. Hai overload tạo stream và ý nghĩa của `parallel`

Với stream tham chiếu, hai dạng chính:

```java
Stream<T> stream = StreamSupport.stream(spliterator, parallel);

Stream<T> delayed = StreamSupport.stream(
    supplier, characteristics, parallel);
```

Đây là **chữ ký minh họa**, trong đó các biến phải được khai báo với kiểu phù hợp.

| API | Cách nguồn được cung cấp | Nên cân nhắc khi |
| --- | --- | --- |
| `stream(Spliterator<T>, boolean)` | Đã có một spliterator ở lúc tạo stream | Nguồn bất biến, concurrent hoặc spliterator **late-binding** |
| `stream(Supplier<? extends Spliterator<T>>, int, boolean)` | Có hàm tạo spliterator; supplier được gọi muộn | Muốn giảm khoảng thời gian dễ xảy ra can thiệp vào nguồn mutable |
| `intStream(Spliterator.OfInt, boolean)` | Nguồn chuyên biệt cho `int` | Không cần boxing mỗi phần tử |
| `intStream(Supplier<? extends Spliterator.OfInt>, int, boolean)` | Supplier tạo nguồn `int` muộn | Cần late construction cho nguồn primitive |
| `longStream(...)` / `doubleStream(...)` | Các phiên bản chuyên biệt cho `long`/`double` | Nguồn lưu số nguyên dài hoặc số thực |

Cả hai overload của `stream` và các bản primitive đều là API hiện còn được hỗ trợ. Giá trị Boolean:

- `false`: stream được tạo ở chế độ **sequential**.
- `true`: stream được tạo ở chế độ **parallel**.

Có thể kiểm tra bằng `isParallel()` hoặc đổi bằng `parallel()` / `sequential()`. Nhưng **`isParallel() == true` không chứng minh có nhiều luồng đã thực sự xử lý phần tử**; đó chỉ là chế độ của pipeline. Runtime có thể xử lý ít tác vụ khi nguồn nhỏ, `trySplit()` không chia được, hoặc phần việc không đáng chia.

`Spliterator` được stream sử dụng theo nguyên tắc **tiêu thụ một lần**. Muốn so sánh `sequential` với `parallel`, phải tạo **hai spliterator/stream mới**, không dùng lại cùng instance đã duyệt.

### Overload nhận `Supplier` thực sự hoãn điều gì?

```java
int[] limit = {3};

IntStream direct = StreamSupport.intStream(
    new RangeSpliterator(0, limit[0]), false);

IntStream deferred = StreamSupport.intStream(
    () -> new RangeSpliterator(0, limit[0]),
    RangeSpliterator.FLAGS,
    false);

limit[0] = 5;
```

`RangeSpliterator` là lớp được định nghĩa đầy đủ ở mục 8. Đến khi gọi terminal operation:

- `direct.toArray()` cho `[0, 1, 2]` vì **chính constructor `RangeSpliterator`** đã chốt `fence = 3` tại thời điểm tạo. Điều đó **không có nghĩa mọi spliterator truyền trực tiếp đều snapshot sớm**: một spliterator late-binding khác vẫn có thể nhận thay đổi hợp lệ trước traversal.
- `deferred.toArray()` cho `[0, 1, 2, 3, 4]`: supplier tạo spliterator mới **sau khi terminal operation bắt đầu**, khi `limit[0]` đã bằng 5.

Theo hợp đồng `StreamSupport`, `Supplier.get()` được gọi **không quá một lần** và chỉ sau khi terminal operation khởi động. Giá trị `characteristics` truyền vào overload này **phải bằng chính xác** `supplier.get().characteristics()`; nếu không, API cảnh báo hành vi không được xác định.

Supplier giúp **thu hẹp khoảng thời gian** nguồn dễ bị can thiệp khi chưa chạy terminal; nó **không làm cho một collection mutable tự động thread-safe** và không cho phép sửa nguồn tùy tiện trong lúc pipeline đang xử lý.

## 3. Hợp đồng cốt lõi của `Spliterator`

`Spliterator<T>` vừa biết **duyệt phần tử**, vừa biết **chia phần còn lại** thành các nhánh độc lập để hỗ trợ xử lý song song.

| Phương thức | Ý nghĩa | Kiểm tra quan trọng |
| --- | --- | --- |
| `tryAdvance(Consumer)` hoặc `tryAdvance(IntConsumer)` | Tiêu thụ tối đa một phần tử, trả `true` nếu có | Không phát trùng, không vượt giới hạn, hết dữ liệu trả `false` |
| `forEachRemaining(...)` | Duyệt phần còn lại | Phát đúng phần tử còn lại, không thêm/bỏ sót |
| `trySplit()` | Trả một spliterator chứa **một phần** của các phần tử chưa tiêu thụ; spliterator gốc giữ phần còn lại | Hai phần không giao nhau, hợp lại đúng nguồn chưa tiêu thụ |
| `estimateSize()` | Ước lượng lượng phần tử còn lại | Không âm, tương thích cờ `SIZED` và trạng thái sau chia |
| `characteristics()` | Các thuộc tính được spliterator **cam kết** | Chỉ bật cờ đúng với dữ liệu và mọi phương thức |
| `getExactSizeIfKnown()` | Kích thước chính xác khi có `SIZED`, ngược lại `-1` | Có giá trị chính xác nếu nguồn cam kết `SIZED` |

### Những cờ đặc tính quan trọng

| Cờ | Cam kết | Lỗi thường gặp |
| --- | --- | --- |
| `ORDERED` | Có encounter order; khi split, spliterator trả về phải là **tiền tố chặt (strict prefix)** của phần còn lại | Hai nhánh chia xen kẽ nhưng vẫn gắn `ORDERED` |
| `SIZED` | `estimateSize()` phản ánh kích thước chính xác trong những điều kiện do API quy định | Trả `Long.MAX_VALUE` hoặc ước lượng thô mà vẫn bật `SIZED` |
| `SUBSIZED` | Mọi spliterator con tạo bởi `trySplit()` đều có `SIZED` và `SUBSIZED` | Không biết size của nhánh con mà vẫn khai báo `SUBSIZED` |
| `IMMUTABLE` | Nguồn không bị thay đổi cấu trúc trong lúc duyệt | Đánh dấu cho nguồn đang bị `add/remove` tùy ý |
| `CONCURRENT` | Nguồn cho phép thay đổi cấu trúc đồng thời với chính sách nhất quán được tài liệu hóa | Tưởng cứ dùng `parallelStream` là có thể bật `CONCURRENT` |
| `NONNULL` | Mọi phần tử được cung cấp đều khác `null` | Nguồn object có thể chứa `null` |
| `DISTINCT` | Không có cặp phần tử bằng nhau theo `equals` | Dữ liệu chứa trùng lặp |
| `SORTED` | Thứ tự gặp phù hợp thứ tự tự nhiên hoặc một `Comparator` | Không bảo đảm thứ tự nhưng tự gắn `SORTED` |

`Spliterator.CONCURRENT` mô tả **cấu trúc nguồn có thể thay đổi đồng thời theo hợp đồng của nguồn**, **không phải** `Collector.Characteristics.CONCURRENT` và **không phải** điều kiện bắt buộc để chạy một stream song song.

Một spliterator thường **không được giả định thread-safe để nhiều luồng cùng gọi `tryAdvance()` hay `trySplit()` trên cùng instance**. Thay vào đó, framework có thể chia ra các spliterator khác nhau và giao từng phần cho tác vụ riêng (serial thread confinement).

### Kích thước chính xác khi split

Với spliterator có `SIZED | SUBSIZED` và chưa bị duyệt, nếu gọi:

```java
long before = source.estimateSize();
Spliterator.OfInt prefix = source.trySplit();

if (prefix != null) {
    long after = prefix.estimateSize() + source.estimateSize();
    // Với SUBSIZED trong điều kiện trên, before == after.
}
```

Đoạn minh họa này giả định `source` là `Spliterator.OfInt` và mọi phép cộng size nằm trong miền `long` hợp lệ.

`SUBSIZED` đòi các spliterator con cũng có kích thước chính xác. Với một số nguồn cây hoặc dữ liệu bất cân bằng, nguồn có thể biết tổng `SIZED` nhưng không biết chính xác kích thước các nhánh; **không nên bật `SUBSIZED` khi không thực sự đáp ứng được**.

## 4. `trySplit()` quyết định khả năng chạy song song hữu ích

Nếu spliterator chưa hết phần tử mà gọi `trySplit()`:

- Nó có thể trả về `null` khi không thể hoặc không đáng chia. **Không bắt buộc** mọi spliterator đều phải chia được.
- Nếu trả về một spliterator con, **phần tử của con phải được loại khỏi phần còn lại của cha**; hai nhánh không được phát chung phần tử.
- Nếu có `ORDERED`, nhánh trả về phải là **tiền tố** của phần tử chưa được duyệt. Như vậy thứ tự toàn bộ có thể phục hồi bằng cách duyệt nhánh con trước rồi đến phần còn lại của nhánh cha.
- Đối với nguồn hữu hạn, chia lặp lại cuối cùng phải dừng. Một thuật toán cứ trả nhánh không thu nhỏ có thể gây chia mãi hoặc lãng phí tác vụ.
- Chia cân đối (thường gần một nửa) tạo cơ hội tốt để các tác vụ có lượng việc tương tự, nhưng hiệu năng còn phụ thuộc chi phí tạo nhánh và độ nặng của phép tính.

Ví dụ cho dãy nguyên chưa tiêu thụ `[0, 1, 2, 3, 4, 5, 6, 7]`:

```text
trước split:        [0,1,2,3,4,5,6,7]   estimateSize = 8
                               |
                 trySplit():    |
                /              \
prefix trả về: [0,1,2,3]  nguồn còn: [4,5,6,7]
    size 4                            size 4

Hai nửa không trùng; ghép prefix trước + nguồn còn = nguồn gốc.
```

Điều cần kiểm thử là **tính đúng đắn của phép chia**, không phải chỉ việc `trySplit() != null`. Một spliterator có thể trả nhánh con nhưng vẫn sai vì làm mất phần tử, phát trùng hoặc đảo thứ tự.

## 5. Thiết kế một nguồn primitive `RangeSpliterator`

Ví dụ đầy đủ bên dưới mô hình hóa nửa khoảng nguyên **`[startInclusive, endExclusive)`** với `startInclusive >= 0`. Đây là nguồn hữu hạn, không thay đổi sau khi tạo, có kích thước chính xác và encounter order tăng dần.

Các thuộc tính:

- `index`: phần tử tiếp theo chưa tiêu thụ.
- `fence`: cận trên loại trừ, cố định sau constructor.
- `tryAdvance`: phát đúng `index` rồi tăng 1; trả `false` khi `index == fence`.
- `trySplit`: chia phần còn lại ở giữa; trả nhánh chứa các phần tử nhỏ hơn và dịch `index` của nhánh cha đến midpoint.
- `estimateSize`: `fence - index`, luôn không âm nhờ validate đầu vào.
- `FLAGS`: `ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL`. Đây đều là cam kết thật sự của một nguồn số nguyên nửa khoảng bất biến.

Có thể có thêm `DISTINCT` vì dãy không trùng, nhưng ví dụ không bật cờ không thiết yếu. **Không gắn `SORTED` tùy tiện**: nếu đã gắn, còn phải tuân theo hợp đồng `getComparator()` và thứ tự tăng dần; ví dụ cố ý giữ bộ cờ tối thiểu dễ kiểm tra.

### Lưu ý thiết kế quan trọng

`index + (fence - index) / 2` tính midpoint từ hai cận hợp lệ của ví dụ. Constructor giới hạn miền `0 <= startInclusive <= endExclusive`. Nếu thiết kế miền `int` bao trùm giá trị âm/dương cực lớn hoặc khoảng hiệu vượt giới hạn `int`, phải dùng phép toán `long` hoặc cách tính midpoint không tràn tương ứng. Không mở rộng mã ví dụ sang miền khác mà bỏ qua giới hạn được khai báo.

`Objects.requireNonNull(action)` làm rõ hợp đồng về consumer null. Khi action tự ném exception, exception phải được truyền ra; không âm thầm nuốt lỗi hoặc tự phát lại phần tử đã được tiêu thụ.

## 6. Kiểm thử nguồn: thứ tự ưu tiên là tính đúng đắn

Một bộ test hữu ích nên kiểm tra **hai tầng**.

### Tầng A — kiểm thử riêng spliterator

1. **Nguồn rỗng:** `tryAdvance` trả `false`, `estimateSize()==0`, `trySplit()==null`.
2. **Một phần tử:** được phát đúng một lần và không nhất thiết phải split; ví dụ `RangeSpliterator` trả `null`.
3. **Chẵn/lẻ, kích thước không phải lũy thừa của 2:** các nhánh chia vẫn phủ toàn bộ dữ liệu, không trùng/bỏ sót.
4. **Chia lặp đệ quy:** duyệt prefix trước, suffix sau, kiểm tra danh sách bằng dãy chuẩn.
5. **`SIZED/SUBSIZED`:** kích thước trước split bằng tổng kích thước hai nhánh (khi chưa traversal); sau mỗi `tryAdvance` đúng một phần tử, `estimateSize` giảm tương ứng.
6. **Cờ đặc tính:** `hasCharacteristics(FLAGS)` đúng; không báo `CONCURRENT` nếu nguồn không có chính sách thay đổi cấu trúc đồng thời.
7. **Không chia vô hạn:** nửa khoảng dương co dần; test dùng kích thước 0, 1, 2, 3, 17 và 10.000.

### Tầng B — kiểm thử qua `StreamSupport`

Tạo **mỗi lần một spliterator mới** rồi so:

```java
int[] expected = IntStream.range(0, size).toArray();

int[] sequential = StreamSupport.intStream(
    new RangeSpliterator(0, size), false).toArray();

int[] parallel = StreamSupport.intStream(
    new RangeSpliterator(0, size), true).toArray();

if (!Arrays.equals(expected, sequential)
        || !Arrays.equals(expected, parallel)) {
    throw new AssertionError("Mismatch at size " + size);
}
```

Đoạn trên là minh họa rút từ chương trình hoàn chỉnh tại mục 8. `toArray()` là phép terminal rõ ràng: nó buộc thực sự tạo ra các giá trị nguồn và cho phép so từng phần tử. Vì spliterator khai báo `ORDERED`, `toArray()` có thể trả kết quả theo encounter order kể cả khi pipeline ở chế độ song song.

**Không chỉ kiểm tra `count()`:** với nguồn `SIZED`, Stream API có thể tối ưu tính count mà không cần duyệt từng phần tử, nên một `tryAdvance` bị lỗi vẫn có thể lọt qua test chỉ gọi `count()`. Cũng **không dùng số lần `peek()` chạy làm tiêu chí đúng** vì pipeline được phép bỏ qua các stage không ảnh hưởng đến kết quả terminal.

### Tại sao không kiểm tra số luồng?

Việc đếm tên thread từ `peek()`/`forEach()` có thể thay đổi theo máy, độ lớn dữ liệu, môi trường chạy và cách runtime tối ưu. Chế độ `parallel` không bảo đảm sẽ dùng ít nhất hai thread cho mọi trường hợp. Test chức năng phải khẳng định **giá trị và thứ tự hợp đồng**, không khẳng định "bắt buộc có 4 thread" hoặc "cứ parallel là nhanh hơn".

Nếu cần đánh giá khả năng khai thác song song, nên có **benchmark riêng**, dữ liệu đủ lớn, công việc đủ nặng và phép đo tái lặp (ví dụ JMH). Benchmark không được thay cho test về dữ liệu đúng.

## 7. Các dạng test cần bổ sung khi mở rộng nguồn tùy biến

| Khía cạnh | Ý tưởng kiểm thử | Vì sao quan trọng |
| --- | --- | --- |
| Kích thước và biên | 0, 1, 2, 3, 17, rất lớn, gần giới hạn miền cho phép | Lỗi off-by-one và split lệch thường lộ ở biên |
| Trùng/bỏ sót | So `toArray()` với dữ liệu chuẩn; nếu unordered, so multiset/tần suất | Đếm tổng không phát hiện đồng thời một phần tử bị mất và phần tử khác bị lặp |
| `ORDERED` | So mảng **đúng vị trí** với nguồn chuẩn | Một phép `sum()` không phát hiện đảo thứ tự |
| Không `ORDERED` | So multiset hoặc map tần suất, không ép thứ tự | Nguồn unordered hợp lệ không phải lỗi |
| Split thủ công | Chia đệ quy rồi duyệt prefix trước suffix | Bắt lỗi xảy ra ngay trong `trySplit()` mà parallel runtime có thể không kích hoạt ở test nhỏ |
| `SIZED/SUBSIZED` | So `getExactSizeIfKnown()`, sum kích thước sau split | Khai báo sai khiến một số phép toán stream tối ưu sai |
| Supplier | Thay đổi dữ liệu **trước** terminal, kiểm tra supplier tạo nguồn mới | Đảm bảo hiểu late construction và characteristics chính xác |
| Source mutation | Không sửa nguồn trong lúc pipeline chạy, trừ khi cấu trúc concurrent cho phép và định nghĩa rõ semantics | Tránh data race/undefined behavior |
| Exception propagation | Consumer ném lỗi thì exception phải xuất hiện | Không nuốt exception rồi coi stream đã xử lý đúng |
| Tái sử dụng | Không dùng lại Spliterator/Stream đã tiêu thụ | Dùng lại có thể cho kết quả thiếu, rỗng hoặc lỗi |
| Tính quyết định | Chạy lặp nhiều lần; đối chiếu reference implementation | Phát hiện sai sót chỉ nổi lên khi chia tác vụ khác nhau |

**Đặc biệt:** với nguồn **unordered**, so set thuần túy có thể bỏ lọt lỗi trùng phần tử. Hãy so **multiset** hoặc map tần suất nếu phần tử hợp lệ được phép trùng. Với nguồn `ORDERED`, so `int[]` theo vị trí là cách trực tiếp nhất.

## 8. Chương trình Java hoàn chỉnh (chạy được với JDK 17+)

Tạo file **`StreamSupportSourceDemo.java`** dưới đây. Mã sử dụng API Java 8, không cần thư viện ngoài.

Chương trình tự kiểm tra sáu kích thước nguồn, chia đệ quy bằng `trySplit()`, so sánh output sequential với parallel, xác nhận `SIZED/SUBSIZED`, và minh họa sự khác nhau giữa spliterator tạo trước và overload nhận supplier.

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class StreamSupportSourceDemo {

    static final class RangeSpliterator implements Spliterator.OfInt {
        static final int FLAGS = Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED | Spliterator.IMMUTABLE
                | Spliterator.NONNULL;

        private int index;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive < 0 || endExclusive < startInclusive) {
                throw new IllegalArgumentException("invalid range");
            }
            index = startInclusive;
            fence = endExclusive;
        }

        @Override
        public OfInt trySplit() {
            int mid = index + (fence - index) / 2;
            if (mid == index) {
                return null;
            }
            OfInt prefix = new RangeSpliterator(index, mid);
            index = mid;
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
        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action);
            while (index < fence) {
                action.accept(index++);
            }
        }

        @Override
        public long estimateSize() {
            return (long) fence - index;
        }

        @Override
        public int characteristics() {
            return FLAGS;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Duyệt mọi nhánh được tách, luôn xử lý prefix trước suffix.
    static void drainInOrder(Spliterator.OfInt source, List<Integer> out) {
        long before = source.estimateSize();
        Spliterator.OfInt prefix = source.trySplit();

        if (prefix == null) {
            source.forEachRemaining((IntConsumer) out::add);
            return;
        }

        check(before == prefix.estimateSize() + source.estimateSize(),
                "split sizes");
        drainInOrder(prefix, out);
        drainInOrder(source, out);
    }

    public static void main(String[] args) {
        int[] sizes = {0, 1, 2, 3, 17, 10_000};

        for (int size : sizes) {
            int[] expected = IntStream.range(0, size).toArray();

            RangeSpliterator probe = new RangeSpliterator(0, size);
            check(probe.hasCharacteristics(RangeSpliterator.FLAGS), "flags");
            check(probe.getExactSizeIfKnown() == size, "exact size");

            int[] sequential = StreamSupport.intStream(
                    new RangeSpliterator(0, size), false).toArray();
            int[] parallel = StreamSupport.intStream(
                    new RangeSpliterator(0, size), true).toArray();

            List<Integer> manuallySplit = new ArrayList<>();
            drainInOrder(new RangeSpliterator(0, size), manuallySplit);
            int[] manual = manuallySplit.stream()
                    .mapToInt(Integer::intValue).toArray();

            check(Arrays.equals(expected, sequential),
                    "sequential " + size);
            check(Arrays.equals(expected, parallel),
                    "parallel " + size);
            check(Arrays.equals(expected, manual),
                    "split " + size);
        }

        int[] bound = {3};
        IntStream direct = StreamSupport.intStream(
                new RangeSpliterator(0, bound[0]), false);
        IntStream deferred = StreamSupport.intStream(
                () -> new RangeSpliterator(0, bound[0]),
                RangeSpliterator.FLAGS, false);

        bound[0] = 5; // Chỉ thay đổi trước khi bắt đầu terminal operation.

        System.out.println("cases passed: " + sizes.length);
        System.out.println("parallel ordered: " + Arrays.toString(
                StreamSupport.intStream(
                        new RangeSpliterator(0, 8), true).toArray()));
        System.out.println("parallel sum: " + StreamSupport.intStream(
                new RangeSpliterator(0, 10_000), true)
                .asLongStream().sum());
        System.out.println("direct snapshot: " +
                Arrays.toString(direct.toArray()));
        System.out.println("supplier deferred: " +
                Arrays.toString(deferred.toArray()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StreamSupportSourceDemo.java
java StreamSupportSourceDemo
```

**Kết quả chuẩn** — nếu bất kỳ `check(...)` nào sai, chương trình sẽ ném `AssertionError` thay vì in đủ kết quả:

```text
cases passed: 6
parallel ordered: [0, 1, 2, 3, 4, 5, 6, 7]
parallel sum: 49995000
direct snapshot: [0, 1, 2]
supplier deferred: [0, 1, 2, 3, 4]
```

Giải thích:

1. Sáu kích thước `0, 1, 2, 3, 17, 10_000` đều được kiểm bằng ba cách: stream tuần tự, stream song song và chia/duyệt thủ công. Việc so mảng theo vị trí phát hiện lỗi trùng, mất hoặc đảo thứ tự.
2. `drainInOrder` gọi `trySplit` cho đến khi không thể chia thêm; mỗi lần kiểm tra tổng size hai nhánh bằng size trước chia. Đây là kiểm thử thực tế của `SIZED/SUBSIZED`, không chỉ đọc cờ.
3. `parallel ordered` là 0 đến 7 đúng thứ tự dù được cấu hình `parallel = true`, vì nguồn `ORDERED` và `toArray()` bảo toàn encounter order.
4. `parallel sum` bằng `0 + 1 + ... + 9999 = 49.995.000`; dùng `asLongStream()` để tính tổng trong kiểu `long`, tránh phụ thuộc giới hạn của tổng `int` khi mở rộng quy mô dữ liệu.
5. `direct snapshot` và `supplier deferred` khác nhau do **thời điểm tạo `RangeSpliterator`**, không phải vì một overload tự động ngăn mọi dạng sửa đổi nguồn.

Tại đây `trySplit()` chỉ thay đổi `index` của spliterator gốc và tạo một spliterator prefix mới. Mỗi nhánh có trạng thái riêng sau split, vì vậy không có hai luồng nào phải cùng sửa một `index` để duyệt các nhánh của range.

## 9. Mở rộng sang `Stream<T>` và các nguồn thực tế

Nếu nguồn đã cung cấp một `Spliterator<T>` tin cậy, cách tạo stream tham chiếu rất ngắn:

```java
List<String> words = Arrays.asList("a", "b", "c");

List<String> copy = StreamSupport
    .stream(words.spliterator(), true)
    .collect(Collectors.toList());

// copy = [a, b, c] vì nguồn List có encounter order.
```

Đoạn mã độc lập này cần `import java.util.*;` và `import java.util.stream.*;`. Nhưng với `List` thông thường, `words.parallelStream()` nói rõ ý định hơn và tránh thao tác cấp thấp không cần thiết.

### Nguồn primitive và tránh boxing

Nếu dữ liệu thực chất là `int`, `long` hoặc `double`, ưu tiên `Spliterator.OfInt`/`OfLong`/`OfDouble` và `StreamSupport.intStream/longStream/doubleStream`. Nếu chuyển ngay nguồn primitive thành `Stream<Integer>`, có thể phải boxing nhiều phần tử, gây thêm chi phí bộ nhớ/CPU.

Ví dụ:

```java
long total = StreamSupport.intStream(
        new RangeSpliterator(0, 10_000), true)
    .asLongStream()
    .sum();
```

Mã này không boxing từng `int` khi tính tổng và vẫn tận dụng được việc chia nguồn.

### Nguồn dữ liệu mutable, iterator hoặc I/O

- Nguồn có thể thay đổi cấu trúc trước terminal nhưng **không có cơ chế late binding**: cân nhắc overload dùng `Supplier` để tạo spliterator đúng thời điểm; đảm bảo cờ characteristics được truyền chính xác.
- Nguồn hỗ trợ duyệt một lượt, ví dụ iterator đọc tệp hoặc dữ liệu từ cursor: `trySplit` có thể không hiệu quả. `parallel = true` **không biến mọi iterator thành nguồn song song hữu ích**.
- Nguồn có tài nguyên như tệp/socket: Stream là `AutoCloseable` nhưng một stream tạo từ spliterator tùy biến **không tự đóng tài nguyên tùy biến nếu không tích hợp cơ chế đóng**. Cần quản lý vòng đời nguồn và cân nhắc `onClose(...)`/`try-with-resources` khi phù hợp.
- Đối với nguồn mutable thông thường, **không sửa nguồn từ các thao tác `map`/`filter`/`forEach`** đang duyệt nó. Nếu cấu trúc hỗ trợ cập nhật concurrent, phải xác định chính sách nhất quán của chính nguồn và không hứa mọi phần tử xuất hiện chính xác một lần dưới mọi lịch cập nhật nếu API không cam kết.

`StreamSupport` là cầu nối giữa nguồn và pipeline; nó **không sửa chữa một `Spliterator` có hợp đồng sai** hoặc tự tạo snapshot an toàn cho nguồn thay đổi đồng thời.

## 10. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Đặt `parallel=true` rồi coi như chắc chắn nhiều thread chạy | `trySplit` có thể không chia, nguồn nhỏ, scheduler tùy môi trường | Kiểm tra `isParallel()` cho chế độ, benchmark riêng cho mức song song thực tế |
| `trySplit` trả phần tử đã còn ở spliterator gốc | Bị trùng dữ liệu | Sau split, hai phần **không giao nhau**, hợp lại đúng phần chưa tiêu thụ |
| `trySplit` không trả strict prefix nhưng báo `ORDERED` | `findFirst`/`toArray` có thể cho kết quả sai thứ tự | Nhánh con trả tiền tố, cha giữ phần còn lại |
| Luôn trả `this` hoặc nhánh không nhỏ đi | Có thể chia vô hạn, tranh chấp hoặc mất phần tử | Mỗi nhánh riêng và tiến dần đến `null` |
| Khai báo `SIZED` khi size chỉ là ước lượng | Các tối ưu hóa stream có thể tin kích thước sai | Bỏ `SIZED` nếu không có bảo đảm chính xác |
| Khai báo `SUBSIZED` nhưng kích thước các con không biết | Vi phạm hợp đồng của mọi descendant | Chỉ bật khi mọi nhánh con cũng `SIZED | SUBSIZED` |
| Bật `CONCURRENT` vì muốn parallel nhanh | Đây là cờ của **nguồn cho phép cập nhật đồng thời**, không phải yêu cầu của parallel | Chỉ bật khi nguồn có chính sách cập nhật concurrent đúng |
| Cho đặc tính truyền vào overload `Supplier` khác với đặc tính thực | API quy định hành vi không xác định | Khai báo đúng **toàn bộ** mask characteristics của spliterator được tạo |
| Dùng một spliterator đã duyệt cho cả sequential và parallel | Nguồn đã bị tiêu thụ, dữ liệu thiếu | Tạo một spliterator **mới cho mỗi test** |
| Chỉ kiểm tra `sum` hoặc `count` | Sum có thể không phát hiện trùng/mất đồng thời; count có thể tối ưu không duyệt | So từng phần tử/multiset và split thủ công |
| Dùng `peek` để bắt buộc đếm số phần tử đã duyệt | Runtime có thể bỏ qua callback khi tối ưu | Dùng terminal `toArray` và test nội dung đầu ra |
| Dùng `forEach(System.out::println)` và ép thứ tự in | `forEach` không cam kết encounter order trong parallel | Dùng `forEachOrdered` nếu cần, hoặc test `toArray` |
| Trộn nhiều luồng sửa cùng một `Spliterator` không thread-safe | Race trên vị trí duyệt và trạng thái | Phân nhánh đúng, giao từng spliterator cho một luồng tại một thời điểm |
| Sửa nguồn thường trong lúc terminal chạy | Có thể sai dữ liệu, lỗi hoặc behavior không xác định | Giữ nguồn ổn định; chỉ dùng concurrent source khi có hợp đồng phù hợp |
| Dùng `StreamSupport` cho mọi `List` | Phức tạp không cần thiết | Dùng `list.stream()` hoặc `list.parallelStream()` |
| Đo tốc độ một lần trên máy cá nhân | Kết quả nhiễu bởi JIT, GC, kích thước dữ liệu, CPU | Dùng phép đo lặp có kiểm soát; JMH khi cần benchmark tin cậy |

## 11. Tự luyện tập

**Bài 1 — Sửa `trySplit` bị mất dữ liệu.** Một spliterator biểu diễn `[0, 10)`, `trySplit` trả `[0, 5)` nhưng đồng thời dịch chỉ số của nguồn gốc lên `6`. Điều gì xảy ra?

**Đáp án:** Phần tử `5` bị mất: prefix trả 0..4, nguồn gốc chỉ còn 6..9. Phải đặt chỉ số nguồn gốc về đúng midpoint `5` và kiểm tra phép nối hai nhánh trả đúng 0..9.

**Bài 2 — Nhận diện test không đủ mạnh.** Tại sao `StreamSupport.intStream(custom, true).sum() == expectedSum` chưa chứng minh nguồn đúng?

**Đáp án:** Một phần tử có thể bị bỏ sót và phần tử khác bị lặp hoặc thay bằng giá trị bù khiến tổng không đổi. Cần đối chiếu đầy đủ các phần tử (mảng theo vị trí nếu `ORDERED`, multiset nếu unordered), đồng thời test trực tiếp `trySplit`.

**Bài 3 — Kiểm tra kích thước.** Một spliterator báo `SUBSIZED`; trước split size là 100, sau split prefix size 40 và suffix size 50. Có hợp lệ không?

**Đáp án:** Không với nguồn `SUBSIZED` trong điều kiện không có traversal/cập nhật cấu trúc hợp lệ giữa phép đo: tổng 40+50=90 không bằng 100. Phải sửa tính kích thước/chia hoặc ngừng khai báo đặc tính không đáp ứng.

**Bài 4 — Tại sao `Supplier` không phải giải pháp chống race?** Một chương trình tạo stream với `StreamSupport.stream(supplier, flags, true)`, sau đó sửa `ArrayList` trong lúc terminal đang xử lý. Có an toàn không?

**Đáp án:** Không mặc định. Supplier chỉ trì hoãn việc lấy nguồn đến lúc terminal bắt đầu; nó không tự đồng bộ `ArrayList` và không hợp thức hóa việc sửa cấu trúc nguồn trong quá trình duyệt.

**Bài 5 — Khi nào dùng `parallel = false`?** Một nguồn chỉ đọc từ socket theo từng thông điệp, không hỗ trợ chia, và mỗi phần tử được xử lý rất nhẹ.

**Đáp án:** Thông thường nên bắt đầu bằng tuần tự, vì stream song song có thể không mang lợi ích và phần duyệt nguồn vẫn là nút thắt. Nếu cần xử lý message song song, hãy tách giai đoạn đọc I/O khỏi giai đoạn xử lý bằng kiến trúc có hàng đợi/backpressure phù hợp và đo hiệu năng thực.

**Bài 6 — Cờ characteristics.** Một nguồn tăng dần `0..99` là immutable, ordered, có size chính xác và chia khoảng nửa đầu. Có thể khai báo `ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL` không?

**Đáp án:** Có nếu cả cách duyệt và `trySplit` thật sự giữ các bảo đảm này. Không tự gắn `CONCURRENT`: việc nhiều nhánh được xử lý song song không có nghĩa cấu trúc nguồn hỗ trợ cập nhật cấu trúc đồng thời.

## 12. Checklist trước khi đưa một nguồn stream tùy biến vào production

- [ ] Nguồn và phạm vi phần tử được định nghĩa rõ (biên, thứ tự, khả năng thay đổi).
- [ ] `tryAdvance`/`forEachRemaining` phát đúng các phần tử còn lại, không trùng/bỏ sót.
- [ ] `trySplit` trả phần **không giao** và giảm công việc còn lại; với `ORDERED` luôn là strict prefix.
- [ ] `estimateSize`, `SIZED`, `SUBSIZED` nhất quán trên mọi nhánh.
- [ ] Chỉ khai báo `IMMUTABLE`, `CONCURRENT`, `DISTINCT`, `SORTED`, `NONNULL` khi thật sự đúng.
- [ ] Mỗi test dựng spliterator mới; so kết quả sequential/parallel và chia thủ công.
- [ ] Test dữ liệu rỗng, một phần tử, chẵn/lẻ, kích thước lớn và các biên miền hợp lệ.
- [ ] Không phụ thuộc số lượng thread, thứ tự `forEach` hoặc thời gian chạy tức thời để khẳng định tính đúng.
- [ ] Đối với overload `Supplier`, `characteristics` truyền vào bằng chính xác mask của spliterator được cấp.
- [ ] Không có shared mutable state thiếu đồng bộ, hoặc nguồn concurrent có hợp đồng rõ ràng.
- [ ] Đã đo thử bằng dữ liệu đại diện trước khi kết luận parallel mang lại lợi ích.
- [ ] Nếu nguồn giữ tài nguyên, có cơ chế đóng đúng vòng đời.

### Tài liệu API chính thức, còn áp dụng

- [`StreamSupport` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/StreamSupport.html): các overload `stream`, `intStream`, `longStream`, `doubleStream`, dùng `Supplier` và quy tắc đặc tính chính xác.
- [`Spliterator` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html): `trySplit`, `estimateSize`, `ORDERED`, `SIZED`, `SUBSIZED` và các luật kích thước/thứ tự.
- [`Stream` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): terminal operation, encounter order, non-interference, khả năng tối ưu bỏ qua callbacks.
- [`java.util.stream` — Java SE 26 package documentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html): stream sources, parallelism và các ràng buộc xử lý.
- [Java SE 27 Release Notes (15/09/2026)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): đối chiếu với bản Java được phát hành hiện nay. Các API sử dụng trong bài vẫn có thể dùng trên JDK hiện đại.