# Atomic không thay thế giao dịch nhiều đối tượng trong Java Concurrency

Trong Java, các lớp như `AtomicInteger`, `AtomicLong`, `AtomicBoolean` và `AtomicReference` cung cấp **thao tác nguyên tử trên một đơn vị trạng thái cụ thể**. Ví dụ, `incrementAndGet()` không mất lượt tăng; `compareAndSet(expected, update)` chỉ cập nhật khi giá trị hiện tại khớp expected. Nhưng nếu một nghiệp vụ phải sửa **hai tài khoản, hai trường liên quan hoặc nhiều object khác nhau**, từng phép cập nhật atomic riêng lẻ **không tự biến toàn bộ quy trình thành một giao dịch nguyên tử**.

Một phép chuyển tiền là ví dụ rõ nhất: trừ tiền ở A và cộng tiền ở B phải cùng nhau tạo nên một trạng thái hợp lệ. Nếu thread khác nhìn thấy giữa hai bước, tổng tiền tạm thời giảm. Nếu có exception hoặc JVM dừng sau bước trừ, tổng có thể sai lâu dài. Dùng hai `AtomicLong` không giải quyết ranh giới giao dịch ấy.

Bài học thuộc **Atomic & CAS trong Java Concurrency nói chung**. Nội dung phân biệt tính nguyên tử của từng biến với transaction nhiều object; hướng dẫn dùng một vùng khóa chung, khóa nhiều object có thứ tự, hoặc gộp state bất biến vào một `AtomicReference`. Các cơ chế tích hợp riêng của Spring không nằm trong phạm vi.

## 1. Atomic là gì, và phạm vi bảo đảm nằm ở đâu?

`java.util.concurrent.atomic` chứa các primitive phục vụ lập trình đồng thời. Một số ví dụ:

| API | Phép toán nguyên tử điển hình | Đơn vị được bảo vệ |
| --- | --- | --- |
| `AtomicInteger.incrementAndGet()` | Đọc–sửa–ghi một số nguyên không bị lost update do contender cùng thao tác trên atomic ấy. | Một `AtomicInteger`. |
| `AtomicLong.addAndGet(delta)` | Cộng vào một biến atomic và trả về giá trị mới. | Một `AtomicLong`. |
| `AtomicBoolean.compareAndSet(false, true)` | Chuyển cờ nếu giá trị hiện tại còn false. | Một `AtomicBoolean`. |
| `AtomicReference<T>.compareAndSet(old, next)` | Thay **reference** nếu còn là expected reference. | Một reference atomic. |
| `AtomicReference<T>.getAndUpdate(fn)` | Thử cập nhật một reference theo hàm, có thể thực thi lại hàm khi tranh chấp. | Một reference atomic; không tự bảo vệ side effect của fn. |
| `AtomicIntegerArray` | Các thao tác nguyên tử **trên từng phần tử** được chỉ định. | Một phần tử tại một chỉ số mỗi lần thao tác. |

Các thao tác atomic tiêu chuẩn còn có **memory effects** theo hợp đồng Java Memory Model. Tuy nhiên có ba tầng correctness cần xét riêng:

1. **Atomicity:** một thao tác RMW riêng lẻ có bị mất cập nhật hay không?
2. **Visibility/ordering:** các thread quan sát phép ghi theo quan hệ đồng bộ/happens-before nào?
3. **Invariant liên biến/liên đối tượng:** nhiều giá trị có cùng phản ánh **một trạng thái nghiệp vụ hợp lệ** không?

Một chương trình có thể đạt (1) và (2) cho từng atomic variable nhưng **vẫn không đạt (3)** cho toàn bộ nghiệp vụ.

### 1.1 Giao dịch là một hợp đồng lớn hơn một instruction CAS

Trong bài này, “giao dịch” theo nghĩa *một operation logic toàn vẹn* phải có đặc tính tối thiểu:

- **All-or-nothing về trạng thái được bảo vệ:** các bước phụ thuộc phải được quan sát như một thay đổi duy nhất, hoặc không có bước nào được commit.
- **Invariant được giữ:** ví dụ `balanceA + balanceB == total`.
- **Isolation ở ranh giới quan sát đã định:** người đọc không được lấy nửa trạng thái cũ và nửa trạng thái mới nếu hợp đồng yêu cầu snapshot nhất quán.
- **Exception/cancellation safety:** lỗi ở giữa không được để object ở trạng thái vi phạm invariant.

Đây **không mặc nhiên là ACID transaction của database**. Atomicity trong bộ nhớ một JVM khác với durability qua JVM crash, hai process, database hoặc remote service. Phân biệt phạm vi ngay từ đầu để tránh dùng sai cơ chế.

## 2. Ví dụ kinh điển: hai AtomicLong vẫn có khoảng hở

Giả sử hai tài khoản nội bộ có tổng 100 đơn vị:

~~~java
AtomicLong accountA = new AtomicLong(100);
AtomicLong accountB = new AtomicLong(0);

accountA.addAndGet(-30);
accountB.addAndGet(30);
~~~

Từng `addAndGet` là atomic **trên chính biến đó**. Nhưng cả hai phép cộng/trừ là **hai điểm cập nhật khác nhau**. Trong khoảng giữa chúng, state thật sự có thể là:

~~~text
Trước:  A=100, B=0,  A+B=100
Giữa:  A=70,  B=0,  A+B=70
Sau:    A=70,  B=30, A+B=100
~~~

Một thread đọc báo cáo tài sản đúng lúc giữa hai bước thấy tổng 70. Nó không phải “đọc cache lỗi thời”; đó là một **trạng thái trung gian có thật** mà giao thức cho phép quan sát.

Tình huống còn nguy hiểm hơn nếu exception xuất hiện sau debit nhưng trước credit. Việc cả hai field là atomic không tạo cơ chế rollback, không làm việc cộng bên B tự diễn ra khi bước trừ A đã thành công.

## 3. Chương trình Java 17+: tái hiện lỗi một cách xác định

Thay vì dựa vào một vòng stress test may rủi bắt được interleaving, sử dụng hai `CountDownLatch` để tạm dừng thread chuyển tiền ngay sau bước trừ.

Tạo tệp `AtomicTransferGapDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicTransferGapDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger accountA = new AtomicInteger(100);
        AtomicInteger accountB = new AtomicInteger(0);
        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch continueTransfer = new CountDownLatch(1);

        Thread transfer = new Thread(() -> {
            boolean success = accountA.compareAndSet(100, 70);
            if (!success) {
                throw new AssertionError("Unexpected starting balance");
            }
            debited.countDown();
            try {
                continueTransfer.await();
                accountB.addAndGet(30);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "transfer");

        transfer.start();
        debited.await();

        try {
            System.out.println("During: A=" + accountA.get()
                    + ", B=" + accountB.get()
                    + ", total=" + (accountA.get() + accountB.get()));
        } finally {
            continueTransfer.countDown();
        }

        transfer.join();
        System.out.println("After: A=" + accountA.get()
                + ", B=" + accountB.get()
                + ", total=" + (accountA.get() + accountB.get()));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac AtomicTransferGapDemo.java
java AtomicTransferGapDemo
~~~

Stdout trong điều kiện bình thường, không có external interruption:

~~~text
During: A=70, B=0, total=70
After: A=70, B=30, total=100
~~~

**Vì sao output có thể xác định?** Thread transfer đã hoàn thành CAS trừ tiền và báo `debited.countDown()`. Main gọi `debited.await()` rồi đọc hai atomic, trong khi transfer chưa thể cộng vào B do `continueTransfer.await()`. Main mở cổng trong `finally` rồi chờ bằng `join()`. Latch phục vụ **kiểm soát thời điểm thử nghiệm**, không phải cơ chế giao dịch.

Ngay cả khi `accountA.compareAndSet` là một CAS có điều kiện đúng, CAS đó **không bao phủ biến accountB**. Thêm `volatile`, `get()` nhiều lần hoặc `Thread.sleep()` không biến hai phép cập nhật thành một operation.

**Lưu ý phạm vi demo:** nếu thread transfer bị interrupt bên ngoài trong lúc đợi latch, đoạn ví dụ có thể bỏ qua bước credit. Đó chính là một kiểu failure window mà production code phải xử lý; không lấy ví dụ lỗi làm mã nghiệp vụ an toàn.

## 4. CAS bảo vệ một precondition nhưng không commit nhiều object

Có thể sửa rủi ro “rút tiền vượt số dư” trên riêng A bằng vòng CAS:

~~~java
boolean withdraw(AtomicLong balance, long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    while (true) {
        long current = balance.get();
        if (current < amount) {
            return false;
        }
        if (balance.compareAndSet(current, current - amount)) {
            return true;
        }
    }
}
~~~

Đây là **mảnh method Java**, giả định import `AtomicLong`; nó biên dịch khi được đặt trong class phù hợp. Phép CAS giữ được điều kiện không trừ dưới 0 đối với **một balance**, nếu mọi đường ghi balance dùng cùng giao thức. Nhưng nếu sau đó chuyển tiền bằng:

~~~java
if (withdraw(accountA, 30)) {
    accountB.addAndGet(30);
}
~~~

thì giữa hai hành động vẫn tồn tại khoảng hở. CAS trên A chỉ là **điểm tuyến tính hóa của withdraw**, không phải điểm tuyến tính hóa của **transfer A→B**.

### 4.1 Nguyên tắc ranh giới commit

Khi operation gồm nhiều thay đổi, phải trả lời:

- Khi nào có thể nói “transfer đã thành công”?
- Thread khác có được phép đọc cả hai tài khoản trong lúc transfer chưa hoàn tất không?
- Nếu credit thất bại, có rollback được debit không? Nếu rollback lại gặp tranh chấp thì sao?
- Nếu process chết giữa chừng, trạng thái có được khôi phục không?
- Những method nào khác sửa A/B? Chúng có cùng protocol không?

Nếu không thể chỉ ra một ranh giới commit bảo vệ toàn bộ invariant, việc bổ sung thêm AtomicInteger/AtomicLong không giải quyết được nguyên nhân gốc.

## 5. Atomic field riêng lẻ và snapshot nhất quán là hai bài toán khác nhau

Cả hai đoạn đọc sau đều **không bảo đảm** một snapshot tuyến tính hóa của cặp tài khoản khi writer đang cập nhật chúng độc lập:

~~~java
long a = accountA.get();
long b = accountB.get();
long total = a + b;
~~~

hoặc:

~~~java
long a1 = accountA.get();
long b = accountB.get();
long a2 = accountA.get();
if (a1 == a2) {
    // Không phải bằng chứng tổng quát rằng cả a và b cùng một phiên bản.
}
~~~

Đây là **mảnh code minh họa**, giả định hai atomic đã được tạo. Trong đoạn thứ hai, A có thể thay đổi rồi quay về giá trị ban đầu (**ABA**), hoặc B đổi độc lập trong lúc A không đổi. So sánh hai lần đọc A không xác nhận một giao dịch tổng thể đã xảy ra hay chưa.

**Snapshot consistency** đòi hỏi tất cả giá trị quan trọng được lấy từ **một trạng thái logic**. Một số cách đạt được:

1. Một `synchronized`/`ReentrantLock` chung bảo vệ mọi writer và reader của invariant.
2. Một immutable aggregate state, publish qua `AtomicReference<State>` và reader đọc **một reference**.
3. Một protocol versioned snapshot/seqlock được thiết kế rất cẩn thận (khó hơn nhiều, có khả năng retry/starvation, không thích hợp nếu tự viết tùy tiện).
4. Transaction của nơi lưu dữ liệu nếu state nằm ngoài một JVM.

Nếu yêu cầu nghiệp vụ chỉ cần số liệu gần đúng (ví dụ dashboard metrics), snapshot tạm lệch có thể chấp nhận. Nhưng nếu ra quyết định rút tiền, cấp quota hoặc kiểm tra invariant tài chính, phải xác định consistency contract chặt hơn.

## 6. Đúng hướng 1: một owner và một critical section chung

Khi hai balance thuộc **cùng một owner object** trong một JVM, giải pháp dễ hiểu nhất thường là một lock bảo vệ cả hai.

Ý tưởng:

~~~java
synchronized (lock) {
    if (accountA >= amount) {
        accountA -= amount;
        accountB = Math.addExact(accountB, amount);
    }
}
~~~

Đây là mảnh minh họa, chưa xử lý toàn bộ validation và exception safety. Cần **tính/validate giá trị đích trước khi mutate** vì `Math.addExact` có thể ném exception; nếu trừ A xong mới gọi `addExact` rồi xảy ra overflow, state bị dở dang khi monitor được nhả.

Mẫu an toàn hơn:

~~~java
synchronized (lock) {
    if (accountA < amount) {
        return false;
    }
    long nextA = accountA - amount;
    long nextB = Math.addExact(accountB, amount);

    accountA = nextA;
    accountB = nextB;
    return true;
}
~~~

Đoạn trên nằm trong method trả `boolean`, giả định `amount > 0` đã được kiểm tra. Các phép tính có thể throw được thực hiện trước commit; sau đó chỉ còn phép gán primitive. Mọi reader cần đọc cả A và B **dưới cùng lock**, vì trong nội bộ critical section vẫn có hai phép gán liên tiếp.

### 6.1 Chương trình Java 17+ có thể chạy độc lập

Tạo tệp `LockedTransferDemo.java`:

~~~java
public final class LockedTransferDemo {
    private record Snapshot(long accountA, long accountB) {
        long total() {
            return Math.addExact(accountA, accountB);
        }
    }

    private static final class Ledger {
        private final Object lock = new Object();
        private long accountA = 100;
        private long accountB;

        boolean transfer(boolean fromA, long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            synchronized (lock) {
                long from = fromA ? accountA : accountB;
                long to = fromA ? accountB : accountA;
                if (from < amount) {
                    return false;
                }

                long nextFrom = from - amount;
                long nextTo = Math.addExact(to, amount);
                if (fromA) {
                    accountA = nextFrom;
                    accountB = nextTo;
                } else {
                    accountB = nextFrom;
                    accountA = nextTo;
                }
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(accountA, accountB);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                if (!ledger.transfer(true, 1)
                        || !ledger.transfer(false, 1)) {
                    throw new AssertionError("Transfer unexpectedly failed");
                }
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot s = ledger.snapshot();
        System.out.println("A=" + s.accountA());
        System.out.println("B=" + s.accountB());
        System.out.println("Total=" + s.total());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac LockedTransferDemo.java
java LockedTransferDemo
~~~

Stdout khi không có external interruption:

~~~text
A=100
B=0
Total=100
~~~

Mỗi thread thực hiện 100 cặp chuyển 1 đơn vị A→B rồi B→A. Vì mỗi thread chỉ chuyển về sau khi đã chuyển đi, tổng số lượt A→B đã commit không thể nhỏ hơn số lượt B→A đã commit; B có đủ cho mỗi lượt chuyển về. Trong thời gian chạy, số dư A và B có thể thay đổi, nhưng **mọi snapshot lấy qua `ledger.snapshot()`** giữ tổng bằng 100 và không có balance âm.

Các điểm quan trọng:

- `Ledger` sở hữu **cả hai balance**. Caller không thể tự sửa một tài khoản qua reference public.
- `transfer` gồm kiểm tra số dư, kiểm tra overflow và cập nhật **hai trường dưới một lần lock**.
- `snapshot` lấy **cùng lock**, trả immutable record. Reader không ghép hai phiên bản.
- Cả phép tính `Math.addExact` nằm **trước** commit. Nếu phép tính throw, state cũ còn nguyên.
- `Thread.join()` giúp main nhận biết hai worker đã kết thúc; trong ví dụ này không có operation expected-to-fail.
- Output cuối cùng xác định, nhưng ví dụ cũng dạy **cách đọc snapshot ở mọi thời điểm**, chứ không chỉ đo tổng cuối.

**Không nên mặc định một `synchronized` lock toàn ứng dụng**. Lock nên thuộc owner của đúng invariant; các state không liên quan có thể có owner riêng để tránh contention vô ích.

## 7. Đúng hướng 2: khóa nhiều object theo thứ tự toàn cục

Đôi khi mỗi `Account` phải là một object độc lập, không thể gộp tự nhiên vào một ledger duy nhất. Muốn transfer hai object, cần một protocol khóa **đồng thời cả hai** và yêu cầu mọi code liên quan tuân thủ nó.

Nếu thread T1 khóa A→B và T2 khóa B→A, cả hai có thể deadlock. Cần quy tắc nhất quán, thường là theo **ID duy nhất, bất biến**, không phụ thuộc hướng chuyển:

~~~java
Account first = from.id < to.id ? from : to;
Account second = from.id < to.id ? to : from;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Kiểm tra số dư from và cập nhật cả from/to.
    }
}
~~~

Đây là mảnh mã minh họa. `Account` cần `id` không trùng, `lock` private/được protocol kiểm soát, `balance` và các method liên quan. Cần xử lý trường hợp `from == to`, ID trùng, amount không hợp lệ và overflow; không lấy snippet như một class production hoàn chỉnh.

### 7.1 Điều kiện để đúng thật sự

Không chỉ riêng method transfer phải tuân thủ order:

1. Bất kỳ writer nào sửa balance của một account cũng phải giữ **lock của account ấy**.
2. Một operation ảnh hưởng hai account cần giữ **cả hai lock** theo order ổn định.
3. Một reader yêu cầu **snapshot của cặp account** cũng phải lấy cả hai lock cùng protocol. Đọc từng account qua getter synchronized riêng vẫn có thể lấy từ hai thời điểm khác nhau.
4. Không truyền lock ra ngoài cho code không kiểm soát; callback có thể tự lấy lock ngược thứ tự.
5. Thực hiện validation và tính toán trước khi commit, tránh exception giữa debit và credit.
6. Nếu amount hoặc tổng có khả năng overflow, dùng kiểu số học và kiểm tra miền thích hợp.

Một transfer có hai điểm gán Java bên trong nested synchronized không phải một instruction CPU. Nhưng **đối với tất cả observer tuân thủ lock protocol**, thao tác có thể được xem như một operation nguyên tử; bên ngoài không thể xen vào để quan sát trạng thái trung gian.

### 7.2 Đơn vị khóa và scalability

Khóa hai account có thể cho các giao dịch trên **hai cặp không liên quan** chạy đồng thời. Đó là lợi ích so với một global ledger lock. Đổi lại:

- Logic lock order phức tạp hơn.
- Dễ phát sinh deadlock khi các operation ba hoặc nhiều account chen nhau.
- Snapshot toàn bộ hệ thống phải phối hợp nhiều lock, tốn thời gian.
- Quy tắc ownership và ngoại lệ phải được review trên mọi call path.

Chọn đa lock khi **nhu cầu song song và số lượng object** đủ để biện minh. Không tách lock chỉ vì “đang dùng atomic”, khi hệ thống chưa có giải pháp đọc snapshot đồng nhất.

## 8. Đúng hướng 3: gộp cả invariant vào immutable state rồi CAS một reference

Nếu một nhóm field có thể quản lý như **một state bất biến**, `AtomicReference<State>` cho phép thay **toàn bộ snapshot** bằng một CAS. Đây là cách dùng atomic để đạt một dạng transaction nhiều field **sau khi đã tái thiết kế chúng thành một đơn vị atomic duy nhất**.

~~~text
State old = (A=100, B=0)
      |
      | tạo State mới đầy đủ (A=70, B=30)
      v
AtomicReference<State>.compareAndSet(old, next)
      |
      +-- thành công: toàn bộ snapshot mới có hiệu lực
      |
      +-- thất bại: discard candidate, đọc state mới và thử lại
~~~

Lợi ích cốt lõi là reader có thể lấy `State s = ref.get()` **một lần**, rồi đọc hai field từ chính immutable object đó. Không có “A cũ, B mới” nếu object được xây dựng hoàn chỉnh trước khi publish và không còn bị sửa.

### 8.1 Java 17+ runnable: transfer bằng AtomicReference

Tạo `AtomicStateTransferDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicStateTransferDemo {
    private record State(long accountA, long accountB) {
        State {
            if (accountA < 0 || accountB < 0
                    || Math.addExact(accountA, accountB) != 100) {
                throw new IllegalArgumentException("Invalid state");
            }
        }

        long total() {
            return Math.addExact(accountA, accountB);
        }
    }

    private final AtomicReference<State> current =
            new AtomicReference<>(new State(100, 0));

    boolean transfer(boolean fromA, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        while (true) {
            State old = current.get();
            long from = fromA ? old.accountA() : old.accountB();
            long to = fromA ? old.accountB() : old.accountA();

            if (from < amount) {
                return false;
            }

            long nextFrom = from - amount;
            long nextTo = Math.addExact(to, amount);
            State next = fromA
                    ? new State(nextFrom, nextTo)
                    : new State(nextTo, nextFrom);

            if (current.compareAndSet(old, next)) {
                return true;
            }
            // Có thread khác commit trước: đọc state mới và thử lại.
        }
    }

    State snapshot() {
        return current.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicStateTransferDemo ledger = new AtomicStateTransferDemo();
        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                if (!ledger.transfer(true, 1)
                        || !ledger.transfer(false, 1)) {
                    throw new AssertionError("Transfer unexpectedly failed");
                }
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        State result = ledger.snapshot();
        System.out.println("A=" + result.accountA());
        System.out.println("B=" + result.accountB());
        System.out.println("Total=" + result.total());
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac AtomicStateTransferDemo.java
java AtomicStateTransferDemo
~~~

Stdout:

~~~text
A=100
B=0
Total=100
~~~

**Tại sao một CAS đủ cho nhóm trường?**

- `State` là record bất biến chỉ chứa hai primitive `long`; constructor kiểm tra số dư không âm và tổng bằng 100, nên mỗi instance hợp lệ.
- Tất cả writer đi qua `current.compareAndSet(old, next)`. Một CAS thành công thay **duy nhất một reference** từ snapshot cũ sang snapshot mới.
- Reader dùng một lần `current.get()` rồi đọc `accountA` và `accountB` cùng từ một object; không ghép hai trạng thái.
- Nếu contender khác cập nhật trước, CAS thất bại; vòng lặp đọc lại snapshot. Nhờ đó writer không ghi đè một bản cập nhật mới bằng tính toán từ state đã lỗi thời.
- Không có side effect bên ngoài trong đoạn tính candidate, nên có thể retry an toàn trong phạm vi ví dụ.
- Cả hai thread thực hiện số cặp chuyển cân bằng như ví dụ khóa; state cuối cùng xác định.

**Điểm quan trọng:** giải pháp này thành công không phải vì “AtomicReference có phép giao dịch nhiều object” mà vì chúng ta **đổi mô hình dữ liệu**: hai balance không còn là hai mutable object độc lập; chúng là hai thành phần của **một immutable aggregate state** được công bố bằng **một atomic reference**. Nếu hai tài khoản vẫn có setters công khai riêng, một CAS trên reference thứ ba không bảo vệ được các đường cập nhật đó.

### 8.2 CAS loop có thể retry và không miễn phí

Một vòng CAS không khóa monitor nhưng có các chi phí và giới hạn:

- Contention cao làm CAS thất bại nhiều lần, dẫn đến retry, CPU và allocation cho candidate bị bỏ.
- Không bảo đảm một thread cụ thể được phục vụ trong thời gian hữu hạn; **starvation** vẫn có thể xảy ra.
- Object mới được tạo mỗi lần thử; GC và cache behavior phụ thuộc workload.
- Hàm tính `next` phải **thuần hoặc có side effect có thể lặp an toàn**. Các method cập nhật dựa trên `getAndUpdate` cũng có thể gọi update function nhiều lần.
- Một record chứa reference đến object mutable không tự bất biến sâu. Collection/phần tử mutable cần copy hoặc ownership protocol riêng.
- Thuật toán sử dụng reference/giá trị tái sử dụng có thể gặp bài toán **ABA** khi cần phân biệt lịch sử. Trong ví dụ, mỗi state được tạo mới và không tái sử dụng object cũ; nếu nghiệp vụ cần versioning, hãy thêm version vào state.

Với nhiều field và invariant phức tạp, `synchronized` có thể dễ hiểu, dễ audit và đạt hiệu năng tốt hơn một CAS loop đầy allocation. Không chọn “lock-free” chỉ vì tên gọi.

## 9. AtomicReference trên một reference không tự làm object graph bên dưới atomic

Ví dụ sai:

~~~java
class Pair {
    int a;
    int b;
}

AtomicReference<Pair> ref = new AtomicReference<>(new Pair());
Pair pair = ref.get();
pair.a = 70;
pair.b = 30;
~~~

Đây là mảnh minh họa. `ref.get()` là atomic **đối với reference**, nhưng hai assignment trực tiếp lên fields của cùng `Pair` là thao tác mutable bình thường, không được bảo vệ bởi CAS. Reader khác có thể nhìn thấy `a = 70` và `b` còn cũ.

Để atomic reference publish một transaction logic, phải:

1. Tạo **State mới độc lập** và hoàn chỉnh.
2. Không mutate State đã publish.
3. Commit bằng một phép `set` hợp lệ nếu chỉ có một writer và protocol cho phép, hoặc CAS nếu nhiều writer cần tránh lost update.
4. Reader lấy reference **một lần** cho toàn snapshot.
5. Không cho code ngoài bỏ qua owner và mutate state khác.

Ngay cả `AtomicReference<List<Item>>` cũng có thể chứa một `ArrayList` mutable; chỉ atomic reference không giúp danh sách đó thread-safe. Nếu cần snapshot bất biến, dùng copy có chủ đích và bảo đảm **cả các phần tử** có semantics immutable phù hợp.

## 10. Composite operations và `ConcurrentHashMap`: phạm vi vẫn quan trọng

Nhiều API concurrent có các operation atomic **trong phạm vi một key** hoặc một mapping:

~~~java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.merge("paid", 1, Integer::sum);
~~~

Đây là mảnh minh họa, giả định đã import `ConcurrentHashMap`. `merge` áp dụng thao tác cập nhật mapping tương ứng theo hợp đồng map. Nhưng nghiệp vụ cần cập nhật **hai key cùng nhau**:

~~~java
counts.merge("available", -1, Integer::sum);
counts.merge("reserved", 1, Integer::sum);
~~~

vẫn là **hai operation**. Reader có thể lấy một giá trị sau lần merge thứ nhất và giá trị còn lại trước lần merge thứ hai. `ConcurrentHashMap` không hứa transaction toàn map chỉ vì các method đơn lẻ thread-safe.

Ngay cả khi `compute` hoặc `merge` chạy atomic đối với một key, code dùng mapping function để sửa thêm object/key ngoài phạm vi đó có thể tạo race, deadlock hoặc vi phạm hợp đồng API. Đừng làm I/O/blocking lâu trong mapping function.

Nếu invariant thực sự gồm nhiều key, hãy chọn lại **transaction boundary**: một lock cấp owner bảo vệ operation và snapshot, hoặc một immutable aggregate object dưới một key/reference, hoặc transaction của lớp dữ liệu thích hợp.

### 10.1 `LongAdder` và metrics không phải transaction

`LongAdder` có thể giảm contention cho các bộ đếm thống kê nhiều writer bằng cách phân tán cập nhật; `sum()` trong lúc có concurrent updates **không phải atomic snapshot**. Nó hợp với metrics chấp nhận giá trị xấp xỉ ở thời điểm đọc, không phù hợp để giữ invariant tài khoản/quotas đòi độ chính xác tức thời.

Tương tự, nhiều `AtomicInteger` độc lập có thể đúng nếu chúng là **những metrics độc lập** và người đọc không cần tổng nhất quán. Vấn đề chỉ xuất hiện khi nghiệp vụ cam kết các giá trị đó phải cùng thuộc một trạng thái.

## 11. Liveness: nhiều CAS không tự mang lại tiến triển toàn nghiệp vụ

CAS thường là nền tảng của các thuật toán **non-blocking**, nhưng cần phân biệt:

- **Lock-free:** thuật toán theo định nghĩa progress tương ứng bảo đảm toàn hệ thống có tiến triển trong điều kiện mô hình của thuật toán; không bảo đảm một thread cụ thể không starvation.
- **Wait-free:** mọi operation hoàn tất trong một số bước hữu hạn theo mô hình, là bảo đảm mạnh hơn.
- **Obstruction-free:** một thread hoàn tất nếu được chạy đủ lâu mà không có cạnh tranh.

Không thể kết luận một business operation gồm **hai CAS trên hai biến** là “lock-free transaction” chỉ vì từng CAS riêng lẻ lock-free. Nếu CAS thứ nhất thành công rồi thread bị preempt/cancel trước CAS thứ hai, state nghiệp vụ vẫn dở dang.

Một multi-word CAS/transactional memory algorithm đúng thường cần cơ chế **descriptor, giúp hoàn tất (helping), versioning hoặc rollback** với lập luận tinh vi. Java SE `AtomicInteger`/`AtomicReference` mặc định **không cung cấp API transaction đa địa chỉ**. Tự viết thuật toán như vậy chỉ để tránh một lock thường làm tăng rủi ro rất lớn.

CAS loop với nhiều contender còn có thể retry liên tục; cần kiểm tra retry rate, tail latency và khả năng hủy. “Không dùng monitor” không đồng nghĩa “không có vấn đề liveness”.

## 12. Exception, interruption và rollback: atomic từng bước chưa đủ

Giả sử code thực hiện:

~~~java
accountA.addAndGet(-30);
sendNetworkMessage();  // Có thể throw hoặc timeout.
accountB.addAndGet(30);
~~~

Đây là mảnh minh họa, chưa có khai báo `sendNetworkMessage`. Nếu network call ném exception, chương trình có thể dừng sau khi trừ A mà chưa cộng B. Chuyển hai `addAndGet` thành hai CAS không thay đổi failure window này.

### 12.1 Vì sao rollback thủ công cũng có thể sai?

Một ý tưởng là:

~~~java
try {
    accountA.addAndGet(-30);
    accountB.addAndGet(30);
} catch (RuntimeException e) {
    accountA.addAndGet(30);
    throw e;
}
~~~

Mảnh này **không phải transaction an toàn**: giữa các bước, thread khác có thể cập nhật A/B; rollback cộng 30 không nhất thiết trả lại đúng trạng thái nghiệp vụ trước đó. Thậm chí nếu thao tác credit B đã thành công rồi exception phát sinh ở nơi khác, rollback A không có cơ sở để quyết định có phải rollback B hay không.

Một rollback đúng cần xác định **chính xác trạng thái đã commit**, isolation của concurrent operations và cách xử lý lỗi trong lúc rollback. Với external side effect, còn có nguy cơ một lệnh đã được phía xa xử lý nhưng caller chỉ nhìn thấy timeout.

### 12.2 Exception safety với lock

`synchronized` hoặc `ReentrantLock` tự bảo vệ atomic observation **nếu mọi reader/writer cùng protocol**, nhưng không tự rollback dữ liệu khi exception:

~~~java
synchronized (lock) {
    accountA -= amount;
    long nextB = Math.addExact(accountB, amount); // Có thể throw.
    accountB = nextB;
}
~~~

Nếu `addExact` throw sau khi đã trừ, monitor nhả khi exception thoát, để lại trạng thái không hợp lệ. Hãy **tính và validate mọi giá trị có thể throw trước commit**, rồi thực hiện các assignment đơn giản trong critical section:

~~~java
synchronized (lock) {
    if (accountA < amount) {
        return false;
    }
    long nextA = accountA - amount;
    long nextB = Math.addExact(accountB, amount);
    accountA = nextA;
    accountB = nextB;
    return true;
}
~~~

Đây là mảnh method minh họa, giả định `amount > 0` đã được validate, các trường dùng `long` và method trả boolean. Tính đúng của cả hai assignment được bảo vệ bởi lock; reader không thể xen vào giữa hai gán nếu dùng cùng lock.

### 12.3 Interruption không phải transaction rollback

`Thread.interrupt()` là tín hiệu hợp tác. Nó không quay ngược những write đã thực hiện. Một operation được thiết kế tốt nên chỉ kiểm tra interruption/cancellation ở **điểm an toàn**, hoặc chuẩn bị khả năng rollback/compensation phù hợp. Không chia operation tài chính thành nhiều primitive rồi hy vọng interrupt sẽ đưa hệ thống trở lại trạng thái cũ.

## 13. Crash consistency và durability: lock/CAS không ghi được dữ liệu bền vững

Trong một JVM đang chạy, lock hoặc CAS có thể bảo vệ **in-memory state**. Nhưng nếu JVM/process chết sau khi ghi một object mà trước khi ghi object khác, state ngoài RAM hoặc log bên ngoài có thể đã phản ánh một phần operation.

Đừng nhầm:

| Khả năng | AtomicInteger / CAS | Một lock JVM | Transaction dữ liệu bền vững |
| --- | --- | --- | --- |
| Atomic một biến/reference trong RAM | Có, theo operation | Có nếu truy cập dưới protocol | Phụ thuộc storage |
| Atomic nhiều field trong RAM | Không nếu nhiều atomics độc lập; có thể gộp immutable state vào một reference | Có nếu tất cả access cùng lock | Phụ thuộc transaction boundary |
| Isolation giữa nhiều JVM/process | Không | Không | Cần cơ chế cấp storage/distributed |
| Rollback khi exception | Không tự động | Không tự động | Có thể được hệ thống giao dịch hỗ trợ theo hợp đồng |
| Durability sau process crash | Không | Không | Cần cơ chế lưu bền vững |
| Network I/O exactly-once | Không | Không | Cần protocol riêng; không mặc định được bảo đảm |

Một giao dịch database có thể cung cấp atomicity/isolation/durability theo cấu hình và isolation level; không phải mọi database hoặc thao tác ngoài transaction đều cho cùng bảo đảm. Nếu chuyển tiền giữa **hai datastore độc lập** hoặc giữa database và message broker, đây là bài toán transaction nhiều hệ thống, không thể giải chỉ bằng monitor hay atomic class trong ứng dụng.

Các giải pháp ở cấp rộng hơn có thể bao gồm transaction database, optimistic version checks, idempotency keys, durable outbox, saga/compensating actions hay distributed transaction khi hệ thống hỗ trợ. Mỗi cách có trade-off và failure model riêng. Trong bài này chỉ cần nhớ **phạm vi lock/CAS không vượt khỏi những object mà chính giao thức của chúng kiểm soát trong một JVM**.

## 14. Atomicity, isolation, visibility và linearizability

Các từ này liên quan nhưng không đồng nghĩa:

| Thuật ngữ | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Atomicity** | Một operation được quan sát như một thay đổi không bị chia đôi trong phạm vi đã định. | Transfer cập nhật hai số dư dưới một lock. |
| **Isolation** | Các operation đồng thời không nhìn thấy những trạng thái trung gian không hợp lệ theo contract. | Reader cặp account lấy cùng hai lock. |
| **Visibility / happens-before** | Hiệu ứng ghi được công bố và quan sát theo quy tắc JMM. | Unlock → lock sau đó trên cùng monitor. |
| **Linearizability** | Mỗi operation có thể coi như có hiệu lực tại một điểm giữa invocation và response, giữ thứ tự real-time của operations không chồng lấn. | CAS thành công thay `AtomicReference<State>`. |
| **Durability** | Trạng thái đã commit sống sót qua một số loại lỗi/crash theo hợp đồng lưu trữ. | Ghi transaction vào hệ thống lưu bền vững. |

`AtomicLong.addAndGet` có một điểm tuyến tính hóa cho **một biến**. Hai operation addAndGet liên tiếp có **hai điểm**; không có điểm tuyến tính hóa chung của transfer nếu không thêm một giao thức khác.

Một synchronized method làm transfer nhưng reader của account B bỏ qua lock cũng không tạo isolation mong muốn: contract chỉ đúng với những participant tuân thủ lock. Khi bàn về “transaction trong RAM”, luôn chỉ rõ những operation nào nằm trong phạm vi bảo đảm.

## 15. Khi nào các atomics độc lập vẫn là lựa chọn đúng?

Không nên rút ra kết luận rằng mọi lần xuất hiện nhiều AtomicInteger đều sai.

Chúng phù hợp khi **những state thực sự độc lập** hoặc hợp đồng cho phép snapshot gần đúng. Ví dụ:

- Bộ đếm số request thành công và thất bại phục vụ dashboard, chấp nhận số tổng đọc trong lúc cập nhật hơi lệch.
- Hai feature flags độc lập, được cập nhật riêng và không yêu cầu chuyển trạng thái nguyên tử cùng nhau.
- Nhiều counters phục vụ throughput monitoring, không dùng làm hạn mức hoặc accounting chính xác.
- Cấu trúc dữ liệu concurrent có mỗi node/key độc lập theo invariant đã thiết kế, không yêu cầu một snapshot toàn cục.

Ngược lại, nếu một điều kiện kiểu `a + b == capacity`, `paid ⇒ paymentId != null` hoặc `available >= 0` phải đúng tại **mọi thời điểm được observer nhìn thấy**, cần cập nhật/đọc với transaction boundary chung.

**Tính đúng đắn phụ thuộc hợp đồng quan sát.** Một dashboard chấp nhận eventual consistency khác hẳn một hệ thống cấp quota không được vượt hạn mức.

## 16. Performance và chi phí của giải pháp

| Kỹ thuật | Ưu điểm | Chi phí/giới hạn | Khi cân nhắc |
| --- | --- | --- | --- |
| Một `synchronized` lock cho aggregate | Đơn giản, dễ chứng minh correctness, bảo vệ nhiều field. | Contention có thể tuần tự hóa các operation không liên quan nếu lock quá rộng. | Default tốt cho invariant nội bộ một owner. |
| `ReentrantLock` | Timeout, interruptible acquisition, Condition; giữ invariant qua critical section. | Phải unlock trong finally, dễ thêm nhánh lỗi. | Cần policy lấy lock/condition. |
| Khóa hai object theo ID | Cho phép cặp object không giao nhau chạy song song. | Deadlock nếu lock order sai; snapshot toàn cục khó hơn. | Nhiều account/object độc lập nhưng có transfer giữa chúng. |
| `AtomicReference<ImmutableState>` CAS | Một điểm commit cho aggregate, read snapshot đơn giản. | Allocation, retry, starvation, logic candidate phải thuần. | State gọn, immutable, multi-writer optimistic update. |
| Hai `AtomicLong` độc lập | Rẻ và dễ dùng cho hai biến không có invariant chung. | Không bảo vệ transaction đa biến. | Metrics độc lập hoặc consistency gần đúng được cho phép. |
| Giao dịch storage/database | Có thể bảo vệ dữ liệu bền vững và nhiều record theo hợp đồng. | I/O, transaction contention, isolation/configuration complexity. | Invariant thuộc storage hoặc nhiều process. |

Không có công thức “CAS nhanh hơn synchronized”. Nếu state chỉ gồm vài trường và updates nhiều, một lock ngắn có thể hiệu quả và dễ bảo trì hơn một vòng CAS liên tục tạo object mới. Nếu nhiều reader ít writer, immutable snapshot có thể hấp dẫn. Hãy đo **throughput, p95/p99 latency, lock blocked time, CAS retry rate, GC allocation** và độ đúng của invariant dưới workload tương ứng.

## 17. Cách kiểm thử transaction nhiều object

Một test chỉ so sánh tổng số dư **sau khi mọi thread đã join** có thể bỏ sót khoảng hở giữa debit và credit. Ví dụ demo đầu có tổng cuối đúng 100, nhưng một reader giữa chừng thấy 70.

Các bước kiểm thử:

1. **Định nghĩa invariant chính xác**: tổng bảo toàn, số dư không âm, mỗi transfer thành công làm thay đổi đúng hai balance.
2. **Định nghĩa snapshot contract**: reader có quyền nhìn trạng thái khi transfer đang chạy không? Nếu có, phải thấy snapshot trước hoặc sau một transfer hoàn chỉnh.
3. **Dùng latch/barrier tạo interleaving**: cố ý dừng writer giữa hai bước để kiểm tra reader không thấy dở dang. Đối với thiết kế đã sửa, reader phải dùng API snapshot chuẩn.
4. **Stress test nhiều writer**: chuyển tiền qua lại với nhiều thread, cùng kiểm tra số dư và tổng.
5. **Chèn lỗi ở điểm có thể throw**: overflow, validation, callback, interruption hoặc network timeout; xác nhận operation thất bại vẫn giữ invariant.
6. **Kiểm tra mọi đường cập nhật**: setters, admin operations, reset, scheduled jobs, background tasks. Chỉ một đường bypass lock có thể phá toàn bộ protocol.
7. **Đo hiệu năng sau khi correctness đạt**: tránh đánh đổi dữ liệu đúng để đổi một con số benchmark hấp dẫn.
8. **Nhận biết giới hạn test**: chạy nhiều lần thấy đúng không chứng minh mọi interleaving đều an toàn. Code review trên invariant, lock ownership và HB vẫn là bắt buộc.

### 17.1 Test lỗi bằng countdown giữa hai bước

`AtomicTransferGapDemo` là một test đối chứng: với thiết kế hai atomic độc lập, reader chủ động được đưa vào giữa các update và quan sát total=70. Khi sửa bằng `Ledger.transfer` hoặc `AtomicReference<State>`, không còn API để nhìn một nửa update: thread đọc `snapshot()` theo protocol sẽ thấy một snapshot hợp lệ.

Nếu cần test một operation đang giữ lock, tạo latch để biết worker đã vào critical section rồi cho reader gọi `snapshot()`; reader sẽ chờ cho đến khi operation nhả lock. **Không đặt một latch khiến worker chờ tín hiệu từ reader trong khi reader lại đang chờ chính lock worker giữ**, vì đó sẽ là deadlock do test tạo ra.

### 17.2 Test overflow

Thử các biên gần `Long.MAX_VALUE` hoặc `Long.MIN_VALUE` và xác nhận phép tính checked xảy ra **trước commit**. Java `long` không an toàn khỏi overflow chỉ vì nó 64-bit; với tiền tệ cần kiểm tra đơn vị, miền giá trị và số học phù hợp. Một transaction đồng bộ hoàn hảo vẫn có thể sai nghiệp vụ nếu overflow.

## 18. Những ngộ nhận thường gặp

**“Từng phép cộng là atomic thì chuỗi hai phép cộng cũng atomic.”** Sai. Hai operation có hai điểm commit và có thể bị observer chen vào giữa.

**“CAS của A thành công nghĩa là transfer A→B đã hoàn thành.”** Sai. Nó chỉ chứng minh một thay đổi trên A đã thành công.

**“Đọc lại hai lần và so sánh có thể thay transaction.”** Không tổng quát. Có thể gặp ABA hoặc các writer khác không được quan sát; cần protocol snapshot/versioning có chứng minh.

**“Đưa hai object vào AtomicReference là đủ.”** Chỉ khi object graph được publish đúng, thực sự bất biến và mọi mutation đi qua một reference/protocol. Thay reference không tự ngăn thay fields của object cũ.

**“Hai getter synchronized riêng là một snapshot.”** Sai. Writer có thể chạy giữa hai lần getter. Cần một operation snapshot cùng lock hoặc một immutable aggregate.

**“Đã có lock nên exception tự rollback.”** Sai. Monitor được nhả khi exception thoát, nhưng các phép gán đã chạy vẫn giữ nguyên. Cần tính/validate trước commit hoặc giao thức rollback.

**“Bỏ lock và dùng nhiều CAS sẽ tự thành lock-free transaction.”** Sai. Progress guarantee của một CAS không ghép thành transaction đa địa chỉ; thuật toán đúng thường phức tạp hơn nhiều.

**“AtomicReference thay được database transaction.”** Không. Nó không tạo durability, isolation giữa process hay rollback các external side effect.

**“Thread.join giúp sửa phép chuyển tiền bị dở dang.”** Join giúp caller quan sát worker đã kết thúc và memory effects của nó; không hoàn tất bước credit bị bỏ qua hoặc sửa invariant.

**“Không thấy tổng sai trong stress test nghĩa là đã chứng minh correctness.”** Không. Interleaving lỗi có thể rất hiếm. Dùng protocol reasoning và test có điều phối bằng latch.

## 19. Quy trình chọn giải pháp theo phạm vi

| Bài toán | Điều kiện | Cách tiếp cận |
| --- | --- | --- |
| Một balance cần cộng/trừ chính xác | Không liên quan invariant ngoài balance | Một `AtomicLong` hoặc lock, kiểm tra amount/overflow. |
| Hai field trong cùng object luôn phải cùng trạng thái | Mọi reader/writer do một owner kiểm soát | `synchronized`/`ReentrantLock` bao trùm cả check, update và snapshot. |
| Nhiều field thuộc một snapshot immutable | Có thể gói thành một object không đổi sau publish | `AtomicReference<State>` CAS, mọi writer qua một reference. |
| Hai Account độc lập cần chuyển tiền | Có ID bất biến, lock ownership rõ | Lấy cả hai lock theo thứ tự toàn cục; đọc snapshot cặp theo cùng protocol. |
| Nhiều keys trong ConcurrentHashMap có invariant chung | Atomic per-key không đủ | Thiết kế owner/transaction boundary chung, không dùng hai `merge` độc lập. |
| Nhiều record cùng một database | Cần isolation/durability của storage | Transaction của database theo isolation thích hợp. |
| Database và dịch vụ ngoài cùng tham gia | Có network/crash/duplicate delivery | Thiết kế idempotency, transaction/outbox/compensation theo failure model. |
| Metrics nhiều counter độc lập | Có thể chấp nhận snapshot gần đúng | Atomic/LongAdder riêng cho mỗi metric. |

**Quy tắc thực hành:** chọn **đơn vị sở hữu invariant** trước, rồi đảm bảo cả cập nhật và quan sát cùng đi qua đơn vị đó. Nếu không thể xác định được ai sở hữu toàn bộ invariant, bài toán cần đổi mô hình dữ liệu/transaction boundary trước khi chọn API Atomic hay lock.

## 20. Câu hỏi tự kiểm tra

**1.** Hai `AtomicLong`, mỗi lần `addAndGet` atomic. Chuyển 30 từ A sang B có atomic không?  
**Không.** Có khoảng giữa lần trừ A và lần cộng B; một observer có thể thấy tổng sai.

**2.** CAS giúp A không bị rút quá số dư. Vì sao vẫn chưa đủ cho transfer?  
**Vì** điều kiện và cập nhật của B không nằm trong cùng atomic operation. CAS của A không commit B.

**3.** Hai balance nằm trong cùng một Ledger. Giải pháp dễ chứng minh nhất?  
**Một private lock** bảo vệ cả chuyển tiền và snapshot; tính/validate trước khi commit.

**4.** Nếu mỗi Account có lock riêng, tránh deadlock khi chuyển A↔B bằng cách nào?  
**Lấy cả hai lock theo thứ tự toàn cục ổn định**, ví dụ ID duy nhất; mọi call path cùng protocol.

**5.** Vì sao một `AtomicReference<State>` có thể đủ khi hai balance thành fields của immutable State?  
**Vì** một lần CAS thay toàn bộ reference đến snapshot; reader lấy một reference duy nhất, không đọc hai object mutable riêng.

**6.** Nếu `State` có field `List` mutable và caller sửa list sau publish thì snapshot còn bất biến không?  
**Không.** Record/final reference không tự tạo bất biến sâu của object graph.

**7.** Có thể gọi remote API trong lambda của `getAndUpdate` rồi hy vọng chỉ chạy một lần không?  
**Không.** Hàm có thể bị gọi nhiều lần khi tranh chấp; side effect cần được tách hoặc làm idempotent theo thiết kế.

**8.** `synchronized` có tự rollback khi `Math.addExact` ném exception giữa hai gán không?  
**Không.** JVM nhả monitor, nhưng các gán đã thực hiện vẫn tồn tại; phải tính trước commit.

**9.** `ConcurrentHashMap.merge` hai key liên tiếp có tạo transaction toàn map không?  
**Không.** Mỗi merge có phạm vi riêng, không tự bảo vệ invariant của hai key.

**10.** Vì sao CAS/lock trong RAM không thay transaction database?  
**Vì** chúng không bảo đảm durability hoặc isolation giữa các process và external resources.

**11.** Nếu total cuối luôn đúng sau join, liệu từng observer giữa transfer cũng thấy total đúng?  
**Chưa chắc.** Cần test và chứng minh snapshot contract trong lúc operation đang chạy.

**12.** Khi nào nhiều atomics độc lập là lựa chọn hợp lý?  
**Khi** các giá trị độc lập theo nghiệp vụ hoặc contract chấp nhận snapshot gần đúng, không đòi transaction liên biến.

**Ghi nhớ:** Atomic/CAS là cơ chế mạnh để bảo vệ **một biến hoặc một reference**. Nó chỉ bảo vệ giao dịch nhiều field khi bạn **gộp toàn bộ invariant thành một đơn vị cập nhật nguyên tử** và buộc mọi writer/reader tuân thủ protocol đó. Nếu nhiều object độc lập phải cập nhật nhất quán, cần một transaction boundary rõ ràng: khóa chung, thứ tự đa khóa, immutable aggregate CAS, hoặc cơ chế giao dịch ở lớp dữ liệu tương ứng. **Từng bước atomic không có nghĩa toàn bộ quy trình atomic.**