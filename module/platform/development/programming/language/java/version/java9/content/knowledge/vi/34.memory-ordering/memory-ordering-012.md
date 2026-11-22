# Kiểm thử tranh chấp và tránh kết luận từ một lần chạy

Kiểm thử đồng thời khó hơn kiểm thử tuần tự vì kết quả phụ thuộc vào cách các thread được lập lịch, thứ tự truy cập bộ nhớ và những quan hệ *happens-before* được thiết lập. Một lỗi race condition có thể chỉ xuất hiện khi hai thao tác chồng lấn đúng thời điểm; một bài test chạy thành công một lần không chứng minh rằng chương trình không có lỗi.

Muốn kiểm thử đáng tin cậy, cần kết hợp ba cách tiếp cận: điều khiển interleaving để tái hiện một tình huống cụ thể, stress test để tăng cơ hội gặp các lịch chạy khác nhau, và phân tích các outcome được Java Memory Model cho phép. Mỗi cách cung cấp một loại bằng chứng khác nhau; không cách nào thay thế hoàn toàn việc lập luận về tính đúng đắn.

## 1. Phân biệt race condition và data race

**Race condition** là lỗi logic mà kết quả phụ thuộc vào thứ tự hoặc thời điểm các thao tác đồng thời. Ví dụ, hai thread cùng kiểm tra số lượng chỗ trống rồi cùng đặt chỗ, khiến số lượng đặt vượt giới hạn.

**Data race** là tình huống hai thao tác truy cập cùng một biến, ít nhất một thao tác là ghi, và các thao tác đó không được sắp thứ tự bằng quan hệ happens-before. Data race có thể làm một thread quan sát giá trị cũ hoặc tạo ra trạng thái mà chương trình không dự kiến.

Hai khái niệm liên quan nhưng không đồng nghĩa. Một race condition có thể xuất hiện ngay cả khi từng biến được truy cập thread-safe, nếu một chuỗi thao tác nhiều bước không nguyên tử. Ngược lại, data race là dấu hiệu cần xem xét rất nghiêm túc theo Java Memory Model.

Ví dụ `count++` gồm đọc, cộng và ghi. Dù biến `count` được khai báo `volatile`, cả biểu thức vẫn không phải một thao tác nguyên tử. Hai thread có thể cùng đọc một giá trị rồi ghi cùng kết quả, làm mất một lần tăng. Dùng `AtomicInteger.incrementAndGet()`, `VarHandle` CAS hoặc lock phù hợp với invariant.

## 2. Vì sao một lần chạy không đủ?

Thread scheduler có thể chọn thứ tự thực thi khác nhau giữa các lần chạy. Kết quả còn chịu ảnh hưởng của số lõi CPU, tải hệ thống, JIT compilation, garbage collection, runtime, kiến trúc CPU và những thao tác đồng bộ khác trong chương trình.

Một test có thể chạy hàng nghìn lần mà không gặp interleaving gây lỗi. Điều đó chỉ cho thấy lỗi chưa xuất hiện trong những lịch chạy đã quan sát. Nó không chứng minh rằng lịch chạy đó không thể xảy ra.

Ngược lại, thêm `System.out.println()`, debugger hoặc `Thread.sleep()` có thể làm thay đổi timing và khiến lỗi biến mất hoặc xuất hiện thường xuyên hơn. Việc thay đổi timing không tạo ra một hợp đồng đồng bộ đáng tin cậy.

Vì vậy, không kết luận rằng code thread-safe chỉ vì:

- Chạy thử một lần và nhận kết quả đúng.
- Chạy nhiều lần trên một máy x86 và không thấy lỗi.
- Thêm `sleep()` giữa hai thao tác rồi lỗi không còn xuất hiện.
- Chỉ kiểm thử với một thread hoặc một lượng dữ liệu nhỏ.
- Một test stress không quan sát được outcome sai.

## 3. Dùng synchronization primitive để điều khiển interleaving

Thay vì hy vọng scheduler tạo ra đúng thứ tự cần kiểm tra, hãy chủ động điều phối thread bằng các công cụ đồng bộ:

- `CountDownLatch`: một hoặc nhiều thread chờ cho đến khi một số thao tác đã sẵn sàng hoặc một sự kiện xảy ra.
- `CyclicBarrier`: nhiều thread cùng chờ tại một điểm rồi tiếp tục khi đủ số bên tham gia.
- `Phaser`: điều phối nhiều phase khi số bên tham gia có thể thay đổi.
- `Semaphore`: giới hạn số thread được đi qua một vùng hoặc sử dụng một tài nguyên cùng lúc.
- `Exchanger`: trao đổi dữ liệu giữa hai thread tại một điểm đồng bộ.
- `Future.get()` hoặc `Thread.join()`: chờ tác vụ kết thúc và tạo ranh giới quan sát kết quả.

Ví dụ, để tái hiện lost update, cho cả hai thread đọc giá trị ban đầu trước, rồi mới mở cổng cho cả hai ghi. `CountDownLatch` giúp buộc thứ tự đó mà không cần `sleep()`.

```text
Thread A: read 0 ---- wait ---- write 1
Thread B: read 0 ---- wait ---- write 1
                         ^
              main opens write gate

Kết quả plain counter: 1 thay vì 2
```

Đây là test có điều khiển cho một interleaving cụ thể. Nó không phụ thuộc vào việc scheduler có tình cờ chạy hai phép đọc cùng lúc hay không.

## 4. Stress test: tăng số lần và mức tranh chấp

Stress test chạy nhiều thread cùng thực hiện thao tác trong một khoảng thời gian hoặc số vòng lặp lớn. Mục tiêu là tăng số interleaving được thử và làm lộ lỗi hiếm gặp.

Ví dụ với bộ đếm nguyên tử:

```java
AtomicInteger counter = new AtomicInteger();

Runnable task = () -> {
    for (int i = 0; i < 100_000; i++) {
        counter.incrementAndGet();
    }
};
```

Khi hai task hoàn tất, kết quả kỳ vọng là `200_000`. Nếu dùng `int` thường với `count++` mà không có đồng bộ, kết quả có thể thấp hơn. Tuy nhiên, stress test không nên dựa vào việc plain counter chắc chắn sai ở mọi lần chạy; một lần chạy có thể tình cờ không làm lộ lost update.

Để stress test có ý nghĩa:

1. Dùng nhiều worker thay vì chỉ hai thread nếu workload thực tế có nhiều bên tranh chấp.
2. Tăng số vòng lặp đủ lớn nhưng vẫn giữ thời gian test có giới hạn.
3. Bắt đầu các worker gần nhau bằng barrier hoặc latch để tăng mức chồng lấn.
4. Kiểm tra invariant cuối cùng, không chỉ kiểm tra một giá trị trung gian.
5. Lặp test trong nhiều process hoặc nhiều lượt CI để khám phá thêm lịch chạy.
6. Thử trên các JDK, hệ điều hành và kiến trúc CPU mà ứng dụng hỗ trợ.
7. Thu thập lỗi từ mọi worker bằng `Future.get()` hoặc cơ chế tương đương; không để exception trong worker bị bỏ qua.

Stress test giúp tăng độ tin cậy thực nghiệm nhưng không chứng minh rằng mọi interleaving đều đúng. Với lỗi liên quan memory ordering, cần xem xét cả outcome mà Java Memory Model cho phép.

## 5. Kiểm thử theo Java Memory Model

Java Memory Model (JMM) quy định khi nào một thao tác ghi được bảo đảm nhìn thấy bởi thread khác và những thứ tự nào được phép. Khi thiết kế test, hãy xác định các quan hệ happens-before thay vì suy luận chỉ từ thứ tự dòng code.

Một số quan hệ quan trọng:

- Các thao tác trong cùng một thread được sắp theo program order.
- Một thao tác ghi vào `volatile` synchronizes-with các lần đọc tiếp theo của cùng biến volatile đó.
- Mở khóa monitor happens-before lần khóa monitor tiếp theo trên cùng monitor.
- Gọi `Thread.start()` happens-before các thao tác trong thread được khởi chạy.
- Các thao tác của thread hoàn tất happens-before thread khác phát hiện thread đó đã kết thúc qua `join()`.
- Các hành động trước `CountDownLatch.countDown()` happens-before các hành động sau khi một thread khác `await()` thành công trên latch đó.
- Các hành động trong tác vụ bất đồng bộ happens-before các hành động sau khi caller nhận kết quả qua `Future.get()` thành công theo memory consistency effect của Future.

Với VarHandle, `setRelease()` và `getAcquire()` có thể tạo quan hệ công bố dữ liệu: thread ghi payload trước release, sau đó ghi cờ; thread đọc cờ bằng acquire và thấy giá trị release tương ứng thì các thao tác đọc sau acquire có thể quan sát payload đã được công bố.

### Không kiểm tra một outcome vốn vẫn được phép

Giả sử hai thread ghi hai biến độc lập mà không có synchronization. Nếu test yêu cầu một thread luôn nhìn thấy cả hai giá trị mới chỉ vì thread ghi đã chạy trước theo thời gian thực, test đang giả định một quan hệ happens-before không tồn tại.

Trước khi viết assertion, hãy xác định:

1. Outcome nào bị cấm bởi JMM?
2. Outcome nào vẫn được phép vì thiếu synchronization?
3. Test đang thiết lập quan hệ happens-before nào?
4. Assertion có phụ thuộc vào thứ tự thực thi không được bảo đảm hay không?

Nếu nhiều outcome đều hợp lệ, test phải chấp nhận tập outcome hợp lệ thay vì ép một kết quả duy nhất. Không quan sát thấy outcome hiếm trong một lần chạy không có nghĩa outcome đó bị JMM cấm.

## 6. Kiểm tra visibility riêng với atomicity

Visibility và atomicity là hai yêu cầu khác nhau:

- **Visibility:** thread đọc có nhìn thấy dữ liệu được thread khác công bố hay không.
- **Atomicity:** thao tác có được thực hiện như một đơn vị không thể bị xen giữa hay không.
- **Ordering:** các thao tác trước và sau có bị quan sát theo thứ tự mà hợp đồng memory model quy định hay không.

`volatile` hỗ trợ visibility và ordering cho các lần đọc/ghi volatile, nhưng không biến chuỗi `read → modify → write` thành một thao tác nguyên tử. `AtomicInteger.incrementAndGet()` cung cấp phép tăng nguyên tử. `VarHandle` cho phép chọn access mode như acquire/release hoặc compare-and-set phù hợp với thuật toán.

Test cần kiểm tra đúng thuộc tính. Một test thấy payload mới không tự chứng minh phép cập nhật compound là atomic; một test thấy counter cuối đúng cũng không tự chứng minh mọi trường dữ liệu liên quan được publish đúng thứ tự.

## 7. Ví dụ Java hoàn chỉnh: điều khiển race, stress counter và release/acquire

Chương trình dưới đây có ba phần:

1. Dùng hai latch để buộc hai thread cùng đọc giá trị `0` trước khi được phép ghi, qua đó tái hiện lost update một cách xác định.
2. Dùng hai thread tăng `AtomicInteger` tổng cộng 200.000 lần và kiểm tra kết quả sau khi cả hai task kết thúc.
3. Dùng `VarHandle.setRelease()` và `getAcquire()` để công bố một payload trước khi thread đọc tiếp nhận cờ.

Tạo tệp `ConcurrencyEvidenceDemo.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencyEvidenceDemo {
    private static int plainValue;
    private static int payload;
    private static int readyFlag;
    private static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup().findStaticVarHandle(
                    ConcurrencyEvidenceDemo.class, "readyFlag", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static void demonstrateControlledLostUpdate(ExecutorService executor)
            throws Exception {
        plainValue = 0;
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Future<?> first = executor.submit(() -> {
            int observed = plainValue;
            bothRead.countDown();
            if (!allowWrite.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Write gate timed out");
            }
            plainValue = observed + 1;
            return null;
        });
        Future<?> second = executor.submit(() -> {
            int observed = plainValue;
            bothRead.countDown();
            if (!allowWrite.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Write gate timed out");
            }
            plainValue = observed + 1;
            return null;
        });

        if (!bothRead.await(5, TimeUnit.SECONDS)) {
            allowWrite.countDown();
            throw new IllegalStateException("Workers did not reach the read gate");
        }
        allowWrite.countDown();
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        System.out.println("Controlled plain increment result: " + plainValue);
    }

    private static void demonstrateAtomicContention(ExecutorService executor)
            throws Exception {
        AtomicInteger counter = new AtomicInteger();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Future<?> first = executor.submit(() -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timed out");
            }
            for (int i = 0; i < 100_000; i++) {
                counter.incrementAndGet();
            }
            return null;
        });
        Future<?> second = executor.submit(() -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timed out");
            }
            for (int i = 0; i < 100_000; i++) {
                counter.incrementAndGet();
            }
            return null;
        });

        if (!ready.await(5, TimeUnit.SECONDS)) {
            start.countDown();
            throw new IllegalStateException("Workers did not become ready");
        }
        start.countDown();
        first.get(10, TimeUnit.SECONDS);
        second.get(10, TimeUnit.SECONDS);
        System.out.println("Atomic increment result: " + counter.get());
    }

    private static int awaitPublishedPayload(CountDownLatch readerStarted)
            throws InterruptedException {
        readerStarted.countDown();
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while ((int) READY.getAcquire() == 0) {
            if (System.nanoTime() - deadline >= 0) {
                throw new IllegalStateException("Publication timed out");
            }
            Thread.onSpinWait();
        }
        return payload;
    }

    private static void demonstrateReleaseAcquire(ExecutorService executor)
            throws Exception {
        payload = 0;
        readyFlag = 0;
        CountDownLatch readerStarted = new CountDownLatch(1);
        Future<Integer> reader = executor.submit(
                () -> awaitPublishedPayload(readerStarted));

        if (!readerStarted.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Reader did not start");
        }
        Future<?> writer = executor.submit(() -> {
            payload = 42;
            READY.setRelease(1);
            return null;
        });

        writer.get(5, TimeUnit.SECONDS);
        System.out.println("Release/acquire payload: " + reader.get(5, TimeUnit.SECONDS));
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            demonstrateControlledLostUpdate(executor);
            demonstrateAtomicContention(executor);
            demonstrateReleaseAcquire(executor);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all ConcurrencyEvidenceDemo.java
java ConcurrencyEvidenceDemo
```

Kết quả stdout:

```text
Controlled plain increment result: 1
Atomic increment result: 200000
Release/acquire payload: 42
```

Ở phần đầu, cả hai worker phải đọc `plainValue` trước khi main thread mở `allowWrite`. Vì vậy cả hai cùng tính `0 + 1` và ghi `1`; một lần tăng bị mất. Đây là interleaving được điều khiển bằng latch, không phải kết quả tình cờ của scheduler.

Ở phần hai, hai worker bắt đầu sau khi cùng báo sẵn sàng. `AtomicInteger` bảo đảm từng lần tăng là nguyên tử nên tổng cuối là `200000`. `Future.get()` chờ hai task kết thúc và cho phép main thread kiểm tra kết quả.

Ở phần ba, writer ghi `payload` trước `setRelease(1)`. Reader lặp `getAcquire()` đến khi thấy `1`, rồi mới đọc payload. Khi acquire đọc giá trị đã được release công bố, payload ghi trước release được nhìn thấy theo memory semantics của cặp thao tác đó.

Chương trình dùng timeout cho latch và Future để test thất bại rõ ràng nếu worker không tiến triển. Executor được shutdown trong `finally`. Timeout ở test là giới hạn bảo vệ test khỏi treo; nó không phải cách đồng bộ hóa dữ liệu.

## 8. Những cách viết test dễ gây kết luận sai

### Dùng `Thread.sleep()` để ép thứ tự

`sleep()` chỉ tạm dừng thread hiện tại. Nó không tạo quan hệ happens-before giữa các thao tác dữ liệu và không bảo đảm thread khác đã chạy đến một vị trí cụ thể. Dùng latch, barrier hoặc giao thức đồng bộ rõ ràng để điều khiển thứ tự.

### Dựa vào `println()` để kiểm tra visibility

In log làm thay đổi timing và có thể tạo thêm đồng bộ trong implementation của stream. Không dùng thứ tự dòng log như bằng chứng duy nhất về visibility hoặc atomicity. Hãy thu thập kết quả vào biến/queue phù hợp rồi kiểm tra sau khi các task kết thúc.

### Bỏ qua exception trong worker

Nếu tạo `Thread` thủ công rồi không chuyển exception về thread kiểm thử, test có thể vẫn báo thành công dù worker đã thất bại. Dùng `ExecutorService.submit()` và gọi `Future.get()`; hoặc dùng framework test có cơ chế thu thập lỗi từ mọi worker.

### Không giới hạn thời gian chờ

Một deadlock trong test có thể làm CI treo vô hạn. Dùng timeout cho latch, barrier, Future và chờ executor; khi thất bại, giải phóng cổng đang chờ, hủy task nếu phù hợp và shutdown executor.

### Assert một interleaving ngẫu nhiên

Không viết test yêu cầu scheduler phải tạo đúng một lịch chạy chỉ vì thứ tự dòng code có vẻ như vậy. Nếu cần một lịch chạy cụ thể, điều khiển nó bằng synchronization primitive. Nếu mục tiêu là khám phá nhiều lịch chạy, dùng stress test và chấp nhận rằng test có thể không tái hiện mọi lịch.

### Nhầm kiểm thử đúng đắn với benchmark

Thời gian chạy một test không phải phép đo hiệu năng đáng tin cậy. JIT, warm-up, GC, scheduler và tải máy ảnh hưởng lớn đến thời gian. Kiểm tra correctness bằng assertion và invariant; đo hiệu năng bằng benchmark harness như JMH với thiết kế benchmark phù hợp.

## 9. Công cụ kiểm thử chuyên biệt

Với thuật toán lock-free hoặc câu hỏi về outcome của Java Memory Model, có thể dùng OpenJDK **jcstress**. Đây là harness chuyên cho kiểm thử đồng thời ở mức thấp: khai báo actor, chạy nhiều lần trên JVM/hardware và phân loại các outcome quan sát được theo những trạng thái hợp lệ hoặc đáng ngờ.

jcstress bổ sung bằng chứng thực nghiệm cho các litmus test; nó không thay thế việc hiểu JMM và không chứng minh một outcome là bất khả thi chỉ vì chưa quan sát thấy outcome đó. Hãy dùng phiên bản tương thích với JDK và cấu hình build của dự án.

Với bài toán hiệu năng, dùng JMH thay vì tự đo bằng vòng lặp trong unit test. Một benchmark cần warm-up, fork, kiểm soát dead-code elimination và workload đại diện. Không dùng kết quả benchmark để kết luận tính đúng đắn của thuật toán.

## 10. Kiểm thử trên nhiều môi trường

Kết quả đồng thời có thể khác nhau giữa các máy và runtime. Với thư viện hoặc ứng dụng hỗ trợ nhiều môi trường, nên kiểm tra trên:

- Các phiên bản JDK mà dự án cam kết hỗ trợ.
- Các hệ điều hành và kiến trúc CPU có trong môi trường triển khai, chẳng hạn x86-64 và AArch64.
- Số lượng processor khác nhau và tải nền khác nhau.
- Cấu hình executor, số worker và kích thước dữ liệu gần với production.
- Chế độ chạy CI lặp lại để tăng cơ hội phát hiện lỗi hiếm.

Không cần mọi dự án phải có toàn bộ ma trận này. Chọn môi trường dựa trên phạm vi hỗ trợ và mức độ rủi ro của phần code đồng thời.

## 11. Quy trình kiểm thử đề xuất

1. Viết rõ invariant: điều gì phải luôn đúng sau mọi interleaving?
2. Xác định biến dùng chung, thao tác đọc/ghi và synchronization edge liên quan.
3. Phân tích outcome được JMM cho phép; không giả định thứ tự chỉ dựa vào thời gian thực.
4. Viết test có điều khiển bằng latch/barrier cho interleaving quan trọng.
5. Viết stress test với nhiều worker và đủ số vòng lặp; kiểm tra invariant sau khi mọi task hoàn tất.
6. Với memory-ordering hoặc lock-free code, bổ sung litmus test bằng jcstress khi phù hợp.
7. Thu thập exception từ mọi worker, đặt timeout và luôn giải phóng executor/tài nguyên.
8. Chạy trên các JDK/CPU mục tiêu và lặp trong CI.
9. Dùng JMH riêng nếu cần đo hiệu năng; không trộn benchmark với assertion correctness.
10. Ghi nhận giới hạn bằng chứng: test đã bao phủ những interleaving nào và outcome nào vẫn chưa được kiểm chứng.

## 12. Checklist trước khi tin một test đồng thời

- [ ] Invariant cần bảo vệ được mô tả rõ.
- [ ] Test không dùng `sleep()` làm cơ chế đồng bộ.
- [ ] Interleaving quan trọng được điều khiển bằng latch, barrier hoặc công cụ tương đương.
- [ ] Stress test có nhiều worker, có giới hạn thời gian và kiểm tra kết quả sau khi hoàn tất.
- [ ] Exception từ mọi task đều được chuyển về thread kiểm thử.
- [ ] Các latch, Future và executor đều có timeout/cleanup phù hợp.
- [ ] Assertion chỉ yêu cầu những điều được synchronization và JMM bảo đảm.
- [ ] Visibility, atomicity và ordering được kiểm tra riêng khi cần.
- [ ] Không kết luận an toàn chỉ vì một outcome sai chưa xuất hiện.
- [ ] Benchmark được tách khỏi correctness test.

Kiểm thử đồng thời tốt cần kết hợp interleaving có điều khiển, stress test và lập luận theo Java Memory Model. Một lần chạy đúng chỉ là một quan sát; độ tin cậy đến từ invariant rõ ràng, synchronization đúng, kiểm tra nhiều lịch chạy và hiểu chính xác outcome nào được phép.