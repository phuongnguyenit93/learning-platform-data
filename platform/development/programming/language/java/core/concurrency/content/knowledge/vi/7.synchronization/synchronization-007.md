# Lock ordering để ngăn deadlock trong Java

## 1. Khi hai thread cần giữ nhiều khóa

Một thao tác đồng thời đôi khi phải cập nhật **nhiều đối tượng như một đơn vị nhất quán**: chuyển tiền giữa hai tài khoản, chuyển phần tử giữa hai cấu trúc, đổi chủ sở hữu một tài nguyên hoặc cập nhật hai thành phần có quan hệ với nhau. Để bảo vệ bất biến, code có thể phải giữ hai khóa cùng lúc.

Nhưng nếu các thread lấy khóa theo những thứ tự khác nhau, một thread có thể giữ khóa A và chờ B, trong khi thread khác giữ B và chờ A. Cả hai đều chờ tài nguyên do bên kia giữ; **deadlock (bế tắc)** xuất hiện và không thread nào tự tiến triển.

**Lock ordering** là quy tắc mọi đường code phải lấy nhiều khóa theo **cùng một thứ tự toàn cục ổn định**. Khi thứ tự được áp dụng nhất quán, những quan hệ chờ khóa đi một chiều theo thứ tự đó, loại bỏ kiểu vòng chờ phát sinh chỉ từ các khóa trong giao thức này.

Bài này tập trung vào **Synchronization và concurrency của Java nói chung**: intrinsic monitor qua `synchronized`, `ReentrantLock`, quy tắc thứ tự, giới hạn và cách chẩn đoán. Không cần framework để áp dụng.

### Kết quả cần đạt

Sau bài, bạn có thể:

1. Nhận diện vòng chờ trong wait-for graph và giải thích vì sao hai vùng khóa riêng lẻ vẫn có thể deadlock.
2. Định nghĩa thứ tự toàn cục trên các tài nguyên, kể cả tình huống hai caller truyền tham số đảo chiều.
3. Tạo ví dụ Java 17+ lấy khóa theo thứ tự cố định và giữ bất biến nhiều đối tượng.
4. Hiểu điều kiện để chứng minh lock ordering phòng tránh deadlock, giới hạn của `tryLock`/timeout và những bẫy với callback, khóa ẩn, lock khác loại.
5. Quan sát thread dump, trạng thái `BLOCKED` và kết quả `ThreadMXBean.findDeadlockedThreads()` để điều tra bế tắc monitor/ownable synchronizer.

## 2. Deadlock và wait-for graph

### 2.1. Hai đường đi đảo thứ tự khóa

Xét hai khóa A và B.

**Thread 1**:

~~~java
// MINH HỌA nguy cơ; lockA và lockB đã khai báo.
synchronized (lockA) {
    synchronized (lockB) {
        doWork();
    }
}
~~~

**Thread 2**:

~~~java
// MINH HỌA nguy cơ; cùng hai khóa ở trên nhưng ngược thứ tự.
synchronized (lockB) {
    synchronized (lockA) {
        doOtherWork();
    }
}
~~~

Nếu thread 1 lấy A, thread 2 lấy B, rồi mỗi bên yêu cầu khóa còn lại, chúng chờ nhau vô hạn nếu không có cơ chế can thiệp từ ngoài. `synchronized` không có timeout khi chờ lấy monitor; `Thread.interrupt()` đơn thuần không phá được luồng đang `BLOCKED` chờ vào một monitor.

Sơ đồ chờ:

~~~text
Thread 1 giữ A ---> cần B ---> B đang do Thread 2 giữ
      ^                               |
      |                               v
      +----------- Thread 2 cần A <---+
~~~

Đây là **vòng chờ tài nguyên**. Việc A và B được bảo vệ bởi hai `synchronized` riêng không sai; điều nguy hiểm là **thứ tự lồng khóa không thống nhất**.

### 2.2. Bốn điều kiện Coffman

Một deadlock kiểu tài nguyên khóa thường liên quan đồng thời bốn điều kiện:

| Điều kiện | Ý nghĩa trong bài toán khóa |
| --- | --- |
| Mutual exclusion | Một khóa chỉ cho một chủ sở hữu tại thời điểm tương ứng |
| Hold and wait | Thread đang giữ khóa này nhưng tiếp tục chờ khóa khác |
| No preemption | Không tự ý lấy lại khóa đang thuộc một thread khác |
| Circular wait | Tồn tại vòng A chờ B, B chờ C, …, Z chờ A |

Lock ordering chủ yếu **phá điều kiện circular wait** bằng cách quy định hướng lấy khóa. Nó không yêu cầu xóa mutual exclusion hoặc giảm bảo vệ bất biến. Nhưng lập luận chỉ đúng nếu **mọi đường đi tham gia cùng hệ khóa** tuân thủ thứ tự và các phụ thuộc/khóa ẩn khác cũng đã được xem xét.

Deadlock khác với **starvation** (một thread luôn bị thiệt khi cạnh tranh), **livelock** (thread liên tục đổi trạng thái mà không tạo tiến triển) và **blocking dài** do I/O. Một ứng dụng treo không mặc nhiên đồng nghĩa có chu trình deadlock.

## 3. Nguyên tắc lock ordering: đặt một thứ tự tổng

Giả sử mỗi tài nguyên có một khóa riêng. Gán mỗi tài nguyên một **thứ hạng duy nhất, ổn định**; ví dụ account 100 có thứ hạng nhỏ hơn account 200. Với hai khóa, code phải luôn:

1. Xác định khóa nào có thứ hạng thấp hơn.
2. Lấy khóa thấp trước.
3. Lấy khóa cao sau.
4. Thực hiện thao tác cần bảo vệ.
5. Thoát vùng khóa theo cơ chế tương ứng.

Ngay cả khi lời gọi là `transfer(from=A,to=B)` hoặc `transfer(from=B,to=A)`, thứ tự lấy khóa **không dựa vào hướng nghiệp vụ**; nó vẫn là A rồi B nếu A có thứ hạng thấp hơn.

### Vì sao quy tắc này ngăn vòng chờ?

Giả sử tất cả thread chỉ được giữ khóa có thứ hạng thấp khi chờ khóa có thứ hạng cao hơn. Khi có chuỗi chờ, thứ hạng các khóa đang được chờ phải tăng dần. Một vòng chờ sẽ đòi hỏi thứ hạng tăng mãi rồi quay về khóa đầu tiên nhỏ hơn, mâu thuẫn với thứ tự tăng nghiêm ngặt. Vậy không thể tạo chu trình **giữa các khóa cùng tuân thủ giao thức đó**.

Điều kiện thiết yếu:

- Mỗi tài nguyên khác nhau phải có thứ hạng **phân biệt**; trường hợp bằng nhau phải có quy tắc phá hòa rõ ràng.
- Thứ hạng **không đổi khi tài nguyên đang hoạt động**.
- **Mọi code lấy hai khóa** đều dùng cùng quy tắc, kể cả đọc snapshot nhiều đối tượng.
- Nếu đang giữ một khóa ở bậc cao, không gọi tiếp phương thức lấy khóa bậc thấp.
- Callback, listener, logging phức tạp hoặc gọi code ngoài phạm vi có thể lấy thêm khóa; cần tính cả khóa được lấy **gián tiếp**.

Đây là một nguyên tắc thiết kế áp dụng cho mọi đường đi của chương trình, không phải vài dòng code chỉ trong một phương thức.

## 4. Ví dụ chạy được — chuyển dữ liệu theo thứ tự khóa ổn định (Java 17+)

Giả sử hai tài khoản trong bộ nhớ có `balance`; chuyển giữa chúng cần nguyên tử xét trên **cả hai tài khoản**. Mỗi account có một monitor **riêng tư** và thứ hạng được cấp phát khi tạo.

Tạo tệp `OrderedTransferDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public class OrderedTransferDemo {
    static final class Account {
        private static final AtomicLong NEXT_ID = new AtomicLong();
        private final long lockOrderId = NEXT_ID.getAndIncrement();
        private final Object lock = new Object();
        private int balance;

        Account(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Negative balance");
            }
            balance = initialBalance;
        }

        int balance() {
            synchronized (lock) {
                return balance;
            }
        }
    }

    static void transfer(Account from, Account to, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (from == to) {
            return;
        }

        Account first = from.lockOrderId < to.lockOrderId ? from : to;
        Account second = first == from ? to : from;

        synchronized (first.lock) {
            synchronized (second.lock) {
                if (from.balance < amount) {
                    throw new IllegalArgumentException("Insufficient funds");
                }
                from.balance -= amount;
                to.balance += amount;
            }
        }
    }

    static int total(Account a, Account b) {
        if (a == b) {
            return a.balance();
        }

        Account first = a.lockOrderId < b.lockOrderId ? a : b;
        Account second = first == a ? b : a;

        synchronized (first.lock) {
            synchronized (second.lock) {
                return a.balance + b.balance;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Account a = new Account(100);
        Account b = new Account(100);

        Thread one = new Thread(
            () -> transfer(a, b, 10), "transfer-a-to-b"
        );
        Thread two = new Thread(
            () -> transfer(b, a, 20), "transfer-b-to-a"
        );

        one.start();
        two.start();
        one.join();
        two.join();

        System.out.println(
            "A=" + a.balance() + ", B=" + b.balance()
        );
        System.out.println("total=" + total(a, b));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OrderedTransferDemo.java
java OrderedTransferDemo
~~~

Stdout khi cả hai chuyển khoản hoàn thành bình thường:

~~~text
A=110, B=90
total=200
~~~

**Giải thích kết quả:**

- Tài khoản A bắt đầu 100, gửi 10 và nhận 20, nên cuối cùng 110. B nhận 10 rồi gửi 20, nên cuối cùng 90. Cả hai giao dịch đều hợp lệ bất kể thứ tự thread nào lấy khóa trước.
- `AtomicLong` cấp thứ hạng riêng cho từng `Account` trong ví dụ. Khóa dùng để bảo vệ `balance` là `private final Object lock`, nên caller không thể vô tình `synchronized` trên một monitor công khai.
- Cả `transfer` lẫn `total` đều xếp thứ tự khóa theo `lockOrderId` và lấy `first.lock` trước `second.lock`. Vì vậy không có đường gọi nào đảo A/B chỉ vì đổi chiều chuyển khoản.
- Hai cập nhật `from.balance -= amount` và `to.balance += amount` xảy ra khi giữ cả hai monitor; một thao tác đọc tổng hợp cũng giữ đúng hai monitor nên không nhìn thấy trạng thái chuyển dở.
- `balance()` cũng lấy monitor tương ứng. Trong ví dụ, hai lần đọc riêng lẻ chỉ chạy **sau `join()`**, khi không còn chuyển khoản đang hoạt động. Nếu muốn đọc đồng thời **cả hai số dư như một snapshot**, phải dùng một phương thức lấy cả hai khóa theo thứ tự như `total` hoặc trả về một immutable snapshot chứa cả hai trường.
- `Thread.join()` chờ mỗi thread kết thúc, nhưng bản thân `join()` không làm lại một giao dịch thất bại và không tự báo lỗi của thread. Trong sản phẩm thực, cần có cơ chế nhận kết quả/exception của task thay vì chỉ tin rằng thread đã dừng là thành công.

**Phạm vi ví dụ:** Code quản lý hai object nằm trong một tiến trình JVM. Nó minh họa khóa bộ nhớ Java; không thay thế transaction hoặc đồng bộ liên tiến trình cho dữ liệu ở database hay dịch vụ khác. Với trường hợp thực tế có thể tạo số lượng tài khoản đủ để thứ hạng `long` tràn vòng, phải dùng cơ chế cấp ID không trùng hoặc xử lý tràn; ví dụ giả định ID chưa tràn.

### Điều gì xảy ra khi thử viết theo chiều chuyển khoản?

Thiết kế nguy hiểm thường viết:

~~~java
// Minh họa sai, không phải chương trình độc lập.
synchronized (from.lock) {
    synchronized (to.lock) {
        moveBalance(from, to, amount);
    }
}
~~~

Nếu một caller chuyển A → B và caller khác chuyển B → A, chúng lấy khóa theo thứ tự ngược nhau. Vì thế khóa phải được sắp theo **thứ tự tài nguyên**, không theo vai trò `from`/`to`.

## 5. Chọn khóa và thứ hạng như thế nào?

### 5.1. Dùng khóa riêng thay vì khóa dễ bị code ngoài nắm giữ

Một đối tượng công khai hoặc `String` được chia sẻ rộng có thể vô tình bị thành phần khác dùng làm monitor. Khi đó phương thức của bạn không biết những khóa nào đã được giữ trước khi nó chạy.

Ưu tiên:

~~~java
// Minh họa trong một class; không phải chương trình độc lập.
private final Object lock = new Object();

void update() {
    synchronized (lock) {
        // Bảo vệ trạng thái nội bộ.
    }
}
~~~

Không dùng `synchronized(this)` theo thói quen nếu instance được trao cho nhiều thành phần và bạn không kiểm soát các chỗ có thể khóa nó. Một khóa `private final` giúp thể hiện ownership. Nhưng một class dùng nhiều khóa riêng vẫn phải xác định quan hệ thứ tự giữa chúng nếu có các phương thức giữ hơn một khóa.

### 5.2. Chọn rank bất biến và có thứ tự toàn phần

Một ID nghiệp vụ **duy nhất và bất biến** là lựa chọn tốt nếu hợp đồng bảo đảm nó thực sự duy nhất. Nếu ID có thể thay đổi, lấy khóa dựa vào ID động sẽ khiến hai thread dùng hai thứ tự khác nhau.

Có thể cấp riêng một rank lúc xây dựng object. Với nhiều cấp độ khóa, hãy định nghĩa thứ tự chung, ví dụ:

~~~text
Lock level 10: cấu hình toàn cục
Lock level 20: session
Lock level 30: tài nguyên con
Lock level 40: cache cục bộ
~~~

Nếu giữ khóa cấp 30 rồi gọi code cần khóa cấp 10, đường gọi đó vi phạm giao thức. Không cần lúc nào cũng giữ cả bốn khóa; quy tắc chỉ áp dụng khi nhiều khóa được giữ đồng thời.

### 5.3. Cẩn trọng với `hashCode()` và `System.identityHashCode()`

Không nên tự động sắp khóa theo `object.hashCode()`:

- `hashCode()` có thể do class override, có thể dựa trên trạng thái mutable hoặc không duy nhất.
- `System.identityHashCode(object)` ổn định theo identity trong vòng đời object nhưng **có thể va chạm** giữa hai object khác nhau.
- Nếu hai thread xử lý cặp A/B có identity hash bằng nhau rồi “giữ nguyên thứ tự đầu vào”, chúng vẫn có thể đảo khóa và deadlock.

Nếu thiết kế dựa trên identity hash, cần một **tie lock** chung dùng trong trường hợp va chạm, hoặc tốt hơn dùng rank phân biệt được cấp một cách có kiểm soát. Không giả định hai hash code luôn khác nhau.

### 5.4. Nếu hai tham số trỏ cùng một đối tượng?

Đối tượng khóa monitor Java có tính **reentrant**: cùng thread có thể `synchronized` cùng một monitor nhiều lần mà không tự deadlock. Nhưng thiết kế vẫn nên xử lý `from == to` rõ ràng, vì đó có thể là giao dịch vô nghĩa hoặc cần hành vi nghiệp vụ riêng.

Với `ReentrantLock`, cùng thread cũng có thể acquire lại một lock mình đang sở hữu; phải release đúng số lần acquire. Với **khóa không reentrant** hoặc primitive khác, lấy lại cùng khóa có thể tự bế tắc. Vì vậy quy tắc xếp khóa nên xử lý tham số trùng và loại primitive đang sử dụng.

## 6. Với ba khóa trở lên: thứ tự phải nhất quán toàn hệ

Giả sử có A, B, C được xếp A < B < C. Những đường đi hợp lệ khi cần nhiều khóa sẽ đi theo chiều tăng, ví dụ A → C hoặc A → B → C. Một đường đi C → A có thể tạo vòng với đường khác và phải được sửa.

### Ví dụ ba thread có vòng chờ

~~~text
Thread 1: giữ A, chờ B
Thread 2: giữ B, chờ C
Thread 3: giữ C, chờ A

Wait-for graph:
  T1 --> T2 --> T3 --> T1
~~~

Chỉ nhìn từng phương thức riêng có thể không thấy vòng. Nó có thể hình thành qua lời gọi lồng nhau hoặc giữa các module có cùng tài nguyên chia sẻ.

Nếu một code path cần lấy nhiều lock, hãy tập hợp các lock, loại bỏ phần tử trùng theo identity và **sắp theo thứ hạng chung** trước khi acquire. Khi dùng `Lock`, release tất cả khóa đã lấy trong `finally`, theo thứ tự ngược lại cho dễ kiểm chứng.

**Đừng chỉ sắp theo dữ liệu “hiện tại”** nếu khóa liên quan có thể được thay thế hoặc rank thay đổi trong lúc thực thi. Thứ hạng dùng để xếp phải bền vững và các caller phải chia sẻ cùng định nghĩa.

### Bảng review thứ tự khóa

| Đường code | Khóa lấy lần lượt | Đạt quy tắc A < B < C? |
| --- | --- | --- |
| Xử lý A rồi B | A → B | Có |
| Đọc snapshot A và C | A → C | Có |
| Kiểm tra B rồi C | B → C | Có |
| Cập nhật C rồi gọi hàm dùng A | C → A | **Không** |
| Lấy A rồi B rồi C | A → B → C | Có |
| Gọi callback khi giữ C và callback lấy B | C → B | **Không** |

Việc lập bản đồ những đường gọi như vậy thường phát hiện được rủi ro bị che giấu bởi helper method hoặc callback.

## 7. `synchronized` và `ReentrantLock` trong lock ordering

### 7.1. Intrinsic monitor

`synchronized` có ưu điểm tự release monitor khi thoát block, kể cả khi có exception. Nhược điểm khi debug deadlock là yêu cầu vào monitor không có timeout hoặc cơ chế `lockInterruptibly`; một thread bị `BLOCKED` đợi monitor không thể chỉ dùng interrupt để kết thúc ngay việc chờ lock.

Thứ tự toàn cục là cách phòng tránh thực chất; nếu đã mắc kẹt, thường phải điều tra thread dump và sửa code.

### 7.2. Explicit lock

`ReentrantLock` hỗ trợ `lock()`, `tryLock()`, `tryLock(timeout, unit)` và `lockInterruptibly()`. Nó cho phép quyết định **không tiếp tục chờ vô hạn** trong một số trường hợp, nhưng không tự áp dụng thứ tự khóa.

Ví dụ mẫu có hai lock đã được xếp đúng thứ tự:

~~~java
// Minh họa Java 17+, giả sử first/second là ReentrantLock phân biệt.
first.lock();
try {
    second.lock();
    try {
        updateTogether();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
~~~

Luôn unlock đúng khóa, kể cả khi việc cập nhật ném exception. Nếu có nhiều khóa hơn, nên gói thứ tự và cleanup trong một abstraction rõ ràng; tránh copy-paste phức tạp dẫn đến unlock sai.

**Chú ý:** `ReentrantLock.lock()` có thể chờ vô hạn, kể cả nếu thread bị interrupt trước hoặc trong khi chờ; sau khi acquire có thể vẫn còn interrupt flag. Nếu muốn thao tác lấy khóa phản ứng với interrupt, dùng `lockInterruptibly()` hoặc timed `tryLock` và xử lý `InterruptedException` phù hợp.

### 7.3. `tryLock` là cách thất bại có kiểm soát, không thay thế toàn bộ thiết kế

`tryLock()` có thể trả về `false` ngay nếu chưa lấy được khóa. `tryLock(timeout, unit)` chờ có giới hạn và có thể ném `InterruptedException`. Khi lấy nhiều khóa, nếu không lấy được khóa tiếp theo, phải release những khóa đã giữ, rồi trả kết quả thất bại hoặc retry theo chính sách.

Một ví dụ ngắn, hoàn chỉnh, cho thấy lựa chọn **không block vô thời hạn**.

Tạo tệp `TryLockDemo.java`:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class TryLockDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        lock.lock();

        try {
            Thread worker = new Thread(() -> {
                if (lock.tryLock()) {
                    try {
                        System.out.println("Acquired");
                    } finally {
                        lock.unlock();
                    }
                } else {
                    System.out.println("Lock unavailable");
                }
            }, "competitor");

            worker.start();
            worker.join();
        } finally {
            lock.unlock();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TryLockDemo.java
java TryLockDemo
~~~

Stdout:

~~~text
Lock unavailable
~~~

Thread `main` đang giữ `ReentrantLock` trong suốt khoảng worker gọi `tryLock()`. Worker ở thread khác nên `tryLock()` thất bại ngay, in một dòng rồi kết thúc. `join()` trở về, sau đó `main` release khóa trong `finally`. Đây là ví dụ đã được sắp đặt để kết quả xác định; trong chương trình bình thường, `tryLock` có thể thành công hoặc thất bại tùy tình trạng khóa.

Cần phân biệt **tránh block vô hạn** với **bảo đảm cập nhật thành công**: khi không lấy được khóa, thao tác nghiệp vụ chưa được thực hiện. Caller phải có quy tắc trả lỗi, xếp hàng, hủy, retry hữu hạn hoặc chờ đến deadline, không được giả vờ đã cập nhật.

### 7.4. Retry và backoff cũng có bẫy

Nếu hai thread cùng lấy một khóa rồi không lấy được khóa thứ hai và lập tức retry đồng loạt, chúng có thể rơi vào **livelock** hoặc làm CPU bận. Giải pháp có thể là backoff, jitter và giới hạn số lần thử; tuy nhiên retry không sửa thứ tự khóa không nhất quán ở lõi thiết kế. Hãy ưu tiên quy tắc lock ordering khi có thể.

Với timed `tryLock`, deadline của nghiệp vụ cần tính qua **toàn bộ chuỗi khóa**, tránh chờ tối đa N giây cho mỗi khóa rồi nhân độ trễ lên nhiều lần.

## 8. Deadlock do khóa ẩn và gọi code bên ngoài

Ngay cả khi một phương thức của bạn luôn lấy A rồi B, chương trình vẫn có thể deadlock nếu nó đang giữ một khóa không được tính vào thứ tự. Ví dụ:

- Giữ lock account rồi gọi callback do plugin viết; callback cố lấy lock cấu hình toàn cục có rank thấp hơn.
- Giữ lock cache rồi gọi phương thức có `synchronized` trên object khác mà không biết; luồng kia giữ object đó rồi cần cache.
- Giữ monitor khi thực hiện logging, observer notification hoặc hàm override có thể gọi ngược vào code gốc.
- Giữ lock khi chờ một `Future.get()`; task trong future cần chính lock đang bị giữ.
- Tự tạo dependency giữa worker trong một thread pool có một worker: task A chờ task B trong cùng pool nhưng B chưa có worker để chạy.

Hai trường hợp cuối có thể là **deadlock phụ thuộc công việc** hoặc pool starvation, dù không nhất thiết có vòng đợi hai monitor. Thứ tự khóa monitor đơn thuần không xử lý mọi loại chờ.

Các nguyên tắc phòng ngừa:

1. Giữ critical section **ngắn**; chuẩn bị dữ liệu bên ngoài khóa khi an toàn.
2. Không gọi callbacks hoặc mã của bên thứ ba trong lúc giữ lock nếu có thể.
3. Không đợi I/O, network, user input hoặc task khác vô hạn khi đang giữ lock.
4. Tài liệu hóa khóa nào được mỗi phương thức yêu cầu; nếu phương thức gọi sâu vào code khác, phải kiểm tra những khóa ẩn.
5. Nếu phải giữ nhiều lock, xem chúng là **một giao thức thứ tự duy nhất** xuyên các lớp liên quan.

## 9. Làm sao phát hiện deadlock trong JVM?

### 9.1. Biểu hiện

Một số dấu hiệu: request treo liên tục, thread không kết thúc dù không có tiến triển, CPU có thể thấp, thread dump có các luồng `BLOCKED` hoặc `WAITING`. Nhưng CPU thấp và nhiều thread đang chờ chưa đủ để kết luận deadlock: ứng dụng bình thường cũng có worker đang chờ queue/lock.

**Bằng chứng mạnh** là một chu trình tài nguyên trong đó mỗi thread giữ một khóa mà thread khác đang yêu cầu, hoặc công cụ JVM chỉ ra deadlock.

### 9.2. Thread dump và công cụ JDK

Có thể sử dụng các công cụ theo bản JDK/JVM đã triển khai:

~~~bash
jcmd <PID> Thread.print -l
~~~

hoặc khi `jstack` có sẵn:

~~~bash
jstack -l <PID>
~~~

`<PID>` là process ID thật của JVM; dòng trên là **mẫu lệnh**, cần thay bằng PID thực tế. Không phải stdout của một chương trình demo.

Trong thread dump, quan sát tên thread, stack frame đang đợi monitor, thông tin khóa đang sở hữu và khóa muốn lấy. Với deadlock monitor được JVM nhận diện, nhiều bản dump có phần thông báo deadlock kèm chuỗi khóa/owner.

Các trạng thái có ý nghĩa:

| Trạng thái thường thấy | Diễn giải |
| --- | --- |
| `BLOCKED` | Thread chờ lấy intrinsic monitor cho một vùng `synchronized` |
| `WAITING` | Có thể chờ `Object.wait`, `LockSupport.park`, `Thread.join` hoặc primitive khác |
| `TIMED_WAITING` | Chờ có deadline/time limit; không mặc nhiên deadlock |
| `RUNNABLE` | Đang thực thi hoặc sẵn sàng chạy; không tự chứng minh có tiến triển hữu ích |

Với `ReentrantLock`, thread có thể xuất hiện ở `WAITING` hoặc `TIMED_WAITING` (đợi qua `LockSupport`), không phải `BLOCKED` chờ intrinsic monitor. Vì vậy không chỉ lọc các thread `BLOCKED` khi điều tra.

### 9.3. ThreadMXBean

`java.lang.management.ThreadMXBean` cung cấp:

- `findMonitorDeadlockedThreads()`: phát hiện vòng deadlock liên quan **object monitor**.
- `findDeadlockedThreads()`: tìm vòng deadlock liên quan **object monitor và ownable synchronizer**, khi JVM hỗ trợ khả năng này; không phát hiện mọi dạng chờ ngoài JVM hoặc deadlock phụ thuộc hệ thống.
- `getThreadInfo(ids, true, true)`: lấy thông tin monitor và synchronizer theo khả năng hỗ trợ của JVM.

Ví dụ cách truy vấn, **không phải chương trình độc lập**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isSynchronizerUsageSupported()) {
    long[] ids = bean.findDeadlockedThreads();
    if (ids != null) {
        System.out.println("Deadlocked threads: " + ids.length);
    }
}
~~~

Đoạn minh họa trên chỉ truy vấn thông tin; ứng dụng phải có cơ chế cảnh báo/điều tra và tránh lặp kiểm tra với tần suất gây chi phí cao. Việc không tìm thấy chu trình tại một thời điểm không chứng minh mọi luồng đang tiến triển tốt, cũng không loại trừ deadlock xảy ra sau đó.

### 9.4. Khi phát hiện deadlock trong production

Thu thập thread dump hoặc JFR/log phù hợp, xác định thread nào giữ/chờ khóa nào, lần theo nguồn gọi vào monitor/lock, vẽ wait-for graph và tìm đường đi đảo thứ tự. Sửa giao thức cấp khóa ở mã nguồn; tránh coi việc restart tiến trình là lời giải gốc. Nếu cần can thiệp vận hành, chú ý việc force-stop các thread khi chúng giữ bất biến có thể phá hỏng trạng thái.

Không sử dụng `Thread.stop()` để “phá deadlock”: API này không an toàn, đã deprecated và không phải chiến lược phục hồi đúng.

## 10. Kiểm thử quy tắc thứ tự khóa

Một test đơn thuần khởi chạy hai thread rồi ngủ 100 ms không chứng minh không có deadlock; các thread có thể chạy tuần tự trong lần test đó.

Để kiểm tra có ý nghĩa:

1. Thiết kế **invariant** cần giữ: tổng số dư, số phần tử, trạng thái cập nhật, thứ tự bản ghi.
2. Khởi chạy nhiều task theo cả hai hướng thao tác (A → B, B → A), có thể dùng `CountDownLatch` hoặc `CyclicBarrier` để bắt đầu cạnh tranh cùng lúc.
3. Đợi hoàn tất với timeout ở tầng test; nếu timeout, thu thập thread dump và xác định vì sao. Timeout không tự chứng minh deadlock.
4. Kiểm tra kết quả/invariant sau khi mọi task hoàn tất; đừng xem “không treo” là đủ.
5. Phân tích **tất cả đường gọi và khóa ẩn**, bao gồm snapshot getter, callback và error handler.
6. Chạy stress test phù hợp và đo contention/latency, nhưng xem **lập luận thứ tự** là bảo đảm thiết kế quan trọng nhất.

Một ví dụ test có thể sinh nhiều cặp account, chuyển khoản qua lại, rồi xác minh tổng không đổi, số dư không âm, không thread nào kẹt. Cần giới hạn số task và thời gian chờ, để test không bị treo vĩnh viễn khi phát hiện lỗi.

## 11. Những sai lầm phổ biến

**“Lúc nào cũng lấy khóa của đối tượng `from` trước `to`.”** Khi hai caller đi hai chiều ngược nhau, chúng đảo thứ tự và có thể tạo vòng chờ. Xếp theo rank ổn định độc lập với hướng nghiệp vụ.

**“`hashCode` là thứ tự duy nhất.”** Hash có thể va chạm và bị override. Dùng rank riêng duy nhất hoặc có tie-breaker được áp dụng nhất quán.

**“Chỉ cần sửa chỗ có hai `synchronized` lồng nhau là xong.”** Code có thể lấy khóa gián tiếp qua helper/callback; phải kiểm tra toàn bộ call graph và đường lấy khóa nhiều cấp.

**“`ReentrantLock` tự tránh deadlock.”** Lock explicit vẫn có thể lấy sai thứ tự. `tryLock`/timeout giúp không chờ mãi ở một số tình huống nhưng cần cleanup và retry policy.

**“Lấy hai khóa rất nhanh nên không thể deadlock.”** Deadlock phụ thuộc thứ tự cạnh tranh, không chỉ thời gian critical section. Thời gian giữ khóa ngắn giảm xác suất, không chứng minh an toàn.

**“Chỉ thread BLOCKED mới có deadlock.”** `ReentrantLock` chờ qua `LockSupport`; phụ thuộc `Future` hoặc queue có thể khiến thread `WAITING`. Đọc stack và thông tin owner.

**“Mọi timeout đều là deadlock.”** Timeout có thể do CPU quá tải, I/O lâu, starvation hoặc pool cạn worker. Cần bằng chứng của chuỗi chờ và loại tài nguyên.

**“Đã dùng lock ordering thì mọi lỗi concurrency biến mất.”** Thứ tự khóa chỉ xử lý một nhóm deadlock; dữ liệu vẫn có thể bị race nếu có đường đọc/ghi không khóa, hay hệ thống vẫn có livelock, starvation, hủy lỗi, thời gian chờ và sự cố external resource.

## 12. Checklist review trước khi đưa vào ứng dụng

| Câu hỏi | Tiêu chí |
| --- | --- |
| Có tài nguyên nào cần giữ hai khóa cùng lúc? | Đã liệt kê tất cả đường gọi, kể cả đọc snapshot |
| Rank của mỗi khóa có duy nhất và ổn định? | Không phụ thuộc thứ tự đầu vào, trạng thái mutable hoặc hash có thể va chạm |
| Mọi đường code có lấy khóa theo cùng thứ tự? | Không có helper/callback lén lấy khóa bậc thấp trong khi giữ bậc cao |
| Lock có được đóng gói riêng? | Tránh để code ngoài giữ monitor không biết trước |
| Code có gọi I/O hoặc chờ task trong lúc giữ lock? | Đã giảm tối đa các lời chờ không giới hạn |
| `ReentrantLock` có unlock đúng trong `finally`? | Mỗi lần acquire có release tương ứng |
| Thất bại lấy khóa có trả kết quả rõ ràng? | Không cập nhật dở, không retry vô hạn |
| Có cách điều tra deadlock? | Thread dump/JFR/metrics, stack và lock owner |
| Có kiểm tra bất biến sau khi chạy đồng thời? | Test nhiều hướng, có timeout và chẩn đoán |
| Đã hiểu giới hạn? | Lock ordering không tự xử lý resource deadlock ngoài phạm vi khóa đã xếp |

### Câu hỏi tự kiểm tra

**1.** Thread 1 lấy A → B; thread 2 lấy B → A. Khi nào deadlock xuất hiện?

Khi thread 1 giữ A và cần B trong lúc thread 2 giữ B và cần A, tạo vòng chờ. Việc mỗi lock riêng lẻ hoạt động đúng không loại bỏ vòng này.

**2.** Trong một hệ thống có rank A < B, chuyển tiền từ B sang A nên lấy khóa nào trước?

Vẫn là **A rồi B**, bất kể chiều nghiệp vụ B → A.

**3.** Vì sao xếp khóa theo `System.identityHashCode` mà không xử lý giá trị bằng nhau là chưa đủ?

Hai object khác nhau có thể có cùng identity hash. Nếu hai thread tự giữ thứ tự tham số khi bằng nhau, chúng có thể lấy A/B ngược nhau. Cần tie lock hoặc rank duy nhất.

**4.** Một thread đang `BLOCKED` chờ vào `synchronized`. Gọi `interrupt()` có tự động làm nó dừng chờ monitor không?

Không. Yêu cầu vào intrinsic monitor không phải một phép chờ interruptible theo kiểu `ReentrantLock.lockInterruptibly()`. Phải thiết kế tránh vòng chờ hoặc dùng primitive phù hợp từ đầu.

**5.** Hai thread luôn lấy A rồi B, nhưng trong lúc giữ B có callback cố lấy khóa C, còn một thread thứ ba giữ C và cần A. Đã đủ chứng minh không có deadlock chưa?

Chưa. Khóa C là một phần của wait-for graph và phải được đưa vào thứ tự toàn cục, hoặc không gọi callback trong critical section.

**Ghi nhớ:** Khi cần đồng thời nhiều khóa, hãy **định nghĩa một thứ tự tổng ổn định trên tài nguyên và tuân thủ ở mọi đường lấy khóa**. Chứng minh được không tồn tại cạnh chờ đi ngược thứ tự giúp loại bỏ deadlock do vòng chờ của những khóa này, đồng thời vẫn duy trì khóa cần thiết để bảo vệ bất biến.