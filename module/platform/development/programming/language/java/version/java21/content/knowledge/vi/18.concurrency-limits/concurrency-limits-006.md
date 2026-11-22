# Giới hạn hàng đợi, bộ nhớ và số request đang chờ

Một ứng dụng Java có thể tạo rất nhiều thread hoặc virtual thread, nhưng điều đó không làm cho CPU, heap, connection pool, dịch vụ từ xa hay băng thông có khả năng xử lý vô hạn. Khi tốc độ request đến cao hơn tốc độ xử lý, công việc tích tụ trong hàng đợi, giữ lại request body và các object liên quan, làm tăng độ trễ và cuối cùng có thể gây cạn bộ nhớ.

Giới hạn đồng thời cần được thiết kế ở nhiều lớp: số request được chấp nhận, số tác vụ đang chạy, kích thước hàng đợi, dung lượng dữ liệu mỗi request và số lần gọi tới tài nguyên hữu hạn. Bài này trình bày cách đặt các giới hạn đó trong ứng dụng Java 21, gồm cả ứng dụng dùng platform thread và virtual thread.

## 1. Vì sao cần giới hạn concurrency?

Giả sử một dịch vụ nhận 500 request mỗi giây nhưng chỉ xử lý hoàn tất được 300 request mỗi giây trong thời gian tải cao. Nếu vẫn nhận tất cả request mà không giới hạn, số request đang chờ sẽ tăng theo thời gian. Mỗi request có thể giữ lại:

- Request object, header, context xác thực và thông tin tracing.
- Body đã đọc vào heap hoặc buffer trực tiếp.
- Task, lambda, `Future` và dữ liệu được capture trong closure.
- Bộ nhớ tạm, response buffer và tài nguyên đã cấp phát trước khi xử lý.
- Một slot trong connection pool hoặc một thread đang chờ tài nguyên khác.

Hàng đợi không giới hạn có thể biến một đợt tăng tải tạm thời thành tình trạng quá tải kéo dài. Khi heap tăng, garbage collection chạy thường xuyên hơn; latency tăng khiến request tồn tại lâu hơn; request mới lại tiếp tục được nhận. Đây là vòng lặp làm hệ thống suy giảm nhanh.

Mục tiêu của giới hạn concurrency là giữ lượng công việc đang tồn tại trong một phạm vi mà hệ thống có thể xử lý, đồng thời phản hồi sớm khi không còn khả năng nhận thêm việc.

## 2. Phân biệt các loại giới hạn

Không nên dùng một con số duy nhất để đại diện cho mọi giới hạn. Mỗi giới hạn bảo vệ một loại tài nguyên khác nhau:

| Giới hạn | Đang giới hạn điều gì? | Cơ chế thường dùng |
|---|---|---|
| Số request đang được chấp nhận (in-flight) | Tổng request đã nhận nhưng chưa hoàn tất | Semaphore, admission control tại ingress/server |
| Số task đang chạy | Số worker xử lý cùng lúc | `ThreadPoolExecutor` với core/max pool size |
| Số task đang chờ | Công việc đã nhận nhưng chưa có worker xử lý | Bounded `BlockingQueue` |
| Số thao tác tới dependency | Tải đồng thời lên database, API hoặc dịch vụ khác | Semaphore, connection pool có giới hạn |
| Tốc độ request | Số request trong một đơn vị thời gian | Rate limiter hoặc quota |
| Kích thước dữ liệu | Bộ nhớ tối đa cho body, file, message hoặc response | Giới hạn payload, streaming, bounded buffer |
| Thời gian chờ | Thời gian request được phép nằm trong queue hoặc chờ dependency | Deadline, timeout và cancellation |

Giới hạn số request đồng thời khác giới hạn tốc độ request. Rate limit có thể cho phép 100 request mỗi giây nhưng không ngăn 100 request đó cùng lúc bị treo trong một dịch vụ chậm. Ngược lại, semaphore giới hạn 20 request đang xử lý nhưng có thể vẫn cho phép tổng cộng hàng nghìn request đến trong một phút nếu mỗi request hoàn tất nhanh.

Một hệ thống thường cần kết hợp cả hai: rate limit để kiểm soát lưu lượng đến và concurrency limit để bảo vệ tài nguyên đang được sử dụng.

## 3. Dùng bounded queue thay cho hàng đợi không giới hạn

`ThreadPoolExecutor` cho phép cấu hình số worker và một `BlockingQueue` chứa task đang chờ. Khi dùng queue có giới hạn, hệ thống có một điểm rõ ràng để từ chối công việc mới khi đã đạt dung lượng.

Ví dụ tạo pool có tối đa 8 worker và hàng đợi tối đa 200 task:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4,
        8,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(200),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Các tham số chính:

- `corePoolSize = 4`: số worker cốt lõi.
- `maximumPoolSize = 8`: số worker tối đa khi queue đầy và cần mở rộng pool.
- `keepAliveTime = 30 seconds`: thời gian worker vượt mức core có thể chờ task mới trước khi được thu hồi.
- `ArrayBlockingQueue<>(200)`: tối đa 200 task chờ.
- `AbortPolicy`: từ chối task mới bằng `RejectedExecutionException` khi executor không thể nhận thêm.

Với `ThreadPoolExecutor`, khi task được submit, executor thường tạo worker đến mức core trước. Sau đó, nó ưu tiên đưa task vào queue. Chỉ khi queue đầy mới tạo thêm worker cho tới `maximumPoolSize`. Nếu cả queue và pool đều đạt giới hạn, rejection policy được áp dụng.

Một số queue thường dùng:

- `ArrayBlockingQueue<>(capacity)`: queue bounded với dung lượng cố định; phù hợp khi muốn capacity rõ ràng.
- `LinkedBlockingQueue<>(capacity)`: queue linked có giới hạn nếu truyền capacity; constructor không truyền capacity dùng giới hạn rất lớn (`Integer.MAX_VALUE`) và thực tế thường được xem là unbounded.
- `SynchronousQueue`: không lưu phần tử; mỗi lần handoff cần có consumer nhận trực tiếp. Nó phù hợp với một số mô hình direct handoff, nhưng không tạo hàng đợi chờ.

Ở tầng `BlockingQueue`, `offer()` trả `false` nếu không thể thêm ngay, `put()` chờ cho đến khi có chỗ và `add()` ném exception nếu không thêm được. Chọn thao tác chờ chỉ khi producer được giới hạn và có timeout/cancellation; nếu nhiều request thread cùng `put()` vô thời hạn, hàng đợi đã bị chuyển thành một tập thread đang chờ và vẫn giữ bộ nhớ.

### Xử lý khi queue đầy

Với `AbortPolicy`, caller có thể chuyển việc từ chối thành phản hồi quá tải ở tầng HTTP hoặc messaging:

```java
try {
    executor.execute(() -> processRequest(request));
} catch (java.util.concurrent.RejectedExecutionException e) {
    // Ví dụ ở tầng HTTP: trả 503 Service Unavailable.
    rejectAsOverloaded(request);
}
```

Không bắt `RejectedExecutionException` rồi âm thầm bỏ qua. Caller cần biết task chưa được nhận để phản hồi, ghi nhận hoặc thử lại theo chính sách có giới hạn.

### Các rejection policy thường gặp

| Policy | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Muốn caller chủ động từ chối hoặc xử lý quá tải |
| `CallerRunsPolicy` | Chạy task trên thread gọi `execute`, nếu executor chưa shutdown | Tạo backpressure cho producer đơn giản; cần bảo đảm thread gọi có thể thực thi task |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Chỉ phù hợp khi bỏ task là hành vi được nghiệp vụ cho phép và có cơ chế quan sát riêng |
| `DiscardOldestPolicy` | Bỏ task đầu queue rồi thử submit task mới | Rất thận trọng; có thể loại bỏ công việc cũ đang chờ và gây mất thứ tự/nghiệp vụ |

`CallerRunsPolicy` có thể làm chậm producer vì chính thread submit phải thực hiện task. Đây là một dạng backpressure, nhưng không phù hợp nếu thread gọi là event loop, request dispatcher hoặc thread cần phản hồi nhanh. Với hệ thống HTTP, thường dễ kiểm soát hơn khi dùng `AbortPolicy` rồi trả mã quá tải rõ ràng.

## 4. Cẩn thận với các factory executor có queue không giới hạn

Một số factory tiện lợi của `Executors` có hành vi cần được hiểu trước khi dùng dưới tải không kiểm soát:

| Factory | Đặc điểm | Rủi ro khi tải tăng |
|---|---|---|
| `newFixedThreadPool(n)` | Số worker cố định, dùng shared unbounded queue | Task chờ có thể tích tụ và giữ bộ nhớ không giới hạn |
| `newSingleThreadExecutor()` | Một worker tuần tự, queue không giới hạn | Một task chậm làm toàn bộ task sau tích tụ |
| `newCachedThreadPool()` | Có thể tạo thêm platform thread khi không có worker rảnh, dùng direct handoff | Có thể tăng số platform thread rất lớn khi tải tăng |
| `newVirtualThreadPerTaskExecutor()` | Tạo một virtual thread cho mỗi task | Chi phí thread thấp hơn nhưng số task và dữ liệu đang giữ vẫn có thể tăng không giới hạn |

`newFixedThreadPool` không tự tạo backpressure chỉ vì số worker đã cố định; queue mặc định của nó không giới hạn dung lượng. Nếu cần giới hạn queue, hãy cấu hình `ThreadPoolExecutor` trực tiếp hoặc dùng một cơ chế admission control tương đương.

`newVirtualThreadPerTaskExecutor()` cũng không phải bộ giới hạn request. Virtual thread giúp giảm chi phí chờ, nhưng mỗi task vẫn giữ request, context, buffer và có thể giữ tài nguyên bên ngoài. Giới hạn số request được nhận và số thao tác tới dependency vẫn cần thiết.

## 5. Giới hạn số request đang xử lý bằng Semaphore

`Semaphore` có thể giới hạn số tác vụ cùng lúc đi vào một đoạn xử lý. Ví dụ, chỉ cho phép tối đa 40 request cùng thực hiện một công việc tốn nhiều tài nguyên:

```java
import java.util.concurrent.Semaphore;

final class RequestAdmission {
    private final Semaphore permits = new Semaphore(40);

    boolean tryProcess(Request request) {
        if (!permits.tryAcquire()) {
            return false; // Không còn slot, caller có thể trả 503.
        }

        try {
            process(request);
            return true;
        } finally {
            permits.release();
        }
    }

    private void process(Request request) {
        // Xử lý request.
    }
}
```

`tryAcquire()` không chờ permit. Khi không còn slot, caller có thể từ chối ngay thay vì tạo thêm một hàng đợi thread đang chờ semaphore. `release()` phải nằm trong `finally` để không làm mất permit nếu xử lý ném exception.

Nếu muốn chờ một khoảng thời gian ngắn, có thể dùng `tryAcquire(timeout, unit)`. Tuy nhiên, các caller đang chờ permit cũng tiêu tốn thread, request context và bộ nhớ. Chỉ dùng kiểu chờ này khi tầng trước đã có giới hạn số caller và timeout nằm trong deadline tổng của request.

### Giới hạn riêng cho từng dependency

Một request có thể gọi nhiều dịch vụ. Không nên dùng chung một semaphore cho tất cả nếu mỗi dependency có dung lượng khác nhau:

```java
private final Semaphore databaseSlots = new Semaphore(30);
private final Semaphore paymentApiSlots = new Semaphore(10);
private final Semaphore searchApiSlots = new Semaphore(50);
```

Mỗi semaphore bảo vệ một tài nguyên riêng. Khi gọi dependency, lấy permit trước khi bắt đầu thao tác và nhả permit trong `finally` sau khi thao tác kết thúc. Nếu permit không có sẵn, từ chối, trì hoãn có giới hạn hoặc dùng fallback theo hợp đồng nghiệp vụ.

Không giữ permit lâu hơn thời gian thực sự sử dụng tài nguyên. Ví dụ, nếu semaphore chỉ nhằm giới hạn database query, hãy nhả permit ngay sau khi query và đọc dữ liệu xong; không giữ nó trong lúc thực hiện xử lý CPU không liên quan.

Semaphore trong ví dụ là giới hạn bên trong một JVM. Nếu dịch vụ chạy trên 5 instance và mỗi instance có 30 permit, tổng số thao tác có thể đồng thời lên tới 150. Nếu dependency cần một giới hạn toàn cụm, phải phối hợp ở tầng dùng chung như gateway, distributed limiter hoặc chính connection pool/dịch vụ đích; không cộng nhầm giới hạn local thành giới hạn toàn hệ thống.

## 6. Kết hợp virtual thread với giới hạn tài nguyên

Virtual thread phù hợp với nhiều tác vụ blocking vì có thể tạo số lượng lớn với chi phí thấp hơn platform thread. Tuy nhiên, không nên dùng số lượng virtual thread làm giới hạn tải. Hãy giới hạn request tại ingress và giới hạn từng tài nguyên bên trong tác vụ.

Ví dụ, executor tạo virtual thread theo từng task, nhưng chỉ cho phép tối đa 30 thao tác database chạy cùng lúc:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

final class OrderService {
    private final ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor();
    private final Semaphore databaseSlots = new Semaphore(30);

    void submit(Order order) {
        executor.submit(() -> {
            if (!databaseSlots.tryAcquire()) {
                rejectDatabaseOverload(order);
                return;
            }

            try {
                saveOrder(order);
            } finally {
                databaseSlots.release();
            }
        });
    }

    void close() {
        executor.close();
    }

    private void saveOrder(Order order) {
        // Ghi dữ liệu vào database.
    }

    private void rejectDatabaseOverload(Order order) {
        // Chuyển sang phản hồi/fallback phù hợp.
    }
}
```

Ví dụ trên minh họa giới hạn database, nhưng bản thân `submit()` vẫn có thể tạo rất nhiều virtual thread nếu `submit` được gọi không giới hạn. Trong ứng dụng HTTP, cần một giới hạn admission khác ở tầng nhận request hoặc một queue có giới hạn trước khi submit. Nếu cần từ chối trước khi tạo task, lấy permit admission ở caller, rồi chuyển quyền sở hữu permit cho task và bảo đảm nhả permit nếu submit thất bại.

Không tạo pool để tái sử dụng virtual thread; mô hình hiện hành là tạo virtual thread cho từng task. Hãy giới hạn những thứ task sử dụng, chẳng hạn database connection, API quota, số request in-flight và bộ nhớ body.

## 7. Hàng đợi cũng là một ngân sách bộ nhớ

Giới hạn số task chưa đủ nếu mỗi task giữ một payload rất lớn. Hãy ước lượng bộ nhớ mà queue có thể giữ:

\[
M_{queue} \approx Q \times B_{avg}
\]

Trong đó:

- `Q` là số task tối đa trong queue.
- `B_avg` là lượng bộ nhớ trung bình được giữ lại bởi mỗi task đang chờ, gồm request body, object, closure và context liên quan.

Ví dụ, nếu mỗi request giữ trung bình 256 KiB dữ liệu và queue chứa 1.000 request, riêng payload có thể giữ khoảng 250 MiB, chưa tính object overhead, buffer, task đang chạy, response và các dữ liệu khác.

Do đó, hãy đặt giới hạn đồng thời cùng với:

- Kích thước request body tối đa.
- Kích thước file upload và số upload đồng thời.
- Giới hạn message/batch size khi xử lý queue.
- Số response buffer và dữ liệu đã giải nén được giữ trong heap.
- Số connection đang mở và số connection chờ trong pool.
- Thời gian tối đa request được phép nằm trong queue.

Nếu có thể, dùng streaming để xử lý dữ liệu theo từng phần thay vì đọc toàn bộ body vào bộ nhớ. Streaming cũng cần giới hạn số stream đang hoạt động và buffer mỗi stream; nó không làm bộ nhớ trở thành miễn phí.

## 8. Dùng Little's Law để ước lượng mức đồng thời

Trong một hệ thống ổn định với các giá trị trung bình hữu hạn, Little's Law mô tả mối quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian một công việc ở trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- `L`: số request trung bình đang ở trong hệ thống.
- `λ`: throughput trung bình, tính bằng request mỗi giây.
- `W`: thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, dịch vụ hoàn tất trung bình 120 request/giây và thời gian một request ở trong hệ thống trung bình là 0,25 giây:

\[
L = 120 \times 0.25 = 30
\]

Như vậy, trung bình có khoảng 30 request đang ở trong hệ thống. Nếu chỉ xét thời gian chờ queue, dùng dạng tương ứng:

\[
L_q = \lambda \times W_q
\]

Với throughput 120 request/giây và thời gian chờ queue trung bình 0,1 giây, queue trung bình có khoảng 12 request.

Little's Law giúp ước lượng mức đồng thời từ số liệu thực tế, nhưng không tự cho biết queue capacity tối ưu hay mức tải tối đa an toàn. Cần đo latency ở percentile cao, thời gian xử lý, burst traffic, mức sử dụng bộ nhớ và giới hạn dependency để chọn ngưỡng. Không lấy throughput trung bình làm lý do đặt queue cực lớn.

## 9. Deadline, timeout và request đã hết hạn

Một request có thể chờ trong queue lâu đến mức khi worker bắt đầu xử lý, kết quả không còn hữu ích. Ví dụ, người dùng đã đóng kết nối hoặc deadline của request đã hết.

Nên dùng một deadline tổng cho request và phân bổ ngân sách thời gian cho từng giai đoạn:

```text
Tổng deadline của request
  ├── Thời gian chờ admission/queue
  ├── Thời gian xử lý nội bộ
  ├── Thời gian chờ database
  └── Thời gian gọi dịch vụ từ xa
```

Không đặt timeout độc lập quá dài cho từng dependency khiến tổng thời gian vượt deadline của request. Truyền thời gian còn lại xuống các tầng dưới; nếu request đã hết hạn, bỏ hoặc hủy công việc theo cách an toàn.

Với `Future`, có thể dùng `get(timeout, unit)` để giới hạn thời gian chờ kết quả và `cancel(true)` để gửi yêu cầu hủy task. Tuy nhiên, hủy vẫn mang tính hợp tác: task và API I/O phải phản hồi interruption hoặc có cơ chế đóng tài nguyên riêng.

Không dùng timeout như một cách thay thế cho giới hạn concurrency. Timeout giới hạn thời gian giữ công việc; semaphore và bounded queue giới hạn số công việc được nhận hoặc chạy cùng lúc. Hệ thống ổn định thường cần cả hai.

## 10. Backpressure và lựa chọn cách phản hồi quá tải

Backpressure là cách làm chậm hoặc từ chối producer khi consumer không thể xử lý thêm công việc. Khi queue đầy hoặc hết permit, có một số chính sách phổ biến:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Reject fast | Từ chối ngay, ví dụ HTTP 503 hoặc 429 theo ngữ nghĩa API | Caller có thể thử lại sau hoặc hiển thị lỗi |
| Wait briefly | Chờ một khoảng nhỏ để có slot | Có giới hạn caller và deadline còn đủ |
| Caller-runs | Producer tự thực thi task | Producer là worker có thể chịu tải và việc chạy task không chặn event loop |
| Load shedding | Bỏ tác vụ không thiết yếu hoặc dữ liệu đã lỗi thời | Có thể xác định rõ mức ưu tiên và hậu quả nghiệp vụ |
| Queue bền vững | Ghi message vào broker để xử lý sau | Cần chịu được process restart và chấp nhận độ trễ lớn hơn |

Nếu trả 429 khi client vượt quota/rate limit hoặc 503 khi dịch vụ tạm thời không đủ capacity, có thể cung cấp `Retry-After` khi phù hợp. Client cần retry với exponential backoff và jitter; retry ngay lập tức từ mọi client có thể tạo thành một đợt tải mới đúng lúc hệ thống đang quá tải.

Không tự động retry mọi request bị từ chối. Cần xác định thao tác có idempotent không, có idempotency key không và deadline của client còn hiệu lực không.

## 11. Theo dõi các giới hạn trong production

Để biết giới hạn có phù hợp, cần quan sát cả lượng công việc, thời gian chờ và kết quả từ chối. Các metric hữu ích gồm:

| Metric | Dấu hiệu cần quan sát |
|---|---|
| Active worker / active request | Số lượng đang sử dụng và tỷ lệ so với giới hạn |
| Queue depth | Queue tăng liên tục hoặc thường xuyên chạm capacity |
| Queue wait time | Thời gian task nằm chờ trước khi bắt đầu |
| Task/service duration | Dependency chậm làm worker hoặc permit bị giữ lâu |
| Rejected task/request | Số lần bị từ chối và tỷ lệ trên tổng request |
| Semaphore permits available | Tài nguyên nào thường xuyên hết slot |
| Heap usage và allocation rate | Queue hoặc payload đang giữ quá nhiều bộ nhớ |
| Timeout/cancellation | Request hết deadline hoặc task bị hủy |
| Connection pool pending/acquired | Áp lực lên database hoặc dịch vụ ngoài |

Đặc biệt, hãy phân biệt queue depth cao do burst ngắn với queue tăng liên tục. Queue thường xuyên chạm giới hạn cho thấy consumer không theo kịp producer hoặc giới hạn đang đặt chưa phù hợp; tăng capacity chỉ trì hoãn thời điểm quá tải và có thể làm latency tệ hơn.

## 12. Ví dụ kết hợp bounded queue và xử lý rejection

Đây là mẫu platform-thread executor với queue có giới hạn. Executor được đóng khi thành phần sở hữu kết thúc vòng đời:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

final class ImageProcessor implements AutoCloseable {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4,
            8,
            30,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(100),
            new ThreadPoolExecutor.AbortPolicy()
    );

    boolean submit(ImageJob job) {
        try {
            executor.execute(() -> process(job));
            return true;
        } catch (RejectedExecutionException e) {
            return false;
        }
    }

    private void process(ImageJob job) {
        // Xử lý ảnh; cần giới hạn kích thước ảnh và buffer riêng.
    }

    @Override
    public void close() {
        executor.close();
    }
}
```

Caller nhận `false` khi executor từ chối task và có thể trả phản hồi quá tải. Trong ứng dụng thực tế, cần ghi metric rejection và xác định phản hồi phù hợp cho từng loại job. `close()` chờ các task đã nhận hoàn tất; thành phần sở hữu cần gọi nó ở thời điểm shutdown thích hợp, không gọi sau mỗi request.

## 13. Checklist thiết kế concurrency limit

- [ ] Có giới hạn số request in-flight tại tầng nhận request.
- [ ] Có giới hạn số worker hoặc số task đang chạy phù hợp với workload.
- [ ] Queue có capacity hữu hạn và rejection policy rõ ràng.
- [ ] Đã hiểu queue mặc định của executor factory đang sử dụng.
- [ ] Có semaphore hoặc giới hạn riêng cho database, API ngoài và tài nguyên hữu hạn.
- [ ] Đã đặt giới hạn payload, file upload, batch size và buffer.
- [ ] Đã ước lượng bộ nhớ mà queue và request đang hoạt động có thể giữ.
- [ ] Có deadline/timeout cho thời gian chờ queue và dependency.
- [ ] Không giả định virtual thread tự giới hạn số request hoặc tài nguyên.
- [ ] Có backpressure/rejection và chính sách retry an toàn.
- [ ] Theo dõi queue depth, queue wait, active count, rejection, memory và timeout.
- [ ] Đã kiểm thử tải bình thường, burst và quá tải kéo dài để xác nhận giới hạn.

## Tài liệu tham khảo

- [ThreadPoolExecutor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): pool sizing, work queue, rejection handler và các chính sách từ chối task.
- [BlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): queue bounded/unbounded và các phương thức insert, wait, reject.
- [Executors — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): factory executor, fixed/cached pool và virtual-thread-per-task executor.
- [Semaphore — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn số permit và điều phối truy cập tài nguyên.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời executor, submit task và quản lý shutdown.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread và lưu ý về việc giới hạn tài nguyên thay vì pool virtual thread.
