# `tryLock` và thao tác thử khóa có thời hạn

## 1. Thử khóa là thử lấy quyền truy cập

Khi cần bảo vệ trạng thái dùng chung, một luồng phải lấy đúng khóa trước khi đọc hoặc sửa vùng dữ liệu được bảo vệ. `tryLock` cho phép luồng quyết định không đợi mãi nếu khóa đang bận.

Hai dạng thường dùng trên `ReentrantLock`:

```java
boolean tryLock();
boolean tryLock(long timeout, TimeUnit unit) throws InterruptedException;
```

Cả hai đều **thực sự lấy khóa nếu trả `true`**. Chúng không chỉ hỏi “khóa có rảnh không?”. Sau `true`, luồng có trách nhiệm nhả đúng lần lấy đó. Sau `false`, luồng chưa có quyền truy cập vùng được bảo vệ và không được nhả như thể đã lấy thành công.

Ví dụ tình huống: một tác vụ cập nhật cấu hình chỉ được phép đợi ngắn; nếu khóa đang do tác vụ khác giữ quá lâu, nó cần phản hồi đang bận hoặc thử lại theo chính sách. Đây là quyết định của ứng dụng, không phải một lỗi mà thư viện tự xử lý thay.

Hợp đồng chung của các dạng thử khóa được mô tả tại [Java SE `Lock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html). Bài dùng `ReentrantLock` để nói rõ các hành vi cụ thể đang áp dụng trên Java hiện hành.

## 2. So sánh các đường kết thúc

| Dạng gọi | Khi đang có thể lấy khóa | Khi khóa do luồng khác giữ | Phản hồi ngắt khi lấy khóa trên `ReentrantLock` |
| --- | --- | --- | --- |
| `tryLock()` | Lấy và trả `true` | Trả `false`, không chờ khóa rảnh | Không phải điểm ném `InterruptedException` |
| `tryLock(timeout, unit)` | Có thể lấy và trả `true` | Chờ trong khoảng cho phép; hết khoảng mà chưa lấy được thì trả `false` | Ném `InterruptedException` nếu bị ngắt theo hợp đồng |

Với dạng có thời hạn, phải phân biệt ba kết quả:

```text
true                 → đã lấy khóa, được làm việc trong vùng tới hạn
false                → chưa lấy khóa do không thành công trong khoảng chờ
InterruptedException → yêu cầu ngắt đã chấm dứt việc thử lấy khóa
```

Không biến cả `false` lẫn ngoại lệ ngắt thành thông báo “đã cập nhật thành công”. Cũng không gộp chúng thành “hết thời gian”: bị ngắt thường phục vụ hủy hoặc dừng công việc, có ý nghĩa khác với chỉ gặp tranh chấp khóa.

Nếu khóa rảnh trước khi hết thời gian, lời gọi có thể thành công sớm. Không có yêu cầu phải đợi đủ timeout rồi mới trả kết quả.

## 3. Mẫu dùng đúng: chỉ nhả khi đã lấy thành công

Một phương thức minh họa:

```java
boolean updateWithin(long timeout, TimeUnit unit)
        throws InterruptedException {
    if (!lock.tryLock(timeout, unit)) {
        return false;
    }
    try {
        updateProtectedState();
        return true;
    } finally {
        lock.unlock();
    }
}
```

Đoạn này giả định `lock` là trường `ReentrantLock` ổn định của lớp, `updateProtectedState` là thao tác ứng dụng, và các bên truy cập trạng thái đều tuân theo khóa ấy.

Điểm đặt `try` là quan trọng:

1. Nếu việc lấy khóa ném `InterruptedException`, chưa vào phần thân và không gọi `unlock` cho lần chưa thành công.
2. Nếu trả `false`, kết thúc theo nhánh chưa lấy được khóa.
3. Nếu trả `true`, mọi đường ra khỏi phần thân đều phải qua `finally` để nhả.

Một cách viết sai thường gặp:

```java
try {
    lock.tryLock(100, TimeUnit.MILLISECONDS);
    updateProtectedState();
} finally {
    lock.unlock();
}
```

Đây là mã minh họa lỗi, không phải mẫu dùng được: bỏ qua boolean có thể làm phần thân chạy mà không sở hữu khóa. Nếu chưa sở hữu, `unlock` của `ReentrantLock` gây `IllegalMonitorStateException`.

Một lỗi khác là thao tác có thể ném ngoại lệ nằm giữa lần lấy khóa thành công và khối `try`. Khi đó chương trình có thể lỗi trước khi thiết lập đường nhả khóa.

## 4. Timeout chỉ thuộc bước lấy khóa

Giả sử:

```java
if (lock.tryLock(100, TimeUnit.MILLISECONDS)) {
    try {
        performSlowOperation();
    } finally {
        lock.unlock();
    }
}
```

Đoạn minh họa không đặt thời hạn 100 ms cho `performSlowOperation`. Nếu lấy khóa sau 5 ms rồi công việc chạy 3 giây, khóa vẫn bị giữ trong suốt khoảng công việc đó trừ khi chương trình nhả sớm bằng thiết kế riêng.

Timeout cũng không tự hủy một lời gọi mạng, hoàn tác cập nhật hoặc bảo đảm thời điểm trả về chính xác theo đồng hồ. Lập lịch và tài nguyên hệ thống có thể khiến thời điểm bên gọi quan sát được kết quả muộn hơn mốc chờ dự kiến.

Nếu yêu cầu nghiệp vụ là thời hạn tổng cho toàn bộ thao tác, phải phân bổ ngân sách cho từng bước, theo dõi phần còn lại và có chính sách hủy công việc đang chạy phù hợp. Chỉ thêm timeout vào bước lấy khóa chưa giải quyết hết yêu cầu đó.

Không giữ khóa qua công việc chậm hoặc callback ngoài kiểm soát nếu có thể thiết kế lại an toàn. Một vùng tới hạn quá dài vẫn gây tranh chấp dù các bên chờ có timeout.

## 5. Ví dụ Java 17+ chạy được

Lưu thành `TimedTryLockDemo.java`. Chương trình kiểm chứng khóa đang bận từ một luồng khác, đường ngắt và lần thử thành công sau khi chủ nhả khóa.

```java
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedTryLockDemo {
    private static <T> T callElsewhere(FutureTask<T> task) throws Exception {
        Thread thread = new Thread(task, "attempt");
        thread.start();
        try {
            return task.get(5, TimeUnit.SECONDS);
        } finally {
            task.cancel(true);
            thread.join(1_000);
            if (thread.isAlive()) {
                throw new IllegalStateException("attempt did not stop");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        lock.lock();
        try {
            FutureTask<Boolean> immediate = new FutureTask<>(() -> {
                if (!lock.tryLock()) {
                    return false;
                }
                try {
                    return true;
                } finally {
                    lock.unlock();
                }
            });
            System.out.println("immediate while owned: "
                    + callElsewhere(immediate));

            FutureTask<Boolean> timed = new FutureTask<>(() -> {
                if (!lock.tryLock(25, TimeUnit.MILLISECONDS)) {
                    return false;
                }
                try {
                    return true;
                } finally {
                    lock.unlock();
                }
            });
            System.out.println("timed while owned: " + callElsewhere(timed));

            FutureTask<String> interrupted = new FutureTask<>(() -> {
                Thread.currentThread().interrupt();
                try {
                    if (!lock.tryLock(1, TimeUnit.SECONDS)) {
                        return "timeout";
                    }
                    try {
                        return "acquired";
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException ex) {
                    boolean cleared = !Thread.currentThread().isInterrupted();
                    Thread.currentThread().interrupt();
                    return "interrupted; flag cleared by exception: " + cleared;
                }
            });
            System.out.println(callElsewhere(interrupted));
        } finally {
            lock.unlock();
        }

        FutureTask<Boolean> available = new FutureTask<>(() -> {
            if (!lock.tryLock(1, TimeUnit.SECONDS)) {
                return false;
            }
            try {
                return true;
            } finally {
                lock.unlock();
            }
        });
        System.out.println("timed after release: " + callElsewhere(available));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TimedTryLockDemo.java
java TimedTryLockDemo
```

Stdout khi các tác vụ hoàn tất trong thời hạn kiểm tra của ví dụ:

```text
immediate while owned: false
timed while owned: false
interrupted; flag cleared by exception: true
timed after release: true
```

Vì sao kết quả ổn định?

- Luồng chính giữ khóa và đợi tác vụ thử hoàn tất trước khi nhả. Khóa không thể rảnh ở giữa hai lần thử đầu.
- Lần thử có thời hạn trả `false` vì chủ khóa không nhả trong suốt khoảng đó. Chương trình không khẳng định thời gian thực tế đúng bằng 25 ms.
- Tác vụ thứ ba đặt cờ ngắt trước khi gọi. Nó kiểm chứng phản hồi ngắt ở lúc vào phương thức, không giả định đã ngắt ở một nanosecond cụ thể trong khi luồng đang chờ.
- `InterruptedException` làm cờ ngắt bị xóa theo hợp đồng này; tác vụ khôi phục cờ trước khi kết thúc theo đường hủy.
- Lần cuối bắt đầu sau khi luồng chính đã nhả, không có bên tranh chấp khác, nên lấy được khóa.

`FutureTask` được dùng để chuyển kết quả hoặc lỗi về luồng chính. Các timeout dọn dẹp trong ví dụ là cơ chế kiểm tra, không phải một chính sách hủy hoàn chỉnh cho mọi loại tác vụ.

## 6. Các trường hợp của `ReentrantLock` cần biết

### Thời hạn bằng 0 hoặc âm

`tryLock(timeout, unit)` với `timeout <= 0` không tạo một khoảng chờ dương. Lời gọi vẫn có thể lấy được khóa nếu điều kiện cho phép; không phải mọi giá trị 0 đều buộc trả `false`.

Dạng có thời hạn vẫn kiểm tra ngắt theo hợp đồng. Vì vậy `tryLock(0, unit)` không hoàn toàn giống `tryLock()` chỉ vì cả hai đều không dành thời gian đợi khóa rảnh. `unit` phải khác `null`.

### Vào lại từ chính luồng đang giữ khóa

Nếu luồng hiện tại đã sở hữu `ReentrantLock`, `tryLock()` có thể trả `true` và tăng số lần nắm khóa. Cần thêm một `unlock()` tương ứng cho lần lấy thành công đó.

Không dùng một lần thử từ chủ khóa để kiểm chứng kết quả khi một **luồng khác** gặp khóa bận. Hai tình huống có chủ sở hữu khác nhau.

### Công bằng không giống nhau ở mọi overload

`ReentrantLock(true)` có chính sách công bằng khi tranh chấp, nhưng `tryLock()` không có thời hạn vẫn có thể lấy khóa rảnh trước những bên đang chờ. Dạng có thời hạn tuân theo chính sách công bằng tương ứng của lớp; dùng thời hạn 0 vẫn có khác biệt về kiểm tra ngắt.

Không ghép `tryLock() || tryLock(timeout, unit)` rồi mặc định đã giữ đầy đủ ý nghĩa công bằng của riêng dạng có thời hạn: nhánh đầu có thể đã lấy khóa trước.

### Ngắt là kết quả độc lập

Với `ReentrantLock`, dạng có thời hạn có thể ưu tiên phản hồi ngắt hơn lấy khóa hoặc báo hết thời gian, theo hợp đồng lớp. Không viết mã đòi hỏi một thứ tự thắng tuyệt đối giữa ba sự kiện xảy ra sát nhau mà API không cam kết.

Các chi tiết này được mô tả ở [Java SE `ReentrantLock`, hai overload `tryLock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

## 7. Một ngân sách chờ cho hai khóa

Nếu thao tác cần lấy hai khóa, gọi mỗi khóa với đầy đủ timeout có thể làm tổng thời gian chờ lớn hơn dự kiến. Ví dụ “100 ms cho khóa A rồi 100 ms cho khóa B” không phải ngân sách chờ chung 100 ms.

Đoạn phương thức minh họa sau dùng một ngân sách nhỏ theo nanosecond. Nó giả định hai khóa ổn định, trạng thái chỉ được sửa trong `action`, và các bên dùng thứ tự khóa được thiết kế nhất quán:

```java
static boolean withBoth(ReentrantLock first,
                        ReentrantLock second,
                        long budgetNanos,
                        Runnable action) throws InterruptedException {
    if (budgetNanos <= 0) {
        return false;
    }
    long start = System.nanoTime();
    if (!first.tryLock(budgetNanos, TimeUnit.NANOSECONDS)) {
        return false;
    }
    try {
        long remaining = budgetNanos - (System.nanoTime() - start);
        if (remaining <= 0
                || !second.tryLock(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }
        try {
            action.run();
            return true;
        } finally {
            second.unlock();
        }
    } finally {
        first.unlock();
    }
}
```

Đây là phương thức để đặt trong một lớp có các import `ReentrantLock`, `TimeUnit`; không phải chương trình `main` thứ hai. Các ý cần học:

1. Khi chưa lấy được khóa đầu, không nhả khóa nào.
2. Sau khi lấy khóa đầu, `finally` luôn nhả nó, kể cả khi khóa thứ hai hết thời gian, bị ngắt hoặc `action` ném lỗi.
3. Chỉ nhả khóa thứ hai sau khi chính lần lấy thứ hai thành công.
4. Không cấp lại toàn bộ ngân sách cho lần lấy thứ hai.
5. Phương thức chủ động từ chối khi ngân sách không dương; đó là chính sách của mẫu này, khác với chính API `tryLock(0, unit)` vẫn có thể thử lấy ngay.

`System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng JVM; xem [Java SE `System.nanoTime()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()). Mẫu giả định ngân sách vận hành nhỏ hơn nhiều so với phạm vi tràn số của `long`, không dùng nó để biểu diễn lịch hẹn rất xa.

Ngân sách này vẫn chỉ bao phủ việc chờ lấy hai khóa trước khi chạy hành động. Nó không giới hạn thời gian chạy `action` hoặc bảo đảm thời điểm trở về chính xác tuyệt đối.

## 8. Timeout chưa đủ để ngăn deadlock hoặc livelock

Hai luồng lấy khóa theo hai thứ tự đối nghịch vẫn có thể gây chờ vòng. Việc có timeout cho phép một bên thoát nếu mã nhả đúng các khóa đã giữ, nhưng không thay thế thiết kế thứ tự lấy khóa.

Nếu cả hai bên liên tục lấy khóa đầu, thất bại ở khóa thứ hai, nhả rồi thử lại cùng lúc, chúng có thể hoạt động liên tục mà không hoàn thành công việc; đó là dạng không tiến triển thường gọi là livelock. Cần chính sách thử lại có giới hạn, khoảng chờ phù hợp hoặc thay đổi cách phối hợp, không vòng quay bận vô hạn.

Không viết:

```java
while (!lock.tryLock()) {
    // liên tục thử lại, không có chính sách chờ hoặc hủy
}
```

Nếu mục tiêu thực sự là chờ lấy khóa, chọn một phương thức có cơ chế chờ và ngắt phù hợp. Nếu mục tiêu là thử lại, xác định số lần, ngân sách tổng và cách phản hồi khi cuối cùng vẫn bận.

Trước khi lấy đủ khóa, tránh làm một nửa thay đổi nghiệp vụ rồi hy vọng timeout sẽ tự hoàn tác. Phải thiết kế trạng thái trung gian và đường thất bại rõ ràng; khóa không phải cơ chế giao dịch tự động.

## 9. Những lỗi về quyền sở hữu và dữ liệu cần tránh

| Lỗi | Hệ quả hoặc cách sửa |
| --- | --- |
| Bỏ qua boolean từ `tryLock` | Có thể truy cập trạng thái khi chưa sở hữu khóa |
| `unlock` vô điều kiện dù thử thất bại | Có thể ném `IllegalMonitorStateException` hoặc nhả sai một lần nắm có sẵn do vào lại |
| Quên `finally` sau khi lấy thành công | Ngoại lệ hoặc `return` có thể để khóa bị giữ |
| Dùng `isLocked()` thay cho thử lấy | Quan sát không đặt quyền sở hữu; có khoảng đua ngay sau lần kiểm tra |
| Tạo khóa mới cho mỗi lời gọi | Các luồng không tranh chấp cùng khóa nên không bảo vệ dữ liệu chung |
| Dùng `synchronized(lock)` ở nơi khác | Monitor của đối tượng không phải trạng thái do `ReentrantLock.lock` quản lý |
| Đọc dữ liệu được bảo vệ ở nhánh `false` rồi cho rằng vẫn an toàn | Chưa lấy khóa thì chưa thiết lập quyền truy cập theo giao thức đó |
| Nuốt `InterruptedException` rồi tiếp tục thử mãi | Có thể bỏ qua yêu cầu hủy/dừng |

Ở lớp có thể truyền `InterruptedException` cho bên gọi, hãy để bên gọi quyết định chính sách. Ở biên tác vụ không truyền được checked exception và muốn ngừng, có thể khôi phục cờ ngắt rồi thoát theo thiết kế. Không đổi yêu cầu ngắt thành thành công giả.

## 10. Tự kiểm tra

1. `tryLock()` trả `true` có cần một lời gọi `lock()` bổ sung trước khi sửa dữ liệu không?
2. Thử có thời hạn trả `false` có cho phép gọi `unlock` không?
3. Timeout 100 ms có ép công việc trong vùng khóa kết thúc trong 100 ms không?
4. Vì sao thử khóa với thời hạn 0 có thể khác overload không có thời hạn?
5. Nếu đã lấy khóa A nhưng lấy B bị ngắt, A phải được xử lý thế nào?
6. Vì sao lặp vô hạn `tryLock()` có thể tốn CPU và vẫn không đem lại tiến triển?

Gợi ý: (1) Không, đã lấy khóa; lấy thêm có thể làm tăng số lần nắm trên khóa vào lại. (2) Không cho chính lần thử thất bại. (3) Không. (4) Khác hợp đồng ngắt và công bằng trên `ReentrantLock`. (5) Phải nhả A trên đường thoát. (6) Nó không có chính sách chờ, ngân sách hoặc phối hợp, nên có thể quay bận và tranh chấp lặp lại.
