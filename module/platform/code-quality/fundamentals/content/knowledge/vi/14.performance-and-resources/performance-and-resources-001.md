# Đặt yêu cầu về độ trễ, thông lượng và giới hạn bộ nhớ

Một dịch vụ trả kết quả đúng nhưng mất 12 giây để hoàn thành một yêu cầu thường không mang lại trải nghiệm tốt. Một dịch vụ phản hồi trong 30 mili giây khi chỉ có một người dùng cũng có thể trở nên không sử dụng được khi hàng trăm yêu cầu đến cùng lúc. Một hệ thống đạt tốc độ mong muốn trong vài phút nhưng dùng ngày càng nhiều bộ nhớ rồi bị hệ điều hành dừng tiến trình cũng chưa đáp ứng yêu cầu vận hành.

Trong chương **Hiệu năng và tài nguyên** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học cách biến các mô tả như “nhanh”, “chịu tải tốt”, “không tốn nhiều RAM” thành **hợp đồng hiệu năng có thể đo và kiểm chứng**. Mục tiêu của chất lượng mã nguồn không chỉ là chạy đúng một lần, mà còn **đáng tin cậy, dễ hiểu và dễ thay đổi** dưới điều kiện sử dụng đã thống nhất.

## 1. Ba đại lượng trả lời ba câu hỏi khác nhau

| Đại lượng | Câu hỏi cần trả lời | Đơn vị thường dùng | Điều dễ hiểu nhầm |
| --- | --- | --- | --- |
| **Độ trễ** (*latency*) | Một yêu cầu mất bao lâu từ lúc bắt đầu đến khi người gọi nhận được kết quả? | ms, s; phân vị p50, p95, p99 | Một giá trị trung bình thấp không bảo đảm phần lớn người dùng không gặp yêu cầu chậm |
| **Thông lượng** (*throughput*) | Hệ thống hoàn tất bao nhiêu công việc trong một đơn vị thời gian? | request/s, giao dịch/s, bản ghi/s | Nhiều yêu cầu được gửi đến không có nghĩa nhiều yêu cầu được hoàn tất |
| **Bộ nhớ** (*memory*) | Tiến trình sử dụng bao nhiêu tài nguyên bộ nhớ trong thời gian hoạt động và khi tải tăng? | MiB, GiB; heap, RSS, mức đỉnh | Giới hạn Java heap không đồng nghĩa giới hạn toàn bộ bộ nhớ của tiến trình |

Ba đại lượng liên hệ với nhau nhưng không thay thế được nhau. Tăng số luồng có thể cải thiện thông lượng trong một khoảng tải nhất định nhưng tăng chi phí bộ nhớ, cạnh tranh CPU và độ trễ khi quá tải. Cache có thể giảm độ trễ đọc nhưng tiêu thụ thêm bộ nhớ và cần chiến lược giới hạn, làm mới dữ liệu.

**Độ phức tạp thuật toán** như `O(n)` cũng chỉ là một phần của câu chuyện. Một thuật toán `O(n)` có thể đủ nhanh với 20 mục dữ liệu nhưng không đáp ứng khi đầu vào tăng lên hàng triệu mục; một thuật toán tốt về độ phức tạp vẫn có thể chậm vì I/O, khóa, cấp phát bộ nhớ hoặc gọi mạng.

## 2. Một yêu cầu hiệu năng tốt phải có điều kiện đo

Các câu như “API phải nhanh”, “hệ thống xử lý được nhiều đơn” hoặc “bộ nhớ không quá lớn” **không có tiêu chí chấp nhận rõ**. Người phát triển không thể biết khi nào công việc đã hoàn thành và người kiểm thử cũng khó xác định điều kiện thành công.

Một yêu cầu kiểm chứng được thường bao gồm:

1. **Chức năng hoặc luồng:** yêu cầu nào đang được đo, bắt đầu và kết thúc ở đâu.
2. **Khối lượng và phân bố công việc:** tần suất yêu cầu, kích thước dữ liệu, tỷ lệ thao tác nặng/nhẹ và trạng thái cache.
3. **Đại lượng:** độ trễ theo phân vị, thông lượng hoàn tất, tỷ lệ lỗi hoặc bộ nhớ sử dụng.
4. **Ngưỡng mục tiêu:** số cụ thể và đơn vị rõ ràng.
5. **Khoảng thời gian đánh giá:** trong 5 phút, 30 phút hay một cửa sổ vận hành dài hơn.
6. **Môi trường và cấu hình:** số CPU, RAM/container limit, phiên bản JDK, cơ sở dữ liệu, cấu hình kết nối và mạng.
7. **Điều kiện thất bại:** lỗi, timeout, từ chối do quá tải và hành vi khi hệ thống đã đến giới hạn.

### 2.1. Ví dụ hợp đồng cho API báo giá

Giả sử nhóm cần kiểm chứng API `POST /quotes` trả báo giá cho đơn hàng. Các số dưới đây là **mục tiêu giả định của bài học**, không phải chuẩn chung cho mọi dịch vụ.

**Phạm vi và tải thử:**

- Mỗi yêu cầu có từ 1 đến 20 dòng hàng; 90% yêu cầu có không quá 10 dòng hàng.
- 90% yêu cầu thuộc nhóm báo giá thông thường, 10% cần thêm quy tắc ưu đãi phức tạp.
- Bộ sinh tải tạo **300 yêu cầu đến mỗi giây** trong giai đoạn ổn định; luồng yêu cầu phân bố theo mẫu nghiệp vụ đã xác nhận.
- Môi trường thử có 2 vCPU và giới hạn bộ nhớ container 512 MiB cho mỗi instance; các dịch vụ phụ thuộc được cấu hình và giám sát riêng.
- Khởi động và làm nóng hệ thống trước; sau đó đo liên tục trong **30 phút**.

**Tiêu chí chấp nhận minh họa:**

| Yêu cầu | Định nghĩa đo trong bài | Ngưỡng giả định |
| --- | --- | --- |
| Độ trễ p95 | Từ lúc bộ sinh tải gửi yêu cầu đến khi nhận xong phản hồi, trên các yêu cầu hoàn tất trong cửa sổ 30 phút | `p95 <= 200 ms` |
| Độ trễ p99 | Cùng phạm vi đo như p95; ngoài ra phải thống kê riêng timeout | `p99 <= 500 ms` |
| Thông lượng | Số yêu cầu **hoàn tất** mỗi giây, không chỉ số đã gửi | Ít nhất `300 request/s` tính trung bình trong cửa sổ đo khi tải đến 300 request/s |
| Tỷ lệ lỗi | Yêu cầu thất bại hoặc timeout chia cho toàn bộ yêu cầu gửi trong cửa sổ; phân loại riêng lỗi nghiệp vụ dự kiến | Không quá `0,5%` lỗi không mong đợi |
| Bộ nhớ tiến trình | RSS của tiến trình trong container, quan sát suốt cửa sổ thử | Không vượt `384 MiB` |
| Độ ổn định | Theo dõi hàng đợi, thời gian chờ, CPU, GC và bộ nhớ trong cả cửa sổ | Không có tồn đọng tăng kéo dài hoặc tiến trình bị OOM/khởi động lại |

Các ngưỡng **cùng phải đạt**, không phải lựa chọn một trong ba đại lượng. Ví dụ, hệ thống từ chối nửa số yêu cầu để giữ p95 đẹp thì không đạt tiêu chí tỷ lệ lỗi và thông lượng. Tương tự, đủ 300 request/s trong 20 giây rồi không xử lý được trong 29 phút còn lại thì không đạt yêu cầu ổn định.

**Lưu ý về định nghĩa:** bảng đo phân vị độ trễ trên **các yêu cầu hoàn tất**, do đó yêu cầu timeout hoặc mất kết nối **không được phép biến mất khỏi báo cáo**: chúng được ghi ở mẫu số tổng yêu cầu và số liệu lỗi/timeout riêng. Nếu chỉ lọc những yêu cầu thành công rất nhanh rồi bỏ qua các yêu cầu chậm bị timeout, số p95/p99 sẽ gây hiểu nhầm.

### 2.2. Tách SLI, SLO và điều kiện chấp nhận của bài thử

- **SLI (Service Level Indicator):** phép đo, ví dụ độ trễ p95 trong một khoảng thời gian, tỷ lệ yêu cầu thành công hoặc độ lớn RSS.
- **SLO (Service Level Objective):** mục tiêu gắn với SLI trên **một cửa sổ đánh giá**. Ví dụ “tỷ lệ phản hồi hợp lệ trong 7 ngày đạt từ 99,9%” là một mục tiêu vận hành nếu tổ chức chọn nó.
- **Điều kiện chấp nhận thử tải:** tiêu chí để một phiên thử cụ thể đạt, ví dụ “300 request/s trong 30 phút, p95 không quá 200 ms, lỗi không mong đợi tối đa 0,5%”.

Một bài thử 30 phút đạt mục tiêu **không chứng minh SLO bảy ngày đã đạt**; nó chỉ cung cấp bằng chứng trong môi trường và tải thử cụ thể. Ngược lại, SLO vận hành tốt cũng không thay thế kiểm tra định kỳ khi thay thuật toán, cấu hình hoặc cơ sở dữ liệu.

## 3. Độ trễ: phải đo cả phần đuôi phân bố

Độ trễ là một **phân bố** của nhiều giá trị, không phải một con số cố định. Giả sử quan sát 100 yêu cầu: phần lớn hoàn tất trong 40–80 ms, một số ít mất 500–800 ms vì chờ cơ sở dữ liệu. Trung bình có thể vẫn tương đối đẹp nhưng người dùng ở phần đuôi gặp trải nghiệm kém.

| Chỉ số | Cách hiểu thực tế |
| --- | --- |
| `p50` (median) | Khoảng một nửa mẫu có độ trễ không lớn hơn giá trị này |
| `p95` | Khoảng 95% mẫu có độ trễ không lớn hơn giá trị này |
| `p99` | Khoảng 99% mẫu có độ trễ không lớn hơn giá trị này |
| Maximum | Lần đo chậm nhất quan sát được trong tập mẫu |
| Trung bình | Tổng độ trễ chia số mẫu; nhạy với giá trị cực lớn |

Phân vị thường được ước lượng từ các mẫu hoặc histogram. Có nhiều quy ước nội suy phân vị; công cụ khác nhau có thể cho số hơi khác nhau với tập nhỏ. Khi so sánh, phải biết **cách lấy mẫu, gộp dữ liệu và tính phân vị**.

### 3.1. Quy định điểm bắt đầu và kết thúc

Với một request HTTP, có thể đo:

- **Client-observed latency:** từ khi client gửi yêu cầu đến khi nhận đủ phản hồi, bao gồm thời gian mạng trong điều kiện đo.
- **Server-side latency:** từ khi server nhận yêu cầu đến khi hoàn tất phần xử lý đã đo, không nhất thiết bao gồm toàn bộ mạng.
- **Dependency latency:** thời gian gọi SQL, dịch vụ thanh toán hoặc cache bên trong một request.

Ba con số này giúp phân tích **những phần khác nhau**. Không nên so sánh trực tiếp p95 ở client với p95 của một hàm tính thuần và kết luận hàm đó đã “đạt SLO API”. Muốn kiểm chứng yêu cầu đã đặt ở phía client, cần đo cùng ranh giới client.

Độ trễ end-to-end có thể tách theo các phần:

```text
Tổng thời gian yêu cầu ≈
    thời gian chờ trong hàng đợi
  + thời gian xử lý ứng dụng
  + thời gian phụ thuộc (DB, mạng, I/O...)
  + thời gian truyền phản hồi
```

Đây là cách phân rã khái niệm, không phải công thức cộng trực tiếp các p95 con. **p95 của tổng không bằng tổng các p95 thành phần** trong trường hợp tổng quát vì các độ trễ không nhất thiết xuất hiện đồng thời.

### 3.2. Đo thời gian trong Java

Để đo **khoảng thời gian** bên trong JVM, dùng `System.nanoTime()` thay vì lấy hai mốc `System.currentTimeMillis()` rồi trừ. `nanoTime()` phù hợp để tính khoảng thời gian tương đối; nó không phải dấu thời gian lịch.

Ví dụ ý tưởng:

```java
long startedNanos = System.nanoTime();
try {
    return quoteService.quote(request);
} finally {
    long elapsedNanos = System.nanoTime() - startedNanos;
    latencyRecorder.record(elapsedNanos);
}
```

`quoteService`, `request` và `latencyRecorder` ở đây là các đối tượng minh họa, không phải đoạn chương trình độc lập. Dùng `finally` giúp ghi nhận thời gian cả khi thao tác ném ngoại lệ. Dữ liệu cần được gắn với **loại kết quả** (thành công, lỗi nghiệp vụ, lỗi hạ tầng), tránh chỉ nhìn các trường hợp nhanh và thành công.

Trong môi trường thực tế, nên dùng cơ chế quan sát phù hợp như histogram có số bucket giới hạn thay vì giữ **một bản ghi trong bộ nhớ cho mọi request mãi mãi**. Tránh thêm nhãn metric có cardinality rất cao như `requestId` hoặc `userId` cho mỗi mẫu nếu cơ chế đo không được thiết kế để chịu số nhãn đó.

## 4. Thông lượng: công việc hoàn tất, không phải tải được gửi

Thông lượng có thể tính trong một cửa sổ:

```text
throughput = số công việc hoàn tất / thời lượng quan sát
```

Ví dụ, 18.000 yêu cầu hoàn tất trong 60 giây tương ứng **300 request/s trung bình** trên cửa sổ đó. Nhưng nếu 300 yêu cầu đến mỗi giây mà server chỉ xử lý xong 220, số yêu cầu còn lại có thể **tồn đọng trong hàng đợi, timeout hoặc bị từ chối**. Do vậy cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Offered load / arrival rate | Số yêu cầu được gửi đến mỗi giây |
| Completed throughput | Số yêu cầu kết thúc xử lý mỗi giây |
| Successful throughput | Số yêu cầu hoàn tất **thành công** mỗi giây |
| Error/rejection rate | Tỷ lệ lỗi, từ chối, timeout theo phân loại rõ |
| Queue depth | Số yêu cầu đang chờ xử lý tại một ranh giới |
| In-flight/concurrency | Số thao tác đang được thực hiện hoặc đang tồn tại trong hệ thống |

**Khi quá tải**, hàng đợi có thể tích tụ và làm độ trễ tăng mạnh ngay cả khi CPU hoặc một thành phần đơn lẻ chưa đạt 100%. Giới hạn kết nối DB, khóa dùng chung hoặc phụ thuộc ngoài có thể là nút thắt cổ chai.

### 4.1. Quan hệ giữa tải, độ trễ và số yêu cầu đồng thời

Trong một hệ thống **ổn định** và với cách xác định ranh giới nhất quán, **định luật Little** cung cấp quan hệ:

```text
L = λ × W

L: số công việc trung bình đang ở trong hệ thống
λ: thông lượng trung bình qua ranh giới (công việc/giây)
W: thời gian trung bình một công việc ở trong hệ thống (giây)
```

Ví dụ minh họa: nếu thực sự hoàn tất trung bình `300 request/s` và **thời gian trung bình** mỗi yêu cầu trong ranh giới là `0,12 s`, thì số yêu cầu trung bình đang ở trong ranh giới đó là khoảng `300 × 0,12 = 36`.

Không thay `W` bằng `p95` để suy ra quan hệ tương tự: định luật dùng **giá trị trung bình**, không dùng phân vị. Khi hàng đợi tăng mãi, tải chưa ổn định hoặc việc đo λ và W dùng hai ranh giới khác nhau, phép tính trên cũng không phải dự báo đáng tin cậy.

### 4.2. Tải thực tế không đều

Một bài thử với đúng 300 request/s đều đặn có thể bỏ sót rủi ro của **burst**: ví dụ 600 request/s trong 30 giây rồi trở về 300 request/s. Bên cạnh mức tải ổn định, nên xác định thêm:

- **Mức đỉnh cần chịu:** đỉnh trong bao lâu, được phép tăng độ trễ bao nhiêu?
- **Khả năng phục hồi:** sau khi đỉnh qua đi, hàng đợi có giảm và độ trễ có trở về mức mong đợi không?
- **Đường từ chối có kiểm soát:** khi hệ thống không thể nhận thêm công việc, trả lỗi quá tải có rõ ràng không, và có làm mất yêu cầu đã nhận không?
- **Tương quan với lỗi:** nếu đạt thông lượng cao bằng cách trả nhiều lỗi nhanh, có đáp ứng yêu cầu không?

Các mục tiêu đỉnh cần được xác nhận riêng; không được suy ra một API đạt tải ổn định 300 request/s chắc chắn xử lý tốt đỉnh 600 request/s.

## 5. Bộ nhớ: phải xác định đang giới hạn cái gì

Trong Java, “bộ nhớ tối đa 512 MiB” có thể được diễn giải rất khác nhau:

| Đại lượng | Bao gồm hoặc phản ánh | Lưu ý |
| --- | --- | --- |
| Java heap | Đối tượng Java trong vùng heap, chịu quản lý của GC | `-Xmx` đặt giới hạn heap tối đa, **không** giới hạn toàn bộ tiến trình |
| Metaspace và bộ nhớ native | Metadata lớp, mã JIT, cấu trúc runtime, một phần thư viện native | Có thể tăng ngoài heap |
| Stack của luồng | Bộ nhớ cho ngăn xếp mỗi luồng | Tăng số luồng thường tăng tổng chi phí bộ nhớ |
| Direct/off-heap buffers | Bộ đệm ngoài heap, I/O và các thư viện | Heap thấp không có nghĩa tiến trình ít dùng RAM |
| RSS (*resident set size*) | Lượng trang bộ nhớ tiến trình hiện cư trú trong RAM | Khác heap và có đặc điểm phụ thuộc OS/runtime |
| Giới hạn container | Ngưỡng tài nguyên mà container được phép tiêu thụ theo cấu hình | Vượt giới hạn có thể khiến tiến trình bị dừng, tùy nền tảng |

Nếu container có giới hạn **512 MiB**, đặt `-Xmx512m` không để lại ngân sách rõ ràng cho stack, metaspace, native buffers hoặc bộ nhớ runtime khác. Vì vậy cần **ngân sách cho toàn tiến trình**, không chỉ cho heap.

Ví dụ cho bài học:

```text
Container memory limit:     512 MiB
Mục tiêu RSS khi thử tải:   <= 384 MiB
Khoảng dự phòng tối thiểu
so với container limit:     128 MiB tại mức RSS mục tiêu
```

Đây là cách **đặt mục tiêu**; không có nghĩa đã chứng minh khoảng dự phòng 128 MiB sẽ đủ trong mọi đợt GC, giai đoạn khởi động, thay đổi số luồng hoặc burst tải. Để chọn `-Xmx` và vùng dự phòng thích hợp, phải đo heap sau GC, mức cấp phát, native memory, RSS đỉnh và hành vi dưới tải thật.

### 5.1. Giới hạn dữ liệu đầu vào và hàng đợi

Một hàng đợi có thể tăng gần như vô hạn khi số việc đến lớn hơn khả năng xử lý. Nếu mỗi công việc giữ tham chiếu tới một payload lớn, chính hàng đợi làm bộ nhớ tăng. Tương tự, gọi `readAllBytes()` cho tệp người dùng tải lên mà không giới hạn kích thước có thể tạo áp lực bộ nhớ khó dự đoán.

Các điểm nên có giới hạn rõ:

1. Kích thước request, số dòng hàng và dung lượng payload chấp nhận.
2. Số tác vụ đang chạy đồng thời.
3. Độ sâu hàng đợi chờ, timeout và chính sách từ chối.
4. Kích thước cache, thời gian sống, số key và bộ nhớ dùng cho mỗi entry.
5. Số kết quả được giữ trong RAM, nhất là thao tác xuất báo cáo hoặc xử lý batch.
6. Số connection và thread, phạm vi giải phóng tài nguyên sau lỗi.

Một **giới hạn hàng đợi** bảo vệ hệ thống khỏi tích tụ vô hạn nhưng chưa đảm bảo đạt SLO về độ trễ. Nếu để quá nhiều yêu cầu chờ, người dùng có thể timeout trước khi tác vụ được xử lý.

## 6. Ví dụ Java 17: giới hạn công việc đang chờ

Xét một thành phần chạy tác vụ CPU-bound ngắn. Nếu dùng thread pool cùng hàng đợi không giới hạn, lúc tải tăng nhanh có thể giữ lại lượng lớn tác vụ và dữ liệu đính kèm, khiến bộ nhớ và độ trễ tăng. Một lựa chọn là **giới hạn số worker và hàng đợi**, đồng thời từ chối công việc khi không còn sức chứa.

### 6.1. Bộ thực thi có giới hạn

Ví dụ tệp `BoundedTaskRunner.java`:

```java
package com.example.performance;

import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BoundedTaskRunner implements AutoCloseable {
    private final ThreadPoolExecutor executor;

    public BoundedTaskRunner(int workerCount, int waitingCapacity) {
        if (workerCount <= 0 || waitingCapacity <= 0) {
            throw new IllegalArgumentException("pool sizes must be positive");
        }
        this.executor = new ThreadPoolExecutor(
                workerCount,
                workerCount,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(waitingCapacity),
                new ThreadPoolExecutor.AbortPolicy());
    }

    public void submit(Runnable task) {
        // Có thể ném RejectedExecutionException khi pool đã đầy/đã đóng.
        executor.execute(Objects.requireNonNull(task, "task"));
    }

    @Override
    public void close() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

**Hợp đồng của ví dụ:** số tác vụ đang chạy không vượt `workerCount` và số tác vụ đang chờ trong hàng đợi nội bộ không vượt `waitingCapacity`. Khi cả worker và hàng đợi đã đầy, `AbortPolicy` khiến lời gọi `submit` bị từ chối bằng `RejectedExecutionException` thay vì tiếp tục giữ tác vụ trong hàng đợi vô hạn.

`close()` cố dừng pool có kiểm soát; nếu còn tác vụ sau thời gian chờ, `shutdownNow()` gửi yêu cầu ngắt và trả về danh sách tác vụ chưa bắt đầu. **Nó không bảo đảm mọi tác vụ tự dừng ngay**: mã tác vụ phải xử lý interruption phù hợp. Khi đưa vào ứng dụng thật, cần quyết định cách ghi nhận và xử lý các tác vụ bị hủy hoặc chưa hoàn tất, không đơn giản coi chúng đã xử lý thành công.

### 6.2. JUnit 5 xác nhận giới hạn hoạt động

Một unit test không nên cố “chứng minh p99 dưới 200 ms” trên laptop hoặc CI chia sẻ tài nguyên. Nhưng nó có thể kiểm tra **thuộc tính chức năng** của cơ chế bảo vệ: hàng đợi đầy sẽ từ chối công việc.

Ví dụ tệp `BoundedTaskRunnerTest.java`:

```java
package com.example.performance;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import org.junit.jupiter.api.Test;

class BoundedTaskRunnerTest {
    @Test
    void rejectsWorkWhenWorkersAndQueueAreFull() throws Exception {
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try (BoundedTaskRunner runner = new BoundedTaskRunner(2, 2)) {
            try {
                // Hai tác vụ đang chạy, cố ý đợi lệnh giải phóng.
                for (int i = 0; i < 2; i++) {
                    runner.submit(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
                }
                assertTrue(started.await(5, SECONDS));

                // Hai tác vụ tiếp theo chiếm hết hai ô chờ.
                runner.submit(() -> {});
                runner.submit(() -> {});

                assertThrows(RejectedExecutionException.class,
                        () -> runner.submit(() -> {}));
            } finally {
                // Luôn giải phóng tác vụ dù assertion phía trên lỗi.
                release.countDown();
            }
        }
    }
}
```

Bài kiểm thử kiểm tra điều kiện **2 đang chạy + 2 chờ → tác vụ thứ 5 bị từ chối**, sử dụng latch để chủ động tạo trạng thái cần quan sát. Nó không kiểm tra mức RSS thực tế, không mô phỏng toàn bộ pipeline nhận HTTP request và không phải kiểm thử thông lượng. Nếu tầng HTTP đã nhận một request và `submit` bị từ chối, hệ thống còn cần **ánh xạ từ chối thành phản hồi rõ ràng**, quan sát metric và xử lý retry theo tính chất nghiệp vụ.

### 6.3. Đổi một giới hạn không đồng nghĩa đạt yêu cầu hiệu năng

Lựa chọn `workerCount = 2` và `waitingCapacity = 2` chỉ minh họa. Số worker thích hợp phụ thuộc tác vụ **CPU-bound hay I/O-bound**, lượng CPU cấp cho container, thời gian chờ phụ thuộc và số yêu cầu cùng tồn tại. Số ô chờ lớn có thể giảm từ chối ngắn hạn nhưng tăng thời gian chờ và bộ nhớ; số ô quá nhỏ có thể làm tỷ lệ từ chối tăng khi có burst hợp lệ.

Chính sách từ chối cần được kiểm tra cùng **thời gian phản hồi và tỷ lệ lỗi đã cam kết**. Đạt giới hạn bộ nhớ bằng cách từ chối phần lớn yêu cầu thì không phải đạt đồng thời các yêu cầu độ trễ, thông lượng và tính sẵn sàng.

## 7. Thiết kế thử tải để có bằng chứng đáng tin

Một bài thử có ý nghĩa phải mô phỏng được **mô hình công việc** thay vì chỉ lặp một endpoint với dữ liệu nhỏ nhất. Quy trình:

### Bước 1 — Mô tả kịch bản và nguồn kỳ vọng

Liệt kê các request có ý nghĩa, tỷ lệ giữa chúng, số mặt hàng trong đơn, trạng thái cache, dữ liệu trong database và những phụ thuộc sẽ tham gia. Xác định đầu vào không hợp lệ, timeout và số yêu cầu có thể bị từ chối khi vượt tải.

Nếu đang kiểm tra API báo giá, hãy có cả **đơn ít dòng**, **đơn nhiều dòng**, **đơn có ưu đãi phức tạp** và **đơn gần ngưỡng giảm giá**, với tỷ lệ sát tình huống sử dụng mục tiêu. Không dùng một request được cache sẵn rồi suy ra kết quả cho mọi trường hợp.

### Bước 2 — Cố định cấu hình môi trường

Ghi rõ JDK, số instance, giới hạn vCPU và bộ nhớ, tham số heap, cấu hình connection pool, phiên bản database, network và cấu hình sinh tải. Bộ sinh tải không được trở thành nút thắt cổ chai; cần theo dõi CPU, mạng và lỗi của chính nó.

### Bước 3 — Warm-up trước khi đo chính thức

JVM có thời gian khởi động, nạp lớp, JIT compilation và làm nóng cache. Đánh giá giai đoạn ổn định nên có warm-up được quy định riêng. Tuy nhiên, **startup performance** có thể là một yêu cầu độc lập, nhất là dịch vụ thường xuyên scale lên/xuống; đừng vô tình loại nó khỏi phạm vi nếu người dùng cần đo.

### Bước 4 — Sinh tải theo đúng kiểu cần kiểm chứng

Phân biệt:

- **Open workload:** tải được phát theo tốc độ đến định trước, ví dụ trung bình 300 request/s, không tự giảm chỉ vì server phản hồi chậm.
- **Closed workload:** một số client ảo cố định gửi yêu cầu mới sau khi yêu cầu trước hoàn tất; khi server chậm, tốc độ phát tải thường giảm theo.

Chọn sai mô hình có thể che giấu quá tải. Với yêu cầu “chịu 300 request đến mỗi giây”, dùng closed workload mà chỉ quan sát tốc độ đạt được khi hệ thống chậm có thể không kiểm chứng được mục tiêu thực sự. Cần kiểm tra hiện tượng **coordinated omission**: bộ sinh tải bỏ qua những thời điểm lẽ ra có request đến khi server chậm, làm phân bố độ trễ nhìn tốt hơn thực tế.

### Bước 5 — Đo đồng thời độ trễ, thông lượng, lỗi và tài nguyên

Không chỉ lưu một dòng “average = 70 ms”. Ít nhất, cần các đường thời gian cho arrival/completion rate, p50/p95/p99 theo cửa sổ, timeout/error/rejection, CPU, RSS/heap, GC, connection pool và queue depth. Ghi rõ cách công cụ xử lý request chưa hoàn tất khi cửa sổ đo kết thúc.

### Bước 6 — Thử tải ổn định, tăng tải và đỉnh tải

| Loại thử | Mục tiêu |
| --- | --- |
| **Baseline** | Xác nhận độ trễ và mức bộ nhớ ở tải thấp, kiểm tra tính đúng đắn công cụ đo |
| **Load test** | Kiểm tra đúng tải mục tiêu và thời lượng đã cam kết |
| **Stress test** | Tăng tải để tìm điểm suy giảm, cách từ chối và khả năng phục hồi |
| **Spike test** | Quan sát ứng xử khi tải tăng/giảm đột ngột |
| **Soak test** | Duy trì tải lâu hơn để tìm tích tụ, memory leak, queue growth hoặc suy giảm theo thời gian |

Không cần chạy mọi loại thử sau mỗi sửa một biến. Chọn theo rủi ro thay đổi, nhưng phải **nói rõ loại bằng chứng đang có và loại còn thiếu**.

### Bước 7 — Kết luận theo toàn bộ tiêu chí

Một báo cáo nên trả lời: có đạt p95 và p99 không; đạt bao nhiêu request hoàn tất/giây; có bao nhiêu lỗi/timeout; RSS và heap biến động thế nào; hàng đợi có ổn định không; CPU hoặc dependency nào là giới hạn; sau tải đỉnh có phục hồi không; và phép đo có thể tái hiện không.

Khi không đạt, cần phân loại theo bằng chứng: nút cổ chai CPU, wait/lock, I/O, network, GC, cache miss, pool saturation hoặc chiến lược retry. Đừng mặc định tăng số luồng hay thêm cache là giải pháp nếu chưa biết nguyên nhân.

## 8. Ví dụ mẫu báo cáo yêu cầu và kết quả

Bảng sau là **số liệu giả lập để luyện cách đọc**, hoàn toàn không phải kết quả đo của một dịch vụ đã chạy:

| Chỉ số | Mục tiêu | Kết quả giả lập | Đánh giá |
| --- | --- | --- | --- |
| Tải yêu cầu đến | 300 request/s | 300 request/s trong 30 phút | Đúng điều kiện tải |
| Thông lượng hoàn tất | Ít nhất 300 request/s trung bình | 298,8 request/s | **Chưa đạt** |
| Độ trễ p95 | Không quá 200 ms | 170 ms | Đạt riêng chỉ số này |
| Độ trễ p99 | Không quá 500 ms | 620 ms | **Chưa đạt** |
| Lỗi không mong đợi/timeout | Không quá 0,5% yêu cầu gửi | 0,4% | Đạt riêng chỉ số này |
| RSS tiến trình | Không quá 384 MiB | Đỉnh 410 MiB | **Chưa đạt** |
| Hàng đợi | Không có backlog tăng kéo dài | Tăng đều ở cuối phiên thử | **Chưa đạt** |

Trong ví dụ, p95 đạt không đủ để tuyên bố API đáp ứng yêu cầu. Độ trễ p99, thông lượng, RSS và backlog đều cho thấy rủi ro. Cũng cần đối chiếu cách đếm request đã hoàn tất và request còn treo ở cuối bài thử; không thể coi một bảng số giả lập là bằng chứng kỹ thuật nếu chưa có log, cấu hình và phương pháp đo đi kèm.

**Mẫu ghi nhận phép đo thực tế:**

```text
Chức năng: POST /quotes
Phiên bản mã và cấu hình: [ghi mã commit/JDK/container]
Thiết lập tải: [tốc độ đến, phân bố request, dữ liệu thử]
Khoảng warm-up: [thời gian]
Cửa sổ đo: [bắt đầu/kết thúc, múi giờ]

Độ trễ: [p50, p95, p99, timeout, cách tính]
Thông lượng: [đến, hoàn tất, thành công, bị từ chối]
Tài nguyên: [RSS/heap/GC/CPU/queue/connection]
Kết quả đúng chức năng: [số ca thành công/lỗi kỳ vọng]
Điều kiện chấp nhận: [đạt/chưa đạt từng tiêu chí]
Tệp bằng chứng: [log, biểu đồ, cấu hình bộ sinh tải]
Giới hạn: [điều kiện chưa thử hoặc phụ thuộc được giả lập]
```

## 9. Những đánh đổi cần được nêu rõ

| Phương án | Có thể cải thiện | Giá phải trả hoặc rủi ro |
| --- | --- | --- |
| Tăng số worker | Thông lượng nếu phần lớn thời gian là chờ I/O và còn tài nguyên | Tăng stack/thread, tranh chấp và áp lực dependency |
| Thêm cache | Giảm độ trễ đọc và tải DB | Tốn bộ nhớ, dữ liệu cũ, eviction khó dự đoán |
| Gộp xử lý theo batch | Giảm overhead từng bản ghi | Có thể tăng độ trễ của một mục và kích thước bộ nhớ tạm |
| Xử lý bất đồng bộ | Giảm thời gian chờ tại điểm nhận nếu hợp đồng chấp nhận kết quả chưa hoàn tất | Thêm hàng đợi, trạng thái, retry và đối soát |
| Hàng đợi có giới hạn | Ngăn tích tụ vô hạn và giúp backpressure | Tăng số yêu cầu bị từ chối khi tải vượt khả năng |
| Giảm cấp phát | Có thể giảm áp lực GC | Tăng độ phức tạp mã nếu tối ưu thủ công quá sớm |
| Thêm instance | Chia tải nếu kiến trúc hỗ trợ | Tăng chi phí, áp lực lên hệ thống phụ thuộc và độ phức tạp phối hợp |

**Không tối ưu chỉ một chỉ số mà bỏ điều kiện còn lại.** Ví dụ cache 1 GiB có thể đưa p95 xuống 80 ms nhưng không hợp lệ nếu container bị giới hạn 512 MiB. Tối ưu bộ nhớ bằng cách khóa toàn bộ xử lý trong một luồng có thể làm throughput tụt mạnh. Bản thân mức độ dễ hiểu và khả năng sửa đổi của mã cũng là chi phí cần cân nhắc.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao chưa đủ | Cách làm phù hợp |
| --- | --- | --- |
| “Trung bình 60 ms nghĩa là phần lớn người dùng đều nhanh.” | Một số request rất chậm có thể bị trung bình che khuất | Đo phân vị, timeout và lỗi |
| “300 request/s đã gửi nghĩa là server xử lý 300 request/s.” | Request có thể xếp hàng, lỗi hoặc bị từ chối | Báo cáo arrival, completed và success rate riêng |
| “`-Xmx256m` nghĩa là container chỉ dùng 256 MiB.” | Còn stack, metaspace, direct buffers, native memory | Đo cả RSS/container usage và heap |
| “p95 tốt thì không cần p99.” | Đuôi dài có thể gây timeout và trải nghiệm xấu | Chọn mục tiêu dựa vào rủi ro dịch vụ |
| “Unit test có `assertTimeout` là kiểm thử tải.” | Không tạo đủ workload hoặc đo sử dụng tài nguyên thật | Dùng load/stress test có môi trường và tải được mô tả |
| “Tăng worker chắc chắn tăng thông lượng.” | Có thể tăng contention, GC và nghẽn phụ thuộc | Đo bottleneck rồi điều chỉnh |
| “Chạy một lần đạt là đủ.” | Kết quả phụ thuộc warm-up, cache, máy sinh tải và môi trường | Lặp lại trong điều kiện có kiểm soát và lưu cấu hình |
| “Không bị OOM trong 5 phút là không rò rỉ bộ nhớ.” | Rò rỉ nhỏ chỉ lộ sau tải kéo dài | Soak test và quan sát bộ nhớ qua thời gian |
| “Từ chối nhiều request giúp p99 đẹp hơn nên đã tối ưu.” | Hy sinh tính sẵn sàng và throughput | Đánh giá các mục tiêu cùng lúc |
| “Tổng p95 của từng dependency bằng p95 end-to-end.” | Phân vị không cộng tuyến tính | Đo end-to-end trực tiếp |

## 11. Bài tập vận dụng

Một API tìm kiếm khóa học đang phục vụ 120 request/s. Nhóm muốn hỗ trợ **350 request/s** khi bắt đầu kỳ đăng ký. Dữ liệu: 80% yêu cầu tìm theo tên, 15% lọc theo nhiều điều kiện và 5% xuất danh sách lớn. Mỗi container có giới hạn 1 GiB RAM. Trong một lần đo thử trước đây, chỉ có giá trị trung bình 90 ms và nhận xét “CPU còn thấp”.

Hãy tự hoàn thành:

1. **Viết hợp đồng kiểm chứng:** đề xuất ngưỡng p95/p99, throughput thành công, error/timeout và RSS; nêu rõ 350 request/s là offered load hay completed throughput; chọn thời lượng đo và mô hình tải.
2. **Xác định ranh giới đo:** người dùng cần toàn bộ JSON hay chỉ thời gian tới byte đầu tiên? Xuất danh sách lớn có tính chung với tìm kiếm ngắn không? Nếu tách nhóm, phải giải thích mục tiêu riêng cho từng nhóm.
3. **Thiết kế tải:** mô phỏng phân bố 80/15/5, kích thước dữ liệu, cache nóng/lạnh, dữ liệu truy vấn và số người dùng đồng thời như thế nào?
4. **Ngân sách bộ nhớ:** đề xuất mức RSS tối đa so với container 1 GiB, cách giới hạn kết quả xuất lớn, hàng đợi, cache và số luồng; giải thích vì sao `-Xmx` không đủ.
5. **Kế hoạch đo:** xác định số liệu cần thu khi load test, spike test và soak test; nêu dấu hiệu hệ thống quá tải hoặc rò rỉ bộ nhớ.
6. **Diễn giải kết quả:** nếu p95 đạt 180 ms nhưng p99 là 2.000 ms, bộ nhớ tiến trình chạm giới hạn và 8% yêu cầu bị từ chối, có thể tuyên bố “đạt mục tiêu 350 request/s” không? Vì sao?

**Gợi ý tự đối chiếu:** mục tiêu phải chọn dựa trên yêu cầu sản phẩm, không có một ngưỡng p95 hay RSS đúng cho mọi hệ thống. Cần phân biệt tốc độ yêu cầu đến và tốc độ xử lý xong; với 5% yêu cầu xuất lớn, nên xác định tài nguyên và yêu cầu riêng hoặc công bố rõ cách chúng được tính trong chỉ số chung. Từ một kết quả trung bình 90 ms ở tải 120 request/s **không thể suy ra** dịch vụ đáp ứng 350 request/s. Nếu nhiều yêu cầu lỗi hoặc bộ nhớ vượt giới hạn, một p95 tốt chưa đủ để kết luận đạt.

## 12. Ghi nhớ

- **Độ trễ** cần định nghĩa ranh giới quan sát và phân vị (p95, p99), không chỉ trung bình.
- **Thông lượng** phải đo công việc hoàn tất, đi kèm offered load, tỷ lệ lỗi, hàng đợi và tải đỉnh.
- **Giới hạn bộ nhớ** phải rõ heap, RSS và container budget; quản lý hàng đợi, cache, payload và số tác vụ song song.
- **Yêu cầu có thể kiểm thử** phải ghi chức năng, workload, môi trường, thời lượng, ngưỡng, cách thu thập số liệu và hành vi khi quá tải.
- **Một kết quả xanh không chứng minh mọi tải đều an toàn**: thử tải cần có phạm vi, bằng chứng và những giới hạn được công bố.

Đặt yêu cầu hiệu năng là đặt **một hợp đồng về hành vi dưới tải và giới hạn tài nguyên**, chứ không phải chọn một con số “nhanh” tùy ý. Khi hợp đồng rõ, nhóm có cơ sở ưu tiên cải thiện, kiểm tra hồi quy và cân bằng hiệu năng với tính đúng đắn, độ dễ hiểu và khả năng thay đổi lâu dài.
