# Dữ liệu rỗng và giới hạn trong kiểm thử Spring Batch

## 1. Vì sao cần kiểm thử dữ liệu rỗng và dữ liệu biên?

Trong Spring Batch, một job thường xử lý khối lượng lớn dữ liệu từ file, cơ sở dữ liệu hoặc dịch vụ bên ngoài. Bộ dữ liệu có vài trăm bản ghi hợp lệ thường chạy suôn sẻ nhưng không đại diện cho những tình huống dễ gây lỗi nhất: **không có bản ghi nào**, **chỉ có bản ghi không hợp lệ**, **số bản ghi nằm ngay tại ranh giới kích thước chunk/page**, hoặc **giá trị một trường nằm đúng ngưỡng hợp lệ**.

Ví dụ, một job nhập đơn hàng có thể gặp:

- Ngày không phát sinh đơn hàng: truy vấn nguồn trả về 0 hàng.
- File CSV có header nhưng không có bản ghi dữ liệu.
- Toàn bộ bản ghi bị processor lọc bỏ vì không đáp ứng điều kiện nghiệp vụ.
- Có đúng 100 hoặc 101 bản ghi, trong khi cấu hình chunk size là 100.
- Số tiền bằng 0, ngay dưới mức tối thiểu, đúng mức tối đa hoặc vượt mức tối đa.
- Một chuỗi có độ dài đúng bằng giới hạn cột trong cơ sở dữ liệu.
- Dữ liệu chứa khoảng trắng, ký tự Unicode, trường thiếu và trường `null`.

Các tình huống này tác động trực tiếp tới cách Spring Batch kết thúc vòng đọc, đóng tài nguyên, ghi chunk cuối cùng, cập nhật số đếm của step và quyết định trạng thái job. Một bài kiểm thử tốt phải xác định **hành vi mong đợi của hệ thống đối với từng loại đầu vào**, rồi kiểm tra cả kết quả nghiệp vụ lẫn metadata của Spring Batch.

Mục tiêu của bài học là xây dựng test data có chủ đích, thực thi job trong môi trường kiểm thử cô lập và dùng `StepExecution` để chứng minh dữ liệu rỗng hoặc dữ liệu biên đã được xử lý đúng.

## 2. Hiểu chính xác “rỗng” ở từng giai đoạn

Không phải mọi trường hợp “không có dữ liệu đầu ra” đều giống nhau.

| Tình huống | Reader | Processor | Writer | Điều cần kiểm thử |
| --- | --- | --- | --- | --- |
| Nguồn thật sự rỗng | Trả về `null` ngay lần `read()` đầu | Không được gọi | Không được gọi | Step kết thúc theo chính sách mong đợi, không phát sinh đầu ra |
| Nguồn có dữ liệu, mọi bản ghi bị lọc | Đọc được N bản ghi | Trả về `null` cho từng bản ghi | Không ghi item nào | `readCount=N`, `filterCount=N`, `writeCount=0` |
| Nguồn có bản ghi lỗi định dạng | Đọc/ánh xạ có thể ném exception | Tùy cấu hình | Tùy cấu hình | Phân biệt `skip`, `retry` và `FAILED` |
| Bản ghi có trường trống | Vẫn trả về đối tượng nếu ánh xạ hợp lệ | Có thể chuẩn hóa, lọc hoặc báo lỗi | Phụ thuộc nghiệp vụ | Không nhầm trường trống với kết thúc nguồn |
| Nguồn không tồn tại | Có thể lỗi khi mở tài nguyên | Chưa chạy | Chưa chạy | Phân biệt file thiếu với file có 0 dòng |
| Nguồn có dữ liệu nhưng truy vấn lọc hết | Trả về 0 bản ghi | Không chạy | Không chạy | Xác minh điều kiện truy vấn và chính sách “không có kết quả” |

### Quy ước quan trọng của ItemReader

Đối với `ItemReader<T>`, giá trị trả về `null` từ `read()` có ý nghĩa **hết dữ liệu (end of input)**:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Vì vậy, không thể dùng `null` như một item hợp lệ phát ra từ reader theo hợp đồng chuẩn. Nếu bản ghi nghiệp vụ có một trường trống, reader nên trả về một đối tượng, ví dụ `new OrderRow(id, null, amount)`, rồi để processor hoặc validator quyết định xử lý trường đó. Trong khi đó, `ItemProcessor.process()` trả về `null` lại có nghĩa **lọc bỏ item hiện tại**, không phải kết thúc nguồn.

Sự khác biệt này ảnh hưởng đến số đếm và logic test. Một step đọc 10 item rồi lọc hết vẫn có `readCount=10`, khác với step gặp EOF ngay lập tức có `readCount=0`.

## 3. Dữ liệu biên ở cấp số lượng bản ghi

Giả sử step dùng chunk size `3`. Không nên chỉ test bộ dữ liệu có 9 hoặc 12 dòng. Những kích thước sau bắt được các lỗi phổ biến ở ranh giới chunk:

| Số item đầu vào | Mục tiêu kiểm tra |
| ---: | --- |
| 0 | Nguồn rỗng, kết thúc ngay |
| 1 | Chỉ có một item, vẫn phải ghi được |
| 2 | Chưa đủ một chunk |
| 3 | Vừa đúng một chunk |
| 4 | Một chunk đầy và một chunk cuối chỉ có 1 item |
| 6 | Vừa đúng hai chunk |
| 7 | Hai chunk đầy và một chunk dư |
| N rất lớn | Hành vi với dữ liệu thực tế, tài nguyên, hiệu suất và tính ổn định |

Nếu `N` item đều hợp lệ, không có filter/skip/retry và writer hoạt động chính xác, kỳ vọng là:

```text
readCount = N
filterCount = 0
writeCount = N
Số item đầu ra = N
```

**Không nên mặc định `commitCount = ceil(N / chunkSize)`.** Một chunk-oriented step có thể có giao dịch phục vụ việc phát hiện EOF hoặc thay đổi hành vi do cấu hình và phiên bản framework. Khi mục tiêu là kiểm thử dữ liệu đầu vào/đầu ra, hãy tập trung vào số item thực đọc, lọc, ghi và đầu ra nghiệp vụ.

Ngoài chunk size, cần kiểm tra ranh giới của **page size**, số phần tử của partition, giới hạn tối đa cho một request và trường hợp bản ghi cuối cùng nằm đúng cuối file/trang.

## 4. Chuẩn bị môi trường kiểm thử

Với dự án dùng Spring Boot 3.x, Spring Batch 5.x và JUnit 5, có thể cấu hình các dependency cho test như sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Trong môi trường integration test:

1. Dùng cơ sở dữ liệu độc lập chứa metadata của Spring Batch, chẳng hạn H2.
2. Tắt job tự chạy khi context khởi động bằng `spring.batch.job.enabled=false`.
3. Khởi tạo schema metadata cho cơ sở dữ liệu test bằng `spring.batch.jdbc.initialize-schema=always` khi thích hợp.
4. Dọn metadata giữa các phép thử hoặc dùng database độc lập để không nhầm lần chạy cũ với lần chạy đang kiểm thử.
5. Đặt dữ liệu test trực tiếp trong fixture hoặc tạo file/database test mới cho từng kịch bản.
6. Truyền `JobParameters` xác định khi gọi job, tránh tham số ngẫu nhiên làm việc quan sát hành vi khó lặp lại.

`@SpringBatchTest` cung cấp các tiện ích hỗ trợ như `JobLauncherTestUtils` và `JobRepositoryTestUtils`. Nếu test cần kiểm soát chính xác job được chạy, có thể tự tiêm `JobLauncher` và `Job` tương ứng, như ví dụ bên dưới.

## 5. Ví dụ integration test với dữ liệu rỗng và kích thước chunk

Ví dụ sử dụng một job nhận danh sách chuỗi từ fixture. Mỗi chuỗi được bỏ khoảng trắng ở hai đầu và chuyển sang chữ hoa; chuỗi chỉ có khoảng trắng bị lọc. Writer ghi dữ liệu vào một đối tượng thu thập kết quả để test kiểm tra. Chunk size được cố định bằng `3` để nhìn rõ các giá trị ranh giới.

Điểm quan trọng là reader được tạo **mới cho mỗi StepExecution** bằng `@StepScope`. Nếu tái sử dụng cùng một `ListItemReader` sau khi đã đọc đến cuối danh sách, những test sau có thể nhìn thấy dữ liệu rỗng giả tạo do trạng thái đọc cũ.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.IntStream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(
    classes = EmptyAndBoundaryDataTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:edge_data_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class EmptyAndBoundaryDataTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("boundaryJob")
    private Job job;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private InputFixture fixture;

    @Autowired
    private OutputProbe outputProbe;

    @BeforeEach
    void resetData() {
        jobRepositoryTestUtils.removeJobExecutions();
        fixture.replace(List.of());
        outputProbe.clear();
    }

    private JobExecution launch(String testCase) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("case", testCase, true)
            .toJobParameters();

        return jobLauncher.run(job, parameters);
    }

    private StepExecution onlyStep(JobExecution execution) {
        assertEquals(1, execution.getStepExecutions().size());
        return execution.getStepExecutions().iterator().next();
    }

    @Test
    void emptySourceProducesNoOutput() throws Exception {
        fixture.replace(List.of());

        JobExecution execution = launch("empty-source");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(0, step.getReadCount());
        assertEquals(0, step.getFilterCount());
        assertEquals(0, step.getWriteCount());
        assertEquals(List.of(), outputProbe.snapshot());
        assertEquals(0, outputProbe.writeCalls());
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3, 4, 6, 7})
    void worksAroundChunkBoundaries(int count) throws Exception {
        List<String> input = IntStream.range(0, count)
            .mapToObj(i -> " item-" + i + " ")
            .toList();
        List<String> expected = IntStream.range(0, count)
            .mapToObj(i -> "ITEM-" + i)
            .toList();

        fixture.replace(input);

        JobExecution execution = launch("count-" + count);
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(count, step.getReadCount());
        assertEquals(0, step.getFilterCount());
        assertEquals(count, step.getWriteCount());
        assertEquals(expected, outputProbe.snapshot());
    }

    @Test
    void sourceWithOnlyWhitespaceFiltersEveryItem() throws Exception {
        fixture.replace(List.of(" ", "", "\t"));

        JobExecution execution = launch("only-whitespace");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(3, step.getReadCount());
        assertEquals(3, step.getFilterCount());
        assertEquals(0, step.getWriteCount());
        assertEquals(List.of(), outputProbe.snapshot());
        assertEquals(0, outputProbe.writeCalls());
    }

    @Test
    void mixedItemsPreserveOnlyValidData() throws Exception {
        fixture.replace(List.of("  apple  ", " ", "banana", ""));

        JobExecution execution = launch("mixed-input");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(4, step.getReadCount());
        assertEquals(2, step.getFilterCount());
        assertEquals(2, step.getWriteCount());
        assertEquals(
            List.of("APPLE", "BANANA"),
            outputProbe.snapshot()
        );
    }

    // Dữ liệu test được thay trước khi mỗi step bắt đầu.
    static class InputFixture {
        private List<String> rows = List.of();

        synchronized void replace(List<String> newRows) {
            rows = List.copyOf(newRows);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(rows);
        }
    }

    // Bản ghi đầu ra và số lần ItemWriter.write được gọi.
    static class OutputProbe {
        private final List<String> written = new ArrayList<>();
        private int calls;

        synchronized void capture(List<? extends String> items) {
            calls++;
            written.addAll(items);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(written);
        }

        synchronized int writeCalls() {
            return calls;
        }

        synchronized void clear() {
            written.clear();
            calls = 0;
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        InputFixture fixture() {
            return new InputFixture();
        }

        @Bean
        OutputProbe outputProbe() {
            return new OutputProbe();
        }

        @Bean
        @StepScope
        ListItemReader<String> edgeReader(InputFixture fixture) {
            return new ListItemReader<>(fixture.snapshot());
        }

        @Bean
        ItemProcessor<String, String> normalizingProcessor() {
            return item -> {
                String value = item.trim();
                return value.isEmpty()
                    ? null
                    : value.toUpperCase(Locale.ROOT);
            };
        }

        @Bean
        ItemWriter<String> capturingWriter(OutputProbe outputProbe) {
            return chunk -> outputProbe.capture(chunk.getItems());
        }

        @Bean
        Step boundaryStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                @Qualifier("edgeReader") ItemReader<String> reader,
                @Qualifier("normalizingProcessor")
                    ItemProcessor<String, String> processor,
                @Qualifier("capturingWriter") ItemWriter<String> writer) {

            return new StepBuilder("boundaryStep", jobRepository)
                .<String, String>chunk(3, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
        }

        @Bean
        Job boundaryJob(
                JobRepository jobRepository,
                @Qualifier("boundaryStep") Step step) {

            return new JobBuilder("boundaryJob", jobRepository)
                .start(step)
                .build();
        }
    }
}
```

### Ý nghĩa các phép thử

**Nguồn hoàn toàn rỗng:** `ListItemReader` trả về `null` ngay lập tức, nên reader không cung cấp item cho processor/writer. Trong ví dụ, job được thiết kế chấp nhận nguồn rỗng; vì vậy `BatchStatus.COMPLETED` là kết quả hợp lệ, đồng thời ba số đếm đều bằng 0.

**Kích thước quanh chunk boundary:** bảng tham số `{0,1,2,3,4,6,7}` chứng minh cả chunk chưa đầy, chunk vừa đủ và chunk cuối có phần dư vẫn ghi đúng tổng số item và đúng thứ tự.

**Dữ liệu chỉ có khoảng trắng:** reader đã đọc 3 item nhưng processor trả về `null` ở cả 3 lần. `readCount=3` và `filterCount=3` giúp phát hiện tình trạng “không ghi gì” là do filter, thay vì do nguồn không có dữ liệu.

**Dữ liệu hợp lệ và bị lọc xen kẽ:** kiểm tra không chỉ số lượng mà cả nội dung đầu ra, bảo đảm bản ghi được giữ lại vẫn đúng thứ tự và được chuẩn hóa như mong đợi.

Ở ví dụ này, `OutputProbe` dùng bộ nhớ để phép thử dễ quan sát. Khi kiểm thử job thật, hãy xác nhận dữ liệu tại bảng đích, file xuất hoặc thông điệp được ghi. Nếu ghi dữ liệu trong cùng transaction với chunk, bạn còn cần test rollback khi writer gặp lỗi.

## 6. Dữ liệu rỗng đối với từng loại nguồn

### 6.1. File CSV hoặc văn bản

Các fixture nên được tách rõ:

```text
empty.csv             -> 0 byte
header-only.csv       -> id,amount\n
blank-lines.csv       -> các dòng trống hoặc chứa khoảng trắng
valid-one-row.csv     -> header + 1 bản ghi
missing-file.csv      -> đường dẫn không tồn tại
malformed-row.csv     -> bản ghi thiếu cột hoặc sai kiểu
```

Với `FlatFileItemReader`:

- **File tồn tại nhưng rỗng:** reader thường không đọc được item nào, step có thể `COMPLETED` nếu nghiệp vụ chấp nhận.
- **File chỉ có header:** khi cấu hình bỏ qua một dòng header, kết quả cũng là 0 item; cần kiểm tra rằng header được xử lý đúng và không bị ghi thành bản ghi nghiệp vụ.
- **File không tồn tại:** với `strict=true` (mặc định), reader có thể báo lỗi khi mở tài nguyên; với `strict=false`, nó có thể xem nguồn không tồn tại như đầu vào rỗng. Quy tắc mong muốn phải được quy định rõ.
- **Dòng trống:** tùy `RecordSeparatorPolicy`, `LineMapper` và logic xử lý, dòng trống có thể bị bỏ qua hoặc gây lỗi ánh xạ. Không giả định rằng dòng trống và EOF là cùng một sự kiện.
- **Dòng cuối không có ký tự xuống dòng:** vẫn cần được đọc như một bản ghi nếu nội dung hợp lệ.

Ví dụ cấu hình nhấn mạnh chính sách file thiếu:

```java
FlatFileItemReader<OrderRow> reader = new FlatFileItemReaderBuilder<OrderRow>()
    .name("orderCsvReader")
    .resource(new FileSystemResource("test-data/orders.csv"))
    .linesToSkip(1)
    .delimited()
    .names("id", "amount")
    .fieldSetMapper(fieldSet -> new OrderRow(
        fieldSet.readLong("id"),
        fieldSet.readBigDecimal("amount")
    ))
    .strict(true)
    .build();
```

Fixture dùng cho test nên được tạo trong thư mục tạm của JUnit, hoặc từ tài nguyên test được quản lý rõ. Tránh dùng đường dẫn làm việc phụ thuộc vào máy lập trình.

### 6.2. Database

Với `JdbcCursorItemReader` hoặc `JdbcPagingItemReader`, truy vấn trả về 0 dòng là một kết quả hợp lệ ở cấp JDBC. Tuy nhiên, câu SQL sai hoặc kết nối lỗi phải được phân biệt với kết quả rỗng.

Bộ test nên bao gồm:

- Bảng không có hàng.
- Bảng có hàng nhưng mệnh đề `WHERE` không khớp.
- Kết quả đúng 1 hàng, đúng page size, hơn page size một hàng.
- Trường nullable chứa `NULL`, tách biệt khỏi trường hợp không có hàng.
- Trường `VARCHAR`, `DECIMAL` hoặc ngày tháng ở giá trị cực đại/cực tiểu theo schema.
- Với paging reader, dữ liệu có khóa sắp xếp rõ ràng và duy nhất để tránh thiếu hoặc lặp bản ghi khi phân trang.

Khi tạo fixture bằng SQL, cần kiểm tra cả số hàng ở bảng nguồn trước khi job chạy và số hàng ở bảng đích sau khi job kết thúc. Chỉ kiểm tra `COMPLETED` có thể bỏ sót lỗi lọc toàn bộ dữ liệu ngoài ý muốn.

### 6.3. API hoặc message queue

Nguồn ngoài có thể trả về danh sách rỗng hợp lệ, HTTP `204 No Content`, trang cuối không có phần tử, lỗi mạng hoặc rate limit. Mỗi trường hợp có ý nghĩa khác nhau. Test reader/adapter phải định nghĩa rõ điều kiện nào có nghĩa “không còn dữ liệu” và điều kiện nào yêu cầu retry hoặc fail.

Với API phân trang, đừng kết thúc vòng đọc chỉ vì một trang rỗng nếu hợp đồng của API còn `nextPageToken`. Cần dựa vào quy tắc kết thúc thật của nguồn dữ liệu.

## 7. Giá trị biên của từng trường dữ liệu

Ngoài số lượng item, hãy xây dựng test data cho các giá trị tại ranh giới nghiệp vụ và ranh giới lưu trữ.

Ví dụ với yêu cầu: mã đơn hàng dài từ 1 đến 20 ký tự, số tiền lớn hơn 0 và không vượt quá 10.000.000.

| Trường | Dữ liệu test | Kết quả mong đợi |
| --- | --- | --- |
| `orderCode` | `""` và `"   "` | Bị từ chối hoặc lọc theo chính sách |
| `orderCode` | Độ dài 1 | Hợp lệ nếu các điều kiện khác đạt |
| `orderCode` | Độ dài 20 | Hợp lệ tại ngưỡng trên |
| `orderCode` | Độ dài 21 | Không hợp lệ; không được cắt âm thầm |
| `amount` | `null` | Không hợp lệ nếu bắt buộc |
| `amount` | `-0.01`, `0` | Không hợp lệ |
| `amount` | `0.01` | Giá trị hợp lệ nhỏ nhất theo đơn vị tiền tệ giả định |
| `amount` | `10000000.00` | Hợp lệ tại ngưỡng trên |
| `amount` | `10000000.01` | Không hợp lệ |
| Ngày nghiệp vụ | Trước ngày bắt đầu, đúng ngày bắt đầu, đúng ngày kết thúc, sau ngày kết thúc | Xác minh ranh giới bao gồm hay không bao gồm |
| Số nguyên | `Integer.MIN_VALUE`, `0`, `Integer.MAX_VALUE` | Xử lý theo miền giá trị và tránh tràn số |

Một validator minh họa cho tiền tệ:

```java
import java.math.BigDecimal;

static void validateAmount(BigDecimal amount) {
    BigDecimal min = new BigDecimal("0.00");
    BigDecimal max = new BigDecimal("10000000.00");

    if (amount == null ||
        amount.compareTo(min) <= 0 ||
        amount.compareTo(max) > 0) {
        throw new IllegalArgumentException("Invalid amount");
    }
}
```

Việc dùng `BigDecimal.compareTo` giúp so sánh giá trị số học nhất quán, tránh lỗi so sánh `double` ở ngưỡng. Đối với chuỗi Unicode, quy tắc “20 ký tự” cần được diễn đạt rõ: độ dài Java `String.length()` đếm đơn vị UTF-16, có thể khác số code point hiển thị. Nếu yêu cầu nghiệp vụ tính theo code point, validator phải dùng cách đếm tương ứng.

Cũng nên kiểm tra khoảng trắng đầu/cuối, ký tự xuống dòng, dấu phân cách CSV, ký tự có dấu và BOM (nếu nguồn có thể chứa). Những giá trị này có thể khiến parser trả về trường rỗng hoặc số cột sai dù file không hề rỗng.

## 8. Ngưỡng skip, retry và chính sách dữ liệu lỗi

Đối với step fault tolerant, các ranh giới số lượng cần kiểm tra theo **giới hạn cấu hình**, không chỉ theo chunk size.

Ví dụ:

```java
Step step = new StepBuilder("importStep", jobRepository)
    .<OrderRow, OrderRow>chunk(10, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(IllegalArgumentException.class)
    .skipLimit(2)
    .build();
```

Với `skipLimit(2)`, số lỗi thuộc loại được skip trong phạm vi cho phép tối đa là 2; lỗi thứ 3 cùng loại trong step sẽ làm vượt giới hạn skip và thường khiến step thất bại. Ma trận test nên có:

| Số bản ghi gây lỗi skip được cấu hình | Kỳ vọng |
| ---: | --- |
| 0 | Thành công, không có skip |
| 1 | Thành công, đếm đúng 1 skip |
| 2 | Thành công, vừa đạt ngưỡng cho phép |
| 3 | Vượt giới hạn, step thất bại |

Cần kiểm tra `readSkipCount`, `processSkipCount` hoặc `writeSkipCount` tùy lỗi phát sinh ở đâu. Đừng chỉ kiểm tra tổng `skipCount`; số đếm theo giai đoạn giúp xác định bản ghi bị loại ở bước đọc, xử lý hay ghi.

**Filter khác skip.** Processor trả về `null` để loại bản ghi theo quy tắc nghiệp vụ làm tăng `filterCount`; nó không tự động tiêu thụ `skipLimit`. Nếu cần báo cáo bản ghi không hợp lệ như skip, phải thiết kế processor/exception và fault-tolerance policy tương ứng.

Với retry, hãy kiểm thử tại các mốc trước, đúng và sau giới hạn nỗ lực được cấu hình, đồng thời xác định rõ exception nào được retry. Kiểm tra dữ liệu đích để tránh ghi trùng nếu một lần thực thi thất bại sau khi đã gây ra tác động ở hệ thống bên ngoài.

## 9. Trạng thái job khi không có dữ liệu là quyết định nghiệp vụ

Không nên tự động xem `readCount=0` là lỗi. Có ít nhất ba cách xử lý hợp lý:

| Ngữ cảnh | Chính sách phù hợp | Assertion quan trọng |
| --- | --- | --- |
| Báo cáo hàng ngày, ngày đó không có giao dịch | Hoàn tất bình thường với tập kết quả rỗng | `COMPLETED`, `readCount=0`, file hoặc bảng đích có trạng thái mong đợi |
| Import file bắt buộc phải có ít nhất một đơn hàng | Báo lỗi kiểm tra dữ liệu | `FAILED` hoặc mã thoát nghiệp vụ xác định, không tạo dữ liệu đích sai |
| Job đồng bộ chỉ cần hành động khi có bản ghi mới | Không ghi gì và hoàn tất | `COMPLETED`, writer không tạo tác động phụ không cần thiết |

Nếu muốn phân biệt “hoàn tất vì không có dữ liệu” với “hoàn tất sau khi xử lý dữ liệu”, có thể dùng `StepExecutionListener` để đặt một `ExitStatus` nghiệp vụ, chẳng hạn `NO_DATA`, rồi cấu hình flow tương ứng. Cần nhớ rằng `ExitStatus` và `BatchStatus` là hai khái niệm khác nhau; không giả định gán một exit code tùy biến sẽ tự động đổi batch status thành `FAILED`.

Với job sản xuất, chính sách này nên được ghi thành yêu cầu kiểm thử cụ thể: dữ liệu rỗng có hợp lệ hay không, có tạo file đầu ra rỗng hay không, có gửi thông báo không, và job có được phép restart không.

## 10. Kiểm tra metadata và kết quả nghiệp vụ

Để phép thử phát hiện lỗi thật, nên quan sát hai lớp.

**Lớp Spring Batch:** lấy `JobExecution` và `StepExecution`, kiểm tra:

```java
assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions()
    .iterator()
    .next();

assertEquals(expectedReadCount, step.getReadCount());
assertEquals(expectedFilterCount, step.getFilterCount());
assertEquals(expectedWriteCount, step.getWriteCount());
```

**Lớp nghiệp vụ:** kiểm tra bản ghi được thêm/cập nhật trong database, nội dung và số dòng của file xuất, danh sách message đã phát hoặc tổng giá trị sau xử lý. Hai bộ dữ liệu có cùng số lượng đầu ra vẫn có thể khác nhau về nội dung, thứ tự, khóa hoặc giá trị tính toán.

Ví dụ, với dữ liệu đầu vào `["A", "", "B"]` và policy lọc chuỗi rỗng, kết quả đúng không chỉ là `writeCount=2` mà còn là đầu ra đúng `["A", "B"]`. Trường hợp `["A", "A"]` vẫn có 2 item nhưng là lỗi nghiệp vụ.

Ngoài ra, nên phân biệt:

- `readCount`: số item reader đọc thành công và cung cấp cho quá trình xử lý.
- `filterCount`: số item processor lọc bằng cách trả về `null`.
- `writeCount`: số item được tính là đã ghi bởi writer.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: số lần skip theo giai đoạn.
- `commitCount` và `rollbackCount`: hữu ích khi phân tích giao dịch, nhưng không phải chỉ dấu duy nhất để xác minh số item thực tế ở đầu ra.

Khi có retry, rollback hoặc writer thực hiện side effect ngoài transaction, hãy ưu tiên xác minh trạng thái cuối của dữ liệu đích. Metadata có thể ghi lại một diễn biến xử lý mà chưa đủ để chứng minh không có dữ liệu trùng ở hệ thống bên ngoài.

## 11. Những lỗi thường gặp khi kiểm thử dữ liệu rỗng và biên

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Test nguồn rỗng vẫn thấy dữ liệu | Reader giữ vị trí/fixture từ test trước, hoặc job tự chạy lúc startup | Tạo reader mới cho mỗi execution, reset fixture, tắt auto-run |
| Test báo thành công dù thiếu dữ liệu bắt buộc | Job chấp nhận EOF như kết thúc bình thường | Thiết kế chính sách rỗng và assertion cho `readCount=0` |
| Không phân biệt all-filtered với nguồn rỗng | Chỉ assert `writeCount=0` | Kiểm tra `readCount` và `filterCount` |
| Bản ghi cuối bị mất | Logic xử lý chunk cuối, paging hoặc flush không đúng | Test `chunkSize-1`, `chunkSize`, `chunkSize+1` |
| File thiếu bị coi như file rỗng | Reader dùng `strict=false` ngoài ý muốn | Kiểm tra riêng trường hợp đường dẫn không tồn tại |
| File chỉ có header bị parse thành một item | Cấu hình `linesToSkip` hoặc mapper sai | Tạo fixture header-only và assert reader trả 0 item |
| Test chạy đơn lẻ đúng nhưng chạy suite sai | Metadata và bảng test dùng chung | Cô lập DB hoặc dọn dữ liệu giữa test |
| Số dòng ghi đúng nhưng dữ liệu sai | Chỉ kiểm tra số đếm, không kiểm tra nội dung | Assert bản ghi cụ thể, thứ tự và các ranh giới giá trị |
| Test ngưỡng skip sai | Nhầm `filterCount` với `skipCount` | Kiểm tra loại exception và số đếm từng giai đoạn |
| Biên số tiền bị sai | Dùng `double` hoặc điều kiện so sánh thiếu dấu bằng | Dùng `BigDecimal` và test sát hai phía của ngưỡng |

## 12. Bài tập thực hành

Hãy tạo một job đọc `OrderRow(orderCode, amount)`, loại những dòng trắng và từ chối đơn hàng có `amount <= 0` hoặc `amount > 10000000`. Writer ghi các đơn hàng hợp lệ vào bảng H2 `accepted_orders`.

Chuẩn bị ít nhất các bộ dữ liệu: nguồn 0 bản ghi; nguồn 1 bản ghi hợp lệ; nguồn có 2, 3 và 4 bản ghi với chunk size 3; nguồn chỉ toàn dòng bị lọc; số tiền `0`, `0.01`, `10000000.00` và `10000000.01`; cùng với trường hợp file thiếu nếu job đọc từ file.

Với từng bộ, xác định trước kỳ vọng về `BatchStatus`, `readCount`, `filterCount`, `writeCount`, số bản ghi trong `accepted_orders` và dữ liệu cụ thể của những bản ghi được lưu. Nếu áp dụng skip cho lỗi hợp lệ, bổ sung bộ dữ liệu có 0, 1, 2 và 3 bản ghi lỗi khi `skipLimit=2`.

Để tăng độ tin cậy, hãy chạy lại cùng một bộ test nhiều lần với dữ liệu được cô lập, rồi thử thay chunk size từ 3 thành 5. Tính đúng đắn của kết quả nghiệp vụ không được phụ thuộc vào việc bản ghi cuối cùng rơi vào chunk nào.

## 13. Kết luận

Trong Spring Batch, dữ liệu rỗng là một trạng thái đầu vào cần được định nghĩa rõ, còn dữ liệu biên là công cụ để phát hiện lỗi ở ranh giới chunk, paging và các quy tắc nghiệp vụ. Test hiệu quả cần phân biệt **không có item để đọc**, **item được đọc nhưng bị filter**, **item lỗi bị skip** và **item được ghi thành công**. Khi kiểm tra đồng thời số đếm của `StepExecution` với đầu ra thật, bạn sẽ phát hiện được những lỗi mà chỉ assert `COMPLETED` không thể nhận ra.
