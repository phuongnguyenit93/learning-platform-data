# Đọc thông tin Quartz job, trigger và dữ liệu đã được che

## 1. Hiểu đúng công việc, lịch kích hoạt và dữ liệu

Khi một báo cáo không được tạo đúng giờ, có ít nhất ba câu hỏi khác nhau: công việc đã được đăng ký chưa, lịch nào sẽ kích hoạt công việc, và công việc nhận dữ liệu gì? Endpoint `quartz` của Spring Boot Actuator giúp đọc thông tin từ Quartz Scheduler đang được ứng dụng sử dụng.

Trong Quartz, các khái niệm được tách rõ:

| Khái niệm | Vai trò | Ví dụ trong bài |
| --- | --- | --- |
| `Job` | Mã thực hiện công việc qua phương thức `execute`. | `ReportJob` |
| `JobDetail` | Định nghĩa một công việc cụ thể: khóa, lớp thực thi và dữ liệu. | Nhóm `reporting`, tên `report` |
| `Trigger` | Lịch quyết định khi nào kích hoạt công việc. | Mỗi 30 giây hoặc đầu mỗi phút |
| `JobDataMap` | Dữ liệu gắn với định nghĩa công việc hoặc lịch kích hoạt. | `channel`, `apiToken` |
| `Scheduler` | Thành phần quản lý và thực thi các đăng ký Quartz. | Bộ lập lịch được Boot cấu hình |

Một công việc có thể được nhiều trigger kích hoạt; một trigger trỏ đến một công việc. Khóa được tạo từ **nhóm và tên**, nên chỉ biết tên là chưa đủ để chọn chính xác đối tượng. Nhóm của trigger cũng có thể khác nhóm của công việc. [Quartz: Jobs, Triggers và định danh](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-02.html)

Phạm vi bài là **đọc endpoint `quartz` trên Spring Boot 3.3.x**, kèm cách hiểu dữ liệu bị thay bằng `******`. Ví dụ dùng Java 21 và Boot `3.3.13` để có phiên bản đối chiếu cụ thể.

## 2. Điều kiện để đọc được endpoint

Ứng dụng cần Actuator, Quartz và một `Scheduler` được cấu hình phù hợp. Khi dùng `spring-boot-starter-quartz`, Boot có thể tự cấu hình `Scheduler` thông qua `SchedulerFactoryBean`; các bean `JobDetail` và `Trigger` được đưa vào bộ lập lịch. Mặc định kho công việc nằm trong bộ nhớ. [Tích hợp Quartz của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/io/quartz.html)

Cần phân biệt ba lớp:

1. **Sự hiện diện:** ứng dụng có hạ tầng Quartz để endpoint quan sát.
2. **Khả năng truy cập:** endpoint được bật, công khai qua HTTP và người gọi vượt qua kiểm soát truy cập.
3. **Khả năng xem giá trị gốc:** chính sách che dữ liệu cho phép người gọi xem phần `data` hay chỉ thấy `******`.

Đọc được JSON không đồng nghĩa được xem dữ liệu gốc. Ngược lại, thay đổi chính sách hiển thị giá trị cũng không tự công khai endpoint qua HTTP.

## 3. Dự án thực hành độc lập

### 3.1. Tạo cấu trúc và cấu hình Gradle

Chuẩn bị JDK 21 và Gradle 8.5. Tạo các tệp sau trong một dự án thực hành riêng:

```text
quartz-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/sample/quartz/
    │   ├── QuartzReadApplication.java
    │   ├── ReportJob.java
    │   └── QuartzJobs.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'quartz-read-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
}

application {
    mainClass = 'sample.quartz.QuartzReadApplication'
}
```

Plugin `application` cung cấp lệnh chạy; BOM của Boot đồng bộ phiên bản thư viện. Dự án sử dụng bộ nhớ để lưu lịch, nên không cần cấu hình cơ sở dữ liệu cho thí nghiệm này.

### 3.2. Lớp khởi động và mã công việc

`src/main/java/sample/quartz/QuartzReadApplication.java`:

```java
package sample.quartz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuartzReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuartzReadApplication.class, args);
    }
}
```

`src/main/java/sample/quartz/ReportJob.java`:

```java
package sample.quartz;

import org.quartz.Job;
import org.quartz.JobExecutionContext;

public class ReportJob implements Job {
    @Override
    public void execute(JobExecutionContext context) {
        String channel = context.getMergedJobDataMap().getString("channel");
        System.out.println("report:" + channel);
    }
}
```

`JobExecutionContext.getMergedJobDataMap()` hợp nhất dữ liệu của công việc và trigger đang kích hoạt. Khi trùng khóa, giá trị từ trigger được ưu tiên. Endpoint chi tiết công việc và endpoint chi tiết trigger cho phép xem hai nguồn dữ liệu riêng, còn đoạn mã trên đọc dữ liệu hợp nhất của một lần thực thi. [Javadoc JobExecutionContext](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobExecutionContext.html)

### 3.3. Một công việc, hai lịch kích hoạt

`src/main/java/sample/quartz/QuartzJobs.java`:

```java
package sample.quartz;

import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.SimpleTrigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QuartzJobs {

    @Bean
    public JobDetail reportJob() {
        return JobBuilder.newJob(ReportJob.class)
                .withIdentity("report", "reporting")
                .withDescription("Creates a demo report")
                .usingJobData("channel", "job-default")
                .usingJobData("apiToken", "demo-token-not-a-secret")
                .storeDurably()
                .build();
    }

    @Bean
    public SimpleTrigger every30Seconds(JobDetail reportJob) {
        return TriggerBuilder.newTrigger()
                .withIdentity("every30Seconds", "ops")
                .forJob(reportJob)
                .usingJobData("channel", "simple-trigger")
                .startNow()
                .withSchedule(SimpleScheduleBuilder.simpleSchedule()
                        .withIntervalInSeconds(30)
                        .repeatForever())
                .build();
    }

    @Bean
    public CronTrigger minuteReport(JobDetail reportJob) {
        return TriggerBuilder.newTrigger()
                .withIdentity("minuteReport", "calendar")
                .forJob(reportJob)
                .usingJobData("source", "minute-clock")
                .withSchedule(CronScheduleBuilder.cronSchedule("0 * * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh")))
                .build();
    }
}
```

Giá trị `apiToken` là dữ liệu giả để quan sát việc che dữ liệu. Mã công việc chỉ in `channel`.

Các định danh đã tạo:

```text
JobKey: reporting / report
    <- TriggerKey: ops / every30Seconds
    <- TriggerKey: calendar / minuteReport
```

`storeDurably()` giữ định nghĩa công việc khi không còn trigger tham chiếu. Nó không tự biến kho trong bộ nhớ thành kho bền qua lần khởi động lại; việc chọn kho lưu trữ và việc giữ một công việc không còn trigger là hai quyết định khác nhau. [Hợp đồng JobDetail](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html)

### 3.4. Công khai endpoint cho thí nghiệm cục bộ

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,quartz
management.endpoint.quartz.show-values=never
```

`quartz` mặc định được bật trong Boot 3.3, nhưng HTTP mặc định chỉ công khai `health`. Nếu ứng dụng đã tắt mặc định toàn bộ endpoint, cần bật riêng bằng `management.endpoint.quartz.enabled=true`. Cấu hình `exposure.exclude` có ưu tiên hơn `include`. [Quy tắc bật và công khai endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Dự án thực hành không thêm Spring Security và chỉ lắng nghe loopback. Khi áp dụng vào hệ thống thật, cấu hình quyền truy cập endpoint theo cơ chế bảo mật của ứng dụng; dữ liệu bị che vẫn có thể để lộ tên lớp, tên công việc, tên khóa và thời gian chạy.

Tại thư mục dự án, dùng Gradle 8.5 đã cài:

```shell
gradle run
```

Nếu đã có Gradle Wrapper phù hợp, có thể dùng `./gradlew run` hoặc `.\gradlew.bat run`. Sau khi ứng dụng khởi động, giữ tiến trình chạy để gửi các yêu cầu đọc từ terminal khác.

Với trigger `ops/every30Seconds`, mỗi lần gọi công việc in:

```text
report:simple-trigger
```

Với trigger `calendar/minuteReport`, mỗi lần gọi công việc in:

```text
report:job-default
```

Giá trị thứ hai dùng dữ liệu của công việc vì cron trigger không định nghĩa lại `channel`. Console còn chứa log khởi động; thời điểm và thứ tự xen kẽ các dòng phụ thuộc lịch thực thi.

## 4. Đi từ danh sách đến đúng đối tượng

Các yêu cầu dưới đây đều dùng **GET**. Trên PowerShell, dùng `curl.exe` nếu `curl` đang trỏ đến một lệnh khác.

| Đường dẫn sau `/actuator/quartz` | Thông tin cần đọc |
| --- | --- |
| Không có phần bổ sung | Các nhóm công việc và nhóm trigger |
| `/jobs` | Tên công việc theo từng nhóm |
| `/triggers` | Tên trigger theo từng nhóm |
| `/jobs/{group}` | Các công việc trong một nhóm |
| `/triggers/{group}` | Các trigger trong một nhóm |
| `/jobs/{group}/{name}` | Chi tiết một công việc và các trigger liên quan |
| `/triggers/{group}/{name}` | Chi tiết một trigger |

Đây là các đường dẫn đọc của [API Quartz trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html). Khi đổi base path hoặc cổng quản trị, thay URL tương ứng.

### 4.1. Xem nhóm trước

```shell
curl -i http://127.0.0.1:8080/actuator/quartz
```

Phần thân phản hồi mong đợi của dự án thực hành:

```json
{
  "jobs": {
    "groups": ["reporting"]
  },
  "triggers": {
    "groups": ["calendar", "ops"]
  }
}
```

Không dựa vào thứ tự các nhóm để xác định ý nghĩa. `reporting` là nhóm công việc; `calendar` và `ops` là hai nhóm trigger. Cùng một từ `groups` nhưng ở hai nhánh dữ liệu khác nhau.

### 4.2. Xem tên và quan hệ công việc–trigger

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/jobs
curl -i http://127.0.0.1:8080/actuator/quartz/triggers
curl -i http://127.0.0.1:8080/actuator/quartz/jobs/reporting
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/ops
```

Phản hồi của `/jobs` có nhánh sau:

```json
{
  "groups": {
    "reporting": {
      "jobs": ["report"]
    }
  }
}
```

Tiếp tục đọc công việc cụ thể:

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/jobs/reporting/report
```

Các trường ổn định cần chú ý được trích ra như sau; phản hồi đầy đủ còn có thời điểm kích hoạt trong từng phần tử `triggers`:

```json
{
  "group": "reporting",
  "name": "report",
  "description": "Creates a demo report",
  "className": "sample.quartz.ReportJob",
  "durable": true,
  "requestRecovery": false,
  "data": {
    "channel": "******",
    "apiToken": "******"
  },
  "triggers": [
    {"group": "ops", "name": "every30Seconds"},
    {"group": "calendar", "name": "minuteReport"}
  ]
}
```

Đây là bản trích có chủ đích, không phải toàn bộ JSON nguyên trạng. Thứ tự các trigger phụ thuộc thời điểm đọc. Định nghĩa công việc cho biết lớp thực thi; hai khóa trigger dẫn bạn đến đúng lịch cần kiểm tra.

## 5. Đọc chi tiết công việc và lịch kích hoạt

### 5.1. Những điều có thể kết luận từ công việc

Trong ví dụ, `className` trỏ đến `sample.quartz.ReportJob`; khóa của công việc là `reporting/report`. `data` là dữ liệu gắn với `JobDetail`, còn danh sách `triggers` cho biết những lịch đang liên kết với công việc.

Hai cờ thường bị hiểu sai:

- `durable=true`: công việc có thể được giữ lại khi không còn trigger tham chiếu. Muốn biết có tồn tại qua lần khởi động lại hay không, phải kiểm tra loại kho lưu trữ.
- `requestRecovery=true`: yêu cầu cơ chế phục hồi của Quartz xem xét thực thi lại khi xảy ra tình huống phục hồi/chuyển đổi sau sự cố. Đây không phải cấu hình tự thử lại mọi ngoại lệ nghiệp vụ.

Ý nghĩa hai cờ đến từ [hợp đồng JobDetail](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html). Với ví dụ, `requestRecovery` giữ giá trị mặc định `false`.

`triggers: []` không tự chứng minh định nghĩa công việc bị lỗi. Một công việc được giữ lại có thể đang chờ gắn lịch mới. Hãy đối chiếu mục đích cấu hình trước khi kết luận.

### 5.2. Đọc SimpleTrigger

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/ops/every30Seconds
```

Phần giá trị ổn định của phản hồi được trích ra như sau:

```json
{
  "group": "ops",
  "name": "every30Seconds",
  "type": "simple",
  "data": {
    "channel": "******"
  },
  "simple": {
    "interval": 30000,
    "repeatCount": -1
  }
}
```

Phản hồi đầy đủ còn có `state`, các thời điểm và `simple.timesTriggered`. Cách đọc phần `simple`:

- `interval=30000`: khoảng lặp là 30.000 mili giây.
- `repeatCount=-1`: lặp vô hạn trong cấu hình ví dụ.
- `timesTriggered`: số lần trigger đã kích hoạt; giá trị thay đổi theo thời điểm đọc.

Đây là thông tin của lịch kích hoạt, không phải bộ đếm số báo cáo thành công. Nếu cấu hình số lần lặp hữu hạn là `2`, lịch có một lần đầu và hai lần lặp, tổng cộng ba lần dự kiến khi không có yếu tố khác làm thay đổi lịch. [API SimpleTrigger](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/SimpleTrigger.html)

Không dùng `timesTriggered` làm lịch sử kiểm toán nghiệp vụ lâu dài; nó gắn với trigger hiện tại và có thể thay đổi khi trigger được thay thế hoặc lịch được khởi tạo lại.

### 5.3. Đọc CronTrigger

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/calendar/minuteReport
```

Phần mô tả cron của dự án thực hành:

```json
{
  "type": "cron",
  "data": {
    "source": "******"
  },
  "cron": {
    "expression": "0 * * * * ?",
    "timeZone": "Asia/Ho_Chi_Minh"
  }
}
```

Ở đây, `expression` chọn giây 0 của mỗi phút. Đọc cả `timeZone` khi phân tích lịch theo giờ địa phương. Múi giờ dùng để giải lịch và phần chênh lệch UTC trong chuỗi thời gian trả về là hai thông tin cần được phân biệt khi so sánh.

Quartz còn có các loại trigger `dailyTimeInterval`, `calendarInterval` và `custom`. Khi đọc phản hồi chi tiết, dùng `type` để chọn đúng object chứa thuộc tính riêng; đừng áp dụng cấu trúc `simple` cho mọi loại. [Các loại phản hồi trigger của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html)

### 5.4. Đọc thời điểm và trạng thái mà không suy diễn quá mức

| Trường | Câu hỏi nó giúp trả lời |
| --- | --- |
| `startTime`, `endTime` | Lịch bắt đầu có hiệu lực và dừng lặp khi nào? |
| `previousFireTime` | Lần kích hoạt trước là lúc nào, nếu có? |
| `nextFireTime` | Thời điểm kích hoạt tiếp theo dự kiến là khi nào? |
| `priority` | Mức ưu tiên khi các trigger có cùng mốc kích hoạt? |
| `calendarName` | Có lịch loại trừ Quartz Calendar nào được gắn không? |

Các trường có điều kiện có thể vắng mặt khi chưa có giá trị. Một trigger mới chưa kích hoạt có thể chưa có `previousFireTime`; lịch đã hết lượt có thể không còn `nextFireTime`. Việc có mốc chạy trước không chứng minh lần chạy đó hoàn thành thành công. Các thời điểm là thông tin từ trigger tại lúc quan sát. [API Trigger](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Trigger.html)

`state` là trạng thái của **trigger**, không phải kết quả nghiệp vụ của công việc. Các giá trị Quartz định nghĩa gồm `NONE`, `NORMAL`, `PAUSED`, `COMPLETE`, `ERROR`, `BLOCKED`. [TriggerState](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Trigger.TriggerState.html)

Cách dùng chúng trong chẩn đoán:

- `NORMAL`: tiếp tục đối chiếu thời điểm dự kiến và bằng chứng thực thi; không tự kết luận công việc đang chạy.
- `PAUSED`: kiểm tra lịch hoặc nhóm có đang bị tạm dừng theo chủ đích.
- `COMPLETE`: kiểm tra lịch đã hết các lần kích hoạt hay đạt giới hạn thời gian; không coi tên trạng thái này là chứng nhận xử lý nghiệp vụ thành công.
- `ERROR`: cần điều tra lỗi ở cơ chế lập lịch và log liên quan; phản hồi không cung cấp đầy đủ nguyên nhân ngoại lệ.
- `BLOCKED`: kiểm tra điều kiện chặn thực thi, chẳng hạn công việc được cấu hình không chạy đồng thời đang có một lần chạy khác.

Endpoint không thay thế lịch sử thực thi, log hay số liệu nghiệp vụ. Khi `nextFireTime` khác kỳ vọng, còn phải xem xét múi giờ, khoảng hiệu lực, lịch loại trừ và cách xử lý lần kích hoạt bị lỡ.

## 6. Hiểu đúng dữ liệu đã được che

### 6.1. `******` có nghĩa gì?

Với `management.endpoint.quartz.show-values=never`, các giá trị trong phần dữ liệu công việc/trigger được thay bằng `******` khi trả ra endpoint. Việc che mặc định không chỉ dựa vào tên khóa giống mật khẩu. Vì vậy cả `channel`, `source` và `apiToken` của ví dụ đều bị che. Giá trị mặc định của thuộc tính này là `never`. [Thuộc tính Quartz endpoint](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.quartz.show-values)

Từ một phản hồi đã che, bạn vẫn đọc được **khóa nào có mặt**, nhưng không thể kết luận hai giá trị gốc có bằng nhau hay giá trị gốc đang rỗng. Chẳng hạn `channel` trong dữ liệu công việc và `channel` trong trigger đều hiện `******`, dù ví dụ đã gán hai chuỗi khác nhau.

Việc che là biến đổi ở **đầu ra quản trị**. Nó không mã hóa kho Quartz, không sửa `JobDataMap` gốc và không bảo đảm các đường ghi log khác cũng che dữ liệu. Bằng chứng ngay trong thí nghiệm: endpoint hiện `******`, còn `execute` vẫn đọc chuỗi `channel` thật để in kết quả.

### 6.2. Ba chế độ hiển thị

| `management.endpoint.quartz.show-values` | Cách hiển thị giá trị gốc |
| --- | --- |
| `never` | Luôn che giá trị. |
| `when-authorized` | Chỉ cho người gọi đủ điều kiện xem giá trị gốc. |
| `always` | Cho mọi người đã truy cập được endpoint xem giá trị gốc, trừ phần vẫn bị hàm che tùy chỉnh xử lý. |

Hàm `SanitizingFunction` tùy chỉnh vẫn có thể che những giá trị mà nó xử lý, kể cả khi chính sách cho xem dữ liệu gốc. Chính sách hiển thị không phải cách vượt qua các hàm che đó. [Cơ chế che dữ liệu của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization)

Để yêu cầu một vai trò cụ thể trên **ứng dụng đã có xác thực HTTP và cấu hình cấp quyền truy cập endpoint**, có thể dùng:

```properties
management.endpoint.quartz.show-values=when-authorized
management.endpoint.quartz.roles=QUARTZ_ADMIN
```

Đoạn cấu hình này chỉ minh họa chính sách xem dữ liệu. Nó không tự tạo người dùng hoặc cấu hình Spring Security. `roles` là danh sách vai trò dùng cho quyết định hiển thị giá trị gốc; khi danh sách rỗng, mọi người dùng đã xác thực đều được xem theo chế độ `when-authorized`. [Thuộc tính roles của Quartz](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.quartz.roles)

Vì vậy, cần đánh giá hai quyết định theo đúng thứ tự:

```text
Người gọi có được truy cập endpoint không?
    -> nếu không: cơ chế bảo mật từ chối yêu cầu
    -> nếu có: xét chính sách show-values và vai trò
        -> đủ điều kiện: xem các giá trị không còn bị hàm tùy chỉnh che
        -> chưa đủ điều kiện: vẫn có thể nhận JSON với data bị che
```

Ví dụ, nếu cơ chế bảo mật cho phép một tài khoản đọc endpoint nhưng tài khoản thiếu `QUARTZ_ADMIN`, chế độ `when-authorized` có thể vẫn trả HTTP 200 cùng các giá trị `******`. Nếu cơ chế bảo mật chặn ngay quyền đọc, yêu cầu nhận phản hồi từ chối thay vì đi tới bước hiển thị này.

### 6.3. Quan sát dữ liệu của hai nguồn

Khi được phép xem giá trị gốc và không có hàm che tùy chỉnh áp dụng, phần `data` của ví dụ cho thấy:

```text
GET .../jobs/reporting/report
  channel = job-default
  apiToken = demo-token-not-a-secret

GET .../triggers/ops/every30Seconds
  channel = simple-trigger

GET .../triggers/calendar/minuteReport
  source = minute-clock
```

Các dòng trên là cách trình bày quan hệ dữ liệu, không phải stdout nguyên trạng của `curl`. Chúng giải thích vì sao công việc đọc được `simple-trigger` khi SimpleTrigger kích hoạt nhưng đọc `job-default` khi CronTrigger kích hoạt.

Trong một môi trường thật, chỉ đưa những giá trị cần cho chẩn đoán tới người có quyền phù hợp. Khả năng đọc dữ liệu gốc không làm việc sao chép chúng vào log, ảnh chụp màn hình hoặc báo cáo công khai trở nên phù hợp.

## 7. Chẩn đoán theo hiện tượng

| Hiện tượng | Kiểm tra tiếp theo |
| --- | --- |
| 404 ở `/actuator/quartz` | Đúng ứng dụng, cổng/base path, hạ tầng Quartz, bật endpoint và HTTP exposure chưa? |
| Tìm thấy nhóm nhưng không thấy đối tượng mong đợi | Dùng đúng nhóm và tên của công việc/trigger chưa? |
| 401 hoặc 403 | Xác thực và quyền truy cập HTTP endpoint đang được cấu hình thế nào? |
| 200 nhưng `data` toàn `******` | Kiểm tra `show-values`, vai trò người gọi và hàm che tùy chỉnh. |
| Công việc có mặt nhưng chưa có báo cáo | Đối chiếu trigger, thời điểm, trạng thái, log và kết quả dữ liệu. |
| Mất các đăng ký động sau khởi động lại | Kiểm tra kho lưu trong bộ nhớ hay JDBC và cơ chế đăng ký lại. |
| Có `previousFireTime` nhưng xử lý thất bại | Đọc log/lịch sử của lần chạy; mốc kích hoạt không phải kết quả thành công. |

Đối với tên nhóm/tên đối tượng có ký tự đặc biệt, mã hóa đúng từng thành phần đường dẫn URL. Không tự bỏ nhóm và thử theo tên đơn vì điều đó có thể hướng việc điều tra sang một đối tượng khác.

Khi triển khai nhiều bản sao ứng dụng, xác định bạn đang đọc bộ lập lịch nào. Một phản hồi không tự mô tả toàn bộ các lịch riêng của mọi bản sao. Nếu dùng Quartz với JDBC và cấu hình cụm, cần kiểm tra cấu hình chia sẻ kho và cơ chế cụm thực tế trước khi suy ra khả năng phối hợp.

Với dự án thực hành, kho trong bộ nhớ được tạo lại khi chạy ứng dụng. Các bean cấu hình lại tạo công việc và trigger, còn các thay đổi động ngoài cấu hình đó không tự được giữ lại. `durable=true` của `JobDetail` không thay đổi thực tế này.

## 8. Bài thực hành kiểm chứng

1. Chạy dự án, gọi endpoint gốc rồi xác định đúng nhóm công việc `reporting` và hai nhóm trigger `ops`, `calendar`.
2. Đọc chi tiết `reporting/report`, lần theo hai khóa trigger và kiểm tra loại `simple`/`cron` tương ứng.
3. Xác minh SimpleTrigger có `interval=30000`, `repeatCount=-1`; cron có biểu thức `0 * * * * ?` và múi giờ `Asia/Ho_Chi_Minh`.
4. Giữ `show-values=never`, đọc dữ liệu của công việc và cả hai trigger. Giải thích tại sao khóa thông thường `channel` cũng bị che.
5. Đối chiếu console: mỗi lần SimpleTrigger gọi công việc in `report:simple-trigger`; mỗi lần CronTrigger gọi công việc in `report:job-default`. Giải thích quy tắc ưu tiên dữ liệu của trigger.
6. Đổi khoảng lặp trong mã từ 30 giây thành 45 giây, dừng rồi chạy lại. Kiểm tra `simple.interval=45000` và tiếp tục xác minh dữ liệu vẫn được che.

Nếu cần thí nghiệm chính sách xem giá trị gốc trong môi trường có xác thực, kiểm tra hai tài khoản đã được phép đọc endpoint nhưng có vai trò khác nhau. Đối chiếu cả mã HTTP lẫn phần `data`, rồi đưa cấu hình về chính sách phù hợp sau thí nghiệm.

Các câu hỏi tự kiểm tra:

- Vì sao một công việc có hai trigger nhưng chỉ có một `JobDetail`?
- `durable=true` có bảo đảm lịch còn nguyên sau khi tắt JVM không?
- `previousFireTime` có chứng minh báo cáo đã được tạo thành công không?
- Hai giá trị cùng hiện `******` có nhất thiết bằng nhau không?
- Người đọc được endpoint có nhất thiết được xem dữ liệu gốc không?

Câu trả lời cần dựa trên quan hệ công việc–trigger, loại kho lưu trữ, bằng chứng thực thi và chính sách hiển thị dữ liệu; tên trạng thái hoặc một chuỗi đã che không thay thế các bằng chứng đó.
