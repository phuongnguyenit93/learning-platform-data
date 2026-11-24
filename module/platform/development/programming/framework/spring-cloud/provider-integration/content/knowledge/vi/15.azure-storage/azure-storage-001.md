# Phân biệt Blob Storage, File Share và Storage Queue trong Azure

## 1. Bối cảnh và mục tiêu

Khi tích hợp ứng dụng Spring Boot với dịch vụ lưu trữ được quản lý của Azure, ba tên **Azure Blob Storage**, **Azure Files (File Share)** và **Azure Queue Storage** dễ gây nhầm lẫn vì cùng thuộc nhóm Azure Storage. Tuy nhiên, chúng giải quyết **ba nhu cầu khác nhau**:

- **Blob Storage**: lưu và truy xuất **đối tượng dữ liệu** như ảnh, video, tệp PDF, bản sao lưu hoặc nội dung xuất ra từ hệ thống.
- **Azure Files / File Share**: cung cấp **hệ thống tệp dùng chung**, có thư mục và tệp, thường được ứng dụng hoặc máy chủ truy cập qua SMB/NFS.
- **Queue Storage**: lưu **thông điệp công việc** để các thành phần xử lý bất đồng bộ; đây không phải nơi lưu nội dung tệp.

Bài học thuộc module **SPRING_CLOUD_PROVIDER_INTEGRATION**, tập trung vào việc chọn đúng dịch vụ managed, tích hợp với Spring Boot/Spring Cloud Azure, phân quyền truy cập, thiết kế luồng xử lý và kiểm thử. Sau bài này, bạn cần giải thích được *vì sao* một bài toán nên dùng Blob, File Share hay Queue, và biết cách kết hợp chúng mà không nhầm vai trò.

## 2. So sánh nhanh

| Tiêu chí | Azure Blob Storage | Azure Files (File Share) | Azure Queue Storage |
|---|---|---|---|
| Đơn vị dữ liệu chính | Blob (đối tượng) trong container | Tệp, thư mục trong file share | Message trong queue |
| Bài toán chủ đạo | Lưu nội dung phi cấu trúc, tải lên/tải xuống qua API | Thư mục dùng chung, ứng dụng cần thao tác kiểu filesystem | Giao việc, tách rời producer và consumer |
| Cách truy cập đặc trưng | HTTPS/REST, Azure SDK, URL/SAS | SMB/NFS để mount; cũng có REST/SDK | HTTPS/REST, Azure SDK, producer/worker |
| Cách định danh | Storage account → container → blob name | Storage account → share → directory → file | Storage account → queue → message |
| Thao tác thường gặp | Upload, download, list, delete, metadata, versioning | Tạo thư mục, mở/đọc/ghi tệp, chia sẻ qua đường dẫn | Enqueue, receive, xử lý, delete message |
| Ngữ nghĩa cần lưu ý | Object storage; tên có dấu `/` không đồng nghĩa với thư mục thực trong cấu hình thông thường | Có phân cấp thư mục, thao tác và khóa tệp theo giao thức sử dụng | Nhận lặp có thể xảy ra; thứ tự không được bảo đảm |
| Ví dụ | Ảnh sản phẩm, hồ sơ PDF, file export, log lưu trữ | Thư mục báo cáo cho nhiều VM/container, thay thế file server | Yêu cầu tạo thumbnail, gửi email, xử lý tài liệu |
| **Không nên dùng như** | Ổ đĩa dùng chung đòi hỏi đầy đủ ngữ nghĩa SMB | Kho hàng tỷ object chỉ truy cập qua URL mà không cần filesystem | Kho lưu PDF/video hoặc hàng đợi cần giao dịch/phát theo chủ đề phức tạp |

**Quy tắc chọn nhanh:** cần *lưu nội dung* → nghĩ đến **Blob**; cần *mount một thư mục dùng chung* → nghĩ đến **Azure Files**; cần *gửi một công việc để xử lý sau* → nghĩ đến **Queue**. Một luồng nghiệp vụ có thể dùng cả ba, nhưng không nhất thiết phải sử dụng đủ ba dịch vụ.

## 3. Blob Storage: lưu object và phục vụ nội dung

Blob Storage tổ chức dữ liệu theo **storage account → container → blob**. Mỗi blob có tên (key), nội dung và metadata. Ứng dụng thường dùng Azure SDK hoặc REST để upload/download; phía trình duyệt có thể dùng URL được cấp quyền phù hợp. Những blob name như `customers/42/avatar.png` giúp nhóm đối tượng theo tiền tố; trong tài khoản Blob thông thường, dấu gạch chéo trong tên không tự biến Blob thành hệ thống tệp có đầy đủ ngữ nghĩa POSIX. Azure Data Lake Storage Gen2 với hierarchical namespace là trường hợp có đặc tính thư mục riêng.

Các loại blob cần nhận biết:

- **Block blob**: lựa chọn phổ biến cho tài liệu, ảnh, media và dữ liệu được upload.
- **Append blob**: tối ưu cho kiểu ghi nối thêm, chẳng hạn một số luồng log.
- **Page blob**: hỗ trợ đọc/ghi theo trang; có các trường hợp sử dụng cho đĩa ảo.

Blob Storage phù hợp với luồng **upload một lần, truy xuất nhiều lần**, tải lên/tải xuống theo khóa, phục vụ nội dung lớn và lưu trữ theo vòng đời. Có thể dùng các cơ chế bảo vệ như phiên bản blob, soft delete, quy tắc lifecycle và các access tier được hỗ trợ theo loại tài khoản/dữ liệu. Chọn access tier dựa vào tần suất truy cập, thời gian lưu trữ và chi phí lấy lại dữ liệu, thay vì mặc định mọi dữ liệu là `Hot`.

**Ví dụ:** một ứng dụng bán hàng lưu ảnh sản phẩm tại container `product-images`. Database chỉ lưu blob name hoặc URL tham chiếu, metadata nghiệp vụ và quan hệ với sản phẩm; tệp ảnh thật nằm trong Blob Storage. Khi trả file riêng tư cho người dùng, backend xác thực quyền truy cập trước khi tải nội dung hoặc phát hành SAS có quyền và thời hạn tối thiểu.

**Điểm dễ nhầm:** Blob Storage có thể liệt kê blob theo prefix, nhưng điều này không khiến nó trở thành lựa chọn tương đương Azure Files cho ứng dụng cần mở nhiều tệp qua một thư mục SMB, khóa tệp kiểu filesystem hoặc dùng một đường dẫn mount chung.

## 4. Azure Files / File Share: thư mục và tệp dùng chung

Azure Files cung cấp **file share được quản lý** bên trong storage account. Cấu trúc là **share → directory → file**. Các máy chủ hoặc ứng dụng có thể mount file share bằng giao thức được hỗ trợ, điển hình là **SMB** hoặc **NFS**, rồi thao tác qua đường dẫn filesystem như với ổ chia sẻ truyền thống. Azure Files cũng có API REST và Azure Storage Files SDK để truy cập theo chương trình.

Các tình huống điển hình:

- Chuyển một ứng dụng cũ vốn đọc/ghi `\\fileserver\reports` sang nền tảng đám mây mà không viết lại toàn bộ lớp truy cập tệp.
- Cho nhiều VM hoặc container đọc một thư mục tài liệu chung khi kiến trúc triển khai và giao thức mount cho phép.
- Cung cấp thư mục báo cáo, cấu hình hoặc dữ liệu dùng chung có phân cấp thư mục rõ ràng.

Chẳng hạn, sau khi hạ tầng mount share vào `/mnt/reports`, code Java có thể dùng API filesystem quen thuộc:

~~~java
Path report = Path.of("/mnt/reports/2026/summary.csv");
Files.createDirectories(report.getParent());
Files.writeString(report, "month,total\n11,1250\n");
~~~

Đoạn code này **giả định share đã được mount và tài khoản tiến trình có quyền ghi**; bản thân Spring Boot không thực hiện việc mount. Nếu không mount, ứng dụng có thể dùng Azure Files SDK. Tính khả dụng của SMB/NFS, xác thực, phân quyền, tính năng giao thức và kiểu share phụ thuộc cấu hình Azure Files cụ thể; cần kiểm tra trước khi chọn cho môi trường chạy.

Không nên chọn File Share chỉ vì dữ liệu “là một file”. Nếu yêu cầu thực tế là upload ảnh, lưu PDF và phát URL tải về cho web/mobile, Blob thường có mô hình truy cập phù hợp hơn. Azure Files đem lại giá trị khi **đường dẫn thư mục và tương tác filesystem thực sự là yêu cầu kiến trúc**.

## 5. Queue Storage: tách xử lý bất đồng bộ

Azure Queue Storage chứa **message**, không chứa tệp. Producer ghi thông điệp vào queue; một hoặc nhiều worker đọc và xử lý. Mỗi thông điệp nên nhỏ và mang đủ thông tin để worker tìm được dữ liệu nghiệp vụ, ví dụ `{"blobName":"incoming/7f2a.pdf","jobType":"INDEX"}`. Với thông điệp lớn hoặc dữ liệu nhị phân, lưu payload vào Blob rồi **đưa blob name/ID vào queue**. Giới hạn nội dung một message của Azure Queue Storage là **64 KiB**.

Một chu kỳ xử lý điển hình:

1. API nhận yêu cầu và upload tệp vào Blob Storage.
2. API gửi message chứa `blobName` vào Storage Queue.
3. Worker nhận message; message tạm thời bị ẩn trong khoảng **visibility timeout**.
4. Worker lấy dữ liệu từ Blob và xử lý.
5. **Chỉ sau khi xử lý thành công**, worker xóa message bằng message ID và pop receipt. Nếu worker lỗi hoặc không xóa, message có thể xuất hiện lại để được xử lý tiếp.

~~~mermaid
flowchart LR
    C[Client] -->|Upload PDF| A[Spring Boot API]
    A -->|Lưu nội dung PDF| B[(Blob Storage)]
    A -->|Gửi blobName + jobId| Q[(Storage Queue)]
    Q -->|Nhận công việc| W[Spring Boot Worker]
    W -->|Đọc PDF| B
    W -->|Ghi kết quả/idempotency| D[(Database)]
    W -->|Xóa message sau thành công| Q
~~~

Queue Storage thường được dùng như **work queue với competing consumers**, tức nhiều worker có thể cùng nhận các công việc khác nhau. Nó không bảo đảm thứ tự tuyệt đối, không cung cấp exactly-once processing và không phải cơ chế publish/subscribe phát một message cho mọi subscriber. Consumer cần **idempotent** (xử lý lại cùng job mà không tạo kết quả sai), theo dõi số lần nhận lại (`dequeue count`), và có chiến lược chuyển công việc lỗi kéo dài sang một **poison queue** do ứng dụng quản lý. Queue Storage không tự cung cấp dead-letter queue như Azure Service Bus.

Nếu cần FIFO có kiểm soát bằng session, transaction, dead-letter queue tích hợp hoặc publish/subscribe theo topic, hãy đánh giá **Azure Service Bus**. Nếu cần sự kiện theo mô hình routing đến nhiều đích, hãy đánh giá **Event Grid**. Nếu cần truyền lượng lớn luồng sự kiện, hãy đánh giá **Event Hubs**. Những dịch vụ này đáp ứng kiểu bài toán khác với Storage Queue.

## 6. Thực hành tích hợp với Spring Boot và Spring Cloud Azure

Giả sử ứng dụng cần **nhận tài liệu PDF và đưa vào hàng đợi lập chỉ mục**. Chọn Blob để lưu tài liệu, Queue để điều phối xử lý. Không cần File Share vì không có yêu cầu mount thư mục dùng chung.

### 6.1. Khai báo thư viện và cấu hình

Với Maven, chọn BOM **Spring Cloud Azure tương thích với phiên bản Spring Boot đang dùng** và dùng các starter tương ứng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

Trong `application.yml`, để tên storage account ở biến môi trường:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
~~~

Ví dụ trên giả định **container `documents` và queue `document-jobs` đã được tạo trước**. Có thể dùng hai storage account khác nhau nếu yêu cầu về quyền, chi phí hoặc vận hành khác nhau. Cơ chế credential của Spring Cloud Azure cần được cấu hình tương thích với môi trường: đăng nhập nhà phát triển khi chạy local và **managed identity** trong Azure là lựa chọn phổ biến. Không hardcode account key, connection string hay client secret vào Git.

### 6.2. API lưu Blob rồi gửi Queue message

Đoạn code dùng các client mà Spring Cloud Azure có thể tự cấu hình từ starter:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueClient;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final BlobContainerClient documents;
    private final QueueClient jobs;

    public DocumentController(BlobServiceClient blobService,
                              QueueServiceClient queueService) {
        this.documents = blobService.getBlobContainerClient("documents");
        this.jobs = queueService.getQueueClient("document-jobs");
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(@RequestParam("file") MultipartFile file)
            throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File không được rỗng");
        }

        String blobName = UUID.randomUUID() + ".pdf";
        try (var stream = file.getInputStream()) {
            documents.getBlobClient(blobName)
                     .upload(stream, file.getSize(), false);
        }

        jobs.sendMessage(blobName);
        return Map.of("blobName", blobName, "state", "QUEUED");
    }
}
~~~

Hướng triển khai này minh họa trách nhiệm của hai dịch vụ; để đưa vào production, cần **kiểm tra nội dung/định dạng, giới hạn dung lượng, xác thực người dùng, kiểm soát quyền xem tài liệu, logging và xử lý lỗi**. Tên `.pdf` trong ví dụ không phải kiểm chứng rằng file thực sự là PDF.

Một điểm quan trọng: upload Blob thành công nhưng `sendMessage` thất bại sẽ để lại blob chưa được đưa vào hàng đợi. **Blob và Queue không có transaction liên dịch vụ**. Hệ thống cần cách khôi phục: ghi job vào database với trạng thái chờ, retry có kiểm soát, outbox hoặc quy trình đối soát blob chưa được xử lý. Tránh khẳng định API sẽ “luôn đảm bảo cả hai thao tác thành công”.

### 6.3. Worker nhận, xử lý và xóa message

Ví dụ rút gọn dưới đây dùng SDK trực tiếp; `@EnableScheduling` phải được bật ở cấu hình Spring Boot:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DocumentWorker {
    private static final Logger log =
            LoggerFactory.getLogger(DocumentWorker.class);

    private final BlobContainerClient documents;
    private final QueueClient jobs;

    public DocumentWorker(BlobServiceClient blobService,
                          QueueServiceClient queueService) {
        this.documents = blobService.getBlobContainerClient("documents");
        this.jobs = queueService.getQueueClient("document-jobs");
    }

    @Scheduled(fixedDelayString = "PT5S")
    public void poll() {
        jobs.receiveMessages(4).forEach(message -> {
            try {
                String blobName = message.getBody().toString();
                var blob = documents.getBlobClient(blobName);
                var content = blob.downloadContent();

                // TODO: kiểm tra jobId đã xử lý chưa, lập chỉ mục tài liệu,
                //       lưu kết quả theo khóa idempotency vào database.
                indexDocument(blobName, content.toBytes());

                jobs.deleteMessage(message.getMessageId(),
                                   message.getPopReceipt());
            } catch (Exception ex) {
                log.warn("Xử lý queue message thất bại; sẽ retry theo policy",
                         ex);
            }
        });
    }

    private void indexDocument(String key, byte[] bytes) {
        // Triển khai xử lý tài liệu và idempotency tại đây.
    }
}
~~~

**Giới hạn của ví dụ:** `indexDocument` là chỗ để bổ sung nghiệp vụ, chưa phải bộ lập chỉ mục hoàn chỉnh. `downloadContent().toBytes()` chỉ phù hợp với tệp nhỏ; tệp lớn nên đọc qua stream hoặc xử lý theo chunk để tránh dùng quá nhiều bộ nhớ. Thời gian invisibility của message phải đủ cho một lượt xử lý, hoặc worker cần gia hạn visibility phù hợp. Khi lỗi lặp nhiều lần, ứng dụng cần kiểm tra `dequeue count` và chuyển sang poison queue, đồng thời ghi telemetry để vận hành. Việc xóa message phải diễn ra **sau khi** kết quả được lưu thành công.

### 6.4. Nếu bài toán thực sự cần Azure Files

Một dịch vụ tạo báo cáo chạy trên nhiều instance và phải ghi vào cùng cây thư mục `/mnt/reports` có thể dùng Azure Files. Hai cách triển khai:

1. **Mount file share** qua SMB/NFS (nếu hạ tầng và giao thức hỗ trợ), rồi dùng `java.nio.file.Files` như ở mục 4.
2. **Dùng Azure Files SDK** (`com.azure:azure-storage-file-share`) để truy cập share/directory/file qua REST mà không mount.

Chọn cơ chế xác thực/ủy quyền phù hợp cho **SMB/NFS** hoặc **REST**; chúng không có cách cấp quyền giống nhau. Không giả định rằng gán role data-plane cho Blob sẽ tự cấp quyền cho File Share.

## 7. Xác thực, phân quyền và bảo vệ dữ liệu

Ở môi trường Azure, ưu tiên **Microsoft Entra ID và managed identity** khi SDK/dịch vụ/phương thức truy cập hỗ trợ. Với Spring Cloud Azure, cấu hình credential tập trung giúp tránh đưa secret vào source. Việc có quyền quản lý storage account ở management plane **không tự đồng nghĩa** ứng dụng có mọi quyền đọc/ghi dữ liệu.

| Dịch vụ / cách truy cập | Điều cần cấu hình |
|---|---|
| Blob qua Azure SDK/REST | Data-plane RBAC phù hợp, ví dụ **Storage Blob Data Contributor** khi cần upload; hạn chế container và tài khoản ứng dụng theo quyền tối thiểu |
| Queue qua Azure SDK/REST | Data-plane RBAC phù hợp, ví dụ **Storage Queue Data Contributor** cho producer/worker khi cần gửi, nhận và xóa message; nên tách quyền nếu vai trò cho phép |
| Azure Files qua SMB | Cấu hình xác thực phù hợp (chẳng hạn tích hợp danh tính), quyền share và ACL trên file/directory theo mô hình SMB |
| Azure Files qua REST/SDK | Cơ chế credential và role/quyền tương thích với phiên bản API/SDK, tính năng OAuth và kiểu thao tác đang dùng |

Đi kèm với quyền tối thiểu là **HTTPS/TLS**, hạn chế truy cập public, firewall/private endpoint khi phù hợp, mã hóa dữ liệu, audit log và vòng đời lưu trữ. Nếu phát hành **SAS**, cấp đúng resource, quyền và thời gian hiệu lực cần thiết; không đưa SAS lâu dài vào log hoặc tài liệu công khai. Secret cần được bảo vệ bằng công cụ như **Azure Key Vault** nếu trường hợp triển khai bắt buộc sử dụng secret.

## 8. Kiểm thử tích hợp và các lỗi thường gặp

Để kiểm chứng một thiết kế Spring Boot + Azure Storage, cần thử đủ **cả luồng thành công và luồng thất bại**:

| Kiểm thử | Điều cần xác nhận |
|---|---|
| Upload tài liệu | Blob tồn tại, nội dung và metadata đúng; API không tự ý công khai dữ liệu riêng tư |
| Gửi công việc | Queue có message mang ID/blob name; worker tìm đúng Blob |
| Worker thành công | Kết quả nghiệp vụ được lưu; message bị xóa; xử lý lại cùng job không tạo bản ghi trùng |
| Worker bị lỗi giữa chừng | Message có thể xuất hiện lại sau visibility timeout; retry không làm hỏng dữ liệu |
| Message lỗi liên tục | Có ngưỡng retry, poison queue, cảnh báo và hướng xử lý thủ công |
| Thiếu quyền hoặc chặn mạng | Ứng dụng báo lỗi có thể chẩn đoán; không fallback sang key hardcode |
| Blob đã lưu nhưng queue gửi lỗi | Có retry/đối soát để không bỏ sót công việc |
| Dùng File Share | Hai tiến trình truy cập đường dẫn mong đợi; quyền mount/ACL, khóa tệp và tính nhất quán phù hợp nghiệp vụ |

**Azurite** hữu ích khi kiểm thử local cho Blob/Queue, nhưng không phải bản sao đầy đủ của tất cả tính năng của Azure Storage và **không hỗ trợ Azure Files** như một file share thật. Kiểm thử quyền Entra ID, private endpoint, mount SMB/NFS, giới hạn và đặc tính vận hành cần dùng môi trường Azure thử nghiệm. Khi viết integration test, dùng dữ liệu/tài khoản riêng, dọn tài nguyên theo vòng đời test và cố tình gửi message trùng để kiểm tra idempotency.

Những sai lầm phổ biến:

- Nhét toàn bộ PDF hoặc payload lớn vào Queue message thay vì lưu ở Blob.
- Lưu nội dung ảnh trong File Share chỉ vì “ảnh là file”, dù ứng dụng chỉ upload và tải qua HTTP.
- Dùng Blob như filesystem có khóa file/đường dẫn mount và chờ mọi thao tác giống SMB.
- Xóa Queue message **trước khi** nghiệp vụ hoàn tất, khiến công việc thất bại bị mất.
- Cho rằng Queue message chỉ tới worker đúng một lần và luôn theo đúng thứ tự gửi.
- Kiểm thử local bằng account key rồi quên xác minh quyền data-plane của managed identity khi triển khai Azure.

## 9. Bài tập tình huống và câu hỏi tự kiểm tra

**Tình huống A — Ứng dụng tuyển dụng:** Người dùng gửi CV PDF, backend lưu tệp và một worker OCR trích xuất văn bản. **Giải pháp:** Blob giữ CV; Queue giữ job `cvId`/`blobName`; worker đọc Blob, xử lý idempotent và xóa message khi xong. File Share không cần thiết nếu không có yêu cầu thư mục mount.

**Tình huống B — Ứng dụng kế toán cũ:** Nhiều máy chủ chạy chương trình viết tệp theo đường dẫn thư mục và chia sẻ file Excel giữa các tiến trình. **Giải pháp:** cân nhắc Azure Files và kiểm chứng SMB/NFS, ACL, khóa tệp, độ trễ và mô hình triển khai. Chuyển thẳng sang Blob có thể đòi hỏi viết lại logic filesystem.

**Tình huống C — Gửi thông báo cho ba hệ thống độc lập:** Mỗi sự kiện phải được ba ứng dụng nhận, với quy tắc retry và dead-letter riêng. **Giải pháp:** Storage Queue đơn lẻ không tự phát cùng message cho cả ba consumer; cân nhắc Azure Service Bus Topics hoặc Event Grid tùy ngữ nghĩa cần có.

Tự trả lời trước khi xem gợi ý:

1. Tại sao Queue nên chứa `blobName` thay vì nội dung tệp? — Vì giới hạn message nhỏ và vai trò của Queue là điều phối công việc, còn Blob mới lưu dữ liệu lớn.
2. Khi nào Azure Files có lợi thế rõ ràng so với Blob? — Khi ứng dụng cần thư mục/đường dẫn mount, chia sẻ tệp và các thao tác filesystem.
3. Worker xử lý xong nghiệp vụ nhưng chết trước khi xóa message sẽ ra sao? — Message có thể được nhận lại; cần idempotency để không xử lý sai hoặc tạo kết quả trùng.
4. Vì sao gán quyền quản lý storage account chưa chắc giúp SDK upload Blob? — Vì quyền quản lý tài nguyên và quyền dữ liệu (data plane) là hai phạm vi cần kiểm tra riêng.

## 10. Tổng kết

**Blob = nội dung**, **File Share = filesystem dùng chung**, **Queue = thông điệp giao việc**. Trong ứng dụng Spring Boot hiện đại, tổ hợp **Blob + Queue** phổ biến khi cần upload rồi xử lý bất đồng bộ; **Azure Files** chỉ phát huy lợi thế khi luồng nghiệp vụ thực sự cần chia sẻ thư mục/tệp theo ngữ nghĩa filesystem. Chọn dịch vụ theo kiểu truy cập, tính nhất quán/xử lý lại, yêu cầu danh tính và vận hành; sau đó kiểm thử cả thành công, lỗi, quyền truy cập và tình huống khôi phục.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — What is Azure Files?](https://learn.microsoft.com/azure/storage/files/storage-files-introduction)
- [Microsoft Learn — Introduction to Azure Queue Storage](https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction)
- [Microsoft Learn — Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
