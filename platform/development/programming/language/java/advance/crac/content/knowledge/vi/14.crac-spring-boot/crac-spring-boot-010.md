# Tác vụ @Scheduled và công việc nền sau restore

Spring Boot thường chạy các công việc định kỳ và tác vụ nền ngay trong cùng tiến trình với web application. Ví dụ: đồng bộ dữ liệu, làm mới cache, gửi báo cáo, dọn dữ liệu hết hạn, kiểm tra trạng thái dịch vụ, đọc message queue hoặc xử lý tác vụ bất đồng bộ. Các công việc này có thể được khai báo bằng @Scheduled, chạy qua TaskScheduler, TaskExecutor, @Async hoặc một worker riêng.

Khi ứng dụng dùng CRaC (Coordinated Restore at Checkpoint), tiến trình được lưu lại rồi tiếp tục chạy sau restore. Trong thời gian checkpoint, các thread Java không xử lý công việc bình thường nhưng thời gian bên ngoài vẫn trôi qua. Một lịch chạy có thể đã đến hạn, một task có thể đang xử lý dở, một message lease có thể hết hạn hoặc một lần retry có thể không còn phù hợp.

Vì vậy, cần thiết kế vòng đời của công việc nền một cách rõ ràng: ngừng nhận việc mới trước checkpoint, chờ hoặc xử lý task đang chạy, xác định chính sách cho các lần chạy bị bỏ lỡ, khởi tạo lại scheduler/worker sau restore và chỉ cho phép chạy khi dependency đã sẵn sàng. Bản thân annotation @Scheduled không thể thay thế chính sách nghiệp vụ đó.

## 1. @Scheduled hoạt động như thế nào?

Trong Spring, @EnableScheduling bật cơ chế phát hiện các method được đánh dấu @Scheduled. Spring đăng ký các method này với một TaskScheduler. Ví dụ:

~~~java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Một bean có thể khai báo công việc định kỳ:

~~~java
@Component
public class CacheRefreshJob {

    private final CacheService cacheService;

    public CacheRefreshJob(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @Scheduled(fixedDelay = 30_000)
    public void refreshCache() {
        cacheService.refresh();
    }
}
~~~

Trong ví dụ, Spring gọi refreshCache() theo lịch. Nếu không cấu hình scheduler riêng, Spring sẽ chọn scheduler theo cơ chế mặc định của framework; cấu hình thực tế phụ thuộc phiên bản Spring và các bean TaskScheduler/TaskExecutor hiện có. Với ứng dụng cần kiểm soát thread, shutdown và restore, nên khai báo scheduler tường minh.

### 1.1. Các kiểu lịch phổ biến

| Thuộc tính | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| fixedDelay | Chờ một khoảng thời gian sau khi lần chạy trước hoàn tất rồi mới chạy lần tiếp theo | Polling, refresh cache, tác vụ cần khoảng nghỉ sau khi xử lý |
| fixedRate | Lập lịch theo khoảng cách giữa các thời điểm bắt đầu dự kiến | Công việc cần nhịp chạy tương đối đều |
| cron | Chạy theo biểu thức lịch dạng lịch dân sự | Báo cáo, tổng hợp theo giờ/ngày, công việc theo múi giờ |

Ví dụ:

~~~java
@Component
public class MaintenanceJobs {

    @Scheduled(fixedDelay = 60_000)
    public void pollQueue() {
        // Chạy lại sau 60 giây kể từ khi lần trước hoàn tất.
    }

    @Scheduled(fixedRate = 300_000)
    public void refreshMetrics() {
        // Lịch dự kiến cách nhau 5 phút.
    }

    @Scheduled(
            cron = "0 0 2 * * *",
            zone = "Asia/Ho_Chi_Minh")
    public void dailyMaintenance() {
        // Chạy lúc 02:00 theo giờ Việt Nam.
    }
}
~~~

Với cron, thuộc tính zone rất quan trọng. Nếu bỏ qua zone, lịch phụ thuộc timezone mặc định của môi trường chạy. Hai deployment ở các timezone khác nhau có thể chạy cùng biểu thức cron vào thời điểm UTC khác nhau.

### 1.2. fixedDelay và fixedRate không có cùng ý nghĩa

Với fixedDelay, khoảng nghỉ được tính từ khi lần chạy trước kết thúc. Nếu tác vụ mất 20 giây và delay là 30 giây, lần kế tiếp được lập lịch sau khi lần trước hoàn tất thêm 30 giây.

Với fixedRate, các thời điểm bắt đầu dự kiến cách nhau một khoảng cố định. Nếu tác vụ mất nhiều thời gian hơn chu kỳ, lần tiếp theo có thể bắt đầu trễ so với thời điểm dự kiến. Không nên hiểu fixedRate là bảo đảm method luôn chạy đúng từng mốc thời gian, cũng không nên giả định các lần chạy sẽ tự động song song.

Nếu một method có nhiều khai báo @Scheduled hoặc ứng dụng có nhiều scheduler/worker, có thể xuất hiện các lần thực thi chồng lấn. Với tác vụ cập nhật dữ liệu, cần có cơ chế chống chạy đồng thời và bảo vệ side effect.

## 2. Điều gì xảy ra với công việc nền khi checkpoint?

Checkpoint lưu trạng thái tiến trình. Các bean, object scheduler, scheduled future, executor và một phần trạng thái task có thể nằm trong snapshot. Tuy nhiên, hệ thống bên ngoài vẫn tiếp tục hoạt động trong lúc process tạm dừng.

Ví dụ một tác vụ đồng bộ:

~~~text
Spring application
     │
     ▼
@Scheduled method
     │
     ▼
Đọc dữ liệu từ database
     │
     ▼
Gọi partner API
     │
     ▼
Ghi kết quả và cập nhật cursor
     │
     ▼
Hoàn tất
~~~

Nếu checkpoint xảy ra giữa quá trình này, một số tình huống có thể xuất hiện:

- Task đang chạy bị đóng băng giữa một thao tác I/O hoặc giữa hai bước nghiệp vụ.
- Database transaction hoặc HTTP connection có thể timeout trong thời gian process dừng.
- Message consumer có thể mất lease hoặc bị broker phân phối message cho instance khác.
- Lịch cron có thể có một hoặc nhiều lần chạy dự kiến đã trôi qua.
- Một retry delay có thể đã hết hạn trước khi process được restore.
- Scheduled executor có thể có task đang chờ trong queue.
- Task được restore có thể tiếp tục từ trạng thái bộ nhớ không còn phù hợp với hệ thống bên ngoài.

Không nên suy luận rằng task sẽ tự chạy lại từ đầu hoặc chắc chắn chạy đúng một lần. CRaC phục hồi process state; nó không tạo transaction phân tán giữa JVM, database, message broker và API bên ngoài.

## 3. Xác định chính sách cho các lần chạy bị bỏ lỡ

Trước khi tích hợp CRaC, mỗi background job cần có chính sách rõ ràng cho khoảng thời gian process bị dừng.

Bốn chính sách phổ biến:

| Chính sách | Hành vi sau restore | Ví dụ |
|---|---|---|
| Catch up | Chạy bù các lần đến hạn nhưng chưa thực hiện | Đồng bộ các partition hoặc khoảng dữ liệu bị bỏ lỡ |
| Skip missed runs | Bỏ qua mốc đã qua, chờ lần chạy kế tiếp | Làm mới cache định kỳ, tác vụ chỉ cần dữ liệu mới nhất |
| Coalesce | Gộp nhiều lần bị bỏ lỡ thành một lần chạy | Tính lại dashboard hoặc tổng hợp trạng thái hiện tại |
| Resume remaining delay | Tiếp tục với khoảng thời gian còn lại trước lần chạy kế tiếp | Một workflow có thời gian chờ tương đối |

Ví dụ, một cron job chạy mỗi phút. Process checkpoint trong 10 phút:

- Catch up có thể tạo ra 10 lần chạy bù.
- Skip missed runs chỉ chạy ở mốc cron tiếp theo trong tương lai.
- Coalesce chạy một lần để xử lý toàn bộ dữ liệu mới kể từ lần thành công gần nhất.
- Resume remaining delay chỉ phù hợp khi ứng dụng có khái niệm delay còn lại cần tiếp tục.

Không có một chính sách đúng cho mọi job. Báo cáo hàng ngày, cache refresh, message consumer và job xử lý thanh toán có yêu cầu khác nhau.

### 3.1. Ưu tiên lưu trạng thái nghiệp vụ

Nếu task xử lý dữ liệu theo khoảng thời gian, hãy lưu cursor hoặc watermark đã hoàn tất, chẳng hạn lastProcessedAt hoặc ID cuối cùng đã commit. Sau restore, job truy vấn từ cursor đã commit đến thời điểm hiện tại.

Không dựa duy nhất vào số lần timer đã kích hoạt. Một timer có thể bỏ lỡ lần chạy trong lúc checkpoint, nhưng dữ liệu cần xử lý vẫn tồn tại ở database hoặc message broker.

### 3.2. Idempotency và chống xử lý trùng

Catch up hoặc retry có thể làm cùng một đơn vị công việc được gửi lại. Tác vụ cần có idempotency key, unique constraint, transactional outbox/inbox hoặc cơ chế deduplication phù hợp.

Ví dụ, nếu job gửi hóa đơn, không nên chỉ kiểm tra một boolean trong heap để biết hóa đơn đã gửi. Trạng thái đã gửi phải được ghi nhận bền vững ở hệ thống sở hữu nghiệp vụ để lần chạy sau không gửi trùng.

## 4. Dừng công việc nền trước checkpoint

Trước checkpoint, ứng dụng nên chuyển sang trạng thái không nhận thêm công việc mới. Các bước thường gồm:

1. Chuyển readiness hoặc job admission sang NOT_READY/PAUSED.
2. Ngừng nhận message mới hoặc ngừng poll nguồn công việc.
3. Ngăn các lần @Scheduled mới bắt đầu xử lý nghiệp vụ.
4. Chờ task đang chạy hoàn tất trong thời gian giới hạn.
5. Commit/rollback transaction và trả connection về pool.
6. Đóng resource cần tạo lại sau restore.
7. Chỉ hoàn tất callback khi trạng thái process an toàn để checkpoint.

Chỉ hủy ScheduledFuture không đảm bảo task đang chạy đã dừng. Cũng không nên gọi shutdownNow() rồi giả định mọi task đã kết thúc; phương thức này chỉ gửi interrupt cho thread và task phải hợp tác với interrupt.

### 4.1. Phân biệt scheduler với task đang chạy

Scheduler chịu trách nhiệm phát lịch. Task là phần công việc thực tế. Dừng scheduler có thể ngăn lần chạy mới, nhưng task đã được executor bắt đầu vẫn có thể tiếp tục chạy.

Một quy trình shutdown cần quản lý cả hai:

~~~text
PAUSE SCHEDULER / JOB ADMISSION
             │
             ▼
Ngăn task mới vào phần nghiệp vụ
             │
             ▼
Đợi active task count = 0
             │
             ▼
Đóng database/client/resource phụ thuộc
             │
             ▼
Checkpoint
~~~

Nếu task không thể hoàn tất trong deadline, cần báo lỗi và từ chối checkpoint theo policy. Không để callback chờ vô hạn.

## 5. Dùng gate để chặn task mới và drain task đang chạy

Một cách dễ kiểm soát với @Scheduled là để method annotation tiếp tục được Spring quản lý, nhưng đặt một gate trước phần nghiệp vụ. Gate ngăn lần chạy mới đi vào khi ứng dụng chuẩn bị checkpoint và theo dõi số task đang hoạt động.

~~~java
package com.example.jobs;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class BackgroundJobGate {

    private final Object monitor = new Object();

    private boolean accepting = true;
    private int activeTasks;

    public boolean enter() {
        synchronized (monitor) {
            if (!accepting) {
                return false;
            }

            activeTasks++;
            return true;
        }
    }

    public void exit() {
        synchronized (monitor) {
            activeTasks--;

            if (activeTasks == 0) {
                monitor.notifyAll();
            }
        }
    }

    public void pauseAndAwait(Duration timeout)
            throws InterruptedException, java.util.concurrent.TimeoutException {

        long started = System.nanoTime();
        long timeoutNanos = timeout.toNanos();

        synchronized (monitor) {
            accepting = false;

            while (activeTasks > 0) {
                long elapsed = System.nanoTime() - started;
                long remaining = timeoutNanos - elapsed;

                if (remaining <= 0) {
                    // Checkpoint không tiếp tục; cho ứng dụng chạy lại.
                    accepting = true;
                    monitor.notifyAll();

                    throw new java.util.concurrent.TimeoutException(
                            "Background tasks did not drain before checkpoint");
                }

                TimeUnit.NANOSECONDS.timedWait(monitor, remaining);
            }
        }
    }

    public void resume() {
        synchronized (monitor) {
            accepting = true;
            monitor.notifyAll();
        }
    }
}
~~~

Gate dùng cùng một monitor để thực hiện hai việc: kiểm tra accepting và tăng activeTasks. Vì vậy, pause không thể xảy ra giữa lúc task đã được chấp nhận nhưng chưa được ghi nhận là active.

Task cần gọi exit() trong finally để bộ đếm luôn được giảm kể cả khi nghiệp vụ ném exception.

### 5.1. Bọc @Scheduled method bằng gate

~~~java
package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationJob {

    private final BackgroundJobGate gate;
    private final ReconciliationService service;

    public ReconciliationJob(
            BackgroundJobGate gate,
            ReconciliationService service) {
        this.gate = gate;
        this.service = service;
    }

    @Scheduled(fixedDelay = 30_000)
    public void reconcile() {
        if (!gate.enter()) {
            return;
        }

        try {
            service.reconcile();
        } finally {
            gate.exit();
        }
    }
}
~~~

Khi gate đã pause, Spring vẫn có thể gọi method theo lịch nhưng method thoát ngay trước khi thực hiện nghiệp vụ. Cách này chặn phần xử lý mới và cho callback biết khi nào các task đã vào trước đó hoàn tất.

Gate không tự thay đổi lịch nội bộ của TaskScheduler. Một lần chạy bị bỏ qua, lần chạy đến hạn hoặc hành vi catch-up sau restore còn phụ thuộc scheduler và trigger đang sử dụng. Nếu cần chính sách missed-run chính xác, hãy quản lý next-run time tường minh như phần sau.

## 6. Kết nối gate với CRaC Resource

Có thể tạo một bean Resource để pause và drain công việc trước checkpoint, sau đó mở gate sau restore:

~~~java
package com.example.jobs;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Component
public class BackgroundJobsCracResource implements Resource {

    private final BackgroundJobGate gate;

    public BackgroundJobsCracResource(BackgroundJobGate gate) {
        this.gate = gate;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        try {
            gate.pauseAndAwait(Duration.ofSeconds(20));
        } catch (InterruptedException interrupted) {
            gate.resume();
            Thread.currentThread().interrupt();
            throw interrupted;
        } catch (TimeoutException timeout) {
            gate.resume();
            throw timeout;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        gate.resume();
    }
}
~~~

Trong ví dụ, nếu task không drain trong 20 giây, callback báo lỗi để checkpoint thất bại theo policy. Gate được mở lại vì process tiếp tục chạy sau một lần checkpoint thất bại. Nếu thread bị interrupt, trạng thái interrupt được giữ lại.

Đây là mẫu tối giản. Ứng dụng thực tế cần phối hợp readiness, scheduler, worker pool và các resource mà job sử dụng. Không chỉ pause gate rồi bỏ qua trạng thái database hoặc HTTP client.

### 6.1. Đăng ký theo thứ tự dependency

Giả sử job cần database và HTTP server tiếp tục nhận request khi ứng dụng chạy:

~~~text
Đăng ký Resource:
1. DatabasePoolResource
2. BackgroundJobsCracResource
3. HttpServerResource

beforeCheckpoint (đảo thứ tự):
1. HttpServerResource dừng nhận request
2. BackgroundJobsCracResource pause/drain job
3. DatabasePoolResource đóng pool

afterRestore (thuận thứ tự):
1. DatabasePoolResource khôi phục pool
2. BackgroundJobsCracResource mở gate
3. HttpServerResource nhận request
~~~

Thứ tự trên là ví dụ cho một context và một dependency graph cụ thể. Nếu job còn phụ thuộc resource khác, hãy đặt resource callback sao cho dependency sẵn sàng trước khi gate được mở. Không đăng ký một resource hai lần để hai callback cùng quản lý một scheduler hoặc connection pool.

## 7. Cấu hình TaskScheduler tường minh trong Spring Boot

Với ứng dụng có nhiều scheduled job, nên cấu hình scheduler rõ ràng để kiểm soát thread và quan sát hoạt động:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableScheduling
public class SchedulerConfiguration {

    @Bean
    public TaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("scheduled-job-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(20);

        return scheduler;
    }
}
~~~

Pool size cần dựa trên số job, thời gian chạy và mức độ I/O. Một pool quá nhỏ có thể khiến job chậm trễ; pool quá lớn có thể tạo nhiều thread và tăng tải lên database hoặc service bên ngoài.

Các thuộc tính shutdown giúp Spring chờ task khi application context dừng bình thường. Chúng không tự tạo một chính sách CRaC hoàn chỉnh. Callback checkpoint cần được tích hợp rõ ràng để dừng admission, drain công việc và quyết định cách tiếp tục sau restore.

Nếu phiên bản Spring Framework đang dùng cung cấp cơ chế pause/resume cho scheduler, có thể tận dụng API đó để điều khiển lịch. Cần xác nhận phiên bản thực tế và thử nghiệm behavior khi pause, resume, shutdown và restore. Không giả định mọi TaskScheduler implementation đều hỗ trợ cùng lifecycle API.

## 8. Xử lý lịch bị bỏ lỡ bằng deadline và next-run time

Với job có yêu cầu lịch rõ ràng, lưu thời điểm chạy tiếp theo dưới dạng Instant thay vì chỉ dựa vào delay đang nằm trong scheduler queue.

Ví dụ job cần chạy mỗi 5 phút và bỏ qua các mốc đã qua. Sau mỗi lần hoàn tất, ứng dụng tính nextRunAt là mốc tương lai kế tiếp. Trước checkpoint, dừng scheduler và giữ nextRunAt. Sau restore, tính lại delay:

~~~java
Instant now = clock.instant();

Duration delay =
        Duration.between(now, nextRunAt);

if (delay.isNegative()) {
    delay = Duration.ZERO;
}

taskScheduler.schedule(job, nextRunAt);
~~~

TaskScheduler có thể nhận một thời điểm Instant để lập lịch. Cần chọn chính sách riêng khi nextRunAt đã ở quá khứ:

- Chạy ngay một lần.
- Bỏ qua và tính mốc kế tiếp.
- Gộp dữ liệu từ các mốc bị bỏ lỡ.
- Chạy bù có giới hạn số lần.

Không chỉ gọi schedule với thời điểm quá khứ rồi mặc định scheduler sẽ thực hiện đúng policy nghiệp vụ.

### 8.1. fixedDelay sau restore

Nếu chính sách là fixedDelay, thời điểm lần kế tiếp nên được tính từ lúc lần xử lý gần nhất hoàn tất hoặc từ lúc restore tùy mục tiêu.

Ví dụ:

- Nếu checkpoint không được tính vào thời gian chờ, sau restore đặt nextRunAt = restoreTime + delay.
- Nếu thời gian checkpoint được tính vào thời gian chờ, lưu deadline tuyệt đối trước checkpoint và tính remaining sau restore.
- Nếu job đã quá hạn, chạy ngay một lần hoặc bỏ qua theo policy.

### 8.2. fixedRate sau restore

fixedRate dựa trên nhịp thời gian. Nếu process dừng lâu, nhiều mốc có thể đã trôi qua. Ứng dụng phải quyết định catch up, skip hoặc coalesce.

Với job không cần chạy bù từng mốc, có thể tính mốc tương lai kế tiếp dựa trên chu kỳ và thời điểm bắt đầu lịch. Không nên lặp lại tất cả lần chạy đã bỏ lỡ nếu mỗi lần đều chỉ làm mới cùng một trạng thái hiện tại.

### 8.3. Cron và timezone

Cron là lịch dân sự. Nên lưu biểu thức cron, ZoneId và policy missed-run. Sau restore, dùng thời điểm hiện tại cùng zone để tính lần chạy kế tiếp.

Ví dụ, lịch 02:00 tại Asia/Ho_Chi_Minh phải được tính theo timezone đó. Không dùng cách cộng 24 giờ vào Instant của lần trước để thay thế lịch hàng ngày trong mọi trường hợp; lịch dân sự có thể chịu ảnh hưởng của timezone và daylight saving time ở các vùng khác.

## 9. Khi nào nên dùng @Scheduled, khi nào cần scheduler riêng?

@Scheduled phù hợp với job đơn giản, có lịch ổn định và chính sách sau restore dễ xác định. Ví dụ: refresh cache, kiểm tra health hoặc chạy cleanup có thể lặp lại an toàn.

Nên dùng scheduler riêng hoặc job orchestration có state khi:

- Cần biết chính xác nextRunAt.
- Phải catch up hoặc coalesce các lần bị bỏ lỡ.
- Job cần retry/backoff có trạng thái bền vững.
- Có nhiều bước và checkpoint giữa các bước nghiệp vụ.
- Cần kiểm soát concurrency theo tenant/partition.
- Cần bảo đảm không chạy trùng trên nhiều instance.
- Công việc dài hoặc có side effect quan trọng.

Một scheduler riêng có thể lưu trạng thái lịch trong database, sử dụng TaskScheduler chỉ để đánh thức worker. Database là nguồn sự thật về công việc cần chạy; timer trong JVM chỉ là cơ chế đánh thức.

## 10. Các loại công việc nền khác trong Spring Boot

CRaC không chỉ ảnh hưởng tới @Scheduled. Các công việc sau cũng cần lifecycle tương ứng.

### 10.1. @Async và TaskExecutor

@Async gửi method vào executor. Trước checkpoint, dừng nhận task mới và đợi task đang chạy hoàn tất. Nếu task còn trong queue, cần quyết định giữ, hủy hay ghi lại vào durable queue.

Không giả định task trong memory queue đã được xử lý bền vững. Nếu công việc phải tồn tại qua process restart, hãy lưu job vào database hoặc message broker trước khi executor thực hiện.

### 10.2. Message listener và consumer

Consumer có thể giữ connection, session hoặc lease từ broker. Trước checkpoint:

- Dừng nhận message mới.
- Đợi message đang xử lý hoàn tất trong deadline.
- Ack message sau khi side effect đã commit.
- Nack/requeue message chưa xử lý xong theo semantics của broker.
- Đóng hoặc tạm dừng consumer theo thư viện.

Sau restore, kết nối lại broker, khôi phục subscription và xử lý message còn lại. Không dựa vào object consumer cũ hoặc một flag trong heap để chứng minh message chưa bị xử lý ở instance khác.

### 10.3. Executor loop và worker thread tự quản lý

Một thread vòng lặp thường cần cờ dừng, interrupt hoặc cơ chế wake-up. Trước checkpoint, dừng nhận việc, đưa loop về điểm an toàn và chờ thread kết thúc. Sau restore, tạo worker thread mới theo trạng thái đã lưu.

Không giữ một Thread object trong heap rồi giả định thread đó tự tiếp tục đúng trạng thái chỉ vì object còn tồn tại. Thread lifecycle cần được quản lý theo khả năng của JDK/CRaC runtime và API resource của thư viện.

### 10.4. Retry và backoff

Một retry delay 5 phút có thể đã hết hạn trong thời gian checkpoint. Lưu retryAt bằng Instant hoặc lưu trạng thái retry bền vững. Sau restore, tính lại thời gian còn lại và áp dụng giới hạn retry.

Không reset retry counter về 0 chỉ vì process restore. Điều đó có thể làm hệ thống thử vô hạn một request lỗi hoặc gây tải lớn lên dependency đang gặp sự cố.

## 11. Nhiều instance và distributed scheduling

Nếu ứng dụng chạy nhiều replica, mỗi replica có thể khôi phục cùng một @Scheduled job. Điều này có thể khiến job chạy nhiều lần sau restore.

Ví dụ, 5 instance đều có lịch cleanup lúc 02:00. Khi cả 5 instance restore cùng lúc, mỗi instance có thể kích hoạt cleanup.

Các biện pháp thường dùng:

- Distributed lock hoặc scheduler cluster.
- Leader election.
- Partition công việc theo tenant hoặc shard.
- Unique constraint và idempotency key.
- Database job table với claim/lease có thời hạn.
- Jitter để giảm đợt request đồng thời.

Distributed lock phải được xác thực lại sau restore. Lease cũ có thể đã hết hạn trong lúc process dừng và một instance khác có thể đã trở thành owner. Dùng fencing token hoặc version để hệ thống dữ liệu từ chối thao tác của owner cũ.

Không dùng synchronized hoặc AtomicBoolean trong một JVM để bảo đảm singleton job trên toàn cluster. Những cơ chế đó chỉ phối hợp thread trong cùng process.

## 12. Transaction và điểm an toàn của background job

Một background job nên có ranh giới transaction rõ ràng. Nếu task có nhiều bước, hãy lưu tiến độ sau mỗi bước đã commit để sau restore có thể tiếp tục mà không lặp side effect.

Ví dụ:

~~~text
Job bắt đầu
   │
   ▼
Đọc batch dữ liệu
   │
   ▼
Xử lý batch
   │
   ▼
Commit kết quả + cập nhật cursor
   │
   ▼
Batch tiếp theo
~~~

Nếu checkpoint xảy ra giữa hai batch, job có thể tiếp tục từ cursor đã commit. Nếu checkpoint xảy ra giữa thao tác ghi và cập nhật cursor, hai thao tác cần cùng transaction hoặc có cơ chế idempotency để tránh bỏ sót/lặp dữ liệu.

Không cố giữ một JDBC transaction mở xuyên qua checkpoint. Database server có thể timeout hoặc đóng session trong khi tiến trình bị dừng. Trước checkpoint, drain task và hoàn tất transaction; sau restore, tạo connection mới và tiếp tục từ trạng thái bền vững.

## 13. Readiness và thứ tự mở công việc sau restore

Không mở tất cả scheduler, consumer và HTTP server cùng một lúc nếu chúng phụ thuộc vào nhau.

Một thứ tự thường dùng:

~~~text
Restore process
      │
      ▼
Load runtime configuration/secrets
      │
      ▼
Restore database and external clients
      │
      ▼
Validate dependencies
      │
      ▼
Resume background workers
      │
      ▼
Start accepting HTTP traffic
      │
      ▼
Application READY
~~~

Tùy hệ thống, background worker có thể cần chạy trước HTTP listener hoặc sau listener. Ví dụ, nếu worker tạo dữ liệu mà request cần đọc, có thể cần worker hoàn tất bước bootstrap trước khi readiness chuyển READY. Nếu worker có thể chạy độc lập, nó có thể được mở sau khi dependency đã sẵn sàng.

Điều quan trọng là readiness phải phản ánh đúng khả năng phục vụ. Không đánh dấu READY chỉ vì Spring context đã được restore. Hãy kiểm tra database, broker, secret provider và các resource bắt buộc.

## 14. Kiểm tra và quan sát job sau restore

Mỗi background job nên ghi log các thông tin:

- Tên job và phiên bản cấu hình.
- Thời điểm dự kiến chạy tiếp theo.
- Thời điểm thực sự bắt đầu/kết thúc.
- Thời lượng xử lý.
- Số task active và task đang chờ.
- Cursor hoặc watermark đã commit.
- Số lần retry và lỗi gần nhất.
- Chính sách missed-run được áp dụng sau restore.

Tránh log nội dung secret, token hoặc dữ liệu nghiệp vụ nhạy cảm.

Có thể thêm metric:

| Metric | Ý nghĩa |
|---|---|
| job_active_tasks | Số task đang chạy |
| job_last_success_timestamp | Thời điểm lần thành công gần nhất |
| job_next_run_timestamp | Mốc chạy dự kiến tiếp theo |
| job_duration_seconds | Thời lượng mỗi lần chạy |
| job_skipped_runs_total | Số mốc bị bỏ qua |
| job_catchup_runs_total | Số lần chạy bù |
| job_restore_failures_total | Số lỗi khi khôi phục worker |
| job_checkpoint_drain_seconds | Thời gian drain trước checkpoint |

Sau restore, so sánh nextRunAt với thời điểm hiện tại để xác nhận missed-run policy đã được áp dụng. Nếu có nhiều instance, bổ sung instance ID và fencing token vào log để phân biệt owner.

## 15. Kiểm thử các tình huống checkpoint/restore

Một bài kiểm thử chỉ xác nhận ứng dụng restore và endpoint trả HTTP 200 là chưa đủ. Cần kiểm tra hành vi của background job.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Checkpoint khi không có task active | Gate pause, restore mở gate và lịch tiếp tục đúng policy |
| Checkpoint khi task đang chạy | Callback chờ task drain hoặc fail theo timeout |
| Task không kết thúc đúng hạn | Checkpoint bị từ chối có kiểm soát; ứng dụng tiếp tục hoạt động |
| Cron bị bỏ lỡ nhiều mốc | Catch up/skip/coalesce đúng chính sách |
| fixedDelay đang chờ | Remaining delay được tính theo policy |
| Database unavailable sau restore | Job chưa chạy khi dependency chưa READY |
| Message lease hết hạn | Consumer acquire/validate lại lease |
| Hai replica restore cùng lúc | Job không tạo side effect trùng ngoài policy |
| Task lỗi sau restore | Retry/backoff và trạng thái bền vững hoạt động đúng |
| Callback restore thất bại | Readiness không chuyển READY giả |

Nên kết hợp unit test cho gate và lịch với integration test trên đúng CRaC-enabled JDK, Spring Framework/Spring Boot version, scheduler implementation và môi trường CRIU dự kiến triển khai.

### 15.1. Kiểm thử gate

Có thể kiểm tra ba tình huống:

1. Khi accepting=true, enter() trả true và activeTasks tăng.
2. Khi một task đang active, pauseAndAwait() chờ đến khi exit() được gọi.
3. Sau khi pause hoàn tất, enter() trả false cho đến khi resume() được gọi.

Thêm test timeout để bảo đảm gate tự mở lại khi checkpoint không thể tiếp tục. Với tác vụ dài, kiểm tra interrupt và deadline để tránh callback bị treo.

### 15.2. Kiểm thử missed-run policy

Dùng Clock có thể điều khiển để mô phỏng:

- Trước checkpoint, nextRunAt còn 2 phút.
- Restore sau 10 phút.
- Chính sách skip chọn mốc cron tương lai.
- Chính sách catch up tạo một hoặc nhiều công việc bù có giới hạn.
- Chính sách coalesce chỉ tạo một lần chạy tổng hợp.

Không cần chờ 10 phút thật để kiểm thử logic deadline. Dùng Clock.fixed hoặc Clock giả lập cho phần tính lịch; sau đó chạy một integration test thực tế để xác nhận scheduler hoạt động đúng với runtime.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ @Scheduled tự tính lại mọi lần chạy sau restore | Job có thể chạy bù hoặc trễ ngoài ý muốn | Định nghĩa missed-run policy và kiểm tra scheduler thực tế |
| Chỉ cancel ScheduledFuture | Task đang chạy vẫn có thể tiếp tục | Drain active task và chờ hoàn tất |
| Gọi shutdownNow rồi tiếp tục checkpoint ngay | Task có thể chưa dừng, transaction chưa an toàn | Chờ termination có timeout |
| Không chặn task mới trong lúc drain | Active count có thể tăng trở lại | Dùng admission gate |
| Mở scheduler trước database | Job truy cập dependency chưa sẵn sàng | Sắp xếp callback theo dependency |
| Chạy cron trên mọi replica | Side effect bị thực hiện nhiều lần | Distributed lock, leader election hoặc idempotency |
| Giữ retry delay bằng nanoTime qua restore | Thời gian còn lại không đúng policy | Lưu deadline/Instant và tính lại |
| Không lưu cursor nghiệp vụ | Catch up có thể bỏ sót hoặc xử lý trùng | Lưu cursor/watermark bền vững |
| Task giữ transaction xuyên checkpoint | Connection/session có thể đã mất sau restore | Drain và commit/rollback trước checkpoint |
| Mở readiness trước khi worker sẵn sàng | Request thấy trạng thái không nhất quán | Chỉ READY sau khi dependency bắt buộc hoạt động |

## 17. Quy trình thiết kế @Scheduled và background work cho CRaC

Với mỗi job, hãy xác định:

1. Job dùng lịch fixedDelay, fixedRate, cron hay được kích hoạt bởi queue?
2. Có thể chạy đồng thời trên nhiều thread hoặc nhiều replica không?
3. Job đang chạy có thể dừng ở điểm an toàn nào?
4. Cần drain trong bao lâu trước checkpoint?
5. Nếu checkpoint kéo dài, những lần chạy bị bỏ lỡ sẽ được catch up, skip hay coalesce?
6. Trạng thái tiến độ nào phải lưu bền vững?
7. Job cần database, broker, secret hoặc client nào?
8. Resource nào phải sẵn sàng trước khi resume?
9. Cách bảo đảm idempotency và chống xử lý trùng là gì?
10. Readiness và metric nào chứng minh worker đã hoạt động sau restore?

Một ứng dụng Spring Boot dùng CRaC nên quản lý background work như một phần của lifecycle tiến trình. Dừng admission trước checkpoint, drain công việc đang chạy, xử lý transaction và lease theo policy, rồi tính lại lịch sau restore. Với job đơn giản, @Scheduled kết hợp gate có thể đủ; với job có yêu cầu catch-up, retry hoặc lịch chính xác, hãy dùng scheduler và trạng thái nghiệp vụ được quản lý tường minh.

Điều cần bảo đảm sau restore là mỗi công việc chạy đúng theo policy đã định, sử dụng dependency hợp lệ và không tạo side effect trùng. Việc Spring context được khôi phục hoặc method @Scheduled tiếp tục được gọi chỉ là một phần của quá trình; readiness của background worker phải được xác nhận riêng trước khi ứng dụng tiếp tục phục vụ.

