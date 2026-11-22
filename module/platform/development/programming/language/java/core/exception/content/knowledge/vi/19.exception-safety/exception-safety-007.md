# Lock.lock kết hợp unlock trong finally — bảo toàn khóa và trạng thái trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một vùng tới hạn dùng <code>Lock</code> phải có đường giải phóng khóa đáng tin cậy cả khi code ném ngoại lệ.
- Viết đúng mẫu <code>lock.lock()</code> → <code>try</code> → <code>finally</code> → <code>lock.unlock()</code>.
- Phân biệt **giải phóng khóa** với **bảo toàn bất biến dữ liệu** khi thao tác cập nhật có thể thất bại.
- Hiểu quyền sở hữu khóa, khả năng khóa lại (reentrancy), và vì sao chỉ luồng giữ khóa mới được gọi <code>unlock()</code>.
- Sử dụng đúng biến thể <code>tryLock()</code>, <code>tryLock(timeout, unit)</code> và <code>lockInterruptibly()</code> khi có nhu cầu.
- Nhận biết lỗi như quên <code>finally</code>, nhả khóa sai luồng, bắt ngoại lệ rồi bỏ qua và làm hỏng trạng thái trước khi nhả khóa.

Phạm vi bài tập trung vào <code>java.util.concurrent.locks.Lock</code> và triển khai thường gặp <code>java.util.concurrent.locks.ReentrantLock</code> trong Java 17+.

## 2. Vấn đề: ngoại lệ xảy ra khi đang giữ khóa

Một vùng tới hạn (*critical section*) chứa thao tác đọc/sửa dữ liệu chia sẻ cần được bảo vệ khỏi các luồng khác đang sử dụng **cùng khóa**. Với <code>ReentrantLock</code>, một luồng gọi <code>lock()</code> để lấy quyền truy cập và phải gọi <code>unlock()</code> đủ số lần để giải phóng quyền đó.

Cách viết thiếu an toàn:

~~~java
lock.lock();
updateSharedState();
lock.unlock();
~~~

Đoạn trên là **mã minh họa**, giả định <code>lock</code> và <code>updateSharedState()</code> đã tồn tại. Nếu <code>updateSharedState()</code> ném <code>RuntimeException</code>, <code>IOException</code> được chuyển tiếp qua một lời gọi liên quan, hoặc code thoát bằng <code>return</code> trước dòng cuối, lời gọi <code>unlock()</code> có thể không bao giờ chạy.

Hệ quả:

- Khóa vẫn bị giữ bởi luồng đã lấy nó.
- Các luồng khác cần cùng khóa có thể phải chờ vô thời hạn hoặc tới khi luồng giữ khóa giải phóng nó ở nơi khác.
- Một thao tác tiếp theo của **chính luồng đó** đôi khi vẫn chạy được do <code>ReentrantLock</code> là khóa có thể lấy lại nhiều lần; điều này dễ che giấu lỗi rò rỉ khóa.
- Nếu thao tác cập nhật dở dang, trạng thái chia sẻ cũng có thể không nhất quán dù sau đó khóa được nhả.

Phương pháp chuẩn của Java:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Khi <code>lock.lock()</code> trả về thành công, luồng đang giữ khóa trước khi vào khối <code>try</code>. Nếu code trong <code>try</code> hoàn thành bình thường, <code>return</code>, hoặc ném ngoại lệ, Java sẽ thực hiện <code>finally</code> khi thoát khối theo ngữ nghĩa thông thường.

**Điểm cốt lõi:** <code>finally</code> bảo vệ **lệnh giải phóng khóa**. Nó không tự hoàn tác những thay đổi dữ liệu đã được thực hiện trong <code>try</code>.

## 3. Cấu trúc chuẩn và thứ tự thực hiện

~~~text
Luồng gọi lock.lock()
          |
          v
  Đợi đến khi giữ được khóa
          |
          v
       vào try
          |
          +---- hoàn tất bình thường ----+
          |                              |
          +---- return/throw -----------+----> finally: lock.unlock()
                                                  |
                                                  v
                                       tiếp tục/return/ném ngoại lệ
~~~

### Vì sao đặt lock.lock() trước try?

Mẫu khuyến nghị:

~~~java
lock.lock();
try {
    // Các thao tác cần giữ khóa.
} finally {
    lock.unlock();
}
~~~

Nhờ vậy <code>finally</code> gắn với phần thực thi **sau khi đã lấy khóa**. Nếu một cách lấy khóa có thể thất bại hoặc ném ngoại lệ **trước khi sở hữu khóa**, code sẽ không đi vào khối <code>try</code>, nên không nhả một khóa mà mình chưa giữ.

Với <code>ReentrantLock.lock()</code>, thao tác bình thường sẽ đợi cho tới khi lấy được khóa; nó không khai báo <code>InterruptedException</code>. Việc ngắt luồng khi đang đợi không có cùng cách xử lý với <code>lockInterruptibly()</code>; không được giả định rằng mọi phương thức lấy khóa đều có cùng hợp đồng.

Trong phương thức <code>tryLock()</code> trả về <code>false</code>, còn rõ hơn: **chưa lấy được khóa thì không được gọi <code>unlock()</code>**.

### Vì sao finally thay vì catch?

Một khối <code>catch</code> chỉ chạy với những loại ngoại lệ nó bắt được. Nếu ta viết:

~~~java
lock.lock();
try {
    updateSharedState();
} catch (IllegalArgumentException e) {
    lock.unlock();
    throw e;
}
lock.unlock();
~~~

thì những loại ngoại lệ khác và một số đường thoát sớm vẫn có thể làm mất lời gọi nhả khóa. Đoạn này là **mã minh họa không độc lập** và cố ý thể hiện cấu trúc dễ sai.

<code>finally</code> giúp tập trung thao tác giải phóng vào đúng một vị trí. Nếu cần <code>catch</code> để bổ sung ngữ cảnh hoặc chuyển ngoại lệ, có thể đặt nó **bên trong cùng khối <code>try</code> hoặc bao quanh vùng khóa**, nhưng vẫn giữ <code>finally</code> làm nơi chịu trách nhiệm nhả khóa.

Trong các sự cố đặc biệt như JVM bị dừng đột ngột hoặc tiến trình bị kết thúc, Java không bảo đảm mọi <code>finally</code> đều được thực thi. Cơ chế này đáp ứng việc quản lý khóa ở đường thực thi Java thông thường, không phải bảo đảm phục hồi hệ thống sau mọi sự cố vật lý.

## 4. Ví dụ Java 17 độc lập: ngoại lệ không làm rò rỉ ReentrantLock

Ví dụ dưới đây kết hợp ba tình huống:

1. Cập nhật số dư hợp lệ.
2. Thao tác bị từ chối bằng ngoại lệ ngay trong vùng khóa; một luồng khác vẫn lấy lại được khóa sau đó.
3. Bốn luồng cùng tăng một bộ đếm; việc nhả khóa nhất quán giúp mọi lần tăng được thực hiện an toàn.

Tạo tệp **LockFinallyDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class LockFinallyDemo {

    static final class Wallet {
        private final ReentrantLock lock = new ReentrantLock();
        private int balance;

        Wallet(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư ban đầu âm");
            }
            balance = initialBalance;
        }

        void deposit(int amount) {
            lock.lock();
            try {
                if (amount <= 0) {
                    throw new IllegalArgumentException("Số tiền phải dương");
                }
                balance = Math.addExact(balance, amount);
            } finally {
                lock.unlock();
            }
        }

        void withdraw(int amount) {
            lock.lock();
            try {
                if (amount <= 0) {
                    throw new IllegalArgumentException("Số tiền phải dương");
                }
                if (amount > balance) {
                    throw new IllegalStateException("Không đủ số dư");
                }
                balance -= amount;
            } finally {
                lock.unlock();
            }
        }

        int balance() {
            lock.lock();
            try {
                return balance;
            } finally {
                lock.unlock();
            }
        }

        // Chỉ phục vụ minh họa/kiểm thử quyền sở hữu khóa.
        boolean probeLock() {
            if (!lock.tryLock()) {
                return false;
            }
            try {
                return true;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int get() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Wallet wallet = new Wallet(100);
        wallet.deposit(50);

        try {
            wallet.withdraw(200);
        } catch (IllegalStateException e) {
            System.out.println("Giao dịch bị từ chối: " + e.getMessage());
        }

        boolean[] probeResult = {false};
        Thread probe = new Thread(
                () -> probeResult[0] = wallet.probeLock());
        probe.start();
        probe.join();

        System.out.println("Luồng khác lấy được khóa: " + probeResult[0]);

        wallet.withdraw(20);
        System.out.println("Số dư cuối: " + wallet.balance());

        Counter counter = new Counter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int n = 0; n < 5_000; n++) {
                    counter.increment();
                }
            });
        }

        for (Thread worker : workers) {
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Tổng số lần tăng: " + counter.get());
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 LockFinallyDemo.java
java LockFinallyDemo
~~~

Stdout:

~~~text
Giao dịch bị từ chối: Không đủ số dư
Luồng khác lấy được khóa: true
Số dư cuối: 130
Tổng số lần tăng: 20000
~~~

### Phân tích kết quả

- Ban đầu ví có 100 đơn vị; nạp thêm 50 thành 150.
- <code>withdraw(200)</code> ném <code>IllegalStateException</code> **trước khi trừ số dư**. Luồng thoát khối <code>try</code>, chạy <code>finally</code> rồi ngoại lệ đi tới <code>catch</code> ở <code>main</code>.
- Phép thử khóa chạy ở **luồng khác**, vì <code>ReentrantLock</code> cho phép **chính luồng đang sở hữu khóa** gọi <code>tryLock()</code> thành công dù nó chưa nhả hết số lần giữ khóa. Kiểm tra lại bằng cùng luồng sẽ không chứng minh đã nhả khóa.
- Chương trình gọi <code>probe.join()</code> trước khi đọc mảng kết quả, nên công việc của luồng kiểm tra đã kết thúc và thay đổi của nó được nhìn thấy sau <code>join()</code>.
- Rút tiếp 20 cho số dư 130. Trong ví dụ này, thao tác sai không làm thay đổi dữ liệu; <code>finally</code> bảo đảm không giữ khóa khi ném lỗi.
- Bốn luồng tăng <code>Counter</code> mỗi luồng 5.000 lần, tạo đúng 20.000 lượt tăng. Các luồng được <code>join()</code> trước khi lấy tổng, nên kết quả không phụ thuộc thứ tự lập lịch.

Trong triển khai thực tế, một phương thức <code>probeLock()</code> chỉ nhằm quan sát khóa thường không nên là một phần của API nghiệp vụ; nó hiện diện ở đây để thể hiện một phép kiểm tra cụ thể.

## 5. finally bảo toàn khóa, nhưng chưa đủ để bảo toàn trạng thái

Giả sử một giỏ hàng lưu hai trường:

- <code>stock</code>: số lượng hàng còn có thể bán.
- <code>reserved</code>: số lượng đã được giữ chỗ.

Một thao tác giữ chỗ phải vừa giảm <code>stock</code> vừa tăng <code>reserved</code>. Nếu code thay đổi trường đầu tiên rồi ném ngoại lệ trước khi thay đổi trường thứ hai, trạng thái có thể trở nên không nhất quán **dù khóa được nhả trong finally**.

Ví dụ thiết kế nguy hiểm:

~~~java
lock.lock();
try {
    stock -= amount;
    callPotentiallyFailingOperation();
    reserved += amount;
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa**, giả định các biến và phương thức tương ứng đã tồn tại. Nếu <code>callPotentiallyFailingOperation()</code> ném lỗi, <code>stock</code> đã bị giảm nhưng <code>reserved</code> chưa tăng. <code>finally</code> chỉ nhả khóa; nó không thể biết cần phục hồi dữ liệu như thế nào.

**Nguyên tắc thiết kế:** bảo vệ hai mục tiêu riêng biệt:

1. **An toàn khóa:** mọi đường thoát sau khi lấy khóa đều nhả khóa đúng cách.
2. **An toàn trạng thái:** mỗi thao tác hoàn tất hoặc thất bại theo quy tắc đã định, không công bố trạng thái vi phạm bất biến.

### Cách ưu tiên: kiểm tra trước, thay đổi sau

Nếu có thể, hãy thực hiện toàn bộ kiểm tra có thể thất bại **trước các phép biến đổi trạng thái** rồi cập nhật các trường bằng thao tác xác định, nhỏ và không gọi code bên ngoài ở giữa.

Ví dụ dưới đây là **đoạn đặt trong một lớp có các trường <code>lock</code>, <code>stock</code>, <code>reserved</code> kiểu phù hợp**:

~~~java
void reserve(int amount) {
    lock.lock();
    try {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (amount > stock) {
            throw new IllegalStateException("Không đủ hàng");
        }
        int newReserved = Math.addExact(reserved, amount);

        stock -= amount;
        reserved = newReserved;
    } finally {
        lock.unlock();
    }
}
~~~

Các phép kiểm tra yêu cầu dương, đủ hàng và tràn số nguyên đều hoàn thành trước khi thay đổi dữ liệu. Sau đó chỉ còn hai phép gán trên biến nguyên thủy, không gọi code tùy ý ở giữa. Nếu dự án có bất biến khác, những bất biến đó cũng phải được kiểm tra.

Nếu cập nhật nhiều đối tượng hoặc thực hiện thao tác I/O, cách “kiểm tra trước” có thể chưa đủ: code bên ngoài vẫn có thể thất bại giữa chuỗi bước. Khi ấy có thể cần chuẩn bị trạng thái mới trong bộ nhớ trước khi công bố, phương án rollback đáng tin cậy, giao dịch cơ sở dữ liệu, hoặc một giao thức nhất quán được thiết kế riêng. Khóa trong bộ nhớ **không tự tạo ra database transaction** và không hoàn tác tác dụng phụ bên ngoài.

### Tình huống Math.addExact trong demo

Dòng:

~~~java
balance = Math.addExact(balance, amount);
~~~

có tính chất hữu ích: nếu tổng vượt phạm vi <code>int</code>, <code>Math.addExact</code> ném <code>ArithmeticException</code> trước khi phép gán cập nhật <code>balance</code>. <code>finally</code> vẫn nhả khóa, còn số dư giữ nguyên. Điều này tốt hơn phép cộng <code>int</code> không kiểm tra tràn trong một miền giá trị yêu cầu số dư hợp lệ.

## 6. Bốn nguyên tắc khi thao tác với ReentrantLock

### 6.1. Mỗi lần lấy khóa thành công phải có lần nhả tương ứng

<code>ReentrantLock</code> là khóa **reentrant**: cùng một luồng có thể gọi <code>lock()</code> nhiều lần mà không tự khóa chết. Mỗi lần lấy khóa thành công làm tăng số lần giữ khóa (*hold count*). Mỗi lần <code>unlock()</code> tương ứng làm giảm số lần đó; quyền sở hữu thực sự được giải phóng khi số lần giữ trở về 0.

Ví dụ đoạn minh họa trong một phương thức:

~~~java
lock.lock();       // Hold count: 1
try {
    lock.lock();   // Hold count: 2
    try {
        doWork();
    } finally {
        lock.unlock(); // Hold count: 1
    }
} finally {
    lock.unlock();     // Hold count: 0
}
~~~

Giả định <code>doWork()</code> và <code>lock</code> tồn tại. Nếu quên một <code>unlock()</code>, luồng vẫn giữ khóa, dù đã chạy một khối <code>finally</code>. Trong code thực tế, việc lồng lấy cùng khóa không cần thiết nên được hạn chế để dễ review.

### 6.2. Chỉ luồng sở hữu khóa mới được unlock

Với <code>ReentrantLock</code>, gọi <code>unlock()</code> từ luồng không sở hữu khóa sẽ ném <code>IllegalMonitorStateException</code>. Một luồng khác không thể “dọn dẹp giúp” khóa mà mình không nắm giữ. Do đó, hãy đặt <code>unlock()</code> trong <code>finally</code> của **chính luồng và chính luồng điều khiển đã lấy khóa**.

Không chia tách “thread A lấy khóa; thread B nhả khóa” khi dùng <code>ReentrantLock</code>. Nếu cần điều phối công việc giữa luồng, hãy thiết kế cơ chế đồng bộ phù hợp với yêu cầu đó, thay vì vi phạm quyền sở hữu khóa.

### 6.3. Mọi truy cập trạng thái chia sẻ cần tuân thủ cùng giao thức khóa

Khóa chỉ có tác dụng đồng bộ hóa những thao tác tham gia cùng giao thức. Ví dụ, <code>Counter.increment()</code> có khóa nhưng một chỗ khác lại đọc thẳng trường <code>value</code> không được bảo vệ thì người đọc không được hưởng cùng bảo đảm quan sát nhất quán.

Với <code>Lock</code> cùng đối tượng khóa, việc <code>unlock()</code> và lần <code>lock()</code> thành công sau đó có quan hệ đồng bộ hóa giúp bảo đảm nhìn thấy các thay đổi bộ nhớ được công bố dưới khóa. Muốn đọc/ghi nhất quán, phải giữ quy ước đó ở **mọi lối truy cập** tới dữ liệu cần bảo vệ.

### 6.4. Không giữ khóa lâu hơn cần thiết

Nếu vùng khóa thực hiện network I/O, ghi tệp chậm, chờ người dùng hoặc gọi callback không kiểm soát được, các luồng khác sẽ phải đợi lâu. Vì vậy, nên rút gọn vùng khóa quanh thao tác cần bảo vệ, nhưng chỉ chuyển công việc ra ngoài sau khi xem xét bất biến và thứ tự cần thiết.

Không được tùy tiện chuyển phép kiểm tra và cập nhật sang hai vùng khóa khác nhau:

~~~java
lock.lock();
try {
    if (balance < amount) {
        throw new IllegalStateException("Không đủ số dư");
    }
} finally {
    lock.unlock();
}

// Luồng khác có thể thay đổi balance ở khoảng trống này.

lock.lock();
try {
    balance -= amount;
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa không độc lập**. Nó tạo lỗi *check-then-act*: hai đoạn riêng lẻ có khóa nhưng toàn bộ thao tác không còn nguyên tử. Kiểm tra điều kiện và cập nhật phụ thuộc điều kiện thường phải thuộc cùng một lần giữ khóa.

## 7. Khi không chắc có lấy được khóa: tryLock

Phương thức <code>tryLock()</code> trên <code>Lock</code> trả về <code>true</code> nếu lời gọi lấy được khóa ngay tại thời điểm đó, hoặc <code>false</code> nếu không lấy được theo hợp đồng của cách triển khai. Với <code>ReentrantLock</code>, cùng luồng đang giữ khóa vẫn có thể gọi <code>tryLock()</code> thành công nhờ reentrancy.

Mẫu an toàn:

~~~java
boolean acquired = lock.tryLock();
if (!acquired) {
    return false;
}
try {
    updateSharedState();
    return true;
} finally {
    lock.unlock();
}
~~~

Đoạn này là **mã minh họa nằm trong một phương thức trả <code>boolean</code>**. Nhánh <code>false</code> thoát trước khi vào <code>try</code>, vì nó chưa sở hữu khóa. Nếu thành công, <code>finally</code> sẽ nhả khóa ngay cả khi <code>updateSharedState()</code> ném ngoại lệ hoặc code <code>return</code>.

Đừng viết:

~~~java
try {
    if (lock.tryLock()) {
        updateSharedState();
    }
} finally {
    lock.unlock();
}
~~~

Đây là **mã cố ý sai**: nếu <code>tryLock()</code> trả <code>false</code>, <code>finally</code> vẫn gọi <code>unlock()</code> khi luồng chưa sở hữu khóa và <code>ReentrantLock</code> có thể ném <code>IllegalMonitorStateException</code>.

Trong mã thực tế, biến tên <code>acquired</code> giúp review chính xác điều kiện nhả khóa, nhất là khi có nhiều đường thoát.

## 8. Chờ khóa có thể hủy: lockInterruptibly và tryLock có thời hạn

### 8.1. lockInterruptibly()

<code>lockInterruptibly()</code> cho phép luồng đang chờ khóa đáp ứng tín hiệu ngắt theo hợp đồng <code>Lock</code> và khai báo <code>throws InterruptedException</code>. Cấu trúc chuẩn khi phương thức cho phép chuyển tiếp ngoại lệ:

~~~java
void update() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateSharedState();
    } finally {
        lock.unlock();
    }
}
~~~

Đoạn minh họa giả định <code>lock</code> và <code>updateSharedState()</code> đã tồn tại. Nếu luồng bị ngắt **trước khi lấy khóa**, <code>lockInterruptibly()</code> có thể ném <code>InterruptedException</code> và code không đi vào <code>try</code>: không gọi <code>unlock()</code>. Nếu đã lấy khóa và exception phát sinh **bên trong <code>try</code>**, <code>finally</code> sẽ nhả khóa theo đường thực thi thông thường.

Nếu không thể khai báo <code>throws InterruptedException</code> và buộc phải đổi sang unchecked exception, code xử lý thường cần khôi phục cờ ngắt bằng <code>Thread.currentThread().interrupt()</code>, đồng thời chuyển tiếp ngoại lệ gốc thành cause. Tuy nhiên cách xử lý cụ thể còn phụ thuộc hợp đồng của tác vụ.

### 8.2. tryLock(timeout, unit)

Một phương thức chờ tối đa trong một khoảng thời gian có thể viết:

~~~java
boolean acquired = lock.tryLock(200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    return false;
}
try {
    updateSharedState();
    return true;
} finally {
    lock.unlock();
}
~~~

Đoạn này là **mã minh họa thuộc phương thức trả <code>boolean</code> và khai báo hoặc xử lý <code>InterruptedException</code>**. Không được quên:

- Trả <code>false</code> vì hết thời gian hoặc không lấy được khóa có nghĩa là **không nhả khóa**.
- Phương thức có thể ném <code>InterruptedException</code> khi đang chờ; khi đó chưa có quyền sở hữu khóa từ lời gọi này.
- Chỉ sau khi <code>acquired == true</code> mới đi vào khối có <code>finally</code> tương ứng.

Nếu <code>tryLock</code> từ một luồng đã giữ <code>ReentrantLock</code> trước đó, số lần giữ khóa có thể tăng; lời gọi <code>unlock()</code> trong phương thức này chỉ nhả phần mà lời gọi hiện tại đã lấy, không giải phóng mọi lần giữ từ các ngữ cảnh bên ngoài.

## 9. return, break và exception trong try

Java chạy <code>finally</code> trước khi hoàn tất một đường thoát khỏi khối <code>try</code> do <code>return</code>, <code>break</code>, <code>continue</code> hoặc ngoại lệ theo quy tắc bình thường. Bởi vậy có thể trả kết quả ngay trong vùng khóa:

~~~java
int readBalance() {
    lock.lock();
    try {
        return balance;
    } finally {
        lock.unlock();
    }
}
~~~

Mã minh họa trong lớp có <code>lock</code> và <code>balance</code>. Biểu thức <code>return balance</code> được đánh giá trước khi phương thức thực sự thoát; khối <code>finally</code> nhả khóa trước khi người gọi nhận kết quả.

Tuy nhiên, **không viết <code>return</code> hoặc ném ngoại lệ mới vô cớ bên trong <code>finally</code>**. Một lời gọi <code>return</code> trong <code>finally</code> có thể thay thế giá trị trả về hoặc che mất ngoại lệ của <code>try</code>.

Ví dụ sai:

~~~java
lock.lock();
try {
    return readData();
} finally {
    lock.unlock();
    return null;
}
~~~

Đây là mã minh họa trong một phương thức trả về kiểu tham chiếu. <code>return null</code> của <code>finally</code> có thể che khuất kết quả hoặc ngoại lệ của <code>readData()</code>. <code>finally</code> nên dành cho thao tác giải phóng bắt buộc, không thay đổi cách phương thức báo cáo kết quả.

### Ngoại lệ từ unlock() thì sao?

<code>ReentrantLock.unlock()</code> có thể ném <code>IllegalMonitorStateException</code> nếu gọi khi luồng không sở hữu khóa. Nếu <code>finally</code> ném một ngoại lệ mới, ngoại lệ đó có thể **che mất** ngoại lệ đang được ném từ <code>try</code>. Với mẫu đúng, mỗi lần lấy khóa thành công chỉ được nhả một lần bởi chính luồng sở hữu, nên lỗi này không phải đường xử lý thường lệ.

Đừng thêm <code>catch (Exception ignored)</code> quanh <code>unlock()</code> chỉ để che một lỗi quản lý quyền sở hữu. Cần sửa nguyên nhân nhả khóa sai, vì nó phản ánh sự cố logic đồng bộ hóa.

## 10. Ngoại lệ trong vùng khóa: nên xử lý ở đâu?

Mẫu dưới đây vừa giữ giải phóng khóa vừa cho lỗi có ý nghĩa lan truyền:

~~~java
lock.lock();
try {
    validateRequest();
    changeState();
} finally {
    lock.unlock();
}
~~~

Đây là **đoạn mã minh họa** có sẵn <code>lock</code>, <code>validateRequest()</code> và <code>changeState()</code>.

Nếu tầng API cần chuyển một ngoại lệ kỹ thuật thành ngoại lệ phù hợp hơn, có thể bắt và chuyển đổi nhưng vẫn giữ nguyên tắc nhả khóa:

~~~java
lock.lock();
try {
    return dataStore.load();
} catch (java.io.IOException original) {
    throw new DataAccessException("Không thể tải dữ liệu", original);
} finally {
    lock.unlock();
}
~~~

Đây là **mã minh họa** trong phương thức trả về kiểu phù hợp; giả định <code>dataStore.load()</code> khai báo <code>IOException</code> và có constructor <code>DataAccessException(String, Throwable)</code>. <code>finally</code> vẫn chạy trước khi ngoại lệ mới thoát ra. Truyền <code>original</code> làm cause giúp giữ được dấu vết I/O để chẩn đoán.

Về thiết kế, nếu thao tác I/O có thể chạy lâu, cân nhắc liệu thật sự cần giữ khóa xuyên suốt lần gọi đó không. Có thể tách bước chuẩn bị và công bố kết quả để giảm thời gian giữ khóa, với điều kiện vẫn bảo toàn thứ tự và bất biến dữ liệu.

### Có nên nuốt ngoại lệ?

Không nên viết một khối <code>catch</code> rỗng rồi nhả khóa như thể thao tác đã thành công. Nếu đã khôi phục hoàn toàn lỗi theo hợp đồng, ứng dụng có thể tiếp tục; nếu chưa, cần báo lỗi thích hợp. Cũng không nên biến mọi lỗi thành một giá trị thành công giả (<code>0</code>, <code>null</code>, chuỗi rỗng) nếu API không công bố cách biểu đạt lỗi đó.

## 11. Khi cần nhiều khóa: finally vẫn chưa phòng được deadlock

Giả sử giao dịch giữa hai tài khoản cần lấy khóa của cả hai. Nếu luồng A lấy khóa tài khoản X trước rồi chờ Y, trong khi luồng B lấy khóa Y trước rồi chờ X, hệ thống có thể deadlock.

Ngay cả khi cả hai luồng đều viết:

~~~java
first.lock();
try {
    second.lock();
    try {
        transfer();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
~~~

đoạn minh họa này **vẫn có thể deadlock** nếu các luồng lấy cùng hai khóa theo thứ tự khác nhau. <code>finally</code> chỉ thực thi khi chương trình rời khỏi các khối đang chạy; nó không giúp một luồng thoát khỏi lời gọi <code>second.lock()</code> đang chờ vô thời hạn.

Hướng thiết kế phổ biến:

- Định nghĩa thứ tự lấy khóa cố định và nhất quán cho mọi luồng.
- Giảm số khóa cần giữ đồng thời khi có thể.
- Xem xét <code>tryLock</code> có giới hạn và cách hoàn trả khóa đã lấy nếu không lấy được khóa tiếp theo.
- Không tự cho rằng tăng thời gian chờ hoặc thêm <code>finally</code> là đủ để giải quyết deadlock.

**Không được tự nhả khóa đang do luồng khác sở hữu** để “gỡ deadlock”; quyền sở hữu của <code>ReentrantLock</code> không cho phép cách làm đó.

## 12. Condition.await() và việc tạm nhả khóa

<code>Condition</code> thường được tạo từ <code>ReentrantLock.newCondition()</code>. Các phương thức chờ như <code>await()</code> có cơ chế đặc biệt: khi chờ, luồng **tạm nhả khóa gắn với condition** và khi kết thúc chờ theo hợp đồng, nó **lấy lại khóa trước khi trở về hoặc báo <code>InterruptedException</code>**.

Một mẫu điển hình:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyData();
} finally {
    lock.unlock();
}
~~~

Đây là đoạn **minh họa** trong phương thức khai báo/xử lý <code>InterruptedException</code>, với <code>lock</code>, <code>condition</code>, <code>ready</code> và <code>consumeReadyData()</code> đã được xác định. Vòng <code>while</code> cần thiết vì điều kiện có thể không còn đúng sau khi tỉnh, và <code>await()</code> có thể thức dậy dù không có tín hiệu tương ứng.

Nguyên tắc <code>finally</code> vẫn áp dụng: sau khi <code>lock.lock()</code> thành công, luồng kết thúc đoạn xử lý bằng <code>unlock()</code> đúng cách. Việc <code>await()</code> tạm nhả/lấy lại khóa là một phần hợp đồng của <code>Condition</code>, không có nghĩa người dùng được gọi <code>unlock()</code> tùy ý ngay sau <code>await()</code>.

Không gọi <code>await()</code> hoặc <code>signal()</code> của condition trên một <code>ReentrantLock</code> khi chưa giữ khóa tương ứng; với triển khai này, điều đó dẫn tới <code>IllegalMonitorStateException</code>.

## 13. So sánh synchronized và Lock

Java cũng có cú pháp:

~~~java
synchronized (monitor) {
    updateSharedState();
}
~~~

Mã minh họa trên dùng monitor object đã khai báo. Khi luồng rời khỏi khối <code>synchronized</code>, JVM tự giải phóng monitor theo ngữ nghĩa ngôn ngữ, kể cả khi khối ném ngoại lệ. Với <code>Lock</code>, việc nhả khóa là **trách nhiệm tường minh của lập trình viên**, vì đó là API phương thức.

| Khía cạnh | <code>synchronized</code> | <code>ReentrantLock</code> |
| --- | --- | --- |
| Vào vùng khóa | <code>synchronized (monitor)</code> | <code>lock.lock()</code> |
| Ra khỏi vùng khóa | JVM tự nhả monitor khi thoát khối | Phải gọi <code>unlock()</code>, thường trong <code>finally</code> |
| Thử lấy khóa ngay | Không có API tương đương trực tiếp như <code>tryLock()</code> | Có <code>tryLock()</code> |
| Chờ có thể ngắt khi lấy khóa | Không có thao tác monitor-enter tương đương <code>lockInterruptibly()</code> | Có <code>lockInterruptibly()</code> |
| Condition | <code>wait/notify/notifyAll</code> gắn monitor | <code>Condition</code> do lock tạo |

Không phải cứ dùng <code>ReentrantLock</code> là tốt hơn <code>synchronized</code>. Nếu chỉ cần bảo vệ một vùng ngắn và không cần các tính năng lấy khóa linh hoạt, <code>synchronized</code> có thể đơn giản hơn. Khi đã chọn <code>Lock</code>, quy tắc <code>try/finally</code> là phần bắt buộc của thiết kế an toàn.

## 14. Kiểm thử bảo đảm giải phóng khóa

Kiểm thử nên đánh giá **đường thoát qua ngoại lệ**, không chỉ đường thành công.

| Tình huống kiểm thử | Kỳ vọng |
| --- | --- |
| Vùng tới hạn hoàn thành bình thường | Khóa được nhả |
| Kiểm tra đầu vào trong vùng khóa ném ngoại lệ | Ngoại lệ vẫn được báo và khóa được nhả |
| Code ném <code>ArithmeticException</code> trước phép gán | Dữ liệu chưa bị thay đổi, khóa được nhả |
| Có <code>return</code> bên trong <code>try</code> | Giá trị được trả đúng và khóa được nhả |
| <code>tryLock()</code> trả <code>false</code> | Không được gọi <code>unlock()</code> |
| <code>lockInterruptibly()</code> bị ngắt trước khi sở hữu khóa | Ngoại lệ ngắt được truyền/xử lý, không nhả khóa chưa sở hữu |
| Nhiều luồng cùng thay đổi dữ liệu | Kết quả và bất biến được giữ dưới cùng giao thức khóa |

Để kiểm tra lỗi rò rỉ trên <code>ReentrantLock</code>, nên kiểm tra từ **một luồng khác**. Nếu chỉ gọi lại <code>lock()</code> trên cùng luồng, cơ chế reentrancy có thể khiến kiểm thử tưởng khóa đã được nhả dù số lần giữ khóa còn dương.

Trong các bài kiểm thử có concurrency, tránh để một lỗi khóa khiến test treo vô thời hạn. Có thể sử dụng giới hạn thời gian, <code>tryLock(timeout, unit)</code>, hoặc cơ chế đồng bộ trong test để chỉ tiếp tục khi trạng thái đã được thiết lập. Đừng khẳng định tính đúng đắn dựa trên một lần chạy “không bị kẹt”; kiểm thử nên kiểm tra bất biến, kết quả và đường ngoại lệ có chủ đích.

Đối với lớp có nhiều trường chia sẻ, thêm kiểm thử rằng sau mỗi lỗi dự kiến, trạng thái vẫn hợp lệ. Một phép kiểm tra “khóa đã nhả” không đủ chứng minh dữ liệu còn nhất quán.

## 15. Các lỗi thường gặp khi review

1. **Đặt <code>unlock()</code> sau khối thao tác mà không có <code>finally</code>:** lỗi, <code>return</code> hoặc đường thoát sớm có thể bỏ qua nó.
2. **Nhả khóa dù chưa lấy được:** thường gặp với <code>tryLock()</code> hoặc <code>lockInterruptibly()</code> khi đặt sai ranh giới <code>try</code>.
3. **Gọi <code>unlock()</code> hai lần cho một lần lấy khóa:** có thể dẫn đến <code>IllegalMonitorStateException</code> hoặc làm thay đổi hold count không đúng.
4. **Nhả khóa ở luồng khác:** trái hợp đồng quyền sở hữu của <code>ReentrantLock</code>.
5. **Bọc toàn bộ <code>finally</code> bằng catch rỗng:** che giấu lỗi quản lý khóa và làm khó chẩn đoán.
6. **Cho rằng finally tự rollback:** khóa được nhả nhưng trạng thái có thể đã bị cập nhật một phần.
7. **Kiểm tra rồi cập nhật trong hai vùng khóa khác nhau:** tạo khoảng trống cho luồng khác thay đổi dữ liệu.
8. **Quên khóa khi đọc:** giá trị đọc có thể không đồng bộ với những thao tác ghi được bảo vệ bằng khóa.
9. **Gọi công việc chậm hoặc callback không kiểm soát trong vùng khóa:** kéo dài thời gian chờ và tăng nguy cơ deadlock.
10. **Dùng nhiều khóa với thứ tự khác nhau:** <code>finally</code> không sửa được deadlock do đợi khóa kế tiếp.
11. **Dùng <code>return</code> trong finally:** có thể che mất kết quả hoặc ngoại lệ của vùng tới hạn.
12. **Kiểm tra nhả khóa từ cùng luồng:** reentrancy khiến <code>tryLock()</code> vẫn có thể thành công dù khóa bị giữ lại.
13. **Bắt và nuốt tất cả ngoại lệ:** dễ tiếp tục với trạng thái không hợp lệ, mặc dù đã nhả khóa.
14. **Bỏ qua ngắt khi chờ khóa:** khiến cơ chế hủy thao tác khó hoạt động như mong đợi.

## 16. Checklist áp dụng

Trước khi hoàn tất một phương thức có <code>Lock</code>, hãy tự trả lời:

- Phương thức đã lấy khóa **thành công** trước khi vào <code>try</code> chưa?
- Có đúng một đường <code>finally</code> nhả lần lấy khóa đó trong cùng luồng không?
- Với <code>tryLock()</code> và <code>lockInterruptibly()</code>, các đường không lấy được khóa có tránh <code>unlock()</code> không?
- Khi code ném ngoại lệ, người gọi có nhận được lỗi thích hợp, và khóa đã được nhả chưa?
- Khi lỗi xảy ra giữa cập nhật, dữ liệu có còn thỏa mãn bất biến không? Cần chuẩn bị trước, rollback hay transaction không?
- Mọi luồng đọc/ghi dữ liệu chia sẻ có sử dụng cùng giao thức khóa không?
- Có gọi network, I/O hoặc callback lâu trong vùng khóa mà không cần thiết không?
- Nếu có nhiều khóa, thứ tự lấy khóa giữa các luồng có nhất quán không?
- Kiểm thử đã mô phỏng exception và xác nhận **một luồng khác** vẫn lấy khóa được chưa?

**Kết luận:** Mẫu <code>lock.lock()</code> đặt trước <code>try</code> và <code>lock.unlock()</code> trong <code>finally</code> là cách quản lý <code>Lock</code> căn bản để tránh giữ khóa sau đường lỗi. Để thật sự **bảo toàn trạng thái**, còn cần bảo vệ bất biến, cập nhật dữ liệu theo một quy tắc nhất quán và xử lý ngoại lệ đúng hợp đồng.