# Triển khai riêng cho khách hàng và triển khai dùng chung

> **Chương:** Mô hình triển khai  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây (cloud architecture), từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào lựa chọn mức độ cô lập giữa các khách hàng, đánh đổi về độ tin cậy, bảo mật, mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **triển khai riêng cho từng khách hàng** (single-tenant/dedicated deployment) và **triển khai dùng chung** (multi-tenant/shared deployment), đồng thời không nhầm mô hình thuê dùng với mô hình hạ tầng công cộng, riêng hoặc lai.
2. Phân biệt các mô hình triển khai **silo, pool, bridge** và mức cô lập ở lớp mạng, compute, dữ liệu, khóa mã hóa và vận hành.
3. Thiết kế đường ranh giới tenant để giảm nguy cơ rò rỉ dữ liệu, ảnh hưởng chéo và hiện tượng **noisy neighbor**.
4. So sánh các phương án theo yêu cầu nghiệp vụ, tuân thủ, SLO, RTO/RPO, khả năng mở rộng, TCO và năng lực đội vận hành.
5. Lập phương án onboarding, nâng cấp, giám sát, sao lưu, khôi phục và chuyển đổi tenant giữa các mô hình.
6. Ghi lại lựa chọn bằng Architecture Decision Record (ADR) và xác định phép thử cần có trước khi triển khai thực tế.

## 1. Khái niệm nền tảng: tenant là gì?

Trong ứng dụng SaaS hoặc nền tảng phục vụ nhiều tổ chức, **tenant** là một đơn vị khách hàng hoặc tổ chức có dữ liệu, người dùng, cấu hình, quyền truy cập và chính sách riêng. Một tenant có thể có hàng nghìn người dùng; một người dùng cũng có thể được phép truy cập nhiều tenant nếu nghiệp vụ hỗ trợ điều đó.

Ví dụ: một phần mềm quản lý đặt chỗ trên cloud phục vụ 50 doanh nghiệp. Mỗi doanh nghiệp là một tenant, còn nhân viên của doanh nghiệp là người dùng thuộc tenant tương ứng.

Hai lựa chọn triển khai phổ biến:

- **Triển khai riêng cho khách hàng (dedicated/single-tenant):** mỗi tenant có một hoặc nhiều thành phần triển khai dành riêng, chẳng hạn cụm ứng dụng và cơ sở dữ liệu riêng. Đơn vị cô lập cụ thể phải được mô tả rõ: môi trường cloud, account/subscription, VPC/VNet, cluster, namespace, instance, database hay chỉ schema.
- **Triển khai dùng chung (shared/multi-tenant):** nhiều tenant cùng sử dụng một phần hạ tầng hoặc cùng một phiên bản ứng dụng; hệ thống nhận diện và thực thi ranh giới truy cập, phân bổ tài nguyên theo tenant.

**Hai khái niệm không đối lập tuyệt đối.** Một ứng dụng có thể dùng chung lớp định danh, điều khiển hoặc phần API nhưng dành cơ sở dữ liệu riêng cho tenant lớn. Vì vậy, khi thiết kế phải trả lời **“chung ở lớp nào, riêng ở lớp nào?”** thay vì chỉ gắn nhãn single-tenant/multi-tenant.

### Không nhầm tenancy với mô hình cloud

- **Public cloud** mô tả môi trường hạ tầng do nhà cung cấp cloud vận hành; vẫn có thể triển khai **single-tenant** trên một account/VPC dành riêng cho khách hàng.
- **Private cloud** mô tả môi trường cloud dành cho một tổ chức; phần mềm trong đó vẫn có thể có nhiều nhóm hoặc đơn vị nghiệp vụ đóng vai trò tenant.
- **Hybrid cloud** nói về việc kết hợp các môi trường triển khai; một hệ thống hybrid có thể dùng mô hình silo, pool hoặc kết hợp.
- **Multi-tenant SaaS** mô tả cách ứng dụng phục vụ và cách ly các tổ chức khách hàng; một dịch vụ cloud dùng chung bên dưới không tự động biến ứng dụng thành multi-tenant đúng nghĩa.

## 2. Ba mẫu tổ chức tenant: silo, pool và bridge

### 2.1. Silo: mỗi tenant một môi trường ứng dụng riêng

~~~mermaid
flowchart TB
    C["Các khách hàng"] --> A["Tenant A"]
    C --> B["Tenant B"]
    A --> AP["Compute / API A"]
    AP --> AD[("Database A")]
    B --> BP["Compute / API B"]
    BP --> BD[("Database B")]
    OP["Nền tảng tự động hóa và quan sát"] -.-> AP
    OP -.-> BP
~~~

Mỗi tenant có một “ngăn” triển khai. Ở mức cô lập cao, các ngăn có thể thuộc các cloud account/subscription, VPC, cluster, khóa mã hóa và database khác nhau. Tuy nhiên, **mỗi tenant có deployment riêng không đồng nghĩa chắc chắn có phần cứng vật lý riêng**; dịch vụ quản lý của cloud vẫn có thể chia sẻ hạ tầng vật lý của nhà cung cấp.

**Ưu điểm:**

- Thuận lợi khi khách hàng yêu cầu phạm vi cô lập, cấu hình, vùng dữ liệu hoặc lịch nâng cấp khác nhau.
- Dễ khoanh vùng một số sự cố và đo chi phí hạ tầng theo tenant.
- Có thể mở rộng năng lực cho tenant lớn độc lập, hoặc áp dụng quy tắc sao lưu riêng.

**Hạn chế:**

- Chi phí cố định nhân theo số tenant, dễ lãng phí tài nguyên khi lưu lượng thấp.
- Nhiều môi trường phải vá lỗi, giám sát, kiểm thử và quản lý cấu hình; nguy cơ **configuration drift** nếu triển khai thủ công.
- Onboarding, nâng cấp và xử lý sự cố có thể phức tạp khi có hàng trăm hoặc hàng nghìn bản triển khai.
- Cần quy trình quản trị quyền truy cập và tự động hóa nhất quán cho mọi môi trường.

Silo phù hợp khi cô lập mạnh là điều kiện hợp đồng/tuân thủ, tenant có tải lớn, cần tùy biến sâu hoặc có yêu cầu về vùng dữ liệu và chu kỳ nâng cấp riêng.

### 2.2. Pool: nhiều tenant dùng chung ứng dụng và tài nguyên

~~~mermaid
flowchart TB
    A["Tenant A"] --> GW["API Gateway / Auth"]
    B["Tenant B"] --> GW
    C["Tenant C"] --> GW
    GW --> APP["Ứng dụng dùng chung, tenant-aware"]
    APP --> DB[("Cơ sở dữ liệu dùng chung\ncó phân tách tenant")]
    APP --> CACHE[("Cache / Queue dùng chung\nvới khóa và hạn mức tenant")]
~~~

Trong mô hình pool, tenant được phân biệt bằng danh tính và ngữ cảnh tenant đã được xác thực. Có thể có một bộ API, worker, cache hoặc database dùng chung. Mức dùng chung càng cao thì **kiểm soát cô lập logic** càng trở nên quan trọng.

**Ưu điểm:**

- Dễ tận dụng tài nguyên nhàn rỗi, đặc biệt với nhiều tenant nhỏ.
- Một pipeline triển khai cho phần ứng dụng chung; sửa lỗi, cập nhật chức năng đồng loạt thuận tiện.
- Hạ tầng có thể tự động mở rộng dựa trên tổng tải, giảm phần tài nguyên phải dự phòng riêng cho từng tenant.

**Hạn chế:**

- Sai sót trong kiểm tra tenant có thể gây rò rỉ dữ liệu giữa khách hàng.
- Một tenant tạo nhiều tải hoặc dữ liệu có thể làm chậm các tenant khác nếu thiếu hạn mức.
- Nhiều tenant chịu ảnh hưởng chung khi ứng dụng hoặc tài nguyên dùng chung gặp sự cố.
- Cần đo lường, phân bổ chi phí và quản lý vòng đời dữ liệu **theo tenant**, dù hạ tầng là chung.

Pool phù hợp khi có nhiều tenant với hành vi tương đối giống nhau, yêu cầu cô lập logic được chấp nhận và nhóm có năng lực xây dựng cơ chế bảo vệ đa tenant chặt chẽ.

### 2.3. Bridge: kết hợp thành phần chung và thành phần riêng

~~~mermaid
flowchart LR
    A["Tenant tiêu chuẩn"] --> GW["Gateway + định danh chung"]
    B["Tenant doanh nghiệp"] --> GW
    GW --> S["Ứng dụng dùng chung"]
    S --> PD[("Database pool\ncác tenant tiêu chuẩn")]
    S --> DD[("Database riêng\nTenant doanh nghiệp")]
    B -. "Nếu cần cô lập mạnh hơn" .-> D["Ứng dụng / VPC riêng"]
    D --> DD
~~~

**Bridge** kết hợp pool và silo. Ví dụ: phần đăng nhập, billing và catalog dùng chung; dữ liệu giao dịch của tenant doanh nghiệp nằm ở database riêng. Với tenant có yêu cầu rất chặt, cả lớp compute, mạng và cơ sở dữ liệu có thể tách khỏi pool.

Bridge cho phép phân tầng dịch vụ, nhưng cũng tăng gánh nặng định tuyến, provisioning, phân quyền, schema version và quản lý nhiều kiểu triển khai. Cần làm rõ **phần nào vẫn chung**, vì một database riêng chưa đủ đáp ứng yêu cầu “không dùng chung compute” nếu ứng dụng vẫn chạy trong pool.

### 2.4. Bảng so sánh nhanh

| Tiêu chí | Silo (riêng) | Pool (chung) | Bridge (lai) |
| --- | --- | --- | --- |
| Phạm vi cô lập | Có thể cao nếu tách compute, mạng, dữ liệu và quyền | Phần lớn là cô lập logic; cần thiết kế thực thi ở nhiều lớp | Tùy dịch vụ và nhóm tenant |
| Chi phí cố định/tenant | Thường cao | Thường thấp khi số tenant tăng | Trung gian; có chi phí hỗ trợ nhiều mô hình |
| Phát hành phần mềm | Nhiều môi trường, cần quản lý phiên bản | Một hoặc ít cụm chung | Nhiều luồng phát hành cần phối hợp |
| Độ phức tạp theo quy mô | Tăng theo số môi trường | Tăng theo mức tinh vi của kiểm soát tenant | Tăng vì có cả hai loại cơ chế |
| Sự cố ảnh hưởng chéo | Có thể giới hạn tốt nếu cô lập đủ sâu | Blast radius của phần chung lớn hơn | Phụ thuộc ranh giới tài nguyên |
| Tùy biến từng khách hàng | Tương đối thuận tiện nhưng dễ phân nhánh | Nên ưu tiên cấu hình/feature flag an toàn | Tùy nhóm khách hàng |
| Phân bổ chi phí | Tương đối trực tiếp cho phần riêng | Cần chỉ số sử dụng và quy tắc phân bổ | Phải kết hợp hai cách |
| Khả năng di chuyển tenant | Phụ thuộc tự động hóa môi trường riêng | Cần công cụ tách dữ liệu một tenant | Cần luồng chuyển đổi giữa tier |

Các đặc tính trên là xu hướng, **không phải cam kết kỹ thuật tuyệt đối**. Ví dụ, một silo nằm chung cluster không tự động có blast radius nhỏ hơn pool chạy ở các cell tách biệt.

## 3. Chọn mức cô lập theo từng lớp kiến trúc

“Dùng chung hay riêng” là quyết định có nhiều chiều. Có thể thiết kế ma trận cô lập như sau:

| Lớp | Dùng chung / cô lập logic | Cô lập mạnh hơn | Câu hỏi thiết kế |
| --- | --- | --- | --- |
| **Định danh** | Một dịch vụ đăng nhập và chính sách tenant-aware | Identity realm/provider riêng nếu được yêu cầu | Ai xác nhận người dùng thuộc tenant nào? |
| **Mạng** | Chung VPC/VNet, kiểm soát luồng bằng policy | VPC/VNet hoặc cloud account riêng, kết nối có kiểm soát | Tenant có yêu cầu mạng riêng hay kiểm tra vùng dữ liệu không? |
| **Compute** | Chia sẻ service, pod, serverless runtime | Namespace, node pool, cluster hoặc deployment riêng | Giới hạn CPU, bộ nhớ, concurrency, autoscaling ở đâu? |
| **Dữ liệu** | Chung bảng có tenant ID và policy | Schema riêng, database riêng hoặc account dữ liệu riêng | Có thể chứng minh không truy cập chéo và phục hồi riêng không? |
| **Cache / queue** | Chung hạ tầng với key, partition và quota theo tenant | Instance/namespace/queue riêng | Một tenant có thể làm đầy cache hoặc nghẽn hàng đợi không? |
| **Khóa mã hóa** | Dùng chung dịch vụ KMS với chính sách chặt | Khóa riêng tenant, đôi khi tài khoản KMS riêng | Ai quản lý quyền, rotate, revoke và audit khóa? |
| **Giám sát / vận hành** | Chung nền tảng quan sát, gắn tenant ID | Dashboard, logging boundary, đội vận hành hoặc lịch nâng cấp riêng | Có tách được log, chi phí, sự cố và dữ liệu nhạy cảm không? |
| **Phục hồi** | Phục hồi cả pool hoặc cell | Backup, restore và RTO/RPO riêng tenant | Có khôi phục một tenant mà không ghi đè tenant khác không? |

Mức cô lập là **một phổ**, từ nhiều tenant chung một process tới từng tenant có cloud account, VPC, compute và dữ liệu riêng. Quyết định cần gắn với tài sản cần bảo vệ và **mối đe dọa cụ thể**. Tách database không giải quyết được vấn đề API gửi nhầm dữ liệu hoặc log chứa thông tin tenant khác.

### Cô lập vật lý và cô lập logic

- **Cô lập vật lý/hạ tầng**: phân tách tài nguyên hoặc miền quản trị, giảm một số loại ảnh hưởng chéo, nhưng vẫn cần IAM, cấu hình đúng và kiểm soát đường truy cập.
- **Cô lập logic**: nhiều tenant chia sẻ tài nguyên, ứng dụng và nền tảng dữ liệu dùng identity, policy, chỉ mục và hạn mức để giữ ranh giới.
- **Không có một mức cô lập tốt nhất cho mọi tenant.** Quyết định phụ thuộc dữ liệu, SLA, lưu lượng, hợp đồng, chi phí và năng lực vận hành.

## 4. Những lựa chọn quan trọng ở tầng dữ liệu

Có ba cách thường gặp khi các tenant cần cùng một mô hình dữ liệu:

| Chiến lược | Tổ chức dữ liệu | Điểm mạnh | Rủi ro/công việc |
| --- | --- | --- | --- |
| **Shared tables + tenant_id** | Một bảng chứa bản ghi nhiều tenant | Dùng chung tài nguyên tốt; một schema để di trú | Mọi truy vấn/ủy quyền phải giữ đúng ranh giới; tạo chỉ mục và unique key có tenant |
| **Schema per tenant** | Mỗi tenant một schema trong DB dùng chung | Tách namespace và di trú có thể chia nhóm | Nhiều schema, công cụ migration/connection phức tạp; vẫn chung tài nguyên DB |
| **Database per tenant** | Database riêng, có thể cùng server/cluster | Dễ quản lý một phần backup và quyền theo tenant | Số lượng kết nối, migration, chi phí và vận hành tăng; chia sẻ server vẫn chia sẻ CPU/IO |

**Database riêng chưa chắc là môi trường hoàn toàn riêng:** nhiều database có thể cùng một máy chủ DB hoặc cụm quản lý. Ngược lại, một database dùng chung có thể đáp ứng yêu cầu của một số hệ thống nếu cô lập logic, kiểm thử và kiểm soát quyền được thực hiện tốt.

Với dữ liệu chung bảng, thông thường phải:

1. Lưu **tenant_id bất biến** trên mọi bản ghi nghiệp vụ chịu phạm vi tenant; mọi unique constraint/foreign key liên quan phải xem xét tenant để tránh tham chiếu chéo.
2. Xác thực **quyền thành viên tenant** trước khi query; tenant ID không được lấy từ header hoặc tham số tùy ý rồi tin tưởng trực tiếp.
3. Áp dụng cơ chế bảo vệ **ở tầng dữ liệu** (ví dụ row-level security khi DB hỗ trợ) bên cạnh kiểm tra ở API/service.
4. Gắn tenant vào key cache, khóa lưu trữ object, sự kiện, job bất đồng bộ và luồng search/index.
5. Thử các đường đọc/ghi ít gặp: báo cáo, export, background job, webhook, công cụ hỗ trợ khách hàng và truy vấn vận hành.

### Ví dụ triển khai PostgreSQL Row-Level Security (RLS)

Đoạn SQL minh họa ý tưởng **phòng vệ nhiều lớp** khi dùng bảng chung. Đây không phải cấu hình hoàn chỉnh cho production.

~~~sql
CREATE TABLE bookings (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    booking_code TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (tenant_id, booking_code)
);

-- app_role là vai trò ứng dụng đã được cấp quyền phù hợp.
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_bookings_policy
ON bookings
FOR ALL
TO app_role
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
~~~

Trong ứng dụng, sau khi **xác thực danh tính và kiểm tra user thuộc tenant**, backend gắn ngữ cảnh tenant vào **mỗi transaction** và chỉ sau đó chạy các câu lệnh nghiệp vụ:

~~~sql
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
SELECT id, booking_code, status FROM bookings;
COMMIT;
~~~

**Điều kiện an toàn cần lưu ý:**

- Giá trị tenant ID phải do backend xác lập từ danh tính đã xác thực và quyền thành viên, không phải dữ liệu đầu vào do client tự khai.
- Role của ứng dụng không được có quyền superuser hoặc BYPASSRLS. Owner có các ngoại lệ nếu không thiết lập FORCE RLS; tác vụ quản trị/migration cần quy trình riêng.
- SET LOCAL chỉ có hiệu lực trong transaction, giúp tránh lưu sót tenant context giữa các request dùng chung connection. Phải kiểm tra hành vi với connection pool, transaction pooling và ORM đang sử dụng.
- Biến cấu hình tùy chỉnh như app.tenant_id có thể bị ứng dụng thay đổi; RLS **không thay thế** phòng chống SQL injection hoặc hệ thống xác thực/ủy quyền.
- Truy vấn, quyền SELECT/INSERT/UPDATE/DELETE, liên kết bảng, khóa ngoại, import/export, dữ liệu log và các job nền vẫn cần kiểm thử độc lập.
- Thiếu tenant context cần dẫn đến **từ chối truy cập mặc định**; không thiết kế lối đi “tenant trống nghĩa là toàn bộ dữ liệu”.

## 5. Bảo mật: bảo vệ ranh giới tenant từ đầu đến cuối

Nguy cơ lớn nhất ở mô hình shared là **cross-tenant access**, tức một request, job hay cấu hình của tenant A chạm vào dữ liệu hoặc tài nguyên của tenant B. Việc gắn tenant_id vào bảng chỉ giải quyết một phần vấn đề.

Một luồng truy cập đáng tin cậy:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant I as Identity Provider
    participant G as Gateway / API
    participant S as Tenant-aware Service
    participant D as Database
    U->>I: Đăng nhập
    I-->>U: Token/phiên xác thực
    U->>G: Yêu cầu kèm token
    G->>G: Xác minh chữ ký, hạn dùng, audience
    G->>S: Danh tính đã xác thực
    S->>S: Kiểm tra tư cách thành viên và quyền trong tenant
    S->>D: Truy vấn với tenant context + policy
    D-->>S: Chỉ dữ liệu được phép
    S-->>U: Kết quả
~~~

Các kiểm soát tối thiểu cần xem xét:

- **Authentication ≠ authorization.** Đăng nhập hợp lệ chưa đồng nghĩa có quyền trên tenant đang được chọn; người dùng nhiều tenant phải được kiểm tra quyền cho từng tenant.
- **Tenant context phải được truyền tin cậy** qua API, worker, message queue, webhook và công cụ quản trị. Không coi một tenant ID trong request hoặc đường dẫn là bằng chứng quyền truy cập.
- **Least privilege** cho service identity, cloud IAM, database role và quyền support; quản lý truy cập đặc quyền và audit.
- **Mã hóa dữ liệu** trên đường truyền và khi lưu; quản lý key, secret và chứng chỉ theo chính sách. Khóa riêng tenant là một lựa chọn tăng mức cô lập, đồng thời phát sinh chi phí/quy trình vận hành.
- **Kiểm soát dữ liệu sao chép:** backup, replica, object storage, log, tracing, analytics và công cụ bên thứ ba phải tuân thủ phạm vi vùng dữ liệu và chính sách lưu giữ.
- **Kiểm thử tấn công ngang tenant:** thử đọc, sửa, xóa và dò ID thuộc tenant khác; kiểm tra cache poisoning, truy cập object, đường export và job nền.
- **Quản trị hoạt động support:** phiên hỗ trợ khách hàng phải có ủy quyền rõ, thời hạn, ghi log và tránh dùng khóa/role toàn quyền trong xử lý thường ngày.

Đối với khách hàng đòi hỏi **dedicated deployment**, cần xác định chính xác hợp đồng mong đợi: “database riêng”, “compute riêng”, “không cùng mạng”, “cloud account riêng”, “không có nhân sự vận hành chung”, hay “vùng lưu trữ riêng” là các yêu cầu khác nhau.

## 6. Hiệu năng, noisy neighbor và độ tin cậy

### 6.1. Noisy neighbor là gì?

Một tenant nhập 10 triệu bản ghi hoặc chạy báo cáo nặng khiến CPU, IOPS, connection pool, hàng đợi hoặc quota dịch vụ chung bị chiếm dụng. Khi đó, request của tenant khác bị chậm dù họ không tăng lưu lượng. Đây là hiện tượng **noisy neighbor**.

Biện pháp thường dùng:

- Giới hạn **requests/giây, concurrency, dung lượng, thời gian xử lý và số job** theo tenant hoặc gói dịch vụ.
- Có **fair scheduling**, queue partition, circuit breaker, bulkhead và backpressure để tránh một tenant nuốt hết năng lực chung.
- Đặt hạn mức DB connection/statement timeout, kiểm soát truy vấn nặng, index theo mẫu truy cập có tenant; tách job analytics khỏi giao dịch trực tuyến.
- Autoscaling dựa trên tổng tải **và** tín hiệu nghẽn thực (latency, queue age, saturation); tăng số pod không tự giải quyết nghẽn database chung.
- Chuyển tenant có tải lớn sang cell/cluster riêng khi bài toán kinh tế và vận hành chứng minh cần thiết.

### 6.2. Blast radius và cell-based architecture

Mô hình shared có thể giảm phạm vi ảnh hưởng bằng cách chia thành các **cell**: mỗi cell phục vụ một nhóm tenant với cụm ứng dụng và dữ liệu riêng; dịch vụ điều khiển có thể dùng chung.

~~~mermaid
flowchart TB
    GW["Tenant Router / Control Plane"] --> C1["Cell 1: nhóm tenant A"]
    GW --> C2["Cell 2: nhóm tenant B"]
    GW --> C3["Cell 3: nhóm tenant C"]
    C1 --> D1[("Data 1")]
    C2 --> D2[("Data 2")]
    C3 --> D3[("Data 3")]
~~~

Cell giúp giới hạn sự cố của ứng dụng và dữ liệu trong một nhóm tenant; tuy nhiên các thành phần còn chung, như identity, DNS, control plane hoặc billing, vẫn có thể trở thành điểm lỗi chung. Việc phân cell phải đi kèm **khả năng phục hồi, định tuyến và vận hành** thực tế, không chỉ là chia nhãn.

### 6.3. SLO, SLA, RTO và RPO theo tenant

- **SLI:** đại lượng đo thực tế, ví dụ tỷ lệ request hợp lệ được trả thành công trong thời gian mục tiêu.
- **SLO:** mục tiêu chất lượng nội bộ đã thỏa thuận, ví dụ p95 độ trễ hoặc tỷ lệ request thành công trong một kỳ.
- **SLA:** cam kết theo hợp đồng; cần làm rõ điều kiện tính và ngoại lệ.
- **RTO:** thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố.
- **RPO:** lượng dữ liệu tối đa chấp nhận mất, tính theo thời gian.

Một pool phục vụ nhiều gói khách hàng có thể có SLO khác nhau, nhưng chỉ có tuyên bố SLO **khi kiến trúc và phép đo thực sự hỗ trợ sự khác biệt đó**. Nếu cùng phụ thuộc vào một database chung, việc hứa RTO “5 phút riêng tenant A” trong khi thiếu quy trình khôi phục riêng sẽ không đáng tin cậy.

**Bài toán phục hồi dữ liệu theo tenant:** restore một bản backup toàn bộ database chung có thể ghi đè dữ liệu của tenant khác. Hệ thống cần thiết kế cách khôi phục chọn lọc (logical export, point-in-time recovery sang môi trường tạm, lọc bản ghi theo tenant, đối soát khóa ngoại và sự kiện phát sinh) và kiểm thử quy trình. Silo cũng phải kiểm thử backup/restore và failover, không tự động đạt RTO/RPO chỉ vì tách môi trường.

## 7. Phân tích chi phí và khả năng mở rộng

Đánh giá chỉ bằng giá một máy ảo thường dẫn đến kết luận sai. Tổng chi phí sở hữu (TCO) cần tính compute, database, storage, backup, truyền dữ liệu, quan sát, bảo mật, license, công vận hành, triển khai, DR và hỗ trợ.

Có thể dùng mô hình sơ bộ:

\[
C_{\text{silo}} \approx \sum_{i=1}^{N}(F_i+V_i+O_i)
\]

\[
C_{\text{pool}} \approx F_{\text{platform}}+\sum_{i=1}^{N}V_i+O_{\text{shared}}+I
\]

Trong đó:

- \(N\): số tenant.
- \(F_i\): chi phí cố định cho mỗi tenant riêng (compute tối thiểu, DB, nền tảng).
- \(V_i\): chi phí biến đổi theo tải/dung lượng tenant.
- \(O_i\): chi phí vận hành/triển khai riêng.
- \(F_{\text{platform}}\): chi phí cố định của nền tảng dùng chung.
- \(O_{\text{shared}}\): vận hành pool.
- \(I\): chi phí thực thi và kiểm chứng cô lập tenant (policy, đo lường, kiểm thử, kiểm toán, quản trị).

**Ví dụ minh họa, không phải báo giá cloud:** 20 tenant có tải tương đối nhỏ.

| Khoản mục | Silo (giả định) | Pool (giả định) |
| --- | ---: | ---: |
| Tài nguyên cố định | 20 × 100 = 2.000 USD | 900 USD |
| Chi phí theo tải | 20 × 30 = 600 USD | 20 × 30 = 600 USD |
| Vận hành và kiểm soát cô lập | 20 × 40 = 800 USD | 650 USD |
| **Tổng/tháng** | **3.400 USD** | **2.150 USD** |

Trong giả định này, pool tiết kiệm **1.250 USD/tháng**. Tuy nhiên kết luận có thể đảo chiều nếu pool cần triển khai nhiều cell, DB mạnh hơn, nhiều vùng dữ liệu, hỗ trợ compliance phức tạp hoặc cần xử lý sự cố ảnh hưởng nhiều tenant. Với silo, khả năng dùng chung CI/CD, logging và provisioning cũng làm giảm chi phí vận hành so với ước tính thô.

### Những biến số cần đưa vào mô hình TCO

1. **Phân bố tải:** tổng lưu lượng chưa đủ; cần biết tải đỉnh đồng thời và mức chênh lệch giữa các tenant.
2. **Tăng trưởng dữ liệu:** kích thước dữ liệu, số kết nối, số chỉ mục, thời gian lưu trữ, tốc độ backup/restore.
3. **Bậc dịch vụ:** tenant cao cấp có quota, SLO, vùng dữ liệu hay khả năng mở rộng riêng?
4. **Dự phòng và vận hành:** chi phí môi trường dự phòng, diễn tập DR, nhật ký bảo mật, audit và trực sự cố.
5. **Độ phức tạp phát triển:** một lỗi cô lập tenant có thể có chi phí khắc phục lớn hơn phần tiền tiết kiệm hạ tầng.
6. **Độ nhạy dữ liệu:** những yêu cầu không thể thương lượng phải được kiểm tra **trước** khi tối ưu ngân sách.

Đừng dùng “chi phí trên mỗi tenant” như chỉ số duy nhất. Nên đo cả **chi phí trên một giao dịch hợp lệ**, mức sử dụng tài nguyên, biên lợi nhuận theo gói và chi phí hỗ trợ/vận hành để tránh tối ưu sai.

## 8. Vòng đời tenant và các quy trình vận hành

### 8.1. Onboarding và provisioning

Một tenant mới cần được tạo **tenant ID ổn định**, gói dịch vụ, quyền và chính sách lưu trú dữ liệu; sau đó ánh xạ tới môi trường, cell hoặc database phù hợp.

~~~mermaid
flowchart LR
    A["Khách hàng đăng ký"] --> B["Tạo tenant ID và chính sách"]
    B --> C{"Gói / điều kiện cô lập"}
    C -- "Pool" --> D["Gán cell + tạo dữ liệu/cấu hình"]
    C -- "Dedicated" --> E["Tạo môi trường bằng IaC"]
    D --> F["Cấu hình IAM, quota, key và logging"]
    E --> F
    F --> G["Kiểm tra quyền, dữ liệu và health"]
    G --> H["Kích hoạt tenant"]
~~~

**Control plane** quản lý metadata tenant, provisioning, entitlement, định tuyến, billing và vận hành; **data plane** phục vụ lưu lượng nghiệp vụ và dữ liệu tenant. Tách rõ hai trách nhiệm giúp triển khai pool, silo và bridge thống nhất. Tuy nhiên control plane dùng chung vẫn cần bảo vệ, HA và kế hoạch khôi phục vì nó có thể ảnh hưởng nhiều tenant.

### 8.2. Phát hành và migration schema

- Với **pool**, một migration database có thể ảnh hưởng nhiều tenant ngay lúc triển khai. Cần migration tương thích ngược, phát hành theo giai đoạn, kiểm soát tải và rollback ứng dụng phù hợp.
- Với **silo**, mỗi tenant có thể ở một phiên bản khác nhau. Cần tự động hóa kiểm tra phiên bản, migration từng nhóm, cập nhật bảo mật và tránh phụ thuộc vào thao tác thủ công.
- Với **bridge**, phải hỗ trợ đa dạng schema/database khi phát hành; tránh buộc đường code nghiệp vụ phải phân nhánh theo từng khách hàng không kiểm soát.

Một chuỗi phát hành an toàn thường là **expand → deploy → migrate data (nếu cần) → contract**: bổ sung schema tương thích trước, triển khai code đọc/ghi tương thích, chuyển dữ liệu có quan sát, rồi mới xóa cấu trúc cũ khi không còn bên dùng. Mọi bước vẫn cần kế hoạch khôi phục thực tế.

### 8.3. Theo dõi và chargeback/showback

Thu thập các chỉ số theo tenant (và theo cell/deployment): request count, error rate, p50/p95/p99 latency, quota usage, DB size, queue lag, cost allocation, tỷ lệ lỗi backup và thời gian xử lý sự cố. Chỉ số phải được **gắn nhãn kiểm soát cardinality**, vì đưa mọi tenant ID lên mọi metric label có thể làm bùng chi phí hệ thống monitoring. Các chi tiết truy vết có tenant ID cần bảo vệ theo chính sách log.

- **Showback:** báo cáo mức sử dụng/chi phí để các bên hiểu.
- **Chargeback:** phân bổ hoặc tính phí cho tenant/đơn vị dựa trên quy tắc được phê duyệt.
- Các khoản chi phí chung cần có cách phân bổ minh bạch: theo giao dịch, dung lượng, phần tài nguyên dự trữ hay mức hỗ trợ.

### 8.4. Chấm dứt hợp đồng, xóa và xuất dữ liệu

Offboarding cần xác minh quyền yêu cầu, xuất dữ liệu theo phạm vi hợp đồng, thu hồi quyền truy cập/token/key, dừng job/webhook, xử lý dữ liệu đang chờ trong queue và xóa dữ liệu theo chính sách lưu giữ. Backup, bản sao, log và hệ thống bên thứ ba có vòng đời riêng nên phải được liệt kê, xử lý và lưu bằng chứng phù hợp; không thể chỉ chạy một lệnh DELETE rồi tuyên bố hoàn tất.

### 8.5. Khôi phục sau sự cố

Runbook phải nêu rõ sự cố ở tenant, cell hay thành phần chung; ai quyết định failover, khôi phục từ đâu, xác minh tính nhất quán thế nào, thời gian ước tính theo bài diễn tập, cách thông báo khách hàng và cơ chế quay về trạng thái thường. Với pool, kiểm thử khôi phục **một tenant** quan trọng không kém khôi phục toàn bộ ứng dụng.

## 9. Khung ra quyết định lựa chọn mô hình

### Bước 1: Thu thập yêu cầu và phân tách điều kiện bắt buộc

Hỏi trực tiếp các bên liên quan:

- **Kinh doanh/Product:** có bao nhiêu tenant hiện tại/tương lai, lưu lượng đỉnh, nhu cầu cá nhân hóa, mô hình giá, hạn ra mắt?
- **Bảo mật/pháp chế:** dữ liệu nào chịu ràng buộc, cần vùng lưu trú nào, điều kiện “dedicated” trong hợp đồng cụ thể là gì, ai có quyền truy cập?
- **SRE/vận hành:** SLO, RTO/RPO, tenant nào cần cửa sổ bảo trì riêng, số lượng môi trường đội có thể quản lý?
- **Tài chính:** ngân sách cố định/biến đổi, chi phí hỗ trợ khách hàng, yêu cầu dự báo/chargeback?
- **Kỹ thuật:** khả năng thiết kế tenant-aware, kiểm thử truy cập chéo, tự động hóa IaC, migrations, quan sát và quota?

Một yêu cầu bảo mật/hợp đồng có tính bắt buộc không thể bị loại chỉ vì phương án còn lại rẻ hơn. Nếu điều kiện bắt buộc xung đột ngân sách hoặc tiến độ, phải đưa ra quyết định cấp có thẩm quyền để đổi phạm vi, ngân sách hoặc kế hoạch.

### Bước 2: So sánh phương án theo tiêu chí đo được

| Câu hỏi | Tín hiệu nghiêng về silo | Tín hiệu nghiêng về pool | Tín hiệu nghiêng về bridge |
| --- | --- | --- | --- |
| Mức cô lập hợp đồng cần? | Compute/mạng/dữ liệu tách biệt rõ | Cô lập logic được chấp nhận và có bằng chứng | Nhiều phân khúc khách hàng |
| Số lượng và quy mô tenant? | Ít tenant lớn hoặc tải rất khác nhau | Nhiều tenant nhỏ, tải bổ sung cho nhau | Có cả tenant lớn và nhỏ |
| Khả năng tùy biến? | Mạnh, khác lịch nâng cấp | Chủ yếu cấu hình/feature flag | Gói doanh nghiệp tùy chọn thêm |
| Năng lực vận hành? | Có IaC và quản trị nhiều môi trường | Có tenant-aware security, quota, monitoring | Có thể quản lý hai hình thức và đường chuyển đổi |
| Yêu cầu vùng dữ liệu? | Mỗi tenant có vị trí riêng được phê duyệt | Các tenant dùng cùng vùng hợp lệ | Chia nhóm theo vùng/chính sách |
| Mục tiêu chi phí? | Chấp nhận phí cố định cao vì lợi ích khác | Ưu tiên dùng chung để giảm chi phí nhàn rỗi | Cân bằng theo phân khúc |

### Bước 3: Kiểm chứng bằng thử nghiệm

Các bài thử nên sát kịch bản rủi ro thực:

1. Thử **truy cập chéo tenant** qua API, DB, cache, object storage, search, export và job nền.
2. Tạo tải lớn cho một tenant, đo **p95/p99, error rate, saturation** của các tenant khác.
3. Cố tình làm lỗi một service/cell, quan sát **blast radius**, circuit breaker và phục hồi.
4. Diễn tập **restore tenant** (hoặc cả cell) và đo RTO/RPO thực tế.
5. Tạo nhiều tenant mới; đo thời gian onboarding, khả năng rollback, mức configuration drift.
6. Dự báo và đối chiếu TCO ở tải bình thường, đỉnh và khi kích hoạt DR.

### Bước 4: Ghi Architecture Decision Record (ADR)

~~~markdown
# ADR-021: Tenancy model cho nền tảng đặt chỗ

Trạng thái: Chấp thuận có điều kiện
Decision owner: Kiến trúc sư phụ trách + đại diện nghiệp vụ

Bối cảnh:
- 60 tenant nhỏ, 4 tenant doanh nghiệp có tải và chính sách riêng.
- Tenant nhỏ được phép dùng chung ứng dụng và dữ liệu có cô lập logic.
- Tenant doanh nghiệp yêu cầu database riêng; 1 khách hàng
  yêu cầu thêm compute và mạng riêng theo hợp đồng.
- Mục tiêu: giới hạn ảnh hưởng chéo, kiểm soát chi phí và vận hành.

Phương án:
A. Silo cho toàn bộ tenant.
B. Pool cho toàn bộ tenant.
C. Bridge: pool cho nhóm tiêu chuẩn; tách thành phần theo hợp đồng.

Quyết định:
- Chọn C, với tenant directory/định tuyến tập trung.
- Kiểm chứng an toàn truy cập chéo và giới hạn tải theo tenant.
- Không công bố đáp ứng SLA/RTO/RPO trước khi diễn tập.

Đánh đổi:
- Tăng độ phức tạp provisioning, routing và migration.
- Control plane và các dịch vụ dùng chung vẫn có thể ảnh hưởng rộng.

Điều kiện xem xét lại:
- Thay đổi chính sách dữ liệu; tải/chi phí vượt ngưỡng;
  yêu cầu cô lập mạnh hơn; thử nghiệm bảo mật hoặc DR không đạt.
~~~

## 10. Tình huống thực tế: nền tảng đặt chỗ B2B tăng trưởng

Giả sử một sản phẩm có **80 doanh nghiệp khách hàng**, mỗi doanh nghiệp có người dùng, lịch đặt chỗ và chính sách dữ liệu riêng:

- 70 tenant nhỏ: dưới 5 yêu cầu/giây trung bình; chủ yếu dùng những chức năng giống nhau.
- 8 tenant trung bình: nhiều tác vụ đồng bộ dữ liệu và báo cáo ngoài giờ.
- 2 tenant lớn: có hợp đồng yêu cầu database riêng; một trong hai còn yêu cầu compute/mạng riêng và khu vực lưu trữ dữ liệu được phê duyệt.
- Product muốn phát hành tính năng cho nhóm phổ thông mỗi tuần.
- SRE muốn giữ số môi trường phải vận hành ở mức có thể tự động hóa và thử khôi phục được.

### Phương án đánh giá

**Phương án A — Tất cả là silo:** đáp ứng nhu cầu tách nhiều lớp cho tenant lớn nhưng 70 môi trường nhỏ có thể tăng chi phí cố định, số pipeline/backup và công vận hành. Nếu đội thiếu IaC và tự động kiểm thử, độ ổn định có thể thấp hơn kỳ vọng.

**Phương án B — Tất cả là pool:** tận dụng tài nguyên tốt, triển khai nhanh cho 70 tenant nhỏ. Tuy nhiên không đáp ứng hợp đồng của những tenant yêu cầu database hoặc compute/mạng riêng; còn cần hạn mức để 8 tenant báo cáo nặng không làm chậm giao dịch trực tuyến.

**Phương án C — Bridge có phân tầng:** một pool/cell cho tenant nhỏ; nhóm có tải báo cáo cao dùng queue và quota riêng hoặc cell riêng; hai tenant lớn có dữ liệu riêng; tenant yêu cầu cô lập mạnh có cả compute, mạng và kiểm soát truy cập riêng. Control plane quản lý mapping tenant → cell/deployment và routing.

**Lựa chọn có điều kiện:** C có thể là điểm khởi đầu hợp lý **nếu** kiểm thử chứng minh cô lập dữ liệu, quota, định tuyến, đáp ứng SLO và DR; đồng thời ước lượng TCO nằm trong giới hạn đã phê duyệt. Nếu chi phí bridge hoặc độ phức tạp điều phối vượt năng lực đội, cần điều chỉnh phạm vi/gói dịch vụ hoặc phương án trước khi cam kết.

### Gợi ý cấu trúc vận hành

~~~text
Control plane chung
  ├─ Tenant directory, hợp đồng, gói dịch vụ
  ├─ Identity / access policy / cấu hình
  ├─ Provisioning / routing / billing / quan sát
  └─ Audit và quản lý thay đổi
           |
           v
Data plane
  ├─ Pool/Cell 1: nhiều tenant nhỏ
  │    ├─ App và worker chung + tenant-aware authorization
  │    └─ DB chung + cô lập tenant, quota, backup/restore
  ├─ Cell 2: tenant có workload nặng
  │    ├─ App / queue giới hạn tải
  │    └─ DB theo chính sách đã chọn
  └─ Silo: tenant yêu cầu cô lập mạnh
       ├─ Account/VPC/compute theo hợp đồng
       └─ DB, key, backup và runbook riêng
~~~

Điểm cần tránh: vẽ control plane như một thành phần “không cần dự phòng”. Đây thường là hệ thống quan trọng vì lỗi tenant directory hoặc routing có thể ảnh hưởng khả năng truy cập của nhiều tenant.

## 11. Chuyển tenant giữa pool và silo

Nhiều hệ thống bắt đầu với pool rồi tách một tenant lớn sang silo, hoặc hợp nhất môi trường riêng khi hợp đồng thay đổi. Việc chuyển đổi phải giữ tính toàn vẹn dữ liệu và khả năng khôi phục.

Một quy trình tham khảo:

1. **Xác định phạm vi tenant:** dữ liệu giao dịch, tệp, cache, search index, hàng đợi, secret, key, mapping identity, lịch sử audit và dữ liệu lưu ở hệ thống ngoài.
2. **Chuẩn bị đích:** tài nguyên compute/database, schema tương thích, quyền IAM, vùng dữ liệu và chính sách backup, quota, giám sát.
3. **Sao chép dữ liệu có kiểm soát:** export/snapshot và áp dụng thay đổi phát sinh (nếu cần) qua CDC hoặc cơ chế phù hợp; ghi rõ mốc đồng bộ.
4. **Đối soát:** so số bản ghi, checksum phù hợp, quan hệ dữ liệu, phân quyền, số dư giao dịch/đặt chỗ, lịch sử sự kiện; bảo đảm không lẫn dữ liệu tenant khác.
5. **Chuyển hướng có kiểm soát:** tạm dừng hoặc điều phối ghi, hoàn tất đồng bộ, cập nhật tenant routing rồi kiểm tra luồng nghiệp vụ.
6. **Theo dõi và quay lui:** giám sát lỗi/độ trễ, xác định tiêu chí rollback, người phê duyệt và cách xử lý nếu hai phía đã nhận ghi khác nhau.
7. **Kết thúc:** hủy quyền và thu hồi tài nguyên cũ sau thời gian giám sát/lưu giữ đã thỏa thuận; cập nhật runbook và ADR.

Không nên bật ghi đồng thời vào hai nơi như một lối tắt nếu chưa thiết kế giải quyết xung đột, idempotency và kiểm tra nhất quán. Di chuyển tenant là một **thay đổi kiến trúc và dữ liệu**, phải có kế hoạch rollback và thử trên dữ liệu đại diện.

## 12. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tưởng “riêng” nghĩa là an toàn tuyệt đối | IAM, backup, vận hành hoặc mạng vẫn có thể cấu hình sai | Xác định ranh giới cụ thể và kiểm chứng từng lớp |
| Chỉ thêm tenant_id vào bảng | API, cache, object, queue hoặc export vẫn có thể lộ dữ liệu | Tenant-aware authorization + data policy + kiểm thử end-to-end |
| Tin tenant ID từ client | Kẻ tấn công tự chọn tenant khác | Xác thực danh tính, kiểm tra membership và quyền trên backend |
| Không có quota | Noisy neighbor làm giảm SLO của cả pool | Giới hạn theo tenant, phân vùng queue, cell và fair scheduling |
| Một schema migration tác động mọi tenant | Thay đổi gây lỗi diện rộng | Migration tương thích ngược, canary, giám sát và rollback |
| Silo triển khai thủ công | Configuration drift, chậm vá lỗi, chi phí vận hành cao | IaC, pipeline chuẩn, inventory và tự động hóa |
| Hứa khôi phục tenant trong pool nhưng chỉ backup toàn DB | Không thể restore riêng mà không ảnh hưởng khách hàng khác | Thiết kế và diễn tập selective restore từ đầu |
| So chi phí chỉ bằng giá compute | Bỏ sót hỗ trợ, DR, truyền dữ liệu, security, vận hành | So TCO và chi phí theo giao dịch/tenant |
| Không ghi mapping tenant → deployment | Chuyển vùng hoặc migration có thể định tuyến sai | Tenant directory có kiểm soát quyền, log và quy trình cập nhật |
| Tách riêng từng tenant quá sớm hoặc dùng chung bằng mọi giá | Đánh đổi chi phí và độ phức tạp không dựa trên nhu cầu | Chọn theo điều kiện bắt buộc, số liệu đo và ngưỡng chuyển tier |

## 13. Bài tập thực hành

Một ứng dụng SaaS quản lý kho chạy trên cloud hiện phục vụ 30 khách hàng. Sáu tháng tới dự báo tăng lên 150 khách hàng. Hai khách hàng lớn muốn chạy báo cáo dữ liệu với tải cao; một khách hàng yêu cầu database riêng và vùng lưu trú dữ liệu cụ thể. Ngân sách phải được theo dõi theo từng gói dịch vụ. Đội kỹ thuật có ít người nhưng đã có CI/CD và cơ bản về IaC.

**Yêu cầu:**

1. Đặt ít nhất **sáu câu hỏi** để xác định ranh giới cô lập, tải, SLO, RTO/RPO, dữ liệu và chi phí; phân biệt điều đã xác nhận với giả định.
2. Phác thảo ba phương án **silo, pool và bridge**. Với mỗi phương án ghi các lớp dùng chung/riêng: gateway/identity, compute, network, DB, cache, queue, backup và monitoring.
3. Tạo **ma trận quyết định** với các tiêu chí: bảo mật, tuân thủ, hiệu năng cô lập tenant, chi phí, khả năng mở rộng và vận hành. Chỉ so sánh những phương án đáp ứng tất cả điều kiện bắt buộc.
4. Mô tả một kiểm thử **cross-tenant access** và một kiểm thử **noisy neighbor**; nêu chỉ số đầu ra và điều kiện đạt.
5. Xây dựng runbook rút gọn cho **onboarding**, **offboarding** và **restore dữ liệu một tenant**.
6. Viết ADR 10–15 dòng, nêu phương án được chọn, chủ sở hữu quyết định, đánh đổi, bằng chứng cần kiểm chứng và thời điểm xem xét lại.

**Tiêu chí tự đánh giá:** giải pháp tốt phải mô tả ranh giới kỹ thuật chính xác, chứng minh cô lập bằng kiểm thử, dự báo TCO có đủ yếu tố vận hành và cung cấp đường nâng cấp/migration khi phân khúc khách hàng thay đổi.

## 14. Checklist trước khi chốt kiến trúc

- [ ] Xác định tenant là đơn vị gì; ai được phép chuyển tenant hoặc phục vụ nhiều tenant.
- [ ] Ghi rõ thành phần **chung/riêng** ở từng lớp: mạng, compute, dữ liệu, cache, queue, key và vận hành.
- [ ] Xác nhận các ràng buộc hợp đồng, pháp lý, vùng dữ liệu và điều kiện bắt buộc.
- [ ] Thiết kế xác thực, ủy quyền, tenant context và data isolation theo nguyên tắc từ chối mặc định.
- [ ] Có phép thử truy cập chéo, quota/noisy neighbor, lỗi thành phần và blast radius.
- [ ] Có SLI/SLO, RTO/RPO và bằng chứng diễn tập phù hợp phạm vi cam kết.
- [ ] Dự tính TCO gồm tăng trưởng, tải đỉnh, backup, truyền dữ liệu, hỗ trợ và vận hành.
- [ ] Có tự động provisioning, inventory, migration schema, audit và offboarding.
- [ ] Có phương án khôi phục riêng tenant hoặc mô tả giới hạn đã được phê duyệt.
- [ ] Có ADR với người chịu trách nhiệm, rủi ro còn lại và điều kiện đánh giá lại.

## Ghi nhớ

**Triển khai riêng** ưu tiên khả năng phân tách tài nguyên và kiểm soát theo khách hàng, đổi lại thường tăng chi phí cố định và công vận hành. **Triển khai dùng chung** khai thác tài nguyên hiệu quả và phát hành thuận tiện, đổi lại đòi hỏi cơ chế cô lập tenant vững chắc, hạn mức và kiểm thử ảnh hưởng chéo. **Bridge** cho phép kết hợp hai cách theo phân khúc khách hàng, nhưng cần điều phối và tự động hóa có chủ đích.

Quyết định tốt không bắt đầu từ tên mô hình, mà từ **yêu cầu nghiệp vụ và ràng buộc → mức cô lập cần thiết → thiết kế mạng/compute/dữ liệu → đo SLO và TCO → kiểm chứng bảo mật, độ tin cậy và vận hành**. Xem xét lại quyết định khi số tenant, tải, hợp đồng hoặc bằng chứng thực tế thay đổi.
