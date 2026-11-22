# Bảo vệ metadata repository trong Spring Batch

## 1. Vì sao metadata repository là tài sản cần bảo vệ?

Trong Spring Batch Core Processing, **JobRepository** là hạ tầng lưu metadata để framework nhận diện **JobInstance**, quản lý **JobExecution**, **StepExecution**, trạng thái và checkpoint. Metadata này cho phép xác định một Job đã chạy hay chưa, phát hiện lần chạy đang hoạt động và phục hồi dữ liệu từ lần thực thi thất bại.

Nhưng metadata không chỉ là những bộ đếm vô hại. Tùy cách ứng dụng thiết kế, nó có thể chứa:

- Tên Job và Step phản ánh quy trình kinh doanh hoặc tác vụ nhạy cảm.
- **JobParameters** như ngày nghiệp vụ, tên khách hàng, mã tài khoản, mã tenant, vị trí file và các tham số định danh.
- **ExecutionContext** của Job và Step, bao gồm vị trí reader, khóa trạng thái, thông tin checkpoint và những object được ứng dụng đưa vào.
- **ExitStatus**, exit description, exception message hoặc dấu vết lỗi có thể chứa một phần dữ liệu đầu vào.
- Thời gian chạy, số lượng giao dịch, số lần thất bại và thông tin vận hành có giá trị với kẻ tấn công.

Vì vậy, bảo vệ JobRepository là một phần của **security, privacy, integrity và availability** trong hệ thống batch. Nếu một tài khoản không phù hợp có quyền **đọc**, người đó có thể thấy thông tin nghiệp vụ nhạy cảm. Nếu có quyền **sửa**, họ có thể gây sai lệch trạng thái và phá cơ chế restart. Nếu có quyền **xóa**, Job có thể mất lịch sử và checkpoint, hoặc vô tình xử lý lại dữ liệu đã hoàn thành.

Bài này trình bày các nguyên tắc và cách triển khai để bảo vệ metadata repository của **Spring Batch 5.x / Spring Boot 3.x**, với ví dụ sử dụng JDBC JobRepository và PostgreSQL. Tư duy bảo vệ vẫn áp dụng được khi sử dụng hệ quản trị database khác, nhưng cú pháp quyền và cấu hình kết nối phải được điều chỉnh theo môi trường thực tế.

## 2. JobRepository lưu những gì?

Mô hình metadata cơ bản:

~~~text
                           JobRepository
                                 |
             +-------------------+-------------------+
             |                   |                   |
       JobInstance         JobExecution         StepExecution
       (danh tính)         (mỗi lần chạy)        (mỗi Step chạy)
             |                   |                   |
       JobParameters       ExecutionContext      ExecutionContext
             |                   |                   |
       identifying        status, exit info     counts, checkpoint
~~~

Trong JDBC JobRepository, các bảng thường có tiền tố **BATCH_**:

| Bảng / đối tượng | Thông tin thường lưu | Tại sao cần bảo vệ |
| --- | --- | --- |
| **BATCH_JOB_INSTANCE** | Job name, Job key và định danh JobInstance | Bị sửa có thể làm sai nhận diện JobInstance |
| **BATCH_JOB_EXECUTION** | Lần chạy, trạng thái, mốc thời gian, exit code/description | Có thể tiết lộ lịch chạy; chỉnh sửa phá trạng thái vận hành |
| **BATCH_JOB_EXECUTION_PARAMS** | Tên, kiểu, giá trị JobParameters và cờ identifying | Có thể chứa tên file, ID, dữ liệu nghiệp vụ hoặc bí mật bị đưa vào nhầm |
| **BATCH_STEP_EXECUTION** | Read/write/filter/skip/commit/rollback count, trạng thái, exit description | Tiết lộ lưu lượng công việc và nguyên nhân thất bại |
| **BATCH_JOB_EXECUTION_CONTEXT** | ExecutionContext cấp Job | Có thể chứa trạng thái hoặc dữ liệu nhạy cảm do ứng dụng lưu |
| **BATCH_STEP_EXECUTION_CONTEXT** | ExecutionContext cấp Step, thường liên quan checkpoint | Ảnh hưởng trực tiếp khả năng restart chính xác |
| **Sequence / bảng cấp ID** | Bộ sinh ID metadata theo database/schema | Không phù hợp nếu bị chỉnh sửa hoặc bị cấp quyền sai |

Tên bảng và cấu trúc cụ thể phụ thuộc phiên bản Spring Batch, loại database và custom table prefix. Khi thay đổi schema framework, cần dùng migration tương thích với phiên bản đang chạy; không tự ý sửa cấu trúc metadata vì tưởng đó chỉ là bảng log.

### JobParameters khác ExecutionContext như thế nào?

**JobParameters** là tham số cung cấp khi khởi chạy Job. Những tham số mang cờ **identifying** tham gia xác định JobInstance. Ví dụ:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("batchId", "import-20261115-001", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

Dù **requestedBy** không mang tính identifying, nó vẫn là một tham số của execution và có thể được lưu trong metadata. Cờ **identifying=false không phải cơ chế bảo mật hoặc mã hóa**.

**ExecutionContext** là tập key-value dùng để lưu trạng thái có thể tồn tại qua checkpoint/restart:

~~~java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastProcessedId", 10500L);
context.putString("inputVersion", "v3");
~~~

Metadata serializer có thể biểu diễn nội dung dưới dạng chuỗi hoặc định dạng tuần tự hóa khác. **Dữ liệu được serialize/encode không mặc nhiên là dữ liệu được mã hóa**. Nếu đưa token, mật khẩu hoặc dữ liệu cá nhân vào context, chúng có thể còn tồn tại trong database và bản sao lưu nhiều năm.

## 3. Mô hình rủi ro đối với metadata

Có thể xét bốn nhóm rủi ro chính:

| Rủi ro | Kịch bản | Tác động |
| --- | --- | --- |
| **Disclosure** | Tài khoản đọc metadata thấy JobParameters chứa API key, customer ID hoặc đường dẫn nội bộ | Lộ bí mật và dữ liệu nghiệp vụ |
| **Tampering** | Người dùng sửa trạng thái Step từ STARTED thành COMPLETED, hoặc thay checkpoint | Restart sai, xử lý thiếu/trùng dữ liệu |
| **Deletion** | Script xóa các hàng BATCH_* để “dọn rác” trong lúc Job chạy | Mất lịch sử, lỗi khóa ngoại, phá khả năng restart |
| **Denial of service** | Người dùng kích hoạt hàng nghìn JobExecution, giữ lock hoặc làm đầy database | Hệ thống batch chậm, không thể chạy lịch |

Nguồn rủi ro có thể đến từ quyền SQL trực tiếp, endpoint REST quản trị, một service account bị lộ, các ứng dụng dùng chung DataSource, script vận hành hoặc log và bản sao lưu bị truy cập sai.

**Nguyên tắc nền tảng:** metadata repository là **trạng thái điều khiển thực thi**, không phải một bảng thống kê mà mọi thành phần đều được tự do chỉnh sửa. Chỉ framework và các công cụ quản trị được cho phép mới nên thao tác thay đổi metadata theo contract được hỗ trợ.

## 4. Phân tách vai trò truy cập bằng nguyên tắc least privilege

Một mô hình quyền rõ ràng thường có ba vai trò:

1. **Migration owner:** tạo và nâng cấp schema Batch trong bước triển khai được kiểm soát.
2. **Batch runtime:** tài khoản mà ứng dụng dùng để đọc, tạo và cập nhật metadata phục vụ Job.
3. **Read-only observer:** tài khoản dashboard, báo cáo hoặc công cụ audit chỉ cần xem trạng thái.

Một vai trò thứ tư có thể là **maintenance/retention operator**, dành cho công việc dọn metadata lịch sử theo quy trình phê duyệt, không chia quyền rộng đó cho tất cả ứng dụng.

| Vai trò | SELECT | INSERT/UPDATE | DELETE | DDL |
| --- | --- | --- | --- | --- |
| Batch runtime | Cần | Cần cho hoạt động JobRepository | Chỉ khi workflow thực sự yêu cầu | Thường không |
| Read-only observer | Chỉ bảng/cột cần thiết | Không | Không | Không |
| Migration owner | Theo nhu cầu migration | Theo nhu cầu migration | Theo nhu cầu migration | Có kiểm soát |
| Maintenance operator | Theo nhu cầu lưu trữ/xóa lịch sử | Theo quy trình | Có thể cần, được giới hạn | Chỉ khi có lý do rõ ràng |

Trong runtime thông thường, JobRepository chủ yếu thực hiện truy vấn, tạo và cập nhật metadata. Không cần cấp tài khoản runtime quyền **DROP TABLE**, **ALTER TABLE**, quyền quản trị database hoặc quyền đọc mọi schema của toàn hệ thống chỉ vì ứng dụng sử dụng Spring Batch.

Tuy nhiên, **không nên cắt quyền chỉ theo bảng trên một cách máy móc**: hãy xác minh SQL thực tế mà phiên bản Spring Batch, database driver và các chức năng quản trị đang sử dụng cần, nhất là khi có batch maintenance hoặc lệnh dọn lịch sử. Quyền thiếu sẽ gây lỗi vận hành; quyền thừa tạo rủi ro bảo mật.

## 5. Ví dụ phân quyền PostgreSQL cho Batch metadata

Giả sử schema **batch_meta** đã được tạo bằng migration và chứa các bảng BATCH_*. Các tài khoản cần được cấp thông tin xác thực qua hệ thống quản lý bí mật, không viết password trực tiếp vào script hay Git.

Ví dụ SQL minh họa:

~~~sql
-- Chạy bằng tài khoản quản trị/migration có quyền phù hợp.
CREATE SCHEMA IF NOT EXISTS batch_meta;

-- Tài khoản runtime và observer cần được provision bằng quy trình
-- quản lý danh tính của hệ thống. Ví dụ ROLE dưới đây chỉ minh họa.
CREATE ROLE batch_runtime LOGIN;
CREATE ROLE batch_observer LOGIN;

-- Không để PUBLIC mặc định sử dụng schema này.
REVOKE ALL ON SCHEMA batch_meta FROM PUBLIC;

GRANT USAGE ON SCHEMA batch_meta
    TO batch_runtime, batch_observer;

-- Batch runtime đọc, tạo và cập nhật metadata.
GRANT SELECT, INSERT, UPDATE
    ON ALL TABLES IN SCHEMA batch_meta
    TO batch_runtime;

-- JobRepository có thể dùng sequence để tạo ID.
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA batch_meta
    TO batch_runtime;

-- Dashboard chỉ đọc metadata.
GRANT SELECT
    ON ALL TABLES IN SCHEMA batch_meta
    TO batch_observer;
~~~

Lưu ý khi dùng script:

- **CREATE ROLE** chỉ là cú pháp ví dụ; production nên quản lý role/password/rotation qua DBA, IAM hoặc secret manager. Không để tài khoản LOGIN không có chính sách xác thực phù hợp.
- **GRANT ON ALL TABLES** áp dụng cho các bảng hiện có. Nếu migration tạo bảng/sequence mới, phải thiết kế **default privileges** hoặc chạy lại grant trong bước migration.
- Quyền SELECT trên toàn bộ bảng metadata có thể vẫn quá rộng với một dashboard đơn giản. Có thể dùng **view đã giới hạn cột và dữ liệu** thay vì đưa tài khoản observer truy cập mọi bảng.
- Runtime có thể cần quyền riêng trong hệ quản trị khác; ví dụ SQL Server, Oracle, MySQL không dùng chính xác cú pháp PostgreSQL trên.
- **DELETE** chưa được cấp trong ví dụ runtime. Nếu ứng dụng dùng API hoặc tác vụ dọn metadata cần DELETE, nên cấp cho một tài khoản/đường vận hành riêng và kiểm chứng theo contract cụ thể.
- Các bảng và sequence có thể có tên khác nếu ứng dụng tùy chỉnh prefix/schema.

Một hướng tách quyền mạnh hơn là tạo **view chỉ chứa dữ liệu tổng quan** cho dashboard:

~~~sql
CREATE VIEW batch_meta.v_step_status AS
SELECT
    se.STEP_EXECUTION_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM batch_meta.BATCH_STEP_EXECUTION se;
~~~

Người dùng dashboard chỉ cần SELECT trên view thay vì tất cả JobParameters và ExecutionContext. Với PostgreSQL, view và quyền đọc underlying tables phải được thiết kế theo cơ chế ownership/security invoker tương ứng. Tránh vô tình cho observer quyền đọc bảng gốc nếu mục tiêu chỉ là xem view.

## 6. Cô lập schema và kết nối JobRepository

Có một số mức độ cô lập thường dùng:

### 6.1. Cùng database, tách schema

~~~text
application_db
  |
  +-- business_data
  |     +-- orders
  |     +-- customers
  |
  +-- batch_meta
        +-- BATCH_JOB_INSTANCE
        +-- BATCH_JOB_EXECUTION
        +-- BATCH_STEP_EXECUTION
        +-- ...
~~~

Lợi ích là dễ quản lý backup và transaction khi cùng database, đồng thời có thể cấp quyền khác nhau theo schema. Tuy nhiên, phải chắc chắn runtime kết nối đúng schema/prefix. Nếu một pod dùng bảng **public.BATCH_*** còn pod khác dùng **batch_meta.BATCH_***, hai instance không còn chia sẻ cùng repository.

### 6.2. Database riêng cho metadata

~~~text
batch-metadata-db  -> JobRepository
orders-db          -> ItemReader / ItemWriter
~~~

Cách này có thể tăng cô lập quyền, backup và tài nguyên. Nhưng cần hiểu **ranh giới giao dịch giữa metadata và dữ liệu nghiệp vụ**: hai DataSource khác nhau không tự tạo một transaction phân tán nguyên tử. Chỉ dùng một transaction manager cục bộ cho hai database có thể làm checkpoint metadata và dữ liệu ghi lệch nhau nếu thiết kế sai.

Với Job quan trọng, hãy xác định rõ transaction manager cho JobRepository và Step, chính sách rollback, checkpoint và idempotency của writer. Không tách database chỉ để “an toàn hơn” mà bỏ qua tính nhất quán restart.

### 6.3. Nhiều instance cần chung nguồn metadata

Khi nhiều scheduler/worker instance cùng chạy một hệ thống Batch và cần phối hợp trạng thái, chúng thường phải sử dụng **cùng JobRepository** phù hợp với thiết kế concurrency. Nếu mỗi pod vô tình trỏ tới một H2 in-memory hoặc một schema khác nhau, mỗi pod có thể tạo JobInstance riêng cho cùng kỳ xử lý.

Quyền truy cập và tính sẵn sàng của database repository là một phần của kiến trúc phân tán. Cần theo dõi pool connection, lock, latency, backup/restore và khả năng failover.

## 7. Không lưu mật khẩu hoặc token trong JobParameters

Một sai lầm phổ biến là truyền bí mật dưới dạng tham số Job:

~~~java
// Không an toàn: mật khẩu có thể được lưu trong metadata.
JobParameters params = new JobParametersBuilder()
        .addString("apiToken", realApiToken, false)
        .addString("sftpPassword", sftpPassword, false)
        .toJobParameters();
~~~

Việc đặt **identifying=false** không làm tham số biến mất khỏi repository, log hoặc các công cụ truy vấn.

Thay vào đó, chỉ lưu **tham chiếu** hoặc định danh không nhạy cảm:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceId", "partner-feed-A", true)
        .addString("credentialRef", "partner-feed-A/read", false)
        .toJobParameters();
~~~

Ở đây **credentialRef** là tên logic dùng để tra bí mật từ một secret manager hoặc service cấu hình có kiểm soát. Bản thân tham chiếu cũng cần được đánh giá, vì tên đối tác hoặc nguồn dữ liệu đôi khi vẫn là thông tin nhạy cảm.

Một component sử dụng secret manager có thể nhận reference ở runtime:

~~~java
public interface CredentialResolver {
    String resolveToken(String credentialRef);
}

@Service
public class PartnerFeedClient {

    private final CredentialResolver resolver;

    public PartnerFeedClient(CredentialResolver resolver) {
        this.resolver = resolver;
    }

    public void fetch(String credentialRef) {
        String token = resolver.resolveToken(credentialRef);

        // Gửi token vào header của request qua TLS.
        // Không đặt token vào JobParameters, ExecutionContext hoặc log.
    }
}
~~~

Trong hệ thống thật cần thêm cấu hình client, timeout, vòng đời token và cách xóa/đổi token phù hợp. Bí mật nên được cấp theo quyền tối thiểu, có thể rotate và không bị ghi vào exception message.

### Những trường nhạy cảm khác cũng nên cân nhắc

Dù không phải mật khẩu, metadata vẫn có thể chứa:

- Số tài khoản, email, số điện thoại hoặc định danh khách hàng.
- Đường dẫn file chứa thông tin tenant, tên người dùng hoặc dữ liệu nội bộ.
- Tên bucket, địa chỉ máy chủ, endpoint nội bộ.
- Giá trị tìm kiếm có dữ liệu cá nhân trong JobParameters.
- Mã giao dịch tài chính hoặc tên hệ thống đối tác.

Với mỗi tham số, nên hỏi: **Có thật sự cần lưu giá trị này để nhận diện hoặc restart Job không?** Nếu không, lưu một ID trung gian và cho ứng dụng truy vấn thông tin chi tiết từ nơi có kiểm soát quyền.

## 8. ExecutionContext là checkpoint, không phải kho dữ liệu tùy ý

ExecutionContext được Spring Batch lưu để khôi phục trạng thái của reader/writer hoặc dữ liệu thực thi được ứng dụng xác định. Ví dụ hợp lý:

~~~java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastProcessedOrderId", 100500L);
context.putString("inputSnapshotId", "snapshot-20261115");
~~~

Ví dụ rủi ro:

~~~java
// Không nên lưu toàn bộ dữ liệu nhạy cảm vào checkpoint.
context.putString("accessToken", accessToken);
context.put("rawCustomerRecord", customerWithPersonalData);
context.putString("sqlWithPassword", connectionStringWithSecret);
~~~

Vì context được lưu qua database, một lần crash/restart có thể giữ nguyên dữ liệu nhạy cảm lâu hơn dự kiến. Một đoạn context được biểu diễn dưới dạng encoded bytes hoặc serialized string **vẫn có thể đọc được** khi có đủ quyền và biết serializer.

Nguyên tắc thiết kế:

1. Chỉ lưu trạng thái **tối thiểu cần cho restart**, chẳng hạn offset, ID cuối hoặc version của input.
2. Tránh lưu nguyên object chứa dữ liệu cá nhân hay thông tin xác thực.
3. Không dùng context làm cache cho hàng nghìn item; vừa tăng rủi ro dữ liệu vừa gây áp lực serialize/checkpoint.
4. Nếu một mã định danh nhạy cảm là bắt buộc, cần cân nhắc token hóa, mã hóa ở tầng ứng dụng có quản lý khóa hoặc tái thiết kế cách lưu.
5. Kiểm tra dữ liệu mặc định do reader/writer lưu trong ExecutionContext, nhất là tên resource, đường dẫn, key hoặc metadata nguồn.

**Không nên tự sửa ExecutionContext trong database để “nhảy qua” bản ghi lỗi**. Việc thay checkpoint không hiểu transaction có thể tạo mất hoặc trùng dữ liệu.

## 9. Kiểm soát exception và ExitStatus để tránh lộ dữ liệu

Khi ItemReader, ItemProcessor hoặc ItemWriter ném lỗi, Spring Batch có thể ghi thông tin lỗi vào metadata của JobExecution/StepExecution, tùy cấu hình. Một thông báo exception thiếu kiểm soát có thể chứa input hoặc secret:

~~~java
// Không an toàn: dữ liệu raw có thể được lưu/log.
throw new IllegalStateException(
        "Invalid customer record: " + rawCustomerJson);
~~~

Cách thông báo tốt hơn:

~~~java
throw new InvalidOrderException(
        "Invalid order amount, batchId=" + batchId
        + ", lineNumber=" + lineNumber);
~~~

Trong ví dụ thứ hai, batchId/lineNumber phải là định danh an toàn theo chính sách dữ liệu của tổ chức. Có thể đưa correlation ID vào log bảo vệ riêng để truy vết, còn không đặt payload nhạy cảm trong message được lưu rộng rãi.

Nếu dùng **ExitStatus** tùy chỉnh, tránh nhúng token, raw SQL có credential, JSON đầu vào hoặc dữ liệu cá nhân:

~~~java
// Mã trạng thái có ý nghĩa nhưng không chứa payload nhạy cảm.
return new ExitStatus("VALIDATION_FAILED", "invalid_input");
~~~

Ngoài metadata, còn phải xem log của Spring Batch, framework JDBC, HTTP client, tracing và alerting. Bảo vệ repository nhưng để stack trace chứa token xuất hiện trong log công khai vẫn là lỗ hổng.

### Khi cần giữ chi tiết lỗi phục vụ điều tra

Có thể lưu phần chi tiết lỗi vào một **audit store được bảo vệ chặt** với thời hạn lưu trữ, phân quyền và mã hóa riêng. Trong metadata Batch, lưu error code và correlation ID để tra cứu. Như vậy người theo dõi tiến độ không mặc nhiên được phép xem nội dung dữ liệu lỗi.

## 10. Bảo vệ giao diện truy vấn JobExplorer và các API quản trị

Spring Batch cung cấp **JobExplorer** để đọc metadata và các API vận hành như **JobOperator** để thao tác lifecycle Job. Khi ứng dụng xây REST endpoint, CLI hoặc dashboard nội bộ, cần đặt kiểm soát truy cập ở **lớp ứng dụng**, không chỉ dựa vào quyền database.

Ví dụ các quyền có thể phân biệt:

| Quyền ứng dụng | Nghiệp vụ cho phép |
| --- | --- |
| **BATCH_METADATA_READ** | Xem danh sách Job/Step và các count không nhạy cảm |
| **BATCH_JOB_START** | Yêu cầu chạy Job được phép |
| **BATCH_JOB_RESTART** | Restart một JobInstance phù hợp |
| **BATCH_JOB_STOP** | Dừng một JobExecution theo quy trình |
| **BATCH_AUDIT_READ** | Xem dữ liệu audit chi tiết được phép |
| **BATCH_ADMIN** | Thực hiện tác vụ quản trị nâng cao có kiểm soát |

**Quyền đọc metadata không đồng nghĩa được phép restart hoặc stop Job.** Một endpoint cho phép người dùng chọn tùy ý tên Job, parameters hay execution ID cần được bảo vệ khỏi truy cập không có quyền và khỏi lạm dụng gây tải hoặc xử lý trùng.

### Ví dụ chỉ trả về dữ liệu đã tối giản

Với Spring Security method security được bật:

~~~java
@Configuration
@EnableMethodSecurity
public class BatchMethodSecurityConfig {
}
~~~

Service trả về DTO không chứa JobParameters hay ExecutionContext:

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SafeBatchMetadataService {

    private final JobExplorer explorer;

    public SafeBatchMetadataService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    @PreAuthorize("hasAuthority('BATCH_METADATA_READ')")
    public List<StepStatusView> stepStatuses(long jobExecutionId) {
        JobExecution execution = explorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return execution.getStepExecutions().stream()
                .map(step -> new StepStatusView(
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount()))
                .toList();
    }

    public record StepStatusView(
            String stepName,
            String status,
            long readCount,
            long writeCount,
            int commitCount) {}
}
~~~

Ví dụ này minh họa **data minimization** và kiểm tra quyền bằng **@PreAuthorize**. Trong production còn cần authentication, SecurityFilterChain, TLS, audit, rate limiting, kiểm soát được phép xem Job nào và cách xử lý lỗi trả ra ngoài.

**@PreAuthorize** hoạt động khi bean được Spring Security quản lý và lời gọi đi qua cơ chế interception của Spring; gọi trực tiếp một method qua self-invocation có thể bỏ qua kiểm tra tùy cách áp dụng proxy. Test bảo mật phải gọi qua lớp giao diện thực tế như HTTP/service bean được proxy.

### Bẫy truy cập theo ID trong hệ thống nhiều tenant

Một người dùng có quyền **BATCH_METADATA_READ** chưa chắc được phép xem **tất cả** các JobExecution. Nếu Job của nhiều tenant cùng nằm trong repository, endpoint nhận một ID số tăng dần có nguy cơ **IDOR (Insecure Direct Object Reference)**.

Phải kiểm tra **scope** theo tenant/đơn vị nghiệp vụ trước khi trả kết quả. JobExplorer không tự áp dụng quy tắc phân quyền theo tenant cho ứng dụng của bạn. Có thể thiết kế bảng ánh xạ quyền riêng hoặc dùng repository/service đã lọc theo tenant đáng tin cậy; tuyệt đối không chỉ tin tenantId do client gửi lên.

## 11. Phân biệt JobExplorer và JobOperator

Một số nguyên tắc khi xây công cụ vận hành:

**JobExplorer** phù hợp đọc lịch sử và trạng thái. Chỉ nên trả các trường cần cho mục tiêu người dùng; không serialize nguyên đối tượng **JobExecution** ra JSON nếu nó chứa JobParameters hoặc exception details.

**JobOperator** có thể start, restart, stop hoặc thao tác lifecycle theo API hiện có. Đây là **quyền điều khiển xử lý**, cần mức ủy quyền cao hơn read-only monitoring.

**JobRepository** là hạ tầng framework dùng để tạo/cập nhật metadata. Không tạo một SQL endpoint cho phép người dùng sửa trực tiếp các trường **STATUS**, **VERSION**, **JOB_KEY** hoặc **SHORT_CONTEXT** để điều khiển Job; việc này phá invariant và có thể vượt qua chính sách lifecycle của Spring Batch.

Trong ứng dụng nội bộ, các thao tác quản trị nên có:

- Authentication và authorization theo hành động.
- Kiểm tra Job được phép chạy cùng parameters đã kiểm soát.
- Ràng buộc không chạy trùng kỳ nghiệp vụ hoặc quá số Job đồng thời.
- Rate limit, audit trail và correlation ID.
- Phản hồi lỗi không lộ stack trace/secret.
- Quy trình phê duyệt nếu thao tác có thể tác động dữ liệu tài chính hay khách hàng.

## 12. Bảo vệ kết nối, bí mật và backup của repository

Bảo vệ ở tầng ứng dụng sẽ không đủ nếu traffic tới database hoặc bản sao lưu bị lộ.

### 12.1. Truyền dữ liệu qua kết nối bảo mật

Giữa ứng dụng và database cần TLS theo tiêu chuẩn của môi trường. Ví dụ với PostgreSQL, có thể cấu hình JDBC URL yêu cầu xác minh server certificate:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/batchdb?sslmode=verify-full
spring.datasource.username=batch_runtime
# Password nhận từ secret manager hoặc cấu hình bảo mật của runtime,
# không commit giá trị thật vào source control.
~~~

Khi dùng **verify-full**, client phải tin cậy CA phù hợp và tên host phải khớp certificate. **Không được chuyển sang disable certificate validation để “sửa” lỗi TLS**.

Nếu app có nhiều DataSource, ví dụ chỉ là một kết nối; cần chọn đúng DataSource mà Spring Batch JobRepository đang dùng.

### 12.2. Mã hóa dữ liệu lưu trữ và backup

Metadata nên được bảo vệ bằng encryption at rest theo chính sách database/storage, cùng với mã hóa backup, snapshot và các bản xuất dữ liệu.

Nhưng **encryption at rest không thay thế quyền SELECT**: tài khoản runtime có quyền đọc metadata thường nhận được giá trị giải mã từ database. Secret bị ghi nhầm vào JobParameters vẫn có thể bị lộ qua API hoặc log dù ổ đĩa được mã hóa.

### 12.3. Quản lý tài khoản và credential

- Dùng secret manager, workload identity hoặc cơ chế được tổ chức phê duyệt.
- Không hard-code password trong source, test fixture dùng chung hoặc log startup.
- Thực hiện rotation và kiểm soát quyền truy cập theo từng ứng dụng/môi trường.
- Tách tài khoản production, staging và test để tránh nhầm môi trường.
- Không dùng tài khoản DBA/admin cho Batch runtime.
- Theo dõi kết nối thất bại và hành vi đăng nhập bất thường.

Với database backup và replication, cũng phải kiểm soát người đọc metadata ở bản sao; dữ liệu nhạy cảm không hết nhạy cảm chỉ vì nằm trong backup.

## 13. Audit và quan sát hoạt động trên repository

Một số sự kiện nên được ghi nhận:

| Sự kiện | Lý do quan sát |
| --- | --- |
| Tạo JobExecution mới | Phát hiện lịch chạy bất thường hoặc launch thủ công |
| Restart JobInstance | Xác định ai/vì sao kích hoạt chạy lại |
| Stop hoặc abandon Job | Truy vết can thiệp vận hành |
| Truy cập metadata nhạy cảm | Hỗ trợ điều tra truy cập không hợp lệ |
| Đăng nhập DB/role thay đổi | Phát hiện thay đổi quyền bất thường |
| DDL/migration schema Batch | Biết khi nào repository được nâng cấp |
| Xóa hoặc archive metadata | Bảo vệ restart và tuân thủ retention |
| Đột biến số JobExecution | Phát hiện lỗi scheduler hoặc abuse |

Nên ghi correlation ID, tên Job, Step, JobExecution ID, actor, thời điểm và kết quả hành động. Tránh ghi toàn bộ JobParameters/ExecutionContext trong log audit phổ thông.

**Metrics** như số Job đang chạy, tỷ lệ thất bại, độ trễ truy vấn JobRepository, kích thước bảng metadata và số lỗi authorization giúp cảnh báo sớm.

Không gắn **jobExecutionId**, customerId hoặc token làm tag metric tăng vô hạn trong Prometheus. Những giá trị đó phù hợp với log/tracing hoặc kho audit có kiểm soát; metric tổng hợp nên dùng tag ổn định như jobName, status hoặc môi trường.

### Phát hiện hành vi bất thường

Ví dụ một endpoint quản trị đột ngột gọi restart 500 lần/phút cho nhiều execution khác nhau. Hệ thống cần có rate limit và audit để phát hiện, vì kẻ tấn công hoặc bug có thể dùng quyền được cấp để tạo tải lên database/worker.

Nếu một tài khoản read-only bắt đầu thử INSERT/UPDATE vào BATCH_* và nhận permission denied, đó cũng là tín hiệu cần điều tra. Audit không tự ngăn truy cập, nhưng giúp phát hiện và chứng minh sự kiện sau đó.

## 14. Metadata retention, cleanup và quyền xóa

Theo thời gian, các bảng metadata có thể tăng lớn do mỗi JobInstance có nhiều lần chạy, nhiều StepExecution và checkpoint. Retention cần giải quyết hai mục tiêu đối lập:

- Giữ đủ lịch sử để điều tra, audit và restart Job chưa hoàn tất.
- Không giữ dữ liệu nhạy cảm lâu hơn mức cần thiết và không làm repository quá tải.

Một chính sách thực tế phân loại:

| Loại metadata | Chính sách điển hình |
| --- | --- |
| JobExecution đang STARTING/STARTED | Không xóa |
| JobExecution FAILED có thể restart | Giữ cho đến khi xử lý hoặc hết thời hạn recovery đã duyệt |
| JobExecution COMPLETED cũ | Có thể archive/purge theo retention nghiệp vụ |
| JobInstance đang có lịch sử liên quan | Chỉ xóa theo thứ tự an toàn và chính sách cụ thể |
| Exception/ExecutionContext có dữ liệu nhạy cảm | Đánh giá thời hạn lưu và cách ẩn/mã hóa phù hợp |
| Báo cáo audit đã chốt | Tuân thủ chính sách pháp lý/nội bộ riêng |

**Không xóa ngẫu nhiên các hàng trong BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION hoặc ExecutionContext** bằng một vài câu DELETE thủ công. Các bảng có khóa ngoại và liên hệ trạng thái; xóa sai thứ tự có thể gây lỗi dữ liệu hoặc làm mất khả năng restart.

Các điểm nên thiết kế:

1. Chỉ chạy cleanup khi đã chắc chắn Job không đang sử dụng metadata cần xóa.
2. Xem xét phụ thuộc giữa JobInstance, JobExecution, StepExecution và ExecutionContext.
3. Dùng quy trình archive/cleanup được kiểm soát và kiểm thử trên backup hoặc môi trường tương đương.
4. Dùng account maintenance có quyền riêng; runtime bình thường không cần quyền xóa toàn bộ lịch sử.
5. Giữ log/biên bản số lượng đã xóa, phạm vi và người thực hiện.
6. Đảm bảo backup/restore tương thích với schema và phiên bản Spring Batch.

**JobRepositoryTestUtils.removeJobExecutions()** là tiện ích hữu ích trong **kiểm thử**, không phải lựa chọn mặc định cho cleanup production. Việc xóa metadata đang được một test hoặc process khác sử dụng có thể làm test/job thất bại ngẫu nhiên.

## 15. Không sửa metadata trực tiếp để khắc phục lỗi Job

Một số thao tác có vẻ đơn giản nhưng nguy hiểm:

~~~sql
-- KHÔNG thực hiện như một cách khắc phục thông thường.
UPDATE BATCH_JOB_EXECUTION
SET STATUS = 'COMPLETED'
WHERE JOB_EXECUTION_ID = 1234;
~~~

Câu SQL này không thể bảo đảm Step đã ghi đầy đủ kết quả hoặc transaction cuối cùng đã commit. Nó còn có thể làm Spring Batch xem một execution chưa xử lý xong là đã hoàn tất.

Tương tự, thay **ExecutionContext** để chỉnh offset có thể khiến reader bỏ qua item hoặc đọc lại sai vị trí. Khi một Job có trạng thái **STARTED** nhưng process thực sự đã chết, cần điều tra metadata, transaction và cơ chế phục hồi theo quy trình được tổ chức chấp thuận. Các API quản trị của framework có thể hỗ trợ một phần lifecycle, nhưng không nên giả định rằng cập nhật STATUS là đủ để sửa dữ liệu nghiệp vụ.

Phân biệt:

- **Sửa trạng thái vận hành:** thao tác lifecycle có kiểm soát.
- **Khôi phục dữ liệu:** restart/reprocess/compensation theo business key.
- **Sửa metadata hỏng:** công việc bảo trì đặc biệt, cần backup và đánh giá tác động.

Nếu metadata bị thay đổi trái phép, ưu tiên cô lập credential, thu thập bằng chứng, so sánh backup/audit và xác minh lại output thay vì tiếp tục launch Job dựa trên checkpoint có thể đã bị giả mạo.

## 16. Phòng chống lộ dữ liệu qua logging, API và monitoring

Một hệ thống có thể phân quyền DB rất tốt nhưng vẫn để lộ metadata qua những đường phụ:

~~~text
PostgreSQL batch_meta
         |
         +--> application log
         +--> REST /internal/batch/executions
         +--> distributed tracing
         +--> error monitoring
         +--> support dashboard
         +--> backup / export file
~~~

Cần áp dụng **data minimization** tại mỗi điểm:

- Chỉ hiển thị trạng thái, start/end time và count cần thiết cho người xem.
- Không tự xuất raw ExecutionContext, exception stack trace hoặc toàn bộ JobParameters ra JSON.
- Ẩn hoặc thay thế giá trị nhạy cảm bằng mã tham chiếu.
- Bật phân quyền theo môi trường và tenant ở dashboard.
- Giữ HTTPS/TLS và cấu hình session/token an toàn cho API quản trị.
- Cấu hình retention phù hợp cho log, trace, metrics và bản export.
- Kiểm thử sự cố lỗi để chắc chắn exception không làm lộ credential trong response.

Nếu cần debug sâu, có thể cung cấp một đường truy cập audit riêng với authorization chặt và lịch sử truy cập, thay vì mở rộng mặc định cho mọi người có quyền xem dashboard.

## 17. Tách môi trường dev, test và production

Môi trường development thường dùng H2 in-memory, chạy script tạo schema tự động và có các tiện ích dọn metadata. Điều đó phù hợp cho test cục bộ nhưng có thể nguy hiểm nếu sao chép nguyên cấu hình sang production.

Ví dụ cấu hình được giới hạn cho môi trường test:

~~~properties
# Chỉ trong test/dev database dùng một lần.
spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false
~~~

Trong production, nên để migration được thực hiện bởi Flyway/Liquibase hoặc cơ chế DBA đã phê duyệt; runtime không cần tự tạo/xóa schema.

~~~properties
# Ví dụ production: schema do migration quản lý.
spring.batch.jdbc.initialize-schema=never
~~~

Thuộc tính trên chỉ điều khiển khởi tạo **Batch metadata schema** bằng cơ chế Spring Boot tương ứng; nó không tự bảo vệ quyền SQL, tạo role, mã hóa JobParameters hay kiểm tra secrets.

Các nguyên tắc khác:

- Không kết nối test suite tới JobRepository production.
- Không dùng chung credential giữa môi trường.
- Không đưa database dump production có PII vào laptop/dev mà chưa được ẩn danh và phê duyệt.
- Không chạy test cleanup trên một repository đang phục vụ Job thật.
- Khi dùng Testcontainers hoặc database tạm, vẫn tránh log token trong fixture.

## 18. Kiểm thử bảo mật metadata repository

Một thiết kế bảo vệ chỉ thực sự đáng tin khi có kiểm thử cho **đường thành công lẫn đường bị từ chối**. Test có thể chia thành nhiều lớp:

### 18.1. Kiểm thử quyền database

Chuẩn bị một schema metadata test và các role có quyền giống production:

1. Dùng tài khoản **batch_runtime** khởi chạy một Job đơn giản. Xác nhận JobRepository đọc/ghi metadata được và có StepExecution hợp lệ.
2. Dùng tài khoản **batch_observer** thực hiện SELECT trên view giám sát được phép.
3. Kiểm tra tài khoản observer không INSERT/UPDATE/DELETE bảng BATCH_*.
4. Kiểm tra role runtime không được DROP hoặc ALTER metadata schema.
5. Nếu có retention role, kiểm tra quyền DELETE chỉ được cấp trong đúng phạm vi cần thiết.

Dùng database engine tương đương production khi kiểm tra quyền, vì H2 có hành vi authorization khác PostgreSQL/Oracle/MySQL.

### 18.2. Kiểm thử JobParameters và ExecutionContext

Một test hữu ích cần launch Job với các tham số cho phép và kiểm tra metadata không chứa secret thô:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "feed-A/read", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, params);

// Từ JobExplorer hoặc các bảng metadata test,
// xác minh không có giá trị token/password thực trong parameters/context.
// Không ghi lại token vào log khi assert thất bại.
~~~

Một test khác có thể cố tạo exception chứa dữ liệu nhạy cảm trong môi trường test, sau đó xác minh cơ chế sanitize của ứng dụng chặn nó trước khi vào log, audit và response. Không dùng credential production trong fixture.

### 18.3. Kiểm thử phân quyền endpoint

Với Spring Security Test và MockMvc, endpoint giám sát nội bộ có thể được kiểm tra theo role. Ví dụ giả định endpoint **GET /internal/batch/executions/42** đã được triển khai và được bảo vệ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BatchMetadataAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(authorities = "BATCH_METADATA_READ")
    void metadataReaderCanViewSanitizedExecution() throws Exception {
        mvc.perform(get("/internal/batch/executions/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.jobParameters").doesNotExist())
                .andExpect(jsonPath("$.executionContext").doesNotExist());
    }

    @Test
    @WithMockUser(authorities = "BATCH_JOB_START")
    void launcherCannotReadMetadataWithoutReadPermission() throws Exception {
        mvc.perform(get("/internal/batch/executions/42"))
                .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ trên cần fixture có JobExecution ID tương ứng hoặc một endpoint/service được mock phù hợp; những import/test dependencies của Spring Boot Test, Spring Security Test và MockMvc cần được cấu hình trong dự án.

Ngoài kiểm tra role, đặc biệt với multi-tenant, cần tạo hai tenant khác nhau và xác minh người của tenant A **không thể xem execution của tenant B** dù biết ID số.

### 18.4. Kiểm thử an toàn restart và tính toàn vẹn metadata

Trong một integration test:

- Chạy Job với dữ liệu cố định rồi tạo lỗi có kiểm soát ở giữa.
- Xác nhận JobRepository giữ checkpoint và trạng thái thất bại.
- Restart bằng cùng identifying JobParameters.
- Xác nhận không mất/trùng record, writer idempotent và Job cuối cùng đúng.
- Kiểm tra một tài khoản không có quyền không thể sửa StepExecution/ExecutionContext giữa hai lần chạy.

Điều này chứng minh **quyền truy cập và tính toàn vẹn metadata có ảnh hưởng trực tiếp tới dữ liệu cuối**, không chỉ tới trang giám sát.

## 19. Tổ chức quyền trong mô hình nhiều tenant

Nếu nhiều tổ chức hoặc khách hàng dùng chung Spring Batch deployment, JobRepository có thể chứa metadata của nhiều tenant. Có ba cấp độ cô lập:

| Cấp độ | Đặc điểm | Rủi ro cần giải quyết |
| --- | --- | --- |
| Một repository chung, phân quyền ứng dụng | Chi phí thấp, metadata cùng bảng | IDOR, log hoặc query đọc nhầm tenant |
| Schema riêng theo tenant | Tách quyền database tốt hơn | Cấu hình prefix/schema, migration và kết nối |
| Database riêng theo tenant | Cô lập mạnh hơn | Quản lý nhiều repository, connection/backup và monitoring |

Trong mô hình chung, **JobParameters chứa tenantId không phải tự động biến JobRepository thành hệ thống Row-Level Security**. JobExplorer và SQL vẫn có thể đọc metadata không thuộc tenant nếu không có lớp phân quyền bổ sung.

Nếu dùng PostgreSQL RLS hoặc view riêng để lọc, cần kiểm tra tính tương thích với metadata relationships, transaction, connection pooling và thao tác framework. Không nên bật RLS cho bảng Batch mà chưa kiểm thử toàn bộ lifecycle, bởi JobRepository có thể cần truy cập nhiều bảng có khóa quan hệ trong cùng transaction.

Một lựa chọn đơn giản cho các batch có yêu cầu isolation rất cao là tách repository vật lý. Tuy nhiên, cần tính chi phí vận hành, backup, truy vấn tập trung và định danh Job giữa các repository.

## 20. Bảng đánh giá các biện pháp bảo vệ

| Biện pháp | Bảo vệ khỏi | Không giải quyết hoàn toàn |
| --- | --- | --- |
| **Least-privilege DB role** | Đọc/ghi/xóa metadata trái quyền | Lộ dữ liệu từ tài khoản runtime bị chiếm |
| **Tách schema/database** | Truy cập vượt phạm vi cấu trúc được cấp | Sai JobParameters hoặc lỗi idempotency |
| **Không lưu secret trong params/context** | Lộ credential qua metadata | Secret bị lộ ở log hoặc hệ thống khác |
| **TLS tới database** | Nghe lén trên đường truyền | Đọc trái quyền khi đã đăng nhập hợp lệ |
| **Encryption at rest/backup** | Lộ dữ liệu từ disk hoặc backup | SELECT hợp lệ trả plaintext |
| **API authorization + tenant scope** | Đọc hoặc điều khiển Job qua API không hợp lệ | Quyền SQL trực tiếp quá rộng |
| **Audit + monitoring** | Giúp phát hiện và điều tra lạm dụng | Không tự ngăn sự kiện |
| **Retention + archival** | Giảm tồn dư dữ liệu và kích thước metadata | Không thay thế backup/restart strategy |
| **Idempotent writer + restart test** | Hậu quả của chạy lại sau crash | Không ngăn người lạ xem thông tin |
| **Migration kiểm soát** | Thay schema tùy tiện, lỗi cấu trúc metadata | Mã độc chạy dưới tài khoản được cấp quyền cao |

Không có một cấu hình đơn lẻ nào bảo vệ toàn bộ JobRepository. Hệ thống cần kết hợp kiểm soát quyền, giảm dữ liệu nhạy cảm, mã hóa, audit, sao lưu và kiểm thử.

## 21. Checklist triển khai cho production

- [ ] JobRepository sử dụng database/schema đúng và ổn định với mọi instance có liên quan.
- [ ] Runtime account không có quyền DBA/DDL không cần thiết.
- [ ] Dashboard observer chỉ đọc những trường cần thiết, ưu tiên view đã được thu hẹp.
- [ ] Mọi migration schema Batch chạy qua pipeline/role được kiểm soát.
- [ ] Không có password, API token hoặc secret thô trong JobParameters.
- [ ] ExecutionContext chỉ lưu trạng thái tối thiểu cần cho restart.
- [ ] ExitStatus/exception message và log không chứa raw payload nhạy cảm.
- [ ] REST/API vận hành có authentication, authorization theo hành động và tenant scope.
- [ ] Các thao tác start/restart/stop có audit và giới hạn lạm dụng.
- [ ] Database traffic, backup và storage được bảo vệ theo chính sách mã hóa.
- [ ] Credential được cấp qua secret manager/workload identity và có rotation.
- [ ] Có retention nhưng không xóa metadata của Job còn chạy hoặc cần restart.
- [ ] Không sửa STATUS/ExecutionContext bằng SQL tùy tiện để xử lý lỗi Job.
- [ ] Có metrics/cảnh báo cho thao tác quản trị, database authorization failure và bất thường repository.
- [ ] Môi trường dev/test không dùng chung repository/credential với production.
- [ ] Có integration test quyền DB, lộ dữ liệu, phân quyền API, restart và tính toàn vẹn metadata.

## 22. Quy trình vận hành an toàn khi cần điều tra lỗi Batch

Giả sử một Job nhập dữ liệu báo **FAILED** sau khi đã commit nhiều chunk. Một luồng xử lý có kiểm soát:

~~~text
Monitoring phát hiện Job FAILED
             |
             v
Người vận hành được xác thực
             |
             v
Đọc metadata qua JobExplorer / dashboard đã lọc
             |
             +--> Xem status, counts, execution IDs
             +--> Xem error code/correlation ID
             +--> Không mặc định xem params/context nhạy cảm
             |
             v
Điều tra log/audit được phân quyền
             |
             v
Đánh giá nguyên nhân và dữ liệu đã commit
             |
       +-----+------+
       |            |
    Restart      Remediate
    được phép    theo nghiệp vụ
       |            |
       +-----+------+
             |
             v
Đối soát output, kiểm tra không mất/trùng
             |
             v
Lưu kết quả xử lý + audit trail
~~~

Quy trình này giữ metadata phục vụ điều tra, không cấp quyền sửa database tùy ý và kiểm tra dữ liệu thực tế sau khi recovery.

**Bảo vệ metadata repository** không chỉ có nghĩa là giấu một vài bảng BATCH_*. Đó là việc coi JobRepository như **thành phần điều khiển cốt lõi của Spring Batch**, với thông tin có thể nhạy cảm và trạng thái ảnh hưởng trực tiếp tới restart. Khi áp dụng least privilege, hạn chế dữ liệu lưu, kiểm soát endpoint, bảo mật kết nối, retention và audit, hệ thống vừa bảo vệ thông tin, vừa giữ được tính toàn vẹn của quá trình xử lý batch và khả năng phục hồi sau lỗi.

