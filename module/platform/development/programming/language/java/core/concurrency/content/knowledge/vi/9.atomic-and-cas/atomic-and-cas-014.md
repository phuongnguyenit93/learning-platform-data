# updateAndGet, accumulateAndGet và nguy cơ tác dụng phụ khi CAS phải thử lại

## 1. Vấn đề: một lời gọi cập nhật không có nghĩa lambda chỉ chạy một lần

Trong Java concurrency, `AtomicInteger`, `AtomicLong` và `AtomicReference<V>` cung cấp các phương thức cập nhật dựa trên **giá trị hiện tại** mà không cần tự viết vòng `compareAndSet` (CAS) cho mỗi trường hợp. Hai phương thức trọng tâm:

~~~java
int updated = counter.updateAndGet(old -> old + 1);

int total = counter.accumulateAndGet(
        5, (current, delta) -> current + delta);
~~~

Cả hai thao tác cập nhật **giá trị atomic**. Tuy nhiên, việc cập nhật nguyên tử **không đồng nghĩa** hàm lambda được gọi đúng một lần. Khi có thread khác cập nhật cạnh tranh, một lần tính toán có thể dựa trên giá trị cũ và thất bại khi commit bằng CAS; JDK có thể **gọi lại hàm** với giá trị mới rồi thử lại.

Vì thế tài liệu JDK yêu cầu hàm `updateFunction` và `accumulatorFunction` là **side-effect-free** (không có tác dụng phụ). Nếu lambda gửi email, ghi log nghiệp vụ, ghi cơ sở dữ liệu, cộng một metric riêng hoặc sửa mutable object, những hành động đó có thể xảy ra **nhiều lần cho một lần cập nhật thành công**.

Bài học này giúp bạn:

- Hiểu chữ ký và kết quả trả về của `updateAndGet`, `getAndUpdate`, `accumulateAndGet` và `getAndAccumulate` trên số nguyên và object reference.
- Giải thích vì sao CAS thất bại dẫn đến retry, và tại sao việc **hàm được đánh giá** khác với việc **candidate đã được commit**.
- Biết quy tắc áp dụng `UnaryOperator` và `BinaryOperator`, thứ tự đối số (`current` trước, `x` sau), điều kiện để phép biến đổi thread-safe.
- Dùng immutable state và immutable input để thiết kế hàm cập nhật thuần, bảo vệ invariant khi nhiều writer tranh chấp.
- Tái hiện một lần cập nhật thực tế nhưng lambda được chạy **hai lần** bằng ví dụ Java 17+ có lịch chạy điều khiển.
- Chọn nơi phù hợp để ghi log, gửi sự kiện hoặc thực hiện I/O; hiểu giới hạn “thực hiện side effect sau CAS thành công”.
- Phân biệt `updateAndGet` với `set`, `getAndSet`, `getAndIncrement`, `LongAdder`, `synchronized` và các phương án đồng bộ khác.

**Phạm vi:** Java SE/JVM concurrency, Java Memory Model (JMM), Atomic & CAS. Các ví dụ chạy độc lập với **JDK 17 trở lên**.

## 2. Bộ API cơ bản và ý nghĩa giá trị trả về

### 2.1. AtomicInteger và AtomicLong

Với `AtomicInteger`:

~~~java
int newValue = atomic.updateAndGet(old -> old + 1);

int oldValue = atomic.getAndUpdate(old -> old + 1);

int newTotal = atomic.accumulateAndGet(
        delta, (current, amount) -> current + amount);

int previous = atomic.getAndAccumulate(
        delta, (current, amount) -> current + amount);
~~~

`AtomicLong` tương tự nhưng dùng kiểu `long`. Hàm một đối số cho `AtomicInteger` là `IntUnaryOperator`, hai đối số là `IntBinaryOperator`; `AtomicLong` dùng `LongUnaryOperator` và `LongBinaryOperator`. Tất cả đều thuộc Java standard library, không cần thêm thư viện.

| API | Đối số của hàm biến đổi | Giá trị trả về | Ghi nhớ |
|---|---|---|---|
| `updateAndGet(fn)` | Giá trị hiện tại `old` | **Giá trị mới** sau lần cập nhật thành công | Update → return new |
| `getAndUpdate(fn)` | Giá trị hiện tại `old` | **Giá trị cũ** trước lần cập nhật thành công | Return old → update |
| `accumulateAndGet(x, fn)` | `fn(current, x)` | **Giá trị mới** | Hợp nhất current với x |
| `getAndAccumulate(x, fn)` | `fn(current, x)` | **Giá trị cũ** | Hợp nhất, nhưng trả old |
| `getAndIncrement()` | Không truyền hàm | Giá trị cũ, rồi tăng 1 nguyên tử | Chuyên biệt cho counter |
| `incrementAndGet()` | Không truyền hàm | Giá trị mới sau tăng 1 nguyên tử | Chuyên biệt cho counter |
| `compareAndSet(expect, next)` | Hai giá trị ứng viên | `true`/`false` | Tự kiểm soát CAS/retry |
| `getAndSet(next)` | Giá trị thay thế | Giá trị cũ | Thay **vô điều kiện**, không tính từ old |

Ở nhóm update functions, giá trị trả về là **giá trị thuộc lần cập nhật đã commit**, không phải giá trị của một lần đánh giá lambda thất bại. Trong thời điểm nhiều thread cập nhật, một lần `get()` khác diễn ra sau đó vẫn có thể quan sát giá trị mới hơn; kết quả trả về không khóa giá trị ở trạng thái mãi mãi.

### 2.2. AtomicReference<V>

Khi giá trị được bảo vệ là **một object reference**, dùng:

~~~java
AtomicReference<State> current = new AtomicReference<>(initial);

State newState = current.updateAndGet(
        old -> new State(old.count() + 1, old.version() + 1));

State oldState = current.getAndUpdate(
        old -> new State(old.count() + 1, old.version() + 1));

State afterMerge = current.accumulateAndGet(
        delta, (old, increment) -> merge(old, increment));
~~~

Đây là các **đoạn trích trong một class/method**; `State`, `initial`, `delta` và `merge` phải được ứng dụng định nghĩa. Với `AtomicReference<V>`, các hàm là `UnaryOperator<V>` và `BinaryOperator<V>`. Do đó `accumulateAndGet(x, function)` nhận **x cùng kiểu V**, khác `AtomicInteger` nhận một `int`.

**Chú ý:** AtomicReference bảo vệ việc thay **tham chiếu**; nó không làm `ref.get().mutableField++` trở thành an toàn. Khi cập nhật object state bằng functional APIs, nên tạo **immutable snapshot mới**, tránh sửa object cũ đang được các reader khác sử dụng.

## 3. CAS loop và lý do một function có thể bị gọi lại

Một mô hình logic dễ hiểu cho `updateAndGet(fn)` là:

~~~java
while (true) {
    Value before = atomic.get();
    Value candidate = fn.apply(before);
    if (atomic.compareAndSet(before, candidate)) {
        return candidate;
    }
    // Có tranh chấp: lấy current mới và thử lại.
}
~~~

Đây là **pseudocode Java-like**, với `Value` là kiểu giả định và `atomic` là atomic holder; không phải implementation nguyên văn của JDK. JDK có thể tối ưu và dùng các biến thể CAS/VarHandle khác nhau. Điều quan trọng từ hợp đồng API là: **function có thể được áp dụng lại** nếu lần cập nhật dự kiến không thành công do contention.

### Interleaving: lambda bị gọi hai lần nhưng chỉ cập nhật một lần

Giả sử `counter = 0`:

| Mốc | Thread A: `updateAndGet(x -> x + 1)` | Thread B | Counter |
|---|---|---|---|
| 1 | Đọc old = 0 | — | 0 |
| 2 | Gọi lambda lần 1, candidate = 1 | — | 0 |
| 3 | — | `incrementAndGet()`, commit 0 → 1 | 1 |
| 4 | CAS expected 0 → 1 **thất bại** | — | 1 |
| 5 | Đọc lại old = 1 | — | 1 |
| 6 | Gọi lambda lần 2, candidate = 2 | — | 1 |
| 7 | CAS expected 1 → 2 **thành công** | — | 2 |

Kết quả của A là **2**, nghĩa là phép tăng của A thực sự được commit **một lần**. Nhưng hàm do A cung cấp được tính **hai lần**. Nếu trong hàm có `sendEmail()` thì có thể gửi hai email. Nếu trong hàm có `auditCounter.incrementAndGet()` thì auditCounter có thể tăng hai lần, dù chỉ có một lần tăng của A vào state chính.

### Sự khác biệt giữa ba loại sự kiện

1. **Lambda được thực thi:** công thức tính một candidate; chưa chắc candidate được publish.
2. **CAS thành công:** candidate đã được commit thành một cập nhật atomic.
3. **Tác dụng phụ bên ngoài:** email, database, log hay sự kiện là hệ thống riêng; có thể thực thi kể cả khi CAS thất bại, và không được rollback bởi CAS.

Tính đúng yêu cầu không nhầm ba sự kiện này.

## 4. Ví dụ chạy độc lập 1: tái hiện lambda chạy hai lần một cách xác định

Ví dụ Java 17+ dùng `CountDownLatch` để ép updater A tính candidate từ 0 rồi tạm dừng. Main tăng counter từ 0 lên 1 trước khi cho A tiếp tục. Vì thế CAS đầu của A phải thất bại; A đọc lại và gọi lambda lần hai. Biến `functionCalls` cố ý là **side effect minh họa lỗi**, không phải mẫu production.

Lưu tệp **AtomicFunctionRetryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicFunctionRetryDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger(0);
        AtomicInteger functionCalls = new AtomicInteger(0);
        CountDownLatch firstEvaluation = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);

        Thread updater = new Thread(() -> {
            value.updateAndGet(old -> {
                int callNumber = functionCalls.incrementAndGet();

                if (callNumber == 1) {
                    firstEvaluation.countDown();
                    try {
                        resume.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }

                return old + 1;
            });
        }, "retry-updater");

        updater.start();
        firstEvaluation.await();

        // Main commit một update cạnh tranh trong lúc A tạm dừng.
        value.incrementAndGet();  // 0 -> 1
        resume.countDown();        // A tiếp tục, CAS cũ sẽ thất bại.
        updater.join();

        System.out.println("value=" + value.get());
        System.out.println("functionCalls=" + functionCalls.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AtomicFunctionRetryDemo.java
java AtomicFunctionRetryDemo
~~~

Output trong điều kiện không có interrupt bên ngoài:

~~~text
value=2
functionCalls=2
~~~

**Tại sao output có thể dự đoán?**

- `firstEvaluation.await()` ở main chỉ kết thúc sau khi lambda của A đã **được gọi lần đầu**, đọc `old=0` và báo tới latch.
- Trong lần đầu, A chưa trả candidate; A chờ `resume`. Main thực hiện `value.incrementAndGet()`, commit giá trị `1`.
- Main mở `resume`. Khi A tiếp tục thử commit candidate tính từ `0`, CAS mong đợi `0` thất bại vì current là `1`.
- A phải tính lại từ current = `1`, gọi lambda lần nữa; candidate 2 được commit.
- Main `join()` trước khi đọc kết quả. Không dùng `sleep()` để đoán lịch chạy.

**Đây là anti-pattern có chủ đích để giảng dạy:** lambda thực hiện `functionCalls.incrementAndGet()` và gọi `await()` trong lần đầu. Không đưa việc đợi latch, gọi external service, thay đổi metric hoặc side effect như vậy vào hàm cập nhật của hệ thống thật. Nếu một updater bị chặn bên trong callback, nó có thể kéo dài thời gian thao tác, làm tăng contention và gây rủi ro không mong muốn. Bài chỉ dùng latch để minh họa rõ hành vi retry.

## 5. Ví dụ chạy độc lập 2: updateAndGet và accumulateAndGet đúng cách

Ví dụ dưới dùng `AtomicInteger`, trong đó cả hai lambda chỉ tính giá trị mới từ đối số, **không cập nhật biến bên ngoài**.

Lưu tệp **AtomicFunctionBasicsDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicFunctionBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger(10);

        int afterUpdate = counter.updateAndGet(old -> old + 2);
        int afterAccumulate = counter.accumulateAndGet(
                5, (current, delta) -> current + delta);

        int oldFromGetAndUpdate =
                counter.getAndUpdate(old -> old * 2);

        int oldFromGetAndAccumulate = counter.getAndAccumulate(
                3, (current, delta) -> current - delta);

        System.out.println("updateAndGet=" + afterUpdate);
        System.out.println("accumulateAndGet=" + afterAccumulate);
        System.out.println("oldUpdate=" + oldFromGetAndUpdate);
        System.out.println("oldAccumulate=" + oldFromGetAndAccumulate);
        System.out.println("final=" + counter.get());
    }
}
~~~

Lệnh:

~~~bash
javac AtomicFunctionBasicsDemo.java
java AtomicFunctionBasicsDemo
~~~

Output:

~~~text
updateAndGet=12
accumulateAndGet=17
oldUpdate=17
oldAccumulate=34
final=31
~~~

Giải thích theo thứ tự **một thread**:
- Bắt đầu `10`.
- `updateAndGet(x -> x + 2)` cập nhật thành `12` và trả `12`.
- `accumulateAndGet(5, (current, delta) -> current + delta)` cập nhật thành `17` và trả `17`.
- `getAndUpdate(x -> x * 2)` thay thành `34` nhưng trả **old=17**.
- `getAndAccumulate(3, (current, delta) -> current - delta)` thay thành `31` nhưng trả **old=34**.
- `get()` cuối đọc `31`.

Với nhiều threads, mỗi lời gọi atomic có một thứ tự cập nhật hợp lệ nhưng **thứ tự giữa các thread không cố định**. Đừng dự đoán output của một bài test concurrent nếu chưa kiểm soát thứ tự.

### Tại sao thứ tự đối số của accumulateAndGet quan trọng?

Hợp đồng hàm hai đối số là:

~~~java
(current, x) -> newValue
~~~

`current` **luôn là giá trị của atomic hiện hành ở lần đánh giá đó**, còn `x` là đối số update bạn truyền. Với phép cộng, đổi thứ tự hai đối số không làm đổi kết quả. Với phép trừ, nối chuỗi hoặc phép chuyển trạng thái không giao hoán, đổi thứ tự sẽ **làm thay đổi logic**.

~~~java
AtomicInteger n = new AtomicInteger(10);
n.accumulateAndGet(3, (current, amount) -> current - amount);
// 10 - 3 = 7
~~~

Đoạn trên là minh họa trong method có import phù hợp, không phải chương trình `main` độc lập. Không viết nhầm `(amount, current) -> amount - current` nếu nghiệp vụ thật cần trừ lượng mới vào số hiện có.

## 6. Hàm cập nhật side-effect-free là thế nào?

Trong bối cảnh này, một lambda tốt nên có tính **thuần (pure) đối với shared state**:
- Chỉ dùng giá trị `old/current` và đối số dữ liệu bất biến của lời gọi.
- Tính kết quả mới **không ghi ra bên ngoài**: không sửa field, List/Map dùng chung, không tăng counter khác, không ghi file, không gửi event.
- Không gọi I/O, transaction, callback có tác dụng phụ hoặc thao tác có thể blocking lâu.
- Không làm thay đổi chính object `old` nếu object này được các readers khác giữ.
- Không phụ thuộc vào mutable state ngoài được thay đổi không đồng bộ giữa các lần retry.
- Dễ đánh giá lại nhiều lần mà vẫn không gây hại cho hệ thống.

Ví dụ tốt:

~~~java
AtomicInteger balance = new AtomicInteger(100);
int newBalance = balance.accumulateAndGet(
        20, (current, amount) -> Math.addExact(current, amount));
~~~

Đoạn trích trên có phép cộng với kiểm soát overflow. `Math.addExact` là tính toán thuần; nếu phát hiện overflow thì ném `ArithmeticException` trước khi commit candidate của lần thử đang xét.

Ví dụ không tốt:

~~~java
AtomicInteger sum = new AtomicInteger();
AtomicInteger logCounter = new AtomicInteger();

sum.updateAndGet(old -> {
    logCounter.incrementAndGet(); // side effect: có thể nhiều hơn 1
    return old + 1;
});
~~~

Cả hai atomic counters riêng đều thread-safe cho từng thao tác, **nhưng toàn bộ nghiệp vụ không có atomicity giữa hai counters**. Khi `sum` gặp contention và callback chạy lại, logCounter có thể tăng nhiều hơn số lần update `sum` thật sự thành công.

### Một hàm chỉ đọc clock/random cũng cần xem xét

~~~java
state.updateAndGet(old ->
        new State(old.value(), System.nanoTime()));
~~~

Lệnh gọi `System.nanoTime()` không trực tiếp ghi shared state trong ứng dụng, nhưng hàm không còn là một transformation ổn định từ cùng `old`: mỗi retry có thể cho timestamp khác. Nếu nghiệp vụ cần thời điểm bắt đầu của **một request** thay vì thời điểm một lần retry, hãy tính timestamp **trước** khi gọi atomic update và truyền giá trị bất biến vào hàm. Tương tự cho random input, generated ID và dữ liệu dùng để đảm bảo idempotency.

Không phải mọi sự không xác định đều làm atomicity sai, nhưng nó làm kết quả khó diễn giải, kiểm tra và khôi phục. Tách lựa chọn đầu vào khỏi pha retry là cách dễ kiểm soát hơn.

## 7. Ví dụ với AtomicReference và immutable object state

Khi cần thay nhiều field có quan hệ, `AtomicReference<State>` + immutable record thường thích hợp. Hàm cập nhật tạo **snapshot mới**, tránh sửa snapshot cũ.

Lưu tệp **AtomicStateFunctionDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateFunctionDemo {
    record Inventory(int available, int reserved) {
        Inventory {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("negative stock");
            }
        }
    }

    private final AtomicReference<Inventory> current =
            new AtomicReference<>(new Inventory(10, 0));

    Inventory addStock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        return current.updateAndGet(old -> new Inventory(
                Math.addExact(old.available(), amount),
                old.reserved()));
    }

    Inventory transferToReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        return current.updateAndGet(old -> {
            if (old.available() < amount) {
                return old; // không đủ: không thay đổi trạng thái
            }
            return new Inventory(
                    old.available() - amount,
                    Math.addExact(old.reserved(), amount));
        });
    }

    Inventory snapshot() {
        return current.get();
    }

    public static void main(String[] args) {
        AtomicStateFunctionDemo store = new AtomicStateFunctionDemo();

        store.transferToReserved(3);
        store.addStock(2);
        Inventory after = store.transferToReserved(4);
        Inventory finalState = store.snapshot();

        System.out.println("after=" + after.available()
                + "/" + after.reserved());
        System.out.println("final=" + finalState.available()
                + "/" + finalState.reserved());
    }
}
~~~

Lệnh chạy:

~~~bash
javac AtomicStateFunctionDemo.java
java AtomicStateFunctionDemo
~~~

Output khi main chạy tuần tự:

~~~text
after=5/7
final=5/7
~~~

Diễn biến:
1. Ban đầu `available=10`, `reserved=0`.
2. `transferToReserved(3)` tạo snapshot `(7,3)`.
3. `addStock(2)` tạo snapshot `(9,3)`.
4. `transferToReserved(4)` tạo snapshot `(5,7)`.
5. `snapshot()` trả reference tới một immutable Inventory với **hai field thuộc cùng một phiên bản**.

Nếu nhiều thread cập nhật cùng một instance, mỗi lời gọi `updateAndGet` có thể tính lại từ snapshot mới khi tranh chấp. Vì callback chỉ đọc `old`, `amount` và tạo object mới, retry không gây side effect ngoài. Khi số hàng không đủ, callback trả `old`, nên trạng thái bất biến giữ nguyên.

**Cảnh báo semantic:** `transferToReserved` trả về Inventory, không trả một cờ thành công riêng. Nếu caller cần phân biệt “có đặt được không”, đừng đoán từ identity hay hai lần `get()` ở bên ngoài khi vẫn có writers; hãy thiết kế API CAS loop riêng để trả outcome có nghĩa hoặc đặt kết quả nghiệp vụ trong chính state/transition thích hợp. Hàm cập nhật được chạy lại có thể trả cùng object `old`, và callback không phải nơi được phép ghi log “đã đặt chỗ” trước commit.

### Vì sao không sửa trực tiếp old?

Sai:

~~~java
AtomicReference<MutableInventory> ref = ...;
ref.updateAndGet(old -> {
    old.available -= 1;
    old.reserved += 1;
    return old;
});
~~~

Đây là đoạn minh họa lỗi, `MutableInventory` giả định là mutable class của ứng dụng. Các mutation xảy ra **trước CAS**, có thể thấy bởi reader khác, và có thể lặp nhiều lần nếu CAS retry. AtomicReference còn đang trỏ tới **chính object old**, nên CAS trên cùng reference không ngăn data race trên field. Dùng immutable state với candidate mới hoặc khóa toàn bộ mutation hợp lệ.

## 8. accumulateAndGet: kết hợp current với đầu vào của một lần gọi

Với `AtomicInteger`/`AtomicLong`, `accumulateAndGet(x, function)` thích hợp khi nghiệp vụ là “áp dụng một lượng delta vào state hiện tại”, ví dụ cộng dồn, lấy max/min, cập nhật bitmask hoặc giới hạn tăng giảm.

~~~java
AtomicInteger max = new AtomicInteger(0);

max.accumulateAndGet(12, Math::max);
max.accumulateAndGet(7, Math::max);
// giá trị cuối là 12, không cần khóa riêng cho hai lần cập nhật
~~~

Hàm là `(current, incoming) -> Math.max(current, incoming)`. Nếu không còn writer cạnh tranh ở thời điểm đọc, kết quả là 12.

Ví dụ về một giá trị có giới hạn:

~~~java
AtomicInteger used = new AtomicInteger(0);
int limit = 100;
int updated = used.accumulateAndGet(5,
        (current, amount) -> Math.min(limit, current + amount));
~~~

Đây là minh họa cho giới hạn tổng đơn giản; cần xử lý overflow nếu phép `current + amount` có thể vượt phạm vi int. Đặc biệt, nếu tài nguyên cần trả kết quả **“đã cấp thành công bao nhiêu”** hoặc từ chối atomic khi quá limit, API chỉ trả giá trị mới không tự đáp ứng toàn bộ hợp đồng nghiệp vụ. Bạn có thể cần CAS loop và một return type diễn đạt outcome.

### Phép kết hợp không phải lúc nào cũng giao hoán

Với hai thread gọi `accumulateAndGet` khác nhau:
- Các updates được commit theo một thứ tự tuyến tính hóa hợp lệ.
- Nếu phép hợp nhất giao hoán và kết hợp được, tổng cuối có thể độc lập với thứ tự.
- Nếu là phép không giao hoán như trừ hai lần với chính sách phức tạp, gắn chuỗi, ưu tiên trạng thái hoặc clamp với điều kiện, **kết quả cuối có thể phụ thuộc thứ tự commit**.
- Atomicity của từng operation **không hứa** thứ tự giữa các callers chạy đồng thời.

Tương tự, không phải cứ dùng accumulator là có thể đổi thứ tự operands hoặc tách nhiều transitions thành một mà vẫn giữ nguyên nghiệp vụ.

## 9. Dùng getAndUpdate hay updateAndGet khi nào?

Khác biệt quan trọng nhất là **giá trị trả về**, không phải độ an toàn:

~~~java
AtomicInteger n = new AtomicInteger(10);

int previous = n.getAndUpdate(old -> old + 1); // 10
int updated = n.updateAndGet(old -> old + 1);   // 12
~~~

`previous` biểu thị giá trị trước lần cập nhật atomic tương ứng. Trong concurrency, nếu cần biết số thứ tự duy nhất được cấp cho từng request, đôi khi `getAndIncrement()` phù hợp hơn vì trả số cũ chính xác của từng lần tăng.

Không nên dùng `getAndUpdate` chỉ để “giảm số lần gọi lambda”; nó cũng có thể retry và tính lại function. Hai lựa chọn có cùng nguyên tắc không side effect.

### AtomicReference và việc so sánh bằng identity

`AtomicReference.compareAndSet(expected, newValue)` so sánh current reference với expected theo **`==`**, không dùng `equals()`. Khi một update function tạo snapshot mới từ expected và CAS thất bại, JDK có thể tính lại với reference current mới.

Nếu hai immutable objects có cùng nội dung nhưng là hai references khác nhau, CAS với expected cũ thất bại như thường. Điều này tốt trong các state transition dựa trên version; nhưng cần nhớ vấn đề **ABA** khi reference từng đổi A→B→chính A cũ rồi quay lại. Nếu thuật toán yêu cầu biết mọi thay đổi trung gian, `AtomicStampedReference` hoặc versioned protocol có thể cần thiết. Các convenience update methods không tự giải quyết mọi bài toán ABA.

## 10. Ghi log hay sự kiện ở đâu cho đúng?

Giải pháp tối thiểu là **không thực hiện side effect trong callback**. Thay vì:

~~~java
balance.updateAndGet(old -> {
    sendReceipt(); // có thể bị gọi nhiều lần khi CAS retry
    return old - amount;
});
~~~

hãy tính/cập nhật một cách thuần, sau đó thực hiện side effect ở một vị trí có hợp đồng rõ ràng:

~~~java
int updated = balance.updateAndGet(old -> old - amount);
sendReceiptAfterSuccessfulUpdate(updated);
~~~

Đây là **pseudocode tích hợp**, tên `sendReceiptAfterSuccessfulUpdate` giả định do ứng dụng định nghĩa. Việc đặt send sau khi update thành công **tránh side effect bị lặp chỉ vì callback CAS retry**, nhưng **không tạo transaction atomic** giữa lần cập nhật trong JVM và việc gửi receipt bên ngoài.

Có ít nhất hai trường hợp cần giải quyết:
1. State đã commit, sau đó gửi thông điệp **thất bại**.
2. Process crash sau commit nhưng trước khi gửi; hoặc gửi thành công nhưng client không nhận được xác nhận và gửi lại request.

Nếu nghiệp vụ yêu cầu “đúng một lần” xuyên qua persistence/queue/email, chỉ dùng AtomicInteger hay AtomicReference **không đủ**. Cần thiết kế outbox/transaction/idempotency/durable processing theo hợp đồng của tài nguyên bên ngoài. Không được hứa exactly-once chỉ vì code gọi send sau `updateAndGet`.

### Không được gửi email khi state transition bị từ chối

Ví dụ chuyển tiền không đủ số dư: nếu callback chỉ trả `old` khi không đủ tiền nhưng caller gửi email “thành công” sau khi updateAndGet return, đó vẫn là logic sai. Cần **phân biệt outcome commit và outcome nghiệp vụ** một cách nguyên tử.

Một hướng dùng **CAS loop thủ công**, nơi callback chỉ tính toán, và hàm trả boolean khi kiểm tra điều kiện/commit thành công:

~~~java
boolean withdraw(AtomicInteger balance, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    while (true) {
        int before = balance.get();
        if (before < amount) {
            return false;
        }

        int after = before - amount;
        if (balance.compareAndSet(before, after)) {
            return true;
        }
    }
}
~~~

Đây là method Java hợp lệ trong một class có imports tương ứng. Toàn bộ check-then-decrement được bảo vệ bằng CAS; caller có thể gửi thông báo thành công **chỉ nếu method trả true**. Cũng ở đây, thông báo ngoài JVM vẫn không phải một phần atomic transaction với state; phải thêm giao thức nếu cần độ bền.

### Metric cho attempts khác metric cho successful commits

Việc tăng một bộ đếm `lambdaInvocations` bên trong callback có thể dùng **trong ví dụ kiểm thử để quan sát retry**, nhưng không nên ghi số “business operations completed” ở đó. Nếu cần đo contention, hãy tách metrics **CAS attempts/failures** khỏi **committed updates** và công bố rõ chúng là metrics kỹ thuật. Với tiện ích `updateAndGet`, không nhất thiết có API công khai cho số CAS retries của từng lời gọi; tự viết CAS loop khi cần quan sát/chính sách cụ thể.

## 11. Lambda capture và tính nhất quán của input

Hàm cập nhật thường capture một biến ngoài lambda:

~~~java
int delta = 5;
AtomicInteger total = new AtomicInteger();

total.accumulateAndGet(delta,
        (current, incoming) -> current + incoming);
~~~

`delta` là local effectively final, có một giá trị cố định cho lời gọi. Đó là pattern hợp lý. Khi capture một **tham chiếu tới object mutable**:

~~~java
List<String> changes = mutableList;
state.updateAndGet(old -> calculate(old, changes));
~~~

đoạn này **không tự an toàn**: dù biến `changes` effectively final, nội dung List có thể bị thread khác thay đổi trong lúc lambda chạy hoặc chạy lại, khiến kết quả không xác định. Để tránh, tạo immutable input snapshot **trước khi cập nhật** nếu cần:

~~~java
List<String> immutableChanges = List.copyOf(mutableList);
state.updateAndGet(old -> calculate(old, immutableChanges));
~~~

Đây là các đoạn minh họa trong một method; `calculate` và `state` do ứng dụng định nghĩa. `List.copyOf` bảo vệ cấu trúc List khỏi mutation qua reference gốc ở tầng container; nếu các phần tử của List là mutable objects, phải xét copy sâu/immutable elements.

Các trường hợp đáng lưu ý:
- Đọc đồng hồ, random, UUID hoặc remote data **bên trong** lambda có thể tạo candidate khác nhau qua các lần retry. Nếu cần input nhất quán cho một request, lấy chúng **trước** callback.
- Gọi API không thread-safe từ callback là rủi ro ngay cả khi không trực tiếp mutate atomic state.
- Nếu function được giữ và tái sử dụng, đừng dựa vào mutable shared fields bị thay đổi theo thời điểm để áp cùng một transformation.
- Constructor của immutable candidate cần giữ invariant; nếu bên trong constructor phát sinh side effect, nó cũng có thể được gọi lại khi retry.

## 12. AtomicReference.updateAndGet và nested mutable state

Hãy phân biệt hai việc:

**Đúng:** tạo immutable object mới rồi CAS thay reference.

~~~java
record Position(int x, int y) {}

AtomicReference<Position> position =
        new AtomicReference<>(new Position(0, 0));

position.updateAndGet(old ->
        new Position(old.x() + 1, old.y() + 1));
~~~

Reader có thể lấy một `Position snapshot = position.get()` rồi đọc x/y từ **cùng một phiên bản**.

**Sai:** thay đổi object cũ và trả lại nó.

~~~java
class MutablePosition {
    int x, y;
}

AtomicReference<MutablePosition> position =
        new AtomicReference<>(new MutablePosition());

position.updateAndGet(old -> {
    old.x++;
    old.y++;
    return old;
});
~~~

Trong ví dụ sai, nhiều threads có thể cùng sửa `old` trước bất kỳ CAS nào; reader cũng có thể thấy x đã tăng nhưng y chưa tăng. Nếu hàm phải retry, mutation có thể xảy ra nhiều lần. `AtomicReference` không biến mutable object thành transaction.

**Snapshot chỉ có giá trị khi thực sự immutable.** Với record chứa `List` hoặc `Map` mutable, bên đọc vẫn có thể thấy nội dung bị thay đổi sau publication. Dùng defensive copy, immutable nested values và ownership rõ ràng.

### Các field khác nhau trong cùng object

Nếu một invariant trải qua hai field `available` và `reserved`, hai `AtomicInteger` riêng cũng không tự tạo một operation atomic cho cả cặp. Có thể gói hai giá trị trong một immutable record và thay một reference, hoặc dùng lock chung cho toàn bộ check/update nếu state phức tạp. Atomicity của update function áp dụng cho **giá trị của một atomic variable**, không tự mở rộng sang tài nguyên thứ hai.

## 13. Java Memory Model và giới hạn quan sát

Theo tài liệu JDK, các phương thức update của atomic classes có **memory effects theo `VarHandle.compareAndSet`**; `get()` trên AtomicReference/AtomicInteger có semantics đọc volatile tương ứng, và `set()` có semantics ghi volatile tương ứng.

Khi một writer hoàn tất xây dựng immutable candidate và publish thành công qua atomic update, thread khác đọc được reference đã publish có thể quan sát các ghi phù hợp theo JMM. Tuy nhiên:

- **Happens-before/visibility** không làm cho callback trở thành “chạy một lần duy nhất”.
- Atomic update không cấm thread khác commit một update mới **ngay sau khi** bạn nhận kết quả.
- Không nên đọc một snapshot hai lần để ghép các field của hai phiên bản nếu bạn cần tính nhất quán. Lấy reference một lần, lưu local và đọc đủ field từ đó.
- Nếu object được publish nhưng tiếp tục mutate thiếu đồng bộ, lợi ích safe publication ban đầu không đủ để bảo vệ các mutation sau.
- Một CAS loop có thể tiến bộ toàn cục trong nhiều tình huống, nhưng **không cam kết từng thread riêng lẻ không bị starvation** dưới contention.

Cẩn thận với khẳng định “lock-free nghĩa là không block ở đâu”: update function của người dùng có thể tự thực hiện I/O hoặc chờ lock (dù rất không nên), khiến toàn lời gọi bị block. Các thuật toán atomic chỉ cung cấp memory/atomic semantics cho lõi cập nhật theo API, không kiểm soát mọi việc trong callback.

## 14. Hiệu năng, retry và lựa chọn giải pháp

Các convenience methods giúp code ngắn gọn, nhưng **không miễn phí** dưới tranh chấp:

| Yếu tố | Điều có thể xảy ra | Hành động hợp lý |
|---|---|---|
| Nhiều threads cùng cập nhật một giá trị | CAS thất bại, callback được tính lại | Đảm bảo function thuần, giảm độ phức tạp tính toán mỗi retry. |
| Lambda tạo immutable object lớn | Những candidates thất bại tạo allocation/GC | Đo allocation, cân nhắc mô hình dữ liệu rẻ hơn hoặc lock. |
| Lambda xử lý công việc dài | Retry nhân nhiều lần CPU work | Chuyển công việc độc lập ra trước, giữ transform nhỏ. |
| Nhiều writers và contention rất cao | Throughput/tail latency có thể kém | Benchmark cả Atomic*, Lock, sharding/aggregation theo workload. |
| Counters đơn giản | Lambda có thể không cần thiết | Dùng `incrementAndGet()`, `addAndGet()` theo ý nghĩa. |
| Metric nhiều writers, đọc tổng quan sát | Contention trên một AtomicLong | Cân nhắc `LongAdder`; `sum()` không phải atomic snapshot khi đang cập nhật. |
| Invariant nhiều trường phức tạp | CAS loop khó giữ đúng và candidate copy tốn | Cân nhắc `synchronized` hoặc `ReentrantLock` với vùng bảo vệ đúng. |
| Side effects cùng state | Atomic update không bao trùm tài nguyên ngoài | Thiết kế protocol nghiệp vụ, durability, idempotency. |

### Khi nào dùng AtomicInteger.accumulateAndGet thay cho addAndGet?

Nếu chỉ cộng một lượng delta:

~~~java
int value = counter.addAndGet(delta);
~~~

`addAndGet` rõ nghĩa và không cần callback tùy biến. `accumulateAndGet` phù hợp khi có phép kết hợp như `Math.max`, clamping có kiểm soát hoặc một transition có logic nhiều hơn phép cộng đơn giản. Không nên dùng callback phức tạp cho tất cả các counter chỉ vì API tổng quát hơn.

### Khi nào dùng synchronized?

Nếu update phải bảo vệ nhiều trường mutable, callback khó làm thuần, hoặc chi phí copy ứng viên lớn, một critical section dưới khóa chung có thể đơn giản và phù hợp hơn. Tuy nhiên, giữ lock khi gọi external I/O có thể khiến callers khác chờ lâu. Chọn theo invariant, đo contention và đặc điểm workload; không kết luận CAS luôn nhanh hơn lock hay ngược lại.

## 15. Một ví dụ logic cần tránh: side effect trước khi biết commit

Giả sử muốn “gửi một message cho mỗi lần chuyển state từ PENDING sang COMPLETED”. Sai:

~~~java
status.updateAndGet(old -> {
    if (old == State.PENDING) {
        publishMessage("completed");
        return State.COMPLETED;
    }
    return old;
});
~~~

Đây là đoạn trích không độc lập; `status`, `State` và `publishMessage` được ứng dụng định nghĩa. Với contention, callback có thể đọc PENDING, gửi message, rồi CAS thất bại vì thread khác đã chuyển state. Khi retry, callback lại gặp COMPLETED; kết quả cuối không có commit PENDING→COMPLETED từ caller ban đầu, nhưng message đã bị gửi.

Một cách tiếp cận trong **một JVM** là dùng `compareAndSet(State.PENDING, State.COMPLETED)` để biết **thread nào giành quyền transition**:

~~~java
boolean transitioned =
        status.compareAndSet(State.PENDING, State.COMPLETED);

if (transitioned) {
    publishMessage("completed");
}
~~~

Đoạn minh họa giả định State là enum; CAS dựa trên identity của constants enum. Cách này tránh publishMessage khi caller **không** thành công trong CAS, nhưng có giới hạn rất quan trọng:

- Nếu process crash sau CAS thành công nhưng trước publishMessage, event bị bỏ lỡ.
- Nếu publishMessage đã gửi nhưng xác nhận bị mất, retry có thể dẫn đến gửi lặp ở cấp hệ thống ngoài.
- AtomicReference/AtomicInteger không làm giao dịch của hệ thống khác trở nên atomic với RAM.
- Nếu request đến lần nữa sau khi state đã COMPLETED, caller nên xử lý idempotently.

Muốn đảm bảo thông báo bền vững, cần giao thức transaction/outbox hoặc một thiết kế có cam kết phù hợp ở hệ thống lưu trữ; không hứa exactly-once xuyên mọi tài nguyên chỉ bằng CAS.

## 16. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Hiểu “atomic update” thành “lambda chạy đúng một lần”.** Sai; callback có thể được đánh giá lại sau thất bại do contention. Ghi nhận candidate computation và commit là hai sự kiện khác nhau.

**Lỗi 2 — Gửi email, log nghiệp vụ hoặc tăng counter phụ trong lambda.** Side effects có thể xảy ra nhiều lần. Đưa side effects ra ngoài callback và thiết kế commit/outcome cùng retry bền vững nếu cần.

**Lỗi 3 — Đọc old bằng `get()`, tính toán rồi gọi `set(candidate)`.** Dù get/set riêng lẻ atomic, toàn bộ read–modify–write không atomic, có thể lost update. Dùng update function hoặc CAS loop.

**Lỗi 4 — Nhầm `getAndUpdate` với `updateAndGet`.** Phương thức đầu trả **old**, phương thức sau trả **new**; cả hai có thể retry.

**Lỗi 5 — Đảo ngược đối số của accumulateAndGet.** Thứ tự luôn là `(current, x)`. Với phép không giao hoán, đảo thứ tự làm sai logic.

**Lỗi 6 — Lấy `AtomicReference.get()` rồi sửa object mutable.** Reference an toàn không làm các field mutable an toàn. Dùng immutable snapshots hoặc đồng bộ khác.

**Lỗi 7 — Để function thay đổi old object rồi return old.** Mutation có thể lộ trước commit và lặp trên retry. Tạo candidate object mới, không sửa phiên bản đã publish.

**Lỗi 8 — Capture mutable List/Map/array từ ngoài callback.** Giá trị lambda có thể thay đổi qua các lần retry; dùng immutable input snapshot hoặc ownership rõ ràng.

**Lỗi 9 — Nhầm return từ updateAndGet với “tôi sở hữu giá trị hiện tại mãi”.** Thread khác có thể cập nhật ngay sau đó; kết quả chỉ gắn với điểm commit của lời gọi.

**Lỗi 10 — Dùng updateAndGet để thực hiện check-then-act với outcome nhập nhằng.** Nếu callback trả old khi không đủ điều kiện, caller cần cách diễn đạt chính xác có transition hay không; cân nhắc CAS loop trả boolean/outcome.

**Lỗi 11 — Không kiểm tra overflow.** `AtomicInteger` và `AtomicLong` không tự chống overflow. Nếu invariant yêu cầu không wrap, dùng `Math.addExact` hoặc validation thích hợp.

**Lỗi 12 — Đếm số lần callback chạy để suy ra số cập nhật thành công.** Hai con số có thể khác nhau vì CAS retry. Chỉ đếm commit theo contract thích hợp.

**Lỗi 13 — Tưởng phép cập nhật nhiều AtomicReferences là một transaction.** Chúng là các atomic variables riêng; invariant nhiều field có thể cần một immutable snapshot hoặc lock chung.

**Lỗi 14 — Tối ưu sớm bằng CAS callback rất nặng.** Trong contention, mỗi lần thất bại lãng phí việc tạo object/tính toán; đo thực tế trước khi chọn.

**Lỗi 15 — Cho rằng một bài stress test đúng là bằng chứng không có race.** Lịch chạy, JIT và CPU khác nhau có thể cho interleaving khác. Kiểm tra bằng case xác định, invariant và nhiều mức contention.

## 17. Checklist review trước khi merge code

1. **Atomic variable nào?** Một `AtomicInteger`, `AtomicLong` hay một `AtomicReference<State>` thật sự là nguồn state dùng chung?
2. **Hàm có thuần không?** Không I/O, không mutation ra ngoài, không log nghiệp vụ, không update metric phụ, không sửa old object?
3. **Có thể retry không?** Đã giả định đúng rằng function được gọi 1..N lần cho một successful update?
4. **Kết quả trả về là old hay new?** `getAnd*` trả old; `*AndGet` trả new.
5. **accumulator có thứ tự đúng?** `(current, incoming)`, không đảo operands với phép không giao hoán.
6. **Input bất biến?** Captured args có bị thay đổi đồng thời không? Immutable snapshot đủ sâu chưa?
7. **Invariant được bảo vệ ở đâu?** Candidate có được validation và publish qua một atomic commit phù hợp không?
8. **Có side effect sau commit không?** Nếu có, đã xử lý khả năng crash, gửi trùng, mất event hoặc lỗi ngoài JVM chưa?
9. **Có phân biệt business rejection với CAS contention không?** Caller phải biết có áp dụng thay đổi hay không.
10. **Có overflow và exception không?** Hàm ném trước commit; nếu nó đã có side effect thì không tự rollback.
11. **Đã kiểm tra contention thực tế chưa?** CAS retries, CPU, allocation/GC, throughput và p95/p99 latency?
12. **Một update có phải thật sự cần lambda không?** Với phép đơn giản, ưu tiên API chuyên biệt như `addAndGet`.

## 18. Bài tập thực hành và đáp án

**Câu 1.** Hai thread cùng gọi `AtomicInteger.updateAndGet(x -> x + 1)` trên cùng counter. Mỗi lời gọi có thể chạy lambda mấy lần?

**Đáp án:** Có thể một hoặc nhiều lần. Một thread có thể tính từ giá trị cũ, thua CAS, rồi gọi lại lambda với giá trị mới. Mỗi lời gọi thành công chỉ commit một update, không bảo đảm chỉ một lần đánh giá lambda.

**Câu 2.** `AtomicInteger.getAndUpdate(x -> x + 10)` trả giá trị nào?

**Đáp án:** Giá trị **cũ** ngay trước lần cập nhật đã commit. `updateAndGet` sẽ trả giá trị **mới**.

**Câu 3.** `n.accumulateAndGet(3, (current, amount) -> current - amount)` với n ban đầu 10, không có tranh chấp, trả gì?

**Đáp án:** 7. Đối số đầu callback là current=10, đối số thứ hai là amount=3.

**Câu 4.** Vì sao `emailService.send()` bên trong `updateAndGet` là nguy hiểm, dù state atomic cuối đúng?

**Đáp án:** Callback có thể được áp dụng lại khi CAS thất bại, nên email gửi nhiều lần; CAS thất bại không hoàn tác email đã gửi.

**Câu 5.** Một lambda không có side effect nhưng đọc một mutable List từ thread khác. Có đủ an toàn không?

**Đáp án:** Chưa chắc. Input có thể đổi giữa các lần retry, hoặc chính việc đọc List không thread-safe. Cần ownership, immutable snapshot hoặc cơ chế đồng bộ thích hợp.

**Câu 6.** Vì sao `AtomicReference<State>` có thể cập nhật hai field nguyên tử với immutable record, nhưng `AtomicReference<MutableState>` với mutation field thì không?

**Đáp án:** Record mới được tạo hoàn chỉnh rồi publish bằng **một reference swap**; reader giữ một phiên bản bất biến. Với MutableState, field thay đổi **bên trong object đang chia sẻ**, không qua CAS của reference.

**Câu 7.** Nếu lambda có thể bị gọi lại, làm sao tạo một request ID cố định cho cả lời gọi?

**Đáp án:** Tạo ID **trước khi** bắt đầu update, đưa nó làm immutable input vào callback. Không phát ID mới cho mỗi retry nếu business contract yêu cầu một ID trên một request.

**Câu 8.** Sau một `updateAndGet` thành công rồi gửi event ngoài JVM, có bảo đảm event đúng một lần bất kể process crash không?

**Đáp án:** Không. Atomic state trong JVM và hệ thống ngoài là hai tài nguyên; cần persistence/transaction/idempotency/outbox hoặc thiết kế tương ứng nếu yêu cầu độ bền và phát sự kiện đáng tin cậy.

## 19. Tài liệu API gốc

- **AtomicInteger (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- **AtomicLong (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- **AtomicReference (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- **AtomicStampedReference (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- **VarHandle (Java SE 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html
- **JLS `17 — Java Memory Model:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Kết luận:** `updateAndGet` và `accumulateAndGet` giúp diễn đạt **atomic read–modify–write** ngắn gọn; `getAndUpdate` và `getAndAccumulate` có cùng tính nguyên tử nhưng trả kết quả **trước** cập nhật. Trong mọi trường hợp, hàm callback có thể chạy **nhiều lần** do CAS retry: chỉ dùng **phép biến đổi thuần** từ current và immutable input để tạo candidate. Side effects, business outcome, retry bền vững và transaction ngoài JVM phải được xử lý bằng giao thức riêng, không đặt cược vào một lời gọi lambda chạy đúng một lần.
