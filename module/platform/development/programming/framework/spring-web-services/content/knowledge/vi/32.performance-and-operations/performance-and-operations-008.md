# Đánh đổi giữa base64, MTOM và lưu tệp tạm

> **Chương:** Hiệu năng và vận hành  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích để tích hợp hệ thống doanh nghiệp ổn định.

## 1. Bài toán vận chuyển binary trong SOAP

Khi SOAP operation cần gửi ảnh, PDF, tài liệu ký số hoặc archive, có nhiều cách biểu diễn và lưu dữ liệu. Ba lựa chọn thường được đặt cạnh nhau là:

- **Base64 inline:** binary được mã hóa thành text bên trong XML element của SOAP Body.
- **MTOM/XOP:** SOAP XML chứa tham chiếu XOP; binary được truyền trong MIME attachment.
- **Tệp tạm:** application ghi dữ liệu stream vào disk hoặc storage trung gian để tránh giữ toàn bộ nội dung trong heap.

Cần phân biệt hai trục. Base64 và MTOM quyết định **cách binary được biểu diễn trên wire**. Tệp tạm quyết định **dữ liệu được buffer/lưu ở đâu trong quá trình xử lý**. Một ứng dụng có thể nhận MTOM rồi spool attachment ra tệp tạm; hoặc nhận Base64, decode và ghi ra file. Vì vậy ba lựa chọn không loại trừ lẫn nhau.

Chọn sai có thể làm payload phình lớn, tăng heap pressure, tạo nhiều bản sao, đẩy đầy disk, lộ dữ liệu tạm hoặc khiến đối tác không đọc được message. Chọn đúng phải cân bằng hiệu năng, interoperability, security và vận hành.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Base64 inline, MTOM/XOP và temporary-file buffering.
2. Ước lượng Base64 expansion và chi phí memory/copy ở từng tầng.
3. Hiểu vai trò MIME multipart, XOP Include và attachment Content-ID.
4. Chọn JAXB mapping cho binary theo contract và implementation thực tế.
5. Thiết kế stream-to-file, file-to-stream và cleanup an toàn.
6. Đặt limits cho bytes, concurrency, temp disk, duration và file count.
7. Đánh giá interoperability, WS-Security, antivirus scanning và data-at-rest protection.
8. Xử lý timeout, retry, partial failure, idempotency và file lifecycle.
9. Viết architecture decision record dựa trên workload và evidence đo được.

**Nguyên tắc:** Base64/MTOM là quyết định wire contract; temp file là quyết định buffering/storage. Không dùng một quyết định để thay thế quyết định còn lại.

## 2. Ba phương án và kiến trúc điển hình

~~~mermaid
flowchart TB
    A["SOAP client"] --> B{"Binary representation"}
    B --> C["Base64 element trong XML"]
    B --> D["MTOM/XOP MIME package"]
    C --> E["SOAP Body / XML parser"]
    D --> F["SOAP root part + MIME attachment"]
    E --> G["Decode / stream / temp storage"]
    F --> G
    G --> H["Validation / malware scan / business"]
    H --> I["Durable storage hoặc downstream"]
~~~

Sơ đồ cho thấy cả hai wire representations cuối cùng đều có thể đi qua một buffering/storage stage. Temporary file có thể xuất hiện ở client trước khi gửi, server khi nhận, trong antivirus scanning hoặc khi chuyển tiếp sang object storage.

| Lựa chọn | Wire representation | Buffer/storage |
|---|---|---|
| Base64 inline | Text trong SOAP XML | Có thể nằm trong XML buffer, String/byte[], hoặc file sau decode |
| MTOM/XOP | MIME multipart, XML tham chiếu binary | Có thể stream, buffer hoặc spool attachment |
| Tệp tạm | Không xác định riêng wire format | Disk/file/object storage trung gian; kết hợp Base64 hoặc MTOM |

## 3. Base64 inline hoạt động thế nào?

Base64 biểu diễn binary bytes bằng một tập ký tự ASCII có thể nhúng vào XML element.

~~~xml
<doc:UploadDocumentRequest
    xmlns:doc="urn:example:documents:v1">
  <doc:documentId>DOC-1001</doc:documentId>
  <doc:fileName>invoice.pdf</doc:fileName>
  <doc:content>JVBERi0xLjQKJ...</doc:content>
</doc:UploadDocumentRequest>
~~~

Ở phía Java, contract có thể ánh xạ content sang byte[]:

~~~java
public class UploadDocumentRequest {
    private String documentId;
    private String fileName;
    private byte[] content;

    // getters/setters
}
~~~

JAXB thường encode byte[] thành Base64 text khi marshal và decode khi unmarshal. Mapping thuận tiện, đơn giản với file nhỏ và consumer tooling phổ biến, nhưng không có nghĩa quá trình xử lý streaming. Một file có thể cùng lúc tồn tại dưới dạng byte[], XML text/buffer và bản copy trong transport/parser.

### 3.1. Base64 expansion

Số Base64 characters xấp xỉ:

[
L = 4 \times \lceil N/3 \rceil
]

Trong đó N là số binary bytes. Với file lớn, overhead gần 33,3% so với kích thước binary, chưa tính XML tags, whitespace và SOAP headers.

Ví dụ gần đúng:

| Binary gốc | Base64 characters gần đúng |
|---:|---:|
| 300 KiB | 400 KiB |
| 3 MiB | 4 MiB |
| 15 MiB | 20 MiB |
| 75 MiB | 100 MiB |

Số liệu trên chỉ là wire representation của Base64 text; heap có thể cao hơn do character encoding, object graph, temporary buffers và copies. Không cộng một hệ số cố định để suy ra heap cho mọi JDK/parser.

### 3.2. Ưu điểm và giới hạn

**Ưu điểm**
- Contract XML đơn giản; binary nằm trong payload element.
- Dễ kiểm tra bằng XML tools và test fixtures.
- Được nhiều SOAP clients hỗ trợ mà không cần MTOM.
- Dễ áp dụng cho binary nhỏ, giới hạn kích thước rõ.

**Giới hạn**
- XML lớn hơn do Base64 expansion.
- JAXB byte[] thường cần materialize toàn nội dung.
- Logging/copy XML có thể tạo thêm bản sao lớn.
- Khó stream từng phần qua nhiều framework layers.
- XML parser phải xử lý một text node rất lớn.
- Retry gửi lại toàn bộ binary có thể tốn băng thông/CPU.

Base64 là lựa chọn hợp lý cho payload nhỏ và compatibility quan trọng; không nên mặc định phù hợp file lớn.

## 4. MTOM/XOP: tách binary khỏi XML text

MTOM (SOAP Message Transmission Optimization Mechanism) kết hợp XOP (XML-binary Optimized Packaging) để tối ưu truyền binary trong SOAP. Root SOAP part vẫn chứa XML infoset, nhưng binary content có thể được chuyển thành MIME attachment và được tham chiếu bằng xop:Include.

~~~xml
<doc:UploadDocumentRequest
    xmlns:doc="urn:example:documents:v1"
    xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <doc:documentId>DOC-1001</doc:documentId>
  <doc:fileName>invoice.pdf</doc:fileName>
  <doc:content>
    <xop:Include href="cid:attachment-001"/>
  </doc:content>
</doc:UploadDocumentRequest>
~~~

MIME package chứa root SOAP XML part và attachment part với Content-ID tương ứng. Transport và message factory phối hợp để biểu diễn binary theo MTOM/XOP.

### 4.1. MTOM không đổi business contract thành một kiểu file khác

Về bản chất, MTOM tối ưu cách serialize dữ liệu binary trong SOAP message. Schema vẫn định nghĩa element binary (thường là xs:base64Binary); consumer phải hiểu MTOM/XOP và MIME packaging để phục hồi nội dung.

Một consumer chỉ hỗ trợ XML/Base64 inline có thể không hiểu MTOM package dù XSD vẫn có base64Binary. Vì vậy MTOM là lựa chọn interoperability phải được xác nhận với tất cả client/server stacks.

### 4.2. Ưu điểm

- Tránh Base64 expansion trong XML root part khi được tối ưu hóa.
- Có thể xử lý MIME attachment riêng với XML control metadata.
- Hữu ích cho binary lớn và contract cần truyền file qua SOAP.
- Giảm chi phí parse một text node Base64 rất dài.
- Có khả năng hỗ trợ streaming/spooling tùy transport và implementation.

### 4.3. Giới hạn

- Cần client và server đều hỗ trợ MTOM/XOP.
- MIME multipart, Content-ID, boundary và root part làm transport phức tạp hơn.
- Message factory/HTTP sender có thể vẫn buffer attachment trong memory.
- Security signature/encryption với attachments cần cấu hình đúng.
- Proxy/gateway có thể thay đổi MIME message hoặc không hỗ trợ.
- Debugging bằng log XML đơn thuần không hiển thị attachment bytes.

### 4.4. Threshold và bật tối ưu

Một số stacks hỗ trợ ngưỡng kích thước để quyết định binary nào nên inline và binary nào nên thành attachment. Giá trị threshold phải dựa trên workload, client support và implementation version. Không giả định mọi tool tự động dùng cùng threshold.

Nếu bật MTOM, kiểm tra:
- Client đã enable MTOM trên binding/marshaller.
- Server message factory/transport hỗ trợ attachments.
- XSD và WSDL contract được công bố đúng.
- MIME request/response qua HTTP thật.
- Payload nhỏ và lớn ở hai bên threshold.
- Attachment integrity và cleanup sau lỗi.

## 5. Temporary files là buffering strategy, không phải SOAP wire format

Tệp tạm có thể giúp giảm peak heap khi dữ liệu lớn. Thay vì giữ toàn bộ binary trong byte[], application copy stream sang file và xử lý file theo từng chunk.

~~~text
HTTP/MIME stream
    → bounded input stream
    → temporary file
    → size/checksum validation
    → malware/content scan
    → durable storage
    → delete temporary file
~~~

Tệp tạm có thể kết hợp:
- Base64 được parser decode rồi ghi xuống disk.
- MTOM attachment stream được spool xuống disk.
- File upload đầu vào đã có trên disk rồi được gửi qua MTOM.
- Download SOAP response được stream ra file thay vì materialize byte[].

### 5.1. Lợi ích

- Giảm việc giữ binary lớn trong heap.
- Cho phép công cụ scan/parse file theo stream.
- Có thể retry downstream từ file đã staging mà không tải lại source.
- Phù hợp với pipeline cần checksum, scan, inspect hoặc chuyển sang durable storage.
- Tách vòng đời nhận message khỏi vòng đời business processing nếu thiết kế queue/job rõ.

### 5.2. Chi phí và rủi ro

- Disk I/O, latency và dung lượng storage tăng.
- Cần quota, cleanup và xử lý file orphan.
- File có thể chứa PII/secrets và phải bảo vệ at-rest.
- Cần tránh path traversal, symlink attacks và filename injection.
- Disk full hoặc permission failure có thể làm request fail.
- Nhiều concurrent uploads có thể làm cạn disk/inodes.
- Temp file không tự động làm transport streaming; tầng trước có thể đã buffer toàn message.

### 5.3. Temporary directory và tên file

Không dùng tên file do caller kiểm soát để tạo path trực tiếp. Tạo tên ngẫu nhiên bằng API của hệ điều hành/framework, ghi trong directory riêng có permissions chặt và không phục vụ qua web root.

~~~java
Path tempFile = Files.createTempFile(
        configuredTempDirectory,
        "soap-upload-",
        ".part");
~~~

Tên prefix/suffix không phải nơi lưu metadata nhạy cảm. Lấy configuredTempDirectory từ cấu hình server; không hardcode path của máy developer. Kiểm tra directory tồn tại, writable, nằm trên volume có quota và không theo symlink ngoài vùng kiểm soát.

## 6. So sánh chi phí theo các tài nguyên

| Tiêu chí | Base64 inline | MTOM/XOP | Temp file |
|---|---|---|---|
| Wire bytes cho binary | Tăng gần 1/3 | Gần kích thước binary cộng MIME overhead | Phụ thuộc Base64/MTOM được dùng |
| XML parsing | Text node lớn | XML root nhỏ hơn, attachment riêng | Không phải wire choice |
| Heap | Dễ tạo String/byte[] copies | Có thể thấp hơn nếu streaming/spooling; tùy implementation | Giảm binary heap nếu stream thật |
| CPU | Base64 encode/decode | MIME/XOP packaging/parsing | Disk I/O, checksum/scan |
| Disk | Không bắt buộc | Không bắt buộc, nhưng có thể spool | Cần quota và cleanup |
| Compatibility | Rộng hơn | Phải xác nhận MTOM support | Nội bộ implementation |
| Debugging | Dễ đọc hơn, nhưng XML rất lớn | Cần MIME-aware tooling | Cần trace file lifecycle |
| Failure modes | Heap/CPU, payload size | MIME/Content-ID, streaming, negotiation | Disk full, orphan, permissions |
| Phù hợp | Binary nhỏ/bounded | Binary lớn qua SOAP | Staging/scanning/retry workflows |

Không phương án nào luôn nhanh nhất. MTOM có thể giảm wire/heap expansion nhưng MIME/transport vẫn có thể buffer. Temp file giảm heap nhưng chuyển chi phí sang disk, I/O và lifecycle.

## 7. JAXB mapping và cách tránh materialize file lớn

### 7.1. byte[] mapping

JAXB mapping phổ biến cho xs:base64Binary là byte[]. Cách này phù hợp khi:
- Payload nhỏ hoặc có maximum size thấp.
- Business cần toàn bộ bytes để xử lý một lần.
- Có heap budget được đo và concurrency được giới hạn.

Không nên nhận file không giới hạn vào byte[] trong endpoint có thể chạy nhiều requests đồng thời.

### 7.2. DataHandler/DataSource và attachment-aware mapping

Một số JAXB/activation/SOAP stacks dùng DataHandler hoặc DataSource để biểu diễn binary/attachments, tùy binding và implementation. Điều đó có thể cho phép truy cập stream hoặc deferred content hơn byte[], nhưng không tự bảo đảm streaming đầu-cuối.

Cần xác minh:
- Binding customization thực tế.
- DataHandler trả stream bao lâu và ai sở hữu/đóng stream.
- Framework có materialize attachment trước khi gọi endpoint không.
- Stream có thể đọc một lần hay nhiều lần.
- Retry cần rewind/copy hay phải giữ staging file.
- File có bị xóa trước khi async processing dùng xong không.

Không đưa javax.activation và jakarta.activation types lẫn nhau. Namespace/package phụ thuộc JDK/framework generation line.

### 7.3. Contract DTO và internal command

Giữ JAXB wire DTO ở boundary:

~~~text
SOAP Base64/MTOM
   → JAXB DTO / attachment handle
   → validate size + checksum + policy
   → staging/storage adapter
   → internal document reference
   → business service
~~~

Business service nên làm việc với document reference/metadata hoặc stream abstraction được quản lý, không truyền byte[] lớn qua nhiều layers nếu không cần.

## 8. Spring-WS và cấu hình MTOM

Spring-WS sử dụng WebServiceMessageFactory, marshalling layer và transport để xử lý SOAP message. Cấu hình cụ thể phụ thuộc Spring-WS release, SOAP message implementation (ví dụ SAAJ hoặc implementation khác), JAXB provider và activation APIs.

Một số điểm cần xác minh trong ứng dụng:
- MessageFactory có hỗ trợ MIME attachments và MTOM không.
- Marshaller được cấu hình MTOM-enabled theo API/provider tương ứng.
- Message sender/receiver giữ attachment streams đúng lifecycle.
- Server và client đều công bố/enable profile cần thiết.
- Servlet/container có giới hạn body phù hợp.
- Interceptors/logging không copy toàn attachment vào memory.
- WS-Security policy có hỗ trợ ký/mã hóa attachment theo yêu cầu.

Không chỉ set một boolean MTOM rồi kết luận đã streaming. Kiểm actual HTTP multipart message và heap profile trên payload lớn.

## 9. Temporary-file lifecycle: tạo, dùng, promote và xóa

Một file tạm cần lifecycle rõ. Ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Receiving
    Receiving --> Validating
    Validating --> Scanning
    Scanning --> Promoting
    Promoting --> Durable
    Durable --> Deleted
    Receiving --> Failed
    Validating --> Failed
    Scanning --> Failed
    Promoting --> Failed
    Failed --> Cleanup
    Cleanup --> Deleted
    Deleted --> [*]
~~~

### 9.1. Quy tắc lifecycle

1. Tạo file trong controlled directory với tên ngẫu nhiên.
2. Ghi stream theo chunk và enforce maximum bytes ngay khi đọc.
3. Khi kết thúc, flush/close stream và kiểm actual size.
4. Tính checksum nếu contract/workflow yêu cầu.
5. Xác minh content type dựa trên nội dung, không chỉ filename/header.
6. Scan/quarantine trước khi file được downstream sử dụng.
7. Promote/copy sang durable storage theo transaction/idempotency strategy.
8. Ghi metadata và trạng thái job một cách nhất quán.
9. Xóa file tạm sau khi durable commit hoặc terminal failure.
10. Có scheduled cleanup cho orphaned files sau crash/restart.

Không xóa temp file ngay khi HTTP request kết thúc nếu async worker còn dùng nó. Chuyển quyền sở hữu rõ ràng từ request scope sang job/storage lifecycle.

### 9.2. Cleanup trong Java

~~~java
Path temp = Files.createTempFile(tempDirectory, "soap-", ".tmp");

try {
    try (InputStream in = attachmentStream;
         OutputStream out = Files.newOutputStream(temp)) {
        in.transferTo(out);
    }

    validateFile(temp);
    scanFile(temp);
    promoteToDurableStorage(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

Ví dụ này phù hợp xử lý đồng bộ, khi promote hoàn tất trước khi finally chạy. Nếu job bất đồng bộ, không xóa trong finally của HTTP thread; chuyển file ownership sang job record và để worker/cleanup process quản lý.

## 10. Giới hạn tài nguyên và chống abuse

Đặt giới hạn riêng cho từng layer:

| Limit | Mục đích |
|---|---|
| Max HTTP request bytes | Chặn body quá lớn ở ingress |
| Max decompressed bytes | Chặn compression expansion |
| Max attachment count | Tránh quá nhiều MIME parts |
| Max bytes per attachment | Giới hạn từng file |
| Max total attachment bytes | Giới hạn tổng request |
| Max XML depth/elements | Giảm parser complexity |
| Max temp disk per request/tenant | Tránh chiếm hết volume |
| Max concurrent uploads | Giới hạn peak memory/disk I/O |
| Max upload duration | Tránh giữ resources quá lâu |
| Max queued jobs | Tránh backlog giữ file/metadata |

Enforce byte limits trong lúc stream đọc, không chỉ kiểm tra Content-Length vì header có thể vắng mặt hoặc không đáng tin trong một số transport/proxy paths. Giới hạn decompressed size nếu HTTP compression được bật.

### 10.1. Admission control

Nếu server đã gần hết heap hoặc temp volume, từ chối/queue công việc mới theo policy thay vì tiếp tục nhận file đến khi OOM hoặc disk full. Dùng bounded queues, per-partner quotas và response lỗi có kiểm soát.

### 10.2. File content không đáng tin

Không tin:
- Filename extension.
- Content-Type từ caller.
- Content-Length.
- Checksum caller gửi mà chưa xác minh.
- XML metadata mô tả loại file.

Validate file signature/content theo allowlist nghiệp vụ, scan malware khi cần, và không render/execute file nhận được trên server.

## 11. Security: data in transit, temp storage và message integrity

### 11.1. TLS và WS-Security

TLS bảo vệ kênh truyền HTTP; WS-Security có thể cung cấp message-level signature/encryption theo policy. Khi payload dùng MTOM, cần kiểm policy có bao phủ attachment data đúng cách hay không. Không giả định ký SOAP Body XML đồng nghĩa binary attachment tự được bảo vệ nếu profile/configuration không áp dụng.

### 11.2. Temp file at rest

Temporary file cần:
- Directory permissions hạn chế service account.
- Encryption at rest hoặc encrypted volume theo phân loại dữ liệu.
- Không để trên web root/public shared volume.
- Không dùng filename chứa PII hoặc business secrets.
- Retention ngắn và cleanup tự động.
- Audit file access/promote/delete.
- Quản lý backup/snapshot để file đã xóa không vô tình tồn tại lâu.

Xóa file bằng Files.delete không bảo đảm mọi storage media đã overwrite vật lý. Nếu yêu cầu xóa an toàn nghiêm ngặt, chọn storage/encryption key lifecycle phù hợp thay vì dựa vào overwrite thủ công.

### 11.3. Malware scanning và quarantine

File nên được đặt ở quarantine/staging trước khi được dùng downstream. Xác định scan timeout, scan service outage, file password-protected, archive recursion và policy cho unknown format. Không coi SOAP schema validation là malware/content validation.

### 11.4. XML security và attachment security

XXE/XML parser protections vẫn áp dụng cho SOAP XML root part. Attachment content cần giới hạn kích thước, loại file, archive expansion và scanner riêng. Nếu nội dung attachment được chuyển tiếp, không để một reference ID có thể bị đoán để tải file của tenant khác.

## 12. Xử lý failure, retry và idempotency

File pipeline có nhiều điểm fail: upload dở dang, disk full, checksum mismatch, scan unavailable, durable store timeout, database commit thất bại hoặc HTTP response bị mất sau khi server đã lưu file.

| Failure point | Hành vi cần có |
|---|---|
| Stream nhận bị cắt | Mark incomplete, cleanup temp, không promote |
| Quá size limit | Stop read, reject, cleanup |
| Disk full | Fail rõ ràng, cleanup partial file, alert quota |
| Checksum mismatch | Quarantine/reject, không business commit |
| Malware scan fail | Không promote; retry/dead-letter theo policy |
| Durable store success, DB fail | Reconciliation/idempotent promotion |
| DB success, response lost | Client retry không tạo document duplicate |
| Worker crash | Job lease/recovery và orphan cleanup |

### 12.1. Idempotency key

Dùng idempotency key hoặc document ID gắn với partner/tenant đã xác thực. Lưu trạng thái processing và checksum; khi retry:
- Cùng key và cùng content: trả kết quả đã xử lý hoặc tiếp tục an toàn.
- Cùng key nhưng content khác: reject conflict.
- Job đang chạy: không tạo một bản promote thứ hai.
- Job failed terminal: áp dụng retry policy rõ.

Không dùng filename làm idempotency key duy nhất.

### 12.2. Promote file và database consistency

Filesystem/object storage và database thường không cùng một transaction. Thiết kế state machine như RECEIVING, SCANNED, STORED, COMMITTED, FAILED; có reconciliation để xử lý file đã promote nhưng metadata chưa commit và ngược lại. Có thể dùng outbox/job table và durable object key để đảm bảo worker tiếp tục được sau restart.

## 13. Client-side strategy

Client có thể:
- Encode Base64 từ byte[] cho file nhỏ.
- Dùng MTOM client stack cho attachment.
- Đọc file source bằng InputStream và sử dụng API hỗ trợ streaming/attachment.
- Stage local temp file nếu source là generated stream cần retry/rewind.
- Giữ checksum/idempotency metadata qua retries.

Không đọc toàn file vào byte[] chỉ để đặt vào DTO nếu file có thể lớn. Tuy nhiên, trước khi chọn streaming cần kiểm client SOAP stack thật sự hỗ trợ và không materialize toàn nội dung ở marshaller.

Temporary file phía client có lifecycle riêng: giữ đủ lâu cho transport hoàn thành/retry theo policy, đóng file handle, xóa khi terminal completion và dọn orphan sau crash.

## 14. Server-side strategy trong Spring-WS

Server nên xử lý theo pipeline:

~~~text
HTTP ingress limits
  → SOAP MessageFactory / MIME parsing
  → WS-Security and message validation
  → identify binary/attachment handle
  → bounded stream to staging
  → size/checksum/content validation
  → malware scan / quarantine
  → durable storage
  → commit document metadata/idempotency state
  → SOAP response
~~~

Thứ tự WS-Security và payload processing phụ thuộc policy/framework. Đặc biệt, không thực hiện business promotion trước khi xác thực signer/authorization và xác minh đúng nội dung được ký. Cần kiểm attachment signed coverage theo security profile.

Không giữ attachment bytes trong singleton field hoặc shared mutable DTO. Đóng stream đúng ownership; xử lý client disconnect; hủy staging khi request abort; và đảm bảo async worker không phụ thuộc file đã bị request cleanup xóa.

## 15. Observability và capacity planning

Metrics có ích:
- Request bytes, attachment count và tổng attachment bytes.
- Base64 vs MTOM usage.
- In-memory buffer size/attachment spool bytes nếu implementation cung cấp.
- Temp directory current bytes, free space, file count và age.
- Upload duration, scan duration, promote duration.
- Concurrent in-flight uploads.
- Rejected requests theo limit reason.
- Cleanup failures/orphan file count.
- Heap allocation/GC pause và disk I/O latency.

Dùng labels có cardinality thấp như operation/version/outcome. Không gắn document ID, filename, tenant ID tự do hoặc payload text làm metric tags.

Alert nên dựa trên disk free space, quota utilization, file age, queue depth và cleanup failure. Capacity planning phải dùng peak concurrency và worst-case file sizes, không chỉ average file size.

## 16. Case study: Base64 upload gây OOM, chuyển sang MTOM và staging

### 16.1. Hiện tượng

Một service nhận PDF 25 MiB dưới dạng Base64 trong SOAP Body. Khi có nhiều đối tác gửi đồng thời, heap tăng mạnh và GC pause kéo dài. Audit interceptor còn tạo String copy của toàn request. Client retry khi timeout làm băng thông tiếp tục tăng.

### 16.2. Đánh giá lựa chọn

- Giữ Base64: dễ tương thích nhưng XML text khoảng 33% lớn hơn binary, JAXB byte[] và logging tạo thêm allocations.
- Chuyển MTOM: giảm binary text trong root XML nhưng cần tất cả partner stacks hỗ trợ; phải xác minh actual implementation có stream/spool hay vẫn buffer.
- Thêm temp staging: giảm heap nếu attachment stream được spool theo chunk, nhưng cần quota, encryption, cleanup và durable promotion.

### 16.3. Thiết kế đích

1. Giữ Base64 cho file nhỏ có giới hạn rõ.
2. Dùng MTOM cho partner đã chứng minh support.
3. Spool attachment lớn vào encrypted staging volume với byte limit.
4. Validate checksum/content và scan trước promote.
5. Lưu document metadata/idempotency state.
6. Worker promote sang object storage, rồi cleanup staging.
7. Bỏ full-body logging; chỉ ghi metadata đã redaction.
8. Giới hạn concurrency và tổng temp bytes.
9. Test timeout/retry sau khi durable store thành công.

### 16.4. Tiêu chí nghiệm thu

- Heap peak, allocation rate và p95/p99 cải thiện dưới cùng concurrency/profile.
- Binary checksum/bytes không đổi.
- Partner client tạo/đọc MTOM đúng.
- Oversized request bị reject và partial temp file được cleanup.
- Malware/validation failure không promote.
- Crash/retry không tạo duplicate document.
- Temp volume có quota/alerts và orphan cleanup.
- WS-Security/integrity requirements vẫn được đáp ứng.

## 17. Bài tập tự luyện

**Bài 1 — Base64 overhead:** File binary 30 MiB tạo bao nhiêu Base64 characters xấp xỉ?

**Đáp án:** Khoảng 40 MiB characters, chưa tính XML markup và các buffers.

**Bài 2 — MTOM có streaming không?**

**Đáp án:** Không tự động. MessageFactory, HTTP sender, marshaller và proxy có thể buffer. Phải kiểm actual path bằng profile.

**Bài 3 — Temp file có phải wire format thứ ba?**

**Đáp án:** Không. Temp file là buffering/storage strategy; wire vẫn có thể là Base64 hoặc MTOM.

**Bài 4 — JAXB byte[]:** Vì sao nguy hiểm với file rất lớn?

**Đáp án:** Toàn binary cần materialize trong heap, có thể thêm XML String/buffers/copies và concurrency amplification.

**Bài 5 — Filename từ caller:** Có thể dùng trực tiếp làm temp path?

**Đáp án:** Không. Dùng tên ngẫu nhiên trong controlled directory, tránh traversal/symlink và data leakage.

**Bài 6 — Cleanup trong finally:** Có luôn đúng khi async worker dùng file?

**Đáp án:** Không. Cần chuyển ownership sang job lifecycle; chỉ xóa sau khi worker terminal completion hoặc cleanup policy quyết định.

**Bài 7 — Content-Type:** Caller gửi application/pdf có chứng minh file là PDF?

**Đáp án:** Không. Kiểm nội dung/signature và policy, không tin header/extension.

**Bài 8 — Disk full:** Nên tiếp tục giữ phần bytes đã nhận trong heap?

**Đáp án:** Không. Dừng đọc, fail rõ, cleanup partial data và phát cảnh báo quota.

**Bài 9 — TLS:** TLS có bảo vệ temp file at rest?

**Đáp án:** Không. Cần storage permissions, encryption-at-rest, retention và cleanup.

**Bài 10 — Retry sau commit:** Response mất nhưng server đã lưu file. Cần gì?

**Đáp án:** Idempotency key, checksum và trạng thái processing để retry không tạo duplicate.

**Bài 11 — MTOM và WS-Security:** Ký SOAP Body có luôn ký attachment?

**Đáp án:** Không được giả định. Cần profile/configuration bảo vệ attachment reference/content theo đúng policy.

**Bài 12 — Chọn phương án:** File 200 KiB, partners không hỗ trợ MTOM. Nên dùng gì?

**Đáp án:** Base64 inline có thể phù hợp nếu giới hạn payload/concurrency rõ và profiling xác nhận memory budget.

## 18. Checklist quyết định và vận hành

### Chọn wire representation
- [ ] Đo kích thước binary thực tế và phân phối p95/p99.
- [ ] Xác nhận partner/client support Base64 hay MTOM.
- [ ] Tính Base64 expansion và XML/parser overhead.
- [ ] Đánh giá MTOM/XOP, MIME boundary, Content-ID và SOAP version.
- [ ] Test threshold/behavior thực tế trên mọi SOAP stack.
- [ ] Không coi temp file là wire format.

### Heap và streaming
- [ ] Kiểm JAXB mapping byte[]/DataHandler/DataSource thực tế.
- [ ] Profile marshaller/message factory/transport buffers.
- [ ] Xác minh end-to-end streaming hoặc spool behavior.
- [ ] Không copy toàn attachment thành String/byte[] không cần thiết.
- [ ] Đặt in-flight upload/concurrency/bounded queue limits.
- [ ] Có memory budget dưới peak load.

### Temp file lifecycle
- [ ] Controlled directory với permissions hạn chế.
- [ ] Filename ngẫu nhiên, không tin caller path.
- [ ] Enforce per-file/total bytes khi stream.
- [ ] Có quota disk, file count và retention.
- [ ] Stream được close đúng ownership.
- [ ] Cleanup partial/orphan files sau lỗi/crash.
- [ ] Async worker sở hữu file đến terminal state.
- [ ] Promote sang durable storage có reconciliation.

### Security và data integrity
- [ ] TLS/WS-Security theo policy.
- [ ] Attachment signature/encryption coverage được xác minh.
- [ ] Content type được kiểm bằng file content.
- [ ] Checksum được tính/đối chiếu.
- [ ] Malware scan/quarantine theo risk.
- [ ] Encryption at rest và access controls.
- [ ] Logs/metrics không chứa file content, PII hoặc secrets.

### Failure/retry và observability
- [ ] Test disconnect, timeout, disk full và checksum mismatch.
- [ ] Idempotency chống duplicate sau response loss.
- [ ] Có states/reconciliation giữa storage và database.
- [ ] Theo dõi temp bytes/free space/age/cleanup failures.
- [ ] Theo dõi heap/GC/throughput/latency cùng concurrency.
- [ ] Có performance và interoperability regression tests.

**Ghi nhớ:** Base64 đơn giản và dễ tương thích cho binary nhỏ nhưng làm XML lớn hơn khoảng một phần ba và thường tăng nhu cầu materialize dữ liệu. MTOM/XOP tách binary thành MIME attachment, có thể giảm XML expansion nhưng chỉ hiệu quả khi toàn stack hỗ trợ và buffering được kiểm soát. Temporary files giúp chuyển peak memory sang disk và hỗ trợ scanning/retry, đổi lại cần quota, encryption, lifecycle, cleanup và reconciliation. Lựa chọn tốt thường là phối hợp: Base64 cho payload nhỏ, MTOM cho binary lớn khi partner hỗ trợ, và staging/storage có kiểm soát cho processing cần file bền vững — tất cả đều phải được đo dưới concurrency thực và giữ nguyên contract/security semantics.
