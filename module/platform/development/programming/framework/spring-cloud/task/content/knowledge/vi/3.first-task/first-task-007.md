# Đọc nhật ký và kiểm tra bản ghi thực thi đầu tiên

## 1. Mục tiêu của bước kiểm tra

Khi đã chạy được ứng dụng **Spring Cloud Task** đầu tiên, cần xác nhận hai điều độc lập: **mã nghiệp vụ thực sự được thực thi** và **Spring Cloud Task đã ghi nhận vòng đời của lần chạy trong cơ sở dữ liệu**. Nhìn thấy dòng “Started …” trên console chưa đủ để khẳng định task đã hoàn tất; nhìn thấy một bản ghi trong database cũng chưa đủ để khẳng định kết quả nghiệp vụ chính xác.

Trong chương **Task đầu tiên**, bài này tập trung vào cách đọc log, nhận diện từng lần chạy, tra cứu **TaskRepository**, kiểm tra tham số, mã thoát và thông tin lỗi. Đây là nền tảng để sau này chạy task theo lịch hoặc theo yêu cầu, phối hợp với Spring Batch và vận hành an toàn.

Sau bài học, bạn có thể:

- Phân biệt log khởi động ứng dụng, log xử lý nghiệp vụ và log vòng đời task.
- Tìm một lần chạy cụ thể bằng **task execution ID** và đối chiếu nó với bản ghi trong bảng **TASK_EXECUTION**.
- Đọc **START_TIME**, **END_TIME**, **EXIT_CODE**, **EXIT_MESSAGE**, **ERROR_MESSAGE** và tham số đầu vào.
- Nhận biết các dấu hiệu thất bại, tiến trình bị ngắt hoặc cấu hình TaskRepository không đúng.
- Thực hiện một chu trình kiểm chứng có thể lặp lại trước khi đưa task vào lịch chạy thật.

## 2. Mô hình quan sát một lần thực thi

Spring Cloud Task làm việc với ứng dụng Spring Boot có vòng đời hữu hạn: khởi động, thực hiện công việc, kết thúc. Khi được kích hoạt và cấu hình repository phù hợp, framework lưu **TaskExecution** vào cơ sở dữ liệu qua **TaskRepository**.

~~~mermaid
sequenceDiagram
    participant O as Người chạy / Scheduler
    participant A as Ứng dụng Spring Boot
    participant R as TaskRepository
    participant DB as Cơ sở dữ liệu
    O->>A: Khởi chạy với tham số
    A->>R: Bắt đầu TaskExecution
    R->>DB: Lưu ID, tên task, thời gian bắt đầu
    A->>A: Chạy nghiệp vụ, ghi log
    alt Kết thúc có kiểm soát
        A->>R: Ghi thông tin kết thúc / mã thoát
        R->>DB: Cập nhật bản ghi thực thi
    else Tiến trình bị kết thúc đột ngột
        Note over A,DB: Có thể không kịp lưu END_TIME hoặc kết quả cuối
    end
    O->>DB: Tra cứu lần chạy, đối chiếu log
~~~

Ba nhóm dữ liệu cần phân biệt:

| Nguồn | Trả lời câu hỏi nào? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| **Log ứng dụng** | Lệnh đã khởi động chưa, bước nào đang chạy, lỗi phát sinh ở đâu? | Log thành công không bảo đảm kết quả đã được ghi bền vững. |
| **TaskRepository** | Lần chạy có ID nào, bắt đầu/kết thúc lúc nào, mã thoát và thông tin lỗi ra sao? | Không chứa đầy đủ chi tiết các bước xử lý nghiệp vụ. |
| **Dữ liệu nghiệp vụ** | Đơn hàng, file, báo cáo hoặc dữ liệu đích có được cập nhật đúng không? | Không tự cho biết vì sao một tiến trình bị dừng. |

**TaskRepository không phải hệ thống lưu log**. Nó lưu metadata về vòng đời thực thi; log vẫn đến từ hệ thống ghi nhật ký Spring Boot, hệ thống tập trung log hoặc hạ tầng chạy container.

## 3. Chuẩn bị ví dụ task để quan sát

Giả sử bạn có một ứng dụng Spring Boot sử dụng phiên bản **Spring Cloud Task** tương thích, có dependency cần thiết và DataSource trỏ tới database chứa schema metadata. Ví dụ đặt tên task là **first-task** và cho nhận tham số ngày xử lý.

### 3.1. Cấu hình cục bộ

Để thử nghiệm và kiểm tra dữ liệu **sau khi JVM đã thoát**, có thể dùng H2 dạng lưu xuống tệp:

~~~yaml
# application.yml: ví dụ dành cho môi trường học tập
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./data/first-task-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: first-task

logging:
  level:
    root: INFO
~~~

Ứng dụng phải có driver H2 trong classpath và các bảng schema của Spring Cloud Task phù hợp với phiên bản đang dùng. Việc tạo schema tự động hay thông qua migration phụ thuộc cấu hình và môi trường; hãy kiểm tra trước khi chạy. Trong hệ thống thực tế, nên dùng database được quản trị và quy trình migration rõ ràng.

**Lưu ý:** H2 `jdbc:h2:mem:...` chỉ phù hợp để thử trong cùng tiến trình; khi JVM kết thúc, dữ liệu trong bộ nhớ có thể biến mất. Với H2 dạng tệp, đường dẫn tương đối `./data/first-task-db` được tính từ **thư mục làm việc khi khởi chạy**. Nếu dùng hai thư mục làm việc khác nhau, bạn có thể vô tình tạo hai database khác nhau.

### 3.2. Một runner minh họa

Nếu ứng dụng của bạn đã có runner, chỉ cần áp dụng kỹ thuật ghi log và đối chiếu ở các phần tiếp theo. Đoạn mã sau cho thấy một ứng dụng task đơn giản, kiểm tra tham số và cho phép giả lập lỗi:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class FirstTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(FirstTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(FirstTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner firstRunner() {
        return arguments -> {
            List<String> values = arguments.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Tham số bắt buộc: --businessDate=yyyy-MM-dd");
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            log.info("BUSINESS_START businessDate={}", businessDate);

            if (arguments.containsOption("fail")) {
                throw new IllegalStateException("Lỗi giả lập để kiểm tra");
            }

            // Thay bằng xử lý nghiệp vụ thật.
            log.info("BUSINESS_DONE businessDate={} processedCount={}",
                    businessDate, 12);
        };
    }
}
~~~

Ở ví dụ trên, **12 là dữ liệu minh họa**, chưa phải kết quả đã được ghi trong database nghiệp vụ. Trong ứng dụng thực tế, log kết quả phải lấy từ giá trị xử lý thật và không nên ghi mật khẩu, token hoặc dữ liệu cá nhân nhạy cảm.

Để liên kết log với bản ghi TaskRepository chính xác hơn, có thể thêm một listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class TaskAuditLogListener implements TaskExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditLogListener.class);

    @Override
    public void onTaskStartup(TaskExecution taskExecution) {
        log.info("TASK_START executionId={} taskName={}",
                taskExecution.getExecutionId(),
                taskExecution.getTaskName());
    }

    @Override
    public void onTaskEnd(TaskExecution taskExecution) {
        log.info("TASK_END executionId={}",
                taskExecution.getExecutionId());
    }

    @Override
    public void onTaskFailed(TaskExecution taskExecution, Throwable throwable) {
        log.error("TASK_FAILED executionId={} errorType={}",
                taskExecution.getExecutionId(),
                throwable.getClass().getSimpleName(), throwable);
    }
}
~~~

Listener ghi **executionId** vào log để có thể truy vấn chính xác một lần chạy, ngay cả khi nhiều lần chạy có cùng tên task. Nếu phiên bản Spring Cloud Task có khác biệt về API listener, hãy dùng API của chính phiên bản đang chạy; nguyên tắc đối chiếu vẫn là **một execution ID cho một lần thực thi**.

## 4. Chạy lần đầu và đọc nhật ký

Giả sử bạn đã đóng gói thành `first-task.jar`, khởi chạy với một tham số nghiệp vụ:

~~~bash
java -jar first-task.jar --businessDate=2026-11-23
~~~

Một đoạn log có thể trông như sau (**minh họa**; tên logger, thứ tự dòng và ID thực tế tùy môi trường):

~~~text
2026-11-24 08:00:01 INFO  ... : Starting FirstTaskApplication
2026-11-24 08:00:03 INFO  ... : TASK_START executionId=1 taskName=first-task
2026-11-24 08:00:03 INFO  ... : BUSINESS_START businessDate=2026-11-23
2026-11-24 08:00:03 INFO  ... : BUSINESS_DONE businessDate=2026-11-23 processedCount=12
2026-11-24 08:00:03 INFO  ... : TASK_END executionId=1
~~~

Đọc log theo luồng:

1. **Starting …** cho biết ứng dụng đang khởi tạo; đây chưa phải bằng chứng đã chạy xong nghiệp vụ.
2. **TASK_START** chỉ ra task được framework ghi nhận, kèm `executionId=1` trong ví dụ.
3. **BUSINESS_START** cho thấy runner đã bắt đầu xử lý với giá trị tham số đã phân tích.
4. **BUSINESS_DONE** xác nhận nhánh xử lý của runner đã hoàn tất theo logic ví dụ.
5. **TASK_END** cho biết callback kết thúc của listener được gọi. Cần tra cứu database sau khi tiến trình dừng để xác nhận metadata được lưu.

Các dòng có tiền tố `TASK_START`, `BUSINESS_START`, `BUSINESS_DONE`, `TASK_END` là do **mã ví dụ tự ghi**, không phải văn bản log cố định mà Spring Cloud Task luôn phát ra.

Khi kiểm tra lần chạy, ưu tiên `executionId` thay vì chỉ tìm theo `taskName` và timestamp. Nếu có hai tiến trình `first-task` cùng chạy, các log có thể xen kẽ; mỗi execution ID vẫn xác định một lần chạy độc lập.

### 4.1. Đối chiếu thời gian

So sánh thời điểm khởi động, bắt đầu nghiệp vụ, hoàn tất nghiệp vụ và kết thúc task. Dấu thời gian log có thể dùng múi giờ của hệ thống chạy hoặc cấu hình logging, trong khi kiểu thời gian của cột database và cách công cụ SQL hiển thị có thể khác. Hãy **chuẩn hóa múi giờ trước khi so sánh**; không vội kết luận có độ trễ bất thường chỉ từ hai chuỗi giờ hiển thị khác nhau.

### 4.2. Kiểm tra mã thoát tiến trình

Với tác vụ chạy trong terminal, script hoặc orchestrator, mã thoát của **tiến trình** có ý nghĩa đối với hệ thống khởi chạy. Theo quy ước thông dụng, `0` thể hiện hoàn tất bình thường và khác `0` thể hiện thất bại. Tuy nhiên, mã thoát hệ điều hành, mã thoát ghi trong TaskRepository và trạng thái nghiệp vụ cần được kiểm tra theo cách ứng dụng xử lý ngoại lệ và cấu hình exit code; không giả định ba giá trị luôn đồng nhất.

Ví dụ, nếu runner bắt lỗi rồi chỉ ghi log mà không ném lại hoặc không đánh dấu kết quả thất bại, framework có thể xem ứng dụng đã hoàn tất bình thường. Vì vậy thông điệp “ERROR” trong log **không tự bảo đảm** `EXIT_CODE` sẽ khác 0.

## 5. Tra cứu bản ghi trong TaskRepository

Trong schema SQL thông dụng của Spring Cloud Task, hai bảng thường dùng để xác minh lần chạy đầu tiên là:

- **TASK_EXECUTION**: metadata về từng lần thực thi của task.
- **TASK_EXECUTION_PARAMS**: các tham số dòng lệnh được ghi nhận cho lần thực thi đó.

Tên bảng, cột và cú pháp truy vấn có thể cần điều chỉnh theo schema/chế độ đặt tên hoặc phiên bản framework của dự án. Dưới đây là ví dụ SQL sử dụng các tên cột thông dụng.

### 5.1. Tìm lần chạy vừa hoàn tất

Mở công cụ SQL kết nối **đúng database mà ứng dụng dùng**, rồi chạy:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'first-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Kết quả minh họa:

| TASK_EXECUTION_ID | TASK_NAME | START_TIME | END_TIME | EXIT_CODE | EXIT_MESSAGE | ERROR_MESSAGE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | first-task | 2026-11-24 08:00:03 | 2026-11-24 08:00:03 | 0 | (trống) | (trống) |

Trong tình huống minh họa:

- `TASK_EXECUTION_ID = 1` trùng với `executionId=1` trong log listener.
- `TASK_NAME = first-task` trùng với tên đã cấu hình.
- `START_TIME` và `END_TIME` đều có giá trị; lần chạy đã được ghi nhận là kết thúc.
- `EXIT_CODE = 0` phù hợp với kết thúc bình thường trong ví dụ.
- `EXIT_MESSAGE` và `ERROR_MESSAGE` trống không phải là lỗi; chúng có thể không được đặt cho lần chạy thành công.

**Không suy ra thành công chỉ từ việc có END_TIME.** Một lần chạy lỗi được ghi nhận bình thường cũng có thể có thời gian kết thúc. Hãy kết hợp `EXIT_CODE`, thông tin lỗi, log và kết quả nghiệp vụ.

### 5.2. Kiểm tra theo đúng execution ID

Nếu log đã cung cấp `executionId=1`, truy vấn trực tiếp một bản ghi:

~~~sql
SELECT *
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 1;
~~~

ID trong ví dụ chỉ là số minh họa. Với mỗi lần chạy mới, thay bằng ID thực tế trong log hoặc ID đã tra từ bảng. Đây là cách ít nhầm lẫn hơn khi hệ thống có nhiều lần chạy cùng tên.

### 5.3. Kiểm tra tham số của lần chạy

~~~sql
SELECT TASK_EXECUTION_ID, TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = 1;
~~~

Đối chiếu kết quả với tham số đã truyền:

~~~text
--businessDate=2026-11-23
~~~

Cách biểu diễn giá trị trong `TASK_PARAM` phụ thuộc cơ chế lưu tham số của phiên bản đang sử dụng. Đừng mặc định bảng này chứa một cặp cột `KEY`/`VALUE` hay tự suy ra rằng tham số đã được kiểm tra hợp lệ; việc phân tích và kiểm tra tham số vẫn là trách nhiệm của ứng dụng.

**Lưu ý bảo mật:** tham số dòng lệnh có thể xuất hiện trong lịch sử thực thi và log của hệ thống. Không truyền mật khẩu, access token hay dữ liệu nhạy cảm dưới dạng tham số mà môi trường có thể ghi lại.

### 5.4. Đối chiếu nhiều lần chạy

Mỗi lần khởi động một ứng dụng Spring Cloud Task thường tạo **một bản ghi TaskExecution mới**. Nếu chạy lại cùng `businessDate`, bạn có thể thấy các bản ghi có execution ID khác nhau nhưng tham số giống nhau. Spring Cloud Task ghi nhận lịch sử từng lần khởi động; nó **không tự bảo đảm thao tác nghiệp vụ chỉ được thực hiện một lần**.

Ví dụ:

| Execution ID | Tham số nghiệp vụ | Exit code | Ý nghĩa |
| --- | --- | --- | --- |
| 1 | `businessDate=2026-11-23` | 0 | Lần chạy đầu hoàn tất bình thường. |
| 2 | `businessDate=2026-11-23` | 0 | Chạy lại cùng ngày; cần kiểm tra chống xử lý trùng. |
| 3 | `businessDate=2026-11-24` | Khác 0 | Có thể là lần chạy thất bại; xem lỗi cụ thể. |

Để tránh tác động lặp lại, xử lý nghiệp vụ nên có **khóa nghiệp vụ** (ví dụ: ngày đối soát và đối tượng xử lý), ràng buộc dữ liệu và logic **idempotent** phù hợp.

## 6. Thử tình huống lỗi và phân tích bản ghi

Để quan sát một lần chạy không thành công, dùng nhánh giả lập lỗi trong runner:

~~~bash
java -jar first-task.jar --businessDate=2026-11-24 --fail
~~~

Ví dụ log:

~~~text
2026-11-24 08:10:00 INFO  ... : TASK_START executionId=2 taskName=first-task
2026-11-24 08:10:00 INFO  ... : BUSINESS_START businessDate=2026-11-24
2026-11-24 08:10:00 ERROR ... : TASK_FAILED executionId=2 errorType=IllegalStateException
java.lang.IllegalStateException: Lỗi giả lập để kiểm tra
    at ...FirstTaskApplication...
~~~

Truy vấn bản ghi sau khi JVM kết thúc:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 2;
~~~

Với lỗi được framework ghi nhận đầy đủ, bạn thường sẽ thấy metadata thể hiện lần thực thi thất bại, chẳng hạn mã thoát không bằng 0 và/hoặc thông tin lỗi. **Không nên phụ thuộc vào một giá trị hoặc một thông điệp lỗi chính xác giữa mọi phiên bản**. Nếu tiến trình bị dừng đột ngột trước khi framework cập nhật repository, bản ghi có thể còn thiếu dữ liệu kết thúc.

Khi xác định nguyên nhân lỗi, hãy đọc **cả ba lớp thông tin**:

1. **Stack trace trong log** để tìm exception gốc và bước phát sinh.
2. **TaskExecution** để xác định một lần chạy nào bị ảnh hưởng và trạng thái cuối đã lưu.
3. **Hệ thống đích** để xem có dữ liệu đã được cập nhật một phần trước khi lỗi hay không.

Ví dụ: tác vụ xuất file có thể tạo xong file nhưng lỗi khi gửi thông báo. Nếu chỉ nhìn `EXIT_CODE` rồi chạy lại toàn bộ, có thể tạo file trùng. Xử lý lại phải dựa trên trạng thái nghiệp vụ.

## 7. Bảng diễn giải trạng thái thường gặp

| Dấu hiệu quan sát | Cách hiểu ban đầu | Hướng kiểm tra tiếp |
| --- | --- | --- |
| Có log xử lý, có bản ghi, `END_TIME` và `EXIT_CODE = 0` | Framework ghi nhận một lần chạy hoàn tất bình thường | Kiểm tra kết quả nghiệp vụ thật. |
| Có bản ghi, `END_TIME` và `EXIT_CODE` khác 0 | Lần chạy kết thúc nhưng được ghi nhận lỗi | Xem `ERROR_MESSAGE`, stack trace, tham số, dữ liệu đã xử lý. |
| Có bản ghi nhưng `END_TIME` trống | Chưa ghi nhận kết thúc; có thể còn chạy hoặc bị dừng bất thường | Kiểm tra PID/pod/job thực tế, timeout và log hệ thống. |
| Có log khởi động nhưng không thấy bản ghi | TaskRepository chưa ghi nhận lần chạy ở database đang kiểm tra | Kiểm tra enable task, datasource, schema, quyền và log lỗi kết nối. |
| Có bản ghi nhưng không thấy log mong đợi | Có thể sai nguồn log, mức log hoặc runner chưa đến bước ghi log | Xác định execution ID, vị trí log, cấu hình logger và stack trace. |
| Có nhiều bản ghi cùng tên/đầu vào | Task được khởi chạy nhiều lần | Kiểm tra scheduler, retry, yêu cầu thủ công và xử lý trùng. |
| `EXIT_CODE = 0` nhưng kết quả nghiệp vụ sai | Ứng dụng có thể đã báo thành công quá sớm hoặc bỏ qua lỗi nghiệp vụ | Kiểm tra điều kiện thành công, kiểm thử và cách phát tín hiệu lỗi. |

**Quan trọng:** `END_TIME IS NULL` không đồng nghĩa chắc chắn task *đang chạy*. Khi tiến trình bị kill, mất điện, hết tài nguyên hoặc database không thể cập nhật, metadata có thể giữ trạng thái dang dở. Cần đối chiếu trạng thái thật của tiến trình/container.

## 8. Quy trình xử lý sự cố khi không tìm thấy bản ghi

Nếu vừa chạy task nhưng không thấy dữ liệu trong **TASK_EXECUTION**, hãy kiểm tra theo thứ tự:

1. **Xác nhận tiến trình được khởi chạy:** tìm log khởi động ứng dụng, log runner và exception đầu tiên.
2. **Kiểm tra cấu hình Spring Cloud Task:** ứng dụng có dependency, có kích hoạt chức năng task (ví dụ `@EnableTask` theo cấu hình đang dùng) và thực sự sử dụng TaskRepository hay không.
3. **Kiểm tra DataSource:** URL, tên database, schema, username và profile đang bật có đúng với nơi bạn mở SQL client không.
4. **Kiểm tra schema:** có bảng **TASK_EXECUTION** và **TASK_EXECUTION_PARAMS** phù hợp với phiên bản framework không; tài khoản có quyền đọc/ghi không.
5. **Kiểm tra khả năng ghi lúc khởi động:** nếu database chưa sẵn sàng, task có thể thất bại trước khi tạo được một bản ghi đầy đủ.
6. **Đối chiếu thư mục làm việc đối với H2 dạng tệp:** `./data` khi chạy jar có thể khác vị trí database mà SQL client đang mở.
7. **Xem log chi tiết có chọn lọc:** trong môi trường thử nghiệm có thể tạm tăng mức log cho namespace liên quan, sau đó đưa về mức phù hợp.

Ví dụ bật log chi tiết trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.cloud.task: DEBUG
~~~

Không bật mức DEBUG rộng rãi vô thời hạn trên production: log lớn có thể ảnh hưởng chi phí lưu trữ và làm lộ thông tin không cần thiết nếu cấu hình ghi dữ liệu đầu vào thiếu kiểm soát.

Nếu dùng PostgreSQL/MySQL hoặc hệ quản trị khác, kiểm tra quyền database và cách khởi tạo schema bằng migration tương ứng. Nếu muốn truy vấn ngay khi ứng dụng còn chạy, dùng hệ quản trị cho phép client truy cập đồng thời và bảo đảm bạn đang kết nối đúng database; với H2 file, quy tắc khóa tệp phụ thuộc cấu hình và phương thức kết nối.

## 9. Checklist tự kiểm tra lần chạy đầu tiên

Sau khi chạy thành công, tự đánh dấu từng mục:

- [ ] Log thể hiện ứng dụng đã khởi động và runner đã thực hiện công việc.
- [ ] Có execution ID xác định được từ listener hoặc truy vấn TaskRepository.
- [ ] Tên task và tham số đầu vào khớp kỳ vọng.
- [ ] Database chứa bản ghi trong **TASK_EXECUTION** cho lần chạy này.
- [ ] Có thể truy vấn chi tiết theo chính xác `TASK_EXECUTION_ID`.
- [ ] **START_TIME** có giá trị; với lần chạy hoàn tất bình thường, **END_TIME** cũng có giá trị.
- [ ] Đã kiểm tra **EXIT_CODE**, **EXIT_MESSAGE**, **ERROR_MESSAGE** phù hợp với kết quả thực tế.
- [ ] Đã đối chiếu log và kết quả nghiệp vụ, không chỉ tin vào mã thoát.
- [ ] Có thể tìm được bản ghi lần chạy lỗi và giải thích nguyên nhân.
- [ ] Nếu chạy lại cùng tham số, đã xem xét nguy cơ tạo kết quả trùng lặp.

## 10. Ghi nhớ

Quy trình kiểm chứng đáng tin cậy cho **task đầu tiên** là: **chạy ứng dụng → ghi nhận execution ID → đọc log theo ID → truy vấn TaskRepository → đối chiếu kết quả nghiệp vụ**. Log cho biết diễn biến, TaskRepository cho biết metadata của một lần thực thi và dữ liệu nghiệp vụ cho biết tác động thực tế.

Khi hiểu ba nguồn thông tin này, bạn sẽ dễ phát hiện lần chạy lỗi, lần chạy quá hạn và lần chạy trùng khi tích hợp Spring Cloud Task với scheduler, hệ thống điều phối hoặc Spring Batch. Đồng thời, bạn có cơ sở để thiết kế retry, cảnh báo và kiểm toán an toàn thay vì chỉ dựa vào dòng log “Started” hoặc “Completed”.

