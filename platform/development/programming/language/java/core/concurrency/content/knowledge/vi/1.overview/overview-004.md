# Latency, throughput, responsiveness và utilization trong Java concurrency

## Mục tiêu và bối cảnh

Khi đánh giá một chương trình Java chạy nhiều tác vụ đồng thời, “nhanh” có thể mang nhiều nghĩa: một yêu cầu hoàn thành sớm, hệ thống xử lý được nhiều yêu cầu mỗi giây, người dùng thấy ứng dụng phản hồi kịp thời, hay CPU/luồng được sử dụng hiệu quả. Bốn góc nhìn đó lần lượt là **latency**, **throughput**, **responsiveness** và **utilization**. Chúng liên quan với nhau nhưng không thay thế cho nhau.

Sau bài này, bạn có thể:
- Đặt ranh giới và đơn vị đo cho từng chỉ số, phân biệt thời gian chờ hàng đợi với thời gian thực thi.
- Đọc trung vị, p95, p99 và nhận ra vì sao một con số trung bình không mô tả được trải nghiệm xấu nhất của một nhóm người dùng.
- Giải thích vì sao tăng số thread có thể tăng throughput ở tác vụ chờ I/O nhưng không chắc giúp tác vụ tính toán, thậm chí làm latency xấu đi.
- Liên hệ lượng công việc đang xử lý, tốc độ hoàn thành và thời gian phản hồi bằng định luật Little; nhận ra khi hệ thống gần quá tải.
- Tự đo thử các chỉ số trong Java bằng `System.nanoTime()` và `ExecutorService`, rồi diễn giải số liệu đúng giới hạn thí nghiệm.

**Phạm vi:** cơ chế concurrency của Java/JVM nói chung, gồm thread, executor, hàng đợi, CPU và tác vụ chờ I/O. Các cơ chế hoặc cấu hình riêng của Spring thuộc một chương khác.

## 1. Một mô hình thời gian trước khi đo

Giả sử một tác vụ được gửi đến hệ thống tại thời điểm `t0`, bắt đầu được một worker xử lý tại `t1` và hoàn thành tại `t2`.

~~~text
Tác vụ đến/được submit                 Bắt đầu chạy                  Hoàn thành
t0                                    t1                           t2
|-------------- queue wait ------------|--------- execution ---------|
|------------------- latency đo tại ranh giới này ------------------|
~~~

Nếu chỉ xét quãng đường từ lúc submit đến khi kết thúc:
- **Queue wait:** `t1 − t0`. Tác vụ đã được nhận nhưng chưa có worker thực hiện.
- **Execution elapsed time:** `t2 − t1`. Có thể gồm **CPU thực chạy**, chờ khóa, chờ I/O, `sleep`, bị scheduler tạm dừng… Vì vậy “execution elapsed” không đồng nghĩa “CPU time”.
- **Task latency:** `t2 − t0 = queue wait + execution elapsed time`.

Ví dụ tác vụ chờ trong hàng đợi 80 ms rồi mất 40 ms để hoàn tất: latency tính từ lúc submit là **120 ms**, dù đoạn chạy của worker chỉ 40 ms. Nếu đo ở phía người gọi qua mạng, latency còn có thể bao gồm truyền dữ liệu, proxy, serialization và thời gian phía client. Luôn ghi rõ **bắt đầu đo ở đâu, kết thúc đo ở đâu, đối tượng đo là gì**.

Với tác vụ có nhiều giai đoạn (enqueue → gọi dịch vụ khác → đợi lock → tính toán → gửi kết quả), nên đo cả latency toàn phần và thời gian từng giai đoạn. Việc chỉ đặt đồng hồ quanh lời gọi xử lý sau khi đã lấy tác vụ ra khỏi queue có thể che mất nút thắt thật sự.

## 2. Latency: một công việc mất bao lâu?

**Latency** là khoảng thời gian để một đơn vị công việc hoàn thành, tính theo ranh giới đã công bố. Đơn vị thường là ms hoặc µs. Khi nói “latency 100 ms” cần biết đó là latency của lần gọi nào, phía client hay server, có tính hàng đợi không, thành công hay cả lỗi/timeout.

Các thống kê quen thuộc:

| Chỉ số | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| Mean (trung bình) | Tổng thời gian / số mẫu | Dễ bị kéo lên bởi vài yêu cầu rất chậm |
| Median / p50 | Khoảng 50% mẫu có latency không vượt quá giá trị này | Mô tả trải nghiệm điển hình |
| p95 | Khoảng 95% mẫu không vượt quá giá trị này | Thấy rõ hơn phần đuôi chậm |
| p99 | Khoảng 99% mẫu không vượt quá giá trị này | Quan trọng với trải nghiệm hiếm nhưng tệ |
| Max | Mẫu chậm nhất trong tập đã đo | Nhạy với số mẫu và nhiễu |

Ví dụ có 100 yêu cầu, 95 yêu cầu hoàn thành trong khoảng 20–40 ms và 5 yêu cầu mất 800 ms: trung bình có thể trông vẫn chấp nhận được với một số mục tiêu, nhưng p99 sẽ ở vùng khoảng 800 ms. Một giao diện hoặc chuỗi nhiều lời gọi dễ bị ảnh hưởng bởi các trường hợp chậm đột biến này.

**Percentile phụ thuộc tập mẫu và cách tính.** Với mẫu ít, p99 rất kém ổn định; các công cụ dùng nội suy hoặc histogram khác nhau có thể cho số khác nhau. Đừng so hai p99 nếu cửa sổ đo, tập yêu cầu, cách xử lý lỗi hoặc thuật toán percentile khác nhau. Percentile cũng không thể cộng trực tiếp: p95 của bước A cộng p95 của bước B không nhất thiết là p95 của toàn bộ yêu cầu.

Để phân tích latency cao, tách ít nhất: **thời gian nằm trong queue**, **thời gian chờ lock/đồng bộ**, **thời gian chờ I/O**, **thời gian chạy thực tế**. Thời gian tạm dừng do GC, CPU scheduling và khởi động/JIT cũng có thể tạo ra đỉnh latency.

## 3. Throughput: hoàn thành được bao nhiêu việc?

**Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ task/s, request/s, message/s hoặc MB/s:

~~~text
throughput = số công việc hoàn tất trong khoảng đo / độ dài khoảng đo (giây)
~~~

Nếu 600 tác vụ hoàn thành trong 10 giây, throughput quan sát được là 60 task/s. Chọn rõ “hoàn tất” nghĩa là mọi kết quả, chỉ kết quả thành công hay số byte thực truyền. Nên đi kèm **error rate** và **timeout rate**, bởi throughput tính cả yêu cầu thất bại có thể tạo ấn tượng sai về năng lực phục vụ hữu ích.

Phân biệt:
- **Arrival rate / offered load (λ):** số tác vụ đi vào mỗi giây.
- **Completion throughput (X):** số tác vụ kết thúc mỗi giây.
- **Capacity:** tốc độ mà hệ thống có thể duy trì với mục tiêu latency và tỷ lệ lỗi đã chọn, dưới workload và cấu hình xác định.

Ở trạng thái ổn định, không thất thoát tác vụ và hàng đợi không tăng dài hạn, tốc độ vào gần với tốc độ ra. Khi 120 request/s liên tục đi vào nhưng chỉ 90 request/s được xử lý xong, trung bình backlog tăng khoảng **30 request mỗi giây** cho đến khi có cơ chế từ chối, timeout, rớt tác vụ hoặc tải thay đổi. Một khoảng đo ngắn có thể cho throughput cao nhờ xả backlog cũ; nó chưa chứng minh năng lực duy trì.

Đo throughput phải nêu kích thước công việc: 10 tác vụ đọc cache không tương đương 10 truy vấn đĩa hay 10 phép mã hóa nặng. So số task/s của hai hệ thống có input khác nhau thường vô nghĩa.

## 4. Responsiveness: khả năng phản hồi kịp thời

**Responsiveness** mô tả hệ thống phản ứng nhanh và nhất quán như thế nào trước tương tác hoặc tín hiệu mới. Nó liên quan đến latency nhưng bao gồm cả **thời điểm có phản hồi đầu tiên**, sự mượt mà và khả năng tiếp tục phục vụ khi một công việc dài còn chạy.

Ví dụ:
- Một giao diện Java desktop nhận lệnh rồi chạy xử lý nặng trên luồng giao diện: tổng công việc có thể xong sau 2 giây, nhưng cửa sổ bị “đơ” trong cả 2 giây. Đưa công việc sang worker và cập nhật tiến độ giúp giao diện responsive hơn, dù tổng latency hoàn tất không chắc giảm.
- Một dịch vụ xử lý công việc kéo dài có thể nhanh chóng xác nhận “đã nhận” rồi hoàn thành sau. **Time to first acknowledgment** thấp, nhưng **end-to-end completion latency** vẫn dài. Không được đổi tên thời gian xác nhận thành thời gian hoàn tất.
- Khi hủy tác vụ hoặc hệ thống cần shutdown, worker kiểm tra cờ hủy/interrupt đúng cách thường cải thiện responsiveness với thao tác điều khiển, dù throughput của tác vụ thường ngày không đổi.

Responsiveness không có một công thức duy nhất áp dụng cho mọi sản phẩm. Hãy chọn chỉ số đại diện cho lời hứa thực tế: **time to first response**, trễ xử lý sự kiện, thời gian UI không phản hồi, độ trễ hủy tác vụ hoặc tail latency của yêu cầu tương tác. Đừng dùng “có nhiều thread” như bằng chứng rằng hệ thống responsive.

## 5. Utilization: tài nguyên bận đến mức nào?

**Utilization (U)** là tỷ lệ thời gian hoặc năng lực của **một tài nguyên xác định** đang được sử dụng trong cửa sổ đo:

~~~text
U = thời gian tài nguyên bận / thời gian tài nguyên có thể phục vụ
~~~

Ví dụ một CPU core bận chạy tác vụ trong 700 ms của một khoảng 1.000 ms có utilization xấp xỉ **70%** trong khoảng đó. Với máy 4 core, cần nêu cách chuẩn hóa: tiêu thụ trung bình 3 core tương đương khoảng 75% năng lực 4 core; một công cụ có thể hiển thị “300% CPU” khi lấy **100% cho mỗi core**. Cần kiểm tra mẫu số trước khi so số.

Trong Java thường cần phân biệt các tài nguyên sau:

| Tài nguyên đang đo | Chỉ số gần đúng | Không được suy ra |
| --- | --- | --- |
| CPU của tiến trình/hệ thống | Phần trăm CPU hoặc CPU time theo khoảng | 80% CPU không tự cho biết p99 latency |
| Worker thread pool | Số worker đang chạy tác vụ / kích thước pool | Worker đang chờ socket vẫn có thể được tính là active, dù không tiêu CPU |
| Connection pool | Số kết nối đang được mượn / tổng kết nối | Bận kết nối không đồng nghĩa CPU cao |
| Băng thông/đĩa | Tỷ lệ dùng công suất hoặc thời gian thiết bị bận | Thread count không phản ánh trực tiếp tải I/O |
| Lock/critical section | Thời gian giữ lock và số/thời gian chờ | Nhiều thread có thể chỉ làm tăng tranh chấp |

**Thread pool utilization và CPU utilization là hai đại lượng khác nhau.** Với tác vụ chờ I/O, 100% worker bận không nhất thiết là 100% CPU; còn ít worker “active” vẫn có thể có một thread tính toán ngốn trọn một core. `ThreadPoolExecutor.getActiveCount()` và `getQueue().size()` chỉ cung cấp các snapshot xấp xỉ, hữu ích để quan sát xu hướng chứ không phải số đếm tuyến tính hóa tuyệt đối.

Utilization quá thấp có thể là năng lực dư, workload ít, hoặc đang bị chặn bởi khóa/I/O. Utilization cao giúp tận dụng tài nguyên nhưng **không đồng nghĩa hiệu suất tốt**: khi gần bão hòa, hàng đợi có thể tăng mạnh, làm latency và độ biến động xấu đi. Không có một “% CPU lý tưởng” cho mọi hệ thống; cần xét burst, tail latency, độ ưu tiên và mức dự phòng mong muốn.

## 6. Bốn chỉ số ảnh hưởng lẫn nhau như thế nào?

### 6.1. Hàng đợi là mối nối quan trọng

Nếu tốc độ tác vụ đến vượt tốc độ một tài nguyên xử lý trong thời gian đủ dài, hàng đợi tăng. Công việc cũ chiếm chỗ, công việc mới chờ lâu hơn: **latency tăng**, **responsiveness giảm**, còn **throughput có thể đã chạm trần** dù utilization vẫn cao. Tăng thêm công việc hoặc thêm thread trong lúc CPU đã bão hòa thường chỉ làm tranh chấp, chuyển ngữ cảnh và bộ nhớ tệ hơn.

~~~text
Arrival rate tăng
       |
       v
Worker/resource tiến gần giới hạn
       |
       +---- năng lực còn đủ ----> throughput tăng, latency có thể ổn định
       |
       +---- gần/vượt giới hạn --> queue tăng --> p95/p99 latency tăng
                                                 |
                                                 v
                                    timeout, phản hồi chậm, lỗi nhiều
~~~

Nếu có hàng đợi hữu hạn và chính sách từ chối, backlog được giới hạn bằng cách **admission control / backpressure**: phần tải vượt năng lực nhận lỗi hoặc được yêu cầu thử lại. Cách này có thể bảo vệ latency cho tác vụ được nhận, nhưng phải đo riêng tỷ lệ bị từ chối; không được xem throughput thấp do từ chối là hiệu quả tốt.

### 6.2. Định luật Little: số việc trong hệ thống, tốc độ, thời gian

Với **hệ thống ổn định**, cùng ranh giới đo và cùng loại công việc, định luật Little cho:

~~~text
L = λ × W
~~~

- `L`: số công việc trung bình **đang ở trong hệ thống** (chờ + đang chạy).
- `λ`: tốc độ công việc đi qua hệ thống ở trạng thái ổn định, tính bằng công việc/giây.
- `W`: thời gian lưu lại hệ thống trung bình, tính bằng giây.

Ví dụ hệ thống ổn định hoàn thành **120 request/s**, mỗi request có latency trung bình **0,25 s** từ lúc nhận đến lúc xong. Khi đó số request trung bình đang chờ hoặc được thực thi là `L = 120 × 0,25 = 30`.

Dùng công thức đúng cách:
1. Đổi ms ra giây và giữ cùng phạm vi đo; nếu W không tính queue thì L cũng không được tính queue.
2. Sử dụng **trung bình**, không thay W bằng p95/p99 trong công thức.
3. Xem hàng đợi có tăng theo thời gian không. Khi hệ thống liên tục tích backlog, không thể lấy một cửa sổ ngắn rồi coi đó là trạng thái ổn định.
4. Nếu tính cả yêu cầu thất bại, retry hoặc timeout, phải xác định nhất quán khi nào chúng rời hệ thống.

Định luật Little mô tả quan hệ giữa các đại lượng, **không tự chứng minh** tăng concurrency sẽ tăng throughput. Nếu bottleneck là CPU 4 core, thêm vài trăm thread không tạo thêm core.

### 6.3. Utilization từ nhu cầu tài nguyên

Cho một tài nguyên có `m` đơn vị phục vụ tương đương nhau, mỗi công việc tiêu trung bình `D` giây **thời gian bận của một đơn vị tài nguyên**, và tốc độ hoàn tất `X` công việc/giây. Khi cân bằng và workload ổn định, mức utilization trung bình xấp xỉ:

~~~text
U ≈ X × D / m
~~~

Ví dụ tiến trình cần **0,025 CPU-core-second/request**; ở **120 request/s**, tổng nhu cầu là `120 × 0,025 = 3` core bận liên tục. Nếu có 4 core khả dụng cho tiến trình, utilization tương đương khoảng `3/4 = 75%`. Đây là phép tính cho **CPU time**, không được lấy elapsed time 250 ms có chờ mạng rồi thay vào `D` để suy ra CPU utilization.

Công thức gần đúng này giả định định nghĩa CPU capacity/affinity/quota phù hợp và đủ khả năng chạy song song. Đối với thread pool, thời gian bận có thể bao gồm chờ I/O; cần mô hình tài nguyên riêng.

### 6.4. Tăng số thread: khi nào hữu ích?

| Loại công việc | Thêm worker có thể đem lại | Giới hạn hoặc rủi ro |
| --- | --- | --- |
| CPU-bound: mã hóa, tính toán | Tăng parallelism đến khi dùng hết core hữu ích | Vượt core dễ tăng context switching, cache contention và tail latency |
| I/O-bound: chờ file/socket | Cho phép công việc khác chạy trong lúc một worker chờ | Quá nhiều thread/tác vụ có thể làm cạn RAM, connection pool hoặc downstream |
| Tranh chấp lock nặng | Thường không giải quyết bottleneck | Nhiều contender hơn có thể làm queue/latency xấu thêm |
| Workload hỗn hợp | Pool và giới hạn concurrency thích hợp có thể cân bằng | Cần đo riêng queue wait, CPU, I/O và phụ thuộc ngoài |

Từ Java 21, **virtual threads** giúp tạo nhiều tác vụ đồng thời đang chờ theo mô hình thread-per-task với chi phí thread nhỏ hơn trong nhiều tình huống. Chúng **không làm CPU-bound chạy song song vượt năng lực CPU**, và không xóa giới hạn database, socket, lock hay tài nguyên bên ngoài. Ví dụ đo trong phần sau dùng **Java 17+** và platform threads để dễ quan sát.

## 7. Thực hành: đo một batch tác vụ trong Java 17+

Thí nghiệm tạo **12 tác vụ**, mỗi tác vụ `Thread.sleep(120)` để mô phỏng *chờ* trong khoảng 120 ms. Chạy hai lượt với pool 2 và 4 worker; đo thời điểm submit, bắt đầu thực thi, hoàn thành và thời gian toàn batch. Mỗi lần đo dùng đồng hồ đơn điệu `System.nanoTime()`, thích hợp tính **khoảng thời gian** chứ không dùng như timestamp lịch.

Tạo tệp **`ConcurrencyMetricsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ConcurrencyMetricsDemo {
    private record Sample(long queueNs, long runNs, long latencyNs) {}

    private static void experiment(int workers) throws InterruptedException {
        final int taskCount = 12;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        List<Sample> samples = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch completed = new CountDownLatch(taskCount);

        long batchStart = System.nanoTime();
        for (int i = 0; i < taskCount; i++) {
            long submittedAt = System.nanoTime();
            pool.execute(() -> {
                long startedAt = System.nanoTime();
                try {
                    Thread.sleep(120); // Mô phỏng thời gian chờ, không đốt CPU
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    long finishedAt = System.nanoTime();
                    samples.add(new Sample(
                            startedAt - submittedAt,
                            finishedAt - startedAt,
                            finishedAt - submittedAt));
                    completed.countDown();
                }
            });
        }

        completed.await();
        long batchEnd = System.nanoTime();
        pool.shutdown();
        if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
            throw new IllegalStateException("Workers did not terminate");
        }

        List<Long> latencies = samples.stream()
                .map(Sample::latencyNs)
                .sorted()
                .toList();

        int p95Index = (int) Math.ceil(0.95 * latencies.size()) - 1;
        double p95Ms = latencies.get(p95Index) / 1_000_000.0;
        double avgQueueMs = samples.stream()
                .mapToDouble(s -> s.queueNs() / 1_000_000.0)
                .average().orElse(0.0);
        double avgRunMs = samples.stream()
                .mapToDouble(s -> s.runNs() / 1_000_000.0)
                .average().orElse(0.0);
        double throughput = taskCount
                / ((batchEnd - batchStart) / 1_000_000_000.0);

        System.out.printf(Locale.US,
                "workers=%d | throughput=%.1f tasks/s"
                + " | p95=%.1f ms | avgQueue=%.1f ms | avgRun=%.1f ms%n",
                workers, throughput, p95Ms, avgQueueMs, avgRunMs);
    }

    public static void main(String[] args) throws InterruptedException {
        experiment(2);
        experiment(4);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConcurrencyMetricsDemo.java
java ConcurrencyMetricsDemo
~~~

Chương trình in **hai dòng** theo định dạng:

~~~text
workers=2 | throughput=... tasks/s | p95=... ms | avgQueue=... ms | avgRun=... ms
workers=4 | throughput=... tasks/s | p95=... ms | avgQueue=... ms | avgRun=... ms
~~~

Các dấu `...` ở đây **chỉ vị trí số thực đo**, không phải stdout số cố định. Kết quả chịu ảnh hưởng của máy, scheduler, JIT, độ chính xác timer và độ trễ khi bắt đầu thread.

**Cách diễn giải:** khi chỉ có hai worker, nhiều tác vụ phải đợi các đợt trước, nên `avgQueue` và `p95` thường cao hơn. Bốn worker có thể hoàn thành batch sớm hơn, cho throughput batch cao hơn, bởi các tác vụ chủ yếu đang ngủ/chờ. `avgRun` thường gần 120 ms cộng overhead của scheduler; đó là elapsed time của tác vụ, **không phải 120 ms CPU**.

**Giới hạn của thí nghiệm:**
- Đây là phép đo **burst 12 task**, throughput = 12 / thời gian hoàn thành batch; **không phải** capacity ổn định của dịch vụ hoạt động liên tục.
- `Executors.newFixedThreadPool` dùng hàng đợi không giới hạn về cấu trúc; ví dụ phù hợp để học phép đo trên batch nhỏ, **không nên mặc định áp dụng** cho hệ thống chịu tải bất kỳ.
- `p95` của 12 mẫu là phép thống kê học thuật rất nhiễu. Không dùng để khẳng định SLO hay so benchmark thực tế.
- `Thread.sleep` mô phỏng việc worker không tính toán; để thử CPU-bound, cần workload tính toán đủ lớn và đo CPU time thực.
- Chỉ đo tác vụ đã submit thành công; bài toán production còn cần đo lỗi, từ chối tác vụ, timeout, retry, warm-up và phân phối input.

Một cải tiến cho bài tập: bổ sung pool hữu hạn dùng `ThreadPoolExecutor` với `ArrayBlockingQueue` và `RejectedExecutionHandler` rõ ràng; thử tăng tốc độ submit để quan sát queue wait, throughput thành công và rejection cùng lúc. Đặt giới hạn an toàn, tránh tạo tải không kiểm soát.

## 8. Thu thập số liệu đáng tin trên JVM

### Đo đúng thứ cần đo

- Dùng `System.nanoTime()` để tính duration: `end - start`. Không dùng `System.currentTimeMillis()` cho benchmark thời gian rất ngắn vì đồng hồ wall clock có thể bị điều chỉnh và độ phân giải khác.
- Ghi thời gian **submit/enqueue → start → finish**; nếu có API network, bổ sung dấu thời gian **client send → first response → complete** để không trộn hai phía.
- Theo dõi histogram/distribution latency thay vì chỉ một average; giữ cùng cửa sổ đo, tag loại tác vụ, phiên bản, tải và tỷ lệ lỗi.
- Với `ThreadPoolExecutor`, quan sát `getActiveCount()`, `getPoolSize()`, `getQueue().size()`, số hoàn thành và rejection. Các getter cho trạng thái tức thời/xấp xỉ; lấy mẫu theo chu kỳ sẽ hữu ích hơn một snapshot đơn.
- Theo dõi CPU/GC/lock contention bằng công cụ JVM thích hợp như **Java Flight Recorder (JFR)** và **Java Mission Control (JMC)**; có thể dùng `java.lang.management.ThreadMXBean` để xem CPU time theo thread **nếu JVM hỗ trợ và tính năng được bật**. CPU time, wall time và blocked/waited time phục vụ các câu hỏi khác nhau.
- Gắn throughput, latency, CPU, queue depth, error/timeout rate vào **cùng biểu đồ theo thời gian** để hiểu hướng nhân quả: CPU cao trước khi p99 tăng? Queue tăng khi arrival vượt completion? Timeout tăng sau khi queue dài?

### Thiết kế thí nghiệm tải

1. Định nghĩa workload: kích thước dữ liệu, tỷ lệ CPU/I/O, số loại tác vụ, đường đi xử lý, cấu hình JVM và tài nguyên (core, memory, quota).
2. Warm-up đủ để tránh coi chi phí class loading/JIT ban đầu là steady state; nhưng ghi riêng hiệu năng cold start nếu đó là mục tiêu thực tế.
3. Tăng offered load theo nhiều mức và giữ đủ lâu để thấy hệ thống ổn định hoặc backlog tăng. So sánh throughput **thành công**, p50/p95/p99, CPU, queue và lỗi tại mỗi mức.
4. Phân biệt thử tải **open-loop** (gửi theo tốc độ định trước) với **closed-loop** (chờ phản hồi rồi gửi yêu cầu tiếp). Closed-loop có thể tự giảm tốc khi hệ thống chậm, làm kết quả nhìn đẹp sai lệch. Tránh **coordinated omission**: bộ phát tải không ghi nhận quãng thời gian đáng lẽ yêu cầu phải đến nhưng đã không được gửi vì hệ thống bị chậm.
5. Cố định môi trường và đo nhiều lượt; báo cả biến động. Dữ liệu từ laptop đang chạy nhiều tiến trình không đủ để khẳng định capacity production.

### Một bản ghi kiểm thử hữu ích

~~~text
Workload: 80% I/O wait, 20% CPU work; 4 CPU cores; JVM/config cố định
Offered load: 100 request/s, đo trong 5 phút sau warm-up
Completed success: 98 request/s; errors/timeouts: ghi riêng
Latency boundary: client send -> complete
Latency: mean ..., p50 ..., p95 ..., p99 ... (ms)
CPU utilization: ...% / 4 cores; pool active: .../N; queue: ...
Kết luận: xét xu hướng qua nhiều mức tải, chưa kết luận từ một mẫu
~~~

Các dấu `...` là chỗ cần **điền số đo thật**, không phải số liệu được suy đoán.

## 9. Phân tích tình huống thường gặp

| Quan sát đồng thời | Giả thuyết nên kiểm chứng | Hướng điều tra/điều chỉnh |
| --- | --- | --- |
| Throughput gần như đứng yên, CPU gần bão hòa, queue và p99 tăng | CPU đã là bottleneck | Profile CPU, giảm CPU/request, giảm tải được nhận hoặc bổ sung tài nguyên CPU; tránh tăng thread vô tội vạ |
| CPU thấp, worker active gần hết, queue tăng | Worker kẹt I/O hoặc chờ lock/downstream | Đo blocked/waited time, timeout và tài nguyên phụ thuộc; cân nhắc giới hạn concurrency/pool phù hợp |
| Mean latency ổn nhưng p99 tăng mạnh | Tắc nghẽn theo đợt, GC pause, lock, slow I/O hoặc bất cân bằng công việc | Xem histogram, trace theo giai đoạn, JFR và thời điểm hàng đợi tăng |
| Throughput tăng nhưng nhiều timeout/rejection | Tải vào tăng hoặc cơ chế từ chối bắt đầu hoạt động | Báo throughput thành công và tỷ lệ lỗi; xác định capacity theo SLO |
| Tăng worker giúp task chờ I/O nhưng làm CPU-bound chậm hơn | Thêm concurrency đã vượt tài nguyên hữu ích | Tách workload, giới hạn pool, đo chuyển ngữ cảnh/CPU/queue |
| Trả lời “đã nhận” rất nhanh nhưng kết quả thực rất muộn | First response tốt nhưng completion latency kém | Công bố rõ trạng thái, đo hai mốc và khả năng hủy/theo dõi tiến độ |

Đừng suy kết luận chỉ từ một chỉ số. Ví dụ **CPU thấp + p99 cao** không chứng minh hệ thống còn nhiều năng lực: một lock hoặc downstream chậm có thể là nút cổ chai trong khi CPU gần như rảnh.

## 10. Lỗi tư duy phổ biến và nguyên tắc áp dụng

1. **“Nhiều thread hơn nghĩa là nhanh hơn.”** Chỉ đúng trong những giới hạn tài nguyên và loại workload nhất định; CPU-bound, lock contention và áp lực bộ nhớ có thể tệ hơn.
2. **“Throughput cao nghĩa là latency thấp.”** Một hệ thống có thể hoàn thành rất nhiều request/s nhưng vẫn làm từng request đợi lâu trong queue.
3. **“Mean thấp nên mọi người dùng đều hài lòng.”** Cần xem p95/p99, timeout và ranh giới đo.
4. **“100% utilization luôn tốt.”** Gần bão hòa thường giảm khả năng hấp thụ burst; tail latency có thể tăng rất nhanh.
5. **“Thread active tức là CPU bận.”** Thread có thể chờ I/O, `synchronized`, `Lock` hoặc điều kiện.
6. **“Task latency bằng thời gian xử lý sau dequeue.”** Queue wait cũng là phần người gọi phải chờ nếu bắt đầu đo từ lúc submit.
7. **“Một batch benchmark chứng minh công suất duy trì.”** Burst, warm-up, backlog và cơ chế phát tải có thể làm lệch kết quả.
8. **“Chỉ cần tăng timeout.”** Timeout dài hơn có thể giữ nhiều tác vụ trong hệ thống hơn và làm nghẽn tài nguyên; phải tìm bottleneck và chính sách giới hạn tải.

Khi thiết kế chương trình concurrent trong Java, hãy bắt đầu bằng **mục tiêu có thể đo**: ví dụ “p95 completion latency dưới 200 ms ở 150 task/s, lỗi dưới 0,1%, trong điều kiện 4 core và workload đã mô tả”. Sau đó quan sát cả **latency distribution + successful throughput + responsiveness + utilization/queue/error rate**. Các chỉ số chỉ có nghĩa khi cùng ranh giới, cùng khoảng đo và cùng định nghĩa workload.

## Tự kiểm tra

1. Nếu một request chờ 90 ms trong queue và chạy 30 ms, latency từ lúc submit là bao nhiêu? Vì sao không nên báo 30 ms như toàn bộ latency?
2. Hệ thống ổn định hoàn thành 200 task/s và latency trung bình 150 ms. Theo Little, trung bình có bao nhiêu task đang ở trong hệ thống? (Đáp án: `200 × 0,150 = 30`.)
3. Pool có 100% active worker nhưng CPU tiến trình chỉ 15%. Bạn sẽ kiểm tra những thời gian chờ nào trước khi tăng pool?
4. Tại sao không thể cộng p99 của hai bước xử lý để có chính xác p99 của toàn luồng?
5. Với workload CPU-bound trên 4 core, cần quan sát gì trước khi đổi từ 4 sang 64 worker?

**Ghi nhớ:** latency đo **thời gian cho một công việc**, throughput đo **số công việc hoàn thành theo thời gian**, responsiveness đo **khả năng phản hồi kịp thời**, còn utilization đo **mức bận của tài nguyên cụ thể**. Tối ưu concurrency là quản lý quan hệ giữa các chỉ số, bottleneck và mức tải, không phải tối đa một chỉ số độc lập.