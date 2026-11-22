# Đặc tính `SIZED`, `SUBSIZED`, `IMMUTABLE` và `CONCURRENT`

> **Chương:** Spliterator và nguồn tự định nghĩa  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers; đồng thời đánh giá giới hạn về trạng thái, tài nguyên và hiệu năng.

Khi lập trình với Java Stream API, ta thường để `List`, `Set` hoặc thư viện chuẩn tạo `Spliterator` tự động. Nhưng nếu muốn đưa một nguồn dữ liệu riêng vào Stream — một dải số, bộ đọc bản ghi, cây dữ liệu hay cấu trúc có thể thay đổi đồng thời — người lập trình cần mô tả **nguồn có những đặc tính gì** để thư viện Stream duyệt, chia công việc và tối ưu cho đúng.

Bốn đặc tính quan trọng là `SIZED`, `SUBSIZED`, `IMMUTABLE` và `CONCURRENT`. Chúng không chỉ là nhãn hiệu năng: khai báo sai có thể khiến phép toán cho kết quả không chính xác hoặc gặp hành vi không được bảo đảm.

Mục tiêu của bài:

1. Giải thích chính xác ý nghĩa của từng đặc tính và cách kiểm tra chúng.
2. Phân biệt **kích thước biết chính xác**, **khả năng chia thành các phần có kích thước chính xác**, **nguồn ổn định**, và **nguồn cho phép thay đổi đồng thời**.
3. Tự viết `Spliterator.OfInt` cho dải số cố định, khai báo đúng các đặc tính và dùng `StreamSupport`.
4. Hiểu vì sao `CONCURRENT` không đồng nghĩa chính đối tượng `Spliterator` có thể được nhiều luồng gọi đồng thời; nhận diện rủi ro với nguồn thay đổi trong lúc duyệt.

## 1. `Spliterator` giữ vai trò gì trong Stream?

`Spliterator<T>` là giao diện dùng để **duyệt** và có thể **chia** một nguồn phần tử. Những phương thức nền tảng gồm:

| Phương thức | Vai trò |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Đưa tối đa một phần tử vào action; trả `false` khi không còn phần tử. |
| `void forEachRemaining(Consumer<? super T> action)` | Duyệt các phần tử còn lại; có triển khai mặc định dựa trên `tryAdvance`. |
| `Spliterator<T> trySplit()` | Thử tách một phần công việc để duyệt độc lập; có thể trả `null`. |
| `long estimateSize()` | Ước tính số phần tử còn lại; đôi khi là kích thước chính xác. |
| `int characteristics()` | Trả tập cờ mô tả đặc tính của nguồn và quá trình duyệt. |
| `boolean hasCharacteristics(int flags)` | Kiểm tra xem **tất cả** cờ được yêu cầu có hiện diện không. |
| `long getExactSizeIfKnown()` | Nếu có `SIZED`, trả `estimateSize()`; nếu không, trả `-1`. |

Luồng dữ liệu có thể hình dung như sau:

```text
Nguồn dữ liệu
     │
     ▼
 Spliterator<T> ──► trySplit() ──► các Spliterator con
     │                                  │
     └──────────── tryAdvance() ◄───────┘
                        │
                        ▼
          Stream pipeline (filter/map/...)
                        │
                        ▼
            terminal operation
```

Các cờ thuộc `Spliterator` nằm trong `java.util.Spliterator`. Chúng là bit flags, có thể ghép bằng toán tử OR theo bit `|` và kiểm tra bằng `hasCharacteristics(...)`. Chúng **khác** `Collector.Characteristics`, là tập đặc tính của phép thu thập chứ không phải của nguồn.

## 2. Tổng quan bốn đặc tính

| Đặc tính | Cam kết chính | Không được hiểu nhầm thành |
| --- | --- | --- |
| `SIZED` | `estimateSize()` biểu diễn chính xác số phần tử còn lại theo hợp đồng tại thời điểm tương ứng, khi không có can thiệp cấu trúc ngoài ý muốn. | Có thể truy cập ngẫu nhiên từng phần tử hoặc luôn chia nhanh. |
| `SUBSIZED` | Spliterator hiện tại **và tất cả Spliterator sinh ra từ `trySplit()`** đều có `SIZED` và `SUBSIZED`. | Việc chia luôn cân bằng hoặc nhất định chia được. |
| `IMMUTABLE` | Nguồn phần tử không thể bị thay đổi cấu trúc (thêm, thay thế, xóa phần tử) trong quá trình duyệt. | Mọi đối tượng phần tử đều bất biến; hoặc bộ đếm duyệt không thay đổi. |
| `CONCURRENT` | Nguồn phần tử có thể được thay đổi đồng thời bởi các luồng mà không cần đồng bộ bên ngoài, theo hợp đồng của nguồn. | Bản thân **một** đối tượng Spliterator an toàn để nhiều luồng cùng gọi `tryAdvance`; hoặc kết quả là snapshot cố định. |

Các đặc tính biểu diễn **những bảo đảm có thật**, không phải mục tiêu mong muốn. Nếu chưa chứng minh được một cờ đúng cho mọi trường hợp hỗ trợ, đừng khai báo cờ đó chỉ để tìm cách tăng tốc.

## 3. `SIZED`: kích thước chính xác

Với `SIZED`, `estimateSize()` phải cho số lượng phần tử còn lại đúng theo hợp đồng khi nguồn không bị can thiệp cấu trúc trái với chính sách duyệt. Một dải số cố định `[1, 11)` có đúng 10 phần tử; sau khi đã tiêu thụ 3 phần tử thì còn 7.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> sp = List.of("A", "B", "C").spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.SIZED)); // true
System.out.println(sp.getExactSizeIfKnown());                 // 3
```

`getExactSizeIfKnown()` trả `-1` khi Spliterator không khai báo `SIZED`. Điều đó **không có nghĩa nguồn rỗng**: chỉ có nghĩa không có bảo đảm kích thước chính xác bằng API này.

### Phân biệt `estimateSize()` và `getExactSizeIfKnown()`

- `estimateSize()` luôn là phương thức trên `Spliterator`. Với nguồn không biết kích thước hoặc vô hạn, giá trị có thể là `Long.MAX_VALUE`.
- `getExactSizeIfKnown()` cung cấp cách kiểm tra an toàn khi cần kích thước **được đặc tính `SIZED` bảo đảm**.
- Kích thước còn lại có thể giảm khi `tryAdvance` đã xử lý phần tử; không nên coi nó là số lượng ban đầu cố định trong cả vòng đời duyệt.
- `SIZED` không tự nói rằng số phần tử sau `filter` vẫn biết trước: điều kiện lọc có thể loại bỏ số lượng chưa đoán được.

Ví dụ nguồn chỉ cung cấp `Iterator`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

Iterator<String> iterator = List.of("A", "B", "C").iterator();
Spliterator<String> unknown = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
);

System.out.println(unknown.hasCharacteristics(Spliterator.SIZED)); // false
System.out.println(unknown.getExactSizeIfKnown());                 // -1
```

Ở ví dụ này, danh sách thực tế chứa 3 phần tử nhưng adapter từ `Iterator` được yêu cầu xử lý theo kiểu **không biết kích thước**. Đừng gắn `SIZED` khi chưa có cách đếm chính xác, nhất là với nguồn nhận dữ liệu liên tục.

### Ảnh hưởng đến tối ưu trong Stream

Thư viện Stream có thể sử dụng thông tin kích thước để cấp phát hoặc tối ưu phép toán. Ví dụ, một số pipeline có kích thước đã biết có thể tính `count()` mà **không phải thực thi từng action của `peek`**.

```java
long count = List.of(10, 20, 30).stream()
        .peek(System.out::println)
        .count();

System.out.println("count = " + count); // 3
// Các dòng từ peek có thể không được in.
```

Vì vậy, không đặt logic nghiệp vụ có side effect bắt buộc trong `peek` rồi kỳ vọng mọi phần tử đều được duyệt. `SIZED` chỉ cung cấp thông tin cho việc tối ưu, không phải lời hứa một chiến lược thực thi duy nhất.

## 4. `SUBSIZED`: mỗi nhánh được chia đều biết kích thước chính xác

`SUBSIZED` là cam kết mạnh hơn `SIZED` về **tính chất được bảo toàn sau khi chia**: tất cả Spliterator tạo ra từ `trySplit()`, kể cả những lần chia tiếp theo, đều có `SIZED` và `SUBSIZED`.

```text
Spliterator gốc [0..15]   SIZED + SUBSIZED, 16 phần tử
          │
       trySplit()
       ┌──┴───┐
       ▼      ▼
      [0..7] [8..15]     8 + 8 = 16
       │      │
    split    split
     │        │
   [0..3]   [8..11]     mỗi nhánh biết chính xác số phần tử
```

Một Spliterator có `SIZED` **chưa chắc có `SUBSIZED`**. Có cấu trúc nguồn xác định được tổng kích thước nhưng không bảo đảm mọi phần con sau chia đều xác định chính xác số phần tử còn lại. Chỉ gắn `SUBSIZED` khi thuật toán `trySplit` và các nhánh con bảo đảm được điều đó.

### Hai điều kiện thực tế nên kiểm chứng

1. Mỗi lần `trySplit()` trả một nhánh khác `null`, hai nhánh đại diện cho các phần tử **không chồng lắp và không bỏ sót**, theo hợp đồng nguồn.
2. Cả nhánh trả về và nhánh còn lại báo kích thước chính xác, các lần chia kế tiếp vẫn duy trì `SIZED | SUBSIZED`.

`SUBSIZED` **không** cam kết luôn chia được: `trySplit()` có thể trả `null` nếu lượng công việc quá nhỏ hoặc nguồn không hỗ trợ chia hữu ích. Nó cũng không cam kết chia ra hai nửa cân bằng tuyệt đối, chỉ cam kết các Spliterator đều báo kích thước chính xác.

## 5. `IMMUTABLE`: nguồn không thay đổi cấu trúc trong lúc duyệt

`IMMUTABLE` cho biết nguồn phần tử **không thể bị thay đổi cấu trúc** (thêm, thay thế hoặc xóa phần tử) trong quá trình Spliterator duyệt. Điều này giúp việc duyệt không phải thiết kế để phản ứng với các sửa đổi cấu trúc bất ngờ.

Cần phân biệt:

- **Nguồn bất biến trong lúc duyệt:** tập phần tử và vị trí/quan hệ của chúng không bị thêm, thay thế, xóa.
- **Đối tượng phần tử bất biến:** các trường của mỗi đối tượng không thể thay đổi. `IMMUTABLE` trên Spliterator **không tự bảo đảm** điều thứ hai.
- **Trạng thái duyệt bất biến:** con trỏ của Spliterator không thay đổi. Điều này **không đúng**: `tryAdvance()` vẫn phải cập nhật vị trí duyệt.

Ví dụ, một dải số được xác định hoàn toàn bởi hai biên cố định có nguồn logic bất biến, dù con trỏ `next` trong Spliterator tăng sau mỗi lần đọc.

### Không nhầm `IMMUTABLE` với `Collections.unmodifiableList`

Một *unmodifiable view* chỉ từ chối sửa đổi **qua view**, nhưng collection nền vẫn có thể bị thay đổi qua tham chiếu khác. Không thể vì đã bọc bằng `Collections.unmodifiableList(original)` mà khẳng định tùy ý rằng nguồn không thể thay đổi cấu trúc.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> original = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(original);

original.add("C"); // view cũng quan sát được thay đổi này.
```

Vì thế, hãy xem **hợp đồng thực tế của nguồn** thay vì suy đoán cờ từ kiểu biến. `IMMUTABLE` cũng không đồng nghĩa phép đọc bản thân đối tượng phần tử được đồng bộ với mọi phép thay đổi trạng thái ở luồng khác.

## 6. `CONCURRENT`: nguồn cho phép thay đổi đồng thời

`CONCURRENT` diễn tả **khả năng của nguồn phần tử** chịu được việc thêm, thay thế hoặc xóa phần tử từ các luồng khác trong lúc duyệt, theo cơ chế của nguồn đó, không đòi hỏi người gọi phải đặt khóa đồng bộ bên ngoài.

Một ví dụ điển hình là các view từ `ConcurrentHashMap`:

```java
import java.util.Set;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;

Set<String> keys = ConcurrentHashMap.<String>newKeySet();
keys.add("A");
keys.add("B");
keys.add("C");

Spliterator<String> sp = keys.spliterator();
System.out.println(sp.hasCharacteristics(Spliterator.CONCURRENT)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SIZED));      // false
```

Spliterator của nguồn đồng thời thường có kiểu duyệt **weakly consistent**: không yêu cầu bản sao tức thời của toàn bộ dữ liệu. Khi phần tử được thêm hoặc xóa trong lúc duyệt, những thay đổi đó **có thể được quan sát hoặc không** tùy thời điểm và hợp đồng của cấu trúc nguồn.

```java
// Ví dụ bổ sung sau đoạn trên:
keys.add("D");
sp.forEachRemaining(System.out::println);

// Không viết bài kiểm thử phụ thuộc chính xác vào việc "D"
// có được sp quan sát hay không nếu nguồn đang bị sửa đồng thời.
```

### Cờ `CONCURRENT` KHÔNG nói `Spliterator` thread-safe

Điều phải phân biệt là:

| Đối tượng | Phạm vi bảo đảm |
| --- | --- |
| **Nguồn** có `CONCURRENT` | Cho phép sửa đổi cấu trúc đồng thời theo hợp đồng nguồn. |
| **Một đối tượng `Spliterator` cụ thể** | Không tự có bảo đảm an toàn khi nhiều luồng gọi đồng thời `tryAdvance()` hoặc `trySplit()` trên **chính nó**. |
| **Các Spliterator đã tách ra** | Stream có thể phân phối từng nhánh độc lập tới các tác vụ, đúng theo hợp đồng chia nguồn. |
| **Lambda/collector của pipeline** | Vẫn phải tự thỏa hợp đồng không can thiệp, tính độc lập hoặc an toàn đồng thời thích hợp. |

Đặc tính này cũng khác `Collector.Characteristics.CONCURRENT`: một cờ nói về **nguồn**, cờ kia nói về cách **bộ thu thập** tích lũy.

### Vì sao nguồn concurrent thường không khai báo `SIZED`?

Kích thước của tập phần tử có thể thay đổi giữa hai lần đọc khi luồng khác thêm hoặc xóa phần tử. Dù `ConcurrentHashMap.size()` trả một con số, nó không có nghĩa `Spliterator` có thể bảo đảm kích thước còn lại chính xác xuyên suốt việc duyệt đang chịu sửa đổi đồng thời.

Vì vậy, một Spliterator cấp cao của nguồn cho phép cập nhật đồng thời thường **không** khai báo `SIZED`/ `SUBSIZED`. Không nên thêm `SIZED` chỉ vì có sẵn phương thức `size()` nếu số lượng thực sự duyệt có thể biến động.

## 7. Ví dụ Java 17+ hoàn chỉnh: tự xây dựng dải số có `SIZED | SUBSIZED | IMMUTABLE`

Để nhìn rõ sự liên quan giữa các đặc tính và phương thức, hãy xây dựng một Spliterator trên khoảng số nguyên **`[fromInclusive, toExclusive)`**, không âm và có hai biên cố định.

Lưu mã sau vào `SpliteratorCharacteristicsDemo.java`:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorCharacteristicsDemo {

    static final class FixedRangeSpliterator implements Spliterator.OfInt {
        private int next;
        private final int fence;

        FixedRangeSpliterator(int fromInclusive, int toExclusive) {
            if (fromInclusive < 0 || toExclusive < fromInclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.next = fromInclusive;
            this.fence = toExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (next >= fence) {
                return false;
            }
            action.accept(next++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = next;
            int remaining = fence - lo;
            if (remaining < 2) {
                return null;
            }

            int mid = lo + remaining / 2;
            next = mid;
            // Nhánh trả về là tiền tố [lo, mid);
            // đối tượng hiện tại giữ hậu tố [mid, fence).
            return new FixedRangeSpliterator(lo, mid);
        }

        @Override
        public long estimateSize() {
            return (long) fence - next;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                    | Spliterator.SIZED
                    | Spliterator.SUBSIZED
                    | Spliterator.IMMUTABLE
                    | Spliterator.NONNULL
                    | Spliterator.DISTINCT;
        }
    }

    public static void main(String[] args) {
        FixedRangeSpliterator source = new FixedRangeSpliterator(1, 11);

        System.out.println("SIZED + SUBSIZED: "
                + source.hasCharacteristics(
                        Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("IMMUTABLE: "
                + source.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("Ban đầu: "
                + source.getExactSizeIfKnown());

        Spliterator.OfInt prefix = source.trySplit();
        System.out.println("Nhánh trái: "
                + prefix.getExactSizeIfKnown());
        System.out.println("Nhánh phải: "
                + source.getExactSizeIfKnown());

        // Tạo nguồn MỚI để không dùng lại Spliterator đã thử chia.
        int sum = StreamSupport.intStream(
                new FixedRangeSpliterator(1, 11), true
        ).sum();
        System.out.println("Tổng 1..10: " + sum);
    }
}
```

Kết quả:

```text
SIZED + SUBSIZED: true
IMMUTABLE: true
Ban đầu: 10
Nhánh trái: 5
Nhánh phải: 5
Tổng 1..10: 55
```

### Phân tích từng cam kết

1. **`SIZED`:** số phần tử còn lại được tính chính xác bằng `fence - next`. Mỗi lần `tryAdvance` tiêu thụ một giá trị, `next` tăng tương ứng.
2. **`SUBSIZED`:** `trySplit` tạo hai khoảng không giao nhau. Cả hai dùng cùng lớp nên vẫn có `SIZED | SUBSIZED`; các lần chia tiếp theo giữ quy tắc đó.
3. **`IMMUTABLE`:** nguồn logic là tập số cố định của khoảng; không có API để thay đổi danh sách giá trị cấu thành nguồn trong lúc duyệt. Việc `next` thay đổi chỉ là tiến độ duyệt, không phải sửa nguồn.
4. **`ORDERED`:** các số có thứ tự tự nhiên trong khoảng, và nhánh tách ra là **tiền tố** của phần còn lại.
5. **`NONNULL` và `DISTINCT`:** mỗi phần tử là số nguyên nguyên thủy, không null, và mỗi giá trị trong khoảng xuất hiện đúng một lần.
6. **Không có `CONCURRENT`:** ví dụ không cung cấp nguồn cho phép thay đổi cấu trúc đồng thời; cũng không cho phép nhiều luồng chia sẻ và cùng gọi `tryAdvance` trên một đối tượng.

`StreamSupport.intStream(spliterator, parallel)` dùng `Spliterator.OfInt` làm nguồn cho `IntStream`. Giá trị `parallel = true` cho phép thực thi song song; nó **không bảo đảm** chắc chắn nhanh hơn hoặc phải tách thành nhiều tác vụ trong mọi tình huống.

Đối với nhu cầu dải số thông thường, dùng `IntStream.range(1, 11)` có sẵn sẽ đơn giản hơn; việc tự viết `FixedRangeSpliterator` ở đây nhằm học rõ hợp đồng khi tạo nguồn riêng.

## 8. So sánh hai tình huống sử dụng

| Tình huống | `SIZED` | `SUBSIZED` | `IMMUTABLE` | `CONCURRENT` |
| --- | --- | --- | --- | --- |
| Dải số cố định trong ví dụ `FixedRangeSpliterator` | Có | Có | Có | Không |
| Nguồn kiểu `Iterator` được bọc bởi `spliteratorUnknownSize` | Không được cam kết | Không được cam kết trên Spliterator ban đầu | Không tự suy ra | Không tự suy ra |
| `ConcurrentHashMap.newKeySet().spliterator()` | Không | Không | Không | Có |
| Một nguồn tùy biến tự viết | Chỉ khi chứng minh được | Chỉ khi mọi nhánh chứng minh được | Chỉ khi nguồn không bị sửa cấu trúc | Chỉ khi nguồn hỗ trợ sửa cấu trúc đồng thời đúng hợp đồng |

Không được suy từ `List`, `Set` hoặc một tên lớp chung rằng mọi Spliterator đều có cùng bộ cờ; hãy xét **implementation và cách nguồn được cung cấp**. Có thể xem các cờ thực tế bằng `characteristics()` hoặc `hasCharacteristics(...)`, nhưng hiểu đúng hợp đồng nguồn mới là điều kiện để viết Spliterator tùy chỉnh.

## 9. Late-binding, can thiệp cấu trúc và tính nhất quán

Một Spliterator có thể là **late-binding**: nó liên kết với nội dung nguồn tại một thời điểm muộn, thường gần lần duyệt/chia đầu tiên, thay vì chốt tập phần tử ngay khi lấy Spliterator. Điều này có thể giúp giảm khoảng thời gian chịu tác động của những thay đổi cấu trúc trước khi bắt đầu xử lý.

Tuy nhiên, late-binding **không tự đồng nghĩa `CONCURRENT` hoặc `IMMUTABLE`**. Khi nguồn bị thay đổi sau thời điểm liên kết, hành vi phụ thuộc chính sách cụ thể của nguồn: có thể phát hiện thay đổi rồi ném `ConcurrentModificationException`, có thể duyệt yếu nhất quán, hoặc có thể có chính sách khác.

Ba chính sách cần phân biệt:

- **Fail-fast, best-effort:** cố phát hiện can thiệp cấu trúc không được phép và báo lỗi, nhưng không nên dùng ngoại lệ để bảo đảm đồng bộ dữ liệu.
- **Snapshot:** duyệt một tập phần tử được chốt trước; thay đổi của nguồn sau thời điểm chốt không xuất hiện trong tập đang duyệt. Việc tạo snapshot có thể tốn bộ nhớ hoặc chi phí sao chép.
- **Weakly consistent:** cho phép tiếp tục duyệt khi nguồn đồng thời thay đổi, nhưng không bảo đảm nhìn thấy chính xác mọi cập nhật theo một thời điểm duy nhất.

`Spliterator.CONCURRENT` cho biết khả năng **nguồn bị thay đổi an toàn khi đang duyệt**, không phải một khẳng định nó đồng thời cung cấp snapshot. Nguồn concurrent thường mang chính sách yếu nhất quán, nhưng chính sách cụ thể phải dựa trên tài liệu của cấu trúc nguồn đó.

### Cách tạo Stream từ nguồn tùy biến

Có hai dạng phổ biến:

```java
// Tạo Stream từ Spliterator đã có:
StreamSupport.stream(spliterator, parallel)

// Tạo Stream từ supplier cung cấp Spliterator khi bắt đầu terminal operation:
StreamSupport.stream(supplier, characteristics, parallel)
```

Hai dòng trên là **minh họa chữ ký API**, không phải chương trình độc lập. Overload nhận `Supplier<? extends Spliterator<T>>` có thể giúp hạn chế thời gian giữa lúc lấy Spliterator và khi bắt đầu duyệt nguồn. Khi dùng overload này, **cờ `characteristics` truyền vào phải phù hợp với cờ của Spliterator do supplier tạo ra**, nếu không hành vi không được bảo đảm theo hợp đồng API.

## 10. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Khai báo `SIZED` vì biết số phần tử lúc khởi tạo, dù nguồn có thể thêm/xóa tùy ý khi duyệt | `estimateSize` không còn là kích thước đúng; Stream có thể tối ưu trên thông tin sai | Chỉ khai báo khi bảo đảm chính xác theo hợp đồng; nếu không, bỏ `SIZED`. |
| Khai báo `SUBSIZED` nhưng `trySplit` tạo nhánh không biết kích thước | Vi phạm cam kết cho nhánh con | Kiểm tra cả nhánh trả về và nhánh còn lại, kể cả sau nhiều cấp chia. |
| Dùng `IMMUTABLE` cho một unmodifiable view có nguồn nền vẫn thay đổi | Nguồn thực tế có thể bị sửa sau lưng view | Phân biệt view với snapshot/nguồn thật sự ổn định. |
| Dùng `CONCURRENT` vì muốn chạy `parallelStream()` | Đánh đồng nguồn sửa đồng thời được với khả năng xử lý song song | Chỉ khai báo nếu nguồn hỗ trợ thay đổi cấu trúc đồng thời theo hợp đồng. |
| Gọi cùng một đối tượng Spliterator từ nhiều luồng vì thấy `CONCURRENT` | Race trên con trỏ duyệt hoặc trạng thái của Spliterator | Chia nhánh bằng `trySplit`, dùng mỗi nhánh theo cách thực thi hợp lệ. |
| Xem `getExactSizeIfKnown() == -1` là nguồn rỗng | Bỏ qua dữ liệu vẫn tồn tại | `-1` nghĩa là không có kích thước chính xác được khai báo. |
| `trySplit` tạo các khoảng chồng nhau | Trùng phần tử; kết quả `sum`/`collect` sai | Đảm bảo chia không trùng, không bỏ sót; giữ encounter order khi có `ORDERED`. |
| Giả định mọi `CONCURRENT` đều có snapshot tại cùng thời điểm | Kỳ vọng sai về phần tử sẽ quan sát được | Đọc rõ chính sách weak consistency/snapshot của từng nguồn. |
| Dùng `peek` để ghi log bắt buộc rồi gọi `count` trên pipeline đã biết kích thước | `peek` có thể bị bỏ qua trong tối ưu | Không dựa vào side effect của các bước trung gian. |
| Khai báo nhiều cờ chỉ để tối ưu mà không có kiểm thử/hợp đồng | Có thể dẫn tới hành vi không được bảo đảm | Khai báo bảo thủ, kiểm thử tuần tự và song song với dữ liệu đại diện. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một Spliterator có `SIZED` có nhất thiết có `SUBSIZED` không?

**Đáp án:** Không. `SIZED` chỉ bảo đảm kích thước của Spliterator hiện tại; `SUBSIZED` còn bảo đảm tất cả các nhánh tạo ra khi chia đều `SIZED` và `SUBSIZED`.

**Câu 2.** Nguồn có 5 phần tử nhưng `getExactSizeIfKnown()` trả `-1`. Có phải nguồn rỗng?

**Đáp án:** Không. Trả `-1` nghĩa Spliterator không khai báo `SIZED`; `estimateSize()` có thể chỉ là ước lượng.

**Câu 3.** Một `Spliterator` có `IMMUTABLE` có bảo đảm mọi đối tượng phần tử là immutable object không?

**Đáp án:** Không. Cờ mô tả nguồn phần tử không bị sửa cấu trúc trong lúc duyệt, không đảm bảo trạng thái bên trong từng đối tượng là bất biến.

**Câu 4.** Vì sao nguồn `ConcurrentHashMap` có thể khai báo `CONCURRENT` mà không khai báo `SIZED`?

**Đáp án:** Nguồn hỗ trợ cập nhật đồng thời, nhưng số phần tử có thể thay đổi trong lúc duyệt nên khó bảo đảm số còn lại chính xác.

**Câu 5.** Trên dải số `[0, 8)`, một lần `trySplit` chia thành `[0, 4)` và `[4, 8)`. Mỗi nhánh báo số phần tử còn lại là bao nhiêu?

**Đáp án:** Mỗi nhánh có 4 phần tử; tổng là 8. Nếu các lần chia sau tiếp tục tạo những khoảng không giao nhau với kích thước đúng, cách triển khai có thể duy trì `SIZED | SUBSIZED`.

**Câu 6.** Đã có `CONCURRENT`, liệu hai thread có thể cùng gọi `sp.tryAdvance(...)` trên một đối tượng `sp`?

**Đáp án:** Không được suy ra như vậy. `CONCURRENT` áp dụng cho **nguồn**, không phải mặc định cho trạng thái duyệt của chính `sp`. Hãy tuân thủ hợp đồng thread-safety của implementation và ưu tiên các nhánh `trySplit` độc lập khi xử lý song song.

## Ghi nhớ

- `SIZED` khẳng định kích thước còn lại chính xác theo hợp đồng; `getExactSizeIfKnown()` trả `-1` nếu không có `SIZED`.
- `SUBSIZED` mở rộng cam kết: **mọi nhánh** được sinh ra khi chia đều có kích thước chính xác và mang `SIZED | SUBSIZED`.
- `IMMUTABLE` nói nguồn không thể thay đổi cấu trúc trong lúc duyệt, **không nói** mọi đối tượng phần tử hoặc con trỏ duyệt đều bất biến.
- `CONCURRENT` nói về khả năng sửa đổi **nguồn** đồng thời, **không** tự bảo đảm một đối tượng `Spliterator` được nhiều thread gọi đồng thời hay có snapshot nhất quán.
- Với nguồn tùy biến, khai báo đặc tính bảo thủ, thiết kế `trySplit` không trùng/không sót, xử lý nguồn thay đổi có chính sách rõ ràng và chỉ tối ưu sau khi đã giữ đúng hợp đồng.
