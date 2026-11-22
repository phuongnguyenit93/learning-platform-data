# Bảo vệ secret không lưu trực tiếp vào metadata

Spring Batch lưu metadata để nhận diện JobInstance, theo dõi JobExecution và StepExecution, đồng thời hỗ trợ restart. JobParameters và ExecutionContext là một phần của dữ liệu metadata này. Vì vậy, nếu truyền password, API token, private key hoặc credential trực tiếp vào JobParameters hay ExecutionContext, giá trị đó có thể được ghi xuống repository cùng lịch sử chạy của Job.

Metadata repository không phải là secret vault. Cách an toàn là lưu secret trong hệ thống quản lý bí mật hoặc cấu hình bảo mật của ứng dụng, sau đó chỉ truyền một tham chiếu không nhạy cảm vào Job khi cần. Step lấy tham chiếu đó để truy xuất secret đúng thời điểm thực thi.

## 1. Vì sao metadata của Spring Batch cần được bảo vệ?

Spring Batch cần lưu trạng thái để biết một Job đã chạy hay chưa, Step nào đã hoàn thành, execution nào thất bại và có thể restart từ đâu. JobRepository lưu các thông tin này trong kho metadata.

Các nhóm dữ liệu thường được lưu gồm:

- Tên Job và thông tin định danh JobInstance.
- JobParameters của từng JobExecution.
- Trạng thái, thời gian chạy và exit status của JobExecution, StepExecution.
- ExecutionContext ở phạm vi Job và Step.
- Thông tin phục vụ restart và theo dõi tiến độ.

Với JDBC JobRepository, các phiên bản Spring Batch thường dùng các bảng metadata có tiền tố BATCH_. Ví dụ:

| Nhóm dữ liệu | Bảng metadata thường gặp |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| JobParameters | BATCH_JOB_EXECUTION_PARAMS |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| StepExecution | BATCH_STEP_EXECUTION |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Tên cột và cấu trúc bảng có thể khác giữa các phiên bản Spring Batch. Điểm cần nhớ là JobParameters và ExecutionContext được repository lưu bền vững để phục vụ lịch sử và restart.

Do đó, nếu một secret được đưa vào những đối tượng này, secret có thể xuất hiện trong database metadata, bản sao lưu, bản export, công cụ quản trị hoặc hệ thống giám sát có quyền đọc metadata.

## 2. Không truyền secret trực tiếp trong JobParameters

Một cách làm không an toàn là đưa API key hoặc password vào JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("apiToken", apiToken, false)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

Đặt apiToken là non-identifying không làm giá trị này trở thành bí mật hoặc tránh việc lưu metadata. Cờ identifying chỉ quyết định parameter có tham gia xác định JobInstance hay không. Nó không phải cờ bảo mật, không che giá trị và không ngăn repository lưu parameter.

Tương tự, không nên đưa secret vào các kiểu JobParameter khác, kể cả khi secret được mã hóa trước ở tầng gọi nhưng ứng dụng lại giải mã và lưu giá trị rõ ở một nơi khác.

Một số dữ liệu không nên xuất hiện trong JobParameters:

- Password database hoặc password của tài khoản dịch vụ.
- API key, access token, refresh token và bearer token.
- Private key, nội dung certificate có khóa riêng hoặc passphrase.
- Client secret OAuth.
- Mã khôi phục, signing key và credential của cloud provider.
- Chuỗi kết nối có chứa username/password.
- Bất kỳ giá trị nào cho phép người đọc metadata truy cập hệ thống hoặc thực hiện hành động thay mặt ứng dụng.

JobParameters nên chứa dữ liệu mô tả công việc như ngày nghiệp vụ, mã lô, ID file, tenant, chế độ xử lý hoặc tham chiếu đến cấu hình bảo mật.

## 3. Dùng secret reference thay cho secret value

Thay vì truyền giá trị bí mật, truyền một tên hoặc tham chiếu để ứng dụng tìm secret trong hệ thống quản lý bí mật.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFileId", "file-8421", true)
        .addString("credentialRef", "orders-api/prod", false)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

Trong ví dụ, orders-api/prod là định danh cấu hình hoặc tên secret trong secret manager. Nó không chứa credential thực tế.

Luồng xử lý:

~~~text
API / Scheduler
      |
      | JobParameters:
      | businessDate, sourceFileId, credentialRef
      v
  JobLauncher
      |
      v
  JobRepository
      |
      | Lưu metadata và tham chiếu
      v
  JobExecution
      |
      v
  Step bắt đầu
      |
      | Đọc credentialRef
      v
  SecretProvider
      |
      | Xác thực quyền và truy xuất secret
      v
  Secret Manager
      |
      | Trả secret trong thời gian sử dụng
      v
  Gọi dịch vụ bên ngoài
~~~

JobRepository chỉ cần lưu tham chiếu để nhận diện cấu hình cần dùng. SecretProvider lấy secret từ secret manager tại thời điểm cần thiết, sau đó component xử lý dùng secret để xác thực với hệ thống đích.

Các secret manager phổ biến có thể được cung cấp bởi nền tảng cloud, hệ thống vault nội bộ hoặc dịch vụ quản lý khóa và credential của tổ chức. Chọn nhà cung cấp theo môi trường triển khai và cơ chế xác thực workload của ứng dụng.

### Thiết kế tham chiếu

Một reference tốt nên:

- Không chứa secret hoặc token có thể dùng trực tiếp.
- Có ý nghĩa ổn định, dễ phân quyền và dễ quản lý.
- Chỉ cho phép truy cập đúng secret mà Job cần.
- Có thể xác định môi trường hoặc ứng dụng, ví dụ orders-api/prod.
- Không tiết lộ thông tin nhạy cảm qua tên nếu metadata được nhiều người xem.

Không dùng URL chứa token, signed URL, chuỗi kết nối có password hoặc đường dẫn có embedded credential làm reference.

Nếu reference tự nó có khả năng cấp quyền truy cập secret, ví dụ một bearer token hoặc signed link, thì nó cũng là secret và không được lưu trong metadata.

## 4. Truy xuất secret trong Step khi thực thi

Có thể định nghĩa một abstraction để Step không phụ thuộc trực tiếp vào một nhà cung cấp secret cụ thể:

~~~java
public interface SecretProvider {
    char[] getSecret(String reference);
}
~~~

Implementation của SecretProvider có thể gọi API của secret manager, sử dụng workload identity hoặc credential do môi trường triển khai cấp. Không nên hard-code master key hoặc token truy cập secret manager trong source code.

Một Tasklet có thể nhận reference từ JobParameters bằng Step scope rồi truy xuất secret khi thực thi:

~~~java
@Bean
@StepScope
Tasklet callOrdersApiTasklet(
        @Value("#{jobParameters['credentialRef']}")
        String credentialRef,
        SecretProvider secretProvider,
        OrdersApiClient ordersApiClient) {

    return (contribution, chunkContext) -> {
        char[] secret = secretProvider.getSecret(credentialRef);

        try {
            ordersApiClient.submitPendingOrders(secret);
        } finally {
            Arrays.fill(secret, '\0');
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

Ở đây:

- JobParameters chỉ chứa credentialRef.
- @StepScope trì hoãn việc tạo Tasklet cho đến khi Step chạy, khi JobParameters đã có sẵn.
- SecretProvider truy xuất secret theo reference.
- Secret chỉ được dùng trong phạm vi thao tác cần xác thực.
- finally giúp xóa nội dung mảng ký tự sau khi sử dụng trong phạm vi mà ứng dụng kiểm soát được.

Đoạn mã minh họa cần được điều chỉnh theo API client thực tế. Một số thư viện chuyển credential thành String hoặc giữ bản sao trong bộ nhớ; Java String không thể được xóa nội dung một cách đáng tin cậy. Nếu client lưu credential nội bộ, hãy xem tài liệu thư viện và giới hạn vòng đời client/credential phù hợp.

Không đưa giá trị secret vào exception message, log hoặc nội dung trả về từ Tasklet. Nếu truy xuất secret thất bại, hãy ném lỗi có thông tin chẩn đoán an toàn, chẳng hạn mã reference không nhạy cảm và correlation ID, nhưng không in giá trị secret.

### Dùng reference từ cấu hình ứng dụng

Nếu một Job luôn dùng cùng một secret theo môi trường, không nhất thiết phải đưa reference vào JobParameters. Có thể cấu hình alias trong application configuration và inject vào bean, trong khi secret value vẫn được truy xuất từ SecretProvider.

Ví dụ abstraction:

~~~java
@ConfigurationProperties(prefix = "app.credentials")
public record CredentialProperties(String ordersApiReference) {
}
~~~

Cấu hình theo môi trường có thể chứa alias không nhạy cảm:

~~~yaml
app:
  credentials:
    orders-api-reference: orders-api/prod
~~~

Sau đó inject CredentialProperties vào Step hoặc service và gọi SecretProvider bằng alias. Không đặt secret value trực tiếp trong file cấu hình được commit vào source control. Nếu cấu hình được lấy từ environment variable hoặc mounted file, vẫn cần bảo vệ quyền đọc và tránh in toàn bộ environment/configuration ra log.

## 5. JobParameters non-identifying vẫn có thể được lưu

Một hiểu lầm thường gặp là chỉ identifying JobParameters mới được lưu trong metadata. Trên thực tế, identifying là thuộc tính dùng để xác định JobInstance. Non-identifying parameter vẫn là một phần của JobParameters gắn với JobExecution và có thể được lưu trong repository.

Ví dụ:

~~~java
new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "orders-api/prod", false)
        .toJobParameters();
~~~

Trong trường hợp này:

- businessDate tham gia vào danh tính JobInstance.
- credentialRef không tham gia vào danh tính JobInstance.
- Cả hai đều có thể xuất hiện trong metadata của execution.

Do đó, đánh dấu một parameter là non-identifying chỉ phù hợp khi muốn thay đổi giá trị đó mà không tạo JobInstance mới. Không dùng cờ này để che giấu password hoặc token.

Tương tự, không nên dựa vào việc đổi kiểu parameter, đổi tên key hoặc đặt một giá trị vào parameter không được dùng trong flow để tránh lưu trữ. Nếu nó là JobParameter, hãy giả định repository có thể lưu giá trị đó.

## 6. Không chuyển secret vào ExecutionContext

ExecutionContext dùng để lưu trạng thái cần thiết cho restart và trao đổi metadata giữa các Step. Job ExecutionContext và Step ExecutionContext cũng được JobRepository lưu bền vững.

Vì vậy, các cách sau đều không an toàn:

~~~java
// Không làm như vậy.
jobExecution.getExecutionContext()
        .putString("apiToken", apiToken);

// Cũng không làm như vậy.
stepExecution.getExecutionContext()
        .put("databasePassword", databasePassword);
~~~

Không lưu secret trong:

- Job ExecutionContext.
- Step ExecutionContext.
- Custom execution context key.
- ExitStatus hoặc thông tin mô tả lỗi.
- Custom JobParameter object.
- Execution attribute hoặc metadata tự bổ sung có thể được persist.

Thay vào đó, chỉ lưu reference, ID cấu hình hoặc phiên bản secret không nhạy cảm nếu Step sau cần dùng. Khi Step sau chạy, nó truy xuất secret từ SecretProvider theo reference.

ExecutionContext phù hợp với vị trí đọc, ID bản ghi cuối, tên file, checksum, mã lô và các giá trị nhỏ phục vụ restart. Nó không phải nơi lưu credential.

## 7. Bảo vệ secret trong log, exception và monitoring

Ngay cả khi secret không được lưu trong JobParameters, ứng dụng vẫn có thể vô tình làm lộ nó qua log hoặc metadata khác.

Ví dụ không an toàn:

~~~java
log.info("Launching import with parameters: {}", jobParameters);
log.error("API call failed using token " + apiToken, exception);
throw new IllegalStateException("Invalid password: " + password);
~~~

Các cách này có thể đưa secret vào log aggregation, APM, alert, exception tracker hoặc response HTTP. Hãy log tên Job, JobExecution ID, mã lô và trạng thái cần thiết; không log toàn bộ parameter map nếu có nguy cơ chứa dữ liệu nhạy cảm.

Ví dụ log an toàn hơn:

~~~java
log.info(
        "Launching job={}, sourceFileId={}, businessDate={}, requestId={}",
        "importOrders",
        sourceFileId,
        businessDate,
        requestId
);
~~~

Khi ghi nhận lỗi truy xuất secret, chỉ cung cấp thông tin không nhạy cảm:

~~~java
throw new IllegalStateException(
        "Cannot resolve configured credential reference for orders API",
        cause
);
~~~

Cần kiểm soát cả những vị trí sau:

- Log của ứng dụng và framework.
- HTTP access log và request/response body logging.
- Distributed tracing span attributes.
- Metric label và dashboard.
- Error tracking và crash report.
- Audit event.
- Message dead-letter queue.
- File tạm và bản dump khi xử lý lỗi.

Không đưa secret vào metric label. Metric thường có phạm vi truy cập rộng và được lưu lâu dài; chỉ dùng các dimension không nhạy cảm như tên Job, Step, môi trường hoặc mã trạng thái.

## 8. Phân quyền truy cập secret manager

Dùng secret manager chỉ có hiệu quả nếu quyền truy cập được giới hạn đúng.

Nên cấp quyền theo nguyên tắc least privilege:

- Job nhập đơn hàng chỉ được đọc secret cần cho API đơn hàng.
- Môi trường development không được đọc secret production.
- Developer không mặc nhiên cần quyền đọc secret production chỉ vì họ có quyền xem source code.
- Mỗi workload hoặc service account có danh tính riêng.
- Quyền đọc, cập nhật và xoay vòng secret được tách biệt khi phù hợp.
- Các lần truy cập secret có audit log, nhưng audit log không ghi giá trị secret.

Ưu tiên workload identity hoặc cơ chế xác thực của nền tảng triển khai để ứng dụng lấy secret. Nếu cần credential bootstrap, credential đó cũng phải được cấp phát và bảo vệ qua cơ chế quản lý bí mật của môi trường.

Không đặt master credential của secret manager trong JobParameters, ExecutionContext, source code hoặc file YAML được commit.

## 9. Restart và vòng đời của secret

Restart tạo ra một JobExecution mới cho cùng JobInstance khi trạng thái và cấu hình cho phép. Vì vậy, cần quyết định Step restart sẽ dùng secret nào.

Có hai cách quản lý phổ biến:

**Dùng alias trỏ đến secret hiện tại.** Reference như orders-api/prod luôn trỏ đến phiên bản đang hoạt động. Khi restart, Step có thể nhận credential mới nhất. Cách này thuận tiện khi secret được rotate thường xuyên, nhưng cần bảo đảm credential mới vẫn có quyền và tương thích với công việc đang tiếp tục.

**Dùng reference đến một phiên bản cụ thể.** Nếu secret manager hỗ trợ versioned secret, có thể dùng alias kèm mã phiên bản không nhạy cảm để Step lấy đúng phiên bản. Điều này giúp execution restart có hành vi ổn định hơn khi cần hoàn thành cùng một lô công việc.

Ví dụ JobParameters có thể chứa:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "orders-api/prod", false)
        .addString("credentialVersion", "version-17", false)
        .toJobParameters();
~~~

credentialVersion ở đây chỉ là định danh phiên bản, không phải credential. Nó vẫn có thể được lưu trong metadata, vì vậy chỉ sử dụng nếu mã phiên bản không nhạy cảm.

Nếu muốn giữ nguyên hành vi khi restart, phải truyền lại cùng reference và version phù hợp. Đừng tự động tạo một JobInstance mới chỉ vì secret đã rotate; hãy phân biệt việc thay credential dùng để truy cập dịch vụ với việc thay đổi đơn vị công việc nghiệp vụ.

Nếu phiên bản secret cũ đã bị thu hồi vì sự cố bảo mật, yêu cầu an toàn phải được ưu tiên. Khi đó, Job có thể cần dừng và xử lý lại theo chính sách nghiệp vụ thay vì cố dùng lại credential đã bị thu hồi.

## 10. Mã hóa database metadata có đủ không?

Mã hóa database hoặc disk at rest là một lớp bảo vệ hữu ích. Nó giảm rủi ro khi thiết bị lưu trữ, snapshot hoặc bản backup bị truy cập trái phép. Tuy nhiên, mã hóa at rest không biến metadata repository thành secret manager.

Khi ứng dụng hoặc một tài khoản database được cấp quyền đọc metadata, dữ liệu sau giải mã vẫn có thể được truy cập. Nếu secret đã được lưu như một JobParameter, các hệ thống truy vấn metadata, công cụ hỗ trợ vận hành hoặc bản export có thể đọc được giá trị đó tùy quyền.

Nên kết hợp:

- Không lưu secret value trong metadata.
- Phân quyền database theo vai trò và môi trường.
- Mã hóa kết nối ứng dụng đến database.
- Mã hóa storage và backup.
- Giới hạn quyền truy vấn các bảng metadata.
- Có chính sách retention và cleanup cho JobRepository.
- Quản lý khóa mã hóa tách biệt với dữ liệu được mã hóa.

Nếu tổ chức có yêu cầu mã hóa trường metadata cụ thể, cần thiết kế và kiểm thử cơ chế bảo vệ tương ứng theo phiên bản Spring Batch và repository đang dùng. Không giả định rằng Spring Batch tự động mã hóa hoặc che mọi JobParameter nhạy cảm.

## 11. Nếu secret đã từng được ghi vào metadata

Nếu một phiên bản ứng dụng trước đây đã truyền password hoặc token trực tiếp trong JobParameters hoặc ExecutionContext, chỉ sửa code để ngừng truyền secret sẽ không xóa các giá trị đã được lưu.

Cần xử lý cả giá trị đã tồn tại:

1. Xác định loại secret và các Job/JobExecution có thể đã lưu nó.
2. Rotate hoặc revoke secret nếu có khả năng đã bị lộ cho người không được phép.
3. Kiểm tra phạm vi log, export, backup và hệ thống giám sát có thể chứa bản sao.
4. Áp dụng chính sách retention và cleanup metadata đã được tổ chức phê duyệt.
5. Xử lý backup theo quy trình lưu trữ và hết hạn của hệ thống.
6. Xác nhận code mới chỉ lưu reference và không log secret.

Không xóa tùy tiện các hàng metadata của Job đang chạy hoặc cần restart. Xóa metadata không đúng cách có thể làm mất khả năng restart, phá vỡ quan hệ khóa ngoại hoặc khiến lịch sử execution không còn nhất quán. Dùng quy trình cleanup chính thức và tuân thủ yêu cầu audit/retention.

## 12. Kiểm tra thiết kế trước khi đưa Job vào vận hành

Khi tích hợp secret vào một Spring Batch Job, cần xác nhận:

| Nội dung | Điều cần xác nhận |
|---|---|
| JobParameters | Chỉ chứa business data và secret reference không nhạy cảm |
| Identifying flag | Được dùng để xác định JobInstance, không dùng như cơ chế bảo mật |
| ExecutionContext | Không chứa password, token, private key hoặc credential |
| SecretProvider | Truy xuất secret bằng danh tính workload và quyền tối thiểu |
| Step scope | Secret chỉ được truy xuất khi Step cần thực thi |
| Log và exception | Không ghi giá trị secret hoặc dump toàn bộ parameters |
| Restart | Quyết định rõ dùng alias hiện tại hay secret version cố định |
| Rotation | Có quy trình đổi secret mà không làm hỏng công việc đang chạy |
| Database metadata | Có phân quyền, mã hóa kết nối, backup và retention phù hợp |
| Legacy metadata | Đã có kế hoạch xử lý nếu secret từng được lưu trước đây |

Một cách kiểm tra hữu ích là chạy Job trong môi trường thử nghiệm với secret giả, sau đó truy vấn metadata repository và log để xác nhận chỉ có reference xuất hiện. Không dùng secret production làm dữ liệu kiểm thử. Cũng cần kiểm tra rằng restart vẫn lấy được secret theo chính sách đã chọn và tài khoản workload không thể đọc các secret ngoài phạm vi được cấp.

## 13. Mô hình triển khai khuyến nghị

Một mô hình rõ ràng có thể được tổ chức như sau:

~~~text
JobLauncher
    |
    | JobParameters:
    |   businessDate
    |   sourceFileId
    |   credentialRef
    v
JobRepository
    |
    | Lưu parameters và execution metadata
    | Không lưu secret value
    v
StepExecution
    |
    | Nhận credentialRef
    v
SecretProvider
    |
    | Dùng workload identity
    v
Secret Manager
    |
    | Trả secret cho thao tác cần thiết
    v
External API
~~~

JobParameters xác định lô công việc và tham chiếu cấu hình. JobRepository lưu metadata phục vụ nhận diện, theo dõi và restart. SecretProvider chịu trách nhiệm truy xuất bí mật bằng quyền của workload. Step dùng secret trong phạm vi ngắn nhất có thể và không ghi lại nó vào ExecutionContext, log hoặc exception.

Thiết kế này giữ được khả năng restart của Spring Batch mà không biến metadata thành nơi lưu trữ credential. Khi cần thay đổi secret, nhóm vận hành quản lý vòng đời trong secret manager; khi cần restart một Job, framework vẫn dùng JobParameters và checkpoint không nhạy cảm để nhận diện đúng công việc.

