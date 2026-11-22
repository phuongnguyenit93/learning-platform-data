# Tránh chặn luồng giao diện hoặc giữ yêu cầu quá lâu

Một ứng dụng MVC có thể phản hồi chậm dù từng thành phần hoạt động đúng: trình duyệt bận chạy JavaScript, Controller giữ request trong lúc chờ dịch vụ khác, thread pool cạn, truy vấn cơ sở dữ liệu kéo dài hoặc một tác vụ báo cáo chiếm tài nguyên quá lâu. Khi nhiều request cùng gặp tình trạng đó, độ trễ tăng nhanh và ứng dụng có thể ngừng phục vụ cả những thao tác đơn giản.

Cần phân biệt hai vấn đề liên quan nhưng khác nhau. **Chặn luồng giao diện** khiến người dùng không thể tương tác hoặc nhìn thấy cập nhật kịp thời. **Giữ request quá lâu** khiến tài nguyên phía máy chủ và kết nối bị chiếm dụng, đồng thời làm người dùng phải chờ lâu. Bất đồng bộ có thể giúp giải phóng một luồng trong lúc chờ I/O, nhưng không tự làm công việc nặng chạy nhanh hơn. Thiết kế tốt cần chọn đúng cách xử lý cho từng loại công việc, đặt giới hạn thời gian và mức đồng thời, đồng thời đo được nơi phát sinh độ trễ.

Bài học này trình bày cách nhận diện điểm nghẽn ở trình duyệt và máy chủ, tổ chức xử lý đồng bộ/bất đồng bộ trong MVC, chuyển tác vụ dài sang nền, kiểm soát timeout và backpressure, cũng như đo lường và kiểm thử hiệu năng.

Các ví dụ Java sử dụng Spring MVC và Servlet stack; import, DTO và service phụ trợ có thể được lược bỏ để tập trung vào cơ chế. Các con số cấu hình chỉ để minh họa, cần điều chỉnh bằng số liệu tải thực tế.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt chặn luồng giao diện với request xử lý lâu ở máy chủ.
- Giải thích event loop của trình duyệt và thread-per-request trong Spring MVC.
- Nhận biết khi nào nên dùng xử lý đồng bộ, async request hoặc background job.
- Sử dụng Callable, DeferredResult và StreamingResponseBody đúng mục đích.
- Thiết kế timeout, cancellation, giới hạn đồng thời và hàng đợi có giới hạn.
- Tránh giữ transaction hoặc connection trong thời gian dài.
- Bảo vệ giao diện trước thao tác lặp, request cũ và kết quả đến sai thứ tự.
- Đo latency, queue time, throughput và mức sử dụng tài nguyên để tìm điểm nghẽn.

## 2. Hai loại chặn cần phân biệt

### 2.1. Chặn luồng giao diện

Trong trình duyệt, JavaScript chạy trên main thread cùng với nhiều công việc giao diện như xử lý sự kiện, tính toán style, layout và paint. Nếu một đoạn JavaScript đồng bộ chiếm CPU quá lâu, trình duyệt không thể xử lý kịp sự kiện đầu vào hoặc vẽ lại màn hình.

Ví dụ:

- Tính toán một tập dữ liệu lớn ngay trong event handler.
- Render hàng chục nghìn phần tử DOM cùng lúc.
- Parse một tệp JSON rất lớn trên main thread.
- Chạy vòng lặp không có điểm nhường quyền.
- Xử lý ảnh hoặc mã hóa dữ liệu nặng trong luồng giao diện.

Người dùng có thể thấy trang bị đứng, nút bấm không phản hồi hoặc thanh tiến trình không cập nhật dù request chưa gửi đi.

### 2.2. Giữ request quá lâu ở máy chủ

Trong mô hình Servlet MVC phổ biến, một request được xử lý trên một servlet thread trong thời gian handler thực hiện công việc đồng bộ. Nếu handler chờ cơ sở dữ liệu, HTTP client hoặc một tác vụ tính toán, thread đó vẫn bị chiếm dụng.

Ví dụ:

- Controller gọi dịch vụ thanh toán mất 8 giây.
- Báo cáo chạy truy vấn lớn và tổng hợp dữ liệu trong 30 giây.
- Request giữ transaction trong lúc chờ một API bên ngoài.
- Một endpoint tải tệp lớn và giữ worker trong toàn bộ thời gian truyền.
- Request chờ trong hàng đợi vì thread pool đã bận.

Khi số request đồng thời tăng, thread pool có thể hết worker. Request mới phải chờ, bị từ chối hoặc timeout. Đây là hiện tượng cạn kiệt tài nguyên; độ trễ thường tăng nhanh và phi tuyến khi hệ thống tiến gần giới hạn phục vụ.

### 2.3. Độ trễ không đồng nghĩa với thời gian CPU

Một request mất 5 giây có thể chỉ dùng CPU 100 mili giây và dành phần lớn thời gian để chờ I/O. Ngược lại, một tác vụ mất 2 giây có thể tiêu thụ gần như toàn bộ CPU trong suốt thời gian đó.

Cần biết công việc đang:

- Chờ I/O: database, HTTP, file, lock hoặc queue.
- Dùng CPU: tính toán, mã hóa, nén, chuyển đổi dữ liệu.
- Chờ tài nguyên: thread pool, connection pool, semaphore hoặc giới hạn dịch vụ.
- Chờ người dùng hoặc một sự kiện bên ngoài.

Loại công việc quyết định cách tối ưu. Chuyển một tác vụ CPU-bound sang một executor khác có thể giữ main thread hoặc servlet thread rảnh, nhưng tổng lượng CPU cần thiết vẫn không đổi.

## 3. Vòng đời tương tác và request trong MVC

Một ứng dụng web có ít nhất hai vòng xử lý: event loop của trình duyệt và vòng xử lý request của máy chủ.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Main as Browser Main Thread
    participant Server as Spring MVC
    participant Worker as Servlet Worker
    participant DB as Database / API

    User->>Main: Nhấn nút
    Main->>Browser: Gửi fetch bất đồng bộ
    Browser->>Server: HTTP request
    Server->>Worker: Giao request cho worker
    Worker->>DB: Chờ truy vấn hoặc dịch vụ
    Note over Main: Main thread tiếp tục xử lý input và render
    DB-->>Worker: Kết quả
    Worker-->>Browser: HTTP response
    Browser-->>Main: Promise được tiếp tục
    Main-->>User: Cập nhật giao diện
~~~

Khi dùng fetch, trình duyệt không phải chờ phản hồi mạng trong một lời gọi đồng bộ trên main thread. Tuy nhiên, callback hoặc phần xử lý dữ liệu sau khi nhận response vẫn chạy trên main thread trừ khi được chuyển sang Web Worker hoặc cơ chế khác.

Việc đọc và parse một response JSON rất lớn cũng có thể tiêu tốn CPU trên main thread. Phân trang hoặc giới hạn payload trước; chỉ chuyển bước parse/tính toán sang worker khi đo đạc cho thấy chi phí đó đáng kể.

Ở phía máy chủ, một request có thể vẫn giữ servlet worker trong lúc chờ I/O. Vì thế, giao diện bất đồng bộ không tự giải quyết tình trạng thread pool phía server bị chiếm dụng.

## 4. Chọn cách xử lý theo loại công việc

Không nên chuyển tất cả endpoint thành bất đồng bộ. Xử lý đồng bộ vẫn phù hợp với các thao tác ngắn, có thời gian đáp ứng dự đoán được và cần trả kết quả ngay.

| Loại công việc | Cách xử lý thường phù hợp | Lý do |
|---|---|---|
| Đọc hoặc cập nhật nhỏ | Request đồng bộ | Đơn giản, kết quả cần ngay |
| Gọi I/O có thời gian chờ đáng kể | Async request hoặc client non-blocking | Giảm thời gian giữ request thread tùy stack |
| Tính toán CPU ngắn | Xử lý đồng bộ nếu nằm trong ngân sách latency | Tránh overhead chuyển executor |
| Tính toán CPU nặng | Worker pool giới hạn hoặc background job | Cô lập tài nguyên và tránh chặn luồng giao diện |
| Báo cáo hoặc export kéo dài | Job nền và endpoint lấy trạng thái | Không giữ request mở trong nhiều phút |
| Tệp lớn hoặc dữ liệu sinh dần | Streaming có giới hạn | Tránh buffer toàn bộ nội dung |
| Sự kiện cần cập nhật liên tục | SSE hoặc WebSocket khi phù hợp | Tránh polling quá dày |

Khi chọn, cần cân nhắc thời gian xử lý, mức đồng thời, khả năng retry, yêu cầu hủy, tính bền vững của công việc và cách client nhận kết quả.

## 5. Tránh chặn main thread trong trình duyệt

### 5.1. Chia nhỏ công việc và nhường quyền

Nếu công việc có thể chia thành các phần nhỏ, hãy xử lý theo từng lô và nhường quyền giữa các lô để trình duyệt có cơ hội xử lý input và render.

Ví dụ minh họa:

~~~javascript
async function processItems(items, batchSize = 200) {
  for (let start = 0; start < items.length; start += batchSize) {
    const batch = items.slice(start, start + batchSize);

    processBatch(batch);
    updateProgress(Math.min(start + batchSize, items.length), items.length);

    // Nhường quyền để browser có thể xử lý các tác vụ khác.
    await new Promise(resolve => setTimeout(resolve, 0));
  }
}
~~~

setTimeout với độ trễ 0 không bảo đảm chạy ngay ở frame kế tiếp; nó chỉ đưa phần tiếp theo vào hàng đợi task. Kích thước batch cần được điều chỉnh theo chi phí thực tế. Với cập nhật giao diện theo frame, requestAnimationFrame có thể phù hợp hơn.

### 5.2. Dùng Web Worker cho tính toán CPU nặng

Web Worker chạy JavaScript trong worker thread riêng và không trực tiếp thao tác DOM. Có thể chuyển dữ liệu cần tính toán sang worker, nhận kết quả rồi cập nhật giao diện trên main thread.

~~~javascript
// main.js
const worker = new Worker("/workers/report-worker.js", { type: "module" });

worker.addEventListener("message", event => {
  renderReport(event.data);
});

worker.postMessage({
  type: "BUILD_REPORT",
  rows: reportRows
});
~~~

~~~javascript
// report-worker.js
self.addEventListener("message", event => {
  const { type, rows } = event.data;

  if (type === "BUILD_REPORT") {
    const result = calculateReport(rows);
    self.postMessage(result);
  }
});
~~~

Web Worker phù hợp với tính toán độc lập, parse hoặc biến đổi dữ liệu lớn. Việc gửi bản sao dữ liệu lớn giữa main thread và worker cũng có chi phí; với ArrayBuffer có thể cân nhắc transferable objects khi phù hợp. Worker không tự truy cập DOM và cần được thiết kế giao thức message rõ ràng.

### 5.3. Giảm công việc render

Một danh sách có hàng chục nghìn phần tử không nên tạo toàn bộ DOM cùng lúc. Các kỹ thuật thường dùng:

- Pagination để chỉ tải một phần dữ liệu.
- Virtual scrolling để chỉ render phần tử đang nhìn thấy.
- Debounce input tìm kiếm để không gửi request cho từng phím.
- Throttle sự kiện cuộn hoặc resize.
- Tránh tính toán lặp lại trong mỗi lần render.
- Chỉ cập nhật vùng DOM thay đổi.

Ví dụ debounce tìm kiếm:

~~~javascript
function debounce(callback, delay) {
  let timer;

  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}

const search = debounce(async keyword => {
  const response = await fetch(
    "/api/products?keyword=" + encodeURIComponent(keyword)
  );

  if (!response.ok) {
    showSearchError();
    return;
  }

  renderProducts(await response.json());
}, 300);
~~~

Debounce giảm số request khi người dùng gõ liên tục. Nó không thay thế giới hạn tốc độ ở server và không nên được dùng làm cơ chế bảo vệ API.

### 5.4. Hủy request cũ và tránh kết quả sai thứ tự

Người dùng có thể gõ từ khóa A, sau đó gõ B. Request B có thể hoàn tất trước A. Nếu kết quả A đến sau và được render, giao diện hiển thị dữ liệu cũ.

Có thể dùng AbortController:

~~~javascript
let activeController;
let searchSequence = 0;

async function searchProducts(keyword) {
  activeController?.abort();
  activeController = new AbortController();
  const sequence = ++searchSequence;

  try {
    const response = await fetch(
      "/api/products?keyword=" + encodeURIComponent(keyword),
      { signal: activeController.signal }
    );

    if (!response.ok) {
      throw new Error("Search failed");
    }

    const products = await response.json();
    if (sequence !== searchSequence) {
      return;
    }

    renderProducts(products);
  } catch (error) {
    if (error.name !== "AbortError") {
      showSearchError();
    }
  }
}
~~~

Hủy request ở browser không bảo đảm server hoặc database đã dừng công việc. Server cần có timeout và cancellation riêng nếu muốn giải phóng tài nguyên phía sau.

### 5.5. Trạng thái giao diện trong lúc chờ

Một giao diện phản hồi tốt nên biểu diễn rõ các trạng thái:

- Idle: chưa có thao tác.
- Loading: request đang xử lý.
- Success: kết quả đã sẵn sàng.
- Empty: không có dữ liệu.
- Error: thao tác thất bại và có thể thử lại.
- Cancelled: người dùng đã hủy hoặc request cũ không còn cần thiết.

Có thể vô hiệu hóa nút gửi trong lúc thao tác đang diễn ra để tránh nhấn lặp, nhưng server vẫn phải xử lý duplicate request an toàn. Với thao tác tạo giao dịch, cân nhắc idempotency key.

Không nên khóa toàn bộ giao diện trong khi một request nền đang chạy. Người dùng vẫn có thể xem dữ liệu khác hoặc tiếp tục các thao tác độc lập.

## 6. Request đồng bộ trong Spring MVC

Spring MVC truyền thống dựa trên Servlet API. Trong cấu hình phổ biến, mỗi request đồng bộ chiếm một worker thread trong thời gian handler thực hiện.

~~~java
@GetMapping("/reports/{id}")
public ResponseEntity<ReportDto> getReport(@PathVariable UUID id) {
    ReportDto report = reportService.generate(id);
    return ResponseEntity.ok(report);
}
~~~

Đoạn code đơn giản và phù hợp nếu generate hoàn tất nhanh. Nếu phương thức mất nhiều giây, servlet worker phải chờ. Khi nhiều request cùng gọi, thread pool có thể bị cạn.

Không nên chuyển async chỉ vì một phương thức có vẻ dài. Trước hết hãy đo thời gian CPU, thời gian chờ I/O, số request đồng thời và giới hạn thread pool. Nếu thao tác vốn cần trả kết quả ngay và tải nằm trong ngân sách, đồng bộ thường dễ hiểu và dễ vận hành hơn.

## 7. Async request trong Spring MVC

Spring MVC hỗ trợ xử lý bất đồng bộ theo Servlet async processing. Handler có thể trả về Callable, DeferredResult hoặc WebAsyncTask. DispatcherServlet bắt đầu async processing và giải phóng servlet request thread ban đầu; kết quả được xử lý tiếp khi sẵn sàng.

Điều này có thể giảm số servlet thread bị giữ trong lúc chờ. Nhưng công việc vẫn cần được thực hiện ở một executor hoặc callback phù hợp. Nếu worker pool mới bị chặn hoặc không có giới hạn, hệ thống chỉ chuyển điểm nghẽn sang nơi khác.

### 7.1. Callable

Callable cho phép Spring chạy phần xử lý trong một async TaskExecutor:

~~~java
@GetMapping("/reports/{id}/preview")
public Callable<ResponseEntity<ReportPreview>> preview(
        @PathVariable UUID id) {

    return () -> {
        ReportPreview result = reportService.buildPreview(id);
        return ResponseEntity.ok(result);
    };
}
~~~

Khi handler trả Callable, servlet thread ban đầu có thể quay lại pool. Callable được thực thi trên executor dành cho async MVC. Nếu buildPreview chờ một HTTP call blocking, worker async vẫn bị chiếm dụng trong lúc chờ; cần đặt timeout và giới hạn pool.

Callable phù hợp khi kết quả có thể trả về trong thời gian request chấp nhận được và công việc có thể chạy trong executor. Không nên dùng nó để giữ một request mở hàng phút cho báo cáo lớn.

### 7.2. DeferredResult

DeferredResult phù hợp khi kết quả sẽ được hoàn tất bởi một callback hoặc sự kiện đến từ thành phần khác.

~~~java
@GetMapping("/jobs/{id}/result")
public DeferredResult<ResponseEntity<JobResult>> result(
        @PathVariable UUID id) {

    DeferredResult<ResponseEntity<JobResult>> deferred =
        new DeferredResult<>(10_000L);

    jobResultService.findWhenReady(id)
        .whenComplete((result, error) -> {
            if (error != null) {
                deferred.setErrorResult(error);
            } else {
                deferred.setResult(ResponseEntity.ok(result));
            }
        });

    deferred.onTimeout(() ->
        deferred.setResult(
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build()
        )
    );

    return deferred;
}
~~~

Ví dụ minh họa giả định findWhenReady trả về một CompletionStage hoặc abstraction tương tự. Cần xử lý timeout, lỗi và trường hợp client ngắt kết nối theo hợp đồng của ứng dụng. Không nên để callback hoàn tất DeferredResult nhiều lần hoặc giữ tham chiếu request vô thời hạn.

### 7.3. WebAsyncTask

WebAsyncTask cho phép gắn timeout và callback xử lý cho một Callable cụ thể:

~~~java
@GetMapping("/reports/{id}/async-preview")
public WebAsyncTask<ReportPreview> asyncPreview(@PathVariable UUID id) {
    Callable<ReportPreview> task =
        () -> reportService.buildPreview(id);

    WebAsyncTask<ReportPreview> asyncTask =
        new WebAsyncTask<>(8_000L, task);

    asyncTask.onTimeout(() -> {
        throw new ReportTimeoutException();
    });

    return asyncTask;
}
~~~

Đây là ví dụ khái quát; lỗi khi chạy Callable được chuyển qua cơ chế xử lý exception của Spring MVC và nên được ánh xạ bằng exception handler phù hợp. Timeout không tự bảo đảm mọi công việc bên dưới đã dừng. Tác vụ cần hỗ trợ hủy hoặc tự kiểm tra deadline nếu muốn dừng sớm.

### 7.4. Cấu hình async executor có giới hạn

Không nên để async MVC dùng một hàng đợi vô hạn hoặc một executor không được quản lý. Ví dụ cấu hình:

~~~java
@Configuration
public class MvcAsyncConfiguration implements WebMvcConfigurer {
    private final AsyncTaskExecutor mvcExecutor;

    public MvcAsyncConfiguration(AsyncTaskExecutor mvcExecutor) {
        this.mvcExecutor = mvcExecutor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(8_000L);
        configurer.setTaskExecutor(mvcExecutor);
    }
}
~~~

Một executor có thể được cấu hình ở composition root:

~~~java
@Bean
ThreadPoolTaskExecutor mvcExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(32);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mvc-async-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
~~~

Các con số chỉ là ví dụ, không phải cấu hình dùng chung cho mọi hệ thống. Cần chọn theo CPU, thời gian I/O, giới hạn downstream, connection pool và tải đo được. Hàng đợi hữu hạn giúp hệ thống có thể từ chối hoặc làm chậm tải mới thay vì tích lũy request vô hạn.

Khi executor đầy, cần xác định hành vi từ chối và cách ánh xạ thành response phù hợp, thường là lỗi quá tải có thể retry sau. Không nên chạy tác vụ nặng ngay trên thread gọi request như một cách né từ chối, vì điều đó có thể làm nghẽn servlet pool.

## 8. Async không đồng nghĩa với non-blocking

Đây là khác biệt quan trọng khi làm việc với Spring MVC.

- **Async request:** servlet thread ban đầu được giải phóng trong khi kết quả chưa sẵn sàng.
- **Blocking I/O:** một thread gọi hàm và chờ cho đến khi I/O hoàn tất.
- **Non-blocking I/O:** thread đăng ký callback hoặc continuation và có thể làm công việc khác trong lúc chờ I/O.
- **Reactive processing:** biểu diễn chuỗi dữ liệu và thao tác bất đồng bộ theo cơ chế reactive, thường có backpressure.

Callable trong Spring MVC có thể chạy một lời gọi JDBC blocking trên worker khác. Nó giải phóng servlet thread ban đầu nhưng worker async vẫn phải chờ database.

Nếu hệ thống dùng JDBC/JPA blocking, hãy giới hạn số thao tác đồng thời theo connection pool và database. Không nên tăng thread pool vượt xa khả năng phục vụ của downstream.

Spring WebFlux được thiết kế cho mô hình reactive và non-blocking khi toàn bộ chuỗi thư viện hỗ trợ. Không nên chạy JDBC/JPA blocking trực tiếp trên event-loop thread của WebFlux. Nếu phải gọi thư viện blocking, cần cô lập trên scheduler phù hợp và giới hạn concurrency; tốt hơn là dùng client non-blocking tương ứng khi có thể.

## 9. Chuyển tác vụ dài sang background job

Một số công việc không phù hợp với request-response vì thời gian xử lý dài hoặc không cần kết quả ngay:

- Tạo báo cáo lớn.
- Export hàng triệu bản ghi.
- Xử lý video hoặc ảnh.
- Gửi hàng loạt email.
- Đồng bộ dữ liệu từ hệ thống ngoài.
- Import tệp lớn.
- Tính toán theo lô.

Thay vì giữ request mở, Controller có thể tạo job, lưu trạng thái và trả HTTP 202 Accepted cùng mã job.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant API as MVC Controller
    participant App as Application Service
    participant Queue as Job Queue
    participant Worker as Background Worker
    participant Store as Job Store

    User->>Browser: Yêu cầu tạo báo cáo
    Browser->>API: POST /reports
    API->>App: SubmitReportCommand
    App->>Store: Tạo job trạng thái QUEUED
    App->>Queue: Phát job ID
    API-->>Browser: 202 Accepted + job ID
    Worker->>Queue: Nhận job
    Worker->>Store: Đặt RUNNING
    Worker->>Worker: Tạo báo cáo
    Worker->>Store: Đặt SUCCEEDED hoặc FAILED
    Browser->>API: GET /jobs/{id}
    API->>Store: Đọc trạng thái
    API-->>Browser: Trạng thái và tiến độ
~~~

Một phản hồi 202 có thể trả:

~~~json
{
  "jobId": "job-7f3a",
  "status": "QUEUED",
  "statusUrl": "/api/jobs/job-7f3a"
}
~~~

Client có thể polling status URL với khoảng thời gian tăng dần hoặc dùng SSE/WebSocket để nhận cập nhật khi phù hợp. Khi job hoàn tất, endpoint khác cung cấp kết quả hoặc URL tải tệp có thời hạn.

### 9.1. Lưu trạng thái job bền vững

Nếu job chỉ nằm trong bộ nhớ của một process, restart có thể làm mất công việc. Với tác vụ quan trọng, lưu metadata và trạng thái trong database hoặc hệ thống queue bền vững.

Trạng thái thường gặp:

- QUEUED: đang chờ.
- RUNNING: đang xử lý.
- SUCCEEDED: hoàn tất.
- FAILED: thất bại.
- CANCEL_REQUESTED: đã yêu cầu hủy.
- CANCELLED: đã hủy.
- EXPIRED: kết quả hết hạn.

Lưu thời điểm tạo, bắt đầu, kết thúc, tiến độ, mã lỗi an toàn và người sở hữu job. Endpoint trạng thái phải kiểm tra quyền để người dùng không đọc job của người khác.

Nếu metadata job nằm trong database còn queue là một hệ thống riêng, việc commit job rồi publish message có thể thất bại ở giữa hai bước. Có thể dùng transactional outbox hoặc một cơ chế quét job QUEUED để bảo đảm công việc đã ghi nhận cuối cùng được đưa đến worker.

### 9.2. Retry và idempotency

Worker có thể nhận lại một job do timeout, restart hoặc retry của message broker. Vì vậy, xử lý cần có khả năng chịu lặp:

- Dùng job ID hoặc idempotency key.
- Ghi trạng thái chuyển tiếp một cách nhất quán.
- Tránh gửi email hoặc tạo giao dịch trùng khi retry.
- Phân loại lỗi tạm thời và lỗi không thể khắc phục.
- Đặt giới hạn số lần retry và khoảng chờ tăng dần.
- Có cơ chế dead-letter hoặc can thiệp vận hành khi job thất bại kéo dài.

Không retry vô hạn một tác vụ đang gặp lỗi cấu hình hoặc dữ liệu đầu vào không hợp lệ.

## 10. Timeout, deadline và cancellation

Một request có thể đi qua nhiều tầng: browser, gateway, Controller, application service, database và dịch vụ ngoài. Nếu mỗi tầng chờ một khoảng thời gian không liên quan, request có thể giữ tài nguyên lâu hơn mức người dùng hoặc hệ thống chấp nhận.

### 10.1. Phân biệt timeout

| Timeout | Giới hạn điều gì? |
|---|---|
| Client timeout | Thời gian client chờ response |
| Gateway/proxy timeout | Thời gian gateway chờ upstream |
| MVC async timeout | Thời gian Spring MVC chờ kết quả async |
| HTTP client timeout | Thời gian kết nối hoặc chờ response từ dịch vụ ngoài |
| Database query timeout | Thời gian truy vấn được phép chạy |
| Job deadline | Thời điểm tác vụ nền không còn được tiếp tục |

Các timeout cần phối hợp với nhau. Nếu gateway timeout sau 10 giây nhưng downstream call chờ 60 giây, request phía server có thể vẫn chạy sau khi client đã bỏ cuộc.

### 10.2. Deadline end-to-end

Thay vì đặt từng timeout tùy ý, hãy xác định ngân sách thời gian tổng thể. Ví dụ một endpoint có mục tiêu phản hồi trong 3 giây có thể phân bổ một phần cho gateway, application, database và dịch vụ ngoài, đồng thời chừa thời gian tạo response.

Deadline nên được truyền hoặc suy ra nhất quán ở các tầng. Một bước downstream không nên bắt đầu công việc mới nếu thời gian còn lại đã thấp hơn mức tối thiểu cần thiết.

### 10.3. Cancellation phải có tính hợp tác

Khi người dùng đóng trang hoặc fetch bị abort, server không tự động dừng mọi công việc. Hệ thống cần cơ chế hủy phù hợp:

- Kiểm tra cancellation token hoặc interrupt flag giữa các bước.
- Dùng API client có hỗ trợ cancel.
- Đặt query timeout cho database.
- Dừng việc tạo dữ liệu khi không còn người nhận nếu chính sách cho phép.
- Cho phép job nhận trạng thái CANCEL_REQUESTED và kiểm tra tại các checkpoint.

Thread interruption chỉ có tác dụng khi code và thư viện được gọi hợp tác xử lý interrupt. Không thể cưỡng bức dừng an toàn một đoạn Java bất kỳ chỉ bằng cách ngắt thread.

Một số future có phương thức cancel nhưng việc hủy chỉ có hiệu quả nếu tác vụ bên dưới hỗ trợ. Tương tự, hoàn tất một CompletableFuture bằng timeout không đồng nghĩa với việc I/O hoặc công việc CPU đang chạy đã dừng.

### 10.4. Timeout không thay thế idempotency

Client timeout không cho biết server đã hoàn thành thao tác hay chưa. Với lệnh thanh toán hoặc tạo đơn, client có thể retry sau khi không nhận response và vô tình tạo giao dịch trùng.

Dùng idempotency key hoặc mã thao tác để server nhận diện retry của cùng một ý định. Phản hồi lần sau có thể trả kết quả đã ghi nhận thay vì thực hiện lại thao tác.

## 11. Backpressure và giới hạn đồng thời

Backpressure là cách hệ thống điều tiết tốc độ giữa bên sản xuất và bên tiêu thụ để tránh tích lũy công việc vượt khả năng xử lý. Trong Reactive Streams, subscriber có thể yêu cầu số phần tử muốn nhận; ở ứng dụng Servlet MVC, giới hạn queue, concurrency và từ chối tải mới là các cơ chế admission control/load shedding có mục tiêu tương tự, không phải cùng một giao thức demand-based.

Trong ứng dụng MVC, những nơi cần giới hạn gồm:

- Số servlet worker đang xử lý.
- Async executor và hàng đợi.
- Connection pool của database.
- HTTP client connection pool.
- Số job chạy đồng thời.
- Số message consumer đang hoạt động.
- Số tác vụ CPU nặng.

### 11.1. Dùng hàng đợi có giới hạn

Hàng đợi vô hạn có thể khiến hệ thống tiếp nhận nhiều công việc hơn khả năng xử lý. Bộ nhớ tăng, thời gian chờ dài và request hết hạn trước khi được chạy.

Hàng đợi hữu hạn cho phép ứng dụng từ chối tải mới khi quá tải. Client có thể nhận 429 Too Many Requests hoặc 503 Service Unavailable tùy nguyên nhân và hợp đồng. Nếu có thể retry, cung cấp Retry-After phù hợp.

### 11.2. Bulkhead và giới hạn concurrency

Không để một nhóm tác vụ chiếm toàn bộ worker dùng chung. Có thể tách executor hoặc semaphore cho:

- Báo cáo nặng.
- Gọi dịch vụ thanh toán.
- Tác vụ gửi email.
- Import/export.
- Tác vụ tương tác cần latency thấp.

Bulkhead cô lập sự cố hoặc tải cao ở một nhóm để nhóm khác vẫn có tài nguyên phục vụ. Tuy nhiên, tách pool quá nhiều làm tăng độ phức tạp và có thể tạo ra nhiều hàng đợi nhỏ khó sử dụng hết tài nguyên. Hãy dựa trên tải và dependency thực tế.

### 11.3. Không tăng thread pool vô hạn

Tăng max thread có thể cải thiện throughput trong một khoảng nhất định, nhưng quá nhiều thread làm tăng context switching, stack memory và cạnh tranh connection. Nếu database chỉ phục vụ được 30 query đồng thời, tạo 300 worker chờ database không làm database nhanh hơn.

Chọn concurrency theo giới hạn nhỏ nhất trong chuỗi phụ thuộc và đo queue wait cùng thời gian thực thi.

## 12. Streaming dữ liệu lớn

Với dữ liệu lớn, tạo toàn bộ nội dung trong bộ nhớ rồi mới trả response có thể gây áp lực heap và tăng thời gian đến byte đầu tiên (time to first byte).

Streaming gửi dữ liệu theo từng phần khi sẵn sàng:

~~~java
@GetMapping("/exports/{id}")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID id) {

    StreamingResponseBody body = output -> {
        exportService.writeCsv(id, output);
    };

    return ResponseEntity.ok()
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=orders.csv"
        )
        .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
        .body(body);
}
~~~

StreamingResponseBody giúp ghi response theo luồng và được Spring MVC thực hiện qua async processing. Tuy nhiên, thao tác ghi vào output stream có thể chờ client nhận dữ liệu; worker streaming vẫn có thể bị chiếm trong lúc ghi.

Cần chú ý:

- Không giữ transaction database trong toàn bộ thời gian client tải nếu có thể tránh.
- Đọc dữ liệu theo batch hoặc cursor phù hợp, không tải hết vào heap.
- Đóng tài nguyên đúng cách.
- Đặt giới hạn kích thước export và thời gian tải.
- Xử lý client ngắt kết nối.
- Theo dõi worker và connection bị giữ trong lúc truyền.
- Bảo đảm quyền tải tệp được kiểm tra trên từng request.

Khi response headers đã gửi, server khó thay đổi status code nếu lỗi xảy ra giữa stream. Hợp đồng cần xác định cách xử lý lỗi giữa chừng, ví dụ kết thúc kết nối, dùng định dạng có record trạng thái hoặc tạo artifact hoàn chỉnh trước rồi mới cho tải.

## 13. Giao dịch và tài nguyên không nên bị giữ quá lâu

Transaction database nên bao quanh phần đọc/ghi cần tính nguyên tử. Tránh giữ transaction trong lúc:

- Chờ người dùng xác nhận.
- Gọi API bên ngoài chậm.
- Gửi email.
- Tạo tệp lớn.
- Stream nội dung cho client.
- Chờ message hoặc callback trong thời gian dài.

Một luồng tốt có thể đọc dữ liệu trong transaction ngắn, thực hiện công việc bên ngoài, rồi mở transaction khác để lưu kết quả. Nếu cần bảo đảm sự kiện chỉ phát sau khi commit, cân nhắc transaction synchronization hoặc transactional outbox.

Cũng cần theo dõi thời gian giữ connection database. Một request async vẫn có thể giữ connection hoặc transaction nếu code mở transaction quá sớm và chờ I/O trong phạm vi đó.

## 14. Caching và giảm công việc lặp

Một cách giảm latency là không thực hiện lại cùng một công việc khi dữ liệu không thay đổi hoặc kết quả có thể tái sử dụng.

Có thể cân nhắc:

- Cache dữ liệu tham chiếu ít thay đổi.
- Cache kết quả query có khóa và TTL phù hợp.
- Dùng ETag hoặc conditional request để tránh tải lại nội dung không đổi.
- Dùng CDN cho tài nguyên tĩnh hoặc nội dung công khai.
- Dùng request coalescing để gộp nhiều yêu cầu đồng thời cho cùng một dữ liệu.
- Dùng batch query thay vì gọi repository lặp trong vòng lặp.

Cache cần có chính sách invalidation, phạm vi tenant và quyền truy cập. Không dùng cache chung cho dữ liệu riêng tư nếu cache key không bao gồm danh tính hoặc scope phù hợp. Kết quả quyền truy cập cũng không nên cache lâu hơn chính sách cho phép.

## 15. Đo lường để tìm điểm nghẽn

Tối ưu dựa trên số liệu, không dựa vào cảm giác. Một số chỉ số quan trọng:

| Chỉ số | Ý nghĩa |
|---|---|
| Latency p50 | Thời gian phản hồi điển hình |
| Latency p95/p99 | Trải nghiệm ở nhóm request chậm |
| Throughput | Số request hoặc job hoàn tất trong một khoảng thời gian |
| Queue wait | Thời gian chờ trước khi bắt đầu xử lý |
| Execution time | Thời gian thực thi handler hoặc tác vụ |
| CPU utilization | Mức sử dụng CPU |
| Heap / GC | Áp lực bộ nhớ và thời gian garbage collection |
| Active threads | Số worker đang hoạt động |
| Pool saturation | Mức sử dụng servlet, executor, DB hoặc HTTP connection pool |
| Error / timeout rate | Tỷ lệ lỗi và timeout |

### 15.1. Tách thời gian chờ và thời gian chạy

Một request có tổng latency 4 giây có thể gồm:

- Queue wait: 1,5 giây.
- Database: 1,8 giây.
- Xử lý application: 0,4 giây.
- Render và truyền response: 0,3 giây.

Nếu chỉ đo tổng thời gian, khó biết nên tăng worker, tối ưu query hay giảm công việc trong Controller. Instrument các span hoặc mốc thời gian ở ranh giới quan trọng để tìm nguyên nhân.

### 15.2. Dùng distributed tracing và correlation ID

Khi request gọi nhiều dịch vụ, tracing giúp nối các span từ gateway đến Controller, database và downstream API. Correlation ID giúp liên kết log của request với job nền hoặc message được phát sinh từ request đó.

Không ghi dữ liệu nhạy cảm vào trace hoặc log. Dùng tên operation và metadata cần thiết để phân tích.

### 15.3. Đo ở trình duyệt

Dùng browser Performance panel để xem long task, layout, paint và thời gian script. Dùng Network panel để phân biệt thời gian chờ server, truyền dữ liệu và xử lý client.

Một endpoint server nhanh vẫn có thể tạo trải nghiệm chậm nếu client render quá nhiều DOM hoặc xử lý JSON lớn trên main thread.

## 16. Kiểm thử hiệu năng và khả năng chịu tải

Kiểm thử một request đơn lẻ không đủ để phát hiện thread pool saturation. Cần mô phỏng tải đồng thời và các trường hợp phụ thuộc chậm.

Nên kiểm tra:

- Latency p95/p99 khi số request tăng.
- Queue wait khi executor gần đầy.
- Hành vi khi database chậm hoặc connection pool cạn.
- Timeout và cancellation có giải phóng tài nguyên không.
- Hàng đợi có giới hạn và từ chối tải mới đúng không.
- Một loại job nặng có làm endpoint nhẹ bị đói worker không.
- Client retry có tạo thao tác trùng không.
- Streaming có tăng heap theo kích thước tệp không.
- Browser main thread có long task khi render dữ liệu lớn không.

Có thể dùng JMeter, Gatling hoặc k6 để tạo tải HTTP; dùng profiler và tracing để xác định bottleneck. Thiết lập dữ liệu test và giới hạn môi trường phù hợp để tránh gây ảnh hưởng hệ thống dùng chung.

## 17. Những lỗi thiết kế thường gặp

### Chuyển mọi endpoint thành async

Async tăng độ phức tạp về executor, timeout, error handling và cancellation. Chỉ dùng khi nó giải quyết một điểm nghẽn hoặc yêu cầu giao tiếp cụ thể.

### Nghĩ async là non-blocking

Callable chạy JDBC blocking trên worker khác vẫn chiếm worker trong lúc chờ. Phân biệt rõ async request với non-blocking I/O.

### Dùng hàng đợi vô hạn

Hàng đợi vô hạn làm request chờ ngày càng lâu và tiêu thụ bộ nhớ. Dùng queue capacity có giới hạn, concurrency limit và load shedding.

### Dùng @Async cho tác vụ quan trọng rồi coi là bền vững

Một tác vụ trong executor bộ nhớ có thể mất khi process dừng. Công việc cần bền vững nên được ghi nhận bằng job store hoặc message broker và có retry/idempotency.

### Giữ transaction trong lúc gọi dịch vụ ngoài

Điều này giữ connection và lock trong thời gian chờ mạng. Giữ transaction ngắn quanh thao tác cần tính nguyên tử.

### Dùng timeout nhưng không hủy công việc

Client đã bỏ cuộc nhưng server vẫn tiếp tục tính toán hoặc gọi downstream. Propagate deadline và hỗ trợ cancellation ở các bước có thể dừng.

### Tăng thread pool để chữa mọi vấn đề

Tăng worker không sửa được database chậm, API ngoài quá tải hoặc CPU bão hòa. Đo pool saturation và giới hạn downstream trước khi điều chỉnh.

### Render quá nhiều DOM

Một response nhanh vẫn có thể làm browser đứng khi tạo hàng nghìn phần tử. Dùng pagination, virtualization và chia nhỏ công việc.

### Không xử lý request lặp

Người dùng nhấn nhiều lần hoặc client retry có thể tạo nhiều giao dịch. Dùng idempotency key cho thao tác cần bảo đảm không lặp.

## 18. Quy trình thiết kế để tránh chặn và giữ request quá lâu

Khi xây dựng một chức năng MVC, hãy thực hiện theo trình tự:

1. **Xác định mục tiêu latency.** Chức năng cần phản hồi trong bao lâu và ở percentile nào?
2. **Phân loại công việc.** CPU-bound, I/O-bound, chờ người dùng hay tác vụ nền kéo dài?
3. **Tìm ranh giới đang bị giữ.** Browser main thread, servlet thread, executor, DB connection hay transaction?
4. **Chọn cách xử lý.** Đồng bộ, async request, non-blocking client, Web Worker, streaming hoặc background job.
5. **Đặt giới hạn.** Timeout, deadline, queue capacity, concurrency và kích thước batch.
6. **Thiết kế cancellation và retry.** Hủy có hợp tác, idempotency và giới hạn số lần retry.
7. **Bảo vệ trạng thái giao diện.** Loading, error, empty, duplicate submission và kết quả đến sai thứ tự.
8. **Giữ transaction ngắn.** Không chờ người dùng hoặc mạng trong transaction database.
9. **Đo lường.** Theo dõi p95/p99, queue wait, execution time và pool saturation.
10. **Kiểm thử tải và lỗi.** Mô phỏng downstream chậm, quá tải, timeout, retry và client disconnect.

Trước khi hoàn thành, hãy tự hỏi:

- Main thread có đang chạy tính toán hoặc render quá lâu không?
- Request có giữ servlet worker trong lúc chờ I/O không?
- Async executor có queue và concurrency giới hạn không?
- Tác vụ dài có nên chuyển thành job nền không?
- Timeout có được truyền xuống database và dịch vụ ngoài không?
- Khi client hủy, server có thể dừng phần việc không còn cần thiết không?
- Transaction và connection có bị giữ trong lúc stream hoặc chờ mạng không?
- Có bảo vệ thao tác ghi khỏi retry và gửi lặp không?
- Số liệu có chỉ ra queue wait hay execution time là nguyên nhân chính không?

## 19. Kết luận

Tránh chặn luồng giao diện và giữ request quá lâu đòi hỏi hiểu rõ công việc đang chạy ở đâu và đang chờ điều gì. Trình duyệt cần giữ main thread đủ rảnh để xử lý input và render; máy chủ cần giới hạn thời gian giữ servlet worker, executor, connection và transaction.

Spring MVC cung cấp async request để giải phóng servlet thread ban đầu trong lúc chờ kết quả, nhưng công việc blocking vẫn tiêu thụ worker khác. Với tác vụ kéo dài, background job bền vững thường phù hợp hơn; với dữ liệu lớn, streaming có thể giảm buffering nhưng vẫn cần quản lý worker và kết nối. Kết hợp timeout, cancellation, backpressure, idempotency và đo lường p95/p99 giúp ứng dụng MVC phản hồi ổn định khi tải tăng.

