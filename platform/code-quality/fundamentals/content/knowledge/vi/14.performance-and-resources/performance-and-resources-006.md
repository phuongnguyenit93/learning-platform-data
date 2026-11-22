# Giới hạn bộ đệm, hàng đợi và số tác vụ đồng thời

Một hệ thống xử lý nhanh khi ít yêu cầu có thể trở nên rất chậm hoặc mất ổn định khi có nhiều yêu cầu đến cùng lúc. Nguyên nhân không chỉ là thuật toán tốn CPU: **bộ đệm quá lớn, hàng đợi không giới hạn và quá nhiều tác vụ đồng thời** có thể tiêu thụ hết bộ nhớ, kết nối hoặc thời gian chờ của người dùng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Ở chương **Hiệu năng và tài nguyên**, một thiết kế tốt cần thể hiện rõ: hệ thống **nhận bao nhiêu công việc, giữ bao nhiêu việc đang chờ, chạy đồng thời bao nhiêu việc và phản ứng thế nào khi hết năng lực xử lý**.

Bài học phân biệt ba loại giới hạn, phân tích cơ chế **backpressure** (điều tiết ngược), minh họa bằng Java 17 và JUnit 5, rồi xây dựng cách kiểm tra để hệ thống không âm thầm suy giảm khi tải tăng.

## 1. Vì sao thêm hàng đợi và thêm luồng chưa chắc giải quyết được quá tải?

Giả sử một dịch vụ tiếp nhận yêu cầu tạo báo cáo. Mỗi báo cáo cần xử lý dữ liệu và gọi một phụ thuộc. Khi số yêu cầu tăng, nhóm phát triển có thể nghĩ:

- “Hãy tăng số luồng để xử lý nhiều yêu cầu hơn.”
- “Hãy tăng hàng đợi để không phải từ chối khách hàng.”
- “Hãy lưu mọi request vào bộ nhớ rồi xử lý sau.”

Những cách này có thể hiệu quả trong **một số điều kiện** nhưng không tự tạo thêm năng lực CPU, bộ nhớ, kết nối CSDL hoặc giới hạn của dịch vụ ngoài.

Khi lượng công việc đến **liên tục vượt quá khả năng hoàn tất**, công việc tồn đọng sẽ tăng. Hàng đợi lớn hơn có thể trì hoãn thời điểm từ chối nhưng cũng làm tăng thời gian chờ và lượng bộ nhớ bị giữ lại. Tăng số tác vụ đồng thời quá mức có thể khiến chúng cạnh tranh tài nguyên và **làm giảm thông lượng thực tế**.

Mô hình đơn giản:

~~~mermaid
flowchart LR
    A["Yêu cầu đến"] --> B{"Kiểm soát tiếp nhận"}
    B -- "Được nhận" --> C["Hàng đợi có giới hạn"]
    B -- "Quá tải" --> D["Từ chối / yêu cầu thử lại"]
    C --> E["Nhóm worker có giới hạn"]
    E --> F["CPU / DB / API phụ thuộc"]
    F --> G["Hoàn tất và giải phóng tài nguyên"]
~~~

**Bốn câu hỏi cần trả lời rõ:** ai được nhận vào, ai phải chờ, ai được chạy, và ai chịu trách nhiệm khi tài nguyên đã đầy.

## 2. Phân biệt bộ đệm, hàng đợi và số tác vụ đồng thời

| Khái niệm | Đối tượng được giới hạn | Ví dụ | Khi không có giới hạn |
| --- | --- | --- | --- |
| **Bộ đệm (buffer)** | Dữ liệu được giữ tạm trong bộ nhớ hoặc vùng lưu trữ. | Mảng byte khi tải file, bộ đệm phản hồi HTTP, bộ đệm ghi log. | Bộ nhớ có thể tăng theo kích thước hoặc số dữ liệu đến. |
| **Hàng đợi (queue)** | Các tác vụ hoặc thông điệp đã được nhận nhưng **chưa được xử lý**. | Danh sách job chờ worker. | Thời gian chờ và lượng đối tượng tồn đọng tăng không kiểm soát. |
| **Số tác vụ đồng thời (concurrency)** | Các công việc đang thực sự thực hiện hoặc chiếm tài nguyên cùng lúc. | 8 truy vấn DB đang chạy, 4 báo cáo đang tạo. | Có thể cạn luồng, kết nối, CPU hoặc hạn mức phụ thuộc. |
| **Giới hạn đầu vào** | Kích thước hoặc số lượng dữ liệu mà một yêu cầu được phép mang theo. | File tối đa 20 MiB, danh sách tối đa 500 mục. | Một yêu cầu lớn có thể chiếm nguồn lực vượt dự kiến. |

Một **bộ đệm** có thể chứa byte, không nhất thiết chứa task. Một **hàng đợi** có thể là bộ đệm chứa các tác vụ chưa chạy. **Số luồng** không hoàn toàn đồng nghĩa số tác vụ đang gây tải: một tác vụ có thể gọi nhiều phụ thuộc, và một mô hình bất đồng bộ có thể có nhiều yêu cầu đang chờ I/O mà không chiếm riêng một luồng.

### Giới hạn ở những vị trí khác nhau

Ví dụ một dịch vụ xử lý file:

~~~text
HTTP request
  -> giới hạn kích thước file
  -> bộ đệm đọc theo từng khối
  -> hàng đợi tác vụ đã được chấp nhận
  -> worker xử lý file
  -> pool kết nối CSDL / dịch vụ ngoài
~~~

Giới hạn ở mỗi tầng có mục đích riêng. Giới hạn worker không thay thế giới hạn kích thước file; giới hạn hàng đợi không thay thế giới hạn số kết nối đang mở.

## 3. Bài toán xuyên suốt: dịch vụ tạo báo cáo

Giả sử một dịch vụ nhận yêu cầu tạo báo cáo và có các đặc tính **giả định**:

- Mỗi báo cáo mất trung bình **200 ms thời gian thực hiện**, trong điều kiện tải chuẩn.
- Tạm thời dùng **4 worker** chạy song song.
- Hàng đợi chỉ chứa tối đa **50 báo cáo đang chờ**.
- Một đợt tăng tải đưa **30 yêu cầu/giây** tới dịch vụ trong một khoảng thời gian.
- Chưa xét các giới hạn khác như CSDL, GC, biến thiên thời gian báo cáo hoặc chi phí tiếp nhận.

Nếu mỗi worker hoàn thành trung bình một tác vụ sau 0,2 giây, **mức thông lượng lý tưởng xấp xỉ 4 / 0,2 = 20 báo cáo/giây** trong điều kiện giả định.

Với lượng đến 30 báo cáo/giây, phần tồn đọng có thể tăng khoảng **10 báo cáo/giây** khi hệ thống đã chạy ở mức ổn định. Một hàng đợi trống chứa tối đa 50 tác vụ có thể đầy trong khoảng 5 giây nếu đợt tải kéo dài với cùng mức chênh lệch.

**Đây là phép tính minh họa năng lực trung bình, không phải cam kết hiệu năng.** Thời gian xử lý có phân phối, worker có thể bị chặn bởi phụ thuộc, lịch chạy và GC khiến tốc độ thay đổi. Hệ thống thật cần **đo ở tải đại diện**.

Điều quan trọng: nếu hàng đợi đã đầy mà dịch vụ vẫn nhận thêm yêu cầu vô hạn, thời gian chờ hoặc tài nguyên giữ lại không còn được kiểm soát.

## 4. Tại sao hàng đợi không giới hạn nguy hiểm?

Một hàng đợi không giới hạn có thể tạo ấn tượng rằng ứng dụng “không bỏ sót request” vì phương thức nhận tác vụ vẫn thành công. Nhưng chấp nhận vào bộ nhớ **không có nghĩa đã xử lý xong hoặc sẽ xử lý thành công**.

Những rủi ro thường gặp:

1. **Áp lực bộ nhớ:** mỗi tác vụ giữ object, tham số, closure, tham chiếu tới buffer, context hoặc dữ liệu lớn.
2. **Độ trễ tăng:** công việc chờ lâu dù khi thực sự chạy chỉ mất ít thời gian.
3. **Công việc lỗi thời:** một tác vụ đợi vài phút có thể không còn ý nghĩa với người dùng.
4. **Khả năng phục hồi kém:** khi phụ thuộc chậm, công việc được nhận vào nhanh hơn tốc độ tiêu thụ.
5. **Sự cố dây chuyền:** bộ nhớ căng và GC tăng có thể làm chậm cả phần còn lại của ứng dụng.
6. **Bảo đảm giao việc giả:** tác vụ chỉ nằm trong RAM có thể mất khi tiến trình chết.

Trong Java, cần chú ý **Executors.newFixedThreadPool(n)** sử dụng hàng đợi chia sẻ **không giới hạn theo dung lượng được cấu hình** ở mô hình thông thường. Dù số worker cố định, số Runnable đang chờ vẫn có thể tăng rất lớn nếu bên gọi gửi nhanh hơn tốc độ xử lý.

**Executors.newCachedThreadPool()** có đặc tính khác: có thể tạo thêm nhiều luồng khi nhu cầu tăng, nên cần hiểu giới hạn luồng và tác động tài nguyên trước khi dùng cho tải không kiểm soát.

Không kết luận hai factory này luôn sai: chúng có thể phù hợp với tải đã được giới hạn ở phía trước. Vấn đề là **không biết giới hạn thực sự nằm ở đâu**.

## 5. Giới hạn bộ đệm theo lượng dữ liệu giữ lại, không chỉ theo số mục

Hàng đợi 100 mục không có nghĩa nó chỉ giữ một lượng bộ nhớ nhỏ. Nếu mỗi tác vụ giữ tham chiếu tới một mảng byte 1 MiB, 100 tác vụ có thể giữ khoảng **100 MiB dữ liệu thô**, chưa tính object, overhead và các bản sao khác.

Ngược lại, 100 tác vụ chỉ chứa một định danh ngắn có thể cần ít bộ nhớ hơn nhiều. Vì vậy:

- Xác định **kích thước trung bình và kích thước xấu nhất** của đối tượng được giữ.
- Ưu tiên xếp hàng **định danh hoặc thông tin tối thiểu** thay vì ôm toàn bộ file vào closure.
- Giới hạn **số mục** và khi cần, cả **tổng số byte** đã nhận.
- Đọc dữ liệu lớn **theo luồng/từng khối** khi khả thi, thay vì tải toàn bộ trước khi kiểm tra giới hạn.
- Tránh giữ request context, stream, kết nối và dữ liệu nhạy cảm lâu hơn vòng đời cần thiết.

Ví dụ mã dễ làm tăng bộ nhớ:

~~~java
// Mỗi lambda giữ tham chiếu tới toàn bộ nội dung file.
byte[] fileBytes = readEntireFile();
executor.execute(() -> parseFile(fileBytes));
~~~

Một hướng thiết kế khác là lưu file theo cơ chế có kiểm soát, sau đó chỉ xếp hàng **jobId** hoặc đường dẫn tham chiếu an toàn. Khi worker được phép chạy, nó mới mở dữ liệu bằng cách đọc từng phần và đóng tài nguyên đúng thời điểm. Tuy nhiên, cách này chuyển thêm trách nhiệm sang kho lưu trữ; cần có giới hạn dung lượng, thời gian lưu, dọn dẹp và phân quyền truy cập file.

## 6. Giới hạn số worker với ThreadPoolExecutor

Java cung cấp **ThreadPoolExecutor** cho phép cấu hình số luồng và hàng đợi có dung lượng cố định. Ví dụ dưới đây dùng Java 17, cho phép gửi tác vụ **đã được kiểm tra** vào một nhóm worker có giới hạn.

~~~java
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BoundedTaskExecutor {
    private final ThreadPoolExecutor executor;

    public BoundedTaskExecutor(int workers, int waitingCapacity) {
        if (workers <= 0 || waitingCapacity <= 0) {
            throw new IllegalArgumentException("Limits must be positive");
        }

        executor = new ThreadPoolExecutor(
                workers,
                workers,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(waitingCapacity),
                new ThreadPoolExecutor.AbortPolicy());
    }

    // true: tác vụ được tiếp nhận, KHÔNG có nghĩa đã hoàn tất.
    // false: executor từ chối vì đầy, đang đóng hoặc đã đóng.
    public boolean trySubmit(Runnable task) {
        Objects.requireNonNull(task, "task");
        try {
            executor.execute(task);
            return true;
        } catch (RejectedExecutionException rejected) {
            return false;
        }
    }

    // Chỉ dùng làm thông tin quan sát; không ra quyết định admission
    // dựa trên getQueue().size() vì số liệu có thể thay đổi ngay lập tức.
    public int queuedTasks() {
        return executor.getQueue().size();
    }

    public int activeWorkers() {
        return executor.getActiveCount();
    }

    public void shutdown() {
        executor.shutdown();
    }

    public boolean awaitTermination(long timeout, TimeUnit unit)
            throws InterruptedException {
        return executor.awaitTermination(timeout, unit);
    }
}
~~~

Ở ví dụ này:

- **workers** là số luồng core **và** maximum; không quá số đó các tác vụ đang chạy đồng thời trong executor theo cấu hình.
- **ArrayBlockingQueue** chỉ giữ tối đa **waitingCapacity** tác vụ đang đợi trong hàng đợi.
- **AbortPolicy** ném RejectedExecutionException khi không thể chấp nhận tác vụ.
- **trySubmit** chuyển việc từ chối thành boolean để tầng tiếp nhận có thể xử lý một cách tường minh.
- **queuedTasks** và **activeWorkers** là số liệu quan sát gần đúng, không phải phép kiểm tra đủ chỗ một cách nguyên tử.
- **shutdown** bắt đầu đóng executor; nó không tự bảo đảm đã hoàn tất tất cả tác vụ.

Đây là ví dụ giới hạn tài nguyên **trong một tiến trình**. Nếu ứng dụng chạy trên 5 replica, mỗi replica có executor riêng và tổng số tác vụ có thể cao hơn năm lần. Khi phụ thuộc có hạn mức toàn hệ thống, phải tính cả số replica và các luồng khác cùng dùng phụ thuộc.

### Lưu ý về lỗi trong tác vụ

Số luồng và hàng đợi được giới hạn **không có nghĩa ngoại lệ trong Runnable được xử lý đúng**. Một task có thể lỗi sau khi được nhận. Với công việc nghiệp vụ, cần thiết kế **định danh job, trạng thái hoàn tất/thất bại, logging và cách thông báo kết quả**. Không nên trả HTTP 200 “đã xử lý xong” chỉ vì trySubmit trả true.

Đối với job cần bảo đảm không mất khi tiến trình dừng, một hàng đợi RAM không đủ: cần cân nhắc **kho job bền vững**, outbox hoặc broker có cơ chế xác nhận và xử lý lặp theo hợp đồng.

## 7. Kiểm thử hành vi khi đầy hàng đợi

Chỉ kiểm thử “gửi một tác vụ và nó chạy thành công” không chứng minh được giới hạn có hiệu lực. Cần tạo tình huống worker đang bận, hàng đợi đã đầy rồi kiểm tra tác vụ mới bị từ chối **mà không phá trạng thái của các tác vụ đã nhận**.

Ví dụ JUnit 5 dùng CountDownLatch để giữ worker bận một cách có kiểm soát:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class BoundedTaskExecutorTest {
    @Test
    void rejectsWhenWorkersAndWaitingQueueAreFull()
            throws InterruptedException {

        BoundedTaskExecutor bounded = new BoundedTaskExecutor(2, 1);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable blocked = () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            assertTrue(bounded.trySubmit(blocked));
            assertTrue(bounded.trySubmit(blocked));
            assertTrue(started.await(5, TimeUnit.SECONDS));

            // Hai worker đang bận; một chỗ đợi cuối cùng.
            assertTrue(bounded.trySubmit(() -> {}));
            assertEquals(1, bounded.queuedTasks());

            // Không còn chỗ: phải từ chối.
            assertFalse(bounded.trySubmit(() -> {}));
            assertEquals(1, bounded.queuedTasks());
        } finally {
            release.countDown();
            bounded.shutdown();
            assertTrue(bounded.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

**Ý nghĩa của kiểm thử:** trước khi lấp hàng đợi, ta đã biết hai worker thực sự đang chờ release. Điều này tránh dựa vào một khoảng Thread.sleep đoán chừng. Hai assertion sau đó kiểm tra giới hạn 1 tác vụ đang đợi và hành vi từ chối.

Đoạn test là ví dụ về kiểm tra cấu hình ở đơn vị nhỏ; trên CI quá chậm, các timeout cố định vẫn có thể gây thất bại do môi trường. Cần thiết kế test ổn định và theo dõi các trường hợp timeout thay vì bỏ qua tín hiệu lỗi.

Bộ kiểm thử đầy đủ còn nên có: giá trị cấu hình không hợp lệ, shutdown, tác vụ tự ném exception, dừng ứng dụng khi còn job, và kiểm tra khi nhiều bên gửi đồng thời.

## 8. Khi giới hạn đạt ngưỡng: backpressure và overload policy

**Backpressure** là cơ chế ngăn phía tạo công việc tiếp tục gửi nhanh hơn khả năng tiếp nhận hoặc xử lý của phía sau. Nó có thể diễn ra ở mức API, queue, stream, thread pool hoặc phụ thuộc.

Những lựa chọn thường gặp:

| Chính sách | Hành vi | Khi nào phù hợp | Rủi ro cần kiểm tra |
| --- | --- | --- | --- |
| **Từ chối sớm** | Không nhận thêm việc khi đầy; trả trạng thái quá tải. | API có thể đề nghị phía gọi thử lại, hoặc job không bắt buộc phải nhận mọi lúc. | Cần hợp đồng rõ, tránh retry đồng loạt. |
| **Chờ có giới hạn** | Chỉ chờ một khoảng thời gian hoặc đến deadline. | Có năng lực phục hồi nhanh, phía gọi chấp nhận chờ. | Chờ cũng giữ luồng/kết nối; không được chờ vô hạn. |
| **CallerRuns** | Bên gửi tự chạy tác vụ khi pool quá tải, theo quy tắc handler. | Một số pipeline nội bộ có thể chậm producer một cách tự nhiên. | Có thể làm nghẽn HTTP/event-loop hoặc tạo side effect ở ngữ cảnh không mong muốn. |
| **Giảm mức phục vụ** | Bỏ tính năng không thiết yếu hoặc dùng kết quả được phép từ cache. | Gợi ý, ảnh xem trước, dữ liệu công khai ít quan trọng. | Không thể áp dụng nếu làm sai quy tắc tiền, quyền hoặc dữ liệu nhạy cảm. |
| **Bỏ qua công việc có chủ đích** | Hủy dữ liệu có thể mất theo chính sách rõ. | Một số metric, log mức ưu tiên thấp hoặc cập nhật thay thế được. | Nguy hiểm nếu âm thầm bỏ đơn hàng, thanh toán hoặc tác vụ bắt buộc. |
| **Hàng đợi bền vững** | Ghi công việc ra kho riêng rồi worker xử lý sau. | Công việc quan trọng, có yêu cầu phục hồi sau crash. | Vẫn cần giới hạn dung lượng, quyền truy cập, retry và chống xử lý lặp. |

**Không tồn tại một lựa chọn “luôn tốt nhất”.** Cần dựa vào ưu tiên sản phẩm: công việc có thể bị từ chối không, có được phép mất không, thời gian tối đa người dùng chịu được là bao nhiêu, và kết quả có tác dụng phụ nào.

### HTTP có thể phản hồi gì khi từ chối?

Một API công khai có thể dùng:

- **429 Too Many Requests** khi giới hạn áp dụng cho người dùng, khóa API, tenant hoặc chính sách tốc độ.
- **503 Service Unavailable** khi hệ thống tạm thời không đủ năng lực phục vụ do quá tải/phụ thuộc.
- **Retry-After** chỉ khi có cơ sở để hướng dẫn thời điểm phía gọi thử lại; không tự hứa “sau 1 giây chắc chắn thành công”.

Mã phản hồi cụ thể là một phần hợp đồng API. **Không nên biến việc hàng đợi đầy thành HTTP 200** với nội dung “đã hoàn tất”, bởi vì tác vụ chưa được xử lý hoặc chưa được nhận.

## 9. Vì sao CallerRunsPolicy không mặc nhiên an toàn?

ThreadPoolExecutor có **CallerRunsPolicy**, thường khiến luồng gọi phương thức execute tự chạy Runnable khi executor chưa ở trạng thái shutdown và không thể nhận thêm.

Điều này có thể **làm chậm producer**, tạo backpressure tự nhiên ở một pipeline nội bộ. Nhưng nó cũng chuyển địa điểm thực thi:

~~~text
Thông thường:
HTTP thread -> enqueue -> worker thread chạy tác vụ

Khi CallerRuns được kích hoạt:
HTTP thread -> trực tiếp chạy tác vụ
~~~

Nếu tác vụ mất nhiều giây, HTTP thread có thể bị giữ lâu, dẫn đến timeout hoặc giảm số request đồng thời mà máy chủ xử lý được. Trên event-loop, chạy công việc blocking còn có thể làm ảnh hưởng nhiều kết nối khác.

Ngoài ra, khi executor đã shutdown, CallerRunsPolicy có thể **không chạy tác vụ bị từ chối** theo cơ chế handler của Java; vì vậy không được dùng nó như bảo đảm mọi tác vụ đều đã được thực hiện.

Chỉ chọn CallerRuns khi hiểu rõ **ngữ cảnh của caller, vòng đời executor, deadline và tác dụng phụ**. Đối với dịch vụ HTTP cần bảo vệ độ trễ, từ chối tường minh thường dễ kiểm soát hơn.

## 10. Giới hạn số tác vụ đang gọi một phụ thuộc bằng Semaphore

Giới hạn worker của một pool không nhất thiết giới hạn mọi lời gọi tới cùng một phụ thuộc: nhiều endpoint hoặc service khác có thể sử dụng pool riêng. Một cơ chế **giới hạn số thao tác đang diễn ra** ngay trước phụ thuộc là Semaphore.

Ví dụ Java 17 cho một gateway gọi hệ thống kho:

~~~java
import java.util.Objects;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class LimitedInventoryGateway {
    @FunctionalInterface
    public interface InventoryClient {
        String load(String productCode);
    }

    public static final class TooBusyException extends RuntimeException {
        public TooBusyException() {
            super("Inventory dependency is busy");
        }
    }

    private final Semaphore permits;
    private final InventoryClient client;

    public LimitedInventoryGateway(int maxConcurrentCalls,
                                   InventoryClient client) {
        if (maxConcurrentCalls <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        this.permits = new Semaphore(maxConcurrentCalls);
        this.client = Objects.requireNonNull(client);
    }

    public String load(String productCode) throws InterruptedException {
        Objects.requireNonNull(productCode);

        // Không cho mọi caller chờ vô hạn để lấy permit.
        if (!permits.tryAcquire(150, TimeUnit.MILLISECONDS)) {
            throw new TooBusyException();
        }

        try {
            return client.load(productCode);
        } finally {
            permits.release();
        }
    }
}
~~~

Ở đây:

- Semaphore giới hạn **số lời gọi client.load đang giữ permit trong cùng instance**.
- Bên gọi chờ tối đa **150 ms** để lấy quyền thực hiện; đây là con số minh họa, cần chỉnh theo deadline thực.
- Khi không lấy được permit, phương thức báo quá tải riêng thay vì mặc định gọi phụ thuộc.
- **finally** bảo đảm trả lại permit khi client hoàn tất hoặc ném ngoại lệ.
- **InterruptedException** được chuyển ra cho bên gọi xử lý, không bị nuốt.

**Lưu ý:** Semaphore không tự giới hạn số caller đang đợi permit ở phía trước. Nếu hàng nghìn HTTP thread đồng thời gọi tryAcquire với timeout, chúng vẫn có thể tạo áp lực bộ nhớ và luồng. Cần kiểm soát tiếp nhận ở tầng trên nữa.

Semaphore cũng chỉ giới hạn trong **một instance**; khi ứng dụng có nhiều replica, tổng số lời gọi tới Inventory có thể vượt giới hạn mỗi instance. Muốn bảo vệ hạn mức dùng chung, cần phân bổ ngân sách theo replica hoặc cơ chế giới hạn toàn hệ thống thích hợp.

### Vì sao release phải nằm trong finally?

Nếu release chỉ được gọi khi client.load trả về thành công, một lỗi runtime có thể khiến permit không được trả lại. Sau nhiều lần như vậy, tất cả permit bị chiếm vĩnh viễn và hệ thống không còn tiếp nhận lời gọi mới.

Ngược lại, không release nếu **tryAcquire chưa thành công**, vì điều đó sẽ làm tăng số permit vượt giới hạn. Cấu trúc if rồi try/finally như ví dụ giúp phân biệt rõ hai trường hợp.

## 11. Queue capacity và concurrency nên được chọn bằng bằng chứng

Không có công thức chung “CPU 8 core thì queue 1.000, worker 100”. Quyết định cần dựa trên **tải thực tế, tài nguyên và mục tiêu thời gian phản hồi**.

Các câu hỏi cần đo:

| Biến số | Điều nên quan sát | Tác động đến giới hạn |
| --- | --- | --- |
| **Arrival rate** | Số việc đến trung bình và trong đỉnh tải. | Cho biết áp lực mà producer tạo ra. |
| **Service time** | Thời gian thực thi trung bình, p95, p99 khi tải tăng. | Cho thấy worker bị giữ trong bao lâu. |
| **Throughput** | Số việc hoàn tất thật mỗi giây. | Cho biết năng lực, không chỉ khả năng nhận vào. |
| **Queue wait time** | Thời gian một tác vụ chờ trước khi bắt đầu. | Giúp giới hạn độ trễ và nhận diện tồn đọng. |
| **Memory per waiting job** | Kích thước dữ liệu và tham chiếu bị giữ. | Giúp chọn giới hạn queue/bytes an toàn. |
| **Dependency capacity** | Connection pool, quota, rate limit, số request phụ thuộc chịu được. | Tránh tăng đồng thời vượt năng lực phía sau. |
| **SLO/latency budget** | Người dùng chấp nhận chờ tối đa bao lâu. | Hàng đợi quá dài có thể không còn giá trị. |
| **Burst duration** | Đợt tải ngắn hay kéo dài nhiều phút. | Phân biệt đệm đỉnh tải ngắn và tình trạng thiếu năng lực kéo dài. |

**Đừng lấy kích thước hàng đợi bằng giới hạn bộ nhớ chia cho size object rồi coi đó là đủ.** Nếu request đợi lâu đến mức hết deadline, công việc nhận vào vẫn có thể vô ích dù bộ nhớ còn đủ.

### Little's Law và cách dùng đúng

Trong điều kiện hệ thống tương đối ổn định, định luật Little biểu diễn quan hệ:

\[
L = \lambda W
\]

Trong đó:

- **L** là số công việc trung bình đang ở trong hệ thống.
- **λ** là tốc độ công việc hoàn tất/đến trong trạng thái ổn định.
- **W** là thời gian trung bình một công việc ở trong hệ thống.

Cần xác định phạm vi đo: nếu **L** gồm cả đang chờ và đang chạy thì **W** cũng phải gồm cả thời gian chờ và chạy. Nếu chỉ đo hàng đợi, các đại lượng phải cùng giới hạn ở hàng đợi.

Little's Law **không phải công thức tự tạo năng lực**. Nó giúp phát hiện chi phí của việc giữ nhiều công việc chờ: khi thông lượng không đổi nhưng số việc tồn đọng tăng, thời gian trung bình trong hệ thống cũng có xu hướng tăng.

## 12. Giới hạn thời gian chờ và vòng đời tác vụ

Một tác vụ có thể đã được tiếp nhận nhưng mất hàng phút mới tới lượt. Khi đó, người dùng có thể đã hủy yêu cầu hoặc hết thời hạn cần kết quả.

Thiết kế nên xác định:

1. **Deadline:** Tác vụ phải có kết quả trước thời điểm nào?
2. **Queue timeout:** Có nên bỏ qua/hủy tác vụ nếu nó chờ quá lâu?
3. **Execution timeout:** Khi đang chạy, có giới hạn thời gian gọi phụ thuộc không?
4. **Cancellation:** Khi phía gọi ngừng chờ, tác vụ có tiếp tục hay cần tín hiệu hủy?
5. **Retry:** Nếu thử lại, ngân sách thời gian tổng có còn đủ không?
6. **Shutdown:** Khi dịch vụ dừng, tác vụ đang chờ và đang chạy được xử lý thế nào?

Một timeout ở tầng HTTP **không mặc nhiên hủy** một Runnable đã được nhận vào thread pool. Nếu hệ thống thực sự yêu cầu dừng công việc, cần thiết kế cơ chế hủy phù hợp và bảo đảm tác vụ kiểm tra interruption/cancellation ở những điểm an toàn.

Tương tự, lời gọi **CompletableFuture.cancel** không nên được giả định là tự ngắt mọi tác vụ đang chạy trên mọi executor. Cần hiểu cơ chế thực tế và tác dụng phụ trước khi hứa có thể hủy.

Với công việc ghi dữ liệu hoặc gửi thanh toán, việc hủy giữa chừng còn đòi hỏi **transaction, idempotency hoặc đối soát** chứ không chỉ ngắt luồng.

## 13. Vì sao virtual thread không tự giải quyết vấn đề giới hạn?

Java hiện đại hỗ trợ mô hình **virtual threads** (Java 21 trở lên). Virtual thread có thể giúp xử lý nhiều tác vụ chờ I/O với chi phí luồng thấp hơn so với nhiều platform thread trong các tình huống phù hợp.

Tuy nhiên:

- Nhiều virtual thread vẫn có thể tạo **nhiều lời gọi đồng thời** tới CSDL hoặc API ngoài.
- Connection pool, rate limit và bộ nhớ vẫn là tài nguyên hữu hạn.
- Một request lớn hoặc object được giữ lâu vẫn tiêu thụ bộ nhớ.
- Queue không giới hạn và thiếu admission control vẫn có thể gây tồn đọng.
- Một số tình huống pinning hoặc sử dụng thành phần blocking không phù hợp có thể ảnh hưởng hiệu quả; cần đo trên môi trường thực.

Vì vậy, **virtual threads cải thiện cách triển khai đồng thời, không thay thế chính sách giới hạn đồng thời**. Ví dụ Semaphore hoặc giới hạn ở dependency vẫn hữu ích khi phải bảo vệ dịch vụ ngoài.

Bài này dùng Java 17 cho ví dụ ThreadPoolExecutor/Semaphore; khi nâng lên Java 21 và dùng virtual threads, vẫn phải thiết kế **capacity, timeouts và backpressure**.

## 14. Giám sát để biết hệ thống đang quá tải thật hay không

Một giới hạn chỉ hữu ích khi đội ngũ có thể quan sát hành vi của nó. Các tín hiệu nên được theo dõi:

| Chỉ số | Câu hỏi nó trả lời |
| --- | --- |
| **Active workers / running tasks** | Có bao nhiêu công việc đang chạy so với giới hạn? |
| **Queue depth và queue utilization** | Hàng đợi hiện đầy tới mức nào? |
| **Queue wait p50/p95/p99** | Tác vụ phải chờ bao lâu trước khi được chạy? |
| **Rejection count/rate** | Bao nhiêu công việc bị từ chối, ở endpoint hoặc tenant nào? |
| **Throughput và completion rate** | Bao nhiêu việc hoàn tất, không chỉ đã nhận vào? |
| **Failure/timeout/cancellation rate** | Có bao nhiêu việc lỗi, hết hạn hoặc bị hủy? |
| **Heap/GC, thread count, connection utilization** | Giới hạn có bảo vệ tài nguyên thật không? |
| **Dependency latency/error rate** | Phụ thuộc bị chậm khiến queue tăng hay không? |
| **Oldest waiting age** | Có công việc nào nằm trong queue quá lâu không? |

Chỉ số **queue depth = 0** không tự động là tín hiệu tốt: có thể do hệ thống không có tải, hoặc do nó từ chối tất cả trước khi nhận. Phải đọc nhiều tín hiệu cùng nhau.

Ngược lại, **queue gần đầy** chưa chắc luôn là lỗi nếu có một đợt tải rất ngắn và thời gian chờ vẫn trong SLO. Nhưng nếu queue liên tục đầy và rejection tăng, cần xem năng lực thật và chính sách admission.

**Cảnh báo** nên gắn với ảnh hưởng đến SLO hoặc hoạt động, không chỉ một ngưỡng kỹ thuật đơn lẻ.

## 15. Kiểm thử quá tải và các đường thất bại

Sau unit test cho hàng đợi đầy, còn cần bằng chứng ở mức tích hợp hoặc tải:

### Trường hợp cần kiểm tra

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Không có tải | Nhận và hoàn tất công việc bình thường. |
| Tải gần ngưỡng | Độ trễ và tài nguyên còn trong ngân sách đã đặt. |
| Tải vượt ngưỡng ngắn | Hàng đợi tăng có giới hạn, không cạn tài nguyên. |
| Tải vượt ngưỡng kéo dài | Từ chối hoặc giảm mức phục vụ theo hợp đồng, không giữ việc vô hạn. |
| Phụ thuộc chậm bất thường | Số lời gọi đồng thời tới phụ thuộc không vượt ngân sách. |
| Tác vụ ném exception | Có trạng thái thất bại và quan sát được, không mất âm thầm. |
| Client timeout/hủy request | Hành vi task và side effect theo đúng chính sách hủy. |
| Executor đang shutdown | Không nhận task mới như thể đã được xử lý. |
| Nhiều replica cùng tải | Tổng mức dùng phụ thuộc được kiểm soát. |
| Job quan trọng và tiến trình crash | Có cơ chế phục hồi nếu hợp đồng yêu cầu. |

Không nên chạy stress test không kiểm soát trên môi trường sản xuất chỉ để chứng minh giới hạn. Dùng môi trường phù hợp, kịch bản tải có giới hạn và số liệu có thể so sánh.

### Các dấu hiệu sai thường bị bỏ sót

- Assert **submit trả về** nhưng không xác nhận kết quả hoặc trạng thái hoàn tất.
- Chỉ đo **thời gian xử lý** mà bỏ qua **thời gian trong queue**.
- Test có 100 request nhưng **không chắc chúng diễn ra đồng thời**.
- Cho một test chạy nhiều giây rồi kết luận “thread pool không deadlock” mà thiếu cơ chế phát hiện.
- Không kiểm tra **rejection**, nên mọi trường hợp đều xanh khi thực tế worker âm thầm bỏ qua task.
- Tăng số worker làm throughput tăng trong test nhỏ nhưng **không đo p99 và tác động tới DB**.

Một test tốt cần có **oracle**: giới hạn nào không được vượt, tỷ lệ thành công nào được yêu cầu, khi nào phải từ chối, và dữ liệu sau thất bại cần ra sao.

## 16. Những đánh đổi khi chọn kích thước queue và concurrency

| Lựa chọn | Lợi ích | Rủi ro |
| --- | --- | --- |
| **Queue rất nhỏ** | Phát hiện quá tải sớm, ít giữ bộ nhớ và giảm thời gian chờ. | Từ chối nhiều hơn khi có burst ngắn dù hệ thống có thể phục hồi nhanh. |
| **Queue lớn hơn có kiểm soát** | Hấp thụ burst ngắn, giảm từ chối nhất thời. | Tăng tail latency và công việc tồn đọng. |
| **Nhiều worker hơn** | Có thể tăng thông lượng nếu đủ tài nguyên và công việc chờ I/O. | Cạnh tranh CPU/DB, GC, chuyển ngữ cảnh và quota phụ thuộc. |
| **Ít worker hơn** | Bảo vệ phụ thuộc và giới hạn tác vụ đang chạy. | Dễ tạo hàng chờ khi nhu cầu vượt năng lực. |
| **Chờ permit lâu** | Có thể tránh từ chối khi năng lực sắp được giải phóng. | Tiêu tốn thời gian request và tài nguyên phía trước. |
| **Từ chối sớm** | Giữ hệ thống khỏe và hành vi dự đoán được. | Phía gọi cần biết cách giảm tốc hoặc retry có kiểm soát. |

Vì vậy, giới hạn nên được xem là **một phần hợp đồng vận hành**, được điều chỉnh bằng số liệu thực và thay đổi có kiểm chứng, chứ không chỉ là các hằng số bất kỳ.

## 17. Quy trình thiết kế giới hạn cho một ca sử dụng

1. **Xác định công việc và nguồn tài nguyên hạn chế.** CPU, bộ nhớ, kết nối DB, API ngoài, file descriptor hoặc thời gian của người dùng?
2. **Phân loại công việc.** Có cần đồng bộ không? Có thể từ chối, hủy, gửi lại hoặc mất có chủ đích không?
3. **Đặt giới hạn đầu vào.** Số phần tử, số byte và kích thước object được giữ trong từng task.
4. **Đặt giới hạn đồng thời.** Bắt đầu từ năng lực đo được của thành phần chậm nhất, không chỉ số core CPU.
5. **Đặt giới hạn hàng đợi và thời gian chờ.** Chọn dung lượng phù hợp với burst và SLO; không dùng vô hạn làm mặc định không suy xét.
6. **Chọn chính sách khi đầy.** Từ chối tường minh, chờ có giới hạn, giảm tính năng hoặc hàng đợi bền vững theo yêu cầu.
7. **Bảo vệ đường thất bại.** Timeout, interruption, exception, shutdown, retry, idempotency và trạng thái tác vụ.
8. **Ghi số liệu quan sát.** Queue depth, age, rejection, completion, latency, memory và lỗi phụ thuộc.
9. **Kiểm thử với tải đại diện.** Đo cả tải nền, burst, sustained overload và dependency degradation.
10. **Điều chỉnh dựa trên bằng chứng.** Tăng giới hạn chỉ khi số liệu cho thấy nó cải thiện kết quả mà không chuyển sự cố sang tài nguyên khác.

### Checklist review code

- **Tác vụ được lưu ở đâu khi chưa chạy?** Queue RAM, broker, CSDL hay stream?
- **Giới hạn queue và bộ đệm là bao nhiêu?** Có giới hạn tổng bytes không?
- **Tối đa có bao nhiêu tác vụ đang gọi cùng một phụ thuộc?** Có nhiều executor hoặc replica không?
- **Ai bị từ chối khi đầy?** Họ nhận tín hiệu nào? Có retry storm không?
- **Việc chờ có deadline không?** Khi quá hạn thì job có bị xử lý vô ích không?
- **Có đường mất công việc âm thầm không?** Rejection handler, lỗi Runnable, shutdown hoặc crash?
- **Có phản hồi nhầm “hoàn tất” với “đã nhận” không?**
- **Có metric, log và test chứng minh giới hạn không?**

## 18. Tình huống tự luyện

### Tình huống A — Queue vô hạn để tránh lỗi

Một API dùng **Executors.newFixedThreadPool(4)** và liên tục nhận hàng nghìn tác vụ mỗi giây. Mỗi task giữ một byte array lớn. Nhóm phát triển thấy execute hiếm khi báo lỗi nên kết luận hệ thống ổn định.

**Câu hỏi:** Vì sao kết luận này yếu?

**Gợi ý:** Hàng đợi có thể tiếp tục tích tụ tác vụ, giữ dữ liệu trong bộ nhớ và tăng thời gian chờ. Cần giới hạn số tác vụ, lượng dữ liệu và phản hồi khi hết năng lực; đo thông lượng hoàn tất thay vì chỉ số việc nhận vào.

### Tình huống B — Tăng worker từ 20 lên 200

Dịch vụ có pool kết nối CSDL tối đa 30, nhưng một ứng dụng tăng worker lên 200 để “tận dụng CPU”. Nhiều worker chờ kết nối và p99 tăng mạnh.

**Câu hỏi:** Vấn đề chính nằm ở đâu?

**Gợi ý:** Tăng luồng không tạo thêm kết nối hoặc năng lực CSDL. Cần xem độ trễ phụ thuộc, giới hạn số tác vụ đang gọi DB, queue wait và throughput thực tế.

### Tình huống C — Dùng CallerRuns trên HTTP thread

Khi pool đầy, request thread tự chạy job mất 5 giây. API trước đó thường phản hồi trong 100 ms.

**Câu hỏi:** Hệ quả có thể là gì?

**Gợi ý:** CallerRuns chuyển tác vụ sang request thread, làm tăng response time và giảm năng lực phục vụ request khác. Cần kiểm tra deadline và hợp đồng, cân nhắc từ chối tường minh hoặc chuyển sang xử lý nền có trạng thái.

### Tình huống D — Giới hạn 10 tác vụ mỗi replica

Ứng dụng có 8 replica, mỗi replica giới hạn tối đa 10 lời gọi đồng thời tới dịch vụ ngoài. Phụ thuộc chỉ cho phép tổng cộng 30 lời gọi đồng thời.

**Câu hỏi:** Giới hạn tại từng instance đã đủ chưa?

**Gợi ý:** Chưa. Tổng khả năng có thể tới 80 lời gọi. Cần phân bổ ngân sách theo replica, dùng cơ chế điều phối hoặc hạn mức chung thích hợp.

### Tình huống E — HTTP đã timeout nhưng worker vẫn chạy

Khách gửi yêu cầu tạo báo cáo, HTTP timeout, nhưng job vẫn nằm trong queue và sau đó ghi báo cáo vào kho.

**Câu hỏi:** Đây có nhất thiết là lỗi không?

**Gợi ý:** Phụ thuộc hợp đồng. Nếu API chỉ nhận việc bất đồng bộ và trả job ID thì tiếp tục xử lý có thể đúng. Nếu hợp đồng nói hủy khi client ngắt, phải có cơ chế hủy rõ. Điều quan trọng là phản hồi “đã nhận”, “đang xử lý”, “đã hoàn tất” và “đã hủy” không bị nhầm nhau.

---

**Ghi nhớ:** **Bộ đệm, hàng đợi và tác vụ đồng thời đều phải có giới hạn phù hợp** với bộ nhớ, năng lực phụ thuộc và ngân sách thời gian. Giới hạn không nhằm từ chối càng nhiều càng tốt mà để **kiểm soát quá tải, tránh giữ việc vô hạn và giữ hành vi thất bại có thể dự đoán**. Hãy kết hợp admission control, backpressure, timeout, quan sát và kiểm thử trước khi tăng số luồng hoặc kích thước queue.
