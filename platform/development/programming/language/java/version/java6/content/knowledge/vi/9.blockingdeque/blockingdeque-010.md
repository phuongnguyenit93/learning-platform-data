# Kiểm thử quá tải, timeout và ngắt khi chờ

## 1. Mục tiêu: chứng minh hành vi và bảo vệ bộ kiểm thử khỏi bị treo

Một bài kiểm thử cho `BlockingDeque` không chỉ cần xác nhận lấy ra đúng phần tử. Nó còn phải trả lời ba câu hỏi: khi không đủ điều kiện thì thao tác có kết thúc sai không; khi điều kiện được đáp ứng thì nó có tiếp tục không; khi bị ngắt thì tác vụ có thoát đúng cách không.

Trong chương trình đồng thời, một kết quả “chạy thành công trên máy tôi” có thể đến từ thứ tự chạy thuận lợi. Ngược lại, một bài kiểm thử chờ vô hạn có thể làm cả bộ kiểm thử ngừng tiến triển khi gặp lỗi. Vì thế phải kiểm tra cả **hợp đồng thao tác** và **giới hạn chờ của chính bộ kiểm thử**.

Quá tải trong bài này là tình huống bên tạo muốn thêm công việc trong khi deque hữu hạn đã đầy. Nó khác với trường hợp bên lấy phải chờ vì deque rỗng, nhưng cả hai đều cần kiểm thử đường chờ và đường ngắt.

## 2. Lập ma trận hành vi trước khi viết mã

Với `BlockingDeque`, phương thức thêm/lấy có các dạng không chờ, chờ hoặc chờ có thời hạn. `takeFirst`/`takeLast` chờ dữ liệu; `putFirst`/`putLast` chờ chỗ; `poll` có thời hạn trả `null` nếu chưa lấy được; `offer` có thời hạn trả `false` nếu chưa thêm được. Các lời gọi chờ có thể ném `InterruptedException`. [Hợp đồng BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

| Tình huống | Kích thích do kiểm thử tạo ra | Điều phải kiểm tra |
| --- | --- | --- |
| Deque đầy | Thử `offer` không chờ | Trả `false`, dữ liệu cũ còn nguyên |
| Deque đầy | Dùng `add` | Ném `IllegalStateException`, không thêm phần tử |
| Deque rỗng | Gọi `take`, sau đó thêm dữ liệu | Chưa hoàn thành trước lúc thêm; sau đó lấy đúng và xóa phần tử |
| Deque đầy | Gọi `put`, sau đó lấy bớt | Chưa hoàn thành trước khi có chỗ; sau đó thêm thành công |
| Không có dữ liệu/chỗ trong toàn bộ khoảng chờ | Gọi `poll`/`offer` có thời hạn | Nhận `null`/`false`, trạng thái không thay đổi |
| Điều kiện vẫn chưa thỏa mãn | Ngắt luồng đang thực hiện lời gọi chờ | Nhận đúng `InterruptedException`; tác vụ kết thúc |
| Có nhiều bên tạo/lấy | Chạy một đợt tải có định danh công việc | Không vượt giới hạn, không mất/trùng ngoài chính sách đã định |

Cần xét cả hai đầu. Nhưng không gộp quá nhiều điều kiện vào một ca: bài kiểm thử timeout không nên đồng thời có bên tạo ngẫu nhiên thêm dữ liệu, vì khi đó có phần tử và hết thời gian đều có thể là kết quả hợp lệ.

## 3. Ba loại thời hạn rất dễ nhầm

Ví dụ `queue.pollFirst(40, MILLISECONDS)` được quan sát bằng `future.get(5, SECONDS)`. Có ít nhất hai thời hạn độc lập:

- **Thời hạn nghiệp vụ của thao tác:** 40 ms mà `pollFirst` dùng để chờ phần tử.
- **Thời hạn của bộ kiểm thử:** 5 giây dành cho việc đợi tác vụ hoàn tất và báo lỗi nếu không tiến triển.

Ngoài ra còn có cửa sổ quan sát như `get(80, MILLISECONDS)` để kiểm tra tác vụ chưa thông báo hoàn thành trong một giai đoạn không có dữ liệu/chỗ trống.

`Future.get` hết thời hạn ném `TimeoutException` ở luồng quan sát; việc đó không tự hủy tác vụ và không chứng minh lời gọi deque đã kết thúc. Hủy là một thao tác riêng. Lỗi phát sinh bên trong tác vụ được quan sát qua `ExecutionException`, với nguyên nhân gốc trong `getCause()`. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Vì vậy không viết bài kiểm thử như “bắt được `TimeoutException` từ `Future.get` thì `poll` đã hết thời gian đúng”. Muốn kiểm tra timeout của `poll`, phải lấy được **kết quả `null` của tác vụ**; nếu thời hạn bảo vệ 5 giây hết trước thì bài kiểm thử thất bại.

## 4. Điều phối thứ tự bằng tín hiệu, không phỏng đoán bằng sleep

Mẫu dễ hỏng là khởi động một luồng, `sleep(100)`, rồi mặc định rằng luồng đó đã vào `takeFirst()`. Máy tải nặng có thể chưa kịp chạy luồng mới. Máy nhanh cũng có thể hoàn thành một nhánh khác trước lúc ta quan sát.

Sử dụng tín hiệu như `CountDownLatch` để biết tác vụ đã đến một điểm xác định. Tuy nhiên, latch đặt ngay trước lời gọi deque **chỉ xác nhận đã đến điểm đó**, không chứng minh tại đúng thời điểm khác luồng đang ở trạng thái `WAITING`.

Cách kiểm tra hữu ích ở mức hợp đồng là giữ điều kiện không thể thành công: không có bên tạo khi đang kiểm tra `take` trên deque rỗng; không có bên lấy khi đang kiểm tra `put` trên deque đầy. Sau khi đã quan sát tác vụ chưa báo hoàn thành, bài kiểm thử chủ động thay đổi đúng một điều kiện rồi đợi kết quả với thời hạn bảo vệ.

Điều này kiểm tra hành vi có thể quan sát, không phụ thuộc tên luồng nội bộ, cách dùng khóa hoặc trạng thái JVM tại một thời điểm lấy mẫu. Một cửa sổ quan sát hữu hạn vẫn không phải bằng chứng toán học về mọi lịch chạy có thể có.

## 5. Bộ kiểm thử độc lập, chạy được trên Java 17+

Lưu toàn bộ chương trình dưới đây thành `DequeWaitingTest.java`. Chương trình chỉ dùng JDK, không cần JUnit hoặc thư viện ngoài. Hàm `check` luôn hoạt động; không cần bật tùy chọn `-ea` như khi dùng từ khóa `assert`.

`Running` quản lý một tác vụ phụ: báo đã bắt đầu, giữ kết quả qua `FutureTask`, giới hạn mọi lần chờ kết quả và dọn luồng trong `close()`. Việc dùng `FutureTask` giúp ngoại lệ của tác vụ quay về luồng kiểm thử thay vì chỉ được in ra rồi bị bỏ qua. [Tài liệu FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html)

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class DequeWaitingTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static final class Running<T> implements AutoCloseable {
        final CountDownLatch started = new CountDownLatch(1);
        final FutureTask<T> result;
        final Thread thread;

        Running(Callable<T> action) {
            result = new FutureTask<>(() -> {
                started.countDown();
                return action.call();
            });
            thread = new Thread(result, "deque-test-worker");
            thread.setDaemon(true);
            thread.start();
        }

        void awaitStarted() throws InterruptedException {
            check(started.await(5, TimeUnit.SECONDS), "worker did not start");
        }

        void stillPending() throws Exception {
            awaitStarted();
            try {
                result.get(80, TimeUnit.MILLISECONDS);
                throw new AssertionError("operation completed unexpectedly");
            } catch (TimeoutException expected) {
                // The operation has not reported completion.
            }
        }

        T get() throws Exception {
            return result.get(5, TimeUnit.SECONDS);
        }

        @Override
        public void close() throws InterruptedException {
            thread.interrupt();
            thread.join(5000);
            check(!thread.isAlive(), "worker leaked");
        }
    }

    private static <T> T guarded(Callable<T> action) throws Exception {
        try (Running<T> running = new Running<>(action)) {
            running.awaitStarted();
            return running.get();
        }
    }

    private static void capacity() {
        BlockingDeque<Integer> q = new LinkedBlockingDeque<>(2);
        check(q.offerLast(1), "insert 1");
        check(q.offerLast(2), "insert 2");
        check(!q.offerFirst(3), "full offer must fail");
        try {
            q.addLast(4);
            throw new AssertionError("full add must throw");
        } catch (IllegalStateException expected) {
            // Expected for a full deque.
        }
        check(q.remainingCapacity() == 0, "capacity changed");
        check(new ArrayList<>(q).equals(List.of(1, 2)), "data changed");
    }

    private static void timeouts() throws Exception {
        BlockingDeque<Integer> q = new LinkedBlockingDeque<>(1);
        check(guarded(() -> q.pollFirst(40, TimeUnit.MILLISECONDS)) == null,
                "empty pollFirst must return null");
        check(guarded(() -> q.pollLast(40, TimeUnit.MILLISECONDS)) == null,
                "empty pollLast must return null");
        check(q.isEmpty(), "poll created an element");
        check(q.offerLast(10), "initial insert");
        check(!guarded(() -> q.offerFirst(20, 40, TimeUnit.MILLISECONDS)),
                "full timed offerFirst must fail");
        check(!guarded(() -> q.offerLast(30, 40, TimeUnit.MILLISECONDS)),
                "full timed offerLast must fail");
        check(new ArrayList<>(q).equals(List.of(10)), "timed offer changed data");
    }

    private static void unblock(boolean first) throws Exception {
        BlockingDeque<Integer> q = new LinkedBlockingDeque<>(1);
        try (Running<Integer> take = new Running<>(
                () -> first ? q.takeFirst() : q.takeLast())) {
            take.stillPending();
            check(q.offerLast(7), "supply element");
            check(take.get() == 7, "wrong element");
            check(q.isEmpty(), "take did not remove element");
        }

        check(q.offerLast(10), "fill deque");
        try (Running<Void> put = new Running<>(() -> {
            if (first) q.putFirst(20); else q.putLast(20);
            return null;
        })) {
            put.stillPending();
            check(Integer.valueOf(10).equals(q.pollFirst()), "remove original");
            put.get();
            check(new ArrayList<>(q).equals(List.of(20)), "put lost element");
        }
    }

    private static void expectInterrupted(Running<?> running) throws Exception {
        running.stillPending();
        running.thread.interrupt();
        try {
            running.get();
            throw new AssertionError("operation ignored interrupt");
        } catch (ExecutionException expected) {
            check(expected.getCause() instanceof InterruptedException,
                    "wrong failure: " + expected.getCause());
        }
    }

    private static void interrupts(boolean first) throws Exception {
        BlockingDeque<Integer> q = new LinkedBlockingDeque<>(1);
        try (Running<Integer> take = new Running<>(
                () -> first ? q.takeFirst() : q.takeLast())) {
            expectInterrupted(take);
            check(q.isEmpty(), "interrupted take changed data");
        }

        check(q.offerLast(10), "fill deque");
        try (Running<Void> put = new Running<>(() -> {
            if (first) q.putFirst(20); else q.putLast(20);
            return null;
        })) {
            expectInterrupted(put);
            check(new ArrayList<>(q).equals(List.of(10)),
                    "interrupted put changed data");
        }
    }

    public static void main(String[] args) throws Exception {
        capacity();
        System.out.println("capacity PASS");
        timeouts();
        System.out.println("timeouts PASS");
        for (boolean first : new boolean[] {true, false}) {
            String end = first ? "first" : "last";
            unblock(first);
            System.out.println("unblock-" + end + " PASS");
            interrupts(first);
            System.out.println("interrupt-" + end + " PASS");
        }
        System.out.println("ALL PASS");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 DequeWaitingTest.java
java DequeWaitingTest
```

Đầu ra khi mọi ca đạt:

```text
capacity PASS
timeouts PASS
unblock-first PASS
interrupt-first PASS
unblock-last PASS
interrupt-last PASS
ALL PASS
```

Nếu một điều kiện sai hoặc hết thời hạn bảo vệ, chương trình kết thúc bằng lỗi thay vì in `ALL PASS`. Các dòng đầu ra do luồng chính in sau khi kiểm tra xong, nên không cần dự đoán thứ tự những lệnh in đến từ nhiều luồng.

## 6. Mỗi nhóm kiểm thử thực sự chứng minh điều gì?

### 6.1. capacity: quá tải không làm hỏng dữ liệu đang đợi

Deque có dung lượng 2 và chứa `[1, 2]`. Thêm phần tử thứ ba ở đầu bằng `offerFirst` phải thất bại, còn `addLast` phải ném đúng ngoại lệ. Bài kiểm thử xác nhận nội dung vẫn là `[1, 2]`, không chỉ kiểm tra giá trị trả về.

Kiểm tra hậu trạng thái bắt được lỗi như vô tình loại phần tử cũ để nhường chỗ hoặc thêm ở sai nhánh xử lý. Việc lấy bản sao bằng `ArrayList` ở đây có ý nghĩa rõ ràng vì không có luồng nào khác đang thay đổi deque.

Đây là ca quá tải chức năng có điều kiện kiểm soát. Nó không phải phép thử thông lượng và cũng không tạo áp lực bộ nhớ bằng cách thêm hàng triệu phần tử.

### 6.2. timeouts: phải nhận kết quả từ chính thao tác có thời hạn

Hai `poll` chạy trên deque rỗng mà không có bên tạo. Hai `offer` có thời hạn chạy trên deque đầy mà không có bên lấy. Bộ kiểm thử đợi kết quả thực sự qua `guarded`, rồi kiểm tra dữ liệu còn nguyên.

Thời hạn 5 giây bảo vệ bài kiểm thử nếu một lời gọi có lỗi không kết thúc. Nó không thay đổi thời hạn 40 ms của thao tác đang được thử. Bài này kiểm tra kết quả và khả năng kết thúc; chưa kiểm tra độ chính xác thời gian ở mức mili giây.

### 6.3. unblock: điều kiện được đáp ứng thì lời gọi đi tiếp

Với `take`, kiểm thử bắt đầu từ rỗng, quan sát chưa hoàn thành, rồi mới đưa vào 7. Với `put`, deque đã chứa 10; chỉ sau khi quan sát chưa hoàn thành mới lấy 10 ra để giải phóng chỗ.

Hai phần kiểm tra bổ sung cho nhau. Chỉ thử timeout/ngắt mà không thử tiếp tục thành công có thể bỏ sót một lớp lỗi khiến lời gọi không được đánh thức khi điều kiện đã thay đổi.

Trong deque dung lượng 1, kiểm thử này tập trung vào điều kiện chờ ở từng đầu. Nó không chứng minh thứ tự nhiều phần tử ở hai đầu; cần một ca riêng với dung lượng lớn hơn để phân biệt rõ `first` và `last` về thứ tự.

### 6.4. interrupts: kiểm tra nguyên nhân ngắt, không chỉ trạng thái Future

Không có bên nào làm deque rỗng trở thành có dữ liệu hoặc deque đầy trở thành có chỗ trong ca này. Sau khi quan sát tác vụ chưa hoàn thành, luồng kiểm thử gọi `interrupt()` trực tiếp lên luồng phụ và đợi ngoại lệ được chuyển qua `FutureTask`.

Không dùng `cancel(true)` ở đây, vì khi Future đã bị hủy, việc quan sát `CancellationException` chỉ xác nhận trạng thái Future bị hủy; nó chưa chứng minh đoạn mã bên trong đã phản ứng bằng đúng `InterruptedException`. Ca này cần nhìn nguyên nhân lỗi từ lời gọi deque.

Latch và cửa sổ quan sát không bảo đảm tín hiệu ngắt đến sau đúng một lệnh máy bên trong phương thức. Nó có thể đến ngay trước hoặc trong lúc chờ; điều kiện deque vẫn không thể thỏa mãn. Nếu cần kiểm tra chính xác một điểm nội bộ của lớp tự viết, phải thiết kế điểm điều phối chuyên dụng thay vì xem mẫu này như bằng chứng về lịch chạy nội bộ.

### 6.5. close: mọi nhánh đều phải thu dọn

`try-with-resources` gọi `close` cả khi assertion hoặc tác vụ thất bại. Luồng được ngắt, đợi tối đa 5 giây rồi kiểm tra còn sống hay không. Trong ứng dụng sản xuất, việc xử lý `InterruptedException` thường phải tuân thủ quy tắc truyền ngoại lệ/khôi phục cờ ngắt của tầng quản lý tác vụ; ở bộ kiểm thử này, nguyên nhân được chuyển về để kiểm tra.

`setDaemon(true)` chỉ là lớp bảo vệ để một luồng lỗi không giữ JVM sống mãi sau khi bộ kiểm thử đã báo thất bại. Nó không thay cho việc dọn luồng: `close` vẫn bắt buộc kiểm tra không còn luồng phụ. Với mã bị treo không phản ứng ngắt, còn cần thời hạn ở cấp tiến trình/CI để chặn cả bộ kiểm thử.

## 7. Kiểm tra thời gian mà không tạo bài thử chập chờn

Không viết `elapsedMillis == 40`. Thời gian thực tế chịu tác động của độ phân giải đồng hồ, việc được cấp CPU, GC và môi trường chạy. Một thời hạn chờ không phải lời hứa rằng câu lệnh kế tiếp của bên gọi sẽ chạy đúng vào thời điểm đó.

Nếu cần quan sát thời lượng, dùng hiệu của hai lần `System.nanoTime()`, phù hợp với đo khoảng thời gian; không dùng nó như ngày/giờ tuyệt đối. [Tài liệu System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime())

Đoạn sau minh họa đo riêng một lời gọi; `q` là deque rỗng do ca kiểm thử sở hữu và phương thức chứa đoạn này phải xử lý `InterruptedException`:

```java
long started = System.nanoTime();
Integer item = q.pollFirst(40, TimeUnit.MILLISECONDS);
long elapsedNanos = System.nanoTime() - started;
if (item != null) {
    throw new AssertionError("Unexpected element");
}
// Ghi elapsedNanos để chẩn đoán hoặc đánh giá với ngân sách đã xác định.
```

Nếu đặt giới hạn trên cho thời lượng trong CI, cần khoảng dự phòng theo môi trường và phân biệt lỗi tiến triển với máy kiểm thử quá tải. Không chọn một ngưỡng sát 40 ms rồi coi mọi lần vượt nhẹ là lỗi cấu trúc đồng thời.

Cũng không để ngưỡng quá rộng che khuất lỗi cần phát hiện. Kiểm thử hợp đồng, kiểm tra ngân sách độ trễ của ứng dụng và đánh giá hiệu năng là ba mục đích khác nhau; mỗi mục đích cần điều kiện chạy và tiêu chí riêng.

## 8. Mở rộng thành kiểm thử tải có đối soát

Một deque đầy trong ca nhỏ không chứng minh toàn bộ hệ thống sẽ xử lý quá tải đúng. Để kiểm tra đường xử lý ứng dụng, có thể thiết kế đợt tải hữu hạn như sau:

1. Mỗi công việc có một mã duy nhất; số bên tạo, bên lấy, tổng số công việc và dung lượng đều được cố định trong cấu hình ca.
2. Giữ bên lấy ở một cổng bắt đầu do kiểm thử điều khiển. Cho bên tạo thử thêm bằng `offer` để tạo tình huống đầy mà không phụ thuộc tốc độ CPU.
3. Ghi riêng mã được nhận và mã bị từ chối. Nếu chưa có bên lấy và dung lượng là 3, ba lần thêm đầu thành công, các lần tiếp theo phải theo chính sách đầy.
4. Mở cổng cho bên lấy, xử lý tập đã được nhận, rồi chờ kết thúc với thời hạn tổng thể.
5. Đối soát: mỗi mã được nhận đã đi đến một trạng thái cuối xác định, không xử lý trùng; mã bị từ chối chưa được xác nhận là thành công. Đối với chính sách cho phép bỏ/gộp, phải ghi được lý do tương ứng.

Sau ca điều phối có kiểm soát, chạy thêm ca tranh chấp với nhiều bên tạo/lấy cùng hoạt động. Lặp lại có thể tăng khả năng gặp lịch chạy xấu, nhưng không biến kiểm thử tải thành chứng minh đầy đủ về tính đúng đồng thời.

Không khẳng định “không bao giờ vượt dung lượng” chỉ vì một bộ lấy mẫu thấy `size()` luôn nhỏ. Lấy mẫu có thể bỏ qua trạng thái ngắn; nó hữu ích cho quan sát, còn đối soát mã công việc và các bất biến cần kiểm tra độc lập.

Khi đối soát một đường xử lý đầy đủ, nên phân biệt ít nhất: đã được tiếp nhận, đang đợi, đang chạy, thành công, thất bại và bị hủy theo chính sách. Deque rỗng không có nghĩa tất cả công việc đã hoàn tất: bên lấy có thể còn đang xử lý phần tử đã lấy ra.

## 9. Những ca biên đáng thêm vào bộ kiểm thử ứng dụng

| Ca bổ sung | Sai sót có thể phát hiện |
| --- | --- |
| Phần tử/chỗ xuất hiện trước khi thời hạn hết | Nhánh có thời hạn không tiếp tục dù đã đủ điều kiện |
| Ngắt `poll`/`offer` có thời hạn | Bỏ qua ngắt ở biến thể có thời hạn |
| Yêu cầu ngắt có sẵn trước lời gọi | Chỉ xử lý ngắt nếu tín hiệu đến sau khi bắt đầu chờ |
| Hết thời gian rồi bên tạo mới thêm dữ liệu | Nhầm kết quả đã hết hạn với dữ liệu đến sau; hủy sai tác vụ khác |
| Nhiều luồng bị dừng khi deque đầy | Bên tạo không thoát, làm quá trình dừng treo |
| Tất cả bên xử lý cùng đưa việc lỗi trở lại deque đầy | Vòng phụ thuộc khiến không ai tạo chỗ trống |
| Công việc mới và ngắt xảy ra gần nhau | Khẳng định quá mạnh về kết quả mà lịch chạy không bảo đảm |

Với ca cạnh tranh giữa thêm dữ liệu và ngắt, không tự quy định một kết quả duy nhất nếu hợp đồng ứng dụng chưa đưa ra bảo đảm đó. Hãy kiểm tra tập kết quả được phép và đối soát dữ liệu: phần tử có thể đã được lấy thành công trước tín hiệu ngắt, hoặc tác vụ có thể thoát do ngắt. Chính sách cho công việc đã lấy ra phải do ứng dụng quyết định.

Không dùng `Thread.stop`, cưỡng bức kết thúc luồng hay bỏ mặc luồng lỗi để làm bài kiểm thử “xanh”. Cũng không chỉ in stack trace trong luồng phụ rồi tiếp tục báo ca đạt; lỗi phải truyền về luồng điều khiển bộ kiểm thử.

## 10. Bài tập củng cố

- Thêm ca `pollLast(1, SECONDS)` trên deque rỗng; bên kiểm thử thêm đúng một phần tử sau khi tác vụ báo bắt đầu. Xác nhận nhận phần tử trước thời hạn bảo vệ và không còn phần tử trong deque.
- Thêm ca `offerFirst` có thời hạn trên deque đầy; giải phóng chỗ rồi kiểm tra thêm thành công. Giữ thời hạn của ca đủ rộng để không kiểm tra tốc độ máy thay cho hợp đồng.
- Thêm hai ca ngắt cho `pollFirst` và `offerLast` có thời hạn, kiểm tra nguyên nhân `InterruptedException` qua Future như các ca ngắt hiện có.
- Thay chính sách phản ứng với `false` của ứng dụng bằng một nhánh cố ý báo thành công. Thiết kế phép đối soát để bài kiểm thử phát hiện sai lệch này.

Một bộ kiểm thử hữu ích cho đường chờ phải có điều kiện vào rõ ràng, một tác nhân thay đổi điều kiện hoặc ngắt, kết quả được đối soát và đường dọn tài nguyên có thời hạn.
