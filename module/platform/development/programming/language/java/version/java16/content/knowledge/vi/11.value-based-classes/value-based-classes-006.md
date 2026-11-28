# Chọn khóa private chuyên dụng cho trạng thái cần đồng bộ

Khi nhiều luồng cùng truy cập và thay đổi một trạng thái, chương trình cần một cơ chế phối hợp để tránh race condition. Trong Java, **synchronized** sử dụng intrinsic monitor của object làm khóa. Muốn cơ chế này hoạt động đúng, các luồng cùng bảo vệ một trạng thái phải sử dụng thống nhất một monitor.

Một cách thiết kế phổ biến và dễ kiểm soát là tạo object khóa riêng bằng **new Object()**, lưu trong field **private final**. Khóa được giữ bên trong lớp, không bị code bên ngoài lấy hoặc thay thế. Phạm vi của khóa cần phù hợp với phạm vi trạng thái được bảo vệ: mỗi instance có khóa riêng cho trạng thái riêng, còn trạng thái static dùng chung cần một khóa static dùng chung.

Bài học này trình bày cách chọn và đóng gói khóa, bảo vệ dữ liệu nhất quán, tổ chức nhiều khóa để tránh deadlock và lựa chọn API đồng bộ phù hợp trong Java hiện đại.

## 1. Vì sao cần một object khóa riêng?

Một khối **synchronized** có dạng:

~~~java
synchronized (lock) {
    // Vùng code cần bảo vệ
}
~~~

Khi một luồng đi vào khối, nó phải lấy được monitor của object được tham chiếu bởi **lock**. Luồng khác muốn vào một khối đồng bộ trên cùng object sẽ phải chờ cho tới khi monitor được giải phóng.

Có thể tạo một object khóa riêng:

~~~java
private final Object lock = new Object();
~~~

Field này có ba đặc điểm quan trọng:

- **private:** code bên ngoài lớp không thể trực tiếp lấy khóa để đồng bộ tùy ý.
- **final:** tham chiếu khóa không thể bị gán sang object khác sau khi khởi tạo.
- **Object mới:** mỗi lần tạo instance của lớp sẽ có một object khóa riêng, có identity ổn định trong vòng đời của instance đó.

Khóa riêng giúp lớp kiểm soát được những đoạn code cùng tham gia bảo vệ trạng thái. Khi tất cả thao tác đọc và ghi dữ liệu đều tuân theo cùng một quy tắc khóa, chương trình có thể duy trì tính nhất quán giữa các luồng.

Không dùng các giá trị có identity không phù hợp làm khóa như **Integer**, **Long**, **Boolean**, **String literal**, **Optional** hoặc các value-based class khác. Một object khóa chuyên dụng nên được tạo riêng cho đúng mục đích đồng bộ.

## 2. Chọn phạm vi khóa theo phạm vi trạng thái

Một quyết định quan trọng là xác định dữ liệu thuộc về từng object hay được chia sẻ giữa mọi instance.

### Trạng thái riêng của từng instance: private final Object

Giả sử mỗi tài khoản có số dư riêng. Các thao tác đọc và cập nhật số dư của cùng một tài khoản cần được đồng bộ, nhưng hai tài khoản khác nhau có thể hoạt động độc lập.

~~~java
public class Account {
    private final Object lock = new Object();
    private long balance;

    public Account(long initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư ban đầu không hợp lệ");
        }
        this.balance = initialBalance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
        }

        synchronized (lock) {
            balance += amount;
        }
    }

    public boolean withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
        }

        synchronized (lock) {
            if (balance < amount) {
                return false;
            }

            balance -= amount;
            return true;
        }
    }

    public long getBalance() {
        synchronized (lock) {
            return balance;
        }
    }
}
~~~

Mỗi instance **Account** có một object khóa riêng. Các luồng cùng thao tác trên một tài khoản sẽ tranh chấp cùng monitor, trong khi thao tác trên hai tài khoản khác nhau không cần dùng chung khóa.

Ví dụ:

~~~java
Account accountA = new Account(1_000);
Account accountB = new Account(2_000);
~~~

**accountA** và **accountB** có trạng thái độc lập và mỗi object có một khóa riêng. Điều này cho phép tăng khả năng xử lý đồng thời khi các thao tác không liên quan tới nhau.

Một nguyên tắc cần giữ là mọi đường truy cập tới **balance** đều phải tuân theo cùng cơ chế đồng bộ. Nếu một phương thức đọc hoặc ghi field này bên ngoài khối **synchronized (lock)**, bảo đảm đồng bộ có thể bị phá vỡ.

### Trạng thái static dùng chung: private static final Object

Nếu nhiều instance cùng truy cập một biến static, khóa instance riêng không đủ để bảo vệ dữ liệu đó. Mỗi instance có monitor riêng, vì vậy hai luồng trên hai instance khác nhau vẫn có thể đồng thời cập nhật cùng biến static.

Hãy sử dụng một khóa static dùng chung:

~~~java
public class GlobalCounter {
    private static final Object LOCK = new Object();
    private static long count;

    public static void increment() {
        synchronized (LOCK) {
            count++;
        }
    }

    public static long getCount() {
        synchronized (LOCK) {
            return count;
        }
    }
}
~~~

Tất cả instance và lời gọi static trong cùng class loader sử dụng cùng một object **LOCK**. Vì vậy, các thao tác đọc và ghi **count** được phối hợp trên cùng monitor.

Nếu dùng **private final Object** không có **static** trong trường hợp này, mỗi instance sẽ có một khóa khác nhau và không bảo vệ được biến static trước các truy cập đồng thời từ nhiều instance.

### So sánh hai cách chọn khóa

| Đặc điểm | Khóa instance | Khóa static |
| --- | --- | --- |
| Khai báo | **private final Object lock** | **private static final Object LOCK** |
| Số lượng khóa | Một khóa cho mỗi instance | Một khóa dùng chung ở cấp lớp |
| Trạng thái phù hợp | Field thuộc từng object | Field static hoặc tài nguyên dùng chung ở cấp lớp |
| Mức độ song song | Các instance độc lập có thể hoạt động đồng thời | Các thao tác dùng chung monitor phải lần lượt lấy khóa |
| Ví dụ | Số dư của từng tài khoản | Bộ đếm dùng chung toàn class |

Không chọn khóa chỉ dựa trên tên phương thức. Hãy xác định chính xác trạng thái nào cần được bảo vệ và những luồng nào có thể cùng truy cập trạng thái đó.

## 3. Đóng gói khóa để kiểm soát quyền truy cập

Khóa đồng bộ là một phần của thiết kế nội bộ lớp. Nếu để khóa ở mức public hoặc trả nó qua getter, code bên ngoài có thể sử dụng cùng monitor cho mục đích khác.

Ví dụ không nên dùng:

~~~java
public class SharedState {
    public final Object lock = new Object();
    private int value;
}
~~~

Code bên ngoài có thể viết:

~~~java
synchronized (sharedState.lock) {
    // Khóa ngoài lớp
}
~~~

Khi đó, lớp không còn kiểm soát đầy đủ việc sử dụng monitor. Một đoạn code bên ngoài có thể giữ khóa quá lâu hoặc lấy nhiều khóa theo thứ tự không nhất quán, gây tranh chấp và deadlock.

Cách thiết kế tốt hơn:

~~~java
public class SharedState {
    private final Object lock = new Object();
    private int value;

    public void update(int newValue) {
        synchronized (lock) {
            value = newValue;
        }
    }

    public int getValue() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Khóa chỉ được sử dụng bên trong class. Các phương thức công khai cung cấp hành vi cần thiết, còn chi tiết phối hợp giữa các luồng được giữ kín.

### Vì sao cần final?

Nếu tham chiếu khóa có thể thay đổi, các luồng có thể vô tình đồng bộ trên những object khác nhau.

Ví dụ:

~~~java
private Object lock = new Object();

public void update() {
    synchronized (lock) {
        // Cập nhật trạng thái
    }
}
~~~

Nếu một luồng thay đổi **lock** trong khi luồng khác đang dùng giá trị cũ, các lời gọi tiếp theo có thể khóa một monitor khác. Khi đó, chúng không còn phối hợp trên cùng một khóa.

Khai báo:

~~~java
private final Object lock = new Object();
~~~

giúp giữ nguyên tham chiếu khóa trong suốt vòng đời của instance. Đây là lựa chọn phù hợp cho khóa monitor chuyên dụng.

**final** bảo vệ tham chiếu khỏi việc gán lại, không tự thay thế quy tắc đồng bộ dữ liệu. Những field được bảo vệ vẫn cần được truy cập theo cùng giao thức khóa.

## 4. Đồng bộ nhất quán mọi thao tác đọc và ghi

Một khóa chỉ có tác dụng khi mọi thao tác liên quan tới trạng thái được bảo vệ đều tuân theo giao thức đồng bộ.

Xét ví dụ:

~~~java
public class Stock {
    private final Object lock = new Object();
    private int quantity;

    public void add(int amount) {
        synchronized (lock) {
            quantity += amount;
        }
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Phương thức **add()** sử dụng khóa nhưng **getQuantity()** đọc dữ liệu bên ngoài vùng đồng bộ. Cách viết này không tạo ra giao thức bảo vệ nhất quán cho field **quantity**. Luồng đọc không lấy cùng monitor nên không có quan hệ happens-before tương ứng với thao tác ghi được bảo vệ.

Hãy sửa bằng cách dùng cùng khóa:

~~~java
public int getQuantity() {
    synchronized (lock) {
        return quantity;
    }
}
~~~

Khi mọi thao tác đọc và ghi cùng lấy một monitor, việc mở khóa của luồng trước xảy ra trước lần khóa thành công tiếp theo trên cùng monitor. Đây là quan hệ **happens-before** trong Java Memory Model, giúp bảo đảm visibility của các thay đổi được thực hiện trong vùng đồng bộ.

Nếu một field chỉ được truy cập dưới cùng một monitor, thông thường không cần thêm **volatile** cho chính field đó. Nếu một số đường truy cập nằm ngoài monitor, cần thiết kế lại giao thức đồng bộ thay vì mặc định rằng **synchronized** ở một phương thức đã bảo vệ toàn bộ trạng thái.

### Bảo vệ một invariant thay vì từng field riêng lẻ

Một invariant là điều kiện phải luôn đúng giữa nhiều field. Ví dụ, một hệ thống tồn kho có số lượng khả dụng và số lượng đã đặt:

~~~java
public class Inventory {
    private final Object lock = new Object();
    private int available;
    private int reserved;

    public void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException();
        }

        synchronized (lock) {
            if (available < amount) {
                throw new IllegalStateException("Không đủ hàng");
            }

            available -= amount;
            reserved += amount;
        }
    }

    public int getAvailable() {
        synchronized (lock) {
            return available;
        }
    }

    public int getReserved() {
        synchronized (lock) {
            return reserved;
        }
    }
}
~~~

Hai field **available** và **reserved** cùng mô tả trạng thái của một kho hàng. Việc chuyển số lượng từ khả dụng sang đã đặt phải diễn ra trong cùng vùng đồng bộ. Nếu khóa từng field riêng, một luồng khác có thể quan sát trạng thái trung gian không phù hợp với invariant.

Hãy chọn phạm vi khóa đủ rộng để bảo vệ toàn bộ thay đổi cần được xem như một thao tác nguyên tử.

## 5. Giảm tranh chấp bằng cách chọn đúng độ hạt khóa

Một khóa duy nhất cho toàn bộ ứng dụng có thể đơn giản, nhưng dễ khiến nhiều luồng không liên quan phải chờ nhau. Ngược lại, chia quá nhiều khóa làm tăng độ phức tạp và nguy cơ deadlock.

Có thể lựa chọn theo nguyên tắc:

- Dùng một khóa cho một nhóm trạng thái cần duy trì invariant chung.
- Dùng các khóa độc lập khi các nhóm trạng thái không phụ thuộc nhau.
- Giữ vùng đồng bộ ngắn, chỉ bao gồm thao tác cần bảo vệ.
- Tránh thực hiện I/O, gọi mạng, chờ tác vụ hoặc gọi callback bên ngoài khi đang giữ khóa.
- Đánh giá hiệu năng bằng profiling và tải thực tế trước khi chia nhỏ khóa.

Ví dụ, một đối tượng có hai nhóm dữ liệu độc lập:

~~~java
public class UserSession {
    private final Object profileLock = new Object();
    private final Object preferenceLock = new Object();

    private String displayName;
    private boolean notificationsEnabled;

    public void updateDisplayName(String name) {
        synchronized (profileLock) {
            displayName = name;
        }
    }

    public void setNotificationsEnabled(boolean enabled) {
        synchronized (preferenceLock) {
            notificationsEnabled = enabled;
        }
    }
}
~~~

Hai thao tác cập nhật độc lập có thể diễn ra đồng thời. Tuy nhiên, nếu có một thao tác cần đọc hoặc cập nhật cả hai nhóm dữ liệu trong cùng một invariant, thiết kế phải xác định một giao thức khóa kết hợp rõ ràng.

Không chia khóa chỉ để giảm thời gian chờ nếu chưa xác định được quan hệ giữa các field. Một khóa bảo vệ invariant thường dễ hiểu và an toàn hơn nhiều khóa nhỏ nhưng không có quy tắc phối hợp.

## 6. Tránh deadlock khi cần lấy nhiều khóa

Deadlock có thể xảy ra khi các luồng chờ khóa của nhau theo một chu trình.

Ví dụ:

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        // Công việc
    }
}
~~~

Nếu luồng thứ nhất lấy **lockA** rồi chờ **lockB**, trong khi luồng thứ hai lấy **lockB** rồi chờ **lockA**, cả hai có thể chờ vô hạn.

Cách quan trọng để giảm rủi ro là quy định một thứ tự lấy khóa nhất quán trong toàn bộ ứng dụng. Ví dụ, nếu hai tài khoản cần được khóa đồng thời khi chuyển tiền, hãy sắp xếp chúng theo một định danh duy nhất trước khi lấy khóa.

~~~java
// Ý tưởng: luôn lấy khóa tài khoản có ID nhỏ hơn trước,
// sau đó mới lấy khóa tài khoản có ID lớn hơn.
~~~

Nếu hai tài nguyên không có thứ tự tự nhiên, có thể thiết kế một khóa điều phối chung hoặc dùng một cơ chế khóa khác có khả năng kiểm soát thứ tự và timeout. Không tự tạo thứ tự bằng cách dựa vào giá trị **hashCode()** vì hash code có thể trùng nhau và không phải định danh duy nhất.

Một số nguyên tắc thực hành:

1. Xác định thứ tự lấy khóa cho các tài nguyên có thể được khóa cùng lúc.
2. Áp dụng cùng thứ tự trong mọi đường code.
3. Không gọi code bên ngoài khi đang giữ nhiều khóa.
4. Giữ vùng đồng bộ ngắn và tránh chờ một tác vụ khác đang cần khóa hiện tại.
5. Khi cần timeout hoặc hủy thao tác chờ, cân nhắc **ReentrantLock**.

## 7. Khi nào dùng synchronized và khi nào dùng API khác?

Khóa **private final Object** phù hợp với vùng tới hạn đơn giản, nơi các thao tác cần phối hợp trên một monitor. Java hiện đại còn có nhiều công cụ đồng bộ chuyên biệt.

| Nhu cầu | Giải pháp phù hợp |
| --- | --- |
| Bảo vệ một nhóm field có invariant chung | **synchronized** với khóa riêng |
| Cần timeout, tryLock hoặc khả năng interrupt khi chờ khóa | **ReentrantLock** |
| Cập nhật một giá trị số độc lập theo thao tác nguyên tử | **AtomicInteger**, **AtomicLong** |
| Nhiều luồng ghi và đọc bộ đếm thống kê | **LongAdder** |
| Trao đổi dữ liệu giữa các luồng | **BlockingQueue** |
| Chờ một nhóm tác vụ hoàn thành | **CountDownLatch**, **Phaser** |

Ví dụ với **ReentrantLock**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class TaskCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int completed;

    public void increment() {
        lock.lock();
        try {
            completed++;
        } finally {
            lock.unlock();
        }
    }

    public int getCompleted() {
        lock.lock();
        try {
            return completed;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Khóa phải được giải phóng trong **finally**, kể cả khi code trong vùng tới hạn phát sinh exception.

Nếu chỉ bảo vệ một biến số độc lập bằng thao tác tăng hoặc giảm nguyên tử, **AtomicInteger** có thể đơn giản hơn:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    public void recordRequest() {
        count.incrementAndGet();
    }

    public int getCount() {
        return count.get();
    }
}
~~~

Không cần tạo thêm monitor riêng nếu một API nguyên tử đã đáp ứng đúng yêu cầu. Ngược lại, khi cần cập nhật nhiều field như một đơn vị nhất quán, một khóa chung thường phù hợp hơn việc dùng nhiều atomic variable riêng lẻ.

## 8. Rà soát thiết kế khóa trong dự án

Khi thiết kế một class có trạng thái dùng chung giữa các luồng, hãy kiểm tra các điểm sau:

1. Xác định các field mutable cần bảo vệ và invariant giữa chúng.
2. Xác định trạng thái thuộc từng instance hay dùng chung ở cấp lớp.
3. Chọn **private final Object** hoặc **private static final Object** theo đúng phạm vi.
4. Đảm bảo mọi thao tác đọc và ghi liên quan đều sử dụng cùng giao thức đồng bộ.
5. Không công khai hoặc trả tham chiếu khóa cho code bên ngoài.
6. Giữ vùng đồng bộ ngắn và tránh gọi I/O, mạng hoặc callback khi đang giữ khóa.
7. Nếu phải lấy nhiều khóa, thiết lập thứ tự lấy khóa nhất quán.
8. Chọn **ReentrantLock** hoặc API trong **java.util.concurrent** khi cần tính năng chuyên biệt.
9. Kiểm thử các tình huống nhiều luồng truy cập đồng thời và đo hiệu năng trên tải đại diện.

Một thiết kế khóa tốt giúp người đọc nhận biết ngay trạng thái nào được bảo vệ, ai sở hữu khóa và các thao tác nào phải phối hợp với nhau.

## 9. Kết luận

**private final Object lock = new Object()** là cách đơn giản và đáng tin cậy để tạo monitor riêng cho trạng thái của một instance. Với dữ liệu static được chia sẻ giữa các instance, dùng **private static final Object** để mọi thao tác cần phối hợp lấy cùng monitor.

Giữ khóa private và final, đồng bộ nhất quán mọi thao tác đọc ghi, bảo vệ invariant trong cùng vùng tới hạn và quy định thứ tự lấy khóa khi cần nhiều monitor. Khi nhu cầu vượt quá khả năng của **synchronized**, hãy chọn **ReentrantLock**, atomic class hoặc các công cụ đồng thời phù hợp. Những nguyên tắc này giúp code Java dễ kiểm soát, dễ bảo trì và an toàn trong môi trường nhiều luồng.

## Tài liệu tham khảo

- [JLS 27 — Synchronized Statements (Section 14.19)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.19)
- [JLS 27 — Happens-before Order (Section 17.4.5)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4.5)
- [Object — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html)
- [ReentrantLock — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [AtomicInteger — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [LongAdder — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [BlockingQueue — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [CountDownLatch — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Phaser — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Phaser.html)

