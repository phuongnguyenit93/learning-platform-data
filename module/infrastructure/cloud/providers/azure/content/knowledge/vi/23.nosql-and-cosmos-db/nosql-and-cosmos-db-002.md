# Account, database, container và mô hình dữ liệu tài liệu

Khi bắt đầu một ứng dụng với **Azure Cosmos DB**, đặc biệt là **Azure Cosmos DB for NoSQL**, câu hỏi không nên chỉ là “cần tạo bao nhiêu bảng?”. Cần biết **ứng dụng đọc và ghi những tài liệu nào, theo khóa nào, với tốc độ bao nhiêu**, rồi mới quyết định tổ chức account, database, container và items. Thiết kế document phù hợp có thể biến một màn hình đơn hàng cần nhiều JOINs thành một **point read**, nhưng thiết kế sai partition key hoặc nhúng quá nhiều dữ liệu có thể gây hot partition, HTTP 429, xung đột ghi và chi phí RU cao.

Bài học này thuộc chương **Dữ liệu NoSQL với Cosmos DB** trong module **CLOUD_PROVIDERS_AZURE**. Đây là một phần của lộ trình khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng, compute, lưu trữ và dữ liệu. Mục tiêu không chỉ tạo được tài nguyên mà còn biết thiết kế, triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure.

Trọng tâm là **API for NoSQL** và dữ liệu **JSON document**, với cấu trúc:

~~~text
Azure subscription
└── Resource group
    └── Cosmos DB account (API for NoSQL)
        ├── Database: commerce
        │   ├── Container: orders
        │   │   ├── Item: order-481
        │   │   └── Item: order-482
        │   ├── Container: customers
        │   └── Container: products
        └── Database: internal-tools
            └── Container: audit-events
~~~

> **Nguyên tắc:** Account là ranh giới dịch vụ/cấu hình toàn cục; database tổ chức các containers và có thể chia sẻ throughput; container định nghĩa partition key và nhiều chính sách dữ liệu; item là JSON document mang trường **id** và giá trị partition key. Thiết kế tốt bắt đầu từ **access patterns, partition distribution, transaction boundary và chi phí Request Unit (RU)**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **account**, **database**, **container**, **item**, **logical partition** và **physical partition**.
2. Giải thích JSON document, trường **id**, partition key, nested object, arrays, schemaVersion và metadata **_etag/_ts**.
3. So sánh Cosmos DB for NoSQL với cách dùng bảng, foreign key và JOIN của cơ sở dữ liệu quan hệ.
4. Thiết kế dữ liệu từ các tình huống đọc/ghi: **embed**, **reference**, denormalization, snapshot và materialized view.
5. Chọn partition key theo cardinality, phân phối tải, khả năng truy vấn, tính bất biến và phạm vi transaction.
6. Hiểu provisioned RU/s, autoscale, shared database throughput và serverless.
7. Dùng Azure CLI tạo account/database/container trong lab được phê duyệt, kiểm tra metadata và chi phí.
8. Dùng Java SDK v4 với Microsoft Entra credentials để create, point read, query, update/delete item.
9. Áp dụng ETag optimistic concurrency và transactional batch trong **cùng logical partition**.
10. Giải thích indexing, unique keys, TTL, Change Feed và consistency levels.
11. Thiết kế bảo mật data-plane RBAC, networking, backup/DR, monitoring RU/429 và migration.
12. Đánh giá ví dụ Orders–Customers–Inventory trước production.

## 2. Mô hình tư duy: Cosmos DB for NoSQL khác RDBMS thế nào?

**Azure Cosmos DB** là họ dịch vụ dữ liệu do Azure quản lý với những API/mô hình được hỗ trợ khác nhau. Trong bài này, **API for NoSQL** lưu dữ liệu dưới dạng **JSON items** và truy vấn bằng ngôn ngữ SQL-like dành cho JSON, không phải T-SQL của Azure SQL Database.

| Tiêu chí | Cơ sở dữ liệu quan hệ, ví dụ Azure SQL | Cosmos DB for NoSQL |
|---|---|---|
| Đơn vị dữ liệu | Table/row | Container/JSON item |
| Schema | Cột và constraint | JSON linh hoạt, ứng dụng phải kiểm soát schema contract |
| Liên kết | Foreign keys và JOIN | Embed/reference, query trong item; không có arbitrary cross-container JOIN |
| Truy cập tối ưu thường gặp | Indexed SQL queries | Point read bằng **id + partition key** |
| Phân vùng | Có thể có nhưng không phải mọi bảng cần chọn key | Partition key là quyết định kiến trúc cốt lõi |
| Atomic transaction | Trong database theo transaction engine | Các thao tác thường atomic trong **một logical partition** |
| Năng lực | vCore/DTU/IOPS... | RU/s, storage, region/replication và chi phí liên quan |
| Thay đổi cấu trúc | Schema migrations | Item schemaVersion, đọc nhiều phiên bản, migration dữ liệu |
| Analytics | JOIN, relational reporting | Query/document projections; thường kết hợp stream/analytical platform |

Cosmos DB hữu ích khi workload có những **đường truy cập biết rõ partition key**, cần JSON linh hoạt và scale phân tán. Nếu hầu hết tác vụ là JOIN quan hệ phức tạp giữa nhiều thực thể hoặc transaction trải rộng, **Azure SQL Database/PostgreSQL** có thể hợp lý hơn.

Không nên giả định:

- “NoSQL không cần schema”.
- “Tất cả queries đều rẻ”.
- “Mọi document đều luôn ở một physical partition”.
- “Cosmos DB có distributed ACID transaction giữa nhiều containers”.
- “Cứ chọn Strong consistency là tốt nhất”.
- “Tạo thêm RU/s sẽ sửa được mọi hot partition”.

## 3. Cấu trúc account → database → container → item

~~~mermaid
flowchart TB
    SUB["Azure subscription"] --> RG["Resource group"]
    RG --> ACCOUNT["Cosmos DB account<br/>API, endpoint, regions, consistency, security"]
    ACCOUNT --> DB1["Database commerce"]
    ACCOUNT --> DB2["Database internal-tools"]
    DB1 --> ORDERS["Container orders<br/>partition key /tenantId"]
    DB1 --> CUSTOMERS["Container customers<br/>partition key /tenantId"]
    DB1 --> PRODUCTS["Container products<br/>partition key /categoryId"]
    ORDERS --> O1["JSON item order-481"]
    ORDERS --> O2["JSON item order-482"]
    CUSTOMERS --> C1["JSON item customer-91"]
~~~

### 3.1. Account

**Account** là tài nguyên Azure có endpoint kết nối và các thiết lập như:

- API được chọn lúc tạo (trọng tâm ở đây là NoSQL).
- Region gốc, các vùng bổ sung/replication và failover.
- Default consistency level.
- Network access, firewall, private endpoints theo tính năng.
- Identity, keys, control-plane/data-plane security.
- Throughput model/billing capabilities theo lựa chọn tạo account.
- Monitoring, backup và thông tin quản trị.

Một endpoint Cosmos DB for NoSQL thường có dạng:

~~~text
https://<cosmos-account-name>.documents.azure.com:443/
~~~

Tên account phải thỏa điều kiện duy nhất và naming constraints của dịch vụ. Account không phải là một document hay table.

### 3.2. Database

**Database** nhóm các containers cùng ứng dụng/domain, ví dụ **commerce**. Nó có thể mang **shared provisioned throughput**, cho những containers được cấu hình dùng chung RU/s.

Database **không tự là một dedicated compute cluster** hay một trust boundary độc lập tuyệt đối. Những quyền truy cập thực tế còn liên quan account, data-plane RBAC, scope, network và app authorization.

### 3.3. Container

**Container** là tập các JSON items cùng quy tắc partitioning. Ở đây thường xác định:

- Container name/id.
- **Partition key path** (ví dụ **/tenantId**).
- Indexing policy.
- Unique key policy, nếu cần.
- TTL mặc định/áp theo item, nếu bật.
- Throughput riêng hoặc dùng shared throughput.
- Các thiết lập tính năng được dịch vụ hỗ trợ.

Các items trong container được Cosmos DB phân bố lên physical partitions theo partition key và nhu cầu scale.

### 3.4. Item

**Item** là tài liệu JSON. Để đọc trực tiếp một item, thường cần **id** và giá trị **partition key** của nó.

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "status": "PAID",
  "currency": "VND",
  "totalMinorUnits": 350000,
  "createdAtUtc": "2026-11-20T03:03:20Z",
  "customer": {
    "customerId": "customer-91",
    "displayName": "Khach hang mau"
  },
  "lines": [
    { "sku": "SKU-12", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ]
}
~~~

Không cần tạo schema SQL với các cột trước khi tạo document, nhưng phải **validate fields/versions/types** trong ứng dụng.

## 4. Chọn đúng API và dịch vụ

Có những trải nghiệm Cosmos DB khác nhau, ví dụ **API for NoSQL**, **API for MongoDB** và những API/mô hình khác theo dịch vụ hiện hành.

| Yêu cầu | Cân nhắc |
|---|---|
| Dữ liệu JSON và Cosmos partition/query model | Cosmos DB **for NoSQL** |
| Ứng dụng cần MongoDB wire protocol/tooling | Mô hình **Cosmos DB for MongoDB** tương ứng |
| Nhiều quan hệ, JOIN và transactions quan hệ phức tạp | Azure SQL/PostgreSQL |
| Graph traversals là trọng tâm | Graph-capable database/API phù hợp |
| Báo cáo dài hạn cần phân tích dữ liệu lớn | Fabric/Synapse/Data Lake/ADX hoặc đường analytical tương ứng |

Không áp dụng cú pháp Java SDK NoSQL hoặc lệnh **az cosmosdb sql container** cho một account dùng API khác mà không xác minh tính tương thích.

## 5. Account: những quyết định trước khi tạo

1. **Region và data residency:** ứng dụng chạy ở đâu, dữ liệu được lưu ở đâu, user latency mục tiêu?
2. **Availability:** chỉ một region hay nhiều read/write regions theo khả năng hỗ trợ?
3. **Consistency:** Session, Eventual, Strong... theo nhu cầu nghiệp vụ.
4. **Billing/throughput mode:** provisioned manual/autoscale hay serverless.
5. **Network:** public access hạn chế hay Private Endpoint.
6. **Credentials:** Microsoft Entra identity và quyền dữ liệu, tránh account key trong code.
7. **Backup/restore:** mô hình được hỗ trợ và yêu cầu RPO/RTO.
8. **FinOps:** owner, tags, budget và theo dõi chi phí.

### 5.1. Consistency không thể chọn tùy tiện

Cosmos DB for NoSQL có các mức **Strong**, **Bounded staleness**, **Session**, **Consistent prefix**, **Eventual** với những bảo đảm đọc khác nhau.

Mức mặc định được cấu hình cấp account và các requests/SDK có thể yêu cầu những mức phù hợp trong phạm vi cho phép; không mặc nhiên được chọn mức **mạnh hơn** account config bằng một dòng code.

### 5.2. Multi-region không thay backup

Replication/failover giúp availability, nhưng một bug xóa nhầm tài liệu hoặc một thay đổi sai trong dữ liệu có thể được replicate. Cần backup/restore, audit và quy trình DR riêng.

### 5.3. Serverless hay provisioned?

**Provisioned throughput** cấp khả năng xử lý theo **RU/s** tại database hoặc container. **Serverless** tính theo request RU theo mô hình/giới hạn riêng, phù hợp một số ứng dụng nhỏ/không đều.

Không tự cho rằng có thể đổi qua lại serverless và provisioned trên cùng account mà không cần migration; kiểm tra quyết định mode ngay từ đầu.

## 6. Database và phân bổ throughput

Một ví dụ:

~~~text
Database: commerce
    Container orders
    Container customers
    Container products

Database: internal-tools
    Container audit-events
~~~

### 6.1. Shared database throughput

Đặt một RU/s pool ở **database scope**, cho những containers được cấu hình dùng pool này.

**Ưu điểm:** nhiều containers nhỏ có thể dùng chung capacity, giảm overhead quản trị.

**Đánh đổi:** một container nóng có thể chiếm ngân sách khiến container khác bị throttle. Cần theo dõi per-container, không chỉ tổng RU.

### 6.2. Dedicated container throughput

Đặt RU/s riêng cho một container nhiều traffic/nhu cầu SLO riêng. Dễ phân bổ ngân sách nhưng tổng mức RU/s/chi phí tối thiểu có thể cao hơn.

### 6.3. Autoscale

Autoscale cho phép Cosmos DB điều chỉnh throughput trong phạm vi đã cấu hình theo mô hình hỗ trợ. Nhưng không đồng nghĩa “không có traffic thì chi phí bằng 0”. Billing theo max/tiêu chí của autoscale và tier thực tế cần được kiểm tra bằng bảng giá.

| Tình huống | Gợi ý mô hình |
|---|---|
| Nhiều containers nhỏ, traffic rải rác | Shared database throughput |
| Orders rất lớn, Products rất nhỏ | Dedicated throughput cho Orders, pool nhỏ/riêng cho Products |
| Traffic có peak theo giờ | Autoscale nếu phù hợp |
| Lab nhẹ, requests ít/không đều | Xem serverless và các hạn chế |
| Report toàn bộ tenants liên tục | Cân nhắc analytical/read model, không chỉ tăng RU/s |

## 7. Container: đơn vị quan trọng nhất của mô hình

Partition key path, unique key policy và indexing policy của một container thường là các quyết định khó đổi khi đã có nhiều dữ liệu.

### 7.1. Một container có thể chứa nhiều loại document

~~~text
Container: commerce-data
Partition key: /tenantId

type = order
type = customer
type = cart
type = audit
~~~

Có thể hợp lý nếu các types chia sẻ query patterns/transaction boundary. Nhưng không nên gộp mọi domain nếu:

- TTL khác nhau.
- Quyền truy cập khác nhau.
- Một loại tài liệu tạo hot traffic.
- Unique key constraints khác.
- Indexing và retention needs khác.

**Không tạo một container cho mỗi Java class theo phản xạ**, cũng không coi một container duy nhất là lựa chọn đúng cho mọi NoSQL system.

### 7.2. Quy tắc đặt tên

~~~text
Account       = cosmos-commerce-prod-sea
Database      = commerce
Container     = orders
Partition key = /tenantId
Document type = order
Schema        = schemaVersion: 2
~~~

Tên ví dụ phải được kiểm tra tính hợp lệ và availability; không phải tài nguyên đã tạo trong subscription của bạn.

## 8. Document schema và metadata hệ thống

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "schemaVersion": 2,
  "orderNumber": "HN-2026-00481",
  "status": "PAID",
  "createdAtUtc": "2026-11-20T03:03:20Z",
  "updatedAtUtc": "2026-11-20T03:10:00Z",
  "currency": "VND",
  "totalMinorUnits": 350000,
  "customerSnapshot": {
    "id": "customer-91",
    "displayName": "Khach hang mau"
  },
  "lines": [
    { "sku": "SKU-12", "nameSnapshot": "Ao thun", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "nameSnapshot": "Van chuyen", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ],
  "labels": ["online", "paid"]
}
~~~

### 8.1. Các trường quan trọng

| Trường | Nguồn | Công dụng |
|---|---|---|
| **id** | Ứng dụng | Identifier của item trong logical partition |
| **tenantId** | Ứng dụng | Giá trị partition key khi path là /tenantId |
| **type** | Ứng dụng | Phân biệt loại JSON item |
| **schemaVersion** | Ứng dụng | Quản lý tiến hóa schema |
| **status** | Ứng dụng | Trạng thái nghiệp vụ |
| **createdAtUtc** | Ứng dụng | Timestamp theo contract ISO 8601 |
| **lines** | Ứng dụng | Array dữ liệu nhúng |
| **_etag** | Cosmos DB | Optimistic concurrency token |
| **_ts** | Cosmos DB | Timestamp do dịch vụ quản lý |
| **_rid**, **_self**... | Cosmos DB | Metadata nội bộ |

Không tự thay đổi metadata hệ thống hoặc dùng **_rid** như business ID. Không tự kết luận **_ts** là createdAtUtc; nó liên quan trạng thái metadata được dịch vụ quản lý.

### 8.2. Schema linh hoạt vẫn cần validation

Hai items sau có thể cùng tồn tại nhưng khó xử lý:

~~~json
{"id":"o-1","tenantId":"t-1","status":"PAID","totalMinorUnits":200000}
{"id":"o-2","tenantId":"t-1","state":"PAID","amount":"200000"}
~~~

Thiết kế cần:

- JSON Schema/application validators.
- Field required/optional rõ ràng.
- Kiểu thống nhất cho tiền, timestamp, enum.
- Schema version và backward-compatible readers.
- Contract tests giữa API/worker.
- Data migration khi đổi tên field.
- Không để null/missing values gây query sai.

### 8.3. Date và tiền

JSON không có kiểu Date chuyên biệt; dùng ISO 8601 UTC string hoặc một dạng timestamp có contract rõ. Với tiền, tránh floating-point không có quy ước làm tròn. Có thể dùng integer minor units hoặc decimal-as-string tùy currency/business contract.

### 8.4. Item không nên tăng vô hạn

Nếu embed hàng triệu audit events vào một order document:

- Point read trả dữ liệu quá lớn.
- RU cho write/read tăng.
- Cạnh tranh ETag khi nhiều worker cập nhật.
- Có nguy cơ vượt giới hạn item size (thường tối đa khoảng **2 MiB** với NoSQL; xác minh quota hiện hành).
- Không có lifecycle riêng cho history.

Tách history thành những items, cùng logical partition khi cần transaction hoặc container khác khi lifecycle/throughput khác.

## 9. Logical partition và physical partition

### 9.1. Logical partition

Container có partition key path **/tenantId** tạo các logical partitions theo **giá trị**:

~~~text
tenant-hcm:
    order-481
    order-482
    order-483

tenant-hn:
    order-601
    order-602
~~~

Các items có cùng partition key value thuộc **một logical partition**. Đây cũng là transaction boundary quan trọng.

### 9.2. Physical partition

Cosmos DB bố trí các logical partitions lên **physical partitions** mà dịch vụ quản lý. Bạn không tự tạo **P0/P1** rồi gán items bằng code.

~~~mermaid
flowchart TB
    C["Container orders"] --> L1["Logical partition tenant-hcm"]
    C --> L2["Logical partition tenant-hn"]
    C --> L3["Logical partition tenant-dn"]
    L1 --> P1["Physical partition A"]
    L2 --> P1
    L3 --> P2["Physical partition B"]
~~~

Sơ đồ chỉ minh họa. Mapping thực tế có thể thay đổi khi Cosmos DB scale.

### 9.3. Id không nhất thiết duy nhất toàn container

Trong container partitioned:

~~~text
(id=order-481, partitionKey=tenant-hcm) → Item A
(id=order-481, partitionKey=tenant-hn)  → Item B
~~~

Hai items có cùng **id** nhưng nằm trong logical partitions khác nhau có thể tồn tại. Khi point read, cần **đúng cả id và partition key**.

### 9.4. Partition key không chỉ là index

Partition key ảnh hưởng:

- Định tuyến query/read.
- Phân phối storage và RU.
- Hot partition và throughput scale.
- Atomic transaction boundary.
- Khả năng tìm item khi API chỉ biết một business ID.
- Phương án migration khi business key thay đổi.

Chọn sai partition key thường khó sửa hơn tạo thiếu một index.

## 10. Năm tiêu chí chọn partition key

1. **Cardinality cao:** đủ nhiều giá trị.
2. **Tải phân phối đều:** tránh tập trung writes/reads vào một giá trị.
3. **Có trong truy vấn phổ biến:** app biết partition key khi thực hiện point read/single-partition query.
4. **Ổn định:** không phải business field thường thay đổi.
5. **Phù hợp transaction:** dữ liệu cần atomic updates nằm cùng logical partition khi hợp lý.

| Candidate key | Lợi ích | Rủi ro |
|---|---|---|
| **/status** | Lọc trạng thái có vẻ thuận tiện | Chỉ vài giá trị NEW/PAID; cực nóng và lưu trữ lớn |
| **/createdDate** | Phục vụ một số báo cáo ngày | Ngày hiện tại luôn hot |
| **/tenantId** | Đa thuê bao, tenant-scoped API, transaction cùng tenant | Tenant rất lớn gây hot partition |
| **/orderId** | Cardinality lớn, phân phối tốt theo order | Query tất cả orders của tenant có thể cross-partition |
| **/customerId** | Lấy lịch sử orders của customer | Reporting theo tenant và khách hàng rất lớn |
| **Synthetic bucket** | Chủ động phân phối tải | App cần mapping, query tenant quét nhiều buckets |

Không chọn **/status** chỉ vì ứng dụng hay filter theo status. Partition key cần cân bằng **query routing và khả năng scale**.

### 10.1. Multi-tenant /tenantId

Nếu mọi API đều biết tenantId, **/tenantId** là một lựa chọn dễ hiểu. Nhưng phải đánh giá tenant rất lớn có thể vượt capacity hoặc storage cho một logical partition.

Với nhu cầu lớn, cân nhắc:

- Hierarchical partition key.
- Synthetic key như tenant + bucket/order prefix.
- Tách những tenant lớn ra container/account khác khi cần.
- Materialized view/lookup container để hỗ trợ access patterns.
- Đánh giá giới hạn logical partition và throughput thật.

### 10.2. Hierarchical partition key

Một số cấu hình API for NoSQL hỗ trợ hierarchical partition keys gồm nhiều cấp, ví dụ:

~~~text
Cấp 1: /tenantId
Cấp 2: /orderId
~~~

Nó có thể giúp phân bố tenant lớn mà vẫn phục vụ truy vấn theo prefix theo tính năng hỗ trợ. Nhưng logical partition đầy đủ sẽ dùng **các thành phần key theo định nghĩa**, không tự coi mọi items cùng tenant có thể tham gia một transactional batch nếu cấp thứ hai khác nhau.

Đây không phải một tùy chọn nên bật mà không xem SDK/API/feature compatibility và kế hoạch migration. Phải benchmark theo query và transaction boundaries thật.

### 10.3. Không chọn field thường đổi làm partition key

Nếu partition key là **/country** rồi khách chuyển quốc gia, bạn không thể coi việc đổi field như UPDATE column trong cùng partition. Thường cần tạo item trong partition mới, xử lý reference/idempotency rồi xóa item cũ theo workflow.

Ưu tiên key ổn định như tenantId/orderId thay vì status hoặc account tier.

## 11. Access patterns trước data model

Viết bảng tác vụ:

| Access pattern | Tần suất | Input có sẵn | Mục tiêu |
|---|---:|---|---|
| Lấy order detail | Rất cao | tenantId + orderId | Point read một item |
| Xem 20 orders mới nhất trong tenant | Cao | tenantId | Single-partition indexed query |
| Cập nhật order status | Cao | tenantId + orderId | Conditional patch/replace |
| Lấy customer profile | Trung bình | tenantId + customerId | Point read customer |
| Hiển thị giá tại thời điểm bán | Cao | orderId + tenantId | Embed price snapshot |
| Tìm order theo email | Trung bình | email | Lookup/read model theo email |
| Báo cáo tất cả tenants theo tháng | Batch | Date interval | Analytical projection/pipeline |
| Audit status history | Trung bình | orderId | Separate event items |
| Cập nhật inventory SKU | Rất cao | warehouseId + sku | Domain/partition riêng |

### 11.1. API đã biết id và partition key

~~~text
GET /tenants/tenant-hcm/orders/order-481
~~~

Với container **orders** có **/tenantId** và item **id=order-481**, app có thể point read trực tiếp.

### 11.2. API chỉ có orderId

~~~text
GET /orders/order-481
~~~

Nếu key là /tenantId, ứng dụng **thiếu giá trị định tuyến**. Các lựa chọn:

- Bắt buộc tenantId trong route/token hoặc request context.
- Tạo lookup **orderId → tenantId**.
- Chọn key khác nếu lookup by orderId là access pattern áp đảo.
- Chấp nhận cross-partition query với budget/telemetry khi hiếm.
- Có materialized lookup projection cập nhật qua Change Feed/outbox.

Đừng chọn partition key rồi mới phát hiện mọi request quan trọng thiếu key.

## 12. Embed hay reference?

### 12.1. Embed dữ liệu thuộc về order

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "lines": [
    { "sku": "SKU-12", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ]
}
~~~

Ưu điểm: một point read lấy cả order/lines, ít round trips, giá là snapshot tại lúc mua. Đánh đổi: item lớn, cạnh tranh ghi, khó xử lý arrays tăng liên tục.

### 12.2. Reference tới dữ liệu sống

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "customerId": "customer-91",
  "lineItemIds": ["line-1", "line-2"]
}
~~~

Ưu điểm: entities update/scale/lifecycle riêng. Đánh đổi: thêm round trips, ứng dụng phải phối hợp reads, không có JOIN tùy ý giữa containers.

### 12.3. Quy tắc chọn

**Embed** nếu dữ liệu nhỏ, bounded, thường đọc cùng, có lifecycle phụ thuộc và cần snapshot.

**Reference** nếu dữ liệu lớn hoặc tăng vô hạn, có nhiều nơi dùng chung, cập nhật riêng thường xuyên, access pattern/throughput/TTL/permission riêng.

Kết hợp là phổ biến: giữ **customerId** để liên kết hồ sơ sống và **customerNameSnapshot** trong order để phục vụ hóa đơn đúng thời điểm.

## 13. Order modeling: từ bảng sang document

### 13.1. Mô hình quan hệ ban đầu

~~~text
Orders(orderId, tenantId, customerId, status, createdAt)
OrderLines(lineId, orderId, sku, qty, price)
Customers(customerId, tenantId, name)
Products(sku, currentPrice)
OrderStatusHistory(eventId, orderId, eventTime)
~~~

Một màn hình order detail thường join nhiều bảng.

### 13.2. Document tối ưu đọc order detail

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "schemaVersion": 2,
  "customerId": "customer-91",
  "customerSnapshot": {
    "displayName": "Khach hang mau",
    "membershipTierAtPurchase": "GOLD"
  },
  "lines": [
    {
      "sku": "SKU-12",
      "nameSnapshot": "Ao thun",
      "quantity": 2,
      "unitPriceMinorUnits": 125000
    }
  ],
  "totalMinorUnits": 250000,
  "status": "PAID",
  "createdAtUtc": "2026-11-20T03:03:20Z"
}
~~~

Màn hình order detail có thể đọc một item. Catalog Product hiện tại vẫn tách vì giá/tồn kho thay đổi độc lập; order cần snapshot giá tại lúc mua.

### 13.3. Status history dạng event items

~~~json
{
  "id": "order-481-event-0001",
  "tenantId": "tenant-hcm",
  "orderId": "order-481",
  "type": "order-status-event",
  "eventType": "PAID",
  "eventTimeUtc": "2026-11-20T03:10:00Z"
}
~~~

Nếu order và audit event nằm trong **cùng container và logical partition**, có thể cân nhắc transactional batch; nếu ở **containers khác nhau**, không có arbitrary transaction xuyên chúng.

### 13.4. Denormalization cần quy tắc đồng bộ

Nếu customer đổi tên:

- Customer profile giữ tên hiện tại.
- Order snapshot có thể giữ tên đã hiển thị tại thời điểm mua.
- Nếu cần sửa snapshot theo nghiệp vụ, có version/audit.
- Nếu là read model không phải snapshot, cần projection update qua Change Feed/outbox.

Không xem denormalization là “sao chép nhưng không ai chịu trách nhiệm cập nhật”.

## 14. Query: point read, single-partition và cross-partition

### 14.1. Point read

~~~text
Container: orders
id: order-481
partitionKey: tenant-hcm

ReadItem(id, PartitionKey("tenant-hcm"))
~~~

Point read thường có độ trễ/RU tốt khi biết đúng khóa và item size hợp lý.

### 14.2. Query theo một tenant

~~~sql
SELECT c.id, c.status, c.createdAtUtc, c.totalMinorUnits
FROM c
WHERE c.tenantId = "tenant-hcm"
  AND c.type = "order"
  AND c.status = "PAID"
ORDER BY c.createdAtUtc DESC
~~~

Trong SDK, truyền partition key trong query options khi đã biết. Chú ý index/ORDER BY/pagination và đo RU.

### 14.3. Cross-partition query

~~~sql
SELECT * FROM c
WHERE c.status = "PAID"
~~~

Với partition key **/tenantId**, câu query có thể quét nhiều partitions; RU/latency có thể rất cao. Nếu báo cáo cross-tenant là nhu cầu thường xuyên, cân nhắc materialized view hoặc analytical store/ADX/Fabric/Synapse theo tính năng.

### 14.4. JOIN trong Cosmos SQL

~~~sql
SELECT c.id, line.sku, line.quantity
FROM c
JOIN line IN c.lines
WHERE c.tenantId = "tenant-hcm"
~~~

Đây là JOIN trên **array trong một item**, không phải arbitrary JOIN giữa containers **orders** và **products**.

## 15. RU/s, chi phí và HTTP 429

**Request Unit (RU)** là phép đo tài nguyên tiêu thụ bởi một thao tác: đọc, ghi, query, indexing và các công việc liên quan. Với provisioned throughput, cấp **RU/giây**.

| Thao tác | Đặc tính RU |
|---|---|
| Point read item nhỏ | Thường hiệu quả |
| Query có partition filter và index | Hiệu quả hơn truy vấn quét rộng |
| Cross-partition aggregate | Có thể tốn RU lớn |
| Write item lớn, nhiều indexed properties | Tốn RU hơn write item nhỏ |
| Update một field qua thay thế item | Có chi phí write và index |
| TTL/delete/change projection | Có overhead/tính năng riêng theo billing |

### 15.1. Ví dụ ước lượng RU

~~~text
Thử tải đo được:
  Point read: 5 RU/request
  Write:     12 RU/request

Peak:
  600 reads/s  → 600 × 5  = 3.000 RU/s
  100 writes/s → 100 × 12 = 1.200 RU/s

Tổng sơ bộ             ≈ 4.200 RU/s
~~~

Đây chỉ là dự toán; chưa tính queries, retries, indexing, cross-region và hot partitions. Không lấy ví dụ làm benchmark hay thông số giá của Azure.

### 15.2. Hot partition và 429

Một partition key rất nóng có thể bị throttle dù container còn RU ở các physical partitions khác. Khi gặp **429 Request Rate Too Large**:

1. Xem retry-after và SDK retry behavior.
2. Đo normalized RU consumption và nóng theo partition.
3. Kiểm tra query không có key, queries scan rộng.
4. Kiểm tra writes lớn/indexing policy.
5. Cân nhắc bounded concurrency/caching/batching.
6. Cân nhắc thay đổi partition strategy nếu thực sự có hot key.
7. Chỉ tăng provisioned RU sau khi hiểu bottleneck.

Không retry vô hạn hoặc tăng số workers vô giới hạn, vì có thể làm hiệu năng xấu hơn.

## 16. Indexing, unique keys và TTL

### 16.1. Indexing

Cosmos DB for NoSQL thường index nhiều property paths theo **default indexing policy**, cho phép query linh hoạt nhưng có overhead khi ghi.

- Loại những fields không bao giờ query khỏi index nếu thực sự giúp giảm write cost.
- Tạo **composite indexes** khi query nhiều ORDER BY fields cần.
- Kiểm tra query metrics/index metrics và RU charge.
- Không nhầm “có index status” với “cross-partition query trở thành single-partition”.

Ví dụ:

~~~sql
SELECT * FROM c
WHERE c.tenantId = "tenant-hcm"
ORDER BY c.status ASC, c.createdAtUtc DESC
~~~

có thể cần composite index phù hợp với fields/order và policy thực tế.

### 16.2. Unique key policy

Unique key giúp ràng buộc một hoặc nhiều property paths **trong logical partition** theo dịch vụ.

~~~text
Partition key /tenantId
Unique key /normalizedEmail

tenant-hcm + alice@example.invalid → duy nhất trong tenant-hcm
tenant-hn  + alice@example.invalid → có thể tồn tại riêng
~~~

Cần thiết kế khi tạo container: đổi unique key policy thường phải tạo container mới/migrate. Phải test case sensitivity, missing/null fields, collation/normalization.

### 16.3. TTL

Time to Live cho phép tự hết hạn items theo cấu hình container/item. Ví dụ:

~~~json
{
  "id": "session-481",
  "tenantId": "tenant-hcm",
  "type": "session",
  "ttl": 3600
}
~~~

Item TTL hoạt động khi container bật TTL phù hợp; giá trị thường theo giây. Việc hết hạn gắn với metadata do dịch vụ quản lý chứ không đơn thuần lấy **createdAtUtc** do ứng dụng gắn.

Phù hợp với session/cache/telemetry tạm; không bật TTL ngắn cho Orders hoặc audit phải lưu theo quy định.

## 17. Change Feed và consistency

### 17.1. Change Feed

**Change Feed** cho phép consumer đọc thay đổi tài liệu theo semantics/mode được hỗ trợ, phục vụ:

- Cập nhật search/read models.
- Đẩy dữ liệu sang analytical pipeline.
- Đồng bộ ứng dụng.
- Tạo projection cross-tenant.
- Event-driven processing sau khi item thay đổi.

Một projection cần idempotency, checkpoint và schema version. Hành vi với deletes, TTL và hình thức lịch sử thay đổi phụ thuộc **change feed mode**; không giả định mọi mode chứa toàn bộ before/after states.

### 17.2. Các consistency levels

| Level | Ý nghĩa khái niệm |
|---|---|
| **Strong** | Đọc thấy trạng thái mới nhất theo bảo đảm strong trong phạm vi hỗ trợ |
| **Bounded staleness** | Giới hạn độ trễ/staleness theo ngưỡng |
| **Session** | Các bảo đảm theo session, gồm read-your-writes khi dùng đúng session token |
| **Consistent prefix** | Quan sát tiền tố hợp lệ của chuỗi writes |
| **Eventual** | Replica hội tụ về sau, đọc có thể stale |

**Session** thường là lựa chọn cân bằng cho web APIs, nhưng phải hiểu session token khi request đi qua nhiều services/clients. **Strong** có những trade-off và giới hạn multi-region; không đặt Strong chỉ vì “dữ liệu quan trọng”.

### 17.3. Consistency không thay transaction

Ngay cả khi đọc Strong, hai workers vẫn có thể cạnh tranh ghi một item; cần ETag/conditional update. Ngược lại Session consistency không tự đảm bảo atomicity giữa Cosmos DB và Service Bus.

## 18. Transaction và optimistic concurrency

### 18.1. Transactional batch giới hạn trong một logical partition

Cosmos DB for NoSQL hỗ trợ **transactional batch** cho những thao tác dữ liệu **cùng container và cùng logical partition**, theo quota/API hỗ trợ.

Ví dụ:

~~~text
Container orders, partition key /tenantId

Logical partition tenant-hcm:
    Replace order-481: status=PAID
    Create order-481-event-0001: type=order-event

Transactional batch:
    Cả hai thao tác cùng commit hoặc cùng rollback
~~~

Nếu status history nằm trong container **audit** khác, không có nghĩa Cosmos DB sẽ bảo đảm atomic transaction xuyên hai containers. Cũng không có một transaction tự động bao trùm Cosmos DB, Azure SQL, Blob Storage và Service Bus.

### 18.2. ETag và If-Match

Hai workers cùng đọc một order:

~~~text
Worker A: đọc order-481, ETag=e1
Worker B: đọc order-481, ETag=e1

Worker A: replace If-Match e1 → thành công, ETag mới e2
Worker B: replace If-Match e1 → HTTP 412 Precondition Failed
~~~

Ứng dụng xử lý 412 bằng cách đọc lại trạng thái mới, kiểm tra business invariant, sau đó merge/retry có giới hạn hoặc báo conflict. **Không retry mù bằng upsert**: điều đó có thể ghi đè dữ liệu hợp lệ của worker khác.

### 18.3. Create, replace, patch và upsert không giống nhau

| Thao tác | Khi dùng | Rủi ro nếu dùng sai |
|---|---|---|
| **Create item** | Chỉ chấp nhận item chưa tồn tại | 409 khi id trùng trong logical partition |
| **Replace item** | Thay toàn item có kiểm soát | Bỏ sót fields mới của một reader có thể làm mất dữ liệu |
| **Patch item** | Đổi một số paths theo khả năng hỗ trợ | Cần kiểm tra preconditions/atomicity/concurrency |
| **Upsert item** | Tạo nếu mới, thay nếu đã tồn tại | Có thể che conflict hoặc overwrite fields |
| **Delete item** | Xóa theo policy | Cần cân nhắc audit, backup, legal retention |

Đối với lịch sử tài chính, thường không được phép ghi đè một event cũ chỉ để đạt trạng thái hiện tại; cần ledger/audit và idempotent business state.

## 19. Chuẩn bị thực hành Azure Cosmos DB for NoSQL

Bài lab sử dụng tài nguyên minh họa:

| Thiết lập | Giá trị ví dụ |
|---|---|
| Azure region | southeastasia |
| Resource group | rg-cosmos-lab |
| Account | cosmosorderslabxyz (tên phải duy nhất) |
| API | for NoSQL |
| Database | commerce |
| Container | orders |
| Partition key path | /tenantId |
| Throughput | 400 RU/s manual trên provisioned model, nếu được phép |
| Tenant test | tenant-hcm |
| Item test | order-481 |

**Điều kiện:**

1. Có subscription lab/budget và quyền tạo resource đã được phê duyệt.
2. Biết chủ sở hữu/account có tồn tại hay không; không ghi đè production.
3. Được cấp Azure Resource Manager role phù hợp để tạo account/database/container.
4. Nếu dùng Java Entra SDK, danh tính có **Cosmos DB data-plane role** phù hợp.
5. Có Java 17+, Maven và SDK version được dự án chọn.
6. Network/DNS/TLS tới Cosmos endpoint hoạt động; nếu dùng Private Endpoint, cấu hình đúng đường riêng.
7. Dữ liệu test không phải thông tin khách hàng thật.
8. Có phương án dọn lab; provisioned RU/s có thể tiếp tục phát sinh phí khi app không chạy.

Không cần tạo account mới nếu tổ chức đã cung cấp một account/database/container lab riêng phù hợp.

## 20. Azure CLI: tạo account, database và container

Ví dụ dùng **Azure Cloud Shell Bash** hoặc shell đã có Azure CLI. Đây là **thao tác có thể phát sinh chi phí**, chỉ thực hiện trên subscription lab đã duyệt.

### 20.1. Tạo resource group và account

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-cosmos-lab"
REGION="southeastasia"
ACCOUNT="<globally-unique-cosmos-account>"
DB="commerce"
CONTAINER="orders"

az group create \
  --name "$RG" \
  --location "$REGION"

az cosmosdb create \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --locations regionName="$REGION" failoverPriority=0 \
  --default-consistency-level Session
~~~

Ví dụ trên minh họa một **provisioned-throughput account**, không phải cú pháp tạo serverless. Serverless là account-level capability/model có lựa chọn và giới hạn riêng; cần xem cấu hình tạo phù hợp khi chọn mode đó.

Nếu account đã tồn tại, **không chạy create**; kiểm tra metadata bằng lệnh đọc.

### 20.2. Tạo database

~~~bash
az cosmosdb sql database create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB"
~~~

Ví dụ không cấp shared throughput cho database vì throughput sẽ gắn ở container. Nếu dùng database shared RU/s, cấu hình phải được thực hiện theo đúng mode, tránh vừa gắn pool chia sẻ vừa vô tình đặt dedicated RU/s cho mọi container.

### 20.3. Tạo container và partition key

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --partition-key-path "/tenantId" \
  --throughput 400
~~~

**Không chọn partition key tạm bợ** rồi đưa dữ liệu thật vào. Đổi key sau khi có dữ liệu thường cần container mới và migration.

400 RU/s là mức lab minh họa, chịu điều kiện tier/quota/giá hiện hành. Không coi đây là default hay minimum hợp lệ cho mọi cấu hình.

### 20.4. Kiểm tra account/database/container

~~~bash
az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,endpoint:documentEndpoint,consistency:consistencyPolicy,locations:readLocations}" \
  --output json

az cosmosdb sql database show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB" \
  --output json

az cosmosdb sql container show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --output json
~~~

Trong output container, tìm **partitionKey paths**, indexing policy, TTL và các fields tương ứng. Lệnh Azure CLI và cấu trúc JSON có thể khác nhau tùy phiên bản/API; nếu query projection trả null, xem JSON đầy đủ trước khi kết luận tài nguyên lỗi.

### 20.5. Dọn lab

Chỉ xóa account/database/container/resource group nếu **do bài lab tạo riêng**, không chứa dữ liệu hoặc tài nguyên của nhóm khác. Khi cần, lưu export/bằng chứng test và kiểm tra Azure Cost Management sau khi dọn; chi phí có thể cập nhật chậm.

## 21. Microsoft Entra ID và Cosmos DB data-plane RBAC

### 21.1. Hai lớp phân quyền

**Control plane (ARM/Azure RBAC)** quyết định ai được tạo/sửa/xóa tài nguyên, quản trị region/network/throughput.

**Data plane Cosmos DB for NoSQL** quyết định ai được đọc/query/ghi items, theo cơ chế **Cosmos DB native data-plane RBAC** và roles như:

- **Cosmos DB Built-in Data Reader**.
- **Cosmos DB Built-in Data Contributor**.

**Azure Contributor ở resource group không đồng nghĩa có quyền query/write documents** qua Entra data-plane identity. Cũng không cần cấp account key cho app chỉ vì đã có Azure Contributor.

### 21.2. Gán quyền data-plane có kiểm soát

Trong lab, người quản trị có thể xem role definitions:

~~~bash
az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

Nếu đã được chủ sở hữu cho phép, sử dụng role definition ID thực và principal object ID của managed identity để tạo assignment với scope cần thiết. Ví dụ cấu trúc:

~~~bash
PRINCIPAL_ID="<managed-identity-principal-object-id>"
ROLE_DEF_ID="<data-contributor-role-definition-id>"

az cosmosdb sql role assignment create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --principal-id "$PRINCIPAL_ID" \
  --role-definition-id "$ROLE_DEF_ID" \
  --scope "/dbs/commerce/colls/orders"
~~~

Cú pháp role definition identifier, scopes và quyền cần thiết để quản lý assignments phải được kiểm tra theo Azure CLI/API hiện hành. **Không chạy với placeholder**. Scope **/dbs/commerce/colls/orders** dùng làm ví dụ cho một container; không tự cấp phạm vi **/** toàn account nếu chỉ cần Orders.

### 21.3. Không dùng account keys trong source

Account keys hoặc connection strings cung cấp quyền rất rộng theo cơ chế key authentication. Không commit vào Git, log, Dockerfile hoặc application telemetry. Khi dùng key trong tình huống đặc biệt phải có Key Vault, rotation và hạn chế quyền phù hợp.

Với App Service, AKS, Functions, VM, ưu tiên **managed identity/Workload Identity** khi SDK/data plane hỗ trợ, phối hợp RBAC và network.

### 21.4. Private networking

Nếu account dùng Private Endpoint:

- VNet/subnet của ứng dụng cần có route tới endpoint private.
- DNS phải resolve Cosmos endpoint đúng private IP.
- Private DNS zone NoSQL thường liên quan **privatelink.documents.azure.com**.
- Đường HTTPS/TLS phải được phép qua firewall/NSG theo topology.
- Managed identity/token issuance có thêm các phụ thuộc authentication tương ứng.

**Private Endpoint không cấp data role**. Nếu SDK nhận 403, kiểm tra data-plane role; nếu DNS/network timeout, kiểm tra Private Link, route và TLS; nếu 429, kiểm tra RU budget.

## 22. Java SDK v4: chuẩn bị phụ thuộc và client

Azure SDK cho API for NoSQL thường dùng Maven artifact **com.azure:azure-cosmos** (v4) cùng **com.azure:azure-identity** để xác thực Entra.

Ví dụ dependencies trong **pom.xml**:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>REPLACE_WITH_TESTED_COSMOS_V4_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>REPLACE_WITH_TESTED_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

**Các version là placeholder**: phải điền phiên bản đang được dự án phê duyệt hoặc dùng Azure SDK BOM/dependency management tương thích trước khi chạy Maven. Đoạn trên là phần dependencies, không phải POM hoàn chỉnh.

### 22.1. Tạo CosmosClient

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.CosmosContainer;
import com.azure.identity.DefaultAzureCredentialBuilder;

String endpoint = System.getenv("COSMOS_ENDPOINT");
if (endpoint == null || endpoint.isBlank()) {
    throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
}

CosmosClient client = new CosmosClientBuilder()
    .endpoint(endpoint)
    .credential(new DefaultAzureCredentialBuilder().build())
    .consistencyLevel(ConsistencyLevel.SESSION)
    .buildClient();

CosmosContainer orders = client
    .getDatabase("commerce")
    .getContainer("orders");

// Quản lý vòng đời client và gọi client.close() khi ứng dụng dừng.
~~~

Đây là **đoạn code trong một class/method**, chưa có main hoặc đầy đủ imports. App phải được cấp đúng **Cosmos DB data-plane RBAC**. Không chạy Create/Read với managed identity chưa được cấp role rồi kết luận SDK hỏng.

### 22.2. Tái sử dụng client

Trong ứng dụng lâu dài, **CosmosClient** nên được tái sử dụng thay vì tạo và đóng cho mỗi HTTP request. Mỗi client có connection management/cache; việc tạo lặp lại có thể tăng latency và resource usage.

Tuy nhiên, nếu một ứng dụng phục vụ nhiều tenants, đừng trộn quyền/trust boundary giữa tenants chỉ vì dùng chung client; application-level authorization vẫn phải kiểm soát tenantId.

## 23. Java CRUD: ví dụ đầy đủ theo partition key

Đoạn code dưới minh họa **create, read, query, conditional replace và delete** trên container đã được tạo bằng Azure CLI. Nó chỉ thao tác với một item lab. Để chạy, cần chọn SDK versions tương thích, cấu hình **COSMOS_ENDPOINT** và đăng nhập Entra/managed identity với quyền dữ liệu.

### 23.1. Class OrdersCrudDemo

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;
import com.azure.cosmos.util.CosmosPagedIterable;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class OrdersCrudDemo {
    public static void main(String[] args) {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
        }

        CosmosClient client = new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .consistencyLevel(ConsistencyLevel.SESSION)
            .buildClient();

        try {
            CosmosContainer container = client
                .getDatabase("commerce")
                .getContainer("orders");

            String tenant = "tenant-hcm";
            String orderId = "order-lab-481";
            PartitionKey pk = new PartitionKey(tenant);

            Map<String, Object> order = new HashMap<>();
            order.put("id", orderId);
            order.put("tenantId", tenant);
            order.put("type", "order");
            order.put("schemaVersion", 1);
            order.put("status", "NEW");
            order.put("totalMinorUnits", 350000);
            order.put("currency", "VND");
            order.put("createdAtUtc", "2026-11-20T03:03:20Z");

            CosmosItemResponse<Map> created = container.createItem(
                order, pk, new CosmosItemRequestOptions());

            System.out.printf("Created RU=%.2f%n",
                created.getRequestCharge());

            CosmosItemResponse<Map> fetched = container.readItem(
                orderId, pk, Map.class);

            System.out.println("Read item: " + fetched.getItem());
            System.out.printf("Read RU=%.2f%n",
                fetched.getRequestCharge());

            // Conditional replace với ETag bảo vệ concurrent writers.
            Map<String, Object> latest = fetched.getItem();
            latest.put("status", "PAID");

            CosmosItemRequestOptions replaceOptions =
                new CosmosItemRequestOptions()
                    .setIfMatchETag(fetched.getETag());

            CosmosItemResponse<Map> updated =
                container.replaceItem(
                    latest, orderId, pk, replaceOptions);

            System.out.printf("Updated RU=%.2f%n",
                updated.getRequestCharge());

            // Query trong tenant, tránh fan-out không cần thiết.
            SqlQuerySpec query = new SqlQuerySpec(
                "SELECT * FROM c WHERE c.tenantId = @tenant " +
                "AND c.type = @type",
                List.of(
                    new SqlParameter("@tenant", tenant),
                    new SqlParameter("@type", "order")
                )
            );

            CosmosQueryRequestOptions queryOptions =
                new CosmosQueryRequestOptions()
                    .setPartitionKey(pk);

            CosmosPagedIterable<Map> results =
                container.queryItems(query, queryOptions, Map.class);

            results.iterableByPage().forEach(page -> {
                System.out.printf("Query page RU=%.2f%n",
                    page.getRequestCharge());
                page.getResults().forEach(System.out::println);
            });

            // Chỉ xóa item demo khi đã đối chiếu đúng id + PK.
            container.deleteItem(
                orderId, pk, new CosmosItemRequestOptions());

        } finally {
            client.close();
        }
    }
}
~~~

### 23.2. Những điều cần hiểu trước khi chạy

- **Create** sẽ trả conflict nếu đã có cùng id trong partition; chương trình lab cần chạy một lần hoặc đổi ID.
- **Read** dùng cả id và partition key, không phải SELECT cross-partition.
- **Conditional replace** với ETag có thể trả **412 Precondition Failed** khi item bị worker khác cập nhật.
- **Query** được parameterized; không tự ghép chuỗi dữ liệu user vào query.
- **Query page request charge** giúp đo RU thực tế.
- **Delete** là thao tác dữ liệu thật, dù là lab. Không thay ID thành một order production.
- Credential resolution của DefaultAzureCredential khác nhau giữa local/CI/App Service/AKS; phải xác nhận danh tính thật sự và role.
- Nếu SDK/library API đổi giữa phiên bản, điều chỉnh theo tài liệu Java SDK version đã pin, không ngẫu nhiên sửa semantics của partition key.

### 23.3. Vì sao có cả id và tenantId?

**id** định danh một document trong partition. **tenantId** là field tại path **/tenantId**. Hai phần cùng tạo địa chỉ logic:

~~~text
(tenantId="tenant-hcm", id="order-lab-481")
~~~

Nếu truyền partition key nhầm thành **tenant-hn**, point read có thể trả 404 dù item với id đó vẫn tồn tại ở tenant-hcm.

### 23.4. Java dùng map hay POJO?

POJO có thể mang annotations/serialization constraints và validation rõ hơn; Map tiện minh họa nhưng dễ sai kiểu. Production nên có DTO/domain models, schema versioning, test data migrations và giới hạn trường dữ liệu người dùng được phép ghi.

## 24. Transactional batch trong Java

Khi cần hai thao tác trong **cùng container và cùng logical partition**, dùng transactional batch theo SDK hỗ trợ.

~~~java
import com.azure.cosmos.models.CosmosBatch;
import com.azure.cosmos.models.CosmosBatchResponse;
import com.azure.cosmos.models.PartitionKey;

import java.util.Map;

// Giả định container là CosmosContainer đã tạo,
// hai items đều có tenantId="tenant-hcm".
PartitionKey pk = new PartitionKey("tenant-hcm");

Map<String, Object> order =
    Map.of("id", "order-lab-481",
           "tenantId", "tenant-hcm",
           "type", "order",
           "status", "PAID");

Map<String, Object> event =
    Map.of("id", "order-lab-481-event-1",
           "tenantId", "tenant-hcm",
           "type", "order-event",
           "eventType", "PAID");

CosmosBatch batch = CosmosBatch.createCosmosBatch(pk);
batch.upsertItemOperation(order);
batch.createItemOperation(event);

CosmosBatchResponse response = container.executeCosmosBatch(batch);
if (!response.isSuccessStatusCode()) {
    throw new IllegalStateException(
        "Transactional batch not committed");
}
~~~

Đây là **đoạn Java chèn vào method có container và imports phù hợp**, không phải một class độc lập. Nó giả định event ID chưa tồn tại và order hợp lệ theo business rules. Nếu event trùng, batch có thể fail; cần stable event ID, kiểm tra response và idempotent workflow.

**Giới hạn:** không có bảo đảm atomicity từ đoạn code này nếu tách order/event sang hai containers hoặc partition key values khác nhau.

### 24.1. Nếu phải ghi SQL và Cosmos DB trong một workflow

Không giữ distributed transaction ảo. Có thể dùng **outbox**, saga/compensation và consumer idempotent:

~~~mermaid
flowchart LR
    API["Orders API"] --> TX["Business database transaction"]
    TX --> STATE["Order state"]
    TX --> OUT["Outbox"]
    OUT --> PUB["Publisher"]
    PUB --> BUS["Service Bus / Event Grid"]
    BUS --> WORKER["Consumer idempotent"]
    WORKER --> COSMOS["Cosmos DB document/read model"]
~~~

Tác dụng phụ ngoài broker/DB vẫn có thể lặp khi retry; cần eventId và idempotency ở người nhận.

## 25. Mô hình multi-tenant và tránh hot partition

### 25.1. Tenant nhỏ, vừa và lớn

Giả sử một SaaS có:

~~~text
Tenant A:  10.000 orders / năm
Tenant B:  60.000 orders / năm
Tenant C:  20.000.000 orders / năm
~~~

**/tenantId** có thể rất phù hợp A/B, nhưng C có thể làm một logical partition quá lớn/hot. Chọn partition key chỉ bằng số lượng tenants trung bình là chưa đủ.

### 25.2. Các phương án

| Phương án | Lợi ích | Trade-off |
|---|---|---|
| **/tenantId** | Tenant isolation theo key, truy vấn tenant đơn giản | Big tenant/hot key |
| **/orderId** | Cardinality rất cao | Query theo tenant cần secondary view/fan-out |
| **/tenantBucket** | Tenant lớn được chia buckets | App phải quản lý bucket, multi-bucket queries |
| **Hierarchical key** | Có thể hỗ trợ tenant prefix và phân bố cấp dưới | Feature/API/transaction semantics cần thử |
| **Tenant riêng container/account** | Quota/cost/permission isolation rõ | Nhiều resources/operations overhead |

### 25.3. Authorization bắt buộc

Cosmos DB partition key không tự kiểm tra xem caller có thuộc tenant đó không. Một API nhận tenantId từ request cần:

1. Xác thực JWT/identity.
2. Kiểm tra tenant membership trong business authorization.
3. Lấy tenantId đáng tin từ claims/context đã kiểm chứng.
4. Dùng đúng partition key trong Cosmos requests.
5. Không cho caller tùy ý thay tenantId để đọc dữ liệu tenant khác.

Data-plane role của một managed identity có thể cho quyền trên nhiều tenants; **tenant isolation trong API vẫn phải được lập trình**.

## 26. Mô hình Catalog, Inventory và Orders

### 26.1. Products/Catalog

Catalog thường có lookup by SKU/productId, search và filter theo category. Nếu API chủ yếu biết productId, chọn partition key theo productId hoặc thiết kế phù hợp với lookup. Không tự chọn **/categoryId** nếu 80% point reads chỉ có productId mà không biết category.

Ví dụ:

~~~json
{
  "id": "SKU-12",
  "productId": "SKU-12",
  "type": "product",
  "name": "Ao thun",
  "categoryId": "apparel",
  "currentPriceMinorUnits": 125000,
  "version": 7
}
~~~

### 26.2. Inventory

Inventory có access pattern **warehouse + SKU**, cập nhật liên tục và concurrency lớn. Có thể dùng key phù hợp với item uniqueness và lượng cập nhật, nhưng phải xem **hot SKU**. Không cho rằng tồn kho hàng nghìn SKU có thể được đặt trong một document lớn rồi cập nhật đồng thời từ mọi orders.

Nếu cần reservation/ledger:

- Dùng optimistic concurrency/transaction batch trong logical partition phù hợp.
- Có idempotent reservation ID.
- Tách ledger entries nếu lịch sử tăng.
- Kiểm tra giới hạn RU ở hot SKU.
- Nếu business cần ACID across inventory/ledger nhiều partitions, đánh giá database/architecture khác.

### 26.3. Orders

Order detail thường đọc cùng lines/customer snapshot. Container **orders /tenantId** là một mô hình ban đầu hợp lý với nhiều tenants có kích cỡ vừa.

~~~mermaid
flowchart TB
    API["Orders API"] --> OR["Container orders<br/>/tenantId"]
    API --> CA["Container customers<br/>/tenantId"]
    API --> PR["Container products<br/>/productId"]
    API --> INV["Container inventory<br/>key theo warehouse + SKU"]
    OR --> CF["Change Feed"]
    CF --> PROJ["Materialized analytics/search projection"]
~~~

**Không cố biến mọi writes vào bốn containers thành một Cosmos transaction.** Business workflow phải có state/idempotency/compensation.

## 27. Query tối ưu và đo Request Charge

### 27.1. Projection

~~~sql
SELECT c.id, c.status, c.totalMinorUnits
FROM c
WHERE c.tenantId = "tenant-hcm"
  AND c.type = "order"
~~~

Chỉ lấy fields màn hình cần, tránh trả rawPayload lớn. Nhưng projection không tự bảo đảm RU giảm mạnh nếu query vẫn phải tìm ở nhiều partitions.

### 27.2. Pagination

Một request trả hàng triệu items là anti-pattern. Dùng page size/continuation token theo SDK, áp giới hạn cho API, không gán nghĩa “page 100” bằng OFFSET vô hạn nếu service/query cost không phù hợp.

Client cần giữ continuation token trong phạm vi query/partition và version phù hợp; không chỉnh sửa token như một ID tự tạo.

### 27.3. Query nhiều điều kiện

Cần theo dõi:

- Query metrics.
- Index utilization.
- Request Charge.
- Result count.
- Query latency p95/p99.
- Cross-partition fan-out.
- Composite index requirements.
- Giá trị hot key và normalized RU.

### 27.4. Ví dụ chi phí thay đổi theo access pattern

| API | Thiết kế | Hành vi cần đo |
|---|---|---|
| GET order detail | Point read id + PK | RU/read và latency |
| GET latest orders tenant | Filter /tenantId + index createdAt | RU/page |
| Search by email toàn tenants | Cross-partition query | RU/latency cao, cần lookup model |
| Yearly revenue dashboard | Aggregate trên toàn orders | Có thể chuyển Change Feed/analytical |
| Update one status | Conditional patch/replace | ETag conflicts, RU/write |
| Fetch giant order item | Embed quá nhiều rows | Item size, response payload, RU |

## 28. Backup, DR, consistency và regional topology

### 28.1. Backup không phải replication

Cosmos DB cung cấp các mô hình backup/restore theo cấu hình và khả năng dịch vụ, chẳng hạn periodic hoặc continuous backup trong những điều kiện hỗ trợ.

- **Replication** bảo vệ availability và phân bố reads/writes.
- **Backup/restore** giúp khôi phục từ lỗi dữ liệu/accidental deletion theo RPO/RTO và khả năng hỗ trợ.
- **Business event ledger** hỗ trợ audit và tái dựng domain state.

Không mặc định mọi account/tier đều có cùng retention, restore granularity hoặc chi phí. Phải chọn theo yêu cầu sản xuất và thử khôi phục.

### 28.2. Multi-region trade-offs

- Người dùng gần read region có thể giảm read latency.
- Write-region topology và consistency ảnh hưởng read-after-write, conflicts và latency.
- Multi-write có thể đòi hỏi conflict resolution policy được thiết kế và thử.
- Chi phí có thể tăng theo replicated storage/throughput và dữ liệu qua region.
- Network, private endpoints và DNS ở từng region phải được chuẩn bị.
- Ứng dụng cần SDK preferred regions/failover strategy theo khả năng hỗ trợ.

Không coi “đã thêm 2 region” là có RTO/RPO 0 nếu chưa test failover, conflict, client retry và data correctness.

## 29. Migration và thay đổi partition key

Một bài toán production phổ biến: ban đầu chọn **/tenantId**, sau một năm tenant lớn nhất trở nên quá nóng.

### 29.1. Không sửa key in place tùy tiện

Thường cần:

1. Thiết kế container mới với key đúng.
2. Viết migration copy items, giữ schema/ids theo policy.
3. Dùng Change Feed/dual-write/outbox để bắt kịp writes mới.
4. Đối chiếu item counts, checksums và sample queries.
5. Chuyển reads theo feature flag/canary.
6. Chuyển writes qua đường mới với idempotency.
7. Theo dõi RU, 429, p95 latency và correctness.
8. Có rollback route/backup và giới hạn thời gian hoạt động song song.
9. Chỉ ngừng container cũ khi đã đủ điều kiện và hết retention window phù hợp.

### 29.2. Thay đổi schemaVersion

Ví dụ v1 dùng **amount** dạng string, v2 dùng **totalMinorUnits**:

~~~json
{"id":"order-1","tenantId":"t-1","schemaVersion":1,"amount":"350000"}
{"id":"order-2","tenantId":"t-1","schemaVersion":2,"totalMinorUnits":350000}
~~~

Reader cần:

- Nhận diện version.
- Chuyển dữ liệu đúng business semantics.
- Không gán default tùy tiện làm thay giá tiền.
- Hỗ trợ chuyển tiếp khi deployment blue-green.
- Có migration plan và audit.

### 29.3. Không migration bằng SELECT * rồi ghi thẳng production

Đọc/quét toàn container có thể tiêu thụ rất nhiều RU và tạo throttling. Migration cần:

- Partition-aware reading.
- Bounded concurrency và rate limit.
- Stable cursor/continuation hoặc change-feed strategy.
- Resume checkpoints.
- Idempotent writes.
- Data comparison/report.
- Cost/timeout budget.
- Không cản hoạt động live API.

## 30. Monitoring và kiểm soát chi phí

### 30.1. Các tín hiệu cần theo dõi

| Tín hiệu | Dùng để |
|---|---|
| **Total Request Units** | Hiểu RU đang tiêu thụ |
| **Normalized RU Consumption** | Đánh giá mức sử dụng capacity/hot partition |
| **Throttled Requests / 429** | Nhận biết vượt quota/tải |
| **Server-side latency** | Đo phản hồi dịch vụ |
| **Client-side latency/retries** | Phân biệt network, SDK retry và app latency |
| **Data Usage / Storage** | Theo dõi tăng trưởng dữ liệu/index |
| **Partition key statistics** theo khả năng hỗ trợ | Tìm hot logical partitions |
| **Availability / regional events** | Theo dõi DR/failover |
| **Change Feed lag/projection delay** | Đánh giá read model/analytical freshness |
| **Azure Activity Log** | Audit thay đổi account/network/throughput |
| **Data-plane diagnostics** | Quan sát truy vấn/thao tác theo chính sách logging |

Không mặc định mọi metric hoặc logs đều được bật sẵn hoặc được xuất ở cùng độ chi tiết. Diagnostic settings/Log Analytics có thể phát sinh phí.

### 30.2. Phân tích hóa đơn

Chi phí có thể đến từ:

- Provisioned RU/s hoặc serverless RU consumed.
- Data storage/index storage.
- Replicated regions, multi-write capabilities theo tier.
- Backup/restore theo model.
- Data transfer, private networking.
- Client compute, serverless processing và ETL.
- Azure Monitor/Log Analytics ingestion/retention.
- Migration/backfill/cross-partition queries.

Tăng index paths có thể tăng write RU và storage. Chọn một container throughput riêng có thể tăng baseline cost. Serverless có thể rẻ với tải nhỏ nhưng không chắc tối ưu với traffic liên tục.

### 30.3. Dự báo cost theo workload thật

Một phương pháp:

1. Thu thập request types và tần suất theo từng API.
2. Đo RU trung bình/p95 theo thao tác, partition và item size.
3. Nhân với peak requests/s để chọn capacity và headroom.
4. Xem traffic theo giờ/tuần để chọn manual/autoscale/serverless.
5. Đo storage growth và backup/region multiplier.
6. Xem log retention và data transfer.
7. Tạo budget/alerts; định kỳ so sánh **cost per completed order**.

Không chỉ tối ưu tổng RU mà bỏ qua lỗi nghiệp vụ, stale reads hoặc SLA latency.

## 31. Chẩn đoán sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **404 Not Found** khi readItem | Sai id/partition key hoặc item không tồn tại | Đối chiếu cả id và tenantId |
| **409 Conflict** khi create | id đã tồn tại trong logical partition, hoặc unique key conflict | Kiểm tra idempotency/business key |
| **412 Precondition Failed** | ETag cũ, concurrent writers | Read-reconcile-retry có giới hạn |
| **429 Request Rate Too Large** | Thiếu RU/s, hot partition, costly query | Xem RU, partition stats, query/index |
| **403 Forbidden** | Data-plane role thiếu/scope sai hoặc network policy theo lỗi | Kiểm tra principal, Cosmos role, firewall |
| **401 Unauthorized** | Token/key không hợp lệ | Kiểm tra Entra credential, token scope/expiry |
| **Timeout/connection failure** | DNS, Private Endpoint, firewall, TLS hoặc network | Kiểm tra route, endpoint, cert, SDK |
| Query rất chậm | Cross-partition scan, index mismatch, paging | Xem query metrics, partition filter, indexes |
| Chi phí tăng sau update | Index mới, nhiều writes/queries, autoscale peak | So sánh RU charge, storage, meters |
| Một tenant bị throttle dù tổng RU còn | Hot logical partition | Chọn partition strategy/key phù hợp |
| Data trùng khi retry | At-least-once/events, thiếu unique event ID | Idempotent writes/unique key/ledger |
| Lost update | Upsert/replace không có precondition | ETag/patch/conditional update |
| Item quá lớn | Embed history/arrays vô hạn | Tách event items/blob references |
| Query sai sau đổi schema | Readers không xử lý schemaVersion | Contract tests + migration |
| Change Feed projection lệch | Consumer lỗi/checkpoint/idempotency | Theo dõi lag, reconcile source/projection |
| SDK trả 403 dù user là Azure Contributor | Nhầm management vs data-plane role | Cấp Cosmos native data-plane RBAC đúng scope |

### 31.1. Debug 404 khi biết order có tồn tại

1. Kiểm tra đúng Cosmos account endpoint.
2. Kiểm tra đúng database/container.
3. Kiểm tra **id** case/format.
4. Kiểm tra partition key path của container.
5. Kiểm tra giá trị **tenantId** thực của item.
6. Kiểm tra app có đang dùng version môi trường khác không.
7. Chỉ dùng query cross-partition để điều tra có kiểm soát nếu thực sự cần; không biến nó thành production workaround.

### 31.2. Debug 429

1. Ghi operation type và request charge.
2. Kiểm tra normalized RU theo container/partition.
3. Xem index/query metrics và hot keys.
4. Xác minh client retry policy và Retry-After.
5. Kiểm tra number of clients/concurrency.
6. Xem capacity manual/autoscale, usage peak.
7. Tối ưu query/partition/caching rồi cân nhắc capacity.
8. Đo lại application p95/p99, không chỉ tỷ lệ 429 server.

### 31.3. Debug concurrency conflicts

1. Xác định item id + partition key.
2. Đọc ETag hiện tại.
3. Kiểm tra số writers và business rule.
4. Phân biệt cùng một command retry với hai commands hợp lệ cạnh tranh.
5. Nếu 412, reconcile state thay vì overwrite.
6. Nếu cần nhiều items atomically, xem transaction boundary.
7. Đối chiếu audit ledger, không chỉ latest status.

## 32. Những anti-pattern thiết kế

| Anti-pattern | Vì sao sai | Cách cải thiện |
|---|---|---|
| Chọn **/status** làm partition key | Giá trị ít, hot partition | Key cardinality lớn và query-aware |
| Dùng **SELECT * cross-partition** cho mọi request | Latency/RU cao | Point read, tenant filter, projection |
| Một document lưu mọi lịch sử | Item lớn, write conflicts | Separate items/Change Feed/Blob |
| Tạo container cho từng Java class | Throughput/cost overhead, khó transaction | Nhóm theo access patterns/ownership |
| Nhét mọi domain vào một container | TTl/indexing/permissions khác nhau | Tách theo boundaries thật |
| Copy schema RDBMS và mong cross-container JOIN | Nhiều network calls, query khó | Embed snapshot/read model |
| Dùng **upsert** thay mọi update | Che duplicate/lost update | Create/conditional replace/patch |
| Không có schemaVersion | Readers bị gãy khi field đổi | Versioned documents và contract tests |
| Bỏ qua idempotency | Retry tạo event/order trùng | Stable business IDs và unique constraints |
| Đặt account key trong source | Credential leak | Managed identity + data-plane RBAC |
| Cho rằng Azure Contributor được đọc data | Nhầm control-plane/data-plane | Cosmos native data role |
| Dùng partition key là status/region có thể đổi | Khó move items | Stable key + migration plan |
| Không đo RU thực | Estimate sai/429/cost | SDK request charge, load test |
| Dùng multi-region thay backup | Xóa nhầm cũng replicate | Backup/restore, audit, DR tests |
| Update tất cả documents khi giá product đổi | Expensive, mất historical snapshot | Catalog current + order price snapshot |
| Migration bỏ qua tail writes | Mất updates ở thời điểm cutover | Change Feed/outbox, reconciliation |

## 33. Checklist trước production

- [ ] Đã xác nhận workload phù hợp **API for NoSQL**, không cần relational joins/transactions làm chủ đạo.
- [ ] Account region, availability, data residency, consistency và billing mode được lựa chọn rõ.
- [ ] Database/container boundaries xuất phát từ ownership và access patterns.
- [ ] Có bảng top reads/writes/queries với input keys và SLO.
- [ ] Partition key đủ cardinality, phân phối tải, ít đổi và xuất hiện trong hot queries.
- [ ] Đã kiểm tra giới hạn logical partition và tenant lớn.
- [ ] Không chọn low-cardinality status/date làm partition key chỉ để filter.
- [ ] ID + partition key được đưa vào point-read APIs.
- [ ] JSON item có schemaVersion, validation, enum/date/currency contract.
- [ ] Embed bounded data; reference large/shared/mutable data.
- [ ] Historical snapshot được tách khỏi current mutable profile/catalog.
- [ ] Document size và indexing paths được kiểm soát.
- [ ] Unique key, TTL và indexing policy được quyết định trước container creation.
- [ ] Cross-partition queries được đo RU và có budget.
- [ ] Manual/autoscale/serverless model đã được load-test và estimate cost.
- [ ] Có ETag/conditional updates và idempotency.
- [ ] Transactional batch chỉ dùng đúng logical partition boundary.
- [ ] Không kỳ vọng transaction Cosmos DB bao gồm Service Bus/SQL.
- [ ] Change Feed consumers có idempotency/checkpoint/reconciliation.
- [ ] Entra/managed identity và Cosmos native data-plane roles dùng least privilege.
- [ ] Backend kiểm tra tenant authorization, không tin tenantId tùy ý từ user.
- [ ] TLS, firewall, Private Endpoint/DNS theo network requirements.
- [ ] Có backup/restore, DR và diễn tập failover theo RPO/RTO.
- [ ] Monitor RU, 429, latency, normalized usage, size và hot keys.
- [ ] Có CI/CD/IaC, canary, schema migration và rollback.
- [ ] Có cost dashboard cho RU, storage, replication, logs và data transfer.
- [ ] Không xóa resources lab hoặc production khi chưa xác nhận ownership.

## 34. Bài tập thực hành

### Bài 1: Đọc tài nguyên

Trong lab được duyệt:

1. Tạo account API for NoSQL trong một region.
2. Tạo database **commerce**.
3. Tạo container **orders** với **/tenantId**.
4. Kiểm tra endpoint, partition key, throughput và indexing policy.
5. Phân biệt bước nào dùng Azure ARM control plane và bước nào dùng Cosmos data plane.

### Bài 2: Point read và cross-partition

1. Tạo ba order items của **tenant-hcm**, hai order items của **tenant-hn**.
2. Point read một order bằng id + partition key.
3. Cố đọc bằng partition key sai, ghi status code.
4. Query all paid orders của tenant-hcm.
5. Query all paid orders toàn container.
6. Đo request charge và giải thích sự khác biệt.

### Bài 3: Chọn partition key

Hệ thống có 2.000 tenants; tenant lớn nhất chiếm 50% tổng writes, và API thường tra cứu **orderId** không đi kèm tenantId.

Hãy đánh giá **/tenantId**, **/orderId**, hierarchical keys và synthetic bucket. Xác định lookup path, query pattern, transactional needs và migration cost.

### Bài 4: Embed hay reference?

Thiết kế:

- Một order có 5–20 lines.
- Mỗi customer có 1.000–100.000 orders.
- Catalog products đổi giá mỗi ngày.
- Order status history có thể tăng mãi.
- Invoice phải giữ giá/nội dung tại thời điểm mua.

Chỉ ra field nào embed, reference, snapshot, separate item/container và vì sao.

### Bài 5: Concurrency

Hai workers cùng cập nhật **order-481**:

1. Mô phỏng cả hai đọc cùng ETag.
2. Worker A replace thành công.
3. Worker B nhận 412.
4. Viết chính sách reconcile/retry tối đa 3 lần.
5. Giải thích vì sao upsert có thể làm mất update.

### Bài 6: Transaction boundary

Cần thay trạng thái Order thành PAID và ghi một order-status event.

- Nếu cùng container và cùng tenantId, dùng gì?
- Nếu khác containers thì cần thiết kế gì?
- Nếu còn phải gửi Service Bus message, outbox/idempotency xuất hiện ở đâu?

### Bài 7: RU và chi phí

Giả định một point read tốn 4 RU, một write 15 RU, peak 300 reads/s và 200 writes/s.

1. Tính RU/s sơ bộ.
2. Cộng thêm 20% headroom để lập phương án thử tải.
3. Giải thích tại sao tính này không bảo đảm không có 429 khi một partition nóng.
4. So sánh manual, autoscale và serverless cho workload này.

### Bài 8: Bảo mật

Một Java Function dùng managed identity đọc/ghi orders.

1. Phân biệt ARM Contributor và Cosmos DB Built-in Data Contributor.
2. Gán role ở scope container phù hợp.
3. Kiểm tra 403 khi role chưa propagate.
4. Cấu hình Private Endpoint và DNS.
5. Giải thích vì sao API vẫn cần tenant authorization.

### Bài 9: Migration

Container cũ dùng **/country**. Country thay đổi và dữ liệu mất cân bằng.

Hãy lập kế hoạch container mới, copy, Change Feed/tail updates, đối chiếu, canary cutover, rollback, metrics và chi phí.

### Bài 10: Case study Orders–Catalog–Inventory

Thiết kế ba containers hoặc một mô hình hợp lý theo những API:

~~~text
GET /tenants/{tenantId}/orders/{orderId}
GET /products/{productId}
POST /warehouses/{warehouseId}/inventory/{sku}/reserve
GET /tenants/{tenantId}/orders?status=PAID
GET /reports/revenue/monthly
~~~

Chọn item shapes, partition keys, unique identities, ETag/concurrency và read model cho reporting.

### Câu hỏi tự kiểm tra

1. Account, database, container và item khác nhau thế nào?
2. Có thể để một Cosmos DB account phục vụ nhiều databases không?
3. Database luôn có throughput riêng không?
4. Partition key path được chọn ở cấp nào?
5. Logical partition khác physical partition ra sao?
6. Id có tự duy nhất toàn container không?
7. Point read cần biết những giá trị nào?
8. Vì sao status ít cardinality là partition key tệ?
9. Hierarchical partition key có làm mọi items cùng tenant thành một transaction không?
10. Khi nào embed tốt hơn reference?
11. Vì sao snapshot product price cần nằm trong order?
12. JSON schema linh hoạt có nghĩa không cần validation không?
13. Cosmos SQL JOIN có JOIN arbitrary hai containers không?
14. Cross-partition query có rẻ như point read không?
15. RU là đơn vị gì?
16. 429 luôn được sửa bằng tăng RU/s không?
17. Autoscale có làm chi phí bằng 0 khi idle không?
18. Default indexing có overhead writes không?
19. Unique key có hiệu lực toàn account không?
20. TTL và application createdAtUtc có cùng semantics không?
21. Change Feed có chứa mọi delete ở mọi mode không?
22. Session consistency có tự bảo đảm atomic transaction không?
23. Transactional batch có thể ghi hai containers không?
24. ETag giúp chống lỗi nào?
25. Tại sao create và upsert có nghĩa khác nhau?
26. Tại sao role Azure Contributor chưa chắc được đọc items?
27. Private Endpoint có tự cấp quyền database không?
28. Đổi partition key cho hàng triệu items có nên là sửa field trực tiếp không?
29. Vì sao multi-region không thay backup?
30. Trong sản xuất cần theo dõi những chỉ số RU, latency và cost nào?

## 35. Tài liệu tham khảo

- [Azure Cosmos DB documentation — Microsoft Learn](https://learn.microsoft.com/azure/cosmos-db/)
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview)
- [Resource model — accounts, databases, containers and items](https://learn.microsoft.com/azure/cosmos-db/resource-model)
- [Modeling and partitioning data](https://learn.microsoft.com/azure/cosmos-db/nosql/modeling-data)
- [Partitioning and horizontal scaling](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview)
- [Hierarchical partition keys](https://learn.microsoft.com/azure/cosmos-db/hierarchical-partition-keys)
- [Request Units and throughput](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [Provisioned throughput](https://learn.microsoft.com/azure/cosmos-db/set-throughput)
- [Autoscale throughput](https://learn.microsoft.com/azure/cosmos-db/provision-throughput-autoscale)
- [Indexing policies](https://learn.microsoft.com/azure/cosmos-db/index-policy)
- [Unique key constraints](https://learn.microsoft.com/azure/cosmos-db/unique-keys)
- [Time to live (TTL)](https://learn.microsoft.com/azure/cosmos-db/nosql/time-to-live)
- [Change Feed overview](https://learn.microsoft.com/azure/cosmos-db/change-feed)
- [Consistency levels](https://learn.microsoft.com/azure/cosmos-db/consistency-levels)
- [Transactional batch in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Optimistic concurrency control](https://learn.microsoft.com/azure/cosmos-db/nosql/database-transactions-optimistic-concurrency)
- [Azure Cosmos DB for NoSQL security and data-plane RBAC](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access)
- [Azure Cosmos DB for NoSQL Java SDK v4](https://learn.microsoft.com/java/api/overview/azure/cosmos-readme)
- [Cosmos DB Java SDK performance tips](https://learn.microsoft.com/azure/cosmos-db/nosql/performance-tips-java-sdk-v4)
- [Back up and restore Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/online-backup-and-restore)
- [Azure Cosmos DB pricing](https://azure.microsoft.com/pricing/details/cosmos-db/autoscale-provisioned/)



