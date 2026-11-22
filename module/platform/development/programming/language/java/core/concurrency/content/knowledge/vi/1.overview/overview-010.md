# Khi nào nên dùng tuần tự thay vì đa luồng trong Java?

## 1. Hiểu đúng vấn đề

**Thực thi tuần tự (sequential execution)** là xử lý các bước lần lượt trên một luồng điều khiển: bước trước hoàn tất thì bước tiếp theo mới bắt đầu. **Thực thi đa luồng (multithreading)** cho phép nhiều tác vụ tiến triển trong cùng một khoảng thời gian, có thể thực sự chạy song song trên nhiều lõi CPU hoặc thay phiên nhau khi có tác vụ chờ.

Đa luồng **không mặc định nhanh hơn**. Quyết định phụ thuộc vào kích thước và tính độc lập của công việc, tỷ lệ tính toán so với thời gian chờ I/O, yêu cầu về thứ tự, trạng thái chia sẻ, tài nguyên và hiệu năng thực tế.

Ba khái niệm cần phân biệt:

- **Tuần tự:** một chuỗi công việc được xử lý theo thứ tự; mã thường dễ theo dõi hơn.
- **Đồng thời (concurrency):** nhiều công việc có thể cùng tiến triển, dù chưa chắc đang thực sự chạy cùng lúc.
- **Song song (parallelism):** các phần tính toán thực sự chạy đồng thời trên nhiều lõi hoặc đơn vị thực thi.

Một luồng cũng có thể bị chặn khi gọi I/O. Nhiều luồng cũng có thể không giúp tăng tốc nếu cùng tranh một tài nguyên.

## 2. Khi nào nên ưu tiên tuần tự?

### 2.1. Công việc nhỏ, chi phí mỗi task thấp

Khởi tạo hoặc điều phối nhiều luồng phát sinh chi phí: đưa task vào hàng đợi, chuyển ngữ cảnh, đồng bộ, quản lý kết quả và bộ nhớ. Với vòng lặp nhỏ hoặc phép tính đơn giản, chi phí này có thể lớn hơn thời gian xử lý tác vụ.

Ví dụ, cộng vài trăm số, kiểm tra ít đối tượng hoặc xử lý một cấu hình nhỏ thường nên bắt đầu bằng vòng lặp tuần tự. Không có một mốc số phần tử chung cho mọi chương trình: cùng 1.000 phần tử nhưng mỗi phần tử có thể là một phép cộng hoặc một phép tính đắt đỏ. **Đo theo workload thực**, không quyết định chỉ bằng số phần tử.

### 2.2. Các bước có quan hệ phụ thuộc

Nếu B cần kết quả của A và C cần B, ba bước tạo thành đường phụ thuộc A → B → C. Đưa chúng lên ba luồng không làm đường phụ thuộc biến mất; thay vào đó còn cần cơ chế chờ và chuyển kết quả.

Ví dụ: đọc dữ liệu → kiểm tra tính hợp lệ → tính kết quả → cập nhật một trạng thái dựa trên kết quả. Giữ tuần tự cho phần phụ thuộc giúp thể hiện điều kiện trước/sau rõ ràng. Nếu trong một bước có nhiều nhánh thật sự độc lập, vẫn có thể tách riêng nhánh đó để xử lý đồng thời.

### 2.3. Cần thứ tự chặt chẽ và hành vi dễ dự đoán

Những thao tác cần thứ tự cập nhật, chuỗi chuyển trạng thái, thuật toán có phụ thuộc vị trí hoặc việc ghi vào một tài nguyên phải tuân theo thứ tự thường dễ triển khai tuần tự.

Mã tuần tự có ít lịch thực thi phải xét hơn, thuận tiện để đọc stack trace, tái hiện lỗi và kiểm thử. Tuy nhiên, tuần tự **không tự bảo đảm** thuật toán đúng, transaction an toàn hay dữ liệu bên ngoài không thay đổi.

### 2.4. Có trạng thái mutable dùng chung khó đồng bộ

Nhiều luồng cùng chạy `count++` trên một biến `int` có thể làm mất lượt tăng vì câu lệnh gồm đọc, cộng và ghi; đây không phải một phép nguyên tử. `volatile` giúp bảo đảm một số quy tắc visibility nhưng **không làm `count++` trở nên nguyên tử**.

Với lượng công việc nhỏ và ít yêu cầu throughput, xử lý tuần tự có thể tránh chi phí khóa và rủi ro race. Nếu cần đa luồng, hãy cân nhắc chia nhỏ dữ liệu không chia sẻ, immutable objects, `AtomicInteger`, đồng bộ hoặc collection concurrent thích hợp.

### 2.5. Tài nguyên cuối có thể xử lý từng việc một

Nếu mọi task cùng chờ một khóa, một thiết bị đơn luồng hoặc một tài nguyên có giới hạn chặt, nhiều worker không làm tài nguyên đó nhanh hơn. Hệ thống có thể chỉ thêm hàng đợi, timeout và tiêu thụ bộ nhớ.

Ví dụ, nhiều thao tác cùng cần khóa ghi cho một trạng thái nhỏ: dù chạy trên nhiều luồng, đoạn được bảo vệ vẫn thực thi lần lượt. Tìm **nút thắt thực tế** trước khi tăng số luồng.

### 2.6. Chưa có bằng chứng concurrency giúp đạt mục tiêu

Với job nhỏ, chương trình dòng lệnh, khởi tạo ứng dụng hoặc xử lý ít dữ liệu, giải pháp tuần tự thường là baseline tốt: dễ hiểu, ít lỗi và dễ đo. Hãy giữ cách này nếu nó đã đáp ứng thời gian phản hồi, throughput và mức dùng tài nguyên yêu cầu.

Đây không phải quy tắc “luôn dùng một luồng”. Khi một công việc chờ I/O lâu làm nghẽn công việc khác, hoặc có khối tính toán lớn và độc lập, cần đánh giá các phương án đồng thời.

## 3. Java 17+: ví dụ vòng lặp tuần tự

Tạo tệp `SmallSum.java`:

```java
import java.util.stream.IntStream;

public class SmallSum {
    public static void main(String[] args) {
        int[] values = IntStream.rangeClosed(1, 1_000).toArray();
        long sum = 0;

        for (int value : values) {
            sum += value;
        }

        System.out.println(sum);
    }
}
```

Biên dịch và chạy:

```bash
javac SmallSum.java
java SmallSum
```

Đầu ra:

```text
500500
```

Chương trình cộng 1.000 số nguyên theo thứ tự trong một vòng lặp. Không có yêu cầu nghiệp vụ nào bắt buộc chia thành nhiều task. Có thể thực hiện phép cộng bằng Stream song song trong bài toán khác, nhưng với ví dụ nhỏ này chưa có bằng chứng nó sẽ nhanh hơn. **Đây là minh họa tính đúng đắn, không phải benchmark hiệu năng.**

## 4. Khi nào đa luồng đáng để thử?

| Tình huống | Hướng bắt đầu | Vì sao |
| --- | --- | --- |
| Phép tính đơn giản trên ít phần tử | Tuần tự | Tránh overhead điều phối |
| Các bước phụ thuộc trực tiếp | Tuần tự ở phần phụ thuộc | Luồng khác không xóa phụ thuộc dữ liệu |
| Trạng thái mutable dùng chung, ít tải | Tuần tự hoặc thiết kế lại trạng thái | Giảm race và chi phí đồng bộ |
| Nhiều khối CPU nặng, độc lập, đủ lớn | Thử song song giới hạn | Có thể dùng nhiều lõi CPU |
| Nhiều tác vụ I/O độc lập, thường xuyên chờ | Thử đồng thời giới hạn | Có thể che thời gian chờ |
| Các task cùng tranh một tài nguyên đơn | Đo nút thắt; thường giữ tuần tự | Tài nguyên cuối vẫn là giới hạn |
| Cần đáp ứng công việc khác khi một task chờ | Cân nhắc tách task | Tránh một task làm chặn luồng xử lý |

**CPU-bound:** phần lớn thời gian thực sự dùng CPU. Nếu có nhiều khối độc lập đủ lớn và nhiều lõi, song song có thể hữu ích; nếu số worker quá nhiều so với lõi hữu ích, tranh CPU và chuyển ngữ cảnh có thể gây chậm.

**I/O-bound:** phần lớn thời gian chờ mạng, đĩa hoặc dịch vụ. Đồng thời có thể tận dụng khoảng chờ, nhưng phải giới hạn số kết nối, file descriptor, yêu cầu tới dịch vụ và độ dài hàng đợi.

**Workload hỗn hợp:** cần đo thời gian xử lý và thời gian chờ, CPU, bộ nhớ, connection pool, timeout, throughput và latency. Không chọn số worker chỉ theo một nhãn CPU-bound/I/O-bound.

## 5. Java 17+: so sánh tuần tự với thread pool cho tác vụ chờ

Ví dụ **mô phỏng chờ I/O** bằng `Thread.sleep(120)`. Bốn tác vụ độc lập trả về một chuỗi riêng. Sleep minh họa thời gian chờ có thể chồng lấp, không phải phép đo mạng hoặc ổ đĩa thực.

Tạo tệp `SequentialOrConcurrent.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SequentialOrConcurrent {
    private static String simulateWait(int id) throws InterruptedException {
        Thread.sleep(120);
        return "job-" + id;
    }

    private static List<String> sequential() throws InterruptedException {
        List<String> results = new ArrayList<>();
        for (int id = 1; id <= 4; id++) {
            results.add(simulateWait(id));
        }
        return results;
    }

    private static List<String> concurrent()
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int id = 1; id <= 4; id++) {
                final int taskId = id;
                futures.add(pool.submit(() -> simulateWait(taskId)));
            }

            List<String> results = new ArrayList<>();
            for (Future<String> future : futures) {
                results.add(future.get());
            }
            return results;
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> a = sequential();
        List<String> b = concurrent();
        System.out.println(a);
        System.out.println(b);
        System.out.println("Ket qua tuong duong: " + a.equals(b));
    }
}
```

Biên dịch và chạy:

```bash
javac SequentialOrConcurrent.java
java SequentialOrConcurrent
```

Kết quả xác định khi tất cả tác vụ hoàn tất bình thường:

```text
[job-1, job-2, job-3, job-4]
[job-1, job-2, job-3, job-4]
Ket qua tuong duong: true
```

Bản tuần tự thực hiện bốn khoảng chờ nối tiếp. Thread pool có hai worker cho phép tối đa hai tác vụ tiến triển cùng lúc; các khoảng chờ có thể chồng lên nhau. Danh sách `Future` được duyệt theo **thứ tự gửi task**, do đó kết quả được lắp về đúng thứ tự đó, dù thứ tự hoàn thành thực tế có thể khác. `Future.get()` chờ kết quả task và tạo quan hệ đồng bộ để luồng nhận kết quả nhìn thấy tác dụng của task đã hoàn tất.

Không suy từ ví dụ rằng đa luồng sẽ “nhanh gấp hai”. Thời gian phụ thuộc việc lập lịch, thời gian tạo pool, tải máy và tài nguyên ngoài. Ví dụ đóng pool qua `shutdown()` sau khi đã lấy hết kết quả. Trong ứng dụng dài hạn, cần thêm chiến lược timeout, hủy, xử lý `ExecutionException`/`InterruptedException`, giới hạn hàng đợi, xử lý partial failure và quản lý vòng đời pool.

## 6. Chi phí và rủi ro của đa luồng

**Điều phối:** submit task, xếp hàng, chuyển ngữ cảnh, `Future`, ghép kết quả, đồng bộ. Pool tái sử dụng luồng giúp giảm chi phí tạo luồng liên tục nhưng không xóa toàn bộ overhead.

**Race, visibility, deadlock:** ghi cùng dữ liệu không được bảo vệ có thể mất cập nhật; lock có thể tranh chấp hoặc gây deadlock nếu lấy không nhất quán. Với dữ liệu bất biến, chia sẻ an toàn hơn nhưng vẫn phải xem khả năng tranh tài nguyên bên ngoài.

**Thông lượng và độ trễ:** xử lý được nhiều request/giây không có nghĩa từng request nhanh hơn. Hàng đợi và tranh tài nguyên có thể làm p95/p99 latency xấu đi. Cần đo cả thời gian trung bình, độ trễ đuôi và khả năng chịu tải.

**Tài nguyên:** nhiều platform thread tiêu thụ stack và tài nguyên hệ điều hành; nhiều task cùng lúc cần thêm heap, kết nối, băng thông hoặc file descriptor. Concurrency phải có giới hạn và cơ chế backpressure khi đầu vào nhanh hơn khả năng xử lý.

**Lỗi, timeout và hủy:** khi các task chạy đồng thời, lỗi có thể xuất hiện ở nhiều thời điểm; các task khác có thể vẫn chạy dù một task đã thất bại. Cần định nghĩa hành vi khi timeout, interrupt, cancellation, kết quả một phần và thứ tự áp dụng kết quả.

Java 17 có thể dùng `ExecutorService`, `CompletableFuture` và các primitive concurrent chuẩn của JDK tùy loại công việc. Chọn API nào cũng không thay thế việc chứng minh tính độc lập và đo lợi ích.

## 7. Đo lường trước khi quyết định

1. **Làm baseline tuần tự đúng:** xác định đầu vào, kết quả mong đợi và thời gian thực thi trên workload đại diện.
2. **Phân tích phụ thuộc:** các task có độc lập không, có cập nhật cùng trạng thái, cần thứ tự hay tranh tài nguyên nào không?
3. **Đo điểm nghẽn:** tỷ lệ CPU/I/O wait, lõi CPU hữu ích, memory, số kết nối, hàng đợi, throughput, latency p50/p95/p99 và timeout.
4. **Thử mức đồng thời có giới hạn:** thay đổi số worker từng bước, so sánh kết quả với tuần tự, kiểm tra đúng đắn dưới tải và khả năng hủy/khôi phục.
5. **Cân nhắc tổng chi phí:** nếu chỉ giảm ít thời gian nhưng mã khó debug, quản lý pool và kiểm thử phức tạp đáng kể, giải pháp tuần tự có thể tốt hơn.

Với tính toán song song, **định luật Amdahl** cho một ước lượng giới hạn lý tưởng: nếu tỷ lệ có thể song song hóa là `p` và có `k` đơn vị tính toán, thì:

```text
Speedup <= 1 / ((1 - p) + p / k)
```

Ví dụ `p = 0,8` và `k = 4` cho giới hạn lý tưởng `1 / (0,2 + 0,8 / 4) = 2,5` lần, chưa tính chi phí thêm. Phần tuần tự càng lớn, tăng worker càng ít tác dụng. Công thức này minh họa giới hạn song song tính toán và không trực tiếp dự đoán tốc độ che thời gian chờ I/O.

Không dùng một lần chạy `System.nanoTime()` của ví dụ nhỏ để kết luận microbenchmark JVM: JIT compilation, warm-up, tối ưu hóa, GC và nhiễu môi trường đều ảnh hưởng. Dùng JMH cho microbenchmark Java (warm-up, nhiều lượt đo, đầu vào đại diện) và dùng load test/metrics thật cho hệ thống I/O.

## 8. Ngộ nhận và lỗi phổ biến

- **“Thêm luồng luôn nhanh hơn.”** Sai nếu task quá nhỏ, phụ thuộc, tranh CPU, khóa hoặc tài nguyên cuối.
- **“Tuần tự luôn chậm.”** Sai khi làm ít việc hoặc chi phí chia/ghép task vượt lợi ích.
- **“Có nhiều thread là chạy song song.”** Scheduler có thể xen kẽ; số lõi và nút thắt mới quyết định.
- **“`volatile` làm `count++` an toàn.”** Sai, vì read–modify–write không nguyên tử.
- **“`parallelStream()` là cách tăng tốc mặc định.”** Sai khi việc nhỏ, chia không đều, có side effects hoặc nhiều task cùng tranh pool/tài nguyên.
- **“Sleep demo chứng minh hiệu năng production.”** Sai; `Thread.sleep` chỉ cho thấy khả năng chồng lấp thời gian chờ.
- **“Task không chia sẻ biến nên muốn tạo bao nhiêu thread cũng được.”** Sai, các task vẫn cùng dùng CPU, memory, kết nối và quota dịch vụ.

## 9. Checklist lựa chọn

**Chọn tuần tự trước** khi task nhỏ, các bước phụ thuộc nhau, thứ tự xử lý là ràng buộc chính, trạng thái mutable chia sẻ khó quản lý, tài nguyên cuối thực thi từng việc một hoặc chưa đo được lợi ích rõ ràng của đa luồng.

**Cân nhắc đa luồng giới hạn** khi có nhiều tác vụ đủ lớn và độc lập, có khả năng tận dụng lõi CPU hoặc chồng lấp I/O wait, và đã thiết kế giới hạn worker, cách xử lý lỗi/timeout, kiểm soát tài nguyên và kiểm thử concurrency.

Bắt đầu bằng lời giải tuần tự **đúng và đo được**, xác định điểm nghẽn, rồi chỉ tăng concurrency ở phần độc lập cần tăng tốc. Chọn theo kết quả workload thực tế, không theo số luồng càng nhiều càng tốt.