# So sánh với AtomicLong khi cần một giá trị nguyên tử

> **Java 8 — Biến tích lũy.** Bài tập trung vào quyết định dùng `AtomicLong` khi cần **một giá trị đọc/cập nhật nguyên tử**, so với `LongAdder` và `LongAccumulator` khi cần **tích lũy số liệu dưới contention cao**. Các API trình bày đã có từ Java 8 và vẫn còn áp dụng trong Java hiện đại.

## 1. Vì sao cùng là counter nhưng không thay thế được nhau?

Hãy hình dung hai bài toán:

**Bài toán A — đếm metrics:** 100 luồng cùng tăng bộ đếm request. Cứ vài giây dashboard đọc tổng. Mục tiêu là cập nhật nhiều lần với overhead hợp lý; không đòi mỗi lần đọc lúc writer đang chạy phải là một **snapshot tuyến tính hóa đúng tại một thời điểm duy nhất**. `LongAdder` có thể phù hợp.

**Bài toán B — kiểm soát quota:** Chỉ còn 2 lượt đặt chỗ. Mỗi thread cần kiểm tra còn lượt và giảm đi đúng một lượt, để không bao giờ cho phép ba người đặt cùng hai chỗ. Hoặc hệ thống cần cấp **số thứ tự không trùng**. `AtomicLong` có các phép CAS, get-and-increment và conditional update đáp ứng primitive cho một giá trị.

Điều khác biệt cốt lõi:

- `AtomicLong` cung cấp **các thao tác nguyên tử trên một biến `long`**: `get()`, `set()`, `compareAndSet`, `getAndIncrement`, `incrementAndGet`, `getAndSet`, `updateAndGet`.
- `LongAdder` chuyên cộng dồn. Nó có `add`, `increment`, `decrement`, `sum` và `sumThenReset`, nhưng **không có CAS hoặc trả giá trị cũ/mới nguyên tử từ mỗi increment**.
- `LongAccumulator` dùng một **hàm kết hợp** như `Long::max` hoặc `Long::min` thay vì chỉ cộng. `get()` là phép tổng hợp trạng thái, **không phải atomic snapshot** khi có writer.
- Cả ba đều được thiết kế cho concurrency, nhưng không có cùng hợp đồng đọc, cập nhật, tổng hợp và reset.

~~~text
Nhu cầu
  |
  +-- Phải trả ID khác nhau cho mỗi thao tác? ---> AtomicLong
  |
  +-- Check-and-update cùng một biến bằng CAS? ---> AtomicLong
  |
  +-- Đếm nhiều request, đọc tổng định kỳ? ----> LongAdder
  |       (chấp nhận sum không phải atomic snapshot)
  |
  +-- Tính max/min từ nhiều writer? ----------> LongAccumulator
  |
  +-- Cần giao dịch qua nhiều biến/DB? -------> Lock/transaction/
                                               state atomic phù hợp
~~~

**Đừng bắt đầu bằng việc hỏi “class nào nhanh hơn”.** Trước hết phải xác định loại invariant và consistency mà nghiệp vụ cần.

## 2. Bảng đối chiếu đầy đủ

| Tính chất | `AtomicLong` | `LongAdder` | `LongAccumulator` |
| --- | --- | --- | --- |
| Package | `java.util.concurrent.atomic` | Cùng package | Cùng package |
| Giá trị logic | Một biến long | Tổng các phần nội tại | Kết hợp các phần bằng hàm |
| Increment | `incrementAndGet/getAndIncrement` | `increment()` | `accumulate(1)` khi hàm phù hợp |
| Add | `addAndGet/getAndAdd` | `add(long)` | `accumulate(long)` |
| Đọc | `get()` | `sum()` | `get()` |
| Mỗi increment trả số cũ/mới? | **Có** | **Không, void** | **Không, void** |
| CAS | `compareAndSet` | Không | Không |
| Update function | `updateAndGet/getAndUpdate/accumulateAndGet` | Cộng dồn | Hàm tích lũy được cung cấp khi tạo |
| Atomic snapshot khi updates tiếp tục? | `get()` là đọc nguyên tử một biến | `sum()` không phải atomic snapshot | `get()` không phải atomic snapshot |
| Reset và đọc cùng lúc | `getAndSet(0)` nguyên tử | `sumThenReset()` không nguyên tử với updates | `getThenReset()` không nguyên tử với updates |
| Phù hợp sequence ID? | Có, nếu quản lý overflow và persistence | Không | Không |
| Cập nhật nhiều thread vào hot counter | Đúng nhưng contention có thể cao | Thường tăng throughput ở contention cao | Có thể tăng throughput theo hàm |
| Bộ nhớ | Thường gọn | Có thể dùng thêm các ô nội tại | Có thể dùng thêm các ô nội tại |
| Chi phí đọc | Đọc một long | Tổng hợp các ô | Tổng hợp qua hàm |
| Khi nào chọn | Quota, CAS, ID, state nguyên tử | Metrics/counter nhiều writer | Max/min hay phép gộp kết hợp |

Một phép `LongAdder.increment()` vẫn **thread-safe**. “`sum()` không atomic” không có nghĩa bộ đếm cập nhật sai ngẫu nhiên; nó nói rằng reader có thể không nhận một snapshot đồng thời duy nhất của tất cả phần khi writers đang chạy.

## 3. AtomicLong bảo đảm gì?

### 3.1. Một lần increment trả đúng giá trị cũ hoặc mới

~~~java
AtomicLong sequence = new AtomicLong(10);

long old = sequence.getAndIncrement();  // 10
long now = sequence.get();             // 11
long next = sequence.incrementAndGet(); // 12
~~~

Đây là đoạn minh họa Java 8, cần `import java.util.concurrent.atomic.AtomicLong;`.

- `getAndIncrement()` trả **giá trị trước tăng**.
- `incrementAndGet()` trả **giá trị sau tăng**.
- Mỗi lời gọi thực hiện read-modify-write trên một biến theo cơ chế atomic, không phải hai thao tác Java độc lập.

Trong miền chưa overflow, nhiều thread gọi `getAndIncrement()` trên cùng instance sẽ nhận các số không trùng. Dùng nó để cấp ticket trong một JVM là hợp lý. **Không suy ra** thứ tự hoàn tất request/network phải trùng thứ tự các ID.

### 3.2. get, set và lỗi check-then-act

~~~java
AtomicLong total = new AtomicLong();

long snapshot = total.get();
total.set(snapshot + 1);
~~~

Mỗi `get` hoặc `set` riêng có ý nghĩa đúng, nhưng tổ hợp đọc-rồi-ghi **không nguyên tử**. Hai threads cùng đọc 0 có thể đều ghi 1, dù có hai lần cập nhật.

**Cách đúng** cho phép tăng một biến là `incrementAndGet()` hoặc `getAndIncrement()`. `volatile long` với `x++` cũng không biến phép đọc/cộng/ghi thành một thao tác nguyên tử.

### 3.3. getAndSet là atomic exchange

~~~java
AtomicLong window = new AtomicLong();

window.addAndGet(10);
long previous = window.getAndSet(0); // 10
long current = window.get();         // 0
~~~

Một `getAndSet(0)` có điểm hiệu lực nguyên tử trên biến. Khi updates khác xảy ra đồng thời, từng update và swap có thứ tự logic; ta có thể phân ranh giới bucket theo primitive này nếu toàn bộ writers áp dụng hợp đồng phù hợp.

### 3.4. compareAndSet là primitive cho điều kiện và thay đổi

~~~java
AtomicLong quota = new AtomicLong(2);

boolean ok = quota.compareAndSet(2, 1); // true
boolean stale = quota.compareAndSet(2, 0); // false
~~~

`compareAndSet(expected,next)` chỉ thay giá trị nếu nó vẫn bằng expected ở thời điểm CAS. Khi có cạnh tranh, caller có thể đọc lại và retry.

Một quota không được viết kiểu:

~~~java
// PHẢN VÍ DỤ: check và decrement không nguyên tử cùng nhau.
if (quota.get() > 0) {
    quota.decrementAndGet();
}
~~~

Hai threads có thể cùng nhìn quota=1 rồi cùng decrement, xuống -1. Dù `decrementAndGet` riêng lẻ nguyên tử, cả hai dòng không tạo một critical section.

### 3.5. Vòng CAS bảo vệ quota đơn biến

~~~java
static boolean tryReserve(AtomicLong available) {
    while (true) {
        long current = available.get();
        if (current <= 0L) {
            return false;
        }
        if (available.compareAndSet(current, current - 1L)) {
            return true;
        }
    }
}
~~~

Đoạn **phương thức minh họa** này cũng được dùng nguyên trong chương trình runnable.

- Đọc quota.
- Nếu hết, trả false.
- Nếu còn, chỉ giảm khi giá trị chưa bị thread khác thay đổi.
- CAS thua thì đọc lại, không tự giảm lần thứ hai trên dữ liệu stale.

Nó bảo vệ **bất biến của một AtomicLong trong một JVM**. Nếu còn database thanh toán, tài nguyên ngoài process hoặc nhiều counter, cần transaction/idempotency/protocol phù hợp.

### 3.6. updateAndGet và accumulateAndGet

~~~java
AtomicLong value = new AtomicLong(20);

long updated = value.updateAndGet(x -> x + 5); // 25
long max = value.accumulateAndGet(30, Long::max); // 30
long before = value.getAndUpdate(x -> x - 2); // 30
~~~

Những API này có từ Java 8. Nhưng **hàm tính toán có thể được thực thi lại nếu CAS cạnh tranh**. Callback phải **không có side effect**: không gọi API thanh toán, không gửi email, không tăng một counter khác có yêu cầu exactly-once bên trong update function.

~~~java
// PHẢN VÍ DỤ: đây không phải chỗ gửi email exactly-once.
value.updateAndGet(x -> {
    sendEmail();
    return x + 1;
});
~~~

`sendEmail` là tên giả cho side effect, không phải mã độc lập. Nếu CAS retry, callback có thể bị gọi nhiều lần. Tách quyết định cập nhật nguyên tử và side effect bên ngoài, thiết kế idempotency ở boundary.

## 4. LongAdder tối ưu cho trường hợp nào?

### 4.1. Phép cộng dồn dễ dùng

~~~java
LongAdder requests = new LongAdder();

requests.increment();
requests.add(5);
requests.decrement();

long total = requests.sum(); // 5, nếu chỉ có luồng trên.
~~~

`LongAdder.increment()` không trả số tổng cũ hoặc mới. Nó là `void`; không thể dùng như `AtomicLong.getAndIncrement()` để cấp ID hoặc biết số thứ tự của từng lần cập nhật.

### 4.2. Ý tưởng phân tán contention

Khi rất nhiều threads cập nhật một `AtomicLong`, chúng tranh quyền cập nhật một vị trí logic. `LongAdder` có thể phân tán cập nhật trên các ô trạng thái nội tại, rồi tổng hợp chúng lúc `sum()`.

~~~text
AtomicLong                      LongAdder (mô hình khái niệm)
----------                      ---------------------------------
Thread A ----+                  Thread A ---> cell A ----+
Thread B ----+--> one value     Thread B ---> cell B ----+--> sum()
Thread C ----+                  Thread C ---> cell C ----+
Thread D ----+                  Thread D ---> cell D ----+
~~~

Đây là sơ đồ tư duy, **không phải API hứa số lượng hoặc bố trí ô nội tại**. Chi tiết thực thi có thể thay đổi giữa phiên bản JDK.

Ưu điểm thường thấy khi cập nhật nhiều và đọc ít:

- Nhiều writers không nhất thiết tranh nhau trên cùng một vùng cập nhật.
- Tốc độ cập nhật ở contention cao có thể tốt hơn AtomicLong.
- Hợp lý cho metrics như request count, retry count, cache hit count.

Đánh đổi:

- Nhiều ô có thể cần **nhiều bộ nhớ** hơn.
- `sum()` phải gộp nhiều phần, có thể đắt hơn một `get()`.
- Không có CAS, atomic get-and-increment hay atomic swap tổng.
- Với ít writers hoặc đọc liên tục, AtomicLong có thể tốt hơn. **Benchmark đúng workload** trước khi kết luận hiệu năng.

### 4.3. sum() không phải snapshot nguyên tử khi đồng thời cập nhật

~~~java
LongAdder adder = new LongAdder();

// Nhiều thread gọi adder.increment().
// Thread đọc thỉnh thoảng gọi:
long observed = adder.sum();
~~~

Javadoc nói `sum()` **không phải atomic snapshot**. Các update xảy ra đồng thời với việc tổng hợp có thể không được phản ánh trong phép đọc. Không có cam kết rằng `observed` là một giá trị đại diện cho một điểm linearization duy nhất của mọi ô.

**Điều được bảo đảm trong thiết kế kiểm thử:** khi **đã chờ toàn bộ writers kết thúc**, và không còn nguồn khác cập nhật, `sum()` phản ánh tổng đã tích lũy. Chương trình ở mục 13 kiểm tra chính xác đặc tính đó.

### 4.4. Không dùng sum+increment để cấp mã ID

~~~java
// PHẢN VÍ DỤ: hai thread có thể cùng nhận một "id".
long id = adder.sum();
adder.increment();
~~~

Vừa không có atomic snapshot, vừa không có check-and-update nguyên tử. Đúng primitive để cấp sequence là `AtomicLong.getAndIncrement()` nếu hệ thống còn quản lý overflow/persistence.

### 4.5. Không dùng sum làm quota cứng

~~~java
// PHẢN VÍ DỤ: check + increment không nguyên tử.
if (activeCount.sum() < LIMIT) {
    activeCount.increment();
    beginWork();
}
~~~

Đây là minh họa với `activeCount`, `LIMIT` và `beginWork()` do ứng dụng cung cấp. Hai threads có thể cùng vượt qua điều kiện khi chỉ còn một slot; LongAdder không có CAS để gắn điều kiện với thay đổi. Dùng AtomicLong CAS, semaphore hoặc transaction tùy invariant.

### 4.6. longValue không tạo ra atomic read

`LongAdder` mở rộng `Number`. `longValue()` trả tổng tương đương `sum()`; không mạnh hơn về atomicity. `intValue()` còn có thể thu hẹp số 64-bit xuống 32-bit và mất các bit cao. Với counters lớn, giữ kiểu `long` khi báo cáo.

## 5. reset và sumThenReset: khác biệt rất quan trọng

### 5.1. AtomicLong.getAndSet(0) là một phép trao đổi nguyên tử

~~~java
AtomicLong counter = new AtomicLong();
counter.addAndGet(10);

long finishedWindow = counter.getAndSet(0); // 10
~~~

Khi writers khác đang cập nhật cùng AtomicLong bằng các atomic operations, thao tác swap và từng update có thứ tự logic, cho phép định nghĩa boundary rõ trên **một biến**.

### 5.2. LongAdder.sumThenReset không tương đương

~~~java
LongAdder counter = new LongAdder();
counter.add(10);

long finishedWindow = counter.sumThenReset(); // 10 khi không có writer.
long newWindow = counter.sum(); // 0
~~~

Theo Javadoc, `sumThenReset()` **không nguyên tử với updates concurrent**. `reset()` cũng chỉ thích hợp khi biết không có threads nào đang update. Nếu vẫn có writer, không nên hứa mỗi sự kiện chắc chắn rơi vào đúng một bucket.

`sumThenReset()` có thể là lựa chọn rất tốt nếu có giai đoạn ngừng cập nhật thật sự hoặc một barrier đảm bảo không còn writer cũ. Vấn đề không phải method luôn gây mất số liệu, mà là **không có giao dịch đọc-reset nguyên tử dưới concurrent writes**.

### 5.3. Thay reference chưa chắc đã tách được hai cửa sổ

~~~java
AtomicReference<LongAdder> current =
        new AtomicReference<>(new LongAdder());

LongAdder previous = current.getAndSet(new LongAdder());
long count = previous.sum();
~~~

Đây là **một phản ví dụ về giả định quá mạnh**. Atomic swap của reference không ngăn một worker đã lấy reference cũ trước swap tiếp tục gọi `previous.increment()` **sau khi `previous.sum()` được đọc**. Muốn bucket chính xác cần thêm cơ chế phối hợp với writers hoặc ownership theo epoch.

### 5.4. Trường hợp lựa chọn thực tế

| Mục tiêu | Lựa chọn |
| --- | --- |
| Scrape counter metrics đang chạy | `LongAdder.sum()` nếu chấp nhận không snapshot |
| Đếm batch rồi kiểm tra sau khi writers dừng | `LongAdder` hoặc `AtomicLong` đều có thể |
| Số sự kiện theo cửa sổ phải chính xác dù writers đồng thời | Atomic swap hoặc cơ chế epoch/barrier được thiết kế đúng |
| Ghi nhận tổng tăng trong cùng thread | Không cần tối ưu contention; AtomicLong đơn giản hoặc `long` dưới synchronization phù hợp |
| Chỉ một worker update rồi nhiều reader cần atomic get | `AtomicLong` có ngữ nghĩa trực tiếp |

## 6. LongAccumulator và khi nào cần một hàm kết hợp

`LongAccumulator` tổng quát hóa việc tích lũy: thay vì luôn cộng, caller cung cấp một `LongBinaryOperator` và một giá trị identity.

~~~java
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);

maximum.accumulate(-9);
maximum.accumulate(4);
maximum.accumulate(2);

long max = maximum.get(); // 4 khi không có writers khác.
~~~

### 6.1. Chọn identity đúng

Với max, identity là `Long.MIN_VALUE` vì:

~~~text
max(x, Long.MIN_VALUE) = x
~~~

Với min, thường chọn `Long.MAX_VALUE`:

~~~java
LongAccumulator minimum =
        new LongAccumulator(Long::min, Long.MAX_VALUE);

minimum.accumulate(10);
minimum.accumulate(3);
minimum.accumulate(9);

// minimum.get() == 3 khi không có writer khác.
~~~

**Phản ví dụ:** chọn identity 0 cho min của các số đều dương có thể khiến kết quả vẫn là 0, không phải min của inputs.

### 6.2. Associative và side-effect-free

Hàm accumulation nên **associative**, tức thay đổi cách nhóm không đổi kết quả. Hàm cũng phải **không có side effect**, vì LongAccumulator có thể gọi nó trong cách cập nhật nội tại không nên bị coi là exactly-once callback.

Phù hợp: `Long::max`, `Long::min`, phép cộng trong miền long theo hợp đồng. Không phù hợp nếu cần kết quả cố định bất kể cách nhóm: phép trừ `(a,b) -> a-b`.

~~~java
// PHẢN VÍ DỤ vì phép trừ không associative:
LongAccumulator wrong =
        new LongAccumulator((a, b) -> a - b, 0);
~~~

Trong hệ thống nhiều threads, không dựa vào **thứ tự input** để định nghĩa business state bằng một accumulator phân tán. Hàm còn nên **commutative** khi thứ tự giữa các writers không phải một phần contract, như max/min.

### 6.3. get() và getThenReset vẫn không phải atomic snapshot

`LongAccumulator.get()` phải tổng hợp các phần; không có bảo đảm giống `AtomicLong.get()` khi cập nhật đồng thời. `getThenReset()` và `reset()` không atomic với các writers. Nếu cần “max đã thấy” để **quyết định nguyên tử ngay lập tức**, có thể dùng `AtomicLong.accumulateAndGet(candidate, Long::max)` trên một state.

### 6.4. Identity khác trạng thái có input

Một accumulator max mới tạo có `get()==Long.MIN_VALUE`. Điều đó không phân biệt được “chưa có số nào” với “đã nhận đúng input Long.MIN_VALUE”. Nếu phân biệt quan trọng, dùng thêm trạng thái hoặc một result model có cờ presence; nhớ rằng hai biến nguyên tử riêng cũng không tự tạo snapshot nhất quán chung.

### 6.5. Khi chỉ cần cộng hãy cân nhắc LongAdder

Có thể tạo `LongAccumulator(Long::sum,0)` nhưng `LongAdder` có API `increment/add/sum` rõ hơn cho cộng dồn. Chỉ chọn LongAccumulator khi hàm gộp như max/min là trọng tâm, hoặc khi thiết kế cần một hàm kết hợp đã được xác minh đầy đủ.

## 7. DoubleAdder và DoubleAccumulator: sai số dấu phẩy động

Java 8 còn có:

~~~java
DoubleAdder total = new DoubleAdder();
total.add(0.5);
total.add(1.25);

// total.sum() == 1.75 trong ví dụ.
~~~

Và:

~~~java
DoubleAccumulator minimum =
        new DoubleAccumulator(Double::min,
                Double.POSITIVE_INFINITY);

minimum.accumulate(4.5);
minimum.accumulate(-2.0);

// minimum.get() == -2.0 khi không concurrent writes.
~~~

Tuy nhiên, số học `double` trong Java tuân floating point và có **rounding**. Phép cộng double không associative tuyệt đối:

~~~text
(1e16 + (-1e16)) + 1  có thể bằng 1
1e16 + ((-1e16) + 1) có thể bằng 0
~~~

Vì các phần tích lũy có thể gộp theo thứ tự khác nhau, `DoubleAdder.sum()` có thể khác bit thấp so với vòng cộng tuần tự với thứ tự cố định.

**Không dùng DoubleAdder mặc định cho tiền cần độ chính xác tuyệt đối.** Cân nhắc số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` với concurrency/transaction phù hợp. Ngoài ra phải xác định chính sách với `NaN`, `Infinity`, `-0.0` khi dùng DoubleAccumulator.

## 8. Memory model, visibility và linearizability

### 8.1. Một AtomicLong là một state nguyên tử

`AtomicLong.get()` là phép đọc giá trị được bảo vệ theo memory semantics tương ứng, còn `compareAndSet` và các phép update thực hiện read-modify-write trên state đó. Trong concurrency, ta có thể đặt các thao tác này vào một thứ tự hiệu lực hợp lệ, chứ không phải suy ra từ thứ tự log của threads.

### 8.2. Thread-safe update khác atomic aggregate

`LongAdder.add()` và `LongAccumulator.accumulate()` được thiết kế thread-safe. Nhưng `LongAdder.sum()` và `LongAccumulator.get()` đọc tổng hợp từ nhiều phần, không hứa atomic snapshot. Cùng một object có thể có **operations bảo đảm khác nhau**.

### 8.3. Một lock chỉ ở reader không giúp nếu writers không theo

~~~java
// Không đủ nếu writers không synchronized trên cùng lock:
synchronized (lock) {
    observed = adder.sum();
}
~~~

Đoạn minh họa với `lock` và `observed` do caller cung cấp. Nếu writers không tham gia lock, chúng vẫn có thể update trong khi sum đang chạy; đừng kỳ vọng synchronized ở reader tự thay đổi hợp đồng LongAdder.

### 8.4. Chờ writer hoàn thành rồi sum

~~~java
for (Future<?> writerTask : tasks) {
    writerTask.get();
}

long finalCount = adder.sum();
~~~

Đây là **đoạn minh họa** trong trường hợp `tasks` chứa toàn bộ writer tasks và không còn nguồn cập nhật khác. `Future.get()` còn là một completion/visibility boundary; sau khi tasks kết thúc, đọc tổng đúng với những updates đã thực hiện trong giai đoạn đó.

Không dùng `Thread.sleep(100)` để kết luận writers đã xong. Sleep không phải completion barrier.

## 9. Quota, ticket ID và invariant cứng

### 9.1. Ticket ID

~~~java
AtomicLong nextId = new AtomicLong(0);
long id = nextId.getAndIncrement();
~~~

Mỗi thread nhận một giá trị riêng từ cùng object trước khi overflow. Nhưng nếu hai JVM cùng tạo AtomicLong(0), các IDs vẫn có thể trùng; nếu process restart, counter cũng có thể trở về seed. Cần scheme phân tán/persistent nếu uniqueness vượt một vòng đời JVM.

### 9.2. Quota cứng

`AtomicLong` CAS loop phù hợp với quota nằm trong một state. Với nhiều quy tắc đồng thời như “số vé còn lại, số vé đã bán, số tiền đã nhận” nằm trong nhiều object, CAS trên một biến **không** tự tạo transaction toàn bộ.

Có thể xem xét `AtomicReference<ImmutableState>` cập nhật bằng CAS, `synchronized`, `ReentrantLock`, semaphore, hoặc transaction DB tùy bài toán.

### 9.3. Side effect xảy ra ngoài AtomicLong

Giả sử CAS giảm quota thành công, sau đó network request gửi đơn hàng bị lỗi. AtomicLong không tự rollback DB/request. Ngược lại, một retry có thể gửi trùng side effect nếu không có idempotency key. **Atomicity của một biến không phải exactly-once processing toàn hệ thống.**

### 9.4. Multi-variable snapshot

Hai `AtomicLong` riêng có thể được đọc ở **hai thời điểm khác nhau**. Nếu một thread tăng A rồi tăng B, reader có thể thấy A đã tăng nhưng B chưa. Mỗi lần `get()` là nguyên tử nhưng **cả cặp không phải snapshot chung**.

Cũng vậy, đọc nhiều `LongAdder.sum()` trong một ConcurrentHashMap không tự tạo snapshot chính xác của toàn bộ map tại một thời điểm.

## 10. Đếm theo key với ConcurrentHashMap

Pattern Java 8 thường gặp:

~~~java
ConcurrentHashMap<String, LongAdder> hits =
        new ConcurrentHashMap<>();

hits.computeIfAbsent("api/login", key -> new LongAdder())
        .increment();

hits.computeIfAbsent("api/login", key -> new LongAdder())
        .increment();

long count = hits.get("api/login").sum();
// 2 nếu không có writer cạnh tranh.
~~~

`ConcurrentHashMap.computeIfAbsent` giúp tạo counter cho key theo concurrency contract của map; `LongAdder` nhận updates từ nhiều threads.

### 10.1. Điều không được tự giả định

- Map có thread-safe operations **không có nghĩa** đi qua toàn bộ map lấy sum là snapshot atomic.
- Nếu thread giữ reference tới một LongAdder cũ, rồi thread khác `remove/replace` entry, writer vẫn có thể tăng object đã bị loại khỏi map.
- Nếu cần reset đúng từng cửa sổ, không chỉ đổi LongAdder trong map mà không phối hợp với writers.
- Nếu mỗi key cần CAS/threshold thay vì chỉ metrics, có thể dùng `ConcurrentHashMap<K,AtomicLong>` với hợp đồng thích hợp.

### 10.2. Pattern metrics không phải transaction

Bộ đếm số request/HTTP status hoặc cache hits theo key thường chấp nhận snapshot quan sát trong lúc chạy. Nhưng billing, số tồn kho hay audit event counts tuyệt đối cần bảo đảm cấp nghiệp vụ mạnh hơn.

## 11. Hiệu năng: khi nào LongAdder thắng, khi nào không?

### 11.1. Contention quyết định rất nhiều

Nếu chỉ một writer tăng counter, một AtomicLong có thể rất rẻ. Nếu nhiều writers cùng cập nhật một hot counter, LongAdder có thể phân tán contention nên throughput tốt hơn.

Nhưng đánh đổi có thật:

- LongAdder có thể tốn thêm bộ nhớ cho nhiều phần.
- Đọc sum thường đắt hơn atomic get.
- Tần suất đọc quá cao có thể giảm lợi ích.
- Với hàng triệu counters ít được dùng, overhead memory của LongAdder cần được đo.
- Với một cờ/quota/state cần điều kiện CAS, dù LongAdder nhanh hơn thì **sai primitive**.

Không khẳng định một con số tăng tốc phổ quát. JDK, CPU, scheduler, số writer, tỷ lệ read/write và workload thực đều ảnh hưởng.

### 11.2. Benchmark đúng cách

Nên dùng JMH hoặc harness benchmark chuẩn; thực hiện warmup, tránh dead-code elimination, kiểm tra allocation, memory, throughput và latency. Chạy cùng số threads, cùng khối lượng work và đo riêng workload chỉ-update so với workload update + sum.

Một vòng for trong `main` tính thời gian bằng `currentTimeMillis` không đủ để kết luận hiệu suất concurrency.

### 11.3. Correctness quan trọng hơn benchmark

Trình tự chọn: semantics → invariant → implementation → concurrent unit tests → đo hiệu năng → điều chỉnh. Nếu mục tiêu cần CAS, không thể thay bằng LongAdder chỉ vì benchmark đẹp.

## 12. Java 8 runnable: AtomicLong, LongAdder, LongAccumulator và đa luồng

Lưu mã sau thành **AccumulatorVsAtomicDemo.java**. Chương trình chứa một demo bốn writers cùng cập nhật, dùng `CountDownLatch` tạo cổng bắt đầu và `Future.get` bảo đảm đã dừng cập nhật trước khi đọc final sum. Nó đồng thời kiểm chứng CAS quota, uniqueness của các ticket, và các hàm reset trong trạng thái không có writer.

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class AccumulatorVsAtomicDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    private static boolean tryReserve(AtomicLong available) {
        while (true) {
            long current = available.get();
            if (current <= 0L) {
                return false;
            }
            if (available.compareAndSet(current, current - 1L)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicLong single = new AtomicLong(10);
        System.out.println("getAndIncrement returns = "
                + single.getAndIncrement());
        System.out.println("after increment = " + single.get());
        System.out.println("CAS 11 to 20 = "
                + single.compareAndSet(11, 20));
        System.out.println("CAS 11 to 30 = "
                + single.compareAndSet(11, 30));
        System.out.println("updateAndGet +5 = "
                + single.updateAndGet(x -> x + 5));

        LongAdder sequentialAdder = new LongAdder();
        sequentialAdder.add(10);
        sequentialAdder.increment();
        sequentialAdder.decrement();
        System.out.println("adder sum = " + sequentialAdder.sum());
        System.out.println("adder sumThenReset = "
                + sequentialAdder.sumThenReset());
        System.out.println("adder after reset = "
                + sequentialAdder.sum());

        LongAccumulator maxValue =
                new LongAccumulator(Long::max, Long.MIN_VALUE);
        maxValue.accumulate(-9);
        maxValue.accumulate(4);
        maxValue.accumulate(2);
        System.out.println("accumulator max = " + maxValue.get());
        System.out.println("accumulator getThenReset = "
                + maxValue.getThenReset());
        System.out.println("accumulator identity = "
                + maxValue.get());

        DoubleAdder doubles = new DoubleAdder();
        doubles.add(0.5);
        doubles.add(1.25);
        System.out.println("double sum = " + doubles.sum());

        final int workers = 4;
        final int perWorker = 5000;
        AtomicLong exactCount = new AtomicLong();
        LongAdder highContentionCount = new LongAdder();
        LongAccumulator maxSeen =
                new LongAccumulator(Long::max, Long.MIN_VALUE);
        AtomicLong ticketSequence = new AtomicLong();
        Set<Long> uniqueTickets = ConcurrentHashMap.newKeySet();
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();
        try {
            for (int worker = 0; worker < workers; worker++) {
                final int workerId = worker;
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    await(start);
                    for (int i = 0; i < perWorker; i++) {
                        exactCount.incrementAndGet();
                        highContentionCount.increment();
                        maxSeen.accumulate(workerId * perWorker + i);
                        uniqueTickets.add(ticketSequence.getAndIncrement());
                    }
                }));
            }
            await(ready);
            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
        System.out.println("atomic final count = " + exactCount.get());
        System.out.println("adder final count = "
                + highContentionCount.sum());
        System.out.println("max accumulated value = " + maxSeen.get());
        System.out.println("all tickets unique = "
                + (uniqueTickets.size() == workers * perWorker));
        System.out.println("ticket sequence count = "
                + ticketSequence.get());
        System.out.println("post-quiescence sumThenReset = "
                + highContentionCount.sumThenReset());
        System.out.println("post-quiescence next window = "
                + highContentionCount.sum());

        AtomicLong inventory = new AtomicLong(2);
        System.out.println("reserve first = " + tryReserve(inventory));
        System.out.println("reserve second = " + tryReserve(inventory));
        System.out.println("reserve third = " + tryReserve(inventory));
        System.out.println("inventory remaining = " + inventory.get());

        AtomicLong wrap = new AtomicLong(Long.MAX_VALUE);
        System.out.println("overflow wraps = "
                + (wrap.incrementAndGet() == Long.MIN_VALUE));
    }
}
~~~

Biên dịch với JDK hỗ trợ target Java 8:

~~~bash
javac --release 8 AccumulatorVsAtomicDemo.java
java AccumulatorVsAtomicDemo
~~~

**Stdout đã xác minh thực tế:**

~~~text
getAndIncrement returns = 10
after increment = 11
CAS 11 to 20 = true
CAS 11 to 30 = false
updateAndGet +5 = 25
adder sum = 10
adder sumThenReset = 10
adder after reset = 0
accumulator max = 4
accumulator getThenReset = 4
accumulator identity = -9223372036854775808
double sum = 1.75
atomic final count = 20000
adder final count = 20000
max accumulated value = 19999
all tickets unique = true
ticket sequence count = 20000
post-quiescence sumThenReset = 20000
post-quiescence next window = 0
reserve first = true
reserve second = true
reserve third = false
inventory remaining = 0
overflow wraps = true
~~~

### 12.1. Phần đầu: AtomicLong

`getAndIncrement` trả số cũ 10, sau đó `get` là 11. `compareAndSet(11,20)` thắng; `compareAndSet(11,30)` thất bại vì state đã thành 20. `updateAndGet(x -> x+5)` cho 25.

### 12.2. LongAdder và LongAccumulator không bị biến thành giá trị nguyên tử chỉ vì test pass

Ở chương trình đơn luồng, LongAdder 10 + 1 - 1 = 10. `sumThenReset` trả 10 và tổng tiếp theo 0. LongAccumulator với hàm max trả 4 rồi reset về identity `Long.MIN_VALUE`.

Phần đa luồng có **4*5000=20000** increments. Sau khi `Future.get()` xác nhận writers xong:

- `AtomicLong.get()` = 20000.
- `LongAdder.sum()` = 20000.
- `LongAccumulator(Long::max)` trả 19999 vì input là các số từ 0 tới 19999.
- `AtomicLong.getAndIncrement()` tạo 20000 ticket không trùng, được xác minh bằng một concurrent set.
- `sumThenReset()` sau khi mọi writer dừng trả 20000, rồi sum tiếp theo 0.

Đây không phải bằng chứng `sum()` có snapshot nguyên tử trong lúc chạy; mọi phép đọc chính của demo xảy ra **sau barrier**.

### 12.3. Quota và overflow

Khi inventory=2, ba lần reserve theo CAS cho `true, true, false` và state còn 0. Điều này không yêu cầu thread nào được chạy trước trong chương trình demo; nếu gọi nhiều thread, CAS loop vẫn bảo vệ điều kiện đơn biến.

Phép `incrementAndGet()` trên `Long.MAX_VALUE` wrap thành `Long.MIN_VALUE` vì số học long 64-bit. Không dùng một AtomicLong tăng vô hạn làm ID scheme mà thiếu overflow/restart policy.

### 12.4. Đây là kiểm thử correctness, không phải benchmark

Chương trình còn dùng concurrent set để xác nhận uniqueness. Overhead của set khiến phép đo elapsed time không có ý nghĩa so sánh hiệu năng của AtomicLong/LongAdder. Khi cần đánh giá performance, thiết kế benchmark riêng.

## 13. Overflow, dấu âm và reset

### 13.1. Long có miền hữu hạn

`AtomicLong`, `LongAdder` và `LongAccumulator` hoạt động trên số `long` 64-bit, không tự nâng cấp lên `BigInteger`. Khi phép cộng vượt giới hạn, arithmetic long có thể wrap. Phép cập nhật nguyên tử không đồng nghĩa phát hiện overflow.

### 13.2. LongAdder cho phép số âm

~~~java
LongAdder delta = new LongAdder();
delta.add(10);
delta.add(-4);
// delta.sum() == 6 khi không writer khác.
~~~

LongAdder không bắt buộc chỉ tăng. Nhưng nếu trạng thái phải “không âm tại mọi thời điểm”, LongAdder không có primitive CAS phù hợp để chặn update vượt giới hạn.

### 13.3. Counter zero không nói có hay chưa có input

Một LongAdder mới tạo có sum=0. Một LongAdder đã nhận +1 và -1 cũng có sum=0. Nếu nghiệp vụ cần biết **đã từng có record hay chưa**, phải có model presence/history riêng.

Với LongAccumulator(max), identity Long.MIN_VALUE không phân biệt được “chưa có input” với một input đúng Long.MIN_VALUE. Khi cần phân biệt, thiết kế state riêng và xem xét atomicity chung.

### 13.4. Reset cần quiescence thật

Không gọi reset trên LongAdder đang có writers nếu business kỳ vọng không mất/misclassify update. Dùng completion barrier, lifecycle quản lý writers hoặc primitive cho atomic window.

## 14. Hai mươi lỗi phổ biến

### Lỗi 1. LongAdder cấp ID bằng sum rồi increment

Không có atomic check-and-increment. Nhiều threads có thể nhận cùng số. **Dùng AtomicLong.getAndIncrement()**.

### Lỗi 2. LongAdder làm quota cứng

`sum()<limit` rồi `increment` không là một transaction. **Dùng CAS, semaphore hoặc transaction**.

### Lỗi 3. Nghĩ LongAdder.sum() nguyên tử

Không có atomic snapshot giữa nhiều ô khi writers đang chạy. **Định nghĩa metrics consistency đúng**.

### Lỗi 4. Nghĩ LongAdder cập nhật không an toàn

Sai. Update có concurrency design phù hợp; đọc tổng có bảo đảm khác. **Tách thread-safe update và snapshot consistency**.

### Lỗi 5. Viết AtomicLong.get()+set() cho increment

Một phép đọc và một phép ghi riêng không bảo đảm read-modify-write. **Dùng incrementAndGet**.

### Lỗi 6. Viết volatile long x++ thay AtomicLong

Volatile không tự làm phép cộng nguyên tử. **Dùng AtomicLong hoặc lock phù hợp**.

### Lỗi 7. Dùng sumThenReset dưới tải concurrent

Không bảo đảm mỗi event thuộc đúng một kỳ. **Dùng barrier/epoch hợp lệ hoặc atomic exchange**.

### Lỗi 8. Tin swap LongAdder reference đã đóng cửa sổ

Writer cũ có thể giữ reference cũ. **Quản lý ownership của writer**.

### Lỗi 9. Nghĩ LongAccumulator.get() là atomic getter

Nó tổng hợp nhiều phần. **Chọn AtomicLong nếu cần read state nguyên tử**.

### Lỗi 10. Hàm accumulator không associative

Phép trừ có kết quả phụ thuộc cách nhóm. **Chọn phép kết hợp hợp lý như min/max**.

### Lỗi 11. Identity sai

Min với identity=0 khi dữ liệu dương có thể luôn trả 0. **Dùng Long.MAX_VALUE cho min**.

### Lỗi 12. Side effect trong hàm CAS/accumulator

Các function có thể được thực thi lại hoặc phối hợp theo runtime. **Giữ function pure**.

### Lỗi 13. DoubleAdder cho tiền chính xác

Floating point có sai số. **Dùng integer đơn vị nhỏ nhất hoặc BigDecimal**.

### Lỗi 14. Tin DoubleAdder luôn cộng ra cùng bit với thứ tự tuần tự

Grouping thay đổi rounding. **Xác định tolerance hoặc thuật toán deterministic**.

### Lỗi 15. Giả định LongAdder luôn nhanh hơn AtomicLong

Không đúng với mọi workload. **Benchmark theo tỷ lệ read/write/contenders/memory thực**.

### Lỗi 16. Dùng AtomicLong khi cần transaction nhiều biến

Một biến atomic không bảo vệ invariant của hai biến. **Dùng state nguyên tử chung, lock hoặc DB transaction**.

### Lỗi 17. Nhầm CAS với exactly-once I/O

Network, DB hoặc email không rollback tự động. **Idempotency/transaction là vấn đề riêng**.

### Lỗi 18. Dùng Thread.sleep để đợi writers

Không có bảo đảm hoàn thành. **Dùng Future.get hoặc synchronization barrier**.

### Lỗi 19. Đọc sum khi writer còn chạy rồi assert đúng tổng cuối

Đọc trước completion có thể thiếu updates. **Test sau khi mọi writer hoàn thành**.

### Lỗi 20. Quên overflow/restart của AtomicLong sequence

AtomicLong không bảo đảm ID duy nhất xuyên JVM/restart hay khi wrap. **Thiết kế ID scheme theo phạm vi hệ thống**.

### Lỗi 21. Nghĩ ConcurrentHashMap có snapshot toàn map

Map và các counter vẫn có thể đổi trong lúc reader đi qua. **Dùng protocol snapshot nếu yêu cầu tuyệt đối**.

### Lỗi 22. Remove counter trong map mà không quản lý reference cũ

Writer đang giữ object cũ có thể tăng sau remove. **Thiết kế lifecycle của bucket và writers**.

### Lỗi 23. Nhầm LongAdder.longValue() với AtomicLong.get()

LongAdder.longValue vẫn dựa trên sum. **Không xem Number conversion là bảo đảm mới**.

### Lỗi 24. Bỏ qua memory của rất nhiều LongAdder

Nhiều ô nội tại khi contention có thể tăng footprint. **Đo allocation và memory**.

## 15. Checklist lựa chọn

| Câu hỏi | Tác động tới lựa chọn |
| --- | --- |
| Mỗi update cần trả giá trị cũ/mới? | `AtomicLong` |
| Cần CAS/threshold để quyết định? | `AtomicLong` |
| Chủ yếu tăng counter từ nhiều writers? | Cân nhắc `LongAdder` |
| Đọc tổng ít và không cần snapshot nguyên tử? | `LongAdder` thường phù hợp |
| Cần max/min thay vì tổng? | `LongAccumulator` nếu hợp đồng cho phép |
| Phép tích lũy associative và side-effect-free? | Bắt buộc xem xét cho accumulator |
| Cần reset chính xác khi writers đang chạy? | `AtomicLong.getAndSet` hoặc protocol bucket |
| Cần tổng chính xác sau batch? | Chờ writers rồi `LongAdder.sum()` |
| Dữ liệu là số tiền? | Không mặc định DoubleAdder |
| Counter nhiều key? | Cân nhắc `ConcurrentHashMap<K,LongAdder>` |
| Snapshot gồm nhiều fields? | State atomic chung/lock/transaction |
| Chạy trên nhiều JVM? | Local atomics không đủ cho uniqueness toàn hệ thống |
| Gần long overflow? | Chính sách miền giá trị |
| Throughput đã đo thực tế? | Benchmark sau khi chọn semantics đúng |

### 15.1. Bộ test concurrency nên có

1. Nhiều threads tăng AtomicLong cùng object, kiểm tra final count.
2. Nhiều threads lấy ticket bằng getAndIncrement, kiểm tra không trùng.
3. CAS loop quota với nhiều contenders, kiểm tra không cấp quá số permits.
4. Nhiều threads tăng LongAdder, **chờ kết thúc**, kiểm tra sum.
5. `LongAdder.sum()` trong lúc writers chạy: **không** assert nó tương đương một atomic snapshot.
6. `sumThenReset()` chỉ sau khi quiescence, kiểm tra next window bằng 0.
7. LongAccumulator(max) nhận dữ liệu theo nhiều threads, kiểm tra max cuối.
8. LongAccumulator identity đúng trước khi có input.
9. Kiểm tra overflow Long.MAX_VALUE.
10. Xác nhận không còn writer sau khi xóa/đổi counter trong map.
11. Với DoubleAdder, test chính sách rounding/tolerance trên dữ liệu lớn và nhỏ.
12. Với transaction nhiều biến, kiểm tra atomicity ở đúng tầng dữ liệu.

## 16. Bài tập tự kiểm tra và đáp án

**Câu 1.** Tại sao `LongAdder` không phải lựa chọn tốt để cấp số thứ tự?

**Đáp án:** Vì `increment()` trả void, `sum()` không là atomic snapshot và cặp `sum()+increment()` không atomic; `AtomicLong.getAndIncrement()` có thể cấp giá trị cũ nguyên tử.

**Câu 2.** Nhiều threads cùng tăng một metrics counter nhưng chỉ đọc vài giây một lần, nên cân nhắc gì?

**Đáp án:** `LongAdder`, nếu yêu cầu chấp nhận `sum()` không là snapshot nguyên tử khi updates đang diễn ra.

**Câu 3.** `AtomicLong.get()` khác `LongAdder.sum()` ở đâu?

**Đáp án:** `get()` đọc một state nguyên tử, còn `sum()` tổng hợp nhiều phần và không đảm bảo snapshot nguyên tử khi concurrent writes.

**Câu 4.** `LongAdder.increment()` có trả tổng sau khi tăng không?

**Đáp án:** Không. Nó trả void.

**Câu 5.** Vì sao `get()+set(get()+1)` không an toàn?

**Đáp án:** Hai bước đọc và ghi có thể bị thread khác xen giữa và gây lost update.

**Câu 6.** Khi cần CAS kiểm tra quota >0 và giảm 1, dùng gì?

**Đáp án:** `AtomicLong.compareAndSet` trong loop, hoặc công cụ đồng bộ/transaction thích hợp.

**Câu 7.** `LongAdder.sumThenReset()` có bảo đảm atomic với writers không?

**Đáp án:** Không. Cần dừng writers hoặc dùng thiết kế khác nếu cần phân kỳ chính xác.

**Câu 8.** `AtomicLong.getAndSet(0)` có khác `sumThenReset()` không?

**Đáp án:** Có, nó là atomic exchange trên một AtomicLong.

**Câu 9.** `LongAccumulator(Long::max,Long.MIN_VALUE)` ban đầu trả gì?

**Đáp án:** `Long.MIN_VALUE`, identity của max.

**Câu 10.** Có nên dùng `LongAccumulator((a,b)->a-b,0)` làm bộ trừ song song deterministic?

**Đáp án:** Không. Phép trừ không associative.

**Câu 11.** LongAccumulator.get có snapshot nguyên tử không?

**Đáp án:** Không khi các threads vẫn accumulate.

**Câu 12.** Vì sao DoubleAdder không mặc định dùng cho tiền?

**Đáp án:** Floating point rounding làm số tiền có thể lệch chính xác; chọn integer smallest units/BigDecimal với concurrency contract.

**Câu 13.** Sau khi toàn bộ writer tasks kết thúc, LongAdder.sum có thể bằng tổng increments đã thực hiện không?

**Đáp án:** Có, nếu không còn writers nào khác và xét arithmetic long.

**Câu 14.** Thread nào được cấp ID nhỏ hơn có chắc hoàn thành trước không?

**Đáp án:** Không. AtomicLong chỉ cấp số thứ tự tại điểm increment, còn thứ tự công việc/I/O có thể khác.

**Câu 15.** Hai AtomicLong có tạo transaction chung không?

**Đáp án:** Không; cần một state atomic chung/lock/transaction khi invariant bắc qua nhiều biến.

**Câu 16.** AtomicLong có tự chống overflow không?

**Đáp án:** Không; cập nhật long có thể wrap tại giới hạn 64-bit.

**Câu 17.** Dùng ConcurrentHashMap<K,LongAdder> có giúp đếm theo key không?

**Đáp án:** Có. `computeIfAbsent` và `increment` là pattern Java 8, nhưng snapshot/reset/removal cần lifecycle rõ.

**Câu 18.** Vì sao AtomicReference.getAndSet(new LongAdder) chưa đủ đóng bucket?

**Đáp án:** Vì writer đã giữ reference cũ có thể tăng tiếp sau khi swap; phải phối hợp với writers.

## 17. Tổng kết

- **`AtomicLong` dành cho một biến có thao tác nguyên tử**: CAS, cập nhật có điều kiện, get-and-increment, get-and-set và cấp sequence local.
- **`LongAdder` chuyên cộng dồn có nhiều writer**, thường tăng throughput ở contention cao; `sum()` không phải atomic snapshot lúc updates đang chạy.
- **`sumThenReset()` không tương đương `AtomicLong.getAndSet(0)`** khi có concurrent updates. Dùng LongAdder reset khi đã đảm bảo writers ngừng hoặc có protocol phối hợp.
- **`LongAccumulator` hỗ trợ max/min và hàm kết hợp associative/side-effect-free**, nhưng `get()` cũng không atomic snapshot khi writers đang hoạt động.
- **`DoubleAdder` và `DoubleAccumulator` không bảo đảm tổng dấu phẩy động độc lập thứ tự**, không mặc định phù hợp dữ liệu tiền chính xác.
- **Atomicity không tự trở thành transaction xuyên nhiều biến, JVM hoặc external systems**; overflow và idempotency cần thiết kế riêng.
- **Bộ test Java 8** xác minh final totals sau completion barrier, uniqueness của ticket AtomicLong, CAS quota và reset an toàn sau quiescence.
- Chọn primitive theo **độ đúng nghiệp vụ trước, benchmark sau**. Đây đều là các API concurrency còn được hỗ trợ trên Java hiện hành.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — AtomicLong](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/AtomicLong.html)
- [Oracle Java SE 8 — LongAdder](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/LongAdder.html)
- [Oracle Java SE 8 — LongAccumulator](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/LongAccumulator.html)
- [Oracle Java SE 8 — DoubleAdder](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/DoubleAdder.html)
- [Oracle Java SE 8 — DoubleAccumulator](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/DoubleAccumulator.html)
- [Oracle Java SE 8 — ConcurrentHashMap](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentHashMap.html)
- [Oracle Java SE 8 — Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html)
- [Oracle Java SE 25 — AtomicLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Oracle Java SE 25 — LongAdder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
