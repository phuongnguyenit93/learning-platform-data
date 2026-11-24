# Xác nhận yêu cầu khởi chạy và theo dõi kết quả hoàn tất

Trong chương **Khởi chạy** của module **SPRING_CLOUD_TASK**, một hệ thống có thể bắt đầu tác vụ Spring Cloud Task từ giao diện quản trị, API, bộ lập lịch hoặc thông điệp. Việc gửi yêu cầu thường rất nhanh, trong khi tác vụ có thể cần nhiều phút để thực hiện. Vì vậy cần trả lời **hai câu hỏi khác nhau**:

1. **Yêu cầu đã được hệ thống khởi chạy tiếp nhận hay chưa?** (launch acknowledgement).
2. **Tác vụ thực sự đã kết thúc chưa và kết quả có thành công không?** (completion verification).

Đây không phải cùng một trạng thái. Một lệnh khởi chạy được chấp nhận vẫn có thể thất bại ở bước tải artifact, tạo container, khởi tạo `ApplicationContext`, chạy nghiệp vụ hoặc ghi kết quả cuối vào `TaskRepository`. Ngược lại, nếu phản hồi HTTP bị mất sau khi server đã tiếp nhận yêu cầu, người gọi có thể tưởng thất bại và vô tình khởi chạy **hai lần**.

Bài này dùng **Spring Cloud Data Flow (SCDF)** làm ví dụ cho một bộ điều phối tác vụ, đồng thời giải thích cách áp dụng nguyên tắc tương tự với Kubernetes Job, scheduler và `TaskLaunchRequest` qua Spring Cloud Stream. Trọng tâm là xây dựng chuỗi theo dõi từ **yêu cầu** → **lần thực thi** → **kết quả nghiệp vụ** và vận hành retry an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `accepted`, `launched`, `running`, `completed`, `failed` và trạng thái chưa xác định.
- Nhận diện ID của **yêu cầu khởi chạy**, `TaskExecution.executionId` và ID bên ngoài (pod/job/runtime); không dùng lẫn chúng.
- Gọi API khởi chạy task trong SCDF và sử dụng ID/đường dẫn từ phản hồi để tra cứu.
- Thiết kế polling có timeout, backoff, kiểm tra `endTime`, `exitCode`, `exitMessage` và điều kiện thành công nghiệp vụ.
- Theo dõi lỗi trước khi `ApplicationContext` khởi tạo xong, tiến trình bị kill và trường hợp metadata chưa cập nhật.
- Xử lý việc mất phản hồi khởi chạy mà không tạo trùng tác vụ.
- Phối hợp mã thoát của Spring Cloud Task với trạng thái `JobExecution` khi tác vụ chạy Spring Batch.
- Đề xuất giám sát, cảnh báo và nguyên tắc bảo mật đối với ứng dụng chạy theo lịch hoặc theo yêu cầu.

## 2. Ba cấp độ xác nhận

Một yêu cầu chạy báo cáo cuối ngày có thể đi qua các giai đoạn:

~~~mermaid
flowchart TD
    A["Người dùng / scheduler gửi yêu cầu"] --> B{"Bộ điều phối tiếp nhận?"}
    B -->|"Không"| X["Bị từ chối / không rõ đã nhận"]
    B -->|"Có"| C["ACK + mã yêu cầu / execution id"]
    C --> D["Tạo process / Kubernetes Job / pod"]
    D --> E["Spring Boot khởi tạo ApplicationContext"]
    E --> F["Spring Cloud Task ghi START khi có thể"]
    F --> G["ApplicationRunner / Spring Batch xử lý"]
    G --> H["Ghi kết quả và trạng thái kết thúc khi có thể"]
    H --> I["Process thoát; điều phối cập nhật trạng thái"]
    I --> J{"Dữ liệu nghiệp vụ đúng?"}
    J -->|"Có"| K["Xác nhận hoàn tất"]
    J -->|"Không"| L["Thất bại / cần đối soát"]
    D -. "Có thể lỗi" .-> L
    E -. "Có thể lỗi sớm" .-> L
    G -. "Có thể lỗi" .-> L
~~~

Ta nên phân biệt **ba mức bằng chứng**:

| Mức | Bằng chứng | Điều chứng minh được | Điều **chưa** chứng minh |
| --- | --- | --- | --- |
| **Tiếp nhận** | HTTP 201/202, phản hồi launcher, message được nhận | Bộ điều phối đã chấp nhận hoặc đăng ký yêu cầu theo hợp đồng API | Ứng dụng thực sự chạy, dữ liệu đã tạo |
| **Thực thi** | Process/pod/Job đang chạy, `TaskExecution` có `startTime` | Đã có hoạt động thực thi được một hoặc nhiều hệ thống quan sát | Tác vụ hoàn tất thành công |
| **Hoàn tất** | Runtime kết thúc, `TaskExecution.endTime` và `exitCode`, kết quả đầu ra đã xác minh | Có bằng chứng để phân loại kết quả | Mọi tác động bên ngoài đều nguyên tử nếu không thiết kế thêm |

Điều cần tránh là đánh đồng **"Launched task"** với **"Task completed successfully"**. Lời xác nhận từ launcher thường là tín hiệu của bước đầu, không phải chứng nhận kết quả nghiệp vụ.

## 3. Các định danh cần ghi lại từ đầu

Trong một hệ thống có nhiều lần thử, nên phân biệt:

| Định danh | Ai tạo? | Công dụng | Có giữ nguyên qua retry? |
| --- | --- | --- | --- |
| `requestId` / `runId` do ứng dụng điều phối định nghĩa | API/scheduler trước khi launch | Định danh **một yêu cầu nghiệp vụ** và nối log | **Nên giữ nguyên** nếu retry cùng yêu cầu |
| `TaskExecution.executionId` | Spring Cloud Task / SCDF theo cơ chế lưu metadata | Định danh **một lần thực thi vật lý** | Thường **khác nhau** giữa các lần chạy |
| `externalExecutionId` | Bộ triển khai/runtime khi tích hợp có hỗ trợ | Nối task với tiến trình, pod hoặc deployment trên nền tảng | Có thể khác nhau giữa các lần chạy |
| `JobExecutionId` | Spring Batch | Định danh một lần thực thi Batch Job | Có thể thay đổi giữa các lần chạy/restart |
| Business key | Hệ thống nghiệp vụ | Chống tạo trùng hiệu ứng, ví dụ `tenantId+businessDate+version` | **Phải ổn định** khi yêu cầu giống nhau |

**Ví dụ:** người dùng gửi yêu cầu `REQ-20261124-017` để tạo báo cáo ngày 24/11. Lần launch đầu có execution ID `101` nhưng kết thúc lỗi; lần thử lại có ID `102`. Cả hai cần liên hệ cùng `requestId` và business key, trong khi báo cáo nghiệp vụ chỉ nên xuất hiện một lần nếu đã được tạo thành công.

Không sử dụng `TASK_EXECUTION_ID` để chống ghi trùng dữ liệu nghiệp vụ: nó là ID kỹ thuật của **lần chạy**, không phải của **yêu cầu cần thực hiện**.

## 4. Ví dụ: phát lệnh khởi chạy bằng Spring Cloud Data Flow

Spring Cloud Data Flow hỗ trợ định nghĩa ứng dụng task và khởi chạy thông qua shell hoặc REST API. Ví dụ này giả định:

- SCDF server đã chạy ở địa chỉ minh họa `http://localhost:9393`.
- Task definition tên `dailySummary` đã được đăng ký và chứa artifact Spring Cloud Task tương thích.
- SCDF có platform được cấu hình để khởi chạy, đồng thời có nguồn dữ liệu metadata phù hợp.
- Người dùng/ứng dụng gọi API đã được cấp quyền thực hiện launch.

### 4.1. Khởi chạy qua Data Flow Shell

Ví dụ:

~~~text
dataflow:> task launch dailySummary --arguments "--businessDate=2026-11-24"
Launched task 'dailySummary'
~~~

Chuỗi `Launched task` nghĩa là lệnh launch đã được tiếp nhận/xử lý theo công cụ điều phối, **không đồng nghĩa** report đã được tạo. Tên task và cú pháp shell phải tương thích phiên bản SCDF đang chạy.

Ngay sau đó có thể theo dõi:

~~~text
dataflow:> task execution list --name dailySummary
dataflow:> task execution status --id 101
~~~

Giá trị `101` chỉ là ID minh họa, phải thay bằng ID của execution thực tế. Output và tập trường có thể thay đổi theo phiên bản SCDF, Spring Boot và cấu hình platform.

### 4.2. Khởi chạy bằng REST API

Tài liệu SCDF mô tả endpoint **`POST /tasks/executions/launch`** cho việc launch task. Ví dụ bằng `curl`:

~~~bash
curl -i -X POST "http://localhost:9393/tasks/executions/launch"   --data-urlencode "name=dailySummary"   --data-urlencode "arguments=--businessDate=2026-11-24"
~~~

Ví dụ phản hồi thành công, **chỉ để minh họa hình dạng dữ liệu**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/hal+json
~~~

~~~json
{
  "executionId": 101,
  "schemaTarget": "boot2",
  "_links": {
    "self": {
      "href": "http://localhost:9393/tasks/executions/101?schemaTarget=boot2"
    }
  }
}
~~~

Trong hệ thống thực, `executionId` là số được cấp mới; `schemaTarget` phụ thuộc loại schema/version, không được tự mặc định luôn là `boot2`. **Dùng nguyên `_links.self.href` trả về để theo dõi**, thay vì tự ghép URL/schema target khi không cần.

**Điểm then chốt:** HTTP `201 Created` và `executionId` là **phản hồi cho việc tạo/đăng ký lần thực thi**. Nó **không** hứa rằng tiến trình đã kết thúc hoặc `exitCode=0`.

Một số bản SCDF cũ có endpoint **`POST /tasks/executions`** (legacy); tài liệu SCDF phân biệt endpoint cũ với `/tasks/executions/launch` và nêu giới hạn của legacy endpoint với ứng dụng Spring Boot 3. Do đó đừng sao chép endpoint từ bài viết cũ mà không đối chiếu với server đang sử dụng.

## 5. Theo dõi đến khi hoàn tất

Sau khi nhận phản hồi launch, caller nên **lưu ID/đường dẫn tra cứu** rồi bắt đầu kiểm tra trạng thái ở một quy trình riêng. Với REST API SCDF, dùng link `self` trong phản hồi:

~~~bash
curl -i "http://localhost:9393/tasks/executions/101?schemaTarget=boot2"
~~~

Phản hồi thường có các trường tương tự:

~~~json
{
  "executionId": 101,
  "taskName": "dailySummary",
  "startTime": "2026-11-24T01:00:00",
  "endTime": "2026-11-24T01:00:08",
  "exitCode": 0,
  "exitMessage": "COMPLETED;rows=1500",
  "errorMessage": null,
  "externalExecutionId": "runtime-generated-id",
  "taskExecutionStatus": "COMPLETE"
}
~~~

Đây là **payload được rút gọn, có tính minh họa**, không phải phản hồi nguyên văn bắt buộc của API. Kiểu/trạng thái/tên trường và các liên kết HAL còn tùy version và platform. Ở các lần polling đầu tiên, `startTime`, `endTime`, `exitCode` hoặc status có thể chưa đầy đủ.

### Tiêu chí xác nhận kết thúc

Nên xét nhiều bằng chứng đồng thời:

1. **Trạng thái nền tảng:** pod/process/Job đã kết thúc hoặc ít nhất không còn chạy.
2. **Task metadata:** bản ghi có `endTime` và `exitCode` khi repository còn truy cập được.
3. **Mã kết quả:** `exitCode=0` theo chính sách ứng dụng là dấu hiệu thành công; khác `0` cần điều tra, nhưng không luôn đồng nghĩa mọi tác động nghiệp vụ đã rollback.
4. **Kết quả nghiệp vụ:** file, record báo cáo hoặc checksum đã tồn tại và khớp điều kiện cần thiết.
5. **Ngữ cảnh lỗi:** xem `errorMessage`, `exitMessage` và log để hiểu nguyên nhân.

**`endTime=null` không đủ để kết luận "đang chạy"**: process có thể chết trước khi cập nhật metadata. Ngược lại, ứng dụng có thể ghi metadata cuối trước khi mọi tài nguyên runtime được hệ điều hành thu hồi. Khi dữ liệu mâu thuẫn, nên chuyển sang đối soát chứ không suy đoán kết quả.

## 6. Thiết kế polling đúng cách

Polling là việc gọi lại endpoint trạng thái theo khoảng thời gian, **không phải gửi lại lệnh launch**. Nếu liên tục `POST /launch`, bạn có thể tạo thêm nhiều lần thực thi.

Quy trình đề xuất:

~~~text
POST /launch (đúng một lần cho requestId khi chưa biết đã được tiếp nhận)
    -> lưu executionId và self href
    -> GET self href sau một khoảng chờ
    -> nếu chưa kết thúc: chờ với backoff rồi GET lại
    -> nếu kết thúc: kiểm tra exitCode và kết quả nghiệp vụ
    -> nếu quá deadline hoặc nguồn theo dõi lỗi: UNKNOWN, cảnh báo/đối soát
~~~

Ví dụ thuật toán **mã giả**, không phải API Java cụ thể:

~~~java
LaunchReceipt receipt = launcher.launchOnce(requestId, arguments);
saveReceipt(requestId, receipt.executionId(), receipt.statusUrl());

long deadline = clock.millis() + timeoutMillis;
long delay = initialDelayMillis;

while (clock.millis() < deadline) {
    TaskState state = monitor.fetch(receipt.statusUrl());

    if (state.hasTerminalPlatformState()) {
        return reconcileTaskAndBusinessResult(requestId, state);
    }

    sleep(delay);
    delay = Math.min(maxDelayMillis, delay * 2);
}

return markNeedsReconciliation(requestId, "TIMEOUT_WAITING_FOR_COMPLETION");
~~~

Các interface `LaunchReceipt`, `TaskState`, `launcher` và `monitor` chỉ là **khái niệm thiết kế**, không phải class có sẵn trong Spring Cloud Task. Cần xử lý `HTTP 404/429/5xx`, đứt mạng, timeout và retry của lệnh GET trong implementation.

### Những nguyên tắc polling quan trọng

- **Có deadline:** một lần chạy quá lâu cần có trạng thái `TIMED_OUT` hoặc `UNKNOWN` ở hệ thống điều phối và cảnh báo.
- **Có backoff/jitter:** không poll mỗi vài mili-giây, nhất là khi hàng nghìn task đồng thời.
- **Không lặp POST:** poll bằng GET status, chỉ launch lại khi có quyết định nghiệp vụ an toàn.
- **Không xem 404 tức thì là "chưa từng chạy":** có thể là sai schema target, nguồn dữ liệu chưa đồng bộ, record bị xóa hoặc cấu hình environment không khớp.
- **Giữ nguyên correlation ID:** log lần polling và kết quả phải nối được với request ban đầu.
- **Tách trạng thái chưa biết:** nếu REST/server/JDBC không phản hồi, đừng chuyển thẳng sang "FAILED" hoặc "SUCCESS" khi chưa đủ bằng chứng.

## 7. Mô hình trạng thái ở tầng điều phối

Một API nội bộ có thể tạo trạng thái riêng để trình bày rõ tiến trình. Các tên dưới đây là **đề xuất nghiệp vụ**, **không phải enum mặc định** của Spring Cloud Task hoặc Spring Cloud Data Flow:

| Trạng thái điều phối | Ý nghĩa | Có thể chuyển tiếp đến |
| --- | --- | --- |
| `RECEIVED` | Đã nhận và lưu yêu cầu có `requestId` | `LAUNCHING`, `REJECTED` |
| `LAUNCHING` | Đang yêu cầu platform tạo lần chạy | `ACCEPTED`, `UNKNOWN`, `REJECTED` |
| `ACCEPTED` | Đã có phản hồi launch/ID theo hợp đồng | `RUNNING`, `FAILED`, `UNKNOWN` |
| `RUNNING` | Có bằng chứng tiến trình đang xử lý | `SUCCEEDED`, `FAILED`, `UNKNOWN` |
| `SUCCEEDED` | Đã đối soát hoàn tất theo điều kiện nghiệp vụ | Kết thúc |
| `FAILED` | Đã có bằng chứng thất bại | Điều tra/ retry có điều kiện |
| `UNKNOWN` | Chưa đủ bằng chứng xác định kết quả | Đối soát, chờ/điều tra |
| `REJECTED` | Không chấp nhận yêu cầu | Sửa đầu vào/quyền, rồi gửi yêu cầu mới |

Hệ thống thực tế có thể thấy **quá trình chạy ngắn hơn chu kỳ polling**. Một task có thể hoàn tất quá nhanh khiến bạn không bao giờ quan sát được trạng thái `RUNNING`; điều đó không làm việc theo dõi sai nếu kết quả cuối được xác minh đầy đủ.

### Không tự chế trạng thái "đã thành công" từ HTTP 201

Nếu thiết kế API riêng cho người dùng, có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /api/task-requests/REQ-20261124-017
~~~

~~~json
{
  "requestId": "REQ-20261124-017",
  "status": "ACCEPTED",
  "statusUrl": "/api/task-requests/REQ-20261124-017"
}
~~~

Đây là **ví dụ API do nhóm phát triển tự thiết kế**, **không phải endpoint mặc định của Spring Cloud Task**. Endpoint status có thể hiển thị `executionId`, thời điểm, kết quả nghiệp vụ và liên kết tới log hoặc SCDF, đồng thời tránh bắt người dùng chờ HTTP request ban đầu đến khi task hoàn tất.

## 8. Ví dụ ứng dụng Spring Cloud Task để kiểm tra kết quả

Giả sử `dailySummary` là một ứng dụng Spring Boot + Spring Cloud Task. Một runner đơn giản giúp minh họa các trường hợp thành công hoặc thất bại.

Tạo `src/main/java/com/example/task/DailySummaryApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DailySummaryApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DailySummaryApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner dailySummary() {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("businessDate");

            if (dates == null || dates.size() != 1
                    || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Cần đúng một --businessDate=YYYY-MM-DD");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            if (arguments.containsOption("failDemo")) {
                throw new IllegalStateException("Giả lập lỗi nghiệp vụ");
            }

            // Thực tế: gọi service xử lý có transaction và idempotency.
            System.out.println("Report completed for " + date);
        };
    }
}
~~~

Dự án cần `spring-cloud-starter-task`, Spring Boot starter và JDBC driver tương thích, với Spring Boot parent/BOM và Spring Cloud BOM phù hợp. Ví dụ phần dependency Maven:

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
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Để tạo JAR thực thi, dự án cũng cần `spring-boot-maven-plugin` trong phần `build` của `pom.xml`. Trong cấu hình chuẩn, Spring Cloud Task auto-configuration có thể quản lý metadata mà không cần thêm `@EnableTask` thủ công.

Cấu hình minh họa `application.yml`:

~~~yaml
spring:
  application:
    name: daily-summary
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: dailySummary
      initialize-enabled: false
~~~

Biến môi trường cần trỏ đến database metadata có schema Spring Cloud Task **đã được tạo phù hợp phiên bản**; ở môi trường SCDF, cách chia sẻ datasource, schema target và thuộc tính ứng dụng phụ thuộc cấu hình platform. Không hard-code mật khẩu vào `application.yml` được commit hoặc tham số launch. Ví dụ được rút gọn, không bao gồm toàn bộ pom/migration.

Chạy thành công bằng lệnh thông thường:

~~~bash
java -jar daily-summary.jar --businessDate=2026-11-24
~~~

Chạy lỗi có chủ đích trong môi trường thử nghiệm:

~~~bash
java -jar daily-summary.jar --businessDate=2026-11-24 --failDemo
~~~

Ở cả hai trường hợp, chương trình có thể **đã khởi động**, nhưng chỉ trường hợp đầu thực hiện xong logic demo. Nếu chạy qua SCDF, **đừng giả định phản hồi launch đã xác nhận kết quả của runner**; cần lấy lại execution status và kiểm tra repository/log.

Lưu ý: câu lệnh `System.out.println` chỉ minh họa điểm hoàn thành. Với báo cáo thật, phải kiểm tra record/file đầu ra đã commit/đã xuất và tính đúng đắn nghiệp vụ.

## 9. Truy vấn TaskRepository sau lần chạy

Với JDBC repository lưu bền vững, có thể kiểm tra metadata theo schema mặc định:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'dailySummary'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Câu SQL hữu ích khi đối soát, nhưng không thay thế việc dùng **API của SCDF** để tra cứu các thông tin riêng của platform như `externalExecutionId` hoặc trạng thái pod.

Diễn giải:

| Quan sát | Ý nghĩa khả dĩ | Điều cần đối chiếu |
| --- | --- | --- |
| `END_TIME IS NULL`, process còn chạy | Task có thể đang thực thi | Runtime, deadline và log |
| `END_TIME IS NULL`, process đã chết | Metadata kết thúc có thể chưa được ghi | Pod reason, kết nối DB, business output |
| `EXIT_CODE = 0` và có `END_TIME` | Framework ghi nhận một lần chạy hoàn tất với mã thành công | Kiểm tra nghiệp vụ đúng và đủ |
| `EXIT_CODE != 0` | Có lỗi theo mã thoát của Task | `ERROR_MESSAGE`, log, trạng thái Batch nếu dùng |
| Không có record | Có thể lỗi trước khi context sẵn sàng hoặc truy vấn sai DB/schema | Launcher, container, app logs, datasource/schema target |
| Có nhiều record cùng `TASK_NAME` | Nhiều lần thực thi, có thể do retry | Ghép bằng requestId/business key và xử lý trùng |

Nếu `EXIT_CODE` là `NULL`, không nên tự quy về `0`. Một record được khởi tạo nhưng chưa hoàn tất hoặc cập nhật không thành công có thể thiếu thông tin.

### Hai thời điểm dễ mất thông tin

Spring Cloud Task ghi nhận một lần thực thi sau khi `ApplicationContext` đã bootstrap đủ. Nếu bootstrap thất bại **trước khi TaskRepository tạo record**, bạn có thể thấy lỗi ở platform nhưng **không có `TaskExecution`**. Nếu JVM bị kill sau khi ghi kết quả nghiệp vụ nhưng trước lúc cập nhật repository, bạn có thể thấy record thiếu `END_TIME` dù công việc đã hoàn thành một phần hoặc toàn phần.

Vì thế hệ thống điều phối nên quản lý yêu cầu launch **độc lập** với repository, không dùng bảng Task làm nguồn duy nhất cho toàn bộ các lần **cố gắng** khởi chạy.

## 10. Khi phản hồi launch bị mất: tránh chạy trùng

Một trường hợp thường bị xử lý sai:

1. Client gửi yêu cầu `POST /launch`.
2. Server đã tiếp nhận và có thể tạo execution.
3. Mạng đứt trước khi client nhận phản hồi.
4. Client coi đây là thất bại chắc chắn và gửi lại POST.
5. Hai process cùng có thể được khởi chạy cho một business key.

Đó là vấn đề **kết quả tiếp nhận không xác định**, tương tự lỗi mất phản hồi quanh `COMMIT`. Không được cho rằng timeout của HTTP đồng nghĩa server chưa thực hiện lệnh.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orchestrator
    participant T as Task runtime
    C->>O: POST launch(requestId=REQ-17)
    O->>T: Khởi tạo lần chạy
    O--xC: Response ACK bị mất
    Note over C,O: Client chưa biết launch đã được tiếp nhận chưa
    C->>O: GET trạng thái REQ-17 / truy vấn theo correlation id
    O-->>C: ID và trạng thái đã lưu nếu có
    Note over C,T: Chỉ retry launch theo chính sách idempotent
~~~

### Thiết kế chống trùng ở tầng API điều phối

Nếu bạn xây API bên ngoài SCDF, nên có:

- `requestId` hoặc `idempotencyKey` do client cung cấp hoặc được server cấp ổn định.
- Bảng yêu cầu với ràng buộc `UNIQUE(request_id)`.
- Dữ liệu trạng thái `RECEIVED/LAUNCHING/ACCEPTED/...`, tham số đã kiểm tra và correlation ID.
- Sau khi có kết quả từ SCDF, ghi lại `executionId`/`self href` vào bản ghi yêu cầu.
- Khi client gửi lại **cùng** `requestId`, API trả lại trạng thái/receipt đã có thay vì tự launch lần thứ hai.
- Cùng `requestId` nhưng nội dung yêu cầu khác phải báo xung đột, không âm thầm thay tham số.

**Ranh giới khó:** nếu hệ thống API ghi `LAUNCHING` vào database, sau đó gửi lệnh launch cho SCDF và chết trước khi lưu execution ID, vẫn có một khoảng không rõ đã launch hay chưa. Một bảng unique chỉ chống tạo **yêu cầu trùng** tại API của bạn, **không tự bảo đảm exactly-once** qua hai hệ thống. Cần đối soát với SCDF/runtime bằng correlation ID và đồng thời làm nghiệp vụ idempotent.

### Không chỉ chống duplicate launch

Ngay cả khi chỉ có một execution, các retry bên trong Spring Batch, gọi API hoặc DB có thể tạo tác động lặp. Hãy dùng **business key ổn định** như `tenantId+businessDate+reportVersion` và ràng buộc unique/idempotency ở nơi ghi kết quả.

## 11. Spring Cloud Stream TaskLaunchRequest: ACK không phải completion

Spring Cloud Task hỗ trợ **khởi chạy một task từ stream** thông qua sink xử lý payload `TaskLaunchRequest`. Theo API, một `TaskLaunchRequest` mô tả:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `uri` | URI artifact của tác vụ |
| `applicationName` | Tên gắn với tác vụ được launcher tạo |
| `commandLineArguments` | Danh sách tham số dòng lệnh đưa cho task |
| `environmentProperties` | Biến môi trường cho lần chạy |
| `deploymentProperties` | Thuộc tính triển khai mà launcher/platform hiểu |

Ví dụ mã Java tạo request (ở ứng dụng phát yêu cầu, khi đã dùng đúng dependency):

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;

TaskLaunchRequest request = new TaskLaunchRequest(
        "maven://com.example:daily-summary-task:jar:1.0.0",
        List.of("--businessDate=2026-11-24"),
        Map.of(),
        Map.of(),
        "dailySummary");
~~~

Đoạn này minh họa cấu trúc request, **không phải một ứng dụng hoàn chỉnh tự gửi message**. Trong hệ thống sử dụng Spring Cloud Stream và một sink `@EnableTaskLauncher` tương thích, request có thể đến sink để được triển khai bằng `TaskLauncher`. URI artifact và lựa chọn deployer phụ thuộc môi trường.

Quan trọng là phân biệt:

1. **Message được broker ghi/consumer nhận:** thông điệp yêu cầu launch đã đi qua một phần luồng.
2. **Task launcher tiếp nhận:** sink có thể cố tạo process/deployment.
3. **Task hoàn tất:** ứng dụng riêng đã thực thi xong và ghi metadata theo điều kiện khả dụng.

Việc ACK một message ở broker **không chứng minh task đã hoàn tất**. Nếu consumer xử lý lặp thông điệp, có thể launch lặp trừ khi có chiến lược chống trùng. Nếu sink bị kill sau khi launch nhưng trước khi xác nhận message, cùng request có thể được nhận lại.

Không suy luận cơ chế reply/acknowledgement đồng bộ từ riêng class `TaskLaunchRequest`; cách trả receipt, correlation và theo dõi completion phải được thiết kế rõ trong kiến trúc thông điệp.

## 12. Kubernetes Job và scheduler: kiểm tra ở mức platform

Khi không dùng SCDF, cùng nguyên tắc áp dụng cho Kubernetes Job hoặc cron:

| Hệ thống | Bằng chứng đã tiếp nhận | Bằng chứng đã chạy | Bằng chứng kết thúc |
| --- | --- | --- | --- |
| Kubernetes | API server tạo `Job` object | Pod được tạo/đang `Running` | `Job.status.conditions`, `succeeded/failed`, Pod termination |
| Cron / scheduler hệ điều hành | Lịch hoặc lệnh thực thi được ghi nhận | PID/log bắt đầu | Exit code + log và metadata Task |
| API điều phối tự xây | HTTP `202 Accepted` + requestId | Runtime/external ID được ghi | Kết quả runtime + `TaskExecution` + dữ liệu nghiệp vụ |
| SCDF | Response launch có execution ID/schema target | Runtime status và Task metadata | Status cuối + exit code + đối soát |

Một Job object Kubernetes được tạo **không đồng nghĩa Pod đã bắt đầu**, và Pod đã chạy **không đồng nghĩa kết quả nghiệp vụ thành công**. Xem lý do lỗi cụ thể như image pull failure, thiếu secret, quota, scheduling failure, OOMKilled hoặc deadline exceeded.

Với Kubernetes, cần cấu hình `backoffLimit`, `activeDeadlineSeconds` và chính sách `concurrencyPolicy` nếu dùng CronJob theo mục tiêu vận hành. Các retry do platform điều khiển phải tương thích với khóa idempotency của nghiệp vụ; không để platform lặp một thao tác tạo tác động mới mà không kiểm tra.

## 13. Phối hợp với Spring Batch

Khi Spring Cloud Task gọi một **Spring Batch Job**:

- `TaskExecution` phản ánh vòng đời **ứng dụng task**.
- `JobExecution` và `StepExecution` phản ánh tiến độ/thất bại của **Batch Job** và các step.
- `JobRepository` của Batch hỗ trợ lưu trạng thái và restart theo chính sách của job.
- `BatchStatus` và `ExitStatus` không đồng nhất một cách tự nhiên với mã thoát Task hoặc kết quả nghiệp vụ.

Một điều kiện dễ bỏ sót là Batch Job thất bại nhưng ứng dụng không phản ánh điều đó vào exit code của Task. Khi phiên bản Spring Cloud Task hỗ trợ, có thể cân nhắc:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

Hãy thử với một job thất bại trên staging và xác minh **Batch FAILED → mã thoát Task không phải 0**, đồng thời kiểm tra trạng thái của process mà scheduler nhìn thấy. Property phải được đối chiếu theo phiên bản Task/Batch cụ thể.

Nếu job Batch kết thúc thành công nhưng nhiệm vụ hậu xử lý (upload file, thông báo) thất bại, cần quyết định điều đó có làm thất bại **task tổng thể** không. Không nên chỉ dùng trạng thái Job để báo thành công khi yêu cầu nghiệp vụ còn các bước khác.

## 14. Thiết kế API trả kết quả cho người dùng

Đối với giao diện quản trị, cách dễ hiểu là trả **receipt ngay** rồi cho phép lấy trạng thái qua endpoint riêng:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Task API
    participant O as SCDF / Scheduler
    participant R as TaskRepository
    U->>A: POST /api/task-requests
    A-->>U: 202 Accepted + requestId + statusUrl
    A->>O: Launch khi đã kiểm soát duplicate
    O-->>A: executionId / external id nếu có
    A->>R: Tra cứu metadata theo executionId
    R-->>A: start/end/exit khi đã ghi nhận
    U->>A: GET statusUrl
    A-->>U: RUNNING / SUCCEEDED / FAILED / UNKNOWN
~~~

Dữ liệu response nên trả **tối thiểu**:

~~~json
{
  "requestId": "REQ-20261124-017",
  "taskName": "dailySummary",
  "status": "SUCCEEDED",
  "executionId": 101,
  "startedAt": "2026-11-24T01:00:00Z",
  "finishedAt": "2026-11-24T01:00:08Z",
  "exitCode": 0,
  "result": {
    "reportId": "RPT-20261124-01"
  }
}
~~~

Đây là **schema API do bạn thiết kế**, không phải tài nguyên mặc định của SCDF. Đội phát triển cần thống nhất semantics:

- `SUCCEEDED` chỉ trả khi điều kiện hoàn tất được xác minh.
- `UNKNOWN` để biểu diễn thiếu hoặc mâu thuẫn dữ liệu, không phải lỗi mặc định.
- `FAILED` nên có mã lỗi có thể hiểu, nhưng không trả trực tiếp toàn bộ stack trace hoặc secret.
- `result` chỉ chứa thông tin nhỏ và liên kết tới dữ liệu nghiệp vụ thực tế; không nhét báo cáo lớn vào HTTP status response.

API nên có xác thực/phân quyền, giới hạn tần suất đọc status và chính sách retention/cleanup. Người dùng chỉ được xem thông tin thực thi thuộc phạm vi quyền của họ.

## 15. Lỗi và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| POST launch trả `201` nhưng không thấy báo cáo | Task chưa chạy, lỗi startup, runner lỗi hoặc output chưa được lưu | GET execution, kiểm tra log platform và business DB |
| POST timeout nhưng sau đó có hai lần chạy | Client retry POST không có idempotency/correlation | Xem request log, `executionId`, thiết kế requestId + chống trùng |
| Có execution ID nhưng `startTime=null` lâu | Chưa deploy/start được hoặc thiếu metadata | Platform status, image/artifact, quyền, broker/cluster |
| `endTime=null` nhưng pod đã chết | JVM bị kill hoặc TaskRepository không ghi được kết thúc | Pod reason, DB, log và đối soát kết quả |
| `exitCode=0` nhưng dữ liệu sai | Ứng dụng nuốt lỗi hoặc chưa kiểm tra invariant nghiệp vụ | Kiểm tra kết quả đã commit/được xuất |
| `exitCode!=0` nhưng output đã có | Output commit trước lỗi cập nhật bước sau | Xác minh idempotency và quyết định retry an toàn |
| API GET trả 404 | Sai execution ID/schema target, cleanup, dữ liệu chưa đồng bộ hoặc không đúng môi trường | Dùng self link gốc, xác minh datasource/schema |
| Polling kéo dài vô hạn | Không có deadline hoặc quên xử lý trạng thái UNKNOWN | Thêm timeout, backoff, alert |
| Batch status FAILED nhưng Task SUCCESS | Chính sách ánh xạ trạng thái chưa đúng | `fail-on-job-failure` và test exit code |
| Task được gọi nhiều lần do cron chồng lịch | Không có guard theo business key hoặc quản lý concurrency | Khóa unique, điều phối và chính sách skip/retry |

### Kiểm tra theo thứ tự nào?

1. **Lớp launch:** requestId, HTTP status, executionId, self link, log của server điều phối.
2. **Lớp runtime:** process/pod có được tạo, lỗi image/deployment/quota, exit code thực tế.
3. **Lớp TaskRepository:** `TaskExecution` có record không, thời gian/exit code/exit message gì.
4. **Lớp nghiệp vụ:** dữ liệu output đúng và đủ không, có tác động lặp không.
5. **Lớp Batch (nếu có):** `JobExecution`/`StepExecution` và restart state.
6. **Lớp giám sát:** event, log, correlation, cảnh báo và trạng thái kết luận.

Không chỉ nhìn một bảng hoặc một dòng log rồi tuyên bố thành công/thất bại khi các nguồn dữ liệu đang mâu thuẫn.

## 16. Checklist trước khi đưa vào vận hành

- [ ] API/scheduler lưu `requestId` bền vững trước khi launch.
- [ ] Phản hồi launch và trạng thái hoàn tất được thiết kế **riêng**, không dùng HTTP 201 thay cho business success.
- [ ] Lưu `executionId`, `schemaTarget`/self link và external runtime ID khi có.
- [ ] Theo dõi bằng polling có timeout/backoff hoặc kênh event phù hợp, không poll bằng cách gửi lại POST.
- [ ] Có trạng thái `UNKNOWN` và quy trình đối soát khi bootstrap lỗi sớm, JVM bị kill hoặc database mất kết nối.
- [ ] Kết quả cuối được kiểm chứng bằng exit code **và** invariant nghiệp vụ.
- [ ] Retry dùng business key ổn định; hệ thống chống duplicate cả ở tầng điều phối lẫn dữ liệu nghiệp vụ.
- [ ] Tác vụ chạy trên database metadata JDBC bền vững nếu cần theo dõi giữa nhiều lần chạy.
- [ ] Kiểm tra riêng trạng thái Spring Batch Job/Step và chính sách ánh xạ exit code nếu có.
- [ ] Có bảo mật cho API, log, tham số và dữ liệu trả về; không lộ secret hoặc stack trace.
- [ ] Đã thử kịch bản mất phản hồi launch, task thất bại lúc khởi động, process bị kill và timeout trong staging.

## 17. Bài tập và câu hỏi tự kiểm tra

**Câu hỏi 1.** SCDF trả HTTP `201 Created` và `executionId=101`. Điều này đã chứng minh rằng báo cáo ngày 24/11 được tạo thành công chưa? Vì sao?

**Câu hỏi 2.** Vì sao `requestId` do API/scheduler cấp nên giữ nguyên qua các lần thử, còn `TASK_EXECUTION_ID` có thể thay đổi?

**Câu hỏi 3.** Nếu `endTime=null` nhưng Kubernetes báo Job đã thất bại, bạn sẽ kiểm tra những nguồn dữ liệu nào trước khi cho chạy lại?

**Câu hỏi 4.** Polling khác với retry launch như thế nào? Lỗi gì có thể xảy ra nếu frontend cứ gọi POST launch mỗi 5 giây?

**Câu hỏi 5.** Một client timeout ngay sau khi gửi launch. Tại sao không nên gửi lại request mới ngay mà chưa tra cứu trạng thái của request gốc?

**Bài tập A — Thiết kế contract API.** Định nghĩa `POST /api/task-requests` và `GET /api/task-requests/{requestId}` với `202 Accepted`, các trạng thái điều phối và điều kiện báo `SUCCEEDED`. Chỉ rõ dữ liệu nào đến từ SCDF và dữ liệu nào đến từ kho nghiệp vụ.

**Bài tập B — Polling bền vững.** Mô tả hoặc cài đặt worker kiểm tra execution status theo self link từ phản hồi launch; giới hạn số lần, timeout và backoff. Xử lý `404`, `429` và `503` mà không tạo thêm execution.

**Bài tập C — Launch mơ hồ.** Mô phỏng server chấp nhận launch nhưng response bị mất. Thiết kế `requestId`/idempotency, đối soát và ràng buộc database để bảo đảm một business key không bị ghi trùng.

**Bài tập D — So sánh kênh launch.** Đối chiếu SCDF REST, Spring Cloud Stream `TaskLaunchRequest` và Kubernetes Job theo bốn khía cạnh: receipt, execution ID, completion signal và nguồn dữ liệu đáng tin cậy.

**Bài tập E — Kết hợp Batch.** Cho Batch Job trả trạng thái `FAILED` trong ứng dụng Spring Cloud Task. So sánh `JobExecution`, `TaskExecution`, mã thoát process và điều kiện báo kết quả tới người dùng.

## 18. Ghi nhớ

- **Xác nhận launch là nhận yêu cầu; xác nhận completion là chứng minh tác vụ đã kết thúc và kết quả đáp ứng yêu cầu.** Hai việc này phải được thiết kế độc lập.
- SCDF có thể trả **`executionId`/`schemaTarget`/self link** khi nhận yêu cầu. Hãy lưu và dùng link đó để theo dõi; HTTP `201` không đồng nghĩa `exitCode=0`.
- `TaskExecution` cho biết thời gian và kết quả được framework ghi nhận; **không có record hoặc thiếu `endTime` không chứng minh một task chưa từng chạy**.
- Mỗi lần retry có thể tạo execution ID mới. **`requestId` và business key** cần ổn định để đối soát và chống lặp hiệu ứng.
- Polling phải có **timeout, backoff và xử lý UNKNOWN**, không nhầm GET status với POST launch.
- Trong ứng dụng dùng Spring Batch, cần kiểm tra `JobExecution`/`StepExecution` và chính sách phản ánh thất bại Batch sang mã thoát Task.
- Trạng thái kết luận cho người dùng nên dựa trên **runtime + TaskRepository + kết quả nghiệp vụ**, với nguồn quan sát độc lập từ scheduler/container.

## Tài liệu tham khảo

- [Spring Cloud Task — Features / Lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): thời điểm tạo/cập nhật `TaskExecution` và giới hạn lỗi khởi động.
- [Spring Cloud Task — Spring Cloud Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): `TaskLaunchRequest`, `TaskLauncherSink` và `@EnableTaskLauncher`.
- [Spring Cloud Task — TaskLaunchRequest API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html): trường URI, arguments, deployment/environment properties.
- [Spring Cloud Data Flow — Reference Guide, Launching Tasks and Reviewing Task Executions](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/): shell, REST API `/tasks/executions/launch`, phản hồi execution ID/schema target và execution detail.
- [Spring Cloud Data Flow — Task DSL API](https://docs.spring.io/spring-cloud-dataflow/docs/current/api/org/springframework/cloud/dataflow/rest/client/dsl/task/Task.html): launch bất đồng bộ và theo dõi status.
- [Spring Cloud Data Flow — Task Execution Details](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_execution_detail): thông tin runtime, arguments, exit message và log.

Các API mẫu cần được đối chiếu với phiên bản Spring Cloud Data Flow, Spring Cloud Task, nền tảng deployer và cấu hình bảo mật thực tế; đặc biệt không dùng endpoint legacy của một phiên bản để suy ra hợp đồng REST của phiên bản khác.
