# Hủy thao tác và kết thúc có kiểm soát

> **Chương:** Độ tin cậy  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **yêu cầu hủy**, **tác vụ thực sự dừng**, **hết thời gian chờ** và **kết thúc dịch vụ có kiểm soát**.
2. Thiết kế tác vụ Java có thể nhận tín hiệu hủy, dừng tại điểm an toàn và giải phóng tài nguyên.
3. Sử dụng `Thread.interrupt()`, `InterruptedException`, `Future.cancel(...)` và `ExecutorService` đúng với giới hạn thực tế của chúng.
4. Xác định cách xử lý công việc đang dở, giao dịch, thông điệp hàng đợi và tác dụng phụ bên ngoài khi hủy.
5. Lập quy trình dừng dịch vụ có thời hạn, có quan sát và có kiểm thử cho các tình huống tranh chấp (race condition).

## 1. Vì sao hủy và dừng có kiểm soát là một phần của độ tin cậy?

Một chương trình đáng tin cậy cần hoàn thành yêu cầu đúng; nó cũng cần **dừng đúng khi yêu cầu không còn cần thiết hoặc môi trường đang kết thúc**. Nếu thao tác đã bị người dùng hủy mà vẫn tiếp tục tiêu tốn tài nguyên, hệ thống có thể chậm hoặc gây tác dụng phụ ngoài ý muốn. Nếu dịch vụ bị tắt khi đang ghi dữ liệu, gửi thanh toán hoặc xử lý hàng đợi, hệ thống có thể để lại trạng thái dở dang hoặc mất công việc.

Ví dụ thực tế:

- Người dùng hủy thao tác xuất báo cáo dài: hệ thống cần biết có tiếp tục tạo tệp không, tệp tạm được dọn ở đâu và trạng thái cuối được ghi thế nào.
- Một HTTP request hết hạn: không nên tiếp tục gọi nhiều dịch vụ tốn kém nếu không còn ai cần kết quả, nhưng phải tránh xem timeout là bằng chứng công việc đã dừng.
- Container nhận tín hiệu dừng để triển khai phiên bản mới: cần ngừng nhận công việc mới, xử lý hoặc bàn giao công việc đang chạy, rồi mới đóng tài nguyên.
- Worker đang thực hiện lệnh thanh toán: không thể giả định ngắt thread sẽ hoàn tác yêu cầu đã gửi ra hệ thống bên ngoài.

**Hủy an toàn** là một hợp đồng giữa bên yêu cầu và bên thực hiện: yêu cầu hủy được truyền đi, tác vụ quan sát tín hiệu, chọn thời điểm có thể dừng, dọn dẹp và công bố kết quả cuối. **Kết thúc có kiểm soát** (graceful shutdown) là quá trình dừng nhận việc mới, giải quyết việc đang chạy trong giới hạn thời gian và giải phóng tài nguyên trước khi tiến trình kết thúc.

### Phân biệt những trạng thái dễ nhầm

| Trạng thái/sự kiện | Ý nghĩa | Điều chưa thể kết luận |
| --- | --- | --- |
| **Cancel requested** | Đã phát tín hiệu muốn hủy | Tác vụ đã dừng hoặc tác dụng phụ đã được hoàn tác |
| **Cancelled** | Theo hợp đồng hệ thống, tác vụ kết thúc theo đường hủy | Mọi hành động đã thực hiện trước đó đều bị đảo ngược |
| **Timed out** | Bên chờ đã vượt hạn chờ hoặc deadline | Công việc phía sau chắc chắn đã ngừng |
| **Failed** | Tác vụ gặp lỗi khi thực hiện | Lỗi do yêu cầu hủy hay do nguyên nhân độc lập |
| **Completed** | Tác vụ hoàn tất theo tiêu chí thành công | Bên gọi còn đang chờ hoặc đã nhận được kết quả |
| **Shutdown requested** | Dịch vụ được yêu cầu dừng | Tất cả tác vụ, kết nối và luồng đều đã kết thúc |

Một lệnh `cancel()` trả về `true` thường chỉ phản ánh **trạng thái hủy theo API tương ứng**, không phải cam kết rằng mọi dòng mã của tác vụ đã ngừng chạy. Người thiết kế cần phân biệt trạng thái **được công bố** với trạng thái **thực tế của hoạt động bên ngoài**.

## 2. Xây dựng hợp đồng hủy rõ ràng

Trước khi triển khai, cần thống nhất:

1. **Ai có quyền yêu cầu hủy?** Người tạo tác vụ, quản trị viên, HTTP client, scheduler hay hệ thống giám sát?
2. **Điều gì được hủy?** Một lượt thử, một tác vụ logic, toàn bộ batch, các tác vụ con hay cả dịch vụ?
3. **Hủy có hiệu lực ở điểm nào?** Trước khi bắt đầu, giữa các bản ghi, khi chờ I/O hay sau khi đã ghi nhận một giao dịch?
4. **Kết quả nào được coi là thành công?** Dừng thực thi, hoàn tác thay đổi chưa commit, bù trừ tác dụng phụ hay chỉ dừng các bước còn lại?
5. **Bên gọi nhận tín hiệu nào?** Chấp nhận yêu cầu hủy, đang hủy, đã hủy, hoàn tất hoặc hủy không còn khả thi?
6. **Ai quản lý tài nguyên và công việc dở?** Chủ sở hữu của thread pool, kết nối, tệp tạm, thông điệp hay lệnh thanh toán?

Một mô hình trạng thái khái niệm có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: bắt đầu
    QUEUED --> CANCELLED: hủy khi chưa chạy
    RUNNING --> COMPLETED: hoàn tất
    RUNNING --> FAILED: lỗi
    RUNNING --> CANCELLING: yêu cầu hủy
    CANCELLING --> CANCELLED: dừng ở điểm an toàn
    CANCELLING --> COMPLETED: hoàn tất đã thắng cuộc đua
    CANCELLING --> FAILED: lỗi trước khi kết thúc
~~~

Đây là **mô hình thiết kế**, không phải máy trạng thái tự động do Java cung cấp. Hủy có thể xảy ra đồng thời với hoàn tất; hệ thống cần quy tắc chuyển trạng thái nguyên tử (ví dụ compare-and-set hoặc cập nhật có điều kiện trong database), tránh hai kết quả cuối mâu thuẫn. Khi đã có tác dụng phụ không thể đảo ngược, cần mô tả rõ giới hạn của trạng thái `CANCELLED`.

**Tính idempotent của yêu cầu hủy:** gửi yêu cầu hủy lần hai không được tạo thêm tác dụng phụ bất ngờ. Có thể phản hồi trạng thái hiện tại thay vì cố bắt đầu một quy trình hủy mới.

## 3. Hủy cộng tác trong Java: ngắt là tín hiệu, không phải cưỡng chế

Java chủ yếu dùng **cơ chế hủy hợp tác** (cooperative cancellation): một bên phát tín hiệu, bên chạy kiểm tra tín hiệu và tự chọn thời điểm thoát. `Thread.interrupt()` đặt cờ ngắt trên thread. Nó không bảo đảm dừng tức thì, không tự đóng mọi tài nguyên và không hoàn tác giao dịch.

Một số thao tác chờ như `Thread.sleep()`, `Object.wait()` hoặc `BlockingQueue.take()` phản ứng với interrupt bằng cách ném `InterruptedException`. Nhiều lời gọi thư viện, tác vụ CPU hoặc I/O bên ngoài **không tự dừng** chỉ vì thread bị ngắt; cần kiểm tra đặc tính API và cấu hình timeout thích hợp.

### 3.1. Kiểm tra cờ ngắt tại điểm an toàn

Ví dụ một tác vụ xử lý lần lượt các bản ghi, với thao tác `processOne` do ứng dụng định nghĩa:

~~~java
import java.util.List;

interface RecordHandler {
    void processOne(String id) throws InterruptedException;
}

static int processBatch(
        List<String> recordIds,
        RecordHandler handler
) throws InterruptedException {
    int processed = 0;

    for (String id : recordIds) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Batch cancellation requested");
        }

        handler.processOne(id); // Phải có chính sách timeout/interrupt riêng.
        processed++;
    }

    return processed;
}
~~~

Tác vụ kiểm tra cờ **trước khi bắt đầu bản ghi tiếp theo**. Điểm dừng này hợp lý khi mỗi bản ghi có thể xử lý độc lập. Nếu mỗi bản ghi chứa giao dịch nhiều bước, cần dừng ở ranh giới an toàn của giao dịch, tránh bỏ ngang ngay sau khi ghi một phần dữ liệu.

`Thread.currentThread().isInterrupted()` **chỉ đọc cờ**, không xóa nó. Trong khi đó, phương thức tĩnh `Thread.interrupted()` đọc **và xóa** trạng thái ngắt của thread hiện tại. Việc vô tình xóa cờ có thể khiến tầng bên ngoài không còn biết yêu cầu hủy.

### 3.2. Xử lý `InterruptedException`

Khi một thao tác chờ ném `InterruptedException`, cờ ngắt thường đã được xóa bởi thao tác đó. Có hai hướng hợp lý:

**Nếu API hiện tại cho phép, chuyển tiếp ngoại lệ** để tầng sở hữu tác vụ quyết định:

~~~java
static String waitForResult(
        java.util.concurrent.BlockingQueue<String> queue
) throws InterruptedException {
    return queue.take();
}
~~~

**Nếu phải bắt ngoại lệ rồi kết thúc tại đây, khôi phục cờ ngắt** để những tầng gọi phía trên vẫn nhận biết tín hiệu:

~~~java
static void runWorker(
        java.util.concurrent.BlockingQueue<String> queue
) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            handle(item); // Hàm nghiệp vụ do ứng dụng triển khai.
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    } finally {
        releaseWorkerResources(); // Dọn tài nguyên do worker sở hữu.
    }
}
~~~

Hai hàm `handle` và `releaseWorkerResources` chỉ là điểm mở rộng minh họa. Với hệ thống thật, cần xác định ai sở hữu item đã lấy khỏi queue và chuyện gì xảy ra nếu đang `handle(item)` thì hủy.

**Mẫu sai thường gặp:**

~~~java
try {
    queue.take();
} catch (InterruptedException ignored) {
    // Sai: nuốt tín hiệu rồi tiếp tục làm việc vô hạn.
}
~~~

Không nên dùng `Thread.stop()` để cưỡng chế dừng, vì việc dừng bất thường có thể phá vỡ bất biến trạng thái và tài nguyên. Cũng không nên biến mọi `InterruptedException` thành lỗi nghiệp vụ thông thường rồi retry không giới hạn.

### 3.3. Hủy tác vụ CPU và các lời gọi chặn lâu

Với một vòng lặp tính toán dài, cần kiểm tra tín hiệu theo chu kỳ hoặc ở mỗi đơn vị công việc đủ nhỏ. Với truy vấn database, HTTP call và I/O, cần timeout được hỗ trợ bởi thư viện, cơ chế hủy riêng của API hoặc đóng tài nguyên theo hợp đồng thư viện.

Một lời gọi `Future.cancel(true)` có thể phát interrupt nhưng **không chứng minh** socket, truy vấn hay yêu cầu của dịch vụ bên ngoài đã bị dừng. Khi thư viện không hỗ trợ ngắt, việc hủy có thể bị trì hoãn đến lúc lời gọi trả về hoặc timeout.

Đừng kiểm tra interrupt bên trong từng phép cộng cực nhỏ nếu việc đó làm tăng đáng kể chi phí chạy; nên chọn **điểm kiểm tra có độ trễ hủy chấp nhận được**, xác định bằng yêu cầu hệ thống.

## 4. `Future`, `CompletableFuture` và giới hạn của lệnh hủy

`ExecutorService.submit(...)` trả về `Future` để bên gọi theo dõi kết quả:

~~~java
import java.util.concurrent.*;

ExecutorService pool = Executors.newSingleThreadExecutor();
Future<Integer> future = pool.submit(() -> {
    int processed = 0;
    for (int i = 0; i < 1_000; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Cancelled");
        }
        // Giả sử mỗi bước tính toán có thể dừng trước tác dụng phụ tiếp theo.
        processed++;
    }
    return processed;
});

// Tại một thời điểm sau khi submit, khi không còn cần kết quả:
boolean requestAccepted = future.cancel(true);
~~~

Lưu ý mã trên chỉ minh họa cơ chế gửi yêu cầu; trong ứng dụng thật, **đối tượng sở hữu pool phải đóng pool** theo quy trình ở phần sau.

- `future.cancel(true)` cố đưa `Future` vào trạng thái bị hủy và, nếu đang chạy trong thread do `Future` quản lý, **yêu cầu ngắt** thread đó. Tác vụ có hợp tác hay không phụ thuộc mã thực thi.
- `future.cancel(false)` không yêu cầu ngắt thread đang chạy; vẫn có thể chuyển trạng thái của `Future` sang canceled tùy việc tác vụ đã hoàn thành hay chưa và triển khai cụ thể.
- `future.get()` trên `Future` bị hủy ném `CancellationException`; `isCancelled()` không phải phép đo chắc chắn rằng side effect đã dừng.
- Nếu tác vụ đã hoàn tất trước khi hủy, `cancel(...)` có thể trả `false`: việc hoàn tất và hủy có một **cuộc đua thời gian**.
- Tác vụ đang chạy có thể đã gửi lệnh ra mạng trước khi nhận ngắt. Không nên dùng kết quả `cancel(true)` để quyết định tự động thanh toán lại.

Đối với `CompletableFuture`, `cancel(boolean mayInterruptIfRunning)` chủ yếu hoàn tất future theo hướng hủy/ngoại lệ. **Tham số `mayInterruptIfRunning` không dùng để điều khiển việc ngắt tác vụ bên dưới** theo hợp đồng của `CompletableFuture`. Muốn hủy công việc thực sự, cần giữ quyền sở hữu tác vụ, truyền tín hiệu hủy hoặc dùng API của executor/operation tương ứng.

### Hết thời gian chờ không đồng nghĩa hủy công việc

~~~java
try {
    Integer result = future.get(2, TimeUnit.SECONDS);
    use(result);
} catch (TimeoutException timeout) {
    future.cancel(true); // Yêu cầu hủy tường minh, vẫn không bảo đảm dừng.
}
~~~

`get(timeout, unit)` chỉ giới hạn **thời gian của lời chờ**. Khi quá hạn, công việc vẫn có thể đang chạy. Tương tự, `CompletableFuture.orTimeout(...)` và `completeOnTimeout(...)` thay đổi cách future hoàn tất theo thời hạn; không tự bảo đảm dừng phép tính hay I/O bên dưới.

Nên phân biệt **timeout của từng phụ thuộc** với **deadline của toàn yêu cầu**. Nếu tổng ngân sách còn 800 ms thì lời gọi tiếp theo không nên dùng timeout 5 giây chỉ vì đó là cấu hình mặc định. Khi truyền deadline sang dịch vụ khác, cần thống nhất cách biểu diễn và tính đến sai lệch đồng hồ giữa máy; khi đo thời gian còn lại trong một tiến trình, đồng hồ đo khoảng tương đối là lựa chọn thích hợp.

## 5. Dọn dẹp tài nguyên và giữ bất biến dữ liệu

Khi hủy hoặc shutdown, việc quan trọng không chỉ là thoát vòng lặp. Tác vụ còn cần giải phóng **những tài nguyên mà nó sở hữu**:

- Đóng tệp, stream, socket, phiên database và tài nguyên tạm.
- Hoàn tác giao dịch chưa commit nếu hệ thống hoặc tầng giao dịch cung cấp cơ chế rollback.
- Dừng timer hoặc tác vụ con thuộc cùng vòng đời.
- Ghi trạng thái cuối và thông tin chẩn đoán theo hợp đồng, không lộ dữ liệu nhạy cảm.
- Hoàn trả hoặc ghi nhận công việc chưa xong để có thể tiếp tục xử lý sau.

Với tài nguyên triển khai `AutoCloseable`, dùng `try-with-resources`:

~~~java
static void importFile(java.nio.file.Path path)
        throws java.io.IOException, InterruptedException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        String line;
        while ((line = reader.readLine()) != null) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("Import cancelled");
            }
            validateAndWrite(line); // Chỉ minh họa: phải định nghĩa ranh giới commit.
        }
    } // Reader được đóng cả khi xử lý xong, có lỗi hoặc bị ngắt.
}
~~~

`validateAndWrite` biểu thị logic do ứng dụng định nghĩa. Nó không có đảm bảo rollback chỉ nhờ `try-with-resources`: nếu đã ghi một số dòng vào database rồi bị hủy, các dòng đó vẫn có thể tồn tại.

**Phân biệt tài nguyên cục bộ và tác dụng phụ bên ngoài:** đóng một file tạm khác với hoàn tác email đã gửi, tiền đã trừ hoặc sự kiện đã được hệ thống ngoài xác nhận. Khi không thể rollback, có thể cần **bước bù trừ** (compensation), ví dụ tạo yêu cầu hoàn tiền theo quy trình nghiệp vụ. Bước bù trừ cũng có thể thất bại và cần truy vết, retry hợp lệ hoặc xử lý thủ công.

### Ranh giới commit quyết định khả năng hủy

Giả sử một đơn hàng có ba bước:

~~~text
1. Kiểm tra điều kiện -> 2. Ghi trạng thái -> 3. Gọi cổng thanh toán
                                          ^
                            Có thể đã xuất hiện tác dụng phụ
~~~

Nếu yêu cầu hủy đến giữa bước 2 và 3, không nên tự đặt `CANCELLED` mà bỏ qua việc đồng bộ trạng thái. Nếu yêu cầu đến sau khi cổng thanh toán nhận lệnh, **không thể suy ra giao dịch chưa diễn ra** chỉ vì lời gọi HTTP của ứng dụng bị timeout. Cần đối soát trạng thái bằng mã giao dịch/idempotency key, và thiết kế chuyển trạng thái theo kết quả thực tế.

Đối với một quy trình dài, phân đoạn công việc thành các bước **có checkpoint rõ ràng**, lưu tiến độ bền vững ở điểm thích hợp và quyết định nhất quán: hoàn tất, tiếp tục, bù trừ hay chờ đối soát. Không nên dùng thread interrupt như một dạng transaction rollback.

## 6. Kết thúc có kiểm soát của dịch vụ

Khi một ứng dụng cần dừng, mục tiêu là kết thúc đúng theo **thứ tự sở hữu và phụ thuộc** của các thành phần. Ví dụ thông thường:

~~~mermaid
flowchart TD
    A["Nhận tín hiệu dừng"] --> B["Báo không sẵn sàng nhận việc mới"]
    B --> C["Dừng tiếp nhận request/job mới"]
    C --> D["Đợi request/job đang chạy trong thời hạn cho phép"]
    D --> E{"Đã xử lý hết?"}
    E -->|Có| F["Đóng tài nguyên theo thứ tự phụ thuộc"]
    E -->|Chưa| G["Yêu cầu hủy, bàn giao/retry việc chưa xong"]
    G --> F
    F --> H["Ghi nhận trạng thái và kết thúc tiến trình"]
~~~

Thứ tự cụ thể tùy ứng dụng. Ví dụ: **không đóng database trước khi worker đang chạy xong phần cần dùng database**. Tương tự, nếu request handler còn cần gọi service nội bộ, không nên đóng service đó ngay khi nhận tín hiệu.

Một quy trình thường gồm:

1. **Ngừng tiếp nhận:** giảm khả năng có thêm việc mới; cập nhật readiness để hệ thống điều phối ngừng gửi lưu lượng, đồng thời xử lý độ trễ lan truyền và các request đã được chấp nhận.
2. **Drain:** cho các tác vụ đang chạy thời gian hoàn thành tự nhiên; với công việc dài, chọn checkpoint để dừng hoặc bàn giao.
3. **Escalate:** khi quá ngân sách, phát tín hiệu hủy hợp tác và ghi lại việc chưa xong. Một số công việc không thể dừng an toàn giữa chừng, cần chính sách xử lý riêng.
4. **Đóng tài nguyên:** đóng executor, kết nối, consumer, scheduler, tệp và telemetry theo đúng quan hệ phụ thuộc.
5. **Quan sát kết quả:** ghi log/metric về số tác vụ đã hoàn thành, còn dở, bị hủy, thời gian drain, nguyên nhân dừng và tình trạng bàn giao.

**Readiness** và **liveness** không cùng nghĩa. Readiness cho biết tiến trình có nên nhận thêm lưu lượng hay không; trong giai đoạn drain tiến trình có thể vẫn còn sống và đang xử lý đúng công việc đã nhận. Không nên cấu hình probe khiến tiến trình bị giết ngay khi cần thời gian drain.

### 6.1. Kết thúc `ExecutorService` có thời hạn

Ví dụ một hàm dừng pool trong Java:

~~~java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

static void stopExecutor(ExecutorService executor) {
    executor.shutdown(); // Không nhận task mới; cho task đã nhận tiếp tục.
    try {
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            // Tác vụ chưa bắt đầu được trả về; tác vụ đang chạy chỉ được
            // yêu cầu ngắt, không có bảo đảm đã dừng.
            List<Runnable> neverStarted = executor.shutdownNow();
            reportUnstartedTasks(neverStarted); // Ứng dụng tự định nghĩa.

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                reportStillRunning(); // Ghi nhận và kích hoạt xử lý vận hành.
            }
        }
    } catch (InterruptedException interrupted) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

`reportUnstartedTasks` và `reportStillRunning` là các hàm ứng dụng cần triển khai. Đoạn mẫu minh họa thứ tự dừng, **không phải cơ chế bàn giao công việc đã hoàn chỉnh**.

- `shutdown()` từ chối task mới và cho task đã nhận chạy tiếp.
- `awaitTermination(...)` chờ trong giới hạn; khi trả `false`, executor chưa kết thúc hoàn toàn.
- `shutdownNow()` thử ngắt task đang chạy và trả về danh sách task trong hàng đợi chưa bắt đầu; không cam kết dừng tác vụ không hợp tác.
- Nếu thread đang thực hiện shutdown bị ngắt, nên đáp ứng tín hiệu và **khôi phục cờ ngắt** sau khi gọi cơ chế dừng cần thiết.
- Những tác vụ đã submit nhưng chưa bắt đầu **không tự động được gửi lại** chỉ vì `shutdownNow()` trả danh sách `Runnable`. Bên sở hữu phải có quy trình bền vững để không làm mất công việc.

Trong ứng dụng thực, **tổng thời gian** chờ còn phải nằm trong ngân sách dừng được môi trường triển khai cấp. Thời gian drain ở ứng dụng cần đủ ngắn để còn thời gian đóng tài nguyên, gửi log và thực hiện bước dự phòng. Không nên giả định mọi shutdown hook đều sẽ được chạy, ví dụ khi tiến trình bị kill cưỡng bức, máy mất điện hoặc hết hạn grace period.

### 6.2. Tín hiệu dừng, hook và quyền sở hữu vòng đời

Trên JVM có thể đăng ký shutdown hook, hoặc dùng lifecycle callback của framework đang chạy. Hook chỉ nên điều phối việc dừng theo thứ tự và giới hạn đã định, tránh chờ vô hạn hoặc phụ thuộc vào thành phần cũng đang đóng. Môi trường hệ điều hành/container có thể giới hạn nghiêm ngặt thời gian kết thúc; sau hạn đó, tiến trình có thể bị kết thúc cưỡng bức.

Chủ sở hữu của thread pool, HTTP client, database pool hoặc scheduler phải **được xác định rõ**. Nếu mỗi tác vụ tự đóng shared executor, các tác vụ khác có thể bị từ chối ngoài dự kiến. Ngược lại, nếu không ai có trách nhiệm đóng, tiến trình có thể treo do thread còn sống hoặc kết nối bị rò rỉ.

## 7. Hủy trong hệ thống phân tán và hàng đợi

Trong hệ thống nhiều dịch vụ, hủy một HTTP request ở phía client **không tự động** hủy truy vấn database hay tác vụ đã được đẩy vào message queue. Tín hiệu hủy phải được truyền qua những thành phần có hợp đồng hỗ trợ nó.

| Tình huống | Điều dễ hiểu nhầm | Điều cần thiết kế |
| --- | --- | --- |
| Client ngắt kết nối | Backend chắc chắn đã ngừng | Server có cơ chế phát hiện ngắt và truyền tín hiệu, nhưng vẫn giữ bất biến dữ liệu |
| API trả timeout | Tác vụ nền chắc chắn thất bại | Trạng thái thực phải được kiểm tra; hạn chế retry tạo tác dụng phụ trùng |
| Message consumer bị dừng | Message đã nhận sẽ không bị mất | Chỉ acknowledge theo thời điểm xử lý bền vững; nắm rõ cơ chế redelivery |
| Tác vụ bị retry | Công việc sẽ chỉ thực hiện một lần | Thiết kế idempotency/deduplication phù hợp với side effect |
| Dừng worker giữa batch | Toàn batch được tự động rollback | Có checkpoint, ghi nhận phần đã xong và phần cần xử lý tiếp |
| Gửi tín hiệu hủy đến service phụ | Mọi service đều dừng lập tức | Có truyền deadline/cancellation, chính sách timeout và xác minh kết quả |

### 7.1. Ví dụ với consumer hàng đợi

Giả sử một worker nhận thông điệp từ broker:

~~~text
Nhận message
    |
    v
Kiểm tra trùng / idempotency
    |
    v
Xử lý nghiệp vụ và lưu tiến độ bền vững
    |
    v
Acknowledge message
~~~

Nếu worker bị hủy **trước khi xử lý xong**, việc không xác nhận thông điệp có thể giúp broker phát lại tùy ngữ nghĩa của broker và cấu hình consumer. Nếu nghiệp vụ đã commit nhưng acknowledgement chưa thành công, broker **có thể phát lại** thông điệp: do đó cần xử lý trùng (ví dụ khóa idempotency hoặc trạng thái xử lý bền vững).

Không được coi `cancel()` là bằng chứng message đã bị trả về hàng đợi; phải sử dụng API của broker và kiểm tra cơ chế ack/nack, lease hoặc visibility timeout tương ứng. Các bảo đảm như at-most-once, at-least-once và exactly-once cũng phụ thuộc phạm vi; không nên đồng nhất “exactly-once ở broker” với “mọi tác dụng phụ ngoài broker chỉ xảy ra một lần”.

### 7.2. Lệnh hủy trong giao dịch nhiều bước

Có những thao tác hủy được **trước điểm cam kết**, nhưng sau điểm đó phải dùng một hành động nghiệp vụ khác, như hoàn tiền, hủy vận chuyển hoặc tạo bản ghi điều chỉnh. Đối với thao tác thanh toán, nên thiết kế trạng thái bền vững và khả năng đối soát, tránh trả về kết quả `CANCELLED` gây hiểu nhầm rằng tiền chưa bị trừ.

Khi có yêu cầu hủy và hoàn tất cùng lúc, hãy đặt quy tắc xác định kết quả cuối tại **nguồn sự thật có kiểm soát đồng thời**, không chỉ dựa vào thứ tự log hoặc response của hai thread.

## 8. Độ tin cậy cần quan sát được khi hủy và dừng

Lỗi trong quá trình shutdown thường khó tái hiện vì chỉ xuất hiện lúc triển khai hoặc mất kết nối. Log và metric có cấu trúc giúp phân biệt nguyên nhân:

| Dấu hiệu | Ý nghĩa cần điều tra |
| --- | --- |
| `active_tasks` không giảm khi drain | Tác vụ chặn, không kiểm tra hủy, timeout quá dài hoặc deadlock |
| `cancel_requested` tăng nhưng `cancel_completed` không tăng | Tín hiệu không truyền tới nơi chạy, tác vụ không hợp tác hoặc trạng thái không được chốt |
| `shutdown_duration` chạm giới hạn | Ngân sách quá ngắn, nhiều công việc dài hoặc thứ tự đóng tài nguyên sai |
| Số message redelivery tăng sau deploy | Task bị ngắt trước ack, checkpoint thiếu hoặc retry đang trùng |
| Lỗi “executor rejected” xuất hiện khi dừng | Thành phần vẫn submit việc sau khi pool đã shutdown |
| Thiếu log kết thúc hoặc file còn khóa | Shutdown không hoàn thành, tài nguyên không được dọn hoặc tiến trình bị kết thúc cưỡng bức |

Những chỉ số này cần gắn với **loại tác vụ, nguyên nhân dừng, request/job ID và giai đoạn vòng đời** khi phù hợp. Tránh log dữ liệu nhạy cảm, token hay toàn bộ payload chỉ để điều tra.

Người bảo trì cần nhận biết rõ một trạng thái **đang hủy** khác với **đã hủy**, vì điều đó quyết định có an toàn để retry, hiển thị hoàn tất hoặc giải phóng tài nguyên hay chưa.

## 9. Kiểm thử hủy mà không dựa vào may rủi thời gian

Hủy là hành vi đồng thời nên rất dễ có kiểm thử lúc qua lúc trượt nếu chỉ dùng `Thread.sleep(...)` rồi đoán tác vụ đã bắt đầu. Thay vào đó, đồng bộ bằng `CountDownLatch`, `Future` và các giới hạn chờ rõ ràng.

### 9.1. Kiểm tra tác vụ đang chờ phản ứng với ngắt

Ví dụ JUnit 5 sau chứng minh **tác vụ thực sự thoát**, thay vì chỉ kiểm tra `Future.isCancelled()`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.concurrent.*;

class CancellationTest {
    @Test
    void cancelInterruptsBlockingWorker() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            assertTrue(started.await(5, TimeUnit.SECONDS));
            assertTrue(future.cancel(true));
            assertTrue(finished.await(5, TimeUnit.SECONDS));
            assertTrue(future.isCancelled());
            assertThrows(CancellationException.class, future::get);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Ví dụ chỉ kiểm tra thao tác chờ có khả năng bị interrupt; nó **không chứng minh** việc hủy truy vấn database hoặc hành động bên ngoài. Trong bộ test thật cần bao phủ đúng loại công việc và cơ chế hủy của thư viện đang dùng.

### 9.2. Các trường hợp nên có trong bộ kiểm thử

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hủy trước khi task bắt đầu | Task không thực hiện tác dụng phụ, trạng thái cuối nhất quán |
| Hủy khi task đang chờ interruptible operation | Task phản hồi, giải phóng tài nguyên, không nuốt `InterruptedException` |
| Hủy khi task đang xử lý bước có tác dụng phụ | Không để lại trạng thái sai; có checkpoint/compensation khi cần |
| Hủy và hoàn tất xảy ra gần như đồng thời | Chỉ một trạng thái cuối hợp lệ, không mất kết quả hoặc ghi đè |
| Hai yêu cầu hủy liên tiếp | Không tạo thao tác lặp nguy hiểm |
| Hết timeout chờ kết quả | Phân biệt timeout của caller với trạng thái thực tế của worker |
| Hủy khi phụ thuộc không phản hồi | Timeout được áp dụng; giải phóng hoặc cô lập tài nguyên theo hợp đồng |
| Shutdown khi đang nhận request mới | Dừng intake, từ chối/điều hướng công việc mới đúng lúc |
| Shutdown khi có task đã nhận, task đang chạy | Drain trong ngân sách và xử lý rõ việc chưa hoàn thành |
| Shutdown bị ngắt hoặc quá grace period | Có đường dừng dự phòng và khả năng khôi phục khi khởi động lại |
| Worker xử lý message bị ngắt trước/sau commit | Không mất message, tránh nhân đôi side effect |
| Khởi động lại sau dừng giữa batch | Tiếp tục từ checkpoint hợp lệ, không xử lý trùng không kiểm soát |

Nên đưa một số tình huống vào **integration test với database/broker thật hoặc môi trường gần thực tế**. Unit test không thể khẳng định được ngữ nghĩa của giao dịch hoặc acknowledgement nếu chúng chỉ được giả lập bằng mock.

## 10. Mối quan hệ với chất lượng mã nguồn

Trong Code Quality Fundamentals, tính dễ hiểu và dễ thay đổi liên quan trực tiếp đến khả năng hủy an toàn:

- **Trách nhiệm rõ ràng:** người đọc biết thành phần nào tạo task, gửi tín hiệu hủy, quyết định trạng thái cuối và đóng tài nguyên.
- **API thể hiện vòng đời:** phân biệt `requestCancellation()` với `awaitStopped()`; không đặt tên `stopImmediately()` nếu chỉ yêu cầu dừng.
- **Ranh giới tác dụng phụ rõ:** những bước đã commit, chưa commit, cần rollback hoặc cần bù trừ được mô tả tường minh.
- **Lỗi và trạng thái riêng biệt:** không gộp `TIMEOUT`, `CANCELLED` và `FAILED` vào một cờ boolean mơ hồ.
- **Tính quan sát được:** log và metric giúp chẩn đoán vì sao shutdown quá hạn, tác vụ bị kẹt hoặc công việc bị phát lại.
- **Thiết kế thuận tiện cho kiểm thử:** có thể chặn worker ở checkpoint bằng latch/test double, rồi xác minh hành vi khi hủy mà không phụ thuộc vào ngủ chờ.

Tăng số lượng thread, timeout hay hook không tự nâng độ tin cậy. Một giải pháp có thể đơn giản hơn nếu tác vụ có ranh giới rõ, nguyên tắc sở hữu tài nguyên nhất quán và quy trình kết thúc được mô tả bằng các trạng thái có thể kiểm tra.

## 11. Các ngộ nhận thường gặp

- **“Gọi `interrupt()` là thread đã dừng.”** Interrupt là tín hiệu; mã đang chạy và thư viện bên dưới phải hợp tác.
- **“`cancel(true)` trả `true` thì mọi side effect đã bị hủy.”** Trạng thái `Future` không thể thay thế kiểm tra thực tế tác dụng phụ.
- **“Một lần timeout là lệnh phía server chưa thực hiện.”** Timeout của bên chờ có thể xảy ra sau khi bên kia đã xử lý xong.
- **“Bắt `InterruptedException` rồi bỏ qua sẽ giúp chương trình ổn định.”** Nuốt ngắt có thể làm task không bao giờ dừng khi dịch vụ shutdown.
- **“Đóng executor là xong mọi công việc.”** Cần biết còn những task nào đã nhận, chưa bắt đầu, đang chạy hoặc chưa bền vững.
- **“`finally` luôn chạy khi tiến trình bị kill.”** Khi bị kết thúc cưỡng bức hoặc mất nguồn, không thể dựa vào cleanup trong tiến trình; phải thiết kế khôi phục.
- **“Chỉ cần retry là không mất dữ liệu.”** Retry có thể tạo tác dụng phụ trùng nếu không có idempotency và checkpoint.
- **“Shutdown chậm thì tăng grace period thật lớn.”** Cần xác định việc nào không hợp tác, độ trễ được chấp nhận và giới hạn của môi trường triển khai.

## 12. Tự kiểm tra

1. Người dùng hủy xuất báo cáo khi tác vụ đã ghi xong một phần tệp. Cần làm gì với tệp tạm, trạng thái job và tiến độ đã lưu?
2. Phân biệt `Thread.currentThread().isInterrupted()` và `Thread.interrupted()`. Khi nào nên dùng từng phương thức?
3. Vì sao `Future.isCancelled()` không đủ để khẳng định một lệnh thanh toán chưa được gửi?
4. Điều gì xảy ra khi gọi `Future.get(2, SECONDS)` và nhận `TimeoutException`? Tác vụ có tự dừng không?
5. Hãy giải thích thứ tự `shutdown()` → `awaitTermination()` → `shutdownNow()` và giới hạn của từng bước.
6. Một consumer xử lý và commit message xong nhưng chưa kịp ack thì tiến trình dừng. Khi khởi động lại, lỗi nào có thể xảy ra? Cần thiết kế gì để giảm nguy cơ?
7. Khi có hai sự kiện hoàn tất và hủy xảy ra cùng thời điểm, cần lưu trạng thái ra sao để không có hai kết quả cuối mâu thuẫn?
8. Nêu một cách kiểm thử một tác vụ phản hồi với interrupt mà không chỉ sử dụng `Thread.sleep` để chờ may rủi.
9. Tại sao cần giảm readiness trước khi dừng toàn bộ worker nhưng vẫn phải duy trì liveness đủ lâu cho drain?
10. Với một tác vụ gồm bước ghi database và gọi API ngoài, hãy chỉ ra checkpoint an toàn và hành động bù trừ có thể cần thiết.

## Ghi nhớ

**Hủy thao tác là một giao thức hợp tác có trạng thái, không phải lệnh xóa bỏ mọi điều đã diễn ra.** **Kết thúc có kiểm soát** là khả năng ngừng nhận việc, giải quyết hoặc bàn giao phần đang làm, đóng tài nguyên và công bố kết quả trong giới hạn thời gian. Muốn mã đáng tin cậy, cần thiết kế quyền sở hữu công việc, tín hiệu hủy, ranh giới commit, cơ chế retry/idempotency và kiểm thử các tình huống tranh chấp ngay từ đầu.
