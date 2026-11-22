# Dọn output file sau test trong Spring Batch

Khi kiểm thử một batch job hoặc một step ghi tệp, dữ liệu đầu ra thường không chỉ nằm trong bộ nhớ. `FlatFileItemWriter`, `JsonFileItemWriter`, `StaxEventItemWriter` hoặc một writer tự xây dựng có thể tạo CSV, TXT, JSON, XML, tệp tạm và thư mục trên ổ đĩa. Nếu các tệp này còn tồn tại sau test, lần chạy kế tiếp có thể đọc nhầm kết quả cũ, ghi nối vào tệp trước đó hoặc thất bại vì đường dẫn đã tồn tại.

Trong chủ đề **Test data** của **Spring Batch Core Processing**, *dọn output file sau test* là tổ chức vòng đời của dữ liệu đầu ra như sau:

```text
Tạo khu vực output riêng cho test
          |
          v
Khởi chạy writer / step / job
          |
          v
Đọc và assert file đầu ra
          |
          v
Đóng reader, writer, stream và các tài nguyên liên quan
          |
          v
Dọn output, kể cả khi assert hoặc batch execution thất bại
```

Mục tiêu là mỗi test bắt đầu từ một trạng thái đã biết, có thể chạy lại độc lập và không ảnh hưởng đến dữ liệu của các test khác hay của ứng dụng thật. Cách ưu tiên với **JUnit Jupiter (JUnit 5)** là để `@TempDir` quản lý thư mục riêng cho từng test. Khi bắt buộc ghi vào một vị trí khác, cần thiết lập cleanup rõ ràng bằng `@AfterEach` hoặc `try/finally` và chỉ xóa tài nguyên do test sở hữu.

## 1. Vì sao phải dọn output file?

Giả sử một step xuất báo cáo:

```text
exportOrdersStep
    ItemReader<Order>
        -> ItemProcessor<Order, String>
        -> FlatFileItemWriter<String>
        -> build/reports/orders.csv
```

Lần đầu test có ba đơn hàng và tạo `orders.csv`. Nếu không dọn tệp, những lần sau có thể gặp các hiện tượng sau:

| Hiện tượng | Nguyên nhân có thể | Hệ quả |
| --- | --- | --- |
| File chứa dòng từ test trước | Writer cấu hình append hoặc logic tùy chỉnh mở tệp ở chế độ nối | Assert sai, dữ liệu trùng |
| Test thành công khi đáng lẽ thất bại | Test đọc output còn lại từ lần chạy trước, không xác nhận output mới thực sự được tạo | False positive |
| Test thất bại không ổn định | Nhiều test dùng chung tên file, cùng tạo/xóa/đọc | Test phụ thuộc thứ tự hoặc chạy song song |
| Lỗi không thể xóa file, đặc biệt trên Windows | `ItemStream`, `BufferedWriter`, input stream chưa đóng | File còn bị khóa, cleanup lỗi |
| Output rác tích lũy | Test thất bại trước đoạn `delete`, hoặc không có teardown | Môi trường CI đầy tệp, khó phân biệt kết quả mới/cũ |
| Test xóa nhầm dữ liệu thật | Đường dẫn output trỏ tới thư mục dùng chung hoặc lấy từ cấu hình runtime | Mất dữ liệu ngoài phạm vi test |

Hai hành động phải được tách bạch: **assert nội dung file** chứng minh xử lý đúng; **cleanup file** bảo đảm môi trường sau test được đưa về trạng thái sạch. Cleanup không thay thế assertions, và assertion thành công không chứng minh cleanup đã diễn ra.

## 2. Giải pháp ưu tiên: `@TempDir` của JUnit 5

JUnit Jupiter cung cấp `@TempDir` để tạo một thư mục tạm cho test. Sau khi bài test hoàn tất, JUnit dọn thư mục cùng các tệp bên trong theo chính sách cleanup được cấu hình (thông thường là xóa sau test). Điều này áp dụng cả khi assertion ném lỗi, vì việc cleanup là một phần của vòng đời test.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportFileTest {

    @TempDir
    Path outputDir;

    @Test
    void writesExpectedContent() throws IOException {
        // Arrange: mỗi test nhận một đường dẫn riêng.
        Path output = outputDir.resolve("orders.csv");

        // Giả lập kết quả của một writer để tập trung vào vòng đời file.
        Files.write(output, List.of("A001,PAID", "A002,NEW"),
            StandardCharsets.UTF_8);

        // Assert trước khi JUnit dọn outputDir.
        assertThat(Files.exists(output)).isTrue();
        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");

        // Không cần Files.delete(output): JUnit xử lý khi test kết thúc.
    }
}
```

`@TempDir` có thể khai báo tại field hoặc tham số method:

```java
@Test
void exportsOneFile(@TempDir Path outputDir) throws IOException {
    Path file = outputDir.resolve("result.csv");
    Files.writeString(file, "id,status\n1,DONE\n", StandardCharsets.UTF_8);

    assertThat(Files.readString(file, StandardCharsets.UTF_8))
        .contains("1,DONE");
}
```

Đây là ví dụ minh họa quản lý output theo JUnit. Trong Spring Batch, thay `Files.write...` bằng thao tác chạy writer hoặc step. Việc cleanup vẫn do JUnit quản lý, miễn là output thực sự nằm **bên trong** thư mục được cấp phát.

### 2.1. Ưu điểm và giới hạn của `@TempDir`

- Đường dẫn được tạo cho test giúp tránh trùng tên khi chạy nhiều test hoặc chạy song song.
- Cleanup không phụ thuộc vào việc method test chạy đến dòng cuối; test thất bại giữa chừng vẫn kích hoạt quá trình teardown.
- Không phải viết code xóa file đệ quy cho các thư mục chứa nhiều output nhỏ.
- JUnit chỉ quản lý cây thư mục tạm đã cấp. Nếu job bỏ qua tham số và ghi ra `C:/data/export.csv` hoặc một object storage bên ngoài, `@TempDir` không thể tự dọn những tài nguyên đó.
- Muốn giữ lại file để điều tra khi test thất bại, có thể cấu hình cleanup mode của JUnit cho môi trường debug, nhưng nên trả về chính sách dọn mặc định ở CI.

`@TempDir` **không** dọn bảng metadata của `JobRepository` như `BATCH_JOB_EXECUTION` hay `BATCH_STEP_EXECUTION`; đó là một vòng đời dữ liệu khác.

## 3. Ví dụ trực tiếp với `FlatFileItemWriter`

Trước khi đưa writer vào job, ta có thể kiểm thử việc ghi file ở mức component. Ví dụ sau dùng API của **Spring Batch 5.x** và JUnit Jupiter:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.core.io.FileSystemResource;

class OrderWriterTest {

    @TempDir
    Path outputDir;

    @Test
    void writesOrdersAndReleasesFileHandle() throws Exception {
        Path output = outputDir.resolve("orders.csv");

        FlatFileItemWriter<String> writer =
            new FlatFileItemWriterBuilder<String>()
                .name("orderWriter")
                .resource(new FileSystemResource(output))
                .encoding(StandardCharsets.UTF_8.name())
                .lineAggregator(item -> item)
                .build();

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                "A001,PAID",
                "A002,NEW"
            )));
        } finally {
            // ItemStream phải đóng ngay cả khi writer.write() ném exception.
            writer.close();
        }

        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");
        // JUnit dọn outputDir và orders.csv sau test.
    }
}
```

`FlatFileItemWriter` triển khai `ItemStream`. Khi chạy bằng một `Step` được cấu hình đúng, Spring Batch đảm nhiệm vòng đời `open`, `update` và `close`. Nhưng **khi gọi writer trực tiếp trong test**, lập trình viên phải chủ động đóng writer. `try/finally` là cần thiết để không giữ file handle nếu ghi lỗi, đặc biệt trên Windows.

Nếu mục tiêu là kiểm tra transaction, restart, skip hoặc writer được đóng đúng bởi framework, nên chạy **step thật** thay vì chỉ gọi `write()` như trên.

## 4. Kiểm thử step ghi file với đường dẫn do test cung cấp

Một khó khăn phổ biến ở integration test là ApplicationContext được cache giữa các test, còn thư mục `@TempDir` thay đổi từng lần chạy. Cách dễ kiểm soát là đưa đường dẫn output vào `JobParameters` và dùng writer có `@StepScope` để lấy đúng đường dẫn của lần chạy hiện tại.

Ví dụ này dành cho **Spring Boot 3.x, Spring Batch 5.x, JUnit 5**. Các dependency Gradle cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Test sau dựng một job chỉ có step `exportOrdersStep`, chạy nó qua `JobLauncherTestUtils`, kiểm tra CSV và để JUnit xóa thư mục output sau test.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = ExportOrdersStepTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ExportOrdersStepTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path outputDir;

    @Test
    void exportsToItsOwnTemporaryDirectory() throws Exception {
        Path output = outputDir.resolve("orders.csv");

        JobParameters parameters = new JobParametersBuilder()
            .addString("outputPath", output.toAbsolutePath().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
            "exportOrdersStep", parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(Files.exists(output)).isTrue();
        assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
            .containsExactly("A001,PAID", "A002,NEW");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Job exportOrdersJob(JobRepository repository,
                            @Qualifier("exportOrdersStep") Step exportStep) {
            return new JobBuilder("exportOrdersJob", repository)
                .start(exportStep)
                .build();
        }

        @Bean
        Step exportOrdersStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("ordersWriter") FlatFileItemWriter<String> writer) {

            return new StepBuilder("exportOrdersStep", repository)
                .<String, String>chunk(2, transactionManager)
                .reader(new ListItemReader<>(List.of(
                    "A001,PAID", "A002,NEW")))
                .writer(writer)
                .build();
        }

        @Bean
        @StepScope
        FlatFileItemWriter<String> ordersWriter(
                @Value("#{jobParameters['outputPath']}") String outputPath) {

            return new FlatFileItemWriterBuilder<String>()
                .name("ordersWriter")
                .resource(new FileSystemResource(outputPath))
                .encoding(StandardCharsets.UTF_8.name())
                .lineAggregator(item -> item)
                .build();
        }
    }
}
```

Điều cần chú ý trong ví dụ:

1. `@TempDir` cấp đường dẫn đầu ra và tạo thư mục cha trước khi step bắt đầu. Đường dẫn `orders.csv` vẫn chưa tồn tại tại thời điểm chuẩn bị test.
2. `outputPath` là `JobParameter` của lần chạy. `@StepScope` trì hoãn việc khởi tạo writer thực tới khi step hoạt động, vì thế writer nhận đúng giá trị `outputPath` của test hiện tại.
3. Spring Batch mở và đóng `FlatFileItemWriter` trong vòng đời step. Test chỉ cần assert sau khi `launchStep(...)` trả kết quả.
4. Khi test kết thúc, JUnit xóa output directory. Dù có lỗi trong writer hoặc trong assertion, lifecycle cleanup vẫn được gọi; riêng việc xóa có thể thất bại nếu resource bị khóa hoặc tiến trình khác đang dùng nó.
5. Đường dẫn khác nhau giữa các test cũng tạo identifying `JobParameters` khác nhau, giúp tránh va chạm `JobInstance` trên `JobRepository` dùng lại trong test context. Nếu dùng tham số không thay đổi giữa các lần chạy, cần chủ động xử lý metadata để tránh `JobInstanceAlreadyCompleteException`.

**Lưu ý về phiên bản:** Trong Spring Batch 6.x, `JobOperatorTestUtils.startStep(...)` thay thế hướng sử dụng `JobLauncherTestUtils.launchStep(...)` được dùng ở Spring Batch 5.x. Spring Batch 6 còn thay đổi một số package của kiểu core. Về nguyên tắc cleanup, `@TempDir`, `JobParameters` và scoped writer vẫn áp dụng như nhau; hãy điều chỉnh API/import theo version của project.

## 5. Khi không dùng được `@TempDir`: cleanup bằng `@AfterEach`

Một số test kiểm tra tích hợp với chương trình hoặc công cụ chỉ nhận một output path cố định. Nếu bắt buộc phải tự dọn file, đặt cleanup trong `@AfterEach` thay vì để ở cuối method test, vì method test có thể dừng ngay tại assertion hoặc exception.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FixedOutputPathTest {

    private Path testDirectory;
    private Path report;
    private Path temporaryPart;

    @BeforeEach
    void createIsolatedDirectory() throws IOException {
        testDirectory = Files.createTempDirectory("spring-batch-output-");
        report = testDirectory.resolve("report.csv");
        temporaryPart = testDirectory.resolve("report.csv.tmp");
    }

    @Test
    void exportsReport() throws IOException {
        // Trong test thật: gọi step để ghi report.
        Files.writeString(report, "id,total\nA001,100\n",
            StandardCharsets.UTF_8);

        assertThat(Files.readString(report, StandardCharsets.UTF_8))
            .contains("A001,100");
    }

    @AfterEach
    void removeGeneratedFiles() throws IOException {
        // Chỉ xóa những file do test này có quyền quản lý.
        if (report != null) {
            Files.deleteIfExists(report);
        }
        if (temporaryPart != null) {
            Files.deleteIfExists(temporaryPart);
        }
        if (testDirectory != null) {
            Files.deleteIfExists(testDirectory); // thư mục phải rỗng
        }
    }
}
```

`Files.deleteIfExists(...)` không ném lỗi nếu file không tồn tại, hữu ích khi batch dừng trước khi tạo output. Tuy nhiên, nó vẫn ném `IOException` khi file đang bị mở, thiếu quyền hoặc thư mục chưa rỗng. Trong nhiều tình huống nên **để test thất bại với lỗi cleanup** để tìm ra resource leak; tránh nuốt toàn bộ exception một cách im lặng.

Ví dụ trên liệt kê chính xác hai tệp có thể sinh ra. Nếu writer tạo cấu trúc nhiều thư mục con hoặc tên file động, `@TempDir` đơn giản và an toàn hơn nhiều. Chỉ khi không có lựa chọn đó mới cân nhắc hàm xóa đệ quy, kèm bước xác minh path trỏ **đúng** vào thư mục test đã tạo. Không gọi xóa đệ quy trên một đường dẫn đọc trực tiếp từ biến môi trường production hay `JobParameters` chưa kiểm soát.

Nếu tệp chỉ được tạo trong một code path ngắn ngoài JUnit, sử dụng `try/finally` cũng có ý nghĩa:

```java
Path output = Files.createTempFile("batch-result-", ".csv");
try {
    // Chạy logic ghi output và assert kết quả.
} finally {
    Files.deleteIfExists(output);
}
```

Với `FlatFileItemWriter`, bảo đảm `close()` được gọi **trước** `Files.deleteIfExists(output)`.

## 6. Phân biệt cleanup test với hành vi xóa file của writer

`FlatFileItemWriter` có một số cấu hình quản lý output trong quá trình thực thi:

| Cấu hình | Vai trò | Có thay thế teardown test không? |
| --- | --- | --- |
| `shouldDeleteIfExists(true)` | Có thể xóa file đích đã tồn tại khi bắt đầu một lần thực thi mới, tùy trạng thái restart | Không. File mới vẫn còn sau step |
| `shouldDeleteIfEmpty(true)` | Xóa output rỗng khi kết thúc nếu không có dữ liệu được ghi | Không. Output có dữ liệu vẫn còn |
| `appendAllowed(true)` | Cho phép ghi nối vào file hiện có theo cấu hình writer | Không. Càng cần tránh file cũ từ test khác |
| `saveState(true)` và `ExecutionContext` | Lưu trạng thái để hỗ trợ restart | Không. Đây là checkpoint, không phải cleanup tệp |

Không nên sửa các cờ này chỉ để che việc test không dọn output. Ví dụ, một test dự kiến xác nhận chế độ append phải chủ động tạo file ban đầu rồi assert chính xác những dòng được thêm, sau cùng mới dọn toàn bộ file. Một test restart cần giữ file sau lần chạy thứ nhất để thực thi lần chạy thứ hai; chỉ dọn khi toàn bộ kịch bản restart đã được assert.

### File output có đặc điểm khác transaction của database

Spring Batch thường quản lý transaction của chunk. Tuy nhiên, ghi file không nhất thiết có cùng khả năng rollback vật lý như một bảng SQL. Khi chunk thất bại hoặc step dừng giữa chừng, file có thể đã được tạo hoặc chứa dữ liệu một phần, tùy writer và cấu hình buffer/transaction. Test kiểm tra failure path cần xác nhận cả:

- `JobExecution`/`StepExecution` có trạng thái kỳ vọng (`FAILED`, `STOPPED` hoặc trạng thái khác theo thiết kế).
- File có tồn tại hay không, có bao nhiêu dòng và có dữ liệu không mong muốn hay không.
- File tạm hoặc file kết quả dở dang được xử lý đúng theo chính sách ứng dụng.
- Sau khi assert xong, output thuộc phạm vi test được dọn.

Đừng giả định transaction rollback của cơ sở dữ liệu tự động xóa file đã được writer tạo. Nếu ứng dụng cần cam kết xuất file nguyên vẹn, có thể thiết kế ghi ra file tạm rồi chỉ đổi tên/đưa vào thư mục đích khi step thành công; test cũng phải kiểm tra hành vi của file tạm khi có lỗi.

## 7. Dọn input và output đúng phạm vi

Một batch test thường cần cả input fixture lẫn output mới tạo:

```text
@TempDir testDir/
    input/
        orders.csv        # dữ liệu đầu vào của test
    output/
        result.csv        # file do batch tạo
        result.csv.tmp    # file trung gian nếu có
```

Có thể tạo cấu trúc này dưới `@TempDir`:

```java
Path inputDir = Files.createDirectories(testDir.resolve("input"));
Path outputDir = Files.createDirectories(testDir.resolve("output"));

Path input = inputDir.resolve("orders.csv");
Path output = outputDir.resolve("result.csv");

Files.writeString(input, "id,total\nA001,100\n",
    StandardCharsets.UTF_8);
```

Cách tổ chức đó giúp phân biệt fixture ban đầu với sản phẩm của batch, đồng thời JUnit có thể dọn cả hai sau test. Nếu input fixture là file bất biến đặt ở `src/test/resources`, chỉ đọc nó; không xóa hay ghi đè fixture nguồn. Nếu writer có thể thay đổi file input, hãy **copy** fixture vào thư mục tạm trước khi chạy.

Trong nhiều project, một số test dùng `build/test-output/` (hoặc `target/test-output/`) thay cho thư mục hệ điều hành. Khi chọn cách này, nên cấp thư mục con riêng cho từng test, không dọn toàn bộ `build/` hay `target/` trong `@AfterEach`. Việc làm sạch thư mục build diện rộng thuộc về build tool hoặc quy trình CI, không phải một unit test.

## 8. Những trường hợp cleanup thường bị bỏ sót

### 8.1. Test thất bại trước khi tạo file

Batch có thể fail trong reader hoặc processor, khiến output chưa được tạo. Cleanup dùng `Files.deleteIfExists` hoặc `@TempDir` xử lý được trường hợp này. Không nên coi việc file không tồn tại là một lỗi cleanup.

### 8.2. Output được giữ mở khi assertion chạy

Nếu gọi trực tiếp `FlatFileItemWriter` mà không `close`, nội dung có thể chưa được flush đầy đủ và Windows có thể từ chối xóa file. Đóng writer trước khi đọc/so sánh output. Với step thực, để Spring Batch quản lý `ItemStream`; nếu có writer tự viết, phải thực hiện đúng hợp đồng mở/đóng tài nguyên.

### 8.3. Test chạy song song

Hai bài test cùng ghi `report.csv` vào một thư mục chung dễ làm hỏng nhau: một test xóa file khi test kia còn đọc. Dùng thư mục `@TempDir` riêng, hoặc tạo một tên thư mục duy nhất cho mỗi test execution. Không dựa vào số thứ tự chạy test hoặc một tên file cố định duy nhất cho cả suite.

### 8.4. File đã xóa nhưng Spring Batch metadata vẫn tồn tại

`@TempDir` xóa output trên đĩa nhưng không xóa `JobInstance`, `JobExecution`, `StepExecution` khỏi `JobRepository`. Nếu dùng lại cùng *identifying JobParameters* cho job đã hoàn tất, test tiếp theo vẫn có thể bị `JobInstanceAlreadyCompleteException`. Trong test database riêng, có thể dùng `JobRepositoryTestUtils` để dọn metadata đúng phạm vi; hoặc cấp identifying parameters khác nhau giữa các test. Đừng xóa metadata chung của job thật.

### 8.5. File tạm, nhiều output và nested directory

Step có thể tạo `report.csv.tmp`, file partition, file log riêng hoặc nhiều tệp theo ngày. Test nên biết rõ những file nào là sản phẩm mong đợi, kiểm tra sự tồn tại/vắng mặt của chúng trước khi JUnit cleanup. Nếu dùng `@TempDir`, các tệp này nằm trong cùng cây thư mục nên được dọn theo vòng đời của test.

### 8.6. Output không nằm trên filesystem cục bộ

Khi writer gửi dữ liệu tới S3, MinIO, object storage hoặc SFTP, `@TempDir` chỉ dọn được dữ liệu cục bộ. Với integration test thật, tạo bucket/prefix hoặc thư mục từ xa dành riêng cho test và xóa chính các đối tượng test tạo ra trong teardown; ưu tiên fake hoặc container lưu trữ để tránh tác động môi trường dùng chung. Tránh dùng wildcard xóa rộng cho các đối tượng ngoài test.

### 8.7. Cần giữ file để chẩn đoán lỗi

Trong CI, cleanup tự động giữ suite sạch và tái lập được. Khi cần điều tra lỗi khó, có thể cấu hình JUnit giữ `@TempDir` ở chế độ debug hoặc copy file cần thiết sang khu vực artifacts của CI trước teardown. Không để test phụ thuộc vào việc một file từ lần chạy trước còn sót.

## 9. Chiến lược đề xuất theo loại test

| Loại test | Thiết lập output | Cleanup phù hợp |
| --- | --- | --- |
| Unit test formatter/processor | Không cần tạo file | Không có output để dọn |
| Unit test `FlatFileItemWriter` | `FileSystemResource` trỏ vào `@TempDir` | Gọi `writer.close()` rồi để JUnit dọn |
| Integration test một step xuất file | `outputPath` đi qua `JobParameters`, `@StepScope` writer | `@TempDir` cho output; metadata test xử lý riêng |
| Integration test luồng job nhiều step | Tạo `input/` và `output/` trong một thư mục test riêng | Dọn sau khi hoàn tất assertions cả job |
| Test retry/restart | Giữ cùng output qua các pha thử nghiệm | Cleanup sau pha cuối cùng, không xóa giữa các lần restart |
| Test tích hợp hệ thống ngoài | Tài nguyên riêng do test sở hữu (bucket, prefix, thư mục từ xa) | Teardown xóa đúng tài nguyên đã tạo |

## 10. Những nguyên tắc cần nhớ

1. **Mọi output test phải có chủ sở hữu và phạm vi rõ ràng.** Đặt output trong thư mục riêng cho test thay vì dùng đường dẫn runtime của ứng dụng.
2. **Assert trước khi cleanup.** Kiểm tra nội dung, encoding, tên tệp, số dòng và các file phụ tùy yêu cầu nghiệp vụ.
3. **Đóng tài nguyên trước khi xóa.** Với `ItemStream`, đảm bảo `close()` được gọi dù ghi thất bại.
4. **Để cleanup chạy ngay cả khi test lỗi.** Ưu tiên `@TempDir`; nếu không phù hợp thì dùng `@AfterEach` hoặc `try/finally`.
5. **Không xóa vượt phạm vi test.** Tránh xóa một thư mục cha dùng chung, fixture nguồn hoặc dữ liệu production.
6. **Tách dọn output file khỏi dọn metadata batch.** File và `JobRepository` có vòng đời khác nhau; cần giải quyết cả hai khi test chạy lặp lại.

Khi áp dụng nhất quán các nguyên tắc trên, test Spring Batch sẽ phát hiện chính xác lỗi xuất file, ít phụ thuộc vào thứ tự chạy, có khả năng chạy song song và để lại môi trường sạch cho lần chạy tiếp theo.

## Tài liệu tham khảo

- [JUnit 5 User Guide — Built-in Extensions, `@TempDir`](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): cách JUnit tạo và dọn thư mục tạm cho test.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): tích hợp Spring Batch với Spring Test và công cụ chạy step/job.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): cấu hình file writer và các tùy chọn quản lý output.
- [Spring Batch API — `FlatFileItemWriter`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/file/FlatFileItemWriter.html): vòng đời `ItemStream` và các tùy chọn liên quan đến output file.
