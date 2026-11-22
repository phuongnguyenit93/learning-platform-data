# Quyền gọi job launcher

`JobLauncher` là API dùng để yêu cầu Spring Batch chạy một job với một bộ `JobParameters`. Bản thân `JobLauncher` không xác thực người gọi và không quyết định người đó có quyền chạy job hay không. Ứng dụng phải đặt kiểm soát truy cập ở lớp API hoặc service trước khi gọi launcher.

Điều này quan trọng vì một job có thể đọc, sửa hoặc xuất dữ liệu với phạm vi rộng hơn quyền thông thường của người dùng. Người được phép đăng nhập vào ứng dụng không mặc nhiên được phép khởi chạy mọi job, truyền mọi tham số hoặc thao tác với dữ liệu của mọi tenant.

## 1. Phân biệt authentication và authorization

Có hai quyết định bảo mật riêng biệt:

- **Authentication (xác thực):** xác định ai đang gọi yêu cầu. Ví dụ người dùng đăng nhập qua session, access token OAuth2 hoặc một service account.
- **Authorization (phân quyền):** quyết định danh tính đó được phép thực hiện hành động nào trên job và dữ liệu nào. Ví dụ chỉ người có authority `BATCH_JOB_LAUNCH_IMPORT` mới được chạy job nhập đơn hàng.

Luồng gọi job nên có dạng:

```text
Người dùng / scheduler / service
             |
             v
      Authentication
             |
             v
     API hoặc launch service
             |
             v
        Authorization
             |
      +------+-------+
      |              |
   Được phép       Bị từ chối
      |              |
      v              v
  JobLauncher     403 / access denied
      |
      v
  JobRepository và JobExecution
```

Spring Batch quản lý vòng đời thực thi, metadata, trạng thái và restart. Chính sách người nào được phép yêu cầu thực thi thuộc trách nhiệm bảo mật của ứng dụng.

## 2. JobLauncher không tự kiểm tra quyền

API cơ bản của launcher nhận một `Job` cùng `JobParameters`:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

Lời gọi này yêu cầu Spring Batch khởi chạy job. `JobLauncher` không tự hỏi người gọi có role, authority, tenant hay quyền truy cập dữ liệu tương ứng hay không. Nếu một controller công khai gọi trực tiếp launcher mà không có lớp kiểm soát truy cập, bất kỳ caller nào vượt qua được lớp HTTP đó đều có thể yêu cầu chạy job.

`JobRepository` có các kiểm tra về trạng thái và danh tính execution, chẳng hạn từ chối một JobInstance đang chạy hoặc đã hoàn thành với cùng identifying parameters. Những kiểm tra này phục vụ tính đúng đắn và điều phối batch; chúng không phải authorization. Một người không có quyền vẫn có thể vượt qua kiểm tra trạng thái nếu ứng dụng không chặn yêu cầu từ trước.

Tương tự, `JobOperator` cung cấp các thao tác quản lý như start, restart, stop và abandon, nhưng các phương thức đó cũng không thay thế chính sách phân quyền của ứng dụng.

## 3. Bảo vệ điểm gọi bằng Spring Security

Với ứng dụng Spring, có thể dùng Spring Security để bảo vệ endpoint HTTP và service khởi chạy job. Một cách dễ duy trì là đặt quy tắc quyền trên service chuyên trách, để mọi đường gọi từ controller hoặc thành phần khác đều đi qua cùng một chính sách.

Bật method security:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
```

Sau đó yêu cầu authority cụ thể ở service:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final TenantAuthorization tenantAuthorization;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            TenantAuthorization tenantAuthorization) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.tenantAuthorization = tenantAuthorization;
    }

    @PreAuthorize("hasAuthority('BATCH_JOB_LAUNCH_IMPORT')")
    public JobExecution launchImport(
            LocalDate businessDate, String tenantId) throws JobExecutionException {

        Authentication caller = SecurityContextHolder.getContext().getAuthentication();
        tenantAuthorization.assertCanLaunchFor(caller, tenantId);

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("tenantId", tenantId, true)
            .addString("requestedBy", caller.getName(), false)
            .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

Trong ví dụ này:

- `@PreAuthorize` yêu cầu caller có authority `BATCH_JOB_LAUNCH_IMPORT` trước khi method được thực hiện.
- `TenantAuthorization` kiểm tra caller có quyền chạy cho tenant được yêu cầu hay không.
- Job và bộ parameters được chọn trong service; caller không thể tùy ý chỉ định một bean Job khác.
- `requestedBy` lưu danh tính người yêu cầu để phục vụ audit. Đây là parameter non-identifying vì người yêu cầu không xác định đơn vị công việc nghiệp vụ.
- `businessDate` và `tenantId` là identifying parameters trong ví dụ vì chúng xác định tập dữ liệu cần xử lý.

`@EnableMethodSecurity` cần được bật để các annotation như `@PreAuthorize` có hiệu lực. Method cần được gọi qua Spring proxy; lời gọi nội bộ từ method này sang method khác trong cùng object (self-invocation) có thể bỏ qua interceptor bảo mật. Vì vậy, hãy đặt điểm kiểm soát trên một bean service được gọi từ bean khác hoặc bảo vệ thêm tại lớp gọi.

Authority là chuỗi do ứng dụng và hệ thống cấp danh tính thống nhất. Có thể dùng role như `ROLE_BATCH_OPERATOR`, nhưng với các hành động batch khác nhau, authority cụ thể thường giúp phân quyền chính xác hơn.

## 4. Không mở một endpoint chạy mọi job tùy ý

Một thiết kế rủi ro là tạo endpoint tổng quát nhận tên job và map parameters từ request rồi chuyển thẳng cho launcher:

```java
// Không nên dùng endpoint tổng quát thiếu kiểm soát như thế này
@PostMapping("/api/batch/run")
public JobExecution run(
        @RequestParam String jobName,
        @RequestBody Map<String, String> parameters) {
    Job job = jobRegistry.getJob(jobName);
    return jobLauncher.run(job, toJobParameters(parameters));
}
```

Caller có thể thử tên job nội bộ, gửi tham số ngoài dự kiến hoặc kích hoạt một luồng xử lý có quyền dữ liệu cao hơn quyền của họ. Việc kiểm tra đăng nhập ở endpoint vẫn chưa đủ.

Nên cung cấp endpoint theo nghiệp vụ, chẳng hạn `POST /api/batch/imports`, và để service chọn job cụ thể. Với mỗi loại job, xác định rõ:

- Authority nào được phép khởi chạy.
- Parameters nào được chấp nhận và kiểu dữ liệu của chúng.
- Caller được phép xử lý tenant, tài khoản, ngày nghiệp vụ hoặc phạm vi dữ liệu nào.
- Giới hạn tần suất, khối lượng và số execution đồng thời.
- Kết quả nào được trả về cho caller và thông tin nào chỉ dành cho vận hành.

Ví dụ controller nhận một request DTO có cấu trúc cố định:

```java
public record ImportRequest(
        @NotNull LocalDate businessDate,
        @NotBlank String tenantId) {
}

@RestController
@RequestMapping("/api/batch/imports")
public class ImportController {

    private final BatchLaunchService launchService;

    @PostMapping
    public ResponseEntity<LaunchResponse> launch(
            @Valid @RequestBody ImportRequest request) throws JobExecutionException {

        JobExecution execution = launchService.launchImport(
            request.businessDate(), request.tenantId());

        return ResponseEntity.accepted().body(
            new LaunchResponse(execution.getId(), execution.getStatus().name()));
    }
}
```

Ví dụ minh họa cách tách request khỏi service; phần `SecurityFilterChain` vẫn cần bảo vệ endpoint theo authority hoặc policy phù hợp. Service cũng tự kiểm tra quyền tenant nên một đường gọi khác không thể vô tình bỏ qua kiểm tra phạm vi dữ liệu.

## 5. Phân quyền theo từng hành động

Không nên gộp mọi thao tác batch vào một quyền `BATCH_ADMIN`. Một người có thể được phép khởi chạy một job nghiệp vụ nhưng không được phép dừng hoặc abandon execution của người khác.

| Hành động | Authority gợi ý | Mục đích |
|---|---|---|
| Khởi chạy job nhập dữ liệu | `BATCH_JOB_LAUNCH_IMPORT` | Yêu cầu chạy một loại job cụ thể |
| Khởi chạy đối soát | `BATCH_JOB_LAUNCH_RECONCILIATION` | Chạy job đối soát có phạm vi riêng |
| Xem trạng thái execution | `BATCH_JOB_READ` | Đọc trạng thái và thông tin được phép hiển thị |
| Xem chi tiết lỗi | `BATCH_JOB_READ_DETAILS` | Truy cập stack trace hoặc thông tin vận hành nhạy cảm |
| Restart execution | `BATCH_JOB_RESTART` | Yêu cầu tiếp tục một execution thất bại/dừng |
| Stop execution | `BATCH_JOB_STOP` | Yêu cầu dừng một execution đang chạy |
| Abandon execution | `BATCH_JOB_ABANDON` | Đánh dấu execution không tiếp tục theo quy trình vận hành |
| Quản trị cấu hình batch | `BATCH_ADMIN` | Thay đổi cấu hình hoặc chính sách quản trị |

Các authority trên là ví dụ do ứng dụng tự định nghĩa, không phải danh sách quyền Spring Batch tự tạo. Hãy gán quyền theo trách nhiệm thực tế và dùng nguyên tắc least privilege: mỗi tài khoản chỉ có quyền cần cho công việc của mình.

Đối với thao tác restart, stop hoặc abandon, nên kiểm tra thêm trạng thái execution và phạm vi tài nguyên mà caller được quản lý. Ví dụ, quyền `BATCH_JOB_STOP` không nhất thiết cho phép dừng mọi job trong hệ thống.

## 6. Kiểm soát JobParameters và phạm vi dữ liệu

JobParameters có thể quyết định job xử lý dữ liệu nào. Do đó, authorization phải xét cả hành động khởi chạy lẫn giá trị parameters.

Ví dụ người dùng có quyền chạy job nhập dữ liệu nhưng chỉ được phép xử lý tenant `tenant-42`. Nếu request gửi `tenantId=tenant-99`, service phải từ chối trước khi gọi `JobLauncher`, dù caller có authority khởi chạy job.

Các quy tắc nên áp dụng:

1. **Allow-list parameters.** Chỉ nhận các parameter được thiết kế cho job; từ chối key không biết hoặc kiểu dữ liệu sai.
2. **Xác thực giá trị.** Kiểm tra ngày nghiệp vụ, mã lô, tên tệp, giới hạn khoảng thời gian và các ràng buộc nghiệp vụ.
3. **Kiểm tra quyền theo tài nguyên.** So sánh tenant, account, region hoặc business unit trong request với phạm vi caller được phép.
4. **Không tin dữ liệu phân quyền từ request.** Nếu tenant hoặc user scope có thể suy ra từ token/session, hãy lấy từ danh tính đã xác thực hoặc đối chiếu với dịch vụ phân quyền phía server.
5. **Không đưa secret vào JobParameters.** Parameters có thể được lưu trong metadata và xuất hiện trong log hoặc công cụ quản trị; không truyền password, access token, private key hay credential.
6. **Chọn identifying flag đúng nghiệp vụ.** Parameter làm thay đổi đơn vị công việc phải tham gia định danh; thông tin audit như người yêu cầu thường không nên tạo JobInstance mới.

Không nên dùng một parameter `tenantId` do caller tự khai báo làm bằng chứng caller được phép truy cập tenant đó. Parameter mô tả phạm vi công việc; authorization service mới quyết định caller có quyền với phạm vi ấy hay không.

## 7. Danh tính người yêu cầu và danh tính thực thi

Một job có thể được yêu cầu bởi người dùng nhưng thực thi trên thread nền hoặc bởi worker process. Cần phân biệt:

- **Requester:** người dùng hoặc hệ thống đã yêu cầu khởi chạy.
- **Execution identity:** tài khoản dịch vụ hoặc tiến trình thực sự chạy job và truy cập tài nguyên.
- **Business scope:** tenant, khách hàng, kỳ dữ liệu hoặc tập bản ghi mà job được phép xử lý.

Khi audit, nên lưu requester, thời điểm yêu cầu, nguồn gọi, job name, parameters không nhạy cảm, execution ID, kết quả và lý do khởi chạy. Có thể ghi vào bảng audit riêng hoặc lưu một trường phù hợp trong JobParameters/metadata. Nếu lưu `requestedBy` trong JobParameters, hãy cân nhắc việc dữ liệu này được giữ trong repository và có thể được người có quyền đọc metadata xem.

Không nên phụ thuộc hoàn toàn vào `SecurityContextHolder` bên trong step để xác định người yêu cầu. Với launcher chạy bất đồng bộ, step có thể chạy trên thread khác. Spring Security context thường gắn với thread; nó không tự động được truyền sang mọi executor.

Nếu step thật sự cần SecurityContext, hãy cấu hình cơ chế truyền context rõ ràng, ví dụ `DelegatingSecurityContextTaskExecutor` hoặc `TaskDecorator` thích hợp. Thường tốt hơn là ghi requester vào audit metadata một cách tường minh trước khi bắt đầu execution, rồi để job dùng dữ liệu audit đã lưu. Không truyền đối tượng request web hoặc access token vào job nền.

## 8. Job được gọi bởi scheduler hoặc service account

Không phải mọi job đều được khởi chạy bởi người dùng đang đăng nhập. Một scheduler, message consumer hoặc hệ thống điều phối khác có thể gọi launch service.

Trong trường hợp này, hãy xác định danh tính hệ thống riêng, ví dụ `service:nightly-import`, và cấp đúng authority cho job đó. Audit cần phân biệt execution tự động với yêu cầu do người dùng tạo.

Nếu service dùng method security, lời gọi từ scheduler có thể không có authentication trong `SecurityContextHolder` và bị từ chối. Đây là hành vi cần dự liệu. Hãy thiết lập service principal hoặc một entry point nội bộ có chính sách rõ ràng, thay vì bỏ toàn bộ kiểm tra bảo mật chỉ để scheduler chạy được.

Không nên cấp tài khoản scheduler quyền quản trị toàn bộ batch nếu nó chỉ cần chạy một job theo lịch. Cũng cần bảo vệ endpoint nội bộ, message channel hoặc scheduler trigger để người ngoài không thể giả mạo yêu cầu tự động.

## 9. Bảo vệ endpoint và thông tin execution

Khi job được khởi chạy qua HTTP, áp dụng các chính sách bảo mật phù hợp với loại client:

- Với ứng dụng web dùng session/cookie, bảo vệ request thay đổi trạng thái bằng CSRF token và quy tắc session phù hợp.
- Với API dùng OAuth2/JWT, xác thực issuer, audience, chữ ký, thời hạn token và authority/scope được ánh xạ.
- Dùng HTTPS để bảo vệ token và dữ liệu truyền qua mạng.
- Giới hạn tốc độ và số yêu cầu khởi chạy để tránh caller tạo quá nhiều execution hoặc làm cạn tài nguyên.
- Ghi audit cho yêu cầu bị từ chối và yêu cầu được chấp nhận theo chính sách logging của hệ thống.
- Không trả stack trace, SQL, thông tin kết nối hoặc toàn bộ ExecutionContext cho caller không có quyền đọc chi tiết.

Việc xem trạng thái job cũng là một quyền riêng. Thông tin như tên tệp, tenant, số bản ghi, exception message và tham số nghiệp vụ có thể tiết lộ dữ liệu nội bộ. Hãy lọc response theo authority và phạm vi tài nguyên tương tự lúc khởi chạy.

## 10. Quyền gọi job và xử lý yêu cầu chạy trùng

Authorization trả lời câu hỏi caller có được phép yêu cầu chạy job hay không. Sau khi caller được phép, Spring Batch còn áp dụng các quy tắc về JobInstance và trạng thái execution.

Ví dụ, hai yêu cầu cùng chạy `importOrders` với cùng identifying parameters có thể dẫn đến lỗi instance đã chạy hoặc đang chạy. Đây là kiểm soát trạng thái của JobRepository, không phải dấu hiệu caller thiếu quyền.

API nên xử lý riêng các tình huống:

| Tình huống | Cách phản hồi phù hợp |
|---|---|
| Caller không có authority | Từ chối truy cập, thường là HTTP 403 |
| Caller chưa xác thực | Yêu cầu xác thực, thường là HTTP 401 với API token |
| Parameters không hợp lệ | Trả lỗi validation, thường là HTTP 400 |
| JobInstance đang chạy hoặc đã hoàn thành | Trả thông tin xung đột/trạng thái phù hợp, không diễn giải thành lỗi phân quyền |
| Job được chấp nhận chạy bất đồng bộ | Trả mã execution để caller theo dõi, thường dùng HTTP 202 |

Có thể dùng request ID hoặc idempotency key ở lớp API để nhận diện yêu cầu gửi lại do timeout. Cần thiết kế key và lưu kết quả yêu cầu sao cho retry từ client không vô tình tạo một công việc nghiệp vụ mới.

## 11. Những lỗi phân quyền thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Cho rằng JobLauncher tự kiểm tra role | Người dùng đã đăng nhập có thể chạy job ngoài quyền | Bảo vệ controller/service bằng Spring Security |
| Chỉ kiểm tra role mà không kiểm tra tenant | Caller có thể yêu cầu job xử lý dữ liệu tenant khác | Kiểm tra quyền trên từng tài nguyên và parameter |
| Cho caller truyền tên job tùy ý | Có thể kích hoạt job nội bộ hoặc job đặc quyền | Dùng endpoint nghiệp vụ và allow-list job |
| Cho caller truyền mọi JobParameters | Có thể thay đổi phạm vi dữ liệu hoặc cấu hình ngoài dự kiến | DTO cố định, allow-list và validation |
| Dùng một quyền admin cho mọi thao tác | Khó giới hạn tác động của operator | Tách quyền launch, read, restart, stop và abandon |
| Dựa vào SecurityContext trong worker thread | Job nền có thể không thấy danh tính người gọi | Lưu requester rõ ràng hoặc cấu hình context propagation |
| Không audit người yêu cầu | Khó truy vết ai đã khởi chạy một execution | Lưu requester, thời gian, nguồn gọi và execution ID |
| Đưa credential vào JobParameters | Secret có thể bị lưu trong metadata hoặc log | Dùng secret manager và cấu hình kết nối an toàn |

## 12. Quy trình kiểm tra trước khi cho phép launch

Trước khi gọi `JobLauncher`, launch service nên thực hiện theo trình tự:

1. Xác thực caller đã được Spring Security nhận diện.
2. Kiểm tra authority được phép khởi chạy đúng loại job.
3. Kiểm tra quyền với tenant hoặc phạm vi dữ liệu yêu cầu.
4. Kiểm tra và chuẩn hóa các JobParameters theo hợp đồng của job.
5. Ghi nhận audit request và danh tính requester.
6. Gọi `JobLauncher.run(job, parameters)`.
7. Trả execution ID và trạng thái ban đầu phù hợp; cung cấp endpoint đọc trạng thái được bảo vệ riêng.

Với các thao tác quản trị như restart, stop và abandon, áp dụng chính sách riêng dựa trên quyền và trạng thái execution. Không tái sử dụng quyền launch như quyền quản trị mặc định.

## Kết luận

`JobLauncher` chỉ cung cấp cơ chế khởi chạy job; nó không tự xác thực hoặc phân quyền caller. Ứng dụng cần bảo vệ điểm gọi bằng Spring Security, giới hạn loại job và JobParameters, kiểm tra quyền trên tenant hoặc dữ liệu cụ thể, đồng thời tách quyền launch khỏi quyền đọc, restart, stop và abandon.

Khi job chạy bất đồng bộ hoặc được gọi bởi scheduler, hãy lưu danh tính requester và audit một cách tường minh. Kết hợp kiểm soát truy cập với validation, giới hạn tài nguyên và chính sách idempotency để chỉ những yêu cầu hợp lệ mới có thể tạo execution.
