# Điều kiện sở hữu monitor và `IllegalMonitorStateException` trong Java

## 1. Mục tiêu và ngữ cảnh

Khi phối hợp các luồng bằng `synchronized`, `wait()`, `notify()` và `notifyAll()`, câu hỏi quan trọng nhất là: **luồng đang thực thi có sở hữu đúng monitor của đối tượng nhận lệnh hay không?** Nếu không, các thao tác chờ hoặc phát tín hiệu của `Object` ném `IllegalMonitorStateException`. Bài học này giải thích điều kiện sở hữu, cách nhận diện sai monitor và cách viết đoạn chờ/thông báo an toàn.

Sau bài học, bạn có thể:
- Xác định monitor đang được khóa bởi `synchronized` dạng khối, phương thức instance và phương thức static.
- Giải thích vì sao `obj.wait()`, `obj.notify()`, `obj.notifyAll()` yêu cầu **chính luồng hiện tại** sở hữu monitor của `obj`.
- Phân biệt việc **giải phóng monitor khi `wait`** với việc **chỉ đánh thức luồng khi `notify`**.
- Chẩn đoán `IllegalMonitorStateException` và sửa lỗi mà không vô tình thay đổi đối tượng dùng làm khóa.

## 2. Monitor ownership là gì?

Mỗi đối tượng Java thông thường có một *intrinsic lock* (monitor) dùng cho đồng bộ bằng `synchronized`. Tại một thời điểm, một monitor chỉ có tối đa một luồng sở hữu; cùng một luồng có thể vào lại (*reentrant*) monitor đó nhiều lần.

Một luồng T sở hữu monitor của đối tượng `lock` trong các tình huống sau:

| Cú pháp đang chạy | Monitor mà luồng sở hữu |
| --- | --- |
| `synchronized (lock) { ... }` | Chính đối tượng `lock` |
| `synchronized void method() { ... }` trong đối tượng `x` | Chính `x` (tức `this` của lời gọi) |
| `static synchronized void method() { ... }` của `Example` | Đối tượng `Example.class` |

Ví dụ, `synchronized (a)` không làm luồng sở hữu monitor của `b`, kể cả nếu `a.equals(b)` là `true`. Điều quan trọng là **cùng một tham chiếu đối tượng thực tế** (identity), không phải cùng giá trị theo `equals()`.

`Thread.holdsLock(lock)` cho biết **luồng hiện tại** có đang giữ intrinsic lock của `lock` hay không; phương thức này hữu ích khi kiểm tra/debug. Không sử dụng kết quả kiểm tra như cách thay cho việc khóa thật, và đừng nhầm với việc hỏi luồng khác đang giữ khóa nào.

Khi ra khỏi khối/phương thức `synchronized`, kể cả do ngoại lệ, JVM tự nhả mức sở hữu monitor tương ứng. Nhờ tính *reentrant*, cùng luồng có thể khóa lại chính monitor đó trong lời gọi lồng nhau.

## 3. Hợp đồng sở hữu của `Object.wait/notify/notifyAll`

Ba thao tác này đều được gọi trên **đối tượng đích**, nên monitor cần giữ cũng thuộc **đối tượng đích**:

| Thao tác | Yêu cầu lúc gọi | Tác động chính |
| --- | --- | --- |
| `lock.wait()` / `wait(timeout)` | Luồng hiện tại giữ monitor của `lock` | Vào tập chờ của `lock`; tạm nhả monitor của `lock`, rồi giành lại trước khi tiếp tục |
| `lock.notify()` | Luồng hiện tại giữ monitor của `lock` | Chọn một luồng đang chờ trên `lock` để đánh thức; không nhả monitor ngay |
| `lock.notifyAll()` | Luồng hiện tại giữ monitor của `lock` | Đánh thức tất cả luồng đang chờ trên `lock`; không nhả monitor ngay |

Thiếu quyền sở hữu đúng monitor khi gọi một trong ba thao tác sẽ ném `java.lang.IllegalMonitorStateException`. Đây là `RuntimeException` (*unchecked*), nên không bắt buộc khai báo `throws`. Nó phản ánh lỗi sử dụng cơ chế đồng bộ, không phải tín hiệu bình thường của một hàng đợi đang trống.

Phân biệt các trường hợp khác:
- `wait` khai báo `InterruptedException` khi luồng bị ngắt trước hoặc trong lúc đợi; đây là ngoại lệ *checked*. Sau khi giành lại monitor, lệnh chờ mới kết thúc bằng ngoại lệ này.
- `wait(long timeoutMillis)` với thời gian âm ném `IllegalArgumentException`; `wait(0)` có nghĩa chờ không giới hạn thời gian chờ, không phải chờ 0 mili giây rồi quay lại.
- `notify` không yêu cầu đang tồn tại luồng chờ; gọi hợp lệ khi không có người chờ chỉ không đánh thức ai.

### Sai: đồng bộ trên đối tượng khác

```java
Object gate = new Object();
Object unrelated = new Object();

synchronized (unrelated) {
    gate.notifyAll(); // IllegalMonitorStateException: chưa giữ monitor của gate
}
```

**Đúng:** dùng cùng đối tượng cho khóa và lời gọi:

```java
Object gate = new Object();

synchronized (gate) {
    gate.notifyAll(); // Hợp lệ, dù lúc này có thể không có luồng chờ
}
```

Tương tự, ở phương thức instance `synchronized`, `this.wait()` hợp lệ trong thời gian giữ monitor của `this`; nhưng `other.wait()` vẫn sai nếu chưa giữ monitor của `other`. Một phương thức `static synchronized` khóa `TenLop.class`, không khóa một instance cụ thể.

## 4. Chương trình Java 17+ chạy được: đúng và sai monitor

Tạo tệp `MonitorOwnershipDemo.java`:

```java
public class MonitorOwnershipDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        System.out.println("outside=" + Thread.holdsLock(lock));

        try {
            lock.wait(1);
        } catch (IllegalMonitorStateException expected) {
            System.out.println("wait: IllegalMonitorStateException");
        }

        try {
            lock.notify();
        } catch (IllegalMonitorStateException expected) {
            System.out.println("notify: IllegalMonitorStateException");
        }

        try {
            lock.notifyAll();
        } catch (IllegalMonitorStateException expected) {
            System.out.println("notifyAll: IllegalMonitorStateException");
        }

        synchronized (lock) {
            System.out.println("inside=" + Thread.holdsLock(lock));

            lock.notifyAll(); // Hợp lệ dù không có ai đang chờ
            lock.wait(1);     // Tạm nhả lock; quay lại sau timeout hoặc thức sớm

            System.out.println("afterWait=" + Thread.holdsLock(lock));
        }

        System.out.println("afterBlock=" + Thread.holdsLock(lock));
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac MonitorOwnershipDemo.java
java MonitorOwnershipDemo
```

Kết quả chuẩn:

```text
outside=false
wait: IllegalMonitorStateException
notify: IllegalMonitorStateException
notifyAll: IllegalMonitorStateException
inside=true
afterWait=true
afterBlock=false
```

Giải thích:
1. Trước khối `synchronized`, luồng `main` chưa sở hữu monitor của `lock`; ba lời gọi phải ném ngoại lệ.
2. Khi vào `synchronized (lock)`, `Thread.holdsLock(lock)` là `true`.
3. `lock.wait(1)` có thể kết thúc do hết hạn hoặc thức sớm (*spurious wakeup*), nhưng luôn giành lại monitor của `lock` trước khi trả về bình thường. Vì thế `afterWait=true`.
4. Khi thoát khối, monitor đã được nhả, nên `afterBlock=false`. Thời gian chờ chính xác không phải một phần của kết quả cần kiểm chứng.

## 5. `wait()` nhả khóa nào? `notifyAll()` làm gì?

Xét tiến trình hai luồng cùng phối hợp qua đối tượng `gate`:

1. Luồng A vào `synchronized (gate)`, thấy điều kiện chưa thỏa rồi gọi `gate.wait()`.
2. A đi vào *wait set* gắn với `gate` và **nhả toàn bộ các mức giữ monitor của `gate`**. Nếu A còn giữ monitor của đối tượng khác, các monitor khác không tự được nhả.
3. Luồng B có thể vào `synchronized (gate)`, cập nhật trạng thái dùng chung và gọi `gate.notifyAll()`.
4. Các luồng đã được thông báo chuyển sang cạnh tranh giành monitor của `gate`; B vẫn giữ monitor tới khi thoát phần `synchronized`.
5. A chỉ tiếp tục thực thi sau khi giành lại `gate`, rồi **kiểm tra lại điều kiện**.

Do đó, một lời gọi `notify()` **không chuyển quyền sở hữu monitor ngay lập tức** sang luồng được đánh thức. `notify()` cũng không bảo đảm chọn luồng nào trong tập chờ; `notifyAll()` đánh thức mọi luồng chờ, nhưng chúng vẫn phải lần lượt giành khóa.

Không được đồng nhất `wait` với `Thread.sleep`: `sleep` không tự nhả monitor đang giữ. Nếu ngủ trong `synchronized` để chờ luồng khác sửa điều kiện cùng monitor, bạn có thể tự ngăn tiến triển.

## 6. Khóa đúng là điều kiện cần, nhưng chưa đủ

Đoạn kiểm chứng ở mục 4 chứng minh luồng có hoặc không có quyền sở hữu monitor. Trong chương trình thực tế, **quyền gọi `wait/notify` hợp lệ chưa tự bảo đảm giao thức phối hợp đúng**. Có thể giữ đúng `lock` nhưng đọc điều kiện bằng một khóa khác, không kiểm tra điều kiện sau khi tỉnh dậy, hoặc thông báo trước khi cập nhật trạng thái.

Để kiểm tra hai lớp điều kiện riêng biệt, xét bảng sau:

| Câu hỏi | Quy tắc cần xác minh |
| --- | --- |
| Có quyền gọi `lock.wait()`/ `lock.notifyAll()`? | Chính thread hiện tại đang giữ monitor của `lock`, có thể kiểm tra bằng `Thread.holdsLock(lock)` khi debug. |
| Dữ liệu điều kiện có an toàn? | Mọi lần đọc và ghi predicate chia sẻ tuân theo cùng `lock`. |
| Có bỏ lỡ thay đổi? | Kiểm tra predicate trước khi chờ và lặp lại sau mỗi lần `wait()` trở về, ngay trong `synchronized (lock)`. |
| Có đánh thức đúng nhóm cần xử lý? | Thay đổi trạng thái trước khi báo; ưu tiên `notifyAll()` nếu nhiều loại điều kiện chờ, rồi để mỗi waiter tự kiểm tra predicate. |
| Có xử lý ngắt? | Truyền `InterruptedException` hoặc khôi phục cờ ngắt và kết thúc hợp lý nếu không thể truyền lên. |

Ví dụ producer–consumer đầy đủ với vòng `while` nằm ở bài **“Dùng vòng `while` kiểm tra điều kiện trước và sau khi chờ”**. Ở đây, trọng tâm chẩn đoán là **receiver của `wait/notify` có thực sự là đối tượng đang được đồng bộ hay không**; hai đối tượng khác nhau vẫn có monitor khác nhau ngay cả khi `equals()` trả về `true`.

## 7. Chẩn đoán lỗi trong mã thật

Khi thấy stack trace tại `Object.wait`, `Object.notify` hoặc `Object.notifyAll` cùng `IllegalMonitorStateException`, kiểm tra theo thứ tự:

1. **Xác định receiver của lời gọi**: ví dụ `queueLock.wait()` cần monitor của `queueLock`, không phải mặc nhiên `this` hoặc `Thread.currentThread()`.
2. **Tìm vùng khóa đang bao quanh lời gọi**: có đúng `synchronized (queueLock)` hoặc phương thức `synchronized` trên chính receiver đó không?
3. **Kiểm tra identity**: có vô tình tạo `new Object()` cho mỗi lần gọi, thay biến khóa, khóa bản sao, hoặc dùng hai object `equals` nhau nhưng khác reference không?
4. **Xác định thread thực thi**: một thread sở hữu monitor không cấp quyền cho thread khác gọi `wait/notify` thay nó.
5. **Sau khi sửa quyền sở hữu**, rà lại điều kiện `while`, cập nhật dữ liệu và `notifyAll` dưới một monitor, tránh race condition hoặc lost notification.

Một vài bẫy tiêu biểu:

| Mẫu sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `lock.wait()` ngoài `synchronized(lock)` | Không sở hữu `lock` | Đặt thao tác và kiểm tra điều kiện trong `synchronized(lock)` |
| `synchronized(this) { lock.notify(); }` với `lock != this` | Đang sở hữu monitor khác | Đồng bộ trên `lock` |
| `synchronized(a) { b.wait(); }` dù `a.equals(b)` | Monitor dựa trên identity | Dùng chính `b` làm khóa |
| Chuyển `wait` sang `sleep` để “tránh exception” | `sleep` không nhả monitor, có thể kẹt luồng | Dùng `wait` dưới monitor đúng, hoặc chọn công cụ điều phối phù hợp |
| `if (!ready) lock.wait()` | Không xử lý thức dậy giả / trạng thái đổi | `while (!ready) lock.wait()` |
| Chỉ `notify()` khi nhiều loại điều kiện cùng đợi | Có thể đánh thức luồng không thể tiến triển | Cân nhắc `notifyAll()` và kiểm tra lại điều kiện |

### Ranh giới với `java.util.concurrent.locks`

`ReentrantLock`/`Condition` có quy tắc sở hữu riêng: `Condition.await()`/`signal()` cần giữ đúng `ReentrantLock` gắn với condition. Giữ `ReentrantLock` **không** tự đồng nghĩa với sở hữu intrinsic monitor của một `Object` để gọi `wait/notify`. Đừng trộn hai giao thức khóa trên cùng một điều kiện trạng thái.

## 8. Tự kiểm tra

1. Trong `synchronized (a) { b.notifyAll(); }`, điều gì quyết định lời gọi có hợp lệ? **Đáp án:** luồng hiện tại phải đồng thời giữ monitor của `b`; chỉ giữ `a` không đủ nếu `a` và `b` khác đối tượng.
2. `static synchronized` của `Demo` khóa đối tượng nào? **Đáp án:** `Demo.class`.
3. Luồng vừa được `notify` có chạy ngay không? **Đáp án:** không; trước tiên phải giành lại monitor sau khi chủ hiện tại nhả.
4. Tại sao `wait()` phải đặt trong `while`? **Đáp án:** trạng thái cần kiểm tra lại sau thức dậy giả, cạnh tranh giành khóa hoặc thay đổi từ luồng khác.
5. `IllegalMonitorStateException` có phải `InterruptedException` không? **Đáp án:** không; lỗi thứ nhất là vi phạm sở hữu monitor, lỗi thứ hai báo chờ bị ngắt.

**Ghi nhớ:** `synchronized (x)` trao quyền sở hữu monitor **của chính `x` cho luồng đang chạy**. Khi gọi `x.wait()`, `x.notify()` hay `x.notifyAll()`, phải đang giữ chính monitor đó; sau thức dậy, luôn kiểm tra lại điều kiện của trạng thái chung.

## Tài liệu tham khảo

- [Java SE 21 — `Object` (`wait`, `notify`, `notifyAll`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html).
- [Java SE 21 — `IllegalMonitorStateException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalMonitorStateException.html).
- [Java SE 21 — `Thread.holdsLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)).