# BlockingDeque, ngắt luồng và quy ước kết thúc luồng xử lý

## Từ hàng đợi hai đầu đến vòng đời của luồng

Một dịch vụ nhận việc thường có hai nhóm luồng: bên sản xuất tạo công việc và bên tiêu thụ lấy công việc để xử lý. Hàng đợi giải quyết việc bàn giao giữa hai nhóm. Nhưng khi dịch vụ cần dừng, một câu hỏi khác xuất hiện: luồng tiêu thụ đang chờ việc sẽ được đánh thức bằng cách nào, và các việc còn lại sẽ đi đâu?

`BlockingDeque<E>` bổ sung khả năng chờ vào hàng đợi hai đầu. Luồng có thể thêm hoặc lấy phần tử ở đầu trước (`first`) hay đầu sau (`last`); một số phương thức chờ khi hàng đợi đầy hoặc rỗng. Khả năng này giúp xây dựng luồng xử lý có điều tiết và chọn hướng lấy việc. Nó cũng tạo ra những điểm chờ cần được đưa vào thiết kế kết thúc.

Cần phân biệt bốn sự kiện:

1. Công việc được chấp nhận vào hàng đợi.
2. Công việc được một luồng lấy ra.
3. Phần xử lý công việc hoàn thành.
4. Luồng tiêu thụ thực sự kết thúc.

Bốn sự kiện này không đồng nghĩa. Hàng đợi rỗng chỉ nói rằng không còn phần tử đang nằm trong hàng đợi tại thời điểm quan sát; một luồng vẫn có thể đang xử lý phần tử đã lấy. Tương tự, gọi `interrupt()` là đưa ra yêu cầu ngắt, không phải chứng nhận luồng đã kết thúc.

Trong bài này, `producer` là bên sản xuất, `consumer` là bên tiêu thụ, `interrupt` là yêu cầu ngắt có sự hợp tác, còn `end message` là thông điệp kết thúc do ứng dụng tự quy ước. Hiểu từng khái niệm trước, sau đó ghép chúng thành một quy trình dừng có thể kiểm chứng.

## Hai đầu, bốn cách xử lý khi chưa thể hoàn thành

`BlockingDeque` kế thừa cả `Deque` và `BlockingQueue`. Với thao tác thêm hoặc lấy, tên phương thức thể hiện cách ứng xử khi điều kiện chưa đáp ứng:

| Mục đích | Ném ngoại lệ nếu không làm được ngay | Trả giá trị báo thất bại ngay | Chờ đến khi có thể làm | Chờ có thời hạn |
| --- | --- | --- | --- | --- |
| Thêm đầu trước | `addFirst(e)` | `offerFirst(e)` | `putFirst(e)` | `offerFirst(e, timeout, unit)` |
| Thêm đầu sau | `addLast(e)` | `offerLast(e)` | `putLast(e)` | `offerLast(e, timeout, unit)` |
| Lấy đầu trước | `removeFirst()` | `pollFirst()` | `takeFirst()` | `pollFirst(timeout, unit)` |
| Lấy đầu sau | `removeLast()` | `pollLast()` | `takeLast()` | `pollLast(timeout, unit)` |

Thêm thất bại vì đầy: `addFirst/addLast` ném `IllegalStateException`, còn `offerFirst/offerLast` trả `false`. Lấy thất bại vì rỗng: `removeFirst/removeLast` ném `NoSuchElementException`, còn `pollFirst/pollLast` trả `null`. Phiên bản có thời hạn của `offer` trả `false` nếu hết thời gian chờ chỗ; phiên bản có thời hạn của `poll` trả `null` nếu hết thời gian chờ phần tử.

Các phương thức `put`, `take` và phiên bản chờ có thời hạn khai báo `InterruptedException`. `peekFirst/peekLast` chỉ xem, trả `null` khi rỗng; `getFirst/getLast` chỉ xem, ném ngoại lệ khi rỗng. Không có phương thức xem đầu hàng đợi rồi chờ cho đến khi xuất hiện phần tử.

Đây là hợp đồng của [BlockingDeque trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html). Hãy chọn cả hướng thao tác lẫn chính sách chờ; chọn đúng một trong hai vẫn chưa đủ.

### Những tên không có First hoặc Last dùng đầu nào?

Khi được dùng như `BlockingQueue`, hàng đợi thêm ở cuối và lấy ở đầu:

~~~text
put(e), offer(e), add(e)      -> thêm Last
take(), poll(), remove()     -> lấy First
peek(), element()            -> xem First
~~~

Do đó `putLast` kết hợp `takeFirst` tạo cách phục vụ vào trước ra trước, thường gọi là FIFO. `putFirst` kết hợp `takeFirst` lại đưa phần tử mới lên trước phần tử cũ, giống cách dùng ngăn xếp.

`push(e)` tương đương thêm đầu trước theo kiểu ném ngoại lệ nếu đầy; `pop()` tương đương lấy đầu trước theo kiểu ném ngoại lệ nếu rỗng. Việc đối tượng có kiểu `BlockingDeque` không biến `push/pop` thành phương thức chờ. Muốn chờ, phải chọn `putFirst/takeFirst` rõ ràng.

Trong một quy trình cần giữ thứ tự, việc cho phép các đoạn mã tùy ý dùng cả hai đầu làm thay đổi ý nghĩa của thứ tự đó. Chẳng hạn, quy tắc “thông điệp kết thúc được thêm sau mọi công việc” không còn đủ nếu một consumer khác lấy từ đầu sau.

### LinkedBlockingDeque và dung lượng chung

Một cách khởi tạo rõ ràng:

~~~java
BlockingDeque<String> inbox = new LinkedBlockingDeque<>(100);
~~~

`100` là giới hạn tổng số phần tử của cả deque, không phải mỗi đầu được 100 phần tử. Nếu đã có 100 phần tử, `putFirst` và `putLast` đều phải chờ chỗ. Chuyển từ thêm cuối sang thêm đầu không vượt qua được giới hạn.

Nếu dùng hàm tạo không tham số, `LinkedBlockingDeque` có giới hạn `Integer.MAX_VALUE`. Trong thực tế, bộ nhớ có thể cạn từ lâu trước khi đạt số phần tử đó. Vì vậy, khi muốn tạo điều tiết ngược tới bên sản xuất, hãy chọn dung lượng có chủ ý. Các đặc điểm này được mô tả ở [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Dung lượng giới hạn phần tử đang chờ, không giới hạn số byte của từng phần tử, không tính toàn bộ dữ liệu producer giữ bên ngoài, và không tính các việc consumer đã lấy ra nhưng chưa xử lý xong. Nếu một công việc giữ mảng lớn hoặc kích hoạt nhiều tác vụ khác, chỉ nhìn `size()` sẽ đánh giá thiếu lượng tài nguyên đang sử dụng.

## Vì sao một vòng lặp lấy việc có thể không bao giờ thoát?

Xét đoạn minh họa, giả sử `process` là phương thức xử lý của ứng dụng:

~~~java
for (;;) {
    Job job = inbox.takeFirst();
    process(job);
}
~~~

Khi không còn việc, `takeFirst()` chờ. Không có suy luận tự động nào rằng “đã rỗng lâu, chắc là hết dữ liệu”. Hàng đợi không biết producer sẽ gửi việc tiếp sau một giây hay không bao giờ gửi nữa.

`BlockingQueue` không có thao tác `close/shutdown` nội tại để tuyên bố hết dữ liệu; ứng dụng cần một quy ước riêng. `BlockingDeque` cũng cần quy ước ấy khi được dùng như kênh truyền việc. Xem [hợp đồng BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Có hai ý định dừng khác nhau:

| Ý định | Điều cần xảy ra | Cơ chế thường dùng |
| --- | --- | --- |
| Kết thúc có trật tự | Ngừng nhận việc mới, xử lý hết các việc đã chấp nhận theo chính sách, rồi consumer thoát | Thông điệp kết thúc hoặc kênh có vòng đời do ứng dụng quản lý |
| Hủy sớm | Yêu cầu consumer bỏ chờ hoặc ngừng phần xử lý khi có thể; xử lý số việc còn lại theo chính sách hủy | Ngắt luồng, cờ hủy có đồng bộ, thao tác đóng tài nguyên phù hợp |

Nếu yêu cầu là xử lý hết việc đã nhận, không thể chỉ ngắt ngay mọi consumer rồi tuyên bố thành công. Nếu yêu cầu là dừng khẩn cấp, cũng không thể mặc định chờ hàng triệu công việc trước một thông điệp kết thúc.

Tên hàm `stop` của ứng dụng phải thể hiện được ý định nào đang được thực hiện: dừng nhận, yêu cầu hủy, hay chờ xác nhận hoàn tất.

## Ngắt luồng là giao thức hợp tác

Mỗi luồng có trạng thái ngắt. Gọi `target.interrupt()` yêu cầu luồng `target` chú ý tới việc ngắt. Phần mã đang chạy quyết định phản ứng theo hợp đồng của thao tác nó đang thực hiện.

Đối với chỗ chờ có thể ngắt như chờ lấy từ deque rỗng hoặc chờ thêm vào deque đầy, `InterruptedException` cho phép mã rời khỏi chỗ chờ. Đối với vòng tính toán thuần CPU không kiểm tra ngắt, cờ được đặt không tự làm vòng lặp dừng. Một thao tác I/O cũng phải xét đúng API; không được suy luận rằng mọi kiểu đọc mạng hoặc đọc tệp đều ném `InterruptedException` khi gọi `interrupt()`.

Ba phương thức dễ nhầm:

| Phương thức | Luồng được kiểm tra hoặc yêu cầu | Có xóa trạng thái ngắt khi kiểm tra? |
| --- | --- | --- |
| `target.interrupt()` | Luồng `target` | Không phải phương thức kiểm tra |
| `target.isInterrupted()` | Luồng `target` | Không |
| `Thread.interrupted()` | Luồng hiện tại đang gọi | Có |

`Thread.interrupted()` là phương thức `static`. Viết qua một biến `Thread` không biến nó thành phép kiểm tra luồng mà biến đó trỏ tới. Khi chỉ muốn quan sát cờ, dùng `isInterrupted()`.

Các quy tắc của trạng thái ngắt và sự khác nhau giữa các điểm chờ nằm trong [Thread của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt()).

### Bắt InterruptedException rồi phải quyết định điều gì?

Khi một chỗ chờ báo `InterruptedException` theo cơ chế ngắt thông thường, trạng thái ngắt đã được xóa khi ngoại lệ được giao cho mã bắt. Do đó, kiểm tra `isInterrupted()` ngay trong `catch` có thể nhận `false` dù nguyên nhân đi vào `catch` chính là yêu cầu ngắt. Chương trình đầy đủ phía dưới kiểm chứng trường hợp này bằng deque luôn rỗng.

Nếu phương thức cho phép truyền ngoại lệ, cách trực tiếp là để bên gọi quyết định:

~~~java
static String receive(BlockingDeque<String> inbox)
        throws InterruptedException {
    return inbox.takeFirst();
}
~~~

Phương thức không nuốt tín hiệu; bên gọi nhận `InterruptedException` và phải xử lý.

Nếu đang ở biên `Runnable.run()`, không thể khai báo thêm checked exception. Một mẫu dừng hợp tác là khôi phục cờ rồi thoát khỏi `run`. Đoạn sau là minh họa cấu trúc; `Job` và `process` thuộc ứng dụng:

~~~java
try {
    for (;;) {
        Job job = inbox.takeFirst();
        process(job);
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseOwnedResources();
}
~~~

Việc khôi phục giúp phần gọi hoặc phần dọn tài nguyên còn cơ hội quan sát trạng thái ngắt. Việc thoát mới làm vòng tiêu thụ kết thúc. Hai hành động có vai trò khác nhau.

Nếu phương thức chuyển `InterruptedException` lên trên thì không cần bắt chỉ để khôi phục rồi lại ném như một quy tắc máy móc. Nếu một thành phần chủ động tiêu thụ tín hiệu ngắt và tiếp tục, nó phải có chính sách được thiết kế rõ, không phải vì muốn bỏ thông báo lỗi.

### Hai cách bắt lỗi làm hỏng ý định dừng

Cách thứ nhất là bắt rồi lặp tiếp, không giữ lại dấu vết:

~~~java
for (;;) {
    try {
        handle(inbox.takeFirst());
    } catch (InterruptedException ex) {
        System.err.println("Interrupted while waiting");
    }
}
~~~

Đây là đoạn minh họa lỗi. Sau `catch`, luồng quay lại `takeFirst`. Nếu deque vẫn rỗng và không có yêu cầu ngắt mới, nó có thể chờ mãi. Dòng log không thay thế hành động dừng.

Cách thứ hai là khôi phục cờ nhưng vẫn cố tiếp tục cùng vòng chờ:

~~~java
for (;;) {
    try {
        handle(inbox.takeFirst());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
}
~~~

Đoạn này cũng là minh họa lỗi đối với chính sách “ngắt thì thoát”. Khi lại gặp chỗ chờ kiểm tra ngắt, nó có thể lặp bắt ngoại lệ rồi khôi phục liên tục, tiêu tốn CPU hoặc sinh log dồn dập. Khôi phục cờ không tự làm câu lệnh `for (;;)` dừng.

Nếu vòng lặp dùng `while (!Thread.currentThread().isInterrupted())`, việc phục hồi cờ có thể làm lần kiểm tra sau kết thúc vòng. Tuy nhiên, vẫn cần xem mọi nhánh điều khiển và mã xử lý việc; một `return` tại biên dừng thường thể hiện ý định rõ hơn.

### Ngắt không hoàn tác việc đã làm

Giả sử consumer đã lấy công việc, ghi một phần kết quả vào cơ sở dữ liệu, rồi bị ngắt khi đang chờ bước tiếp theo. Deque không đưa công việc trở lại và không hoàn tác bản ghi. Tương tự, ngắt producer không xóa những phần tử producer đã gửi thành công trước đó.

Nếu yêu cầu ngắt đua với việc một thao tác hoàn thành, không được kết luận rằng “đã gọi interrupt nên chắc chắn không có phần tử nào được lấy”. Hãy xử lý dựa trên kết quả thật sự của thao tác và trạng thái công việc mà luồng đang sở hữu.

Những yêu cầu như không mất việc, xử lý đúng một lần, hay phục hồi sau tiến trình bị tắt cần giao thức xác nhận, lưu trữ bền vững, tính lặp an toàn hoặc giao dịch phù hợp. Hàng đợi trong bộ nhớ và cờ ngắt không cung cấp các bảo đảm ấy.

## Thông điệp kết thúc: một phần của dữ liệu điều khiển

Một thông điệp kết thúc là phần tử có ý nghĩa “luồng dữ liệu này đã hết việc theo quy ước”. Consumer lấy nó như lấy một phần tử bình thường, nhận ra loại thông điệp rồi thoát.

Không dùng `null` làm dấu kết thúc: deque không chấp nhận phần tử `null`, còn `poll` dùng `null` để báo không lấy được phần tử. Một chuỗi như `"STOP"` cũng dễ đụng dữ liệu thật nếu công việc vốn là văn bản.

Có thể tách loại ngay trong hệ kiểu:

~~~java
sealed interface Message permits Item, End {}

record Item(int number) implements Message {}

enum End implements Message {
    INSTANCE
}
~~~

`Item` mang dữ liệu, `End` mang ý nghĩa điều khiển. Consumer có thể kiểm tra `message == End.INSTANCE` vì đó là hằng `enum`. Không cần một giá trị số đặc biệt như `-1` phải được mọi người nhớ để tránh dùng cho việc thật.

Đối tượng `End.INSTANCE` có thể được thêm nhiều lần vào deque: mỗi lần thêm là một vị trí phần tử riêng, dù cùng tham chiếu. Điều này hữu ích khi cần một thông điệp cho mỗi consumer.

### Đặt dấu kết thúc ở đâu?

Giả sử mọi công việc đều được `putLast` và mọi consumer đều dùng `takeFirst`:

~~~text
First [Item(1), Item(2), End] Last
~~~

Một consumer đi qua các phần tử theo hướng này sẽ lấy công việc trước `End`. Nếu thay bằng `putFirst(End)`:

~~~text
First [End, Item(1), Item(2)] Last
~~~

Consumer có thể thoát ngay và để lại việc. Đây là thay đổi chính sách từ xử lý hết sang vượt qua việc tồn, không phải tối ưu thao tác dừng.

Ngay cả đặt `End` ở cuối cũng chưa đủ nếu vẫn còn producer có thể gửi sau nó:

~~~text
First [Item(1), End, Item(2)] Last
~~~

Bài học không phải là chọn một tên phương thức rồi coi bài toán đã xong. Cần đóng được giai đoạn sản xuất trước khi phát dấu kết thúc, đồng thời thống nhất hướng lấy trong toàn bộ các consumer.

### Một dấu kết thúc có đánh thức tất cả consumer không?

Không. Với ba consumer đều thoát khi lấy `End`, một phần tử `End` chỉ được một consumer lấy. Hai consumer còn lại có thể tiếp tục chờ.

Một giao thức dễ kiểm tra là gửi đúng một dấu cho mỗi consumer đang tham gia giai đoạn kết thúc. Consumer nhận dấu thì thoát ngay và không lấy dấu thứ hai. Trong ví dụ có hai consumer, producer gửi hai dấu.

Có những thiết kế chuyền lại một dấu cho consumer khác, nhưng phải chứng minh không mất dấu, không phát lại sai vòng đời và không treo khi deque đầy. Nếu chưa cần cơ chế ấy, nhiều dấu đơn giản hơn. Nếu số consumer thay đổi động, việc đếm không thể là một số cứng nằm ngoài cơ chế quản lý vòng đời.

### Dấu kết thúc đi qua hàng đợi đầy như thế nào?

Thông điệp điều khiển cũng chiếm dung lượng. Với deque đầy, `putLast(End.INSTANCE)` chờ giống như khi gửi việc.

Nếu consumer vẫn hoạt động và đang xử lý bình thường, chờ chỗ có thể là điều chấp nhận được. Nếu mọi consumer đã hỏng hoặc bị hủy, chờ vô hạn sẽ biến thủ tục dừng thành điểm treo.

Một ứng dụng cần giới hạn thời gian có thể dùng `offerLast(End.INSTANCE, timeout, unit)`. Khi trả `false`, ứng dụng phải xử lý thất bại thật sự: ghi nhận chưa kết thúc có trật tự, yêu cầu hủy phù hợp, kiểm tra lỗi consumer, và chờ xác nhận. Không được bỏ qua `false` rồi tiếp tục báo đã dừng.

Chỉ thêm thời hạn cho thao tác gửi không bảo đảm cả quy trình có cùng thời hạn. Nếu gửi nhiều dấu, mỗi lần chờ một thời hạn riêng sẽ cộng dồn thời gian. Khi yêu cầu là hạn chót chung, hãy theo dõi ngân sách thời gian còn lại.

## Chương trình đầy đủ: hai đầu, ngắt và kết thúc có trật tự

Lưu toàn bộ mã dưới đây vào `DequeTerminationDemo.java`. Chương trình dùng cú pháp Java 17, không cần thư viện ngoài. Mã được biên dịch với `--release 17` và đã chạy bằng OpenJDK Zulu 24.0.2; kết quả dưới đây là stdout của lần chạy đó.

Năm phần kiểm chứng:

1. Thao tác hai đầu, các tên kiểu queue và các tên kiểu stack.
2. Ngắt một consumer đang chuẩn bị chờ trên deque rỗng; quan sát cờ và dọn tài nguyên.
3. Ngắt một producer trên deque luôn đầy; phần tử mới không được chèn.
4. Cho dấu kết thúc vào đầu trước để thấy việc còn bị bỏ lại.
5. Dùng hai dấu ở cuối để hai consumer xử lý hết sáu việc rồi thoát.

Chương trình dùng `CountDownLatch` làm mốc phối hợp, không dùng `Thread.sleep` để đoán lịch chạy. Latch `ready` chỉ chứng minh luồng con đã đi tới đoạn ngay trước thao tác deque; nó không khẳng định luồng chắc chắn đang ở trạng thái `WAITING`. Kết quả vẫn xác định vì không có luồng nào đưa phần tử vào deque rỗng hay lấy khỏi deque đầy của hai phép thử ngắt.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class DequeTerminationDemo {
    sealed interface Message permits Item, End {}
    record Item(int number) implements Message {}
    enum End implements Message { INSTANCE }

    static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Latch timed out");
        }
    }

    static Thread start(String name, Runnable action) {
        Thread thread = new Thread(action, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    static void join(Thread thread, AtomicReference<Throwable> failure)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not terminate: " + thread.getName());
        }
        if (failure.get() != null) {
            throw new AssertionError("Background failure", failure.get());
        }
    }

    static void ends() throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(3);
        deque.putLast("B");
        deque.putFirst("A");
        deque.putLast("C");
        System.out.println("two-ends-content = " + deque);
        System.out.println("take-first = " + deque.takeFirst());
        System.out.println("take-last = " + deque.takeLast());
        deque.put("D");
        System.out.println("queue-put-content = " + deque);
        System.out.println("queue-take = " + deque.take());
        deque.push("X");
        System.out.println("stack-pop = " + deque.pop());
        deque.clear();
        System.out.println("timed-poll-empty = "
                + deque.pollLast(0, TimeUnit.MILLISECONDS));
        try {
            deque.pop();
        } catch (NoSuchElementException ex) {
            System.out.println("empty-pop = " + ex.getClass().getSimpleName());
        }

        BlockingDeque<String> one = new LinkedBlockingDeque<>(1);
        one.putLast("held");
        System.out.println("other-end-offer-full = " + one.offerFirst("urgent"));
        System.out.println("other-end-take = " + one.takeLast());
    }

    static void interruptTake() throws InterruptedException {
        BlockingDeque<String> empty = new LinkedBlockingDeque<>(1);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean insideCatch = new AtomicBoolean(true);
        AtomicBoolean afterRestore = new AtomicBoolean();
        AtomicBoolean cleaned = new AtomicBoolean();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread taker = start("waiting-taker", () -> {
            ready.countDown();
            try {
                empty.takeFirst();
                failure.set(new AssertionError("Unexpected item"));
            } catch (InterruptedException ex) {
                caught.set(true);
                insideCatch.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                afterRestore.set(Thread.currentThread().isInterrupted());
            } catch (Throwable ex) {
                failure.set(ex);
            } finally {
                cleaned.set(true);
            }
        });
        await(ready);
        taker.interrupt();
        join(taker, failure);
        System.out.println("take-interrupted = " + caught.get());
        System.out.println("status-inside-catch = " + insideCatch.get());
        System.out.println("status-after-restore = " + afterRestore.get());
        System.out.println("cleanup-ran = " + cleaned.get());
        System.out.println("taker-terminated = " + !taker.isAlive());

        List<Boolean> flags = new ArrayList<>();
        Thread probe = start("flag-probe", () -> {
            Thread.currentThread().interrupt();
            flags.add(Thread.currentThread().isInterrupted());
            flags.add(Thread.interrupted());
            flags.add(Thread.currentThread().isInterrupted());
        });
        join(probe, failure);
        System.out.println("flag-probe = " + flags);
    }

    static void interruptPut() throws InterruptedException {
        BlockingDeque<String> full = new LinkedBlockingDeque<>(1);
        full.putLast("kept");
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread producer = start("waiting-producer", () -> {
            ready.countDown();
            try {
                full.putFirst("not-inserted");
                failure.set(new AssertionError("Unexpected insertion"));
            } catch (InterruptedException ex) {
                caught.set(true);
                Thread.currentThread().interrupt();
            } catch (Throwable ex) {
                failure.set(ex);
            }
        });
        await(ready);
        producer.interrupt();
        join(producer, failure);
        System.out.println("put-interrupted = " + caught.get());
        System.out.println("after-producer-interrupt = " + full);
    }

    static void markerAtWrongEnd() throws InterruptedException {
        BlockingDeque<Message> deque = new LinkedBlockingDeque<>(3);
        deque.putLast(new Item(1));
        deque.putLast(new Item(2));
        deque.putFirst(End.INSTANCE);
        System.out.println("front-stop-taken-first = "
                + (deque.takeFirst() == End.INSTANCE));
        System.out.println("work-left-after-front-stop = " + deque.size());
    }

    static void graceful() throws InterruptedException {
        BlockingDeque<Message> inbox = new LinkedBlockingDeque<>(2);
        ConcurrentLinkedQueue<Integer> completed = new ConcurrentLinkedQueue<>();
        AtomicInteger endMessages = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Runnable consume = () -> {
            try {
                for (;;) {
                    Message message = inbox.takeFirst();
                    if (message == End.INSTANCE) {
                        endMessages.incrementAndGet();
                        return;
                    }
                    completed.add(((Item) message).number());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (Throwable ex) {
                failure.compareAndSet(null, ex);
            }
        };
        Thread first = start("consumer-1", consume);
        Thread second = start("consumer-2", consume);
        boolean sentAll = false;
        try {
            for (int n = 1; n <= 6; n++) {
                if (!inbox.offerLast(new Item(n), 5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Could not send item");
                }
            }
            for (int n = 0; n < 2; n++) {
                if (!inbox.offerLast(End.INSTANCE, 5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Could not send end message");
                }
            }
            sentAll = true;
        } finally {
            if (!sentAll) {
                first.interrupt();
                second.interrupt();
            }
        }
        join(first, failure);
        join(second, failure);
        List<Integer> sorted = new ArrayList<>(completed);
        Collections.sort(sorted);
        System.out.println("graceful-completed = " + sorted);
        System.out.println("graceful-end-messages = " + endMessages.get());
        System.out.println("graceful-consumers-terminated = "
                + (!first.isAlive() && !second.isAlive()));
        System.out.println("graceful-inbox-empty = " + inbox.isEmpty());
    }

    public static void main(String[] args) throws InterruptedException {
        ends();
        interruptTake();
        interruptPut();
        markerAtWrongEnd();
        graceful();
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 DequeTerminationDemo.java
java DequeTerminationDemo
~~~

Stdout:

~~~text
two-ends-content = [A, B, C]
take-first = A
take-last = C
queue-put-content = [B, D]
queue-take = B
stack-pop = X
timed-poll-empty = null
empty-pop = NoSuchElementException
other-end-offer-full = false
other-end-take = held
take-interrupted = true
status-inside-catch = false
status-after-restore = true
cleanup-ran = true
taker-terminated = true
flag-probe = [true, true, false]
put-interrupted = true
after-producer-interrupt = [kept]
front-stop-taken-first = true
work-left-after-front-stop = 2
graceful-completed = [1, 2, 3, 4, 5, 6]
graceful-end-messages = 2
graceful-consumers-terminated = true
graceful-inbox-empty = true
~~~

### Đọc kết quả theo đúng điều đã được chứng minh

`two-ends-content = [A, B, C]` cho thấy thêm `A` ở đầu trước đưa nó lên trước `B`, còn thêm `C` ở cuối đặt nó sau `B`. Sau khi lấy `A` và `C`, `put("D")` thêm cuối nên nội dung là `[B, D]`; `take()` lấy đầu và trả `B`. Hai dòng này tránh việc học thuộc `put/take` mà không biết đầu thao tác.

`stack-pop = X` xác nhận cặp `push/pop` dùng cùng đầu. Sau `clear`, `pollLast` có thời hạn bằng không trả `null`, trong khi `pop` trên deque rỗng ném `NoSuchElementException`. Chọn kiểu có khả năng chờ không thay đổi hợp đồng của các phương thức khác.

`other-end-offer-full = false` kiểm chứng dung lượng dùng chung: phần tử `held` ở deque dung lượng một làm `offerFirst` thất bại dù trước đó `held` được thêm ở đầu sau.

Ba dòng về ngắt tách rõ ba việc:

- `take-interrupted = true`: thao tác chờ đã báo ngoại lệ.
- `status-inside-catch = false`: cờ đã được tiêu thụ khi ngoại lệ được giao.
- `status-after-restore = true`: chính câu lệnh khôi phục trong `catch` đã đặt lại cờ.

`cleanup-ran = true` và `taker-terminated = true` là hai xác nhận khác nhau. Có chạy khối `finally` không đủ để suy luận mọi mã sau nó đã kết thúc; vì vậy chương trình còn chờ `join` và kiểm tra luồng đã hết sống.

`flag-probe = [true, true, false]` đến từ một luồng thăm dò riêng. Nó tự ngắt, quan sát không xóa, gọi phép đọc có xóa, rồi quan sát lại. Luồng chính không tự đặt cờ ngắt của mình, nên các thí nghiệm sau không vô tình nhận yêu cầu ngắt từ thí nghiệm trước.

`after-producer-interrupt = [kept]` chứng minh phần tử cũ vẫn còn, còn `not-inserted` không được thêm trong trường hợp full-queue đã thiết kế. Kết luận chỉ áp dụng cho thao tác bị gián đoạn đó; nó không hứa producer chưa từng gửi việc nào trước khi bị ngắt.

`front-stop-taken-first = true` và `work-left-after-front-stop = 2` là phản ví dụ cho cách chèn dấu dừng vào trước backlog rồi gọi đó là kết thúc có trật tự.

Phần cuối chỉ in sau khi chờ cả hai consumer. Danh sách kết quả được sao chép và sắp xếp để stdout ổn định. `[1, 2, 3, 4, 5, 6]` chứng minh các công việc đã được ghi nhận đầy đủ trong thí nghiệm; nó không chứng minh thứ tự hoàn thành của hai consumer là 1 rồi 2 rồi 3. Một consumer có thể lấy việc trước nhưng hoàn thành sau consumer khác.

`graceful-end-messages = 2` xác nhận hai thông điệp đã được lấy. Kết hợp số việc, số dấu, trạng thái hai luồng và deque rỗng mới tạo thành bằng chứng phù hợp với giao thức đơn giản này.

### Vì sao còn có timeout, daemon và bộ giữ lỗi?

Giới hạn năm giây trong `await`, `join` và `offerLast` giúp phép thử báo thất bại khi không tiến triển. Đó là giới hạn bảo vệ thí nghiệm, không phải cam kết thời gian của deque hay một thông số vận hành được khuyến nghị cho mọi dịch vụ.

Các luồng thử được đặt daemon để một lỗi trong thí nghiệm không giữ JVM chạy mãi. Việc kết thúc đúng vẫn được kiểm tra bằng `join` và `isAlive`. Trong dịch vụ thật, đổi consumer thành daemon không phải giao thức dừng; JVM có thể thoát mà không chờ xử lý hoặc dọn tài nguyên của daemon.

`AtomicReference<Throwable>` chuyển lỗi từ luồng con về luồng chính. Nếu chỉ nhìn luồng đã chết rồi kết luận thành công, một consumer ném ngoại lệ và chết sớm cũng có thể bị hiểu lầm là đã kết thúc có trật tự.

Trong ví dụ, `join` có thời hạn nhưng không tin rằng hết chờ đồng nghĩa luồng đã xong. Nó kiểm tra `isAlive` rồi báo lỗi nếu còn sống. Đây là điểm cần giữ khi chuyển thí nghiệm thành một quy trình giám sát thực tế.

## Thiết kế một quy trình dừng có trật tự

Một thiết kế dùng `putLast/takeFirst` và thông điệp kết thúc có thể chia thành các bước có trách nhiệm rõ ràng:

1. Ngừng chấp nhận nguồn công việc mới.
2. Chờ các producer đang tham gia hoàn thành việc gửi hoặc báo kết quả gửi cuối cùng.
3. Xác nhận không producer nào có thể thêm việc sau mốc kết thúc.
4. Gửi đủ dấu kết thúc, bằng đúng hướng đã thống nhất.
5. Chờ mọi consumer kết thúc và thu thập lỗi của chúng.
6. Kiểm tra những điều kiện hoàn tất của ứng dụng, rồi mới báo thành công.

Trong ví dụ, luồng chính là producer duy nhất nên kết thúc vòng `for` gửi sáu việc là một mốc đơn giản. Với nhiều producer, một thành phần điều phối phải chờ tất cả producer hoặc đóng một cổng nhận việc được đồng bộ đúng trước khi phát dấu.

Một cờ `accepting = false` riêng lẻ chưa chắc đóng được cổng. Nếu producer kiểm tra cờ, bị tạm dừng, rồi thêm việc sau khi thành phần khác đã gửi `End`, thứ tự vẫn sai. Phép quyết định nhận việc và mốc đóng cần có giao thức chung; đó là logic vòng đời của ứng dụng, không phải thứ deque tự suy ra.

### Đã lấy hết việc khác với đã hoàn thành hết việc

Với hai consumer, consumer thứ nhất có thể nhận `End` và thoát trong lúc consumer thứ hai vẫn xử lý công việc nó đã lấy trước đó. Dấu dừng ở cuối bảo vệ thứ tự lấy từ hàng đợi trong điều kiện đã nêu, không buộc mọi phần xử lý trước đó hoàn thành cùng lúc.

Vì vậy, phải chờ tất cả consumer hoặc một bộ đếm xác nhận hoàn thành tương ứng. Một lần thấy `inbox.isEmpty()` không thay thế được bước chờ.

Ví dụ dùng ghi số vào `ConcurrentLinkedQueue` làm phần xử lý rất ngắn. Trong ứng dụng thật, “hoàn thành” phải được định nghĩa tại nơi có kết quả cần bảo đảm: ghi tệp xong, giao dịch đã commit, phản hồi đã lưu, hay chỉ mới gửi yêu cầu cho dịch vụ khác. Nếu consumer tạo tác vụ bất đồng bộ rồi tiếp tục, việc consumer thoát không tự chứng minh những tác vụ con đã hoàn tất.

### Xử lý lỗi consumer là một phần của giao thức

Nếu một consumer chết trước khi nhận dấu, số dấu dự kiến có thể không còn khớp số luồng đang chạy. Các producer cũng có thể bị kẹt khi deque đầy và không còn người lấy.

Điều phối cần thu thập lỗi và chọn một trong các kết quả có tên rõ ràng: đã xử lý xong, kết thúc có lỗi với việc còn lại, hoặc hủy và chuyển số việc chưa làm sang nơi khác. Không báo thành công chỉ vì cuối cùng không còn luồng sống.

Chính sách thử lại phải tính tới việc consumer đã làm một phần tác động trước khi lỗi. Đưa công việc lại vào đầu deque có thể làm công việc đó được xử lý lần nữa; gửi lại vô hạn còn có thể làm công việc khác bị đói. Các lựa chọn như mã định danh công việc, số lần thử, nơi lưu việc lỗi và xử lý lặp an toàn thuộc thiết kế nghiệp vụ.

## Khi cần hủy sớm

Một quy trình hủy sớm thường bắt đầu bằng ngừng nhận việc mới, phát yêu cầu ngắt tới các luồng thuộc quyền quản lý, rồi chờ chúng phản ứng. Các việc đang chờ và đang xử lý phải có chính sách riêng.

Nếu phần xử lý là vòng tính toán dài, hãy tạo điểm kiểm tra ở ranh giới công việc hợp lý. Đoạn minh họa sau giả định mỗi `processChunk` là một bước hữu hạn và không bỏ qua ngoại lệ ngắt từ các API nó gọi:

~~~java
while (hasNextChunk()) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processChunk();
}
~~~

Kiểm tra trước mỗi khối tạo cơ hội dừng, không tạo một giao dịch nguyên tử giữa “kiểm tra” và “xử lý”. Yêu cầu ngắt vẫn có thể tới ngay sau lần kiểm tra. Độ trễ hủy phụ thuộc độ dài mỗi khối và các điểm chờ thực tế.

Nếu một tài nguyên có cơ chế hủy riêng, chẳng hạn thao tác đóng kênh hoặc hủy truy vấn theo API của nó, cần dùng đúng hợp đồng đó. Không gọi `Thread.stop` để ép kết thúc. Ép luồng dừng giữa lúc cập nhật dữ liệu có thể phá vỡ tính nhất quán của trạng thái mà các luồng khác cùng sử dụng.

### Cờ volatile không tự đánh thức take

Đoạn minh họa sau có vấn đề nếu `requestStop` chỉ đặt `running = false`:

~~~java
while (running) {
    Job job = inbox.takeFirst();
    process(job);
}
~~~

`volatile` có thể giúp lần đọc `running` sau nhìn thấy giá trị mới, nhưng consumer đang chờ trong `takeFirst` chưa quay lại để đọc cờ. Cần một cơ chế rời chỗ chờ: ngắt, một thông điệp điều khiển đúng giao thức, hoặc chờ có thời hạn rồi kiểm tra trạng thái.

Nếu chọn `pollFirst(timeout, unit)`, `null` chỉ có nghĩa chưa lấy được phần tử trong lần chờ đó. Nó không chứng minh mọi producer đã kết thúc. Điều kiện dừng phải kết hợp trạng thái vòng đời được đồng bộ, không phải “thấy null là hết dữ liệu”.

Thời hạn chờ ngắn giúp phản ứng sớm hơn với cờ nhưng tăng số lần thức dậy. Thời hạn dài giảm số lần kiểm tra nhưng tăng độ trễ. Đây là đánh đổi của thiết kế thăm dò; thông điệp hoặc ngắt thường diễn đạt một sự kiện cụ thể hơn.

### Dọn tài nguyên và giữ lại công việc đang sở hữu

Sau khi `takeFirst` trả một `Job`, trách nhiệm tạm thời đã chuyển sang consumer. Nếu consumer bị ngắt trong `process`, cần biết nó đang giữ công việc nào để ghi trạng thái thích hợp.

Một khối `finally` phù hợp để giải phóng tài nguyên do luồng sở hữu. Nhưng việc phát sinh một ngoại lệ khác trong dọn tài nguyên không được làm mất dấu lỗi gốc; cách quản lý tài nguyên phải giữ thông tin thất bại có ích. Nếu dùng tài nguyên `AutoCloseable`, xem xét `try-with-resources` theo hợp đồng đóng của tài nguyên.

Không mặc định rằng luôn đưa công việc trở lại deque là an toàn. Nếu deque đầy và consumer cố `putFirst` trong lúc đang thoát, nó lại có thể chờ vô hạn; nếu tác động bên ngoài đã xảy ra, thử lại có thể nhân đôi tác động. Kết quả hủy phải được giải quyết bằng một chính sách cụ thể, không bằng một câu lệnh chèn lại chung cho mọi tình huống.

## Chờ xác nhận: join, latch và executor

Gọi `interrupt` xong là thời điểm phát yêu cầu. Chờ luồng kết thúc là một bước tiếp theo. Với luồng do ứng dụng trực tiếp tạo, `join` là một cách chờ; bản có thời hạn cần kiểm tra lại luồng còn sống hay không.

Khi `join` xác nhận luồng đã kết thúc, các hành động trong luồng đó có quan hệ happens-before với phần mã đi tiếp sau khi phát hiện kết thúc. Vì vậy, ví dụ chỉ đọc danh sách `flags` sau `join`. Danh sách ấy chỉ có một luồng ghi và không bị đọc đồng thời khi đang ghi; không cần dùng nó như một danh sách chia sẻ cho nhiều bên cập nhật. Quy tắc về kết thúc luồng nằm trong [JLS 17.4.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).

Một `CountDownLatch` có thể xác nhận nhiều consumer đã đi qua điểm hoàn thành mà ứng dụng quy định. Nhưng nếu đặt `countDown` trong `finally`, việc đếm về không cũng có thể bao gồm luồng kết thúc do lỗi. Cần giữ thêm kết quả hoặc lỗi; latch chỉ truyền sự kiện đã tới điểm đó. Xem [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

### shutdown của executor không đóng deque bên trong tác vụ

Nếu một `Runnable` chạy vòng `takeFirst` dài hạn bên trong `ExecutorService`, gọi `shutdown()` không tự đưa `End` vào deque và không làm tác vụ đang chạy rời `takeFirst`. Executor ngừng nhận tác vụ mới nhưng tác vụ consumer đã gửi vẫn cần hoàn thành.

`shutdownNow()` cố gắng dừng tác vụ đang chạy, thường bằng ngắt; mã phải hợp tác. `awaitTermination` chỉ chờ, có thể hết thời hạn hoặc chính luồng đang chờ bị ngắt. Đây là sự khác nhau giữa yêu cầu kết thúc và xác nhận kết thúc trong [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Nếu dùng `Future.cancel(true)`, đó là yêu cầu hủy có thể kèm ngắt luồng thực thi theo hợp đồng triển khai. Trạng thái đã hủy của `Future` không phải bằng chứng rằng mọi phần dọn tài nguyên bên trong đã chạy xong. Nếu ứng dụng cần biết một tài nguyên đã được giải phóng, hãy có xác nhận cho đúng sự kiện đó. Xem [Future.cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean)).

## Các lỗi phối hợp thường gặp

### Giữ khóa ứng dụng trong lúc chờ hàng đợi

Giả sử producer giữ `synchronized(lock)` rồi gọi `putLast` khi đầy. Consumer cần chính `lock` để hoàn tất công việc trước khi có thể lấy tiếp. Producer chờ chỗ, consumer chờ khóa; một deque an toàn cho nhiều luồng không sửa được vòng chờ do ứng dụng tạo.

Hãy sắp xếp để không giữ tài nguyên mà phía bên kia cần trong lúc chờ deque. Tính nguyên tử của một cập nhật nghiệp vụ và sự điều tiết của kênh truyền cần được thiết kế cùng nhau; bọc tất cả vào một khóa lớn có thể làm mất khả năng tiến triển.

### Để producer chiếm hết các luồng trong cùng pool

Nếu mọi luồng của một pool hữu hạn đều chạy producer đang kẹt trong `putLast`, còn consumer chỉ nằm trong danh sách tác vụ chờ của pool, không có consumer nào được chạy để tạo chỗ. Có đủ tác vụ tiêu thụ trên giấy không có nghĩa có tài nguyên thực thi cho chúng.

Cần kiểm tra cả quan hệ giữa hàng đợi công việc của ứng dụng và hàng đợi tác vụ của executor. Giải pháp có thể là tách tài nguyên thực thi, dùng giao thức gửi không chờ với xử lý từ chối, hoặc tổ chức công việc khác. Tăng dung lượng chỉ có thể trì hoãn tình trạng đầy.

### clear không có nghĩa đóng

`clear()` loại bỏ phần tử đang nằm trong deque. Nó không gửi thông điệp kết thúc cho consumer đang chờ trên một deque rỗng, cũng không dừng công việc consumer đã lấy.

Ngay cả nếu thao tác xóa tạo chỗ cho producer, producer lại có thể gửi thêm việc. Nếu dùng xóa trong quy trình hủy, phải ngừng bên gửi và xác định số việc bị loại bỏ; không thể coi việc xóa là toàn bộ quy trình hủy.

### Kiểm tra isEmpty rồi mới take

Đoạn `if (!inbox.isEmpty()) inbox.takeFirst()` không bảo đảm `takeFirst` sẽ không chờ. Consumer khác có thể lấy phần tử giữa hai thao tác. Nếu ý định là thử lấy ngay, gọi `pollFirst` và xử lý `null`.

Tương tự, `remainingCapacity() > 0` không giữ chỗ cho một lần `putLast` sau đó. Kết quả của chính `offerLast` mới cho biết lần gửi đó có được chấp nhận ngay hay không.

### Tưởng bàn giao an toàn đồng nghĩa đối tượng bên trong bất biến

Việc công bố phần tử qua cấu trúc đồng thời có quy tắc hiển thị bộ nhớ. Nhưng nếu producer tiếp tục sửa một danh sách nằm trong `Job` sau khi đã gửi, deque không tự khóa danh sách ấy cho consumer.

Trong ví dụ, `Item` chỉ chứa `int` và `End` là hằng enum nên việc bàn giao đơn giản. Với dữ liệu phức tạp, có thể chọn dữ liệu bất biến, bản sao thích hợp hoặc quy tắc chuyển quyền sở hữu: sau khi gửi thành công, producer không sửa nội dung đó nữa. Một `record` có trường trỏ tới danh sách mutable vẫn không tự làm danh sách bất biến.

## Chọn cơ chế theo điều cần bảo đảm

| Tình huống | Hướng thiết kế | Điều phải xác nhận thêm |
| --- | --- | --- |
| Nguồn dữ liệu hữu hạn, muốn xử lý hết | Đóng giai đoạn gửi, thêm dấu cuối, consumer lấy đầu | Không có việc gửi sau dấu; đủ dấu; tất cả consumer hoàn thành |
| Consumer đang chờ nhưng cần hủy sớm | Ngắt luồng do thành phần quản lý sở hữu | Consumer bắt đúng, thoát, dọn tài nguyên và được chờ |
| Xử lý dài không có chỗ chờ | Kiểm tra cờ ở ranh giới khối việc | Độ trễ hủy và số tác động đã thực hiện |
| Muốn kiểm tra trạng thái định kỳ | `pollFirst` có thời hạn | `null` không phải hết dữ liệu; trạng thái kết thúc phải đáng tin |
| Không gửi được dấu vì đầy | Gửi có thời hạn và theo dõi lỗi consumer | Có nhánh thất bại hoặc hủy; không báo hoàn tất giả |
| Phải phục hồi sau tiến trình chết | Kênh bền vững và xác nhận nghiệp vụ phù hợp | Quy tắc thử lại, lặp an toàn và lưu trạng thái |

Khi dùng cả hai đầu để ưu tiên hoặc thử lại, hãy viết lại điều kiện kết thúc cho đúng các hướng đó. Một giao thức được chứng minh cho `putLast/takeFirst` không tự áp dụng cho một hệ thống khác có `putFirst` và `takeLast` xen kẽ.

## Bài tập tự kiểm tra

### 1. Dung lượng một, hai đầu có hai chỗ không?

Deque dung lượng một đã có `A` bằng `putLast`. Lệnh `offerFirst("B")` trả gì?

**Đáp án:** `false`. Giới hạn áp dụng cho tổng số phần tử; đầu trước không có một vùng dung lượng riêng.

### 2. Vì sao pop không chờ?

Một deque đang rỗng. Đổi biến từ kiểu `Deque` sang `BlockingDeque` rồi gọi `pop()` có làm nó chờ việc mới không?

**Đáp án:** Không. `pop` vẫn ném `NoSuchElementException` khi rỗng. Muốn chờ lấy ở đầu trước, dùng `takeFirst` và xử lý khả năng ngắt.

### 3. Cờ false trong catch có chứng minh chưa bị ngắt không?

Consumer nhận `InterruptedException` từ một lần chờ `takeFirst`. Trong `catch`, `isInterrupted` là `false`.

**Đáp án:** Không. Đây là kết quả phù hợp với việc ngoại lệ được giao sau khi cờ đã được xóa. Phải xử lý ngoại lệ theo chính sách hủy; nếu không truyền lên, mẫu phổ biến ở biên `Runnable` là khôi phục cờ và thoát.

### 4. Một End cho bốn consumer

Bốn consumer đều lấy đầu trước và thoát khi gặp `End`. Producer gửi một `End` rồi chờ cả bốn.

**Đáp án:** Chỉ một consumer lấy phần tử đó. Ba consumer còn lại có thể chờ mãi. Với giao thức mỗi consumer lấy một dấu rồi thoát, gửi đủ bốn dấu sau khi mọi producer đã hoàn thành.

### 5. End ở cuối nhưng còn producer đang gửi

Thành phần điều phối gửi `End` vào cuối khi producer thứ hai chưa kết thúc. Producer ấy gửi thêm `Item(9)` sau `End`.

**Đáp án:** Thứ tự gửi không bảo đảm consumer đi tới `Item(9)`. Cần một mốc kết thúc giai đoạn sản xuất có đồng bộ; không dùng `isEmpty` hay một lần nhìn cờ để thay cho việc đóng cổng nhận và chờ các lượt gửi đang tham gia.

### 6. isEmpty là true, vì sao chưa thể đóng tệp kết quả?

Một consumer vừa lấy công việc cuối và đang ghi tệp. Luồng điều phối nhìn deque rỗng.

**Đáp án:** Công việc đã ra khỏi hàng đợi nhưng chưa hoàn thành. Chờ consumer hoặc xác nhận hoàn thành nghiệp vụ trước khi đóng tài nguyên nó đang dùng.

### 7. Chỉ đặt volatile running thành false

Consumer đang ở `takeFirst` trên deque rỗng. Luồng khác đặt cờ dừng.

**Đáp án:** Cờ nhìn thấy được không tự đánh thức thao tác chờ. Cần thêm ngắt, thông điệp điều khiển đúng giao thức, hoặc thiết kế thăm dò có thời hạn. Việc thêm cơ chế phải khớp ý định xử lý hết hay hủy sớm.

### 8. Kết quả sắp xếp có chứng minh thứ tự hoàn thành không?

Hai consumer ghi số việc đã xử lý vào cấu trúc đồng thời; sau khi chờ chúng, chương trình sắp xếp kết quả thành `[1, 2, 3, 4, 5, 6]`.

**Đáp án:** Nó chứng minh tập kết quả trong thí nghiệm, không chứng minh lịch hoàn thành theo thứ tự. Muốn giữ thứ tự kết quả, cần cơ chế đánh số và ghép kết quả theo thứ tự hoặc cách thực thi phù hợp; tính FIFO của lúc lấy không đủ khi nhiều consumer xử lý song song.
