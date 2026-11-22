# Đọc tác vụ đã lên lịch bằng endpoint `scheduledtasks`

## 1. Từ câu hỏi vận hành đến thông tin cần đọc

Giả sử ứng dụng có tác vụ làm mới bộ nhớ đệm mỗi 10 giây và dọn dữ liệu tạm sau mỗi lần xử lý. Khi triển khai, bạn muốn kiểm tra: Spring đã nhận lịch nào, phương thức nào gắn với lịch đó, và khoảng thời gian thực tế sau khi đọc cấu hình là bao nhiêu?

`scheduledtasks` là endpoint tích hợp của Actuator giúp xem các tác vụ được hạ tầng lập lịch của Spring cung cấp cho endpoint. Trọng tâm của bài là đọc thông tin đăng ký lịch trong ứng dụng đang chạy. Một phương thức có mặt trong danh sách chưa chứng minh rằng lần xử lý gần nhất đã thành công. API của `ScheduledTasksEndpoint` công bố thao tác đọc qua `@ReadOperation`. [Javadoc Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

Ba khái niệm cần phân biệt:

- **Tác vụ (task):** phần công việc cần thực hiện, chẳng hạn phương thức `refreshCache()`.
- **Bộ lập lịch (scheduler):** thành phần bố trí thời điểm thực thi công việc.
- **Điều kiện kích hoạt (trigger):** quy tắc xác định khi nào đến lượt chạy, chẳng hạn biểu thức cron.

Ví dụ và cấu trúc phản hồi trong bài áp dụng cho **Spring Boot 3.3.x, Java 21**; dự án thực hành ghim Boot `3.3.13` để đối chiếu đúng tài liệu phiên bản. Khi dùng nhánh Boot khác, đọc tài liệu API của chính nhánh đó trước khi viết bộ phân tích JSON.

## 2. Dữ liệu được thu thập như thế nào?

Luồng thông thường với `@Scheduled`:

```text
Bean có phương thức @Scheduled
    -> @EnableScheduling bật xử lý annotation
    -> Spring đăng ký tác vụ với hạ tầng lập lịch
    -> ScheduledTaskHolder cung cấp những tác vụ đã đăng ký
    -> ScheduledTasksEndpoint tạo mô tả
    -> GET /actuator/scheduledtasks trả JSON
```

`ScheduledAnnotationBeanPostProcessor` xử lý các phương thức có `@Scheduled`, đồng thời tham gia hợp đồng `ScheduledTaskHolder`. Thành phần này còn thu thập các đăng ký qua `SchedulingConfigurer`. Vì vậy, nguồn dữ liệu có thể bao gồm cả lịch khai báo bằng annotation và lịch đăng ký bằng mã thông qua hạ tầng tương ứng. [Javadoc bộ xử lý `@Scheduled`](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html)

Cấu hình tự động của endpoint nhận các `ScheduledTaskHolder` từ Spring. Có thể suy ra giới hạn quan trọng: một luồng nền hoặc một `ScheduledExecutorService` tự tạo sẽ không tự xuất hiện chỉ vì nó đang chạy trong cùng JVM; tác vụ phải được cung cấp qua hợp đồng mà endpoint đọc. [Cấu hình tự động của `scheduledtasks`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/scheduling/ScheduledTasksEndpointAutoConfiguration.html)

## 3. Ví dụ chạy được: tạo ba loại lịch và đọc kết quả

### 3.1. Chuẩn bị dự án độc lập

Tạo dự án thực hành với JDK 21 và Gradle 8.5. Cấu trúc tệp:

```text
scheduledtasks-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/scheduling/
    │   ├── SchedulerApplication.java
    │   └── DemoJobs.java
    └── resources/application.properties
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'scheduledtasks-demo'
```

Nội dung `build.gradle`:

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
}

application {
    mainClass = 'example.scheduling.SchedulerApplication'
}
```

Plugin `application` cung cấp tác vụ `run`; BOM của Boot đồng bộ phiên bản các thư viện phụ thuộc. Hai starter cung cấp HTTP server và Actuator. Ví dụ này chạy bằng Gradle, vì mã Java cần các thư viện Spring trên classpath.

Nội dung `src/main/java/example/scheduling/SchedulerApplication.java`:

```java
package example.scheduling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class SchedulerApplication {
    public static void main(String[] args) {
        SpringApplication.run(SchedulerApplication.class, args);
    }
}
```

Nội dung `src/main/java/example/scheduling/DemoJobs.java`:

```java
package example.scheduling;

import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DemoJobs {

    @Scheduled(cron = "0 * * * * *", zone = "Asia/Ho_Chi_Minh")
    public void createMinuteReport() {
        System.out.println("minute-report");
    }

    @Scheduled(fixedDelay = 7, initialDelay = 2, timeUnit = TimeUnit.SECONDS)
    public void cleanTemporaryData() {
        System.out.println("cleanup");
    }

    @Scheduled(fixedRateString = "${demo.cache-rate-ms}", initialDelay = 3000)
    public void refreshCache() {
        System.out.println("cache-refresh");
    }
}
```

Các phương thức đều không nhận tham số và trả `void`. `DemoJobs` nằm trong phạm vi quét bean của lớp ứng dụng. `@EnableScheduling` bật xử lý `@Scheduled`; chỉ thêm Actuator không thay thế bước này. Đơn vị mặc định của các giá trị số trong `@Scheduled` là mili giây; `timeUnit` thay đổi đơn vị của các thuộc tính khoảng thời gian tương ứng. [Hợp đồng của `@Scheduled`](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

### 3.2. Cho phép truy cập endpoint trong môi trường thực hành

Nội dung `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,scheduledtasks
demo.cache-rate-ms=10000
```

Trong Boot 3.3, cần phân biệt **bật endpoint** và **công khai endpoint qua HTTP**. `scheduledtasks` mặc định được bật, nhưng HTTP mặc định chỉ công khai `health`. Nếu ứng dụng đã đặt `management.endpoints.enabled-by-default=false`, cần thêm `management.endpoint.scheduledtasks.enabled=true`; cấu hình `exposure.exclude` có ưu tiên hơn `include`. [Quy tắc bật và công khai endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Dự án thực hành không thêm Spring Security và chỉ lắng nghe địa chỉ loopback. Trong hệ thống thật, giới hạn quyền truy cập thông tin lịch bằng cấu hình bảo mật và mạng phù hợp; tên lớp và phương thức có thể tiết lộ cấu trúc nội bộ. Khi Spring Security hiện diện, quy tắc xác thực còn phụ thuộc `SecurityFilterChain` đang có. [Bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

### 3.3. Chạy ứng dụng và gửi yêu cầu

Tại thư mục dự án thực hành, với lệnh `gradle` 8.5 đã cài và JDK 21 sẵn có:

```shell
gradle run
```

Nếu dự án đã có Gradle Wrapper tương ứng, dùng `./gradlew run` trên shell hỗ trợ hoặc `.\gradlew.bat run` trên Windows. Giữ tiến trình chạy và mở terminal thứ hai:

```shell
curl -i http://127.0.0.1:8080/actuator/scheduledtasks
```

Trên PowerShell, dùng `curl.exe` nếu `curl` đang được ánh xạ sang lệnh khác.

Phần thân phản hồi mong đợi của riêng ví dụ này, trình bày lại thụt dòng để dễ đọc:

```json
{
  "cron": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.createMinuteReport"
      },
      "expression": "0 * * * * *"
    }
  ],
  "fixedDelay": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.cleanTemporaryData"
      },
      "initialDelay": 2000,
      "interval": 7000
    }
  ],
  "fixedRate": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.refreshCache"
      },
      "initialDelay": 3000,
      "interval": 10000
    }
  ],
  "custom": []
}
```

Yêu cầu đọc thành công trả HTTP `200`. Thứ tự thuộc tính JSON không phải điều kiện đúng/sai. Các con số `2000`, `7000`, `3000`, `10000` là giá trị kỳ vọng từ mã và cấu hình trên; không cần chờ tác vụ chạy lần đầu để đọc thông tin đăng ký. Đường dẫn mặc định và cấu trúc phản hồi được mô tả trong [API `scheduledtasks` của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html).

Các phương thức lần lượt in `minute-report`, `cleanup` và `cache-refresh`. Console còn có log khởi động; thứ tự các dòng tác vụ phụ thuộc thời điểm khởi động và lịch thực thi. Vì vậy không dùng thứ tự console để suy ra thứ tự phần tử JSON.

## 4. Đọc từng nhóm và từng trường

| Nhóm/trường | Cách đọc |
| --- | --- |
| `cron` | Các tác vụ theo biểu thức cron. |
| `cron[].expression` | Biểu thức quyết định các thời điểm chạy. |
| `fixedDelay` | Các tác vụ đợi một khoảng sau khi lần trước kết thúc. |
| `fixedRate` | Các tác vụ có chu kỳ theo những mốc bắt đầu dự kiến. |
| `initialDelay` | Độ trễ ban đầu, theo mili giây trong phản hồi. |
| `interval` | Khoảng thời gian, theo mili giây trong phản hồi. |
| `runnable.target` | Đối tượng/phương thức được thực thi. |
| `custom[].trigger` | Chuỗi mô tả điều kiện kích hoạt tùy chỉnh. |

Đây là các nhóm của hợp đồng REST Boot 3.3; nhóm không có tác vụ có thể là mảng rỗng. [Mô tả phản hồi chính thức](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html#scheduledtasks.retrieving.response-structure)

### 4.1. `fixedDelay` và `fixedRate` khác nhau ở đâu?

Dùng các giá trị của ví dụ và giả sử mỗi lần xử lý mất đúng 2 giây, bộ lập lịch không bận:

```text
fixedDelay: initialDelay=2s, interval=7s
bắt đầu 2s -> kết thúc 4s -> đợi 7s -> bắt đầu 11s

fixedRate: initialDelay=3s, interval=10s
các mốc bắt đầu dự kiến: 3s, 13s, 23s, ...
```

Đây là trục thời gian minh họa tính từ thời điểm lập lịch, không phải cam kết độ chính xác thời gian thực. Máy bận hoặc tác vụ khác chiếm luồng có thể làm lần chạy đến muộn. `fixedRate` mô tả nhịp dự kiến; riêng chữ đó không đủ để kết luận cùng một tác vụ sẽ chạy chồng lấn.

Ở cấu hình mặc định không bật virtual threads, bộ lập lịch do Boot tự cấu hình dùng một luồng. Một công việc chặn lâu có thể khiến công việc khác đến lượt muộn dù endpoint vẫn hiển thị đúng `interval`. `scheduledtasks` không hiển thị kích thước nhóm luồng hay độ trễ thực thi để tự chẩn đoán nguyên nhân này. [Cấu hình bộ lập lịch của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)

### 4.2. Cron và múi giờ

Trong ví dụ, `0 * * * * *` có sáu trường: giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần. Nó chọn giây 0 của mỗi phút. `zone` chỉ định múi giờ dùng khi giải lịch. Không lấy biểu thức cron năm trường của hệ điều hành rồi giả định có thể chép nguyên vào Spring. [Cú pháp CronExpression](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/support/CronExpression.html) và [thuộc tính zone](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

Phản hồi Boot 3.3 ở trên đưa ra `expression`; nó không đưa ra trường `zone` hoặc thời điểm chạy tiếp theo. Muốn kiểm tra múi giờ, đối chiếu annotation/cấu hình thực tế. Hai máy trả cùng biểu thức cron vẫn có thể có lịch theo giờ địa phương khác nhau nếu chúng dùng múi giờ khác nhau.

### 4.3. `custom` và lịch đăng ký bằng mã

`ScheduledTaskRegistrar` hỗ trợ đăng ký bằng mã, chẳng hạn `addTriggerTask(Runnable, Trigger)`. Khi tác vụ đi qua hạ tầng thu thập tương ứng, endpoint có thể mô tả nó dù không có `@Scheduled` trên phương thức. [API đăng ký tác vụ](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/config/ScheduledTaskRegistrar.html)

Đừng đồng nhất mọi `TriggerTask` với nhóm `custom`: Boot có mô tả riêng cho `CronTrigger` và `PeriodicTrigger` chạy theo fixed delay/fixed rate. `custom` dùng cho những điều kiện kích hoạt tùy chỉnh tương ứng. Chuỗi `trigger` hoặc tên lớp sinh từ lambda phù hợp để chẩn đoán nhưng không phải mã định danh nghiệp vụ bền vững; tránh dùng chúng làm khóa lưu trữ lâu dài. [Các lớp mô tả của endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

## 5. Rút thông tin cần thiết khi có nhiều tác vụ

Thay vì đọc cả JSON bằng mắt, có thể lọc bằng `jq` nếu máy đã cài công cụ này. Ví dụ sau dành cho Bash:

```bash
curl -fsS http://127.0.0.1:8080/actuator/scheduledtasks \
  | jq -r '.fixedRate[] | [.runnable.target, .initialDelay, .interval] | @tsv'
```

Với dự án thực hành, stdout của bước lọc là một dòng có ba cột phân cách bằng ký tự tab:

```text
example.scheduling.DemoJobs.refreshCache	3000	10000
```

Để kiểm tra chính xác một lịch đã nhận đúng cấu hình:

```bash
curl -fsS http://127.0.0.1:8080/actuator/scheduledtasks \
  | jq -e 'any(.fixedRate[]; .runnable.target == "example.scheduling.DemoJobs.refreshCache" and .interval == 10000)'
```

Kết quả với ví dụ là `true` và `jq` trả mã thoát `0`. Nếu không có phần tử phù hợp, kết quả là `false` và mã thoát `1`. Quy tắc mã thoát của `-e` được mô tả trong [hướng dẫn jq](https://jqlang.org/manual/#invoking-jq). Kiểm tra này xác nhận mô tả lịch có giá trị mong đợi; muốn kiểm chứng công việc đã xử lý được dữ liệu, cần thêm bằng chứng từ chính công việc.

## 6. Giới hạn khi dùng endpoint để chẩn đoán

### 6.1. Có lịch và có kết quả là hai bằng chứng khác nhau

Phản hồi Boot 3.3 mô tả lịch, không cung cấp lịch sử thành công/thất bại, tổng số lần chạy, thời lượng từng lần, stack trace hay trạng thái nghiệp vụ. Ví dụ, phương thức dọn dữ liệu có thể đã được đăng ký nhưng đang gặp lỗi truy cập cơ sở dữ liệu.

Với tình huống đó, dùng `scheduledtasks` để xác định đúng tên tác vụ và cấu hình; tiếp tục đối chiếu log, số liệu đo được ghi nhận và kết quả dữ liệu. Nếu cần biết một lần chạy đang mắc ở đâu, dùng bằng chứng thực thi như thread dump phù hợp với quyền truy cập của bạn. Các trường lịch của phiên bản này được giới hạn bởi [hợp đồng phản hồi REST](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html).

### 6.2. Phạm vi là ứng dụng đang được truy vấn

Với nhiều bản sao ứng dụng, phản hồi từ một bản sao không phải bản kiểm kê toàn cụm. Nếu gọi qua bộ cân bằng tải, hai lần gọi có thể tới hai bản sao khác nhau; hãy xác định bản sao và phiên bản triển khai trước khi so sánh.

Endpoint cũng không tạo khóa phân tán hoặc bảo đảm công việc chỉ chạy một lần trên toàn cụm. Nếu mỗi bản sao đều đăng ký cùng lịch, cần thiết kế cơ chế điều phối công việc theo yêu cầu của hệ thống.

Các công việc do Quartz quản lý có endpoint `quartz` riêng. Khi điều tra một Quartz Job, bắt đầu từ đúng công cụ dành cho Quartz thay vì coi một mảng `scheduledtasks` rỗng là bằng chứng Job không tồn tại. [API Quartz của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html)

### 6.3. Đọc endpoint không thay đổi lịch

Gửi `GET /actuator/scheduledtasks` chỉ đọc mô tả. API này không cung cấp lệnh chạy ngay một tác vụ, tạm dừng nó hoặc thay đổi cron. Cũng không tự coi thao tác sửa một property bên ngoài là đã lập lịch lại: hãy kiểm tra cơ chế nạp cấu hình và đăng ký lại lịch mà ứng dụng thực sự triển khai. [Thao tác đọc của endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

## 7. Chẩn đoán theo hiện tượng

| Hiện tượng | Hướng kiểm tra tiếp theo |
| --- | --- |
| HTTP 404 | Kiểm tra đúng cổng, base path, việc bật endpoint và cấu hình HTTP exposure. |
| HTTP 401 hoặc 403 | Kiểm tra xác thực, quyền của người gọi và chuỗi bộ lọc bảo mật đang áp dụng. |
| HTTP 200 nhưng các nhóm đều rỗng | Kiểm tra `@EnableScheduling`, bean có được quét không, profile/điều kiện tạo bean và nguồn đăng ký lịch. |
| Có tên tác vụ nhưng không thấy hiệu quả | Tìm log của chính tác vụ, lỗi phụ thuộc và bằng chứng dữ liệu; kiểm tra việc chờ luồng. |
| Khoảng thời gian khác mong đợi | Đối chiếu đơn vị, property đã được giải, profile đang chạy và phiên bản triển khai. |
| Hai lần gọi cho danh sách khác nhau | Kiểm tra có truy vấn cùng bản sao/cùng cấu hình triển khai không. |

HTTP 404 có nhiều nguyên nhân, nên kiểm tra từng lớp trước khi sửa mã Java. Nếu đã đổi `management.endpoints.web.base-path`, dùng đường dẫn mới; nếu có cổng quản trị riêng, gửi yêu cầu tới đúng cổng đó. API mặc định dùng tiền tố `/actuator`. [Quy tắc URL của Actuator](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html)

Khi kết quả rỗng, bắt đầu bằng câu hỏi “tác vụ được đăng ký qua đâu?”. Đối tượng do `new DemoJobs()` tự tạo nằm ngoài quy trình quản lý bean sẽ không được xử lý annotation như bean trong ví dụ. Một cron được đặt thành `-` cũng biểu thị lịch bị vô hiệu hóa ở Spring; đừng nhầm trường hợp này với HTTP endpoint bị tắt. [Quy tắc xử lý và vô hiệu hóa cron](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

## 8. Thực hành và tự kiểm tra

Thực hiện lần lượt trên dự án độc lập:

1. Chạy ứng dụng, đọc endpoint và tìm đủ ba phương thức `DemoJobs` trong đúng nhóm.
2. Đổi `demo.cache-rate-ms` thành `15000`, dừng rồi chạy lại ứng dụng. Kiểm tra `fixedRate` của `refreshCache` có `interval=15000`; `initialDelay` vẫn là `3000`.
3. Bỏ `@EnableScheduling`, khởi động lại và đọc phản hồi. Với riêng dự án này, endpoint vẫn có thể truy cập nhưng không còn ba lịch được đăng ký bằng annotation.
4. Thêm lại `@EnableScheduling`, khởi động lại, kiểm tra danh sách được khôi phục.
5. Bỏ `scheduledtasks` khỏi `management.endpoints.web.exposure.include`, khởi động lại rồi gọi endpoint. Với cấu hình ví dụ, đường dẫn đó trả 404, trong khi tác vụ vẫn có thể tiếp tục in các dòng của chúng.

Giải thích được ba kết quả sau là bạn đã nắm trọng tâm bài:

- `fixedDelay.interval=7000` nghĩa là chờ 7 giây sau khi lần trước kết thúc, không phải cam kết bắt đầu đúng mỗi 7 giây.
- `fixedRate.interval=10000` xuất phát từ property đã được giải trong ứng dụng, không còn là chuỗi `${demo.cache-rate-ms}`.
- Một tác vụ xuất hiện trong phản hồi cho biết hạ tầng đã cung cấp mô tả đăng ký của nó; kết quả nghiệp vụ của từng lần chạy cần được xác minh bằng bằng chứng thực thi.
