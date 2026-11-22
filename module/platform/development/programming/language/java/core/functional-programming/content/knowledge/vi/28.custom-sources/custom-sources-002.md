# Spliterator: tryAdvance(), forEachRemaining() và trySplit() trong Java

**Spliterator<T>** là giao diện giúp Java duyệt một nguồn phần tử và, khi có thể, **chia những phần tử chưa xử lý thành các phần độc lập** để hỗ trợ Stream API. Khi tự tạo nguồn cho Stream, ba phương thức cần hiểu nhất là **tryAdvance()**, **forEachRemaining()** và **trySplit()**.

- **tryAdvance(action)**: thử chuyển **một** phần tử tiếp theo cho action và trả true; trả false nếu hết.
- **forEachRemaining(action)**: chuyển lần lượt **toàn bộ phần tử chưa tiêu thụ** cho action.
- **trySplit()**: thử tách một phần dữ liệu **chưa tiêu thụ** thành Spliterator mới, để Spliterator gốc giữ phần còn lại.

Ba phương thức phải nhất quán về trạng thái duyệt. Nếu chúng lặp một phần tử, bỏ sót phần tử, hoặc chia vùng chồng lấn thì Stream dựa trên nguồn đó có thể cho kết quả sai, nhất là khi chạy song song. Bài học trình bày hợp đồng của từng phương thức, kích thước, đặc tính, cách chia, StreamSupport, lỗi thường gặp và một chương trình Java 17+ biên dịch/chạy độc lập.

## 1. Spliterator là gì?

**Spliterator** nằm trong package **java.util**. Tên gọi gợi ý một iterator có khả năng split: ngoài việc đi qua từng phần tử, nó có thể giao một phần công việc cho một Spliterator khác.

So sánh nhanh:

| Thuộc tính | Iterator<T> | Spliterator<T> |
| --- | --- | --- |
| Duyệt lần lượt | hasNext() và next() | tryAdvance(action) |
| Duyệt phần còn lại | forEachRemaining(action) | forEachRemaining(action) |
| Chia nguồn thành phần | Không có phương thức chuẩn | trySplit() |
| Biết số phần tử còn lại | Không có hợp đồng chung | estimateSize() |
| Khai báo đặc tính nguồn | Không có bit flags chuẩn | characteristics() |
| Dùng trong Stream | Có thể chuyển đổi qua adapter | Có thể truyền cho StreamSupport |

Spliterator **không phải Collection**. Nó không hứa lưu toàn bộ dữ liệu, không nhất thiết có reset và không bắt buộc biết chính xác kích thước. Một implementation có thể chỉ đọc từng phần tử theo thứ tự, với **trySplit() trả null**. Điều này vẫn hợp lệ và hữu ích cho luồng tuần tự.

### 1.1. Các chữ ký quan trọng

Với Spliterator<T> tổng quát:

~~~java
boolean tryAdvance(Consumer<? super T> action);
void forEachRemaining(Consumer<? super T> action);
Spliterator<T> trySplit();
long estimateSize();
int characteristics();
~~~

Trong Java có các specialization cho giá trị primitive:

~~~java
Spliterator.OfInt
Spliterator.OfLong
Spliterator.OfDouble
~~~

Với OfInt, thay Consumer<Integer> bằng **IntConsumer**, không cần boxing thành Integer khi phát số:

~~~java
boolean tryAdvance(IntConsumer action);
void forEachRemaining(IntConsumer action);
Spliterator.OfInt trySplit();
~~~

Bài thực hành sẽ dùng Spliterator.OfInt để sinh dãy **[fromInclusive, toExclusive)**, ví dụ [1,9) tức 1,2,3,4,5,6,7,8.

## 2. tryAdvance(): chuyển đúng một phần tử

tryAdvance nhận một action và tìm phần tử kế tiếp:

~~~java
List<String> names = List.of("An", "Binh");

Spliterator<String> sp = names.spliterator();
boolean a = sp.tryAdvance(System.out::println);
boolean b = sp.tryAdvance(System.out::println);
boolean c = sp.tryAdvance(System.out::println);
~~~

Đây là **đoạn minh họa** cần import List và Spliterator trong phương thức. Nó in hai tên, sau đó a và b bằng true, c bằng false.

Hợp đồng:

1. **true** nghĩa có một phần tử được chuyển cho action.
2. **false** nghĩa không có phần tử kế tiếp, không được gọi action với dữ liệu giả.
3. Mỗi lời gọi thành công phát **một phần tử**, không phải cả batch.
4. Khi action là null, phương thức phải xử lý theo hợp đồng, thông thường ném NullPointerException.
5. Nếu action ném exception, exception có thể được truyền lên; không tự giả định có thể retry cùng phần tử một cách an toàn.

### 2.1. Cài đặt với cursor và fence

~~~java
@Override
public boolean tryAdvance(IntConsumer action) {
    Objects.requireNonNull(action);
    if (cursor >= fence) {
        return false;
    }
    action.accept(cursor++);
    return true;
}
~~~

Đây là phương thức trong một class implement Spliterator.OfInt, với cursor chỉ giá trị kế tiếp chưa đọc và fence là cận trên không bao gồm. Khi chưa hết, action nhận đúng một số, cursor tăng một và phương thức trả true.

Nếu cursor bằng fence, không có số còn lại. **Đừng trả true nếu không gọi action** hoặc gọi action hai lần rồi chỉ trả một giá trị true.

### 2.2. Phần đã tiêu thụ không xuất hiện lại

Hình dung dãy:

~~~text
1 2 3 4 5 6 7 8
└───────────────┘
        nguồn
~~~

Sau hai lần tryAdvance:

~~~text
[1 2] | 3 4 5 6 7 8
 đã đọc    phần còn lại
~~~

Spliterator giờ chỉ phụ trách **3..8**. Một lời gọi tiếp theo sẽ lấy 3, không quay lại 1. Nếu cần duyệt lại toàn bộ dãy, tạo Spliterator mới từ một nguồn có thể tái tạo.

## 3. forEachRemaining(): đi hết đoạn còn lại

forEachRemaining(action) xử lý các phần tử chưa đọc cho đến hết, trừ khi action phát sinh exception.

~~~java
Spliterator<String> sp =
    List.of("An", "Binh", "Mai").spliterator();

sp.tryAdvance(System.out::println);       // An
sp.forEachRemaining(System.out::println); // Binh rồi Mai
~~~

Nó tiếp tục từ vị trí hiện tại, không reset về đầu.

Default implementation có thể hình dung bằng:

~~~java
while (tryAdvance(action)) {
    // Tiếp tục tới khi không còn phần tử.
}
~~~

Với Spliterator tùy chỉnh, có thể override để giảm overhead:

~~~java
@Override
public void forEachRemaining(IntConsumer action) {
    Objects.requireNonNull(action);
    while (cursor < fence) {
        action.accept(cursor++);
    }
}
~~~

Override không bắt buộc nếu default method đã đáp ứng nhu cầu. Nhưng nếu tự override, nó phải phát **đúng phần chưa đọc** theo cùng thứ tự/hợp đồng của tryAdvance.

### 3.1. Phân biệt Spliterator và Stream terminal

**Spliterator.forEachRemaining** tiêu thụ phần còn lại của chính Spliterator đó. **Stream.forEach** là một terminal operation của pipeline có thể gồm filter/map. Trong parallel Stream, forEach không hứa giữ encounter order của hành động.

**Stream.forEachOrdered** mới dành cho trường hợp cần giữ encounter order của một ordered pipeline; có thể đi kèm chi phí khác.

Không cho một caller gọi Spliterator.forEachRemaining trong khi Stream khác đang tiêu thụ cùng một Spliterator instance. Hai bên có thể cùng tiến trạng thái của cùng nguồn.

## 4. trySplit(): phân quyền phần việc chưa tiêu thụ

trySplit thử tách **một phần công việc chưa xử lý** và trả Spliterator mới. Spliterator gốc giữ phần còn lại. Nếu không thể chia hoặc không đáng chia, trả **null**.

Ví dụ với dãy 1..8 chưa đọc:

~~~text
Trước khi split:
gốc [1 2 3 4 5 6 7 8]

Sau khi split:
đối tượng trả về [1 2 3 4]
gốc còn lại      [5 6 7 8]
~~~

Với một nguồn **ORDERED**, Spliterator được trả về phải đại diện cho **prefix** của phần chưa duyệt. Với dãy đã đọc 1,2, phần còn lại là 3..8:

~~~text
đã đọc           [1 2]
đối tượng trả về [3 4 5]
gốc còn lại      [6 7 8]
~~~

Hai đối tượng mới phải có trách nhiệm **không chồng lấn**. Split không phải là nhân đôi nguồn, không tự tạo thread và cũng không tự gọi consumer.

### 4.1. Thuật toán chia khoảng

Giả sử RangeSpliterator giữ cursor và fence:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = (long) fence - cursor;
    if (remaining <= 1) {
        return null;
    }

    int low = cursor;
    int middle = (int) (low + remaining / 2);
    cursor = middle;
    return new RangeSpliterator(low, middle);
}
~~~

Nếu vùng ban đầu là **[low, fence)** thì sau split:

- Spliterator mới phụ trách **[low, middle)**.
- Spliterator gốc có cursor mới middle, phụ trách **[middle, fence)**.
- Không có khoảng bị bỏ sót hoặc chồng lấn.
- Khi số phần tử còn lại không quá một, trả null.

**Tính chênh lệch bằng long** trước khi lấy điểm giữa tránh overflow khi hai đầu mút int ở xa nhau. Dùng trực tiếp phép cộng hai cận dưới kiểu int có thể tràn, khiến chia sai.

### 4.2. Điểm dừng của splitting

Nếu một Spliterator trả một phần mới nhưng không làm giảm công việc của gốc, hệ thống có thể split mãi hoặc phát lặp phần tử. Với khoảng số hữu hạn, cách chia đôi thường đảm bảo các đoạn nhỏ dần cho đến khi chỉ còn 0 hoặc 1 phần tử.

Không có quy tắc mọi Spliterator phải chia đôi. Một nguồn cây, mảng, danh sách liên kết hoặc file có thể yêu cầu chiến lược khác. Nhưng **mọi lần chia thành công phải bảo toàn tập phần tử chưa tiêu thụ**.

## 5. estimateSize và kích thước còn lại

Spliterator.estimateSize() trả **long** là ước lượng số phần tử chưa đọc, hoặc một giá trị upper bound phù hợp. Nó không nhất thiết là số phần tử ban đầu.

Với RangeSpliterator:

~~~java
@Override
public long estimateSize() {
    return (long) fence - cursor;
}
~~~

Nếu vùng [1,9) có 8 số, sau hai lần tryAdvance chỉ còn 6. Split chia đôi thì prefix và gốc đều còn 3.

### 5.1. SIZED

Characteristic **SIZED** là một lời hứa rằng estimateSize cung cấp kích thước chính xác theo hợp đồng. Đừng khai báo SIZED cho nguồn mà số phần tử phụ thuộc vào dữ liệu chưa đọc hoặc thay đổi không dự đoán được.

Java có phương thức **getExactSizeIfKnown()**. Với Spliterator có SIZED, nó trả kích thước chính xác được công bố; nếu không có SIZED, trả -1.

### 5.2. SUBSIZED

**SUBSIZED** hứa rằng các Spliterator sinh ra bằng trySplit đều có SIZED và SUBSIZED thích hợp. RangeSpliterator biết chính xác số giá trị của mọi đoạn [start,end) nên thỏa cả hai.

Nếu split trên một cursor I/O chưa biết được số lượng dữ liệu mỗi phần, không nên khai báo SUBSIZED chỉ để Stream có vẻ “tối ưu hơn”.

### 5.3. Tránh overflow khi tính size

Sai ý định với khoảng int cực rộng:

~~~java
// Có thể overflow trước khi chuyển sang long.
return (long) (fence - cursor);
~~~

Đúng:

~~~java
return (long) fence - cursor;
~~~

Phép ép kiểu phải xảy ra **trước phép trừ** để kết quả chênh lệch nằm trong phạm vi long.

## 6. characteristics(): metadata của nguồn

Spliterator dùng **bit flags** để công bố đặc tính. Thông tin này có thể được Stream runtime sử dụng để tối ưu, nên phải trung thực.

| Flag | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| ORDERED | Có encounter order xác định | trySplit của nguồn ORDERED trả prefix |
| DISTINCT | Không có phần tử trùng theo hợp đồng | Chỉ dùng khi thực sự bảo đảm |
| SORTED | Phần tử đã có thứ tự sắp xếp | Cần hợp đồng getComparator phù hợp |
| SIZED | Biết chính xác kích thước theo hợp đồng | estimateSize phải đáng tin |
| SUBSIZED | Những phần tách cũng SIZED và SUBSIZED | Không tự suy ra từ SIZED |
| NONNULL | Phần tử không null | Hợp lý với primitive elements |
| IMMUTABLE | Nguồn không bị sửa cấu trúc trong quá trình duyệt | Không có nghĩa cursor là final |
| CONCURRENT | Nguồn cho phép sửa đổi đồng thời theo hợp đồng | Không phải lệnh bật parallel |

Ví dụ trong RangeSpliterator:

~~~java
@Override
public int characteristics() {
    return ORDERED | SIZED | SUBSIZED |
        IMMUTABLE | NONNULL | DISTINCT;
}
~~~

**ORDERED** vì số được phát tăng dần; **DISTINCT** vì không lặp số; **SIZED/SUBSIZED** vì có cận; **NONNULL** vì int nguyên thủy; **IMMUTABLE** vì nguồn là quy tắc sinh số từ hai cận cố định.

### 6.1. IMMUTABLE khác bất biến của cursor

Spliterator vẫn có cursor mutable để tiến qua các phần tử. Cờ IMMUTABLE nói về **cấu trúc nguồn** không thay đổi trong vòng đời duyệt, không phải mọi field của chính đối tượng duyệt đều final.

Đừng khai báo IMMUTABLE cho một Spliterator trỏ vào ArrayList mutable được sửa đồng thời mà không có cơ chế đảm bảo hợp đồng nguồn.

### 6.2. SORTED và getComparator

Nếu khai báo SORTED, getComparator phải tuân thủ hợp đồng của thứ tự: có thể trả **null** cho natural ordering hoặc Comparator phù hợp cho thứ tự khác. Nếu không có SORTED, getComparator mặc định có thể ném IllegalStateException.

Trong chương trình chính, chúng ta **không khai báo SORTED**, dù dãy số thực tế tăng dần, để tập trung vào ba phương thức duyệt/tách và tránh bổ sung một hợp đồng không được minh họa.

### 6.3. hasCharacteristics

~~~java
boolean correctFlags = source.hasCharacteristics(
    Spliterator.SIZED | Spliterator.SUBSIZED);
~~~

Kết quả true khi **tất cả cờ yêu cầu đều có**, không phải chỉ cần một cờ bất kỳ.

### 6.4. CONCURRENT không có nghĩa parallel

Một Spliterator có thể chia và chạy trong parallel stream **mà không có CONCURRENT**. CONCURRENT dành cho nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng. Parallelism được quyết định ở Stream API; không khai báo flag này cho nguồn không có khả năng phù hợp.

## 7. StreamSupport nối nguồn tùy chỉnh với Stream API

Với Spliterator<T>:

~~~java
Stream<String> stream =
    StreamSupport.stream(customSpliterator, false);
~~~

Đây là đoạn minh họa, customSpliterator cần được định nghĩa trước và hỗ trợ các phần tử String. Tham số **false** yêu cầu chế độ sequential.

Với Spliterator.OfInt, dùng primitive specialization:

~~~java
IntStream stream = StreamSupport.intStream(
    new RangeSpliterator(1, 9), false);
~~~

**true** ở tham số thứ hai yêu cầu chế độ parallel:

~~~java
int sum = StreamSupport.intStream(
    new RangeSpliterator(1, 9), false
).sum();

int squares = StreamSupport.intStream(
    new RangeSpliterator(1, 9), true
).map(n -> n * n).sum();
~~~

Kết quả lần lượt là 36 và 204. Hai phép tính dùng **hai instance Spliterator mới**, vì một Spliterator đã tiêu thụ không được xem như nguồn có thể reset tùy ý.

### 7.1. Parallel stream không tự bảo đảm nhanh hơn

**parallel=true** cho phép Stream runtime phân công xử lý song song khi thích hợp; không bảo đảm số thread cụ thể hoặc tốc độ tốt hơn. Với chỉ tám số, overhead phân chia và gom kết quả có thể lớn hơn lợi ích.

Một Spliterator không tách được (trySplit luôn trả null) vẫn dùng được như nguồn sequential, nhưng có thể hạn chế khả năng khai thác parallelism.

### 7.2. Không tự tạo thread trong trySplit

trySplit chỉ tạo một vùng dữ liệu mới. **Stream runtime điều phối task**. Nếu tự tạo thread trong mỗi trySplit mà không có thiết kế rõ, bạn có thể thêm quá nhiều thread, thay đổi hợp đồng dữ liệu và gây lỗi vòng đời tài nguyên.

## 8. Ordered source, ordered results và callback order

ORDERED mô tả encounter order của phần tử. Với RangeSpliterator, đó là thứ tự tăng dần từ cursor tới fence.

Tuy nhiên, parallel Stream **forEach** không bắt buộc gọi action theo thứ tự nguồn. Nếu cần action được quan sát đúng encounter order, dùng **forEachOrdered** trên ordered pipeline và lưu ý hiệu năng.

Ngược lại, các phép tổng hợp có tính kết hợp thích hợp như tổng các số nguyên nhỏ có thể cho kết quả như nhau không phụ thuộc lịch task. Vì vậy chương trình ví dụ dùng **sum()**, không dùng nhiều thread in trực tiếp ra stdout.

### 8.1. Không chia lại phần đã đọc

Nếu source đã tryAdvance hai lần rồi split, prefix được trả phải bắt đầu từ phần tử thứ ba. Giao lại phần tử cũ cho prefix sẽ làm xuất hiện dữ liệu lặp. Tương tự, nguồn gốc sau khi split chỉ được giữ suffix, không được đồng thời phát prefix.

### 8.2. Không gọi cùng một Spliterator đồng thời tùy tiện

Spliterator với cursor mutable không mặc định thread-safe khi hai thread cùng gọi tryAdvance trên **chính một instance**. Mô hình parallel đúng là **split thành các đối tượng có vùng riêng** và để runtime xử lý.

Đừng chia sẻ cùng RangeSpliterator cho một vòng forEachRemaining tự viết và một Stream đang chạy, bởi hai bên sẽ tranh chấp trạng thái duyệt.

## 9. Spliterator của nguồn mutable và I/O

Một Spliterator tự viết có thể lấy dữ liệu từ array, List, tree, buffer, file hoặc generator. Các nguồn này có hợp đồng rất khác nhau.

Với một List mutable, việc sửa cấu trúc khi đang duyệt có thể vi phạm non-interference hoặc dẫn đến ConcurrentModificationException tùy implementation. Đừng tuyên bố **IMMUTABLE** hay **CONCURRENT** nếu nguồn không thực sự đáp ứng.

Với file hoặc socket, Spliterator có thể cần đọc theo nhu cầu; việc chia file thành vùng độc lập có thể khó vì newline, encoding, quyền truy cập và trạng thái I/O. Trong trường hợp không thể tách an toàn, **trySplit trả null** là lựa chọn chính xác.

### 9.1. Quản lý tài nguyên

Spliterator interface tự nó **không có hợp đồng close chung**. Nếu nó giữ file descriptor/socket, API tạo Stream phải làm rõ ai đóng nguồn và khi nào. Có thể cung cấp Stream với **onClose** liên kết đến cleanup và yêu cầu caller dùng **try-with-resources**, hoặc thiết kế một wrapper quản lý vòng đời rõ ràng.

Terminal operation không nên được mặc định là tự động đóng mọi tài nguyên của custom source. Không để một Stream I/O-backed tồn tại ngoài vòng đời của file mà nó phụ thuộc.

### 9.2. Late binding và đặc tính nguồn

Một số Spliterator gắn với nguồn muộn hơn thời điểm được tạo; một số khác gắn sớm. Điều này ảnh hưởng cách nguồn phản ánh mutation, tính sized và fail-fast.

Không tự suy luận rằng vì Stream xử lý các intermediate operations lazily nên việc mở tài nguyên I/O hoặc binding nguồn nhất thiết cũng lazy. Đó là hai cơ chế khác nhau.

## 10. Chương trình Java 17+ hoàn chỉnh

Chương trình **CustomSpliteratorDemo.java** tự cài đặt OfInt sinh dãy số nguyên không cần mảng lưu sẵn. Nó dùng cursor/fence để bảo đảm split không chồng lấn. Tất cả giá trị in ra đều ổn định và đã được kiểm chứng trong thử nghiệm Java 17; biến thể midpoint bằng long cũng đã được kiểm tra với cận int rất rộng.

Tạo file **CustomSpliteratorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomSpliteratorDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int fromInclusive, int toExclusive) {
            if (fromInclusive > toExclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.cursor = fromInclusive;
            this.fence = toExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (cursor >= fence) return false;
            action.accept(cursor++);
            return true;
        }

        @Override
        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action);
            while (cursor < fence) {
                action.accept(cursor++);
            }
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = (long) fence - cursor;
            if (remaining <= 1) return null;
            int low = cursor;
            int middle = (int) (low + remaining / 2);
            cursor = middle;
            return new RangeSpliterator(low, middle);
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED |
                IMMUTABLE | NONNULL | DISTINCT;
        }
    }

    public static void main(String[] args) {
        RangeSpliterator source = new RangeSpliterator(1, 9);
        List<Integer> visited = new ArrayList<>();
        boolean first = source.tryAdvance((int n) -> visited.add(n));
        boolean second = source.tryAdvance((int n) -> visited.add(n));
        System.out.println("advanced=" + visited);
        System.out.println("advancedFlags=" + first + "," + second);
        System.out.println("remainingSize=" + source.estimateSize());

        Spliterator.OfInt prefix = source.trySplit();
        System.out.println("splitSizes=" + prefix.estimateSize()
            + "," + source.estimateSize());
        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining((int n) -> left.add(n));
        source.forEachRemaining((int n) -> right.add(n));
        System.out.println("prefix=" + left);
        System.out.println("remainder=" + right);
        System.out.println("exhausted=" +
            source.tryAdvance((int n) -> right.add(n)));

        System.out.println("sizeFlags=" +
            source.hasCharacteristics(Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("emptySplit=" +
            (new RangeSpliterator(5, 5).trySplit() == null));

        int sequentialSum = StreamSupport.intStream(
            new RangeSpliterator(1, 9), false).sum();
        int parallelSquares = StreamSupport.intStream(
            new RangeSpliterator(1, 9), true)
                .map(n -> n * n).sum();
        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSquares=" + parallelSquares);
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac CustomSpliteratorDemo.java
java CustomSpliteratorDemo
~~~

**Stdout chính xác:**

~~~text
advanced=[1, 2]
advancedFlags=true,true
remainingSize=6
splitSizes=3,3
prefix=[3, 4, 5]
remainder=[6, 7, 8]
exhausted=false
sizeFlags=true
emptySplit=true
sequentialSum=36
parallelSquares=204
~~~

### 10.1. Giải thích các kết quả

**advanced=[1, 2]**: hai lần tryAdvance phát đúng hai số, không phát toàn bộ dãy.

**advancedFlags=true,true**: còn phần tử nên cả hai lần đều thành công.

**remainingSize=6**: dãy ban đầu [1,9) có tám số; đã lấy hai nên còn sáu.

**splitSizes=3,3**: chia sáu giá trị chưa đọc thành prefix [3,6) và remainder [6,9). Mỗi phần còn ba số.

**prefix=[3,4,5] và remainder=[6,7,8]**: forEachRemaining tiêu thụ hai phần độc lập, không trùng và không bỏ sót.

**exhausted=false**: sau khi đã duyệt hết phần gốc, không còn số tiếp theo.

**sizeFlags=true**: Spliterator công bố cả SIZED và SUBSIZED đúng hợp đồng.

**emptySplit=true**: nguồn [5,5) rỗng nên trySplit không trả một vùng mới.

**sequentialSum=36**: tổng 1+2+3+4+5+6+7+8.

**parallelSquares=204**: tổng bình phương 1²+2²+3²+4²+5²+6²+7²+8². Chương trình không cần giả định thứ tự các thread để xác định kết quả.

### 10.2. Kiểm tra midpoint với khoảng số rộng

Bản cài đặt dùng **long remaining** để tính midpoint và estimateSize. Khi khoảng trải từ Integer.MIN_VALUE tới Integer.MAX_VALUE với cận trên không bao gồm, tổng số phần tử là **4.294.967.295** (nằm trong long).

Với phép chia đôi trong ví dụ mở rộng đã kiểm thử, kích thước hai phần là **2.147.483.647** và **2.147.483.648**, tổng vẫn chính xác. Không nên thật sự thu toàn bộ khoảng này thành List chỉ để thử: số lượng phần tử quá lớn. Có thể kiểm tra tính toán kích thước và chia khoảng mà không duyệt toàn bộ.

## 11. Sai lầm phổ biến

**Sai lầm 1 — tryAdvance trả true nhưng không gọi action.** Caller tưởng phần tử được xử lý dù thực tế không có dữ liệu; phá hợp đồng tiến trình.

**Sai lầm 2 — tryAdvance gọi action nhiều lần cho một lần true.** Dùng forEachRemaining khi muốn duyệt cả đoạn; tryAdvance chỉ một phần tử.

**Sai lầm 3 — forEachRemaining bắt đầu lại từ điểm gốc.** Sau khi đã lấy một số phần tử, nó phải tiếp tục từ cursor hiện hành, nếu không sẽ lặp dữ liệu.

**Sai lầm 4 — trySplit trả bản sao toàn bộ vùng chưa đọc mà không thay đổi gốc.** Hai Spliterator sẽ phát trùng phần tử. Split là phân quyền, không phải nhân đôi.

**Sai lầm 5 — chia lệch cận.** Với khoảng [low,middle) và [middle,fence), không được bỏ middle hoặc cho cả hai cùng chứa middle.

**Sai lầm 6 — trySplit không có điều kiện dừng.** Khi còn 0 hoặc 1 phần tử, thường nên trả null; tránh chia vô hạn hoặc tạo vô số phần trống.

**Sai lầm 7 — estimateSize không đổi khi đã tiêu thụ dữ liệu.** Khi khai báo SIZED, con số phải phù hợp với lượng chưa đọc tại thời điểm theo hợp đồng.

**Sai lầm 8 — khai báo SUBSIZED không đúng.** Mọi split con phải duy trì size chính xác, không chỉ source gốc.

**Sai lầm 9 — tính midpoint bằng phép cộng int có thể overflow.** Dùng long cho chênh lệch và cận nếu phạm vi rất rộng.

**Sai lầm 10 — đánh dấu SORTED mà không bảo đảm comparator và getComparator.** Characteristic sai có thể khiến runtime tối ưu trên giả định không đúng.

**Sai lầm 11 — đánh dấu CONCURRENT để bật parallelism.** CONCURRENT nói về tính chất nguồn, không phải số thread.

**Sai lầm 12 — cho hai thread gọi tryAdvance trên cùng instance mà không có hợp đồng thread-safe.** Cursor mutable có thể race; hãy split và giao từng vùng riêng.

**Sai lầm 13 — lấy một Spliterator vừa duyệt thủ công rồi mong Stream đọc lại từ đầu.** Nó tiếp tục từ vị trí chưa xử lý, không tự reset.

**Sai lầm 14 — dùng trySplit trên nguồn I/O không thể chia an toàn.** Trả null có thể đúng hơn việc tự chia sai ranh giới dữ liệu.

**Sai lầm 15 — quên đóng file/socket của custom source.** Spliterator không tự có close chung; cần thiết kế vòng đời tài nguyên cho Stream/owner.

**Sai lầm 16 — coi parallel luôn nhanh hơn.** Với vài giá trị và phép tính rẻ, chi phí điều phối có thể lớn hơn lợi ích.

## 12. Checklist kiểm thử nguồn Spliterator

- **Nguồn rỗng**: tryAdvance false, estimateSize bằng 0 nếu SIZED, trySplit null, forEachRemaining không gọi action.
- **Một phần tử**: tryAdvance true đúng một lần rồi false; trySplit không tạo vùng trống vô ích.
- **Sau khi đã duyệt một phần**: forEachRemaining tiếp tục từ phần còn lại.
- **Sau khi split**: hai phần không lặp, không thiếu; với ORDERED, phần trả về là prefix.
- **Split đệ quy**: kích thước các phần giảm tới điểm dừng, kết quả ghép vẫn đầy đủ.
- **SIZED/SUBSIZED**: kích thước công bố đúng trước/sau khi split và duyệt.
- **Cận lớn**: không overflow khi tính midpoint/estimateSize.
- **Sequential vs parallel**: hai nguồn mới với cùng dữ liệu cho kết quả ngữ nghĩa như nhau ở phép tổng hợp phù hợp.
- **Action lỗi hoặc null**: xử lý đúng hợp đồng; không tưởng mọi action có thể retry.
- **Nguồn mutable/I/O**: đánh dấu characteristics trung thực và quản lý tài nguyên đúng.

### 12.1. Test splitting không cần parallel

Có thể tự tạo một Spliterator, gọi trySplit, thu prefix và suffix vào hai List, ghép chúng, rồi so sánh với một danh sách kỳ vọng.

Nếu đã đọc hai phần tử của [1,9), kết quả hai phần sau split ghép lại phải là [3,4,5,6,7,8], **không phải** toàn bộ [1,2,3,4,5,6,7,8]. Cách này tái hiện lỗi thiếu/lặp chính xác hơn việc đợi một parallel stream có lịch chạy không xác định.

## 13. Khi nào chọn nguồn tùy chỉnh?

Không phải lúc nào cũng cần tự viết Spliterator. Với Collection hoặc array, **collection.stream()** và các API Stream/Arrays có sẵn thường đơn giản hơn. Tự viết Spliterator khi nguồn **có cách sinh dữ liệu hoặc cách chia tự nhiên riêng**:

- Một dãy số, đoạn chỉ số hoặc một vùng trong array/buffer.
- Cấu trúc cây có các nhánh có thể duyệt độc lập.
- Một nguồn paginated với hợp đồng chia phạm vi rõ ràng.
- Một API đặc thù cung cấp cursor nhưng không có Stream sẵn.
- Một nguồn dữ liệu đắt cần kiểm soát kích thước, thứ tự hoặc vòng đời tài nguyên.

Hãy chọn cấu trúc đơn giản nhất giữ đúng ngữ nghĩa. **Độ phức tạp của Spliterator tùy chỉnh chỉ đáng giá khi nó giải quyết một yêu cầu thực tế về nguồn dữ liệu, không chỉ để viết lại chức năng JDK đã có.**

## 14. Câu hỏi tự kiểm tra

1. tryAdvance và forEachRemaining khác nhau thế nào về số phần tử được chuyển cho action?
2. Sau hai lần tryAdvance từ [1,9), estimateSize còn bao nhiêu và phần tử tiếp theo là gì?
3. Khi một Spliterator có ORDERED, trySplit phải trả phần nào so với vùng chưa duyệt?
4. Vì sao trySplit không được để cả prefix và gốc cùng phát một số?
5. Tại sao trySplit được phép trả null dù nguồn chưa hoàn toàn rỗng?
6. SIZED và SUBSIZED có cùng một nghĩa không?
7. Nếu estimateSize trả số sai, Stream có thể gặp hậu quả gì?
8. Vì sao IMMUTABLE của nguồn không đòi cursor phải final?
9. CONCURRENT khác parallel ở đâu?
10. Vì sao không nên tự tạo thread trong trySplit?
11. Nếu yêu cầu in theo thứ tự nguồn, parallelStream.forEach có bảo đảm không?
12. Khi nào nên chọn Spliterator.OfInt thay vì Spliterator<Integer>?
13. Làm cách nào dùng StreamSupport.intStream để xử lý dãy số từ Spliterator?
14. Vì sao cần tạo Spliterator mới nếu muốn tính cả sum và max?
15. Với nguồn I/O, ai có trách nhiệm đóng tài nguyên?
16. Vì sao lấy midpoint bằng phép cộng hai int có thể lỗi?
17. Cách kiểm thử splitting bằng List giúp phát hiện mất/lặp dữ liệu ra sao?
18. Với một nguồn chỉ tiến theo cursor không chia được, có phải đó là Spliterator sai không?

**Kết luận:** **tryAdvance()** duyệt từng phần tử, **forEachRemaining()** duyệt hết phần chưa đọc, còn **trySplit()** chia một phần việc chưa đọc thành vùng độc lập. Các phương thức phải nhất quán về trạng thái và không làm mất/lặp dữ liệu. **estimateSize() và characteristics()** mô tả nguồn trung thực để Stream runtime xử lý đúng; **StreamSupport** biến nguồn tùy chỉnh thành pipeline tuần tự hoặc song song. Khi thiết kế Spliterator, correctness của việc duyệt và chia luôn quan trọng hơn việc cố bật parallel.