# Lưu tham số khởi chạy trong TaskExecution

Trong **Spring Cloud Task**, mỗi lần khởi chạy một ứng dụng xử lý hữu hạn tạo ra một **TaskExecution** để theo dõi vòng đời và kết quả của lần chạy đó. Ngoài tên tác vụ, thời điểm bắt đầu/kết thúc và mã thoát, **TaskExecution còn giữ danh sách đối số dòng lệnh đã dùng để khởi chạy ứng dụng**. Nhờ vậy, khi điều tra một lần nhập dữ liệu hoặc tạo báo cáo, ta có thể xác định nó được gọi với tệp nào, kỳ dữ liệu nào và chế độ xử lý nào.

Bài học thuộc chương **Dữ liệu thực thi**, tập trung vào cách truyền, lưu, đọc lại và quản trị **tham số khởi chạy** trong hệ thống Spring Cloud Task có **TaskRepository** lưu trên cơ sở dữ liệu. Các ví dụ cũng làm rõ ranh giới với Spring Boot, Spring Batch, lỗi thực thi và các nguyên tắc vận hành an toàn.

## 1. Vì sao cần lưu tham số theo từng lần chạy?

Giả sử ứng dụng được triển khai dưới dạng một tiến trình Java chạy ngắn hạn để nhập đơn hàng từ đối tác. Hai lần chạy có thể dùng cùng artifact và cùng tên tác vụ, nhưng có tham số khác nhau:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=false

java -jar order-import-task.jar \
  --source-id=partner-b-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=true
~~~

Ở đây:

| Tham số | Ý nghĩa nghiệp vụ | Lợi ích khi lưu |
| --- | --- | --- |
| `--source-id` | Định danh tệp hoặc đợt dữ liệu nguồn | Đối chiếu nguồn nào đã được xử lý |
| `--business-date` | Ngày nghiệp vụ của tập dữ liệu | Phát hiện xử lý nhầm kỳ và hỗ trợ chạy lại |
| `--dry-run` | Chỉ kiểm tra thay vì ghi dữ liệu | Phân biệt lần chạy thử với lần chạy thực |

Nếu chỉ biết tên tác vụ `order-import`, người vận hành không thể xác định vì sao số lượng đơn hàng giữa hai lượt khác nhau. Khi lưu **đối số gắn với đúng TaskExecution ID**, lịch sử có thể truy vết được mà không phụ thuộc hoàn toàn vào log còn lưu hay không.

Lưu tham số không đồng nghĩa **lưu kết quả nghiệp vụ**. Chẳng hạn, danh sách đơn hàng đã nhập, đường dẫn báo cáo đầu ra và checksum kết quả thường cần bảng nghiệp vụ hoặc kho lưu trữ riêng.

## 2. TaskExecution lưu tham số gì?

Trong API Spring Cloud Task, `TaskExecution` có thuộc tính `arguments`, kiểu **`List<String>`**, và phương thức `getArguments()`. Đây là danh sách **đối số dòng lệnh nhận được từ ứng dụng Spring Boot**, ví dụ:

~~~text
[
  "--source-id=partner-a-2026-11-23",
  "--business-date=2026-11-23",
  "--dry-run=false"
]
~~~

Thông thường, khi Spring Cloud Task khởi tạo một lần thực thi, framework ghi danh sách này thông qua **TaskRepository**. Không cần tự viết câu lệnh `INSERT` để lưu từng đối số.

Cần phân biệt ba khái niệm thường bị gọi chung là “tham số”:

| Loại | Ví dụ | Có mặc nhiên nằm trong `TaskExecution.arguments`? |
| --- | --- | --- |
| **Application command-line arguments** | `--source-id=abc`, `--dry-run=true`, đối số vị trí | **Có**: đây là danh sách mà Spring Cloud Task ghi lại |
| **Cấu hình từ environment / application.yml** | `DB_URL`, `spring.datasource.url`, cấu hình trong tệp YAML | **Không** chỉ vì chúng tồn tại trong môi trường; chúng phải được truyền thành đối số nếu muốn xuất hiện ở danh sách |
| **Spring Batch JobParameters** | `businessDate` dạng chuỗi/ngày, `run.id` cho Batch Job | **Không tự động tương đương**: là metadata của JobRepository và cần được ánh xạ riêng nếu ứng dụng kết hợp Batch |

Ví dụ, `java -Dmy.property=x -jar task.jar --source-id=abc` truyền `-Dmy.property=x` như một **JVM system property**, trong khi `--source-id=abc` là **đối số ứng dụng**. Đừng kỳ vọng toàn bộ giá trị lấy bằng `@Value` hoặc `Environment` được lưu tự động.

**Điểm cốt lõi:** `TaskExecution.arguments` là bằng chứng về *những đối số đã được truyền*. Nó không bảo đảm các giá trị ấy đã được kiểm tra hợp lệ, cũng không ghi lại mọi cấu hình môi trường tại thời điểm chạy.

## 3. Luồng ghi tham số trong TaskRepository

~~~mermaid
flowchart TD
    A["Scheduler / API / vận hành viên"] --> B["Chạy ứng dụng với command-line arguments"]
    B --> C["Spring Boot nhận args"]
    C --> D["Spring Cloud Task tạo TaskExecution"]
    D --> E[("TASK_EXECUTION: metadata lần chạy")]
    D --> F[("TASK_EXECUTION_PARAMS: từng đối số")]
    C --> G["ApplicationRunner / CommandLineRunner"]
    G --> H["Xử lý nghiệp vụ với tham số đã kiểm tra"]
    H --> I["Hoàn tất hoặc ném lỗi"]
    I --> J["TaskRepository cập nhật kết quả thực thi"]
~~~

Thứ tự logic là:

1. **Bộ khởi chạy** tạo tiến trình Java cùng các đối số, ví dụ `--source-id=abc`.
2. **Spring Boot** khởi tạo ứng dụng và cung cấp đối số cho các thành phần như `ApplicationArguments`, `ApplicationRunner` hoặc `CommandLineRunner`.
3. **Spring Cloud Task** ghi một `TaskExecution` mới với danh sách đối số khi vòng đời Task bắt đầu, trước khi các runner thực thi.
4. **Logic nghiệp vụ** kiểm tra, chuyển kiểu và sử dụng tham số; nếu lỗi, lần thực thi được cập nhật thông tin thất bại theo cơ chế lifecycle.
5. **TaskExplorer** hoặc công cụ quản trị đọc lại metadata và danh sách đối số của lần chạy.

TaskRepository có thể ghi thành công metadata đầu vào ngay cả khi nghiệp vụ sau đó thất bại do tham số không hợp lệ. Ngược lại, nếu **ApplicationContext không khởi tạo đủ để vòng đời Spring Cloud Task bắt đầu**, có thể không có bản ghi TaskExecution tương ứng; lúc đó phải kiểm tra thêm log khởi động và trạng thái container/job từ bộ điều phối.

### 3.1. Các bảng liên quan

Với schema quan hệ mặc định, thông tin được tách thành hai bảng:

| Bảng | Cột quan trọng | Vai trò |
| --- | --- | --- |
| `TASK_EXECUTION` | `TASK_EXECUTION_ID`, `TASK_NAME`, `START_TIME`, `END_TIME`, `EXIT_CODE` | Một bản ghi cho mỗi lần thực thi |
| `TASK_EXECUTION_PARAMS` | `TASK_EXECUTION_ID`, `TASK_PARAM` | Các dòng chứa đối số của lần thực thi, liên kết bằng execution ID |

Trong schema được tài liệu Spring Cloud Task công bố, cột `TASK_PARAM` là `VARCHAR(2500)`. Không dùng bảng này làm nơi lưu payload JSON lớn hoặc dữ liệu nhị phân. Khi chọn phiên bản framework và hệ quản trị cơ sở dữ liệu, hãy kiểm tra DDL đi kèm phiên bản thực tế; cấu hình **table prefix** tùy chỉnh cũng làm thay đổi tên bảng.

Ví dụ dữ liệu minh họa:

**TASK_EXECUTION**

| TASK_EXECUTION_ID | TASK_NAME | EXIT_CODE |
| ---: | --- | ---: |
| 4101 | order-import | 0 |
| 4102 | order-import | 1 |

**TASK_EXECUTION_PARAMS**

| TASK_EXECUTION_ID | TASK_PARAM |
| ---: | --- |
| 4101 | `--source-id=partner-a-2026-11-23` |
| 4101 | `--business-date=2026-11-23` |
| 4101 | `--dry-run=false` |
| 4102 | `--source-id=partner-b-2026-11-23` |
| 4102 | `--business-date=2026-11-23` |
| 4102 | `--dry-run=true` |

Các mã và exit code trong bảng chỉ là **ví dụ giả lập**, không phải dữ liệu được lấy từ một hệ thống đang chạy.

## 4. Ví dụ Spring Boot: nhận và lưu đối số

Giả sử dự án đã có dependency Spring Cloud Task phù hợp với phiên bản Spring Boot đang dùng, đã cấu hình cơ sở dữ liệu cho TaskRepository và tạo schema metadata tương ứng.

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: order-import
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: order-import
~~~

Mật khẩu cung cấp qua cơ chế quản lý secrets hoặc biến môi trường bảo mật. Không truyền password thành đối số dòng lệnh vì đối số có thể tồn tại trong **TaskRepository**, lịch sử lệnh, danh sách tiến trình hoặc log.

Dưới đây là phần nhận tham số bằng `ApplicationRunner`. Interface `OrderImportService` biểu diễn nghiệp vụ cần cài đặt trong ứng dụng thực tế:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class OrderImportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderImportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner importOrders(OrderImportService service) {
        return args -> {
            String sourceId = requiredOne(args, "source-id");
            LocalDate businessDate =
                    LocalDate.parse(requiredOne(args, "business-date"));
            boolean dryRun = parseBoolean(
                    requiredOne(args, "dry-run"));

            service.importOrders(sourceId, businessDate, dryRun);
        };
    }

    private static String requiredOne(
            ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + key + "=value");
        }
        return values.get(0);
    }

    private static boolean parseBoolean(String value) {
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        throw new IllegalArgumentException(
                "--dry-run must be true or false");
    }
}

interface OrderImportService {
    void importOrders(
            String sourceId, LocalDate businessDate, boolean dryRun);
}
~~~

Lệnh chạy:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=false
~~~

Ở ví dụ này, `ApplicationArguments` giúp **trích xuất và kiểm tra** các giá trị theo tên, còn **Spring Cloud Task tự lưu danh sách đối số thô** trong TaskRepository. Gọi `requiredOne` không phải thao tác “ghi tham số”; nó chỉ ngăn trường hợp thiếu, rỗng hoặc truyền trùng một khóa. `LocalDate.parse` và `parseBoolean` bảo đảm kiểu dữ liệu dùng trong nghiệp vụ hợp lệ.

Lưu ý khi đưa vào chạy thực tế: dự án cần cung cấp bean cài đặt `OrderImportService`; ví dụ chỉ giới thiệu phần giao nhận tham số. Các tham số đầu vào phải được kiểm tra thêm về giới hạn chiều dài, định dạng mã nguồn, quyền truy cập tài nguyên và quy tắc nghiệp vụ.

## 5. Đọc lại tham số theo TaskExecution ID

Khi biết mã thực thi, có thể dùng **TaskExplorer** để đọc `TaskExecution` từ repository. Đây là API được thiết kế cho việc truy vấn lịch sử thực thi; không cần parse trực tiếp các bảng trong mã ứng dụng.

~~~java
import java.util.List;

import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.stereotype.Service;

@Service
public class TaskExecutionLookup {

    private final TaskExplorer taskExplorer;

    public TaskExecutionLookup(TaskExplorer taskExplorer) {
        this.taskExplorer = taskExplorer;
    }

    public List<String> findLaunchArguments(long executionId) {
        TaskExecution execution =
                taskExplorer.getTaskExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "TaskExecution not found: " + executionId);
        }
        return List.copyOf(execution.getArguments());
    }
}
~~~

Ví dụ kết quả từ `findLaunchArguments(4101L)`:

~~~text
--source-id=partner-a-2026-11-23
--business-date=2026-11-23
--dry-run=false
~~~

Kết quả là danh sách **String**. Nếu hệ thống quản trị muốn hiển thị biểu mẫu “khóa → giá trị”, nó phải parse theo quy ước của ứng dụng và xử lý các tình huống như đối số vị trí, lặp tên khóa hoặc giá trị chứa dấu `=`. Không tự động mặc định mọi phần tử luôn có định dạng `--key=value`.

Về bảo mật, đoạn `TaskExecutionLookup` là lớp truy cập nội bộ để minh họa API. Nếu sử dụng trong HTTP endpoint, phải kiểm tra quyền trước khi trả về; nên trả về **bản xem đã ẩn các tham số nhạy cảm**, thay vì trực tiếp xuất toàn bộ danh sách.

### 5.1. Truy vấn SQL để điều tra

Khi cần đối soát trực tiếp trong CSDL, có thể dùng:

~~~sql
SELECT e.TASK_EXECUTION_ID,
       e.TASK_NAME,
       e.START_TIME,
       e.END_TIME,
       e.EXIT_CODE,
       p.TASK_PARAM
FROM TASK_EXECUTION e
LEFT JOIN TASK_EXECUTION_PARAMS p
       ON p.TASK_EXECUTION_ID = e.TASK_EXECUTION_ID
WHERE e.TASK_EXECUTION_ID = :execution_id;
~~~

Ký hiệu `:execution_id` là **bind parameter** của lớp truy cập dữ liệu (ví dụ named-parameter JDBC); khi chạy trong SQL client, thay bằng placeholder mà client hỗ trợ.

Mỗi `TaskExecution` có thể xuất hiện ở **nhiều dòng** do có nhiều đối số. `LEFT JOIN` giúp vẫn thấy bản ghi thực thi ngay cả khi không có đối số. Không nên dựa vào thứ tự hàng trả về của truy vấn SQL để xác định thứ tự các tham số, bởi bảng tham số không mặc định có cột thứ tự rõ ràng.

Khi cần tìm các lượt chạy theo một `source-id`, có thể truy vấn bảng tham số để điều tra. Tuy nhiên, nếu nhu cầu là **tra cứu thường xuyên, bảo đảm duy nhất hoặc kiểm soát chạy trùng theo source-id**, nên thiết kế bảng nghiệp vụ có khóa có cấu trúc; tìm kiếm bằng `LIKE` trên chuỗi `TASK_PARAM` không phải cơ chế idempotency đáng tin cậy.

## 6. Tham số, danh tính nghiệp vụ và chạy lại

Cùng một lệnh được chạy hai lần sẽ tạo **hai lần TaskExecution khác nhau** nếu mỗi lần đều khởi chạy một tiến trình Task mới:

~~~text
Lần A: executionId = 4101
        source-id = partner-a-2026-11-23
        status = COMPLETED

Lần B: executionId = 4103
        source-id = partner-a-2026-11-23
        status = COMPLETED
~~~

Spring Cloud Task **ghi nhận các lần chạy**, không tự suy ra rằng cùng `--source-id` thì phải bỏ qua lần thứ hai. Quy tắc xử lý trùng là trách nhiệm của nghiệp vụ.

Đối với tác vụ nhập đơn hàng, có thể quản lý trạng thái theo `source-id` trong bảng riêng:

~~~sql
CREATE TABLE import_run (
    source_id        varchar(200) PRIMARY KEY,
    source_checksum  varchar(128) NOT NULL,
    status           varchar(30) NOT NULL,
    completed_at     timestamp NULL
);
~~~

Trước khi nhập, kiểm tra/chiếm quyền xử lý trên khóa `source_id` bằng transaction và ràng buộc duy nhất phù hợp. Sau đó xử lý theo cơ chế idempotent, ghi checkpoint nếu cần, đối soát tổng số và đánh dấu hoàn tất. Nếu lần chạy mới có cùng `source-id` nhưng checksum khác, phải xử lý theo chính sách phiên bản/xung đột thay vì âm thầm bỏ qua.

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **TaskExecution ID** | `4101` | Phân biệt từng lần chạy kỹ thuật |
| **Tên task** | `order-import` | Phân loại loại công việc |
| **Launch argument** | `--source-id=partner-a-2026-11-23` | Ghi lại yêu cầu đã truyền cho lần chạy |
| **Business key** | `partner-a-2026-11-23` | Đối soát dữ liệu, chống xử lý trùng, quyết định chạy lại |
| **Trạng thái nghiệp vụ** | `IMPORTED`, `REJECTED` | Cho biết kết quả xử lý nguồn hoặc đầu ra |

Việc cùng một dòng `--source-id=...` xuất hiện ở nhiều TaskExecution là **điều bình thường** khi retry. Theo dõi lịch sử cần gắn được mỗi lần thử với trạng thái nghiệp vụ tại thời điểm tương ứng.

## 7. Tương tác với Spring Batch

Khi Spring Cloud Task khởi chạy một **Spring Batch Job**, có hai lớp metadata riêng:

- **TaskExecution / TaskRepository:** lưu đối số khởi chạy **ứng dụng** và vòng đời của tiến trình.
- **JobExecution, JobInstance và JobParameters / JobRepository:** lưu thông tin **Batch Job** và các tham số dùng để nhận diện/chạy lại Job theo quy tắc của Spring Batch.

Ví dụ bộ điều phối gọi ứng dụng:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23
~~~

Ứng dụng có thể kiểm tra hai tham số rồi tạo `JobParameters` tương ứng cho Batch Job. Việc ánh xạ đó cần được thực hiện một cách tường minh hoặc theo cơ chế launcher được cấu hình; **không được coi `TASK_EXECUTION_PARAMS` và metadata JobParameters là một bảng dùng chung**.

Điều này quan trọng khi khởi động lại: một `TaskExecution` mới chỉ nói rằng có **một tiến trình mới** được chạy; còn Spring Batch dùng cấu hình Job và các **identifying JobParameters** để quyết định lần gọi thuộc `JobInstance` nào, có thể restart hay tạo instance mới.

Để đối soát khi hệ thống hỗ trợ liên kết Task–Batch, có thể dùng API `TaskExplorer.getJobExecutionIdsByTaskExecutionId(executionId)` thay vì đoán JobExecution ID từ TaskExecution ID.

## 8. Bảo mật và độ tin cậy của dữ liệu tham số

### 8.1. Không truyền bí mật qua đối số

Ví dụ **không an toàn**:

~~~bash
# KHÔNG làm như sau: mật khẩu trở thành đối số ứng dụng.
java -jar task.jar --api-token=actual-secret-token
~~~

Những giá trị này có thể xuất hiện trong **TASK_EXECUTION_PARAMS**, công cụ quản lý tiến trình, lịch sử shell và log. Việc thêm dấu `***` vào màn hình sau khi chạy **không xóa** giá trị đã lưu trong repository.

Thay bằng cách cấp bí mật qua secret store hoặc cơ chế cấu hình bảo mật khi triển khai. Đối số chỉ chứa định danh tham chiếu **không bí mật**, ví dụ:

~~~bash
java -jar task.jar \
  --source-id=partner-a-2026-11-23 \
  --credential-ref=partner-a-import
~~~

Ứng dụng tra cứu credential từ hệ thống phù hợp, không ghi token vào log, kết quả TaskExecution, exception message hoặc các bảng nghiệp vụ. Ngay cả tên tệp, đường dẫn và ID có thể làm lộ dữ liệu; hãy chọn cách định danh tối thiểu.

### 8.2. Chính sách giới hạn và kiểm tra

| Rủi ro | Biện pháp |
| --- | --- |
| Tham số chứa token/mật khẩu/PII | Không truyền bí mật; giới hạn những khóa được phép; kiểm soát quyền đọc TaskRepository |
| Chuỗi quá dài so với `TASK_PARAM` | Validate chiều dài đầu vào; lưu payload trong object storage và chỉ truyền tham chiếu |
| Thiếu hoặc lặp khóa | Kiểm tra đủ và đúng một giá trị cho các tùy chọn bắt buộc |
| Giá trị ngày sai hoặc ngoài phạm vi | Parse định dạng xác định, kiểm tra timezone, giới hạn khoảng thời gian |
| Hai tác vụ cùng business key | Unique constraint/lock nghiệp vụ và cơ chế xử lý trùng |
| Log vô tình in toàn bộ `args` | Chỉ log tham số cho phép, che dữ liệu nhạy cảm và quản lý thời hạn lưu log |
| TaskRepository bị dọn quá sớm | Đặt chính sách retention nhất quán với yêu cầu kiểm toán và các bảng liên quan |

### 8.3. Nguyên tắc thiết kế tham số tốt

Ưu tiên tham số **ổn định, giải thích được và có thể tái hiện**:

~~~text
--source-id=partner-a-2026-11-23
--business-date=2026-11-23
--operation=import
--dry-run=false
~~~

Hạn chế tham số có ý nghĩa thay đổi theo thời gian mà không được chốt, ví dụ `--date=today`. Khi cần chạy lại sau vài ngày, `today` có thể trỏ tới tập dữ liệu khác. Tốt hơn là bộ điều phối tính ngày nghiệp vụ cụ thể và truyền giá trị ấy cho ứng dụng.

Tương tự, dùng `--input-uri` dẫn tới nội dung có thể thay đổi sẽ không bảo đảm tái hiện. Nếu cần kiểm toán chính xác, kèm thêm `source-version`, checksum hoặc định danh đối tượng bất biến.

## 9. Vận hành: kiểm chứng thông tin sau khi chạy

Một quy trình kiểm tra có thể thực hiện như sau:

1. Chuẩn bị TaskRepository trong CSDL bền vững với schema tương thích phiên bản Spring Cloud Task đang dùng.
2. Khởi chạy tác vụ với một tập tham số **không chứa bí mật**, ghi lại execution ID qua log/lớp quan sát hoặc truy vấn lịch sử.
3. Dùng `TaskExplorer.getTaskExecution(id)` để lấy `TaskExecution` rồi đọc `getArguments()`, hoặc truy vấn `TASK_EXECUTION_PARAMS`.
4. Đối chiếu `TASK_EXECUTION_ID`, `TASK_NAME`, `EXIT_CODE`, thời điểm bắt đầu/kết thúc, các đối số và trạng thái nghiệp vụ.
5. Chạy lại với cùng business key rồi xác nhận **execution ID mới** và hành vi idempotent trong dữ liệu đích.
6. Thử một giá trị `--business-date` không hợp lệ và kiểm tra lỗi được phản ánh trong hệ thống điều phối, log và metadata nếu Task đã bắt đầu.

**Quan sát cần thận trọng:** nếu `END_TIME` trống, một lần chạy có thể **đang chạy hoặc kết thúc bất thường trước khi ghi trạng thái cuối**. Không tự kết luận tiến trình còn sống; cần đối chiếu với Job/Pod, timeout và hệ thống giám sát.

Nếu không thấy tham số, lần lượt kiểm tra:

| Triệu chứng | Khả năng và hướng kiểm tra |
| --- | --- |
| Có TaskExecution nhưng không có hàng trong `TASK_EXECUTION_PARAMS` | Xác minh tham số thật sự được truyền vào ứng dụng, phân biệt môi trường/JVM property với app arguments |
| Không có TaskExecution | Kiểm tra khởi động ApplicationContext, datasource, schema, quyền DB, cấu hình Spring Cloud Task |
| Tìm theo ID ra `null` | Kiểm tra đúng môi trường, repository, table prefix và execution ID |
| Tham số khác mong đợi | Kiểm tra cách launcher escape dấu cách, giá trị có dấu `=`, tham số lặp và shell/kịch bản gọi |
| Query trả nhiều hàng cho một execution ID | Đúng thiết kế: một hàng biểu diễn một đối số; xử lý tập kết quả theo execution ID |
| Task báo thành công nhưng dữ liệu đích sai | Đối soát logic nghiệp vụ; metadata tham số không thay thế kiểm tra đầu ra |

## 10. Bài tập thực hành

Xây dựng ứng dụng `invoice-report-task` nhận ba đối số:

~~~text
--tenant-id=acme
--report-date=2026-11-23
--format=csv
~~~

Yêu cầu:

1. Dùng `ApplicationArguments` xác thực đúng một `tenant-id`, `report-date` kiểu `LocalDate`, `format` thuộc `csv` hoặc `json`.
2. Chạy tác vụ hai lần với hai ngày khác nhau, dùng `TaskExplorer` đọc lại hai danh sách `arguments`; xác nhận mỗi lượt có một execution ID riêng.
3. Thử thiếu `--report-date` và ghi nhận lỗi; đối chiếu metadata TaskExecution và trạng thái tiến trình.
4. Chạy lại một ngày báo cáo đã có kết quả. Đặt khóa nghiệp vụ **(`tenant-id`, `report-date`, `format`)** ở bảng báo cáo để tránh phát hành trùng ngoài ý muốn.
5. Thử một tham số chứa chuỗi rất dài và một tham số có tên khóa lặp. Giải thích cách validate giúp tránh lỗi repository và nhập nhằng dữ liệu.
6. Kiểm tra rằng không có secret hoặc dữ liệu cá nhân nhạy cảm được ghi vào `TASK_EXECUTION_PARAMS`.

**Tiêu chí hoàn thành:** người học chỉ ra chính xác sự khác nhau giữa **đối số lúc gọi**, **danh sách `TaskExecution.arguments` đã lưu**, **tham số của Spring Batch Job** (nếu có) và **kết quả nghiệp vụ**.

## 11. Tổng kết

- **TaskExecution** lưu danh sách đối số ứng dụng dưới dạng `List<String>`; TaskRepository lưu chúng trong bảng **`TASK_EXECUTION_PARAMS`** gắn với mã thực thi.
- **ApplicationArguments** giúp ứng dụng đọc, xác thực và chuyển kiểu giá trị; không cần tự INSERT các đối số vào bảng Spring Cloud Task.
- **TaskExplorer** dùng để truy vấn lịch sử theo execution ID; SQL giúp điều tra nhưng phải hiểu mỗi lần chạy có thể có nhiều hàng tham số.
- **Chạy lại cùng tham số** vẫn là lần thực thi kỹ thuật mới. Khóa nghiệp vụ, ràng buộc duy nhất và idempotency quyết định có được xử lý dữ liệu lần nữa hay không.
- **Không truyền secret trong command-line arguments** vì thông tin có thể tồn tại lâu dài trong TaskRepository và các hệ thống giám sát liên quan.
- Khi kết hợp Spring Batch, cần phân biệt metadata TaskExecution với metadata JobExecution/JobParameters.

### Tài liệu tham khảo

- [Spring Cloud Task Reference Guide — TaskExecution, TaskRepository và schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/htmlsingle/)
- [Javadoc: TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
- [Javadoc: TaskExplorer](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
