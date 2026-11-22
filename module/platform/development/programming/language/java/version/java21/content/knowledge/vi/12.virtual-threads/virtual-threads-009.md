# Vì sao không dùng thread pool để tái sử dụng virtual thread

Virtual thread được thiết kế theo mô hình **một thread cho mỗi task** (thread-per-task). Trong Java 21, chương trình thường tạo một virtual thread mới cho mỗi tác vụ bằng `Executors.newVirtualThreadPerTaskExecutor()`. Khi tác vụ kết thúc, virtual thread kết thúc theo; runtime tự quản lý việc lập lịch và tái sử dụng các platform thread làm carrier để thực thi virtual thread.

Thread pool truyền thống được tạo ra chủ yếu để tái sử dụng platform thread vì việc tạo và quản lý một OS thread có chi phí đáng kể. Virtual thread nhẹ hơn nhiều, nên pooling chúng thường không mang lại lợi ích tương ứng. Việc giới hạn số virtual thread trong một pool còn làm mất khả năng phục vụ đồng thời số lượng lớn tác vụ đang chờ I/O. Nếu cần giới hạn tải hoặc bảo vệ tài nguyên dùng chung, hãy giới hạn chính tài nguyên hoặc lượng công việc đang được tiếp nhận, thay vì tái sử dụng virtual thread.

## 1. Thread pool giải quyết vấn đề gì?

Với platform thread, việc tạo một thread cho mỗi tác vụ có thể gây áp lực lên bộ nhớ, tài nguyên hệ điều hành và chi phí lập lịch khi số lượng tác vụ đồng thời tăng cao. Thread pool giải quyết vấn đề này bằng cách duy trì một số lượng worker thread cố định hoặc có giới hạn. Nhiều task lần lượt được thực thi trên các worker đó.

Ví dụ một fixed thread pool:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

class Main {
    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newFixedThreadPool(8)) {
            for (int i = 0; i < 100; i++) {
                int taskId = i;
                executor.submit(() ->
                    System.out.println("Task " + taskId
                            + " on " + Thread.currentThread())
                );
            }
        }
    }
}
```

Pool có tối đa tám worker thread chạy task tại một thời điểm; các task còn lại chờ trong hàng đợi. Cách làm này có thể phù hợp khi muốn giới hạn số platform thread, đặc biệt với công việc CPU-bound hoặc với một hệ thống cần giới hạn song song rõ ràng.

Virtual thread thay đổi bài toán ở chỗ runtime có thể quản lý rất nhiều thread nhẹ trên một số lượng nhỏ hơn các platform thread. Vì vậy, không cần duy trì một nhóm virtual thread sống lâu chỉ để tiết kiệm chi phí tạo thread.

## 2. Virtual thread được thiết kế theo mô hình một task cho mỗi thread

Virtual thread là đối tượng `Thread` được runtime Java lập lịch. Nó không tương ứng một-một với một OS thread trong suốt vòng đời. Khi virtual thread thực hiện thao tác blocking được runtime hỗ trợ, nó có thể được unmount khỏi carrier platform thread; carrier sau đó có thể chạy virtual thread khác.

Mô hình này cho phép mã nguồn giữ phong cách lập trình đồng bộ, dễ đọc theo từng tác vụ, trong khi runtime quản lý việc chia sẻ platform thread.

API được khuyến nghị trong Java 21:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

class Main {
    static String fetch(String resource) throws InterruptedException {
        Thread.sleep(100);
        return "Loaded " + resource;
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            var first = executor.submit(() -> fetch("profile"));
            var second = executor.submit(() -> fetch("orders"));

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }
}
```

Mỗi lần gọi `submit` tạo một virtual thread mới để thực hiện task tương ứng. `ExecutorService` ở đây quản lý việc nhận task và vòng đời thực thi; nó không phải pool tái sử dụng virtual thread.

Khi đóng executor bằng try-with-resources, executor ngừng nhận task mới và chờ các task đã được submit hoàn thành. Cách quản lý vòng đời này giúp nhóm tác vụ có điểm bắt đầu và kết thúc rõ ràng.

## 3. Vì sao không nên pool virtual thread?

### 3.1. Virtual thread có chi phí tạo thấp

Thread pool truyền thống giảm số lần tạo platform thread vì platform thread có chi phí tương đối cao. Virtual thread được thiết kế nhẹ để có thể tạo theo từng task. Việc tạo một virtual thread mới thường là lựa chọn đơn giản và phù hợp hơn so với giữ một virtual thread sống lâu để dùng lại.

Nếu tạo pool chỉ gồm một số virtual thread cố định, số task có thể chạy đồng thời bị giới hạn bởi số worker đó. Khi tất cả worker đang chờ I/O, những task khác phải đợi trong hàng đợi dù runtime có thể chạy thêm nhiều virtual thread trên các carrier.

### 3.2. Pool làm mất mô hình một task cho mỗi thread

Một trong các lợi ích của virtual thread là mỗi task có thread riêng. Stack, trạng thái thực thi, xử lý hủy và thông tin gắn với thread có vòng đời gắn với task.

Khi tái sử dụng một virtual thread cho nhiều task, chương trình quay lại mô hình worker sống lâu. Các task không còn có quan hệ một-một với virtual thread, và có thể phải quản lý việc dọn trạng thái giữa các lần chạy.

Một virtual thread đã kết thúc cũng không thể được khởi động lại. Vì vậy, “pool virtual thread” thực tế là giữ một số virtual thread worker sống lâu để mỗi worker chạy nhiều task nối tiếp; nó không phải đưa một virtual thread đã kết thúc trở lại trạng thái sẵn sàng.

### 3.3. Pool tạo thêm hàng đợi và giới hạn không cần thiết

Một pool có số worker cố định sẽ buộc task chờ khi tất cả worker đang bận. Đây chính là giới hạn mà virtual thread được thiết kế để giảm bớt đối với workload có nhiều thao tác chờ.

Nếu mục tiêu là bảo vệ database chỉ cho phép 20 truy vấn đồng thời, giới hạn 20 virtual thread cho toàn bộ ứng dụng là quá rộng: những task không truy cập database cũng bị giới hạn theo. Hãy tạo virtual thread cho mỗi task và giới hạn riêng đoạn truy cập database bằng semaphore hoặc cơ chế kiểm soát tài nguyên phù hợp.

### 3.4. Runtime đã tái sử dụng carrier platform thread

Virtual thread chạy trên carrier platform thread do scheduler quản lý. Runtime chịu trách nhiệm lập lịch virtual thread lên các carrier và có thể dùng lại carrier cho nhiều virtual thread theo thời gian.

Do đó, ứng dụng không cần tạo một pool virtual thread để đạt mục tiêu tái sử dụng platform thread. Phần tái sử dụng tài nguyên thực thi cấp thấp đã được runtime đảm nhiệm.

## 4. Không nhầm virtual-thread-per-task executor với thread pool

Tên `ExecutorService` đôi khi khiến người học nghĩ rằng mọi executor đều là thread pool. Thực tế, `ExecutorService` là abstraction để gửi task và quản lý vòng đời thực thi; implementation có thể dùng các mô hình khác nhau.

| Executor | Cách thực thi | Có tái sử dụng virtual thread không? |
|---|---|---|
| `Executors.newFixedThreadPool(n)` | Dùng một số worker platform thread cố định theo mặc định | Không áp dụng; mặc định worker là platform thread |
| `Executors.newVirtualThreadPerTaskExecutor()` | Tạo một virtual thread mới cho mỗi task | Không |
| `Executors.newFixedThreadPool(n, Thread.ofVirtual().factory())` | Dùng một số virtual thread worker sống lâu để chạy nhiều task | Có; đây thường không phải mô hình được khuyến nghị |

Ví dụ dưới đây tạo fixed pool với virtual thread factory:

```java
var executor = Executors.newFixedThreadPool(
        8,
        Thread.ofVirtual().factory()
);
```

Cách cấu hình này có thể tạo các virtual thread worker chạy lâu dài và lần lượt thực thi nhiều task. Nó tái tạo cách dùng worker pool trên virtual thread, làm giới hạn concurrency theo số worker và không tận dụng đầy đủ mô hình thread-per-task.

Với Java 21, nếu muốn mỗi task có một virtual thread riêng, hãy dùng:

```java
var executor = Executors.newVirtualThreadPerTaskExecutor();
```

## 5. Khi cần giới hạn tài nguyên, hãy giới hạn tài nguyên đó

Không pool virtual thread không có nghĩa là phải cho phép mọi tác vụ gọi tài nguyên bên ngoài cùng lúc. Virtual thread nhẹ nhưng database connection, file descriptor, API quota, bộ nhớ và năng lực xử lý của dịch vụ bên ngoài vẫn có giới hạn.

Có thể dùng `Semaphore` để giới hạn số task truy cập một tài nguyên cùng lúc:

```java
import java.util.concurrent.Semaphore;

class DatabaseService {
    private final Semaphore permits = new Semaphore(20);

    String loadRecord(String id) throws InterruptedException {
        permits.acquire();
        try {
            // Giả sử đây là thao tác I/O tới database.
            return queryDatabase(id);
        } finally {
            permits.release();
        }
    }

    private String queryDatabase(String id) {
        return "record-" + id;
    }
}
```

Khi 20 permit đã được sử dụng, virtual thread tiếp theo chờ tại `acquire()`. Khi một task hoàn thành và gọi `release()`, một task đang chờ có thể tiếp tục.

Có thể kết hợp với virtual-thread-per-task executor:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (String id : recordIds) {
        executor.submit(() -> databaseService.loadRecord(id));
    }
}
```

Trong ví dụ này, mỗi task có virtual thread riêng, còn semaphore giới hạn số thao tác database đồng thời ở mức 20. Phải bảo đảm `release()` luôn được gọi sau khi lấy permit thành công; đặt nó trong `finally` giúp xử lý cả trường hợp thao tác ném exception.

Semaphore chỉ là một cách giới hạn concurrency. Tùy yêu cầu, ứng dụng còn có thể dùng connection pool cho database connection, rate limiter cho giới hạn request theo thời gian, bounded queue hoặc backpressure ở tầng tiếp nhận công việc.

## 6. Virtual thread nhẹ nhưng không miễn phí

Không pool virtual thread không có nghĩa có thể tạo vô hạn task mà không cần quan tâm tài nguyên. Mỗi virtual thread vẫn tiêu thụ bộ nhớ và các task có thể giữ nhiều object, buffer, request body hoặc tài nguyên I/O trong lúc chờ.

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được gửi vào. Nếu ứng dụng nhận một lượng task khổng lồ không giới hạn, số virtual thread đang chờ cũng có thể tăng cao và gây áp lực bộ nhớ hoặc hệ thống phụ thuộc.

Cần thiết kế admission control và backpressure khi đầu vào có thể tăng đột biến:

- Giới hạn số request đang được chấp nhận hoặc xử lý.
- Dùng bounded queue khi nghiệp vụ cho phép task chờ trong hàng đợi có dung lượng giới hạn.
- Từ chối hoặc trì hoãn request khi hệ thống quá tải.
- Giới hạn số kết nối hoặc thao tác đồng thời tới từng dịch vụ bên ngoài.
- Theo dõi số virtual thread đang tồn tại, độ trễ, bộ nhớ và thời gian chờ tài nguyên.

Điểm cần tách biệt là giới hạn **số task được tiếp nhận** và giới hạn **số thao tác tới một tài nguyên**. Không nên dùng một pool virtual thread để vô tình áp đặt cùng một giới hạn lên mọi loại công việc.

## 7. Virtual thread phù hợp với workload nào?

Virtual thread đặc biệt hữu ích cho ứng dụng có nhiều task đồng thời và phần lớn thời gian của mỗi task dành cho thao tác blocking như chờ HTTP response, database, socket hoặc file I/O được runtime hỗ trợ.

Ví dụ, một server có thể xử lý nhiều request đồng thời. Mỗi request chạy trong một virtual thread; khi request chờ dịch vụ bên ngoài, virtual thread có thể nhường carrier để runtime thực thi task khác.

Virtual thread không làm một phép tính CPU-bound chạy nhanh hơn. Nếu hàng nghìn task cùng thực hiện phép tính nặng, chúng vẫn cạnh tranh số lõi CPU hữu hạn. Trong trường hợp này, giới hạn mức song song bằng executor có số worker phù hợp hoặc dùng cơ chế xử lý song song dành cho CPU-bound workload.

| Đặc điểm workload | Hướng lựa chọn |
|---|---|
| Nhiều task chờ I/O, cần concurrency cao | Virtual thread-per-task |
| Task chủ yếu tính toán CPU-bound | Bounded platform-thread executor hoặc cơ chế parallelism phù hợp |
| Cần giới hạn số truy vấn database đồng thời | Virtual thread-per-task kết hợp semaphore/connection pool |
| Cần giới hạn request theo quota mỗi giây | Rate limiter hoặc admission control |
| Cần giữ hàng đợi có giới hạn và kiểm soát quá tải | Bounded queue/backpressure |

## 8. ThreadLocal và trạng thái giữa các task

Virtual thread có hỗ trợ `ThreadLocal`, nhưng mô hình một task cho mỗi virtual thread giúp tránh việc một thread worker được tái sử dụng cho task khác và vô tình mang theo trạng thái thread-local của task trước.

Khi dùng virtual thread, không nên dựa vào `ThreadLocal` để cache một tài nguyên đắt đỏ cho nhiều task, vì mỗi task có thể có virtual thread riêng và số lượng virtual thread có thể rất lớn. Cách đó có thể làm tăng số bản sao tài nguyên hoặc lượng bộ nhớ giữ lại.

Hãy quản lý tài nguyên theo đúng vòng đời của nó:

- Dùng try-with-resources cho tài nguyên có thể đóng theo task.
- Dùng connection pool cho kết nối database nếu cần tái sử dụng connection.
- Truyền context tường minh hoặc dùng cơ chế context phù hợp thay vì dựa vào worker thread được tái sử dụng.
- Tránh lưu object lớn trong thread-local nếu không cần thiết.

Pooling virtual thread cũng làm phức tạp việc dọn `ThreadLocal` giữa các task, vì trạng thái gắn với thread có thể tồn tại qua nhiều lần thực thi task trên cùng worker.

## 9. Vòng đời task và xử lý hủy

Với thread-per-task, vòng đời virtual thread gắn với một tác vụ cụ thể. Khi task kết thúc, virtual thread kết thúc; không có yêu cầu đưa nó trở lại pool để chờ task tiếp theo.

Dùng `ExecutorService` theo phạm vi rõ ràng để quản lý task:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var result = executor.submit(() -> performOperation());

    // Có thể lấy kết quả, xử lý lỗi hoặc hủy task qua Future.
    System.out.println(result.get());
}
```

Nếu cần hủy task, có thể dùng `Future.cancel(true)` và bảo đảm code tác vụ phản hồi interruption đúng cách. Virtual thread vẫn tuân theo cơ chế interrupt của Java; việc dùng virtual thread không làm cho thao tác I/O hoặc code tùy ý tự động có thể hủy an toàn.

Đừng giữ một virtual thread trong pool chỉ để tái sử dụng sau khi task đã kết thúc. Nếu có nhiều task liên quan cần chia sẻ trạng thái, hãy quản lý trạng thái ở object hoặc component có vòng đời phù hợp, thay vì gắn nó vào thread worker.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| Virtual thread cần pool giống platform thread | Virtual thread có chi phí tạo thấp và được thiết kế theo thread-per-task |
| `newVirtualThreadPerTaskExecutor()` là một virtual thread pool | Executor này tạo virtual thread mới cho mỗi task |
| Không pool nghĩa là không cần giới hạn concurrency | Vẫn cần giới hạn tài nguyên, admission control và backpressure |
| Virtual thread làm CPU-bound task nhanh hơn | Nó chủ yếu cải thiện khả năng mở rộng với workload chờ I/O |
| Virtual thread là OS thread nhẹ hơn | Virtual thread được runtime lập lịch trên carrier platform thread |
| Có thể tạo vô hạn virtual thread mà không có giới hạn | Thread nhẹ nhưng vẫn tiêu thụ bộ nhớ và tài nguyên của task |
| ThreadLocal luôn là nơi tốt để cache connection | Nên pool connection theo tài nguyên, không pool virtual thread |

## 11. Quy tắc lựa chọn trong Java 21

Khi xây dựng ứng dụng Java 21, có thể áp dụng các nguyên tắc sau:

1. Tạo một virtual thread cho mỗi task bằng `Executors.newVirtualThreadPerTaskExecutor()`.
2. Không dùng fixed pool để tái sử dụng virtual thread worker.
3. Để runtime lập lịch virtual thread lên các carrier platform thread.
4. Dùng semaphore, connection pool, rate limiter hoặc backpressure để bảo vệ tài nguyên có giới hạn.
5. Kiểm soát số task được tiếp nhận nếu đầu vào có thể tăng không giới hạn.
6. Dùng bounded parallelism cho workload CPU-bound.
7. Quản lý trạng thái và tài nguyên theo vòng đời task, tránh dùng ThreadLocal để cache tài nguyên dùng chung.
8. Quản lý vòng đời executor và xử lý interruption/hủy task đúng cách.

Virtual thread phát huy lợi ích khi được sử dụng như thread-per-task. Thread pool vốn giải quyết chi phí và giới hạn của platform thread; tái sử dụng virtual thread làm giảm concurrency và đưa mô hình worker sống lâu trở lại. Hãy để runtime tái sử dụng carrier thread, còn ứng dụng tạo virtual thread theo từng task và giới hạn đúng tài nguyên cần bảo vệ.

## Tài liệu tham khảo

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Oracle Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
