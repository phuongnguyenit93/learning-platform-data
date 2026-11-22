# Phân biệt đồng bộ, bất đồng bộ, song song và lập lịch trong Spring Framework

Bốn thuật ngữ **đồng bộ (synchronous)**, **bất đồng bộ (asynchronous)**, **song song (parallel)** và **lập lịch (scheduling)** thường xuất hiện cùng nhau khi xây dựng ứng dụng Spring, nhưng chúng trả lời **bốn câu hỏi khác nhau**. Nhầm lẫn chúng dễ dẫn đến thiết kế API gây chờ đợi không cần thiết, cấu hình thread pool sai, công việc chạy trùng hoặc giả định một tác vụ đã hoàn thành khi nó mới được đưa vào hàng đợi.

Sau bài này, bạn cần phân biệt được hành vi của bên gọi, cách công việc được thực thi, thời điểm kích hoạt và các thành phần Spring phù hợp; đồng thời nhận ra khi nào các cơ chế có thể kết hợp với nhau.

## 1. Bản chất của từng khái niệm

### 1.1. Đồng bộ: bên gọi chờ kết quả

Một lời gọi **đồng bộ** chỉ hoàn thành đối với bên gọi khi thao tác đã trả về kết quả hoặc ném lỗi. Trong thời gian đó, luồng xử lý của bên gọi chưa thể chuyển qua câu lệnh kế tiếp. Ví dụ:

```java
String report = reportService.generate("R1"); // Chờ generate hoàn thành
sendResponse(report);                         // Chỉ chạy sau khi có report
```

Hãy tưởng tượng trình tự:

```text
Caller:  gọi generate ───────────── chờ ───────────── nhận kết quả → tiếp tục
Công việc:              bắt đầu → xử lý → kết thúc
```

Điểm cốt lõi là **quan hệ chờ giữa lời gọi và kết quả**, không phải số lượng thread. Một phương thức có thể giao việc sang thread khác nhưng gọi `Future.get()` hoặc `CompletableFuture.join()` ngay lập tức; về trải nghiệm của bên gọi, đoạn mã đó vẫn chờ đồng bộ.

### 1.2. Bất đồng bộ: bên gọi tiếp tục trước khi công việc xong

Một thao tác **bất đồng bộ** cho phép bên gọi nhận lại quyền điều khiển trước khi công việc kết thúc. Kết quả đến sau qua `CompletableFuture`, callback, sự kiện, hàng đợi hoặc một cơ chế thông báo khác.

```java
CompletableFuture<String> result = reportService.generateAsync("R1");
doOtherWork();                  // Có thể chạy khi generateAsync còn xử lý
String report = result.join();  // Chỉ đến đây mới chờ nếu kết quả chưa sẵn sàng
```

```text
Caller:   gọi → nhận Future → làm việc khác ── join/đọc kết quả → tiếp tục
Worker:          nhận task ── thực thi ── hoàn thành Future
```

Bất đồng bộ **không đồng nghĩa** với: chạy nhanh hơn, luôn có thread mới, không dùng thread, không bao giờ chờ, hoặc công việc chắc chắn chạy song song. Một Future có thể hoàn thành ngay; bên gọi cũng có thể tự làm mất lợi ích bất đồng bộ bằng cách `join()` ngay sau lúc gửi việc.

Trong Spring, `@Async` thường giao phương thức cho một `TaskExecutor`, giúp thread gọi phương thức không cần trực tiếp làm toàn bộ công việc. Tuy nhiên, thread worker vẫn có thể bị chặn bởi I/O đồng bộ bên trong.

### 1.3. Song song: nhiều công việc thực sự chạy cùng lúc

**Song song** mô tả **cách thực thi**: hai hay nhiều phần việc cùng tiến triển tại một thời điểm trên các tài nguyên xử lý khác nhau (thường là nhiều lõi CPU). Mục tiêu phổ biến là giảm thời gian xử lý tổng của công việc có thể chia nhỏ.

Phân biệt thêm với **concurrency (tính đồng thời)**:

- **Concurrency:** nhiều tác vụ đang được quản lý trong cùng khoảng thời gian; trên một lõi CPU, chúng có thể xen kẽ từng lượt chạy mà không thực sự chạy đồng thời tại từng khoảnh khắc.
- **Parallelism:** thực thi thực sự trùng thời điểm trên nhiều tài nguyên xử lý.

```text
Một lõi, chạy xen kẽ (concurrent):
Thời gian →  [A][B][A][B][A][B]

Hai lõi, chạy song song (parallel):
Lõi 1     →  [A][A][A][A]
Lõi 2     →  [B][B][B][B]
```

Ví dụ `list.parallelStream().map(...).toList()` có thể chia xử lý sang nhiều worker, nhưng lệnh `toList()` chỉ trả về khi xử lý cần thiết đã xong; tức là **bên trong có thể song song, còn bên gọi vẫn chờ đồng bộ**. Ngược lại, một executor chỉ có một worker vẫn có thể phục vụ API bất đồng bộ và xếp các task tuần tự.

Song song không tự bảo đảm tăng tốc: chi phí chia/gộp việc, tranh chấp khóa, I/O, giới hạn CPU và dữ liệu dùng chung có thể khiến kết quả chậm hơn hoặc sai.

### 1.4. Lập lịch: quyết định lúc nào kích hoạt

**Lập lịch** mô tả **thời điểm** một công việc được kích hoạt: vào 08:00 mỗi ngày làm việc, sau 5 giây, hoặc cứ một chu kỳ nhất định. Trong Spring, `@Scheduled` và `TaskScheduler` là các công cụ tiêu biểu.

```java
@Scheduled(fixedDelay = 5_000)
public void refreshCache() {
    refresh();
}
```

Lập lịch không xác định sẵn công việc phải chạy đồng bộ hay bất đồng bộ, trên một hay nhiều thread. Một job được scheduler gọi có thể tự xử lý trên thread lập lịch, hoặc chuyển tiếp sang executor rồi trở về. **Scheduler trả lời “khi nào?”; executor trả lời “thực thi ở đâu và bằng những worker nào?”**

## 2. Đừng nhầm với blocking/non-blocking

**Blocking** và **non-blocking** là một trục riêng: thread có phải chờ tài nguyên hay kết quả hay không.

- **Blocking I/O:** thread đứng chờ thao tác mạng, tệp hoặc cơ sở dữ liệu; gọi qua `@Async` chỉ chuyển việc chờ đó sang worker.
- **Non-blocking I/O:** thao tác không giữ thread để đợi kết quả I/O; kết quả được xử lý khi dữ liệu sẵn sàng.
- **Bất đồng bộ:** bên gọi có thể tiếp tục trước khi thao tác hoàn thành, dù thao tác bên dưới dùng blocking hay non-blocking I/O.

Ví dụ, Spring MVC có thể trả về `CompletableFuture` để xử lý HTTP bất đồng bộ nhưng tác vụ bên trong vẫn dùng JDBC blocking. Spring WebFlux có thể dùng pipeline reactive/non-blocking khi mọi thành phần liên quan hỗ trợ; chỉ bọc một lệnh JDBC blocking trong `Mono` **không biến JDBC thành non-blocking**. Không đặt lời gọi blocking lên event-loop của WebFlux.

## 3. Bảng so sánh nhanh

| Khái niệm | Câu hỏi chính | Quan sát từ bên gọi/hệ thống | Công cụ thường gặp |
| --- | --- | --- | --- |
| Đồng bộ | Khi nào lời gọi trả về? | Bên gọi chờ thao tác hoàn thành | Lời gọi Java trực tiếp, `get()`/`join()` |
| Bất đồng bộ | Có trả quyền điều khiển sớm không? | Kết quả/ lỗi đến sau; caller có thể làm việc khác | Spring `@Async`, `TaskExecutor`, `CompletableFuture` |
| Song song | Có nhiều việc chạy thực sự đồng thời không? | Nhiều worker/lõi xử lý các phần việc trùng thời điểm | Thread pool nhiều worker, `ForkJoinPool`, parallel stream |
| Lập lịch | Khi nào công việc được kích hoạt? | Có trigger theo thời gian/chu kỳ | `@Scheduled`, `TaskScheduler`, cron |

**Những tổ hợp hoàn toàn hợp lệ:**

1. **Đồng bộ và tuần tự:** gọi dịch vụ, nhận kết quả, rồi mới gọi dịch vụ tiếp theo.
2. **Bất đồng bộ nhưng các job xếp hàng tuần tự:** gửi nhiều task vào executor có một worker.
3. **Song song bên trong một lời gọi đồng bộ:** chia việc cho nhiều worker rồi `join()` trước khi trả kết quả.
4. **Lập lịch và xử lý tuần tự:** một scheduler kích hoạt job, job chạy xong mới tới lượt sau.
5. **Lập lịch kết hợp bất đồng bộ:** scheduler chỉ gửi task vào executor; worker xử lý sau và có thể chồng lấn với lần kích hoạt tiếp theo.

Do đó, phát biểu “đã dùng `@Scheduled` thì tự động đa luồng” hoặc “có `@Async` thì chắc chắn tận dụng nhiều lõi CPU” đều sai.

## 4. Ví dụ Java 17+ độc lập: hiểu sự khác nhau từ phía caller

Lưu đoạn sau thành **CallVsExecution.java**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CallVsExecution {
    private static String work(String name) {
        return "done " + name;
    }

    public static void main(String[] args) {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            String first = work("A"); // Đồng bộ
            System.out.println(first);

            CompletableFuture<String> second =
                    CompletableFuture.supplyAsync(() -> work("B"), worker);

            System.out.println("Caller continues");
            System.out.println(second.join()); // Chờ nếu B chưa xong
        } finally {
            worker.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CallVsExecution.java
java CallVsExecution
```

**Stdout chính xác** (chỉ thread chính in ra màn hình):

```text
done A
Caller continues
done B
```

Ở bước A, caller nhận kết quả trước khi tiếp tục. Ở bước B, caller nhận Future rồi in dòng tiếp theo; việc B có thể hoàn thành trước hoặc sau dòng “Caller continues”, nhưng thứ tự **in kết quả** là xác định nhờ `join()`. Một worker duy nhất xử lý các task được gửi vào executor theo lượt; API bất đồng bộ không yêu cầu nhiều worker. Không suy luận thứ tự thực thi thật chỉ từ thời điểm in log.

## 5. Các thành phần Spring liên quan

### 5.1. `@Async` và `TaskExecutor`: gửi việc chạy sau

Spring cung cấp `TaskExecutor` để thực thi `Runnable`/task; `ThreadPoolTaskExecutor` là một implementation quản lý nhóm thread. Khi bật `@EnableAsync`, Spring có thể tạo proxy để chặn lời gọi tới phương thức `@Async` và gửi công việc sang executor đã chọn.

Luồng ý tưởng:

```text
HTTP/service caller
      │ gọi qua Spring proxy
      ▼
@Service @Async("jobExecutor") ── submit ──► hàng đợi executor ──► worker
      │                                                     │
      └── trả Future sớm                                    └── hoàn thành Future
```

Lưu ý quan trọng: **phải gọi qua Spring proxy**. Một phương thức trong cùng bean gọi `this.asyncMethod()` sẽ không đi qua proxy ở chế độ mặc định, nên annotation có thể không hoạt động như mong muốn. Tương tự, không nên đặt kỳ vọng `@Async` hoạt động trên lời gọi trực tiếp vào đối tượng được tạo bằng `new`, hoặc trên phương thức `private`.

`@Async` thường dùng với kiểu trả về `void`, `Future` hoặc `CompletableFuture`. Để nhận lỗi và giá trị theo cách kiểm soát được, ưu tiên Future/CompletableFuture; nếu dùng `void`, cần chú ý cơ chế xử lý ngoại lệ bất đồng bộ.

### 5.2. `@Scheduled` và `TaskScheduler`: phát trigger theo thời gian

Spring hỗ trợ khai báo lịch bằng `@EnableScheduling` và `@Scheduled`. Method thông thường không nhận tham số; lịch được quyết định bởi cấu hình annotation, không phải lời gọi nghiệp vụ từ một controller.

- `fixedDelay = 5_000`: đợi 5 giây **sau khi lần gọi phương thức được lập lịch trước kết thúc** rồi mới kích hoạt lần kế tiếp.
- `fixedRate = 5_000`: nhắm tới chu kỳ 5 giây tính theo **mốc bắt đầu** của các lượt; khi job chạy lâu, khả năng đúng giờ hoặc chồng lấn phụ thuộc scheduler, executor và cách triển khai, không được tự giả định chạy song song.
- `initialDelay = 2_000`: đợi ban đầu 2 giây trước lần kích hoạt đầu tiên trong lịch định kỳ tương ứng.
- `cron = "0 0 8 * * MON-FRI", zone = "Asia/Ho_Chi_Minh"`: kích hoạt lúc 08:00 các ngày thứ Hai đến thứ Sáu theo múi giờ chỉ định. Cron của Spring thông dụng gồm **6 trường**: giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần.

Nếu một job trực tiếp gửi `@Async` rồi return, `fixedDelay` đo khoảng cách từ **lúc phương thức scheduled kết thúc việc gửi**, chứ không đo thời điểm task bất đồng bộ hoàn thành. Các lượt nền vì thế có thể chồng nhau khi xử lý lâu.

Ví dụ trong điều kiện lý tưởng, job chạy 2 giây và khoảng lặp cấu hình là 5 giây:

```text
fixedRate:   bắt đầu tại khoảng t = 0s, 5s, 10s, 15s...
fixedDelay:  bắt đầu tại khoảng t = 0s, 7s, 14s, 21s...
```

Đây là minh họa về mốc thời gian, không phải cam kết job luôn chạy đúng mili giây. Thread bận, dừng ứng dụng, GC pause hoặc giới hạn tài nguyên đều có thể làm trễ việc kích hoạt.

## 6. Ví dụ Spring Boot hoàn chỉnh: kết hợp ba cơ chế

Ví dụ dùng **Java 17+, Spring Boot 3.x/Spring Framework 6.x** với dependency `spring-boot-starter-web` và plugin chạy ứng dụng của Spring Boot. Đặt toàn bộ mã dưới đây trong **src/main/java/com/example/demo/ModesApplication.java**. Đây là ứng dụng minh họa độc lập về mặt mã nguồn, nhưng cần Spring Boot dependencies để biên dịch/chạy; lệnh `javac` thuần không đủ.

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModesApplication.class, args);
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("job-");
        executor.initialize();
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.initialize();
        return scheduler;
    }
}

@Service
class ReportService {
    public String createSync(String id) {
        return slowWork(id);
    }

    @Async("jobExecutor")
    public CompletableFuture<String> createAsync(String id) {
        return CompletableFuture.completedFuture(slowWork(id));
    }

    private String slowWork(String id) {
        try {
            Thread.sleep(800); // Chỉ mô phỏng I/O blocking, không phải giải pháp production
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Work interrupted", e);
        }
        return "done:" + id;
    }
}

@RestController
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/sync/{id}")
    public String sync(@PathVariable String id) {
        return service.createSync(id);
    }

    @GetMapping("/async/{id}")
    public CompletableFuture<String> async(@PathVariable String id) {
        return service.createAsync(id);
    }
}

@Component
class ReportTicker {
    private final ReportService service;

    ReportTicker(ReportService service) {
        this.service = service;
    }

    @Scheduled(initialDelay = 3_000, fixedDelay = 10_000)
    public void tick() {
        service.createAsync("periodic").whenComplete((result, error) -> {
            if (error != null) {
                System.err.println("Scheduled work failed: " + error.getMessage());
            } else {
                System.out.println("Scheduled work result: " + result);
            }
        });
    }
}
```

Trong một dự án Spring Boot đã cấu hình Gradle, chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), rồi gọi:

```bash
curl -s http://localhost:8080/sync/A
curl -s http://localhost:8080/async/B
```

**Body phản hồi tương ứng:**

```text
done:A
done:B
```

Mỗi lệnh `curl` chỉ trả về khi HTTP response hoàn tất. Hai body giống dạng nhau, nhưng phía server xử lý khác:

1. `/sync/A`: request thread trực tiếp chạy `slowWork` và chờ khoảng 800 ms.
2. `/async/B`: controller trả `CompletableFuture` cho Spring MVC; phần `slowWork` diễn ra trên thread `job-*`, và Spring MVC hoàn tất response khi Future hoàn thành. Điều này **không có nghĩa client HTTP nhận kết quả ngay**; client vẫn chờ nội dung của response.
3. `ReportTicker.tick()`: scheduler gọi phương thức theo `fixedDelay`; phương thức giao việc cho `jobExecutor`, đăng ký callback quan sát kết quả rồi trả về. Scheduler và executor là **hai vai trò riêng**.
4. `createAsync` chỉ được gọi từ các bean khác (`ReportController`, `ReportTicker`), nên lời gọi đi qua proxy `@Async`. Nếu đổi thành `this.createAsync(...)` bên trong `ReportService` thì hiệu lực khác.

Log của job và thứ tự xử lý giữa các request phụ thuộc lịch chạy thread nên **không có thứ tự stdout tổng thể cố định**. Không dùng thứ tự log ngẫu nhiên để kết luận có hoặc không có parallelism.

### Một điểm thường bị hiểu nhầm về Future

Trong thân `createAsync()`, `CompletableFuture.completedFuture(slowWork(id))` chạy `slowWork` **trước**, rồi mới tạo một future đã hoàn tất. Sự bất đồng bộ của lời gọi phía ngoài đến từ **Spring proxy + executor**. Nếu bỏ `@Async` và gọi trực tiếp dòng này, toàn bộ `slowWork` sẽ xảy ra trên caller thread trước khi Future được trả về. Chỉ thấy kiểu trả về `CompletableFuture` chưa đủ kết luận là chạy nền.

## 7. Kết hợp cơ chế theo nhu cầu thực tế

| Nhu cầu | Cách tiếp cận | Điều cần kiểm soát |
| --- | --- | --- |
| Đọc dữ liệu ngắn, phải có kết quả ngay | Lời gọi đồng bộ | Timeout, độ trễ của dependency |
| Tạo báo cáo tốn thời gian, có thể lấy sau | Gửi việc bất đồng bộ; có thể trả HTTP 202 kèm mã job và endpoint tra trạng thái | Lưu trạng thái, xử lý lỗi, retry, idempotency |
| Xử lý nhiều phần độc lập dùng CPU | Executor nhiều worker, phân chia/gộp dữ liệu có kiểm soát | Số lõi, shared state, overhead chia việc |
| Đồng bộ cache định kỳ | `@Scheduled` với `fixedDelay` hoặc cron | Lịch chạy, trễ lịch, trùng tác vụ |
| Lịch định kỳ kích hoạt xử lý I/O chậm | `@Scheduled` gọi service `@Async` qua bean khác | Queue, backlog, chồng lấn, mất lỗi |
| Job phải chạy một lần cho cả cụm nhiều instance | Scheduler có phối hợp phân tán hoặc hệ thống job/queue chuyên dụng | Ownership, khóa, deduplication, khôi phục sau sự cố |

**Không nên nhầm “trả Future” với “đã có API nền”**: một HTTP endpoint trả Future và đợi hoàn tất vẫn khiến HTTP client chờ. Muốn client gửi yêu cầu rồi tự quay lại lấy kết quả, thường cần giao thức job riêng: trả `202 Accepted` và job ID, lưu trạng thái, có endpoint tra cứu/kết quả và chính sách hết hạn/retry.

## 8. Những lỗi phổ biến và cách phòng tránh

**Lỗi 1 — Gọi `@Async` trong cùng bean.** Spring AOP mặc định chặn lời gọi qua proxy. Tách phương thức bất đồng bộ sang bean khác, inject bean rồi gọi qua đó. Đừng dùng `this` để kỳ vọng annotation được áp dụng.

**Lỗi 2 — Tạo Future rồi chờ ngay.** `supplyAsync(...).join()` tại cùng vị trí khiến caller chờ kết quả. Chỉ chuyển sang Future khi bạn thật sự có việc hữu ích để làm trước khi cần kết quả, hoặc cần kết hợp nhiều kết quả.

**Lỗi 3 — Cho rằng `@Scheduled` mặc định song song.** Việc một job có chạy chồng lần trước, và các job có được worker khác nhau phục vụ hay không, tùy scheduler, thời gian chạy và việc chuyển giao executor. Thiết kế dựa trên hành vi cấu hình cụ thể và kiểm thử dưới tải.

**Lỗi 4 — Giữ một thread pool/queue không giới hạn.** Công việc có thể đến nhanh hơn xử lý, khiến hàng đợi tích tụ, tăng bộ nhớ/độ trễ và cuối cùng bị từ chối hoặc quá tải. Với `ThreadPoolTaskExecutor`, đặt `corePoolSize`, `maxPoolSize` và `queueCapacity` phù hợp; khi dùng queue có sức chứa dương, pool thường ưu tiên xếp task vào queue trước khi tăng vượt số core thread. Theo dõi active threads, queue depth, task duration và rejection.

**Lỗi 5 — Gắn `@Async` rồi tưởng đã non-blocking.** Một lời gọi HTTP blocking/JDBC/blocking file I/O vẫn giữ worker trong thời gian đợi. Cần giới hạn đồng thời, timeout và biết rõ tài nguyên nào đang chờ. Non-blocking end-to-end yêu cầu cả pipeline phù hợp.

**Lỗi 6 — Dùng shared mutable state không an toàn.** Khi nhiều worker truy cập cùng `HashMap` hoặc biến đếm mà không có đồng bộ hóa, có thể xuất hiện race condition và dữ liệu sai. Dùng dữ liệu bất biến, chia vùng sở hữu, `ConcurrentHashMap`, `AtomicInteger` hoặc khóa khi thực sự cần; song song không thay thế thread safety.

**Lỗi 7 — Quên thread-local context và transaction.** Transaction của Spring thường gắn với thread hiện tại; một phương thức `@Async` chạy ở thread khác không tự kế thừa transaction đang chạy của caller. Tương tự, MDC logging hoặc security context không nên mặc định là được truyền sang worker. Xác định lại ranh giới transaction và truyền context có chủ đích.

**Lỗi 8 — Nuốt ngoại lệ của job nền.** Exception từ Future không được quan sát có thể trôi qua mà caller không biết; callback như `whenComplete`, `exceptionally`, metric và log giúp nhận lỗi. Với job định kỳ, bổ sung chiến lược retry/backoff có giới hạn, cảnh báo và idempotency trước khi chạy lại.

**Lỗi 9 — Triển khai nhiều replica và nghĩ cron chỉ chạy một lần.** Mỗi instance Spring bật lịch có thể tự kích hoạt cùng job. Nếu yêu cầu “một lần duy nhất toàn hệ thống”, cần cơ chế phối hợp như distributed lock, queue có consumer ownership, hoặc scheduler phân tán; `@Scheduled` đơn lẻ không bảo đảm điều đó.

**Lỗi 10 — Dựa vào lịch để bảo đảm giao việc bền vững.** Một trigger trong tiến trình có thể không chạy khi ứng dụng tắt hoặc có thể bị trễ khi hệ thống quá tải. Nếu cần lưu job, phục hồi sau restart, giữ lịch sử và retry đáng tin cậy, dùng giải pháp lưu trữ/phối hợp phù hợp thay vì chỉ một cron trong bộ nhớ.

## 9. Cách chọn giải pháp trong Spring

Trước khi thêm annotation, lần lượt trả lời:

1. **Caller có bắt buộc chờ kết quả ngay không?** Nếu có, đồng bộ thường đơn giản hơn. Nếu không, xác định Future/callback/event hoặc giao thức job.
2. **Công việc nặng CPU hay phải đợi I/O?** CPU-bound nên xét số lõi và chia việc; I/O-bound cần giới hạn số tác vụ chờ và timeout. Không tăng thread vô hạn.
3. **Có cần kích hoạt theo thời gian?** Nếu có, chọn `fixedDelay`, `fixedRate` hay cron dựa trên nghĩa nghiệp vụ; thời điểm kích hoạt độc lập với cách xử lý.
4. **Có được phép chạy chồng không?** Nếu không, cần khóa, tuần tự hóa hoặc kiểm tra trạng thái; đừng mặc nhiên trông cậy vào pool một thread trong mọi cấu hình.
5. **Có cần bảo đảm chạy lại và chạy một lần trong cụm không?** Thiết kế retry, idempotency, trạng thái lưu bền vững và phối hợp giữa các instance.
6. **Sẽ đo và xử lý sự cố như thế nào?** Quan sát độ trễ, backlog, số worker bận, job trễ, lỗi, timeout và hành vi khi shutdown.

Một quy tắc dễ nhớ là:

> **Đồng bộ/bất đồng bộ** nói về lúc caller tiếp tục. **Concurrency/song song** nói về mức công việc có thể tiến triển cùng lúc. **Lập lịch** nói về lúc bắt đầu. **Blocking/non-blocking** nói về cách thread chờ tài nguyên. Các lựa chọn này có thể kết hợp, nhưng không thay thế lẫn nhau.

## 10. Tự kiểm tra

**Câu 1.** Method có `@Async` trả `CompletableFuture`, nhưng caller gọi `join()` ngay. Đây có phải caller đang chờ không?

**Đáp án:** Có. Công việc được gửi bất đồng bộ, nhưng caller sau đó chủ động chờ đồng bộ ở `join()`.

**Câu 2.** Một `@Scheduled(fixedRate = 1_000)` có chắc tạo thread mới mỗi giây và cho các lượt chạy song song không?

**Đáp án:** Không. Cấu hình định nghĩa mục tiêu thời gian kích hoạt; thread và mức chồng lấn phụ thuộc scheduler, pool và cách job thực thi.

**Câu 3.** `parallelStream().toList()` có phải lời gọi bất đồng bộ đối với đoạn code phía sau không?

**Đáp án:** Không theo mặc định. Các phần xử lý có thể chạy song song bên trong, nhưng lời gọi terminal trả kết quả sau khi đã hoàn tất các phần cần thiết.

**Câu 4.** Nếu controller Spring MVC trả `CompletableFuture<String>`, liệu trình duyệt nhận nội dung ngay lập tức?

**Đáp án:** Không. Server có thể xử lý request bất đồng bộ, nhưng HTTP response mang kết quả chỉ hoàn tất khi Future hoàn thành. Muốn client không chờ job dài, thiết kế endpoint nhận job và tra kết quả riêng.

**Câu 5.** Có ba instance cùng chạy `@Scheduled(cron = "...")`. Có được bảo đảm chỉ một instance làm việc không?

**Đáp án:** Không. Cần cơ chế phối hợp để bảo đảm thực thi duy nhất trong cụm.

## Tài liệu tham khảo

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Reference — Asynchronous Requests trong Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Java SE — `CompletableFuture`, `ExecutorService`, `ScheduledExecutorService` trong gói `java.util.concurrent`.
