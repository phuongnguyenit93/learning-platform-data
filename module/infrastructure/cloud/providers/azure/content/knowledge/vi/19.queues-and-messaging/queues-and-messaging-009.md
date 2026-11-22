# Transaction, scheduling và deferred message

Trong kiến trúc ứng dụng cloud, thông điệp thường không chỉ được gửi rồi nhận ngay. Một đơn hàng có thể cần **hoàn tất bước ghi nhận trước khi phát sự kiện tiếp theo**, một email nhắc thanh toán chỉ nên xuất hiện **sau 30 phút**, hoặc sự kiện “payment confirmed” phải được **đặt sang một bên** cho đến khi thông tin đơn hàng tương ứng đã đến hệ thống. Ba nhu cầu này liên quan đến **transaction**, **scheduled message** và **deferred message** trong **Azure Service Bus**.

Đây là bài học của chương **Hàng đợi và thông điệp** thuộc module **CLOUD_PROVIDERS_AZURE**. Bên cạnh subscription, resource group, Microsoft Entra ID, mạng, compute và lưu trữ của Microsoft Azure, học viên cần hiểu cách bảo đảm tính nhất quán cho những dịch vụ giao tiếp bất đồng bộ, cách hẹn giờ xử lý và cách điều phối sự kiện đến sai thứ tự mà không mất dữ liệu.

**Ba khái niệm không thay thế nhau:**

- **Transaction:** gộp những thao tác **Service Bus được hỗ trợ** vào một đơn vị **commit hoặc rollback**.
- **Scheduling:** đưa thông điệp vào trạng thái **chờ thời điểm đủ điều kiện xuất hiện** để consumer nhận bình thường.
- **Deferral:** consumer đã nhận một thông điệp nhưng chủ động **để dành ngay trong queue/subscription**, chỉ nhận lại bằng **sequence number** khi điều kiện nghiệp vụ đã đủ.

> **Nguyên tắc thiết kế:** Transaction của Service Bus **không phải distributed transaction** tự động bao gồm Azure SQL Database, Cosmos DB, Blob Storage, API HTTP hoặc email. Scheduled message **không phải** một lời hứa xử lý xong đúng giờ. Deferred message **không tự xuất hiện lại** trong luồng nhận bình thường vào một thời điểm đã đặt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt queue, topic/subscription, message, delivery mode và settlement trong Azure Service Bus.
2. Nêu phạm vi atomicity, timeout, điều kiện và giới hạn của Service Bus transaction.
3. Thiết kế tình huống send nhiều message theo transaction, settle message trong transaction và xử lý commit không rõ kết quả.
4. Sử dụng **Azure SDK for Java** để tạo/commit/rollback transaction theo API được hỗ trợ.
5. Schedule message bằng thời gian UTC, lưu sequence number và hủy lịch khi thông điệp chưa được kích hoạt.
6. Phân biệt scheduled message với delay trong ứng dụng, cron job, Service Bus Sessions và deferral.
7. Defer message trong **PeekLock**, lưu sequence number an toàn và receive deferred message để hoàn tất xử lý.
8. Kết hợp các cơ chế vào workflow có idempotency, duplicate detection, TTL, dead-letter queue (DLQ) và retry hợp lý.
9. Thiết lập namespace/queue lab, quản lý identity và quyền theo least privilege.
10. Đọc logs/metrics, chẩn đoán lỗi lock, transaction timeout, message không thấy và backlog.
11. Đánh giá trade-off hiệu năng, throughput, phí vận hành và độ tin cậy của một hệ thống thông điệp.

## 2. Kiến trúc minh họa: hệ thống Orders trên Azure

Giả sử có ba ứng dụng:

- **Orders API:** ghi nhận yêu cầu mua hàng.
- **Payment Worker:** xử lý kết quả thanh toán, cần biết đơn hàng tương ứng.
- **Reminder Worker:** gửi lời nhắc khi khách hàng chưa thanh toán sau một khoảng thời gian.

Một thiết kế đơn giản:

~~~mermaid
flowchart LR
    USER["Khách hàng"] --> API["Orders API<br/>App Service / AKS"]
    API -->|"OrderCreated"| SB["Azure Service Bus<br/>Namespace"]
    SB --> QUEUE1["orders-events"]
    SB --> QUEUE2["payment-events"]
    SB --> QUEUE3["payment-reminders"]
    QUEUE1 --> ORDER["Order Worker"]
    QUEUE2 --> PAY["Payment Worker"]
    QUEUE3 --> REM["Reminder Worker"]
    ORDER --> DB["Azure SQL / Cosmos DB"]
    PAY --> DB
    REM --> DB
    API -. "Entra ID / managed identity" .-> SB
~~~

Sơ đồ chỉ mô tả các thành phần. Thực tế, mỗi queue/topic/subscription là một **messaging entity** dưới namespace. Producer và consumer có thể được cấp danh tính/role khác nhau.

### 2.1. Một số thuật ngữ bắt buộc

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Namespace** | Ranh giới quản lý các entity Azure Service Bus và mạng/identity/tier | sb-orders-lab |
| **Queue** | Nơi nhiều consumer có thể cạnh tranh xử lý từng message | orders-events |
| **Topic/subscription** | Publish/subscribe; mỗi subscription nhận bản sao phù hợp với rule/filter | orders-topic / billing |
| **Producer/Sender** | Ứng dụng gửi message | Orders API |
| **Consumer/Receiver** | Ứng dụng đọc và settle message | Payment Worker |
| **PeekLock** | Nhận nhưng chưa xóa message; phải complete/abandon/defer/dead-letter | Xử lý có kiểm soát |
| **ReceiveAndDelete** | Message bị loại khỏi entity khi nhận theo cơ chế dịch vụ | Workload chấp nhận rủi ro mất xử lý |
| **Lock token** | Đại diện một lần lock để settle message | Quyền thao tác trên bản message đã nhận |
| **Sequence number** | Số định danh do broker gán trong entity | Tìm lại deferred/cancel scheduled |
| **MessageId** | Định danh do producer cung cấp; hữu ích cho tương quan/dedup | order-481-payment |
| **SessionId** | Nhóm messages cần điều phối theo session | order-481 |
| **TTL** | Thời gian sống của message theo entity/message | 24 giờ |
| **DLQ** | Subqueue dành cho message không thể xử lý/được chủ động chuyển | orders-events/$DeadLetterQueue |

Không nhầm **MessageId**, **SequenceNumber**, **SessionId** và **LockToken**. Chúng được dùng vào những mục đích khác nhau và không thể thay nhau một cách tùy tiện.

### 2.2. PeekLock là nền tảng cho settlement

~~~mermaid
flowchart TD
    A["Queue: Active message"] --> B["Receiver: PeekLock"]
    B --> C{"Xử lý thế nào?"}
    C -->|"Thành công"| D["Complete → xóa khỏi queue"]
    C -->|"Lỗi tạm"| E["Abandon → có thể được nhận lại"]
    C -->|"Lỗi không phục hồi"| F["Dead-letter → DLQ"]
    C -->|"Chưa đủ dữ kiện"| G["Defer → chỉ nhận lại bằng sequence number"]
~~~

**ReceiveAndDelete** không phù hợp với kịch bản cần settlement transaction hoặc deferral sau khi nhận: thông điệp đã bị loại khỏi hàng đợi ngay khi broker chuyển giao theo chế độ này.

## 3. Bảng so sánh: transaction, scheduling và deferral

| Tiêu chí | Transaction | Scheduled message | Deferred message |
|---|---|---|---|
| Câu hỏi giải quyết | Nhiều thao tác broker có cùng thành công/thất bại? | Khi nào message được **đưa vào luồng nhận thông thường**? | Khi nào consumer đã nhận một message sẽ tự quay lại xử lý? |
| Bên khởi xướng | Sender/receiver tạo transaction context | Sender schedule message | Receiver trong PeekLock defer message |
| Đối tượng | Những thao tác Service Bus hỗ trợ | Message được hẹn giờ trước khi active | Message đã có trong queue/subscription |
| Cách truy cập tiếp | Commit/rollback transaction | Receiver bình thường sau thời điểm kích hoạt | Receiver phải biết **sequence number** |
| Dấu hiệu cần nhớ | Transaction context và outcome | Sequence number của message đang scheduled | Sequence number của message đã defer |
| Có hẹn giờ tích hợp? | Không | **Có** | **Không** |
| Có bảo đảm atomic với database? | Không | Không | Không |
| Rủi ro nổi bật | Timeout/unknown commit/retry sai | Cancel sát giờ bị race; delivery trễ | Mất sequence number; message bị bỏ quên |
| Tình huống | Send hai sự kiện cùng thành công hoặc rollback | Gửi nhắc hạn thanh toán sau 30 phút | Chờ sự kiện OrderCreated trước khi xử lý PaymentConfirmed |

Bài tập suy luận: nếu yêu cầu là “PaymentConfirmed đã đến nhưng chưa có OrderCreated”, **defer** có thể phù hợp. Nếu yêu cầu là “sau 15 phút mới gửi nhắc”, dùng **schedule**. Nếu yêu cầu là “cả hai message được gửi hoặc không message nào được gửi”, dùng **transaction** trong phạm vi broker hỗ trợ.

## 4. Chuẩn bị môi trường và chọn tier

### 4.1. Service Bus Basic, Standard và Premium

Azure Service Bus có các tier khác nhau. **Standard** bổ sung topics/subscriptions, sessions, transactions và duplicate detection so với Basic. **Premium** cung cấp tài nguyên messaging được phân tách hơn, hỗ trợ những khả năng mạng và hiệu năng nâng cao như Private Link trong phạm vi cấu hình cho phép.

Với bài lab có **transaction**, nên dùng **Standard hoặc Premium**, không giả định mọi chức năng nâng cao tồn tại trên Basic. Trước triển khai thật, xác nhận lại các tính năng scheduling/deferral, queue options và giới hạn theo tier/version API.

| Tiêu chí | Basic | Standard | Premium |
|---|---|---|---|
| Queue cơ bản | Có | Có | Có |
| Topic/subscription | Không | Có | Có |
| Transactions | Không dùng Basic cho lab này | Có | Có |
| Sessions/duplicate detection | Có giới hạn theo tier | Có | Có |
| Năng lực riêng, quy mô/SLA | Ít tính năng | Shared capacity | Messaging units chuyên dụng |
| Private Link/VNet capabilities | Có giới hạn | Có giới hạn | Các khả năng nâng cao theo tính năng |
| Chi phí | Theo tier/usage | Theo operations/usage | Theo messaging units/usage và các thành phần liên quan |

### 4.2. Điều kiện thực hành

- Subscription và resource group được phép sử dụng.
- Namespace Service Bus Standard/Premium trong region phù hợp.
- Ba queues minh họa hoặc một queue riêng cho từng thử nghiệm.
- Java 17+ và Maven nếu thực hành Java SDK; chọn phiên bản SDK được hỗ trợ.
- Azure CLI, Azure Cloud Shell hoặc môi trường có kết nối với namespace.
- Microsoft Entra identity có quyền phù hợp: **Azure Service Bus Data Sender** hoặc **Data Receiver**, chỉ dùng **Data Owner** khi thực sự cần và được duyệt.
- Network/DNS/TLS và cổng AMQP/TCP hoặc WebSockets theo cấu hình môi trường.
- Chính sách an toàn cho test: không dùng thông điệp khách hàng thật; có quota/TTL, DLQ và kế hoạch dọn dẹp.

Các lệnh trong bài **chỉ là hướng dẫn**, không tạo tài nguyên trên subscription của bạn trong quá trình soạn bài.

### 4.3. Tạo namespace và queue lab bằng Azure CLI

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-servicebus-messaging-lab"
REGION="southeastasia"
NS="<globally-unique-servicebus-namespace>"

az group create \
  --name "$RG" \
  --location "$REGION"

az servicebus namespace create \
  --resource-group "$RG" \
  --name "$NS" \
  --location "$REGION" \
  --sku Standard
~~~

Tạo các queue riêng, để thao tác complete/defer/schedule không trộn với message khác:

~~~bash
az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "tx-lab"

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "scheduled-lab"

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "deferred-lab"
~~~

Kiểm tra:

~~~bash
az servicebus namespace show \
  --resource-group "$RG" \
  --name "$NS" \
  --query "{name:name,location:location,sku:sku.name,status:status}" \
  --output json

az servicebus queue list \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --output table
~~~

Nếu namespace/queue đã tồn tại, **không tự tạo hoặc thay đổi production entity**. Các tùy chọn nâng cao như duplicate detection, sessions, DLQ, auto-forwarding và partitioning cần được xác định **trước** khi dùng một entity thật, vì một số thiết lập có hạn chế thay đổi về sau.

## 5. Danh tính Java và cấu hình SDK

Đối với ứng dụng mới, ưu tiên **Microsoft Entra ID / managed identity** thay vì nhúng Service Bus connection string vào repository hoặc container image.

### 5.1. Maven dependencies

Ví dụ cho project Java; hãy đồng bộ version qua BOM hoặc dependency management của dự án:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-servicebus</artifactId>
    <version>7.18.0</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>1.18.7</version>
  </dependency>
</dependencies>
~~~

**Lưu ý:** hai phiên bản SDK trong đoạn Maven là giá trị ví dụ đã phát hành, không phải cam kết đây luôn là cặp phiên bản mới nhất. Trong dự án thực, dùng bản hiện hành tương thích hoặc Azure SDK BOM/dependency management được duyệt, đồng thời khóa version để build tái lập. Đoạn trên là phần dependencies cần đưa vào POM của dự án, không phải một POM đầy đủ.

### 5.2. Tạo sender và receiver với DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

String fqdn = System.getenv("SERVICEBUS_FQDN");
// Ví dụ: sb-orders-lab.servicebus.windows.net
String queue = "tx-lab";

ServiceBusSenderClient sender = new ServiceBusClientBuilder()
        .credential(fqdn, credential)
        .sender()
        .queueName(queue)
        .buildClient();

ServiceBusReceiverClient receiver = new ServiceBusClientBuilder()
        .credential(fqdn, credential)
        .receiver()
        .queueName(queue)
        .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
        .buildClient();

// Sau khi dùng xong: sender.close(); receiver.close();
~~~

Đây là **đoạn cấu hình trong một phương thức Java**, không phải class độc lập. Trong project thực, validate biến môi trường trước khi tạo client và quản lý vòng đời client. Các SDK clients thường nên được tái sử dụng, tránh tạo lại kết nối cho từng message.

**FQDN không có tiền tố https://**; dùng dạng **your-namespace.servicebus.windows.net**.

### 5.3. Phân quyền riêng cho sender và receiver

- Producer: **Azure Service Bus Data Sender** trên queue/namespace phù hợp.
- Consumer: **Azure Service Bus Data Receiver**.
- Người tạo queue/namespace: quyền Azure management plane theo scope.
- Ứng dụng cần cả send/receive: cấp hai quyền thấp nhất phù hợp, tránh Data Owner nếu không cần.

Role assignment có thể cần thời gian propagation. Phải phân biệt lỗi **401/403 authorization** với lỗi DNS, TLS hoặc message settlement.

### 5.4. Network

Azure Service Bus SDK thường kết nối qua **AMQP over TLS**. Nếu môi trường chặn đường AMQP trực tiếp, có thể xem cấu hình **AMQP over WebSockets** mà SDK hỗ trợ theo hướng dẫn tương ứng.

Khi namespace dùng **Private Endpoint**, phải có route và private DNS chính xác từ App Service/AKS/VM đến namespace. **Không tắt firewall hay mở public access tùy tiện** để làm lab chạy nhanh hơn.

## 6. Transaction: phạm vi atomicity

Một Service Bus transaction gom một hoặc nhiều thao tác **được broker hỗ trợ** vào một nhóm: hoặc commit khiến kết quả có hiệu lực, hoặc rollback hủy hiệu ứng trong phạm vi transaction.

### 6.1. Các thao tác được hỗ trợ

Các thao tác messaging được tài liệu Service Bus liệt kê cho transaction bao gồm:

- **Send** message.
- **Complete** message đã nhận.
- **Abandon** message đã nhận.
- **Dead-letter** message đã nhận.
- **Defer** message đã nhận.
- **Renew lock** trong trường hợp API hỗ trợ.

Một số API sender của Azure SDK for Java cũng cung cấp **scheduleMessage(..., transactionContext)** hoặc **scheduleMessages(..., transactionContext)**. Khi dùng, kiểm tra giới hạn và hành vi theo SDK/broker hiện hành, không suy rằng tất cả API quản trị entity đều nằm trong transaction.

**Receive không tự được thực hiện trong transaction.** Mô hình thường gặp:

1. Consumer nhận message bằng **PeekLock**.
2. Xử lý phần logic có thể thực hiện ngoài transaction.
3. Tạo transaction.
4. Gửi event tiếp theo/settle message đã nhận bằng transaction context theo mô hình hỗ trợ.
5. Commit hoặc rollback.

### 6.2. Ví dụ atomic send

~~~mermaid
flowchart TD
    S["Bắt đầu transaction"] --> A["Send Event A"]
    A --> B["Send Event B"]
    B --> D{"Commit?"}
    D -->|Có| C["Cả A và B có hiệu lực"]
    D -->|Rollback| R["Không áp dụng A và B trong transaction"]
~~~

Ý nghĩa: nếu hai message phải xuất hiện cùng nhau trong một entity và một lần send thất bại trước commit, ứng dụng có thể rollback cả nhóm.

Không gộp **hàng nghìn message hoặc xử lý nghiệp vụ kéo dài** vào một transaction chỉ vì nghe có vẻ an toàn hơn. Transaction có timeout, quota, lock và throughput giới hạn.

### 6.3. Transaction timeout

Service Bus transaction có **timeout khoảng 2 phút**, tính từ thao tác đầu tiên trong transaction theo tài liệu dịch vụ. Transaction nên được giữ ngắn; không gọi database/query HTTP dài hoặc chờ người dùng nhập dữ liệu khi transaction còn mở.

Một điểm dễ bỏ sót: SDK **không tự retry các thao tác trong transaction theo cách retry thông thường**, vì retry có thể dẫn đến những vấn đề về deadlock/settlement hoặc kết quả không chắc chắn. Khi lỗi, cần đánh giá outcome và dùng idempotency thay vì gọi lại mù quáng.

### 6.4. Cross-entity transactions

Service Bus hỗ trợ những mẫu transaction liên quan **nhiều messaging entity trong cùng namespace** theo điều kiện và cấu hình SDK, trong đó có mô hình **send via / transfer entity** để phối hợp settlement của input với gửi output.

Tuy nhiên:

- Không tự giả định gửi từ queue của namespace A sang queue của namespace B là một transaction.
- Cần cấu hình tính năng **cross-entity transactions** nếu SDK và mẫu thiết kế yêu cầu; ví dụ Java có builder option tương ứng.
- Phải kiểm tra cùng namespace, entity path, transfer route và cách quyền được cấp.
- Cần xét sự khác biệt khi chuyển message giữa queue/topic/subscription.
- Tránh khẳng định mọi loại thao tác/topic filter luôn nằm trong cùng atomicity nếu chưa xem tài liệu cụ thể.

Bài học cung cấp ví dụ transaction **trong một queue** ở phần tiếp theo để minh họa atomicity rõ ràng; mẫu chuyển queue theo transaction phải được thiết kế và thử riêng.

## 7. Thực hành Java: gửi hai message trong một transaction

Ví dụ đầy đủ dưới đây chạy với Java SDK có API **ServiceBusSenderClient.createTransaction**, **sendMessage(message, transaction)**, **commitTransaction** và **rollbackTransaction**.

Dùng queue **tx-lab**, credentials được cấp **Data Sender** và biến môi trường **SERVICEBUS_FQDN**.

### 7.1. Class TransactionSendDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusTransactionContext;

import java.util.UUID;

public final class TransactionSendDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        if (fqdn == null || fqdn.isBlank()) {
            throw new IllegalArgumentException("Missing SERVICEBUS_FQDN");
        }

        try (ServiceBusSenderClient sender = new ServiceBusClientBuilder()
                .credential(fqdn,
                        new DefaultAzureCredentialBuilder().build())
                .sender()
                .queueName("tx-lab")
                .buildClient()) {

            String batchId = UUID.randomUUID().toString();
            ServiceBusMessage first =
                    new ServiceBusMessage("reserve-stock")
                    .setMessageId(batchId + "-stock");

            ServiceBusMessage second =
                    new ServiceBusMessage("record-audit")
                    .setMessageId(batchId + "-audit");

            ServiceBusTransactionContext transaction =
                    sender.createTransaction();

            try {
                sender.sendMessage(first, transaction);
                sender.sendMessage(second, transaction);
                sender.commitTransaction(transaction);
                System.out.println("Committed batchId=" + batchId);
            } catch (RuntimeException error) {
                try {
                    sender.rollbackTransaction(transaction);
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

**Kết quả kỳ vọng trong lab:** nếu transaction commit thành công, hai message được ghi trong **tx-lab**. Nếu rollback hoàn tất trước commit, không có hai send đó được áp dụng.

### 7.2. Những giới hạn của ví dụ

- Đây chỉ là **atomicity của send đến broker**, không phải “đã trừ hàng tồn kho” trong database.
- **BatchId** giúp tra cứu và nhận diện. **MessageId** được gán rõ để hỗ trợ correlation/dedup khi cấu hình tương ứng.
- Nếu **commitTransaction** bị timeout hoặc kết nối mất đúng lúc phản hồi, ứng dụng có thể **không biết commit đã thành công hay chưa**. Gọi rollback sau lỗi có thể không đảo được một commit đã hoàn tất.
- Vì thế **không tự retry lại lệnh với MessageId hoàn toàn mới** khi outcome không rõ. Tìm trạng thái nghiệp vụ, dùng duplicate detection/outbox và idempotency.
- Không gọi một transaction mới rồi mong rollback của transaction cũ ảnh hưởng tới nó.

### 7.3. Mô hình kiểm thử

1. Trong lab, chạy demo khi mạng hoạt động và đọc message từ **tx-lab**.
2. Dùng một lỗi có kiểm soát **trước commit** để xác minh rollback.
3. Thử producer gặp lỗi mạng nhưng không giả định outcome từ exception.
4. Ghi **MessageId**, **batchId** và thời gian thực hiện để đối chiếu.
5. Kiểm tra số message và các logs, tránh xóa message production để thử.
6. Ghi nhận giới hạn thời gian transaction và hành vi retry của SDK.

## 8. Transaction với settlement của message đã nhận

Khi consumer đã nhận message bằng **PeekLock**, việc **Complete** có thể được đưa vào transaction theo API hỗ trợ. Trong Azure SDK Java, receiver dùng **CompleteOptions.setTransactionContext(...)**.

### 8.1. Mẫu code minh họa

~~~java
import com.azure.messaging.servicebus.*;
import com.azure.messaging.servicebus.models.*;
import com.azure.identity.DefaultAzureCredentialBuilder;
import java.time.Duration;
import java.util.Iterator;

public final class TransactionCompleteDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .receiver()
                   .queueName("tx-lab")
                   .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                   .buildClient()) {

            Iterator<ServiceBusReceivedMessage> it =
                receiver.receiveMessages(
                    1, Duration.ofSeconds(20)).iterator();

            if (!it.hasNext()) {
                System.out.println("No message received");
                return;
            }

            ServiceBusReceivedMessage message = it.next();
            // Chỉ minh họa settlement, chưa thực hiện xử lý nghiệp vụ.
            ServiceBusTransactionContext tx =
                    receiver.createTransaction();

            try {
                receiver.complete(
                    message,
                    new CompleteOptions().setTransactionContext(tx));
                receiver.commitTransaction(tx);
                System.out.println(
                    "Completed MessageId=" + message.getMessageId());
            } catch (RuntimeException error) {
                try {
                    receiver.rollbackTransaction(tx);
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Code chỉ được dùng với **message thử nghiệm**. Không đánh dấu complete một message production chỉ để thử API mà chưa thực sự xử lý nội dung.

### 8.2. Vì sao receive diễn ra trước transaction?

Service Bus giả định ứng dụng đã nhận và lock message trước khi mở transaction để settle. Transaction không kéo dài suốt thời gian xử lý nghiệp vụ vài phút; nó bao phủ các thao tác broker cuối cùng.

Ví dụ “nhận từ queue A, gửi sang queue B, complete message A” có thể được thực hiện atomically **trong phạm vi Service Bus hỗ trợ**, nhưng phải cấu hình cross-entity transactions đúng. Không tự thay client trong ví dụ một queue thành hai queue rồi cho rằng vẫn atomic.

### 8.3. Lock mất trước khi commit

Một message trong PeekLock có thời hạn lock. Nếu công việc xử lý kéo dài, lock có thể hết hạn và một consumer khác nhận lại message. Khi đó complete/defer có thể trả **MessageLockLost** hoặc lỗi settlement tương ứng.

Để tránh:

- Không tạo transaction khi còn một tác vụ HTTP/SQL rất dài chưa xử lý xong.
- Dùng cơ chế auto-lock renewal hoặc renew lock theo SDK khi cần và trong giới hạn.
- Đặt max delivery count, timeout và retry phù hợp.
- Xử lý idempotent vì lock renew vẫn có thể thất bại.
- Nếu việc xử lý rất lâu, cân nhắc lưu trạng thái bên ngoài, complete rồi điều phối bước khác bằng mô hình phù hợp.

## 9. Transaction không phải distributed transaction với database

Đây là một sai lầm kiến trúc phổ biến.

~~~mermaid
flowchart LR
    A["Orders API"] --> DB["Azure SQL: INSERT order"]
    A --> SB["Service Bus: SEND OrderCreated"]
    X["Một lỗi xảy ra giữa hai thao tác"] -. "Không tự rollback cả DB và broker" .-> DB
    X -. "Không tự rollback cả DB và broker" .-> SB
~~~

Nếu ứng dụng ghi SQL thành công nhưng gửi Service Bus thất bại, transaction ở SQL **không tự rollback** message broker; nếu gửi message thành công rồi SQL rollback, sự kiện có thể mô tả một đơn hàng không tồn tại.

### 9.1. Transactional outbox

Một cách tiếp cận phổ biến:

1. Trong **một transaction của database**, ghi **Orders** và một record vào **Outbox**.
2. Commit database.
3. Một background worker đọc Outbox.
4. Worker gửi message đến Service Bus bằng MessageId ổn định.
5. Sau khi send được xác nhận, đánh dấu Outbox đã gửi.
6. Consumer xử lý idempotent và lưu dấu kết quả.

~~~mermaid
flowchart TD
    API["Orders API"] --> TX["DB transaction"]
    TX --> O["Orders table"]
    TX --> OUT["Outbox table"]
    OUT --> RELAY["Outbox publisher"]
    RELAY --> SB["Service Bus"]
    SB --> WORKER["Consumer idempotent"]
~~~

Outbox tránh khoảng trống “ghi DB xong nhưng chưa ghi ý định phát message”. Tuy nhiên publisher vẫn có thể gửi trùng nếu crash giữa **send success** và **mark sent**. Vì thế cần duplicate detection/idempotency ở consumer; không coi outbox là exactly-once tuyệt đối cho tác dụng phụ bên ngoài.

### 9.2. Saga / compensating action

Đối với luồng gồm Orders, Payments, Inventory và Shipping, một transaction Service Bus ngắn không thể bao hết các API và database. Cần workflow có trạng thái và **saga/compensation** nếu một bước thất bại sau khi những bước trước đã commit.

Đừng giữ transaction Service Bus mở trong lúc chờ ngân hàng trả kết quả; vượt timeout là gần như chắc chắn.

## 10. Scheduling: gửi message để broker kích hoạt trong tương lai

**Scheduled message** là thông điệp được gửi trước nhưng được Service Bus giữ ở trạng thái **scheduled** cho đến thời điểm **scheduled enqueue time**.

~~~mermaid
flowchart LR
    P["Producer"] -->|"Schedule: 15:30 UTC"| Q["Service Bus scheduled store"]
    Q -->|"Đến thời điểm kích hoạt"| A["Active queue/subscription"]
    A -->|"Receive bình thường"| C["Consumer"]
~~~

Các ứng dụng:

- Gửi email nhắc khi đơn hàng chưa thanh toán sau 30 phút.
- Gửi một thông điệp đánh giá lại trạng thái giao dịch sau 10 phút.
- Khởi tạo một bước bù trừ khi timeout workflow.
- Đặt lịch một thông điệp audit/reconciliation vào ngày nghiệp vụ thích hợp.

### 10.1. Scheduled time là mốc kích hoạt, không phải deadline xử lý xong

Nếu schedule message cho 15:30 UTC:

- Broker dự kiến đưa message vào trạng thái có thể nhận **từ mốc đó** theo cơ chế dịch vụ.
- Consumer có thể nhận **sau** 15:30 vì backlog, capacity, lỗi mạng, throttling hoặc consumer offline.
- Hệ thống **không bảo đảm** email đã được gửi lúc đúng 15:30.
- Scheduled message không tự trở thành một **cron schedule lặp lại**; mỗi lần hẹn giờ là một message.

Nếu cần định kỳ mỗi ngày/tuần, dùng orchestrator/scheduler tạo các lần gửi phù hợp hoặc dịch vụ có hỗ trợ lịch lặp.

### 10.2. Hai cách schedule

- Gửi message bình thường nhưng đặt **ScheduledEnqueueTimeUtc**/thuộc tính tương ứng của SDK.
- Gọi API **scheduleMessage**/**scheduleMessages** với thời gian mong muốn.

Với Azure SDK Java, phương thức **scheduleMessage** trả về **sequence number của message đang scheduled**, dùng để cancel khi chưa kích hoạt. Cách đặt thuộc tính trên message cần đối chiếu cơ chế lấy sequence number và cancellation nếu workflow có thể bị hủy.

### 10.3. Giờ và timezone

Service Bus dùng timestamp UTC/offset trong giao thức. Với Java, ưu tiên:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime when = OffsetDateTime.now(ZoneOffset.UTC)
    .plusMinutes(30);
~~~

Nếu yêu cầu “nhắc lúc 09:00 giờ Việt Nam”, hãy chuyển thời gian theo timezone đúng (ví dụ **Asia/Ho_Chi_Minh**) sang UTC trước khi schedule. Đừng tự cộng trừ số giờ cố định nếu một ứng dụng còn phục vụ nhiều quốc gia có daylight saving time.

### 10.4. TTL và scheduled message

Với scheduled message, **TTL countdown cho thông điệp active** gắn với thời điểm message được enqueue/activate theo cách dịch vụ xác định, không đơn giản là thời điểm producer đặt lịch gửi.

Ví dụ: schedule sau 5 phút, TTL 10 phút thì message có thể hết hạn khoảng 15 phút kể từ lúc producer gửi yêu cầu, nếu chưa được xử lý. Đây chỉ là ví dụ khái niệm; kiểm tra TTL của queue, message và cách hệ thống xử lý expiry/DLQ.

## 11. Thực hành Java: schedule và cancel message

Với queue **scheduled-lab** và sender đã được cấp quyền:

### 11.1. Class ScheduleDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

public final class ScheduleDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        String orderId = "order-lab-" + UUID.randomUUID();

        try (ServiceBusSenderClient sender =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .sender()
                   .queueName("scheduled-lab")
                   .buildClient()) {

            ServiceBusMessage reminder =
                    new ServiceBusMessage(
                        "{\"type\":\"PaymentReminder\",\"orderId\":\""
                          + orderId + "\"}")
                    .setMessageId("reminder-" + orderId);

            reminder.getApplicationProperties().put(
                    "orderId", orderId);

            OffsetDateTime when =
                    OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(5);

            long scheduledSequence =
                    sender.scheduleMessage(reminder, when);

            System.out.printf(
                "Scheduled order=%s, sequence=%d, when=%s%n",
                orderId, scheduledSequence, when);

            // Trong production: LƯU scheduledSequence bền vững
            // cùng namespace, entity, orderId và trạng thái lịch.
        }
    }
}
~~~

Kết quả kỳ vọng: message ở trạng thái scheduled, chưa xuất hiện trong **receiveMessages** bình thường trước mốc kích hoạt. Sau mốc này, consumer có thể nhận như message active khác.

### 11.2. Hủy lịch

Giả sử **scheduledSequence** được lưu từ bước trước và message vẫn chưa kích hoạt:

~~~java
// sender đang kết nối đúng namespace và queue đã schedule.
long scheduledSequence = Long.parseLong(
        System.getenv("SCHEDULED_SEQUENCE"));

sender.cancelScheduledMessage(scheduledSequence);
~~~

Đây là **đoạn code chèn vào phương thức có sender**, không phải class hoàn chỉnh. Biến môi trường **SCHEDULED_SEQUENCE** chỉ dành cho lab; production nên lưu sequence number ở database/workflow store cùng entity và business key.

**Sau thời điểm kích hoạt, không thể dùng sequence number scheduled cũ để hủy message active một cách đáng tin cậy.** Service Bus cấp một sequence number mới khi scheduled message chuyển sang active.

### 11.3. Race condition giữa cancel và activation

Nếu ứng dụng gọi cancel sát thời điểm kích hoạt, hai thao tác có thể chạy đồng thời. Theo đặc tính dịch vụ, không có đảm bảo rằng cancel đang diễn ra sẽ đảo ngược một activation đã bắt đầu.

Vì vậy, workflow không nên chỉ dựa vào **cancelScheduledMessage** để bảo đảm “không gửi email nhắc”:

1. Khi khách hàng đã trả tiền, đánh dấu order status = PAID trong database.
2. Cố hủy scheduled message nếu nó còn pending.
3. Khi reminder consumer nhận message, đọc lại trạng thái order.
4. Nếu PAID, **complete message mà không gửi email**.
5. Nếu UNPAID và còn trong thời hạn nghiệp vụ, thực hiện nhắc bằng cơ chế idempotent.
6. Ghi audit cho quyết định gửi/không gửi.

**Business state là nguồn sự thật cuối cùng**; cancel chỉ giúp tránh xử lý không cần thiết.

### 11.4. Sequence number không phải MessageId

| Giá trị | Ai tạo? | Dùng để làm gì? |
|---|---|---|
| MessageId | Producer | Correlation, duplicate detection theo entity/config |
| Scheduled sequence | Service Bus khi schedule | Cancel message trước activation |
| Active sequence | Service Bus khi message active | Định danh message khi đã enqueue |
| SessionId | Producer | Nhóm workflow/session |
| Lock token | Broker/receiver | Settle một lần nhận PeekLock |

Đừng dùng MessageId để gọi **cancelScheduledMessage**, hoặc dùng sequence của một message đã active như một lịch đang chờ.

## 12. Deferral: cố ý gác message đã nhận sang một bên

**Deferred message** xuất phát từ tình huống **consumer đã nhận được message**, nhưng biết rằng có một phụ thuộc chưa sẵn sàng và muốn xử lý nó sau.

Ví dụ:

1. Worker nhận **PaymentConfirmed(orderId=481)**.
2. Chưa có record OrderCreated/order 481 trong hệ thống đích.
3. Worker **defer** PaymentConfirmed.
4. Worker lưu **sequence number** vào nơi bền vững theo orderId.
5. Sau khi OrderCreated xuất hiện, worker lấy lại deferred message bằng sequence number.
6. Xử lý và complete.

~~~mermaid
flowchart TD
    A["PaymentConfirmed đến queue"] --> B["Receiver nhận PeekLock"]
    B --> C{"Đã có OrderCreated?"}
    C -->|Có| D["Xử lý + Complete"]
    C -->|Chưa| E["Defer + lưu sequence number"]
    E --> F["Nhận tín hiệu OrderCreated"]
    F --> G["receiveDeferredMessage(sequence)"]
    G --> H["Xử lý + Complete"]
~~~

### 12.1. Deferred nằm ở đâu?

Deferred message **vẫn thuộc main queue hoặc subscription**, không chuyển vào DLQ riêng. Nó bị loại khỏi luồng **receive bình thường**, nhưng có thể được tìm bằng **peek/browse** theo khả năng dịch vụ.

Để nhận lại, cần dùng API theo **sequence number**. Không có cơ chế tự “un-defer sau 10 phút” chỉ vì đã hết thời gian chờ.

### 12.2. Vì sao không dùng Abandon?

**Abandon** trả message về luồng có thể được nhận lại, tăng delivery count theo quy tắc dịch vụ. Nếu phụ thuộc vẫn chưa sẵn sàng, worker có thể nhận và abandon lặp lại, dẫn đến:

- Hot loop/traffic không cần thiết.
- MaxDeliveryCount bị vượt và message vào DLQ.
- Tăng phí operations/throttling.
- Một message làm cản xử lý những message khác.

**Defer** phù hợp khi có một điều kiện cụ thể khiến message chưa thể xử lý nhưng cần lưu giữ có chủ đích.

### 12.3. Khi không nên dùng defer

Nếu **database chung của mọi message bị ngừng hoạt động**, không nên defer từng message và chất đầy danh sách sequence numbers. Thường nên **tạm dừng nhận**, dùng retry có backoff/circuit breaker và đánh giá health của dependency.

Nếu cần xử lý **sau 10 phút bất kể message đã được nhận hay chưa**, scheduling hoặc hệ thống retry có delay phù hợp hơn. Deferred message cần **hệ thống đánh thức có lưu state**, không phải built-in timer.

## 13. Thực hành Java: defer và nhận lại bằng sequence number

Ví dụ dùng **deferred-lab** với receiver ở chế độ PeekLock. Để dễ thử, dùng hai chế độ chạy:

- Không đặt **DEFERRED_SEQUENCE**: nhận một message và defer.
- Đặt **DEFERRED_SEQUENCE**: nhận lại message đã defer rồi complete sau khi kiểm tra.

### 13.1. Class DeferralDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceivedMessage;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;

import java.time.Duration;
import java.util.Iterator;

public final class DeferralDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        String savedSequence = System.getenv("DEFERRED_SEQUENCE");

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .receiver()
                   .queueName("deferred-lab")
                   .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                   .buildClient()) {

            if (savedSequence == null || savedSequence.isBlank()) {
                Iterator<ServiceBusReceivedMessage> it =
                    receiver.receiveMessages(
                        1, Duration.ofSeconds(20)).iterator();

                if (!it.hasNext()) {
                    System.out.println("No active message available");
                    return;
                }

                ServiceBusReceivedMessage message = it.next();
                long sequence = message.getSequenceNumber();

                // DEMO: giả định chưa có dữ kiện để xử lý.
                receiver.defer(message);
                System.out.println(
                    "Deferred sequenceNumber=" + sequence);
                // Production: lưu sequence + entity + business key.
            } else {
                long sequence = Long.parseLong(savedSequence);
                ServiceBusReceivedMessage message =
                        receiver.receiveDeferredMessage(sequence);

                if (message == null) {
                    throw new IllegalStateException(
                        "Deferred message not found: " + sequence);
                }

                // Trong hệ thống thật: kiểm tra prerequisite,
                // thực hiện business operation idempotent.
                System.out.println(
                    "Received deferred MessageId="
                        + message.getMessageId());
                receiver.complete(message);
            }
        }
    }
}
~~~

**Trước khi chạy**, hãy gửi một test message vào **deferred-lab** và xác nhận không có consumer khác lấy mất. Một lần chạy đầu tiên in ra sequence number; lần sau dùng giá trị đó làm **DEFERRED_SEQUENCE** trong môi trường thử nghiệm.

### 13.2. Gửi message thử nghiệm

~~~java
// Đoạn chèn vào phương thức đã có sender của deferred-lab.
ServiceBusMessage message =
    new ServiceBusMessage(
        "{\"type\":\"PaymentConfirmed\",\"orderId\":\"lab-481\"}")
    .setMessageId("payment-lab-481");

sender.sendMessage(message);
~~~

Đây là **đoạn code**, không phải class đầy đủ. Không gửi sự kiện thanh toán giả vào queue production.

### 13.3. Vì sao phải lưu sequence number bền vững?

Nếu consumer defer xong rồi crash, sequence number chỉ còn trong bộ nhớ/log cục bộ có thể bị mất. Message vẫn ở queue nhưng workflow không biết phải gọi **receiveDeferredMessage** với số nào.

Nên lưu record trong database/workflow store:

~~~text
DeferredWork {
    namespace: "sb-orders-lab"
    entity: "deferred-lab"
    messageId: "payment-lab-481"
    orderId: "lab-481"
    sequenceNumber: 34751
    state: "WAITING_FOR_ORDER"
    createdAtUtc: "..."
    nextCheckAtUtc: "..."
}
~~~

Giá trị sequence number ở trên chỉ là **minh họa**, không phải giá trị của một queue thật.

Cần kiểm soát tính nhất quán giữa hai thao tác **lưu record và defer**: chúng thuộc hai hệ thống, không tự có một transaction chung. Nếu crash giữa hai bước, nên có **reconciliation** bằng message browsing, correlation ID, retry an toàn hoặc một workflow có trạng thái để không bỏ quên message.

### 13.4. Deferred message đã hết TTL

Một chi tiết quan trọng: **deferred message không nhất thiết được tự động đưa vào DLQ đúng lúc TTL hết** như message active thông thường. Kiểm tra expiration có thể xảy ra khi client cố nhận lại theo sequence number, rồi dịch vụ xử lý message đã hết hạn theo cấu hình entity/DLQ.

Vì vậy:

- Không giữ deferred vô thời hạn.
- Thiết lập timeout nghiệp vụ trong workflow store.
- Có job reconciliation để phát hiện sequence numbers bị bỏ quên.
- Định nghĩa cách xử lý khi message không còn khả dụng hoặc đã hết TTL.
- Theo dõi DLQ và trạng thái workflow, không chỉ ActiveMessageCount.

## 14. Scheduling và deferral không phải cùng một hàng đợi chờ

Một lỗi thiết kế là gọi **deferMessage** rồi mong message “sống lại” sau một khoảng delay cố định.

| Tình huống | Nên dùng | Lý do |
|---|---|---|
| “Nhắc đơn hàng sau 30 phút” | Scheduled message | Broker kích hoạt sau mốc thời gian |
| “Payment đã đến, đợi OrderCreated” | Deferral | Cần sự kiện nghiệp vụ bổ sung |
| “Gọi API lỗi tạm, thử lại sau 5 phút” | Scheduled retry/new message hoặc orchestration | Chờ theo thời gian, có kiểm soát retries |
| “Một message phải gửi cho hai entity cùng commit” | Transaction phù hợp | Atomic operations trong broker |
| “Tất cả message của một order phải xử lý tuần tự” | Sessions theo thiết kế | Sequence number đơn lẻ không bảo đảm thứ tự xử lý giữa consumers |
| “Đến 9:00 mỗi ngày chạy báo cáo” | Scheduler/cron + message | Scheduling một message không tạo recurrence |

**Kết hợp deferral với scheduling** có thể rất hữu ích: khi defer một message, hệ thống schedule **một message đánh thức/kiểm tra** sau vài phút. Khi tín hiệu đến, consumer dùng sequence number đã lưu để retrieve deferred message.

Nhưng wake-up message cũng có thể đến trùng, đến muộn hoặc bị cancel trễ. Cần idempotency và trạng thái workflow để xử lý an toàn.

## 15. Kết hợp ba tính năng trong một workflow thanh toán

Giả sử khi tạo order 481, hệ thống cần:

1. Phát **OrderCreated**.
2. Đặt lịch **PaymentReminder** sau 30 phút.
3. Khi **PaymentConfirmed** đến trước **OrderCreated** ở hệ thống downstream, defer payment.
4. Khi OrderCreated xuất hiện, lấy lại payment và cập nhật.
5. Nếu thanh toán xong, hủy reminder khi còn pending.
6. Nếu reminder đã active, consumer phải kiểm tra trạng thái order trước khi gửi.

~~~mermaid
flowchart TB
    API["Orders API"] --> OUTBOX["Database Outbox"]
    OUTBOX --> PUB["Publisher"]
    PUB --> ORDER["Service Bus: OrderCreated"]
    PUB --> SCHED["Scheduled PaymentReminder"]
    PAYMENT["PaymentConfirmed"] --> WORKER["Payment Worker"]
    WORKER --> READY{"Order record exists?"}
    READY -->|No| DEFER["Defer PaymentConfirmed<br/>Lưu sequence"]
    ORDER --> CREATE["Order projection updated"]
    CREATE --> RECV["Receive deferred theo sequence"]
    RECV --> DONE["Process payment idempotently"]
    READY -->|Yes| DONE
    DONE --> CANCEL["Try cancel reminder"]
    SCHED --> REM["Reminder consumer"]
    REM --> STATE{"Order is paid?"}
    STATE -->|Yes| SKIP["Complete, không gửi nhắc"]
    STATE -->|No| SEND["Send reminder idempotently"]
~~~

### 15.1. Bảng trạng thái đơn hàng

| Order state | Payment event | Scheduled reminder | Hành vi |
|---|---|---|---|
| CREATED/UNPAID | Chưa có | Pending | Đợi thanh toán; nhắc nếu đến hạn |
| CREATED/UNPAID | CONFIRMED | Pending | Ghi nhận PAID, thử cancel reminder |
| Chưa có order projection | CONFIRMED | Không liên quan | Defer PaymentConfirmed, lưu sequence |
| PAID | Reminder active | Đã kích hoạt | Complete reminder mà không gửi |
| CANCELLED | Reminder pending | Pending | Cố cancel, kiểm tra state khi reminder nhận |
| CANCELLED | Reminder active | Active | Complete/ghi audit, không gửi nhắc |

Mỗi bước thay đổi database và broker cần xét khả năng crash. Một transaction Service Bus không tự đồng bộ trạng thái **Orders** với SQL; dùng outbox, idempotency, workflow state và compensation theo thiết kế.

### 15.2. Trường hợp crash sau cập nhật DB nhưng trước Complete

Nếu Payment Worker cập nhật **Orders.state=PAID**, rồi crash trước **complete** message:

- Lock có thể hết hạn và message được redeliver.
- Consumer phải nhận biết **payment event đã xử lý** qua event ID/order state.
- Consumer complete bản nhận lại, **không ghi thêm một lần thanh toán**.
- Nếu dùng outbox để phát event tiếp theo, đảm bảo record outbox và state nghiệp vụ được commit cùng transaction database.

Đây là khác biệt giữa “at-least-once delivery” và “exactly-once business effect”.

### 15.3. Trường hợp Reminder đã active khi Cancel được gọi

Consumer vẫn phải đọc **business state** trước khi gửi. Nếu cần chống hai worker đồng thời gửi reminder, dùng record gửi nhắc với unique key hoặc atomic transition như **PENDING → SENDING → SENT**, có timeout/reconciliation và retry hợp lý.

Cancel scheduled message không phải một distributed lock hoặc cancellation token có bảo đảm tuyệt đối đối với mọi side effect.

## 16. Duplicate detection, MessageId và idempotency

### 16.1. Duplicate detection

Azure Service Bus hỗ trợ **duplicate detection** ở tier/entity phù hợp, thường dựa vào **MessageId** trong cửa sổ thời gian cấu hình, với các điều kiện bổ sung khi partitioning/sessions áp dụng.

Ví dụ producer không chắc gửi **OrderCreated(orderId=481)** đã được Service Bus ghi hay chưa. Nếu dùng lại cùng MessageId và entity bật duplicate detection, broker có thể loại bản gửi trùng trong cửa sổ hỗ trợ.

### 16.2. Những điều duplicate detection không giải quyết

- Không tự ngăn double-charge trong SQL hoặc hệ thống thanh toán bên ngoài.
- Không bảo đảm phát hiện trùng sau khi cửa sổ dedup hết hạn.
- Không cứu được producer gán MessageId ngẫu nhiên mới ở mỗi lần retry.
- Không tự ngăn hai sự kiện khác loại nhưng cùng order bị xử lý sai.
- Không thay thế database unique constraint hoặc consumer idempotency.
- Không biến transaction Service Bus thành distributed transaction.

### 16.3. MessageId nên được thiết kế

Ví dụ:

~~~text
OrderCreated:
  MessageId = "order-481-created-v1"

PaymentConfirmed:
  MessageId = "payment-provider-event-9c5..."

PaymentReminder:
  MessageId = "order-481-reminder-30m"
~~~

Không dùng dữ liệu cá nhân nhạy cảm trong MessageId nếu nó được ghi vào logs/telemetry. Với workflow có nhiều lần nhắc, thêm **reminder type + attempt/run key** có kiểm soát để không vô tình loại bỏ thông điệp hợp lệ.

## 17. Sessions, ordering và deferred message

### 17.1. Sequence number không bảo đảm thứ tự hoàn thành

Service Bus gán sequence number nhằm định danh và thể hiện thứ tự enqueuing trong những giới hạn của entity/partition. Hai consumers có thể xử lý và complete **khác thứ tự** vì thời gian thực thi khác nhau.

Nếu cần một chuỗi message cùng order được xử lý tuần tự, đánh giá **Service Bus Sessions**:

~~~text
Order 481:
   OrderCreated (SessionId=order-481)
   PaymentConfirmed (SessionId=order-481)
   PrepareShipment (SessionId=order-481)
~~~

Sessions cung cấp cơ chế lock/affinity theo session trong mô hình hỗ trợ. Nhưng **sessions không bảo đảm mọi event đến đúng thứ tự nghiệp vụ**: message có thể được phát sai thứ tự từ nhiều nguồn. Deferral vẫn có thể cần thiết khi event không có prerequisite, kết hợp trạng thái phiên/workflow.

### 17.2. Session-aware deferral

Với entity bật sessions, việc receive deferred message cần tuân theo receiver/session context phù hợp. Không dùng một receiver không hiểu session để lấy sequence number thuộc session khác. Kiểm tra API Java **ServiceBusSessionReceiverClient/ServiceBusReceiverClient** của phiên bản SDK và cách session locks được quản lý.

### 17.3. Khi nào tránh dùng sessions?

Nếu mỗi message hoàn toàn độc lập và throughput là ưu tiên lớn, session affinity có thể thêm chi phí điều phối/giới hạn concurrency không cần thiết. Đừng bật sessions cho mọi queue chỉ vì muốn sử dụng sequence number hoặc deferral.

## 18. TTL, DLQ và MaxDeliveryCount trong ba cơ chế

### 18.1. Active message TTL

Message có TTL để giới hạn việc lưu giữ khi không được xử lý. Nếu message hết hạn, Service Bus xử lý theo entity settings, có thể xóa hoặc chuyển DLQ khi bật dead-letter on expiration.

### 18.2. Scheduled TTL

Một scheduled message bắt đầu có ý nghĩa trong luồng receive sau thời điểm được enqueue/activate. Vì vậy **tính TTL dựa trên scheduled enqueue time** theo mô hình dịch vụ, không chỉ thời gian gửi yêu cầu schedule.

Điều này quan trọng với reminder: nếu TTL quá ngắn, message có thể hết hạn trước khi consumer kịp nhận khi có backlog.

### 18.3. Deferred TTL

Deferred message có hành vi expiry đặc biệt: nó có thể vẫn nằm trong entity khi đã hết hạn và chỉ được kiểm tra/di chuyển khi client cố nhận lại theo sequence number. Cần reconciliation và chiến lược xử lý expired deferred messages.

### 18.4. MaxDeliveryCount và DLQ

Nếu message bị abandon/lock expired lặp lại, delivery count tăng. Khi vượt ngưỡng **MaxDeliveryCount** theo cấu hình, message có thể vào DLQ.

| Loại tình huống | Hành vi phù hợp |
|---|---|
| Lỗi tạm ngắn | Abandon hoặc retry có backoff, giới hạn số lần |
| Lỗi theo thời gian dài | Scheduled retry với state/attempt, tùy workflow |
| Chưa đủ sự kiện | Defer + lưu sequence và trigger |
| Message không hợp lệ/poison | Dead-letter có reason và correlation |
| Không chắc commit transaction | Reconcile outcome + idempotent retry |
| Không xử lý kịp trước TTL | Điều chỉnh TTL, capacity hoặc workflow policy |

Không đẩy tất cả message lỗi vào DLQ rồi bỏ mặc. Thiết kế runbook inspect/reprocess, retention, alert và phân quyền đọc DLQ.

## 19. Transaction kết hợp scheduling: nguyên tắc và rủi ro

Một số SDK Service Bus, bao gồm **ServiceBusSenderClient** trong Azure SDK Java, hỗ trợ truyền **ServiceBusTransactionContext** vào phương thức schedule message.

Ví dụ theo API Java:

~~~java
ServiceBusTransactionContext tx = sender.createTransaction();

try {
    sender.sendMessage(
        new ServiceBusMessage("OrderCreated"), tx);

    sender.scheduleMessage(
        new ServiceBusMessage("PaymentReminder"),
        OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(30),
        tx);

    sender.commitTransaction(tx);
} catch (RuntimeException error) {
    try {
        sender.rollbackTransaction(tx);
    } catch (RuntimeException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
}
~~~

Đây là **đoạn code nằm trong class/method đã tạo sender và imports**, chỉ minh họa những thao tác cùng **một queue** ở phạm vi broker. Nếu cần một message ở queue A và reminder ở queue B, phải xác minh và cấu hình cross-entity transactions theo cơ chế được hỗ trợ.

### 19.1. Một lưu ý về sequence number của schedule trong transaction

Nếu muốn cancel sau này, ứng dụng phải lưu **sequence number** trả về từ **scheduleMessage** cùng business key và entity. Nhưng **ghi sequence number vào SQL và commit transaction Service Bus không tự atomic**.

Kế hoạch xử lý phù hợp:

- Dùng outbox/workflow state và cơ chế xác nhận kết quả.
- Ghi trạng thái **SCHEDULE_REQUESTED → SCHEDULED** sau khi broker xác nhận.
- Nếu outcome commit không rõ, reconcile trước khi schedule lại.
- Consumer reminder vẫn kiểm tra trạng thái order, không phụ thuộc tuyệt đối vào cancel.
- Không xóa record liên kết chỉ vì cancel trả về exception.

### 19.2. Không cố kéo dài transaction để giữ lịch

Transaction tồn tại trong thời gian ngắn để commit thao tác **schedule**, không mở đến lúc 30 phút sau reminder được kích hoạt. Broker lưu lịch độc lập; bạn không cần giữ connection/transaction mở suốt 30 phút.

## 20. Deferred message + scheduled wake-up

Đây là mẫu workflow kết hợp hai cơ chế nhưng vẫn có phân tách trách nhiệm rõ:

1. Consumer nhận **PaymentConfirmed**.
2. Chưa có order → lưu deferred sequence number vào workflow store và defer message.
3. Schedule một **WakeDeferredPayment** sau 5 phút.
4. Khi wake-up message active, worker kiểm tra order.
5. Nếu order đã tồn tại → receive deferred message theo sequence, xử lý rồi complete.
6. Nếu chưa có → schedule lần kiểm tra tiếp theo với attempt count và deadline.
7. Quá deadline → chuyển trạng thái business sang **NEEDS_REVIEW** hoặc phát event lỗi phù hợp.
8. Có reconciliation job rà soát các deferred records chưa được giải quyết.

~~~mermaid
flowchart TD
    P["Payment message"] --> D["Defer + store sequence"]
    D --> W["Schedule WakeUp sau 5 phút"]
    W --> Q{"Order đã sẵn sàng?"}
    Q -->|Có| R["Receive deferred by sequence"]
    R --> OK["Xử lý idempotent + complete"]
    Q -->|Không và chưa quá hạn| W2["Schedule lần kiểm tra tiếp"]
    Q -->|Quá hạn| DL["Alert / manual review"]
~~~

**Không tạo wake-up vô hạn**: gắn attempt limit, business deadline và correlation ID. Một message wake-up thất bại cũng cần retry/DLQ policy riêng.

## 21. Thiết kế an toàn trước sự cố mạng và crash

### 21.1. Bốn khoảng trống phổ biến

| Điểm crash | Kết quả có thể xảy ra | Biện pháp |
|---|---|---|
| Sau SQL commit, trước Service Bus send | Đơn hàng có trong DB nhưng chưa có event | Transactional outbox |
| Sau Service Bus send, trước đánh dấu outbox sent | Event đã gửi nhưng publisher sẽ retry | Stable MessageId + dedup/idempotent consumer |
| Sau defer, trước lưu sequence | Message tồn tại nhưng không biết cách lấy lại | Lưu state có kiểm soát, reconciliation/peek |
| Sau cancel reminder, trước ghi DB | Outcome cancel khó đối chiếu | Business state nguồn sự thật, consumer kiểm tra lại |
| Sau complete message, trước ghi external audit | Audit mất nếu lưu tách rời | Outbox hoặc ghi audit trước settlement theo design |

### 21.2. Giao thức xử lý idempotent

Một consumer có thể thực hiện:

~~~text
function process(message):
    eventId = message.messageId

    begin DB transaction
        if processedEvents contains eventId:
            result = ALREADY_PROCESSED
        else:
            validate business preconditions
            apply state change once
            insert processedEvents(eventId)
            insert outbox follow-up events
    commit DB transaction

    complete Service Bus message

    # Publisher riêng phát outbox events có MessageId ổn định.
~~~

Đây là **pseudocode**, không phải mã Java chạy trực tiếp. Nếu complete thất bại sau DB commit, message được nhận lại nhưng consumer thấy eventId trong processedEvents và chỉ cần complete, không lặp tác dụng nghiệp vụ.

### 21.3. Không mất message vì xử lý quá lâu

- Dùng PeekLock, renew lock khi cần.
- Đặt thời gian timeout hợp lý, tránh xử lý blocking vô hạn.
- Không dựa vào lock duration làm SLA cho một giao dịch nghiệp vụ dài nhiều giờ.
- Tách bước xử lý dài thành trạng thái workflow.
- Tăng worker concurrency có kiểm soát, xét sessions nếu cần ordering.
- Thiết kế shutdown graceful và đóng client đúng cách.
- Phân loại lỗi transient, permanent, authorization, quota và poison message.

## 22. Quan sát và vận hành

### 22.1. Metrics nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Active messages | Message đang có thể được nhận, phát hiện backlog |
| Scheduled messages | Khối lượng message chờ kích hoạt, phát hiện lịch tăng bất thường |
| Dead-letter messages | Message bị chuyển DLQ, cần triage |
| Incoming/outgoing messages | Lưu lượng producer/consumer |
| Successful requests / server errors / user errors | Tình trạng gọi broker theo phân loại |
| Throttled requests | Giới hạn throughput/credit và capacity |
| Transaction failures/timeouts | Tác động đến atomic operations |
| Lock lost / delivery count | Xử lý quá lâu, retry hoặc cạnh tranh |
| Deferred records trong workflow store | Message bị gác lại chưa được giải quyết |
| Schedule cancel failures | Nguy cơ reminder vẫn được kích hoạt |
| Time from scheduled activation to processed | Đo độ trễ xử lý thực tế so với thời gian mong muốn |

Không phải metric nào cũng được Azure Monitor cung cấp **nguyên dạng**; những KPI như deferred backlog theo nghiệp vụ, transaction outcome không rõ hoặc time-to-process thường cần **application telemetry/workflow store**.

### 22.2. Logs/tracing cần ghi

Một record nên có:

~~~json
{
  "event": "PAYMENT_MESSAGE_DEFERRED",
  "traceId": "trace-example",
  "orderId": "lab-481",
  "messageId": "payment-lab-481",
  "entity": "deferred-lab",
  "sequenceNumber": 34751,
  "timestampUtc": "2026-11-20T11:00:00Z",
  "reason": "ORDER_NOT_FOUND"
}
~~~

Đây là **dữ liệu minh họa**; không gửi thông tin cá nhân hoặc payload thanh toán nhạy cảm vào log. Chỉ ghi thuộc tính cần thiết và áp dụng retention/access control theo chính sách.

Các event quan trọng nên có:

- TRANSACTION_BEGIN / COMMIT_SUCCEEDED / COMMIT_UNKNOWN / ROLLBACK_FAILED.
- MESSAGE_SCHEDULED / SCHEDULE_CANCEL_ATTEMPTED / REMINDER_SKIPPED.
- MESSAGE_DEFERRED / DEFERRED_RETRIEVED / DEFERRED_EXPIRED.
- DEAD_LETTERED / REPROCESSED.
- LOCK_RENEWED / LOCK_LOST.
- RETRY_SCHEDULED / RETRY_EXHAUSTED.

### 22.3. Azure Monitor và Azure Cost Management

Mở **Service Bus namespace → Monitoring / Metrics** trong Azure Portal để xem message counts, request metrics và error/throttling. Nếu cần logs chi tiết, bật **Diagnostic settings** cho categories được dịch vụ hỗ trợ và gửi tới Log Analytics/Storage/Event Hub theo chính sách.

Giám sát messaging không chỉ là số message. Nên xác định **business SLO**, ví dụ:

- 99% PaymentConfirmed được xử lý trong 2 phút sau khi prerequisite tồn tại.
- Không có deferred record chưa giải quyết quá 2 giờ mà không alert.
- Scheduled reminder được consumer đánh giá trong vòng 5 phút sau activation.
- Không có transaction outcome unknown tồn đọng quá một khoảng đã định.
- DLQ được rà soát theo lịch vận hành.

Các mốc trên là **SLO minh họa**, không phải SLA do Azure cam kết.

## 23. Quy trình xử lý sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Transaction fails/timeout | Xử lý quá lâu, không đúng entity/client, lock lost | Rút ngắn transaction, xem timeout và SDK |
| Đã gửi hai message nhưng chỉ thấy một | Thiếu transaction, commit chưa rõ, consumer đã đọc, filters khác nhau | Kiểm tra transaction logs, entity, MessageId, consumer/DLQ |
| Commit trả lỗi nhưng message đã xuất hiện | Outcome không rõ lúc mất kết nối | Reconcile bằng idempotency/dedup, không gửi lại với ID mới |
| Scheduled message không thấy trong receive | Chưa tới thời điểm kích hoạt | Kiểm tra thời gian UTC và scheduled count |
| Scheduled message không được xử lý đúng giờ | Consumer offline/backlog/capacity | Kiểm tra thời gian activation, receiver health, queue depth |
| Cancel không có tác dụng | Message đã active, race với activation hoặc seq sai | Kiểm tra business state, seq/entity, không gửi side effect trùng |
| Deferred message không hiện trong receive | Đúng hành vi deferral | Lấy lại bằng receiveDeferredMessage(sequence) |
| Không biết deferred sequence | Chưa lưu state, consumer crash | Reconciliation bằng peek/browse và correlation ID |
| Deferred message không lấy lại được | Sai queue/session/seq, TTL hoặc lock/identity lỗi | Kiểm tra entity, session, expiration, permissions |
| Message bị DLQ do MaxDeliveryCount | Retry/abandon/lock expiry quá nhiều | Đọc DLQ reason, sửa consumer và retry policy |
| 401/403 | RBAC/SAS/identity sai | Kiểm tra Data Sender/Receiver và role propagation |
| Timeout kết nối Service Bus | Firewall, DNS, Private Endpoint, AMQP/WebSockets | Kiểm tra đường mạng và TLS |
| Backlog tăng dù nhiều consumers | Throttling, session hot key, database chậm | Xem throughput, locks, capacity và dependency |
| Tổng chi phí tăng | Nhiều operations, retry, scheduled churn, Premium units/logs | Cost Management + metrics + workflow retries |

### 23.1. Bước debug một scheduled message

1. Xác nhận namespace/entity và MessageId.
2. Xác nhận schedule request được Service Bus chấp nhận.
3. Lấy **scheduled sequence number** và scheduled enqueue time.
4. Kiểm tra thời gian UTC và trạng thái gần activation.
5. Kiểm tra có cancel/replace schedule nào không.
6. Sau mốc, kiểm tra active count và consumer logs.
7. Xem TTL/DLQ nếu message biến mất.
8. Xem business state để quyết định xử lý lại hay bỏ qua.

### 23.2. Bước debug một deferred message

1. Xác định order/workflow key và nơi lưu deferred sequence number.
2. Xác nhận đúng namespace/queue hoặc topic subscription.
3. Với session-enabled entity, xác định SessionId/receiver session context.
4. Thử **receiveDeferredMessage(sequence)** trong môi trường được phép.
5. Nếu không tìm thấy, kiểm tra TTL, DLQ, việc complete ở lần trước và reconciliation.
6. Xử lý prerequisite và side effect idempotently.
7. Complete message, đánh dấu workflow đã hoàn tất.
8. Xóa/cập nhật record deferred sau khi đã xác nhận, không xóa vô điều kiện khi outcome chưa rõ.

### 23.3. Bước debug transaction

1. Xác định transaction context và các thao tác có liên quan.
2. Kiểm tra tier/namespace/entity có hỗ trợ.
3. Xác minh receive PeekLock, lock không mất.
4. Kiểm tra timeout và latency từng thao tác.
5. Nếu cross-entity, kiểm tra cách SDK kích hoạt tính năng và transfer routing.
6. Đọc lỗi và correlation/diagnostic IDs.
7. Nếu outcome commit không rõ, **reconcile**, không tự kết luận rollback.
8. Kiểm tra duplicate detection và idempotency trước khi retry.
9. Giảm thời lượng/khối lượng transaction nếu vượt giới hạn.
10. Ghi lại kết quả và tình trạng data-plane trong runbook.

## 24. Chi phí, quota và hiệu năng

### 24.1. Vì sao ba cơ chế ảnh hưởng chi phí?

- Transaction thêm các bước điều phối/commit và có thể tăng latency khi thực hiện nhiều thao tác.
- Scheduling tạo message chờ broker quản lý và sau này kích hoạt, có thể làm tăng operations.
- Deferral cần thao tác settle và explicit receive, cùng lưu state/reconciliation.
- Retry quá nhiều làm tăng requests, network traffic, DLQ và log ingestion.
- Premium có mô hình tính phí messaging units; Standard có thành phần tính phí theo operations theo bảng giá.
- Azure Monitor, Log Analytics, Storage/SQL dùng làm workflow store cũng có phí riêng.

Không có công thức cố định “mỗi deferred message = một giá trị tiền” áp dụng mọi tier/region. Dùng bảng giá và metric thực tế.

### 24.2. Ví dụ ước lượng tải

Một hệ thống nhận **100.000 orders/ngày**. Mỗi order tạo:

- 1 event OrderCreated.
- 1 scheduled PaymentReminder.
- 1 cancel attempt với các order thanh toán trước hạn, ví dụ 80%.
- 1 xử lý PaymentConfirmed, có thể phát sinh một tỷ lệ deferral.
- 1–2 retries trong các tình huống lỗi.

Chỉ riêng số message business gốc đã khác đáng kể tổng số **broker requests** sau send, receive, complete, schedule, cancel, defer, retrieve, retries và DLQ.

Một cách lập bảng tải:

| Loại | Số thao tác ước lượng/ngày | Ghi chú |
|---|---:|---|
| OrderCreated gửi | 100.000 | Chưa tính publish/retry |
| Schedule reminder | 100.000 | 1/order |
| Cancel attempts | 80.000 | Nếu 80% paid sớm |
| PaymentConfirmed receive/settle | Theo lưu lượng thanh toán | Có thể retry |
| Deferred + retrieve | Theo tỷ lệ event đến lệch thứ tự | Phải tính hai thao tác và state store |
| DLQ/monitoring | Theo tỷ lệ lỗi | Có overhead |

Đây là mô hình **minh họa**, không phải phép đo Azure. Muốn dự toán, dùng **Service Bus pricing**, size của message, Premium units/Standard operations, tier, số queues/subscriptions, throughput và retention.

### 24.3. Hiệu năng

- Ưu tiên clients kết nối dài hạn, không mở/tắt mỗi message.
- Dùng batching/async khi phù hợp nhưng kiểm tra batch size và transaction semantics.
- Giữ transaction ngắn, tránh thao tác network kéo dài trong transaction.
- Chọn concurrency phù hợp với downstream database và sessions.
- Theo dõi lock duration, renewal, prefetch và max concurrent calls.
- Chống hot partitions/sessions nếu entity dùng partitioning/session.
- Không schedule hàng triệu message mà không đánh giá quota, storage và chi phí.
- Đặt timeouts/retry/backoff cho transient errors; với transaction, tuân thủ hướng dẫn SDK đặc biệt.

## 25. Bảo mật và vận hành production

### 25.1. IAM và quyền

- Producer dùng **Azure Service Bus Data Sender**, receiver dùng **Data Receiver**.
- Managed identity/Workload Identity không tự cấp quyền; cần role assignment đúng scope.
- Không đưa connection strings, SAS keys hoặc token vào logs/Git.
- Tách quyền quản trị namespace, quyền gửi, quyền nhận, quyền DLQ và quyền quan sát.
- RBAC ở Azure và quyền xử lý nghiệp vụ của application phải được đánh giá riêng.

### 25.2. Network và mã hóa

- Dùng TLS, DNS và đường kết nối theo yêu cầu Service Bus.
- Nếu Private Endpoint, cấu hình private DNS, VNet integration/peering và firewall đúng.
- Giới hạn client networks và egress khi cần.
- Đừng công khai queue payload nhạy cảm trong metrics/logs.
- Kiểm tra điều kiện dùng AMQP over WebSockets qua proxy nếu kết nối 5671 bị chặn theo môi trường.

### 25.3. Quản trị schema và version

Thông điệp nên có:

~~~json
{
  "eventType": "PaymentConfirmed",
  "schemaVersion": 1,
  "eventId": "payment-event-xyz",
  "orderId": "lab-481",
  "occurredAtUtc": "2026-11-20T11:00:00Z"
}
~~~

Consumer phải xử lý schema version, unknown fields, idempotency và correlation. Không lưu dữ liệu thẻ thanh toán, access token hay PII không cần thiết trong message body.

### 25.4. Runbook production

Trước khi đưa vào sản xuất:

1. Document toàn bộ entities, owners, TTL, MaxDeliveryCount, DLQ.
2. Document transaction boundaries và các phụ thuộc dữ liệu ngoài broker.
3. Lưu trạng thái scheduled/deferred trong hệ thống bền vững.
4. Có công cụ truy vấn workflow theo orderId/MessageId/sequence.
5. Có alert cho deferred quá hạn và scheduled backlog.
6. Có quy trình xử lý commit outcome unknown.
7. Có test race cancel/activation, crash sau defer và lock lost.
8. Có phương án rollback code và schema.
9. Rà soát identity, network, retention và chi phí.

## 26. Checklist thiết kế

- [ ] Đã phân biệt transaction, scheduling và deferral theo đúng mục đích.
- [ ] Namespace/tier hỗ trợ tính năng cần dùng.
- [ ] Producer/consumer dùng SDK hiện hành với Entra ID và quyền tối thiểu.
- [ ] Receiver cần settlement chạy ở **PeekLock**, không ReceiveAndDelete.
- [ ] Transaction chỉ chứa thao tác Service Bus được hỗ trợ và diễn ra nhanh.
- [ ] Cross-entity transaction được cấu hình theo SDK khi thực sự cần.
- [ ] Không coi transaction Service Bus là transaction với SQL/Cosmos/HTTP.
- [ ] Có transactional outbox và idempotency khi dữ liệu nằm ngoài broker.
- [ ] MessageId ổn định, duplicate detection có cấu hình/cửa sổ phù hợp.
- [ ] Scheduled enqueue time được tính bằng UTC và kiểm tra timezone.
- [ ] Lưu scheduled sequence number kèm entity và business key.
- [ ] Có xử lý race giữa cancel và activation.
- [ ] Consumer reminder luôn kiểm tra business state trước khi thực hiện tác dụng phụ.
- [ ] Deferred sequence number được lưu bền vững, có reconciliation.
- [ ] Không dùng deferral như timer tự thức dậy.
- [ ] TTL, MaxDeliveryCount, DLQ và lock renewal được thiết kế.
- [ ] Có hạn retry và cách xử lý poison message.
- [ ] Monitoring có active/scheduled/DLQ counts và workflow deferred state.
- [ ] Có runbook cho unknown commit, expired deferred và duplicate delivery.
- [ ] Test lỗi mạng, rollback, concurrency, restart và scale.
- [ ] Chi phí operations/Premium units, storage và logging được dự toán.

## 27. Bài tập thực hành

### Bài 1: Chọn cơ chế

Phân loại:

1. “Gửi OrderCreated và AuditRequested cùng thành công hoặc cùng rollback.”
2. “Gửi reminder sau 30 phút nếu khách chưa trả tiền.”
3. “Nhận PaymentConfirmed nhưng chưa có order tương ứng.”
4. “Mỗi ngày lúc 09:00 chạy báo cáo.”
5. “Một order có ba message phải được consumer xử lý theo thứ tự.”
6. “Sau khi ghi SQL thành công, bảo đảm event sẽ được phát dù app crash.”

Giải thích vì sao lần lượt cần transaction, scheduling, deferral, scheduler, sessions hoặc outbox phù hợp.

### Bài 2: Transaction send/rollback

Trong namespace Standard lab:

1. Tạo queue tx-lab.
2. Tạo sender Java bằng DefaultAzureCredential.
3. Tạo transaction, gửi hai message và commit.
4. Kiểm tra message ở queue.
5. Thử lỗi trước commit và rollback.
6. Mô tả trường hợp commit timeout không rõ kết quả.

### Bài 3: Hẹn giờ và hủy

1. Schedule một message sau 5 phút.
2. Ghi sequence number và mốc UTC.
3. Hủy trước mốc để kiểm tra.
4. Schedule message khác và để kích hoạt.
5. Giải thích tại sao sequence number scheduled có thể không còn dùng để cancel sau activation.
6. Thiết kế kiểm tra business state phòng race condition.

### Bài 4: Deferred message

1. Gửi PaymentConfirmed test vào deferred-lab.
2. Nhận message ở PeekLock.
3. Defer và lưu sequence number.
4. Xác nhận receive bình thường không trả về deferred message đó.
5. Retrieve bằng receiveDeferredMessage(sequence).
6. Complete và cập nhật workflow store.
7. Nêu phương án phục hồi nếu sequence number bị mất.

### Bài 5: Kiểm tra TTL và DLQ

Tạo môi trường kiểm thử có TTL/MaxDeliveryCount phù hợp để quan sát:

- Message active hết hạn.
- Message bị abandon nhiều lần.
- Deferred message nằm chờ qua TTL và được truy xuất lại.
- Message trong DLQ sau khi bị dead-letter.

Chỉ thực hiện trên queue lab; ghi lại chính xác hành vi quan sát được theo cấu hình entity.

### Bài 6: Transaction ngoài Service Bus

Orders API ghi SQL và gửi OrderCreated. Hãy vẽ hai trường hợp crash:

- SQL commit xong nhưng Service Bus send chưa có.
- Service Bus send thành công, nhưng chưa đánh dấu outbox published.

Đề xuất transactional outbox + stable MessageId + idempotent consumer.

### Bài 7: Workflow kết hợp

Thiết kế một hệ thống thanh toán:

- PaymentConfirmed có thể đến trước OrderCreated.
- Sau 30 phút cần nhắc nếu chưa thanh toán.
- Có thể khách hàng thanh toán ngay lúc reminder được kích hoạt.
- Một worker có thể crash ở bất kỳ bước nào.

Viết state machine, nơi lưu sequence numbers, các trạng thái cần commit và cách chống gửi nhắc trùng.

### Bài 8: Ước tính hiệu năng/chi phí

Hệ thống có 50.000 đơn/ngày, trung bình mỗi đơn tạo 2 message, 70% cancel reminder, 5% payment events cần defer.

Tính sơ bộ số send/schedule/cancel/defer/retrieve, sau đó giải thích tại sao con số **không bằng billed operations** khi có complete, retry, TTL, DLQ, batching và tier khác nhau.

### Câu hỏi tự kiểm tra

1. Service Bus transaction có bao gồm Azure SQL transaction không?
2. Receive operation có nằm trong transaction của Service Bus không?
3. Vì sao transaction không nên giữ mở trong lúc chờ HTTP response dài?
4. Khi transaction commit timeout, có chắc rollback đã xảy ra không?
5. Transaction khác duplicate detection ở điểm nào?
6. Scheduling có bảo đảm consumer xử lý xong đúng mốc giờ không?
7. Scheduled sequence number dùng để làm gì?
8. Cancel scheduled message sát giờ có thể race với activation không?
9. MessageId có thay thế sequence number cho cancel được không?
10. Deferred message nằm trong DLQ hay main queue?
11. Vì sao receiveMessages không trả về deferred message?
12. Nếu mất deferred sequence number thì làm gì?
13. Defer có tự nhận lại message sau 5 phút không?
14. Trong tình huống nào nên tạm dừng receive thay vì defer toàn bộ?
15. TTL của deferred message có được tự dọn ngay khi hết hạn không?
16. Vì sao cần sessions khi yêu cầu strict processing order?
17. Abandon nhiều lần có thể dẫn tới điều gì?
18. Làm sao chống double-charge dù message được redeliver?
19. Vì sao chỉ cancel reminder không đủ bảo đảm không gửi lời nhắc?
20. Metric nào cho thấy deferred workflow bị bỏ quên?

## 28. Tài liệu tham khảo

- [Azure Service Bus messaging overview — Microsoft Learn](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Transactions in Azure Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions)
- [Azure Service Bus message sequencing and scheduled messages](https://learn.microsoft.com/azure/service-bus-messaging/message-sequencing)
- [Azure Service Bus message deferral](https://learn.microsoft.com/azure/service-bus-messaging/message-deferral)
- [Message expiration and TTL](https://learn.microsoft.com/azure/service-bus-messaging/message-expiration)
- [Message transfers, locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Dead-letter queues in Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Message sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Azure SDK for Java — Service Bus client library](https://learn.microsoft.com/java/api/overview/azure/messaging-servicebus-readme)
- [ServiceBusSenderClient Java API](https://learn.microsoft.com/java/api/com.azure.messaging.servicebus.servicebussenderclient)
- [ServiceBusReceiverClient Java API](https://learn.microsoft.com/java/api/com.azure.messaging.servicebus.servicebusreceiverclient)
- [Service Bus pricing tiers](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-premium-messaging)
- [Azure Service Bus pricing](https://azure.microsoft.com/pricing/details/service-bus/)

