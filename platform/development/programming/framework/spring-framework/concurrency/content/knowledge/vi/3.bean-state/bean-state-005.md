# Phép kiểm tra rồi cập nhật và thao tác nhiều bước cần bảo vệ

## 1. Vấn đề: một quyết định nghiệp vụ thường gồm nhiều bước

Trong ứng dụng Spring, một bean `@Service` thường có scope `singleton`: nhiều request HTTP, callback, tác vụ `@Async` hoặc job có thể sử dụng **cùng một đối tượng**. Nếu bean giữ trạng thái có thể thay đổi, các luồng có thể cùng đọc và ghi trạng thái đó.

Ví dụ, nghiệp vụ chỉ còn một suất đăng ký:

```java
// SAI khi nhiều thread cùng gọi và cùng dùng biến available
if (available > 0) {
    available--;
    return true;
}
return false;
```

Đoạn này gồm ít nhất hai hành động: **kiểm tra** điều kiện rồi **cập nhật** dữ liệu. Chúng không trở thành một thao tác nguyên tử chỉ vì nằm liền nhau trong mã nguồn. Hai luồng cùng thấy `available == 1`, đều kết luận “còn suất” rồi đều cấp thành công: hệ thống bán hai suất dù chỉ có một suất.

Đây là lỗi **check-then-act** (kiểm tra rồi hành động), một dạng **TOCTOU** (*time of check to time of use*). Vấn đề cốt lõi không phải thread nào nhanh hơn; đó là dữ liệu có thể thay đổi **giữa thời điểm kiểm tra và thời điểm hành động**.

Các biến thể trong thực tế:

- **Check-then-act:** “Nếu còn hàng thì giảm tồn kho”; “Nếu chưa có bản ghi thì tạo”; “Nếu chưa xử lý request này thì xử lý”.
- **Read-modify-write:** `counter++`, `balance = balance - amount`, `visits.put(key, visits.get(key) + 1)`.
- **Compound action (thao tác nhiều bước):** chuyển tiền phải giảm một tài khoản và tăng tài khoản khác; đặt vé phải giảm `available`, tăng `reserved` rồi tạo phiếu; cập nhật cấu hình phải đổi nhiều trường trong một trạng thái hợp lệ.
- **Check-then-use tài nguyên bên ngoài:** kiểm tra file tồn tại rồi mở file, kiểm tra quyền rồi thực hiện thao tác, kiểm tra DB chưa có bản ghi rồi chèn. Các bước ở những hệ thống khác nhau thường không thể bảo vệ chỉ bằng một lock Java.

**Mục tiêu học tập:** nhận diện ranh giới nguyên tử của quy tắc nghiệp vụ, chọn một cơ chế bảo vệ nhất quán, hiểu phạm vi bảo vệ của từng cơ chế, và kiểm chứng tính đúng đắn khi có nhiều request đồng thời.

## 2. Nhìn thấy race condition bằng lịch xen kẽ

Ban đầu `available = 1`. Hai request A và B chạy trên hai luồng:

| Thời điểm | Thread A | Thread B | Kết quả |
| --- | --- | --- | --- |
| T1 | Đọc `available == 1` | | A thấy còn suất |
| T2 | | Đọc `available == 1` | B cũng thấy còn suất |
| T3 | Cập nhật, trả thành công | | A được cấp |
| T4 | | Cập nhật, trả thành công | B cũng được cấp |

Ngay cả khi hai lệnh giảm dùng thao tác atomic riêng lẻ, **phần kiểm tra và phần giảm vẫn có thể bị xen vào giữa**. Với `AtomicInteger`, mẫu sau **vẫn sai**:

```java
private final AtomicInteger available = new AtomicInteger(1);

public boolean reserveWrong() {
    if (available.get() <= 0) {
        return false;
    }
    available.getAndDecrement(); // Bản thân phép giảm atomic, cả quy trình thì không.
    return true;
}
```

Khi A và B đều vượt qua `get()` trước khi một bên giảm, cả hai có thể gọi `getAndDecrement()`. Kết quả có thể là `available == -1` và cả hai request đều được xác nhận thành công.

Cần phân biệt ba thuộc tính:

1. **Atomicity (tính nguyên tử):** các bước liên quan đến một quy tắc nghiệp vụ được nhìn nhận như một quyết định không bị chen ngang bởi thao tác cạnh tranh.
2. **Visibility (tính nhìn thấy):** một thread có nhìn thấy cập nhật của thread khác theo quy tắc Java Memory Model hay không.
3. **Consistency/invariant (bất biến nghiệp vụ):** những điều luôn phải đúng, chẳng hạn `available >= 0` và `available + reserved == capacity`.

`volatile` hỗ trợ visibility và quy tắc thứ tự nhất định, nhưng **không làm nguyên tử** chuỗi “đọc → kiểm tra → ghi”, cũng không khiến `counter++` trở thành atomic. `AtomicInteger` bảo vệ thao tác riêng lẻ và cung cấp CAS; cần **CAS loop** hoặc một lock bao trọn cả quyết định để giải quyết check-then-act.

## 3. Xác định ranh giới cần bảo vệ

Một giải pháp đúng bắt đầu từ **bất biến**, không bắt đầu từ tên annotation.

Giả sử tổng số suất ban đầu là 5; bean lưu hai trường `available` và `reserved`. Bất biến cần giữ là:

```text
available >= 0
reserved >= 0
available + reserved == 5
```

Một lượt đặt chỗ phải làm **trọn** các bước “kiểm tra còn suất → giảm available → tăng reserved” trong cùng một vùng bảo vệ. Nếu chỉ đồng bộ lệnh giảm, lệnh kiểm tra vẫn có race. Nếu đồng bộ cập nhật nhưng cho phép thread khác đọc hai trường rời rạc, người đọc có thể quan sát snapshot thiếu nhất quán.

Cần xác định:

- **Trạng thái nào được chia sẻ?** Field của bean singleton, cache, static field, map, database row, hay tài nguyên hệ thống khác?
- **Ai có thể truy cập?** Request threads, executor workers, scheduled tasks, listener, các bean khác, hoặc nhiều instance ứng dụng?
- **Bất biến nào phải giữ?** Không âm, không cấp trùng, tổng phải bảo toàn, không thể chuyển từ trạng thái cuối trở lại trạng thái đầu, v.v.
- **Đơn vị nguyên tử là gì?** Một biến, một khóa trong map, nhiều trường của một object, nhiều DB rows, hay nhiều hệ thống bên ngoài?
- **Phạm vi bảo vệ ở đâu?** Trong một object/JVM, một transaction DB, hoặc một hệ phân tán?

Một phần mã được gọi là “thread-safe” chưa đủ để suy ra **cả workflow** thread-safe. Ví dụ, `ConcurrentHashMap` an toàn cho từng thao tác được bảo đảm, nhưng đoạn `containsKey(key)` rồi `put(key, value)` là hai thao tác riêng và vẫn có cửa sổ race.

## 4. Ví dụ Java 17 chạy độc lập: tái hiện lỗi và sửa

Ví dụ sau **cố ý** sử dụng `CountDownLatch` để hai worker cùng đi qua bước kiểm tra trước khi thực hiện bước giảm. Nhờ thế kết quả lỗi có thể tái hiện xác định, không dựa vào may rủi của scheduler. Sau đó so sánh hai cách sửa: CAS cho một biến và lock cho bất biến nhiều trường.

Tạo tệp **`CheckThenActDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class CheckThenActDemo {
    private static final class BrokenInventory {
        private final AtomicInteger remaining = new AtomicInteger(1);

        boolean reserve(CountDownLatch bothChecked, CountDownLatch proceed)
                throws InterruptedException {
            if (remaining.get() <= 0) {
                return false;
            }

            // Demo: buộc cả hai luồng vượt qua check trước khi ai được giảm.
            bothChecked.countDown();
            proceed.await();

            remaining.getAndDecrement();
            return true;
        }

        int remaining() {
            return remaining.get();
        }
    }

    private static final class CasInventory {
        private final AtomicInteger remaining = new AtomicInteger(1);

        boolean reserve() {
            while (true) {
                int observed = remaining.get();
                if (observed <= 0) {
                    return false;
                }
                if (remaining.compareAndSet(observed, observed - 1)) {
                    return true;
                }
                // Có thread khác thay đổi giá trị: đọc lại và thử tiếp.
            }
        }

        int remaining() {
            return remaining.get();
        }
    }

    private static final class ProtectedLedger {
        private final Object lock = new Object();
        private int available = 1;
        private int reserved = 0;

        boolean reserve() {
            synchronized (lock) {
                if (available <= 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(available, reserved);
            }
        }
    }

    private record Snapshot(int available, int reserved) {}

    private static int accepted(Future<Boolean> first, Future<Boolean> second)
            throws Exception {
        return (first.get() ? 1 : 0) + (second.get() ? 1 : 0);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            BrokenInventory broken = new BrokenInventory();
            CountDownLatch checked = new CountDownLatch(2);
            CountDownLatch proceed = new CountDownLatch(1);

            Future<Boolean> b1 = pool.submit(() -> broken.reserve(checked, proceed));
            Future<Boolean> b2 = pool.submit(() -> broken.reserve(checked, proceed));
            checked.await();
            proceed.countDown();

            int brokenAccepted = accepted(b1, b2);
            System.out.println("Broken accepted: " + brokenAccepted);
            System.out.println("Broken remaining: " + broken.remaining());

            CasInventory cas = new CasInventory();
            int casAccepted = accepted(pool.submit(cas::reserve),
                                       pool.submit(cas::reserve));
            System.out.println("CAS accepted: " + casAccepted);
            System.out.println("CAS remaining: " + cas.remaining());

            ProtectedLedger ledger = new ProtectedLedger();
            int lockAccepted = accepted(pool.submit(ledger::reserve),
                                        pool.submit(ledger::reserve));
            Snapshot current = ledger.snapshot();
            System.out.println("Lock accepted: " + lockAccepted);
            System.out.println("Lock available: " + current.available());
            System.out.println("Lock reserved: " + current.reserved());
        } finally {
            pool.shutdown();
        }
    }
}
```

Trong thư mục chứa tệp, dùng **JDK 17+**:

```bash
javac CheckThenActDemo.java
java CheckThenActDemo
```

Kết quả stdout:

```text
Broken accepted: 2
Broken remaining: -1
CAS accepted: 1
CAS remaining: 0
Lock accepted: 1
Lock available: 0
Lock reserved: 1
```

**Giải thích kết quả:**

- **Broken:** cả hai luồng đã kiểm tra giá trị dương trước khi `proceed` mở. Hai phép `getAndDecrement()` đều nguyên tử, nhưng quyết định cấp suất không nguyên tử, nên hai request được chấp nhận và tồn kho thành -1.
- **CAS:** khi còn 1 suất, chỉ một thread có thể đổi thành 0 bằng `compareAndSet(1, 0)`. Thread khác thử CAS sẽ thất bại, đọc lại 0 và trả `false`. Không có overselling.
- **Lock:** cả kiểm tra và hai cập nhật `available--`, `reserved++` nằm trong cùng monitor. `snapshot()` cũng lấy monitor đó nên không nhìn thấy nửa chừng một lần cập nhật. Tổng `available + reserved` luôn là 1 tại các điểm quan sát được bảo vệ.

Lưu ý: `CountDownLatch` trong nhánh Broken chỉ phục vụ tái hiện race có chủ đích; đó **không phải** cơ chế bảo vệ nghiệp vụ. Ví dụ không nói rằng một lịch thực thi luôn gây lỗi trong chương trình không dùng latch. Khi đánh giá một hệ thống thật, cần chứng minh bất biến đúng với mọi lịch xen kẽ có thể xảy ra.

## 5. Chọn đúng công cụ cho ranh giới nguyên tử

### 5.1. `synchronized` hoặc `ReentrantLock` khi bảo vệ một nhóm trạng thái

Cách trực quan cho invariant nhiều trường trong một JVM là cùng dùng một lock:

```java
private final Object stateLock = new Object();
private int available = 5;
private int reserved = 0;

public boolean tryReserve() {
    synchronized (stateLock) {
        if (available <= 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}
```

Đây là snippet nằm trong một class có các field như khai báo, không phải chương trình standalone. Mọi phương thức đọc/sửa **các trường cùng bất biến** phải tuân thủ cùng một khóa. Lock chỉ có hiệu lực giữa những thread cùng truy cập **đúng đối tượng lock**. Tránh dùng string intern, class object hoặc đối tượng công khai làm monitor nếu code khác có thể khóa ngoài ý muốn. Dùng `private final Object` thể hiện quyền sở hữu rõ ràng.

`synchronized` vừa cung cấp mutual exclusion, vừa thiết lập quan hệ happens-before khi một thread mở monitor và thread khác sau đó lấy cùng monitor. Một snapshot nhất quán cần đọc tất cả trường liên quan khi đang giữ cùng lock.

`ReentrantLock` hữu ích khi cần `tryLock()`, timeout, khả năng interrupt trong lúc đợi lock hoặc các condition riêng. Phải mở khóa trong `finally`:

```java
lock.lock();
try {
    // Kiểm tra và cập nhật các trường cùng invariant.
} finally {
    lock.unlock();
}
```

Đây là snippet minh họa với biến `lock` là `ReentrantLock` được khởi tạo ở lớp. Không nên mở nhiều lock theo thứ tự tùy ý. Ví dụ chuyển tiền A→B khóa A rồi B, còn B→A khóa B rồi A có thể gây **deadlock**. Cần một thứ tự khóa nhất quán theo ID hoặc cơ chế dữ liệu phù hợp khác.

Không giữ lock qua lời gọi HTTP, truy cập mạng, `Thread.sleep`, callback không kiểm soát, hay xử lý dài nếu có thể tránh. Những công việc ấy giữ các request khác chờ và có thể gây deadlock. Nhưng cũng không được thả lock giữa “check” và “update” nếu invariant phụ thuộc cả hai bước: hãy thiết kế dữ liệu và ranh giới transaction để thu hẹp critical section **mà vẫn nguyên tử**.

### 5.2. `AtomicInteger` và CAS loop khi chỉ cần cập nhật một giá trị

Với counter hoặc quota lưu trong **một biến**, mẫu CAS trong ví dụ Java độc lập phù hợp:

```java
public boolean reserveOne(AtomicInteger remaining) {
    while (true) {
        int current = remaining.get();
        if (current <= 0) {
            return false;
        }
        if (remaining.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
```

Đây là snippet nhận một `AtomicInteger` chia sẻ giữa các thread. CAS làm thao tác “chỉ đổi nếu giá trị vẫn như vừa đọc” trở thành một quyết định nguyên tử trên **biến đó**. Nếu thất bại vì có cạnh tranh, vòng lặp phải **đọc lại** thay vì cố ghi theo giá trị cũ. Trong tải cạnh tranh, có thể phải thử nhiều lần; tránh đặt I/O hay side effect trong vòng retry.

Không dùng hai `AtomicInteger` riêng và mặc định chúng tạo ra transaction trên hai trường. Nếu invariant liên quan cả `available` và `reserved`, một thread khác vẫn có thể đọc trạng thái ở giữa hai phép cập nhật. Có thể gói các trường vào **một state immutable** rồi CAS cả reference, hoặc dùng lock để giải thích và duy trì tính đúng đắn đơn giản hơn.

### 5.3. Concurrent collections: atomic operation khác với chuỗi nhiều thao tác

Chẳng hạn, đánh dấu một khóa “đã xử lý” trong memory:

```java
private final java.util.Set<String> processed =
        java.util.concurrent.ConcurrentHashMap.newKeySet();

public boolean markOnce(String requestId) {
    return processed.add(requestId); // true chỉ cho lần thêm thành công.
}
```

Đây là snippet trong class được chia sẻ. `add` trên concurrent key set hỗ trợ đánh dấu nguyên tử cho **một khóa**. Trái lại, `if (!processed.contains(id)) processed.add(id)` tách check và act, nên không thể dựa vào `contains` để kết luận ai có quyền xử lý.

`ConcurrentHashMap.putIfAbsent`, `compute` và `computeIfAbsent` cũng có thao tác atomic **theo key** theo hợp đồng API. Callback của `compute` cần ngắn, đơn giản, không sửa đệ quy cùng map và không gửi email/trừ tiền/gọi mạng bên trong: callback map không tạo transaction với hệ ngoài. Đối với điều kiện trải qua nhiều key, cần cơ chế phối hợp cao hơn.

`LongAdder` có thể tối ưu thống kê đếm có cạnh tranh cao, nhưng kết quả `sum()` khi đang cập nhật không phải snapshot nguyên tử của cả hệ thống. Đừng dùng `sum() >= limit` rồi `increment()` như cách giữ quota tuyệt đối.

## 6. Đặt cơ chế bảo vệ vào Spring bean đúng cách

Ví dụ sau là một **Spring-managed service** trong dự án Spring Boot/Spring Framework đã có dependencies tương ứng. Đây là class hoàn chỉnh để đưa vào mã nguồn dự án ở package phù hợp; không phải chương trình `javac` độc lập vì dùng annotation Spring.

**`LocalSeatService.java`:**

```java
import org.springframework.stereotype.Service;

@Service
public class LocalSeatService {
    private final Object stateLock = new Object();
    private int remaining = 3;
    private int booked = 0;

    public boolean bookOne() {
        synchronized (stateLock) {
            if (remaining <= 0) {
                return false;
            }
            remaining--;
            booked++;
            return true;
        }
    }

    public State state() {
        synchronized (stateLock) {
            return new State(remaining, booked);
        }
    }

    public record State(int remaining, int booked) {}
}
```

Một controller có thể gọi `bookOne()`; khi ba request cùng đến, tối đa ba lượt sẽ thành công **trong một instance bean**. Phương thức `state()` trả record immutable chứa hai giá trị được đọc đồng thời dưới cùng lock.

Các giả định phải được ghi rõ khi dùng cách này:

- **Mặc định `@Service` singleton trong một `ApplicationContext`.** Đây không có nghĩa là singleton cho toàn bộ cluster. Hai JVM/pod có hai `LocalSeatService` và hai lock riêng.
- **State đang ở RAM:** khởi động lại làm mất số đếm. Nếu nghiệp vụ là giữ chỗ thật, dữ liệu cần sống trong database; bean RAM không phải source of truth phù hợp.
- **Request scope hoặc prototype không phải thuốc chữa race:** object khác nhau có thể vẫn trỏ tới tài nguyên chung, hoặc một object vẫn bị dùng từ nhiều thread. Phân tích ownership thực tế quan trọng hơn đổi scope.
- **`@Async` không tự đảm bảo thread safety:** nó chuyển công việc qua executor và còn khiến việc truy cập đồng thời dễ xảy ra hơn nếu state dùng chung.
- **Bất biến phải được bảo vệ từ mọi đường vào:** HTTP endpoint, scheduled task, listener và các service khác không được cập nhật `remaining`/`booked` qua lối tắt.

Khi logic nghiệp vụ có cả thao tác DB, không nên giữ lock Java và gọi DB trong đó như một cách mặc định. Lock này chỉ bao phủ các thread trong một JVM và có thể giữ lâu do I/O; dùng cơ chế transaction/constraint/atomic update ở database cho state bền vững.

## 7. Multi-step trong database: `@Transactional` cần đi cùng cơ chế chống race

Một ví dụ sai thường gặp:

```java
@Transactional
public boolean reserveWrong(long eventId) {
    int available = jdbc.queryForObject(
            "SELECT available FROM event_capacity WHERE event_id = ?",
            Integer.class, eventId);

    if (available <= 0) {
        return false;
    }

    jdbc.update(
            "UPDATE event_capacity SET available = available - 1 WHERE event_id = ?",
            eventId);
    return true;
}
```

Đây là snippet minh họa với một `JdbcTemplate jdbc` đã được inject, không phải class standalone. **Chỉ thêm `@Transactional` không đủ để loại race** giữa hai transaction đồng thời trong cấu hình isolation thông dụng như READ COMMITTED: cả hai có thể đọc giá trị cũ trước khi update. Còn hành vi cụ thể khi lock/isolation xung đột tùy database. Không suy luận “transaction = tự động tuần tự hóa tất cả request”.

Khi quy tắc chỉ là “giảm 1 nếu còn suất”, có thể chuyển cả check và decrement thành **một câu UPDATE có điều kiện**:

```sql
UPDATE event_capacity
SET available = available - 1
WHERE event_id = :event_id
  AND available > 0;
```

Trong một RDBMS hỗ trợ transaction và row locking đúng chuẩn, câu lệnh này xét điều kiện và cập nhật nhất quán với các cập nhật cạnh tranh của hàng liên quan. **Số hàng bị ảnh hưởng** là căn cứ xác định thành công: `1` là giữ được suất; `0` là không còn suất hoặc ID không tồn tại. Phải xác minh hành vi với database/driver đang dùng.

Nếu sau đó còn tạo bản ghi đăng ký, hai thao tác DB cần thuộc cùng **một transaction**. Ví dụ Spring JDBC dưới đây có thể dùng trong ứng dụng đã cấu hình `JdbcTemplate`, datasource và transaction manager:

**`DatabaseReservationService.java` (snippet tích hợp Spring):**

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseReservationService {
    private final JdbcTemplate jdbc;

    public DatabaseReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(long eventId, String requestId) {
        int updated = jdbc.update(
                "UPDATE event_capacity " +
                "SET available = available - 1 " +
                "WHERE event_id = ? AND available > 0",
                eventId);

        if (updated != 1) {
            return false;
        }

        jdbc.update(
                "INSERT INTO event_registration (request_id, event_id) VALUES (?, ?)",
                requestId, eventId);

        return true;
    }
}
```

Ví dụ giả định schema tối thiểu có `event_capacity(event_id PRIMARY KEY, available)`, `event_registration(request_id UNIQUE, event_id)`, ràng buộc `CHECK (available >= 0)` nếu database hỗ trợ, và dùng database transaction thực sự. `request_id` duy nhất ngăn tạo hai đăng ký có cùng định danh. Nếu INSERT vi phạm unique constraint và ném exception runtime từ Spring JDBC, transaction mặc định rollback cả phần giảm suất. Cần xử lý lỗi trùng `requestId` ở **biên gọi ngoài transaction** và tra lại kết quả cũ nếu nghiệp vụ yêu cầu retry idempotent; class minh họa trên chưa tự triển khai toàn bộ quy trình idempotency.

**Phân biệt rõ các cơ chế khác trong DB:**

| Cơ chế | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `UPDATE ... WHERE condition` + kiểm tra số hàng | Quy tắc có thể biểu diễn thành một cập nhật điều kiện | Thường đơn giản cho stock/quota; kiểm tra hàng bị ảnh hưởng và lỗi |
| Unique constraint | Không cho hai bản ghi có cùng khóa nghiệp vụ | `SELECT` trước khi `INSERT` không thay thế unique constraint |
| Optimistic locking với `@Version` | Nhiều request sửa cùng entity, xung đột tương đối hiếm | Transaction thất bại do version cũ cần chiến lược retry hoặc báo conflict |
| Pessimistic row lock, ví dụ `SELECT ... FOR UPDATE` hoặc JPA `PESSIMISTIC_WRITE` | Cần đọc và cập nhật nhiều bước trên các hàng có liên quan | Lock có thể chặn, deadlock, timeout; thứ tự khóa cần nhất quán |
| Isolation mạnh hơn, như SERIALIZABLE | Quy tắc phức tạp cần bảo đảm nhất quán theo transaction | Chi phí cạnh tranh và khả năng transaction bị abort/retry; tùy RDBMS |
| Queue/outbox hoặc workflow coordinator | Một nghiệp vụ liên quan DB cùng dịch vụ ngoài, phải chịu restart/retry | Không thể có atomicity cross-system chỉ bằng `synchronized` hay transaction DB thông thường |

Không gói gửi email hoặc gọi REST từ dịch vụ ngoài vào giữa lock/transaction DB và giả định chúng sẽ rollback cùng database. Nếu phải phát sự kiện sau khi ghi DB với bảo đảm không mất, cân nhắc transactional outbox và xử lý downstream có idempotency.

## 8. Những vấn đề thường làm lời giải “đã có lock” vẫn sai

### Lock sai phạm vi

`synchronized` trên một instance chỉ bảo vệ **instance ấy**. Nhiều instance ứng dụng dùng chung DB không chia sẻ monitor. Với dữ liệu bền vững, dùng DB atomic constraint/transaction hoặc cơ chế điều phối phân tán được thiết kế phù hợp. Distributed lock cần tính đến lease hết hạn, fencing token và failure; không nên dùng chỉ để thay cho một câu SQL có điều kiện.

### Đọc không cùng cơ chế bảo vệ

Nếu writer cập nhật `available` và `reserved` trong lock nhưng reader đọc chúng độc lập ngoài lock, reader có thể thấy snapshot “nửa cũ nửa mới”. Đọc nhiều trường liên quan cần cùng monitor, immutable snapshot được công bố đúng cách, hoặc transaction/snapshot đúng mức ở DB.

### “Mỗi lệnh đều thread-safe” nhưng workflow không thread-safe

`AtomicInteger.get()` và `getAndDecrement()` đều có tính atomic riêng nhưng ghép lại không bảo vệ điều kiện. Tương tự `ConcurrentHashMap.containsKey()` + `put()`, hoặc DB `SELECT` + `UPDATE` khi không có guard/lock phù hợp. Phải kiểm tra **toàn bộ quyết định**.

### Nhầm ranh giới của Spring proxy và transaction

Spring mặc định xử lý `@Transactional` bằng AOP proxy; lời gọi `this.methodAnnotated()` bên trong cùng bean thường không đi qua proxy, nên không tự mở transaction như mong đợi. Các transaction imperative gắn với thread; công việc được chuyển sang thread khác bằng `@Async` không tự động kế thừa transaction của thread gọi. Khi cần transaction trong task async, đặt ranh giới transaction tại chính service/method xử lý ở thread đó, thông qua cách gọi Spring quản lý phù hợp.

### Khóa quá rộng hoặc lồng khóa không nhất quán

Một lock toàn cục có thể giảm throughput mạnh, nhất là khi chứa I/O. Nhiều lock lấy theo thứ tự khác nhau có thể deadlock. Cần chọn đúng hạt khóa (per-key/per-account nếu phù hợp), thứ tự khóa cố định, timeout và metric về thời gian chờ. Tối ưu lock chỉ sau khi đã giữ được invariant.

### Lỗi, retry và tác vụ không lặp an toàn

Nếu cập nhật state rồi exception xảy ra trước khi ghi nhận kết quả, caller có thể retry và thực hiện lần hai. In-memory lock không giải quyết được crash/retry qua JVM. Cần request ID/idempotency key, unique constraint, transaction rollback, outbox hoặc các kỹ thuật nghiệp vụ tương ứng. Tính đúng đắn bao gồm cả **điều xảy ra khi lỗi**, không chỉ lúc hai luồng chạy bình thường.

## 9. Cách kiểm thử và đánh giá giải pháp

Bài toán concurrency không thể chứng minh bằng một lần chạy “thấy đúng”. Hãy kiểm tra bất biến sau nhiều lịch xen kẽ và thiết kế test có điểm đồng bộ chủ động:

1. **Xác định invariant:** số lượt cấp thành công không vượt quota; `remaining >= 0`; tổng các thành phần không đổi; một request ID chỉ được chấp nhận một lần.
2. **Tạo đối thủ đồng thời có kiểm soát:** dùng `CountDownLatch` hoặc `CyclicBarrier` để nhiều worker tiến gần điểm kiểm tra cùng lúc; test không nên dựa duy nhất vào `Thread.sleep`.
3. **Thu kết quả từng task:** đợi `Future.get()`/`join()` để không kiểm tra khi task chưa hoàn thành; xử lý exception; không giả định thứ tự thread hoàn thành.
4. **Đo invariant, không đo thứ tự log:** ví dụ với 1 suất và 2 đối thủ, phải có đúng một thành công, tồn kho 0; không quan trọng request A hay B thắng.
5. **Chạy cả điều kiện lỗi:** timeout, exception trong bước hai, retry cùng request ID, transaction rollback, restart và nhiều JVM nếu nghiệp vụ có.
6. **Quan sát giới hạn tài nguyên:** số request tranh lock, thời gian chờ, deadlock/timeout, throughput, lỗi DB và số lần optimistic-lock retry.

Test Java ở mục 4 chứng minh một lịch lỗi cụ thể của cách sai và kết quả đúng của hai cách sửa cho tình huống nhỏ. Nó **không phải chứng minh hình thức** rằng mọi triển khai ứng dụng đều đúng. Với state trong DB hoặc nhiều instance, test tích hợp thật phải dùng đúng database, mức isolation, cấu hình pool và topology triển khai mục tiêu.

## 10. Chọn hướng giải quyết cho từng tình huống

| Bài toán | Ranh giới nguyên tử cần thiết | Hướng ưu tiên |
| --- | --- | --- |
| Quota tạm trong RAM của một singleton bean trên một JVM | Một số nguyên | `AtomicInteger` + CAS loop hoặc synchronized |
| Hai hay nhiều field của cùng bean phải thỏa invariant | Toàn bộ nhóm trường | Một lock nhất quán / immutable state CAS; snapshot dưới cùng cơ chế |
| Dedupe một key trong concurrent cache | Một key | `putIfAbsent`/`newKeySet().add()`/`compute` thích hợp |
| Trừ tồn kho bền vững, nhiều pod cùng truy cập | Một hàng/điều kiện trong database | Conditional UPDATE + affected row + DB constraint |
| Chuyển số dư giữa hai tài khoản | Nhiều hàng và một transaction | Database transaction, locking/isolation, thứ tự cập nhật và retry |
| Nhận request lặp do mạng/queue | Request ID và kết quả lâu dài | Idempotency key, unique constraint, record trạng thái |
| Ghi DB rồi phát event đáng tin cậy | DB commit + giao event cuối cùng | Outbox/queue và consumer idempotent |

Có thể tự rà soát một phương thức bằng năm câu hỏi: **(1)** Quy tắc “chỉ khi...” đang kiểm tra điều gì? **(2)** Dữ liệu nào có thể đổi ngay sau khi kiểm tra? **(3)** Cơ chế nào làm toàn bộ quyết định nguyên tử? **(4)** Cơ chế đó bao phủ một object, một JVM, một database hay cả cụm? **(5)** Nếu crash hoặc retry ở giữa các bước thì bất biến và kết quả nghiệp vụ còn đúng không?

## 11. Tài liệu đối chiếu

- [Java SE 17 – AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `get()`, `compareAndSet()`, `getAndDecrement()`.
- [Java SE 17 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `putIfAbsent`, `compute` và bảo đảm atomic theo key.
- [Java SE 17 – Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): acquire/release, interruptibility và `tryLock`.
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction proxy, thread-bound transaction và khác biệt với reactive.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): quy tắc gọi qua proxy và self-invocation.

**Ghi nhớ:** Thread-safe của một field, collection hay statement không tự đảm bảo một **quy trình kiểm tra rồi cập nhật** là đúng. Bắt đầu bằng invariant, bao trọn điểm ra quyết định trong một cơ chế nguyên tử có phạm vi đủ rộng, rồi kiểm tra cả chạy đồng thời, lỗi, retry và nhiều instance.
