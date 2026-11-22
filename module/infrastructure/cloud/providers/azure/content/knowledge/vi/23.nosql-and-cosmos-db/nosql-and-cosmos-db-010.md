# TTL, unique key và quản lý vòng đời tài liệu

Một ứng dụng thương mại điện tử lưu giỏ hàng tạm, phiên truy cập, thông báo, đơn hàng và bản ghi kiểm toán trên Azure Cosmos DB. Không phải mọi tài liệu đều cần tồn tại mãi mãi: giỏ hàng có thể hết hạn, token phiên phải biến mất sau một khoảng thời gian, nhưng hóa đơn và bằng chứng kiểm toán phải được giữ theo chính sách. Đồng thời, hai người dùng trong **cùng một tenant** không được tạo hồ sơ với cùng email; một yêu cầu retry cũng không được vô tình tạo tài liệu trùng.

**Azure Cosmos DB for NoSQL** cung cấp các cơ chế quan trọng để xử lý những nhu cầu đó:

- **Time to Live (TTL):** tự động hết hạn tài liệu sau số giây tính từ lần sửa cuối.
- **Unique key policy:** ngăn các tổ hợp giá trị trùng nhau **trong cùng logical partition**.
- **Quản lý vòng đời tài liệu:** thiết kế trạng thái, retention, soft delete, change feed, lưu trữ lâu dài, hủy và quan sát để không giữ hoặc xóa dữ liệu sai.

Bài học thuộc chương **Dữ liệu NoSQL với Cosmos DB**, trong mô-đun **CLOUD_PROVIDERS_AZURE**. Kiến thức liên hệ với Azure subscription, resource group, Microsoft Entra ID, ứng dụng App Service/Azure Functions/AKS, mạng riêng, Storage, giám sát, bảo mật và kiểm soát chi phí. Nội dung tập trung vào **API for NoSQL**; những API như MongoDB, Cassandra hoặc Table có quy tắc tính năng riêng, không nên sao chép toàn bộ ví dụ sang các API đó.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

1. Giải thích container, item/document, JSON, partition key, logical partition, id và request units (RU).
2. Phân biệt TTL tắt, TTL bật không có mặc định, TTL mặc định ở container và TTL ghi đè ở item.
3. Tính thời điểm hết hạn từ trường hệ thống **_ts** và hiểu vì sao cập nhật item làm tính lại thời gian.
4. Thiết kế dữ liệu có thời hạn: session, giỏ hàng, thông báo, nhật ký và bản ghi trung gian.
5. Tạo container với TTL và unique key policy bằng Azure CLI, kiểm tra cấu hình qua Data Explorer/management APIs.
6. Phân biệt tính duy nhất của **(partition key, id)** với unique key trên property hoặc tổ hợp properties.
7. Nhận biết giới hạn unique key: phạm vi logical partition, giá trị phân biệt hoa/thường, đường dẫn thiếu trở thành null, policy không sửa được sau tạo container.
8. Giải quyết HTTP 409, lỗi retry, race condition và nhu cầu uniqueness toàn hệ thống.
9. Phân biệt TTL hard deletion với soft delete, tombstone, change feed và lưu trữ trước khi xóa.
10. Xây vòng đời có kiểm soát khi có legal hold, retention, sao lưu, audit và yêu cầu xóa dữ liệu.
11. Tính tác động của TTL/unique key tới RU, storage, throughput và cost.
12. Xây checklist production, migration plan, kịch bản test và runbook chẩn đoán.

Các đoạn cấu hình và mã dưới đây chỉ là ví dụ học tập; tên tài nguyên và dữ liệu đều giả định. Không tự thực thi hoặc tạo tài nguyên tính phí nếu chưa có môi trường lab được cấp phép.

## 2. Kiến thức nền: item, container và partition

### 2.1. Cấu trúc dữ liệu Cosmos DB for NoSQL

~~~mermaid
flowchart TD
    A["Azure Cosmos DB account"] --> D["Database: commerce"]
    D --> C["Container: profiles"]
    C --> P1["Logical partition: tenant-a"]
    C --> P2["Logical partition: tenant-b"]
    P1 --> I1["Item: user-001"]
    P1 --> I2["Item: user-002"]
    P2 --> I3["Item: user-001"]
~~~

Trong mô hình này:

- **Account** là tài nguyên Azure Cosmos DB.
- **Database** chứa các containers.
- **Container** là phạm vi cấu hình partition key, indexing policy, unique key policy và TTL mặc định.
- **Item/document** là một JSON object có trường **id** và property phân vùng tương ứng.
- **Partition key** được chọn khi tạo container và dùng để phân phối dữ liệu/tải.
- **Logical partition** gồm các items có cùng partition key value.
- **Physical partition** là chi tiết triển khai phân phối/scale; một logical partition không đồng nghĩa một máy vật lý cố định.

Ví dụ item:

~~~json
{
  "id": "user-001",
  "tenantId": "tenant-a",
  "email": "Minh@example.com",
  "emailNormalized": "minh@example.com",
  "displayName": "Minh",
  "state": "active"
}
~~~

Khi đọc bằng point read, client thường phải cung cấp **id và partition key value**. Cosmos DB duy trì các hệ thống metadata như **_etag**, **_ts**, **_rid**, có thể nhìn thấy ở response nhưng không nên tự thay đổi bằng business code.

### 2.2. Phân biệt id và unique key

Trong Cosmos DB for NoSQL, **id phải duy nhất trong một logical partition**. Hai logical partitions khác nhau có thể chứa item cùng id.

Ví dụ:

| Partition key value | id | Hợp lệ? | Lý do |
|---|---|---|---|
| tenant-a | user-001 | Có | Item đầu tiên |
| tenant-a | user-001 | Không khi tạo thêm | Trùng (partition key, id) |
| tenant-b | user-001 | Có | Logical partition khác |

Nếu muốn **emailNormalized** không bị trùng trong từng tenant, chỉ id chưa đủ khi id là một UUID khác email. Khi đó cần unique key policy hoặc mô hình dữ liệu khác để thực thi tính duy nhất.

### 2.3. RU là gì?

Cosmos DB tính toán mức sử dụng tài nguyên cho các thao tác đọc, ghi, query, cập nhật và xóa theo **Request Units (RU)**. Chi phí chịu ảnh hưởng bởi:

- Kích thước item.
- Số property, indexing policy và unique key policy.
- Số đọc/ghi và query complexity.
- Số partitions, truy vấn có/không có partition key.
- Throughput provisioned/autoscale hoặc serverless billing model.
- Storage dung lượng sau lưu trữ/replication.
- Tác vụ nền và change feed processing.

**Unique key và TTL không phải tính năng vô hạn miễn phí.** Cần benchmark RU khi lựa chọn schema và retention.

## 3. TTL là gì?

### 3.1. Định nghĩa

**Time to Live (TTL)** quy định số **giây** một item được phép tồn tại tính từ **thời điểm sửa cuối** của nó. Khi item vượt thời gian TTL, Cosmos DB đánh dấu hết hạn và xóa bằng cơ chế nền theo khả năng tài nguyên của hệ thống.

~~~mermaid
flowchart LR
    W["Create / Update item"] --> TS["Hệ thống cập nhật _ts"]
    TS --> E["Tính hạn = _ts + ttl"]
    E --> V["Item còn hiệu lực"]
    V --> X["Quá hạn TTL"]
    X --> Q["Không còn hiện trong query"]
    Q --> P["Background purge"]
    P --> D["Xóa vật lý khỏi container"]
~~~

**TTL không phải lệnh xóa chính xác đến mili-giây.** Sau khi hết hạn, item không còn được đưa vào query results theo semantics của Cosmos DB, nhưng quá trình **physical deletion** là bất đồng bộ và có thể bị chậm khi thiếu RU/throughput.

### 3.2. _ts là gì?

Trường hệ thống **_ts** là Unix timestamp tính bằng **giây**, do Cosmos DB quản lý và đại diện thời điểm item được chỉnh sửa gần nhất.

Ví dụ minh họa:

~~~json
{
  "id": "session-101",
  "tenantId": "tenant-a",
  "userId": "user-001",
  "ttl": 1800,
  "_ts": 1795000000
}
~~~

Giả sử container bật TTL, thời điểm item hết hạn được hiểu là:

~~~text
expirationEpochSeconds = _ts + ttl
                       = 1,795,000,000 + 1,800
                       = 1,795,001,800
~~~

Nếu item được cập nhật trước khi hết hạn, Cosmos DB cập nhật **_ts** và bắt đầu tính TTL từ thời điểm mới. Một yêu cầu **replace/upsert/patch** hợp lệ có thể làm kéo dài sự tồn tại của item dù business logic chỉ muốn sửa một property không liên quan tới thời hạn.

**Không tự sửa _ts** để gia hạn phiên. Nếu ứng dụng cần hết hạn cố định tại một thời điểm pháp lý, xem mục 8 về **expiresAt** và chiến lược không phụ thuộc vào last-modified TTL.

### 3.3. TTL theo container hoặc item

Cosmos DB hỗ trợ:

- **Container-level default TTL:** quy tắc áp dụng cho item không có property ttl riêng.
- **Item-level TTL:** property **ttl** trong JSON có thể ghi đè default TTL, khi container đã bật TTL.

Lưu ý **item-level ttl chỉ có tác dụng khi container-level TTL được bật**, nghĩa là giá trị container không phải null/không bị bỏ cấu hình.

## 4. Ba trạng thái TTL ở container

### 4.1. Giá trị defaultTtl

Trong API/SDK/ARM, tên property thường là **defaultTtl** hoặc **DefaultTimeToLive** tùy ngôn ngữ và API. Ba trạng thái cần nhớ:

| Container default TTL | Ý nghĩa | Item không có ttl |
|---|---|---|
| **null / absent** | TTL **tắt** | Không tự hết hạn |
| **-1** | TTL **bật**, **không có hạn mặc định** | Không tự hết hạn |
| **n > 0** | TTL **bật** với hạn n giây | Hết hạn n giây sau _ts |

**Giá trị 0 không phải TTL hợp lệ.** Với item, ttl cũng phải là một số nguyên dương khác 0 trong phạm vi hỗ trợ hoặc -1.

### 4.2. Ma trận tương tác container và item

| Container defaultTtl | Item ttl | Kết quả |
|---|---|---|
| null/absent | Không có | Không hết hạn |
| null/absent | 3600 | **Bị bỏ qua**, không hết hạn |
| -1 | Không có | Không hết hạn |
| -1 | 3600 | Hết hạn sau 3.600 giây |
| -1 | -1 | Không hết hạn |
| 86.400 | Không có | Hết hạn sau 24 giờ |
| 86.400 | 3600 | Hết hạn sau 1 giờ |
| 86.400 | -1 | Không hết hạn |
| 86.400 | 172800 | Hết hạn sau 48 giờ |

**Bẫy:** set item **ttl: 600** nhưng container **defaultTtl = null** không khiến item biến mất sau 10 phút.

### 4.3. TTL -1 ở container không có nghĩa “tắt cơ chế”

Khi container **defaultTtl = -1**, cơ chế TTL được bật nhưng những item không có ttl sẽ không tự xóa. Bạn có thể đặt ttl khác nhau cho từng item:

~~~json
{
  "id": "notification-short",
  "tenantId": "tenant-a",
  "ttl": 1800,
  "type": "notification"
}
~~~

Một item khác không có ttl:

~~~json
{
  "id": "notification-archived",
  "tenantId": "tenant-a",
  "type": "notification",
  "archiveStatus": "retained"
}
~~~

Trong cùng container, item đầu hết hạn sau 30 phút từ _ts, item thứ hai được giữ vô thời hạn **theo quy tắc TTL**, trừ khi business process xóa riêng.

### 4.4. TTL -1 ở item khi container có mặc định dương

Nếu defaultTtl = 604800 (7 ngày), item sau có ngoại lệ:

~~~json
{
  "id": "audit-legal-hold-001",
  "tenantId": "tenant-a",
  "type": "audit",
  "ttl": -1,
  "retentionReason": "legal-hold"
}
~~~

Item đó không tự hết hạn theo TTL. Nhưng **ttl: -1 đơn thuần không đáp ứng đầy đủ yêu cầu legal hold/immutable retention**: quyền truy cập vẫn có thể xóa/sửa item, nên cần policy, RBAC, khóa/backup, audit và quy trình phê duyệt.

### 4.5. Item ttl null là không hợp lệ

Không dùng:

~~~json
{
  "id": "bad-item",
  "tenantId": "tenant-a",
  "ttl": null
}
~~~

Để dùng default TTL của container, **bỏ hẳn property ttl** khỏi item. Để giữ item không tự hết hạn trong container có default dương, dùng **ttl: -1** theo hỗ trợ.

## 5. Các mẫu TTL thực tế

### 5.1. Session hết hạn sau 30 phút kể từ lần cập nhật

~~~json
{
  "id": "session-1",
  "tenantId": "tenant-a",
  "userId": "user-42",
  "sessionState": "active",
  "ttl": 1800
}
~~~

Nếu ứng dụng ghi một heartbeat vào item sau mỗi request, **_ts** thay đổi và TTL trượt về sau. Đây là **sliding expiration** nếu mong muốn. Nếu business cần session hết hạn cố định sau hai giờ từ lúc login, phải kiểm tra thêm **absoluteExpiresAt** ở application logic, không chỉ dựa vào ttl của item.

### 5.2. Giỏ hàng tạm trong 14 ngày

~~~json
{
  "id": "cart-100",
  "tenantId": "tenant-a",
  "userId": "user-42",
  "items": [
    {"sku": "P-10", "qty": 2}
  ],
  "ttl": 1209600
}
~~~

14 × 24 × 60 × 60 = 1.209.600 giây. Nếu người dùng sửa giỏ hàng sau 10 ngày, TTL tính lại từ thời điểm sửa; đó có thể là hành vi đúng với cart “không hoạt động 14 ngày thì xóa”.

### 5.3. Cache document của API trong 10 phút

~~~json
{
  "id": "cache-product-10",
  "tenantId": "tenant-a",
  "cacheKey": "product:P-10",
  "payloadRef": "blob-path-or-small-payload",
  "ttl": 600
}
~~~

TTL hữu ích để dọn cache, nhưng **không thay kiểm tra tính mới** trong application khi có yêu cầu consistency hoặc invalidation tức thì. Nếu dữ liệu nguồn đổi, cache item có thể vẫn hợp lệ cho tới khi ứng dụng cập nhật/xóa.

### 5.4. Audit cần giữ nhiều năm

Bản ghi kiểm toán phải tuân theo chính sách riêng. Nếu có retention bắt buộc hoặc legal hold, **không nên chỉ để default TTL ngắn rồi mong đưa ttl: -1 thủ công cho mọi bản ghi quan trọng**. Nên tách container/Storage tier phù hợp và dùng retention/encryption/audit controls được quản trị.

### 5.5. Ma trận vòng đời thường gặp

| Loại tài liệu | TTL gợi ý để thảo luận | Điểm cần chú ý |
|---|---|---|
| Session token state | Vài phút/giờ | Absolute expiry và revocation |
| Giỏ hàng không hoạt động | Vài ngày/tuần | Sliding expiration từ _ts |
| Notification tạm | Vài giờ/ngày | User chưa đọc hay đã đọc? |
| ETL processing marker | Vài giờ/ngày | Phải đủ lâu cho retry và reconciliation |
| API cache item | Vài phút | Freshness và invalidation |
| Business order | Thường không dùng TTL ngắn | Đối soát, lưu trữ, compliance |
| Security audit event | Theo retention policy được phê duyệt | Immutable/audit/legal hold |
| GDPR/data deletion queue | Không dùng TTL như SLA xóa duy nhất | Verify deletion và backups |

Các khoảng thời gian là gợi ý thiết kế, **không phải chính sách bảo lưu pháp lý**.

## 6. Cấu hình TTL bằng Azure Portal và Azure CLI

### 6.1. Chuẩn bị môi trường lab

Giả sử các tài nguyên đã tồn tại:

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-cosmos-lab
Cosmos DB account (API for NoSQL): cosmos-commerce-lab
Database: commerce
Container cần tạo: sessions
Partition key path: /tenantId
TTL mặc định: 1800 giây
~~~

Bạn phải có quyền quản lý các resource ở Azure management plane. Mỗi tài nguyên/throughput được provision có thể phát sinh chi phí. Bài này không thực thi lệnh Azure CLI.

Kiểm tra context:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az cosmosdb show \
  --resource-group rg-cosmos-lab \
  --name cosmos-commerce-lab \
  --query "{name:name,kind:kind,locations:locations}" \
  --output json
~~~

Đảm bảo **API for NoSQL account** và database đã sẵn sàng, đúng subscription/region.

### 6.2. Tạo container có TTL mặc định

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --partition-key-path "/tenantId" \
  --ttl 1800 \
  --throughput 400
~~~

Trong môi trường lab, **--throughput 400** là giá trị minh họa cho dedicated provisioned throughput; chỉ dùng khi mô hình throughput và account cho phép. Nếu database đã có shared throughput, có thể không cần cấp throughput riêng cho container theo cấu hình thực tế.

Giá trị --ttl là TTL **container**, không phải per-item TTL. Các command options có thể thay đổi theo Azure CLI version; kiểm tra **az cosmosdb sql container create --help** trước khi dùng.

### 6.3. Xem cấu hình container

~~~bash
az cosmosdb sql container show \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --query "{id:resource.id,partitionKey:resource.partitionKey,defaultTtl:resource.defaultTtl}" \
  --output json
~~~

Nếu CLI API response/version trả cấu trúc khác, xem output JSON thực tế để lấy defaultTtl, partition key và uniqueKeyPolicy. Đọc configuration qua management plane không tự chứng minh TTL purge đã thực thi.

### 6.4. Bật TTL qua Portal

Trong Azure Portal:

1. Mở đúng Cosmos DB account → **Data Explorer**.
2. Mở database và container.
3. Chọn phần **Settings** hoặc **Scale & Settings** tùy UI.
4. Tìm **Time to Live**.
5. Chọn **Off**, **On (no default)** hoặc **On** cùng số giây theo nhu cầu.
6. Lưu và kiểm tra cấu hình.

Đặc biệt cẩn thận khi đổi từ TTL tắt sang default dương trên container đã có dữ liệu cũ: các item có **_ts từ lâu** có thể trở nên hết hạn ngay theo TTL mới và bị xóa. Phải đánh giá data retention, backup và rollback **trước** khi áp cho production.

### 6.5. Bật TTL không có hạn mặc định

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name mixed-lifecycle \
  --partition-key-path "/tenantId" \
  --ttl -1 \
  --throughput 400
~~~

Các item không có ttl sẽ không tự hết hạn; chỉ item có ttl dương mới có hạn. **-1 không có nghĩa toàn bộ item sẽ xóa ngay hoặc TTL bị tắt.**

### 6.6. Thay đổi TTL trên container đã tồn tại

TTL có thể được cập nhật theo khả năng management SDK/CLI, trái với **unique key policy không thể sửa sau khi tạo container**. Ví dụ cú pháp:

~~~bash
az cosmosdb sql container update \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --ttl 3600
~~~

Trước khi thay đổi phải:

- Xác định những item sẽ hết hạn sớm hơn hoặc muộn hơn.
- Đánh giá ảnh hưởng đến compliance/business retention.
- Xem cấu hình indexing/throughput.
- Đảm bảo backup/khôi phục nếu dữ liệu quan trọng.
- Thử trên staging với dữ liệu mô phỏng.
- Ghi approval và theo dõi purge volume.

Không dùng --ttl 0 để “tắt TTL”; nếu cần tắt hoàn toàn, dùng cơ chế bỏ/đặt null container defaultTtl theo SDK/API được hỗ trợ. Chuyển sang -1 nghĩa là bật TTL nhưng không có hạn mặc định, **không giống null**.

## 7. Đặt TTL trên từng item với Python SDK

### 7.1. Khuyến nghị xác thực

Ứng dụng triển khai trên Azure nên ưu tiên **Microsoft Entra workload identity/managed identity** khi SDK/API for NoSQL hỗ trợ; cấp Cosmos DB **data-plane RBAC** cần thiết. Không nhúng account key trong source.

Ví dụ Python 3.x với **azure-cosmos** và **azure-identity** tương thích. Azure Cosmos client dùng endpoint và một credential object hỗ trợ token:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]
credential = DefaultAzureCredential()

client = CosmosClient(endpoint, credential=credential)
database = client.get_database_client("commerce")
container = database.get_container_client("sessions")
~~~

Trên máy developer, DefaultAzureCredential có thể dùng user identity đăng nhập công cụ phát triển; trên Azure có thể dùng managed identity. Đây **có thể là hai principals khác nhau**, nên cần cấp quyền dev/prod đúng và kiểm tra SDK credentials. Azure management role Contributor không tự cho quyền tạo/đọc item nếu chưa có Cosmos data-plane authorization đúng.

### 7.2. Tạo session item có ttl

~~~python
from uuid import uuid4

session = {
    "id": f"session-{uuid4()}",
    "tenantId": "tenant-a",
    "userId": "user-42",
    "status": "active",
    "ttl": 1800
}

created = container.create_item(body=session)
print("Session created:", created["id"])
~~~

Không in token hoặc payload chứa PII. Với workload nhạy cảm, nên dùng business ID/idempotency key ổn định khi tạo thay vì UUID ngẫu nhiên mỗi lần retry request.

### 7.3. Đọc bằng point read

~~~python
session_id = created["id"]

current = container.read_item(
    item=session_id,
    partition_key="tenant-a"
)

print(current["id"], current.get("status"))
~~~

Sử dụng partition key làm point read hiệu quả hơn truy vấn cross-partition khi đã biết id và tenant. Khi item đã hết hạn, chương trình phải xử lý trường hợp không tìm thấy; **không tin rằng physical deletion đã hoàn tất ngay cùng thời điểm hết hạn**.

### 7.4. Ghi đè TTL riêng cho item

Nếu container mặc định TTL = 1.800 giây nhưng một session test cần 300 giây:

~~~python
session["ttl"] = 300
container.upsert_item(body=session)
~~~

**upsert không phải lựa chọn an toàn cho mọi nghiệp vụ**: nếu item có id/partition key đã tồn tại, nó thay thế hoặc cập nhật theo API semantics và có thể reset _ts. Với dữ liệu tranh chấp, dùng optimistic concurrency thông qua _etag/If-Match và thao tác có tiền điều kiện.

### 7.5. Thay đổi item làm reset _ts

Giả sử một notification cần giữ đúng 1 giờ từ lúc tạo nhưng ứng dụng cập nhật trường **read: true** ở phút thứ 59. Nếu chỉ dùng ttl: 3600, _ts được cập nhật và thời gian hết hạn lại tính từ lúc đánh dấu đọc. Điều này có thể là bug về retention.

Các giải pháp:
- Tách **state thường thay đổi** và **đối tượng có absolute deadline** sang items/containers khác.
- Lưu thêm **expiresAtUtc** và kiểm tra ở application/query phù hợp.
- Tính lại ttl theo thời gian còn lại khi cập nhật, có xử lý race và sai số thời gian.
- Dùng timer/worker cho thao tác cần deadline cứng và xác minh sau xóa.
- Tránh ghi metadata không cần thiết vào item có TTL trượt.

## 8. Sliding expiration và absolute expiration

### 8.1. Sliding expiration

Nếu chính sách là “xóa giỏ hàng sau 14 ngày **không có hoạt động**”, TTL theo _ts có thể phù hợp:

~~~text
Create cart: Day 0      → dự kiến hết hạn Day 14
Update cart: Day 10     → _ts thay đổi
New expected expiration → Day 24
~~~

Nên chỉ cập nhật khi có **hoạt động thực sự** cần gia hạn; đừng gửi heartbeat làm mới _ts một cách vô hạn nếu đó không phải mục tiêu nghiệp vụ.

### 8.2. Absolute expiration

Nếu chính sách là “token hết hạn tuyệt đối sau 60 phút kể từ login”, cập nhật trạng thái không được kéo dài hạn:

~~~json
{
  "id": "session-absolute-1",
  "tenantId": "tenant-a",
  "createdAtUtc": "2026-11-20T08:00:00Z",
  "expiresAtUtc": "2026-11-20T09:00:00Z",
  "ttl": 3600
}
~~~

**expiresAtUtc là business field do ứng dụng quản lý**, còn Cosmos DB chỉ tự áp TTL dựa vào _ts + ttl. Application phải **kiểm tra expiresAtUtc khi cấp quyền**, ngay cả khi item chưa bị purge. Khi cập nhật item gần expiration, có thể tính lại ttl còn lại nhưng vẫn phải bảo đảm không gia hạn ngoài policy.

### 8.3. Công thức tính lại ttl

~~~text
remainingSeconds = floor(expiresAtEpochSeconds - currentEpochSeconds)
~~~

Nếu remainingSeconds <= 0, không ghi một ttl = 0 rồi hy vọng Cosmos DB xóa ngay. Hãy thực thi nhánh hết hạn/từ chối, sau đó xóa hoặc xử lý theo policy với concurrency control. Nếu remainingSeconds > 0, có thể đặt ttl bằng số giây còn lại theo hạn cố định, nhưng phải tính đến thời gian mạng, retry và clock skew.

### 8.4. TTL không thay hệ thống token revocation

Một phiên đã bị thu hồi cần bị từ chối ngay theo logic xác thực, không chờ physical deletion nền. Quy trình auth nên kiểm tra trạng thái revoked/expiry của token/session hoặc dùng cơ chế token/revocation thích hợp. TTL dùng để **dọn dữ liệu**, không phải chính sách authorization duy nhất.



## 9. Unique key trong Cosmos DB for NoSQL

### 9.1. Unique key ngăn điều gì?

Giả sử một SaaS quản lý hồ sơ người dùng nhiều tenants. Trong **tenant-a**, không được có hai tài khoản với cùng email chuẩn hóa, nhưng **tenant-b** vẫn có quyền sử dụng email đó.

~~~json
{
  "id": "profile-001",
  "tenantId": "tenant-a",
  "email": "Minh@Example.com",
  "emailNormalized": "minh@example.com"
}
~~~

Khi container có partition key path **/tenantId** và unique key path **/emailNormalized**, Cosmos DB sẽ ngăn tạo item khác có cùng **tenantId và emailNormalized**, bất kể id mới khác.

~~~mermaid
flowchart TD
    W["Create profile"] --> P["Xác định logical partition /tenantId"]
    P --> U["Kiểm tra unique key /emailNormalized"]
    U --> C{"Đã có email trong tenant?"}
    C -->|Chưa| OK["Create item thành công"]
    C -->|Có| X["Conflict HTTP 409"]
~~~

**Unique key policy là ràng buộc server-side**, không chỉ kiểm tra ở ứng dụng. Hai requests đồng thời cùng cố tạo một giá trị trùng trong cùng logical partition sẽ không cùng tạo thành công nếu constraint được thiết lập đúng.

### 9.2. Phạm vi uniqueness là logical partition

Ví dụ unique key **/emailNormalized**, partition key **/tenantId**:

| tenantId | id | emailNormalized | Hợp lệ? |
|---|---|---|---|
| tenant-a | p1 | minh@example.com | Có |
| tenant-a | p2 | minh@example.com | Không, unique key conflict |
| tenant-b | p3 | minh@example.com | Có, logical partition khác |
| tenant-a | p4 | lan@example.com | Có |

**Không có tính duy nhất toàn bộ container nếu các items nằm ở logical partitions khác nhau.** Nếu yêu cầu email là duy nhất trên mọi tenants, unique key trên một container partitioned theo tenantId **không đáp ứng**.

### 9.3. id và unique key bổ sung cho nhau

- **id:** giúp định danh item; cặp (partition key value, id) phải duy nhất.
- **Unique key:** ràng buộc những property khác id, ví dụ emailNormalized, externalRef, hoặc tổ hợp nhiều trường.
- **Partition key:** xác định phạm vi mà constraint có hiệu lực và ảnh hưởng scale/data distribution.

Nếu business ID đã tự đủ để xác định duy nhất trong một tenant, có thể thiết kế **id là một giá trị ổn định** thay vì thêm unique key trùng lặp không cần thiết. Tuy nhiên cần cân nhắc public id, PII, khả năng đổi tên, access patterns và partition design.

## 10. Unique key policy là thuộc tính lúc tạo container

### 10.1. Không thể thêm/sửa sau khi container được tạo

Đây là một trong những khác biệt quan trọng nhất so với TTL:

- **TTL container có thể thay đổi** theo API/SDK và điều kiện của sản phẩm.
- **Unique key policy phải xác định khi tạo container**, sau đó không thể sửa policy của chính container đó.

Nếu container production đã tồn tại và thiếu unique key, không thể chỉ gửi một lệnh UPDATE đổi unique key policy. Cần:

1. Thiết kế container mới với đúng partition key và unique key policy.
2. Kiểm tra dữ liệu nguồn có duplicates và missing paths.
3. Chuyển/copy/migrate items, xử lý các conflicts.
4. Đồng bộ thay đổi phát sinh trong lúc di chuyển khi cần.
5. Cutover application có kiểm soát.
6. Verify counts, business invariants và read/write routing.
7. Chỉ dừng/xóa container cũ sau retention/rollback window và approval.

### 10.2. JSON schema unique key policy

Một policy có **một** unique constraint trên email:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    }
  ]
}
~~~

Một policy có **hai** constraints độc lập:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    },
    {
      "paths": ["/externalAccountId"]
    }
  ]
}
~~~

Trong cấu hình trên, mỗi constraint được kiểm tra riêng. Hai item có cùng email hoặc cùng externalAccountId trong tenant sẽ bị từ chối.

### 10.3. Composite unique key

Để tổ hợp **countryCode + taxNumber** là duy nhất:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/countryCode", "/taxNumber"]
    }
  ]
}
~~~

Ý nghĩa: cặp giá trị phải duy nhất **trong cùng logical partition**. Hai item có cùng taxNumber nhưng khác countryCode có thể hợp lệ; hai item cùng cả countryCode và taxNumber không hợp lệ.

**Một composite constraint không có nghĩa từng thành phần phải duy nhất riêng lẻ**. Nếu muốn cả email riêng và cặp countryCode/taxNumber riêng, khai báo **hai entries** tương ứng trong uniqueKeys.

### 10.4. Giới hạn policy

Theo hướng dẫn cho Azure Cosmos DB for NoSQL, unique key policy có giới hạn:

- Tối đa **10 unique key constraints/combinations** trong một container.
- Tối đa **16 unique key paths tổng cộng** trong policy.
- Tăng RU charge cho các thao tác create/update/delete so với trường hợp không có unique key policy.

Giới hạn sản phẩm có thể thay đổi; kiểm tra documentation ở thời điểm tạo container. Tránh sử dụng unique keys để thay cho toàn bộ business validation hoặc full-text uniqueness.

## 11. Bẫy của unique key: null, optional fields và case sensitivity

### 11.1. Path thiếu bị coi là null

Cosmos DB for NoSQL **không hỗ trợ sparse unique keys** theo cùng nghĩa nhiều database engines. Nếu property unique key **không tồn tại** trong item, giá trị tham gia kiểm tra uniqueness được xem như **null**.

Ví dụ unique key **/emailNormalized**, tenantId = tenant-a:

~~~json
{
  "id": "profile-100",
  "tenantId": "tenant-a",
  "displayName": "Người chưa cung cấp email"
}
~~~

Item trên sử dụng giá trị null cho unique key path. Item thứ hai trong tenant-a cũng không có emailNormalized sẽ bị **unique constraint conflict**, vì cùng giá trị null trong phạm vi constraint.

Không dựa vào cơ chế “missing path không được index” để cho phép nhiều item optional field giống SQL sparse filtered unique index.

### 11.2. Cần tách thiết kế optional fields

Nếu email là optional đối với phần lớn items, có vài hướng:

- **Container riêng:** records có email trong container áp unique policy, records không có email ở container khác phù hợp nghiệp vụ.
- **Đặt giá trị placeholder duy nhất và có chủ đích** cho từng item khi email vắng mặt, nhưng phải chứng minh placeholder không làm sai mô hình và không va chạm với giá trị hợp lệ.
- **Business reservation container:** lưu claim theo email chỉ khi đã có email; không ép unique key trên trường missing ở container chính.
- **Thay partition/item model:** nếu uniqueness thực tế chỉ cần cho một loại document cụ thể.
- **Ứng dụng kiểm tra + phối hợp giao dịch có ràng buộc**, nếu không thể thay schema nhưng cần cơ chế chống race thực sự.

Không dùng placeholder ngẫu nhiên nếu nó khiến những record thiếu email được hiểu nhầm là email hợp lệ, hoặc phá logic tìm kiếm/quyền riêng tư.

### 11.3. Unique key path phân biệt chữ hoa/thường

Property JSON là case-sensitive. Path **/emailNormalized** khác **/EmailNormalized** và **/emailnormalized**.

Nếu policy khai báo:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    }
  ]
}
~~~

Nhưng item ghi:

~~~json
{
  "id": "profile-200",
  "tenantId": "tenant-a",
  "EmailNormalized": "minh@example.com"
}
~~~

Cosmos DB xem **/emailNormalized** là missing/null. Điều này có thể làm những lần tạo sau bị 409 do trùng null. Vì vậy cần:

- Chuẩn hóa tên property theo JSON contract.
- Schema validation trong app hoặc gateway/pipeline.
- Test các biến thể tên field.
- Tránh silent field rename giữa deployment versions.
- Kiểm tra kỹ policy paths trước khi tạo container vì không sửa được sau đó.

### 11.4. Giá trị unique key cũng phân biệt hoa/thường

Ví dụ unique key **/email**, hai giá trị:

~~~text
Minh@Example.com
minh@example.com
~~~

Có thể được coi là **khác nhau** theo so sánh case-sensitive của Cosmos DB. Nếu business yêu cầu email không phân biệt hoa/thường, lưu thêm **emailNormalized** theo chính sách canonicalization thống nhất và dùng chính path này làm unique key.

Một quy trình normalize email phải cân nhắc domain IDN/Unicode, whitespace, văn bản case folding và semantics email của provider. Ví dụ đơn giản trong lab:

~~~python
def normalize_email(raw: str) -> str:
    return raw.strip().casefold()
~~~

Đây là phép xử lý minh họa, **không phải một chính sách chuẩn hóa email quốc tế hoàn chỉnh**. Không mặc định mọi loại username/domain/address đều nên casefold giống nhau trong production nếu có yêu cầu tương thích email đặc biệt.

### 11.5. Nhiều unique keys và composite null

Nếu composite constraint gồm **/countryCode** và **/taxNumber**, item thiếu taxNumber vẫn tham gia như tổ hợp (countryCode, null). Hai item cùng countryCode và thiếu taxNumber có thể xung đột trong cùng partition.

Quy tắc thiết kế an toàn: các paths dùng cho unique key nên là **bắt buộc, nhất quán kiểu dữ liệu và được chuẩn hóa** cho tập documents chịu constraint.

### 11.6. Unique key không thay kiểm tra toàn vẹn quan hệ

Unique key chỉ ngăn trùng những paths khai báo trong logical partition. Nó không tự thực thi:

- Foreign key tới item khác/container khác.
- Business trạng thái chuyển hợp lệ (active → suspended → deleted).
- Số dư không âm sau nhiều transactions phức tạp.
- Quyền tenant trên mọi truy vấn.
- Tính duy nhất xuyên mọi partitions.
- Có đủ dữ liệu audit trước khi TTL xóa.

Các yêu cầu đó cần data model, operations, transaction strategy và application rules riêng.

## 12. Tạo container có unique key và TTL bằng Azure CLI

### 12.1. Container profiles cho một SaaS nhiều tenants

Giả sử:

~~~text
Account: cosmos-commerce-lab
Database: commerce
New container: profiles
Partition key path: /tenantId
Unique key path: /emailNormalized
Container TTL: -1 (bật nhưng không có hạn mặc định)
Throughput: 400 RU/s trong lab khi phù hợp
~~~

Lệnh minh họa cho môi trường Bash/Azure Cloud Shell:

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name profiles \
  --partition-key-path "/tenantId" \
  --unique-key-policy '{"uniqueKeys":[{"paths":["/emailNormalized"]}]}' \
  --ttl -1 \
  --throughput 400
~~~

Trong Windows PowerShell, quy tắc quoting khác Bash, cần điều chỉnh **--unique-key-policy**. Với pipeline, thường lưu policy JSON trong **artifact IaC được review** và truyền theo cơ chế file policy nếu CLI hỗ trợ. Bài này không tự tạo file JSON phụ nào.

**Không chạy lại lệnh tạo như một cách “update unique key”** nếu container đã tồn tại. Xác minh tên resource/account/database, throughput mode và partition key trước khi tạo. Azure CLI help có thể có các flags khác theo extension/version.

### 12.2. Xem policy sau khi tạo

~~~bash
az cosmosdb sql container show \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name profiles \
  --output json
~~~

Trong response, kiểm tra các property tương ứng:

~~~json
{
  "resource": {
    "id": "profiles",
    "partitionKey": {
      "paths": ["/tenantId"]
    },
    "defaultTtl": -1,
    "uniqueKeyPolicy": {
      "uniqueKeys": [
        {
          "paths": ["/emailNormalized"]
        }
      ]
    }
  }
}
~~~

JSON trên chỉ là **phần cấu trúc minh họa**, không phải toàn bộ management response hay giá trị thực từ Azure. Nếu CLI/API version có output shape khác, đọc từ API response thật.

### 12.3. Cách thực hành qua Data Explorer

1. Mở Cosmos DB account → **Data Explorer**.
2. Kiểm tra database commerce, tạo container mới profiles.
3. Chọn partition key path đúng.
4. Thiết lập unique key policy từ đầu theo UI được hỗ trợ.
5. Cấu hình TTL khi cần.
6. Review throughput, indexing và tên container.
7. Tạo container rồi xác minh policy.
8. Thử insert hai documents cùng emailNormalized trong cùng tenant.
9. Thử cùng email nhưng khác tenant.
10. Ghi log response status và RU charge ở lab, không chứa PII thật.

**Unique key policy không thể được sửa trên chính container sau tạo**, ngay cả khi UI cho phép xem cấu hình.

## 13. Thực hành: kiểm tra unique key với Python SDK

### 13.1. Kết nối container profiles

Dùng Cosmos DB SDK với managed identity và data-plane permissions:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.identity import DefaultAzureCredential

client = CosmosClient(
    os.environ["COSMOS_ENDPOINT"],
    credential=DefaultAzureCredential()
)
container = (
    client.get_database_client("commerce")
    .get_container_client("profiles")
)
~~~

Đoạn này giả định account hỗ trợ Entra data-plane RBAC và runtime identity được cấp quyền tạo item trong container. Nếu trả 403, kiểm tra đúng **Cosmos DB data-plane role assignment** và network, không tăng Azure management RBAC vô tội vạ.

### 13.2. Tạo hồ sơ đầu tiên

~~~python
first = {
    "id": "profile-001",
    "tenantId": "tenant-a",
    "email": "Minh@Example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Minh",
    "state": "active"
}

result = container.create_item(body=first)
print(result["id"])
~~~

Unique key policy cho **/emailNormalized** được kiểm tra ở server trong logical partition tenant-a.

### 13.3. Thử tạo giá trị trùng

~~~python
duplicate = {
    "id": "profile-002",
    "tenantId": "tenant-a",
    "email": "MINH@example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Hồ sơ trùng",
    "state": "active"
}

try:
    container.create_item(body=duplicate)
except CosmosResourceExistsError as exc:
    if exc.status_code == 409:
        print("Conflict: email đã được sử dụng trong tenant")
    else:
        raise
~~~

Kỳ vọng **HTTP 409 Conflict**. Thông điệp lỗi có thể đề cập ID hoặc unique index và thay đổi theo SDK/server; không dùng chuỗi tiếng Anh trong exception để xác định business code.

**Không tự động upsert item trùng** khi nhận 409: upsert với id khác vẫn phải tôn trọng unique key, còn upsert với id có sẵn có thể vô tình ghi đè hồ sơ thật.

### 13.4. Khác tenant được phép cùng email

~~~python
other_tenant = {
    "id": "profile-003",
    "tenantId": "tenant-b",
    "email": "Minh@Example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Minh ở tenant-b",
    "state": "active"
}

container.create_item(body=other_tenant)
~~~

Nếu không có ràng buộc khác, lệnh có thể thành công vì tenant-b là logical partition riêng.

### 13.5. Thử missing key và case mismatch

~~~python
missing_email = {
    "id": "profile-010",
    "tenantId": "tenant-a",
    "displayName": "Không có email"
}

wrong_case = {
    "id": "profile-011",
    "tenantId": "tenant-a",
    "EmailNormalized": "abc@example.com"
}
~~~

Cả hai đều thiếu đúng property **emailNormalized**. Trong container dùng unique key /emailNormalized, một item missing key có thể được tạo, còn item thứ hai missing cùng key trong tenant-a sẽ bị conflict do null. Thực hiện test riêng trong tenant/partition trống để tránh nhiễu từ dữ liệu lab cũ.

### 13.6. Case-sensitive value test

~~~python
case_1 = {
    "id": "case-1",
    "tenantId": "tenant-c",
    "emailNormalized": "A@example.com"
}

case_2 = {
    "id": "case-2",
    "tenantId": "tenant-c",
    "emailNormalized": "a@example.com"
}
~~~

Theo case-sensitive value semantics, hai giá trị khác nhau có thể cùng tồn tại. Đây là lý do phải canonicalize trước khi ghi nếu business yêu cầu case-insensitive uniqueness.

### 13.7. Test đồng thời để chứng minh uniqueness

Một test tốt tạo nhiều concurrent requests cùng:

~~~text
tenantId = tenant-race
emailNormalized = race@example.com
id khác nhau ở mỗi request
~~~

Sau cùng, chỉ **một** request được phép tạo item theo constraint; những request khác nhận 409 (bỏ qua các lỗi test/network khác). Nếu application trước tiên query “email đã tồn tại chưa?” rồi mới create mà **không có constraint server-side**, hai requests có thể cùng thấy “chưa tồn tại” và cùng insert.

## 14. Khi cần uniqueness trên toàn hệ thống

### 14.1. Vấn đề của uniqueness theo partition

Business quy định email phải là duy nhất **trong toàn bộ app**, không phụ thuộc tenant. Nhưng profiles partition theo tenantId; unique key /emailNormalized chỉ có hiệu lực **trong tenant**.

Các lựa chọn cần đánh giá:

1. **Đổi partition key/model** sao cho mọi record cần so unique nằm cùng logical partition, nếu scale và size phù hợp; không nên dồn tất cả users lớn vào một partition chỉ để có global uniqueness.
2. **Identity claim/reservation container:** tạo một document được định danh bởi emailNormalized ở partition thích hợp để giữ quyền sở hữu, với create-only operation có thể conflict.
3. **Identity service chuyên biệt:** dùng Microsoft Entra ID hoặc hệ thống định danh có quy tắc uniqueness theo nghiệp vụ.
4. **External transactional store:** dùng database khác có uniqueness phù hợp nếu cần giao dịch xuyên nhiều thực thể.

### 14.2. Reservation container pattern

Một container dành riêng để giữ claim email:

~~~json
{
  "id": "email:sha256-of-normalized-email",
  "claimBucket": "by-email",
  "ownerTenantId": "tenant-a",
  "profileId": "profile-001",
  "status": "reserved"
}
~~~

**ID** được tạo ổn định từ email đã canonicalize; ví dụ dùng hash phù hợp nhằm hạn chế đưa PII rõ ràng vào ID. Để ngăn create trùng, dùng create-only operation với cặp id và partition key cố định/được thiết kế để đảm bảo mọi claim cho cùng email đến đúng logical partition.

Tuy nhiên, việc tạo claim ở container A và hồ sơ ở container B **không có giao dịch nguyên tử mặc định xuyên containers**. Có thể gặp:

~~~text
Tạo claim thành công
        |
        v
Tạo profile lỗi do network/validation
        |
        v
Claim bị giữ nhưng không có profile
~~~

Cần saga/compensation, trạng thái pending, timeout hợp lý, reconciliation worker và idempotency. **Không đặt TTL quá ngắn trên claim đang được dùng** rồi cho một người khác chiếm email trước khi hoàn tất phục hồi.

### 14.3. Transactional batch chỉ trong cùng logical partition

Cosmos DB for NoSQL hỗ trợ transactional batch cho các items có **cùng logical partition key value** trong một container theo API/SDK hỗ trợ. Không sử dụng transactional batch như lời hứa atomic transaction xuyên mọi containers hoặc partitions.

Nếu business constraint quan trọng không thể nằm cùng partition, phải thiết kế phân tán dựa trên idempotency, saga hoặc một authority store khác.

## 15. TTL và unique key tương tác ra sao?

### 15.1. Unique value được giải phóng khi item hết hạn?

Giả sử trong tenant-a, item có emailNormalized = minh@example.com và ttl = 600. Sau khi TTL hết hạn, Cosmos DB bắt đầu quy trình xóa nền. Đừng thiết kế nghiệp vụ dựa trên giả định **giá trị unique key có thể dùng lại chính xác giây thứ 600**:

- Item có thể đã không xuất hiện trong query.
- Physical purge có thể chưa hoàn tất.
- Lịch giải phóng constraint phải được kiểm chứng theo runtime/SDK và tải thực.
- Một yêu cầu tạo cùng unique value có thể gặp conflict/điều kiện cạnh tranh trong khoảng chuyển tiếp.
- Client nên xử lý 409 minh bạch và retry có giới hạn khi nghiệp vụ cho phép.

Nếu business cần chuyển quyền sở hữu email/người dùng **đúng lúc**, dùng workflow có trạng thái riêng hoặc rõ ràng xóa/giải phóng quyền theo operation có điều kiện; TTL chỉ nên là cơ chế dọn dữ liệu bổ sung.

### 15.2. Dữ liệu hồ sơ không nên hết hạn chỉ vì muốn giải phóng email

Một profile đã đóng có thể phải được giữ phục vụ audit dù email được phép đăng ký lại. Nếu dùng unique key /emailNormalized trên container chính, hai yêu cầu có thể mâu thuẫn:

- Giữ profile cũ làm bằng chứng.
- Cho người mới dùng email đó.

Các giải pháp:

- Tách **active identity claim** khỏi **historical profile**.
- Khi đóng account, cập nhật/xóa claim theo workflow và giữ immutable audit record khác.
- Nếu điều kiện retention cho phép, chuyển profile cũ sang archive container với chính sách thích hợp.
- Không dùng TTL trên audit record chỉ để “giải phóng” một unique key.
- Ghi reason, approver và time nếu việc chuyển email sở hữu có yêu cầu compliance.

### 15.3. Không giữ business uniqueness bằng một item có TTL không kiểm soát

Nếu reservation record cho email có ttl dương và service xử lý chậm, TTL có thể xóa claim trước khi bước tạo profile kết thúc; một request khác tạo claim mới và phát sinh duplicate ownership. Các claim cần một lifecycle độc lập: pending, committed, released, expired theo deadline và reconciliation.



## 16. Quản lý vòng đời tài liệu: tạo, sửa, lưu trữ và xóa

### 16.1. Xem vòng đời như một state machine

Một tài liệu có thể đi qua nhiều trạng thái hơn là “tồn tại hoặc bị xóa”:

~~~mermaid
flowchart TD
    C["Created"] --> A["Active"]
    A --> U["Updated"]
    U --> A
    A --> S["Soft Deleted / Archived"]
    S --> R["Restored theo policy"]
    R --> A
    S --> H{"Legal hold?"}
    H -->|Có| L["Retained / Hold"]
    H -->|Không| E["Eligible for TTL / purge"]
    L --> P["Release hold có approval"]
    P --> E
    E --> D["Physically Deleted"]
    D --> V["Verify deletion + reconcile copies"]
~~~

Đây là state machine **do ứng dụng triển khai**, không phải tính năng tự có của Cosmos DB. TTL chỉ thực hiện phần hết hạn/xóa tự động; nó không tự kiểm tra legal hold hoặc chuyển dữ liệu sang storage lưu trữ trước.

### 16.2. Phân loại dữ liệu trước khi chọn TTL

Một inventory mẫu:

| Document type | Người sở hữu dữ liệu | Hoạt động cuối | Retention | Xóa/Archive |
|---|---|---|---|---|
| Session | Authentication service | Login/refresh | Ngắn | TTL + auth expiry |
| Cart | Shopping service | User activity | Inactivity policy | TTL hoặc archive chọn lọc |
| Notification | Notification service | Delivered/read | Theo trải nghiệm | TTL sau đủ thời gian |
| Process marker | Data pipeline | Completed | Phải đủ cho retry | TTL sau reconciled |
| Order | Commerce service | Fulfilled/refunded | Theo business/legal policy | Archive trước xóa nếu được phép |
| Payment record | Payments service | Settled/disputed | Theo hợp đồng/pháp luật | Retention riêng và audit |
| Security event | Security team | Recorded | Theo security/compliance policy | Immutability/audit cần đánh giá |
| Profile | Identity service | Deactivated | Theo privacy/retention | Soft delete/claim release/reconciliation |

Không đặt một defaultTtl = 86400 lên container chứa đồng thời sessions, invoices và audit evidence nếu các loại dữ liệu có chính sách khác nhau. Có thể tách containers theo access pattern, partition key, lifecycle và bảo mật.

### 16.3. Hard delete

**Hard delete** là thao tác xóa item khỏi container qua SDK/API hoặc TTL purge. Sau khi xóa, các point reads/query không còn tìm thấy item; nhưng yêu cầu xóa khỏi tất cả backups, replicas, exports, logs và analytical copies cần được xem độc lập.

Hard delete có thể dùng khi:

- Tài liệu cache/tạm không cần khôi phục.
- Chính sách bảo lưu cho phép.
- Consumer không cần phát hiện delete event qua latest-version change feed.
- Không có legal hold hoặc dependency còn tham chiếu item.

### 16.4. Soft delete

**Soft delete** cập nhật item với cờ/trạng thái thay vì xóa ngay:

~~~json
{
  "id": "profile-001",
  "tenantId": "tenant-a",
  "emailNormalized": "minh@example.com",
  "state": "deleted",
  "deletedAtUtc": "2026-11-20T10:30:00Z",
  "ttl": 86400
}
~~~

Workflow:

1. API xác thực người có quyền yêu cầu xóa.
2. Kiểm tra business hold/retention.
3. Chuyển **state = deleted** bằng conditional write.
4. Ghi deletedAtUtc, correlation ID và audit record thích hợp.
5. Consumer cập nhật search index/cache/replica theo soft-delete event.
6. Khi chắc chắn downstream đã xử lý, có thể để TTL hard-delete hoặc chạy explicit purge.
7. Theo dõi các bản sao/backups theo chính sách riêng.

**TTL vẫn tính từ _ts sau khi soft-delete được ghi**. Ví dụ ttl: 86400 nghĩa là khoảng một ngày kể từ thao tác cuối làm thay đổi _ts, không nhất thiết một ngày từ deletedAtUtc nếu sau đó item còn bị cập nhật.

### 16.5. Soft delete không tự bảo vệ dữ liệu khỏi người truy cập

Một item **state=deleted** vẫn tồn tại và có thể đọc nếu caller có data-plane permission phù hợp. Vì vậy mọi query, API read và background consumer phải tôn trọng trạng thái:

~~~sql
SELECT c.id, c.displayName
FROM c
WHERE c.tenantId = @tenantId
  AND c.state = "active"
~~~

Đây là truy vấn Cosmos DB for NoSQL trong tình huống minh họa. Nếu một client truy vấn khác quên filter state, soft-deleted item có thể bị lộ trở lại. Các trường nhạy cảm nên được xóa/anonymize hoặc giới hạn quyền theo policy thay vì tin hoàn toàn vào filter ứng dụng.

### 16.6. Archive trước khi xóa

Một pipeline có thể:

~~~mermaid
flowchart LR
    C["Cosmos DB active container"] --> F["Change feed / export workflow"]
    F --> B["Azure Blob Storage archive"]
    B --> V["Verify checksum, schema, access, retention"]
    V --> M["Mark archived / soft deleted"]
    M --> T["TTL / approved hard deletion"]
    T --> A["Audit + reconciliation"]
~~~

Đừng giả định TTL sẽ **tự chuyển item tới Blob Storage**. TTL chỉ làm hết hạn và xóa; archival là công việc của ứng dụng/pipeline. Nếu cần đảm bảo mỗi item được archive trước xóa, hãy thiết kế trạng thái và xác minh archive trước khi gán TTL ngắn.

## 17. Change feed và những giới hạn khi xử lý xóa

### 17.1. Latest-version change feed

Trong **latest version mode**, Cosmos DB for NoSQL ghi nhận các phiên bản mới nhất từ create/update. Nó **không phát ra delete operation** dưới dạng thay đổi để consumer xử lý giống insert/update.

Các hệ quả:

- TTL hard deletion không tạo một delete event tương đương trong latest-version feed.
- Nếu soft delete là một **update**, consumer có thể nhìn thấy trạng thái deleted khi xử lý kịp.
- Một số intermediate updates có thể không xuất hiện nếu item được thay đổi liên tục trước khi consumer đọc.
- Nếu item bị xóa/TTL purge trước khi consumer đọc, marker update có thể không còn sẵn trong feed.
- Không dựa vào latest-version change feed làm bằng chứng đầy đủ về mọi lần xóa.

### 17.2. Soft-delete marker pattern

Ví dụ:

~~~text
10:00 Item đang active
10:05 Update state=deleted, ttl=86400
10:06 Change feed consumer đọc item đã soft-deleted
10:07 Consumer xóa khỏi search index, gửi audit
Ngày hôm sau Cosmos DB có thể purge item bằng TTL
~~~

Nếu consumer bị dừng lâu hơn TTL và không kịp xử lý, không thể đảm bảo sẽ đọc marker đó từ latest-version feed. Thiết kế retention của soft-delete marker **dài hơn worst-case consumer lag + recovery window**, đồng thời có reconciliation.

### 17.3. All versions and deletes change feed

Ở những account/cấu hình hỗ trợ, **all versions and deletes mode** có thể cung cấp:

- Các phiên bản thay đổi trung gian.
- Events create/update/delete.
- Metadata phân biệt xóa do TTL expiry.
- Khả năng đọc thay đổi trong **continuous backup retention window**.

Điều kiện và khả năng hiện hành cần kiểm tra: chế độ này gắn với **continuous backup**, API for NoSQL, feature availability/enrollment và những hạn chế tài khoản được nhà cung cấp công bố. Không mặc định mọi tài khoản đã bật sẵn hoặc giữ events vô hạn.

Đặc biệt **TTL delete events xuất hiện khi item thực sự được purge**, không nhất thiết ngay lúc TTL hết hạn.

### 17.4. So sánh hai chế độ

| Tiêu chí | Latest-version mode | All versions and deletes mode |
|---|---|---|
| Create/update | Có, theo latest version semantics | Có, gồm intermediate versions |
| Explicit delete | Không ghi như delete event | Có khi chế độ được hỗ trợ |
| TTL delete | Không ghi như delete event | Có metadata TTL khi purge |
| History completeness | Không bảo đảm mọi update trung gian | Đầy đủ trong retention window theo semantics |
| Retention | Theo đặc điểm latest-version feed | Theo continuous backup retention |
| Account requirements | Phổ biến mặc định theo API hỗ trợ | Continuous backup và feature prerequisites |
| Mục tiêu | Đồng bộ trạng thái mới nhất, ETL cơ bản | CDC/audit/replication cần delete awareness |

Không dùng change feed thay thế immutable compliance audit log nếu audit yêu cầu không được mất events khi outage hoặc retention window hết.

### 17.5. Idempotency của change feed consumer

Một consumer có thể xử lý lại item/event do checkpoint/retry. Vì vậy:

- Dùng operation ID, version/etag hoặc business sequence phù hợp để deduplicate.
- Ghi trạng thái đã xử lý trong store có ràng buộc.
- Không gửi lại email/thanh toán khi event được replay.
- Chấp nhận rằng thứ tự được bảo đảm theo partition key scope, không mặc định có global total order.
- Đo consumer lag, lease health, RU và retry.

Nếu delete event tới sau một create khác của cùng business key, consumer phải so version/operation timestamp và trạng thái nghiệp vụ để tránh xóa nhầm bản mới.

## 18. TTL so với analytical store TTL và backup retention

### 18.1. Transactional TTL

TTL container/item đã thảo luận quản lý tài liệu trong **transactional store** theo mô hình Azure Cosmos DB for NoSQL. Nó dựa trên **_ts** và được thực thi bằng expiry/purge nền.

### 18.2. Analytical TTL là cấu hình khác

Nếu account/container dùng analytical store theo những khả năng được hỗ trợ, có cấu hình **analytical storage TTL** riêng với transactional TTL.

Ví dụ trong CLI có thể có hai flags:

~~~text
--ttl
--analytical-storage-ttl
~~~

Không đồng nhất hai giá trị:

- Transactional TTL quyết định item còn tồn tại trong transactional container bao lâu.
- Analytical TTL điều khiển thời gian tồn tại trong analytical store khi feature được bật/hỗ trợ.
- Chi phí, đồng bộ và retention của analytical store có semantics riêng.
- Xóa dữ liệu khỏi transactional store không chứng minh mọi bản phân tích, exports hoặc backups bị xóa tức thì.

Nếu sản phẩm đang dùng analytical link/mirroring ngoài Cosmos DB, cần xem chính sách sao chép và xóa theo dịch vụ tương ứng, không suy luận từ một TTL duy nhất.

### 18.3. Backups không giống TTL

Cosmos DB có những chế độ backup như periodic hoặc continuous theo cấu hình account. Backup phục vụ khả năng phục hồi theo retention được hỗ trợ. Khi một item đã TTL purge khỏi transactional store, **bản dữ liệu trong backup/restore point vẫn có thể tồn tại trong thời gian chính sách backup cho phép**.

Vì thế:
- TTL không phải cam kết xóa sạch tất cả backups ngay lập tức.
- Backup retention không thay thế legal retention của dữ liệu hoạt động.
- Nếu khôi phục về thời điểm trước delete, có nguy cơ dữ liệu đã xóa xuất hiện lại trong bản phục hồi.
- Quy trình restore phải có đối soát danh sách yêu cầu xóa/consent/legal hold theo compliance.
- Thời gian và địa lý backup cần tuân thủ data residency và chính sách quyền riêng tư.

### 18.4. TTL không đủ cho yêu cầu xóa theo luật/hợp đồng

Nếu khách hàng yêu cầu xóa dữ liệu cá nhân trong SLA cụ thể, chỉ đặt ttl = số giây còn lại có thể không đủ:

1. TTL purge là background, không bảo đảm thời điểm physical delete chính xác.
2. Dữ liệu có thể còn trong backups, logs, exports, replicas và analytical stores.
3. Có thể cần xác minh xóa ở search index, cache và downstream.
4. Đôi khi legal hold ngăn xóa ngay.
5. Quy trình cần audit bằng chứng hành động và xác minh.

Hãy dùng một **deletion workflow** với owner, queue, deadlines, explicit delete/verification, tracking các bản sao và chính sách retention để chứng minh việc tuân thủ; TTL chỉ hỗ trợ dọn dữ liệu khi phù hợp.

## 19. Indexing policy, RU và chi phí xóa TTL

### 19.1. TTL và indexing

Cosmos DB TTL có điều kiện tương thích với indexing policy. **Indexing mode = none không thể được dùng để bật TTL** theo tài liệu quản trị indexing hiện hành.

Nếu muốn dùng Cosmos DB như key-value store có TTL nhưng không cần index các property nghiệp vụ, có thể cân nhắc indexing mode **consistent** với includedPaths/excludedPaths phù hợp để giảm index overhead, thay vì tắt indexing hoàn toàn.

Tuy nhiên, nếu ứng dụng vẫn chạy queries/filter/sort theo properties đã exclude, performance/RU có thể thay đổi hoặc query không hiệu quả. Cần test thực tế trước khi tối ưu.

### 19.2. TTL background purge sử dụng RU

Theo mô hình **provisioned throughput**, xóa tài liệu quá TTL sử dụng RUs còn dư trong quá trình nền. Khi workload đang chiếm phần lớn throughput, quá trình purge có thể bị chậm.

Theo mô hình **serverless**, xóa do TTL có thể được **tính RU tương tự delete item operations**. Mọi account còn có storage cost, network/replication và các giới hạn riêng.

Đừng thiết kế tính phí theo giả định TTL deletes bằng 0 RU trên mọi pricing model.

### 19.3. Unique key làm tăng RU ghi

Container có unique key policy cần kiểm tra tính duy nhất khi create/update/delete; Microsoft Learn lưu ý RU charge cho các hoạt động này có thể cao hơn một chút so với container không có unique key policy.

Yếu tố ảnh hưởng:

- Kích thước item.
- Số và chiều dài unique key paths.
- Indexing policy.
- Logical partition hot spots.
- Throughput mode.
- Tỷ lệ create/update/delete.
- Nguồn contention và số 409 conflicts.

Không nên định nghĩa 10 unique constraints chỉ vì có thể; mỗi constraint phải tương ứng yêu cầu business rõ ràng.

### 19.4. Benchmark RU

Một bài test lab:

1. Tạo container A không unique key, container B có unique key.
2. Giữ **cùng partition strategy**, indexing policy và item size.
3. Insert 1.000 records với dữ liệu không trùng.
4. Đo request charge trung bình/p95 và latency ở cả A/B.
5. Update cùng số records và đo lại.
6. Test 409 conflicts có kiểm soát.
7. Bật TTL phù hợp, quan sát số item còn hiệu lực và storage sau expiry/purge.
8. So RU theo throughput/pricing model.
9. Lặp qua nhiều partition keys để phát hiện skew.
10. Ghi lại region, SDK version, consistency level và settings.

Mức tăng RU không có một hằng số đáng tin cho mọi workload; đo theo actual data model.

### 19.5. Tổng chi phí vòng đời

~~~text
Total lifecycle cost =
    RU đọc/ghi/query/patch/delete
  + Provisioned/autoscale capacity hoặc serverless request charges
  + Transactional storage theo dung lượng và replicas
  + Indexing / uniqueness overhead
  + Change feed processor RU và lease container
  + Backup/continuous backup/analytical store (nếu dùng)
  + Archive Blob Storage và network
  + Application telemetry/log retention
  + Vận hành reconciliation, security và compliance
~~~

Không có nghĩa TTL luôn giảm chi phí ngay lập tức. Bật TTL trên một lượng lớn item cũ có thể tạo backlog purge; cần dự toán RU/capacity và lịch rollout.

## 20. Thay đổi unique key policy: migration đúng cách

### 20.1. Tình huống

Container **profiles-v1** đã có một triệu hồ sơ, partition key /tenantId nhưng chưa có unique key. Business nay yêu cầu emailNormalized duy nhất trong từng tenant.

**Không thể sửa unique key policy tại chỗ.** Phải tạo **profiles-v2** với policy mới và migrate.

### 20.2. Sơ đồ chuyển đổi

~~~mermaid
flowchart TD
    V1["profiles-v1 đang phục vụ"] --> A["Inventory + duplicate scan"]
    A --> B["Normalize email + resolve null/duplicate"]
    B --> C["Create profiles-v2 with uniqueKeyPolicy"]
    C --> D["Backfill dữ liệu sạch"]
    V1 --> CF["Change feed / dual-write strategy"]
    CF --> D
    D --> E["Validate counts, conflicts, partition routing"]
    E --> G{"Cutover gate đạt?"}
    G -->|Không| H["Tiếp tục v1, sửa và retry"]
    G -->|Có| I["Switch app read/write sang v2"]
    I --> J["Monitor + reconciliation + rollback window"]
~~~

### 20.3. Inventory trước migration

Kiểm tra:

- Có bao nhiêu items thiếu emailNormalized?
- Có bao nhiêu email chỉ khác chữ hoa/thường?
- Có duplicate email trong từng tenant?
- Các giá trị có whitespace/Unicode/định dạng bất thường?
- Có items dùng **EmailNormalized** thay vì **emailNormalized** không?
- Có document types không cần email nhưng cùng container không?
- Có item sắp hết hạn TTL cần chuyển không?
- Cần thay partition key hay không?
- Có continuous writes, change feed, batch jobs làm nguồn thay đổi không?
- Bao nhiêu RUs và thời gian sẽ cần để backfill?

### 20.4. Giải quyết duplicate trước khi copy

Ví dụ:

~~~text
tenant-a:
  profile-001 → minh@example.com
  profile-002 → MINH@example.com

Chuẩn hóa:
  cả hai trở thành minh@example.com
~~~

Chỉ một hồ sơ có thể giữ giá trị này nếu unique key đã được áp trong tenant. Cần business policy: merge profiles, chọn canonical owner, liên kết orders/transactions, yêu cầu manual review hoặc đổi email của một record có consent.

Không tự xóa một hồ sơ để backfill “chạy được” khi nó còn liên quan tài chính hoặc quyền riêng tư.

### 20.5. Backfill và writes liên tục

Nếu application vẫn ghi vào v1 trong lúc copy, chỉ copy một snapshot rồi cutover có thể mất những thay đổi mới.

Chiến lược có thể gồm:

- **Dual-write có kiểm soát**, với idempotency và lỗi từng target được reconcile.
- **Change feed** để đồng bộ create/update; với delete cần hiểu mode và semantics như mục 17.
- **Maintenance/read-only window** trước cutover nếu nghiệp vụ cho phép.
- **Container copy job/tool** khi sản phẩm hỗ trợ và configuration phù hợp.

Chọn chiến lược theo độ lớn dữ liệu, SLA downtime và data consistency. Không suy luận latest-version feed sẽ tự đồng bộ mọi delete ở v1.

### 20.6. Verify trước cutover

- Tổng số item hợp lệ theo tenant/type.
- Tỷ lệ failures và unique conflicts đã xử lý.
- Các truy vấn index/partition key chính hoạt động.
- TTL mới không xóa sớm tài liệu cần giữ.
- NoSQL SDK point reads trả đúng tài liệu.
- Application contract tests cho create/update/delete.
- Change feed lag gần 0 hoặc phù hợp cutover policy.
- RU và 429 trong ngưỡng.
- Có rollback reference và ngày hết thời hạn giữ container cũ.

### 20.7. Rollback có hạn chế

Nếu app chuyển qua v2 rồi có writes mới, quay về v1 **không tự đồng bộ** những writes đó. Cần reverse sync/reconciliation, freeze writes hoặc phương án rollback dữ liệu riêng. Xóa v1 sớm sẽ làm mất đường quay lại, nhưng giữ v1 quá lâu có thể làm tăng chi phí/storage và rủi ro dữ liệu cá nhân. Phải cân bằng rollback window theo policy.



## 21. Tình huống thực tế: SaaS hồ sơ và thông báo đa tenant

### 21.1. Đầu bài

Một SaaS nhiều doanh nghiệp có các nhu cầu:

- Mỗi tenant có danh sách user profiles; emailNormalized phải duy nhất trong tenant.
- Session tự hết hạn sau 30 phút không hoạt động.
- Notification tồn tại tối đa 7 ngày sau lần sửa cuối nếu không có ngoại lệ.
- Payment evidence và audit records cần retention riêng.
- Khi user yêu cầu xóa tài khoản, hệ thống phải xóa khỏi search index, chặn đăng nhập và xử lý downstream copies.
- Ứng dụng chạy Azure Functions và App Service, dùng managed identity, VNet/Private Endpoint khi có yêu cầu bảo mật.

### 21.2. Container design

| Container | Partition key | Unique keys | TTL | Lý do |
|---|---|---|---|---|
| profiles | /tenantId | /emailNormalized | -1 | Profiles không tự xóa, uniqueness theo tenant |
| sessions | /tenantId hoặc partition phù hợp tải | Không cần nếu id đủ | 1800 | Session inactivity |
| notifications | /tenantId | Tùy business ID | 604800 | Dọn thông báo sau 7 ngày từ _ts |
| identity-claims | Theo global email claim strategy | id/unique constraint theo mô hình | Theo state | Global email reservation nếu cần |
| payment-audit | Chọn theo access/retention | Theo nghiệp vụ | Theo policy riêng | Không xóa ngắn hạn |
| deletion-jobs | Theo tenant/job ID | Idempotency ID | Sau reconciliation | Theo dõi trạng thái xóa và audit |

**Không phải mọi container đều bắt buộc có unique key policy.** id ổn định có thể đủ cho notifications; tạo thêm constraint không có yêu cầu sẽ tăng RU/complexity.

### 21.3. Luồng tạo hồ sơ

~~~mermaid
sequenceDiagram
    participant U as App Client
    participant A as Profile API
    participant C as Cosmos DB Profiles
    participant M as Monitor
    U->>A: POST profile + email
    A->>A: Authenticate tenant + normalize email
    A->>C: create_item (tenantId, id, emailNormalized)
    alt Unique constraint satisfied
        C-->>A: Created
        A-->>U: 201
    else Duplicate
        C-->>A: 409 conflict
        A-->>U: 409 business error
    end
    A->>M: Log correlation, status, RU (không ghi email rõ)
~~~

Không cho caller tự chỉ định tenantId tùy ý mà không kiểm tra access token/tenant ownership; unique key không giải quyết authorization.

### 21.4. Luồng xóa tài khoản

~~~mermaid
flowchart TD
    R["Authenticated delete request"] --> A["Check tenant ownership + legal hold"]
    A --> B{"Có legal hold?"}
    B -->|Có| H["Mark restricted / human review"]
    B -->|Không| S["Disable login + soft delete profile"]
    S --> C["Publish deletion job / event"]
    C --> D["Remove cache/search/index copies"]
    D --> E["Archive hoặc xóa dữ liệu theo policy"]
    E --> F["Verify Cosmos + downstream"]
    F --> G["Audit completion; retention for deletion job"]
~~~

Đừng bật TTL ngắn trên profile rồi coi toàn bộ deletion workflow đã thành công. Bản ghi có thể hết hạn khi search index hoặc Blob archive chưa được xử lý, làm giảm khả năng đối soát.

### 21.5. Tiêu chí chấp nhận

1. Hai concurrent creates cùng email trong một tenant: chỉ một thành công.
2. Hai tenants khác nhau có thể dùng email giống nhau theo policy.
3. Unique path missing/case mismatch không được vào production thông qua schema validation.
4. Session hết hạn trong thời gian chính sách, app không cấp quyền khi absolute expiry đã qua.
5. Khi profile bị soft-delete, mọi API bình thường đều không trả profile.
6. Change feed consumer xử lý marker trước khi TTL purge hoặc có chiến lược all versions and deletes phù hợp.
7. Backup/analytical/export retention được phân loại riêng.
8. Cosmos DB RU/429, consumer lag và deletion SLA được giám sát.
9. Có diễn tập migration/rollback khi thay unique key policy.
10. Mọi hành động quản trị có audit và RBAC/approval.

## 22. Monitoring, vận hành và bảo mật

### 22.1. Những tín hiệu cần theo dõi

| Tín hiệu | Vì sao quan trọng |
|---|---|
| RU consumption/normalized RU | Tải đọc/ghi/unique key tăng hay không |
| HTTP 429 | Throughput bị giới hạn, retry không hợp lý |
| HTTP 409 | Duplicates/id conflicts/schema bugs |
| P95 latency reads/writes | Business SLA và noisy partitions |
| Storage usage | TTL có giảm dung lượng theo kỳ vọng? |
| Logical partition skew | Hot partition hoặc tenant lớn |
| Change feed lag | Soft-delete markers có bị chậm? |
| Lease/processor failures | Đồng bộ archive/search/index dừng |
| TTL volume / deletion backlog từ workflow | Không hứa purge đúng giây |
| Legal-hold exceptions | Có item cần bảo lưu khác default TTL |
| Backup/retention changes | Compliance và recovery risk |
| Privileged data-plane role changes | Nguy cơ đọc/xóa hàng loạt |
| App delete-job failures | Xóa không hoàn tất trên downstream |
| Cost by account/container/environment | Kiểm soát RU/storage/replication |

Cosmos DB metrics/diagnostics không nhất thiết có sẵn một metric tên chính xác **TTL Backlog** ở mọi account; nếu cần theo dõi deadline/physical purge, xây chỉ số nghiệp vụ, sampling và verification phù hợp.

### 22.2. Logging an toàn

Nên ghi:

- Correlation ID.
- Account/database/container name.
- Tenant ID ở dạng được quản lý theo privacy policy.
- Operation type, status code, substatus khi SDK cung cấp.
- RU charge, latency và retry count.
- Business document ID đã được phân loại dữ liệu.
- Policy version/TTL setting và release commit.
- Deletion job state, timestamp UTC và audit actor.

Không ghi:

- Account key hoặc authorization header.
- Connection strings có credentials.
- Raw email/PII nếu không cần cho điều tra.
- Toàn bộ document payload từ users.
- Secrets hoặc SAS tokens trong Blob URLs.

### 22.3. Azure RBAC và Cosmos DB data-plane roles

Phân biệt:

- **Azure management plane RBAC:** ai được sửa Cosmos DB account, database/container properties, TTL/throughput.
- **Cosmos DB for NoSQL data-plane RBAC:** ai được read/create/update/delete items bằng Microsoft Entra identity.
- **Network:** firewall, Private Endpoint, VNet, DNS.
- **Application authorization:** user nào được truy cập tenant nào.
- **Key Vault:** quản lý secret ngoài Cosmos DB theo chính sách.

Bật managed identity không tự cho quyền ghi tài liệu. Một principal quản trị tài nguyên Azure chưa chắc có quyền Cosmos data plane; role và scope phải được cấp đúng.

### 22.4. Private networking

Trong môi trường private-only:

~~~text
App Service / Azure Functions / AKS
    ↓ VNet integration / VNet networking
Private DNS resolver / zone
    ↓
Cosmos DB Private Endpoint
    ↓
Cosmos DB for NoSQL data plane
~~~

Kiểm tra DNS từ runtime thực tế, TLS hostname, route/NSG/firewall và khả năng kết nối tới Entra token services. Không mở public access toàn cầu chỉ vì app nhận timeout, và không cấp quyền data-plane rộng để sửa lỗi DNS.

### 22.5. Runbook xử lý 409

1. Xác định create item hay update item bị conflict.
2. Kiểm tra id và partition key value.
3. Xem unique key policy của container.
4. Kiểm tra case của JSON paths và normalized field.
5. Xem duplicate hiện có trong **logical partition tương ứng**.
6. Kiểm tra item thiếu key/null và composite combination.
7. Nếu item sắp TTL expire, không dựa vào đúng deadline để tự chạy lại vô hạn.
8. Phân biệt business conflict với retry trùng idempotent.
9. Trả HTTP 409 có mã lỗi nghiệp vụ rõ, không trả secret/payload.
10. Ghi incident khi schema/normalization hoặc migration gây hàng loạt conflicts.

### 22.6. Runbook TTL item không biến mất

1. **Container defaultTtl có null/absent không?** Nếu có, item ttl bị bỏ qua.
2. **Container defaultTtl = -1?** Item phải có ttl dương mới hết hạn.
3. **Item ttl = -1?** Item được loại khỏi auto-expiry.
4. **_ts có vừa bị update?** Hạn sẽ trượt theo last modification.
5. **TTL là giây hay milliseconds?** Không dùng số milliseconds như seconds.
6. **Item đã hết hạn thực chưa?** Tính từ _ts + ttl.
7. **Query không còn thấy item nhưng storage chưa giảm?** Purge nền có thể chậm.
8. **Provisioned RUs có bị dùng hết?** Có thể trì hoãn physical deletion.
9. **Đang xem analytical store/backup/export?** Đó là retention khác.
10. **Có legal hold/archive workflow?** Kiểm tra audit/override.

### 22.7. Runbook xóa nhầm do TTL policy change

1. Dừng rollout và thay đổi ứng dụng gây update/cleanup ngoài kế hoạch.
2. Xác định container, policy trước/sau và thời gian UTC thay đổi.
3. Kiểm tra items đã expire và item còn tồn tại bằng truy vấn có giới hạn.
4. Xem backup mode/restore point khả dụng trong phạm vi retention.
5. Không phục hồi đè production tùy tiện; restore/test trong môi trường phù hợp.
6. Đối soát writes mới kể từ thời điểm sự cố.
7. Xác định bản sao ở archive/search/downstream; tránh “phục sinh” dữ liệu đã được yêu cầu xóa.
8. Cutover/merge theo approval và business reconciliation.
9. Ghi postmortem và thêm guardrail khi thay defaultTtl.
10. Áp kiểm tra canary trên một container/test dataset trước rollout production sau này.

## 23. Những lỗi và hiểu lầm thường gặp

| Triệu chứng hoặc hiểu lầm | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Item ttl=600 nhưng không hết hạn | Container TTL chưa bật | defaultTtl phải khác null |
| defaultTtl=-1 mà không item nào bị xóa | -1 là bật không có hạn mặc định | Đặt ttl dương trên item cần hết hạn |
| Muốn tắt TTL bằng 0 | 0 không hợp lệ | Bỏ/null default TTL theo API hỗ trợ |
| Item hết hạn muộn hơn dự kiến | _ts thay đổi do update | Dùng absoluteExpiresAt/logic riêng nếu cần |
| Query không thấy nhưng storage còn cao | Background purge bất đồng bộ | Đo RU/retention và kiểm tra lại |
| TTL làm app không còn biết ai xóa | Latest change feed không ghi delete | Soft-delete event hoặc all versions/deletes nếu hỗ trợ |
| Bật TTL khiến nhiều item cũ mất | Default TTL tính từ _ts cũ | Preflight data age, canary, backup |
| Update unique key trên container bị từ chối | Policy immutable | Tạo container mới và migrate |
| Trùng email trong tenant vẫn lọt | Policy path sai/case khác hoặc chưa có policy | Chuẩn hóa và verify policy |
| Khác tenant cùng email bị coi là bug | Unique chỉ theo logical partition | Xác nhận business scope |
| Nhiều item thiếu email bị 409 | Missing unique path coi là null | Schema validation hoặc tách model |
| A@domain và a@domain cùng tồn tại | Unique value case-sensitive | Dùng normalized key |
| Composite key không làm từng field unique | Tổ hợp mới là constraint | Khai báo constraints riêng nếu cần |
| 409 từ retry tạo id mới | Idempotency không ổn định | Business request ID ổn định |
| 409 do id trùng | Cặp (pk, id) phải unique | Phân biệt với unique field |
| Muốn global uniqueness với pk=/tenantId | Constraint chỉ trong tenant | Reservation/authority store |
| Archiver không thấy TTL deletes | Latest feed không có delete events | Soft-delete + kịp đọc hoặc all versions/deletes |
| TTL xóa trước khi audit xong | Retention quá ngắn | Archive verify trước TTL |
| Legal hold bị xóa | Business logic không kiểm tra hold | Retention separation và access policy |
| Chi phí không giảm ngay | Purge delay/backups/index/other storage | Phân tích từng thành phần |
| RU tăng sau thêm unique key | Index/constraint overhead | Benchmark và bỏ constraints dư |
| TTL không dùng được với indexing none | TTL cần indexing setup phù hợp | Dùng consistent indexing với exclusion nếu cần |
| Restore làm dữ liệu đã xóa xuất hiện lại | Restore point trước deletion | Reconcile deletion ledger và policy |

## 24. Checklist production

### Data model

- [ ] Đã chọn partition key dựa trên access patterns, scale và tenant isolation.
- [ ] Phân biệt id uniqueness và property unique key.
- [ ] Unique key chỉ được đặt trên fields có business semantics rõ.
- [ ] Unique paths được đảm bảo tồn tại, case và kiểu dữ liệu nhất quán.
- [ ] Optional fields/null behavior đã được thử.
- [ ] Có chiến lược canonicalization email/identifier.
- [ ] Cần global uniqueness hay per-tenant uniqueness đã được quyết định.
- [ ] Có migration plan nếu unique key policy cần thay đổi.

### TTL và vòng đời

- [ ] Default TTL null/-1/n được chọn có chủ đích.
- [ ] Item ttl có đơn vị **giây**, chỉ -1 hoặc số nguyên dương hợp lệ.
- [ ] Đã kiểm tra _ts thay đổi khi update/patch.
- [ ] Sliding vs absolute expiration được phân biệt.
- [ ] Business authorization không chỉ dựa vào item còn tồn tại.
- [ ] Đã xác định archival/soft-delete/physical delete sequence.
- [ ] Legal hold và retention exceptions có policy riêng.
- [ ] Không dùng TTL như SLA xóa tức thì.
- [ ] Có chiến lược backup restore sau khi data deletion.
- [ ] Analytical TTL/exports được xem độc lập khi sử dụng.

### Change feed, reliability và security

- [ ] Latest-version feed không được dùng như complete deletion log.
- [ ] Soft-delete marker TTL đủ lâu cho consumer lag/recovery.
- [ ] All versions and deletes mode chỉ dùng sau khi kiểm tra prerequisites.
- [ ] Change feed consumer có idempotency/deduplication.
- [ ] Data-plane RBAC và management RBAC tách rõ.
- [ ] Managed identity có scope tối thiểu.
- [ ] Private networking/DNS/TLS đã kiểm thử.
- [ ] Logs không chứa account keys, PII không cần thiết.
- [ ] Business deletes có audit trail/correlation và owner.

### RU, monitoring và release

- [ ] Có benchmark RU của create/update/delete với unique key.
- [ ] Có dự toán purge/TTL volume và throughput mode.
- [ ] Theo dõi RU, 429, 409, latency, storage, consumer lag.
- [ ] Có Azure Cost Management budget/tag.
- [ ] Thay defaultTtl được đánh giá trước trên dataset cũ.
- [ ] Có rollback/restore/reconciliation runbook.
- [ ] Có test concurrent writes vào unique key.
- [ ] Có test null/case sensitivity/composite constraints.
- [ ] Có test consumer dừng lâu hơn TTL marker.
- [ ] Có cảnh báo khi deletion workflow quá deadline.

## 25. Câu hỏi tự kiểm tra

1. **TTL trong Cosmos DB for NoSQL dùng đơn vị gì?** Giây.
2. **TTL được tính từ creation time hay last modification?** Từ _ts của lần sửa cuối, hoặc thời điểm tạo nếu chưa sửa.
3. **defaultTtl = null nghĩa gì?** Tắt TTL; item ttl bị bỏ qua.
4. **defaultTtl = -1 nghĩa gì?** Bật TTL nhưng item không có ttl sẽ không tự hết hạn.
5. **defaultTtl = 604800 nghĩa gì?** Item không override sẽ hết hạn sau 7 ngày từ _ts.
6. **ttl = -1 ở item có tác dụng gì?** Miễn tự hết hạn, dù container có TTL mặc định dương.
7. **ttl = null ở item có hợp lệ không?** Không; bỏ property để dùng default.
8. **TTL 0 có nên dùng để xóa ngay không?** Không; không phải TTL value hợp lệ.
9. **Item ttl dương có hoạt động khi container TTL tắt không?** Không.
10. **Query không trả item đã expired có nghĩa physical purge xong chưa?** Không.
11. **Update item có làm TTL tính lại không?** Có, vì _ts thay đổi.
12. **Sliding expiration khác absolute expiration thế nào?** Sliding dựa vào lần hoạt động cuối; absolute dựa vào mốc cố định.
13. **TTL có thay token revocation không?** Không.
14. **Unique key kiểm tra trong phạm vi nào?** Logical partition.
15. **Cặp (pk,id) có phải unique không?** Có trong container.
16. **Unique key /emailNormalized có chặn email trùng giữa hai tenant không?** Không nếu tenantId là partition key và khác nhau.
17. **Unique key policy có thêm vào container hiện hữu được không?** Không, phải tạo container mới và migrate.
18. **Có tối đa bao nhiêu unique constraints/path tổng?** Theo tài liệu hiện tại, 10 constraints và 16 paths tổng.
19. **Unique key path có phân biệt case không?** Có.
20. **Giá trị A@example.com và a@example.com có mặc định coi như trùng không?** Không, cần normalization.
21. **Item thiếu unique property được coi là gì?** Null trong uniqueness constraint.
22. **Composite unique key có khiến từng component unique riêng không?** Không.
23. **Tại sao cần xử lý 409?** Trùng id/unique constraint hoặc một conflict khác cần phân loại.
24. **Chỉ query “email đã tồn tại?” rồi create có an toàn khi concurrency không?** Không, dễ race nếu không có constraint/reservation atomic.
25. **Làm sao bảo đảm global uniqueness?** Thiết kế partition/reservation authority và concurrency/reconciliation, không dựa vào per-tenant unique key.
26. **Soft delete khác TTL hard delete thế nào?** Soft delete giữ item có marker, TTL hard delete loại item sau expiry.
27. **Latest-version change feed có chứa TTL delete events không?** Không.
28. **All versions/deletes mode cần điều kiện gì?** Continuous backup và feature availability/prerequisites phù hợp.
29. **TTL delete event trong all versions xuất hiện khi nào?** Khi item thực sự được purge, không nhất thiết lúc TTL vừa hết.
30. **Có nên đặt TTL ngắn hơn thời gian consumer có thể outage không?** Không nếu cần bảo đảm đọc soft-delete marker.
31. **TTL tự archive vào Blob không?** Không.
32. **TTL có xóa ngay mọi backups/export không?** Không.
33. **Indexing mode none có phù hợp container bật TTL không?** Không theo support hiện hành.
34. **Unique key có tác động RU không?** Có thể tăng RU create/update/delete.
35. **Provisioned throughput có thể làm TTL purge chậm khi nào?** Khi không còn đủ RU nền.
36. **Serverless TTL delete có thể phát sinh RU charge không?** Có.
37. **Retention legal hold có được giải quyết chỉ bằng ttl=-1 không?** Không, cần security/audit/retention controls.
38. **Thay unique policy production cần làm gì?** Container mới, normalize/resolve conflicts, migrate, test, cutover, reconcile.
39. **Điều gì xảy ra nếu restore một snapshot trước khi item đã được xóa?** Có nguy cơ dữ liệu đã xóa xuất hiện trong bản khôi phục.
40. **Thế nào là vòng đời tài liệu đúng?** State model rõ, TTL/unique policy phù hợp, security, archival, deletion verification, cost và monitoring.

## 26. Tài liệu tham khảo

- [Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/) — tài liệu dịch vụ NoSQL, dữ liệu JSON và SDK.
- [Time to live (TTL)](https://learn.microsoft.com/azure/cosmos-db/time-to-live) — TTL container/item, _ts, RU và tính chất expiration.
- [Configure time to live](https://learn.microsoft.com/azure/cosmos-db/how-to-time-to-live) — Portal, CLI, SDK và cập nhật TTL.
- [Unique key constraints](https://learn.microsoft.com/azure/cosmos-db/unique-keys) — phạm vi partition, policy immutable, case/null và limits.
- [Define unique keys for a container](https://learn.microsoft.com/azure/cosmos-db/how-to-define-unique-keys) — tạo container có unique key.
- [Azure CLI cosmosdb sql container](https://learn.microsoft.com/cli/azure/cosmosdb/sql/container) — create/show/update, ttl và unique-key-policy options.
- [Change feed in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/change-feed) — consumer patterns và change feed.
- [Change feed modes](https://learn.microsoft.com/azure/cosmos-db/change-feed-modes) — latest version vs all versions/deletes.
- [Transactional batch operations](https://learn.microsoft.com/azure/cosmos-db/transactional-batch) — giao dịch cùng logical partition.
- [Indexing policy management](https://learn.microsoft.com/azure/cosmos-db/nosql/how-to-manage-indexing-policy) — indexing và TTL compatibility.
- [Partitioning in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview) — logical/physical partitions và scale.
- [Azure Cosmos DB request units](https://learn.microsoft.com/azure/cosmos-db/request-units) — RU và performance.
- [Azure Cosmos DB security](https://learn.microsoft.com/azure/cosmos-db/security) — identity, networking và encryption.
- [Azure Cosmos DB backup and restore](https://learn.microsoft.com/azure/cosmos-db/online-backup-and-restore) — backup modes và recovery constraints.
- [Azure Cosmos DB monitoring](https://learn.microsoft.com/azure/cosmos-db/monitor) — metrics, diagnostic logs và alerts.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags, phân tích chi phí.

**Kết luận:** TTL quản lý thời gian tồn tại của tài liệu theo _ts và tự xóa nền; unique key bảo vệ tính duy nhất **trong logical partition** và phải được chọn khi tạo container; vòng đời tài liệu là một bài toán rộng hơn gồm trạng thái nghiệp vụ, soft delete, archive, change feed, backup, security, legal hold và xác minh xóa. Một triển khai tốt không chỉ làm item “biến mất sau n giây” hay “không trùng email”, mà còn phải chống race, xử lý 409 đúng cách, tránh xóa dữ liệu cần giữ, không làm mất tín hiệu xóa trong pipeline và có thể vận hành/kiểm toán với chi phí RU hợp lý.

