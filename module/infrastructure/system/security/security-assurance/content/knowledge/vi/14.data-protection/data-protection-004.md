# Data Flow trong Data Protection và Security Assurance

## 1. Vì sao bảo vệ dữ liệu phải bắt đầu từ luồng dữ liệu?

Một doanh nghiệp phát triển dịch vụ hóa đơn SaaS có thể bật mã hóa trên database chính, kiểm tra phân quyền ở API và kiểm soát quyền truy cập nhân viên. Nhưng dữ liệu khách hàng vẫn có thể đi qua **message broker, bộ nhớ đệm, file export, công cụ phân tích, log, backup và dịch vụ bên thứ ba**. Một biện pháp kiểm soát được thiết kế tốt tại database không tự động bảo vệ các bản sao ở những nơi khác.

Giả sử API chỉ cho phép user tenant A đọc hóa đơn thuộc A. Sau đó một worker xử lý yêu cầu export sử dụng service account đọc mọi tenant; message queue chứa tenant ID do client cung cấp; file CSV được đặt vào object storage có URL tải được chia sẻ rộng. Đội kiểm thử chỉ xác nhận API trả HTTP 403 với request sai tenant rồi kết luận **“đã cô lập dữ liệu khách hàng”**. Kết luận đó bỏ qua phần còn lại của **data flow**.

**Data flow (luồng dữ liệu)** là mô tả **dữ liệu nào phát sinh ở đâu, đi qua thành phần nào, chịu những phép xử lý nào, được ai truy cập hoặc nhận, tồn tại dưới những bản sao nào và đi tới đâu trong toàn bộ vòng đời**. Trong bảo vệ dữ liệu, data flow là cơ sở để xác định:

1. **Nguồn và đích:** ai tạo, ai nhận, hệ thống nào giữ bản gốc hoặc bản sao.
2. **Mục đích và phạm vi:** vì sao cần chuyển/biến đổi dữ liệu, trường nào thực sự cần.
3. **Ranh giới tin cậy:** dữ liệu đi qua những hệ thống, tenant, mạng, tài khoản, tổ chức hoặc khu vực nào.
4. **Rủi ro bảo mật:** nơi có thể lộ, bị thay đổi, mất, dùng sai mục đích hoặc truy cập trái phép.
5. **Security controls:** các biện pháp cần áp dụng ở nguồn, đường truyền, đích và các hoạt động quản trị.
6. **Assurance evidence:** phép kiểm tra nào chứng minh controls hoạt động đúng trên luồng thực tế, không chỉ tồn tại trên bản vẽ.

Trong module **SECURITY_SECURITY_ASSURANCE**, trọng tâm là **đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện. Vì thế bài **Data flow** không chỉ dạy cách vẽ sơ đồ; nó giải thích cách biến một **dòng dữ liệu cụ thể** thành các **security requirements, test cases, evidence và quyết định residual risk** có thể kiểm tra.

> **Nguyên tắc trọng tâm:** không thể khẳng định một loại dữ liệu đã được bảo vệ trên toàn hệ thống nếu chưa biết các đường di chuyển, những bản sao và các đường truy cập quan trọng của nó trong phạm vi đánh giá.

## 2. Data flow, DFD, data lineage và data inventory khác nhau thế nào?

| Khái niệm | Câu hỏi trả lời | Hiện vật điển hình | Giới hạn |
| --- | --- | --- | --- |
| **Data inventory / data catalog** | Có những tài sản dữ liệu nào, ai sở hữu, được phân loại ra sao? | Danh mục dataset, table, object, field, owner và nhãn. | Không tự thể hiện đầy đủ dữ liệu di chuyển qua hệ thống nào. |
| **Data flow** | Dữ liệu được tạo, truyền, xử lý, chia sẻ và hủy theo đường nào? | Sơ đồ, danh sách luồng có metadata và lifecycle. | Có thể thiếu chi tiết nếu chỉ vẽ đường mũi tên. |
| **Data Flow Diagram (DFD)** | Những entity, process, store và flow nào liên quan ở một mức trừu tượng? | DFD mức ngữ cảnh hoặc mức phân rã, kèm trust boundaries. | DFD không tự mô tả mọi field, thời hạn lưu hay quyền ở đích. |
| **Data lineage** | Một dataset/field ở đích bắt nguồn từ đâu và được biến đổi thế nào? | Quan hệ source → transformation → destination, schema mapping. | Lineage kỹ thuật có thể không chứa business purpose hoặc hợp đồng dữ liệu. |
| **Data classification** | Dữ liệu nhạy cảm, quan trọng và có tác động CIA như thế nào? | Nhãn/thuộc tính và tiêu chí phê duyệt. | Nhãn không tự triển khai quyền hay mã hóa. |
| **Data mapping / processing record** | Ai xử lý dữ liệu nào, cho mục đích nào và theo trách nhiệm nào? | Bảng xử lý, hệ thống, bên nhận, retention và nghĩa vụ. | Một bảng quản trị thiếu tuyến kỹ thuật có thể bỏ sót cache/event/log. |
| **Threat model** | Kẻ tấn công hoặc sai sót có thể khai thác các thành phần/ranh giới ra sao? | Scenarios, trust boundaries, controls và risk decisions. | Không thay thế test và evidence về hệ thống đang chạy. |

Chúng **bổ trợ nhau**. Data catalog cho biết dataset “Customer Contact” là Confidential. Data flow cho biết email khách hàng được gửi qua API, event bus, search index và hệ thống vận chuyển. Lineage chứng minh warehouse đã nhận trường email từ event nào. Threat model phát hiện nguy cơ event được gửi tới sai consumer. Security assurance kiểm tra **quy định và hiện trạng** của từng nơi.

### Hai cấp độ cần tách

- **Logical flow:** mô tả “Invoice Service gửi dữ liệu giao dịch cho Analytics Service” để thảo luận mục đích và quyền.
- **Physical/deployment flow:** mô tả API, topic, object storage, region, tài khoản dịch vụ, network route, namespace và replication để kiểm tra thực tế.

Không nên bắt một sơ đồ phải chứa mọi trường, nhưng phải có **traceability** giữa sơ đồ logic và inventory/luồng vật lý. Nếu sơ đồ cấp cao nói “Analytics” trong khi production có ba kho dữ liệu và hai vendor, cuộc đánh giá cần mở rộng tới đúng điểm nhận.

## 3. Các phần tử của một Data Flow Diagram phục vụ bảo mật

Một DFD thường dùng những loại phần tử sau:

| Phần tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **External entity** | Chủ thể/hệ thống bên ngoài phạm vi xử lý đang mô hình hóa. | Người dùng, Identity Provider, đối tác vận chuyển. |
| **Process** | Thành phần nhận, xử lý, biến đổi hoặc quyết định trên dữ liệu. | Invoice API, Export Worker, ETL Job. |
| **Data store** | Nơi dữ liệu được lưu để sử dụng sau. | Database, bucket, cache, message broker, backup. |
| **Data flow** | Đường dữ liệu đi từ phần tử nguồn đến phần tử đích. | HTTPS API request, queue event, object download. |
| **Trust boundary** | Ranh giới mà mức tin cậy, quyền điều khiển hoặc trách nhiệm thay đổi. | Trình duyệt → API; tenant A → platform; SaaS → vendor. |

Sơ đồ có mũi tên phải đặt tên **loại dữ liệu và hướng**. Mũi tên “HTTPS” mô tả kênh nhưng không mô tả có gì bên trong; “Customer contact subset” hữu ích hơn khi đánh giá data minimization. Một kênh có thể truyền **request và response mang loại dữ liệu khác nhau**, cần hai flow hoặc thông tin tách biệt khi rủi ro khác nhau.

### Tại sao trust boundary quan trọng?

Ranh giới không chỉ là cổng firewall. Dữ liệu có thể thay đổi mức độ tin cậy khi:

- Đi từ **người dùng không tin cậy** vào API xử lý dữ liệu có giá trị.
- Đi qua **dịch vụ có danh tính và quyền khác**.
- Từ **tenant A** sang thành phần xử lý nhiều tenant.
- Từ **production** sang staging hoặc warehouse do nhóm khác quản lý.
- Từ **tổ chức** sang SaaS hoặc đối tác bên ngoài.
- Từ **database** sang log, cache, backup, CDN hoặc thiết bị cá nhân.

**Cross-boundary flow cần được kiểm soát cả hai phía.** TLS bảo vệ đường truyền có thể giảm nguy cơ bị đọc/sửa trên mạng, nhưng không chứng minh người nhận được phép giữ dữ liệu hay worker xử lý đúng tenant.

## 4. Các trường metadata cần có cho mỗi luồng

Sơ đồ có thể dễ xem, nhưng muốn đưa vào audit cần một **data flow register** với thông tin truy vết.

| Trường | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **flow_id / version** | Luồng này là luồng nào, phiên bản gì? | FLOW-INV-EXPORT-03 / rev 4 |
| **business purpose** | Vì sao chuyển dữ liệu? | Tạo file hóa đơn khách hàng đã yêu cầu. |
| **source / destination** | Thành phần nào tạo và nhận? | Invoice Service → Export Worker. |
| **dataset / fields** | Loại dữ liệu và những trường thực tế? | invoice_id, tenant_id, amount, status; không có secret. |
| **classification / impact** | Mức độ nhạy cảm và CIA? | Confidential, integrity cao. |
| **identity / owner** | Principal nào xử lý và ai chịu trách nhiệm? | export-worker identity, service/data owner. |
| **trust boundary** | Luồng có vượt vùng quyền hoặc tổ chức? | App service → broker consumer; SaaS → đối tác. |
| **transport / format** | Truyền bằng gì, thông điệp ra sao? | mTLS, JSON event, batch CSV, HTTPS API. |
| **authorization / purpose** | Cơ chế quyết định đúng người/tenant/mục đích? | Job được tạo sau object-level authorization. |
| **storage / copies** | Dữ liệu có persist, cache, retry, backup không? | Queue DLQ, export bucket, analytics copy. |
| **protection controls** | Áp dụng control nào ở nguồn, kênh và đích? | Field allowlist, IAM, encryption, monitoring. |
| **retention / deletion** | Bao lâu, xóa ở đâu, xử lý bản sao thế nào? | Job TTL, lifecycle rule, supplier obligations. |
| **tests / evidence** | Đánh giá ra sao và bản nào đã được kiểm tra? | AUTHZ-05, DATA-MIN-02, test report, config snapshot. |
| **exception / risk** | Còn phần nào chưa kiểm tra hoặc không đạt? | Vendor log retention chưa xác minh, finding F-17. |

### Một dòng data flow không phải một dòng API duy nhất

Một HTTP endpoint có thể đọc cache, truy vấn database, gửi event và trả response; đây là **nhiều luồng có mục đích, tài sản và controls khác nhau**. Một batch job có thể xuất dữ liệu ra nhiều nơi mà không có endpoint riêng. Vì vậy cần phân rã theo **đường đi và quyết định bảo mật**, không chỉ đếm số API.

## 5. Quy trình lập bản đồ data flow theo rủi ro

Một quy trình thực hành gồm tám bước:

1. **Chốt mục tiêu và scope:** hệ thống, dữ liệu, tenant, môi trường, khu vực lưu trữ và các bên liên quan.
2. **Lập inventory:** dataset/field, data owner, ứng dụng, kho lưu, event, file, nhà cung cấp, tài khoản dịch vụ.
3. **Vẽ DFD mức ngữ cảnh:** các entity và ranh giới hệ thống, luồng vào/ra chính.
4. **Phân rã luồng rủi ro cao:** export, thanh toán, thay quyền, analytics, backup, logs, file download.
5. **Gắn classification, mục đích, trust boundary, authorization và data minimization** cho từng flow.
6. **Tìm risk scenarios và định nghĩa controls:** bảo mật, toàn vẹn, sẵn sàng, quyền riêng tư và lifecycle.
7. **Kiểm tra thực tế:** code/config/schema, traces đã làm sạch, access tests, data sampling, logs và nhà cung cấp.
8. **Lưu evidence, xử lý phát hiện và cập nhật bản đồ:** event mới, schema mới, consumer mới, thay nhà cung cấp hoặc thay mục đích phải kích hoạt review.

### Không cần vẽ mọi chi tiết ngay

Có thể bắt đầu ở mức hệ thống rồi **drill down theo độ nhạy và impact**. Nếu rủi ro chính là export thông tin khách hàng, ưu tiên hiểu đường export từ người dùng tới file và mọi bản sao. Một hệ thống public website có thể cần tập trung hơn vào integrity, nguồn nội dung và availability.

Vẫn phải ghi nhận **scope exclusions** để không biến “phần đã khảo sát” thành “toàn bộ hệ thống”.

## 6. Data flow mức ngữ cảnh: hệ thống hóa đơn SaaS

Ví dụ giả định: ứng dụng Invoice SaaS cho nhiều doanh nghiệp tạo, lưu, tra cứu, xuất hóa đơn và phân tích số liệu. Khách hàng có thể tải file; đối tác nhận một tập trường có giới hạn để xử lý tác vụ kinh doanh.

~~~mermaid
flowchart LR
    U["Khách hàng / Trình duyệt"] -->|Đăng nhập, yêu cầu, dữ liệu hóa đơn| API["Invoice SaaS API"]
    IDP["Enterprise IdP"] -->|Thông tin xác thực| API
    API -->|Đọc / ghi có kiểm soát| DB[("Invoice Database")]
    API -->|Yêu cầu xử lý có tenant/job ID| MQ[("Message Broker")]
    MQ --> WORK["Export / Analytics Workers"]
    WORK -->|File xuất có kiểm soát| OBJ[("Object Storage")]
    WORK -->|Dữ liệu tối thiểu đã biến đổi| WH[("Analytics Warehouse")]
    API -->|Subset đã duyệt| EXT["Đối tác bên ngoài"]
    DB -->|Snapshot / backup| BK[("Protected Backups")]
    API -->|Security events / metrics| LOG[("Logging / SIEM")]
    U <-->|File sau kiểm tra quyền| OBJ
~~~

### Những điều sơ đồ này chưa chứng minh

- Luồng API có **thật sự** dùng đối tượng đúng tenant hay không.
- Broker có nhận toàn bộ payload nhạy cảm hay chỉ metadata.
- Export worker có được quyền database rộng đến mức nào.
- Object storage có link tải public hoặc CDN không.
- Analytics có giữ các định danh khách hàng không cần thiết không.
- Backup và log có bản sao ngoài vùng đang mô tả không.
- Supplier có lưu hoặc truyền tiếp dữ liệu cho tổ chức khác không.

Vì vậy DFD là **đầu vào cho câu hỏi bảo mật**, không phải bằng chứng control hiệu quả.

### Những ranh giới trong ví dụ

**TB-1 Browser ↔ API:** dữ liệu từ người dùng có thể bị thao túng; cần authentication, authorization, input validation và session controls.

**TB-2 IdP ↔ API:** ranh giới federation; API tin các kết quả xác thực đã được kiểm tra nhưng vẫn phải quyết định quyền trên invoice.

**TB-3 API ↔ DB:** dữ liệu có giá trị cao; service identity, truy vấn theo tenant, database grants và audit.

**TB-4 API ↔ Broker ↔ Worker:** payload có thể bị replay, sửa, trễ hoặc đến sai consumer; cần nguồn tin cậy, idempotency và quyền ở worker.

**TB-5 SaaS ↔ đối tác:** bên khác kiểm soát môi trường nhận, mục đích và retention.

**TB-6 Database ↔ backup/analytics/log:** các bản sao có thể sống lâu, quyền khác hoặc chứa nhiều dữ liệu hơn dự kiến.

## 7. Phân rã một luồng quan trọng: export hóa đơn

Export là ví dụ điển hình cho **đường dữ liệu vượt ra ngoài việc đọc qua API**.

~~~mermaid
sequenceDiagram
    participant U as User tenant A
    participant API as Invoice API
    participant DB as Invoice DB
    participant Q as Queue
    participant W as Export Worker
    participant S as Object Storage
    U->>API: POST /exports (filter, tenant context)
    API->>API: Xác thực, quyền export và policy
    API->>DB: Tạo job đã gắn tenant, actor, scope
    DB-->>API: Job ID
    API->>Q: Thông báo job ID / metadata tối thiểu
    API-->>U: 202 Accepted + Job ID
    Q-->>W: Nhận job
    W->>DB: Đọc job; kiểm tra scope; truy vấn dữ liệu tenant A
    DB-->>W: Tập trường được phép
    W->>S: Ghi file bảo vệ và metadata TTL
    W->>DB: Cập nhật trạng thái job / audit
    U->>API: GET /exports/{jobId}/download
    API->>API: Xác minh chủ thể, tenant, quyền, TTL
    API-->>U: Quyền tải có thời hạn / download có kiểm soát
    U->>S: Tải file theo cơ chế được cấp
~~~

### Không tin tenant ID trong event như một bằng chứng authorization

Client có thể gửi tenant_id không đáng tin. Sau khi tạo job, server nên gắn **tenant và actor từ ngữ cảnh đã xác minh**, lưu các scope cần thiết và quyết định quyền tại thời điểm phù hợp. Worker đọc job từ nguồn tin cậy và kiểm tra khả năng xử lý. Không cho phép người gọi tự thay đổi tenant trong message rồi khiến worker dùng service account đọc chéo tenant.

### Bất đồng bộ làm đổi ý nghĩa trạng thái

HTTP 202 **Accepted** chỉ có nghĩa yêu cầu được tiếp nhận theo thiết kế, không có nghĩa **file đã hoàn tất**, quyền đã được kiểm tra ở mọi bước hoặc dữ liệu đã được gửi an toàn. Cần phân biệt:

- **EXPORT_REQUESTED / ACCEPTED:** yêu cầu/job được chấp thuận.
- **EXPORT_STARTED:** worker đã bắt đầu.
- **EXPORT_COMPLETED / FAILED:** kết quả cuối cùng của job.
- **DOWNLOAD_GRANTED / DENIED:** quyết định tại lần truy cập file.
- **OBJECT_ACCESSED:** nếu nền tảng storage có dấu vết phù hợp, đối chiếu được với job/session.

Một job có thể retry hoặc chạy trùng; một link tải có thể được mở từ nơi khác. **Data flow assurance** phải bao gồm event, trạng thái job, thời điểm tạo file, đường cấp link và đường tải thực tế.

## 8. Phân loại dữ liệu và mục đích xử lý theo từng flow

Không phải tất cả dữ liệu trong một luồng đều có cùng độ nhạy. Cần kết hợp **data classification, các thuộc tính CIA và nhu cầu nghiệp vụ**.

| Dataset / trường | Ví dụ mức nhạy cảm | Mục đích thông thường | Điểm kiểm soát |
| --- | --- | --- | --- |
| Public product catalog | Có thể công khai sau phê duyệt | Hiển thị cho mọi khách | Bảo vệ integrity và nguồn công bố. |
| Invoice ID + tenant ID | Nội bộ/nhạy cảm theo ngữ cảnh | Định danh và cô lập tài nguyên | Không tự tiết lộ tenant hoặc quyền qua ID; authorization theo đối tượng. |
| Hóa đơn đầy đủ | Confidential theo tình huống giả định | Xử lý và cung cấp chứng từ cho chủ thể được phép | Quyền tối thiểu, mã hóa, export và retention. |
| Email/địa chỉ khách | Dữ liệu cá nhân trong nhiều bối cảnh | Gửi hóa đơn hoặc liên hệ theo mục đích được duyệt | Data minimization, giới hạn bên nhận, lifecycle. |
| Tổng doanh thu theo nhóm | Có thể mật về kinh doanh | Báo cáo quản trị/analytics | Kiểm tra nguy cơ suy diễn từ nhóm nhỏ và quyền của người nhận. |
| API key, signing key | Bí mật xác thực đặc biệt nhạy cảm | Chứng thực hệ thống hoặc ký | Không đưa vào analytics/log/event, quản lý secret/keys riêng. |
| Audit/security event | Có thể chứa dữ liệu nhạy cảm về người dùng/hệ thống | Phát hiện, điều tra, kiểm chứng controls | Giới hạn trường, quyền SIEM, integrity và retention. |

Những mức trên chỉ **minh họa**; tổ chức phải có tiêu chí phân loại và người có thẩm quyền xác nhận. Dữ liệu có tính bí mật thấp vẫn có thể có **integrity hoặc availability cao**, ví dụ thông tin giá công khai phục vụ giao dịch.

### Phân loại ở nơi nhận có thể khác

Khi hai bộ dữ liệu được nối, một tập thông tin tưởng chừng ẩn danh có thể trở nên nhận diện được hoặc tiết lộ kinh doanh. Bản xuất analytics cần được đánh giá **theo nội dung thực ở đích và khả năng liên kết**, không mặc định vẫn giữ nhãn “Internal” của một field nguồn.

## 9. Data minimization và schema contract

**Data minimization** yêu cầu giới hạn dữ liệu được thu thập, chuyển và giữ ở mức cần thiết cho mục đích đã duyệt. Trong data flow, nguyên tắc này phải kiểm chứng **tại mọi chuyển tiếp**, không chỉ ở form đầu vào.

### Lỗi thường gặp: dùng toàn bộ entity làm payload

Invoice Service có một entity chứa email, địa chỉ, ghi chú nội bộ và lịch sử thanh toán. Khi phát sự kiện “Invoice Paid”, developer serialize nguyên entity rồi gửi tới broker. Analytics consumer chỉ cần tenant_id, invoice_id, amount và thời điểm, nhưng vẫn nhận mọi trường khác.

**Rủi ro:** dữ liệu nhạy cảm được nhân bản sang nhiều topic, dead-letter queue, log debug và consumer. Sau đó việc sửa schema có thể vô tình đưa thêm trường mới vào mọi nơi nhận.

### Thiết kế event contract với allowlist

~~~json
{
  "event_type": "INVOICE_PAID",
  "schema_version": 2,
  "event_id": "event-demo-482",
  "occurred_at": "2026-11-28T02:00:00Z",
  "tenant_id": "tenant-a",
  "invoice_id": "invoice-008",
  "amount_minor": 125000,
  "currency": "VND"
}
~~~

Đây là **payload minh họa**, không phải bản ghi thật. Các ID cần được tạo từ nguồn tin cậy và xem xét độ nhạy. Trường amount_minor là đơn vị tiền nhỏ theo quy tắc nghiệp vụ đã chọn; trong hệ thống thực phải có định nghĩa precision và validation phù hợp.

### Data contract cần nêu

1. **Producer/consumer và mục đích** của event.
2. **Các trường được phép**, loại, tính bắt buộc, ý nghĩa và phiên bản.
3. **Trường bị cấm**, ví dụ secret, token, thông tin cá nhân không cần thiết.
4. **Classification** và yêu cầu bảo vệ kênh/topic.
5. **Cơ chế thay đổi schema** và kiểm thử tương thích.
6. **Retention, retry, DLQ** và hành vi khi payload lỗi.
7. **Authorization/tenant context:** nguồn đáng tin cho tenant và resource reference.
8. **Evidence:** contract tests, kiểm tra sample và quản lý consumer inventory.

### Test quan trọng

Khi thêm một field vào entity nguồn, chạy test để chứng minh field đó **không tự xuất hiện ở event payload**. Data flow không được mở rộng chỉ do dùng cơ chế serialize mặc định của object.

## 10. Authentication và authorization tại mỗi điểm ra quyết định

Không nên dựa vào một lần kiểm tra quyền ở đầu luồng để suy ra mọi thành phần phía sau đều an toàn.

### Ba câu hỏi riêng biệt

- **Ai là actor?** User, service principal, batch identity, đối tác?
- **Actor được làm gì?** Đọc, sửa, xóa, export, publish, subscribe hoặc download?
- **Trên dữ liệu nào?** Tenant, đối tượng, field, mục đích, thời điểm và điều kiện gì?

Một hệ thống xử lý đa tenant cần đặc biệt cẩn trọng với **cross-tenant data leakage**.

### Phân lớp kiểm soát

| Lớp | Ví dụ control | Kịch bản lỗi nếu thiếu |
| --- | --- | --- |
| Browser/API Gateway | Xác thực, session, route protection, giới hạn request. | Người chưa xác thực gọi endpoint nhạy cảm. |
| Application service | Object-level authorization, tenant binding, giới hạn action. | User có token hợp lệ đọc object khác tenant. |
| Queue/broker | Producer/consumer ACL, topic isolation, payload verification. | Job được gửi sang consumer trái phép hoặc bị giả. |
| Worker | Quyền service identity, kiểm tra job và tenant context, giới hạn query. | Worker quyền rộng tin tenantId tùy ý trong message. |
| Database | SQL permissions, query scoping, row-level policies nếu phù hợp. | Một bug ứng dụng dẫn tới đọc tập dữ liệu lớn. |
| Object storage/CDN | Bucket/IAM policy, quyền cấp link, thời hạn, access audit. | User B dùng link tải file của A. |
| Analytics/reporting | Workspace rights, dataset-level access, export limits. | Nhân viên analytics thấy trường không cần thiết. |
| Vendor integration | Danh tính đối tác, phạm vi dữ liệu, điều khoản xử lý. | Đối tác nhận vượt mục đích hoặc giữ quá lâu. |

**Một security control ở lớp nào đó có thể là defense in depth, không phải thay thế hoàn toàn lớp khác.** Ví dụ database row-level security có thể bổ trợ kiểm tra tenant ở application, nhưng cần thiết kế đúng cho connection pool và service accounts; tuyệt đối không giả định DB policy tự bảo đảm mọi đường export mà không thử.

## 11. Java/Spring Boot: bảo vệ dòng dữ liệu trong ứng dụng

Trong ứng dụng Java, developer cần tránh biến một **entity nhiều field** thành JSON hoặc event công khai ngoài phạm vi. Nên dùng **DTO cụ thể**, phép chiếu truy vấn và authorization rõ ràng.

### Ví dụ đọc hóa đơn với tenant scope

~~~java
// Các kiểu VerifiedPrincipal, InvoiceRepository, Invoice và InvoiceView
// là các thành phần do ứng dụng thiết kế, chỉ minh họa luồng bảo vệ.
@Service
public class InvoiceReadService {
    private final InvoiceRepository repository;

    public InvoiceReadService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceView readInvoice(UUID invoiceId, VerifiedPrincipal actor) {
        String trustedTenant = actor.tenantId();
        if (trustedTenant == null || !actor.mayReadInvoice()) {
            throw new AccessDeniedException("Not authorized");
        }

        Invoice invoice = repository
                .findByIdAndTenantId(invoiceId, trustedTenant)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        // DTO chỉ có những trường được phép hiển thị.
        return new InvoiceView(
                invoice.getId(),
                invoice.getIssueDate(),
                invoice.getAmount(),
                invoice.getStatus());
    }
}
~~~

**Điều kiện an toàn:** actor phải lấy từ **security context đã được xác minh**, không phải đối tượng do client tự truyền hoặc giá trị tenant trong header tự đặt. Cần kiểm tra authorization theo action và object; ví dụ cố ý không đưa email, địa chỉ hay dữ liệu nhạy cảm khác vào DTO trả về.

### Luồng dữ liệu cần thử

- User tenant A đọc invoice A trong quyền → chỉ trả fields được phép.
- User tenant A đọc invoice B → không có nội dung của B trong response, log hoặc lỗi.
- Principal không có quyền hoặc thiếu tenant → từ chối.
- Dịch vụ khác gọi API nội bộ → danh tính dịch vụ và quyền tenant vẫn được kiểm tra.
- Export/batch endpoint → phải có test riêng, không dùng thành công của GET để suy diễn.
- Cache/search index → không trả kết quả từ tenant khác do cache key hoặc filter sai.

### Code review phải đi xa hơn controller

Kiểm tra tầng repository/query, serialization, async event, mapper, exception handling và caching. Một controller có annotation role đúng nhưng worker đọc data bằng SQL không giới hạn vẫn có data flow không an toàn.

## 12. Mã hóa và bảo vệ dữ liệu qua các trạng thái

Data flow thường được xem theo ba trạng thái:

| Trạng thái | Rủi ro điển hình | Control cần đánh giá |
| --- | --- | --- |
| **In transit** | Bị đọc/sửa trên mạng, kết nối tới endpoint không đúng. | TLS/mTLS hoặc cơ chế bảo vệ phù hợp, xác thực peer, xác minh endpoint, hạn chế kênh không được phép. |
| **At rest** | Truy cập trái phép kho lưu, snapshot, đĩa hoặc object. | Mã hóa phù hợp, IAM/storage policy, bảo vệ khóa, kiểm soát bản sao. |
| **In use** | Logic ứng dụng, process hoặc người có quyền xử lý tiết lộ dữ liệu. | Authorization, giới hạn service identity, data minimization, hardening và kiểm thử hành vi. |

### Mã hóa không thay thế phân quyền

Một worker có thể đọc dữ liệu được mã hóa nếu nó có quyền gọi database hoặc khóa giải mã. Nếu worker đọc sai tenant, mã hóa at rest không ngăn hành vi đó.

### Quản lý khóa là một luồng dữ liệu/quyền riêng

Khi đánh giá mã hóa, cần xem:

- Ai hoặc service nào có quyền **sử dụng khóa**, không chỉ nơi khóa được cất.
- Có phân tách quyền quản trị khóa và truy xuất dữ liệu khi cần?
- Key rotation, backup, recovery và thu hồi ảnh hưởng thế nào tới dữ liệu cũ?
- Bản sao/warehouse/export có dùng những key và quyền nào?
- Có audit việc thay đổi quyền hoặc thao tác với khóa không?

**Evidence** cần bao gồm cấu hình đường truyền, storage, KMS/secret policy, negative access tests và kết quả sau thay đổi. Một cờ “encryption: enabled” không đủ để khẳng định toàn bộ data flow được bảo vệ.

## 13. Data transformation: masking, tokenization, pseudonymization và aggregation

Biến đổi dữ liệu có thể giảm rủi ro trước khi gửi sang môi trường khác nhưng phải được kiểm tra đúng mục đích.

| Phương án | Ví dụ | Điều cần chú ý |
| --- | --- | --- |
| **Masking** | Chỉ hiển thị vài ký tự cuối của một định danh. | Masking tại UI không bảo vệ API, dữ liệu gốc hay event khác. |
| **Pseudonymization** | Thay customer ID bằng pseudonymous ID và giữ bảng ánh xạ riêng. | Dữ liệu vẫn có thể nhận diện lại khi có bảng ánh xạ hoặc nguồn bổ sung. |
| **Tokenization** | Thay số nhạy cảm bằng token, ánh xạ qua vault. | Vault và API giải token là tài sản cần bảo vệ. |
| **Aggregation** | Tính tổng số đơn theo nhóm. | Nhóm nhỏ hoặc phép lọc có thể suy ra thông tin cá nhân; kiểm tra disclosure. |
| **Synthetic data** | Tạo đơn hàng giả để kiểm thử. | Nếu sinh từ dữ liệu thật, phải kiểm tra khả năng ghi nhớ/tiết lộ. |
| **Redaction** | Loại bỏ trường không cần trước khi gửi log/report. | Cần kiểm tra cả error path và debug mode. |

### Trách nhiệm tại điểm biến đổi

ETL job không chỉ cần được chạy thành công; nó cần có **data contract và test** bảo đảm dữ liệu ở đích đúng loại, đúng mức tối thiểu và không lộ field cấm. Nếu kết quả biến đổi được đưa vào nhiều dataset khác, lineage cần chỉ ra nơi nhận và mức phân loại sau biến đổi.

**Không đánh đồng pseudonymization với anonymization.** Mức khả năng tái nhận diện phụ thuộc dữ liệu còn lại, bảng ánh xạ, nguồn bên ngoài và bối cảnh; kết luận liên quan quyền riêng tư phải có đánh giá chuyên môn phù hợp.

## 14. Analytics, ETL và dữ liệu dùng cho AI

Luồng phân tích thường được thiết kế sau khi ứng dụng đã vận hành, dễ trở thành nguồn nhân bản dữ liệu lớn.

### Các câu hỏi trước khi tạo dataset phân tích

1. Mục tiêu phân tích là gì, có cần dữ liệu ở mức từng cá nhân không?
2. Những trường nào được sử dụng, **trường nào phải loại**?
3. Consumer nào có quyền đọc, export hoặc kết hợp với nguồn khác?
4. Dữ liệu có được biến đổi, tổng hợp hoặc phân vùng theo tenant?
5. Có quyền truy cập rộng hơn production database không?
6. Dữ liệu được lưu bao lâu, được xóa và đồng bộ thay đổi thế nào?
7. Nhà cung cấp analytics hoặc AI có giữ dữ liệu, sử dụng để cải thiện mô hình hay chuyển tiếp cho bên khác theo điều kiện nào?
8. Có test schema drift, PII leakage, authorization và access audit không?

### Kịch bản không đạt

Invoice Service gửi event INVOICE_PAID đầy đủ customer email và địa chỉ. Analytics pipeline sao chép mọi field vào warehouse, sau đó dashboard được chia sẻ cho toàn bộ nhân viên. API gốc vẫn có phân quyền đúng, nhưng **data flow phía sau đã tạo đường disclosure độc lập**.

**Hướng sửa:** giới hạn schema event tại nguồn, giảm trường trong ETL, phân quyền dataset, xử lý bản sao đã nhận và audit các consumer; xác minh retention và khả năng xóa. Không chỉ đổi tên cột hoặc mã hóa warehouse rồi coi data minimization đã đạt.

### Data flow tới AI/ML

Nếu dữ liệu khách hàng được đưa vào training, retrieval, prompt hoặc log của một công cụ AI, phải xác định **mục đích, nguồn dữ liệu, quyền sử dụng, nơi xử lý, retention, quyền của nhà cung cấp và khả năng rò rỉ qua đầu ra**. Không mặc định dữ liệu ở prompt là “không lưu” hoặc chỉ tồn tại trong request. Bài toán vẫn là **data flow và trách nhiệm của bên nhận**, với threat scenarios chuyên biệt cần đánh giá thêm.

## 15. Logging, tracing và dữ liệu quan sát được

Logs và traces giúp security assurance kiểm tra dữ liệu đã đi đâu, nhưng chúng cũng có thể **nhân bản dữ liệu nhạy cảm** sang nền tảng quan sát.

### Những trường cần tránh đưa vào log

- Password, OTP, session cookie, access/refresh token, private key hoặc API secret.
- Toàn bộ request/response chứa hồ sơ khách hàng hoặc nội dung tài liệu.
- Connection string có mật khẩu, signed download URL hoặc thông tin bí mật trong query string.
- Payload của event chứa dữ liệu nhạy cảm không cần cho mục đích điều tra.

Thay vì log nguyên payload, sử dụng **event type, source, actor/tenant đã xác minh, resource reference, outcome, timestamp, request/job ID và reason code** theo event contract.

### Tracing không tự là audit trail

Một trace có thể cho thấy API đã gọi worker, nhưng chưa chắc chứng minh **người dùng nào được phép export**, file nào đã tạo, người nào tải hoặc kết quả cuối cùng sau retry. Audit event cho thao tác nhạy cảm cần được phát ở đúng điểm quyết định/nghiệp vụ.

### Evidence của hệ thống logging

- Event contract và kiểm tra trường nhạy cảm.
- Kiểm thử log injection và redaction.
- Quyền đọc/xuất, retention và tính toàn vẹn của log.
- Kiểm tra đường từ source → collector → storage → SIEM.
- Theo dõi nguồn im lặng, backlog, ingestion lag và lỗi parser.

**Không có log truy cập trái phép** chưa đủ chứng minh không có truy cập trái phép, đặc biệt khi log coverage hoặc retention chưa được kiểm tra.

## 16. Backups, caches, retries và hidden copies

Những bản sao khó quan sát có thể phá vỡ giả định “dữ liệu chỉ ở một database”.

| Bản sao/đường lưu | Nguy cơ | Cách kiểm soát và kiểm chứng |
| --- | --- | --- |
| **Cache** | Trả dữ liệu tenant khác do cache key không đủ scope, retention không rõ. | Key theo tenant/permission khi cần, invalidation, negative tests. |
| **Message queue** | Payload tồn tại lâu, consumer nhận sai hoặc quyền subscribe rộng. | Message schema, ACL, retention, replay/idempotency tests. |
| **Dead-letter queue (DLQ)** | Dữ liệu nhạy cảm lỗi xử lý bị giữ và người vận hành đọc rộng. | Quyền DLQ, hạn giữ, redaction khi phù hợp, xử lý retry/cleanup. |
| **Search index** | Bản sao thiếu object-level authorization hoặc chưa nhận lệnh xóa. | Index permissions, filter/tenant tests, sync/deletion lag. |
| **Object export** | Link tải rộng, thời hạn quá dài, file còn lại sau hết nhu cầu. | Access tests, short-lived links phù hợp, storage policy, lifecycle. |
| **Database snapshot/backup** | Dữ liệu đã xóa ở nguồn vẫn trong bản sao, quyền restore quá rộng. | Backup encryption, IAM, retention, restore drill và quy trình sau phục hồi. |
| **Observability pipeline** | PII/secret bị sao chép vào logs, traces và vendor. | Field minimization, sampling có kiểm soát, access review, scan test. |
| **Developer/test copy** | Production data được tải về máy hoặc staging có quyền yếu. | Synthetic data ưu tiên, approval, masking và kiểm tra lifecycle. |
| **Partner downstream** | Bên nhận chia sẻ tiếp hoặc lưu ngoài lịch thỏa thuận. | Hợp đồng/điều kiện, data transfer register, evidence đối tác và xử lý sự cố. |

### Không đồng nghĩa “bản sao” với “cùng một mức truy cập”

Một backup có thể mã hóa và lưu khác region; một search index có thể được truy cập bằng ứng dụng phân tích; DLQ có thể chỉ nhân sự vận hành xem. **Mỗi nơi nhận có chủ thể, quyền, retention và evidence riêng**, dù dữ liệu bắt nguồn từ cùng một bảng.

## 17. Retention, deletion và dữ liệu sau khi bị yêu cầu xóa

Data protection phải theo **toàn bộ vòng đời**; một dòng mũi tên kết thúc ở storage mà không có cơ chế xóa chưa phải data flow hoàn chỉnh.

### Đặt câu hỏi tại mỗi bản sao

- Dữ liệu cần lưu trong bao lâu theo mục đích và nghĩa vụ áp dụng?
- Ai có quyền tạo hold hoặc kéo dài retention?
- Dữ liệu ở cache, index, warehouse, log, archive, export và đối tác có lịch riêng không?
- Nếu xóa ở nguồn, lệnh xóa lan tới các bản sao thế nào?
- Nếu restore từ backup, dữ liệu đã phải xóa có bị đưa trở lại không?
- Có evidence về job, kết quả, lỗi, retry và thời điểm hoàn thành không?

### Phân biệt ba sự kiện

1. **Delete requested:** yêu cầu được tiếp nhận; chưa chứng minh dữ liệu đã biến mất.
2. **Delete applied:** một hệ thống đã thực thi xóa/ẩn danh theo quy tắc.
3. **Delete verified:** các nơi nhận trong phạm vi được kiểm tra hoặc có bằng chứng quy trình phù hợp.

Một yêu cầu xóa có thể chịu **giới hạn pháp lý, hợp đồng, mục đích lưu hồ sơ hoặc hold**. Không tự đặt thời hạn chung cho mọi loại dữ liệu; phải xác định nghĩa vụ thực sự áp dụng với chức năng chuyên trách.

### Backup và restore là trường hợp đặc biệt

Không nên tuyên bố xóa ngay trên mọi bản backup nếu kỹ thuật lưu trữ không hỗ trợ điều đó. Có thể cần lịch hết hạn backup, hạn chế restore, cơ chế áp lại danh sách xóa sau restore và hồ sơ nghĩa vụ/ngoại lệ. Kết luận assurance phải nêu rõ **điều nào có thể kiểm chứng ngay và điều nào phụ thuộc vòng đời lưu giữ**.

## 18. Bên thứ ba, khu vực xử lý và shared responsibility

Khi dữ liệu đi tới cloud service, supplier hoặc tổ chức khác, ranh giới không chỉ là API: **quyền sở hữu hạ tầng và trách nhiệm bảo vệ đã thay đổi**.

### Data transfer checklist

1. **Bên nhận:** đơn vị pháp lý, hệ thống, tài khoản, nhà cung cấp phụ nếu liên quan.
2. **Mục đích và trường dữ liệu:** có đúng với nhu cầu đã được duyệt không?
3. **Phạm vi địa lý/khu vực:** dữ liệu lưu, xử lý, sao chép hoặc backup ở đâu theo khả năng hợp đồng và kiến trúc?
4. **Quyền/secret/endpoint:** ai được gọi, API scopes và cơ chế xác thực ra sao?
5. **Bảo vệ kênh và đích:** cấu hình truyền, mã hóa, access policy, logging và retention.
6. **Đối soát:** kết quả gửi/nhận, trường hợp thất bại, retry, idempotency và duplicate.
7. **Lưu giữ/chia sẻ tiếp:** có những điều kiện, giới hạn và bằng chứng gì?
8. **Xóa/chấm dứt hợp tác:** quy trình xử lý bản sao và xác nhận kết thúc?
9. **Sự cố/giám sát:** đầu mối thông báo, điều tra và điều kiện bảo toàn evidence.

### Phạm vi nghĩa vụ không được tự suy đoán

Chuyển dữ liệu cá nhân, thanh toán hoặc loại dữ liệu chuyên ngành có thể chịu nghĩa vụ khác nhau theo **địa bàn, hợp đồng, loại dữ liệu và bên xử lý**. Không mặc định mọi flow qua biên giới là hợp lệ hay bất hợp lệ; cần phối hợp privacy/legal và xác minh văn bản, phiên bản, phạm vi áp dụng.

### Shared responsibility không có nghĩa mọi trách nhiệm chuyển sang vendor

Cloud provider có thể chịu trách nhiệm hạ tầng, trong khi tổ chức vẫn phải chịu trách nhiệm **cấu hình quyền, nội dung payload, data minimization, mục đích, retention và consumer inventory**. Bằng chứng đánh giá nhà cung cấp cần được xem xét theo **scope, thời kỳ và controls thực sự do bên đó vận hành**, không thay cho kiểm tra cấu hình của khách hàng.

## 19. Tính toàn vẹn và sẵn sàng của dữ liệu khi truyền bất đồng bộ

Data flow không chỉ liên quan confidentiality. Khi event bị gửi trùng, mất, tới muộn hoặc đổi thứ tự, hệ thống có thể **sửa sai trạng thái tài chính** hoặc không hoàn thành nghiệp vụ.

### Các rủi ro điển hình

- **Replay/duplicate:** cùng lệnh thanh toán hoặc export được thực thi nhiều lần.
- **Out-of-order:** sự kiện hủy đến trước hoặc sau sự kiện tạo theo thứ tự không dự kiến.
- **Partial failure:** DB đã commit nhưng event không được gửi, hoặc event gửi nhưng transaction rollback.
- **Queue backlog:** dữ liệu nhạy cảm nằm lâu hơn dự kiến, việc xử lý trễ gây sai lệch.
- **Schema mismatch:** consumer xử lý sai field hoặc bỏ qua chính sách khi đổi phiên bản.
- **Consumer permissions:** worker không được quyền nhận topic nhưng ACL cấu hình quá rộng.

### Các controls tương ứng

| Rủi ro | Control thiết kế | Evidence kiểm tra |
| --- | --- | --- |
| Duplicate processing | Event ID, idempotency key và thiết kế idempotent tại side effect. | Test gửi trùng, đối soát giao dịch không nhân đôi. |
| Mất event khi DB commit | Transactional outbox hoặc cơ chế bền vững tương đương nếu phù hợp. | Test crash giữa commit/gửi, so đối chiếu outbox và queue. |
| Gửi tới consumer không được phép | Broker IAM/ACL, môi trường/tenant scoping. | Negative subscribe/publish tests, config snapshot. |
| Message bị sửa/giả | Nguồn phát được xác thực, integrity của kênh/message khi cần, validation. | Test giả producer/sửa payload, kiểm tra logs. |
| Xử lý sai thứ tự | Sequence/version rules, reconciliation và quy tắc cập nhật có điều kiện. | Reorder tests, trạng thái cuối đúng. |
| Không nhận hoặc xử lý lỗi | Retry có giới hạn, DLQ có quyền, alert, manual reconciliation. | Test consumer outage, backlog/lag metrics, xử lý DLQ. |

**Đừng mặc định broker bảo đảm exactly-once end-to-end.** Phụ thuộc hệ thống và phạm vi giao dịch, một consumer có thể thấy duplicate hoặc side effect đã xảy ra trước khi xác nhận xử lý. Data flow phải có phép kiểm tra **kết quả nghiệp vụ cuối cùng**.

## 20. Từ Data Flow sang threat model và security requirements

Một data flow register chỉ có giá trị assurance khi **mỗi điểm rủi ro được biến thành yêu cầu có thể kiểm chứng**.

| Data flow | Threat scenario | Requirement | Control | Evidence |
| --- | --- | --- | --- | --- |
| Browser → Invoice API | User A giả tenant B hoặc đoán invoice ID. | Object-level và tenant authorization trước khi trả dữ liệu. | Principal tin cậy, tenant-scoped query, deny default. | Negative tests A/B, response check, audit event. |
| API → broker → worker | Tenant ID hoặc job payload bị thay/replay. | Worker chỉ xử lý job đã xác minh và có cơ chế chống xử lý trùng. | Job record nguồn tin cậy, ACL, idempotency. | Replay/tamper tests, worker logs, đối soát. |
| Worker → export storage | File có đường tải public hoặc TTL không kiểm soát. | Chỉ principal đúng quyền tải trong thời gian được phép. | Storage IAM, download authorization, lifecycle. | Negative download test, policy/config readback. |
| Event → analytics | Consumer nhận trường nhạy cảm vượt mục đích. | Chỉ các trường allowlist đi qua pipeline và tồn tại ở đích. | Data contract, ETL validation, dataset IAM. | Schema test, field diff, scan dữ liệu đích. |
| API → đối tác | Bên nhận quá nhiều dữ liệu hoặc chia sẻ lại. | Mục đích, phạm vi, quyền, lưu giữ và đường hỗ trợ sự cố đã duyệt. | Field allowlist, giao ước xử lý, API IAM. | Transfer records, sampled payload, partner assessment. |
| DB → backup | Backup bị đọc/xóa hoặc không restore được. | Bản sao được bảo vệ và có thể phục hồi theo BIA. | Backup IAM/encryption, restore runbook. | Negative access test, restore drill, RTO/RPO. |
| Service → logs | Token/PII bị ghi ra hệ thống quan sát. | Log tối thiểu dữ liệu và kiểm soát quyền, retention. | Structured logging, redaction, SIEM IAM. | Canary tests, log sample, access review. |

### Tách claim thiết kế và claim vận hành

**Design claim:** “Luồng export sử dụng job gắn tenant từ principal đã xác minh; worker và storage kiểm tra quyền theo thiết kế.”

**Operating claim:** “Trong release và thời kỳ đã đánh giá, các đường export thuộc phạm vi đã từ chối truy cập trái tenant, file được lưu với quyền phù hợp, event từ nguồn đến kho log đầy đủ trong các test và quan sát được thực hiện.”

Một sơ đồ và code review có thể hỗ trợ **thiết kế**; để kết luận về vận hành phải có **test, config và telemetry thực tế**, kèm giới hạn.

## 21. Security assurance bằng Claim – Argument – Evidence (CAE)

### Claim minh họa

“Trong release 2.8 của Invoice SaaS, dữ liệu hóa đơn thuộc các tenant được kiểm tra chỉ di chuyển qua các luồng đã đăng ký; các luồng export và analytics áp dụng authorization và data minimization theo requirements; mọi bản sao thuộc phạm vi có chính sách quyền và retention phù hợp.”

### Argument

1. Data asset inventory và luồng vật lý được đối chiếu với ứng dụng, queue topics, storage, warehouse và provider config.
2. Flow register định nghĩa trường dữ liệu, tenant, purpose, owner và boundaries.
3. Access/field contracts được thực thi tại API, worker, ETL và storage.
4. Tests bao phủ kết quả đúng, quyền bị từ chối, thay payload, schema drift và xóa bản sao.
5. Configuration/telemetry được theo dõi, findings có người sửa và retest.

### Evidence

- Flow diagrams được duyệt và **inventory có timestamp**.
- API, event và ETL schemas; danh sách fields thực sự ở đích.
- IAM policies, service identities, broker ACL, storage access settings.
- Integration/security tests và kết quả triển khai cho release được kiểm tra.
- Log/audit được bảo vệ, đối chiếu job ID và request IDs.
- Kiểm tra retention, xóa ở nguồn/đích, backup/restore.
- Partner data transfer records và bằng chứng bên nhận trong phạm vi có thể lấy.
- Findings, exceptions, remediation, retest và quyết định residual risk.

**Không đạt một mắt xích quan trọng thì claim toàn luồng phải được thu hẹp hoặc gắn phát hiện.** Đạt authorization ở API không đủ nếu URL tải file có thể được chia sẻ không giới hạn; đạt mã hóa storage không đủ nếu dữ liệu được chuyển tới warehouse ngoài mục đích.

~~~mermaid
flowchart TD
    A["Data asset + business purpose"] --> B["Inventory + Data flow + Trust boundaries"]
    B --> C["Threats, obligations, impact CIA"]
    C --> D["Requirements + controls by flow"]
    D --> E["Tests + observed state + evidence"]
    E --> F{"Claim đạt trong scope?"}
    F -- "Có" --> G["Time-scoped assurance conclusion"]
    F -- "Không / thiếu evidence" --> H["Finding / action / risk decision"]
    H --> I["Remediation + retest"]
    I --> E
    G --> J["Monitor schema, consumer, tenant, vendor changes"]
    J --> B
~~~

## 22. Data flow register mẫu dưới dạng YAML

Mẫu sau có mục tiêu minh họa **một luồng cụ thể** với requirement, control và evidence, không phải tệp cấu hình có thể dùng trực tiếp trong hệ thống hay metadata của bài học.

~~~yaml
flow_id: FLOW-INV-EXPORT-03
version: "4-example"
system: invoice-saas
environment: production
business_purpose: "Generate requested invoice export for authorized tenant"
data_asset:
  id: invoice-records
  classification: Confidential
  fields_allowed:
    - invoice_id
    - issue_date
    - amount
    - status
  fields_forbidden:
    - access_token
    - payment_secret
source:
  service: invoice-api
  owner_role: Invoice Service Owner
destination:
  service: export-worker
  storage: protected-export-bucket
  owner_role: Export Service Owner
trust_boundaries:
  - user_to_api
  - api_to_broker
  - broker_to_worker
  - worker_to_object_storage
processing:
  identity_source: verified_principal
  tenant_scope: server_side_job_record
  queue_payload: job_id_only_where_sufficient
  export_authorization: object_and_action_level
  file_download: authorized_time_bound_access
copies:
  - broker_retry_or_dlq
  - export_file
  - operational_audit_event
controls:
  - id: CTRL-AUTHZ-EXPORT-01
    objective: "Deny cross-tenant export and download"
  - id: CTRL-DATA-MIN-02
    objective: "Export only approved fields"
  - id: CTRL-STORE-03
    objective: "Protect files and enforce approved lifecycle"
retention:
  rule_reference: "approved-export-retention-schedule"
  copy_deletion: "include export files and queue copies as applicable"
tests:
  - negative_cross_tenant_download
  - forged_tenant_context
  - schema_field_allowlist
  - export_file_expiry_and_access
evidence:
  - "restricted://assurance/export/release-2.8/config"
  - "restricted://assurance/export/release-2.8/tests"
known_gaps:
  - "CDN path to be assessed separately if enabled"
review_triggers:
  - new_export_field
  - new_consumer_or_storage_path
  - tenant_authorization_change
  - retention_policy_change
~~~

Các ID, đường dẫn, giá trị và trạng thái là **giả định học tập**, không thể được coi là evidence thực. Khi vận hành, cần thêm timestamp, cấu hình/commit/deploy ID, phương pháp kiểm tra, người phê duyệt, kết quả test thật và bản ghi các ngoại lệ.

## 23. Kế hoạch kiểm thử end-to-end theo từng data flow

Kiểm thử ở mỗi điểm không nên chỉ đo “service trả HTTP 200”. Phải đối chiếu dữ liệu **được phép đi đâu**, **không được đi đâu**, **còn tồn tại ở đâu** và **đối tượng nào có quyền truy cập**.

| Test ID | Kịch bản | Kỳ vọng và evidence |
| --- | --- | --- |
| **DF-01** | Client gửi tenant B trong request nhưng đăng nhập thuộc A. | API không thay trusted tenant; không đọc dữ liệu B. |
| **DF-02** | Người A đọc invoice B bằng ID đoán được. | Bị từ chối; response, error và logs không lộ nội dung B. |
| **DF-03** | Producer gửi message job với tenant bị sửa. | Worker không xử lý dữ liệu ngoài job/tenant scope tin cậy. |
| **DF-04** | Gửi trùng event/job trong queue. | Không tạo side effect trái yêu cầu; kết quả có thể đối soát. |
| **DF-05** | Consumer nhận event sai schema hoặc thêm field mới. | Contract test phát hiện sai; trường nhạy cảm không vào analytics. |
| **DF-06** | Export sinh CSV với thông tin chưa duyệt. | Kiểm tra nội dung file thật: chỉ có allowlisted fields. |
| **DF-07** | User B biết file URL do user A nhận. | Không tải được nếu không có quyền phù hợp. |
| **DF-08** | Object storage hoặc CDN có cấu hình public. | Control phát hiện/ngăn theo baseline; test effective access. |
| **DF-09** | Debug log bật với request có token canary giả. | Token không hiện ở application logs, pipeline, SIEM/traces trong scope. |
| **DF-10** | Dữ liệu bị xóa tại nguồn. | Các bản sao trong phạm vi được xóa/ẩn danh theo lịch/quy trình, ghi evidence giới hạn. |
| **DF-11** | Consumer analytics mất quyền hoặc bị thay quyền. | Chỉ principal được phép truy cập dataset, có audit thay đổi. |
| **DF-12** | Vendor API trả lỗi, job retry. | Retry không gửi vượt tập trường, không nhân đôi giao dịch ngoài quy tắc. |
| **DF-13** | Backup storage không sẵn sàng hoặc thiếu khóa. | Restore drill/negative test cho thấy rủi ro và xử lý theo RTO/RPO. |
| **DF-14** | Broker DLQ chứa message lỗi nhạy cảm. | ACL, retention, access audit và cleanup phù hợp. |
| **DF-15** | Thêm consumer hoặc field mới vào event. | Trigger review classification, contract, permission và evidence. |
| **DF-16** | Một nguồn event hoặc collector im lặng. | Health monitoring phát hiện, không báo compliance giả do thiếu dữ liệu. |

**Nên phân loại kết quả** PASS, FAIL, PARTIAL, NOT TESTED, NOT APPLICABLE có lý do, EXCEPTION và EVIDENCE MISSING. Nếu không truy xuất được cấu hình partner, không gắn “PASS” chỉ vì lời xác nhận không kèm cơ sở.

### Tránh kiểm thử gây ảnh hưởng thực

Không cố tình gửi dữ liệu thật sai tenant hoặc tạo file nhạy cảm public trên production ngoài quy trình cho phép. Dùng **synthetic data, sandbox, môi trường staging tương đương và test với scope hạn chế**; kiểm tra production qua config, telemetry và phép kiểm tra an toàn được phê duyệt.

## 24. Case study: Phát hiện dữ liệu khách hàng lọt vào Analytics Warehouse

### Bối cảnh

Invoice SaaS muốn tổng hợp doanh thu theo tháng. Đội analytics cho rằng chỉ nhận invoice_id, amount và period, nhưng phiên bản mới của event INVOICE_PAID chứa thêm customer_email sau khi Invoice Service dùng bộ serializer tự động cho toàn entity.

Warehouse lưu email, dashboard có thể export dữ liệu này và retention lâu hơn database giao dịch. DFD cấp cao trước đó chỉ ghi “Invoice Service → Analytics”, chưa liệt kê **field-level lineage** hoặc bản sao.

### Bước 1 — Nhận diện claim chưa đạt

**Claim ban đầu:** “Analytics chỉ xử lý những trường cần thiết cho tổng hợp doanh thu.”

**Evidence trái chiều:** scan schema và mẫu bản ghi trong warehouse cho thấy có trường email. Đây là **control failure về data minimization** trong phạm vi được kiểm tra; không chỉ là việc sơ đồ thiếu thông tin.

### Bước 2 — Đánh giá phạm vi và rủi ro

Đội data và security xác định:

- Thời điểm field xuất hiện ở event, các consumer có nhận không.
- Những nơi đã lưu email: topic, DLQ, warehouse, backup, report export, log.
- Ai có quyền xem hoặc export dataset, log truy cập và giới hạn dữ liệu có sẵn.
- Mục đích, thỏa thuận với bên nhận và nghĩa vụ xử lý dữ liệu trong phạm vi áp dụng.
- Khả năng dữ liệu đã bị chia sẻ ngoài phạm vi; không suy diễn “chưa ai xem” chỉ vì thiếu log.

### Bước 3 — Containment và remediation

**Containment:** giới hạn quyền dataset/exports nếu có nguy cơ, tạm dừng consumer hoặc trường dữ liệu sai theo quy trình có kiểm soát, bảo toàn evidence cần thiết.

**Remediation tại nguồn:** thay automatic entity serialization bằng event DTO allowlist, bổ sung schema contract tests và review khi đổi field.

**Remediation tại nơi nhận:** xử lý dữ liệu không được phép ở warehouse, queue, DLQ và reports theo lịch và nghĩa vụ; rà quyền, retention và downstream consumers; theo dõi dữ liệu đã export.

**Root cause:** quy tắc schema thiếu owner và không có test phủ định cho field nhạy cảm, chứ không chỉ “developer quên xóa email”.

### Bước 4 — Retest

| Test | Expected | Evidence cần lưu |
| --- | --- | --- |
| Event INVOICE_PAID mới | Không có email/địa chỉ hoặc trường cấm. | Contract test, sample event synthetic. |
| Analytics transform | Chỉ tạo dữ liệu cho mục đích tổng hợp. | Mapping, output schema, sample warehouse. |
| Quyền dataset | Nhân sự không có nhiệm vụ không truy xuất được dữ liệu nhạy cảm. | Negative access tests, IAM policy. |
| Bản sao cũ | Được xử lý theo kế hoạch đã duyệt với các giới hạn rõ. | Deletion/retention records, report đối soát, exceptions. |
| Schema change tương lai | Khi thêm field nguồn, pipeline không tự đưa field vào event. | Regression test khi thêm canary field. |

### Bước 5 — Kết luận assurance

Một kết luận có trách nhiệm:

> “Trong release sau khắc phục, các trường không được phép không xuất hiện trong event và warehouse theo các luồng đã kiểm tra; quyền đọc dataset được giới hạn theo tiêu chí. Các bản sao lịch sử tại hệ thống đối tác chưa được đối chiếu nên phần đó vẫn là finding/rủi ro cần owner xử lý.”

Không được đổi thành “dữ liệu đã được bảo vệ hoàn toàn” khi vẫn còn phần chưa biết.

## 25. Ownership, RACI và phối hợp giữa các đội

Một luồng dữ liệu có thể xuyên nhiều đội, nên ownership phải rõ từ nguồn tới đích.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Data/business owner** | Xác định mục đích, loại dữ liệu, mức nhạy cảm, phạm vi sử dụng và chấp thuận chia sẻ theo thẩm quyền. |
| **Service owner / producer** | Duy trì schema đầu ra, authentication, authorization ở nguồn, test và thay đổi có kiểm soát. |
| **Consumer/warehouse owner** | Chịu trách nhiệm quyền, data minimization ở đích, retention, dữ liệu phái sinh và evidence. |
| **Platform/cloud owner** | Bảo vệ broker, IAM, storage, encryption, backup, monitoring và health pipeline. |
| **Privacy/legal/compliance** | Tư vấn mục đích xử lý, nghĩa vụ, hợp đồng, lưu trữ và chia sẻ trong phạm vi áp dụng. |
| **Security architect/threat modeling** | Xác định boundaries, trust assumptions, threat scenarios và requirements. |
| **Control owner** | Chịu trách nhiệm giải trình về thiết kế/vận hành một control đã được chỉ định. |
| **Security assurance/assessor** | Đánh giá coverage, phương pháp test, chất lượng evidence và kết luận có giới hạn. |
| **Risk owner** | Quyết định xử lý/chấp nhận residual risk theo thẩm quyền, không tự thay control owner. |
| **Incident response** | Điều phối điều tra, containment, evidence khi xảy ra vi phạm dữ liệu. |

### RACI minh họa cho event Invoice → Analytics

**R** = trực tiếp thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = thông báo.

| Hoạt động | Producer owner | Consumer owner | Data owner | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Chốt event fields và ràng buộc producer | **A/R** | C | C | C | I |
| Chốt mục đích và trường cần thiết ở dataset | C | **R** | **A** | C | I |
| Triển khai ETL, quyền warehouse và retention | C | **A/R** | C | C | I |
| Kiểm thử độc lập luồng và evidence | C | C | C | **A/R** | I |
| Quyết định residual risk còn vượt ngưỡng | C | C | C | C | **A/R** |

RACI cụ thể có thể khác tùy tổ chức. Trách nhiệm giữa producer và consumer không được để “trống” tại ranh giới; nếu có nhà cung cấp, cần bổ sung **shared responsibility theo hợp đồng và thực tế cấu hình**.

## 26. Assurance liên tục và quản trị thay đổi Data Flow

Data flow phải được cập nhật khi có thay đổi, không chỉ một lần khi kiến trúc mới ra mắt.

### Trigger quan trọng

- Thêm API, field, event, topic, consumer hoặc job mới.
- Thay **data classification**, purpose, retention hoặc quyền sử dụng.
- Tạo bản sao mới sang warehouse, test environment, CDN, cache hoặc partner.
- Đổi IAM, service identity, signing key, KMS, storage region hoặc network boundary.
- Dùng dữ liệu cho AI/ML, reporting hoặc nhóm khách hàng mới.
- Thay serializer, ETL mapping, backup/restore hoặc cơ chế xóa.
- Có security finding, incident, evidence gap, schema drift hoặc quyền trái phép.
- Ký hợp đồng mới, kết thúc vendor hoặc thay quy định có áp dụng.

### Data flow change gate

Khi một pull request thêm trường email vào event, pipeline nên:

1. Phát hiện schema diff.
2. Xác định producer, consumers, classification và data owner.
3. Kiểm tra field có được đưa vào contract và mục đích đã duyệt không.
4. Yêu cầu review phù hợp và cập nhật security requirements.
5. Chạy tests payload/field-level, IAM, tenant context và retention liên quan.
6. Triển khai, kiểm chứng payload tại nơi nhận và lưu evidence theo release.
7. Theo dõi drift, các consumer mới và thực hiện reassessment nếu có thay đổi ngoài dự kiến.

**CI/CD PASS không thay cho production verification.** Một bộ test schema trên staging có thể bỏ qua broker production đang cấu hình sai ACL hoặc consumer không có trong inventory.

### Chỉ số theo dõi

| Chỉ số | Mục đích | Nguy cơ diễn giải sai |
| --- | --- | --- |
| **Data asset/flow coverage** | Biết bao nhiêu luồng quan trọng có owner, classification và metadata. | Population thiếu sẽ tạo tỷ lệ đẹp nhưng sai. |
| **Unapproved consumer/field changes** | Phát hiện luồng mới vượt mục đích. | Không phát hiện có thể do thiếu telemetry. |
| **Sensitive field leakage tests** | Theo dõi việc field cấm xuất hiện ở event/log/warehouse. | Scanner có false negative hoặc chỉ chạy một môi trường. |
| **Cross-tenant authz test pass** | Xác minh ranh giới tenant qua API/worker/export. | Chỉ test GET không đại diện toàn bộ data flow. |
| **Retention/deletion verification** | Xử lý bản sao theo lifecycle và exceptions. | Xóa database không đồng nghĩa xóa backup/partner. |
| **Config/evidence freshness** | Liệu bằng chứng còn phù hợp với bản triển khai và phạm vi? | File mới tải lên có thể chứa thông tin cũ. |
| **Finding age/retest completion** | Theo dõi sai lệch đã được sửa và xác minh. | Ticket đóng không đồng nghĩa dữ liệu đã xử lý xong. |
| **Pipeline delivery/health** | Nhận ra mất event, backlog, collector không hoạt động. | Không có alert không chứng minh không có sự cố. |

## 27. Sai lầm phổ biến khi lập Data Flow

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có sơ đồ kiến trúc là đủ.” | Cần field/dataset, mục đích, trust, owner, copies, tests và evidence. |
| “Database đã mã hóa nên data flow an toàn.” | Dữ liệu khi xử lý, export, queue, log và quyền consumer còn rủi ro. |
| “User được xác thực là được xử lý mọi dữ liệu.” | Authorization phải theo action, object, tenant và bối cảnh. |
| “API chặn cross-tenant thì worker cũng an toàn.” | Worker dùng service identity và nguồn tenant riêng; phải kiểm tra từng ranh giới. |
| “Async 202 nghĩa là giao dịch đã hoàn tất.” | Chỉ là yêu cầu được tiếp nhận; cần final outcome và correlation. |
| “Event không chứa email nên mọi nơi đều không có PII.” | Có thể có dữ liệu nhận diện khác, kết hợp dataset hoặc DLQ/log vẫn giữ bản cũ. |
| “Pseudonymized nghĩa là hoàn toàn ẩn danh.” | Có thể tái nhận diện; cần đánh giá ngữ cảnh và nguồn liên kết. |
| “Chỉ cần vẽ các flow production.” | Test/staging, backup, logging và vendor có thể chứa dữ liệu thật hoặc bản sao. |
| “Xóa ở database nghĩa là dữ liệu đã hết.” | Phải xét cache, export, index, warehouse, backups và partner. |
| “Hợp đồng vendor chứng minh mọi control của mình.” | Shared responsibility và cấu hình do khách hàng quản lý vẫn cần kiểm tra. |
| “Schema mới vẫn parse được nghĩa là không có rủi ro.” | Trường mới có thể làm tăng loại dữ liệu/đối tượng nhận, dù schema backward compatible. |
| “Không thấy truy cập trái phép nghĩa là không có lộ dữ liệu.” | Cần xét logging coverage, nguồn, retention và khả năng quan sát. |
| “Mọi dữ liệu đều phải giữ cùng thời hạn.” | Retention theo mục đích, nghĩa vụ, loại dữ liệu và bản sao; phải có phê duyệt. |
| “Data flow đã duyệt một lần nên không cần cập nhật.” | Consumer, field, key, tenant, provider và mục đích thay đổi cần reassessment. |
| “Tạo ticket remediation là risk đã giảm.” | Chỉ tính controls đã triển khai và có evidence; target khác current residual risk. |

## 28. Checklist rà soát Data Flow trước audit hoặc release

1. **Scope:** đã nêu dịch vụ, tenant, môi trường, khu vực, nhà cung cấp và phần loại trừ?
2. **Inventory:** data assets, owners, trường, classification và bản sao có đầy đủ?
3. **DFD/lineage:** đã thể hiện source, process, store, destination và trust boundaries?
4. **Purpose:** mỗi flow có mục đích được duyệt và data minimization?
5. **Authentication/authorization:** ai phát/gửi/nhận, có object/tenant checks và service identity?
6. **Transport/storage:** đường truyền, mã hóa, quản lý khóa và IAM đúng mức rủi ro?
7. **Async/data integrity:** retry, replay, idempotency, DLQ, thứ tự và failure handling?
8. **Logs/traces:** dữ liệu nhạy cảm có lọt vào observability pipeline và audit đủ tin cậy?
9. **Downstream:** analytics, export, cache, backup, CDN, third-party và AI/ML có được bao phủ?
10. **Lifecycle:** retention, deletion, archive, hold và restore có quy trình/kiểm chứng?
11. **Tests:** có negative cases, schema tests, data sampling, config và end-to-end verification?
12. **Evidence:** có provenance, scope, timestamp, release, observed results và limitations?
13. **Governance:** role/data/control owner, ngoại lệ, finding và residual risk rõ?
14. **Change triggers:** có cách phát hiện schema/consumer/data purpose/partner changes và cập nhật flow?

## 29. Bài tập ứng dụng và gợi ý giải

### Bài tập A — Bản vẽ thiếu object storage

Đội kiến trúc chỉ vẽ User → API → DB. Sau đó một tính năng export tạo file CSV trên bucket và cho người dùng tải qua link.

**Gợi ý:** Cần thêm Export Worker, queue nếu có, object storage, đường cấp link và tải thực tế, expiration/retention, quyền tenant và audit. Một diagram bỏ storage không thể hỗ trợ claim “mọi đường đọc dữ liệu đều có authorization”.

### Bài tập B — Event chứa quá nhiều trường

Consumer analytics cần amount và month, nhưng event InvoicePaid có cả email và địa chỉ vì producer serialize nguyên entity.

**Gợi ý:** Áp dụng field-level allowlist, data contract và tests chống schema drift. Kiểm tra bản sao cũ ở topic/DLQ/warehouse/log và quyền consumer. Không chỉ mã hóa broker rồi coi đúng mục đích.

### Bài tập C — Client tự gửi tenant ID

Worker nhận message gồm tenant_id và invoice_ids do client cung cấp, sử dụng tài khoản database có quyền rộng để tạo file.

**Gợi ý:** Ràng buộc job vào tenant/principal đã xác minh ở server, lưu nguồn tin cậy, kiểm tra quyền ở các điểm xử lý và giảm quyền worker. Test forged tenant, cross-tenant job, replay và file download; không chỉ kiểm tra ở UI.

### Bài tập D — Xóa database nhưng còn dữ liệu ở cache

Một khách hàng gửi yêu cầu xóa theo quy trình được phép; database xóa thành công, nhưng search index và cache vẫn chứa dữ liệu.

**Gợi ý:** Cập nhật data lineage và deletion plan, đo propagation, kiểm tra bản sao trong scope, audit failures. Kết luận chỉ có thể là “source deletion applied” nếu chưa xác minh downstream; retention/hold của backup cần đánh giá riêng.

### Bài tập E — Đối tác lưu dữ liệu ngoài phạm vi ban đầu

API chỉ gửi tên và số điện thoại cho đối tác vận chuyển, nhưng hợp đồng thay đổi khiến dữ liệu được đồng bộ sang vendor phụ, không có trong flow register.

**Gợi ý:** Thêm downstream recipient và trust boundary; xem purpose, quyền, contract, retention, địa bàn và nghĩa vụ áp dụng với bộ phận chuyên trách. Đánh giá bảo vệ ở đối tác, cơ chế thông báo sự cố và cập nhật evidence/risk.

### Bài tập F — Đủ log nhưng không biết ai tải file

API ghi EXPORT_REQUESTED có user ID, worker ghi EXPORT_COMPLETED có job ID, storage chỉ có object access log theo service account. Đội điều tra không liên kết được user với file bị tải.

**Gợi ý:** Data flow cần thiết kế correlation giữa request/job/object và download action, xác thực principal ở điểm cấp quyền và audit đường tải. Cần kiểm tra dữ liệu log có an toàn, retention đủ và biết giới hạn nếu CDN/storage không hỗ trợ attribution tới user.

### Bài tập G — Schema test PASS, production vẫn rò dữ liệu

CI kiểm tra event DTO không chứa email. Nhưng một debug handler trong production ghi nguyên message payload vào log SaaS bên ngoài.

**Gợi ý:** Data flow còn đường **service → logging vendor**. Phải bổ sung inventory, log minimization/redaction, kiểm tra debug mode và negative test với canary secret; kiểm soát quyền, retention và xử lý bản sao đã ghi. CI test của event DTO không đủ cho claim bảo vệ dữ liệu toàn luồng.

### Bài tập H — Backup không restore được

Doanh nghiệp lưu backup hóa đơn được mã hóa trên kho khác region và báo job thành công. Diễn tập restore không giải mã được vì quyền KMS chỉ tồn tại trong môi trường cũ.

**Gợi ý:** Yêu cầu Availability và Integrity của data flow chưa đạt. Cần đánh giá luồng sử dụng khóa trong kịch bản restore, quyền/kho lưu, runbook, test RTO/RPO và đối soát nghiệp vụ. Một backup encrypted không tự chứng minh khả năng phục hồi.

## Kết luận

**Data flow** giúp tổ chức nhìn thấy **đường đi thực tế của dữ liệu** từ nơi tạo đến nơi xử lý, chia sẻ, lưu lại, sao lưu và xóa. Bảo vệ dữ liệu vì vậy không thể chỉ là kiểm tra database hoặc API chính: mỗi boundary, consumer, bản sao và tác vụ bất đồng bộ đều có mục đích, quyền, rủi ro và nghĩa vụ riêng. Trong **SECURITY_SECURITY_ASSURANCE**, giá trị của data flow nằm ở khả năng **liên kết dữ liệu và luồng cụ thể với security requirements, controls, test cases, evidence, findings, remediation và residual risk**. Một bản đồ hữu ích phải được đối chiếu với hiện trạng, kiểm chứng cả các đường bị từ chối và failure cases, rồi cập nhật khi schema, consumer, tenant hoặc nhà cung cấp thay đổi. **Chỉ kết luận bảo vệ dữ liệu đạt trong phạm vi những luồng và bản sao đã có bằng chứng kiểm chứng đáng tin cậy**.
