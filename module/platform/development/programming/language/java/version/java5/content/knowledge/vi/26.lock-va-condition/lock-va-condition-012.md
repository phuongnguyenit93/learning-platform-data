# Phối hợp thứ tự khóa để phòng tránh deadlock

Mỗi tài khoản có một khóa riêng. Chuyển tiền từ A sang B cần giữ cả hai khóa để kiểm tra và cập nhật nhất quán. Nếu một luồng khóa A rồi chờ B, còn luồng khác khóa B rồi chờ A, cả hai có thể dừng mãi dù mỗi khóa riêng hoạt động đúng.

Giải pháp quan trọng là **mọi đường chạy cùng tuân thủ một thứ tự lấy khóa ổn định**, không lấy theo chiều nghiệp vụ như “tài khoản nguồn trước, tài khoản đích sau”.

## 1. Vòng chờ hình thành như thế nào?

Lịch xen kẽ gây bế tắc (deadlock):

```text
Luồng T1: giữ khóa A, yêu cầu khóa B.
Luồng T2: giữ khóa B, yêu cầu khóa A.

T1 đợi tài nguyên do T2 giữ.
T2 đợi tài nguyên do T1 giữ.
Không luồng nào tới được bước trả khóa.
```

Một đồ thị chờ có thể viết:

```text
T1 → khóa B → T2 → khóa A → T1
```

Với các khóa độc quyền không bị thu hồi cưỡng bức trong tình huống này, vòng chờ khép kín làm các bên không tự tiến triển.

Deadlock thường được phân tích qua các điều kiện: tài nguyên có quyền sở hữu độc quyền, luồng giữ một tài nguyên trong khi chờ tài nguyên khác, tài nguyên không bị tự động thu hồi và tồn tại chờ vòng. Một thứ tự lấy khóa chung nhắm vào việc loại bỏ khả năng chờ vòng.

Java không tự ngăn hoặc bắt buộc phát hiện deadlock; trách nhiệm thiết kế thuộc chương trình. [JLS 17.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.1).

## 2. Vì sao try/finally chưa đủ?

Đoạn dưới chỉ là phân tích một cách lấy khóa nguy hiểm; không chạy hai đoạn đối nghịch như chương trình minh họa:

```java
from.lock.lock();
try {
    to.lock.lock();
    try {
        moveMoney();
    } finally {
        to.lock.unlock();
    }
} finally {
    from.lock.unlock();
}
```

`finally` bảo đảm trả khóa khi luồng thoát vùng tương ứng, nhưng luồng có thể chưa thoát được lời gọi lấy khóa thứ hai. Nếu hai luồng cùng mắc ở đó theo thứ tự ngược, chưa luồng nào tới phần mở khóa.

Phải giữ cả hai trách nhiệm:

- **Thứ tự lấy khóa:** tránh vòng chờ giữa các bên.
- **try/finally theo từng lần lấy thành công:** trả đúng khóa khi thành công, return hoặc lỗi.

Mẫu mở khóa trong `finally` và các dạng lấy khóa được nêu trong [Lock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

## 3. Chọn một thứ tự chung

Ví dụ đặt quy tắc: tài khoản có `id` nhỏ hơn được khóa trước. Khi chuyển hai chiều:

```text
A(id=1) → B(id=2): lấy khóa 1 rồi 2.
B(id=2) → A(id=1): vẫn lấy khóa 1 rồi 2.
```

Một luồng có thể phải chờ khóa 1 trước khi giữ gì cả, nhưng không có luồng nào giữ khóa 2 rồi đòi khóa 1 theo quy tắc này.

### Lập luận không có vòng chờ

Nếu mọi lần lấy thêm khóa đều đi từ hạng nhỏ sang hạng lớn, một vòng chờ sẽ đòi hỏi:

```text
hạng 1 < hạng 2 < ... < hạng cuối < hạng 1
```

Điều đó không thể đúng với một thứ tự tăng nghiêm ngặt. Đây là lý do thiết kế có cơ sở, thay vì chỉ dựa vào việc chạy thử nhiều lần chưa thấy treo.

Quy tắc phải áp dụng cho **mọi đường có thể giữ nhiều khóa liên quan**, gồm hàm trợ giúp, mã lỗi, callback và tác vụ nền. Một hàm đúng không bảo vệ được toàn hệ thống nếu hàm khác vẫn khóa theo chiều ngược.

## 4. Chương trình chạy đầy đủ

Lưu thành `LockOrderingDemo.java`. Số dư dùng đơn vị nguyên nhỏ nhất để giữ ví dụ tập trung vào đồng bộ hóa. Đây là mô hình trong bộ nhớ của một JVM, không phải thiết kế giao dịch tài chính đầy đủ.

```java
import java.util.concurrent.locks.ReentrantLock;

public class LockOrderingDemo {
    static final class Account {
        final int id;
        final ReentrantLock lock = new ReentrantLock();
        private long balance;

        Account(int id, long balance) {
            if (balance < 0) {
                throw new IllegalArgumentException("negative balance");
            }
            this.id = id;
            this.balance = balance;
        }

        long balance() {
            lock.lock();
            try {
                return balance;
            } finally {
                lock.unlock();
            }
        }
    }

    static void transfer(Account from, Account to, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (from == to) {
            return;
        }
        if (from.id == to.id) {
            throw new IllegalArgumentException("distinct accounts need unique ids");
        }

        Account first = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;
        first.lock.lock();
        try {
            second.lock.lock();
            try {
                if (from.balance < amount) {
                    throw new IllegalStateException("insufficient balance");
                }
                long credited = Math.addExact(to.balance, amount);
                from.balance -= amount;
                to.balance = credited;
            } finally {
                second.lock.unlock();
            }
        } finally {
            first.lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Account a = new Account(1, 10_000);
        Account b = new Account(2, 10_000);

        Thread forward = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                transfer(a, b, 1);
            }
        }, "forward");
        Thread reverse = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                transfer(b, a, 1);
            }
        }, "reverse");

        forward.start();
        reverse.start();
        forward.join();
        reverse.join();

        System.out.println("A: " + a.balance());
        System.out.println("B: " + b.balance());
        System.out.println("total: " + (a.balance() + b.balance()));
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 LockOrderingDemo.java
java LockOrderingDemo
```

Stdout khi hai luồng hoàn tất bình thường:

```text
A: 10000
B: 10000
total: 20000
```

### Những chi tiết giữ thiết kế đúng

1. Hai chiều truyền tham số khác nhau, nhưng `first`/`second` luôn được tính bằng cùng thứ tự `id` tăng dần.
2. Hàm từ chối hai đối tượng khác nhau có cùng `id`, vì không thể để khóa hòa hạng rồi tùy chiều gọi mà chọn thứ tự khác.
3. Trường hợp `from == to` được xử lý riêng. Không cần lấy cùng một khóa hai lần chỉ để chuyển cho chính tài khoản đó.
4. Mỗi lần lấy khóa có `try/finally` tương ứng. Nếu kiểm tra số dư hoặc phép cộng ném ngoại lệ, cả hai khóa vẫn được trả.
5. Tính `credited` bằng `Math.addExact` trước khi thay đổi hai số dư để lỗi tràn phép cộng không xảy ra sau khi đã trừ nguồn. Kiểm tra đủ tiền cũng xảy ra trước cập nhật.
6. Mỗi luồng chỉ chuyển ra tổng cộng 1.000 đơn vị, trong khi số dư đầu mỗi bên là 10.000; vì vậy ví dụ không thiếu tiền dù lịch chạy lệch hoàn toàn về một phía.
7. `main` đọc tổng sau khi `join()` cả hai luồng. Nếu cần ảnh chụp tổng trong lúc chuyển vẫn đang diễn ra, hai lần gọi `balance()` riêng không tự là một ảnh chụp nguyên tử của cặp tài khoản.

`join()` không có thời hạn ở đây phục vụ chờ hoàn tất để lấy kết quả xác định. Nó không biến thành cam kết thời gian thực: bộ lập lịch vẫn cần cho các luồng tiến triển. Đảm bảo thiết kế là không tạo vòng chờ do thứ tự hai khóa trong chương trình, không phải bảo đảm mọi máy hoàn thành trong một số mili giây.

## 5. Hạng khóa phải ổn định và xử lý được va chạm

Những thuộc tính quan trọng của hạng:

- Không đổi trong khi đối tượng còn có thể tham gia lấy khóa.
- So sánh có thứ tự nhất quán trên mọi bên gọi.
- Phân biệt được những khóa khác nhau, hoặc có cách xử lý hòa hạng được thiết kế rõ ràng.

Không dùng số dư, thời gian cập nhật hay tên có thể sửa làm thứ tự, vì hai luồng có thể suy ra hai thứ tự khác nhau khi dữ liệu đổi.

`hashCode()` và `System.identityHashCode()` không bảo đảm duy nhất. Nếu dùng chúng để chọn thứ tự mà không xử lý va chạm, hai đối tượng cùng giá trị băm có thể lại bị khóa theo chiều tham số. Có thể cần hạng duy nhất do hệ thống cấp hoặc một khóa phân xử hòa hạng chung; không bỏ qua trường hợp hòa chỉ vì ít gặp.

Trong ví dụ, cùng một tài khoản logic phải tương ứng với một đối tượng/khóa được chia sẻ phù hợp. Tạo hai đối tượng độc lập cho cùng tài khoản rồi mỗi bên giữ khóa riêng không cung cấp bảo vệ chung cho một tài nguyên bên ngoài. Thứ tự đúng không sửa được sai mô hình quyền sở hữu tài nguyên.

## 6. Nhiều tài nguyên và phân cấp khóa

Nếu một thao tác cần khóa một tập tài nguyên được xác định động:

1. Xác định tập tài nguyên cần bảo vệ.
2. Loại các tham chiếu trùng và xử lý hạng trùng theo chính sách.
3. Sắp theo cùng thứ tự toàn cục.
4. Lấy lần lượt, ghi nhận những khóa đã thật sự lấy thành công.
5. Trả các khóa đã lấy theo thứ tự ngược, kể cả khi bước sau lỗi hoặc bị ngắt.

Không lấy một khóa rồi vừa duyệt vừa phát hiện và lấy tùy ý thêm khóa có hạng nhỏ hơn. Nếu buộc phải nhả rồi lấy lại theo tập đầy đủ, trạng thái có thể đã đổi trong khoảng đó và phải được kiểm tra lại.

Với các loại khóa khác nhau, có thể cần một phân cấp như `khóa registry → khóa tài nguyên → khóa bộ đệm`, cộng thứ tự theo id bên trong cùng cấp. Mọi bên cần hiểu cùng quy tắc.

Cũng phải tính các khóa ẩn trong phương thức được gọi. Gọi callback hoặc mã ngoài tầm kiểm soát khi đang giữ khóa có thể làm xuất hiện một cạnh lấy khóa mới mà người viết hàm không thấy.

## 7. tryLock và ngắt là công cụ bổ sung

`tryLock(timeout, unit)` cho phép từ bỏ chờ sau ngân sách và `lockInterruptibly()` cho phép phản ứng với tín hiệu hủy theo hợp đồng. Nếu không lấy được khóa thứ hai, phải trả khóa thứ nhất trước khi kết thúc hoặc thử lại. [ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Nhưng không chỉ thêm timeout rồi kết luận thiết kế đã không thể lỗi:

- Timeout có thể làm thao tác thất bại hợp lệ; bên gọi phải có chính sách xử lý.
- Hai bên cùng nhả rồi cùng thử lại liên tục có thể không tạo tiến triển hữu ích, tức livelock.
- Một bên có thể liên tục thua và chờ rất lâu, tức starvation.
- Các lần thử lại phải dùng ngân sách chung hoặc giới hạn số lần theo mục tiêu; không vô tình chờ vô hạn bằng cách luôn cấp lại toàn bộ thời gian.

Khóa công bằng chỉ liên quan cách phân xử trên một khóa. Nó không phá vòng T1 giữ A chờ B, T2 giữ B chờ A. Đổi tất cả `ReentrantLock` thành chế độ fair không thay thế thứ tự toàn cục.

Tương tự, `interrupt()` không tự tước khóa khỏi chủ đang giữ. Dùng `lock()` không có nghĩa luồng sẽ ném ngoại lệ ngắt khi chờ; phải chọn API và giao thức hủy phù hợp.

## 8. Deadlock có thể vượt ngoài thứ tự hai khóa

Thứ tự khóa loại trừ một nguồn vòng chờ, nhưng còn các phụ thuộc khác:

```text
T1 giữ khóa A rồi join T2.
T2 cần khóa A để kết thúc.
```

Hoặc một bên giữ khóa ngoài rồi `await()` trên condition của một khóa khác; `await` chỉ nhả khóa gắn với condition, nên khóa ngoài vẫn có thể chặn bên cập nhật.

Khi rà soát, không chỉ tìm các lệnh `lock()`. Cần tìm cả `join`, `Future.get`, chờ condition, chờ I/O hoặc tài nguyên bên ngoài trong lúc giữ khóa. Một khóa JVM cũng không tự bảo vệ giao dịch giữa nhiều JVM hoặc thay thế khóa của cơ sở dữ liệu.

Giữ vùng khóa gọn và không chờ một tác vụ cần chính tài nguyên đang giữ để hoàn tất. Những quy tắc này bổ sung cho thứ tự lấy khóa, không phải các cách diễn đạt trùng nhau.

## 9. Kiểm chứng và chẩn đoán

Một bài kiểm tra hữu ích tạo các thao tác nhiều chiều cùng lúc, xác nhận mọi bên hoàn tất trong ngân sách kiểm tra và kiểm tra bất biến dữ liệu cuối. Khi kiểm tra treo, phải có cơ chế dừng/thu dọn luồng hoặc chạy trong tiến trình thử nghiệm riêng; đừng tạo một ví dụ deadlock không thể kết thúc trong bộ kiểm thử chính.

Kết quả chạy thành công không chứng minh không còn đường lấy khóa ngược ở mã khác. Cần rà sơ đồ sở hữu/chờ và mọi đường vào vùng nhiều khóa.

Khi điều tra một JVM đang treo, thông tin luồng và khóa có thể chỉ ra chu kỳ sở hữu. `ThreadMXBean.findDeadlockedThreads()` hỗ trợ tìm một số chu kỳ chờ monitor hoặc ownable synchronizer của **platform thread**, không phải máy dò mọi dạng treo ứng dụng hay mọi virtual thread. Xem phạm vi và khả năng hỗ trợ trong [ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html#findDeadlockedThreads()).

Không thấy chu kỳ từ API đó không đủ kết luận ứng dụng đang tiến triển: nó có thể đang chờ I/O, phụ thuộc logic, livelock hoặc mắc ở dạng chờ khác.

## 10. Tự kiểm tra

1. Vì sao lấy tài khoản nguồn trước có thể sai khi chuyển hai chiều? — Nó tạo hai thứ tự khóa đối nghịch.
2. Có `finally` mở khóa thì còn deadlock được không? — Có; luồng có thể mắc trước khi tới `finally`.
3. Vì sao hạng phải bất biến? — Mọi bên phải suy ra cùng thứ tự trong toàn thời gian sử dụng.
4. Fair lock có ngăn chờ vòng giữa hai khóa không? — Không.
5. Đọc từng số dư dưới khóa riêng có tự cho tổng nhất quán trong lúc chuyển không? — Không; ảnh chụp nhiều tài nguyên cần phạm vi bảo vệ phù hợp.
