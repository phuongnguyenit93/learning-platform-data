# Đưa tham số nhóm luồng ra cấu hình ngoài và kiểm tra giá trị không hợp lệ

Trong Spring Framework, cấu hình tài nguyên cho `ThreadPoolTaskExecutor` quyết định cách ứng dụng nhận và xử lý tác vụ: số worker cơ bản, giới hạn worker, dung lượng hàng đợi, thời gian giữ worker nhàn rỗi và hành vi khi quá tải. Những giá trị này thường cần thay đổi giữa máy phát triển, môi trường kiểm thử và production. Nếu chúng bị viết cứng rải rác trong mã Java, việc tinh chỉnh dễ tạo sai lệch và khó truy vết.

Bài này hướng dẫn hai mục tiêu liên quan:

1. **Externalize configuration**: lưu giá trị ngoài phần logic tạo executor; đọc chúng qua cơ chế cấu hình của Spring thay vì thay mã nguồn mỗi lần chỉnh tài nguyên.
2. **Validate trước khi dùng**: kiểm tra kiểu, khoảng giá trị, điều kiện giữa các trường và ý nghĩa vận hành; nếu cấu hình sai, báo lỗi rõ ràng khi khởi động thay vì chạy với tham số bất hợp lý.

Phần ví dụ chính dùng **Java 17+, Spring Framework 6.x và Spring Boot 3.x**. `@ConfigurationProperties` thuộc **Spring Boot**, không phải một tính năng tự động có sẵn của mọi ứng dụng dùng Spring Framework thuần. Phần cuối có ví dụ `Environment`/`@PropertySource` cho Spring Framework không dùng Boot.

## 1. Vì sao cần đưa tham số executor ra ngoài?

Xét cấu hình viết cứng:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(64);
executor.setKeepAliveSeconds(60);
~~~

Đây là **đoạn mã minh họa**, chưa phải chương trình Spring hoàn chỉnh. Nó hoạt động, nhưng không thể đổi profile hoặc cấu hình triển khai mà không sửa cách tạo bean. Tệ hơn, nếu mỗi executor đọc giá trị riêng theo các cách khác nhau, ứng dụng khó kiểm soát tính nhất quán.

Một mô hình rõ ràng hơn:

~~~text
application.yml / file bên ngoài / biến môi trường / CLI
                         |
                         v
                Spring Environment
                         |
                         v
               Bind vào PoolProperties
                         |
                         v
                Validate kiểu + giới hạn
                         |
           +-------------+-------------+
           |                           |
         hợp lệ                    không hợp lệ
           |                           |
           v                           v
     Tạo executor                Báo lỗi khởi động
           |
           v
     @Async / TaskExecutor
~~~

**Cấu hình ngoài không đồng nghĩa với cập nhật nóng.** Trong các ví dụ dưới đây, các giá trị được đọc lúc tạo bean. Sửa file hoặc biến môi trường sau khi ứng dụng chạy **không tự động** thay đổi pool hiện tại. Muốn cập nhật động cần cơ chế reload riêng, kiểm tra lại điều kiện và hiểu tham số nào có thể thay đổi khi executor đã khởi tạo.

## 2. Nhận diện chính xác những tham số cần kiểm tra

| Thuộc tính | Ý nghĩa | Quy tắc có thể áp dụng cho ứng dụng ví dụ |
| --- | --- | --- |
| `corePoolSize` | Số worker lõi; pool thường ưu tiên tạo worker tới ngưỡng này khi nhận task | Số nguyên từ 1 đến 32 |
| `maxPoolSize` | Số worker tối đa khi cần mở rộng | Số nguyên từ 1 đến 64 **và không nhỏ hơn core** |
| `queueCapacity` | Số task chờ được chứa trước khi tính tới mở thêm worker | Số nguyên từ 0 đến 2.000 |
| `keepAliveSeconds` | Thời gian nhàn rỗi cho worker vượt core trước khi bị thu hồi | Số nguyên từ 1 đến 600 |
| `threadNamePrefix` | Tiền tố tên worker để dễ quan sát thread dump/log | Chuỗi không trống hoặc chỉ có khoảng trắng |
| `RejectedExecutionHandler` | Cách xử lý khi pool không còn nhận được task | Chọn một chính sách có chủ đích, không nên chọn tùy tiện qua chuỗi bất kỳ |

**Các ngưỡng 32, 64, 2.000 và 600 là chính sách của ví dụ, không phải giới hạn chuẩn của Spring hay JVM.** Dự án thật chọn chúng từ CPU quota, bộ nhớ, tốc độ tác vụ, độ trễ dịch vụ phụ thuộc và yêu cầu vận hành.

Có ít nhất ba lớp hợp lệ cần phân biệt:

- **Hợp lệ về kiểu:** `corePoolSize: abc` không chuyển thành số nguyên được; `queueCapacity: 999999999999999999` vượt phạm vi `int`.
- **Hợp lệ về miền và quan hệ:** `corePoolSize=0` bị cấm theo chính sách của ví dụ; `maxPoolSize < corePoolSize` mâu thuẫn; `queueCapacity < 0` không được ứng dụng này chấp nhận.
- **Hợp lý về năng lực vận hành:** `maxPoolSize=64` có thể hợp lệ theo annotation nhưng vẫn quá cao với database pool chỉ có 10 kết nối. Validation tĩnh **không thay thế thử tải và capacity planning**.

Lưu ý ở mức API: với `ThreadPoolTaskExecutor`, `queueCapacity > 0` tạo `LinkedBlockingQueue`; giá trị 0 tạo `SynchronousQueue`, nghĩa là bàn giao trực tiếp, **không giữ task trong hàng đợi**. Vì vậy việc cấm `queueCapacity=0` là một quyết định sản phẩm, không phải luật bắt buộc của Spring.

## 3. Cách làm được khuyến nghị trong Spring Boot: @ConfigurationProperties

`@ConfigurationProperties` gom các khóa có chung prefix vào một Java object có kiểu rõ ràng. Spring Boot bind dữ liệu từ `Environment` rồi, khi bean được đánh dấu `@Validated` và có Bean Validation provider, kiểm tra các ràng buộc `jakarta.validation`.

Ưu điểm so với đặt nhiều `@Value` rời rạc: cùng một chỗ mô tả các thuộc tính, dễ tái sử dụng, dễ kiểm thử lỗi cấu hình, hỗ trợ relaxed binding và metadata cho IDE.

### 3.1. Bước 1 — Khai báo application.yml

Ví dụ tệp `src/main/resources/application.yml`:

~~~yaml
app:
  executor:
    io:
      core-pool-size: ${APP_IO_CORE_POOL_SIZE:4}
      max-pool-size: ${APP_IO_MAX_POOL_SIZE:8}
      queue-capacity: ${APP_IO_QUEUE_CAPACITY:64}
      keep-alive-seconds: ${APP_IO_KEEP_ALIVE_SECONDS:60}
      thread-name-prefix: ${APP_IO_THREAD_NAME_PREFIX:io-}
~~~

Cú pháp `${ENV_NAME:default}` có nghĩa: dùng biến hoặc property tên `ENV_NAME` trong `Environment` nếu tìm thấy, nếu không dùng giá trị sau dấu `:`. Giá trị mẫu nằm trong YAML nên ứng dụng vẫn có cấu hình rõ ràng khi chạy local.

Ta đã chủ động đặt tên biến môi trường riêng, ví dụ `APP_IO_CORE_POOL_SIZE`. **Đừng nhầm các tên placeholder này với phép biến đổi tự động của relaxed binding**. Trong relaxed binding trực tiếp, tên canonical `app.executor.io.core-pool-size` được chuyển sang dạng biến môi trường bằng cách thay dấu chấm bằng gạch dưới, **loại bỏ dấu gạch nối** và viết hoa, tức `APP_EXECUTOR_IO_COREPOOLSIZE`. Với placeholder trong YAML, ta có thể dùng tên khác miễn nhất quán.

Ví dụ chạy trên shell Unix:

~~~bash
APP_IO_CORE_POOL_SIZE=6 APP_IO_MAX_POOL_SIZE=12 java -jar app.jar
~~~

Hoặc truyền trực tiếp property của Spring Boot:

~~~bash
java -jar app.jar --app.executor.io.core-pool-size=6 --app.executor.io.max-pool-size=12
~~~

Trên Windows PowerShell, có thể đặt các biến môi trường cho tiến trình shell hiện tại bằng `$env:APP_IO_CORE_POOL_SIZE = "6"` và `$env:APP_IO_MAX_POOL_SIZE = "12"` rồi chạy `java -jar app.jar`.

Các ví dụ lệnh giả định `app.jar` là một file Spring Boot executable JAR đã được build; không phải tên JAR cố định của mọi dự án.

### 3.2. Bước 2 — Có Bean Validation provider trên classpath

Trong dự án Gradle Spring Boot 3.x, cần một implementation của Jakarta Bean Validation, thường được cung cấp bởi starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Đây là **đoạn build.gradle minh họa**: dự án phải đã áp dụng cơ chế dependency/version management tương thích Spring Boot. Nếu chỉ thêm `@Validated` mà không có validator phù hợp, không được mặc nhiên cho rằng các annotation `@Min`, `@Max`, `@AssertTrue` sẽ thực thi như dự kiến. Hãy kiểm tra dependency và behavior bằng một trường hợp cấu hình sai.

### 3.3. Bước 3 — Định nghĩa record chứa cấu hình và validation

Tệp `IoExecutorProperties.java`:

~~~java
package example.concurrency;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "app.executor.io",
        ignoreUnknownFields = false
)
public record IoExecutorProperties(
        @Min(1) @Max(32) int corePoolSize,
        @Min(1) @Max(64) int maxPoolSize,
        @Min(0) @Max(2000) int queueCapacity,
        @Min(1) @Max(600) int keepAliveSeconds,
        @NotBlank String threadNamePrefix
) {
    @AssertTrue(message = "max-pool-size phải >= core-pool-size")
    public boolean isMaxAtLeastCore() {
        return maxPoolSize >= corePoolSize;
    }
}
~~~

Đây là **mã tích hợp Spring Boot 3.x**, cần có dependencies Spring Boot và Jakarta Validation. Java record cho phép constructor binding theo các component mà không cần khai báo setter. Spring Boot nhận các khóa kebab-case như `max-pool-size` và ánh xạ đến `maxPoolSize`.

Các ràng buộc làm gì?

- `@Min`/`@Max`: kiểm tra giá trị sau khi bind đã nằm trong miền hỗ trợ của ví dụ. Với tham số kiểu `int` bị thiếu, giá trị mặc định 0 sẽ bị `@Min(1)` bắt ở những trường yêu cầu tối thiểu 1. Tốt hơn vẫn là quản lý khóa bắt buộc hoặc default rõ ràng.
- `@NotBlank`: chặn tiền tố tên luồng `null`, rỗng hoặc chỉ chứa whitespace.
- `@AssertTrue` trên phương thức getter Boolean `isMaxAtLeastCore()`: kiểm tra điều kiện **liên trường** mà các annotation độc lập không thể diễn đạt.
- `ignoreUnknownFields=false`: yêu cầu binder báo lỗi khi bắt gặp thuộc tính ngoài cấu trúc đã định nghĩa trong phạm vi prefix được bind, hữu ích để phát hiện typo. Vẫn cần kiểm thử để phát hiện các property đặt sai prefix hoàn toàn hoặc nguồn cấu hình không được đọc.

`@Validated` đến từ Spring (`org.springframework.validation.annotation.Validated`). Các constraint đến từ `jakarta.validation.constraints`, không phải `javax.validation` của các thế hệ Spring Boot cũ.

Trong ứng dụng thật, có thể chọn tên property và nhóm theo workload như `io`, `cpu`, `reports`, nhưng chỉ tạo nhiều pool khi có lý do giới hạn tài nguyên riêng; quá nhiều executor khiến việc tuning và giám sát khó khăn hơn.

### 3.4. Bước 4 — Tạo ThreadPoolTaskExecutor bằng các giá trị đã bind

Tệp `ExecutorConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableConfigurationProperties(IoExecutorProperties.class)
public class ExecutorConfiguration {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor(IoExecutorProperties properties) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(properties.corePoolSize());
        executor.setMaxPoolSize(properties.maxPoolSize());
        executor.setQueueCapacity(properties.queueCapacity());
        executor.setKeepAliveSeconds(properties.keepAliveSeconds());
        executor.setThreadNamePrefix(properties.threadNamePrefix());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Phần này là **bean Spring**, không phải chương trình độc lập chạy bằng `javac`. `@EnableConfigurationProperties(IoExecutorProperties.class)` đăng ký properties record để Boot bind/validate; `@EnableAsync` bật cơ chế `@Async`. Bean `ThreadPoolTaskExecutor` được Spring quản lý, bao gồm quá trình gọi lifecycle initialization. Vì vậy ví dụ không cần gọi `initialize()` thủ công ngay trong factory method.

Có chủ ý chọn `AbortPolicy` để quá tải sinh tín hiệu rejection rõ ràng. Đây **không phải chính sách an toàn duy nhất**; có thể dùng chính sách khác nếu đã đánh giá cách tác động tới thread gọi, retry và yêu cầu không mất tác vụ. Nếu policy là lựa chọn cần externalize, hãy bind thành **enum với tập giá trị cho phép**, sau đó ánh xạ enum sang một tập `RejectedExecutionHandler` được kiểm soát; không nhận tên class tùy ý từ config để tạo bằng reflection.

### 3.5. Bước 5 — Dùng đúng executor cho @Async

Tệp `FileExportService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class FileExportService {

    @Async("ioExecutor")
    public CompletableFuture<String> export(String fileId) {
        // Công việc minh họa; I/O thật cần timeout và kiểm soát lỗi.
        return CompletableFuture.completedFuture("exported:" + fileId);
    }
}
~~~

Một bean khác gọi `fileExportService.export("file-7")` qua Spring proxy sẽ submit công việc vào `ioExecutor`. Các tham số được nạp từ properties record lúc tạo executor. Lời gọi bên trong cùng instance (`this.export(...)`) thường **bỏ qua proxy** ở chế độ `@Async` mặc định, làm công việc không được chuyển sang pool như dự kiến.

Nếu executor đã đầy, lỗi có thể phát sinh ngay khi **submit**; nếu task đã nhận nhưng chạy thất bại, kết quả tương ứng có thể hoàn thành theo trạng thái thất bại. Caller cần phân biệt hai dạng lỗi. Không nghĩ rằng khai báo `CompletableFuture` làm việc gửi task luôn thành công.

## 4. Validation được thực hiện khi nào?

Đối với thiết kế trong mục 3, tiến trình thường là:

~~~text
Khởi động ApplicationContext
          |
      Thu thập config
          |
      Bind giá trị có kiểu
          |
      Chạy Bean Validation
          |
  +-------+-------------+
  |                     |
 Hợp lệ               Sai/không bind được
  |                     |
  v                     v
 Tạo bean executor    Khởi động thất bại
  |
  v
 Bắt đầu nhận task
~~~

Nếu có giá trị `max-pool-size: 3` và `core-pool-size: 8`, giá trị riêng từng trường có thể nằm trong khoảng hợp lệ nhưng **quan hệ giữa chúng sai**; `@AssertTrue` cho thông báo xác định điều kiện bị vi phạm. Nếu số `core-pool-size` thành chữ `many`, binding vào `int` sẽ lỗi từ tầng chuyển kiểu **trước hoặc trong quá trình bind**, không cần chờ kiểm tra `@Min`.

Thông báo lỗi cụ thể, tên exception và thứ tự các chi tiết hiển thị tùy phiên bản Boot, Validation provider và đường khởi tạo bean. **Không nên bắt/nuốt lỗi validation rồi tự đổi thành con số ngẫu nhiên** để buộc ứng dụng chạy. Với thiết lập tài nguyên sai, fail-fast thường giúp giảm rủi ro sự cố khó chẩn đoán ở runtime.

### 4.1. Bảng trường hợp hợp lệ và không hợp lệ

Giả sử giữ `queueCapacity=64`, `keepAliveSeconds=60`, `threadNamePrefix=io-` trừ khi ghi khác:

| Input | Dự kiến | Nguyên nhân |
| --- | --- | --- |
| core=4, max=8 | **PASS** | Hai số trong miền và max ≥ core |
| core=0, max=8 | **FAIL** | Vi phạm `@Min(1)` của core |
| core=12, max=8 | **FAIL** | Vi phạm quan hệ `max ≥ core` |
| core=4, max=0 | **FAIL** | `@Min(1)` của max; đồng thời max < core |
| queue=-1 | **FAIL** | Chính sách ví dụ chỉ chấp nhận queue ≥ 0 |
| queue=0 | **PASS** | Là cấu hình bàn giao trực tiếp bằng `SynchronousQueue` |
| queue=5000 | **FAIL** | Vượt `@Max(2000)` của ví dụ |
| keep-alive-seconds=0 | **FAIL** | Ví dụ bắt buộc ≥ 1 giây |
| thread-name-prefix chỉ có dấu cách | **FAIL** | `@NotBlank` |
| core=abc | **FAIL** | Không bind được chuỗi thành `int` |
| core không được cung cấp trong mọi source và không có default | **FAIL theo mẫu này** | Primitive `int` nhận 0, vi phạm `@Min(1)` |

Trường hợp không có default cần hiểu đúng: nếu `application.yml` còn giá trị mặc định từ mục 3, việc **không đặt biến môi trường** không gây lỗi, vì binder vẫn nhận số mặc định từ file. Muốn property bắt buộc phải có giá trị triển khai, không đặt default trong config, dùng kiểu biểu diễn thiếu vắng rõ ràng và validation tương ứng, và kiểm tra khởi động không có biến môi trường.

### 4.2. Cross-field validation bằng @AssertTrue và phương án khác

Các annotation trên từng trường chỉ bảo đảm mỗi giá trị riêng lẻ nằm trong miền. Chúng không tự hiểu quan hệ `maxPoolSize ≥ corePoolSize`. Với quan hệ đơn giản, getter `isMaxAtLeastCore()` mang `@AssertTrue` đủ dễ đọc.

Khi có nhiều quan hệ phức tạp — ví dụ budget tổng các pool hoặc quy tắc phụ thuộc môi trường — có thể dùng class-level custom constraint/validator, hoặc một phương thức kiểm tra tập trung trước lúc tạo bean. Mục tiêu là báo lỗi **gắn với tên tham số và điều kiện sai**, không tạo ra một loạt validation rời rạc khó bảo trì.

Không chuyển mọi quy tắc vận hành thành `@Max` bất biến: ngưỡng cho workload có thể thay đổi khi tăng CPU quota, DB capacity và SLA. Hãy giữ miền an toàn ở properties, còn lựa chọn giá trị thực tế phải được đo đạc.

## 5. Java 17 độc lập: kiểm tra cấu hình mà không cần chạy Spring

Ví dụ sau mô phỏng **bước parse và kiểm tra tính nhất quán** bằng record Java 17. Nó không thay thế Bean Validation của Spring Boot, nhưng cho thấy vì sao cần cả kiểm tra kiểu lẫn kiểm tra giữa các tham số.

Tạo tệp `PoolSettingsValidationDemo.java`:

~~~java
public class PoolSettingsValidationDemo {
    record PoolSettings(int core, int max, int queue) {
        public PoolSettings {
            if (core < 1) {
                throw new IllegalArgumentException("core must be >= 1");
            }
            if (max < core) {
                throw new IllegalArgumentException("max must be >= core");
            }
            if (queue < 0) {
                throw new IllegalArgumentException("queue must be >= 0");
            }
        }
    }

    static void check(String core, String max, String queue) {
        try {
            PoolSettings settings = new PoolSettings(
                    Integer.parseInt(core),
                    Integer.parseInt(max),
                    Integer.parseInt(queue));

            System.out.printf("VALID core=%d max=%d queue=%d%n",
                    settings.core(), settings.max(), settings.queue());
        } catch (NumberFormatException e) {
            System.out.println("INVALID: value must be integer");
        } catch (IllegalArgumentException e) {
            System.out.println("INVALID: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        check("4", "8", "64");
        check("0", "8", "64");
        check("12", "8", "64");
        check("4", "8", "-1");
        check("x", "8", "64");
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 PoolSettingsValidationDemo.java
java PoolSettingsValidationDemo
~~~

Kết quả xác định:

~~~text
VALID core=4 max=8 queue=64
INVALID: core must be >= 1
INVALID: max must be >= core
INVALID: queue must be >= 0
INVALID: value must be integer
~~~

Giải thích: `Integer.parseInt(...)` bắt lỗi kiểu trước; compact constructor của `record` kiểm tra miền và quan hệ, sau đó mới có object cấu hình hợp lệ. `NumberFormatException` là subclass của `IllegalArgumentException` nên khối catch cho lỗi số phải đứng **trước** khối catch tổng quát. Các trường hợp được kiểm chứng với JDK hỗ trợ record; ví dụ trong Spring ở mục 3 tương đương về ý tưởng, nhưng dùng binder và Jakarta Bean Validation thay vì tự parse từng chuỗi.

Nếu input như `" 4 "` chưa được chuẩn hóa, `Integer.parseInt` thuần Java sẽ báo lỗi thay vì tự trim. Spring Boot binder có quy tắc chuyển kiểu riêng, vì vậy không suy diễn hành vi whitespace của Java thuần sang mọi property source.

## 6. Spring Framework thuần: đọc Environment và kiểm tra thủ công

Không sử dụng Spring Boot thì **không mặc nhiên có application.yml auto-load và binder @ConfigurationProperties như mục 3**. Spring Framework core vẫn có `Environment`, `@PropertySource`, `@Value` và cơ chế validation nhưng ứng dụng phải cấu hình nguồn và bước validate phù hợp.

Tạo tệp `executor.properties` trên classpath:

~~~properties
app.executor.core=4
app.executor.max=8
app.executor.queue=64
app.executor.keep-alive=60
~~~

Ví dụ class Spring Framework tích hợp:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@PropertySource("classpath:executor.properties")
public class PlainSpringExecutorConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor(Environment environment) {
        int core = environment.getRequiredProperty(
                "app.executor.core", Integer.class);
        int max = environment.getRequiredProperty(
                "app.executor.max", Integer.class);
        int queue = environment.getRequiredProperty(
                "app.executor.queue", Integer.class);
        int keepAlive = environment.getRequiredProperty(
                "app.executor.keep-alive", Integer.class);

        if (core < 1 || max < core || queue < 0 || keepAlive < 1) {
            throw new IllegalArgumentException(
                    "Invalid executor config: require core >= 1, " +
                    "max >= core, queue >= 0, keepAlive >= 1");
        }

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(core);
        executor.setMaxPoolSize(max);
        executor.setQueueCapacity(queue);
        executor.setKeepAliveSeconds(keepAlive);
        executor.setThreadNamePrefix("io-");
        return executor;
    }
}
~~~

Đây là **mã tích hợp**: cần Spring Context, đăng ký/scan cấu hình và resource `executor.properties`; không chạy chỉ bằng một lệnh `javac`. Nếu thiếu khóa, `getRequiredProperty` báo lỗi; nếu không thể chuyển thành số nguyên, conversion báo lỗi; nếu sai quan hệ, phương thức `@Bean` ném `IllegalArgumentException` khiến bean không khởi tạo thành công.

Ví dụ cho thấy hai lớp khác nhau:

- **Spring Framework core:** cung cấp trừu tượng property source và environment để ứng dụng tự đọc, tự dựng bean và tự quyết định cách validate.
- **Spring Boot:** ngoài các cơ chế nền tảng trên còn cung cấp config data, relaxed binding, `@ConfigurationProperties`, tích hợp validation và thứ tự override cấu hình để chuẩn hóa quy trình.

Không phải mọi ứng dụng Spring Framework đều sử dụng Spring Boot. Tài liệu, mã và cách cấu hình cần ghi rõ đang dựa trên lớp nào.

## 7. Thứ tự ưu tiên nguồn cấu hình và profile

### 7.1. Nguồn cấu hình có thể ghi đè nhau

Trong Spring Boot, `application.yml` nằm trong JAR, `application-{profile}.yml`, file cấu hình bên ngoài JAR, biến môi trường, system properties và command-line arguments đều có thể cung cấp cấu hình. Boot có **quy tắc ưu tiên của PropertySource**, vì vậy hai nguồn cùng khai báo một khóa sẽ không có nghĩa cả hai cùng được dùng.

Trước khi kết luận ứng dụng “không nhận cấu hình”, phải xác định **giá trị hiệu lực cuối cùng** và nguồn đang thắng. Ví dụ CLI `--app.executor.io.max-pool-size=12` có thể ghi đè giá trị trong `application.yml` theo thứ tự mặc định của Boot. Đừng khẳng định một thứ tự ưu tiên chung cho mọi dự án nếu chúng đã custom `PropertySources` hoặc tắt xử lý command-line properties.

### 7.2. Profile thay đổi giá trị, không thay đổi quy tắc validate

Tệp profile ví dụ `application-prod.yml`:

~~~yaml
app:
  executor:
    io:
      core-pool-size: 8
      max-pool-size: 16
      queue-capacity: 128
~~~

Các khóa khác vẫn lấy từ cấu hình cơ sở nếu không có nguồn ưu tiên cao hơn ghi đè. Các constraint của `IoExecutorProperties` **vẫn được áp dụng** sau khi bind giá trị cuối cùng; profile không phải lý do để bỏ qua kiểm tra tính hợp lệ.

Cần lưu ý việc bật profile bằng `spring.profiles.active=prod`, biến môi trường hoặc tham số CLI phải phù hợp cơ chế deployment; không giả định file có tên `application-prod.yml` sẽ được nạp nếu profile `prod` chưa active.

### 7.3. Cấu hình phải quan sát được nhưng không làm rò rỉ thông tin

Tham số core/max/queue thường không nhạy cảm, có thể log **giá trị hiệu lực đã được kiểm tra** ở mức phù hợp hoặc xuất metrics cấu hình. Nhưng không in toàn bộ `Environment` vì cùng nguồn đó có thể chứa token, mật khẩu hoặc credential. Khi dùng Actuator `/actuator/configprops`, cần giới hạn truy cập và tận dụng cơ chế sanitization; nó có thể giúp kiểm tra bean config nhưng không thay thế logging và metric định hướng.

## 8. Kiểm tra thực tế: trường hợp lỗi phải không khởi động bình thường

Một cách kiểm thử có giá trị là chạy các kịch bản cấu hình tách biệt (local hoặc integration test) rồi kiểm tra Spring ApplicationContext.

| Kịch bản | Đầu vào ví dụ | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | `core=4,max=8,queue=64` | Context tạo `ioExecutor` với giá trị tương ứng |
| Sai kiểu | `core=abc` | Binding lỗi; không khởi tạo executor như bình thường |
| Sai khoảng | `queue=-1` | Bean Validation từ chối |
| Sai quan hệ | `core=12,max=8` | `isMaxAtLeastCore()` trả false; validation từ chối |
| Thiếu tiền tố tên | `thread-name-prefix="   "` | `@NotBlank` từ chối |
| Giá trị sát biên | `queue=0`, `core=max=1` | Hợp lệ về constraint; queue là SynchronousQueue |
| Giới hạn trên | `max=65` | Constraint `@Max(64)` từ chối |
| Khóa gõ sai trong prefix | `max-pool-szie=8` | Với `ignoreUnknownFields=false`, dự kiến báo lỗi bind cho thuộc tính không hợp lệ; vẫn kiểm tra việc nguồn chứa khóa được nạp |

Dùng các biến cấu hình/CLI để tạo riêng từng case, không sửa cấu hình production chỉ để thử lỗi. Khi chạy integration test, bảo đảm không dùng lại singleton executor từ một context đã khởi tạo thành công vì điều đó che giấu quá trình bind mới. Với unit test validation thuần, có thể tạo `Validator` và gọi `validate(properties)`, nhưng việc test startup thật còn kiểm tra bước đọc nguồn, conversion, đăng ký bean và lifecycle.

**Không viết test chỉ xác nhận một method `isMaxAtLeastCore()` trả false** rồi kết luận toàn bộ Boot validation đã hoạt động; cần một kiểm tra cấu hình sai thực sự khiến khởi động context thất bại.

## 9. Lỗi phổ biến và cách sửa

### 9.1. Đưa ra ngoài nhưng vẫn có hard-code xung đột

Nếu YAML định nghĩa `core=4` nhưng mã `@Bean` vẫn gọi `setCorePoolSize(16)` sau khi đọc properties, cấu hình ngoài không còn là nguồn quyết định. Chỉ dùng các giá trị cuối cùng đã bind/validate. Nếu cần fallback, đặt ở lớp cấu hình hoặc mặc định được mô tả, tránh nhiều lớp fallback mâu thuẫn.

### 9.2. Dùng @Value cho nhiều trường rồi quên kiểm tra quan hệ

`@Value("${app.executor.io.core-pool-size}")` phù hợp để inject một scalar đơn giản, nhưng không tự xây dựng quy tắc `max >= core` hoặc biểu diễn nhóm thuộc tính có liên hệ. Với một nhóm tham số pool, `@ConfigurationProperties` thường rõ ràng hơn. Nếu bắt buộc dùng `@Value`, phải có bước validate tập trung trước khi tạo executor.

### 9.3. Chỉ validate số dương, không validate max >= core

`@Min(1)` trên core và max **không chứng minh max lớn hơn hoặc bằng core**. `core=16,max=8` vượt qua kiểm tra riêng từng field nếu nằm trong giới hạn. Cross-field constraint hoặc kiểm tra một lần ở factory method là cần thiết.

### 9.4. Nhầm queue=0 với queue bị lỗi

`queueCapacity=0` là hành vi hợp lệ của Spring `ThreadPoolTaskExecutor`: `SynchronousQueue` không giữ công việc chờ, buộc giao trực tiếp/cho phép mở rộng workers đến max rồi reject khi cần. Nếu workload không phù hợp thì chính sách ứng dụng có thể cấm giá trị này bằng `@Min(1)`, nhưng phải nói rõ đó là lựa chọn riêng.

### 9.5. Tưởng tăng maxPoolSize là tăng ngay concurrency

Sau khi tới core, `ThreadPoolExecutor` thường ưu tiên queue. Khi queue chưa đầy, pool **chưa cần** mở thêm workers tới max. Có thể thấy queue dài với `poolSize` bằng core dù max lớn. Đặt max cao mà queue gần như vô hạn không tạo ra concurrency như kỳ vọng.

### 9.6. Ràng buộc quá lỏng hoặc quá chặt

Không có validation làm lỗi đi sâu tới executor/JVM và khó đọc. Ngược lại, giới hạn 32 threads có thể hợp lý cho workload này nhưng quá thấp cho workload blocking I/O khác. Các giới hạn của record phải có chủ đích: ngăn giá trị rõ ràng nguy hiểm, trong khi điều chỉnh năng lực phải dựa trên thử tải và hệ thống phía sau.

### 9.7. Tưởng sửa YAML làm pool thay đổi ngay

Khi ứng dụng đang chạy, `IoExecutorProperties` đã được bind và executor đã khởi tạo. Dù một số setter của `ThreadPoolTaskExecutor` có thể thay đổi runtime, ví dụ trên **không có logic hot reload**. Queue type/capacity là quyết định lúc khởi tạo, không đổi tự động chỉ vì file thay đổi. Khi triển khai cấu hình mới, cách đơn giản và dễ kiểm soát là restart/rolling rollout phù hợp.

### 9.8. Giấu lỗi bằng default im lặng

Nếu production thiếu một khóa quan trọng nhưng default ẩn vẫn khiến ứng dụng chạy với `core=1`, sự cố có thể chỉ bộc lộ dưới tải. Hãy phân loại khóa nào được phép mặc định và khóa nào phải cung cấp khi deploy. Với khóa bắt buộc, dùng binding/validation làm thiếu cấu hình thành lỗi khởi động rõ ràng.

### 9.9. Đánh đồng lỗi khởi động với quá tải lúc chạy

Sai kiểu, sai khoảng và sai quan hệ là **lỗi cấu hình**; nên được phát hiện trước khi nhận traffic. Pool bão hòa/rejection xảy ra **ở runtime ngay cả với cấu hình hợp lệ** khi tải vượt năng lực. Cần theo dõi `getActiveCount()`, `getPoolSize()`, queue length, task duration, rejection, timeout và tài nguyên downstream. Annotation validation không thể bảo đảm sẽ không có rejection dưới tải.

## 10. Quy trình đưa cấu hình executor lên production

1. **Xác định workload**: CPU-bound hay blocking I/O; đo số task mỗi giây, thời gian giữ worker, độ trễ queue, CPU, bộ nhớ và giới hạn database/network.
2. **Chọn nhóm thuộc tính**: thống nhất prefix, tên biến môi trường, default, đơn vị đo và lý do từng giá trị. Với thời gian, ưu tiên định dạng rõ đơn vị khi thiết kế schema mới; ví dụ ở đây dùng `keepAliveSeconds` để khớp API Spring.
3. **Bind một lần theo kiểu rõ ràng**: Boot dùng `@ConfigurationProperties` record; Framework thuần dùng `Environment` và mapping/validator do ứng dụng quản lý.
4. **Validate hai lớp**: từng trường và quan hệ; xử lý missing/unknown/non-integer; báo lỗi ngay ở bootstrap.
5. **Định tuyến đúng bean**: `@Async("ioExecutor")` hoặc injection bằng qualifier để bảo đảm workload dùng pool đã cấu hình.
6. **Kiểm tra môi trường triển khai**: chạy các trường hợp invalid trong test/staging, xác nhận ứng dụng không khởi động với config sai; xác nhận profile/env/CLI override theo đúng ý định.
7. **Triển khai và quan sát**: ghi nhận bản cấu hình hiệu lực không nhạy cảm, theo dõi active workers, queue, rejection, p95/p99 và downstream.
8. **Thay đổi có kiểm soát**: tăng/giảm core/max/queue khi có bằng chứng; kiểm tra kết quả sau rollout, tránh đổi nhiều biến cùng lúc.

## 11. Câu hỏi tự kiểm tra

**1. Vì sao `@ConfigurationProperties` phù hợp với nhóm tham số executor hơn nhiều `@Value` rải rác?**

Vì nó gom các tham số thành object có kiểu, hỗ trợ relaxed binding, metadata, injection và validation tập trung. Đặc biệt, ta có chỗ rõ ràng để kiểm tra các điều kiện liên trường.

**2. Chỉ có `@Min(1)` trên `corePoolSize` và `maxPoolSize` đã đủ chưa?**

Chưa. `core=12,max=8` vẫn thỏa `@Min(1)` ở từng trường nhưng sai quan hệ. Cần `@AssertTrue`, custom constraint hoặc validate ở điểm tạo executor.

**3. Spring Boot có tự chạy `@Validated` của properties record nếu không có Bean Validation provider không?**

Không được giả định như vậy. Cần implementation Jakarta Bean Validation tương thích, thường thêm `spring-boot-starter-validation`, và kiểm tra bằng startup test với cấu hình sai.

**4. `queueCapacity=0` có phải luôn sai?**

Không. Nó chọn cơ chế `SynchronousQueue` trong `ThreadPoolTaskExecutor`. Tính phù hợp phụ thuộc chiến lược nhận task và tải; ví dụ bài này cho phép 0 và cấm số âm.

**5. Tại sao một cấu hình có max=64 nhưng số worker vẫn chỉ có 4?**

Vì sau khi đạt core, task thường được đưa vào queue trước. Khi queue còn nhận được, executor chưa cần tăng tới max. Phải đọc cả core, queue, activeCount và trạng thái downstream.

**6. Nếu thay biến môi trường khi JVM đang chạy thì executor có nhận số mới không?**

Không tự động theo ví dụ. Config được bind lúc khởi tạo context; muốn thay runtime cần cơ chế cập nhật riêng có kiểm tra an toàn hoặc rolling restart.

**7. Nếu validation PASS thì có thể bỏ giám sát rejection/latency không?**

Không. Validation chỉ ngăn cấu hình sai theo các quy tắc đã khai báo. Một pool hợp lệ vẫn có thể quá tải, bị chặn I/O, cạn connection hoặc tạo queue wait rất dài.

## 12. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, property sources, relaxed binding và @ConfigurationProperties Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework 6.x — ThreadPoolTaskExecutor API (core/max/queue/keep-alive): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 — ThreadPoolExecutor và RejectedExecutionHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Jakarta Bean Validation — javax/jakarta constraints (@Min, @Max, @NotBlank, @AssertTrue): https://jakarta.ee/specifications/bean-validation/
