# Backup, restore và bảo vệ truy cập Cosmos DB

> **Chương:** Dữ liệu NoSQL với Cosmos DB  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau khi hoàn thành bài học, bạn có thể:

1. Giải thích vì sao **Azure Cosmos DB** cần chiến lược **backup, restore, data protection và access control** dù là dịch vụ managed database có khả năng phân phối nhiều region.
2. Phân biệt **periodic backup** với **continuous backup/point-in-time restore (PITR)** và các điều kiện lựa chọn, thời gian lưu, phạm vi và cách khôi phục.
3. Phân biệt **replication/failover**, backup, export và **change feed**; xây dựng mục tiêu **RPO, RTO** và kế hoạch diễn tập khôi phục.
4. Thiết kế runbook khôi phục dữ liệu khi bị xóa nhầm hoặc cập nhật sai, kiểm tra restore point và cách chuyển ứng dụng sang tài nguyên đã khôi phục.
5. Phân biệt **Azure control-plane RBAC** với **Cosmos DB for NoSQL data-plane RBAC**, account keys, resource tokens và Microsoft Entra authentication.
6. Bảo vệ tài khoản Cosmos DB bằng **firewall, network ACL, Private Endpoint, Private DNS, managed identity, TLS, encryption và Key Vault**.
7. Sử dụng **Azure CLI** để đọc trạng thái cấu hình và quản lý data-plane role assignments có kiểm soát; dùng **Python Azure Cosmos SDK** với `DefaultAzureCredential`.
8. Giám sát hoạt động bằng **Azure Monitor**, diagnostic logs, các chỉ số RU, 429, availability, backup/restore và audit; phát hiện truy cập sai hoặc dữ liệu khôi phục không nhất quán.
9. Thiết kế test case, runbook, phương án rollback và dự toán chi phí cho kiến trúc Cosmos DB có thể vận hành an toàn.

## 1. Bối cảnh: database managed vẫn có thể mất dữ liệu nghiệp vụ

Một công ty sử dụng Cosmos DB for NoSQL cho hệ thống đơn hàng:

- API tạo và cập nhật tài liệu `orders` với `tenantId` và `orderId`.
- Ứng dụng có nhiều replicas trên Azure Container Apps hoặc AKS.
- Tài khoản Cosmos DB có thể triển khai đa region để tăng tính sẵn sàng.
- Một script migration lỗi thực hiện `DELETE` hoặc cập nhật sai hàng nghìn documents.
- Mã truy cập hoặc account key bị lộ khiến người lạ có thể đọc/xóa dữ liệu.

**Dịch vụ quản lý hạ tầng không tự khắc phục việc xóa nhầm, thao tác hợp lệ nhưng sai nghiệp vụ, hoặc quyền truy cập bị cấp quá rộng.** Dữ liệu xóa có thể được đồng bộ tới các replica đang hoạt động, vì replication chỉ phản ánh thay đổi chứ không phải bản sao lịch sử bất biến.

~~~mermaid
flowchart LR
    U["Client"]
    APP["Order API\nManaged identity"]
    NET["Private Endpoint\nNetwork access policy"]
    DB["Cosmos DB account\nNoSQL database / containers"]
    BACK["Backup policy\nPeriodic hoặc Continuous"]
    REST["Restored account\nkiểm tra và cutover"]
    MON["Azure Monitor\nLogs / Alerts"]
    U --> APP --> NET --> DB
    DB -.-> BACK
    BACK -->|"Restore được hỗ trợ"| REST
    DB -.-> MON
    APP -.-> MON
~~~

Sơ đồ chỉ mô tả luồng logic. **Backup/restore không tự tạo restored account hoặc tự cutover trong mọi policy.** Quy trình cụ thể phụ thuộc API, backup mode, region, tier và quyền được cấp. Một hệ thống production cần biết trước cách chạy và kiểm tra khôi phục, không đợi đến lúc dữ liệu đã mất.

### Câu hỏi cần trả lời trước khi triển khai

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Sai dữ liệu được phát hiện sau bao lâu? | Quyết định retention và cửa sổ PITR |
| Có thể mất tối đa bao nhiêu dữ liệu? | Xác định RPO |
| Dịch vụ được phép gián đoạn bao lâu? | Xác định RTO |
| Phải khôi phục cả account hay chỉ database/container? | Chọn backup mode và runbook |
| Ứng dụng có quyền xóa toàn bộ container không? | Kiểm soát data-plane RBAC và account keys |
| Khi tài khoản bị xâm nhập có thể xóa backup không? | Đánh giá separation of duties và quyền quản trị |
| Khôi phục có tạo endpoint/account mới không? | Chuẩn bị cấu hình mạng, identity và cutover |
| Có hạn chế nơi lưu dữ liệu theo region không? | Chọn vùng backup/restore và compliance |

## 2. Xác định phạm vi Azure Cosmos DB

### 2.1. Account, database, container và item

Với **Azure Cosmos DB for NoSQL**, cấu trúc thường là:

~~~text
Azure subscription
  Resource group
    Cosmos DB account: cos-orders-prod
      API: NoSQL
      Database: commerce
        Container: orders
          Partition key path: /tenantId
          Items: JSON documents
        Container: auditEvents
          Partition key path: /eventId
          Items: JSON documents
~~~

- **Account** là ranh giới lớn cho endpoint, network, consistency, regions, backup mode và nhiều policy vận hành.
- **Database** nhóm các containers, có thể liên quan cấu hình throughput.
- **Container** chứa items, partition key và indexing/TTL policies.
- **Item** là JSON document có `id` và partition key value phù hợp.
- **Partition key** quyết định phân bố logic và cách tra cứu/khôi phục các items theo từng container; một `id` có thể xuất hiện ở nhiều logical partitions tùy key.

### 2.2. API support là điều kiện bắt buộc

Cosmos DB cung cấp nhiều API/model, ví dụ **Cosmos DB for NoSQL**, **API for MongoDB**, **Cassandra**, **Gremlin**, **Table** và các lựa chọn MongoDB vCore riêng tùy sản phẩm.

**Bài này dùng Cosmos DB for NoSQL làm luồng chính.** Trước khi áp dụng các ví dụ CLI, SDK hay data-plane RBAC cho API khác, phải kiểm tra **đúng tài liệu API/account type/backup mode**. Không giả định:

- Cú pháp `az cosmosdb sql role assignment` áp dụng nguyên cho MongoDB/Cassandra.
- Mọi API đều hỗ trợ continuous backup và restore cùng phạm vi.
- Restore cả account và restore chọn lọc một container có cùng thao tác.
- Một Cosmos DB managed offering bất kỳ đều dùng cùng account keys hoặc permission model.

### 2.3. Cosmos DB for NoSQL không phải PostgreSQL backup

PITR cho Cosmos DB **không phải** lệnh SQL `RESTORE DATABASE`, file `.bak` hay thư mục WAL của PostgreSQL. Mỗi account có cách backup/restore được Azure cung cấp. Một bản export JSON thủ công **không tự bảo toàn** partition key design, indexing policy, throughput, toàn bộ metadata, users và quyền mạng nếu không có công cụ/quy trình riêng.

### 2.4. Tính sẵn sàng và durability khác lịch sử dữ liệu

Cosmos DB có cơ chế lưu dữ liệu phân tán và multi-region tùy account, nhưng khi app vô tình xóa item, thao tác xóa đó là một **write được hệ thống chấp nhận**. Các bản sao có thể đồng bộ việc xóa. Backup là một **đường khôi phục dữ liệu theo thời gian** độc lập với việc tăng số replicas đang phục vụ.

## 3. RPO, RTO, retention và các tình huống khôi phục

### 3.1. RPO và RTO

- **RPO (Recovery Point Objective)**: thời điểm dữ liệu có thể phải quay lùi tối đa mà nghiệp vụ chấp nhận. Ví dụ RPO mục tiêu 10 phút không bảo đảm dịch vụ tự có restore point trong mọi backup mode.
- **RTO (Recovery Time Objective)**: thời gian tối đa để ứng dụng trở lại trạng thái phục vụ đã được xác định, bao gồm restore, validation và cutover.
- **Retention window**: khoảng thời gian mà backup data còn khả dụng để restore theo chính sách và giới hạn dịch vụ.

**Backup mode không tự cam kết đạt RTO.** Một restore phải tạo account mới, kiểm tra dữ liệu và đổi ứng dụng có thể lâu hơn rất nhiều so với thao tác failover HA.

### 3.2. Phân loại tình huống

| Tình huống | Cách ứng phó ưu tiên |
| --- | --- |
| Mất một region, dữ liệu logic vẫn đúng | Xem multi-region failover/availability policy |
| Script xóa nhầm một số items | Xem continuous PITR hoặc khôi phục có chọn lọc theo mode/API hỗ trợ |
| Mất toàn database/container | Restore theo phạm vi được backup mode hỗ trợ |
| Tài khoản bị cấp quyền sai hoặc key lộ | Cô lập truy cập, revoke/rotate, audit, đánh giá restore |
| Bug ghi sai giá tiền trong 30 phút | Xác định restore point và kế hoạch merge/replay writes hợp lệ |
| Mất dữ liệu do quá retention | Backup không còn đủ; xem export/archival ngoài cửa sổ |
| Cần sao chép data định kỳ cho analytics | Change feed, ETL/export hoặc Data Factory; không lạm dụng PITR |
| Khôi phục sau xóa account | Kiểm tra khả năng recoverable resources/restore theo backup mode và lifecycle; không mặc định chắc chắn |

### 3.3. Điểm khôi phục không tự trùng thời điểm phát hiện

Ví dụ:

~~~text
09:00 UTC: dữ liệu còn đúng
09:12 UTC: job lỗi xóa nhiều items
09:18 UTC: hệ thống phát hiện bất thường
09:22 UTC: SRE dừng job và chặn quyền ghi
09:24 UTC: xác định restore point trước 09:12
~~~

Muốn khôi phục đúng, phải biết **thời điểm thay đổi đầu tiên gây hỏng**, không phải chỉ thời điểm đội vận hành phát hiện. Sử dụng Azure Activity Log, application audit events, change logs và business evidence để khoanh vùng.

### 3.4. Khôi phục toàn bộ có thể làm mất ghi hợp lệ sau restore point

Nếu restore toàn bộ về 09:11 UTC, những đơn hàng hợp lệ được tạo từ 09:11 tới thời điểm cutover **không tự xuất hiện** trong restored dataset. Cần kế hoạch reconciliation, selective replay hoặc bù giao dịch theo event log còn tin cậy. Không đưa restored account lên production và xóa account cũ mà chưa đánh giá những thay đổi hợp lệ sau mốc đó.

## 4. Periodic backup: mô hình sao lưu theo chu kỳ

### 4.1. Periodic backup là gì?

Ở **periodic backup policy**, dịch vụ tạo các bản sao lưu theo lịch/chính sách hỗ trợ. Độ mới của restore point phụ thuộc **backup interval** và retention. Các thông số về interval, retention và storage redundancy có thể có default và tùy chỉnh khác nhau theo tài khoản, API, tier hoặc thời điểm.

~~~mermaid
flowchart LR
    S["Dữ liệu đang chạy"]
    B1["Backup snapshot\n01:00"]
    B2["Backup snapshot\n05:00"]
    B3["Backup snapshot\n09:00"]
    I["Incident\n10:30"]
    R["Restore theo quy trình\nbackup được chọn"]
    S -.-> B1
    S -.-> B2
    S -.-> B3
    I --> R
    B3 --> R
~~~

Các mốc giờ **chỉ minh họa**, không phải khoảng backup mặc định của Azure. Nếu backup gần nhất trước lỗi là 09:00, những ghi hợp lệ sau đó cần được đánh giá/reconcile khi restore.

### 4.2. Ưu và nhược điểm

**Ưu điểm:**

- Phù hợp khi business chấp nhận RPO theo lịch snapshot.
- Policy có thể đơn giản hơn với workload không đòi phục hồi chính xác từng phút.
- Có lựa chọn redundancy/retention theo tính năng được hỗ trợ.

**Giới hạn:**

- Không tự chọn bất kỳ thời điểm giữa hai backups như PITR liên tục.
- Khôi phục có thể phụ thuộc **quy trình phục hồi của dịch vụ/hỗ trợ** thay vì cùng trải nghiệm self-service với continuous backup.
- Độ chi tiết restore account/database/container và recovery time phụ thuộc API/mode.
- Không tự thay thế một bản backup xuất ra môi trường kiểm toán riêng.

### 4.3. Câu hỏi phải kiểm tra khi chọn periodic

1. Khoảng cách giữa các backups có đáp ứng RPO?
2. Retention có đủ khi bug được phát hiện sau vài ngày?
3. Có thể chọn backup nào và yêu cầu restore theo quy trình nào?
4. Những regions và storage redundancy options nào được hỗ trợ?
5. Restore có cần hỗ trợ vận hành hay có giao diện tự phục vụ?
6. Cần bao lâu để dựng và kiểm tra restored account?
7. Dữ liệu vừa sửa sau backup có cần được replay bằng nguồn khác?

Không mặc định rằng bật một cờ `backup` sẽ có “restore về 10:23:45 UTC” nếu account đang dùng periodic mode.

## 5. Continuous backup và point-in-time restore (PITR)

### 5.1. Khái niệm

**Continuous backup** được thiết kế cho khả năng phục hồi **tới một thời điểm trong cửa sổ retention** ở những Cosmos DB API/account types hỗ trợ. Cửa sổ retention có thể có các cấp/tier khác nhau; cần xem cấu hình thực và giới hạn dịch vụ.

~~~mermaid
flowchart LR
    A["09:00\nDữ liệu đúng"]
    D["09:12\nXóa nhầm"]
    NOW["09:18\nPhát hiện"]
    P["09:11\nRestore point"]
    REST["Restored account\nvalidate"]
    A --> D --> NOW
    D -.->|"Chọn mốc trước lỗi"| P
    P --> REST
~~~

Điểm quan trọng: PITR cho phép chọn **một mốc được dịch vụ hỗ trợ**, nhưng không phải mọi giây/mọi tài nguyên đều luôn có thể khôi phục với độ phân giải bất kỳ. Phải xác minh earliest/latest restorable timestamps, account configuration và feature restrictions.

### 5.2. Continuous khác periodic như thế nào?

| Tiêu chí | Periodic | Continuous/PITR |
| --- | --- | --- |
| Điểm khôi phục | Các bản sao theo lịch hỗ trợ | Mốc thời gian trong restorable window |
| Mục tiêu | Bảo vệ theo chu kỳ | Hạn chế mất dữ liệu do thay đổi/xóa nhầm cần rewind |
| RPO khả thi | Phụ thuộc backup interval | Có thể nhỏ hơn khi tính năng/điểm khôi phục cho phép |
| Self-service restore | Khác theo API/mode/quy trình dịch vụ | Có trải nghiệm quản lý restore được hỗ trợ |
| Tạo resource mới khi restore | Kiểm tra behavior phục hồi cụ thể | Thường phục hồi thành **account đích mới** |
| Restore chọn lọc | Kiểm tra giới hạn | Có thể hỗ trợ account/database/container theo phạm vi và API |
| Cấu hình/tính phí | Theo periodic policy | Theo continuous backup tier/retention/cost |
| Hỗ trợ account/API/region | Kiểm tra compatibility | Kiểm tra compatibility |

**Đừng suy ra continuous luôn rẻ hơn hoặc nhanh hơn periodic**; chi phí và thời gian restore tùy dữ liệu, throughput, region, retention và features.

### 5.3. Lựa chọn retention tier

Nếu Azure hiển thị các lựa chọn tier continuous có retention khác nhau (ví dụ khoảng ngắn hơn và dài hơn), cần căn cứ:

- Thời gian trung bình phát hiện lỗi ghi/xóa.
- RPO/RTO của đơn hàng và hoạt động tài chính.
- Yêu cầu pháp lý/lưu dữ liệu theo vùng.
- Số lượng data/regions và chi phí backup.
- Khả năng phục hồi container/database riêng lẻ.
- Điều kiện thay đổi policy hoặc nâng/hạ retention mode được hỗ trợ.

**Không dựa vào một giới hạn retention cố định cho mọi API/SKU**; kiểm tra options ngay tại lúc tạo/đổi account và các giới hạn backup mode hiện hành.

### 5.4. Restore thường không là thao tác hoàn tác ngay trên primary

Với các quy trình continuous PITR được hỗ trợ, restore thường tạo **một Cosmos DB account mới**. Điều đó có nghĩa:

- Endpoint khác, tên tài khoản mới.
- Network ACL/Private Endpoint/Private DNS cần kiểm tra lại.
- Authorization và app identity cần có quyền data-plane đúng.
- Throughput, indexing, partition key, TTL, stored procedures, triggers, users/roles và các thuộc tính cần kiểm chứng.
- Region/consistency/backup settings phụ thuộc restore API và lựa chọn đích.
- Không tự động chuyển toàn bộ client traffic sang đích.
- Dữ liệu sau restore point cần reconciliation hoặc replay nếu vẫn hợp lệ.

Đây là lý do phải có **runbook cutover** ngay cả khi đã có continuous backup.

## 6. Những điều backup không thể tự giải quyết

### 6.1. Replication và failover không hoàn tác xóa nhầm

Một account multi-region có thể giúp phục vụ khi một region gặp sự cố. Nhưng nếu DELETE hợp lệ được replicate, failover sang region khác không biến dữ liệu thành bản trước khi xóa. **Replication là availability strategy, không phải lịch sử backup.**

### 6.2. Change feed là luồng thay đổi, không phải snapshot phục hồi hoàn chỉnh

Change feed hữu ích cho event-driven processing, analytics và xây dựng một số event log. Tuy nhiên:

- Đặc tính về captures của create/update/delete và thời gian lưu phụ thuộc **change feed mode** được hỗ trợ.
- Change feed thông thường không tự tạo bản sao đầy đủ có thể dùng PITR.
- Consumer có checkpoint, lag, TTL và error handling riêng.
- Muốn dùng change feed làm nguồn replay, cần **data contract và storage bền vững** riêng.

Không coi việc “đã bật change feed” là bảo hiểm rằng xóa nhầm có thể hoàn tác bằng một nút.

### 6.3. Export JSON không tự tương đương backup dịch vụ

Một job export documents ra Blob Storage/Data Lake có thể hữu ích cho archive và kiểm toán. Nhưng phải kiểm tra:

- Export có nhất quán tại một mốc thời gian không?
- Có ghi đủ partition key, id, timestamps và metadata cần thiết?
- Khôi phục có giữ indexing policy, TTL, throughput và unique key policy không?
- Có phù hợp encryption, IAM và data residency?
- Có khả năng replay những ghi xảy ra trong khi export không?
- Có kiểm thử import vào account mới với cùng partition design không?

Backup, replication, archive và export là **các lớp khác nhau**, đôi khi cần kết hợp để đáp ứng RPO/RTO.


## 7. Kiểm tra chính sách backup và khả năng restore hiện tại

### 7.1. Tiền điều kiện trước khi đọc resource

- Đã đăng nhập Azure bằng account được phép.
- Biết chính xác subscription ID, resource group và tên Cosmos DB account.
- Hiểu account API là NoSQL hay API khác.
- Có quyền **read metadata** trên account; không cần quyền đọc dữ liệu kinh doanh chỉ để xem backup policy.
- Trước khi thay đổi backup mode hoặc tạo restored account, đã được phê duyệt chi phí/ảnh hưởng hệ thống.

Ví dụ biến môi trường trong **Bash**:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"
~~~

`ACCOUNT` là placeholder cần thay bằng account thật; các lệnh `show` dưới đây chỉ đọc, còn lệnh thay policy/restore ở các mục sau là thao tác có thể phát sinh phí và ảnh hưởng an toàn dữ liệu.

### 7.2. Xem thông tin account và backup policy

~~~bash
# Không in keys hoặc connection strings.
az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, kind:kind, backupPolicy:backupPolicy, locations:locations, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Mục tiêu đọc:

- `backupPolicy.type` thể hiện periodic hoặc continuous theo response schema của Azure Resource Manager.
- Retention, tier/interval/redundancy có thể được biểu diễn khác nhau tùy loại policy và API version.
- Account locations cho biết vùng dữ liệu hiện đang được cấu hình.
- `publicNetworkAccess` là **một** tín hiệu về mạng, không đủ kết luận Private Endpoint/DNS và routing đã đúng.

Nếu query trả `null` hoặc field thiếu, **không đoán**. Hãy xem JSON metadata theo quyền được cấp, kiểm tra API version/CLI và tài liệu dịch vụ tương ứng; **không in `az cosmosdb keys list`** để debug policy.

### 7.3. Xem những tùy chọn restore được hỗ trợ

Azure CLI có nhóm lệnh chuyên về **restorable resources** và khôi phục Cosmos DB tùy phiên bản. Hãy tra chính các lệnh help có sẵn trước khi dựa vào tham số:

~~~bash
az cosmosdb --help
az cosmosdb restore --help
az cosmosdb restorable-database-account --help
~~~

Một số SDK/API cung cấp khả năng liệt kê **restorable database accounts, databases và containers** và mốc thời gian, với hạn chế tùy policy/API. Không dựa vào việc lệnh `restore --help` tồn tại để kết luận account đang dùng periodic cũng hỗ trợ cùng cơ chế self-service.

### 7.4. Không sửa backup mode trực tiếp khi chưa có change plan

Thay đổi backup mode giữa periodic và continuous có thể có **ràng buộc về chuyển đổi một chiều, API eligibility và các điều kiện account đang hoạt động**. Trước khi chọn/tạo mới:

1. Xác minh mode hiện tại.
2. Xác minh tính năng, retention và chi phí theo account API/region.
3. Ghi risk assessment và thời gian dự kiến.
4. Thử restore trong môi trường staging.
5. Ghi rõ liệu có cần recreate/migrate account hay không.
6. Được data owner, SRE và security phê duyệt.

**Không dùng `az cosmosdb update` với giá trị backup policy đoán mò**, vì một thay đổi policy có thể không dễ hoàn tác.

## 8. Runbook khôi phục sai dữ liệu với continuous backup

### 8.1. Kịch bản mẫu

Tài khoản `cos-orders-prod` có database `commerce`, container `orders` dùng partition key `/tenantId`.

- 13:10 UTC: dữ liệu đang đúng.
- 13:18 UTC: batch job lỗi ghi `status="CANCELLED"` cho nhiều đơn hợp lệ.
- 13:25 UTC: cảnh báo tỷ lệ đơn hủy tăng đột biến.
- 13:28 UTC: SRE dừng batch job và cô lập identity gây lỗi.
- 13:35 UTC: xác định mốc phục hồi hợp lệ trước 13:18.

**Quyết định nghiệp vụ quan trọng:** có thể cần khôi phục chỉ những đơn bị cập nhật sai thay vì thay toàn account, vì từ 13:18 đến 13:35 đã có đơn mới hợp lệ.

### 8.2. Các bước điều phối incident

**Bước 1 — Bảo toàn bằng chứng.** Ghi thời gian UTC, tên account/database/container, deployment/job version, `eventId`/correlation ID và số lượng item bị ảnh hưởng. Không in toàn bộ thông tin khách hàng trong báo cáo công khai.

**Bước 2 — Ngăn ghi sai tiếp tục.** Tạm dừng job hoặc giới hạn identity sai theo runbook. Không xóa account, xóa backups hoặc thay firewall/keys bừa bãi khi chưa điều tra quyền của các workloads hợp lệ.

**Bước 3 — Xác định restore point.** Dựa trên application audit logs, lịch deployment và các thao tác dữ liệu để chọn thời điểm **trước thay đổi đầu tiên gây lỗi**. So với earliest/latest restorable time và retention hiện có.

**Bước 4 — Chọn phạm vi phục hồi.** Cân nhắc account, database hoặc container tùy tính năng selective restore được API/mode hỗ trợ. Nếu không thể restore chọn lọc trực tiếp, khôi phục rộng hơn sang **account mới** rồi trích phần dữ liệu cần thiết.

**Bước 5 — Khôi phục sang môi trường đích.** Thực hiện restore theo Azure portal/CLI/API được hỗ trợ, chọn account đích không trùng tên và các thông số vùng/backup mode hợp lệ. Đây là **thao tác ghi có thể phát sinh phí**; cần change approval.

**Bước 6 — Xác minh metadata.** Kiểm tra danh sách databases/containers, partition key, indexing policy, unique keys, TTL, throughput mode, regions, stored procedures/triggers khi có, và security/network configuration.

**Bước 7 — Xác minh dữ liệu.** Đối chiếu các order IDs, số items theo tenant/partition, sample business checksums, timestamps và các transaction quan trọng. Không chỉ nhìn “portal báo restore thành công”.

**Bước 8 — Xử lý phần ghi hợp lệ sau restore point.** Đối chiếu audit/change logs và nguồn hệ thống tin cậy, replay/merge **có idempotency** để tránh bỏ sót hoặc ghi trùng. Xem xét các event đã gửi sang Service Bus, Event Hubs hoặc hệ thống thanh toán.

**Bước 9 — Cutover có kiểm soát.** Cập nhật endpoint, identity role assignments, Private Endpoint, DNS, secret references và application config theo phương án. Tránh dual writes không được phối hợp.

**Bước 10 — Giám sát và đóng incident.** Theo dõi 429, 401/403, 5xx, p95 latency, failed requests, data invariants và ngân sách. Chỉ dọn resources phục hồi khi đã được phê duyệt.

### 8.3. Những kiểm tra trước khi đưa restored account vào production

| Hạng mục | Câu hỏi nghiệm thu |
| --- | --- |
| API/account type | NoSQL và backup mode có đúng? |
| Region/consistency | Region, consistency, preferred locations có đáp ứng thiết kế? |
| Database/container | Đúng tên và số lượng cần thiết? |
| Partition key path | `/tenantId` và logical partitions chính xác? |
| Indexing/TTL | Policy giống kỳ vọng, không tự hết hạn dữ liệu ngoài ý muốn? |
| Throughput | Autoscale/provisioned RU/s đủ cho traffic cần phục vụ? |
| Authentication | App identity có role assignment tại data-plane scope đúng? |
| Network | Private Endpoint/DNS/firewall và public access policy đúng? |
| CMK/encryption | Key Vault/key/identity có sẵn và hợp lệ nếu dùng CMK? |
| Application | SDK endpoint/credential/client region config và retry hoạt động? |
| Data validation | Sample và reconciliation theo tenant/order ID đã hoàn tất? |
| Monitoring | Diagnostic settings, alerts và budget có owner? |
| Rollback | Có đường quay lại an toàn nếu cutover không đạt SLO? |

Không mặc định một restored account sẽ **kế thừa** toàn bộ Role Assignments, network policy, Key Vault permissions, alerts và CI/CD mappings như production account ban đầu. Cần xác minh từng thuộc tính.

### 8.4. Có thể vừa restore vừa giữ traffic production không?

Có thể chuẩn bị restored account **song song** để kiểm tra mà chưa chuyển traffic. Nhưng không phải dữ liệu đã khôi phục sẽ liên tục nhận các writes tiếp theo của original account. Nếu muốn cutover, cần chiến lược:

- Ngừng ghi trong cửa sổ ngắn (maintenance/freeze).
- Dùng event log tin cậy để replay.
- Dùng application-level sync/merge có kiểm chứng.
- Định nghĩa nguồn sự thật nếu có hai hướng ghi.
- Đánh giá TTL, unique key, partition key và xung đột khi merge.

Không tạo hai endpoints cùng nhận writes trong lúc thiếu conflict resolution; điều này có thể khiến phục hồi khó hơn.

### 8.5. Kiểm tra riêng kịch bản container bị xóa

Nếu container bị xóa, việc restore có thể phụ thuộc mốc xóa và khả năng resource-level restore. Hãy kiểm tra restorable metadata và constraints của tài khoản; không coi container vừa bị xóa có thể được “undelete” ngay trên account gốc chỉ vì có PITR.

### 8.6. Khi mất thông tin account keys/credential

Restore dữ liệu **không phải** biện pháp đầu tiên để xử lý credential leak. Cần khóa/revoke credential, rotate keys hoặc gỡ role assignments bị lộ, kiểm tra data access logs và duy trì bằng chứng. Chỉ thực hiện restore khi có dấu hiệu dữ liệu bị sửa/xóa và đã đánh giá phạm vi ảnh hưởng.

## 9. Backup và restore không thay thế quản trị quyền

### 9.1. Hai ranh giới quyền khác nhau

**Control plane** quản lý Azure resource: account, regions, backups, networking, throughput, identity và các cấu hình. **Data plane** đọc/ghi items trong databases/containers.

~~~mermaid
flowchart TB
    ADMIN["Azure operator / IaC"]
    APP["Order API\nManaged identity"]
    ARM["Azure Resource Manager\nControl plane"]
    ACC["Cosmos DB account config"]
    AUTH["Cosmos DB NoSQL\nData-plane authorization"]
    DOC["Database/Container/Items"]
    ADMIN -->|"Azure RBAC permission"| ARM --> ACC
    APP -->|"Entra token / SDK"| AUTH --> DOC
~~~

**Azure RBAC Contributor trên account không tự bảo đảm có thể đọc mọi item khi ứng dụng dùng Cosmos DB native data-plane RBAC.** Ngược lại, một identity có quyền `readMetadata`/`readItems` không được mặc định quyền sửa backup policy của Azure Resource Manager.

### 9.2. Những loại credential cần phân biệt

| Cơ chế | Dùng ở đâu | Rủi ro và lưu ý |
| --- | --- | --- |
| **Account primary/secondary keys** | Auth bằng khóa tài khoản theo API hỗ trợ | Quyền rất rộng; phải giới hạn phân phối và rotate |
| **Read-only keys** | Một số tình huống read-only access | Vẫn là shared secrets và có phạm vi rộng; không là tenant isolation |
| **Microsoft Entra ID** | Identity-based auth, NoSQL data-plane RBAC khi hỗ trợ | Cần role assignment trong Cosmos DB và token refresh |
| **Managed identity** | Identity của Azure-hosted workload | Không tự có data-plane rights nếu chưa gán |
| **Resource tokens** | Cấp quyền tạm theo phạm vi khi API/support phù hợp | Cần backend trusted phát token, giới hạn TTL và scope |
| **Connection string** | Có thể chứa endpoint + key | Không log/commit, không đưa cho client browser/mobile |
| **Key Vault reference** | Cấp secrets/config từ vault | Quyền truy cập vault và cache/rotation cần kiểm tra |

**Không đặt primary key trong JavaScript chạy trên trình duyệt.** Browser/mobile client phải được bảo vệ bằng backend authorization hoặc cơ chế token có scope/TTL và kiểm tra tính năng hỗ trợ; không cấp quyền toàn account cho client không tin cậy.

### 9.3. Ai cần quyền gì?

Ví dụ ứng dụng:

- `orders-api`: đọc/ghi items ở `commerce/orders`.
- `fraud-worker`: đọc một số fields/items theo thiết kế, không xóa container.
- `audit-reader`: chỉ đọc container audit.
- `platform-admin`: quản trị account/backup/network theo vai trò Azure.
- `security-operator`: audit config, kiểm tra logs, quản lý incidents với quyền phù hợp.
- `break-glass`: quy trình truy cập khẩn cấp có MFA, logging, thời hạn và phê duyệt.

Quyền càng lớn, blast radius càng cao. Không cấp `Owner` hay account primary key chỉ để API đọc một order.

## 10. Microsoft Entra ID và Cosmos DB for NoSQL data-plane RBAC

### 10.1. Lý do chọn Entra ID

Microsoft Entra ID giúp ứng dụng Azure dùng **managed identity** thay cho khóa bí mật lâu dài. Với Cosmos DB for NoSQL, có mô hình **native data-plane RBAC** để cấp các quyền thích hợp cho data access.

Lợi ích:

- Không phải nhúng account key vào code.
- Có thể gán quyền cho đúng service identity.
- Thu hồi/đổi quyền theo principal và scope.
- Audit các thay đổi role assignments theo cơ chế quan sát.
- Phân tách read-only API với read-write worker.

### 10.2. Role definition và role assignment

Cosmos DB for NoSQL cung cấp các **built-in data-plane roles** cùng khả năng định nghĩa custom roles theo API hỗ trợ. Hai tên thường gặp:

- **Cosmos DB Built-in Data Reader**: thao tác đọc phù hợp được role định nghĩa cho phép.
- **Cosmos DB Built-in Data Contributor**: thao tác đọc/ghi data phù hợp được role định nghĩa cho phép.

**Tên roles này thuộc Cosmos DB for NoSQL data-plane RBAC, không tự đồng nghĩa Azure IAM roles "Reader"/"Contributor".** Cần kiểm tra chính xác dataActions của role và scope thực tế, tránh suy luận từ tên.

Mỗi role assignment gồm:

1. **Principal object ID** của user, group, service principal hoặc managed identity.
2. **Role definition ID** trong Cosmos DB account.
3. **Scope** theo account/database/container path được hỗ trợ.

Ví dụ scope:

~~~text
/                          (phạm vi gốc account)
/dbs/commerce              (database)
/dbs/commerce/colls/orders  (container orders)
~~~

### 10.3. Liệt kê roles và assignments bằng Azure CLI

Các lệnh **chỉ đọc**:

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"

az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json

az cosmosdb sql role assignment list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

Trước khi gán role, xác nhận **account API là NoSQL**, **identity object ID** đúng, **role definition ID** và **scope**. Đừng dùng ID của app registration/client ID nếu command yêu cầu **object ID (principal ID)**.

### 10.4. Gán quyền dữ liệu cho managed identity (chỉ môi trường được phép)

Mẫu lệnh dưới đây **làm thay đổi quyền truy cập**:

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"

PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_OBJECT_ID>"
ROLE_DEFINITION_ID="<COSMOS_SQL_DATA_ROLE_DEFINITION_ID>"
ROLE_SCOPE="/dbs/commerce/colls/orders"

az cosmosdb sql role assignment create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --principal-id "$PRINCIPAL_OBJECT_ID" \
  --role-definition-id "$ROLE_DEFINITION_ID" \
  --scope "$ROLE_SCOPE"
~~~

**Không chạy nếu principal/scope/role chưa được review.** Sau khi gán, đọc lại assignments và thử cả **positive tests** (đọc/ghi đúng container) lẫn **negative tests** (không đọc được container ngoài phạm vi) theo dữ liệu lab.

Có thể có **độ trễ propagation** của quyền; xử lý 403 bằng việc kiểm tra role/scope/network và chờ propagation trong phạm vi hợp lý, không lập tức phát account key toàn quyền để “chữa”.

### 10.5. Chọn custom role khi quyền tích hợp quá rộng

Ứng dụng chỉ cần đọc items nhưng built-in role có thêm dataActions không mong muốn thì cân nhắc custom role với tập action tối thiểu được hỗ trợ.

Thiết kế role cần dựa trên **dataActions thật sự cần** cho SDK, như metadata read/query items; không chỉ cho action `read item` rồi bỏ permissions cần để query container. Với multi-tenant ứng dụng, RBAC scope container **không tự lọc hàng theo tenantId**: backend phải xác thực tenant, xác thực partition key và kiểm soát truy cập nghiệp vụ.

### 10.6. Thử negative authorization

Ví dụ:

| Kiểm thử | Expected |
| --- | --- |
| `orders-api` đọc item thuộc container `orders` hợp lệ | Thành công |
| `orders-api` ghi item ở `orders` nếu có Contributor | Thành công |
| `orders-api` đọc container `auditEvents` khi không có quyền | Bị từ chối |
| `orders-api` liệt kê account keys | Bị từ chối theo quyền quản trị |
| Principal không có data-role đọc Cosmos DB | Data access bị từ chối |
| Principal có data-role nhưng network bị chặn | Connection vẫn thất bại |
| Principal có IAM Contributor nhưng không có data-role | Không tự suy ra quyền đọc item qua Entra RBAC |

Những tests này dùng identity và dữ liệu **riêng cho lab**; không thực hiện phép thử phá hủy production.

## 11. Sử dụng Azure Cosmos SDK với managed identity

### 11.1. Đường đi xác thực

~~~mermaid
sequenceDiagram
    participant A as API / Azure workload
    participant I as Managed Identity / Entra ID
    participant C as Cosmos DB for NoSQL
    A->>I: Yêu cầu access token
    I-->>A: Access token
    A->>C: HTTPS request + Entra token
    C->>C: Data-plane RBAC + network policy
    C-->>A: Item / lỗi 401,403
~~~

Ứng dụng không phải lưu master key khi identity-based auth được cấu hình đúng. **Entra login thành công không có nghĩa Cosmos DB role assignment đúng**; đây là hai bước.

### 11.2. Python SDK đọc document an toàn

Ví dụ `azure-cosmos` và `azure-identity`, dùng `DefaultAzureCredential`:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]

client = CosmosClient(
    url=endpoint,
    credential=DefaultAzureCredential(),
)

database = client.get_database_client("commerce")
container = database.get_container_client("orders")

# Container /tenantId. Đọc item bằng cả id và partition key value.
item = container.read_item(
    item="ORD-1001",
    partition_key="tenant-01",
)

print({
    "id": item.get("id"),
    "tenantId": item.get("tenantId"),
    "status": item.get("status"),
})
~~~

**Điều kiện:** account là Cosmos DB for NoSQL, SDK version hỗ trợ token credential, principal đã có data-plane role phù hợp trên container, network/TLS thông và item mẫu tồn tại. Nếu dùng `DefaultAzureCredential` tại máy developer, identity có thể khác với managed identity của deployment; xác minh tenant/principal thật, không suy đoán.

### 11.3. Vì sao phải dùng partition key đúng?

Với container `/tenantId`:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "tenant-01",
  "orderId": "ORD-1001",
  "status": "NEW"
}
~~~

Point read cần **id + partition key** để định vị item hiệu quả. Một application identity có quyền trên container **không tự có row-level per-tenant authorization**. Backend phải xác thực tenant từ identity người dùng và bảo đảm `partition_key` khớp tenant đã được ủy quyền; không tin giá trị `tenantId` do client tự đưa vào request nếu chưa kiểm tra.

### 11.4. Khi nào token hết hạn?

SDK/identity provider có thể quản lý token refresh tùy phiên bản và runtime. Ứng dụng vẫn cần:

- Duy trì phiên bản SDK được hỗ trợ.
- Không giữ access token thủ công vô thời hạn.
- Đo 401/403 và retry có điều kiện phù hợp.
- Không log token.
- Định nghĩa fallback/alert khi Entra identity unavailable.
- Kiểm tra gán role cho **identity thực của workload** sau khi đổi slot/revision/service principal.

### 11.5. Kết nối Java SDK

Ứng dụng Java có thể dùng Azure Cosmos Java SDK và Azure Identity:

~~~java
// Minh họa API builder: yêu cầu azure-cosmos + azure-identity
// với phiên bản SDK hỗ trợ credential/tokenCredential.
TokenCredential credential = new DefaultAzureCredentialBuilder().build();

CosmosClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("COSMOS_ENDPOINT"))
    .credential(credential)
    .buildClient();

CosmosContainer container = client
    .getDatabase("commerce")
    .getContainer("orders");

CosmosItemResponse<OrderDocument> response =
    container.readItem("ORD-1001",
        new PartitionKey("tenant-01"),
        OrderDocument.class);

// Đóng client khi ứng dụng thực sự shutdown, không tạo mỗi request.
client.close();
~~~

Đây là **đoạn mã minh họa**, không phải chương trình Java đầy đủ: cần imports, dependency versions, model `OrderDocument` và cấu hình network/regions. API builder có thể khác giữa các major SDK versions; kiểm tra đúng SDK đang dùng trước khi triển khai. Trong server application, nên dùng **CosmosClient singleton/lifecycle rõ ràng** để tái sử dụng connections, tránh tạo mới cho mỗi HTTP request.


## 12. Network security: firewall, VNet và Private Endpoint

### 12.1. Kiến trúc phòng thủ nhiều lớp

Một tài khoản Cosmos DB có thể có data endpoint public. Đường truyền TLS và authentication giúp bảo vệ request, nhưng **không tự hạn chế nguồn nào có thể thử kết nối vào endpoint**. Trong production thường kết hợp:

1. Public network access policy hoặc network ACL/IP allowlist phù hợp.
2. VNet service endpoint hoặc **Private Endpoint** theo API và khả năng dịch vụ.
3. Private DNS Zone, VNet links và routing từ workload.
4. Managed identity + data-plane RBAC.
5. TLS certificate validation và observability.
6. Application-level authorization theo tenant.

### 12.2. Các mô hình mạng

| Phương án | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Public endpoint + IP firewall | Chỉ cho public egress IP đã được phê duyệt | IP NAT/VPN có thể khác IP máy client |
| VNet service endpoint + ACL | Cho phép truy cập từ subnet được cấu hình theo tính năng | Không tự tạo private IP như Private Link |
| **Private Endpoint** | Private IP/interface trong VNet đi tới Cosmos DB | Cần Private DNS, approval, routing |
| Tắt public network access | Ngăn data path công khai theo chính sách | Cần xác minh private path trước |
| Private DNS | FQDN phân giải theo đường riêng tư | Không phải authentication hoặc data-plane permission |

Không giả định **Private Endpoint tự động tắt public access** nếu account vẫn được cấu hình cho đường công khai. Phải xác minh cả chính sách public access lẫn private path.

### 12.3. Luồng Private Endpoint với Cosmos DB for NoSQL

~~~mermaid
flowchart LR
    API["AKS / App Service\nVNet-integrated workload"]
    DNS["Private DNS Zone\nCosmos DB NoSQL"]
    PE["Private Endpoint\nprivate IP"]
    COS["Cosmos DB account\nNoSQL"]
    AUTH["Entra ID + NoSQL data RBAC"]
    API --> DNS --> PE --> COS
    AUTH -.->|"Authorization"| COS
~~~

Để triển khai:

1. Xác nhận **API và Private Link subresource** của account là phù hợp.
2. Tạo Private Endpoint trong VNet/subnet được phép.
3. Chờ/phê duyệt private endpoint connection theo policy.
4. Thiết lập Private DNS Zone và VNet links/forwarding đúng.
5. Từ **chính VM/Pod/Container App/App Service** đang chạy SDK, kiểm tra account hostname phân giải về đường private như thiết kế.
6. Kiểm tra TLS, identity và data-plane role assignments.
7. Chỉ sau khi private path được xác nhận, tắt public network access nếu đó là yêu cầu bảo mật.
8. Chạy negative test từ nguồn public không được phép.

Với Cosmos DB for NoSQL, private DNS thường sử dụng zone kiểu `privatelink.documents.azure.com`. **Không tự đổi hostname SDK sang private IP**, không dùng zone cho MongoDB/Cassandra trên account NoSQL và không tắt TLS validation.

### 12.4. Gateway và Direct connection modes

Azure Cosmos DB for NoSQL SDK có các connection modes thường được gọi là:

- **Gateway:** giao tiếp qua gateway HTTPS, thường cổng 443; có thể dễ cấu hình với firewall hạn chế.
- **Direct:** tạo thêm TCP connections tới các replicas/backends theo cơ chế SDK/region; thường giảm latency trong điều kiện thích hợp.

Không mặc định Direct mode chỉ sử dụng cổng 443. Các port ranges/endpoints có thể khác tùy API, SDK, Private Endpoint và dịch vụ. **Kiểm tra networking requirements của đúng SDK hiện hành** thay vì hard-code một dải cổng cũ.

Nếu Gateway mode hoạt động nhưng Direct mode timeout, cần phân tích NSG, outbound route, private DNS và TCP ports cho Direct mode trước khi đổi credential.

### 12.5. Các kiểm tra chỉ đọc

Linux/macOS:

~~~bash
ACCOUNT="cos-orders-prod"
COSMOS_HOST="$ACCOUNT.documents.azure.com"

nslookup "$COSMOS_HOST"
nc -vz "$COSMOS_HOST" 443
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName cos-orders-prod.documents.azure.com
Test-NetConnection cos-orders-prod.documents.azure.com -Port 443
~~~

Lệnh thành công **không chứng minh role/secret đã hợp lệ**. DNS từ laptop cũng không chứng minh Pod trong AKS dùng cùng DNS/egress path.

## 13. Account keys, resource tokens và secret rotation

### 13.1. Vì sao cần hạn chế account key?

Account keys và connection strings có thể cấp quyền **rất rộng** theo API/account configuration. Nếu đưa key vào JavaScript browser/mobile app, kẻ tấn công có thể dùng key trực tiếp, vượt qua lớp xác thực người dùng của backend.

Ưu tiên **Entra ID + native data-plane RBAC** khi API/SDK hỗ trợ. Chỉ giữ key-based auth nếu có yêu cầu tương thích, được security review và quản lý vòng đời secret.

### 13.2. Primary và secondary keys

Với account hỗ trợ primary/secondary keys, cơ chế xoay vòng có thể là:

~~~text
Clients đang dùng primary
  → Chuẩn bị/triển khai secondary secret qua vault
  → Kiểm thử clients dùng secondary
  → Chuyển các clients sang secondary
  → Regenerate primary theo change approval
  → Theo dõi lỗi auth và chuẩn bị chu kỳ rotation tiếp theo
~~~

Không regenerate key đang được ứng dụng sử dụng mà không có kế hoạch chuyển đổi. Tránh chạy `az cosmosdb keys list` rồi copy kết quả có secret vào logs/chat/ticket.

### 13.3. Read-only key không phải tenant isolation

Read-only key (khi được cung cấp) có thể giới hạn write operations, nhưng vẫn là **shared secret với phạm vi đọc rộng**. Nó không tự chứng minh rằng tenant A không xem dữ liệu tenant B trong cùng container.

### 13.4. Resource tokens

Một số API/SDK Cosmos DB hỗ trợ **resource tokens** cấp quyền hạn chế theo phạm vi và thời gian. Backend tin cậy phải:

- Xác thực người dùng và tenant trước khi phát token.
- Cấp scope tối thiểu và thời hạn ngắn.
- Không ghi token vào logs.
- Kiểm tra SDK/permission model được API hỗ trợ.
- Có kế hoạch revoke/expiry và negative access tests.

Nếu khó bảo đảm giới hạn token từ untrusted clients, giữ Cosmos DB access **chỉ ở backend server-side** rồi trả dữ liệu đã được ủy quyền.

### 13.5. Secrets management

- Lưu credentials trong Key Vault hoặc secret manager được quản trị.
- Tách Dev/Staging/Production.
- Cấp quyền truy cập Key Vault theo managed identity tối thiểu.
- Không commit secrets vào source, Docker image, pipeline logs hoặc client bundles.
- Rotate theo lịch và khi có incident.
- Kiểm tra khả năng ứng dụng nhận secret mới, reconnect và phục hồi.
- Không dùng account primary key làm phương án fallback thường trực khi một role assignment bị sai.

## 14. Encryption, CMK và bảo vệ dữ liệu theo nhiều lớp

### 14.1. At rest và in transit

Cosmos DB có cơ chế mã hóa dữ liệu **at rest** của dịch vụ. Trên đường truyền, client cần **TLS** và xác minh hostname/certificate. Đây là hai lớp khác với authorization.

Một account có encryption đúng vẫn có thể bị xóa dữ liệu nếu app identity có quyền quá rộng. Ngược lại, private endpoint không có nghĩa truyền thông được miễn kiểm tra TLS.

### 14.2. Customer-managed keys (CMK)

Trong các account/API/configuration được hỗ trợ, Cosmos DB có thể dùng **customer-managed keys** với Key Vault/managed identity và chính sách quản lý khóa tương ứng.

Cần chuẩn bị:

1. Key Vault hoặc kho khóa được dịch vụ hỗ trợ, quyền truy cập và region/compliance.
2. Managed identity/permission để dịch vụ truy cập khóa.
3. Key rotation, versioning và policy giữ các key versions cần cho restore.
4. Quy trình khi key bị disabled, deleted hoặc Vault/network unavailable.
5. Xác minh tài khoản **được restore** có thể dùng key hợp lệ.
6. Kiểm tra tính tương thích giữa CMK, regions, backup policy và Private Link.
7. Audit mọi thay đổi key/role/key vault access.

**Vô hiệu hóa/mất key có thể khiến dữ liệu không truy cập được** theo cơ chế dịch vụ. Không bật CMK khi chưa có runbook khôi phục khả năng giải mã.

### 14.3. Bảng phân biệt các biện pháp

| Cơ chế | Bảo vệ chính | Không tự giải quyết |
| --- | --- | --- |
| Private Endpoint | Data path riêng tư | Không cấp/kiểm tra quyền đọc dữ liệu |
| Entra ID + native data RBAC | Authorization thao tác data | Không thay routing/TLS |
| CMK / encryption at rest | Bảo vệ dữ liệu lưu trữ | Không ngăn DELETE hợp lệ do bug |
| TLS | Kết nối được mã hóa, xác minh server | Không xác minh user business role |
| Backup/PITR | Khôi phục lịch sử dữ liệu | Không ngăn truy cập sai đang diễn ra |
| Audit/alerts | Phát hiện và điều tra | Không tự tái tạo dữ liệu bị xóa |
| App tenant checks | Phân quyền nghiệp vụ | Không thay account networking |

### 14.4. Multi-tenant và partition key

Container `orders` dùng partition key `/tenantId` giúp tổ chức dữ liệu, nhưng **không tự thực thi row-level tenant authorization**. Một managed identity có quyền đọc toàn container có thể được SDK dùng để query dữ liệu nhiều tenants nếu backend không kiểm soát.

Do đó:

- Xác minh tenant từ identity đã xác thực, không chỉ từ body request.
- Ép server-side partition key và filter tenant.
- Có negative tests cross-tenant.
- Cân nhắc tách container/account nếu cần trust boundary mạnh.
- Không đưa thông tin nhạy cảm vào logs/partition keys không cần thiết.

## 15. Azure Monitor, diagnostic logs và audit

### 15.1. Ba loại telemetry

1. **Service metrics:** RU consumption, requests, HTTP 429, storage, latency, availability và các số liệu được account/API hỗ trợ.
2. **Control-plane audit:** Azure Activity Log về thay đổi account, regions, firewall, roles, backup mode, restore actions.
3. **Application/data-plane telemetry:** identity, tenant, operation, item IDs, business event/correlation IDs và dữ liệu lỗi cần thiết.

Không mặc định Azure Activity Log là transaction log của từng item. Với incident DELETE hàng loạt, thường phải kết hợp application audit events và diagnostic logs **đã được bật trước sự cố**.

### 15.2. Các tín hiệu quan trọng

| Metric hoặc event | Vì sao đáng theo dõi? |
| --- | --- |
| Normalized RU consumption | Cận công suất, tác vụ bất thường |
| 429 / throttled requests | Request vượt available RU hoặc hot partitions |
| 401/403 | Lỗi credential, role/scope hoặc network policy |
| Data storage/partition growth | TTL, chi phí, hot partitions |
| p95/p99 request latency | Network/region/query/SDK client issues |
| Backup policy change | Có ai giảm khả năng phục hồi ngoài change window? |
| Restore account created | Có thao tác phục hồi hợp lệ hay bất thường? |
| SQL role assignments changed | Có ai cấp quyền dữ liệu quá rộng? |
| Key regeneration | Key rotation theo lịch hay incident? |
| Public access/firewall change | Có mở mạng ngoài policy? |
| Unexpected mass updates/deletes | Có bug, script sai hoặc credential compromise? |
| Diagnostic settings disabled | Có giảm audit evidence bất thường? |

Azure Monitor metric definitions/dimensions có thể khác theo API/tier/region. Không dùng tên metrics của một tài khoản API khác mà chưa xác minh.

### 15.3. Liệt kê metric definitions

~~~bash
COSMOS_ID=$(az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$COSMOS_ID" \
  --output table
~~~

Đây là lệnh chỉ đọc. Chọn metric, time grain, aggregation và dimensions theo definitions trả về. Không suy từ một giá trị 429 tổng rằng backup đang lỗi; phải phân biệt request throttling và restore operation.

### 15.4. Application audit log ví dụ

~~~json
{
  "timestampUtc": "2026-11-20T13:18:09Z",
  "service": "orders-migration",
  "deploymentId": "release-42",
  "operation": "PatchOrder",
  "account": "cos-orders-prod",
  "database": "commerce",
  "container": "orders",
  "tenantId": "tenant-01",
  "eventId": "job-42-00013",
  "result": "success",
  "requestChargeRU": 7.1
}
~~~

Đây là **schema minh họa do ứng dụng định nghĩa**, không phải tài liệu khẳng định Azure tự ghi sẵn toàn bộ fields. Hạn chế logs chứa PII, keys, tokens hoặc full document bodies. Gắn correlation IDs từ API tới database operations giúp xác định chính xác thời điểm lỗi.

### 15.5. Alert thiết thực

- Mass delete/update vượt baseline theo tenant/container.
- Backup policy hoặc role assignment thay ngoài change window.
- Public network access bật lại ngoài kế hoạch.
- 401/403 tăng bất thường, credential leak nghi vấn.
- RU 429/latency tăng, storage capacity gần giới hạn.
- Restore process không hoàn thành hoặc restore drill quá RTO.
- Account key regeneration không theo lịch.
- Diagnostics bị tắt hoặc workspace không nhận logs.
- Cost anomaly do restored account tồn tại quá lâu.

Mỗi cảnh báo cần **owner, severity, hành động, ngưỡng và hướng khôi phục**, không chỉ gửi email không ai xử lý.

## 16. Chi phí backup, restore và bảo vệ truy cập

### 16.1. Các nguồn chi phí

| Hạng mục | Động lực chi phí |
| --- | --- |
| Cosmos DB RU/s | Provisioned/autoscale throughput theo mode |
| Storage | Dữ liệu, index, replication/regions |
| Periodic/continuous backup | Mode, retention, redundancy theo chính sách giá |
| Restored account | Throughput/storage hoạt động song song |
| Multi-region | Storage/throughput/replication traffic và mô hình tính phí |
| Private Endpoint | Resources/network data processing |
| Key Vault / CMK | Key operations và quản lý khóa |
| Diagnostic logs | Log Analytics ingestion/retention, archive |
| Export/DR copy | Blob/Data Lake, compute và egress |
| Drill khôi phục | Tạo restored account, test workloads, cleanup |

Không đưa một mức giá cố định vì phụ thuộc region, currency, account API/tier, throughput, retention và bảng giá lúc triển khai.

### 16.2. Ước lượng RU, không nhầm với giá

Giả sử 1.000 requests/giây và mỗi request trung bình 5 RU:

\[
1000\ \text{requests/s}\times5\ \text{RU/request}=5000\ \text{RU/s}
\]

Đây chỉ là mức tiêu thụ RU trung bình, **không đủ** để chọn throughput chính xác hoặc tính hóa đơn. Peak, hot partition, query pattern, indexes, regions, retries và autoscale đều ảnh hưởng. Backup và restored accounts phát sinh chi phí riêng.

### 16.3. Lập budget cho restore song song

Một restore drill có thể tạm thời giữ **hai tài khoản cùng lúc**: account cũ và restored account. Cần budget cho capacity chạy đồng thời, Private Endpoints, telemetry và data validation. Không dọn restored account trước khi dữ liệu được kiểm chứng và data owner ký xác nhận.

### 16.4. Tối ưu mà không hạ thấp tiêu chuẩn phục hồi

- Chọn retention theo thời gian phát hiện lỗi và yêu cầu compliance.
- Tối ưu partition key/query để tránh RU nóng.
- Dọn stale test/restored accounts có approval.
- Không tắt audit logs quan trọng chỉ để giảm ingestion.
- Quản lý tài khoản/network/role qua IaC và review.
- Kiểm tra backup/restore thông qua diễn tập định kỳ.
- Dự toán tăng trưởng dữ liệu, multi-region và capacity.


## 17. Runbook xử lý sự cố: mất dữ liệu, lỗi xác thực và không kết nối được

### 17.1. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| DNS không phân giải được endpoint | Private DNS Zone/forwarding/VNet link sai | `nslookup` từ đúng môi trường client |
| TCP/TLS timeout | Private Endpoint, NSG, route, firewall, SDK Direct mode | Gateway vs Direct requirements, network path |
| HTTP 401 Unauthorized | Token/key/credential không hợp lệ hoặc hết hạn | Token audience/identity/key rotation |
| HTTP 403 Forbidden | Data-plane role/scope, firewall/network ACL | Role assignments, IP/VNet restrictions, diagnostic substatus |
| HTTP 429 Too Many Requests | RU limit, hot partition hoặc load tăng | RU consumption/partition metrics, SDK retry |
| Query từ tenant A đọc dữ liệu tenant B | Backend thiếu tenant authorization | App policy, partition key validation, token scope |
| Data thiếu sau migration | DELETE/UPDATE hợp lệ nhưng sai logic | Audit timeline, backups, restore point |
| PITR không thấy mốc cần chọn | Ngoài retention hoặc unsupported mode/API | Backup policy, earliest/latest restorable time |
| Restore không tạo được đích | Region/feature/permission/cost/quota | Restorable resources, scope, Azure operations |
| Restored account 403 | Role assignments hoặc keys/config không đúng | Data-plane roles, identity, policy |
| Restored account network timeout | Private Endpoint/DNS chưa được dựng | Private path, public access, SDK mode |
| Item không đọc được bằng ID | Sai partition key hoặc item đã bị xóa | `id` + `partition_key`, container metadata |
| CMK/key vault error | Key disabled/missing permission/network | Key Vault roles, key version, identity |
| Chi phí tăng sau restore drill | Restored account/Private Endpoint/logs chưa dọn | Cost Management, inventory và owner |
| Multi-region failover không mang dữ liệu cũ trở lại | Replication không phải backup | PITR/restore, reconciliation |

### 17.2. Bước 1 — Phân loại sự cố

Trước khi thay cấu hình:

- **Availability/network:** ứng dụng không tới được account hoặc region.
- **Authentication/authorization:** request tới dịch vụ nhưng bị 401/403.
- **Throttling/performance:** SDK trả 429, latency hoặc RU cao.
- **Data corruption/deletion:** request có thể vẫn thành công nhưng giá trị nghiệp vụ sai.
- **Backup/restore issue:** không thể chọn mốc/đích hoặc restore validation thất bại.
- **Credential compromise:** khóa/identity bị lộ, có thể có data access bất thường.

Một sự cố có thể liên quan nhiều lớp; cần ghi thời gian UTC và operation IDs để nối bằng chứng.

### 17.3. Bước 2 — Xác định resource đúng

~~~bash
az account show \
  --query "{name:name, subscriptionId:id}" \
  --output json

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, kind:kind, backupPolicy:backupPolicy, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Không dump primary keys vào output. Phải chắc workload đang hướng tới account **prod/staging** nào, tránh sửa nhầm tài nguyên.

### 17.4. Bước 3 — Network và TLS

- Kiểm tra DNS FQDN từ Pod/VM/host chạy SDK.
- Nếu account có Private Endpoint, xác minh DNS private và connection state.
- Kiểm tra NSG/UDR/firewall/outbound restrictions.
- Nếu SDK Direct mode lỗi, thử logic kiểm tra Gateway path theo runbook và so sánh TCP ports; **không đổi credential để giải quyết timeout mạng**.
- Không dùng private IP thay hostname, không tắt TLS certificate validation.
- Thực hiện negative test từ nguồn không được phép sau khi sửa.

### 17.5. Bước 4 — Role/identity

Với SDK Entra authentication:

1. Identity đang chạy thực tế là ai (client ID, principal object ID, tenant)?
2. Có role assignment native data-plane đúng role/scope không?
3. Role definition có dataActions phù hợp thao tác query/read/write?
4. Azure IAM role có bị nhầm với Cosmos SQL data-plane RBAC không?
5. Role vừa gán có cần thời gian propagation?
6. Network account có cho request qua không?
7. SDK credentials có đang lấy token của developer thay vì managed identity production?

Không “chữa” 403 bằng cách cấp `Owner` hoặc chèn primary key vào app khi chưa xác định nguyên nhân.

### 17.6. Bước 5 — Khôi phục dữ liệu khi đã xác định có ghi sai

1. Dừng tác nhân đang ghi sai hoặc cô lập identity.
2. Lưu audit evidence và event timeline.
3. Xác định **thời điểm sai bắt đầu**, mốc UTC trước lỗi.
4. Kiểm tra policy, retention và restore eligibility.
5. Khôi phục ra resource mới nếu quy trình yêu cầu.
6. So sánh dữ liệu trước/sau bằng business IDs và tenant/partition.
7. Phân tích writes hợp lệ sau restore point.
8. Kiểm tra identity, Private Endpoint, RU/s, CMK, alerts của đích.
9. Có sign-off mới thực hiện cutover/merge.
10. Giám sát và dọn tạm resources khi đã an toàn.

### 17.7. Bước 6 — Hậu kiểm sau khôi phục

- Có đúng số lượng documents quan trọng theo tenants?
- Item IDs và partition key values có trùng bản gốc hợp lệ?
- Các giao dịch thanh toán, vận chuyển, email và downstream events có bị phát lại không?
- API trả cùng contract và p95 latency đạt SLO?
- Security policies, logs, alerts và budgets đúng?
- Backup policy trên restored account có còn đáp ứng RPO/retention?
- Có incident postmortem để sửa code, permission và quy trình?

**Khôi phục thành công về mặt dịch vụ chưa phải phục hồi hoàn tất về mặt nghiệp vụ.**

## 18. Thiết kế kịch bản bảo vệ dữ liệu hoàn chỉnh

### 18.1. Kiến trúc đơn hàng

~~~mermaid
flowchart LR
    W["Web/Mobile"]
    APIM["API Management\nAuth, rate limit"]
    API["Order API\nManaged identity"]
    VN["VNet / Private DNS"]
    PE["Private Endpoint"]
    COS["Cosmos DB NoSQL\ncommerce/orders"]
    EV["Event Hubs / Service Bus\nsự kiện nghiệp vụ"]
    INS["Azure Monitor\nAlerts + Audit"]
    BK["Continuous backup\nRetention theo RPO"]
    REST["Restored account\nfor drill/incident"]
    W --> APIM --> API
    API --> VN --> PE --> COS
    API --> EV
    COS -.-> BK --> REST
    API -.-> INS
    COS -.-> INS
~~~

Giả sử container `orders` có partition key `/tenantId`. Backend xác thực tenant từ user session/claims rồi tự áp dụng partition key, không dựa vào tenantId chưa xác minh từ request.

### 18.2. Luồng tạo đơn đáng tin cậy

1. API xác thực user và tenant.
2. Server gắn `tenantId` hợp lệ và tạo `orderId`/`idempotencyKey`.
3. Cosmos SDK sử dụng managed identity và data-plane role đúng scope.
4. Ghi item vào partition tương ứng và kiểm tra kết quả.
5. Phát business event qua outbox/thiết kế đảm bảo consistency phù hợp.
6. Audit tạo eventId, timestamp UTC, actor và outcome mà không lộ secret.
7. Retry 429 có backoff theo SDK; retry ghi cần idempotent.
8. Khi lỗi, phân loại network/authorization/throttling trước khi thử tiếp.

### 18.3. Luồng khi batch job xóa nhầm

1. Alerts phát hiện mass delete.
2. Disable/freeze job gây lỗi và gỡ quyền không còn cần.
3. Cập nhật incident severity, business owner và mốc UTC.
4. Chọn PITR nếu account/mode hỗ trợ và dữ liệu còn trong retention.
5. Restore sang account riêng, không ghi vào dữ liệu production.
6. So sánh dữ liệu, reconcile writes hợp lệ sau mốc restore.
7. Chọn **selective merge** hoặc **cutover toàn account** theo business impact.
8. Thử app/identity/network, tiếp tục quan sát và postmortem.

### 18.4. Phân trách nhiệm nhóm

| Vai trò | Trách nhiệm |
| --- | --- |
| Product/data owner | RPO/RTO, dữ liệu cần khôi phục, business sign-off |
| SRE/Cloud Platform | Backup policy, account/network, restore execution, monitoring |
| Security/IAM | Token/key compromise, RBAC, Private Endpoint, audit |
| Database/Data Engineering | Kiểm tra documents, partition key, TTL/indexing, reconciliation |
| Backend team | Idempotency, app config, endpoint cutover, tenant checks |
| FinOps | Cost estimate của retention/restore/sandbox |
| Compliance | Data residency, retention/audit constraints |

Không để một principal vừa có thể xóa toàn bộ dữ liệu, tắt logs và thay backup policy mà không có review/break-glass constraints.

## 19. Bài thực hành an toàn

### 19.1. Môi trường

Bạn có một **Cosmos DB for NoSQL account thử nghiệm**:

~~~text
Resource group: rg-cosmos-lab
Account:         cos-orders-lab
Database:        commerce
Container:       orders
Partition key:   /tenantId
Backup mode:     tùy lab, kiểm tra trước
Application:     orders-api-lab (managed identity)
~~~

**Không dùng production.** Nếu chưa có account lab, phần dưới có thể thực hiện như bài tập thiết kế trên giấy; không bắt buộc tạo tài nguyên.

### 19.2. Phần A — Read-only preflight

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-lab"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, backupPolicy:backupPolicy, publicNetworkAccess:publicNetworkAccess}" \
  --output json

az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json

az cosmosdb sql role assignment list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

**Câu hỏi:**

- Backup mode hiện tại là gì?
- Data-plane role nào đã gán cho identity của Order API?
- Có quyền đọc ngoài `orders` không?
- Public network access có đúng chính sách không?
- Có thể thực hiện restore self-service theo mode/API không?

Không in keys trong quá trình kiểm tra.

### 19.3. Phần B — Chọn backup policy

Có hai yêu cầu độc lập:

- **Ứng dụng A:** báo cáo thử nghiệm, chấp nhận mất vài giờ dữ liệu và có export/archive riêng.
- **Ứng dụng B:** đơn hàng production, lỗi được phát hiện trong vài phút và muốn khôi phục tới mốc trước bug.

**Gợi ý đáp án:** A có thể xem periodic backup nếu RPO/quy trình restore phù hợp. B nên đánh giá continuous PITR với retention đáp ứng thời gian phát hiện, nhưng phải xác minh API, chi phí, RTO và reconciliation. Không mặc định continuous luôn đáp ứng mọi RPO/RTO mà không kiểm thử.

### 19.4. Phần C — Khôi phục sai cập nhật

Một job chạy lúc 14:05 UTC sửa sai `status` của 5.000 orders. Từ 14:05 tới 14:30 có thêm 800 orders hợp lệ.

**Câu hỏi:** Có nên restore toàn account về 14:04 rồi cutover ngay?

**Đáp án:** Không. Phải xác minh backup eligibility, restore thử ở account mới và **reconcile 800 orders hợp lệ** cùng các updates đúng trong khoảng sau 14:04. Có thể tốt hơn nếu chọn selective data merge thay vì toàn account.

### 19.5. Phần D — Data-plane role

Một container `orders` chỉ nên được phép đọc/ghi bởi `orders-api`. Một principal đã có Azure IAM `Contributor` trên resource group nhưng không có Cosmos SQL data-plane role.

**Câu hỏi:** Principal có chắc đọc được item qua Entra SDK không?

**Đáp án:** Không. Control plane RBAC và native data plane RBAC khác nhau; cần đúng role/scope và network.

### 19.6. Phần E — Network policy

Tài khoản đã tạo Private Endpoint, nhưng public access vẫn bật và IP firewall còn allowlist cũ.

**Câu hỏi:** Có thể tuyên bố database private-only không?

**Đáp án:** Không. Private Endpoint không tự tắt public path. Phải kiểm tra/cấu hình disable public network access theo chính sách và xác minh app vẫn kết nối qua private route.

### 19.7. Phần F — Partition key và tenant

API đọc tài liệu bằng `read_item(id, partition_key=tenantId)`, nhưng `tenantId` lấy nguyên từ query parameter do client gửi.

**Câu hỏi:** Có phải đã bảo vệ tenant isolation bằng Cosmos partition key?

**Đáp án:** Chưa. Phải xác thực tenant từ identity/claims, kiểm tra quyền nghiệp vụ và ép partition key server-side. Partition key là phân vùng dữ liệu, không phải authentication.

### 19.8. Phần G — Chẩn đoán 403

Một managed identity mới được gán data contributor scope `/dbs/commerce/colls/orders`, SDK vẫn nhận 403. Kiểm tra gì?

**Đáp án:** Identity thực, principal object ID, role definition/dataActions, scope, thời gian propagation, public network ACL/Private Endpoint/DNS và diagnostic substatus. Không chuyển sang primary key một cách vội vàng.

### 19.9. Phần H — Restore bị lỗi kết nối

Portal xác nhận restored account đã tạo. API vẫn timeout khi dùng endpoint đích.

**Đáp án:** Kiểm tra hostname mới, private endpoint approval/DNS zone links, route, SDK Gateway/Direct requirements, TLS và identity/role assignments. Restore dữ liệu không tự tạo mọi kết nối mạng của production account.

### 19.10. Phần I — Cost review

Một restore drill tạo thêm account 3 ngày và bật diagnostic logs ở mức rất chi tiết.

**Đáp án:** kiểm tra Cost Management, throughput/storage của restored account, region/network, retention, log ingestion, cleanup approval. Không xóa trước khi hoàn tất validation/sign-off.

## 20. Checklist trước khi đưa Cosmos DB vào production

- [ ] Account API/backup mode và retention đáp ứng yêu cầu RPO.
- [ ] Đã diễn tập restore tới tài nguyên đích và đo RTO thực.
- [ ] Có runbook khôi phục account/container/item theo tính năng hỗ trợ.
- [ ] Đã thử reconcile writes hợp lệ sau restore point.
- [ ] Roles control plane và data plane phân tách, least privilege.
- [ ] App dùng managed identity/Entra thay account keys khi hỗ trợ.
- [ ] Account keys được bảo vệ, rotation và break-glass có runbook.
- [ ] Không đưa keys/tokens vào browser/mobile/client logs.
- [ ] Network private-only nếu cần, Private Endpoint/DNS/route đã test.
- [ ] TLS/certificate verification và SDK connection mode phù hợp.
- [ ] Backend kiểm soát tenant authorization độc lập partition key.
- [ ] CMK/Key Vault lifecycle đã kiểm tra nếu có dùng.
- [ ] Azure Monitor, audit và alerts được bật, owner rõ ràng.
- [ ] RU/429, latency, storage và security events được giám sát.
- [ ] Có budget cho backup retention, multi-region và restored account tạm.
- [ ] Data privacy/residency, incident escalation và backup ownership rõ.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Cosmos DB multi-region replication có khôi phục dữ liệu đã bị app xóa nhầm không?

**Trả lời:** Không. Replication thường đồng bộ thay đổi/xóa hợp lệ; cần backup/PITR hoặc nguồn lịch sử độc lập.

**Câu 2.** Periodic và continuous backup khác nhau về lựa chọn restore point như thế nào?

**Trả lời:** Periodic phụ thuộc mốc backup theo lịch; continuous được thiết kế cho PITR trong restorable window theo API/configuration hỗ trợ.

**Câu 3.** Một account dùng continuous backup có thể restore tới bất kỳ ngày nào trong quá khứ không?

**Trả lời:** Không. Chỉ trong retention và khoảng restorable timestamps được dịch vụ hỗ trợ.

**Câu 4.** Restore continuous có tự sửa account production hiện tại không?

**Trả lời:** Không nên giả định. Quy trình thường tạo restored account mới, cần validation và cutover.

**Câu 5.** Tại sao restore về 14:04 có thể làm mất dữ liệu kinh doanh hợp lệ?

**Trả lời:** Vì các ghi sau 14:04 không tự tồn tại trong restored snapshot; cần reconciliation/replay.

**Câu 6.** Azure IAM Contributor có thay Cosmos DB native data-plane RBAC không?

**Trả lời:** Không. Hai mặt phẳng quyền khác nhau; SDK Entra cần role phù hợp.

**Câu 7.** Data Contributor gán ở scope container `orders` có thể mặc định ghi mọi containers không?

**Trả lời:** Không nên. Quyền dựa vào dataActions và scope assignment; cần negative tests.

**Câu 8.** Vì sao không đặt account primary key trong JavaScript browser?

**Trả lời:** Browser là môi trường không tin cậy và key có quyền rộng; kẻ tấn công có thể lấy key để gọi data plane trực tiếp.

**Câu 9.** Tạo Private Endpoint có tự tắt public network access không?

**Trả lời:** Không được mặc định. Phải xác minh chính sách public access và đường riêng tư.

**Câu 10.** Partition key theo tenant có là cơ chế bảo mật tenant không?

**Trả lời:** Không. Backend phải xác thực/ủy quyền tenant; partition key chỉ điều phối dữ liệu.

**Câu 11.** Vì sao Gateway mode hoạt động nhưng Direct mode timeout?

**Trả lời:** Direct mode có nhu cầu TCP/route khác; kiểm tra network requirements/ports và Private Link/DNS.

**Câu 12.** CMK có ngăn ứng dụng xóa item khi app đã có quyền ghi không?

**Trả lời:** Không. CMK bảo vệ dữ liệu lưu trữ, không thay authorization, backup hay kiểm soát logic ứng dụng.

**Câu 13.** Azure Activity Log có thể tìm mọi thay đổi JSON item không?

**Trả lời:** Không mặc định. Cần data-plane diagnostics và application audit events được cấu hình phù hợp.

**Câu 14.** Một restore thành công có tự tạo data-plane role assignments và Private Endpoint giống account cũ không?

**Trả lời:** Không nên giả định. Phải kiểm tra metadata, network, identity, keys và monitoring ở tài khoản mới.

**Câu 15.** Alert gì giúp phát hiện việc một job cập nhật sai hàng nghìn đơn?

**Trả lời:** Mass-update/delete anomaly theo service/container/tenant, kết hợp business metrics và deployment correlation.

**Câu 16.** Thay đổi backup policy có nên thực hiện không review vì “không ảnh hưởng data” không?

**Trả lời:** Không. Policy có thể ảnh hưởng restore ability, cost và khả năng đổi lại.

**Câu 17.** Có thể dùng một file export JSON bất kỳ thay cho PITR không?

**Trả lời:** Không. Export cần kiểm chứng consistency, partition key/schema, index/TTL, permissions và replay.

**Câu 18.** Vì sao dọn restored account ngay sau khi portal báo restore thành công là sai?

**Trả lời:** Còn phải validate dữ liệu, kiểm tra ứng dụng, reconciliation và business sign-off; xóa sớm có thể mất phương án phục hồi.

## Ghi nhớ

- **Cosmos DB managed và multi-region không tự chống xóa nhầm**; backup, restore drills, identity và audit vẫn là trách nhiệm thiết kế của bạn.
- **Periodic backup** lưu theo lịch; **continuous backup/PITR** hỗ trợ chọn mốc phục hồi trong restorable window theo API/tier phù hợp.
- **Restore thường cần tài khoản đích mới, kiểm tra dữ liệu, quyền và network**, đồng thời reconcile các ghi hợp lệ sau restore point.
- **Azure control-plane RBAC khác Cosmos DB for NoSQL data-plane RBAC**; app nên dùng managed identity/Entra và role/scope tối thiểu.
- **Account keys là shared secrets quyền rộng**; tránh lộ ở client và quản trị rotation chặt chẽ.
- **Private Endpoint, Private DNS, TLS và RBAC** là các lớp bổ sung nhau; partition key không thay tenant authorization.
- **CMK/encryption không thay backup hay identity governance**; mất khả năng dùng key có thể làm dữ liệu không truy cập được.
- Kết hợp **Azure Monitor, diagnostics và audit nghiệp vụ** để phát hiện truy cập bất thường, 429, lỗi, mass changes và thay đổi backup policy.
- Chỉ coi phương án bảo vệ dữ liệu đủ sẵn sàng khi đã có **RPO/RTO thực nghiệm, restore runbook, security tests, cost budget và người chịu trách nhiệm**.
