# Giới hạn của virtual thread đối với tác vụ CPU-bound

Virtual thread giúp ứng dụng Java xử lý nhiều tác vụ đồng thời khi các tác vụ thường xuyên chờ I/O. Nó không làm một phép tính chạy nhanh hơn và không tạo thêm năng lực xử lý CPU. Với tác vụ CPU-bound, thời gian chạy chủ yếu dùng để thực hiện lệnh tính toán; số lõi CPU và khả năng xử lý song song của máy mới là giới hạn chính.

Trong Java 21, Virtual Threads đã là tính năng chính thức theo JEP 444. Oracle khuyến nghị dùng chúng cho tác vụ có phần lớn thời gian bị chặn, thường là chờ I/O, và không xem chúng là lựa chọn cho phép tính CPU-intensive kéo dài. Bài học này giải thích nguyên nhân, các giới hạn khi tạo nhiều virtual thread cho công việc tính toán và cách phối hợp virtual thread với executor dành riêng cho CPU.

## 1. Phân biệt tác vụ CPU-bound và I/O-bound

Hai loại tác vụ có đặc điểm chờ đợi khác nhau:

| Loại tác vụ | Phần lớn thời gian | Ví dụ |
|---|---|---|
| CPU-bound | CPU đang thực thi phép tính | Mã hóa dữ liệu, nén ảnh, tính toán số học, phân tích dữ liệu lớn, xử lý đồ thị |
| I/O-bound | Chờ tài nguyên bên ngoài hoặc thao tác I/O hoàn tất | Gọi HTTP, truy vấn cơ sở dữ liệu, đọc socket, chờ message hoặc file |

Một yêu cầu web có thể gồm cả hai phần: tải dữ liệu từ dịch vụ khác là I/O-bound; giải mã, tính điểm hoặc tạo báo cáo trên dữ liệu nhận được là CPU-bound. Không nhất thiết phải dùng cùng một kiểu executor cho toàn bộ vòng đời yêu cầu.

Ví dụ một tác vụ tính số nguyên tố đến một giới hạn chủ yếu dùng CPU:

```java
static long countPrimes(int limit) {
    long count = 0;

    for (int number = 2; number <= limit; number++) {
        boolean prime = true;

        for (int divisor = 2; divisor <= number / divisor; divisor++) {
            if (number % divisor == 0) {
                prime = false;
                break;
            }
        }

        if (prime) {
            count++;
        }
    }

    return count;
}
```

Trong vòng lặp trên, chương trình liên tục thực hiện phép chia, phép nhân và kiểm tra điều kiện. Nếu không có I/O hoặc thao tác blocking đáng kể, virtual thread không có cơ hội nhường carrier để carrier chạy một tác vụ khác trong lúc chờ.

## 2. Virtual thread không tăng tốc phép tính

Virtual thread là một đối tượng `Thread` nhẹ do Java runtime lập lịch. Khi chạy, nó được mount lên một platform thread gọi là *carrier thread*. CPU thực thi mã Java trên carrier đó; virtual thread không sở hữu một lõi CPU riêng.

Khi virtual thread thực hiện một thao tác blocking được runtime hỗ trợ, nó có thể unmount khỏi carrier. Carrier sau đó có thể chạy virtual thread khác trong khi tác vụ ban đầu chờ I/O. Đây là lý do nhiều tác vụ I/O có thể cùng tồn tại mà không cần một platform thread riêng cho mỗi tác vụ.

Với phép tính CPU-bound kéo dài, virtual thread tiếp tục chạy trên carrier và sử dụng CPU. Nó không tự unmount chỉ vì đã tiêu thụ một khoảng thời gian CPU. Vì vậy:

- Một tác vụ tính toán đơn lẻ không chạy nhanh hơn chỉ vì được tạo bằng `Thread.ofVirtual()`.
- Nhiều virtual thread cùng tính toán vẫn phải chia sẻ số lõi CPU hiện có.
- Tạo số lượng virtual thread lớn hơn số lõi không làm tổng năng lực tính toán tăng tương ứng.
- Khi các carrier đều đang chạy tác vụ CPU-bound, những virtual thread khác có thể phải chờ được chạy.

Trong JDK 21, scheduler của virtual thread không thực hiện time-slicing để cưỡng bức dừng một virtual thread chỉ vì nó đã dùng CPU lâu. Một virtual thread thường rời carrier khi hoàn tất hoặc khi gặp điểm blocking có thể unmount. Do đó, tác vụ tính toán dài có thể chiếm carrier lâu và làm tăng độ trễ của tác vụ khác đang chờ scheduler.

Mặc định, target parallelism của scheduler virtual thread dựa trên số processor mà JVM nhìn thấy qua `Runtime.getRuntime().availableProcessors()`. Đây là số platform thread mục tiêu dùng để chạy virtual thread, không phải số CPU mới được tạo ra. Tăng target parallelism không tạo thêm lõi vật lý và thường không giúp một workload CPU-bound đạt throughput cao hơn.

## 3. Vì sao tạo thật nhiều virtual thread cho CPU-bound không hiệu quả?

Có thể tạo một virtual thread cho mỗi tác vụ tính toán:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 100_000; i++) {
        int input = i;
        executor.submit(() -> countPrimes(input + 100_000));
    }
}
```

Đoạn code có thể tạo và quản lý rất nhiều virtual thread, nhưng executor này không phải CPU pool có giới hạn. `newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task và số thread có thể tạo là không giới hạn bởi executor.

Khi task chủ yếu tính toán:

1. Các virtual thread cần được scheduler đưa lên một số lượng carrier hữu hạn.
2. Một virtual thread đang chạy phép tính dài tiếp tục chiếm carrier.
3. Các task còn lại phải chờ đến khi carrier sẵn sàng.
4. Tạo thêm virtual thread làm tăng số task và tài nguyên cần quản lý, nhưng không tăng số phép tính CPU có thể hoàn thành đồng thời vượt quá năng lực phần cứng.

Điều này có thể làm tăng bộ nhớ sử dụng, thời gian chờ trong scheduler và độ trễ hoàn tất toàn bộ batch. Virtual thread nhẹ hơn platform thread, nhưng không miễn phí và cũng không phải cơ chế giới hạn tải.

`newVirtualThreadPerTaskExecutor()` phù hợp khi mỗi task thường xuyên chờ I/O. Nếu dùng nó để nhận một lượng công việc CPU không giới hạn từ bên ngoài, ứng dụng vẫn có nguy cơ tích lũy quá nhiều công việc đang chờ và gây quá tải.

## 4. Dùng executor có số worker phù hợp cho CPU-bound

Với tập tác vụ tính toán độc lập, một lựa chọn phổ biến là fixed thread pool gồm platform thread. Có thể dùng số processor JVM nhìn thấy làm điểm bắt đầu, sau đó đo đạc và điều chỉnh theo workload thực tế:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CpuBoundTasks {
    static long countPrimes(int limit) {
        long count = 0;

        for (int number = 2; number <= limit; number++) {
            boolean prime = true;

            for (int divisor = 2; divisor <= number / divisor; divisor++) {
                if (number % divisor == 0) {
                    prime = false;
                    break;
                }
            }

            if (prime) {
                count++;
            }
        }

        return count;
    }

    public static void main(String[] args) throws Exception {
        int workers = Runtime.getRuntime().availableProcessors();
        List<Integer> inputs = List.of(500_000, 600_000, 700_000, 800_000);

        try (ExecutorService cpuExecutor =
                     Executors.newFixedThreadPool(workers)) {
            List<Future<Long>> results = new ArrayList<>();

            for (int limit : inputs) {
                results.add(cpuExecutor.submit(() -> countPrimes(limit)));
            }

            for (Future<Long> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
```

Ở đây, số tác vụ đang thực thi đồng thời bị giới hạn bởi số worker của executor. Các task còn lại chờ trong hàng đợi. `availableProcessors()` là điểm bắt đầu hợp lý, không phải con số tối ưu cho mọi ứng dụng: hiệu năng còn phụ thuộc thời gian mỗi task, băng thông bộ nhớ, mức sử dụng CPU của phần còn lại trong ứng dụng và giới hạn CPU của container.

Lưu ý rằng `Executors.newFixedThreadPool()` dùng hàng đợi chia sẻ không giới hạn. Nó giới hạn số worker đang chạy nhưng không giới hạn số task đang chờ. Với hệ thống nhận công việc liên tục hoặc từ nguồn không kiểm soát, cần thêm backpressure, giới hạn số task đang chờ, hoặc dùng `ThreadPoolExecutor` với bounded queue và chính sách từ chối phù hợp.

Với thuật toán chia để trị hoặc các tác vụ CPU có thể tách thành nhiều nhánh con, `ForkJoinPool` hoặc `Executors.newWorkStealingPool()` cũng là lựa chọn phù hợp. Work-stealing giúp worker rảnh lấy task từ hàng đợi khác; nó vẫn không tạo thêm năng lực CPU vượt quá phần cứng.

## 5. Kết hợp virtual thread cho I/O và CPU executor cho tính toán

Trong ứng dụng thực tế, một request có thể cần tải dữ liệu rồi mới xử lý tính toán. Có thể dùng virtual thread cho giai đoạn I/O và chuyển giai đoạn CPU sang executor riêng:

```java
int cpuWorkers = Runtime.getRuntime().availableProcessors();

try (ExecutorService ioExecutor =
             Executors.newVirtualThreadPerTaskExecutor();
     ExecutorService cpuExecutor =
             Executors.newFixedThreadPool(cpuWorkers)) {

    List<CompletableFuture<Analysis>> tasks = requests.stream()
            .map(request -> CompletableFuture
                    .supplyAsync(() -> fetchFromRemote(request), ioExecutor)
                    .thenApplyAsync(this::analyze, cpuExecutor))
            .toList();

    CompletableFuture.allOf(tasks.toArray(CompletableFuture[]::new)).join();

    List<Analysis> results = tasks.stream()
            .map(CompletableFuture::join)
            .toList();
}
```

Trong ví dụ:

- `fetchFromRemote` chạy trên virtual thread và có thể block khi chờ network I/O.
- `thenApplyAsync` chuyển phần `analyze` sang CPU executor có số worker hữu hạn.
- `CompletableFuture.allOf(...).join()` đợi các pipeline hoàn tất trước khi lấy kết quả.

Đây là cách tách hai loại tài nguyên theo đặc điểm công việc. Nếu `requests` có thể chứa lượng phần tử rất lớn, không nên tạo toàn bộ future cùng lúc mà không có giới hạn. Hãy xử lý theo batch hoặc dùng cơ chế backpressure để giới hạn số request đang hoạt động và số tác vụ CPU đang chờ.

Nếu phần I/O truy cập database hoặc dịch vụ ngoài có giới hạn kết nối, hãy giới hạn concurrency tại đúng tài nguyên đó. Virtual thread không tự giới hạn số kết nối, request hoặc transaction. Connection pool thường đã có giới hạn; nếu không, có thể dùng `Semaphore` để đặt số thao tác đồng thời tối đa. Không cần thêm semaphore nếu connection pool đã thực hiện đúng giới hạn đó.

## 6. Không dùng virtual thread như một thread pool để giới hạn CPU

Virtual thread được thiết kế theo mô hình một thread cho một task. Không cần tạo một pool virtual thread cố định để tái sử dụng chúng. Nếu cần giới hạn số tác vụ CPU chạy đồng thời, hãy dùng executor có số worker hữu hạn hoặc một cơ chế admission control phù hợp.

| Mục tiêu | Cách tiếp cận |
|---|---|
| Chạy nhiều request chờ HTTP/JDBC | `Executors.newVirtualThreadPerTaskExecutor()` |
| Giới hạn số phép tính CPU chạy cùng lúc | Fixed platform-thread executor hoặc `ForkJoinPool` phù hợp |
| Giới hạn số request truy cập dịch vụ bên ngoài | Connection pool hoặc `Semaphore` |
| Giới hạn số công việc đang chờ trong hệ thống | Bounded queue, batch hoặc backpressure |
| Xử lý hỗn hợp I/O rồi tính toán | Virtual thread cho I/O, CPU executor riêng cho compute |

Không nên tăng số virtual thread với kỳ vọng tăng tốc CPU. Cũng không nên tăng target parallelism của scheduler như một cách thay thế cho việc chọn thuật toán, giới hạn concurrency và tối ưu số worker. Các tham số scheduler là cấu hình runtime phụ thuộc triển khai, không phải cơ chế tạo thêm tài nguyên xử lý.

## 7. Cách đánh giá hiệu năng CPU-bound

Khi quyết định số worker hoặc so sánh executor, cần đo trên workload đại diện thay vì suy luận chỉ từ số lượng thread.

### Những chỉ số cần quan sát

- Throughput: số tác vụ hoàn thành trong một đơn vị thời gian.
- Latency: thời gian một tác vụ hoàn tất, đặc biệt là percentile p95/p99 khi có nhiều request.
- CPU utilization: mức sử dụng CPU của tiến trình và máy.
- Queue depth: số tác vụ đang chờ được xử lý.
- Memory/GC: bộ nhớ dành cho task, object và chi phí thu gom rác.

Nếu CPU đã gần bão hòa trong khi queue tiếp tục tăng, tạo thêm virtual thread thường chỉ làm tăng lượng công việc chờ. Khi đó, cần giảm admission rate, giới hạn hàng đợi, tối ưu thuật toán hoặc phân phối workload sang nhiều máy/năng lực xử lý khác.

### Thiết kế phép đo có ý nghĩa

1. Dùng cùng một tập input và cùng thuật toán cho từng phương án.
2. Tách thời gian khởi động JVM và warm-up khỏi phép đo ổn định.
3. So sánh số worker quanh số processor mà môi trường triển khai cấp phát.
4. Đo cả throughput lẫn latency; throughput cao hơn có thể đi kèm tail latency xấu hơn.
5. Chạy benchmark nhiều lần trong môi trường ít nhiễu; với benchmark vi mô, dùng JMH thay vì chỉ đo một vòng `System.nanoTime()`.
6. Đo trên đúng môi trường triển khai, vì số processor JVM nhìn thấy có thể khác máy phát triển, đặc biệt trong container.

Không có một tỷ lệ virtual thread/platform thread cố định nào làm CPU-bound nhanh hơn cho mọi ứng dụng. Tối ưu số worker phải dựa trên đặc điểm thuật toán, phần cứng và tải thực tế.

## 8. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Virtual thread nhẹ nên chạy phép tính nhanh hơn | Nó không tăng tốc lệnh CPU; lợi ích chính là giảm chi phí khi nhiều task chờ blocking I/O |
| Tạo 100.000 virtual thread đồng nghĩa chạy 100.000 phép tính song song | Số phép tính chạy đồng thời vẫn bị giới hạn bởi CPU và scheduler |
| `newVirtualThreadPerTaskExecutor()` tự giới hạn số task | Executor tạo một virtual thread cho mỗi task và không đặt giới hạn số thread |
| Tăng scheduler parallelism sẽ tạo thêm lõi CPU | Nó chỉ thay đổi target số carrier platform thread mà scheduler sử dụng |
| Fixed thread pool giải quyết cả giới hạn worker và backlog | `newFixedThreadPool` có số worker cố định nhưng dùng hàng đợi không giới hạn |
| Virtual thread chỉ hữu ích cho I/O và không thể chứa đoạn tính toán | Một virtual thread có thể thực hiện đoạn CPU; vấn đề là không có lợi thế throughput cho CPU-bound và có thể chiếm carrier lâu |

## 9. Nguyên tắc áp dụng

1. Phân loại từng giai đoạn công việc theo thời gian CPU và thời gian chờ.
2. Dùng virtual thread cho tác vụ có nhiều blocking I/O và cần concurrency cao.
3. Dùng executor có số worker hữu hạn cho công việc CPU-bound; bắt đầu gần số processor khả dụng rồi benchmark.
4. Với workload hỗn hợp, tách giai đoạn I/O và CPU bằng hai executor phù hợp.
5. Giới hạn backlog và tài nguyên downstream bằng bounded queue, batch, connection pool hoặc semaphore.
6. Đánh giá throughput, tail latency, CPU và bộ nhớ trên môi trường triển khai thực tế.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [OpenJDK JDK-8295817 — Virtual Threads](https://bugs.openjdk.org/browse/JDK-8295817)
