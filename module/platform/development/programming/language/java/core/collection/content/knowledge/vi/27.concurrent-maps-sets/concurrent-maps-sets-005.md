# size, duyệt và thao tác hàng loạt khi đang có cập nhật

Một map hoặc set đồng thời cho phép các luồng tiếp tục đọc, thêm và xóa mà không phải dừng toàn bộ cấu trúc cho mỗi thao tác. Đổi lại, một phép đo hay lượt duyệt nhiều phần tử không mặc nhiên nhìn thấy **một phiên bản thống nhất của tất cả dữ liệu**.

Ví dụ, một bảng giám sát chỉ cần số kết nối gần đúng hiện tại. Một báo cáo đối chiếu lại có thể yêu cầu mọi dòng thuộc cùng thời điểm chốt. Hai yêu cầu ấy cần mức nhất quán khác nhau dù cùng đọc một `ConcurrentHashMap`.

Bài học phân biệt ba việc:

1. **Đếm hoặc hỏi trạng thái tổng hợp:** `size`, `mappingCount`, `isEmpty`, `containsValue`.
2. **Duyệt và đọc nhiều ánh xạ/phần tử:** iterator, view, `forEach`, stream.
3. **Xử lý hàng loạt:** vừa có các phép ghi như `putAll`, `clear`, `replaceAll`, vừa có nhóm `forEach`/`search`/`reduce` riêng của `ConcurrentHashMap`.

Các khái niệm chính:

- **Quan sát tạm thời:** thông tin đọc được trong khi cấu trúc vẫn có thể thay đổi.
- **Nhất quán yếu (weak consistency):** chính sách cho phép duyệt cùng lúc với cập nhật, nhưng không cung cấp một bản chụp nguyên khối của nguồn.
- **Bản chụp nhất quán:** dữ liệu được xác định thuộc một trạng thái chung theo giao thức lấy bản chụp.
- **Nguồn đã yên:** không còn cập nhật liên quan trong khoảng cần đọc, và kết quả của bên ghi đã được công bố đúng cách.
- **Nguyên tử theo phần tử/khóa:** bảo đảm của thao tác riêng không tự mở rộng thành bảo đảm cho toàn bộ collection.

`ConcurrentHashMap` được dùng làm ví dụ chính. `ConcurrentSkipListMap`, `ConcurrentSkipListSet` và set tạo từ `ConcurrentHashMap` có những điểm tương đồng về việc dữ liệu có thể thay đổi trong lúc đọc, nhưng vẫn cần xét hợp đồng riêng của từng lớp.

## 1. size là một phép quan sát, không phải đặt chỗ

`size()` hỏi số ánh xạ/phần tử. Khi bên khác vẫn thêm hoặc xóa, con số quan sát có thể thay đổi ngay trong hoặc ngay sau quá trình lấy thông tin.

Tài liệu `ConcurrentHashMap` lưu ý các phép hỏi tổng hợp như `size`, `isEmpty` và `containsValue` phản ánh trạng thái tạm thời khi có cập nhật, phù hợp hơn với giám sát hoặc ước lượng thay vì điều khiển một giao thức cần điều kiện mạnh. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Đoạn minh họa sau giả sử `sessions` là một map đồng thời:

~~~java
if (sessions.size() < 100) {
    sessions.put(sessionId, session);
}
~~~

Nó chưa bảo đảm có tối đa `100` phiên. Hai luồng có thể cùng thấy `99` rồi thêm hai khóa khác nhau.

Điểm đáng chú ý: lỗi này vẫn tồn tại ngay cả nếu lần `size` của mỗi bên trả về một con số hoàn toàn chính xác ở thời điểm đọc. Vấn đề nằm ở khoảng trống giữa **hỏi còn chỗ** và **chiếm chỗ**. Độ chính xác của phép đo và tính nguyên tử của quyết định là hai câu hỏi khác nhau.

Muốn giới hạn chặt, dùng một giao thức đặt chỗ hoặc bảo vệ cả quyết định kiểm tra và thêm. Không dùng `size` làm một “vé” mà các luồng có thể cùng tiêu thụ.

### 1.1. mappingCount không tăng mức nhất quán

`ConcurrentHashMap.size` trả `int`; nếu số ánh xạ vượt `Integer.MAX_VALUE`, kết quả bị giới hạn ở giá trị đó. `mappingCount` trả `long`, thích hợp hơn về miền số cho map rất lớn, nhưng tài liệu vẫn mô tả kết quả là ước lượng khi có thêm/xóa đồng thời. [Java 17: size và mappingCount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#mappingCount())

Đổi `size` thành `mappingCount` không biến một phép hỏi thành thao tác đặt chỗ hay một khóa toàn map.

### 1.2. isEmpty không chứng minh công việc đã kết thúc

Một lần `isEmpty()` trả `true` không chứng minh sẽ không có công việc mới được thêm ngay sau đó. Nếu ứng dụng cần biết tất cả công việc đã hoàn thành, còn phải có quy tắc về bên tạo việc, thời điểm ngừng nhận, các tác vụ đang chạy và cách chờ hoàn tất.

Ví dụ “hàng đợi/map đang rỗng” khác với “mọi bên sản xuất đã dừng và không còn tác vụ đang thực thi”. Một phép hỏi trên collection chỉ trả lời phần dữ liệu mà nó quản lý.

### 1.3. Không phải mọi size đều có cùng chi phí

Không suy từ việc quen dùng `ArrayList.size` hoặc `HashMap.size` rằng mọi collection đồng thời đều có `size` rẻ. `ConcurrentSkipListSet` ghi rõ phép đếm không phải thời gian hằng số và có thể không chính xác nếu tập thay đổi trong lúc duyệt để đếm. [Java 17: ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html)

Nếu cần lấy số liệu thường xuyên, phải xét cả ý nghĩa nhất quán lẫn chi phí của đúng lớp đang dùng.

## 2. Một lượt duyệt an toàn chưa phải bản chụp

Iterator nhất quán yếu được thiết kế để có thể tiếp tục cùng với các thao tác khác. Nó không dùng `ConcurrentModificationException` như iterator fail-fast thông thường để báo các cập nhật được chính sách đồng thời cho phép. [Java 17: Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#ConcurrentCollections)

Tuy nhiên, không nên diễn giải nó thành một trong hai cực đoan:

- “Đó luôn là bản chụp chính xác ở thời điểm tạo iterator.”
- “Mọi cập nhật mới chắc chắn sẽ xuất hiện trong lượt duyệt.”

Hãy đọc hợp đồng lớp. Với `ConcurrentHashMap`, các phần tử mà lượt duyệt trả về có thể phản ánh những thời điểm khác nhau kể từ khi bắt đầu. Việc nhìn thấy một giá trị ở một khóa không buộc giá trị ở khóa khác phải thuộc cùng một phiên bản chung.

### 2.1. Ghép các quan sát đúng riêng lẻ có thể tạo bản tổng hợp chưa từng tồn tại

Giả sử có hai khóa P và Q, ban đầu đều là `0`. Một bên cập nhật theo thứ tự:

~~~text
P=0, Q=0
P=1, Q=0
P=1, Q=1
~~~

Một lượt duyệt có thể đọc P trước khi cập nhật, rồi đọc Q sau khi cả hai cập nhật xong:

~~~text
Lượt duyệt thu được: P=0, Q=1
~~~

Từng giá trị đều được đọc từ dữ liệu hợp lệ của khóa tương ứng, nhưng cặp `P=0, Q=1` không xuất hiện trong ba trạng thái thực ở trên.

Đó là giới hạn quan trọng của báo cáo tổng hợp: không chỉ “hơi cũ” mà còn có thể **trộn thời điểm** giữa các dòng. Chương trình đầy đủ bên dưới tạo đúng lịch ấy mà không phụ thuộc khóa nào được duyệt trước.

### 2.2. Thứ tự khóa và thời điểm dữ liệu là hai thuộc tính riêng

`ConcurrentSkipListMap` giữ thứ tự theo khóa, nhưng iterator và spliterator vẫn có tính nhất quán yếu. Việc các khóa được đọc theo thứ tự tăng không làm mọi giá trị cùng thuộc một thời điểm. Các thao tác nhiều phần tử cũng không tự thành nguyên tử toàn map. [Java 17: ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

Tương tự, sắp xếp kết quả sau một lượt duyệt chỉ tạo thứ tự trình bày. Nó không quay ngược thời gian để đồng bộ các lần đọc.

### 2.3. View sống cùng nguồn

`keySet`, `values` và `entrySet` là các góc nhìn vào map, không phải bản sao chụp chỉ vì được gán vào biến.

Việc lưu `Set<K> keys = map.keySet()` không chốt tập khóa tại dòng gán. Một lượt sử dụng view sau đó vẫn phải hiểu theo nguồn và chính sách duyệt tương ứng.

Nếu đã giữ một iterator, đừng mặc nhiên chia sẻ chính đối tượng iterator đó cho nhiều luồng chỉ vì nguồn là map đồng thời. Trong `ConcurrentHashMap`, iterator được thiết kế cho một luồng sử dụng tại một thời điểm.

## 3. Các phép ghi hàng loạt không phải giao dịch toàn bộ

Tên “all” nói về tập công việc dự định, không tự nói về ranh giới nguyên tử.

| Phép xử lý | Điều cần hiểu khi có bên cập nhật/đọc khác |
|---|---|
| `putAll(source)` | Người đọc có thể quan sát một phần ánh xạ đã được đưa vào trước phần còn lại. |
| `clear()` | Không tạo một khoảng thời gian rỗng độc quyền cho các thao tác tiếp theo; cập nhật có thể xen kẽ. |
| `replaceAll(function)` | Không phải tất cả giá trị cùng chuyển sang phiên bản mới trong một giao dịch. |
| `removeIf` trên view hoặc set | Nhiều phép xét/xóa riêng không đồng nghĩa một quyết định nguyên khối trên mọi phần tử. |
| `addAll` trên set đồng thời | Không buộc người đọc chỉ thấy trạng thái trước hoặc sau toàn bộ đợt thêm. |

Hợp đồng của từng lớp quyết định chi tiết. Chẳng hạn `ConcurrentSkipListSet` nêu rõ các phép nhiều phần tử như `addAll`, `removeIf` và `forEach` không được bảo đảm thực hiện nguyên tử. [Java 17: thao tác hàng loạt trên ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html)

### 3.1. putAll có cả nguồn lẫn đích

Khi `destination.putAll(source)` chạy, cần hỏi hai câu độc lập:

1. Đích cho người đọc khác quan sát đợt cập nhật như thế nào?
2. Nguồn có thể được đọc hợp lệ trong khi bên khác sửa nó không?

Đích là `ConcurrentHashMap` không tự làm một `HashMap` nguồn đang bị sửa thiếu đồng bộ trở nên an toàn. Nếu nguồn cũng là map đồng thời, lượt đọc nguồn vẫn có thể trộn thời điểm. Tính an toàn của đích không nâng ngữ nghĩa nguồn thành bản chụp.

### 3.2. clear không phải một hàng rào đóng dữ liệu

Sau `clear`, một luồng khác có thể `put` ngay trước lần `isEmpty` tiếp theo của bên gọi. Trong lúc `clear` và ghi chồng lấn, không được dùng nó như giao thức “xóa hết và cấm thêm”.

Nếu yêu cầu là đóng một registry rồi xóa, cần trạng thái đóng và cách phối hợp với bên đăng ký. Xóa nội dung và đổi vòng đời registry là hai việc cần được mô hình hóa.

### 3.3. replaceAll có thể để lại kết quả một phần

Nếu hàm xử lý đã trả giá trị mới cho vài khóa rồi ném lỗi ở khóa tiếp theo, những cập nhật trước đó không tự được hoàn tác.

Ngoài ra, triển khai mặc định của `ConcurrentMap.replaceAll` có thể thử lại dưới tranh chấp và gọi hàm nhiều lần cho một khóa. Đừng dùng nó làm nơi phát sinh tác dụng bên ngoài với giả định mỗi khóa chỉ gọi đúng một lần. [Java 17: ConcurrentMap.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#replaceAll(java.util.function.BiFunction))

Nếu cần thay nguyên cả bộ dữ liệu từ phiên bản cũ sang phiên bản mới, xây một bản mới rồi công bố theo giao thức phiên bản có thể phù hợp hơn việc lần lượt thay từng ánh xạ.

## 4. Nhóm bulk operation riêng của ConcurrentHashMap

`ConcurrentHashMap` có các phương thức xử lý hàng loạt riêng, nhận thêm `parallelismThreshold`. Chúng được thiết kế để có thể sử dụng khi map có cập nhật, nhưng kết quả không mặc nhiên nguyên tử đối với toàn map.

Ba nhóm chính là:

- `forEach`: xử lý những cặp/khóa/giá trị/entry được duyệt.
- `search`: tìm một kết quả khác `null` từ hàm tìm kiếm.
- `reduce`: kết hợp các kết quả thành một giá trị tổng hợp.

Các biến thể có thể nhận khóa, giá trị, cặp khóa–giá trị hoặc entry. Không có yêu cầu phải dùng nhóm này cho mọi phép đọc; hãy chọn khi ngữ nghĩa tổng hợp trong nguồn đang biến động phù hợp.

### 4.1. Ngưỡng song song là lựa chọn thực thi, không phải khóa dữ liệu

`Long.MAX_VALUE` tắt việc chia xử lý song song cho các phương thức này. Ngưỡng `1` cho phép chia mạnh; các ngưỡng trung gian dùng kích thước ước lượng để quyết định cách chia. Điều đó không đồng nghĩa luôn có đúng một số lượng luồng cố định.

Các tính toán song song dùng `ForkJoinPool.commonPool`. Pool này là tài nguyên chung; hàm chặn lâu hoặc có I/O có thể ảnh hưởng công việc khác. [Java 17: ForkJoinPool.commonPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html#commonPool())

Hai điều cần tách:

- **Tuần tự/song song:** một hay nhiều luồng thực hiện lượt xử lý.
- **Nhất quán:** các quan sát có cùng một trạng thái nguồn hay không.

Một lượt `forEach(Long.MAX_VALUE, ...)` vẫn có thể bị bên ghi khác làm nguồn thay đổi trong lúc chạy. Tắt song song không lấy khóa toàn map.

### 4.2. forEach không bảo vệ collection đích mà hàm tự ghi

Ví dụ cần phân tích:

~~~java
List<String> lines = new ArrayList<>();
map.forEach(1L, (key, value) -> lines.add(key + "=" + value));
~~~

Đây là đoạn minh họa chưa an toàn, giả sử `map` là `ConcurrentHashMap` và các kiểu danh sách đã được import. Hàm có thể chạy đồng thời ở nhiều tác vụ; `ArrayList` bên ngoài không tự được bảo vệ.

Có thể dùng một nơi thu kết quả có hợp đồng phù hợp như `ConcurrentLinkedQueue` rồi sắp xếp sau khi lượt xử lý hoàn tất. Cách đó giải quyết nơi ghi kết quả, nhưng vẫn không biến nguồn đang cập nhật thành bản chụp nhất quán.

Các entry được truyền cho bulk operation trên entry không hỗ trợ `setValue`. Để sửa ánh xạ theo điều kiện, dùng API cập nhật có hợp đồng phù hợp thay vì coi entry xử lý hàng loạt là giao dịch sống.

### 4.3. search trả một kết quả, không phải kết quả nhỏ nhất hay mới nhất

Hàm tìm kiếm trả `null` để nói chưa có kết quả phù hợp tại phần tử đó. Khi có kết quả khác `null`, xử lý tiếp được giảm/dừng theo cơ chế của phương thức; những tác vụ khác có thể đã bắt đầu.

Vì vậy:

- Có nhiều kết quả phù hợp thì không mặc nhiên chọn khóa nhỏ nhất.
- Không dùng hàm tìm kiếm để thực hiện một tác dụng với giả định chỉ đúng một lần gọi.
- Kết quả `null` nói về những dữ liệu đã được quá trình tìm quan sát, không chứng minh không có phần tử phù hợp trong mọi thời điểm cập nhật.
- Một kết quả tìm được có thể đã bị thay đổi/gỡ khỏi map trước khi bên gọi sử dụng tiếp.

Nếu cần “tìm và nhận độc quyền”, phải có thêm thao tác điều kiện hoặc mô hình nhận việc; tìm kiếm chỉ là phần quan sát.

### 4.4. reduce cần phép kết hợp phù hợp

Vì không có thứ tự duyệt chung của `ConcurrentHashMap` và có thể chia nhóm khác nhau, hàm giảm cần tính kết hợp và giao hoán theo hợp đồng để kết quả không phụ thuộc cách chia/thứ tự.

Các ví dụ thường phù hợp trên miền dữ liệu đã xác định là cộng số nguyên không tràn, đếm hoặc chọn cực trị. Phép nối chuỗi theo thứ tự, trừ tuần tự hoặc hàm phụ thuộc vào một biến bên ngoài đang thay đổi không tự đáp ứng yêu cầu ấy.

Với biến thể trả đối tượng, `null` là dấu hiệu không có kết quả đóng góp. Hàm chuyển đổi có thể trả `null` để lọc bỏ phần tử. Với biến thể số nguyên thủy, chọn phần tử trung hòa đúng: tổng dùng `0`, nhỏ nhất dùng giá trị lớn nhất của miền, lớn nhất dùng giá trị nhỏ nhất của miền.

**Phần tử trung hòa** là giá trị mà khi kết hợp với một giá trị khác thì giữ nguyên giá trị kia. Không chọn `100` làm giá trị gốc cho phép cộng rồi hy vọng nó chỉ được thêm đúng một lần khi quá trình chia nhiều phần.

### 4.5. Tổng hợp an toàn vẫn có thể không thuộc một thời điểm chung

Một `reduce` có thể đọc giá trị cũ ở khóa này và giá trị mới ở khóa khác. Kết quả của nó phản ánh các quan hệ nhìn thấy dữ liệu theo từng ánh xạ, chưa nhất thiết là tổng của toàn map ở cùng một thời điểm. Đây là giới hạn được nêu trong phần hợp đồng bulk operation. [Java 17: tính nhất quán của bulk operation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Đối với số liệu giám sát, điều đó có thể chấp nhận được. Đối với đối chiếu số dư hay chốt báo cáo, cần giao thức mạnh hơn.

## 5. Chương trình kiểm chứng

Tệp `ConcurrentObservationDemo.java` chạy độc lập bằng API Java 17. Chương trình đã được biên dịch với `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2. Không coi đây là tuyên bố đã chạy trên JVM 17.

Các phép tổng hợp đầu chương trình dùng nguồn không có bên ghi để kiểm chứng API và stdout rõ ràng. Các phần sau chủ động tạo lịch cập nhật bằng latch/hàng rào; không dự đoán kết quả từ một cuộc đua ngẫu nhiên.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ConcurrentObservationDemo {
    static void await(CountDownLatch signal) {
        try {
            if (!signal.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Signal timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AssertionError("Interrupted", ex);
        }
    }

    static Thread launch(String name, Runnable action,
                         AtomicReference<Throwable> error) {
        Thread thread = new Thread(() -> {
            try {
                action.run();
            } catch (Throwable ex) {
                error.compareAndSet(null, ex);
            }
        }, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    static void finish(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread timed out: " + thread.getName());
        }
        if (error.get() != null) {
            throw new AssertionError("Thread failed", error.get());
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> stable = new ConcurrentHashMap<>();
        stable.put("a", 2);
        stable.put("b", 5);
        stable.put("c", 7);
        System.out.println("stable-size = " + stable.size());
        System.out.println("stable-mappingCount = " + stable.mappingCount());
        System.out.println("sum-sequential = "
                + stable.reduceValuesToLong(Long.MAX_VALUE, Integer::longValue,
                                            0L, Long::sum));
        System.out.println("sum-parallel-enabled = "
                + stable.reduceValuesToLong(1L, Integer::longValue, 0L, Long::sum));
        System.out.println("odd-value-sum = "
                + stable.reduceValues(Long.MAX_VALUE,
                        value -> value % 2 == 1 ? value : null, Integer::sum));
        System.out.println("search-b = "
                + stable.search(Long.MAX_VALUE,
                        (key, value) -> key.equals("b") ? value : null));
        System.out.println("search-absent = "
                + stable.searchValues(Long.MAX_VALUE, value -> value > 100 ? value : null));

        ConcurrentLinkedQueue<String> collected = new ConcurrentLinkedQueue<>();
        stable.forEach(1L, (key, value) -> collected.add(key + "=" + value));
        List<String> ordered = new ArrayList<>(collected);
        Collections.sort(ordered);
        System.out.println("collected-sorted = " + ordered);

        ConcurrentHashMap<String, Integer> empty = new ConcurrentHashMap<>();
        System.out.println("empty-reference-reduce = "
                + empty.reduceValues(Long.MAX_VALUE, Integer::sum));
        System.out.println("empty-sum = "
                + empty.reduceValuesToLong(Long.MAX_VALUE, Integer::longValue,
                                           0L, Long::sum));

        ConcurrentHashMap<String, Integer> slots = new ConcurrentHashMap<>();
        AtomicInteger ids = new AtomicInteger();
        AtomicReference<Throwable> limitError = new AtomicReference<>();
        CyclicBarrier checked = new CyclicBarrier(2);
        Runnable attempt = () -> {
            int id = ids.incrementAndGet();
            boolean hasRoom = slots.size() < 1;
            try {
                checked.await(5, TimeUnit.SECONDS);
            } catch (Exception ex) {
                throw new AssertionError("Barrier failed", ex);
            }
            if (hasRoom) {
                slots.put("slot-" + id, id);
            }
        };
        Thread first = launch("limit-first", attempt, limitError);
        Thread second = launch("limit-second", attempt, limitError);
        finish(first, limitError);
        finish(second, limitError);
        System.out.println("capacity-one-final-size = " + slots.size());

        ConcurrentHashMap<String, Integer> changing = new ConcurrentHashMap<>();
        changing.put("a", 0);
        changing.put("b", 0);
        List<Map<String, Integer>> actualStates = new ArrayList<>();
        actualStates.add(Map.copyOf(changing));
        AtomicReference<String> firstKey = new AtomicReference<>();
        CountDownLatch firstObserved = new CountDownLatch(1);
        CountDownLatch updated = new CountDownLatch(1);
        AtomicReference<Throwable> updateError = new AtomicReference<>();
        Thread updater = launch("two-updates", () -> {
            try {
                await(firstObserved);
                String visited = firstKey.get();
                changing.put(visited, 1);
                actualStates.add(Map.copyOf(changing));
                String other = visited.equals("a") ? "b" : "a";
                changing.put(other, 1);
                actualStates.add(Map.copyOf(changing));
            } finally {
                updated.countDown();
            }
        }, updateError);

        Map<String, Integer> observations = new TreeMap<>();
        changing.forEach(Long.MAX_VALUE, (key, value) -> {
            observations.put(key, value);
            if (firstKey.compareAndSet(null, key)) {
                firstObserved.countDown();
                await(updated);
            }
        });
        finish(updater, updateError);
        List<Integer> observedValues = new ArrayList<>(observations.values());
        Collections.sort(observedValues);
        System.out.println("mixed-observed-values = " + observedValues);
        System.out.println("observed-map-was-actual-state = "
                + actualStates.contains(observations));
        System.out.println("current-values = " + new TreeMap<>(changing));

        ConcurrentHashMap<String, Integer> partial = new ConcurrentHashMap<>();
        partial.put("x", 1);
        partial.put("y", 2);
        partial.put("z", 3);
        AtomicInteger calls = new AtomicInteger();
        boolean failed = false;
        try {
            partial.replaceAll((key, value) -> {
                if (calls.incrementAndGet() == 2) {
                    throw new IllegalStateException("Stop on second callback");
                }
                return value * 10;
            });
        } catch (IllegalStateException ex) {
            failed = true;
        }
        long changed = partial.values().stream().filter(value -> value >= 10).count();
        System.out.println("replaceAll-failed = " + failed);
        System.out.println("replaceAll-changed-entries = " + changed);
        System.out.println("replaceAll-size = " + partial.size());

        ConcurrentSkipListSet<Integer> sortedSet =
                new ConcurrentSkipListSet<>(List.of(3, 1, 2));
        System.out.println("quiescent-sorted-set = " + sortedSet);
        System.out.println("quiescent-set-size = " + sortedSet.size());

        AtomicReference<Map<String, Integer>> published =
                new AtomicReference<>(Map.of("a", 0, "b", 0));
        Map<String, Integer> captured = published.get();
        published.set(Map.of("a", 1, "b", 1));
        System.out.println("captured-version = " + new TreeMap<>(captured));
        System.out.println("published-version = " + new TreeMap<>(published.get()));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ConcurrentObservationDemo.java
java ConcurrentObservationDemo
~~~

Stdout đã kiểm chứng:

~~~text
stable-size = 3
stable-mappingCount = 3
sum-sequential = 14
sum-parallel-enabled = 14
odd-value-sum = 12
search-b = 5
search-absent = null
collected-sorted = [a=2, b=5, c=7]
empty-reference-reduce = null
empty-sum = 0
capacity-one-final-size = 2
mixed-observed-values = [0, 1]
observed-map-was-actual-state = false
current-values = {a=1, b=1}
replaceAll-failed = true
replaceAll-changed-entries = 1
replaceAll-size = 3
quiescent-sorted-set = [1, 2, 3]
quiescent-set-size = 3
captured-version = {a=0, b=0}
published-version = {a=1, b=1}
~~~

Chương trình không khẳng định các bulk operation ngẫu nhiên trên mọi nguồn đang đổi sẽ luôn có cùng stdout. Các kết quả liên quan tranh chấp ở đây được điều phối để tạo một tình huống cụ thể.

## 6. Vì sao các kết quả có ý nghĩa?

### 6.1. Nguồn đã yên: có thể so sánh hai cách thực thi

Nguồn `stable` có các giá trị `2`, `5`, `7` và không bị sửa trong lúc xử lý:

~~~text
sum-sequential = 14
sum-parallel-enabled = 14
odd-value-sum = 12
~~~

Hai phép cộng cùng đạt `14`. Ngưỡng `1` chỉ cho phép song song, không được dùng kết quả này để suy ra đã có chính xác bao nhiêu luồng chạy. Phép chuyển đổi trả `null` cho số chẵn khiến `2` không đóng góp vào tổng số lẻ, còn `5 + 7 = 12`.

Tìm khóa `b` chỉ có một đáp án `5`. Tìm giá trị lớn hơn `100` không có kết quả nên trả `null`. Với map rỗng, phép giảm trả đối tượng cho `null`, phép cộng nguyên thủy dùng phần tử trung hòa `0` nên trả `0`.

Kết quả thu bằng queue được sắp xếp **sau khi bulk operation hoàn tất**, vì vậy stdout không phụ thuộc thứ tự callback chạy.

### 6.2. Cả hai size đều đúng mà giới hạn vẫn bị vượt

Hai luồng cùng đo `slots.size() < 1` trước khi ai thêm phần tử. Hàng rào giữ cả hai ở sau phép đo; khi được đi tiếp, cả hai đều thêm khóa riêng.

~~~text
capacity-one-final-size = 2
~~~

Ở đây không cần dựa vào sự sai lệch nội bộ của phép đếm: mỗi bên đều có thể đã quan sát đúng map rỗng. Điều bị thiếu là một quyết định cấp chỗ nguyên tử.

### 6.3. Lượt duyệt tạo bản ghép chưa từng là trạng thái nguồn

Chương trình không giả định `a` hay `b` được duyệt trước. Khóa đầu tiên được callback đọc gọi là **khóa đã thăm**; khóa còn lại là **khóa chưa thăm**.

Lịch được điều khiển như sau:

~~~text
Nguồn: (khóa đã thăm=0, khóa chưa thăm=0)
Callback ghi nhận giá trị 0 của khóa đầu tiên rồi đợi.

Luồng cập nhật:
    đổi khóa đã thăm thành 1
    đổi khóa chưa thăm thành 1
    báo đã xong

Callback tiếp tục:
    ghi nhận giá trị 1 của khóa còn lại
~~~

Lịch sử nguồn chỉ có ba trạng thái:

~~~text
(0, 0) -> (1, 0) -> (1, 1)
~~~

Bản thu lại là `(0, 1)` theo thứ tự khóa đã thăm/chưa thăm, nên:

~~~text
mixed-observed-values = [0, 1]
observed-map-was-actual-state = false
~~~

`actualStates` được luồng cập nhật ghi sau từng lần thay, khi không có bên ghi nào khác. Luồng chính chỉ đọc danh sách lịch sử sau khi `join` hoàn tất, nên không có cuộc đua trên chính danh sách `ArrayList` lưu lịch sử.

Điểm chờ trong callback là dụng cụ tạo lịch cho thí nghiệm, không phải lời khuyên chặn callback lâu trong bulk operation sản phẩm. Ví dụ cho thấy một lượt duyệt tuần tự vẫn không khóa nguồn.

### 6.4. replaceAll không hoàn tác cập nhật trước lỗi

Hàm đầu tiên nhân một giá trị với `10`. Hàm thứ hai ném lỗi. Không cần biết khóa nào được xử lý đầu tiên, có thể kiểm tra đúng một giá trị đã đổi:

~~~text
replaceAll-failed = true
replaceAll-changed-entries = 1
replaceAll-size = 3
~~~

Không có luồng ghi khác ở phần này. Nó cô lập tính chất “không phải giao dịch hoàn tác toàn bộ”. Trong môi trường có cập nhật cạnh tranh, còn phải xét các lần thay xen kẽ và khả năng hàm được gọi lại.

### 6.5. Bản phiên đã lấy khác với đọc lại tham chiếu mới

Ở cuối chương trình, `AtomicReference` giữ một map không sửa được chứa hai số nguyên. Bên đọc lấy một tham chiếu `captured`, rồi bên công bố thay toàn bộ tham chiếu sang một map mới.

~~~text
captured-version = {a=0, b=0}
published-version = {a=1, b=1}
~~~

Bản đã lấy vẫn là map cũ. Toàn bộ lượt đọc trên bản ấy dùng cùng đối tượng dữ liệu không còn bị sửa. Đây là mô hình phiên dữ liệu, khác với lần lượt cập nhật hai khóa trong cùng map sống.

`AtomicReference` cung cấp truy cập/cập nhật một tham chiếu nguyên tử. Nó không tự đóng băng đối tượng tham chiếu tới; tính không bị sửa của map trong ví dụ là một phần thiết kế dữ liệu. [Java 17: java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)

## 7. Lấy bản sao không tự bảo đảm cùng một thời điểm

Các thao tác sau tạo một đối tượng kết quả riêng, nhưng nguồn vẫn có thể thay đổi trong lúc sao chép:

~~~java
Map<String, Integer> copy = new HashMap<>(liveMap);
Map<String, Integer> frozen = Map.copyOf(liveMap);
~~~

Đây là đoạn minh họa trong phương thức với các kiểu từ `java.util` và `liveMap` là map đồng thời. Khi quá trình lấy dữ liệu hoàn tất, kết quả riêng có thể ổn định theo cách nó được quản lý. Nhưng các mục được sao chép vẫn có thể đến từ nhiều thời điểm của nguồn.

`Map.copyOf` tạo map không sửa được; đặc tính đó không biến việc đọc nguồn thành một giao dịch chụp toàn nguồn. Hơn nữa, các đối tượng khóa/giá trị có thể vẫn là cùng tham chiếu, nên không có sao chép sâu tự động. [Java 17: Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))

Một bản sao có thể đáp ứng yêu cầu “từ giờ kết quả của tôi không tiếp tục nhận thay đổi thành viên”. Để đáp ứng yêu cầu mạnh hơn “mọi mục cùng thuộc một trạng thái nguồn”, phải có cơ chế lấy dữ liệu tương ứng.

Sắp xếp bản sao, đổi sang `TreeMap` hoặc gọi `toArray` sau đó không sửa được vấn đề trộn thời điểm đã xảy ra lúc đọc nguồn.

## 8. Khi nào cần cơ chế mạnh hơn?

### 8.1. Chỉ cần theo dõi, ước lượng

Bảng giám sát số lượng, thống kê hoạt động hoặc việc tìm một ứng viên có thể chấp nhận kết quả biến động. Khi ấy, dùng các API đồng thời và diễn đạt đúng mức đảm bảo thường phù hợp.

Đừng đặt tên hoặc diễn giải số liệu thành “số chính xác tại thời điểm chốt” nếu quá trình lấy dữ liệu chưa có giao thức chốt. Sự rõ ràng về ý nghĩa kết quả giúp người dùng hệ thống quyết định đúng.

### 8.2. Cần giới hạn sức chứa

Có thể dùng một `Semaphore` để cấp quyền chiếm chỗ hoặc một khối khóa chung bảo vệ kiểm tra/thêm. `Semaphore` quản lý số giấy phép bằng các thao tác lấy/trả có hợp đồng, thay vì để nhiều luồng tự suy từ cùng một số `size`. [Java 17: Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)

Nhưng phải thiết kế toàn bộ vòng đời: thêm thất bại thì trả giấy phép đã lấy, xóa thành công thì trả đúng một lần, mọi đường ghi đều tuân thủ, và trường hợp khóa trùng không làm rò hoặc trả thừa giấy phép. Chỉ đặt thêm một semaphore cạnh map chưa tự nối hai cấu trúc thành giao thức đúng.

### 8.3. Cần một bản chụp nhất quán cho báo cáo

Một số cách thiết kế thường dùng:

- Tạm dừng hoặc chờ hoàn tất tất cả bên ghi liên quan rồi đọc trong khoảng nguồn đã yên.
- Dùng khóa ngoài chung mà **mọi bên ghi liên quan** tuân thủ; giữ khóa trong cả khoảng sao chép cần nhất quán.
- Công bố các phiên dữ liệu không bị sửa và để người đọc lấy một phiên cho cả lượt xử lý.
- Dùng cơ chế phiên/giao dịch của nơi thực sự sở hữu dữ liệu khi dữ liệu nằm ở hệ thống khác.

Không có cách nào được áp dụng chỉ bằng một dòng `synchronized(liveMap)` nếu các bên khác vẫn gọi trực tiếp phương thức `ConcurrentHashMap` mà không tham gia monitor ấy.

### 8.4. Nếu dùng wrapper đồng bộ

`Collections.synchronizedMap` có giao thức khác: truy cập qua wrapper và đồng bộ thủ công trên wrapper khi duyệt các view. Với lượt sao chép cần chặn bên ghi, mọi truy cập liên quan phải tuân thủ wrapper/khóa chung, không đi vòng qua map gốc. [Java 17: Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Ngoài ra, nếu một cập nhật nghiệp vụ gồm nhiều bước phải được nhìn như một đợt, bên ghi cũng cần giữ khóa chung quanh cả đợt. Chỉ khóa từng lời gọi riêng lẻ chưa bảo vệ bất biến nhiều khóa.

### 8.5. Nếu công bố phiên không sửa được

Bên đọc phải lấy tham chiếu phiên **một lần** rồi dùng nó trong suốt lượt xử lý. Nếu đọc lại tham chiếu đã công bố cho từng khóa, nó vẫn có thể lấy khóa này từ bản cũ và khóa kia từ bản mới.

Phần tử có thể sửa vẫn cần thiết kế riêng. Map không sửa được chứa đối tượng số dư đang thay đổi không phải bản chụp sâu của mọi số dư.

Nếu có nhiều bên tạo phiên mới từ bản cũ, còn phải phối hợp việc công bố để tránh ghi đè mất phiên cập nhật. Ví dụ cuối chương trình chỉ minh họa một lần công bố, không tự giải quyết tất cả bài toán nhiều bên ghi.

## 9. Set đồng thời và các phép hỏi nhiều phần tử

`ConcurrentHashMap.newKeySet()` dùng tính chất map nền cho một tập không thứ tự. `ConcurrentSkipListSet` cung cấp thứ tự phần tử. Trong cả hai, cần tách:

- Một lần thêm hoặc xóa phần tử.
- Một lượt duyệt nhiều phần tử.
- Một điều kiện tổng như số lượng hay tập con.
- Một đợt thêm/xóa nhiều phần tử.

Việc `set.add(x)` trả kết quả theo hợp đồng không làm `if (set.size() < limit) set.add(x)` thành nguyên tử. Một phép `containsAll` hoặc so sánh hai tập đang bị sửa cũng không nên được coi như đối chiếu hai bản dữ liệu đã chốt.

Nếu set được dùng để ghi các công việc đang chạy, xóa phần tử không tự chứng minh tác vụ ấy đã kết thúc đúng cách. Vòng đời tác vụ cần cơ chế hoàn tất riêng.

Khi cần gỡ có điều kiện theo phiên hoặc chủ sở hữu, một map chứa dấu nhận diện phiên thường diễn đạt điều kiện rõ hơn một set chỉ lưu khóa; lựa chọn phụ thuộc dữ liệu thực sự cần bảo vệ.

## 10. Stream không nâng mức nhất quán của nguồn

`liveMap.values().stream()` hoặc `parallelStream()` vẫn bắt đầu từ nguồn đang sống. Một pipeline không tự sao chép map trước khi chạy. Stream có xử lý trì hoãn; việc tạo pipeline không đồng nghĩa đã đọc hết dữ liệu ở thời điểm đó. [Java 17: Stream và thời điểm duyệt nguồn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)

Nếu nguồn cho phép cập nhật đồng thời, lượt xử lý cần được hiểu theo chính sách nguồn. Đổi từ `forEach` sang `stream` không biến các quan sát thành một phiên chung.

`parallelStream` còn đặt thêm yêu cầu đối với hàm xử lý và nơi nhận kết quả. Đừng ghi cùng một `ArrayList` từ nhiều tác vụ rồi cho rằng tính đồng thời của map bảo vệ cả danh sách đó.

Khi đã có một bản dữ liệu phù hợp với yêu cầu nhất quán, mới xét cách tính tuần tự hoặc song song trên bản ấy. Tính nhất quán của đầu vào và hiệu năng phép tính là hai quyết định riêng.

## 11. Những kết luận cần tránh

| Kết luận dễ mắc | Điều thực sự cần kiểm tra |
|---|---|
| “Không có ConcurrentModificationException nên tôi có bản chụp.” | Lượt duyệt có hợp đồng bản chụp hay chỉ nhất quán yếu? |
| “size vừa dưới giới hạn nên thêm chắc còn chỗ.” | Kiểm tra và cấp chỗ có cùng một thao tác/giao thức không? |
| “mappingCount là long nên luôn chính xác hơn về thời điểm.” | Kiểu số lớn hơn không tạo mức nhất quán mạnh hơn. |
| “forEach tuần tự thì bên ghi không thay được dữ liệu.” | Có cơ chế ngăn hoặc phối hợp bên ghi trong cả lượt đọc không? |
| “putAll/replaceAll có all nên người đọc chỉ thấy trước hoặc sau.” | Hợp đồng có nguyên tử toàn bộ hay chỉ nhiều cập nhật riêng? |
| “Map.copyOf cho tôi ảnh chụp đúng một thời điểm.” | Quá trình đọc nguồn đã được phối hợp thế nào? |
| “Dùng set có thứ tự thì mọi phần tử thuộc cùng phiên.” | Thứ tự phần tử khác với tính nhất quán theo thời gian. |
| “Hàm bulk ghi kết quả thoải mái vì nguồn an toàn.” | Nơi nhận kết quả và các tác dụng của hàm có an toàn khi chạy đồng thời không? |

Các phép đo hay log cũng có thể thực hiện duyệt. Chẳng hạn `toString` hoặc việc định dạng toàn map có thể tạo một mô tả trộn thời điểm khi nguồn đang cập nhật. Dùng thông tin ấy để chẩn đoán với ý nghĩa phù hợp, tránh coi nó là chứng cứ chốt trạng thái mà không có giao thức chụp.

## 12. Bài tập tự kiểm tra

### Bài 1 — Phép đếm hoàn toàn đúng vẫn chưa đủ

Hai luồng đều thấy map có `9` phần tử, giới hạn là `10`, rồi mỗi luồng thêm một khóa riêng. Có cần chứng minh `size` trả sai mới giải thích được kết quả `11` không?

**Đáp án:** Không. Hai phép đo có thể đều đúng lúc đọc. Vấn đề là kiểm tra và thêm chưa được gộp thành quyết định cấp chỗ nguyên tử.

### Bài 2 — Ngưỡng Long.MAX_VALUE

`map.forEach(Long.MAX_VALUE, action)` chạy tuần tự. Có thể dùng nó để bảo đảm dữ liệu không đổi trong suốt lượt duyệt không?

**Đáp án:** Không. Nó tắt việc chia song song của chính lượt xử lý, không khóa các bên ghi khác.

### Bài 3 — Bản ghép chưa từng tồn tại

Nguồn lần lượt có `(P=0,Q=0)`, `(P=1,Q=0)`, `(P=1,Q=1)`. Vì sao một lượt duyệt có thể thu `(P=0,Q=1)` mà không có lỗi cấu trúc?

**Đáp án:** Nó có thể đọc P trước đợt cập nhật và Q sau đợt cập nhật. Từng quan sát hợp lệ theo khóa nhưng không cùng thời điểm.

### Bài 4 — ReplaceAll thất bại giữa chừng

Hàm đã đổi ba khóa rồi ném lỗi ở khóa tiếp theo. Có nên mong ba khóa trước tự quay lại giá trị cũ không?

**Đáp án:** Không. Đây không phải giao dịch hoàn tác toàn bộ. Cần xử lý trạng thái một phần hoặc dùng mô hình công bố phiên mới nếu yêu cầu thay cả bộ cùng lúc.

### Bài 5 — Thu kết quả song song

Một bulk `forEach` ngưỡng `1` ghi các chuỗi vào một `ArrayList` dùng chung. Nguồn là `ConcurrentHashMap`. Chỗ nào còn thiếu hợp đồng?

**Đáp án:** Danh sách nhận kết quả không tự được bảo vệ. Dùng nơi thu phù hợp hoặc cách tổng hợp khác. Sau đó vẫn phải xét việc nguồn có trộn thời điểm không.

### Bài 6 — Phần tử trung hòa

Vì sao phép cộng số lượng dùng giá trị gốc `0` thay vì `100` khi giảm song song?

**Đáp án:** `0` giữ nguyên giá trị kết hợp. Một giá trị không trung hòa có thể bị tính vào nhiều phần của quá trình giảm; nó không phải khoản cộng thêm duy nhất được bảo đảm.

### Bài 7 — Sao chép rồi sắp xếp

`new TreeMap<>(liveConcurrentMap)` cho kết quả có thứ tự. Có đủ để nói mọi mục được chụp cùng thời điểm không?

**Đáp án:** Không. Thứ tự trình bày không thay đổi cách dữ liệu được đọc từ nguồn đang biến động. Cần cơ chế lấy bản chụp nhất quán riêng.

### Bài 8 — Giữ một phiên

Một `AtomicReference` trỏ đến các map không bị sửa sau công bố. Người đọc gọi `get` riêng trước khi đọc từng khóa. Có thể vẫn trộn hai phiên không?

**Đáp án:** Có. Tham chiếu có thể đã được thay giữa hai lần `get`. Lấy một tham chiếu phiên và dùng nó cho toàn bộ lượt đọc nếu yêu cầu mọi khóa thuộc cùng bản.

Trước một phép `size`, lượt duyệt hay thao tác hàng loạt, hãy xác định kết quả cần là một ước lượng đang sống, một hành động theo từng khóa, hay một bản dữ liệu đã chốt. Mức nhất quán cần thiết quyết định giao thức đọc/ghi; tên phương thức và việc không có ngoại lệ chưa thay thế được quyết định đó.
