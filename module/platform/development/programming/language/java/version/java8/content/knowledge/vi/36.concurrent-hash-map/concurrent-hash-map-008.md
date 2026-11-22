# Phân biệt nguyên tử từng thao tác với giao dịch nhiều khóa trong ConcurrentHashMap (Java 8)

Một hệ thống có hai tài khoản A và B, mỗi tài khoản có số dư **100**. Người dùng chuyển **30** từ A sang B. Nhà phát triển sử dụng `ConcurrentHashMap<String,Integer>` và viết hai thao tác:

```java
balances.computeIfPresent("A", (key, value) -> value - 30);
balances.computeIfPresent("B", (key, value) -> value + 30);
```

Mỗi thao tác `computeIfPresent` ở trên có tính **nguyên tử đối với cập nhật của khóa được tác động**. Nhưng **cả hai thao tác gộp lại không phải một giao dịch nguyên tử**. Sau khi A bị trừ 30 nhưng trước khi B được cộng 30, một luồng khác có thể nhìn thấy `A=70, B=100, tổng=170`, trong khi tổng trước và sau chuyển tiền phải luôn là **200**. Nếu chương trình bị dừng hoặc ném lỗi sau bước đầu, giao dịch còn có nguy cơ dở dang.

Đó là ranh giới phải hiểu khi dùng `ConcurrentHashMap`:

> **Nguyên tử cho một phép cập nhật đơn lẻ/khóa không tự tạo tính nguyên tử, nhất quán hay khả năng rollback cho một chuỗi thay đổi trên nhiều khóa.**

Bài này giải thích đầy đủ cơ chế, giới hạn, ví dụ race thực sự, phương án đồng bộ nhiều khóa, bất biến nghiệp vụ, bất biến giá trị, chiến lược CAS, khả năng đọc snapshot nhất quán và khi nào bắt buộc dùng giao dịch database. Các mã độc lập trong bài **biên dịch ở mức Java 8 và đã được chạy, kiểm tra stdout**. Mọi API được chọn đều hiện còn dùng; không dựa vào thủ thuật legacy hoặc những tiện ích chỉ có từ các phiên bản Java mới hơn.

## 1. Hiểu đúng ba khái niệm: thread-safe, atomic và transaction

Ba từ thường bị đánh đồng nhưng nói về ba yêu cầu khác nhau.

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Thread-safe collection** | Các luồng có thể gọi phương thức của collection đồng thời mà không làm hỏng cấu trúc nội bộ? | Nhiều thread đọc/ghi một `ConcurrentHashMap` |
| **Atomic operation** | Một phép cập nhật nhất định có được quan sát như một đơn vị, không bị chen giữa ngay trong logic cập nhật được bảo đảm? | `merge("count",1,Integer::sum)` cập nhật một khóa |
| **Multi-key transaction** | Nhiều thay đổi có được xem là một đơn vị với bất biến xuyên khóa, rollback, isolation và có thể durability tùy hợp đồng? | Chuyển tiền từ A sang B mà mọi observer hợp lệ không thấy trạng thái nửa chừng |

**ConcurrentHashMap** là một map hỗ trợ truy cập đồng thời và cung cấp những thao tác cập nhật nguyên tử ở phạm vi được tài liệu API xác định. Nó **không tự biến** một dãy nhiều lệnh `get`, `put`, `compute`, `remove` thành một transaction.

Từ “atomic” phải gắn với một **phạm vi cụ thể**. Nói “hệ thống này dùng ConcurrentHashMap nên mọi hoạt động đều atomic” là phát biểu quá rộng.

### Ví dụ bất biến nghiệp vụ

Một ledger chỉ có hai số dư cần duy trì:

```text
balance[A] >= 0
balance[B] >= 0
balance[A] + balance[B] = 200
```

Một phép chuyển `A -> B` số lượng 30 phải đảm bảo các điều kiện đó theo chính sách của hệ thống. Dùng hai phép cập nhật nguyên tử riêng không đủ để bảo đảm bất biến tổng **tại mọi thời điểm được quan sát**.

Trong hệ thống thực tế, tổng ban đầu có thể khác 200, phải có quy định về số âm, phí chuyển, giới hạn, đồng tiền, precision và các tài khoản bên ngoài. Ví dụ này cố ý dùng hai số nguyên nhỏ để cô lập bài toán concurrency.

## 2. ConcurrentHashMap bảo đảm những gì?

`ConcurrentHashMap<K,V>` được thiết kế cho truy cập đồng thời, với các đặc tính hữu ích:

- Các phép truy cập như `get` và `put` được dùng an toàn giữa các thread theo hợp đồng map.
- `putIfAbsent` là thao tác có điều kiện nguyên tử cho một mapping.
- `replace(key, oldValue, newValue)` hỗ trợ conditional update một mapping.
- `remove(key, value)` hỗ trợ conditional removal.
- `computeIfAbsent`, `computeIfPresent`, `compute`, `merge` cho phép tính toán và cập nhật một mapping theo hợp đồng nguyên tử của phép gọi.
- Các iterator và view như `entrySet()` thường **weakly consistent** trong khi map đang thay đổi, không biến vòng lặp qua nhiều entry thành một snapshot có giao dịch.
- Map không cho phép key hoặc value là `null`; không dùng `null` làm “số dư chưa khởi tạo” một cách ngầm định.

Điểm then chốt: **mỗi bảo đảm chỉ áp dụng ở phạm vi phương thức**. Khi thực hiện:

```java
map.compute("A", (k, old) -> newA);
map.compute("B", (k, old) -> newB);
```

đó vẫn là **hai lần hoàn thành riêng**, không có API “commit cả A và B đồng thời” được suy ra từ ConcurrentHashMap.

### Có được nói “ConcurrentHashMap atomic mọi thứ trên một khóa” không?

Cũng phải nói chính xác hơn: các thao tác **được tài liệu là atomic**, như `compute`, `merge`, conditional update, có bảo đảm nhất định cho mapping liên quan. Nhưng việc **ghép nhiều lời gọi**, kể cả cùng một khóa, không tự tạo atomicity cho cả chuỗi:

```java
Integer old = map.get("count");
map.put("count", old + 1);
```

Cả get và put có thể an toàn riêng lẻ, nhưng phép **read–modify–write tổng hợp** trên hai lời gọi không atomic. Hai thread có thể đọc cùng old value rồi ghi đè kết quả của nhau.

## 3. Lost update: hai lời gọi thread-safe chưa chắc thành một phép tăng nguyên tử

Giả sử `count=0`, hai thread thực hiện:

```text
Thread A                    Thread B
--------                    --------
get("count") -> 0
                            get("count") -> 0
put("count", 1)
                            put("count", 1)

Kết quả cuối: 1, trong khi hai lần tăng kỳ vọng phải là 2.
```

Điều này không chứng minh `ConcurrentHashMap.put` thiếu an toàn. Nó chứng minh **đọc và viết trong hai lời gọi riêng không bảo vệ phép tính có điều kiện của ứng dụng**.

Với counter theo khóa, dùng:

```java
map.merge("count", 1, Integer::sum);
```

hoặc:

```java
map.compute("count", (k, old) -> old == null ? 1 : old + 1);
```

Các phép đó kết hợp tính toán/cập nhật **cho mapping của khóa được thao tác**. Dù vậy, chúng không tạo một transaction cho **hai khóa khác nhau**.

### Các trường hợp phù hợp của nguyên tử một khóa

- Đếm số lượng event theo loại, mỗi loại là một key.
- Khởi tạo cache value theo nhu cầu bằng `computeIfAbsent`.
- Thay đổi một trạng thái máy đơn lẻ bằng `replace(old,new)`.
- Gộp count hoặc tổng theo một key bằng `merge`.
- Chỉ cập nhật một aggregate immutable được lưu trong **một mapping**, nếu phù hợp thiết kế.

Không biến câu “atomic một key” thành lời khuyên rằng mọi thao tác phức tạp phải nhét vào một callback `compute`. Callback có thể giữ khóa/nút liên quan đủ lâu để cản các cập nhật đồng thời; nên ngắn, không block I/O và không cập nhật đệ quy các key khác của cùng map.

## 4. Ví dụ Java 8 số 1 — get/put làm mất cập nhật, merge cho đúng kết quả

Tệp **`SingleKeyAtomicityDemo.java`** tạo race có kiểm soát bằng `CountDownLatch`. Hai thread cố ý đọc cùng giá trị trước khi được phép ghi, nhờ đó tái hiện lost update không phụ thuộc tốc độ CPU. Sau đó bốn thread dùng `merge` để tăng cùng key nhiều lần.

```java
import java.util.concurrent.*;

public class SingleKeyAtomicityDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> unsafe =
            new ConcurrentHashMap<>();
        unsafe.put("count", 0);

        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch resume = new CountDownLatch(1);

        Runnable readThenPut = () -> {
            int oldValue = unsafe.get("count");
            bothRead.countDown();

            try {
                resume.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new AssertionError(ex);
            }

            unsafe.put("count", oldValue + 1);
        };

        Thread first = new Thread(readThenPut, "lost-update-a");
        Thread second = new Thread(readThenPut, "lost-update-b");
        first.start();
        second.start();

        bothRead.await();
        resume.countDown();
        first.join();
        second.join();

        check(unsafe.get("count") == 1,
              "lost update reproduced");

        ConcurrentHashMap<String, Integer> safe =
            new ConcurrentHashMap<>();
        safe.put("count", 0);

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1000; j++) {
                    safe.merge("count", 1, Integer::sum);
                }
            }, "atomic-" + i);
            workers[i].start();
        }

        for (Thread worker : workers) worker.join();
        check(safe.get("count") == 4000,
              "atomic merge total");

        System.out.println("getThenPut=" + unsafe.get("count"));
        System.out.println("mergeResult=" + safe.get("count"));
        System.out.println("PASS");
    }
}
```

Chạy trên JDK 8:

```bash
javac -encoding UTF-8 SingleKeyAtomicityDemo.java
java SingleKeyAtomicityDemo
```

Khi dùng JDK mới và muốn xác minh chỉ dùng API Java 8:

```bash
javac --release 8 -encoding UTF-8 SingleKeyAtomicityDemo.java
java SingleKeyAtomicityDemo
```

**Stdout đã kiểm chứng:**

```text
getThenPut=1
mergeResult=4000
PASS
```

**Diễn giải:**

1. Hai thread ở lần thử đầu cùng đọc 0, nên cả hai đều viết 1. Map không bị hỏng; **ngữ nghĩa tăng hai lần đã bị mất một lần cập nhật**.
2. Trong lần thử thứ hai, mỗi `merge("count",1,Integer::sum)` là một cập nhật nguyên tử cho key đó. Bốn thread, mỗi thread 1.000 lần, cho tổng **4.000**.
3. Các worker đều được `join()` trước khi đọc kết quả cuối, do đó không đọc khi phép tính còn chạy.
4. Ví dụ sử dụng `CountDownLatch` thay vì `Thread.sleep` để tạo interleaving xác định.
5. Tính nguyên tử của merge này **không kéo dài** sang phép cập nhật một key khác nằm ở câu lệnh tiếp theo.

## 5. Giao dịch hai khóa: từng compute nguyên tử vẫn thấy trạng thái trung gian

Đưa vấn đề lên mức cao hơn:

```java
ConcurrentHashMap<String,Integer> balances =
    new ConcurrentHashMap<>();
balances.put("A", 100);
balances.put("B", 100);

// Một phép chuyển 30 đơn vị:
balances.computeIfPresent("A", (k, v) -> v - 30);
balances.computeIfPresent("B", (k, v) -> v + 30);
```

Cả hai lời gọi đều đúng về cơ chế cập nhật cho key riêng. Nhưng giữa chúng:

```text
Trước:       A=100, B=100, tổng=200
Sau trừ A:   A= 70, B=100, tổng=170  <-- observer có thể nhìn thấy
Sau cộng B:  A= 70, B=130, tổng=200
```

Một người đọc A rồi B có thể thấy tổng 170. Một process crash ở thời điểm giữa hai bước có thể khiến dữ liệu in-memory dở dang; sau restart, nếu không có nguồn dữ liệu bền vững, còn có thể mất toàn bộ state.

**Cảnh báo kỹ thuật:** kết quả `170` trong ví dụ không phải một lỗi hiếm do ConcurrentHashMap “thiếu memory barrier”. Tại thời điểm giữa hai lời gọi, **đó là trạng thái thật của hai mapping**. Không có transaction nào hứa che trạng thái ấy khỏi reader.

### Atomicity là tính chất của operation, không phải của câu chuyện nghiệp vụ

Một phép chuyển tiền logic chứa ít nhất:

1. Kiểm tra tài khoản nguồn tồn tại.
2. Xác minh số dư đủ.
3. Trừ số dư nguồn.
4. Cộng số dư đích.
5. Ghi dấu giao dịch, trạng thái/ID, tránh thực hiện lặp.
6. Công bố kết quả theo hợp đồng ứng dụng.

Nếu những bước này tác động nhiều key hoặc nhiều hệ thống, không thể bảo đảm cả giao dịch chỉ bằng việc đổi `put` sang `compute` cho từng khóa.

## 6. Ví dụ Java 8 số 2 — nhìn thấy giao dịch nửa chừng

Tệp **`TwoKeyTransferGapDemo.java`** cố ý dừng giữa hai thao tác, dùng latch để luồng đọc quan sát đúng trạng thái nửa chừng.

```java
import java.util.concurrent.*;

public class TwoKeyTransferGapDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> balances =
            new ConcurrentHashMap<>();
        balances.put("A", 100);
        balances.put("B", 100);

        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch allowCredit = new CountDownLatch(1);

        Thread transfer = new Thread(() -> {
            balances.computeIfPresent(
                "A", (key, current) -> current - 30);
            debited.countDown();

            try {
                allowCredit.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new AssertionError(ex);
            }

            balances.computeIfPresent(
                "B", (key, current) -> current + 30);
        }, "transfer");

        transfer.start();
        debited.await();

        int middleA = balances.get("A");
        int middleB = balances.get("B");
        int middleSum = middleA + middleB;

        check(middleA == 70 && middleB == 100
              && middleSum == 170,
              "partial transfer visible");

        allowCredit.countDown();
        transfer.join();

        int finalA = balances.get("A");
        int finalB = balances.get("B");
        int finalSum = finalA + finalB;

        check(finalA == 70 && finalB == 130
              && finalSum == 200,
              "final sum restored");

        System.out.println("midA=" + middleA);
        System.out.println("midB=" + middleB);
        System.out.println("midTotal=" + middleSum);
        System.out.println("finalA=" + finalA);
        System.out.println("finalB=" + finalB);
        System.out.println("finalTotal=" + finalSum);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 TwoKeyTransferGapDemo.java
java TwoKeyTransferGapDemo
```

**Stdout đã kiểm chứng:**

```text
midA=70
midB=100
midTotal=170
finalA=70
finalB=130
finalTotal=200
PASS
```

Điểm cần nhớ: `midTotal=170` không đến từ một thread không an toàn hay read hỏng. Cả hai `get` đều trả chính xác mapping đang tồn tại ở thời điểm đọc. Vấn đề là **một giao dịch cần hai key nhưng thiếu cơ chế để bảo vệ hai key như một đơn vị**.

**Một rủi ro khác:** nếu code ném exception sau trừ A nhưng trước cộng B, invariant không tự được khôi phục. Chỉ nhìn thấy tổng cuối đúng trong một lần thử không đủ chứng minh giao dịch luôn nhất quán dưới mọi lỗi/crash.

## 7. Tại sao bọc hai compute trong một callback compute(A) không giải quyết được?

Một ý tưởng thường thấy:

```java
// Không phải chiến lược giao dịch nhiều khóa.
balances.compute("A", (key, current) -> {
    balances.merge("B", 30, Integer::sum);
    return current - 30;
});
```

**Không nên dùng đoạn này làm giải pháp.** `compute("A")` chỉ cam kết atomically cập nhật mapping A theo phạm vi API; một `merge("B")` trong callback không tự trở thành commit chung với A. Thứ tự có thể làm invariant tạm sai, callback có thể thất bại sau khi đã cập nhật B, và thao tác đệ quy/cập nhật map từ mapping function có thể gây vấn đề khóa hoặc bị API từ chối.

JavaDoc của `ConcurrentHashMap.compute`/`computeIfAbsent`/`computeIfPresent` khuyến nghị mapping function nên **ngắn và đơn giản**, không cố cập nhật các mapping khác của chính map trong khi callback đang thực thi. Đây không phải nơi để làm I/O, mở transaction remote hoặc điều khiển nhiều key theo cách ad hoc.

Một câu lệnh duy nhất ở **mã nguồn Java** không đồng nghĩa một transaction. Ngược lại, một khối synchronized chứa nhiều câu lệnh có thể tạo critical section đúng nếu **mọi luồng liên quan** tôn trọng cùng khóa và hợp đồng không đòi durability.

## 8. Phương án A — một monitor/lock chung cho toàn bộ ledger in-memory

Với trạng thái nhỏ, một đối tượng ledger có thể sở hữu map và một lock chung:

```java
synchronized void transfer(...) {
    // Validate, trừ A, cộng B trong cùng monitor.
}

synchronized Snapshot snapshot() {
    // Đọc cả A, B trong cùng monitor.
}
```

Ưu điểm:

- Dễ hiểu và dễ chứng minh invariant.
- Transfer và những reader dùng **cùng monitor** không chen vào giữa các bước.
- Có thể validate đầy đủ **trước khi mutation**.
- Hợp với một tiến trình/instance nhỏ và ít contention.

Giới hạn:

- Mỗi transfer phải đợi nhau: lock có thể trở thành bottleneck.
- Nếu code khác giữ tham chiếu tới map và đọc trực tiếp **không lấy lock**, nó vẫn có thể quan sát trạng thái trung gian.
- Lock chỉ bảo vệ **trong cùng JVM/tiến trình**. Nó không đồng bộ với server khác có map riêng.
- Nếu process crash, `synchronized` không đảm bảo lưu bền hay rollback trên disk/database.
- Trong code production, không giữ lock qua I/O hoặc tác vụ callback không kiểm soát, vì dễ khiến tiến trình khác bị chặn.

**Điểm then chốt:** giải pháp đúng không chỉ là “writer lock”. Các reader cần snapshot nhất quán cũng phải **tuân thủ cùng giao thức đồng bộ**, hoặc nhận một aggregate immutable đã được publish atomically.

## 9. Ví dụ Java 8 số 3 — synchronized transfer và snapshot nhất quán

Tệp **`SynchronizedLedgerDemo.java`** chứa ledger với map private, mọi transfer và snapshot đều dùng monitor của cùng đối tượng. Hai thread thực hiện 1.000 lần chuyển ngược chiều; kiểm thử cả nhánh thiếu số dư.

```java
import java.util.concurrent.*;

public class SynchronizedLedgerDemo {
    static final class Ledger {
        private final ConcurrentHashMap<String, Integer> balances =
            new ConcurrentHashMap<>();

        Ledger() {
            balances.put("A", 2000);
            balances.put("B", 2000);
        }

        synchronized void transfer(String from,
                                   String to, int amount) {
            if (amount <= 0)
                throw new IllegalArgumentException("amount");

            Integer oldFrom = balances.get(from);
            Integer oldTo = balances.get(to);
            if (oldFrom == null || oldTo == null)
                throw new IllegalArgumentException("unknown account");

            if (from.equals(to)) return;
            if (oldFrom < amount)
                throw new IllegalStateException("insufficient funds");

            balances.put(from, oldFrom - amount);
            balances.put(to, oldTo + amount);
        }

        synchronized String snapshot() {
            return "A=" + balances.get("A")
                   + ",B=" + balances.get("B");
        }

        synchronized int sum() {
            return balances.get("A") + balances.get("B");
        }
    }

    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();

        Thread ab = new Thread(() -> {
            for (int i = 0; i < 1000; i++)
                ledger.transfer("A", "B", 1);
        }, "A-to-B");

        Thread ba = new Thread(() -> {
            for (int i = 0; i < 1000; i++)
                ledger.transfer("B", "A", 1);
        }, "B-to-A");

        ab.start();
        ba.start();
        ab.join();
        ba.join();

        check(ledger.sum() == 4000,
              "invariant total");
        check("A=2000,B=2000".equals(ledger.snapshot()),
              "two-way transfers");

        boolean rejected = false;
        try {
            ledger.transfer("A", "B", 3000);
        } catch (IllegalStateException ex) {
            rejected = true;
        }
        check(rejected && ledger.sum() == 4000,
              "failed validation makes no change");

        System.out.println("snapshot=" + ledger.snapshot());
        System.out.println("total=" + ledger.sum());
        System.out.println("insufficientRejected=" + rejected);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 SynchronizedLedgerDemo.java
java SynchronizedLedgerDemo
```

**Stdout đã kiểm chứng:**

```text
snapshot=A=2000,B=2000
total=4000
insufficientRejected=true
PASS
```

**Vì sao chương trình này tốt hơn ví dụ lỗi?**

- Tất cả thao tác liên quan đến hai mapping diễn ra **trong cùng monitor**.
- `snapshot()` và `sum()` cũng lấy monitor, nên không đọc xen giữa lúc chuyển tiền.
- Kiểm số dư đủ được làm **trước khi trừ/cộng**. Thử chuyển 3.000 từ A khi chỉ có 2.000 bị từ chối và tổng vẫn 4.000.
- Các thread khác phải qua API của `Ledger`, map được giữ **private**. Nếu bạn lộ map qua getter hoặc để code khác đọc trực tiếp, giao thức bảo vệ snapshot có thể bị phá.
- Ví dụ dùng `int` để ngắn gọn; hệ thống tiền thật không nên tùy tiện dùng số thực nhị phân hoặc một int không xét tràn số. Cân nhắc số nguyên ở đơn vị nhỏ nhất với overflow validation, hoặc `BigDecimal` khi domain yêu cầu.

**Một nhận xét thiết kế:** trong demo này, vì mọi truy cập đều được bảo vệ bởi một monitor chung, bản thân `ConcurrentHashMap` không phải điều kiện bắt buộc để bảo vệ critical section: một `HashMap` được encapsulate đầy đủ cũng có thể hoạt động. Dùng ConcurrentHashMap không thay thế monitor, và monitor không tự thêm durability.

## 10. Phương án B — khóa các tài khoản liên quan theo thứ tự thống nhất

Khi nhiều chuyển tiền giữa các cặp tài khoản độc lập, một lock chung có thể làm giảm throughput. Một lựa chọn là dùng **lock theo tài khoản**:

1. Xác định hai tài khoản tham gia.
2. Lấy lock của cả hai theo **thứ tự tổng quát cố định** (ví dụ sort theo account ID).
3. Validate số dư/điều kiện.
4. Cập nhật cả hai mapping trong critical section.
5. Thả lock theo thứ tự ngược, ngay cả khi exception xảy ra.
6. Mọi reader cần snapshot cùng hai account cũng phải lấy **đủ hai lock với cùng thứ tự**.

**Vì sao phải sắp thứ tự khóa?**

```text
Không có thứ tự thống nhất:

Thread 1: giữ lock A -> chờ lock B
Thread 2: giữ lock B -> chờ lock A

=> deadlock.
```

Khi mọi transfer đều lấy A trước B (hoặc key nhỏ trước key lớn), không xảy ra chu trình chờ giữa hai lock theo cách trên.

### Hạn chế của lock theo key

- Quản lý vòng đời lock: nếu account mới/xóa, việc tạo và thu hồi lock phải an toàn, tránh thay lock khi vẫn có thread dùng lock cũ.
- Snapshot qua nhiều hơn hai account cần cùng giao thức lock đủ các key, theo thứ tự thống nhất.
- Có thể gây nghẽn nếu nhiều transfer cùng chạm một tài khoản nóng.
- Không hỗ trợ transaction liên JVM hoặc database; chỉ bảo vệ vùng nhớ trong tiến trình.
- Không nên gọi I/O hoặc callback không kiểm soát trong khi giữ nhiều lock.
- Khi có exception giữa hai mutation trong critical section, reader tuân thủ lock không thấy trạng thái giữa chừng, nhưng **dữ liệu có thể đã bị sửa một nửa khi lock được thả do exception**. Do đó phải validate trước, làm mutation ngắn, hạn chế chỗ có thể ném exception, và thiết kế recovery/rollback nếu có thao tác thất bại.

**Quan trọng:** lock ngăn luồng khác chen vào; nó không phải một cơ chế rollback. Nói “đã khóa cả hai nên giao dịch ACID” là không chính xác.

## 11. Ví dụ Java 8 số 4 — hai lock cố định, luôn lấy A trước B

Để code dễ kiểm thử, **`OrderedAccountLocksDemo.java` chỉ hỗ trợ đúng hai tài khoản A và B**. Phương thức `withBothLocks` luôn khóa A rồi B dù chiều chuyển tiền là A→B hay B→A. Ứng dụng nhiều tài khoản cần mở rộng giao thức bằng sort account IDs và quản lý lock registry ổn định.

```java
import java.util.concurrent.*;
import java.util.concurrent.locks.*;

public class OrderedAccountLocksDemo {
    static final class Ledger {
        private final ConcurrentHashMap<String, Integer> balances =
            new ConcurrentHashMap<>();
        private final ConcurrentHashMap<String, ReentrantLock> locks =
            new ConcurrentHashMap<>();

        Ledger() {
            balances.put("A", 1000);
            balances.put("B", 1000);
            locks.put("A", new ReentrantLock());
            locks.put("B", new ReentrantLock());
        }

        private void withBothLocks(Runnable action) {
            ReentrantLock left = locks.get("A");
            ReentrantLock right = locks.get("B");

            left.lock();
            try {
                right.lock();
                try {
                    action.run();
                } finally {
                    right.unlock();
                }
            } finally {
                left.unlock();
            }
        }

        void transfer(String from, String to, int amount) {
            if (amount <= 0 || !balances.containsKey(from)
                    || !balances.containsKey(to))
                throw new IllegalArgumentException("arguments");

            if (from.equals(to)) return;

            withBothLocks(() -> {
                int current = balances.get(from);
                if (current < amount)
                    throw new IllegalStateException("insufficient funds");

                balances.put(from, current - amount);
                balances.put(to, balances.get(to) + amount);
            });
        }

        int[] snapshot() {
            int[] result = new int[2];
            withBothLocks(() -> {
                result[0] = balances.get("A");
                result[1] = balances.get("B");
            });
            return result;
        }
    }

    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();

        Thread ab = new Thread(() -> {
            for (int i = 0; i < 500; i++)
                ledger.transfer("A", "B", 1);
        }, "A-to-B");

        Thread ba = new Thread(() -> {
            for (int i = 0; i < 500; i++)
                ledger.transfer("B", "A", 1);
        }, "B-to-A");

        ab.start();
        ba.start();
        ab.join();
        ba.join();

        int[] result = ledger.snapshot();
        check(result[0] == 1000 && result[1] == 1000,
              "two-key transfer with both locks");

        System.out.println("A=" + result[0]);
        System.out.println("B=" + result[1]);
        System.out.println("total=" + (result[0] + result[1]));
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 OrderedAccountLocksDemo.java
java OrderedAccountLocksDemo
```

**Stdout đã kiểm chứng:**

```text
A=1000
B=1000
total=2000
PASS
```

**Điểm thực hành:**

- Có hai đối tượng ReentrantLock, nhưng chúng được lấy **theo cùng thứ tự A rồi B** trong mọi đường chuyển và đọc snapshot.
- Lock được thả trong `finally`, kể cả khi callback ném exception.
- `snapshot()` đọc cả hai giá trị bên trong cùng critical section. Nó không phải hai lệnh get tự do ở ngoài.
- Cả hai thread thực hiện 500 lần chuyển ngược chiều. Vì các số dư ban đầu đủ lớn, thứ tự scheduling không gây lỗi thiếu số dư.
- Đây là mô hình **minh họa việc phối hợp hai lock trong một JVM**, không phải thư viện ledger đa tài khoản production: không có persistence, transaction log, timeout, idempotency, định nghĩa overflow hay quy tắc tạo/xóa account động.
- Kiểm tra `containsKey` bên ngoài lock trong ví dụ an toàn chỉ do **tập hai tài khoản cố định** và không có operation xóa. Với tập account động, kiểm tồn tại phải là một phần của giao thức đồng bộ.

## 12. Phương án C — gom bất biến nhiều trường vào một giá trị immutable dưới một key

Nếu có một aggregate nhỏ cần luôn nhất quán và thuộc **một chủ sở hữu logic**, bạn có thể lưu hai số dư **bên trong một immutable value**:

```java
final class Pair {
    final int a;
    final int b;

    Pair(int a, int b) {
        this.a = a;
        this.b = b;
    }
}
```

Map chỉ có một mapping chứa toàn bộ aggregate:

```java
ConcurrentHashMap<String, Pair> map = new ConcurrentHashMap<>();
map.put("ledger", new Pair(100, 100));
```

Khi cần cập nhật cặp:

```java
map.compute("ledger", (key, oldPair) ->
    new Pair(oldPair.a - 30, oldPair.b + 30));
```

Từ góc nhìn reader gọi `map.get("ledger")`, nó nhận tham chiếu tới **một Pair hoàn chỉnh**: hoặc phiên bản trước hoặc phiên bản sau. Vì các trường final và object immutable, reader không thấy “a mới, b cũ” **trong cùng phiên bản Pair**.

### Đây có phải transaction nhiều khóa không?

**Không.** Chúng ta đã **đổi mô hình dữ liệu** để chuyển bất biến vốn trải trên hai map keys thành **một value gắn với một map key**. Do đó có thể tận dụng atomic compute cho một mapping. Đây là giải pháp hợp lý khi aggregate nhỏ và có thể cập nhật trọn trong bộ nhớ.

Đánh đổi:

- Tăng contention trên một key nóng.
- Mỗi mutation tạo object mới; nếu aggregate lớn, chi phí copy/GC có thể cao.
- Khó đáp ứng cập nhật độc lập cực thường xuyên trên các phần của aggregate.
- Không tự thực hiện commit lên database hoặc message broker.
- Không phù hợp nếu dữ liệu phải chia cho nhiều node độc lập mà không có giao thức nhất quán phân tán.

**Không nên dùng một giá trị mutable rồi tin ConcurrentHashMap tự bảo vệ các field của value.** Map bảo vệ mapping, không tự biến các đối tượng được lưu trong map thành thread-safe.

## 13. Ví dụ Java 8 số 5 — immutable aggregate, một key, nhiều thread

Tệp **`ImmutableAggregateDemo.java`** đặt hai số dư trong một Pair bất biến, dùng `compute` để cập nhật theo một key và giữ invariant tổng. Hai thread chuyển A→B và hai thread chuyển B→A; mỗi thread chạy 500 lần.

```java
import java.util.concurrent.*;

public class ImmutableAggregateDemo {
    static final class Pair {
        final int a;
        final int b;

        Pair(int a, int b) {
            this.a = a;
            this.b = b;
        }
    }

    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Pair> map =
            new ConcurrentHashMap<>();

        Pair original = new Pair(1000, 1000);
        map.put("ledger", original);

        Thread[] threads = new Thread[4];

        for (int i = 0; i < threads.length; i++) {
            final boolean ab = (i % 2 == 0);

            threads[i] = new Thread(() -> {
                for (int j = 0; j < 500; j++) {
                    map.compute("ledger", (key, oldPair) -> {
                        if (ab) {
                            if (oldPair.a < 1)
                                throw new IllegalStateException("A empty");
                            return new Pair(
                                oldPair.a - 1, oldPair.b + 1);
                        }

                        if (oldPair.b < 1)
                            throw new IllegalStateException("B empty");
                        return new Pair(
                            oldPair.a + 1, oldPair.b - 1);
                    });
                }
            }, "aggregate-" + i);

            threads[i].start();
        }

        for (Thread worker : threads) worker.join();

        Pair actual = map.get("ledger");
        check(actual.a == 1000 && actual.b == 1000,
              "aggregate result");
        check(actual.a + actual.b == 2000,
              "aggregate invariant");
        check(original.a == 1000 && original.b == 1000,
              "original immutable snapshot");

        System.out.println("finalA=" + actual.a);
        System.out.println("finalB=" + actual.b);
        System.out.println("finalTotal=" + (actual.a + actual.b));
        System.out.println("originalA=" + original.a);
        System.out.println("originalB=" + original.b);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ImmutableAggregateDemo.java
java ImmutableAggregateDemo
```

**Stdout đã kiểm chứng:**

```text
finalA=1000
finalB=1000
finalTotal=2000
originalA=1000
originalB=1000
PASS
```

**Tại sao bất biến được giữ?**

- Mỗi lần `compute("ledger", ...)` nhận Pair hiện có và tạo **một Pair mới** có tổng giữ nguyên.
- Việc publish Pair mới diễn ra trong phép cập nhật nguyên tử **trên đúng key "ledger"**.
- Reader lấy Pair bằng một `get` thấy một snapshot pair nhất quán; không đọc a/b từ hai mapping riêng.
- Pair gốc vẫn giữ 1000/1000 vì immutable, chứng minh snapshot đã publish trước đó không bị sửa tại chỗ.
- Giá trị `final` cũng hỗ trợ safe publication khi object được xây dựng hợp lệ rồi công bố qua cơ chế thread-safe của map.

**Giới hạn thiết kế:** ví dụ giả định mọi thay đổi A/B đều đi qua một Pair duy nhất trong map và không có hệ thống bên ngoài cần commit chung. Nếu phải ghi cùng lúc hai bản ghi SQL khác nhau, single-key compute trong JVM không thay được database transaction.

## 14. Phương án D — AtomicReference và CAS cho toàn bộ state bất biến

Một cách khác để publish **toàn bộ state** như một object immutable là:

```java
AtomicReference<State> ref =
    new AtomicReference<>(new State(100, 100));
```

Khi transfer, dùng vòng lặp compare-and-set:

1. Đọc phiên bản State hiện tại.
2. Validate bất biến.
3. Tạo State mới.
4. Dùng `compareAndSet(before, after)` để thay **nguyên tử một tham chiếu**.
5. Nếu có một update cạnh tranh đã thay ref, đọc lại và tính lại từ state mới.

Đây là **optimistic concurrency** cho một aggregate in-memory. Nó không dùng hai mapping keys cần commit độc lập, mà cập nhật **một tham chiếu tới snapshot toàn bộ state**.

### CAS đảm bảo điều gì và không đảm bảo điều gì?

Nó giúp reader của `ref.get()` thấy một State đã được publish trọn vẹn, miễn là State immutable và mọi mutation đi qua cùng AtomicReference. CAS thất bại khi một thread khác thay ref, nên cần retry.

Nhưng CAS **không**:

- Commit một transaction vào nhiều database rows.
- Bảo đảm durable khi process crash.
- Cập nhật đồng thời cache ở server khác hoặc hệ thống bên ngoài.
- Cho phép callback có side effect không idempotent trong vòng lặp mà không có thiết kế riêng: callback có thể được tính lại nhiều lần.
- Loại bỏ yêu cầu xử lý contention, starvation, overflow hoặc validation domain.

### Đừng thực hiện side effect trước CAS thành công

Đoạn sau là sai về thiết kế nếu gửi email/chuyển tiền thật mỗi khi tính state mới:

```java
// Không nên làm kiểu này trong retry loop:
for (;;) {
    State before = ref.get();
    sendPayment(); // Side effect có thể xảy ra nhiều lần!
    State after = new State(...);
    if (ref.compareAndSet(before, after)) break;
}
```

Một vòng CAS có thể retry nhiều lần. Chỉ đặt **phép tính thuần** và tạo object mới trong vòng lặp. Side effect bên ngoài cần quy trình commit/transaction/outbox riêng sau khi trạng thái được chấp thuận theo domain.

## 15. Ví dụ Java 8 số 6 — AtomicReference + immutable State + compareAndSet

Tệp **`AtomicReferenceLedgerDemo.java`** bảo vệ cùng lúc hai số dư trong một State immutable. Hai thread chuyển tiền ngược chiều, CAS đảm bảo mỗi lần chuyển được publish thành **một phiên bản state duy nhất**.

```java
import java.util.concurrent.atomic.*;

public class AtomicReferenceLedgerDemo {
    static final class State {
        final int a;
        final int b;

        State(int a, int b) {
            this.a = a;
            this.b = b;
        }
    }

    static final class Ledger {
        private final AtomicReference<State> ref =
            new AtomicReference<>(new State(5000, 5000));

        void transfer(boolean aToB, int amount) {
            if (amount <= 0)
                throw new IllegalArgumentException("amount");

            for (;;) {
                State before = ref.get();
                int from = aToB ? before.a : before.b;

                if (from < amount)
                    throw new IllegalStateException("insufficient funds");

                State after = aToB
                    ? new State(
                        before.a - amount, before.b + amount)
                    : new State(
                        before.a + amount, before.b - amount);

                if (ref.compareAndSet(before, after)) return;
            }
        }

        State snapshot() {
            return ref.get();
        }
    }

    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();

        Thread ab = new Thread(() -> {
            for (int i = 0; i < 1000; i++)
                ledger.transfer(true, 1);
        }, "A-to-B");

        Thread ba = new Thread(() -> {
            for (int i = 0; i < 1000; i++)
                ledger.transfer(false, 1);
        }, "B-to-A");

        ab.start();
        ba.start();
        ab.join();
        ba.join();

        State result = ledger.snapshot();
        check(result.a == 5000 && result.b == 5000,
              "equal transfers");
        check(result.a + result.b == 10000,
              "sum invariant");

        System.out.println("A=" + result.a);
        System.out.println("B=" + result.b);
        System.out.println("total=" + (result.a + result.b));
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 AtomicReferenceLedgerDemo.java
java AtomicReferenceLedgerDemo
```

**Stdout đã kiểm chứng:**

```text
A=5000
B=5000
total=10000
PASS
```

**Lý giải:**

- Mỗi State có hai trường final, không bị mutate sau khi publish.
- CAS thay thế **một tham chiếu** chỉ khi state chưa bị thread khác thay. Nếu CAS thất bại, vòng lặp đọc lại và tính từ trạng thái mới.
- Hai luồng cùng cố update một state không làm mất update vì chỉ phiên bản khớp `before` mới được chấp thuận.
- Reader `snapshot()` lấy **một State** rồi đọc hai field từ cùng snapshot.
- Nếu nhiều thao tác khác sửa data **ngoài ref**, bất biến hệ thống rộng hơn không tự được đảm bảo.
- Demo chỉ mô tả trạng thái trong một process, không mô tả transaction bền vững hay multi-service.

## 16. Vì sao mutable object trong ConcurrentHashMap vẫn có thể không an toàn?

Giả sử:

```java
// Không phải chương trình standalone.
final class MutablePair {
    volatile int a;
    volatile int b;
}

ConcurrentHashMap<String, MutablePair> map = new ConcurrentHashMap<>();
map.put("ledger", new MutablePair());

// Giả sử một thread cập nhật:
MutablePair pair = map.get("ledger");
pair.a = 70;
pair.b = 130;
```

ConcurrentHashMap bảo vệ việc **lưu/lấy tham chiếu** tới MutablePair, nhưng các thay đổi hai field của object đó **không tự thành một transaction**. Kể cả dùng `volatile` cho từng field, hai lần gán riêng vẫn có thể bị reader quan sát xen giữa.

Với `ArrayList`, `HashMap` hoặc object mutable làm value, còn có vấn đề thread-safety riêng của object được lưu: map thread-safe **không tự làm mọi collection value thread-safe**.

Giải pháp tùy domain:

- Đổi value thành immutable snapshot và thay tham chiếu bằng `compute` hoặc CAS.
- Đồng bộ nhất quán quanh cả quá trình mutate và read.
- Dùng collection/value có concurrency semantics phù hợp **nếu invariant chỉ ở phạm vi đó**.
- Nếu cần transaction trên nhiều bản ghi ngoài JVM, dùng transactional data store.

### Counter per key: LongAdder có phải giao dịch nhiều khóa không?

Không. `LongAdder` hữu ích cho counter có contention cao; có thể kết hợp với `ConcurrentHashMap<String,LongAdder>`, ví dụ khởi tạo value bằng `computeIfAbsent`. Nhưng tổng qua nhiều LongAdder hoặc các bước cập nhật nhiều key vẫn **không trở thành snapshot nguyên tử**. Ngoài ra, `LongAdder.sum()` có semantics phù hợp thống kê nhưng không nên coi là đọc snapshot linearizable trong khi đang có update cạnh tranh.

Chọn counter cho telemetry khác chọn cấu trúc giữ **số dư tài chính với bất biến xuyên tài khoản**.

## 17. get hai khóa không phải đọc một snapshot nhất quán

Ngay cả khi transfer đã dùng một lock đúng, một reader làm:

```java
int a = balances.get("A");
int b = balances.get("B");
return a + b;
```

**mà không lấy cùng lock** vẫn có thể thấy giá trị ở hai thời điểm khác nhau. Với nhiều transfer đang chạy, reader còn có thể ghép A của phiên bản này với B của phiên bản khác.

Để có snapshot nhất quán:

- Với **một monitor chung**, reader phải lấy monitor trước khi đọc cả hai.
- Với **lock theo key**, reader phải lấy **đủ các lock** liên quan theo cùng thứ tự.
- Với **immutable aggregate + một key**, reader lấy value một lần rồi đọc các field từ value đó.
- Với **AtomicReference<State>**, reader lấy ref một lần và đọc một State.
- Với database, dùng **transaction và isolation level** phù hợp để đọc một snapshot theo contract.

Một vòng lặp qua `map.entrySet()` không phải phép “freeze” ConcurrentHashMap: iterator **weakly consistent**, có thể phản ánh một số update trong khi đi qua map mà không đưa ra snapshot giao dịch. Các phép bulk processing/aggregation khi map đang thay đổi cũng không được tự suy là transaction.

### Tại sao new HashMap<>(concurrentMap) không đủ?

Sao chép map đang thay đổi có thể thu được dữ liệu ở nhiều thời điểm khác nhau trong quá trình copy. Không có hợp đồng rằng constructor sao chép biến các cập nhật đồng thời thành **một trạng thái nhất quán ở một thời điểm**.

Nếu muốn snapshot, cần một giao thức lock/phiên bản hoặc dữ liệu immutable được publish atomically. Sau khi đã tạo snapshot hợp lệ, có thể đưa nó vào `Collections.unmodifiableMap` để ngăn caller sửa snapshot, nhưng **unmodifiable không chứng minh quá trình lấy snapshot là atomic**.

## 18. Các mức bảo đảm thường gặp: atomicity, isolation, durability

Đối với ứng dụng quản lý nghiệp vụ, cần hỏi thêm ngoài câu “thread-safe chưa?”.

| Thuộc tính | Ý nghĩa | ConcurrentHashMap tự đảm bảo? |
| --- | --- | --- |
| Thao tác một key có bảo đảm atomic theo API | Update mapping không bị chen giữa trong phạm vi thao tác | **Có đối với các API atomic tương ứng** |
| Atomic commit nhiều key | Hoặc tất cả thay đổi, hoặc không thay đổi | **Không** |
| Snapshot nhất quán xuyên nhiều key khi đọc | Reader không thấy kết hợp của nhiều phiên bản | **Không mặc định** |
| Rollback tự động nếu bước 2 thất bại | Trả trạng thái về trước transaction | **Không** |
| Durability qua process crash | Dữ liệu đã commit còn sau restart | **Không, chỉ là memory** |
| Transaction trên nhiều server/nút | Các tiến trình khác cùng tuân một commit | **Không** |
| Isolation level kiểu SQL | Read committed/repeatable read/serializable | **Không có contract transaction SQL** |
| Idempotency của chuyển tiền | Retry không chuyển trùng | **Không** |

**Một critical section đúng cũng không tự có ACID đầy đủ.** Nó có thể bảo vệ atomicity/isolation in-memory cho những participant tuân thủ lock, nhưng không tạo bền vững hay distributed commit.

### Nếu cần giao dịch nhiều khóa thật sự?

Hãy ưu tiên kiến trúc lưu dữ liệu phù hợp:

1. **Một database transaction** khi nhiều row/bảng nằm trong cùng transactional datastore.
2. **Pessimistic row locking** hoặc isolation đủ mạnh, cộng với validation toàn bộ bất biến trước commit.
3. **Optimistic locking/version column** và retry có kiểm soát khi dùng compare-and-set ở database.
4. **Outbox/idempotency** khi phải gửi message hoặc tích hợp side effect ngoài transaction.
5. **Saga/compensation** khi hoạt động trải qua nhiều service hoặc datastore không hỗ trợ transaction chung, với semantics được giải thích rõ.
6. Đối với trạng thái chỉ cần **một JVM** và không cần durability, có thể chọn monitor, ordered locks hoặc immutable aggregate/CAS như ví dụ.

Lựa chọn cụ thể phụ thuộc tải, số account, SLA, yêu cầu lỗi/crash, khả năng scale, hệ lưu trữ và độ nghiêm ngặt của invariant.

## 19. Kiểm soát lỗi giữa hai thay đổi

Ngay cả khi có lock, đoạn:

```java
lock.lock();
try {
    debit();
    credit(); // Có thể ném exception.
} finally {
    lock.unlock();
}
```

không tự rollback debit nếu credit thất bại. Nó chỉ làm các luồng **tuân lock** không quan sát được hai lời gọi đan xen trong lúc lock được giữ.

Để xử lý:

- Thực hiện **toàn bộ validation trước mutation** trong lock.
- Giữ đường mutation ngắn và tránh I/O/remote calls khi đã thay một phần state.
- Kiểm tràn số: dùng `Math.addExact` hoặc tính toán có kiểm tra phạm vi trước commit nếu dùng long/int.
- Khi state là immutable, tạo bản mới hoàn chỉnh **trước khi publish**; nếu constructor/validation ném exception, mapping/ref cũ chưa bị thay.
- Với cơ sở dữ liệu, dùng transaction có rollback tự động theo hợp đồng.
- Nếu giao dịch trải nhiều service, định nghĩa **compensation và trạng thái trung gian** thay vì giả vờ rollback đồng bộ giữa nhiều hệ thống.

### Ví dụ snapshot immutable có lợi gì khi exception xảy ra?

Trong `map.compute("ledger", callback)`, callback tạo một object immutable mới trước khi map publish nó. Nếu callback **ném exception** theo hợp đồng của `ConcurrentHashMap.compute`, mapping hiện tại không bị thay bởi phép compute đó. Điều này làm việc bảo toàn invariant trong một mapping dễ hơn so với sửa nhiều object mutable riêng.

**Nhưng không đưa side effect vào callback** như gửi email hoặc ghi database, bởi lỗi ở lần tính value không tự hoàn tác các tác dụng bên ngoài.

## 20. Xác thực nghiệp vụ trước commit và các tình huống cạnh tranh

Hệ thống chuyển số dư còn có các ràng buộc thường gặp:

- Account nguồn và đích phải tồn tại, không bị đóng.
- Amount phải dương, không overflow, cùng đơn vị.
- Số dư nguồn không bị âm theo policy.
- Tổng hai số dư giữ nguyên nếu không có phí/điều chỉnh.
- Một transaction ID chỉ được thực hiện một lần.
- Nếu có transaction đồng thời, hai lần rút không được cùng tiêu số dư ban đầu.
- Nếu có retry, phải biết thao tác trước đã commit hay chưa.
- Reader hiển thị số dư và lịch sử phải tuân một nguồn dữ liệu nhất quán.

Một check độc lập:

```java
if (map.get("A") >= amount) {
    map.computeIfPresent("A", (k,v) -> v - amount);
}
```

**không nguyên tử như một check-and-update**. Một transfer khác có thể rút tiền giữa `get` và `computeIfPresent`, làm số dư âm. Nếu invariant chỉ thuộc A, có thể đưa check vào **cùng callback compute của A**. Nếu invariant bao gồm **A và B cùng lúc**, cần giao thức atomic trên cả hai hoặc aggregate state như đã trình bày.

### Tách trách nhiệm validation và mutation

Khi có nhiều điều kiện phụ thuộc các key, kiểm trước khi lấy lock rồi tin kết quả không thay đổi là một TOCTOU bug (*time-of-check to time-of-use*). Cần kiểm điều kiện **trong critical section**, hoặc đọc version và CAS/retry với dữ liệu bất biến.

Nếu transaction có nhiều key, việc map thread-safe không thay thế một unit-of-work đảm bảo các điều kiện được kiểm trên **cùng một phiên bản trạng thái**.

## 21. Bảo đảm visibility và publication không đồng nghĩa invariant xuyên khóa

`ConcurrentHashMap` có các bảo đảm về memory consistency cho các thao tác truy cập/cập nhật tương ứng. Khi một thread publish một value đúng cách, thread khác có thể quan sát object đã được khởi tạo theo hợp đồng.

Nhưng:

- Visibility tốt của mapping A không khiến mapping B tự đồng bộ thành cùng phiên bản.
- Việc `get(A)` thấy cập nhật mới không bảo đảm `get(B)` đã thấy bước tiếp theo.
- `volatile` ở hai field riêng không tạo atomic update cho cả hai.
- `synchronized` trên một object chỉ bảo vệ vùng code lấy đúng monitor đó.
- `ReentrantLock` ở hai account cần được lấy **cả hai** nếu invariant liên quan hai account.
- CAS trên một AtomicReference chỉ bảo vệ **một tham chiếu**; đây là lý do ta gói toàn bộ invariant vào một immutable State trước khi publish.

Câu cần tự hỏi là: **đâu là linearization point của toàn bộ operation mà người dùng quan tâm?** Với ví dụ chuyển tiền bằng một Pair immutable dưới một key, điểm publish là cập nhật mapping/ref. Với hai thao tác compute riêng, **không có một điểm commit chung**.

## 22. Các bẫy của iteration và bulk operation

`ConcurrentHashMap.entrySet()` trả view của các mapping; iterator không fail-fast theo cùng cách với một số collection khác, nhưng nó **không cung cấp snapshot transaction** khi concurrent updates diễn ra.

Ví dụ:

```java
// Đoạn minh họa, map có thể đang thay đổi.
int total = 0;
for (Integer balance : balances.values()) {
    total += balance;
}
```

Đoạn tính tổng có thể đọc trạng thái từ các thời điểm khác nhau. Với một bảng giá trị thay đổi đồng thời, tổng kiểu này có thể phù hợp **telemetry xấp xỉ** nhưng không phù hợp để chứng minh bất biến tài chính.

Các phương thức như `forEach`, `search` và `reduce` trong ConcurrentHashMap hỗ trợ xử lý đồng thời theo API, nhưng không làm tập dữ liệu “đóng băng” để có snapshot giao dịch. Tương tự, `size`/`mappingCount` hoặc các phép thống kê khi đang có concurrent modification không phải công cụ chứng minh transaction trên nhiều key.

Khi yêu cầu kết quả nhất quán:

1. Xác định độ mạnh của snapshot cần có.
2. Chọn giao thức đồng bộ hoặc phiên bản immutable.
3. Tách đọc đang cần gần thời gian thực với đọc cần consistency mạnh.
4. Nếu dùng DB, chọn isolation theo yêu cầu báo cáo và kiểm behavior của driver/ORM.

## 23. Những phương án phổ biến và khi nào chọn

| Cách làm | Phạm vi bảo đảm | Lợi thế | Giới hạn |
| --- | --- | --- | --- |
| `merge/compute` một key | Một mapping | Đơn giản, không lost update trên key | Không bao trùm nhiều key |
| Monitor chung | Một instance và mọi participant tuân monitor | Dễ chứng minh invariant | Contention, không durable |
| Lock theo account có thứ tự | Nhiều account trong một JVM nếu tất cả participant tuân protocol | Cho phép cặp account độc lập hoạt động song song ở thiết kế tổng quát | Quản lý lock khó, dễ lỗi deadlock nếu sai thứ tự |
| Immutable aggregate trong một CHM key | Một value chứa toàn bộ invariant | Reader lấy một snapshot hoàn chỉnh | Hot key, chi phí copy |
| `AtomicReference<State>` + CAS | Một phiên bản immutable state | Không cần blocking monitor cho phép publish | Retry/contended CAS, một process |
| Database transaction | Các bản ghi trong transactional scope | Atomic commit/rollback/durability theo DB | Chi phí I/O/lock/isolation, cần thiết kế |
| Distributed saga/outbox | Nhiều service và side effect | Phù hợp workflow phân tán | Eventual consistency, compensation/phức tạp |

**Không có “một cấu trúc đúng cho mọi bài toán”.** Nếu chỉ đếm lượt xem per key, dùng ConcurrentHashMap + merge/LongAdder có thể là hợp lý. Nếu cần chuyển tiền thật giữa các account lưu ở database, không chỉ dùng một lock local trong JVM hoặc ConcurrentHashMap.

## 24. Ma trận test concurrency và bất biến

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Lost update get/put | Hai thread đọc cùng 0 rồi cùng put 1 | Kết quả có thể là 1, không phải 2 |
| Atomic merge một key | Bốn thread, mỗi thread 1.000 merge | Tổng chính xác 4.000 |
| Hai-key transfer không lock | Dừng giữa debit A và credit B | Observer thấy tổng trung gian 170 |
| Sau transfer hai-key | Cho credit B hoàn tất | Tổng trở lại 200 |
| Process/exception sau debit | Lỗi trước credit | Không tự rollback bằng CHM |
| Monitor transfer | Hai luồng chuyển 1.000 lần ngược chiều | Tổng bất biến, số dư cuối đúng |
| Monitor reader | Snapshot lấy cùng lock | Không xen vào giữa transfer |
| Insufficient funds | Transfer vượt số dư | Bị từ chối trước thay đổi |
| Ordered account locks | Hai luồng A↔B, luôn khóa A rồi B | Không deadlock trong demo, tổng đúng |
| Reader dùng lock | Snapshot khóa cả A, B | Đọc được cặp nhất quán |
| Reader không dùng lock | Đọc A/B trực tiếp | Có thể thấy trạng thái rời |
| Immutable Pair | Nhiều luồng compute một key | Tổng giữ nguyên theo mỗi Pair |
| Old immutable object | Giữ reference Pair trước update | Giá trị cũ không bị mutate |
| AtomicReference CAS | Hai luồng cập nhật State | Không mất update, snapshot nguyên tử |
| CAS contention | compareAndSet thất bại, thử lại | Tính lại từ State mới |
| Mutable value in CHM | Value chứa hai field mutable | Map không bảo vệ mutation xuyên field |
| Iterator dưới concurrent writes | Map liên tục cập nhật | Không assume transaction snapshot |
| Failure trong callback compute | Callback ném trước khi return value | Mapping của phép compute giữ nguyên |
| Exception trong hai-key update | Mutation thứ hai ném | Cần rollback/recovery riêng |
| Multiple map instances | Hai JVM dùng hai map độc lập | Lock trong một JVM không đồng bộ node khác |
| DB transaction rollback | Bước thứ hai SQL thất bại | Transaction rollback theo hợp đồng DB |
| Retry sau timeout | Có side effect chưa rõ outcome | Idempotency, không double commit |
| Stress với nhiều khóa | Transfer đồng thời giữa nhiều pair | Tổng, nonnegative, no-deadlock |
| Livelock/starvation | CAS retry kéo dài | Đo contention, có chính sách giới hạn |
| Integer overflow | Cộng số dư lớn | Validate/Math.addExact, không silently wrap |

**Test phải nhìn vào bất biến, không chỉ “không ném exception”.** Một race có thể kết thúc mà không throw nhưng dữ liệu vẫn sai. Dùng `CountDownLatch` để dựng lịch interleaving có chủ đích; chạy stress với nhiều thread nhiều lần để tìm lỗi khác. Đừng dựa vào một lần thực thi nhanh và kết luận không có race.

### QA các ví dụ trong bài

Sáu chương trình đã được biên dịch với `javac --release 8 -encoding UTF-8` trên JDK thử nghiệm, rồi chạy bằng `java`. Các test kiểm:

- Chênh lệch `get+put` so với `merge`.
- Trạng thái trung gian 170 và trạng thái cuối 200.
- Bất biến tổng trong monitor.
- Chuyển hai chiều với hai lock cố định.
- Immutable Pair qua compute.
- AtomicReference State qua CAS.

Các demo là **mô hình giáo dục** với số dư và khóa cố định; đừng sao chép nguyên xi làm giải pháp giao dịch tài chính production.

## 25. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `ConcurrentHashMap` biến mọi code thành transaction | Thấy trạng thái nửa chừng | Xác định phạm vi atomicity |
| `get` rồi `put` để tăng count | Lost update | `merge`/`compute` |
| Hai `compute` riêng để chuyển A→B | Không atomic cross-key | Lock chung, lock cả key, aggregate/DB |
| Cập nhật B bên trong `compute(A)` | Không commit chung, nguy cơ recursion/deadlock | Không mutate map khác trong mapping function |
| Chỉ khóa writer, reader đọc ngoài lock | Snapshot không nhất quán | Đồng bộ cả read lẫn write |
| Lộ map private qua getter rồi kỳ vọng bất biến | Caller bypass protocol | Encapsulation |
| Khóa A rồi B / B rồi A theo chiều transfer | Deadlock | Lock theo thứ tự cố định |
| Nghĩ lock có rollback | State đã thay một phần vẫn có thể tồn tại khi exception | Validate trước, immutable publication/DB txn |
| Nghĩ `synchronized` đủ trên nhiều JVM | Mỗi process có monitor riêng | Shared transactional store/distributed design |
| Lưu mutable object value rồi update fields riêng | Invariant qua fields bị thấy nửa chừng | Immutable snapshot hoặc lock |
| Đọc hai key bằng hai `get` rồi coi là snapshot | Hai thời điểm đọc khác nhau | Snapshot protocol |
| Sao chép CHM đang thay đổi rồi coi atomic | Snapshot có thể trộn phiên bản | Lock/immutable version |
| Dùng `LongAdder.sum()` để kiểm tổng tài chính trong lúc update | Không phải transaction snapshot | Mô hình có invariant mạnh |
| CAS loop có I/O side effect | Retry làm side effect lặp | Tính toán thuần trong CAS |
| Coi `compute` làm transaction SQL | Không durable, không rollback DB | Database transaction |
| Dùng mỗi `int` cho số tiền lớn | Overflow, precision | Long with checks/BigDecimal theo domain |
| Retry transfer thiếu transaction ID | Double-transfer | Idempotency key |
| Không kiểm tài khoản tồn tại trong lock | TOCTOU với account động | Validate trong giao thức đồng bộ |
| Bulk iteration để chứng minh invariant mạnh | Weakly consistent | Snapshot đúng contract |
| Dùng `putAll` hoặc `replaceAll` làm multi-key commit | Không có bảo đảm transaction toàn bộ | Lock/DB txn |
| Đo thời gian chạy rồi suy ra thread-safety | Race có thể hiếm | Deterministic interleaving + stress |
| Gán lỗi “ConcurrentHashMap không an toàn” | Chẩn đoán sai | Phân biệt operation atomic và business invariant |

## 26. Bài tập thực hành có đáp án

### Bài 1 — counter trên một key

**Đề:** ba thread cùng tăng counter 1.000 lần bằng `count=map.get(k); map.put(k,count+1)`. Có chắc kết quả là 3.000 không?

**Đáp án:** không. Dãy get–put không atomic, có thể lost update. Dùng `merge(k,1,Integer::sum)` hoặc `compute` cho cùng mapping; không thêm transaction hai khóa nếu chỉ có một key.

### Bài 2 — chuyển từ A sang B

**Đề:** A=100, B=100. Dùng hai `computeIfPresent` cập nhật A-30 và B+30. Mọi reader đều chắc chắn thấy tổng 200 chứ?

**Đáp án:** không. Reader có thể nhìn thấy A=70,B=100,tổng=170 giữa hai thao tác. Cần giao thức atomic xuyên hai account nếu invariant luôn phải đúng ở view được công bố.

### Bài 3 — reader không khóa

**Đề:** writer dùng `synchronized transfer`, nhưng endpoint báo cáo đọc trực tiếp map bằng hai `get`. Snapshot đã an toàn chưa?

**Đáp án:** chưa. Reader không tham gia cùng monitor, vẫn có thể đọc giữa hai mutation. Cần đọc qua API snapshot có lock hoặc dùng aggregate immutable được publish atomically.

### Bài 4 — hai lock theo chiều chuyển

**Đề:** thread A→B khóa A rồi B; thread B→A khóa B rồi A. Điều gì có thể xảy ra?

**Đáp án:** deadlock khi mỗi thread giữ một lock và chờ lock còn lại. Phải đặt **thứ tự khóa thống nhất** cho mọi chiều chuyển và cả snapshot.

### Bài 5 — immutable Pair

**Đề:** lưu `Pair(a,b)` immutable trong đúng một CHM key và update bằng `compute`. Reader lấy Pair một lần có thể thấy a mới và b cũ trong cùng Pair không?

**Đáp án:** không nếu Pair thật sự immutable và được publish đúng, vì reader tham chiếu đến một version hoàn chỉnh. Đây là atomic **một mapping chứa aggregate**, không phải multi-key transaction.

### Bài 6 — AtomicReference CAS

**Đề:** hai thread cùng đọc State trước, tạo State mới. Nếu cả hai gọi compareAndSet với cùng reference before, cả hai có thành công không?

**Đáp án:** không. Chỉ phép CAS khớp state hiện tại được publish; thread còn lại cần đọc state mới và retry. Phải tránh side effect trong vòng retry.

### Bài 7 — compute callback cập nhật map khác

**Đề:** để chuyển tiền, đặt `map.merge("B",...)` trong callback `map.compute("A",...)`. Có được bảo đảm cùng commit không?

**Đáp án:** không. Scope atomic của compute A không tự mở rộng sang B. Callback cũng không nên cập nhật các mapping khác của cùng map; cần thiết kế lock/aggregate/transaction.

### Bài 8 — yêu cầu ACID

**Đề:** hai tài khoản lưu ở hai bản ghi SQL; ứng dụng chạy nhiều server. Một `synchronized` method trên mỗi server có đủ không?

**Đáp án:** không. Monitor chỉ có hiệu lực trong một JVM, không đảm bảo các server cùng lock hoặc rollback/durability trong database. Cần transaction DB và isolation phù hợp.

### Bài 9 — lỗi sau khi trừ tiền

**Đề:** đã trừ A xong nhưng cộng B ném exception, trong khi giữ lock. Sau `finally unlock`, dữ liệu có tự rollback không?

**Đáp án:** không. Lock loại bỏ interleaving của những participant tuân khóa, nhưng **không có rollback tự động**. Cần tính trước đầy đủ và publish immutable state, hoặc transaction có rollback thực sự.

### Bài 10 — snapshot nhiều key

**Đề:** `new HashMap<>(concurrentMap)` có luôn là ảnh chụp tức thời nhất quán không?

**Đáp án:** không khi nguồn đang có concurrent updates. Việc copy đọc các mapping tại những thời điểm khác nhau. Phải bảo vệ snapshot theo giao thức được chọn.

### Bài 11 — nhiều service

**Đề:** một lần cập nhật phải ghi database và gửi message tới queue. `map.compute` có giúp chúng commit cùng nhau không?

**Đáp án:** không. Cần transactional outbox hoặc pattern bảo đảm phù hợp, cùng idempotency/compensation nếu có nhiều hệ thống độc lập. Map chỉ quản lý bộ nhớ của tiến trình.

### Bài 12 — LongAdder

**Đề:** sử dụng `ConcurrentHashMap<String,LongAdder>` để đếm lượt truy cập. Có thể dùng nó làm sổ cái nhiều tài khoản được đảm bảo tổng chính xác mọi lúc không?

**Đáp án:** không. LongAdder phù hợp thống kê/count contention, không phải multi-key transactional state hay snapshot có invariant tài chính.

## 27. Câu hỏi tự kiểm tra

**1. Có phải hai thao tác atomic liên tiếp tự tạo một transaction atomic không?**  
Không. Atomicity không tự mở rộng qua nhiều lời gọi.

**2. ConcurrentHashMap bảo vệ điều gì?**  
Các thao tác map thread-safe và bảo đảm nguyên tử theo hợp đồng của từng phương thức, không tự bảo vệ invariant toàn hệ thống.

**3. Vì sao get rồi put có thể làm mất increment?**  
Hai thread có thể đọc cùng giá trị cũ rồi cùng ghi một giá trị mới.

**4. merge/compute giúp điều gì với một key?**  
Kết hợp logic cập nhật một mapping theo bảo đảm atomic của API.

**5. Vì sao chuyển A→B bằng hai compute chưa đủ?**  
Giữa hai lời gọi, trạng thái nửa chừng có thể hiển thị hoặc tồn tại sau lỗi.

**6. Muốn snapshot từ hai key dưới monitor phải làm gì?**  
Reader phải lấy cùng monitor với writer trong lúc đọc cả hai.

**7. Vì sao khóa theo key dễ deadlock?**  
Hai thread có thể lấy hai lock theo thứ tự ngược nhau và chờ lẫn nhau.

**8. Giá trị immutable trong một CHM key có lợi gì?**  
Cả invariant của aggregate được publish như một snapshot khi mapping cập nhật.

**9. AtomicReference.compareAndSet có tự lưu bền ra disk không?**  
Không. Nó chỉ cập nhật tham chiếu trong bộ nhớ theo ngữ nghĩa CAS.

**10. Có nên đặt I/O trong vòng CAS retry không?**  
Không, vì có thể thực hiện side effect nhiều lần khi CAS thất bại.

**11. Lock có tự rollback khi exception xảy ra không?**  
Không.

**12. entrySet iterator có cho transactional snapshot không?**  
Không, nó weakly consistent khi có concurrent modification.

**13. Có phải mutable value trở nên thread-safe chỉ vì nằm trong ConcurrentHashMap?**  
Không.

**14. Khi nào nên dùng database transaction?**  
Khi invariant và commit cần bao trùm nhiều bản ghi, bền vững qua crash hoặc nhiều instance, theo yêu cầu của datastore.

**15. Cách kiểm một ứng dụng có đúng không chỉ bằng stress test?**  
Ngoài stress, tạo interleaving có kiểm soát, assert invariant, test lỗi/rollback, concurrent readers và tính nhất quán giữa các process khi cần.

**16. Tại sao phải xác định phạm vi của “atomic”?**  
Vì atomic một mapping, atomic một immutable aggregate và transaction trên nhiều bản ghi là các bảo đảm khác nhau.

## Tài liệu Java SE 8 chính thức

- [ConcurrentHashMap](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentHashMap.html): thread-safety, per-key atomic operations, compute/merge, weakly consistent iterators, bulk operations.
- [ConcurrentMap](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentMap.html): các phương thức cập nhật có điều kiện theo key.
- [Map](https://docs.oracle.com/javase/8/docs/api/java/util/Map.html): hợp đồng Map và khác biệt đối với concurrent implementations.
- [AtomicReference](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/AtomicReference.html): get, set, compareAndSet và cơ chế CAS.
- [ReentrantLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/ReentrantLock.html): explicit lock, try/finally unlock, phối hợp nhiều lock.
- [Lock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/Lock.html): nguyên tắc dùng lock và memory synchronization.
- [CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html): dựng interleaving xác định cho test concurrency.
- [LongAdder](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/LongAdder.html): counter có contention, lưu ý sum khi cập nhật đồng thời.
- [Math](https://docs.oracle.com/javase/8/docs/api/java/lang/Math.html): kiểm tra tràn với addExact khi dùng số nguyên.
- [Thread](https://docs.oracle.com/javase/8/docs/api/java/lang/Thread.html): chạy và chờ kết thúc luồng trong các demo.

**Ghi nhớ:** `ConcurrentHashMap` cho các phép đọc/ghi và cập nhật có điều kiện an toàn theo **phạm vi từng thao tác**, nhưng **không có multi-key transaction**. Một phép chuyển tiền gồm hai `compute` vẫn có khoảng giữa hai cập nhật, có thể lộ trạng thái không nhất quán. Nếu invariant sống trên nhiều key, cần lock chung/ordered locks với reader cùng tuân protocol, hoặc đổi mô hình sang **immutable aggregate trong một key** hay **AtomicReference<State> + CAS** khi chỉ trong một JVM. Khi cần atomic commit nhiều bản ghi, rollback, durability hoặc nhiều service, hãy chọn **transactional datastore/kiến trúc phân tán phù hợp**, không kỳ vọng collection thread-safe tự làm thay.