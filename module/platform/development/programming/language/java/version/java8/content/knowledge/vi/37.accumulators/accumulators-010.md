# Kiểm thử đúng đắn và hiệu năng của biến tích lũy dưới tranh chấp

Khi nhiều thread cùng cập nhật một số đếm hoặc một giá trị tổng hợp, chương trình có hai mục tiêu **khác nhau nhưng đều bắt buộc**:

1. **Đúng đắn (*correctness*)**: không mất cập nhật, không tính lặp, phép tích lũy đáp ứng toán học và quy tắc nhất quán mà ứng dụng cam kết.
2. **Hiệu năng (*performance*) dưới tranh chấp (*contention*)**: khi số thread cùng tác động lên một biến tăng, throughput/latency, tài nguyên CPU/bộ nhớ và chi phí đọc kết quả thay đổi thế nào?

Trong Java 8, các công cụ hiện hành thường gặp là `AtomicLong`, `LongAdder`, `LongAccumulator`, `DoubleAdder` và `DoubleAccumulator`. Các lớp này nằm trong `java.util.concurrent.atomic`, nhưng **không có cùng hợp đồng đọc, cập nhật và nhất quán**. Không thể chỉ chạy một vòng tăng trong nhiều thread rồi thấy kết quả đúng để tuyên bố mọi implementation đều đúng; càng không thể dùng một phép đo `System.nanoTime()` duy nhất để kết luận loại nào “nhanh nhất”.

Đây là bài thuộc nhóm **Biến tích lũy** với chủ đề trực tiếp **Kiểm thử đúng đắn và hiệu năng dưới tranh chấp**. Bài cung cấp phương pháp kiểm thử lặp lại được, cách phân biệt bộ đếm chính xác với số liệu giám sát, thiết kế bài đo JMH, kiểm tra contention, các lỗi thường gặp và **một chương trình Java hoàn chỉnh** để chạy. Các API trình bày có từ Java 8, **vẫn áp dụng trong Java hiện đại**; khi nhắc công cụ ngoài JDK, bài sẽ phân biệt ví dụ JDK độc lập với đoạn cần thư viện chuyên dụng.

## 1. Các lớp tích lũy và điều chúng bảo đảm

| Lớp | Phương thức cập nhật | Phương thức quan sát | Cơ chế/đặc tính chính | Phù hợp khi |
| --- | --- | --- | --- | --- |
| `AtomicLong` | `incrementAndGet`, `getAndAdd`, `updateAndGet`, `compareAndSet` | `get` | Một giá trị `long`, các phép đọc/sửa cụ thể là atomic | Cần đọc giá trị hiện tại theo hợp đồng atomic, CAS, sequence number hoặc điều phối |
| `LongAdder` | `increment`, `add(long)`, `decrement` | `sum` | Có thể phân tán cập nhật qua nhiều ô nội bộ để giảm tranh chấp; `sum` **không phải snapshot atomic** | Đếm sự kiện/metric nhiều writer, ít cần đọc đồng thời và không dùng số đọc làm điều kiện đồng bộ |
| `LongAccumulator` | `accumulate(long)` với `LongBinaryOperator` | `get` | Tích lũy bằng hàm được cung cấp, có thể phân tán cập nhật; `get` **không phải snapshot atomic** | Min/max, hàm kết hợp giao hoán/kết hợp, thống kê dưới contention |
| `DoubleAdder` | `add(double)` | `sum` | Tương tự adder cho số thực; thứ tự cộng không được bảo đảm | Metric số thực chấp nhận sai số làm tròn |
| `DoubleAccumulator` | `accumulate(double)` với `DoubleBinaryOperator` | `get` | Hàm tích lũy double, yêu cầu tính chất toán học phù hợp | Thống kê số thực có policy độ chính xác rõ ràng |

**Điểm quyết định:** `LongAdder`/`LongAccumulator` thường phù hợp **thu thập thống kê** hơn là **kiểm soát đồng bộ chính xác theo từng thao tác**. Javadoc hiện hành nói rằng khi nhiều thread cùng cập nhật một tổng, chúng thường có throughput tốt hơn `AtomicLong` dưới contention cao, **đổi lại là bộ nhớ nhiều hơn**. Đây là **kỳ vọng thiết kế**, không phải bằng chứng mọi workload đều nhanh hơn.

### Những điều không nên gán cho cả nhóm

- Không phải `LongAdder.sum()` trả một giá trị tuyến tính hóa tại một thời điểm duy nhất khi writer vẫn đang chạy.
- Không phải `LongAccumulator.get()` có semantics giống `AtomicLong.get()` trong mọi ngữ cảnh.
- Không phải `LongAdder` có API `compareAndSet` hoặc `getAndIncrement` tương đương `AtomicLong`.
- Không phải hàm bất kỳ đều an toàn khi dùng làm accumulator function; với `LongAccumulator`, thứ tự kết hợp có thể khác nhau.
- Không phải `DoubleAdder` luôn cho kết quả bitwise giống phép cộng tuần tự; floating point không kết hợp chính xác theo toán học thực.

## 2. Tranh chấp được tạo ra khi nào?

**Contention** xảy ra khi nhiều thread phải phối hợp trên một vị trí cập nhật hoặc các tài nguyên chung. Ví dụ, tám worker cùng gọi:

~~~java
atomic.incrementAndGet();
~~~

trên **cùng một `AtomicLong`**. Mỗi lời gọi cần thực hiện cập nhật nguyên tử lên cùng trạng thái. Khi nhiều core cạnh tranh, cache-coherence traffic và các lần thử lại có thể tăng, dẫn tới giảm thông lượng so với trường hợp mỗi thread cập nhật một biến độc lập.

`LongAdder` giảm điểm nóng bằng cơ chế có thể mở rộng các vị trí ghi nội bộ khi có contention. Reader gọi `sum()` sẽ cộng các giá trị đang được giữ; điều đó giải thích **trade-off**:

- **Nhiều ghi đồng thời:** có thể giảm tranh chấp ở một biến chung.
- **Đọc kết quả:** cần tổng hợp nhiều vị trí, không có snapshot atomic khi update đang diễn ra.
- **Bộ nhớ:** có thể sử dụng nhiều cấu trúc nội bộ hơn một `AtomicLong`.
- **Số thread ít:** lợi ích có thể nhỏ hoặc không đáng kể; chọn bằng benchmark workload thật.

**Không dựa vào cấu trúc cell cụ thể của một bản JDK** để viết business logic. Chỉ dựa vào hợp đồng API và đo trên runtime bạn dùng. Các chi tiết phân mảnh có thể thay đổi giữa các implementation, CPU/JDK version.

### 2.1. Đừng dùng “số thread” làm thước đo contention duy nhất

Tám thread cập nhật tám bộ đếm riêng **khác hẳn** tám thread cập nhật **cùng một bộ đếm**. Benchmark cần phân biệt:

~~~text
LOW CONTENTION:
Thread 1 -> Counter A
Thread 2 -> Counter B
Thread 3 -> Counter C

HIGH CONTENTION:
Thread 1 --\
Thread 2 ---+--> SAME COUNTER
Thread 3 --/
~~~

Cùng số worker nhưng điểm tranh chấp khác. Nếu ứng dụng thật có hàng nghìn key, mỗi key chỉ có vài cập nhật, đo một **hot key duy nhất** sẽ làm sai mô hình tải thực tế. Ngược lại, nếu một metric toàn cục là điểm nóng, benchmark per-thread counter sẽ che mất bottleneck.

## 3. Kiểm thử đúng đắn phải xác định hợp đồng trước

Trước khi chạy test, viết ra **invariant** (điều kiện bắt buộc phải đúng) của cấu trúc:

| Hợp đồng cần kiểm tra | Cách quan sát hợp lệ |
| --- | --- |
| `AtomicLong.incrementAndGet` cập nhật nguyên tử, đọc cuối sau khi mọi task xong bằng số cập nhật | Dùng `Future.get` hoặc latch bảo đảm quiescence, so `atomic.get()` với tổng dự kiến |
| `LongAdder.increment` không mất cập nhật sau khi toàn bộ writer xong | Chờ mọi writer xong, assert `adder.sum() == expected` |
| `LongAccumulator(Long::max, Long.MIN_VALUE)` chọn max các input | Chờ writer xong, assert `acc.get() == maxExpected` |
| `LongAccumulator(Long::sum, 0L)` tính tổng với phép kết hợp phù hợp | Chờ writer xong, assert `acc.get() == expectedSum` |
| `LongAdder.sum()` trong lúc update | **Không assert** rằng nó bằng “số update đã bắt đầu” hoặc “số update đã hoàn thành” tại một thời điểm toàn cục |
| `LongAdder.sumThenReset()` khi writers đã dừng | Đọc giá trị cuối kỳ rồi reset, assert sau reset bằng 0 |
| `LongAccumulator.getThenReset()` khi writers đã dừng | Đọc kết quả cuối kỳ, assert sau reset bằng identity |
| Hàm accumulation có side effect | **Thiết kế không hợp lệ** nếu dựa vào số lần callback gọi đúng một lần |

### 3.1. Tách giai đoạn viết và giai đoạn chốt số

Mẫu test đáng tin:

1. Tạo đối tượng tích lũy và tập input cố định.
2. Tạo N worker, mỗi worker thực hiện M lần cập nhật.
3. Đồng bộ thời điểm bắt đầu bằng `CountDownLatch` khi cần tạo contention.
4. Chờ **tất cả** worker hoàn thành bằng `Future.get()` hoặc cơ chế tương đương; truyền lỗi từ worker về test.
5. Chỉ **sau khi mọi writer dừng**, gọi `sum/get` để assert con số cuối.
6. Sau đó, nếu cần test reset, gọi `sumThenReset/getThenReset` khi không còn update và kiểm tra giá trị sau reset.

Nên dùng dữ liệu không tràn `long` và toán tử có kết quả xác định. Ví dụ N = 8, M = 10.000, mỗi worker tăng một lần trong một vòng: giá trị đúng cuối cùng là **80.000**, bất kể thứ tự thread chạy.

### 3.2. Tại sao `Thread.sleep` không đủ để xác nhận hoàn tất?

~~~java
new Thread(() -> adder.increment()).start();
Thread.sleep(100);
System.out.println(adder.sum());
~~~

Đây là **phản ví dụ kiểm thử**, không phải cách xác nhận task đã hoàn tất: scheduler có thể chưa cho worker chạy, và `sleep` không làm rõ lỗi worker đã ném. Thay bằng `Thread.join`, `Future.get`, `CountDownLatch` hoặc cơ chế đồng bộ có hợp đồng phù hợp.

`CountDownLatch` để cho các worker bắt đầu gần nhau **không** thay thế việc **chờ worker kết thúc**. Trong chương trình chính bên dưới, có cả barrier bắt đầu và `Future.get`.

## 4. Phản ví dụ: phép tăng của một biến long thông thường

~~~java
long counter = 0;

// Hai thread cùng làm:
// counter++;
~~~

Đây là mã giả về shared field, không phải chương trình Java hoàn chỉnh. `counter++` gồm **đọc → cộng → ghi**, không phải một thao tác nguyên tử theo hợp đồng khi nhiều thread cập nhật cùng một biến `long` bình thường.

~~~text
Giá trị ban đầu = 0

Thread A đọc 0
Thread B đọc 0
Thread A ghi 1
Thread B ghi 1

Kết quả = 1 (mất một lần tăng)
Giá trị đúng nếu cả hai tăng một lần = 2
~~~

Thêm `volatile` vào một biến long giúp về **visibility/atomicity của từng lần đọc-ghi** theo hợp đồng volatile, nhưng **không biến `counter++` thành atomic read-modify-write**. Hai thread vẫn có thể lost update. Dùng `AtomicLong.incrementAndGet()` hoặc `LongAdder.increment()` phù hợp với yêu cầu.

### 4.1. Tại sao không nên in một kết quả sai cố định?

Nếu tạo 8 thread tăng một biến thường và chạy vài trăm nghìn lần, kết quả **có thể đúng tình cờ** hoặc thấp hơn dự kiến tùy timing/JIT. Không được đưa một số “chắc chắn ra 57.000” làm expected stdout. Test concurrency cần assert **điều được Java Memory Model và API cam kết**, không ép một race data có output ổn định.

Có thể xây jcstress test để nghiên cứu các outcome hợp lệ hoặc lỗi; nhưng ngay cả stress test chạy thành công nhiều lần cũng không thay thế phân tích correctness/happens-before.

## 5. `AtomicLong`: đúng ở mức một phép cập nhật nguyên tử

~~~java
AtomicLong atomic = new AtomicLong();

long afterFirst = atomic.incrementAndGet(); // 1
long oldValue = atomic.getAndIncrement();    // 1
long current = atomic.get();                 // 2
~~~

Đây là đoạn minh họa; cần import `AtomicLong`. Các method cung cấp thao tác atomic lên giá trị đơn:

- `incrementAndGet()`: tăng nguyên tử và trả **giá trị mới**.
- `getAndIncrement()`: tăng nguyên tử và trả **giá trị cũ**.
- `getAndAdd(delta)` / `addAndGet(delta)`: cộng nguyên tử; khác giá trị trả về.
- `compareAndSet(expected, update)`: chỉ đổi nếu giá trị hiện tại khớp `expected`.
- `updateAndGet(fn)` / `accumulateAndGet(x,fn)`: cập nhật nguyên tử bằng function, function phải **side-effect-free** vì có thể được chạy lại do contention.

Nếu một yêu cầu là **“cấp số thứ tự duy nhất”**, `AtomicLong.getAndIncrement()` có thể là một primitive phù hợp trong một JVM với quản lý overflow, khởi tạo và tính bền vững rõ ràng. `LongAdder.increment()` **không trả một sequence number riêng** cho từng lời gọi.

### 5.1. Tính đúng không dừng ở một giá trị

Một `AtomicLong` chỉ bảo đảm tính nguyên tử của thao tác trên **chính biến đó**. Nếu nghiệp vụ đòi **cập nhật hai tài khoản cùng lúc**, đọc hai AtomicLong liên tiếp không tạo snapshot giao dịch hai biến. Cần transaction, locking, domain invariants hoặc mô hình dữ liệu khác.

Ví dụ:

~~~java
long a = accountA.get();
long b = accountB.get();

// Không có bảo đảm (a,b) được đọc cùng một thời điểm
// nếu writer khác vẫn chuyển tiền giữa hai biến.
~~~

Đây là pseudocode với hai AtomicLong đã khai báo ở ngoài.

### 5.2. `compareAndSet` không phải thay thế toán học phù hợp với LongAdder

Nếu cần “cấp ID liên tục không trùng”, một phép CAS/`getAndIncrement` theo giá trị đơn hợp lý. Nếu chỉ cần đếm lượt request để vẽ biểu đồ, điểm nóng của AtomicLong có thể không đáng so với `LongAdder`. Đừng thay mọi AtomicLong bằng LongAdder chỉ vì đo được throughput lớn hơn trong một microbenchmark.

## 6. `LongAdder`: chính xác sau quiescence, không atomic khi `sum` đang đọc

~~~java
LongAdder adder = new LongAdder();
adder.increment();
adder.add(4L);
adder.decrement();

System.out.println(adder.sum()); // 4 nếu không có writer khác
~~~

`LongAdder` có thể duy trì nhiều ô cập nhật để giảm contention. `sum` tổng hợp các ô ấy. Tài liệu Oracle nêu rõ:

> `sum()` **không phải snapshot atomic** khi có cập nhật đồng thời.

Điều đó nghĩa là nếu một worker đang tăng trong lúc một reader chạy `sum`, **không nên dùng kết quả làm một hàng rào điều khiển hoặc quyết định giao dịch cần một tổng chính xác tại một instant**. Những cập nhật xảy ra trong lúc `sum` đang tính có thể không được tính vào con số trả về.

### 6.1. Cách kiểm thử đúng

~~~java
for (Future<?> task : tasks) {
    task.get();
}
long finalCount = adder.sum();
assert finalCount == expected;
~~~

Đây là đoạn minh họa; `tasks`, `adder`, `expected` được tạo trước. Khi `Future.get` bảo đảm các worker đã hoàn tất và không có writer khác, kết quả `sum` chính xác cho tất cả cập nhật được thực hiện.

### 6.2. Không đọc `sum` rồi suy “đã có đúng N lần hoàn tất”

~~~java
while (adder.sum() < target) {
    // Chờ đủ cập nhật theo giá trị quan sát...
}
~~~

Đây là phản ví dụ khi `target` là điều kiện đồng bộ có ý nghĩa chính xác và các writer vẫn chạy. `sum` không cung cấp một snapshot atomic và đọc lặp để polling có thể gây lãng phí CPU. Nếu thật sự cần barrier “mọi worker đã xong”, dùng `CountDownLatch`/`Phaser`/`Future`. Nếu chỉ quan sát dashboard best-effort, `sum` phù hợp.

### 6.3. `sumThenReset()` không phải “counter delta atomic” khi writer liên tục chạy

~~~java
long lastPeriod = adder.sumThenReset();
~~~

Tài liệu nói đây tương đương về hiệu ứng với `sum()` rồi `reset()`. Khi vẫn có cập nhật, giá trị trả về **không được bảo đảm** là tổng cuối ngay trước reset và có thể có race/loss trong việc phân chia giữa các kỳ.

**Cách an toàn nếu cần số đúng theo cửa sổ kỳ:** đóng cửa sổ ghi qua cơ chế phối hợp, đợi toàn bộ cập nhật kỳ cũ hoàn tất rồi gọi `sumThenReset`; hoặc **đổi reference sang bộ đếm mới theo epoch**, bảo đảm không còn writer giữ reference cũ trước khi chốt. Việc dùng `AtomicReference<Counter>` để swap reference mà **không kiểm tra các writer đang giữ counter cũ** cũng **không đủ** để bảo đảm cửa sổ chính xác.

`reset`/`sumThenReset` rất hữu ích khi giữa các đợt có thời điểm **quiescent**, không phải primitive cho mọi hệ thống ghi liên tục.

## 7. `LongAccumulator`: test cả hàm và identity

`LongAccumulator` nhận một `LongBinaryOperator` cùng một **identity** (giá trị trung hòa). Khi contention, nó cũng có thể phân tán updates và tổng hợp theo toán tử.

Ví dụ lấy giá trị lớn nhất:

~~~java
LongAccumulator max =
    new LongAccumulator(Long::max, Long.MIN_VALUE);

max.accumulate(-9);
max.accumulate(12);
max.accumulate(3);

System.out.println(max.get()); // 12
~~~

Identity phải thỏa:

~~~text
max(Long.MIN_VALUE, x) = x  cho mọi x thuộc long
max(x, Long.MIN_VALUE) = x
~~~

Với phép cộng `Long::sum`, identity hợp lý là `0L`. Với phép nhân, identity thường là `1L` nếu chấp nhận miền số học và overflow theo `long`.

### 7.1. Associative, commutative và không side effect

Vì thứ tự kết hợp giữa các thread **không được bảo đảm**, để có kết quả dự đoán được, function nên:

- **Associative (kết hợp):** `f(f(a,b),c) = f(a,f(b,c))`.
- **Commutative (giao hoán):** `f(a,b) = f(b,a)`.
- **Side-effect-free:** không ghi file, không tăng bộ đếm khác, không tạo thanh toán, không làm I/O.
- **Identity đúng:** `f(identity,x) = x` và `f(x,identity) = x` với miền quan tâm.

Ví dụ `Long::max` và `Long::min` là những lựa chọn tốt. Các function như phép trừ hoặc nối chuỗi theo thứ tự sẽ **không** có kết quả ổn định khi bị phân tán/đổi thứ tự.

Function có thể được áp dụng lại khi update tranh chấp, nên **không đếm số lần callback function được gọi bằng một side effect**. Muốn đếm số request, cập nhật bộ đếm tương ứng độc lập và bảo đảm đúng số lần ở phía caller.

### 7.2. `get()` và `getThenReset()`

`LongAccumulator.get()` giống `LongAdder.sum()` ở giới hạn snapshot: nếu các update vẫn đang diễn ra, nó không tạo giá trị atomic tại một mốc chung. `reset()` đặt lại identity; `getThenReset()` phù hợp khi đã quiescent.

~~~java
LongAccumulator max =
    new LongAccumulator(Long::max, Long.MIN_VALUE);

max.accumulate(10);
long beforeReset = max.getThenReset();
// beforeReset == 10 (không có writer khác)
// max.get() == Long.MIN_VALUE
~~~

Nếu identity chọn sai (chẳng hạn `0` cho max khi các input đều âm), test có thể “đúng” cho input dương mà sai hoàn toàn với dữ liệu thực. Luôn test **giá trị âm, 0, identity và ranh giới** khi hàm hỗ trợ.

### 7.3. Overflow và tính toán long

Java `long` có phạm vi hữu hạn. Phép cộng `long` tràn sẽ wrap theo số học 64-bit; bản thân `LongAdder` hay `AtomicLong` **không tự ném ArithmeticException** khi tổng vượt `Long.MAX_VALUE`.

Nếu một hệ thống phải tính **số tiền** hoặc tổng rất lớn với yêu cầu không tràn, đừng chỉ chọn một adder vì throughput. Cần mô hình miền phù hợp (ví dụ `BigInteger`/decimal/partitioning và kiểm tra giới hạn), khả năng báo overflow và transaction nhất quán.

## 8. `DoubleAdder`/`DoubleAccumulator`: correctness bao gồm sai số số thực

Với `double`, phép cộng không kết hợp chính xác do làm tròn IEEE-754:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

// (a + b) + c = 1.0
// a + (b + c) có thể bằng 0.0 do làm tròn.
~~~

`DoubleAdder` có thể thay đổi thứ tự cộng giữa các vị trí cập nhật, nên **không có bảo đảm mọi run trả cùng một bit pattern** hoặc giống tổng tuần tự với thứ tự cố định. Javadoc cảnh báo các giá trị có độ lớn rất khác nhau có thể khiến kết quả kém ổn định về số.

**Khi test DoubleAdder:**

1. Chọn input hợp lý và xác định sai số chấp nhận được theo nghiệp vụ.
2. Nếu so kết quả, so với tolerance/ULP phù hợp thay vì `==` bitwise cho mọi bộ dữ liệu.
3. Test cả số âm/dương, giá trị lớn/nhỏ, NaN/Infinity nếu miền dữ liệu cho phép.
4. Không dùng kết quả floating point để chốt số tiền nếu yêu cầu tuyệt đối chính xác; cân nhắc số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` theo domain.
5. Với `DoubleAccumulator`, function cũng cần xét associativity/commutativity và identity theo miền dữ liệu; không bỏ qua chính sách NaN.

**Quan trọng:** tolerance không thay thế kiểm thử **không mất cập nhật**. Khi miền dữ liệu có thể dùng nguyên `long` và tổng dưới giới hạn, test exact equality là tốt hơn. Chỉ dùng tolerance khi bản chất số thực thật sự cần.

## 9. Phương pháp tạo contention có kiểm soát

Một bài kiểm thử concurrency thường có ít nhất ba pha:

~~~text
MAIN:    tạo shared state -> submit N tasks -> [ready.await]
WORKERS: khởi tạo ----------> ready.countDown -> [start.await]
MAIN:    start.countDown
WORKERS: N lần cập nhật cùng counter -> kết thúc
MAIN:    Future.get cho tất cả -> assert trạng thái cuối
~~~

`CountDownLatch ready` giúp biết các task đã đến điểm bắt đầu. `start` cho phép chúng đi tiếp gần nhau hơn để tăng xác suất contention. `Future.get` giữ exception từ worker, nên nếu một task ném lỗi, test thất bại rõ thay vì chỉ nhìn con số cuối.

**Lưu ý thiết kế:** nếu bạn có 8 worker nhưng executor chỉ có 2 thread, `ready.await()` có thể deadlock vì 6 task còn lại chưa được bắt đầu. Trong ví dụ hoàn chỉnh, pool có **số worker bằng số task** để tránh trường hợp này. Trong production không nên tạo pool kiểu này cho hàng nghìn request; đây là test được kiểm soát.

### 9.1. Test isolation

Mỗi phép đo hoặc case kiểm thử cần **counter mới**, không dùng kết quả của run trước. Tránh cho một JUnit test sau đọc biến `static` đã bị test trước tăng. Nếu dùng reusable fixture, reset chỉ ở trạng thái không có writer.

### 9.2. Không chỉ kiểm tra “không có exception”

Một race lost update có thể chạy hàng trăm lần mà không xuất hiện trong test ngắn. Kiểm tra invariant định lượng, thử nhiều cấu hình số thread và phân tích memory model. Nếu thật sự nghiên cứu cạnh tranh lệnh ở mức thấp, dùng công cụ chuyên dụng **jcstress** của OpenJDK, có outcome model và nhiều schedule/lặp; ngay cả vậy cũng phải xác định outcomes hợp lệ bằng hợp đồng Java.

### 9.3. Chú ý bug trong test harness

Kiểm thử có thể sai ngay cả khi thư viện đúng:

- Test đọc `sum` trước khi writer thực sự dừng.
- Test dùng `Thread.sleep` thay vì barrier.
- Test nuốt exception của worker hoặc bỏ qua `Future.get`.
- Test reset trong khi worker vẫn ghi rồi assert tổng cuối.
- Test dùng random seed không được ghi lại, khiến fail khó tái hiện.
- Test dùng `AtomicInteger` làm expected nhưng chính expected không được cập nhật đầy đủ.
- Test có side effect trong `LongAccumulator` function rồi đếm callback không đúng.
- Test tạo hàng nghìn thread trên máy ít core, đo chủ yếu overhead scheduling.

## 10. Chương trình Java hoàn chỉnh: correctness khi nhiều thread cùng cập nhật

Chương trình sau dùng **`AtomicLong`, `LongAdder`, `LongAccumulator` và `ConcurrentHashMap<String,LongAdder>`** trong cùng một bộ test. Nó kiểm tra các giá trị **chỉ sau khi mọi writer đã hoàn tất**, không đặt assertion sai lên `sum()` đang bị cập nhật.

Lưu thành **`AccumulatorContentionCorrectnessDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public final class AccumulatorContentionCorrectnessDemo {
    private static final int WORKERS = 8;
    private static final int UPDATES_PER_WORKER = 10_000;

    private AccumulatorContentionCorrectnessDemo() {
    }

    public static void main(String[] args) throws Exception {
        final AtomicLong atomic = new AtomicLong();
        final LongAdder adder = new LongAdder();
        final LongAccumulator max =
                new LongAccumulator(Long::max, Long.MIN_VALUE);
        final LongAccumulator additive =
                new LongAccumulator(Long::sum, 0L);

        final ConcurrentHashMap<String, LongAdder> frequencies =
                new ConcurrentHashMap<>();

        ExecutorService pool =
                Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready =
                new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int w = 0; w < WORKERS; w++) {
                final int worker = w;

                Callable<Void> task = () -> {
                    ready.countDown();
                    start.await();

                    for (int i = 0; i < UPDATES_PER_WORKER; i++) {
                        atomic.incrementAndGet();
                        adder.increment();
                        additive.accumulate(1L);

                        long candidate =
                                (long) worker * UPDATES_PER_WORKER + i;
                        max.accumulate(candidate);

                        String key =
                                worker % 2 == 0 ? "even" : "odd";
                        frequencies.computeIfAbsent(
                                key, k -> new LongAdder())
                                .increment();
                    }
                    return null;
                };

                futures.add(pool.submit(task));
            }

            // Chỉ thả start khi cả 8 task đã sẵn sàng.
            ready.await();
            start.countDown();

            // Chờ tất cả và truyền exception nếu có.
            for (Future<Void> future : futures) {
                future.get();
            }

            final long expected =
                    (long) WORKERS * UPDATES_PER_WORKER;

            if (atomic.get() != expected
                    || adder.sum() != expected
                    || additive.get() != expected
                    || max.get() != expected - 1) {
                throw new AssertionError("wrong final accumulation");
            }

            System.out.println("expected=" + expected);
            System.out.println("atomic=" + atomic.get());
            System.out.println("adder=" + adder.sum());
            System.out.println("accumulatorSum=" + additive.get());
            System.out.println("accumulatorMax=" + max.get());
            System.out.println("even="
                    + frequencies.get("even").sum());
            System.out.println("odd="
                    + frequencies.get("odd").sum());

            // CHỈ reset SAU khi tất cả writer đã dừng.
            long beforeAdderReset = adder.sumThenReset();
            long beforeMaxReset = max.getThenReset();
            long beforeAddReset = additive.getThenReset();

            System.out.println("adderBeforeReset="
                    + beforeAdderReset);
            System.out.println("adderAfterReset=" + adder.sum());
            System.out.println("maxBeforeReset="
                    + beforeMaxReset);
            System.out.println("maxAfterReset=" + max.get());
            System.out.println("addBeforeReset="
                    + beforeAddReset);
            System.out.println("addAfterReset="
                    + additive.get());

            long previous = atomic.getAndIncrement();
            System.out.println("atomicPrevious=" + previous);
            System.out.println("atomicNow=" + atomic.get());

            // Thay vì sum() trong lúc ghi, test được chốt
            // tại thời điểm writer đã hoàn tất.
            System.out.println("correctnessPassed=true");
        } finally {
            // Cũng thả latch nếu code thay đổi và có lỗi
            // xảy ra trước lệnh start.countDown bình thường.
            start.countDown();
            pool.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 AccumulatorContentionCorrectnessDemo.java
java AccumulatorContentionCorrectnessDemo
~~~

**Đầu ra kỳ vọng (không phụ thuộc thứ tự thread hoàn tất):**

~~~text
expected=80000
atomic=80000
adder=80000
accumulatorSum=80000
accumulatorMax=79999
even=40000
odd=40000
adderBeforeReset=80000
adderAfterReset=0
maxBeforeReset=79999
maxAfterReset=-9223372036854775808
addBeforeReset=80000
addAfterReset=0
atomicPrevious=80000
atomicNow=80001
correctnessPassed=true
~~~

### Giải thích đầu ra

1. **`expected=80000`:** 8 worker × 10.000 update = 80.000. Bộ test không phụ thuộc tốc độ thực thi của từng worker.
2. **`atomic=80000`:** `incrementAndGet` trên cùng một `AtomicLong` không làm mất cập nhật.
3. **`adder=80000`:** sau khi `Future.get` trả thành công cho **mọi writer**, `sum` được gọi trong quiescence và phải khớp 80.000.
4. **`accumulatorSum=80000`:** `LongAccumulator(Long::sum,0L)` có identity đúng và cộng đủ 80.000 lần `1L`.
5. **`accumulatorMax=79999`:** mỗi worker ghi candidate từ `worker*10000` đến `worker*10000+9999`; giá trị lớn nhất là 79.999.
6. **`even=40000` và `odd=40000`:** bốn worker có index chẵn và bốn worker có index lẻ, mỗi worker 10.000 lượt. `ConcurrentHashMap.computeIfAbsent` tạo adder theo khóa nếu chưa tồn tại.
7. **`adderBeforeReset=80000`, `adderAfterReset=0`:** reset thực hiện khi mọi writer đã dừng, tránh race.
8. **`maxBeforeReset=79999`, `maxAfterReset=Long.MIN_VALUE`:** bộ tích lũy max trở lại identity thay vì mặc định 0.
9. **`addBeforeReset=80000`, `addAfterReset=0`:** bộ tích lũy phép cộng trở lại identity `0L`.
10. **`atomicPrevious=80000` và `atomicNow=80001`:** `AtomicLong.getAndIncrement` trả giá trị cũ — đây là thông tin mỗi update mà `LongAdder.increment` không cung cấp.
11. Không in `Thread.currentThread().getName()` hoặc số phép `sum()` trong lúc writer chạy, nên output được thiết kế ổn định. Đây là **correctness test**, không đo số lần LongAdder nhanh hơn AtomicLong.

**Giới hạn test:** một chương trình pass không chứng minh không thể có bug ở mọi lịch scheduling. Bằng chứng lớn hơn là hợp đồng Java cộng với test nhiều cấu hình và mô hình memory. Ví dụ này không đưa ra kết quả benchmark hiệu năng vì tốc độ phụ thuộc CPU, JIT, GC, tải nền và kiểu contention.

## 11. Kiểm thử đọc giữa chừng: điều gì được phép assert?

Giả sử một reader lấy mẫu `adder.sum()` khi writer đang tăng. **Không được** áp dụng invariant:

~~~java
// Phản ví dụ về ASSERT sai:
assert adder.sum() == completedOperations.get();
~~~

Nếu các thao tác của `completedOperations` và `adder` không được cập nhật như **một giao dịch**, số đọc có thể không trùng do thời điểm quan sát. Thêm nữa, chính `sum()` không tạo snapshot atomic từ các ô tích lũy.

**Một cách test đúng hơn** là tách:

- Trong lúc update: kiểm tra gọi `sum` không ném lỗi, kết quả trong miền hợp lý của workload cụ thể; **không áp chuẩn một con số instant**.
- Sau quiescence: assert kết quả chính xác bằng số lượng cập nhật đã thực hiện.
- Với business cần atomic read: sử dụng một primitive có hợp đồng phù hợp như `AtomicLong.get`, và chỉ dùng nó cho một giá trị đơn có ý nghĩa đọc nguyên tử.
- Với business nhiều biến: cần transaction/snapshot hoặc giao thức đồng bộ đa biến, không chỉ thay long adder bằng AtomicLong.

### 11.1. Đọc kết quả sau `Future.get` có ý nghĩa gì về bộ nhớ?

Trong Java concurrency, các hành động trong tác vụ xảy ra trước khi kết quả task được lấy thành công qua `Future.get()` theo memory-consistency effects của `Future`. Khi tất cả `Future.get` đã hoàn tất và không có writer khác, test có một ranh giới rõ để quan sát trạng thái cuối.

**Không nhầm:** `Thread.sleep(100)` không tạo quan hệ tương đương để chứng minh tất cả công việc đã xong.

### 11.2. Nếu callback ném exception thì sao?

Một future có thể hoàn thành bằng lỗi. `Future.get` sẽ ném `ExecutionException`; test phải fail hoặc xử lý rõ lỗi này thay vì tiếp tục assert con số cuối trong trạng thái chưa đầy đủ. Nếu dùng `CompletableFuture.join`, lỗi có thể được bọc trong `CompletionException`. Đừng catch mọi exception rồi mặc định tính tổng là hợp lệ.

## 12. Chuyển từ correctness sang performance: hai thí nghiệm khác nhau

**Correctness test** tìm xem các giá trị có đúng không theo API. **Benchmark** đo chi phí/throughput khi các kết quả được bảo đảm đúng và workload đã được định nghĩa.

Một benchmark chưa đáng tin nếu:

- Không có warmup cho JIT.
- Chỉ đo một lần.
- Dùng `System.currentTimeMillis()` cho vòng rất ngắn.
- Tạo object/thread/Executor bên trong vòng đo rồi coi đó là chi phí cập nhật counter.
- Không tiêu thụ/kết nối kết quả khiến JIT có thể tối ưu bỏ công việc.
- So sánh hai implementation với số worker hoặc số update khác nhau.
- Đo benchmark khi có writer/reader từ ứng dụng khác chen vào.
- Không kiểm soát GC, CPU frequency, số core, hyperthreading, nhiệt độ, power management.
- Đặt cả AtomicLong và LongAdder vào **cùng vòng loop**, khiến chúng cùng tranh chấp và không tách được thời gian.

**JMH** (*Java Microbenchmark Harness*) của OpenJDK là công cụ hiện hành để xây benchmark JVM. Nó cung cấp cách quản lý warmup, measurement iterations, forks, thread groups, state scopes, modes và aggregation tốt hơn phép stopwatch thủ công. JMH không thuộc JDK tiêu chuẩn: muốn chạy cần thêm dependency/plugin của dự án JMH.

## 13. Benchmark bằng JMH: thiết kế có nghĩa cho contention

### 13.1. Chọn thứ cần đo

Một số câu hỏi hợp lệ:

1. Với **1 writer**, throughput cập nhật `AtomicLong` so với `LongAdder` có khác đáng kể không?
2. Với **2/4/8/16 writers cùng cập nhật một object**, throughput thay đổi thế nào?
3. Nếu **80% thời gian là ghi, 20% là đọc** có chênh lệch so với 100% ghi không?
4. `LongAdder.sum()` tốn thêm chi phí thế nào khi số vị trí nội bộ tăng?
5. Với **một nghìn hot keys** và `ConcurrentHashMap<String,LongAdder>`, tốc độ khác trường hợp một hot key ra sao?
6. Khi threads vượt số core, có thêm throughput hay chỉ tăng queueing/context switches?
7. Allocation/memory footprint có tăng không khi contention khiến adder mở rộng?

Không bắt đầu bằng kết luận “LongAdder nhanh gấp X lần”; hãy đặt một giả thuyết rồi đo trên workload cụ thể.

### 13.2. Một skeleton JMH để làm thí nghiệm

Mã dưới đây là **ví dụ riêng cho dự án có JMH**, **không phải class biên dịch chỉ bằng javac thuần JDK**: các annotation `org.openjdk.jmh.annotations` thuộc thư viện JMH và cần annotation processor của JMH. Nó cho thấy cách giữ counter chung **trong một nhóm thread** và đo mỗi loại riêng:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class AccumulatorJmh {

    @State(Scope.Group)
    public static class GroupCounters {
        AtomicLong atomic;
        LongAdder adder;

        @Setup(Level.Iteration)
        public void setup() {
            atomic = new AtomicLong();
            adder = new LongAdder();
        }
    }

    @Benchmark
    @Group("atomicCounter")
    @GroupThreads(4)
    public void atomicIncrement(GroupCounters c) {
        c.atomic.incrementAndGet();
    }

    @Benchmark
    @Group("stripedCounter")
    @GroupThreads(4)
    public void longAdderIncrement(GroupCounters c) {
        c.adder.increment();
    }
}
~~~

**Ý nghĩa của thiết kế:**

- `@State(Scope.Group)` khiến nhiều worker trong cùng benchmark group cùng dùng một object counter, thật sự tạo contention trên một key.
- `@Group("atomicCounter")` và `@Group("stripedCounter")` dùng nhóm khác nhau; không cố tình cho hai phép cập nhật cạnh tranh lẫn nhau trong cùng một phép đo.
- `@GroupThreads(4)` làm nhóm có bốn thread gọi phương thức tương ứng.
- `@Setup(Level.Iteration)` tạo counter mới **trước** vòng đo, không reset trong mỗi invocation.
- `@Warmup`/`@Measurement`/`@Fork` tạo nhiều giai đoạn/fork để giảm phụ thuộc một lần khởi động JIT.
- `Mode.Throughput` đánh giá **số operations mỗi đơn vị thời gian**, không tự nói p99 latency của từng thao tác.
- `AtomicLong.incrementAndGet` có kiểu trả long nhưng trong benchmark chỉ dùng side effect lên state; `LongAdder.increment` trả void. Khi cần kết quả value-return, đó là một loại workload khác nên đo riêng.

Chạy theo hướng dẫn chính thức từ <https://github.com/openjdk/jmh>: tạo **Maven JMH project** với archetype/dependencies và annotation processing phù hợp, đặt class vào package nguồn benchmark, build bằng Maven rồi chạy benchmark jar. Không chạy đoạn trên bằng `javac AccumulatorJmh.java` khi chưa thêm JMH vào classpath.

**Cảnh báo:** một nhóm bốn writer chưa đủ đại diện mọi mức contention. Để so 1, 2, 8, 16 threads, hãy tạo các nhóm thử nghiệm tương ứng hoặc cấu hình JMH theo hướng dẫn group semantics, giữ nguyên workload và report đầy đủ điều kiện.

### 13.3. Đừng dùng correctness test để kết luận tốc độ

Trong `AccumulatorContentionCorrectnessDemo`, mỗi task đồng thời cập nhật bốn loại counter và một map tần suất; điều đó **có chủ ý** để test đúng đắn, **không phải** benchmark công bằng giữa các cấu trúc. Nếu lấy thời gian chạy toàn chương trình đó để so AtomicLong với LongAdder, bạn đã trộn quá nhiều yếu tố.

Một benchmark công bằng phải đo các implementation riêng với state/worker count/operation mix được kiểm soát.

## 14. Các cấu hình benchmark quan trọng

| Biến độc lập | Các mức nên thử | Vì sao |
| --- | --- | --- |
| Số threads | 1, 2, 4, 8, bằng và lớn hơn số core | Contention và scheduling tăng không tuyến tính |
| Số counters | Một hot key, ít hot keys, nhiều key phân tán | Ảnh hưởng đến điểm tranh chấp |
| Read/write ratio | 100% write; 95/5; 50/50 | LongAdder có write/read trade-off |
| Kiểu phép toán | `increment`, `add(delta)`, `max`, các hàm khác | Chi phí function khác nhau |
| Cường độ tính toán bao quanh | Chỉ cập nhật; tính toán trước/sau | Trong app thật counter chỉ là một phần chi phí |
| Kiểu executor/threads | Platform thread; cấu hình khác nếu cần | Scheduling ảnh hưởng throughput |
| JDK/CPU | Nhiều JDK được hỗ trợ, nhiều kiến trúc CPU | Kết quả benchmark phụ thuộc implementation/hardware |
| Thời gian warmup | Đủ để JIT/GC ổn định | Tránh đo chủ yếu startup |
| Kích thước dữ liệu/map | Nhỏ, trung bình, lớn | Ảnh hưởng cache locality và memory |
| Allocation/GC | Đo và ghi nhận | LongAdder có thể dùng thêm bộ nhớ |

Chạy từng phương án đủ lần để đánh giá biến thiên. Báo cáo nên có **JDK vendor/version, CPU model/core count, OS, bộ nhớ, JMH version, flags, số forks, số iteration, threads**, và giá trị mean/score/error theo JMH. Không dùng các kết quả đo từ một laptop bận làm định mức cứng cho production trên một kiến trúc khác.

### 14.1. Throughput khác latency

- **Throughput:** số thao tác hoàn tất mỗi giây; thích hợp để đánh giá mức tải lớn.
- **Latency trung bình:** thời gian một thao tác; có thể bị ảnh hưởng bởi scheduling và GC.
- **Tail latency:** p95/p99 cần đo ở đúng tầng có queueing và workload thực; throughput microbenchmark không tự trả lời p99 request.
- **CPU sử dụng:** throughput cao hơn có thể đánh đổi CPU hoặc năng lượng; theo dõi tài nguyên.
- **Bộ nhớ:** striped counters có thể tăng footprint dưới contention; cần đo thêm nếu có hàng triệu counter.

Kết luận tốt có dạng “ở 8 threads cùng tăng một counter trên JDK/CPU X, LongAdder có throughput cao hơn trong benchmark Y nhưng chi phí đọc `sum` và bộ nhớ tăng”, **không đưa ra số liệu nếu chưa đo**.

## 15. Những bẫy benchmark thường gây kết luận sai

### 15.1. Đo cả việc tạo thread và khởi tạo counter

~~~java
long started = System.nanoTime();
ExecutorService pool = Executors.newFixedThreadPool(8);
// ... submit và đợi ...
long elapsed = System.nanoTime() - started;
~~~

Đây là **mã minh họa**, không phải benchmark so riêng `AtomicLong` và `LongAdder`; thời gian chứa cả thread startup, queueing, warmup, code biên và GC. Có thể dùng làm bài đo end-to-end **nếu** đó thực sự là chi phí người dùng quan tâm, nhưng không dùng làm “nanoseconds/op của increment”.

### 15.2. Đo `adder.sum()` bên trong vòng increment khi so update throughput

Nếu test `LongAdder.increment(); LongAdder.sum();` trong mỗi lần lặp nhưng test AtomicLong chỉ gọi `incrementAndGet()`, bạn đã thay đổi thao tác được đo. Hãy so **update với update**, **read với read** và một workload mixed đọc/ghi riêng.

### 15.3. Dùng global mutable state không được cô lập giữa forks

Nếu benchmark nhận trạng thái từ một singleton đã bị run trước cập nhật, số liệu có thể không lặp lại. Dùng `@State` và `@Setup` đúng scope/lifecycle, không reset trong mỗi operation nếu app thật không làm vậy.

### 15.4. Nhầm có nhiều thread với cùng chia sẻ một object

Trong JMH, `@State(Scope.Thread)` tạo state riêng mỗi thread; nếu mục tiêu contention **trên cùng một counter**, `Scope.Thread` có thể làm mất contention. Dùng `Scope.Group` hoặc `Scope.Benchmark` phù hợp, và xác nhận các worker **thật sự chạm cùng object**.

### 15.5. Kết luận “không có contention” từ một run nhanh

JIT, GC, CPU affinity, turbo boost và tải nền có thể làm run bất thường. Cần warmup/fork/multiple measurements, xem error bar và quy mô effect, không chỉ nhìn một số duy nhất.

### 15.6. Không đo chi phí đọc, reset và vòng đời

Một dịch vụ có thể cập nhật metric nhanh nhưng phải xuất snapshot mỗi 10 ms. Nếu mỗi lần `sum` tốn thêm thời gian và không atomic, hãy tính **giá của yêu cầu đọc**. Nếu cần reset window, phải có quiescent protocol; throughput increment cao không giải quyết correctness của reset.

### 15.7. Tối ưu hóa biến mất hoặc thay nghĩa phép đo

Một benchmark bị JIT tối ưu bỏ work, hoặc dùng kết quả không được tiêu thụ theo cách hợp lệ, có thể cho số liệu phi thực tế. Với JMH, giữ side effect vào state quan sát được, hoặc dùng `Blackhole` khi thích hợp để tiêu thụ kết quả; tránh đo một constant computation không phản ánh production.

### 15.8. So sánh thao tác có ngữ nghĩa khác nhau

`AtomicLong.getAndIncrement()` vừa **tăng** vừa **trả giá trị trước đó**, cho phép cấp sequence number. `LongAdder.increment()` **chỉ tăng** và không cung cấp số ID riêng. Nếu benchmark chỉ thấy LongAdder nhanh hơn mà thay nó vào nơi cần sequence, đó là **sai chức năng**, dù throughput cao hơn.

## 16. Kiểm thử reset và windowed metrics

Một số hệ thống muốn mỗi phút xuất số request và reset counter:

~~~java
long perMinute = requests.sumThenReset();
~~~

Nếu writer vẫn đang tăng, đây là **best-effort** theo hợp đồng, **không phải phân chia chính xác từng request theo minute boundary**.

### 16.1. Khi nào best-effort đủ?

Ví dụ dashboard có tính chất quan sát, số đếm mỗi phút được dùng để xem xu hướng; sai khác nhỏ lúc rollover có thể chấp nhận theo SLA monitoring. Khi đó `sumThenReset` trong một hệ thống có writer liên tục vẫn cần được mô tả đúng là **racy và không có guarantee exact**, không dùng làm cơ sở tính cước hay phạt.

### 16.2. Khi nào cần chính xác?

Nếu hệ thống tính tiền dựa theo từng request hoặc chốt hạn mức cứng, cần **một điểm linearization/epoch** rõ ràng. Các cách có thể gồm:

1. Đóng nhận update của kỳ cũ và **chờ tất cả writer đã submit vào kỳ cũ hoàn thành**.
2. Sau quiescence, đọc `sumThenReset` của counter cũ, ghi kết quả có audit.
3. Chuyển writer sang epoch mới theo cơ chế được kiểm chứng là không có update muộn vào epoch cũ.
4. Nếu không thể quiesce, dùng transactional event log/sequence hoặc mô hình snapshot được điều phối thay vì tự coi `LongAdder` có thể chốt exact.

**Cẩn thận `AtomicReference<LongAdder>`:** chỉ swap reference bằng CAS chưa đủ nếu một worker đã đọc reference cũ rồi bị pause; sau swap nó có thể tiếp tục update adder cũ đã chốt. Cần phối hợp inflight writers/epoch handoff.

### 16.3. Test reset đúng cách

Sau khi đợi `Future.get` toàn bộ writer, assert:

~~~java
long period = adder.sumThenReset();

if (period != expected || adder.sum() != 0) {
    throw new AssertionError("period mismatch");
}
~~~

Đây là **mã minh họa**, `adder/expected` được tạo trước. Nếu writer khác vẫn đang ghi, phép assert không còn được bảo đảm. Test phải mô tả rõ cửa sổ **không update**.

## 17. Frequency map: thêm một lớp contention trên khóa

Javadoc `LongAdder` đưa ví dụ hiện hành để tạo frequency map:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies =
    new ConcurrentHashMap<>();

frequencies
    .computeIfAbsent("error", k -> new LongAdder())
    .increment();
~~~

`computeIfAbsent` cho phép tạo value cho key nếu chưa có theo thao tác nguyên tử của map. Sau đó `increment` là thao tác của adder được lưu dưới key.

### 17.1. Test đúng khi nhiều thread cùng đếm một key

- Không xóa thay value của key giữa lúc worker vẫn giữ reference adder nếu yêu cầu cuối kỳ bao gồm tất cả lượt.
- Sau khi tất cả worker đã dừng, dùng `frequencies.get("error").sum()` để so số lượt đã tăng.
- Không khẳng định `sum` giữa chừng là snapshot exact của mọi update.
- Nếu tạo các key khác nhau, kiểm tra từng key và tổng toàn bộ sau quiescence.
- Nếu cần atomic “update map và snapshot toàn map”, `ConcurrentHashMap` cùng adder không cung cấp transaction nhiều key.

### 17.2. Khi key thay đổi hoặc bị remove

Một worker có thể lấy reference adder, writer khác xóa mapping, worker cũ vẫn `increment` reference không còn nằm trong map. Khi đó một lượt cập nhật có thể không xuất hiện trong các lần đọc map sau. Nếu nghiệp vụ cần accounting exact, không được xóa/swap value trong khi còn writer tới reference cũ mà không có cơ chế handoff.

Frequency map là mẫu rất hữu ích cho **metrics**, nhưng không đồng nghĩa hệ thống event accounting bền vững qua crash hoặc phân tán qua nhiều JVM.

## 18. Từ stress test đến jcstress: dùng công cụ đúng câu hỏi

Một vòng tạo 8 thread và cập nhật 80.000 lần có thể phát hiện lost update trong code tự viết, nhưng không đủ để “chứng minh” mọi tương tác memory model. **jcstress** của OpenJDK là công cụ để nghiên cứu tính đúng của concurrency trên JVM, thư viện và hardware, bằng cách chạy nhiều tác nhân với shared state và **thu thập outcome**.

### 18.1. Một outcome model minh họa

Giả sử hai actor đều chạy `counter++` trên biến không đồng bộ và arbiter đọc kết quả. Tùy memory model và cách thiết kế test, có thể quan sát một giá trị thấp hơn mong đợi. Khi thay bằng `AtomicLong.incrementAndGet`, nếu mỗi actor tăng một lần và arbiter đọc sau khi cả hai actor hoàn thành, trạng thái cuối mong đợi là 2. Nhưng để dùng jcstress đúng, phải khai báo actors, arbiter, state và outcomes theo API của dự án jcstress, không tự biến ví dụ pseudo này thành một test đã được harness xác nhận.

### 18.2. Khi nào nên dùng jcstress?

- Kiểm tra custom CAS loop, cache publication, double-checked locking hoặc concurrent state machine.
- Nghiên cứu các kết quả hợp lệ của racy code.
- Đối chiếu những điều chắc chắn/không chắc chắn theo Java Memory Model.
- Phát hiện lỗi trong một accumulator hoặc utility tự viết, thay vì kiểm tra lại từng implementation chuẩn đã có hợp đồng.

Xem dự án chính thức <https://github.com/openjdk/jcstress> và các samples. Đừng gọi một bài test JUnit đơn lẻ là “jcstress” nếu nó không dùng harness đó. **JMH đo tốc độ; jcstress khám phá các outcome concurrency; unit test xác minh chức năng**, ba công cụ bổ sung lẫn nhau.

### 18.3. Test performance không thay thế test correctness

Một implementation racy có thể nhanh hơn rất nhiều vì **làm thiếu việc** (lost updates). Trước khi so throughput, xác minh rằng các implementation thực hiện đúng **cùng số cập nhật theo cùng semantics**. Đừng xếp hạng một bộ đếm sai lên đầu chỉ vì nó đạt ops/s lớn.

## 19. Lựa chọn cấu trúc theo yêu cầu nghiệp vụ

| Nhu cầu | Lựa chọn cân nhắc | Vì sao |
| --- | --- | --- |
| Số thứ tự tăng duy nhất trong một process | `AtomicLong.getAndIncrement()` | Trả được giá trị cũ atomically |
| Bộ đếm request toàn cục để dashboard | `LongAdder.increment()` | Được tối ưu cho nhiều cập nhật và đọc ít; đọc best-effort under writes |
| Bộ đếm số request theo endpoint | `ConcurrentHashMap<String,LongAdder>` | Phân tán thêm theo key |
| Max latency đã quan sát (số nguyên) | `LongAccumulator(Long::max, Long.MIN_VALUE)` | Function max phù hợp luật kết hợp |
| Tổng số thực dùng cho giám sát | `DoubleAdder` | Chấp nhận rounding/không snapshot |
| Tổng tiền cần đối soát tuyệt đối chính xác | Thiết kế decimal/transaction/ledger phù hợp | Không đánh đổi tính đúng chỉ để tăng throughput |
| Thông lượng update cao và cần chốt số đúng theo phút | Counter + epoch/quiescence protocol hoặc event log | `sumThenReset` không atomic dưới writes |
| Tính tổng của nhiều key cần một snapshot T | Cơ chế snapshot/transaction nhiều bản ghi | Atomic theo một counter không tạo transaction nhiều key |
| Cập nhật bằng function có side effect | Tách side effect khỏi hàm accumulator | Function có thể được áp dụng lại khi tranh chấp |

**Không có “bộ đếm tốt nhất” cho mọi trường hợp.** Điều đúng nhất là lớp có **ngữ nghĩa đáp ứng SLA và invariant**, sau đó mới dùng JMH đo xem lựa chọn nào đạt hiệu năng mục tiêu.

## 20. Danh sách lỗi phổ biến

### Lỗi 1 — Dùng `LongAdder.sum()` làm CAS

`LongAdder` không cung cấp `compareAndSet`/`getAndIncrement`. Nếu cần một giá trị atomic để quyết định vượt hạn mức đúng từng giao dịch, chọn thiết kế có primitive phù hợp.

### Lỗi 2 — So sum giữa chừng với tổng số lượt đã submit

Task đã được submit không có nghĩa nó đã chạy; `sum` cũng không tạo atomic snapshot dưới concurrent updates. Chỉ so số tổng sau quiescence, hoặc dùng hệ đồng bộ riêng.

### Lỗi 3 — Quên lỗi từ worker

`ExecutorService.submit` trả future có thể chứa exception; không gọi `Future.get` sẽ khiến test bỏ sót lỗi. Kết quả count thấp chưa chắc do LongAdder, có thể vì task thất bại.

### Lỗi 4 — Dùng sleep làm barrier

`Thread.sleep` không chứng minh task bắt đầu/xong. Dùng `CountDownLatch`, `Future.get`, `Phaser`, hoặc join tùy trường hợp.

### Lỗi 5 — Reset khi vẫn có writer

`sumThenReset/getThenReset` không phân chia exact window khi writer cập nhật đồng thời. Cần quiescence hoặc epoch handoff.

### Lỗi 6 — Chọn identity sai cho max/min

`LongAccumulator(Long::max,0L)` sai nếu mọi input có thể âm. Dùng `Long.MIN_VALUE` cho max và `Long.MAX_VALUE` cho min khi miền là toàn bộ long.

### Lỗi 7 — Dùng phép không giao hoán/kết hợp

Phép trừ hoặc function phụ thuộc thứ tự không phù hợp mô hình phân mảnh. Chọn function phù hợp và side-effect-free.

### Lỗi 8 — Function side effect trong CAS/accumulate

Function có thể được gọi lại; không ghi tiền, gửi message hay increment một counter bên ngoài từ bên trong callback function nếu dựa vào “đúng một lần”.

### Lỗi 9 — Nhầm `LongAdder` với nguyên tử một giá trị khi đọc

Adder bảo đảm các cập nhật phù hợp và tổng chính xác khi không có concurrent writers; `sum` giữa chừng **không có atomic snapshot**.

### Lỗi 10 — So benchmark thiếu warmup/forks

JIT, GC, CPU scaling có thể khiến số đo nhiễu; dùng JMH và report đầy đủ môi trường.

### Lỗi 11 — Đo trạng thái thread-local thay vì shared contention

`@State(Scope.Thread)` có thể làm mỗi worker có counter riêng. Nếu cần đo tranh chấp một counter, dùng shared state `Scope.Group`/`Scope.Benchmark`.

### Lỗi 12 — Lấy đo thời gian cả program làm latency increment

Thread startup, allocation, scheduler, logging làm nhiễu. Tách correctness test và microbenchmark, không in console trong hot loop.

### Lỗi 13 — Bỏ qua chi phí `sum` và bộ nhớ

LongAdder có thể tăng throughput cập nhật nhưng tổng hợp để đọc thường tốn hơn; các cell nội bộ tiêu thụ thêm bộ nhớ. Đo workload thực gồm số lần đọc.

### Lỗi 14 — So mỗi benchmark với một hành động khác nhau

AtomicLong trả sequence, LongAdder chỉ update. Nếu bài toán cần sequence, throughput LongAdder không phải so sánh cùng chức năng.

### Lỗi 15 — Không tính overflow

Các loại long accumulator không tự đảm bảo không tràn. Test ranh giới và dùng kiểu/chiến lược phù hợp nếu số liệu có giới hạn tài chính hoặc dài hạn.

### Lỗi 16 — So `DoubleAdder` bằng `==` tuyệt đối

Thứ tự cộng floating point khác nhau có thể làm rounding khác. Dùng sai số theo miền, và tránh double cho các phép toán đòi decimal exact.

### Lỗi 17 — Chỉ báo throughput, không báo error bar

Một số trung bình thiếu điều kiện môi trường và biến thiên không đủ tin cậy. Báo score/error/forks/threads/JDK/CPU và workload.

### Lỗi 18 — Tuyên bố một kết quả benchmark áp dụng mọi JVM

JDK/CPU/cache topology và data distribution ảnh hưởng mạnh. Đo lại tại môi trường, phiên bản và tải mục tiêu.

### Lỗi 19 — Xóa `LongAdder` khỏi frequency map trong lúc writer còn giữ reference

Worker có thể tăng một adder đã bị remove/swap, làm cập nhật không xuất hiện trong map mới. Cần policy quản lý vòng đời key và inflight updates.

### Lỗi 20 — Dùng `LongAdder` để bảo đảm chính xác tài chính nhiều JVM

Đó là một cấu trúc trong bộ nhớ JVM, không phải distributed transaction/ledger. Nếu một service crash, trạng thái chưa persist có thể mất.

## 21. Checklist kiểm thử đúng đắn

- [ ] Đã xác định hợp đồng từng lớp: AtomicLong vs LongAdder vs LongAccumulator?
- [ ] Đã test input 0, số âm, identity và ranh giới khi dùng LongAccumulator?
- [ ] Hàm accumulator có associative/commutative và side-effect-free phù hợp không?
- [ ] Mọi worker có thực sự dùng **cùng object** khi test contention không?
- [ ] Có barrier start giúp tạo contention nhưng không deadlock executor nhỏ không?
- [ ] Có chờ **tất cả** Future.get và không nuốt exception trước assert không?
- [ ] Có tính expected độc lập từ số worker × số update, không tính từ một shared racy counter không?
- [ ] Có chỉ assert `sum/get` chính xác **sau quiescence** không?
- [ ] Có tránh bắt `sum` trong lúc update làm snapshot exact không?
- [ ] Có kiểm tra quy tắc `sumThenReset/getThenReset` chỉ trong cửa sổ không writer không?
- [ ] Có kiểm tra CAS/sequence number nếu business cần atomic value cho từng lời gọi không?
- [ ] Có kiểm tra input không tràn long/decimal sai số double không?
- [ ] Có kiểm tra map frequency không thay mapping trong khi worker còn giữ reference không?
- [ ] Có stress nhiều tổ hợp worker, key distribution và lặp lại, nhưng không biến stress pass thành bằng chứng hình thức không?

## 22. Checklist benchmark hiệu năng và quyết định thiết kế

- [ ] Chọn metric cụ thể: update throughput, read latency, tail latency, memory hay end-to-end request latency?
- [ ] Benchmark đúng cùng phép tính và số cập nhật?
- [ ] Tách một hot counter với nhiều counters phân tán?
- [ ] Đã thử 1/2/4/8/... writers và đối chiếu số core?
- [ ] State của benchmark có thật sự shared đúng scope giữa các worker?
- [ ] Có warmup, nhiều forks, measurement iterations và dùng JMH đúng cách?
- [ ] Có tránh startup/thread scheduling/console output trong hot path không?
- [ ] Có xem tác động của GC, JIT, CPU contention và thermal/power state không?
- [ ] Có đo trường hợp có read `sum` cùng write, không chỉ 100% increment?
- [ ] Có xem memory footprint khi nhiều adder tồn tại hoặc khi contention cao?
- [ ] Có lưu lại JDK, JMH, OS, CPU, flags, thread count và sai số kết quả?
- [ ] Có tránh tuyên bố “LongAdder luôn nhanh hơn AtomicLong” không?
- [ ] Có đối chiếu kết quả correctness trước khi dùng kết luận benchmark?
- [ ] Có xác định nghiệp vụ thật sự cần số liệu atomic hay chỉ metric best-effort không?
- [ ] Khi số liệu cần bền vững/đa JVM, đã có event log, persistence hoặc transaction thay vì chỉ adder trong heap chưa?

**Kết luận:** `AtomicLong` phù hợp khi cần cập nhật/đọc **một giá trị nguyên tử** và thao tác CAS/sequence. `LongAdder` và `LongAccumulator` thường giúp giảm tranh chấp ghi khi nhiều thread, nhưng `sum/get` khi concurrent writes **không phải snapshot atomic**; `reset/sumThenReset/getThenReset` phải được dùng với chính sách quiescence nếu cần độ chính xác cuối kỳ. Kiểm thử cần assert **sau khi các writer hoàn tất**, dùng dữ liệu/identity/hàm kết hợp đúng, rồi đo throughput bằng JMH trên workload thực. **Tính đúng đắn là điều kiện để một kết quả hiệu năng có ý nghĩa**, không phải thứ có thể đánh đổi bằng một biểu đồ ops/s đẹp.

## Tài liệu chính thức và chuyên dụng

- [Oracle Java SE 26 — LongAdder: contention, sum không snapshot và reset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Oracle Java SE 26 — LongAccumulator: identity, associativity/commutativity, side-effect-free, get/getThenReset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html)
- [Oracle Java SE 26 — AtomicLong: CAS, updateAndGet, getAndIncrement](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Oracle Java SE 26 — DoubleAdder: sai số do thứ tự tích lũy và sum không atomic](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html)
- [Oracle Java SE 26 — ConcurrentHashMap: frequency map với LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Oracle Java SE 26 — Future: memory consistency effects và get](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html)
- [OpenJDK JMH — công cụ benchmark Java chính thức, archetype và samples](https://github.com/openjdk/jmh)
- [OpenJDK jcstress — harness nghiên cứu correctness concurrency và outcomes](https://github.com/openjdk/jcstress)
