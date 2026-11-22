# Tranh chấp dữ liệu và tính đúng của kết quả

## Mục tiêu học tập

Trong nhóm **Thuật toán song song**, việc tạo nhiều thread, task hoặc worker không tự đảm bảo kết quả đúng. Khi các tác vụ đọc và ghi dữ liệu dùng chung, thứ tự xen kẽ có thể làm mất cập nhật, đọc trạng thái chưa hoàn tất hoặc phá vỡ một bất biến của thuật toán. Ngay cả khi tất cả thao tác đọc/ghi riêng lẻ đều atomic, một chuỗi nhiều thao tác vẫn có thể không atomic như một giao dịch.

Bài **Tranh chấp dữ liệu và tính đúng của kết quả** giải thích cách nhận diện và loại bỏ lỗi đồng thời trong Java 17+, từ mô hình phụ thuộc tới Java Memory Model, các primitive đồng bộ và thiết kế thuật toán tránh shared mutable state. Đặc biệt cần phân biệt:

- **Data race:** các truy cập bộ nhớ xung đột không có quan hệ đồng bộ/happens-before thích hợp.
- **Race condition:** tính đúng của thao tác logic phụ thuộc thứ tự xen kẽ; có thể xuất hiện **ngay cả khi mọi truy cập đến một biến đều atomic**.
- **Contention:** nhiều thread tranh cùng tài nguyên, thường làm **chậm**, không đồng nghĩa kết quả sai.
- **Liveness:** khả năng tiến triển và hoàn tất; khác với safety (không xảy ra trạng thái sai).

Kết thúc bài, người học có thể:

1. Chứng minh vì sao `counter++` có thể làm mất lượt tăng.
2. Phân biệt atomicity, visibility, ordering và happens-before của Java.
3. Chọn đúng `volatile`, `synchronized`, `AtomicInteger`, `AtomicLong`, CAS, `LongAdder`, `Lock` và công cụ đồng bộ tác vụ.
4. Phân tích race condition do **get–set tách rời** ngay trên `AtomicInteger`.
5. Dùng ownership, dữ liệu bất biến, phân vùng không chồng lấn và partial results để tránh cùng ghi.
6. Cài **parallel reduction** và **parallel prefix scan** với ranh giới hoàn thành rõ ràng.
7. Phân biệt race-free, linearizability, determinism, starvation, deadlock và false sharing.
8. Viết Java 17+ có đầu ra xác định, kiểm thử bằng oracle và có thông báo lỗi số học hợp lý.
9. Đánh giá tính đúng riêng với hiệu năng; không suy tốc độ chỉ từ số worker.

---

## 1. Thuật toán tuần tự đúng chưa chắc đúng khi chạy đồng thời

Giả sử có một bộ đếm:

```java
int counter = 0;
```

Hai thread cùng làm:

```java
counter++;
```

Ý định của thuật toán là có hai lần tăng, nên:

\[
\boxed{counter=2.}
\]

Tuy nhiên `counter++` về mặt thao tác logic cần:

1. Đọc giá trị hiện tại.
2. Tính giá trị mới bằng giá trị cũ cộng 1.
3. Ghi giá trị mới.

Có thể có lịch xen kẽ:

| Thứ tự | Thread A | Thread B | Dữ liệu lưu |
| ---: | --- | --- | ---: |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1 | | 0 |
| 4 | | Tính 1 | 0 |
| 5 | Ghi 1 | | 1 |
| 6 | | Ghi 1 | 1 |

Kết quả:

\[
\boxed{counter=1\ne2.}
\]

Đây là **lost update**: hai phép cập nhật logic đã bị gộp thành một vì chúng cùng xuất phát từ giá trị cũ.

**Lưu ý:** bảng là một lịch diễn giải hợp lý, không phải lời khẳng định một JVM phải luôn thực hiện đúng những bước máy theo thứ tự ấy. Điểm mấu chốt là chương trình không có bảo đảm cập nhật atomic và đồng bộ cần thiết.

### 1.1. Bản chất lỗi

Không phải phép cộng 0+1 sai. Không phải hai thread tự động "đè nhau" chỉ vì cùng chạy. Lỗi xuất hiện vì một **vùng trạng thái có thể bị nhiều writer truy cập không theo giao thức đúng**.

Muốn chứng minh thuật toán song song đúng, phải xét:

- Mỗi phần tử dữ liệu tham gia đúng số lần.
- Tác vụ nào cần chờ kết quả tác vụ nào.
- Mỗi vùng dữ liệu có bao nhiêu reader và writer.
- Truy cập xung đột được bảo vệ bởi cơ chế nào.
- Một thao tác logic gồm mấy truy cập đơn lẻ.
- Đọc kết quả sau khi worker hoàn thành được bảo đảm ra sao.
- Đầu ra phải đúng với mọi lịch hợp lệ hay chỉ một tập lịch cụ thể.
- Số học có overflow hoặc vấn đề làm tròn không.

### 1.2. Hai tầng lỗi thường bị nhầm

**Sai cấp truy cập:** nhiều thread đọc/ghi cùng biến thường không có quan hệ happens-before, gây data race.

**Sai cấp thuật toán:** từng truy cập an toàn, nhưng logic kiểm tra–cập nhật (*check-then-act*) hoặc đọc–sửa–ghi (*read-modify-write*) gồm nhiều bước không được kết hợp thành một thao tác atomic.

Bài này sẽ cố ý dựng một ví dụ **thuộc tầng thứ hai** mà không cần dựa vào một data race có đầu ra bất định để chứng minh lỗi.

---

## 2. Data race là gì?

Trong Java Memory Model (JMM), data race liên quan những truy cập từ các thread khác nhau tới **cùng một biến**, có xung đột đọc/ghi hoặc ghi/ghi, và không được sắp thứ tự bằng **happens-before** cũng như các quy tắc đồng bộ thích hợp.

Ví dụ minh họa nguy hiểm:

```java
final class UnsafeCounter {
    int value;
}

// Thread A:
unsafe.value++;

// Thread B:
unsafe.value++;
```

Nếu không có một giao thức lock, atomic hay quan hệ đồng bộ thích hợp, hai thao tác lên `value` có thể tranh chấp. JMM không bảo đảm chúng tương đương hai lần increment atomic.

### 2.1. Truy cập thế nào là xung đột?

Các trường hợp đáng xét:

- A đọc x, B ghi x.
- A ghi x, B đọc x.
- A ghi x, B ghi x.

Nếu không có quan hệ điều phối phù hợp, đó là truy cập xung đột trên cùng dữ liệu.

Hai thread **chỉ đọc** một giá trị đã được khởi tạo/publish đúng không phải là xung đột đọc–ghi.

Hai thread ghi vào **hai phần tử mảng khác nhau**, nếu không có alias trùng vùng hoặc reader bất đồng bộ vào các vùng ấy, không tự tạo data race trên cùng phần tử.

### 2.2. Data race không nhất thiết biểu hiện trong mọi lần chạy

Một lần test có thể trả đúng `counter=2` do lịch thuận lợi. Ngàn lần test đúng vẫn không chứng minh chương trình data-race-free.

Tính đúng phải dựa vào thiết kế đồng bộ và lập luận theo mọi lịch mà chương trình cho phép, không chỉ theo một lần thực thi được quan sát.

### 2.3. Race condition rộng hơn data race

Race condition là sự phụ thuộc không mong muốn của tính đúng vào thứ tự sự kiện. Một race condition **có thể tồn tại ngay cả khi không có data race**.

Ví dụ:

```java
AtomicInteger count = new AtomicInteger(0);

// Hai thread đều thực hiện:
int old = count.get();
count.set(old + 1);
```

`get` và `set` đều atomic trên `count`, nhưng cả cặp **không phải** một increment atomic. Nếu cả hai cùng đọc 0 trước khi ghi, cuối cùng là 1 thay vì 2.

Do đó:

\[
\boxed{\text{Mọi truy cập atomic}\ \not\Rightarrow\
       \text{mọi thao tác logic đúng}.}
\]

### 2.4. Contention không đồng nghĩa data race

Một triệu `AtomicInteger.incrementAndGet()` từ nhiều thread có thể cho kết quả đúng nhưng chậm do cùng cập nhật một ô cache/biến atomic.

**False sharing** giữa hai ô độc lập nằm cùng cache line cũng làm hiệu năng xấu mà không nhất thiết sai dữ liệu.

Phải tách câu hỏi:

1. **Đúng không?** — safety, invariant, happens-before.
2. **Nhanh không?** — contention, cache, scheduler và memory bandwidth.

---

## 3. Ba thuộc tính: atomicity, visibility, ordering

### 3.1. Atomicity — tính nguyên tử

Một thao tác nguyên tử có thể được xem như xảy ra tại một điểm logic duy nhất theo contract của primitive.

```java
AtomicInteger count = new AtomicInteger();
count.incrementAndGet();
```

`incrementAndGet` là một atomic read–modify–write, trái với:

```java
int old = count.get();
count.set(old + 1);
```

vì hai lời gọi thứ hai có thể bị xen bởi một thao tác khác.

**Một biến atomic không biến giao dịch nhiều biến thành atomic.** Nếu chuyển tiền từ A sang B cần sửa hai số dư, cập nhật hai `AtomicLong` độc lập có thể để reader quan sát trạng thái nửa cũ, nửa mới nếu không có giao thức cấp giao dịch.

### 3.2. Visibility — khả năng nhìn thấy

Một thread ghi dữ liệu và thread khác đọc dữ liệu. Không có đồng bộ, thread đọc có thể không được bảo đảm thấy giá trị mới vào thời điểm mong muốn.

Ví dụ giao thức nguy hiểm:

```java
boolean stop = false;

// Worker:
while (!stop) {
    // work
}

// Controller:
stop = true;
```

JMM không bảo đảm thread worker sẽ thấy thay đổi `stop` đúng cách nếu thiếu đồng bộ.

Khi cờ chỉ cần một trạng thái đơn:

```java
private volatile boolean stop;
```

có thể phù hợp. Nhưng volatile **không tạo mutual exclusion** và không khiến `stop++` hoặc `count++` atomic.

### 3.3. Ordering — quan hệ thứ tự

JVM/JIT và phần cứng có thể đổi cách thực hiện các thao tác trong phạm vi chương trình được phép. Java Memory Model xác định các quan hệ **happens-before** để các thread quan sát dữ liệu đúng theo đồng bộ đã thiết kế.

Ví dụ công bố giá trị:

```java
class Holder {
    int data;
    volatile boolean ready;
}

// Producer:
holder.data = 42;
holder.ready = true;

// Consumer:
if (holder.ready) {
    int result = holder.data;
}
```

Nếu consumer quan sát write `ready=true` của producer qua volatile read, và không có writer khác thay đổi `data`/`ready` theo cách phá hợp đồng, write `data=42` trước đó happens-before read tương ứng.

Không nên tổng quát hóa ví dụ này sang nhiều lần cập nhật cùng một cờ mà không xác định phiên bản/snapshot của dữ liệu.

---

## 4. Java Memory Model và happens-before

**Happens-before** (HB) mô tả thứ tự bộ nhớ được bảo đảm. Thời gian trên đồng hồ **không thay thế** quan hệ HB: "thread A chạy sớm hơn B" không tự chứng minh B quan sát mọi write của A.

### 4.1. Những quy tắc quan trọng

| Cơ chế | Quan hệ happens-before |
| --- | --- |
| Thứ tự trong một thread | Thao tác trước theo program order HB thao tác sau |
| `Thread.start()` | Hành động xảy ra trước lời gọi start HB hành động trong thread được khởi chạy |
| `Thread.join()` | Hành động của thread đã kết thúc HB các hành động sau khi join thành công |
| Monitor `synchronized` | Unlock trên một monitor HB lock kế tiếp trên **chính monitor đó** |
| `volatile` | Write vào volatile HB read tiếp theo trên cùng volatile theo quy tắc đồng bộ |
| Executor/Future | Hành động trước submit HB task; hành động trong task HB hành động sau `Future.get()` |
| `CountDownLatch` | Hành động trước countDown HB hành động sau await thành công |
| Tính bắc cầu | A HB B và B HB C ⇒ A HB C |

Điểm chung: **đồng bộ có contract**, không chỉ là "giảm độ trễ" hay "chờ ngẫu nhiên một chút".

### 4.2. Vì sao sleep không giải quyết visibility?

`Thread.sleep(100)` khiến thread ngừng chạy một khoảng thời gian, nhưng không tự tạo happens-before giữa writer và reader của một biến thường.

Nếu thêm sleep khiến lỗi bớt xuất hiện, chương trình vẫn có thể sai ở lịch khác.

### 4.3. Future.get() làm gì?

`Future.get()` chờ task hoàn thành hoặc ném exception; những hành động trong task happens-before những hành động sau khi lấy kết quả thành công từ Future theo contract concurrency của Java.

Vì vậy:

```java
Future<Long> future = pool.submit(() -> computePartial());
long value = future.get();
```

là cách lấy kết quả có ranh giới đồng bộ rõ ràng.

### 4.4. Happens-before không tự thay thế invariant logic

Đoạn:

```java
if (count.get() < limit) {
    count.incrementAndGet();
}
```

có thể sai khi nhiều thread cùng kiểm tra và tăng: cả hai thấy giá trị dưới limit trước khi một thread tăng. Mọi thao tác trên `AtomicInteger` vẫn atomic, nhưng đoạn check-then-act **không atomic như một tổng thể**.

Muốn không vượt limit, có thể dùng CAS loop hoặc lock bao cả check và update.

---

## 5. Các cơ chế đồng bộ và phạm vi đúng

### 5.1. Volatile

Dùng cho cờ/trạng thái đơn giản cần visibility:

```java
private volatile boolean shutdownRequested;
```

Không đủ cho:

```java
volatile int count;
count++; // vẫn là read-modify-write không atomic
```

Volatile cũng không phải cơ chế transaction nhiều trường hay bảo vệ một đoạn critical section.

### 5.2. Synchronized

```java
final class LockedCounter {
    private long count;

    public synchronized void increment() {
        count++;
    }

    public synchronized long get() {
        return count;
    }
}
```

Với cùng một monitor:

- Các vùng đồng bộ tương ứng không chạy chồng nhau.
- Unlock/lock thiết lập HB.
- Nếu **mọi truy cập** vào `count` đều tuân cùng khóa, thao tác increment là atomic theo giao thức này.

Nếu một nơi khác trực tiếp đọc/ghi `count` không khóa, contract có thể bị phá.

### 5.3. AtomicInteger/AtomicLong

Một số thao tác quen thuộc:

```java
incrementAndGet()
getAndIncrement()
addAndGet(delta)
compareAndSet(expected, update)
get()
set(value)
```

`incrementAndGet()` atomic cho increment. `get()` rồi `set()` là hai thao tác riêng, không bảo vệ invariant khi bị xen.

### 5.4. CAS loop

Ví dụ tăng nếu còn dưới trần:

```java
static boolean tryIncrementBelow(
        AtomicInteger counter, int limit) {

    for (;;) {
        int old = counter.get();

        if (old >= limit) {
            return false;
        }

        if (counter.compareAndSet(old, old + 1)) {
            return true;
        }

        // State changed: retry.
    }
}
```

Điều kiện sử dụng: giá trị không âm và giới hạn thích hợp để phép `old+1` không tràn `int`; đặc tả ứng dụng phải quy định dữ liệu hợp lệ.

Nếu `compareAndSet` thất bại, phải thử lại hoặc có xử lý khác phù hợp. Không được báo thành công dù update chưa thực hiện.

### 5.5. LongAdder

`LongAdder` giảm contention bằng nhiều ô đếm nội bộ khi có nhiều writer:

```java
LongAdder adder = new LongAdder();
adder.increment();
```

Sau khi mọi task cập nhật đã hoàn thành, `sum()` là tổng các cập nhật đã xong. Tuy nhiên **`sum()` khi writer vẫn đang chạy không phải một snapshot atomic của tất cả ô**; không nên dùng nó để thực thi invariant "bây giờ chắc chắn count≤limit" với nhiều concurrent writer.

### 5.6. ReentrantLock

`ReentrantLock` hỗ trợ lock/unlock chủ động, `tryLock`, interruptible acquisition và Condition.

```java
lock.lock();
try {
    // Read and update protected state.
} finally {
    lock.unlock();
}
```

Không bỏ qua `finally` vì exception hoặc return sớm có thể khiến khóa không được giải phóng.

### 5.7. ConcurrentHashMap

`ConcurrentHashMap` hỗ trợ các thao tác thread-safe theo contract, ví dụ cập nhật theo khóa với `merge`/`compute`.

Nhưng việc sửa **hai khóa** bằng hai lời gọi không mặc nhiên là một transaction atomic trên cả hai khóa. Việc duyệt map đang được cập nhật cũng không tự tạo snapshot nhất quán toàn bộ.

Cần xác định invariant áp dụng cho **một khóa, một biến hay cả tập biến** trước khi chọn primitive.

---

## 6. Ví dụ phản chứng: từng get/set atomic nhưng phép tăng sai

Hai thread cùng thực hiện:

```java
int old = counter.get();
barrier.await();
counter.set(old + 1);
```

Ở đây `counter` là `AtomicInteger(0)` và `barrier` là `CyclicBarrier(2)`.

- Thread A đọc 0.
- Thread B đọc 0.
- Cả hai phải tới barrier trước khi thread nào được đi tiếp.
- A ghi 1.
- B ghi 1.

Kết quả chắc chắn là:

\[
\boxed{1}
\]

thay vì kết quả mong đợi của **hai increment** là:

\[
\boxed{2}.
\]

Đây là **race condition của thao tác logic** dù bản thân các get/set là atomic. Test có lịch được ép bởi barrier nên không phụ thuộc vào việc một data race ngẫu nhiên có xảy ra không.

Thay đoạn `get`/`set` bằng:

```java
counter.incrementAndGet();
```

thì hai lần tăng thành công sẽ cho 2.

### 6.1. Vì sao không chỉ thêm sleep?

Sleep không xác định chính xác thời điểm hai thread đọc trước khi ghi. Barrier thiết lập một ranh giới rõ: **mọi party phải hoàn thành bước đọc rồi mới qua bước ghi**.

Trong chương trình có barrier, phải cấp đủ worker để số parties tới barrier; pool chỉ có một worker mà hai task cùng đợi barrier hai parties có thể treo.

---

## 7. Thiết kế tổng song song không dùng sharedSum

Xét bài toán:

\[
\boxed{S=\sum_{i=1}^{1\,000\,000}i=500\,000\,500\,000.}
\]

Chia dữ liệu thành bốn khoảng không giao nhau:

| Worker | Khoảng số nguyên | Partial sum |
| ---: | --- | ---: |
| 0 | 1..250.000 | 31.250.125.000 |
| 1 | 250.001..500.000 | 93.750.125.000 |
| 2 | 500.001..750.000 | 156.250.125.000 |
| 3 | 750.001..1.000.000 | 218.750.125.000 |

Gộp:

\[
31\,250\,125\,000+
93\,750\,125\,000+
156\,250\,125\,000+
218\,750\,125\,000
=\boxed{500\,000\,500\,000}.
\]

### 7.1. Hai bất biến phân hoạch

Nếu `I_j` là tập chỉ số của worker j:

\[
I_i\cap I_j=\varnothing
\quad(i\ne j),
\]

\[
\bigcup_j I_j=\{1,\ldots,N\}.
\]

Nghĩa là không bỏ sót, không đếm trùng.

### 7.2. Không cập nhật biến tổng chung

Mỗi task tính:

```java
long local = 0;
for (int i = start; i < end; i++) {
    local = Math.addExact(local, i + 1L);
}
return local;
```

Biến `local` chỉ thuộc task. Thread chính nhận mỗi `Future<Long>` bằng `get()` rồi gộp. Không có hai worker cùng ghi một biến tổng.

### 7.3. Lợi ích

- Ít contention hơn so với mỗi phần tử đều khóa một biến chung.
- Dễ chứng minh không mất lượt cập nhật.
- Có thể gộp kết quả theo thứ tự cố định để tăng khả năng tái lập.
- Áp dụng cho tổng, histogram theo vùng, vector dot product và những phép aggregate kết hợp phù hợp.

Không được tự suy "ít lock" nghĩa luôn nhanh hơn: với input nhỏ, chi phí tạo task và đồng bộ có thể vượt lợi ích song song.

---

## 8. Parallel prefix scan: dependency phải đúng

Reduction chỉ trả một kết quả. **Inclusive prefix scan** trả tổng tiền tố ở từng vị trí.

Ví dụ:

```text
Input:  [1,2,3,4,5,6,7,8]
Output: [1,3,6,10,15,21,28,36]
```

Nếu đồng thời thực hiện:

```java
// KHÔNG đúng khi chạy đồng thời trên cùng mảng thường:
a[i] += a[i - 1];
```

một task có thể đọc `a[i-1]` trước hoặc sau khi task khác sửa nó, gây sai và có thể có data race.

### 8.1. Hillis–Steele scan với hai mảng mỗi vòng

Giả sử stage hiện tại dùng khoảng cách d:

\[
dst[i]=
\begin{cases}
src[i],&i<d,\\
src[i]+src[i-d],&i\ge d.
\end{cases}
\]

Tất cả task trong vòng này **chỉ đọc src** và ghi **các chỉ số không giao nhau** của dst.

Sau khi tất cả `Future.get()` hoàn tất mới dùng dst làm src cho vòng kế tiếp. Khoảng cách lần lượt:

\[
d=1,2,4,\ldots
\]

### 8.2. Ví dụ từng stage

```text
Ban đầu: [1,2,3,4,5,6,7,8]
d=1:     [1,3,5,7,9,11,13,15]
d=2:     [1,3,6,10,14,18,22,26]
d=4:     [1,3,6,10,15,21,28,36]
```

Kết quả cuối là mọi prefix sum.

### 8.3. Chứng minh bất biến

Đầu vòng d, `src[i]` là tổng của tối đa d phần tử liên tiếp kết thúc tại i. Khi i≥d, hai tổng `src[i]` và `src[i-d]` thuộc hai khối kề nhau, gộp thành tối đa 2d phần tử. Nếu i<d, src[i] đã là tổng toàn bộ tiền tố tới i.

Sau d=1,2,4,..., mỗi vòng tăng độ dài khối tối đa gấp đôi. Khi d đủ lớn, tất cả phần tử ở phía trước đã được gộp, nên kết quả đúng.

### 8.4. Độ phức tạp

Với n phần tử:

- O(log n) stage trong mô hình chuẩn.
- O(n) phép toán mỗi stage.
- Work tổng O(n log n).
- Span lý tưởng O(log n) với đủ bộ xử lý và mỗi stage được đồng bộ phù hợp.
- Bộ nhớ phụ O(n) cho source/target, chưa tính overhead lập task.

Hillis–Steele dễ hiểu nhưng không work-efficient so với scan tuần tự O(n). **Blelloch scan** dùng upsweep/downsweep có thể đạt O(n) work và O(log n) span dưới mô hình phù hợp.

### 8.5. Số học song song

Phép cộng số nguyên chính xác là kết hợp về toán học. Nhưng Java `long` có giới hạn. Mã bài dùng `Math.addExact` để phát hiện overflow.

Với `double`, thay thứ tự nhóm phép cộng có thể làm thay đổi vài bit kết quả vì làm tròn; không được đồng nhất mọi khác biệt nhỏ với data race.

---

## 9. Ownership và safe publication

### 9.1. Input chỉ đọc

Nếu input được khởi tạo đầy đủ trước khi submit task, và không có thread nào sửa input trong thời gian các task đọc, nhiều task có thể cùng đọc mà không cần khóa từng ô.

Việc submit qua ExecutorService cung cấp quan hệ đồng bộ thích hợp cho dữ liệu chuẩn bị trước submit theo contract Java concurrency.

Nếu có writer sửa input đồng thời, phải xét snapshot/đồng bộ.

### 9.2. Output chia vùng

Ví dụ:

```text
Worker 0 ghi result[0..249]
Worker 1 ghi result[250..499]
Worker 2 ghi result[500..749]
Worker 3 ghi result[750..999]
```

Mỗi phần tử chỉ có một writer, tránh xung đột trên cùng phần tử. Thread chính đọc sau khi các worker đã hoàn thành.

Hai phần tử khác nhau vẫn có thể nằm chung cache line, gây **false sharing**, nhưng khác với race trên cùng ô.

### 9.3. Immutable snapshot

Thay vì sửa nhiều trường của một object đang được đọc, writer có thể xây một snapshot mới **bất biến** rồi publish tham chiếu bằng `volatile`/`AtomicReference` theo giao thức rõ.

Lưu ý:

- `final` reference không tự làm object mà nó trỏ tới bất biến.
- Nếu snapshot chứa `long[]` mutable, phải phòng ngừa sửa mảng từ bên ngoài.
- Safe publication giúp reader thấy object ở trạng thái khởi tạo thích hợp; không làm đồng bộ các sửa đổi sau đó nếu object vẫn mutable.

---

## 10. Linearizability, safety và liveness

### 10.1. Safety

Thuộc tính safety nói "điều gì không được xảy ra":

- Tổng không bỏ sót và không đếm trùng.
- Bộ đếm không vượt limit.
- Không đọc trạng thái giữa một transaction cần atomic.
- Không đưa một đường đi chưa tính đủ vào kết quả.

### 10.2. Liveness

Thuộc tính liveness nói "có thể tiến triển và hoàn tất", ví dụ:

- Task không bị chờ vô hạn do vòng khóa.
- Barrier cuối cùng được giải phóng khi đủ parties.
- Một yêu cầu hợp lệ không bị bỏ đói mãi dưới điều kiện lập lịch giả định.

Chương trình **không có data race** vẫn có thể deadlock hoặc starvation.

### 10.3. Deadlock

Ví dụ:

```text
Thread A giữ lock X, chờ lock Y.
Thread B giữ lock Y, chờ lock X.
```

Cả hai chờ nhau.

Biện pháp thường dùng là **lấy khóa theo thứ tự toàn cục nhất quán**, giới hạn thời gian chờ hoặc dùng `tryLock` khi phù hợp, giải phóng khóa trong `finally`, tránh giữ khóa trong khi `Future.get()` chờ task cần cùng khóa.

### 10.4. Starvation và livelock

- **Starvation:** thread thường xuyên không được tiếp cận tài nguyên.
- **Livelock:** các thread vẫn thực hiện phản ứng qua lại nhưng không tạo tiến triển hữu ích.

Lock-free không có nghĩa mọi thread luôn hoàn tất trong số bước bị chặn (*wait-free*). CAS loop có thể retry nhiều lần do contention.

### 10.5. Linearizability

Một thao tác linearizable có thể được xem như xảy ra tại một thời điểm logic duy nhất giữa lúc gọi và trả kết quả, đồng thời giữ thứ tự những thao tác không chồng lấn.

`AtomicInteger.incrementAndGet()` cung cấp phép tăng nguyên tử. Nhưng cặp `get()` rồi `set()` **không phải** một phép tăng linearizable.

Một `LongAdder.sum()` trong lúc còn writer không phải snapshot atomic của toàn bộ các ô; nếu ứng dụng cần một phép đọc tuyến tính hóa ngay khi writer vẫn đang chạy, phải chọn cơ chế khác.

---

## 11. Java 17+: chương trình độc lập có đầu ra xác định

Tệp: **`DataRaceCorrectnessDemo.java`**.

Chương trình minh họa:

1. `AtomicInteger.get()`/`set()` tách rời với barrier ép cả hai đọc 0, dẫn tới **1 thay vì 2**.
2. Bốn worker tăng 50.000 lần bằng `incrementAndGet()`, ra **200000**.
3. Bốn worker tăng bằng `synchronized`, ra **200000**.
4. Bốn worker dùng `LongAdder`, chỉ đọc `sum()` sau `Future.get()`, ra **200000**.
5. Tổng 1..1.000.000 bằng bốn phân vùng, ra **500000500000**.
6. Inclusive scan tám phần tử qua stage có hai mảng riêng, ra `[1,3,6,10,15,21,28,36]`.
7. Scan n=1, n=0, input null và xử lý overflow bên trong Future.

**Không in kết quả của một data race không xác định trên biến `int` thường.** Các dòng stdout chỉ dựa vào hành vi được bảo đảm bằng barrier, atomic operation và Future.get.

### 11.1. Mã nguồn hoàn chỉnh

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public final class DataRaceCorrectnessDemo {

    private static final int WORKERS = 4;
    private static final int INCREMENTS = 50_000;

    static final class LockedCounter {
        private long value;

        synchronized void increment() {
            value++;
        }

        synchronized long get() {
            return value;
        }
    }

    // Both get() calls complete before either set().
    // Atomic accesses do not make the get+set pair atomic.
    static int brokenGetSet(ExecutorService pool)
            throws Exception {

        AtomicInteger counter = new AtomicInteger(0);
        CyclicBarrier afterReads = new CyclicBarrier(2);

        Callable<Void> update = () -> {
            int old = counter.get();
            afterReads.await();
            counter.set(old + 1);
            return null;
        };

        Future<Void> first = pool.submit(update);
        Future<Void> second = pool.submit(update);
        first.get();
        second.get();

        return counter.get();
    }

    static int safeAtomicIncrements(ExecutorService pool)
            throws Exception {

        AtomicInteger counter = new AtomicInteger(0);
        List<Future<?>> tasks = new ArrayList<>();

        for (int w = 0; w < WORKERS; w++) {
            tasks.add(pool.submit(() -> {
                for (int j = 0; j < INCREMENTS; j++) {
                    counter.incrementAndGet();
                }
            }));
        }

        for (Future<?> task : tasks) {
            task.get();
        }

        return counter.get();
    }

    static long safeSynchronizedIncrements(
            ExecutorService pool) throws Exception {

        LockedCounter counter = new LockedCounter();
        List<Future<?>> tasks = new ArrayList<>();

        for (int w = 0; w < WORKERS; w++) {
            tasks.add(pool.submit(() -> {
                for (int j = 0; j < INCREMENTS; j++) {
                    counter.increment();
                }
            }));
        }

        for (Future<?> task : tasks) {
            task.get();
        }

        return counter.get();
    }

    static long safeLongAdderAfterJoins(
            ExecutorService pool) throws Exception {

        LongAdder counter = new LongAdder();
        List<Future<?>> tasks = new ArrayList<>();

        for (int w = 0; w < WORKERS; w++) {
            tasks.add(pool.submit(() -> {
                for (int j = 0; j < INCREMENTS; j++) {
                    counter.increment();
                }
            }));
        }

        // Read sum only after every updating task completes.
        for (Future<?> task : tasks) {
            task.get();
        }

        return counter.sum();
    }

    // Compute sum(1..n) with no shared mutable accumulator.
    static long partitionedSum(
            int n, ExecutorService pool) throws Exception {

        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }

        List<Future<Long>> tasks = new ArrayList<>();

        for (int w = 0; w < WORKERS; w++) {
            final int start =
                    w * (n / WORKERS)
                    + Math.min(w, n % WORKERS);

            final int end =
                    start
                    + n / WORKERS
                    + (w < n % WORKERS ? 1 : 0);

            tasks.add(pool.submit(() -> {
                long local = 0L;

                for (int i = start; i < end; i++) {
                    local = Math.addExact(local, i + 1L);
                }

                return local;
            }));
        }

        long answer = 0L;

        for (Future<Long> task : tasks) {
            answer = Math.addExact(answer, task.get());
        }

        return answer;
    }

    // Inclusive Hillis-Steele scan with a full stage barrier.
    static long[] parallelPrefixScan(
            long[] input, ExecutorService pool)
            throws Exception {

        if (input == null) {
            throw new IllegalArgumentException(
                    "Input must not be null");
        }

        long[] current = input.clone();
        int n = current.length;
        final int chunk = 2;

        for (int offset = 1; offset < n; ) {
            final int shift = offset;
            final long[] source = current;
            final long[] target = new long[n];
            List<Future<?>> tasks = new ArrayList<>();

            for (int start = 0; start < n; start += chunk) {
                final int lo = start;
                final int hi = Math.min(start + chunk, n);

                tasks.add(pool.submit(() -> {
                    for (int i = lo; i < hi; i++) {
                        if (i < shift) {
                            target[i] = source[i];
                        } else {
                            target[i] = Math.addExact(
                                    source[i],
                                    source[i - shift]);
                        }
                    }
                }));
            }

            // Every task from this stage must finish first.
            for (Future<?> task : tasks) {
                task.get();
            }

            current = target;

            // Avoid overflow of the shift when n is huge.
            if (offset > n / 2) {
                break;
            }
            offset *= 2;
        }

        return current;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(WORKERS);

        try {
            System.out.println(
                    "Atomic get/set with barrier: "
                    + brokenGetSet(pool));

            System.out.println(
                    "Atomic incrementAndGet: "
                    + safeAtomicIncrements(pool));

            System.out.println(
                    "Synchronized increments: "
                    + safeSynchronizedIncrements(pool));

            System.out.println(
                    "LongAdder after joins: "
                    + safeLongAdderAfterJoins(pool));

            System.out.println(
                    "Partitioned sum 1..1000000: "
                    + partitionedSum(1_000_000, pool));

            long[] scan = parallelPrefixScan(
                    new long[] {1, 2, 3, 4, 5, 6, 7, 8},
                    pool);

            System.out.println(
                    "Parallel prefix scan: "
                    + Arrays.toString(scan));

            System.out.println(
                    "Singleton scan: "
                    + Arrays.toString(
                            parallelPrefixScan(
                                    new long[] {42}, pool)));

            System.out.println(
                    "Empty scan: "
                    + Arrays.toString(
                            parallelPrefixScan(
                                    new long[0], pool)));

            boolean nullRejected = false;
            try {
                parallelPrefixScan(null, pool);
            } catch (IllegalArgumentException ex) {
                nullRejected = true;
            }

            System.out.println(
                    "Null input rejected: " + nullRejected);

            boolean overflowDetected = false;
            try {
                parallelPrefixScan(
                        new long[] {Long.MAX_VALUE, 1L},
                        pool);
            } catch (ExecutionException ex) {
                overflowDetected =
                        ex.getCause() instanceof ArithmeticException;
            }

            System.out.println(
                    "Overflow detected: " + overflowDetected);
        } finally {
            pool.shutdown();
        }
    }
}
```

### 11.2. Biên dịch và chạy

Yêu cầu JDK 17+:

```bash
javac DataRaceCorrectnessDemo.java
java DataRaceCorrectnessDemo
```

**Stdout kỳ vọng:**

```text
Atomic get/set with barrier: 1
Atomic incrementAndGet: 200000
Synchronized increments: 200000
LongAdder after joins: 200000
Partitioned sum 1..1000000: 500000500000
Parallel prefix scan: [1, 3, 6, 10, 15, 21, 28, 36]
Singleton scan: [42]
Empty scan: []
Null input rejected: true
Overflow detected: true
```

### 11.3. Vì sao kết quả get/set là 1?

Hai task đều gọi `counter.get()` trước barrier và đều thấy 0, vì không có task nào được `set` trước khi cả hai đến barrier. Sau barrier, mỗi task đặt 1, vì thế kết quả cuối là 1.

Từng truy cập vẫn atomic, nhưng **hai increment logic bị mất một lượt**.

### 11.4. Vì sao ba bộ đếm an toàn là 200000?

Bốn worker cùng tăng 50.000 lần:

\[
4\cdot50\,000=200\,000.
\]

- `AtomicInteger.incrementAndGet` không làm mất lượt tăng.
- `LockedCounter` bao thao tác tăng trong `synchronized` của cùng monitor.
- `LongAdder.sum` được gọi sau khi tất cả task đã hoàn thành.

Các bộ đếm có thể có hiệu năng khác nhau; **đúng cùng kết quả** không có nghĩa chúng có thời gian bằng nhau.

### 11.5. Vì sao tổng phân vùng chính xác?

Mỗi worker có một dải `[start,end)` không giao nhau. Mọi số i+1 từ 1..1.000.000 được xử lý đúng một lần. `local` là biến riêng; thread chính lấy kết quả qua Future sau khi hoàn tất.

Không có `sharedSum` để nhiều worker cùng ghi.

### 11.6. Vì sao scan không có ghi đè dữ liệu của vòng trước?

- Mảng `source` của mỗi stage chỉ được đọc.
- Những task khác nhau ghi những chỉ số khác nhau của `target`.
- Thread chính đợi tất cả `Future.get()` xong rồi mới chuyển `current=target`.
- Vòng sau chỉ bắt đầu khi vòng trước hoàn chỉnh.

Đây là cấu trúc bảo vệ phụ thuộc, không chỉ một mẹo làm code chạy nhanh.

### 11.7. Vì sao overflow xuất hiện dưới dạng ExecutionException?

`Math.addExact` chạy trong một task được submit. Khi tràn long, task ném `ArithmeticException`. Khi gọi `Future.get()` trên task ấy, Java chuyển exception của task qua `ExecutionException`. Lý do gốc nằm trong `getCause()`, do đó test:

```java
ex.getCause() instanceof ArithmeticException
```

là cách xác minh đúng đối với ví dụ.

### 11.8. Trường hợp n nhỏ

- n=0: mảng scan rỗng, không có vòng cộng nào, trả [].
- n=1: không cần cộng, trả bản sao [42].
- n=2: một stage shift1, trả [a0,a0+a1].
- n lẻ: vẫn dùng các shift lũy thừa hai cho tới khi bao phủ.
- Input null: từ chối bằng `IllegalArgumentException`.

### 11.9. Giới hạn mã demo

- Dùng pool bốn worker nên barrier hai parties có đủ worker để tham gia.
- Không có timeout; nếu áp dụng vào production với task có khả năng lỗi, cần thiết kế hủy/timeout phù hợp.
- `Math.addExact` kiểm tra tổng nguyên long, không giải bài toán số học vượt 64 bit.
- `shutdown()` ngừng nhận task mới nhưng không tự cưỡng bức hoàn tất/hủy mọi task; demo đã chờ các Future đang sử dụng.
- Đây là demo tính đúng với stdout xác định, **không phải benchmark** độ trễ của một máy cụ thể.

---

## 12. Chứng minh đúng và độ phức tạp

### 12.1. Bộ đếm atomic

Bất biến: sau m lần `incrementAndGet()` thành công, giá trị tăng đúng m so với ban đầu.

Cơ sở m=0 đúng. Mỗi atomic increment chuyển count tăng một mà không ghi đè mất increment khác, nên quy nạp cho mọi m trong giới hạn `int`.

### 12.2. Bộ đếm synchronized

Nếu mọi truy cập dùng cùng monitor, các lần increment được tuần tự hóa theo mutual exclusion. Mỗi lần cộng một, nên sau m lần kết quả bằng m.

Nếu một nhánh khác ghi biến không lock, lập luận không còn hợp lệ.

### 12.3. Reduction

Giả sử các tập chỉ số `I_j` đôi một rời nhau và hợp của chúng bằng tất cả input. Khi task j tính chính xác tổng các phần tử `I_j`:

\[
\sum_j\sum_{i\in I_j}a_i=\sum_i a_i.
\]

Đây là tính đúng theo phân hoạch, không phụ thuộc thời điểm các task bắt đầu. Việc gộp sau khi Future hoàn thành loại bỏ nhu cầu đồng bộ một shared accumulator.

### 12.4. Scan

Bất biến: trước stage offset d, `source[i]` chứa tổng của tối đa d phần tử liên tiếp kết thúc ở i. `target[i]` gộp hai khối kề nhau hoặc giữ nguyên prefix ở biên.

Sau O(log n) stage, tổng tại i bao phủ chính xác 0..i. Ranh giới Future.get ngăn task stage sau đọc dữ liệu chưa hoàn chỉnh.

### 12.5. Độ phức tạp

| Kỹ thuật | Work | Phụ thuộc và lưu ý |
| --- | --- | --- |
| Atomic counter M lần | O(M) | Contention trên cùng một biến có thể hạn chế throughput |
| Synchronized counter M lần | O(M) | Các cập nhật vào cùng monitor bị tuần tự hóa |
| LongAdder M lần | O(M) | Giảm contention; `sum()` không snapshot atomic khi đang update |
| Reduction N phần tử, P worker | O(N+P) | Local sum khoảng N/P phần tử; gộp P partials trong mã là O(P) |
| Hillis–Steele scan | O(N log N) | O(log N) stage, bộ nhớ phụ O(N), overhead task không tính trong cận lý tưởng |

Các con số work/span ở đây không phải ms thực đo. Với N nhỏ, tạo task và đồng bộ có thể chậm hơn xử lý tuần tự.

---

## 13. Đồng bộ đúng nhưng hiệu năng vẫn kém

### 13.1. Contention trên một biến nóng

Một `AtomicInteger` chung có thể đúng nhưng mọi writer phải tranh giành cập nhật cùng biến. Thêm thread không nhất thiết tăng throughput tuyến tính.

### 13.2. False sharing

Hai biến **khác nhau** thuộc cùng cache line có thể bị hai lõi cập nhật luân phiên, tạo nhiều lưu lượng coherency. Kết quả vẫn có thể đúng nhưng thời gian tăng.

Đừng gán lỗi kết quả sai cho false sharing nếu thực tế có lost update; hai hiện tượng khác loại.

### 13.3. Task quá nhỏ

Nếu mỗi phép cộng chỉ rất rẻ, tạo một task và một Future cho mỗi phần tử có thể tốn nhiều hơn phép cộng. Chọn kích thước block phù hợp.

### 13.4. Lock quá lớn

Nếu một thread giữ lock để xử lý toàn bộ mảng, các thread khác phải chờ, khiến chương trình gần như tuần tự.

### 13.5. Băng thông và locality

Với luồng dữ liệu lớn, các thread cùng đọc RAM có thể gặp giới hạn băng thông. Phân vùng liên tục giúp locality nhưng không xóa giới hạn phần cứng.

### 13.6. Cần benchmark riêng

Dùng baseline tuần tự đúng và cùng input, khởi động JIT trước khi đo, chạy nhiều lần, báo kích thước dữ liệu/số worker/phiên bản JDK/hardware. Không được lấy "bốn task" làm chứng cứ chương trình nhanh gấp bốn.

---

## 14. Kiểm thử đồng thời đúng phương pháp

### 14.1. Test P=1 chưa đủ

Một chương trình sai khi hai writer xen kẽ có thể chạy hoàn toàn đúng khi chỉ có một worker.

### 14.2. Test chạy đi chạy lại chưa phải chứng minh

Một race condition có thể cực hiếm xuất hiện trong lịch thông thường. Một triệu lần pass không đảm bảo mọi lịch đều đúng.

Cần bổ sung lập luận HB/invariant và kiểm thử interleaving có chủ đích.

### 14.3. Dùng barrier để dựng lịch

Demo `brokenGetSet` ép hai lần đọc xảy ra trước mọi lần ghi. Kết quả 1 là một phản chứng **có cấu trúc và lặp lại được**, không dựa vào `Thread.sleep`.

Không nên dùng barrier với số parties lớn hơn số task có thể đồng thời tới đó, vì có nguy cơ treo.

### 14.4. Oracle reduction

Với tổng 1..N:

\[
\boxed{\frac{N(N+1)}2}
\]

là oracle độc lập phù hợp nếu tính bằng kiểu số không bị tràn.

Hoặc dùng một vòng tuần tự tách biệt để so với các partial sums đã gộp.

### 14.5. Oracle scan

Với input a:

```java
long running = 0;
for (int i = 0; i < a.length; i++) {
    running = Math.addExact(running, a[i]);
    expected[i] = running;
}
```

So **mọi vị trí** của scan, không chỉ phần tử cuối.

### 14.6. Các ca biên

| Trường hợp | Kỳ vọng |
| --- | --- |
| Hai Atomic get/set có barrier | Kết quả 1, chứng minh thao tác ghép không atomic |
| Hai incrementAndGet | Kết quả 2 |
| Bốn worker × 50.000 atomic increments | 200.000 |
| Bốn worker × 50.000 locked increments | 200.000 |
| LongAdder sau joins | 200.000 |
| Sum từ 1 đến 1.000.000 | 500.000.500.000 |
| Scan [1..8] | [1,3,6,10,15,21,28,36] |
| Scan [42] | [42] |
| Scan mảng rỗng | [] |
| Scan null | Từ chối |
| Long.MAX_VALUE + 1 trong worker | ExecutionException chứa ArithmeticException |
| n không chia hết P | Mọi phần tử vẫn được xử lý đúng một lần |
| Các giá trị âm, 0 | Prefix và tổng khớp oracle |
| Số thread lớn hơn số phần tử | Cho phép phân vùng rỗng nếu thuật toán có hợp đồng |
| Writer sửa input trong khi task đang đọc | Bắt buộc có snapshot/đồng bộ; không giả định an toàn |

### 14.7. Công cụ chuyên dụng

Với litmus tests về JMM, có thể dùng **jcstress** khi môi trường phù hợp. Để đo vi hiệu năng trên JVM, có thể dùng **JMH** và warmup phù hợp.

Không biến các công cụ đó thành "bằng chứng tự động chương trình luôn đúng"; thiết kế và chứng minh invariant vẫn cần thiết.

---

## 15. Những lỗi thường gặp

1. **Nhầm nhiều thread cùng chạy với data race**, dù không có truy cập xung đột.
2. **Cho rằng một lần chạy đúng nghĩa là không có race**.
3. **Cho rằng race-free đồng nghĩa thuật toán đúng**, bỏ thao tác logic ghép không atomic.
4. **Dùng counter++ trên biến thường** khi nhiều writer.
5. **Thêm volatile rồi nghĩ ++ atomic**.
6. **Thay int bằng AtomicInteger nhưng vẫn dùng get–set rời rạc**.
7. **Check-then-act bằng hai atomic call** và làm vượt limit.
8. **CAS thất bại nhưng không retry/xử lý**, mất cập nhật.
9. **CAS loop overflow old+1**.
10. **Dùng một biến atomic để bảo vệ invariant nhiều biến**, không đủ.
11. **Đọc dữ liệu do worker ghi trước Future.get/join**, thiếu ranh giới.
12. **Dùng sleep để thay HB**.
13. **Synchronized trên hai monitor khác nhau**, không loại trừ nhau.
14. **Một nhánh đọc/ghi không khóa**, phá quy ước khóa.
15. **Quên unlock trong finally**.
16. **Giữ lock khi chờ Future cần lock ấy**, deadlock.
17. **Tưởng LongAdder.sum đang cập nhật là snapshot tức thời**, không đúng.
18. **Tưởng concurrent map tự cung cấp transaction đa khóa**, không đúng.
19. **Tưởng final reference bảo vệ nội dung mutable bên trong**, không đúng.
20. **Quên safe publication của input dùng chung**.
21. **Hai worker ghi cùng một index output**, data race.
22. **Scan cùng vòng đọc một mảng đang bị ghi**, phụ thuộc sai.
23. **Không chờ mọi task stage trước khi sang stage sau**.
24. **Chia phân vùng có chồng lấn hoặc bỏ sót phần tử**.
25. **Cộng partial results khi task chưa xong**.
26. **Không xử lý exception của task qua Future.get**.
27. **Không kiểm tra overflow long**.
28. **Đòi double reduction bằng từng bit dù đổi thứ tự cộng**.
29. **Coi mọi sai khác floating point là lỗi làm tròn**, bỏ qua race thật.
30. **Bỏ trường hợp n=0,1 và n lẻ**.
31. **Dùng barrier hai parties với pool không đủ worker**, có thể treo.
32. **Dùng nhiều lock không có thứ tự**, deadlock.
33. **Nhầm false sharing với lost update**, một bên hiệu năng, bên kia tính đúng.
34. **Dùng rất nhiều task nhỏ cho phép tính rẻ**, overhead cao.
35. **Tuyên bố pool bốn worker chắc nhanh gấp bốn**, thiếu benchmark.
36. **Không tách kiểm thử kết quả khỏi đo hiệu năng**.
37. **Chỉ so phần tử cuối của scan**, bỏ lỗi prefix trước.
38. **Chỉ stress random mà thiếu test lịch có chủ đích**.
39. **Quên liveness**, chương trình không sai dữ liệu nhưng treo.
40. **Cho rằng ExecutorService.shutdown() lập tức dừng mọi task**, không đúng.

---

## 16. Bài tập tự kiểm tra

### Bài 1
Data race là gì? Nêu điều kiện có ít nhất một writer.

### Bài 2
Race condition khác data race ở điểm nào?

### Bài 3
Tạo một lịch hai thread làm `count++` dẫn đến count=1 thay vì 2.

### Bài 4
Vì sao `volatile int count` không giải quyết `count++`?

### Bài 5
Vì sao `get()` và `set()` của AtomicInteger riêng lẻ không đủ cho increment?

### Bài 6
Khi dùng barrier buộc cả hai đọc trước khi ghi, hai get/set từ 0 cho kết quả nào?

### Bài 7
Phân biệt atomicity và visibility.

### Bài 8
Happens-before có thể được tạo bởi những cơ chế nào?

### Bài 9
Vì sao sleep không thể thay Future.get?

### Bài 10
`Future.get()` bảo đảm điều gì liên quan task?

### Bài 11
Volatile boolean phù hợp cho loại trạng thái nào?

### Bài 12
Giải thích vì sao một AtomicLong không tự bảo vệ giao dịch hai tài khoản.

### Bài 13
`incrementAndGet()` khác `get()` rồi `set()` như thế nào?

### Bài 14
Trong CAS loop, khi compareAndSet false thì sao?

### Bài 15
Có nguy cơ gì nếu hai thread cùng kiểm tra count<10 rồi tăng từ 9?

### Bài 16
Tại sao LongAdder.sum đang có writer không nên dùng làm kiểm tra ngưỡng exact?

### Bài 17
Vì sao LongAdder.sum sau mọi joins cho kết quả kiểm tra cuối?

### Bài 18
Hai điều kiện của phân vùng để tổng không bỏ sót/đếm trùng?

### Bài 19
Tổng 1..1.000.000 bằng bao nhiêu?

### Bài 20
Vì sao tính partial sums local có thể giảm contention?

### Bài 21
Tại sao scan song song ghi ngay vào source cùng vòng nguy hiểm?

### Bài 22
Viết công thức một vòng scan shift d với source/target tách biệt.

### Bài 23
Sau shift1 trên [1..8], mảng là gì?

### Bài 24
Sau shift2, mảng là gì?

### Bài 25
Sau shift4, mảng là gì?

### Bài 26
Độ phức tạp work của Hillis–Steele là gì?

### Bài 27
Blelloch scan cải thiện work thế nào?

### Bài 28
Linearizability là gì?

### Bài 29
Không có data race thì có thể deadlock không?

### Bài 30
Cho hai thread giữ hai khóa ngược thứ tự rồi chờ nhau. Đây là gì?

### Bài 31
Nêu một cách giảm nguy cơ deadlock.

### Bài 32
False sharing khác lost update thế nào?

### Bài 33
Hai thread ghi hai index khác nhau của mảng có race trên cùng index không?

### Bài 34
Vì sao cần safe publication cho object chỉ đọc?

### Bài 35
Vì sao test một nghìn lần pass chưa đủ chứng minh không có race?

### Bài 36
Barrier giúp kiểm thử interleaving tốt hơn sleep ở điểm nào?

### Bài 37
Math.addExact trong worker ném lỗi thì Future.get báo thế nào?

### Bài 38
Floating-point reduction có thể khác do thứ tự cộng dù không có race không?

### Bài 39
Phân biệt safety và liveness.

### Bài 40
Bốn worker mỗi worker tăng 50.000 lần atomic cho kết quả gì?

### Đáp án gợi ý

1. Truy cập xung đột cùng biến từ các thread khác nhau, ít nhất một ghi, thiếu thứ tự HB/đồng bộ thích hợp.
2. Race condition là lỗi phụ thuộc xen kẽ ở cấp logic, data race liên quan xung đột bộ nhớ.
3. A đọc0, B đọc0, A ghi1, B ghi1.
4. Volatile không làm chuỗi đọc–sửa–ghi thành một thao tác atomic.
5. Mỗi get/set riêng atomic nhưng cặp gọi có thể xen với thread khác.
6. 1.
7. Atomicity đảm bảo một thao tác không bị chia sẻ trạng thái giữa chừng; visibility bảo đảm nhìn thấy dữ liệu qua đồng bộ.
8. Synchronized unlock/lock, volatile write/read, Thread.start/join, Future.get, latch/barrier theo contract.
9. Sleep chỉ trì hoãn; Future.get chờ task và thiết lập HB.
10. Hoàn thành task và khả năng quan sát hiệu ứng/hành động của task sau get.
11. Cờ dừng hoặc trạng thái đơn có giao thức rõ; không dùng làm increment atomic.
12. Hai biến riêng có trạng thái trung gian, phải bảo vệ cả invariant.
13. incrementAndGet là một atomic RMW; get–set là hai thao tác.
14. Đọc lại và thử lại hoặc xử lý thất bại theo giao thức.
15. Hai thread có thể đều thấy9 rồi cùng tăng thành11.
16. Nó không tạo snapshot atomic của nhiều ô trong lúc writer cập nhật.
17. Vì mọi update hoàn thành trước lần đọc tổng.
18. Các khoảng đôi một không giao nhau và hợp của chúng bao phủ input.
19. `500000500000`.
20. Mỗi task cộng vào biến riêng, chỉ gộp sau khi hoàn thành.
21. Có thể đọc dữ liệu vừa bị worker khác sửa trong cùng vòng, phá bất biến.
22. `dst[i]=src[i]` nếu i<d; ngược lại `dst[i]=src[i]+src[i-d]`.
23. `[1,3,5,7,9,11,13,15]`.
24. `[1,3,6,10,14,18,22,26]`.
25. `[1,3,6,10,15,21,28,36]`.
26. O(n log n).
27. O(n) work và O(log n) span trong mô hình song song phù hợp.
28. Thao tác có thể được xem như xảy ra tại một thời điểm logic trong khoảng gọi–trả.
29. Có, deadlock là vấn đề liveness khác với data race.
30. Deadlock.
31. Lấy khóa theo thứ tự thống nhất và giải phóng bằng finally.
32. False sharing làm tăng overhead cache; lost update làm sai dữ liệu.
33. Không nếu là hai phần tử khác nhau không có truy cập xung đột cùng ô; vẫn có thể false sharing.
34. Để reader thấy trạng thái được khởi tạo hợp lệ theo JMM.
35. Một lịch sai có thể chưa xuất hiện; phải phân tích HB/invariant.
36. Barrier ép một ranh giới thứ tự; sleep không đảm bảo ai đã làm xong gì.
37. Future.get ném ExecutionException, nguyên nhân gốc ở getCause.
38. Có; phép cộng double không kết hợp bit-for-bit do làm tròn.
39. Safety: không mất cập nhật; liveness: task không treo mãi.
40. `200000`.

---

## Ghi nhớ

Khi song song hóa một thuật toán, phải xác định **cả quan hệ phụ thuộc và quyền truy cập bộ nhớ**.

- **Data race:** xung đột bộ nhớ thiếu đồng bộ phù hợp.
- **Race condition:** lỗi cấp logic phụ thuộc xen kẽ, kể cả khi truy cập riêng lẻ atomic.
- **Atomicity:** `incrementAndGet` khác `get` rồi `set`.
- **Visibility và ordering:** dùng happens-before qua monitor, volatile, Future.get, join/latch/barrier đúng contract.
- **Giảm chia sẻ:** task sở hữu dữ liệu riêng, partial sums local, gộp sau khi hoàn thành.
- **Scan:** source chỉ đọc, target ghi không chồng lấn và chờ mọi task mỗi stage.
- **Liveness:** tránh deadlock, starvation, barrier thiếu parties.
- **Hiệu năng:** contention, false sharing và overhead phải đo riêng.

Một chương trình **không có data race chưa chắc đúng toàn bộ invariant**, và một chương trình **trả đúng một lần chưa chắc an toàn**. Tính đúng đáng tin cần đặc tả, bất biến, happens-before, phép cập nhật atomic ở phạm vi phù hợp và oracle kiểm thử độc lập.
