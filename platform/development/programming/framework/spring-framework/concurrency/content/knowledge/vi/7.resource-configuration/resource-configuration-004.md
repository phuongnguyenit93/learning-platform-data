# Chọn sức chứa hàng đợi theo bộ nhớ và thời gian chờ cho phép

## 1. Vì sao kích thước hàng đợi là quyết định về tài nguyên?

Trong một ứng dụng Spring, nhiều yêu cầu có thể cùng gửi công việc tới `ThreadPoolTaskExecutor`: tính toán báo cáo, gọi hệ thống ngoài, xử lý ảnh, ghi nhận sự kiện hoặc cập nhật dữ liệu. Khi tất cả worker đang bận, tác vụ mới có thể phải **đợi trong hàng đợi** trước khi được một worker lấy ra xử lý.

Giới hạn hàng đợi (`queue capacity`) trả lời câu hỏi: **cho phép bao nhiêu tác vụ đang chờ trong bộ nhớ của tiến trình?** Đây không phải số worker và cũng không phải thời gian được phép chờ.

Chọn hàng đợi quá lớn có thể khiến:
- Nhiều `Runnable`/`Callable`, `Future` và đối tượng bị chúng giữ tham chiếu tồn tại lâu trong heap, làm tăng áp lực GC hoặc gây `OutOfMemoryError`.
- Tác vụ mới nhận được thông báo đã gửi thành công nhưng phải đợi quá lâu mới bắt đầu chạy, đến khi chạy thì dữ liệu có thể hết hạn.
- Việc quá tải bị che giấu: hàng đợi tiếp tục nhận việc dù hệ thống không xử lý kịp.
- Thời gian dừng/redeploy và việc thu hồi, hủy các tác vụ chưa chạy trở nên khó kiểm soát.

Chọn hàng đợi quá nhỏ cũng có chi phí: một đợt tăng tải ngắn có thể gây từ chối nhiều tác vụ mặc dù hệ thống có thể xử lý chúng ngay sau đó. Vì vậy kích thước tốt không phải “càng lớn càng an toàn” hay “luôn đặt bằng 0”, mà là điểm cân bằng có thể **đo, giải thích và kiểm chứng**.

Bài này hướng dẫn chọn một giới hạn ban đầu từ **ngân sách bộ nhớ** và **ngân sách thời gian đợi**, hiểu tương tác giữa hàng đợi với số worker của Spring, rồi kiểm tra bằng tải thực tế.

## 2. Mô hình: worker, tác vụ đang chờ và tổng thời gian

Một tác vụ được gửi đến bộ thực thi có thể đi qua các giai đoạn:

```text
Người gọi gửi công việc
         |
         v
      execute() / submit()
         |
         v
  Còn worker có thể nhận ngay? ---- Có ---> Đang chạy (active)
         |
         | Không
         v
  Còn chỗ chờ trong queue? ------- Có ---> Đang xếp hàng (queued)
         |                                      |
         |                                      v
         |                                Worker rảnh -> chạy
         v
  Cơ chế pool có thể tăng worker? -- Có ---> Tăng worker, chạy
         |
         | Không
         v
      TỪ CHỐI (rejected)
```

Sơ đồ này giúp hình dung, nhưng quy tắc **thực tế của `ThreadPoolExecutor`** chi tiết hơn và được giải thích ở mục 3.

Phân biệt các số liệu:

| Thuật ngữ | Ký hiệu | Ý nghĩa |
|---|---|---|
| Số tác vụ đang chạy | `A` | Tác vụ đã được worker nhận và chưa xong |
| Số tác vụ đang chờ | `Q_current` | Tác vụ hiện nằm trong work queue |
| Sức chứa hàng đợi | `Q_capacity` | Giới hạn số tác vụ được xếp hàng |
| Số worker có thể chạy | `c` | Mức đồng thời của pool tại thời điểm xét |
| Thời gian chờ trước khi chạy | `Wq` | Từ lúc tác vụ được nhận đến lúc worker bắt đầu thực thi |
| Thời gian thực thi | `S` | Từ lúc worker bắt đầu đến khi tác vụ kết thúc |
| Thời gian trong hệ thống thực thi | `T` | Xấp xỉ `Wq + S`, chưa tính xử lý trước/sau của người gọi |
| Tốc độ gửi | `λ` | Số tác vụ đến mỗi giây, cần phân biệt gửi vào và được chấp nhận |
| Tốc độ hoàn thành | `μ` | Số tác vụ hoàn thành mỗi giây ở tải đo được |

**`Q_capacity = 100` nghĩa là tối đa 100 tác vụ chờ, không phải 100 tác vụ chạy đồng thời, cũng không phải 100 MB.** Hệ thống có thể đồng thời chứa tác vụ đang chạy, tác vụ nằm trong queue và những dữ liệu được giữ ở tầng HTTP/message broker phía trước.

Đối với một yêu cầu có mục tiêu phản hồi trong 500 ms, thời gian dành cho queue có thể chỉ là 100 ms sau khi trừ thời gian gọi cơ sở dữ liệu, xử lý nghiệp vụ, truyền mạng và các bước khác. Không nên dùng toàn bộ hạn mức độ trễ cho `Wq`.

## 3. ThreadPoolExecutor xử lý queue trước khi tăng đến maxPoolSize

`ThreadPoolTaskExecutor` của Spring dựa trên `java.util.concurrent.ThreadPoolExecutor`. Ba cấu hình quan trọng là:

- `corePoolSize`: số worker lõi mà pool cố gắng tạo khi nhận công việc (theo quy tắc tạo worker).
- `maxPoolSize`: giới hạn số worker tối đa.
- `queueCapacity`: số tác vụ có thể chờ trong work queue.

Quy tắc của `ThreadPoolExecutor.execute(...)` ở điều kiện bình thường:

1. Khi số worker ít hơn `corePoolSize`, pool ưu tiên tạo một worker mới để nhận việc.
2. Khi đã đạt mức lõi, pool **ưu tiên đưa việc vào hàng đợi**.
3. Chỉ khi việc **không thể vào queue** mới thử tăng số worker lên tới `maxPoolSize`.
4. Nếu pool không thể nhận việc qua cả worker lẫn queue, `RejectedExecutionHandler` quyết định cách từ chối/xử lý.

Ví dụ cấu hình `corePoolSize=4`, `maxPoolSize=8`, `queueCapacity=20`:

```text
Các task đầu -> tạo tới 4 worker lõi
4 worker bận -> những task tiếp theo chờ (tối đa 20 vị trí)
Queue đầy -> pool mới có thể tăng worker thứ 5 ... thứ 8
8 worker bận + queue đầy -> từ chối hoặc dùng chính sách từ chối
```

Đây là **sơ đồ trạng thái lý tưởng khi task đủ lâu để pool đang tải**. Trong thực tế, worker có thể hoàn tất và lấy việc khỏi queue ngay khi tác vụ khác gửi vào, nên không thể chỉ nhìn số thứ tự task để suy ra chính xác kết quả.

### 3.1. Queue rất lớn làm maxPoolSize gần như không có tác dụng

Nếu queue có sức chứa cực lớn, pool gần như luôn xếp hàng sau khi đạt `corePoolSize`. `maxPoolSize` sẽ không được dùng để tăng số worker trong điều kiện thông thường vì queue chưa đầy.

Đặc biệt, `ThreadPoolTaskExecutor` **khi không được cấu hình riêng** có giá trị mặc định trong Spring Framework là `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE` và `queueCapacity=Integer.MAX_VALUE`. Đó là mặc định của **chính lớp Spring này**; cấu hình tự động của một phiên bản Spring Boot cụ thể có thể khác và cần xem cấu hình hiệu lực. Không nên dựa vào giá trị mặc định khi triển khai hệ thống có yêu cầu tải/độ trễ.

**Kết luận kỹ thuật:** Tăng `maxPoolSize` mà không hiểu `queueCapacity` có thể không làm tăng số worker trong lúc tải cao. Hãy kiểm tra quy tắc xếp hàng trước khi điều chỉnh số luồng.

### 3.2. queueCapacity=0 khác với queueCapacity dương

Trong `ThreadPoolTaskExecutor`:

| `queueCapacity` | Loại queue được tạo | Tác động |
|---|---|---|
| Giá trị dương, ví dụ `16` | `LinkedBlockingQueue` có giới hạn tương ứng | Cho phép tối đa 16 tác vụ chờ |
| `0` | `SynchronousQueue` | Không lưu tác vụ trong hàng đợi; chuyển trực tiếp cho worker hoặc thử tạo worker khác |
| Giá trị cực lớn/mặc định | `LinkedBlockingQueue` có giới hạn rất lớn về mặt số nguyên | Có nguy cơ tích lũy nhiều công việc trong heap trước khi đạt giới hạn đếm |

`SynchronousQueue` không lưu task và không phải queue có một vị trí. Với `queueCapacity=0`, nếu mọi worker đã bận và không thể tạo worker mới, việc bị từ chối theo policy; mức `maxPoolSize` hữu hạn là thiết yếu để kiểm soát tài nguyên. Không đặt `maxPoolSize` không giới hạn một cách vô thức chỉ vì không dùng queue.

`queueCapacity` thường cần được đặt **trước khi executor được khởi tạo**. Thay property trên bean đã chạy không có nghĩa underlying queue tự được thay bằng queue có dung lượng khác.

## 4. Ràng buộc thứ nhất: mỗi tác vụ đang chờ chiếm bao nhiêu bộ nhớ?

Một phần tử queue không chỉ là con trỏ tới tác vụ. Nó giữ tham chiếu tới một `Runnable`, đối tượng `FutureTask` hoặc wrapper của framework. Tác vụ có thể giữ cả một đồ thị đối tượng (`object graph`):

- Lambda/callback capture `request`, `byte[]` chứa ảnh hoặc file, danh sách bản ghi, JSON parse tree.
- Đối tượng `Future`, ngữ cảnh, metadata, dữ liệu tạo bởi `TaskDecorator` và closure liên quan.
- Các tham số, collection, cache tạm hoặc tham chiếu tới bean, tài liệu, dữ liệu của cả request.
- Cấu trúc nội bộ của queue, ví dụ nút của `LinkedBlockingQueue`, cộng với phần quản lý của executor.

Ví dụ:

```java
byte[] payload = loadPayload();
executor.execute(() -> process(payload));
```

Mã trên **chỉ là đoạn minh họa**, với `loadPayload()`/`process(...)` là phương thức ứng dụng. Lambda giữ tham chiếu tới `payload`; nếu công việc chờ lâu, mảng vẫn có thể được giữ sống dù request đã trả về. Một queue đếm 1.000 phần tử có thể rất nhẹ nếu mỗi task nhỏ, hoặc rất nặng nếu mỗi task giữ mảng nhiều MB.

Không thể lấy kích thước mã lambda hoặc kích thước reference (4/8 byte) để suy ra tổng bộ nhớ. Cần ước lượng **bộ nhớ còn được giữ lại do việc xếp hàng** (`retained heap`), bao gồm đối tượng chỉ còn sống nhờ task. Dùng profiling/heap dump hoặc đo mức tiêu thụ heap với tải đại diện; tránh cộng trùng các đối tượng được nhiều task chia sẻ.

### 4.1. Lập ngân sách heap thực tế

Đặt:

- `M_queue`: số byte heap **được phép dành cho những task đang xếp hàng**, sau khi trừ tải nền, dữ liệu của tác vụ đang chạy, các cache và khoảng dự phòng GC.
- `B_task`: ước lượng bảo thủ số byte heap bị giữ bởi **một tác vụ đang chờ**, gồm wrapper, queue node và dữ liệu được giữ tham chiếu.
- `Q_memory`: giới hạn queue tính từ ngân sách bộ nhớ.

Công thức sơ bộ:

\[
Q_{\text{memory}} = \left\lfloor \frac{M_{\text{queue}}}{B_{\text{task}}} \right\rfloor
\]

Ví dụ dành 20 MiB heap cho queue và giả định **mỗi tác vụ giữ tối đa khoảng 96 KiB trong mô hình thử nghiệm**:

\[
Q_{\text{memory}} =
\left\lfloor \frac{20 \times 1024}{96} \right\rfloor
= 213\ \text{tác vụ}
\]

Đây chỉ là **giới hạn theo bộ nhớ**, chưa trả lời liệu chờ 213 tác vụ có chấp nhận được hay không. Trong production, `B_task` biến thiên; nên đo đạc ở nhiều payload, lấy cận trên thực tế cùng hệ số dự phòng. Một giá trị trung bình hoặc p95 không phải cận trên tuyệt đối và không đảm bảo sẽ không có task lớn bất thường.

Ngân sách queue còn phải tách khỏi bộ nhớ cho: task đang chạy, thread stacks (chủ yếu ngoài Java heap), connection, buffer trực tiếp (`direct buffer`), cache, response đang trả và các bộ phận khác. Đừng gán toàn bộ `-Xmx` cho hàng đợi.

### 4.2. Giảm dữ liệu bị task giữ lại

Nếu task chỉ cần một ID, thay vì capture cả một request/DTO lớn, có thể capture ID bất biến và tải dữ liệu cần thiết tại nơi thực thi (cân nhắc thêm chi phí I/O và khả năng dữ liệu thay đổi). Không giữ `HttpServletRequest`, stream đang mở hay object có vòng đời request trong queue dài.

Các cách tối ưu khác là đưa payload lớn vào vùng lưu trữ thích hợp và chỉ queue một reference có độ bền, chia lô theo kích thước kiểm soát được, hoặc loại bỏ dữ liệu tạm trước khi submit. Khi nhiệm vụ phải tồn tại qua restart, queue trong heap vốn không phải giải pháp lưu công việc bền vững.

## 5. Ràng buộc thứ hai: tác vụ được phép chờ bao lâu?

Ngân sách độ trễ của hàng đợi `Wq_budget` cần được suy ra từ yêu cầu người dùng/nguồn gọi:

```text
Thời hạn đầu-cuối của yêu cầu
  - chi phí tạo/nhận yêu cầu
  - thời gian thực thi nghiệp vụ dự kiến (đặc biệt p95/p99)
  - thời gian trả kết quả/đường truyền
  - khoảng dự phòng
= ngân sách tối đa dành cho queue wait
```

Nếu end-to-end SLO là 600 ms, worker có thể phải dùng 350 ms ở phân vị cao, các giai đoạn khác mất 100 ms và cần dự phòng 50 ms, thì queue wait chỉ có ngân sách khoảng 100 ms. Dồn 500 ms để đợi queue sẽ làm mục tiêu 600 ms trở nên khó đạt.

Một phép tính **gần đúng để tìm ứng viên cấu hình**:

\[
Q_{\text{time}} \approx
\left\lfloor \mu_{\text{effective}} \times W_{q,\text{budget}}\right\rfloor
\]

Trong đó `μ_effective` là **tốc độ tác vụ thực tế có thể bắt đầu/hoàn thành** ở điều kiện tải và cấu hình worker được đo, tính theo task/giây. Nếu pool đang bận và xử lý ổn định, một queue có `Q` công việc phía trước cần khoảng `Q / μ_effective` giây để được giải phóng; phải cộng tác động của tác vụ đang chạy, độ dao động thời gian xử lý và lịch thực thi.

Ví dụ tốc độ hoàn thành có thể duy trì khoảng **80 tác vụ/giây**, và ứng dụng chỉ cho phép **0,20 giây** chờ:

\[
Q_{\text{time}} \approx \lfloor 80 \times 0.20 \rfloor = 16
\]

Con số 16 là **điểm bắt đầu để thử tải**, không phải cam kết mọi task đều bắt đầu trong 200 ms. Với workload có job rất dài, phân phối không đồng đều, GC pause hoặc downstream chậm bất thường, ngay cả queue ngắn vẫn có thể vượt ngân sách.

### 5.1. Đừng nhầm với định luật Little

Với hệ thống ổn định xét trên khoảng thời gian đủ dài, định luật Little cho **giá trị trung bình**:

\[
L_q = \lambda_{\text{accepted}} \times \overline{W_q}
\]

Trong đó `Lq` là số task trung bình trong queue, `λ_accepted` là thông lượng task được **nhận thực sự** (và hoàn thành ở trạng thái ổn định), còn `Wq_bar` là thời gian chờ **trung bình**. Phương trình này giúp đối chiếu số liệu đo: nếu thông lượng 80 task/s và trung bình chờ 0,1 s thì có trung bình khoảng 8 task đang chờ.

**Không thể lấy định luật Little làm bảo đảm cho p95/p99 hoặc thời gian chờ tối đa.** Nó không cho biết tail latency, và phép dùng trạng thái ổn định không thể che giấu việc queue đang tăng vô hạn trong tình huống đầu vào vượt năng lực phục vụ.

Nếu yêu cầu là “99% task bắt đầu trong 200 ms”, phải đo trực tiếp `p99 queue wait` với tải đại diện, không chỉ tính bằng tốc độ trung bình.

## 6. Cách gộp hai ngân sách để chọn giới hạn ban đầu

Với một loại tác vụ tương đối đồng nhất, cách khởi đầu có thể kiểm toán:

\[
Q_{\text{candidate}} =
\max\left(0,\;
\min(Q_{\text{memory}}, Q_{\text{time}})\right)
\]

Nếu có một khoảng dự phòng riêng, có thể chọn **nhỏ hơn** `Q_candidate` và dùng thử tải để điều chỉnh. Công thức này không biến queue thành cơ chế bảo đảm SLO; nó chỉ tránh chọn một con số vượt quá một trong hai ngân sách ngay từ bước thiết kế.

Lấy cùng bộ dữ liệu ví dụ:

| Đại lượng | Giá trị giả định |
|---|---:|
| Bộ nhớ heap dành cho tác vụ đang chờ | 20 MiB |
| Bộ nhớ mỗi task queued (ước lượng có dự phòng) | 96 KiB |
| Giới hạn theo bộ nhớ | 213 task |
| Tốc độ hoàn tất đo được của pool | 80 task/s |
| Ngân sách chờ queue | 200 ms |
| Giới hạn theo thời gian | 16 task |
| **Ứng viên `queueCapacity`** | **16 task** |

**Giới hạn đang quyết định là độ trễ, không phải bộ nhớ.** Nếu đặt queue 213 chỉ vì heap còn chỗ, thì ở tốc độ 80 task/s, việc đứng sau khoảng 213 task có thể phải chờ cỡ 2,66 giây trong mô hình đơn giản, vượt 200 ms rất xa.

Ngược lại, nếu mỗi task giữ 2 MiB và chỉ dành 20 MiB heap cho queue thì giới hạn bộ nhớ khoảng 10 task, dù thời gian chờ cho phép 16. Khi đó chọn 10 hoặc ít hơn, rồi quyết định cách từ chối/giảm tải.

### 6.1. Ví dụ Java 17 tính hai giới hạn

**Tệp `QueueBudgetDemo.java` — chương trình độc lập, không cần Spring**

```java
public class QueueBudgetDemo {
    public static void main(String[] args) {
        long budgetBytes = 20L * 1024 * 1024;
        long estimatedBytesPerQueuedTask = 96L * 1024;

        double measuredThroughputPerSecond = 80.0;
        double queueWaitBudgetSeconds = 0.20;

        long byMemory = budgetBytes / estimatedBytesPerQueuedTask;
        long byTime = (long) Math.floor(
                measuredThroughputPerSecond * queueWaitBudgetSeconds);

        long initialCapacity = Math.max(0L,
                Math.min(byMemory, byTime));

        System.out.println("Giới hạn theo bộ nhớ: " + byMemory);
        System.out.println("Giới hạn theo thời gian: " + byTime);
        System.out.println("Ứng viên cấu hình: " + initialCapacity);
    }
}
```

```bash
javac QueueBudgetDemo.java
java QueueBudgetDemo
```

Đầu ra xác định:

```text
Giới hạn theo bộ nhớ: 213
Giới hạn theo thời gian: 16
Ứng viên cấu hình: 16
```

Chương trình cho thấy cách tính, **không đo heap hoặc tốc độ hệ thống thay cho bạn**. Các đầu vào trong code là giả định để luyện tập; production cần thay bằng dữ liệu đo được.

## 7. Điều gì xảy ra khi tải đầu vào cao hơn năng lực xử lý?

Gọi `λ_in` là tốc độ task đến và `μ_effective` là tốc độ pool phục vụ ổn định.

- Nếu `λ_in` thường thấp hơn năng lực phục vụ, queue có cơ hội trở về mức thấp sau mỗi đợt tăng tải.
- Nếu `λ_in` liên tục lớn hơn năng lực phục vụ, lượng công việc chờ có xu hướng tăng khoảng `λ_in - μ_effective` task/giây cho đến khi chạm giới hạn và xảy ra từ chối, chặn caller hoặc chính sách khác.
- Nếu tốc độ trung bình gần năng lực tối đa, thời gian chờ vẫn có thể tăng mạnh do dao động thời gian xử lý, đợt đến theo cụm và tranh chấp tài nguyên.

Ví dụ đầu vào duy trì **120 task/giây**, pool chỉ hoàn tất được **80 task/giây**: dư khoảng **40 task/giây**. Nếu worker đã bận và queue đang trống, queue 16 sẽ đầy sau cỡ **0,4 giây** trong mô hình liên tục đơn giản. Queue 160 chỉ dời thời điểm quá tải ra khoảng 4 giây, **không tăng thông lượng thực của pool**.

Đây là lập luận tốc độ chênh lệch để hiểu tình trạng quá tải, không phải dự báo thời gian đầy chính xác cho pool có thể mở rộng từ core tới max, nhiều loại job, hay nguồn đến biến thiên. Trong thực tế phải đo `μ_effective` theo cấu hình và tải thật.

**Giải pháp cho quá tải kéo dài:** giảm lưu lượng, áp dụng giới hạn đồng thời ở đầu vào, điều chỉnh tác vụ, tăng năng lực xử lý nếu tài nguyên cho phép, hoặc chuyển công việc sang hàng đợi bền vững. Chỉ tăng queue không giải quyết sự mất cân bằng dài hạn.

### 7.1. Một đợt tăng tải ngắn khác quá tải kéo dài

Giả sử pool có 8 worker đang rảnh và đồng thời nhận 20 tác vụ, mỗi tác vụ chạy đủ lâu để không kết thúc ngay. Tối đa 8 tác vụ có thể chạy sớm trên 8 worker; phần còn lại có thể đợi hoặc được chuyển cho worker mở rộng tùy `core/max/queue`. Queue 16 có thể hấp thụ một phần đợt tăng, nhưng điều đó không chứng minh nó xử lý được **mọi** burst 20 task với mức `p99 Wq` mong muốn.

Cần đo cả **biên độ burst** (bao nhiêu task đến dồn), **thời lượng burst**, **khoảng nghỉ để queue thoát tải**, và **tương quan giữa thời gian chạy task**. Một đợt tăng 5 giây và một đợt tăng 5 phút không tương đương về ngân sách.

## 8. Áp dụng vào ThreadPoolTaskExecutor của Spring

Cấu hình minh họa dùng `corePoolSize=8`, `maxPoolSize=12`, `queueCapacity=16`. Đây là **một ứng viên để kiểm thử**, không phải cấu hình tiêu chuẩn đúng cho mọi hệ thống.

**Tệp `AsyncExecutorConfig.java` — cấu hình Spring, cần dependency Spring Framework và ApplicationContext**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfig {

    @Bean("boundedTaskExecutor")
    public ThreadPoolTaskExecutor boundedTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("bounded-worker-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        return executor;
    }
}
```

Giải thích:

1. `corePoolSize=8` cho pool khả năng mở rộng tới 8 worker lõi khi có nhu cầu.
2. `maxPoolSize=12` cho phép tối đa 12 worker (không phải luôn duy trì đủ 12).
3. `queueCapacity=16` đặt giới hạn cho **tác vụ đang chờ** trong `LinkedBlockingQueue`.
4. Khi core worker bận, queue được sử dụng trước; chỉ khi queue không nhận thêm việc thì pool thử tạo worker thứ 9–12.
5. `AbortPolicy` cho phép người gọi nhận biết tình trạng từ chối. Spring có thể biểu diễn trường hợp này bằng `TaskRejectedException` qua giao diện `TaskExecutor`.

Phương thức `@Bean` trả về object để **Spring quản lý vòng đời**; ở cách đăng ký bean thông thường, Spring gọi phương thức khởi tạo cần thiết cho executor. Không cần gọi `initialize()` thủ công từ phương thức bean khi bean lifecycle được quản lý đúng. Nếu tự `new ThreadPoolTaskExecutor()` ở ngoài container thì phải tự xử lý khởi tạo và đóng.

Ví dụ một service dùng executor đã đăng ký:

**Tệp `ReportService.java` — thành phần Spring, không có `main` độc lập**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("boundedTaskExecutor")
    public CompletableFuture<String> buildReport(String reportId) {
        String result = "Đã tạo báo cáo " + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
```

Phương thức cần được gọi **qua Spring proxy** từ một bean khác thì `@Async` mới đưa công việc sang executor trong cấu hình proxy phổ biến. Gọi `this.buildReport(...)` nội bộ thường bỏ qua proxy. Một lệnh `@Async` có thể bị từ chối ngay khi gửi nếu pool đầy; caller phải có chính sách xử lý.

Không viết test dựa vào thứ tự in log của các task bất đồng bộ; lịch chạy phụ thuộc thực thi. Các class Spring trên là mã cấu hình/thành phần để ghép vào ứng dụng Spring phù hợp, **không phải** chương trình Java SE thuần chỉ cần `javac`.

## 9. Java 17: thí nghiệm queue đầy và từ chối có kết quả xác định

Để thấy rõ ý nghĩa `queueCapacity` mà không cần server Spring, dùng `ThreadPoolExecutor` Java chuẩn với **1 worker** và queue chứa **2** tác vụ. Chúng ta giữ task đầu tiên ở một `CountDownLatch`; vì vậy hai tác vụ tiếp theo chắc chắn chờ trong queue khi kiểm tra.

**Tệp `BoundedQueueDemo.java` — chương trình Java 17 độc lập**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedQueueDemo {
    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch allowWorkerFinish = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    allowWorkerFinish.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();

            pool.execute(() -> {});
            pool.execute(() -> {});
            System.out.println("Đang xếp hàng: "
                    + pool.getQueue().size());

            try {
                pool.execute(() -> {});
                System.out.println("Không mong đợi: nhận task thứ tư");
            } catch (RejectedExecutionException rejected) {
                System.out.println("Tác vụ thứ tư bị từ chối");
            }

            System.out.println("Hàng đợi sau từ chối: "
                    + pool.getQueue().size());
        } finally {
            allowWorkerFinish.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

```bash
javac BoundedQueueDemo.java
java BoundedQueueDemo
```

Đầu ra xác định (không phụ thuộc thứ tự worker thực thi các task chờ):

```text
Đang xếp hàng: 2
Tác vụ thứ tư bị từ chối
Hàng đợi sau từ chối: 2
```

Tại sao kết quả chắc chắn?

- `workerStarted.await()` bảo đảm tác vụ đầu tiên đã vào worker.
- Worker đầu tiên chặn ở `allowWorkerFinish.await()` **trước khi** chúng ta gửi task thứ hai và thứ ba.
- Pool có tối đa một worker, vì vậy hai task tiếp theo chỉ có thể đợi trong queue dung lượng 2.
- Task thứ tư bị từ chối bởi `AbortPolicy` vì worker đang bận và queue đã đầy.
- Chỉ trong `finally` mới giải phóng latch, cho worker hoàn tất và xử lý các task chờ; `shutdown()`/`awaitTermination(...)` giúp chương trình thoát có kiểm soát.

Trong production, `getQueue().size()` chỉ là snapshot tại thời điểm gọi và có thể thay đổi ngay. Thí nghiệm có kết quả cố định nhờ latch, không có nghĩa mọi hệ thống luôn chính xác theo thứ tự task 1/2/3/4 dưới tải cạnh tranh.

Cũng lưu ý: ví dụ dùng `ArrayBlockingQueue` của Java để trình diễn khái niệm. Spring `ThreadPoolTaskExecutor` với `queueCapacity > 0` dùng `LinkedBlockingQueue`; hai queue đều có giới hạn đếm nhưng khác cấu trúc nội bộ, chi phí bộ nhớ và đặc tính hiệu năng.

## 10. Khi queue đầy: phải có chính sách backpressure

Chọn `queueCapacity` hữu hạn nghĩa là **công khai thừa nhận hệ thống có giới hạn**. Cần xác định người gọi thấy gì khi không thể nhận việc.

Một số `RejectedExecutionHandler` của `ThreadPoolExecutor`:

| Chính sách | Hành vi khi quá tải | Hệ quả cần cân nhắc |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Phản hồi rõ ràng, cho tầng trên quyết định từ chối/điều tiết |
| `CallerRunsPolicy` | Khi executor chưa shutdown, caller tự chạy task trên luồng gửi | Tạo áp lực ngược vì caller chậm lại; có thể chặn HTTP/request thread |
| `DiscardPolicy` | Bỏ task bị từ chối mà không ném lỗi | Rủi ro mất công việc âm thầm |
| `DiscardOldestPolicy` | Bỏ phần tử đầu queue rồi thử gửi task mới | Có thể mất tác vụ cũ và phá trật tự nghiệp vụ |

`CallerRunsPolicy` có thể phù hợp khi caller **được phép chặn** và hệ thống chấp nhận áp lực ngược. Nhưng trong request thread cần đáp ứng nhanh, thực thi tác vụ nặng trên caller có thể gây timeout; khi executor đã shutdown, policy này cũng có thể bỏ tác vụ thay vì chạy nó. Không nên coi `CallerRunsPolicy` là lời giải phổ quát.

Một luồng xử lý lỗi có thể là:

```text
Pool đầy / từ chối
        |
        v
Đây là công việc mất được hay phải bảo đảm?
        |
        +-- Mất được --> báo metrics/log theo chính sách, không "nuốt" âm thầm
        |
        +-- Phải bảo đảm --> đưa vào hệ thống lưu trữ bền vững phù hợp,
        |                   hoặc trả lỗi có thể retry an toàn
        |
        +-- Người gọi đồng bộ --> trả tín hiệu quá tải rõ ràng
                              (ví dụ HTTP 429 hoặc 503 theo hợp đồng API)
```

Chính sách retry phải có giới hạn, khoảng dãn và tránh đồng loạt gửi lại; task có tác động bên ngoài cần idempotency để không thực hiện trùng khi timeout/retry. Retry liên tục trong cùng pool đang đầy chỉ làm tăng mức quá tải.

**Hàng đợi bị giới hạn là nơi bắt đầu kiểm soát tải, không thay thế rate limiting, bulkhead, circuit breaker, timeout hay hàng đợi bền vững** nếu bài toán cần những cơ chế đó.

## 11. Đừng dùng thời gian chờ của Future để thay thế giới hạn queue

Người gọi có thể đặt:

```java
result.get(200, TimeUnit.MILLISECONDS);
```

Đây là đoạn mã minh họa khi `result` là `Future<T>`. `get(timeout)` giới hạn **thời gian luồng gọi chờ kết quả**, không đặt giới hạn thời gian một task được giữ trong executor queue.

Nếu `get(...)` hết hạn, task có thể vẫn đang xếp hàng hoặc đang chạy; lời gọi không tự động xóa task khỏi queue. `cancel(true)` chỉ là yêu cầu hủy/ngắt theo hợp đồng, và việc loại bỏ ngay task đã hủy khỏi underlying queue phụ thuộc cơ chế executor/task wrapper.

Do đó, nếu nội dung chỉ còn giá trị tới một hạn chót, tác vụ nên nhận deadline rõ ràng và kiểm tra khi bắt đầu chạy. Nếu tác vụ quá hạn, nên tránh thực hiện side effect không còn hợp lệ. Khi hủy, phải giám sát tỷ lệ hủy và khả năng queue còn giữ các wrapper chưa được dọn.

Một hệ thống có `Wq_budget=200 ms` không nên chỉ đơn giản đặt `Future.get(200 ms)` rồi kết luận “queue đáp ứng SLO”; điều đó chỉ thay thời gian chờ của caller và có thể để lại công việc nền không còn cần thiết.

## 12. Hai loại giới hạn đi cùng nhau: pool, queue, downstream

Giả sử pool có `maxPoolSize=12` và `queueCapacity=16`. Tại một thời điểm, executor có thể giữ tối đa khoảng 12 tác vụ đang chạy và 16 tác vụ chờ (chưa kể công việc của các tầng khác). Nhưng **số luồng lớn hơn không tự bảo đảm thông lượng cao hơn**.

Với tác vụ CPU-bound, vượt số lõi hữu dụng có thể tăng chuyển ngữ cảnh và tranh chấp CPU, khiến `S` lớn hơn. Với I/O-bound, thêm worker có thể tăng mức đồng thời nhưng cũng có thể làm cạn connection pool, DB hoặc quota của dịch vụ ngoài. Khi downstream bị nghẽn, `μ_effective` có thể **giảm** dù tăng `maxPoolSize`.

Xem xét các tài nguyên liên quan:

- CPU cores, thời gian xử lý từng task và mức sử dụng CPU.
- Bộ nhớ heap cho queue và task đang chạy, cùng bộ nhớ native cho thread stacks.
- Số connection DB, HTTP connection, connection timeout và quota API.
- Thread pool khác của HTTP server, scheduler hoặc message consumer.
- Hàng đợi ở broker, reverse proxy, servlet request và chính executor. Các hàng đợi nối tiếp sẽ cộng dồn độ trễ.
- Độ trễ mạng/GC pause có thể làm p99 tệ hơn giá trị trung bình rất nhiều.

Nếu database pool chỉ có 8 connection mà 50 worker cùng chờ DB, tăng `maxPoolSize` từ 12 lên 50 có thể chỉ tạo thêm hàng chờ **ở connection pool**. Việc chọn queue phải căn cứ vào cả năng lực xử lý cuối chuỗi, không chỉ số worker trong một bean.

## 13. Đo queue wait thay vì chỉ đo queue size

Không có một con số `queueCapacity` tốt cho mọi lưu lượng. Khi chạy thử tải, tối thiểu theo dõi:

| Chỉ số | Câu hỏi nó giúp trả lời |
|---|---|
| `queue.size` hiện tại và mức đỉnh | Có thường xuyên chạm giới hạn không? |
| `activeCount`, `poolSize`, `maxPoolSize` | Có bao nhiêu worker đang phục vụ và khả năng tăng thêm ra sao? |
| Thời gian chờ task p50/p95/p99 | Task có bắt đầu trong ngân sách không? |
| Thời gian thực thi task p50/p95/p99 | Nút thắt là queue hay bản thân công việc? |
| Throughput hoàn thành và tốc độ gửi | Có đang tích lũy công việc hay không? |
| Số task từ chối / tỷ lệ rejection | Hệ thống đã vượt giới hạn ở đâu? |
| Heap, GC pauses, retained size theo payload | Queue có đang giữ quá nhiều đối tượng? |
| Timeout, canceled, deadline-expired | Bao nhiêu việc trở nên vô ích vì chờ lâu? |

`ThreadPoolTaskExecutor` cung cấp các phương thức theo dõi như `getActiveCount()`, `getPoolSize()` và `getThreadPoolExecutor()` (sau khởi tạo); underlying executor có `getQueue().size()` và các bộ đếm liên quan. Những số liệu này là quan sát theo thời điểm, không phải snapshot nguyên tử của mọi phần hệ thống.

**Đo queue wait đúng cách:** ghi timestamp (đơn điệu, ví dụ `System.nanoTime()`) lúc task được nhận/gửi và timestamp khi nó **thực sự bắt đầu chạy**, tính hiệu số. Đừng dùng thời gian từ khi nhận HTTP request làm queue wait nếu giữa request và submit còn các bước khác. Với task bị từ chối, phải ghi riêng vì nó chưa có thời điểm bắt đầu.

Trong Spring có thể dùng `TaskDecorator` để trang trí `Runnable` và đo thời gian đến lúc chạy, nhưng phải hiểu rằng task truyền tới decorator có thể là wrapper của framework (đặc biệt khi `submit`); không suy luận việc bắt ngoại lệ ở wrapper sẽ thấy mọi lỗi của task. Lỗi từ `Future` cần được quan sát qua cơ chế phù hợp.

### 13.1. Mẫu kiểm chứng tải

1. Chạy ở tải thấp để đo thời gian xử lý và mức giữ heap khi queue gần như rỗng.
2. Tạo burst ngắn để đo queue đạt đỉnh và thời gian thoát queue.
3. Giữ tải gần ngưỡng năng lực để quan sát p95/p99 queue wait, GC và số worker.
4. Tạo quá tải kéo dài có kiểm soát để xác nhận rejection policy và đường xử lý phía caller.
5. Tăng kích thước payload và thời gian I/O để kiểm chứng ước lượng `B_task` và `μ_effective`.
6. Kiểm thử hủy, shutdown, redeploy và tác vụ có side effect; không để công việc vô ích chiếm chỗ vô hạn.

Mỗi lần chỉ nên đổi một nhóm tham số có quan hệ rõ ràng (ví dụ queue và giới hạn luồng sau khi đã đo), so sánh p99 và lỗi, không chỉ thông lượng trung bình.

## 14. Những sai lầm phổ biến khi quyết định queueCapacity

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Đặt hàng đợi rất lớn “cho khỏi từ chối task” | Chỉ dời quá tải sang heap và thời gian chờ | Đặt ngân sách memory/time rồi xử lý rejection |
| Chỉ tính số phần tử mà quên payload bị capture | Một task có thể giữ cả request hoặc mảng lớn | Profile retained heap của task thực tế |
| Dùng `-Xmx` làm toàn bộ ngân sách queue | Heap còn cần GC headroom, cache, task đang chạy | Phân bổ `M_queue` sau các tải khác |
| Dùng Little's law để cam kết p99 | Quan hệ là trung bình ở trạng thái ổn định | Đo p99 queue wait trực tiếp |
| Tăng `maxPoolSize` nhưng queue gần như vô hạn | Pool ưu tiên queue sau core, không tăng thêm worker | Cấu hình queue có giới hạn phù hợp |
| Dùng `queueCapacity=0` nhưng không giới hạn `maxPoolSize` | Có thể tạo nhiều luồng khi tải tăng | Đặt max và chính sách từ chối rõ ràng |
| Không dự liệu việc task bị từ chối | Task quan trọng có thể mất hoặc caller lỗi | Thiết kế backpressure, lỗi, retry/idempotency |
| Dùng `CallerRunsPolicy` mà nghĩ luôn bất đồng bộ | Task có thể chạy ngay trên request thread | Cân nhắc hợp đồng độ trễ và trường hợp shutdown |
| Chỉ đo queue size trung bình | Không thấy burst, p99 và task chờ quá hạn | Đo đỉnh queue, thời gian chờ, rejection, GC |
| Tăng queue khi downstream đã quá tải | Không tạo thêm năng lực phục vụ | Tìm bottleneck, giới hạn đầu vào |
| Dùng queue nội bộ cho công việc phải sống qua restart | Queue trong heap không bền vững | Dùng hệ thống lưu công việc phù hợp |
| Chọn cấu hình một lần rồi bỏ mặc | Tải và kích thước task đổi theo thời gian | Theo dõi, thử tải và hiệu chỉnh có kiểm soát |

## 15. Bài tập thực hành

**Bài 1 — Tính hai ngân sách.** Một pool có ngân sách queue 12 MiB, task giữ khoảng 64 KiB, tốc độ xử lý đo được 50 task/s và thời gian đợi cho phép 0,2 s. Tính `Q_memory`, `Q_time` và ứng viên queueCapacity. Vì sao chỉ chọn theo bộ nhớ sẽ nguy hiểm?

**Đáp án định hướng:** `Q_memory = floor(12×1024/64)=192`; `Q_time=floor(50×0,2)=10`; ứng viên tối đa 10 trong mô hình đơn giản. Phải đo p95/p99 và để dự phòng.

**Bài 2 — Max pool có tăng không?** Pool có `corePoolSize=2`, `maxPoolSize=10`, queue gần như vô hạn, và 100 tác vụ dài được gửi dồn. Giải thích tại sao phần lớn tác vụ có thể xếp hàng và pool không tự nhảy lên 10 worker.

**Đáp án định hướng:** Sau khi có hai worker lõi, `ThreadPoolExecutor` ưu tiên queue; khi queue chưa đầy, không có lý do theo thuật toán để tăng worker trên core.

**Bài 3 — Phân tích p99.** QueueCapacity là 16 và throughput đo được 80 task/s. Có thể khẳng định 99% task không bao giờ chờ hơn 200 ms không? Đưa ra ít nhất ba nguyên nhân khiến kết luận sai.

**Đáp án định hướng:** Không. Thời gian task dao động, worker đang bận, GC, I/O chậm, burst, thay đổi throughput hoặc các queue khác đều làm p99 khác phép ước lượng trung bình.

**Bài 4 — Chạy thí nghiệm Java 17.** Biên dịch `BoundedQueueDemo.java`, thay queue 2 bằng 3 nhưng vẫn gửi bốn task. Dự đoán khi nào rejection xảy ra nếu thêm task thứ năm trong lúc worker còn chờ latch.

**Đáp án định hướng:** Với 1 worker và queue 3, task 2/3/4 được xếp hàng, task thứ năm bị từ chối trong điều kiện worker vẫn chặn.

**Bài 5 — Điều chỉnh cho workload lớn.** Task mới giữ thêm ảnh 2 MiB trong closure. Nếu vẫn cho phép queue 1000 phần tử, rủi ro là gì? Đề xuất một cách giảm retained heap và một cách kiểm soát mất việc khi queue đầy.

**Đáp án định hướng:** Queue có thể giữ cỡ vài GiB dữ liệu từ ảnh trước khi tính overhead; chỉ truyền ID hoặc reference bền vững, giới hạn queue và dùng xử lý từ chối có tín hiệu/đường lưu công việc thích hợp.

**Bài 6 — Kịch bản phụ thuộc tài nguyên.** Task cần một connection DB, nhưng pool DB chỉ cho phép 8 connection trong khi executor có 40 worker. Nếu p99 tăng, nên tăng queueCapacity ngay không? Giải thích điều cần đo trước.

**Đáp án định hướng:** Không tự động. Cần đo thời gian chờ connection, throughput của DB, active workers và Wq; queue lớn chỉ che giấu nút thắt nếu DB đã bão hòa.

## 16. Quy trình quyết định cấu hình trong dự án

Áp dụng sáu bước theo thứ tự:

1. **Xác định hợp đồng:** task có phải hoàn tất nhanh, có được từ chối, có deadline, có bắt buộc thực hiện dù restart hay không.
2. **Đo độ lớn và thời gian:** phân phối retained bytes của một task chờ; phân phối thời gian xử lý trên worker; tốc độ gửi và các đợt burst.
3. **Chia ngân sách:** giới hạn heap cho queue sau khi dành chỗ cho các thành phần khác, và giới hạn queue wait lấy từ SLO.
4. **Tính ứng viên:** `min(Q_memory, Q_time)`, xem xét hệ số an toàn và nhu cầu chịu burst. Nếu cần buffer lớn hơn giới hạn thời gian, phải thay đổi thiết kế/cách tiếp nhận công việc hoặc thỏa thuận SLO, không tự tăng queue.
5. **Cấu hình đồng bộ:** `corePoolSize`, `maxPoolSize`, `queueCapacity` và chính sách rejection phải phù hợp cùng nhau; xem cả downstream.
6. **Kiểm thử và theo dõi:** p95/p99 queue wait, queue depth, rejection, heap/GC, timeouts và thời gian phục hồi sau burst; điều chỉnh theo chứng cứ.

Có thể ghi nhớ quy tắc: **hàng đợi là ngân sách cho công việc đang chờ, không phải nguồn năng lực xử lý.** Chọn dung lượng từ khả năng giữ trong bộ nhớ **và** thời gian chờ chấp nhận được, sau đó kiểm chứng dưới tải thật.

### Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE 17 Javadoc — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 Javadoc — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html)
