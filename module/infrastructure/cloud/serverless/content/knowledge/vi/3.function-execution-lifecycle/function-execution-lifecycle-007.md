# Hủy tác vụ, kết thúc tiến trình và công việc chạy nền

Trong ứng dụng serverless, một Java function thường được gọi để xử lý một HTTP request, một message hoặc một event. Có lúc người gọi đổi ý, invocation hết thời gian, một bước xử lý bị treo hoặc nền tảng cần thu hồi execution environment. Khi đó, ứng dụng phải biết dừng công việc đúng cách và xác định phần nào đã hoàn thành.

Ba việc thường bị nhầm lẫn là **hủy một tác vụ**, **kết thúc tiến trình JVM** và **kết thúc một invocation**. Chúng có phạm vi và hậu quả khác nhau. Hủy một Future không nhất thiết dừng được mọi thao tác bên dưới; handler trả về không có nghĩa một background thread được bảo đảm tiếp tục; còn kết thúc JVM có thể ảnh hưởng đến nhiều invocation hoặc tài nguyên dùng chung trong cùng execution environment.

Bài học này trình bày cách Java xử lý cancellation, interruption và shutdown, đồng thời chỉ ra cách tổ chức công việc nền bền vững trong môi trường FaaS.

## 1. Phân biệt task, invocation và execution environment

| Khái niệm | Phạm vi | Sự kiện kết thúc |
|---|---|---|
| Task (tác vụ) | Một đơn vị công việc trong ứng dụng, có thể chạy trên thread hoặc executor | Hoàn tất, lỗi hoặc được yêu cầu hủy |
| Invocation | Một lần nền tảng gọi function để xử lý request, message hoặc event | Handler trả kết quả, ném lỗi hoặc runtime kết thúc lần gọi |
| Execution environment | Môi trường chứa runtime, process và tài nguyên của function | Được nền tảng tái sử dụng, đóng băng, thu hồi hoặc khởi tạo lại |
| JVM process | Tiến trình Java đang chạy trong execution environment | JVM thoát hoặc bị hệ điều hành/nền tảng kết thúc |

Một execution environment có thể xử lý nhiều invocation trong các thời điểm khác nhau. Runtime có thể giữ process sống để tái sử dụng class đã nạp, kết nối và dữ liệu khởi tạo. Một số nền tảng hoặc cấu hình còn cho phép xử lý đồng thời. Vì vậy, không nên mặc định kết thúc một invocation đồng nghĩa với kết thúc JVM.

~~~mermaid
flowchart TD
    A["Execution environment được khởi tạo"] --> B["JVM và runtime sẵn sàng"]
    B --> C["Invocation bắt đầu"]
    C --> D["Handler xử lý request / message / event"]
    D --> E{"Kết quả invocation"}
    E -->|Trả kết quả| F["Invocation hoàn tất"]
    E -->|Ném lỗi / timeout| G["Invocation thất bại"]
    F --> H{"Nền tảng giữ environment?"}
    G --> H
    H -->|Có| I["Có thể tái sử dụng cho invocation sau"]
    I --> C
    H -->|Không| J["Environment bị thu hồi"]
    J --> K["Process kết thúc"]
~~~

Sơ đồ thể hiện một vòng đời khái quát. Chi tiết freeze, thaw, shutdown, concurrency và thời điểm thu hồi phụ thuộc nhà cung cấp cùng loại trigger.

## 2. Hủy tác vụ trong Java

### 2.1. Hủy là yêu cầu hợp tác

Java không thể tùy ý dừng một thread đang chạy ở bất kỳ lệnh nào một cách an toàn. Cơ chế chuẩn là yêu cầu thread dừng bằng interruption. Thread đang thực hiện phải kiểm tra trạng thái interrupt hoặc gọi API có hỗ trợ interruption, sau đó chủ động kết thúc.

**Thread.interrupt()** đặt cờ interrupt của thread đích. Nếu thread đang chờ trong một số thao tác như **sleep**, **wait** hoặc **join**, thao tác đó có thể ném **InterruptedException** và xóa cờ interrupt. Nếu thread đang chạy tính toán bình thường, nó thường chỉ nhận được cờ và phải tự kiểm tra.

Ví dụ, một vòng lặp xử lý theo từng record có thể kiểm tra cờ trước khi bắt đầu phần việc tiếp theo:

~~~java
void processRecords(Iterable<Record> records)
        throws InterruptedException {

    for (Record record : records) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Processing was cancelled");
        }

        processOne(record);
    }
}
~~~

**isInterrupted()** đọc cờ mà không xóa nó. Ngược lại, **Thread.interrupted()** kiểm tra thread hiện tại rồi xóa cờ. Nếu không có lý do rõ ràng để xóa, hãy ưu tiên **isInterrupted()** khi kiểm tra cancellation.

Một tác vụ dài nên kiểm tra interrupt ở các điểm có thể dừng an toàn, chẳng hạn giữa các batch hoặc trước một lời gọi tốn thời gian. Không nên chỉ kiểm tra một lần ở đầu hàm nếu phần còn lại có thể chạy rất lâu.

### 2.2. Xử lý InterruptedException đúng cách

Khi một API ném **InterruptedException**, thread thường đã bị xóa cờ interrupt. Có hai cách xử lý phổ biến:

- Truyền **InterruptedException** lên caller nếu chữ ký hàm cho phép, để tầng trên quyết định kết thúc tác vụ.
- Nếu không thể truyền tiếp, khôi phục cờ bằng **Thread.currentThread().interrupt()** rồi thoát hoặc chuyển thành exception của ứng dụng.

Ví dụ:

~~~java
try {
    waitForNextItem();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new ProcessingCancelledException(e);
}
~~~

Không nên bắt **InterruptedException** rồi bỏ qua để tiếp tục vòng lặp như không có gì xảy ra. Làm vậy có thể khiến hệ thống không dừng được dù đã gửi yêu cầu hủy.

Interruption cũng không bảo đảm đánh thức mọi thao tác I/O. Một số **InputStream** hoặc thư viện mạng có thể tiếp tục block. Hãy dùng connect/read/request timeout, API có hỗ trợ cancellation hoặc đóng tài nguyên tương ứng khi cần dừng. Đóng một stream dùng chung cần được phối hợp để tránh làm hỏng tác vụ khác.

### 2.3. Future.cancel và ExecutorService

**ExecutorService.submit()** trả về **Future**, cho phép theo dõi kết quả và yêu cầu hủy:

- **cancel(false)** yêu cầu hủy Future nhưng không gửi interrupt; nếu computation đã bắt đầu, nó có thể vẫn tiếp tục chạy dù Future đã được đánh dấu hủy.
- **cancel(true)** yêu cầu interrupt thread thực thi nếu tác vụ đã bắt đầu.
- **isCancelled()** cho biết Future đã được đánh dấu hủy.
- **isDone()** cho biết Future đã ở trạng thái kết thúc, bao gồm hoàn tất, lỗi hoặc bị hủy.

Lệnh **cancel(true)** vẫn là yêu cầu hợp tác. Nếu code bỏ qua interrupt hoặc đang mắc trong API không phản hồi interruption, công việc có thể chưa dừng ngay.

Ví dụ, một invocation có thể chờ một tác vụ con trong giới hạn thời gian còn lại:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
Future<Result> future = executor.submit(this::calculate);

try {
    return future.get(remainingMillis, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    future.cancel(true);
    throw new ProcessingTimeoutException(e);
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    throw new ProcessingCancelledException(e);
} finally {
    executor.shutdownNow();

    try {
        if (!executor.awaitTermination(200, TimeUnit.MILLISECONDS)) {
            logger.warn("Worker tasks did not stop within the grace period");
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là ví dụ cho executor thuộc riêng invocation. Trong ứng dụng thực tế, **remainingMillis** phải được tính từ deadline còn lại, không phải một timeout tùy ý dài hơn deadline của function. Tác vụ **calculate** cũng phải hỗ trợ interruption hoặc có timeout cho các lời gọi bên ngoài.

Nếu executor được chia sẻ ở phạm vi process để tái sử dụng, không được gọi **shutdownNow()** sau mỗi invocation vì sẽ dừng cả công việc của invocation khác. Khi dùng executor dùng chung, hãy quản lý Future theo từng invocation và chỉ hủy những tác vụ thuộc invocation đó. Việc khởi tạo pool dùng chung cần giới hạn thread, hàng đợi và concurrency.

### 2.4. Timeout không tự động có nghĩa là task đã dừng

**Future.get(timeout, unit)** chỉ giới hạn thời gian caller chờ kết quả. Khi hết thời gian, nó ném **TimeoutException**; task vẫn có thể đang chạy. Caller cần chủ động yêu cầu hủy và xác minh tác vụ có dừng hay không.

Tương tự, các API như **CompletableFuture.orTimeout()** làm cho future hoàn tất với lỗi timeout, nhưng không bảo đảm computation nền đã dừng. Với **CompletableFuture**, tham số **mayInterruptIfRunning** của **cancel** không phải cơ chế đáng tin cậy để interrupt computation đang chạy. Nếu cần dừng thread thực thi, hãy giữ handle **Future** từ executor hoặc thiết kế một cancellation signal mà tác vụ kiểm tra định kỳ.

Không nên báo trạng thái **CANCELLED** cho người dùng chỉ vì đã gửi yêu cầu cancel. Có thể cần các trạng thái riêng như **CANCEL_REQUESTED** và **CANCELLED**, trong đó **CANCELLED** chỉ được ghi khi worker đã dừng hoặc xác nhận không còn phần việc nào đang thực hiện.

## 3. Kết thúc invocation và kết thúc JVM

### 3.1. Handler trả về hoặc ném lỗi

Đối với function đồng bộ, handler trả về thường báo cho runtime rằng invocation đã hoàn tất và kết quả có thể được gửi lại cho caller. Nếu handler ném exception, runtime hoặc dịch vụ tích hợp xử lý lỗi theo loại trigger và cấu hình retry.

Đối với event hoặc message bất đồng bộ, hoàn tất thành công có thể khiến message được xác nhận hoặc event được coi là đã xử lý. Ném lỗi hoặc timeout có thể dẫn đến retry, redelivery hoặc chuyển sang dead-letter queue. Hành vi chính xác phụ thuộc dịch vụ nguồn, cấu hình và giao thức tích hợp.

Kết thúc invocation không nhất thiết kết thúc process. Runtime có thể tiếp tục giữ JVM để tái sử dụng cho lần gọi sau. Điều này có nghĩa biến static, thread pool, connection pool và file tạm có thể còn tồn tại sau khi handler trả về.

### 3.2. Không dùng System.exit trong handler

**System.exit(status)** yêu cầu JVM kết thúc. Nó không chỉ kết thúc hàm hiện tại. Nếu process đang phục vụ nhiều invocation hoặc giữ tài nguyên dùng chung, hành động này có thể làm gián đoạn công việc không liên quan. Nó cũng có thể khiến nền tảng khởi tạo execution environment mới và làm tăng cold start.

**Runtime.getRuntime().halt(status)** còn mạnh hơn: nó dừng JVM mà không chạy shutdown hook. Cả hai API đều không phải cách thông thường để báo một invocation thất bại.

Trong function handler, hãy trả kết quả khi thành công và ném exception phù hợp khi cần báo lỗi. Để runtime quản lý vòng đời process. Không gọi **System.exit()** để kết thúc một request, dừng một task hoặc yêu cầu retry.

### 3.3. Shutdown hook chỉ dành cho cleanup best-effort

Java cho phép đăng ký shutdown hook:

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    closeLocalResources();
}, "application-shutdown"));
~~~

Hook có thể được gọi khi JVM kết thúc theo cách cho phép shutdown hook chạy, chẳng hạn một số trường hợp gọi **System.exit()** hoặc tiến trình nhận tín hiệu kết thúc có thể xử lý. Tuy nhiên, hook không được bảo đảm chạy khi process bị kill cưỡng bức, máy chủ gặp sự cố, runtime hết thời gian grace period hoặc nền tảng thu hồi môi trường đột ngột.

Vì vậy, shutdown hook chỉ nên làm cleanup có giới hạn thời gian như đóng client, flush log hoặc giải phóng tài nguyên cục bộ. Không đặt công việc nghiệp vụ quan trọng, xác nhận thanh toán, ghi checkpoint duy nhất hoặc gửi message bắt buộc vào hook. Các thao tác đó phải hoàn tất và được xác nhận trong luồng xử lý bình thường.

Trong serverless, không nên đăng ký nhiều hook theo từng invocation. Hook gắn với vòng đời JVM, trong khi invocation có thể kết thúc và process vẫn tiếp tục sống. Nếu mỗi request tạo một hook mới, danh sách hook và trạng thái giữ lại có thể tăng qua thời gian.

## 4. Vì sao background thread sau khi handler trả về không đáng tin cậy?

Một mẫu dễ gây lỗi là khởi chạy thread rồi trả kết quả ngay:

~~~java
public Response handle(Request request) {
    executor.submit(() -> sendImportantNotification(request));
    return Response.accepted();
}
~~~

Đoạn mã này chỉ gửi công việc vào executor. Nó không chứng minh notification đã được gửi, cũng không bảo đảm thread tiếp tục chạy sau khi handler trả về.

Sau invocation, nền tảng có thể đóng băng execution environment, giới hạn CPU, tái sử dụng hoặc thu hồi process. Thread đang chạy có thể bị tạm dừng, không được chạy tiếp hoặc bị mất khi environment bị kết thúc. Một số nền tảng có hành vi cụ thể khác nhau, nhưng FaaS không cung cấp bảo đảm chung rằng công việc nền tách rời sẽ hoàn tất sau khi invocation kết thúc.

Ngay cả khi thread đôi khi tiếp tục chạy trong môi trường phát triển hoặc trong một số lần chạy production, đó không phải hợp đồng có thể dựa vào. Các lỗi khó tái hiện thường xuất hiện khi có cold start, tải cao, timeout hoặc scale-in.

Một tác vụ nền cũng có thể tạo race condition: handler trả về thành công nhưng tác vụ nền thất bại; invocation bị retry trong khi thread cũ vẫn chạy; hai worker cùng gửi notification hoặc cập nhật dữ liệu; hoặc execution environment bị tái sử dụng và trạng thái static cũ ảnh hưởng invocation mới.

**Quy tắc thiết kế:** mọi công việc cần được bảo đảm hoàn tất phải được chờ trong invocation hiện tại hoặc được bàn giao cho một cơ chế bền vững trước khi handler trả về.

## 5. Các cách tổ chức công việc chạy nền bền vững

### 5.1. Queue hoặc message broker

Function nhận request có thể ghi một message mô tả công việc vào queue rồi trả mã tiếp nhận cho client. Một function hoặc worker khác được kích hoạt để xử lý message.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API Function
    participant Q as Queue
    participant W as Worker Function
    participant D as Database
    C->>A: Gửi yêu cầu tạo job
    A->>D: Lưu job và trạng thái QUEUED
    A->>Q: Phát message chứa jobId
    A-->>C: Trả jobId và trạng thái tiếp nhận
    Q->>W: Kích hoạt worker
    W->>D: Đọc job và cập nhật RUNNING
    W->>D: Lưu kết quả và SUCCEEDED
~~~

Queue tạo ranh giới bền vững giữa việc tiếp nhận và xử lý. Tuy nhiên, cần thiết kế theo khả năng message được giao lại:

- Mỗi job có ID ổn định và idempotency key.
- Worker ghi nhận trạng thái trước và sau từng bước quan trọng.
- Message chỉ được xác nhận khi xử lý thành công theo giao thức của dịch vụ.
- Lỗi tạm thời có retry giới hạn và backoff.
- Lỗi kéo dài được chuyển đến dead-letter queue để điều tra.
- Worker xử lý message trùng mà không tạo hiệu ứng nghiệp vụ trùng.

Nếu việc lưu job trong database và gửi message không thể thực hiện trong cùng một transaction, có thể dùng transactional outbox. Request ghi job và bản ghi outbox trong cùng transaction; một publisher riêng đọc outbox và gửi message, sau đó đánh dấu đã phát. Cách này giảm nguy cơ lưu job thành công nhưng message bị mất do lỗi giữa hai thao tác.

### 5.2. Workflow orchestration

Với quy trình nhiều bước, có nhánh điều kiện, retry theo từng bước, chờ callback hoặc cần theo dõi trạng thái dài hạn, dùng workflow orchestration. Workflow lưu trạng thái tiến trình và điều phối các function theo định nghĩa.

Ví dụ, quy trình xử lý hồ sơ có thể gồm:

1. Kiểm tra dữ liệu đầu vào.
2. Lưu file lên object storage.
3. Gửi tác vụ phân tích.
4. Chờ kết quả từ dịch vụ khác.
5. Tổng hợp kết quả và ghi trạng thái hoàn tất.

Mỗi bước nên có timeout, retry policy và cách xử lý lỗi riêng. Không nên giữ một invocation sống chỉ để chờ nhiều phút hoặc nhiều giờ nếu workflow service có thể quản lý trạng thái chờ.

### 5.3. Dịch vụ job hoặc worker chuyên dụng

Nếu tác vụ cần chạy liên tục, giữ kết nối lâu, xử lý dữ liệu lớn hoặc có yêu cầu điều khiển tiến trình chi tiết, một worker/container hoặc dịch vụ job chuyên dụng có thể phù hợp hơn FaaS. Dịch vụ này cần có cơ chế giám sát, restart, giới hạn tài nguyên và lưu trạng thái riêng.

### 5.4. Lưu tham chiếu thay vì nhồi dữ liệu vào message

Với file lớn, lưu nội dung trong object storage rồi gửi message chứa object key, version, checksum và job ID. Worker đọc dữ liệu theo luồng và cập nhật checkpoint. Message nhỏ hơn, dễ retry và không phụ thuộc vào việc giữ dữ liệu lớn trong bộ nhớ invocation.

## 6. Thiết kế yêu cầu hủy cho job chạy dài

Hủy một job nghiệp vụ thường cần nhiều hơn **Thread.interrupt()**. Người dùng có thể yêu cầu hủy khi job đang ở queue, đang chạy hoặc đã hoàn tất. Hệ thống cần lưu trạng thái có thể quan sát được.

Một mô hình trạng thái đơn giản:

~~~text
QUEUED
  |
  v
RUNNING -------> SUCCEEDED
  |  \
  |   \--------> FAILED
  |
  v
CANCEL_REQUESTED
  |
  v
CANCELLED
~~~

Các trạng thái cần được cập nhật bằng thao tác có kiểm soát, chẳng hạn compare-and-set hoặc transaction, để hai worker không ghi đè trạng thái của nhau. **CANCEL_REQUESTED** thể hiện yêu cầu đã được ghi nhận; worker sẽ kiểm tra ở checkpoint tiếp theo. **CANCELLED** thể hiện công việc đã dừng an toàn.

Một luồng hủy điển hình:

1. Client gửi yêu cầu hủy với job ID.
2. API xác thực quyền sở hữu job và ghi **CANCEL_REQUESTED**.
3. Worker đang chạy đọc trạng thái ở checkpoint tiếp theo.
4. Worker dừng nhận phần việc mới, hoàn tất hoặc rollback phần đang xử lý nếu có thể.
5. Worker đóng tài nguyên, lưu checkpoint cuối và cập nhật **CANCELLED**.
6. Client truy vấn trạng thái để biết kết quả cuối cùng.

Nếu worker đang chờ một API bên ngoài, cần timeout hoặc API cancellation của dịch vụ đó. Nếu thao tác đã được dịch vụ ngoài chấp nhận, việc hủy phía Java không thể tự động đảo ngược hiệu ứng. Có thể cần một lệnh bù (compensation) như hủy đặt chỗ hoặc hoàn tiền, tùy nghiệp vụ.

Yêu cầu hủy có thể đến đồng thời với lúc job hoàn tất. Hãy định nghĩa rõ quy tắc thắng: nếu transaction ghi **SUCCEEDED** đã commit trước, API hủy nên trả trạng thái đã hoàn tất; nếu **CANCEL_REQUESTED** được ghi trước khi bước tiếp theo bắt đầu, worker nên dừng tại checkpoint. Tránh để client nhận **CANCELLED** trong khi một side effect vẫn đang diễn ra.

### 6.1. Cancellation token ở tầng ứng dụng

Với một quy trình có nhiều bước, có thể truyền một đối tượng kiểm tra trạng thái hủy. Ví dụ dưới đây minh họa giao diện đơn giản; phần đọc trạng thái từ database hoặc cache cần được triển khai với timeout và cơ chế nhất quán phù hợp:

~~~java
interface CancellationCheck {
    boolean isCancellationRequested();
}

void processJob(Job job, CancellationCheck cancellation)
        throws InterruptedException {

    for (WorkItem item : job.items()) {
        if (Thread.currentThread().isInterrupted()
                || cancellation.isCancellationRequested()) {
            throw new InterruptedException("Job cancellation requested");
        }

        processOne(item);
        saveCheckpoint(job.id(), item.id());
    }
}
~~~

Không cần truy vấn database cho mỗi record nếu chi phí quá cao. Có thể kiểm tra theo batch hoặc tại các checkpoint, cân bằng giữa độ trễ hủy và chi phí đọc trạng thái. Nếu dùng cache, hãy xác định độ trễ nhất quán và thời gian tối đa để worker nhận được yêu cầu.

## 7. Lưu ý theo loại trigger

| Trigger | Ý nghĩa khi handler kết thúc | Cách xử lý cancellation và lỗi |
|---|---|---|
| HTTP đồng bộ | Runtime trả response hoặc lỗi cho caller | Client ngắt kết nối không bảo đảm invocation bị hủy; dùng deadline và API hủy job riêng nếu công việc dài |
| Queue/message | Message có thể được xác nhận khi xử lý thành công | Chỉ xác nhận theo đúng giao thức sau khi hoàn tất; retry phải idempotent; kiểm tra trạng thái hủy tại checkpoint |
| Event bất đồng bộ | Event được coi là đã xử lý hoặc thất bại theo kết quả invocation | Cấu hình retry, thời hạn và DLQ; event có thể lặp hoặc đến trễ |
| Scheduled trigger | Một lần chạy theo lịch được khởi tạo | Dùng job ID theo kỳ chạy, chống chạy trùng và lưu trạng thái để điều phối lần chạy tiếp theo |

Với HTTP, việc trình duyệt đóng tab hoặc client timeout không đồng nghĩa server đã dừng công việc. Nếu cần cho phép người dùng hủy, API nên tạo job ID và cung cấp endpoint yêu cầu hủy/truy vấn trạng thái. Không dùng việc client đóng socket làm nguồn sự thật về cancellation.

Với queue, đừng xóa hoặc xác nhận message chỉ vì đã bắt đầu xử lý. Nếu worker bị dừng trước khi xác nhận, message có thể được giao lại. Điều này an toàn khi job có idempotency và checkpoint. Nếu dịch vụ hỗ trợ partial batch response, có thể chỉ báo lỗi các record chưa xử lý thành công.

Với event bất đồng bộ, không phải lúc nào cũng có một caller đang chờ để gửi tín hiệu hủy. Nếu nghiệp vụ cần hủy, hãy phát một cancellation event hoặc cập nhật trạng thái job. Worker xử lý event đó như một yêu cầu nghiệp vụ có xác thực.

## 8. Dọn dẹp tài nguyên khi task hoặc invocation kết thúc

Dù kết thúc bình thường hay bị hủy, ứng dụng cần giải phóng tài nguyên mà nó sở hữu:

- Đóng stream, file, socket và connection trong try-with-resources hoặc finally.
- Dừng tác vụ con thuộc invocation và chờ trong khoảng grace period hợp lý.
- Không đóng pool hoặc client dùng chung khi invocation khác còn sử dụng.
- Xóa file tạm khi hoàn tất; không coi /tmp là nơi lưu trạng thái bền vững.
- Đảm bảo transaction được commit hoặc rollback theo quy tắc nghiệp vụ.
- Ghi checkpoint trước khi trả lỗi nếu việc tiếp tục xử lý cần thông tin đó.
- Không dựa vào shutdown hook để hoàn tất công việc bắt buộc.

Cleanup cũng có thể bị timeout hoặc interruption. Vì vậy, các bước cleanup cần ngắn, có giới hạn thời gian và có thể chạy lại an toàn. Nếu việc dọn dẹp phải được bảo đảm, ghi một trạng thái cần xử lý và giao cho worker khác thay vì giữ invocation quá lâu.

## 9. Quan sát và kiểm thử cancellation

Một hệ thống có cancellation cần cho người vận hành biết yêu cầu đã được nhận, worker đã nhìn thấy nó và công việc đã dừng ở đâu. Các thông tin hữu ích gồm:

- Job ID, invocation/request ID và correlation ID.
- Trạng thái job cùng thời điểm chuyển trạng thái.
- Thời điểm nhận yêu cầu hủy và thời điểm worker xác nhận.
- Số checkpoint đã hoàn thành và phần việc còn lại.
- Số lần retry, số lần giao lại và nguyên nhân lỗi.
- Thời gian dừng task sau khi nhận interrupt.
- Tác vụ con hoặc connection chưa kết thúc khi invocation sắp hết deadline.

Nên kiểm thử các tình huống sau:

1. Hủy task trước khi executor bắt đầu chạy.
2. Hủy khi task đang tính toán và kiểm tra interrupt định kỳ.
3. Hủy khi task đang block trong I/O.
4. Hết timeout của Future.get() nhưng computation vẫn còn chạy.
5. Invocation bị timeout sau khi dịch vụ ngoài đã nhận lệnh.
6. Process kết thúc đột ngột trước khi shutdown hook chạy.
7. Worker nhận lại cùng message sau một lần xử lý dở dang.
8. Yêu cầu hủy đến đúng lúc job chuyển sang SUCCEEDED.
9. Hai invocation đồng thời cùng thử cập nhật trạng thái job.
10. Execution environment được tái sử dụng và executor/static state còn tồn tại.

Log nên ghi sự kiện và mã định danh, không ghi toàn bộ payload hoặc dữ liệu nhạy cảm. Dùng metric để theo dõi tỷ lệ job bị hủy, thời gian từ CANCEL_REQUESTED đến CANCELLED, số tác vụ không dừng đúng hạn và số message bị retry.

## 10. Quy tắc lựa chọn

- **Task ngắn nằm trong invocation:** chạy và chờ hoàn tất; nếu có task con, giới hạn concurrency và hỗ trợ interruption.
- **Task có thể vượt deadline của function:** lưu trạng thái và chuyển sang queue hoặc workflow.
- **Cần hủy theo yêu cầu người dùng:** dùng job ID, trạng thái bền vững và checkpoint; interruption là cơ chế dừng worker ở cấp thread.
- **Cần cleanup khi JVM đóng:** dùng shutdown hook cho thao tác best-effort, có giới hạn thời gian.
- **Cần bảo đảm công việc hoàn tất:** không để nó chạy tách rời sau khi handler trả về; bàn giao cho dịch vụ bền vững.
- **Cần dừng cả process:** để nền tảng quản lý vòng đời; không gọi System.exit() từ handler để xử lý một request.

## 11. Câu hỏi tự kiểm tra

- Thread.interrupt() có trực tiếp giết thread đang chạy không?
- Vì sao Future.get(timeout) ném TimeoutException nhưng task có thể vẫn tiếp tục?
- CompletableFuture.orTimeout() có bảo đảm dừng computation nền không?
- Handler trả về thì execution environment và JVM có nhất thiết kết thúc không?
- Vì sao System.exit() nguy hiểm trong function runtime có thể được tái sử dụng?
- Shutdown hook có thể được dùng để ghi kết quả nghiệp vụ cuối cùng không?
- Cách nào phù hợp để người dùng hủy một job kéo dài qua nhiều invocation?
- Vì sao queue worker phải idempotent khi message có thể được giao lại?

Hiểu rõ ranh giới giữa task, invocation và process giúp thiết kế cancellation có thể dự đoán. Trong FaaS, công việc cần được bảo đảm hoàn tất phải có trạng thái bền vững, cơ chế retry và điểm tiếp tục rõ ràng; thread nền chỉ nên phục vụ phần việc có phạm vi và thời gian sống được kiểm soát trong invocation.

