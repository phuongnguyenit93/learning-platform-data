# CopyOnWriteArrayList: ưu và nhược điểm khi ghi nhiều

## 1. Bài toán cần giải quyết

`CopyOnWriteArrayList<E>` thuộc `java.util.concurrent`, triển khai giao diện `List<E>` theo chiến lược **copy-on-write**: khi cần thay đổi cấu trúc hoặc phần tử của danh sách, thao tác cập nhật thường tạo một mảng nền mới rồi công bố mảng mới cho các luồng đọc. Trong khi đó, luồng đọc có thể truy cập mảng hiện tại mà không phải khóa danh sách cho mỗi lần đọc.

Đây là lựa chọn tốt khi **số lần đọc/duyệt vượt xa số lần sửa**, ví dụ danh sách listener hoặc cấu hình ít thay đổi. Ngược lại, nếu thêm, xóa, thay thế phần tử liên tục, việc sao chép mảng, cấp phát bộ nhớ và tranh chấp giữa các luồng ghi có thể khiến nó đắt hơn nhiều lựa chọn khác.

Mục tiêu bài học: hiểu tính nhất quán của đọc/duyệt, thấy chi phí thực sự của mỗi lần ghi, và biết khi nào nên dùng hoặc thay thế `CopyOnWriteArrayList`. Phạm vi là Java concurrency nói chung.

## 2. Cơ chế hoạt động

Giả sử mảng nền ban đầu là `[A, B, C]`:

1. Một luồng đọc gọi `iterator()`, iterator giữ tham chiếu đến **mảng tại thời điểm tạo iterator**.
2. Luồng ghi gọi `add(D)`. Nó đồng bộ thao tác ghi, cấp phát một mảng mới, sao chép các tham chiếu phần tử từ mảng cũ và thêm `D`.
3. Luồng ghi công bố mảng `[A, B, C, D]`. Những lời gọi đọc mới có thể thấy trạng thái đã được công bố.
4. Iterator cũ tiếp tục đi qua `[A, B, C]`. Nó không thấy `D`, không bị thay đổi giữa lúc duyệt và không ném `ConcurrentModificationException` do danh sách bị sửa song song.

`CopyOnWriteArrayList` dùng cơ chế công bố mảng có bảo đảm hiển thị giữa các luồng; những thao tác sửa trên cùng danh sách được phối hợp để không làm mất cập nhật. Trong cách triển khai JDK 17, luồng ghi sử dụng một khóa nội bộ, còn các thao tác đọc thông thường lấy trạng thái mảng đã công bố. Không hiểu nhầm rằng mọi thao tác cấp cao gồm **nhiều lời gọi riêng biệt** đều tự động trở thành một giao dịch nguyên tử.

**Snapshot ở đây là snapshot của mảng tham chiếu**, không phải bản sao sâu của từng object. Nếu phần tử là object có thể thay đổi, một luồng sửa trực tiếp trường của object vẫn có thể ảnh hưởng đến dữ liệu mà iterator cũ nhìn thấy; thread safety của object đó cần được đảm bảo riêng.

## 3. Chi phí đọc và ghi

| Thao tác | Đặc điểm/chi phí điển hình | Ý nghĩa |
| --- | --- | --- |
| `get(index)` | O(1), không sao chép toàn mảng | Phù hợp với đọc theo chỉ số. |
| `iterator()` rồi duyệt | Tạo iterator O(1), duyệt n phần tử O(n) | Một lần duyệt thấy một ảnh chụp ổn định của các tham chiếu phần tử. |
| `add(element)`, `add(index, element)` | O(n) để tạo mảng mới và sao chép tham chiếu | Danh sách càng lớn, mỗi lần thêm càng tốn chi phí. |
| `remove(index)` hoặc xóa phần tử tồn tại | Thường O(n) để tìm/dịch và tạo mảng mới | Xóa từng phần tử nhiều lần dễ sinh nhiều mảng trung gian. |
| `set(index, value)` | Thường O(n) khi cần thay phần tử trong mảng mới | Không coi `set` như cập nhật O(1) kiểu `ArrayList`. |
| `contains(value)` | O(n) tìm tuyến tính | Không nên dùng để kiểm tra thành viên với tần suất rất cao trên danh sách lớn. |
| `addIfAbsent(value)` | Tìm phần tử và, nếu thiếu, thêm theo cơ chế an toàn cho luồng; thường O(n) | Tránh lỗi cạnh tranh của cặp `contains` + `add` nhưng không giải quyết chi phí sao chép. |

Các độ phức tạp trên diễn tả chi phí phổ biến của những thao tác thực sự làm thay đổi dữ liệu, không khẳng định mọi nhánh triển khai đều sao chép mảng (ví dụ xóa phần tử không tồn tại có thể không tạo mảng mới). Những phép cập nhật hàng loạt như `addAll`, `removeIf` hoặc `clear` có hành vi và chi phí riêng; khi có thể, gom thay đổi hợp lý thường tốt hơn gọi `add`/`remove` từng phần tử.

**Vì sao ghi nhiều rất đắt?** Với n phần tử, mỗi lần thêm thành công thường phải sao chép khoảng n tham chiếu. Nếu có m thao tác thêm độc lập ở kích thước gần n, lượng công việc sao chép xấp xỉ O(m × n), chưa kể đồng bộ, cấp phát và dọn rác. Nếu thêm lần lượt n phần tử vào danh sách ban đầu rỗng bằng n lời gọi `add`, tổng số tham chiếu được sao chép có bậc O(n²).

Ví dụ ước lượng: một mảng chứa 100.000 tham chiếu có phần tham chiếu khoảng 0,4 MB nếu JVM dùng tham chiếu 4 byte, hoặc 0,8 MB nếu dùng 8 byte, chưa tính header/căn chỉnh. Một nghìn lần cập nhật thành công mỗi giây ở quy mô đó có thể tạo ra hàng trăm MB phân bổ mảng mỗi giây. Đây là **ước lượng minh họa theo cấu hình JVM**, không phải kết quả benchmark hay dự đoán độ trễ cụ thể. Các object phần tử không bị clone sâu; cái được sao chép chủ yếu là các tham chiếu.

## 4. Ưu điểm trong bài toán đọc nhiều, ghi ít

- **Đọc ít tranh chấp với ghi:** các thao tác đọc thông thường không cần giữ khóa ghi; luồng khác có thể công bố phiên bản mảng mới trong lúc một iterator cũ đang duyệt.
- **Iterator ổn định:** không cần bọc toàn bộ vòng lặp trong `synchronized` chỉ để chống danh sách bị sửa đồng thời; iterator không gặp `ConcurrentModificationException` do thay đổi cấu trúc của danh sách.
- **Thứ tự và API `List`:** giữ thứ tự chèn và hỗ trợ truy cập theo index, hữu ích khi thứ tự listener có ý nghĩa.
- **Đơn giản cho danh sách đăng ký ít đổi:** listener, callback, handler, cấu hình chỉ thỉnh thoảng được bổ sung/xóa nhưng đọc rất thường xuyên.
- **Một số thao tác tiện ích cho cạnh tranh:** `addIfAbsent` và `addAllAbsent` giúp thêm phần tử chưa tồn tại mà không cần tự ghép kiểm tra và cập nhật thành hai lời gọi tách rời.

Các lợi ích này chỉ bù được chi phí ghi khi workload phù hợp. “Thread-safe” không đồng nghĩa với “nhanh trong mọi tình huống đa luồng”.

## 5. Nhược điểm khi ghi nhiều

### 5.1. Sao chép O(n) cho nhiều cập nhật

Giả sử danh sách có 50.000 listener và mỗi event lại thêm/xóa nhiều listener. Các thao tác ghi có thể liên tiếp sao chép mảng tham chiếu lớn. Kích thước càng tăng, tổng chi phí CPU và băng thông bộ nhớ càng đáng kể. Đặc biệt không nên dùng `CopyOnWriteArrayList` làm một danh sách công việc mà các luồng liên tục `add`/`remove` như queue.

### 5.2. Cấp phát và áp lực garbage collection

Các phiên bản mảng cũ trở thành đối tượng có thể thu gom khi không còn ai giữ tham chiếu. Tuy nhiên iterator snapshot đang sống có thể **giữ mảng cũ lâu hơn**, nên nhiều iterator lâu sống cùng với cập nhật liên tục làm tăng lượng bộ nhớ tồn tại đồng thời. Thông lượng cấp phát cao có thể kéo theo nhiều lần GC và biến động độ trễ.

### 5.3. Tranh chấp giữa các writer

Nhiều luồng có thể đọc thuận tiện, nhưng các thao tác sửa vẫn phải phối hợp/tuần tự hóa đối với cùng danh sách. Nếu các writer hoạt động dày đặc, chúng cạnh tranh nhau trong phần công việc ghi vốn đã có sao chép O(n); tăng số writer không bảo đảm tăng thông lượng.

### 5.4. Iterator không thấy thay đổi mới

Iterator tạo trước khi thêm/xóa vẫn thấy snapshot cũ. Điều này là ưu điểm cho việc duyệt nhất quán, nhưng không phù hợp nếu thuật toán yêu cầu một vòng lặp **ngay lập tức quan sát** dữ liệu vừa thay đổi. Mỗi lần gọi `iterator()` mới lấy một snapshot tại thời điểm riêng; không có lời hứa tất cả các vòng lặp chạy song song nhìn thấy cùng trạng thái.

### 5.5. Không sửa trực tiếp qua iterator

`Iterator.remove()` và `ListIterator.remove()`, `ListIterator.set()`, `ListIterator.add()` không được hỗ trợ; chúng ném `UnsupportedOperationException`. Nếu cần xóa, hãy thao tác qua chính danh sách, ví dụ `removeIf(predicate)`; iterator đã tạo trước đó vẫn duyệt snapshot cũ.

### 5.6. Đừng nhầm an toàn của danh sách với an toàn của từng phần tử

`CopyOnWriteArrayList<Account>` bảo vệ cấu trúc danh sách; nó không tự làm cho phép cộng trừ trên `Account.balance` an toàn. Tương tự, mã kiểu `if (!list.contains(x)) list.add(x);` gồm hai lời gọi riêng, có thể bị luồng khác xen vào. Với mục đích thêm nếu vắng mặt, dùng `addIfAbsent(x)`; với các quy tắc nghiệp vụ nhiều bước, cần thiết kế đồng bộ/phối hợp thích hợp ở cấp nghiệp vụ.

## 6. Ví dụ Java 17+: snapshot và thao tác thêm an toàn

Tạo tệp `CowSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CowSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("An", "Bình"));

        Iterator<String> beforeAdd = names.iterator();
        names.add("Chi");

        List<String> snapshot = new ArrayList<>();
        beforeAdd.forEachRemaining(snapshot::add);

        System.out.println("Snapshot: " + snapshot);
        System.out.println("Current : " + names);
        System.out.println("Add Chi again: " + names.addIfAbsent("Chi"));
        System.out.println("Add Dũng: " + names.addIfAbsent("Dũng"));
        System.out.println("Final   : " + names);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CowSnapshotDemo.java
java CowSnapshotDemo
```

Kết quả xác định:

```text
Snapshot: [An, Bình]
Current : [An, Bình, Chi]
Add Chi again: false
Add Dũng: true
Final   : [An, Bình, Chi, Dũng]
```

Iterator `beforeAdd` giữ mảng trước khi thêm `Chi`. Lời gọi `names.add("Chi")` cập nhật danh sách nhưng không thay ảnh chụp đó. `addIfAbsent("Chi")` trả `false` vì `Chi` đã tồn tại; `addIfAbsent("Dũng")` thêm mới và trả `true`.

## 7. Ví dụ nhiều luồng: dùng addIfAbsent thay cho contains + add

Tạo tệp `CowConcurrentDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CowConcurrentDemo {
    public static void main(String[] args) throws Exception {
        CopyOnWriteArrayList<String> jobs =
                new CopyOnWriteArrayList<>(List.of("seed"));
        int writers = 4;
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(writers);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < writers; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    jobs.addIfAbsent("job-42");
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> future : futures) {
                future.get();
            }
        } finally {
            pool.shutdown();
        }

        long count = jobs.stream().filter("job-42"::equals).count();
        System.out.println("Count: " + count);
        System.out.println("Jobs : " + jobs);
    }
}
```

```bash
javac -encoding UTF-8 CowConcurrentDemo.java
java CowConcurrentDemo
```

```text
Count: 1
Jobs : [seed, job-42]
```

Cả bốn worker được mở cổng bằng `CountDownLatch` rồi cùng thử thêm cùng một giá trị. `addIfAbsent` bảo đảm thao tác “kiểm tra và thêm nếu vắng mặt” không tạo bốn bản sao phần tử trên danh sách này. Giá trị trả về chỉ phản ánh worker nào thêm được; kết quả cuối có đúng một `job-42`. Trường hợp dùng `if (!jobs.contains("job-42")) jobs.add("job-42");` sẽ có nguy cơ hai worker cùng thấy “chưa có” rồi cùng thêm. Dù tránh trùng lặp bằng `addIfAbsent`, nếu nhiều giá trị khác nhau liên tục được thêm vào danh sách lớn thì chi phí copy-on-write vẫn còn.

## 8. Chọn cấu trúc khác khi workload đổi

| Nhu cầu thực tế | Lựa chọn cân nhắc | Điều phải chú ý |
| --- | --- | --- |
| Danh sách listener nhỏ/vừa, gần như chỉ đọc | `CopyOnWriteArrayList` | Thích hợp nhất khi duyệt áp đảo cập nhật và chấp nhận snapshot. |
| Danh sách cần thêm/xóa liên tục, có truy cập theo index | `ArrayList` được bảo vệ bởi `synchronized` hoặc `ReentrantReadWriteLock` | Phải bảo vệ **toàn bộ** thao tác phức hợp và vòng duyệt; đọc có thể bị khóa. Đo đạc theo workload. |
| Cần hàng đợi nhiều producer/consumer | `ConcurrentLinkedQueue`, hoặc `BlockingQueue` như `LinkedBlockingQueue`/`ArrayBlockingQueue` | Queue có semantics FIFO/nhận việc, không phải `List` theo index. Chọn bounded queue nếu cần giới hạn backlog. |
| Cần lưu trữ theo key, cập nhật và tra cứu đồng thời | `ConcurrentHashMap<K,V>` | Semantics map, không giữ thứ tự list; phù hợp hơn nếu chính nhu cầu là lookup theo key. |
| Cần tập hợp các phần tử duy nhất, thao tác thêm/xóa thường xuyên | `ConcurrentHashMap.newKeySet()` | Không có thứ tự index như `List`; iterator có tính nhất quán yếu thay vì snapshot cố định. |

Không có cấu trúc nào là bản thay thế 1:1 cho mọi yêu cầu. Trước khi đổi, xác định rõ: có cần thứ tự phần tử và index không, iterator phải thấy trạng thái nào, mức độ đồng thời ra sao, có cần giới hạn bộ nhớ/queue không, và thao tác nào cần tính nguyên tử.

### Một lỗi chọn cấu trúc thường gặp

Nếu cần đăng ký/hủy đăng ký listener rất thường xuyên, nhưng mỗi lần phát sự kiện chỉ duyệt một lần, `CopyOnWriteArrayList` có thể trở thành điểm nghẽn. Không nên chỉ tăng thread pool để khắc phục: các writer vẫn tuần tự hóa và sao chép. Hãy đánh giá khả năng đổi cấu trúc, giảm tần suất cập nhật, gom các cập nhật hợp lý, hoặc cung cấp snapshot bất biến được công bố theo lô khi yêu cầu ứng dụng cho phép.

## 9. Cách đánh giá bằng đo đạc

Đừng quyết định chỉ dựa trên tên “concurrent”. Thu thập tải đại diện và đo:

1. **Tỷ lệ đọc/ghi**: số `get`/duyệt so với `add`/`remove`/`set` trên một đơn vị thời gian.
2. **Kích thước danh sách**: trung bình, p95 và mức cực đại, bởi chi phí copy phụ thuộc số phần tử.
3. **Số reader/writer đồng thời**: xác định luồng ghi có tranh chấp nhiều hay không.
4. **Độ trễ và thông lượng**: đặc biệt p95/p99 của thao tác ghi và của đường xử lý chính.
5. **Cấp phát và GC**: allocation rate, heap occupancy và pause time khi cập nhật liên tục.
6. **Yêu cầu nhất quán**: iterator snapshot có phù hợp không, hay cần thấy thay đổi mới/lập tức?

Có thể dùng JMH cho microbenchmark các thao tác Java và benchmark tích hợp cho luồng xử lý thực tế. Benchmark cần warm-up JVM, kích thước dữ liệu thực tế, nhiều reader/writer, kiểm soát dead-code elimination và so sánh cùng đặc tả nhất quán. Không lấy một vòng lặp `System.nanoTime()` đơn giản làm kết luận hiệu năng.

## 10. Câu hỏi tự kiểm tra và kết luận

**Hỏi:** Đọc nhiều, ghi hiếm, cần callback theo thứ tự: dùng gì?  
**Đáp:** `CopyOnWriteArrayList` là ứng viên hợp lý; iterator snapshot giúp duyệt ổn định ngay cả khi có luồng đăng ký/hủy đăng ký.

**Hỏi:** Có 200.000 phần tử, nhiều writer liên tục `add` và `remove`: vì sao chậm?  
**Đáp:** Mỗi cập nhật thành công thường phải sao chép lượng lớn tham chiếu, cấp phát mảng mới và phối hợp các writer; thêm áp lực GC và snapshot cũ có thể giữ bộ nhớ.

**Hỏi:** Iterator tạo trước `list.add(x)` có thấy `x` không?  
**Đáp:** Không. Iterator đó đi trên mảng cũ. Iterator mới tạo sau khi `add` hoàn tất có thể thấy `x` nếu chưa bị thay đổi tiếp.

**Hỏi:** Có thể gọi `iterator.remove()` để xóa phần tử không?  
**Đáp:** Không; phương thức này ném `UnsupportedOperationException`. Hãy sửa qua API của danh sách, chẳng hạn `removeIf`.

**Hỏi:** `CopyOnWriteArrayList` có làm mọi object bên trong thread-safe không?  
**Đáp:** Không. Nó bảo vệ cấu trúc danh sách và việc công bố tham chiếu, không tự đồng bộ trạng thái mutable bên trong object.

**Ghi nhớ:** `CopyOnWriteArrayList` đánh đổi **chi phí ghi và bộ nhớ** để có **đọc/duyệt ổn định, ít tranh chấp**. Nó thường phát huy lợi thế ở mô hình *read-mostly*; với workload *write-heavy*, hãy xem xét lại cấu trúc dữ liệu và đo đạc cả độ trễ, lượng cấp phát lẫn yêu cầu nhất quán.

Tài liệu chuẩn: [Oracle Java 17 API — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).
