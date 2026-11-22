# Transaction trong logical partition và transactional batch

Một ứng dụng thương mại điện tử cần tạo đơn hàng và đồng thời ghi một bản ghi **outbox** để phát sự kiện `OrderPlaced`. Nếu chỉ ghi đơn hàng thành công nhưng ghi outbox thất bại, worker ở hệ thống khác sẽ không biết có đơn mới. Nếu chỉ ghi outbox thành công nhưng đơn hàng chưa tồn tại, người tiêu thụ sự kiện có thể gặp dữ liệu không nhất quán. Với **Azure Cosmos DB for NoSQL**, cách thiết kế an toàn là đặt những tài liệu cần cập nhật nguyên tử trong **cùng một logical partition** của **cùng container**, rồi thực thi chúng qua **Transactional Batch**.

Điểm mấu chốt: Transactional Batch không phải một “transaction SQL toàn hệ thống”. Nó chỉ cam kết tính **all-or-nothing** cho những thao tác điểm (point operations) được hỗ trợ **trong cùng logical partition key**. Nó không biến mọi document của một container hay nhiều containers thành một giao dịch ACID duy nhất.

Bài thuộc chương **Dữ liệu NoSQL với Cosmos DB** trong module `CLOUD_PROVIDERS_AZURE`. Module này khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, storage, dữ liệu, triển khai, giám sát, bảo mật và chi phí. Vì thế, ngoài viết batch thành công, bài còn hướng dẫn chọn partition key, thiết kế nhất quán nghiệp vụ, quản lý RU, bảo mật kết nối và khắc phục sự cố.

> Phạm vi chính là **API for NoSQL (Azure Cosmos DB for NoSQL)**. Azure Cosmos DB còn có các API và mô hình dữ liệu khác với semantics/SDK khác nhau; không lấy ví dụ Transactional Batch ở đây áp dụng nguyên xi cho MongoDB, Cassandra, Gremlin hoặc Table. SDK, giới hạn và tính năng có thể đổi theo phiên bản/tier; các lệnh và dữ liệu chỉ dành cho môi trường thực hành được phê duyệt.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **container, partition key path, partition key value, logical partition và physical partition**.
2. Hiểu ý nghĩa của **transactional scope** trong Cosmos DB for NoSQL.
3. Phân biệt transaction trong một logical partition với **cross-partition bulk**, nhiều requests độc lập và giao dịch phân tán.
4. Xác định những thao tác Transactional Batch thường hỗ trợ như **create, read, replace, upsert, delete, patch** theo SDK.
5. Xây một batch ghi **Order + OutboxEvent** nguyên tử và xử lý kết quả theo từng operation.
6. Dùng **ETag/optimistic concurrency** để ngăn lost update khi có nhiều client.
7. Giải thích **snapshot isolation**, tính nguyên tử, lỗi rollback và khả năng một batch thất bại vì một thao tác.
8. Thiết kế partition key để những document cần chung transaction nằm cùng phạm vi mà không tạo hot partition.
9. Xử lý **409 Conflict, 412 Precondition Failed, 429 throttling, timeout** và những lần thử lại có kết quả không rõ.
10. Tách biệt **ACID trong Cosmos DB** với **eventual consistency, multi-region replication** và tác động bên ngoài như Service Bus.
11. Áp dụng **transactional outbox + change feed processor** và tiêu thụ sự kiện idempotent.
12. Quan sát request charge (RU), latency, diagnostic logs và kiểm thử failure/retry.
13. Phân biệt Transactional Batch với **JavaScript stored procedure** và **saga/outbox**.
14. Hoàn thành bài thực hành có hai documents cùng partition và một negative test cross-partition.

## 2. Bối cảnh: một đơn hàng cần hai bản ghi nhất quán

Giả sử API xử lý yêu cầu:

```json
{
  "tenantId": "tenant-a",
  "orderId": "ORD-1042",
  "customerId": "C-81",
  "amount": 250000,
  "currency": "VND"
}
```

Trong một container `orders`, hệ thống cần ghi hai items:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042",
  "docType": "Order",
  "tenantId": "tenant-a",
  "orderId": "ORD-1042",
  "status": "Pending",
  "amount": 250000,
  "currency": "VND"
}
```

```json
{
  "id": "outbox:evt-1042-created",
  "orderScope": "tenant-a|ORD-1042",
  "docType": "OutboxEvent",
  "eventId": "evt-1042-created",
  "eventType": "OrderPlaced",
  "orderId": "ORD-1042",
  "publishState": "Pending"
}
```

Cả hai đều có `orderScope = "tenant-a|ORD-1042"`. Nếu container được cấu hình **partition key path `/orderScope`**, hai items thuộc **cùng logical partition**.

Mục tiêu transaction:

- **Cả Order và OutboxEvent được tạo**, hoặc **không item mới nào được tạo**.
- Nếu trùng ID hoặc ETag conflict, không được để lại trạng thái “đơn hàng mới không có outbox”.
- Sau khi commit, một processor có thể phát event ra Service Bus theo cơ chế riêng; không nhầm việc phát ra broker với phạm vi ACID của database.

### Tại sao không dùng hai calls CreateItemAsync riêng?

```text
Create Order → thành công
                  |
                  v
       Create OutboxEvent → timeout/thất bại
                  |
                  v
          Order tồn tại nhưng
          outbox chưa chắc tồn tại
```

Dù có retry, việc xử lý idempotency và tình trạng commit không rõ vẫn khó hơn. Transactional Batch giảm cửa sổ không nhất quán **giữa các items cùng logical partition**, nhưng không mở rộng transaction tới hệ thống bên ngoài.

## 3. Phân biệt account, database, container và partition

Một mô hình tổ chức điển hình:

```text
Azure subscription / resource group
└── Azure Cosmos DB account (API for NoSQL)
    └── Database: commerce
        └── Container: orders
            ├── Logical partition "tenant-a|ORD-1042"
            │   ├── Order: order:ORD-1042
            │   └── OutboxEvent: outbox:evt-1042-created
            │
            ├── Logical partition "tenant-a|ORD-1043"
            │   ├── Order: order:ORD-1043
            │   └── OutboxEvent: outbox:evt-1043-created
            │
            └── Logical partition "tenant-b|ORD-9001"
                └── Order: order:ORD-9001
```

| Thành phần | Vai trò | Liên hệ transaction |
|---|---|---|
| **Account** | Endpoint, regions, auth, consistency và cấu hình dịch vụ. | Không phải phạm vi ACID tự do xuyên account. |
| **Database** | Nhóm các containers, có thể dùng throughput theo mô hình phù hợp. | Không tạo transaction giữa nhiều containers. |
| **Container** | Nơi lưu items, indexing, partition key path, throughput. | Batch phải chạy trên **một container**. |
| **Partition key path** | Đường dẫn thuộc tính dùng phân vùng, ví dụ `/orderScope`. | Xác định cách group items thành logical partitions. |
| **Partition key value** | Giá trị thực của document, ví dụ `tenant-a|ORD-1042`. | Batch buộc dùng **một giá trị key**. |
| **Logical partition** | Tập items có **cùng giá trị partition key đầy đủ** trong container. | Đơn vị của ACID transaction/Transactional Batch. |
| **Physical partition** | Đơn vị hạ tầng quản lý lưu trữ và RU, chứa nhiều logical partitions. | **Không** phải phạm vi cho phép một batch chạm mọi logical key. |

## 4. Logical partition khác physical partition ra sao?

Azure Cosmos DB phân tán dữ liệu để mở rộng quy mô. **Logical partition** là khái niệm do ứng dụng và partition key quyết định; **physical partition** là khái niệm hạ tầng của dịch vụ.

```text
Container: orders, partition key /orderScope

Physical partition P0
  ├── Logical key tenant-a|ORD-1042
  │      ├── order document
  │      └── outbox document
  └── Logical key tenant-b|ORD-9001
         └── order document

Physical partition P1
  └── Logical key tenant-a|ORD-1043
         ├── order document
         └── outbox document
```

Giả sử hai logical keys tình cờ nằm trên **cùng physical partition**. Bạn **vẫn không được** sử dụng Transactional Batch để ghi cùng lúc hai logical keys. Phạm vi transaction là **logical**, không phải physical partition.

Dịch vụ có thể split/redistribute physical partitions khi scale; ứng dụng không nên dựa vào ánh xạ physical partition để quyết định transaction. Điều bạn kiểm soát là **partition key path và value**.

### Hai items cùng ID nhưng khác key?

Trong API for NoSQL, định danh point lookup của item thường gắn với **cặp (partition key, id)**. Hai items có thể dùng cùng `id` nếu partition key khác nhau, theo semantics container. Vì vậy chỉ dùng `id` mà không mang đúng partition key có thể khiến reads/updates không xác định đúng item hoặc phát sinh cross-partition query tốn RU.

## 5. Vì sao Cosmos DB ràng buộc transaction vào logical partition?

Phân phối dữ liệu sang nhiều partitions giúp throughput và khả năng scale, nhưng một transaction cần điều phối trên nhiều partition sẽ phức tạp hơn, tăng latency và rủi ro concurrency/failure.

Cosmos DB for NoSQL vì thế cung cấp **ACID transaction trong một logical partition**, nơi các thao tác trên những items thuộc cùng key có thể được thực hiện như một đơn vị nhất quán.

Khi thiết kế cần hỏi:

1. Những documents nào phải được commit **cùng lúc**?
2. Chúng có thể dùng cùng partition key mà vẫn tối ưu distribution/throughput không?
3. Có yêu cầu ghi tới **container khác** không?
4. Có thao tác bắt buộc gọi **dịch vụ ngoài** như payment provider, SQL Database hoặc Service Bus không?
5. Hệ thống có chấp nhận eventual consistency giữa các aggregates không?
6. Có thể dùng saga/outbox/idempotency để xử lý những bước nằm ngoài transaction scope?

Một schema NoSQL tốt thường được thiết kế từ **access patterns và transaction boundaries**, không chỉ từ các bảng quan hệ đem chuyển sang JSON.

## 6. ACID trong một logical partition có nghĩa gì?

Bốn chữ ACID:

| Thuộc tính | Ý nghĩa trong Transactional Batch |
|---|---|
| **Atomicity** | Các operations trong batch **cùng commit hoặc cùng rollback**. |
| **Consistency** | Transaction bảo toàn các quy tắc nhất quán do hệ thống lưu trữ thực thi, cộng với bất biến nghiệp vụ mà code/ETag/validation thiết kế đúng. |
| **Isolation** | Thao tác transactional trong logical partition theo **snapshot isolation** được dịch vụ cung cấp; không nhìn trạng thái trung gian đã commit một phần. |
| **Durability** | Khi transaction được commit theo contract dịch vụ, thay đổi được lưu theo durability/replication settings và consistency guarantees tương ứng. |

**Consistency ở ACID** khác **Cosmos DB consistency level** (Strong, Bounded Staleness, Session, Consistent Prefix, Eventual). Đây là hai vấn đề cần phân biệt.

Ví dụ:

- Transactional Batch tạo Order và Outbox nguyên tử trong một partition.
- Một client đọc từ region/replica khác dưới consistency level cho phép lag có thể chưa nhìn thấy commit mới nhất.
- Nhưng không nên vì thế kết luận transaction đã “nửa commit” trong phạm vi mà Cosmos DB bảo đảm.

### Atomicity không tự chứng minh nghiệp vụ đúng

Nếu bạn tạo hai items cùng một amount sai, cả hai có thể được commit nguyên tử nhưng dữ liệu vẫn **sai nghiệp vụ**. Database transaction không thay thế schema validation, checks, authorization, amount calculations và quy tắc doanh nghiệp.

## 7. Transactional Batch hỗ trợ những thao tác nào?

Trong Azure Cosmos DB for NoSQL SDK hỗ trợ, **Transactional Batch** cho phép gom các **point operations** thuộc cùng logical partition thành một yêu cầu.

Các thao tác thường gặp:

| Operation | Ý nghĩa | Dùng khi |
|---|---|---|
| **Create** | Tạo item mới; trùng ID trong partition sẽ conflict. | Tạo Order và Outbox mới. |
| **Read** | Đọc item theo ID/partition key như một phần của batch khi SDK hỗ trợ. | Đọc trạng thái cần thiết. |
| **Replace** | Thay thế item đã có, thường kết hợp ETag. | Chuyển trạng thái Order theo phiên bản. |
| **Upsert** | Tạo nếu chưa có hoặc thay đổi item hiện có theo semantics SDK. | Đồng bộ một record khi overwrite được chấp nhận. |
| **Delete** | Xóa item theo ID. | Xóa document phụ khi điều kiện nghiệp vụ cho phép. |
| **Patch** | Thay đổi một số paths/properties mà không thay toàn bộ document. | Cập nhật trạng thái/counter khi API hỗ trợ. |

### Những điều không có trong một Batch API “tự do”

- Không bao gồm arbitrary cross-partition SQL queries.
- Không đảm bảo transaction xuyên hai containers.
- Không gọi Service Bus hay email **bên trong ACID commit**.
- Không tự giữ transaction mở qua nhiều HTTP requests.
- Không bao hàm code external chạy giữa hai operations.
- Không tự tạo distributed transaction có prepare/commit trên các database regions khác nhau.
- Không tự kiểm tra mọi business invariant nếu code không biểu diễn điều kiện thực thi.

**Nếu cần đọc một truy vấn phức tạp rồi quyết định hàng loạt writes**, có thể phải thiết kế lại aggregate hoặc cân nhắc stored procedure trong phạm vi logical partition và giới hạn được hỗ trợ.

## 8. Giới hạn của Transactional Batch

Một Transactional Batch được thiết kế cho **tập thao tác ngắn**. Các giới hạn thường được tài liệu API for NoSQL công bố gồm:

- Tối đa **100 operations** trong một batch.
- Giới hạn **kích thước payload batch khoảng 2 MB**.
- Giới hạn **thời gian thực thi phía dịch vụ ở mức vài giây** (thường được nêu là 5 giây).

**Hãy xác nhận giới hạn hiện hành của SDK/dịch vụ trước khi triển khai**; những số trên là mốc lập thiết kế, không phải lời cam kết tính năng cho mọi API, region hoặc phiên bản.

### Không nên làm gì?

- Nhét 20.000 dòng hóa đơn vào một batch.
- Giữ transaction trong lúc chờ HTTP API thanh toán trả lời.
- Tách một transaction 150 operations thành hai batches rồi tuyên bố toàn bộ 150 thao tác atomic.
- Dùng batch để thay bulk ingestion trên nhiều partition keys.
- Dùng quá nhiều operations làm request thường xuyên vượt RU budget và timeout.

### Phân biệt với Bulk

**Bulk** trong SDK thường tối ưu throughput khi gửi nhiều point operations song song, có thể thuộc nhiều logical partitions. Nhưng **Bulk không đồng nghĩa một ACID transaction** cho tất cả thao tác đó.

| Công cụ | Mục tiêu | Atomicity |
|---|---|---|
| Transactional Batch | Nhóm các operations cùng key thành một commit. | Trong logical partition. |
| Bulk operations | Tăng hiệu suất nhiều operations, kể cả đa partition. | Mỗi thao tác/transaction riêng; không atomic toàn batch đa key. |
| Stored procedure | Logic JavaScript chạy ở server trong partition. | Trong logical partition khi được hỗ trợ. |
| Saga/outbox | Phối hợp các bước phân tán. | Không có một ACID commit bao phủ mọi service; dùng trạng thái, retry và compensation. |

## 9. Chọn partition key theo aggregate boundary

Đây là quyết định quan trọng nhất khi muốn transaction nhiều items.

Giả sử mỗi đơn hàng là một **aggregate** gồm Order, PaymentAttempt metadata và OutboxEvent. Bạn muốn cập nhật các items này nguyên tử theo **một Order ID**.

Ba lựa chọn:

| Partition key | Ưu điểm | Hạn chế |
|---|---|---|
| `/tenantId` | Nhiều items của cùng tenant có thể chung transaction. | Tenant lớn dễ hot logical partition, kích thước key range tăng; khó phân phối tải. |
| `/orderId` | Items thuộc cùng đơn hàng chung partition. | Phải xử lý uniqueness của orderId giữa tenants và truy vấn theo tenant. |
| `/orderScope` = `tenantId|orderId` | Rõ aggregate, tránh trùng order ID giữa tenants, phân tán theo đơn. | Truy vấn tất cả đơn của tenant có thể fan-out nếu không có query/indexing strategy. |

Với bài lab, chọn **`/orderScope`**.

### Cần tránh “hot partition”

Nếu tất cả khách hàng ghi vào `orderScope="global"`, chỉ có một logical partition gánh phần lớn workload. Dù container có tổng RU cao, một logical partition/hot physical partition vẫn có giới hạn riêng. Điều này làm batch bị throttling trong khi những partition khác nhàn rỗi.

**Đừng chọn partition key chỉ để có transaction thật rộng.** Chọn aggregate cần atomicity nhỏ, phân phối tốt và khớp các point reads/writes quan trọng.

## 10. Thiết kế container đơn hay nhiều containers?

Một schema từ SQL có thể đề xuất:

```text
Container Orders
Container OrderItems
Container OutboxEvents
```

Nhưng nếu muốn một Transactional Batch cập nhật Order và OutboxEvent **cùng một ACID commit**, ba containers tách biệt **không đáp ứng** yêu cầu.

Một lựa chọn là **co-locate nhiều doc types trong một container**:

```text
Container orders, partition key: /orderScope
  - docType=Order, id=order:<orderId>
  - docType=OutboxEvent, id=outbox:<eventId>
  - docType=OrderItem, id=item:<sku> (nếu cần)
```

Ưu điểm:

- Các items cùng `orderScope` thuộc transaction boundary giống nhau.
- Point reads/updates dùng cặp ID + partition key.
- Có thể tạo order + outbox nguyên tử.
- Change feed có thể phát hiện records mới để downstream xử lý.

Đánh đổi:

- Query/indexing thay đổi khi nhiều doc types cùng container.
- RU và TTL policies cần thiết kế phù hợp.
- Query mọi orders theo tenant có thể cross-partition nếu key theo order.
- Kích thước logical partition, số documents và tần suất ghi có thể gây hot keys.
- Không phải mọi quan hệ nghiệp vụ đều nên gộp vào một aggregate.

### Nếu vẫn bắt buộc hai containers?

Hãy dùng **saga, outbox relay, change feed, reconciliation** hoặc một data architecture khác. Không tuyên bố tạo một transaction cross-container bằng cách gọi hai batches liên tiếp.

## 11. Partition key path, value và immutable nature

Khi tạo container, bạn chọn **partition key path**, ví dụ:

```text
/orders container:
  partition key path = /orderScope
```

Mỗi document phải mang giá trị phù hợp:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042",
  "status": "Pending"
}
```

Batch được bắt đầu với partition key value:

```text
PartitionKey("tenant-a|ORD-1042")
```

**Không thể tạo một batch với partition key A rồi viết item có partition key B**. SDK/server phải từ chối thao tác không đúng phạm vi.

### Partition key không nên được dùng như một field trạng thái thay đổi

Nếu bạn lấy `/status` làm partition key:

- Order chuyển từ Pending sang Paid nghĩa là cần đổi partition key.
- Partition key của item không được sửa trực tiếp qua Replace/Patch như một field bình thường.
- Di chuyển sang key khác đòi hỏi mô hình **create new + delete old**, không atomic xuyên hai logical partitions.
- Query và transaction boundaries trở nên rối.

Dùng khóa **ổn định theo vòng đời aggregate**, ví dụ tenant/order, thay vì field nghiệp vụ biến động liên tục.

## 12. Hierarchical partition key: cần đầy đủ các thành phần

Trong những container dùng **hierarchical partition keys (HPK)**, logical partition được xác định bởi **toàn bộ tuple khóa**, không chỉ prefix cấp đầu.

Ví dụ:

```text
Partition key paths:
  /tenantId
  /orderId

Full key:
  ("tenant-a", "ORD-1042")
```

Order và Outbox phải có **cả tenantId lẫn orderId giống nhau** để cùng logical partition. Hai đơn `("tenant-a", "ORD-1042")` và `("tenant-a", "ORD-1043")` không thuộc chung transaction chỉ vì cùng tenant.

Trong .NET SDK có khả năng xây full key như:

```csharp
PartitionKey fullKey = new PartitionKeyBuilder()
    .Add("tenant-a")
    .Add("ORD-1042")
    .Build();
```

### Khi nào cân nhắc HPK?

- Multi-tenant có tenant lớn và cần phân phối dữ liệu tốt hơn chỉ dùng tenantId.
- Query/access patterns cần tenant prefix trong khi vẫn phân phối theo khóa cấp sau.
- Muốn transactional scope theo một aggregate dưới tenant.
- Có kế hoạch logical/physical partition capacity và RU distribution rõ ràng.

Không tự coi HPK là cách mở rộng transaction từ một đơn hàng sang **mọi đơn của tenant**. Transactional Batch vẫn yêu cầu các operations dùng **cùng full logical partition key** theo khả năng API.

## 13. Thiết lập tài nguyên lab qua Azure Portal

Lab giả định:

| Tài nguyên | Giá trị minh họa |
|---|---|
| Resource group | `rg-cosmos-lab` |
| Cosmos DB account | `cosmos-shop-lab-unique` |
| API | **Azure Cosmos DB for NoSQL** |
| Database | `commerce` |
| Container | `orders` |
| Partition key | `/orderScope` |
| Order scope | `tenant-a|ORD-1042` |
| Thực thi | Azure Cosmos DB .NET SDK với identity được cấp quyền |
| Data | 100% giả lập; không chứa khách hàng thật |
| Kiểm tra | Hai documents cùng xuất hiện hoặc cùng không xuất hiện |

Các bước:

1. Vào Azure Portal, xác nhận tenant/subscription và budget.
2. Tạo Cosmos DB account **API for NoSQL** trong môi trường lab được phê duyệt, chọn region và capacity theo chính sách.
3. Chọn throughput mode phù hợp (manual provisioned/autoscale/serverless khi tính năng hỗ trợ); không mặc định mọi mode có cùng cách tính phí.
4. Tạo database `commerce` và container `orders` với partition key path **`/orderScope`**.
5. Bật authentication/RBAC/network restrictions cần thiết.
6. Gán quyền data plane thích hợp cho identity chạy SDK.
7. Xác nhận endpoint, database/container names và throughput.
8. Ghi lại configuration; không lưu account keys hoặc tokens vào repo.
9. Dùng local development identity hoặc managed identity của runtime đã được phê duyệt.
10. Sau thực hành, kiểm tra môi trường và dọn resources theo đúng quyền, không xóa account dùng chung.

**Thay partition key path** sau khi container chứa dữ liệu không giống đổi tên field đơn giản; thường cần lập kế hoạch migration sang container mới. Vì vậy preflight key trước khi tạo workload thật rất quan trọng.

## 14. Azure CLI: kiểm tra metadata read-only

Trước khi chạy SDK, xác minh đúng account và container:

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

az cosmosdb show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<COSMOS_ACCOUNT_NAME>" \
  --query "{Name:name,Location:location,Endpoint:documentEndpoint}" \
  --output json

az cosmosdb sql database show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --name "commerce" \
  --output json

az cosmosdb sql container show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --database-name "commerce" \
  --name "orders" \
  --query "{Name:name,PartitionKey:resource.partitionKey}" \
  --output json
```

Các field đầu ra có thể khác theo phiên bản ARM/CLI, nên nếu JSON query không có giá trị hãy kiểm tra metadata container thực. Với CLI có schema khác, dùng `az cosmosdb sql container show --help`.

### Điều CLI không chứng minh

Những lệnh trên chỉ giúp xác nhận **metadata/configuration**. Chúng không chứng minh:

- Data plane identity có thể tạo item.
- Một Batch có commit nguyên tử.
- App có read-your-writes trên region/consistency đang sử dụng.
- RU đủ cho peak traffic.
- Outbox processor đã phát message tới Service Bus.
- Logical partition không nóng hoặc không vượt giới hạn kích thước.

Muốn nghiệm thu phải chạy batch trên dữ liệu lab và kiểm tra postconditions theo đúng partition key.

## 15. Chuẩn bị .NET SDK và danh tính

Ví dụ SDK sử dụng **Azure Cosmos DB for NoSQL .NET SDK v3** theo API phổ biến cùng `Azure.Identity`. Mục tiêu là minh họa cách gọi Transactional Batch, không yêu cầu bạn chạy build/tests trong repo của bài học.

Trong project .NET của **lab riêng** đã được phê duyệt, các package cần thiết:

```bash
dotnet add package Microsoft.Azure.Cosmos
dotnet add package Azure.Identity
```

Dùng environment variable chứa **endpoint URL không có key**:

```text
COSMOS_ENDPOINT=https://cosmos-shop-lab-unique.documents.azure.com:443/
```

Và identity đã được cấp Cosmos DB **data-plane** role phù hợp. Người dùng chạy local có thể dùng danh tính được chọn bởi `DefaultAzureCredential`; deployment trong Azure nên ưu tiên managed identity hoặc Workload Identity theo môi trường.

### Control-plane RBAC khác data-plane RBAC

Một tài khoản có quyền tạo account/container qua Azure Resource Manager **chưa chắc có quyền read/write items** qua SDK. Với Cosmos DB for NoSQL, kiểm tra mô hình **Cosmos DB built-in data-plane roles** và scope thực sự được hỗ trợ. Không trao account keys cho toàn bộ đội chỉ để giải quyết lỗi 403.

**Lệnh thử hoặc kết nối không cần in credential thật.** Dữ liệu lab dưới đây chỉ dùng tên tài nguyên và nội dung không nhạy cảm.

## 16. Mẫu .NET SDK: tạo Order và Outbox trong một batch

Ví dụ đầy đủ ở mức một file C# (.NET SDK phù hợp), giả định container có partition key `/orderScope`:

```csharp
using Azure.Identity;
using Microsoft.Azure.Cosmos;

string endpoint = Environment.GetEnvironmentVariable("COSMOS_ENDPOINT")
    ?? throw new InvalidOperationException("Missing COSMOS_ENDPOINT");

using var cosmosClient = new CosmosClient(
    endpoint,
    new DefaultAzureCredential());

Container container = cosmosClient.GetContainer("commerce", "orders");

string tenantId = "tenant-a";
string orderId = "ORD-1042";
string orderScope = $"{tenantId}|{orderId}";

var order = new
{
    id = $"order:{orderId}",
    orderScope,
    docType = "Order",
    tenantId,
    orderId,
    status = "Pending",
    amount = 250000,
    currency = "VND"
};

var outbox = new
{
    id = "outbox:evt-1042-created",
    orderScope,
    docType = "OutboxEvent",
    eventId = "evt-1042-created",
    eventType = "OrderPlaced",
    orderId,
    publishState = "Pending"
};

using TransactionalBatchResponse response = await container
    .CreateTransactionalBatch(new PartitionKey(orderScope))
    .CreateItem(order)
    .CreateItem(outbox)
    .ExecuteAsync();

Console.WriteLine($"Batch status: {response.StatusCode}");
Console.WriteLine($"Success: {response.IsSuccessStatusCode}");
Console.WriteLine($"Request charge: {response.RequestCharge} RU");

if (!response.IsSuccessStatusCode)
{
    // Không coi một operation đã tạo thành công riêng lẻ.
    // Xem operation results để tìm nguyên nhân của batch failure.
    for (int i = 0; i < response.Count; i++)
    {
        Console.WriteLine(
            $"Operation {i} status: {response[i].StatusCode}");
    }
    throw new InvalidOperationException(
        "Order + outbox transaction failed");
}

Console.WriteLine("Order and outbox committed atomically.");
```

**Giải thích điểm cốt lõi:**

1. `GetContainer("commerce", "orders")` chọn **một container**.
2. `CreateTransactionalBatch(new PartitionKey(orderScope))` đặt **một logical partition key** cho toàn bộ batch.
3. Cả `order` và `outbox` phải có cùng giá trị `orderScope`.
4. `CreateItem(order)` và `CreateItem(outbox)` tạo **hai operations** trong một transaction.
5. `ExecuteAsync()` là lúc gửi transaction tới Cosmos DB.
6. `IsSuccessStatusCode` phản ánh trạng thái batch; phải kiểm tra, không chỉ việc có HTTP response.
7. `response[i].StatusCode` giúp định vị lỗi operation nếu batch failed.
8. `RequestCharge` giúp quan sát chi phí RU của request.
9. API trả thành công nghĩa là **Order + Outbox đã commit trong container**; chưa nói event đã tới Service Bus.

Không log toàn bộ documents nếu chứa thông tin người dùng thực. Console ở ví dụ chỉ in trạng thái và RU.

## 17. Negative test: một operation lỗi thì cả batch rollback

Giả sử đã có Order trong logical partition. Bạn cố tạo lại cùng ID và đồng thời tạo một outbox event mới:

```text
Batch partition key = tenant-a|ORD-1042

Operation 0: CREATE id=order:ORD-1042   → ID conflict (409)
Operation 1: CREATE id=outbox:new-event  → không commit

Expected: không có outbox:new-event được tạo
          chỉ vì nó là operation thứ hai.
```

Khi một operation thất bại, **cả transaction không được commit**. Những operations khác có thể có trạng thái phụ như **424 Failed Dependency** trong batch response khi chúng không thể thành công vì operation khác thất bại. Hãy xem **operation đầu tiên có mã lỗi gốc** và các kết quả chi tiết, không hiểu 424 là lỗi độc lập của mỗi item.

### Kiểm chứng

1. Chọn một ID outbox chưa tồn tại.
2. Cố tạo item Order trùng ID trong batch.
3. Kiểm tra batch báo failed.
4. Đọc Order cũ: không bị ghi đè ngoài ý muốn.
5. Point-read Outbox mới bằng **cùng partition key**: kỳ vọng không tồn tại.
6. Ghi status/error codes và RU (không ghi data nhạy cảm).
7. Không xóa item Production để dựng negative test.

### Một trường hợp thất bại khác

Nếu một item có `orderScope="tenant-a|ORD-1042"` nhưng item khác có `orderScope="tenant-a|ORD-1043"`, batch không có đủ điều kiện cùng logical partition. SDK/server có thể từ chối vì partition key mismatch/bad request. **Không có chế độ tự chia một Transactional Batch thành hai giao dịch độc lập mà vẫn bảo đảm nguyên tử toàn bộ**.

## 18. ETag và optimistic concurrency control

Hai người dùng cùng cập nhật Order có thể gây **lost update**:

```text
T0: Order.status = Pending, version = V1

Worker A đọc V1
Worker B đọc V1

Worker A đổi thành Paid
Worker B đổi thành Cancelled

Nếu không kiểm tra phiên bản:
  cập nhật của worker sau có thể ghi đè worker trước.
```

Cosmos DB gắn **ETag** cho item; client có thể gửi **If-Match ETag** cho replace/delete/patch theo SDK và điều kiện hỗ trợ. Nếu ETag đã thay đổi, thao tác có thể thất bại với **412 Precondition Failed** thay vì âm thầm ghi đè.

### Vì sao ETag hữu ích trong batch?

Bạn có thể:

1. Point-read Order để lấy document và ETag.
2. Tính trạng thái tiếp theo dựa trên thông tin đã đọc.
3. Tạo batch gồm **Replace Order với IfMatchEtag** và **Create OutboxEvent**.
4. Nếu ETag không còn khớp, **cả batch thất bại**, không có event mô tả một trạng thái chưa được commit.

## 19. Mẫu .NET SDK: Replace + Outbox với If-Match

Ví dụ dưới đây minh họa optimistic concurrency khi chuyển một Order sang trạng thái Paid. Chỉ thực hiện khi đã có tài nguyên lab phù hợp.

```csharp
using Azure.Identity;
using Microsoft.Azure.Cosmos;

using var client = new CosmosClient(
    Environment.GetEnvironmentVariable("COSMOS_ENDPOINT")!,
    new DefaultAzureCredential());

Container container = client.GetContainer("commerce", "orders");
string scope = "tenant-a|ORD-1042";
string orderDocId = "order:ORD-1042";
var pk = new PartitionKey(scope);

// Kiểu OrderDoc ở cuối ví dụ có trường JSON phù hợp.
ItemResponse<OrderDoc> current = await container.ReadItemAsync<OrderDoc>(
    id: orderDocId,
    partitionKey: pk);

if (current.Resource.status != "Pending")
{
    throw new InvalidOperationException(
        "Order must be Pending before marking Paid.");
}

current.Resource.status = "Paid";
current.Resource.updatedAtUtc = DateTimeOffset.UtcNow.ToString("O");

var evt = new
{
    id = "outbox:evt-1042-paid",
    orderScope = scope,
    docType = "OutboxEvent",
    eventId = "evt-1042-paid",
    eventType = "OrderPaid",
    orderId = "ORD-1042",
    publishState = "Pending"
};

using TransactionalBatchResponse result = await container
    .CreateTransactionalBatch(pk)
    .ReplaceItem(
        orderDocId,
        current.Resource,
        new TransactionalBatchItemRequestOptions
        {
            IfMatchEtag = current.ETag
        })
    .CreateItem(evt)
    .ExecuteAsync();

if (!result.IsSuccessStatusCode)
{
    Console.WriteLine($"Batch failed: {result.StatusCode}");
    for (int i = 0; i < result.Count; i++)
    {
        Console.WriteLine($"Op {i}: {result[i].StatusCode}");
    }
    // Khi gặp ETag conflict: đọc trạng thái mới và quyết định,
    // không tự động ghi đè hoặc gửi event cũ.
}
else
{
    Console.WriteLine("OrderPaid + outbox committed.");
}

public sealed class OrderDoc
{
    public string id { get; set; } = "";
    public string orderScope { get; set; } = "";
    public string docType { get; set; } = "Order";
    public string status { get; set; } = "";
    public string updatedAtUtc { get; set; } = "";
}
```

> Ví dụ minh họa API của Cosmos DB .NET SDK v3, dùng kiểu dữ liệu tối giản. Khi ứng dụng thực có thêm thuộc tính Order, cần bảo toàn các trường và chính sách serialization khi Replace; nếu không, Replace toàn document có thể làm mất các thuộc tính không có trong model. Trường hợp chỉ cần đổi vài field, xem xét Patch và điều kiện phù hợp theo SDK/version.

### Điều gì xảy ra khi một worker khác thắng race?

Nếu Worker A commit trước, ETag của Order đổi từ V1 sang V2. Batch của Worker B dùng IfMatch V1 sẽ bị từ chối. Nó phải **đọc lại state** và quyết định đúng business rule; không chỉ đổi IfMatch thành wildcard để cưỡng ép ghi đè.

### Nếu chưa dùng ETag?

Transactional Batch vẫn atomic cho các operations **bên trong một batch**, nhưng không tự bảo vệ business decision được tính từ **dữ liệu đọc trước đó ngoài batch**. Nếu giá trị read có thể thay đổi giữa Read và ExecuteAsync, cần optimistic concurrency hoặc thiết kế điều kiện khác phù hợp.

## 20. Patch trong batch và tránh replace thừa

**Patch** có thể giảm việc gửi cả document khi chỉ muốn sửa một vài paths, tùy SDK version và thao tác được hỗ trợ.

Ý tưởng:

```text
Batch(pk = "tenant-a|ORD-1042"):
  PATCH order:ORD-1042
    set /status = "Paid"
    set /updatedAtUtc = <time>
  CREATE outbox:evt-1042-paid
```

Ưu điểm:

- Không cần gửi toàn bộ document chỉ để sửa một số properties.
- Có thể giảm nguy cơ code model mất trường khi replace không đủ.
- Có thể kết hợp các operations trong cùng logical partition.

Nhưng **Patch không tự chứng minh transition hợp lệ**. Cần kiểm tra điều kiện như trạng thái hiện tại phải là Pending, ETag hoặc filter predicate được SDK hỗ trợ. Nếu không, một payment callback cũ có thể sửa trạng thái đã Cancelled thành Paid.

**Không giả định Patch luôn rẻ hơn hoặc luôn không conflict**. Đo RU, operation semantics và indexing impact.

## 21. Upsert: tiện lợi nhưng rủi ro đối với event idempotency

Upsert thuận tiện khi bạn muốn “tạo hoặc thay” một item theo ID. Tuy nhiên, dùng Upsert cho Order hoặc Outbox không cân nhắc có thể che giấu những lần gửi trùng.

Ví dụ một event `evt-1042-created` được xử lý hai lần:

- Với **CreateItem** và ID cố định, lần thứ hai trả **409 Conflict** — tín hiệu có thể dùng để kiểm tra liệu thao tác đã xảy ra trước đó.
- Với **UpsertItem**, lần thứ hai có thể ghi đè item đã có, đổi timestamp/metadata và tạo thêm change-feed activity không mong muốn.

Vì vậy:

- Ưu tiên **Create + idempotency ID ổn định** khi event chỉ được tạo một lần.
- Chỉ dùng Upsert khi overwrite là hợp đồng nghiệp vụ mong muốn.
- Không dùng upsert thay thế conditional update/ETag trên trạng thái tài chính quan trọng.
- Khi gặp 409, xác minh item hiện có có **cùng business payload/operation ID**; đừng coi mọi Conflict là “đã xử lý thành công”.

## 22. Mọi document trong batch phải cùng full partition key

Một lỗi hay gặp:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042"
}
```

và:

```json
{
  "id": "outbox:evt-1042-created",
  "orderScope": "tenant-a|ORD-1043"
}
```

Dù cả hai có `tenantId=tenant-a` trong một field khác, **full partition key không trùng**.

### Checklist trước ExecuteAsync

1. Container là đúng container mong muốn?
2. Partition key path thực là `/orderScope`?
3. Mỗi document đều có field `orderScope` và đúng kiểu string?
4. Các values có **giống hệt** (bao gồm case, dấu cách, cách encode)?
5. Batch có tạo bằng `new PartitionKey(scope)` đúng không?
6. ID các documents độc lập nhưng đều duy nhất **trong cùng partition**?
7. Có thao tác nào dùng container khác hoặc REST API bên ngoài không?
8. Tổng số operations và request size có nằm trong giới hạn?
9. SDK nhận đúng phiên bản partition key (đơn/hierarchical)?
10. Log đã loại bỏ secrets và PII?

**Sai giá trị partition key không được Cosmos DB tự sửa** bằng cách đi tìm item ở partition khác cho một transaction.

## 23. RU/s và chi phí của Transactional Batch

Azure Cosmos DB sử dụng **Request Units (RU)** để biểu diễn chi phí tương đối của các thao tác dữ liệu, dựa trên kích thước item, indexing, query/workload và các yếu tố khác. Throughput có thể được cấu hình theo **RU/s** trong các mô hình provisioned/autoscale hoặc tính phí khác theo SKU.

### Các yếu tố tăng RU

- Thêm nhiều Create/Replace/Delete/Patch operations.
- Item lớn và nhiều indexed properties.
- Index updates do các thuộc tính thay đổi.
- Write volume cao trên một partition key.
- Batch thất bại và bị retry lặp lại.
- Point reads, ETag verification và queries phục vụ validation.
- Stored procedures/change feed hoặc các consumer operations khác nằm ngoài batch.

**Batch một request** không đồng nghĩa “chỉ tốn 1 RU”. Server tính request charge theo khối lượng công việc thực tế và trả số RU tiêu thụ.

### Ví dụ lập kế hoạch minh họa

Giả sử batch Order + Outbox trong lab đo được trung bình **12 RU**. Với 200 requests/giây:

```text
Write demand ≈ 200 batches/s × 12 RU/batch
             ≈ 2.400 RU/s
```

Đây **không phải mức RU cố định** của mọi batch hai item. Bạn phải đo `RequestCharge` trên payload/indexing thực tế, cân nhắc retry, tải đọc, change feed và phân phối partition.

### Throttling 429

Khi vượt capacity hiện có, Cosmos DB có thể trả **429 Too Many Requests** kèm retry hints. SDK có cơ chế retry cho một số tình huống theo cấu hình, nhưng phải:

- Theo dõi số 429 và latency thực, không chỉ lỗi cuối.
- Đặt retry budget/backoff hợp lý.
- Kiểm tra nóng tập trung ở **một partition key** trước khi chỉ tăng tổng RU.
- Cân nhắc batch size, write rate và indexing policy.
- Không spam retries của hàng nghìn clients đồng thời.
- Theo dõi cả chi phí tăng khi nâng RU/s/autoscale.

## 24. Hot logical partition và giới hạn quy mô

Chọn partition key chỉ để gom “mọi thứ trong tenant” có thể khiến tenant lớn tạo hotspot.

```text
Container throughput đủ cao

Logical key "tenant-enterprise"
  90% writes + 90% transactions → hotspot

Logical keys tenant-small-1, tenant-small-2
  rất ít traffic
```

Hệ thống có thể throttle tenant-enterprise dù các partitions khác còn tài nguyên. Cùng lúc, logical partition còn chịu các hạn mức dung lượng được dịch vụ công bố và mô hình HPK/large partition options.

### Cách giảm rủi ro

1. Xác định **aggregate boundary nhỏ hơn**, ví dụ tenant+order thay vì tenant.
2. Phân tích top partition keys theo RU, storage và request count.
3. Tách dữ liệu lịch sử/analytics ra khỏi hot transaction container khi phù hợp.
4. Dùng HPK nếu access patterns hỗ trợ và hiểu đầy đủ tuple transaction.
5. Nếu aggregate quá lớn để atomic trong một logical partition, thiết kế saga hoặc domain boundaries khác.
6. Không phân tán cùng một aggregate cần atomicity bằng random key mà không có cách thay thế consistency.

**Không có partition key “tốt nhất” cho mọi hệ thống**: phải đánh đổi transaction scope, point read efficiency, query fan-out, capacity và tenancy isolation.

## 25. Snapshot isolation và đọc dữ liệu nhất quán

Transactional Batch thực thi theo cơ chế transactional isolation được Cosmos DB cung cấp trong logical partition. Khi nhiều operations tạo/cập nhật các items liên quan, batch giữ tính all-or-nothing và snapshot semantics theo dịch vụ.

Nhưng cần tránh hai hiểu nhầm:

1. **Một query cross-partition sau batch** không tự trở thành một global snapshot của toàn account. Những partition khác có thể đang đổi đồng thời.
2. **Một consumer đọc từ region khác** có thể chịu consistency/replication delay; không suy ra snapshot transaction đang mở bao phủ mọi region.

### Một ví dụ đọc nghiệp vụ

Nếu API cần trả “Order + Outbox” sau create:

- Cả hai items được commit atomically khi batch thành công.
- Nếu client đọc theo **cùng partition** và consistency/session context phù hợp, có thể xác minh kết quả.
- Đừng tách hai truy vấn cross-region với consistency yếu rồi diễn giải độ trễ nhìn thấy là partial commit.
- Để đọc **một aggregate** trong cùng partition, có thể dùng point reads hoặc query scoped theo partition key và logic consistency phù hợp.

### Tách database consistency và transaction

Cosmos DB có các consistency levels như **Strong, Bounded Staleness, Session, Consistent Prefix, Eventual**. Chọn level ảnh hưởng latency, availability và freshness, nhưng **không thay đổi quy tắc Batch chỉ trong một logical partition**.

Nếu ứng dụng cần **read-your-writes** sau batch, hãy thiết kế session token/region routing/SDK client lifetime thích hợp thay vì đoán mọi reader ở mọi region thấy commit tức thì.

## 26. Multi-region writes: transaction vẫn không phải global ACID

Một Cosmos DB account có thể được cấu hình nhiều read regions và trong các thiết lập hỗ trợ có thể nhiều write regions. Điều đó làm bài toán consistency/conflict resolution phức tạp hơn.

Những điều cần phân biệt:

- Transactional Batch ACID scope vẫn gắn với **logical partition**, không phải một distributed transaction qua tất cả regions.
- Multi-region replication và consistency levels ảnh hưởng **thời điểm thay đổi xuất hiện tại region khác**.
- Với multi-write, cần hiểu cơ chế **conflict resolution**, write conflicts và semantics trong dịch vụ.
- Đừng mặc định hai writers ở hai regions cùng ghi một business aggregate sẽ tuân thủ một global serialization/unique business constraint nếu kiến trúc không bảo đảm.
- Idempotency keys, bounded retries, region failover và reconciliation cần được thiết kế kỹ.
- Những lỗi do client timeout trong quá trình region failover có thể dẫn tới kết quả không rõ ngay cả khi batch đã commit ở một nơi.

Đối với transaction tài chính, chỉ “bật multi-region” không đủ để chứng minh exactly-once business effect. Cần lựa chọn write topology, ownership của aggregate và quy trình xử lý conflicts.

## 27. Transactional outbox: nối ACID trong Cosmos DB với Service Bus

Đây là một ứng dụng điển hình của Transactional Batch.

```text
Orders API
   |
   v
Transactional Batch trong 1 logical partition
   +-- CREATE/UPDATE Order
   +-- CREATE OutboxEvent
   |
   v
Cosmos DB COMMIT thành công
   |
   v
Change Feed Processor / Outbox relay
   |
   +-- Đọc OutboxEvent mới/được cập nhật
   +-- Publish Azure Service Bus / Event Hubs
   +-- Ghi trạng thái/marker theo thiết kế
   |
   v
Downstream worker
   +-- Idempotent event processing
   +-- Persist business result
```

**Bước ghi Order + Outbox** nằm trong ACID. **Bước gửi Service Bus** không nằm trong transaction Cosmos DB, vì vậy hệ thống phải chấp nhận và xử lý các tình huống:

1. Cosmos DB commit xong nhưng relay chưa chạy.
2. Relay gửi message thành công rồi crash trước khi đánh dấu sent.
3. Relay phát cùng event lần nữa khi restart/rebalance.
4. Service Bus receiver xử lý rồi timeout trước khi Complete.
5. Downstream DB xử lý thành công nhưng có duplicate event.
6. Outbox quá lớn hoặc processor lag tăng, làm event đến chậm.

### Vai trò của Change Feed

Change feed ghi nhận các thay đổi được Cosmos DB hỗ trợ trên items của container và có thể được consumer xử lý theo cursor/checkpoint model. Nó là cách phổ biến để xây relay mà không phải poll toàn bộ container.

Tuy nhiên:

- Consumer có thể **đọc lại** sự kiện; cần idempotency.
- Phải lọc `docType = "OutboxEvent"` ở processor/application nếu container có nhiều loại docs.
- Hành vi với **deletes, TTL, intermediate updates** phụ thuộc change feed mode/tính năng; không mặc định mọi thay đổi đều phát giống một audit log đầy đủ.
- Checkpoint/lease của processor khác với ACID commit Order + Outbox.
- Change feed processing có thể chậm hoặc bị ngắt; phải đo lag và cảnh báo.
- Không đưa bí mật/chứng từ không cần vào outbox payload.

## 28. Outbox relay và vấn đề gửi trùng

Giả sử có OutboxEvent `evt-1042-created`:

```text
T0: OutboxEvent đã commit
T1: Relay publish Service Bus thành công
T2: Relay crash trước khi ghi publishState=Sent
T3: Relay restart
T4: Relay publish lại event cùng eventId
```

Transaction trong Cosmos DB **không thể atomic** với việc publish Service Bus. Giải pháp cần kết hợp:

- **Message ID ổn định** (eventId) từ lúc tạo outbox.
- Consumer sử dụng **inbox/idempotent handler**, ví dụ unique constraint theo eventId.
- Relay có retries/backoff và dead-letter/quarantine policy.
- Theo dõi trạng thái event và reconciliation khi relay lag.
- Có thể tận dụng duplicate detection của broker nếu được hỗ trợ, nhưng không dựa hoàn toàn vào cơ chế đó thay vì idempotency.
- Đặt alerts cho số event pending/tuổi event và số lần retry.
- Không đánh dấu outbox Sent **trước khi** publish được broker xác nhận nếu điều đó dẫn tới mất event.

### Lưu ý về trạng thái Sent và change feed

Nếu cùng outbox item được cập nhật nhiều lần trong quá trình gửi, mode change feed có thể phát các phiên bản cập nhật; processor phải tránh **tự xử lý lại** sự kiện đã Sent. Một số hệ thống chọn immutable outbox documents kết hợp external lease/checkpoint hoặc trạng thái riêng; điều này cần test theo change feed mode và retry semantics thực tế.

## 29. Idempotency khi client gửi lại cùng một batch

Một API request có thể timeout ngay sau khi Cosmos DB **đã commit**, làm client không biết kết quả.

```text
Client → ExecuteAsync(Order + Outbox)
           |
       Cosmos DB COMMIT
           |
       Response mất vì network timeout
           |
       Client retry
```

Nếu dùng hai Create operations với **IDs ổn định**, retry sau commit có thể trả 409 vì items đã tồn tại. Nhưng không phải cứ gặp 409 là được phép trả HTTP 200/202:

1. Point-read items theo đúng partition key.
2. So business operation/requestId với request đang retry.
3. Kiểm tra nội dung cần thiết có khớp không (không chỉ ID).
4. Nếu cả Order/Outbox tồn tại và trạng thái đúng, có thể trả kết quả “đã tiếp nhận” theo API contract.
5. Nếu ID trùng nhưng payload khác, đây có thể là **idempotency key reuse error** cần trả Conflict.
6. Nếu không thể xác minh vì lỗi mạng, báo trạng thái chưa rõ và có cơ chế query/status/reconciliation.

### Không tạo ID ngẫu nhiên khi retry

Nếu mỗi lần retry dùng `Guid.NewGuid()` để tạo eventId mới, hệ thống có thể tạo nhiều outbox records cho cùng một order operation. Hãy tạo ID một lần từ request/business operation hoặc dùng khóa ổn định do caller cung cấp và được xác thực.

## 30. Xử lý lỗi batch theo từng operation

Những status thường gặp:

| Mã/trạng thái | Ý nghĩa khả dĩ | Điều tra/ứng xử |
|---|---|---|
| **2xx** | Batch được chấp nhận/thành công theo SDK. | Kiểm tra toàn batch và dùng metrics/diagnostics. |
| **400 Bad Request** | Partition key mismatch, malformed operation hoặc cấu hình không hợp lệ. | Kiểm tra paths, types, IDs, payload. |
| **401/403** | Credential/data-plane quyền chưa phù hợp, policy/permission error. | Kiểm tra Entra identity, role assignment, key/token và network. |
| **404 Not Found** | Replace/Delete/Read tới item không tồn tại hoặc sai partition key. | Point-read với đúng key; không đoán ID toàn cục. |
| **409 Conflict** | Create trùng (id, partition key) hoặc constraint. | Xác minh idempotency/bản ghi hiện có. |
| **412 Precondition Failed** | ETag/IfMatch hoặc điều kiện optimistic concurrency không thỏa. | Đọc lại state, quyết định transition hợp lệ. |
| **424 Failed Dependency** | Operation bị ảnh hưởng vì một operation khác trong batch thất bại. | Tìm operation gây lỗi gốc trong response. |
| **429 Too Many Requests** | RU/capacity bị throttle. | Retry có backoff, đo hot partition/RU. |
| **413 Request Entity Too Large** hoặc giới hạn batch | Batch payload vượt giới hạn. | Chia aggregate hợp lý; không tách atomicity rồi giấu. |
| **Timeout/network error** | Không biết request đã tới server/commit chưa. | Read-after-error và idempotency, tránh retry không kiểm soát. |
| **5xx/503** | Dịch vụ/connectivity có vấn đề tạm thời. | Theo dõi Azure status, diagnostics, retry policy và RTO. |

### Trình tự phân tích batch failure

1. Ghi operation count, partition key **đã được làm sạch**, timing và correlation/ActivityId.
2. Kiểm tra batch-level status, request charge và diagnostics.
3. Xem status của từng operation, xác định mã lỗi **gốc**.
4. Kiểm tra container partition key path/key value và item IDs.
5. Nếu 409/412, point-read rồi so state/idempotency.
6. Nếu 429, so RU/throttle/hot partition.
7. Nếu timeout, không suy ra batch rollback; xác minh state sau khi kết nối hồi phục.
8. Chỉ retry khi semantics an toàn và trong giới hạn.
9. Cảnh báo nếu lỗi kéo dài hoặc nhiều batches của cùng aggregate thất bại.
10. Giữ logs tối thiểu, không in payload nhạy cảm.

## 31. Điểm khác biệt: lỗi được trả về và lỗi vận chuyển

Nếu Cosmos DB trả **batch response** với status failure, bạn biết server đã đánh giá request theo contract API và có thể xem operation results.

Nhưng nếu **kết nối bị ngắt trước khi response tới client**, ứng dụng có thể không biết server có commit hay không. Đây là một tình huống **ambiguous outcome**, khác với một batch response thông báo rollback rõ ràng.

Ví dụ:

- Trả 409 có nghĩa tạo item đó conflict; xem toàn bộ batch.
- Trả 412 có nghĩa điều kiện optimistic concurrency thất bại.
- Request mất response sau một commit thành công có thể khiến client thấy timeout dù transaction đã commit.

**Không biến network timeout thành “giao dịch chắc chắn thất bại”.** Thiết kế retry cần đọc lại trạng thái và idempotency.

## 32. So sánh Transactional Batch và JavaScript stored procedure

Azure Cosmos DB for NoSQL cũng hỗ trợ **JavaScript stored procedures** cho transaction trong một logical partition theo semantics và runtime giới hạn.

| Tiêu chí | Transactional Batch | Stored procedure |
|---|---|---|
| Nơi mô tả logic | Client SDK (C#/.NET, Java, ngôn ngữ hỗ trợ). | JavaScript chạy ở phía service. |
| Thao tác chính | Point operations được SDK hỗ trợ. | Logic JavaScript dùng API context/collection theo phạm vi. |
| Scope ACID | Một logical partition trong một container. | Một logical partition trong một container. |
| Kiểm soát logic giữa operations | Client xây operations trước khi execute; kết hợp ETag/conditions. | Có thể chạy logic transaction trong stored procedure theo API được hỗ trợ. |
| Deployment | SDK application code. | Phải quản lý/deploy stored procedure resource. |
| Latency | Một request batch, tránh nhiều round trips. | Server-side execution nhưng có runtime/code constraints. |
| Maintainability | Dễ tích hợp codebase/CI testing với ngôn ngữ app. | Cần quản lý JS server-side code và khả năng tương thích. |
| Cross-partition | Không. | Không. |

### Chọn cách nào?

- **Transactional Batch**: nhiều point writes rõ ràng, ít nhánh nghiệp vụ, muốn code trong ứng dụng và dùng optimistic concurrency.
- **Stored procedure**: khi cần logic transaction server-side trong cùng key mà SDK batch không diễn đạt tiện, nếu giới hạn runtime phù hợp.
- **Saga/outbox**: khi yêu cầu workflow trải qua nhiều keys/containers/services.

**Không coi stored procedure là lối tắt cho cross-partition ACID.** Khi gọi stored procedure, cũng phải cung cấp partition key phù hợp.

## 33. Transaction giữa nhiều logical partitions: dùng saga thay vì ảo tưởng ACID

Giả sử chuyển 100 điểm thưởng từ tài khoản A sang B, nhưng hai tài khoản nằm ở hai logical partitions.

```text
Partition A: LoyaltyAccount A
Partition B: LoyaltyAccount B
```

Bạn **không thể** dùng một Transactional Batch để đảm bảo atomic update trên cả A và B nếu keys khác nhau.

Một hướng thiết kế là **saga/process manager**:

```text
Transfer request + operationId
        |
        v
Saga state = Pending
        |
        +-- Step 1: reserve/deduct A (idempotent)
        |
        +-- Step 2: credit B (idempotent)
        |
        +-- Success → saga Completed
        |
        +-- Failure → retry / compensating action
                         |
                         +-- reconcile/alert
```

Nhưng saga có những phức tạp:

- Có **trạng thái trung gian** và eventual consistency.
- Compensation không phải hoàn tác ACID tuyệt đối.
- Những bước đã tác động thế giới ngoài như email/chuyển tiền có thể không hoàn tác được.
- Cần timeout, retry, idempotency và audit.
- Phải tránh double-spend hoặc trừ điểm hai lần khi có concurrency.
- Cần business owner chấp nhận thời gian xử lý và trạng thái pending.

Nếu nghiệp vụ thực sự yêu cầu atomicity đa bản ghi mạnh trên toàn hệ thống, hãy đánh giá liệu Cosmos DB NoSQL data model và transaction boundary có phù hợp hay cần một transactional database/ledger khác.

## 34. Bảo mật: identity và least privilege

Một ứng dụng tạo Order + Outbox cần quyền đọc/ghi items trong Cosmos DB, nhưng không nhất thiết quyền thay đổi account, throughput hay xóa container.

### Các lớp quyền

| Lớp | Mục đích | Sai lầm thường gặp |
|---|---|---|
| Azure Resource Manager RBAC | Tạo/sửa account, database, container, networking. | Nghĩ Contributor tự cho phép mọi data-plane operations. |
| Cosmos DB for NoSQL data-plane RBAC | Read/write items theo scope/role. | Cấp key toàn account khi chỉ cần read/write trong một container. |
| Network restrictions | Public/private endpoint, VNet, firewall, TLS. | Mở public toàn Internet để xử lý 403 thiếu quyền. |
| Application authorization | Tenant/order-level checks, kiểm tra người gọi. | Coi partition key là một cơ chế kiểm soát quyền. |
| Secrets/keys | Account keys, managed identity, credentials. | Đưa key vào Git/terminal logs. |

### Partition key không phải security boundary

Một caller biết `tenant-a|ORD-1042` không có nghĩa họ được phép thao tác trên Order đó. Cosmos DB transaction scope **không tự enforce tenant authorization** trong code ứng dụng. Cần:

1. Xác thực client/user.
2. Xác minh caller được phép truy cập tenant/order.
3. Dùng container/data-plane scope và identity tối thiểu.
4. Không để caller tự gửi tùy ý partition key của tenant khác mà thiếu kiểm tra.
5. Audit những thao tác cập nhật trạng thái có rủi ro.
6. Bảo vệ PII, mã hóa, backup và key rotation theo chính sách.

### Managed identity

Khi chạy trên AKS, Azure Functions, Container Apps hoặc VM, cân nhắc managed identity/Workload Identity được Azure.Identity SDK hỗ trợ. Bật identity chưa đồng nghĩa có data-plane permissions; role assignment và endpoint/network vẫn phải hợp lệ.

## 35. Mạng và multi-region: lỗi connection không phải lỗi transaction

Một batch có thể thất bại hoặc timeout vì:

- Private Endpoint/DNS phân giải sai.
- NSG, Azure Firewall, UDR hoặc outbound rules chặn kết nối.
- TLS certificate validation lỗi hoặc endpoint sai.
- Regional endpoint/routing không đúng.
- Retry policies và failover regions được SDK cấu hình không phù hợp.
- Cosmos DB service có sự cố tạm thời.
- RU capacity thiếu hoặc một partition quá nóng.

### Quy trình phân biệt

1. Kiểm tra `COSMOS_ENDPOINT` đúng account và API for NoSQL.
2. Kiểm tra DNS/TLS từ **runtime thật**, không chỉ laptop.
3. Xác minh principal có Cosmos DB data-plane role.
4. Dùng một read-only/point-read lab để kiểm tra data-plane connectivity.
5. Xem ActivityId/diagnostics để phân biệt transport errors và server status.
6. Nếu 429, tập trung RU/hot partition; nếu 403, tập trung quyền.
7. Không dùng HTTP client generic để ghi lại keys/tokens trong verbose logs.
8. Khi đổi region, xem consistency/session tokens và failover semantics.

**Một database account có trạng thái “Online” trong Azure Portal chưa chứng minh ứng dụng có thể thực thi transaction**. Cần thử data-plane requests có kiểm soát.

## 36. Observability: theo dõi batch đúng cách

Một batch production nên có những tín hiệu:

- **Operation ID/requestId** của nghiệp vụ.
- **Partition key fingerprint** hoặc giá trị đã làm sạch, tránh log PII.
- **Batch operation count**, loại operations.
- **Batch-level status** và failure operation index.
- **RequestCharge (RU)**.
- **Latency** tổng thể và các retry counts.
- **Cosmos DB ActivityId/diagnostics** nếu SDK cung cấp.
- **429 rate**, hot partition metrics và throughput utilization.
- **Outbox pending age/change feed lag**, nếu dùng outbox.
- **Downstream publish/processing success**, không chỉ batch commit.
- **Conflict (409/412)** và tỷ lệ optimistic concurrency thất bại.

### Một dashboard tối thiểu

| Metric | Vì sao cần |
|---|---|
| Số batch successful/failed theo thời gian | Sức khỏe write path. |
| P50/P95/P99 batch latency | Xác định trải nghiệm API. |
| RU per successful order | Kiểm soát chi phí và indexing changes. |
| 429 rate + retry delay | Phát hiện capacity hoặc hot key. |
| 409/412 conflict rate | Phát hiện retries, race và duplicated operations. |
| Outbox pending count/oldest age | Phát hiện relay bị treo. |
| Change feed processor lag/lease health | Khả năng bắt kịp committed events. |
| Service Bus publish/consume failures | Bảo đảm luồng nghiệp vụ end-to-end. |

### Azure Monitor và diagnostics

Tùy cấu hình, Azure Monitor cung cấp metrics và diagnostic logs của Cosmos DB account. Logs data plane có thể được xuất tới Log Analytics theo category/table được hỗ trợ. Không tự kết luận “không có lỗi” chỉ vì workspace chưa bật diagnostic settings hoặc có ingestion delay.

Tránh ghi toàn bộ document bodies vào observability vì có thể chứa PII, payment metadata hoặc internal identifiers nhạy cảm. Ghi **IDs đã được xử lý theo chính sách** và status/latency đủ để điều tra.

## 37. Runbook: Batch 409 vì client retry

**Hiện tượng:** khách hàng bấm “Đặt hàng”, API timeout. Khi bấm lại, transaction báo 409 Conflict.

### Điều tra

1. Ghi requestId, orderId và thời điểm UTC.
2. Kiểm tra batch-level và per-operation statuses.
3. Xác minh đúng Cosmos account/container/partition key.
4. Point-read Order theo key và ID.
5. Point-read OutboxEvent theo cùng key.
6. So payload/business operation ID hiện có với request retry.
7. Xác nhận Order + Outbox có đồng bộ trạng thái hay không.
8. Không tạo outbox event ID mới chỉ để tránh 409.

### Hướng xử lý

- Nếu batch trước **đã commit cùng nội dung**, trả kết quả idempotent theo API contract.
- Nếu ID bị dùng cho payload khác, trả conflict nghiệp vụ, không overwrite.
- Nếu transaction chưa commit, chỉ retry an toàn với IDs ổn định.
- Nếu còn ambiguous do network, trả trạng thái có thể truy vấn và chạy reconciliation.
- Theo dõi tỷ lệ 409 tăng bất thường do client retry storms.

**Bài học:** 409 có thể là tín hiệu retry đã xảy ra sau commit; nhưng cần **xác minh state**, không tự coi mọi 409 là thành công.

## 38. Runbook: 412 ETag và xử lý tranh chấp trạng thái

**Hiện tượng:** Worker A và B cùng cập nhật Order Pending sang Paid/Cancelled. Một batch trả 412.

### Điều tra

1. Đọc lại Order và ETag mới.
2. Xem current status và business operation IDs.
3. Xác định transition hợp lệ theo state machine.
4. Không dùng Replace không If-Match để ghi đè.
5. Nếu một worker đã xử lý cùng operation, trả kết quả idempotent.
6. Nếu operation của worker thua không còn hợp lệ, đưa vào conflict workflow/alert theo nghiệp vụ.

### Hướng xử lý

- Retry chỉ sau khi **re-read and recompute**, không dùng body cũ.
- Nếu hai transitions loại trừ nhau, chỉ một được chấp nhận.
- Tạo OutboxEvent **cùng batch** với transition được commit.
- Đảm bảo không publish event về transition đã bị 412 rollback.
- Đo conflict rate nếu concurrency tăng cao.

**Bài học:** Atomicity ngăn partial commit, còn ETag giúp tránh **lost update giữa các transactions**.

## 39. Runbook: 429 dù tổng RU/s nhìn còn dư

**Hiện tượng:** API có 20.000 RU/s provisioned và báo cáo tổng utilization chưa quá cao, nhưng một nhóm Orders liên tục gặp 429.

### Giả thuyết

- Nhiều writes tập trung vào một logical partition key (hot key).
- Indexing/update cost của một loại item tăng.
- Một physical partition đang quá tải dù tổng throughput còn.
- Batch quá lớn hoặc retry storm.
- Một outbox relay đồng thời cập nhật cùng key quá thường xuyên.

### Hướng xử lý

1. Xem 429 diagnostics và partition-level statistics khi có.
2. Kiểm tra top keys theo RU/write rate.
3. So payload size, operations/batch và indexing.
4. Giảm retries đồng thời; dùng backoff.
5. Tối ưu number of writes, batch content và event frequency.
6. Nếu key design sai, lập kế hoạch **data migration/new container**; không chỉ thay partition key path bằng một lệnh update.
7. Cân nhắc tăng throughput nếu bottleneck là capacity thực sự và ngân sách cho phép.
8. Test lại latency/429 và business consistency.

**Bài học:** tăng RU tổng không chữa được mọi hotspot; partition design là yếu tố cốt lõi.

## 40. Thực hành: nguyên tử hóa Order + Outbox

**Bối cảnh:** công ty có Cosmos DB account lab API for NoSQL. Orders API cần ghi hai documents trong một logical partition và chuẩn bị phát event qua một relay riêng.

### Tài nguyên và dữ liệu

| Thành phần | Giá trị |
|---|---|
| Database | `commerce` |
| Container | `orders` |
| Partition key path | `/orderScope` |
| Order scope | `tenant-lab|ORD-LAB-1042` |
| Order ID | `order:ORD-LAB-1042` |
| Outbox ID | `outbox:evt-lab-1042-created` |
| Order status | `Pending` |
| Event type | `OrderPlaced` |
| SDK | Azure Cosmos DB for NoSQL .NET SDK |
| Authentication | Managed identity / DefaultAzureCredential được cấp quyền lab |
| Rủi ro bị cấm | Không dùng dữ liệu thật, không in credential/PII |

### Nhiệm vụ

1. Vẽ Account → Database → Container → logical partition → hai documents.
2. Giải thích vì sao cùng physical partition chưa đủ điều kiện ACID batch.
3. Tạo container với `/orderScope` hoặc xác minh container lab đã tồn tại.
4. Chọn partition key value ổn định cho một đơn hàng.
5. Tạo Order và Outbox bằng một Transactional Batch.
6. Kiểm tra response.IsSuccessStatusCode, per-operation status và RequestCharge.
7. Point-read hai items đúng partition key.
8. Chạy lại batch cùng IDs và giải thích 409/idempotent outcome.
9. Dựng một batch conflict có outbox ID mới; chứng minh rollback.
10. Thử cố tình đặt `orderScope` khác nhau giữa hai items; ghi expected failure.
11. Sửa Order bằng Replace với IfMatch ETag và tạo outbox OrderPaid cùng batch.
12. Mô phỏng hai workers đọc cùng ETag; giải thích vì sao một 412.
13. Tính write RU/s cần thiết từ RequestCharge và transaction rate đo được.
14. Giải thích tại sao không thể tạo transaction atomic giữa hai Orders khác key.
15. Thiết kế change feed/outbox relay gửi Service Bus sau commit.
16. Giải thích trường hợp relay publish thành công rồi crash trước khi đánh dấu Sent.
17. Thêm idempotency key ở consumer để ngăn side effect trùng.
18. Viết alerts cho 429, conflict rate, outbox age và lag.
19. Đề xuất schema khi một tenant có 100.000 Orders, tránh hot key tenantId.
20. Mô tả ảnh hưởng nếu dùng một HPK gồm tenantId/orderId.
21. Chạy negative test trên môi trường lab, không sửa Production.
22. Tổng hợp bằng chứng và dọn tài nguyên lab theo quyền.

### Sơ đồ mong đợi

```text
POST /orders (requestId cố định)
         |
         v
Validate schema + tenant authorization
         |
         v
TransactionalBatch (key tenant-lab|ORD-LAB-1042)
         |
         +-- Create Order
         |
         +-- Create OutboxEvent
         |
         v
     Commit atomic
         |
         +---- Failed → không item mới nào được commit
         |
         +---- Succeeded → response accepted
                             |
                             v
                       Change Feed Relay
                             |
                             v
                         Service Bus
                             |
                             v
                      Idempotent consumer
```

### Đáp án định hướng

- **Hai items một key:** Batch có thể thực thi ACID.
- **Hai items khác key:** Batch không được dùng như một transaction xuyên partitions.
- **Create lại cùng ID:** xung đột 409; xác minh dữ liệu đã tồn tại và business request trùng hay khác.
- **ETag 412:** một worker khác đã đổi item; đọc lại và tính transition.
- **Timeout sau commit:** có khả năng ambiguous; dựa vào point reads và stable IDs.
- **Outbox:** giúp DB commit Order+Event record nguyên tử; Service Bus publish vẫn là bước riêng có thể lặp.
- **RU:** đo trên request thực, không suy ra từ số thao tác đơn giản.
- **Partition key:** chọn theo aggregate và scale; tránh một tenant khổng lồ trong một logical key.
- **Bảo mật:** data-plane RBAC/identity + network + app tenant authorization.

### Tiêu chí nghiệm thu

1. Có **một batch thành công** và hai items tồn tại với cùng key.
2. Có **một batch lỗi có chủ đích** và không xuất hiện item mới được cho là “commit nửa chừng”.
3. Có ví dụ ETag chống lost update.
4. Có cơ chế idempotency khi client retry sau timeout.
5. Có phân biệt transaction database với publish message ngoài database.
6. Có số liệu RU/latency và cách xác minh ngưỡng 429.
7. Không để credential thật hoặc tài liệu nhạy cảm trong source/logs.
8. Có hướng xử lý khi cần thao tác xuyên nhiều logical partitions.

## 41. Câu hỏi tự kiểm tra

**Câu 1.** Cosmos DB for NoSQL Transactional Batch có phạm vi transaction rộng đến đâu?

**Đáp án:** Các point operations thuộc **cùng logical partition key đầy đủ** trong **cùng container**.

**Câu 2.** Hai logical partitions nằm trên cùng physical partition có được đưa vào một batch atomic không?

**Đáp án:** Không. Physical partition không mở rộng ACID scope qua hai logical keys.

**Câu 3.** Cùng một `id` ở hai partition key khác nhau có nghĩa là cùng một document không?

**Đáp án:** Không. Item identity/point lookup gắn với partition key và ID.

**Câu 4.** Vì sao thiết kế Order và Outbox cùng `orderScope` hữu ích?

**Đáp án:** Cho phép ghi hai documents nguyên tử bằng Transactional Batch, giảm rủi ro Order commit mà thiếu outbox.

**Câu 5.** Có thể gọi Service Bus trong Transactional Batch để cùng ACID commit với Order không?

**Đáp án:** Không. Service Bus nằm ngoài phạm vi Cosmos DB transaction; cần outbox/relay và idempotency.

**Câu 6.** Batch thất bại do Create Order trùng ID, OutboxEvent ở operation sau có được commit độc lập không?

**Đáp án:** Không. Transaction rollback toàn batch.

**Câu 7.** Mã 424 trên các operations khác trong một batch thường gợi ý điều gì?

**Đáp án:** Chúng bị ảnh hưởng do một operation khác thất bại. Tìm mã lỗi gốc như 409/412 trước.

**Câu 8.** Batch thành công có nghĩa change feed relay đã publish event thành công không?

**Đáp án:** Không. Commit trong Cosmos DB và publish qua Service Bus là hai bước tách biệt.

**Câu 9.** ETag giúp ngăn lỗi gì?

**Đáp án:** Optimistic concurrency giúp phát hiện item đã bị thay đổi, tránh lost update khi dùng IfMatch.

**Câu 10.** Transactional Batch tự bảo vệ business decision được tính từ một read cũ bên ngoài batch không?

**Đáp án:** Không. Cần ETag, điều kiện hoặc thiết kế transaction logic thích hợp.

**Câu 11.** 412 có nên được giải bằng cách bỏ IfMatch và retry lại write cũ không?

**Đáp án:** Không. Phải đọc state mới và xác nhận transition còn hợp lệ.

**Câu 12.** 409 sau timeout có thể xảy ra nếu request trước đã commit không?

**Đáp án:** Có. Hãy kiểm tra items và business IDs trước khi quyết định trả kết quả idempotent.

**Câu 13.** Dùng Upsert cho outbox event có thể tạo rủi ro gì?

**Đáp án:** Retry có thể ghi đè event đã có và làm mờ tín hiệu duplicated operation; Create với stable ID thường phù hợp hơn cho sự kiện chỉ tạo một lần.

**Câu 14.** Vì sao `/status` là partition key không tốt cho Order?

**Đáp án:** Status thay đổi theo vòng đời; partition key của item không thể sửa trực tiếp như một field thường.

**Câu 15.** Với HPK `(/tenantId, /orderId)`, hai Orders của cùng tenant có chung transactional scope không?

**Đáp án:** Không nếu orderId khác. Cần cùng **full hierarchical key tuple**.

**Câu 16.** Transactional Batch có tự thực hiện một SQL query cross-partition trước khi commit không?

**Đáp án:** Không. API batch dành cho point operations được hỗ trợ trong một logical key.

**Câu 17.** Một batch có một HTTP call có nghĩa chỉ tốn 1 RU không?

**Đáp án:** Không. RU phụ thuộc số operations, item size, indexing và workload; đo RequestCharge.

**Câu 18.** Vì sao 429 vẫn có thể xuất hiện khi tổng RU của container chưa hết?

**Đáp án:** Một key/physical partition có thể hot, hoặc capacity và phân phối throughput không đều.

**Câu 19.** Snapshot isolation của Transactional Batch có biến mọi cross-region read thành strongly consistent không?

**Đáp án:** Không. Consistency level, region routing và replication visibility là những vấn đề khác.

**Câu 20.** Nếu relay đã publish rồi crash trước khi ghi Sent, điều gì xảy ra?

**Đáp án:** Event có thể được publish lại; consumer cần idempotency và sự kiện có ID ổn định.

**Câu 21.** Bulk operations trên nhiều partitions có giống một Transactional Batch không?

**Đáp án:** Không. Bulk tối ưu throughput nhưng không tạo atomicity toàn bộ across partitions.

**Câu 22.** Stored procedure có vượt được phạm vi logical partition không?

**Đáp án:** Không. Transactional stored procedure cũng bị giới hạn trong một logical partition theo API for NoSQL.

**Câu 23.** Nếu muốn chuyển điểm thưởng giữa hai accounts ở hai keys khác nhau, có dùng một Batch atomic được không?

**Đáp án:** Không. Cần thiết kế saga/compensation hoặc chọn một data model/system bảo đảm được transaction theo yêu cầu.

**Câu 24.** Có phải chỉ biết partition key là được phép đọc Order của tenant khác?

**Đáp án:** Không. Partition key không phải authorization; cần xác thực và kiểm tra quyền tenant trong ứng dụng và data-plane policies.

**Câu 25.** Nếu một JSON document dùng sai tên field partition key, SDK có tự tìm vị trí đúng để giữ atomicity không?

**Đáp án:** Không. Field/key mismatch sẽ gây lỗi; phải thống nhất schema và container definition.

**Câu 26.** Có nên bật retry vô hạn cho mọi batch 429 hoặc timeout không?

**Đáp án:** Không. Cần backoff, giới hạn số lần và idempotency/read-after-error; retry storms có thể tăng tải và chi phí.

**Câu 27.** Vì sao không nên xem transaction thành công là bằng chứng payment đã hoàn tất?

**Đáp án:** Batch chỉ commit dữ liệu trong Cosmos DB; payment provider, broker và downstream có kết quả độc lập.

**Câu 28.** Nếu bị xóa nhầm Order trong batch rồi commit, atomicity có tự phục hồi Order về trạng thái cũ không?

**Đáp án:** Không. Atomicity đảm bảo cùng commit/rollback, không tự làm backup. Cần restore/recovery/change feed/audit theo kiến trúc.

**Câu 29.** Nên theo dõi những chỉ số nào để kiểm tra Transactional Batch vận hành tốt?

**Đáp án:** Success/failure rate, per-operation codes, latency, RU, 429, 409/412, hot partitions, outbox pending age và downstream processing status.

**Câu 30.** Khi nào nên thiết kế lại partition key thay vì cố mở rộng batch?

**Đáp án:** Khi transaction boundary không khớp aggregate, một key quá nóng/lớn, hoặc các nghiệp vụ cần atomicity nằm trên nhiều keys; lúc đó cần xem lại data model và saga/outbox.

**Tóm lại:** **Transactional Batch của Azure Cosmos DB for NoSQL** tạo một giao dịch ACID cho các **point operations trong cùng logical partition của một container**. Thiết kế thành công bắt đầu từ **partition key đúng aggregate**, kết hợp **ETag để chống lost update**, **stable IDs để xử lý retry**, **outbox + change feed** để kết nối tới hệ thống khác và **RU/hot-partition monitoring** để vận hành ổn định. Batch không phải distributed transaction, không thay thế backup hoặc idempotency. Khi hiểu chính xác phạm vi này, bạn có thể tạo những cập nhật nhiều document **nguyên tử, đo được và có khả năng phục hồi** mà không đánh đổi sai tính nhất quán nghiệp vụ.
