# Tạo nguồn Stream tùy biến với Spliterator trong Java 8

## 1. Khi nào cần một Spliterator tùy biến?

Stream API thường lấy dữ liệu từ Collection, mảng hoặc factory có sẵn:

~~~java
List<Order> orders = loadOrders();

long total = orders.stream()
    .filter(Order::isPaid)
    .count();
~~~

Nhưng không phải nguồn dữ liệu nào cũng là Collection. Dữ liệu có thể đến từ một vùng chỉ số trong mảng hoặc bộ nhớ, một cursor đọc dữ liệu theo từng phần, một cấu trúc cây hoặc đồ thị, một bộ sinh giá trị, một iterator do thư viện khác cung cấp, hoặc một nguồn dữ liệu nội bộ cần được chia thành các phần độc lập.

Trong những trường hợp đó, có thể tạo một Stream từ nguồn tùy biến bằng Spliterator và StreamSupport.

Spliterator mô tả cách **duyệt** và **chia nhỏ** nguồn dữ liệu. Nó cho phép Stream lấy từng phần tử, xử lý toàn bộ phần còn lại hoặc tách nguồn thành các phần nhỏ hơn để xử lý song song. Đây là điểm khác biệt chính so với Iterator: Spliterator có giao thức trySplit() để phân hoạch dữ liệu.

Bài Knowledge **“Tạo nguồn Stream tùy biến với Spliterator”** thuộc nhóm **Thực hành**, module **Java 8**. Bài đi từ hợp đồng của Spliterator đến cách tạo Stream bằng StreamSupport, xây dựng Spliterator có kích thước chính xác, chia phần tử cân bằng, khai báo characteristics, dùng primitive specialization, chuyển Iterator thành nguồn Stream, xử lý nguồn mutable bằng late binding và kiểm thử tính đúng đắn của cả sequential lẫn parallel stream.

**Mục tiêu:** có thể tự tạo một nguồn Stream khi JDK chưa cung cấp adapter phù hợp, mô tả đúng đặc tính dữ liệu và chia nguồn an toàn để Stream có thể xử lý song song khi có lợi.

## 2. Spliterator và StreamSupport phối hợp với nhau như thế nào?

Một pipeline Stream có ba phần:

1. **Source:** nơi cung cấp phần tử.
2. **Intermediate operations:** các phép biến đổi như filter, map, distinct hoặc sorted.
3. **Terminal operation:** thao tác bắt đầu duyệt và tạo kết quả như collect, count, sum hoặc forEach.

Spliterator là giao diện mà Stream dùng để lấy phần tử từ source. StreamSupport là utility cấp thấp để tạo Stream từ một Spliterator hoặc từ Supplier cung cấp Spliterator.

Luồng cơ bản:

~~~text
Nguồn dữ liệu tùy biến
        |
        v
   Spliterator
   |          |
   |          +---- trySplit() -> Spliterator con
   |
   +---- tryAdvance() / forEachRemaining()
        |
        v
 StreamSupport.stream(...)
        |
        v
 filter / map / reduce / collect
        |
        v
 terminal operation
        |
        v
 kết quả
~~~

Tạo Stream tổng quát:

~~~java
Spliterator<Order> spliterator = createOrderSpliterator();

Stream<Order> stream =
    StreamSupport.stream(spliterator, false);
~~~

Tham số boolean thứ hai quyết định Stream là sequential hay parallel:

~~~java
Stream<Order> sequential =
    StreamSupport.stream(createOrderSpliterator(), false);

Stream<Order> parallel =
    StreamSupport.stream(createOrderSpliterator(), true);
~~~

Với dữ liệu primitive, dùng factory chuyên biệt:

~~~java
IntStream values =
    StreamSupport.intStream(createIntSpliterator(), false);

LongStream ids =
    StreamSupport.longStream(createLongSpliterator(), true);

DoubleStream measurements =
    StreamSupport.doubleStream(createDoubleSpliterator(), false);
~~~

Spliterator mô tả cách duyệt và chia nguồn; nó không phải Executor và không quyết định chính sách thread của ứng dụng. Các factory StreamSupport trong Java 8 nhận tham số sequential/parallel, không có tham số Executor. Khi cần kiểm soát partition, thiết kế trySplit(); khi cần kiểm soát execution resource, đó là một quyết định riêng của hệ thống chạy Stream.

## 3. Bốn phương thức cốt lõi

Một Spliterator tùy biến thường tập trung vào bốn phương thức:

| Phương thức | Trách nhiệm |
| --- | --- |
| tryAdvance(action) | Lấy và chuyển đúng một phần tử cho action; trả true nếu có phần tử |
| forEachRemaining(action) | Xử lý tuần tự mọi phần tử còn lại |
| trySplit() | Chia phần dữ liệu còn lại và trả về một Spliterator con, hoặc null nếu không chia được |
| estimateSize() | Ước lượng số phần tử còn lại |

Ngoài ra, characteristics() mô tả những thuộc tính mà Stream có thể dùng để chọn cách xử lý phù hợp.

### tryAdvance()

tryAdvance() thực hiện một bước duyệt:

~~~java
public boolean tryAdvance(Consumer<? super T> action) {
    Objects.requireNonNull(action, "action");

    if (!hasNextElement()) {
        return false;
    }

    T value = nextElement();
    action.accept(value);
    return true;
}
~~~

Hợp đồng quan trọng:

- Trả true khi lúc bắt đầu lời gọi còn một phần tử và action được gọi với phần tử đó.
- Trả false khi không còn phần tử.
- Phần tử đã trả ra không được trả lại lần nữa trong cùng quá trình duyệt.
- Nếu action ném exception, exception được truyền lại cho caller.

Đối với Spliterator có encounter order, phần tử được trả theo đúng thứ tự đó.

### forEachRemaining()

forEachRemaining() xử lý tất cả phần tử còn lại trong thread hiện tại:

~~~java
public void forEachRemaining(Consumer<? super T> action) {
    Objects.requireNonNull(action, "action");

    while (tryAdvance(action)) {
        // tryAdvance đã chuyển phần tử cho action.
    }
}
~~~

Interface có implementation mặc định dựa trên tryAdvance(). Có thể override nếu nguồn có cách duyệt hàng loạt hiệu quả hơn, chẳng hạn copy một đoạn mảng hoặc đọc liên tục từ buffer.

Không gọi forEachRemaining() rồi tiếp tục kỳ vọng Spliterator còn nguyên dữ liệu: thao tác này tiêu thụ toàn bộ phần còn lại.

### trySplit()

trySplit() là phần quan trọng nhất nếu muốn hỗ trợ parallel stream.

Khi có thể chia, phương thức trả về một Spliterator con mô tả một phần dữ liệu; Spliterator hiện tại tiếp tục quản lý phần còn lại. Hai vùng phải không chồng lấn và không bỏ sót phần tử.

Nếu có ORDERED, Spliterator được trả về phải chứa một **strict prefix** của encounter order. Ví dụ nguồn [1, 2, 3, 4, 5, 6, 7, 8] có thể chia thành:

~~~text
Spliterator con: [1, 2, 3, 4]
Spliterator gốc: [5, 6, 7, 8]
~~~

Chia cân bằng thường giúp parallel processing hiệu quả hơn. Một lần chia không nhất thiết phải đúng một nửa, nhưng chênh lệch lớn hoặc thuật toán chia tốn nhiều thời gian có thể làm mất lợi ích song song.

Nếu không thể chia thêm, trả null. Với nguồn hữu hạn, việc chia lặp lại cuối cùng phải dừng.

### estimateSize()

estimateSize() trả số phần tử còn lại hoặc một ước lượng hữu ích. Nếu nguồn có kích thước chính xác, hãy báo SIZED và trả số còn lại chính xác.

Nếu kích thước không biết, có thể trả Long.MAX_VALUE. Khi Spliterator báo SIZED, estimateSize() phải phản ánh đúng số phần tử còn lại theo hợp đồng.

Sau một lần split, tổng kích thước hai phần phải phù hợp với kích thước trước khi chia. Nếu có SUBSIZED, cả hai phần và mọi phần được chia tiếp đều phải có kích thước chính xác.

## 4. Characteristics: chỉ khai báo điều mình bảo đảm

characteristics() trả về tập bit flags mô tả nguồn. Các flags phổ biến:

| Flag | Ý nghĩa | Chỉ khai báo khi |
| --- | --- | --- |
| ORDERED | Có encounter order xác định | Thứ tự phần tử có ý nghĩa và được bảo đảm |
| DISTINCT | Không có phần tử trùng nhau | Mỗi giá trị chỉ xuất hiện một lần |
| SORTED | Phần tử được sắp theo thứ tự xác định | Nguồn thật sự được sắp xếp; getComparator() phản ánh đúng |
| SIZED | Biết chính xác số phần tử còn lại | estimateSize() luôn chính xác |
| NONNULL | Không có phần tử null | Nguồn bảo đảm mọi phần tử khác null |
| IMMUTABLE | Cấu trúc nguồn không thể bị thay đổi | Không thể thêm/xóa phần tử trong khi duyệt |
| CONCURRENT | Nguồn hỗ trợ cập nhật đồng thời theo hợp đồng | Nguồn có semantics concurrency rõ ràng |
| SUBSIZED | Mọi Spliterator con đều SIZED và SUBSIZED | trySplit() luôn bảo toàn kích thước chính xác |

Có thể ghép nhiều flags bằng phép OR:

~~~java
return ORDERED | DISTINCT | SIZED | NONNULL | IMMUTABLE | SUBSIZED;
~~~

**Khai báo sai characteristics nguy hiểm hơn khai báo thiếu.** Stream có thể dùng flags để tối ưu pipeline. Nếu nói SIZED nhưng estimate sai, DISTINCT nhưng có duplicate, hoặc IMMUTABLE trong khi nguồn vẫn bị sửa, kết quả có thể sai hoặc hành vi không còn được bảo đảm.

### ORDERED và SORTED không giống nhau

ORDERED chỉ nói thứ tự gặp phần tử được xác định. Một danh sách có thứ tự chèn là ORDERED dù chưa được sắp theo giá trị.

SORTED có nghĩa phần tử tuân theo thứ tự sort xác định. Nếu dùng thứ tự tự nhiên, getComparator() phải trả null. Nếu dùng comparator riêng, trả về đúng comparator đó. Nếu không báo SORTED, implementation mặc định của getComparator() ném IllegalStateException.

### SIZED và SUBSIZED

- SIZED: kích thước chính xác của phần còn lại đã biết.
- SUBSIZED: mọi Spliterator được tạo bởi trySplit(), kể cả chia tiếp nhiều lần, đều có SIZED và SUBSIZED.

Một nguồn có kích thước chính xác nhưng chia ra các phần mà kích thước không thể tính chính xác có thể báo SIZED mà không báo SUBSIZED.

### IMMUTABLE và CONCURRENT

IMMUTABLE nói cấu trúc nguồn không bị thay đổi trong khi duyệt. CONCURRENT nói nguồn có thể chịu được cập nhật đồng thời theo semantics của chính nó.

Không đánh dấu một ArrayList tùy biến là CONCURRENT chỉ vì nhiều thread cùng đọc nó. Đọc đồng thời và cập nhật đồng thời là hai điều khác nhau. Nếu nguồn mutable không phải concurrent, cần chính sách binding và phát hiện structural interference rõ ràng.

## 5. Thiết kế một Spliterator có thể chia hiệu quả

Với nguồn dữ liệu có thể đánh số phần tử, một thiết kế đơn giản là giữ hai mốc:

- current: vị trí phần tử tiếp theo;
- fence: vị trí kết thúc, không bao gồm fence.

Ví dụ nguồn [start, end):

~~~text
current                         fence
   |                               |
   v                               v
   [  phần tử còn lại, phần tử cuối  )
~~~

tryAdvance() lấy current rồi tăng current. trySplit() tính midpoint, tạo Spliterator con cho [current, midpoint), sau đó chuyển current của Spliterator gốc thành midpoint.

~~~text
Trước khi chia:
[ current ------------------------- fence )

Sau khi chia:
[ current -------- middle ) [ middle -------- fence )
  Spliterator con                Spliterator gốc
~~~

Đây là cách phù hợp với mảng, vùng chỉ số, dãy số và nguồn có thể phân hoạch theo key/range.

### Những nguyên tắc cần giữ

1. Không trả cùng một phần tử cho cả hai nhánh.
2. Không bỏ sót phần tử tại ranh giới split.
3. Nếu ORDERED, phần con được trả về là prefix.
4. trySplit() nên rẻ và không phải duyệt toàn bộ nguồn mới chia được.
5. estimateSize() giảm đúng sau mỗi lần chia.
6. Chia lặp lại phải kết thúc khi phần còn lại quá nhỏ.
7. Mỗi Spliterator chỉ được một thread sử dụng tại một thời điểm.
8. Không chia sẻ cursor mutable giữa các Spliterator con nếu không có cơ chế phân vùng rõ ràng.

## 6. Ví dụ 1 — xây dựng IntRangeSpliterator hoàn chỉnh

Tệp **IntRangeSpliteratorDemo.java** tạo nguồn số nguyên trong khoảng [startInclusive, endExclusive). Ví dụ dùng Spliterator.OfInt và IntStream để tránh boxing Integer khi duyệt dữ liệu primitive.

Một chi tiết đáng chú ý: cursor và fence dùng long. Nhờ vậy, có thể biểu diễn cả khoảng int đầy đủ từ Integer.MIN_VALUE đến Integer.MAX_VALUE bằng fence exclusive là Integer.MAX_VALUE + 1 mà không tràn số.

~~~java
import java.util.*;
import java.util.stream.*;
import java.util.function.IntConsumer;

public class IntRangeSpliteratorDemo {
    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private long current;
        private final long fence;

        IntRangeSpliterator(long startInclusive, long endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            if (startInclusive < Integer.MIN_VALUE
                    || endExclusive > (long) Integer.MAX_VALUE + 1L) {
                throw new IllegalArgumentException("range outside int domain");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        public OfInt trySplit() {
            long remaining = fence - current;
            if (remaining <= 1L) return null;
            long middle = current + remaining / 2L;
            IntRangeSpliterator prefix =
                new IntRangeSpliterator(current, middle);
            current = middle;
            return prefix;
        }

        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (current >= fence) return false;
            action.accept((int) current++);
            return true;
        }

        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            while (current < fence) {
                action.accept((int) current++);
            }
        }

        public long estimateSize() {
            return fence - current;
        }

        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED
                | NONNULL | IMMUTABLE | SUBSIZED;
        }

        public Comparator<? super Integer> getComparator() {
            return null;
        }
    }

    public static void main(String[] args) {
        IntRangeSpliterator root = new IntRangeSpliterator(1, 11);
        long initial = root.estimateSize();
        Spliterator.OfInt prefix = root.trySplit();
        long prefixSize = prefix.estimateSize();
        long remainderSize = root.estimateSize();

        List<Integer> splitValues = new ArrayList<Integer>();
        prefix.forEachRemaining((int value) -> splitValues.add(value));
        root.forEachRemaining((int value) -> splitValues.add(value));

        int sequentialSum = StreamSupport
            .intStream(new IntRangeSpliterator(1, 11), false)
            .sum();
        int parallelSum = StreamSupport
            .intStream(new IntRangeSpliterator(1, 11), true)
            .sum();
        List<Integer> parallelOrder = StreamSupport
            .intStream(new IntRangeSpliterator(1, 6), true)
            .boxed()
            .collect(Collectors.toList());

        if (initial != 10L) throw new AssertionError("initial size");
        if (prefixSize != 5L) throw new AssertionError("prefix size");
        if (remainderSize != 5L) throw new AssertionError("remaining size");
        if (!splitValues.equals(Arrays.asList(
                1, 2, 3, 4, 5, 6, 7, 8, 9, 10))) {
            throw new AssertionError("split coverage/order: " + splitValues);
        }
        if (sequentialSum != 55 || parallelSum != 55) {
            throw new AssertionError("stream sum");
        }
        if (!parallelOrder.equals(Arrays.asList(1, 2, 3, 4, 5))) {
            throw new AssertionError("parallel encounter order");
        }

        IntRangeSpliterator fullIntDomain =
            new IntRangeSpliterator(
                Integer.MIN_VALUE, (long) Integer.MAX_VALUE + 1L);
        long fullSize = fullIntDomain.estimateSize();
        Spliterator.OfInt fullPrefix = fullIntDomain.trySplit();
        long splitTotal =
            fullPrefix.estimateSize() + fullIntDomain.estimateSize();
        if (fullSize != 4294967296L || splitTotal != fullSize) {
            throw new AssertionError("long range accounting");
        }

        System.out.println("initialEstimate=" + initial);
        System.out.println("prefixEstimate=" + prefixSize);
        System.out.println("remainingEstimate=" + remainderSize);
        System.out.println("splitEncounterOrder=" + splitValues);
        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("parallelEncounterOrder=" + parallelOrder);
        System.out.println("fullIntDomainSize=" + fullSize);
        System.out.println("splitSizesPreserveTotal="
            + (splitTotal == fullSize));
        System.out.println("sortedComparatorIsNatural="
            + (new IntRangeSpliterator(1, 2).getComparator() == null));
        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy với JDK 8:

~~~bash
javac -encoding UTF-8 IntRangeSpliteratorDemo.java
java IntRangeSpliteratorDemo
~~~

Hoặc dùng JDK mới để kiểm tra source/API tương thích Java 8:

~~~bash
javac --release 8 -encoding UTF-8 IntRangeSpliteratorDemo.java
java IntRangeSpliteratorDemo
~~~

**Stdout đã biên dịch và chạy kiểm chứng:**

~~~text
initialEstimate=10
prefixEstimate=5
remainingEstimate=5
splitEncounterOrder=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
sequentialSum=55
parallelSum=55
parallelEncounterOrder=[1, 2, 3, 4, 5]
fullIntDomainSize=4294967296
splitSizesPreserveTotal=true
sortedComparatorIsNatural=true
PASS
~~~

### Vì sao implementation này đúng?

- Khoảng dữ liệu dùng fence exclusive, nên mỗi phần tử có đúng một vị trí.
- tryAdvance() tăng current đúng một lần sau khi lấy phần tử.
- trySplit() trả prefix từ current đến midpoint, rồi cập nhật current sang midpoint.
- estimateSize() bằng fence - current, luôn chính xác.
- Mỗi phần con tiếp tục có cùng quy tắc chia và kích thước chính xác.
- Dãy số tăng dần, không trùng, không null, không phụ thuộc collection mutable.
- SORTED dùng thứ tự tự nhiên nên getComparator() trả null.
- Primitive IntConsumer giúp tránh boxing trong quá trình duyệt số nguyên.

Ví dụ cũng kiểm tra cả khoảng int đầy đủ. Tổng số giá trị là 4.294.967.296, lớn hơn giới hạn int; vì vậy cursor và phép tính kích thước phải dùng long.

## 7. Tạo Stream tổng quát từ Iterator có sẵn

Nếu nguồn đã có Iterator và không cần thuật toán chia tùy biến, không nhất thiết phải tự viết class Spliterator. JDK cung cấp adapter trong Spliterators.

### Kích thước chưa biết

Dùng spliteratorUnknownSize():

~~~java
Iterator<String> iterator =
    Arrays.asList("alpha", "beta", "gamma").iterator();

Spliterator<String> spliterator =
    Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
    );

Stream<String> stream =
    StreamSupport.stream(spliterator, false);
~~~

Adapter này không báo SIZED vì số phần tử ban đầu không được cung cấp. estimateSize() trả Long.MAX_VALUE khi kích thước không biết. Nó có thể hỗ trợ chia ở mức giới hạn, nhưng thường không có phân hoạch cân bằng tốt như nguồn có chỉ số hoặc kích thước rõ ràng.

### Kích thước đã biết chính xác

Nếu biết chính xác số phần tử còn lại, có thể dùng:

~~~java
Spliterator<String> spliterator =
    Spliterators.spliterator(
        iterator,
        exactRemainingCount,
        Spliterator.ORDERED | Spliterator.NONNULL
    );
~~~

Giá trị exactRemainingCount phải đúng với số phần tử mà iterator thực sự còn trả ra. Nếu khai báo sai kích thước, hành vi duyệt và split không còn được bảo đảm.

### Ví dụ 2 — adapter cho iterator không biết kích thước

Tệp **UnknownSizeIteratorDemo.java** chuyển iterator thành Stream tuần tự, đồng thời xác minh estimateSize() và kết quả.

~~~java
import java.util.*;
import java.util.stream.*;

public class UnknownSizeIteratorDemo {
    public static void main(String[] args) {
        Iterator<String> iterator =
            Arrays.asList("alpha", "beta", "gamma").iterator();
        Spliterator<String> spliterator =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL);
        long estimateBefore = spliterator.estimateSize();

        List<String> result = StreamSupport
            .stream(spliterator, false)
            .map(value -> value.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        if (estimateBefore != Long.MAX_VALUE) {
            throw new AssertionError("unknown size estimate");
        }
        if (!result.equals(Arrays.asList("ALPHA", "BETA", "GAMMA"))) {
            throw new AssertionError("result: " + result);
        }
        System.out.println("estimateBefore=" + estimateBefore);
        System.out.println("result=" + result);
        System.out.println("PASS");
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 UnknownSizeIteratorDemo.java
java UnknownSizeIteratorDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
estimateBefore=9223372036854775807
result=[ALPHA, BETA, GAMMA]
PASS
~~~

Nếu nguồn thực tế là một Collection, ưu tiên spliterator() của Collection hoặc Spliterators.spliterator(collection, characteristics). JDK đã biết cấu trúc và chính sách duyệt của các collection chuẩn; tự bọc iterator có thể làm mất thông tin sizing hoặc split hiệu quả mà nguồn gốc đã có.

## 8. Nguồn mutable và late binding

Với nguồn mutable như ArrayList, có một vấn đề: nếu lấy Spliterator quá sớm, nguồn có thể thay đổi trước lúc Stream bắt đầu duyệt.

Một cách giảm cửa sổ interference là dùng overload StreamSupport nhận Supplier:

~~~java
Stream<T> stream = StreamSupport.stream(
    () -> source.spliterator(),
    characteristics,
    false
);
~~~

Supplier chỉ tạo Spliterator khi terminal operation bắt đầu traversal. Điều này cho phép các thay đổi được thực hiện **trước khi traversal bắt đầu** được phản ánh trong nguồn.

Đặc tính truyền vào StreamSupport phải tương ứng với characteristics của Spliterator mà Supplier trả về. Không khai báo thêm flag mà nguồn không bảo đảm.

Late binding không cấp quyền sửa nguồn trong lúc Stream đang chạy. Khi terminal operation đã bắt đầu, không được structurally modify một nguồn không hỗ trợ concurrent modification. Tùy implementation, việc đó có thể gây ConcurrentModificationException hoặc hành vi không xác định.

### Ví dụ 3 — Supplier tạo Spliterator khi traversal bắt đầu

Tệp **LateBindingStreamDemo.java** tạo Stream trước, thêm một phần tử vào ArrayList, rồi mới chạy terminal operation. Supplier lấy Spliterator sau khi nguồn đã được cập nhật.

~~~java
import java.util.*;
import java.util.stream.*;

public class LateBindingStreamDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<String>();
        source.add("alpha");
        int characteristics = Spliterator.ORDERED
            | Spliterator.SIZED
            | Spliterator.SUBSIZED;

        Stream<String> stream = StreamSupport.stream(
            () -> source.spliterator(),
            characteristics,
            false);

        source.add("beta");
        List<String> result = stream.collect(Collectors.toList());

        if (!result.equals(Arrays.asList("alpha", "beta"))) {
            throw new AssertionError("late-bound result: " + result);
        }
        System.out.println("result=" + result);
        System.out.println("lateBindingObserved=true");
        System.out.println("PASS");
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 LateBindingStreamDemo.java
java LateBindingStreamDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
result=[alpha, beta]
lateBindingObserved=true
PASS
~~~

ArrayList.spliterator() cung cấp ORDERED, SIZED và SUBSIZED; nó là late-binding và fail-fast. Ví dụ chỉ sửa danh sách trước khi terminal operation bắt đầu. Không thêm/xóa phần tử trong lúc collect đang chạy.

## 9. Khi nào dùng Spliterators.AbstractSpliterator?

Nếu nguồn không dễ chia cân bằng hoặc bạn chỉ muốn cung cấp logic tryAdvance(), có thể kế thừa Spliterators.AbstractSpliterator<T>.

Ví dụ minh họa:

~~~java
Iterator<String> iterator = obtainIterator();

Spliterator<String> spliterator =
    new Spliterators.AbstractSpliterator<String>(
        Long.MAX_VALUE,
        Spliterator.ORDERED | Spliterator.NONNULL) {

        @Override
        public boolean tryAdvance(
                Consumer<? super String> action) {
            Objects.requireNonNull(action, "action");

            if (!iterator.hasNext()) {
                return false;
            }

            action.accept(iterator.next());
            return true;
        }
    };
~~~

AbstractSpliterator đã cung cấp một implementation trySplit() cho phép một mức parallelism giới hạn. Đây là điểm khởi đầu hữu ích khi việc chia nguồn thủ công khó thực hiện.

Tuy nhiên, implementation mặc định không thay thế một thuật toán chia theo cấu trúc nguồn. Nếu nguồn có thể chia chính xác theo index, range hoặc partition key, một Spliterator chuyên biệt với trySplit() cân bằng thường dễ dự đoán và có hiệu năng tốt hơn.

### Chọn cách triển khai nào?

| Nguồn | Cách ưu tiên |
| --- | --- |
| Collection chuẩn | Dùng source.spliterator() |
| Mảng | Dùng Arrays.spliterator() |
| Iterator, không biết size | Spliterators.spliteratorUnknownSize() |
| Iterator, biết chính xác size | Spliterators.spliterator(iterator, size, flags) |
| Chỉ cần viết tryAdvance, split khó | Spliterators.AbstractSpliterator |
| Nguồn có index/range rõ ràng | Spliterator tùy biến với split theo midpoint |
| Primitive int/long/double | Spliterator.OfInt/OfLong/OfDouble |
| Nguồn mutable cần lấy dữ liệu muộn | StreamSupport.stream(Supplier, flags, parallel) |

Không tự triển khai Spliterator nếu adapter có sẵn đã mô tả đúng nguồn. Tự viết chỉ có ích khi bạn cần kiểm soát cách duyệt, metadata, late binding hoặc cách chia dữ liệu.

## 10. Parallel stream: Spliterator tốt chưa đủ

Parallel stream có thể chia công việc thành nhiều nhánh, nhưng tốc độ phụ thuộc nhiều yếu tố:

- trySplit() có tạo các phần cân bằng không?
- Việc chia có rẻ hơn chi phí xử lý không?
- Mỗi phần tử có đủ công việc để bù overhead scheduling không?
- Nguồn có phải chờ I/O hoặc lock không?
- Các operation có stateless và non-interfering không?
- Reduction có associative để ghép kết quả theo nhóm khác nhau không?

Một Spliterator không chia được vẫn có thể dùng với Stream tuần tự. Khi tạo parallel stream mà trySplit() liên tục trả null, nguồn không có nhiều cơ hội xử lý song song.

### Phân hoạch cân bằng

Nếu có 1.000.000 phần tử, split thành hai phần 500.000 thường thuận lợi hơn chia thành 999.999 và 1 phần. Nếu mỗi lần split phải quét toàn bộ dữ liệu để tìm điểm chia, chi phí phân hoạch có thể lớn hơn lợi ích xử lý song song.

Nguồn có thể chia bằng index thường rất phù hợp:

- mảng: chia khoảng chỉ số;
- range: chia midpoint;
- cây cân bằng: chia theo subtree;
- partitioned data: chia theo partition độc lập.

Nguồn dạng stream một chiều hoặc socket có thể không chia được. Khi đó parallel stream không tự biến I/O tuần tự thành I/O song song.

### Encounter order và terminal operation

Nếu Spliterator báo ORDERED, Stream có thể giữ encounter order cho các operation yêu cầu thứ tự. Nhưng forEach() trên parallel stream không bảo đảm thứ tự thực thi.

Nếu cần xuất kết quả theo thứ tự nguồn, dùng forEachOrdered() hoặc terminal operation/collector có semantics giữ encounter order. Trong ví dụ, collect(Collectors.toList()) trên ordered stream cho danh sách theo thứ tự encounter.

### Reduction phải phù hợp với parallel execution

Các phép cộng, min, max và kết hợp dữ liệu có tính associative thường dễ chia nhỏ rồi ghép kết quả. Một accumulator có side effect hoặc phép gộp phụ thuộc thứ tự có thể cho kết quả khác khi chạy song song.

Không dùng shared mutable ArrayList trong parallel forEach nếu không có cơ chế đồng bộ thích hợp. Ưu tiên collector được thiết kế cho reduction, hoặc tạo accumulator riêng cho từng nhánh.

## 11. Primitive specialization để tránh boxing

Nếu nguồn là int, long hoặc double, nên dùng:

- Spliterator.OfInt với IntConsumer;
- Spliterator.OfLong với LongConsumer;
- Spliterator.OfDouble với DoubleConsumer.

Và tạo stream tương ứng bằng:

- StreamSupport.intStream(...);
- StreamSupport.longStream(...);
- StreamSupport.doubleStream(...).

Nếu dùng Spliterator<Integer> cho dãy số lớn, mỗi phần tử có thể cần boxing/unboxing. Primitive specialization giúp tránh overhead đó ở đường duyệt. Đây là lý do ví dụ đầu tiên triển khai Spliterator.OfInt.

Với object như Order, Customer hoặc Event, dùng Spliterator<T> là tự nhiên; không cần cố ép thành primitive.

## 12. Quản lý resource khi nguồn là file, socket hoặc cursor

Spliterator không kế thừa AutoCloseable. Nếu nó đọc từ BufferedReader, file, socket hoặc database cursor, việc hoàn tất traversal không tự động đóng resource.

Có thể gắn cleanup vào Stream bằng onClose():

~~~java
Stream<String> stream =
    StreamSupport.stream(spliterator, false)
        .onClose(() -> closeSource());

try (Stream<String> managed = stream) {
    managed.forEach(this::process);
}
~~~

closeSource() phải đóng tài nguyên và xử lý checked exception phù hợp. Nếu dùng reader/database cursor, có thể để component sở hữu resource quản lý trực tiếp bằng try-with-resources.

Không mở connection/file trong mỗi tryAdvance() rồi để chúng không được đóng. Không giữ resource vô hạn nếu terminal operation short-circuit như findFirst() hoặc limit() dừng sớm. Khi nguồn có tài nguyên, đường đóng phải hoạt động cả khi traversal kết thúc bình thường lẫn khi pipeline ném exception.

## 13. Kiểm thử Spliterator trước khi đưa vào Stream

Một Spliterator tùy biến nên được test trực tiếp, trước khi test pipeline.

### Kiểm thử duyệt tuần tự

- tryAdvance() trả đúng phần tử tiếp theo.
- Sau phần tử cuối, tryAdvance() trả false.
- forEachRemaining() chỉ xử lý phần còn lại.
- Không có phần tử lặp lại hoặc bị bỏ qua.

### Kiểm thử chia

- trySplit() trả null khi không còn đủ phần tử để chia.
- Prefix và phần còn lại không giao nhau.
- Hợp hai phần tái tạo đúng toàn bộ dữ liệu.
- Với ORDERED, prefix đứng trước phần còn lại.
- Tổng estimateSize() của các phần bằng kích thước trước split nếu báo SUBSIZED.
- Chia lặp lại cuối cùng phải dừng.

### Kiểm thử characteristics

- SIZED chỉ khi size chính xác.
- SUBSIZED chỉ khi mọi split có size chính xác.
- SORTED phải có comparator đúng.
- NONNULL, DISTINCT, IMMUTABLE và CONCURRENT phải phản ánh đúng nguồn.
- Không tự đặt thêm flag chỉ để Stream có vẻ tối ưu hơn.

### Kiểm thử Stream

Chạy cùng một phép toán trên sequential và parallel stream:

~~~java
long sequentialCount = StreamSupport
    .stream(createSpliterator(), false)
    .filter(this::matches)
    .count();

long parallelCount = StreamSupport
    .stream(createSpliterator(), true)
    .filter(this::matches)
    .count();
~~~

Với phép toán deterministic và không có interference, kết quả phải tương đương. Tạo Spliterator mới cho mỗi pipeline vì mỗi Spliterator chỉ phục vụ một lần bulk computation.

Không test concurrency bằng Thread.sleep(). Nếu cần điều khiển thời điểm giữa các thread, dùng CountDownLatch, barrier hoặc cơ chế đồng bộ phù hợp.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| tryAdvance() không tăng cursor | Trả lại một phần tử vô hạn | Chỉ tiêu thụ mỗi phần tử một lần |
| trySplit() trả hai vùng chồng lấn | Duplicate trong stream | Tách prefix và remainder không giao nhau |
| Bỏ sót phần tử ở midpoint | Kết quả thiếu | Xác định rõ range inclusive/exclusive |
| ORDERED nhưng split không trả prefix | Vi phạm encounter order | Trả strict prefix khi chia |
| SIZED nhưng estimateSize sai | Stream có thể tối ưu sai | Chỉ báo SIZED khi chính xác |
| Báo SUBSIZED dù split không chính xác | Sai giả định về kích thước con | Kiểm mọi split và split tiếp |
| SORTED nhưng comparator không đúng | Sort semantics sai | Trả comparator đúng hoặc bỏ SORTED |
| Báo NONNULL cho nguồn có null | Stream có thể tối ưu sai | Chỉ báo khi nguồn bảo đảm |
| Báo IMMUTABLE cho list có thể sửa | Interference không được mô tả đúng | Dùng late-binding/fail-fast hoặc source phù hợp |
| Dùng CONCURRENT cho mọi truy cập đa luồng | Nhầm read concurrency với concurrent mutation | Chỉ báo khi nguồn hỗ trợ cập nhật đồng thời |
| Chia quá mất cân bằng | Parallel stream chậm | Split theo range/partition cân bằng |
| trySplit() quét toàn bộ nguồn mỗi lần | Chi phí chia quá cao | Chia bằng index/metadata nếu có |
| Dùng iterator unknown-size cho dữ liệu lớn cần parallel | Khả năng chia và sizing hạn chế | Viết Spliterator theo cấu trúc nguồn |
| Chia sẻ cùng một Spliterator cho nhiều thread | Cursor race, mất/nhân phần tử | Mỗi instance chỉ một thread tại một thời điểm |
| Sửa nguồn trong lúc Stream chạy | CME hoặc kết quả không xác định | Không interference; dùng concurrent source khi phù hợp |
| Dùng lại Stream đã terminal | IllegalStateException hoặc hành vi không hợp lệ | Tạo Stream mới từ nguồn |
| Không đóng resource-backed stream | Rò rỉ file/socket/cursor | Gắn onClose và dùng try-with-resources |
| Dùng boxing cho primitive stream lớn | Tăng allocation/CPU | OfInt/OfLong/OfDouble |
| Nghĩ parallel luôn nhanh hơn | Overhead có thể lớn hơn công việc | Benchmark với dữ liệu và workload thực tế |

## 15. Bài tập thực hành có đáp án

### Bài 1 — mục đích của Spliterator

**Đề:** Spliterator khác Iterator ở khả năng quan trọng nào?

**Đáp án:** Spliterator có trySplit() để phân hoạch phần dữ liệu còn lại, ngoài việc duyệt từng phần tử. Điều này hỗ trợ parallel stream.

### Bài 2 — tryAdvance

**Đề:** Khi không còn phần tử, tryAdvance() phải trả gì?

**Đáp án:** false. Nếu có phần tử, action nhận một phần tử và phương thức trả true.

### Bài 3 — trySplit

**Đề:** Một nguồn ORDERED có encounter order [A, B, C, D]. Nếu trySplit() trả [C, D], có hợp lệ không?

**Đáp án:** Không theo hợp đồng prefix của ORDERED. Phần được trả về phải là strict prefix, ví dụ [A, B].

### Bài 4 — kích thước

**Đề:** estimateSize() trả một con số phỏng đoán. Có thể báo SIZED không?

**Đáp án:** Không. SIZED yêu cầu kích thước chính xác.

### Bài 5 — SUBSIZED

**Đề:** Một Spliterator báo SIZED. Có bắt buộc báo SUBSIZED không?

**Đáp án:** Không. SUBSIZED còn yêu cầu mọi Spliterator con được tạo bởi split đều có kích thước chính xác.

### Bài 6 — SORTED

**Đề:** Một Spliterator chứa số nguyên theo thứ tự tăng tự nhiên. getComparator() trả gì khi báo SORTED?

**Đáp án:** null, biểu thị thứ tự tự nhiên.

### Bài 7 — primitive

**Đề:** Nguồn chứa hàng triệu int. Nên triển khai Spliterator<Integer> hay OfInt?

**Đáp án:** OfInt giúp tránh boxing trong đường duyệt primitive.

### Bài 8 — iterator unknown size

**Đề:** Iterator không biết trước số phần tử. Adapter nào có sẵn?

**Đáp án:** Spliterators.spliteratorUnknownSize(iterator, characteristics).

### Bài 9 — late binding

**Đề:** Muốn lấy Spliterator khi terminal operation bắt đầu, dùng factory nào?

**Đáp án:** StreamSupport.stream(Supplier, characteristics, parallel).

### Bài 10 — source interference

**Đề:** Có thể thêm phần tử vào ArrayList trong khi parallel stream đang duyệt không?

**Đáp án:** Không. Nguồn mutable không concurrent không được structurally modify trong traversal.

### Bài 11 — thread safety

**Đề:** Có thể gọi tryAdvance() đồng thời trên cùng một Spliterator từ hai thread không?

**Đáp án:** Không. Mỗi instance chỉ nên được một thread sử dụng tại một thời điểm. Chia bằng trySplit() rồi chuyển các instance con cho thread khác.

### Bài 12 — parallel order

**Đề:** Parallel stream dùng forEach() có bảo đảm thứ tự encounter không?

**Đáp án:** Không. Nếu cần xử lý theo encounter order, dùng forEachOrdered() hoặc collector giữ thứ tự.

### Bài 13 — AbstractSpliterator

**Đề:** Khi nào AbstractSpliterator hữu ích?

**Đáp án:** Khi có thể triển khai tryAdvance() nhưng thuật toán chia nguồn tùy biến khó thực hiện; implementation mặc định cung cấp một mức splitting giới hạn.

### Bài 14 — resource

**Đề:** Spliterator đọc file có tự đóng BufferedReader khi stream kết thúc không?

**Đáp án:** Không. Gắn cleanup bằng onClose() và đóng Stream bằng try-with-resources hoặc để owner quản lý resource.

### Bài 15 — parallel performance

**Đề:** trySplit() trả hai phần đúng nhưng chia rất chậm. Parallel stream có chắc nhanh không?

**Đáp án:** Không. Chi phí chia, scheduling và mất cân bằng có thể lớn hơn lợi ích song song. Hãy đo workload thực tế.

## 16. Câu hỏi tự đánh giá

**1.** Spliterator thuộc package nào? — java.util.

**2.** StreamSupport thuộc package nào? — java.util.stream.

**3.** Phương thức lấy một phần tử là gì? — tryAdvance().

**4.** Phương thức chia nguồn là gì? — trySplit().

**5.** Khi không chia được, trySplit() trả gì? — null.

**6.** estimateSize() biểu diễn gì? — Ước lượng số phần tử còn lại.

**7.** SIZED có nghĩa gì? — Kích thước chính xác đã biết.

**8.** SUBSIZED có nghĩa gì? — Mọi phần được split tiếp đều có size chính xác.

**9.** ORDERED yêu cầu gì khi split? — Phần trả về là strict prefix.

**10.** SORTED với natural order trả comparator nào? — null.

**11.** NONNULL bảo đảm điều gì? — Không có phần tử null.

**12.** IMMUTABLE mô tả gì? — Cấu trúc nguồn không thể bị thay đổi.

**13.** CONCURRENT có nghĩa gì? — Nguồn hỗ trợ cập nhật đồng thời theo hợp đồng.

**14.** Spliterator có thread-safe mặc định không? — Không.

**15.** Dùng API nào để tạo Stream từ Spliterator? — StreamSupport.stream().

**16.** Dùng API nào cho nguồn int? — StreamSupport.intStream().

**17.** Adapter cho Iterator không biết size? — Spliterators.spliteratorUnknownSize().

**18.** Factory nào hỗ trợ late binding? — StreamSupport.stream(Supplier, characteristics, parallel).

**19.** Một Stream có thể được terminal nhiều lần không? — Không; tạo stream mới cho lần duyệt mới.

**20.** Spliterator có tự đóng file/socket không? — Không; resource phải được quản lý riêng.

## Tài liệu chính thức

- [Java SE 8 — Spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html) — hợp đồng tryAdvance, trySplit, estimateSize, characteristics và primitive specialization.
- [Java SE 8 — StreamSupport](https://docs.oracle.com/javase/8/docs/api/java/util/stream/StreamSupport.html) — tạo Stream/IntStream từ Spliterator hoặc Supplier.
- [Java SE 8 — Spliterators](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterators.html) — adapter cho Collection, Iterator, unknown size và AbstractSpliterator.
- [Java SE 8 — Spliterators.AbstractSpliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterators.AbstractSpliterator.html) — hỗ trợ triển khai tryAdvance với limited splitting.
- [Java SE 8 — Stream package](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html) — source, pipeline, laziness, sequential và parallel semantics.
- [Java SE 26 — Spliterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html) — xác nhận các hợp đồng Spliterator tiếp tục hiện hành.
- [Java SE 26 — StreamSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/StreamSupport.html) — factory Stream từ Spliterator và Supplier ở JDK hiện tại.

**Ghi nhớ:** Spliterator là hợp đồng duyệt và phân hoạch nguồn; StreamSupport kết nối hợp đồng đó với Stream API. tryAdvance() tiêu thụ một phần tử, trySplit() chia phần còn lại không chồng lấn, estimateSize() phải chính xác khi báo SIZED và characteristics chỉ được khai báo khi nguồn bảo đảm. Với nguồn có thể chia theo index/range, hãy ưu tiên split cân bằng; với Iterator, dùng adapter có sẵn nếu đủ. Dùng Supplier-based StreamSupport để late-bind nguồn mutable trước khi traversal bắt đầu, tránh sửa nguồn trong lúc stream đang chạy, và dùng OfInt/OfLong/OfDouble cho dữ liệu primitive. Parallel chỉ có lợi khi việc chia và xử lý thực sự hiệu quả.