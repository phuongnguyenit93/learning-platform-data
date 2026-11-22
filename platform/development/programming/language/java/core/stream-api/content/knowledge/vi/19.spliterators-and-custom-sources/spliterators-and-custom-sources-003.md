# Chia nguồn bằng trySplit và ước lượng bằng estimateSize

Khi gọi `parallel()` trên một pipeline **Java Stream API**, chương trình không tự động trở nên nhanh hơn. Muốn xử lý song song hiệu quả, nguồn dữ liệu cần được **chia thành các phần công việc** vừa đủ độc lập, không mất phần tử và không xử lý trùng. Trong Java, giao diện **`Spliterator`** là một cơ chế quan trọng hỗ trợ việc duyệt và chia nguồn.

Hai phương thức cốt lõi là **`trySplit()`** và **`estimateSize()`**:

- `trySplit()` cố gắng tách một phần dữ liệu chưa duyệt thành **Spliterator mới**, để phần đó có thể được xử lý độc lập.
- `estimateSize()` cho biết **ước lượng số phần tử còn lại** trong Spliterator hiện tại; nếu biết chính xác và khai báo đúng đặc tính, con số này còn có thể giúp Stream tối ưu hóa.

Bài thuộc chương **Spliterator và nguồn tự định nghĩa** của module **JAVA_STREAM_API**. Chúng ta sẽ học hợp đồng phân chia nguồn, quan hệ với `tryAdvance()`, ý nghĩa `SIZED`/`SUBSIZED`/`ORDERED`, cách tự viết `Spliterator.OfInt` cho khoảng số, chuyển nguồn thành Stream bằng `StreamSupport`, và những lưu ý về trạng thái, bộ nhớ, thứ tự, tràn số và hiệu năng xử lý song song. Đây là nền tảng để xây custom source, hiểu các pipeline lazy và phối hợp với `filter`, `map`, `reduce`, `collect` hay các cơ chế nâng cao như Stream Gatherers.

## 1. Spliterator giải quyết vấn đề gì?

Giả sử một danh sách có tám số:

~~~text
[0, 1, 2, 3, 4, 5, 6, 7]
~~~

Khi xử lý tuần tự, ta có thể duyệt lần lượt từ trái sang phải. Nhưng muốn chia việc cho hai nhóm xử lý, cần có cách biến **một vùng chưa duyệt** thành hai vùng **không giao nhau**:

~~~text
Nguồn ban đầu:
[0, 1, 2, 3, 4, 5, 6, 7]

trySplit() có thể tạo:
  Spliterator trả về: [0, 1, 2, 3]
  Spliterator gốc:    [4, 5, 6, 7]

Một trong hai phần có thể được chia tiếp:
  [0, 1] và [2, 3]
~~~

Một Spliterator hỗ trợ **traversal** (duyệt) và, khi khả thi, **partitioning** (phân chia). Đây là lý do tên `Spliterator` gợi ý đến *split* + *iterator*.

`Iterator` thông thường có `hasNext()` và `next()`. `Spliterator` sử dụng `tryAdvance(...)`, `forEachRemaining(...)`, `trySplit()` cùng thông tin về kích thước và đặc tính nguồn. Vì thế, nó có thể cung cấp nhiều tín hiệu hữu ích cho một pipeline Stream.

### Phân biệt ba khái niệm

| Thành phần | Vai trò |
|---|---|
| `Stream` | Mô tả pipeline xử lý khai báo với các bước lazy và terminal operation |
| `Spliterator` | Cơ chế duyệt, phân chia và mô tả đặc tính của **nguồn** |
| `ForkJoinPool`/cơ chế thực thi | Tổ chức công việc song song theo các phần mà nguồn và pipeline có thể cung cấp |

Việc `trySplit()` trả về một phần dữ liệu **không đồng nghĩa** nó tự tạo thread. `Spliterator` không quyết định số luồng chạy; việc lên lịch thuộc tầng thực thi Stream.

## 2. Các phương thức chính của Spliterator

Giao diện `java.util.Spliterator<T>` có các thao tác cơ bản:

~~~java
boolean tryAdvance(Consumer<? super T> action);

void forEachRemaining(Consumer<? super T> action);

Spliterator<T> trySplit();

long estimateSize();

int characteristics();
~~~

Ngoài ra còn có:

~~~java
long getExactSizeIfKnown();

boolean hasCharacteristics(int characteristics);

Comparator<? super T> getComparator();
~~~

`getComparator()` chỉ thích hợp khi nguồn khai báo `SORTED`; nếu không, phương thức mặc định thường ném `IllegalStateException`. Với thứ tự tự nhiên, một Spliterator có đặc tính `SORTED` có thể trả `null` từ `getComparator()` để biểu thị natural ordering.

Bảng diễn giải:

| Phương thức | Câu hỏi nó trả lời |
|---|---|
| `tryAdvance(action)` | Còn phần tử kế tiếp không? Nếu có, chuyển **một phần tử** cho action và trả `true` |
| `forEachRemaining(action)` | Duyệt hết những phần tử còn lại |
| `trySplit()` | Có thể chia vùng chưa duyệt để lấy một Spliterator độc lập không? |
| `estimateSize()` | Ước lượng còn bao nhiêu phần tử? |
| `characteristics()` | Nguồn có tính chất như `ORDERED`, `SIZED`, `SUBSIZED` không? |
| `getExactSizeIfKnown()` | Trả kích thước còn lại **nếu biết chính xác**, nếu không trả `-1` |

**Lưu ý:** `tryAdvance` không chỉ “kiểm tra tồn tại” như `hasNext`, mà còn **tiêu thụ** một phần tử nếu có. `forEachRemaining` cũng tiêu thụ dữ liệu. Việc này làm thay đổi phạm vi dữ liệu *chưa duyệt* trong Spliterator.

## 3. Hợp đồng của trySplit(): phân chia không mất và không trùng

Chữ ký:

~~~java
Spliterator<T> trySplit();
~~~

`trySplit()` trả về:

- **Một Spliterator mới** chứa **một số phần tử chưa duyệt** được tách khỏi Spliterator hiện tại, nếu tách được.
- **`null`** nếu không thể hoặc không muốn chia thêm.

Sau khi phân chia thành công, phần tử thuộc Spliterator trả về **không còn nằm trong phạm vi chưa duyệt của Spliterator gốc**. Nếu duyệt cả hai phần đúng một lần, ta phải thu được **đúng tập phần tử chưa duyệt trước khi chia**, không mất và không phát lại phần tử.

### 3.1. Trường hợp nguồn có ORDERED

Khi Spliterator báo `ORDERED`, Spliterator được `trySplit()` trả về phải chứa **một tiền tố** (*prefix*) của các phần tử còn lại, còn Spliterator gốc giữ phần **hậu tố** (*suffix*).

Ví dụ hợp lệ:

~~~text
Trước split:
    [A, B, C, D, E, F]

Sau split:
    kết quả trySplit(): [A, B, C]
    Spliterator gốc:   [D, E, F]
~~~

Một cách tách thành `[A, C, E]` và `[B, D, F]` **không** thỏa ràng buộc tiền tố/hậu tố của một Spliterator `ORDERED`.

Với nguồn **không có `ORDERED`**, phần trả về không nhất thiết phải là tiền tố; nhưng vẫn phải bảo đảm sự phân chia hợp lệ, không làm mất hoặc lặp phần tử.

### 3.2. Có bắt buộc chia đôi không?

**Không.** `trySplit()` có thể tách theo kích thước bất kỳ phù hợp với nguồn; nó có thể trả `null` dù còn nhiều phần tử nếu không thể tách hiệu quả. Chia gần một nửa thường hợp lý cho **mảng hoặc khoảng chỉ số** vì:

- Hai công việc có thể có kích thước gần nhau.
- Có thể tiếp tục chia thành các nhánh nhỏ hơn.
- Tính toán ranh giới tương đối đơn giản.

Nhưng đối với `Iterator` một chiều, dữ liệu I/O hoặc bộ sinh có trạng thái, không phải nguồn nào cũng chia ngẫu nhiên được. Trong trường hợp đó, tách theo lô (*batching*) hoặc không hỗ trợ chia có thể phù hợp hơn.

### 3.3. Split sau khi đã duyệt một phần

Nếu trước đó `tryAdvance` đã tiêu thụ một phần tử, `trySplit` chỉ được chia **phần còn lại**:

~~~text
Ban đầu: [0, 1, 2, 3, 4, 5]
Đã tryAdvance lấy 0.

Còn lại: [1, 2, 3, 4, 5]
Split hợp lệ:
    phần trả về: [1, 2]
    phần gốc:    [3, 4, 5]
~~~

Phần tử `0` đã xử lý **không được xuất hiện lại** ở Spliterator nào.

## 4. estimateSize(): kích thước còn lại, không phải kích thước ban đầu

Chữ ký:

~~~java
long estimateSize();
~~~

Kết quả có kiểu `long` để mô tả số phần tử lớn hơn giới hạn `int`. Tuy nhiên, **ước lượng không luôn chính xác**: ý nghĩa phụ thuộc vào đặc tính nguồn.

- Với nguồn kích thước biết chính xác, chẳng hạn một vùng chỉ số của mảng ổn định, `estimateSize()` có thể bằng chính số phần tử còn lại.
- Với nguồn có kích thước khó xác định, giá trị có thể chỉ là một ước lượng.
- Khi không có ước lượng hữu hạn đáng tin cậy, hoặc với nguồn vô hạn, API có thể trả `Long.MAX_VALUE` để biểu diễn “không biết/không giới hạn” — **không** có nghĩa nguồn thực sự chứa đúng bấy nhiêu phần tử.

Ví dụ: nếu một Spliterator quản lý đoạn `[10, 20)`, còn mười số nguyên, thì kích thước chính xác là:

~~~text
20 - 10 = 10
~~~

Sau khi tiêu thụ số 10, phạm vi còn `[11, 20)`, kích thước giảm còn **9**. Nếu chia tại 15, phần trả về quản lý `[11, 15)` (4 phần tử), phần gốc quản lý `[15, 20)` (5 phần tử). Tổng còn 9 phần tử.

### 4.1. getExactSizeIfKnown khác estimateSize như thế nào?

~~~java
long estimate = spliterator.estimateSize();
long exact = spliterator.getExactSizeIfKnown();
~~~

Theo hợp đồng mặc định:

- Khi Spliterator báo **`SIZED`**, `getExactSizeIfKnown()` trả kích thước còn lại mà nó biết, tương ứng với `estimateSize()`.
- Khi **không có `SIZED`**, `getExactSizeIfKnown()` trả **`-1`**.

`getExactSizeIfKnown() == -1` không có nghĩa Spliterator rỗng; nó chỉ có nghĩa **không công bố kích thước chính xác**. Không dùng `estimateSize()` để cấp phát mảng đầu ra lớn nếu con số đó chỉ là ước lượng hoặc `Long.MAX_VALUE`.

### 4.2. Giá trị size thay đổi trong quá trình duyệt

Với nguồn cỡ cố định được thiết kế đúng, sau khi `tryAdvance` thành công, số phần tử còn lại giảm. Sau khi `trySplit` thành công, `estimateSize()` của đối tượng gốc phản ánh **phần nó còn quản lý**, chứ không phải kích thước trước khi chia.

Không viết Spliterator luôn trả tổng kích thước ban đầu sau khi đã tiêu thụ hoặc phân chia mà vẫn khai báo `SIZED`. Làm vậy khiến dữ liệu về kích thước mâu thuẫn và có thể ảnh hưởng đến các tối ưu hóa của Stream.

## 5. SIZED và SUBSIZED: những lời hứa phải giữ

`characteristics()` trả về tổ hợp các hằng số bit-mask từ `Spliterator`, trong đó quan trọng với chủ đề này là:

| Đặc tính | Ý nghĩa |
|---|---|
| `SIZED` | Kích thước còn lại trước khi duyệt/phân chia được xác định chính xác theo hợp đồng |
| `SUBSIZED` | Spliterator hiện tại và **các Spliterator sinh từ `trySplit`** cũng bảo đảm `SIZED` và `SUBSIZED` |
| `ORDERED` | Có encounter order; kết quả split của nguồn ordered phải là tiền tố |
| `IMMUTABLE` | Cấu trúc nguồn không bị thay đổi theo cách vi phạm đặc tính trong lúc duyệt |
| `CONCURRENT` | Nguồn được thiết kế để xử lý biến đổi đồng thời theo hợp đồng riêng của nó |
| `DISTINCT` | Không có hai phần tử khác nhau bằng nhau theo `equals` |
| `SORTED` | Các phần tử theo thứ tự được định nghĩa, gắn với `getComparator()` |
| `NONNULL` | Phần tử không phải `null` |

**Phân biệt:** `SIZED` không tự động suy ra `SUBSIZED`. Một Spliterator có thể biết chính xác kích thước ban đầu nhưng không bảo đảm mọi nhánh con đều tiếp tục biết chính xác. Nếu khai báo `SUBSIZED`, phải giữ lời hứa mạnh hơn cho **cả cây Spliterator**.

Đối với mảng bất biến về cấu trúc hoặc dãy chỉ số `[start, end)`, việc tính chính xác kích thước của mọi nửa tách thường khả thi, nên `SIZED | SUBSIZED` là lựa chọn hợp lý.

### 5.1. Không khai báo đặc tính chỉ để hy vọng chạy nhanh hơn

Khai báo `SIZED` sai có thể làm một số terminal operation như `count()` dựa vào kích thước được báo, không nhất thiết duyệt từng phần tử. Nếu số báo sai, kết quả có thể sai hoặc phát sinh vấn đề nội bộ.

Tương tự, nếu nguồn chưa được sắp xếp mà khai báo `SORTED`, một số pipeline có thể tối ưu hóa dựa trên một lời hứa không đúng. Chỉ khai báo các đặc tính mà **nguồn thực sự bảo đảm**.

## 6. Quan sát trySplit trên nguồn chuẩn của Java

Trước khi tự viết Spliterator, ta có thể quan sát hành vi ở `List`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

public class StandardSplitDemo {
    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(0, 1, 2, 3, 4, 5, 6, 7);

        Spliterator<Integer> remaining = values.spliterator();

        System.out.println(remaining.estimateSize()); // 8
        System.out.println(remaining.getExactSizeIfKnown()); // 8

        Spliterator<Integer> prefix = remaining.trySplit();

        if (prefix != null) {
            System.out.println(
                "Phần trả về: " + prefix.estimateSize()
            );
            System.out.println(
                "Phần gốc: " + remaining.estimateSize()
            );

            // Với List có ORDERED, phần trả về là tiền tố.
            System.out.println(StreamSupport.stream(prefix, false).toList());
        }

        System.out.println(StreamSupport.stream(remaining, false).toList());
    }
}
~~~

**Lưu ý về kết quả:** Java không cam kết mọi Spliterator của `List` sẽ chia **đúng một nửa**. Chẳng hạn một triển khai có thể chia 4–4, nhưng kích thước hai nhánh có thể khác hoặc `trySplit()` có thể trả `null`. Điều quan trọng là **nội dung không trùng/mất**, tiền tố đúng nếu `ORDERED`, và kích thước tuân thủ đặc tính đã công bố.

Code trên dùng `Stream.toList()` (Java 16+). Với Java 8–15, có thể thay bằng `collect(Collectors.toList())`.

## 7. Tự viết Spliterator.OfInt cho một khoảng số nguyên

Bây giờ ta tạo một nguồn tự định nghĩa cho khoảng nguyên **`[startInclusive, endExclusive)`**, tương tự ý nghĩa của `IntStream.range`. Nguồn này có:

- Hai ranh giới `current` (phần tử tiếp theo) và `fence` (điểm cuối **không bao gồm**).
- `tryAdvance` phát giá trị `current` rồi tăng con trỏ.
- `trySplit` chia phần chưa duyệt thành **nửa đầu trả về** và **nửa cuối giữ lại**.
- `estimateSize` trả chính xác `fence - current`.
- `characteristics` công bố các tính chất thực sự bảo đảm.

Ta chọn `Spliterator.OfInt` để làm việc với `int` trực tiếp, tránh boxing khi chỉ cần tính tổng và lọc số.

### 7.1. Chương trình Java hoàn chỉnh

Tạo file `RangeSpliteratorDemo.java` với nội dung dưới đây; chương trình chạy trên **Java 8+**.

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class RangeSpliteratorDemo {

    static final class RangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");

            if (current >= fence) {
                return false;
            }

            int value = current;
            current++;
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining <= 1) {
                return null;
            }

            // Tính bằng long để tránh tràn khi ranh giới int rất xa nhau.
            long middleAsLong = (long) current + remaining / 2;
            int middle = (int) middleAsLong;

            // Trả tiền tố [current, middle).
            Spliterator.OfInt prefix =
                new RangeSpliterator(current, middle);

            // Giữ hậu tố [middle, fence) trong đối tượng hiện tại.
            current = middle;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
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
        RangeSpliterator original = new RangeSpliterator(0, 10);

        Spliterator.OfInt prefix = original.trySplit();

        if (prefix == null) {
            throw new AssertionError("Khoảng này phải chia được");
        }

        System.out.println(prefix.estimateSize());    // 5
        System.out.println(original.estimateSize());  // 5

        int[] left = StreamSupport.intStream(prefix, false).toArray();
        int[] right = StreamSupport.intStream(original, false).toArray();

        System.out.println(Arrays.toString(left));
        // [0, 1, 2, 3, 4]

        System.out.println(Arrays.toString(right));
        // [5, 6, 7, 8, 9]

        // Tạo nguồn mới: hai pipeline riêng, không dùng lại Stream cũ.
        long sequential = StreamSupport.intStream(
            new RangeSpliterator(0, 1_000), false
        ).asLongStream().sum();

        long parallel = StreamSupport.intStream(
            new RangeSpliterator(0, 1_000), true
        ).asLongStream().sum();

        System.out.println(sequential); // 499500
        System.out.println(parallel);   // 499500
    }
}
~~~

Đây là **một nguồn có kích thước xác định**. Mã không triển khai `forEachRemaining` riêng vì `Spliterator.OfInt` đã cung cấp cách duyệt còn lại dựa trên `tryAdvance`; ở nguồn hiệu năng cao có thể tối ưu thêm phương thức đó, miễn vẫn giữ nguyên hợp đồng và không phát lại phần tử.

### 7.2. Vì sao dùng long khi tính trung điểm?

Phép tính ngây thơ:

~~~java
int middle = (current + fence) / 2; // Không an toàn ở biên int.
~~~

có thể tràn `int` khi `current` và `fence` cùng rất lớn, thậm chí khi mỗi ranh giới riêng lẻ vẫn hợp lệ.

Trong ví dụ, dùng:

~~~java
long remaining = (long) fence - current;
long middleAsLong = (long) current + remaining / 2;
int middle = (int) middleAsLong;
~~~

Khi `current < fence` và `remaining >= 2`, `middleAsLong` nằm **giữa hai ranh giới** và biểu diễn được trong `int`. Dùng `long` còn giúp `estimateSize` báo đúng những khoảng có hơn `Integer.MAX_VALUE` phần tử.

Ví dụ, số phần tử của `[Integer.MIN_VALUE, Integer.MAX_VALUE)` là **4.294.967.295**, vượt `int` nhưng vẫn nằm trong `long`. Không nên cấp phát một mảng chứa toàn bộ khoảng đó; ví dụ chỉ minh họa tính chính xác của kích thước và trung điểm.

### 7.3. Vì sao không khai báo SORTED?

Nguồn này phát số tăng dần, về mặt dữ liệu hoàn toàn có thứ tự sắp xếp. Tuy vậy, ví dụ cố ý **không khai báo `SORTED`**, vì muốn công bố đặc tính đó một cách đầy đủ cần tuân thủ thêm hợp đồng `getComparator()` (đối với thứ tự tự nhiên, trả `null`).

Đặc tính **`ORDERED`** chỉ nói có encounter order và `trySplit` phải trả tiền tố; nó **không tương đương** với `SORTED`. Khi triển khai nguồn tùy chỉnh, ưu tiên khai báo đúng những đặc tính đã hiểu và kiểm chứng.

## 8. Chứng minh bất biến của nguồn tự định nghĩa

Đối với `RangeSpliterator`, tại mọi thời điểm trước khi kết thúc:

~~~text
Phần tử còn lại: current, current+1, ..., fence-1
Khoảng quản lý: [current, fence)
Kích thước còn lại: fence - current
~~~

Giả sử ban đầu `current = a` và `fence = b`, với `a < b`. Sau khi chia tại `m`:

~~~text
Tiền tố được trả về: [a, m)
Hậu tố nằm trong gốc: [m, b)

[a, m) ∩ [m, b) = ∅
[a, m) ∪ [m, b) = [a, b)
~~~

Từ hai quan hệ này, ta suy ra:

1. Không có phần tử thuộc cả hai nhánh.
2. Không có phần tử nào bị bỏ sót.
3. Nhánh được trả về là tiền tố, đúng với `ORDERED`.
4. Tổng kích thước hai nhánh bằng kích thước nguồn còn lại trước khi chia.
5. Các nhánh mới vẫn có dạng khoảng nửa mở, nên tiếp tục đáp ứng `SIZED` và `SUBSIZED`.

Các bất biến trên **quan trọng hơn** việc ép mỗi nhánh có đúng nửa số phần tử khi khoảng lẻ. Với 9 phần tử, ta có thể chia 4–5: vẫn hợp lệ.

## 9. Quan sát ảnh hưởng của tryAdvance đến kích thước

Một `Spliterator` không chỉ được chia mà còn được **tiêu thụ dần**:

~~~java
RangeSpliterator remaining = new RangeSpliterator(10, 16);

System.out.println(remaining.estimateSize()); // 6

boolean hasNext = remaining.tryAdvance(
    (int value) -> System.out.println(value)
); // In 10

System.out.println(hasNext);                  // true
System.out.println(remaining.estimateSize()); // 5

Spliterator.OfInt prefix = remaining.trySplit();

System.out.println(prefix.estimateSize());    // 2
System.out.println(remaining.estimateSize()); // 3

prefix.forEachRemaining((int value) ->
    System.out.println("Prefix: " + value)
); // 11, 12

remaining.forEachRemaining((int value) ->
    System.out.println("Suffix: " + value)
); // 13, 14, 15

System.out.println(remaining.estimateSize()); // 0
~~~

Ví dụ này dùng lớp `RangeSpliterator` khai báo bên trong `RangeSpliteratorDemo` ở mục 7; khi thực hành có thể đặt đoạn code vào `main` của lớp đó.

Điều đáng chú ý:

- Sau khi lấy phần tử 10, Spliterator chỉ còn `[11, 16)`, size = 5.
- `trySplit` chia `[11, 16)` thành `[11, 13)` (2 phần tử) và `[13, 16)` (3 phần tử).
- Duyệt hết hai nhánh sẽ phát đúng các số 11–15 **một lần**.
- Khi đã hết, `tryAdvance` tiếp theo sẽ trả `false` và `estimateSize()` bằng 0.

Trong ví dụ thực tế, đừng sử dụng `Spliterator` hoặc `Stream` sau khi đã giao nó cho pipeline khác để xử lý. Các lời gọi nhằm minh họa nên được thực hiện khi bạn đang sở hữu độc quyền nguồn.

## 10. StreamSupport: đưa Spliterator thành nguồn Stream

Hai phương thức quen thuộc trong `java.util.stream.StreamSupport`:

~~~java
StreamSupport.stream(Spliterator<T> spliterator, boolean parallel)

StreamSupport.intStream(Spliterator.OfInt spliterator, boolean parallel)
~~~

Ngoài ra có `longStream` và `doubleStream` cho `OfLong`/`OfDouble`.

Tham số `parallel` cho biết Stream được tạo ở **chế độ tuần tự** (`false`) hay **song song** (`true`). Điều này không thay đổi tính đúng đắn phải có của `trySplit` hoặc `estimateSize`.

~~~java
long sum = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .filter(n -> n % 2 == 0)
    .asLongStream()
    .sum();

System.out.println(sum); // 2450
~~~

Ví dụ trên sử dụng nguồn tự định nghĩa từ mục 7, nên cần đặt cùng phạm vi lớp hoặc dùng tên đầy đủ. Các số chẵn từ 0 đến 98 có tổng `2450`.

Một chuỗi xử lý:

~~~mermaid
flowchart LR
    A["Spliterator.OfInt"] --> B["StreamSupport.intStream"]
    B --> C["filter(n % 2 == 0)"]
    C --> D["asLongStream()"]
    D --> E["sum()"]
    F["trySplit / estimateSize"] --> A
~~~

`filter`, `map`, `reduce`, `collect` và các thao tác khác vẫn nằm ở **tầng pipeline**. Việc thiết kế nguồn chỉ nên quyết định dữ liệu được phát ra, cách chia và những đặc tính mà nguồn có thể bảo đảm.

### 10.1. Không phải cứ parallel là tự động chia thành nhiều phần

Nếu `trySplit()` luôn trả `null`, framework vẫn có thể tạo Stream với `parallel = true`, nhưng **nguồn đó không hỗ trợ tách phần việc ở mức Spliterator**. Do vậy, khả năng tận dụng nhiều luồng để duyệt nguồn sẽ bị giới hạn.

Ngược lại, dù `trySplit()` có thể chia tốt, parallel vẫn không mặc nhiên nhanh hơn: còn chi phí chia việc, bộ nhớ, thao tác trung gian có trạng thái, việc gộp kết quả và tài nguyên máy.

## 11. Chia nguồn quá nhỏ hoặc quá lớn đều có chi phí

Ví dụ tự định nghĩa tách mọi khoảng có ít nhất hai phần tử. Điều này **đúng về logic**, nhưng nếu framework tiếp tục tách rất nhiều nhánh nhỏ, chi phí tạo đối tượng và điều phối có thể tăng.

Một số chiến lược:

| Chiến lược | Điểm mạnh | Điểm cần kiểm soát |
|---|---|---|
| Chia gần một nửa vùng chỉ số | Cân bằng, dễ tính size, dễ tiếp tục chia | Không biết trước chi phí xử lý từng phần tử |
| Chia theo lô một số phần tử cố định | Phù hợp nguồn tuần tự hoặc đọc theo batch | Cần xử lý lô cuối và giữ đúng ORDERED |
| Không chia khi còn ít phần tử | Tránh overhead cho việc quá nhỏ | Có thể giảm cơ hội song song hóa |
| Không hỗ trợ chia | Đơn giản với nguồn không thể phân chia | Tốc độ song song có thể bị hạn chế |

Nếu muốn giới hạn việc chia cho những đoạn rất nhỏ, một biến thể có thể viết:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = estimateSize();
    if (remaining < 1_024) {
        return null;
    }

    int middle = (int) ((long) current + remaining / 2);
    Spliterator.OfInt prefix =
        new RangeSpliterator(current, middle);
    current = middle;
    return prefix;
}
~~~

Đây là **phương án thay thế** cho `trySplit` trong lớp `RangeSpliterator`, không phải phương thức được chèn thêm bên cạnh phương thức cũ. Ngưỡng 1.024 chỉ là ví dụ; chọn ngưỡng phụ thuộc khối lượng xử lý mỗi phần tử và kết quả đo trên hệ thống thực tế.

## 12. Nguồn không biết kích thước: estimateSize không nhất thiết chính xác

Không phải mọi nguồn đều là khoảng số hoặc mảng. Một `Iterator` có thể lấy dữ liệu từng phần, không biết trước có bao nhiêu phần tử.

Java cung cấp `Spliterators.spliteratorUnknownSize`:

~~~java
import java.util.Arrays;
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;

public class UnknownSizeDemo {
    public static void main(String[] args) {
        Iterator<String> iterator =
            Arrays.asList("A", "B", "C").iterator();

        Spliterator<String> source =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );

        System.out.println(
            source.hasCharacteristics(Spliterator.SIZED)
        ); // false

        System.out.println(source.getExactSizeIfKnown()); // -1

        System.out.println(
            source.estimateSize() == Long.MAX_VALUE
        ); // true ở nguồn unknown-size mới tạo
    }
}
~~~

Mặc dù **dữ liệu mẫu** thực tế có ba phần tử, Spliterator tạo từ một Iterator không nhận bảo đảm kích thước đó theo hợp đồng. `Long.MAX_VALUE` ở đây là giá trị biểu thị **không biết số phần tử**, không phải ước lượng đáng dùng để cấp phát.

Lưu ý: một triển khai có thể chia một Iterator thành **các batch đã đọc trước**, khiến estimate của nhánh con khác với nguồn gốc. Không nên viết logic phụ thuộc vào chi tiết batch và vị trí gọi `trySplit` của một lớp thư viện.

### 12.1. Không báo SIZED và SUBSIZED cho một nguồn không thể đảm bảo

Nếu nguồn có thể thêm/xóa phần tử trong khi đang duyệt, hoặc không biết trước kích thước, việc tuyên bố `SIZED | SUBSIZED` sẽ là lời hứa sai. `Spliterators.spliteratorUnknownSize` không bảo đảm `SIZED` và `SUBSIZED` cho Spliterator gốc.

Đừng dùng kiểu đoán “còn khoảng 1000 phần tử” rồi gắn `SIZED`. Hãy trả estimate phù hợp (nếu có thể) nhưng **không khai báo `SIZED`** nếu nó không chắc chắn chính xác theo hợp đồng.

### 12.2. Các nguồn vô hạn cần điểm dừng

Một `Spliterator` quản lý bộ sinh không có giới hạn có thể trả `Long.MAX_VALUE` từ `estimateSize`. Một phép toán như `collect(toList())` trên nguồn vô hạn sẽ không thể hoàn thành nếu không có bước cắt hoặc điều kiện kết thúc phù hợp.

~~~java
// Cẩn thận: nguồn vô hạn, không thể thu toàn bộ.
// Stream.generate(() -> 1).collect(Collectors.toList());

// Giới hạn hữu hạn:
int[] firstFive = java.util.stream.IntStream
    .generate(() -> 1)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(firstFive));
// [1, 1, 1, 1, 1]
~~~

`limit` có thể giúp ngắt nguồn, nhưng chi phí và khả năng hoàn thành cũng phụ thuộc vào **các thao tác trung gian phía trước**. Một phép `sorted()` trên nguồn vô hạn có thể không hoàn thành dù phía sau có `limit(5)`.

## 13. Đặc tính ORDERED, DISTINCT, SORTED và ảnh hưởng đến pipeline

`Spliterator` không chỉ cung cấp dữ liệu: nó còn mô tả **các tính chất mà Stream có thể tin tưởng**.

- `ORDERED` nói về encounter order, không đồng nghĩa với việc dữ liệu được sắp xếp tăng dần.
- `SORTED` mạnh hơn: dữ liệu phải tuân theo quan hệ thứ tự và `getComparator` tương ứng; nó bao hàm `ORDERED`.
- `DISTINCT` nói về việc không có hai phần tử bằng nhau theo `equals`; việc các giá trị số tăng dần trong khoảng khiến đặc tính này phù hợp.
- `NONNULL` nói các giá trị không null; với Stream nguyên thủy, đây là điều tự nhiên.
- `SIZED` và `SUBSIZED` nói về số lượng phần tử, **không nói về số byte hoặc lượng bộ nhớ cấp phát**.

Nếu công bố `DISTINCT` hoặc `SORTED` sai, các thao tác như `distinct()` hoặc `sorted()` có thể tối ưu dựa trên thông tin không đúng. Sai đặc tính không chỉ làm giảm hiệu năng mà còn có thể làm **sai dữ liệu đầu ra**.

### 13.1. Đừng đánh đồng ORDERED với duyệt tuần tự

Nguồn `ORDERED` vẫn có thể được xử lý song song. Encounter order chỉ đặt ra những yêu cầu về ngữ nghĩa mà các phép toán như `forEachOrdered`, `findFirst` hoặc `limit` phải tôn trọng khi phù hợp.

Ngược lại, một nguồn không có `ORDERED` không bắt buộc phải xáo trộn đầu ra. Một lần chạy có vẻ “đúng thứ tự” không phải là bảo đảm để mã nghiệp vụ dựa vào.

## 14. Vấn đề thread-safety và quyền sở hữu phần dữ liệu

Một `Spliterator` tùy chỉnh **không cần mặc định thread-safe** để hỗ trợ parallel Stream. Mô hình thông thường là:

1. Framework sở hữu một Spliterator.
2. Framework có thể gọi `trySplit` để tạo một Spliterator mới.
3. **Mỗi nhánh** được duyệt độc lập và sở hữu trạng thái con trỏ riêng.
4. Khi các nhánh đã được giao cho tác vụ khác, không dùng cùng một Spliterator từ nhiều thread nếu nguồn không hỗ trợ rõ ràng.

Ví dụ nguồn `RangeSpliterator` có các trường `current` khác nhau giữa các nhánh và `fence` cố định. Điều này tránh việc hai thread phải cùng cập nhật một biến đếm.

**Không nên** viết `trySplit` chỉ trả lại `this`:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    // Sai: hai nhánh cùng chia sẻ đúng một trạng thái current!
    return this;
}
~~~

Nếu framework coi giá trị trả về và đối tượng gốc là hai nhánh khác nhau, cùng một đối tượng bị duyệt chồng lấn, có nguy cơ lặp, mất phần tử, race condition hoặc vòng lặp phân chia không kết thúc.

Tương tự, không tạo hai Spliterator con đều trỏ tới **cùng toàn bộ đoạn** mà không điều chỉnh ranh giới. Một split đúng phải phân vùng phần **chưa duyệt** thành các phần không giao nhau.

### 14.1. NONNULL, IMMUTABLE và CONCURRENT không thay thế nhau

`IMMUTABLE` nói **nguồn không bị biến đổi về cấu trúc** trong lúc traversal theo mô hình nguồn đó. `CONCURRENT` nói **nguồn hỗ trợ các biến đổi đồng thời** trong những điều kiện được công bố. `NONNULL` nói phần tử không null. Chúng là những khái niệm độc lập; không dùng `CONCURRENT` chỉ vì muốn chạy `parallelStream`.

Với nguồn tự định nghĩa dựa trên một mảng có thể bị thread khác sửa dữ liệu, khai báo `IMMUTABLE` tùy tiện có thể sai. Hãy cân nhắc snapshot hoặc cơ chế đồng bộ theo yêu cầu dữ liệu.

## 15. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| `trySplit` trả `this` | Hai nhánh chia sẻ trạng thái; có thể lặp/mất phần tử | Tạo Spliterator con quản lý vùng **khác** |
| Sau split, đối tượng gốc vẫn giữ toàn bộ đoạn | Phần tử lặp giữa nhánh trả về và nhánh gốc | Chuyển `current` của gốc đến trung điểm |
| Trả hậu tố cho nguồn khai báo `ORDERED` | Vi phạm quy tắc trả tiền tố | Trả `[current, middle)` và giữ `[middle, fence)` |
| `estimateSize` luôn trả kích thước ban đầu | Kích thước không phản ánh phần còn lại | Tính từ con trỏ hiện tại đến ranh giới |
| Tính `(start + end) / 2` bằng `int` | Có thể tràn số và chia sai | Dùng phép tính `long` an toàn |
| Khai báo `SIZED` trên nguồn không biết size | Framework có thể tin vào số phần tử sai | Bỏ `SIZED` nếu không chắc chắn |
| Khai báo `SUBSIZED` nhưng nhánh con không có size chính xác | Vi phạm hợp đồng cây Spliterator | Bảo đảm mọi nhánh con đủ đặc tính hoặc bỏ `SUBSIZED` |
| Giả định `trySplit` luôn chia được | Nguồn có thể trả `null` | Hỗ trợ trường hợp không chia, vẫn duyệt tuần tự |
| Bật `parallel` rồi mong có nhiều luồng | Có thể không tách được nguồn hoặc overhead quá lớn | Đo và thiết kế chiến lược split theo nguồn |
| Chia mọi phần tử thành công việc cực nhỏ | Tốn chi phí đối tượng và điều phối | Chia theo lô/ngưỡng phù hợp |
| Tự duyệt đồng thời cùng một Spliterator không thread-safe | Race condition và kết quả khó đoán | Giao mỗi nhánh cho một chủ sở hữu độc lập |
| Thu toàn bộ nguồn vô hạn | Không hoàn thành, có thể hết tài nguyên | Có giới hạn hoặc quy tắc dừng phù hợp |
| Khai báo `SORTED` cho nguồn không sorted | Pipeline có thể bỏ bước xử lý cần thiết | Chỉ công bố đặc tính đúng |
| Dựa vào `peek` rồi `count` để đếm lời gọi duyệt | Tối ưu `SIZED` có thể bỏ qua xử lý trung gian | Dùng kết quả terminal và kiểm thử bất biến |

## 16. Bài thực hành: kiểm tra phân vùng và tổng song song

**Bài toán:** hoàn thiện một Spliterator cho khoảng `[0, 20)`, rồi so sánh kết quả tuần tự và song song. Dùng lớp `RangeSpliterator` đã viết ở mục 7.

**Yêu cầu:**

1. Tạo Spliterator quản lý `[0, 20)`, kiểm tra `estimateSize() == 20`.
2. Gọi `trySplit()` một lần, lấy phần tiền tố và hậu tố.
3. Duyệt mỗi nhánh bằng `StreamSupport.intStream(..., false).toArray()`.
4. Kiểm tra tổng số phần tử bằng 20, không có phần tử trùng, và thứ tự của hai đoạn liên tiếp tạo thành `0..19`.
5. Dùng một **Spliterator mới** tạo `IntStream` song song để tính tổng, so với kết quả tuần tự.
6. Đổi `trySplit` theo ngưỡng và quan sát rằng **kết quả đúng không đổi**, dù mức độ phân chia có thể khác.

### Lời giải tham khảo (đặt trong main của RangeSpliteratorDemo)

~~~java
RangeSpliterator original = new RangeSpliterator(0, 20);
System.out.println(original.estimateSize()); // 20

Spliterator.OfInt firstHalf = original.trySplit();
if (firstHalf == null) {
    throw new IllegalStateException("Không chia được");
}

int[] left = StreamSupport.intStream(firstHalf, false).toArray();
int[] right = StreamSupport.intStream(original, false).toArray();

int[] joined = new int[left.length + right.length];
System.arraycopy(left, 0, joined, 0, left.length);
System.arraycopy(right, 0, joined, left.length, right.length);

int[] expected = java.util.stream.IntStream.range(0, 20).toArray();

System.out.println(Arrays.equals(joined, expected)); // true

long serialSum = StreamSupport.intStream(
    new RangeSpliterator(0, 20), false
).asLongStream().sum();

long parallelSum = StreamSupport.intStream(
    new RangeSpliterator(0, 20), true
).asLongStream().sum();

System.out.println(serialSum);   // 190
System.out.println(parallelSum); // 190
~~~

Vì nguồn của chúng ta là `ORDERED`, kết hợp tiền tố trước và hậu tố sau tạo đúng dãy `0..19`. Nếu vô tình đảo phần, trùng phần tử hoặc không cập nhật `current` của nguồn gốc sau split, phép `Arrays.equals(joined, expected)` sẽ cho `false`.

**Lưu ý về kiểm thử `count()`:** đối với nguồn báo `SIZED`, terminal `count()` có thể dùng trực tiếp kích thước khai báo và không buộc duyệt các phần tử. Do đó, muốn kiểm thử **hành vi `tryAdvance` và `trySplit`**, nên thực sự thu hoặc tính toán dữ liệu như `toArray()`/`sum()`, rồi so sánh với kết quả mong đợi. Đừng chỉ kiểm tra `count() == 20` để kết luận nguồn tùy chỉnh đã phát đúng 20 phần tử.

### Câu hỏi tự kiểm tra

1. `trySplit()` trả gì khi không thể chia tiếp? — **`null`**.
2. Với Spliterator có `ORDERED`, phần được trả về sau split là tiền tố hay hậu tố? — **Tiền tố**.
3. `estimateSize()` trả kiểu gì? — **`long`**.
4. `Long.MAX_VALUE` từ `estimateSize` có luôn nghĩa nguồn có đúng `Long.MAX_VALUE` phần tử không? — **Không**, có thể là kích thước chưa biết hoặc nguồn vô hạn.
5. `SIZED` có tự động bảo đảm `SUBSIZED` không? — **Không**.
6. `SUBSIZED` yêu cầu gì? — **Spliterator hiện tại và các nhánh sau split có kích thước chính xác, tiếp tục đáp ứng SIZED/SUBSIZED**.
7. Sau khi Spliterator của `[0, 10)` đã phát số 0, estimateSize còn bao nhiêu? — **9**.
8. Vì sao phải tính trung điểm bằng `long` trong ví dụ? — **Tránh tràn `int` khi tính ranh giới**.
9. Tạo `StreamSupport.intStream(spliterator, true)` có tự tạo thread ngay không? — **Không**, nó tạo Stream ở chế độ song song; thực thi xảy ra khi pipeline chạy.
10. Nếu `trySplit()` luôn trả null thì `parallel = true` có đảm bảo xử lý nguồn bằng nhiều tác vụ độc lập không? — **Không**.
11. Khi nào nên bỏ `SIZED`? — **Khi không thể cam kết số phần tử còn lại chính xác**.
12. Có nên dùng cùng một Spliterator mutable trên hai thread không? — **Không**, trừ khi thiết kế và hợp đồng nguồn cho phép rõ ràng.

## 17. Ghi nhớ trước khi thiết kế nguồn tùy chỉnh nâng cao

**`trySplit()`** tách phần tử **chưa duyệt** thành hai vùng độc lập; với nguồn `ORDERED`, phần được trả về là **tiền tố**. **`estimateSize()`** mô tả số phần tử còn lại: có thể là số chính xác khi nguồn khai báo `SIZED`, hoặc là một ước lượng/`Long.MAX_VALUE` khi không biết rõ. **`SUBSIZED`** là cam kết mạnh hơn: các Spliterator con cũng giữ được kích thước chính xác.

Khi tự viết nguồn, hãy bảo đảm các bất biến **không mất/không trùng phần tử**, **không chia sẻ con trỏ giữa các nhánh**, **kích thước cập nhật đúng sau duyệt và split**, **đặc tính không khai báo sai**, và **khả năng dừng phù hợp với terminal operation**. Đừng dùng `parallel` như một nút tăng tốc mặc định: thuật toán chia, chi phí mỗi phần tử, kết hợp kết quả và thứ tự cần được đo lường.

Hiểu đúng `trySplit` và `estimateSize` giúp bạn lý giải vì sao một số nguồn Stream chia việc rất tốt, trong khi các nguồn dựa trên Iterator, I/O hoặc bộ sinh có trạng thái lại khó song song hóa. Đây là cơ sở để đi xa hơn với custom `Spliterator`, collector, pipeline lazy, xử lý song song và Stream Gatherers một cách chính xác và tiết kiệm tài nguyên.
