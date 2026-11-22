# Secret trong JobParameters — Security cho Spring Batch Core Processing

## 1. Tại sao không được truyền secret qua JobParameters?

Trong Spring Batch, `JobParameters` xác định lô công việc và cung cấp những đầu vào như ngày xử lý, tenant, nguồn dữ liệu hoặc tên file. Khi Job cần kết nối API hay hệ thống bên ngoài, lập trình viên đôi khi truyền thêm password, API key, OAuth token hoặc private key vào `JobParameters`:

~~~java
// Ví dụ sai: token có thể bị lưu trong JobRepository và log.
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("apiToken", "dummy-sensitive-token")
    .toJobParameters();
~~~

**JobParameters là metadata thực thi, không phải kho lưu trữ bí mật.** Với JDBC JobRepository, các giá trị parameter được persist để hỗ trợ nhận diện JobInstance và quản lý lịch sử JobExecution. Trong nhiều đường chạy, parameter còn xuất hiện trong log, dashboard, báo cáo vận hành, bản dump hoặc sao lưu database.

Đặc biệt, chuyển sang `.addString("apiToken", token, false)` **không làm secret an toàn hơn**. Cờ identifying=false chỉ loại parameter khỏi danh tính JobInstance; nó không yêu cầu Spring Batch che log, mã hóa hay bỏ qua persistence.

Mục tiêu bài học:

- Hiểu tham số định danh và đường đi của dữ liệu trong JobRepository.
- Nhận diện rò rỉ từ metadata, log, ExecutionContext, REST API và monitoring.
- Sử dụng business key hoặc tham chiếu không nhạy cảm để lấy secret tại runtime.
- Xây dựng Step dùng secret manager theo đúng scope và quyền.
- Xử lý rotation, retry và restart mà không nhúng credential vào metadata.
- Kiểm thử chống lộ secret, bảo vệ multi-tenant và xử lý secret đã lỡ bị lưu.

## 2. JobInstance, JobExecution và tham số định danh

~~~text
Job: importOrdersJob
Identifying parameters:
    businessDate = 2026-11-16
    tenantCode   = acme
                |
                v
          JobInstance #42
             /       \
            v         v
   JobExecution #101  JobExecution #102
        FAILED           COMPLETED
                         (restart)
~~~

Spring Batch nhận diện JobInstance bằng **tên Job và tập identifying JobParameters**. Nếu Job đã FAILED và được restart, execution mới thuộc cùng JobInstance. Nếu thay một identifying parameter, framework tạo một JobInstance khác.

Tham số phù hợp:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantCode", "acme", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
~~~

| Tham số | Có nên truyền? | Giải thích |
| --- | --- | --- |
| `businessDate` | Có | Kỳ xử lý nghiệp vụ, ổn định qua restart. |
| `tenantCode` | Có điều kiện | Có thể cần giới hạn quyền đọc metadata theo tenant. |
| `inputId` | Có điều kiện | Ưu tiên opaque ID hoặc đường dẫn được phê duyệt. |
| `credentialRef` | Có điều kiện | Chỉ khi reference không nhạy cảm và được kiểm quyền. |
| Password, API key, refresh token | **Không** | Credential có thể bị persist và log. |
| Private key, signing key | **Không** | Secret cần được quản lý bằng kho bí mật thích hợp. |
| JDBC URL có mật khẩu | **Không** | Chứa credential nhúng trong chuỗi. |

Không dùng token hoặc hash token làm identifying parameter. Khi token được rotate, JobInstance identity không nên thay đổi; kỳ dữ liệu vẫn là cùng một lô.

## 3. Secret có thể rò qua những đâu?

~~~text
      Scheduler / REST / CLI
              |
              v
         JobParameters
              |
        +-----+---------+
        |     |         |
        v     v         v
   JobRepo   Logs    Admin/Monitoring
        |     |         |
        v     v         v
    BATCH_*  Log DB    Dashboard/APM
        |     |         |
        +-----+---------+
              |
              v
        Backup / Export
~~~

| Đường rò rỉ | Nguy cơ |
| --- | --- |
| JDBC metadata | Giá trị JobParameter nằm trong bảng metadata, có thể được truy vấn bởi DBA/reporting service. |
| `JobParameters.toString()` | Log chứa toàn bộ các key/value. |
| REST request | Credential trong body/query có thể xuất hiện ở gateway, reverse proxy hoặc access log. |
| CLI | Giá trị argument có thể xuất hiện trong process listing và shell history. |
| `ExecutionContext` | Nếu token được lưu vào Job/Step context, serializer có thể persist nó. |
| Actuator/APM | Environment, request attributes, trace hoặc exception message chứa secret. |
| Metrics | Gắn token làm tag vừa rò rỉ vừa gây cardinality rất cao. |
| Backup/snapshot | Secret vẫn tồn tại dù Job và token ban đầu đã hết hạn. |

Trong Spring Batch **5.x**, bảng `BATCH_JOB_EXECUTION_PARAMS` thường có:

~~~text
JOB_EXECUTION_ID
PARAMETER_NAME
PARAMETER_TYPE
PARAMETER_VALUE
IDENTIFYING
~~~

Spring Batch 4.x và các phiên bản khác có thể dùng schema khác. Không sao chép câu SQL thay đổi metadata mà chưa kiểm schema và quan hệ với JobInstance key.

Để kiểm tên tham số đáng ngờ mà **không in giá trị**:

~~~sql
SELECT JOB_EXECUTION_ID, PARAMETER_NAME, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE LOWER(PARAMETER_NAME) IN (
    'password', 'apikey', 'api_token',
    'accesstoken', 'access_token', 'clientsecret'
);
~~~

Đây chỉ là bước rà soát sơ bộ: secret có thể bị giấu trong JSON dưới key `config`, và tham số `credentialRef` có thể chỉ là reference được cho phép.

## 4. Kiến trúc an toàn: resolve secret trong Step

Thay vì truyền secret raw, launcher chỉ gửi ID nghiệp vụ:

~~~text
Scheduler / Controller
    |
    | businessDate=2026-11-16
    | tenantCode=acme
    v
JobRepository
    |
    | Không có password/token
    v
StepScope Tasklet / Writer
    |
    | tenantCode
    v
CredentialResolver
    |
    +--> Server-side tenant mapping
                  |
                  v
          Secret Manager / Vault
                  |
                  v
              Credential
                  |
                  v
            API / DB client
~~~

Hai kiểu triển khai:

1. **Business key → server-side mapping:** Job nhận `tenantCode=acme`, ứng dụng ánh xạ sang identifier của secret tại cấu hình bảo mật phía server. Đây là lựa chọn ưu tiên khi client không được tự chọn credential.
2. **Secret reference:** Job nhận `credentialRef=partners/acme/token`, Step truy xuất giá trị thực từ kho secret. Chỉ áp dụng khi bản thân reference không được phân loại bí mật và quyền truy cập đã được kiểm.

Secret reference cũng có thể tiết lộ tên khách hàng hoặc môi trường. Nếu path nhạy cảm, dùng opaque ID hoặc business key và không đưa path vào JobParameters.

### Nguồn lưu secret

| Nguồn | Cách sử dụng | Điều cần kiểm |
| --- | --- | --- |
| HashiCorp Vault | Truy xuất KV hoặc dynamic credential | Token policy, TTL, audit và rotation. |
| AWS Secrets Manager | IAM role truy xuất secret | Quyền theo workload, không nhúng access key vào Job. |
| Google Cloud Secret Manager | Workload identity/service account | Quyền truy cập đúng resource và secret version. |
| Azure Key Vault | Managed identity | Quyền read secret/certificate tối thiểu. |
| Kubernetes Secret | Mount file hoặc environment | RBAC, etcd encryption, container access và secret rotation. |
| Token issuer riêng | Cấp token ngắn hạn | Hết hạn, refresh và giới hạn số lần retry. |

Ưu tiên **identity của workload** thay vì tạo thêm một master password tĩnh để ứng dụng truy cập secret manager.

## 5. Ví dụ Spring Batch 5.2: Tasklet lấy secret ở runtime

Giả định ứng dụng dùng Spring Boot 3.x, Spring Batch 5.2.x và Java 17+. Định nghĩa những interface ứng dụng:

~~~java
public interface CredentialResolver {
    // Implementation đọc token theo tenant và quyền workload.
    char[] resolvePartnerToken(String tenantCode);
}

public interface PartnerGateway {
    // Client không log hoặc persist token.
    void synchronize(String tenantCode, String businessDate, char[] token);
}
~~~

Tasklet được khởi tạo cho StepExecution với các JobParameters không nhạy cảm:

~~~java
import java.util.Arrays;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerBatchConfiguration {

    @Bean
    @StepScope
    Tasklet partnerTasklet(
            CredentialResolver resolver,
            PartnerGateway gateway,
            @Value("#{jobParameters['tenantCode']}") String tenantCode,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        return (contribution, chunkContext) -> {
            char[] token = resolver.resolvePartnerToken(tenantCode);
            try {
                gateway.synchronize(tenantCode, businessDate, token);
                return RepeatStatus.FINISHED;
            } finally {
                Arrays.fill(token, '\0');
            }
        };
    }
}
~~~

Cấu hình Step và Job:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step partnerStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        Tasklet partnerTasklet) {
    return new StepBuilder("partnerStep", repository)
            .tasklet(partnerTasklet, tx)
            .build();
}

@Bean
Job partnerJob(JobRepository repository, Step partnerStep) {
    return new JobBuilder("partnerJob", repository)
            .start(partnerStep)
            .build();
}
~~~

`char[]` cho phép xóa buffer mà code đang sở hữu, nhưng HTTP client hoặc SDK có thể tạo bản sao `String`, vì vậy không nên tuyên bố có thể xóa hoàn toàn secret khỏi heap. Không ghi token vào exception, log hoặc singleton mutable field chia sẻ giữa tenant/Job.

Với chunk-oriented Step, resolver có thể nằm trong HTTP client hoặc item writer. Cần có cache và refresh theo TTL nếu Step xử lý lâu, đồng thời kiểm quyền và tránh tải quá nhiều lên secret manager. Không chuyển refresh token vào JobParameters để giảm số lần resolve.

## 6. Chặn credential từ nơi nhận request

Một lỗi phổ biến là nhận map tham số tùy ý rồi tạo JobParameters:

~~~java
// Không nên: caller có thể gửi bất kỳ key/value nào.
for (Map.Entry<String, String> entry : rawRequest.entrySet()) {
    builder.addString(entry.getKey(), entry.getValue());
}
~~~

Thay bằng DTO allowlist:

~~~java
public record ImportRequest(
        String businessDate,
        String tenantCode) {
}

JobParameters parametersFor(ImportRequest request) {
    return new JobParametersBuilder()
            .addString("businessDate", request.businessDate(), true)
            .addString("tenantCode", request.tenantCode(), true)
            .toJobParameters();
}
~~~

Trước khi tạo parameters, API phải xác thực caller, kiểm quyền chạy Job với tenant và xác minh businessDate đúng định dạng. Không cho caller tùy ý chỉ định một secret path của tenant khác.

### JobParametersValidator làm lớp bảo vệ bổ sung

~~~java
import java.util.Locale;
import java.util.Set;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class NoRawSecretsValidator
        implements JobParametersValidator {

    private static final Set<String> FORBIDDEN = Set.of(
        "password", "passwd", "apikey", "api_key",
        "accesstoken", "access_token", "clientsecret",
        "client_secret", "privatekey");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {
        for (String name : parameters.getParameters().keySet()) {
            if (FORBIDDEN.contains(name.toLowerCase(Locale.ROOT))) {
                throw new JobParametersInvalidException(
                    "Raw credentials are forbidden in JobParameters");
            }
        }
    }
}
~~~

Đăng ký bằng `.validator(new NoRawSecretsValidator())` trong `JobBuilder`. Lớp kiểm này hữu ích nhưng **không phải cơ chế chính**: nó không phát hiện secret nằm dưới tên khác như `options` hay `config`. Tùy đường launcher và version, một số xử lý metadata/logging có thể xảy ra trước khi Job-level validation chạy. Hãy thực hiện input validation ở boundary trước khi truyền vào Batch.

## 7. Không lưu secret trong ExecutionContext

Cách làm dưới đây vẫn nguy hiểm:

~~~java
// Sai: Step ExecutionContext có thể được serialize vào database.
stepExecution.getExecutionContext()
    .putString("partnerToken", token);
~~~

Spring Batch dùng `ExecutionContext` lưu checkpoint của Job/Step; JDBC JobRepository có thể persist nó vào `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`.

Lưu các giá trị không phải secret để khôi phục:

~~~java
stepExecution.getExecutionContext()
    .putString("tenantCode", "acme");
stepExecution.getExecutionContext()
    .putLong("lastProcessedItemId", 1510L);
~~~

Khi restart, Step lấy lại `tenantCode` rồi yêu cầu secret mới từ resolver. Không đưa password, refresh token, access token, private key hoặc connection string có mật khẩu vào context.

Một số quy trình mã hóa/giải mã cần cố định **phiên bản khóa**. Khi đó có thể lưu version ID không nhạy cảm theo chính sách và để secret manager cấp key đúng phiên bản; không lưu key bytes raw.

## 8. Rotation, expiration và restart

~~~text
02:00  JobExecution #101 sử dụng token version A
02:20  JobExecution #101 FAILED
02:30  Secret manager rotate sang version B
03:00  JobExecution #102 restart cùng JobInstance
~~~

Nếu token A nằm trong JobParameters, nó có thể hết hạn và tồn tại trong metadata. Với resolver runtime, execution #102 có thể lấy token B, miễn là thay token không thay đổi ý nghĩa nghiệp vụ.

| Trường hợp | Chiến lược |
| --- | --- |
| Token chỉ dùng xác thực API | Resolve credential mới nhất ở runtime. |
| Token TTL ngắn so với thời gian Job | Client/resolver có refresh và retry có giới hạn. |
| Key dùng giải mã dữ liệu cũ | Pin version reference được phép, giữ version theo retention. |
| Secret bị revoke khẩn cấp | Rotate/revoke trong secret store, không thay identity JobInstance. |
| Restart trên node khác | Node mới dùng workload identity và quyền tương ứng. |

Đừng dùng token/hash của token làm identifying parameter: rotation sẽ làm biến đổi JobInstance identity và có thể khiến hệ thống xử lý lại từ đầu.

## 9. Chặn rò rỉ qua log, metrics và tracing

~~~java
// Chỉ log metadata đã được phê duyệt.
log.info("Starting job={} businessDate={} tenant={}",
        "partnerJob", businessDate, tenantCode);

// Tránh log raw JobParameters, Authorization header,
// request body chứa token, secret value hoặc URL có token.
~~~

Cần rà soát:

- Log framework, scheduler, Quartz, CI runner.
- `toString()` của JobParameters, request DTO và SDK credential.
- HTTP headers: Authorization, Cookie, X-API-Key.
- Exception message và structured log fields.
- APM traces, request/response capture, SQL bind parameters.
- Actuator `env`, `configprops`, heap dumps và support bundles.
- Dashboard và database metadata export.

Metric nên dùng tag cố định như job, step, status và failure category. Không gắn raw token, credential path nhạy cảm hoặc identifier duy nhất cho mỗi request vào Prometheus labels.

### Bảo mật truy cập metadata

Ngay cả khi không có raw secret, JobParameters vẫn có thể chứa tên tenant, tên file hoặc thời gian giao dịch. Bảo vệ quyền đọc `BATCH_*`, encryption at rest, TLS, retention và backup access. Mã hóa disk chỉ bảo vệ một lớp; người dùng được quyền đọc dữ liệu đã giải mã vẫn có thể thấy metadata.

## 10. Test không rò secret

### 10.1. Kiểm JobParameters sạch

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("tenantCode", "acme", true)
        .toJobParameters();

assertFalse(params.getParameters().containsKey("apiToken"));
assertFalse(params.getParameters().containsKey("password"));
assertFalse(params.getParameters().containsKey("clientSecret"));
~~~

Test này chỉ kiểm một builder; cần thêm test cho đường khởi chạy thật từ REST/CLI/scheduler. Nếu parser chấp nhận arbitrary key/value, caller vẫn có thể bypass bằng key khác.

### 10.2. Kiểm metadata JDBC

Trong integration test với Spring Batch 5.x và JDBC JobRepository:

~~~java
List<String> parameterNames = jdbcTemplate.queryForList(
    "SELECT PARAMETER_NAME " +
    "FROM BATCH_JOB_EXECUTION_PARAMS " +
    "WHERE JOB_EXECUTION_ID = ?",
    String.class,
    jobExecution.getId());

assertTrue(parameterNames.contains("businessDate"));
assertTrue(parameterNames.contains("tenantCode"));
assertFalse(parameterNames.contains("apiToken"));
assertFalse(parameterNames.contains("password"));
~~~

Chỉ truy vấn **tên** để không in nhầm giá trị secret ra test report. Cần dùng schema chính xác của phiên bản Batch trong dự án.

### 10.3. Test resolver, rotation và multi-tenant

1. Sử dụng fake CredentialResolver trả token thử nghiệm A.
2. Chạy Job có businessDate và tenantCode, cho Step fail ở điểm xác định.
3. Đổi fake token sang B, restart **cùng JobInstance**.
4. Xác nhận JobInstance ID không đổi, JobExecution ID mới và dữ liệu cuối đúng.
5. Kiểm raw token A/B không nằm trong JobParameters, ExecutionContext, log hoặc trace.
6. Thử caller tenant A yêu cầu credential của tenant B; API và resolver phải chặn.

Bài integration test dùng `@SpringBatchTest` và JDBC JobRepository để quan sát metadata thật. Không xóa bảng `BATCH_*` giữa lần FAILED và restart; không dùng credential production cho test.

## 11. Khi secret đã bị lưu trong JobRepository

Nếu phát hiện credential thật trong bảng metadata, việc đổi code mới không làm các bản sao lịch sử biến mất.

Quy trình xử lý:

1. **Ngăn lộ tiếp:** bỏ raw secret khỏi API/launcher, tắt đường log nhạy cảm và triển khai allowlist.
2. **Đánh giá phạm vi:** JobExecution, metadata DB, log backend, dashboard, trace, backup và snapshot nào có thể chứa credential.
3. **Giới hạn quyền:** chặn các tài khoản báo cáo hoặc endpoint không cần xem dữ liệu này.
4. **Rotate/revoke** credential đã lộ theo mức độ rủi ro.
5. **Kiểm JobInstance chưa hoàn thành:** sửa parameter cũ có thể ảnh hưởng khả năng restart của lô đã commit dữ liệu.
6. **Lập kế hoạch redaction/migration** metadata, log, backups theo schema và chính sách retention; thử trước trên môi trường cách ly.
7. **Ngăn hồi quy:** cập nhật test, code review và quy tắc logging.

**Không tự sửa/xóa cột `PARAMETER_VALUE` hoặc xóa bảng `BATCH_*` trong production** chỉ vì muốn làm sạch secret. JobRepository sử dụng metadata để nhận diện JobInstance và phục hồi execution; sửa không nhất quán có thể làm mất checkpoint hoặc tạo duplicate.

Token còn trong backup sẽ vẫn là rủi ro dù database live đã được xử lý. Rotate/revoke giúp giảm giá trị khai thác của bản sao cũ, đồng thời vẫn phải kiểm soát backup access.

## 12. Spring Batch 5.2 và 6.x

| Hạng mục | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| JobParametersBuilder | `org.springframework.batch.core.JobParametersBuilder` | Các type domain được tổ chức vào package như `org.springframework.batch.core.job.parameters`. |
| Khởi chạy Job | `JobLauncher.run(Job, JobParameters)` | `JobOperator.start(Job, JobParameters)` là hướng API mới. |
| Step tasklet | `new StepBuilder(name, repo).tasklet(tasklet, tx)` | Dùng builder/API phù hợp phiên bản 6.x. |
| Metadata JDBC | Schema `BATCH_JOB_EXECUTION_PARAMS` theo 5.x | Kiểm schema/migration JDBC của 6.x khi triển khai. |
| Nguyên tắc bảo mật | Tránh raw secret trong JobParameters/Context | **Không đổi**: vẫn phải tránh raw secret và che log. |

Nếu cấu hình repository resourceless trên một phiên bản, việc không thấy bảng JDBC không chứng minh cách truyền token là an toàn; credential vẫn đi qua API, process, log và memory.

## 13. Những sai lầm thường gặp

**Cho rằng identifying=false bảo vệ secret.** Cờ này chỉ tác động JobInstance identity.

**Đưa secret vào ExecutionContext để Step sau dùng.** Context có thể được persist và log.

**Mã hóa Base64 hoặc lưu token hash làm parameter.** Base64 không phải mã hóa; hash token không phải business identity và có thể làm thay đổi instance sau rotation.

**Cho caller gửi secretRef bất kỳ.** Có nguy cơ truy cập chéo tenant; phải kiểm quyền và ánh xạ server-side.

**Chỉ redaction ở frontend.** Giá trị có thể đã tồn tại trong DB, API response, log và backup.

**Giữ token trong singleton mutable field.** Dễ rò giữa tenant, sai khi concurrent Job và stale sau rotation.

**Dùng environment variable mà không xét quyền process và diagnostics.** Credential vẫn cần quyền hạn, masking, retention và lifecycle.

**Xóa metadata bị lộ ngay lập tức.** Có thể phá restart và history; phải có kế hoạch remediation.

## 14. Bài tập thực hành

### Bài 1 — So sánh metadata

Trên database test cô lập, truyền một **token giả** qua JobParameters để quan sát rủi ro lưu metadata; sửa launcher thành businessDate + tenantCode và xác nhận parameter mới không chứa token.

### Bài 2 — Tasklet lấy token runtime

Tạo fake CredentialResolver, một `@StepScope` Tasklet và fake PartnerGateway. Chạy Job thành công, kiểm token không xuất hiện trong JobParameters/ExecutionContext.

### Bài 3 — Input allowlist

Xây REST controller chỉ nhận businessDate và tenantCode; thử gửi password, apiKey, accessToken và JSON chứa token. API phải từ chối trước khi tạo JobParameters và không log raw body.

### Bài 4 — Rotation sau failure

Cho execution đầu fail với fake token A, đổi resolver sang token B rồi restart cùng JobInstance. Kiểm cùng instance ID, execution ID mới và dữ liệu cuối không trùng.

### Bài 5 — Multi-tenant isolation

Caller có quyền tenant A thử gửi tenant B hoặc một secretRef của tenant B. Phân quyền ở controller và resolver phải từ chối.

### Bài 6 — Logging test

Tạo lỗi giả trong HTTP client, dùng log capture xác nhận giá trị credential giả không xuất hiện ở logger, exception hoặc trace, trong khi JobExecution ID và failure category vẫn phục vụ chẩn đoán.

### Bài 7 — Lịch sử đã bị lộ

Với database test, mô phỏng secret giả đã lưu lâu ngày. Lập kế hoạch rotate, thu hẹp quyền, xử lý backup/log và migration an toàn trước khi xóa lịch sử metadata.

## 15. Tài liệu tham khảo

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch — Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch — ItemStream and ExecutionContext](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch 5.2 — JobParameters API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParameters.html)
- [Spring Batch 5.2 — JobParametersBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersBuilder.html)
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/index.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

