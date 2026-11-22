# Thực hành ứng dụng phân phối toàn cầu với Cosmos DB

## 1. Bài toán và kết quả cần đạt

Một ứng dụng bán hàng có khách hàng tại nhiều khu vực cần trả lời nhanh các thao tác xem danh mục, kiểm tra trạng thái đơn hàng và tạo đơn. Nếu toàn bộ API và cơ sở dữ liệu đặt tại một region, khách hàng ở xa phải chịu thêm độ trễ mạng; khi region gặp sự cố, cả ứng dụng có thể ngừng phục vụ. Đưa ứng dụng ra nhiều region chỉ giải quyết một phần: dữ liệu cũng phải có cơ chế phân phối, tính nhất quán, ghi và phục hồi phù hợp.

Trong chương **Kiến trúc và thực hành tổng hợp** của module `CLOUD_PROVIDERS_AZURE`, bài thực hành này kết nối những kiến thức về subscription, resource group, Microsoft Entra ID, mạng ảo, dịch vụ tính toán, lưu trữ/dữ liệu, quan sát, bảo mật và chi phí thành một kiến trúc ứng dụng phân phối toàn cầu dựa trên **Azure Cosmos DB for NoSQL**.

Người học sẽ thiết kế và thử nghiệm một hệ thống đơn hàng đơn giản, trong đó:

- API được đặt ở **hai region**, có điểm vào hỗ trợ định tuyến và health check.
- Một tài khoản **Azure Cosmos DB for NoSQL** được cấu hình phân phối dữ liệu qua những region được hỗ trợ.
- Ứng dụng Java dùng Cosmos DB SDK để ghi/đọc tài liệu JSON, có **partition key**, định danh ổn định và xử lý lỗi.
- Nhóm chọn **consistency level** dựa trên yêu cầu của từng hành trình nghiệp vụ.
- Có kịch bản kiểm tra khi một API region hỏng, khi vùng dữ liệu ghi chính không khả dụng và khi xảy ra throttling.
- Kết quả được đo bằng **latency, request charge (RU), tỷ lệ HTTP 429, độ trễ dữ liệu quan sát được, chi phí và khả năng phục hồi**.

**Giới hạn:** Đây là bài tập thiết kế và thực hành. Những số liệu, tên resource, region, SKU và mức tải đều là minh họa; khả năng hỗ trợ thực tế phải được xác minh theo subscription, vùng và cấu hình. Không thực hiện failover gây ảnh hưởng đến tài khoản production chỉ để hoàn thành bài tập.

### 1.1. Kết quả đầu ra của lab

Cuối bài, người học cần có: sơ đồ kiến trúc, bảng chọn consistency/partition key, một chương trình Java ghi-đọc tài liệu thử nghiệm, bảng phép đo ở hai vùng, kịch bản lỗi và runbook phục hồi, bảng chi phí dự kiến, cùng phần giải thích các trade-off giữa hiệu năng, tính nhất quán và độ tin cậy.

## 2. Azure Cosmos DB là gì và chọn mô hình nào?

**Azure Cosmos DB** là nhóm dịch vụ cơ sở dữ liệu được quản lý trên Azure với các mô hình/API khác nhau. Bài này tập trung **Azure Cosmos DB for NoSQL** (API for NoSQL) vì có mô hình tài liệu JSON, truy vấn SQL-style, SDK phù hợp và khả năng phân phối dữ liệu theo nhiều region.

Các khái niệm cốt lõi:

| Thuật ngữ | Vai trò trong lab |
| --- | --- |
| **Account** | Tài khoản Cosmos DB, nơi cấu hình các region, cơ chế ghi và tính nhất quán mặc định |
| **Database** | Nhóm logic chứa container |
| **Container** | Tập tài liệu JSON, cấu hình partition key, throughput và indexing |
| **Item** | Một tài liệu JSON, nhận diện bởi `id` trong phạm vi logical partition |
| **Logical partition** | Các item có cùng giá trị partition key; ranh giới quan trọng cho định tuyến và giao dịch |
| **Physical partition** | Đơn vị triển khai nội bộ do Cosmos DB phân chia và quản lý |
| **RU (Request Unit)** | Đơn vị chuẩn hóa chi phí tài nguyên để xử lý thao tác |
| **RU/s** | Công suất throughput được cấp/điều chỉnh theo chế độ đã chọn |
| **Consistency level** | Cam kết về độ mới và thứ tự dữ liệu client có thể quan sát |
| **Region** | Vị trí địa lý triển khai replica dữ liệu và xử lý request của tài khoản |
| **Partition key** | Thuộc tính dùng để phân phối tài liệu và chọn đích truy vấn |

Một *container* không giống bảng quan hệ theo mọi nghĩa. Azure Cosmos DB for NoSQL không tự cung cấp mọi loại JOIN, transaction đa partition hoặc ràng buộc quan hệ như RDBMS. Thiết kế dữ liệu phải hướng theo **access pattern**, khả năng phân vùng và yêu cầu về giao dịch.

### 2.1. Khi nào phù hợp, khi nào cần cân nhắc?

Cosmos DB for NoSQL thường phù hợp khi workload cần độ trễ thấp, phân phối dữ liệu, mở rộng quy mô theo partition, dữ liệu JSON và các mẫu truy cập xác định được. Tuy nhiên, không nên chọn chỉ vì nghe “global distribution”:

- Nếu cần nhiều giao dịch ACID đa thực thể, nhiều bảng và truy vấn join phức tạp, hãy so sánh với giải pháp quan hệ.
- Nếu phần lớn dữ liệu chỉ đọc như hình ảnh/tệp lớn, **Azure Blob Storage + CDN** có thể phù hợp hơn; Cosmos DB không thay thế object storage.
- Nếu workload chỉ có một khu vực với tải thấp, chi phí replica đa region có thể vượt lợi ích hiệu năng.
- Nếu quy định dữ liệu không được rời một khu vực pháp lý, phải chọn region và replication theo **data residency** trước khi bật thêm vùng.

## 3. Kiến trúc tham chiếu: điểm vào toàn cầu, API theo vùng, dữ liệu phân phối

Giả sử có hai vùng Azure đáp ứng yêu cầu về dịch vụ và dữ liệu:

- **Region A:** vùng ưu tiên cho ghi, triển khai API A.
- **Region B:** vùng dữ liệu thứ hai, triển khai API B.
- **Azure Front Door:** nhận HTTP(S) từ người dùng, kiểm tra health của các API origin và định tuyến theo chính sách đã cấu hình.
- **Azure Cosmos DB for NoSQL:** một account với các location/region đã được thêm và chọn chế độ ghi.
- **Azure Monitor/Application Insights:** đo SLI end-to-end, dependency latency và sự cố; Cost Management theo dõi chi phí.

~~~mermaid
flowchart TB
    EU["Người dùng ở nhiều địa điểm"] --> FD["Azure Front Door<br/>TLS, WAF, health probes, origin groups"]
    FD --> A["API Region A<br/>Java + Cosmos SDK"]
    FD --> B["API Region B<br/>Java + Cosmos SDK"]
    A --> C["Azure Cosmos DB for NoSQL<br/>một account, nhiều region"]
    B --> C
    C --> PA["Replica / write Region A"]
    C --> PB["Replica Region B"]
    OBS["Azure Monitor + App Insights"] -.-> FD
    OBS -.-> A
    OBS -.-> B
    OBS -.-> C
    IAM["Managed Identity / RBAC / Key Vault"] -.-> A
    IAM -.-> B
~~~

Sơ đồ thể hiện **mô hình logic**, không có nghĩa mỗi ứng dụng tự kết nối trực tiếp vào một IP replica. SDK của Cosmos DB sử dụng thông tin account/region và routing nội bộ theo cấu hình. Với chế độ **single-region write**, Region B có thể phục vụ read gần client hơn nhưng **ghi vẫn phải được xử lý bởi write region**. Vì vậy không được tuyên bố độ trễ ghi ở hai vùng luôn như nhau.

### 3.1. Tránh nhầm hai kiểu failover

| Tầng | Thành phần có thể lỗi | Cơ chế phục hồi |
| --- | --- | --- |
| **API/ingress** | API A không khỏe nhưng Cosmos DB vẫn phục vụ | Front Door loại origin lỗi, chuyển request mới sang API B theo probe/routing |
| **Database** | Write region của Cosmos DB không khả dụng | Account sử dụng cơ chế failover vùng ghi khi được cấu hình, có điều kiện và thời gian hội tụ |
| **Dependency khác** | Identity, DNS, queue, payment provider, secrets | Cần thiết kế HA/DR riêng; Cosmos DB không tự khắc phục |
| **Lỗi logic/dữ liệu** | Item bị xóa nhầm hoặc ứng dụng ghi dữ liệu sai | Backup/restore, versioning, validation và quy trình phục hồi riêng |

**Global distribution không thay thế DR toàn hệ thống.** API phải được triển khai và kiểm tra ở các vùng, Front Door phải có health probe đúng, quyền và kết nối DNS/private network phải hoạt động ở cả hai vùng, và dữ liệu phải đáp ứng mục tiêu RTO/RPO đã thỏa thuận.

### 3.2. Single-write hay multi-write?

**Single-region write (mặc định phổ biến):**

- Một region nhận ghi chính; các region khác có thể phục vụ đọc theo topology của account.
- Dễ giữ một điểm điều phối ghi cho những thao tác cần thứ tự.
- Khi write region lỗi, chuyển quyền ghi cần cơ chế failover; app có thể gặp lỗi tạm thời.
- Ghi từ API ở vùng xa có thể thêm network latency vì request cuối cùng hướng tới vùng ghi.

**Multi-region writes (tùy chọn khi được hỗ trợ và cấu hình):**

- Nhiều region có thể chấp nhận ghi, giúp giảm khoảng cách mạng của ghi trong một số workload.
- Xuất hiện khả năng **ghi xung đột** giữa các vùng hoặc các biến thể của cùng tài liệu; cần chính sách giải quyết xung đột phù hợp.
- Thao tác liên quan tiền hoặc kho hàng đòi hỏi thiết kế chặt về idempotency, invariants, concurrency và phạm vi giao dịch.
- Chi phí, độ phức tạp kiểm thử và các giới hạn về consistency có thể khác chế độ single-write.

**Quyết định cho lab:** bắt đầu bằng **single-region write và hai vùng đọc**, tập trung đo read latency và failover. Sau đó *phân tích* multi-write như một phương án mở rộng. Không bật multi-write trên một hệ thống đơn hàng có giao dịch tài chính thật khi chưa chứng minh tính nhất quán nghiệp vụ và cơ chế conflict resolution.

## 4. Thiết kế document và partition key cho ứng dụng toàn cầu

Trong Cosmos DB for NoSQL, **partition key** quyết định nơi item được phân phối và ảnh hưởng lớn đến độ trễ, RU, tính mở rộng và khả năng thực hiện transaction. Phải thiết kế theo cách ứng dụng truy vấn, không chọn key ngẫu nhiên.

### 4.1. Tài liệu đơn hàng mẫu

~~~json
{
  "id": "order-10001",
  "tenantId": "tenant-a",
  "customerId": "customer-009",
  "regionOfCustomer": "apac",
  "status": "CREATED",
  "currency": "USD",
  "amount": 125.50,
  "createdAtUtc": "2026-11-20T10:00:00Z",
  "lastUpdatedAtUtc": "2026-11-20T10:00:00Z"
}
~~~

Container có partition key path `/tenantId`. Cặp **id + partition key value** xác định item để point read, ví dụ `order-10001` trong logical partition `tenant-a`.

### 4.2. Vì sao chọn /tenantId?

Giả sử ứng dụng SaaS thường hiển thị đơn hàng theo doanh nghiệp/tenant và truy cập item bằng `tenantId` cùng `id`:

- Query/filter trong một tenant có thể giới hạn về một logical partition.
- Point read theo `id` và `tenantId` giúp SDK định tuyến chính xác, thường hiệu quả RU hơn truy vấn thiếu partition key.
- Các thao tác transactional batch có thể thực hiện trên các item **cùng logical partition** theo điều kiện dịch vụ.
- Cách phân nhóm dữ liệu hỗ trợ ranh giới nghiệp vụ tenant trong truy vấn và quản trị.

**Rủi ro:** một tenant rất lớn có thể trở thành **hot logical partition** hoặc chạm giới hạn về dữ liệu/throughput của logical partition. Partition key không nên là một giá trị duy nhất cho mọi item, cũng không nên có phân bố quá lệch.

### 4.3. So sánh lựa chọn partition key

| Partition key | Lợi thế | Rủi ro |
| --- | --- | --- |
| `/tenantId` | Truy vấn từng tenant và batch cùng tenant thuận lợi | Tenant lớn dễ tạo hot partition |
| `/orderId` | Phân bố gần như theo từng đơn, điểm đọc theo orderId | Truy vấn tất cả đơn của một tenant có thể cross-partition |
| `/customerId` | Đọc lịch sử theo khách hàng dễ hơn | Khách hàng rất lớn có thể nóng; transaction theo tenant khó |
| `/regionOfCustomer` | Dễ nhóm dữ liệu theo khu vực | Ít giá trị phân biệt; hotspot và giới hạn logical partition |
| **Hierarchical partition key** khi hỗ trợ | Có thể cải thiện mô hình đa tenant khi chọn cấp hợp lý | Phải hiểu query/access pattern, giới hạn dịch vụ và SDK |

Một giá trị như `apac` hay `eu` không đảm bảo dữ liệu được lưu duy nhất ở vùng địa lý tương ứng. **Partition key không phải công cụ data residency.** Region replication của account được cấu hình riêng; mọi region nhận replica phải đáp ứng chính sách dữ liệu.

### 4.4. Mô hình write và concurrency

Đối với đơn hàng:

1. Client tạo `orderId` ổn định hoặc gửi idempotency key.
2. API kiểm tra quyền truy cập tenant và validation nghiệp vụ.
3. Ghi item với `id` và `tenantId` đúng partition key.
4. Nếu client retry cùng yêu cầu, trả kết quả đã ghi hoặc xử lý trùng an toàn; **không tạo hai đơn khác nhau**.
5. Với update, dùng **ETag / optimistic concurrency** khi cần ngăn ghi đè các thay đổi đồng thời.
6. Nếu nhiều item phải thay đổi nguyên tử, đánh giá transactional batch/same-partition constraints hoặc thiết kế saga/outbox.

**Không xem upsert là idempotency hoàn chỉnh.** Upsert cùng id có thể ghi đè dữ liệu mới, che giấu trạng thái từ một yêu cầu khác. Với nghiệp vụ nhạy cảm, nên dùng create có phát hiện conflict, trạng thái hợp lệ và kiểm soát phiên bản.

## 5. Năm mức consistency và tác động thực tế

Azure Cosmos DB for NoSQL có các mức consistency thường được nhắc đến:

1. **Strong** – đọc với bảo đảm nhất quán mạnh trong phạm vi và điều kiện cấu hình hỗ trợ; có thể làm tăng độ trễ và hạn chế topology/availability.
2. **Bounded Staleness** – dữ liệu đọc có độ cũ bị giới hạn theo các tham số được dịch vụ hỗ trợ.
3. **Session** – các thao tác thuộc một phiên có bảo đảm về tính nhất quán của phiên, hữu ích cho *read-your-writes* khi session context được duy trì.
4. **Consistent Prefix** – các thay đổi được quan sát theo tiền tố thứ tự, nhưng không nhất thiết mới nhất.
5. **Eventual** – dữ liệu cuối cùng hội tụ khi không còn cập nhật mới, nhưng đọc có thể thấy giá trị cũ trước khi hội tụ.

Mức đảm bảo thực tế còn phụ thuộc **single-write/multi-write, region, account, SDK và mô hình đọc/ghi**. Không được tự suy rằng mọi mức consistency đều được hỗ trợ trong mọi topology hoặc đều có hiệu năng giống nhau.

| Hành trình | Gợi ý xem xét | Điều phải kiểm tra |
| --- | --- | --- |
| Hiển thị danh mục ít thay đổi | Eventual/Consistent Prefix nếu sản phẩm cho phép dữ liệu cũ | Thời gian hội tụ và mức stale chấp nhận được |
| Người dùng vừa tạo đơn rồi xem lại | Session có thể phù hợp | Có giữ/đưa đúng session token qua nhiều request/service instance? |
| Báo cáo phân tích không tức thời | Eventual hoặc dữ liệu được xử lý bất đồng bộ | SLA độ trễ báo cáo và tính đầy đủ |
| Thao tác cập nhật số dư/kho quan trọng | Phải thiết kế invariants và transaction phù hợp | Consistency alone không bảo đảm giao dịch đa partition/region an toàn |
| Trang giám sát trạng thái đơn từ vùng xa | Session hoặc consistency phù hợp UX | Stale read, retry, token propagation, failover |

### 5.1. Session token giữa nhiều instance

Một ứng dụng web có thể dùng nhiều API instance ở hai region. Đừng mặc định mọi request của người dùng luôn tới cùng một process. **Session consistency** có thể yêu cầu duy trì session context hoặc truyền session token đúng cách theo SDK và kiến trúc.

Ví dụ, client tạo đơn qua API A, rồi được Front Door đưa sang API B để đọc ngay. Nếu hai API sử dụng các session/SDK client context độc lập, API B có thể **không tự có session token của thao tác ghi trước**. Cần thiết kế session affinity, token propagation hoặc workflow đọc sau ghi phù hợp; không quảng cáo “read-your-writes toàn cầu” mà chưa kiểm thử trường hợp đổi API region.

### 5.2. Chọn consistency bằng phép thử

Với mỗi hành trình, ghi:

- Mục tiêu độ mới dữ liệu: chấp nhận stale bao lâu?
- Có cần giữ thứ tự sự kiện và transaction atomic không?
- Request ghi từ vùng nào, request đọc từ vùng nào?
- Khi lỗi vùng dữ liệu, có chấp nhận tạm ngừng ghi để bảo toàn tính nhất quán không?
- Session token được quản lý ra sao qua các request và dịch vụ?

Sau đó đo latency và dữ liệu quan sát được trong cấu hình thật, thay vì chọn mức consistency chỉ bằng một bảng lý thuyết.

## 6. Throughput, RU/s và độ trễ

**Request Unit (RU)** biểu thị chi phí xử lý logic của thao tác. RU phụ thuộc kích thước item, indexing, query pattern, số item, partitioning, consistency và những yếu tố khác.

Các chế độ capacity của Cosmos DB for NoSQL gồm **provisioned throughput** (thủ công), **autoscale throughput** khi phù hợp và **serverless** ở những cấu hình/region được hỗ trợ. Không phải mọi chế độ đều có cùng khả năng multi-region hoặc cùng mô hình tính phí; phải xác minh trước khi tạo account.

### 6.1. Bài toán RU/s minh họa

Giả sử bài benchmark cho một workload đưa ra:

- Point read trung bình: **1 RU** (giả định để tính).
- Create item trung bình: **6 RU** (giả định để tính).
- Trong một giây đỉnh: **600 reads** và **100 writes**.

~~~text
Estimated RU/s
  = 600 × 1 + 100 × 6
  = 1.200 RU/s
~~~

Nếu muốn biên dự phòng 25% theo mô hình đơn giản:

~~~text
Target capacity >= 1.200 × 1,25 = 1.500 RU/s
~~~

**Đây không phải con số RU thực của Cosmos DB.** RU cho mỗi thao tác phải được lấy từ response/metrics của môi trường thật, và provisioned throughput có mức cấp phát tối thiểu, bước tăng, giới hạn partition và điều kiện autoscale. Khi thêm region hoặc tăng indexing, chi phí RU và tiền có thể thay đổi.

### 6.2. Vì sao có HTTP 429?

**429 Too Many Requests** là tín hiệu throttling khi nhu cầu vượt khả năng phục vụ được cấp tại thời điểm hoặc partition liên quan. Có thể có tổng RU/s còn dư nhưng một partition nóng vẫn bị throttling.

Cần xem:

- Tổng tiêu thụ RU và tỷ lệ RU normalized theo container/partition.
- Request charge của point read, query và write.
- Tỷ lệ 429, retry count và thời gian chờ.
- Phân bố partition key, kích thước tài liệu, query scans và indexing policy.
- Request latency ở client và server, network RTT, CPU app.

SDK thường có xử lý retry cho 429 theo các giới hạn/config được hỗ trợ. **Không retry vô hạn** hoặc đồng loạt bằng vòng lặp tự viết: retry storm có thể làm độ trễ tăng và che dấu lỗi thiết kế. Dùng backoff, giới hạn tổng thời gian, timeouts, idempotency và quan sát retry.

### 6.3. Point read so với truy vấn cross-partition

Nếu đã biết `id` và partition key, point read thường là lựa chọn hiệu quả nhất. Truy vấn không khai báo điều kiện partition phù hợp có thể phải đi qua nhiều physical partitions, tiêu thụ RU lớn và tăng latency.

Ví dụ truy vấn hợp lý khi scope là tenant:

~~~sql
SELECT c.id, c.status, c.createdAtUtc
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAtUtc DESC
~~~

Query parameterized, index và partition key được chọn theo access pattern. Kiểm tra query metrics, RU, quy tắc composite index khi có ORDER BY/filter và độ chọn lọc. Không giả định mọi câu SQL-style query đều dùng index tối ưu mà không cần thiết kế.

## 7. Chuẩn bị môi trường lab một cách an toàn

### 7.1. Những thứ cần có

- Azure subscription có quyền tạo/đọc Cosmos DB, resource group và các tài nguyên quan sát theo quy trình tổ chức.
- Tài khoản test được cô lập với dữ liệu production; có ngân sách và ngày cleanup.
- Java 17+ và Maven/Gradle cho ví dụ SDK.
- SDK **azure-cosmos v4** được chọn ở phiên bản đã được tổ chức xác minh, cùng Azure CLI nếu muốn đọc cấu hình.
- Quyền thiết lập region, database/container và giới hạn truy cập mạng nếu triển khai thực tế.
- Một bộ dữ liệu JSON **synthetic**, không chứa PII hoặc thông tin thẻ thanh toán.
- Nếu triển khai hai API region, dịch vụ compute, ingress và telemetry phù hợp; không bắt buộc tạo Front Door thật chỉ để thử code đọc/ghi.

### 7.2. Quyết định region và dữ liệu

Chọn hai region mà tài khoản/loại dịch vụ hỗ trợ, có khả năng cấp phát và đáp ứng quy định dữ liệu. Ví dụ minh họa có thể dùng **Southeast Asia** và **East Asia**, nhưng phải kiểm tra tính khả dụng hiện hành theo subscription, account type, zone configuration, quota và các giới hạn sản phẩm.

**Chú ý data residency:** Bật replication ở Region B đồng nghĩa dữ liệu của account có thể được sao chép đến vùng đó theo mô hình dịch vụ. Không bật vùng không được pháp lý/doanh nghiệp chấp thuận. Nếu yêu cầu chỉ cho phép một tập khu vực địa lý, hãy chọn cấu trúc account/partitioning hoặc phương án khác phù hợp; **partition key không ngăn replication qua region**.

### 7.3. Kế hoạch tài nguyên mẫu

| Resource | Tên minh họa | Vai trò |
| --- | --- | --- |
| Resource group | `rg-cosmos-global-lab` | Gom tài nguyên test và kiểm soát cleanup |
| Cosmos DB account | `cosmos-orders-global-unique` | Account NoSQL; tên thực tế phải duy nhất theo quy tắc dịch vụ |
| Database | `commerce` | Chứa container |
| Container | `orders` | Item JSON, partition key `/tenantId` |
| API Region A/B | `orders-api-a` / `orders-api-b` | Các bản ứng dụng tương đương ở hai region |
| Front Door | `fd-orders-lab` | Định tuyến/health probe giữa hai origin |
| Monitoring | App Insights/Log Analytics | Quan sát ứng dụng và Cosmos SDK |
| Budget | `budget-global-lab` | Cảnh báo phí phát sinh theo scope hỗ trợ |

Phần này **chỉ là kế hoạch**; việc tạo tài nguyên Azure có thể phát sinh phí từ khi bật throughput, replication, logs và ingress.

## 8. Tạo tài khoản Cosmos DB nhiều region bằng Azure Portal

Giao diện Azure Portal và các trường có thể thay đổi, nhưng luồng cơ bản:

1. Vào **Azure Portal → Create a resource → Azure Cosmos DB**, chọn **Azure Cosmos DB for NoSQL**.
2. Chọn đúng subscription/resource group test; đặt tên account, chọn region chính đáp ứng chính sách dữ liệu.
3. Chọn mô hình throughput phù hợp với **multi-region lab**. Với mô hình provisioned throughput, xác định manual hoặc autoscale tùy điều kiện; kiểm tra giá và ngưỡng tối thiểu.
4. Trong phần **Replicate data globally** hoặc cấu hình tương ứng, thêm vùng đọc thứ hai, xem thứ tự failover. Ban đầu dùng **single-write** để đơn giản hóa consistency.
5. Xác nhận tùy chọn **automatic failover** nếu muốn nghiên cứu kịch bản tự chuyển vùng ghi; kiểm tra hành vi/điều kiện và thời gian failover theo cấu hình.
6. Kiểm tra zone redundancy theo **region/khả năng hỗ trợ và lựa chọn account**, không giả định hai region đồng nghĩa chịu mọi lỗi Availability Zone.
7. Chọn cơ chế backup được dịch vụ hỗ trợ và phù hợp với yêu cầu khôi phục logic; xem các lựa chọn periodic/continuous theo tài khoản.
8. Cấu hình identity, network, firewall/Private Endpoint và monitoring. Giới hạn public access theo thiết kế và yêu cầu lab.
9. Tạo database `commerce` và container `orders` với partition key **/tenantId**. Chọn throughput ở **cấp database hay container** theo cách tổ chức muốn cấp và phân chia RU/s.
10. Ghi lại account endpoint, database/container, danh sách region, consistency, chế độ write, backup, throughput và chi phí ước tính.

**Không bật multi-region writes chỉ để xem có nút bật.** Quyết định phải dựa vào semantics của ứng dụng và khả năng giải quyết conflict. Một số thiết lập có hạn chế khi thay đổi sau khi account đã tồn tại; đọc cảnh báo của Portal trước khi xác nhận.

### 8.1. Xem cấu hình qua Azure CLI (read-only)

~~~bash
# Kiểm tra subscription/tenant trước khi truy cập.
az account show --query "{subscription:id,tenant:tenantId}" -o json

# Xem cấu hình tài khoản và các region đã thiết lập.
az cosmosdb show \
  --resource-group rg-cosmos-global-lab \
  --name cosmos-orders-global-unique \
  --query "{name:name,kind:kind,locations:locations,automaticFailover:enableAutomaticFailover,multiWrite:enableMultipleWriteLocations,consistency:consistencyPolicy}" \
  -o json

# Kiểm tra database và container.
az cosmosdb sql database show \
  --resource-group rg-cosmos-global-lab \
  --account-name cosmos-orders-global-unique \
  --name commerce \
  -o json

az cosmosdb sql container show \
  --resource-group rg-cosmos-global-lab \
  --account-name cosmos-orders-global-unique \
  --database-name commerce \
  --name orders \
  -o json
~~~

Tên tài khoản và resource group là **placeholder minh họa**, không phải tài nguyên đang tồn tại. Các lệnh chỉ đọc metadata; kết quả cần so với cấu hình Portal, điều kiện RBAC và lựa chọn throughput thực tế.

## 9. Viết ứng dụng Java dùng Cosmos DB SDK

Bài lab sử dụng Java để tạo item và point read. Mọi dữ liệu là synthetic; chương trình không tạo account/database/container và phải chạy **chỉ sau khi container đã tồn tại**.

### 9.1. Khai báo dependency

Trong `pom.xml` của dự án thực hành, sử dụng SDK phiên bản **azure-cosmos 4.x** đang được hỗ trợ và đã kiểm tra tương thích Java của tổ chức:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-cosmos</artifactId>
  <version>4.x.y</version>
</dependency>
~~~

`4.x.y` là **placeholder, không phải Maven version hợp lệ**. Cần thay bằng phiên bản ổn định cụ thể sau khi kiểm tra dependency management/BOM và hướng dẫn của SDK tại thời điểm triển khai. Không copy nguyên vào pipeline rồi kỳ vọng Maven tự suy phiên bản.

### 9.2. Biến môi trường

~~~bash
# Chỉ dùng account test và kho bí mật được tổ chức chấp thuận.
export COSMOS_ENDPOINT="https://<test-cosmos-account>.documents.azure.com:443/"
export COSMOS_KEY="<test-key-from-approved-secret-store>"
export COSMOS_DATABASE="commerce"
export COSMOS_CONTAINER="orders"
export COSMOS_PREFERRED_REGION_1="Southeast Asia"
export COSMOS_PREFERRED_REGION_2="East Asia"
~~~

**Trong môi trường sản xuất, ưu tiên Microsoft Entra ID/Managed Identity và Cosmos DB data-plane RBAC khi SDK/API và kiến trúc hỗ trợ**; không đặt account key trong code, repository, log hoặc cấu hình được chia sẻ. Đoạn dùng key ở đây chỉ để diễn đạt luồng SDK trong môi trường lab được kiểm soát; Azure Cosmos DB account key có thể cấp quyền rộng, phải bảo vệ theo nguyên tắc least privilege và xoay vòng theo quy trình.

### 9.3. Chương trình Java tạo và đọc một đơn hàng

Ví dụ một class `CosmosGlobalLab`. Các API sử dụng SDK Azure Cosmos DB for NoSQL v4; cần thay dependency version phù hợp trước khi chạy.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.CosmosException;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class CosmosGlobalLab {
    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }

    public static void main(String[] args) {
        String endpoint = requiredEnv("COSMOS_ENDPOINT");
        String accountKey = requiredEnv("COSMOS_KEY");
        String databaseName = requiredEnv("COSMOS_DATABASE");
        String containerName = requiredEnv("COSMOS_CONTAINER");
        String region1 = requiredEnv("COSMOS_PREFERRED_REGION_1");
        String region2 = requiredEnv("COSMOS_PREFERRED_REGION_2");

        CosmosClient client = new CosmosClientBuilder()
            .endpoint(endpoint)
            .key(accountKey)
            .consistencyLevel(ConsistencyLevel.SESSION)
            .preferredRegions(List.of(region1, region2))
            .buildClient();

        try {
            CosmosContainer container = client
                .getDatabase(databaseName)
                .getContainer(containerName);

            String tenantId = "tenant-lab";
            String orderId = "order-" + UUID.randomUUID();

            Map<String, Object> order = new HashMap<>();
            order.put("id", orderId);
            order.put("tenantId", tenantId);
            order.put("status", "CREATED");
            order.put("amount", 125.50);
            order.put("createdAtUtc", Instant.now().toString());

            CosmosItemResponse<Map> written = container.createItem(
                order,
                new PartitionKey(tenantId),
                new CosmosItemRequestOptions()
            );

            System.out.printf(
                "Created order: %s, write RU: %.2f%n",
                orderId,
                written.getRequestCharge()
            );

            CosmosItemResponse<Map> read = container.readItem(
                orderId,
                new PartitionKey(tenantId),
                Map.class
            );

            System.out.printf(
                "Read status: %s, read RU: %.2f%n",
                read.getItem().get("status"),
                read.getRequestCharge()
            );
        } catch (CosmosException error) {
            System.err.printf(
                "Cosmos operation failed. HTTP status=%d%n",
                error.getStatusCode()
            );
            // Không ghi account key, PII hoặc raw request payload.
            throw error;
        } finally {
            client.close();
        }
    }
}
~~~

Chương trình dùng **synchronous client** để người học dễ theo dõi. Với ứng dụng web thực tế, cân nhắc asynchronous SDK, client reuse, connection tuning và metric/tracing phù hợp; không tạo client mới cho mỗi HTTP request. `preferredRegions` là danh sách **ưu tiên đọc/routing SDK** theo cơ chế của account; nó **không tự thêm region vào account** và không đảm bảo mọi request luôn thực thi tại region đứng đầu khi vùng đó không đủ quyền ghi hoặc không khả dụng.

**Kỳ vọng:** Tạo item có `id` và `tenantId` rồi đọc lại bằng cùng partition key. Log hiển thị RU của write và point read; giá trị thực tế phụ thuộc kích thước document, indexing và cấu hình, không nhất thiết bằng ví dụ 1 RU/6 RU ở mục trước.

### 9.4. Xử lý trùng idempotently

Trong chương trình demo, `UUID` tạo ID mới mỗi lần chạy nên **không phù hợp** làm idempotency key cho một request nghiệp vụ được retry. API thực tế nên nhận một mã yêu cầu ổn định do client tạo hoặc lưu mapping `clientRequestId → orderId`.

Ví dụ một lần retry cùng `id` trong cùng partition có thể nhận HTTP 409 Conflict khi `createItem` đã thành công trước đó. Một handler an toàn cần:

1. Bắt 409 và lấy lại item theo `id + partition key`.
2. Kiểm tra owner/tenant, payload hash hoặc các thuộc tính nghiệp vụ xác nhận đây là **cùng yêu cầu**.
3. Trả kết quả đã lưu nếu phù hợp; nếu payload khác, báo conflict đúng nghĩa thay vì ghi đè.
4. Đối với update đồng thời, dùng ETag và điều kiện If-Match theo SDK khi phù hợp.
5. Không retry yêu cầu có trạng thái commit chưa rõ mà tạo ID mới mỗi lần.

### 9.5. Kiểm tra consistency ở hai API instance

Lập phép thử gồm hai ứng dụng, mỗi ứng dụng cấu hình ưu tiên region khác nhau:

- **App A** ưu tiên Region A, **App B** ưu tiên Region B.
- Tạo item qua API A và đọc ngay qua API A; ghi latency và RU.
- Đọc item vừa tạo qua API B, ghi kết quả, số lần retry và thời gian item xuất hiện.
- Đo trong các consistency level **được tài khoản hỗ trợ**, so sánh tác động.
- Với Session, thiết kế truyền session context/token hoặc đảm bảo cơ chế session phù hợp khi chuyển request giữa instance. Ghi rõ nếu phép thử không đảm bảo token propagation.

Không lấy một lần đọc trả về ngay làm bằng chứng rằng mọi request ở mọi vùng sẽ luôn có dữ liệu mới nhất.

## 10. Bảo mật và kết nối mạng cho lab

Ngay cả bài tập chỉ chứa synthetic data cũng cần nguyên tắc bảo mật đủ gần môi trường thật.

### 10.1. Danh tính và quyền truy cập

- Tách **management plane RBAC** (tạo/sửa account) khỏi **Cosmos DB data-plane access** (đọc/ghi item).
- Với Java app production, xem xét **Managed Identity** cùng identity-based auth và vai trò data-plane tối thiểu được Cosmos DB for NoSQL hỗ trợ.
- Không dùng chung account key giữa các nhóm; giảm hoặc vô hiệu hóa local authentication theo chính sách và khả năng hỗ trợ đã kiểm tra.
- Hạn chế người có quyền xóa account hoặc thay đổi replication, failover, backup và networking.
- Lưu audit trail cho những thao tác nhạy cảm, dùng Entra ID và quy trình phê duyệt thay đổi.

### 10.2. Mạng riêng và các đường đi theo region

Nếu API phải truy cập Cosmos DB qua mạng riêng, thiết kế **Private Endpoint, Private DNS Zone, VNet links, firewall/NSG và tuyến** theo topology được hỗ trợ. Có hai API region không nghĩa là chỉ cần một Private Endpoint hoặc một DNS link ở vùng A; phải xác minh đường kết nối tới account từ **từng VNet/app region**.

- DNS phải trả IP Private Endpoint theo đường truy vấn được thiết kế; custom DNS/forwarder cần có quy tắc phù hợp.
- Kiểm tra TLS/hostname khi SDK dùng endpoint chuẩn; không hard-code IP private trong client.
- Chọn mô hình routing/connection mode SDK phù hợp với network rules và tính năng được hỗ trợ.
- Khi region hoặc private endpoint gặp sự cố, xác minh failover connectivity chứ không chỉ trạng thái Cosmos account.
- Đừng mở public network access vô thời hạn chỉ để vượt qua lỗi DNS của bài test.

### 10.3. Bảo vệ dữ liệu và quyền truy cập theo tenant

Partition key `/tenantId` **không tự là cơ chế bảo mật tenant**. API phải xác thực user, map tenant từ identity token đáng tin, áp quyền từng tenant và **không tin tham số tenantId do client tùy ý nhập**. Nếu không, người dùng có thể đoán `id + tenantId` và thử đọc dữ liệu không thuộc quyền.

Với dữ liệu nhạy cảm, kiểm tra encryption, key management, retention, audit và data residency theo chính sách. Bật global replication mà không kiểm tra pháp lý hoặc nơi lưu dữ liệu có thể tạo rủi ro tuân thủ.

## 11. Hiện thực API ở hai region và tuyến Front Door

Cosmos DB có nhiều read region không có nghĩa ứng dụng tự trở nên **global application**. Cần ít nhất hai API deployments có thể phục vụ cùng hợp đồng API, cùng phiên bản schema/logic và có cấu hình tương đương.

### 11.1. Thiết kế điểm vào

Với Azure Front Door, cấu hình ví dụ:

1. Hai origin là endpoint API A và API B, đã có HTTPS và health endpoint.
2. Health probe kiểm tra **readiness thực tế** theo cách không gây tác dụng phụ và không làm mọi backend bị loại do một lỗi nhỏ ở dependency chung.
3. Quy tắc route, priority/weight hoặc latency-based behavior theo khả năng của tier đã chọn.
4. TLS, WAF, custom domain, caching behavior (nếu phù hợp) và header forwarding đúng.
5. Telemetry cho frontend response, origin health và phân bố traffic.

Không dùng health probe quá sâu khiến một region bị đánh dấu không khỏe chỉ vì một dịch vụ phụ trợ ngắn hạn lỗi; ngược lại, probe trả 200 khi API không kết nối được Cosmos DB cũng có thể đánh lừa định tuyến. Cần phân biệt **liveness, readiness và end-to-end synthetic transaction**.

### 11.2. API cần quản lý retry và timeout

Một request thường đi qua:

~~~text
Client -> Azure Front Door -> API Region A/B
       -> Cosmos DB SDK -> write region hoặc read region đủ điều kiện
       -> Response -> Client
~~~

Tầng ứng dụng phải đặt timeout hữu hạn, giới hạn retry, backoff/jitter, circuit breaker khi phù hợp và idempotency cho write. Trên Cosmos DB, **429 là throttling**, trong khi timeout hoặc lỗi endpoint vùng có thể yêu cầu điều tra connectivity/SDK failover. Không coi mọi lỗi đều có thể retry vô hạn.

### 11.3. Quan sát session khi người dùng đổi vùng

Front Door có thể đưa hai request của cùng người dùng tới hai API khác nhau trong quá trình failover hoặc theo chính sách định tuyến. Với Session consistency, cần xác định session token được xử lý ra sao. Cookie affinity không luôn giải quyết được mọi tình huống lỗi, và cache trên API A không có nghĩa API B đã biết trạng thái mới.

Trong lab, thử chuỗi **write A → read A → read B** và so kết quả trước/sau khi đổi ưu tiên region.

## 12. Diễn tập khi Region A hoặc Region B gặp sự cố

Thiết kế ít nhất hai kịch bản tách biệt. **Không kích hoạt failover thật trên production**; chỉ tiến hành trong tài khoản lab được cấp quyền và có kế hoạch rollback/cleanup.

### 12.1. Kịch bản A: chỉ API Region A lỗi

**Given:** Cosmos account vẫn khỏe ở hai region; API A và API B đều hoạt động; Front Door có health probe.

**When:** Trong staging, chủ động làm API A không nhận traffic (ví dụ disable test origin bằng quy trình được duyệt).

**Then:** Front Door chuyển request mới sang API B; read/write vẫn thực thi theo khả năng Cosmos account và consistency đã thiết lập.

Quan sát:

- Thời gian từ `T_impact` đến khi người dùng đạt lại SLI.
- Request bị lỗi hoặc timeout trong lúc đổi origin.
- p95/p99 latency từ khách hàng ở các khu vực.
- Session token/cache, những request đang chạy và cơ chế idempotency.
- Read/write RU và status code ở Cosmos DB.

**Không cần failover database** nếu chỉ API A hỏng; làm nhiều thay đổi cùng lúc sẽ khó chứng minh nguyên nhân và làm tăng rủi ro.

### 12.2. Kịch bản B: write region của Cosmos DB không khả dụng

Với account **single-write** có các region đủ điều kiện và cơ chế automatic failover đã bật khi phù hợp, một lỗi write region có thể làm dịch vụ chuyển vai trò write sang vùng khác theo hành vi được hỗ trợ. Điều này khác với thao tác điều phối API bằng Front Door.

Các bước trong **môi trường kiểm soát**:

1. Ghi cấu hình region, failover priorities, consistency, write mode, network và trạng thái replication trước bài test.
2. Xác minh nguồn dữ liệu, điểm khôi phục và tiêu chí RTO/RPO của lab; tạo synthetic items với ID/ack timestamps độc lập.
3. Chọn **phương pháp thử an toàn mà Azure hỗ trợ**, có phê duyệt và stop conditions. Nếu chỉ đánh giá kiến trúc, dùng tabletop/mô phỏng SDK endpoint lỗi thay vì ép account failover thật.
4. Quan sát SDK diagnostics, errors, request routing, role/failover events và thời gian ứng dụng ngừng/tiếp tục ghi.
5. Sau khi dữ liệu phục vụ lại, đối soát ID đã xác nhận, dữ liệu trùng, transaction commit không rõ trạng thái và thứ tự update.
6. Xác minh read/write tại cả hai API region, giám sát và năng lực còn lại.
7. Khôi phục trạng thái mong muốn bằng quy trình riêng; kiểm tra replication và quyền, không tự ý ép failback.

**Không cam kết RTO=0 hoặc RPO=0** cho mọi cấu hình Cosmos DB. Dữ liệu có thể được replication bất đồng bộ tùy mức consistency/topology; cần hiểu loại lỗi và bảo đảm của dịch vụ, sau đó đo theo nghiệp vụ. Chỉ thấy SDK trả lại HTTP 200 không đủ để kết luận dữ liệu không mất.

### 12.3. Kịch bản C: multi-region writes và conflict (thiết kế mở rộng)

Nếu doanh nghiệp chọn multi-write, hãy mô hình hóa hai API ghi đồng thời vào cùng `id` thuộc cùng partition từ hai vùng với nội dung khác nhau.

~~~text
Region A: order-10001.status = "PAID"
Region B: order-10001.status = "CANCELLED"

Yêu cầu nghiệp vụ:
  - Không thể đồng thời là PAID và CANCELLED nếu chưa có quy tắc rõ.
  - Không gửi hoàn tiền/thanh toán hai lần.
  - Mọi quyết định cần audit và dữ liệu authoritative.
~~~

Mô hình giải quyết xung đột như **Last Writer Wins (LWW)** hoặc cơ chế do dịch vụ/cấu hình hỗ trợ có thể không phản ánh đúng luật nghiệp vụ: timestamp cuối không chứng minh thanh toán là hợp lệ. Một hệ thống đơn hàng nên xem xét **state machine, version, idempotency, các thao tác append-only/event và giao dịch trong phạm vi cho phép**, thay vì đặt toàn bộ niềm tin vào conflict policy tự động.

Bài lab **không bắt buộc bật multi-write thật**. Chỉ cần thiết kế tình huống, tiêu chí correctness và phép thử cho bước mở rộng.

## 13. Đo kết quả bằng dữ liệu có thể đối chiếu

Một báo cáo capstone phải có SLI và metric ở ba tầng: người dùng, API/ingress và Cosmos DB.

### 13.1. Bảng telemetry cần thu

| Tầng | Metric / bằng chứng | Ý nghĩa |
| --- | --- | --- |
| Front Door | Request success, origin health, latency và phân bố route | Người dùng có đến API khỏe đúng vùng? |
| API | 5xx, p95/p99, timeout, retry, thread/connection metrics | Ứng dụng có thực sự phục hồi? |
| Cosmos DB | Request Units, normalized RU consumption, throttled requests 429 | Sizing/partitioning đủ tải không? |
| Cosmos DB | End-to-end/client-side latency, service latency nếu có | Tách RTT/SDK retry với thời gian dịch vụ |
| Cosmos DB | Region availability, failover events và diagnostics | Khi nào routing/failover thay đổi? |
| Dữ liệu | ID đơn, ack timestamps, version, observed read | Đo stale/missing/duplicate và correctness |
| SRE | T_impact, T_detected, T_recovered | Đối chiếu RTO/SLO |
| Cost | Throughput theo vùng, storage, network, monitoring | Kiểm soát ngân sách khi thêm replica |

**RU/s là năng lực được cấp, RU là chi phí từng thao tác.** Không dùng tổng RU tiêu thụ để trực tiếp kết luận latency hoặc độ tin cậy; phải xét phân bố workload, partitioning và topology.

### 13.2. Bảng phép đo cho hai region

| Phép thử | API A | API B | Điều cần kết luận |
| --- | --- | --- | --- |
| Point read same tenant | Ghi p95 và RU | Ghi p95 và RU | Đường đọc có gần người dùng hơn không? |
| Create item | Ghi latency và RU | Ghi latency và RU | Vùng ghi chính ảnh hưởng write latency ra sao? |
| Write A → read B | Ghi thành công | Ghi độ trễ thấy item | Session/consistency đã được xử lý đúng chưa? |
| Load peak | 429, p95, errors | 429, p95, errors | Throughput, hotspot và retry có phù hợp? |
| API A unavailable | Không nhận request mới | Đạt SLI trong cửa sổ | Front Door failover có hoạt động? |
| Database write-region disruption | Errors và timeouts | Errors và timeouts | Failover dữ liệu có đạt mục tiêu và bảo toàn dữ liệu? |

### 13.3. Ví dụ kết quả giả định

Giả sử sau phép thử staging ở một mức tải thấp đã xác định:

~~~text
API Region A, read p95:                 35 ms
API Region B, read p95:                 42 ms
API Region A, write p95:                70 ms
API Region B, write p95:               145 ms
API failover observed disruption:       18 s
Cosmos DB throttling (429):             0,4% requests
Observed stale read without shared token: có trường hợp
Total test period:                       15 phút
~~~

Đây **không phải số liệu Azure cam kết**. Cần ghi tải, công cụ sinh request, client location, consistency, cấu hình SDK, partition key và độ tin cậy thống kê. Nếu kiểm thử failover làm dữ liệu/permission thay đổi, phải ghi rõ phạm vi và thời điểm.

**Không kết luận có thể đạt availability production chỉ từ 15 phút thử tải thấp.** Cần bổ sung peak, burst, dependency failure, quy trình rollback, consistency và dữ liệu đã xác nhận.

## 14. Tối ưu chi phí cho kiến trúc đa region

Global distribution đem lại latency/resilience nhưng tăng chi phí ở nhiều lớp:

| Thành phần | Lý do có thể tăng chi phí | Cách xem xét |
| --- | --- | --- |
| Cosmos DB throughput | Cấp RU/s và replica theo mô hình nhiều region | Theo dõi throughput theo region, utilization và 429 |
| Cosmos DB storage | Dữ liệu và indexing được nhân bản theo topology account | Dung lượng, TTL, indexing, region count |
| Multi-region writes | Cơ chế ghi/phân phối có thể có đơn giá/điều kiện khác | Kiểm tra bảng giá và khả năng hỗ trợ của cấu hình |
| Ứng dụng hai vùng | Compute, autoscale minimum, network, ingress | N-1 capacity, giờ hoạt động và traffic |
| Azure Front Door / WAF | Traffic routing, requests, bandwidth và security features | Chọn tier và tính theo usage thực tế |
| Network egress | Truyền dữ liệu giữa region/Internet hoặc qua dịch vụ trung gian | Đo luồng dữ liệu và region placement |
| Monitoring | Logs, tracing và retention ở hai vùng | Sampling/retention phù hợp, giữ audit cần thiết |
| DR/backup | Continuous backup/restore và bài diễn tập | RTO/RPO, retention, chi phí thử nghiệm |

**Không có mức giá cố định trong bài học**, vì giá thay đổi theo region, throughput, cấu hình, agreement, kỳ hạn và thời điểm. Trước khi dựng môi trường, sử dụng Azure Pricing Calculator/Cost Management và xem các hạn mức/tùy chọn áp dụng.

### 14.1. Tính chi phí trên giao dịch thành công

Giả sử toàn workload (Cosmos DB, API, Front Door, network, logs và chi phí dùng chung) phát sinh **2.400 USD/tháng** và có **120.000 giao dịch hợp lệ**:

~~~text
Cost per successful transaction
  = 2.400 / 120.000
  = 0,02 USD / giao dịch
~~~

Nếu thêm region làm chi phí tăng lên 3.000 USD nhưng giúp phục vụ 180.000 giao dịch hợp lệ:

~~~text
3.000 / 180.000 ≈ 0,0167 USD / giao dịch
~~~

Tổng chi tăng nhưng unit cost có thể giảm. Quyết định vẫn cần đánh giá SLO, data residency, RTO/RPO và rủi ro vận hành; không tối ưu chỉ bằng một chỉ số.

### 14.2. Guardrail FinOps cho lab

- Đặt budget và thông báo theo scope thử nghiệm; **budget không tự dừng tài nguyên**.
- Bắt đầu bằng mức throughput nhỏ phù hợp tính năng; không dùng peak production làm mặc định.
- Giới hạn thời gian tạo/tồn tại account và app nhiều region; có owner chịu trách nhiệm cleanup.
- Đo RU trên mỗi thao tác, tối ưu partition key và query trước khi tăng RU/s.
- Xem các tài nguyên vẫn có phí khi application bị stop, nhất là throughput/replica và monitoring.
- Không bỏ backup, security telemetry hoặc độ tin cậy bắt buộc chỉ để giảm chi phí trong production.

## 15. Quy trình thao tác lab từng bước

Một quy trình tuần tự để người học tự thực hiện và ghi chứng cứ:

### Bước 1 — Chuẩn bị thiết kế

Tạo tài liệu gồm: mục tiêu SLO/RTO/RPO và nơi lưu dữ liệu, hai region dự kiến, danh sách API endpoints, account write mode, consistency, `/tenantId`, RU/s dự kiến, budget và người chịu trách nhiệm.

**Đầu ra:** sơ đồ, quyết định single-write/multi-write và bảng rủi ro.

### Bước 2 — Tạo tài nguyên test

Tạo resource group, Cosmos DB for NoSQL account, hai region, database `commerce`, container `orders`. Xác minh account replication và read/write regions từ Portal/CLI. Bật monitor/diagnostics phù hợp và chụp cấu hình *đã lọc nhạy cảm*.

**Đầu ra:** account configuration, region list, consistency, container partition path.

### Bước 3 — Chạy Java SDK

Điền endpoint và credential test an toàn vào biến môi trường, thay SDK version, chạy `CosmosGlobalLab`, ghi request charge cho create/read. Kiểm tra item xuất hiện trong Data Explorer ở logical partition `tenant-lab`.

**Đầu ra:** một item synthetic, kết quả read, RU/operation.

### Bước 4 — Thêm API hai vùng

Triển khai hai bản API có cùng contract, chỉ khác preferred region/telemetry metadata. Đặt endpoint health kiểm tra readiness. Cấu hình Front Door hoặc mô phỏng HTTP routing an toàn trong môi trường test.

**Đầu ra:** hai API endpoints, bảng route và health.

### Bước 5 — Thử tính nhất quán

Tạo đơn qua API A; lập tức đọc qua API A và B, thử Session, ghi session token strategy, thời gian quan sát và trạng thái đọc. Khi thấy stale data, giải thích vì sao; không tự mặc định lỗi SDK.

**Đầu ra:** bảng thực nghiệm write/read và consistency decision record.

### Bước 6 — Thử tải và partitioning

Sinh các yêu cầu point read/create ở mức tải test, đo p95, RU/operation, 429 và retries. Thử mô hình workload lệch tenant (ví dụ 80% request thuộc một tenant) để quan sát hotspot, nhưng không gây throttling trên production.

**Đầu ra:** biểu đồ theo thời gian, phân tích hotspot và phương án tuning.

### Bước 7 — Diễn tập lỗi ở tầng ứng dụng

Vô hiệu hóa **origin API A** trong môi trường thử theo quy trình; quan sát Front Door chuyển traffic sang API B và độ trễ hội tụ. Không đồng thời thay đổi database account.

**Đầu ra:** T_impact/T_recovered và evidence failover ứng dụng.

### Bước 8 — Phân tích failover dữ liệu

Làm tabletop hoặc test failover theo quy trình dịch vụ được phép trên account lab, tập trung vào write region, session, dữ liệu đã xác nhận và khả năng kết nối từ hai API. Đặt stop condition để tránh mất dữ liệu ngoài phạm vi.

**Đầu ra:** runbook, RTO/RPO quan sát được (nếu đã kiểm thử thật) hoặc danh sách giả định chưa xác minh.

### Bước 9 — Đánh giá chi phí và cleanup

Tính chi phí đa region theo cấu hình thực tế, so với mục tiêu unit cost. Xóa tài nguyên **chỉ trong resource group thử nghiệm thuộc quyền sở hữu của bài lab** theo quy trình được phê duyệt; xác minh không có dữ liệu thật và không còn dependency ngoài phạm vi. Nếu tài nguyên chia sẻ, cleanup từng đối tượng thay vì xóa cả group.

**Đầu ra:** budget report, cost/transaction, checklist cleanup.

## 16. Troubleshooting theo symptom

| Symptom | Nguyên nhân có thể | Phép kiểm tra / hướng xử lý |
| --- | --- | --- |
| HTTP 404 khi đọc item | Sai `id`, `tenantId`, database/container hoặc chưa replicate/không đọc được | Kiểm tra partition key và trạng thái session; đối chiếu item trong Data Explorer |
| HTTP 409 khi create | Cùng `id` trong một logical partition đã tồn tại | Kiểm tra idempotency key, payload và transaction history |
| HTTP 429 nhiều | Thiếu RU/s, query tốn RU, hotspot logical partition | Đo RU, normalized consumption, 429/partition, autoscale/index |
| HTTP 403 | Credential/RBAC, firewall, network restrictions, data-plane role | Xác định error substatus, principal và đường kết nối |
| Đọc ngay ở Region B không thấy dữ liệu mới | Consistency/session context, replication và routing | Kiểm tra session token, level, preferred regions và timeline |
| Ghi từ API B chậm hơn A | Single-write, network distance tới write region | Đo RTT, client diagnostics, xem business yêu cầu multi-write không |
| Front Door vẫn gửi traffic vào API lỗi | Health probe/route/origin configuration sai hoặc chưa hội tụ | Kiểm tra probe, host header, origin state, logs |
| SDK không kết nối được từ VNet B | Private DNS/Endpoint, routes, firewall/TLS, connection mode | Test DNS/TCP/TLS từ chính VNet B, kiểm tra account networking |
| Kích hoạt multi-write và dữ liệu xung đột | Ghi đồng thời cùng item, conflict policy không hợp logic | Thiết kế state machine, ETag, idempotency và conflict handling |
| Tăng RU/s nhưng latency vẫn cao | Network RTT, retry, query logic, app bottleneck | Tách client/server latency, đo query/partition, p95 |
| Chi phí cao hơn dự kiến | Thêm region, RU/s, replica storage, Front Door/logs | So Cost Analysis, region count và budget |
| Failover xong vẫn có dữ liệu thiếu/trùng | Replication window, giao dịch không rõ trạng thái, retry | Đối soát bằng ID/ack và runbook dữ liệu, không chỉ HTTP 200 |

## 17. Báo cáo capstone và rubric đánh giá

### 17.1. Mẫu báo cáo nhóm

~~~markdown
# Cosmos DB Global Distribution Lab — <mã bài tập>

## Kiến trúc và mục tiêu
- Workload, owner, các region, account read/write mode:
- SLO, RTO/RPO, data residency:
- Sơ đồ Front Door → API A/B → Cosmos DB:
- Partition key, document schema, consistency:

## Kết quả chức năng
- Create/read item qua Java SDK:
- Idempotency và lỗi 409:
- Đọc sau ghi từ API A/B:
- Session token / consistency notes:

## Kết quả hiệu năng
| Test | Region/client | p95 | RU/op | HTTP 429 | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... |

## Khả năng phục hồi
- API region failure injection:
- Database write-region scenario:
- T_impact, T_recovered, bằng chứng dữ liệu:

## Bảo mật và chi phí
- RBAC/credential handling, network isolation:
- Cost driver, budget và unit cost:

## Kiến nghị
- Rủi ro còn lại, trade-off:
- Action item, owner, acceptance test:
- Cleanup đã xác minh:
~~~

### 17.2. Rubric nghiệm thu

| Tiêu chí | Đạt khi |
| --- | --- |
| **Đúng phạm vi** | Phân biệt API vùng, Cosmos DB account/replica, điểm vào và dependencies |
| **Partitioning** | Giải thích được vì sao chọn `/tenantId`, rủi ro hotspot và phương án sửa |
| **Consistency** | Có quyết định theo nghiệp vụ và phép thử đọc sau ghi xuyên API region |
| **Chạy được luồng CRUD cơ bản** | Tạo và đọc item bằng SDK; đo request charge |
| **Failover hiểu đúng** | Phân biệt origin failover và database write-region failover |
| **Dữ liệu an toàn** | Không dùng dữ liệu thật, không có secret trong báo cáo, idempotency được xem xét |
| **Hiệu năng** | Đo p95, 429, RU/operation và phân tích khi tăng tải |
| **Chi phí** | Có budget, các thành phần phí theo region và unit cost |
| **Kiểm chứng** | Có timeline, bằng chứng, điều kiện đạt/không đạt rõ |
| **Vận hành** | Có runbook, rollback/cleanup, chủ sở hữu và việc cần làm tiếp |

## 18. Những ngộ nhận cần tránh

**“Thêm hai region là ứng dụng tự chạy toàn cầu.”** Không đúng. Nếu API chỉ chạy ở một vùng hoặc Front Door không chuyển origin khi lỗi, người dùng vẫn mất dịch vụ.

**“Cosmos DB đọc ở đâu cũng luôn thấy dữ liệu mới nhất.”** Còn phụ thuộc consistency, session context, account settings và vùng. Session token across API instances là một bài toán ứng dụng cần kiểm tra.

**“Partition key là chọn region lưu dữ liệu.”** Sai. Partition key quyết định phân bố logic; vùng replication của Cosmos DB là cấu hình khác.

**“Cứ tăng RU/s là hết 429.”** Một hot partition, truy vấn cross-partition hoặc query/index thiết kế kém có thể vẫn gây throttling và tăng chi phí.

**“Bật multi-write không có rủi ro xung đột.”** Sai. Multi-region writes cần conflict resolution và quy tắc business correctness; LWW không phù hợp mọi nghiệp vụ.

**“Automatic failover nghĩa là không gián đoạn và không mất dữ liệu.”** Không thể kết luận như vậy cho mọi topology và consistency; cần đo SDK/client errors, RTO/RPO và đối soát giao dịch.

**“Budget 100% sẽ tự dừng Cosmos DB.”** Budget là cảnh báo, không phải trần chi cứng; cần kiểm soát throughput, region, tài nguyên tồn tại và cleanup.

**“Cosmos DB thay thế backup vì đã có nhiều replica.”** Replica có thể sao chép cả lỗi logic/xóa nhầm; backup/restore và data recovery là một cơ chế độc lập.

## 19. Tổng kết

Một ứng dụng phân phối toàn cầu tốt không chỉ có **Cosmos DB ở nhiều region**. Nó phải có đường vào ứng dụng nhiều vùng, mẫu phân vùng phù hợp truy vấn, consistency đúng yêu cầu nghiệp vụ, bảo vệ danh tính/dữ liệu, khả năng xử lý 429 và retry an toàn, kế hoạch failover tách biệt cho API và database, cùng hệ thống giám sát và kiểm soát chi phí.

Bài thực hành đã kết nối những kiến thức Azure quan trọng: **subscription/resource group** để cô lập tài nguyên, **Entra ID/RBAC và mạng riêng** để bảo vệ truy cập, **compute/Front Door** để phục vụ người dùng ở nhiều địa điểm, **Cosmos DB for NoSQL** để phân phối dữ liệu, **Azure Monitor** để xác minh SLI và **Cost Management** để đánh giá giá trị. Kết quả đáng tin nhất là một bộ **phép đo và bằng chứng có thể lặp lại**, chứ không phải chỉ thấy resource chuyển sang trạng thái Running.
