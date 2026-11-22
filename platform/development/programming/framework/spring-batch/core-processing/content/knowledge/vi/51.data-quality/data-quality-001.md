# Validate đầu vào trước batch trong Spring Batch

## 1. Vì sao cần validate trước khi chạy batch?

Một batch job thường xử lý lượng dữ liệu lớn: tệp CSV, Excel đã chuyển đổi, message được gom theo lô, dữ liệu API, hoặc bảng staging từ đối tác. Nếu bắt đầu ghi dữ liệu ngay khi nhận được đầu vào, một lỗi đơn giản như **thiếu file, sai header, nhầm ngày nghiệp vụ hoặc dữ liệu chưa tải xong** có thể chỉ được phát hiện sau khi nhiều chunk đã commit.

Ví dụ, job `importOrdersJob` dự kiến nhập các đơn hàng của ngày `2026-11-16`:

```text
input: orders_2026-11-16.csv
expected header: order_id,customer_id,amount
expected businessDate: 2026-11-16
```

Nhưng file nhận được có header `order_id,customer_name,amount`. Nếu reader chỉ mapping theo vị trí mà không kiểm tra contract, job có thể đưa tên khách hàng vào trường mã khách hàng, tạo dữ liệu sai và chỉ báo lỗi ở writer hoặc các bước đối soát sau đó.

**Validate đầu vào trước batch** (*preflight validation*, *input admission*) là tập hợp kiểm tra được thực hiện **trước khi dữ liệu được chấp nhận cho xử lý nghiệp vụ có side effect**. Mục tiêu là:

- Chặn những batch chắc chắn không thể xử lý đúng.
- Phân loại lỗi đầu vào sớm, có thông báo rõ cho nhà cung cấp dữ liệu hoặc người vận hành.
- Tránh đọc/ghi hàng triệu record rồi mới biết file sai cấu trúc hoặc sai kỳ nghiệp vụ.
- Tạo dấu vết có thể truy lại: đầu vào nào đã được kiểm tra, phiên bản nào, quy tắc nào và kết quả ra sao.
- Giúp retry, restart và rerun sử dụng đúng **cùng một snapshot dữ liệu**.

Preflight là một lớp của **data quality**, nhưng không thay thế hoàn toàn validation ở `ItemReader`, `ItemProcessor` hoặc database. Một đầu vào đã qua kiểm tra sơ bộ vẫn có thể chứa record sai nghiệp vụ ở giữa file.

## 2. Phân biệt preflight với validation trong luồng chunk

Spring Batch không tự động kiểm tra mọi contract đầu vào. Mỗi lớp làm một việc khác nhau:

| Lớp | Thời điểm | Kiểm tra điển hình | Phản ứng |
| --- | --- | --- | --- |
| **Job parameters** | Khi job nhận tham số | Thiếu `inputPath`, `businessDate` không hợp lệ, tham số mâu thuẫn | Từ chối cấu hình chạy hoặc đánh dấu failure theo cơ chế launch |
| **Preflight step** | Trước step xử lý dữ liệu | File không có, file rỗng, sai header, checksum, schema, số lượng bất thường | Không cho các step nghiệp vụ tiếp tục |
| **Reader / parser** | Khi đọc từng record | CSV lỗi quoting, số cột sai, không parse được số/ngày | Exception, skip/fail theo policy |
| **Processor** | Khi xử lý từng record | Amount âm, customer không tồn tại, business rule sai | Filter, skip/quarantine, fail hoặc retry có điều kiện |
| **Writer / database** | Khi ghi | Khóa trùng, foreign key, constraint, concurrency | Rollback, retry hoặc fail theo transaction và policy |
| **Post-processing reconciliation** | Sau khi xử lý | Tổng tiền, số dòng, cân đối giữa hai nguồn | Chặn publish, đưa lô vào trạng thái cần điều tra |

Ví dụ, một file có đúng tên, đúng encoding và header chưa chắc mọi dòng đều đúng. Ngược lại, một file chứa một dòng amount âm có thể vẫn được phép xử lý nếu hợp đồng dữ liệu cho phép **quarantine dòng sai và tiếp tục những dòng tốt**.

Vì vậy cần định nghĩa rõ **đầu vào không được phép vào batch** và **item không hợp lệ nhưng có thể xử lý cục bộ**. Tránh dùng cùng một nhãn “invalid” cho mọi lỗi, vì chính sách khôi phục của từng nhóm rất khác nhau.

## 3. Bốn lớp kiểm tra đầu vào thường gặp

### 3.1. Availability và tính hoàn chỉnh của nguồn

Trước tiên phải biết dữ liệu đã sẵn sàng:

- File hoặc object tồn tại tại vị trí được phép truy cập.
- File đã được upload **hoàn tất**, không còn ghi dở.
- Quyền đọc và dung lượng phù hợp; file không rỗng nếu contract yêu cầu có dữ liệu.
- Dung lượng nằm trong giới hạn bảo vệ tài nguyên.
- Có manifest, marker “ready”, checksum hoặc tín hiệu hoàn tất từ hệ thống gửi khi cần.
- Nếu có nhiều file cho một kỳ, danh sách file có đầy đủ và không thiếu thành phần.

Chỉ gọi `Files.exists(path)` rồi bắt đầu đọc chưa đảm bảo dữ liệu ổn định: nguồn có thể thay đổi giữa lúc kiểm tra và lúc reader mở file. Đây là vấn đề **time of check vs time of use (TOCTOU)**.

Với nguồn quan trọng, nên đưa dữ liệu vào một **staging location bất biến** rồi validate và xử lý chính snapshot đó. Upload có thể ghi ra tên tạm, kiểm tra checksum, sau đó công bố manifest hoặc chuyển tên theo thao tác atomic nếu hệ lưu trữ hỗ trợ.

### 3.2. Cấu trúc và định dạng

Một số kiểm tra thường dùng:

- Định dạng thực tế có khớp tên file và contract không?
- Encoding có phải UTF-8, UTF-8 BOM hay encoding khác được cho phép?
- Header và tên cột có chính xác, đúng phiên bản schema và quy tắc phân biệt hoa thường không?
- Số cột, dấu phân cách, escaping, quoting và multiline record có được parser hỗ trợ?
- Trường bắt buộc có mặt và tên cột không bị trùng?
- Kiểu dữ liệu (`BigDecimal`, ngày tháng, boolean) có parse đúng?
- Múi giờ, precision, quy ước dấu thập phân và định dạng ngày được công bố rõ?

Ví dụ contract CSV:

```text
Schema version: orders-v2
Encoding: UTF-8
Header: order_id,customer_id,amount
Delimiter: comma
Date pattern: ISO-8601 nếu có cột ngày
Amount: decimal, dấu chấm thập phân, không có ký hiệu tiền
```

Không parse CSV thực tế bằng `line.split(",")` nếu dữ liệu có thể chứa dấu phẩy bên trong trường được quote hoặc dòng multiline. Dùng parser hiểu CSV (như `FlatFileItemReader` với tokenizer phù hợp, hoặc thư viện CSV chuyên dụng). Ví dụ kiểm tra header bằng so sánh chuỗi ở phần sau có phạm vi hẹp: nó **chỉ xác minh header của contract đã cố định**, không thay thế parse toàn bộ CSV.

### 3.3. Chất lượng và quy tắc nghiệp vụ

Các ví dụ:

- `order_id` không được rỗng và không lặp nếu mỗi đơn chỉ được có một event.
- `amount > 0`, đơn vị tiền và làm tròn đúng quy tắc.
- `businessDate` nằm trong kỳ batch đã chọn.
- `customer_id` tồn tại hoặc có trạng thái hợp lệ tại thời điểm chốt.
- Các tổng control total trong manifest khớp với dữ liệu thực.
- Tỷ lệ record lỗi không vượt ngưỡng chấp nhận; các trường hợp không được chấp nhận tuyệt đối phải bằng 0.

Một số quy tắc cần đọc toàn bộ file, join với database hoặc kiểm tra nhiều nguồn. Khi dữ liệu lớn, việc quét toàn bộ **trước** khi xử lý có thể tăng gấp đôi I/O. Có thể chọn staging + một lượt validation, hoặc kết hợp validation trong chunk và chặn bước publish cuối. Lựa chọn phụ thuộc yêu cầu atomicity và hậu quả của dữ liệu sai.

### 3.4. Đúng phiên bản, đúng kỳ, không xử lý lặp

Một file có thể hợp lệ về nội dung nhưng **đã được xử lý cho cùng batch**. Cần phân biệt:

- **Duplicate source:** cùng `sourceId`/checksum/manifest được gửi lại.
- **Rerun có chủ đích:** vận hành muốn xử lý lại một kỳ sau khi sửa lỗi.
- **Restart:** cùng một `JobInstance` thất bại, tiếp tục từ checkpoint.
- **New version:** nhà cung cấp gửi cùng business date nhưng version mới với nội dung khác.

Nên có định danh đầu vào ổn định, ví dụ `sourceSystem + businessDate + fileVersion` hoặc checksum có contract rõ. Đừng dùng mỗi tên file để quyết định trùng, vì file cùng tên có thể bị thay nội dung.

## 4. Kiến trúc preflight cho một batch job

```text
Producer / SFTP / Object Storage
           |
           v
    Upload vào staging
           |
           v
    Manifest / ready marker
           |
           v
     JobParametersValidator
       - đủ inputPath?
       - businessDate hợp lệ?
       - version hợp lệ?
           |
           v
     preflightStep (Tasklet)
       - tồn tại, có thể đọc?
       - header/schema/checksum?
       - sẵn sàng, đúng kỳ?
           |
           +---- INVALID --> FAILED / REJECTED + audit
           |
           v
      importDataStep
       Reader -> Processor -> Writer
           |
           v
   reconcile / quality gate
           |
           +---- FAIL --> không publish
           |
           v
   publish / confirm completion
```

Trong mô hình trên, `preflightStep` là **step đầu tiên**. Nếu nó thất bại, Spring Batch không chạy các step xử lý theo luồng tuần tự mặc định. Các lỗi validation record cụ thể vẫn được xử lý ở `importDataStep` theo policy riêng.

Một sự khác biệt vận hành quan trọng: **JobParametersValidator** là validation của các tham số cấu hình job; **preflightStep** là công việc có thể truy vết trong `StepExecution`. Một job không nên đưa mọi thao tác I/O tốn kém vào `JobParametersValidator` nếu muốn có lịch sử từng lần kiểm tra, metrics và trạng thái step rõ ràng.

## 5. JobParametersValidator: bắt lỗi tham số càng sớm càng tốt

Giả sử job yêu cầu:

| Tham số | Bắt buộc | Ví dụ |
| --- | --- | --- |
| `inputPath` | Có | `/staging/orders_2026-11-16.csv` |
| `businessDate` | Có | `2026-11-16` |
| `schemaVersion` | Có | `orders-v2` |
| `sourceId` | Có | `supplier-a:2026-11-16:v2` |

Triển khai validator đơn giản với **Spring Batch 5.x**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters params)
            throws JobParametersInvalidException {

        if (params == null) {
            throw new JobParametersInvalidException(
                    "JobParameters is required");
        }

        require(params, "inputPath");
        require(params, "sourceId");

        String schemaVersion = require(params, "schemaVersion");
        if (!"orders-v2".equals(schemaVersion)) {
            throw new JobParametersInvalidException(
                    "Unsupported schemaVersion: " + schemaVersion);
        }

        String businessDate = require(params, "businessDate");
        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use ISO yyyy-MM-dd");
        }
    }

    private static String require(JobParameters params, String name)
            throws JobParametersInvalidException {
        String value = params.getString(name);
        if (value == null || value.isBlank()) {
            throw new JobParametersInvalidException(
                    "Missing required parameter: " + name);
        }
        return value;
    }
}
```

Validator trên chỉ xử lý điều kiện **có thể kiểm tra bằng tham số**: có giá trị, đúng format, đúng schema version. Nó không mở file; việc mở và kiểm tra kích thước/header được đưa vào preflight step sau đó.

**Lưu ý:** xác thực `inputPath` chưa dừng ở “không rỗng”. Trong ứng dụng production, cần đảm bảo đường dẫn hoặc object key thuộc phạm vi source được phép, tránh nhận đường dẫn tùy ý từ bên ngoài để đọc file nhạy cảm.

### Gắn validator vào Job

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step importDataStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(new ImportJobParametersValidator())
            .start(preflightStep)
            .next(importDataStep)
            .build();
}
```

Trong Spring Batch 5.x, `JobBuilder` đến từ `org.springframework.batch.core.job.builder.JobBuilder`, `JobRepository` thuộc `org.springframework.batch.core.repository.JobRepository` và `Step` thuộc `org.springframework.batch.core.Step`. Ví dụ giả định `preflightStep` và `importDataStep` đã được định nghĩa trong Spring context.

Khi validation tham số thất bại, không nên giả định luôn có một `StepExecution` thất bại: step chưa được khởi chạy. Kết quả quan sát được ở phía launcher và repository phụ thuộc đường gọi và cách framework quản lý execution; API điều phối nên bắt và báo lỗi tham số rõ ràng.

## 6. Preflight step: kiểm tra file trước khi reader chạy

Với Spring Batch, cách dễ quan sát là tạo một `TaskletStep` đứng đầu flow.

### 6.1. Viết service validate nguồn

Ví dụ preflight chỉ chấp nhận file CSV có header cố định, dung lượng từ 1 byte đến 250 MB. Dự án chạy Java 17 trở lên:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Component;

@Component
public class CsvInputPreflight {

    private static final long MAX_SIZE = 250_000_000L;
    private static final String EXPECTED_HEADER =
            "order_id,customer_id,amount";

    public void validate(Path input) throws IOException {
        Path actual = input.toRealPath();

        if (!Files.isRegularFile(actual) || !Files.isReadable(actual)) {
            throw new IllegalArgumentException(
                    "Input must be a readable regular file");
        }

        long size = Files.size(actual);
        if (size == 0 || size > MAX_SIZE) {
            throw new IllegalArgumentException(
                    "Input size is outside permitted range: " + size);
        }

        try (BufferedReader reader =
                     Files.newBufferedReader(actual, StandardCharsets.UTF_8)) {
            String header = reader.readLine();

            if (header == null) {
                throw new IllegalArgumentException("Missing CSV header");
            }
            if (header.startsWith("\uFEFF")) {
                header = header.substring(1); // UTF-8 BOM
            }
            if (!EXPECTED_HEADER.equals(header)) {
                throw new IllegalArgumentException(
                        "Unexpected CSV header");
            }
        }
    }
}
```

Điểm đáng chú ý:

- `toRealPath()` làm lộ lỗi nguồn không tồn tại và resolve đường dẫn/symlink thành đường dẫn thực; **không tự tạo sandbox** hay tự bảo vệ khỏi các thay đổi sau kiểm tra.
- `isRegularFile` loại trừ nhiều nguồn không phải file thông thường, như directory.
- Kích thước giới hạn giúp ngăn một lô không chủ đích quá lớn chiếm tài nguyên.
- Đọc header qua `BufferedReader` không nạp toàn bộ file vào bộ nhớ.
- Đoạn xử lý BOM hỗ trợ một biến thể phổ biến của UTF-8.
- `IOException` và `IllegalArgumentException` được đẩy lên step để hệ thống có thể báo failure.

Đây là **preflight cấu trúc tối thiểu**. Nó không xác minh record count, quoted CSV, kiểu dữ liệu của mỗi dòng, checksum hay khả năng một uploader đang thay đổi file. Các yêu cầu đó cần mở rộng bằng parser, manifest và cơ chế staging tương ứng.

Một file có header đúng nhưng chỉ chứa header sẽ đi qua điều kiện size > 0. Nếu contract yêu cầu ít nhất một record, phải kiểm tra sự tồn tại của record hợp lệ hoặc so sánh số bản ghi trong manifest, thay vì coi file có byte là đủ.

### 6.2. Gắn service vào Tasklet bằng StepScope

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

import java.nio.file.Path;

@Bean
@StepScope
Tasklet preflightTasklet(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        CsvInputPreflight preflight) {

    return (contribution, chunkContext) -> {
        preflight.validate(Path.of(inputPath));
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` là cần thiết ở ví dụ này để tham số `inputPath` được resolve **khi step chạy**, thay vì lúc Spring tạo bean trong quá trình khởi động ứng dụng.

Nếu `validate(...)` ném exception, Tasklet không trả `RepeatStatus.FINISHED`. Step được báo lỗi theo cơ chế thực thi thông thường; các step theo sau `.next(...)` sẽ không được chạy trong flow tuần tự thành công. Nếu mọi kiểm tra qua, Tasklet kết thúc và import step được phép bắt đầu.

### 6.3. Định nghĩa preflightStep

```java
@Bean
Step preflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet preflightTasklet) {

    return new StepBuilder("preflightStep", jobRepository)
            .tasklet(preflightTasklet, transactionManager)
            .build();
}
```

Các import liên quan đến Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.transaction.PlatformTransactionManager;
```

Tasklet có thể kiểm tra checksum, schema, manifest hoặc gọi service quản lý source, nhưng nên giữ preflight **read-only** hoặc ghi audit theo cơ chế rõ ràng. Tránh biến một bước kiểm tra thành nơi âm thầm sửa dữ liệu nguồn, vì điều đó làm khó xác định snapshot nào đã được kiểm tra.

## 7. Khi nào cần quét toàn bộ file?

Preflight có thể nhẹ hoặc đầy đủ; quyết định này ảnh hưởng độ trễ và chi phí.

| Loại kiểm tra | Có thể làm nhanh trên metadata/header? | Có cần đọc toàn bộ không? |
| --- | --- | --- |
| File tồn tại/quyền đọc | Có | Không |
| Kích thước/tên/extension | Có | Không |
| Header và schema version | Thường có | Không |
| Checksum SHA-256 | Không nếu chưa có checksum đáng tin cậy từ hệ lưu trữ | Thường phải đọc toàn bộ byte |
| Số dòng thực tế | Không | Có hoặc cần manifest/metadata đáng tin cậy |
| Mọi row đều parse được | Không | Có |
| Duplicate business key trong file | Không | Có, thường cần tập key hoặc external index |
| Tổng tiền đối soát | Không | Có |
| Cross-file referential integrity | Không | Có hoặc cần join/staging |

Nếu yêu cầu “không được ghi bất kỳ dữ liệu nghiệp vụ nào trước khi biết toàn lô hợp lệ”, một lượt full validation trước import có thể cần thiết. Nếu chấp nhận dữ liệu tốt và quarantine dữ liệu lỗi, validation theo chunk thường tiết kiệm I/O hơn.

### 7.1. Lựa chọn A: preflight nhẹ + validation trong batch

Phù hợp với:

- Dữ liệu rất lớn.
- Chấp nhận skip hoặc quarantine một số record.
- Output có thể được đối soát và publish có điều kiện.
- Reader/processor/writer được thiết kế idempotent.

Luồng:

```text
Metadata/header preflight -> chunk import -> row validation
                           -> skip/quarantine có kiểm soát
                           -> reconcile -> publish nếu đạt chất lượng
```

### 7.2. Lựa chọn B: full validation rồi mới import

Phù hợp với:

- Lô tài chính phải “all-or-nothing” ở cấp nghiệp vụ.
- Sai một record là không được xử lý cả lô.
- Nguồn có số liệu đối soát bắt buộc.
- Chi phí phát hiện lỗi muộn rất cao.

Luồng:

```text
Staging file bất biến -> validate 100% -> kết quả VALIDATED
                  -> import/publish hoặc REJECTED
```

Đánh đổi: quét dữ liệu hai lần, tiêu tốn I/O và thời gian. Với các pipeline lớn, có thể đọc một lần vào **bảng staging** và kiểm tra trên staging, sau đó chuyển dữ liệu đã qua kiểm tra sang bảng nghiệp vụ trong transaction/phương thức publish được thiết kế rõ.

## 8. Checksum, manifest và tính bất biến của đầu vào

Trong batch tích hợp nhiều hệ thống, điều kiện “file tồn tại” thường quá yếu. Một contract nguồn có thể gồm:

```json
{
  "sourceId": "supplier-a:2026-11-16:v2",
  "businessDate": "2026-11-16",
  "schemaVersion": "orders-v2",
  "dataObject": "orders_2026-11-16_v2.csv",
  "recordCount": 150000,
  "sha256": "a9b8...example..."
}
```

Trong ví dụ, trường `sha256` là **giá trị minh họa bị rút gọn**, không phải checksum hợp lệ để đưa vào code. Với manifest thực, checksum phải có đầy đủ giá trị và đến từ nguồn đáng tin cậy.

Các bước:

1. Producer tải dữ liệu vào staging chưa công bố.
2. Producer tính checksum, record count và phát manifest/ready marker khi upload hoàn tất.
3. Consumer kiểm tra quyền truy cập, phiên bản schema, số bản ghi, checksum (khi có) và business date.
4. Consumer đóng dấu nguồn đã được **VALIDATED** theo `sourceId`/checksum.
5. Import step đọc **đúng bản dữ liệu đã được validate**, không tự lấy “file mới nhất” lúc chạy.

### Kiểm tra hash có ý nghĩa gì?

SHA-256 giúp phát hiện byte của file đã khác với giá trị manifest. Nó không chứng minh dữ liệu đúng nghiệp vụ và không tự chứng minh manifest đến từ nguồn đáng tin. Nếu attacker có thể thay cả file lẫn manifest, cần authentication, quyền truy cập và cơ chế ký/xác thực nguồn phù hợp.

Ví dụ JDK tính checksum theo stream, tránh nạp toàn bộ file vào RAM:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.io.IOException;
import java.util.HexFormat;

public static String sha256(Path path)
        throws IOException, NoSuchAlgorithmException {

    MessageDigest digest = MessageDigest.getInstance("SHA-256");

    try (InputStream stream = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = stream.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return HexFormat.of().formatHex(digest.digest());
}
```

Checksum phải được tính trên **đúng byte stream** mà importer sẽ dùng. Nếu chuyển encoding, giải nén hoặc normalize file giữa lúc kiểm tra và xử lý, hãy chỉ rõ checksum áp dụng cho bản gốc hay bản sau biến đổi.

### Ngăn TOCTOU

```text
10:00:00 validate /inbox/orders.csv -> OK
10:00:03 producer ghi đè file cũ
10:00:05 reader mở /inbox/orders.csv -> nội dung khác
```

Việc kiểm tra metadata một lần rồi mở file sau đó chưa đủ. Cách đáng tin hơn là dùng object version/ETag, snapshot immutable hoặc copy sang tên nhận diện bằng checksum và quyền ghi phù hợp. Nếu không có snapshot, cần xác minh lại ở điểm mở nguồn và biết rằng kiểm tra lại đơn thuần vẫn có race condition.

## 9. Validation record: xử lý invalid item khác với invalid batch

Preflight thất bại vì sai schema thì **không nên import**. Nhưng trong batch một triệu bản ghi, có 5 khách hàng sai mã có thể có chính sách xử lý khác.

Ví dụ rule ở processor:

```java
public ValidatedOrder process(OrderRow row) {
    if (row.amount().signum() <= 0) {
        throw new InvalidOrderDataException(
                "amount must be positive");
    }
    return new ValidatedOrder(
            row.orderId(),
            row.customerId(),
            row.amount());
}
```

Với fault-tolerant step:

```java
new StepBuilder("importDataStep", jobRepository)
        .<OrderRow, ValidatedOrder>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderDataException.class)
        .skipLimit(100)
        .build();
```

`OrderRow`, `ValidatedOrder` và `InvalidOrderDataException` là kiểu dữ liệu của ứng dụng; ví dụ builder giả định các bean được cung cấp đầy đủ. Với một số dữ liệu, chính sách `skipLimit(100)` có thể phù hợp; với giao dịch tài chính bắt buộc đủ 100%, chính sách nên fail và giữ batch ở trạng thái cần đối soát.

**Không biến mọi exception thành skip.** Phải phân biệt lỗi dữ liệu xác định (`InvalidOrderDataException`) với lỗi hệ thống tạm thời (network timeout) và bug chương trình. `skip(Exception.class)` có thể làm job `COMPLETED` nhưng âm thầm mất dữ liệu.

### Filter không phải skip

Một processor trả về `null` để loại record nằm ngoài phạm vi xử lý sẽ làm tăng `filterCount`, không phải `processSkipCount`. Nếu record invalid cần báo cáo, đừng dùng `return null` thay cho exception/audit mà không có quy tắc.

## 10. Quyết định accept, reject hay quarantine

Một chính sách chất lượng phải trả lời **batch tiếp tục được không** và **dữ liệu lỗi sẽ đi đâu**.

| Tình huống | Quyết định ví dụ | Đầu ra cần lưu |
| --- | --- | --- |
| File thiếu | Reject toàn batch | `sourceId`, mã lỗi `INPUT_NOT_FOUND` |
| Sai schema version | Reject toàn batch | Version mong đợi/thực tế |
| Checksum mismatch | Reject, không import | Manifest ID, checksum nhận được |
| Một dòng amount âm, cho phép dữ liệu tốt tiếp tục | Quarantine dòng | Nguồn, số dòng, business key, error code |
| Tổng tiền cuối không khớp control total | Chặn publish hoặc fail quality gate | Expected total, actual total |
| Duplicate source đã hoàn tất | Skip nhận lô hoặc reject theo policy | ID của batch đã xử lý |
| Cùng sourceId nhưng checksum mới | Conflict/revision flow | Version và quyết định phê duyệt |

Không có một ngưỡng lỗi chung phù hợp cho tất cả job. Ví dụ:

```text
file ingestion:
  structuralErrorsAllowed: 0
  invalidRowsAllowed: 50
  invalidRowPercentageAllowed: 0.1%
  missingMandatoryReferencesAllowed: 0
```

Đây là ví dụ **policy nghiệp vụ**, không phải thuộc tính cấu hình mặc định của Spring Batch.

Khi có nhiều ngưỡng, nên áp dụng rõ phép kết hợp, chẳng hạn **reject nếu invalidRows > 50 HOẶC invalidRows / readRows > 0,001**. Với `readRows=0`, cần quy tắc riêng; không được chia cho 0 và diễn giải thành “tỷ lệ lỗi bằng 0%”.

Nếu quyết định phụ thuộc tỷ lệ lỗi trên **toàn bộ lô**, thường phải đọc hết/lưu staging rồi mới xác nhận lô hợp lệ. Dùng skip-limit theo step là cơ chế kỹ thuật cho từng item; nó không tự thay thế một policy chất lượng tổng thể với nhiều điều kiện.

## 11. Thiết kế quality gate trước khi publish

Một batch có thể dùng staging để đảm bảo chỉ publish dữ liệu đạt chất lượng:

```text
                       input snapshot
                             |
                             v
                     preflightStep
                             |
                             v
                     loadStagingStep
                 / valid + invalid rows
                             |
                             v
                   validateStagingStep
                    / total + duplicate
                    / cross-reference
                             |
             +---------------+----------------+
             |                                |
          PASSED                            FAILED
             |                                |
             v                                v
      publishValidatedStep              quarantine/reject
             |
             v
        final output
```

Một quality gate có thể so sánh:

```text
manifest.recordCount = staged.validCount + staged.invalidCount
manifest.controlTotal = staged.validAmountTotal + policy-specific adjustments
duplicateCount <= allowedDuplicateCount
invalidCount <= allowedInvalidCount
```

Các phép đối soát phải được định nghĩa theo business contract: nếu nguồn tính tổng trên mọi dòng, còn job chỉ tính tổng các dòng hợp lệ, hai số đó có thể khác nhau theo quy tắc chấp nhận. Không ép một đẳng thức không đúng nghiệp vụ.

### Hệ quả transaction

Nếu import đã commit nhiều chunk vào **bảng final**, việc phát hiện lỗi ở bước cuối không tự rollback mọi chunk trước đó. Để đạt hiệu ứng “chưa publish khi chưa đạt chất lượng”, có thể lưu vào bảng staging và chỉ chuyển sang trạng thái visible/final khi gate thành công. Quy trình publish cũng cần transaction và cơ chế lặp lại idempotent.

Với object storage hoặc dữ liệu ngoài database, “publish” có thể là cập nhật manifest/marker để downstream chỉ tiêu thụ những object đã được công bố.

## 12. Restart và rerun: đầu vào có được phép thay đổi?

Trong Spring Batch, một `JobInstance` được xác định bởi tên job và các **identifying JobParameters**. Một instance thất bại có thể restart từ checkpoint theo `JobRepository` và `ExecutionContext`.

Ví dụ:

```text
sourceId = supplier-a:2026-11-16:v2
businessDate = 2026-11-16
snapshotSha256 = <hash-of-staged-file>

JobExecution #41: preflight COMPLETED
                  importDataStep FAILED at row 3200

JobExecution #42: restart same JobInstance
                  importDataStep continues from checkpoint
```

Để restart đúng:

1. Nguồn phải giữ **cùng nội dung và thứ tự record** nếu reader khôi phục theo vị trí.
2. Không xóa metadata `JobRepository`/`ExecutionContext` khi cần restart.
3. `businessDate` và cutoff phục vụ logic nghiệp vụ phải ổn định.
4. Writer cần chống duplicate nếu một phần dữ liệu được phát lại.
5. Nếu file buộc phải sửa nội dung, phải có policy cho **version mới và job instance mới** hoặc cơ chế recovery được thiết kế riêng.

### PreflightStep chạy lại khi restart?

Theo mặc định, Spring Batch thường **bỏ qua step đã COMPLETED** khi restart cùng instance, nếu flow và cấu hình cho phép. Vì thế `preflightStep` đã completed ở execution trước không nhất thiết được chạy lại.

Có hai chiến lược:

- **Snapshot bất biến:** preflight xác minh một snapshot/version đã khóa; restart đọc đúng snapshot đó, và không cần kiểm lại toàn bộ file mỗi lần.
- **Revalidate có chủ đích:** cấu hình `allowStartIfComplete(true)` cho preflight step nếu muốn step luôn được chạy lại khi restart. Validation mới phải tương thích với checkpoint và không được vô tình đổi nguồn.

Ví dụ builder:

```java
new StepBuilder("preflightStep", jobRepository)
        .tasklet(preflightTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

Đây là lựa chọn thiết kế, không phải mặc định bắt buộc. Revalidate file không khóa phiên bản có thể phát hiện thay đổi sau khi một phần output đã được commit; đó là lỗi cần xử lý theo chính sách recovery, không nên tự xóa output rồi chạy lại từ đầu.

### Phân biệt duplicate input và duplicate JobInstance

Chỉ cần thay `run.id` có thể tạo một instance mới, nhưng không khiến dữ liệu nghiệp vụ tự động an toàn khi chạy lại. Nếu cùng file được nhập hai lần vào bảng đơn hàng, cần unique constraint/upsert/idempotency key theo **business key** phù hợp. `sourceId` có thể hỗ trợ admission nhưng không thay thế ràng buộc uniqueness ở writer.

## 13. Kiểm thử preflight bằng JUnit

Các test infrastructure nên có cả **unit test service** và **integration test luồng job**.

### 13.1. Unit test validate file bằng @TempDir

JUnit Jupiter có `@TempDir` để tạo thư mục riêng cho từng test. Ví dụ kiểm thử `CsvInputPreflight` ở trên:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CsvInputPreflightTest {

    @TempDir
    Path tempDir;

    private final CsvInputPreflight preflight =
            new CsvInputPreflight();

    @Test
    void acceptsExpectedHeader() throws Exception {
        Path input = tempDir.resolve("orders.csv");
        Files.writeString(
                input,
                "order_id,customer_id,amount\nORD-1,C01,100.00\n",
                StandardCharsets.UTF_8
        );

        assertDoesNotThrow(() -> preflight.validate(input));
    }

    @Test
    void rejectsWrongHeader() throws Exception {
        Path input = tempDir.resolve("wrong-header.csv");
        Files.writeString(
                input,
                "order_id,customer_name,amount\nORD-1,Alice,100.00\n",
                StandardCharsets.UTF_8
        );

        assertThrows(IllegalArgumentException.class,
                () -> preflight.validate(input));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        Path input = tempDir.resolve("empty.csv");
        Files.write(input, new byte[0]);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.validate(input));
    }

    @Test
    void missingFileRaisesIOException() {
        Path input = tempDir.resolve("missing.csv");
        assertThrows(java.io.IOException.class,
                () -> preflight.validate(input));
    }

    @Test
    void acceptsUtf8BomBeforeExpectedHeader() throws Exception {
        Path input = tempDir.resolve("bom.csv");
        Files.writeString(
                input,
                "\uFEFForder_id,customer_id,amount\nORD-1,C01,100.00\n",
                StandardCharsets.UTF_8
        );

        assertDoesNotThrow(() -> preflight.validate(input));
    }
}
```

Những test này xác minh **storage và các điều kiện tối thiểu** của preflight. Chúng không khẳng định mọi record hợp lệ hoặc đảm bảo file không thể thay đổi sau kiểm tra.

### 13.2. Unit test JobParametersValidator

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportJobParametersValidatorTest {

    private final ImportJobParametersValidator validator =
            new ImportJobParametersValidator();

    @Test
    void acceptsValidParameters() {
        var params = new JobParametersBuilder()
                .addString("inputPath", "/staging/orders.csv")
                .addString("sourceId", "supplier-a:2026-11-16:v2")
                .addString("businessDate", "2026-11-16")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(params));
    }

    @Test
    void rejectsInvalidBusinessDate() {
        var params = new JobParametersBuilder()
                .addString("inputPath", "/staging/orders.csv")
                .addString("sourceId", "supplier-a:2026-11-16:v2")
                .addString("businessDate", "16/11/2026")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }
}
```

Đây là unit test của contract tham số; không cần mở file hoặc chạy job. Câu đường dẫn `/staging/orders.csv` là giá trị minh họa và không được truy cập trong test validator.

### 13.3. Integration test: preflight fail thì importer không được ghi

Với Spring Batch 5.x và `spring-batch-test`, cấu hình một job test gồm `preflightStep` và `importDataStep`, output lưu trong database test. Dùng `@SpringBatchTest`, `@SpringBootTest(properties = "spring.batch.job.enabled=false")` và `JobLauncherTestUtils` để điều khiển lần chạy.

Kịch bản:

1. Tạo file CSV có header sai.
2. Khởi chạy job với `inputPath` trỏ tới file đó và các JobParameters hợp lệ khác.
3. Kiểm tra `JobExecution` kết thúc `FAILED`, preflight có `StepExecution.FAILED`.
4. Kiểm tra `importDataStep` **không chạy**, không có bản ghi nghiệp vụ nào được thêm.
5. Thay bằng file hợp lệ, chạy một `JobInstance` mới và xác minh importer chạy.

Ví dụ phần kiểm tra trong test đã cấu hình:

```java
JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
                .addString("inputPath", badCsv.toString())
                .addString("sourceId", "test-invalid-" + UUID.randomUUID())
                .addString("businessDate", "2026-11-16")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters()
);

assertEquals(BatchStatus.FAILED, execution.getStatus());

assertTrue(
        execution.getStepExecutions().stream()
                .anyMatch(s -> s.getStepName().equals("preflightStep")
                        && s.getStatus() == BatchStatus.FAILED)
);

assertTrue(
        execution.getStepExecutions().stream()
                .noneMatch(s -> s.getStepName().equals("importDataStep"))
);

assertEquals(0, countBusinessRows());
```

Đây là **trích đoạn minh họa**: `launcher`, `badCsv` và `countBusinessRows()` phải được khai báo trong lớp test, cùng job/test database thực tế. Test cần cô lập output từ trước để `countBusinessRows()` có ý nghĩa; khi `@SpringBatchTest` và context chứa nhiều job, nhớ gán đúng job cho launcher.

**Lưu ý phiên bản:** Ví dụ cấu hình dùng Spring Batch 5.x. Spring Batch 6 thay đổi một số package và tiện ích khởi chạy test (các ví dụ mới sử dụng `JobOperatorTestUtils`). Điều chỉnh import/API theo phiên bản được dự án sử dụng.

### 13.4. Test data nên có

| Mã | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| V01 | Đủ tham số, file hợp lệ | Preflight hoàn tất, importer được chạy |
| V02 | Thiếu `inputPath` | Validator từ chối |
| V03 | `businessDate` sai định dạng | Validator từ chối |
| V04 | File không tồn tại | Preflight fail |
| V05 | File rỗng | Preflight fail |
| V06 | Header sai | Preflight fail |
| V07 | UTF-8 BOM cho phép | Preflight pass nếu contract cho phép |
| V08 | File có đúng header nhưng record sai | Reader/processor xử lý theo policy |
| V09 | File chưa upload xong | Không đánh dấu READY; từ chối hoặc chờ thông qua orchestration |
| V10 | Checksum khác manifest | Reject không nhập |
| V11 | Cùng `sourceId` được gửi lại | Chấp nhận/từ chối theo idempotency policy |
| V12 | Restart với snapshot không đổi | Tiếp tục đúng checkpoint |
| V13 | Snapshot bị thay giữa hai lần chạy | Phát hiện thay đổi, không nhập lẫn hai version |
| V14 | Control total không cân đối | Chặn publish |

Khi chạy test, kiểm tra **output thực tế** và **trạng thái StepExecution**. `JobExecution.COMPLETED` tự nó không chứng minh lô đã đúng mọi quy tắc chất lượng.

## 14. Logging, audit và monitoring cho validation

Nếu preflight thất bại, log chỉ ghi `IllegalArgumentException` sẽ không đủ cho vận hành. Cần biết:

```text
jobName
jobExecutionId
stepName
stepExecutionId
sourceId
businessDate
schemaVersion
snapshotIdentifier / checksum
validationStage
errorCode
expectedValue (nếu an toàn)
actualValue (nếu an toàn)
```

Ví dụ structured log:

```json
{
  "event": "input_rejected",
  "jobName": "importOrdersJob",
  "stepName": "preflightStep",
  "sourceId": "supplier-a:2026-11-16:v2",
  "validationStage": "schema",
  "errorCode": "HEADER_MISMATCH",
  "schemaVersion": "orders-v2"
}
```

Không đưa toàn bộ payload hoặc đường dẫn nhạy cảm vào log public. Khi log từ một hệ thống nhiều tenant hoặc nhiều môi trường, cần bảo đảm `sourceId` và tham số được ghi đúng phạm vi truy cập.

Các metric ứng dụng có thể định nghĩa:

| Metric | Ý nghĩa |
| --- | --- |
| `batch_input_validation_total{jobName,result,reason}` | Số lần preflight pass/reject theo nhóm lỗi |
| `batch_input_validation_duration_seconds{jobName}` | Thời gian validate đầu vào |
| `batch_input_bytes{jobName}` | Dung lượng nguồn được nhận |
| `batch_invalid_records_total{jobName,reason}` | Số record lỗi theo nhóm hữu hạn |
| `batch_source_age_seconds{jobName}` | Độ trễ từ lúc nguồn sẵn sàng đến lúc nhận |
| `batch_reconciliation_failed_total{jobName}` | Số lần quality gate cuối thất bại |

Những tên trên là **gợi ý metric tùy chỉnh**, không phải tên mặc định của mọi phiên bản Spring Batch/Micrometer. Tránh label `sourceId`, file name, record ID, checksum hoặc exception message nếu cardinality cao; dùng chúng trong log/audit có kiểm soát, còn metric chỉ giữ nhóm hữu hạn.

### Phân biệt lỗi input với lỗi hạ tầng

`INPUT_NOT_FOUND`, `SCHEMA_MISMATCH` và `BUSINESS_DATE_MISMATCH` thường cần liên hệ nguồn dữ liệu. `DATABASE_UNAVAILABLE`, `OBJECT_STORAGE_TIMEOUT` hoặc cấu hình sai thường cần xử lý hạ tầng. Nếu gộp tất cả vào một metric `FAILED`, on-call không biết nên chuyển sự cố cho nhóm nào.

Tốt hơn là phân loại kết quả:

```text
VALID
REJECTED_SOURCE
REJECTED_SCHEMA
REJECTED_BUSINESS_RULE
TRANSIENT_INFRASTRUCTURE_FAILURE
INTERNAL_ERROR
```

Trong Spring Batch, bạn có thể lưu error code trong `ExitStatus` hoặc audit store, nhưng phải thống nhất contract xử lý với scheduler/orchestrator. Không mặc định một custom exit code sẽ tự thay `BatchStatus` theo ý muốn: `BatchStatus` và `ExitStatus` có vai trò khác nhau.

## 15. Những sai lầm thường gặp

### Chỉ kiểm tra file tồn tại

Một file tồn tại có thể đang được ghi dở, có header sai, checksum khác hoặc thuộc kỳ nghiệp vụ không đúng. Dùng ready signal + manifest/snapshot khi contract yêu cầu tính toàn vẹn.

### Dùng file extension làm kiểm tra định dạng

Tên `orders.csv` không đảm bảo nội dung là CSV theo schema. Kiểm tra encoding, header và parse theo contract; với dữ liệu không tin cậy, kiểm tra giới hạn tài nguyên và parser phù hợp.

### Parse CSV bằng split dấu phẩy

CSV hợp lệ có thể chứa trường quote và dấu phẩy bên trong giá trị, ví dụ `"ACME, Inc."`. `String.split(",")` dễ phân tách sai. Dùng parser CSV hỗ trợ quoting/escaping.

### Validate bằng một file rồi xử lý file khác

Nếu nguồn thay đổi sau preflight, kết quả validation không còn gắn với dữ liệu được import. Dùng snapshot/version immutable và gắn source identity vào job.

### Đưa toàn bộ I/O vào JobParametersValidator

Validator tham số phù hợp để từ chối cấu hình sai. Một preflight step rõ ràng thuận tiện hơn cho metadata, timing, failure diagnostics và quản lý workflow khi có I/O hoặc full scan tốn kém.

### Preflight quá nặng mà không cân nhắc I/O

Đọc toàn bộ file để validate, rồi importer đọc lại, có thể tăng chi phí đáng kể. Với dữ liệu lớn, cân nhắc một lượt nạp staging rồi validate/publish, hoặc chia hợp lý giữa kiểm tra cấu trúc trước và validation record trong chunk.

### Coi record lỗi là lỗi phải reject cả batch

Chính sách dữ liệu quyết định fail hay skip. Nếu contract cho phép quarantine 10 dòng lỗi trong một triệu dòng, preflight không nhất thiết phải từ chối cả file vì một record sai. Ngược lại, job tài chính có thể cần từ chối cả lô khi sai một giá trị trọng yếu.

### Coi mọi exception là dữ liệu lỗi

Một HTTP timeout hoặc database outage không phải bằng chứng file không hợp lệ. Phân loại exception để scheduler có thể retry sự cố tạm thời, còn dữ liệu vi phạm contract được chuyển sang quy trình sửa dữ liệu.

### Không kiểm tra lại khi restart

Nếu file có thể bị ghi đè, checkpoint từ run cũ không còn phù hợp. Cần khóa snapshot hoặc revalidate theo một cơ chế không làm thay đổi identity của dữ liệu đang xử lý.

### Xóa JobRepository để chạy lại

Metadata Spring Batch lưu lịch sử và checkpoint. Xóa nó để “bỏ qua lỗi” khiến việc restart, audit và chống xử lý trùng khó kiểm soát. Tách rõ restart, rerun và xử lý version mới.

### Chỉ assert job COMPLETED

Một job hoàn tất vẫn có thể chứa record bị filter sai, skip không được đối soát hoặc tổng tiền lệch. Test cần đo chất lượng output và kết quả gate cuối cùng, không chỉ status.

## 16. Bài tập áp dụng

**Bài 1 — JobParametersValidator.** Viết validator bắt buộc `inputPath`, `businessDate` và `schemaVersion`. Tạo unit test cho tham số thiếu, ngày sai format và version không được hỗ trợ.

**Bài 2 — File preflight.** Viết Tasklet kiểm tra file tồn tại, file không rỗng và header `order_id,customer_id,amount`. Dùng `@TempDir` tạo file test; xác minh preflight fail với file rỗng hoặc header sai.

**Bài 3 — Chặn importer.** Tạo job gồm `preflightStep` rồi `importDataStep`. Với file không hợp lệ, xác minh importer không chạy và bảng nghiệp vụ không có dòng mới.

**Bài 4 — Manifest và checksum.** Tạo manifest có `sourceId`, `businessDate`, `recordCount` và SHA-256. Tính lại hash bằng stream; xác minh file bị thay một byte bị reject.

**Bài 5 — Record validation policy.** Thêm một dòng amount âm. So sánh hai policy: fail toàn batch và skip/quarantine có giới hạn. Ghi rõ đầu ra mong đợi, số dòng hợp lệ, số dòng lỗi và quyền publish.

**Bài 6 — Restart.** Cho job dừng ở chunk thứ ba rồi restart. Cố định một snapshot đầu vào, giữ `JobRepository` và xác minh writer không nhân đôi dữ liệu. Sau đó thử đổi file giữa hai run để kiểm tra chính sách từ chối dữ liệu bị thay.

**Bài 7 — Reconciliation.** Dùng staging chứa 100 đơn hàng, manifest báo 100 dòng nhưng chỉ 99 dòng được parse. Thiết kế quality gate từ chối publish và lưu mã lỗi để vận hành xử lý.

**Bài 8 — Monitoring.** Xuất metric tổng số batch được accept/reject theo nhóm lỗi, thời gian preflight và số record quarantine. Tạo dashboard phân biệt dữ liệu lỗi của đối tác với lỗi hạ tầng.

## 17. Kết luận

**Validate đầu vào trước batch** là bước bảo vệ chất lượng và tính lặp lại của một quy trình Spring Batch. Nó bắt đầu từ **JobParametersValidator** để bảo vệ contract tham số, tiếp tục bằng **preflight step** kiểm tra source/schema/manifest trước khi nhập dữ liệu, rồi kết hợp validation từng record và **quality gate** trước khi publish.

Điểm cốt lõi là xác định **đầu vào nào thực sự được kiểm tra**, kiểm tra và xử lý **cùng một snapshot bất biến**, và có chính sách rõ ràng cho **reject, skip, quarantine, retry, restart và rerun**. Một job chỉ báo `COMPLETED` khi các step chạy xong chưa chắc dữ liệu đã đạt chất lượng; hệ thống còn cần đối soát số lượng, giá trị nghiệp vụ và việc xử lý những record lỗi. Khi những yêu cầu đó được mô hình hóa rõ, lỗi đầu vào được phát hiện sớm, dễ điều tra và ít làm hỏng dữ liệu ở các bước phía sau.

### Tài liệu tham khảo

- [Spring Batch Reference — JobParameters và JobInstance](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
