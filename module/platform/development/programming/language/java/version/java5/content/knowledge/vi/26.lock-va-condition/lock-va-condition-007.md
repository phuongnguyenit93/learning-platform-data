# `Condition` và hàng đợi chờ theo điều kiện

## 1. Có khóa chưa chắc đã đủ điều kiện làm việc

Khóa giúp một luồng kiểm tra và sửa trạng thái dùng chung một cách có phối hợp. Nhưng có những lúc luồng đã lấy được khóa mà vẫn chưa thể tiếp tục:

- Bên lấy dữ liệu thấy bộ đệm đang trống.
- Bên đưa dữ liệu thấy bộ đệm đã đầy.
- Một tác vụ thấy tài nguyên chưa được chuẩn bị xong.

Nếu luồng giữ khóa rồi liên tục kiểm tra, bên khác có thể không lấy được khóa để làm điều kiện thay đổi. Nếu nhả khóa rồi tự ngủ một khoảng, chương trình lại phải đoán thời gian và có thể bỏ lỡ thời điểm phù hợp.

`Condition` cung cấp cách chờ gắn với một khóa: luồng tạm nhả khóa trong lúc chờ, rồi lấy lại khóa trước khi tiếp tục kiểm tra trạng thái. Một khóa có thể gắn nhiều `Condition`, giúp tách các nhóm luồng chờ những điều kiện khác nhau.

Ví dụ một ô đệm:

```text
cùng một khóa bảo vệ: có dữ liệu hay không, dữ liệu là gì
        ├── Condition có dữ liệu: bên lấy chờ ở đây khi ô trống
        └── Condition còn chỗ: bên đưa chờ ở đây khi ô đầy
```

`Condition` không chứa thay một biến boolean cho nghiệp vụ. Nó quản lý việc chờ và phát tín hiệu; điều kiện thật sự vẫn là một biểu thức trên trạng thái được khóa bảo vệ.

## 2. Tạo `Condition` từ đúng khóa

Với `ReentrantLock`:

```java
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
```

Đây là các khai báo trường để đặt trong một lớp, với import từ `java.util.concurrent.locks`. Hai condition đều gắn với chính `lock`.

Không tạo condition từ khóa A rồi bảo vệ dữ liệu bằng khóa B. Khi dùng condition do `ReentrantLock` tạo, luồng phải đang giữ khóa liên quan để gọi các phương thức chờ hoặc phát tín hiệu; dùng sai gây `IllegalMonitorStateException`.

Quy tắc gắn condition với khóa và cách chờ được mô tả trong [Java SE `Condition`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/Condition.html). Các phương thức trong bài vẫn được hỗ trợ trên JDK hiện hành; [hợp đồng `ReentrantLock.newCondition`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#newCondition()) nêu hành vi cụ thể của condition được dùng ở đây.

Không nhầm monitor của chính đối tượng condition với cơ chế này. `synchronized(notEmpty)`, `notEmpty.wait()` hoặc `notEmpty.notify()` dùng monitor của đối tượng Java đó, không phải cơ chế `await`/`signal` liên kết với `lock`.

## 3. Một lần `await()` thực hiện những gì?

Mẫu căn bản:

```java
lock.lockInterruptibly();
try {
    while (!ready) {
        readyCondition.await();
    }
    useReadyState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa, giả định `readyCondition` được tạo từ `lock`, `ready` là trạng thái dùng chung và `useReadyState` thuộc ứng dụng.

Dòng thời gian khi `ready` chưa đúng:

1. Luồng A giữ khóa và kiểm tra điều kiện.
2. A gọi `await`: thao tác chờ phối hợp việc nhả khóa với đưa A vào trạng thái chờ condition.
3. Luồng B có thể lấy khóa, cập nhật trạng thái và gọi `signal` hoặc `signalAll`.
4. A được đánh thức nhưng còn phải lấy lại khóa; nó chưa lập tức chạy vùng tới hạn cùng B.
5. Sau khi lấy lại khóa, A kiểm tra điều kiện trong vòng `while` rồi mới quyết định tiếp tục hoặc chờ lại.

Có thể hình dung hai nhóm chờ:

```text
đang chờ Condition
        ↓ được đánh thức / chờ lại khóa
đang tranh quyền lấy Lock
        ↓ lấy được
kiểm tra lại trạng thái trong vùng khóa
```

Đây là mô hình để hiểu quyền chạy, không yêu cầu ứng dụng tự thao tác vào hàng chờ nội bộ của thư viện.

Trong lúc A chờ condition, khóa liên quan được nhả. Nếu A còn giữ một khóa ứng dụng khác, `await` không tự nhả khóa khác đó. Giữ thêm khóa mà B cần có thể tạo chu trình chờ dù đã dùng condition đúng ở lớp ngoài.

## 4. Vì sao bắt buộc kiểm tra bằng `while`?

Không nên viết:

```java
if (!ready) {
    readyCondition.await();
}
useReadyState();
```

Đây là đoạn minh họa lỗi trong giao thức chờ. Có ít nhất hai lý do phải kiểm tra lại:

**Đánh thức không do tín hiệu mong đợi:** API cho phép đánh thức giả (spurious wakeup), nên `await` có thể trở về mà trạng thái chưa đáp ứng.

**Trạng thái thay đổi trước lúc lấy lại khóa:** một bên khác có thể dùng mất tài nguyên trước khi luồng vừa được đánh thức lấy lại khóa. Ví dụ hai bên lấy cùng chờ dữ liệu, một phần tử được thêm, nhưng chỉ một bên lấy được phần tử đó.

Vì vậy, ý nghĩa đúng là “được nhắc kiểm tra lại”, không phải “đã được cấp chắc chắn tài nguyên”. `while` thể hiện điều kiện cho phép tiến hành và tiếp tục bảo vệ nó dưới cùng khóa.

Việc đọc biến điều kiện ở ngoài khóa rồi chỉ khóa quanh `await` cũng không tạo cùng giao thức: trạng thái có thể đổi giữa lần kiểm tra và lúc bắt đầu chờ. Hãy giữ cả kiểm tra, chờ, cập nhật liên quan và phát tín hiệu trong cấu trúc được thiết kế bằng cùng khóa.

## 5. `signal` không chuyển giao khóa và không lưu một vé cho tương lai

`signal()` chọn một luồng đang chờ condition để đánh thức. `signalAll()` đánh thức tất cả bên đang chờ condition đó. Sau khi được đánh thức, các luồng vẫn cần lấy lại khóa và kiểm tra điều kiện.

Phía tạo điều kiện thường làm:

```java
lock.lock();
try {
    ready = true;
    readyCondition.signalAll();
} finally {
    lock.unlock();
}
```

Đoạn này giả định các biến đã khai báo phù hợp. Cập nhật trạng thái trước rồi báo dưới cùng khóa làm ý định rõ ràng. Phát tín hiệu không tự sửa biến `ready`; chỉ `signalAll()` mà vẫn giữ `ready == false` sẽ khiến các bên được đánh thức quay lại chờ.

Nếu chưa có ai chờ, `signal` không tích trữ một “vé đánh thức”. Điều giữ lại ý nghĩa cho bên đến sau là trạng thái đã được cập nhật. Bên đến sau lấy khóa, thấy `ready == true` và không gọi `await`.

Không gọi `signal` ngoài khóa liên quan khi dùng condition của `ReentrantLock`. Cũng không giữ khóa sau khi báo rồi chờ bên nhận làm tiếp: nó chưa thể tiến vào vùng khóa cho đến khi bên báo nhả.

## 6. Ví dụ Java 17+: một ô đệm và hai nhóm chờ

Lưu thành `ConditionSlotDemo.java`. Ô đệm giữ tối đa một số nguyên. Bên đưa chờ `notFull` khi đầy; bên lấy chờ `notEmpty` khi trống. Biến `full` và `value` đều được bảo vệ bằng cùng khóa.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionSlotDemo {
    static final class IntSlot {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private boolean full;
        private int value;

        void put(int next) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (full) {
                    notFull.await();
                }
                value = next;
                full = true;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take(CountDownLatch firstWait) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!full) {
                    firstWait.countDown();
                    notEmpty.await();
                }
                int result = value;
                full = false;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        IntSlot slot = new IntSlot();
        CountDownLatch firstWait = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Future<List<Integer>> consumer = null;
        Future<Void> producer = null;

        try {
            consumer = pool.submit(() -> {
                List<Integer> received = new ArrayList<>();
                for (int i = 0; i < 3; i++) {
                    received.add(slot.take(firstWait));
                }
                return received;
            });

            if (!firstWait.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not reach wait");
            }
            producer = pool.submit((Callable<Void>) () -> {
                slot.put(10);
                slot.put(20);
                slot.put(30);
                return null;
            });

            producer.get(5, TimeUnit.SECONDS);
            List<Integer> received = consumer.get(5, TimeUnit.SECONDS);
            System.out.println("received: " + received);
            System.out.println("sum: "
                    + received.stream().mapToInt(Integer::intValue).sum());
        } finally {
            if (producer != null) {
                producer.cancel(true);
            }
            if (consumer != null) {
                consumer.cancel(true);
            }
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not terminate");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConditionSlotDemo.java
java ConditionSlotDemo
```

Stdout khi hai tác vụ hoàn tất trong thời hạn minh họa:

```text
received: [10, 20, 30]
sum: 60
```

Điểm cần đọc từ ví dụ:

1. Trước khi cho bên đưa chạy, luồng chính đợi bên lấy đến bước chờ ô trống. `firstWait` chỉ là công cụ điều phối ví dụ, không phải trạng thái nghiệp vụ của ô đệm.
2. Bên lấy gọi `countDown` khi vẫn đang giữ khóa, ngay trước `await`. Dù bên đưa được lập lịch ngay sau đó, nó vẫn phải lấy khóa; quá trình chờ condition phối hợp nhả khóa nên không phải một khoảng “nhả trước, đăng ký chờ sau” do ứng dụng tự ghép.
3. Sau khi `put` ghi giá trị và đặt `full = true`, nó báo `notEmpty`. Sau khi `take` lấy giá trị và đặt `full = false`, nó báo `notFull`.
4. Các thay đổi của `full` và `value` nằm dưới cùng khóa. Không cần đánh dấu hai trường là `volatile` nếu mọi truy cập đều tuân theo đúng giao thức này.
5. Không cần `sleep` để đoán đã có dữ liệu. Bên lấy chỉ tiếp tục khi vòng `while` xác nhận điều kiện dưới khóa.

Chương trình biết trước có đúng ba phần tử và ba lần lấy, nên kết thúc hữu hạn. `IntSlot` không có giao thức đóng hay nhiều nguồn dữ liệu; không dùng nó như một hàng đợi tổng quát có vòng đời hoàn chỉnh. Trong ứng dụng cần hàng đợi tiêu chuẩn, ưu tiên `BlockingQueue` phù hợp thay vì tự viết lại cấu trúc chỉ để dùng condition.

## 7. Chọn `signal` hay `signalAll` theo điều kiện

`signal` có thể phù hợp khi mỗi lần cập nhật chỉ tạo điều kiện cho một bên chờ và các bên trong cùng nhóm có cùng điều kiện chờ. Ví dụ một lần đưa tạo một phần tử cho nhóm đang chờ `notEmpty`; một lần lấy tạo một chỗ cho nhóm đang chờ `notFull`.

`signalAll` thường cần cân nhắc khi:

- Một thay đổi cho phép nhiều bên tiếp tục, chẳng hạn tài nguyên đã khởi tạo xong cho toàn bộ người đọc.
- Cùng một condition được dùng cho nhiều biểu thức chờ khác nhau mà không bảo đảm bên được chọn có thể tiến triển.
- Trạng thái chuyển sang đóng/dừng khiến mọi bên đang chờ phải thức dậy để thoát theo chính sách.

Dùng `signalAll` không bỏ được vòng `while`: các bên cùng thức sẽ tranh khóa, và điều kiện có thể chỉ còn đúng với một số bên. Đánh thức nhiều bên không cần thiết cũng có chi phí.

Không giải thích việc chọn luồng chỉ bằng tên `Condition`. Hợp đồng giao diện cho phép các triển khai có chính sách riêng. Với condition của `ReentrantLock`, thư viện có quy tắc báo theo thứ tự chờ, nhưng việc được báo và việc được lập lịch/lấy lại khóa vẫn là các bước khác nhau. Đừng dựa vào một thứ tự chạy toàn hệ thống mà API không cam kết.

## 8. Chờ có thời hạn vẫn phải kiểm tra lại trạng thái

Một mẫu dùng `awaitNanos`:

```java
lock.lockInterruptibly();
try {
    long remaining = timeoutNanos;
    while (!ready) {
        if (remaining <= 0) {
            return false;
        }
        remaining = readyCondition.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
```

Đây là thân phương thức minh họa, cần đặt trong ngữ cảnh có kiểu trả về `boolean`, khai báo `InterruptedException`, cùng các biến phù hợp. Giá trị thời gian còn lại được đưa vào vòng sau, thay vì bắt đầu lại toàn bộ timeout sau mỗi lần đánh thức.

Không dùng một lần trở về từ `await` như chứng nhận rằng `ready` đã đúng. Với `await(time, unit)`, boolean trả về cũng liên quan đến kết quả chờ chứ không tự đánh giá biến nghiệp vụ. Luôn kiểm tra lại biểu thức trạng thái trong giao thức đã khóa.

Mẫu trên chỉ đặt ngân sách cho bước chờ condition theo cách thể hiện. Nó không tính thời gian lấy khóa ban đầu vào cùng một ngân sách tổng. Nếu yêu cầu thời hạn tổng từ lúc bắt đầu phương thức, cần tính phần còn lại bằng một mốc thời gian chung và giới hạn cả các bước liên quan.

Luồng còn phải lấy lại khóa trước khi hoàn tất chờ, nên timeout không bảo đảm nó sẽ trở về đúng mốc đồng hồ nếu khóa còn đang bị giữ hoặc luồng được lập lịch muộn.

## 9. Ngắt, dừng và đường thoát

`await()` hỗ trợ `InterruptedException`. Với condition của `ReentrantLock`, khi việc chờ thoát vì ngắt, luồng lấy lại khóa trước khi ngoại lệ được đưa ra; khối `finally` vẫn có trách nhiệm nhả khóa đã sở hữu.

Đây là điểm khác với ngắt trong `lockInterruptibly` ở ngay trước `try`: nếu chưa lấy được khóa ban đầu thì chưa vào khối cần nhả. Giữ đúng cấu trúc giúp không nhả thiếu hoặc nhả khóa chưa sở hữu.

Một lớp có thể truyền `InterruptedException` ra để tầng quản lý quyết định. Nếu ở biên `Runnable` và quyết định dừng, thường khôi phục cờ ngắt rồi thoát theo chính sách. Không bắt ngắt rồi quay lại chờ vô hạn nếu mục tiêu là cho phép hủy.

Khi có trạng thái đóng, một vòng chờ có thể cần biểu thức như “chưa có dữ liệu và chưa đóng”. Phương thức đóng phải cập nhật trạng thái dưới khóa và đánh thức những nhóm cần kiểm tra lại. Chỉ đặt một cờ ngoài khóa nhưng không đánh thức sẽ để các luồng còn ngủ không biết đã cần dừng.

`signal` không phải cơ chế khôi phục lỗi của cả hệ thống. Nếu bên được giao tạo dữ liệu đã lỗi, cần tầng quản lý phát hiện và quyết định đóng, hủy hoặc thử lại. Một giao thức condition đúng cục bộ vẫn có thể chờ mãi nếu không ai còn khả năng làm điều kiện thay đổi.

## 10. Các lỗi cần nhận diện

| Lỗi | Hệ quả |
| --- | --- |
| Dùng `if` thay `while` | Tiếp tục khi điều kiện chưa đúng sau đánh thức hoặc tranh chấp |
| Kiểm tra trạng thái ngoài khóa rồi chờ | Có khoảng đua giữa kiểm tra và đăng ký chờ |
| Gọi `await`/`signal` mà không giữ khóa liên quan | Lỗi quyền sở hữu với condition của `ReentrantLock` |
| Chỉ báo mà không cập nhật trạng thái | Bên chờ thức rồi phải chờ lại |
| Báo nhầm condition | Nhóm có thể tiến triển vẫn không được đánh thức |
| Nghĩ `signal` lưu vé khi chưa có ai chờ | Bên đến sau chờ mãi nếu không có trạng thái để nhận biết |
| Giữ khóa rồi `sleep` thay cho `await` | Bên khác không lấy được khóa để thay đổi điều kiện |
| Đợi bên được báo làm tiếp trong khi chưa nhả khóa | Bên đó chưa lấy lại được khóa nên không tiến triển |
| Quên `unlock` trong `finally` | Ngoại lệ có thể giữ khóa và chặn cả hệ thống |

## 11. Tự kiểm tra

1. `Condition` có tự chứa biến boolean mà ứng dụng đang chờ không?
2. Một luồng vừa được `signal` có thể chạy ngay vùng tới hạn đồng thời với bên báo không?
3. Vì sao luồng đến sau một lần báo không cần “vé đánh thức” nếu trạng thái đã đúng?
4. Khi `await` chờ, nó có nhả mọi khóa mà luồng đang giữ không?
5. Có thể dùng `signalAll` để bỏ vòng `while` không?
6. Tại sao bộ đệm dùng hai condition dù cùng một khóa bảo vệ?

Gợi ý: (1) Không, biểu thức điều kiện nằm trên trạng thái của ứng dụng. (2) Không, nó cần lấy lại khóa. (3) Nó kiểm tra trạng thái dưới khóa rồi không cần chờ. (4) Chỉ nhả khóa liên quan theo hợp đồng, không tự nhả khóa khác. (5) Không. (6) Để phân biệt nhóm cần dữ liệu với nhóm cần chỗ trống và báo đúng nhóm có thể tiến triển.
