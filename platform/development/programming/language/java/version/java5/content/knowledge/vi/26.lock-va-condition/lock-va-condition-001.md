# `Lock` và khác biệt về khả năng điều khiển so với `synchronized`

## 1. Cùng bảo vệ vùng dữ liệu dùng chung, khác mức điều khiển

Khi nhiều luồng đọc và sửa cùng một trạng thái, ta thường cần một vùng tới hạn: chỉ một luồng được thực hiện chuỗi thao tác liên quan tại một thời điểm. Các luồng phải tuân theo cùng một quy tắc khóa để bảo vệ trạng thái đó.

`synchronized` là cấu trúc ngôn ngữ dùng monitor gắn với một đối tượng. `Lock` là giao diện cung cấp các thao tác lấy và nhả khóa tường minh; `ReentrantLock` là một lớp triển khai khóa loại trừ tương hỗ có khả năng vào lại.

Trong bài, so sánh chính là giữa `synchronized` và `ReentrantLock`. Không mặc định mọi lớp thực hiện `Lock` đều có chính sách giống `ReentrantLock`: có loại khóa đọc cho phép nhiều bên đọc cùng nắm khóa.

Khác biệt không phải “có an toàn” và “không an toàn”. Nếu dùng đúng, cả hai có thể bảo vệ dữ liệu và thiết lập bảo đảm hiển thị bộ nhớ. `Lock` cung cấp thêm cách điều khiển việc lấy khóa; đổi lại, chương trình phải quản lý việc nhả khóa rõ ràng.

Các khả năng và yêu cầu này được mô tả trong [Java SE `Lock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

## 2. `synchronized`: phạm vi rõ, nhả monitor tự động

Ví dụ một phương thức tăng bộ đếm:

```java
final class MonitorCounter {
    private final Object monitor = new Object();
    private int value;

    void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    int get() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

Đây là một lớp minh họa, chưa có `main`. Đọc và ghi đều dùng cùng `monitor`. Khi một luồng đã vào vùng `synchronized`, luồng khác cần monitor đó phải chờ.

Khi khối kết thúc do chạy hết, `return` hoặc ngoại lệ, monitor được nhả theo cấu trúc ngôn ngữ. Quy tắc này được nêu trong [JLS §14.19, câu lệnh `synchronized`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.19).

Một phương thức instance có từ khóa `synchronized` dùng monitor của `this`; phương thức `static synchronized` dùng monitor của đối tượng `Class` tương ứng. Chúng không tự dùng chung monitor chỉ vì cùng khai báo trong một lớp.

Điểm giới hạn về điều khiển: câu lệnh vào monitor không có tham số “chỉ đợi 200 ms”, không trả `false` khi bận và không cung cấp một biến thể chờ vào monitor có thể hủy bằng `InterruptedException`.

Không nhầm điều này với `Object.wait()`: `wait` là bước chờ điều kiện sau khi đã vào monitor và có giao thức riêng. Thời hạn của `wait` không phải thời hạn để vào khối `synchronized` ban đầu.

## 3. `ReentrantLock`: các cách lấy khóa là những lựa chọn khác nhau

| Cách lấy khóa | Khi khóa đang do luồng khác giữ | Kết quả/đường kết thúc |
| --- | --- | --- |
| `lock()` | Chờ đến khi lấy được | Trở về khi đã nắm khóa; không dùng ngắt để báo thất bại của việc chờ lấy |
| `tryLock()` | Không dành thời gian đợi khóa rảnh | `true` nếu đã lấy được, `false` nếu chưa lấy được |
| `tryLock(timeout, unit)` | Chờ trong khoảng cho phép | `true`, `false` khi hết thời gian, hoặc `InterruptedException` |
| `lockInterruptibly()` | Chờ nhưng có thể phản hồi ngắt | Lấy được khóa hoặc ném `InterruptedException` |

Nếu `tryLock()` trả `true`, luồng đã sở hữu khóa, không phải mới “kiểm tra thấy rảnh”. Nếu trả `false`, luồng chưa được quyền truy cập dữ liệu cần khóa và không được gọi `unlock()` như thể đã lấy thành công.

`lock()` không phải lựa chọn cho yêu cầu “nếu bị ngắt trong lúc đợi khóa thì thoát ngay”. Với yêu cầu hủy chờ như vậy trên `ReentrantLock`, chọn phương thức hỗ trợ ngắt và xử lý đường `InterruptedException` rõ ràng.

Chờ có thời hạn cũng chỉ giới hạn việc cố lấy khóa. Sau khi lấy thành công, nó không tự đặt thời hạn chạy cho đoạn mã đang giữ khóa, không tự gọi `unlock` khi mốc thời gian đến. Thời điểm phương thức thực sự được lập lịch để trở về còn chịu ảnh hưởng của hệ thống; không dùng timeout như một bảo đảm thời gian thực chính xác tuyệt đối.

### Ví dụ phương thức có thể từ chối khi bận

```java
boolean tryIncrement() {
    if (!lock.tryLock()) {
        return false;
    }
    try {
        value++;
        return true;
    } finally {
        lock.unlock();
    }
}
```

Đoạn trên giả định `lock` là trường `ReentrantLock` và `value` chỉ được truy cập theo giao thức ấy. Nhánh `false` phải có ý nghĩa với bên gọi: thử lại theo chính sách, bỏ qua nếu được phép hoặc phản hồi đang bận. Không âm thầm báo thành công khi chưa cập nhật.

## 4. Mẫu `lock` – `try` – `finally` là trách nhiệm bắt buộc

Mẫu dùng thông thường:

```java
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa với `updateState` thuộc ứng dụng. Lời gọi lấy khóa nằm ngay trước `try`. Nhờ đó, nếu lấy khóa thành công, mọi đường thoát qua phần thân đều đi qua `finally` để nhả.

Với lấy khóa có ngắt:

```java
lock.lockInterruptibly();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Nếu `lockInterruptibly()` ném ngoại lệ thì chưa vào `try`, nên không chạy `unlock` cho một khóa chưa sở hữu. Không đặt việc lấy khóa vào trong `try` rồi luôn nhả trong `finally` bất kể nó có thành công hay không.

Với `ReentrantLock`, gọi `unlock()` từ luồng không sở hữu khóa gây `IllegalMonitorStateException`. Quên nhả khóa có thể làm các luồng khác chờ mãi dù luồng đã thực hiện xong công việc hoặc đã lỗi.

Cũng không đặt một thao tác có thể ném lỗi vào giữa lần lấy khóa thành công và khối `try`; nếu thao tác đó lỗi, phần dọn dẹp có thể chưa được thiết lập.

## 5. Ví dụ Java 17+ chạy được: khóa bận, ngắt chờ và lấy lại sau khi nhả

Lưu thành `LockControlDemo.java`. Luồng chính giữ khóa; một tác vụ khác thử lấy khóa. Luồng chính không nhả cho đến khi nhận kết quả nên kết quả “bận” không phụ thuộc việc ngủ một khoảng đoán trước.

```java
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class LockControlDemo {
    private static <T> T runOnOtherThread(FutureTask<T> task) throws Exception {
        Thread worker = new Thread(task, "contender");
        worker.start();
        try {
            return task.get(5, TimeUnit.SECONDS);
        } finally {
            task.cancel(true);
            worker.join(1_000);
            if (worker.isAlive()) {
                throw new IllegalStateException("worker did not terminate");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        lock.lock();
        try {
            FutureTask<String> busy = new FutureTask<>(() -> {
                boolean immediate = lock.tryLock();
                if (immediate) {
                    lock.unlock();
                }
                boolean timed = lock.tryLock(20, TimeUnit.MILLISECONDS);
                if (timed) {
                    lock.unlock();
                }
                return "tryLock while held: " + immediate
                        + "\ntimed tryLock while held: " + timed;
            });
            System.out.println(runOnOtherThread(busy));

            FutureTask<String> interrupted = new FutureTask<>(() -> {
                Thread.currentThread().interrupt();
                try {
                    lock.lockInterruptibly();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return "interruptible acquire: cancelled";
                }
                try {
                    return "interruptible acquire: acquired";
                } finally {
                    lock.unlock();
                }
            });
            System.out.println(runOnOtherThread(interrupted));
        } finally {
            lock.unlock();
        }

        FutureTask<Boolean> afterRelease = new FutureTask<>(() -> {
            if (!lock.tryLock(1, TimeUnit.SECONDS)) {
                return false;
            }
            try {
                return true;
            } finally {
                lock.unlock();
            }
        });
        System.out.println("acquire after release: "
                + runOnOtherThread(afterRelease));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LockControlDemo.java
java LockControlDemo
```

Stdout khi các tác vụ hoàn tất trong thời hạn của ví dụ:

```text
tryLock while held: false
timed tryLock while held: false
interruptible acquire: cancelled
acquire after release: true
```

Giải thích:

1. Hai lần thử đầu chạy trên luồng khác trong khi luồng chính vẫn sở hữu khóa, nên đều thất bại. `tryLock` có thời hạn dùng đường trả `false`; không có luồng nhả khóa trong khoảng chờ đó.
2. Tác vụ tiếp theo chủ động đặt cờ ngắt trước khi gọi `lockInterruptibly`. Với `ReentrantLock`, lời gọi phản hồi bằng `InterruptedException`. Đây là minh họa việc kiểm tra ngắt khi vào phương thức, không khẳng định đã thử một lịch ngắt chính xác giữa lúc đang đợi.
3. Luồng chính nhả trong `finally`. Tác vụ cuối lấy được khóa và cũng nhả trong `finally`.
4. Các `FutureTask` chuyển lỗi tác vụ về luồng chính; thời hạn kiểm tra chỉ nhằm tránh ví dụ chờ vô hạn khi có lỗi. Chương trình không dựa vào thời lượng chính xác 20 ms để in kết quả.

Không thử `tryLock()` từ chính luồng đang giữ `ReentrantLock` rồi kết luận “khóa không bận”: luồng chủ có thể vào lại và lần thử có thể thành công. Đó là lý do ví dụ dùng một luồng khác.

## 6. Vào lại, quyền sở hữu và bảo đảm bộ nhớ

Cả monitor của `synchronized` và `ReentrantLock` đều hỗ trợ vào lại: một luồng đang sở hữu có thể lấy lại cùng khóa theo quy tắc tương ứng. Với `ReentrantLock`, mỗi lần lấy thành công tăng số lần nắm; phải có số lần `unlock` tương ứng để thực sự giải phóng.

Một lần nhả khóa và lần lấy thành công tiếp theo trên cùng khóa thiết lập quan hệ hiển thị bộ nhớ cần thiết. Việc đổi từ `synchronized` sang `ReentrantLock` không yêu cầu đánh dấu mọi trường đã được bảo vệ đúng bằng `volatile` chỉ vì tên khóa khác nhau.

Tuy nhiên, các bên phải dùng **cùng cơ chế**. Đoạn sau không phối hợp với `lock.lock()` ở nơi khác:

```java
synchronized (lock) {
    updateState();
}
```

Monitor của đối tượng `lock` và trạng thái khóa do các phương thức `Lock` quản lý là hai cơ chế khác nhau. Có cùng tham chiếu đối tượng trong mã không làm hai giao thức khóa tương đương.

Tương tự, tạo một `new ReentrantLock()` trong mỗi lần gọi không bảo vệ dữ liệu chung giữa các lần gọi: các luồng đang lấy các khóa khác nhau. Thường giữ một trường khóa ổn định và riêng của đối tượng quản lý trạng thái.

## 7. `Condition`: chia các nhóm chờ theo điều kiện

Với monitor, `wait`, `notify` và `notifyAll` làm việc với tập chờ gắn với đối tượng monitor. Với `ReentrantLock`, có thể tạo nhiều `Condition` từ một khóa để biểu diễn các điều kiện khác nhau, chẳng hạn “hàng chưa rỗng” và “hàng chưa đầy”.

Đoạn minh họa dạng ý tưởng:

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

Đoạn này giả định `readyCondition` được tạo từ chính `lock`, `ready` được bảo vệ bởi khóa ấy, còn `useReadyState` là mã ứng dụng. Khi chờ trên condition của `ReentrantLock`, luồng nhả khóa liên quan trong lúc đợi và phải lấy lại trước khi tiếp tục sau lần chờ. Phía cập nhật trạng thái và phát tín hiệu cũng phải theo cùng giao thức.

Dùng `while` để kiểm tra lại điều kiện, không chỉ `if`: có thể có đánh thức không do tín hiệu mong muốn, hoặc luồng khác thay đổi trạng thái trước khi luồng đang chờ lấy lại khóa. Tín hiệu không phải dữ liệu nghiệp vụ; biến điều kiện được bảo vệ mới quyết định có thể tiếp tục hay không.

Khả năng nhiều `Condition` là một lý do chọn khóa tường minh, nhưng không tự chứng minh một giao thức chờ/phát tín hiệu đã đúng. Bài này giới thiệu khác biệt điều khiển; thiết kế toàn bộ hàng đợi có giới hạn cần phân tích thêm các điều kiện và đường dừng.

## 8. Công bằng và quan sát trạng thái khóa

`ReentrantLock` có tùy chọn công bằng (`fairness`) khi khởi tạo. Nó có thể ưu tiên những bên đã chờ lâu hơn khi có tranh chấp, với đánh đổi hiệu năng cần được đo đạc. Điều đó không bảo đảm hệ điều hành lập lịch mọi luồng công bằng hoặc mỗi luồng có một độ trễ tối đa cố định.

Một chi tiết của `ReentrantLock`: `tryLock()` không có thời hạn không tuân theo tùy chọn công bằng theo cùng cách như các đường lấy khóa có chờ. Nó có thể lấy ngay khóa đang rảnh dù đang có bên khác chờ. Nếu chính sách công bằng là yêu cầu, phải đọc hợp đồng của phương thức cụ thể, không chỉ nhìn tham số constructor.

Các hành vi vào lại, công bằng và thử lấy khóa được nêu trong [Java SE `ReentrantLock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Các phương thức quan sát như `isLocked()` không đặt chỗ cho người gọi. Đừng kiểm tra “khóa đang rảnh” rồi tự truy cập dữ liệu mà chưa lấy khóa; trạng thái có thể thay đổi ngay sau quan sát. Nếu cần thử lấy, dùng `tryLock()` và xử lý kết quả của chính thao tác lấy đó.

## 9. Tính linh hoạt không tự ngăn deadlock

Khóa tường minh cho phép lấy và nhả ở các phạm vi linh hoạt hơn khối `synchronized`, nhưng cũng dễ bỏ sót đường nhả hoặc tạo thứ tự lấy khóa không nhất quán.

Nếu luồng A giữ khóa X rồi đợi Y, trong khi luồng B giữ Y rồi đợi X, việc dùng `ReentrantLock` thay monitor không tự phá chu trình đó. Các hướng giải quyết gồm quy định thứ tự lấy khóa, giảm vùng giữ khóa hoặc thiết kế thử lấy có thời hạn kèm hoàn tác đúng.

Khi thử nhiều khóa, phải biết khóa nào thật sự đã lấy được, nhả đúng các khóa đó trên mọi đường thất bại và không để lại trạng thái nghiệp vụ bị cập nhật dở. Chỉ thêm timeout mà không giải phóng khóa đã giữ vẫn có thể gây nghẽn hoặc lỗi dữ liệu.

Tránh giữ khóa qua thao tác mạng chậm hoặc gọi mã bên ngoài không kiểm soát khi không cần thiết. Khả năng ngắt **lúc đợi lấy khóa** không làm mọi công việc bên trong vùng khóa trở nên có thể hủy.

## 10. Khi nào nên chọn cách nào?

| Nhu cầu | Lựa chọn có thể phù hợp |
| --- | --- |
| Một vùng tới hạn đơn giản, phạm vi rõ, muốn nhả tự động khi thoát | `synchronized` |
| Muốn trả lời ngay khi khóa bận | `ReentrantLock.tryLock()` |
| Muốn giới hạn khoảng chờ lấy khóa | `ReentrantLock.tryLock(timeout, unit)` |
| Muốn hủy chờ lấy khóa bằng ngắt | `ReentrantLock.lockInterruptibly()` hoặc đường có thời hạn |
| Muốn nhiều nhóm chờ điều kiện trên cùng khóa | `ReentrantLock` kết hợp các `Condition` |
| Thuật toán cần cấu trúc lấy/nhả linh hoạt hơn phạm vi một khối | Khóa tường minh, với quản lý đường nhả cẩn thận |

Đừng chọn chỉ vì cho rằng một loại luôn nhanh hơn. Hiệu năng phụ thuộc JVM, mức tranh chấp, độ dài vùng tới hạn và cách sử dụng. Đo trên tình huống đại diện sau khi đã xác định đúng yêu cầu điều khiển và tính đúng.

## 11. Tự kiểm tra

1. Nếu `tryLock()` trả `false`, có được sửa dữ liệu rồi gọi `unlock` không?
2. Timeout của `tryLock` có giới hạn thời gian chạy sau khi đã lấy khóa không?
3. Vì sao `synchronized(lock)` không thay được `lock.lock()`?
4. Nếu đã dùng `ReentrantLock`, còn cần `finally` khi phần thân có thể ném ngoại lệ không?
5. Vì sao thử khóa từ chính luồng đang sở hữu có thể khác thử từ luồng khác?
6. Chuyển hai monitor gây deadlock sang hai `ReentrantLock` có tự sửa deadlock không?

Gợi ý: (1) Không, chưa sở hữu khóa. (2) Không, chỉ liên quan quá trình lấy khóa. (3) Chúng dùng hai cơ chế khóa khác nhau. (4) Có, phải nhả trên mọi đường thoát sau khi lấy thành công. (5) `ReentrantLock` cho phép vào lại. (6) Không, vẫn phải sửa quan hệ chờ hoặc thứ tự lấy khóa.
