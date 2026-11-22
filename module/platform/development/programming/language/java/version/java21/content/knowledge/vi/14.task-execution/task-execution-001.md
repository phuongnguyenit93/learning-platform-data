# Executors.newVirtualThreadPerTaskExecutor và mô hình mỗi task một thread

Trong Java 21, Executors.newVirtualThreadPerTaskExecutor() tạo một ExecutorService thực thi mỗi tác vụ được chấp nhận bằng một virtual thread mới. Mỗi task được submit hoặc execute sẽ có virtual thread riêng. Khi task hoàn tất, virtual thread kết thúc; executor không giữ một nhóm virtual thread cố định để tái sử dụng như thread pool truyền thống.

Mô hình này phù hợp với ứng dụng có nhiều tác vụ đồng thời thường xuyên chờ I/O, chẳng hạn gọi HTTP, truy vấn cơ sở dữ liệu hoặc đọc ghi dữ liệu. Virtual thread giúp giảm chi phí quản lý thread ở quy mô lớn, nhưng không làm tăng năng lực CPU, không tự giới hạn số yêu cầu đồng thời và không thay thế việc quản lý tài nguyên bên ngoài.

## 1. API tạo virtual-thread-per-task executor

Phương thức Executors.newVirtualThreadPerTaskExecutor() thuộc gói java.util.concurrent và có từ Java 21:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

Giá trị trả về có kiểu ExecutorService. Vì vậy, có thể dùng các thao tác chuẩn như execute(), submit(), invokeAll(), shutdown() và close() để quản lý tác vụ.

Điểm quan trọng của executor này là mô hình thực thi:

- Mỗi task được giao cho executor chạy trên một virtual thread mới.
- Virtual thread kết thúc khi task hoàn tất.
- Executor không tái sử dụng một nhóm virtual thread cố định giữa các task.
- Executor có thể tạo số lượng virtual thread lớn; nó không áp đặt một giới hạn concurrency cố định như fixed thread pool.

Có thể hình dung:

~~~text
ExecutorService
    |
    +-- task A --> virtual thread A --> kết thúc
    |
    +-- task B --> virtual thread B --> kết thúc
    |
    +-- task C --> virtual thread C --> kết thúc
    |
    +-- task D --> virtual thread D --> kết thúc
~~~

Mỗi task có vòng đời thread riêng. Điều này giúp lập trình theo kiểu đồng bộ quen thuộc: task có thể gọi phương thức blocking như đọc socket hoặc chờ phản hồi mà không cần tự tổ chức callback cho mọi bước I/O.

## 2. Submit và execute task

Có thể giao một tác vụ không cần nhận kết quả bằng execute():

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class Main {
    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            executor.execute(() -> {
                System.out.println(
                        "Running on virtual thread: "
                                + Thread.currentThread().isVirtual());
            });
        }
    }
}
~~~

Trong ví dụ, executor tạo virtual thread để chạy task. Khối try-with-resources đóng executor khi phạm vi kết thúc; close() chờ các task đã được giao hoàn tất trước khi trả về.

Nếu cần nhận kết quả hoặc kiểm tra lỗi của task, dùng submit():

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class Main {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> future = executor.submit(() -> {
                Thread.sleep(300);
                return "Completed";
            });

            System.out.println(future.get());
        }
    }
}
~~~

submit() trả về Future. Gọi get() chờ task hoàn tất và nhận kết quả. Nếu task kết thúc bằng exception, get() ném ExecutionException và nguyên nhân gốc có thể được lấy từ cause.

Với submit(Runnable), Future<?> có thể được dùng để chờ hoàn tất hoặc kiểm tra lỗi, dù task không trả về giá trị. Nếu chỉ gọi execute(), ứng dụng không nhận Future cho task đó; hãy chọn API dựa trên nhu cầu quản lý kết quả và lỗi.

## 3. Quản lý vòng đời executor

ExecutorService là tài nguyên cần được đóng sau khi đã giao đủ task. Cách đơn giản trong Java 21 là dùng try-with-resources:

~~~java
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> processOrder("ORD-1001"));
    executor.submit(() -> processOrder("ORD-1002"));
    executor.submit(() -> processOrder("ORD-1003"));
}

// Các task đã submit hoàn tất trước khi luồng điều khiển đi qua đây.
System.out.println("All orders processed");
~~~

ExecutorService triển khai AutoCloseable. Khi close() được gọi, executor bắt đầu orderly shutdown: không nhận task mới và chờ những task đã submit hoàn tất trước khi close() trả về.

Có thể quản lý thủ công bằng shutdown():

~~~java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();

try {
    executor.submit(() -> processOrder("ORD-1001"));
    executor.submit(() -> processOrder("ORD-1002"));
} finally {
    executor.shutdown();
}
~~~

shutdown() ngừng nhận task mới nhưng cho phép các task đã giao tiếp tục chạy. Nếu cần chờ executor kết thúc, có thể dùng awaitTermination() sau shutdown().

shutdownNow() yêu cầu dừng các task đang chạy bằng cách gửi interrupt tới thread thực thi và trả về những task chưa bắt đầu nếu có. Đây là yêu cầu hủy tốt nhất có thể theo hợp đồng executor; task phải hợp tác với interruption. Không thể giả định mọi tác vụ sẽ dừng ngay lập tức nếu chúng bỏ qua interrupt hoặc đang thực hiện thao tác không phản hồi.

Với code thông thường, try-with-resources giúp giảm nguy cơ quên đóng executor. Nếu ứng dụng cần thời hạn shutdown hoặc chính sách hủy riêng, hãy thiết kế rõ thời gian chờ, interrupt và xử lý task chưa hoàn tất.

## 4. Mỗi task một virtual thread không có nghĩa là vô hạn tài nguyên

Virtual thread có chi phí thấp hơn platform thread trong nhiều tình huống, nhưng mỗi task vẫn sử dụng tài nguyên thực tế. Ví dụ:

- Mỗi yêu cầu HTTP có thể cần một socket và bộ nhớ cho trạng thái xử lý.
- Mỗi truy vấn cơ sở dữ liệu có thể chiếm một connection trong connection pool.
- Dịch vụ bên ngoài có thể giới hạn số request đồng thời hoặc số request mỗi giây.
- Task có thể giữ buffer, dữ liệu kết quả, transaction hoặc tài nguyên khác trong lúc chờ.

Nếu gửi hàng chục nghìn task cùng lúc tới một database chỉ có 30 connection, virtual thread không tạo thêm connection cho database. Các task còn lại có thể phải chờ connection, chiếm bộ nhớ và làm tăng độ trễ.

Vì thế, cần phân biệt hai giới hạn:

1. **Số lượng task có thể được tạo:** executor mô hình mỗi task một virtual thread không đặt giới hạn concurrency cố định.
2. **Số lượng thao tác được phép đi vào tài nguyên dùng chung:** ứng dụng phải giới hạn theo capacity thực tế của database, dịch vụ từ xa, file descriptor hoặc hệ thống khác.

Virtual thread giúp xử lý nhiều tác vụ chờ đồng thời với chi phí thread thấp; nó không thay thế backpressure, rate limiting hoặc giới hạn connection.

## 5. Giới hạn concurrency bằng Semaphore khi cần

Nếu một dịch vụ bên ngoài chỉ cho phép tối đa một số lượng request đồng thời, có thể dùng Semaphore để giới hạn số task đi vào vùng truy cập tài nguyên đó.

~~~java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(20);

void callRemoteService() throws InterruptedException {
    permits.acquire();
    try {
        // Thực hiện request tới dịch vụ từ xa.
        invokeRemoteApi();
    } finally {
        permits.release();
    }
}
~~~

Khi tích hợp với virtual-thread-per-task executor:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (Request request : requests) {
        executor.submit(() -> {
            permits.acquire();
            try {
                processRequest(request);
            } finally {
                permits.release();
            }
            return null;
        });
    }
}
~~~

Trong ví dụ, có thể có nhiều virtual thread được tạo, nhưng tối đa 20 task cùng giữ permit để thực hiện phần xử lý được giới hạn. Những task khác chờ permit. Khi task hoàn thành hoặc gặp lỗi, finally bảo đảm permit được trả lại.

Nếu acquire() bị interrupt trước khi lấy được permit, task kết thúc theo luồng xử lý exception của nó và không được gọi release() cho permit chưa sở hữu. Đặt acquire() trước try-finally như ví dụ giúp tránh trả lại permit sai.

Semaphore là một cách giới hạn concurrency theo tài nguyên. Tùy hệ thống, có thể phù hợp hơn khi dùng trực tiếp connection pool, bulkhead của thư viện mạng hoặc rate limiter. Không nên đặt một giới hạn tùy ý mà không dựa trên capacity và mục tiêu độ trễ của hệ thống.

## 6. Virtual thread phù hợp nhất với loại công việc nào?

Virtual thread đặc biệt hữu ích với tác vụ có thời gian chờ đáng kể:

- Gọi nhiều dịch vụ HTTP độc lập.
- Xử lý request web có các bước I/O đồng bộ.
- Truy vấn cơ sở dữ liệu hoặc message broker.
- Đọc ghi file hoặc chờ socket.
- Ghép nhiều thao tác blocking trong một luồng điều khiển dễ đọc.

Ví dụ, mỗi request có thể gọi hai dịch vụ độc lập và chờ kết quả:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Customer> customerFuture =
            executor.submit(() -> customerService.find(customerId));

    Future<List<Order>> ordersFuture =
            executor.submit(() -> orderService.findByCustomer(customerId));

    Customer customer = customerFuture.get();
    List<Order> orders = ordersFuture.get();

    return new CustomerSummary(customer, orders);
}
~~~

Hai thao tác có thể tiến hành đồng thời. Thread hiện tại chờ kết quả bằng Future.get(), còn mỗi task chạy trong virtual thread riêng.

Virtual thread không làm một tác vụ CPU-bound chạy nhanh hơn chỉ bằng cách đổi loại thread. Nếu mỗi task chủ yếu tính toán liên tục, số lượng task chạy đồng thời vẫn bị giới hạn bởi số core CPU và tài nguyên máy. Với công việc CPU-bound, một executor có số worker platform thread được giới hạn theo năng lực CPU thường phù hợp hơn.

## 7. Không dùng virtual-thread-per-task executor như một thread pool truyền thống

Một fixed thread pool thường tái sử dụng số lượng platform thread cố định để chạy nhiều task. Virtual-thread-per-task executor áp dụng mô hình khác: tạo một virtual thread mới cho mỗi task.

| Đặc điểm | Fixed thread pool | Virtual-thread-per-task executor |
|---|---|---|
| Thread thực thi | Tái sử dụng nhóm platform thread cố định | Tạo virtual thread mới cho mỗi task |
| Concurrency | Bị giới hạn bởi số worker | Không đặt giới hạn concurrency cố định |
| Task chờ I/O | Worker bị chiếm trong thời gian chờ | Virtual thread có thể nhường carrier khi blocking operation hỗ trợ unmount |
| Giới hạn tài nguyên bên ngoài | Cần quản lý | Vẫn cần quản lý |
| Phù hợp | CPU-bound hoặc cần giới hạn worker | Nhiều tác vụ đồng thời, chủ yếu chờ I/O |

Không nên tạo pool virtual thread để tái sử dụng. Mô hình virtual thread được thiết kế quanh nguyên tắc một virtual thread cho một task; khi task kết thúc, thread kết thúc. Nếu cần giới hạn số thao tác đồng thời, hãy giới hạn tài nguyên hoặc vùng công việc bằng semaphore, connection pool hoặc cơ chế tương đương thay vì giữ một nhóm virtual thread chờ được tái sử dụng.

## 8. Xử lý kết quả và lỗi của nhiều task

Khi submit nhiều Callable, mỗi Future đại diện cho kết quả của một task. Có thể lưu Future để thu thập kết quả sau:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<String>> futures = new ArrayList<>();

    for (String id : orderIds) {
        futures.add(executor.submit(() -> loadOrder(id)));
    }

    for (Future<String> future : futures) {
        String result = future.get();
        System.out.println(result);
    }
}
~~~

Vòng lặp get() ở đây thu kết quả theo thứ tự Future được thêm vào danh sách. Nó không có nghĩa các task chạy lần lượt: các virtual thread đã được executor khởi chạy độc lập và có thể hoàn thành theo thứ tự khác.

Nếu một task thất bại, Future tương ứng sẽ báo lỗi qua ExecutionException khi gọi get(). Ứng dụng cần quyết định tiếp tục xử lý kết quả khác, hủy task còn lại hay báo lỗi cho tầng gọi.

Nếu chỉ dùng execute() hoặc submit() mà bỏ qua Future, executor vẫn chờ task kết thúc khi đóng, nhưng ứng dụng có thể không quan sát được exception theo cách cần thiết. Khi kết quả và lỗi quan trọng, hãy giữ và kiểm tra Future.

## 9. invokeAll và invokeAny

ExecutorService còn cung cấp invokeAll() và invokeAny() để thực hiện nhóm Callable:

- invokeAll() gửi một collection task và trả về danh sách Future sau khi tất cả task hoàn tất. Nếu lời gọi bị interrupt trong lúc chờ, các task chưa hoàn tất bị hủy và phương thức ném InterruptedException.
- invokeAny() trả kết quả của một task hoàn thành thành công và hủy các task còn lại. Nếu không task nào thành công, phương thức ném ExecutionException.

Ví dụ với invokeAll():

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

List<Callable<Integer>> tasks = List.of(
        () -> calculate(10),
        () -> calculate(20),
        () -> calculate(30)
);

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<Integer>> results = executor.invokeAll(tasks);

    for (Future<Integer> result : results) {
        System.out.println(result.get());
    }
}
~~~

Các task trong danh sách có thể chạy đồng thời trên các virtual thread khác nhau. invokeAll() phù hợp khi cần đợi toàn bộ kết quả. Nếu chỉ cần kết quả đầu tiên thành công, invokeAny() có thể phù hợp hơn, nhưng cần cân nhắc việc hủy và tác dụng phụ của các task còn lại.

Các phương thức này không tự tạo một giới hạn concurrency nghiệp vụ. Nếu danh sách có rất nhiều task, executor vẫn có thể tạo rất nhiều virtual thread; hãy giới hạn tải theo khả năng hệ thống.

## 10. Hủy task và xử lý interruption

Có thể yêu cầu hủy một task thông qua Future.cancel(true). Tham số true yêu cầu interrupt thread đang thực hiện task nếu task đã bắt đầu.

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Void> future = executor.submit(() -> {
        try {
            performLongOperation();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            cleanup();
        }
        return null;
    });

    // Hủy task và yêu cầu interrupt nếu task đã bắt đầu.
    future.cancel(true);
}
~~~

Interruption là cơ chế hợp tác. Task cần kiểm tra hoặc phản hồi interrupt, đặc biệt khi chờ các API có thể ném InterruptedException. Nếu task bỏ qua interrupt và tiếp tục chạy, yêu cầu cancel không thể bảo đảm dừng ngay lập tức.

Khi viết task, nên:

- Không nuốt InterruptedException rồi tiếp tục như chưa có gì xảy ra.
- Nếu không thể ném InterruptedException lên tầng gọi, khôi phục interrupt status bằng Thread.currentThread().interrupt().
- Giải phóng tài nguyên trong finally hoặc cơ chế quản lý tài nguyên phù hợp.
- Thiết kế thao tác I/O và lời gọi dịch vụ có timeout nếu có thể chờ vô hạn.

Việc hủy task cũng không tự động hoàn tác các tác dụng phụ đã xảy ra, chẳng hạn dữ liệu đã ghi vào database hoặc request đã gửi tới dịch vụ từ xa. Hãy thiết kế tính idempotent hoặc cơ chế bù trừ khi nghiệp vụ yêu cầu.

## 11. Lưu ý về blocking và giới hạn của virtual thread trong Java 21

Virtual thread cho phép mã sử dụng các thao tác blocking quen thuộc. Với nhiều thao tác blocking trong thư viện JDK, virtual thread có thể unmount khỏi carrier thread trong lúc chờ, giúp carrier phục vụ virtual thread khác.

Tuy nhiên, không phải mọi blocking operation đều có thể nhường carrier trong mọi tình huống. Trong Java 21, một virtual thread có thể bị pin vào carrier khi thực hiện blocking operation trong một số vùng synchronized hoặc native method. Khi pinning xảy ra thường xuyên, khả năng mở rộng có thể giảm.

Với tác vụ dùng virtual thread:

- Tránh giữ monitor lâu trong khi gọi dịch vụ từ xa hoặc thực hiện I/O blocking.
- Đo hiệu năng bằng workload gần với môi trường thật.
- Dùng Java Flight Recorder và các công cụ quan sát phù hợp để phát hiện pinning hoặc điểm nghẽn.
- Không cố định số virtual thread dựa trên số carrier thread; scheduler quản lý việc lập lịch virtual thread trên các platform thread nền.

Virtual thread giảm chi phí thread cho workload chờ I/O, nhưng không làm biến mất lock contention, giới hạn connection, giới hạn file descriptor, thời gian phản hồi dịch vụ hoặc áp lực bộ nhớ.

## 12. Những lỗi thiết kế thường gặp

| Cách làm chưa phù hợp | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng executor giới hạn số task đồng thời | Quá nhiều task có thể cùng chờ một database hoặc dịch vụ | Dùng semaphore, connection pool hoặc rate limiter |
| Dùng virtual thread như worker thread trong pool | Đi ngược mô hình một task một thread | Tạo executor bằng newVirtualThreadPerTaskExecutor() cho phạm vi công việc |
| Dùng virtual thread cho tính toán CPU-bound nặng với số task rất lớn | Tăng cạnh tranh CPU và bộ nhớ nhưng không tăng năng lực tính toán | Giới hạn CPU-bound task theo năng lực CPU |
| Quên đóng executor | Task và tài nguyên có thể tiếp tục tồn tại ngoài phạm vi mong muốn | Dùng try-with-resources hoặc shutdown có chờ |
| Bỏ qua Future khi task có thể lỗi | Không quan sát được kết quả hoặc exception theo cách mong muốn | Lưu Future và gọi get() |
| Nuốt InterruptedException | Task khó dừng khi timeout hoặc shutdown | Khôi phục interrupt status hoặc truyền exception |
| Nghĩ cancel(true) hoàn tác tác dụng phụ | Trạng thái bên ngoài có thể đã được cập nhật | Thiết kế idempotency và xử lý bù trừ |
| Submit lượng task không giới hạn từ đầu vào | Tăng bộ nhớ, socket và áp lực downstream | Áp dụng admission control và backpressure |

## 13. Quy trình áp dụng trong ứng dụng

Khi chuyển một nhóm tác vụ sang virtual-thread-per-task executor, có thể thực hiện theo trình tự:

1. Xác định đơn vị công việc: một request, một tác vụ I/O hoặc một đơn vị xử lý độc lập.
2. Kiểm tra task chủ yếu chờ I/O hay tiêu thụ CPU.
3. Tạo executor bằng Executors.newVirtualThreadPerTaskExecutor().
4. Giao task bằng execute() nếu không cần Future, hoặc submit() nếu cần kết quả và trạng thái hoàn tất.
5. Xác định giới hạn của database, HTTP client, broker và các tài nguyên dùng chung.
6. Bổ sung semaphore, connection pool hoặc rate limiter ở ranh giới tài nguyên cần giới hạn.
7. Quản lý executor bằng try-with-resources hoặc shutdown/awaitTermination phù hợp.
8. Xác định cách thu thập lỗi, timeout, hủy task và xử lý interruption.
9. Đo độ trễ, throughput, bộ nhớ, số kết nối và hành vi khi tải tăng.

## Kết luận

Executors.newVirtualThreadPerTaskExecutor() cung cấp mô hình mỗi task một virtual thread trong Java 21. Mô hình này giúp viết ứng dụng đồng thời có nhiều tác vụ blocking, đặc biệt là I/O, bằng luồng điều khiển đơn giản. Executor không tái sử dụng virtual thread như một pool cố định và không tự giới hạn concurrency. Ứng dụng vẫn cần quản lý vòng đời executor, thu thập kết quả và lỗi, xử lý interruption, đồng thời đặt giới hạn theo năng lực của tài nguyên bên ngoài.

## Tài liệu tham khảo

- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
