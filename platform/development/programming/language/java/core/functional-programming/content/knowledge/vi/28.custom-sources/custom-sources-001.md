# Spliterator và vai trò duyệt hoặc phân chia nguồn trong Java Stream

Khi dùng `list.stream()`, `Arrays.stream(array)` hay `IntStream.range(...)`, Java đã cung cấp cách duyệt dữ liệu cho Stream. Nhưng nếu nguồn dữ liệu là một cấu trúc tự thiết kế — chẳng hạn vùng số, tập bản ghi phân đoạn, cấu trúc cây, khối dữ liệu hoặc một API đọc tuần tự — ta cần hiểu **`Spliterator`**: giao diện giúp Stream **duyệt phần tử** và, khi có thể, **chia nguồn thành các phần độc lập để xử lý song song**.

`Spliterator` viết tắt gợi nhớ đến *splittable iterator*. Một spliterator mô tả **tập phần tử còn phải duyệt**, cung cấp thao tác lấy phần tử kế tiếp, ước lượng số phần tử còn lại và tách một phần công việc thành spliterator khác. Nó là thành phần đầu vào quan trọng trong cơ chế Stream, nhưng **không tự động biến mọi nguồn thành nguồn song song hiệu quả**.

~~~text
Nguồn tùy chỉnh: [1, 2, 3, 4, 5, 6, 7, 8]
                  |
                  v
           Spliterator.OfInt
                  |
        trySplit()| 
          +-------+-------+
          |               |
      [1,2,3,4]       [5,6,7,8]
          |               |
       task A           task B
          +-------+-------+
                  |
             combine
                  |
       kết quả terminal Stream
~~~

Những kỹ năng chính của bài: hiểu `tryAdvance()`, `forEachRemaining()`, `trySplit()`, `estimateSize()`, các **characteristics**, cách tạo Stream bằng `StreamSupport` và cách kiểm thử một Spliterator tự viết.

## 1. `Iterator` và `Spliterator` khác nhau thế nào?

`Iterator<T>` chủ yếu cung cấp `hasNext()` và `next()` để đọc lần lượt từng phần tử. `Spliterator<T>` kết hợp khả năng duyệt với **khả năng tách nguồn thành các phần công việc**, giúp Stream framework có lựa chọn thực thi song song.

| Khía cạnh | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Duyệt từng phần tử | `hasNext()` + `next()` | `tryAdvance(action)` |
| Duyệt hết phần còn lại | Vòng lặp, `forEachRemaining` | `forEachRemaining(action)` |
| Chia phần công việc | Không có API chuẩn | `trySplit()` |
| Ước lượng số phần tử còn lại | Không có phương thức tổng quát | `estimateSize()` |
| Công bố đặc điểm nguồn | Không có bộ cờ chuẩn | `characteristics()` |
| Phục vụ Stream song song | Cần cơ chế adapter/buffering | API được Stream sử dụng trực tiếp |

Đừng suy luận `Spliterator` luôn nhanh hơn `Iterator`. Ưu điểm cốt lõi là **mô tả đủ thông tin để Stream có thể quyết định chiến lược duyệt và chia việc**.

Một collection chuẩn thường cung cấp `collection.spliterator()`. Khi gọi `collection.stream()` hoặc `collection.parallelStream()`, Java có thể dùng Spliterator của nguồn làm đầu vào. Với nguồn tùy chỉnh không phải Collection, ta có thể tạo đối tượng Spliterator trực tiếp rồi chuyển cho `StreamSupport`.

## 2. Các phương thức cốt lõi

### `boolean tryAdvance(Consumer<? super T> action)`

`tryAdvance` thử chuyển **đúng một phần tử** còn lại cho `action`:

- Trả `true` khi đã xử lý một phần tử.
- Trả `false` khi không còn phần tử để duyệt.
- Sau khi trả `false` vì hết nguồn, lần gọi sau không được tự phát lại các phần tử đã duyệt.
- `action` không được `null`; các implementation đúng thường kiểm tra `Objects.requireNonNull(action)`.

Ví dụ:

~~~java
Spliterator<String> sp = List.of("A", "B").spliterator();

boolean first = sp.tryAdvance(System.out::println); // in A, trả true
boolean second = sp.tryAdvance(System.out::println); // in B, trả true
boolean third = sp.tryAdvance(System.out::println); // trả false
~~~

Đây là **đoạn minh họa** trong phương thức, cần import `List` và `Spliterator`. `tryAdvance` là thao tác **tiêu thụ trạng thái duyệt**; không gọi nó để "nhìn thử" nếu vẫn mong Stream bắt đầu lại từ phần tử đầu.

### `void forEachRemaining(Consumer<? super T> action)`

Duyệt toàn bộ phần còn lại, chuyển từng phần tử cho `action`. Có thể hiểu triển khai mặc định theo ý tưởng:

~~~java
// Minh họa logic, không phải source code JDK:
while (tryAdvance(action)) {
    // Đã xử lý thêm một phần tử.
}
~~~

Nếu đã `tryAdvance` một lần, `forEachRemaining` chỉ duyệt những phần tử **chưa được tiêu thụ**.

### `Spliterator<T> trySplit()`

Thử tách một phần tử hoặc một tập con các phần tử **chưa được duyệt** thành một Spliterator khác. Trả `null` khi không thể hoặc không muốn chia tiếp. Sau lần tách thành công, hai Spliterator phải bao phủ các phần dữ liệu **không trùng nhau**, và hợp lại phải đại diện đúng tất cả các phần tử còn lại trước khi chia.

Với nguồn ordered, một `trySplit` đúng thường trả về một **prefix** của phần còn lại; Spliterator gốc tiếp tục quản lý **suffix**. Không bắt buộc chia chính xác 50–50 trong mọi trường hợp, nhưng các phần đủ cân bằng giúp xử lý song song hiệu quả hơn.

### `long estimateSize()`

Trả **ước lượng** số phần tử còn lại. Nếu không biết hoặc số phần tử có thể không bị chặn hữu hạn, có thể trả `Long.MAX_VALUE`. Nếu khai báo đặc tính `SIZED`, giá trị này phải đáp ứng bảo đảm kích thước chính xác theo hợp đồng tương ứng, không chỉ là ước lượng phỏng đoán.

### `int characteristics()` và `hasCharacteristics(int flags)`

`characteristics()` trả một tập cờ bit biểu thị tính chất có thật của nguồn và cách duyệt. `hasCharacteristics(mask)` kiểm tra tất cả bit yêu cầu có được thiết lập không:

~~~java
boolean ordered = sp.hasCharacteristics(Spliterator.ORDERED);
boolean sized = sp.hasCharacteristics(Spliterator.SIZED);
~~~

Khai báo cờ quá mức là **lỗi hợp đồng**: Stream framework có thể dùng thông tin đó để tối ưu và cho kết quả sai khi khai báo không đúng.

## 3. `trySplit()` là cơ chế chia nguồn, không phải chạy thread

Một điểm quan trọng: **`trySplit` không tự tạo thread, không tự khởi chạy `parallelStream` và không tự gọi terminal operation**. Nó chỉ chia **quyền duyệt các phần tử còn lại** cho hai Spliterator. Stream framework quyết định có yêu cầu tách hay không, tách bao nhiêu lần, và giao các phần cho những task nào.

Với phạm vi số nguyên `[1, 9)` (bao gồm 1, loại trừ 9):

~~~text
Ban đầu:
  spliterator: [1,2,3,4,5,6,7,8]

Gọi trySplit():
  returned prefix: [1,2,3,4]
  original suffix: [5,6,7,8]

Gọi trySplit() trên original lần nữa, nếu được:
  returned prefix: [5,6]
  original suffix: [7,8]
~~~

**Tính đúng trước hết:** mỗi phần tử thuộc đúng một nhánh, không có phần tử mất hoặc bị phát hai lần. **Tối ưu sau:** các nhánh có kích thước hợp lý để chi phí xử lý cân bằng, không tạo vô số nhánh quá nhỏ nếu việc chia tốn kém.

Nếu `trySplit` luôn trả `null`, nguồn **vẫn có thể dùng với Stream**, kể cả khi yêu cầu `parallel=true`; nhưng khả năng chia việc bị hạn chế và mức độ song song thực tế có thể thấp. Ngược lại, `trySplit` trả non-null không bảo đảm JVM có đủ lõi hoặc có lợi về hiệu năng.

### Không chia những phần đã duyệt

Giả sử nguồn còn `[3,4,5,6]` sau khi hai phần tử đầu đã đi qua `tryAdvance`. Lúc đó `trySplit` chỉ được chia **phần còn lại**, không lấy lại `1,2`. Tách sai sẽ tạo bản ghi trùng hoặc làm mất dữ liệu khi collect song song.

## 4. Những characteristic cần biết

Các cờ được định nghĩa ở `java.util.Spliterator`:

| Cờ | Bảo đảm chính | Tình huống điển hình |
| --- | --- | --- |
| `ORDERED` | Các phần tử có encounter order được xác định | List, vùng số tăng dần |
| `DISTINCT` | Không có hai phần tử tương đương theo `equals` | Nguồn bảo đảm giá trị duy nhất |
| `SORTED` | Encounter order là một thứ tự sắp xếp đã xác định | Nguồn số tăng dần |
| `SIZED` | Biết chính xác số phần tử còn lại trong điều kiện hợp đồng | Array, phạm vi số hữu hạn |
| `SUBSIZED` | Mọi Spliterator sinh ra sau khi chia cũng có `SIZED` và `SUBSIZED` | Chia chỉ số mảng/phạm vi chính xác |
| `NONNULL` | Không phát phần tử `null` | `int`, nguồn bảo đảm non-null |
| `IMMUTABLE` | Nguồn không thể bị thay đổi cấu trúc trong quá trình duyệt | Dãy số được tính từ biên cố định |
| `CONCURRENT` | Nguồn cho phép sửa đổi đồng thời trong quá trình duyệt theo hợp đồng tương ứng | Một số cấu trúc concurrent |

Đây là **bảo đảm của nguồn** chứ không phải một yêu cầu "hãy bật các tối ưu" tùy ý. Khi thiết kế Spliterator tự tạo, chỉ công bố cờ có thể chứng minh được.

### `ORDERED` khác `SORTED`

`ORDERED` chỉ nói có thứ tự gặp phần tử có nghĩa. Ví dụ `["C", "A", "B"]` có thứ tự rõ ràng nhưng **không** được sắp theo alphabet.

`SORTED` mạnh hơn: phần tử được duyệt theo thứ tự sắp xếp đã công bố. Theo đặc tả, `SORTED` kéo theo `ORDERED`; nếu nguồn tự tạo khai báo `SORTED`, `getComparator()` phải đúng:

- Trả `null` nếu thứ tự tự nhiên.
- Trả comparator nếu có thứ tự tùy chỉnh.
- Nếu không có `SORTED`, `getComparator()` phải ném `IllegalStateException` theo hợp đồng.

Đừng gắn `SORTED` cho một nguồn chỉ "thỉnh thoảng" tạo ra dữ liệu tăng dần. Nếu phần tử có khả năng đảo thứ tự, phải bỏ cờ hoặc sửa thuật toán tạo dữ liệu.

### `DISTINCT` liên quan `equals`, không phải comparator

Spliterator có `DISTINCT` khi không có hai phần tử bằng nhau theo `equals`. Với nguồn số nguyên từ 1 tới 8, điều kiện này đúng. Với các bản ghi có cùng ID nhưng version khác nhau, chúng có thể **không bằng nhau theo `equals`**, dù nghiệp vụ coi cùng ID là một mục; phải xác định rõ hợp đồng equality.

### `IMMUTABLE` không có nghĩa state duyệt không thay đổi

Một Spliterator cần tăng con trỏ `cursor` khi duyệt. Điều đó **không mâu thuẫn với `IMMUTABLE`**: cờ này nói **cấu trúc nguồn dữ liệu không bị thay đổi**, không cấm cập nhật vị trí duyệt nội bộ. Ví dụ một phạm vi số xác định bằng hai biên bất biến không có collection nguồn để bị thêm/xóa phần tử.

### `CONCURRENT` của Spliterator không phải của Collector

`Spliterator.CONCURRENT` mô tả đặc tính **nguồn** khi có thay đổi cấu trúc đồng thời; `Collector.Characteristics.CONCURRENT` mô tả khả năng **accumulator** nhận cập nhật đồng thời lên cùng container. Hai cờ thuộc hai giao diện khác nhau và **không thể dùng thay thế cho nhau**.

Không khai báo `CONCURRENT` cho một nguồn `ArrayList` thường để "chữa" việc list bị sửa từ thread khác. Cũng không tự gắn `IMMUTABLE` khi nguồn vẫn có thể bị thêm/xóa phần tử ngoài ý muốn.

## 5. `SIZED`, `SUBSIZED` và chi phí phân chia

`SIZED` nói về một Spliterator có thể báo **kích thước chính xác** của những phần tử còn lại dưới các giả định của hợp đồng. `SUBSIZED` nói rằng sau các lần chia, các Spliterator con **cũng** giữ đặc tính `SIZED`/`SUBSIZED`.

Ví dụ nguồn số 1–8:

~~~text
Trước khi duyệt: estimateSize() = 8
Sau tryAdvance một phần tử: estimateSize() = 7

Tách nguồn mới 1..8:
  prefix [1..4]: estimateSize() = 4
  suffix [5..8]: estimateSize() = 4
  Tổng kích thước = 8
~~~

Kích thước chính xác có thể giúp framework **phân phối task, phân bổ bộ đệm và tối ưu terminal phù hợp**. Nhưng `estimateSize` không phải yêu cầu buộc framework gọi `trySplit` đến khi mỗi nhánh có đúng một phần tử.

Một nguồn đọc file mạng, dữ liệu tăng liên tục hoặc một iterator không có thông tin về lượng phần tử còn lại không nên tự công bố `SIZED`. Với nguồn không biết kích thước, có thể trả `Long.MAX_VALUE` và bỏ `SIZED/SUBSIZED`. Bịa kích thước chính xác nhằm làm Stream "chạy nhanh hơn" có thể dẫn đến sai logic hoặc lỗi khi framework tin vào metadata.

`getExactSizeIfKnown()` là phương thức tiện ích: nếu Spliterator có `SIZED`, nó có thể trả kích thước chính xác; nếu không, trả `-1`. Không nhầm phương thức này với `estimateSize()` — phương thức thứ hai vẫn có thể trả một ước lượng khi không biết kích thước chính xác.

## 6. Ví dụ Java 17+: tự viết `Spliterator.OfInt` cho vùng số

Để tránh boxing khi duyệt số nguyên, Java cung cấp các chuyên biệt:

- `Spliterator.OfInt`: dùng `IntConsumer` và `IntStream`.
- `Spliterator.OfLong`: dùng `LongConsumer` và `LongStream`.
- `Spliterator.OfDouble`: dùng `DoubleConsumer` và `DoubleStream`.

Một ví dụ đầy đủ là `RangeSpliterator` duyệt các số `startInclusive` đến `endExclusive - 1`, biết kích thước chính xác và chia theo midpoint.

Lưu tệp **`SpliteratorSourceDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorSourceDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.cursor = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (cursor >= fence) {
                return false;
            }
            action.accept(cursor++);
            return true;
        }

        @Override
        public OfInt trySplit() {
            int remaining = fence - cursor;
            if (remaining <= 1) {
                return null;
            }
            int midpoint = cursor + remaining / 2;
            OfInt prefix = new RangeSpliterator(cursor, midpoint);
            cursor = midpoint;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                    | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            return null; // Natural ascending order
        }
    }

    public static void main(String[] args) {
        Spliterator.OfInt probe = new RangeSpliterator(1, 9);
        System.out.println("estimatedBefore=" + probe.estimateSize());
        probe.tryAdvance((int n) -> System.out.println("first=" + n));
        System.out.println("estimatedAfter=" + probe.estimateSize());

        Spliterator.OfInt remainder = new RangeSpliterator(1, 9);
        Spliterator.OfInt prefix = remainder.trySplit();
        System.out.println("prefixSize=" + prefix.estimateSize());
        System.out.println("remainderSize=" + remainder.estimateSize());
        System.out.println("prefix="
                + StreamSupport.intStream(prefix, false).boxed().toList());
        System.out.println("remainder="
                + StreamSupport.intStream(remainder, false).boxed().toList());

        System.out.println("parallelSquares="
                + StreamSupport.intStream(new RangeSpliterator(1, 9), true)
                    .map(n -> n * n).sum());
        System.out.println("parallelOrdered="
                + StreamSupport.intStream(new RangeSpliterator(1, 9), true)
                    .boxed().toList());
        Spliterator.OfInt flags = new RangeSpliterator(1, 9);
        System.out.println("ordered=" + flags.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("sized=" + flags.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized=" + flags.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("naturalComparator=" + (flags.getComparator() == null));
    }
}
~~~

Lệnh kiểm thử với JDK 17+:

~~~bash
javac SpliteratorSourceDemo.java
java SpliteratorSourceDemo
~~~

**Stdout chính xác:**

~~~text
estimatedBefore=8
first=1
estimatedAfter=7
prefixSize=4
remainderSize=4
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
parallelSquares=204
parallelOrdered=[1, 2, 3, 4, 5, 6, 7, 8]
ordered=true
sized=true
subsized=true
naturalComparator=true
~~~

Giải thích:

1. `RangeSpliterator(1, 9)` biểu diễn dãy 1 đến 8, có tám giá trị, do đó `estimateSize()` ban đầu là 8.
2. `tryAdvance` giao phần tử `1` cho action rồi cập nhật con trỏ; phần còn lại có bảy giá trị.
3. `trySplit` trên một nguồn mới chia thành phần trả về là `[1,2,3,4]` và phần gốc còn lại là `[5,6,7,8]`. Mỗi bên báo kích thước 4.
4. `StreamSupport.intStream(prefix, false)` tạo một Stream tuần tự từ nhánh prefix; tương tự cho nhánh suffix. Sau khi tiêu thụ nhánh, không dùng lại đối tượng đó để xây Stream khác.
5. `StreamSupport.intStream(new RangeSpliterator(1,9), true)` yêu cầu pipeline song song. Tổng bình phương các số 1..8 là `204`.
6. `parallelOrdered` cho thấy sau khi xử lý song song, `toList()` vẫn giữ encounter order vì Spliterator công bố và thực hiện đúng `ORDERED`.
7. `getComparator() == null` là đúng với một Spliterator `SORTED` sử dụng **thứ tự tự nhiên**; nó không có nghĩa "không sắp xếp".
8. Ví dụ không khai báo `CONCURRENT`: con trỏ `cursor` không được thiết kế để nhiều thread cùng gọi `tryAdvance` trên **một Spliterator duy nhất**. Framework có thể dùng những Spliterator đã chia cho các task riêng.

Trong phiên bản minh họa, kích thước dãy là nhỏ để dễ quan sát; với phạm vi số `int` cực lớn, phép `fence - cursor` tính ở kiểu `int` có thể tràn **trước khi** gán vào `remaining`. Vì vậy **đừng áp dụng nguyên xi thuật toán chia bằng `int remaining` này cho mọi cặp biên `int` cách nhau hơn `Integer.MAX_VALUE`**. Nếu xây nguồn production cần hỗ trợ toàn bộ miền giá trị, hãy tính khoảng cách bằng `long` và thiết kế lại phép chia/ước lượng cho đúng. Các tính chất `SIZED/SUBSIZED` chỉ được công bố khi implementation thật sự đáp ứng giới hạn của miền được hỗ trợ.

## 7. Hiểu kỹ code `tryAdvance()` và `trySplit()`

### Con trỏ và biên là hai loại trạng thái

`cursor` thay đổi sau mỗi phần tử được duyệt, nhưng `fence` cố định phạm vi bên phải. Điều kiện kết thúc là `cursor >= fence`. Có thể duyệt 0 phần tử nếu `startInclusive == endExclusive`.

Việc kiểm tra `action` khác null tránh gửi một `null` consumer vào pipeline. Nếu action ném ngoại lệ, exception có thể lan ra caller; Spliterator không nên tự nuốt ngoại lệ vì sẽ khiến lỗi xử lý bị che giấu. Không suy luận các lời gọi action xảy ra trên cùng thread trong Stream song song.

### Trả prefix, giữ suffix

Trong `trySplit`:

~~~java
int midpoint = cursor + remaining / 2;
OfInt prefix = new RangeSpliterator(cursor, midpoint);
cursor = midpoint;
return prefix;
~~~

Đây là **trích đoạn từ chương trình đầy đủ**, với biến `remaining` đã được tính. Khi trả về, `prefix` sở hữu `[cursor_cũ, midpoint)`; đối tượng hiện tại sở hữu `[midpoint, fence)`. Hai nhánh không trùng nhau.

Nếu còn 0 hoặc 1 phần tử, thuật toán trả `null` vì tách tiếp sẽ không có ích. Với nguồn đặc biệt có chi phí chia lớn, ta có thể chọn ngưỡng cao hơn, miễn không làm mất/nhân đôi phần tử.

### Không để hai Spliterator dùng chung cursor

Một lỗi dễ gặp khi tự triển khai:

~~~java
// PHẢN VÍ DỤ: hai nhánh cùng tham chiếu tới một Iterator mutable.
// trySplit() trả một wrapper đọc chung iterator,
// trong khi Spliterator gốc vẫn đọc chính iterator ấy.
~~~

Nếu hai nhánh không có phạm vi sở hữu độc lập, chúng có thể tranh nhau phần tử, phát sai thứ tự hoặc gây race. Việc trả một Spliterator khác không đồng nghĩa đã thật sự **chia dữ liệu**. Phải thiết kế quyền truy cập vào dữ liệu nguồn một cách không chồng chéo.

## 8. `StreamSupport`: đưa Spliterator vào Stream API

Các phương thức tạo Stream thường dùng:

~~~java
Stream<T> stream = StreamSupport.stream(spliterator, false);
Stream<T> parallel = StreamSupport.stream(spliterator, true);
IntStream primitive = StreamSupport.intStream(intSpliterator, true);
~~~

Đây là **cú pháp minh họa**, cần import `StreamSupport`, `Stream`, `IntStream` và các biến Spliterator thích hợp. Tham số boolean:

- `false` yêu cầu Stream tuần tự.
- `true` yêu cầu Stream song song.
- Yêu cầu song song **không** bảo đảm JVM chắc chắn dùng nhiều task hoặc nhanh hơn.

Có hai dạng chính của `StreamSupport.stream`: một dạng nhận Spliterator có sẵn; dạng khác nhận **Supplier<? extends Spliterator<T>>** cùng characteristics và cờ parallel.

Ví dụ tạo một Spliterator riêng khi terminal bắt đầu:

~~~java
Stream<Integer> numbers = StreamSupport.stream(
        () -> new RangeSpliterator(1, 9),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
            | Spliterator.DISTINCT | Spliterator.SORTED
            | Spliterator.NONNULL | Spliterator.IMMUTABLE,
        false
).boxed(); // Không đúng kiểu nếu dùng StreamSupport.stream cho OfInt.
~~~

**Đoạn trên cố ý minh họa lỗi chọn overload**: `StreamSupport.stream` tạo `Stream<T>`, vốn không có `boxed()`. Với nguồn `Spliterator.OfInt` cần gọi **`StreamSupport.intStream`**. Cách viết đúng:

~~~java
IntStream numbers = StreamSupport.intStream(
        () -> new RangeSpliterator(1, 9),
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
            | Spliterator.DISTINCT | Spliterator.SORTED
            | Spliterator.NONNULL | Spliterator.IMMUTABLE,
        false
);
~~~

Đây là **đoạn minh họa** sử dụng lớp `RangeSpliterator` của chương trình đầy đủ và import `IntStream`, `Spliterator`, `StreamSupport`. Nguồn ở đây chỉ được lấy khi bắt đầu thực thi terminal operation (*late binding* theo cách sử dụng Supplier overload). Các bit characteristic khai báo cho Supplier phải **khớp với characteristic thực tế** của Spliterator mà Supplier trả về; không được nói nguồn có `SIZED` nếu nó không có.

Lợi ích của overload Supplier là giảm nguy cơ có thay đổi nguồn giữa thời điểm **xây Stream** và **bắt đầu terminal**, đặc biệt khi Spliterator tương ứng không có đặc tính `IMMUTABLE` hoặc `CONCURRENT` và không late-binding. Tuy vậy, nó không làm nguồn mutable trở nên thread-safe.

### Không dùng lại Spliterator đã bị Stream tiêu thụ

~~~java
Spliterator.OfInt sp = new RangeSpliterator(1, 5);
long count = StreamSupport.intStream(sp, false).count();
// Đừng sử dụng lại sp như nguồn mới để kỳ vọng đọc đủ 1..4.
~~~

Một Stream chỉ dùng cho một terminal. Ngoài ra, **không tự duyệt một Spliterator sau khi đã giao nó cho một Stream** rồi kỳ vọng Stream vẫn nhìn thấy toàn bộ dữ liệu. Để chạy nhiều phép tính độc lập, tạo Spliterator mới từ nguồn có thể phát lại, hoặc dùng một terminal tổng hợp phù hợp.

## 9. Iterator adapter và nguồn không biết kích thước

Không phải nguồn nào cũng dễ chia theo index. Nếu chỉ có `Iterator<T>`, Java có tiện ích:

~~~java
Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> sp = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

List<String> result = StreamSupport.stream(sp, false).toList();
// [A, B, C]
~~~

Đây là đoạn **có thể đặt trong một phương thức** với các import `Iterator`, `List`, `Spliterator`, `Spliterators` và `StreamSupport`. Adapter không biết tổng kích thước từ đầu; do đó không được gắn `SIZED/SUBSIZED` tùy tiện. Với iterator nguồn tuần tự, khả năng chia song song có thể đòi hỏi **đọc và đệm trước** theo batch hoặc không hiệu quả bằng nguồn có phạm vi index tách độc lập.

Nếu một nguồn là dữ liệu mạng/đọc file theo luồng hoặc nguồn có side effect, cũng phải quản lý **đóng tài nguyên**, tốc độ phát và lỗi I/O. Spliterator không tự thay thế `try-with-resources` hoặc cơ chế đóng underlying resource.

### Tình huống stream vô hạn

`Spliterator` có thể đại diện nguồn không giới hạn, nhưng nếu không có điều kiện dừng, terminal như `toList()` sẽ không thể hoàn thành hữu hạn. Hơn nữa, nguồn không có kích thước hữu hạn không được tự gắn `SIZED`. Một pipeline như `limit(n)` có thể giới hạn dữ liệu, nhưng tác động của các phép stateful khác phía trước nó vẫn cần xem xét.

## 10. Thứ tự, song song và terminal operation

`ORDERED` nghĩa là nguồn định nghĩa encounter order, nhưng **không bảo đảm mọi terminal thực hiện side effect đúng theo thứ tự này**.

~~~java
// Có thể in không theo thứ tự:
StreamSupport.intStream(new RangeSpliterator(1, 9), true)
        .forEach(System.out::println);
~~~

`forEach` song song không cam kết thứ tự gọi action. Ngược lại:

~~~java
// Giữ encounter order của nguồn:
StreamSupport.intStream(new RangeSpliterator(1, 9), true)
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` yêu cầu action được thực thi theo encounter order, nhưng có thể tăng chi phí phối hợp và không nên dùng làm giải pháp mặc định để xây list từ side effect. Nếu cần một List kết quả, `boxed().toList()` hoặc collector phù hợp thường rõ mục đích hơn.

**Tương tự:** Spliterator có `SORTED` không bảo đảm một thao tác `forEach` song song tự in theo thứ tự; `SORTED` diễn tả encounter order có sắp xếp, còn `forEach` không phải terminal giữ thứ tự. Hãy phân biệt **thứ tự logic của phần tử** với **thứ tự thời điểm callback chạy trên các thread**.

### Khai báo `SIZED` có thể ảnh hưởng việc thực thi pipeline

Một số terminal như `count()` có thể dùng thông tin kích thước khi pipeline không thay đổi số phần tử, thay vì thực hiện `tryAdvance` cho từng phần tử. Vì vậy **không đặt side effect bắt buộc** trong `peek()` hoặc trong quá trình phát phần tử với kỳ vọng mọi terminal chắc chắn đọc qua tất cả các giá trị. Metadata chính xác là một phần của hợp đồng giúp tối ưu hợp lệ.

## 11. Những lỗi thường gặp khi tự triển khai

**Không tăng con trỏ trong `tryAdvance`.** Nếu trả true nhưng không chuyển trạng thái, terminal có thể nhận mãi cùng một phần tử hoặc chạy vô hạn.

**Trả false quá sớm.** Nếu còn phần tử mà trả false, Stream sẽ cho rằng nguồn đã kết thúc và âm thầm mất dữ liệu.

**`trySplit` tạo phần dữ liệu chồng nhau.** Hai nhánh cùng phát một số bản ghi khiến count và reduction sai; lỗi có thể chỉ lộ ra khi chạy song song.

**`trySplit` không cập nhật phần còn lại của Spliterator gốc.** Nếu trả prefix mà original vẫn giữ toàn bộ nguồn, các giá trị trong prefix bị phát hai lần.

**Khai báo `SIZED` với số lượng không chính xác.** Tối ưu dựa trên metadata sai có thể tạo kết quả sai. Với nguồn có thể phát sinh dữ liệu mới, phải xem lại chính sách cờ.

**Khai báo `SUBSIZED` nhưng con không giữ kích thước chính xác.** Cờ này là hợp đồng áp dụng cho *toàn bộ các nhánh sau tách*, không chỉ Spliterator gốc.

**Khai báo `SORTED` nhưng dữ liệu không đúng thứ tự.** Framework có thể bỏ qua một bước sort hợp lệ dựa trên thông tin sai, khiến đầu ra không được sắp xếp như yêu cầu.

**Khai báo `CONCURRENT` để chữa race.** `CONCURRENT` mô tả bảo đảm của nguồn; không tự đồng bộ collection hay cursor. Nếu nguồn mutable không có đồng bộ, phải sửa thiết kế trước khi chọn cờ.

**Không xử lý đúng `getComparator()` khi có `SORTED`.** Với natural-order sorted Spliterator trả `null`; nếu comparator tùy chỉnh phải trả comparator đúng. Nếu không có `SORTED`, theo hợp đồng method không được báo một comparator như thể nguồn đã sort.

**Lấy `spliterator()` rồi tự gọi `tryAdvance` trước khi giao cho Stream.** Stream sẽ chỉ thấy phần còn lại của con trỏ đã tiến; nếu người gọi không chủ đích, kết quả bị thiếu phần tử đầu.

**Dùng `StreamSupport.stream` thay vì `intStream` cho primitive Spliterator.** Dễ dẫn đến boxing, suy luận kiểu sai hoặc cố gọi API không tồn tại trên `Stream<T>`.

**Chia quá nhiều task quá nhỏ.** Tách hàng triệu Spliterator chỉ để xử lý phép cộng đơn giản có thể tốn overhead hơn việc chạy tuần tự; cần chọn chiến lược phân vùng phù hợp.

**Không đóng tài nguyên nguồn.** Với file hoặc network connection, xây Stream không tự bảo đảm tài nguyên được đóng khi terminal hoàn tất; cần API có cơ chế close và quản lý bằng `try-with-resources` khi phù hợp.

## 12. Kiểm thử đúng: tuần tự, song song và trạng thái sau chia

Một Spliterator tùy chỉnh đáng tin cậy nên có các test sau:

1. **Duyệt tuần tự từ đầu tới hết:** không thiếu/trùng phần tử; gọi `tryAdvance` sau khi hết trả false.
2. **Duyệt từng phần rồi duyệt phần còn lại:** gọi `tryAdvance` vài lần, sau đó `forEachRemaining`; tổng kết quả vẫn đủ và đúng thứ tự nếu có `ORDERED`.
3. **Chia một lần và nhiều lần:** hợp nhất phần tử của tất cả nhánh không trùng/không thiếu; với ordered source, prefix/suffix ghép đúng encounter order.
4. **Kích thước:** trước/sau duyệt và sau chia, `estimateSize` đúng với `SIZED`; nếu có `SUBSIZED`, mọi con cũng đúng.
5. **Characteristics:** `ORDERED`, `SORTED`, `DISTINCT`, `NONNULL`, `IMMUTABLE`… chỉ được công bố nếu thực tế thỏa; `getComparator` đúng hợp đồng.
6. **Đầu vào biên:** phạm vi rỗng, một phần tử, số phần tử lẻ/chẵn, gần giới hạn kiểu số, tham số không hợp lệ.
7. **StreamSupport tuần tự/songsong:** so sánh tập giá trị, tổng, số phần tử và kết quả ordered từ hai chế độ.
8. **Nguồn có side effect/IO:** kiểm tra xử lý lỗi, vòng đời tài nguyên và không đánh giá nguồn sớm ngoài dự kiến.

Một cách kiểm tra dữ liệu nhỏ sau `trySplit`:

~~~java
Spliterator.OfInt whole = new RangeSpliterator(1, 9);
Spliterator.OfInt firstHalf = whole.trySplit();

List<Integer> a = StreamSupport.intStream(firstHalf, false).boxed().toList();
List<Integer> b = StreamSupport.intStream(whole, false).boxed().toList();

// a = [1,2,3,4], b = [5,6,7,8] với implementation này.
~~~

Đây là đoạn mã minh họa sử dụng lớp trong chương trình đầy đủ và import `List`, `Spliterator`, `StreamSupport`. Đừng cố tái dùng `whole` hoặc `firstHalf` sau khi terminal đã tiêu thụ chúng.

**Tóm lại:** Spliterator là **hợp đồng truy cập nguồn** cho Stream: `tryAdvance` duyệt phần tử, `trySplit` phân chia phần chưa duyệt, `estimateSize`/`characteristics` giúp framework lập kế hoạch và tối ưu. Nguồn tùy chỉnh chỉ chạy đúng và hiệu quả khi **tách không chồng chéo, con trỏ tiến chính xác, metadata trung thực và ranh giới đồng thời được thiết kế rõ**. Việc gọi `parallel=true` chỉ yêu cầu chế độ song song; nó không sửa được một Spliterator viết sai hoặc bảo đảm hiệu năng tự động.