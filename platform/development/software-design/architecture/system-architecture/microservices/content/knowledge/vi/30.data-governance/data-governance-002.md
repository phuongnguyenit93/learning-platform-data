# Phân loại dữ liệu nhạy cảm và giới hạn sao chép

> **Lĩnh vực:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Quản trị dữ liệu (Data Governance)  
> **Mục tiêu:** Thiết kế cách nhận diện mức độ nhạy cảm của dữ liệu, đặt quy tắc được phép sử dụng và sao chép, kiểm soát việc dữ liệu lan ra hệ thống phụ, môi trường thử nghiệm, cache, log và backup; biết cách chứng minh các bản sao có chủ sở hữu, mục đích, phạm vi truy cập và vòng đời phù hợp.

## 1. Vì sao một bản ghi có thể trở thành hàng chục bản sao?

Một bản ghi khách hàng có thể được tạo ở Customer Service, đồng bộ sang Order Service, gửi qua message broker, xuất vào Data Warehouse, cache trong Redis, đưa vào search index, ghi vào trace khi lỗi, chuyển đến hệ thống hỗ trợ khách hàng và xuất thành file CSV. Database ban đầu được bảo vệ tốt nhưng **khả năng lộ dữ liệu phụ thuộc vào mọi bản sao**, kể cả những bản sao mà nhóm quản lý nguồn không chủ động tạo.

Ví dụ một đơn hàng:

~~~text
Customer Database  ← nguồn dữ liệu khách hàng
      |
      +-- Customer API → Order Service → Order DB
      |                                 |
      |                                 +-- OrderCreated event
      |                                           |
      |                              +------------+------------+
      |                              |            |            |
      |                              v            v            v
      |                         Search Index   Analytics     Notification
      |
      +-- Customer profile cache
      +-- Data export / reports
      +-- Operations and support tooling
      +-- Backups / snapshots
      +-- Logs, traces, error reports
~~~

Nếu event OrderCreated chứa cả số điện thoại, địa chỉ nhà, số định danh và nội dung ghi chú không cần thiết, mọi consumer và hệ thống ghi log event đều có cơ hội nhận các trường đó. Mặc dù Customer DB có phân quyền chặt, event vô tình biến các trường nhạy cảm thành **dữ liệu phân tán khó thu hồi**.

Vì thế quản trị dữ liệu nhạy cảm cần trả lời:

1. **Dữ liệu này là gì, thuộc nhóm nhạy cảm nào và vì sao?**
2. **Ai có quyền biết hoặc xử lý nó, trong mục đích nào?**
3. **Ở đâu là bản dữ liệu nguồn, ở đâu là bản sao và có thực sự cần sao chép không?**
4. **Bản sao có mức bảo vệ, vòng đời, hạn lưu giữ và cơ chế xóa tương ứng không?**
5. **Làm sao phát hiện bản sao mới xuất hiện ngoài kiểm soát?**
6. **Khi có sự cố, thay đổi mục đích hoặc yêu cầu xóa, ai có thể truy vết và xử lý mọi nơi chứa dữ liệu?**

**Nguyên tắc cốt lõi:** đừng chỉ bảo vệ database nguồn; hãy **giảm số nơi lưu dữ liệu nhạy cảm và bảo vệ từng lần dữ liệu được sao chép, chuyển giao hoặc biến đổi**.

## 2. Phân biệt classification, labeling, access control và data minimization

- **Data classification (phân loại dữ liệu):** xác định mức độ nhạy cảm, nghĩa vụ bảo vệ và hệ quả nếu dữ liệu bị lộ, sửa sai hoặc không còn khả dụng.
- **Labeling (gắn nhãn):** ghi lại phân loại dưới dạng metadata, tag hoặc policy có thể đọc bởi người và công cụ.
- **Access control:** xác định chủ thể được đọc, ghi, xuất, chia sẻ hay xóa dữ liệu ở thời điểm và ngữ cảnh cụ thể.
- **Purpose limitation:** chỉ xử lý dữ liệu cho mục đích được xác định và được phép; quyền truy cập kỹ thuật không tự động đồng nghĩa có quyền dùng cho mục đích bất kỳ.
- **Data minimization:** chỉ thu thập, truyền và lưu những trường thực sự cần cho mục đích.
- **Copy limitation:** giảm việc nhân bản dữ liệu, đặt ranh giới số nơi lưu và thời gian tồn tại của bản sao.
- **Retention:** quy định giữ dữ liệu bao lâu và khi nào phải xóa hoặc chuyển trạng thái theo chính sách.
- **Data lineage:** biết dữ liệu đến từ đâu, đã đi qua biến đổi nào, hiện nằm ở hệ thống nào.
- **De-identification:** loại bỏ/biến đổi định danh để giảm khả năng liên kết tới cá nhân; hiệu quả tùy phương pháp, ngữ cảnh và dữ liệu bổ trợ.
- **Anonymization:** làm dữ liệu không còn nhận diện được chủ thể theo tiêu chuẩn và threat model áp dụng; chỉ xóa tên không đủ để mặc nhiên coi dữ liệu đã ẩn danh.

Có nhãn “Confidential” trong schema nhưng mọi service đều được đọc không tạo ra bảo vệ thực. Ngược lại, access control có thể đúng kỹ thuật nhưng dữ liệu vẫn bị sao chép quá nhiều khiến việc thu hồi và xóa trở nên khó khăn.

### 2.1. Nhạy cảm không chỉ là quyền riêng tư

Một dữ liệu có thể nhạy cảm vì nhiều lý do:

| Loại rủi ro | Ví dụ | Hệ quả |
|---|---|---|
| Quyền riêng tư | Thông tin liên hệ, vị trí, hồ sơ khách hàng | Xâm phạm quyền riêng tư, bị lạm dụng |
| Xác thực và quyền truy cập | API key, access token, private key, reset code | Chiếm tài khoản, gọi API trái phép |
| Tài chính và giao dịch | Thông tin thanh toán, hạn mức, dữ liệu hóa đơn | Gian lận, tổn thất tài chính |
| Sức khỏe và dữ liệu đặc biệt | Hồ sơ y tế, thông tin nhạy cảm của cá nhân | Tổn hại nghiêm trọng nếu lộ |
| Bí mật kinh doanh | Giá hợp đồng chưa công bố, thuật toán độc quyền | Thiệt hại cạnh tranh |
| An ninh hạ tầng | Sơ đồ mạng nội bộ, endpoint quản trị, cấu hình khóa | Tăng khả năng tấn công |
| Tính toàn vẹn | Trạng thái thanh toán, số dư, quyền sở hữu tài sản | Sai lệch quyết định, mất tiền |
| Tính khả dụng | Khóa giải mã duy nhất, bản sao phục hồi | Không thể khôi phục khi mất |

Một hệ thống nên xét **confidentiality, integrity và availability** của dữ liệu, không chỉ “PII hay không”. Chẳng hạn một bảng tổng hợp giá trị không có tên cá nhân vẫn có thể là bí mật kinh doanh, còn một số đếm tồn kho sai có thể gây oversell.

## 3. Thiết kế hệ thống phân loại thực dụng

Không có một bộ tên nhãn bắt buộc cho mọi tổ chức. Có thể khởi đầu bằng bốn mức minh họa và điều chỉnh theo chính sách nội bộ, quy định ngành và rủi ro:

| Mức | Ý nghĩa | Ví dụ minh họa | Hướng kiểm soát |
|---|---|---|---|
| PUBLIC | Có thể công bố có chủ đích | Nội dung marketing đã duyệt | Kiểm soát toàn vẹn, nguồn xuất bản |
| INTERNAL | Phục vụ công việc nội bộ, không công khai mặc định | Quy trình vận hành, thống kê nội bộ ít nhạy cảm | Tài khoản nhân sự và quyền theo vai trò |
| CONFIDENTIAL | Lộ hoặc sử dụng sai có thể gây hại đáng kể | Email khách hàng, địa chỉ giao hàng, dữ liệu hợp đồng | Need-to-know, mã hóa, hạn chế xuất, retention |
| RESTRICTED | Rủi ro rất cao hoặc có nghĩa vụ bảo vệ đặc biệt | Private keys, secrets, thông tin thanh toán nhạy cảm, dữ liệu đặc biệt | Tách vùng lưu, kiểm soát chặt, audit, không sao chép tùy ý |

Nhãn ở đây là **mẫu thiết kế**, không thay thế quy định pháp luật, hợp đồng hoặc chính sách thực tế. Một tổ chức có thể phân loại “Highly Confidential”, “Regulated”, “Sensitive Personal Data” hoặc thêm các thuộc tính độc lập. Cần tránh mặc định rằng mọi thông tin có cùng mức bảo vệ chỉ vì đều nằm trong một bảng.

### 3.1. Gắn nhãn theo thuộc tính và ngữ cảnh

Ví dụ bảng customer:

| Trường | Phân loại gợi ý | Bản sao cần thiết? |
|---|---|---|
| customer_id ngẫu nhiên | INTERNAL/CONFIDENTIAL tùy khả năng liên kết | Chỉ nơi dùng làm khóa tham chiếu |
| display_name | CONFIDENTIAL trong ngữ cảnh hồ sơ riêng | Có thể hiển thị cho các use case được phép |
| email | CONFIDENTIAL | Notification cần nhận, analytics thường không |
| phone | CONFIDENTIAL | Logistics có thể cần một thời hạn |
| delivery_address | CONFIDENTIAL hoặc RESTRICTED theo chính sách | Fulfillment cần, search công khai không |
| password_hash | RESTRICTED | Không phát qua event và không đưa vào dịch vụ khác |
| reset_token | RESTRICTED | Lưu tại hệ thống xác thực dưới dạng verifier phù hợp |
| consent/preferences | CONFIDENTIAL, có yêu cầu tính toàn vẹn | Hệ thống thực thi mục đích xử lý được phép |
| risk_score | CONFIDENTIAL/RESTRICTED tùy nguy cơ | Chỉ service có use case rõ |

Ngay cả mã định danh giả ngẫu nhiên có thể trở thành dữ liệu cá nhân nếu dễ liên kết với chủ thể qua một bảng ánh xạ. Không coi hash email hoặc pseudonym là “vô danh tuyệt đối”.

### 3.2. Nhãn không nhất thiết là một số duy nhất

Một model giàu ý nghĩa hơn có thể chứa các chiều:

~~~yaml
dataAsset: customer.deliveryAddress
classification: CONFIDENTIAL
personalData: true
purposeTags:
  - FULFILL_ORDER
allowedConsumers:
  - fulfillment-service
retentionPolicyRef: customer-address-retention-v2
residencyPolicyRef: customer-region-policy
ownerTeam: customer-platform
sourceSystem: customer-service
exportRestricted: true
copyRequiresApproval: true
~~~

Đây là metadata minh họa, không phải tiêu chuẩn schema bắt buộc. Các trường “retentionPolicyRef”, “residencyPolicyRef” không được tự chế từ số ngày/vùng dữ liệu nếu tổ chức chưa phê duyệt chính sách.

Một số tổ chức cần phân biệt **mức bí mật**, **loại dữ liệu cá nhân**, **nguồn pháp lý/căn cứ xử lý**, **địa lý**, **mục đích**, **người quản trị** và **thời hạn** như các nhãn độc lập. Gom mọi nghĩa vào một enum duy nhất có thể khiến policy mơ hồ.

## 4. Quy tắc phân loại phải gắn vào vòng đời dữ liệu

Một chu trình quản trị:

~~~text
Discover data / define asset
          |
          v
Classify fields, records and datasets
          |
          v
Define allowed purposes and consumers
          |
          v
Approve storage, access and copy paths
          |
          v
Collect / ingest only required fields
          |
          v
Process, transmit and observe safely
          |
          v
Track derived copies and destinations
          |
          v
Retention, correction, revocation, deletion
          |
          v
Audit and periodically reassess classification
~~~

Phân loại một lần khi thiết kế schema là chưa đủ. Một cột trước đây chứa “ghi chú giao hàng” có thể về sau được dùng để lưu số định danh do người dùng nhập tự do. Khi source data, pipeline hoặc mục đích xử lý thay đổi, phân loại và cách phát tán cần được đánh giá lại.

### 4.1. Ai chịu trách nhiệm?

Phân biệt các vai trò:

- **Data owner:** quyết định mục đích, mức nhạy cảm, người nhận và ràng buộc dùng dữ liệu.
- **System owner:** chịu trách nhiệm vận hành thành phần lưu/truyền dữ liệu.
- **Security/privacy/compliance:** định nghĩa yêu cầu kiểm soát, tư vấn và đánh giá các trường hợp rủi ro theo chính sách.
- **Data steward/governance:** quản lý catalog, chất lượng metadata, lineage và việc tuân thủ quy trình.
- **Application team:** thực thi projection, minimization, access, logging, deletion và kiểm thử.
- **Operator/support:** truy cập trong phạm vi được cấp, có mục đích, thời hạn và audit phù hợp.

Không nên xem người tạo bảng lần đầu mặc nhiên có quyền phê duyệt mọi bản sao trong tương lai. Mỗi tài sản nhạy cảm cần có owner có thể liên hệ và cơ chế chuyển giao ownership khi hệ thống thay đổi.

## 5. Giới hạn sao chép: vì sao “mỗi service một bản đầy đủ” là nguy hiểm?

Trong microservices, nhóm phát triển thường muốn mỗi service tự quản lý dữ liệu để giảm coupling. Nhưng việc một service có database riêng **không đồng nghĩa phải chép toàn bộ hồ sơ khách hàng** vào database đó.

Một bản sao tạo chi phí bảo vệ ở nhiều chiều:

1. Thêm điểm truy cập, credential, người vận hành và tài khoản dịch vụ.
2. Thêm data-at-rest cần mã hóa và quản lý key.
3. Thêm log, backup, snapshot, replica, index và cache phụ phát sinh từ bản sao.
4. Thêm nguy cơ dữ liệu cũ, sai thứ tự hoặc khác chính sách khi nguồn cập nhật.
5. Thêm điểm phải xử lý khi người dùng sửa, thu hồi hoặc yêu cầu xóa.
6. Thêm vùng/đơn vị xử lý dữ liệu có thể không được phép.
7. Thêm rủi ro do data export, truy vấn ad hoc và phân quyền không đồng bộ.

Vì vậy cần tách hai câu hỏi:

- **Service có cần biết dữ liệu này để hoàn thành nghiệp vụ không?**
- **Service có cần lưu một bản sao bền vững của chính dữ liệu đó không?**

Có thể service cần nhận số điện thoại một lần để gửi thông báo nhưng không cần ghi số điện thoại vào bảng Order. Có thể analytics chỉ cần số đơn theo vùng chứ không cần địa chỉ đường/phố của từng khách.

### 5.1. Data minimization theo mục đích

Một số lựa chọn:

| Nhu cầu | Cách tiếp cận ưu tiên khi phù hợp |
|---|---|
| Biết khách hàng nào đặt đơn | Lưu customer ID/opaque reference |
| Hiển thị tên khách trong dashboard đã cấp quyền | API với authorization hoặc view giới hạn trường |
| Gửi thông báo | Dịch vụ sở hữu thông tin liên hệ nhận lệnh và tự xử lý |
| Fulfillment cần địa chỉ giao | Cấp bản sao tối thiểu, hạn chế TTL/retention và quyền |
| Tổng hợp doanh thu theo khu vực | Dùng dữ liệu tổng hợp hoặc nhóm địa lý đủ rộng |
| Đếm lượt đăng nhập | Event với ID giả danh/aggregate, không truyền credential |
| Debug một lỗi | Correlation ID, error code và metadata an toàn |
| Dùng dữ liệu sản xuất trong test | Tạo synthetic data hoặc dữ liệu được biến đổi theo policy |

Không có câu trả lời duy nhất cho mọi nhu cầu. Đồng bộ dữ liệu có thể cần để bảo đảm tính khả dụng hoặc tính nhất quán nghiệp vụ; nếu copy, hãy chứng minh **vì sao bắt buộc, copy gì, ai có quyền, tồn tại trong bao lâu và làm sao xóa/đối soát**.

### 5.2. “Copy budget” như một công cụ quản trị

Khái niệm **copy budget** là một cách thiết kế nội bộ: mỗi asset nhạy cảm có danh sách nơi lưu được phê duyệt và giới hạn phát tán. Nó không nhất thiết là một con số tuyệt đối, vì backup/replica có thể cần thiết cho phục hồi, nhưng phải tránh bản sao không chủ.

Ví dụ:

~~~text
Asset: customer.delivery_address
Owner: Customer Platform
Approved durable stores:
  - Customer primary database
  - Encrypted recovery backups under retention policy
  - Fulfillment store (required fields only; bounded retention)
Approved transient uses:
  - Fulfillment API request over authenticated TLS
  - Shipment label generation in a controlled worker
Not approved by default:
  - Analytics raw lake
  - Application logs / traces
  - Developer laptops
  - Search index available to other tenants
  - General-purpose customer event
~~~

Các nơi được phép phải xuất phát từ policy đã được phê duyệt. Ví dụ nhằm chỉ ra **hình thức quyết định**, không xác nhận đây là chính sách thực tế của tổ chức.

### 5.3. Copy lifecycle phải có trạng thái

Khi tạo một bản sao được phép, cần biết:
- Bản sao được tạo khi nào và vì mục đích nào?
- Dùng key hoặc định danh nào để tìm lại khi cần xóa?
- Có thể cập nhật sai lệch từ source không?
- Bản sao có TTL hoặc retention policy gì?
- Có được tạo thêm bản sao thứ cấp không?
- Ai có quyền export hay chia sẻ?
- Hệ thống nào phải được thông báo khi nguồn thay đổi/xóa?
- Nếu consumer của một deletion event bị hỏng, ai phát hiện và khôi phục?

Một bảng data lineage chỉ liệt kê “Customer → Analytics” không đủ nếu analytics còn tạo dataset tạm, ML feature store, notebook output và CSV. Cần theo dõi lineage tới các nơi có rủi ro thực tế, tùy khả năng kỹ thuật và mức dữ liệu.

## 6. Chọn giữa tham chiếu, API, projection và event

### 6.1. Chỉ lưu reference

Thay vì nhân bản email trong 7 service, Order Service lưu customerId và gọi một API có kiểm soát khi thật sự cần email. Ưu điểm: một nguồn quản trị chính, cập nhật/thu hồi dễ hơn; nhược điểm: tăng coupling runtime và rủi ro latency/availability.

Có thể dùng cache ngắn hạn theo authorization/freshness contract nếu được phép, nhưng cache cũng là một **bản sao dữ liệu** cần gắn nhãn, TTL và xóa.

### 6.2. Projection tối thiểu

Một service cần truy vấn nhanh có thể lưu projection chỉ những trường cần thiết:

~~~text
Customer Service
  customer_id
  display_name
  email
  phone
  address
  preferences
  status

Order read projection
  customer_id
  display_name (nếu được phép)
  account_status_for_checkout
~~~

Projection không được tự động mang mọi trường “cho tiện tương lai”. Mỗi trường thêm là thêm nghĩa vụ cập nhật/xóa, phân quyền và kiểm thử.

### 6.3. Event schema có data minimization

**Ví dụ không tốt** nếu consumer chỉ cần trạng thái đơn nhưng event gửi toàn bộ dữ liệu khách:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "ord-123",
  "customer": {
    "name": "Nguyen Van A",
    "email": "person@example.invalid",
    "phone": "+00...",
    "deliveryAddress": "full address",
    "accountRecoveryData": "sensitive material"
  }
}
~~~

Mẫu tối thiểu hơn:

~~~json
{
  "eventId": "evt-456",
  "eventType": "OrderCreated",
  "orderId": "ord-123",
  "customerRef": "customer-opaque-ref",
  "orderVersion": 1,
  "occurredAt": "2026-11-12T03:00:00Z"
}
~~~

Nhưng event tối thiểu chưa tự giải quyết mọi nhu cầu: Fulfillment thực sự cần địa chỉ, nên có thể yêu cầu payload riêng được cấp quyền theo mục đích, hoặc một dịch vụ chuyên trách gửi lệnh giao hàng với dữ liệu tối thiểu. Không ép mọi consumer tự gọi Customer API ồ ạt nếu điều đó tạo bottleneck mới; chọn giữa sự tự chủ và giảm bản sao dựa trên rủi ro, SLO và thiết kế.

### 6.4. Event retention và broker đều là bản sao

Kafka topic, retry topic, DLQ và compacted topic là các nơi lưu dữ liệu. Một message nhạy cảm có thể tồn tại ở:
- Producer log/transactional outbox.
- Broker partition và replica của broker.
- Consumer retry storage.
- Dead-letter queue.
- Schema debugging/error logs.
- Sink connector và downstream warehouse.
- Backup/snapshot của broker hoặc consumer state.

Khi quyết định truyền một trường qua event, phải tính tất cả những nơi trên. Đặt retention của topic và DLQ phù hợp, kiểm soát ACL, mã hóa/transport, payload filtering và quyền truy cập console/debug tools.

**DLQ không phải thùng rác an toàn.** Message trong DLQ có thể được giữ lâu hơn luồng chính và thường được operator mở để kiểm tra, nên càng cần giảm trường nhạy cảm và kiểm soát redrive.

## 7. Quy tắc bảo vệ theo phân loại

Một ma trận mẫu cho kiểm soát tối thiểu:

| Kiểm soát | PUBLIC | INTERNAL | CONFIDENTIAL | RESTRICTED |
|---|---|---|---|---|
| Phân quyền đọc | Theo chính sách công bố | Nhân sự/service được cấp quyền | Need-to-know, scope giới hạn | Tối thiểu, phê duyệt/điều kiện bổ sung |
| Mã hóa khi truyền | HTTPS/TLS theo chuẩn dịch vụ | Bắt buộc trong hệ thống theo policy | TLS và xác minh bên nhận | TLS/mTLS hoặc cơ chế được phê duyệt |
| Mã hóa khi lưu | Theo hạ tầng | Khuyến nghị/chuẩn hạ tầng | Bắt buộc theo policy | Mã hóa và quản lý khóa chặt |
| Log payload | Có giới hạn nội dung | Chỉ dữ liệu an toàn | Redaction/không log giá trị gốc | Không log giá trị; audit metadata |
| Export | Qua quy trình xuất bản | Có quyền nghiệp vụ | Kiểm soát và audit | Hạn chế mạnh, phê duyệt nếu cần |
| Non-production | Dữ liệu công khai phù hợp | Theo chính sách | Synthetic/masked có kiểm soát | Tránh copy thực; ngoại lệ có quản trị |
| Retention | Theo mục đích | Theo policy | Bounded, xóa có kiểm chứng | Tối thiểu cần thiết và có kiểm soát |
| Sao chép sang service mới | Theo hợp đồng dữ liệu | Review owner khi cần | Owner/purpose approval | Kiểm soát đặc biệt hoặc không cho phép |

Đây là ma trận tham khảo. Cần gắn với pháp luật, hợp đồng, chính sách nội bộ và dữ liệu cụ thể trước khi áp dụng. Tăng mức phân loại không có nghĩa “bật TLS là đủ”; còn access, purpose, minimization, audit và deletion.

### 7.1. Dùng nguyên tắc default-deny cho luồng nhạy cảm

Thay vì cho mọi consumer subscribe một topic chứa profile rồi tự hứa không sử dụng, đặt ACL theo producer/consumer, giới hạn event schema và dùng API truy cập theo mục đích. Quyền đọc một topic có payload chứa mọi trường có nghĩa người nhận **có khả năng biết tất cả các trường đó**.

Một service cần tên người hiển thị không nhất thiết được quyền thấy reset token hoặc địa chỉ. Việc tách event theo domain/use case có thể giảm nhu cầu “event khổng lồ” và quyền quá rộng.

## 8. Bảo vệ dữ liệu ở mức field và record

### 8.1. RBAC và ABAC

**RBAC:** quyền dựa trên vai trò như support-agent, fulfillment-worker, billing-service. Dễ quản lý ở mức chức năng nhưng có thể quá rộng nếu role được dùng cho nhiều loại bản ghi.

**ABAC:** quyền dựa trên thuộc tính như tenant, owner, purpose, region, mức dữ liệu, thời gian và trạng thái request. Ví dụ support agent chỉ xem trường liên hệ khi đang xử lý ticket đã được phân công.

Một quyết định truy cập có thể dựa trên:

~~~text
allow =
  caller authenticated
  AND caller role/scope permits this action
  AND requested record belongs to authorized tenant
  AND requested fields allowed for purpose
  AND policy permits requested environment/region
  AND additional approval/step-up satisfied if required
~~~

Không lấy “có role SUPPORT” làm quyền đọc toàn bộ bảng khách hàng nếu mục đích chỉ là xác minh một đơn.

### 8.2. Column-level, row-level và application authorization

- Field/column filtering: API chỉ trả cột được phép.
- Row-level/tenant predicate: query phải ràng buộc tài nguyên theo tenant/owner đã xác minh.
- API authorization: kiểm người gọi, action và object; không chỉ JWT signature.
- Database grants/row-level security: có thể bổ sung lớp bảo vệ khi dùng đúng engine và policy.
- Service-to-service identity: mỗi workload có danh tính riêng, tránh một shared superuser cho mọi service.

Khi trả JSON, không serialize toàn entity ORM rồi hy vọng client tự ẩn trường. Dùng response DTO/projection rõ, test trường cấm không xuất hiện.

### 8.3. Ví dụ DTO tối thiểu trong Java

~~~java
public record CustomerInternal(
        String customerId,
        String displayName,
        String email,
        String phone,
        String deliveryAddress,
        String passwordHash
) {}

public record OrderCustomerSummary(
        String customerRef,
        String displayName
) {}

public final class CustomerProjectionMapper {
    public OrderCustomerSummary toOrderSummary(
            CustomerInternal source
    ) {
        return new OrderCustomerSummary(
                source.customerId(),
                source.displayName()
        );
    }
}
~~~

Đây là mẫu mapping minh họa. Sự tồn tại của DTO không thay thế authorization, không chứng minh mọi trường đều được phép sao chép và không bảo đảm record gốc là mô hình phù hợp. Khi mục đích chỉ cần customerRef, thậm chí displayName cũng nên bỏ.

## 9. Secrets và credential: nhóm dữ liệu phải kiểm soát riêng

Một password, private key, API key, access token hoặc refresh token không chỉ là “thông tin cá nhân”; người có nó có thể giành quyền truy cập.

Chính sách thường cần:

- Không đưa credential vào event nghiệp vụ, analytics, error payload, log hoặc trace.
- Không commit secret vào repository, container image, frontend bundle hoặc file ví dụ.
- Giữ secret material tại secret manager/KMS/HSM hoặc nơi được quản trị tương đương.
- Truyền reference/identity thay vì secret gốc khi kiến trúc cho phép.
- Cấp quyền theo workload và môi trường; xoay và thu hồi có audit.
- Không dùng mật khẩu thật hoặc token production cho test.
- Không lưu password plaintext; dùng password hashing phù hợp cho credential đăng nhập.
- Không lưu access/refresh token dưới dạng raw data ở các nơi không cần; áp dụng verifier/hash hay secure store theo loại token và mục đích.

Nếu một service cần gọi API thay mặt người dùng, thiết kế delegation/token exchange hoặc workload identity phù hợp, không phát toàn bộ refresh token của người dùng sang các microservice.

### 9.1. Không nhầm mã hóa với hạn chế sao chép

Mã hóa khi lưu giảm rủi ro truy cập trực tiếp thiết bị/dữ liệu ở tầng thấp, nhưng một service được quyền giải mã và export vẫn có thể làm lộ dữ liệu. **Encryption không giảm số bản sao hay số người có quyền**, nên vẫn cần minimization và authorization.

## 10. Log, trace, metric và error report là nơi rò rỉ phổ biến

Một request có thể bị ghi lại qua:
- HTTP access log với query string.
- Application log “request body” và exception stack.
- Debug log của HTTP client.
- Distributed trace attributes/baggage.
- APM, analytics, crash reporting.
- Reverse proxy, WAF hoặc service mesh.
- Support ticket gắn payload để điều tra.

### 10.1. Thiết kế log an toàn từ đầu

Ví dụ không nên:

~~~text
ERROR Payment request failed:
  customerEmail=person@example.invalid
  cardNumber=<sensitive>
  authorization=Bearer <token>
  deliveryAddress=<full address>
~~~

Log đủ để điều tra:

~~~json
{
  "event": "payment_request_failed",
  "service": "checkout",
  "requestId": "req-123",
  "orderId": "ord-456",
  "dependency": "payment",
  "failureClass": "TIMEOUT",
  "retryable": true,
  "elapsedMs": 850
}
~~~

Ngay cả orderId có thể được xem là identifier nhạy cảm tùy khả năng tra cứu/liên kết; hạn chế quyền xem log, retention và correlation access. Với một số hệ thống, dùng ID nội bộ đã biến đổi hoặc tách tra cứu có quyền.

**Tránh đặt dữ liệu nhạy cảm trong URL query string**, vì proxy, browser history, referrer và logs thường lưu URL. Dùng header/body theo giao thức thích hợp vẫn phải redact ở lớp observability.

### 10.2. Redaction và allowlist tốt hơn blocklist thuần túy

Blocklist các tên trường như password, token, ssn có thể bỏ sót tên mới như authProof hoặc externalCredential. Một chiến lược mạnh hơn:
- Structured logging theo **allowlist field** được phép.
- Tự động phân loại/mask field đã biết.
- DLP scanning trên pipeline log/telemetry theo policy.
- Không log raw request/response body ở production cho các endpoint nhạy cảm.
- Phát hiện secret/personal data leak trong kiểm thử và quan sát.
- Giới hạn quyền truy cập công cụ debug.

DLP là lớp phát hiện, không thay thế thiết kế tối thiểu dữ liệu. Regex không phát hiện mọi định danh, và dữ liệu được mã hóa/encoded có thể vượt khỏi bộ lọc.

### 10.3. Metric không nên chứa nhãn cardinality cao

Không đưa email, customerId, full URL, token, số điện thoại hoặc địa chỉ vào metric label. Ngoài rủi ro riêng tư, số time series sẽ bùng nổ. Dùng nhãn có tập hữu hạn như environment, service, data_classification, access_result hoặc error_class.

## 11. Cache, search index và bản sao tạm

**Cache cũng là một bản sao dữ liệu.** Một entry có TTL một giờ vẫn có thể bị sao chép qua replication, backup của cache, dump, snapshot, request debug hoặc memory crash dump.

### 11.1. Cache key và payload

- Không chứa raw secret hoặc PII dễ đọc trong key nếu có thể tránh.
- Cache key phải chứa tenant, locale, authorization scope hoặc version khi chúng quyết định dữ liệu.
- Cache response DTO đã lọc, không cache nguyên internal entity.
- Xác định TTL/hard retention theo classification và business freshness.
- Kiểm soát cache operator, replication, snapshot và telemetry.
- Có invalidation cho thay đổi/xóa, không chỉ chờ TTL nếu policy đòi thu hồi nhanh.

Ví dụ một cache key customer:42 không phù hợp nếu cùng entry chứa cả profile riêng, email, địa chỉ, quyền và trạng thái cá nhân. Cân nhắc tách view theo nhu cầu.

### 11.2. Search index

Search index thường nhân bản dữ liệu đã tokenized và có thể khiến nội dung dễ tìm kiếm hơn DB gốc. Khi index chứa email, địa chỉ hoặc ghi chú tự do, phải kiểm:
- Ai có quyền query index và fields?
- Index có phân vùng theo tenant không?
- Trường nào cần searchable, trường nào không?
- Index có lưu raw source, snippets và metadata nhạy cảm không?
- Khi xóa ở DB, index được xóa trong thời hạn nào?
- Các snapshot và replica của index được quản lý ra sao?

Một tìm kiếm full-text trên dữ liệu nhạy cảm có thể tạo năng lực khám phá ngoài mục đích ban đầu. Đừng tự đưa mọi field vào indexing để “dễ tìm sau này”.

### 11.3. Scratch files và bộ nhớ tạm

CSV tạm, file export, notebook output và temporary object store có thể tồn tại lâu hơn request nếu cleanup thất bại. Dùng storage có TTL/lifecycle policy, quyền tối thiểu và giới hạn đường dẫn xuất. Xóa file tạm bằng application code chưa đủ nếu có backup, snapshot hoặc replica.

## 12. Không đưa dữ liệu production thô vào môi trường test

Dữ liệu thực giúp tái tạo bug nhưng cũng tạo bản sao mới ở môi trường thường có quyền rộng hơn, nhiều công cụ debug và máy lập trình cá nhân.

### 12.1. Thứ tự lựa chọn dữ liệu test

1. **Synthetic data:** sinh dữ liệu giả theo ràng buộc schema/nghiệp vụ, không có cá nhân thật.
2. **Curated fixtures:** bộ tình huống đã chọn và được phép.
3. **Transformed dataset:** dữ liệu được thay đổi theo chính sách, bảo toàn tính chất cần test.
4. **Controlled exception:** chỉ khi có lý do rõ, phê duyệt và kiểm soát môi trường/tài khoản/time-to-live.

Đừng nhầm masking đơn giản với anonymization. Ví dụ giữ ngày sinh chính xác, mã bưu chính chi tiết và lịch sử giao dịch có thể tái nhận diện dù đã thay tên.

### 12.2. Test transformation có những nguy cơ gì?

- Deterministic pseudonymization giúp liên kết bảng nhưng vẫn có bảng ánh xạ và nguy cơ liên kết ngược.
- Hash email không salt/key có thể bị brute-force theo danh sách email phổ biến.
- Xáo trộn tên nhưng giữ địa chỉ/vị trí/số điện thoại làm rò dữ liệu thật.
- Giữ outlier hiếm gặp làm dễ nhận diện.
- Không bảo toàn foreign keys khiến test sai và người phát triển quay lại dùng dữ liệu thật.
- Dữ liệu transformed được xuất rồi không có retention/deletion plan.

Biến đổi tốt cần threat model, mục đích test, khả năng tái nhận diện và kiểm thử chính xác. Khi không thể bảo đảm phù hợp, ưu tiên synthetic data.

### 12.3. Kiểm soát developer access

Chỉ những người thực sự cần mới được truy cập dữ liệu nhạy cảm. Export nên có logging/approval trong trường hợp rủi ro cao, giới hạn số bản ghi/trường, thời hạn và nơi lưu. Không gửi database dump qua email/chats hoặc đưa lên máy cá nhân không được quản trị.

## 13. Analytics, BI và machine learning

Một pipeline analytics có thể tự nhân bản dữ liệu qua nhiều lớp:

~~~text
OLTP DB
   |
   v
CDC / ETL
   |
   v
Raw landing zone
   |
   v
Curated tables
   |
   +-- BI reports
   +-- Feature store
   +-- ML training data
   +-- Notebook exports
   +-- External sharing
~~~

Mỗi lớp là một nơi cần phân loại, access, retention và deletion. Đừng coi data lake là “đích nội bộ an toàn” để đổ toàn bộ dữ liệu thô.

### 13.1. Giảm nhận diện theo yêu cầu phân tích

Ví dụ báo cáo “tổng số đơn theo vùng” có thể chỉ cần:
- Khu vực đã tổng hợp ở mức thích hợp.
- Mã ngày hoặc tuần.
- Tổng số giao dịch.
- Tổng doanh thu/giá trị theo chính sách.

Không nhất thiết phải giữ tên, email, số điện thoại và địa chỉ chi tiết. Aggregation giúp giảm rủi ro, nhưng **nhóm rất nhỏ hoặc outlier có thể vẫn dẫn tới tái nhận diện**; xem ngưỡng nhóm và khả năng kết hợp nguồn khác.

### 13.2. Dữ liệu ML không tự được miễn trừ

Training dataset, feature store, embedding/vector database, artifact đánh giá, prompt/response logs và model outputs có thể chứa hoặc suy ra dữ liệu nhạy cảm. Cần cùng một contract về mục đích, nguồn, consent/authorization khi áp dụng, retention, access, deletion và chuyển giao bên thứ ba.

Không tự khẳng định “embedding không chứa PII vì không đọc ra trực tiếp”. Khả năng rò thông tin phụ thuộc mô hình, dữ liệu và cách truy xuất; phải đánh giá trong threat model.

### 13.3. Dữ liệu tổng hợp cũng có mức nhạy cảm

Một báo cáo doanh thu chưa công bố có thể không chứa PII nhưng vẫn là bí mật kinh doanh. Phân loại dataset sau biến đổi dựa vào nội dung và rủi ro thực tế; không tự hạ xuống PUBLIC chỉ vì đã xóa tên người.

## 14. Sao lưu, replication và disaster recovery

Backup được tạo để bảo vệ khả năng khôi phục, nên không thể coi mọi bản sao là sai. Nhưng backup nhạy cảm vẫn cần governance:

- Danh sách loại backup, tần suất, vị trí, key mã hóa.
- Quyền đọc/khôi phục và audit của người dùng/automation.
- Retention chính xác và cơ chế tự động xóa khi hết hạn.
- Chính sách bảo vệ backup bất biến chống ransomware.
- Data residency, hợp đồng và quyền truy cập bên vận hành.
- Kiểm thử restore mà không tạo bản sao trôi nổi.
- Kế hoạch xử lý dữ liệu đã bị xóa/thu hồi khi phải restore snapshot cũ.

### 14.1. Backup là trường hợp đặc biệt của deletion

Nếu một hồ sơ được xóa khỏi DB chính hôm nay nhưng còn trong backup tuần trước, không thể nói “mọi bản sao đã biến mất ngay” trừ khi có cơ chế thực sự đáp ứng điều đó.

Một thiết kế có thể quy định:
- Dữ liệu hoạt động bị xóa/vô hiệu hóa trong thời hạn đã xác định.
- Backup được giữ trong một thời hạn phục hồi đã được duyệt và không dùng cho mục đích vận hành thường xuyên.
- Quyền truy cập backup hạn chế, mã hóa và audit.
- Khi restore, có bước **replay deletion tombstones / suppression list** trước khi dữ liệu được phục vụ trở lại.
- Backup hết retention được xóa theo khả năng và chính sách lưu trữ.
- Những yêu cầu pháp lý/hợp đồng khác được xử lý bởi chính sách cụ thể, không tự đoán.

### 14.2. Immutable backup và legal hold

Backup bất biến hoặc legal hold có thể hạn chế xóa ngay. Đây là lý do càng cần mô tả trung thực khả năng xóa ở từng storage tier, thay vì hứa “delete from everywhere instantly” mà hệ thống không thực hiện được.

Khi có legal hold, hệ thống phải ghi nhận đúng cơ sở/chủ thể có quyền và kiểm soát truy cập; không dùng legal hold như cái cớ giữ dữ liệu vô hạn ngoài chính sách.

## 15. Truy vết lineage và inventory các bản sao

Một **data inventory** hữu dụng không chỉ là danh sách bảng. Nó mô tả dữ liệu nào đi qua tuyến nào, ai nhận, với hợp đồng gì.

### 15.1. Schema metadata tối thiểu

| Thuộc tính | Ý nghĩa |
|---|---|
| asset_id | Định danh tài sản dữ liệu |
| owner_team | Nhóm sở hữu và người chịu trách nhiệm |
| source_of_truth | Hệ thống nguồn |
| classification | Mức nhạy cảm và loại dữ liệu |
| data_subject_reference | Cách truy vết tới chủ thể nếu áp dụng |
| business_purpose | Mục đích được phép |
| allowed_consumers | Người nhận/dịch vụ được phê duyệt |
| allowed_regions | Ràng buộc địa lý nếu có |
| storage_locations | DB, cache, index, bucket, queue, backup |
| retention_policy | Thời hạn/lifecycle và xử lý ngoại lệ |
| export_policy | Hạn chế xuất, chia sẻ, download |
| deletion_contract | Cách yêu cầu và xác minh xóa |
| data_lineage | Upstream, transformation, downstream |
| schema_version | Phiên bản hợp đồng dữ liệu |
| review_date | Mốc đánh giá lại và owner liên hệ |

Một ví dụ lineage:

~~~text
customer.contact_email [CONFIDENTIAL]
  ├─ Customer DB: source
  ├─ Notification Service: transient send use
  ├─ Email delivery provider: contracted recipient
  ├─ Support Tool: restricted view
  └─ Backups: encrypted, bounded retention
Not allowed by default:
  ├─ Generic OrderCreated event
  ├─ Open search index
  ├─ Analytics raw export
  └─ Application/HTTP debug logs
~~~

Các mũi tên lineage phải được kiểm tra với thực tế triển khai. Một dataset có thể phát sinh thêm sink khi engineer cấu hình CDC mới, dashboard mới hoặc connector SaaS mới.

### 15.2. Cách phát hiện bản sao ngoài dự kiến

- Schema registry và event-contract review.
- Data catalog/lineage từ ETL, CDC, orchestration.
- Cloud inventory: database, bucket, storage snapshot, index, cache.
- DLP scanning và secret scanning trên nội dung theo quyền.
- Audit logs cho export, share, query và restore.
- CI checks khi thêm payload field vào event/DTO.
- Kiểm tra các đầu ra observability và error tracking.
- Review định kỳ các tích hợp bên thứ ba.
- Inventory file export tạm, data science workspace và retention job.

Không thể giả định công cụ scanning sẽ tìm đủ mọi bản sao. Thực hành quan trọng là **mỗi đường phát tán mới phải đăng ký với governance trước khi hoạt động**, thay vì chờ quét sau sự cố.

## 16. Giới hạn sao chép bằng data contract và policy-as-code

Một hợp đồng data sharing nên mô tả rõ:

~~~yaml
contractId: order-customer-summary-v2
source: customer-service
consumer: order-service
purpose: DISPLAY_ORDER_OWNER
classification: CONFIDENTIAL
fields:
  - customerRef
  - displayName
storage:
  durableCopyAllowed: true
  destination: order-read-model
  retentionPolicyRef: order-retention-policy
transport:
  authenticatedTlsRequired: true
  consumerIdentityRequired: true
audit:
  enabled: true
  includeRawPayload: false
changeReview:
  ownerApprovalRequired: true
~~~

Đây là ví dụ hợp đồng khai báo, không tự có hiệu lực nếu hệ thống không có validator/enforcement tương ứng. Nó giúp review rằng Order Service chỉ nhận customerRef và displayName, không nhận email/phone vì “lỡ có trong event”.

### 16.1. Enforcement tại các ranh giới

- **Source API:** response field allowlist và policy theo consumer/purpose.
- **Schema registry / producer:** reject event chứa field ngoài contract cho consumer/topic.
- **Gateway:** xác thực caller và giới hạn route/scope, không gửi dữ liệu nhạy cảm vào log.
- **Message broker:** topic ACL, retention, mã hóa và consumer identity.
- **ETL/CDC:** column allowlist và destination classification.
- **Data warehouse:** schema/tag, role grants, row/column policy.
- **Export endpoint:** phê duyệt, hạn chế số record, ký nhận và audit.
- **CI/CD:** kiểm tra thay đổi schema, config, quyền và nơi lưu.
- **Storage:** IAM, encryption keys, retention/lifecycle.

Policy-as-code có thể hỗ trợ kiểm tra cấu hình như “RESTRICTED fields không được phát lên topic được nhiều team subscribe” hoặc “chỉ approved sinks nhận customer.email”. Nhưng nếu thư viện serialize một object khác với schema khai báo, chính sách chỉ trên giấy không đủ; cần kiểm thử payload thực và kiểm soát nơi phát.

### 16.2. Pseudocode quyết định cho phép bản sao

~~~text
function mayCopy(asset, source, destination, caller, purpose):
    require caller is authenticated and authorized
    require asset.classification is known
    require purpose is approved for asset
    require destination is an approved consumer and storage location
    require destination.region meets residency policy
    require requested fields are a subset of permitted fields
    require encryption, audit and retention controls are configured
    require deletion/reconciliation contract is registered
    return ALLOW; otherwise DENY with audit metadata
~~~

Đây là rule logic, không phải chương trình hoàn chỉnh. Cần tránh quyền “đọc asset” tự động bao gồm quyền “export toàn bộ asset” hoặc “sao chép vào hệ thống mới”.

## 17. Thiết kế deletion và correction xuyên microservices

Một quyền sửa/xóa dữ liệu hoặc một chính sách retention có thể đòi thay đổi nhiều nơi.

~~~text
Deletion / correction request
        |
        v
Identity and policy validation
        |
        v
Data governance workflow
        |
        +--> Source DB action
        +--> Projection update/delete
        +--> Search index remove/update
        +--> Cache invalidate
        +--> Analytics/warehouse action
        +--> External processor request
        +--> Backup retention / restore suppression policy
        |
        v
Track acknowledgments, failures and verification
~~~

Một lệnh DELETE trên bảng chính **không đồng nghĩa đã xóa các read model, caches, DLQ, data exports và backups**.

### 17.1. Dùng identity và version để truy vết

Một deletion event có thể mang reference/opaque ID và version của record, tránh mang toàn bộ PII:

~~~json
{
  "eventId": "evt-delete-123",
  "eventType": "CustomerDataDeletionRequired",
  "customerRef": "opaque-customer-ref",
  "recordVersion": 38,
  "policyActionId": "action-456",
  "issuedAt": "2026-11-12T03:00:00Z"
}
~~~

Consumer dùng reference để tìm và xóa dữ liệu được phép quản lý. Nếu event đến lặp, thao tác phải idempotent; nếu event đến trễ so với update, version/policy phải ngăn dữ liệu đã xóa bị tái tạo từ event cũ.

### 17.2. Tombstone và suppression

Một record bị xóa có thể quay lại khi:
- CDC replay từ log cũ.
- Rebuild projection từ sự kiện lịch sử.
- Restore backup cũ.
- Retry queue phát một event cũ chứa profile.
- Consumer bị offline dài ngày rồi hoạt động trở lại.

**Tombstone/deletion marker** hoặc suppression state giúp pipeline nhận biết không được tái tạo dữ liệu đã xóa. Marker cũng cần metadata/retention và có thể liên quan dữ liệu cá nhân; không giữ một bảng định danh vĩnh viễn vô điều kiện.

### 17.3. Độ trễ xóa có thể đo được

Cần định nghĩa mục tiêu:
- Source delete/correction latency.
- Cache invalidation delay.
- Projection/index deletion propagation lag.
- Downstream acknowledgment age.
- Số deletion requests còn pending.
- Số bản sao không tìm thấy owner hoặc không báo kết quả.
- Chính sách với backup/immutable storage.

Không tự tuyên bố “đã xóa toàn hệ thống” chỉ vì một event đã được publish. Cần bằng chứng từng nơi nhận và trạng thái ngoại lệ.

### 17.4. Trường hợp không được hoặc chưa thể xóa

Một số dữ liệu có thể có nghĩa vụ lưu giữ theo luật, hợp đồng, điều tra hoặc tính đúng đắn tài chính. Cách xử lý phải dựa trên chính sách đã xác định: hạn chế truy cập, tách mục đích, đặt hold, giữ metadata tối thiểu hoặc xóa những bản sao không cần thiết. Không tự suy diễn “mọi yêu cầu xóa đều phải xóa ngay” hoặc “dữ liệu tài chính luôn được giữ mãi”.

## 18. Chia sẻ dữ liệu với bên thứ ba và giới hạn địa lý

Khi dữ liệu rời khỏi phạm vi do tổ chức trực tiếp vận hành, cần kiểm tra:

1. Bên nhận có thực sự cần dữ liệu đó?
2. Phạm vi trường và mục đích xử lý là gì?
3. Có thỏa thuận và cơ sở xử lý theo chính sách/quy định liên quan không?
4. Bên nhận lưu ở vùng/quốc gia nào, có subprocessor nào?
5. Có thể audit, giới hạn quyền và thu hồi/xóa không?
6. Retention, backup, breach notification và incident response được quy định thế nào?
7. Cơ chế mã hóa, authentication, network và access logging có phù hợp?
8. Có export trong response của dịch vụ bên thứ ba hoặc log support của họ không?
9. Khi vendor đổi hạ tầng hoặc hợp đồng, có cần review lại không?

Không mặc định một SaaS “có chứng nhận” là được phép nhận tất cả dữ liệu. Chứng nhận có thể hữu ích nhưng không thay thế yêu cầu đúng mục đích, data minimization, hợp đồng và kiểm chứng kiểm soát thực tế.

### 18.1. Data residency không chỉ là region của DB chính

Nếu primary DB đặt ở một region nhưng backup, analytics export, logs hoặc error reporting được lưu ở region khác, đường lưu dữ liệu vẫn có thể vượt ranh giới cư trú mong muốn. Cần inventory **mọi nơi lưu bền vững và mọi processor**, không chỉ kết nối database chính.

## 19. Mẫu workflow phê duyệt một bản sao mới

Giả sử team Analytics muốn lấy customer email để đo hiệu quả chiến dịch.

### Bước 1: Mô tả quyết định cần ra

Analytics muốn biết tỷ lệ người mua lại theo cohort. Câu hỏi: có thật sự cần email thô không? Có thể dùng customerRef được pseudonymize, cohort tag hoặc aggregate thay thế không?

### Bước 2: Xác định data asset và classification

Email là trường nhạy cảm; có thể liên kết cá nhân và có rủi ro khi export. Kiểm tra owner, allowed purpose, chính sách liên quan và nguồn dữ liệu.

### Bước 3: Đề xuất phương án ít sao chép nhất

Ưu tiên một sự kiện/tập dữ liệu chỉ chứa:
- Pseudonymous customer reference theo phạm vi phân tích.
- Cohort và số lần mua.
- Thời điểm ở mức độ chi tiết cần thiết.

Nếu vẫn cần email cho một mục đích cụ thể, phải giải thích rõ và có kiểm soát riêng; không đưa email mặc định vào raw lake.

### Bước 4: Thẩm định nơi nhận

Kiểm tra quyền truy cập, encryption, export, retention, region, backup, notebook, dashboards và bên thứ ba. Ai có thể xem raw row? Ai được download CSV?

### Bước 5: Cập nhật contract và lineage

Ghi schema, allowed fields, source, sink, mục đích, owner, thời hạn, quy trình deletion, review. Thiết lập policy-as-code hoặc CI test nơi khả thi.

### Bước 6: Triển khai có kiểm chứng

Dùng allowlist transform và schema validation, không SELECT * rồi bỏ field trên UI. Kiểm tra event/payload thực tế, logs, permissions và data destination. Không tạo một data dump tạm ngoài quy trình chỉ để debug.

### Bước 7: Giám sát và đánh giá lại

Theo dõi số record, số nơi lưu, quyền export, retention job, deletion acknowledgment, drift schema, DLP findings và sự thay đổi mục đích.

## 20. Ví dụ SQL: projection tối thiểu thay vì sao chép toàn bộ

Giả sử source có bảng customers:

~~~sql
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    delivery_address TEXT,
    account_status TEXT NOT NULL,
    password_hash TEXT NOT NULL
);
~~~

Order Service chỉ cần customer ID và trạng thái tài khoản để xác thực một quy tắc nghiệp vụ. Thay vì replicate mọi cột, một projection được cho phép có thể chứa:

~~~sql
CREATE TABLE order_customer_reference (
    customer_id UUID PRIMARY KEY,
    account_status TEXT NOT NULL,
    source_version BIGINT NOT NULL
);
~~~

Consumer áp dụng event đã được phép:

~~~sql
UPDATE order_customer_reference
SET account_status = :newStatus,
    source_version = :eventVersion
WHERE customer_id = :customerId
  AND source_version < :eventVersion;
~~~

Đây là ví dụ logic update theo version, chưa gồm insert/transaction/duplicate handling hoặc deletion. Thực tế phải dùng upsert phù hợp DB, xử lý out-of-order, thông điệp lặp và quyền truy cập, đồng thời đảm bảo account_status thực sự được phép replicate. Không tự sao chép password_hash/email chỉ vì source có các cột đó.

### 20.1. Query không dùng SELECT * mặc định

Nếu một API chỉ cần ba trường để trả UI, hãy chọn rõ ba trường. SELECT * làm contract phụ thuộc schema và có thể vô tình đưa cột nhạy cảm mới vào các đường serialize/log. Dùng DTO hoặc mapping rõ với test kiểm tra không lộ trường cấm.

### 20.2. Ranh giới transaction và sao chép

Khi nguồn ghi transaction và phát event cập nhật, transactional outbox giúp tránh trường hợp DB commit nhưng event phát thất bại không được phục hồi. Tuy nhiên outbox cũng là một bản sao event payload; hãy giữ payload tối thiểu và retention phù hợp. Exactly-once delivery không nên được giả định; downstream projection cần idempotent.

## 21. Trường hợp người dùng tải xuống hoặc xuất báo cáo

Export là hành động **tạo một bản sao dễ di chuyển** nên cần kiểm soát hơn truy cập qua màn hình, nhất là với dữ liệu cá nhân/giới hạn.

Một export endpoint nên xác định:
- Caller được quyền export **những trường nào** trên **những bản ghi nào**?
- Mục đích và số lượng record tối đa.
- Format CSV/JSON/Parquet và chống rò dữ liệu qua tên file/URL.
- Job có cần xét duyệt hoặc xác thực lại không?
- Đường dẫn tải có hết hạn, được xác thực và hạn chế reuse không?
- Object store tạm có TTL/lifecycle và encryption không?
- Export có bị gửi sang email/chat/CDN/public bucket không?
- Hành động được audit bằng metadata gì, không lưu raw file vào log?
- Khi hết hạn hoặc yêu cầu xóa, file export có thể được tìm và xóa không?

Với CSV, cân nhắc nguy cơ formula injection khi dữ liệu do người dùng nhập được mở bằng spreadsheet application; xử lý output encoding/escaping theo định dạng và sản phẩm nhận. Đây là một vấn đề an toàn riêng ngoài bảo mật lưu trữ.

## 22. Các lỗi quản trị thường gặp

| Sai lầm | Tác hại | Biện pháp |
|---|---|---|
| Copy nguyên object vào mọi event | Mọi consumer nhận thêm PII ngoài nhu cầu | Event DTO tối thiểu, schema contract |
| Dùng dữ liệu production trong staging | Bề mặt tấn công tăng, không có cùng kiểm soát | Synthetic/transformed data |
| Bật debug log toàn request | Credential và dữ liệu cá nhân vào log | Allowlist logging, redaction |
| Dùng SELECT * trong ETL | Cột nhạy cảm mới tự đi vào data lake | Column allowlist, schema review |
| Lưu profile vào Redis không có giới hạn | Dữ liệu tồn tại/replicate lâu ngoài dự kiến | TTL, quyền, invalidation, no raw secret |
| Dùng global customer event | Consumer không có use case vẫn được thấy chi tiết | Topic/contract theo mục đích |
| Xóa nguồn mà không xử lý projection | Dữ liệu tiếp tục xuất hiện trên read API | Deletion workflow và ack |
| Bỏ qua DLQ và snapshot | Dữ liệu nhạy cảm giữ lâu và khó xóa | Inventory, retention, access |
| Coi hash là ẩn danh | Có thể tái liên kết hoặc đoán danh tính | Threat model, pseudonymization controls |
| Coi encryption thay minimization | Service được cấp khóa vẫn đọc/export được | Purpose, access, copy limits |
| Coi backup không phải bản sao | Restore tái tạo dữ liệu đã xóa | Restore suppression, retention |
| Coi BI dashboard luôn là dữ liệu công khai | Lộ kinh doanh/nhóm nhỏ | Reclassification after aggregation |
| Không gắn owner cho dataset | Không ai xử lý retention/deletion | Data catalog ownership |
| Không theo dõi export tạm | CSV tồn tại trên object storage lâu | TTL, audit, cleanup |
| Một service account dùng chung | Không cô lập quyền theo consumer | Workload identity, least privilege |
| Metric label chứa customerId/email | Rò dữ liệu và nổ cardinality | Hữu hạn label, log bảo vệ |

## 23. Sự cố: phát hiện PII trong log hoặc event

Giả sử phát hiện application log của Order Service chứa email, địa chỉ và access token vì một exception logger in toàn bộ HTTP request.

Một runbook có thể gồm:

1. **Xác định phạm vi:** service, environment, thời gian, số lượng record, loại dữ liệu, log sinks, retention và ai có quyền xem.
2. **Ngăn phát tán tiếp:** tắt raw payload logging, bổ sung allowlist/redaction, chặn export hoặc truy cập rủi ro theo quy trình.
3. **Đánh giá credential compromise:** nếu access token/API key lộ, thu hồi/xoay theo phạm vi và theo dõi truy cập trái phép.
4. **Kiểm tra bản sao downstream:** log aggregation, APM, backup, support ticket, dashboard, error reports, exports.
5. **Đánh giá nghĩa vụ xử lý sự cố:** nhóm bảo mật/privacy/compliance xác định thủ tục, thông báo và lưu chứng cứ theo quy định áp dụng.
6. **Xử lý dữ liệu đã lộ:** giới hạn quyền, xóa/purge theo khả năng và chính sách, xem xét immutable retention/legal hold.
7. **Kiểm chứng fix:** tái tạo lỗi bằng synthetic data, đảm bảo payload nhạy cảm không còn xuất hiện trong telemetry.
8. **Ngăn tái diễn:** kiểm thử logging contract, schema review, DLP monitoring, training và change control.

Không tự log lại dữ liệu đã lộ trong ticket điều tra. Báo cáo incident dùng số lượng, loại dữ liệu, ID tham chiếu và metadata an toàn, không copy nội dung nhạy cảm sang thêm một hệ thống.

## 24. Đo lường hiệu quả giới hạn sao chép

Một bộ tín hiệu quản trị có thể gồm:

| Tín hiệu | Ý nghĩa |
|---|---|
| sensitive_assets_with_owner_ratio | Bao nhiêu asset nhạy cảm có owner rõ |
| approved_copy_destinations | Số nơi lưu đã duyệt theo asset |
| unapproved_destination_findings | Bản sao ngoài danh sách cho phép |
| raw_sensitive_fields_in_events | Cột nhạy cảm xuất hiện trong event schema |
| data_export_count_by_class | Xu hướng export theo mức phân loại |
| access_denied_by_policy | Nỗ lực truy cập không đáp ứng policy |
| retention_overdue_assets | Dataset/bản sao đã quá retention |
| deletion_requests_pending | Yêu cầu xóa chưa hoàn tất |
| deletion_propagation_age | Độ trễ cập nhật/xóa ở downstream |
| backup_restore_policy_exceptions | Ngoại lệ khi restore/tái tạo bản đã xóa |
| telemetry_sensitive_data_findings | Log/trace chứa dữ liệu nhạy cảm |
| nonprod_production_data_findings | Dữ liệu production xuất hiện ở nơi không được phép |
| schema_contract_violation_count | Payload field không thuộc hợp đồng |
| third_party_dataset_review_overdue | Tích hợp chưa được review đúng hạn |

Không gắn subject ID, email, phone hay token vào metric label. Các bản ghi chi tiết phục vụ điều tra phải được phân quyền, có retention và audit.

### 24.1. Điều kiện hoàn tất không chỉ là “đã tạo policy”

Một chính sách sao chép tốt được thể hiện bằng:
- Consumer thực tế chỉ nhận các field được phép.
- Không có bản sao ẩn trong log/cache/test/analytics.
- Retention jobs và deletion workflow chạy được trong thực tế.
- Người dùng quyền thấp không thể truy vấn tài nguyên tenant khác.
- Incident có thể tìm phạm vi dữ liệu và owner nhanh chóng.
- Quyết định data sharing mới phải được review trước khi bật.
- Hệ thống có thể chứng minh bản sao đã được xóa/thu hồi hoặc ghi ngoại lệ rõ khi chưa thể.

## 25. Bài tập thiết kế: chia sẻ dữ liệu khách hàng trong hệ thống bán hàng

Một hệ thống có:
- Customer Service: customerId, email, phone, deliveryAddress, passwordHash, marketingPreference.
- Order Service: tạo đơn và hiển thị lịch sử.
- Fulfillment Service: in nhãn giao hàng.
- Notification Service: gửi email/SMS.
- Analytics Service: tổng hợp số đơn theo khu vực.
- Support Portal: xem đơn có phân quyền.
- Data Warehouse: thu nhận event từ Kafka.
- Redis, ElasticSearch, log aggregation, backup.

Hiện tại CustomerUpdated event gửi toàn bộ object Customer và mọi service đều subscribe. Trong staging, developer dùng bản dump DB production. Một số log ghi toàn request khi lỗi. Khi người dùng đổi email, thông báo vẫn gửi đến email cũ từ một read model.

### 25.1. Câu hỏi

1. Trường nào nên được phân loại CONFIDENTIAL/RESTRICTED? Có nhóm nào cần policy đặc biệt?
2. Service nào cần **lưu** email, phone, deliveryAddress, và service nào chỉ cần tham chiếu hoặc lệnh?
3. Vì sao passwordHash không nên nằm trong CustomerUpdated event?
4. Làm thế nào thay event “toàn bộ profile” bằng các contract tối thiểu mà vẫn không tạo coupling quá mức?
5. Khi CustomerUpdated đến trễ hoặc bị lặp, ngăn read model lùi version bằng gì?
6. Trong staging, nên dùng bộ dữ liệu nào để tái tạo lỗi?
7. Làm sao xử lý dữ liệu cũ trong Redis, search index, analytics và backup sau khi user sửa/xóa?
8. Làm sao biết bản sao đã lan đến những topic, DLQ, sinks và exports nào?
9. Các log đã chứa raw profile cần incident response thế nào?
10. Dấu hiệu nào chứng minh hệ thống giới hạn sao chép tốt hơn sau refactor?

### 25.2. Hướng giải

- Gắn owner, classification, purpose và retention cho các field.
- Notification có thể nhận lệnh gửi qua một service quản lý liên hệ, hạn chế việc mọi service tự lưu email.
- Fulfillment có thể cần địa chỉ giao trong thời gian xử lý đơn, nhưng không cần passwordHash/marketingPreference.
- Analytics có thể dùng customerRef được quản trị hoặc tổng hợp theo vùng, không cần email/phone.
- Order projection chỉ giữ customerRef và trường phục vụ màn hình đã được phép; dùng version để chống event cũ ghi đè.
- Tách contract event theo nhu cầu, dùng allowlist thay vì serialize entity đầy đủ.
- Test/staging dùng synthetic/transformed data được phê duyệt.
- Deletion/correction dùng workflow có ack, retry, idempotency, tombstone/version và runbook cho backup/restore.
- DLP/secret scanning và structured logging chặn payload nhạy cảm vào log.
- Đo số trường và nơi lưu được phê duyệt, schema violations, retention overdue, deletion lag, và incident findings.

## 26. Checklist triển khai vào hệ thống thực

1. **Inventory:** liệt kê dữ liệu và nơi lưu, bao gồm nguồn, replicas, cache, index, queue, DLQ, warehouse, log, backup, exports.
2. **Classification:** gắn nhãn đúng cho field/dataset, có owner và lý do.
3. **Purpose:** xác định mục đích được phép của từng consumer; không chấp nhận lý do “phòng khi cần”.
4. **Minimization:** giảm field từ lúc thu thập, xử lý, API response và event payload.
5. **Copy contract:** ghi nơi nhận, mục đích, trường, lưu bền vững hay tạm, retention, vùng, quyền, deletion.
6. **Default deny:** yêu cầu quyền để tạo luồng chia sẻ mới, export hoặc lưu bản sao nhạy cảm.
7. **Isolation:** phân quyền theo workload, tenant, region và loại dữ liệu.
8. **Encryption:** bảo vệ khi lưu và truyền, kiểm soát key, không coi encryption là đủ.
9. **Secret handling:** không gửi credential qua event/log/data warehouse; dùng secret manager/identity.
10. **DTO/schema:** field allowlist, không serialize entity nguyên bản hoặc SELECT * vô kiểm soát.
11. **Observability:** log allowlist, redaction, không dùng PII làm metric label.
12. **Non-production:** ưu tiên synthetic data; xử lý ngoại lệ theo quy trình.
13. **Analytics/ML:** giảm trường nhận diện, catalog mọi derived dataset và nơi export.
14. **Retention:** có TTL/lifecycle, owner, job thực thi và giám sát.
15. **Deletion/correction:** có idempotent events, tombstone/version, reconciliation và acknowledgments.
16. **Backups:** ghi retention, access và restore suppression cho dữ liệu đã xóa.
17. **Third parties:** đánh giá mục đích, data residency, hợp đồng, processors và cơ chế thu hồi.
18. **CI/CD:** review event schema, API DTO, data sinks, IAM, logs và policy-as-code.
19. **Detection:** DLP/data inventory/export audit phát hiện bản sao bất thường.
20. **Incident response:** có runbook khi dữ liệu hoặc secret bị lộ.
21. **Business correctness:** phân loại cũng bảo vệ tính toàn vẹn, không chỉ bí mật.
22. **Review định kỳ:** đánh giá lại khi nguồn, schema, mục đích, consumer hoặc luật/chính sách thay đổi.

## 27. Ghi nhớ cốt lõi

- **Dữ liệu nhạy cảm phải được phân loại theo rủi ro và mục đích**, không chỉ theo tên bảng hoặc liệu nó có chứa tên người hay không.
- **Một bản sao mới là một bề mặt tấn công và nghĩa vụ quản trị mới.** Giới hạn số nơi lưu, số trường được phát, người nhận, quyền export và thời gian tồn tại.
- **Microservices không cần sao chép toàn bộ object để tự chủ.** Sử dụng reference, API, projection tối thiểu hoặc event DTO theo use case.
- **Log, cache, search index, retry queue, DLQ, analytics, môi trường test và backups đều có thể chứa dữ liệu nhạy cảm.** Phải quản trị các nơi này như những bản sao thật.
- **Mã hóa và phân quyền là cần nhưng chưa đủ.** Data minimization, purpose limitation, retention, lineage, deletion và audit mới kiểm soát được vòng đời.
- **Dữ liệu giả danh không mặc nhiên là dữ liệu ẩn danh.** Cần đánh giá khả năng liên kết lại và rủi ro theo ngữ cảnh.
- **Xóa ở nguồn không tự xóa toàn hệ thống.** Thiết kế propagation, tombstone, reconciliation, acknowledgement và restore policy.
- **Chỉ tuyên bố quản trị tốt khi có bằng chứng vận hành:** bản sao được phê duyệt, policy được thực thi, data lineage có thể kiểm chứng và sự cố có thể được khoanh vùng/khắc phục.
