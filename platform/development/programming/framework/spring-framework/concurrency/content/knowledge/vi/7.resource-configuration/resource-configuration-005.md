# Phân biệt giới hạn đồng thời với giới hạn số yêu cầu theo thời gian

> **Phạm vi:** Spring Framework – concurrency, phần cấu hình tài nguyên. Bài học giải thích hai kiểu bảo vệ hệ thống thường bị nhầm với nhau: **concurrency limit** (giới hạn số công việc đang diễn ra đồng thời) và **rate limit** (giới hạn số lượt yêu cầu được phép bắt đầu trong một khoảng thời gian). Chúng đo hai đại lượng khác nhau, giải quyết những rủi ro khác nhau và thường phải phối hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt số yêu cầu đang xử lý (*in-flight/concurrent requests*) với lưu lượng yêu cầu theo thời gian (*requests per second – RPS*, *requests per minute – RPM*).
2. Giải thích tại sao giới hạn 10 tác vụ đồng thời không đồng nghĩa 10 request/giây, và giới hạn 100 request/giây cũng không đồng nghĩa tối đa 100 tác vụ chạy song song.
3. Sử dụng `Semaphore` hoặc bulkhead để giới hạn công việc đồng thời; hiểu các thuật toán fixed window, sliding window và token bucket để giới hạn tốc độ.
4. Liên hệ các giới hạn này với `ThreadPoolTaskExecutor`, HTTP controller, tác vụ `@Async` và các trường hợp nhiều instance Spring.
5. Phân biệt quyết định xếp hàng, từ chối, chờ, HTTP 429 và 503; đặt giới hạn có thể giám sát và kiểm thử được.
6. Viết và chạy ví dụ Java 17 có đầu ra xác định, không dùng `Thread.sleep` làm bằng chứng cho tính đúng đắn.

## 2. Hai giới hạn trả lời hai câu hỏi khác nhau

### 2.1. Giới hạn đồng thời (concurrency limit)

**Concurrency limit** khống chế số lượng công việc đang **giữ quyền sử dụng một tài nguyên** tại một thời điểm.

Ví dụ: một semaphore có **8 permit** cho phép tối đa 8 lời gọi tới dịch vụ xử lý báo cáo được thực thi trong cùng thời điểm trong một JVM. Lời gọi thứ chín sẽ phải đợi hoặc bị từ chối, tùy chính sách của chương trình. Khi một công việc hoàn thành hoặc thất bại, nó **trả lại permit** để công việc khác sử dụng.

Cách ký hiệu:

~~~text
In-flight(t) = số công việc đã vào vùng được bảo vệ
               nhưng chưa rời vùng đó tại thời điểm t

Yêu cầu: In-flight(t) <= C ở mọi thời điểm t
         C = giới hạn số công việc đồng thời
~~~

Đơn vị của `C` là **công việc đang diễn ra**, không phải công việc/giây.

Phạm vi “công việc đang diễn ra” phải được xác định trước: một HTTP request từ lúc vào controller đến lúc response kết thúc, một cuộc gọi downstream, một tác vụ đang chạy trong worker, hay cả tác vụ đang nằm trong queue? Đây là các phạm vi khác nhau; một giới hạn chỉ có ý nghĩa nếu permit được lấy và trả ở đúng ranh giới.

### 2.2. Giới hạn yêu cầu theo thời gian (rate limit)

**Rate limit** khống chế số **lượt được chấp nhận/bắt đầu** trong một khoảng thời gian, hoặc tốc độ cấp quyền trung bình theo một thuật toán.

Ví dụ: một người dùng chỉ được bắt đầu **60 yêu cầu trong 60 giây**. Mỗi yêu cầu được chấp nhận thường tiêu thụ một lượt trong quota; việc yêu cầu kết thúc **không lập tức hoàn trả lượt đó**. Quyền tiếp tục được cấp khi thời gian/window/tokens được làm mới theo thuật toán.

Một mô hình cửa sổ đơn giản:

~~~text
Accepted(user, window_60s) <= 60

Đơn vị: yêu cầu / 60 giây (hoặc requests/second)
~~~

Rate limit có thể được tính theo user, API key, IP, tenant, endpoint, toàn dịch vụ hoặc theo kết hợp nhiều tiêu chí. Một quota toàn dịch vụ và quota từng khách hàng không thể thay thế nhau.

### 2.3. Bảng đối chiếu cốt lõi

| Tiêu chí | Giới hạn đồng thời | Giới hạn theo thời gian |
| --- | --- | --- |
| Câu hỏi | “Bao nhiêu việc đang chạy/chiếm tài nguyên ngay lúc này?” | “Bao nhiêu lượt được phép đi vào trong khoảng thời gian?” |
| Đại lượng | In-flight count, permits đang giữ | Requests/giây, requests/phút, token/period |
| Đơn vị | Job/request/call **đồng thời** | Job/request/call **mỗi đơn vị thời gian** |
| Khi lấy quyền | Trước khi bắt đầu vùng tài nguyên cần bảo vệ | Khi request được phép đi vào theo quota |
| Khi trả/khôi phục quyền | Khi công việc hoàn thành, lỗi hoặc bị hủy; thường trong `finally` | Theo thời gian hoặc chính sách refill; hoàn thành task không tự trả token |
| Cơ chế quen thuộc | `Semaphore`, semaphore bulkhead, giới hạn active worker | Fixed/sliding window, token bucket, rate limiter |
| Rủi ro giảm thiểu | Cạn connection/worker/memory do quá nhiều việc kéo dài | Burst, gọi API quá dày, vượt quota đối tác, lạm dụng theo user |
| Có bảo đảm giới hạn còn lại? | **Không bảo đảm RPS** | **Không bảo đảm số in-flight** |
| Phạm vi triển khai | Một JVM, service, pool hoặc toàn cụm nếu có bộ điều phối chung | Một process, API key, gateway hoặc toàn cụm tùy nơi lưu quota |

**Nhớ ngắn:** concurrency limit là **sức chứa tại một thời điểm**; rate limit là **số lượt đi qua theo thời gian**.

## 3. Ví dụ trực giác: cùng giới hạn nhưng throughput rất khác

Giả sử một dịch vụ cho tối đa **10 request đồng thời**.

- Nếu mỗi request mất trung bình **0,05 giây** và luôn có việc chờ, trong một mô hình lý tưởng không có overhead và nút thắt khác, công suất xấp xỉ `10 / 0,05 = 200 request/giây`.
- Nếu mỗi request mất trung bình **5 giây**, cùng giới hạn 10 request đồng thời chỉ cho công suất xấp xỉ `10 / 5 = 2 request/giây`.

Vì vậy, nói “pool có 10 thread nên API giới hạn 10 RPS” là sai. Số thread giới hạn mức song song của công việc chạy trên pool, nhưng số task hoàn thành mỗi giây còn phụ thuộc độ dài tác vụ và giới hạn tài nguyên khác. Nếu có queue, task đã được nhận nhưng chưa chạy càng không đồng nhất với active thread.

Chiều ngược lại, giả sử cấp **100 request/giây** và mỗi request mất trung bình **10 giây**. Nếu lưu lượng ổn định đủ lâu và không có giới hạn khác, số request đồng thời trung bình có thể tiến đến khoảng `100 × 10 = 1.000`, dù rate limit vẫn hoàn toàn tuân thủ. Dịch vụ có 50 kết nối downstream sẽ sớm quá tải nếu không có một lớp admission/concurrency control thích hợp.

### Một hình dung nhanh

~~~text
RATE LIMIT:          100 lượt được phép bắt đầu trong 1 giây
                       | | | | | | | | ...
                       v v v v v v v v
                         hàng đợi/tác vụ
                              |
CONCURRENCY LIMIT:        [ 8 slot đang giữ ]
                          [request 1 ... 8]
                              |
                          hoàn thành -> trả slot
~~~

Hai lớp có thể nằm ở những vị trí khác nhau: rate limit tại API gateway, concurrency limit sát downstream/database. Trật tự và vị trí của chúng quyết định tài nguyên nào được bảo vệ trước tiên.

## 4. Mối liên hệ toán học: Little's Law

Trong hệ thống **ổn định**, xét trung bình dài hạn với cách định nghĩa phạm vi nhất quán, **Little's Law**:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình **đang nằm trong hệ thống đang xét**.
- `λ`: tốc độ trung bình các công việc đi qua hệ thống, đơn vị công việc/giây.
- `W`: thời gian trung bình một công việc ở trong hệ thống, đơn vị giây.

Nếu đang đo riêng đoạn xử lý trong service, `W` là thời gian giữ tài nguyên tương ứng; nếu đo cả queue và xử lý, `W` phải bao gồm **cả thời gian chờ queue**. Không được lấy throughput ở một phạm vi rồi nhân với latency ở phạm vi khác.

Ví dụ khi hệ thống ổn định:

| Throughput `λ` | Thời gian trung bình `W` | In-flight trung bình `L` |
| ---: | ---: | ---: |
| 20 req/s | 0,1 s | 2 |
| 20 req/s | 1 s | 20 |
| 20 req/s | 5 s | 100 |
| 100 req/s | 0,2 s | 20 |

Điều đáng chú ý: **cùng RPS nhưng latency tăng khiến in-flight tăng**. Khi downstream chậm lại, chỉ áp rate limit thường chưa đủ để bảo vệ connection pool hoặc memory.

Little's Law là quan hệ **trung bình**, không chứng minh số in-flight tối đa và không thay thế kiểm tra p95/p99, burst, queue hay timeout. Không thể tự suy một hard concurrency cap chỉ từ một giá trị RPS.

## 5. Concurrency limiter hoạt động ra sao?

Một mô hình điển hình dùng `Semaphore(C)`:

~~~text
Request vào
    |
    v
Thử lấy permit
    |
    +-- Có permit: active++ -> làm việc -> finally release -> active--
    |
    +-- Hết permit:
           +-- Từ chối ngay
           +-- Hoặc chờ có giới hạn (timeout, queue)
~~~

Quan trọng: permit chỉ được trả nếu đã lấy thành công, và phải trả **đúng một lần** ở tất cả đường hoàn thành, exception và cancel.

Ví dụ Java:

~~~java
Semaphore slots = new Semaphore(8);

if (!slots.tryAcquire()) {
    throw new IllegalStateException("capacity exhausted");
}

try {
    performBlockingWork(); // Có tối đa 8 invocation trong vùng này
} finally {
    slots.release();
}
~~~

**Đoạn minh họa:** cần có `performBlockingWork()` thật trong ứng dụng. `tryAcquire()` không chờ; vì vậy request thứ chín bị từ chối ngay. Nếu dùng `tryAcquire(timeout, TimeUnit.MILLISECONDS)`, caller có thể chờ và giữ request thread; phải chọn timeout hợp lý, xử lý `InterruptedException` và đánh giá tác động tài nguyên.

### Giới hạn “đang chạy” khác giới hạn “đã nhận vào queue”

Khi lấy permit:

1. **Ngay trước khi submit vào thread pool:** permit có thể bị giữ trong cả thời gian **đang xếp hàng**, và chỉ trả sau khi task kết thúc. Đây là giới hạn tổng số job đã nhận nhưng chưa hoàn tất, có ích để chặn backlog.
2. **Bên trong worker ngay lúc bắt đầu xử lý:** permit chỉ đếm job **đang thực thi**, còn queue có thể chứa nhiều task hơn, cần giới hạn queue riêng.
3. **Trong HTTP controller đồng bộ:** permit bao quanh lời gọi nghiệp vụ, đếm số invocation đang ở vùng này; không nhất thiết trùng với tổng request đang mở socket.

Không có cách chọn nào mặc định đúng cho mọi hệ thống. Hãy đặt tên chỉ số đúng phạm vi, chẳng hạn `downstream_in_flight`, `executor_active` và `executor_queued`.

## 6. Rate limiter hoạt động ra sao?

Rate limiter quyết định có cấp **lượt bắt đầu** tại thời điểm yêu cầu đến hay không, dựa vào chính sách thời gian.

### 6.1. Fixed window

Cho tối đa 60 request trong mỗi phút lịch:

~~~text
Phút A:  [60 lần được nhận]  [lần 61: từ chối]
Phút B:  [đếm lại từ 0]
~~~

Ưu điểm là dễ hiểu và triển khai. Nhược điểm: ở **ranh giới** hai cửa sổ, một client có thể gửi 60 request sát cuối phút A và 60 request sát đầu phút B, tạo burst 120 request trong khoảng rất ngắn. Vì thế “60/phút fixed window” không tương đương “mọi khoảng trượt dài 60 giây chỉ được 60”.

### 6.2. Sliding window

Đếm các request trong **khoảng thời gian trượt** (hoặc dùng xấp xỉ/bucket). Cách này kiểm soát burst sát biên tốt hơn, nhưng trạng thái và độ phức tạp có thể cao hơn fixed window. Phải xác định chính xác window tính theo thời điểm nào, dữ liệu lưu ở đâu, và cách cleanup.

### 6.3. Token bucket

Bucket chứa tối đa `B` token; hệ thống bổ sung token theo tốc độ `r` token/giây. Mỗi request tiêu thụ token (hoặc số token tỷ lệ chi phí). Nếu không đủ token, request chờ hoặc bị từ chối.

- `r` xác định tốc độ nạp trung bình dài hạn.
- `B` xác định burst tối đa có thể được hấp thụ nếu bucket đầy.
- Token đã dùng không được “trả lại” chỉ vì request kết thúc; chúng được bổ sung theo thời gian.

Ví dụ `r = 10 token/s` và `B = 20` có thể chấp nhận burst 20 request ngay khi bucket đầy, rồi tiếp tục cấp theo nhịp bổ sung. Đó không phải bảo đảm tối đa 10 request trong **mọi** khoảng 1 giây.

### 6.4. Leaky bucket và hàng đợi có kiểm soát

Một bộ điều tiết có thể cho request đi ra với nhịp tương đối đều, đặt phần dư vào queue hữu hạn. Nếu queue đầy thì từ chối. Giải pháp này giảm burst đến downstream nhưng đổi lại độ trễ chờ. **Queue phải có capacity và timeout**: một hàng đợi không giới hạn không biến hệ thống thành vô hạn tài nguyên.

### 6.5. Quyền theo thời gian không giới hạn thời lượng xử lý

Giới hạn “10 requests mỗi giây” vẫn có thể tạo ra 100 invocation đồng thời nếu mỗi invocation cần 10 giây. Vì vậy, khi rủi ro là cạn số connection hoặc tác vụ chậm chiếm tài nguyên, cần thêm concurrency limiter/bulkhead.

## 7. Java 17 chạy được: mô phỏng hai giới hạn độc lập

Ví dụ sau sử dụng **cùng một chương trình** để minh họa:

- `Semaphore(2)` chỉ cho hai tác vụ giữ permit đồng thời.
- Bộ đếm fixed window chỉ cho ba lượt được phép trong mỗi cửa sổ 1.000 ms.
- `CountDownLatch` khóa các mốc của thí nghiệm để output ổn định. Các mốc thời gian của fixed window được **truyền tường minh** cho mục đích kiểm thử; bản demo không khẳng định đây là rate limiter production hoàn chỉnh.

Lưu vào tệp **`LimitsDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class LimitsDemo {
    static final class FixedWindow {
        private final int quota;
        private final long periodMillis;
        private long currentWindow = Long.MIN_VALUE;
        private int used;

        FixedWindow(int quota, long periodMillis) {
            if (quota <= 0 || periodMillis <= 0) {
                throw new IllegalArgumentException("limits must be positive");
            }
            this.quota = quota;
            this.periodMillis = periodMillis;
        }

        synchronized boolean allowAt(long millis) {
            long window = Math.floorDiv(millis, periodMillis);
            if (window != currentWindow) {
                currentWindow = window;
                used = 0;
            }
            if (used >= quota) {
                return false;
            }
            used++;
            return true;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        CountDownLatch bothInside = new CountDownLatch(2);
        CountDownLatch releaseWorkers = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        Runnable slowJob = () -> {
            if (!slots.tryAcquire()) {
                throw new IllegalStateException("unexpected rejection");
            }
            try {
                int now = inFlight.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                bothInside.countDown();

                try {
                    releaseWorkers.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                inFlight.decrementAndGet();
                slots.release();
            }
        };

        Thread first = new Thread(slowJob);
        Thread second = new Thread(slowJob);
        first.start();
        second.start();

        bothInside.await(); // Chắc chắn cả hai đang giữ permit.
        boolean thirdAccepted = slots.tryAcquire();
        if (thirdAccepted) {
            slots.release();
        }

        System.out.println("inFlight = " + inFlight.get());
        System.out.println("thirdAccepted = " + thirdAccepted);

        releaseWorkers.countDown();
        first.join();
        second.join();
        System.out.println("peakInFlight = " + peak.get());
        System.out.println("permitsAfter = " + slots.availablePermits());

        FixedWindow rate = new FixedWindow(3, 1_000);
        int accepted = 0;
        for (int i = 0; i < 5; i++) {
            if (rate.allowAt(0)) {
                accepted++;
            }
        }
        System.out.println("t=0ms accepted = " + accepted);
        System.out.println("t=999ms accepted = " + rate.allowAt(999));
        System.out.println("t=1000ms accepted = " + rate.allowAt(1_000));

        // Hai cửa sổ liền kề đều có quota riêng.
        FixedWindow boundary = new FixedWindow(3, 1_000);
        int boundaryAccepted = 0;
        for (int i = 0; i < 3; i++) {
            if (boundary.allowAt(999)) boundaryAccepted++;
        }
        for (int i = 0; i < 3; i++) {
            if (boundary.allowAt(1_000)) boundaryAccepted++;
        }
        System.out.println("boundaryAccepted = " + boundaryAccepted);
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac LimitsDemo.java
java LimitsDemo
~~~

**Stdout xác định:**

~~~text
inFlight = 2
thirdAccepted = false
peakInFlight = 2
permitsAfter = 2
t=0ms accepted = 3
t=999ms accepted = false
t=1000ms accepted = true
boundaryAccepted = 6
~~~

**Vì sao kết quả xác định?**

1. Hai worker nhận đúng hai permit và gọi `bothInside.countDown()` sau khi tăng `inFlight`; main chỉ tiếp tục khi cả hai đã vào vùng được bảo vệ.
2. Cả hai worker đợi ở `releaseWorkers.await()`, nên lần `tryAcquire()` của main chắc chắn thất bại và in `false`.
3. Main mở latch, dùng `join()` trước khi kiểm tra peak/permit; tránh race trong phép quan sát kết quả.
4. Bộ fixed-window được gọi với mốc thời gian giả lập `0`, `999`, `1000`, không cần dựa vào đồng hồ thực hoặc `sleep`.
5. `boundaryAccepted = 6` cho thấy ba lượt ở cuối một window và ba lượt ở đầu window tiếp theo đều được nhận, dù khoảng cách giữa hai mốc chỉ **1 ms**.

**Giới hạn của ví dụ:** `FixedWindow.allowAt` đồng bộ trong một đối tượng JVM và cho phép người gọi đưa vào thời gian. Trong hệ thống thật phải dùng nguồn thời gian đáng tin, xử lý lệch đồng hồ, làm mới trạng thái, khóa atomic và nhiều replica; nên dùng thư viện/gateway phù hợp thay vì copy class này sang production.

## 8. Áp dụng giới hạn đồng thời trong Spring MVC

Với một HTTP endpoint **đồng bộ**, có thể khai báo semaphore thành bean và bao lời gọi nghiệp vụ bằng permit.

### 8.1. Bean cấu hình

Trong dự án Spring Web có cấu hình component scan tương ứng, tệp **`CapacityConfiguration.java`**:

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CapacityConfiguration {
    @Bean("reportSlots")
    public Semaphore reportSlots() {
        return new Semaphore(8);
    }
}
~~~

Đây là cấu hình Spring: container quản lý một instance semaphore mặc định trên **mỗi application context**, phục vụ những consumer inject cùng bean. Nó không tự tạo quota toàn cụm khi triển khai nhiều JVM.

### 8.2. Service bảo vệ đoạn xử lý

Tệp **`ReportService.java`**:

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final Semaphore reportSlots;

    public ReportService(@Qualifier("reportSlots") Semaphore reportSlots) {
        this.reportSlots = reportSlots;
    }

    public String generate(long id) {
        if (!reportSlots.tryAcquire()) {
            throw new CapacityExceededException();
        }
        try {
            // Trong ứng dụng thật, đây là lời gọi nghiệp vụ đồng bộ.
            return "report-" + id;
        } finally {
            reportSlots.release();
        }
    }

    public static final class CapacityExceededException
            extends RuntimeException {
    }
}
~~~

Tệp **`ReportController.java`**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports/{id}")
    public String getReport(@PathVariable long id) {
        return reports.generate(id);
    }
}
~~~

Các class này là **thành phần của dự án Spring MVC**, cần dependency Web và ứng dụng Spring đã khởi động; chúng không phải chương trình Java SE có `main`. Các class đặt trong cùng package (hoặc bổ sung `import` phù hợp) để tham chiếu `ReportService`.

### 8.3. Phản hồi quá tải

Để minh họa lỗi tài nguyên tạm thời, tệp **`CapacityAdvice.java`**:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CapacityAdvice {
    @ExceptionHandler(ReportService.CapacityExceededException.class)
    public ResponseEntity<String> busy() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("Server capacity exhausted");
    }
}
~~~

Ở đây dùng **503 Service Unavailable** để diễn đạt quá tải tạm thời của server. Khi quota theo user/khách hàng vượt ngưỡng **số request trong thời gian**, **429 Too Many Requests** thường có ý nghĩa rõ hơn. Đây là cách ánh xạ theo mục đích; chuẩn HTTP không bắt buộc mọi sự kiện thiếu permit phải trả đúng một mã duy nhất.

Ví dụ trả chuỗi ngay chỉ cho thấy cấu trúc lấy/trả permit; nó không tái hiện thời gian xử lý dài. Trong dự án thật, vùng `try/finally` phải bao trọn lời gọi downstream, truy xuất hoặc tính toán cần giới hạn. Đừng trả permit ngay sau khi chỉ **submit** một công việc bất đồng bộ nếu công việc đó còn đang chạy.

### 8.4. Khi service trả CompletableFuture hoặc Mono

Với lời gọi bất đồng bộ, ranh giới tài nguyên thường kéo dài tới khi công việc thực sự **hoàn thành, thất bại hoặc bị hủy**, thay vì chỉ khi phương thức schedule trả về.

Ví dụ mẫu `CompletableFuture` (giả định `asyncClient.fetch(id)` trả `CompletableFuture<String>` và `slots` là semaphore):

~~~java
if (!slots.tryAcquire()) {
    return CompletableFuture.failedFuture(
            new IllegalStateException("busy"));
}
try {
    return asyncClient.fetch(id)
            .whenComplete((result, failure) -> slots.release());
} catch (RuntimeException ex) {
    slots.release();
    throw ex;
}
~~~

**Đoạn minh họa không độc lập**, cần context khai báo `slots` và `asyncClient`. Permit được trả bởi completion callback hoặc khi việc tạo future thất bại đồng bộ. Cần kiểm soát thêm các đường cancel/timeout của client thật. Với Reactor `Mono`/`Flux`, thời điểm subscription, terminal signal và cancellation có ý nghĩa riêng; một cấu trúc như `doFinally(...)` thường phù hợp để dọn tài nguyên, nhưng phải thiết kế để permit được lấy tại đúng thời điểm subscribe và được trả đúng một lần. Không áp dụng máy móc `try/finally` bao quanh lúc tạo Publisher rồi tưởng rằng tác vụ reactive đã xong.

## 9. ThreadPoolTaskExecutor có phải rate limiter không?

**Không.** `ThreadPoolTaskExecutor` quản lý **số worker và hàng đợi** trong một JVM:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
    e.setCorePoolSize(4);
    e.setMaxPoolSize(4);
    e.setQueueCapacity(20);
    e.setThreadNamePrefix("reports-");
    return e;
}
~~~

Đây là **snippet cấu hình Spring**, cần các import `@Bean`, `ThreadPoolTaskExecutor` và lớp `@Configuration`. Container quản lý khởi tạo và shutdown. Với ví dụ cấu hình này:

- Tối đa **4 worker** của pool chạy task cùng lúc theo cách phân bổ thông thường.
- Có thể có tối đa **20 task đang chờ trong queue** trước khi xảy ra từ chối, nếu worker đang bận và task không kết thúc kịp.
- Những task rất ngắn có thể xử lý hàng trăm hoặc hàng nghìn lần mỗi giây; `corePoolSize=4` không có nghĩa 4 RPS.
- Task trong queue tiêu thụ RAM và kéo dài thời gian chờ, dù không tính vào `getActiveCount()`.
- Handler từ chối như `CallerRunsPolicy` có thể cho task chạy **trên thread nộp việc**, nên ngay cả giả định “chỉ 4 execution đồng thời trên toàn JVM” cũng không đúng nếu caller-runs cho phép thực thi ngoài pool. `AbortPolicy` từ chối minh bạch hơn khi không thể nhận thêm task.

**Giới hạn pool thread** không đồng nhất với giới hạn tổng HTTP in-flight, số connection DB hoặc số invocation đồng thời tới downstream. Khi cần bảo vệ một tài nguyên cụ thể, đặt semaphore/bulkhead **sát ranh giới gọi tài nguyên đó**.

Một executor với queue rất dài đôi khi che giấu sự quá tải bằng cách tăng latency. Hãy đo queue depth, task wait time và rejected count. Không thiết kế một “rate limiter” chỉ bằng `Thread.sleep(...)` trong worker: sleep vẫn giữ worker và có thể tạo backlog lớn.

## 10. Hai lớp bảo vệ phối hợp như thế nào?

Giả sử API tra cứu tài liệu có hai ràng buộc:

- Mỗi API key: tối đa **60 request/phút**, để kiểm soát mức sử dụng công bằng.
- Mỗi instance service: tối đa **8 lời gọi tới hệ thống tìm kiếm** cùng lúc, vì downstream có connection/quota hữu hạn.

Luồng đề xuất:

~~~text
HTTP / API Gateway
    |
    +-- Xác thực, xác định API key / tenant
    |
    v
Rate limiter: 60 yêu cầu/phút/key
    |
    +-- Vượt quota -> 429, có thể kèm Retry-After
    |
    v
Spring controller / service
    |
    v
Semaphore / Bulkhead: tối đa 8 lời gọi downstream/instance
    |
    +-- Hết slot -> chờ ngắn có kiểm soát hoặc 503
    |
    v
Call downstream -> trả permit -> response
~~~

Có thể đảo thứ tự ở những trường hợp khác, nhưng phải cân nhắc chi phí: nếu làm I/O tốn kém **trước** khi rate limit thì người dùng vượt quota vẫn chiếm tài nguyên; nếu giữ semaphore trong lúc xếp hàng chờ rate token thì permit bị tiêu hao do chờ, không phải do xử lý nghiệp vụ.

| Câu hỏi cấu hình | Trả lời cần có |
| --- | --- |
| Quota theo ai? | Từng user, API key, tenant hay toàn hệ thống? |
| Đếm sự kiện nào? | Mọi request đến, request hợp lệ, request được chấp nhận hay lời gọi downstream? |
| Giới hạn đồng thời đoạn nào? | Controller synchronous, HTTP client, DB connection hay một task worker? |
| Khi quá ngưỡng? | Từ chối ngay, chờ timeout, xếp hàng hữu hạn hay retry ở tầng trên? |
| Phạm vi chia sẻ? | Mỗi process, mỗi pod, mỗi region hay toàn cụm? |
| Cần giữ sau restart? | Quota ngắn hạn ở local memory hay trạng thái bền vững? |
| Có burst không? | Burst tối đa `B`, period và thuật toán window/token bucket? |

Một hệ thống có thể cần cả **rate limiter ở đầu vào** lẫn **concurrency limiter ở các tài nguyên trọng yếu**; hai lớp đo các sự kiện riêng và có thể có chỉ số/tên policy riêng.

## 11. Thư viện phù hợp: Bulkhead và RateLimiter

Trong ứng dụng Spring, có thể dùng thư viện **Resilience4j** thay cho tự viết các bộ giới hạn production:

- **Semaphore Bulkhead**: giới hạn số lời gọi đồng thời tới một dependency (`maxConcurrentCalls`); permit được trả khi phạm vi gọi kết thúc theo hợp đồng thư viện.
- **ThreadPool Bulkhead**: dùng pool riêng với queue hữu hạn để cách ly workload; cấu hình core/max pool và queue.
- **RateLimiter**: cấp quyền theo `limitForPeriod` và `limitRefreshPeriod`, với `timeoutDuration` quyết định thời gian chờ để được cấp quyền.

Một cấu hình **minh họa** trong `application.yml` của dự án đã cài Resilience4j Spring Boot starter tương thích:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      partnerApi:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  bulkhead:
    instances:
      partnerApi:
        maxConcurrentCalls: 8
        maxWaitDuration: 0
~~~

Ý nghĩa của cấu hình: RateLimiter cấp tối đa 30 permit mỗi chu kỳ 1 giây theo thuật toán của thư viện, không chờ thêm khi hết quota; Bulkhead cho tối đa 8 lời gọi chạy đồng thời và không chờ khi đầy. Đây là **hai policy độc lập**; cấu hình này chỉ có hiệu lực nếu ứng dụng đã thêm dependency/aspect/decorator và thực sự áp chúng cho lời gọi mong muốn.

Ví dụ annotate method trong ứng dụng có AOP Resilience4j được bật:

~~~java
@RateLimiter(name = "partnerApi")
@Bulkhead(name = "partnerApi")
public String requestPartner(String id) {
    return partnerClient.fetch(id);
}
~~~

Đây là **method snippet**, giả định có `partnerClient` và các import `io.github.resilience4j.ratelimiter.annotation.RateLimiter`, `io.github.resilience4j.bulkhead.annotation.Bulkhead`. Khi dùng AOP, cần hiểu thứ tự aspect, self-invocation, phương thức async/reactive và cách mapper xử lý exception (chẳng hạn `RequestNotPermitted` hoặc `BulkheadFullException`). Không mặc nhiên suy ra các annotation tự hoạt động nếu thiếu starter/config hoặc lời gọi không đi qua proxy.

**Đặc biệt:** Resilience4j RateLimiter giới hạn theo permission/cycle; nó không tự tạo quota **tập trung giữa nhiều pod** nếu mỗi pod có limiter local. Với quota global, lựa chọn API gateway hoặc backend trạng thái dùng chung sẽ thích hợp hơn.

## 12. Nhiều instance Spring: cộng gộp giới hạn ra sao?

Giả sử triển khai **3 pod**, mỗi pod có:

~~~text
Semaphore(8)
RateLimiter(60 request/phút)
~~~

Nếu mỗi pod giữ trạng thái độc lập và load balancer phân phối đều, mức thực tế toàn cụm **có thể** lên tới khoảng **24 lời gọi đồng thời** và **180 lượt/phút** trong mô hình lý tưởng. Không được quảng bá “8 concurrent toàn hệ thống” hoặc “60/phút toàn hệ thống” khi implementation chỉ bảo vệ từng pod.

Mô hình tổng quát:

~~~text
N pod độc lập, mỗi pod có C slot  ->  tối đa khoảng N*C slot
N pod độc lập, mỗi pod quota R   ->  có thể nhận tổng gần N*R/period
~~~

Thực tế phụ thuộc cách phân phối request, churn/rolling deployment, replica scale và thuật toán; không phải cam kết tổng cố định.

Muốn giới hạn toàn cụm:

- **Rate limit global:** áp tại API gateway hoặc trạng thái chia sẻ như Redis với **thao tác cấp quyền atomic**. Key phải biểu diễn đúng phạm vi user/tenant/API; đặt TTL/expiry đúng và có chính sách khi store lỗi.
- **Concurrency limit global:** cần cơ chế điều phối số lease/slot trên toàn cụm, timeout/heartbeat và giải phóng khi node chết. Đây là vấn đề khó hơn chỉ dùng local `Semaphore`; có thể giới hạn sát tài nguyên downstream thay vì dùng lock phân tán nếu kiến trúc cho phép.
- **Kết hợp:** rate global cho fairness/quota, concurrency local để bảo vệ tài nguyên của mỗi pod, và có thể thêm cap ở downstream.
- **Clock:** đối với điều tiết thời gian trong một tiến trình, dùng nguồn monotonic để tính elapsed time khi phù hợp; với limiter tập trung, nên dựa trên đồng hồ/logic phía store để hạn chế lệch giờ giữa replica.

Nếu hệ thống autoscale, quota local thay đổi tổng sức chứa khi tăng/giảm số pod. Hãy ghi rõ policy là **per instance** hay **cluster-wide** và kiểm thử khi scale.

## 13. HTTP 429 và 503, Retry-After và backpressure

### 13.1. Khi nào dùng 429?

**HTTP 429 Too Many Requests** theo RFC 6585 biểu thị client gửi quá nhiều request trong một khoảng thời gian. Nó phù hợp khi một user/API key vượt quota rate limit. Server có thể gửi `Retry-After` để gợi ý thời điểm thử lại khi biết chính sách hạn mức.

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: text/plain

Rate limit exceeded
~~~

`Retry-After: 30` biểu thị gợi ý chờ **30 giây**, không phải số permit hoặc mức concurrency. Đừng tự đặt thời gian chờ nếu thuật toán không thể xác định thời điểm có quyền tiếp theo.

### 13.2. Khi nào dùng 503?

**HTTP 503 Service Unavailable** theo RFC 9110 thường dùng cho dịch vụ tạm thời không xử lý nổi vì quá tải hoặc bảo trì. Nó có thể phù hợp khi global capacity/bulkhead đã đầy. Có thể kèm `Retry-After` khi có cơ sở dự đoán khoảng chờ.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

Service temporarily busy
~~~

Mã lỗi cụ thể còn phụ thuộc API contract: cùng một semaphore có thể thực hiện **quota theo khách hàng** hoặc **bảo vệ sức chứa server**. Phải phân tích nguyên nhân và hợp đồng với client, không biến các mã 429/503 thành một luật cứng cho mọi trường hợp.

### 13.3. “Chờ” là quyết định về tài nguyên

Khi vượt ngưỡng có thể:

1. **Fail fast:** từ chối ngay, giữ latency nhỏ và tránh tồn đọng. Cần client retry có backoff + jitter khi hợp lệ.
2. **Wait có timeout:** cho một khoảng chờ ngắn, nhưng request thread/connection cũng chiếm tài nguyên trong lúc đợi.
3. **Queue hữu hạn:** đổi burst thành backlog; cần capacity, deadline, metrics và chính sách hủy.
4. **Persist rồi xử lý nền:** trả job ID và dùng queue/job store bền vững nếu nghiệp vụ cho phép bất đồng bộ.

Chờ vô hạn, queue vô hạn và retry không giới hạn có thể biến một sự cố nhỏ thành hàng loạt request tồn đọng. Timeout phải được thiết kế từ deadline tổng của request, không đặt riêng lẻ từng lớp mà tổng thời gian vượt SLA.

## 14. Chọn ngưỡng đúng: đo trước rồi hiệu chỉnh

Một quy trình thực tế:

1. **Xác định nút thắt:** database pool 20 connections, downstream chỉ chịu 8 request đồng thời, CPU, memory, hoặc quota API đối tác 100 request/phút.
2. **Tách hai yêu cầu:** cap concurrency để bảo vệ số slot hữu hạn; rate cap để kiểm soát tốc độ/chi phí/khách hàng.
3. **Đo workload:** thời gian trung bình và p95/p99, số active, queue wait, throughput, tỷ lệ lỗi, timeout, tải CPU, saturation downstream.
4. **Tính sơ bộ bằng Little's Law:** nếu throughput mục tiêu 40 req/s và thời gian giữ tài nguyên trung bình 0,2 s, cần khoảng 8 in-flight *trung bình*; cộng headroom hợp lý dựa trên burst/tail latency, không coi 8 là hard-cap tối ưu chắc chắn.
5. **Chọn thuật toán rate:** cần burst 10? dùng token bucket có capacity thích hợp; cần quota chính xác mỗi 24 giờ? dùng cơ chế đếm/window phù hợp.
6. **Giới hạn queue và wait:** có deadline, mô tả phản hồi khi không còn capacity.
7. **Áp policy đúng scope:** per-user, per-instance hoặc toàn cụm; có kế hoạch thay đổi khi autoscale.
8. **Load test và chaos test:** vừa tải đều vừa burst, downstream chậm, timeout/cancel, nhiều pod, rolling deployment và store rate limit lỗi.

Ví dụ chọn ngưỡng:

| Bài toán | Giới hạn phù hợp hơn | Lý do |
| --- | --- | --- |
| DB chỉ có 20 kết nối, query chậm | Concurrency cap nhỏ hơn hoặc tương ứng tài nguyên thực | Ngăn quá nhiều truy vấn cùng chiếm connection |
| API đối tác cho 300 calls/phút | Rate cap có state chính xác theo scope của quota | Tuân thủ hạn mức gọi theo thời gian |
| Cần tránh một tenant chiếm hết API | Rate quota theo tenant + concurrency cap tùy nhu cầu | Cân bằng lượt truy cập và tài nguyên đang dùng |
| Hàng nghìn tác vụ nhanh trong vài giây | Rate bucket có burst được định nghĩa | Điều tiết peak dù thời gian chạy rất ngắn |
| Một số task chạy treo nhiều phút | Concurrency cap + timeout/cancel | Rate cap đơn lẻ không thu hồi tài nguyên đang bị giữ |
| Process có nhiều executor | Giới hạn theo dependency, không chỉ worker count | Nhiều pool có thể cùng gọi một dependency |

## 15. Metrics và kiểm thử hai lớp tách biệt

### Metrics cho concurrency

- `in_flight`: gauge số permit đang giữ tại một thời điểm, gắn nhãn phạm vi tài nguyên.
- `available_permits`, số lần `tryAcquire` thất bại, thời gian đợi permit, timeout.
- Thread pool: `activeCount`, `poolSize`, `queueSize`, số lần reject.
- Thời gian giữ slot, số task bị hủy và việc release permit đúng một lần.

### Metrics cho rate

- Accepted/denied requests theo khoảng thời gian, API key/tenant (kiểm soát cardinality).
- Token còn lại hoặc quota còn lại, refresh cycles, số lượt chờ token.
- Tỷ lệ HTTP 429, tốc độ gửi thực tế, burst và sai khác giữa replica.
- Khi một policy đổi ngưỡng, theo dõi hiệu ứng với latency và 5xx, không chỉ tỷ lệ 429.

### Các bài test cần có

**Test concurrency:** dùng latch cho một nhóm tác vụ giữ slot và thử thêm task. Assert số đang giữ **không bao giờ vượt C**, sau đó release và xác nhận permit được trả kể cả khi exception.

**Test rate:** dùng **đồng hồ giả lập hoặc clock abstraction** để kiểm tra chính xác cửa sổ, refill, ranh giới hai window và các yêu cầu cạnh tranh cùng lúc. Tránh dùng `Thread.sleep(1000)` làm điều kiện pass.

**Test kết hợp:** nộp nhiều tác vụ chậm trong khi vẫn ở dưới quota RPS. Rate limiter có thể vẫn cho đi qua, nhưng concurrency limiter phải bảo vệ downstream. Ngược lại, nộp nhiều tác vụ cực nhanh: concurrency có thể luôn thấp, nhưng rate limiter phải chặn burst vượt quota.

**Test phân tán:** khởi động nhiều instance cùng dùng key quota và kiểm tra tổng số lượt nhận; kiểm tra scale-up/rolling restart, timeout của store và request đồng thời ở ranh giới thời gian.

Khi kiểm tra kết quả, hãy phân biệt `allowed`, `queued`, `started`, `completed`, `rejected`; năm trạng thái này không phải một chỉ số.

## 16. Những sai lầm phổ biến

1. **“10 worker = 10 RPS.”** Sai: worker hạn chế việc chạy đồng thời, RPS còn phụ thuộc thời gian xử lý. Với task ngắn, RPS có thể lớn hơn nhiều.
2. **“100 RPS = tối đa 100 request đang chạy.”** Sai: request kéo dài nhiều giây có thể tạo số in-flight lớn hơn nhiều.
3. **“ThreadPoolTaskExecutor đã là rate limiter.”** Sai: pool và queue không tự cấp quota theo thời gian.
4. **“Semaphore.release() khi submit Future là được.”** Sai nếu công việc thực sự còn chạy; release phải gắn với completion/cancel/exception đúng nghĩa.
5. **“Token được trả ngay khi response hoàn thành.”** Sai với rate limiter thời gian; quota phục hồi theo policy, không theo thời lượng request.
6. **“Fixed window 60/phút bảo đảm mọi 60 giây trượt chỉ 60.”** Sai ở ranh giới cửa sổ.
7. **“Giới hạn ở từng pod chính là global limit.”** Sai nếu các pod không chia sẻ cùng state/coordinator.
8. **“Queue lớn giúp hệ thống khỏe hơn mà không có giá.”** Sai: tăng thời gian đợi và RAM, có thể che giấu overload tới lúc deadline hết.
9. **“Cứ vượt semaphore là HTTP 429.”** Không nhất thiết; khi server hết capacity tạm thời, 503 có thể mô tả nguyên nhân tốt hơn.
10. **“Chỉ cần tăng concurrency limit để tăng throughput.”** Sai khi downstream/database/CPU đã bão hòa; tăng song song có thể làm latency và tỷ lệ lỗi tăng.
11. **“Chờ permit vô hạn là an toàn.”** Sai: caller thread và request connection tiếp tục bị giữ, dễ khuếch đại overload.
12. **“Đã có @Async thì không cần giới hạn.”** Sai: `@Async` chỉ điều phối thực thi, không tự bảo vệ downstream và không tự tạo rate quota.
13. **“Chỉ đọc số request/giây là biết hệ thống an toàn.”** Sai: cần thêm in-flight, tail latency, queue, lỗi, saturation.
14. **“Sử dụng một HashMap và System.currentTimeMillis không cần đồng bộ là đủ.”** Sai: rate state có thể race, đồng hồ wall-clock có thể bị chỉnh, phân tán càng phức tạp.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Một API áp `Semaphore(5)`, xử lý mỗi request trung bình 100 ms. Điều đó có nghĩa tối đa 5 RPS không?

**Đáp án:** không. `5` là số công việc đồng thời. Trong mô hình lý tưởng với 5 slot luôn bận và mỗi task 0,1 giây, throughput xấp xỉ 50 req/s; không bảo đảm con số đó nếu có overhead hoặc nút thắt khác.

**Câu 2.** Một API giới hạn 30 request/giây, nhưng mỗi request mất 4 giây. Có nguy cơ hơn 30 in-flight không?

**Đáp án:** có. Với tải ổn định, Little's Law cho khoảng `30 × 4 = 120` in-flight trung bình nếu không bị chặn bởi tài nguyên khác.

**Câu 3.** Pool có 4 worker và queue 100. Tại sao nhiều task được “accept” nhưng chỉ 4 task đang chạy?

**Đáp án:** `ThreadPoolTaskExecutor` giữ nhiều task trong hàng đợi; `active worker` khác `accepted/queued job`. Không phải rate limiter.

**Câu 4.** Fixed window 60 request/phút cho phép 60 lượt ở cuối phút cũ và 60 lượt ở đầu phút mới không?

**Đáp án:** có thể, tùy thời điểm reset cửa sổ. Đây là vấn đề burst sát ranh giới; cân nhắc sliding window/token bucket nếu yêu cầu kiểm soát burst tốt hơn.

**Câu 5.** Có ba pod, mỗi pod `Semaphore(10)`. Khi không có coordinator chung, có thể báo cáo “tối đa 10 request đồng thời toàn cụm” không?

**Đáp án:** không. Trong điều kiện đều có tải, tổng có thể lên gần 30 permit; 10 chỉ là ngưỡng cục bộ từng pod.

**Câu 6.** Đang dùng `@Async`, nên release semaphore ngay sau lời gọi phương thức async hay khi future hoàn tất?

**Đáp án:** nếu permit bảo vệ công việc async đang thực hiện, phải gắn release với **hoàn thành/thất bại/hủy** của công việc, không phải ngay lúc nhận future, và cần bảo đảm không release hai lần.

**Câu 7.** Một user bị chặn vì vượt 100 request/phút; nên dùng 429 hay 503?

**Đáp án:** 429 mô tả quota theo thời gian của client phù hợp hơn. Nếu service đang quá tải hệ thống và từ chối tạm thời do hết năng lực xử lý, 503 có thể phù hợp hơn.

## 18. Checklist trước khi triển khai

- [ ] Đã ghi rõ cap là **concurrency** hay **rate**, có đơn vị cụ thể và phạm vi đo.
- [ ] Concurrency: xác định sự kiện lấy permit, thời điểm hoàn trả, xử lý lỗi/cancel và chờ có giới hạn.
- [ ] Rate: xác định thuật toán, window/refill, burst, key quota, nơi lưu state và chính sách chờ.
- [ ] Đã phân biệt task **queued**, **running**, **in-flight request** và **completed**.
- [ ] Có giới hạn riêng cho thread pool, queue, DB connection và downstream nếu cần.
- [ ] Đã kiểm tra behavior trên nhiều pod và khi autoscale.
- [ ] Đã thiết kế HTTP 429/503, thông điệp lỗi và `Retry-After` khi có thể đưa ra.
- [ ] Metrics có cả rate, in-flight, queue, latency và rejection.
- [ ] Test có burst, slow dependency, cancellation, overload, shutdown và giới hạn toàn cụm.
- [ ] Không coi `Semaphore` hoặc `RateLimiter` là giải pháp persistence, idempotency hay durability cho job.

## 19. Tổng kết

**Concurrency limit** trả lời: *“Có bao nhiêu công việc được phép giữ tài nguyên cùng lúc?”* Quyền thường được **trả lại khi công việc kết thúc**. **Rate limit** trả lời: *“Trong thời gian này có bao nhiêu lượt được phép bắt đầu?”* Quyền thường được **phục hồi theo thời gian**.

Vì tốc độ và thời lượng tác vụ khác nhau, hai giới hạn độc lập về mặt ý nghĩa. Trong Spring, dùng một **Semaphore/Bulkhead** để bảo vệ số lời gọi in-flight tới tài nguyên khan hiếm, một **RateLimiter/gateway** cho quota theo thời gian, và cấu hình `ThreadPoolTaskExecutor` cùng queue hữu hạn để quản lý worker. Đo, kiểm thử và mô tả đúng phạm vi local/global của từng giới hạn trước khi mở rộng ứng dụng.

## Tài liệu tham khảo

- Java SE 17 — `Semaphore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Resilience4j — RateLimiter: https://resilience4j.readme.io/docs/ratelimiter
- Resilience4j — Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- [RFC 6585, Section 4 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 9110, Section 15.6.4 — 503 Service Unavailable](https://www.rfc-editor.org/rfc/rfc9110.html)
