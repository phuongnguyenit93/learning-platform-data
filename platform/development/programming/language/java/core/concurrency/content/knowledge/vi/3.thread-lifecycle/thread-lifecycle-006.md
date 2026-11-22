# Scheduling và sự bất định của thứ tự thực thi trong Java

## 1. Scheduling là gì và vì sao thứ tự thực thi không cố định?

Trong Java, **thread scheduling** là quá trình chọn thread nào có cơ hội tiến triển tại một thời điểm. JVM và hệ điều hành cùng tham gia quản lý khả năng chạy của các thread; quyết định thực tế phụ thuộc vào hệ điều hành, số lõi CPU, độ ưu tiên, tải máy, thao tác chờ, khóa và nhiều yếu tố khác. Lập trình viên không được dựa vào một lịch chạy cụ thể chỉ vì chương trình thường chạy theo lịch đó trên máy của mình.

Ví dụ, hai thread độc lập A và B đều in một dòng. Dù gọi `a.start()` trước `b.start()`, hệ thống vẫn có thể cho B in trước A. `start()` khởi động quá trình thực thi bất đồng bộ; nó **không** đợi thread chạy tới một điểm nào đó và không bảo đảm thread được gọi `start()` trước sẽ thực hiện câu lệnh đầu tiên trước.

Cần phân biệt ba khái niệm:

- **Concurrency (đồng thời):** nhiều thread có thể tiến triển trong cùng một khoảng thời gian; JVM/OS có thể xen kẽ chúng trên một lõi.
- **Parallelism (song song):** các thread thực sự thực thi đồng thời trên nhiều lõi.
- **Scheduling (lập lịch):** quyết định khi nào một thread có cơ hội chạy, chờ, bị tạm dừng hoặc tiếp tục. Lập lịch không tạo ra bảo đảm về thứ tự giữa các tác vụ độc lập.

**Thông điệp quan trọng:** kết quả đúng của chương trình đa luồng phải dựa vào quan hệ phụ thuộc và cơ chế đồng bộ xác định, không dựa vào việc “thread này có lẽ sẽ chạy trước”.

## 2. Trạng thái thread liên quan đến scheduler

`Thread.State` trong Java cho biết một số trạng thái JVM quan sát được của thread. Nó không phải bản mô tả đầy đủ mọi trạng thái do hệ điều hành quản lý và chỉ là ảnh chụp tại thời điểm gọi `getState()`.

| `Thread.State` | Ý nghĩa thực hành | Liên hệ với scheduling |
| --- | --- | --- |
| `NEW` | Đã tạo đối tượng nhưng chưa `start()` | Chưa được đăng ký để thực thi như thread mới |
| `RUNNABLE` | Đang thực thi trong JVM hoặc sẵn sàng thực thi | **Không đồng nghĩa đang chiếm CPU đúng thời điểm quan sát** |
| `BLOCKED` | Đang chờ lấy monitor của `synchronized` | Phải đợi monitor khả dụng; không phải một trạng thái chung cho mọi I/O |
| `WAITING` | Đang đợi vô thời hạn theo cơ chế chờ, ví dụ `Object.wait()`, `Thread.join()` hoặc `LockSupport.park()` | Không thể tiếp tục nếu điều kiện/chỉ báo đánh thức tương ứng chưa xảy ra |
| `TIMED_WAITING` | Đang đợi có thời hạn, ví dụ `Thread.sleep()`, timed `join()`, timed `wait()` | Có thể tiếp tục khi điều kiện thỏa hoặc hết thời gian, sau đó còn phụ thuộc lập lịch |
| `TERMINATED` | `run()` đã kết thúc hoặc thread chấm dứt do lỗi không xử lý | Không được khởi động lại |

Một thread có thể đi qua nhiều trạng thái rất nhanh. Ví dụ quan sát `RUNNABLE` rồi gọi `getState()` lại có thể thấy `WAITING`. Vì vậy không viết logic phối hợp dựa vào việc liên tục kiểm tra `getState()` rồi giả định thread đang ở nguyên trạng thái đó.

**Đặc biệt:** gọi `Thread.sleep()` không có nghĩa nhường quyền sở hữu monitor đã giữ; nếu đang ở trong `synchronized`, thread vẫn giữ monitor trong lúc ngủ.

## 3. Ví dụ Java 17+: hai thread bắt đầu cùng mốc nhưng thứ tự không bảo đảm

Tạo tệp `SchedulingObservation.java`:

```java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class SchedulingObservation {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        ConcurrentLinkedQueue<String> order = new ConcurrentLinkedQueue<>();

        Runnable work = () -> {
            ready.countDown();
            try {
                go.await();
                order.add(Thread.currentThread().getName());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(work, "A");
        Thread b = new Thread(work, "B");

        a.start();
        b.start();
        ready.await();    // Cả hai worker đã tới mốc sẵn sàng
        go.countDown();   // Mở cùng một rào chờ
        a.join();
        b.join();

        System.out.println("Observed order: " + order);
        System.out.println("Recorded two events: " + (order.size() == 2));
    }
}
```

Biên dịch và chạy:

```bash
javac SchedulingObservation.java
java SchedulingObservation
```

**Hai dạng đầu ra có thể gặp** (thứ tự không được bảo đảm):

```text
Observed order: [A, B]
Recorded two events: true
```

hoặc:

```text
Observed order: [B, A]
Recorded two events: true
```

Không có cam kết sẽ quan sát được cả hai thứ tự dù chạy nhiều lần trên cùng máy. Lập lịch đôi khi tình cờ lặp lại một thứ tự rất ổn định. **Đừng dùng sự ổn định đó làm chứng cứ bảo đảm.**

Giải thích các thành phần:

1. `CountDownLatch ready` giúp `main` biết cả hai worker đã đi tới cổng chờ.
2. `go.await()` khiến hai worker đợi đến khi `go.countDown()`; đây là đồng bộ tại một mốc, **không** bảo đảm chúng được chạy cùng một nano-giây hoặc chọn thứ tự A/B nào.
3. `ConcurrentLinkedQueue` cho phép ghi sự kiện từ nhiều thread an toàn, tránh lỗi dữ liệu do collection không hỗ trợ đồng thời.
4. Hai `join()` làm `main` chờ cả hai worker hoàn tất trước khi in kết quả.
5. Nếu chương trình không bị interrupt từ bên ngoài thì cả hai worker ghi một tên vào queue. Dòng `Recorded two events: true` xác định; dòng thứ tự quan sát phụ thuộc lịch chạy.

Đây là ví dụ về **thứ tự của các side effect** do nhiều thread thực hiện. Ngay cả khi mỗi thread chỉ có một thao tác rất ngắn, Java cũng không hứa sẽ chạy các thao tác theo thứ tự gọi `start()`.

## 4. Các nguyên nhân khiến lịch thực thi thay đổi

### 4.1. Khả năng chạy và thời điểm thực sự được cấp CPU

Một thread ở trạng thái `RUNNABLE` có thể đã sẵn sàng nhưng chưa được CPU thực thi ngay. Trên máy có nhiều lõi, các thread có thể chạy song song; trên máy ít lõi hơn số thread sẵn sàng, chúng phải chia sẻ thời gian xử lý. Kết quả phụ thuộc hệ điều hành và tình trạng máy tại thời điểm chạy.

### 4.2. Preemption và chuyển ngữ cảnh

Hệ điều hành có thể chuyển CPU từ thread này sang thread khác theo cơ chế lập lịch của nó. Việc chuyển ngữ cảnh khiến các lệnh của nhiều thread có thể xen kẽ với nhau. Java không cung cấp cam kết rằng mỗi đoạn mã giữa hai dấu chấm phẩy sẽ luôn chạy liền một mạch không bị xen kẽ.

Cần phân biệt **tác vụ ngắn về mặt mã nguồn** với **thao tác nguyên tử**. Ví dụ `counter++` gồm các bước đọc, cộng, ghi; việc viết trên một dòng không làm ba bước trở nên không thể xen kẽ với thao tác của thread khác.

### 4.3. Chờ lock, I/O và các primitive đồng bộ

Một thread có thể phải chờ monitor của `synchronized`, điều kiện trong `wait()`/`notify()`, `CountDownLatch`, `Semaphore`, `BlockingQueue`, `LockSupport`, `Future` hoặc I/O. Khi sự kiện chờ kết thúc, thread trở thành ứng viên để chạy; điều đó **không** cam kết nó sẽ được CPU chạy tức thì hoặc chạy trước mọi thread khác.

### 4.4. Độ ưu tiên thread

Java có `Thread.MIN_PRIORITY`, `Thread.NORM_PRIORITY`, `Thread.MAX_PRIORITY` và `setPriority(int)` cho platform threads truyền thống. Priority có thể tác động đến scheduling tùy JVM và hệ điều hành, nhưng **không phải công cụ bảo đảm thứ tự, tính công bằng hay hạn chót**. Không xây dựng tính đúng đắn dựa vào giả thuyết rằng thread priority cao sẽ luôn chạy hoặc hoàn thành trước.

### 4.5. Tối ưu hóa và bộ nhớ

Ngoài sự bất định về lịch chạy, chương trình có **data race** còn có vấn đề visibility và ordering theo Java Memory Model. Compiler, JIT và CPU có thể thực hiện tối ưu hóa hợp lệ mà một thread khác không quan sát được các thao tác như thứ tự mã nguồn đơn giản nếu không có quan hệ đồng bộ thích hợp.

Vì thế câu “chỉ cần thêm `sleep()` để thread kia có thời gian cập nhật biến” có hai lỗi: thời gian ngủ không bảo đảm thread kia đã chạy xong và `sleep()` không tự tạo quan hệ happens-before để xuất bản dữ liệu an toàn.

## 5. `sleep()`, `yield()`, `join()` có làm lịch chạy trở nên xác định không?

| API | Tác dụng | Điều **không** được bảo đảm |
| --- | --- | --- |
| `Thread.sleep(millis)` | Đề nghị thread hiện tại tạm ngừng trong khoảng thời gian chỉ định | Thread khác sẽ hoàn tất; chính xác thời điểm được chạy lại; visibility của dữ liệu |
| `Thread.yield()` | Gợi ý scheduler rằng thread hiện tại sẵn sàng nhường phần thời gian chạy | Scheduler sẽ nghe theo; thread khác sẽ chạy trước; cách sắp lịch cố định |
| `Thread.join()` | Thread gọi chờ thread đích chấm dứt | Thứ tự thực thi giữa các worker độc lập; worker hoàn thành thành công |
| `Thread.start()` | Khởi chạy một thread mới | Thread vừa start sẽ chạy trước thread start sau |
| `Thread.setPriority(...)` | Điều chỉnh gợi ý ưu tiên khi triển khai hỗ trợ | Thứ tự, độ công bằng, thời hạn phản hồi |

**Về `sleep()`:** thời gian ngủ còn phụ thuộc độ chính xác timer, scheduler và tải máy. `sleep(100)` không phải lời hứa “chạy lại sau đúng 100 ms”. Có thể đo thời gian trôi qua để quản lý timeout, nhưng phải tính việc thức dậy muộn hơn dự kiến.

**Về `yield()`:** nó là một hint không có hiệu lực đồng bộ. Thêm `yield()` trong một vòng lặp chờ flag thông thường không thay `volatile`, lock hoặc các cơ chế chờ đúng chuẩn. Busy-wait có thể gây lãng phí CPU và vẫn sai về visibility.

**Về `join()`:** sau khi `join()` trả về bình thường không có timeout, thread đích đã kết thúc; tuy nhiên thứ tự từng câu lệnh giữa các worker trước đó vẫn có thể khác nhau. `join(timeout)` chỉ chờ có giới hạn, nên phải kiểm tra `isAlive()` nếu cần biết worker thực sự đã hoàn tất.

## 6. Đừng nhầm bất định thứ tự với bất định kết quả đúng

Một ứng dụng concurrent tốt **có thể có lịch chạy khác nhau nhưng vẫn có kết quả đúng giống nhau**. Ví dụ hai thread tính hai phần độc lập rồi main lấy tổng sau khi cả hai đã kết thúc: từng phần có thể hoàn tất theo thứ tự nào cũng được nếu cách lưu và thu thập kết quả an toàn.

Ngược lại, nếu nhiều thread cùng cập nhật một biến mutable không đồng bộ, kết quả tính toán có thể sai tùy thứ tự xen kẽ.

### Vì sao `counter++` không an toàn?

Giả sử hai thread cùng đọc `counter = 0`, mỗi thread tính `1`, sau đó đều ghi `1`. Ta mong đợi `2` nhưng nhận được `1`: một lần tăng bị mất. Đây gọi là **lost update**, một dạng race condition. `volatile int counter` bảo đảm visibility của phép đọc/ghi riêng lẻ nhưng **không** biến thao tác đọc-sửa-ghi `counter++` thành nguyên tử.

Để ví dụ có đầu ra đúng, sử dụng `AtomicInteger.incrementAndGet()` hoặc `getAndIncrement()`, hoặc bảo vệ thao tác bằng khóa phù hợp.

Tạo tệp `AtomicScheduling.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicScheduling {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Final count: " + counter.get());
    }
}
```

Biên dịch và chạy:

```bash
javac AtomicScheduling.java
java AtomicScheduling
```

Đầu ra:

```text
Final count: 2000
```

Scheduler có thể xen kẽ A và B theo bất kỳ lịch hợp lệ nào; kết quả vẫn là 2.000 vì hai thread thực hiện đủ số lần tăng nguyên tử và `main` chờ cả hai bằng `join()`. **Không cần** ép A chạy hết rồi mới B. Đây là hướng thiết kế tốt: dùng primitive có bảo đảm phù hợp để kết quả không phụ thuộc thứ tự scheduling.

## 7. Muốn có thứ tự thì phải biểu diễn quan hệ phụ thuộc

Có những công việc cần thứ tự nghiệp vụ thật: chẳng hạn bước “nạp cấu hình” phải xong trước bước “dùng cấu hình”. Khi đó hãy đồng bộ **đúng sự kiện**, thay vì kỳ vọng một thread được `start()` trước sẽ luôn hoàn thành trước.

### Ví dụ Java 17+: bảo đảm bước 1 trước bước 2 bằng `CountDownLatch`

Tạo tệp `OrderedSteps.java`:

```java
import java.util.concurrent.CountDownLatch;

public class OrderedSteps {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstDone = new CountDownLatch(1);

        Thread second = new Thread(() -> {
            try {
                firstDone.await();
                System.out.println("Step 2: use data");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        Thread first = new Thread(() -> {
            System.out.println("Step 1: prepare data");
            firstDone.countDown();
        }, "producer");

        second.start(); // Cố ý start consumer trước
        first.start();

        first.join();
        second.join();
        System.out.println("All done");
    }
}
```

Chạy:

```bash
javac OrderedSteps.java
java OrderedSteps
```

Đầu ra trong lần chạy hoàn tất bình thường:

```text
Step 1: prepare data
Step 2: use data
All done
```

Dù `second.start()` được gọi trước, `second` chỉ in bước 2 sau khi `firstDone` được giảm về 0. Đây là thứ tự **do điều kiện đồng bộ tạo ra**, không phải nhờ scheduler ưu tiên thread nào.

`CountDownLatch.countDown()` có quan hệ happens-before với các hành động sau khi thread khác vượt qua `await()` thành công. Vì vậy nếu producer ghi dữ liệu trước `countDown()` và consumer chỉ đọc sau `await()`, đây là một ranh giới công bố dữ liệu hợp lệ. Lưu ý rằng latch không tự truyền ngoại lệ hoặc chứng minh producer thành công: bài toán production phải định nghĩa cách xử lý lỗi và tránh chờ vô hạn nếu producer không bao giờ gọi `countDown()`.

### Trường hợp chỉ cần kết quả sau khi thread kết thúc

`worker.join()` đơn giản hơn khi **toàn bộ** thread worker phải kết thúc trước khi main dùng kết quả. Nhưng nếu consumer cần chờ một **mốc** trong lúc producer còn tiếp tục làm việc, `CountDownLatch`, `BlockingQueue`, `Condition` hoặc một abstraction tương tự diễn đạt yêu cầu chính xác hơn.

## 8. Java Memory Model: thứ tự logic và visibility

Scheduler quyết định thời điểm thread có cơ hội chạy, còn **Java Memory Model (JMM)** xác định những quan sát dữ liệu được bảo đảm giữa thread khi các điều kiện đồng bộ được thỏa mãn.

Một số quan hệ **happens-before** cần nhớ:

- Các hành động trong cùng một thread tuân theo quy tắc thứ tự chương trình (`program order`) theo ngữ nghĩa JMM; điều này không có nghĩa mọi lệnh máy đều được phát ra theo đúng thứ tự mã nguồn.
- Lời gọi `thread.start()` happens-before các hành động của thread vừa được khởi động.
- Các hành động của một thread happens-before việc thread khác xác nhận thread đó đã kết thúc qua `join()` thành công.
- Một lần unlock monitor happens-before lần lock tiếp theo trên **cùng monitor**.
- Một lần ghi vào trường `volatile` happens-before lần đọc tiếp theo của chính trường đó trong thứ tự đồng bộ.
- Với `CountDownLatch`, các hành động trước `countDown()` happens-before hành động sau `await()` thành công khi latch mở.

Quan hệ happens-before là nền tảng về visibility và ordering, **không có nghĩa scheduler buộc thread có quan hệ trước được CPU chọn chạy đầu tiên ở mọi thời điểm**. Ví dụ, main gọi `a.start()` rồi `b.start()`: thao tác start có quan hệ với các hành động trong từng worker, nhưng **không tạo ra** thứ tự toàn phần giữa mọi hành động của A và B.

Không dùng `System.out.println()` hay `Thread.sleep()` như giao thức điều phối. Một vài triển khai I/O có đồng bộ nội bộ, nhưng dựa vào tác dụng phụ của logging để sửa race hoặc định thứ tự là thiết kế mong manh.

## 9. Các lỗi thường gặp liên quan scheduling

### 9.1. Giả định thứ tự gọi `start()` quyết định thứ tự kết quả

Sai: `a.start(); b.start();` không tạo cam kết A in trước B. Giải pháp: nếu cần thứ tự, dùng `join()` tại đúng ranh giới hoặc primitive đồng bộ sự kiện. Nếu các task độc lập, viết code chấp nhận mọi thứ tự hợp lệ.

### 9.2. Dùng `sleep()` để “đợi đủ lâu”

Sai: ngủ 500 ms không chứng minh một task khác đã hoàn tất hoặc dữ liệu đã được công bố đúng. Hãy chờ điều kiện thật: `join()`, `Future.get()`, latch, queue hoặc lock/condition; khi cần thời hạn, dùng các API có timeout và kiểm tra trạng thái kết quả.

### 9.3. Dùng `yield()`/priority để giải quyết race

Sai: `yield()` chỉ gợi ý lập lịch; priority cũng không tạo thứ tự và không bảo đảm fairness. Lỗi truy cập dữ liệu phải được xử lý bằng quan hệ đồng bộ hoặc thiết kế lại dữ liệu.

### 9.4. Nghĩ kiểm thử vài nghìn lần không lỗi thì không có race

Sai: cùng máy, cùng tải và cùng một lịch chạy phổ biến có thể che giấu race. Thread scheduling biến thiên theo hệ điều hành và tải; chạy nhiều lần, stress tests và công cụ quan sát chỉ tăng khả năng phát hiện, không chứng minh không có mọi race.

### 9.5. Busy-wait không điều kiện đồng bộ

Ví dụ lỗi về mặt ý tưởng:

```java
while (!finished) {
    Thread.yield();
}
```

Nếu `finished` là boolean thường do thread khác ghi và không có đồng bộ phù hợp, thread chờ có thể không quan sát được thay đổi; ngoài ra vòng lặp lãng phí CPU. Đây là **snippet minh họa lỗi**, không phải chương trình Java hoàn chỉnh. Nên dùng `volatile` cho tín hiệu đơn giản theo thiết kế hợp lệ, hoặc `CountDownLatch`, `BlockingQueue`, `Condition` nếu cần đợi sự kiện. Với chuỗi trạng thái phức tạp, `volatile` đơn lẻ không giải quyết mọi vấn đề atomicity.

### 9.6. Deadlock vì đồ thị chờ có vòng

Nếu A giữ một lock và chờ B, trong khi B cần lock đó để hoàn thành, scheduler không thể tự “sửa” quan hệ chờ. Chẳng hạn A `join()` B khi đang giữ monitor mà B phải lấy, cả hai có thể kẹt. Hãy thiết kế thứ tự lock ổn định, hạn chế giữ lock khi chờ và tránh các vòng phụ thuộc.

### 9.7. Nhầm starvation với deadlock

**Starvation** xảy ra khi một thread ít hoặc không có cơ hội tiến triển do cạnh tranh tài nguyên, lock hoặc chính sách ưu tiên không công bằng; hệ thống có thể vẫn đang có các thread khác tiến triển. **Deadlock** là vòng phụ thuộc khiến một nhóm thread không thể tiến triển. **Livelock** là các thread vẫn hoạt động, đổi trạng thái nhưng không đạt mục tiêu. Ba vấn đề đều có thể xuất hiện trong chương trình concurrent, và việc “tăng priority” không phải lời giải tổng quát.

## 10. Quan sát và đo lường đúng cách

- Dùng tên thread rõ ràng (`new Thread(task, "worker-A")`) để log, stack trace và thread dump dễ hiểu.
- Khi quan sát trạng thái, xem `Thread.getState()` như **snapshot**, không phải giao thức đồng bộ hoặc bảo đảm thứ tự thực thi.
- Để phân tích chương trình thực, kết hợp thread dump (`jcmd` và công cụ JVM), JFR, log có timestamp và thread name, CPU profiling, thông tin lock contention và metrics latency/throughput. Quan sát có thể làm thay đổi thời điểm thực thi; không suy từ một lần lấy log rằng mọi lần chạy đều giống nhau.
- Muốn kiểm tra tính đúng đắn, đặt bất biến cụ thể: không mất cập nhật, không trùng xử lý, thứ tự nghiệp vụ được bảo vệ, không chờ vô hạn. Kiểm thử nhiều lịch và tải khác nhau, đồng thời xem xét happens-before và các điểm chia sẻ trạng thái trong code review.
- Với benchmark, dùng môi trường và workload đại diện, warm-up JVM, nhiều lần đo. Những lần chạy có kết quả biến thiên không tự chứng minh một vấn đề scheduling; cần xác định nút thắt và đo đồng bộ/lock/I/O/GC.

## 11. Checklist trước khi phụ thuộc vào thứ tự giữa các thread

1. **Có yêu cầu thứ tự thật không?** Nếu task độc lập, ưu tiên thiết kế không phụ thuộc thứ tự hoàn tất.
2. **Sự kiện nào tạo quan hệ trước/sau?** `start()`, `join()`, latch, lock, queue, `Future` hay một giao thức cụ thể phải được dùng đúng.
3. **Dữ liệu có được công bố an toàn không?** Chứng minh happens-before hoặc sử dụng primitive atomic/synchronized/volatile phù hợp; không chỉ dựa vào việc “nó thường chạy trước”.
4. **Có khả năng treo không?** Kiểm tra vòng chờ, lock contention, timeout, interrupt và đường lỗi khiến tín hiệu kết thúc không bao giờ phát ra.
5. **Kết quả có đúng trên mọi lịch hợp lệ không?** Tránh giả định thứ tự `println`, thời điểm `sleep` kết thúc, hiệu lực `yield` hoặc thứ tự thread priority.
6. **Quan sát có đủ tin cậy không?** Dựa vào bất biến, bằng chứng đồng bộ và đo workload; log hoặc một lần chạy chỉ là ảnh chụp.

**Ghi nhớ:** scheduling trong Java mang tính bất định ở chỗ chương trình không thể dựa vào lịch thực thi cụ thể của các thread độc lập. Tính đúng đắn được xây dựng bằng quan hệ đồng bộ và dữ liệu an toàn, để chương trình vẫn cho kết quả hợp lệ dù JVM/OS chọn thứ tự chạy khác nhau.