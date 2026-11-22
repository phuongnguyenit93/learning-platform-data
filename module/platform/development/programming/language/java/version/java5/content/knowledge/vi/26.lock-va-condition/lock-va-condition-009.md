# Nhả khóa khi await và giành lại khóa trước khi tiếp tục

Một luồng đang giữ khóa kiểm tra trạng thái và nhận ra chưa thể làm tiếp: bộ đệm rỗng, cấu hình chưa sẵn sàng hoặc chưa có chỗ cho dữ liệu mới. Nếu nó cứ giữ khóa trong lúc chờ, luồng có khả năng thay đổi trạng thái có thể không vào được vùng bảo vệ.

`Condition.await()` giải quyết điểm này: **đưa luồng vào cơ chế chờ và nhả khóa gắn với condition một cách nguyên tử; trước khi tiếp tục, luồng phải lấy lại khóa**. Với `ReentrantLock`, số lần giữ khóa trước lúc chờ cũng được phục hồi.

## 1. Condition gắn với một khóa cụ thể

```java
ReentrantLock lock = new ReentrantLock();
Condition changed = lock.newCondition();
```

Đoạn khai báo trên cần import hai kiểu trong `java.util.concurrent.locks`. `changed` gắn với chính `lock`, không phải bất kỳ khóa nào có cùng tên biến ở lớp khác.

Với condition do `ReentrantLock` tạo, bên chờ phải sở hữu khóa khi gọi `await`, và bên báo hiệu phải sở hữu khóa khi gọi `signal`/`signalAll`; nếu không, lời gọi ném `IllegalMonitorStateException`. Hợp đồng cụ thể nằm tại [ReentrantLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#newCondition()).

Mẫu cơ bản:

```java
// Đoạn minh họa trong hàm khai báo throws InterruptedException.
lock.lock();
try {
    while (!ready) {
        changed.await();
    }
    useReadyState();
} finally {
    lock.unlock();
}
```

`ready` là điều kiện nghiệp vụ cần kiểm tra, không phải thuộc tính mà đối tượng `Condition` tự lưu hộ. Mọi bên đọc/ghi trạng thái liên quan phải phối hợp qua cùng khóa.

## 2. Một lần await có ba giai đoạn

```text
ĐANG GIỮ KHÓA
  → kiểm tra điều kiện còn sai
  → await: chờ + nhả khóa gắn với condition
ĐANG CHỜ ĐIỀU KIỆN
  → có tín hiệu / ngắt / thức dậy giả
CHỜ LẤY LẠI KHÓA
  → lấy lại khóa thành công
  → kiểm tra lại điều kiện trong while
  → tiếp tục khi điều kiện đúng
```

Tính nguyên tử của bước chuyển sang chờ và nhả khóa giúp tránh một khoảng hở do ứng dụng tự tạo giữa “kiểm tra chưa sẵn sàng” và “đăng ký chờ”, khi bên cập nhật cũng giữ cùng khóa.

Không tự viết:

```java
// Minh họa sai; không thực hiện kiểu tách rời này.
lock.unlock();
changed.await();
lock.lock();
```

Với `ReentrantLock`, đoạn trên gọi `await` khi chưa giữ khóa. Nó cũng bỏ mất giao thức chờ nguyên tử mà API cung cấp.

Không cần `lock.lock()` thêm ngay sau một lần `await()` trả về bình thường. Luồng lúc đó đã sở hữu khóa; lấy thêm làm tăng số lần giữ và có thể gây giữ khóa dư nếu không mở tương ứng.

Quy tắc nhả khóa, các lý do thoát chờ và việc lấy lại khóa được mô tả tại [Condition.await](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/Condition.html#await()).

## 3. signal không chuyển khóa ngay lập tức

Mẫu bên cập nhật:

```java
lock.lock();
try {
    ready = true;
    changed.signal();
    // Luồng này vẫn giữ khóa cho đến finally.
} finally {
    lock.unlock();
}
```

`signal()` làm một bên chờ đủ điều kiện rời cơ chế chờ condition để tiếp tục giao thức lấy lại khóa. Nó không mở khóa của bên báo hiệu và không lập tức chạy đoạn mã sau `await` ở luồng khác.

Vì thế, một luồng được báo hiệu có thể còn chờ lâu nếu bên báo hiệu giữ khóa làm việc tiếp hoặc các bên khác cạnh tranh. Không dùng thời điểm `signal()` như thời điểm bảo đảm bên chờ đã xử lý xong.

Tín hiệu cũng không phải một “giấy phép” được tích lũy trong condition cho mọi bên tới sau. Trạng thái `ready` và phép kiểm tra trong khóa mới quyết định luồng đến sau có cần chờ hay không.

## 4. Chương trình chạy đầy đủ

Lưu thành `AwaitReacquireDemo.java`. Ví dụ cố ý lấy cùng khóa hai lần để thấy `await` nhả đủ quyền giữ và sau đó phục hồi số lần giữ.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class AwaitReacquireDemo {
    static class Gate {
        final ReentrantLock lock = new ReentrantLock();
        final Condition changed = lock.newCondition();
        boolean ready;
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        CountDownLatch enteringWait = new CountDownLatch(1);

        Thread waiter = new Thread(() -> {
            gate.lock.lock();
            try {
                gate.lock.lock(); // Deliberate reentrancy for this experiment.
                try {
                    System.out.println("before await hold count: "
                            + gate.lock.getHoldCount());
                    enteringWait.countDown();
                    while (!gate.ready) {
                        gate.changed.await();
                    }
                    System.out.println("after await hold count: "
                            + gate.lock.getHoldCount());
                    System.out.println("received value: " + gate.value);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    gate.lock.unlock();
                }
            } finally {
                gate.lock.unlock();
            }
        }, "waiter");

        waiter.start();
        enteringWait.await();

        gate.lock.lock();
        try {
            System.out.println("signaller acquired lock: "
                    + gate.lock.isHeldByCurrentThread());
            gate.value = 42;
            gate.ready = true;
            gate.changed.signal();
            System.out.println("signaller still holds after signal: "
                    + gate.lock.isHeldByCurrentThread());
        } finally {
            gate.lock.unlock();
        }

        waiter.join();
        System.out.println("waiter finished: " + !waiter.isAlive());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 AwaitReacquireDemo.java
java AwaitReacquireDemo
```

Stdout khi các luồng được tiến triển bình thường và không có ngắt từ bên ngoài:

```text
before await hold count: 2
signaller acquired lock: true
signaller still holds after signal: true
after await hold count: 2
received value: 42
waiter finished: true
```

### Vì sao thứ tự này có cơ sở?

1. `waiter` in số lần giữ 2 rồi đếm chốt `enteringWait` về 0 trong lúc vẫn giữ khóa.
2. Chốt không khẳng định `waiter` đã ngủ. Nó chỉ bảo đảm `main` không thử lấy khóa trước khi bên chờ đến điểm chuẩn bị. Nếu `main` tới sớm hơn lúc gọi `await`, nó phải đợi khóa.
3. `await()` nhả toàn bộ trạng thái giữ của `ReentrantLock`, nên `main` có thể lấy khóa dù trước đó `waiter` đã lấy hai lần.
4. `main` sửa `value`, đặt `ready`, báo hiệu rồi in trạng thái. Dòng “still holds” xảy ra trước khi `main` mở khóa; `waiter` chưa thể chạy đoạn sau vòng chờ trong lúc này.
5. Khi lấy lại khóa, `waiter` có số lần giữ được phục hồi là 2, đọc `ready` dưới khóa, rồi đọc `value` là 42.
6. Hai `finally` mở đủ hai lần giữ. `main.join()` sau đó chờ bên chờ kết thúc trước khi in dòng cuối.

Tính tái nhập ở đây chỉ là thí nghiệm; mã nghiệp vụ đơn giản thường nên có một phạm vi giữ khóa rõ ràng thay vì cố tình lồng hai lần lấy không cần thiết.

## 5. Vì sao phải kiểm tra lại bằng while?

Có hai lý do độc lập:

- `Condition` cho phép thức dậy giả (spurious wakeup): `await` có thể trở về mà không có tín hiệu nghiệp vụ như ứng dụng mong muốn.
- Sau báo hiệu và trước lúc luồng lấy lại khóa, trạng thái có thể đã bị một luồng khác thay đổi. Chẳng hạn một bên tiêu thụ khác lấy phần tử cuối trước.

Vì vậy, đoạn sau không đủ:

```java
// Minh họa lỗi.
if (!ready) {
    changed.await();
}
useReadyState();
```

Thay `if` bằng `while`. `await()` trả về bình thường chỉ bảo đảm luồng đã lấy lại khóa theo hợp đồng, không bảo đảm điều kiện nghiệp vụ chắc chắn đúng.

Ngay cả dùng `signalAll()` cũng không bỏ được vòng kiểm tra: nhiều bên cùng được báo hiệu nhưng một lần thay đổi trạng thái có thể chỉ cho phép một bên tiếp tục.

## 6. Giành lại khóa và quan hệ bộ nhớ

Bên ghi sửa dữ liệu trong khóa rồi mở khóa. Bên chờ trước khi tiếp tục phải lấy lại cùng khóa, nên có cơ sở đồng bộ hóa để quan sát trạng thái đã được bảo vệ.

Không cần thêm `volatile` vào `ready` hoặc `value` trong chương trình chỉ để bù cho giao thức này, vì mọi truy cập các trường đó đều nằm trong cùng `ReentrantLock`. Ngữ nghĩa đồng bộ hóa bộ nhớ của các thao tác khóa thành công được mô tả tại [Lock — Memory Synchronization](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

Không dựa vào riêng tín hiệu như một lần “gửi biến”. Nếu một bên sửa `ready` ngoài khóa hoặc dùng khóa khác, thiết kế đã phá giao thức bảo vệ trạng thái dù vẫn gọi đúng tên condition.

## 7. Ngắt và hết thời gian chờ

### Khi await bị ngắt

Với condition của `ReentrantLock`, một lần chờ thực sự nhả khóa sẽ giành lại khóa và phục hồi số lần giữ trước khi ngoại lệ ngắt được chuyển tới mã xử lý. Do đó, `finally` bên ngoài vẫn mở khóa theo phạm vi đã lấy.

Nếu cờ ngắt đã có ngay khi vào `await`, API cho phép kiểm tra ngắt trước hoặc sau bước nhả khóa; không nên dựng giao thức phụ thuộc vào việc khóa chắc chắn đã được nhả trong trường hợp này. Lập luận cần bám vào quyền sở hữu hợp lệ của bên gọi và hợp đồng lớp.

Nếu bắt ngoại lệ tại biên `Runnable`, thường khôi phục cờ ngắt rồi kết thúc tác vụ như ví dụ. Không bắt rồi bỏ qua để tiếp tục chờ vô hạn ngoài ý muốn.

### Khi dùng await có thời hạn

Các dạng như `awaitNanos` hoặc `await(time, unit)` cũng cần lấy lại khóa trước khi tiếp tục. Vì vậy, hết ngân sách chờ điều kiện không đồng nghĩa hàm chắc chắn trở về đúng mili giây đó: việc lấy lại khóa và được lập lịch có thể làm thời điểm trở về trễ hơn.

Khi lặp nhiều lần do điều kiện vẫn sai, dùng ngân sách thời gian còn lại thay vì cấp lại toàn bộ timeout. Sau khi lấy lại khóa, quyết định thành công/thất bại dựa vào trạng thái và chính sách thời hạn đã định; một tín hiệu không tự là kết quả nghiệp vụ.

## 8. await chỉ nhả khóa gắn với condition

Điểm nguy hiểm khi giữ thêm một khóa khác:

```text
Luồng A giữ khóa outer và khóa inner.
A gọi condition của inner.await().
A nhả inner nhưng vẫn giữ outer.
Luồng B cần outer để cập nhật trạng thái và báo hiệu.
B không lấy được outer, A không được cập nhật để tiếp tục.
```

`await` không nhả mọi khóa mà luồng tình cờ đang giữ. Số lần giữ tái nhập của **cùng ReentrantLock liên quan** được xử lý theo hợp đồng, nhưng các khóa độc lập khác vẫn thuộc luồng chờ.

Tránh chờ điều kiện trong lúc giữ những khóa mà bên cập nhật cần để tiến triển. Có `try/finally` không tự giải quyết bế tắc nếu chương trình chưa thể thoát khỏi chờ để tới `finally`.

## 9. Các lỗi dễ nhầm

| Lỗi | Hệ quả |
|---|---|
| Gọi `await` khi chưa sở hữu `ReentrantLock` liên quan | Lỗi quyền sở hữu khóa |
| Dùng `synchronized(condition)` rồi gọi `await` | Monitor đó không thay thế khóa tường minh gắn với condition |
| Gọi `condition.wait()`/`notify()` thay cho `await`/`signal` | Trộn hai cơ chế chờ không có quan hệ phối hợp được chỉ định |
| Mở khóa thủ công ngay trước `await` | Phá điều kiện sở hữu và giao thức chờ |
| Lấy thêm khóa ngay sau `await` vì tưởng chưa sở hữu | Tăng số lần giữ ngoài dự kiến |
| Cho rằng `signal` cho luồng chờ chạy ngay | Bỏ qua giai đoạn lấy lại khóa và lập lịch |
| Giữ khóa độc lập khác trong khi chờ | Có thể chặn bên có khả năng làm điều kiện đúng |

## 10. Tự kiểm tra

1. Một luồng đang `await` có giữ `ReentrantLock` liên quan suốt thời gian ngủ không? — Không; khóa được nhả để bên khác tiến triển.
2. `await` trả về bình thường có cần gọi lại `lock.lock()` trước khi đọc trạng thái không? — Không; luồng đã lấy lại khóa.
3. `signal()` có mở khóa của bên báo hiệu không? — Không.
4. Giữ cùng một khóa hai lần rồi await thì sau khi tiếp tục phải mở bao nhiêu lần theo các phạm vi đó? — Hai, vì số lần giữ được phục hồi.
5. Vì sao vẫn cần `while` khi đã dùng khóa công bằng? — Fairness không bảo đảm điều kiện nghiệp vụ đúng và không loại bỏ thức dậy giả.
