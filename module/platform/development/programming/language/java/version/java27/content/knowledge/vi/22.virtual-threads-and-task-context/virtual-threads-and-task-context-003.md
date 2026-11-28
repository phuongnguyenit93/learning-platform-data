# Phân biệt tác vụ chờ I/O với tác vụ dùng nhiều CPU

Trong Java 27, **virtual threads** giúp viết ứng dụng đồng thời bằng phong cách tuần tự dễ đọc, đặc biệt khi mỗi yêu cầu phải **chờ mạng, cơ sở dữ liệu hoặc một nguồn I/O**. Tuy nhiên, virtual threads không tạo ra thêm lõi CPU và không khiến một phép tính nặng chạy nhanh hơn chỉ nhờ thay loại thread.

Muốn chọn đúng mô hình thực thi, trước tiên cần phân biệt hai dạng công việc:

- **I/O-bound** (*bị giới hạn bởi thời gian chờ I/O*): phần lớn thời gian của tác vụ trôi qua trong khi chờ dữ liệu hoặc kết quả từ bên ngoài.
- **CPU-bound** (*bị giới hạn bởi năng lực CPU*): phần lớn thời gian của tác vụ dành cho thực hiện phép tính trên bộ xử lý.

Đây là hai đặc tính của **khối lượng công việc**, không phải hai loại thread trong Java. Cùng một tác vụ có thể chuyển từ giai đoạn chờ I/O sang giai đoạn tính toán CPU, và ngược lại.

Bài học sử dụng các API ổn định trên Java 27: **Thread.ofVirtual()**, **Thread.isVirtual()**, **Executors.newVirtualThreadPerTaskExecutor()**, **ExecutorService**, **Future**, **Semaphore** và các công cụ chẩn đoán JDK. Tính năng virtual threads đã chính thức từ **Java 21 (JEP 444)**; không cần bật preview.

## 1. Tác vụ I/O-bound và CPU-bound khác nhau như thế nào?

### 1.1. Tác vụ chờ I/O

Ví dụ một yêu cầu xử lý đơn hàng:

1. Đọc thông tin từ cơ sở dữ liệu.
2. Gọi dịch vụ thanh toán qua HTTP.
3. Đọc phản hồi và ghi lại trạng thái.
4. Trả kết quả cho người dùng.

Trong các bước này, ứng dụng có thể mất phần lớn thời gian để **chờ** cơ sở dữ liệu hoặc dịch vụ mạng phản hồi. CPU không nhất thiết thực hiện nhiều phép tính trong khoảng chờ đó.

Một đoạn code Java có dạng:

~~~java
Order order = repository.findById(orderId);
Payment payment = paymentClient.charge(order);
repository.save(order.withPayment(payment));
~~~

Dù các lệnh trông như chạy tuần tự, bên dưới có thể xảy ra nhiều lần chờ I/O. **Nếu thư viện sử dụng thao tác blocking được JDK hỗ trợ**, một virtual thread có thể tạm dừng trong lúc chờ để nhường carrier cho virtual thread khác.

**Lưu ý:** Các lớp **Order**, **Payment**, **repository** và **paymentClient** ở đây là đối tượng giả định của một ứng dụng, không phải API có sẵn trong JDK.

### 1.2. Tác vụ dùng nhiều CPU

Ví dụ:

- Phân tích một lượng dữ liệu lớn hoàn toàn trong bộ nhớ.
- Mã hóa hoặc băm một khối dữ liệu lớn.
- Tính toán toán học, mô phỏng, xử lý hình ảnh.
- Sắp xếp một tập dữ liệu rất lớn đã ở trong RAM.
- Biên dịch, phân tích cú pháp phức tạp hoặc chạy thuật toán tối ưu.

~~~java
long result = calculatePrimes(200_000);
~~~

Nếu phương thức **calculatePrimes** liên tục thực hiện các vòng lặp và phép toán, thread thực thi vẫn cần CPU trong khoảng thời gian đó. Khi đổi từ platform thread sang virtual thread, phép toán không tự biến thành bất đồng bộ và không tiêu thụ ít CPU hơn chỉ nhờ loại thread.

### 1.3. Bảng so sánh

| Tiêu chí | I/O-bound | CPU-bound |
|---|---|---|
| Phần lớn thời gian | Chờ dữ liệu/kết quả từ bên ngoài | Chạy lệnh tính toán |
| Ví dụ | Gọi HTTP, truy vấn DB, chờ socket | Mã hóa, mô phỏng, phân tích dữ liệu |
| Tăng đồng thời có thể giúp gì? | Che giấu thời gian chờ, tăng lượng yêu cầu đang phục vụ | Tăng xử lý song song đến giới hạn lõi CPU |
| Giới hạn thường gặp | Kết nối DB, băng thông, tốc độ dịch vụ ngoài | CPU, cache, bộ nhớ, đồng bộ hóa |
| Virtual threads phù hợp? | **Rất phù hợp** với blocking I/O thông dụng | **Không mang lại lợi thế tự động** cho tác vụ CPU kéo dài |
| Mô hình khởi đầu | Một virtual thread cho mỗi tác vụ đồng thời | Executor có mức song song giới hạn hoặc thuật toán chia việc |
| Cần đo | Thời gian chờ I/O, throughput, p95/p99 latency | CPU sử dụng, CPU time, throughput, contention |

Một công việc có gọi I/O **không nhất thiết** là I/O-bound. Nếu nó tải 1 KB rồi mất 30 giây phân tích dữ liệu, nút thắt chính có thể vẫn là CPU.

## 2. Phân tích thời gian của một tác vụ

Có thể hình dung thời gian hoàn thành một yêu cầu theo mô hình đơn giản:

\[
T_{\text{elapsed}} \approx T_{\text{CPU}} + T_{\text{wait}} + T_{\text{other}}
\]

Trong đó:

- **T_CPU**: thời gian tiêu thụ CPU để thực hiện logic.
- **T_wait**: thời gian chờ I/O, lock, semaphore hoặc kết quả từ hệ thống khác.
- **T_other**: các chi phí khác như scheduling, GC hoặc tranh chấp tài nguyên.

Ví dụ giả định:

| Tác vụ | CPU | Chờ | Tổng | Nhận định |
|---|---:|---:|---:|---|
| Đọc dữ liệu từ API | 10 ms | 190 ms | 200 ms | Thiên về I/O-bound |
| Xử lý ảnh | 190 ms | 10 ms | 200 ms | Thiên về CPU-bound |
| Tải và phân tích file | 100 ms | 100 ms | 200 ms | Hỗn hợp |

Hai tác vụ đầu có cùng **200 ms** thời gian hoàn thành, nhưng cần chiến lược tối ưu khác nhau. Với tác vụ thứ nhất, việc phục vụ thêm các yêu cầu khác khi một yêu cầu đang chờ có thể tăng throughput. Với tác vụ thứ hai, các lõi CPU sẵn có mới là tài nguyên cần phân bổ hiệu quả.

Đây chỉ là mô hình tư duy. Khi đo thực tế, **T_elapsed** còn chịu tác động của scheduler, tác vụ đồng thời, tranh chấp tài nguyên, GC và độ trễ hệ thống.

## 3. Platform thread và virtual thread sử dụng CPU như thế nào?

Java có hai loại **java.lang.Thread**:

- **Platform thread** thường được gắn với một thread của hệ điều hành trong suốt vòng đời.
- **Virtual thread** được runtime Java quản lý và có thể được chạy trên những platform thread đóng vai trò **carrier**.

Khi virtual thread thực hiện code Java, **nó vẫn thực thi trên CPU thật** thông qua một carrier. Virtual thread không phải một bộ xử lý ảo có khả năng tính toán độc lập.

### 3.1. Khi virtual thread chờ blocking I/O

Ở thao tác blocking được hỗ trợ, runtime có thể **unmount** virtual thread khỏi carrier. Carrier này được dùng để chạy một virtual thread khác, trong khi tác vụ đầu tiên chờ I/O hoàn thành.

~~~mermaid
flowchart LR
    A["Virtual thread A"] --> B["Chạy Java trên carrier"]
    B --> C["Đọc socket, phải chờ I/O"]
    C --> D["A tạm dừng, nhường carrier"]
    D --> E["Carrier chạy virtual thread B"]
    C -.-> F["I/O hoàn tất"]
    F --> G["A sẵn sàng tiếp tục"]
    E --> G
~~~

Vì carrier không bị giữ trong phần lớn khoảng chờ, một số lượng tương đối nhỏ platform threads có thể phục vụ **rất nhiều virtual threads đang chờ**.

Virtual thread được runtime *mount* lại khi có cơ hội tiếp tục. Không có cam kết rằng nó sẽ luôn chạy trên đúng carrier ban đầu.

### 3.2. Khi virtual thread đang tính toán CPU

~~~mermaid
flowchart LR
    A["Virtual thread A"] --> B["Carrier: chạy tính toán CPU"]
    B --> C["Tính toán tiếp..."]
    C --> D["Tính toán tiếp..."]
    D --> E["Hoàn thành hoặc nhường CPU"]
    F["Virtual thread B cần CPU"] -.-> B
~~~

Nếu A liên tục tính toán mà không đi vào thao tác chờ hoặc điểm nhường phù hợp, nó **tiếp tục cần carrier và thời gian CPU**. Tạo thêm một nghìn virtual threads cùng tính toán không tạo thêm một nghìn lõi CPU.

Runtime vẫn có scheduler, nhưng virtual threads **không được thiết kế như một cơ chế tăng tốc thuật toán CPU-intensive**. Một số virtual threads tính toán dài có thể khiến những tác vụ khác đợi tới lượt được chạy trên carrier.

### 3.3. Virtual thread không nhanh hơn một thread

Tài liệu Oracle nhấn mạnh: virtual threads giúp **mở rộng số tác vụ đồng thời và throughput**, không làm một thao tác đơn lẻ thực thi nhanh hơn.

Nếu một phép tính mất 800 ms trên một platform thread, không có cơ sở để khẳng định nó sẽ mất ít hơn trên một virtual thread. Ngược lại, nếu một yêu cầu chủ yếu chờ HTTP 800 ms, virtual thread cũng không tự làm dịch vụ HTTP phản hồi nhanh hơn; lợi ích nằm ở khả năng **phục vụ thêm các yêu cầu khác trong lúc chờ**.

## 4. Từ concurrency đến throughput: hiểu đúng lợi ích

Ba khái niệm thường bị trộn lẫn:

- **Concurrency (đồng thời)**: có nhiều tác vụ đang tồn tại và tiến triển xen kẽ.
- **Parallelism (song song)**: nhiều tác vụ đang thực sự chạy trên nhiều lõi CPU tại cùng thời điểm.
- **Throughput**: số tác vụ hoặc yêu cầu hoàn thành trên một đơn vị thời gian.

Một ứng dụng chờ mạng nhiều có thể cần **hàng trăm hoặc hàng nghìn tác vụ đồng thời**, dù nó chỉ có vài lõi CPU.

### 4.1. Ví dụ tải giả định

Giả sử một dịch vụ nhận **500 yêu cầu/giây**, và mỗi yêu cầu dành trung bình **200 ms** trong hệ thống.

Theo cách nhìn gần đúng của định luật Little khi hệ thống ổn định:

\[
L \approx \lambda W
\]

Ta có:

\[
L \approx 500 \text{ yêu cầu/giây} \times 0{,}2 \text{ giây}
= 100 \text{ yêu cầu đồng thời}
\]

Điều này cho thấy dịch vụ có thể phải duy trì khoảng 100 yêu cầu đang xử lý hoặc đang chờ, dù số yêu cầu thực sự cần CPU cùng lúc thấp hơn nhiều.

Nếu đa số thời gian là chờ I/O, virtual threads có thể giảm chi phí duy trì số lượng tác vụ đồng thời lớn. Tuy nhiên, kết quả phụ thuộc khả năng của database, mạng, cấu hình server và mức tiêu thụ bộ nhớ cho từng yêu cầu.

Định luật Little **không phải** một cam kết rằng chỉ cần tạo 100 virtual threads thì dịch vụ đạt 500 yêu cầu/giây. Nó chỉ giúp ước lượng quan hệ giữa thông lượng, thời gian trong hệ thống và lượng công việc đang tồn tại.

## 5. Tạo virtual thread bằng API Java 27

Có thể tạo trực tiếp một virtual thread:

~~~java
Thread worker = Thread.ofVirtual()
    .name("request-handler")
    .start(() -> {
        System.out.println(Thread.currentThread().isVirtual());
    });

worker.join();
~~~

Kết quả:

~~~text
true
~~~

**Thread.ofVirtual()** tạo builder. **start(...)** tạo và khởi động virtual thread. **join()** chờ đến khi thread hoàn thành.

### 5.1. Executor một virtual thread cho mỗi tác vụ

Với nhiều tác vụ độc lập, thường dùng:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = executor.submit(() -> {
        Thread.sleep(100);
        return "Hoàn tất";
    });

    System.out.println(result.get());
}
~~~

Đoạn code này có thể nằm trong method khai báo **throws Exception**, hoặc xử lý **InterruptedException** và **ExecutionException** phù hợp.

**Executors.newVirtualThreadPerTaskExecutor()** tạo **một virtual thread mới cho mỗi tác vụ**. Đây **không phải** một pool tái sử dụng virtual threads.

**ExecutorService.close()** trong try-with-resources thực hiện shutdown có thứ tự và **chờ các tác vụ kết thúc**. Nếu tác vụ không kết thúc do chờ không giới hạn, việc thoát khối **try** cũng có thể phải đợi lâu. Vì vậy, cần timeout/cancellation phù hợp với ứng dụng.

### 5.2. Vì sao không pool virtual threads?

Platform threads tương đối đắt để tạo và giữ nên thường được tái sử dụng trong pool. Virtual threads nhẹ hơn đáng kể và được thiết kế để biểu diễn từng tác vụ.

Cách tổ chức nên ưu tiên:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (Request request : requests) {
        executor.submit(() -> handle(request));
    }
}
~~~

**Request**, **requests** và **handle** trong ví dụ là các thành phần ứng dụng, được lược bỏ chi tiết để minh họa cách tổ chức.

Không tạo “virtual thread pool cố định 10 thread” chỉ để bắt chước pool platform threads. Nếu muốn giới hạn số lời gọi tới một dịch vụ ngoài, nên dùng cơ chế giới hạn tài nguyên như **Semaphore** hoặc connection pool, sẽ được giải thích ở phần sau.

## 6. Thí nghiệm: nhiều tác vụ đang chờ

Để nhìn thấy sự khác biệt giữa một pool ít platform threads và mô hình virtual-thread-per-task, ta mô phỏng các tác vụ phải chờ **200 ms**.

**Quan trọng:** **Thread.sleep** chỉ mô phỏng trạng thái chờ. Nó **không phải thao tác I/O mạng hoặc đĩa**, nên kết quả không chứng minh hiệu năng mạng hay JDBC. Nó chỉ giúp quan sát trực quan khả năng không chiếm carrier trong lúc chờ.

Tạo file **WaitingTasksDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.function.Supplier;

public class WaitingTasksDemo {

    private static final int TASKS = 20;
    private static final long WAIT_MILLIS = 200;

    static void run(
        String name,
        Supplier<ExecutorService> executorFactory
    ) throws Exception {
        long started = System.nanoTime();

        try (ExecutorService executor = executorFactory.get()) {
            List<Future<Void>> futures = new ArrayList<>();

            for (int i = 0; i < TASKS; i++) {
                Callable<Void> task = () -> {
                    Thread.sleep(WAIT_MILLIS);
                    return null;
                };

                futures.add(executor.submit(task));
            }

            for (Future<Void> future : futures) {
                future.get();
            }
        }

        double elapsedMs =
            (System.nanoTime() - started) / 1_000_000.0;

        System.out.printf("%s: %.1f ms%n", name, elapsedMs);
    }

    public static void main(String[] args) throws Exception {
        run("4 platform threads",
            () -> Executors.newFixedThreadPool(4));

        run("virtual thread per task",
            Executors::newVirtualThreadPerTaskExecutor);
    }
}
~~~

Biên dịch và chạy với JDK 27:

~~~bash
javac WaitingTasksDemo.java
java WaitingTasksDemo
~~~

### 6.1. Dự kiến quan sát gì?

Với **20 tác vụ**, mỗi tác vụ chờ khoảng **200 ms**:

- Pool **4 platform threads** thường chia các tác vụ thành khoảng **5 lượt chờ**, nên thời gian có thể xấp xỉ **1 giây** nếu không có overhead đáng kể.
- Virtual-thread-per-task có thể cho nhiều tác vụ chờ đồng thời, nên thời gian có thể gần **200 ms cộng chi phí tạo và lên lịch**.

Các con số chỉ là **minh họa định tính**, không phải kết quả được bảo đảm. JIT, CPU, scheduler, hoạt động của hệ điều hành và máy chạy có thể làm số đo thực tế khác đi.

### 6.2. Diễn giải đúng

Thí nghiệm không có bài toán tính toán phức tạp; tất cả tác vụ đều chỉ chờ. Vì thế, điều ta quan sát là **chi phí chiếm thread trong lúc đợi**, không phải việc virtual threads tính toán nhanh hơn.

Để đánh giá ứng dụng thật, thay phần ngủ giả lập bằng một workload **HTTP/JDBC** đại diện, rồi đo thêm throughput, độ trễ theo phân vị, CPU sử dụng và giới hạn tài nguyên.

## 7. Thí nghiệm: tác vụ dùng nhiều CPU

Với tác vụ tính số nguyên tố, phần lớn công việc là phép chia và vòng lặp trên CPU. Đây là ví dụ nhỏ về CPU-bound workload.

~~~java
static long countPrimes(int max) {
    long count = 0;

    for (int n = 2; n <= max; n++) {
        boolean prime = true;

        for (int divisor = 2; divisor <= n / divisor; divisor++) {
            if (n % divisor == 0) {
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
~~~

Nếu gọi method này từ hàng trăm virtual threads, tất cả vẫn cần CPU để thực hiện phép toán. Đổi thread không làm độ phức tạp của thuật toán giảm xuống.

Với tập tác vụ CPU độc lập, một cách khởi đầu là **giới hạn số công việc tính toán song song** gần với số bộ xử lý sẵn có:

~~~java
int parallelism =
    Math.max(1, Runtime.getRuntime().availableProcessors());

try (var executor = Executors.newFixedThreadPool(parallelism)) {
    List<Future<Long>> futures = new ArrayList<>();

    for (int i = 0; i < 8; i++) {
        futures.add(executor.submit(
            () -> countPrimes(100_000)
        ));
    }

    long total = 0;

    for (Future<Long> future : futures) {
        total += future.get();
    }

    System.out.println("Tổng kết quả: " + total);
}
~~~

Các đoạn code trên cần những import tương ứng từ **java.util** và **java.util.concurrent**, hoặc có thể đặt vào cùng tệp **WaitingTasksDemo.java** rồi bổ sung import để chạy.

### 7.1. Vì sao fixed pool thường hợp lý cho CPU-bound?

Với máy có một số lượng lõi CPU hữu hạn, quá nhiều tác vụ nặng cùng tranh CPU có thể:

- Làm tăng chi phí scheduling và chuyển đổi ngữ cảnh.
- Làm tăng áp lực lên bộ nhớ đệm CPU.
- Tăng độ trễ của tác vụ ngắn.
- Không tăng throughput tương ứng với số lượng thread.
- Gây hiện tượng nhiều công việc chưa hoàn thành cùng giữ bộ nhớ.

**newFixedThreadPool(parallelism)** là một công cụ đơn giản để giới hạn mức thực thi song song cho công việc CPU. Với thuật toán chia để trị, **ForkJoinPool** có thể là một lựa chọn khác cần đánh giá theo đặc tính công việc.

**Không coi availableProcessors() là con số tối ưu tuyệt đối.** Workload có thể bị giới hạn bởi băng thông bộ nhớ, có native calls, chia sẻ CPU hoặc chạy trong container. Cần đo thực tế để chọn parallelism.

### 7.2. Virtual threads vẫn có thể chạy code CPU

Không có quy tắc “cấm” thực thi tính toán bằng virtual thread. Một yêu cầu HTTP được xử lý bằng virtual thread thường có một ít logic CPU, chẳng hạn xác thực dữ liệu và tạo phản hồi.

Điểm quan trọng là **không kỳ vọng tăng số virtual threads sẽ làm tăng tốc phép tính dài**. Khi giai đoạn CPU đủ nặng để trở thành nút thắt, hãy giới hạn mức song song của giai đoạn đó và tối ưu thuật toán hoặc dữ liệu.

### 7.3. Không dùng ví dụ này làm benchmark production

Kết quả chạy một lần có thể bị ảnh hưởng bởi:

- JIT warmup và tối ưu hóa của trình biên dịch.
- Số lượng lõi CPU và quota container.
- Hoạt động GC, hệ điều hành và tác vụ khác.
- Kích thước bài toán quá nhỏ để đo ổn định.
- Thứ tự chạy các phương án so sánh.

Muốn benchmark CPU chính xác, nên sử dụng công cụ chuyên dụng như **JMH** với warmup, nhiều lần đo và thiết kế tránh tối ưu hóa bỏ phép tính. Bài này tập trung vào nguyên lý lựa chọn mô hình thực thi.

## 8. Một yêu cầu thực tế thường là tác vụ hỗn hợp

Xét luồng xử lý một file được tải từ dịch vụ ngoài:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu"]
    B["Gọi dịch vụ tải file"]
    C["Chờ HTTP / mạng — I/O-bound"]
    D["Giải mã / phân tích nội dung — CPU-bound"]
    E["Ghi kết quả vào DB"]
    F["Chờ DB — I/O-bound"]
    G["Trả phản hồi"]
    A --> B --> C --> D --> E --> F --> G
~~~

Một virtual thread có thể xử lý toàn bộ yêu cầu theo luồng code tuần tự. Nó phát huy lợi thế khi tác vụ phải chờ HTTP hoặc cơ sở dữ liệu. Nhưng khi phân tích nội dung tốn nhiều CPU, nó vẫn tiêu thụ carrier và CPU như thread khác.

### 8.1. Không đánh giá theo tên method

Ví dụ tên **fetchAndAnalyze** có thể tạo cảm giác đây là I/O-bound vì có từ “fetch”, nhưng nếu **analyze** chiếm 95% tổng thời gian thì workload thực tế có thể thiên về CPU-bound.

Cần đo:

1. Thời gian chờ network/database.
2. Thời gian CPU cho parse, validation, nén, mã hóa.
3. Độ dài hàng đợi và giới hạn tài nguyên.
4. Throughput khi tăng số yêu cầu đồng thời.
5. Latency các giai đoạn khi hệ thống chịu tải.

### 8.2. Tách riêng giai đoạn CPU khi thật sự cần

Với giai đoạn CPU lớn và độc lập, một kiến trúc có thể dùng:

- **Virtual threads** tại ranh giới mỗi yêu cầu và các thao tác I/O đồng bộ.
- **Executor có parallelism giới hạn** dành riêng cho tác vụ CPU.
- **Giới hạn hàng đợi / backpressure** để tránh nhận vô hạn công việc.

Ví dụ tổ chức ở mức kiến trúc:

~~~java
// cpuExecutor được tạo một lần tại vòng đời ứng dụng.
Future<Analysis> analysis = cpuExecutor.submit(
    () -> analyze(downloadedData)
);

Analysis result = analysis.get();
~~~

**Analysis**, **analyze** và **downloadedData** là thành phần giả định của ứng dụng. Việc một virtual thread gọi **Future.get()** để chờ kết quả CPU là cách chờ hợp lệ, nhưng chưa đủ để kiểm soát kích thước hàng đợi của CPU executor.

Không nên tách mọi phép tính nhỏ sang executor khác: chi phí điều phối có thể lớn hơn lợi ích. Chỉ tách khi số liệu cho thấy giai đoạn CPU dài gây tranh chấp hoặc cần chính sách tài nguyên riêng.

## 9. Ví dụ I/O thật: HTTP đồng bộ trên virtual threads

Java **HttpClient.send(...)** cung cấp API HTTP đồng bộ. Khi được gọi trong virtual thread, việc chờ phản hồi có thể tận dụng khả năng tạm dừng virtual thread của runtime.

Tạo file **VirtualHttpDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class VirtualHttpDemo {

    record FetchResult(
        URI uri,
        int status,
        int textLength
    ) {}

    static FetchResult fetch(
        HttpClient client,
        URI uri
    ) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        return new FetchResult(
            uri,
            response.statusCode(),
            response.body().length()
        );
    }

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        List<URI> targets = List.of(
            URI.create("https://example.com/"),
            URI.create("https://www.example.org/")
        );

        Semaphore outboundLimit = new Semaphore(4);

        try (var executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<FetchResult>> futures =
                new ArrayList<>();

            for (URI uri : targets) {
                futures.add(executor.submit(() -> {
                    outboundLimit.acquire();
                    try {
                        return fetch(client, uri);
                    } finally {
                        outboundLimit.release();
                    }
                }));
            }

            for (Future<FetchResult> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac VirtualHttpDemo.java
java VirtualHttpDemo
~~~

Ví dụ cần **kết nối Internet** và các địa chỉ đích có thể truy cập. Kết quả HTTP, độ dài nội dung và thời gian phản hồi không cố định; chương trình có thể báo lỗi nếu mạng không khả dụng.

### 9.1. Những gì ví dụ minh họa

- **HttpClient** được tạo một lần rồi chia sẻ cho nhiều tác vụ.
- Mỗi lời gọi **executor.submit(...)** có một virtual thread riêng.
- **HttpClient.send** là lời gọi đồng bộ: code của tác vụ dễ theo dõi theo thứ tự.
- **HttpRequest.timeout** và **HttpClient.connectTimeout** giúp tránh một số tình huống chờ vô hạn.
- **Semaphore** giới hạn số tác vụ đang thực hiện lời gọi ra ngoài.
- **finally** luôn giải phóng permit khi công việc bên trong kết thúc bằng thành công hoặc ngoại lệ.
- **Future.get()** truyền kết quả hoặc ngoại lệ của tác vụ về luồng gọi.

Trong ứng dụng thật, cần chính sách retry, cancellation, tổng thời gian chờ và bảo vệ hệ thống đích. Timeout kết nối và request không thay thế toàn bộ chính sách deadline của một workflow nhiều bước.

### 9.2. Không cần chuyển mọi HTTP call sang API async

Khi một ứng dụng đã dùng **HttpClient.send(...)** theo mô hình đồng bộ, chạy trên virtual thread có thể giúp tận dụng thời gian chờ mà không cần thay toàn bộ code thành chuỗi **CompletableFuture**.

Điều đó không có nghĩa API bất đồng bộ là sai hoặc đã lỗi thời. Nếu ứng dụng sử dụng event loop/reactive framework được tối ưu sẵn, hãy đánh giá kiến trúc hiện có trước khi trộn thêm virtual threads. Lợi ích lớn nhất thường đến từ cách tổ chức **thread-per-task với blocking I/O**.

## 10. Giới hạn đồng thời: không nhầm số thread với tài nguyên thật

Tạo được nhiều virtual threads không đồng nghĩa với việc mọi hệ thống phụ trợ đều phục vụ được nhiều yêu cầu.

Giả sử một cơ sở dữ liệu chỉ có **20 kết nối**. Nếu ứng dụng tạo **5.000 virtual threads** cùng truy vấn, các tác vụ vẫn phải chờ quyền sử dụng kết nối, tài nguyên DB hoặc server. Virtual threads làm việc chờ rẻ hơn về chi phí thread, nhưng **không nhân dung lượng connection pool**.

### 10.1. Semaphore dành cho tài nguyên giới hạn

~~~java
import java.util.concurrent.Semaphore;

final class LimitedGateway {
    private final Semaphore permits = new Semaphore(20);

    String callRemote() throws Exception {
        permits.acquire();

        try {
            return performBlockingCall();
        } finally {
            permits.release();
        }
    }

    private String performBlockingCall() {
        // Thay bằng lời gọi HTTP/JDBC đồng bộ thực tế.
        return "OK";
    }
}
~~~

Có thể gọi **callRemote()** từ nhiều virtual threads, nhưng tại một thời điểm chỉ có tối đa **20** tác vụ đã giữ permit để vào **performBlockingCall**.

**Semaphore** kiểm soát một tài nguyên cụ thể; không dùng một pool virtual threads cố định để đạt tác dụng phụ tương tự.

### 10.2. Đừng giới hạn hai lần nếu không cần thiết

Nếu connection pool của cơ sở dữ liệu đã giới hạn tối đa 20 kết nối và có cơ chế chờ phù hợp, việc thêm một **Semaphore(20)** riêng cho cùng mục đích có thể không cần thiết.

Quyết định dựa trên:

- Giới hạn nào đã được connection pool hoặc HTTP client thực thi?
- Hệ thống ngoài có quota theo client, tenant hoặc endpoint không?
- Có cần giới hạn tổng số tác vụ đang nhận vào trước khi tạo virtual thread không?
- Cần đợi, từ chối, hay trả lỗi khi quá tải?

### 10.3. Backpressure vẫn rất quan trọng

Executor virtual-thread-per-task có thể nhận nhiều tác vụ và tạo nhiều virtual threads. Nếu nguồn đầu vào không bị giới hạn, ứng dụng vẫn có thể cạn:

- Bộ nhớ do trạng thái, request body hoặc kết quả nằm chờ.
- File descriptors, socket, DB connections.
- Băng thông mạng và dung lượng hệ thống đích.
- Dung lượng hàng đợi logic hoặc timeout budget.
- Bộ nhớ của các cấu trúc giữ **Future**, dữ liệu phản hồi, log.

Hãy xác định giới hạn nhận request, kích thước dữ liệu, tổng tác vụ đang bay (*in-flight*), timeout và chính sách từ chối có kiểm soát. **Virtual threads không loại bỏ nhu cầu backpressure**.

## 11. Quản lý CPU-bound workload khi hệ thống có virtual threads

Một server có thể dùng virtual threads cho từng request nhưng vẫn cần kiểm soát những đoạn xử lý CPU nặng.

### 11.1. Khởi đầu với mức song song hữu hạn

~~~java
int cpuParallelism =
    Math.max(1, Runtime.getRuntime().availableProcessors());

ExecutorService cpuExecutor =
    Executors.newFixedThreadPool(cpuParallelism);
~~~

Executor này là một **platform-thread pool** phù hợp để thực thi những tác vụ CPU độc lập có thể chia việc. Nên quản lý vòng đời của nó ở tầng ứng dụng, không tạo và hủy pool mỗi khi nhận một request nhỏ.

Với yêu cầu CPU có thể vượt xa khả năng thực thi, cần **giới hạn việc gửi vào queue**. **Executors.newFixedThreadPool** sử dụng hàng đợi không giới hạn về mặt dung lượng khai báo; chỉ giới hạn số worker là **chưa đủ** để chống quá tải.

Một hệ thống có thể dùng **ThreadPoolExecutor** với **ArrayBlockingQueue** và chính sách từ chối rõ ràng, hoặc giới hạn lượng công việc đầu vào trước khi submit.

### 11.2. Không nâng parallelism mù quáng

Tăng từ 4 lên 40 tác vụ CPU chạy song song trên máy có 4 lõi không tạo thêm sức mạnh tính toán. Đôi khi tổng thời gian hoàn thành còn tăng vì contention.

Để chọn parallelism:

1. Xác định tác vụ có thể song song hóa thực sự không.
2. Xem số lõi CPU/CPU quota mà tiến trình nhận được.
3. Quan sát mức dùng CPU, memory bandwidth, GC và contention.
4. Chạy thử với nhiều mức parallelism.
5. Chọn cấu hình theo mục tiêu throughput và latency, không theo số thread tối đa.

Cũng không nên mặc định **mỗi tác vụ CPU phải chạy trên platform thread**. Virtual threads vẫn chạy code CPU đúng chức năng. Vấn đề là **điều phối mức song song và tránh nghẽn carrier** đối với khối lượng CPU nặng kéo dài.

## 12. Cancellation, timeout và interrupt

Một tác vụ I/O không thể chờ vô thời hạn chỉ vì nó chạy trên virtual thread. Quy trình cần xác định rõ thời gian chờ tối đa và cách dừng tác vụ.

Ví dụ với **Future**:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

Future<String> future = executor.submit(
    () -> callSlowService()
);

try {
    String result = future.get(2, TimeUnit.SECONDS);
    System.out.println(result);
} catch (TimeoutException timeout) {
    future.cancel(true);
    throw timeout;
}
~~~

Ở đây **executor** và **callSlowService** là các thành phần đã được khởi tạo trong code ứng dụng.

- **Future.get(timeout, unit)** chỉ giới hạn thời gian **chờ kết quả của luồng gọi**.
- Khi hết hạn, **get** ném **TimeoutException** nhưng **không tự động hủy task**.
- **future.cancel(true)** yêu cầu ngắt nếu task đang chạy; việc dừng thực tế phụ thuộc task có hỗ trợ interrupt/cancellation hay không.
- Các lời gọi I/O nên có timeout riêng và tài nguyên cần được đóng an toàn.

Khi bắt **InterruptedException**, đừng nuốt tín hiệu ngắt. Nếu không thể truyền tiếp ngoại lệ, khôi phục cờ interrupt:

~~~java
try {
    waitForWork();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
        "Tác vụ bị ngắt", interrupted
    );
}
~~~

Các ví dụ trên mô tả mẫu xử lý; **waitForWork** cần được thay bằng thao tác thực tế có thể ném **InterruptedException**.

**Lưu ý:** **ExecutorService.close()** chờ các tác vụ kết thúc; tự nó không tạo timeout tổng thể cho toàn bộ thao tác nghiệp vụ. Đừng dùng một lời gọi **get(timeout)** rồi giả định hệ thống đã chắc chắn giải phóng mọi tài nguyên.

## 13. Pinning và thay đổi quan trọng từ JDK 24

Một virtual thread thường có thể nhường carrier khi đi vào thao tác blocking phù hợp. Tuy nhiên, trong một số hoàn cảnh nó có thể bị **pinned** — không thể unmount khỏi carrier trong khi chờ.

**Trạng thái áp dụng trên Java 27:**

- Từ **JDK 24, JEP 491 — Synchronize Virtual Threads without Pinning** đã loại bỏ vấn đề pinning thông thường khi virtual threads dùng **synchronized**.
- Không nên lặp lại hướng dẫn cũ rằng **cứ blocking trong synchronized là chắc chắn pin carrier** như các bản Java trước.
- Pinning vẫn có thể xảy ra khi chạy **native code** hoặc **foreign functions** và trong một số tình huống runtime đặc biệt.
- Pinning không tự động làm code sai về chức năng, nhưng có thể hạn chế khả năng mở rộng vì carrier không được giải phóng khi virtual thread chờ.

Khi gặp hiệu năng kém, hãy **đo và chẩn đoán** trước khi thay đổi toàn bộ cách dùng **synchronized**.

### 13.1. Công cụ quan sát hiện hành

Java 27 có các công cụ hỗ trợ tìm hiểu virtual threads:

| Công cụ | Công dụng |
|---|---|
| **jcmd <pid> Thread.dump_to_file** | Xuất thread dump bao gồm virtual threads |
| **jcmd <pid> Thread.vthread_scheduler** | Xem hoạt động scheduler của virtual threads |
| **jcmd <pid> Thread.vthread_pollers** | Thông tin về virtual threads chờ socket/network I/O |
| **JDK Flight Recorder (JFR)** | Ghi thời gian thực thi, I/O, sleep, pinning và các sự kiện liên quan |
| **JDK Mission Control** | Phân tích JFR để tìm điểm nghẽn và hành vi theo thời gian |

Ví dụ tạo thread dump:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Thay **<pid>** bằng ID tiến trình Java thực tế. Lệnh trên chỉ minh họa trong tài liệu; không thể chạy nguyên văn nếu chưa có PID.

Bắt đầu JFR recording khi chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording:dumponexit=true,filename=recording.jfr MyApplication
~~~

Sau khi có file **recording.jfr**, có thể xem sự kiện pinning:

~~~bash
jfr print --events jdk.VirtualThreadPinned recording.jfr
~~~

JFR event **jdk.VirtualThreadPinned** giúp chẩn đoán các trường hợp pinning kéo dài vượt ngưỡng cấu hình. Không nên kết luận nguyên nhân CPU-bound chỉ dựa trên sự xuất hiện hoặc vắng mặt của một sự kiện pinning.

## 14. Phân biệt CPU saturation và I/O bottleneck bằng dữ liệu

Khi một ứng dụng chậm, hãy đặt câu hỏi: **CPU đang bận chạy mã, hay nhiều tác vụ đang chờ tài nguyên?**

### 14.1. Dấu hiệu nghiêng về CPU-bound

- CPU tiến trình thường xuyên gần mức quota được phép.
- CPU time lớn so với thời gian chờ trong các profile.
- Tăng số tác vụ đồng thời không tăng throughput hoặc làm p95/p99 latency xấu hơn.
- Hot methods trong profiler là vòng lặp, parse, mã hóa, tính toán.
- Hàng đợi giai đoạn CPU tăng khi tải tăng.

Hướng xử lý: cải thiện thuật toán, giảm công việc lặp, kiểm tra GC/memory, sử dụng mức song song hữu hạn và backpressure.

### 14.2. Dấu hiệu nghiêng về I/O-bound

- CPU chưa sử dụng hết nhưng request vẫn chờ lâu.
- Thời gian ở socket reads, database calls hoặc chờ kết nối chiếm tỉ trọng lớn.
- Nhiều tác vụ đồng thời ở trạng thái chờ.
- Latency dịch vụ phụ trợ hoặc mức bão hòa connection pool là nút thắt.
- Thêm khả năng chạy đồng thời có thể tăng throughput cho đến khi chạm giới hạn phụ trợ.

Hướng xử lý: theo dõi network/database, timeout, connection pool, cache, truy vấn và khả năng dùng virtual threads cho mô hình thread-per-request.

### 14.3. Không coi một số đo là đủ

Một ứng dụng CPU 100% có thể đang chạy **GC hoặc spinning lock**, không nhất thiết tính toán nghiệp vụ. Một ứng dụng CPU thấp có thể đang bị chặn bởi semaphore, connection pool hoặc rate limit chứ không phải I/O mạng thuần túy.

Khi đo, nên tách:

1. **Request latency** trung bình và phân vị p95/p99.
2. **CPU time** của thread/task hoặc profile CPU theo method.
3. **I/O wait** và latency các dependency.
4. **Tỷ lệ lỗi, timeout, retry**.
5. **Số tác vụ đang chờ, hàng đợi và mức sử dụng pool**.
6. **Bộ nhớ, GC, số lượng tác vụ in-flight**.

Không cần tạo một virtual thread mới cho mỗi điểm đo. Hãy gắn measurement vào luồng xử lý hiện tại và thu thập dữ liệu có giới hạn.

## 15. Ngữ cảnh tác vụ không quyết định CPU hay I/O

Trong mô hình virtual thread-per-task, mỗi virtual thread có danh tính của một tác vụ. Ứng dụng thường cần gắn các dữ liệu như **request ID**, thông tin tracing hoặc tenant ID với tác vụ đó.

Java hỗ trợ **ThreadLocal**, nhưng việc lưu bộ đệm đối tượng lớn vào ThreadLocal có thể tốn bộ nhớ khi có rất nhiều virtual threads. Không nên giả định một virtual thread được tái sử dụng cho nhiều request như worker trong fixed thread pool.

Từ Java 25, **ScopedValue** là API chính thức, và tiếp tục áp dụng trong Java 27. Nó phù hợp để truyền dữ liệu ngữ cảnh theo phạm vi thực thi:

~~~java
import java.lang.ScopedValue;

static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

static void handle(String requestId) {
    ScopedValue.where(REQUEST_ID, requestId).run(() -> {
        System.out.println("Request: " + REQUEST_ID.get());
    });
}
~~~

Đây là ví dụ đơn giản về truyền ngữ cảnh. ScopedValue **không tự biến công việc CPU-bound thành I/O-bound**, và ràng buộc trong một thread không nên được giả định tự lan truyền đến mọi virtual thread tạo độc lập. Khi tạo tác vụ con, cần thiết kế cách truyền ngữ cảnh theo API đang sử dụng.

Để lựa chọn executor, **tỉ lệ chờ I/O và tính toán CPU vẫn là tiêu chí chính**; lựa chọn cơ chế truyền ngữ cảnh là một vấn đề khác.

## 16. Cây quyết định chọn mô hình xử lý

~~~mermaid
flowchart TD
    A["Một tác vụ cần chạy đồng thời"]
    B{"Phần lớn thời gian chờ blocking I/O?"}
    C["Ưu tiên virtual-thread-per-task"]
    D{"Phần lớn thời gian là CPU?"}
    E["Giới hạn CPU parallelism, dùng executor phù hợp"]
    F["Đo từng giai đoạn I/O và CPU"]
    G["Giới hạn dịch vụ ngoài, timeout, backpressure"]
    H["Đo throughput, latency, CPU và bộ nhớ"]
    A --> B
    B -->|"Có"| C
    C --> G
    G --> H
    B -->|"Không / chưa rõ"| D
    D -->|"Có"| E
    D -->|"Hỗn hợp"| F
    F --> G
    E --> H
~~~

### 16.1. Các quyết định mẫu

| Tình huống | Lựa chọn khởi đầu hợp lý |
|---|---|
| Server xử lý nhiều yêu cầu, mỗi yêu cầu gọi DB hoặc HTTP | Virtual thread cho từng yêu cầu, kiểm soát số kết nối và timeout |
| Hàng nghìn lời gọi HTTP độc lập đang chờ | Virtual-thread-per-task, giới hạn outbound concurrency khi cần |
| Tính toán ma trận lớn trên nhiều lõi | Pool CPU có parallelism hữu hạn hoặc thư viện tính toán phù hợp |
| Đọc dữ liệu rồi xử lý CPU nặng | Virtual threads cho luồng request/I/O; cân nhắc tách stage CPU |
| Chạy reactive/event-loop framework đã được tối ưu | Đo và đánh giá trước khi đổi kiến trúc |
| Gọi native library blocking kéo dài | Đánh giá pinning, throughput và tác động carrier |
| Công việc được lên lịch liên tục trong nền | Cơ chế lập lịch chuyên dụng; chọn thread model theo đặc tính công việc |
| Dịch vụ ngoài chỉ cho phép 10 tác vụ cùng lúc | Semaphore hoặc capacity limiter, không pool virtual threads |
| Một phép tính CPU cần 2 giây nhưng chỉ chạy mỗi phút một lần | Chạy đơn giản có thể đủ; không cần tối ưu đồng thời khi chưa có nút thắt |

## 17. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Vì sao sai | Cách điều chỉnh |
|---|---|---|
| “Virtual thread làm mọi hàm Java chạy nhanh hơn” | CPU vẫn thực thi trên phần cứng thật | Kỳ vọng tăng throughput khi có nhiều tác vụ chờ |
| “Nhiều virtual threads = nhiều lõi CPU” | Virtual threads dùng carrier chạy trên CPU hữu hạn | Giới hạn parallelism cho công việc CPU-bound |
| “Có HTTP call thì chắc chắn toàn bộ tác vụ I/O-bound” | Có thể tốn nhiều CPU sau khi tải | Đo thời gian từng giai đoạn |
| “Thread.sleep là benchmark I/O thật” | Sleep chỉ mô phỏng chờ | Dùng workload đại diện khi đánh giá production |
| “Cứ dùng virtual-thread-per-task là DB không nghẽn” | DB/connection pool vẫn có capacity riêng | Theo dõi pool, query, timeout và quota |
| “Pool lại virtual threads để tiết kiệm” | Virtual threads đã được thiết kế theo từng tác vụ | Không pool virtual threads; dùng capacity limiter |
| “Fixed CPU pool tự chống quá tải” | Queue có thể tăng không giới hạn | Bổ sung backpressure/queue giới hạn |
| “Future.get(timeout) tự hủy tác vụ” | Timeout chỉ kết thúc việc chờ get | Dùng **cancel(true)** và timeout ở I/O |
| “Mọi synchronized trên virtual thread đều pin carrier” | JEP 491 đã thay đổi ngữ nghĩa pinning từ JDK 24 | Dựa trên tài liệu và JFR của Java 27 |
| “Pinning luôn gây lỗi chức năng” | Pinning chủ yếu hạn chế scalability | Đo thời gian pin và tác động throughput |
| “ThreadLocal cache tiết kiệm bộ nhớ với hàng triệu virtual threads” | Một virtual thread mới mỗi task; cache nhân bản | Dùng dữ liệu bất biến chia sẻ hoặc scoped context |
| “Latency thấp hơn là nhờ tạo nhiều thread” | Thông thường thời gian một I/O operation không đổi | Phân biệt latency và throughput |
| “CPU thấp tức là hệ thống còn năng lực” | Có thể chờ DB, lock, network, quota | Quan sát tài nguyên ngoài và hàng đợi |
| “ExecutorService.close() hủy ngay tất cả tasks” | Close chờ hoàn thành theo shutdown có thứ tự | Thiết kế thời hạn, cancellation và lifecycle |
| “Gọi CPU-bound task trong virtual thread là sai” | Vẫn hợp lệ về chức năng | Chỉ giới hạn/tách khi thực sự là bottleneck |

## 18. Bài thực hành

Hãy xây dựng ứng dụng mô phỏng một hệ thống xử lý dữ liệu gồm hai giai đoạn:

1. **Giai đoạn chờ**: mỗi tác vụ chờ 200 ms (mô phỏng I/O).
2. **Giai đoạn CPU**: mỗi tác vụ tính số lượng số nguyên tố trong khoảng chỉ định.

Thực hiện:

- Chạy 20 tác vụ chờ bằng **Executors.newFixedThreadPool(4)**.
- Chạy cùng 20 tác vụ chờ bằng **Executors.newVirtualThreadPerTaskExecutor()**.
- Đo tổng thời gian bằng **System.nanoTime()**, ghi nhận kết quả nhưng không coi đó là benchmark chuẩn.
- Đổi chương trình thành 20 tác vụ chỉ tính toán CPU. Quan sát cách throughput thay đổi khi số worker là 2, 4, 8 và khi dùng virtual-thread-per-task.
- Chạy một pipeline hỗn hợp: chờ giả lập rồi tính số nguyên tố. Đo riêng thời gian chờ và CPU.
- Thêm **Semaphore(5)** để giới hạn số tác vụ được phép vào giai đoạn gọi dịch vụ.
- Đặt timeout và bảo đảm **finally** luôn release permit.
- Viết bản giải thích vì sao việc tạo thêm 1.000 virtual threads không giúp một tác vụ CPU đơn lẻ nhanh hơn.

**Câu hỏi tự kiểm tra:**

1. Vì sao một virtual thread chờ HTTP có thể nhường carrier?
2. Một virtual thread có thực thi code Java trên CPU thật không?
3. Khi nào fixed platform-thread pool có ích cho CPU-heavy tasks?
4. Vì sao Semaphore phù hợp hơn một virtual-thread pool để giới hạn kết nối?
5. Sự khác nhau giữa tăng concurrency và tăng parallelism là gì?
6. **Future.get(timeout)** có tự hủy task không?
7. Vấn đề pinning do **synchronized** đã thay đổi thế nào từ JDK 24?
8. Khi thấy CPU thấp và latency cao, bạn sẽ kiểm tra các tài nguyên nào trước?

## 19. Ghi nhớ

- **I/O-bound** chủ yếu chờ; **CPU-bound** chủ yếu tính toán. Đây là đặc tính của tác vụ, không phải tên của thread.
- Virtual threads thích hợp cho số lượng lớn tác vụ blocking I/O; khi chờ phù hợp, chúng có thể nhường carrier để tác vụ khác chạy.
- Virtual threads **không làm tăng số lõi CPU** hoặc tự giảm thời gian tính toán một tác vụ CPU-intensive.
- **Executors.newVirtualThreadPerTaskExecutor()** tạo một virtual thread cho mỗi task, không tái sử dụng chúng trong pool.
- Hãy giới hạn **tài nguyên ngoài** bằng connection pool, Semaphore, timeout và backpressure.
- Với CPU-heavy tasks, cần mức song song hữu hạn, kiểm soát hàng đợi và đo trên workload thật.
- **Thread.sleep** mô phỏng tình trạng chờ, không phải benchmark hiệu năng I/O.
- **Future.get(timeout)** giới hạn thời gian chờ kết quả; cancellation là thao tác riêng.
- Từ JDK 24, **synchronized** thông thường không còn gây pinning như trước; trên Java 27 vẫn cần quan sát native/foreign pinning nếu có.
- Dùng JFR, jcmd, CPU profiling, độ trễ I/O, phân vị latency và các chỉ số kết nối để xác định nút thắt.
- Với một tác vụ kết hợp I/O và CPU, đo từng giai đoạn; không buộc toàn bộ pipeline vào một nhãn duy nhất.
- Ngữ cảnh tác vụ như request ID có thể dùng **ScopedValue** đã chính thức, nhưng đó là vấn đề riêng với lựa chọn mô hình thread.

## Tài liệu tham khảo

- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html)
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html)
- [Java SE 27 API — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 27 API — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 27 API — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 27 API — Semaphore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 27 API — ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html)
- [OpenJDK JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491)
- [OpenJDK JEP 506 — Scoped Values (Java 25)](https://openjdk.org/jeps/506)
