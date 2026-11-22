# Duplicate launch protection trong Spring Batch

Trong hệ thống batch, cùng một công việc có thể được yêu cầu nhiều lần từ scheduler, REST API, thao tác vận hành, message broker hoặc cơ chế retry khi mạng bị timeout. Nếu những yêu cầu này tạo ra các lượt xử lý độc lập, job có thể tính tiền hai lần, ghi trùng kết quả, gửi nhiều thông báo hoặc tranh chấp cùng một file đầu ra.

**Duplicate launch protection** là cách ngăn các yêu cầu khởi chạy trùng làm phát sinh quá trình xử lý ngoài ý muốn. Với Spring Batch, cơ chế cốt lõi dựa vào danh tính `JobInstance` được xác định bằng **tên job và identifying JobParameters**, kết hợp `JobRepository` để quản lý `JobExecution`. Điều cần hiểu là chống khởi chạy trùng, restart sau lỗi và tính idempotent của đầu ra có liên quan nhưng có phạm vi khác nhau.

Bài học thuộc chủ đề **Spring Batch Core Processing → Execution control**, tập trung vào lựa chọn key nghiệp vụ, hành vi khi launch đồng thời, bảo vệ trên nhiều node, khởi chạy từ scheduler/API, phục hồi sau lỗi và kiểm chứng các tình huống cạnh tranh. Ví dụ dùng API Spring Batch 5.x trở lên và Java 17+.

## 1. Duplicate launch xuất hiện khi nào?

Giả sử job `dailySettlementJob` chốt sổ giao dịch cho ngày nghiệp vụ `2026-11-15`. Một scheduler được bật ở hai pod; đồng thời client gửi lại request do không nhận được phản hồi của lần đầu.

~~~text
01:00:00.000  Pod A: dailySettlementJob(businessDate=2026-11-15)
01:00:00.003  Pod B: dailySettlementJob(businessDate=2026-11-15)
01:00:00.020  API:   dailySettlementJob(businessDate=2026-11-15)
~~~

Ba yêu cầu trên mô tả **cùng một đơn vị công việc nghiệp vụ**. Nếu mọi lần launch đều sinh tham số định danh ngẫu nhiên, Spring Batch có thể coi chúng là những công việc khác nhau và cho chạy đồng thời. Lỗi này thường không nằm ở câu lệnh ghi dữ liệu mà bắt đầu từ việc **định danh sai lần chạy**.

| Nguồn yêu cầu trùng | Nguyên nhân thường gặp | Hành vi mong đợi |
|---|---|---|
| Scheduler trên nhiều instance ứng dụng | Mỗi node đều có `@Scheduled`. | Một kỳ nghiệp vụ không có hai execution cùng instance chạy song song. |
| HTTP client retry | Server nhận request nhưng client không thấy response. | Request retry cùng key được nhận diện là công việc đã tồn tại. |
| Người vận hành nhấn nút nhiều lần | UI gửi nhiều request liên tiếp. | Báo đang chạy hoặc đã hoàn thành; không tạo run trùng. |
| Broker giao lại message | ACK bị lỗi hoặc message được redeliver. | Message cùng nghiệp vụ không tạo hiệu ứng lặp. |
| Job bị lỗi và người vận hành chạy lại | Cần tiếp tục một execution thất bại. | Cho phép **restart hợp lệ** theo chính sách. |
| Ứng dụng vừa khởi động | Auto-run của Spring Boot và scheduler cùng launch. | Kiểm soát một nguồn kích hoạt hoặc thống nhất business key. |

Điều quan trọng không phải là cấm mọi lời gọi `JobLauncher.run(...)` lặp lại, vì một số lời gọi có thể là **restart** được mong muốn. Phải xác định rõ cái gì là công việc trùng, cái gì là công việc mới và cái gì là thử lại một công việc đã thất bại.

## 2. Job, JobInstance và JobExecution khác nhau thế nào?

Spring Batch tách các khái niệm:

- **`Job`**: định nghĩa quy trình batch, ví dụ `dailySettlementJob`.
- **`JobParameters`**: tham số của yêu cầu chạy, như ngày nghiệp vụ, cửa hàng hoặc request ID.
- **`JobInstance`**: công việc logic duy nhất, được xác định bởi `jobName` và tập **identifying parameters**.
- **`JobExecution`**: một lần cố gắng thực thi một `JobInstance`, có trạng thái và metadata riêng.
- **`JobRepository`**: lưu định danh, trạng thái, lịch sử execution và checkpoint liên quan.

Ví dụ:

~~~text
Job: dailySettlementJob
Identifying parameters: businessDate=2026-11-15, storeId=ACME
                         |
                         v
                   JobInstance A
                         |
             +-----------+-----------+
             |                       |
       JobExecution #101       JobExecution #102
       status=FAILED           status=COMPLETED
                               (restart của A)
~~~

Trong sơ đồ, execution #102 là **lần chạy tiếp của cùng JobInstance A** sau lỗi, không phải job instance mới. Một JobInstance đã thành công và ở trạng thái `COMPLETED` thông thường không được khởi chạy lại bằng chính định danh đó.

### Identifying và non-identifying JobParameters

Spring Batch cho phép đánh dấu tham số:

**Identifying = true:** tham gia xác định một `JobInstance`.

**Identifying = false:** lưu trong parameters để quan sát hoặc sử dụng lúc chạy nhưng **không tạo JobInstance mới** khi giá trị thay đổi.

| Job | Identifying parameters | Non-identifying | Danh tính |
|---|---|---|---|
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-1` | Instance A |
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-2` | **Vẫn instance A** |
| `dailySettlementJob` | `businessDate=2026-11-16`, `storeId=ACME` | `requestId=req-3` | Instance B |
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=OTHER` | `requestId=req-4` | Instance C |
| `anotherJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-5` | Instance khác vì tên Job khác |

Ví dụ Java:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("storeId", "ACME", true)
    .addString("requestId", "req-57", false)
    .toJobParameters();
~~~

Từ góc độ bảo vệ trùng, **chọn identifying parameters đúng là quyết định quan trọng nhất**. Hai lời gọi xử lý cùng ngày/cửa hàng phải tạo cùng tên job và cùng bộ identifying parameters, kể cả khi request ID khác.

## 3. JobRepository thực thi bảo vệ như thế nào?

Khi nhận `JobLauncher.run(job, parameters)`, Spring Batch dùng `JobRepository` để tra cứu hoặc tạo `JobInstance` và tạo `JobExecution` phù hợp. Với JDBC JobRepository có schema chuẩn, bảng `BATCH_JOB_INSTANCE` lưu tên job và `JOB_KEY` (được xác định từ identifying parameters) với ràng buộc uniqueness cho cặp `JOB_NAME` + `JOB_KEY`.

Việc tạo execution được quản lý trong transaction, với isolation và các ràng buộc database giúp tránh trường hợp hai launcher đồng thời đều được chấp nhận cho cùng một instance. Điều này đặc biệt quan trọng khi có nhiều pod/JVM.

~~~mermaid
flowchart TD
    A["Yêu cầu launch job + identifying parameters"] --> B["JobRepository tra cứu / tạo JobInstance"]
    B --> C{"Lịch sử execution của instance"}
    C -->|Chưa có execution| D["Tạo JobExecution mới"]
    C -->|Đang chạy| E["Từ chối launch trùng"]
    C -->|Đã COMPLETED| F["Từ chối chạy lại instance đã xong"]
    C -->|FAILED hoặc STOPPED| G["Có thể restart nếu chính sách cho phép"]
    D --> H["Thực thi job"]
    G --> H
~~~

Một số exception quan trọng từ `JobLauncher.run(...)`:

| Exception | Ngữ cảnh điển hình | Phản ứng thích hợp |
|---|---|---|
| `JobExecutionAlreadyRunningException` | Instance có execution đang chạy. | Báo công việc đã bắt đầu, không cố tạo run thứ hai. |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn thành, hoặc trạng thái không cho chạy lại theo quy tắc repository. | Trả thông tin đã hoàn thành và xác định có cần kỳ xử lý mới hay không. |
| `JobRestartException` | Không được restart, hoặc trạng thái execution không thể restart an toàn. | Điều tra và áp dụng quy trình phục hồi. |
| `JobParametersInvalidException` | Parameters không hợp lệ theo validator của Job. | Trả lỗi validation rõ ràng. |

Loại exception cụ thể khi có race còn có thể phụ thuộc thời điểm và cấu hình database: ràng buộc unique hoặc transaction conflict có thể phát sinh ở tầng JDBC trước khi caller nhận thông báo mong đợi. Không nên dựa vào một lần đọc trạng thái trước khi launch làm cơ chế chống trùng duy nhất.

### Hành vi theo trạng thái

| Trạng thái execution cũ | Khi yêu cầu cùng identifying parameters đến |
|---|---|
| `STARTING`, `STARTED` hoặc `STOPPING` | Execution đang hoạt động; repository ngăn chạy song song cùng instance. |
| `COMPLETED` | Không tạo một lượt chạy mới cho instance đã hoàn tất. |
| `FAILED` | Có thể tạo `JobExecution` mới để restart, nếu job cho phép. |
| `STOPPED` | Có thể restart theo cấu hình, sau khi execution đã thực sự dừng. |
| `ABANDONED` hoặc `UNKNOWN` | Cần đánh giá quy tắc và khả năng phục hồi; không được tự coi là công việc mới. |

**Restart không phải duplicate execution chạy đồng thời.** Restart là một execution mới của cùng `JobInstance`, chỉ được tiến hành khi trạng thái trước và chính sách restart cho phép.

## 4. Định nghĩa business key bền vững

Đối với công việc “chốt sổ mỗi ngày một lần cho mỗi cửa hàng”, business key có thể là:

~~~text
(jobName, businessDate, storeId)
~~~

`businessDate` phải được xác định theo timezone nghiệp vụ thống nhất; `storeId` phải có quy tắc chuẩn hóa (ví dụ không trộn `acme` với `ACME` nếu chúng biểu thị cùng cửa hàng). `requestId` của từng yêu cầu HTTP chỉ để truy vết và có thể đặt non-identifying.

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public JobParameters forBusinessDay(
        LocalDate businessDate,
        String storeId,
        String requestId) {
    return new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("storeId", storeId, true)
        .addString("requestId", requestId, false)
        .toJobParameters();
}
~~~

Ngược lại, cấu hình sau có thể **phá vỡ chống trùng**:

~~~java
// Mỗi lần gọi gần như chắc chắn có một JobInstance mới.
new JobParametersBuilder()
    .addString("businessDate", businessDate.toString(), true)
    .addLong("timestamp", System.currentTimeMillis(), true)
    .toJobParameters();
~~~

Vì `timestamp` là identifying, hai request xử lý cùng ngày có thể mang khóa khác nhau. Tương tự, `RunIdIncrementer` hoặc `JobOperator.startNextInstance(...)` được thiết kế để tạo **instance mới**, không phải để bảo vệ việc schedule trùng cùng kỳ nghiệp vụ.

### Khi nào cần identifying parameter mới?

Có trường hợp hợp lệ cần reprocess cùng ngày với một bộ dữ liệu đã sửa. Khi đó có thể đưa `inputVersion` hoặc `revision` vào business key:

~~~text
dailySettlementJob(
  businessDate=2026-11-15,
  storeId=ACME,
  inputVersion=v2
)
~~~

Phiên bản v2 là một instance có chủ đích khác v1. Nhưng điều đó chỉ đúng nếu nghiệp vụ giải thích được **v2 thay thế hay bổ sung kết quả v1**, cách công bố đầu ra và cách tránh side effect trùng. Một UUID ngẫu nhiên không thay thế được quyết định nghiệp vụ ấy.

## 5. Viết service launch có kiểm soát

Ví dụ Spring Batch 5.x với Java 17+:

~~~java
import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class SettlementLaunchService {

    private final JobLauncher launcher;
    private final Job settlementJob;

    public SettlementLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySettlementJob") Job settlementJob) {
        this.launcher = launcher;
        this.settlementJob = settlementJob;
    }

    public JobExecution launch(
            LocalDate date,
            String storeId,
            String requestId)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", date.toString(), true)
            .addString("storeId", storeId, true)
            .addString("requestId", requestId, false)
            .toJobParameters();

        return launcher.run(settlementJob, parameters);
    }
}
~~~

Điểm then chốt của service:

1. Danh tính nghiệp vụ được tạo nhất quán, không sinh identifying parameter ngẫu nhiên.
2. `JobRepository` được giao trách nhiệm điều phối tạo execution; service không tự lập một cờ `isRunning` trong bộ nhớ.
3. `JobExecutionAlreadyRunningException` và `JobInstanceAlreadyCompleteException` là các kết quả cần xử lý theo hợp đồng ứng dụng, không có nghĩa writer bị lỗi.
4. Khi lần chạy trước `FAILED` và job restartable, lời gọi cùng identifying parameters có thể **restart** thay vì bị từ chối; chính sách này phải được công bố rõ cho người dùng/API.
5. Nếu launcher bất đồng bộ, việc `run(...)` trả về `JobExecution` không đồng nghĩa xử lý đã hoàn thành; cần tiếp tục theo dõi trạng thái thực thi.

Đoạn mã giả định `dailySettlementJob` đã có cấu hình Spring Batch chuẩn và launcher trỏ đến `JobRepository` chia sẻ hợp lệ trong môi trường nhiều node.

### Phản hồi từ REST API

| Kết quả | Phản hồi gợi ý |
|---|---|
| Execution được chấp nhận | Trả `jobExecutionId`, business key và trạng thái (ví dụ HTTP `202 Accepted` nếu chạy nền). |
| Đã có execution đang chạy | Trả “đang xử lý”; có thể dùng HTTP `409 Conflict` và liên kết tới execution hiện có. |
| Instance đã hoàn tất | Trả “đã hoàn thành” với kết quả cũ, chẳng hạn HTTP `200 OK`; hoặc `409` nếu hợp đồng API chọn cách từ chối. |
| Parameters không hợp lệ | Trả lỗi input, thường dùng HTTP `400`. |
| Instance trước đó thất bại | Nêu chính sách có cho phép restart hay yêu cầu thao tác phục hồi riêng. |
| Database/JobRepository không khả dụng | Trả lỗi hạ tầng; caller retry phải giữ nguyên identifying parameters. |

Khi API yêu cầu **cùng idempotency key phải nhận được cùng phản hồi**, có thể cần một kho lưu trạng thái request riêng để gắn request key với kết quả launch. `JobInstance` bảo vệ danh tính batch; nó không tự lưu mọi response của HTTP request.

## 6. Không dùng “check rồi launch” làm khóa chống trùng

Đoạn mã sau tạo ra cửa sổ race:

~~~java
// Chỉ để minh họa anti-pattern; không dùng làm bảo vệ duy nhất.
if (jobExplorer.findRunningJobExecutions("dailySettlementJob").isEmpty()) {
    launcher.run(settlementJob, parameters);
}
~~~

Hai node có thể cùng đọc trạng thái “chưa có execution” trước khi bất kỳ node nào gọi launcher:

~~~text
Node A                       Node B
------                       ------
Check: chưa có job đang chạy
                             Check: chưa có job đang chạy
Gọi launcher
                             Gọi launcher
~~~

Đây là lỗi *time-of-check/time-of-use* (TOCTOU). `JobExplorer` hữu ích để hiển thị thông tin và tra cứu execution đang chạy, nhưng kết quả đọc có thể trở nên cũ ngay lập tức.

Tương tự, dùng `synchronized` hoặc `AtomicBoolean` chỉ khóa trong phạm vi object/JVM có liên quan; không ngăn các pod khác. Cờ trong RAM cũng biến mất khi restart và không đồng bộ với metadata `JobRepository`.

**Phép tạo execution phải được bảo vệ ở lớp chia sẻ có khả năng thực hiện thao tác nguyên tử**, điển hình là `JobRepository` dùng chung database, transaction và unique constraint đúng.

## 7. Chống trùng trong môi trường nhiều node

Khi nhiều pod chạy cùng ứng dụng Spring Batch, cần kiểm soát toàn bộ đường đi từ scheduler đến repository:

~~~mermaid
flowchart LR
    A["Scheduler / API\nNode A"] --> C["JobLauncher A"]
    B["Scheduler / API\nNode B"] --> D["JobLauncher B"]
    C --> E["JDBC JobRepository chung"]
    D --> E
    E --> F["BATCH_JOB_INSTANCE\nJOB_NAME + JOB_KEY unique"]
    E --> G["BATCH_JOB_EXECUTION\ntrạng thái và lịch sử"]
~~~

Điều kiện quan trọng:

- Các node phải sử dụng **cùng repository logic** cho những job cần chia sẻ lịch sử. Repository riêng trên từng pod không thể biết nhau.
- Schema Spring Batch phải có các ràng buộc định danh phù hợp và transaction manager hoạt động đúng.
- Việc tạo `JobExecution` của JDBC repository cần isolation tương thích với cạnh tranh giữa launcher. Không tùy tiện hạ isolation hoặc bỏ ràng buộc unique để né lỗi.
- Mọi node phải xây dựng identifying parameters từ **cùng quy tắc nghiệp vụ**, không dựa vào locale/timezone hay đồng hồ máy theo cách khác nhau.
- Các node phải xử lý trạng thái launch trùng một cách nhất quán, tránh biến các lỗi “đã có job chạy” thành nhiều vòng retry vô hạn.

Trong cấu hình JDBC JobRepository, việc tạo execution được triển khai qua transaction; mức isolation cho thao tác tạo có thể cấu hình, thường được giữ đủ mạnh để xử lý cạnh tranh. Chi tiết và cách cấu hình phụ thuộc phiên bản và cách khởi tạo repository (Spring Batch trực tiếp hoặc qua Spring Boot). Mục tiêu cần giữ là atomicity của phần tạo execution.

### Một JobInstance khác vẫn có thể chạy cùng lúc

Repository bảo vệ theo danh tính `JobInstance`; nó không phải distributed lock cho mọi công việc có dùng chung tài nguyên.

~~~text
dailySettlementJob(businessDate=2026-11-15)
dailySettlementJob(businessDate=2026-11-16)
~~~

Hai ngày là hai instance khác nhau. Nếu mỗi ngày ghi vào phân vùng riêng, đồng thời có thể là điều mong muốn. Nếu cả hai đều ghi vào cùng file `settlement.csv` hoặc rebuild toàn bộ một bảng, chúng có thể xung đột dù JobRepository kiểm soát đúng.

Khi cần chính sách **chỉ một process ghi tài nguyên R tại một thời điểm**, thiết kế thêm cơ chế sở hữu tài nguyên, chẳng hạn:

- Database claim/lease với khóa unique trên resource key.
- Distributed lock do hệ thống điều phối đáng tin cậy cung cấp.
- Phân chia output theo partition/job key để các instance độc lập không tranh chấp.
- Scheduler hỗ trợ điều phối tập trung, khi phạm vi bảo vệ khớp đúng yêu cầu nghiệp vụ.

Ví dụ PostgreSQL về một **claim bền vững**, chưa phải lease hoàn chỉnh:

~~~sql
CREATE TABLE batch_resource_claim (
    resource_key VARCHAR(200) PRIMARY KEY,
    owner_token VARCHAR(100) NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO batch_resource_claim(resource_key, owner_token)
VALUES (:resourceKey, :ownerToken)
ON CONFLICT (resource_key) DO NOTHING;
~~~

Ứng dụng cần kiểm tra số dòng được chèn: **1** nghĩa là claim được lấy; **0** nghĩa là tài nguyên đã có owner. Câu lệnh chỉ mô tả bước nhận quyền nguyên tử. Hệ thống thật còn cần xử lý giải phóng, crash, timeout, heartbeat và trường hợp owner cũ tiếp tục hoạt động sau khi quyền đã được cấp cho owner mới (*fencing*).

Không nên giữ một database transaction/row lock mở xuyên suốt toàn bộ job nhiều chunk chỉ để làm distributed lock: transaction dài có thể gây nghẽn, giữ khóa và không tương thích với transaction ngắn của từng chunk.

## 8. Scheduler phải tạo cùng business key trên mọi node

Ví dụ một job được chạy lúc 01:00 giờ Việt Nam để xử lý ngày hôm trước:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class DailySettlementScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final SettlementLaunchService launchService;

    DailySettlementScheduler(SettlementLaunchService launchService) {
        this.launchService = launchService;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    void launchPreviousDay() throws Exception {
        LocalDate businessDate =
            LocalDate.now(BUSINESS_ZONE).minusDays(1);

        launchService.launch(
            businessDate,
            "ACME",
            UUID.randomUUID().toString() // chỉ là non-identifying requestId
        );
    }
}
~~~

Ở hai pod, cùng kỳ nghiệp vụ tạo cùng `businessDate` và `storeId`. `requestId` được sinh khác nhau để trace nhưng không thay đổi danh tính instance.

Trong ứng dụng thật, scheduler nên bắt riêng các kết quả launch trùng và ghi nhận hợp lý vào log/metric. Không bắt và bỏ qua **mọi** exception: lỗi không kết nối repository, sai tham số hoặc lỗi tạo bean vẫn cần hiển thị rõ.

Một số điểm khác:

- `@Scheduled` thông thường được kích hoạt trên **mỗi instance** chứa bean đó. Nó không tự biến thành singleton scheduler toàn cụm.
- Điều phối ở Kubernetes CronJob, Quartz hoặc hệ ngoài có thể giảm số request trùng; repository vẫn là lớp bảo vệ theo danh tính job.
- Với Spring Boot, cấu hình `spring.batch.job.enabled=false` có thể tắt việc tự launch job khi startup nếu ứng dụng muốn chỉ khởi chạy có kiểm soát qua scheduler/API. Đây là property của Spring Boot, không thay thế JobRepository.
- Khi nhiều timezone hoặc lịch chuyển ngày tham gia, phải tính `businessDate` bằng quy tắc cố định thay vì để mỗi máy suy diễn riêng từ local time.

## 9. Khởi chạy lại sau lỗi: restart khác với launch trùng

Giả sử execution đầu tiên xử lý chunk thứ nhất thành công rồi lỗi ở chunk tiếp theo:

~~~text
JobInstance A: dailySettlementJob(date=2026-11-15, store=ACME)
    |
    +-- JobExecution #101: FAILED
    |     chunk 1: đã commit
    |     chunk 2: thất bại
    |
    +-- JobExecution #102: COMPLETED
          restart của cùng instance A
~~~

Khi `JobInstance A` đang ở trạng thái có thể restart, việc tạo `JobExecution #102` là một hoạt động có chủ đích. Spring Batch có thể dùng trạng thái `StepExecution` và `ExecutionContext` để tiếp tục theo cơ chế restart đã cấu hình.

Những nguyên tắc quan trọng:

1. **Đừng thêm `run.id` hoặc timestamp identifying chỉ để vượt lỗi “Job already exists”.** Điều đó tạo instance mới, có thể đọc lại toàn bộ input và ghi trùng những chunk đã commit.
2. **Đừng xóa bảng `BATCH_*` trước khi restart** nếu muốn giữ checkpoint và lịch sử execution.
3. **Đừng kỳ vọng toàn bộ job rollback khi một chunk lỗi.** Chunk đã commit thường vẫn tồn tại.
4. **Writer phải chịu được replay.** Dùng unique business key, idempotent update hoặc cơ chế chống ghi trùng phù hợp.
5. **Không restart khi execution cũ chưa thực sự kết thúc.** Nếu node bị crash làm trạng thái còn “đang chạy”, cần kiểm tra thực trạng và quy trình phục hồi được phê duyệt.

Một job có thuộc tính không cho restart hoặc một execution có trạng thái không thể phục hồi sẽ bị từ chối theo cơ chế repository. Việc gọi lại `JobLauncher` nhiều lần không tự sửa được lỗi ấy.

### Nếu cần reprocess một JobInstance đã COMPLETED?

Có thể nghiệp vụ muốn tính lại ngày đã chốt sổ vì thuật toán hoặc dữ liệu nguồn thay đổi. Khi đó cần thiết kế **lượt xử lý nghiệp vụ mới có chủ đích**:

~~~text
dailySettlementJob
businessDate=2026-11-15
storeId=ACME
revision=2
~~~

`revision` có thể là identifying parameter khi cần tách hẳn phiên bản v2 khỏi v1. Phải xác định rõ v2 thay thế kết quả v1, được lưu song song hay ghi bù trừ, và side effect như gửi email hoặc message phải hoạt động thế nào. Một timestamp ngẫu nhiên chỉ khiến hệ thống cho phép tạo instance mới nhưng không giải quyết các câu hỏi về dữ liệu.

## 10. Chống duplicate launch chưa phải exactly-once

Giả sử job chỉ có một execution được chấp nhận, nhưng writer gọi HTTP API thành công rồi transaction cơ sở dữ liệu rollback. Khi restart, writer có thể gửi HTTP lần nữa. `JobRepository` không thể tự rollback một hệ thống HTTP bên ngoài.

| Tình huống | Duplicate launch protection giúp gì? | Cần cơ chế bổ sung nào? |
|---|---|---|
| Hai request cùng key trong lúc job đang chạy | Ngăn execution song song của cùng instance khi repository đúng. | Phản hồi API phù hợp, truy vết execution. |
| Request trùng sau `COMPLETED` | Không tạo run mới cùng key. | Trả kết quả đã xử lý cho caller. |
| Job `FAILED` rồi restart | Quản lý execution mới của cùng instance. | Checkpoint, idempotent writer. |
| Hai instance khác ngày cùng ghi một file | Không bị coi là trùng danh tính. | Tên file riêng hoặc resource lock. |
| Writer cộng số dư sau khi retry | Không đảm bảo phép cộng chỉ chạy một lần. | Event ID duy nhất, transaction và logic chống cộng trùng. |
| Writer gọi API và chunk rollback | Không rollback side effect HTTP. | Idempotency key ở phía nhận, outbox hoặc bù trừ. |
| API timeout rồi gửi lại cùng request | Cùng identifying params được nhận diện. | Idempotent response nếu hợp đồng API yêu cầu. |

Các cơ chế hỗ trợ tính nhất quán gồm:

**Ràng buộc unique theo business key.** Ví dụ bảng đầu ra có unique key `(business_date, store_id, transaction_id)` để một item được replay không tạo nhiều hàng tương đương.

**Idempotent writer.** Ghi lại cùng event cho cùng trạng thái cuối; tránh phép cộng dồn không có guard nếu một event có thể bị đọc lại.

**Transactional outbox.** Cùng commit dữ liệu nghiệp vụ và thông tin cần phát sự kiện vào database; tiến trình gửi có thể retry, consumer phải xử lý event ID trùng.

**Phân vùng hoặc khóa tài nguyên.** Các instance khác nhau không được cùng ghi một file hoặc bảng toàn cục nếu không có quy tắc phối hợp.

Duplicate launch protection là **lớp điều phối execution**. Nó không thay thế transaction của chunk, checkpoint, cơ chế retry hoặc tính đúng đắn của writer.

## 11. Quan sát, xử lý lỗi và vận hành

Một lần launch bị từ chối không nhất thiết là sự cố. Hệ thống cần cho người vận hành biết nó trùng với job nào và kết quả trước đó ra sao.

Các trường log hữu ích:

~~~text
jobName=dailySettlementJob
businessDate=2026-11-15
storeId=ACME
requestId=req-57
jobInstanceId=...
jobExecutionId=...
launchOutcome=ALREADY_RUNNING
~~~

Chỉ log các tham số được phép công khai trong hệ thống vận hành. `JobParameters` thường được lưu vào metadata; không đưa password, token bí mật hoặc dữ liệu nhạy cảm vào chúng.

| Trường hợp | Hướng vận hành |
|---|---|
| Scheduler khác node launch cùng key | Ghi nhận duplicate/suppressed event; kiểm tra execution đang chạy. |
| API gọi lại một kỳ đã hoàn tất | Trả thông tin hoàn thành hoặc đường dẫn kết quả theo hợp đồng. |
| Restart sau `FAILED` | Gắn execution mới với instance cũ, theo dõi các step được thực thi lại. |
| Repository không truy cập được | Cảnh báo lỗi hạ tầng; không lặng lẽ chuyển sang repository tạm khác. |
| Execution mãi ở `STARTED` sau crash | Xác minh node/tác vụ ngoài database trước khi can thiệp metadata. |

`JobExplorer` hỗ trợ tra cứu metadata, `JobOperator` hỗ trợ các thao tác vận hành phù hợp. Một execution có metadata “đang chạy” sau crash có thể cần xử lý phục hồi, nhưng **không được tự sửa/xóa các hàng `BATCH_JOB_EXECUTION` một cách tùy tiện** để “mở khóa”. Việc này có thể phá checkpoint, lịch sử audit hoặc làm chạy lại dữ liệu đã commit.

Một thao tác yêu cầu dừng job không phải cơ chế diệt tức thời bất kỳ tiến trình nào; cần hiểu hệ thống đang chạy ở đâu, có checkpoint nào đã lưu và có side effect ngoài transaction hay không.

## 12. Những kịch bản cần kiểm chứng

| Kịch bản | Input | Kỳ vọng |
|---|---|---|
| Hai launch đồng thời cùng key | Cùng `jobName`, ngày, store | Không có hai execution **cùng JobInstance chạy đồng thời**. |
| Client retry với request ID mới | Cùng identifying params, `requestId` khác | Vẫn cùng JobInstance. |
| Ngày nghiệp vụ khác | `businessDate` khác | Hai JobInstance hợp lệ. |
| Cửa hàng khác | `storeId` khác | Hai JobInstance riêng; đầu ra phải được cô lập khi cần. |
| Instance đã `COMPLETED` | Gọi lại cùng identifying params | Không tạo run mới; caller biết đã hoàn tất. |
| Instance `FAILED` | Gọi lại cùng identifying params | Restart theo chính sách, tạo JobExecution tiếp theo của cùng instance. |
| Timestamp identifying thay đổi | Mỗi request có thời gian mới | Tạo instance mới; cho thấy lỗi thiết kế key nếu kỳ nghiệp vụ phải duy nhất. |
| Hai pod dùng repository riêng | Cùng business key | Có nguy cơ xử lý trùng; cần dùng kho metadata chung. |
| Hai instance khác key dùng cùng file | Cùng `report.csv` | Có thể tranh chấp dù JobRepository hoạt động đúng. |
| Một chunk đã commit trước khi crash | Restart sau lỗi | Kiểm chứng không mất item và writer không tạo tác động nghiệp vụ trùng. |

### Kiểm thử concurrent launch một cách xác định

Không nên chỉ gọi launcher hai lần tuần tự rồi khẳng định đã kiểm tra race. Nếu lần đầu chạy rất nhanh, lần thứ hai có thể chỉ gặp trạng thái `COMPLETED`, chứ không kiểm tra yêu cầu đến khi instance đang chạy.

Một integration test có thể:

1. Khởi động JDBC `JobRepository` trên database test có schema và transaction phù hợp.
2. Dùng step test tạm giữ execution ở trạng thái chạy bằng latch/barrier có kiểm soát.
3. Gửi hai launch gần đồng thời với cùng identifying parameters, qua hai thread hoặc hai process nếu muốn kiểm tra liên JVM.
4. Ghi nhận một execution được phép chạy và yêu cầu còn lại bị từ chối hoặc xử lý theo trạng thái repository phù hợp.
5. Giải phóng latch, để job kết thúc; truy vấn metadata và bảng nghiệp vụ để xác nhận invariant không có hai execution cùng instance chạy song song.
6. Lặp lại với `requestId` non-identifying khác, rồi với `businessDate` khác để chứng minh hệ thống phân biệt đúng công việc trùng và công việc mới.

Không nên buộc test phụ thuộc vào thứ tự thread hay đúng một thông báo exception khi database/isolation có thể khác nhau. Điều cần kiểm chứng là invariant **không trùng xử lý cùng instance** và hiệu ứng đầu ra đúng. Nếu muốn khẳng định cụ thể `JobExecutionAlreadyRunningException`, phải giữ execution đầu thực sự đang chạy lúc yêu cầu thứ hai đến.

Ngoài race, kiểm thử restart phải giữ identifying parameters cũ và metadata cần thiết, làm một chunk commit rồi gây lỗi, sau đó phục hồi và xác nhận output đầy đủ nhưng không có bản ghi trùng.

## 13. Những sai lầm thường gặp

**Dùng `run.id` hoặc thời gian hiện tại làm identifying parameter cho mọi request.** Mỗi request thành một JobInstance khác, dù cùng xử lý một ngày. Chỉ dùng tham số tạo instance mới khi thực sự cần một kỳ/phiên bản xử lý mới.

**Chỉ kiểm tra `JobExplorer.findRunningJobExecutions(...)` trước khi chạy.** Kết quả check có thể lỗi thời ngay lập tức; đây không phải lock nguyên tử. Cơ chế tạo execution ở repository phải chịu trách nhiệm điều phối.

**Dùng `synchronized` hoặc cờ JVM để khóa toàn cụm.** Những công cụ này không phối hợp giữa nhiều pod và không thay thế metadata bền vững.

**Mỗi node có JobRepository riêng.** Các node không biết job nào đã chạy ở node khác, nên có thể tạo nhiều instance logic của cùng công việc nghiệp vụ.

**Cho rằng JobRepository ngăn mọi job dùng chung resource.** Nó định danh theo tên job và identifying parameters, không tự khóa file đích hoặc bảng tổng hợp của hai instance khác nhau.

**Xóa batch metadata để “restart” một job.** Việc xóa lịch sử có thể làm mất thông tin checkpoint, khiến lần chạy sau quay lại từ đầu và ghi trùng những chunk đã commit.

**Cho rằng một job không launch trùng thì writer không thể ghi trùng.** Retry, restart, HTTP side effect và concurrent job instance khác vẫn tạo nguy cơ trùng nghiệp vụ.

**Nuốt mọi exception từ launcher.** Việc “đã có job chạy” thường có thể xử lý như trạng thái bình thường, nhưng lỗi database, transaction hoặc invalid parameters là tín hiệu cần xử lý riêng.

## 14. Quy trình thiết kế duplicate launch protection

1. **Xác định đơn vị công việc nghiệp vụ:** một ngày/cửa hàng, một file/phiên bản, một tài khoản/kỳ đối soát, v.v.
2. **Chọn identifying parameters ổn định:** cùng công việc phải có cùng `jobName` và cùng key. Dùng non-identifying parameters cho dữ liệu trace thay đổi theo từng request.
3. **Dùng một JobRepository phù hợp phạm vi triển khai:** schema, unique constraint, isolation và transaction phải hoạt động cho mọi launcher cần phối hợp.
4. **Trả trạng thái launch rõ ràng:** phân biệt đang chạy, đã hoàn tất, restart hợp lệ, invalid parameters và lỗi hạ tầng.
5. **Bảo vệ tài nguyên dùng chung ngoài JobInstance:** output partitioning hoặc một cơ chế claim/lease khi các instance khác key vẫn có thể xung đột.
6. **Thiết kế writer an toàn khi retry/restart:** khóa nghiệp vụ, idempotency, transaction/outbox và cơ chế phục hồi rõ ràng.
7. **Kiểm chứng race và crash:** dùng test đồng thời có kiểm soát, kiểm tra metadata và dữ liệu đầu ra.

Một quy tắc dễ nhớ:

> **Cùng công việc nghiệp vụ → cùng JobInstance. Công việc nghiệp vụ mới → JobInstance mới. Thử lại sau lỗi → JobExecution mới của JobInstance cũ.**

## Kết luận

Duplicate launch protection trong Spring Batch dựa trước hết vào **danh tính `JobInstance`** và khả năng của **`JobRepository`** kiểm soát việc tạo `JobExecution` khi nhiều nguồn cùng yêu cầu chạy. Bộ identifying parameters cần ổn định theo khóa nghiệp vụ; nếu vô tình thêm timestamp, UUID hoặc `run.id` mới cho mọi request, hệ thống sẽ tự biến những yêu cầu trùng thành nhiều instance hợp lệ.

Ở cấp hệ thống, cần kết hợp cơ chế đó với cách phản hồi API, điều phối scheduler, quy tắc restart, khóa tài nguyên khi có nhiều instance khác nhau và writer idempotent. Khi những lớp bảo vệ có phạm vi rõ ràng, cả hoạt động khởi chạy bình thường, retry do timeout và phục hồi sau crash đều có thể được xử lý nhất quán, quan sát được và an toàn cho dữ liệu.
