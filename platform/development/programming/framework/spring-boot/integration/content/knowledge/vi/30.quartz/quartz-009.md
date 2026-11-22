# Misfire, chạy chồng và chính sách khôi phục trong Quartz

> **Chương:** Quartz  
> **Module:** SPRING_BOOT_INTEGRATION — tổ chức tích hợp trong Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration; chú trọng cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát.  
> **Mục tiêu:** Thiết kế lịch Quartz không gây chạy chồng ngoài ý muốn, hiểu các misfire instruction, lựa chọn recovery khi tiến trình/nút hỏng và bảo vệ nghiệp vụ trước việc thực thi lặp.

Một job đối soát thanh toán được lên lịch chạy mỗi 5 phút. Lúc 10:00, job bắt đầu gọi một hệ thống bên ngoài và mất 8 phút. Trong khi đó, các mốc 10:05 và 10:10 tiếp tục đến. Đến 10:12, một node Spring Boot gặp lỗi và khởi động lại. Quartz sẽ chạy bao nhiêu lần, theo lịch cũ hay ngay lập tức, và liệu đối soát có bị nhân đôi?

Câu trả lời phụ thuộc vào **ba cơ chế khác nhau**:

1. **Misfire policy** quyết định cách xử lý một lần kích hoạt theo lịch bị bỏ lỡ quá ngưỡng.
2. **Concurrency policy** quyết định các lần thực thi có được chạy đồng thời với **cùng JobKey** hay không.
3. **Recovery policy** quyết định Quartz có cố thực thi lại một job bị ngắt khi scheduler gặp sự cố hay không.

Ba cơ chế này không đồng nghĩa với **exactly-once processing**. Ngay cả khi Quartz chỉ khởi chạy một job tại một thời điểm, một HTTP request hoặc message đã được hệ thống downstream nhận vẫn có thể bị gửi lại sau sự cố. Đó là lý do job tích hợp còn cần **idempotency**, lưu trạng thái bền vững và đối soát.

## 1. Thuật ngữ cần phân biệt

| Khái niệm | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| **Job** | Lớp Java triển khai **org.quartz.Job**, định nghĩa công việc khi Quartz gọi **execute(...)** | Không mặc nhiên có transaction với toàn bộ hệ thống bên ngoài |
| **JobDetail** | Định nghĩa job có định danh **JobKey**, kiểu class, dữ liệu và cờ **requestRecovery** | Không đồng nghĩa một lần thực thi |
| **Trigger** | Quy tắc tạo thời điểm fire; có **TriggerKey**, next fire time, trạng thái và misfire instruction | Không lưu đầy đủ mọi business task cần làm |
| **Fire / execution** | Một lần scheduler cấp lượt thực thi cho JobDetail | Không bảo đảm side effect xảy ra đúng một lần |
| **Misfire** | Trigger không được kích hoạt đúng lịch và bị xử lý theo chính sách misfire sau ngưỡng trễ | Không đồng nghĩa mọi lần trễ đều được chạy bù |
| **Disallow concurrent execution** | Không thực thi đồng thời các instance có **cùng JobDetail/JobKey** | Không chặn JobDetail khác hay ứng dụng không dùng cùng JobStore |
| **Recovery** | Cơ chế thử chạy lại job đang thực thi khi scheduler/node chết, nếu job yêu cầu recovery và JobStore hỗ trợ | Không khôi phục transaction HTTP/DB đã commit một phần |
| **Idempotency** | Xử lý lại cùng một tác vụ mà không tạo tác động nghiệp vụ trùng | Không tự phát hiện mọi việc còn thiếu nếu không có trạng thái đối soát |

Quartz quản lý **lịch kích hoạt** và **lifecycle thực thi**. Còn đơn hàng đã cập nhật, khoản tiền đã thu, sự kiện broker đã phát và task nào còn pending là dữ liệu nghiệp vụ phải được ứng dụng quản lý.

## 2. Khi nào một trigger trở thành misfire?

Giả sử CronTrigger dự kiến chạy vào 10:00, 10:05, 10:10. Scheduler bị dừng hoặc không thể cấp đủ worker thread, đến 10:12 mới hoạt động bình thường:

~~~mermaid
timeline
    title Mốc chạy dự kiến và thời gian scheduler sẵn sàng trở lại
    10:00 : Fire dự kiến thứ nhất
    10:05 : Fire dự kiến thứ hai
    10:10 : Fire dự kiến thứ ba
    10:12 : Scheduler hoạt động lại
~~~

Quartz so sánh thời điểm **nextFireTime** với thời gian hiện tại và **misfireThreshold** của JobStore. Nếu trigger trễ đủ lớn, JobStore áp dụng misfire instruction tương ứng. Một số nguyên nhân phổ biến:

- Scheduler bị shutdown, node bị kill hoặc service triển khai lại.
- Worker thread bị chiếm bởi job chạy lâu, khiến không có thread rảnh cho trigger.
- Scheduler được đưa vào standby hoặc trigger bị pause rồi resume.
- JDBC JobStore không truy cập được database, nghẽn connection pool hay lock.
- Node bị treo, GC pause dài, CPU quá tải hoặc độ trễ hạ tầng tăng.

Thiết lập thông dụng của Quartz là:

~~~properties
org.quartz.jobStore.misfireThreshold=60000
~~~

Giá trị **60.000 ms** là ngưỡng thường dùng/mặc định của Quartz JobStore; cần kiểm tra cấu hình thực tế trong ứng dụng. Đừng diễn giải đây là một timer riêng cứ đúng 60 giây sẽ phát hiện lỗi: việc phát hiện còn phụ thuộc chu kỳ truy vấn JobStore và khi scheduler có cơ hội xử lý trigger.

**Phân biệt trễ nhỏ với misfire:** một lần fire trễ vài giây do hệ thống bận có thể chỉ là trễ lịch, chưa đạt misfire threshold. Một trigger được đánh dấu misfire sẽ được cập nhật theo instruction; điều đó có thể làm thay đổi nextFireTime và số lần thực thi trong tương lai.

## 3. Misfire của CronTrigger: chạy một lần ngay hay bỏ qua?

CronTrigger dùng cron expression của Quartz, ví dụ **0 0/5 * * * ?** nghĩa là mỗi 5 phút tại giây 0. Cron của Quartz có **trường giây**, khác cú pháp cron 5 trường quen thuộc của Unix.

Với **CronScheduleBuilder**, hai lựa chọn quan trọng là:

| Lựa chọn | API | Khi trở lại sau quãng ngừng |
| --- | --- | --- |
| **Fire once now** | **withMisfireHandlingInstructionFireAndProceed()** | Thực hiện một lần ngay khi xử lý misfire, rồi tiếp tục lịch cron về sau |
| **Do nothing** | **withMisfireHandlingInstructionDoNothing()** | Bỏ các lần fire đã trễ; chọn mốc cron hợp lệ tiếp theo sau hiện tại |
| **Ignore misfires** | **withMisfireHandlingInstructionIgnoreMisfires()** | Bỏ qua cơ chế misfire thông thường; có thể dẫn đến các lượt fire liên tiếp để bắt kịp lịch |

**SMART_POLICY** là chính sách mặc định khi không chọn instruction cụ thể. Với CronTrigger của Quartz, SMART_POLICY được diễn giải như **FIRE_ONCE_NOW** trong xử lý misfire thông thường. Tuy nhiên nên chọn tường minh để người vận hành biết hệ thống muốn **catch up một lần** hay **skip**.

### 3.1. Cấu hình CronTrigger không chạy bù

~~~java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger cron = TriggerBuilder.newTrigger()
        .withIdentity("invoice-reconciliation-trigger", "billing")
        .forJob(reconciliationJobDetail)
        .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0/5 * * * ?")
                .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionDoNothing())
        .build();
~~~

Ví dụ sử dụng biến **reconciliationJobDetail** đã được khởi tạo ở phần cấu hình đầy đủ bên dưới. Nếu scheduler trở lại lúc 10:12, lựa chọn **DO_NOTHING** đưa lần fire tiếp theo về mốc 10:15 (giả sử trigger còn hiệu lực, không có lịch ngoại lệ, timezone tương ứng).

Lựa chọn này phù hợp khi:

- Job cập nhật cache, đọc chỉ số hiện hành hoặc làm mới trạng thái **mới nhất**.
- Mỗi lượt chạy tự quét **toàn bộ công việc quá hạn** từ database; không dựa vào mỗi tick để đại diện cho một business period.
- Bắn lại từng tick cũ không mang thêm giá trị và có thể gây quá tải sau downtime.

### 3.2. Cấu hình CronTrigger chạy một lần sau misfire

~~~java
Trigger catchUpOnce = TriggerBuilder.newTrigger()
        .withIdentity("catch-up-once", "billing")
        .forJob(reconciliationJobDetail)
        .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0/5 * * * ?")
                .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionFireAndProceed())
        .build();
~~~

Nếu các mốc 10:00, 10:05 và 10:10 bị bỏ lỡ, policy này **không cam kết chạy riêng ba lần**. Nó thường tạo **một lần thực thi ngay** để xử lý misfire và sau đó quay về lịch cron. Vì thế không nên tính số bản ghi cần xử lý bằng số fire bị bỏ lỡ.

Với đối soát theo ngày, cách an toàn hơn là job **quét các ngày/chứng từ chưa đối soát trong database**. Một lần fire sau restart có thể xử lý nhiều ngày còn thiếu mà không cần tái tạo mọi thời điểm cron lịch sử.

### 3.3. Tại sao hạn chế IGNORE_MISFIRE_POLICY?

Khi bỏ qua cơ chế misfire, các lần fire quá hạn có thể được scheduler xử lý dồn dập. Ví dụ job gửi email định kỳ hoặc gọi API giới hạn tốc độ có thể phát hàng loạt yêu cầu ngay sau khi node hoạt động lại. Chính sách này chỉ nên dùng khi đã hiểu chính xác số lần fire, tải downstream, cách chống trùng và giới hạn thời gian.

Misfire policy không phải **hàng đợi durable cho từng công việc nghiệp vụ**. Nếu mỗi kỳ thanh toán bắt buộc được xử lý, hãy lưu kỳ thanh toán vào dữ liệu bền vững; Quartz chỉ đánh thức worker để thực hiện.

## 4. Misfire của SimpleTrigger: số lần lặp ảnh hưởng kết quả

SimpleTrigger chạy theo khoảng cố định hoặc số lần lặp giới hạn. Ví dụ:

~~~java
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger heartbeat = TriggerBuilder.newTrigger()
        .withIdentity("heartbeat", "integration")
        .forJob(reconciliationJobDetail)
        .withSchedule(SimpleScheduleBuilder.simpleSchedule()
                .withIntervalInMinutes(5)
                .repeatForever()
                .withMisfireHandlingInstructionNextWithRemainingCount())
        .build();
~~~

Các API lựa chọn của **SimpleScheduleBuilder**:

| API | Ý định chính |
| --- | --- |
| **withMisfireHandlingInstructionFireNow()** | Đưa một lần fire về thời điểm hiện tại |
| **withMisfireHandlingInstructionNowWithExistingCount()** | Reschedule bắt đầu từ hiện tại và giữ quy tắc repeat count hiện có |
| **withMisfireHandlingInstructionNowWithRemainingCount()** | Reschedule từ hiện tại và điều chỉnh số lần lặp còn lại theo phần lịch đã trôi qua |
| **withMisfireHandlingInstructionNextWithExistingCount()** | Chuyển tới mốc lịch tiếp theo, giữ repeat count hiện có |
| **withMisfireHandlingInstructionNextWithRemainingCount()** | Chuyển tới mốc lịch tiếp theo, tính lại số lần lặp còn lại |
| **withMisfireHandlingInstructionIgnoreMisfires()** | Không áp dụng xử lý misfire chuẩn |

Với SimpleTrigger có giới hạn lặp, sự khác biệt giữa **existing count** và **remaining count** có thể quyết định số lượt chạy còn lại sau downtime. Với **repeatForever()**, không có tổng số lần lặp hữu hạn để giữ. Hãy kiểm thử mốc giờ cụ thể (startAt, endAt, repeat interval, repeat count) thay vì suy luận tên API là đủ.

Không chọn **SMART_POLICY** chỉ vì nhìn ngắn hơn: Quartz có thể diễn giải SMART_POLICY của SimpleTrigger khác nhau tùy repeat count và kiểu lặp. Khi nghiệp vụ yêu cầu số lần thực thi chính xác, hãy chỉ rõ policy và viết test cho tình huống trễ.

## 5. Chạy chồng (overlap): hai execution cùng thời điểm

Một job dự kiến chạy mỗi 5 phút nhưng đôi khi cần 8 phút mới xong. Nếu nhiều worker thread có sẵn, Quartz có thể cấp một lần thực thi khác của cùng JobDetail khi lượt trước vẫn đang chạy, **trừ khi áp dụng cơ chế ngăn chạy đồng thời**.

~~~mermaid
gantt
    title Lịch 5 phút, thời gian chạy 8 phút
    dateFormat HH:mm
    axisFormat %H:%M
    section Không chặn overlap
    Fire A :a1, 10:00, 8m
    Fire B :a2, 10:05, 8m
    Fire C :a3, 10:10, 8m
~~~

Chạy chồng có thể gây:

- Cùng một hóa đơn bị tính hai lần hoặc hai job cùng cập nhật một row.
- Hai batch quét chung tập bản ghi **PENDING**, dẫn tới gọi downstream trùng.
- Hai job cùng ghi cache, index hoặc file output theo thứ tự không dự đoán được.
- Hết connection pool/HTTP pool vì số job chạy đồng thời tăng.

### 5.1. Dùng @DisallowConcurrentExecution

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;

@DisallowConcurrentExecution
public class ReconciliationJob implements Job {
    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        // Gọi logic xử lý kỳ đối soát còn thiếu.
        // Triển khai thật ở phần 8.
    }
}
~~~

Annotation **@DisallowConcurrentExecution** yêu cầu Quartz không chạy đồng thời hai instance của cùng **JobDetail/JobKey**. Đây là điểm dễ nhầm:

~~~text
Job class = ReconciliationJob

JobKey("daily", "billing")   -> chặn overlap giữa các fire của "daily"
JobKey("hourly", "billing")  -> chặn overlap giữa các fire của "hourly"

Hai JobKey khác nhau cùng dùng ReconciliationJob
-> vẫn có thể chạy đồng thời với nhau.
~~~

Nếu nhiều Trigger trỏ tới **cùng JobDetail**, annotation áp dụng chung JobKey đó. Nếu mỗi node khởi tạo JobDetail với key khác nhau hoặc dùng **RAMJobStore riêng**, Quartz không có một ranh giới chung để phối hợp.

**Chặn overlap không có nghĩa bỏ lần chạy trễ.** Các trigger vẫn có lịch và trạng thái; những lần chờ do job đang chạy có thể trở thành misfire khi đủ ngưỡng. Sau khi job trước hoàn thành, Quartz áp dụng chính sách misfire để quyết định lượt tiếp theo.

### 5.2. Giữ JobDataMap sau lần chạy

**@PersistJobDataAfterExecution** yêu cầu Quartz lưu lại dữ liệu JobDataMap đã cập nhật sau execution. Nếu job sửa trạng thái trong JobDataMap, thường nên dùng cùng **@DisallowConcurrentExecution** để tránh hai execution ghi đè trạng thái của nhau:

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.PersistJobDataAfterExecution;

@PersistJobDataAfterExecution
@DisallowConcurrentExecution
public class StatefulPollingJob implements Job {
    @Override
    public void execute(JobExecutionContext context) {
        var data = context.getJobDetail().getJobDataMap();
        long cursor = data.containsKey("lastSeenId")
                ? data.getLong("lastSeenId") : 0L;
        // Xử lý cursor theo nghiệp vụ ...
        data.put("lastSeenId", cursor + 1);
    }
}
~~~

**Lưu ý:** JobDataMap không thay thế bảng nghiệp vụ cho checkpoint quan trọng. Không nên đặt object service/connection hoặc payload không serializable vào JobDataMap của persistent JobStore. Nếu bên ngoài đã xử lý xong nhưng Quartz chưa lưu cursor trước khi crash, lần sau có thể chạy lặp; cần idempotency tại đích.

### 5.3. Chặn overlap không chặn trùng khi hai node không chia sẻ JobStore

Khi triển khai hai instance Spring Boot cùng schedule nhưng **mỗi instance có RAMJobStore riêng**, cả hai có thể tự kích hoạt job lúc 10:00. Annotation chỉ ngăn concurrency trong phạm vi mà scheduler/JobStore đang quản lý. Nếu muốn Quartz phân công lịch giữa các node, sử dụng **JDBC JobStore hỗ trợ clustering** với cùng database/scheduler configuration và **instanceId riêng** cho từng node.

Ngay cả với cluster đúng, một tác vụ gửi sang hệ thống ngoài vẫn phải chống trùng do lỗi mạng và recovery.

## 6. Recovery: Quartz làm gì khi scheduler hoặc node hỏng?

Phân biệt hai loại công việc sau downtime:

1. **Trigger chưa fire đúng lịch:** được xét là **misfire** và xử lý theo policy của trigger.
2. **Job đã bắt đầu chạy nhưng node chết giữa chừng:** có thể được Quartz **re-execute** nếu **JobDetail yêu cầu recovery** và JobStore/persistence cho phép phát hiện lần chạy bị ngắt.

Khi tạo JobDetail:

~~~java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;

JobDetail detail = JobBuilder.newJob(ReconciliationJob.class)
        .withIdentity("reconcile-overdue-periods", "billing")
        .requestRecovery(true)
        .storeDurably()
        .build();
~~~

Trong job, có thể kiểm tra:

~~~java
if (context.isRecovering()) {
    // Quartz đang khởi chạy một execution để phục hồi
    // công việc bị ngắt bởi sự cố scheduler trước đó.
    log.warn("Recovery execution for jobKey={}",
             context.getJobDetail().getKey());
}
~~~

**requestRecovery(true)** không có nghĩa Quartz phát lại mọi cron tick bị bỏ lỡ. Nó dùng cho **job đang executing khi scheduler chết**. Không có cờ này, Quartz không mặc định khôi phục execution đang dang dở; trigger sau restart vẫn được xử lý theo trạng thái và misfire policy.

### 6.1. Tại sao recovery vẫn có thể tạo side effect trùng?

~~~mermaid
sequenceDiagram
    participant Q as Quartz Node A
    participant DB as Business DB
    participant X as External Payment API
    participant B as Quartz Node B
    Q->>DB: Đánh dấu tác vụ đang xử lý
    Q->>X: POST /charge idempotencyKey=invoice-42
    X-->>Q: 200 OK
    Note over Q: Node A crash trước khi lưu trạng thái DONE
    B->>B: Phát hiện failed instance
    Note over B: Recovery job nếu requestsRecovery=true
    B->>X: POST /charge idempotencyKey=invoice-42
    Note over X: Trả lại kết quả cũ theo idempotency key
    X-->>B: Kết quả charge đã có
    B->>DB: Lưu DONE
~~~

Nếu Payment API **không** hỗ trợ idempotency, request thứ hai có thể thu tiền lần nữa. Quartz không thể biết response 200 đã xảy ra trước crash, vì kết quả bên ngoài không nằm trong transaction với Quartz JobStore.

Đối với công việc liên quan tiền, tồn kho, gửi email, message broker hoặc tạo tài liệu, cần:

- **Business operation key ổn định** qua retry và recovery, ví dụ **invoiceId**, **orderId + actionType** hoặc **jobType + businessPeriod**.
- Constraint UNIQUE/checkpoint trong database và/hoặc idempotency key mà downstream công nhận.
- Tách trạng thái **PENDING / RUNNING / DONE / FAILED / NEEDS_REVIEW** để biết còn việc phải xử lý.
- Retry với backoff, giới hạn số lần; nếu kết quả remote chưa rõ thì **query status** trước khi lặp lệnh nguy hiểm.
- Cơ chế reconciliation để so sánh trạng thái local và remote sau một lỗi không thể tự quyết định.

**Không dùng fireInstanceId hoặc timestamp hiện tại làm idempotency key** cho nghiệp vụ cần chạy lại sau crash. Các giá trị này có thể thay đổi giữa execution gốc và recovery, khiến phía nhận tưởng là hai yêu cầu khác nhau.

### 6.2. Recovery khác retry sau exception

Job chạy và **ném JobExecutionException** là lỗi execution bình thường khi scheduler vẫn sống. Quartz mặc định không cung cấp chiến lược exponential backoff cho mọi exception.

~~~java
try {
    reconciliationService.reconcileDuePeriods();
} catch (RuntimeException ex) {
    // Cho Quartz biết job đã lỗi;
    // không yêu cầu refireImmediately vô hạn.
    throw new JobExecutionException("Reconciliation failed", ex);
}
~~~

**JobExecutionException.setRefireImmediately(true)** có thể yêu cầu fire lại ngay; không có backoff và dễ tạo vòng lặp khi hệ thống đích đang lỗi. Có các tùy chọn unschedule firing trigger hoặc all triggers, nhưng sử dụng chúng phải theo chính sách vận hành rõ ràng. Với lỗi tích hợp tạm thời, thường hợp lý hơn khi lưu trạng thái lỗi có thể retry, để lần tick kế tiếp hoặc một retry trigger có giới hạn xử lý.

**Recovery** xử lý scheduler bị mất giữa execution; **retry** xử lý lỗi đã được job quan sát; **misfire** xử lý trigger lỡ lịch. Không nên dùng một cơ chế để thay toàn bộ các cơ chế còn lại.

## 7. Persistent JobStore và clustering trong Spring Boot

**RAMJobStore** lưu lịch trong bộ nhớ của một scheduler. Sau khi tiến trình chết/restart, JobDetail/Trigger được tạo lại từ cấu hình ứng dụng nếu có khai báo; không có lịch persisted xuyên restart để phục hồi trạng thái thực thi cũ theo cách JDBC JobStore làm được.

**JDBC JobStore** lưu lịch, trigger state và metadata cần thiết vào database. Trong cluster, các node sử dụng **cùng bộ bảng Quartz** và phối hợp việc acquire trigger; khi một node chết, node khác có thể phát hiện và phục hồi theo cấu hình.

### 7.1. Cấu hình mẫu

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      # Dùng migration có kiểm soát để tạo schema trước khi chạy.
      initialize-schema: never
    wait-for-jobs-to-complete-on-shutdown: true
    properties:
      org:
        quartz:
          scheduler:
            instanceName: BillingQuartzCluster
            instanceId: AUTO
          jobStore:
            isClustered: true
            clusterCheckinInterval: 20000
            misfireThreshold: 60000
          threadPool:
            threadCount: 8
~~~

Ví dụ áp dụng khi đã có **Quartz tables** tương thích với phiên bản Quartz và datasource đã được cấu hình trong Spring Boot. Dùng Flyway/Liquibase hoặc quy trình database migration để quản lý schema. Với cấu hình tự khởi tạo Quartz schema, phải xem kỹ script của phiên bản tương ứng vì một số script mẫu **drop các bảng hiện có**; không chạy chế độ khởi tạo phá dữ liệu trong production.

**Cẩn trọng với Spring Boot auto-configuration:** Spring Boot cung cấp tích hợp SchedulerFactoryBean và JobStore dùng DataSource. Tự cấu hình **org.quartz.jobStore.class** theo ví dụ Quartz thuần có thể làm mất tích hợp datasource/transaction manager mà Boot đang quản lý. Chỉ thay đổi khi hiểu rõ cơ chế JobStore đang hoạt động và đã kiểm thử restart/cluster.

Những yêu cầu vận hành:

| Thành phần | Quy tắc |
| --- | --- |
| **Quartz database** | Các node cùng cluster trỏ đến cùng bảng Quartz, schema tương thích và connection pool đủ dùng |
| **instanceName** | Đồng nhất giữa các node cùng scheduler cluster |
| **instanceId** | Duy nhất trên mỗi instance; AUTO thuận tiện trong nhiều triển khai |
| **Clocks** | Đồng bộ đồng hồ hệ thống (NTP) để giảm sai lệch khi trigger/recovery |
| **Clustered flag** | Bật đúng trên các node chia sẻ cùng JobStore; không trộn cấu hình cluster/noncluster trên cùng bảng |
| **Thread pool** | Giới hạn số job đồng thời; tính cả thời gian job bị chặn bởi I/O |
| **Shutdown** | Graceful shutdown phù hợp với thời gian job và thời hạn container; không coi là bảo đảm nếu tiến trình bị kill |
| **Deploy** | Tránh mỗi lần khởi động ghi đè/đổi lịch hoặc xóa trigger ngoài chủ đích |

Đừng coi **clustering=true** là distributed lock cho mọi đoạn code của ứng dụng: nó phối hợp các job/trigger Quartz đã đăng ký. Nếu có một worker ngoài Quartz cũng xử lý cùng business task, cả hai vẫn có thể tranh chấp tài nguyên; cần claim và uniqueness tại lớp nghiệp vụ.

## 8. Ví dụ hoàn chỉnh: lịch đánh thức job đối soát an toàn

Thiết kế mẫu: mỗi 5 phút, Quartz đánh thức job; job gọi service tìm **business period chưa DONE** và xử lý theo khóa nghiệp vụ. Nếu trễ cron, ta có thể bỏ các tick cũ vì những business period còn thiếu vẫn được lưu trong DB.

### 8.1. JobDetail + CronTrigger với policy rõ ràng

~~~java
package example.integration.quartz;

import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReconciliationQuartzConfiguration {

    @Bean
    public JobDetail reconciliationJobDetail() {
        return JobBuilder.newJob(ReconciliationJob.class)
                .withIdentity("reconcile-overdue-periods", "billing")
                .withDescription("Scan durable pending business periods")
                .requestRecovery(true)
                .storeDurably()
                .build();
    }

    @Bean
    public Trigger reconciliationTrigger(
            JobDetail reconciliationJobDetail) {
        return TriggerBuilder.newTrigger()
                .withIdentity("reconcile-every-five-minutes", "billing")
                .forJob(reconciliationJobDetail)
                .withSchedule(CronScheduleBuilder
                        .cronSchedule("0 0/5 * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                        .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

Lựa chọn **DO_NOTHING** ở đây là chính sách **bỏ lịch đã trễ**, không bỏ dữ liệu cần xử lý. Để bảo đảm điều đó, **reconcileDuePeriods()** phải truy vấn backlog trong database, không chỉ xử lý **một** period suy từ thời điểm Quartz vừa fire.

### 8.2. Job không chạy chồng với cùng JobKey

~~~java
package example.integration.quartz;

import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@DisallowConcurrentExecution
public class ReconciliationJob implements Job {
    private static final Logger log =
            LoggerFactory.getLogger(ReconciliationJob.class);
    private final ReconciliationService service;

    public ReconciliationJob(ReconciliationService service) {
        this.service = service;
    }

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        log.info("Quartz fire job={}, scheduledAt={}, recovering={}",
                context.getJobDetail().getKey(),
                context.getScheduledFireTime(),
                context.isRecovering());

        try {
            service.reconcileDuePeriods();
        } catch (RuntimeException ex) {
            log.error("Quartz reconcile failed, job={}",
                    context.getJobDetail().getKey(), ex);
            throw new JobExecutionException(
                    "Reconcile failed; pending periods remain durable", ex);
        }
    }
}
~~~

Ví dụ dùng **constructor injection** vào Quartz job; để nó hoạt động, môi trường phải cung cấp **JobFactory có tích hợp Spring dependency injection**. Một cách cấu hình tường minh cho ví dụ:

~~~java
package example.integration.quartz;

import org.quartz.Job;
import org.quartz.spi.JobFactory;
import org.springframework.beans.factory.config.AutowireCapableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuartzJobFactoryConfiguration {
    @Bean
    public JobFactory jobFactory(AutowireCapableBeanFactory beanFactory) {
        return (bundle, scheduler) ->
                (Job) beanFactory.createBean(
                        bundle.getJobDetail().getJobClass());
    }
}
~~~

JobFactory trên chỉ minh họa việc tạo job với constructor injection; nếu ứng dụng đã có JobFactory riêng, cần tích hợp vào cấu hình hiện có thay vì khai báo trùng. Khi custom factory, kiểm tra yêu cầu inject **JobDataMap** hoặc quy tắc tạo job khác của hệ thống. Spring Boot có thể có cách autowire job khác tùy phiên bản và cấu hình.

### 8.3. Service xử lý backlog bằng business key

Giả sử database có bảng các kỳ cần đối soát:

~~~sql
CREATE TABLE reconciliation_period (
    business_date DATE PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reconciliation_due
    ON reconciliation_period (status, business_date);

CREATE TABLE daily_settlement (
    business_date DATE PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

**business_date** là idempotency key cho đầu ra **daily_settlement**. Nếu một ngày đã được tính và worker chạy lại, ghi bằng upsert sẽ tránh tạo dòng trùng:

~~~sql
INSERT INTO daily_settlement (business_date, total_amount)
VALUES (:businessDate, :totalAmount)
ON CONFLICT (business_date)
DO UPDATE SET
    total_amount = EXCLUDED.total_amount,
    calculated_at = NOW();
~~~

Ví dụ upsert giả định phép tính có thể chạy lại với dữ liệu đầu vào và cutoff nhất quán. Nếu kết quả phụ thuộc tập giao dịch thay đổi theo thời gian, cần **snapshot/cutoff/version** hoặc quy tắc điều chỉnh để lần chạy lại không vô tình sửa báo cáo đã chốt.

Khi có nhiều worker xử lý backlog, dùng transaction ngắn để **claim** mỗi period và cấp lease, thay vì giữ transaction mở suốt cuộc gọi HTTP:

~~~sql
-- PostgreSQL: chỉ một worker claim thành công cho period này.
UPDATE reconciliation_period
SET status = 'RUNNING',
    lease_owner = :workerId,
    lease_until = NOW() + INTERVAL '2 minutes',
    updated_at = NOW()
WHERE business_date = :businessDate
  AND (
       status IN ('PENDING', 'FAILED')
       OR (status = 'RUNNING' AND lease_until < NOW())
  )
RETURNING business_date;
~~~

**0 dòng trả về** nghĩa là worker không nhận được quyền xử lý period ở thời điểm này. Nếu xử lý lâu hơn lease, phải gia hạn lease một cách an toàn. Khi cập nhật kết quả, kiểm tra **lease_owner/fencing token** để worker cũ không ghi đè thành công của worker mới; lease chỉ là biện pháp điều phối, không thay cho tính idempotent tại DB và downstream.

Một service điều phối ở mức ý tưởng:

~~~java
@Service
public class ReconciliationService {
    private final PeriodRepository periods;
    private final ReconciliationWorker worker;

    public ReconciliationService(PeriodRepository periods,
                                 ReconciliationWorker worker) {
        this.periods = periods;
        this.worker = worker;
    }

    public void reconcileDuePeriods() {
        for (LocalDate day : periods.findPendingOrExpired(100)) {
            worker.tryClaimAndReconcile(day);
        }
    }
}
~~~

Các kiểu **PeriodRepository**, **ReconciliationWorker** là các abstraction nghiệp vụ do ứng dụng triển khai; ví dụ minh họa ranh giới trách nhiệm, không phải API có sẵn của Quartz. **tryClaimAndReconcile** cần tách transaction claim ngắn, xử lý công việc, ghi kết quả và hoàn tất trạng thái bằng transaction phù hợp. Nếu có HTTP hoặc broker, dùng **outbox + consumer idempotent** hoặc API idempotency key; không gộp các side effect thành một **@Transactional** JDBC rồi coi đã atomic xuyên hệ thống.

### 8.4. Vì sao requestRecovery(true) và DO_NOTHING vẫn hợp nhau?

- **DO_NOTHING** chỉ định bỏ các **mốc cron chưa được kích hoạt** trong khoảng trễ.
- **requestRecovery(true)** yêu cầu phục hồi **job đã bắt đầu nhưng bị scheduler ngắt**.
- **@DisallowConcurrentExecution** giữ những execution có cùng **JobKey** khỏi chạy đồng thời khi Quartz quản lý được chúng.
- **Database backlog + business idempotency** bảo đảm một period bỏ lỡ vẫn có thể được tìm lại và xử lý an toàn ngay cả khi job được thực thi lặp.

Đây là cấu hình phù hợp cho nhiều job tích hợp: scheduler chỉ chịu trách nhiệm **đánh thức**, dữ liệu nghiệp vụ bền vững mới là nguồn sự thật của việc phải làm.

## 9. Chính sách lựa chọn theo bản chất công việc

| Loại job | Misfire nên cân nhắc | Overlap | Recovery và dữ liệu |
| --- | --- | --- | --- |
| **Refresh cache** từ nguồn chính | DO_NOTHING nếu lần sau làm mới toàn bộ | Thường chặn cùng JobKey | Chạy lại được; không cần replay từng tick |
| **Quét outbox/inbox backlog** | DO_NOTHING hoặc FIRE_ONCE_NOW | Chặn overlap, hoặc phân chia worker/claim an toàn | Lưu backlog trong DB; retry và idempotent consumer |
| **Đối soát hóa đơn theo kỳ** | DO_NOTHING nếu job quét kỳ quá hạn; FIRE_ONCE_NOW nếu muốn đánh thức ngay sau restart | Chặn cùng JobKey + unique business period | requestRecovery + checkpoint/lease + reconcile |
| **Xuất báo cáo theo ngày** | Chọn chính sách theo deadline; không dựa vào fire count để suy ngày bị thiếu | Ngăn tạo cùng báo cáo 2 lần | Lưu khóa **reportType + businessDate**, trạng thái xuất bản |
| **Gửi email/notification** | Không replay tùy tiện mọi tick; xác định task cần gửi bằng dữ liệu bền vững | Chặn hoặc chia batch bằng claim | Outbox, messageId, deduplication, rate limiting |
| **Thu tiền/thao tác không đảo ngược** | Không tự động FIRE_NOW nếu chưa xác minh trạng thái kỳ trước | Chặn nhưng vẫn cần idempotency | Downstream idempotency key và truy vấn trạng thái khi timeout |
| **Heartbeat/health probe** | DO_NOTHING, không cần fire lại quá khứ | Có thể bỏ nếu lần trước còn chạy | Không lưu lịch sử tick làm công việc nghiệp vụ |

Nếu business yêu cầu chạy **mỗi kỳ** bất kể downtime, giải pháp cốt lõi là tạo/lưu **đơn vị công việc theo kỳ** và xử lý bù trong database. Cấu hình misfire chỉ quyết định **khi nào worker được gọi**, không tạo bảo đảm business đầy đủ.

## 10. Ma trận sự cố và kết quả mong đợi

| Sự cố | Điều Quartz có thể thực hiện | Ứng dụng cần bổ sung |
| --- | --- | --- |
| Job chạy lâu hơn chu kỳ | Chạy chồng nếu không chặn; nếu chặn thì lượt sau chờ và có thể misfire | @DisallowConcurrentExecution, giới hạn thread, idempotent business task |
| Scheduler dừng 20 phút | Cập nhật trigger theo misfire instruction sau restart | Quét backlog nếu từng period phải được xử lý |
| Node chết trong lúc gọi REST | Recovery execution khi có requestRecovery và JobStore phù hợp | Idempotency key cho REST; query trạng thái nếu kết quả không rõ |
| Node chết sau khi DB commit nhưng trước khi gửi event | Quartz có thể chạy lại job | Outbox transaction cùng DB và publisher retry |
| Broker nhận event rồi ACK bị mất | Quartz không thể biết chính xác side effect phía broker | EventId ổn định, consumer deduplication/inbox |
| Hai node dùng RAMJobStore riêng | Mỗi node có thể tự chạy lịch | Chuyển JDBC cluster hoặc dùng cơ chế leader/claim phù hợp |
| JDBC cluster mất DB | Không acquire/commit trigger được như bình thường | Cảnh báo DB, retry, khôi phục backlog sau khi DB trở lại |
| Cron đổi timezone hoặc DST | Next fire time phụ thuộc timezone, cron và lịch thực tế | Quy định timezone/cutoff, kiểm thử DST nếu vùng có chuyển giờ |
| Job ném exception | Execution thất bại, job không mặc định exponential retry | Trạng thái FAILED, bounded retry và alert |
| Worker mất lease khi vẫn chạy | Một worker mới có thể claim cùng period | Fencing token, unique key, side effect idempotent |

## 11. Quan sát scheduler và nghiệp vụ

Khi một job chạy lâu hoặc không chạy, cần phân biệt **lịch** và **thực thi nghiệp vụ**. Theo dõi:

| Nhóm metric/log | Ví dụ dữ liệu |
| --- | --- |
| **Scheduling lag** | Chênh lệch **actual fire time - scheduled fire time** |
| **Execution duration** | Thời gian job chạy, phân vị p95/p99, job vượt giới hạn |
| **Misfire** | Số trigger misfire theo nhóm, policy, thời gian trễ |
| **Recovery** | Số lần **isRecovering=true**, lỗi khi recovery |
| **Overlap/blocked** | Trigger blocked, số worker Quartz đang bận, thread pool sử dụng |
| **Backlog** | Số period PENDING, tuổi công việc cũ nhất, số task RUNNING quá lease |
| **Business success** | Số period DONE, FAILED, NEEDS_REVIEW, số lần xử lý trùng bị chặn |
| **Downstream** | HTTP timeout, retry, rate limit, broker lag, DLQ, outbox chưa publish |

Quartz hỗ trợ **JobListener**, **TriggerListener** và **SchedulerListener** để ghi trạng thái từ cơ chế lịch. Một số sự kiện misfire được quan sát qua **TriggerListener.triggerMisfired(...)**; không nên mặc định chỉ log trong **Job.execute(...)** là nhìn thấy misfire, vì một trigger bị skip có thể không dẫn tới execute.

Khi log, gắn **JobKey**, **TriggerKey**, **scheduledFireTime**, **fireTime**, **isRecovering**, **businessPeriod**, **correlationId** và **attempt** nếu có. Không dùng **fireInstanceId** làm idempotency key nghiệp vụ; nó phù hợp hơn cho việc phân biệt lần fire trong log/diagnostics.

Các chỉ số Quartz không thay thế chỉ số nghiệp vụ. Scheduler có thể liên tục fire thành công trong khi bảng **reconciliation_period** đang tồn tại nhiều task quá hạn. Đặt cảnh báo dựa vào **độ tuổi backlog**, tỷ lệ hội tụ và sai lệch giữa local/downstream.

## 12. Kiểm thử tình huống misfire, overlap và recovery

Kiểm thử cần chủ động tạo **failure window**, không chỉ test rằng một job có thể chạy một lần.

### 12.1. Misfire của CronTrigger

1. Tạo cron trigger với khoảng ngắn trong môi trường test; đặt policy **DO_NOTHING**.
2. Pause scheduler hoặc trigger đủ lâu vượt **misfireThreshold**, sau đó resume.
3. Kiểm tra không có burst nhiều fire bù, nextFireTime tiến tới lịch tương lai hợp lệ.
4. Thực hiện tương tự với **FIRE_ONCE_NOW**, quan sát một lần fire xử lý misfire và lịch tiếp tục.

Khi test logic tính ngày nghiệp vụ, dùng **Clock** được inject để kiểm soát thời gian; khi test Quartz thực tế có thể cần timeouts và polling với ngưỡng hợp lý. Không bắt unit test vào đúng một mili giây dễ khiến test flaky.

### 12.2. Overlap theo JobKey

1. Chạy job thứ nhất với latch để nó giữ trạng thái đang chạy.
2. Fire trigger thứ hai gắn **cùng JobDetail**.
3. Xác minh tối đa một execution của JobKey đó chạy ở cùng thời điểm khi có **@DisallowConcurrentExecution**.
4. Tạo hai JobDetail khác key cùng class và chứng minh annotation không bảo vệ tài nguyên nghiệp vụ dùng chung giữa hai key.

### 12.3. Restart và failover cluster

1. Chạy hai scheduler instance cùng **JDBC JobStore** trong môi trường tích hợp có database thật (ví dụ Testcontainers PostgreSQL).
2. Giao job có **requestRecovery(true)** cho node A, cho job ghi dấu đã bắt đầu.
3. Dừng đột ngột node A, đợi cơ chế cluster phát hiện instance lỗi.
4. Quan sát node B khởi chạy recovery (**isRecovering=true**) và kiểm tra kết quả nghiệp vụ chỉ có một bản ghi/side effect logic theo idempotency key.
5. Kiểm tra thêm job **không** bật requestRecovery và trigger misfire sau downtime.

**Không dùng graceful shutdown để mô phỏng process crash** nếu mục tiêu là kiểm chứng recovery: graceful shutdown có thể chờ job hoàn tất và không tạo trạng thái in-progress bị bỏ rơi.

### 12.4. Thử lỗi tích hợp thật

- Process chết **sau khi HTTP downstream thành công nhưng trước khi lưu DONE**.
- Process chết **sau DB commit nhưng trước khi outbox được publish**.
- Broker đã nhận event nhưng publisher **chưa nhận được ACK**.
- Lần xử lý một businessPeriod mất hơn thời hạn lease và một worker khác claim lại.
- Scheduler bị pause qua nhiều cron tick; backlog vẫn được xử lý đủ theo business keys.
- Một node thiếu connection hoặc JDBC database bị ngắt một khoảng; job trở lại bình thường sau khi kết nối khôi phục.

Kiểm tra đúng **trạng thái cuối cùng, tính không nhân đôi và khả năng tự phục hồi**, không chỉ dựa vào số lần **execute(...)** được gọi.

## 13. Những lỗi triển khai thường gặp

**“Job trễ một phút thì chắc chắn misfire đúng lúc trễ một phút.”** Misfire threshold là ngưỡng xử lý, không phải lịch timer cứng; còn phụ thuộc thời điểm JobStore rà soát và scheduler lấy trigger.

**“Cron FIRE_ONCE_NOW sẽ chạy bù toàn bộ 12 tick bị bỏ lỡ.”** Đây thường là một lần fire ngay sau misfire, không bảo đảm đủ từng tick. Muốn xử lý từng kỳ phải lưu kỳ nghiệp vụ.

**“@DisallowConcurrentExecution ngăn mọi instance của cùng class ở tất cả ứng dụng.”** Annotation áp dụng theo **JobKey** trong phạm vi scheduler/cluster quản lý. JobKey khác hoặc các RAMJobStore độc lập vẫn có thể chạy song song.

**“@PersistJobDataAfterExecution biến JobDataMap thành checkpoint transactional cho REST.”** JobDataMap chỉ thuộc phạm vi Quartz JobStore. Remote API có thể đã commit trong khi dữ liệu này chưa kịp cập nhật.

**“requestRecovery(true) bảo đảm exactly-once.”** Recovery có thể gọi lại một công việc đã tạo side effect trước crash. Idempotency và reconciliation là trách nhiệm riêng.

**“Scheduler bị lỗi thì cứ refireImmediately đến khi thành công.”** Retry tức thời không có backoff có thể gây vòng lặp, quá tải downstream và làm chậm các trigger khác.

**“Chỉ cần @Transactional bao quanh Job.execute để rollback HTTP/Kafka.”** Giao dịch database cục bộ không thể rollback một side effect bên ngoài đã commit; cần outbox, idempotency, compensation tùy workflow.

**“Bật JDBC nhưng quên cluster vẫn chạy một lần toàn hệ thống.”** Chia sẻ bảng Quartz cần cấu hình cluster nhất quán, instance ID và DB/schema đúng. Không kết hợp node clustered và nonclustered cùng một tập bảng.

**“Không có misfire nghĩa là không mất dữ liệu.”** Có thể scheduler vẫn chạy đúng lịch nhưng logic xử lý bỏ sót records, hoặc consumer nhận trùng. Quartz không kiểm chứng tính đúng nghiệp vụ.

## 14. Checklist trước khi vận hành production

- Xác nhận **JobKey**, **TriggerKey**, timezone, lịch, misfire instruction và deadline nghiệp vụ của từng job.
- Phân biệt **skip các tick cũ**, **fire một lần ngay** và **bắt buộc xử lý mọi business period**.
- Dùng **@DisallowConcurrentExecution** khi cùng JobKey không được overlap; thiết kế business claim/unique key nếu nhiều worker hoặc ứng dụng ngoài Quartz cùng xử lý.
- Chọn **requestRecovery(true)** khi công việc dang dở cần được thử lại; đồng thời đảm bảo tác động phía ngoài có thể xử lý lặp an toàn.
- Với đa node, kiểm chứng **JDBC JobStore cluster**, schema, instanceId, khả năng recovery và đồng bộ clock.
- Sắp xếp timeout, DB/HTTP pool, threadCount, shutdown grace và backoff để tránh job chặn cạn tài nguyên.
- Dùng idempotency key ổn định, transaction cục bộ, outbox/inbox hoặc cơ chế bù trừ theo mức độ quan trọng của workflow.
- Có bảng backlog/checkpoint, lease/fencing nếu cần, dashboard, cảnh báo và tác vụ đối soát tự động.
- Test misfire, overlap, restart đột ngột, duplicate delivery và remote timeout ở môi trường tích hợp.

## Tài liệu tham khảo

- [Quartz Scheduler — Tutorial: More About Triggers](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-04.html)
- [Quartz Scheduler — Tutorial: CronTrigger](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-06.html)
- [Quartz Scheduler — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/)
- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

**Ghi nhớ:** Misfire quyết định **làm gì khi một trigger trễ**, @DisallowConcurrentExecution quyết định **có cho phép execution cùng JobKey chạy chồng**, còn requestRecovery quyết định **có thử thực thi lại job bị ngắt do scheduler chết**. Quartz giúp điều phối thời điểm; chính dữ liệu nghiệp vụ bền vững, idempotency và cơ chế đối soát mới bảo vệ kết quả tích hợp trước downtime, trùng lặp và lỗi không xác định.
