# Lock khi nhiều scheduler instance trong Spring Batch

## 1. Bối cảnh: một lịch chạy, nhiều ứng dụng cùng kích hoạt

Khi một ứng dụng Spring Boot được triển khai thành nhiều instance, mỗi instance thường có **ApplicationContext** và bộ lập lịch riêng. Nếu cả ba instance đều có phương thức gắn **@Scheduled**, cả ba có thể kích hoạt cùng một Spring Batch Job khi đến giờ:

~~~text
                    01:10 UTC mỗi ngày
                           |
               +-----------+-----------+
               |           |           |
          Instance A   Instance B   Instance C
           @Scheduled   @Scheduled   @Scheduled
               |           |           |
               +-----------+-----------+
                           |
                     launch Job
                           |
                Có thể chạy trùng
~~~

Giả sử Job tổng hợp doanh thu của ngày hôm trước. Nếu bị chạy đồng thời, nó có thể ghi nhiều bản ghi báo cáo giống nhau, gửi email hai lần, xử lý cùng một giao dịch hoặc tranh chấp khóa database. Dù có ba pod trong Kubernetes hay ba máy chủ độc lập, **@Scheduled chỉ lập lịch tại từng JVM**, không tự bầu ra một instance duy nhất để thực thi.

**Distributed lock** là cơ chế để các instance thống nhất rằng, trong một khoảng thời gian, chỉ một instance được quyền bắt đầu hoặc thực hiện tác vụ đã xác định. Trong bối cảnh Spring Batch Core Processing, cần hiểu hai lớp kiểm soát:

1. **Scheduler lock:** điều phối nhiều scheduler instance cùng kích hoạt một công việc theo lịch.
2. **JobRepository và JobInstance:** quản lý danh tính, lịch sử, trạng thái và restart của một Batch Job.

Hai lớp bổ trợ cho nhau. Không nên xem một lớp là bản thay thế hoàn toàn cho lớp còn lại.

## 2. Phân biệt scheduler lock và bảo vệ từ JobRepository

Spring Batch xác định **JobInstance** bằng tên Job và tập **identifying JobParameters**. Trong thông lệ, hai yêu cầu chạy cùng một tên Job, cùng identifying parameters, được xem là yêu cầu đối với cùng một JobInstance. JobRepository điều phối việc tạo **JobExecution**; nếu JobInstance đang chạy, việc launch trùng có thể bị từ chối bằng **JobExecutionAlreadyRunningException**. Nếu JobInstance đã hoàn thành, yêu cầu chạy lại có thể gặp **JobInstanceAlreadyCompleteException**.

Ví dụ:

~~~text
Job: dailySettlementJob

Instance A:
  businessDate = 2026-11-15
  -> dailySettlementJob(businessDate=2026-11-15)

Instance B:
  businessDate = 2026-11-15
  -> cùng JobInstance, Spring Batch kiểm tra trạng thái

Instance C:
  businessDate = 2026-11-15
  run.id = 872345
  -> có thể thành JobInstance khác nếu run.id là identifying
~~~

Nếu mỗi scheduler dùng **System.currentTimeMillis()**, một UUID hoặc **RunIdIncrementer** để tạo identifying parameters mới cho mỗi lần kích hoạt, ba instance có thể tạo **ba JobInstance khác nhau** và cùng chạy logic nghiệp vụ của một ngày. JobRepository không tự biết rằng cả ba đều xử lý cùng một tập giao dịch.

Ngược lại, nếu cả ba dùng identifying parameter cố định theo ngày, JobRepository cung cấp một lớp bảo vệ quan trọng; nhưng các instance thừa có thể liên tục gọi launch, nhận exception và tạo log nhiễu. Scheduler lock cho phép quyết định **instance nào được thực hiện lời gọi lập lịch** ngay từ đầu.

| Vấn đề | Scheduler lock dùng chung | Spring Batch JobRepository |
| --- | --- | --- |
| Nhiều JVM cùng đến giờ cron | Một JVM lấy lock; JVM khác bỏ qua hoặc không lấy được lock | Không tự điều phối lời gọi **@Scheduled** |
| Hai launch cùng JobInstance đang chạy | Có thể hạn chế nếu đều đi qua cùng lock | Kiểm soát trạng thái chạy của JobInstance |
| Hai JobInstance khác nhau nhưng cùng xử lý một tập dữ liệu | Có thể ngăn nếu cùng tên lock và khóa còn hiệu lực | Có thể cho chạy đồng thời |
| Restart một Job thất bại | Không tự lưu checkpoint | Quản lý **JobExecution**, **StepExecution**, **ExecutionContext** |
| Chống ghi trùng ở API hoặc hệ thống ngoài | Không bảo đảm tuyệt đối | Không thay thế tính idempotent của writer |
| Instance chết giữa chừng | Có thể cần thời gian chờ lease hết hạn | Có thể lưu trạng thái FAILED/STARTED và phục vụ phục hồi theo cơ chế Job |

Điểm mấu chốt: **lock điều phối quyền thực thi trong thời gian nhất định**, còn Spring Batch quản lý một lần thực thi Job và trạng thái xử lý. Hệ thống quan trọng nên có thêm khóa nghiệp vụ, giao dịch và xử lý idempotent tại nơi ghi kết quả.

## 3. Yêu cầu của cơ chế lock trong môi trường nhiều instance

Một distributed lock cho scheduler cần thỏa những điều kiện cơ bản:

- **Dùng chung nguồn sự thật:** mọi instance truy cập cùng bảng lock trong database, cùng Redis hoặc cùng hệ thống điều phối. Lock lưu trong RAM, **synchronized**, **ReentrantLock** hay **AtomicBoolean** riêng từng JVM không có tác dụng phối hợp nhiều instance.
- **Thao tác lấy lock nguyên tử:** trong cùng thời điểm, tối đa một instance nhận được quyền sở hữu lock hợp lệ. Không thể tự viết kiểu “SELECT xem có lock chưa rồi INSERT” nếu hai thao tác không được ràng buộc bằng cơ chế nguyên tử.
- **Có cơ chế phục hồi:** nếu instance giữ lock bị kill hoặc mất kết nối, hệ thống vẫn có cách cho instance khác chạy sau một thời hạn hoặc điều kiện xác định.
- **Tên lock nhất quán:** những instance cùng triển khai một lịch chạy phải dùng **cùng tên lock**, cùng namespace và cùng backend.
- **Phạm vi lock đúng:** lock phải bao trùm hành vi cần bảo vệ, tối thiểu là việc quyết định launch; với yêu cầu không có hai Job đang hoạt động, thời gian sở hữu lock phải phù hợp với **toàn bộ thời gian Job chạy**.
- **Dữ liệu nghiệp vụ an toàn khi thử lại:** lock giúp hạn chế trùng, nhưng crash, mất kết nối hoặc lease hết hạn vẫn có thể dẫn tới xử lý lại.

Có hai cách hình dung phổ biến:

~~~text
A. Khóa tại mỗi JVM (không đủ)

Instance A -- local lock A -- launch
Instance B -- local lock B -- launch
Instance C -- local lock C -- launch

B. Distributed lock dùng chung

Instance A --+
Instance B --+--> Shared lock store --> chỉ một owner
Instance C --+           |
                            +--> launch
~~~

Trong Spring Boot, một lựa chọn thực dụng là **ShedLock** với JDBC. Ngoài ra còn có Quartz cluster, leader election và các cách dùng khóa database trực tiếp; lựa chọn phụ thuộc vào yêu cầu lịch, thời lượng Job và cách triển khai hệ thống.

## 4. Cơ chế lease lock: acquire, release và hết hạn

Một số thư viện, trong đó có ShedLock, dùng **lock có thời hạn (lease)**. Database lưu tên lock, thời điểm bắt đầu giữ và thời điểm lock được coi là hết hạn. Quy trình đơn giản:

~~~text
01:10:00  Instance A giành được lock "dailySettlement"
01:10:00  Instance B không lấy được -> bỏ qua lượt này
01:10:01  Instance C không lấy được -> bỏ qua lượt này
01:10:02  A bắt đầu chạy dailySettlementJob
01:15:00  A hoàn thành, release lock
Ngày sau  Instance mới có thể lấy lock cho kỳ tiếp theo
~~~

Nếu A bị kill lúc 01:12:00, nó không thể release lock theo cách thông thường. Khi thời hạn **lockAtMostFor** trôi qua, lock được xem là hết hạn; instance khác có thể giành quyền ở lần kích hoạt sau.

Tuy nhiên, cần phân biệt hai trường hợp:

- **Instance thực sự chết:** lease cho phép hệ thống tự phục hồi sau một khoảng chờ.
- **Instance vẫn chạy nhưng quá hạn lease:** một instance khác có thể lấy lock và chạy cùng Job khi instance đầu còn hoạt động. Đây là tình huống nguy hiểm, đặc biệt nếu hai lần chạy dùng JobParameters khác nhau hoặc có tác dụng phụ bên ngoài database.

Vì vậy, một cơ chế lease lock không phải bảo đảm tuyệt đối rằng chỉ có một thao tác nghiệp vụ xảy ra. Nếu công việc có thời lượng không dự đoán được hoặc kéo dài nhiều giờ, cần thiết kế chính sách gia hạn lease, giám sát thời lượng và lớp bảo vệ ở dữ liệu đầu ra.

## 5. Dùng ShedLock với Spring Boot và JDBC

### 5.1. Trường hợp phù hợp

**ShedLock** thích hợp khi:

- Ứng dụng đã dùng **@Scheduled**.
- Có nhiều instance dùng chung một database đáng tin cậy.
- Mong muốn các instance không lấy được lock **bỏ qua lượt gọi** thay vì xếp hàng chạy lần lượt.
- Chỉ cần điều phối lịch chạy đơn giản, không cần tính năng quản lý misfire, trigger phức tạp hoặc lịch bền vững của một hệ thống scheduler riêng.

Ví dụ bên dưới minh họa **Spring Boot 3.x, Spring Batch 5.x, Java 17**. Chọn phiên bản ShedLock tương thích với phiên bản Spring và Java thực tế của dự án. ShedLock cần hai phần: hỗ trợ annotation cho Spring và **LockProvider** tương ứng backend lưu trữ.

**Ví dụ dependencies trong Gradle (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Thay VERSION bằng phiên bản ShedLock tương thích dự án.
    implementation 'net.javacrumbs.shedlock:shedlock-spring:VERSION'
    implementation 'net.javacrumbs.shedlock:shedlock-provider-jdbc-template:VERSION'
}
~~~

Nếu ứng dụng đã có starter Batch/JDBC, không cần khai báo trùng. Không nên tự ghép các phiên bản khác nhau của **shedlock-spring** và **shedlock-provider-jdbc-template**.

### 5.2. Tạo bảng lock dùng chung

Ví dụ DDL cho database có kiểu **TIMESTAMP** tương thích:

~~~sql
CREATE TABLE shedlock (
    name       VARCHAR(64)  NOT NULL,
    lock_until TIMESTAMP(3) NOT NULL,
    locked_at  TIMESTAMP(3) NOT NULL,
    locked_by  VARCHAR(255) NOT NULL,
    PRIMARY KEY (name)
);
~~~

Tên bảng và kiểu timestamp có thể điều chỉnh theo database; nếu dùng schema riêng hoặc đổi tên bảng, phải cấu hình **LockProvider** tương ứng. Tạo bảng bằng **Flyway/Liquibase** hoặc migration tập trung của dự án. Không để từng scheduler instance cùng chạy một script xóa và tạo lại bảng lock mỗi khi khởi động.

Ý nghĩa các cột:

| Cột | Ý nghĩa |
| --- | --- |
| **name** | Định danh duy nhất của tác vụ được khóa; mọi instance bảo vệ cùng tác vụ phải dùng một tên. |
| **lock_until** | Thời điểm sau đó lock có thể được lấy lại nếu chưa được gia hạn. |
| **locked_at** | Thời điểm bắt đầu giữ lock, hỗ trợ chẩn đoán. |
| **locked_by** | Thông tin instance giữ lock để hỗ trợ quan sát và điều tra. |

Database là **điểm điều phối chung**. Nếu instance A dùng database X còn B dùng database Y, hai instance vẫn có thể lấy lock mang cùng tên và chạy trùng. Kết nối tới đúng backend quan trọng không kém việc thêm annotation.

### 5.3. Bật scheduling và ShedLock

~~~java
import javax.sql.DataSource;

import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT2H")
public class BatchSchedulerConfiguration {

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

**@EnableScheduling** kích hoạt các phương thức lập lịch của Spring; **@EnableSchedulerLock** kích hoạt cơ chế khóa cho các phương thức được ShedLock hỗ trợ. **LockProvider** là thành phần thực thi thao tác lock trên database.

**usingDbTime()** sử dụng thời gian của database để xác định hạn lock, giúp giảm tác động của sai lệch đồng hồ giữa các máy chạy scheduler. Với nhiều instance triển khai ở các node khác nhau, không nên giả định đồng hồ hệ điều hành của tất cả node hoàn toàn đồng bộ.

Ví dụ trên sử dụng cấu hình database và JDBC tương ứng; với nhiều DataSource, hãy chỉ rõ DataSource **cùng được chia sẻ bởi tất cả scheduler instance**. Bảng lock không nhất thiết phải nằm chung database nghiệp vụ, nhưng mọi instance phải dùng chung backend đó.

### 5.4. Khóa phương thức @Scheduled

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailySettlementScheduler {

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;
    private final Clock clock;

    public DailySettlementScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailySettlementJob") Job dailySettlementJob,
            Clock clock) {

        this.jobLauncher = Objects.requireNonNull(jobLauncher);
        this.dailySettlementJob = Objects.requireNonNull(dailySettlementJob);
        this.clock = Objects.requireNonNull(clock);
    }

    @Scheduled(cron = "0 10 1 * * *", zone = "UTC")
    @SchedulerLock(
            name = "batch.dailySettlement.schedule",
            lockAtMostFor = "PT2H",
            lockAtLeastFor = "PT30S")
    public void runDailySettlement() throws Exception {
        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncher.run(dailySettlementJob, parameters);

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                    "dailySettlementJob did not complete: "
                    + execution.getStatus());
        }
    }
}
~~~

Đăng ký **Clock** cùng múi giờ UTC:

~~~java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
~~~

Cron **0 10 1 * * *** được Spring diễn giải thành mỗi ngày lúc **01:10 UTC**, và Job nhận **businessDate** là ngày UTC trước đó. Ví dụ này giả định lịch chốt ngày của hệ thống được quy định theo UTC; với nghiệp vụ cần múi giờ khác, hãy quy định nhất quán timezone cho cả cron và cách tính ngày xử lý. **Clock** còn giúp cố định thời gian trong test mà không phải thay đổi đồng hồ hệ thống.

Chỉ một scheduler instance lấy được lock tên **batch.dailySettlement.schedule** tại một thời điểm. Instance không lấy được lock sẽ bỏ qua lượt gọi được bảo vệ. Phương thức cần được Spring quản lý và được gọi qua cơ chế proxy/điểm chặn của ShedLock; việc gọi nội bộ qua **this.runDailySettlement()** hoặc khởi tạo thủ công bằng **new** có thể làm mất tác dụng của annotation tùy cách cấu hình.

**Điều kiện rất quan trọng:** ví dụ giả định **JobLauncher chạy đồng bộ**, tức lời gọi **jobLauncher.run(...)** chỉ trả về khi Job đã kết thúc. Nếu ứng dụng cấu hình asynchronous JobLauncher, phương thức scheduler có thể release lock ngay khi Job mới được khởi tạo, trong khi xử lý Batch vẫn tiếp diễn. Trường hợp đó phải điều phối lock theo **vòng đời Job thực tế** hoặc dùng một thiết kế khác bảo đảm không có hai Job cùng xử lý dữ liệu.

### 5.5. Lock giữ trong bao lâu?

ShedLock có hai tham số thường gây nhầm lẫn:

| Tham số | Công dụng | Điều cần cân nhắc |
| --- | --- | --- |
| **lockAtMostFor** | Giới hạn tối đa thời gian giữ lock, kể cả khi process không release được. | Phải lớn hơn thời lượng thực thi dự kiến cộng phần dự phòng hợp lý; quá ngắn dễ có hai owner theo thời gian. |
| **lockAtLeastFor** | Giữ lock ít nhất trong thời gian đã chỉ định, kể cả khi phương thức kết thúc nhanh. | Có thể giảm chạy lặp do lịch/clock lệch trong thời gian ngắn, nhưng làm chậm lượt hợp lệ kế tiếp nếu đặt quá lớn. |

Ví dụ:

~~~text
01:10:00  A acquire, lockAtMostFor=2h, lockAtLeastFor=30s
01:10:08  Job hoàn thành, scheduler release
01:10:30  Lock mới đủ thời gian tối thiểu để được coi là đã release
~~~

Nếu Job chạy 40 phút, lock giữ đến lúc Job kết thúc (nếu launcher đồng bộ). Nếu A chết ở phút thứ 20, lock có thể còn tồn tại đến mốc tối đa đã tính khi acquire. Nếu Job thật sự chạy **hơn 2 giờ**, A có thể vẫn xử lý sau khi lock hết hạn, và một instance khác có thể lấy lock.

Không chọn **lockAtMostFor** bằng đúng cron interval theo thói quen. Hãy dựa vào dữ liệu quan sát được về **thời lượng Job dài nhất có thể chấp nhận**, chiến lược timeout, khả năng gia hạn lock và yêu cầu khôi phục sau crash. Lease càng dài thì hệ thống càng lâu mới có thể lấy lại lock nếu owner thực sự chết.

## 6. JobParameters phải nhất quán theo kỳ nghiệp vụ

Một distributed lock không sửa được việc tạo JobParameters sai. Hai yêu cầu xử lý cùng **businessDate** nên dùng cùng identifying parameters để Spring Batch nhận diện cùng JobInstance.

**Cách tạo có thể gây chạy trùng:**

~~~java
JobParameters params = new JobParametersBuilder()
        .addLong("timestamp", System.currentTimeMillis(), true)
        .toJobParameters();
~~~

Mỗi lần launch tạo một JobInstance mới. Nếu lease hết hạn trong lúc Job đầu vẫn chạy, hoặc một đường gọi thủ công không sử dụng lock, Job thứ hai có thể xử lý trùng cùng dữ liệu.

**Cách định danh theo kỳ xử lý:**

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

Với cùng tên Job và cùng **businessDate**, Spring Batch có thể từ chối launch trùng trong khi Job đang chạy hoặc sau khi đã hoàn thành. Đây là lớp bảo vệ bổ sung bên dưới scheduler lock.

Không phải mọi Job đều xử lý theo ngày. Với lịch mỗi 15 phút, có thể dùng **windowStart** hoặc mã kỳ xử lý được chuẩn hóa thành một mốc rõ ràng, ví dụ **2026-11-16T01:00:00Z**. Điều quan trọng là mọi instance tính ra **cùng mốc cho cùng một kỳ**, thay vì lấy thời điểm hiện tại đến millisecond.

Đối với Job cần restart:

1. Lần đầu chạy **FAILED** với identifying parameters của kỳ đó.
2. Lần restart sử dụng **chính identifying parameters cũ**, để Spring Batch tiếp tục đúng JobInstance.
3. Không tạo tham số identifying mới chỉ để “ép” Job chạy lại. Cách đó có thể bỏ qua checkpoint và làm tăng rủi ro ghi trùng dữ liệu.

Cần quyết định riêng chính sách retry cho các kỳ bị lỗi: lịch ngày hôm sau thường chuyển sang **businessDate** mới, nên nó **không tự restart** Job của ngày trước. Việc phát hiện và xử lý kỳ còn lỗi có thể dùng công cụ vận hành, lịch retry hoặc JobOperator theo quy trình rõ ràng.

## 7. Lock nên bao quanh phần nào của quy trình?

Một Job có thể được kích hoạt qua nhiều đường:

~~~text
                     +--> @Scheduled ---> Scheduler lock --+
                     |                                    |
dailySettlementJob <-+--> REST API / manual trigger ------+
                     |
                     +--> event listener / message --------+
~~~

Nếu chỉ đặt **@SchedulerLock** trên phương thức **@Scheduled**, các đường API, event hoặc quản trị viên vẫn có thể launch Job mà không đi qua lock. Đây không phải lỗi của ShedLock; phạm vi bảo vệ đã được khai báo chỉ bao quanh đường gọi scheduler.

Có ba chiến lược phổ biến:

**Chiến lược A — lock chỉ bảo vệ scheduler:** dùng khi mục tiêu là tránh nhiều pod cùng xử lý cron tick. Các đường gọi khác dựa trên JobRepository, JobParameters và idempotency. Đây là lựa chọn đơn giản nếu launch thủ công có quy trình riêng.

**Chiến lược B — mọi đường gọi đi qua cùng coordinator:** đặt logic quyết định kỳ xử lý và lock trong một service điều phối được sử dụng thống nhất. Khi đó cần thiết kế API của lock rõ ràng, đảm bảo cả REST và scheduler thực sự gọi qua lớp được bảo vệ; không đặt annotation rồi tự gọi nội bộ bỏ qua Spring proxy.

**Chiến lược C — khóa theo khóa nghiệp vụ ở database:** ví dụ bảng **business_period** có ràng buộc unique cho kỳ chốt sổ và trạng thái xử lý, cùng logic claim nguyên tử. Giải pháp này giúp kiểm soát cả các yêu cầu khởi chạy từ ngoài scheduler.

Với hệ thống có nguy cơ tạo side effect không thể rollback, nên kết hợp lớp bảo vệ tại **đích ghi dữ liệu**. Không nên giả định mọi đường gọi đều bị scheduler lock kiểm soát.

## 8. Rủi ro của async JobLauncher và Job chạy lâu

Giả sử scheduler lấy lock, gọi JobLauncher bất đồng bộ và trả về sau vài millisecond:

~~~text
01:10:00  Instance A lấy lock
01:10:01  A launch Job, Job chuyển sang thread khác
01:10:01  @Scheduled method trả về; lock được release
01:10:02  Instance B có thể lấy lock
01:10:02  B launch một Job khác/cùng kỳ
01:10:03  A và B có thể cùng xử lý nếu các lớp bảo vệ khác không chặn
~~~

Khi dùng **TaskExecutorJobLauncher** với một **TaskExecutor** bất đồng bộ, callback trả về của launcher không đồng nghĩa **JobExecution** đã kết thúc. Kiểm tra ngay **execution.getStatus()** cũng có thể cho trạng thái **STARTING** hoặc **STARTED**, dẫn đến nhận định sai.

Có thể chọn một trong những hướng thiết kế:

- Dùng launcher đồng bộ riêng cho các Job mà scheduler cần giữ lock đến khi hoàn tất, nếu phù hợp với nguồn lực và thời lượng.
- Dùng một thành phần orchestration có thể theo dõi **JobExecution** cho đến trạng thái cuối và quản lý lease tương ứng.
- Dùng cơ chế hàng đợi/worker có claim công việc nguyên tử, thay vì coi lời gọi async là toàn bộ đơn vị công việc.
- Với Job rất dài, thiết kế gia hạn lease có giám sát và cơ chế xử lý owner bị treo; bảo vệ kết quả đầu ra bằng khóa nghiệp vụ/idempotency.

Không đặt một transaction database kéo dài suốt hàng giờ chỉ để giữ khóa dòng. Loại khóa phù hợp phụ thuộc thời lượng và yêu cầu crash recovery; lease lock được thiết kế để tránh giữ transaction dài, nhưng chính vì vậy cần xử lý trường hợp lease hết hạn trong khi owner chưa dừng.

## 9. Tình huống cần hiểu trước khi đưa vào production

### 9.1. Hai instance thức dậy lệch nhau

Hai scheduler không nhất thiết kích hoạt chính xác cùng một millisecond. Instance A có thể chạy sớm hơn B vài giây do tải CPU, lệch clock hoặc lịch triển khai. Nếu A hoàn thành quá nhanh, release lock rồi B mới chạy, B có thể lấy lock và kích hoạt lại cùng kỳ.

**lockAtLeastFor** có thể giảm khả năng này trong một cửa sổ nhỏ, nhưng không bảo đảm loại bỏ mọi lượt trễ. **JobParameters xác định kỳ nghiệp vụ** và các ràng buộc ở dữ liệu đích vẫn cần thiết để bảo vệ kết quả.

### 9.2. Instance giữ lock bị kill

Khi process bị kill, đoạn code release lock có thể không chạy. Với lease lock, owner khác phải đợi **lockAtMostFor** hết hạn. Không chỉnh thủ công **lock_until** khi chưa xác định owner trước đó thực sự đã dừng; nếu owner vẫn chạy, việc ép giải phóng có thể tạo xử lý đồng thời.

### 9.3. Database chứa lock bị lỗi

Nếu database lock không khả dụng, scheduler không thể lấy hoặc gia hạn lock bình thường. Điều quan trọng là **không tự chuyển sang chạy không lock** khi kết nối lỗi. Cần log/cảnh báo rõ và lựa chọn chính sách retry thích hợp. Vì cơ chế điều phối phụ thuộc backend chung, độ sẵn sàng của backend là một phần của độ sẵn sàng scheduler.

### 9.4. Lock name không đồng nhất

Nếu A dùng **batch.dailySettlement.schedule** và B dùng **batch.daily-settlement.schedule**, hai tên tương ứng hai khóa khác nhau. Cả hai instance có thể nhận quyền chạy. Tên lock nên ổn định, được khai báo thống nhất trong cùng artifact triển khai; khi đổi tên, phải cân nhắc giai đoạn rolling deployment có phiên bản cũ và mới cùng hoạt động.

### 9.5. Khác database hoặc schema

Một instance dùng database production, instance kia dùng bản copy hoặc schema khác thì mỗi bên có bảng **shedlock** riêng. Cùng một lock name không giúp điều phối nếu không cùng store. Với môi trường multi-tenant, cần xác định lock là theo từng tenant hay theo toàn bộ Job, rồi thống nhất định danh tương ứng.

### 9.6. Job bị lỗi nhưng scheduler method trả về bình thường

Spring Batch có thể trả về **JobExecution** với **BatchStatus.FAILED** mà không ném exception ra khỏi **JobLauncher.run(...)**. ShedLock không tự quyết định retry dựa trên trạng thái nghiệp vụ. Cần quan sát **BatchStatus**, log và tạo cảnh báo; ở ví dụ phần 5, method chủ động ném exception khi Job không **COMPLETED** để thể hiện lỗi.

Dù method ném exception, lock thường được release theo vòng đời lời gọi/lease; **đừng suy luận rằng exception sẽ khiến scheduler tự thử lại ngay**. Retry và lịch khắc phục Job thất bại phải là một quyết định riêng.

### 9.7. Rolling deployment và thay đổi cron

Trong thời gian triển khai rolling, instance phiên bản mới và cũ có thể cùng tồn tại. Nếu hai phiên bản dùng cùng lock nhưng thực hiện hai loại xử lý không tương thích, việc chỉ ngăn overlap không bảo đảm dữ liệu đúng. Nếu dùng tên lock khác nhau, cả hai có thể cùng chạy. Khi thay đổi lịch hoặc businessDate logic, cần chú ý giai đoạn giao nhau của các phiên bản.

## 10. Lock không bảo đảm exactly-once

Trong hệ thống phân tán, “chỉ một scheduler lấy được lock” khác với “mỗi side effect xảy ra chính xác một lần”.

Ví dụ writer gọi API chuyển tiền:

~~~text
A acquire lock
A gửi lệnh với transactionId=T100
Hệ thống ngoài thực hiện thành công
A crash trước khi checkpoint được lưu
Lease của A hết hạn
B restart Job và gửi lại transactionId=T100
~~~

Ngay cả khi A và B **không đồng thời giữ lock**, tác dụng phụ vẫn có thể xảy ra hai lần. Bởi vậy, writer nên được thiết kế **idempotent**, chẳng hạn truyền **idempotency key** dựa trên định danh nghiệp vụ, dùng unique constraint, upsert an toàn hoặc outbox kết hợp xử lý trùng tại consumer.

Nếu tình huống nghiêm trọng yêu cầu chỉ owner mới nhất được phép ghi, có thể cần **fencing token** hoặc kiểm soát phiên bản tại nguồn dữ liệu đích. Một lease lock đơn giản có thể hết hạn và trao quyền mới khi owner cũ còn đang hoạt động; chỉ kiểm tra “đã từng lấy được lock” không đủ để chặn owner cũ tiếp tục ghi.

Ví dụ bảng kết quả có khóa duy nhất theo kỳ:

~~~sql
CREATE TABLE daily_settlement (
    business_date DATE NOT NULL,
    account_id    BIGINT NOT NULL,
    total_amount  DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, account_id)
);
~~~

Bảng này có thể ngăn insert trùng một cặp **(business_date, account_id)** nhưng vẫn cần quy tắc cập nhật và transaction chính xác. Ràng buộc unique là một lớp an toàn dữ liệu, không phải sự thay thế cho kiểm thử tính đúng đắn của Job.

## 11. Các lựa chọn khác ngoài ShedLock

### Quartz clustering

Nếu cần lịch bền vững, misfire handling, nhiều trigger, pause/resume theo lịch, lịch động hoặc khả năng chọn một node thực thi trigger trong cluster, **Quartz với JDBC JobStore được cấu hình clustered** là một lựa chọn.

Trong mô hình đó, các scheduler node dùng chung các bảng Quartz và được cấu hình nhận diện như thành viên cùng cluster. Một trigger được điều phối giữa các node. **@DisallowConcurrentExecution** có thể dùng để không chạy đồng thời các execution của cùng một Quartz JobDetail/JobKey; nó không mặc nhiên ngăn mọi JobDetail khác nhau cùng xử lý một dữ liệu nghiệp vụ. Vẫn cần mapping đúng từ trigger sang Spring Batch Job và JobParameters.

Quartz phù hợp hơn ShedLock nếu chính bài toán là **quản lý lịch một cách bền vững và phong phú**. Nếu chỉ cần một phương thức **@Scheduled** chạy một lần trong nhiều instance, ShedLock thường đơn giản hơn.

### Leader election

Một cluster có thể chọn một instance làm leader; chỉ leader kích hoạt lịch. Cách này phù hợp khi dịch vụ đã có leader election qua Kubernetes, Consul, ZooKeeper hoặc hạ tầng tương ứng. Cần xử lý tình huống đổi leader và đảm bảo owner cũ không tiếp tục thực hiện side effect sau khi mất quyền.

Leader election điều phối **vai trò của node**, còn scheduler lock điều phối **từng tác vụ**. Hai cơ chế có phạm vi và chi phí vận hành khác nhau.

### Database advisory lock hoặc row lock

Một số database hỗ trợ advisory lock, **SELECT ... FOR UPDATE** hoặc câu lệnh claim nguyên tử. Các cơ chế này có thể phù hợp khi cần giao dịch ngắn, claim một hàng công việc hoặc kiểm soát chặt dữ liệu trong chính database.

Cần hiểu vòng đời lock: có lock gắn với transaction, có lock gắn với session/connection. Khi dùng pool JDBC, sự khác biệt này rất quan trọng. Không nên giữ transaction nhiều giờ chỉ để bảo vệ một Job dài, và không nên sử dụng một advisory lock theo session rồi trả connection về pool mà chưa xác định cơ chế release.

### Kubernetes CronJob

Nếu bản chất là một Job chạy theo lịch trên Kubernetes, có thể cân nhắc chuyển lịch sang **CronJob** với chính sách concurrency phù hợp. **concurrencyPolicy: Forbid** hạn chế overlap của những Job do cùng CronJob điều khiển, nhưng không đồng bộ hóa các CronJob resource khác nhau hoặc các đường kích hoạt thủ công. Nó cũng không bảo đảm end-to-end exactly-once nếu có lỗi controller, retry hoặc side effect ngoài transaction.

| Cơ chế | Phù hợp nhất khi | Điểm cần lưu ý |
| --- | --- | --- |
| **ShedLock + @Scheduled** | Ứng dụng có cron trong từng instance, cần skip các lượt trùng | Dùng chung lock store, cấu hình lease đúng, theo dõi async/long-running Job |
| **Quartz clustered JobStore** | Cần quản lý trigger, misfire và scheduler tập trung bằng metadata | Cấu hình JDBC clustering và lifecycle Quartz |
| **Leader election** | Cluster đã có cơ chế leader, nhiều công việc do leader điều phối | Chuyển leader, fencing và trạng thái owner cũ |
| **DB lock / claim** | Muốn claim một bản ghi, kỳ xử lý hoặc công việc trong database | Transaction/connection scope và khả năng recovery |
| **Kubernetes CronJob** | Batch chạy theo mô hình Job riêng trên Kubernetes | Concurrency policy chỉ trong phạm vi CronJob được quản lý |

## 12. Cách kiểm tra thực sự chỉ một scheduler được chạy

Một unit test gọi phương thức scheduler trực tiếp thường **không chứng minh distributed lock hoạt động**, vì annotation có thể chỉ được kích hoạt qua Spring proxy và còn cần một backend dùng chung. Một integration test đáng tin cậy nên mô phỏng tối thiểu **hai scheduler instance** hoặc hai application context độc lập cùng dùng một bảng lock.

### Kịch bản 1: hai scheduler cùng kích hoạt một kỳ

Chuẩn bị:

- Cả A và B cấu hình cùng **LockProvider**, bảng **shedlock** và lock name.
- Cả hai cùng tính **businessDate** từ một kỳ cố định.
- Job chạy đủ lâu để hai yêu cầu có thể tranh lock; có thể dùng **CountDownLatch** để điều phối thay vì **Thread.sleep**.
- Dữ liệu đích có khóa nghiệp vụ và có ghi nhận số lần tác vụ bắt đầu.

Thực hiện:

~~~text
T0:  Khởi động scheduler A và B
T1:  Cho cả hai đến điểm acquire cùng lock
T2:  A acquire thành công; B không acquire
T3:  A thực thi Job
T4:  A hoàn tất và release lock
~~~

Kỳ vọng: **một lần thực thi phương thức được bảo vệ** có quyền chạy trong khoảng tranh lock, và kết quả nghiệp vụ đúng với dữ liệu đầu vào. Không nên khẳng định A luôn thắng; B có thể thắng tùy thứ tự scheduling.

### Kịch bản 2: instance chết giữa Job

A lấy lock rồi process bị dừng trước khi release. Kiểm tra rằng B không chạy chồng ngay lập tức trong lúc lease còn hiệu lực. Khi hết thời hạn, B có thể giành lock trong lượt tiếp theo, và quy trình xử lý/restart dựa trên JobRepository vẫn giữ dữ liệu đúng.

Với test kiểu này, đặt lease ngắn **chỉ trong môi trường kiểm thử được cách ly** để không phải chờ thời gian production. Không chỉnh thủ công mốc lease trong database production để “tạo điều kiện” kiểm thử.

### Kịch bản 3: Job chạy lâu hơn lease

Giữ A chạy vượt **lockAtMostFor** và cho B thử acquire. Mục tiêu là quan sát được rủi ro **hai owner theo thời gian**, sau đó xác nhận lớp bảo vệ bổ sung của JobRepository, JobParameters và dữ liệu đích xử lý tình huống này ra sao.

Test này có ý nghĩa đặc biệt khi Job có thời lượng không dự đoán được. Nếu thiết kế dựa vào gia hạn lease, cần kiểm tra cả trường hợp mất kết nối đến backend lock khi gia hạn.

### Kịch bản 4: lỗi sau side effect

Cho writer ghi thành công vào đích nhưng lỗi trước checkpoint, rồi thực hiện lại cùng kỳ. Xác minh writer/đích có xử lý idempotent, không tạo thêm bản ghi hay gửi lệnh trùng. Kịch bản này không chỉ kiểm thử scheduler lock mà còn kiểm thử tính an toàn khi hệ thống khôi phục.

## 13. Vận hành, log và cảnh báo

Để dễ phát hiện tác vụ bỏ lỡ lịch hoặc lock quá hạn, nên ghi nhận những thông tin sau cho mỗi kỳ chạy:

| Trường quan sát | Cách sử dụng |
| --- | --- |
| **Job name** | Tên Spring Batch Job được kích hoạt |
| **Lock name** | Xác định tác vụ nào đang được điều phối |
| **Business period** | Ngày hoặc cửa sổ dữ liệu mà Job xử lý |
| **JobInstance/JobExecution ID** | Đối chiếu với bảng metadata của Spring Batch |
| **Instance/pod ID** | Biết node nào nhận quyền và thực hiện Job |
| **Start/end time, duration** | Theo dõi thời lượng thực tế để chọn lease phù hợp |
| **BatchStatus, ExitStatus** | Xác định hoàn thành, thất bại, dừng hoặc kết thúc tùy chỉnh |
| **Số lượt bỏ qua vì lock** | Phân biệt cron có kích hoạt nhưng không giành được lock |
| **Lần xử lý thành công gần nhất của từng kỳ** | Phát hiện bỏ sót hoặc thất bại chưa được retry |

Các hàng trong **shedlock** phản ánh tình trạng lease, **không phải lịch sử thực thi nghiệp vụ hoàn chỉnh**. Không dùng **lock_until** để suy ra Job đã thực sự hoàn thành. Nên theo dõi JobRepository, dữ liệu đích và hệ thống monitoring riêng.

Có thể tạo cảnh báo khi:

- Không có JobExecution thành công sau một deadline nghiệp vụ.
- Thời lượng Job tiến sát **lockAtMostFor**.
- Lease thường xuyên hết hạn khi Job còn hoạt động.
- Một kỳ xử lý xuất hiện nhiều lần ghi kết quả hoặc nhiều JobInstance bất thường.
- Database lock không khả dụng hoặc số lần acquire thất bại tăng bất thường.

**Lock skip** là hành vi được mong đợi khi nhiều instance cùng tranh một lịch. Nhưng nếu tất cả các lượt đều bị skip trong thời gian dài, có thể có lock bị giữ lâu, instance bị treo hoặc lease được cấu hình không phù hợp.

## 14. Một số sai lầm cần tránh

### Dùng synchronized để khóa nhiều pod

~~~java
@Scheduled(cron = "0 0 * * * *")
public synchronized void runBatch() {
    // ...
}
~~~

**synchronized** chỉ đồng bộ các thread truy cập **cùng monitor trong một JVM**. Hai pod có hai JVM độc lập nên vẫn có thể chạy song song.

### Tạo lock name theo instance ID

~~~java
// Ví dụ sai về mặt ý tưởng:
String lockName = "dailySettlement-" + podName;
~~~

Mỗi pod dùng một tên khác nhau nghĩa là mỗi pod sở hữu một lock khác nhau. Tên lock phải mô tả **công việc chung**, không mô tả instance; thông tin pod nên dùng cho trường **locked_by** hoặc log.

### Giải phóng lock khi mới submit Job bất đồng bộ

Chỉ khóa quanh lời gọi submit không đủ nếu yêu cầu không có hai Job cùng hoạt động. Cần làm rõ lúc nào công việc được coi là kết thúc và áp dụng bảo vệ theo đúng vòng đời.

### Tự tạo identifying run ID khác nhau ở mọi pod

Việc này biến cùng một kỳ nghiệp vụ thành nhiều JobInstance. Dùng **businessDate/windowStart** theo kỳ đã chuẩn hóa để JobRepository có thể phân biệt chạy trùng với restart.

### Xem lease lock là exactly-once

Lease có thể hết hạn, side effect có thể hoàn thành trước checkpoint và scheduler có thể kích hoạt lại. Phải xem **idempotency** là trách nhiệm ở tầng nghiệp vụ và writer.

### Dùng chung lock name cho hai tác vụ không liên quan

Nếu Job A và Job B cùng tên lock mà không có chủ đích, chúng sẽ ngăn lẫn nhau. Nên đặt tên khóa theo **chức năng được bảo vệ** và định nghĩa rõ phạm vi của nó.

## 15. Checklist áp dụng cho nhiều scheduler instance

- [ ] Tất cả instance chạy lịch đều dùng **cùng backend lock và cùng lock name** cho một công việc.
- [ ] Bảng lock đã được tạo qua migration, có khóa chính và được quản lý tập trung.
- [ ] Sử dụng clock nhất quán; với JDBC ShedLock cân nhắc **usingDbTime()**.
- [ ] **lockAtMostFor** dựa trên thời lượng Job thực tế cộng dự phòng; có phương án nếu Job quá dài.
- [ ] **lockAtLeastFor** phù hợp độ lệch lịch nhỏ, không được dùng để che lỗi định danh Job.
- [ ] Phương thức được lock do Spring quản lý, annotation được áp dụng qua cơ chế phù hợp.
- [ ] Nếu cần lock suốt thời gian Job xử lý, **JobLauncher thực sự đồng bộ** hoặc có orchestration thay thế.
- [ ] Identifying **JobParameters** nhất quán theo kỳ nghiệp vụ và được tái sử dụng đúng khi restart.
- [ ] Những đường launch không đi qua cron đã có chính sách đồng thời rõ ràng.
- [ ] Writer và bảng đích có lớp chống trùng/idempotency khi xảy ra crash hoặc retry.
- [ ] Có test ít nhất hai instance tranh lock, mất owner, hết lease và recovery.
- [ ] Có metric/log theo kỳ chạy để nhận biết scheduler bị skip, Job thất bại hoặc chậm bất thường.

Khi triển khai Spring Batch với nhiều scheduler instance, thiết kế đáng tin cậy thường gồm **distributed lock để chọn instance được kích hoạt**, **JobRepository để quản lý JobInstance và restart**, và **quy tắc idempotent để bảo vệ kết quả nghiệp vụ**. Cả ba lớp cùng có vai trò: lock giảm tranh chấp khi cron được kích hoạt từ nhiều JVM, JobRepository quản lý vòng đời Batch Job, còn kiểm soát dữ liệu đích bảo vệ hệ thống trước crash, retry và những tình huống lease không thể loại bỏ hoàn toàn.

