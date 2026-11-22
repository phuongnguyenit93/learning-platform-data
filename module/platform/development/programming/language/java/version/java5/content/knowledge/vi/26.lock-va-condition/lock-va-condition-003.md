# Khóa và mở khóa an toàn với try, finally

`ReentrantLock` cho phép một luồng bảo vệ vùng truy cập trạng thái dùng chung. Khác với một khối `synchronized`, khóa tường minh không tự được mở chỉ vì chương trình đi ra khỏi dấu ngoặc của một phương thức.

Nếu nhánh `return` hoặc một ngoại lệ làm bỏ qua `unlock()`, luồng khác có thể chờ mãi để truy cập tài nguyên. Mẫu `lock` → `try` → `finally` giải quyết trách nhiệm trả lại khóa trên các đường thoát thông thường của Java.

## 1. Mẫu chuẩn và vị trí từng câu lệnh

```java
lock.lock();
try {
    // Đọc hoặc cập nhật trạng thái được bảo vệ.
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa giả định đã có biến `lock`. Ba điểm cần giữ:

1. Lấy khóa trước khi bắt đầu `try` bảo vệ vùng đã sở hữu khóa.
2. Đặt `try` ngay sau khi lấy khóa thành công, không chèn mã có thể lỗi vào khoảng giữa.
3. Đặt `unlock()` ở đầu `finally`, trước các việc dọn dẹp khác có thể ném ngoại lệ.

Đây là mẫu được khuyến nghị trong [Lock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html) và [ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

`finally` chạy khi điều khiển thoát khỏi `try` theo cơ chế bình thường của ngôn ngữ: hết khối, `return`, ngoại lệ, hoặc một lệnh chuyển điều khiển như `break`/`continue` rời khỏi phạm vi đó. Quy tắc chi tiết nằm trong [JLS 14.20.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.2).

Không diễn giải thành bảo đảm trong mọi tình huống vật lý: tiến trình bị chấm dứt, máy mất điện hoặc mã không bao giờ thoát khỏi `try` không được sửa chỉ bằng cách có `finally`.

## 2. Vì sao đặt unlock sau phần xử lý là sai?

```java
// Minh họa lỗi.
lock.lock();
updateSharedState();
lock.unlock();
```

Nếu `updateSharedState()` ném ngoại lệ, dòng mở khóa không được thực hiện. Đối tượng khóa vẫn ghi nhận luồng hiện tại đang sở hữu nó; việc luồng kết thúc không phải cơ chế mở khóa tự động của `ReentrantLock`.

Chỉ đưa `unlock()` vào `catch` cũng chưa bao phủ đủ đường đi:

```java
// Minh họa lỗi: chỉ mở khóa trong một loại lỗi.
lock.lock();
try {
    updateSharedState();
} catch (IllegalArgumentException e) {
    lock.unlock();
    throw e;
}
```

Nhánh thành công không mở khóa, và ngoại lệ loại khác cũng không đi qua nhánh này. `catch` dùng để xử lý hoặc chuyển tiếp lỗi; `finally` dùng để bảo đảm phần dọn dẹp phù hợp với việc đã lấy khóa.

## 3. Chương trình chạy đầy đủ

Lưu thành `LockFinallyDemo.java`. Lớp `Stock` giữ số lượng tồn kho cùng một khóa riêng. Cả đường mua thành công và mua thất bại đều trả khóa.

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class LockFinallyDemo {
    static class Stock {
        private final ReentrantLock lock = new ReentrantLock();
        private int remaining = 10;

        int buy(int amount) {
            lock.lock();
            try {
                if (amount <= 0) {
                    throw new IllegalArgumentException("amount must be positive");
                }
                if (amount > remaining) {
                    throw new IllegalStateException("insufficient stock");
                }
                remaining -= amount;
                return remaining;
            } finally {
                lock.unlock();
            }
        }

        Integer tryReadRemaining() {
            if (!lock.tryLock()) {
                return null;
            }
            try {
                return remaining;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Stock stock = new Stock();
        System.out.println("after purchase: " + stock.buy(4));

        try {
            stock.buy(100);
        } catch (IllegalStateException e) {
            System.out.println("failed purchase: " + e.getMessage());
        }

        AtomicReference<Integer> observed = new AtomicReference<>();
        Thread observer = new Thread(
                () -> observed.set(stock.tryReadRemaining()), "observer");
        observer.start();
        observer.join();

        System.out.println("other thread acquired lock: "
                + (observed.get() != null));
        System.out.println("remaining: " + observed.get());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 LockFinallyDemo.java
java LockFinallyDemo
```

Stdout:

```text
after purchase: 6
failed purchase: insufficient stock
other thread acquired lock: true
remaining: 6
```

Phân tích:

- `buy(4)` giảm 10 thành 6 rồi `return`. Trước khi bên gọi nhận giá trị trả về, `finally` mở khóa.
- `buy(100)` ném ngoại lệ trong vùng khóa. `finally` vẫn mở khóa trước khi ngoại lệ đi tới `catch` của bên gọi.
- Kiểm tra khả năng mua xảy ra trước khi giảm tồn kho, nên lần thất bại không làm thay đổi số lượng 6.
- Luồng `observer` khác luồng mua và không có bên cạnh tranh khóa lúc nó chạy. `tryLock()` thành công, chứng minh khóa đã được trả qua cả đường return lẫn đường lỗi.

Việc kiểm tra bằng **luồng khác** là có chủ đích. Nếu quên mở một khóa tái nhập mà chỉ gọi lại `lock()` trên cùng luồng, lời gọi có thể vẫn thành công và làm người kiểm tra tưởng khóa đã được trả.

`AtomicReference` là nơi chuyển kết quả quan sát về `main`; sau `join()`, luồng quan sát đã hoàn tất. Phần quan trọng của việc bảo vệ tồn kho vẫn là mọi lần đọc/ghi `remaining` đều tuân thủ cùng khóa.

## 4. Chỉ mở khóa nếu lần lấy khóa đã thành công

### lockInterruptibly

Khi muốn việc chờ khóa có thể bị hủy bằng ngắt, đặt lời gọi lấy khóa ngoài `try` mở khóa:

```java
// Đoạn minh họa trong hàm khai báo throws InterruptedException.
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Nếu `lockInterruptibly()` ném `InterruptedException` trước khi lấy được khóa, luồng chưa sở hữu khóa và không đi vào `try`/`finally` này. Bên gọi xử lý tín hiệu hủy theo chính sách ứng dụng.

Không dùng mẫu sai sau:

```java
// Minh họa lỗi: finally có thể chạy dù chưa lấy được khóa.
try {
    lock.lockInterruptibly();
    updateSharedState();
} finally {
    lock.unlock();
}
```

Với `ReentrantLock`, `unlock()` khi luồng hiện tại không sở hữu khóa ném `IllegalMonitorStateException`, có thể che mất ngoại lệ ngắt ban đầu.

### tryLock

Với phép thử, nhánh mở khóa chỉ áp dụng khi kết quả là `true`:

```java
if (!lock.tryLock()) {
    return; // Chưa lấy khóa; chọn chính sách từ chối hoặc thử lại sau.
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

`tryLock(timeout, unit)` cũng cần cùng cấu trúc khi trả `true`, đồng thời xử lý `InterruptedException` nếu bị ngắt khi chờ. Không mở khóa trên nhánh `false` hoặc nhánh lấy khóa ném ngoại lệ.

Không dùng `if (lock.isLocked()) lock.unlock()` để thay cho quyền sở hữu: `isLocked()` chỉ nói có luồng nào đang giữ khóa, không chứng minh đó là luồng hiện tại. Cấu trúc chương trình nên ghi rõ việc lấy khóa của chính nó đã thành công.

## 5. Mỗi lần lấy thêm cần một lần mở tương ứng

`ReentrantLock` có tính tái nhập: luồng đang giữ khóa có thể lấy lại chính khóa đó, làm tăng số lần giữ. Khóa chỉ thực sự được trả cho luồng khác khi số lần giữ giảm về 0.

Ví dụ minh họa hai vùng có phạm vi riêng:

```java
lock.lock();
try {
    firstChange();
    lock.lock();
    try {
        secondChange();
    } finally {
        lock.unlock();
    }
} finally {
    lock.unlock();
}
```

Không mở “cho chắc” thêm một lần: mở thừa khi không còn quyền sở hữu là lỗi. Cũng không dùng vòng lặp mở toàn bộ số lần giữ trong một hàm con, vì nó có thể làm mất vùng bảo vệ mà bên gọi vẫn đang dựa vào.

Với nhiều khóa khác nhau, lồng `try/finally` theo từng lần lấy thành công để một lần lấy sau thất bại vẫn trả được các khóa đã lấy trước. Thường mở theo thứ tự ngược lại thứ tự lấy. Ngoài dọn dẹp, các đường chạy vẫn cần thống nhất thứ tự lấy khóa để tránh bế tắc; `finally` không ngăn hai luồng chờ nhau khi chưa luồng nào thoát được vùng giữ khóa.

## 6. Mở khóa không đồng nghĩa hoàn tác trạng thái

`finally` bảo đảm trả khóa, không tự khôi phục các phép ghi đã thực hiện.

```java
// Minh họa vấn đề tính nhất quán nghiệp vụ.
lock.lock();
try {
    available -= amount;
    validateOtherCondition(); // Có thể ném ngoại lệ.
} finally {
    lock.unlock();
}
```

Nếu điều kiện lỗi sau phép giảm, `available` vẫn đã đổi. Bên tiếp theo có thể lấy khóa rồi quan sát trạng thái này. Cần thiết kế thứ tự kiểm tra/tính toán/cập nhật để giữ bất biến, hoặc có cơ chế khôi phục rõ ràng nếu phải thay đổi trước.

Ví dụ `Stock` kiểm tra điều kiện trước khi cập nhật nên nhánh lỗi thông thường không làm giảm tồn kho. Với một nghiệp vụ phức tạp, có thể tính trạng thái mới trong biến cục bộ rồi chỉ công bố khi các điều kiện đã thỏa; nếu liên quan giao dịch cơ sở dữ liệu, khóa JVM không thay thế giao dịch đó.

## 7. finally nên ngắn và không che lỗi

Không `return` từ `finally` để “kết thúc cho gọn”: nó có thể thay kết quả hoặc nuốt ngoại lệ từ phần `try`. Không ném một ngoại lệ khác không cần thiết từ `finally` vì có thể che nguyên nhân gốc.

Ví dụ dọn dẹp sai vị trí:

```java
// Minh họa lỗi nếu writeAuditLog có thể ném ngoại lệ.
finally {
    writeAuditLog();
    lock.unlock();
}
```

Nếu ghi log thất bại trước dòng mở khóa, khóa bị giữ lại. Trả khóa trước; việc ghi log bên ngoài vùng khóa cần dùng dữ liệu đã chụp trong vùng bảo vệ nếu phải phản ánh trạng thái cụ thể.

Bản thân `unlock()` ném lỗi quyền sở hữu là dấu hiệu giao thức lấy/mở khóa sai, không nên bị bắt rồi bỏ qua để che lỗi. Giữ mẫu lấy thành công → một `finally` tương ứng giúp tránh nguyên nhân này.

`Lock` và `ReentrantLock` chuẩn không triển khai `AutoCloseable`, nên không thể tự đặt chúng vào `try-with-resources` rồi mong Java mở khóa. Có thể tự xây một đối tượng quản lý phạm vi trong thiết kế riêng, nhưng nó có thêm hợp đồng sở hữu và đóng; mẫu `try/finally` trực tiếp thường rõ ràng cho nhu cầu cơ bản.

## 8. Cùng một khóa phải bảo vệ mọi đường truy cập

Một hàm ghi dùng khóa chưa đủ nếu một hàm đọc khác trả trực tiếp trường thông thường mà không tuân thủ giao thức. Việc lấy/mở khóa thành công có ngữ nghĩa bộ nhớ tương ứng với monitor; hiệu lực đồng bộ hóa liên quan tới cùng khóa và những lần sử dụng đúng hợp đồng.

Cũng không thay `lock.lock()` bằng `synchronized(lock)` ở một nơi khác rồi coi là cùng cơ chế. Monitor của đối tượng `lock` và trạng thái khóa tường minh không có quan hệ phối hợp được chỉ định như vậy. Dùng nhất quán một giao thức cho cùng bất biến.

Giữ khóa trong phạm vi cần bảo vệ trạng thái. Tránh trả về một tham chiếu có thể thay đổi mà bên ngoài sẽ sửa tự do sau khi khóa đã mở, vì điều đó tạo một đường truy cập ngoài vùng bảo vệ.

## 9. Tự kiểm tra

1. `return` bên trong `try` có bỏ qua `finally` không? — Không; phần dọn dẹp được thực hiện trước khi việc trả về hoàn tất, theo quy tắc ngôn ngữ.
2. `tryLock()` trả `false` có cần `unlock()` không? — Không; lần gọi chưa lấy khóa.
3. Vì sao lấy khóa trong `try` rồi luôn mở ở `finally` có thể sai với `lockInterruptibly`? — Việc lấy khóa có thể ném ngoại lệ trước khi có quyền sở hữu.
4. Khóa được mở khi xử lý lỗi có nghĩa dữ liệu đã hoàn tác không? — Không.
5. Cùng luồng lấy lại `ReentrantLock` có chứng minh lần giữ trước đã được trả không? — Không; đó có thể chỉ là lấy tái nhập thêm một lần.
