# Gửi nhận Azure Storage Queue và giới hạn so với Azure Service Bus

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng. Bài học bao gồm cấu hình danh tính và quyền, truy cập storage/messaging/data, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này thuộc chương **Azure Storage**, tập trung vào **Azure Queue Storage** và câu hỏi: khi nào một hàng đợi lưu trữ đơn giản là đủ, khi nào nên chọn **Azure Service Bus**?

Ví dụ xuyên suốt: API nhận hồ sơ PDF, lưu file vào Azure Blob Storage rồi gửi một thông điệp để worker OCR xử lý. API cần gửi việc nhanh mà không chờ OCR hoàn tất; worker có thể tạm dừng, khởi động lại hoặc chạy nhiều bản sao. Hệ thống phải xử lý trường hợp worker nhận lại cùng message, xử lý quá visibility timeout và gặp lỗi nhiều lần.

Sau bài này, bạn có thể:

- Giải thích mô hình producer/consumer và các thao tác gửi, nhận, xóa message trong Azure Queue Storage.
- Hiểu **visibility timeout**, **pop receipt**, **dequeue count**, TTL và lý do message có thể được giao lại.
- Tích hợp Queue Storage với Spring Boot qua Spring Cloud Azure và Azure Storage Queue SDK for Java.
- Thiết kế consumer idempotent, retry có giới hạn và poison queue.
- So sánh Queue Storage với Service Bus về ordering, topic/subscription, session, dead-letter, transaction và giới hạn message.
- Chọn dịch vụ dựa trên semantics nghiệp vụ, yêu cầu vận hành và chi phí tổng thể.

## 2. Azure Queue Storage hoạt động như thế nào?

**Azure Queue Storage** là dịch vụ lưu message theo mô hình queue đơn giản. Producer gửi message vào một queue; consumer nhận message, xử lý rồi xóa message khi hoàn tất.

~~~mermaid
flowchart LR
    API[Spring Boot API / Producer] -->|sendMessage| Q[(Azure Storage Queue)]
    Q -->|receiveMessages| W1[Worker A]
    Q -->|receiveMessages| W2[Worker B]
    W1 -->|deleteMessage sau thành công| Q
    W2 -->|deleteMessage sau thành công| Q
~~~

Các thành phần:

- **Storage account:** tài nguyên Azure chứa dịch vụ Queue.
- **Queue:** một hàng đợi có tên, ví dụ `document-jobs`.
- **Message:** nội dung công việc, thường là JSON nhỏ chứa job ID và tham chiếu tới dữ liệu.
- **Producer:** thành phần tạo message bằng thao tác enqueue.
- **Consumer/worker:** thành phần nhận, xử lý và xóa message.

Queue Storage phù hợp với **work queue**: nhiều worker cùng lấy những công việc khác nhau từ một hàng đợi. Dịch vụ giúp tách thời điểm gửi việc khỏi thời điểm xử lý, nhưng không tự quản lý trạng thái nghiệp vụ của job trong database.

### 2.1. Vì sao message không biến mất ngay khi consumer nhận?

Khi consumer nhận message, Azure Queue Storage thường **ẩn message trong một khoảng thời gian** gọi là visibility timeout. Trong khoảng đó, consumer khác không nhận được message này qua thao tác receive thông thường. Consumer đầu tiên phải xử lý rồi xóa message bằng **message ID và pop receipt** hiện tại.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Storage Queue
    participant W as Worker
    P->>Q: Enqueue message
    W->>Q: Receive message
    Q-->>W: Message + messageId + popReceipt
    Note over Q: Message tạm thời invisible
    W->>W: Xử lý công việc
    W->>Q: Delete bằng messageId + popReceipt
    Q-->>W: Xóa thành công
~~~

Nếu worker chết, timeout hết hoặc worker không xóa message, message có thể xuất hiện lại để consumer khác nhận. Đây là cơ chế hỗ trợ khôi phục sau lỗi, nhưng cũng có nghĩa **cùng một công việc có thể được giao nhiều lần**.

## 3. Những khái niệm phải hiểu trước khi viết consumer

| Khái niệm | Ý nghĩa | Điều consumer cần làm |
|---|---|---|
| **Message ID** | Định danh message do dịch vụ cấp | Dùng khi xóa hoặc cập nhật message |
| **Pop receipt** | Token đại diện cho lần nhận/cập nhật hiện tại | Dùng cùng message ID; receipt cũ có thể không còn hợp lệ |
| **Visibility timeout** | Khoảng thời gian message bị ẩn sau khi nhận | Đảm bảo đủ dài cho xử lý hoặc gia hạn khi cần |
| **Dequeue count** | Số lần message được nhận khỏi queue | Theo dõi retry và phát hiện message lỗi kéo dài |
| **TTL (time to live)** | Thời gian message được phép tồn tại trong queue | Chọn thời hạn phù hợp với SLA công việc |
| **Approximate message count** | Số message ước lượng trong queue | Quan sát backlog, không dùng làm số liệu giao dịch chính xác |

### 3.1. Visibility timeout không phải thời gian xử lý tối đa tuyệt đối

Ví dụ worker nhận một message với visibility timeout 60 giây:

- Nếu xử lý xong sau 20 giây và xóa thành công, message biến mất khỏi queue.
- Nếu xử lý kéo dài hơn 60 giây mà không gia hạn visibility, message có thể hiển thị lại và worker khác có thể nhận.
- Nếu worker xử lý xong nhưng lệnh delete thất bại do lỗi mạng hoặc pop receipt không còn hợp lệ, message có thể được giao lại.

Với công việc dài, consumer có thể **cập nhật message để gia hạn visibility timeout** và phải lưu pop receipt mới trả về. Thiết kế cần có heartbeat hoặc cơ chế gia hạn có giới hạn, tránh gia hạn vô hạn khi worker bị treo.

### 3.2. Pop receipt thay đổi theo lần nhận

Mỗi lần receive hoặc update message có thể tạo **pop receipt mới**. Khi xóa, phải dùng receipt hợp lệ gần nhất:

~~~text
Lần nhận 1: messageId = M42, popReceipt = R1
    Worker xử lý quá thời gian visibility.

Lần nhận 2: messageId = M42, popReceipt = R2
    R2 là receipt hiện tại; R1 đã cũ.

Delete(M42, R1) -> có thể thất bại.
Delete(M42, R2) -> đúng lần nhận hiện tại.
~~~

Không lưu pop receipt như một khóa nghiệp vụ lâu dài; nó là chi tiết giao thức của lần nhận message. Nếu worker cần tiếp tục xử lý sau khi restart, hãy lưu **job ID và trạng thái nghiệp vụ**, rồi nhận message lại theo cơ chế queue.

### 3.3. TTL và kích thước message

Azure Queue Storage giới hạn kích thước message tối đa **64 KiB**. Nếu producer Base64-encode payload, phần dữ liệu gốc phải nhỏ hơn vì Base64 làm tăng kích thước. Hãy kiểm tra giới hạn theo **message sau encoding** và cấu hình encoding của cả producer lẫn consumer phải thống nhất.

TTL quyết định message có thể nằm trong queue bao lâu. Hãy đặt thời hạn phù hợp với loại công việc; message hết hạn không còn là cơ chế lưu trữ lâu dài. Azure Queue Storage có các API version hỗ trợ cấu hình message không hết hạn, nhưng cần kiểm tra phiên bản dịch vụ/SDK và chính sách vận hành trước khi dùng. Đối với công việc cần lưu lịch sử, hãy lưu trạng thái ở database hoặc storage phù hợp.

**Không đưa PDF, video hoặc JSON lớn vào queue message.** Lưu nội dung ở Blob Storage, rồi gửi tham chiếu như `documentId`, `blobName`, `jobId`. Queue là kênh điều phối công việc, không phải kho payload lớn.

## 4. Cấu trúc message và thiết kế producer

Message nên chứa đủ thông tin để consumer tìm dữ liệu và kiểm tra trạng thái, nhưng tránh nhúng toàn bộ nội dung file.

Ví dụ payload:

~~~json
{
  "jobId": "ocr-42",
  "documentId": "doc-2026-0042",
  "blobName": "incoming/2026/doc-2026-0042.pdf",
  "operation": "OCR",
  "schemaVersion": 1,
  "createdAt": "2026-11-24T09:30:00Z"
}
~~~

Các trường có mục đích:

- `jobId`: định danh ổn định của một lần xử lý nghiệp vụ; hỗ trợ idempotency và audit.
- `documentId`: khóa tài liệu trong database, dùng để kiểm tra owner/tenant và trạng thái.
- `blobName`: tham chiếu object trong container; không phải quyền truy cập file.
- `operation`: loại công việc consumer cần thực hiện.
- `schemaVersion`: hỗ trợ nâng cấp định dạng message mà không làm hỏng consumer cũ.
- `createdAt`: thời điểm tạo job để đo thời gian chờ và SLA.

### 4.1. Cấu hình Maven và application.yml

Khai báo BOM Spring Cloud Azure tương thích với phiên bản Spring Boot của dự án và starter Queue Storage:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

Trong `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  queue:
    document-jobs: ${DOCUMENT_JOBS_QUEUE:document-jobs}
~~~

`spring-cloud-azure.version` phải được chọn theo bảng tương thích Spring Boot/Spring Cloud Azure của dự án. Ví dụ giả định queue `document-jobs` đã được provision trước; ứng dụng runtime không cần quyền quản trị subscription để tự tạo storage account.

Với credential, ưu tiên **Microsoft Entra ID và managed identity** khi chạy trên Azure. Local developer có thể dùng Azure CLI login theo chính sách tổ chức. Không commit account key, connection string hoặc SAS vào Git.

### 4.2. Producer sử dụng QueueServiceClient

Spring Cloud Azure Storage Queue starter có thể auto-configure Azure Queue client để inject vào Spring bean. Ví dụ dùng `QueueServiceClient`:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentJobProducer {
    private final QueueClient queue;
    private final ObjectMapper objectMapper;

    public DocumentJobProducer(
            QueueServiceClient queueServiceClient,
            ObjectMapper objectMapper,
            @Value("${app.queue.document-jobs}") String queueName) {
        this.queue = queueServiceClient.getQueueClient(queueName);
        this.objectMapper = objectMapper;
    }

    public void enqueue(DocumentJob job) {
        try {
            String json = objectMapper.writeValueAsString(job);
            queue.sendMessage(json);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Không thể serialize document job", ex);
        }
    }
}
~~~

`DocumentJob` là DTO của ứng dụng, ví dụ:

~~~java
import java.time.Instant;

public record DocumentJob(
        String jobId,
        String documentId,
        String blobName,
        String operation,
        int schemaVersion,
        Instant createdAt) {
}
~~~

`getQueueClient(queueName)` tạo client tham chiếu đến queue; nó không tự tạo queue trên Azure. Queue nên được tạo qua IaC hoặc migration. Nếu cần thao tác quản trị trong môi trường test, SDK có `createIfNotExists()`, nhưng không nên dùng mỗi lần xử lý request production.

### 4.3. Blob + Queue: mẫu tích hợp thường gặp

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant B as Blob Storage
    participant D as Database
    participant Q as Storage Queue
    participant W as OCR Worker
    C->>A: Upload PDF
    A->>B: Lưu blob
    A->>D: Tạo document/job trạng thái PENDING
    A->>Q: Enqueue jobId + blobName
    A-->>C: 202 Accepted
    Q-->>W: Worker nhận job
    W->>B: Đọc PDF
    W->>D: Lưu kết quả OCR / COMPLETED
    W->>Q: Delete message
~~~

Blob và Queue không có transaction chung. Nếu upload Blob thành công nhưng gửi Queue thất bại, có thể tồn tại tài liệu chưa được xử lý. Nếu DB commit nhưng enqueue thất bại, trạng thái nghiệp vụ có thể bị kẹt. Với luồng quan trọng, hãy dùng **transactional outbox** trong database, retry có kiểm soát hoặc job đối soát thay vì giả định ba thao tác luôn thành công cùng lúc.

## 5. Consumer: nhận, xử lý và xóa message

### 5.1. Consumer cơ bản

Consumer chỉ xóa message **sau khi nghiệp vụ đã hoàn tất và kết quả được lưu bền vững**:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.models.QueueMessageItem;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DocumentJobConsumer {
    private final QueueClient queue;
    private final ObjectMapper objectMapper;
    private final DocumentProcessor processor;

    public DocumentJobConsumer(
            QueueServiceClient queueServiceClient,
            ObjectMapper objectMapper,
            DocumentProcessor processor,
            @Value("${app.queue.document-jobs}") String queueName) {
        this.queue = queueServiceClient.getQueueClient(queueName);
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    public void pollOnce() {
        for (QueueMessageItem message : queue.receiveMessages(5)) {
            try {
                DocumentJob job = objectMapper.readValue(
                        message.getMessageText(), DocumentJob.class);

                processor.processIdempotently(job);

                queue.deleteMessage(
                        message.getMessageId(),
                        message.getPopReceipt());
            } catch (Exception ex) {
                // Không xóa message khi xử lý chưa thành công.
                // Sau visibility timeout, message có thể được giao lại.
                // Ghi log job/message ID và error code, không log dữ liệu nhạy cảm.
            }
        }
    }
}
~~~

Đây là phương thức poll một lượt; cần một scheduler/worker lifecycle để gọi nó theo nhịp phù hợp hoặc dùng cơ chế polling mà ứng dụng quản lý. `receiveMessages(5)` dùng visibility timeout mặc định của API/SDK; nếu công việc có thời gian xử lý dài, hãy chọn overload nhận timeout phù hợp và có cơ chế gia hạn message. Đừng dùng một poll loop không giới hạn khiến CPU tăng khi queue rỗng.

`DocumentProcessor.processIdempotently` là phần nghiệp vụ cần triển khai. Ví dụ không thể tự bảo đảm xử lý đúng một lần chỉ nhờ lệnh delete; worker có thể chết sau khi lưu kết quả nhưng trước khi xóa message.

### 5.2. Thứ tự xử lý quan trọng

1. Nhận message và lấy `messageId`, `popReceipt`, `dequeueCount`.
2. Parse/validate schema và kiểm tra `jobId`.
3. Claim job trong database bằng unique key/optimistic update để ngăn xử lý trùng.
4. Xử lý dữ liệu từ Blob; ghi kết quả bền vững.
5. Đánh dấu job `COMPLETED`.
6. Xóa message bằng **pop receipt mới nhất**.

Nếu xóa message trước khi lưu kết quả, worker có thể chết ngay sau delete và công việc bị mất khỏi queue. Nếu lưu kết quả trước khi delete mà worker chết, message có thể được giao lại; do đó processor phải idempotent.

### 5.3. Gia hạn visibility cho công việc dài

Nếu một công việc có thể kéo dài hơn visibility timeout, consumer cần cập nhật message để đặt lại thời điểm message có thể hiển thị. Sau update, dùng **pop receipt mới** trả về cho lần delete/update kế tiếp.

~~~text
Receive(message, visibility = 60s) -> popReceipt R1
    Xử lý được 45s, còn đang chạy
UpdateMessage(messageId, R1, visibility = 60s)
    -> popReceipt R2
    Xử lý tiếp
DeleteMessage(messageId, R2)
~~~

Không gia hạn vô hạn. Nếu job vượt quá SLA hoặc worker mất heartbeat, nên cho phép message được nhận lại, đánh dấu attempt và chuyển qua quy trình lỗi. Với job dài nhiều giờ, cân nhắc tách thành các bước nhỏ hoặc dùng một workflow engine/Service Bus phù hợp hơn.

## 6. Delivery semantics: vì sao cần idempotency?

Azure Queue Storage có thể giao lại message. Ví dụ:

1. Worker xử lý xong và ghi kết quả OCR vào database.
2. Worker mất kết nối trước khi delete message.
3. Visibility timeout hết; message được nhận lại.
4. Worker khác xử lý cùng job lần nữa.

Đây là lý do consumer nên được thiết kế theo hướng **at-least-once processing** và **idempotent handler**. Không nên hứa hẹn exactly-once chỉ dựa trên queue.

### 6.1. Bảng trạng thái job

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| PENDING | Đã ghi nhận yêu cầu, chờ worker | Có thể claim để xử lý |
| PROCESSING | Một worker đang xử lý | Ghi worker ID/lease nghiệp vụ và thời điểm heartbeat |
| COMPLETED | Kết quả đã lưu bền vững | Nếu message được giao lại, bỏ qua nghiệp vụ và xóa message |
| FAILED_RETRYABLE | Lỗi tạm thời | Cho phép retry theo policy |
| FAILED_FINAL | Lỗi không thể khắc phục tự động | Chuyển poison queue hoặc yêu cầu can thiệp |

### 6.2. Idempotency bằng khóa duy nhất

Ví dụ database có bảng `processed_jobs` với unique constraint trên `job_id`:

~~~sql
CREATE TABLE processed_jobs (
    job_id        VARCHAR(100) PRIMARY KEY,
    document_id   VARCHAR(100) NOT NULL,
    status        VARCHAR(30) NOT NULL,
    result_ref    VARCHAR(500),
    completed_at  TIMESTAMP
);
~~~

Luồng xử lý:

- Worker cố gắng tạo/claim record theo `jobId` trong transaction.
- Nếu job đã `COMPLETED`, worker không chạy lại side effect; chỉ xác nhận message có thể xóa.
- Nếu job đang `PROCESSING` bởi worker khác, áp dụng cơ chế claim/timeout để tránh hai worker cùng làm.
- Sau khi xử lý xong, ghi kết quả và trạng thái `COMPLETED` trong transaction phù hợp.

Unique key giúp ngăn tạo hai record job, nhưng **không tự làm mọi side effect bên ngoài trở nên idempotent**. Nếu gọi API thanh toán, gửi email hoặc ghi Blob, cần idempotency key hoặc kiểm tra trạng thái tương ứng ở dịch vụ đích.

### 6.3. Xử lý poison message

**Poison message** là message liên tục thất bại do payload sai, thiếu dữ liệu, schema không tương thích hoặc lỗi nghiệp vụ không thể tự khắc phục.

Azure Queue Storage không có dead-letter queue tích hợp như Service Bus. Ứng dụng thường tạo queue riêng, ví dụ `document-jobs-poison`:

~~~mermaid
flowchart TD
    Q[(document-jobs)] --> W[Worker]
    W --> S{Xử lý thành công?}
    S -->|Có| D[Delete message gốc]
    S -->|Lỗi tạm thời| R[Để message xuất hiện lại / retry]
    R --> Q
    S -->|Quá ngưỡng dequeue count| P[(document-jobs-poison)]
    P --> O[Alert + điều tra + replay có kiểm soát]
~~~

Quy trình chuyển poison an toàn:

1. Đọc `dequeueCount` và xác định ngưỡng retry.
2. Ghi message gốc cùng lỗi, thời điểm và correlation ID vào poison queue hoặc kho lỗi.
3. **Chỉ xóa message gốc sau khi** thao tác ghi poison thành công.
4. Phát cảnh báo và cung cấp công cụ replay có kiểm soát sau khi sửa nguyên nhân.

Nếu ghi poison thất bại, không xóa message gốc; để nó retry theo visibility. Tránh đưa thông tin nhạy cảm hoặc toàn bộ nội dung file vào log/poison message nếu không cần.

## 7. Spring Cloud Azure và Azure Storage Queue SDK

### 7.1. Auto-configuration và credential

Starter `spring-cloud-azure-starter-storage-queue` giúp ứng dụng Spring Boot tích hợp Azure Queue Storage. Khi starter và cấu hình hợp lệ, ứng dụng có thể inject `QueueServiceClient` được auto-configure:

~~~java
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Component;

@Component
public class QueueClientHolder {
    private final QueueServiceClient client;

    public QueueClientHolder(QueueServiceClient client) {
        this.client = client;
    }
}
~~~

`QueueServiceClient` đại diện dịch vụ Queue trong storage account; `QueueClient` đại diện một queue cụ thể. Client SDK có thể được tái sử dụng qua nhiều request, không tạo mới cho mỗi message.

### 7.2. Azure Identity và RBAC

Khi chạy trên Azure, ưu tiên **managed identity**. Một số role data-plane thường dùng:

| Vai trò producer/consumer | Role nên xem xét |
|---|---|
| Chỉ gửi message | **Storage Queue Data Message Sender** |
| Nhận và xử lý message | **Storage Queue Data Message Processor** |
| Cần nhiều thao tác đọc/ghi Queue data | **Storage Queue Data Contributor** |
| Quản trị queue/resource | Role quản trị tương ứng, cấp riêng cho pipeline/hạ tầng |

Gán role cho **principal của managed identity** ở scope storage account/queue phù hợp. Quyền quản lý resource qua Azure Resource Manager không tự đồng nghĩa quyền gửi/nhận dữ liệu Queue. Nếu local developer chạy được nhưng production 403, hãy xác định danh tính thực tế của workload và role data-plane được gán.

### 7.3. Queue name và provision

Queue name phải theo quy tắc Azure Queue Storage: chữ thường, chữ số và dấu gạch nối, bắt đầu bằng chữ cái/số và có độ dài hợp lệ (thông dụng **3–63 ký tự**). Ví dụ `document-jobs`, `invoice-events`.

Provision queue qua IaC hoặc migration có kiểm soát. Trong test có thể dùng `createIfNotExists()`; runtime production nên chỉ có quyền cần thiết cho hoạt động gửi/nhận. Nếu queue chưa tồn tại, SDK sẽ trả lỗi resource not found khi gửi/nhận.

## 8. Azure Queue Storage so với Azure Service Bus

Hai dịch vụ đều có queue, nhưng phục vụ **mức độ phức tạp messaging khác nhau**. Queue Storage thuộc Azure Storage; Service Bus là message broker chuyên dụng với nhiều semantics doanh nghiệp hơn.

| Tiêu chí | Azure Queue Storage | Azure Service Bus |
|---|---|---|
| Mục tiêu | Hàng đợi công việc đơn giản, lưu message trong Storage | Messaging doanh nghiệp, tách rời service với semantics phong phú |
| API/protocol | Azure Storage Queue REST/SDK qua HTTPS | AMQP 1.0 và các giao thức/API được hỗ trợ |
| Kích thước message | Tối đa **64 KiB** | Lớn hơn đáng kể và phụ thuộc tier/protocol; cần kiểm tra giới hạn hiện hành |
| Mô hình queue | Queue đơn, competing consumers | Queue, Topic và Subscription |
| Publish/subscribe | Không có topic/subscription native | Topic phát message đến nhiều subscription |
| Ordering | Không bảo đảm FIFO tuyệt đối | Sessions hỗ trợ thứ tự xử lý trong cùng session khi được cấu hình |
| Duplicate detection | Ứng dụng tự thiết kế idempotency/deduplication | Có tính năng duplicate detection theo MessageId trong thời gian cấu hình; không phải exactly-once end-to-end |
| Dead-letter | Tự xây poison queue/kho lỗi | Có dead-letter queue tích hợp |
| Lock/visibility | Visibility timeout và pop receipt | Peek-Lock, lock duration, renew lock, complete/abandon/dead-letter |
| Transaction | Không có transaction messaging đa thao tác như Service Bus | Hỗ trợ transaction cho các thao tác được dịch vụ cho phép |
| Scheduled/deferred message | Không có bộ tính năng phong phú tương đương | Hỗ trợ scheduled và deferred messages |
| Session/grouping | Không có session semantics | Sessions hỗ trợ nhóm message và xử lý tuần tự theo session |
| Filtering/routing | Ứng dụng tự định tuyến hoặc dùng queue riêng | Topic subscription filters/rules |
| Vận hành | Đơn giản, nằm trong Storage account | Broker chuyên dụng, cần cấu hình namespace/tier và giám sát riêng |

### 8.1. Queue Storage phù hợp khi nào?

Chọn Queue Storage nếu:

- Chỉ cần **một work queue** cho producer và nhiều worker.
- Payload nhỏ, message chủ yếu chứa ID/tham chiếu Blob.
- Không cần FIFO/session, topic/subscription hoặc transaction messaging.
- Ứng dụng đã dùng Azure Storage và muốn mô hình vận hành đơn giản.
- Có thể triển khai idempotency, retry và poison queue ở tầng ứng dụng.

Ví dụ: sau khi upload ảnh, gửi job tạo thumbnail; nhiều worker có thể xử lý ảnh khác nhau, và database lưu trạng thái job.

### 8.2. Service Bus phù hợp khi nào?

Chọn Service Bus nếu yêu cầu có một hoặc nhiều đặc điểm:

- Một sự kiện phải được phân phối đến **nhiều subscriber độc lập** qua Topic/Subscription.
- Cần **sessions** để xử lý tuần tự theo nhóm/aggregate, ví dụ mọi lệnh của một đơn hàng.
- Cần **dead-letter queue** tích hợp, scheduled/deferred message hoặc transaction messaging.
- Cần duplicate detection theo MessageId, correlation/filter/routing phong phú.
- Cần broker chuyên dụng để điều phối giao tiếp giữa nhiều hệ thống nghiệp vụ.

Ví dụ: sự kiện `OrderPlaced` cần được gửi cho billing, fulfillment và notification, mỗi hệ thống có subscription và retry/DLQ riêng. Một Queue Storage đơn lẻ không tự fan-out cùng message cho cả ba consumer.

### 8.3. Duplicate detection không phải exactly-once

Service Bus có thể loại message gửi trùng theo MessageId trong cửa sổ duplicate detection đã cấu hình. Điều đó giúp giảm trùng do producer retry, nhưng không biến toàn bộ workflow thành exactly-once:

- Consumer vẫn có thể nhận lại message khi lock hết hạn hoặc xử lý thất bại.
- Side effect bên ngoài broker vẫn cần idempotency.
- Duplicate detection chỉ áp dụng trong giới hạn cấu hình và semantics dịch vụ.

Với cả hai dịch vụ, hãy thiết kế consumer an toàn khi xử lý lặp.

## 9. Ví dụ gửi và nhận bằng Azure Service Bus SDK

Để thấy sự khác biệt ở code, Service Bus dùng sender/receiver client chuyên biệt. Thêm starter `spring-cloud-azure-starter-servicebus` nếu tích hợp Spring Cloud Azure; hoặc dùng Azure Service Bus SDK trực tiếp khi cần kiểm soát rõ client.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusMessage;

String namespace = System.getenv("AZURE_SERVICEBUS_NAMESPACE");
TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

ServiceBusSenderClient sender = new ServiceBusClientBuilder()
        .credential(namespace, credential)
        .sender()
        .queueName("document-jobs")
        .buildClient();

sender.sendMessage(new ServiceBusMessage(
        "{\"jobId\":\"ocr-42\",\"documentId\":\"doc-42\"}"));
~~~

Đây là ví dụ gửi message vào **Service Bus queue**, không phải Storage Queue. Namespace thường có dạng `<namespace>.servicebus.windows.net`; danh tính cần role Service Bus data-plane phù hợp, ví dụ **Azure Service Bus Data Sender**. Đóng sender client theo vòng đời ứng dụng (ví dụ bean quản lý shutdown), không tạo/đóng client cho mỗi request.

Với Service Bus receiver ở chế độ **Peek-Lock**, consumer nhận message rồi gọi:

~~~java
// Pseudocode mô tả thứ tự xử lý; receiver là ServiceBusReceiverClient.
for (var message : receiver.receiveMessages(10)) {
    try {
        processIdempotently(message.getBody());
        receiver.complete(message);
    } catch (Exception ex) {
        receiver.abandon(message);
    }
}
~~~

`complete` xác nhận message đã xử lý và xóa khỏi queue/subscription. `abandon` giải phóng lock để message có thể được nhận lại. Ngoài ra có thể dead-letter message khi lỗi không thể xử lý. Trong code thực tế, cần chọn overload phù hợp với kiểu body và quản lý lifecycle receiver/processor; pseudocode trên nhấn mạnh **Peek-Lock/complete/abandon** khác với Queue Storage **visibility timeout/pop receipt/delete**.

## 10. Kiểm thử tích hợp

### 10.1. Azurite cho Queue Storage

**Azurite** hỗ trợ mô phỏng Azure Queue Storage để kiểm thử logic gửi/nhận cơ bản ở local. Nó không mô phỏng đầy đủ managed identity/RBAC, firewall/private endpoint, scale, throttling và mọi hành vi production của Azure. Kiểm thử các quyền data-plane và network cần storage account Azure dành riêng cho integration test.

Không dùng account key production trong test fixture. Tách queue test theo run/job ID và cleanup message/queue theo vòng đời test.

### 10.2. Ma trận test cho Storage Queue

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| Producer gửi JSON job | Queue nhận đúng payload và schemaVersion |
| Consumer nhận rồi xử lý thành công | Kết quả được lưu bền vững và message được xóa bằng pop receipt hiện tại |
| Worker chết trước khi delete | Message hiển thị lại sau visibility timeout |
| Worker xử lý lâu | Visibility được gia hạn đúng cách; receipt mới được sử dụng |
| Gửi cùng jobId hai lần | Processor không tạo side effect trùng |
| Payload sai schema | Có retry giới hạn hoặc chuyển poison queue |
| Ghi poison queue thất bại | Message gốc vẫn được giữ để retry |
| Queue rỗng | Polling không gây busy loop/CPU tăng |
| Thiếu RBAC | 403 được chẩn đoán theo principal và scope |
| Message quá 64 KiB | Producer từ chối hoặc chuyển payload lớn sang Blob |
| TTL hết hạn | Message không còn được coi là công việc đang chờ |
| Nhiều worker cạnh tranh | Không giả định FIFO; trạng thái job được cập nhật an toàn |

### 10.3. Test với Service Bus thật

Azurite không giả lập Azure Service Bus. Nếu chọn Service Bus, hãy dùng namespace test riêng để kiểm tra:

- Peek-Lock, complete, abandon, lock renewal và lock expiry.
- Dead-letter queue và replay message.
- Sessions, thứ tự trong cùng session và concurrency giữa sessions.
- Duplicate detection theo MessageId.
- Topic/Subscription, filter/rule và fan-out.
- Transaction messaging trong phạm vi operation được hỗ trợ.

Kiểm thử riêng từng dịch vụ giúp tránh viết abstraction chung quá rộng rồi vô tình làm mất semantics quan trọng của broker.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| HTTP 403 khi gửi/nhận | Managed identity thiếu Queue Data role hoặc storage firewall chặn | Kiểm tra principal, role/scope, endpoint và network |
| HTTP 404 | Queue chưa provision hoặc sai tên/account | Kiểm tra queue name, storage account và môi trường |
| Message xuất hiện lại | Worker không delete, visibility timeout quá ngắn hoặc delete dùng pop receipt cũ | Kiểm tra thời gian xử lý, update visibility và receipt mới |
| Message bị xử lý trùng | At-least-once delivery, producer gửi lại hoặc worker chết sau commit | Dùng jobId/unique key và idempotent processor |
| Queue backlog tăng | Worker thiếu capacity, xử lý chậm hoặc message lỗi lặp | Theo dõi approximate count, latency, dequeue count và scale worker |
| Message biến mất trước khi xử lý | TTL hết hạn hoặc consumer xóa quá sớm | Rà TTL và chỉ delete sau khi kết quả bền vững |
| Queue message quá lớn | Đưa payload/file vào message | Lưu payload ở Blob và gửi reference |
| Poison queue mất message | Xóa message gốc trước khi enqueue poison thành công | Ghi poison bền vững rồi mới xóa bản gốc |
| Không có FIFO như kỳ vọng | Queue Storage không bảo đảm thứ tự tuyệt đối | Dùng Service Bus Sessions nếu ordering theo nhóm là yêu cầu |
| Cần một message cho nhiều hệ thống | Một queue là competing consumers, không phải pub/sub | Chọn Service Bus Topic/Subscription hoặc thiết kế fan-out khác |

## 12. Bảo mật và vận hành

### 12.1. Danh tính và quyền tối thiểu

- Producer chỉ gửi message: cân nhắc **Storage Queue Data Message Sender**.
- Consumer xử lý message: cân nhắc **Storage Queue Data Message Processor**.
- Chỉ dùng **Storage Queue Data Contributor** khi workload cần nhiều thao tác hơn và không có role hẹp phù hợp.
- Gán role cho managed identity tại scope storage account/queue phù hợp; quyền management plane không tự cấp data-plane.
- Không đưa account key, connection string hoặc SAS vào source, log hay message.

### 12.2. Message không phải nơi chứa secret

Không gửi password, access token, SAS URL dài hạn hoặc nội dung nhạy cảm vào message nếu không cần. Queue message có thể bị đọc bởi principal có quyền, xuất hiện trong poison queue/log và được giữ đến khi hết TTL. Nếu message cần chỉ tới tài liệu riêng tư, gửi blob name/document ID; worker dùng managed identity có quyền đọc Blob.

### 12.3. Quan sát và scale

Theo dõi:

- Approximate message count/backlog và tuổi message cũ nhất (ứng dụng có thể tính từ `createdAt`).
- Số message nhận/xóa, dequeue count và tỉ lệ chuyển poison.
- Thời gian xử lý mỗi job, thời gian visibility còn lại và số lượt gia hạn.
- Số worker hoạt động, lỗi 403/404/429/5xx, latency và throughput.
- Job PENDING/PROCESSING quá SLA trong database.

Scale worker theo backlog và thời gian xử lý, nhưng giới hạn concurrency để không làm quá tải Blob Storage, database hoặc dịch vụ OCR. Không dùng approximate message count làm cơ sở duy nhất cho quyết định tài chính hoặc kiểm soát giao dịch.

## 13. Cây quyết định chọn Queue Storage hay Service Bus

~~~mermaid
flowchart TD
    A[Ứng dụng cần gửi công việc bất đồng bộ] --> B{Payload lớn hơn giới hạn queue?}
    B -->|Có| C[Lưu payload ở Blob, chỉ gửi reference]
    B -->|Không| D{Cần topic/subscription fan-out?}
    C --> D
    D -->|Có| SB[Azure Service Bus]
    D -->|Không| E{Cần sessions, DLQ tích hợp, transaction hoặc scheduled/deferred?}
    E -->|Có| SB
    E -->|Không| F{Một work queue đơn giản có đủ?}
    F -->|Có| Q[Azure Queue Storage]
    F -->|Không| SB
~~~

Đây là hướng chọn ban đầu, không thay thế đánh giá tải, chi phí, SLA và khả năng vận hành. Nếu yêu cầu mới xuất hiện như ordering theo aggregate, DLQ tích hợp hoặc fan-out nhiều subscriber, hãy đánh giá lại Service Bus trước khi tự xây nhiều lớp logic trên Storage Queue.

## 14. Bài tập tình huống và câu hỏi tự kiểm tra

**Tình huống A — OCR tài liệu:** API upload PDF vào Blob và gửi job vào Queue Storage. Worker xử lý 2 phút nhưng visibility timeout chỉ 30 giây. Hãy giải thích vì sao message có thể được giao lại, cách gia hạn visibility và cách bảo vệ kết quả bằng idempotency.

**Tình huống B — Message gửi trùng:** Producer nhận timeout sau khi gửi, không biết Azure đã nhận hay chưa và gửi lại cùng job. Hãy dùng job ID ổn định và database unique constraint để tránh tạo hai kết quả OCR.

**Tình huống C — Poison message:** Một JSON sai schema bị nhận lại nhiều lần. Hãy thiết kế ngưỡng dequeue count, poison queue, alert và thao tác replay; giải thích vì sao phải ghi poison thành công trước khi xóa message gốc.

**Tình huống D — Fan-out:** Một sự kiện hợp đồng được gửi cho billing, audit và notification; mỗi nhóm phải nhận độc lập. Hãy chọn Service Bus Topic/Subscription và mô tả vì sao ba consumer cạnh tranh trên một Storage Queue không đáp ứng yêu cầu.

**Tình huống E — Xử lý theo thứ tự đơn hàng:** Mọi message của cùng một order phải được xử lý tuần tự, nhưng các order khác nhau vẫn chạy song song. Hãy đánh giá Service Bus Sessions và so sánh với Queue Storage không có session semantics.

**Tình huống F — Chọn đa cloud:** So sánh Azure Queue Storage với Amazon SQS và Google Cloud Pub/Sub theo delivery, visibility/acknowledgement, retry/dead-letter, ordering và fan-out. Không giả định tên API hoặc giới hạn message giống nhau giữa các provider.

### Câu hỏi tự kiểm tra

1. **Vì sao receive không xóa message ngay?** Vì message được ẩn trong visibility timeout để consumer xử lý; consumer phải xóa sau khi hoàn tất.
2. **Pop receipt dùng để làm gì?** Xác nhận thao tác delete/update thuộc lần nhận hiện tại; receipt cũ có thể không còn hợp lệ.
3. **Queue Storage có bảo đảm exactly-once không?** Không; message có thể được giao lại, nên consumer phải idempotent.
4. **Khi nào cần poison queue?** Khi message thất bại lặp lại hoặc không thể xử lý tự động, cần cách ly và điều tra.
5. **Tại sao không gửi PDF trực tiếp trong queue?** Giới hạn message 64 KiB; Blob phù hợp để lưu payload lớn.
6. **Queue Storage có topic/subscription không?** Không có mô hình native như Service Bus; nhiều consumer trên một queue cạnh tranh nhận message.
7. **Service Bus Sessions giải quyết gì?** Cho phép nhóm message theo session và xử lý tuần tự trong session khi được cấu hình.
8. **Service Bus duplicate detection có thay idempotency không?** Không; nó giảm message gửi trùng trong cửa sổ cấu hình, còn consumer vẫn cần xử lý lặp an toàn.
9. **Azurite có kiểm thử được Service Bus không?** Không; cần namespace Azure Service Bus dành cho integration test.

## 15. Tổng kết

Azure Queue Storage là lựa chọn gọn cho **work queue đơn giản**: producer gửi message nhỏ, consumer nhận với visibility timeout, xử lý và delete bằng message ID cùng pop receipt hiện tại. Vì message có thể được giao lại, ứng dụng cần **idempotency, retry có giới hạn, poison queue và trạng thái job bền vững**. Với payload lớn, lưu nội dung ở Blob và chỉ đưa tham chiếu vào queue.

Khi cần **topic/subscription, sessions, ordering theo nhóm, dead-letter queue tích hợp, scheduled/deferred message hoặc transaction messaging**, hãy đánh giá **Azure Service Bus**. Spring Cloud Azure có starter riêng cho Storage Queue và Service Bus; lựa chọn phải dựa trên semantics nghiệp vụ, không chỉ dựa vào việc cả hai đều có khái niệm queue.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Introduction to Azure Queue Storage](https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction)
- [Microsoft Learn — Get started with Azure Queue Storage using Java](https://learn.microsoft.com/azure/storage/queues/storage-quickstart-queues-java)
- [Microsoft Learn — Queue Storage REST API: Get Messages](https://learn.microsoft.com/rest/api/storageservices/get-messages)
- [Microsoft Learn — Queue Storage REST API: Update Message](https://learn.microsoft.com/rest/api/storageservices/update-message)
- [Microsoft Learn — Azure Service Bus messaging overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Microsoft Learn — Message sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Microsoft Learn — Dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
