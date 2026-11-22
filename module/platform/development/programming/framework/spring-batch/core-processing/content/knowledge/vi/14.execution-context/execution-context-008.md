# Không lưu dữ liệu nhạy cảm tùy ý

ExecutionContext là nơi Spring Batch lưu trạng thái cần thiết để tiếp tục một job hoặc step sau khi bị gián đoạn. Nó rất hữu ích cho checkpoint, ví dụ vị trí reader đã đọc, khóa cuối cùng đã xử lý hoặc mã batch đang chạy. Nhưng vì context được JobRepository lưu cùng metadata batch, mọi giá trị đưa vào đó có thể tồn tại lâu trong database, backup, bản sao dữ liệu và công cụ vận hành.

Vì vậy, **không dùng ExecutionContext như một kho bí mật, cache tùy tiện hoặc nơi cất toàn bộ dữ liệu đầu vào**. Không lưu password, access token, private key, session cookie hay payload nhạy cảm nếu không có yêu cầu và biện pháp bảo vệ được thiết kế rõ ràng. Hãy lưu những checkpoint nhỏ, cần thiết cho restart; với dữ liệu nhạy cảm, lưu một tham chiếu có kiểm soát rồi lấy dữ liệu từ nguồn được bảo vệ khi cần.

Bài này giải thích dữ liệu nào phù hợp với context, dữ liệu nào không nên lưu, vì sao serialization không đồng nghĩa với encryption, những nơi metadata có thể bị lộ và các mẫu triển khai an toàn cho batch production.

## 1. ExecutionContext dùng để làm gì?

ExecutionContext là một vùng key/value mà Spring Batch dùng để giữ trạng thái thực thi. Nó hỗ trợ framework khôi phục tiến độ sau restart, đồng thời cho phép các thành phần batch chia sẻ một số thông tin có phạm vi xác định.

Spring Batch có hai phạm vi context chính:

| Context | Phạm vi | Cách dùng điển hình |
|---|---|---|
| Job ExecutionContext | Thuộc một JobExecution, có thể được chia sẻ giữa các step trong job đó | Mã batch, thông tin điều phối nhỏ cần cho các step tiếp theo |
| Step ExecutionContext | Thuộc một StepExecution | Checkpoint của reader, offset, khóa cuối cùng đã đọc |

Ví dụ reader đọc theo khóa tăng dần có thể lưu ID cuối cùng:

```java
executionContext.putLong("lastProcessedId", lastProcessedId);
```

Khi restart, reader lấy lại giá trị này để tiếp tục từ vị trí phù hợp. Đây là trạng thái điều khiển nhỏ, không phải dữ liệu nghiệp vụ đầy đủ của bản ghi.

### ExecutionContext được lưu ở đâu?

Với JDBC JobRepository, Spring Batch lưu context vào metadata database, thường trong các bảng:

- BATCH_JOB_EXECUTION_CONTEXT: context ở cấp job execution.
- BATCH_STEP_EXECUTION_CONTEXT: context ở cấp step execution.

Schema JDBC thường có các cột lưu bản tóm tắt và nội dung serialized, chẳng hạn SHORT_CONTEXT và SERIALIZED_CONTEXT; tên cột và kiểu dữ liệu phụ thuộc phiên bản Spring Batch và database.

Điều này có nghĩa context có thể được đọc bởi người hoặc ứng dụng có quyền truy cập metadata database. Nó cũng có thể được sao lưu, replicate, export hoặc xuất hiện trong công cụ quản trị nếu các công cụ đó hiển thị metadata.

### put() không phải là một vùng lưu tạm riêng tư

Lệnh putString, putLong hoặc put thay đổi context trong bộ nhớ của execution. Spring Batch lưu context theo lifecycle và transaction/checkpoint của job hoặc step. Với step dùng ItemStream, phương thức update(ExecutionContext) được gọi để ghi checkpoint tại các ranh giới phù hợp, thường gắn với chunk commit.

Không nên giả định mỗi lần gọi put() sẽ được ghi ngay xuống database, cũng không nên giả định dữ liệu chỉ tồn tại trong bộ nhớ. Khi framework lưu context, dữ liệu trở thành một phần của metadata có thể được giữ lại để restart và tra cứu.

## 2. Những dữ liệu nào phù hợp để lưu?

Chỉ lưu dữ liệu nhỏ, ít nhạy cảm và thực sự cần để khôi phục tiến độ hoặc truyền trạng thái giữa các step.

Các ví dụ thường phù hợp:

- Số dòng hoặc offset đã đọc.
- ID tăng dần của bản ghi cuối cùng đã xử lý.
- Số lượng item đã kiểm tra hoặc một bộ đếm checkpoint.
- Mã batch nội bộ không mang thông tin bí mật.
- ID của file/object bất biến và checksum để xác định chính xác nguồn.
- Phiên bản định dạng dữ liệu hoặc mã schema cần thiết để tiếp tục.
- Một cờ điều khiển nhỏ có ý nghĩa rõ ràng trong flow.

Ví dụ:

```java
executionContext.putLong("lastInvoiceId", 845_200L);
executionContext.putLong("recordsValidated", 12_500L);
executionContext.putString("inputObjectId", "object-7f31a2");
executionContext.putString("inputSha256", expectedChecksum);
```

Những giá trị này mô tả tiến độ hoặc tham chiếu đến dữ liệu nguồn. Chúng không chứa nội dung bí mật của invoice, thông tin xác thực hay toàn bộ file.

### Tiêu chí chọn một giá trị để lưu

Trước khi thêm key mới, hãy hỏi:

1. Nếu process dừng ngay bây giờ, restart có thật sự cần giá trị này không?
2. Có thể tính lại giá trị từ một nguồn đáng tin cậy không?
3. Giá trị có nhỏ và ổn định qua lần deploy không?
4. Giá trị có chứa bí mật, dữ liệu cá nhân hoặc payload nghiệp vụ nhạy cảm không?
5. Ai có thể đọc metadata, backup và log của job?
6. Giá trị cần tồn tại bao lâu và khi nào có thể cleanup?

Nếu giá trị không cần cho restart hoặc điều phối, đừng đưa nó vào context chỉ vì API cho phép.

## 3. Không lưu secret trực tiếp trong ExecutionContext

Các loại dữ liệu sau không nên được ghi trực tiếp vào context:

- Mật khẩu database, password của tài khoản dịch vụ.
- API key, bearer token, OAuth access token hoặc refresh token.
- Private key, certificate có private key, signing secret.
- Session cookie, credential tạm thời hoặc signed URL có quyền truy cập.
- Connection string chứa username/password.
- Thông tin thanh toán nhạy cảm như dữ liệu thẻ cần được bảo vệ đặc biệt.
- Payload chứa dữ liệu cá nhân hoặc dữ liệu khách hàng vượt quá mức cần thiết cho checkpoint.

Ví dụ không an toàn:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("dbPassword", databasePassword);
context.putString("partnerAccessToken", accessToken);
context.putString("privateKey", privateKeyPem);
context.putString("customerEmail", customerEmail);
```

Các giá trị trên có thể được serialize vào metadata database. Chúng có thể còn tồn tại sau khi job hoàn tất và được giữ trong backup hoặc môi trường staging/analytics. Người có quyền đọc bảng batch có thể xem được dữ liệu nếu serializer không mã hóa ở tầng ứng dụng.

Không đưa secret vào JobParameters để thay thế. Job parameters cũng được lưu trong metadata, thường ở BATCH_JOB_EXECUTION_PARAMS, và có thể xuất hiện trong log khởi chạy, command line hoặc công cụ vận hành. Đánh dấu parameter là non-identifying không làm nó trở nên bí mật.

## 4. Serialization không phải encryption

Spring Batch cần chuyển ExecutionContext thành dạng có thể lưu trong repository. Serializer có thể biến object thành chuỗi hoặc dạng byte để ghi database. Đây là **serialization**, không tự động là mã hóa bảo mật.

Ví dụ, một giá trị có thể được biểu diễn dưới dạng text hoặc Base64. Base64 chỉ là encoding; người có dữ liệu có thể decode nó. Tương tự, việc dữ liệu nằm trong cột SERIALIZED_CONTEXT không có nghĩa người đọc database không thể khôi phục nội dung.

Phân biệt:

| Cơ chế | Mục đích | Có bảo vệ secret khỏi người đọc dữ liệu không? |
|---|---|---|
| Serialization | Chuyển object thành dạng lưu trữ/truyền tải | Không |
| Base64 hoặc encoding | Biểu diễn dữ liệu theo định dạng khác | Không |
| Database encryption at rest | Bảo vệ file lưu trữ hoặc volume khi nằm trên đĩa | Có giới hạn; không che dữ liệu với ứng dụng và người có quyền truy vấn |
| TLS khi truyền | Bảo vệ dữ liệu trên đường truyền | Không bảo vệ dữ liệu sau khi lưu |
| Application-level encryption | Mã hóa giá trị trước khi lưu | Có, nếu khóa được quản lý tách biệt và đúng cách |

Không suy ra tính bí mật từ tên serializer hoặc tên cột database. Hãy xác định serializer đang cấu hình, nơi dữ liệu được lưu và ai có quyền đọc.

### Vì sao mã hóa database vẫn chưa đủ cho mọi trường hợp?

Encryption at rest bảo vệ dữ liệu khi storage bị truy cập trực tiếp hoặc thiết bị bị lấy cắp, tùy mô hình triển khai. Nhưng ứng dụng và tài khoản database được cấp quyền vẫn có thể đọc dữ liệu đã giải mã. Backup, replica, export hoặc bản dump cũng cần được bảo vệ riêng.

Nếu một secret không cần thiết phải nằm trong metadata, cách tốt nhất là không lưu nó ở đó. Mã hóa không biến việc lưu secret tùy tiện thành một thiết kế tốt.

## 5. Mẫu an toàn: lưu secret reference, lấy secret khi chạy

Thay vì lưu token thật, hãy lưu một tên tham chiếu hoặc ID không nhạy cảm của secret trong hệ thống quản lý secret.

Ví dụ context chỉ giữ reference:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("credentialRef", "batch/partner-api");
```

Khi cần gọi API, service lấy secret từ secret manager:

```java
public class PartnerApiClient {

    private final SecretProvider secretProvider;
    private final HttpClient httpClient;

    public PartnerApiClient(
            SecretProvider secretProvider,
            HttpClient httpClient) {
        this.secretProvider = secretProvider;
        this.httpClient = httpClient;
    }

    public PartnerResponse send(PartnerRequest request) {
        String token = secretProvider.getSecret("batch/partner-api");

        return httpClient.post(
                "/invoices",
                request,
                token);
    }
}
```

SecretProvider là abstraction của ứng dụng; implementation có thể đọc từ secret manager của nền tảng. Token được lấy tại thời điểm cần dùng, không được ghi vào context hoặc log.

Reference cũng cần được xem xét:

- Dùng tên/ID không chứa credential hoặc token.
- Hạn chế quyền đọc context nếu tên secret tiết lộ hệ thống hoặc tenant nhạy cảm.
- Không lưu presigned URL hoặc URL có embedded credential; đó có thể là bearer secret.
- Kiểm soát ai được quyền phân giải reference thành secret thật.

### Secret rotation và restart

Secret manager có thể trả về giá trị mới sau khi credential được rotate. Đây thường là điều mong muốn: lần restart dùng credential hiện hành. Nếu một giao dịch nghiệp vụ yêu cầu gắn với một phiên bản credential cụ thể, chỉ lưu version/reference của secret theo chính sách được phê duyệt; vẫn không lưu secret material trong context.

Không dùng giá trị token làm identifying JobParameter. Token thay đổi khi rotate và không phải danh tính của lô nghiệp vụ.

## 6. Mẫu an toàn: lưu ID và checksum thay vì payload

Một job có thể cần đọc file hoặc payload lớn. Không cần đưa toàn bộ nội dung vào ExecutionContext. Hãy lưu dữ liệu ở nơi phù hợp và chỉ giữ tham chiếu ổn định:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("sourceObjectId", sourceObjectId);
context.putString("sourceVersion", sourceVersion);
context.putString("sourceChecksum", sha256);
context.putLong("lastReadOffset", lastReadOffset);
```

Khi restart:

1. Lấy object theo ID/version.
2. Kiểm tra checksum hoặc version để xác nhận nội dung không thay đổi.
3. Mở lại nguồn và tiếp tục từ checkpoint.
4. Nếu object đã bị xóa hoặc thay đổi, fail rõ ràng thay vì âm thầm đọc nội dung khác.

Với payload chứa dữ liệu nhạy cảm, lưu nó trong hệ thống có encryption, access control, audit và retention phù hợp. Context chỉ lưu opaque ID; không lưu nội dung hoặc signed download URL.

### Vì sao checksum hữu ích?

Giữ cùng một object ID chưa đủ nếu object có thể bị ghi đè. Checksum hoặc immutable object version giúp phát hiện trường hợp restart đang đọc một nội dung khác với lần chạy ban đầu.

Checksum không mã hóa dữ liệu và không che giấu nội dung. Nó chỉ giúp xác nhận tính toàn vẹn/đồng nhất của dữ liệu.

## 7. Lưu checkpoint đúng phạm vi Job hay Step

Chọn đúng context scope giúp giảm chia sẻ trạng thái không cần thiết:

- Dùng step context cho trạng thái chỉ có ý nghĩa với reader/writer của step đó.
- Dùng job context cho một giá trị nhỏ cần được step sau sử dụng.
- Không đưa toàn bộ dữ liệu của step trước vào job context chỉ để truyền sang step sau.

Ví dụ một reader triển khai ItemStreamReader lưu khóa cuối cùng:

```java
public class InvoiceIdReader implements ItemStreamReader<Invoice> {

    private static final String LAST_ID_KEY = "lastInvoiceId";

    private final InvoiceRepository repository;
    private long lastInvoiceId;

    public InvoiceIdReader(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastInvoiceId = context.getLong(LAST_ID_KEY, 0L);
    }

    @Override
    public Invoice read() {
        Invoice next = repository.findNextAfter(lastInvoiceId);
        if (next == null) {
            return null;
        }

        lastInvoiceId = next.id();
        return next;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastInvoiceId);
    }

    @Override
    public void close() {
        // Release resources if this reader owns any.
    }
}
```

Ví dụ giả định ID là khóa tăng dần, query có thứ tự ổn định và findNextAfter chỉ đọc trong tập dữ liệu đã được chốt. Trong triển khai thật, reader phải xử lý đúng ranh giới transaction, late-arriving data và concurrency. Không dùng email, token hay toàn bộ entity làm checkpoint nếu chỉ cần khóa cuối cùng.

### Context giữa các step

Nếu step đầu cần truyền một mã lô cho step sau, có thể đặt một giá trị nhỏ trong job execution context theo lifecycle phù hợp, chẳng hạn từ listener sau khi kiểm tra input. Step sau đọc lại cùng key. Hãy đặt tên key có namespace rõ ràng, ví dụ import.batchId, để tránh xung đột giữa các step.

Không dùng job context làm kho chia sẻ tùy tiện cho nhiều thread. Với partitioning hoặc multi-threaded step, cần xem xét phạm vi context và cơ chế đồng bộ của từng execution.

## 8. Không lưu object lớn hoặc DTO tùy ý

Một lỗi phổ biến là đưa cả object hoặc collection vào context vì nó tiện:

```java
// Không nên
context.put("allInvoices", invoices);
context.put("customerProfile", customerProfile);
context.put("httpResponse", response);
context.put("requestBody", fullRequestBody);
```

Điều này tạo ra nhiều rủi ro:

- Metadata phình to và làm tăng chi phí serialize/deserialize.
- Mỗi checkpoint có thể phải lưu dữ liệu lớn.
- Object thay đổi cấu trúc giữa các phiên bản ứng dụng có thể không tương thích khi restart.
- DTO có thể chứa thông tin cá nhân, secret hoặc dữ liệu nghiệp vụ không cần thiết.
- Context khó tra cứu và khó cleanup theo chính sách dữ liệu.

Hãy lưu payload ở bảng staging hoặc object storage có kiểm soát, sau đó lưu ID, version, checksum và checkpoint cần thiết trong context.

### Giữ context ổn định qua lần deploy

Execution có thể được restart bằng phiên bản ứng dụng mới. Nếu context chứa object Java tùy ý, thay đổi class, package, kiểu dữ liệu hoặc serializer có thể khiến dữ liệu cũ không deserialize được.

Các primitive, string ID, version và offset thường dễ duy trì tương thích hơn. Nếu buộc phải lưu cấu trúc phức tạp, hãy version schema context, định nghĩa migration và kiểm thử restart từ metadata của phiên bản trước.

## 9. JobParameters cũng là metadata cần bảo vệ

Một số ứng dụng tránh ExecutionContext nhưng lại đưa secret vào JobParameters. Đây không phải cách thay thế an toàn.

Job parameters được lưu cùng job execution để Spring Batch có thể nhận diện và mô tả lần chạy. Cả identifying và non-identifying parameters đều là dữ liệu metadata.

Ví dụ không an toàn:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("username", username, false)
        .addString("password", password, false)
        .addString("accessToken", token, false)
        .toJobParameters();
```

Tham số non-identifying vẫn được lưu. Cờ identifying chỉ điều khiển việc tạo JobInstance; nó không điều khiển quyền truy cập hay mã hóa.

Ví dụ phù hợp hơn:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("inputObjectId", objectId, true)
        .addString("requestId", requestId, false)
        .toJobParameters();
```

Secret được phân giải từ secret manager bằng cấu hình hoặc reference được bảo vệ trong runtime. Không truyền secret qua command line nếu có nguy cơ lộ trong process listing, shell history hoặc log của scheduler.

## 10. Những vị trí khác có thể làm lộ dữ liệu

Không chỉ hai bảng execution context mới cần bảo vệ. Giá trị nhạy cảm có thể vô tình xuất hiện ở nhiều nơi:

| Vị trí | Cách dữ liệu có thể xuất hiện |
|---|---|
| BATCH_JOB_EXECUTION_CONTEXT | Job context được serialize |
| BATCH_STEP_EXECUTION_CONTEXT | Step checkpoint và dữ liệu được lưu trong context |
| BATCH_JOB_EXECUTION_PARAMS | Job parameters, kể cả non-identifying |
| BATCH_JOB_EXECUTION.EXIT_MESSAGE | Exception message hoặc nội dung lỗi do ứng dụng tạo |
| Application log | Dump context, parameters, request/response hoặc stack trace chứa giá trị |
| Scheduler/command line | Tham số launch được ghi vào log hoặc process metadata |
| APM/tracing | HTTP headers, query parameters hoặc payload bị capture |
| Database backup/replica/export | Bản sao của metadata database |
| Dashboard/admin tool | Màn hình hiển thị parameters hoặc execution context |

Ví dụ exception message không nên chứa token:

```java
// Không nên
throw new IllegalStateException(
        "Partner request failed with token: " + accessToken);

// Nên
throw new IllegalStateException(
        "Partner request failed; correlationId=" + correlationId);
```

Log correlation ID, job execution ID, batch ID và mã lỗi. Tránh log credential, raw payload hoặc toàn bộ context.

## 11. Bảo vệ metadata database và công cụ vận hành

Ngay cả khi context chỉ chứa dữ liệu tối thiểu, metadata repository vẫn cần được bảo vệ:

- Cấp quyền đọc/ghi theo least privilege cho ứng dụng và người vận hành.
- Tách tài khoản ứng dụng khỏi tài khoản dashboard/reporting nếu cần.
- Bật TLS cho kết nối database.
- Mã hóa database volume và backup theo chính sách nền tảng.
- Giới hạn quyền truy cập bản dump, replica và môi trường non-production.
- Không cho dashboard mặc định hiển thị toàn bộ serialized context.
- Ghi audit log cho thao tác đọc/xuất metadata nhạy cảm.
- Có retention policy cho job execution, context và backup.

Nếu một nhóm support chỉ cần biết job đã xử lý đến ID nào, hãy cung cấp API hoặc màn hình chỉ hiển thị checkpoint đã được chọn lọc. Không cấp quyền truy vấn toàn bộ context database chỉ để xem một con số.

### Mã hóa ở tầng ứng dụng khi thật sự bắt buộc

Nếu có yêu cầu hợp lệ phải lưu một giá trị nhạy cảm trong metadata, cần đánh giá bảo mật riêng. Một phương án là mã hóa giá trị trước khi đưa vào context bằng envelope encryption:

1. Ứng dụng yêu cầu KMS tạo hoặc dùng data encryption key.
2. Giá trị được mã hóa trước khi lưu.
3. Context chỉ chứa ciphertext, key version và metadata tối thiểu.
4. Khóa giải mã được quản lý bên ngoài metadata database.
5. Quyền decrypt được giới hạn cho service account cần thiết.
6. Có quy trình rotation, revoke và xử lý backup cũ.

Không tự thiết kế thuật toán mã hóa hoặc hard-code encryption key trong source code, application properties hay cùng database với ciphertext. Nếu có thể, vẫn nên lưu reference thay vì secret material.

## 12. Retention và cleanup của ExecutionContext

Context có thể tồn tại lâu hơn thời gian chạy job vì nó gắn với execution metadata và hỗ trợ restart/điều tra. Cần quy định thời gian lưu:

- Giữ context của execution đang chạy hoặc còn cần restart.
- Giữ lịch sử theo yêu cầu kiểm toán và vận hành.
- Xóa metadata cũ bằng quy trình cleanup được kiểm thử và hiểu quan hệ bảng.
- Đồng bộ retention giữa metadata database, backup, replica, log và object storage.
- Xác định cách xử lý dữ liệu khi job hoàn tất và hết thời hạn restart.

Không xóa thủ công một dòng context đang được execution sử dụng để “xóa secret” mà không đánh giá ảnh hưởng. Xóa metadata sai thứ tự có thể làm hỏng restart hoặc tính toàn vẹn tham chiếu. Nếu secret đã bị lưu nhầm, trước hết hãy thu hồi/rotate secret, sau đó thực hiện quy trình xử lý dữ liệu theo chính sách và bảo toàn audit cần thiết.

## 13. Nếu đã lỡ lưu secret vào context thì làm gì?

Hãy coi secret đó có khả năng đã bị lộ cho mọi principal có quyền đọc metadata, log, backup hoặc công cụ quản trị tương ứng.

Quy trình xử lý nên gồm:

1. **Thu hồi hoặc rotate secret** ở hệ thống phát hành ngay khi có thể.
2. **Xác định phạm vi**: job/step execution nào chứa giá trị, thời điểm lưu, database, replica, backup, log và dashboard liên quan.
3. **Kiểm tra truy cập**: xem audit log và quyền truy cập metadata trong khoảng thời gian liên quan.
4. **Ngăn tái diễn**: sửa code để lấy secret qua secret manager và không ghi giá trị vào context/parameters/log.
5. **Xử lý dữ liệu lưu trữ** theo quy trình retention, incident response và yêu cầu kiểm toán; không xóa tùy tiện metadata đang cần cho restart.
6. **Kiểm tra bản sao**: xác định cách xử lý backup, export và môi trường non-production theo chính sách tổ chức.

Đừng chỉ xóa key khỏi context hiện tại rồi coi sự cố đã kết thúc. Giá trị cũ có thể vẫn tồn tại trong execution lịch sử, backup, log hoặc bản sao database. Rotate/revoke secret là bước quan trọng vì việc xóa một bản ghi không bảo đảm mọi bản sao đã biến mất.

## 14. Ví dụ tổng hợp: reader checkpoint an toàn và secret được lấy riêng

Một step có thể lưu checkpoint bằng ID, còn API client lấy credential từ secret provider:

```java
public class PartnerInvoiceReader implements ItemStreamReader<Invoice> {

    private static final String LAST_ID = "partner.lastInvoiceId";

    private final InvoiceRepository repository;
    private long lastInvoiceId;

    public PartnerInvoiceReader(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastInvoiceId = context.getLong(LAST_ID, 0L);
    }

    @Override
    public Invoice read() {
        Invoice invoice = repository.findNextAfter(lastInvoiceId);
        if (invoice == null) {
            return null;
        }
        lastInvoiceId = invoice.id();
        return invoice;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastInvoiceId);
    }

    @Override
    public void close() {
    }
}
```

API client không đọc token từ context:

```java
public class PartnerClient {

    private final SecretProvider secretProvider;
    private final HttpClient httpClient;

    public PartnerClient(
            SecretProvider secretProvider,
            HttpClient httpClient) {
        this.secretProvider = secretProvider;
        this.httpClient = httpClient;
    }

    public void publish(Invoice invoice) {
        String token = secretProvider.getSecret("batch/partner-api");
        httpClient.post("/invoices", invoice, token);
    }
}
```

Context chỉ giữ partner.lastInvoiceId. Secret được phân giải ở runtime từ một nguồn có quyền truy cập riêng. Nếu job restart, reader khôi phục checkpoint và client lấy credential hiện hành theo chính sách rotation.

Trong hệ thống thật, cần bảo đảm query reader có thứ tự ổn định, input được chốt phù hợp và writer/API có idempotency key để xử lý an toàn khi request được gửi lại.

## 15. Checklist trước khi thêm key vào ExecutionContext

Trước khi gọi put, hãy xác nhận:

- Giá trị thật sự cần cho checkpoint, restart hoặc điều phối.
- Giá trị nhỏ, có kiểu dữ liệu và tên key ổn định.
- Không chứa password, token, private key, cookie hoặc signed URL.
- Không chứa toàn bộ entity, collection lớn hoặc request/response payload.
- Nếu cần dữ liệu nhạy cảm, context chỉ giữ reference/ID đã được đánh giá.
- Secret được lấy từ secret manager ở runtime và không bị log.
- Job parameters cũng không chứa credential.
- Job context và step context được dùng đúng phạm vi.
- Serializer và schema context tương thích qua các lần deploy.
- Metadata database, backup, replica, dashboard và log có quyền truy cập/retention phù hợp.
- Có quy trình rotate/revoke và xử lý sự cố nếu dữ liệu nhạy cảm bị lưu nhầm.

## 16. Kết luận thực hành

ExecutionContext là metadata phục vụ phục hồi tiến độ, không phải secret vault. Hãy lưu checkpoint nhỏ như offset, last ID, batch ID hoặc object reference. Không lưu password, access token, private key, session cookie hay payload nhạy cảm tùy tiện. Serialization chỉ chuyển dữ liệu sang dạng lưu trữ; nó không tự mã hóa hoặc bảo vệ dữ liệu khỏi người có quyền đọc repository.

Với secret, dùng secret manager và chỉ phân giải giá trị tại runtime. Với payload lớn hoặc nhạy cảm, lưu trong hệ thống dữ liệu được bảo vệ rồi giữ ID/version/checksum trong context. Bảo vệ cả job parameters, exit message, log, backup và dashboard vì chúng cũng có thể làm lộ metadata.

Một context tốt chỉ chứa đủ thông tin để job tiếp tục đúng vị trí. Nó không chứa bí mật hoặc bản sao dữ liệu mà ứng dụng có thể lấy lại từ một nguồn được quản lý an toàn.
