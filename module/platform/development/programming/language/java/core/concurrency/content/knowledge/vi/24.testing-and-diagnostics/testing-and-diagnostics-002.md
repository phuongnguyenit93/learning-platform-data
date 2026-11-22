# Tái hiện race condition với latch/barrier trong Java

## 1. Vì sao race condition khó tái hiện?

Một **race condition** xảy ra khi kết quả đúng của chương trình phụ thuộc vào thứ tự hoặc thời điểm các luồng thực hiện những bước có liên quan. Khi chạy bình thường, lỗi có thể xuất hiện rất hiếm: scheduler chạy một luồng xong rồi mới chuyển sang luồng khác, máy phát triển ít tải, hoặc việc đặt breakpoint/log vô tình thay đổi thứ tự thực thi. Một bài kiểm thử chỉ “chạy thật nhiều thread rồi hy vọng lỗi xuất hiện” thường không thể xác nhận chắc chắn cả trường hợp có lỗi lẫn trường hợp đã sửa.

Ví dụ hai thread cùng tăng một biến:

~~~java
int old = counter.value; // đọc
int next = old + 1;       // tính
counter.value = next;     // ghi
~~~

Phép tăng là chuỗi **read → modify → write**; nó không tự động là một thao tác nguyên tử. Nếu cả hai cùng đọc 0, rồi lần lượt ghi 1, kết quả là 1 dù đã có hai yêu cầu tăng. Đây là **lost update**.

Ta có thể dùng các công cụ đồng bộ trong java.util.concurrent để **ép một lịch thực thi cụ thể**: cho cả hai worker đọc cùng giá trị trước khi cho phép bất kỳ worker nào ghi. Từ đó, lỗi có thể được tái hiện một cách có kiểm soát, dễ chẩn đoán và kiểm tra lại sau khi sửa.

Bài học tập trung vào **Java concurrency nói chung**: CountDownLatch, CyclicBarrier, ExecutorService, Future, AtomicInteger, ConcurrentHashMap và nguyên tắc happens-before trong Java Memory Model. Không sử dụng cơ chế kiểm thử hay cấu hình concurrency đặc thù của Spring.

## 2. Phân biệt race condition, data race và tính nguyên tử

Ba khái niệm liên quan nhưng không hoàn toàn giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Race condition | Tính đúng đắn phụ thuộc vào thứ tự các hành động; thứ tự không được kiểm soát theo hợp đồng | Hai yêu cầu đều thấy một chỗ trống và cùng giữ chỗ |
| Data race (theo Java Memory Model) | Hai truy cập xung đột vào cùng biến, ít nhất một là ghi, không có quan hệ happens-before thích hợp giữa chúng | Hai thread ghi vào trường int thông thường mà không đồng bộ |
| Thao tác không nguyên tử | Một thao tác nghiệp vụ gồm nhiều bước có thể bị thread khác xen vào | get → cộng 1 → put trên ConcurrentHashMap |

Có **race condition ngay cả khi các phương thức riêng lẻ đều thread-safe**. Ví dụ get và put của ConcurrentHashMap được thiết kế cho truy cập đồng thời, nhưng chuỗi get → tính → put không được gộp thành một hành động nguyên tử. Hai thread vẫn có thể đọc cùng giá trị cũ và ghi đè kết quả của nhau.

Một trường int được khai báo volatile giúp cung cấp quy tắc visibility và ordering của volatile, nhưng **volatile không biến phép tăng gồm nhiều bước thành atomic**. Muốn bảo toàn phép tăng, dùng AtomicInteger.incrementAndGet(), synchronized bảo vệ toàn bộ read-modify-write, hoặc cơ chế cập nhật nguyên tử phù hợp.

Một bài tái hiện tốt phải chỉ ra **giả định về thứ tự** và **trạng thái sau khi thực thi**, không chỉ nêu rằng đã chạy hai thread.

## 3. Vai trò khác nhau của CountDownLatch và CyclicBarrier

### CountDownLatch: cổng một chiều

CountDownLatch có bộ đếm ban đầu. Mỗi countDown() giảm bộ đếm; await() đợi đến khi bộ đếm về 0. Nó thích hợp cho hai kiểu phối hợp:

- **Ready gate**: hai worker báo rằng đã khởi động; main đợi cả hai sẵn sàng.
- **Start gate**: main mở một cổng chung để cả hai worker bắt đầu đoạn cần kiểm thử.

Ví dụ:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

// Trong mỗi worker:
ready.countDown();
if (!start.await(5, TimeUnit.SECONDS)) {
    throw new TimeoutException("Start gate timed out");
}

// Trong main, sau khi submit cả hai worker:
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new TimeoutException("Workers did not become ready");
}
start.countDown();
~~~

Đây là **đoạn tích hợp** cần main/worker, các import và biến tương ứng; không phải chương trình Java độc lập. Hai worker được phát lệnh gần nhau, nhưng start gate **không bảo đảm chúng thực sự đọc biến cùng lúc**. Hệ điều hành vẫn có thể chạy worker thứ nhất đến hết trước khi worker thứ hai vào vùng lỗi. Vì vậy chỉ dùng start latch chưa đủ để tái hiện lost update chắc chắn.

CountDownLatch là **one-shot**: khi về 0, nó không đặt lại bộ đếm. Mỗi kịch bản/round nên có latch mới nếu cần lập lại quy trình.

### CyclicBarrier: điểm gặp nhau của nhiều thread

CyclicBarrier với parties = 2 buộc hai worker cùng đi tới await() trước khi cả hai được đi tiếp. Đặt barrier **sau bước đọc nhưng trước bước ghi** để giữ hai giá trị snapshot cũ lại:

~~~text
Worker A: read 0 ──┐
                   ├─ bothRead.await() ──> write 1
Worker B: read 0 ──┘                     ──> write 1
                                      Kết quả cuối: 1
~~~

Khác với latch, barrier có thể dùng lại qua nhiều thế hệ (generation) khi đủ số parties đến. Tuy nhiên, nếu một bên timeout, bị interrupt hoặc barrier action thất bại, barrier có thể rơi vào trạng thái **broken** và các bên khác nhận BrokenBarrierException. Trong bài kiểm thử, nên kết thúc round và tạo barrier mới thay vì reset tùy tiện khi worker cũ có thể vẫn đang chạy.

**Chọn công cụ theo mục tiêu:** latch cho điều kiện “đã sẵn sàng / được phép bắt đầu”; barrier cho điều kiện “tất cả đã hoàn thành pha đọc rồi mới chuyển sang pha ghi”.

## 4. Thí nghiệm Java 17+: buộc lost update xuất hiện

Chương trình đầy đủ dưới đây thực hiện ba phép đếm trên **cùng hai worker**:

1. Trường int thông thường, read-modify-write không đồng bộ.
2. ConcurrentHashMap với chuỗi get rồi put: thao tác đơn lẻ thread-safe nhưng toàn chuỗi không nguyên tử.
3. AtomicInteger.incrementAndGet(): mỗi lần tăng là một thao tác nguyên tử.

Cả hai worker lấy snapshot trước barrier; main chỉ công bố kết quả sau khi cả hai Future hoàn thành. Nếu không có timeout hay lỗi môi trường, kết quả sẽ lặp lại ổn định.

**Tệp RaceReplayDemo.java**

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public final class RaceReplayDemo {

    private static final class Counter {
        int value;
    }

    public static void main(String[] args) throws Exception {
        Counter unsafeCounter = new Counter();
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        AtomicInteger atomicCounter = new AtomicInteger();

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        CyclicBarrier bothRead = new CyclicBarrier(2);

        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> worker = () -> {
            ready.countDown();

            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Start gate timed out");
            }

            // Pha 1: hai worker cùng chụp giá trị cũ.
            int oldInt = unsafeCounter.value;
            int oldMap = map.getOrDefault("hits", 0);

            // Pha 2: không worker nào được ghi trước
            // khi cả hai đã đọc xong.
            bothRead.await(5, TimeUnit.SECONDS);

            // Pha 3: hai bản cập nhật sai cùng ghi giá trị 1.
            unsafeCounter.value = oldInt + 1;
            map.put("hits", oldMap + 1);

            // Phép tăng nguyên tử không làm mất bản cập nhật.
            atomicCounter.incrementAndGet();
            return null;
        };

        Future<Void> first = pool.submit(worker);
        Future<Void> second = pool.submit(worker);

        try {
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Workers did not become ready");
            }

            start.countDown();
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            System.out.println("Yeu cau tang: 2");
            System.out.println("int khong dong bo: " + unsafeCounter.value);
            System.out.println("ConcurrentHashMap get/put: "
                    + map.get("hits"));
            System.out.println("AtomicInteger: " + atomicCounter.get());

            if (unsafeCounter.value != 1
                    || !Integer.valueOf(1).equals(map.get("hits"))
                    || atomicCounter.get() != 2) {
                throw new AssertionError("Unexpected interleaving");
            }
        } finally {
            // Mở cổng nếu main thất bại trước khi phát tín hiệu.
            start.countDown();
            first.cancel(true);
            second.cancel(true);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac RaceReplayDemo.java
java RaceReplayDemo
~~~

Stdout khi hai worker hoàn thành bình thường:

~~~text
Yeu cau tang: 2
int khong dong bo: 1
ConcurrentHashMap get/put: 1
AtomicInteger: 2
~~~

**Vì sao kết quả này có thể tái hiện?**

- ready bảo đảm cả hai Callable đã chạy đến điểm sẵn sàng trước khi main mở start.
- Sau khi start mở, mỗi worker lấy oldInt = 0 và oldMap = 0. Chúng chưa thể đi tới phép ghi vì còn đợi ở bothRead.
- CyclicBarrier chỉ giải phóng khi cả hai worker đã đọc xong. Do đó cả hai đều mang giá trị cũ 0 vào pha ghi, bất kể worker nào được scheduler chạy trước sau barrier.
- Cả hai ghi 1 vào int và map: tác vụ tăng thứ hai bị mất. AtomicInteger thực hiện hai lần tăng nguyên tử nên kết quả bằng 2.
- first.get và second.get hoàn thành bình thường cung cấp quan hệ đồng bộ để main quan sát kết quả của worker. Không đọc kết quả trước khi công việc hoàn tất.

Kết quả 1 được **ép bằng lịch thực thi của thí nghiệm**; nó không có nghĩa hai thread luôn tạo lost update trong mọi lịch thực thi sản xuất. Nếu bỏ barrier, một thread có thể đọc sau khi thread kia đã ghi và kết quả đôi khi trở thành 2. Vì vậy chạy được một lần với kết quả 2 không chứng minh mã ban đầu an toàn.

Bài kiểm thử chủ động lắp đặt điểm đồng bộ trong **harness** để tái hiện một lịch sai. Không nên chèn barrier nhân tạo vào đường xử lý nghiệp vụ chỉ nhằm “sửa” race; cách sửa đúng phải làm nguyên tử thao tác cần bảo vệ.

## 5. Vì sao dùng CountDownLatch một mình chưa đủ?

Xem phiên bản chỉ có start gate:

~~~text
Main:     submit(A), submit(B) -> chờ ready(2) -> start.countDown()
Worker A:                                 đọc 0 -> ghi 1
Worker B:                                             đọc 1 -> ghi 2
~~~

Lịch trên hoàn toàn hợp lệ dù cả hai worker cùng đợi một start gate. Nếu bài kiểm thử viết:

~~~java
start.countDown();
first.get();
second.get();
assertEquals(1, counter.value);
~~~

thì assertion có thể thất bại vì ra 2, **không phải vì lỗi đã được sửa**, mà vì test không điều khiển được interleaving. Đây là mã minh họa có biến và assertion của harness kiểm thử (không phải tệp Java độc lập). Một test “đôi lúc đỏ, đôi lúc xanh” khó dùng làm bằng chứng hồi quy.

Cách điều khiển chính xác hơn là đặt một cổng **ngay giữa hai thao tác xung đột**: đọc xong → chờ bên còn lại cũng đọc xong → cho phép ghi. Khi đó điều kiện gây lost update không còn phụ thuộc vào may rủi.

Tuy nhiên, barrier cũng tạo quan hệ happens-before ở chính ranh giới await. Nó có thể làm thay đổi lỗi timing hoặc che một lỗi visibility khác. Chỉ dùng lịch được dàn dựng để chứng minh **lịch cụ thể này có lỗi**; không coi một lịch duy nhất là kiểm định toàn bộ Java Memory Model hay toàn bộ những race có thể xuất hiện.

## 6. Sửa lỗi ở đúng mức nguyên tử

### Trường đếm đơn giản: AtomicInteger

~~~java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
~~~

Nếu hai thread gọi incrementAndGet, kết quả cuối là 2 sau khi cả hai hoàn thành, không cần tự bọc thêm synchronized. AtomicInteger phù hợp cho một biến độc lập với phép cập nhật nguyên tử đơn giản. Việc đọc nhiều biến hoặc duy trì invariant giữa các đối tượng cần cơ chế phối hợp khác.

### Cập nhật trường trong đối tượng: synchronized cả cụm thao tác

~~~java
synchronized (counter) {
    counter.value = counter.value + 1;
}
~~~

Đây là đoạn tích hợp vào chương trình có đối tượng counter. Mọi truy cập liên quan đến invariant phải tuân thủ **cùng một khóa** hoặc cách đồng bộ tương đương; khóa chỉ ở phép đọc hoặc chỉ ở phép ghi là chưa đủ. Nếu hai worker cần barrier trong test, đặt barrier **trước** khối synchronized; không để worker thứ nhất giữ monitor rồi đợi worker thứ hai cũng vào cùng monitor, vì như vậy có thể tự tạo deadlock.

### Map đồng thời: merge/compute nguyên tử cho khóa

~~~java
ConcurrentHashMap<String, Integer> counts =
        new ConcurrentHashMap<>();

counts.merge("hits", 1, Integer::sum);
~~~

merge thực hiện phép kết hợp cho khóa theo cơ chế cập nhật nguyên tử của ConcurrentHashMap, tránh cặp get → put tách rời. Hàm remapping nên ngắn, không có side effect bên ngoài, và không nên chặn lâu. Nếu logic không thể biểu diễn thành một phép cập nhật per-key, phải thiết kế khóa/giao thức cho invariant lớn hơn.

**Đối chiếu sau sửa:** Dùng lại mục tiêu lịch “hai thread cùng đến pha cập nhật” nhưng **không đọc trước rồi ghi sau** nữa. Với AtomicInteger hoặc merge, mỗi worker gọi trọn phép cập nhật nguyên tử; sau khi Future hoàn thành, assert giá trị 2. Không thể giữ nguyên thiết kế sai gồm snapshot trước barrier rồi thay riêng lệnh put bằng một lệnh ghi đè khác và kỳ vọng tự hết race.

## 7. Kiểm thử điều kiện ghép (check-then-act), không chỉ phép tăng

Nhiều race condition có dạng kiểm tra một điều kiện rồi hành động dựa trên kết quả:

~~~java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
~~~

Mỗi phương thức map có thể thread-safe, nhưng **toàn bộ kiểm tra rồi đặt** vẫn không nguyên tử. Hai thread có thể cùng thấy key chưa tồn tại, cùng chạy createValue(), sau đó một kết quả ghi đè kết quả kia.

Có thể tái hiện bằng một barrier đặt **sau containsKey nhưng trước put**, để cả hai chắc chắn quan sát key chưa có. Sau đó kiểm tra createValue() đã chạy hai lần hay chưa, số side effect có bị nhân đôi và giá trị cuối là gì. Bản sửa có thể dùng putIfAbsent hoặc computeIfAbsent tùy hợp đồng; nhớ rằng createValue() có thể có side effect, nên việc tính giá trị trước putIfAbsent vẫn có thể chạy nhiều lần. Với computeIfAbsent của ConcurrentHashMap, mapping function phải tránh tác dụng phụ không an toàn và không được đệ quy cập nhật cùng map theo cách vi phạm hợp đồng API.

Race về invariant còn gặp ở nhiều nơi: kiểm tra số dư rồi trừ tiền, kiểm tra queue rỗng rồi remove, kiểm tra trạng thái rồi phát event, kiểm tra số vé còn lại rồi đặt chỗ. Những bài toán này đòi hỏi thiết kế **điểm tuyến tính hóa** (linearization point) cho nghiệp vụ, không chỉ thêm nhiều thread trong test.

## 8. Các điều kiện để một test đồng thời đáng tin

### Kiểm soát đúng số worker và thời điểm

Khi CyclicBarrier có parties = 2, cần **ít nhất hai luồng thực sự có khả năng chạy** đến await. Nếu dùng Executors.newSingleThreadExecutor với hai task, task thứ nhất đứng chờ barrier còn task thứ hai chưa được chạy: test sẽ kẹt hoặc timeout. Nếu có main cũng gọi await, số parties phải tính cả main.

Không gọi Future.get() của worker đầu tiên **trước khi phát start.countDown()** nếu worker đang chờ start. Hãy submit cả hai → chờ ready → mở start → chờ kết quả.

Tốt nhất, hãy dùng chính xác hai worker như ví dụ và hạn chế bước không liên quan giữa các cổng để giữ dấu vết dễ đọc.

### Đặt timeout cho mọi điểm chờ

Dùng await(timeout, unit), barrier.await(timeout, unit) và Future.get(timeout, unit) để lỗi kiểm thử không treo vô hạn khi một worker:

- Chết trước khi gọi ready.countDown hoặc trước khi đến barrier.
- Ném exception trong pha đọc.
- Bị interrupt, không thể tới đủ parties.
- Không được executor cấp thread hoặc môi trường chạy bị quá tải.

CountDownLatch.await(timeout, unit) trả **false** nếu quá thời gian. CyclicBarrier.await(timeout, unit) có thể ném TimeoutException; các bên liên quan có thể nhận BrokenBarrierException. Future.get(timeout, unit) có thể ném TimeoutException, còn lỗi trong Callable được bọc bằng ExecutionException. Không đánh đồng các trường hợp này thành “race reproduced”.

Những timeout 5 giây trong chương trình là **cơ chế bảo vệ test**. Chúng không định nghĩa một cam kết về độ trễ sản xuất. Trên CI rất chậm có thể cần timeout cấu hình phù hợp; nếu timeout xảy ra, kết quả đúng là test thất bại do điều kiện thực thi không đạt, không được suy luận ra lỗi lost update.

### Luôn giải phóng worker và tài nguyên

Bao quanh phần khởi chạy và chờ bằng try/finally; khi test thất bại, mở các start gate còn đóng, cancel futures và shutdown executor có chủ đích. cancel(true) yêu cầu interrupt nhưng không bảo đảm mọi công việc dừng ngay, nhất là thao tác I/O không hợp tác. Một harness dùng chung executor cần chỉ hủy **các task của test** và để chủ sở hữu quản lý shutdown.

Không dùng Thread.sleep(...) như cơ chế chứng minh thứ tự thực thi: sleep chỉ yêu cầu tối thiểu chờ tương đối, không đảm bảo hai thread gặp nhau ở điểm mong muốn. Thread.yield cũng chỉ là gợi ý scheduler, không tạo barrier hoặc happens-before theo yêu cầu.

### Đảm bảo lỗi trong worker được báo về main

Một test dễ sai nếu chỉ dùng execute(Runnable) rồi main đọc kết quả quá sớm. Submit Callable/Runnable thành Future và gọi get() để:

- Đợi các tác vụ hoàn thành.
- Thấy exception mà worker ném.
- Có điểm đồng bộ giúp main đọc kết quả sau khi worker hoàn tất.

Nếu dùng CountDownLatch done thay cho Future, hãy đặt countDown trong finally của mỗi worker để thất bại không làm main kẹt; **nhưng vẫn cần lưu và báo lỗi worker** để tránh test báo xanh giả. Chỉ đợi done mà không kiểm tra lỗi không đủ.

## 9. Happens-before: test quan sát đúng và không tự che lỗi

Java Memory Model quy định một số quan hệ đồng bộ quan trọng:

- Hành động trước CountDownLatch.countDown() happens-before hành động sau khi một await tương ứng trở về thành công do bộ đếm về 0.
- Với CyclicBarrier, những hành động trước await() happens-before các hành động sau khi những worker khác đi qua await() trong cùng lần gặp barrier.
- Hành động của task trước khi hoàn thành happens-before hành động sau Future.get() thành công cho task đó.
- Một lần unlock monitor happens-before lần lock tiếp theo trên cùng monitor; các thao tác atomic có quy tắc đồng bộ tương ứng.

Đó là lý do main trong ví dụ đọc counter **sau hai Future.get()**, thay vì đọc giữa lúc worker đang chạy. Barrier làm hai bước đọc hoàn tất trước các bước ghi, nhưng **không biến hai phép ghi int sau barrier thành một giao dịch read-modify-write nguyên tử**. Trong chương trình dàn dựng này, hai worker đều ghi giá trị 1, nên kết quả cuối là 1 dù thứ tự ghi ra sao.

Chú ý kỹ: nếu bạn bọc toàn bộ đoạn đọc → barrier → ghi trong synchronized(counter), thread thứ nhất giữ monitor và đứng chờ thread thứ hai, còn thread thứ hai không thể vào monitor để tới barrier. Kịch bản sẽ deadlock/timeout do chính cấu trúc test. Khi kiểm tra **bản sửa**, điều chỉnh vị trí các cổng để các worker gặp nhau **trước khi thực hiện thao tác nguyên tử được bảo vệ**.

Đừng đặt log đồng bộ hoặc callback có side effect vào giữa hai bước cần tạo race mà không xét ảnh hưởng của chúng. Các tác vụ ghi log, mock trả kết quả chặn, debugger breakpoint và profiler có thể thêm đồng bộ, thay đổi timing và khiến lỗi biến mất.

## 10. Viết test tái hiện và test hồi quy như hai hợp đồng

Nên phân biệt:

1. **Reproduction test**: Có chủ đích chạy thuật toán lỗi theo một interleaving cụ thể. Expected result là lost update = 1 nhằm xác nhận harness thực sự ép được lỗi. Ví dụ chạy trực tiếp ở mục 4 thuộc loại này.
2. **Regression test của thuật toán đã sửa**: Ép các worker đi tới ranh giới cập nhật, rồi gọi phép cập nhật nguyên tử/có khóa. Expected result = 2. Đây là bài kiểm tra dùng để bảo vệ bản sửa.
3. **Stress test**: Lặp lại nhiều tác vụ và nhiều lịch thực thi để tìm thêm lỗi chưa biết. Hữu ích bổ sung nhưng không thay thế lịch tái hiện xác định.

Không để bài test của bản sửa tiếp tục **assert lost update = 1**; đó là kết quả lỗi cần loại bỏ. Tách rõ phiên bản lỗi và phiên bản đúng, hoặc dùng tham số kịch bản có tên mang ý nghĩa. Với một lỗi timing đã quan sát ở sản xuất, ghi chính xác: shared state ban đầu, hai bước xung đột, cổng cần chèn và invariant bị vi phạm.

Trong bộ test tự động, kiểm tra cả **đầu ra nghiệp vụ** lẫn **điều kiện điều phối đã thực sự đạt**: đủ worker vào cổng, không timeout hoặc exception, futures hoàn tất và đúng số thao tác dự kiến. Nếu không đạt một trong các điều kiện đó, test phải thất bại rõ ràng, không được coi là “race không xuất hiện”.

## 11. Một số kỹ thuật mở rộng và giới hạn

### Latch, barrier và phaser

| Công cụ | Dùng tốt khi | Lưu ý |
| --- | --- | --- |
| CountDownLatch | Chờ N worker sẵn sàng hoặc mở một start gate | Một lần; không reset |
| CyclicBarrier | N worker phải cùng qua một ranh giới pha | Parties cố định; có thể broken; có thể tái sử dụng |
| Phaser | Nhiều pha, số bên tham gia có thể đăng ký/rút | Cần quản lý registration/termination cẩn thận |
| Semaphore | Giới hạn số task vào một vùng tài nguyên | Không tự tạo điểm gặp nhau “tất cả cùng tới” |
| Future | Đợi task hoàn tất và lan truyền exception | Không ép lịch read/write ở giữa task |

Phaser có thể hữu ích cho kịch bản nhiều round với số worker thay đổi, nhưng với lost update hai worker đơn giản, CyclicBarrier rõ ràng hơn. Đừng thêm độ phức tạp chỉ để có nhiều primitive trong một test.

### Race không thể chứng minh hết chỉ bằng một lịch

Dàn dựng một interleaving chỉ cho thấy chương trình sai **trên interleaving đó**. Nó không liệt kê tất cả đường thực thi có thể xảy ra; chương trình vượt qua một test đồng thời không phải bằng chứng hình thức là không còn data race. Với thuật toán lock-free hoặc vấn đề memory ordering phức tạp, kết hợp code review theo Java Memory Model với công cụ chuyên dụng như JCStress và các stress test có kiểm soát.

Với test kết hợp I/O thật, network hoặc hệ điều hành, có thể không chèn barrier vào đúng giữa các thao tác nội bộ. Hãy thiết kế điểm quan sát/injection phù hợp ở lớp có quyền kiểm soát, tránh ngụy tạo bảo đảm “deterministic” cho phần mà test không điều khiển được.

### Diagnostic khi test timeout

Khi test kẹt, cần phân biệt:

- **Deadlock**: các luồng đợi khóa/điều kiện tạo vòng chờ, không thể tiến.
- **Barrier thiếu party**: worker được submit nhưng chưa chạy do pool quá nhỏ, đã lỗi trước await, hoặc rẽ nhánh bỏ qua await.
- **Livelock/starvation**: luồng vẫn hoạt động hoặc bị thiếu lịch chạy, nhưng công việc không tiến.
- **Race**: lịch thực thi dẫn đến trạng thái sai dù các thread có thể hoàn thành.

Dùng thread dump (ví dụ jcmd hoặc jstack khi JDK và tiến trình hỗ trợ), tên thread, stack trace, số parties đang đợi và log ở các điểm cổng để xác định lý do. Chẩn đoán timeout là việc khác với chứng minh lost update; một test kẹt ở barrier tự nó không chứng minh có race trong thuật toán nghiệp vụ.

## 12. Quy trình áp dụng khi tìm race condition thực tế

**Bước 1 — Nêu invariant.** Ví dụ “sau đúng hai lần tăng thành công, số đếm phải tăng 2”; hoặc “một key chỉ được tạo một lần”. Không bắt đầu bằng lệnh sleep hay vòng lặp vô hạn.

**Bước 2 — Tách thao tác dễ bị chen ngang.** Vẽ read → check/compute → write; tìm vị trí hai thread có thể cùng quan sát trạng thái cũ.

**Bước 3 — Đặt cổng ở ranh giới quan trọng.** Dùng ready latch để chắc hai worker đã chạy; start latch để phát lệnh; barrier để ép cả hai qua pha đọc trước pha ghi. Tránh đặt cổng khi đang giữ một khóa khiến bên kia không thể tới.

**Bước 4 — Giới hạn và quan sát.** Mỗi await/get có timeout; mỗi worker được submit vào executor đủ thread; kiểm tra exception và đợi cả hai hoàn thành trước assertion.

**Bước 5 — Tái hiện kết quả sai.** Với ví dụ lost update, assert kết quả 1 trong harness cố tình lỗi và ghi nhận rằng có hai yêu cầu tăng. Nếu không ra 1, kiểm tra lại phép điều phối, không kết luận mã an toàn.

**Bước 6 — Sửa cơ chế đồng bộ.** Chọn AtomicInteger, synchronized, lock, hoặc cập nhật nguyên tử trên map ở đúng mức invariant; bỏ cách ghép read-modify-write rời rạc.

**Bước 7 — Chạy test hồi quy.** Ép hai worker tới ranh giới cập nhật, xác minh kết quả 2 và không có exception/timeout. Sau đó bổ sung stress test và những lịch khác theo mức độ rủi ro của thuật toán.

## 13. Những lỗi phổ biến cần tránh

| Lỗi trong bài kiểm thử | Tác hại | Cách xử lý |
| --- | --- | --- |
| Dùng Thread.sleep để “canh” race | Phụ thuộc scheduler, máy, tải CI | Latch/barrier ở đúng pha |
| Chỉ có start latch | Hai worker có thể chạy lần lượt | Thêm điểm gặp sau read nếu cần ép stale snapshot |
| Barrier parties = 2 nhưng pool chỉ có 1 thread | Worker đầu chờ worker chưa được lập lịch | Pool đủ worker và timeout |
| Gọi get trước countDown | Main tự đợi công việc đang đợi main | Phát cổng rồi mới đợi futures |
| Không đặt timeout ở await/get | Test có thể treo vô hạn | Dùng timeout hữu hạn, báo rõ nguồn lỗi |
| Đợi latch done nhưng nuốt exception worker | Test báo xanh dù worker thất bại | Future.get hoặc kênh truyền lỗi tương đương |
| Đặt barrier bên trong khóa mà thread còn lại cần | Tự tạo deadlock | Gặp barrier ngoài vùng khóa |
| Đọc shared state trước khi các Future xong | Assertion nhìn trạng thái trung gian | Chờ hoàn thành rồi kiểm tra |
| Coi volatile là phép tăng atomic | Vẫn có lost update | AtomicInteger hoặc đồng bộ cả phép tăng |
| Coi ConcurrentHashMap get+put là atomic | Hai thread ghi đè kết quả | merge/compute/putIfAbsent đúng hợp đồng |
| Test bug vẫn assert ra 1 sau khi sửa | Bản sửa đúng bị coi là thất bại | Đổi oracle của regression test thành 2 |
| Một lịch test xanh rồi kết luận hết race | Bỏ sót nhiều lịch khác | Review thiết kế, test nhiều kịch bản, stress/JCStress khi cần |

## 14. Kết luận kỹ thuật

CountDownLatch giúp thiết lập **điều kiện bắt đầu có kiểm soát**; CyclicBarrier giúp khóa hai worker tại **một ranh giới pha**; Future.get cho phép **chờ, nhận lỗi và quan sát kết quả sau khi hoàn thành**. Kết hợp chúng, ta có thể buộc hai thread cùng đọc giá trị cũ rồi ghi đè nhau, từ đó tái hiện lost update một cách lặp lại được.

Thành công của bài kiểm thử nằm ở việc **chỉ rõ một interleaving gây sai invariant**, chứ không phụ thuộc xác suất scheduler. Sau khi sửa, hãy kiểm tra invariant bằng một oracle đúng và đưa phép cập nhật về một thao tác nguyên tử hoặc vùng đồng bộ thích hợp. Một thí nghiệm xác định là bằng chứng có lỗi ở lịch được dàn dựng; để đánh giá tính đúng đắn tổng thể vẫn cần lý luận về happens-before, tính nguyên tử và những lịch thực thi khác.
