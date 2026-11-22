# Đánh thức giả và kiểm tra điều kiện trong vòng lặp

## 1. Thức dậy chưa có nghĩa là được phép tiếp tục

Khi một luồng chờ `Condition`, nó đang đợi một trạng thái của ứng dụng thay đổi: có dữ liệu, còn chỗ, đã khởi tạo xong hoặc đã có yêu cầu dừng. Lời gọi chờ trở về không tự chứng minh trạng thái ấy đang đúng.

Vì vậy, cấu trúc căn bản là:

```java
lock.lockInterruptibly();
try {
    while (!ready) {
        changed.await();
    }
    useReadyState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa, giả định `changed` được tạo từ chính `lock`, `ready` là trạng thái được khóa ấy bảo vệ và `useReadyState` là thao tác ứng dụng. Cần các khai báo và import thích hợp khi đặt trong chương trình.

Vòng `while` không phải cách chữa bằng thử lại tùy ý. Nó là phần biểu diễn điều kiện cho phép tiến hành: chừng nào trạng thái chưa đáp ứng thì tiếp tục chờ; chỉ khi kiểm tra dưới khóa thấy đúng mới làm việc.

[Hợp đồng `Condition`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/Condition.html) cho phép đánh thức giả và yêu cầu người dùng luôn tính đến khả năng đó bằng kiểm tra điều kiện trong vòng lặp. Các API này vẫn áp dụng trên Java hiện hành.

## 2. Đánh thức giả là gì?

Đánh thức giả (spurious wakeup) là trường hợp một lần chờ có thể trở về mà không có tín hiệu mong muốn từ ứng dụng. Đây là một khả năng được API cho phép, gắn với cách cơ chế chờ được triển khai trên nền tảng.

Điều cần làm không phải tính xác suất rồi bỏ qua vì “ít khi gặp”. Mã đúng phải giữ được điều kiện nghiệp vụ ngay cả khi lần chờ trở về theo cách đó.

Không nên xây dựng một bài thử bắt buộc phải quan sát được đánh thức giả tự phát. Việc chạy hàng nghìn lần mà chưa gặp không chứng minh chương trình dùng `if` là đúng; gặp hay không phụ thuộc môi trường và lịch chạy. Java không cung cấp một thao tác ứng dụng mang nghĩa “hãy tạo một đánh thức giả ở đúng lần chờ này”.

Cần phân biệt với các sự kiện khác cũng khiến phải kiểm tra lại:

| Sự kiện | Có phải đánh thức giả theo nghĩa trên không? | Vì sao vẫn cần xét trạng thái? |
| --- | --- | --- |
| API cho phép lần chờ trở về không do tín hiệu mong đợi | Có | Không có căn cứ rằng trạng thái nghiệp vụ đã đúng |
| Một luồng gọi `signalAll` nhưng không làm điều kiện đúng | Không, đây là tín hiệu thật | Tín hiệu không tự thay đổi trạng thái |
| Điều kiện đúng lúc báo nhưng luồng khác dùng mất tài nguyên | Không | Trạng thái có thể sai trước khi bên được báo lấy lại khóa |
| Chờ có thời hạn kết thúc | Không | Hết thời gian chờ không tạo dữ liệu hoặc tài nguyên |
| Chờ bị ngắt bằng `InterruptedException` | Không | Đây là đường hủy/dừng riêng cần xử lý |

Tất cả các tình huống liên quan đều nhắc rằng việc được đánh thức và điều kiện cho phép làm việc là hai sự kiện khác nhau.

## 3. `if` hỏng ngay cả khi không có đánh thức giả

Đoạn sau chưa đủ:

```java
if (items.isEmpty()) {
    notEmpty.await();
}
return items.removeFirst();
```

Đây là đoạn minh họa lỗi, giả định đang giữ khóa bảo vệ `items` và `notEmpty`. Vấn đề là sau khi `await` trở về, chương trình đi thẳng tới lấy phần tử mà không kiểm tra lại.

Xét hai bên tiêu thụ cùng chờ và một phần tử được thêm:

1. Luồng tạo lấy khóa, thêm đúng một phần tử, gọi `signalAll`, rồi nhả khóa.
2. Cả A và B được đánh thức, nhưng chỉ một luồng được lấy khóa trước.
3. A lấy khóa và lấy mất phần tử.
4. B lấy khóa sau đó, lần chờ của B trở về nhưng hàng lại trống.
5. Nếu dùng `if`, B vẫn cố lấy phần tử và có thể gặp lỗi.

Không có đánh thức giả nào trong dòng thời gian này: cả A và B đều được báo thật. `while` vẫn cần để B thấy hàng trống và quay lại chờ.

Ngay cả khi chỉ dùng `signal`, một bên không chờ nhưng đang cạnh tranh khóa có thể dùng tài nguyên trước bên vừa được báo. Không biến “được báo” thành một quyền sở hữu tài nguyên nếu giao thức chưa cấp quyền ấy.

## 4. Kiểm tra, chờ và cập nhật phải dùng cùng khóa

Với condition của `ReentrantLock`, `await` phối hợp việc nhả khóa và bắt đầu chờ. Khi trở về bình thường, luồng đã lấy lại khóa liên quan. Vì vậy, điều kiện phải được kiểm tra trong vùng khóa, không tách thành một lần đọc tự do ở ngoài.

Phía tạo trạng thái dùng cùng khóa:

```java
lock.lock();
try {
    ready = true;
    changed.signalAll();
} finally {
    lock.unlock();
}
```

Trạng thái giữ lại ý nghĩa của sự kiện. Nếu `ready` đã đúng trước khi bên chờ đến, bên đó lấy khóa, kiểm tra rồi không gọi `await`. Không cần một tín hiệu được lưu sẵn.

Ngược lại, `signal` không phải một kho vé. Gọi trước khi có ai chờ không tạo một vé để lần `await` tương lai chắc chắn trở về. Nếu ứng dụng cần đếm số quyền được cấp hoặc số sự kiện phải tiêu thụ, phải lưu số đếm hoặc chọn cấu trúc phù hợp với ý nghĩa đó.

Đánh dấu `ready` là `volatile` không thay thế toàn bộ giao thức kiểm tra rồi chờ. Dù lần đọc nhìn thấy dữ liệu đúng, vẫn có thể có khoảng đua giữa lần kiểm tra ở ngoài khóa và lúc bắt đầu chờ nếu các bước không được phối hợp.

## 5. Ví dụ Java 17+: báo nhưng chưa mở cổng

Ví dụ dưới đây **chủ động gửi một tín hiệu thật khi điều kiện vẫn sai**. Nó kiểm chứng rằng vòng lặp không cho tác vụ đi qua. Nó không được trình bày như bằng chứng đã ép JVM tạo đánh thức giả tự phát.

Lưu thành `GuardedWaitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class GuardedWaitDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition changed = lock.newCondition();
        private boolean open;

        boolean awaitOpen(CountDownLatch firstWait,
                          CountDownLatch checkedAgain)
                throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!open) {
                    firstWait.countDown();
                    changed.await();
                    if (!open) {
                        checkedAgain.countDown();
                    }
                }
                return true;
            } finally {
                lock.unlock();
            }
        }

        void signalWithoutOpening() {
            lock.lock();
            try {
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                open = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Gate gate = new Gate();
        CountDownLatch firstWait = new CountDownLatch(1);
        CountDownLatch checkedAgain = new CountDownLatch(1);
        FutureTask<Boolean> passage = new FutureTask<>(() ->
                gate.awaitOpen(firstWait, checkedAgain));
        Thread waiter = new Thread(passage, "waiter");
        waiter.start();

        try {
            if (!firstWait.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("waiter did not reach await");
            }
            gate.signalWithoutOpening();
            if (!checkedAgain.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("condition was not rechecked");
            }
            System.out.println("completed while closed: " + passage.isDone());
            gate.open();
            System.out.println("passed after open: "
                    + passage.get(5, TimeUnit.SECONDS));
        } finally {
            passage.cancel(true);
            waiter.join(1_000);
            if (waiter.isAlive()) {
                throw new IllegalStateException("waiter did not stop");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 GuardedWaitDemo.java
java GuardedWaitDemo
```

Stdout khi các bước điều phối hoàn tất trong thời hạn của ví dụ:

```text
completed while closed: false
passed after open: true
```

Giải thích cách kiểm chứng:

- `firstWait` giúp luồng chính không báo tùy ý trước khi bên chờ đi đến giao thức. Bên chờ giảm chốt khi còn giữ khóa, ngay trước `await`; bên báo cần lấy cùng khóa nên được phối hợp với bước chờ.
- `signalWithoutOpening` không đặt `open = true`. Sau lần chờ trở về mà `open` vẫn sai, tác vụ ghi nhận đã kiểm tra lại rồi tiếp tục vòng lặp.
- Nếu môi trường tự tạo một đánh thức giả sớm hơn, vòng lặp vẫn an toàn và chốt kiểm tra lại cũng có thể được giảm. Không dùng chốt đó để suy ra chắc chắn nguyên nhân của mọi lần đánh thức.
- Khi in dòng đầu, chưa có ai mở cổng và không có yêu cầu hủy, nên tác vụ chưa thể hoàn tất bình thường. Lời gọi `open()` sau đó đổi trạng thái dưới khóa và báo để tác vụ có thể thoát vòng lặp.
- `FutureTask` chuyển lỗi về luồng chính, còn các chốt và thời hạn kiểm tra tránh dựa vào `sleep` để đoán lịch chạy. Số lần chờ lại không được in thành một con số cố định vì có thể có thêm lần đánh thức.

Hai chốt chỉ dùng để quan sát trong ví dụ, không thay biến `open` và không phải điều kiện nghiệp vụ mới. Các timeout 5 giây là giới hạn của bài thử, không phải thời gian chính xác của cơ chế condition.

## 6. Vòng chờ có thời hạn: không cấp lại toàn bộ thời gian sau mỗi lần thức

Một lỗi khác là luôn gọi `await(1, SECONDS)` lại từ đầu trong mỗi vòng. Nếu liên tục có đánh thức mà điều kiện chưa đúng, tổng thời gian chờ có thể kéo dài mãi so với ngân sách 1 giây ban đầu.

Mẫu dùng phần còn lại:

```java
boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0) {
                return false;
            }
            remaining = changed.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
```

Đây là phương thức minh họa để đặt trong lớp có `lock`, `changed`, `ready` và các import phù hợp. `awaitNanos` cung cấp ước lượng thời gian còn lại để dùng cho lần chờ tiếp theo.

Mẫu kiểm tra trạng thái trước: nếu `ready` đã đúng khi lấy khóa, nó trả `true` dù không có ngân sách chờ dương. Nếu điều kiện sai và không còn thời gian, trả `false`. Đây là một chính sách cụ thể, cần được giữ rõ khi viết mã ứng dụng.

Không lấy boolean của `await(time, unit)` hoặc việc `awaitNanos` trở về làm một lần kiểm tra hộ biến `ready`. Giá trị trả về của API mô tả việc chờ, không tự biết trạng thái nghiệp vụ.

Mẫu trên không gộp thời gian lấy khóa ban đầu vào một ngân sách tổng từ lúc bắt đầu phương thức. Nếu cần thời hạn tổng, phải theo dõi một mốc thời gian chung và dành phần còn lại cho cả lấy khóa lẫn chờ điều kiện. Việc lấy lại khóa và lập lịch cũng có thể làm thời điểm trở về muộn hơn mốc dự kiến; timeout không phải cam kết thời gian thực tuyệt đối.

## 7. `while` là cần thiết, nhưng chưa đủ để chứng minh hệ thống luôn tiến triển

Một vòng lặp đúng vẫn có thể chờ mãi nếu không còn luồng nào có khả năng làm điều kiện đúng. Cần kiểm tra toàn bộ giao thức:

- Bên cập nhật có dùng cùng khóa và báo đúng condition không?
- Sau khi cập nhật cho phép nhiều bên tiếp tục, đã chọn cách báo phù hợp chưa?
- Có luồng giữ thêm tài nguyên khiến bên cập nhật không chạy được không?
- Nếu bên cập nhật lỗi, ai phát hiện và đánh thức/hủy bên đang chờ?
- Khi dừng hệ thống, điều kiện thoát có được lưu và được báo cho mọi nhóm liên quan không?

Ví dụ một bộ đệm có trạng thái đóng có thể chờ bằng:

```java
while (empty && !closed) {
    notEmpty.await();
}
```

Đoạn minh họa này giả định đang giữ khóa và các trạng thái đều được bảo vệ. Sau vòng lặp, vẫn cần phân biệt “có dữ liệu” với “đã đóng nhưng trống”, rồi áp dụng chính sách trả kết quả hoặc báo hết dữ liệu. Không thoát vòng lặp rồi mặc định luôn có phần tử.

Phương thức đóng phải cập nhật `closed` dưới khóa và đánh thức những nhóm cần kiểm tra lại. Không có tín hiệu hoặc ngắt, một luồng đang ngủ có thể không biết đã đến lúc kết thúc dù vòng `while` được viết đúng.

## 8. Ngắt luồng khác với đánh thức để tiếp tục

Với `await` có ngắt, `InterruptedException` là đường kết thúc khác với việc trở về bình thường rồi kiểm tra điều kiện. Không bắt ngoại lệ rồi đi thẳng tới xử lý như thể đã có tài nguyên.

Có thể truyền ngoại lệ lên tầng quản lý. Ở biên tác vụ muốn dừng, có thể khôi phục cờ ngắt và thoát theo chính sách. Bắt rồi lờ đi ngắt, sau đó quay lại chờ vô hạn có thể phá yêu cầu hủy của hệ thống.

Với condition của `ReentrantLock`, luồng lấy lại khóa trước khi việc chờ báo ngoại lệ; `finally` vẫn nhả khóa đang sở hữu. Còn nếu bị ngắt ở `lockInterruptibly()` trước khi lấy khóa thì chưa vào khối `try` phía sau, nên không nhả một khóa chưa lấy được.

Đừng mô tả mọi lần thoát chờ là “đánh thức giả”. Dùng đúng tên cho ngắt, hết thời gian và tín hiệu giúp đường xử lý của chương trình rõ ràng.

## 9. Nguyên tắc tương tự với `Object.wait()`

Khi dùng monitor, cùng ý tưởng điều kiện chờ vẫn áp dụng:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    useReadyState();
}
```

Đoạn này giả định phương thức bao ngoài xử lý hoặc khai báo `InterruptedException`. Biến `ready` và các thay đổi tương ứng phải theo cùng giao thức monitor. `wait` nhả monitor của đối tượng được gọi, rồi lấy lại trước khi tiếp tục; không thay bằng `Thread.sleep` vì `sleep` không thực hiện bước nhả monitor đó.

[Java SE `Object.wait`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#wait()) cũng nêu khả năng đánh thức giả và việc phải kiểm tra điều kiện. Đây là nguyên tắc còn hiện hành, không phải lý do để trộn `wait`/`notify` với `Condition.await`/`signal` trên cùng một giao thức.

Khi chọn một cơ chế, phải giữ đúng cặp chờ – báo và đúng khóa liên quan. Monitor của đối tượng `Condition` không thay thế khóa đã tạo condition đó.

## 10. Tự kiểm tra

1. Chương trình chưa từng gặp đánh thức giả trong thử nghiệm có được đổi `while` thành `if` không?
2. Vì sao hai bên nhận `signalAll` vẫn có thể chỉ một bên dùng được tài nguyên?
3. Tín hiệu được gửi lúc chưa ai chờ có được lưu như một vé không?
4. Đặt `ready` thành `volatile` có tự làm kiểm tra ngoài khóa rồi `await` an toàn không?
5. Một vòng lặp dùng lại toàn bộ timeout sau mỗi lần thức có thể gây vấn đề gì?
6. Vì sao ví dụ gửi tín hiệu khi cổng đóng không được gọi là ép tạo đánh thức giả của JVM?

Gợi ý: (1) Không; cả hợp đồng API lẫn cạnh tranh tài nguyên đều yêu cầu kiểm tra lại. (2) Chỉ một bên lấy khóa và sử dụng tài nguyên trước; bên còn lại phải kiểm tra lại. (3) Không, trạng thái ứng dụng mới giữ ý nghĩa cần quan sát. (4) Không thay thế việc phối hợp kiểm tra – chờ. (5) Tổng thời gian có thể bị kéo dài qua các lần chờ lại. (6) Có một tín hiệu thật do mã ứng dụng gọi; ví dụ chỉ kiểm chứng rằng tỉnh dậy chưa cho phép bỏ qua điều kiện.
