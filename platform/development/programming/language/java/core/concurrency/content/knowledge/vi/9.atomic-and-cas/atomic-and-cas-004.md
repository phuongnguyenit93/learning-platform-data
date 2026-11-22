# CAS loop, retry và contention trong Java

**Compare-and-set (CAS)** là phép cập nhật nguyên tử có điều kiện: “chỉ thay giá trị hiện tại bằng giá trị mới nếu nó vẫn bằng giá trị mà tôi kỳ vọng”. Trong Java, CAS được cung cấp qua `AtomicInteger`, `AtomicLong`, `AtomicReference`, các lớp atomic khác và `VarHandle`. Từ CAS, ta có thể xây **vòng lặp thử lại** (*CAS loop*) để cập nhật trạng thái chia sẻ mà không cần mutex cho mỗi phép thay đổi nhỏ.

Tuy nhiên, khi nhiều thread cùng tranh một biến (*contention*), vòng CAS có thể phải tính lại và thử nhiều lần. Nó có thể tiết kiệm khóa ở tình huống thích hợp nhưng **không miễn phí, không mặc nhiên fair, không đảm bảo mỗi thread hoàn thành nhanh**, và còn có bẫy về side effects, ABA, overflow, memory ordering và việc đặt retry vô hạn trong request có deadline.

Bài viết tập trung vào **Java concurrency nói chung**, không dựa vào cơ chế của Spring hay framework.

## 1. CAS thực hiện chính xác điều gì?

Giả sử `state` là một `AtomicInteger` đang giữ số `10`:

```java
boolean ok = state.compareAndSet(10, 11);
```

Đây là snippet. CAS kiểm tra **tại điểm nguyên tử thực thi** rằng giá trị hiện tại có bằng `10` hay không. Nếu có, nó cập nhật thành `11` và trả `true`; nếu không, nó không ghi và trả `false`.

| State trước CAS | Operation | Trả về | State sau CAS |
| --- | --- | --- | --- |
| `10` | `compareAndSet(10, 11)` | `true` | `11` |
| `11` | `compareAndSet(10, 12)` | `false` | `11` |
| `11` | `compareAndSet(11, 12)` | `true` | `12` |

CAS gộp việc **so sánh và cập nhật chính một vị trí** thành một thao tác nguyên tử. Đoạn khác trông tương đương nhưng **không nguyên tử**:

```java
if (state.get() == 10) {
    state.set(11);
}
```

Đây là hai method calls riêng. Thread B có thể sửa state sau khi thread A `get()` nhưng trước khi A `set()`. Không nên gọi “field atomic” rồi giả định mọi workflow ghép các method atomic đều tự nhiên atomic.

**Ba thành phần của CAS:** vị trí lưu state, giá trị expected đã quan sát và giá trị proposed update. CAS **không** tự cam kết gì về một database, một file, một phép gọi mạng hoặc các field khác không thuộc vị trí atomic đó.

## 2. Vì sao phải viết CAS loop?

Một phép CAS có thể thất bại hợp lệ khi một thread khác đã cập nhật state trước. Thay vì bỏ cuộc, nhiều thuật toán thử lại từ snapshot mới:

```java
for (;;) {
    int oldValue = state.get();
    int newValue = transform(oldValue);

    if (state.compareAndSet(oldValue, newValue)) {
        return;
    }
    // Snapshot cũ không còn hợp lệ: đọc mới và tính lại.
}
```

Đây là **snippet minh họa**, giả định `state` là `AtomicInteger`, `transform` là một phép biến đổi thuần và code nằm trong method `void`. Trình tự:

1. **Read:** đọc state hiện tại.
2. **Validate/compute:** kiểm tra invariant và tính proposed state dựa vào giá trị vừa đọc.
3. **CAS:** thử cập nhật nguyên tử.
4. **Success:** hoàn tất đúng một lần cập nhật.
5. **Failure:** đọc lại, kiểm tra lại điều kiện, tính lại kết quả và thử lại.

**Sai lầm nghiêm trọng** là đọc `oldValue` một lần ở ngoài vòng rồi cứ dùng expected đó khi retry. Nếu state đã đổi, vòng có thể spin mãi hoặc áp dụng quyết định đã lỗi thời.

### Ví dụ: bán hàng còn tồn kho

```java
boolean sellOne(AtomicInteger stock) {
    for (;;) {
        int current = stock.get();
        if (current <= 0) {
            return false;
        }
        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
```

Snippet method cần import `java.util.concurrent.atomic.AtomicInteger` và đặt trong class. Nếu hai thread cùng thấy `stock = 1`, chỉ một CAS `1 -> 0` thành công. Thread còn lại retry, đọc `0` và trả `false`. **Đọc lại điều kiện `current <= 0` là phần bắt buộc**: không thể mù quáng thử trừ từ snapshot cũ.

## 3. Retry là tín hiệu contention, không phải exception

Tưởng tượng hai thread cùng đọc version `7`:

```text
A: read version = 7
B: read version = 7
B: CAS(7 -> 8) succeeds
A: CAS(7 -> 8) fails
A: read version = 8
A: compute a new update
A: CAS(8 -> 9) succeeds
```

Khi A thất bại, có thể B **đã tiến triển**; không có exception nghiệp vụ. Trong nhiều thuật toán, đây là điều thường xuyên xảy ra và cần retry. Nhưng một lần retry cũng làm lãng phí ít nhất một số thao tác đọc, tính toán và thử CAS.

Một CAS mạnh `compareAndSet` trên `AtomicInteger` thất bại khi expected không khớp với state tại thời điểm phép thử. Lưu ý `compareAndSet` của `AtomicReference` so sánh **reference identity**, không phải `equals`; việc expected bằng hay khác tùy vào API cụ thể.

**Không phải CAS nào cũng phải retry vô hạn.** Một method cấp thấp có thể liên tục thử tới khi thắng; một request có SLA có thể cần retry budget, deadline, cancellation và kết quả “busy” khi quá tải. Nếu điều kiện nghiệp vụ thay đổi (hết tồn kho, trạng thái đã chuyển), retry có thể **kết thúc bằng false** mà không phải lỗi.

## 4. Java 17: test điều phối để chắc chắn thấy một CAS thất bại

Đếm failed CAS trong một stress test nhỏ có thể luôn ra `0` trên máy ít tải vì hai worker không thực sự tranh nhau. Để học cơ chế, ta cố tình dùng `CyclicBarrier` buộc **cả hai đọc cùng giá trị `0` trước khi ai được phép thử CAS đầu tiên**.

Tạo tệp `CASRetryDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CASRetryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger(0);
        AtomicInteger failures = new AtomicInteger(0);
        CyclicBarrier bothRead = new CyclicBarrier(2);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Void> increment = () -> {
                int attempt = 0;
                for (;;) {
                    int oldValue = counter.get();

                    if (attempt == 0) {
                        bothRead.await(5, TimeUnit.SECONDS);
                    }

                    if (counter.compareAndSet(oldValue, oldValue + 1)) {
                        return null;
                    }

                    failures.incrementAndGet();
                    attempt++;
                }
            };

            Future<Void> first = pool.submit(increment);
            Future<Void> second = pool.submit(increment);

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            System.out.println("counter=" + counter.get());
            System.out.println("failedCAS=" + failures.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac CASRetryDemo.java
java CASRetryDemo
```

Stdout **khi cả hai worker đến barrier và hoàn thành trước timeout**:

```text
counter=2
failedCAS=1
```

**Vì sao xác định?** Hai worker đều đọc `0` trước barrier. Một CAS `compareAndSet(0,1)` thành công; lần CAS đầu của người còn lại thất bại vì state giờ là `1`. Worker thua đếm một thất bại, đọc lại `1` và CAS `1 -> 2` thành công. Ai thắng trước không ảnh hưởng kết quả. `Future.get` giúp main nhận exception worker và chỉ in khi cả hai xong.

Đây là **test chủ động tạo một interleaving**, không phải dự đoán retry trung bình dưới tải thực. Barrier tạo thêm quan hệ happens-before, nên không dùng chương trình để suy diễn về mọi outcome JMM trong code không có barrier. Timeout giúp test thất bại rõ khi participant vắng mặt, không phải cam kết mọi máy sẽ hoàn thành chính xác trong năm giây.

## 5. CAS và `volatile`: visibility không đủ cho read–modify–write

Khai báo:

```java
volatile int count;

void increment() {
    count++;
}
```

là snippet trong class. `volatile` giúp các lần truy cập có semantics về visibility/ordering, nhưng `count++` gồm read–modify–write về mặt logic. A có thể đọc `0`, B đọc `0`, rồi cả hai ghi `1`. Hai lần tăng nhưng kết quả chỉ `1`.

`AtomicInteger.incrementAndGet()` đã giải quyết phép tăng bằng operation atomic. Khi chỉ cần tăng hoặc cộng số:

```java
AtomicInteger count = new AtomicInteger();
int newValue = count.incrementAndGet();
int beforeAdd = count.getAndAdd(5);
```

Snippet cần import `AtomicInteger`. Nên dùng các operation đã có thay vì viết CAS loop thủ công cho phép cộng không có thêm điều kiện. Vòng CAS tùy chỉnh có ích nếu **toàn bộ điều kiện và update** cần dựa trên state hiện hành, ví dụ trừ quota chỉ nếu còn đủ.

`AtomicInteger.updateAndGet`, `getAndUpdate`, `accumulateAndGet` cũng cung cấp phép update theo function. **Function có thể được đánh giá nhiều lần khi contention**, nên phải thuần và không mang side effects không thể lặp an toàn.

## 6. Contention làm CAS loop tốn chi phí ở đâu?

**Contention** là nhiều thread cùng cạnh tranh cập nhật một state chia sẻ. Một biến atomic là **điểm nóng** khi nhiều core cùng làm phép read–modify–write.

Các dạng chi phí:

- **Failed CAS:** phải đọc lại state, tính lại proposed value; nếu phép tính đắt, tổng công việc bị lặp lớn.
- **Cache coherence:** một cache line cần chuyển quyền sở hữu khi nhiều core cập nhật cùng vùng nhớ, kể cả khi CAS thành công.
- **Busy-spinning:** retry liên tục giữ CPU bận, trong khi worker chưa tạo thêm một update thành công.
- **Tail latency:** một worker có thể thua CAS nhiều lần trước khi thắng; p95/p99 tăng dù throughput trung bình vẫn cao.
- **Starvation:** một thread liên tục bị thread khác vượt qua; CAS không mặc nhiên cho lịch công bằng FIFO.
- **False sharing:** hai biến logic độc lập nhưng tình cờ ở gần cùng cache line có thể gây ảnh hưởng cache coherence; tách điểm nóng hoặc dùng layout phù hợp đôi khi giúp, nhưng phải đo.

Càng nhiều thread **không nhất thiết** càng nhiều updates/giây. Có điểm bão hòa khi CPU, cache, coherence và bộ nhớ giới hạn. Đo failed attempts/update, throughput, latency và CPU theo số writer để nhận biết.

Một thất bại CAS không phải luôn là dấu hiệu bất lợi: trong thuật toán lock-free phù hợp, failure có thể đồng nghĩa **một thread khác đã tiến triển**. Vấn đề là mức thất bại và chi phí tổng thể so với mục tiêu throughput/latency.

### Đừng đo contention bằng cách tự tạo thêm contention

Nếu mỗi lần CAS fail đều cập nhật một `AtomicLong failedAttempts` chung, chính metric có thể trở thành hotspot! Trong benchmark, cân nhắc per-thread counters và tổng hợp sau khi hoàn tất; trong hệ thống thực, dùng sampling/tracing/metrics có chi phí kiểm soát.

## 7. Lock-free, wait-free và các bảo đảm tiến triển

Không nên dùng các từ này như đồng nghĩa của “có dùng CAS”.

| Khái niệm | Bảo đảm khái quát |
| --- | --- |
| **Blocking** | Một operation có thể chờ người khác nhả mutex hoặc hoàn thành công việc |
| **Obstruction-free** | Một thread có thể tiến triển khi nó chạy riêng đủ lâu không có contention |
| **Lock-free** | Hệ thống có tiến triển tổng thể; một thread riêng có thể cứ phải retry |
| **Wait-free** | Mỗi operation hoàn thành sau số bước hữu hạn bị chặn theo thuật toán, dù các thread khác tranh chấp |

CAS loop dùng `AtomicInteger` có thể là một phần thuật toán lock-free, nhưng **không tự động khiến toàn method lock-free** nếu body còn chờ latch, gọi I/O hoặc giữ monitor. Và lock-free **không** đảm bảo mỗi request thắng nhanh: một worker có thể bị starvation trong khi worker khác liên tục thành công.

Progress guarantee cần được phân tích ở cấp **toàn thuật toán**, cùng các giả định về scheduler và phần công việc khác; không thể kết luận chỉ từ việc nhìn thấy `compareAndSet`.

## 8. Java 17: CAS loop bảo vệ invariant tồn kho

Tạo `CASInventoryExample.java`, trong đó chỉ có một sản phẩm và hai thread cùng muốn mua:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CASInventoryExample {
    static class Inventory {
        private final AtomicInteger stock;

        Inventory(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("negative stock");
            }
            this.stock = new AtomicInteger(initial);
        }

        boolean sellOne() {
            for (;;) {
                int current = stock.get();
                if (current == 0) {
                    return false;
                }
                if (stock.compareAndSet(current, current - 1)) {
                    return true;
                }
            }
        }

        int remaining() {
            return stock.get();
        }
    }

    public static void main(String[] args) throws Exception {
        Inventory inventory = new Inventory(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Callable<Boolean> purchase = inventory::sellOne;
            Future<Boolean> first = pool.submit(purchase);
            Future<Boolean> second = pool.submit(purchase);

            int successful =
                    (first.get(5, TimeUnit.SECONDS) ? 1 : 0)
                  + (second.get(5, TimeUnit.SECONDS) ? 1 : 0);

            System.out.println("successful=" + successful);
            System.out.println("remaining=" + inventory.remaining());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac CASInventoryExample.java
java CASInventoryExample
```

Stdout khi hoàn thành bình thường:

```text
successful=1
remaining=0
```

Bất kể thread nào thắng, chỉ một CAS `1 -> 0` thành công; worker còn lại đọc `0` hoặc retry rồi thấy `0` và trả false. Không có số lần retry cố định trong ví dụ này, vì scheduler có thể cho worker thứ hai bắt đầu sau khi stock đã hết.

**Phạm vi atomicity rất quan trọng:** đây là “tồn kho trong một JVM”, không phải transaction hoàn chỉnh giữa tồn kho, thanh toán, DB và hệ thống vận chuyển. CAS trong RAM không chống oversell nếu nhiều instance độc lập quản lý mỗi instance một counter và không phối hợp tại nguồn dữ liệu chung.

## 9. Một số mẫu CAS loop sai

### 9.1. Retry bằng expected đã lỗi thời

```java
int old = stock.get();
if (old == 0) return false;

while (!stock.compareAndSet(old, old - 1)) {
    // Lỗi: old không bao giờ được làm mới.
}
return true;
```

Snippet trong một method `boolean`. Nếu thread khác đổi stock, expected cũ có thể không bao giờ khớp lại, gây vòng spin vô hạn. Hãy **đọc lại state bên trong vòng** và kiểm tra lại điều kiện nghiệp vụ.

### 9.2. Cập nhật expected nhưng không kiểm tra lại invariant

```java
int old = stock.get();
for (;;) {
    if (stock.compareAndSet(old, old - 1)) {
        return true;
    }
    old = stock.get(); // Thiếu kiểm tra stock > 0.
}
```

Snippet sai vì có thể trừ `0 -> -1`. Cập nhật giá trị expected là cần nhưng **không đủ**; mỗi retry phải xem update có còn hợp lệ không.

### 9.3. Kiểm tra điều kiện trên field thường không đồng bộ

```java
if (account.isOpen()) {
    balance.compareAndSet(oldBalance, newBalance);
}
```

Nếu `isOpen()` phụ thuộc một state khác mà thread khác có thể thay đổi không phối hợp, phép CAS trên `balance` **không** làm nguyên tử cả điều kiện `isOpen` và cập nhật. Có thể cần chuyển mọi invariant vào một **immutable aggregate** được cập nhật bằng một `AtomicReference`, hoặc dùng lock chung/state machine thích hợp.

### 9.4. Bỏ qua overflow

`current + 1` với `int` có thể overflow sang âm. CAS không sửa lỗi toán học; khi ứng dụng yêu cầu counter không vượt `Integer.MAX_VALUE`, cần kiểm tra trước mỗi CAS hoặc chọn kiểu lớn hơn và vẫn định nghĩa ngưỡng hợp lệ.

## 10. Side effects trong retry: tuyệt đối không xem như chạy một lần

Đoạn sau **sai về nghiệp vụ**:

```java
for (;;) {
    int previous = balance.get();
    chargeExternalPayment(); // Có thể chạy nhiều lần!
    if (balance.compareAndSet(previous, previous - 1)) {
        return;
    }
}
```

Đây là snippet, chưa có kiểm tra số dư và chưa độc lập. Nếu CAS thua do thread khác sửa `balance`, vòng gọi `chargeExternalPayment()` lần nữa, có thể tính phí hai lần dù chỉ một cập nhật trong RAM được chấp nhận. Nếu payment API thành công nhưng response mất, việc retry còn phức tạp hơn.

**Quy tắc:** phần tính proposed state trong CAS loop nên là **pure function**, không chứa side effects không idempotent. Việc chuyển side effects ra sau CAS cũng chưa tự tạo exactly-once xuyên crash/network; cần transaction, idempotency key, outbox hoặc workflow bù trừ phù hợp.

Với `AtomicInteger.updateAndGet(x -> transform(x))`, `transform` có thể được gọi lại nhiều lần do contention. Đừng đặt gửi email, metric đếm “thành công”, ghi DB hoặc thay đổi collaborator mutable trong update function nếu không hiểu semantics lặp.

Đoạn minh họa thuần:

```java
AtomicInteger level = new AtomicInteger(3);
int capped = level.updateAndGet(x -> Math.min(x + 1, 10));
```

Update function chỉ tính toán trên input, không tác động ra ngoài. **Nhưng** một function “có vẻ thuần” mà lại đọc clock hoặc state mutable khác có thể cho ra proposed value khác nhau mỗi lần retry; cần định nghĩa rõ snapshot input của operation và trạng thái nào được phép đọc lại.

## 11. ABA: state quay về giá trị cũ nhưng đã có thay đổi ở giữa

CAS chỉ so sánh giá trị **ở thời điểm CAS**, không kiểm tra lịch sử. Ví dụ:

```text
A: read reference = object X
B: X -> Y
B: Y -> X
A: compareAndSet(expected=X, update=Z) succeeds
```

Nếu ứng dụng chỉ quan tâm reference hiện tại là X, điều này có thể chấp nhận được. Nhưng một thuật toán lock-free về node/resource có thể yêu cầu “node chưa hề bị tháo và đưa lại”; khi đó **ABA** là lỗi.

### Java 17: ví dụ ABA và version stamp

Tạo `ABADemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class ABADemo {
    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();

        AtomicReference<Object> plain = new AtomicReference<>(a);
        Object expected = plain.get();

        plain.compareAndSet(a, b);
        plain.compareAndSet(b, a);

        boolean plainAccepted =
                plain.compareAndSet(expected, c);
        System.out.println("plainAccepted=" + plainAccepted);

        AtomicStampedReference<Object> stamped =
                new AtomicStampedReference<>(a, 0);
        Object expectedRef = stamped.getReference();
        int expectedStamp = stamped.getStamp();

        stamped.compareAndSet(a, b, 0, 1);
        stamped.compareAndSet(b, a, 1, 2);

        boolean stampedAccepted =
                stamped.compareAndSet(expectedRef, c,
                                      expectedStamp, expectedStamp + 1);
        System.out.println("stampedAccepted=" + stampedAccepted);
        System.out.println("currentStamp=" + stamped.getStamp());
    }
}
```

```bash
javac ABADemo.java
java ABADemo
```

Stdout:

```text
plainAccepted=true
stampedAccepted=false
currentStamp=2
```

Ví dụ chạy tuần tự để mô phỏng lịch concurrent, do đó output xác định. `AtomicReference` so sánh reference bằng identity: object `a` đã quay lại **đúng instance cũ**, nên CAS của plain reference nhận. `AtomicStampedReference` kiểm tra đồng thời reference và version: state đã trải qua `stamp 0 -> 1 -> 2`, nên expected stamp cũ `0` bị từ chối.

Stamp không tự giải quyết mọi chuyện: version hữu hạn có thể wrap hoặc bị tái sử dụng nếu thiết kế thiếu kỷ luật, và quản lý node memory/reclamation của thuật toán không khóa vẫn cần phân tích riêng.

## 12. Strong CAS, weak CAS và memory ordering

`AtomicInteger.compareAndSet` là CAS mạnh theo hợp đồng API. Một số biến thể **weak CAS** như `weakCompareAndSetPlain` được phép **spurious failure**: trả `false` dù expected trùng state. Những method mang hậu tố `Plain`, `Acquire`, `Release` và dạng volatile còn khác nhau về **memory-order semantics**.

Điểm cần nhớ:

- Với strong `compareAndSet`, nếu expected không còn khớp thì operation fail. Một lần fail là bình thường dưới contention.
- Với weak CAS, loop phải chấp nhận fail ngay cả khi không có concurrent modification.
- Không đổi sang `weakCompareAndSetPlain` để “nhanh hơn” nếu thuật toán dựa vào volatile publication/happens-before mà chưa phân tích.
- `VarHandle.compareAndExchange` trả về **witness value** (giá trị đã quan sát), khác `compareAndSet` trả `boolean`. Đọc hợp đồng từng API trước khi dùng.
- Không mặc định weak CAS tốt hơn strong CAS trên mọi CPU/JDK; microbenchmark với workload thật khi tối ưu.

CAS trên `AtomicInteger` có memory effects được định nghĩa; operation mặc định tương ứng với semantics phù hợp cho atomic/volatile access. Nhưng **atomicity và visibility không gộp tất cả mutable objects khác thành một transaction**. Nếu tham chiếu atomic trỏ đến một object mutable và thread khác thay đổi phần tử bên trong, CAS reference không tự bảo vệ phần tử ấy.

## 13. Backoff, spin và `Thread.onSpinWait()`

Với contention nhẹ, retry ngay sau khi CAS fail thường đơn giản. Với contention nặng, hàng chục worker cùng spin vào một địa chỉ có thể làm tăng CPU/cache coherence và tail latency.

### Spin hint

Java 9+ hỗ trợ:

```java
int retries = 0;
for (;;) {
    int old = value.get();
    if (value.compareAndSet(old, old + 1)) {
        break;
    }
    retries++;
    if (retries > 16) {
        Thread.onSpinWait();
    }
}
```

Đây là snippet với `value` kiểu `AtomicInteger`. `Thread.onSpinWait()` là **hint cho JVM/CPU**, không phải yield có cam kết công bằng, không tạo timeout và không thay thế lock/condition. Nó có thể giúp một số spin-loop nhưng vẫn tiêu tốn CPU.

### Backoff

Một số chiến lược:

| Chiến lược | Ưu | Nhược |
| --- | --- | --- |
| Retry liên tục | Độ trễ thấp khi ít tranh chấp | Nóng CPU/cache khi nhiều writer |
| Fixed pause | Dễ đặt ngưỡng | Có thể trì hoãn vô ích khi contention giảm |
| Exponential backoff | Giảm tần suất thử nếu thất bại liên tiếp | Nếu tăng quá mức, latency cao |
| Random jitter | Tránh nhiều thread đồng bộ thức dậy cùng lúc | Tăng biến thiên latency và khó chứng minh fairness |
| Partition/shard state | Giảm nguồn contention | Tăng phức tạp tổng hợp/consistency |

`LockSupport.parkNanos(...)` có thể tạm park, nhưng **không bảo đảm ngủ đúng số nanos**: có thể trở lại vì interrupt/unpark/spurious return và scheduler ảnh hưởng thời gian. Backoff cũng **không** mang lại tính fair tuyệt đối.

### Pseudocode minh họa có backoff

```java
long pause = 1_000L;
for (;;) {
    int old = value.get();
    int next = transform(old);

    if (value.compareAndSet(old, next)) {
        return;
    }
    java.util.concurrent.locks.LockSupport.parkNanos(pause);
    pause = Math.min(pause * 2, 1_000_000L);
}
```

Đây là snippet giả định `value`, `transform` và một method `void`; **chưa xử lý cancellation, deadline, overflow và business-side effects**. Không dùng nguyên xi trong request production. Chọn backoff bằng số đo và semantics; đừng áp một khoảng nghỉ “chuẩn” cho mọi ứng dụng.

## 14. CAS loop có thời hạn và khả năng hủy

Một vòng retry vô hạn có thể phù hợp trong atomic class cấp thấp, nhưng trên đường request với SLA cần hợp đồng:

- **Thành công:** CAS thành công và invariant được áp dụng.
- **Từ chối có điều kiện:** state mới không còn đủ điều kiện (ví dụ stock = 0).
- **Bận/timeout:** retry vượt budget/deadline mà chưa cập nhật.
- **Hủy:** thread bị yêu cầu cancel; một CAS loop CPU-bound không tự ném `InterruptedException`.
- **Không chắc trạng thái external side effect:** không được đoán “chưa xảy ra” chỉ vì HTTP response mất; dùng idempotency/transaction.

Snippet giới hạn số lần thử:

```java
boolean tryIncrement(AtomicInteger value, int maxAttempts) {
    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts");
    }

    for (int n = 0; n < maxAttempts; n++) {
        if (Thread.currentThread().isInterrupted()) {
            return false;
        }

        int current = value.get();
        if (value.compareAndSet(current, current + 1)) {
            return true;
        }

        Thread.onSpinWait();
    }
    return false;
}
```

Đây là snippet trong class, import `AtomicInteger`. `false` nghĩa **chưa cập nhật**, có thể do cancellation hoặc quá nhiều CAS fail; nếu API cần phân biệt hai trường hợp, trả enum/result thay boolean. Kiểm tra overflow trước CAS nếu invariant không cho phép tràn. Giới hạn attempts **không bảo đảm một thời gian thực cố định** vì scheduler có thể tạm dừng thread bất kỳ lúc nào.

### Khi retry backoff làm giảm throughput

Ở contention thấp, mỗi lần `parkNanos` có overhead, có thể làm tệ hơn retry trực tiếp. Ở contention cao, backoff có thể giúp tránh “thundering herd”. Mức tốt tùy CPU, JVM, access pattern, số core và chi phí tính proposed state. Không đo thì không kết luận.

## 15. `AtomicLong` hay `LongAdder` khi nhiều writer?

Nếu ứng dụng chỉ đếm số event, có hai lựa chọn tiêu biểu:

- `AtomicLong.incrementAndGet()`: operation tuyến tính hóa trên một biến; có thể đọc giá trị chính xác theo semantics của atomic operation.
- `LongAdder.increment()`: chia cập nhật qua nhiều cell nội bộ dưới contention để tăng throughput trong một số workload. `LongAdder.sum()` **không phải một snapshot nguyên tử đối với cập nhật đang đồng thời**.

Vì vậy `LongAdder` phù hợp với **metrics/statistics** nếu chấp nhận giá trị tổng tại thời điểm đọc không có một linearization point duy nhất; **không** phù hợp để thay `AtomicLong` trong “nếu số dư > 0 thì trừ” hoặc “chỉ cho phép tối đa N reservations” cần một quyết định atomic.

Không nên tự động chọn `LongAdder` cho một counter ít writer; memory và chi phí tổng hợp có thể cao hơn. Benchmark đúng workload.

## 16. Immutable snapshot + CAS khi nhiều field liên quan

Nếu state gồm `version` và `stock`, cập nhật hai field `AtomicInteger` riêng lẻ không tự tạo snapshot nguyên tử. Có thể gói chúng thành **immutable aggregate** và dùng `AtomicReference` CAS trên toàn reference:

```java
record Snapshot(int version, int stock) {}

AtomicReference<Snapshot> current =
        new AtomicReference<>(new Snapshot(0, 5));

for (;;) {
    Snapshot old = current.get();
    if (old.stock() == 0) {
        break;
    }

    Snapshot next =
            new Snapshot(old.version() + 1, old.stock() - 1);

    if (current.compareAndSet(old, next)) {
        break;
    }
}
```

Snippet Java 17 cần import `AtomicReference` và nằm trong method phù hợp. Mỗi reader lấy **một reference** sẽ quan sát version/stock cùng một snapshot. Khi CAS fail, writer phải tạo lại snapshot từ bản mới. Record có hai primitive nên bản thân snapshot này bất biến.

Nếu snapshot chứa `List<MutableItem>`, record không tự deep-copy phần tử; phải thiết kế immutable value/ownership đúng cách. Nếu nhiều writer có side effects ngoài state, một CAS reference cũng không tự làm toàn workflow nguyên tử xuyên nhiều hệ thống.

## 17. Benchmark và tìm nguyên nhân contention

Không dùng một phép đo đơn lẻ trên máy cá nhân để kết luận `compareAndSet` “nhanh hơn synchronized” trong mọi trường hợp. JIT warmup, GC, false sharing, CPU architecture, cache-line layout, number of cores và chi phí transform đều ảnh hưởng.

| Chỉ số | Hỏi điều gì? |
| --- | --- |
| Successful updates/s | Throughput thực tế có tăng khi thêm writer không? |
| Attempts per success | Một cập nhật phải thử trung bình bao nhiêu lần? |
| Failure ratio | Thất bại bao nhiêu trên toàn bộ attempts? |
| Latency p50/p95/p99 | Tail latency có tăng dưới contention không? |
| CPU utilization | Busy-spin có chiếm quá nhiều CPU không? |
| Fairness per worker | Có worker nào liên tục không được hoàn tất? |
| Coherence/cache metrics | Có hotspot hoặc false sharing không? |
| Correctness/invariant | Có lost update, stock âm hoặc side effect lặp không? |

**JMH** có cơ chế warmup, fork, measurement và tránh những lỗi benchmark micro phổ biến; dùng để so các operation có **cùng semantics**, nhiều mức thread count và workload đại diện. Kết hợp JFR/CPU profiling, stress test và load test hệ thống. Mục tiêu đầu tiên là **đúng invariant**, sau đó mới tối ưu.

Với benchmark CAS loop, hãy cẩn thận không đặt một atomic counter đo thất bại ở chính hotspot cạnh tranh; instrumentation có thể làm thay đổi kết quả. Đếm cục bộ trên mỗi worker hoặc sử dụng công cụ profiling phù hợp rồi tổng hợp.

## 18. ABA không phải vấn đề duy nhất của cấu trúc lock-free

Với một stack/queue tự thiết kế bằng CAS, còn nhiều câu hỏi ngoài primitive:

- **Node lifecycle:** node có được phép tái sử dụng hay bị tháo/đưa lại trong lúc thread khác còn reference cũ?
- **Memory visibility:** khi publish node mới, các field đã khởi tạo có thể được reader quan sát đúng không?
- **Invariant khi retry:** nếu cập nhật một pointer thất bại, có phải đọc lại cả chuỗi node đang quan sát?
- **Progress:** có thread nào có thể bị starvation; nếu worker thất bại/treo, các thread khác còn tiến triển không?
- **Memory reclamation:** loại bỏ node không đồng nghĩa có thể tái sử dụng an toàn tức thì trong mọi thuật toán; JVM GC quản lý memory vật lý nhưng không giải quyết mọi logical ABA/node reuse.
- **Exception/cancellation:** nếu tính proposed state ném exception, state vẫn đúng không?
- **Fairness:** nếu một thread phải retry mãi dưới cạnh tranh cao, service-level response nên làm gì?

Khi không có nhu cầu đặc biệt, ưu tiên các cấu trúc đã được kiểm chứng trong `java.util.concurrent` thay vì tự viết lock-free queue/stack. Một atomic CAS nhỏ là primitive an toàn; chứng minh một thuật toán lock-free hoàn chỉnh khó hơn nhiều.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Retry mãi với expected cũ | Spin vô hạn hoặc không tiến triển | Đọc state mới mỗi vòng |
| Update từ snapshot cũ | Ghi đè/logic sai | Đánh giá lại predicate và proposed state |
| Coi `get` + `set` là CAS | Check–then–act bị xen ngang | Dùng CAS hoặc operation atomic phù hợp |
| Dùng `volatile count++` | Lost update | `incrementAndGet` hoặc CAS đúng |
| Cho I/O/side effect vào retry | Có thể chạy nhiều lần | Tách effect, dùng transaction/idempotency |
| Callback trong `updateAndGet` không pure | Có thể có side effect lặp | Function thuần, an toàn khi re-evaluate |
| Không xử lý ABA khi cần version | CAS chấp nhận A→B→A | Version/stamp/ownership phù hợp |
| Nhầm weak CAS với strong CAS | Sai về spurious failure/memory ordering | Đọc đúng hợp đồng method |
| Gọi mọi CAS loop là wait-free | Che starvation | Phân tích progress toàn thuật toán |
| Spin mãi trong request có deadline | CPU cao, latency không kiểm soát | Retry budget/deadline/cancel |
| Luôn dùng backoff | Thêm latency dưới contention nhẹ | Benchmark/điều chỉnh theo tải |
| Một CAS chỉ bảo vệ một field nhưng invariant nhiều field | Snapshot không nhất quán | Immutable aggregate+CAS hoặc mutex |
| `LongAdder.sum()` thay atomic balance | Không phải atomic snapshot | Dùng atomic operation đủ mạnh |
| CAS trên JVM rồi coi như DB transaction | Quá bán hàng ở nhiều process | Đồng bộ tại nguồn dữ liệu/transaction |
| Instrumentation dùng một atomic hotspot | Đo làm tăng contention | Per-thread metrics/sampling |
| Quên integer overflow | Counter/quota sai | Kiểm tra ngưỡng trong mỗi vòng |
| Chỉ test một lịch chạy | Không thấy bug lạ | Stress+coordinated tests+JMM reasoning |

## 20. Chọn thiết kế theo tình huống

**Counter ít writer, cần giá trị chính xác theo từng operation:** `AtomicInteger`/`AtomicLong` method có sẵn; không cần tự CAS loop.

**Counter thống kê cực nhiều writer:** cân nhắc `LongAdder`, nếu chấp nhận `sum` không snapshot nguyên tử khi có updates đồng thời.

**Quota trong một JVM:** CAS loop với check-and-decrement; sau mỗi thất bại đọc lại quota và quyết định có còn được phép không.

**Immutable configuration:** publish snapshot qua `volatile`/`AtomicReference`; nếu nhiều writers cùng dựa vào old version, CAS có thể tránh lost update.

**Một nghiệp vụ nhiều field hoặc nhiều external resources:** cân nhắc `synchronized`, `ReentrantLock`, transaction, queue/ownership và idempotency. Một CAS trên biến cờ không tự bảo vệ mọi resource.

**Contention quá cao:** đo retry ratio và tail latency; cân nhắc chia state, batching, `LongAdder` khi semantics phù hợp hoặc một chiến lược backoff đã được đo. Không tăng threads để hy vọng “nhanh lên” nếu hotspot đã bão hòa.

## 21. Câu hỏi tự kiểm tra

**1. CAS failure có phải lỗi không?** Không mặc định. Với strong CAS, nó thường chỉ là expected không khớp do state đã thay đổi; thuật toán có thể retry hoặc trả kết quả nghiệp vụ khác.

**2. Sau CAS fail, có thể giữ nguyên expected và chỉ chạy lại `compareAndSet` không?** Không. Phải đọc lại và tính lại state đề xuất; nếu điều kiện không còn đúng, dừng hợp lệ.

**3. `AtomicInteger` có làm `get` rồi `set` thành một transaction không?** Không. Phải dùng operation atomic cho cả logic cần nguyên tử hoặc CAS loop đúng.

**4. Một worker liên tục thua CAS có mâu thuẫn với lock-free không?** Không. Lock-free hướng tới tiến triển tổng thể; wait-free mới đòi guarantee mạnh hơn cho từng operation.

**5. Vì sao không gửi email trong `updateAndGet(x -> ...)`?** Function có thể được gọi nhiều lần nếu CAS nội bộ retry, làm lặp side effect.

**6. `LongAdder` thay `AtomicLong` cho tồn kho được không?** Không nên: `sum()` không atomic snapshot với cập nhật đồng thời, nên không đủ cho check-and-decrement quyết định nghiệp vụ.

**7. `onSpinWait` có bảo đảm nhường CPU hay hẹn giờ không?** Không; chỉ là performance hint. Backoff có chính sách thời gian khác và cũng không tự đảm bảo fairness.

**8. ABA là gì?** State chuyển từ A sang B rồi trở lại A; CAS so expected=A có thể thắng dù lịch sử đã thay đổi. Khi cần version hãy dùng stamp/cấu trúc phù hợp.

**9. CAS loop có tự bảo vệ object mutable nằm trong `AtomicReference` không?** Không. Nó bảo vệ thay reference theo contract; data bên trong có thể cần immutable design/ownership.

**10. Test có output cố định `failedCAS=1` có chứng minh số retry luôn là 1 trong production không?** Không. Đó là interleaving được barrier cố ý dựng; thực tế tùy scheduling và contention.

**11. `compareAndSet` và `weakCompareAndSetPlain` có thể tráo nhau không?** Không tự động: weak CAS có thể fail giả và memory-order semantics có thể khác.

**12. Có cách nào bảo đảm CAS retry luôn kết thúc trong 5 ms không?** Không chỉ bằng primitive. Cần deadline/cancellation semantics, kiểm soát khối lượng công việc và scheduler; timer không làm update đúng tự động.

## 22. Checklist triển khai

1. Xác định **state và invariant**; chỉ dùng CAS nếu một atomic cell/reference có thể diễn đạt điều kiện cần bảo toàn.
2. Dùng API atomic chuẩn trước; đừng tự loop cho `incrementAndGet` nếu không có nhu cầu mới.
3. Trong mỗi retry: **đọc mới → kiểm tra mới → tính mới → CAS**.
4. Giữ update function **thuần**, không đặt I/O hoặc side effects không idempotent trong retry.
5. Phân biệt **CAS success**, condition failure, retry budget exhausted và cancellation.
6. Kiểm tra **overflow**, value/reference identity và **ABA** nếu trạng thái có version/lifetime.
7. Hiểu strong/weak CAS cùng memory-order semantics theo JMM.
8. Không gọi cả thuật toán “lock-free/wait-free” chỉ vì có CAS.
9. Đo throughput, retry ratio, CPU, p95/p99 và starvation khi contention tăng.
10. Cân nhắc backoff, sharding, batching, `LongAdder` hoặc lock/immutable state tùy nhu cầu; chọn bằng số đo.
11. Không suy ra atomicity xuyên DB/HTTP/process từ CAS trong một JVM.
12. Test với thread interleavings có chủ đích và stress test, nhưng lập luận đúng đắn vẫn dựa vào contract Java Memory Model.

**Ghi nhớ:** CAS là **optimistic concurrency**: chỉ cập nhật khi snapshot vẫn hợp lệ. Khi thất bại phải **đọc lại, tính lại và kiểm tra lại điều kiện nghiệp vụ**. CAS giúp tránh mutex cho một số state đơn giản nhưng contention có thể khiến retry tiêu tốn CPU và tăng độ trễ; thiết kế tốt kết hợp atomicity, liveness, memory semantics, pure retry logic và phép đo trên workload thật.