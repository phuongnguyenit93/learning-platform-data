# Kiểu dữ liệu Map<String, Object> và tính tương thích đầu vào đầu ra

Trong chương **Job một bước** của module **SPRING_CLOUD_TASK**, chúng ta tìm hiểu hợp đồng dữ liệu khi một ứng dụng Spring Cloud Task chạy **Spring Batch Job có một Step**. Với **Single Step Batch Job Starter** được mô tả trong tài liệu Spring Cloud Task, mỗi bản ghi (item) đi qua bước xử lý có kiểu `Map<String, Object>`. Điều này cho phép kết nối các nguồn như CSV, JDBC, hàng đợi hoặc Kafka với các đích ghi dữ liệu mà không nhất thiết phải định nghĩa Java class riêng cho từng cấu trúc bản ghi.

Tuy nhiên, dùng `Map<String, Object>` **không có nghĩa mọi đầu vào/đầu ra tự tương thích**. Java chỉ kiểm tra được phần kiểu tổng quát; mỗi reader, processor và writer vẫn phải thống nhất **tên khóa, kiểu giá trị, giá trị bắt buộc, cách biểu diễn số/ngày và ý nghĩa nghiệp vụ**. Một bản ghi có thể đi qua bước kiểm tra generic nhưng hỏng lúc runtime vì writer cần `BigDecimal` trong khi reader cung cấp `String`.

Bài này tập trung vào tính tương thích tại ranh giới **`ItemReader<Map<String, Object>>` → `ItemProcessor<Map<String, Object>, Map<String, Object>>` → `ItemWriter<Map<String, Object>>`**, đồng thời phân biệt dữ liệu item với tham số Job, `ExecutionContext` và metadata trong `TaskRepository`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Single Step Batch Job Starter sử dụng `Map<String, Object>` và nó đại diện cho **một item**, không phải toàn bộ job.
- Ghép đúng các generic của `ItemReader`, `ItemProcessor` và `ItemWriter` trong một Step.
- Phân biệt tính tương thích kiểu ở **compile time** với tương thích schema và giá trị ở **runtime**.
- Chuẩn hóa các giá trị đến từ CSV, JDBC, JSON thành một hợp đồng đầu ra nhất quán.
- Viết một `ItemProcessor<Map<String, Object>, Map<String, Object>>` có kiểm tra dữ liệu, không cast mù hoặc sửa Map đầu vào tùy tiện.
- Tạo ví dụ Spring Batch một Step chạy trong ứng dụng Spring Cloud Task, hiểu sự khác nhau giữa cấu hình starter và cấu hình Job/Step thủ công.
- Xác định cách quản lý phiên bản schema, xử lý lỗi, kiểm thử chạy lại, ghi kết quả và theo dõi qua Spring Batch/Task.

## 2. Map<String, Object> là gì trong Single Step Batch Job Starter?

Một `Map<String, Object>` là cấu trúc ánh xạ giữa **khóa kiểu String** và **giá trị kiểu Object**:

~~~java
Map<String, Object> item = new LinkedHashMap<>();
item.put("orderId", "ORD-1001");                // String
item.put("quantity", 2);                       // Integer
item.put("unitPrice", new BigDecimal("19.90")); // BigDecimal
~~~

Ở đây `item` tương ứng **một đơn hàng** trong luồng đọc dữ liệu. Một Step có thể xử lý hàng nghìn item; nó không chứa cả danh sách đơn hàng trong một Map.

| Thành phần kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Map` | Tập hợp các cặp khóa–giá trị | Một dòng CSV được chuyển thành item |
| `String` | Kiểu của tên trường | `"orderId"`, `"quantity"` |
| `Object` | Kiểu khai báo chung cho giá trị | `String`, `Integer`, `BigDecimal`, `LocalDate` |
| `Map<String, Object>` | Kiểu của **một item** trong Step | `{"orderId": "ORD-1001", "quantity": 2}` |

Tài liệu Spring Cloud Task, phần **Single Step Batch Job Starter**, mô tả Job một Step với đầu vào/đầu ra là các item kiểu `Map<String, Object>`. Starter hỗ trợ cấu hình reader/writer và sẽ nhận một processor đúng generic nếu có trong `ApplicationContext`.

Điều quan trọng là **quy ước Map này thuộc về Single Step Batch Job Starter**, không phải quy định bắt buộc của mọi ứng dụng Spring Cloud Task hay mọi Spring Batch Job. Khi tự xây dựng Step bằng Spring Batch, bạn hoàn toàn có thể chọn `Order`, `PaymentRecord` hoặc `Map<String, Object>` làm kiểu item.

## 3. Đường đi của một item trong Job một bước

Một Step xử lý theo chunk thường có ba thành phần:

~~~mermaid
flowchart LR
    A["CSV / JDBC / JSON"] --> B["ItemReader<Map<String, Object>>"]
    B --> C["ItemProcessor<Map<String, Object>, Map<String, Object>>"]
    C --> D["ItemWriter<Map<String, Object>>"]
    D --> E["Database / File / Message broker"]
    C -. "Có thể bỏ qua processor" .-> D
    F["JobRepository / StepExecution"] -. "Quản lý trạng thái Batch" .-> C
    G["TaskRepository / TaskExecution"] -. "Theo dõi ứng dụng hữu hạn" .-> C
~~~

- **Reader** lấy từng item và trả về một `Map`. Trong Spring Batch, trả `null` từ `ItemReader.read()` là tín hiệu **hết dữ liệu**.
- **Processor** nhận một item, kiểm tra/biến đổi và trả một item cùng hoặc khác kiểu. Trả `null` từ `ItemProcessor.process()` có nghĩa **lọc bỏ item đó**, không chuyển sang writer.
- **Writer** nhận **một chunk gồm nhiều item** để ghi ra đích. Với Spring Batch 5, chữ ký điển hình của writer là `write(Chunk<? extends T>)`, không phải nhận một Map đơn lẻ.

Nếu bỏ processor, writer sẽ nhận item từ reader. Vì vậy, với reader trả giá trị thô từ CSV, writer phải xử lý được kiểu thô đó hoặc cần bổ sung processor chuẩn hóa.

### Ba loại dữ liệu không nên nhầm với item Map

| Loại dữ liệu | Mục đích | Có phải Map item đang xử lý không? |
| --- | --- | --- |
| `Map<String, Object>` của reader/processor/writer | Một bản ghi nghiệp vụ được truyền qua Step | **Có** |
| `JobParameters` | Các tham số định danh và điều khiển một `JobInstance`/`JobExecution` | **Không** |
| `ExecutionContext` | Trạng thái checkpoint được Spring Batch lưu để hỗ trợ restart | **Không**, dù bên trong có cấu trúc gần với Map |
| `TaskExecution` trong Spring Cloud Task | Metadata vòng đời ứng dụng, thời gian, exit code | **Không** |

Đặc biệt, `ExecutionContext` là cấu trúc key/value dùng cho trạng thái của `JobExecution` hoặc `StepExecution`. Nó có cơ chế persistence/serialization riêng; không nên nhét toàn bộ item Map hoặc danh sách hàng nghìn bản ghi vào đó. Giá trị không transient được lưu phải tương thích serializer của repository.

## 4. Tương thích generic ở compile time

Một chuỗi xử lý giữ nguyên kiểu Map có khai báo:

~~~java
ItemReader<Map<String, Object>> reader;
ItemProcessor<Map<String, Object>, Map<String, Object>> processor;
ItemWriter<Map<String, Object>> writer;
~~~

Sự tương thích này có hai chiều:

1. **Output của reader** phải là **input của processor**.
2. **Output của processor** phải là **input của writer**.

Nếu không có processor, **output của reader** phải phù hợp với **input của writer**.

### 4.1. Những khai báo phù hợp

~~~java
ItemReader<Map<String, Object>> reader = /* bean đọc dữ liệu */;
ItemProcessor<Map<String, Object>, Map<String, Object>> processor =
        item -> new LinkedHashMap<>(item);
ItemWriter<Map<String, Object>> writer = /* bean ghi dữ liệu */;
~~~

Các biến `reader`, `processor` và `writer` ở đây là minh họa chữ ký; phần khởi tạo cụ thể sẽ được cung cấp trong ví dụ đầy đủ phía sau.

### 4.2. Những khai báo dễ gây lỗi

~~~java
// Không thay thế trực tiếp cho ItemReader<Map<String, Object>>:
ItemReader<Map<String, String>> textReader;

// Processor đổi kiểu output sang DTO trong khi writer vẫn đòi Map:
ItemProcessor<Map<String, Object>, OrderDto> dtoProcessor;
ItemWriter<Map<String, Object>> mapWriter;
~~~

Dù `String` kế thừa `Object`, **`Map<String, String>` không phải subtype của `Map<String, Object>`**. Generic Java là *invariant*. Nếu được phép gán tự do, caller có thể thêm một `BigDecimal` vào Map mà bên tạo dữ liệu tưởng chỉ chứa String.

Tương tự, khi processor trả `OrderDto`, writer phải nhận `OrderDto` (nếu tự xây Step) hoặc có adapter chuyển DTO về Map trước điểm ghi trong starter yêu cầu Map.

| Reader output | Processor input → output | Writer input | Kết luận |
| --- | --- | --- | --- |
| `Map<String,Object>` | `Map<String,Object> → Map<String,Object>` | `Map<String,Object>` | Phù hợp contract của starter |
| `Map<String,Object>` | Không có | `Map<String,Object>` | Phù hợp nếu các trường writer cần đã có |
| `Map<String,String>` | `Map<String,Object> → Map<String,Object>` | `Map<String,Object>` | Không khớp generic trực tiếp |
| `Map<String,Object>` | `Map<String,Object> → OrderDto` | `Map<String,Object>` | Không tương thích đầu ra processor |
| `OrderDto` | `OrderDto → OrderSummary` | `OrderSummary` | Hợp lệ trong Step tự cấu hình theo kiểu DTO; không theo contract Map của starter |

Không dùng raw type `ItemReader`, ép kiểu `(ItemReader)` hay `@SuppressWarnings("unchecked")` chỉ để che mismatch. Kiểu có thể qua biên dịch nhưng gây `ClassCastException` hoặc lỗi writer ở runtime.

## 5. Tương thích runtime: cùng Map vẫn có thể sai

Java chỉ biết giá trị trong Map là `Object`. Nó không tự kiểm tra rằng mỗi Map đều có đúng khóa, kiểu giá trị và ràng buộc nghiệp vụ mà writer cần.

Xét ba item:

~~~java
Map<String, Object> a = Map.of(
        "orderId", "ORD-1001",
        "quantity", "2",
        "unitPrice", "19.90");

Map<String, Object> b = Map.of(
        "orderId", "ORD-1002",
        "quantity", 2,
        "unitPrice", new BigDecimal("19.90"));

Map<String, Object> c = new LinkedHashMap<>();
c.put("ORDER_ID", "ORD-1003");
c.put("quantity", null);
~~~

`Map.of` không chấp nhận khóa hay giá trị `null`, vì vậy tình huống `c` dùng `LinkedHashMap` để minh họa một bản ghi có giá trị `null` và khác tên khóa.

Cả `a` và `b` đều là `Map<String, Object>`, nhưng kiểu runtime khác. Item `c` còn đặt tên khóa `ORDER_ID` khác `orderId`. Writer lấy `(BigDecimal) item.get("unitPrice")` sẽ lỗi với `a`; writer lấy `item.get("orderId")` sẽ nhận `null` với `c`.

**Do đó, phải kiểm tra hai hợp đồng:**

- **Hợp đồng Java:** các generic liên kết Reader → Processor → Writer.
- **Hợp đồng dữ liệu:** khóa nào tồn tại, có bắt buộc không, kiểu runtime nào, đơn vị và giá trị hợp lệ ra sao.

### 5.1. Bảng nguồn dữ liệu điển hình

| Nguồn | Kiểu giá trị có thể gặp | Rủi ro |
| --- | --- | --- |
| CSV | Thường là `String` sau khi token hóa | `"2"` chưa phải `Integer`; dấu thập phân/định dạng ngày |
| JDBC | `Integer`, `Long`, `BigDecimal`, `Timestamp`, `Date` hoặc kiểu driver trả về | Loại SQL và JDBC driver quyết định kiểu Java |
| JSON từ AMQP/Kafka | `Integer`, `Long`, `Double`, `String`, `LinkedHashMap`... | Khác cấu hình converter, giá trị số mất độ chính xác nếu thành floating-point |
| Map do mã ứng dụng tạo | Bất kỳ `Object` nào | Lỗi do thiếu key, đặt sai tên hoặc chứa object chưa hỗ trợ |

Dù cùng định dạng JSON, hai producer vẫn có thể gửi `"quantity": "2"` và `"quantity": 2`. Nếu writer không có chuẩn hóa, lỗi sẽ xuất hiện muộn sau khi đã đọc nhiều item.

### 5.2. Thiết lập schema logic cho một item

Một hợp đồng rõ ràng có thể quy định:

| Khóa | Input thô | Output sau processor | Bắt buộc | Quy tắc |
| --- | --- | --- | --- | --- |
| `orderId` | `String` | `String` | Có | Không rỗng, là mã duy nhất trong phạm vi phù hợp |
| `quantity` | `String` hoặc số nguyên được chuẩn hóa | `Integer` | Có | Lớn hơn 0 |
| `unitPrice` | `String`/số thập phân | `BigDecimal` | Có | Không âm, đơn vị tiền tệ xác định |
| `lineTotal` | Không nhất thiết có | `BigDecimal` | Có ở writer | `quantity × unitPrice` |
| `schemaVersion` | Có thể có | `Integer` | Khuyến nghị | Giúp phát hiện phiên bản dữ liệu |

Ở bước đọc, trường `lineTotal` có thể chưa tồn tại. Processor có trách nhiệm bổ sung nó trước khi writer sử dụng. Nếu writer xuất CSV, có thể chuyển `BigDecimal` thành chuỗi theo format đã quy định ở **biên ghi**, không đưa `Double` vào tính tiền.

## 6. Cơ chế Single Step Batch Job Starter sử dụng Map

Tài liệu chính thức Spring Cloud Task mô tả dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-single-step-batch-job</artifactId>
    <!-- Chọn phiên bản thực sự tương thích với Spring Boot/Batch của dự án -->
</dependency>
~~~

Tài liệu tham khảo có ví dụ starter với phiên bản `2.3.0`. Đây là **ví dụ theo dòng phát hành được tài liệu mô tả**, không phải khuyến nghị sao chép nguyên version đó vào dự án Spring Boot hiện đại. Kiểm tra artifact và release train tương thích trước khi dùng.

Starter cung cấp các property để định nghĩa Job một Step theo tài liệu:

~~~yaml
spring:
  batch:
    job:
      jobName: importOrders
      stepName: normalizeOrders
      chunkSize: 100
~~~

Ba property trên thuộc **Single Step Batch Job Starter** được mô tả; đừng mặc định chúng tạo một Step trong ứng dụng chỉ có `spring-boot-starter-batch` mà không có starter liên quan.

Khi tự cung cấp `ItemProcessor<Map<String, Object>, Map<String, Object>>` dưới dạng bean và các bean reader/writer phù hợp, starter có thể nối processor này vào Step theo cơ chế tự cấu hình của nó. Những reader/writer tích hợp được tài liệu nêu gồm các lựa chọn cho CSV/flat file, JDBC và các hệ thống nhắn tin.

Ví dụ khai báo processor phù hợp về generic:

~~~java
@Bean
ItemProcessor<Map<String, Object>, Map<String, Object>> normalizeOrders() {
    return item -> {
        Map<String, Object> result = new LinkedHashMap<>(item);
        // Kiểm tra và chuẩn hóa các trường trước khi xuất.
        return result;
    };
}
~~~

**Lưu ý về phiên bản:** các property, điều kiện tạo bean, hỗ trợ reader/writer và kiểu `ItemWriter` cụ thể có thể thay đổi giữa các bản Spring Cloud Task/Spring Batch. Nên dùng tài liệu đúng version của starter. Nếu cần kiểm soát kiểu rõ ràng và tránh phụ thuộc vào auto-configuration riêng của starter, có thể **tự khai báo Job/Step** với Spring Batch, như ví dụ tiếp theo.

## 7. Ví dụ tự chứa: Job một Step dùng Map<String, Object>

Ví dụ này dùng **Spring Batch 5.x** với Spring Boot 3.x và Spring Cloud Task tương thích. Ta tự tạo Job/Step để nhìn rõ generic, không phụ thuộc vào việc phiên bản Single Step Batch Job Starter có cung cấp tính năng auto-configuration cụ thể nào.

Ứng dụng xử lý hai đơn hàng mẫu. Reader trả Map gồm số lượng/đơn giá dưới dạng **chuỗi**; processor kiểm tra và chuẩn hóa thành `Integer`/`BigDecimal`; writer in dữ liệu đã chuẩn hóa. Writer console chỉ phục vụ học tập. Với tác vụ production, hãy thay bằng writer lưu database/file thích hợp.

### 7.1. Dependency

Trong dự án Maven đã có Spring Boot parent/BOM và Spring Cloud BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Dự án cũng cần `spring-boot-maven-plugin` để tạo JAR thực thi. Với Spring Boot 3.x + Spring Batch 5.x, các package và builder phía dưới phù hợp với API được tài liệu mô tả. Với Spring Batch 6 hoặc phiên bản khác, hãy kiểm tra thay đổi package/builder trước khi áp dụng.

### 7.2. Mã Java: Reader → Processor → Writer

Tạo `src/main/java/com/example/task/MapSingleStepApplication.java`:

~~~java
package com.example.task;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
@EnableTask
public class MapSingleStepApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(MapSingleStepApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    Job orderJob(JobRepository jobRepository, Step orderStep) {
        return new JobBuilder("orderJob", jobRepository)
                .start(orderStep)
                .build();
    }

    @Bean
    Step orderStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Map<String, Object>> orderReader,
            ItemProcessor<Map<String, Object>,
                          Map<String, Object>> orderProcessor,
            ItemWriter<Map<String, Object>> orderWriter) {

        return new StepBuilder("orderStep", jobRepository)
                .<Map<String, Object>, Map<String, Object>>
                        chunk(2, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    ItemReader<Map<String, Object>> orderReader() {
        Map<String, Object> first = new LinkedHashMap<>();
        first.put("orderId", "ORD-1001");
        first.put("quantity", "2");
        first.put("unitPrice", "19.90");

        Map<String, Object> second = new LinkedHashMap<>();
        second.put("orderId", "ORD-1002");
        second.put("quantity", "3");
        second.put("unitPrice", "5.25");

        return new ListItemReader<>(List.of(first, second));
    }

    @Bean
    ItemProcessor<Map<String, Object>, Map<String, Object>>
            orderProcessor() {
        return input -> {
            String orderId = requiredText(input, "orderId");

            int quantity;
            BigDecimal unitPrice;
            try {
                quantity = Integer.parseInt(
                        requiredText(input, "quantity"));
                unitPrice = new BigDecimal(
                        requiredText(input, "unitPrice"));
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "quantity hoặc unitPrice không hợp lệ", ex);
            }

            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "quantity phải > 0 và unitPrice không âm");
            }

            Map<String, Object> output = new LinkedHashMap<>();
            output.put("orderId", orderId);
            output.put("quantity", quantity);
            output.put("unitPrice", unitPrice);
            output.put("lineTotal",
                    unitPrice.multiply(BigDecimal.valueOf(quantity)));
            return output;
        };
    }

    @Bean
    ItemWriter<Map<String, Object>> orderWriter() {
        return chunk -> {
            for (Map<String, Object> item : chunk) {
                String orderId = (String) item.get("orderId");
                BigDecimal lineTotal =
                        (BigDecimal) item.get("lineTotal");

                System.out.println(
                        orderId + " => " + lineTotal.toPlainString());
            }
        };
    }

    private static String requiredText(
            Map<String, Object> input, String key) {
        Object value = input.get(key);
        if (!(value instanceof String text)
                || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu hoặc sai kiểu trường: " + key);
        }
        return text.trim();
    }
}
~~~

Trong ví dụ, `orderProcessor` yêu cầu đầu vào từ reader có ba trường `String`. Reader cố tình cung cấp dữ liệu theo đúng contract này. Nếu thay bằng `JdbcCursorItemReader` trả `BigDecimal` cho `unitPrice`, bạn **phải sửa quy tắc chuẩn hóa**; sử dụng `toString()` cho mọi loại dữ liệu một cách tùy tiện có thể che giấu lỗi schema.

### 7.3. Config ứng dụng

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: map-single-step
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:mem:mapstep
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true
  cloud:
    task:
      name: map-single-step
      initialize-enabled: true
      batch:
        fail-on-job-failure: true
~~~

Cấu hình này minh họa khởi tạo cả hạ tầng metadata Batch và Spring Cloud Task trong H2 **bộ nhớ**. Các bảng/lịch sử không tồn tại qua lần JVM mới; production cần database lưu bền vững và migration đúng version.

Với ứng dụng Spring Boot có một Job và Batch auto-configuration đang hoạt động, Boot có thể khởi chạy Job khi ứng dụng khởi động. Ví dụ đã tự định nghĩa `Job`/`Step`; **không thêm song song Single Step Batch Job Starter tự sinh một Job thứ hai** khi chưa kiểm soát cách chọn Job.

Property `spring.cloud.task.batch.fail-on-job-failure=true` giúp phản ánh job Batch thất bại vào mã thoát Task theo khả năng của phiên bản Spring Cloud Task đang dùng. Cần chạy thử tình huống thất bại và xác minh exit code thật; không suy luận thành công chỉ vì runner/Job đã được gọi.

### 7.4. Chạy và quan sát

~~~bash
./mvnw clean package
java -jar target/map-single-step-0.0.1-SNAPSHOT.jar
~~~

Trên Windows dùng `mvnw.cmd clean package` và thay đường dẫn JAR bằng artifact thực tế.

Kết quả nghiệp vụ mong đợi trong log:

~~~text
ORD-1001 => 39.80
ORD-1002 => 15.75
~~~

Đây là output từ writer console, **chưa phải dữ liệu nghiệp vụ được lưu bền vững**. Chúng ta dùng nó để quan sát kiểu: `unitPrice`/`lineTotal` là `BigDecimal` sau processor; writer không cần parse lại chuỗi.

### 7.5. Vì sao processor trả Map mới?

`new LinkedHashMap<>()` trong processor giúp tránh vô tình thay đổi Map do reader tái sử dụng hoặc chia sẻ. Trong hệ thống có nhiều callback, cache hay ghi song song, đột biến Map đầu vào có thể tạo lỗi khó chẩn đoán.

Output Map còn giúp xác định **hợp đồng đích**: writer chỉ nhận item đã chuẩn hóa. Với ứng dụng lớn, nên định nghĩa class DTO/record có kiểu mạnh tại biên nghiệp vụ nếu schema đã ổn định; dùng Map khi bạn thật sự cần sự linh hoạt.

## 8. Kết nối với FlatFileItemReader và FlatFileItemWriter

Tài liệu Single Step Batch Job Starter nêu rằng `FlatFileItemReader` có thể sử dụng thuộc tính `names` để đặt tên các khóa trong item Map. Ví dụ CSV:

~~~csv
orderId,quantity,unitPrice
ORD-1001,2,19.90
ORD-1002,3,5.25
~~~

Theo cấu hình mà starter hỗ trợ, có thể chỉ định:

~~~yaml
spring:
  batch:
    job:
      flatfileitemreader:
        names: orderId,quantity,unitPrice
      flatfileitemwriter:
        names: orderId,quantity,unitPrice,lineTotal
~~~

Đây là **trích phần khai báo tên trường**, chưa phải file YAML đầy đủ để chạy. Cần bổ sung `resource`, cấu hình delimited, reader/writer thích hợp, Job/Step và xác minh tên property/điều kiện autoconfiguration theo version starter. Ví dụ nêu rõ ý nghĩa:

- Reader tạo các khóa `orderId`, `quantity`, `unitPrice`.
- Processor có thể tạo thêm `lineTotal`.
- Writer có thể lấy các khóa theo danh sách `names` đã cấu hình.

Nếu writer yêu cầu `lineTotal` nhưng processor chưa tạo, đầu ra thiếu trường. Nếu reader đổi `orderId` thành `order_id`, processor đang gọi `input.get("orderId")` sẽ lỗi. Đây là **lỗi hợp đồng dữ liệu**, dù generic Java vẫn là `Map<String, Object>`.

Không mặc định một `FlatFileItemReader` thuần Spring Batch sẽ trả Map: điều đó còn tùy `LineMapper` và `FieldSetMapper`. Cơ chế Map trong phần này là cách starter hoặc code mapping của bạn định nghĩa.

## 9. Tương thích với JDBC và JSON

### 9.1. JDBC RowMapper

Khi dữ liệu đến từ database, `RowMapper<Map<String, Object>>` có thể chuẩn hóa tên cột:

~~~java
RowMapper<Map<String, Object>> mapper = (rs, rowNum) -> {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("orderId", rs.getString("order_id"));
    item.put("quantity", rs.getInt("quantity"));
    item.put("unitPrice", rs.getBigDecimal("unit_price"));
    return item;
};
~~~

Đoạn mapper trên trả `Integer`/`BigDecimal`, **khác** đầu vào `String` của processor ở mục 7. Nếu muốn dùng lại logic, nên có một trong hai cách:

1. **Định nghĩa contract reader chuẩn**: mọi reader phải trả `quantity: Integer`, `unitPrice: BigDecimal`; sửa reader CSV để chuyển kiểu sớm.
2. **Định nghĩa processor chấp nhận các kiểu được phép**: kiểm tra `instanceof` và chuyển rõ ràng, từ chối những kiểu bất ngờ.

Cách thứ nhất thường dễ kiểm thử hơn khi có nhiều nguồn; cách thứ hai hữu ích ở vùng tích hợp nhưng phải quy định các kiểu cho phép. Tránh ép `(BigDecimal) value` khi loại thực tế có thể là `String`.

`ResultSet.getInt(...)` trả `0` cho SQL `NULL`, nên ở schema cho phép null cần kiểm tra `rs.wasNull()` hoặc dùng getter đối tượng thích hợp. Không được nhầm null với số 0 hợp lệ.

### 9.2. JSON từ hàng đợi

Ví dụ payload:

~~~json
{
  "orderId": "ORD-1001",
  "quantity": 2,
  "unitPrice": "19.90"
}
~~~

Một JSON converter có thể biểu diễn `quantity` là `Integer`, `unitPrice` là `String` và object lồng nhau dưới dạng `Map`. Khi nhận JSON từ hệ thống khác, cần xác thực:

- Root là object, không phải array/string.
- Các trường bắt buộc có mặt và đúng kiểu.
- Phiên bản schema có hỗ trợ.
- Giá tiền sử dụng số thập phân chính xác; không chuyển `Double` thành `BigDecimal` một cách cẩu thả.
- Có giới hạn kích thước và không đưa dữ liệu nhạy cảm vào log.

Khi hệ thống đọc và ghi thông điệp qua Kafka/AMQP, tương thích còn phụ thuộc **serializer/deserializer, message converter và định dạng của producer/consumer**, không chỉ `ItemReader<Map<String, Object>>`.

## 10. Xử lý thiếu khóa, null, sai kiểu và dữ liệu bẩn

Một bộ quy tắc phổ biến:

| Tình huống | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Thiếu khóa bắt buộc | Không có `orderId` | Báo lỗi có mã, không phát item hỏng sang writer |
| Khóa có `null` | `quantity=null` | Từ chối hoặc dùng default **được nghiệp vụ chấp nhận** |
| Sai kiểu | `quantity=["2"]` | Không cast/`toString()` tùy tiện; báo lỗi schema |
| Chuỗi trắng | `orderId="  "` | Từ chối sau khi trim |
| Số ngoài phạm vi | `quantity=-1` | Từ chối |
| Đơn vị không thống nhất | `price` vừa là VND vừa là USD | Thêm `currency` và chuẩn hóa; không cộng trộn |
| Sai tên trường | `order_id` thay `orderId` | Mapping tại reader/adapter |
| Trường mở rộng | `sourceSystem` mới | Có thể cho phép nếu writer bỏ qua và schema version chấp nhận |
| Cùng khóa nhưng nội dung khác | `orderId` trùng với giá tiền khác | Áp dụng chính sách conflict/versioning, không tự overwrite |

Khi item sai, quyết định **fail Step**, **skip** hay **lọc item** phải dựa vào yêu cầu dữ liệu:

- `throw exception` khi mất trường bắt buộc hoặc dữ liệu vi phạm bất biến.
- `ItemProcessor.process(...)` trả `null` khi chủ động **lọc item** theo quy tắc rõ ràng, chẳng hạn bỏ các bản ghi đã đánh dấu hủy.
- Spring Batch có cơ chế skip/retry nếu cấu hình fault tolerance; không phải mọi exception tự được skip.
- Cần báo cáo số lượng read/process/write/skip để không vô tình đánh mất dữ liệu khi file đầu vào có vấn đề.

Không được sử dụng cách “bắt mọi exception rồi trả `null`” mà không có thống kê. Nó biến lỗi chuyển đổi dữ liệu thành mất bản ghi âm thầm.

## 11. Thay đổi schema đầu vào/đầu ra theo thời gian

Map linh hoạt nhưng thiếu ràng buộc kiểu ở compile time, vì vậy cần quản lý **hợp đồng dữ liệu như một API**.

Ví dụ hai phiên bản:

| Trường | v1 | v2 | Đánh giá |
| --- | --- | --- | --- |
| `orderId` | Bắt buộc `String` | Giữ nguyên | Tương thích |
| `quantity` | Số nguyên dương | Giữ nguyên | Tương thích |
| `unitPrice` | `String` dạng thập phân | `BigDecimal` | Có thể phá vỡ consumer dùng cast kiểu cũ |
| `lineTotal` | Không có | Bổ sung sau processor | Tương thích nếu writer cũ bỏ qua trường mới |
| `currency` | Không có | Thêm trường bắt buộc | Phá vỡ producer cũ nếu không có default/migration |
| `orderId` đổi thành `order_id` | Tên cũ | Tên mới | Phá vỡ consumer cũ |

Một quy trình nâng version nên gồm:

1. Định nghĩa schema v1/v2 bằng tài liệu rõ khóa, kiểu, nullability và ngữ nghĩa.
2. Bổ sung adapter chuyển v1 → v2 ở biên đọc, hoặc hỗ trợ song song hai version trong thời gian chuyển đổi.
3. Dùng `schemaVersion` và validate trước khi xử lý.
4. Kiểm tra reader từ mọi nguồn và writer của mọi đích trên bộ mẫu dữ liệu hai version.
5. Chỉ gỡ hỗ trợ v1 khi producer/consumer đã được nâng cấp theo kế hoạch.

Đừng giả định `Map<String, Object>` là định dạng lưu trữ ổn định. Khi xuất CSV, JSON, JDBC, thứ tự trường, kiểu SQL/JSON, encoding và serialize đều cần quy định riêng.

## 12. Restart và bảo toàn tính nhất quán

Trong một tác vụ hữu hạn, Spring Cloud Task có thể lưu `TaskExecution` cho mỗi lần khởi chạy; Spring Batch lưu `JobExecution`, `StepExecution` và `ExecutionContext` để hỗ trợ trạng thái/khởi động lại. Chúng là **hai lớp metadata khác nhau**.

Nếu writer đã ghi một số item nhưng tiến trình chết, kết quả phụ thuộc:

- Chunk đã commit hay chưa.
- Writer và repository Batch có tham gia transaction như thế nào.
- Đích ghi là database, file, broker hay API bên ngoài.
- Reader có hỗ trợ lưu trạng thái restart hay không.
- Writer có idempotent khi nhận lại cùng item hay không.

| Đích ghi | Rủi ro sau crash | Biện pháp |
| --- | --- | --- |
| JDBC cùng transaction | Một chunk có thể rollback; các chunk trước đã commit | Transaction đúng, khóa unique, restart có kiểm soát |
| CSV/file | File có thể ghi dở hoặc bị ghi đè | File tạm, checkpoint phù hợp, atomic publish khi có thể |
| Message broker | Có thể phát lại bản tin sau crash | Message ID và consumer idempotent |
| API bên ngoài | Timeout không chứng minh API chưa xử lý | Idempotency key và đối soát trạng thái |
| Console | Output có thể in lặp | Chỉ dùng để minh họa hoặc ghi log |

Dùng Map không tự tạo khả năng restart. Metadata Batch có thể lưu trạng thái của reader/writer, nhưng **item Map không tự động được ghi toàn bộ vào `ExecutionContext`**. Mỗi component cần khai báo cơ chế save state phù hợp.

Nếu phát sinh lỗi trong reader/processor/writer, `BatchStatus` có thể là `FAILED`. Để scheduler quan sát đúng mã thoát Spring Cloud Task, cần cấu hình ánh xạ Batch failure → Task exit code phù hợp với version, chẳng hạn `spring.cloud.task.batch.fail-on-job-failure=true` khi được hỗ trợ. Luôn kiểm tra mã thoát thực tế và metadata; không suy diễn từ vài dòng log.

## 13. Kiểm tra tính tương thích theo lớp

Một bộ kiểm tra có ý nghĩa nên đi qua các lớp:

### 13.1. Generic compile-time

- Reader khai báo `ItemReader<Map<String, Object>>`.
- Processor khai báo `ItemProcessor<Map<String, Object>, Map<String, Object>>`.
- Writer khai báo `ItemWriter<Map<String, Object>>`.
- Không dùng raw generic, ép kiểu tùy tiện hoặc `Map<String, String>` để lách contract.

### 13.2. Item schema runtime

Kiểm tra các item điển hình:

~~~text
VALID:    orderId="ORD-1001", quantity="2", unitPrice="19.90"
INVALID:  orderId=null,       quantity="2", unitPrice="19.90"
INVALID:  orderId="ORD-1002", quantity="-5", unitPrice="19.90"
INVALID:  orderId="ORD-1003", quantity="2", unitPrice="unknown"
~~~

Yêu cầu processor trả đúng kiểu output và thông báo lỗi rõ, không “cố gắng sửa” mọi dữ liệu bẩn bằng giá trị mặc định.

### 13.3. Đích ghi và khởi động lại

- Với writer JDBC, kiểm tra schema SQL, kiểu `NUMERIC/DECIMAL`, khóa unique và transaction.
- Với writer CSV, kiểm tra encoding, thứ tự trường, dấu thập phân, header và quoting.
- Với writer JSON, kiểm tra serializer/consumer, kiểu số và việc bỏ/giữ trường ngoài schema.
- Gây lỗi sau một chunk đã commit rồi chạy lại; xác nhận không mất hoặc nhân đôi bản ghi.
- Đối chiếu `JobExecution`/`StepExecution` với `TaskExecution` và kết quả nghiệp vụ.

## 14. Checklist khi nối Reader, Processor và Writer

- [ ] Một item tương ứng đúng một đơn vị nghiệp vụ, không nhầm với toàn bộ Job.
- [ ] Generic đầu ra reader tương thích đầu vào processor; đầu ra processor tương thích đầu vào writer.
- [ ] Hợp đồng Map quy định rõ tên khóa, kiểu giá trị, đơn vị, nullability và phạm vi giá trị.
- [ ] Reader chuẩn hóa tên trường từ CSV/JDBC/JSON vào một quy ước.
- [ ] Processor kiểm tra dữ liệu và trả Map đầu ra ổn định, không cast mù.
- [ ] Writer biết chính xác các khóa và kiểu mà nó cần; đã kiểm thử dữ liệu thiếu/trùng/khác version.
- [ ] Dùng `BigDecimal` cho phép tính tiền, với currency và quy tắc làm tròn được xác định.
- [ ] Không đưa dữ liệu nhạy cảm vào log hoặc `TaskExecution`/`ExecutionContext` tùy tiện.
- [ ] Khởi chạy lại qua lỗi được thiết kế an toàn với transaction, khóa nghiệp vụ và cơ chế retry.
- [ ] Đã kiểm tra version Spring Cloud Task, Spring Batch, starter và các thuộc tính autoconfiguration.

## 15. Bài tập và câu hỏi tự kiểm tra

**Câu hỏi 1.** Vì sao `Map<String, String>` không thể dùng trực tiếp ở vị trí yêu cầu `Map<String, Object>`, dù mọi `String` đều là `Object`?

**Câu hỏi 2.** Một reader CSV tạo `quantity="2"`, reader JDBC tạo `quantity=2`. Nếu cả hai đều là `Map<String, Object>`, vì sao writer vẫn có thể thất bại?

**Câu hỏi 3.** Khác biệt giữa `ItemProcessor.process()` trả `null` và `ItemReader.read()` trả `null` là gì?

**Câu hỏi 4.** `ExecutionContext` trong Spring Batch có dùng Map nhưng có đồng nghĩa với Map item không? Có nên lưu cả một danh sách 1 triệu item vào context?

**Câu hỏi 5.** Với Single Step Batch Job Starter, một bean `ItemProcessor<Map<String, Object>, OrderDto>` có phù hợp với writer Map tích hợp không? Nếu không, có thể sửa như thế nào?

**Bài tập A — Chuẩn hóa đa nguồn.** Sửa processor để chấp nhận `quantity` dưới dạng `String` hoặc `Integer`, `unitPrice` dưới dạng `String` hoặc `BigDecimal`. Chỉ cho phép những kiểu này; từ chối `Double` hoặc danh sách.

**Bài tập B — Versioning.** Thêm `schemaVersion` và `currency` vào item. Với dữ liệu v1 thiếu `currency`, chọn một chính sách tương thích có điều kiện; với v2 bắt buộc phải có `currency`. Giải thích vì sao không nên mặc định tất cả bản ghi dùng cùng một loại tiền.

**Bài tập C — Writer bền vững.** Thay writer console bằng writer JDBC có khóa duy nhất `order_id` trên bảng đích. Chạy Job hai lần và kiểm tra duplicate, transaction, `JobExecution` cùng `TaskExecution`.

**Bài tập D — Thay nguồn dữ liệu.** Chuyển từ `ListItemReader` sang `FlatFileItemReader` rồi sang `JdbcCursorItemReader`. Giữ nguyên hợp đồng output chuẩn hóa và thực hiện phép thử đảm bảo các writer vẫn nhận đúng kiểu.

**Bài tập E — Tương thích starter.** Nếu dự án sử dụng `spring-cloud-starter-single-step-batch-job`, xác nhận version artifact, các property `jobName`/`stepName`/`chunkSize`, generic processor và điều kiện tạo reader/writer. Đối chiếu với một Job/Step khai báo thủ công.

## 16. Ghi nhớ

- Single Step Batch Job Starter của Spring Cloud Task mô tả **item đầu vào/đầu ra dạng `Map<String, Object>`** và chỉ tự kết nối processor có generic phù hợp theo cơ chế được tài liệu quy định.
- Tương thích Java **chưa đủ**: reader, processor và writer còn phải thống nhất **tên khóa, kiểu runtime, nullability, ý nghĩa nghiệp vụ và version schema**.
- `Map<String, String>` **không phải** `Map<String, Object>`; tránh raw type và ép kiểu để lách kiểm tra.
- Khi reader trả dữ liệu thô từ CSV/JDBC/JSON, hãy chuẩn hóa ở biên hoặc processor. Writer nên chỉ nhận một contract đã kiểm tra rõ.
- Map item, `JobParameters`, `ExecutionContext` và `TaskExecution` có trách nhiệm khác nhau. Map item **không tự là trạng thái checkpoint** và cũng không phải metadata Task.
- Để chạy theo lịch hoặc yêu cầu một cách an toàn, cần lưu kết quả nghiệp vụ, kiểm soát lỗi, thiết kế idempotency/restart và đối chiếu cả Spring Batch lẫn Spring Cloud Task.

## Tài liệu tham khảo

- [Spring Cloud Task Reference — Single Step Batch Job Starter](https://docs.spring.io/spring-cloud-task/reference/batch-starter.html), mục *Defining a Job*, *ItemProcessor Configuration* và các reader/writer Map.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring.html), cách nối reader, processor và writer trong Step.
- [Spring Batch Reference — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html), `JobParameters`, `StepExecution`, `ExecutionContext` và quy tắc restart.
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html), đối chiếu khi một Step không xử lý theo chunk.
- [Spring Batch 5 API — ExecutionContext](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/ExecutionContext.html), map-backed context và yêu cầu serialization.

Khi áp dụng vào một dự án cụ thể, hãy đối chiếu phiên bản Spring Cloud Task/Single Step Starter và Spring Batch, vì ví dụ starter được tài liệu mô tả có thể thuộc dòng phát hành cũ hơn API Spring Batch mới.
