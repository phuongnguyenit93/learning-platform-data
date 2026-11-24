# Tổ chức dự án và cấu hình theo môi trường

## Mục tiêu

Trong mô-đun **SPRING_CLOUD_TASK (Spring Cloud Task)**, một ứng dụng thường được khởi động để thực hiện một công việc hữu hạn rồi kết thúc: xuất báo cáo, đồng bộ dữ liệu, dọn dẹp tài nguyên hoặc kích hoạt một quy trình xử lý theo yêu cầu. Spring Cloud Task giúp theo dõi thời điểm bắt đầu, kết thúc, trạng thái và kết quả mỗi lần chạy trong cơ sở dữ liệu thông qua `TaskRepository`.

Sau bài học thuộc chương **Môi trường**, bạn có thể:

- Phân chia mã nguồn theo trách nhiệm để logic tác vụ độc lập với cách khởi chạy và cấu hình hạ tầng.
- Thiết lập cấu hình chung và cấu hình riêng cho `local`, `test`, `prod` bằng Spring Profiles.
- Cung cấp `DataSource` và chuẩn bị bảng metadata cho `TaskRepository` ở từng môi trường.
- Truyền tham số nghiệp vụ, quản lý bí mật, xử lý thất bại và kiểm tra kết quả thực thi.
- Chuẩn bị ứng dụng để chạy theo lịch hoặc theo yêu cầu, kể cả khi phối hợp với Spring Batch.

## 1. Đặc điểm của dự án Spring Cloud Task

Ứng dụng web thường phục vụ yêu cầu trong thời gian dài. Một ứng dụng Spring Cloud Task đi theo vòng đời khác:

1. Bộ lập lịch, dòng lệnh hoặc hệ thống điều phối khởi động một **tiến trình mới**.
2. Spring Boot nạp cấu hình và khởi tạo các bean; Spring Cloud Task tạo bản ghi `TaskExecution` trong kho metadata khi hạ tầng sẵn sàng.
3. `ApplicationRunner` hoặc `CommandLineRunner` thực hiện công việc.
4. Framework cập nhật thông tin kết thúc, mã thoát và lỗi vào `TaskRepository`; tiến trình kết thúc để hệ thống bên ngoài quyết định có chạy lại hay không.

Điểm cần phân biệt là **tên tác vụ** (`spring.cloud.task.name`) mô tả loại công việc, còn **mỗi lần chạy** có một mã `TASK_EXECUTION_ID` riêng. Không cần thay đổi tên tác vụ theo ngày chỉ để phân biệt các lần chạy. Tham số như ngày xử lý hay mã lô phải được truyền và kiểm soát riêng.

`TaskRepository` của Spring Cloud Task lưu metadata của tác vụ. Nếu tác vụ sử dụng Spring Batch, `JobRepository` là kho metadata khác, lưu thông tin `JobExecution` và `StepExecution`; Spring Cloud Task có thể ghi liên kết giữa một lần chạy Task và các lần chạy Batch. Hai loại repository có mục đích khác nhau dù có thể cùng sử dụng một máy chủ cơ sở dữ liệu.

## 2. Tổ chức thư mục và trách nhiệm

Ví dụ ứng dụng `daily-order-export` xuất dữ liệu đơn hàng mỗi ngày:

```text
daily-order-export/
├── pom.xml
├── .gitignore
├── src/
│   ├── main/
│   │   ├── java/com/example/orderexport/
│   │   │   ├── OrderExportTaskApplication.java
│   │   │   ├── task/
│   │   │   │   └── OrderExportRunner.java
│   │   │   ├── application/
│   │   │   │   └── OrderExportService.java
│   │   │   ├── domain/
│   │   │   │   └── ExportPeriod.java
│   │   │   ├── infrastructure/
│   │   │   │   └── OrderQueryRepository.java
│   │   │   └── config/
│   │   │       └── ExportProperties.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-test.yml
│   │       ├── application-prod.yml
│   │       └── db/migration/
│   └── test/
│       ├── java/com/example/orderexport/
│       └── resources/
└── deploy/
    └── cronjob.yaml
```

| Thành phần | Trách nhiệm |
| --- | --- |
| `OrderExportTaskApplication` | Điểm vào Spring Boot, kích hoạt Spring Cloud Task. |
| `task/` | Đọc tham số mỗi lần chạy, xác thực đầu vào, gọi dịch vụ và để lỗi lan truyền khi tác vụ thất bại. |
| `application/` | Điều phối các bước nghiệp vụ, kiểm soát giao dịch và tính chạy lại an toàn. |
| `domain/` | Quy tắc, giá trị và bất biến nghiệp vụ, hạn chế phụ thuộc vào môi trường. |
| `infrastructure/` | Truy cập cơ sở dữ liệu nghiệp vụ, API ngoài, tệp và dịch vụ đích. |
| `config/` | Ràng buộc cấu hình ứng dụng, tạo các bean liên quan. |
| `resources/application*.yml` | Khai báo cấu hình chung và phần khác biệt theo profile. |
| `db/migration/` | Quản lý thay đổi lược đồ bằng công cụ migration khi dự án cần; phải bao gồm cách triển khai schema Task tương thích. |
| `deploy/` | Cấu hình chạy theo lịch/triển khai, tách khỏi logic Java. |

Đây là cách tổ chức tham khảo, không phải cấu trúc bắt buộc của framework. Với tác vụ nhỏ, có thể gộp một số package; với nhiều tác vụ độc lập, nên cân nhắc tách chúng thành các ứng dụng triển khai riêng để mỗi tác vụ có thời gian chạy, tài nguyên và lịch phát hành riêng.

**Nguyên tắc:** `Runner` chỉ xử lý vòng đời một lượt chạy. Mã gọi cơ sở dữ liệu, tính toán nghiệp vụ hoặc tích hợp API nên đặt trong dịch vụ và adapter riêng để có thể kiểm thử mà không cần khởi chạy cả ứng dụng Task.

## 3. Phụ thuộc và điểm khởi động

Trong dự án Maven đã khai báo Spring Boot và BOM Spring Cloud **tương thích với nhau**, các phụ thuộc cốt lõi có thể như sau. Phiên bản thực tế phải được chốt theo bảng tương thích của release train đang dùng, không tự trộn các phiên bản Spring Boot và Spring Cloud:

```xml
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
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

`spring-cloud-starter-task` cung cấp tích hợp Spring Cloud Task; `spring-boot-starter-jdbc` hỗ trợ `DataSource`/JDBC; H2 dùng trong ví dụ local/test và PostgreSQL dùng trong ví dụ production. Nếu dự án dùng cơ sở dữ liệu khác, thay JDBC driver và schema metadata phù hợp. Không cần `spring-boot-starter-web` cho tác vụ chỉ chạy dòng lệnh.

Điểm vào tối giản:

```java
package com.example.orderexport;

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
public class OrderExportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderExportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner orderExportRunner() {
        return args -> {
            List<String> dates = args.getOptionValues("businessDate");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Cần đúng một tham số --businessDate=yyyy-MM-dd");
            }

            LocalDate businessDate = LocalDate.parse(dates.get(0));
            // Bản triển khai thực tế: gọi OrderExportService.export(businessDate).
            System.out.println("Đã xử lý ngày nghiệp vụ: " + businessDate);
        };
    }
}
```

`@EnableTask` kích hoạt cơ chế quản lý vòng đời Spring Cloud Task. `ApplicationRunner` nhận tham số theo lượt chạy; ví dụ kiểm tra sự tồn tại và định dạng ngày ngay tại ranh giới ứng dụng. Trong dự án thật, thay dòng in kết quả bằng lời gọi `OrderExportService`. Việc ném ngoại lệ khi tham số sai cho phép framework ghi nhận lỗi thay vì báo hoàn tất giả.

**Lưu ý:** Đoạn mã trên chỉ minh họa vòng đời và cấu hình, chưa thực hiện xuất dữ liệu. Nếu có nhiều runner, cần định rõ thứ tự và tránh các side effect không chủ đích. Không đặt vòng lặp vô hạn, web server hoặc scheduler chạy liên tục trong tiến trình Task, nếu yêu cầu là hoàn thành rồi thoát.

## 4. Chia cấu hình bằng Spring Profiles

Spring Boot tự nạp `application.yml`, sau đó áp dụng phần tương ứng với profile đang được kích hoạt, ví dụ `application-local.yml` hoặc `application-prod.yml`. Một bộ mã nguồn và một artifact có thể được triển khai nhiều môi trường; sự khác nhau chủ yếu là URL dịch vụ, kết nối cơ sở dữ liệu, mức log, tài nguyên và chính sách schema.

| Nguồn cấu hình | Nên chứa | Không nên chứa |
| --- | --- | --- |
| `application.yml` | Tên ứng dụng, tên Task, các mặc định không nhạy cảm, chế độ không mở HTTP. | Mật khẩu và địa chỉ cố định chỉ hợp lệ ở production. |
| `application-local.yml` | H2 hoặc database phát triển, mức log phục vụ gỡ lỗi, schema mẫu. | Credentials sản xuất. |
| `application-test.yml` | Database/cấu hình cô lập cho kiểm thử tự động, giá trị thử nghiệm. | Hệ thống thật hoặc dữ liệu khách hàng. |
| `application-prod.yml` | Quy tắc vận hành, giới hạn connection pool, tham chiếu biến môi trường. | Giá trị bí mật viết trực tiếp. |
| Biến môi trường/secret manager | Thông tin kết nối, token, mật khẩu, tham số triển khai nhạy cảm. | Logic nghiệp vụ Java. |
| Đối số khi chạy | Ngày xử lý, mã lô, profile khi cần ghi đè ở từng lượt. | Mật khẩu có thể xuất hiện trong lịch sử lệnh, log hoặc thông tin tiến trình. |

### 4.1. Cấu hình chung — `application.yml`

```yaml
spring:
  application:
    name: daily-order-export
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-order-export

logging:
  level:
    root: INFO
    com.example.orderexport: INFO
```

`spring.main.web-application-type: none` giúp tiến trình vận hành như ứng dụng dòng lệnh. Tên Task giữ ổn định giữa các lần chạy để có thể tổng hợp lịch sử thực thi.

Không đặt `spring.profiles.active: prod` cứng trong file chung. Môi trường triển khai quyết định profile đang hoạt động qua `SPRING_PROFILES_ACTIVE` hoặc tham số khởi động.

### 4.2. Môi trường local — `application-local.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:taskdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      initialize-enabled: true

logging:
  level:
    com.example.orderexport: DEBUG
```

H2 trong bộ nhớ thuận tiện để chạy thử; dữ liệu lịch sử sẽ biến mất khi tiến trình và database kết thúc. Vì vậy, nó chỉ giúp kiểm tra một lượt chạy, không phù hợp để theo dõi dài hạn. Với một số phiên bản Spring Cloud Task, thuộc tính `spring.cloud.task.initialize-enabled` điều khiển bước khởi tạo bảng metadata. Cần kiểm tra đúng hành vi và tên thuộc tính theo phiên bản framework đã chốt, nhất là khi chuyển hệ quản trị cơ sở dữ liệu.

### 4.3. Môi trường test — `application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:tasktest;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      initialize-enabled: true
```

Dùng profile `test` khi kiểm thử cần một kho metadata độc lập với local và production. Các kiểm thử chạy song song phải có database/schema riêng hoặc cơ chế dọn dữ liệu rõ ràng. Với hành vi phụ thuộc PostgreSQL (kiểu dữ liệu, cú pháp SQL, khóa/giao dịch), kiểm thử tích hợp nên chạy với PostgreSQL thật trong môi trường thử nghiệm, chẳng hạn qua container, thay vì suy ra tính tương thích từ H2.

### 4.4. Môi trường production — `application-prod.yml`

```yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: ${TASK_DB_MAX_POOL_SIZE:4}
  cloud:
    task:
      initialize-enabled: false
```

Ví dụ này giả định production dùng PostgreSQL và **schema metadata Task đã được triển khai trước** bằng quy trình migration/DBA kiểm soát. Việc không tạo bảng tự động khi nhiều bản sao tác vụ khởi động giúp tránh đua tranh DDL hoặc dùng nhầm schema. Biến `TASK_DB_URL` có dạng `jdbc:postgresql://db-host:5432/task_metadata`; các giá trị bí mật phải được nạp từ secret manager, Kubernetes Secret hoặc cơ chế bí mật của hệ thống điều phối.

Không dùng cùng database/schema metadata cho `test` và `prod`. Nếu nhiều ứng dụng Task dùng chung database, cần thống nhất cách phân biệt metadata, schema hoặc table prefix theo khả năng hỗ trợ của phiên bản đang sử dụng.

## 5. Cấu hình `TaskRepository` và quản lý schema

Spring Cloud Task dùng kết nối cơ sở dữ liệu để lưu `TaskExecution`. Khi dùng cấu hình tự động, `DataSource` hợp lệ và các bảng tương thích là hai điều kiện quan trọng. Một số bảng metadata thường gặp gồm:

| Bảng | Ý nghĩa |
| --- | --- |
| `TASK_EXECUTION` | Lần chạy, tên tác vụ, thời điểm bắt đầu/kết thúc, mã thoát và thông tin lỗi. |
| `TASK_EXECUTION_PARAMS` | Tham số của lần thực thi do Task ghi nhận. |
| `TASK_TASK_BATCH` | Liên kết Task execution với Batch job execution khi tích hợp Spring Batch. |

Tên bảng có thể khác nếu hệ thống cấu hình tiền tố hoặc schema riêng. Không nhầm các bảng này với bảng dữ liệu nghiệp vụ như `ORDERS` hay `EXPORT_HISTORY`.

Quy trình phù hợp cho production:

1. Chốt phiên bản Spring Boot, Spring Cloud Task, JDBC driver và hệ quản trị cơ sở dữ liệu; tìm bộ DDL metadata tương ứng đúng với phiên bản đó.
2. Đưa DDL/schema migration vào pipeline triển khai hoặc quy trình DBA; kiểm tra thứ tự triển khai trước khi phát hành Job.
3. Cấp cho tài khoản chạy Task quyền kết nối và DML cần thiết lên schema metadata và dữ liệu nghiệp vụ; hạn chế quyền thay đổi cấu trúc bảng khi không cần.
4. Chạy smoke test một lượt và kiểm tra bản ghi `TaskExecution`, mã thoát và thời điểm kết thúc.
5. Khi nâng cấp thư viện, xem xét thay đổi schema tương ứng trước khi nâng cấp artifact.

Nếu kết nối database thất bại ngay trong giai đoạn khởi động, Spring Cloud Task có thể không ghi được bản ghi thực thi. Vì thế, cần theo dõi cả **trạng thái tiến trình do hệ điều phối cung cấp** lẫn **metadata trong database**. Hai nguồn này bổ sung cho nhau khi chẩn đoán sự cố.

Ví dụ truy vấn lịch sử trong database mẫu (điều chỉnh tên schema/bảng theo triển khai thực tế):

```sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-order-export'
ORDER BY TASK_EXECUTION_ID DESC;
```

Một lượt chạy tốt có thời gian bắt đầu và kết thúc hợp lệ, mã thoát thành công và kết quả nghiệp vụ đã được xác minh. Chỉ có mã thoát bằng 0 chưa đủ chứng minh dữ liệu xuất đúng; cần bổ sung kiểm tra đầu ra hoặc số bản ghi.

## 6. Chạy ứng dụng với profile và tham số

Sau khi dự án được đóng gói thành JAR chạy được, một lượt chạy local có thể dùng:

```bash
java -jar target/daily-order-export.jar \
  --spring.profiles.active=local \
  --businessDate=2026-11-23
```

Tên JAR là ví dụ; dùng đường dẫn artifact thực tế từ cấu hình build. Spring Boot truyền các tùy chọn dạng `--key=value` vào `ApplicationArguments`. Trong mã ở mục 3, `businessDate` là **tham số nghiệp vụ** bắt buộc của mỗi lượt chạy; `spring.profiles.active` là **tham số hạ tầng** quyết định bộ cấu hình.

Trong production, hệ thống điều phối thường đặt `SPRING_PROFILES_ACTIVE=prod` và các biến `TASK_DB_*` trước khi chạy JAR hoặc container. Không cần sửa JAR để thay URL database hay bí mật. Spring Boot hỗ trợ nhiều nguồn cấu hình với thứ tự ưu tiên xác định; tham số dòng lệnh thường ghi đè biến môi trường và tệp cấu hình. Vì vậy, cần rà soát các đối số do scheduler truyền để tránh vô tình ghi đè profile hoặc endpoint quan trọng.

Một lịch chạy có thể được tạo bằng cron hệ điều hành, Kubernetes CronJob, nền tảng điều phối tác vụ hoặc bộ lập lịch bên ngoài. Cùng một ứng dụng cũng có thể được gọi theo yêu cầu qua Job/Task launcher. **Không nên đặt `@Scheduled` trong chính tiến trình Task chỉ để tiến trình nằm chờ vô hạn**: trách nhiệm lặp lại thuộc bộ lập lịch; mỗi lần kích hoạt tạo một lần chạy hữu hạn độc lập.

## 7. Tham số, lỗi và chạy lại an toàn

Tách cấu hình hạ tầng ra khỏi tham số nghiệp vụ giúp tái chạy chính xác một lượt xử lý. Ví dụ `businessDate=2026-11-23` phải có ý nghĩa ổn định bất kể chạy ở local để kiểm thử hay production để xuất báo cáo. Nếu ngày xử lý mặc định phụ thuộc múi giờ, hãy xác định rõ timezone nghiệp vụ để không sinh ngày khác giữa máy phát triển và container.

Các quy tắc thực tế:

- **Xác thực sớm** tham số bắt buộc, định dạng ngày, khoảng dữ liệu và tài nguyên đích; trả lỗi trước khi tạo tác dụng phụ.
- **Không nuốt ngoại lệ**: log có ngữ cảnh rồi để ngoại lệ lan ra khỏi runner khi thao tác thất bại; không giả lập thành công bằng việc chỉ in thông báo lỗi.
- **Thiết kế idempotent**: một lần chạy lại cùng ngày không được nhân đôi kết quả. Có thể dùng khóa nghiệp vụ, upsert, bảng trạng thái xuất, giao dịch và checkpoint tùy nhu cầu.
- **Giới hạn đồng thời**: ngăn hai lần chạy cùng kỳ khi không được phép, chẳng hạn bằng cấu hình concurrency của scheduler kết hợp khóa ở tầng dữ liệu.
- **Phân biệt retry**: retry mạng/DB tạm thời có giới hạn; lỗi dữ liệu hoặc tham số không hợp lệ cần báo thất bại để người vận hành xử lý.
- **Ràng buộc thời gian**: khai báo timeout cho kết nối ngoài, giới hạn thời gian thực thi và chính sách chấm dứt Job ở hệ điều phối.

Một trường hợp dễ sai: runner bắt mọi ngoại lệ, ghi log rồi trả về bình thường. Khi đó hệ điều phối có thể thấy tiến trình thành công và `TaskRepository` cũng có thể đánh dấu lượt chạy hoàn tất, dù nghiệp vụ thất bại. Nên sử dụng ngoại lệ/exit code phù hợp và kiểm tra hai lớp kết quả: metadata kỹ thuật và đầu ra nghiệp vụ.

## 8. Khi tác vụ phối hợp với Spring Batch

Spring Cloud Task phù hợp với các tiến trình hữu hạn nói chung; Spring Batch bổ sung mô hình `Job`, `Step`, checkpoint và restart cho xử lý dữ liệu theo lô. Khi một ứng dụng dùng cả hai:

- Giữ cấu hình `TaskRepository` và `JobRepository` rõ ràng; xác định schema, kết nối và migration cho từng loại metadata.
- Phân biệt **Task parameters** (đối số khởi chạy) với **JobParameters** của Batch; ánh xạ tham số nghiệp vụ một cách tường minh vào job.
- Theo dõi cả `TASK_EXECUTION` và metadata `BATCH_JOB_EXECUTION`. Liên kết Task–Batch không có nghĩa mọi Task đều chạy một Batch Job.
- Kiểm tra chính sách thất bại của tiến trình khi Batch Job thất bại; cấu hình ứng dụng phải bảo đảm scheduler nhận được trạng thái lỗi phù hợp, không chỉ dựa vào log.

Nếu tích hợp Batch có tự động chạy Job khi khởi động, cần xác minh cơ chế auto-start của đúng phiên bản Spring Boot/Batch đang dùng để tránh khởi chạy Job hai lần (vừa tự động, vừa do runner gọi).

## 9. Bảo mật và vận hành theo môi trường

| Rủi ro | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Chạy sai profile | Task test ghi vào database production, hoặc kết nối sai endpoint. | Chọn profile ở tầng triển khai; xác nhận datasource và tên môi trường khi bắt đầu chạy mà không ghi lộ bí mật. |
| Thiếu bảng Task | Khởi động báo không tìm thấy bảng hoặc sequence metadata. | Chạy migration tương thích trước Job; kiểm tra schema và quyền truy cập. |
| Bí mật bị đưa vào Git/log | Mật khẩu xuất hiện trong YAML, command line hoặc stack trace. | Tham chiếu secret store/biến môi trường; giới hạn quyền xem và che dữ liệu nhạy cảm. |
| Chạy lặp không kiểm soát | Nhiều Job ghi trùng dữ liệu cho cùng ngày. | Dùng cơ chế chống chạy trùng và thiết kế idempotent. |
| Task không kết thúc | Pod/tiến trình tồn tại dù công việc đã xong. | Kiểm tra thread nền, web server, connection và tài nguyên chưa đóng; thiết lập deadline. |
| Không thấy lần chạy thất bại trong DB | Database mất kết nối trước khi metadata được ghi. | Kết hợp log, mã thoát tiến trình và trạng thái scheduler. |

Đối với container, ảnh triển khai nên bất biến; cấu hình được cấp lúc chạy. Đặt giới hạn CPU/bộ nhớ, chính sách retry và số lần chạy đồng thời phù hợp. Nếu dùng Kubernetes CronJob, cần quan tâm `concurrencyPolicy`, `backoffLimit`, `restartPolicy` và `activeDeadlineSeconds`. Một lần retry thường tạo lần thực thi mới, vì vậy logic nghiệp vụ phải an toàn khi chạy lại.

Các bản ghi metadata và log cần chính sách lưu giữ/thu dọn dữ liệu, vì lịch chạy hàng ngày có thể tạo nhiều `TaskExecution`. Không ghi dữ liệu nhạy cảm hoặc payload lớn vào error message/parameter metadata. Log nên có tên Task, ngày nghiệp vụ, correlation ID, trạng thái, thời gian chạy và số lượng bản ghi xử lý khi phù hợp; không cần ghi thông tin xác thực.

## 10. Bài thực hành đề xuất

**Tình huống:** Cần chạy `daily-order-export` mỗi ngày lúc 02:00, đồng thời cho phép chạy lại thủ công một ngày bất kỳ.

1. Tạo cấu trúc dự án như mục 2 với một runner nhận `--businessDate=yyyy-MM-dd`. Chuyển thao tác xuất sang service riêng.
2. Viết ba cấu hình `local`, `test`, `prod`; để local/test dùng kho metadata cô lập và production nhận kết nối từ biến môi trường.
3. Chạy local với một ngày hợp lệ và với giá trị không hợp lệ. Quan sát log, mã thoát và việc runner báo lỗi.
4. Chuẩn bị migration metadata cho cơ sở dữ liệu production; kiểm tra rằng application chỉ chạy khi schema đã sẵn sàng.
5. Mô phỏng việc chạy lại cùng `businessDate` hai lần và xác minh không tạo dữ liệu xuất trùng.
6. Cấu hình lịch chạy ở scheduler bên ngoài; thử tình huống hai lượt chạy chồng nhau và kiểm tra chính sách concurrency.
7. Đối chiếu số liệu nghiệp vụ với bản ghi `TASK_EXECUTION` và trạng thái Job ở hệ điều phối.

**Tiêu chí hoàn thành:** Một JAR hoạt động với nhiều profile; không chứa mật khẩu hard-code; mỗi lần chạy có tham số tường minh; lượt lỗi có tín hiệu thất bại; lịch sử Task được lưu trong kho metadata bền vững ở môi trường được triển khai; và việc chạy lại không làm sai kết quả nghiệp vụ.

## Ghi nhớ

- Tổ chức dự án theo trách nhiệm giúp thay đổi hạ tầng và lịch chạy mà không viết lại logic tác vụ.
- Spring Profiles giữ một artifact cho nhiều môi trường; biến môi trường/secret store cấp dữ liệu nhạy cảm tại thời điểm triển khai.
- `TaskRepository` phụ thuộc vào database và schema metadata đúng phiên bản; không nên để mỗi tiến trình production tự cạnh tranh tạo bảng.
- Đối với Spring Cloud Task, **hoàn thành một lượt chạy, ghi nhận trạng thái và thoát tiến trình** là một phần của thiết kế ứng dụng, không chỉ là cách chạy thử.
