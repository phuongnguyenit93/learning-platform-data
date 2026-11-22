# LongAdder so với AtomicLong dưới contention trong Java

## 1. Vấn đề: nhiều thread cùng cập nhật một bộ đếm

Giả sử nhiều thread cùng ghi nhận số request đã xử lý, số task hoàn tất hoặc số sự kiện phát sinh. Phép **counter++** trên biến **long** thông thường không phải thao tác read–modify–write nguyên tử: các thread có thể cùng đọc một giá trị cũ, cùng tăng lên rồi ghi đè kết quả của nhau. Dùng **volatile long** giúp về khả năng nhìn thấy giá trị và một số ràng buộc thứ tự bộ nhớ, nhưng **không** biến **counter++** thành phép tăng nguyên tử.

Trong package **java.util.concurrent.atomic**, hai lựa chọn quen thuộc là:

- **AtomicLong**: một giá trị **long** duy nhất được cập nhật bằng các thao tác nguyên tử, chẳng hạn **incrementAndGet()**, **getAndIncrement()**, **getAndAdd(delta)** hoặc **compareAndSet(expected, update)**.
- **LongAdder**: một bộ cộng dồn tối ưu cho nhiều cập nhật đồng thời. Nó có thể phân tán các lần cộng lên nhiều ô nội bộ rồi cộng chúng lại khi gọi **sum()**.

**Contention** (tranh chấp) xuất hiện khi nhiều thread cùng cập nhật một tài nguyên chia sẻ. Với một địa chỉ nhớ bị cập nhật liên tục, các core CPU phải phối hợp quyền sở hữu cache line và thực hiện các phép read–modify–write nguyên tử. Vì thế, khi số thread và tần suất ghi tăng, một bộ đếm duy nhất có thể thành nút thắt.

Tuy nhiên, tối ưu hiệu năng chỉ có ý nghĩa khi vẫn giữ đúng **semantics** mà ứng dụng cần. Hai lớp có điểm đánh đổi rất quan trọng: **AtomicLong phù hợp khi cần giá trị chính xác và thao tác quyết định nguyên tử; LongAdder phù hợp khi chủ yếu cộng rất nhiều và thỉnh thoảng đọc thống kê.**

## 2. AtomicLong: một giá trị nguyên tử

**AtomicLong** (có từ Java 5) giữ một giá trị **long**. Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **get()** | Đọc giá trị hiện tại bằng semantics đọc volatile. |
| **set(value)** | Gán giá trị bằng semantics ghi volatile. |
| **incrementAndGet()** | Cộng 1 nguyên tử rồi trả về giá trị **sau** khi tăng. |
| **getAndIncrement()** | Cộng 1 nguyên tử và trả về giá trị **trước** khi tăng. |
| **addAndGet(delta)** | Cộng delta nguyên tử, trả về kết quả mới. |
| **getAndAdd(delta)** | Cộng delta nguyên tử, trả về kết quả cũ. |
| **compareAndSet(expected, update)** | Chỉ đổi nếu giá trị hiện tại bằng expected; trả về thành công/thất bại. |
| **getAndSet(newValue)** | Hoán đổi nguyên tử, trả về giá trị trước đó. |
| **updateAndGet(function)** | Cập nhật nguyên tử bằng hàm; hàm có thể bị chạy lại khi tranh chấp. |

Mỗi thao tác cập nhật nguyên tử có thể xem như xảy ra tại một điểm xác định đối với giá trị đó: các thread quan sát được một thứ tự hợp lệ của những lần tăng và hoán đổi trên cùng **AtomicLong**. Do đó, **getAndIncrement()** thích hợp để cấp các số thứ tự khác nhau cho các thread.

Ví dụ, khi **sequence** bắt đầu ở 100, hai lời gọi liên tiếp **getAndIncrement()** trả về 100 và 101; không thread khác nào có thể lấy trùng một số từ cùng chuỗi cập nhật đó (trừ khi số **long** tràn hoặc code chủ động đưa giá trị quay lại). Một **LongAdder** không có API nguyên tử trả về số thứ tự của *riêng lần cộng vừa xảy ra*.

### 2.1. Khi cập nhật AtomicLong xảy ra contention

~~~text
                 AtomicLong (một vị trí logic)
Thread A  ---- increment ----\
Thread B  ---- increment -----+--> cùng một vùng nhớ bị ghi thường xuyên
Thread C  ---- increment ----/
~~~

CPU phải đồng bộ các phép ghi đến cùng một vị trí. Trên hệ thống nhiều core, việc chuyển quyền sở hữu cache line và các lần tranh chấp của thao tác nguyên tử có thể làm throughput giảm khi số writer lớn. Việc Java/JVM sử dụng lệnh read–modify–write hay vòng thử lại CAS ở một đường code cụ thể tùy implementation và nền tảng; **không nên khẳng định mọi increment đều chạy một vòng CAS viết tay**.

Trong nhiều bài toán, chi phí này hoàn toàn chấp nhận được: số thread ít, tần suất cập nhật thấp, hoặc mỗi lần cập nhật còn làm tác vụ I/O nặng hơn rất nhiều. **AtomicLong** cũng có footprint nhỏ và thao tác **get()** đơn giản.

### 2.2. AtomicLong không biến nhiều bước thành một transaction

~~~java
// Sai khi cần bảo đảm chỉ cấp chỗ nếu count < limit:
if (active.get() < limit) {
    active.incrementAndGet();
}
~~~

Giữa **get()** và **incrementAndGet()**, thread khác có thể vượt giới hạn. Cần một phép quyết định và cập nhật gắn với cùng một thao tác đồng bộ, ví dụ vòng **compareAndSet**:

~~~java
static boolean tryAcquire(java.util.concurrent.atomic.AtomicLong active,
                          long limit) {
    while (true) {
        long current = active.get();
        if (current >= limit) return false;
        if (active.compareAndSet(current, current + 1)) return true;
    }
}
~~~

Đây là **phương thức minh họa**, không phải tệp Java độc lập. Nó chỉ cho phép tăng khi giá trị quan sát được còn dưới limit, nếu **tất cả** đường sửa biến active tuân theo cùng chính sách. Với ví dụ này, giả định limit không vượt phạm vi số nguyên **long** hợp lệ và **current + 1** không tràn. Trong ứng dụng cần đồng bộ nhiều tài nguyên hoặc quản lý permit phức tạp, cân nhắc abstraction đồng bộ chuyên dụng.

**LongAdder không phù hợp cho trường hợp này**: đọc **sum()** rồi tăng không tạo thành một quyết định nguyên tử.

## 3. LongAdder: trải tải ghi thành các ô nội bộ

**LongAdder** (Java 8+) là lớp cộng dồn **long**, hỗ trợ:

- **increment()**: tương đương **add(1)**.
- **decrement()**: tương đương **add(-1)**.
- **add(delta)**: cộng một lượng bất kỳ.
- **sum()**: đọc tổng bằng cách cộng những biến thành phần nội bộ.
- **longValue()**: tương đương **sum()**.
- **reset()** và **sumThenReset()**: thao tác đặt lại dùng trong những thời điểm không còn cập nhật đồng thời.

Khác với AtomicLong, **increment()** và **add(delta)** trả về **void**. Điều này phản ánh thiết kế: LongAdder không cố cung cấp “giá trị duy nhất ngay sau lần tăng” cho từng writer. Khi các thread tranh chấp, bộ cộng có thể mở rộng tập biến nội bộ để phân tán các lần ghi.

~~~text
AtomicLong:
  Thread A --\
  Thread B ---+----> [ single long ]
  Thread C --/

LongAdder (sơ đồ khái niệm):
  Thread A ------> [ base / cell 0 ] --\
  Thread B ------> [ cell 1        ] ---+--> sum(): cộng tổng
  Thread C ------> [ cell 2        ] --/
~~~

Đây là **mô hình giải thích**, không phải cam kết rằng mỗi thread được gắn cố định với đúng một cell. JDK dùng thuật toán chia tải nội bộ (striping) và có thể điều chỉnh số cell theo mức tranh chấp. Số cell thực tế, cách chọn cell, bố trí tránh false sharing, và giới hạn mở rộng là chi tiết implementation.

### 3.1. Vì sao LongAdder thường tăng throughput khi nhiều writer?

Khi thay một điểm nóng ghi bằng nhiều điểm ghi, các core ít cạnh tranh lên cùng một cache line hơn. Các phép cập nhật vẫn thread-safe, nhưng có thể diễn ra trên những cell khác nhau. Mức giảm tranh chấp này giúp throughput của **increment()/add()** thường cao hơn **AtomicLong** dưới contention lớn.

Đổi lại:

1. **Nhiều bộ nhớ hơn**: có thể giữ nhiều cell, metadata và khoảng đệm giúp giảm tranh chấp cache.
2. **Đọc tổng đắt hơn**: **sum()** phải đọc và cộng nhiều giá trị thay vì đọc một biến.
3. **Không có snapshot nguyên tử**: khi **sum()** đang duyệt các cell, các thread khác vẫn có thể cộng vào một hoặc nhiều cell đó.
4. **Không có compare-and-set cho tổng**: không thể dùng sum làm điểm đồng bộ để cấp ID, kiểm soát ngưỡng chính xác hoặc điều khiển state machine.

Javadoc khuyến nghị LongAdder cho việc thu thập **statistics** khi nhiều thread cập nhật chung một tổng; với contention thấp, đặc tính hiệu năng của hai lớp thường tương tự nhau, còn LongAdder cần nhiều bộ nhớ hơn.

### 3.2. sum() “không atomic” có nghĩa gì?

Giả sử tổng được giữ trong hai cell:

~~~text
Trước khi đọc: cell A = 5, cell B = 7
Thread reader đọc A = 5
Thread writer cộng thêm 1 vào B
Thread reader đọc B = 8
Reader trả về 13
~~~

Đây chỉ là **một interleaving minh họa**: reader có thể lấy giá trị ở những thời điểm khác nhau. Không có hợp đồng rằng một lần gọi **sum()** là snapshot đồng thời của mọi cell tại cùng một thời điểm, hoặc nó bao gồm tất cả update diễn ra trong lúc đang tính tổng.

Phân biệt ba điều:

- Mỗi lần **add(1)** thành công đều đóng góp vào bộ cộng; đây không phải một phép tăng dữ liệu thông thường bị race rồi mất update.
- Nếu đã **dừng toàn bộ writer và đợi chúng kết thúc**, **sum()** trả về tổng chính xác của các cập nhật đã hoàn thành (với điều kiện không tràn kiểu **long**, không gọi reset, và không có thread khác cập nhật).
- Nếu writer còn chạy, **sum()** là phép quan sát cho thống kê, **không** có tính chất snapshot tuyến tính (linearizable) mà một giá trị đọc từ **AtomicLong.get()** có đối với chính biến nguyên tử đó.

Điều đó khiến LongAdder phù hợp để hiển thị số lượng request đã xử lý trên dashboard hoặc ghi telemetry theo chu kỳ, trong đó snapshot có thể chậm hơn một chút. Nó **không phù hợp** để xác nhận một điều kiện kiểu “chỉ còn một permit” hay tạo một số thứ tự duy nhất.

## 4. Bảng so sánh để chọn công cụ

| Tiêu chí | AtomicLong | LongAdder |
|---|---|---|
| Cấu trúc logic | Một giá trị long nguyên tử. | Nhiều biến thành phần cộng thành tổng. |
| Ghi | Nhiều writer tranh chấp một điểm ghi. | Có thể chia tải ghi trên nhiều cell. |
| Read API | **get()** đọc một giá trị nguyên tử. | **sum()** cộng nhiều biến, không có snapshot nguyên tử. |
| Giá trị trả về sau increment | Có, qua **incrementAndGet()** hoặc **getAndIncrement()**. | Không, **increment()** trả về void. |
| Compare-and-set | Có, **compareAndSet()**. | Không có CAS cho toàn bộ tổng. |
| Throughput ghi khi tranh chấp cao | Có thể giảm vì điểm nóng chung. | Thường tốt hơn với nhiều writer cập nhật liên tục. |
| Mức tranh chấp thấp | Thường đủ nhanh, chi phí gọn. | Thường tương tự; không mặc định nhanh hơn. |
| Chi phí bộ nhớ | Thường thấp hơn. | Có thể tăng đáng kể theo số cell. |
| Chi phí đọc | Một phép get đơn giản. | Tổng hợp các cell; tốn công hơn khi nhiều cell. |
| Reset / lấy rồi reset | **getAndSet(0)** là phép hoán đổi nguyên tử trên một biến. | **sumThenReset()** không là phép hoán đổi nguyên tử của toàn tổng nếu đồng thời có writer. |
| Dùng phù hợp | Sequence, state, quota/limit, gauge cần đọc nhất quán. | Counter thống kê, tổng số event, tần suất truy cập theo key. |

**Không có kết luận “LongAdder luôn nhanh hơn”.** Hiệu năng phụ thuộc vào core, số writer, tần suất đọc **sum()**, pattern cập nhật, cache topology, JDK, chế độ chạy và phần việc còn lại trong mỗi request.

## 5. Ví dụ Java 17+: nhiều thread cùng tăng cả hai bộ đếm

Ví dụ sau nhằm chứng minh **đếm đúng sau khi các worker kết thúc**, không nhằm đo tốc độ. Chúng ta khởi động nhiều thread gần nhau bằng latch, để từng thread tăng hai counter cùng số lần.

Tạo file **CounterComparison.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class CounterComparison {
    public static void main(String[] args) throws InterruptedException {
        final int threads = 4;
        final int updatesPerThread = 10_000;

        AtomicLong atomic = new AtomicLong();
        LongAdder adder = new LongAdder();

        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);

        for (int i = 0; i < threads; i++) {
            Thread worker = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    for (int n = 0; n < updatesPerThread; n++) {
                        atomic.incrementAndGet();
                        adder.increment();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            worker.start();
        }

        ready.await();
        start.countDown();
        done.await();

        long expected = (long) threads * updatesPerThread;
        System.out.println("expected=" + expected);
        System.out.println("atomic=" + atomic.get());
        System.out.println("adder=" + adder.sum());

        AtomicLong sequence = new AtomicLong(100);
        System.out.println("tickets=" + sequence.getAndIncrement()
                           + "," + sequence.getAndIncrement());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 CounterComparison.java
java CounterComparison
~~~

Kết quả của một lần chạy bình thường, không có interrupt:

~~~text
expected=40000
atomic=40000
adder=40000
tickets=100,101
~~~

**Giải thích:**

1. **ready** bảo đảm bốn thread đã tới điểm chuẩn bị; **start** cho phép tất cả bắt đầu vòng lặp gần nhau.
2. Mỗi thread gọi **atomic.incrementAndGet()** và **adder.increment()** đúng 10.000 lần. Có 40.000 lượt cộng ở mỗi counter.
3. **done.await()** bảo đảm mọi thread đã kết thúc. Khi main đọc **adder.sum()**, không còn cập nhật đồng thời, nên tổng là chính xác. Việc đợi hoàn thành cũng tạo quan hệ đồng bộ cần thiết cho việc đọc kết quả cuối.
4. **tickets=100,101** cho thấy **getAndIncrement()** vừa tăng vừa trả về giá trị trước tăng, điều mà **LongAdder** không thể cung cấp bằng một lời gọi tương đương.

Đừng kết luận tốc độ từ chương trình này: cả hai phép cập nhật được thực hiện trong **cùng một loop**; nếu đo một con số thời gian chung sẽ không tách được overhead của từng counter. Ngoài ra, số iteration nhỏ và chi phí tạo thread có thể lấn át tín hiệu thực cần đo.

## 6. Ví dụ ứng dụng: tần suất sự kiện theo key

Một pattern chính thức của JDK là kết hợp **ConcurrentHashMap<String, LongAdder>** với **computeIfAbsent()** để đếm tần suất theo từng loại sự kiện. Mỗi key sở hữu một bộ cộng riêng và nhiều thread có thể cùng gọi hàm ghi nhận.

Tạo file **EventFrequency.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class EventFrequency {
    private static final ConcurrentHashMap<String, LongAdder> COUNTS =
            new ConcurrentHashMap<>();

    private static void record(String event) {
        COUNTS.computeIfAbsent(event, ignored -> new LongAdder())
              .increment();
    }

    public static void main(String[] args) {
        record("ok");
        record("error");
        record("ok");

        System.out.println("ok=" + COUNTS.get("ok").sum());
        System.out.println("error=" + COUNTS.get("error").sum());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 EventFrequency.java
java EventFrequency
~~~

Kết quả:

~~~text
ok=2
error=1
~~~

**computeIfAbsent()** khởi tạo counter cho key chưa tồn tại theo cơ chế thread-safe của **ConcurrentHashMap**; nhiều lời gọi **record("ok")** sau đó được cộng an toàn vào cùng LongAdder. **Ví dụ trên chạy tuần tự** để có output cố định; cùng một phương thức **record** dùng được từ nhiều thread. Để lấy tổng chính xác cuối bài kiểm thử đa luồng, cần đợi tất cả writer xong rồi mới **sum()**.

Các lưu ý triển khai:

- **Không** dùng **LongAdder** làm khóa dựa trên nội dung counter; lớp này không định nghĩa phép so sánh giá trị như một key bất biến.
- Khi key đến từ dữ liệu có thể có số lượng vô hạn (chẳng hạn ID không giới hạn), map có thể tăng bộ nhớ mãi; cần xác định giới hạn nhãn, vòng đời và cách xóa key.
- Nếu phải đồng bộ thao tác xóa/thay bộ đếm với writer, cần một chính sách vòng đời có chủ đích. Việc **remove(key)** khi thread khác còn giữ tham chiếu tới LongAdder cũ có thể khiến số lần cộng không còn nằm trong counter mới của map.
- Với **chỉ số thống kê**, đọc **sum()** trong lúc cập nhật thường đủ. Với logic tài chính, cấp quyền hoặc giới hạn chính xác, cần cơ chế có semantics mạnh hơn.

## 7. Thử nghiệm contention cho đúng

Những phép benchmark nhỏ tự viết kiểu “for 1 triệu vòng rồi lấy nanoTime” rất dễ dẫn đến kết luận sai. JVM có JIT compilation, tiered compilation, warm-up, các tối ưu dead-code và nhiều nhiễu từ scheduler/GC/turbo boost/cache. Muốn so hiệu năng, nên dùng **JMH (Java Microbenchmark Harness)** cho phép benchmark có warm-up, đo nhiều lượt và đặt các phép cập nhật trong tình huống thực có contention. JMH là công cụ benchmark riêng, không phải API bắt buộc của **java.util.concurrent**.

### 7.1. Những biến cần kiểm soát

1. **Threads**: đo 1, 2, 4, 8, … writer phù hợp với số core thật; tránh suy diễn từ một cấu hình duy nhất.
2. **Mô hình chia sẻ**: tất cả thread cập nhật **cùng một** counter để đo contention; nếu mỗi thread dùng counter riêng thì bài toán đã khác.
3. **Read frequency**: đo trường hợp hiếm **sum()** (ví dụ cuối mỗi khoảng) và trường hợp vừa ghi vừa đọc **sum()** thường xuyên. LongAdder có thể đánh đổi tốc độ cập nhật lấy chi phí tổng hợp.
4. **Throughput và latency**: xem updates/second, thời gian mỗi operation nếu phù hợp, phân phối theo nhiều lần thử; đồng thời theo dõi mức CPU và GC.
5. **Memory**: xem footprint khi nhiều LongAdder sinh thêm cell, đặc biệt khi có nhiều key hoặc nhiều instance.
6. **JVM/hardware**: ghi lại JDK, số core, CPU, cấu hình heap, môi trường container/VM và các tải nền.
7. **Định nghĩa phép đo**: không cộng chi phí tạo thread, khởi tạo executor hoặc dựng counter vào phép đo update nếu mục tiêu là so cost của **increment**.

### 7.2. Điều gì thường xảy ra?

| Môi trường | Kỳ vọng hợp lý (không phải số liệu cố định) |
|---|---|
| Một thread hoặc ghi hiếm | AtomicLong có thể ngang hoặc tốt hơn vì ít chi phí cấu trúc. |
| Nhiều writer cập nhật cùng counter rất thường xuyên | LongAdder thường tăng throughput nhờ giảm điểm nóng ghi. |
| Cập nhật hiếm nhưng đọc tổng liên tục | Lợi thế của LongAdder có thể biến mất do chi phí **sum()**. |
| Hàng trăm nghìn key, mỗi key ít update | LongAdder có thể tốn bộ nhớ hơn so với dùng AtomicLong. |
| Cần phát số thứ tự độc nhất sau mỗi update | Chọn AtomicLong vì yêu cầu correctness, không phải vì benchmark. |

Không đưa ra hệ số “nhanh hơn 2x/10x” nếu chưa có kết quả benchmark thực trên workload mục tiêu.

## 8. reset, sumThenReset và ranh giới của số liệu

**AtomicLong.getAndSet(0)** là một phép hoán đổi nguyên tử trên cùng giá trị. Nếu các thread chỉ tăng counter bằng thao tác nguyên tử, lần tăng sẽ nằm trước hoặc sau điểm hoán đổi theo thứ tự hợp lệ. Vì vậy, việc lấy số lượng một khoảng rồi reset có semantics rõ đối với **một** biến AtomicLong.

Ngược lại, **LongAdder.reset()** và **sumThenReset()** hoạt động trên các biến thành phần. Javadoc nhấn mạnh những thao tác này **vốn có race** khi có thread đang cộng; **sumThenReset()** không bảo đảm trả về tổng cuối cùng đúng ranh giới thời gian khi các update diễn ra đồng thời. Chỉ nên dùng khi đã đưa writers vào trạng thái không còn cập nhật (quiescent point) hoặc chấp nhận được độ lệch theo đặc tính triển khai.

Ví dụ một pattern đo số request từng khoảng:

~~~java
// Minh họa cách dùng khi cập nhật đã được tạm dừng:
// LongAdder requests = ...;
// stopAndJoinAllWriters();
// long count = requests.sumThenReset();
// startNextEpoch();
~~~

Phần trên **chỉ là pseudocode**, không phải chương trình Java độc lập: **stopAndJoinAllWriters()** và **startNextEpoch()** đại diện cho cơ chế vòng đời của ứng dụng. Nếu cứ gọi **sumThenReset()** theo timer trong lúc hàng chục worker còn gọi **increment()**, không được tự coi dữ liệu mỗi khoảng là phép chốt nguyên tử chính xác tuyệt đối.

Nếu dashboard chỉ muốn thống kê lũy kế, thường đơn giản hơn khi **không reset** và tính hiệu giữa hai lần lấy mẫu:

~~~text
t0: total = 1_000
t1: total = 1_120
ước lượng số sự kiện của khoảng = 120
~~~

Cách lấy hiệu trên **sum()** vẫn dựa vào những snapshot không nguyên tử khi writer đang chạy; nó phù hợp với telemetry chấp nhận sai lệch thời điểm, không phải sổ cái có yêu cầu chính xác tuyệt đối. Nếu có phép decrement hoặc thay counter, chênh lệch còn có thể âm. Để đo mỗi epoch chặt chẽ, cần rào đồng bộ/chuyển epoch rõ ràng hoặc bộ đếm có semantics phù hợp.

## 9. Trường hợp thực tế nào cần lớp nào?

### 9.1. Bộ đếm phục vụ quan sát hệ thống

Ví dụ đếm request thành công, lỗi, event được tiêu thụ, số byte xử lý từ nhiều writer. Chỉ cần tổng cho báo cáo/monitoring theo chu kỳ.

**Ưu tiên LongAdder** nếu nhiều writer tranh chấp; tổng đọc đồng thời có thể là thống kê gần thời điểm đó. Với tần suất cập nhật thấp, AtomicLong vẫn là lựa chọn đơn giản và hợp lý.

### 9.2. Bộ cấp số thứ tự hoặc sequence

Ví dụ sinh ID tăng dần ở phạm vi một JVM, sequence ghi log hoặc số ticket nội bộ. Mỗi lần gọi cần nhận một giá trị riêng với thứ tự cập nhật rõ ràng.

**Dùng AtomicLong.getAndIncrement()** hoặc **incrementAndGet()**. Lưu ý phạm vi: sequence trong bộ nhớ một JVM không tự tạo ID duy nhất xuyên nhiều JVM, không bền qua restart, và có thể tràn **long** sau thời gian rất dài.

### 9.3. Giới hạn số tác vụ đang chạy

Ví dụ không cho hơn 20 task đồng thời. Bài toán này cần kiểm tra và cấp quyền đồng bộ, không chỉ theo dõi số lần gọi.

**Không chọn LongAdder.sum() rồi increment() để chặn ngưỡng.** Có thể dùng CAS với AtomicLong hoặc cấu trúc đồng bộ như **Semaphore**, tùy mô hình. Nếu dùng AtomicLong, phải thiết kế cả đường giảm permit khi hoàn tất/thất bại, cũng như xử lý exception, để không rò rỉ permit.

### 9.4. Current active requests hoặc một gauge

Một chỉ số gauge có **increment()** khi bắt đầu và **decrement()** khi kết thúc. LongAdder dùng được nếu chỉ hiển thị số request active trên dashboard và chấp nhận việc **sum()** đang chạy không là snapshot chặt. Nếu cần logic “không được âm”, “không vượt capacity” hoặc quyết định giao dịch dựa trên giá trị quan sát, cần atomic check-and-update hoặc lock/permit.

### 9.5. Rất nhiều counter ít được truy cập

Nếu mỗi user/key có counter riêng nhưng phần lớn key chỉ nhận ít update, LongAdder có thể không đem lại lợi ích và gây overhead đối tượng/bộ nhớ, đặc biệt khi có contention dẫn tới mở rộng cell. Thử **AtomicLong** trước, sau đó benchmark trên workload thật khi cần tối ưu.

## 10. Những nhầm lẫn thường gặp

1. **“LongAdder nhanh hơn trong mọi tình huống.”** Sai. Nó chủ yếu phát huy tác dụng khi nhiều writer thực sự tranh chấp cùng tổng; read-heavy hoặc low-contention có thể không lợi.
2. **“LongAdder.sum() tương đương AtomicLong.get().”** Sai về semantics. **sum()** không trả về snapshot nguyên tử khi có update đồng thời.
3. **“LongAdder làm mất các lần increment.”** Không phải vậy. Các **add()** hoàn thành được cộng vào trạng thái; điểm yếu là **thời điểm quan sát tổng**, đặc biệt khi có concurrent updates hoặc reset.
4. **“Một thread được ghim cố định với một cell.”** Không có đảm bảo như vậy trong API; striping là chi tiết implementation có thể thay đổi.
5. **“LongAdder sẽ có thể cấp ID bằng cách increment rồi sum.”** Không bảo đảm: giữa hai thao tác có thể có nhiều writer khác cập nhật và **sum()** không có snapshot nguyên tử.
6. **“volatile long++ đã đủ.”** Sai: volatile không biến chuỗi read–modify–write thành một thao tác nguyên tử.
7. **“AtomicLong luôn không bao giờ chậm khi có nhiều thread vì lock-free.”** Các primitive nguyên tử vẫn có chi phí cache coherence và contention. Lock-free cũng không đồng nghĩa throughput tuyến tính.
8. **“reset hoặc sumThenReset có thể gọi tự do trong lúc writers đang chạy.”** Sai nếu yêu cầu số đếm mỗi chu kỳ chính xác.
9. **“Chạy một vòng for rồi đo nanoTime là đủ kết luận.”** Sai: JIT, độ ấm JVM, số thread, benchmark harness và tần suất đọc ảnh hưởng mạnh tới số liệu.
10. **“AtomicLong khiến mọi phép kiểm tra kèm cập nhật đều an toàn.”** Sai: chỉ những thao tác nguyên tử riêng lẻ và thuật toán được xây đúng quanh chúng có bảo đảm mong muốn.

## 11. Checklist khi ra quyết định

- **Có cần giá trị trả về cho mỗi lần tăng hoặc CAS theo ngưỡng không?** Nếu có, chọn **AtomicLong**.
- **Có cần tổng chính xác tại một thời điểm khi writer vẫn chạy không?** **AtomicLong.get()** có semantics của một giá trị nguyên tử; **LongAdder.sum()** không có snapshot tương đương.
- **Có nhiều writer liên tục cùng cập nhật một counter không?** Nếu có, cân nhắc **LongAdder** và đo bằng workload mục tiêu.
- **Đọc tổng thường xuyên tới mức nào?** Nếu read-heavy, tính cả chi phí **sum()**.
- **Có nhiều counter theo key không?** Đo footprint và kiểm soát số lượng key.
- **Có reset theo khoảng không?** Kiểm tra yêu cầu chính xác của thời điểm reset và chính sách dừng writer.
- **Đã kiểm thử cùng kiểu tải và số core thật chưa?** Không chọn chỉ dựa trên benchmark vô căn cứ.

**Nguyên tắc nhớ:** **AtomicLong** ưu tiên thao tác nguyên tử trên **một giá trị**; **LongAdder** đánh đổi tính nhất quán tức thời khi đọc tổng và tài nguyên bổ sung để tối ưu throughput **cộng dồn khi contention cao**. Chọn dựa trên semantics trước, rồi mới đo hiệu năng.

## 12. Tài liệu chính thức

- [LongAdder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [AtomicLong — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
