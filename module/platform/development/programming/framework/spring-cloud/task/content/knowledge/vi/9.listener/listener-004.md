# `@BeforeTask`, `@AfterTask` và `@FailedTask`

## 1. Mục tiêu bài học

Một ứng dụng **Spring Cloud Task** thực hiện công việc có thời gian chạy hữu hạn: nhập dữ liệu, đồng bộ thông tin, xuất báo cáo hoặc xử lý một yêu cầu rồi kết thúc. Ngoài logic nghiệp vụ, ứng dụng thường cần ghi log, đo thời gian chạy, bổ sung thông tin kết quả và báo lỗi để có thể vận hành an toàn.

Spring Cloud Task cung cấp **listener theo vòng đời thực thi** để đặt các xử lý đó vào đúng thời điểm. Có hai cách đăng ký listener: triển khai giao diện `TaskExecutionListener` hoặc dùng các annotation trên phương thức của Spring bean:

- **`@BeforeTask`**: xử lý ở thời điểm bắt đầu task, trước thao tác lưu thông tin bắt đầu vào `TaskRepository`.
- **`@AfterTask`**: xử lý ở thời điểm task hoàn tất, trước thao tác cập nhật trạng thái cuối vào `TaskRepository`.
- **`@FailedTask`**: xử lý khi task phát sinh ngoại lệ chưa được giải quyết, trước khi các callback `@AfterTask` được gọi.

Bài học thuộc phần **Listener** của module `SPRING_CLOUD_TASK`, tập trung vào ba annotation trên, cách dùng `TaskExecution` và `Throwable`, xử lý lỗi đúng cách và quan sát kết quả qua cơ sở dữ liệu.

Sau bài này, bạn có thể tự viết listener để ghi nhận vòng đời, phân biệt callback của lần chạy thành công và thất bại, đặt `exitMessage` phù hợp, tránh để listener làm sai lệch kết quả nghiệp vụ và tích hợp việc giám sát khi task chạy theo lịch hoặc theo yêu cầu.

## 2. Listener nằm ở đâu trong vòng đời Spring Cloud Task?

**`TaskExecution`** đại diện cho **một lần thực thi** của ứng dụng Spring Cloud Task. **`TaskRepository`** lưu thông tin đó, thường gồm ID, tên task, thời điểm bắt đầu, thời điểm kết thúc, mã thoát, thông tin lỗi và tham số. Mỗi lần chạy JAR sẽ có một `TaskExecution` riêng, kể cả khi cùng tên task.

Spring Cloud Task khởi tạo phần theo dõi trước khi các `ApplicationRunner` và `CommandLineRunner` chạy. Các annotation listener được kích hoạt theo vòng đời này:

| Annotation | Phương thức tương ứng của `TaskExecutionListener` | Khi nào được gọi? | Tham số |
| --- | --- | --- | --- |
| `@BeforeTask` | `onTaskStartup(TaskExecution)` | Trước khi lưu `TaskExecution` bắt đầu vào repository | `TaskExecution` |
| `@FailedTask` | `onTaskFailed(TaskExecution, Throwable)` | Khi có lỗi chưa được xử lý; trước callback kết thúc | `TaskExecution`, `Throwable` |
| `@AfterTask` | `onTaskEnd(TaskExecution)` | Trước khi cập nhật trạng thái cuối của `TaskExecution` trong repository | `TaskExecution` |

Hai luồng phổ biến:

```mermaid
flowchart TD
    A[Spring Boot khởi tạo ứng dụng] --> B[@BeforeTask]
    B --> C[TaskRepository lưu bản ghi bắt đầu]
    C --> D[ApplicationRunner / CommandLineRunner chạy]
    D --> E{Công việc kết thúc thế nào?}
    E -->|Thành công| G[@AfterTask]
    E -->|Ngoại lệ chưa xử lý| F[@FailedTask]
    F --> G
    G --> H[TaskRepository cập nhật trạng thái cuối]
    H --> I[Hoàn tất vòng đời TaskExecution]
```

Điểm đặc biệt cần nhớ: **`@AfterTask` không đồng nghĩa với “thành công”.** Nó là callback khi kết thúc, nên có thể chạy cả sau nhánh `@FailedTask`. Muốn xử lý riêng lỗi, dùng `@FailedTask`. Nếu cần biết kết quả chính thức sau khi cập nhật repository, hãy truy vấn bản ghi **sau khi task đã hoàn tất**, không mặc định dữ liệu cuối đã được ghi trong lúc `@AfterTask` đang chạy.

Đây là listener của **vòng đời ứng dụng task**, không phải listener của từng câu SQL, từng thread hoặc từng step Spring Batch. Khi phối hợp Spring Batch, `TaskExecutionListener` theo dõi lần chạy Spring Cloud Task, còn các listener của Spring Batch theo dõi job/step theo phạm vi riêng.

## 3. Khai báo annotation và chữ ký phương thức

Ba annotation nằm trong package:

```java
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
```

Kiểu dữ liệu callback:

```java
import org.springframework.cloud.task.repository.TaskExecution;
```

Một Spring bean chứa ba phương thức có thể được khai báo như sau:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("[BEFORE] task=" + execution.getTaskName());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable throwable) {
        System.err.println("[FAILED] task=" + execution.getTaskName()
                + ", errorType=" + throwable.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("[AFTER] task=" + execution.getTaskName());
    }
}
```

**Vì sao có `@Component`?** Listener phải thuộc một **Spring-managed bean** được ứng dụng phát hiện; không nên chỉ tạo một đối tượng bằng `new AuditTaskListener()` rồi mong framework tự gọi các phương thức. Annotation được áp dụng cho **phương thức**, không đặt lên toàn bộ class.

Chữ ký của `@FailedTask` cần thêm `Throwable` để nhận nguyên nhân gây lỗi. Phương thức của `@BeforeTask` và `@AfterTask` nhận `TaskExecution`. Cả ba phương thức trả về `void`, phù hợp với vai trò xử lý sự kiện vòng đời.

## 4. Xây dựng ứng dụng mẫu hoàn chỉnh

Ví dụ sau tạo một task chạy một bước nhập dữ liệu giả lập, có thể thành công hoặc cố ý ném ngoại lệ. Listener ghi thông báo cho từng mốc và đặt `exitMessage` khi có lỗi.

Ví dụ dùng **JDK 17**, **Spring Boot 3.4.5**, **Spring Cloud 2024.0.2** và H2 lưu ra tệp. Đây là cặp phiên bản cùng thế hệ cho mục đích học tập; nếu dùng bản khác, hãy chọn release train Spring Cloud tương thích với Spring Boot.

### 4.1. Cấu trúc dự án

```text
task-listener-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/tasklistener/
    │   ├── TaskListenerApplication.java
    │   ├── ImportRunner.java
    │   └── AuditTaskListener.java
    └── resources/
        └── application.yml
```

### 4.2. Cấu hình `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>task-listener-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2024.0.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-cloud-starter-task` cung cấp hạ tầng Task và các annotation listener; `spring-boot-starter-jdbc` kết nối metadata với database; H2 giúp quan sát lịch sử nhiều lần chạy.

### 4.3. Cấu hình datasource và task

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: task-listener-demo
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./data/listenerdb;DB_CLOSE_ON_EXIT=FALSE
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: task-listener-demo
      initialize-enabled: true
      closecontext-enabled: true
```

`web-application-type: none` tắt máy chủ web vì đây là ứng dụng hữu hạn. H2 file lưu metadata sau khi tiến trình kết thúc; đường dẫn `./data/listenerdb` được tính từ thư mục chạy lệnh. `initialize-enabled: true` phù hợp cho khởi tạo bảng thử nghiệm. Với môi trường production, nên dùng database bền vững, quản lý schema bằng migration và chuyển `initialize-enabled` thành `false`.

### 4.4. Lớp Spring Boot

Tạo `TaskListenerApplication.java`:

```java
package com.example.tasklistener;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class TaskListenerApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskListenerApplication.class, args);
    }
}
```

### 4.5. Runner thực thi công việc hữu hạn

Tạo `ImportRunner.java`:

```java
package com.example.tasklistener;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("[RUN] Bắt đầu nhập dữ liệu");

        try {
            Thread.sleep(500);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        }

        if (args.containsOption("fail")) {
            throw new IllegalStateException("Giả lập lỗi nhập dữ liệu");
        }

        System.out.println("[RUN] Nhập dữ liệu hoàn tất");
    }
}
```

Thông thường, runner kết thúc sau khi hoàn thành nghiệp vụ. Trong ví dụ lỗi, ngoại lệ không được bắt và bỏ qua nên Spring Boot có thể báo việc chạy runner thất bại, cho phép Spring Cloud Task ghi nhận lần thực thi không thành công.

**Điểm mấu chốt:** Một listener chỉ *quan sát vòng đời*. Nó không tự biết một nghiệp vụ đã thất bại nếu runner bắt mọi lỗi rồi trả về bình thường.

### 4.6. Listener theo ba annotation

Tạo `AuditTaskListener.java`:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("[BEFORE] " + execution.getTaskName());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable cause) {
        System.err.println("[FAILED] " + execution.getTaskName()
                + " - " + cause.getClass().getSimpleName());

        // Thông điệp ngắn, không chứa secret hoặc stack trace.
        execution.setExitMessage(
                "Import failed: " + cause.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("[AFTER] " + execution.getTaskName());

        // Không ghi đè exitMessage ở đây: cần giữ thông điệp lỗi
        // mà @FailedTask đã thiết lập nếu lần chạy thất bại.
    }
}
```

Listener này chỉ ghi thông tin cần thiết và đặt `exitMessage` ngắn khi lỗi. Hãy lưu ý `@AfterTask` chạy **trước** khi repository được cập nhật trạng thái cuối, nên đừng viết code giả định `getEndTime()` hoặc `getExitCode()` ở thời điểm callback đã là dữ liệu cuối cùng trong database.

## 5. Chạy và nhận biết thứ tự callback

Trong thư mục dự án, tạo thư mục dữ liệu và đóng gói:

```bash
mkdir -p data
mvn clean package
```

Trên PowerShell có thể tạo thư mục bằng lệnh `New-Item -ItemType Directory -Force data`.

### 5.1. Lần chạy thành công

```bash
java -jar target/task-listener-demo-0.0.1-SNAPSHOT.jar
```

Các dòng log do ví dụ phát ra theo luồng thành công:

```text
[BEFORE] task-listener-demo
[RUN] Bắt đầu nhập dữ liệu
[RUN] Nhập dữ liệu hoàn tất
[AFTER] task-listener-demo
```

Các log chuẩn của Spring Boot có thể xuất hiện xen giữa. `@FailedTask` **không** được gọi trong nhánh này vì không có lỗi chưa xử lý.

### 5.2. Lần chạy thất bại

```bash
java -jar target/task-listener-demo-0.0.1-SNAPSHOT.jar --fail
```

Những dòng log nghiệp vụ và listener cần quan sát:

```text
[BEFORE] task-listener-demo
[RUN] Bắt đầu nhập dữ liệu
[FAILED] task-listener-demo - IllegalStateException
[AFTER] task-listener-demo
```

Trong thực tế, Spring Boot cũng sẽ ghi log stack trace của lỗi và tiến trình có thể trả mã thoát khác `0`. Thứ tự dòng giữa `stdout` và `stderr` có thể không hoàn toàn giống thứ tự callback khi terminal hoặc công cụ thu thập log gộp hai luồng; để xác minh chính xác, có thể dùng cùng một logger cho các callback.

`@FailedTask` được gọi do có **ngoại lệ chưa xử lý** và chạy trước `@AfterTask`. Vì thế thông điệp `Import failed: IllegalStateException` có thể được ghi vào metadata cuối của lần thực thi.

### 5.3. Đối chiếu kết quả qua `TaskRepository`

Sau khi JAR kết thúc, dùng H2 console hoặc JDBC client kết nối đến cùng database tại `jdbc:h2:file:./data/listenerdb`, tài khoản `sa`, mật khẩu rỗng. Nếu mở SQL client từ thư mục khác, dùng đường dẫn file tuyệt đối để tránh kết nối nhầm database H2.

```sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
```

Kết quả kỳ vọng về mặt ý nghĩa:

| Lần chạy | Callback xảy ra | Thông tin được kiểm tra |
| --- | --- | --- |
| Thành công | `@BeforeTask` → `@AfterTask` | Mã thoát thành công, thời điểm kết thúc có giá trị. |
| Thất bại với `--fail` | `@BeforeTask` → `@FailedTask` → `@AfterTask` | Mã thoát báo lỗi, có `ERROR_MESSAGE`; `EXIT_MESSAGE` chứa thông điệp listener đặt. |

`EXIT_MESSAGE` là thông điệp tóm tắt do ứng dụng hoặc listener chủ động đặt. `ERROR_MESSAGE` thường chứa thông tin ngoại lệ mà Spring Cloud Task thu thập. `EXIT_CODE` thể hiện trạng thái kết thúc. Ba dữ liệu có mục đích khác nhau; không thể thay thế việc kiểm tra mã thoát bằng việc chỉ thấy một chuỗi thông điệp.

## 6. Đặt `exitMessage` và quy tắc ghi đè

Spring Cloud Task cho phép gọi `TaskExecution.setExitMessage(String)` trong các sự kiện listener. Đây là nơi thích hợp để bổ sung một thông điệp dễ đọc cho vận hành, ví dụ số bản ghi đã xử lý hoặc mã lỗi nghiệp vụ.

```java
@AfterTask
public void after(TaskExecution execution) {
    execution.setExitMessage("Processing finished");
}
```

Đoạn trên hợp lệ về API, nhưng **không nên áp dụng nguyên xi nếu bạn đã đặt thông điệp lỗi trong `@FailedTask`**: callback kết thúc được gọi sau callback lỗi nên chuỗi `Processing finished` có thể ghi đè thông tin thất bại hữu ích.

Tài liệu Spring Cloud Task nêu thứ tự ưu tiên giữa các listener khi chúng đều sửa `exitMessage`:

| Mức ưu tiên | Callback | Ý nghĩa |
| --- | --- | --- |
| Cao nhất | `@AfterTask` / `onTaskEnd` | Giá trị được đặt ở đây có thể ghi đè giá trị từ các mốc trước. |
| Trung bình | `@FailedTask` / `onTaskFailed` | Có thể ghi đè thông điệp đặt lúc bắt đầu khi lỗi xảy ra. |
| Thấp nhất | `@BeforeTask` / `onTaskStartup` | Thông điệp ban đầu có thể được giữ nếu callback sau không thay đổi nó. |

Ví dụ thực tế: `@FailedTask` đặt `"IMPORT_FAILED"`, còn `@AfterTask` không sửa `exitMessage` thì thông điệp lỗi được giữ. Nếu `@AfterTask` luôn gán `"DONE"` thì có thể vô tình che thông tin lỗi.

**Không dùng `exitMessage` để thay đổi logic thành công/thất bại.** Muốn hệ thống điều phối biết lỗi, hãy để ngoại lệ nghiệp vụ được lan truyền phù hợp hoặc dùng cơ chế mã thoát của Spring Boot. Một lời nhắn `"FAILED"` trong metadata không nhất thiết làm `EXIT_CODE` khác `0`.

Không lưu mật khẩu, token, dữ liệu cá nhân hay stack trace đầy đủ trong `exitMessage`. Metadata Task có thể được nhiều công cụ vận hành đọc lại trong thời gian dài.

## 7. Xử lý ngoại lệ bên trong listener

Listener tham gia vào luồng quản lý vòng đời; chính nó cũng có thể gây lỗi nếu gọi API ngoài, kết nối tới hệ thống giám sát hoặc thực thi mã có ngoại lệ.

Tài liệu Spring Cloud Task mô tả rằng khi một listener ném ngoại lệ, **những listener còn lại của cùng sự kiện có thể không được gọi tiếp**. Việc tính mã thoát còn phụ thuộc vào sự kiện và cách framework giải quyết ngoại lệ. Cụ thể, lỗi trong `onTaskStartup` có thể làm task kết thúc với mã `1`; ngoại lệ trong callback `onTaskEnd` hoặc `onTaskFailed` có quy tắc xử lý mã thoát khác, và `ExitCodeExceptionMapper` không phải cách đáng tin cậy để ghi đè mã thoát của chính lỗi listener.

Vì vậy, nên giữ listener **ngắn, ổn định và có giới hạn tài nguyên**:

1. Chỉ ghi log và các chỉ số cần thiết; tránh công việc dài hoặc xử lý nghiệp vụ quan trọng ngay trong callback.
2. Khi gửi metric hoặc audit tới dịch vụ ngoài, thiết lập timeout rõ ràng để tránh làm treo quá trình kết thúc task.
3. Nếu lỗi của hệ thống ghi metric **không nên** làm thay đổi kết quả nghiệp vụ, có thể bắt ngoại lệ cục bộ, ghi một cảnh báo an toàn và tiếp tục.
4. Nếu một thao tác là điều kiện bắt buộc để coi công việc là hoàn tất, đặt nó trong **runner hoặc service nghiệp vụ**, nơi có thể xử lý và lan truyền lỗi minh bạch.
5. Tránh để callback `@AfterTask` xóa hoặc ghi đè `exitMessage` của lỗi nghiệp vụ.

Ví dụ ghi log có xử lý lỗi phụ trợ:

```java
@AfterTask
public void after(TaskExecution execution) {
    try {
        monitoringService.recordTaskFinished(execution.getTaskName());
    } catch (RuntimeException monitoringError) {
        // Chỉ cảnh báo, vì lỗi ở hệ thống metric không phải lỗi nhập dữ liệu.
        System.err.println("Không gửi được metric kết thúc: "
                + monitoringError.getClass().getSimpleName());
    }
}
```

`monitoringService` là một service giả định cần được inject vào Spring bean; đoạn này chỉ minh họa nguyên tắc xử lý phụ trợ, không phải mã hoàn chỉnh để thay trực tiếp `AuditTaskListener` ở phần trước.

**Trường hợp đặc biệt:** Nếu ứng dụng bị kill cưỡng bức, máy chủ mất điện hoặc JVM không hoàn tất vòng đời Spring, không thể bảo đảm `@FailedTask` hay `@AfterTask` sẽ được gọi. Với hệ thống vận hành, phải kết hợp `TaskRepository`, trạng thái process, scheduler và log thay vì phụ thuộc duy nhất vào listener.

## 8. Annotation listener và triển khai giao diện

Ba annotation là cú pháp thuận tiện khi chỉ cần gắn hành vi vào một vài phương thức trên Spring bean. Với listener cần dùng chung, bạn có thể triển khai giao diện `TaskExecutionListener`:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class InterfaceTaskListener implements TaskExecutionListener {

    @Override
    public void onTaskStartup(TaskExecution execution) {
        System.out.println("Startup: " + execution.getTaskName());
    }

    @Override
    public void onTaskFailed(TaskExecution execution, Throwable cause) {
        System.err.println("Failed: " + cause.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        System.out.println("End: " + execution.getTaskName());
    }
}
```

Đây là một **phương án thay thế**, không nên tự động đăng ký đồng thời với `AuditTaskListener` của ví dụ nếu bạn chỉ muốn mỗi sự kiện được log một lần. Cả hai cách đều dựa vào cùng các thời điểm vòng đời.

| Tiêu chí | Annotation trên bean | Triển khai `TaskExecutionListener` |
| --- | --- | --- |
| Cách khai báo | `@BeforeTask`, `@FailedTask`, `@AfterTask` trên phương thức | Override ba phương thức của interface |
| Khi dùng phù hợp | Bean chỉ cần thêm một hoặc vài callback | Lớp chuyên trách toàn bộ vòng đời task |
| Tham số | `TaskExecution`, thêm `Throwable` cho lỗi | Tương ứng qua chữ ký interface |
| Cách đăng ký | Spring bean được framework quét annotation | Spring bean triển khai interface |
| Tác động nghiệp vụ | Nên hạn chế ở giám sát, audit, thông điệp kết quả | Cũng nên tuân thủ nguyên tắc tương tự |

## 9. Listener trong xử lý bất đồng bộ và Spring Batch

### 9.1. Công việc bất đồng bộ

Nếu `ApplicationRunner` gọi `CompletableFuture.runAsync(...)` rồi **trả về ngay**, Spring Cloud Task có thể hoàn tất vòng đời trong khi worker vẫn làm việc. Trong trường hợp đó, `@AfterTask` có thể xảy ra **trước khi công việc con hoàn thành**, khiến log và metadata không phản ánh đúng kết quả nghiệp vụ.

Muốn trạng thái task đáng tin cậy:

- Runner phải đợi toàn bộ công việc con bắt buộc hoàn tất, ví dụ với `CompletableFuture.allOf(...).get(...)` hoặc `Future.get()`.
- Phải xử lý timeout, hủy công việc còn lại khi phù hợp và **lan truyền lỗi** từ worker về runner.
- Listener chỉ chạy thao tác quan sát sau khi runner đã bảo đảm điều kiện hoàn tất; không dùng listener làm nơi “đợi nốt” các future bị bỏ quên.

### 9.2. Khi task chạy một Spring Batch job

Một ứng dụng có thể kết hợp **Spring Cloud Task** và **Spring Batch**:

| Cấp độ | Dữ liệu và listener |
| --- | --- |
| Toàn ứng dụng | `TaskExecution` trong `TaskRepository`, cùng các listener của Spring Cloud Task |
| Job xử lý dữ liệu | `JobExecution`, `JobRepository` và `JobExecutionListener` của Spring Batch |
| Step xử lý cụ thể | `StepExecution`, `StepExecutionListener` và các listener đọc/xử lý/ghi của Spring Batch |

`@BeforeTask` và `@AfterTask` không thay `beforeJob` hoặc `afterStep`. Nếu `JobLauncher` chạy bất đồng bộ, runner cần theo dõi đến khi job thực sự kết thúc nếu muốn `TaskExecution` bao trùm kết quả Batch. Khi Batch job thất bại, không mặc định lỗi sẽ tự được truyền vào callback `@FailedTask` của ứng dụng: điều đó phụ thuộc cách launcher, runner và mã nghiệp vụ chuyển trạng thái Batch thành ngoại lệ/mã thoát.

## 10. Vận hành an toàn và các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không thấy `@BeforeTask` được gọi | Class chưa là Spring bean, sai package quét hoặc chưa cấu hình Task | Kiểm tra `@Component`, package quét, `@EnableTask` và dependency. |
| `@FailedTask` không chạy dù log có lỗi | Runner bắt ngoại lệ rồi trả về bình thường | Để lỗi cần thiết được lan truyền hoặc quản lý mã thoát phù hợp. |
| `@AfterTask` xuất hiện ở lần thất bại | Đây là callback **kết thúc**, không phải callback chỉ dành cho thành công | Tách logic lỗi sang `@FailedTask`; không đồng nhất `After` với `Success`. |
| Thông điệp lỗi biến mất khỏi `EXIT_MESSAGE` | `@AfterTask` ghi đè thông điệp do `@FailedTask` đặt | Chỉ ghi thông điệp kết thúc khi thực sự cần, giữ nguyên thông điệp lỗi. |
| Không thấy thông tin kết thúc trong database khi ở `@AfterTask` | Callback chạy trước khi repository cập nhật trạng thái cuối | Truy vấn sau khi task kết thúc. |
| Listener gửi metric làm task treo | Gọi dịch vụ ngoài không có timeout | Dùng thao tác ngắn, timeout và chính sách lỗi phụ trợ rõ ràng. |
| Không có `@FailedTask` khi pod bị kill | Process không đi qua vòng đời Spring bình thường | Kết hợp giám sát container, trạng thái scheduler, log và DB. |
| Một sự kiện bị log hai lần | Đăng ký hai listener làm cùng việc | Kiểm tra số bean và phân chia trách nhiệm của từng listener. |
| Task báo thành công dù worker lỗi | Runner không đợi hoặc không đọc lỗi từ future | Chờ công việc con và lan truyền lỗi trước khi trả về. |

Với task chạy theo lịch qua `cron`, Kubernetes `Job`/`CronJob` hay một hệ thống điều phối, listener giúp bổ sung log có cấu trúc và metadata dễ truy vết. Tuy nhiên, Spring Cloud Task **không tự lên lịch**; nó chỉ theo dõi một lần chạy ứng dụng. Nên lưu giữ `TaskExecution` trong database bền vững, cấu hình thời gian chờ hợp lý và có chính sách retry/idempotency ở phần nghiệp vụ.

Để ghép log giữa nhiều lần chạy, sử dụng ID của `TaskExecution` khi ID đã được cấp và ổn định. Ở callback `@BeforeTask`, framework đang ở thời điểm **trước khi lưu bản ghi bắt đầu**, nên không nên giả định ID hay những trường metadata cuối cùng đã đầy đủ. Khi ứng dụng chạy nhiều bản sao, tránh dùng biến static để tích lũy thông tin vòng đời giữa các lần chạy.

## 11. Tự kiểm tra và thực hành

### Bài tập 1: Quan sát hai nhánh vòng đời

1. Chạy ví dụ không có tham số và ghi lại thứ tự `BEFORE → RUN → AFTER`.
2. Chạy lại với `--fail` và xác nhận `FAILED` xuất hiện trước `AFTER`.
3. Truy vấn `TASK_EXECUTION`, đối chiếu `EXIT_CODE`, `EXIT_MESSAGE` và `ERROR_MESSAGE` giữa hai lần.

### Bài tập 2: Kiểm soát thông điệp kết thúc

Thêm code `execution.setExitMessage("DONE")` vào `@AfterTask` rồi thử `--fail`. Quan sát thông điệp lỗi do `@FailedTask` đặt bị ảnh hưởng thế nào. Sau đó sửa để giữ lại thông điệp lỗi.

### Bài tập 3: Thiết kế listener dùng trong production

Giả sử task nhập đơn hàng cần ghi metric thời lượng, thông báo thất bại và lưu số bản ghi thành công. Hãy phân chia rõ việc nào thuộc runner/service nghiệp vụ, việc nào thuộc callback, loại thông tin nào nên ghi vào `exitMessage` và cách xử lý khi dịch vụ giám sát bên ngoài bị lỗi.

### Câu hỏi ôn tập

1. `@BeforeTask` chạy trước hay sau khi `TaskExecution` bắt đầu được lưu vào repository?
2. Vì sao `@AfterTask` không có nghĩa task đã thành công?
3. Chữ ký `@FailedTask` khác gì so với `@BeforeTask` và `@AfterTask`?
4. Điều gì xảy ra nếu runner bắt lỗi nhưng không ném lại?
5. Vì sao `@AfterTask` có thể làm mất `exitMessage` đặt ở `@FailedTask`?
6. Vì sao không nên thực hiện các tác vụ I/O dài hoặc không có timeout trong listener?
7. Khi kết hợp Spring Batch, vì sao `@AfterTask` không thay thế `JobExecutionListener`?

**Ghi nhớ:** `@BeforeTask` giúp quan sát khởi đầu, `@FailedTask` nhận lỗi chưa xử lý và `@AfterTask` quan sát kết thúc **bất kể thành công hay thất bại**. Dùng listener cho giám sát và thông điệp thực thi, còn logic nghiệp vụ và quyết định thành công/thất bại phải được xử lý rõ ràng trong luồng chạy của task.

## Tài liệu tham khảo

- [Spring Cloud Task 3.2 — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/3.2/features.html): mốc callback, xử lý ngoại lệ trong listener và thứ tự ưu tiên `exitMessage`.
- [Spring Cloud Task — Annotation `FailedTask` API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/annotation/FailedTask.html): cú pháp và chữ ký callback nhận `TaskExecution`, `Throwable`.
