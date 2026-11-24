# Thông điệp hoàn tất, thông điệp lỗi và giới hạn độ dài

Trong chương **Kết quả và mã thoát** của module **SPRING_CLOUD_TASK**, việc biết một ứng dụng đã chạy xong là chưa đủ. Người vận hành còn cần biết **kết quả nào đã được tạo**, **vì sao tác vụ thất bại** và **nơi tra cứu thông tin chi tiết**. Spring Cloud Task hỗ trợ mục tiêu đó bằng cách lưu metadata của từng lần chạy trong `TaskRepository`, bao gồm `exitCode`, `exitMessage` và `errorMessage`.

Bài học này tập trung vào hai trường dễ bị nhầm: **thông điệp hoàn tất** (`exitMessage`) do ứng dụng có thể chủ động cung cấp, và **thông điệp lỗi** (`errorMessage`) mà hạ tầng Spring Cloud Task có thể ghi khi gặp exception. Cả hai đều chịu **giới hạn độ dài** trong schema JDBC chuẩn. Để vận hành an toàn, cần viết thông điệp ngắn, nhất quán và dùng log hoặc nơi lưu kết quả nghiệp vụ để giữ thông tin đầy đủ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `exitCode`, `exitMessage`, `errorMessage` và log của một lần chạy.
- Đặt `exitMessage` từ `TaskExecutionListener` hoặc `@AfterTask`/`@FailedTask`.
- Giải thích sự ưu tiên của thông điệp được đặt ở `onTaskStartup`, `onTaskFailed` và `onTaskEnd`.
- Nhận diện giới hạn tham khảo **2.500 ký tự** cho `EXIT_MESSAGE` và `ERROR_MESSAGE` trong schema JDBC và giới hạn mặc định của `SimpleTaskRepository`.
- Thiết kế thông điệp đủ ngắn, có mã lỗi ổn định và mã tương quan để truy vấn log.
- Xác minh metadata qua SQL sau một lần chạy thành công và một lần chạy thất bại.
- Tránh các lỗi như nuốt exception, đưa stack trace dài vào exit message, mất thông tin do cắt ngắn và nhầm giữa kết quả của Spring Batch với kết quả Spring Cloud Task.

## 2. Bốn nguồn thông tin về kết quả thực thi

Giả sử một ứng dụng tạo báo cáo cuối ngày. Lần chạy có ID `1042`, đọc 1.500 giao dịch và xuất một file. Người vận hành có thể cần xem:

| Nguồn | Ví dụ | Trả lời câu hỏi gì? |
| --- | --- | --- |
| **`EXIT_CODE` / `exitCode`** | `0`, `1` hoặc mã lỗi được quy ước | Tiến trình hoặc hạ tầng Task ghi nhận thành công/thất bại theo cách nào? |
| **`EXIT_MESSAGE` / `exitMessage`** | `COMPLETED;rows=1500;reportId=RPT-42` | Kết quả tóm tắt cần hiển thị là gì? |
| **`ERROR_MESSAGE` / `errorMessage`** | Một phần stack trace của exception | Có exception nào được ghi nhận khi Task thất bại, và dấu vết là gì? |
| **Log / kho kết quả nghiệp vụ** | Lỗi cụ thể ở dòng 735, correlation ID, đường dẫn báo cáo | Điều gì đã xảy ra chi tiết và cách khắc phục? |

Có thể hình dung mối quan hệ như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Cloud Task"] --> B{"Kết thúc thế nào?"}
    B -->|"Hoàn tất"| C["exitCode thành công"]
    B -->|"Exception chưa được xử lý"| D["exitCode thất bại theo cơ chế đang dùng"]
    C --> E["TaskExecutionListener có thể đặt exitMessage"]
    D --> F["Spring Cloud Task có thể ghi errorMessage"]
    D --> E
    E --> G["TaskRepository lưu tóm tắt khi JDBC hoạt động"]
    F --> G
    A --> H["Log có run-id / correlation-id"]
    G --> I["Tra cứu dashboard hoặc SQL"]
    H --> I
~~~

Các kênh có vai trò **bổ sung cho nhau**:

- `exitCode` phù hợp cho quyết định tự động của scheduler.
- `exitMessage` phù hợp cho một dòng tóm tắt có cấu trúc, dễ đọc.
- `errorMessage` hữu ích khi tìm dấu vết exception, nhưng có thể không chứa đầy đủ stack trace.
- Log và dữ liệu nghiệp vụ cung cấp ngữ cảnh chi tiết, có khả năng tìm kiếm và chính sách lưu trữ riêng.

**Không nên dùng sự tồn tại của `exitMessage` hoặc một câu “SUCCESS” để kết luận thành công nếu `exitCode` hay điều kiện nghiệp vụ cho biết điều ngược lại.**

## 3. exitMessage: thông điệp hoàn tất do ứng dụng chủ động đặt

`TaskExecution` có thuộc tính `exitMessage`; Spring Cloud Task cho phép mã ứng dụng cập nhật nó qua `TaskExecutionListener`. Ví dụ một tác vụ báo cáo có thể ghi:

~~~text
COMPLETED;reportId=RPT-42;rows=1500
~~~

Thông điệp nên là **tóm tắt**, không phải bản báo cáo, payload JSON lớn hay log nhiều dòng. Có thể dùng các trường ngắn, phân cách nhất quán, ví dụ:

| Tình huống | exitMessage đề xuất |
| --- | --- |
| Thành công | `COMPLETED;rows=1500;reportId=RPT-42` |
| Không có dữ liệu để xử lý | `COMPLETED;rows=0;reason=NO_DATA` |
| Bị từ chối vì tham số không hợp lệ | `FAILED;code=INVALID_DATE;runId=run-1042` |
| Lỗi tạm thời khi đọc nguồn dữ liệu | `FAILED;code=UPSTREAM_TIMEOUT;runId=run-1043` |
| Công việc chỉ hoàn tất một phần | `FAILED;code=PARTIAL_WRITE;runId=run-1044` |

Không có format bắt buộc chung cho `exitMessage`. Đội vận hành có thể chọn quy ước `key=value`, JSON ngắn hoặc một mã trạng thái ngắn. Dù chọn cách nào, nên **quy định ý nghĩa, giới hạn độ dài và chính sách che dữ liệu nhạy cảm**.

### Những thông tin không nên đưa vào exitMessage

- Access token, mật khẩu, khóa API, chuỗi kết nối có secret.
- Toàn bộ nội dung hồ sơ khách hàng, thông tin định danh hoặc dữ liệu đầu vào nhạy cảm.
- Cả stack trace hoặc thông tin từng bản ghi thất bại.
- Blob JSON/XML lớn, danh sách hàng nghìn ID hoặc nội dung file kết quả.
- Đường dẫn chứa secret hoặc URL có query string chứa thông tin bí mật.

Thay vào đó, ghi `runId`, `reportId` hoặc `errorCode` không nhạy cảm; sử dụng mã này để tìm log hoặc dữ liệu kết quả ở nơi phù hợp.

## 4. errorMessage: dấu vết lỗi do hạ tầng ghi nhận

`TaskExecution.errorMessage` khác `exitMessage` ở **nguồn phát sinh** và **mục đích sử dụng**. Theo tài liệu Spring Cloud Task, khi một exception là nguyên nhân kết thúc Task và phát ra `ApplicationFailedEvent`, framework có thể lưu stack trace của exception trong `errorMessage`.

Ví dụ nội dung có thể bắt đầu như sau:

~~~text
java.lang.IllegalArgumentException: invalid businessDate
  at com.example.task.ReportRunner.run(ReportRunner.java:...)
  ...
~~~

Đây là **ví dụ minh họa**, vì cách ghi stack trace, tên class, số dòng và phần còn giữ được phụ thuộc phiên bản, lỗi và giới hạn lưu trữ. Cần lưu ý:

1. Một mã thoát khác `0` **không bảo đảm** `ERROR_MESSAGE` có giá trị. Ví dụ tác vụ có thể phát mã thoát theo chính sách riêng mà không có exception chưa xử lý.
2. `errorMessage` có thể trống nếu ứng dụng chết trước khi hạ tầng Task hoạt động, JVM bị kill hoặc kết nối `TaskRepository` bị lỗi.
3. Stack trace thực tế thường dài hơn dung lượng cột; **không được giả định toàn bộ trace nằm trong database**.
4. Exception có thể chứa thông tin nhạy cảm trong message; cần kiểm soát cách tạo exception, quyền đọc database và log.

`errorMessage` không nên là nơi ứng dụng đẩy thủ công cả một báo cáo. Hãy dùng `exitMessage` cho tóm tắt có chủ ý, `errorMessage` cho dấu vết lỗi theo cơ chế framework, và hệ thống log để giữ chi tiết phục vụ chẩn đoán.

## 5. Vòng đời listener và quy tắc ưu tiên thông điệp

Spring Cloud Task hỗ trợ interface `TaskExecutionListener` với ba callback:

| Callback | Thời điểm khái niệm | Có thể dùng để |
| --- | --- | --- |
| `onTaskStartup(TaskExecution)` | Khi Task bắt đầu, sau khi hạ tầng tạo thông tin lần chạy theo phiên bản tương ứng | Gắn một thông điệp ban đầu hoặc ngữ cảnh |
| `onTaskFailed(TaskExecution, Throwable)` | Khi có exception chưa được xử lý, trước callback kết thúc | Đặt mã lỗi ngắn, nguồn lỗi và correlation ID |
| `onTaskEnd(TaskExecution)` | Trước bước cập nhật trạng thái kết thúc vào repository | Ghi tóm tắt thành công hoặc hoàn thiện thông điệp |

Ba annotation tương đương dành cho phương thức trong bean là `@BeforeTask`, `@FailedTask` và `@AfterTask`.

Khi nhiều callback cùng gọi `setExitMessage(...)`, tài liệu Spring Cloud Task mô tả thứ tự ưu tiên:

1. **`onTaskEnd`** có độ ưu tiên cao nhất nếu đặt thông điệp.
2. **`onTaskFailed`** cao hơn `onTaskStartup` trong trường hợp thất bại.
3. **`onTaskStartup`** là giá trị nền khi không có callback sau ghi đè.

Ví dụ: callback lỗi đặt `FAILED;code=TIMEOUT` nhưng callback kết thúc lại luôn đặt `COMPLETED`. Khi đó thông điệp cuối có thể là `COMPLETED` dù công việc đã thất bại. Đây là một lỗi thiết kế thông điệp **rất dễ gây hiểu nhầm dashboard**.

### Quy tắc thực hành

- Chỉ đặt `COMPLETED` trong `onTaskEnd` khi chưa có một thông điệp lỗi đã được đặt.
- Khi thất bại, đặt mã lỗi gọn trong `onTaskFailed`; không ghi đè ở `onTaskEnd`.
- Đừng thay đổi ý nghĩa của mã thoát bằng cách chỉ viết một thông điệp trông giống thành công.
- Listener nên thực hiện công việc nhẹ, không gọi API chậm hoặc thực hiện nghiệp vụ có thể thất bại thêm.
- Không để exception trong listener làm mất hoặc làm sai kết quả lỗi ban đầu; cần kiểm soát mã listener cẩn thận.

## 6. Ví dụ Java: ghi thông điệp thành công và lỗi

Chúng ta xây dựng tác vụ demo thực thi một lần và ghi tóm tắt khác nhau theo kết quả. Ví dụ phù hợp với ứng dụng Spring Boot và Spring Cloud Task tương thích nhau; cần starter `spring-cloud-starter-task`, `spring-boot-starter` và JDBC datasource nếu muốn tra cứu metadata sau khi tiến trình dừng.

### 6.1. Mã ứng dụng

Tạo `src/main/java/com/example/task/ResultMessageApplication.java`:

~~~java
package com.example.task;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class ResultMessageApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResultMessageApplication.class, args);
    }

    @Bean
    RunStats runStats() {
        return new RunStats();
    }

    @Bean
    ApplicationRunner reportRunner(RunStats stats) {
        return args -> {
            stats.processedRows.set(2);

            if (args.containsOption("fail")) {
                throw new IllegalStateException(
                        "Simulated failure while processing report");
            }

            stats.processedRows.set(3);
            System.out.println("Report generated: rows=3");
        };
    }

    @Bean
    TaskExecutionListener resultMessageListener(RunStats stats) {
        return new TaskExecutionListener() {

            @Override
            public void onTaskFailed(TaskExecution execution,
                                     Throwable throwable) {
                // Tóm tắt được kiểm soát; không đưa stack trace vào exitMessage.
                execution.setExitMessage(
                        "FAILED;code=DEMO_ERROR;rows="
                        + stats.processedRows.get());
            }

            @Override
            public void onTaskEnd(TaskExecution execution) {
                // onTaskEnd chạy sau onTaskFailed: giữ lại thông điệp lỗi.
                if (execution.getExitMessage() == null) {
                    execution.setExitMessage(
                            "COMPLETED;rows="
                            + stats.processedRows.get());
                }
            }
        };
    }

    static class RunStats {
        final AtomicInteger processedRows = new AtomicInteger();
    }
}
~~~

**Diễn giải:**

- `reportRunner` là công việc hữu hạn. Nếu có option `--fail`, nó ném exception; nếu không, nó in kết quả hoàn tất.
- `RunStats` là bean giữ số hàng xử lý để minh họa cách listener lấy thông tin tóm tắt.
- `onTaskFailed` ghi `FAILED;code=DEMO_ERROR;rows=2` vào `exitMessage` và **không nuốt exception** phát sinh trong runner.
- `onTaskEnd` chỉ điền thông điệp hoàn tất khi chưa có thông điệp trước đó, tránh ghi đè `FAILED`.
- `errorMessage` được dành cho cơ chế Spring Cloud Task ghi nhận exception khi điều kiện vòng đời và repository cho phép.

Ở ví dụ này, mọi lời gọi `setExitMessage` đều tạo thông điệp ngắn. Trong ứng dụng thực tế, hãy thu thập số liệu bằng một service chuyên trách, đồng thời đảm bảo dữ liệu thống kê phản ánh kết quả **đã commit thành công**, không chỉ số dòng từng được đọc hoặc xử lý thử.

### 6.2. Cách dùng annotation thay cho interface

Nếu muốn phương thức nằm trong một bean Spring bình thường, có thể viết:

~~~java
package com.example.task;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
class MessageHooks {

    @FailedTask
    public void failed(TaskExecution execution, Throwable cause) {
        execution.setExitMessage("FAILED;code=UNEXPECTED");
    }

    @AfterTask
    public void completed(TaskExecution execution) {
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("COMPLETED");
        }
    }
}
~~~

Đây là **phương án thay thế** `TaskExecutionListener` ở mục 6.1. Chỉ chọn **một** cơ chế cho cùng thông điệp để tránh nhiều listener ghi đè nhau theo thứ tự khó kiểm soát. Cả hai đều sử dụng chính đối tượng `TaskExecution` trước khi dữ liệu kết thúc được ghi lại vào repository.

## 7. Cấu hình JDBC để kiểm tra qua nhiều lần chạy

Để đọc record sau khi JVM dừng, có thể dùng PostgreSQL hoặc một database JDBC lưu bền vững. Với thực hành cục bộ, H2 dạng **file** thuận tiện hơn H2 `mem:` vì file giữ metadata qua các tiến trình (cần tuân thủ cách truy cập file H2).

Phần dependency Maven tối thiểu cho H2:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Dự án phải quản lý phiên bản bằng **Spring Boot BOM/parent và Spring Cloud BOM tương thích**. Sử dụng `spring-boot-maven-plugin` để đóng gói thành JAR thực thi; tên và phiên bản artifact do `pom.xml` quy định.

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: result-message-demo
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./result-message-task-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: result-message-demo
      initialize-enabled: true
      closecontextEnabled: true

logging:
  level:
    org.springframework.cloud.task: INFO
~~~

Với `jdbc:h2:file:./result-message-task-db`, H2 lưu trên ổ đĩa của môi trường chạy. Trong production nên sử dụng database dùng chung, quản lý schema bằng migration và không phụ thuộc vào cơ chế tự tạo bảng khi mỗi task khởi động. Không lưu mật khẩu thật trong file cấu hình nguồn.

### 7.1. Chạy thành công

~~~bash
./mvnw clean package
java -jar target/result-message-demo-0.0.1-SNAPSHOT.jar
~~~

Trên Windows PowerShell, dùng `.\mvnw.cmd clean package` và tên JAR thực tế. Đầu ra nghiệp vụ dự kiến:

~~~text
Report generated: rows=3
~~~

Khi Spring Cloud Task ghi metadata thành công, trường `EXIT_MESSAGE` của lần thực thi có thể là:

~~~text
COMPLETED;rows=3
~~~

### 7.2. Chạy thất bại

~~~bash
java -jar target/result-message-demo-0.0.1-SNAPSHOT.jar --fail
~~~

Runner ném `IllegalStateException`. Kết quả mong đợi ở lớp Task, nếu hạ tầng đã khởi tạo và ghi repository thành công:

- `EXIT_MESSAGE` là `FAILED;code=DEMO_ERROR;rows=2`.
- `ERROR_MESSAGE` có thể chứa một phần stack trace của exception.
- `EXIT_CODE` phản ánh thất bại theo cơ chế Spring Boot/Spring Cloud Task và môi trường chạy.

Không yêu cầu log hoặc nội dung `ERROR_MESSAGE` khớp từng ký tự, vì stack trace tùy Java, version thư viện và vị trí ném lỗi.

### 7.3. Truy vấn kết quả

Khi các tiến trình đã dừng, mở database H2 file bằng công cụ SQL với **cùng đường dẫn file**. Theo schema chuẩn, có thể dùng:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Để kiểm tra độ dài đã lưu, dùng hàm `LENGTH` của H2 (nhiều hệ quản trị khác cũng hỗ trợ):

~~~sql
SELECT TASK_EXECUTION_ID,
       LENGTH(EXIT_MESSAGE)  AS EXIT_MESSAGE_LENGTH,
       LENGTH(ERROR_MESSAGE) AS ERROR_MESSAGE_LENGTH
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Nếu chưa có bảng `TASK_EXECUTION` hoặc record nào, hãy kiểm tra schema, datasource, quyền kết nối, cấu hình Task và lỗi trước lúc context hoàn tất. **Không nên cho rằng không có record nghĩa là chương trình chưa được khởi chạy.**

## 8. Giới hạn độ dài: 2.500 ký tự dùng để hiểu điều gì?

Trong tài liệu schema JDBC hiện được công bố của Spring Cloud Task, bảng `TASK_EXECUTION` mô tả:

| Cột | Kiểu tham khảo | Giới hạn độ dài tham khảo |
| --- | --- | ---: |
| `TASK_NAME` | `VARCHAR` | 100 |
| `EXIT_MESSAGE` | `VARCHAR` | **2.500** |
| `ERROR_MESSAGE` | `VARCHAR` | **2.500** |

Javadoc của `SimpleTaskRepository` (bản API 3.0.4) cũng công bố các hằng `MAX_EXIT_MESSAGE_SIZE` và `MAX_ERROR_MESSAGE_SIZE` có giá trị mặc định **2.500**, cùng `MAX_TASK_NAME_SIZE = 100`.

**Cần đọc giới hạn này đúng phạm vi:**

- Đây là giá trị theo **schema và bản API được dẫn**; dự án của bạn phải kiểm tra script DDL và implementation **đúng phiên bản đang sử dụng**.
- Giới hạn ứng dụng và giới hạn cột database liên quan nhau nhưng không hoàn toàn tương đương. DB có thể kiểm tra độ dài theo ký tự, byte hoặc quy tắc riêng.
- Không thể giả định rằng framework ở mọi phiên bản đều xử lý dữ liệu vượt giới hạn theo cùng một cách. Một bản triển khai có thể giới hạn/cắt nội dung trước khi ghi; database vẫn có thể từ chối dữ liệu quá dài khi schema hoặc cách cấu hình không khớp.
- Khi quá dài, phần bị cắt có thể chính là thông tin nguyên nhân cuối cùng, mã tương quan hoặc đoạn stack trace cần tìm.
- Tăng kích thước cột bằng DDL tự ý **không bảo đảm** mã repository sẽ tự gửi nhiều ký tự hơn. Ngược lại, tăng giới hạn trong mã mà không cập nhật schema cũng có thể gây lỗi ghi.

### 8.1. Mức giới hạn nên dùng trong nghiệp vụ

Đừng cố tận dụng hết 2.500 ký tự cho `exitMessage`. Có thể áp dụng quy ước nội bộ:

| Loại dữ liệu | Mức đề xuất trong ví dụ | Nơi lưu |
| --- | --- | --- |
| `exitMessage` tóm tắt | 200–500 ký tự | `TaskRepository` |
| Mã lỗi ổn định | 20–80 ký tự | `exitMessage` và log |
| Correlation ID | Một định danh ngắn, không chứa bí mật | `exitMessage` và log |
| Full stack trace | Không ép vào một thông điệp ngắn | Hệ thống log có phân quyền |
| File kết quả, danh sách bản ghi lỗi | Theo nhu cầu dữ liệu nghiệp vụ | Database hoặc object storage phù hợp |

Các số 200–500 ở đây là **quy ước khuyến nghị**, không phải property bắt buộc của Spring Cloud Task.

### 8.2. Unicode và độ dài chuỗi

Với tiếng Việt hoặc emoji, “2.500 ký tự” không phải lúc nào cũng tương ứng với “2.500 byte”. Java `String.length()` đếm đơn vị UTF-16; một số ký tự như emoji dùng hai đơn vị. Database có thể áp dụng cách đếm khác.

Vì vậy, để an toàn:

1. Giữ thông điệp ngắn hơn đáng kể so với giới hạn cột.
2. Tránh đưa văn bản tự do rất dài của người dùng vào repository.
3. Khi bắt buộc cắt nội dung, chú ý không cắt giữa một cặp surrogate Unicode.
4. Kiểm thử dữ liệu có dấu tiếng Việt và ký tự đặc biệt với **chính JDBC driver và database production**.

Ví dụ hàm cắt theo **Unicode code point**, hữu ích cho một quy ước hiển thị ngắn:

~~~java
static String abbreviate(String text, int maxCodePoints) {
    if (text == null) {
        return null;
    }

    int count = text.codePointCount(0, text.length());
    if (count <= maxCodePoints) {
        return text;
    }

    int end = text.offsetByCodePoints(0, maxCodePoints - 1);
    return text.substring(0, end) + "…";
}
~~~

Hàm này minh họa tránh cắt giữa surrogate pair, **không thay thế** kiểm tra giới hạn byte/độ dài thực tế của hệ quản trị database. Khi dùng, yêu cầu `maxCodePoints >= 1` và cần kiểm soát giá trị tham số ở tầng gọi.

### 8.3. Có nên tăng giới hạn lên 10.000?

Chỉ nên cân nhắc khi có yêu cầu rõ ràng, vì cần đánh giá **cả mã repository, schema và công cụ đọc dữ liệu**:

- Framework/version có hỗ trợ cấu hình độ dài tối đa bằng API tùy biến hay không? `SimpleTaskRepository` có các setter `setMaxExitMessageSize` và `setMaxErrorMessageSize` trong API được dẫn, nhưng **không nên tự đặt tên property YAML chưa được phiên bản hỗ trợ xác nhận**.
- DDL cần migration và kiểm thử các database được hỗ trợ.
- Dashboard/API có xử lý được thông điệp dài và tránh lộ dữ liệu nhạy cảm không?
- Chi phí lưu trữ và truy vấn có hợp lý không?

Trong phần lớn hệ thống, **giữ exitMessage ngắn và chuyển log chi tiết tới nơi lưu thích hợp** là giải pháp dễ vận hành hơn.

## 9. Lưu đầy đủ lỗi dài: dùng mã tương quan và log

Một stack trace có thể dài hàng chục nghìn ký tự. Nếu cột `ERROR_MESSAGE` chỉ giữ được một phần, việc tìm nguyên nhân gốc có thể khó khăn. Thiết kế nên dựa trên **cùng một mã tương quan** giữa nhiều nguồn dữ liệu.

Ví dụ:

~~~text
runId=report-2026-11-24-001
exitMessage=FAILED;code=UPSTREAM_TIMEOUT;runId=report-2026-11-24-001
logKey=runId:report-2026-11-24-001
~~~

Quy trình:

1. Bộ điều phối tạo `runId` và ghi nhận lần yêu cầu thực thi.
2. Ứng dụng dùng `runId` khi ghi log, hoặc liên kết nó với `TASK_EXECUTION_ID` sau khi hạ tầng Task được tạo.
3. Listener ghi tóm tắt có mã lỗi ổn định vào `EXIT_MESSAGE`.
4. Framework ghi `ERROR_MESSAGE` trong giới hạn khi exception được quan sát.
5. Người vận hành từ `runId` và `TASK_EXECUTION_ID` tra log chi tiết, xem tài nguyên lỗi và thực hiện khắc phục.

Không nên phụ thuộc hoàn toàn vào `TASK_EXECUTION_ID` để nối dữ liệu: nếu JVM hỏng trước khi repository ghi được record, ID này có thể không tồn tại. Mã tạo trước bởi scheduler giúp điều tra cả trường hợp **không có TaskExecution**.

Khi log exception, phải chú ý không lộ thông tin nhạy cảm trong message hoặc dữ liệu đầu vào; áp dụng redaction, retention và quyền truy cập phù hợp. Việc lưu lỗi vào database không thay thế chính sách bảo mật log.

## 10. Những tình huống lỗi thường gặp

### 10.1. Exit message ghi “COMPLETED” dù mã thoát thất bại

Nguyên nhân có thể do `onTaskEnd` luôn gọi `setExitMessage("COMPLETED")` kể cả sau `onTaskFailed`. Giải pháp: chỉ đặt thông điệp hoàn tất khi chưa có lỗi, dùng cùng quy ước trạng thái và kiểm tra kết quả nghiệp vụ.

### 10.2. ERROR_MESSAGE rỗng dù exit code khác 0

Không phải mọi mã lỗi đều được tạo bởi `ApplicationFailedEvent` hoặc exception mà framework quan sát. Hãy kiểm tra `ExitCodeGenerator`/`ExitCodeExceptionMapper` nếu có, log và nguyên nhân kết thúc thực tế của process. Nếu tác vụ bị kill, việc lưu lỗi có thể không hoàn tất.

### 10.3. ERROR_MESSAGE chỉ chứa phần đầu stack trace

Độ dài cột và logic lưu trữ có thể giới hạn nội dung. Hãy tìm full trace theo `runId` trong log, thay vì cố dùng phần metadata bị cắt làm nguồn chẩn đoán duy nhất.

### 10.4. Lưu thông điệp dài làm thất bại cập nhật repository

Nếu kích thước chuỗi vượt khả năng của cột hoặc repository/schema không khớp, thao tác lưu cuối có thể lỗi. Ngăn ngừa bằng quy ước ngắn, test với DB thực, migration có kiểm soát và theo dõi lỗi JDBC.

### 10.5. Listener tự ném exception

Một listener có thể tạo lỗi mới và ảnh hưởng tới dòng chảy xử lý callback hoặc mã thoát. Không để listener ghi thông điệp thực hiện thao tác có khả năng thất bại như gọi HTTP hay lưu một file lớn. Tập trung vào tính toán nhẹ trên dữ liệu đã có; không gọi `System.exit` trong listener.

### 10.6. Không có record TaskExecution

Nếu `ApplicationContext` không bootstrap được, task có thể chưa tạo record nào. Hoặc JDBC bị lỗi, schema thiếu, database trỏ sai. Kiểm tra log khởi động và nguồn quan sát bên ngoài trước khi kết luận tác vụ không chạy.

### 10.7. Exit message cho thấy số hàng được xử lý nhưng báo cáo thiếu hàng

Một biến đếm trong bộ nhớ có thể phản ánh số hàng đã được đọc, không phải số hàng đã **commit**. Cần xây dựng tiêu chí nghiệp vụ, kiểm tra transaction và ghi số liệu chỉ sau khi kết quả đã xác nhận.

## 11. Phối hợp với Spring Batch và mã thoát

Trong một ứng dụng dùng cả **Spring Cloud Task** và **Spring Batch**:

- `TaskExecution` mô tả **một lần chạy ứng dụng** và các trường `exitCode`, `exitMessage`, `errorMessage`.
- `JobExecution` và `StepExecution` mô tả trạng thái công việc **theo lô**; chúng thuộc `JobRepository` của Spring Batch.
- `BatchStatus` và `ExitStatus` của Batch **không đồng nhất** với `EXIT_CODE` hoặc `EXIT_MESSAGE` của Spring Cloud Task.
- Nếu job Batch thất bại nhưng ứng dụng xử lý hoặc ánh xạ trạng thái không phù hợp, **mã thoát Task có thể vẫn là 0**. Trong các phiên bản Spring Cloud Task hỗ trợ, thuộc tính `spring.cloud.task.batch.fail-on-job-failure=true` giúp đưa thất bại Batch lên mã thoát Task theo chính sách của thư viện.

Ví dụ policy ở một môi trường có yêu cầu job thất bại thì Task cũng thất bại:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

Hãy xác minh property theo đúng version đang dùng và chạy bài kiểm tra **Batch FAILED → Task exit non-zero**. Không chỉ thay `EXIT_MESSAGE` thành `FAILED` để giả lập một trạng thái Batch; hệ thống điều phối cần mã thoát phản ánh đúng trạng thái.

Khi tạo tóm tắt cuối, có thể đưa `jobExecutionId` và `batchStatus` vào `exitMessage` nếu không chứa dữ liệu nhạy cảm, nhưng nhớ giữ trong giới hạn. Log và Batch `JobRepository` mới là nơi tra cứu nguyên nhân từng step.

## 12. Kiểm thử các tình huống quan trọng

Một bộ kiểm thử tích hợp có ý nghĩa nên chạy với repository JDBC (ít nhất H2 dạng file; tốt hơn là database tương đương production) và xác minh:

| Tình huống | Kết quả cần đối chiếu |
| --- | --- |
| Runner hoàn tất | `EXIT_CODE` thành công; `EXIT_MESSAGE` tóm tắt đúng; có `END_TIME` |
| Runner ném exception | `EXIT_CODE` thất bại; `EXIT_MESSAGE` mã lỗi; `ERROR_MESSAGE` có thể có trace |
| `@AfterTask` tồn tại cùng `@FailedTask` | Không ghi đè thông điệp thất bại bằng `COMPLETED` |
| Chuỗi exitMessage rất dài | Kiểm tra hành vi version hiện tại, kết quả DB, lỗi/truncation; không mất mã tương quan |
| Stack trace dài | Xác minh có full trace trong log và phần metadata chỉ đóng vai trò hỗ trợ |
| Lỗi trước khi tạo ApplicationContext | Scheduler/log vẫn ghi nhận thất bại dù TaskRepository có thể chưa có record |
| PostgreSQL schema và repository lệch version | Phát hiện lỗi JDBC trước khi triển khai, không dựa vào kết quả H2 đơn thuần |
| Spring Batch job FAILED | Mã thoát Task và Batch status khớp với policy đã cấu hình |

**Đối với lỗi giả lập**, có thể truyền một option như `--fail` trong ví dụ Java; không cần tự gây lỗi hạ tầng production để thử kiểm soát độ dài.

## 13. Checklist vận hành an toàn

- [ ] Thống nhất ý nghĩa của `EXIT_CODE`, `EXIT_MESSAGE`, `ERROR_MESSAGE` và trạng thái nghiệp vụ.
- [ ] `exitMessage` ngắn, có mã lỗi ổn định và correlation ID, không chứa secret hoặc dữ liệu nhạy cảm.
- [ ] Listener ghi tóm tắt không ghi đè thông điệp lỗi trong `onTaskFailed`.
- [ ] Đã kiểm tra giới hạn cột `EXIT_MESSAGE`/`ERROR_MESSAGE` theo schema **của phiên bản thực tế**.
- [ ] Có log đầy đủ với định danh lần chạy, retention và phân quyền phù hợp.
- [ ] Scheduler/container ghi nhận mã thoát và trạng thái ngay cả khi TaskRepository không có record.
- [ ] Mã lỗi hoặc exception chưa được xử lý không bị nuốt khiến tiến trình bị báo thành công sai.
- [ ] Khi chạy lại, dữ liệu nghiệp vụ có khóa tránh trùng và chiến lược idempotency.
- [ ] Nếu dùng Spring Batch, có kiểm chứng ánh xạ Batch status sang Task exit code.

## 14. Câu hỏi và bài tập

**Câu hỏi 1.** Nếu `EXIT_CODE = 1`, `EXIT_MESSAGE = "COMPLETED"` và `ERROR_MESSAGE` chứa exception, bạn sẽ kiểm tra điều gì trước tiên? Vì sao không nên tin vào riêng exit message?

**Câu hỏi 2.** Nếu database khai báo `EXIT_MESSAGE VARCHAR(2500)`, tại sao vẫn nên giới hạn thông điệp nghiệp vụ khoảng 200–500 ký tự?

**Câu hỏi 3.** `@FailedTask` đặt `FAILED;code=INPUT_INVALID`. `@AfterTask` chạy sau đó đặt `COMPLETED`. Thông điệp cuối có thể là gì? Hãy sửa logic để bảo toàn nguyên nhân lỗi.

**Câu hỏi 4.** Tại sao `ERROR_MESSAGE` có thể rỗng dù tiến trình không thành công? Trường hợp mất kết nối database khác gì trường hợp lỗi nghiệp vụ?

**Bài tập A — Thông điệp có cấu trúc:** mở rộng ví dụ Java để đặt `exitMessage` theo format `status=...;rows=...;runId=...`. Tạo `runId` từ bộ điều phối và truyền vào ứng dụng. Không cho giá trị dài vượt quy ước nội bộ.

**Bài tập B — Giới hạn độ dài:** tạo một lỗi có message dài trên môi trường thử nghiệm, quan sát log đầy đủ và `ERROR_MESSAGE` trong repository. So sánh kích thước, ghi rõ version framework/database và tránh kết luận rằng mọi phiên bản cắt chuỗi giống nhau.

**Bài tập C — Tích hợp Batch:** chạy một job Batch thất bại; so sánh `BatchStatus`, `ExitStatus`, `TaskExecution.exitCode`, `exitMessage` và exit code của tiến trình. Áp dụng policy `fail-on-job-failure` nếu được phiên bản hỗ trợ.

## 15. Ghi nhớ

- **`exitCode`** là tín hiệu trạng thái dạng số; **`exitMessage`** là tóm tắt do ứng dụng có thể chủ động đặt; **`errorMessage`** là dấu vết lỗi do hạ tầng có thể ghi nhận khi gặp exception.
- `TaskExecutionListener` hỗ trợ đặt `exitMessage`. Trong các callback, `onTaskEnd` có thể ghi đè thông điệp từ `onTaskFailed`, nên phải bảo vệ thông điệp thất bại.
- Schema JDBC tham khảo hiện công bố **`EXIT_MESSAGE` và `ERROR_MESSAGE` dài 2.500**; `SimpleTaskRepository` ở API 3.0.4 cũng có giới hạn mặc định 2.500. Luôn xác minh version và DDL thực tế.
- **Metadata là tóm tắt có giới hạn**. Stack trace đầy đủ, chi tiết từng bản ghi và kết quả lớn cần log hoặc kho nghiệp vụ với mã tương quan.
- Một tiến trình thất bại có thể không có `ERROR_MESSAGE` hoặc thậm chí không có `TaskExecution` nếu hạ tầng khởi động/lưu dữ liệu thất bại.
- Khi phối hợp Spring Batch, phải kiểm tra chính sách ánh xạ trạng thái Batch sang mã thoát Task; không lấy câu chữ trong `exitMessage` để thay thế kiểm tra trạng thái.

## Tài liệu tham khảo

- [Spring Cloud Task Reference — Features: Task Execution, Exit Messages và Task Execution Listener](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/features.html).
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html), mô tả `TASK_EXECUTION.EXIT_MESSAGE` và `TASK_EXECUTION.ERROR_MESSAGE`.
- [SimpleTaskRepository API (Spring Cloud Task 3.0.4)](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/support/SimpleTaskRepository.html), khai báo các giới hạn và API setter liên quan.
- [Constant Field Values (Spring Cloud Task 3.0.4)](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/constant-values.html), giá trị mặc định 2.500.
- [TaskExecutionListener API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html), hợp đồng callback kết thúc/thất bại.

Khi triển khai, hãy đối chiếu các thông tin này với **phiên bản Spring Cloud Task, Spring Boot và DDL đang dùng thực tế**; số lượng và cách xử lý ký tự quá dài có thể thay đổi giữa các bản triển khai.
