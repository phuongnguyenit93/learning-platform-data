# Cấu trúc TaskLaunchRequest trong nhánh API hỗ trợ

## 1. TaskLaunchRequest dùng ở đâu?

**Spring Cloud Task** giúp xây dựng ứng dụng Spring Boot có **vòng đời hữu hạn**: được khởi chạy, thực hiện công việc, lưu thông tin thực thi vào **TaskRepository** rồi kết thúc. Có nhiều cách kích hoạt một task: gọi `java -jar` từ terminal, cho Kubernetes tạo Job/CronJob, dùng một hệ thống điều phối hoặc nhận yêu cầu từ hệ thống khác.

Trong chương **Khởi chạy**, `TaskLaunchRequest` là **đối tượng mô tả yêu cầu khởi chạy** của nhánh tích hợp **Spring Cloud Task với Spring Cloud Stream**. Ở nhánh này, một thành phần gửi thông điệp chứa `TaskLaunchRequest`; **TaskLauncherSink** nhận đối tượng đó và sử dụng một triển khai `TaskLauncher` của **Spring Cloud Deployer** để khởi tạo tiến trình task.

Điều cần phân biệt ngay:

- **Không phải mọi ứng dụng Spring Cloud Task đều phải tạo `TaskLaunchRequest`.** Nếu chạy trực tiếp `java -jar` hoặc để scheduler chạy một Job/Pod, bạn có thể không sử dụng API này.
- **`TaskLaunchRequest` chỉ là dữ liệu mô tả một lần yêu cầu**, không phải đối tượng `TaskExecution` đã được TaskRepository ghi.
- **Nhận được thông điệp và gọi launcher thành công không đồng nghĩa nghiệp vụ đã hoàn tất.** Task được khởi chạy sẽ tiếp tục chạy trong tiến trình/container khác.
- API này nằm trong **nhánh tích hợp được framework và phiên bản Spring Cloud Stream hỗ trợ**. Không mặc định các ví dụ dùng `@EnableTaskLauncher` từ tài liệu cũ hoạt động nguyên vẹn với mọi phiên bản Spring Cloud Stream hiện đại.

Sau bài học, bạn có thể nhận diện năm trường của `TaskLaunchRequest`, tạo đối tượng Java đúng chữ ký constructor, phân loại command-line arguments/environment/deployment properties, thiết kế đường message-to-launch an toàn và theo dõi kết quả thực thi sau khi yêu cầu được nhận.

## 2. Toàn cảnh đường khởi chạy qua thông điệp

~~~mermaid
flowchart LR
    A["HTTP / event / scheduler"] --> B["Processor xác thực yêu cầu"]
    B --> C["TaskLaunchRequest"]
    C --> D[("Spring Cloud Stream / message broker")]
    D --> E["TaskLauncherSink"]
    E --> F["TaskLauncher của Spring Cloud Deployer"]
    F --> G["Tiến trình / container task hữu hạn"]
    G --> H[("TaskRepository")]
    G --> I[("Dữ liệu nghiệp vụ")]
    J["Công cụ giám sát"] --> H
~~~

Các vai trò là:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Nguồn yêu cầu** | Phát lệnh “chạy tác vụ X với đầu vào Y”, có thể qua HTTP, broker hoặc sự kiện |
| **Producer/processor** | Kiểm tra quyền, dữ liệu đầu vào; tạo `TaskLaunchRequest` đã chuẩn hóa |
| **Spring Cloud Stream** | Vận chuyển thông điệp đến consumer/sink theo binder được cấu hình |
| **`TaskLauncherSink`** | Nhận payload kiểu `TaskLaunchRequest` và chuyển yêu cầu cho launcher |
| **`TaskLauncher`** | Giao yêu cầu tạo tiến trình cho hạ tầng cụ thể, ví dụ local hoặc Kubernetes |
| **Ứng dụng Spring Cloud Task được chạy** | Xử lý nghiệp vụ và ghi metadata lần chạy qua TaskRepository |
| **TaskRepository/TaskExplorer** | Lưu và tra cứu vòng đời các lần thực thi task, không phải queue tin nhắn |

Sink thông thường là **ứng dụng nhận thông điệp chạy liên tục**, còn ứng dụng task do nó khởi chạy là **ứng dụng hữu hạn**. Vì thế không được bật cơ chế tự đóng context của task trên một sink vốn phải liên tục nhận thông điệp mà không kiểm tra kiến trúc trước.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant M as Broker / Stream
    participant S as TaskLauncherSink
    participant L as TaskLauncher
    participant T as Task process
    participant R as TaskRepository
    P->>M: Message<TaskLaunchRequest>
    M->>S: Chuyển payload đúng kiểu
    S->>L: Yêu cầu khởi chạy artifact
    L-->>S: Yêu cầu được chấp nhận / ID hạ tầng
    Note over S,T: Chấp nhận launch không đồng nghĩa task hoàn tất
    L->>T: Tạo process / container
    T->>R: Bắt đầu TaskExecution
    T->>T: Xử lý nghiệp vụ
    T->>R: Ghi kết quả kết thúc (nếu kịp)
    Note over R: Giám sát đọc theo TaskExecution hoặc tương quan ngoài
~~~

## 3. Cấu trúc chính xác của TaskLaunchRequest

Theo Javadoc Spring Cloud Task 3.0.4, lớp nằm trong package:

`org.springframework.cloud.task.launcher.TaskLaunchRequest`

Đây là lớp Java triển khai `Serializable`. Constructor có đủ năm đối số:

~~~java
TaskLaunchRequest(
    String uri,
    List<String> commandlineArguments,
    Map<String, String> environmentProperties,
    Map<String, String> deploymentProperties,
    String applicationName
)
~~~

Javadoc cũng liệt kê **constructor không đối số** (có từ 2.0.0) phục vụ các tình huống xây dựng/serialization tương thích. Tuy nhiên, API này **không có các setter cho đủ năm trường**; vì thế khi tạo yêu cầu trong mã ứng dụng, hãy dùng constructor năm đối số thay vì giả định có `setUri(...)` hoặc `setCommandlineArguments(...)`.

### 3.1. Năm trường cần nhớ

| Trường | Kiểu Java | Công dụng | Ví dụ minh họa |
| --- | --- | --- | --- |
| `uri` | `String` | Đường dẫn/URI đến **artifact của task cần chạy** | `maven://com.example.batch:daily-close:1.4.2` |
| `commandlineArguments` | `List<String>` | Các đối số truyền cho **tiến trình task** được khởi chạy | `["--businessDate=2026-11-23", "--tenantId=tenant-a"]` |
| `environmentProperties` | `Map<String,String>` | Các biến môi trường của **task process** | `{"SPRING_PROFILES_ACTIVE":"task"}` |
| `deploymentProperties` | `Map<String,String>` | Các thuộc tính **dành cho TaskLauncher/deployer** để triển khai lên nền tảng | Cấu hình CPU, memory, placement... theo contract của deployer |
| `applicationName` | `String` | Tên ứng dụng/định danh được gắn cho task được khởi chạy | `daily-close` |

Tên getter trong Javadoc:

~~~java
request.getUri();
request.getCommandlineArguments();
request.getEnvironmentProperties();
request.getDeploymentProperties();
request.getApplicationName();
request.setApplicationName("daily-close");
~~~

**Cẩn thận chính tả:** Javadoc Java dùng `getCommandlineArguments()` (chữ `l` của `line` viết thường). Phần mô tả trong tài liệu hướng dẫn có thể viết `commandLineArguments` theo camelCase. Khi viết mã Java, dùng **đúng tên phương thức của phiên bản dependency**, không suy ra phương thức getter từ tên trường được trình bày trong tài liệu.

Javadoc cho biết `getCommandlineArguments()` trả về **danh sách không thể sửa qua getter**. Không nên trông đợi có thể gọi `request.getCommandlineArguments().add(...)` để thay đổi yêu cầu sau khi tạo. Tạo sẵn danh sách mong muốn và đưa vào constructor.

### 3.2. uri khác đường dẫn tham số đầu vào

`uri` xác định **mã ứng dụng sẽ được triển khai**, không phải URI đến tệp CSV cần xử lý.

Ví dụ:

~~~text
uri                     = maven://com.example.batch:daily-close:1.4.2
commandlineArguments[0] = --inputFile=/data/invoices-2026-11-23.csv
~~~

`maven://...` là ví dụ dạng URI artifact thường xuất hiện trong nhánh Spring Cloud Deployer. Cơ chế tra cứu Maven repository, cache và khả năng hiểu URI phụ thuộc **ResourceLoader/TaskLauncher thực tế**. Với một deployer khác, có thể dùng loại `Resource`/URI được nó hỗ trợ; không thể đổi sang bất kỳ URL HTTP nào rồi mặc nhiên kỳ vọng chạy được.

Nên cố định artifact bằng **phiên bản phát hành đã kiểm soát**, không cho message từ người dùng chỉ định một artifact tùy ý.

### 3.3. commandlineArguments chỉ là đối số, không phải JobParameters sẵn có

Các phần tử của danh sách được truyền như đối số của ứng dụng task:

~~~text
--businessDate=2026-11-23
--tenantId=tenant-a
--dryRun=false
~~~

Ứng dụng Spring Boot có thể đọc chúng qua `ApplicationArguments` hoặc cấu hình `Environment`. Nếu task chạy Spring Batch và muốn truyền **JobParameters**, bạn phải xác nhận quy tắc launcher Boot/Batch của ứng dụng: một số đường khởi chạy Batch phân biệt `name=value` với tham số Spring Boot có tiền tố `--`.

`TaskLaunchRequest` **không tự kiểm tra** ngày có hợp lệ, tenant có quyền truy cập hoặc task có hỗ trợ tên tham số đó hay không. Việc xác thực đầu vào phải được làm tại producer và **kiểm tra lại ở task**.

### 3.4. environmentProperties khác deploymentProperties

Đây là hai map dễ nhầm nhất.

**`environmentProperties`** truyền **biến môi trường** cho tiến trình task, chẳng hạn:

~~~text
SPRING_PROFILES_ACTIVE=task
TZ=UTC
~~~

Ứng dụng có thể thấy biến môi trường này khi chạy nếu TaskLauncher hỗ trợ truyền qua đúng cách.

**`deploymentProperties`** được gửi tới **deployer** để quyết định **cách tạo process/container**: giới hạn tài nguyên, lựa chọn môi trường hoặc tham số triển khai mà nền tảng hỗ trợ. Tên key phụ thuộc triển khai `TaskLauncher` và phiên bản; không có một danh sách key CPU/memory dùng được cho mọi deployer.

Ví dụ, một khóa `memory` tùy ý trong `deploymentProperties` **không có nghĩa** mọi `TaskLauncher` sẽ giới hạn RAM theo giá trị đó. Muốn cấu hình Kubernetes, local deployer hay hệ điều phối khác, phải đối chiếu tài liệu của deployer tương ứng.

**Không truyền secret dưới dạng chuỗi văn bản trong các map hoặc command line** nếu chúng có thể nằm trong broker, lịch sử task, log, Kubernetes Pod spec hoặc audit. Nên tham chiếu secret đã được quản lý trên hạ tầng, rồi để platform gắn vào runtime đúng quyền.

### 3.5. applicationName khác business key và taskExecutionId

`applicationName` là **tên logic được launcher gắn cho ứng dụng được khởi chạy**. Nó có thể dùng để đặt tên tài nguyên hạ tầng, log và truy vết. Nó không mặc nhiên là:

- **`TASK_EXECUTION_ID`** — ID của một **lần chạy** do TaskRepository cấp.
- **Business key** — ví dụ `tenant-a:2026-11-23` dùng để chống xử lý trùng.
- **`spring.application.name` / `spring.cloud.task.name`** — các thuộc tính có thể ảnh hưởng tên mà ứng dụng task tự ghi trong TaskRepository theo cấu hình.

Trong một hệ thống thực, cần xác minh tên ở deployer và `TASK_EXECUTION.TASK_NAME` có đồng nhất hay không, thay vì giả định tuyệt đối.

Tài liệu hướng dẫn mô tả tên tự sinh khi không đặt `applicationName` bằng một chuỗi dạng `Task-<UUID>`; một số bản Javadoc nói dạng `Task-<hash/unique id>`. **Không phụ thuộc vào thuật toán tạo tên mặc định.** Hãy đặt `applicationName` rõ ràng, ổn định và phù hợp giới hạn tên của nền tảng triển khai.

## 4. Tạo TaskLaunchRequest bằng Java

Ví dụ sau tạo yêu cầu chạy tác vụ đối soát một ngày cho một tenant. Nó minh họa **cấu trúc object**, chưa gửi thông điệp đến broker hay khởi chạy process.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;

public final class LaunchRequestFactory {

    private LaunchRequestFactory() { }

    public static TaskLaunchRequest dailyClose(
            String tenantId, String businessDate) {

        // Chỉ cho tenant ID chứa chữ thường, số và dấu gạch ngang.
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }

        LocalDate parsedDate = LocalDate.parse(businessDate);
        String date = parsedDate.toString();

        List<String> args = List.of(
                "--tenantId=" + tenantId,
                "--businessDate=" + date,
                "--workKey=" + tenantId + ":" + date
        );

        Map<String, String> environment = Map.of(
                "SPRING_PROFILES_ACTIVE", "task"
        );

        // Để trống trong ví dụ; triển khai thực tế chỉ dùng
        // các khóa do TaskLauncher/deployer tương ứng hỗ trợ.
        Map<String, String> deployment = Map.of();

        return new TaskLaunchRequest(
                "maven://com.example.batch:daily-close:1.4.2",
                args,
                environment,
                deployment,
                "daily-close"
        );
    }
}
~~~

Giải thích:

1. `uri` được lấy từ danh sách artifact **đã phê duyệt**, không lấy trực tiếp từ HTTP request không tin cậy.
2. `businessDate` được parse thành `LocalDate`, tránh nhận định dạng ngày sai.
3. `workKey` ổn định cho **cùng một công việc nghiệp vụ**, dù yêu cầu được gửi lại sau timeout; task phía nhận phải thực sự dùng nó để kiểm soát idempotency.
4. `environmentProperties` chỉ chứa dữ liệu vận hành không nhạy cảm trong ví dụ.
5. `deploymentProperties` rỗng có chủ đích; không bịa khóa dành cho Kubernetes hay Cloud Foundry khi chưa chọn deployer.
6. `applicationName` được đặt rõ ràng. Nếu nền tảng yêu cầu tên ứng dụng duy nhất theo mỗi lần launch, cần có quy ước riêng cho **deployment instance** và **business key**.

### Đọc lại để kiểm tra cấu trúc

~~~java
TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

System.out.println(request.getUri());
System.out.println(request.getApplicationName());
System.out.println(request.getCommandlineArguments());
System.out.println(request.getEnvironmentProperties());
System.out.println(request.getDeploymentProperties());
~~~

Kết quả dự kiến về mặt dữ liệu:

~~~text
maven://com.example.batch:daily-close:1.4.2
daily-close
[--tenantId=tenant-a, --businessDate=2026-11-23, --workKey=tenant-a:2026-11-23]
{SPRING_PROFILES_ACTIVE=task}
{}
~~~

Thứ tự hiển thị của `Map` không nên được dùng như một phần của giao thức, dù ví dụ có một cặp key-value.

## 5. Dữ liệu gửi qua message broker

Theo Spring Cloud Task Reference, một processor có thể tạo một `GenericMessage<TaskLaunchRequest>` rồi gửi đến sink. Payload **phải được chuyển thành `TaskLaunchRequest` hợp lệ** trước khi handler tiếp nhận. Nếu payload mang kiểu khác mà không được chuyển đổi đúng, sink có thể ném exception.

Ví dụ tại producer:

~~~java
import org.springframework.cloud.task.launcher.TaskLaunchRequest;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

Message<TaskLaunchRequest> message =
        MessageBuilder.withPayload(request)
                .setHeader(
                    "correlationId",
                    "tenant-a:2026-11-23")
                .build();
~~~

**Đây là ví dụ tạo message trong Java, chưa phải lệnh tự gửi tới broker.** Producer còn phải có cơ chế publish lên binding/channel tương ứng, và phía consumer cần được cấu hình đúng binder, converter, schema hoặc trusted type.

### 5.1. JSON minh họa cấu trúc logic

Một thông điệp có thể biểu diễn **ý tưởng** của yêu cầu như sau:

~~~json
{
  "uri": "maven://com.example.batch:daily-close:1.4.2",
  "applicationName": "daily-close",
  "commandlineArguments": [
    "--tenantId=tenant-a",
    "--businessDate=2026-11-23",
    "--workKey=tenant-a:2026-11-23"
  ],
  "environmentProperties": {
    "SPRING_PROFILES_ACTIVE": "task"
  },
  "deploymentProperties": {}
}
~~~

**Không coi JSON này là wire contract được framework tự động chấp nhận ở mọi phiên bản.** Tên property khi serialize có thể phụ thuộc Jackson và quy tắc đặt tên JavaBean, ví dụ `commandlineArguments` đối chiếu với tài liệu có cách viết `commandLineArguments`; conversion còn phụ thuộc binder và content type. Cần thử **round-trip serialize/deserialize** của đúng ứng dụng producer/sink, không tin vào một ví dụ JSON viết tay.

Trong hệ thống có yêu cầu bảo mật cao, thay vì cho consumer deserialise một Java class từ message bất kỳ, có thể định nghĩa DTO/giao thức JSON đơn giản, versioned và validated, rồi **chuyển sang `TaskLaunchRequest` trong một lớp adapter tin cậy**. Không bật deserialization tùy ý cho mọi Java class từ broker không tin cậy.

### 5.2. Ví dụ function processor theo kiểu Spring Cloud Stream

Một processor theo mô hình function có thể biến một yêu cầu nghiệp vụ đã được chuyển đổi thành record Java thành `TaskLaunchRequest`:

~~~java
import java.util.function.Function;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LaunchProcessorConfiguration {

    public record DailyCloseCommand(
            String tenantId,
            String businessDate) { }

    @Bean
    public Function<DailyCloseCommand, TaskLaunchRequest>
    toTaskLaunchRequest() {

        return command -> LaunchRequestFactory.dailyClose(
                command.tenantId(),
                command.businessDate());
    }
}
~~~

Với binder/function configuration phù hợp, đầu vào là payload `DailyCloseCommand` đã được kiểm tra/giải mã, đầu ra là `TaskLaunchRequest`. Trong ứng dụng thực tế, cần cấu hình **destination input/output, content type và chuyển đổi message** theo phiên bản Spring Cloud Stream; đoạn mã trên chỉ minh họa **nơi tạo đối tượng request**.

Tính đúng đắn không đến từ việc producer gửi được message: sink phải nhận đúng kiểu payload, triển khai task phải nhận đúng đối số và kết quả phải được xác minh qua metadata cùng dữ liệu nghiệp vụ.

## 6. Nhánh TaskLauncherSink và @EnableTaskLauncher

Trong nhánh API mô tả bởi Spring Cloud Task Reference và Javadoc tương ứng, ứng dụng sink được khai báo:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.launcher.annotation.EnableTaskLauncher;

@SpringBootApplication
@EnableTaskLauncher
public class TaskSinkApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskSinkApplication.class, args);
    }
}
~~~

`@EnableTaskLauncher` import cấu hình `TaskLauncherSink`, giúp sink tiếp nhận một `TaskLaunchRequest` và dùng `TaskLauncher` để khởi chạy task. **Nó không tự cung cấp mọi thành phần hạ tầng**:

- Phải có một **`TaskLauncher` thực sự** của Spring Cloud Deployer hoặc do ứng dụng cấu hình.
- Phải cấu hình **Spring Cloud Stream binder**, destination và cơ chế giải mã để nhận payload đúng kiểu.
- Phải chọn **BOM Spring Boot, Spring Cloud Task, Spring Cloud Stream và Spring Cloud Deployer tương thích**. Các đời Spring Cloud Stream khác nhau về programming model (ví dụ annotation-based so với function-based); không ghép ví dụ cũ vào bản mới mà không kiểm tra.
- Sink muốn nhận message liên tục thường cần **giữ context hoạt động**; còn process task được tạo phải **kết thúc đúng vòng đời**.

Trong một số phiên bản sink theo mô hình legacy, Javadoc `TaskLauncherSink` cho thấy handler:

~~~java
// Chữ ký minh họa từ nhánh Spring Cloud Task có TaskLauncherSink
void taskLauncherSink(TaskLaunchRequest taskLaunchRequest)
        throws Exception;
~~~

Trong kiểu triển khai có input channel tên `input`, binding có thể cấu hình destination bằng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: task-launch-requests
~~~

**Lưu ý phiên bản:** cách binding `input` trong ví dụ chỉ tương ứng với **nhánh annotation/channel-based sink** được framework hỗ trợ. Với Spring Cloud Stream functional binding hiện đại, tên binding và cách nối consumer có thể khác. Hãy xác minh phiên bản chạy thật thay vì giả định `@EnableTaskLauncher` và cấu hình `input` vẫn là lựa chọn khuyến nghị cho mọi dự án mới.

### Không nhầm TaskLauncherSink với TaskLauncher

- **`TaskLauncherSink`**: adapter **nhận thông điệp** trong tích hợp Spring Cloud Stream.
- **`TaskLauncher`**: SPI của **Spring Cloud Deployer** chịu trách nhiệm **triển khai task artifact lên hạ tầng**.
- **`TaskLaunchRequest`**: DTO/command mô tả yêu cầu mà sink tiếp nhận.
- **`AppDeploymentRequest`**: kiểu request ở tầng deployer, được sử dụng khi tương tác trực tiếp với `TaskLauncher` theo contract của Spring Cloud Deployer.
- **`TaskExecution`**: metadata về **một lần chạy** của ứng dụng được tạo, lưu qua TaskRepository.

Không nên viết code gọi `taskLaunchRequest.launch()` vì lớp request **không phải executable task**. Nó không sở hữu JobRepository, không chạy `ApplicationRunner` và không có API để báo thành công nghiệp vụ.

## 7. Vòng đời kết quả: “launch accepted” không phải “task succeeded”

Giả sử một API nội bộ nhận yêu cầu tạo báo cáo:

~~~text
POST /reports/daily
tenantId=tenant-a
businessDate=2026-11-23
~~~

Processor xác thực và phát message chứa `TaskLaunchRequest`. Những trạng thái nên tách biệt:

| Thời điểm | Tín hiệu có thể quan sát | Cần hiểu đúng |
| --- | --- | --- |
| API nhận request | HTTP 202 hoặc bản ghi yêu cầu | Đã nhận yêu cầu, **chưa** phải job xong |
| Broker nhận message | Publisher nhận acknowledgment | Message được chấp nhận, **chưa** chắc sink đã xử lý |
| Sink gọi `TaskLauncher` | Launch request trả về hoặc có mã hạ tầng | Có thể mới tạo/sắp tạo process |
| Process task bắt đầu | `TASK_EXECUTION` có start time | Task khởi động, **chưa** hoàn tất |
| Process task kết thúc | `TASK_EXECUTION` có end time/exit code | Framework đã ghi kết quả vòng đời, cần đối chiếu nghiệp vụ |
| Báo cáo xuất hiện trong hệ thống đích | Kết quả nghiệp vụ có thể kiểm tra | Xác nhận điều kiện thành công cụ thể |

`TaskLaunchRequest` **không phải kết quả trả về** của TaskRepository. Một sink gọi launcher và trả về bình thường có thể không biết worker sẽ thất bại ở bước nào.

### Theo dõi TaskRepository

Ví dụ tra cứu các lần chạy theo tên mà ứng dụng ghi nhận (không mặc định bằng `applicationName` của deployer):

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-close'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Nếu app có tên thực tế khác, dùng `TASK_NAME` đã quan sát từ log hay cơ chế đặt tên của chính task. Với nhiều lần chạy cùng tên, phải tìm **đúng execution ID** hoặc kết hợp dữ liệu tương quan khác, không lấy hàng cuối bất kỳ rồi gán cho một HTTP request.

Có thể bổ sung một **request ID/work key** vào commandline arguments không nhạy cảm và log của task, rồi lưu bảng ánh xạ `requestId → platformExecutionId → taskExecutionId` khi có điều kiện lấy được các ID đó. Việc lưu/khớp ID phải được thiết kế có kiểm soát, không dựa vào giả định rằng ID launcher và ID TaskRepository luôn bằng nhau.

## 8. An toàn thông điệp, retry và idempotency

### 8.1. Những trường dễ trở thành bề mặt tấn công

Nếu cho người gọi kiểm soát toàn bộ `TaskLaunchRequest`, họ có thể:

- Đưa một `uri` đến artifact độc hại hoặc phiên bản chưa được phê duyệt.
- Truyền CLI arguments đổi datasource, kích hoạt profile không phù hợp hoặc chạy với phạm vi dữ liệu vượt quyền.
- Chèn biến môi trường ảnh hưởng việc khởi động Spring Boot.
- Cấp deployment properties làm thay đổi tài nguyên, namespace hoặc hạn mức theo cấu hình nền tảng.
- Gửi nhiều yêu cầu giống nhau, gây chi phí lớn hoặc tác động nghiệp vụ trùng lặp.

**Nguyên tắc an toàn:** API public hoặc nội bộ không nên nhận rồi chuyển tiếp một `TaskLaunchRequest` nguyên vẹn từ client. Thay vào đó, nhận **lệnh nghiệp vụ giới hạn**, kiểm tra tenant/ngày/quyền, chọn artifact và deployment properties bằng **allowlist phía server**, rồi tạo request tại một lớp tin cậy.

~~~mermaid
flowchart LR
    A["Untrusted client"] --> B["DTO nghiệp vụ giới hạn"]
    B --> C{"Kiểm tra authz + input"}
    C -->|Hợp lệ| D["Allowlist artifact / profile / deployer options"]
    D --> E["Tạo TaskLaunchRequest"]
    E --> F["Message broker"]
    F --> G["TaskLauncherSink"]
    C -->|Không hợp lệ| H["Từ chối + audit"]
~~~

Không ghi toàn bộ `TaskLaunchRequest.toString()` vào log nếu chưa biết nó có thể chứa những thông tin gì. Đặc biệt không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào `commandlineArguments` hay `environmentProperties` nếu broker và hạ tầng có thể lưu/hiển thị chúng.

### 8.2. Giao message ít nhất một lần và yêu cầu chạy lặp

Trong đa số hệ thống message broker có cơ chế retry, một message có thể **được giao lại** sau lỗi kết nối hoặc khi consumer xử lý xong launch nhưng chưa ack message. Vì vậy một yêu cầu có thể dẫn đến **hai lần khởi chạy**, kể cả khi không có bug trong code Java.

Ví dụ:

1. Sink nhận request `workKey=tenant-a:2026-11-23`.
2. `TaskLauncher` chấp nhận tạo process.
3. Sink mất kết nối trước khi broker ghi nhận acknowledgment.
4. Broker redeliver cùng message.
5. Sink nhận lần hai và có thể khởi chạy process thứ hai.

`TaskLaunchRequest` không có trường `idempotencyKey` chuẩn riêng trong constructor năm đối số. Muốn idempotency, phải tạo **business key/correlation ID** ở tầng ứng dụng, lưu kết quả nhận yêu cầu có ràng buộc duy nhất hoặc điều phối hợp lý, đồng thời để **task tự xử lý lặp an toàn**.

Các biện pháp thường kết hợp:

- Lưu yêu cầu với unique key theo tenant + kỳ xử lý + loại task + source version.
- Kiểm tra trạng thái trước khi quyết định khởi chạy lại, nhưng **không dùng chỉ một câu SELECT rồi INSERT không có khóa** vì dễ race condition.
- Giới hạn concurrent executions ở scheduler/deployer hoặc dùng locking phù hợp khi cần.
- Cho dữ liệu nghiệp vụ có unique constraint, UPSERT có điều kiện hoặc idempotent consumer.
- Retry có backoff, hạn mức, dead-letter queue và quy trình điều tra.
- Phân biệt “launch lỗi chắc chắn chưa tạo process” với “launch timeout nhưng process có thể đã được tạo”; trường hợp thứ hai cần reconciliation trước khi retry.

**Đừng dùng `applicationName` làm cơ chế exactly-once.** Hai lần chạy tuần tự có thể dùng cùng tên và vẫn tạo tác động trùng; ngược lại, hạ tầng có thể yêu cầu tên resource riêng cho từng lần chạy mà công việc nghiệp vụ vẫn là một work key.

### 8.3. Triển khai theo nguyên tắc quyền tối thiểu

Consumer/sink cần quyền tạo process trên hạ tầng, nhưng không vì vậy mà được phép tạo **mọi** ứng dụng hoặc đọc mọi secret. Cần giới hạn URI artifact, namespace, service account, resource quota và cấu hình runtime; xác thực nguồn message, mã hóa kênh, retention hợp lý và kiểm soát người có quyền publish vào destination.

## 9. Những tình huống sử dụng cụ thể

### Tình huống A — API yêu cầu tạo báo cáo

Một API báo cáo nhận `tenantId` và `businessDate`, xác thực quyền, tạo request dùng `uri` đã cố định, `applicationName=report-generator`, arguments chứa work key, environment chứa profile và deployment properties do nền tảng cấu hình.

**Thiết kế:** trả về `202 Accepted` cùng request ID; frontend hiển thị “đang xử lý” cho đến khi giám sát xác nhận TaskExecution và kết quả file. Không trả `200 SUCCESS` như thể báo cáo đã tạo ngay sau khi publish message.

### Tình huống B — Chạy task theo sự kiện

Khi một tệp dữ liệu mới được xác nhận đã upload hoàn chỉnh, producer phát lệnh nhập tệp. URI artifact được kiểm soát; đường dẫn/manifest đầu vào truyền qua argument không nhạy cảm; worker kiểm tra checksum và version.

**Thiết kế:** nếu cùng sự kiện được giao lại, hệ thống dùng work key và ràng buộc nghiệp vụ để không nhập trùng. Một message được ack không chứng minh database đích đã cập nhật.

### Tình huống C — Chạy task trên Kubernetes

TaskLauncher triển khai Kubernetes Job/Pod. `deploymentProperties` được xây từ cấu hình hệ thống phù hợp với API deployer để giới hạn tài nguyên và namespace; `environmentProperties` bổ sung profile. Task process tự ghi TaskExecution vào database.

**Thiết kế:** theo dõi cả Kubernetes Job/pod và TaskRepository. Resource do deployer tạo và `TASK_EXECUTION_ID` là các định danh khác nhau; timeout không được xử lý chỉ bằng cách gửi lại message ngay lập tức.

### Tình huống D — Chạy Spring Batch trong một task

Task được launch qua sink, sau đó Spring Boot khởi chạy Spring Batch Job. **TaskRepository** lưu lần chạy process; **JobRepository** lưu JobExecution/StepExecution, checkpoint và trạng thái Batch.

**Thiết kế:** truyền JobParameters phù hợp với phiên bản Spring Boot/Batch và theo dõi hai repository. Nếu Job chạy bất đồng bộ và task runner trả về sớm, TaskExecution có thể trông như hoàn tất trước khi dữ liệu Batch thực sự xong.

## 10. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Sink báo payload sai kiểu | Message không được chuyển thành `TaskLaunchRequest` hoặc binder/converter sai | Kiểm tra content type, schema, serialization và trusted types |
| `getUri()` đúng chuỗi nhưng không launch được | Artifact không tồn tại, URI scheme không được hỗ trợ, Maven repo không truy cập được | Kiểm tra resource resolution và log của TaskLauncher |
| Sink không tạo process | Không có bean `TaskLauncher` hợp lệ, thiếu quyền/namespace hoặc lỗi deployment | Kiểm tra bean/config và log platform |
| Process chạy nhưng thiếu `--businessDate` | Producer tạo sai `commandlineArguments`, hoặc launcher chuyển tham số không đúng | Kiểm tra request ở điểm tin cậy, command thực của process |
| Biến môi trường không xuất hiện trong task | Sai tên key, triển khai không truyền env theo kỳ vọng, profile ghi đè | Kiểm tra cấu hình deployer và env của process một cách an toàn |
| `deploymentProperties` bị bỏ qua/lỗi | Dùng key của deployer khác hoặc phiên bản khác | Xác minh danh sách thuộc tính chính thức của TaskLauncher đang dùng |
| Tên pod khác `TASK_NAME` | `applicationName` của launcher và `spring.cloud.task.name` không đồng nhất | Đối chiếu cấu hình task và log ID |
| Launch đã được chấp nhận nhưng không có TaskExecution | Process chưa bootstrap xong, DataSource/schema lỗi, worker chưa được tạo | Kiểm tra hạ tầng, startup log, kết nối metadata |
| Có hai task cùng work key | Broker redelivery, retry, lặp yêu cầu API | Kiểm tra request ID, idempotency/khóa và số process |
| TaskExecution chưa có `END_TIME` | Task còn chạy, bị kill hoặc không kịp ghi kết thúc | Đối chiếu PID/pod, log và nghiệp vụ; không kết luận chỉ từ metadata |
| API báo thành công sớm | Nhầm publish/launch accepted với task completed | Dùng trạng thái nhiều pha và kiểm tra kết quả cuối |

### Quy trình điều tra một yêu cầu khởi chạy

1. Xác nhận client **được phép** yêu cầu tác vụ này và đầu vào có business key rõ ràng.
2. Tìm **request ID/correlation ID** ở API hoặc producer.
3. Kiểm tra message đã tới đúng destination, đúng type/schema, được consumer xác nhận hay chuyển dead-letter queue.
4. Kiểm tra sink **thực sự gọi TaskLauncher** với artifact và deployment options đã phê duyệt.
5. Tìm ID hạ tầng và trạng thái process/container; không đồng nhất nó với execution ID của TaskRepository.
6. Đối chiếu thời điểm task bootstrap, log nghiệp vụ và bản ghi `TASK_EXECUTION` theo tên/ID thực tế.
7. Xác nhận `END_TIME`, exit code, thông điệp lỗi và **kết quả nghiệp vụ**.
8. Nếu có timeout/không chắc launch đã xảy ra, **reconcile trước khi retry** để tránh tạo hai process không mong muốn.

## 11. Thực hành kiểm chứng cấu trúc request

Có thể bắt đầu bằng bài lab **không cần deploy thật** để kiểm tra tính đúng đắn của đối tượng:

**Thử nghiệm 1 — Yêu cầu hợp lệ**

~~~java
TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

assert request.getUri().contains("daily-close");
assert request.getApplicationName().equals("daily-close");
assert request.getCommandlineArguments().size() == 3;
assert request.getEnvironmentProperties()
              .get("SPRING_PROFILES_ACTIVE").equals("task");
assert request.getDeploymentProperties().isEmpty();
~~~

Các lệnh `assert` của Java chỉ chạy khi JVM bật assertions (`-ea`). Trong project thật, nên dùng JUnit `assertEquals`/`assertThrows` để kiểm thử ổn định, không phụ thuộc cờ VM.

**Thử nghiệm 2 — Giá trị sai**

~~~java
try {
    LaunchRequestFactory.dailyClose(
            "TENANT WITH SPACES", "2026-11-23");
    throw new AssertionError("Expected invalid tenantId");
}
catch (IllegalArgumentException expected) {
    // Đầu vào đã bị từ chối.
}
~~~

Hãy kiểm tra thêm ngày không hợp lệ, thiếu tham số, tenant không thuộc quyền người dùng. Không cho consumer nhận URI artifact hay deployment properties tùy ý từ dữ liệu chưa tin cậy.

**Thử nghiệm 3 — Tích hợp với nhánh Stream thực tế**

1. Chọn một bộ phiên bản Spring Boot, Cloud Task, Cloud Stream và Deployer **tương thích**, xác nhận `@EnableTaskLauncher`/sink có mặt.
2. Cấu hình một `TaskLauncher` hợp lệ cho môi trường thử nghiệm và binder có thể chuyển payload kiểu `TaskLaunchRequest`.
3. Gửi một message `Message<TaskLaunchRequest>`; kiểm tra sink gọi đúng launcher bằng quan sát hoặc mock ở integration test.
4. Gửi payload sai kiểu hoặc artifact không được phép; kiểm tra lỗi, dead-letter/retry mà không tạo process ngoài ý muốn.
5. Khởi chạy một ứng dụng task nhỏ: có `ApplicationRunner` kết thúc hữu hạn và TaskRepository cấu hình bền vững.
6. Tra cứu TaskExecution, mã thoát và dữ liệu nghiệp vụ; xác nhận không lấy phản hồi từ `TaskLauncher` làm kết quả cuối.
7. Gửi lại cùng work key và xác minh logic idempotency/reconciliation.

### Checklist trước khi đưa vào vận hành

- [ ] Biết đây là **nhánh Spring Cloud Stream / TaskLauncherSink**, không phải API bắt buộc cho mọi task.
- [ ] `TaskLaunchRequest` chứa đúng năm trường cùng kiểu Java tương ứng.
- [ ] Chọn `uri` artifact từ allowlist, đúng scheme mà deployer hỗ trợ.
- [ ] `commandlineArguments` đã được validate và không chứa secret.
- [ ] `environmentProperties` chỉ chứa giá trị môi trường được phép truyền.
- [ ] `deploymentProperties` dùng đúng key theo triển khai `TaskLauncher` thực tế.
- [ ] `applicationName` rõ ràng; không trộn với business key hoặc TaskExecution ID.
- [ ] Producer/sink kiểm thử round-trip payload đúng kiểu/schema, không deserialise tùy ý.
- [ ] Có bean TaskLauncher, binder, quyền hạ tầng và cấu hình artifact repository phù hợp.
- [ ] Có correlation/request ID để lần theo message, platform process và TaskRepository.
- [ ] Không báo thành công nghiệp vụ khi mới hoàn tất publish hoặc launch.
- [ ] Broker redelivery và retry được xử lý an toàn bằng idempotency/reconciliation.
- [ ] Có metrics, timeout, xử lý dead-letter và giới hạn tài nguyên theo yêu cầu.
- [ ] Nếu chạy Spring Batch, đã phân biệt TaskExecution với JobExecution.

## 12. Ghi nhớ

**`TaskLaunchRequest` là dữ liệu yêu cầu khởi chạy trong nhánh API hỗ trợ Spring Cloud Stream của Spring Cloud Task**, với năm thành phần: **`uri`**, **`commandlineArguments`**, **`environmentProperties`**, **`deploymentProperties`** và **`applicationName`**. `TaskLauncherSink` tiếp nhận object hợp lệ, còn `TaskLauncher` chịu trách nhiệm tạo task trên hạ tầng. Task được tạo sau đó mới ghi nhận **TaskExecution** trong TaskRepository.

Khi thiết kế hệ thống, hãy tách **yêu cầu được chấp nhận**, **tiến trình được tạo**, **task chạy xong** và **nghiệp vụ thành công** thành những trạng thái riêng. Kiểm soát chặt artifact, tham số, môi trường, deployment properties và quyền publish; dùng business key, idempotency và giám sát để ứng dụng có thể chạy lại an toàn nếu message hoặc request bị gửi lặp.

### Tài liệu tham khảo

- [Spring Cloud Task — Spring Cloud Stream Integration: Launching a Task](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/stream.html)
- [Spring Cloud Task 3.0.4 API — TaskLaunchRequest](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html)
- [Spring Cloud Task 3.0.4 API — EnableTaskLauncher](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/annotation/EnableTaskLauncher.html)
- [Spring Cloud Task Reference Guide — Launching a Task from a Spring Cloud Stream](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud Deployer — TaskLauncher API and deployment concepts](https://docs.spring.io/spring-cloud-deployer/docs/current/reference/html/)
