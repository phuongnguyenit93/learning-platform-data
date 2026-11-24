# Phạm vi bảo vệ theo tên tác vụ và cơ sở dữ liệu dùng chung

Trong **Spring Cloud Task**, một tiến trình có thời gian chạy hữu hạn thực hiện công việc rồi kết thúc; mỗi lần chạy được theo dõi bằng một `TaskExecution` trong **TaskRepository**. Khi hai tiến trình của cùng một tác vụ được khởi chạy gần như đồng thời, chúng có thể cùng nhập một tệp, tạo trùng báo cáo hoặc cập nhật cùng các hàng dữ liệu. Cơ chế **single-instance** giúp giới hạn việc chồng lấn, nhưng phải hiểu đúng **khóa dựa trên tên tác vụ** và **các tiến trình phải phối hợp thông qua một cơ sở dữ liệu khóa dùng chung**.

Bài thuộc chương **Khóa và đồng thời**, phân tích phạm vi bảo vệ của `spring.cloud.task.single-instance-enabled`, cách cấu hình repository và cơ chế khóa JDBC, các tình huống triển khai đa máy/đa container, cách kiểm chứng, cùng những giới hạn cần xử lý thêm bằng khóa nghiệp vụ và thiết kế có thể chạy lại an toàn.

## 1. Bài toán: hai tiến trình cùng xử lý một công việc

Giả sử hệ thống bán hàng có tác vụ `invoice-report-task` tạo báo cáo hóa đơn cuối ngày. Bộ lập lịch khởi chạy lúc 02:00, nhưng người vận hành cũng có thể gọi thủ công để tạo lại báo cáo. Hai yêu cầu đến gần nhau:

~~~text
02:00:00  CronJob khởi chạy Task A, --report-date=2026-11-23
02:00:03  API khởi chạy Task B, --report-date=2026-11-23
02:00:04  Cả hai đọc hóa đơn và bắt đầu xuất báo cáo
02:01:15  Hai tiến trình cùng cố ghi đối tượng báo cáo cuối
~~~

Nếu không có biện pháp phối hợp, hệ thống có thể gặp:

- Tạo hai tệp báo cáo cho cùng một kỳ và gửi thông báo hai lần.
- Hai tiến trình đồng thời cập nhật cùng trạng thái `GENERATING`, `READY`.
- Một tiến trình ghi đè tệp đã tạo bởi tiến trình kia.
- Lịch sử TaskExecution ghi **hai lần chạy thành công**, dù nghiệp vụ chỉ muốn một lần phát hành.

Có ba lớp kiểm soát khác nhau:

| Lớp | Phạm vi bảo vệ | Công cụ ví dụ |
| --- | --- | --- |
| **Bộ điều phối** | Những lượt chạy thuộc cùng lịch, workflow hoặc policy | Kubernetes CronJob `concurrencyPolicy: Forbid` |
| **Spring Cloud Task single-instance** | Những lần thực thi **cùng task name** dùng chung cơ chế khóa | `spring.cloud.task.single-instance-enabled=true` |
| **Nghiệp vụ** | Một đối tượng logic, như `(tenantId, reportDate)` | Unique constraint, khóa giao dịch, idempotency key |

Ba lớp này bổ sung cho nhau. Bài học tập trung vào **lớp thứ hai**, đồng thời chỉ rõ khi nào phải thêm lớp thứ nhất và thứ ba.

## 2. Single-instance bảo vệ theo tên tác vụ

Thuộc tính trung tâm:

~~~yaml
spring:
  cloud:
    task:
      single-instance-enabled: true
~~~

Khi tính năng này được bật và **cơ chế khóa dùng chung đã được cấu hình đúng**, Spring Cloud Task chỉ cho phép **một lần thực thi cùng tên tác vụ** giữ quyền chạy tại một thời điểm. Một tiến trình khác cố chạy cùng tên trong khoảng đó sẽ không được tiếp tục thực thi nghiệp vụ theo cách bình thường; cách báo lỗi và thời điểm thoát cần kiểm tra theo phiên bản framework/launcher.

**Tên tác vụ là khóa phân nhóm**. Chẳng hạn:

~~~text
Task A: taskName = invoice-report-task
        args     = --report-date=2026-11-23

Task B: taskName = invoice-report-task
        args     = --report-date=2026-11-24
~~~

Mặc dù hai tiến trình xử lý **hai ngày khác nhau**, single-instance vẫn coi chúng nằm trong cùng phạm vi vì **taskName giống nhau**. Nếu A đang giữ khóa, B không thể đi tiếp theo chế độ single-instance, bất kể `report-date` khác nhau.

Ngược lại:

~~~text
Task C: taskName = invoice-report-task
Task D: taskName = order-import-task
~~~

C và D có **hai tên khác nhau**, nên single-instance không tự ngăn chúng chạy song song, ngay cả khi cả hai sử dụng chung CSDL nghiệp vụ.

### 2.1. Tên tác vụ đến từ đâu?

Trong cấu hình phổ biến, Spring Cloud Task xác định tên qua cơ chế `TaskNameResolver`; giá trị `spring.application.name` giúp thiết lập tên ứng dụng/tác vụ ổn định:

~~~yaml
spring:
  application:
    name: invoice-report-task
~~~

Ứng dụng có thể dùng một `TaskNameResolver` tùy biến nếu muốn chính sách đặt tên riêng. Khi nhiều instance phải khóa nhau, **tất cả phải tính ra cùng một tên**; chỉ cần một instance dùng tên khác, hai instance đã rơi vào hai nhóm khóa khác nhau.

Không nên thay đổi tên theo số Pod, hostname, mã lần chạy hoặc timestamp nếu mục tiêu là chặn các bản sao của **cùng một loại tác vụ**. Những tên luôn khác nhau khiến giới hạn theo tên mất tác dụng.

## 3. Tại sao cần cơ sở dữ liệu dùng chung?

Một ứng dụng Spring Cloud Task có thể chạy trên nhiều máy hoặc container, không cùng vùng nhớ JVM. Biến `synchronized`, `ReentrantLock` hay một cờ boolean trong một tiến trình **chỉ phối hợp các thread của tiến trình đó**; chúng không bảo vệ được hai Pod độc lập.

Cơ chế single-instance trong Spring Cloud Task sử dụng thành phần của **Spring Integration** cho việc khóa liên tiến trình qua JDBC. Khi nhiều tiến trình cùng nhìn thấy **một kho khóa bền vững**, chúng có thể cạnh tranh trên cùng một khóa đại diện cho task name. Chỉ một tiến trình được giữ khóa đúng cách; những tiến trình khác không được chạy đồng thời với nó.

~~~mermaid
flowchart TB
    LA["Cron / API"] --> PA["Pod A<br/>taskName=invoice-report-task"]
    LB["Gọi thủ công"] --> PB["Pod B<br/>taskName=invoice-report-task"]
    PA --> KA["Yêu cầu khóa: invoice-report-task"]
    PB --> KB["Yêu cầu khóa: invoice-report-task"]
    KA --> DB[("CSDL khóa JDBC dùng chung<br/>ví dụ bảng INT_LOCK")]
    KB --> DB
    DB --> R{"Chỉ một bên giữ khóa?"}
    R -->|Có| S["Một Pod thực thi nghiệp vụ"]
    R -->|Bên còn lại| F["Lượt chạy còn lại bị từ chối / không vào vùng bảo vệ"]
    S --> T[("TaskRepository<br/>metadata TaskExecution")]
~~~

**“Dùng chung cơ sở dữ liệu” phải hiểu ở mức kho khóa thật sự.** Hai container cùng nhận một JDBC URL nhưng khác schema, khác bảng khóa hoặc bị cấu hình dùng các registry độc lập chưa chắc nhìn thấy khóa của nhau. Ngược lại, các tiến trình dùng cùng bảng khóa/namespace thông qua một registry phù hợp mới có thể phối hợp.

### 3.1. TaskRepository và kho khóa là hai trách nhiệm

| Thành phần | Dữ liệu chính | Dùng để làm gì? |
| --- | --- | --- |
| **TaskRepository** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, metadata kết thúc | Theo dõi lịch sử mỗi lần chạy, trạng thái và mã thoát |
| **Kho khóa JDBC của Spring Integration** | Bản ghi khóa, ví dụ bảng `INT_LOCK` | Phân xử instance nào được giữ khóa cho cùng tên tác vụ |
| **CSDL nghiệp vụ** | Đơn hàng, báo cáo, trạng thái nhập, khóa duy nhất | Bảo đảm nhất quán và idempotency đối với dữ liệu thực tế |

Các bảng TaskExecution **không tự biến thành distributed lock** chỉ vì nhiều tiến trình dùng cùng TaskRepository. Cơ chế single-instance cần dependency và hạ tầng khóa hỗ trợ đúng cách.

Spring Integration JDBC có schema dành cho khóa, thường với bảng mang tên `INT_LOCK`. Tên bảng, cột, schema, prefix, region và các chi tiết thiết lập có thể thay đổi theo phiên bản hay tùy biến của `LockRepository`. Hãy dùng **DDL tương thích với Spring Integration JDBC đang triển khai**. Đừng suy luận rằng thay `spring.cloud.task.table-prefix` sẽ tự thay tên bảng khóa Spring Integration; hai loại schema có vòng đời cấu hình riêng.

### 3.2. Cùng TaskRepository nhưng khác kho khóa

Giả sử Pod A và Pod B ghi `TASK_EXECUTION` vào chung một schema, nhưng:

- A dùng kho khóa JDBC tại `db1.schema_x.INT_LOCK`.
- B dùng kho khóa JDBC tại `db1.schema_y.INT_LOCK`.

Nếu không được cấu hình liên thông, mỗi Pod có thể thấy khóa **trống** trong bảng của chính mình. Cả hai có thể chạy, dù lịch sử TaskExecution cuối cùng đều xuất hiện ở cùng repository.

Vì vậy, chỉ kiểm tra “cả hai thấy bảng TaskExecution” **chưa đủ** để chứng minh single-instance đang bảo vệ đúng phạm vi.

## 4. Điều kiện để giới hạn có hiệu lực

Cần đồng thời xác nhận những yếu tố sau.

### 4.1. Tất cả instance bật tính năng

Cấu hình bật tính năng phải có hiệu lực trên **mọi tiến trình có thể cạnh tranh**. Nếu chỉ A bật single-instance còn B vẫn chạy độc lập khi không xin khóa, B có thể xâm nhập vùng xử lý dù A đang giữ khóa.

~~~properties
spring.cloud.task.single-instance-enabled=true
~~~

Không được xem một tệp YAML trong repository là bằng chứng tất cả Pod đã nạp giá trị này: profile, biến môi trường, Config Server hoặc đối số dòng lệnh có thể ghi đè. Phải xác nhận cấu hình hiệu lực trong đúng image/deployment.

### 4.2. Dependency Spring Integration phù hợp

Tính năng single-instance sử dụng hạ tầng khóa từ Spring Integration. Tùy nhánh Spring Cloud Task, cần có các module phù hợp, thường gồm **`spring-integration-core`** và **`spring-integration-jdbc`**. Ví dụ khai báo các dependency Maven chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jdbc</artifactId>
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

Không ấn định phiên bản các dependency riêng lẻ khi dùng BOM; Spring Boot, Spring Cloud Task và Spring Integration phải **tương thích theo release train** của hệ thống.

### 4.3. Kho khóa được tạo và dùng đúng

Trước khi triển khai:

1. Cài đặt schema khóa của Spring Integration JDBC đúng với DBMS.
2. Xác nhận các Pod dùng **chung** DataSource/LockRepository và namespace khóa (nếu có tùy biến).
3. Đảm bảo quyền SQL đọc/ghi/xóa/cập nhật cho bảng khóa theo cơ chế thư viện.
4. Kiểm tra tài nguyên DB và kết nối ổn định trong suốt thời gian giữ khóa.
5. Kiểm thử thực tế với **hai tiến trình** thay vì chỉ kiểm tra một instance chạy thành công.

Một kho khóa trong bộ nhớ JVM hoặc một DB nhúng được tạo riêng cho từng container không cung cấp phối hợp liên tiến trình. Nếu dùng PostgreSQL chung, cần chú ý JDBC URL, database, schema và dữ liệu khởi tạo thật sự giống nhau.

### 4.4. Vòng đời task phải bao trùm vùng xử lý

Khóa chỉ bảo vệ khoảng thời gian mà cơ chế Task đang giữ khóa. Nếu runner tạo một thread nền hoặc gọi hệ thống async rồi **kết thúc ngay**, framework có thể xem Task đã hoàn thành và giải phóng khóa **trước khi công việc thật sự kết thúc**.

Ví dụ rủi ro:

~~~java
@Bean
ApplicationRunner unsafeRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> importData()); // Trả về ngay.
    };
}
~~~

Trong tác vụ hữu hạn, hãy đợi kết quả của việc bất đồng bộ, kiểm tra exception và chỉ cho runner kết thúc khi công việc được coi là hoàn tất.

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> job = executor.submit(() -> importData());
        job.get(); // Chờ kết quả; exception được phản ánh cho runner.
    };
}
~~~

Ví dụ chỉ minh họa thời điểm kết thúc; cần cung cấp `ExecutorService` bean, bảo đảm cleanup tài nguyên và xử lý interrupt phù hợp trong ứng dụng thực tế.

## 5. Ma trận phạm vi bảo vệ

Giả sử cả hai tiến trình đều triển khai tính năng đúng cách và kho khóa được cấu hình như mô tả. “Bị chặn” nghĩa là **không được thực thi nghiệp vụ đồng thời theo cơ chế single-instance**; cách ghi metadata và mã thoát phụ thuộc phiên bản.

| Tiến trình A và B | Tên Task | Kho khóa JDBC | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| Cùng loại tác vụ trên hai Pod | **Giống nhau** | **Cùng bảng, cùng namespace** | Một bên giữ khóa; bên kia không chạy đồng thời |
| Hai kỳ báo cáo của cùng ứng dụng | **Giống nhau** | **Cùng** | Bị giới hạn dù `--report-date` khác |
| Cùng nguồn nhập nhưng triển khai app với hai tên khác | **Khác nhau** | **Cùng** | Không bị single-instance khóa chéo theo tên |
| Cùng tên Task trong hai môi trường dùng DB khác nhau | **Giống nhau** | **Khác** | Hai bên có thể chạy song song |
| Cùng JDBC server nhưng lock table/schema khác | **Giống nhau** | **Khác namespace khóa** | Không có bảo đảm loại trừ lẫn nhau |
| Cùng tên và cùng kho khóa nhưng một bên tắt single-instance | **Giống nhau** | **Cùng** | Bên không xin khóa có thể chạy song song |
| Hai tên khác nhau, đụng cùng bảng nghiệp vụ | **Khác nhau** | **Cùng** | Không tự ngăn va chạm dữ liệu nghiệp vụ |
| Cùng task name, chạy lại sau khi lần trước kết thúc | **Giống nhau** | **Cùng** | Được phép chạy tiếp; không tự chống xử lý lặp |

### Đọc đúng ma trận

**Cùng tên và cùng kho khóa** là điều kiện để cơ chế giới hạn hoạt động giữa các tiến trình. Chỉ cùng tên **không đủ** khi mỗi instance dùng database riêng. Chỉ cùng database **không đủ** khi khóa có tên khác hoặc nằm ở hai bảng/namespace khác nhau.

Các tham số `--tenant`, `--date`, `--source-id` **không tham gia mặc định vào khóa single-instance**. Nếu muốn cho phép báo cáo ngày A chạy song song với ngày B nhưng chặn hai lần chạy cùng ngày, cần khóa **theo business key**; không nên kỳ vọng single-instance tự nhận biết tham số.

## 6. Ví dụ cấu hình trên hai Pod dùng PostgreSQL

Ứng dụng `invoice-report-task` chạy hữu hạn, ghi TaskExecution vào PostgreSQL và bật giới hạn theo tên. Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      single-instance-enabled: true
      initialize-enabled: false
~~~

**Giải thích phạm vi:**

- `spring.application.name`: giúp tạo tên Task nhất quán giữa các Pod.
- `spring.datasource.*`: cung cấp kết nối CSDL cho các thành phần JDBC được cấu hình sử dụng nó. Nếu tự tạo nhiều DataSource, phải kiểm tra đúng DataSource của TaskRepository và LockRepository.
- `spring.cloud.task.single-instance-enabled`: yêu cầu cơ chế giới hạn một lần chạy theo task name.
- `spring.cloud.task.initialize-enabled=false`: tắt khởi tạo tự động schema Task; bảng Task và bảng khóa Spring Integration phải được tạo trước bằng migration riêng.

Các biến môi trường cần được cấp cho cả hai Pod, ví dụ:

~~~text
Pod A:
  TASK_DB_URL=jdbc:postgresql://postgres.internal:5432/task_metadata
  TASK_DB_USER=task_runtime

Pod B:
  TASK_DB_URL=jdbc:postgresql://postgres.internal:5432/task_metadata
  TASK_DB_USER=task_runtime
~~~

Giá trị URL và user chỉ là minh họa. Mật khẩu phải đến từ hệ thống secret; **không in ra log hoặc truyền dưới dạng đối số ứng dụng** vì đối số có thể được lưu vào `TASK_EXECUTION_PARAMS`.

Trong Kubernetes, mỗi Pod có thể nhận các biến từ cùng ConfigMap/Secret, nhưng tên secret giống nhau không bảo đảm các Pod thực sự kết nối cùng database. Đối chiếu đường dẫn kết nối ở tầng hạ tầng, schema thực tế và kết quả kiểm thử khóa.

### 6.1. Bài chạy mô phỏng để quan sát khóa

Một runner có chủ đích giữ tiến trình trong thời gian ngắn:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class LockScopeTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockScopeTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner holdRunner() {
        return args -> {
            System.out.println("Entered protected task work");
            Thread.sleep(60_000); // Chỉ dùng để thử nghiệm.
            System.out.println("Finished task work");
        };
    }
}
~~~

Chỉ chạy mẫu trên môi trường kiểm thử. Cần các dependency đã nêu, schema Task và schema khóa JDBC; người chạy không nên dùng DB sản xuất.

Tại hai terminal/container cùng ứng dụng, cấu hình:

~~~bash
# Terminal A:
java -jar lock-scope-task.jar

# Terminal B: khởi chạy khi A vẫn đang ở Thread.sleep(...)
java -jar lock-scope-task.jar
~~~

**Kết quả cần kiểm chứng:** Terminal A vào runner, còn B **không được đồng thời in `Entered protected task work`** khi A đang giữ khóa. Lỗi và mã thoát của B có thể khác tùy phiên bản cơ chế single-instance và chính sách chờ/kiểm tra lock. Sau khi A kết thúc và nhả khóa, chạy lại B thì phải đi vào runner bình thường.

Nếu B cũng vào runner ngay, hãy kiểm tra tên Task, cơ chế khóa có được bật ở cả hai bên, classpath, bảng khóa, DataSource và namespace trước khi nghi ngờ framework.

## 7. Single-instance có tạo được “exactly once” không?

**Không.** Single-instance xử lý việc **hai lần chạy cùng tên đồng thời**. Nó không ngăn một lần chạy mới xuất hiện **sau khi** lần trước đã kết thúc:

~~~text
02:00  Task A nhập source-id=feed-23, thành công, nhả khóa
02:05  Task B nhập lại source-id=feed-23, lấy khóa thành công
~~~

Cả hai đều chạy **lần lượt** và hoàn toàn phù hợp với single-instance. Nếu B tạo thêm các đơn hàng trùng, lỗi nằm ở thiết kế nghiệp vụ.

Đối với nhập dữ liệu, có thể thiết lập khóa duy nhất theo `source_id` hoặc `external_order_id`, kiểm tra checksum và dùng upsert/transaction phù hợp. Với báo cáo, có thể đặt unique constraint trên `(tenant_id, report_date, report_version)`. Với bảo trì, dùng điều kiện cutoff cố định và xử lý theo lô có thể chạy lại.

~~~sql
CREATE TABLE report_publication (
    tenant_id     varchar(100) NOT NULL,
    report_date   date NOT NULL,
    version       integer NOT NULL,
    status        varchar(30) NOT NULL,
    artifact_uri  text,
    PRIMARY KEY (tenant_id, report_date, version)
);
~~~

Ràng buộc duy nhất làm cho cùng một bản báo cáo logic không thể được chèn trùng vô điều kiện, **kể cả khi bộ điều phối vô tình chạy hai loại Task khác tên**. Tuy nhiên, chỉ có unique constraint vẫn chưa đủ để ngăn gửi email hoặc gọi API bên ngoài hai lần; các tác dụng phụ đó cần cơ chế idempotency riêng, ví dụ outbox hoặc idempotency key ở hệ đích.

**TaskExecution ID** là định danh **lần chạy kỹ thuật**, không phải khóa nghiệp vụ. Không dùng TaskExecution ID làm cách chống trùng một tệp đầu vào qua nhiều lần retry.

## 8. Khi cần khóa theo tenant, ngày hoặc đối tượng nguồn

Bài toán nhiều tenant thường muốn:

- Hai lượt tạo **cùng** `(tenantId, reportDate)` không chạy trùng.
- Hai tenant hoặc hai ngày **khác nhau** được phép xử lý song song.

Single-instance theo `invoice-report-task` sẽ quá rộng: mọi kỳ và mọi tenant đều tranh cùng một khóa. Có thể chọn một trong hai hướng:

1. **Giữ single-instance theo tên** nếu công việc chạm nguồn lực toàn cục, không an toàn khi chạy hai kỳ cùng lúc.
2. **Dùng khóa nghiệp vụ** dựa trên `(tenantId, reportDate)` nếu muốn chạy nhiều kỳ song song, kèm unique constraint/transaction ở database để tạo quyền sở hữu xử lý.

Ví dụ một bảng khai báo quyền xử lý một kỳ:

~~~sql
CREATE TABLE report_claim (
    tenant_id       varchar(100) NOT NULL,
    report_date     date NOT NULL,
    state           varchar(30) NOT NULL,
    owner_id        varchar(100),
    claimed_at      timestamptz,
    PRIMARY KEY (tenant_id, report_date)
);
~~~

Ứng dụng có thể dùng một giao dịch để tạo/chiếm quyền claim dựa trên unique key, kiểm tra trạng thái trước đó và thay đổi owner theo một quy tắc có kiểm soát. **Không** chỉ viết `SELECT ... WHERE state='NEW'` rồi `UPDATE` ở hai giao dịch không đồng bộ, vì cả hai có thể đọc cùng trạng thái cũ và cùng làm việc.

Nếu dùng lease có thời hạn để phục hồi sau crash, cần cơ chế **fencing token** hoặc điều kiện cập nhật chỉ chấp nhận owner hiện tại. Bởi lease có thể hết hạn khi tiến trình cũ vẫn sống, tiến trình mới lấy quyền và cả hai cùng cố ghi kết quả. Một khóa có TTL không tự làm cho tác dụng phụ cũ vô hiệu.

Đổi `TaskNameResolver` để nhúng trực tiếp `tenantId` vào tên Task **không phải giải pháp mặc định**: tên có thể có cardinality lớn, dễ gây lệch giữa các phiên bản deployment, phức tạp truy vấn lịch sử và vẫn không giải quyết retry sau khi khóa được giải phóng.

## 9. Khóa, TTL và sự cố tiến trình

Cơ chế khóa phân tán phụ thuộc **quyền sở hữu** và **vòng đời khóa**. Hệ thống cần xử lý các tình huống:

| Sự cố | Rủi ro | Cách chuẩn bị |
| --- | --- | --- |
| Pod bị kill trước khi nhả khóa đúng cách | Bản ghi khóa còn lưu, lần chạy sau không lấy được khóa ngay | Hiểu cơ chế TTL/hồi phục theo phiên bản, giám sát khóa kẹt và thử lỗi crash |
| Chạy dài hơn thời gian hiệu lực khóa | Một tiến trình khác có thể lấy khóa trong khi tiến trình cũ còn chạy | Chọn TTL phù hợp, theo dõi thời gian thực thi và dùng fencing/idempotency ở nghiệp vụ |
| Mất kết nối tới kho khóa | Không xác định chắc quyền sở hữu | Theo nguyên tắc an toàn: dừng hoặc không bắt đầu vùng xử lý có thể gây trùng |
| Task trả về trước khi công việc async hoàn tất | Khóa được nhả quá sớm | Đợi Future, transaction và xử lý đầu ra hoàn tất |
| Mỗi Pod dùng H2 in-memory riêng | Không có cùng trạng thái khóa | Dùng kho JDBC chia sẻ thực sự hoặc cơ chế khóa phân tán tương đương |
| Hai instance khác phiên bản/khác cấu hình | Cách sinh tên khóa hoặc namespace có thể không nhất quán | Triển khai đồng bộ, kiểm chứng khi rolling update |
| Người vận hành xóa thủ công bản ghi lock | Tiến trình cũ có thể vẫn đang chạy và giữ quyền xử lý thực tế | Có runbook, kiểm tra process sống và cách phục hồi trước khi can thiệp bảng khóa |

Một số phiên bản Spring Cloud Task hỗ trợ các tùy chọn như `spring.cloud.task.single-instance-lock-ttl` và `spring.cloud.task.single-instance-lock-check-interval`. Cần đối chiếu **metadata của đúng phiên bản** để biết tên khóa, đơn vị, giá trị mặc định và thuật toán. **Không chọn TTL chỉ bằng cách lấy thời gian chạy trung bình**; hãy tính đến tình huống chậm nhất, xử lý ngắt, mạng chập chờn và quyền sở hữu khi khóa hết hiệu lực.

Lưu ý: TTL của khóa và timeout của Kubernetes Job hoặc workflow **không phải một giá trị duy nhất**. Timeout của Job có thể kill Pod, nhưng cơ chế nhả khóa còn phụ thuộc bản chất lỗi và LockRepository. Không xóa khóa đang giữ chỉ để “chạy lại cho nhanh” mà chưa kiểm tra instance cũ.

## 10. Khác biệt với Kubernetes concurrencyPolicy

Với Kubernetes CronJob:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-invoice-report
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example/invoice-report-task:1.0.0
              args:
                - "--report-date=2026-11-23"
~~~

`Forbid` tránh chồng lấn các Job **do chính CronJob này tạo**, còn cơ chế single-instance của Spring Cloud Task giới hạn các tiến trình **cùng task name** chia sẻ kho khóa. Một tác vụ được gọi riêng từ API hay một CronJob khác không thuộc phạm vi `Forbid` của CronJob ban đầu, nhưng vẫn có thể tranh cùng khóa Spring Cloud Task nếu cấu hình giống nhau.

Ví dụ trên đặt `--report-date` cố định **chỉ để minh họa**, không nên triển khai lịch lặp với một ngày hardcode. Trong sản xuất, bộ điều phối hoặc logic ứng dụng phải xác định ngày nghiệp vụ cụ thể theo timezone đã quy ước. Thuộc tính `timeZone` cần phiên bản Kubernetes có hỗ trợ.

## 11. Quan sát và chẩn đoán sự cố đồng thời

Cần liên kết được **tên tác vụ**, **TaskExecution ID**, **mã yêu cầu của bộ điều phối**, **tham số nghiệp vụ an toàn** và **kết quả của lần tranh khóa**.

Gợi ý log có cấu trúc:

~~~text
event=task_start_requested taskName=invoice-report-task
  businessKey=acme:2026-11-23 runRef=workflow-1042
event=task_lock_acquired taskName=invoice-report-task
  runRef=workflow-1042
event=task_completed taskName=invoice-report-task
  executionId=4102 runRef=workflow-1042 exitCode=0
~~~

Các event cụ thể phụ thuộc instrumentation của ứng dụng và framework; **Spring Cloud Task không mặc nhiên phát đúng các dòng log này**. Không ghi token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm.

Có thể truy vấn TaskRepository:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-report-task'
ORDER BY START_TIME DESC;
~~~

Truy vấn này cho biết **lịch sử TaskExecution**, không phải trạng thái khóa hiện tại. `END_TIME IS NULL` không chứng minh tiến trình còn sống: nó cũng có thể đã bị kill và không kịp cập nhật metadata. Một lượt bị từ chối khi xin khóa cũng **không nên mặc định** sẽ để lại bản ghi TaskExecution với exit code cụ thể; cách ghi phụ thuộc phiên bản và thời điểm framework phát hiện xung đột.

Để điều tra thực tế, đối chiếu thêm:

- Log của cả hai Pod và lý do fail tại bước acquire lock.
- Cấu hình hiệu lực của `single-instance-enabled` và tên task mỗi Pod.
- Dấu hiệu cả hai kết nối **chung kho khóa**: JDBC URL, database, schema, lock namespace, migration.
- Trạng thái Pod/Job, thời gian sống, thời gian chạy, retry và cách timeout.
- Bảng trạng thái nghiệp vụ để phát hiện kết quả trùng sau retry.

Nên có phép đo về số lần tranh khóa, thời gian chờ, lần bị từ chối, tuổi của khóa bất thường và số lượt xử lý trùng theo business key; các số liệu này cần thiết kế và xuất qua công cụ quan sát phù hợp.

## 12. Quy trình kiểm chứng trong môi trường thử nghiệm

Thực hiện các thử nghiệm sau **sau khi đã tạo schema JDBC khóa và TaskRepository**:

| Thử nghiệm | Cách làm | Kết quả kỳ vọng |
| --- | --- | --- |
| **A. Cùng tên, cùng DB** | Chạy A trong khi runner đang ngủ, khởi chạy B ngay | Chỉ một bên vào vùng xử lý cùng lúc |
| **B. Khác tham số, cùng tên** | Đổi `--report-date` ở B nhưng giữ `taskName` | B vẫn bị giới hạn trong lúc A giữ khóa |
| **C. Khác tên, cùng DB** | Dùng hai `spring.application.name` khác nhau | Có thể cùng chạy; xác nhận lock chỉ bảo vệ theo tên |
| **D. Cùng tên, khác DB** | B trỏ tới DB khóa độc lập | Không có bảo đảm phối hợp; bài test chứng minh rủi ro |
| **E. Một bên tắt lock** | A bật, B tắt single-instance | Phạm vi bảo vệ bị phá vỡ |
| **F. Chạy lần lượt** | Đợi A hoàn tất rồi khởi chạy B cùng tham số | B có thể chạy; xác minh idempotency tránh trùng kết quả |
| **G. Bị kill** | Kill A khi đang giữ khóa; thử B theo runbook | Quan sát cơ chế hồi phục khóa và yêu cầu timeout/fencing |
| **H. Rolling update** | Chạy hai bản image/phiên bản có cùng tên và cùng kho khóa | Xác nhận hai bản vẫn tuân theo cùng phạm vi khóa |

Khi ghi nhận, thu thập lệnh gọi, timestamp, task name, target database/schema và log kết quả. **Không** dùng môi trường sản xuất hoặc chủ động phá khóa đang có người dùng thật.

### Bài tập thực hành

Một nền tảng đa tenant chạy `cleanup-task` để xóa dữ liệu tạm đã hết hạn. Nhóm vận hành đưa ra ba yêu cầu:

1. Không cho phép **hai Pod cùng thực thi bất kỳ tác vụ cleanup nào** tại cùng thời điểm.
2. Cho phép `cleanup-task` và `invoice-report-task` chạy đồng thời dù dùng chung TaskRepository.
3. Nếu retry `cleanup-task` sau lỗi, không xóa dữ liệu ngoài `cutoff` và không lặp các tác dụng phụ.

Hãy đề xuất cấu hình và thiết kế:

- Đặt tên Task ổn định; bật single-instance trên mọi Pod cleanup; dùng chung cơ chế khóa JDBC.
- Không cần khóa chéo với `invoice-report-task` vì tên khác, trừ khi hai công việc tranh một tài nguyên nghiệp vụ chung và cần cơ chế bổ sung.
- Khóa cutoff theo tham số ngày/giờ tuyệt đối; xóa theo lô/transaction an toàn; xác định kết quả theo business key và có khả năng tiếp tục sau lỗi.
- Kiểm thử hai Pod cùng tên, hai Pod khác tên, mất DB khóa và restart tiến trình.

**Câu hỏi mở rộng:** nếu yêu cầu đổi thành “chỉ chặn cleanup có cùng `tenantId`; các tenant khác phải chạy song song”, tại sao single-instance khóa theo tên `cleanup-task` lại quá rộng? Hãy phác thảo một bảng claim với unique key `(tenant_id, cleanup_cutoff)` và quy tắc transaction/fencing để đáp ứng.

## 13. Các điểm cần ghi nhớ

1. **Single-instance giới hạn theo `taskName`**, không tự phân biệt tham số ngày, tenant hay source-id.
2. **Cùng tên là chưa đủ**: các instance phải thực sự phối hợp qua **cùng backend khóa JDBC**, schema và namespace phù hợp; mọi tiến trình cạnh tranh đều phải tham gia cơ chế khóa.
3. **TaskRepository theo dõi lần chạy**, còn kho khóa của Spring Integration quyết định quyền thực thi đồng thời; dữ liệu nghiệp vụ cần cơ chế đảm bảo nhất quán riêng.
4. Cơ chế này **không tạo exactly-once**: chạy tuần tự lần thứ hai vẫn có thể lặp dữ liệu. Dùng idempotency, unique constraint và transaction theo business key.
5. Chọn timeout/TTL, kiểm thử crash, không giải phóng khóa trước khi công việc async hoàn tất, và tránh thao tác thủ công với khóa đang được giữ.
6. Giới hạn của CronJob, của Spring Cloud Task và của nghiệp vụ là **ba phạm vi khác nhau**. Thiết kế giải pháp dựa trên chính xác phạm vi cần bảo vệ.

### Tài liệu tham khảo

- [Spring Cloud Task Reference — Features: Restricting Spring Cloud Task Instances](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task Reference — TaskRepository, TaskExecution](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
