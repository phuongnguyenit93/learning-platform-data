# Ranh giới giao dịch và cách xử lý cập nhật nhiều partition

Một thao tác nghiệp vụ như **đặt hàng** có thể cần giảm tồn kho, tạo order, ghi audit và phát sự kiện. Nếu các item nằm trong cùng logical partition của Azure Cosmos DB for NoSQL, ứng dụng Java có thể dùng **Transactional Batch** để commit tất cả hoặc rollback tất cả. Nhưng khi các item thuộc partition key khác nhau, container khác nhau hoặc dịch vụ khác như Azure Blob Storage và Service Bus, không thể mặc định các lệnh gọi độc lập tạo thành một transaction. Khi đó cần thiết kế ranh giới dữ liệu, workflow nhiều bước, idempotency và cơ chế phục hồi.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào Azure Cosmos DB for NoSQL, Spring Data Cosmos và cách điều phối cập nhật khi một use case vượt qua một logical partition.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt atomicity của một item, Transactional Batch, stored procedure, transaction nhiều partition và workflow phân tán.
- Xác định ranh giới transaction của Cosmos DB for NoSQL trong Java SDK.
- Dùng `CosmosBatch` để tạo/cập nhật nhiều item cùng container và cùng partition key.
- Hiểu giới hạn số operation, payload, thời gian thực thi và xung đột khi nhiều transaction cùng partition.
- Giải thích vì sao `@Transactional` của Spring không tự biến nhiều lời gọi repository/SDK thành một transaction Cosmos DB xuyên partition.
- Thiết kế dữ liệu và aggregate để giữ các thay đổi cần atomicity trong cùng logical partition khi phù hợp.
- Dùng saga, transactional outbox, change feed, compensation và reconciliation cho workflow nhiều partition/dịch vụ.
- Nhận biết distributed transactions public preview mới của Cosmos DB và giới hạn hỗ trợ SDK hiện tại.
- Kiểm thử rollback, timeout không rõ kết quả, duplicate event và phục hồi sau restart.

## 2. Phân biệt các loại transaction

Không phải mọi thao tác được gọi liên tiếp trong một method Java đều nằm trong cùng transaction.

| Cấp độ | Phạm vi | Cơ chế điển hình |
| --- | --- | --- |
| Một item | Một create/replace/patch/delete item | Atomic item operation của Cosmos DB |
| Nhiều item trong một logical partition | Cùng container và cùng full partition key value | Transactional Batch hoặc stored procedure |
| Nhiều logical partition/container | Nhiều tài nguyên Cosmos DB trong cùng account | Java production hiện dùng workflow nhiều bước; distributed transactions đang preview nhưng chưa có Java SDK support |
| Cosmos DB + Blob/Service Bus/SQL/API khác | Nhiều dịch vụ độc lập | Outbox, saga, compensation, idempotency và reconciliation |

**Atomicity** có nghĩa tất cả operation trong transaction commit hoặc không operation nào được commit. **Consistency level** như Session/Strong là bảo đảm đọc giữa replica; nó không tự tạo transaction cho nhiều lần ghi. **ETag** phát hiện phiên bản item thay đổi; nó cũng không tự ghép nhiều request thành một transaction.

~~~mermaid
flowchart TD
    A[Business use case] --> B{Các thay đổi ở đâu?}
    B -->|Một item| C[Single item operation]
    B -->|Cùng container + cùng partition key| D[Transactional Batch]
    B -->|Nhiều partition/container| E[Workflow nhiều bước / saga]
    B -->|Cosmos + broker / blob / database| F[Outbox / saga / compensation]
    D --> G[Commit tất cả hoặc rollback tất cả]
    E --> H[Trạng thái + retry + reconciliation]
    F --> H
~~~

## 3. Transaction scope của Azure Cosmos DB for NoSQL

Cosmos DB for NoSQL hỗ trợ ACID transaction với snapshot isolation trong **một logical partition**. Transactional Batch nhóm các point operation có cùng partition key value trong **một container**. Stored procedure và trigger cũng chạy trong transaction scope của một logical partition key.

Điều kiện cốt lõi:

- Các item phải ở cùng container.
- Mọi operation phải dùng cùng partition key value (với hierarchical partition key, phải cung cấp full partition key path/value theo contract).
- Batch chỉ chứa các operation được dịch vụ/SDK hỗ trợ.
- Tổng payload và số operation phải nằm trong giới hạn.

Ví dụ container `orders` có partition key path `/tenantId`. Các item sau có thể nằm trong cùng một transactional batch nếu cùng `tenantId = tenant-42`:

~~~json
{
  "id": "order-1001",
  "tenantId": "tenant-42",
  "type": "order",
  "status": "PENDING"
}
~~~

~~~json
{
  "id": "outbox-order-1001",
  "tenantId": "tenant-42",
  "type": "outbox",
  "eventType": "OrderCreated",
  "eventId": "evt-1001"
}
~~~

Hai item có thể được tạo cùng nhau trong một batch. Nếu một operation thất bại, cả batch rollback. Ngược lại, một item trong container `inventory` có partition key `warehouseId=HCM-01` không thể được thêm vào batch của container `orders` để tạo transaction liên container trong Java SDK hiện hành.

~~~mermaid
flowchart LR
    subgraph C[Container orders]
      subgraph P[Logical partition tenant-42]
        O[Order item]
        E[Outbox event item]
      end
      P2[Logical partition tenant-77]
    end
    O ---|Một Transactional Batch| E
    P2 -. Không cùng transaction .- P
    I[Container inventory] -. Không cùng batch .-> C
~~~

Một query cross-partition hoặc hai lời gọi `save()` liên tiếp không làm thay đổi transaction boundary này. Việc các item có cùng tenant nhưng nằm ở hai container cũng không khiến chúng trở thành một batch hợp lệ.

## 4. Chọn aggregate và partition key để đặt đúng ranh giới atomicity

Trước khi viết code, xác định **invariant nào phải đúng ngay sau một commit**. Ví dụ:

- Order và event `OrderCreated` phải cùng tồn tại hoặc cùng không tồn tại.
- Inventory item không được âm sau khi reserve.
- Một giao dịch chuyển tiền phải ghi nhận debit, credit và ledger entry cùng nhau.
- Order và các order line phải nhất quán trong một lần tạo.

Nếu các item cần atomicity có thể được gom vào cùng logical partition mà vẫn đáp ứng tải và dung lượng, thiết kế partition key theo aggregate là một lựa chọn. Tuy nhiên, đừng gom mọi dữ liệu vào một partition chỉ để có transaction:

| Lựa chọn | Lợi ích | Rủi ro |
| --- | --- | --- |
| `tenantId` cho order và outbox trong cùng container | Transaction tạo order + event đơn giản; query theo tenant thuận tiện | Tenant quá lớn có thể thành hot partition |
| `orderId` làm partition key cho order + lines | Mọi item của một order có thể được cập nhật atomic | Query tất cả order của tenant cần cross-partition |
| `warehouseId` cho inventory | Reserve nhiều SKU trong cùng kho có thể cùng partition | Kho lớn/nhiều request có thể contention |
| Một key toàn cục cho mọi dữ liệu | Dễ đặt mọi item cùng partition | Không scale; một logical partition có thể trở thành nút thắt |

Partition key không chỉ quyết định query routing; nó còn là **transaction boundary**. Nếu use case cần transaction giữa hai tenant hoặc hai warehouse, đừng giả định một partition key đơn có thể đáp ứng cả hai. Cần chọn invariant có thể xử lý bằng workflow nhiều bước, hoặc thay đổi aggregate/data model có chủ đích.

## 5. Transactional Batch bằng Azure Cosmos DB Java SDK

Spring Data Cosmos cung cấp repository cho CRUD và query. Khi cần nhóm nhiều point operation atomic trong một container, có thể dùng API Transactional Batch của **Azure Cosmos DB Java SDK** trong adapter/persistence layer. Không để controller tự tạo batch hoặc để application service phụ thuộc class SDK.

### 5.1. Dependency và container

Ứng dụng cần Azure Cosmos DB Java SDK tương thích với dòng Spring Cloud Azure/Spring Data Cosmos đang dùng. Ví dụ dưới đây giả định ứng dụng đã có một `CosmosClient` đồng bộ được cấu hình và container `orders` được provision với partition key path `/tenantId`. Với starter, kiểm tra đúng bean mà phiên bản đang dùng expose; nếu starter chỉ cấu hình async client/builder, hãy cấu hình sync client có chủ đích hoặc dùng API async tương ứng. Không tạo client mới cho mỗi transaction và không vô tình tạo hai client có identity/endpoint khác nhau.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;

CosmosContainer orders = client.getDatabase("orders-db")
    .getContainer("orders");
~~~

Trong cấu hình Spring, có thể expose container thành bean từ client đã được starter tạo:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CosmosContainerConfiguration {
    @Bean
    CosmosContainer ordersContainer(CosmosClient client) {
        return client.getDatabase("orders-db").getContainer("orders");
    }
}
~~~

Container được tạo bằng IaC/deployment pipeline trong production. Ứng dụng cần quyền data-plane phù hợp cho mọi operation trong batch; không cấp quyền quản trị subscription chỉ để ghi item.

Ví dụ dùng `CosmosClient` là API đồng bộ và sẽ block thread gọi trong lúc chờ dịch vụ. Ứng dụng WebFlux/reactive có thể dùng `CosmosAsyncClient` và API `executeCosmosBatch` bất đồng bộ; không gọi API đồng bộ trên event-loop.

### 5.2. Tạo order và outbox event trong cùng batch

Ví dụ dùng API Java `CosmosBatch`, `CosmosBatchResponse`:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosBatch;
import com.azure.cosmos.models.CosmosBatchResponse;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Component;

@Component
public class OrderCosmosAdapter {
    private final CosmosContainer orders;

    public OrderCosmosAdapter(CosmosContainer orders) {
        this.orders = orders;
    }

    public void createOrderAndOutbox(
            OrderDocument order,
            OutboxEventDocument event) {

        if (!order.getTenantId().equals(event.getTenantId())) {
            throw new IllegalArgumentException(
                "Order and event must use the same tenant partition");
        }

        PartitionKey partitionKey =
            new PartitionKey(order.getTenantId());

        CosmosBatch batch = CosmosBatch.createCosmosBatch(partitionKey);
        batch.createItemOperation(order);
        batch.createItemOperation(event);

        CosmosBatchResponse response =
            orders.executeCosmosBatch(batch);

        if (!response.isSuccessStatusCode()) {
            throw new OrderWriteException(
                response.getStatusCode(),
                response.getResults());
        }
    }
}
~~~

`OrderDocument` và `OutboxEventDocument` phải serialize đúng partition property `tenantId` và cùng container. Ví dụ giả định các model đã được cấu hình serializer phù hợp. Trong thực tế, hãy dùng đúng constructor/method của phiên bản SDK đã pin trong BOM; code Java trên thể hiện API Transactional Batch được Microsoft Learn công bố.

Nếu batch thành công, cả order và event đều được commit. Nếu tạo order thành công nhưng tạo outbox event thất bại (ví dụ trùng ID), cả batch bị rollback. Không tồn tại trạng thái “order đã commit nhưng event chưa được ghi” trong transaction này.

### 5.3. Kiểm tra kết quả từng operation

Khi một operation trong batch thất bại:

- Operation gây lỗi mang status tương ứng, ví dụ 409 nếu item đã tồn tại.
- Các operation còn lại thường nhận **424 Failed Dependency** vì transaction bị rollback.
- Chỉ kiểm tra HTTP status của operation đầu tiên có thể bỏ qua nguyên nhân thực tế; hãy đọc danh sách kết quả theo index.

~~~java
CosmosBatchResponse response = container.executeCosmosBatch(batch);

if (!response.isSuccessStatusCode()) {
    response.getResults().forEach(result -> {
        System.err.printf(
            "operationStatus=%d%n",
            result.getStatusCode());
    });
    throw new OrderWriteException(
        response.getStatusCode(), response.getResults());
}
~~~

Không trả chi tiết account endpoint, key hoặc payload nhạy cảm vào lỗi HTTP. Lưu operation ID, activity/diagnostics phù hợp ở log nội bộ để điều tra.

### 5.4. Giới hạn batch

Theo tài liệu Transactional Batch hiện hành, giới hạn phổ biến là:

| Giới hạn | Giá trị |
| --- | ---: |
| Số operation trong một batch | Tối đa 100 |
| Kích thước payload | Tối đa 2 MB |
| Thời gian thực thi tối đa | 5 giây |

Các giới hạn này áp dụng cho Transactional Batch của NoSQL API và có thể thay đổi theo dịch vụ. Hãy kiểm tra tài liệu trước khi triển khai; không chia một transaction logic lớn thành nhiều batch rồi tuyên bố toàn bộ các batch là atomic.

## 6. Stored procedure và trigger

Cosmos DB for NoSQL hỗ trợ stored procedure và trigger viết bằng JavaScript. Chúng chạy phía server trong transaction scope của một logical partition key:

- Stored procedure có thể thực hiện nhiều thao tác đọc/ghi trong cùng partition và commit/rollback cùng nhau.
- Trigger chạy gắn với thao tác item khi client chỉ định trigger phù hợp; không giả định mọi trigger tự động chạy.
- User-defined function chủ yếu phục vụ query expression, không phải cơ chế transaction write.

Transactional Batch thường phù hợp hơn cho các thao tác point operation có thể biểu diễn từ Java vì code nằm trong ứng dụng và được version cùng CI/CD. Stored procedure có thể hữu ích khi cần logic server-side gần dữ liệu, nhưng phải quản lý mã JavaScript, triển khai/rollback và giới hạn runtime. Cả hai vẫn bị giới hạn trong một logical partition; stored procedure không phải cách mở rộng transaction sang partition khác.

## 7. @Transactional của Spring không tự mở rộng transaction Cosmos

Trong ứng dụng Spring Boot, `@Transactional` thường được dùng với Spring transaction manager của relational database hoặc một transaction manager cụ thể. Annotation này **không tự biến nhiều lần gọi `CosmosRepository.save()` hoặc SDK client thành một Transactional Batch**.

Ví dụ:

~~~java
@Transactional
public void placeOrder(OrderDocument order, OutboxEventDocument event) {
    orderRepository.save(order);
    outboxRepository.save(event);
}
~~~

Không được suy ra hai lời gọi trên atomic chỉ vì method có `@Transactional`. Nếu repository phát hai request độc lập, request đầu có thể commit trước khi request thứ hai thất bại. Muốn atomicity trong Cosmos DB Java, hãy dùng Transactional Batch cho cùng container/partition key hoặc một cơ chế cụ thể mà đúng phiên bản thư viện hỗ trợ.

Nếu cùng method còn ghi PostgreSQL, Blob Storage hoặc Service Bus, transaction manager của một dịch vụ không thể tự rollback các side effect ở dịch vụ khác. Trước khi dùng bất kỳ annotation transaction nào, hãy xác minh transaction manager, resource enlistment và phạm vi thực tế của framework/version; không dựa vào tên annotation.

## 8. Cập nhật nhiều partition: saga và workflow nhiều bước

Giả sử một đơn hàng cần:

1. Tạo order trong partition `tenant-42`.
2. Trừ tồn kho trong partition `warehouse-HCM`.
3. Ghi audit trong container khác.
4. Gửi thông báo tới Service Bus.

Trong Java Cosmos SDK hiện hành, các operation này không thể được gom thành một Transactional Batch duy nhất vì khác partition/container và có dịch vụ ngoài Cosmos. Thiết kế theo **saga**: mỗi bước là một transaction cục bộ, workflow lưu trạng thái và định nghĩa hành động bù trừ khi bước sau thất bại.

~~~mermaid
flowchart TD
    A[Receive PlaceOrder] --> B[Create order PENDING]
    B --> C[Reserve inventory]
    C --> D{Reservation succeeds?}
    D -->|Yes| E[Mark order CONFIRMED]
    E --> F[Publish OrderConfirmed]
    D -->|No| G[Mark order REJECTED]
    F --> H[Complete]
    G --> H
    C -. timeout / unknown .-> I[Reconcile reservation]
    I --> D
~~~

Ví dụ trên là saga đơn giản. Trong hệ thống thật, bước `Reserve inventory` cũng phải có idempotency key; nếu response timeout, workflow cần xác định reservation đã tồn tại chưa trước khi thử lại. Không được tạo reservation thứ hai chỉ vì caller không nhận được response lần đầu.

### 8.1. Orchestration và choreography

| Cách tổ chức | Mô tả | Khi phù hợp |
| --- | --- | --- |
| **Orchestration** | Một coordinator lưu trạng thái và ra lệnh bước tiếp theo | Workflow có nhiều bước, timeout, retry và compensation cần quan sát tập trung |
| **Choreography** | Các service phát/nhận event và phản ứng theo event | Luồng ngắn, ranh giới service rõ và event contract ổn định |

Orchestrator không phải transaction manager toàn cục. Nó lưu tiến trình và quyết định tiếp tục, retry hoặc compensate. Mỗi service vẫn phải đảm bảo idempotency cho local operation và ghi nhận kết quả bền vững.

### 8.2. Trạng thái saga

Một state machine có thể dùng:

| State | Ý nghĩa | Chuyển tiếp |
| --- | --- | --- |
| `PENDING` | Đã nhận command, chưa hoàn tất bước nào | `INVENTORY_RESERVED` hoặc `REJECTED` |
| `INVENTORY_RESERVED` | Tồn kho đã giữ | `CONFIRMED` hoặc `COMPENSATING` |
| `CONFIRMED` | Order hoàn tất theo nghiệp vụ | `COMPLETED` |
| `COMPENSATING` | Đang thực hiện hành động bù trừ | `COMPENSATED` hoặc `COMPENSATION_FAILED` |
| `COMPENSATED` | Side effect trước đó đã được bù theo quy tắc | Kết thúc hoặc cần audit |
| `FAILED_REQUIRES_REVIEW` | Không thể tự phục hồi an toàn | Nhân viên vận hành xử lý |

Mỗi chuyển trạng thái nên có `operationId`, version/ETag, thời gian, số lần thử, bước hiện tại và lý do lỗi an toàn. State transition phải được cập nhật bằng điều kiện phiên bản hoặc transaction cục bộ thích hợp để hai worker không điều khiển cùng saga một cách mâu thuẫn.

## 9. Compensation không phải rollback

Rollback của Transactional Batch xảy ra bên trong một transaction trước khi commit: tất cả operation không có hiệu lực. **Compensation** xảy ra sau khi một bước cục bộ đã commit và cần một thao tác nghiệp vụ khác để khôi phục trạng thái gần với mong muốn ban đầu.

Ví dụ:

| Bước đã thành công | Compensation có thể có | Giới hạn |
| --- | --- | --- |
| Giữ tồn kho | Release reservation | Có thể không release được nếu reservation đã được sử dụng |
| Tạo shipment | Hủy shipment | Hãng vận chuyển có thể đã bàn giao hàng |
| Charge payment | Refund | Refund là giao dịch mới, có phí/thời gian riêng |
| Ghi file vào Blob | Xóa object hoặc đánh dấu orphan | Có thể bị retention/legal hold ngăn xóa |
| Gửi email | Không thể thu hồi email đã gửi | Có thể gửi thông báo đính chính |

Vì compensation không xóa lịch sử side effect, audit phải lưu cả hành động gốc và hành động bù. Không dùng từ “rollback” cho một workflow đã phát email, charge payment hoặc gọi API ngoài.

## 10. Transactional Outbox trong Cosmos DB

Một lỗi phổ biến là ghi business item rồi publish event trong hai thao tác:

~~~text
1. Save Order thành công
2. Publish OrderCreated thất bại do broker/network/process crash
=> Order tồn tại nhưng downstream không biết
~~~

**Transactional Outbox** đặt business item và event record trong cùng một Transactional Batch:

~~~mermaid
flowchart LR
    A[Order service] --> B[Transactional Batch]
    B --> C[Order item]
    B --> D[Outbox event item]
    C --> DB[(Cosmos container)]
    D --> DB
    DB --> CF[Change Feed]
    CF --> RELAY[Outbox relay]
    RELAY --> Q[Service Bus / broker]
    Q --> CONSUMER[Idempotent consumer]
~~~

Order và outbox event phải cùng container và cùng partition key value. Khi batch commit, cả hai xuất hiện; nếu batch rollback, không event nào được phát. Change Feed Processor đọc event document và relay sang broker. Đây là mô hình **at-least-once**: relay có thể phát lại sau restart hoặc checkpoint chưa kịp ghi, nên consumer cần deduplicate theo event ID.

### 10.1. Model outbox event

~~~java
import java.time.Instant;

public class OutboxEventDocument {
    private String id;
    private String tenantId;
    private String type = "outbox";
    private String eventId;
    private String eventType;
    private int schemaVersion;
    private Instant occurredAt;
    private String aggregateId;
    private String payload;

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getType() { return type; }
    public String getEventId() { return eventId; }
    public String getEventType() { return eventType; }
    public int getSchemaVersion() { return schemaVersion; }
    public Instant getOccurredAt() { return occurredAt; }
    public String getAggregateId() { return aggregateId; }
    public String getPayload() { return payload; }
}
~~~

Trong production, dùng `@Container`, `@Id`, `@PartitionKey` hoặc mapping tương ứng và bảo đảm field `tenantId` serialize đúng container partition key path. Event ID nên ổn định qua các lần relay; không dùng broker-generated message ID làm khóa idempotency nghiệp vụ.

### 10.2. Relay và consumer

Relay cần:

- Duyệt change feed bằng checkpoint/lease phù hợp.
- Chỉ publish event đã commit trong container.
- Đưa `eventId`, `eventType`, schema version và correlation context an toàn vào message.
- Chấp nhận event có thể được giao lại; ghi nhận publish outcome và retry có giới hạn.
- Tránh vòng lặp change feed nếu việc đánh dấu “published” lại cập nhật cùng container mà relay đang theo dõi.

Consumer cần một inbox/deduplication record hoặc unique constraint để xử lý một event ID tối đa một lần về mặt business effect. Nếu consumer thực hiện side effect ngoài database của nó, side effect đó cũng cần idempotency hoặc workflow bù trừ.

Outbox giải quyết **ghi business state và event record atomically trong Cosmos DB**. Nó không tạo transaction giữa Cosmos DB và Service Bus; relay có thể gửi trùng, và consumer phải idempotent.

## 11. Cập nhật nhiều dịch vụ: Blob Storage, Service Bus và database

| Tổ hợp | Atomicity có sẵn? | Thiết kế thường dùng |
| --- | --- | --- |
| Hai item cùng container + cùng partition key | Có, Transactional Batch | Commit tất cả/rollback tất cả |
| Nhiều partition/container trong Java SDK hiện hành | Không có Transactional Batch chung | Saga/orchestration, idempotency, reconciliation |
| Cosmos DB + Azure Blob Storage | Không có distributed transaction chung | Upload staging, trạng thái PENDING/READY, cleanup/compensation |
| Cosmos DB + Azure Service Bus | Không có transaction chung mặc định giữa hai resource | Transactional Outbox + Change Feed |
| Cosmos DB + Azure SQL/PostgreSQL | Không tự động atomic | Outbox/saga hoặc thiết kế nguồn dữ liệu chính |
| Cosmos DB + external payment API | Không có rollback nguyên tử | Idempotency key, saga, refund/compensation |

### 11.1. Upload file và ghi metadata

Một workflow có thể:

1. Tạo document metadata với trạng thái `PENDING` và operation ID.
2. Upload file lên Blob Storage bằng object key ổn định.
3. Kiểm tra kết quả upload (ETag/version/checksum theo contract).
4. Cập nhật metadata thành `READY` bằng ETag/optimistic concurrency.
5. Nếu upload thất bại, chuyển `FAILED`; nếu process crash sau upload nhưng trước cập nhật metadata, reconciliation job kiểm tra object rồi hoàn tất hoặc cleanup.

Không thể giả định xóa Blob trong một catch block luôn thành công. Cleanup cũng là side effect cần retry và audit.

### 11.2. Gửi event sau khi lưu dữ liệu

Không viết `repository.save(order); serviceBusSender.sendMessage(event);` rồi cho rằng hai thao tác atomic. Ghi order + outbox bằng batch; relay gửi message sau commit. Nếu relay crash sau khi broker nhận nhưng trước khi checkpoint, event có thể gửi lại. Consumer khử trùng lặp theo event ID.

## 12. Distributed transactions public preview: điều cần biết khi dùng Java

**Cập nhật quan trọng:** Microsoft đã công bố **distributed transactions cho Azure Cosmos DB for NoSQL ở trạng thái public preview**. Tính năng preview này cho phép transaction đọc/ghi qua nhiều logical partition, container và database trong cùng account/region. Tuy nhiên, tài liệu Microsoft Learn hiện công bố hỗ trợ qua **Azure Cosmos DB .NET v3 SDK preview**; phần “Supported APIs and SDKs” ghi rõ hỗ trợ SDK khác đang được phát triển. Vì vậy, ứng dụng **Spring Boot/Spring Data Cosmos dùng Java SDK chưa thể dùng API distributed transaction preview theo hướng dẫn hiện hành**.

Giới hạn preview được công bố:

- Chỉ NoSQL (Core SQL) API.
- Account dùng provisioned throughput (manual hoặc autoscale), không phải serverless.
- Account chỉ có một write region; multi-region writes không được hỗ trợ.
- Chưa hỗ trợ một số cấu hình/tính năng như CMK, continuous backup, long-term retention, partition merge, HPK và một số môi trường sovereign/air-gapped/government.
- Cần enrollment vào preview; không có SLA và giới hạn có thể thay đổi.
- Tài liệu hiện nêu tối đa 100 operation và payload 2 MB mỗi transaction.

Không dùng code .NET `CreateDistributedWriteTransaction()` như thể đây là API Java. Khi Microsoft công bố hỗ trợ Java SDK và Spring integration, cần kiểm tra version, enrollment, semantics và giới hạn mới trước khi thay thế saga/outbox.

Trong preview, multi-partition transaction cũng có các lưu ý quan trọng: transaction được route tới write region; dữ liệu replicate sang secondary region bất đồng bộ; session token trả về theo từng operation/partition và phải truyền đúng khi cần read-your-writes ở transaction tiếp theo. Chế độ FastResponse có thể trả về trước khi commit/abort cuối cùng, nên response đó không được hiểu là kết quả commit cuối. Cancellation không chứng minh transaction đã rollback; không replay mù quáng.

Đối với bài học Spring Data Cosmos Java này, **Transactional Batch cùng partition key vẫn là lựa chọn atomicity trực tiếp**; workflow nhiều partition vẫn cần saga/outbox cho tới khi Java SDK có hỗ trợ chính thức và dự án xác nhận đủ điều kiện dùng preview/GA.

## 13. Xử lý timeout, retry và kết quả không rõ

Một request có thể timeout ở client sau khi server đã commit. Điều này đặc biệt quan trọng với transaction: client không nhận response không đồng nghĩa transaction chắc chắn rollback.

| Tình huống | Cách xử lý |
| --- | --- |
| Batch trả success | Ghi nhận commit và trả kết quả |
| Batch trả lỗi operation cụ thể | Đọc status operation gây lỗi; các operation còn lại có thể 424 do rollback |
| Batch trả 409 create conflict | Kiểm tra item/operation ID đã tồn tại và xác định đó là duplicate hay xung đột khác |
| Batch trả 412 ETag/precondition | Đọc lại item, đánh giá lại invariant và tạo batch mới nếu còn hợp lệ |
| 429/throttling | Tôn trọng retry-after/SDK retry, giới hạn concurrency và retry budget |
| Timeout/network reset sau khi gửi | Đối chiếu bằng deterministic IDs/operation record trước khi replay |
| Saga step thất bại | Retry idempotent hoặc chạy compensation theo state machine |

### 13.1. Idempotency key và deterministic item ID

Một command đặt hàng có thể mang `operationId` do ứng dụng tạo. Dùng ID ổn định để:

- Tạo item order/outbox theo cùng một command.
- Ngăn một request retry tạo nhiều order.
- Tra cứu trạng thái khi response đầu tiên bị mất.
- Khử trùng lặp ở relay và consumer.

Không dùng ID ngẫu nhiên mới mỗi lần retry. Nếu create trả 409, đọc item theo ID + partition key và so sánh operation ID/state để xác định transaction trước đã commit hay một request khác chiếm ID.

### 13.2. Contention trên cùng logical partition

Nhiều transaction đồng thời trên cùng partition key có thể gây contention. Cosmos DB có thể trả lỗi liên quan đến transaction đang chờ kết thúc, ví dụ `TXN_WAIT_FOR_TRANSACTION_END`. Hướng xử lý:

- Giữ batch ngắn và ít operation.
- Không thực hiện network call ngoài trong lúc transaction đang được xây dựng/chờ.
- Retry có exponential backoff và jitter khi lỗi được xác định là transient.
- Giới hạn số worker đồng thời cho một partition key nóng.
- Xem lại partition key nếu một logical partition nhận quá nhiều transaction.

Tăng RU/s không nhất thiết giải quyết transaction contention trên cùng một partition key.

## 14. Kiểm thử ranh giới transaction

### 14.1. Test Transactional Batch

Với emulator hoặc Azure test account, kiểm tra:

1. Tạo hai item cùng container và cùng partition key trong một batch; cả hai tồn tại sau commit.
2. Làm operation thứ hai thất bại (ví dụ create item đã tồn tại); item thứ nhất không được lưu.
3. Dùng partition key khác trong batch; xác minh SDK/dịch vụ từ chối.
4. Kiểm tra 409 và 424 theo operation index.
5. Kiểm tra ETag/If-Match trong batch nếu use case yêu cầu concurrency control.
6. Kiểm tra batch gần giới hạn payload/operation nhưng không dùng dữ liệu production.

### 14.2. Test saga và compensation

Giả lập từng điểm lỗi:

- Sau khi order PENDING được ghi nhưng trước khi reserve inventory.
- Inventory đã reserve nhưng response bị mất.
- Order đã confirmed nhưng relay chưa publish event.
- Broker đã nhận event nhưng relay chưa checkpoint.
- Compensation release inventory thất bại.
- Worker restart khi saga đang ở trạng thái COMPENSATING.

Sau mỗi lần restart, workflow phải đọc state bền vững và tiếp tục từ bước an toàn; không dựa vào biến trong memory của instance.

### 14.3. Test outbox

| Ca test | Kỳ vọng |
| --- | --- |
| Order + event batch thành công | Cả hai item cùng tồn tại |
| Event create thất bại | Order không tồn tại do rollback |
| Relay phát event rồi crash trước checkpoint | Event có thể phát lại, consumer không tạo side effect trùng |
| Event schema version cũ | Consumer xử lý tương thích hoặc đưa dead-letter |
| Change feed lag tăng | Alert và worker tiếp tục từ checkpoint |
| Event poison | Retry giới hạn, DLQ/quarantine, không chặn vô hạn các event khác |

### 14.4. Emulator và Azure thật

Cosmos DB Emulator hữu ích cho kiểm thử CRUD, Transactional Batch và mapping cơ bản. Azure thật cần được dùng để xác minh Managed Identity/native data-plane RBAC, network, throughput, throttling, diagnostics, failover và hành vi vận hành. Distributed transactions preview hiện có điều kiện enrollment và SDK riêng; không mô phỏng bằng cách giả định emulator đã hỗ trợ tính năng này.

## 15. Quy trình chọn giải pháp

~~~mermaid
flowchart TD
    A[Liệt kê invariant nghiệp vụ] --> B[Nhóm item cần commit cùng nhau]
    B --> C{Cùng container + cùng full partition key?}
    C -->|Có| D[Transactional Batch / stored procedure]
    C -->|Không| E{Có Java SDK support distributed transaction phù hợp?}
    E -->|Không| F[Saga / outbox / compensation]
    E -->|Có| G[Đánh giá trạng thái GA/preview, limits, SLA và topology]
    G --> H{Đủ điều kiện production?}
    H -->|Không| F
    H -->|Có| I[Integration test và failure test chuyên biệt]
    D --> J[Kiểm thử atomicity, 409/412/424 và timeout]
    F --> K[Kiểm thử idempotency, recovery và reconciliation]
    I --> L[Deploy có quan sát]
    J --> L
    K --> L
~~~

Trước khi triển khai, trả lời:

1. Invariant nào phải đúng ngay khi request trả thành công?
2. Các item cần atomic có cùng container và partition key value không?
3. Có thể thiết kế aggregate để gom chúng lại mà không tạo hot partition không?
4. Nếu vượt ranh giới, bước nào có thể retry và bước nào có compensation?
5. Làm sao xác định một thao tác đã commit khi response bị mất?
6. Consumer/relay có idempotent theo event ID không?
7. Nếu worker restart giữa workflow, trạng thái nào giúp tiếp tục?
8. Distributed transaction feature/SDK nào thực sự được hỗ trợ ở version triển khai?

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Cho rằng `@Transactional` bao nhiều repository save của Cosmos | Một phần dữ liệu có thể commit độc lập | Dùng Transactional Batch đúng scope |
| Thêm item khác partition vào batch | Batch không hợp lệ | Kiểm tra full partition key trước khi tạo batch |
| Gộp toàn bộ tenant vào một partition chỉ để atomic | Hot partition, contention và giới hạn dung lượng | Chọn aggregate/invariant phù hợp, dùng saga khi cần |
| Ghi Cosmos rồi gửi Service Bus trong cùng method | Có thể mất event hoặc gửi event mồ côi | Transactional Outbox + Change Feed |
| Gọi hai dịch vụ rồi catch exception để rollback thủ công | Compensation có thể thất bại và không xóa lịch sử side effect | State machine saga và reconciliation |
| Retry sau timeout với ID mới | Tạo duplicate order/payment/reservation | Deterministic operation ID và đối chiếu trạng thái |
| Coi outbox delivery là exactly-once | Consumer có thể xử lý event lặp | At-least-once + idempotent consumer |
| Dùng Change Feed như một transaction với broker | Publish/checkpoint có thể lệch | Outbox, checkpoint và dedupe |
| Dùng distributed transaction preview .NET từ Spring Java | SDK/API không tương thích | Chỉ dùng khi Java support chính thức được công bố |
| Bỏ qua transaction contention | 429/transaction wait và latency cao | Batch ngắn, backoff, giới hạn concurrency, thiết kế partition |

## 17. Bài tập thực hành

**Bài tập 1 — Đặt hàng trong một partition.** Order và outbox event nằm trong cùng container `orders`, partition key `tenantId`. Viết batch tạo hai item. Cố ý tạo event ID trùng và xác minh cả batch rollback. Phân tích status operation gây lỗi và các operation 424.

**Bài tập 2 — Inventory khác partition.** Order nằm trong partition tenant, inventory nằm trong partition warehouse. Thiết kế saga gồm create PENDING, reserve inventory, confirm order và release reservation khi cần. Xác định idempotency key và state transition ở mỗi bước.

**Bài tập 3 — Blob + Cosmos.** Upload file lên Azure Blob rồi ghi metadata vào Cosmos. Xây dựng trạng thái PENDING/READY/FAILED, object key ổn định, cleanup và reconciliation cho trường hợp process crash sau upload.

**Bài tập 4 — Transactional Outbox.** Thiết kế order item và outbox event trong cùng Transactional Batch. Xây dựng Change Feed relay tới Service Bus; mô phỏng crash sau khi publish nhưng trước checkpoint và chứng minh consumer không tạo business effect trùng.

**Bài tập 5 — Giới hạn batch.** Một workflow cần tạo 150 item, payload tổng 3 MB và thời gian xử lý vượt 5 giây. Giải thích vì sao không thể chia thành hai batch rồi tuyên bố atomic; đề xuất aggregate hoặc workflow nhiều bước.

**Bài tập 6 — Contention.** 200 request đồng thời cập nhật cùng partition key và xuất hiện `TXN_WAIT_FOR_TRANSACTION_END`. Thiết kế load test, giảm transaction duration, giới hạn concurrency và cân nhắc lại partition key.

**Bài tập 7 — Timeout không rõ kết quả.** Batch tạo order + event bị timeout sau khi request gửi đi. Thiết kế quy trình tra cứu theo operation ID trước khi retry; phân biệt retry an toàn và retry có thể tạo duplicate.

**Bài tập 8 — Preview mới.** Đọc tài liệu distributed transactions public preview của Cosmos DB. Liệt kê điều kiện account, SDK được hỗ trợ, giới hạn và lý do tính năng hiện chưa dùng trực tiếp trong Spring Data Cosmos Java. Nêu bằng chứng nào cần có trước khi thay saga bằng distributed transaction.

## 18. Ghi nhớ

- Cosmos DB for NoSQL hỗ trợ ACID transaction trong **một logical partition**; Java Transactional Batch cần cùng container và cùng full partition key value.
- **Transactional Batch** phù hợp cho các point operation cần commit/rollback cùng nhau; batch failure làm rollback toàn bộ, operation gây lỗi giữ status cụ thể và operation khác có thể nhận 424.
- Giới hạn Transactional Batch được tài liệu hiện hành nêu là **100 operation, 2 MB và 5 giây**; xác minh lại trước khi triển khai.
- `@Transactional` không tự biến nhiều lời gọi repository/SDK thành một Transactional Batch hoặc transaction xuyên Cosmos, Blob và broker.
- Khi cập nhật vượt partition/container/dịch vụ, dùng **saga, outbox, compensation, idempotency và reconciliation** để xử lý partial failure.
- Transactional Outbox ghi business item và event trong cùng partition/batch; Change Feed relay thường là at-least-once nên consumer phải deduplicate.
- Distributed transactions đa partition đã có **public preview**, nhưng tài liệu hiện chỉ nêu hỗ trợ .NET v3 SDK; Spring Data Cosmos Java chưa có API tương ứng theo danh sách hỗ trợ hiện hành. Không dùng preview như một bảo đảm production.
- Timeout/cancellation không chứng minh transaction rollback. Dùng operation ID ổn định và đối chiếu trạng thái trước khi replay.

## 19. Tài liệu tham khảo

- [Transactional Batch operations trong Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch)
- [CosmosBatch Java API](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.models.cosmosbatch?view=azure-java-stable)
- [CosmosContainer.executeCosmosBatch Java API](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.cosmoscontainer.executecosmosbatch)
- [Database transactions và optimistic concurrency control](https://learn.microsoft.com/en-us/azure/cosmos-db/database-transactions-optimistic-concurrency)
- [Stored procedures, triggers và UDFs](https://learn.microsoft.com/en-us/azure/cosmos-db/stored-procedures-triggers-udfs)
- [Partitioning và transaction scope](https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning)
- [Implement Transactional Outbox pattern bằng Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos)
- [Saga distributed transactions pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/saga)
- [Compensating Transaction pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction)
- [Use distributed transactions trong Azure Cosmos DB — public preview và SDK support](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-configure-and-use-distributed-transactions)
