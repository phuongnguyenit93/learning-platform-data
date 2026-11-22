# Lock hierarchy và cách tránh thứ tự khóa vòng trong Java

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích **deadlock do thứ tự lấy khóa vòng** (*circular lock ordering*) và mô tả **wait-for graph** (đồ thị chờ) của các thread.
- Hiểu **lock hierarchy** (thứ bậc khóa) là quy tắc áp dụng **một thứ tự toàn cục, ổn định** khi cần giữ từ hai khóa trở lên.
- Chứng minh vì sao mọi đường lấy khóa theo cùng thứ tự tăng dần có thể loại bỏ vòng chờ do những khóa ấy, đồng thời phân biệt **deadlock**, **starvation**, **livelock** và **contention**.
- Viết Java 17+ dùng **synchronized** hoặc **ReentrantLock**, sắp xếp khóa theo ID/rank duy nhất, và luôn nhả khóa theo cấu trúc an toàn.
- Xử lý trường hợp cùng object, cùng rank, khóa động, va chạm **System.identityHashCode()**, callback và tài nguyên ngoài JVM.
- Nhận biết giới hạn của **tryLock()**, timeout, interrupt và retry: các cơ chế này không thay thế thứ tự khóa nhất quán.
- Chẩn đoán deadlock bằng thread dump và kiểm thử bất biến thay vì phụ thuộc **Thread.sleep()** hoặc thứ tự log tình cờ.

Bài chỉ nói về **Java concurrency trong JDK**, dưới chủ đề **Locks & Conditions**. Các cơ chế khóa và quản lý giao dịch đặc thù của Spring thuộc chương riêng.

## 2. Deadlock xảy ra như thế nào?

**Deadlock** là tình trạng những thực thể đang chờ nhau theo cách khiến không thực thể nào có thể tự tiến lên để giải phóng tài nguyên mà thực thể khác cần. Với các khóa loại trừ nhau trong một JVM, ví dụ quen thuộc nhất là **hai thread lấy hai khóa theo thứ tự ngược nhau**.

Giả sử có **lockA** và **lockB**:

~~~text
Thread T1                            Thread T2
---------                            ---------
lock(lockA)                          lock(lockB)
  đã giữ A                             đã giữ B
  yêu cầu B -> chờ T2                  yêu cầu A -> chờ T1

T1 giữ A và chờ B  ----+
                       +---- vòng chờ -> DEADLOCK
T2 giữ B và chờ A  ----+
~~~

Hai thread đều giữ một tài nguyên mà thread kia cần. Nếu không có timeout, chính sách hủy/giải phóng thích hợp hoặc tác nhân khác thay đổi điều kiện, không thread nào có thể hoàn thành đoạn mã để nhả khóa.

Với **synchronized**, thread chờ giành intrinsic monitor thường được quan sát là **Thread.State.BLOCKED**. Với **ReentrantLock**, thread có thể chờ bằng cơ chế khác và không nhất thiết được báo là BLOCKED; quan sát trạng thái đơn lẻ không đủ kết luận có deadlock.

### Bốn điều kiện kinh điển (Coffman)

| Điều kiện | Ý nghĩa |
| --- | --- |
| **Mutual exclusion** | Ít nhất một tài nguyên không thể được sở hữu đồng thời bởi nhiều thread |
| **Hold and wait** | Thread giữ tài nguyên này trong khi đợi tài nguyên khác |
| **No preemption** | Tài nguyên không thể bị thu hồi tùy ý khỏi thread đang sở hữu |
| **Circular wait** | Tồn tại chu trình các thread chờ tài nguyên do nhau giữ |

Một deadlock dạng khóa chỉ xảy ra khi các điều kiện phù hợp cùng xuất hiện. **Lock hierarchy nhằm phá điều kiện circular wait**, bằng quy tắc không cho thread lấy khóa theo chiều tạo vòng.

**Không nên hiểu rằng chỉ có hai khóa mới deadlock.** Vòng có thể gồm T1→T2→T3→T1, nhiều lock và thậm chí kết hợp lock với sự kiện như **join()**, **Future.get()** hay callback đang chờ.

## 3. Lock hierarchy: áp đặt một thứ tự khóa toàn cục

Cho các khóa được sử dụng chung một **rank** hoặc **level** có thứ tự tổng quát rõ ràng:

~~~text
Rank 10: lockAccount
   ↓
Rank 20: lockLedger
   ↓
Rank 30: lockAudit

Được phép: 10 -> 20 -> 30; 10 -> 30; 20 -> 30.
Không được: 30 -> 20; 20 -> 10; 10 -> 30 -> 20.
~~~

Một quy tắc đơn giản là:

> Khi thread đang giữ khóa có rank **r**, nó chỉ được lấy thêm khóa **khác** có rank **lớn hơn r**. Khi thoát vùng khóa lồng nhau, nhả các khóa theo chiều ngược lại.

Nếu mọi đường mã đều tuân thủ nghiêm ngặt, không thể có vòng chờ chỉ gồm những khóa này:

- Mỗi cạnh chờ để lấy thêm khóa đi từ rank thấp đến rank cao.
- Một chu trình sẽ đòi chuỗi tăng nghiêm ngặt quay lại rank bắt đầu, điều bất khả thi.
- Do đó không có **circular wait** đối với tập khóa chịu cùng quy tắc.

Đây là **lập luận về tính đúng đắn**, không phải bảo đảm rằng code sẽ chạy nhanh, không starvation hoặc không có kiểu chờ khác. Quy tắc phải áp dụng tới **tất cả đường lấy các khóa liên quan**, kể cả helper, callback và phần code nằm sâu bên trong thư viện do ứng dụng kiểm soát.

### Rank cần có thuộc tính nào?

Một cách gán rank thực tế nên đảm bảo:

1. **Ổn định** suốt thời gian dùng khóa: không đổi rank khi một thread có thể đang giữ nó.
2. **Có thể so sánh được theo cùng một quy tắc** ở mọi nơi dùng những khóa đó.
3. **Phân biệt được những khóa khác nhau** khi quy tắc yêu cầu thứ tự nghiêm ngặt; nếu hai khóa có cùng rank cần một cơ chế *tie-break* được chứng minh.
4. **Không phụ thuộc lịch scheduling**: không chọn khóa trước theo thread nào chạy nhanh hơn.
5. **Không bị lách qua đường khác**: mã lấy khóa thủ công hoặc gọi ngược vào code khác không được vi phạm thứ tự.

Ví dụ ID của đối tượng nghiệp vụ có thể phù hợp nếu được cấp **duy nhất, bất biến** trong phạm vi các khóa được điều phối. Đừng dùng giá trị có thể thay đổi hoặc so sánh chỉ bằng tên hiển thị.

## 4. Sơ đồ wait-for graph và cycle

**Wait-for graph** là đồ thị có hướng:

- **Đỉnh** là các thread hoặc tác vụ.
- Cạnh **Ti → Tj** nghĩa là Ti đang chờ tài nguyên do Tj sở hữu.
- **Chu trình chờ** trong ngữ cảnh tài nguyên độc quyền là bằng chứng quan trọng cho deadlock.

Ví dụ:

~~~text
T1 --đợi lockB do T2 giữ--> T2
T2 --đợi lockC do T3 giữ--> T3
T3 --đợi lockA do T1 giữ--> T1

=> T1 -> T2 -> T3 -> T1 : vòng chờ.
~~~

Một **lock-order graph** lại có đỉnh là khóa: cạnh **A → B** nghĩa là trong một đường thực thi, một thread lấy B khi đang giữ A. Nếu hệ thống xuất hiện cả **A → B** và **B → A**, có nguy cơ vòng chờ khi các đường mã đó thực thi đồng thời.

Không phải mọi cycle trên sơ đồ lý thuyết đều dẫn đến deadlock trong một lần chạy cụ thể; nó chỉ ra lịch xen kẽ tiềm năng cần kiểm tra. Ngược lại, một thread dump không thấy vòng tại thời điểm chụp **không chứng minh** không bao giờ deadlock.

### Thứ tự khóa khác với thứ tự chạy

Lock hierarchy không bắt T1 chạy trước T2, cũng không bắt task A xong trước task B. Nó chỉ áp đặt **thứ tự yêu cầu sở hữu tài nguyên** trong các đoạn mã cần nhiều khóa.

Ví dụ một thread có thể lấy rank 20 khi chưa giữ khóa nào; nó không phải lấy rank 10 trước. Nhưng khi đang giữ rank 20 thì **không được bổ sung rank 10**.

## 5. Anti-pattern: hai luồng lấy khóa ngược chiều

Đây là đoạn **minh họa lỗi**, không phải chương trình độc lập nên chạy trực tiếp:

~~~java
Object lockA = new Object();
Object lockB = new Object();

// Thread T1:
synchronized (lockA) {
    synchronized (lockB) {
        // Xử lý cần cả A và B.
    }
}

// Thread T2:
synchronized (lockB) {
    synchronized (lockA) {
        // Xử lý cần cả B và A.
    }
}
~~~

Nếu T1 đang giữ A và T2 giữ B, cả hai lần khóa trong có thể chờ nhau vô hạn. **Không thêm Thread.sleep() để “giải quyết”**: sleep không nhả monitor. Đổi Thread.yield() cũng không nhả monitor hay tạo một giao thức tránh vòng.

Không nên để ví dụ thực hành tạo deadlock vô hạn ở main vì chương trình có thể treo. Các ví dụ bên dưới dùng **thứ tự khóa đúng** hoặc fail-fast để có điểm kết thúc và stdout xác định.

## 6. Ví dụ 1: sắp xếp ReentrantLock theo rank

Một helper lấy hai khóa theo rank tăng dần, bất kể người gọi truyền đối số theo thứ tự nào. Vì hai thread có thể yêu cầu cùng hai tài nguyên theo chiều đối nghịch, helper cần tạo **cùng thứ tự thực tế** trước khi lock.

Tệp **OrderedLocksDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class OrderedLocksDemo {
    static final class RankedLock {
        final int rank;
        final ReentrantLock lock = new ReentrantLock();

        RankedLock(int rank) {
            this.rank = rank;
        }
    }

    static void withBoth(
            RankedLock a, RankedLock b, Runnable action) {

        if (a == b) {
            a.lock.lock();
            try {
                action.run();
            } finally {
                a.lock.unlock();
            }
            return;
        }

        if (a.rank == b.rank) {
            throw new IllegalArgumentException("ranks must be unique");
        }

        RankedLock first = a.rank < b.rank ? a : b;
        RankedLock second = a.rank < b.rank ? b : a;

        first.lock.lock();
        try {
            second.lock.lock();
            try {
                action.run();
            } finally {
                second.lock.unlock();
            }
        } finally {
            first.lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        RankedLock left = new RankedLock(10);
        RankedLock right = new RankedLock(20);
        int[] counter = {0};

        Runnable forward = () -> {
            for (int i = 0; i < 10_000; i++) {
                withBoth(left, right, () -> counter[0]++);
            }
        };
        Runnable backward = () -> {
            for (int i = 0; i < 10_000; i++) {
                withBoth(right, left, () -> counter[0]++);
            }
        };

        Thread a = new Thread(forward, "forward");
        Thread b = new Thread(backward, "backward");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("counter = " + counter[0]);
    }
}
~~~

Lệnh chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 OrderedLocksDemo.java
java OrderedLocksDemo
~~~

Stdout:

~~~text
counter = 20000
~~~

**Tại sao đúng?**

1. **forward** truyền (left, right), **backward** truyền (right, left), nhưng cả hai đều khóa **rank 10 trước rank 20**.
2. Toàn bộ phép **counter[0]++** được thực hiện khi đã có quyền sở hữu cả hai khóa; các lần tăng không chồng lấn.
3. **finally** ở cả hai cấp bảo đảm nhả khóa được lấy thành công ngay cả khi action ném exception.
4. **join()** giữ main chờ cả hai thread xong trước khi đọc counter, nên stdout có giá trị xác định.
5. Nếu **a == b**, helper chỉ khóa một lần. Nếu hai khóa khác nhau nhưng rank bằng nhau, helper **từ chối** thay vì tự ý chọn thứ tự không nhất quán.

Trong hệ thống thật, không nên chỉ kiểm tra rank bằng nhau cho mỗi cặp rồi cho phép các đoạn code khác gán rank trùng lặp; phải định nghĩa **quy tắc cấp rank và quyền sở hữu tài nguyên** ở cấp thiết kế.

## 7. Ví dụ 2: chuyển tiền hai chiều với synchronized theo ID

Đây là bài toán phổ biến: chuyển tiền từ tài khoản A sang B phải giữ hai số dư nhất quán. Nếu mỗi thread khóa **tài khoản nguồn rồi tài khoản đích**, hai giao dịch ngược chiều dễ tạo A→B và B→A.

Ta áp đặt: **khóa tài khoản có ID nhỏ hơn trước, ID lớn hơn sau**, bất kể chiều chuyển tiền.

Tệp **OrderedTransferDemo.java**:

~~~java
public class OrderedTransferDemo {
    static final class Account {
        final long id;
        final Object monitor = new Object();
        long balance;

        Account(long id, long balance) {
            this.id = id;
            this.balance = balance;
        }
    }

    static boolean transfer(
            Account from, Account to, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (from == to) {
            return true;
        }
        if (from.id == to.id) {
            throw new IllegalArgumentException("ids must be unique");
        }

        Account first = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;

        synchronized (first.monitor) {
            synchronized (second.monitor) {
                if (from.balance < amount) {
                    return false;
                }

                from.balance -= amount;
                to.balance += amount;
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Account a = new Account(10, 1_000);
        Account b = new Account(20, 1_000);

        Thread ab = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                transfer(a, b, 1);
            }
        }, "a-to-b");

        Thread ba = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                transfer(b, a, 1);
            }
        }, "b-to-a");

        ab.start();
        ba.start();
        ab.join();
        ba.join();

        synchronized (a.monitor) {
            synchronized (b.monitor) {
                System.out.println("total = " + (a.balance + b.balance));
                System.out.println(
                    "nonnegative = "
                        + (a.balance >= 0 && b.balance >= 0)
                );
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderedTransferDemo.java
java OrderedTransferDemo
~~~

Stdout:

~~~text
total = 2000
nonnegative = true
~~~

**Giải thích:**

- Hai thread yêu cầu chuyển tiền **hai chiều**, nhưng mọi lần chuyển đều khóa **ID 10 rồi ID 20**.
- Bước kiểm tra số dư và cập nhật cả hai tài khoản nằm trong cùng vùng giữ hai monitor, nên **tổng tiền được bảo toàn** và không có tài khoản âm do thao tác chuyển có kiểm tra.
- Một số giao dịch có thể trả **false** khi tài khoản nguồn tạm hết tiền; số lần thành công và số dư từng tài khoản **không phải đầu ra xác định** dưới mọi lịch chạy. Chương trình cố ý chỉ in hai bất biến đúng trong mọi lần chạy bình thường.
- Đoạn in cuối khóa hai tài khoản theo cùng thứ tự, tránh tạo đường lấy khóa ngược chiều trong chính phần quan sát.
- **ID phải duy nhất và bất biến** cho mọi Account khác nhau được quản lý bởi quy tắc này. Trong chương trình minh họa, ID 10 và 20 thỏa điều kiện.

**Giới hạn:** Đây chỉ là trạng thái trong một JVM. Chuyển tiền thật cần transaction, số dư/ghi sổ bền vững, kiểm soát overflow, idempotency và chính sách xử lý lỗi. Monitor trong Java không bảo vệ được dữ liệu giữa nhiều process hoặc instance ứng dụng.

## 8. Cùng object, cùng rank và quy tắc tie-break

### Hai tham chiếu trỏ đến cùng một lock

Nếu **a == b**, khóa reentrant có thể được lấy nhiều lần bởi cùng thread, nhưng code phải nhả đủ số lần. Với helper khóa cặp, cách rõ nhất thường là **nhận ra cùng object và khóa một lần**.

Nếu một đối tượng tham gia hai vai trò trong cùng thao tác, cần xác định logic của thao tác đó, không chỉ thay đổi thứ tự khóa. Ví dụ chuyển tiền từ một tài khoản sang chính nó có thể là no-op, nhưng đó là **quy tắc nghiệp vụ**, không phải điều Java Lock tự quyết định.

### Hai object khác nhau nhưng cùng rank

Nếu hai khóa khác nhau có cùng rank, không thể nói “cứ khóa nhỏ trước” khi chưa định nghĩa tie-break. Hai thread có thể chọn thứ tự khác nhau tùy vào vị trí tham số.

Giải pháp:

- **Cấp ID độc nhất** cho mọi khóa trong cùng miền so sánh.
- Dùng **bộ so sánh toàn phần ổn định** trên các thuộc tính bất biến (ví dụ ID + loại tài nguyên, nếu cặp này thực sự duy nhất).
- Với những trường hợp buộc phải có giá trị so sánh trùng, dùng **một khóa phân xử chung (*tie lock*)** cho trường hợp trùng, hoặc thiết kế lại hệ thống cấp rank.

Không cố “chọn đại theo chiều truyền tham số” khi bằng rank vì nó tái tạo đúng lỗi hai thứ tự đối nghịch.

### Vì sao identityHashCode không luôn đủ?

**System.identityHashCode(object)** cung cấp giá trị hash liên quan identity, **không cam kết không va chạm** giữa hai object khác nhau. Nếu so hash để sắp xếp khóa, phải xử lý tình huống hash bằng nhau.

Đoạn sau là **mã minh họa giải pháp tie-lock**, không phải một ứng dụng hoàn chỉnh:

~~~java
private static final Object TIE_LOCK = new Object();

static void withPair(Object a, Object b, Runnable action) {
    if (a == b) {
        synchronized (a) {
            action.run();
        }
        return;
    }

    int ha = System.identityHashCode(a);
    int hb = System.identityHashCode(b);

    if (ha < hb) {
        synchronized (a) {
            synchronized (b) {
                action.run();
            }
        }
    } else if (ha > hb) {
        synchronized (b) {
            synchronized (a) {
                action.run();
            }
        }
    } else {
        synchronized (TIE_LOCK) {
            synchronized (a) {
                synchronized (b) {
                    action.run();
                }
            }
        }
    }
}
~~~

Mảnh code được đặt trong một class để biên dịch; action là thao tác giả định cần cả hai monitor. **TIE_LOCK** phải là **một đối tượng dùng chung** cho toàn bộ giao thức. Khi hash trùng, chỉ một thread có thể đồng thời đi vào đường tie, nên hai đường truyền tham số trái chiều không lấy hai monitor theo thứ tự đối nghịch song song. Khi dùng cách này, phải áp dụng nhất quán cho **mọi đường lấy các khóa có liên quan**; nếu code khác giữ a hoặc b rồi mới yêu cầu TIE_LOCK, vẫn có thể tạo vòng chờ.

Với thiết kế mới, một ID toàn cục duy nhất, bất biến thường dễ chứng minh hơn việc dựa vào identity hash và tie lock.

## 9. Trường hợp nhiều hơn hai khóa

Với ba hay nhiều khóa, nguyên tắc không thay đổi: **thu thập danh sách khóa, loại các reference trùng, sắp xếp theo thứ tự toàn cục, lấy từ thấp tới cao và nhả ngược lại**.

Ví dụ pseudocode:

~~~text
input: danh sách resource cần khóa
1. Xác minh ID/rank bất biến, không có hai resource khác nhau mang cùng rank.
2. Loại reference trùng hoặc gộp yêu cầu trên cùng resource.
3. Sort theo rank tăng dần.
4. Acquire lần lượt tất cả các lock.
5. Khi đã giữ đủ, kiểm tra và thay đổi bất biến nghiệp vụ.
6. Release đúng các lock thực sự đã acquire theo chiều ngược lại.
~~~

Khi áp dụng với **ReentrantLock**, dùng nested try/finally hoặc ghi nhận rõ các khóa đã lấy thành công trong một cấu trúc stack; nhả trong finally. Nếu acquisition của khóa thứ ba thất bại hoặc bị interrupt, phải nhả hai khóa đầu **mà thread thực sự đang giữ**.

Với **synchronized**, không có phương thức enter/exit tùy ý bằng danh sách runtime mà không tổ chức cấu trúc lồng nhau hoặc helper đệ quy. Nếu tự tạo helper đệ quy, đảm bảo cùng thứ tự với mọi đường vào khác và không có callback lấy thêm khóa rank thấp hơn.

### Khi danh sách khóa thay đổi động

Một thread đã giữ rank 50 rồi mới phát hiện nó cần rank 10 **không được lấy thêm rank 10 ngay**. Các lựa chọn tùy hợp đồng:

- Tính toán trước tập tài nguyên, rồi lấy đúng thứ tự.
- Nhả những khóa đang giữ, xây dựng lại danh sách, sắp xếp và thử lại. **Phải kiểm tra lại điều kiện nghiệp vụ** vì trạng thái có thể đã đổi sau khi nhả.
- Thiết kế API để caller không thể yêu cầu thêm khóa rank thấp trong lúc đang giữ rank cao.
- Dùng mô hình ownership/message passing nếu giao dịch cần nhiều tài nguyên động đến mức hierarchy trở nên khó quản lý.

Đừng tự coi việc nhả và lấy lại khóa như một giao dịch không có kẽ hở. **Nhả khóa** cho phép thread khác cập nhật dữ liệu; mọi snapshot đọc trước đó có thể đã lỗi thời.

## 10. Ví dụ 3: kiểm tra thứ bậc bằng fail-fast trong lúc phát triển

Trong ứng dụng lớn, lock hierarchy được ghi trong tài liệu có thể bị phá khi code mới gọi helper khác. Có thể xây dựng **runtime checker** để phát hiện thao tác lấy khóa sai thứ tự ngay khi chạy test.

Ví dụ sau chủ động áp dụng quy tắc **rank phải tăng nghiêm ngặt** cho các khóa được quản lý; checker **không cho phép lấy lại cùng rank**, dù ReentrantLock thuần có hỗ trợ reentrancy. Đây là chính sách của checker để dễ phát hiện vi phạm, không phải hạn chế của ReentrantLock.

Tệp **LockRankCheckerDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.ReentrantLock;

public class LockRankCheckerDemo {
    private static final ThreadLocal<Deque<Integer>> HELD =
            ThreadLocal.withInitial(ArrayDeque::new);

    static final class RankedLock {
        private final int rank;
        private final ReentrantLock lock = new ReentrantLock();

        RankedLock(int rank) {
            this.rank = rank;
        }

        void acquire() {
            Deque<Integer> held = HELD.get();
            if (!held.isEmpty() && rank <= held.peek()) {
                throw new IllegalStateException("lock order violation");
            }

            lock.lock();
            held.push(rank);
        }

        void release() {
            Deque<Integer> held = HELD.get();

            if (!lock.isHeldByCurrentThread()
                    || held.isEmpty()
                    || held.peek() != rank) {
                throw new IllegalStateException("invalid unlock order");
            }

            lock.unlock();
            held.pop();
            if (held.isEmpty()) {
                HELD.remove();
            }
        }
    }

    public static void main(String[] args) {
        RankedLock low = new RankedLock(10);
        RankedLock high = new RankedLock(20);

        low.acquire();
        try {
            high.acquire();
            try {
                System.out.println("ascending = allowed");
            } finally {
                high.release();
            }
        } finally {
            low.release();
        }

        high.acquire();
        try {
            try {
                low.acquire();
            } catch (IllegalStateException ex) {
                System.out.println("descending = rejected");
            }
        } finally {
            high.release();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LockRankCheckerDemo.java
java LockRankCheckerDemo
~~~

Stdout:

~~~text
ascending = allowed
descending = rejected
~~~

**Điểm cần hiểu:**

- **ThreadLocal<Deque<Integer>>** lưu stack rank mà **thread đang gọi** đã acquire qua checker.
- Mỗi lần acquire, rank mới phải **lớn hơn** rank đang ở đỉnh stack; nếu không, ném exception **trước khi cố lấy khóa**, tránh tự tạo vòng chờ ngay trong demo.
- Mỗi lần release yêu cầu đúng owner và đúng thứ tự LIFO; **finally** giúp cân bằng quyền sở hữu khóa.
- Sau khi thả lock cuối cùng, HELD.remove() tránh giữ ThreadLocal state không cần thiết ở thread có thể được tái sử dụng.
- Demo chỉ minh họa một checker đơn giản cho **quy tắc rank tĩnh và API đóng kín**. Nó không biết khóa được lấy trực tiếp bằng synchronized, ReentrantLock khác, callback bên ngoài hay tài nguyên giữa process; không nên xem nó như detector hoàn chỉnh cho mọi deadlock.

Nếu ứng dụng cần một thread lấy lại **cùng** khóa, checker thực tế phải phân biệt **reentrant same-object** với **different-object same-rank**, theo dõi identity và số mức giữ phù hợp. Không chỉ bỏ điều kiện rank bằng nhau nếu như vậy cho phép hai đối tượng khác nhau cùng rank bị khóa theo thứ tự tùy ý.

## 11. tryLock() và timeout: cách khác để không chờ vô hạn

**ReentrantLock.tryLock()** thử lấy khóa ngay và trả về boolean. **tryLock(timeout, TimeUnit)** có thể chờ tối đa một khoảng và ném InterruptedException khi bị ngắt. Nếu không lấy được khóa thứ hai, caller có thể **nhả khóa thứ nhất, chờ một khoảng phù hợp rồi thử lại**.

Nguyên tắc bắt buộc khi “all-or-none acquisition”:

1. Ghi nhận **những khóa đã thực sự lấy thành công**.
2. Không thực hiện side effect nghiệp vụ khi chưa đủ quyền sở hữu cần thiết.
3. Nếu một khóa không lấy được, nhả **toàn bộ khóa đã lấy** trong finally.
4. Nếu retry, làm lại kiểm tra điều kiện vì trạng thái có thể thay đổi khi khóa đã được nhả.
5. Cần giới hạn lượt thử, deadline hoặc đường hủy để tránh retry vô hạn trong tình trạng tranh chấp.

### Ví dụ 4: thất bại khi lấy khóa thứ hai và cleanup an toàn

Tệp **TryLockCleanupDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockCleanupDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock first = new ReentrantLock();
        ReentrantLock second = new ReentrantLock();
        CountDownLatch finished = new CountDownLatch(1);

        second.lock(); // Main cố ý giữ second khi worker thử lấy.
        try {
            Thread worker = new Thread(() -> {
                first.lock();
                try {
                    boolean gotSecond = second.tryLock();
                    try {
                        System.out.println(
                            "got second = " + gotSecond
                        );
                    } finally {
                        if (gotSecond) {
                            second.unlock();
                        }
                    }
                } finally {
                    first.unlock(); // Dù tryLock thất bại.
                    finished.countDown();
                }
            }, "worker");

            worker.start();
            finished.await();
            worker.join();
            System.out.println("first locked = " + first.isLocked());
        } finally {
            second.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TryLockCleanupDemo.java
java TryLockCleanupDemo
~~~

Stdout:

~~~text
got second = false
first locked = false
~~~

**Giải thích:** Main giữ second cho đến sau khi worker hoàn thành, nên tryLock(second) của worker phải trả false. Worker **không unlock second** vì nó chưa sở hữu; nó vẫn phải nhả first trong finally. Main chờ tín hiệu hoàn tất rồi join để đọc isLocked() khi worker đã nhả first, cho stdout xác định.

Ví dụ này minh họa cleanup khi acquisition thất bại, **không phải đề xuất thay mọi thứ tự khóa bằng tryLock**. Trong ứng dụng có nhiều worker cùng retry, nếu họ cùng giành được khóa đầu rồi cùng thất bại ở khóa sau, họ có thể liên tục nhả rồi tranh lại mà không có ai hoàn tất (**livelock**). Retry cần backoff/giới hạn/hủy thích hợp; **lock hierarchy vẫn thường là phương án dễ chứng minh hơn**.

### Interrupt có tự phá deadlock không?

- Thread chờ vào **synchronized monitor** không thể coi interrupt là cách lấy lại khóa hay ép chủ sở hữu nhả monitor.
- **ReentrantLock.lockInterruptibly()** cho phép bỏ việc *đang chờ lấy khóa* khi bị interrupt, nhưng không tự nhả những khóa thread đó **đã giữ**.
- **tryLock(timeout, unit)** giúp caller không chờ mãi ở một lần acquisition; caller vẫn phải chủ động cleanup các khóa trước đó.
- **Thread.interrupt()** là yêu cầu hợp tác, không phải lệnh cưỡng chế rollback hay mở khóa của thread khác.

Vì vậy, **phòng deadlock bằng thứ tự khóa nhất quán** là hướng chính khi bài toán cho phép áp dụng. Timeout và interrupt là các tính năng bổ sung cho điều khiển tiến độ và hủy an toàn.

## 12. Thứ tự khóa với synchronized, ReentrantLock và Condition

### synchronized

Khi dùng intrinsic monitor, vùng nested synchronized thể hiện rõ thứ tự yêu cầu:

~~~java
synchronized (lowerRankLock) {
    synchronized (higherRankLock) {
        // Critical section cần cả hai.
    }
}
~~~

Đây là đoạn minh họa trong một phương thức; hai biến phải là reference object khóa chung, đã được gán rank theo hợp đồng. Khi thoát scope, Java nhả monitor tương ứng kể cả có exception.

Không có API trực tiếp để đặt timeout cho **monitor enter** như tryLock(timeout). Vì vậy càng cần tránh các chuỗi khóa lồng nhau không có thứ tự.

### ReentrantLock

Dùng hai tầng try/finally:

~~~java
low.lock();
try {
    high.lock();
    try {
        update();
    } finally {
        high.unlock();
    }
} finally {
    low.unlock();
}
~~~

Đây là đoạn minh họa; low/high là các ReentrantLock đã xác định rank, update() là thao tác cần bảo vệ. Nếu high.lock() có exception bất thường trước khi acquire, finally bên ngoài vẫn nhả low. Trong trường hợp bình thường, thread lấy cả hai theo thứ tự ổn định rồi nhả ngược.

### Condition và việc tạm thời nhả khóa

**Condition.await()** cần thread hiện tại đang giữ ReentrantLock tương ứng; khi chờ, nó **nhả chính khóa liên kết với condition**, rồi lấy lại khóa trước khi trả về theo hợp đồng. Nó **không nhả mọi khóa khác** mà thread đang giữ.

Nếu đang giữ **low**, rồi **high**, sau đó gọi await() trên condition của **high**, thread có thể vẫn giữ low trong khi chờ điều kiện. Điều này có thể khiến thread khác cần low không thể thực hiện hành động giúp điều kiện high trở thành đúng. Quy tắc rank đơn giản vì thế **không thay thế phân tích giao thức await/signal, join hay callback**.

Ưu tiên thiết kế tránh giữ nhiều lock trong lúc chờ condition kéo dài, hoặc chứng minh rõ tín hiệu có thể được phát mà không cần những khóa đang bị giữ.

## 13. Deadlock, starvation, livelock và contention không giống nhau

| Hiện tượng | Mô tả | Lock hierarchy giải quyết đến đâu? |
| --- | --- | --- |
| **Deadlock** | Các thread tạo vòng chờ, không thể tiếp tục theo giao thức hiện tại | Ngăn vòng chờ do các khóa tuân thủ rank, không ngăn mọi loại deadlock do tài nguyên khác |
| **Starvation** | Một thread liên tục không được cấp CPU/khóa/tài nguyên trong khi thread khác tiến bộ | Không bảo đảm fairness hoặc thời gian chờ hữu hạn |
| **Livelock** | Thread liên tục phản ứng, retry/nhả khóa nhưng không hoàn thành công việc hữu ích | Không tự ngăn lỗi retry thiếu chính sách |
| **Contention** | Nhiều thread muốn cùng khóa nên một số phải chờ | Vẫn có, ngay cả khi thứ tự đúng |

Một chương trình tránh deadlock vẫn có thể chậm do tranh chấp khóa, starvation hoặc giữ khóa quá lâu. Với ReentrantLock, **fair=true** có các quy tắc ưu tiên nhất định nhưng không bảo đảm lịch CPU công bằng tuyệt đối; **tryLock()** không timeout còn có thể vượt hàng ngay cả khi lock được tạo fair.

Không nên viết bài test “không bị treo trong một giây nên không có deadlock”. Một lịch gây vòng chờ có thể chưa xuất hiện trong bài test đó. Phải xem **mọi thứ tự khóa có thể xảy ra** và lập luận từ cấu trúc chương trình.

## 14. Lock hierarchy khi gọi helper, callback và thư viện

Một trong những nguồn vi phạm hierarchy là một phương thức “vô hại” thực ra tự lấy thêm khóa:

~~~text
ServiceA.process():
  giữ lock(rank 30)
  gọi ServiceB.validate()
    -> ServiceB lấy lock(rank 10)
       => VI PHẠM 30 -> 10
~~~

Đôi khi callback hoặc phương thức override chạy dưới một lock lại gọi ngược về lớp đang giữ khóa khác, tạo **lock inversion** khó thấy trong code gọi trực tiếp. Hãy:

- Ghi rõ **lock rank** trong tài liệu của những API có khóa.
- Tránh gọi callback, hook, logger tùy biến, code plugin hoặc I/O bên ngoài khi đang giữ lock nếu không kiểm soát được khóa mà chúng sử dụng.
- Hạn chế **nested locks** bằng cách tổ chức lại quyền sở hữu dữ liệu hoặc lấy snapshot immutable trước khi gọi code ngoài.
- Với một thao tác cần nhiều tài nguyên, thu thập **đủ tập khóa** từ đầu rồi điều phối tập đó qua một helper duy nhất.
- Dùng checker trong test để phát hiện các lần acquire sai rank; không dựa vào mỗi lần stress test “chạy ổn”.

**Không có thứ tự khóa tự động cho mọi thư viện Java**. Một ReentrantLock tự tạo không biết rằng “rank của tôi là 10”; JVM không tự phát hiện việc dùng nó sai thứ tự. Rank chỉ có hiệu lực khi mọi đường sử dụng tuân thủ hợp đồng mà bạn thiết kế.

### Không để rank thay đổi sau khi khóa đã được công bố

Nếu rank lấy từ số dư, mức ưu tiên của task, thời gian tạo hoặc trường mutable, hai thread có thể sắp xếp cặp khóa khác nhau tại các thời điểm khác nhau. Rank của lock nên là thuộc tính **bất biến**; khi cần thay đổi cấu trúc nghiệp vụ, phải có giao thức tái cấu hình an toàn.

### Khóa theo ID không giải quyết dữ liệu giữa nhiều JVM

Hai JVM có thể có hai object lock riêng dù đại diện cùng account ID. Thứ tự khóa trên Java object trong JVM A **không loại trừ** các cập nhật từ JVM B. Với database, distributed storage hoặc tài nguyên từ xa, cần transaction/optimistic concurrency/lock của nơi lưu trữ thích hợp. Lock hierarchy cục bộ vẫn có ích để tránh deadlock **bên trong** mỗi JVM, nhưng không thay thế giao thức đồng bộ giữa tiến trình.

## 15. Thiết kế API để không thể lấy khóa sai thứ tự

Một API tốt giảm khả năng người gọi phải tự nhớ thứ tự:

- Đóng gói các lock thành **private final** field; tránh trả trực tiếp ReentrantLock ra ngoài để mọi nơi tự acquire tùy ý.
- Tạo một phương thức giao dịch như **transfer(from, to, amount)** hoặc **withLocks(resources, action)**; nó sắp xếp ID, lấy khóa, thực hiện hành động rồi nhả.
- Nếu cho phép nested lock, thiết kế thứ bậc và các method của từng tầng rõ ràng.
- Dùng immutable object/copy-on-write hoặc truyền thông điệp khi có thể tránh shared mutable state.
- Phân biệt trạng thái **đã khóa đủ** với trạng thái **đang tìm cách lấy** để không thực hiện side effect sớm.

Nếu một thao tác phải khóa danh sách đối tượng có thể thay đổi do thread khác tác động, lấy một snapshot của danh sách **chưa đủ** nếu đối tượng có thể bị thêm/bớt và bất biến áp dụng cho toàn bộ tập. Cần một giao thức bảo vệ **cả danh sách thành viên** (ví dụ khóa cấp cao hơn hoặc version và kiểm tra lại dưới khóa). Lock ordering là một phần của giải pháp, không tự giải quyết consistency của topology động.

## 16. Chẩn đoán deadlock trong Java

Khi nghi ngờ deadlock do monitor hoặc ownable synchronizer:

1. **Thu thread dump** khi hệ thống có dấu hiệu mắc kẹt. Có thể dùng các công cụ JDK như **jcmd <pid> Thread.print**, **jstack <pid>** trong môi trường cho phép.
2. Tìm những thread đang giữ monitor/lock nào, đang đợi lock nào; so sánh các stack trace có nested synchronized hoặc ReentrantLock acquisition.
3. Vẽ **wait-for graph**: thread A chờ tài nguyên do thread B giữ, B chờ C, C chờ A.
4. Kiểm tra **đường gọi** nào tạo cạnh lấy khóa theo chiều ngược hierarchy.
5. Sửa tại thiết kế: thống nhất thứ tự và API acquisition; không chỉ tăng timeout hay thêm log/sleep.
6. Thêm regression test cho cặp thao tác đảo tham số (A→B và B→A), xác nhận bất biến sau khi tất cả worker đã join.

**ThreadMXBean** cung cấp những phương thức như **findDeadlockedThreads()** để tìm chu trình deadlock trên object monitors hoặc ownable synchronizers mà JVM có thể phát hiện. Kết quả null không chứng minh chương trình không có deadlock ở thời điểm khác hoặc ở tài nguyên ngoài phạm vi quan sát. Một thread dump cũng có thể thiếu quyền truy cập/không ghi nhận tài nguyên ngoài JVM như database locks.

### Thử nghiệm không tạo deadlock cố ý

Một test có thể khởi chạy nhiều thread dùng helper sắp xếp khóa, sau đó **join với timeout** và assert các bất biến. Timeout giúp phát hiện việc test có thể đang treo; nó không tự sửa worker. Nếu test timeout, nên thu stack/lock info để chẩn đoán, rồi đảm bảo test không giữ non-daemon thread vĩnh viễn làm nghẽn cả test suite.

Các ví dụ runnable trong bài này tránh chương trình deadlock không có đường thoát. Muốn nghiên cứu lịch lỗi, nên dùng các môi trường/thử nghiệm cô lập và cơ chế dừng an toàn; không đưa mẫu deadlock vô hạn vào đường chạy mặc định của ứng dụng.

## 17. Bảng lỗi phổ biến

| Lỗi thiết kế | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| T1 lấy A→B, T2 lấy B→A | Vòng chờ hai khóa | Thống nhất A→B ở mọi đường |
| Sắp xếp theo tham số đầu vào | Hai lời gọi đảo chiều có thể khóa ngược | Sắp theo ID/rank bất biến, không theo tham số |
| Rank thay đổi trong runtime | Hai thread có thể thấy thứ tự khác nhau | Gán rank ổn định theo hợp đồng |
| Hai khóa khác nhau cùng rank nhưng không tie-break | Không có thứ tự toàn phần | ID duy nhất hoặc giao thức tie lock |
| Tin identityHashCode không bao giờ collision | Có thể rơi vào đường xử lý thứ tự không xác định | Thiết kế tie-break an toàn |
| Một method lấy thêm khóa rank thấp dưới khóa rank cao | Vi phạm hierarchy ẩn trong helper | Đóng gói API, kiểm tra toàn call graph |
| Không nhả khóa đã lấy khi tryLock thứ hai thất bại | Giữ tài nguyên, tăng nguy cơ deadlock | finally nhả mọi phần đã acquire |
| Chạy nghiệp vụ trước khi đủ toàn bộ khóa | Side effect dở dang khi acquisition thất bại | Chỉ thực thi sau khi acquire đủ và kiểm tra invariant |
| Đợi join/await khi giữ khóa người khác cần | Có thể tạo vòng chờ ngoài việc giành lock | Phân tích dependency, tránh giữ khóa khi chờ |
| Dùng sleep/yield để “phá” deadlock | Không nhả khóa hay bảo đảm progress | Đổi lock order/giao thức |
| Bắt InterruptedException rồi bỏ qua và giữ khóa | Không có đường cleanup/hủy đúng | Xử lý interrupt và finally an toàn |
| Thấy getState() không BLOCKED nên kết luận không deadlock | ReentrantLock có cơ chế chờ khác monitor | Đọc lock owner/wait-for graph, dump |
| Dùng lock hierarchy trong một JVM để bảo vệ DB nhiều instance | Không có mutual exclusion liên tiến trình | Đồng bộ tại nơi dữ liệu được chia sẻ |
| Chỉ test chạy một lần không treo | Lịch gây cycle có thể chưa xảy ra | Chứng minh order + test đảo chiều + diagnostic |

## 18. Checklist cho code review

**Thiết kế:**

- [ ] Mỗi lock có **vai trò và rank/ID** rõ ràng, ổn định, phân biệt được khi cần.
- [ ] Mọi nested acquisition đều đi theo **một chiều tăng**, không có helper/callback âm thầm đi ngược.
- [ ] Nếu hai reference trỏ cùng object, có đường xử lý rõ; nếu khác object nhưng rank trùng, có tie-break đúng.
- [ ] Những bước thay đổi nhiều dữ liệu chung nằm trong critical section bảo vệ **toàn bộ invariant**.
- [ ] Không giữ một lock thấp trong lúc chờ sự kiện chỉ có thể xảy ra khi thread khác lấy được lock đó.

**Triển khai:**

- [ ] Với ReentrantLock, mỗi lần acquire thành công có **finally unlock** cùng thread, đúng số lần.
- [ ] Với tryLock thất bại/interrupt, nhả mọi khóa đã giữ và không tạo side effect nghiệp vụ quá sớm.
- [ ] Khi nhả rồi retry, đọc lại trạng thái và giới hạn retry/backoff theo yêu cầu.
- [ ] Không gọi I/O/callback hoặc giữ monitor trong lúc ngủ dài nếu không thật sự cần cho bất biến.
- [ ] Không sửa rank hay đối tượng lock sau khi đã công bố cho các thread khác.

**Kiểm thử & vận hành:**

- [ ] Có test hai chiều A→B và B→A, xác nhận tiến độ và bất biến.
- [ ] Có cách thu thread dump/ThreadMXBean nếu bị chặn.
- [ ] Có đường xử lý lỗi, timeout và cleanup phù hợp, không thay chúng bằng lịch chạy đoán trước.
- [ ] Nêu rõ phạm vi **một JVM** của các Java locks và ranh giới DB/tài nguyên ngoài tiến trình.

## 19. Tự kiểm tra

**Câu 1.** Tại sao T1 lấy A rồi B và T2 lấy B rồi A có thể deadlock?  
**Trả lời:** Hai thread có thể mỗi người giữ một khóa, đồng thời chờ khóa do người kia giữ. Đó là circular wait.

**Câu 2.** Quy tắc lấy khóa rank tăng dần loại bỏ điều kiện nào của deadlock?  
**Trả lời:** Loại bỏ **circular wait** trong tập khóa được quản lý đúng bởi quy tắc đó.

**Câu 3.** Nếu cả hai hàm transfer(A,B) và transfer(B,A) đều khóa account có ID nhỏ hơn trước, deadlock kiểu A↔B còn xảy ra không?  
**Trả lời:** Không do cặp monitor ấy theo hai chiều đối nghịch, nếu mọi đường lấy các monitor liên quan đều tuân thủ cùng thứ tự. Các tài nguyên khác vẫn cần phân tích riêng.

**Câu 4.** Vì sao không dùng System.identityHashCode làm rank duy nhất mặc nhiên?  
**Trả lời:** Hai object khác nhau vẫn có thể có cùng identity hash. Cần tie-break ổn định.

**Câu 5.** Khi đã giữ rank 30 nhưng phát hiện cần rank 10, nên làm gì?  
**Trả lời:** Không lấy tiếp rank 10 dưới rank 30. Có thể nhả, xác định lại tập tài nguyên, sắp xếp rồi acquire và kiểm tra lại trạng thái; hoặc thiết kế lại API.

**Câu 6.** tryLock(second) trả false khi đang giữ first. Có được tiếp tục cập nhật dữ liệu đòi cả hai lock không?  
**Trả lời:** Không. Phải nhả first và xử lý thất bại/retry theo giao thức, trừ khi nghiệp vụ có một phương án được chứng minh không cần second.

**Câu 7.** Fair ReentrantLock có thay thế lock hierarchy không?  
**Trả lời:** Không. Fairness không phá vòng chờ giữa các khóa khác nhau.

**Câu 8.** Condition.await() có nhả mọi khóa thread đang giữ không?  
**Trả lời:** Không. Nó chỉ nhả khóa liên kết với Condition theo hợp đồng; các khóa khác vẫn có thể bị giữ trong lúc chờ.

**Câu 9.** Một hệ thống không deadlock vẫn có thể chậm hoặc treo tiến độ vì sao?  
**Trả lời:** Có thể do contention, starvation, livelock, I/O hoặc chính sách chờ khác; tránh vòng chờ không hứa tiến độ hữu hạn.

**Câu 10.** Vì sao Java ReentrantLock giữa hai JVM không bảo vệ cùng một tài khoản trong DB?  
**Trả lời:** Hai process sở hữu các lock object khác nhau. Cần cơ chế đồng bộ ở tầng kho dữ liệu chung.

## 20. Tổng kết

**Lock hierarchy** là phương pháp phòng deadlock bằng cách áp đặt **một thứ tự toàn cục, ổn định khi lấy nhiều khóa**: sắp theo rank/ID, acquire từ thấp đến cao, release theo chiều ngược, xử lý object trùng và tie-break rõ ràng. Nó giải quyết vòng chờ do **thứ tự khóa đối nghịch**, nhưng không tự bảo đảm fairness, không loại bỏ mọi contention, và không tự giải quyết chờ condition, callback, I/O hay tài nguyên giữa các JVM.

Trong Java, hãy đóng gói các đoạn lấy nhiều monitor hoặc ReentrantLock vào API kiểm soát thứ tự, dùng **finally** để nhả mọi khóa thực sự sở hữu, kiểm tra lại invariant khi có retry, và kiểm chứng bằng test đảo chiều cùng thread dump khi cần. Cách tiếp cận đúng bắt đầu từ **đồ thị phụ thuộc khóa và bất biến dữ liệu**, không phải từ sleep, yield hay kỳ vọng scheduler sẽ may mắn chọn lịch không lỗi.
