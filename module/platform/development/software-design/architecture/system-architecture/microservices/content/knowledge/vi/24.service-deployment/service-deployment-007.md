# Quản lý job, tác vụ định kỳ và tránh chạy trùng trong Microservices

## Mục tiêu bài học

Sau bài này, người học có thể phân biệt cơ chế **lập lịch**, **điều phối thực thi** và **kiểm soát tác động nghiệp vụ**; nhận diện nguyên nhân một job chạy nhiều lần khi triển khai nhiều instance; lựa chọn giữa Spring Boot Scheduler, distributed lock, Kubernetes CronJob, Quartz hoặc hệ thống hàng đợi; thiết kế idempotency, lease, retry và xử lý sự cố; đồng thời tổ chức quan sát, phát hành và kiểm thử để job an toàn khi hệ thống mở rộng.

## 1. Job và tác vụ định kỳ trong kiến trúc microservices

**Job** là công việc có thể chạy ngoài vòng đời một HTTP request, thường có thể mất nhiều thời gian, cần lập lịch hoặc xử lý nền. **Tác vụ định kỳ** (scheduled/recurring task) là job được kích hoạt theo khoảng thời gian hoặc một lịch cụ thể.

Ví dụ quen thuộc trong một hệ thống thương mại điện tử:

- Mỗi ngày lúc 02:00 UTC đối soát thanh toán với nhà cung cấp.
- Mỗi 15 phút tổng hợp số liệu giao dịch cho báo cáo.
- Hàng giờ dọn bản ghi tạm đã hết hạn.
- Mỗi đêm tạo hóa đơn theo kỳ, gửi thông báo hoặc tính phí thuê bao.
- Định kỳ quét các sự kiện outbox chưa được chuyển đi.
- Chạy tác vụ bảo trì, backfill hoặc sửa dữ liệu theo lô.

Các công việc này có thể được kích hoạt từ cron, API quản trị, lịch được lưu trong database, message broker hoặc workflow engine. Một job cụ thể có thể được chạy lại sau lỗi, chạy bù sau khi hệ thống ngừng hoạt động, hoặc chạy thủ công để khôi phục dữ liệu.

**Vấn đề cốt lõi:** Trong microservices, một dịch vụ thường có nhiều pod/instance để đáp ứng tải và chịu lỗi. Nếu mỗi instance đều tự chạy cùng một lịch, một lần đến giờ có thể biến thành nhiều lần thực thi. Đồng thời, ngay cả khi chỉ có một instance nhận việc, lỗi mạng và retry vẫn có thể khiến cùng một tác động nghiệp vụ được thực hiện nhiều lần.

~~~text
           02:00 UTC — Job định kỳ đến hạn
                          |
          +---------------+---------------+
          |               |               |
      Order v1 / A    Order v1 / B    Order v1 / C
      @Scheduled      @Scheduled      @Scheduled
          |               |               |
          +---------------+---------------+
                          |
                 Cùng xử lý ngày D
              (có nguy cơ chạy 3 lần)
~~~

Không được đồng nhất ba khái niệm sau:

1. **Một lần kích hoạt lịch (trigger):** hệ thống quyết định lịch đã đến hạn.
2. **Một lần nhận quyền thực thi (claim/lease):** worker giành quyền xử lý công việc hoặc một phân vùng công việc.
3. **Một lần tạo tác động nghiệp vụ (effect):** ghi hóa đơn, trừ tiền, gửi email, chuyển trạng thái hay cập nhật dữ liệu.

Giảm số trigger trùng có ích, nhưng chỉ riêng điều đó không bảo đảm hiệu ứng nghiệp vụ không bị nhân đôi.

## 2. Những nguyên nhân phổ biến làm job chạy trùng

### 2.1 Nhiều instance chạy cùng scheduler

Trong Spring Boot, phương thức đánh dấu bằng @Scheduled được đăng ký trong **từng tiến trình Spring**. Ba pod cùng có bean scheduler có thể cùng gọi phương thức lúc lịch đến hạn. Annotation này tự thân không có distributed lock.

### 2.2 Rolling deployment và chạy chồng phiên bản

Khi deploy, instance phiên bản cũ và mới có thể cùng tồn tại. Nếu cả hai có scheduler đang bật, cùng lịch sẽ được phát ở cả hai nhóm. Việc replica mới Ready không đồng nghĩa replica cũ đã kết thúc các job đang chạy.

### 2.3 Retry do timeout hoặc mất phản hồi

Worker đã gửi yêu cầu đến Payment API, nhà cung cấp đã xử lý thành công nhưng response bị timeout. Worker không biết kết quả và retry, dẫn đến nguy cơ thanh toán lần hai.

### 2.4 Job chưa xong thì kỳ tiếp theo bắt đầu

Một tác vụ chạy 20 phút nhưng được kích hoạt mỗi 15 phút. Với nhiều worker hoặc cơ chế chạy bất đồng bộ, có thể có hai lượt cùng xử lý tập dữ liệu giao nhau.

### 2.5 Scheduler hoạt động theo cơ chế at-least-once

Một số scheduler/controller hoặc queue có thể tạo lại lần chạy để khôi phục lỗi. Ví dụ Kubernetes CronJob không cam kết mỗi lịch chỉ tạo **chính xác một** Job trong mọi sự cố; đôi khi có thể có nhiều Job hoặc không tạo được Job. Việc thiết kế công việc idempotent vẫn cần thiết.

### 2.6 Người vận hành chạy bù hoặc chạy thủ công

Một lịch bị bỏ lỡ do bảo trì và được chạy lại; một nhân viên cũng kích hoạt job bằng API quản trị. Nếu không có business key và cơ chế phối hợp, hai yêu cầu có thể cùng xử lý một kỳ.

## 3. Xác định đúng đơn vị chống trùng: tên job và business key

Chống trùng phải gắn với **định danh nghiệp vụ** của lần chạy, không chỉ tên phương thức hay một timestamp ngẫu nhiên.

Ví dụ job tạo báo cáo ngày:

~~~text
job_name       = daily-settlement
business_key   = 2026-11-11
run_id         = 97c... (một lần cố gắng thực thi)
~~~

**job_name + business_key** biểu diễn một kết quả logic cần tạo, trong khi **run_id** phân biệt từng lần thử xử lý. Cùng business key có thể có nhiều attempt khi retry; kết quả cuối phải tuân theo quy tắc idempotency.

Các ví dụ business key:

| Công việc | Business key phù hợp |
| --- | --- |
| Chốt sổ giao dịch theo ngày | Ngày nghiệp vụ + đơn vị tiền tệ hoặc tenant |
| Tính phí thuê bao hằng tháng | Subscription ID + kỳ thanh toán |
| Gửi thông báo hết hạn | Người nhận + sự kiện nghiệp vụ + loại thông báo |
| Xuất báo cáo bán hàng | Tenant ID + kỳ báo cáo + loại báo cáo |
| Xóa object hết hạn | Object ID + loại hành động |
| Đồng bộ dữ liệu theo lô | Dataset + phạm vi offset/checkpoint |

Business key cần đủ ổn định để một lần chạy lại nhận ra chính công việc cũ. Nếu job được thiết kế để tái tạo một báo cáo theo phiên bản mới, có thể cần đưa phiên bản định nghĩa báo cáo vào key hoặc thiết kế trạng thái rerun riêng, thay vì xóa dấu vết lần trước.

## 4. Những mô hình triển khai phổ biến

| Mô hình | Cách hoạt động | Phù hợp khi | Điều cần lưu ý |
| --- | --- | --- | --- |
| Spring @Scheduled trên một instance | Scheduler chạy bên trong ứng dụng | Bài tập, dịch vụ đơn instance, tác vụ không quan trọng | Scale lên nhiều instance sẽ kích hoạt trùng |
| Spring @Scheduled + distributed lock | Mọi instance có trigger; một instance được nhận lock | Job đơn giản trong ứng dụng nhiều replica | Lease hết hạn, crash, thời gian lock và idempotency |
| Kubernetes CronJob | Control plane tạo Kubernetes Job theo cron | Job độc lập, đóng gói container riêng, vận hành trên K8s | ConcurrencyPolicy không bảo đảm exactly-once |
| Quartz clustered | Các node phối hợp qua job store chung | Lịch phức tạp, dynamic trigger, misfire handling | Cần cấu hình clustering, persistence, recovery đúng |
| Scheduler + queue + worker | Lịch tạo work item; worker tiêu thụ qua queue | Khối lượng lớn, chia việc, retry có kiểm soát | At-least-once, dedup và consumer idempotent |
| Workflow engine | Điều phối nhiều bước, trạng thái và compensation | Quy trình dài, nhiều dịch vụ, cần truy vết | Độ phức tạp vận hành và mô hình trạng thái |

Không có một lựa chọn chung tối ưu cho mọi hệ thống. Với một tác vụ đơn giản, chọn cơ chế ít thành phần nhất vẫn đáp ứng yêu cầu độ tin cậy. Với công việc có thể kéo dài nhiều giờ hoặc cần hàng nghìn worker, nên tách scheduler khỏi thực thi và chia thành nhiều work item.

## 5. Spring Boot @Scheduled: hiểu đúng hành vi

Ví dụ lập lịch đơn giản:

~~~java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}

@Component
public class CleanupScheduler {
    private final CleanupService cleanupService;

    public CleanupScheduler(CleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    public void cleanExpiredRecords() {
        cleanupService.deleteExpiredRecords();
    }
}
~~~

Trong cron của Spring, biểu thức trên gồm **sáu trường** (giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần), kích hoạt mỗi ngày lúc 02:00 UTC. Cron của Linux và cron của Kubernetes thường dùng **năm trường**, vì vậy không được sao chép một biểu thức giữa các scheduler mà không đối chiếu cú pháp.

Với Spring @Scheduled, cần hiểu:

- Mỗi application context có thể đăng ký scheduler của riêng nó; scale từ 1 lên 3 pod không tự biến thành một scheduler duy nhất.
- @Scheduled không phải distributed lock, không ghi nhận durable execution và không tự giải quyết retry.
- Với các dạng fixedDelay, fixedRate và cron, cơ chế lập lịch/độ trễ khác nhau; thay đổi thread pool hoặc chạy bất đồng bộ có thể cho phép các công việc chồng nhau.
- Job dài cần timeout, cơ chế báo tiến độ và quy tắc shutdown; không thể chỉ dựa vào việc JVM đã nhận SIGTERM để giả định xử lý đã hoàn tất.

Có thể vô hiệu hóa job qua cấu hình trên các instance thường, chỉ bật scheduler trên một deployment riêng. Đây là cách giảm rủi ro trùng do số lượng replica, nhưng scheduler đơn instance có thể trở thành điểm ngừng dịch vụ nếu thiếu failover; idempotency vẫn cần được thiết kế.

## 6. Distributed lock: chỉ một worker được nhận quyền tại một thời điểm

Một **distributed lock** cho phép nhiều instance tranh quyền nhưng chỉ một instance nắm khóa trong một khoảng thời gian. Khóa thường được lưu trên hệ thống dùng chung như database hoặc Redis.

Đối với job chạy trong Spring Boot, có thể dùng thư viện ShedLock với JDBC:

~~~java
@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT45M")
public class JobSchedulingConfig {

    @Bean
    public LockProvider lockProvider(DataSource dataSource) {
        return new JdbcTemplateLockProvider(
            JdbcTemplateLockProvider.Configuration.builder()
                .withJdbcTemplate(new JdbcTemplate(dataSource))
                .usingDbTime()
                .build()
        );
    }
}
~~~

~~~java
@Component
public class DailyReconciliationJob {
    private final ReconciliationService service;

    public DailyReconciliationJob(ReconciliationService service) {
        this.service = service;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    @SchedulerLock(
        name = "daily-reconciliation",
        lockAtMostFor = "PT45M",
        lockAtLeastFor = "PT1M"
    )
    public void execute() {
        service.reconcileDuePeriods();
    }
}
~~~

Ví dụ cần dependency ShedLock tương thích với Spring đang dùng, bật cấu hình lock provider và tạo bảng khóa JDBC theo schema được thư viện yêu cầu. Annotation @SchedulerLock không có hiệu lực nếu chưa cấu hình đầy đủ cơ chế thực thi lock trong ứng dụng.

**lockAtMostFor** là hạn cuối để giải phóng lock khi worker crash; thời hạn này cần đủ lớn so với thời gian chạy tối đa hợp lệ hoặc có cách gia hạn lease an toàn. **lockAtLeastFor** có thể hạn chế chạy sát nhau khi có chênh lệch đồng hồ hay job cực ngắn; nó không thay thế idempotency.

Chọn **usingDbTime()** giúp mốc thời gian khóa dựa trên đồng hồ database thay vì đồng hồ riêng từng JVM trong cấu hình JDBC được hỗ trợ. Đồng hồ chuẩn nhất quán làm giảm một nhóm lỗi, nhưng không loại bỏ mọi rủi ro.

### Giới hạn quan trọng của lease lock

Giả sử worker A giành lock 15 phút. Sau 15 phút, A bị treo ở một lời gọi mạng nhưng chưa chết; lock hết hạn và worker B nhận quyền chạy. Nếu A thức dậy, **A và B có thể đồng thời tiếp tục**. Lock dạng lease thường là cơ chế giảm trùng, không phải hàng rào ngăn side effect tuyệt đối.

Các lựa chọn bổ sung:

- Dùng lock token có thứ tự tăng (**fencing token**) và yêu cầu nơi ghi dữ liệu từ chối token cũ.
- Thực hiện thay đổi trạng thái bằng SQL có điều kiện hoặc ràng buộc UNIQUE trên business key.
- Dùng idempotency key khi gọi API bên ngoài hỗ trợ tính năng này.
- Duy trì heartbeat và kéo dài lease khi kiến trúc/lock provider hỗ trợ, đồng thời có timeout để chặn job treo vô hạn.
- Thiết kế task thành những đơn vị công việc nhỏ, để nếu worker chết thì có thể resume.

Một lock theo tên job là quá thô nếu muốn xử lý nhiều tenant hoặc ngày độc lập song song. Có thể khóa theo **job_name + business_key** hoặc chia partition, với điều kiện mỗi khóa vẫn bảo vệ đúng tài nguyên có thể xung đột.

## 7. Kubernetes CronJob: điều phối bằng tài nguyên riêng

Trên Kubernetes, CronJob là lựa chọn tự nhiên khi một tác vụ có thể chạy như một container độc lập, không cần scheduler nằm trong mỗi replica của service.

Ví dụ cấu hình:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
spec:
  schedule: "0 2 * * *"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 3
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: reconciliation
              image: registry.example.com/billing-worker:1.0.0
              args: ["--job=daily-reconciliation"]
              resources:
                requests:
                  cpu: "100m"
                  memory: "256Mi"
                limits:
                  cpu: "1000m"
                  memory: "1Gi"
~~~

Ý nghĩa từng trường:

- **schedule:** cron 5 trường trong Kubernetes; tác vụ chạy 02:00 UTC.
- **timeZone:** chỉ định múi giờ cho lịch; cần phiên bản Kubernetes hỗ trợ trường này.
- **concurrencyPolicy: Forbid:** không khởi tạo lượt mới nếu controller thấy một Job trước của **chính CronJob ấy** còn hoạt động. Lượt bị bỏ lỡ có thể không được chạy đúng hạn.
- **Replace:** có thể thay thế Job đang chạy, dễ cắt ngang tác vụ chưa hoàn tất; không thích hợp với nghiệp vụ không an toàn khi bị ngắt.
- **Allow:** cho phép các lần chạy chồng nhau; chỉ nên dùng khi job độc lập hoặc đã có cơ chế chống xung đột.
- **startingDeadlineSeconds:** khoảng cho phép bắt đầu sau lịch khi controller chậm hoặc gián đoạn; không nên hiểu là “retry business logic”.
- **backoffLimit:** giới hạn retry ở cấp Job khi Pod thất bại; retry nghĩa là cùng tác vụ có thể xử lý lại.
- **activeDeadlineSeconds:** giới hạn tổng thời gian Job hoạt động; hết hạn có thể khiến tiến trình bị chấm dứt.
- **ttlSecondsAfterFinished:** dọn Job/Pod đã kết thúc theo TTL, không phải thời hạn lưu dữ liệu nghiệp vụ.

**Cần hiểu đúng về Forbid:** đây là quy tắc concurrency giữa những Job do **cùng một CronJob** quản lý. Nó không chống việc một CronJob khác, cron ngoài Kubernetes hoặc thao tác thủ công cùng kích hoạt một nghiệp vụ. Kubernetes CronJob cũng không hứa chính xác một lần tạo Job cho mỗi mốc lịch. Khi side effect có giá trị cao, vẫn phải dùng business key và idempotency ở tầng xử lý.

Nếu job chạy quá giờ quy định, có thể dẫn đến lượt bị skip; hãy quyết định chính sách **catch-up** ngay từ thiết kế thay vì giả định lần chạy tiếp theo sẽ xử lý mọi dữ liệu còn thiếu.

## 8. Tách lập lịch và thực thi qua queue

Khi cần xử lý hàng triệu bản ghi, một scheduler duy nhất không nên tự ôm hết toàn bộ dữ liệu. Mô hình phổ biến:

~~~text
Scheduler
   |
   | tạo work item: (jobName, businessKey, partition)
   v
Durable job store / outbox
   |
   v
Message broker / queue
   |
   +------------+-------------+
   |            |             |
 Worker A     Worker B      Worker C
   |            |             |
   +------------+-------------+
                |
        DB / API nghiệp vụ
~~~

Scheduler chỉ quyết định **kỳ nào cần xử lý** và đăng ký công việc bền vững. Các worker nhận các partition, ghi checkpoint, retry những phần lỗi và đánh dấu thành công. Queue tăng khả năng mở rộng ngang nhưng nhiều broker có delivery at-least-once: nếu worker xử lý xong mà chưa ack, message có thể được gửi lại.

Thiết kế nên bao gồm:

- Một work item có business key ổn định và partition ID rõ ràng.
- Trạng thái bền vững của từng partition, tránh phải chạy lại toàn bộ batch.
- Consumer idempotent, ghi nhận event/message ID đã xử lý khi thích hợp.
- Giới hạn concurrency, tốc độ gọi API, số request đang bay và backpressure.
- Retry có exponential backoff + jitter; dead-letter hoặc nơi chứa lỗi không thể retry.
- Cơ chế xử lý job bị mắc kẹt, checkpoint và phục hồi sau crash.
- Dấu vết tổng hợp để biết “kỳ D đã hoàn thành” dù có nhiều worker.

Nếu đăng ký job trong database rồi phát message, cần xét **dual-write**: database commit thành công nhưng publish thất bại. Transactional outbox hoặc một cơ chế dispatch/reconciliation đáng tin cậy giúp tránh mất việc trong khoảng lỗi này.

## 9. Idempotency: ngăn hiệu ứng lặp dù trigger bị lặp

**Idempotent** nghĩa là xử lý cùng một yêu cầu logic nhiều lần vẫn tạo ra trạng thái mong muốn như xử lý một lần. Đây là biện pháp cốt lõi vì trong hệ phân tán không thể chỉ dựa vào việc “job sẽ không bao giờ chạy lại”.

Ví dụ: Job tính phí thuê bao hằng tháng cần tránh tạo hai hóa đơn cho cùng subscription và kỳ.

~~~sql
CREATE TABLE invoice (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subscription_id BIGINT NOT NULL,
    period_start DATE NOT NULL,
    amount_cents BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_invoice_subscription_period
        UNIQUE (subscription_id, period_start)
);
~~~

Khi hai worker cùng tạo hóa đơn:

~~~sql
INSERT INTO invoice (
    subscription_id, period_start, amount_cents
)
VALUES (
    :subscription_id, :period_start, :amount_cents
)
ON CONFLICT (subscription_id, period_start) DO NOTHING;
~~~

Ràng buộc UNIQUE bảo vệ database **ngay cả khi cả hai worker vượt qua kiểm tra SELECT trước khi INSERT**. Cần chọn cách xử lý bản ghi đã tồn tại: đọc và trả lại kết quả trước đó, đối chiếu dữ liệu có cùng nghĩa, hoặc báo lỗi nếu cùng key nhưng payload khác nhau. Không lặng lẽ bỏ qua giá trị khác biệt quan trọng.

Với khoản thanh toán qua API bên ngoài, UNIQUE của bảng nội bộ không đủ để ngăn bên ngoài nhận hai lệnh. Cần dùng **idempotency key ở API nhà cung cấp**, chẳng hạn định danh ổn định từ subscription và kỳ thanh toán. Nếu response timeout, tra cứu kết quả theo key trước khi phát một lệnh mới.

**Idempotency key phải ổn định qua retry.** Không tạo UUID mới cho từng lần thử của cùng một khoản thanh toán, vì như vậy hệ thống bên ngoài có thể xem là hai nghiệp vụ khác nhau.

### Phân biệt ba lớp chống trùng

| Cơ chế | Bảo vệ | Không bảo đảm |
| --- | --- | --- |
| Distributed lock | Giảm việc cùng lúc có hai worker đang cố xử lý | Ngăn tác động lặp sau crash/lease expiry |
| Job run dedup theo business key | Không tạo nhiều job logic cho cùng kỳ | Tác động ngoài DB chỉ diễn ra một lần |
| Idempotent business operation | Cùng yêu cầu logic không tạo hiệu ứng nhân đôi | Không bảo đảm trigger được phát đúng giờ |

Thiết kế đáng tin kết hợp nhiều lớp thay vì xem chúng là những lựa chọn loại trừ nhau.

## 10. Bảng job_run để theo dõi tiến độ và claim công việc

Một job quan trọng cần có trạng thái bền vững, thay vì chỉ in log “started” rồi “finished”:

~~~sql
CREATE TABLE job_run (
    job_name VARCHAR(100) NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    owner_id VARCHAR(100),
    lease_until TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_name, business_key)
);
~~~

Ví dụ trạng thái:

~~~text
PENDING -> RUNNING -> SUCCEEDED
             |
             +----> RETRY -> RUNNING -> SUCCEEDED
             |
             +----> FAILED (cần can thiệp hoặc chính sách riêng)
~~~

Đăng ký một công việc logic theo kiểu có thể chạy lại:

~~~sql
INSERT INTO job_run (job_name, business_key, status)
VALUES (:job_name, :business_key, 'PENDING')
ON CONFLICT (job_name, business_key) DO NOTHING;
~~~

**INSERT trên chỉ tạo hồ sơ công việc**, chưa giành quyền thực thi. Các worker phải claim một cách atomic, ví dụ trong PostgreSQL:

~~~sql
UPDATE job_run
SET status = 'RUNNING',
    owner_id = :owner_id,
    lease_until = now() + INTERVAL '15 minutes',
    attempt_count = attempt_count + 1,
    started_at = now(),
    updated_at = now()
WHERE job_name = :job_name
  AND business_key = :business_key
  AND (
    status IN ('PENDING', 'RETRY')
    OR (status = 'RUNNING' AND lease_until < now())
  )
RETURNING attempt_count;
~~~

Nếu câu lệnh không trả hàng nào, worker không được nhận job ở lượt đó. Nếu trả một hàng, worker đã claim được trạng thái tại database. Ví dụ dùng thời gian DB để giảm sai lệch clock; cần thiết kế thêm heartbeat, timeout và recovery phù hợp.

Khi hoàn thành, chỉ worker hiện sở hữu lượt chạy mới được đánh dấu SUCCEEDED, dùng điều kiện owner_id/attempt token. Tuy nhiên, **kiểm tra owner ở bảng trạng thái chưa chặn một worker cũ tiếp tục gửi side effect** sau khi lease hết hạn. Với thao tác không idempotent, cần cơ chế fencing token tại nơi ghi hoặc idempotency ở chính nghiệp vụ.

Bảng job_run không nên là nơi lưu tất cả payload lớn, log dài hoặc thông tin nhạy cảm. Lưu đủ key, trạng thái, timestamp, attempt và tham chiếu đến artifact để phục vụ điều hành.

## 11. Lease, heartbeat và fencing token

Hình dung hai worker và một lease 10 phút:

~~~text
02:00  A claim job, token = 14, lease đến 02:10
02:03  A mất kết nối tạm thời nhưng tiến trình chưa chết
02:10  Lease hết hạn
02:11  B claim lại, token = 15
02:12  A hồi phục và tiếp tục ghi
~~~

Nếu cả A và B cùng ghi dữ liệu không có kiểm soát, job vẫn có thể chạy trùng dù lock đã được cấp đúng theo thời gian. Đây là lý do **lease không bằng quyền độc quyền vĩnh viễn**.

Fencing token là số thế hệ quyền sở hữu tăng đơn điệu mỗi lần cấp lease. Nơi lưu dữ liệu hoặc hệ thống đích phải từ chối thao tác dùng token nhỏ hơn token mới nhất đã chấp nhận. Chỉ đặt token trong log hoặc trong bảng lock mà nơi ghi không kiểm tra thì không có tác dụng bảo vệ side effect.

Một số hệ thống bên ngoài không hỗ trợ fencing; khi đó cần chiến lược khác: thao tác idempotent, unique constraint, cập nhật có điều kiện, API idempotency key hoặc reconciliation. Với job chạy lâu, heartbeat gia hạn lease và timeout hợp lý vẫn hữu ích nhưng không thay thế các biện pháp ở điểm ghi.

## 12. Retry, timeout và xử lý sự cố

Một job có thể thất bại do lỗi tạm thời (mạng, deadlock, rate limit), lỗi nghiệp vụ (dữ liệu không hợp lệ), lỗi cấu hình, hoặc lỗi không thể xác định kết quả (response timeout sau khi bên ngoài đã commit).

### Retry có chủ đích

- **Retry được:** lỗi mạng tạm thời, HTTP 429/503, deadlock hoặc tài nguyên bận nếu thao tác có thể chạy lại an toàn.
- **Không retry vô hạn:** payload sai schema, quyền truy cập bị từ chối cố định, dữ liệu nghiệp vụ không hợp lệ.
- **Exponential backoff + jitter:** giảm việc hàng loạt worker cùng đập vào dependency vừa hồi phục.
- **Giới hạn lần thử:** sau ngưỡng, chuyển trạng thái cần can thiệp, dead-letter hoặc hàng chờ xử lý thủ công.
- **Phân biệt timeout với thất bại chắc chắn:** khi side effect có thể đã thành công, tra cứu hoặc đối soát trước khi gửi lại.

### Crash ở từng thời điểm khác nhau

| Điểm crash | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Trước claim | Chưa nhận việc | Worker khác nhận khi đến lượt |
| Sau claim, trước side effect | Job bị giữ RUNNING | Lease hết hạn và requeue/claim lại |
| Sau DB commit, trước ghi SUCCEEDED | Chạy lại cùng tác động | Unique constraint và thao tác idempotent |
| Sau gọi API ngoài thành công, trước ack | Gọi lại API | Idempotency key/tra cứu giao dịch |
| Khi đang backfill nửa chừng | Dữ liệu một phần | Checkpoint, batch idempotent, resume |
| Khi shutdown giữa job | Xử lý dang dở | Graceful shutdown, lease/timeout và recovery |

Không giả định một transaction trong service tự động rollback được side effect ở hệ thống ngoài hoặc database của microservice khác.

## 13. Quản lý lịch, múi giờ và những lượt bị lỡ

**Cron expression** biểu diễn thời điểm theo múi giờ. **fixed rate** biểu diễn nhịp kích hoạt theo khoảng thời gian; **fixed delay** thường tính khoảng nghỉ sau khi một lượt hoàn tất. Chọn loại lịch theo ngữ nghĩa nghiệp vụ.

Những vấn đề cần quyết định trước:

1. **Múi giờ:** UTC thường thuận tiện khi vận hành nhiều khu vực. Nếu tính tiền theo ngày địa phương, phải dùng vùng giờ kinh doanh được chỉ định rõ ràng.
2. **Daylight Saving Time (DST):** tại một số múi giờ, giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Xác định trước xử lý lịch bị skip hoặc lặp.
3. **Misfire / missed schedule:** khi cụm dịch vụ down ở thời điểm kích hoạt, sẽ bỏ qua, chạy bù một lượt hay xử lý toàn bộ các kỳ chưa hoàn tất?
4. **Chạy lâu hơn chu kỳ:** skip, đợi, gộp việc, hay chạy song song? Quyết định theo nghiệp vụ.
5. **Manual rerun:** cho phép chạy lại kỳ cũ theo cùng business key với kiểm soát quyền, audit và nguyên tắc tái tạo kết quả.

Với báo cáo ngày, tránh phụ thuộc hoàn toàn vào biểu thức “hôm nay trừ một ngày” tại thời điểm worker được khởi động. Nếu lịch 02:00 bị trễ sang hôm sau, công thức đó có thể xử lý sai kỳ.

Cách an toàn hơn là scheduler đăng ký **business_date cụ thể** và lưu công việc vào job store; worker đọc business_date từ bản ghi thay vì suy đoán từ giờ bắt đầu. Khi khôi phục, scheduler quét các kỳ chưa SUCCEEDED và tạo work item tương ứng, bảo vệ bằng khóa duy nhất.

### Ví dụ timeline chạy bù

~~~text
Ngày D       02:00  Job tổng hợp kỳ D-1 lẽ ra chạy
              |
              +--- Scheduler ngừng hoạt động
Ngày D+1     10:00  Scheduler hồi phục
              |
              +--- Truy vấn job_run / kỳ đã hoàn tất
              +--- Đăng ký các kỳ còn thiếu, đúng business_date
              +--- Worker xử lý có giới hạn tốc độ
~~~

Chính sách catch-up phải tính đến tải đột biến và tính còn hiệu lực của công việc: thông báo nhắc hạn từ tháng trước có thể nên bỏ qua, nhưng chốt sổ thanh toán thường cần được xử lý đầy đủ.

## 14. Deploy, scale và shutdown an toàn

Một cơ chế job đúng trong môi trường local có thể sai khi triển khai production nếu không xét vòng đời instance.

**Rolling update:** trong thời gian nhiều phiên bản cùng chạy, cả hai có thể lên lịch. Phải bảo đảm lock/job store và các business key tương thích giữa phiên bản cũ và mới.

**Scale up và autoscaling:** số replica ứng dụng tăng không được làm tăng số hóa đơn tạo ra cho một kỳ. Tách worker deployment với API deployment nếu nhu cầu resource/scale khác biệt.

**Graceful shutdown:** khi nhận tín hiệu dừng, instance nên ngừng nhận job mới, cho lượt đang chạy một khoảng thời gian hợp lý để hoàn tất hoặc ghi checkpoint, rồi giải phóng/để hết hạn lease theo chính sách. Termination grace period không được coi là bảo đảm sẽ hoàn thành mọi công việc.

**Resource isolation:** job nặng có thể chiếm CPU, thread pool, kết nối database và làm chậm API người dùng. Cân nhắc pod/worker riêng, concurrency limit, pool riêng, rate limit và lịch chạy ngoài cao điểm.

**Versioned job payload:** khi một work item tồn đọng được xử lý bởi code mới, schema payload và quy tắc nghiệp vụ phải tương thích. Ghi version khi cần và có đường chuyển đổi hoặc xử lý lỗi rõ ràng.

**Readiness/health:** một pod Ready chỉ nói nó có thể nhận việc theo cấu hình, không chứng minh job đã hoàn thành. Theo dõi trạng thái scheduler, tuổi của công việc còn chờ và lượt thành công cuối cùng bằng metric riêng.

## 15. Khả năng quan sát và vận hành

Mỗi job quan trọng nên có câu trả lời cho các câu hỏi: kỳ nào phải chạy, kỳ nào đã chạy, kỳ nào thất bại, ai đang sở hữu, retry bao nhiêu lần, hiệu ứng nghiệp vụ đã ghi nhận chưa và có thể phục hồi bằng cách nào?

Các trường log hữu ích:

~~~text
job_name=daily-reconciliation
business_key=2026-11-11
run_id=1cb9...
attempt=2
owner_id=worker-3
state=RUNNING
trace_id=...
started_at=...
~~~

Giám sát bằng metrics:

- **jobs_started_total / jobs_completed_total / jobs_failed_total:** phân biệt theo tên job và loại kết quả.
- **job_duration_seconds:** histogram thời gian xử lý.
- **job_queue_lag_seconds:** độ trễ từ khi đến hạn đến khi worker bắt đầu.
- **job_last_success_timestamp_seconds:** thời điểm một job quan trọng gần nhất thành công.
- **job_retry_total:** số lần retry và phân loại lỗi.
- **job_stuck_count / job_lease_expired_total:** phát hiện work item bị mắc kẹt.
- **job_duplicate_prevented_total:** số yêu cầu trùng bị ràng buộc/idempotency ngăn.
- **job_pending_count:** backlog chưa xử lý và sức khỏe catch-up.

Không đưa business_key, user ID hoặc run_id có giá trị gần như vô hạn vào **label metrics** vì dễ gây cardinality rất cao. Để chúng trong structured logs/traces hoặc bảng job_run. Alert nên dựa vào yêu cầu nghiệp vụ, ví dụ “kỳ chốt sổ ngày hôm qua chưa SUCCEEDED trước 05:00 UTC”, hơn là chỉ “không thấy log started”.

Đối với job có side effect quan trọng, cần audit về người kích hoạt thủ công, mục đích rerun, thời gian thực thi và kết quả đối soát. Token, thông tin thanh toán và dữ liệu cá nhân không nên xuất hiện nguyên văn trong logs.

## 16. Kiểm thử các tình huống trùng lặp và khôi phục

Đừng chỉ kiểm thử job chạy xanh một lần trên máy cá nhân. Những ca sau trực tiếp kiểm tra tính an toàn khi triển khai microservices:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Hai instance cùng đến giờ | Chỉ một nhận quyền cho cùng khóa logic hoặc cả hai an toàn nhờ idempotency |
| Hai worker claim cùng business key | Atomic claim trả quyền cho tối đa một worker tại thời điểm hợp lệ |
| Worker crash trước side effect | Job có thể được phục hồi sau timeout/lease |
| Worker crash sau commit, trước ack | Chạy lại không tạo thêm hóa đơn/thanh toán |
| Lease hết hạn khi worker A chưa chết | Worker cũ không thể gây hiệu ứng sai khi B tiếp quản |
| Retry khi nhà cung cấp đã xử lý nhưng response timeout | Idempotency key không đổi và có reconciliation |
| Lịch bị bỏ lỡ một ngày | Catch-up đăng ký đúng kỳ, không xử lý nhầm “ngày hôm qua” |
| Job kéo dài qua lịch kế tiếp | Concurrency/catch-up đúng chính sách |
| Rolling deployment | Old/new scheduler cùng tồn tại không làm nhân đôi side effect |
| Chạy lại thủ công kỳ đã SUCCEEDED | Trả trạng thái đã hoàn thành hoặc chạy theo quy trình rerun có kiểm soát |

Ở cấp integration test, nên dùng database thật qua môi trường thử nghiệm tương thích để kiểm tra atomic claim, ràng buộc UNIQUE và transaction. Có thể đồng thời gửi hai tác vụ với cùng business key bằng barrier đồng bộ, xác minh kết quả cuối chỉ có một tác động. Mô phỏng crash tại các điểm đặc biệt quan trọng: sau ghi database, trước ack; sau gọi API, trước nhận response; và ngay trước thời điểm lease hết hạn.

Không biến tất cả các biến thể thành E2E toàn hệ thống. Quy tắc idempotency và claim nên được chứng minh phần lớn ở tầng component/integration; một số luồng xuyên dịch vụ quan trọng được kiểm thử E2E có chọn lọc.

## 17. Ví dụ thiết kế hoàn chỉnh: đối soát thanh toán mỗi ngày

Giả sử Billing Service chạy ba instance, cần đối soát giao dịch cho mỗi **ngày nghiệp vụ UTC** và không tạo lệnh điều chỉnh hai lần.

### Phân chia trách nhiệm

1. **Scheduler** kích hoạt lúc 02:00 và xác định ngày nghiệp vụ cần xử lý. Nó ghi hồ sơ (daily-reconciliation, business_date) vào job_run có khóa duy nhất.
2. **Dispatcher/worker** claim hồ sơ chưa xử lý, có lease và attempt ID. Trong hệ nhỏ có thể dùng một phương thức @Scheduled + lock; trong hệ lớn có thể đưa work item lên queue.
3. **Processor** truy xuất dữ liệu theo ngày đã ghi trong job_run, chia trang và ghi checkpoint. Mọi điều chỉnh sử dụng khóa nghiệp vụ duy nhất.
4. **Payment provider adapter** gắn idempotency key vào yêu cầu có side effect; khi timeout, tra cứu hoặc đối soát thay vì gửi tác động mới không kiểm soát.
5. **Completion** chỉ chuyển SUCCEEDED khi các partition đã đạt kết quả kỳ vọng, có đầy đủ dữ liệu đối soát và không còn lỗi cần can thiệp.
6. **Observer** theo dõi pending/failed, tuổi job, duplicate prevention và last success; có API quản trị để chạy bù với quyền hạn/audit.

### Ví dụ một khóa idempotent cho điều chỉnh

~~~text
job_name:           daily-reconciliation
business_key:       2026-11-11
payment_id:         pay_123
adjustment_type:    REFUND_CORRECTION
adjustment_key:     daily-reconciliation/2026-11-11/pay_123/REFUND_CORRECTION
~~~

Cùng điều chỉnh được retry bao nhiêu lần cũng dùng **adjustment_key** đó. Cơ sở dữ liệu có unique constraint trên adjustment_key; khi gửi nhà cung cấp cũng dùng idempotency key tương ứng nếu provider hỗ trợ. Nếu cần điều chỉnh lần thứ hai do quyết định nghiệp vụ mới, phải tạo một định danh nghiệp vụ mới có kiểm toán, không lén đổi UUID khi retry.

### Hành vi khi sự cố

- Scheduler down ở 02:00: lúc hồi phục, tìm business_date chưa SUCCEEDED và đăng ký chạy bù.
- Hai instance cùng đăng ký: khóa duy nhất trong job_run loại trùng.
- Worker chết giữa kỳ: lease hết hạn; worker khác tiếp tục từ checkpoint.
- Worker retry payment adjustment: unique key và idempotency của provider chặn trùng hiệu ứng.
- Đối soát không khớp: job chuyển FAILED/NEEDS_REVIEW, giữ bằng chứng; không tự đánh dấu SUCCEEDED chỉ vì đã chạy hết vòng lặp.
- Người vận hành chạy lại: dùng cùng business key, ghi nhận lý do, thực hiện đúng chính sách cho SUCCEEDED và lỗi đã xử lý.

## 18. Sai lầm thường gặp

**“Chỉ cần @Scheduled là đủ.”** Annotation lập lịch theo từng instance, không cung cấp cơ chế phối hợp phân tán.

**“Forbid trong Kubernetes đảm bảo chạy đúng một lần.”** Forbid chỉ điều chỉnh chồng lặp ở phạm vi CronJob, không cung cấp exactly-once cho hiệu ứng nghiệp vụ.

**“Distributed lock là xong.”** Lease có thể hết hạn trong khi worker cũ còn hoạt động. Cần kiểm soát ở nơi ghi hoặc thao tác idempotent.

**“SELECT kiểm tra trước khi INSERT sẽ tránh trùng.”** Hai worker có thể cùng đọc “chưa tồn tại” rồi đều INSERT. Dùng ràng buộc UNIQUE và thao tác DB atomic.

**“Retry với request ID mới để chắc chắn đi tiếp.”** Với thanh toán hoặc gửi thông báo, đổi key mỗi retry có thể biến cùng một nghiệp vụ thành nhiều tác động.

**“Job chạy lúc 02:00 nên cứ xử lý yesterday.”** Nếu lịch bị delay hoặc catch-up, ngày tính theo lúc worker chạy có thể không phải kỳ được lên lịch.

**“Pod dừng thì job tự rollback.”** Side effect đã commit ở database khác hoặc hệ thống bên ngoài không tự quay lại.

**“Giữ log started/finished là đủ.”** Cần business key, trạng thái bền vững, attempt, owner, timestamp và công cụ khôi phục.

**“Tăng TTL lock thật lớn để tránh chạy hai lần.”** TTL quá dài làm giảm khả năng phục hồi sau crash; TTL quá ngắn gây chạy chồng. Cần tính thời gian thực thi, heartbeat và tính an toàn nghiệp vụ.

**“Một lock toàn cục cho tất cả tenant.”** Khóa quá rộng làm giảm throughput; cần chia khóa theo đơn vị xung đột thực sự.

## 19. Checklist đưa job lên môi trường production

- [ ] Đã xác định đơn vị nghiệp vụ duy nhất và business key ổn định qua retry.
- [ ] Rõ trách nhiệm: ai tạo lịch, ai claim, ai thực thi, ai xác nhận hoàn thành.
- [ ] Nhiều instance hoặc rolling deployment không làm nhân đôi hiệu ứng nghiệp vụ.
- [ ] Có unique constraint hoặc idempotency tại chính nơi ghi dữ liệu quan trọng.
- [ ] Lease/heartbeat/fencing hoặc cơ chế thay thế đã được thiết kế cho trường hợp worker cũ còn sống.
- [ ] Job có timeout, giới hạn retry, backoff và lối xử lý lỗi không thể retry.
- [ ] Có chính sách catch-up, overlap, timezone, DST và rerun thủ công.
- [ ] Job chia batch và checkpoint nếu khối lượng lớn hoặc thời gian chạy dài.
- [ ] Resource và concurrency không làm suy giảm dịch vụ HTTP quan trọng.
- [ ] Có trạng thái durable, logs/traces/metrics, alert trễ hạn và quy trình recovery.
- [ ] Đã kiểm thử crash sau commit, retry sau timeout và hai worker chạy đồng thời.
- [ ] Có quy trình vận hành khi một kỳ bị lỗi hoặc tác động bên ngoài ở trạng thái chưa rõ kết quả.

## 20. Bài tập thực hành

Thiết kế job **tạo hóa đơn thuê bao hằng tháng** cho hệ thống gồm Subscription Service, Billing Service và Payment Provider. Billing Service có bốn replica chạy trên Kubernetes; nhà cung cấp thanh toán có thể timeout sau khi đã nhận lệnh.

Hãy xác định: (1) business key cho từng hóa đơn; (2) bảng trạng thái job_run và ràng buộc UNIQUE tương ứng; (3) chọn Spring @Scheduled + lock hay CronJob + queue; (4) cách xử lý hai worker cùng nhận một kỳ; (5) idempotency key truyền sang nhà cung cấp; (6) quy trình retry nếu không rõ thanh toán đã thành công; (7) cách catch-up khi hệ thống down ba ngày; và (8) metrics để phân biệt job trễ hạn, thất bại hay đã hoàn thành.

Một thiết kế tốt phải giải thích được cả tình huống worker chết **sau khi tạo hóa đơn nhưng trước khi ghi SUCCEEDED**, lẫn tình huống lease đã hết hạn nhưng worker cũ vẫn tiếp tục. Đó là hai phép thử quan trọng để đánh giá hệ thống có thực sự chống trùng hiệu ứng nghiệp vụ hay chưa.

## Kết luận

Quản lý job định kỳ trong microservices không dừng ở việc đặt cron đúng giờ. Hệ thống cần phối hợp nhiều instance, xác định từng công việc bằng business key, duy trì trạng thái bền vững, phục hồi sau crash và bảo vệ hiệu ứng nghiệp vụ khi retry hoặc lease hết hạn. Spring @Scheduled, ShedLock, Kubernetes CronJob, Quartz và message queue hỗ trợ các phần khác nhau của bài toán; **idempotency ở nơi tạo tác động** là nền tảng giúp một công việc có thể được thực thi lại an toàn trong môi trường phân tán.
