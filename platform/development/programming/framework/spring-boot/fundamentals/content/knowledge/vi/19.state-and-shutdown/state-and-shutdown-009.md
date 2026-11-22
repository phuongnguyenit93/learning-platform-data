# SpringApplication.exit, ExitCodeGenerator và mã thoát tiến trình

Một ứng dụng Spring Boot cần biết cách khởi động và cả cách kết thúc. Khi một web service ngừng hoạt động, nó phải đóng tài nguyên và để hạ tầng điều phối tiến trình. Khi một ứng dụng command-line hoặc batch job hoàn tất, bên gọi còn phải biết công việc thành công hay thất bại. Thông tin đó thường được truyền qua **mã thoát tiến trình** (*process exit code*).

Spring Boot cung cấp `SpringApplication.exit(...)` để tính mã thoát và đóng `ApplicationContext`, cùng với interface `ExitCodeGenerator` để ứng dụng quyết định ý nghĩa của mã. Khi cần báo trạng thái cho hệ điều hành, caller có thể đưa số trả về vào `System.exit(...)`.

Ba cơ chế này có trách nhiệm khác nhau:

- **`SpringApplication.exit(context)`:** lấy mã kết quả từ các generator và đóng context nếu có thể.
- **`ExitCodeGenerator.getExitCode()`:** cung cấp số nguyên đại diện cho kết quả của ứng dụng.
- **`System.exit(code)`:** yêu cầu JVM kết thúc và gửi mã trạng thái cho hệ điều hành.

Nếu chỉ gọi `SpringApplication.exit(...)`, JVM chưa bị yêu cầu kết thúc bởi lời gọi đó. Nếu gọi `System.exit(0)` bất kể job thành công hay thất bại, scheduler sẽ khó phát hiện lỗi. Nếu đặt chuỗi `SpringApplication.exit(SpringApplication.run(...))` ngay trong main của web server, ứng dụng có thể dừng ngay sau khi startup.

Bài học giải thích từ nền tảng về exit status đến thiết kế mã thoát cho batch, lựa chọn giữa nhiều generator, xử lý exception, dừng bean an toàn và kiểm thử.

## 1. Process exit code là gì?

Hệ điều hành cung cấp mã trạng thái sau khi tiến trình kết thúc. Một shell script, scheduler, CI job hoặc process supervisor có thể dùng mã đó để quyết định bước tiếp theo.

Quy ước thông dụng là:

| Mã | Ý nghĩa |
|---|---|
| `0` | Kết thúc thành công |
| Khác `0` | Có lỗi hoặc một trạng thái đặc biệt cần xử lý |
| `1` | Có thể được ứng dụng dùng cho lỗi tổng quát |
| `2` | Có thể được ứng dụng dùng cho lỗi đầu vào |
| `10` | Có thể được ứng dụng dùng cho lỗi phụ trợ tạm thời |

Các mã `1`, `2` và `10` trong bảng chỉ là **quy ước ví dụ**. Spring Boot không mặc định rằng `2` luôn là lỗi tham số hoặc `10` là lỗi database. Một hệ thống nên tự quy định ý nghĩa ổn định, thống nhất giữa ứng dụng với các bên gọi.

Ví dụ một lệnh import trên Linux:

~~~bash
java -jar import-job.jar --input=orders.csv
status=$?

if [ "$status" -eq 0 ]; then
  echo "Import completed"
else
  echo "Import failed: exit code $status"
  exit "$status"
fi
~~~

Biến `$?` lưu mã kết quả của lệnh vừa chạy. Phải đọc ngay sau lệnh `java`; nếu chạy thêm lệnh khác, mã trong `$?` sẽ thay đổi.

Trong Windows PowerShell:

~~~powershell
java -jar import-job.jar --input=orders.csv
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Error "Import failed with exit code $code"
    exit $code
}
~~~

`$LASTEXITCODE` cho biết mã từ chương trình native như `java`.

### Khác gì với HTTP status và log?

| Cơ chế | Đối tượng nhận | Ví dụ |
|---|---|---|
| HTTP status | Client gọi một request | `200`, `400`, `500` |
| Log | Người vận hành và hệ thống quan sát | Không thể kết nối database |
| Exit code | Shell, scheduler, OS, process supervisor | `0`, `1`, `10` |

Một REST API trả HTTP 500 cho một request **không đồng nghĩa** toàn bộ JVM phải dừng với exit code 500. Tương tự, một job không có HTTP server vẫn cần trả exit status cho scheduler.

## 2. Vòng đời ứng dụng lúc dừng

Sau khi `SpringApplication.run(...)` khởi động thành công, Spring có một `ApplicationContext` chứa bean definitions và các bean đã được quản lý. Khi đóng context bình thường, Spring thực hiện những hoạt động như phát sự kiện đóng, dừng các thành phần lifecycle và hủy singleton beans.

Luồng khái quát:

~~~text
Một hành động yêu cầu kết thúc
                  |
                  v
   SpringApplication.exit(context)
                  |
                  +--> Đánh giá ExitCodeGenerator
                  |
                  +--> Đóng ApplicationContext
                  |        |
                  |        +--> ContextClosedEvent
                  |        +--> Dừng lifecycle components
                  |        +--> Hủy singleton beans
                  |        +--> @PreDestroy / destroy callbacks
                  |
                  v
             Trả int code
                  |
                  v
          System.exit(code)
                  |
                  v
          OS nhận exit status
~~~

Đây là sơ đồ trách nhiệm, không phải bản cam kết thứ tự từng callback nội bộ. Thứ tự lifecycle chi tiết phụ thuộc context, dependency và các thành phần như `SmartLifecycle`.

Một điểm then chốt: **container Spring và tiến trình JVM là hai đối tượng khác nhau**. Một JVM có thể có nhiều thread hoặc thậm chí nhiều ApplicationContext.

### JVM shutdown hook

Spring Boot thông thường đăng ký một shutdown hook để Spring context có thể đóng khi JVM kết thúc theo quy trình bình thường. Nhờ vậy, những callback như `@PreDestroy` và `DisposableBean.destroy()` có cơ hội chạy.

Tuy nhiên, nếu process bị kill cưỡng bức, JVM crash hoặc máy mất điện, shutdown hook có thể không chạy. Không nên chỉ lưu dữ liệu quan trọng trong callback shutdown.

## 3. SpringApplication.exit(...) hoạt động như thế nào?

Phương thức hỗ trợ chữ ký:

~~~java
static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators
);
~~~

Nó có thể dùng cả những generator được truyền trực tiếp và những bean triển khai `ExitCodeGenerator` trong context. Khi có nhiều generator, Spring Boot xác định mã theo thứ tự của chúng. Sau đó, context được đóng nếu có thể và phương thức trả về một `int`.

Ví dụ:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

Ở đây:

1. `SpringApplication.run` tạo context và thực hiện startup.
2. Các runner đồng bộ, nếu có, hoàn tất trước khi `run` trả về.
3. `SpringApplication.exit` lấy mã và đóng context.
4. `System.exit` yêu cầu JVM kết thúc với mã đó.

Cách này đặc biệt phù hợp với **CLI/batch app chạy một lần**.

### Nếu chỉ gọi SpringApplication.exit

~~~java
int code = SpringApplication.exit(context);
log.info("Exit code = {}", code);
~~~

Context có thể đã đóng, nhưng lời gọi không tự yêu cầu JVM kết thúc. JVM có thể tự kết thúc nếu không còn thread non-daemon; cũng có thể còn sống do thread hoặc thành phần ngoài context chưa dừng.

### Vì sao không gọi ngay sau run trong web application?

Xét:

~~~java
public static void main(String[] args) {
    int code = SpringApplication.exit(
            SpringApplication.run(WebApplication.class, args)
    );
    System.exit(code);
}
~~~

Trong một Spring Boot web service, `SpringApplication.run` thường trả về sau khi server khởi động, thay vì chờ vô hạn cho đến khi mọi HTTP request đã hoàn tất. Vì vậy, đoạn main này đóng context gần như ngay lập tức. Với web server chạy liên tục, main thông thường nên là:

~~~java
public static void main(String[] args) {
    SpringApplication.run(WebApplication.class, args);
}
~~~

Khi cần dừng, hãy để nền tảng triển khai hoặc một cơ chế điều phối lifecycle phù hợp yêu cầu shutdown.

## 4. ExitCodeGenerator: contract chọn mã thoát

Interface nằm trong package `org.springframework.boot.ExitCodeGenerator` và có một phương thức:

~~~java
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

Một implementation có thể trả `0` cho thành công và mã khác `0` cho trạng thái lỗi. Ví dụ:

~~~java
@Configuration
public class ExitConfiguration {

    @Bean
    public ExitCodeGenerator exitCodeGenerator() {
        return () -> 42;
    }
}
~~~

`42` chỉ là số minh họa. Nếu bean này có mặt trong context và ứng dụng gọi `SpringApplication.exit(context)`, nó có thể cung cấp mã thoát đó.

### Vì sao dùng interface?

Thay vì để service bất kỳ gọi `System.exit(1)` ngay khi gặp lỗi, ứng dụng có thể tách:

- Xử lý nghiệp vụ để xác định kết quả công việc.
- Chuyển kết quả sang exit code.
- Đóng context và kết thúc tiến trình.

`ExitCodeGenerator` thực hiện phần thứ hai. Nhờ đó, logic có thể được kiểm thử mà không kết thúc JVM test, và những thành phần nghiệp vụ không cần biết cơ chế process management.

### Generator nên đọc kết quả đã hoàn tất

Phương thức `getExitCode()` nên gọn, có thể dự đoán và ít side effect. Nếu nó gọi remote API, query database hoặc thực hiện thêm một giao dịch lớn ngay trong giai đoạn shutdown, việc dừng ứng dụng có thể bị kéo dài hoặc thất bại.

Nên xác định outcome trong lúc làm công việc rồi để generator chỉ đọc kết quả đó.

## 5. Ví dụ hoàn chỉnh: CLI import job trả mã thoát

Giả sử một job đọc file CSV và nhập dữ liệu. Hệ thống vận hành muốn biết:

- `0`: import thành công.
- `2`: thiếu tham số hoặc input không hợp lệ.
- `10`: import thất bại vì một lỗi có thể retry.
- `20`: lỗi không thể xử lý tự động.

Đầu tiên, định nghĩa hằng số:

~~~java
public final class JobExitCodes {
    public static final int SUCCESS = 0;
    public static final int INVALID_INPUT = 2;
    public static final int TEMPORARY_FAILURE = 10;
    public static final int PERMANENT_FAILURE = 20;

    private JobExitCodes() {
    }
}
~~~

### 5.1. Bean giữ kết quả công việc

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.ExitCodeGenerator;

public final class ImportJobOutcome
        implements ExitCodeGenerator {

    private final AtomicInteger exitCode =
            new AtomicInteger(JobExitCodes.SUCCESS);

    public void success() {
        exitCode.set(JobExitCodes.SUCCESS);
    }

    public void invalidInput() {
        exitCode.set(JobExitCodes.INVALID_INPUT);
    }

    public void temporaryFailure() {
        exitCode.set(JobExitCodes.TEMPORARY_FAILURE);
    }

    public void permanentFailure() {
        exitCode.set(JobExitCodes.PERMANENT_FAILURE);
    }

    @Override
    public int getExitCode() {
        return exitCode.get();
    }
}
~~~

`AtomicInteger` cho phép đọc/ghi giá trị an toàn hơn trong trường hợp có nhiều thread. Nó không tự giải quyết toàn bộ quy tắc ưu tiên giữa các lỗi: nếu nhiều tác vụ chạy song song, cần một chiến lược tổng hợp outcome phù hợp.

Đăng ký bean:

~~~java
@Configuration
public class ImportJobConfiguration {

    @Bean
    public ImportJobOutcome importJobOutcome() {
        return new ImportJobOutcome();
    }
}
~~~

Vì `ImportJobOutcome implements ExitCodeGenerator`, Spring Boot có thể tìm bean này khi tính mã lúc exit.

### 5.2. ApplicationRunner thực hiện công việc

~~~java
@Component
public class ImportJobRunner implements ApplicationRunner {

    private final ImportService importService;
    private final ImportJobOutcome outcome;

    public ImportJobRunner(
            ImportService importService,
            ImportJobOutcome outcome
    ) {
        this.importService = importService;
        this.outcome = outcome;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> inputs = args.getOptionValues("input");

        if (inputs == null || inputs.isEmpty()) {
            outcome.invalidInput();
            return;
        }

        try {
            importService.importFile(inputs.get(0));
            outcome.success();
        } catch (TemporaryImportException ex) {
            outcome.temporaryFailure();
        } catch (PermanentImportException ex) {
            outcome.permanentFailure();
        }
    }
}
~~~

`ImportService` và hai loại exception trong ví dụ là các class giả định của ứng dụng. Trong code thật, nên log nguyên nhân, kiểm tra giá trị option rỗng, quy định retry và xử lý transaction của import.

Ở đây runner **bắt những lỗi đã biết và chuyển thành outcome**. Nó hoàn thành bình thường về mặt lifecycle Spring, cho phép `SpringApplication.run` trả context. Main sau đó đóng context và trả exit code.

### 5.3. Main method kết thúc tiến trình

~~~java
@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ImportJobApplication.class,
                        args
                );

        int code = SpringApplication.exit(context);
        System.exit(code);
    }
}
~~~

Luồng chạy:

~~~text
java -jar import-job.jar --input=orders.csv
                  |
                  v
       SpringApplication.run
                  |
                  v
       ImportJobRunner.run
                  |
          Xử lý import file
                  |
       +----------+----------+
       |                     |
    Thành công           Thất bại
       |                     |
   outcome=0          outcome=2/10/20
       |                     |
       +----------+----------+
                  |
                  v
    SpringApplication.exit(context)
                  |
                  v
          System.exit(code)
                  |
                  v
         Shell nhận exit status
~~~

Mẫu này phù hợp với job một lần có runner thực hiện công việc đồng bộ và không còn task nền đang chạy sau khi runner hoàn tất.

## 6. Truyền ExitCodeGenerator trực tiếp

Generator không nhất thiết phải là một bean. `SpringApplication.exit` nhận các generator qua varargs:

~~~java
int code = SpringApplication.exit(
        context,
        () -> 12
);
~~~

Ví dụ caller có sẵn một kết quả:

~~~java
int requestedCode = completed ? 0 : 10;

int code = SpringApplication.exit(
        context,
        () -> requestedCode
);

System.exit(code);
~~~

Có thể truyền nhiều generator:

~~~java
int code = SpringApplication.exit(
        context,
        () -> 0,
        () -> 12
);
~~~

Các generator truyền trực tiếp được xét cùng với những bean generator trong context. Nếu có nhiều generator trả mã khác `0`, kết quả không đơn giản là “generator truyền cuối cùng luôn thắng”.

### Khi nào dùng bean và khi nào truyền trực tiếp?

| Trường hợp | Lựa chọn |
|---|---|
| Nhiều service cập nhật outcome của một job | Bean trạng thái triển khai `ExitCodeGenerator` |
| Caller đã xác định code và chỉ cần đóng context | Truyền generator trực tiếp |
| Nhiều module cùng đề xuất code | Các generator có thứ tự hoặc một outcome aggregator |
| Exception khiến startup thất bại | Exception generator hoặc exception mapper |

Để dễ vận hành, một ứng dụng batch thường nên có **một nơi chịu trách nhiệm cuối cùng** cho mã thoát.

## 7. Nhiều ExitCodeGenerator: chọn mã khác 0 đầu tiên

Spring Boot có thể thu thập nhiều `ExitCodeGenerator`. Nếu chúng được sắp xếp A, B, C và trả:

~~~text
A -> 0
B -> 12
C -> 20
~~~

kết quả là `12`, vì Spring Boot chọn **mã khác 0 đầu tiên** theo thứ tự generator. Một mã `0` trước đó không ngăn generator phía sau đưa ra mã lỗi.

Để kiểm soát thứ tự, có thể implement `Ordered` hoặc dùng `@Order`.

~~~java
@Component
public class ValidationExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getExitCode() {
        return hasValidationFailure() ? 2 : 0;
    }

    @Override
    public int getOrder() {
        return 10;
    }

    private boolean hasValidationFailure() {
        return false; // Đọc outcome thật của ứng dụng.
    }
}
~~~

Một generator khác:

~~~java
@Component
public class InfrastructureExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getExitCode() {
        return hasInfrastructureFailure() ? 10 : 0;
    }

    @Override
    public int getOrder() {
        return 20;
    }

    private boolean hasInfrastructureFailure() {
        return false;
    }
}
~~~

Giá trị order nhỏ hơn thông thường có ưu tiên xét trước. Với ví dụ, generator validation có thể được xét trước generator infrastructure.

Có thể dùng annotation:

~~~java
@Component
@Order(10)
public class ValidationExitCode
        implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

Nếu cần quyết định loại lỗi có ưu tiên cao hơn, hãy quy định rõ thứ tự hoặc sử dụng một aggregator duy nhất. Không nên để một exit status có ý nghĩa nghiệp vụ phụ thuộc vào thứ tự đăng ký bean ngẫu nhiên.

### Phân biệt order của generator và runner

`@Order` trên `ApplicationRunner` dùng để sắp xếp các runner theo contract của Spring Boot. Thứ tự xét các `ExitCodeGenerator` là một vấn đề riêng. Một runner chạy trước không đồng nghĩa exit code của bean liên quan được ưu tiên trước.

## 8. Không dùng ExitCodeGenerator để tạo ra side effect lúc shutdown

Ví dụ nên tránh:

~~~java
@Override
public int getExitCode() {
    remoteClient.sendFinalBusinessTransaction();
    archiveService.archiveAllData();
    return 0;
}
~~~

Nguyên tắc tốt hơn là hoàn thành nghiệp vụ trước, ghi nhận kết quả, rồi để generator chỉ trả mã.

~~~java
public final class BatchResult implements ExitCodeGenerator {
    private volatile int code = 0;

    public void failWith(int newCode) {
        this.code = newCode;
    }

    @Override
    public int getExitCode() {
        return code;
    }
}
~~~

Nếu phải thực hiện cleanup, hãy đặt nó trong lifecycle callback phù hợp như `@PreDestroy` hoặc một service được điều phối dừng rõ ràng. Nếu phải lưu trạng thái bền vững, hãy lưu trong transaction nghiệp vụ; không phụ thuộc việc shutdown callback luôn chạy.

Không bao giờ gọi `System.exit` từ chính `getExitCode`:

~~~java
@Override
public int getExitCode() {
    System.exit(1); // Không nên làm.
    return 1;
}
~~~

Đó là hành vi vượt quá trách nhiệm của generator và có thể ngắt quy trình đóng context.

## 9. Exception cũng có thể implement ExitCodeGenerator

Không phải mọi lần chạy đều hoàn thành startup bình thường. Một lỗi nghiêm trọng trong runner hoặc trong quá trình khởi động có thể khiến `SpringApplication.run(...)` ném exception trước khi trả về context.

Spring Boot hỗ trợ exception implement `ExitCodeGenerator`:

~~~java
public class InvalidImportArgumentsException
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidImportArgumentsException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

Runner có thể ném exception này:

~~~java
@Component
public class ImportArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (!args.containsOption("input")) {
            throw new InvalidImportArgumentsException(
                    "Missing --input argument"
            );
        }

        // Xử lý công việc.
    }
}
~~~

Nếu exception gây thất bại startup và đi qua cơ chế failure handling của Spring Boot, framework có thể xác định exit code từ `getExitCode()`.

### Phân biệt outcome bình thường và exception

Nếu công việc kết thúc với một trạng thái nghiệp vụ hợp lệ, ví dụ “không có dữ liệu để xử lý”, không nhất thiết cần ném exception. Có thể lưu trạng thái trong một bean `ExitCodeGenerator`.

Exception phù hợp khi luồng khởi động hoặc công việc thực sự không thể tiếp tục và cần được coi là thất bại.

### Exception xảy ra sau startup

Một exception implement `ExitCodeGenerator` được ném trong một HTTP request sau khi server hoạt động không tự làm JVM dừng. Handler của HTTP request có thể bắt lỗi và trả HTTP response. Cơ chế xử lý exit code khi startup thất bại không thay thế kiến trúc xử lý lỗi runtime của một service.

## 10. ExitCodeExceptionMapper cho exception không thể sửa

Khi exception thuộc thư viện bên ngoài hoặc không thể thay đổi class để implement interface, dùng `ExitCodeExceptionMapper`.

Contract:

~~~java
public interface ExitCodeExceptionMapper {
    int getExitCode(Throwable exception);
}
~~~

Mapper trả mã phù hợp hoặc `0` nếu không muốn map exception đó sang một exit code đặc biệt.

Ví dụ:

~~~java
@Configuration
public class ExceptionExitConfiguration {

    @Bean
    public ExitCodeExceptionMapper exitCodeExceptionMapper() {
        return exception -> {
            if (exception instanceof InvalidConfigurationException) {
                return 2;
            }
            if (exception instanceof ExternalSystemUnavailableException) {
                return 10;
            }
            return 0;
        };
    }
}
~~~

Hai exception trong ví dụ là kiểu giả định. Mapper nên nhận diện chính xác những lỗi mà người vận hành cần phân biệt.

### Exception có thể bị bọc nhiều lớp

Một exception gốc có thể xuất hiện bên trong một `BeanCreationException` hoặc exception framework khác. Nếu cần, có thể kiểm tra cause chain:

~~~java
@Bean
public ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        Throwable cause = exception;

        while (cause != null) {
            if (cause instanceof InvalidImportArgumentsException) {
                return 2;
            }

            if (cause instanceof ExternalSystemUnavailableException) {
                return 10;
            }

            cause = cause.getCause();
        }

        return 0;
    };
}
~~~

Đừng map mọi `RuntimeException` thành một mã đặc biệt vì nó sẽ che giấu các lỗi không liên quan.

### ExitCodeExceptionMapper không phải @ControllerAdvice

`@ControllerAdvice` và `@ExceptionHandler` phục vụ HTTP response. `ExitCodeExceptionMapper` phục vụ exit code của ứng dụng trong cơ chế startup failure. Hai công cụ không thay thế nhau.

## 11. Nếu SpringApplication.run thất bại trước khi trả context

Đoạn code quen thuộc:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

chỉ chạy hai dòng cuối nếu `SpringApplication.run` trả context thành công. Nếu một exception ném ra trong quá trình tạo bean hoặc runner, flow Java có thể rời khỏi main trước khi `SpringApplication.exit(context)` được gọi.

Vì vậy cần phân biệt:

~~~text
          SpringApplication.run
                   |
          +--------+--------+
          |                 |
      Thành công          Startup lỗi
          |                 |
    Trả về context     Failure handling
          |                 |
          v                 v
 SpringApplication.exit   Exception generator
          |              hoặc mapper khi phù hợp
          v                 |
    System.exit(code)     Kết thúc với trạng thái lỗi
~~~

Spring Boot có failure handling riêng trong trường hợp startup thất bại. Khi thiết kế mã lỗi, hãy dùng exception generator/mapper nếu muốn có số cụ thể trong tình huống đó, và kiểm thử process exit status thực tế bằng tiến trình con.

### Tránh ghi đè lỗi thành thành công

Đoạn này gây sai tín hiệu:

~~~java
try {
    SpringApplication.run(BatchApplication.class, args);
} catch (Exception ex) {
    System.exit(0);
}
~~~

Khi startup đã thất bại mà trả `0`, scheduler hoặc CI có thể đánh dấu job thành công. Nếu bắt exception trong main, hãy giữ nguyên ý nghĩa lỗi và không che mất thông tin chẩn đoán.

## 12. ExitCodeEvent và những sự kiện dừng ứng dụng

Spring Boot có `ExitCodeEvent` trong package `org.springframework.boot`. Nó biểu diễn một event khi mã thoát đã được xác định từ cơ chế generator tương ứng.

Ví dụ quan sát:

~~~java
@Component
public class ExitCodeObserver {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        int exitCode = event.getExitCode();
        // Ghi log hoặc metrics.
    }
}
~~~

Cần phân biệt nó với những event khác:

| Event | Ý nghĩa |
|---|---|
| `ExitCodeEvent` | Đã xác định exit code theo cơ chế generator |
| `ContextClosedEvent` | ApplicationContext đang đóng |
| `ApplicationFailedEvent` | Startup ứng dụng thất bại |
| `ApplicationReadyEvent` | Ứng dụng đã hoàn tất các bước startup phù hợp |

`ExitCodeEvent` không phải nơi duy nhất đáng tin cậy để cleanup. Không phải mọi kiểu shutdown đều được bảo đảm phát event này, nhất là khi process bị kill cưỡng bức.

## 13. SpringApplication.exit, context.close và System.exit

| Lời gọi | Đóng Spring context | Trả mã exit | Chủ động yêu cầu JVM kết thúc |
|---|---|---|---|
| `context.close()` | Có | Không | Không |
| `SpringApplication.exit(context)` | Có, nếu có thể | Có, `int` | Không |
| `System.exit(code)` | Thông qua shutdown hooks nếu chúng chạy | Truyền mã cho OS | Có |
| `Runtime.getRuntime().halt(code)` | Bỏ qua shutdown hooks bình thường | Truyền mã cho OS | Có, cưỡng bức |

`Runtime.halt` chỉ phù hợp với trường hợp đặc biệt khi quy trình shutdown thông thường không thể hoàn tất. Nó có thể làm mất dữ liệu chưa flush hoặc bỏ qua cleanup.

### Vì sao cần cả exit và System.exit?

Một job có thể gọi:

~~~java
int code = SpringApplication.exit(context);
~~~

Sau lời gọi đó, Spring Boot đã xác định mã kết quả, nhưng shell chưa chắc nhận được mã đó nếu JVM kết thúc tự nhiên theo một đường khác. Khi muốn trả đúng mã cho OS:

~~~java
System.exit(code);
~~~

### Vì sao không chỉ dùng System.exit?

Spring Boot thường đăng ký shutdown hook, nên `System.exit` có thể kích hoạt quy trình đóng context. Nhưng trong một job mà code đã nắm giữ context và cần kết quả từ generator, gọi `SpringApplication.exit` trước thể hiện rõ ranh giới cleanup và exit code. Nó cũng giúp kiểm thử phần tính mã mà không buộc kết thúc JVM.

## 14. Spring bean cleanup khi context đóng

Khi `SpringApplication.exit(context)` đóng context, Spring có thể gọi những callback hủy đã được đăng ký.

### @PreDestroy

~~~java
@Component
public class TemporaryFileManager {

    @PreDestroy
    public void cleanup() {
        // Đóng/xóa tài nguyên tạm thuộc trách nhiệm của bean.
    }
}
~~~

Với Spring Boot 3 và Spring Framework 6, annotation thường thuộc `jakarta.annotation.PreDestroy`. Các thế hệ cũ có thể dùng `javax.annotation.PreDestroy`.

### DisposableBean

~~~java
@Component
public class ManagedSocket implements DisposableBean {

    @Override
    public void destroy() throws Exception {
        // Đóng socket thuộc quyền sở hữu của bean.
    }
}
~~~

### @Bean destroyMethod

~~~java
@Configuration
public class RemoteClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

### SmartLifecycle

Một thành phần chạy nền có thể cần ngừng nhận task rồi chờ task đang chạy hoàn tất. `SmartLifecycle` cung cấp cơ chế start/stop và phase để điều phối thứ tự. Nó thích hợp hơn một callback hủy đơn lẻ khi có dependency giữa nhiều worker.

Bean cleanup phải an toàn, có timeout phù hợp và chỉ đóng tài nguyên mà bean thực sự sở hữu.

### Prototype không được tự hủy đầy đủ như singleton

Spring tạo và cấu hình prototype, sau đó giao instance cho caller. Container thường không theo dõi toàn bộ vòng đời sử dụng của từng prototype để tự gọi destruction callback như singleton. Nếu prototype giữ resource, caller cần có cơ chế đóng riêng.

## 15. ApplicationRunner và CommandLineRunner

`ApplicationRunner` và `CommandLineRunner` là cách phổ biến để chạy công việc sau khi context đã refresh. Trong batch application, main có thể gọi `SpringApplication.exit` sau khi các runner đồng bộ đã kết thúc.

~~~text
SpringApplication.run
        |
        +--> Tạo ApplicationContext
        +--> Tạo bean
        +--> Gọi runner
        |
        v
Runner hoàn tất
        |
        v
SpringApplication.run trả context
        |
        v
SpringApplication.exit(context)
        |
        v
System.exit(code)
~~~

### Runner trả void nhưng cần mã lỗi

Một runner không cần trả `int`. Nó có thể cập nhật `JobOutcome` mà `ExitCodeGenerator` đọc sau đó. Nếu một exception phải làm startup thất bại, runner có thể ném exception có mã tương ứng.

### Async task có thể chưa hoàn tất

Đây là một bẫy quan trọng:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> importService.importData());
}
~~~

Runner trả về ngay sau khi submit, trong khi task vẫn đang chạy. Nếu main gọi `SpringApplication.exit(context)` ngay, context có thể đóng trước khi import xong và mã thoát không phản ánh kết quả thật.

Cần đợi completion hoặc có cơ chế điều phối rõ:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    Future<?> future = executor.submit(
            () -> importService.importData()
    );

    future.get();
}
~~~

Ví dụ minh họa thao tác đợi; code thực tế cần xử lý timeout, interruption, cancellation và mapping lỗi. Không nên chờ vô hạn một tài nguyên không phản hồi.

## 16. Graceful shutdown cho web service

Một web service thường không có một công việc duy nhất để trả mã sau mỗi request. Khi dừng, nó cần:

1. Ngừng hoặc hạn chế nhận request mới theo cơ chế web server.
2. Cho request đang xử lý thời gian hoàn tất.
3. Dừng consumer và worker nền.
4. Đóng connection pool, file/socket và tài nguyên khác.
5. Để process kết thúc theo điều phối của hạ tầng.

Trong những phiên bản Spring Boot hỗ trợ, có thể cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Thời gian thực tế còn phụ thuộc web server và thời hạn mà Docker, Kubernetes hoặc process supervisor cấp cho tiến trình.

### Không kết thúc JVM từ một HTTP request lỗi

~~~java
@RestController
public class OrderController {

    @PostMapping("/orders")
    public void createOrder() {
        System.exit(1); // Không nên làm.
    }
}
~~~

Một request lỗi thường nên trả HTTP error và để server tiếp tục phục vụ request khác. Việc dừng toàn tiến trình phải thuộc về một cơ chế quản trị/vận hành có kiểm soát.

### Web server chạy liên tục nên có main đơn giản

~~~java
@SpringBootApplication
public class WebApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
~~~

Exit code của process chỉ có ý nghĩa khi process thật sự kết thúc, khác với status code của từng request.

## 17. Tín hiệu hệ điều hành, SIGTERM và SIGKILL

Nhiều nền tảng gửi tín hiệu để yêu cầu process kết thúc. Với shutdown có kiểm soát, JVM thường có cơ hội chạy shutdown hooks, và Spring có cơ hội đóng context.

Nhưng cần phân biệt:

- **Kết thúc bình thường:** main đã hoàn tất hoặc process nhận yêu cầu dừng có kiểm soát.
- **Dừng cưỡng bức:** như `SIGKILL` trên Linux, không cho phép JVM chạy shutdown hooks.
- **JVM crash/mất điện:** quá trình dừng có thể bỏ qua cleanup.

Không nên giả định mã do `ExitCodeGenerator` chọn luôn là mã mà shell nhìn thấy khi process bị tín hiệu cưỡng bức chấm dứt. Một số shell biểu diễn lỗi do signal bằng exit status dựa trên `128 + signal number`, nhưng đó là convention của môi trường, không phải quy tắc của Spring Boot.

Khi điều tra một process exit bất thường, kết hợp exit status, log, signal/restart reason và dữ liệu vận hành.

## 18. Dải mã thoát và khả năng tương thích hệ điều hành

`ExitCodeGenerator.getExitCode()` trả một `int` của Java. Nhưng hệ điều hành/shell có thể biểu diễn mã với giới hạn khác nhau.

Trong nhiều môi trường Unix/POSIX, shell nhìn thấy exit status của process trong phạm vi 8 bit. Một mã lớn hơn `255` hoặc một mã âm có thể không hiển thị giống số nguyên ban đầu. Windows có cơ chế exit code riêng.

Với ứng dụng cần chạy trên nhiều môi trường, thường nên chọn **một tập số nguyên dương nhỏ**, ví dụ `0`, `2`, `10`, `20`, tránh những mã có convention đặc biệt trong shell hoặc scheduler mà tổ chức đang dùng.

Không nên dùng exit code như nơi nhét toàn bộ chi tiết lỗi. Exit code là tín hiệu ngắn; log, metrics hoặc báo cáo job lưu nguyên nhân cụ thể.

## 19. Exit code trong scheduler, CI/CD và container

Một job có thể chạy từ cron, CI/CD pipeline, systemd service, Windows Task Scheduler hoặc Kubernetes Job. Bên điều phối thường dùng exit status để phân biệt thành công và thất bại, nhưng hành vi retry hoặc đánh dấu kết quả phụ thuộc cấu hình của chính nền tảng đó.

Ví dụ script:

~~~bash
#!/usr/bin/env bash

java -jar daily-sync.jar --mode=full
code=$?

if [ "$code" -ne 0 ]; then
  echo "Daily sync failed with code $code"
  exit "$code"
fi

echo "Daily sync succeeded"
~~~

Nếu script được dùng trong pipeline, việc exit khác `0` thường làm bước job thất bại theo cấu hình pipeline.

### Bảng mã là một contract vận hành

| Mã | Tên gợi ý | Cách bên gọi có thể xử lý |
|---|---|---|
| `0` | `SUCCESS` | Tiếp tục |
| `2` | `INVALID_INPUT` | Sửa input; không retry mù |
| `10` | `TRANSIENT_FAILURE` | Retry có giới hạn |
| `20` | `PERMANENT_FAILURE` | Gửi cảnh báo/cần can thiệp |
| `30` | `PARTIAL_FAILURE` | Kiểm tra dữ liệu đã xử lý |

Đây là bảng ví dụ, không phải quy ước Spring Boot. Nếu đổi ý nghĩa mã, phải cập nhật script, scheduler và tài liệu vận hành tương ứng.

### Retry cần idempotency

Nếu job đã ghi một phần dữ liệu trước khi trả mã `10`, retry có thể tạo bản ghi trùng hoặc lặp side effect. Vì vậy, một exit code hỗ trợ retry **không tự giải quyết tính nhất quán dữ liệu**. Job cần transaction, checkpoint hoặc idempotency key thích hợp.

## 20. Quy trình xác định mã thoát dễ hiểu

Nếu một job có nhiều loại kết quả, có thể dùng một outcome enum:

~~~java
public enum JobOutcome {
    SUCCESS(0),
    INVALID_INPUT(2),
    TEMPORARY_FAILURE(10),
    PERMANENT_FAILURE(20);

    private final int code;

    JobOutcome(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
~~~

Bean generator ánh xạ outcome cuối:

~~~java
@Component
public class JobResult implements ExitCodeGenerator {

    private volatile JobOutcome outcome = JobOutcome.SUCCESS;

    public void complete(JobOutcome outcome) {
        this.outcome = outcome;
    }

    @Override
    public int getExitCode() {
        return outcome.code();
    }
}
~~~

Với nhiều tác vụ song song, cần tổng hợp kết quả theo một quy tắc rõ: thất bại nào được ưu tiên, khi nào coi toàn job thành công và làm sao tránh một task hoàn tất muộn ghi đè kết quả lỗi.

Một generator duy nhất với outcome tổng hợp thường dễ hiểu hơn nhiều generator cạnh tranh, nếu ứng dụng có yêu cầu trạng thái phức tạp.

## 21. Kiểm thử ExitCodeGenerator và SpringApplication.exit

Không nên gọi `System.exit(...)` trực tiếp trong unit test cùng JVM với JUnit, vì nó có thể kết thúc toàn bộ test runner.

### Unit test generator

~~~java
@Test
void shouldReturnFailureCode() {
    JobResult result = new JobResult();

    result.complete(JobOutcome.TEMPORARY_FAILURE);

    assertEquals(10, result.getExitCode());
}
~~~

Đây là kiểm thử logic mapping thuần Java.

### Context test cho exit

Có thể tạo một Spring context nhỏ:

~~~java
@Test
void closesContextAndReturnsCode() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(
            ExitCodeGenerator.class,
            () -> () -> 12
    );
    context.refresh();

    int code = SpringApplication.exit(context);

    assertEquals(12, code);
    assertFalse(context.isActive());
}
~~~

Test này kiểm tra sự tích hợp giữa generator bean và lời gọi `SpringApplication.exit`. Nó không gọi `System.exit`.

### Test exception mapper

~~~java
@Test
void mapsKnownFailure() {
    ExitCodeExceptionMapper mapper = exception -> {
        if (exception instanceof IllegalArgumentException) {
            return 2;
        }
        return 0;
    };

    assertEquals(
            2,
            mapper.getExitCode(
                    new IllegalArgumentException("Invalid input")
            )
    );
}
~~~

Test trên chỉ xác nhận hàm ánh xạ. Nếu cần chứng minh Spring Boot thực sự tải mapper và trả mã khi startup lỗi, cần integration test.

### End-to-end process test

Để xác nhận exit status hệ điều hành, khởi động ứng dụng bằng **tiến trình con**:

~~~bash
java -jar report-job.jar --input=missing.csv
status=$?
echo "status = $status"
~~~

Lúc này việc gọi `System.exit` sẽ chỉ kết thúc tiến trình của job, không kết thúc JVM chạy test. Cần giới hạn thời gian chạy và xử lý các dependency ngoài (database, file system, network) nếu được sử dụng.

## 22. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Context đã đóng nhưng shell thấy mã thành công | Chỉ gọi `SpringApplication.exit` mà không chuyển code cho OS | Gọi `System.exit(code)` ở tầng main của batch app |
| Job luôn trả mã 42 | Bean generator cố định `() -> 42` | Chuyển sang generator đọc outcome thực |
| Web server khởi động rồi tắt ngay | Gọi exit ngay sau `SpringApplication.run` | Dùng main chuẩn cho web service |
| Runner lỗi nhưng script nhận 0 | Catch lỗi rồi trả thành công | Ánh xạ thất bại sang mã khác `0` |
| Exit code không như mong đợi | Nhiều generator trả nonzero | Kiểm tra `Ordered`, `@Order` và ưu tiên |
| Exception mapper không được dùng cho HTTP error | Mapper không xử lý HTTP request | Dùng controller exception handling |
| Kết quả job bị đọc quá sớm | Runner chỉ submit async task | Chờ công việc hoàn tất trước khi exit |
| Cleanup không chạy khi process bị kill | Shutdown hook bị bỏ qua | Bảo vệ dữ liệu bằng persistence/transaction |
| Test suite dừng đột ngột | Gọi `System.exit` trong JVM test | Chỉ test code/result hoặc dùng process con |
| Mã lỗi khác trên Unix | Số lớn hoặc âm bị giới hạn khi OS/shell biểu diễn | Dùng mã nhỏ, không âm |
| Không tìm ra nguyên nhân từ exit code | Code quá ít thông tin | Kết hợp log, metrics, job ID |
| Process không dừng sau context.close | Còn thread non-daemon hoặc tài nguyên ngoài context | Xác định chủ sở hữu và dừng resource đúng lifecycle |

### Không dùng mã thoát để biểu diễn từng request

Nếu một request HTTP thất bại, hãy xử lý qua status code HTTP và exception handler. Exit code dành cho vòng đời của toàn tiến trình hoặc một job do tiến trình đó thực hiện.

### Không coi shutdown callback là một giao dịch nghiệp vụ

`@PreDestroy` có thể không chạy trong sự cố cưỡng bức. Ghi nhận kết quả quan trọng và checkpoint trong khi job hoạt động, không đợi đến cuối tiến trình.

### Không tự dừng JVM trong service nghiệp vụ

`System.exit` từ domain service làm mờ dependency và khó kiểm thử. Service nên trả outcome hoặc ném exception có ý nghĩa; main/lifecycle layer quyết định kết thúc tiến trình.

## 23. Một kịch bản vận hành đầy đủ

Giả sử ứng dụng đồng bộ dữ liệu khách hàng được scheduler chạy mỗi đêm:

~~~text
Scheduler
    |
    v
java -jar customer-sync.jar
    |
    v
Spring Boot tạo context
    |
    v
ApplicationRunner gọi SyncService
    |
    +--> Kiểm tra input
    +--> Đọc nguồn dữ liệu
    +--> Đồng bộ database
    +--> Ghi checkpoint
    |
    v
JobResult giữ outcome cuối
    |
    v
SpringApplication.exit(context)
    |
    +--> Đọc JobResult.getExitCode()
    +--> Dừng bean và đóng resource
    |
    v
System.exit(code)
    |
    v
Scheduler đọc exit status
    |
    +--> 0: hoàn tất
    +--> 2: sửa đầu vào
    +--> 10: retry có giới hạn
    +--> 20: cảnh báo
~~~

Nếu job ghi 80% dữ liệu rồi trả mã retry, lần sau phải dựa trên checkpoint hoặc idempotent upsert để không làm sai dữ liệu. Exit status chỉ thông báo kết quả; consistency cần được giải quyết trong thiết kế nghiệp vụ.

Nếu scheduler chỉ biết hai trạng thái success/failure, vẫn có thể dùng `0` và một mã lỗi `1` duy nhất. Không cần tạo bảng mã phức tạp khi bên gọi không có nhu cầu phân loại.

## 24. Checklist trước khi triển khai

1. **Xác định loại ứng dụng:** job chạy một lần hay web server lâu dài?
2. **Quy định exit code contract:** `0` cho thành công; các mã lỗi có ý nghĩa ổn định.
3. **Chọn một nơi chịu trách nhiệm outcome:** tránh nhiều generator cạnh tranh không có ưu tiên.
4. **Đảm bảo runner đồng bộ hoàn tất:** đừng đóng context khi task đang chạy.
5. **Dùng `SpringApplication.exit` khi cần vừa lấy mã vừa đóng context.**
6. **Chỉ gọi `System.exit` ở ranh giới process phù hợp**, thường là main của batch app.
7. **Map startup exception khi cần:** exception implement generator hoặc `ExitCodeExceptionMapper`.
8. **Đọc mã trả về từ hệ điều hành trong test process con.**
9. **Đừng dùng HTTP status làm process exit code.**
10. **Đảm bảo cleanup tài nguyên đúng lifecycle** và có giới hạn thời gian.
11. **Không dựa vào shutdown hooks để lưu trạng thái bền vững.**
12. **Chọn số nhỏ, không âm** để dễ tương thích shell/OS.
13. **Ghi log nguyên nhân lỗi** và giữ thông tin đủ cho điều tra.
14. **Đồng bộ quy ước mã với scheduler/CI/CD**, đặc biệt nếu chúng thực hiện retry.
15. **Kiểm tra trường hợp lỗi nhiều bước và retry**, tránh xử lý dữ liệu trùng.

## Kết luận

`SpringApplication.exit(context)` là công cụ Spring Boot để xác định mã kết quả và đóng ApplicationContext. `ExitCodeGenerator` cho phép bean hoặc một đối tượng được truyền trực tiếp cung cấp mã thoát, còn `ExitCodeExceptionMapper` giúp ánh xạ exception ở đường lỗi startup. Khi có nhiều generator, Spring Boot chọn **mã khác `0` đầu tiên** theo thứ tự được xác định bằng `Ordered` hoặc `@Order`.

`System.exit(code)` mới là lời gọi yêu cầu JVM kết thúc và truyền mã trạng thái cho hệ điều hành. Trong ứng dụng batch, phối hợp runner đồng bộ, `SpringApplication.exit` và `System.exit` giúp scheduler quan sát đúng kết quả. Trong web service, cần giữ context sống cho đến khi có yêu cầu shutdown phù hợp và phân biệt rõ HTTP request status với process lifecycle.

Một mã thoát tốt là một **hợp đồng vận hành có thể kiểm thử**: mã số rõ ràng, phản ánh kết quả thực, không phụ thuộc cleanup may rủi và được các script/worker hiểu thống nhất. Thiết kế đúng ranh giới giữa outcome nghiệp vụ, Spring lifecycle và JVM giúp ứng dụng kết thúc an toàn và dễ chẩn đoán khi có sự cố.
