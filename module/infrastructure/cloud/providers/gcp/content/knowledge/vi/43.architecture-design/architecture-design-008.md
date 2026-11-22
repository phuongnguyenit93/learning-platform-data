# Thiết kế đa người thuê và cô lập dữ liệu trên GCP

## 1. Mục tiêu và bài toán

Trong một hệ thống **Software as a Service (SaaS)**, nhiều khách hàng sử dụng cùng sản phẩm nhưng dữ liệu, cấu hình, quyền truy cập và tài nguyên của từng khách hàng phải được phân tách đúng mức. Mỗi khách hàng hoặc đơn vị được phục vụ gọi là một **tenant** (người thuê). Tenant có thể là một doanh nghiệp, một phòng ban hoặc một tổ chức; một tenant thường có nhiều người dùng, nhiều nhóm quyền và nhiều tập dữ liệu.

Ví dụ, nền tảng quản lý hóa đơn phục vụ ba công ty A, B và C. Nhân viên công ty A có thể xem các hóa đơn được cấp quyền trong A nhưng không được đọc hóa đơn, tệp đính kèm, báo cáo, cache hay log chứa dữ liệu của B. Nếu A đột ngột tải lên hàng triệu tệp, mức tiêu thụ tài nguyên của A cũng không được khiến B ngừng hoạt động ngoài mức đã thỏa thuận.

**Cô lập đa người thuê (multi-tenant isolation)** bao gồm nhiều thuộc tính: bảo mật dữ liệu, giới hạn tài nguyên, quản lý danh tính, mạng, khóa mã hóa, vận hành và khôi phục. Chỉ thêm một cột tenant_id vào bảng dữ liệu là chưa tạo ra hệ thống cô lập an toàn.

Bài này nằm trong chương **Thiết kế kiến trúc GCP** của mô-đun **CLOUD_PROVIDERS_GCP**. Người học vận dụng tổ chức project, IAM, VPC, Cloud Run, GKE, dịch vụ lưu trữ/cơ sở dữ liệu, tự động hóa phát hành, theo dõi độ tin cậy và chi phí để lựa chọn mức cô lập phù hợp cho ứng dụng thực tế.

Sau bài học, người học có thể:

1. Phân biệt mô hình tài nguyên dùng chung, tài nguyên riêng và kiến trúc kết hợp.
2. Xác định ranh giới tenant cho xác thực, phân quyền, xử lý yêu cầu, dữ liệu và tác vụ nền.
3. Thiết kế cô lập bằng project, service account, Cloud Run/GKE, Cloud Storage, Cloud SQL, Spanner, Firestore và BigQuery.
4. Giảm rủi ro truy cập chéo tenant, rò rỉ dữ liệu qua cache, log, backup và tác vụ bất đồng bộ.
5. Đề xuất tiêu chí đo lường, kiểm thử và vận hành trong toàn bộ vòng đời tenant.

## 2. Hiểu đúng khái niệm tenant và ranh giới tin cậy

**Tenant** là một đơn vị có dữ liệu và chính sách truy cập riêng. **User** là người dùng hoặc dịch vụ thuộc một hay nhiều tenant. Một user được quyền tham gia hai tenant không có nghĩa hai tenant được chia sẻ dữ liệu. **Tenant identity**, **user identity**, **runtime identity** và **Google Cloud project identity** là bốn khái niệm khác nhau:

| Danh tính | Ví dụ | Dùng để |
| --- | --- | --- |
| Tenant | tenant-acme | Chỉ định tổ chức và phạm vi dữ liệu nghiệp vụ |
| Người dùng | user-123 | Xác thực người thao tác, kiểm tra membership/role |
| Workload | service account của Cloud Run | Gọi API GCP và tài nguyên được IAM cho phép |
| Project | saas-prod-acme | Quản lý ranh giới IAM, quota, API, billing và tài nguyên GCP |

Các lỗi thường gặp bắt đầu khi hệ thống gộp nhầm các danh tính này. Chẳng hạn, một Cloud Run service chạy bằng cùng service account cho mọi tenant có thể được IAM cho phép đọc cả bucket A và B. Khi đó Google Cloud chỉ biết **service account** đang đọc; lớp ứng dụng phải bảo đảm yêu cầu của A không được chọn đường dẫn B. Không thể kỳ vọng IAM tự hiểu tenant_id xuất hiện trong request HTTP.

### Phân loại tác nhân và tình huống bị đe dọa

- **Người dùng hợp lệ nhưng tò mò:** thay mã tenant hoặc document ID trong URL để xem dữ liệu khách hàng khác.
- **Lỗi ứng dụng:** quên mệnh đề tenant_id trong truy vấn, ghi nhầm bucket, dùng cache key thiếu tenant.
- **Tài khoản dịch vụ bị xâm phạm:** token của workload có quyền rộng nên đọc được dữ liệu nhiều tenant.
- **Tenant tạo tải lớn:** sử dụng hết connection pool, CPU, quota API hoặc hàng đợi.
- **Nhân viên vận hành có quyền cao:** thao tác debug hoặc restore nhầm tenant, xuất dữ liệu ngoài phạm vi công việc.
- **Tác vụ nền:** job chạy lại hoặc event thiếu thông tin tenant nên ghi sai phân vùng.
- **Bản sao dữ liệu:** backup, snapshot, file xuất, BigQuery analytical copy hoặc log chứa dữ liệu chưa được kiểm soát.

**Nguyên tắc thiết kế:** mặc định từ chối truy cập khi không xác định được tenant đáng tin cậy. Kiểm tra tenant ở ranh giới vào và duy trì ràng buộc ở từng lớp xử lý, lưu trữ, xuất dữ liệu và quản trị.

## 3. Ba mô hình kiến trúc phổ biến

### 3.1 Pool — tài nguyên dùng chung

Mọi tenant dùng chung một hoặc nhiều dịch vụ Cloud Run/GKE, bộ nhớ cache, cơ sở dữ liệu và bucket. Dữ liệu được phân chia logic bằng tenant_id, collection, schema, partition hoặc object prefix tùy sản phẩm.

**Ưu điểm:** tận dụng tài nguyên tốt, onboarding nhanh, quản lý nâng cấp tập trung, chi phí cố định trên mỗi tenant có thể thấp.

**Đánh đổi:** cần phân quyền ở tầng ứng dụng/dữ liệu rất chặt; phạm vi ảnh hưởng khi lỗi lớn; một tenant có thể làm cạn tài nguyên chung; backup/restore riêng từng tenant khó hơn.

### 3.2 Silo — tài nguyên riêng cho từng tenant

Mỗi tenant được cấp ít nhất một tập tài nguyên riêng, có thể là project GCP, VPC, Cloud Run service, database, bucket, service account và Cloud KMS key riêng. Đường đi dữ liệu không đi qua bộ nhớ hoặc tài khoản dịch vụ chung có quyền tới tất cả tenant, trừ thành phần điều phối có kiểm soát.

**Ưu điểm:** ranh giới IAM và tài nguyên rõ hơn, dễ hạn chế tác động của sự cố, tùy chỉnh vị trí dữ liệu, chính sách bảo mật, phiên bản và chi phí từng tenant.

**Đánh đổi:** chi phí nền lớn hơn, phát sinh giới hạn về project/quota, yêu cầu tự động hóa tạo/xóa tài nguyên, phát hành và theo dõi nhiều môi trường.

### 3.3 Bridge (hybrid) — kiến trúc kết hợp

Một số thành phần như đăng nhập, định tuyến và giao diện API được dùng chung; dữ liệu và workload nhạy cảm hoặc tenant có hợp đồng đặc biệt được đặt trong project/database/bucket riêng.

**Ví dụ:** 500 tenant gói Standard dùng chung compute và database có kiểm soát bằng tenant_id; 10 tenant Enterprise có project và database riêng nhưng vẫn dùng chung control plane để đăng ký, quản lý gói dịch vụ và định tuyến.

| Tiêu chí | Pool | Silo | Bridge |
| --- | --- | --- | --- |
| Ranh giới dữ liệu | Chủ yếu ở ứng dụng, truy vấn, policy | Tài nguyên và IAM riêng | Theo từng thành phần |
| Chi phí nền/tenant | Thường thấp | Thường cao hơn | Có thể tối ưu theo gói |
| Khả năng custom theo tenant | Hạn chế hơn | Cao | Linh hoạt |
| Nguy cơ noisy neighbor | Cần điều tiết chặt | Giảm nhờ tách tài nguyên | Tùy phần được tách |
| Onboarding | Đơn giản hơn | Cần provisioning tự động | Phức tạp trung bình/cao |
| Audit và restore tenant | Cần thiết kế riêng | Thường rõ ràng hơn | Phụ thuộc ranh giới từng dữ liệu |
| Phù hợp | Nhiều khách hàng nhỏ, tải tương đồng | Yêu cầu cô lập mạnh, dữ liệu nhạy cảm | Sản phẩm nhiều cấp dịch vụ |

**Không có mô hình mặc định an toàn cho mọi trường hợp.** Mức cô lập phải dựa trên phân loại dữ liệu, tiêu chuẩn tuân thủ, hợp đồng, RTO/RPO, số tenant, SLO, mô hình tin cậy và chi phí.

## 4. Mô hình tham chiếu: control plane và data plane

~~~mermaid
flowchart TD
    U["Người dùng tenant A / B"] --> G["HTTPS / API gateway / Load balancer"]
    G --> ID["Xác thực token và phân quyền tenant"]
    ID --> CAT[("Tenant catalog: trạng thái, membership, resource mapping")]
    ID --> RT["Router theo tenant đã được xác minh"]
    RT --> SH["Shared application tier (Pool)"]
    RT --> A["Dedicated workload - tenant A (Silo)"]
    RT --> B["Dedicated workload - tenant B (Silo)"]
    SH --> DB[("Shared DB: tenant_id + kiểm soát truy cập")]
    SH --> OBJ[("Shared bucket: managed folder / object key theo tenant")]
    A --> DA[("Database + bucket + IAM của tenant A")]
    B --> DBB[("Database + bucket + IAM của tenant B")]
    CAT -.-> O["Provisioning / policy / billing / offboarding"]
    O -.-> A
    O -.-> B
~~~

**Control plane** giữ metadata quản lý tenant: mã tenant, trạng thái, gói dịch vụ, chủ dữ liệu, vùng lưu trữ, ánh xạ tới project/database/bucket, giới hạn tài nguyên, version và sự kiện vòng đời. Control plane nên lưu **metadata tối thiểu**, không tùy tiện tập trung toàn bộ nội dung nghiệp vụ từ các tenant riêng.

**Data plane** là nơi xử lý request, đọc ghi dữ liệu, chạy tác vụ nền và trả kết quả cho tenant. Nó phải tuân theo tenant context mà control plane và dịch vụ xác thực cho phép.

Một bản ghi tenant catalog minh họa:

~~~yaml
tenant_id: tenant-acme            # ID nội bộ ổn định, không dùng tên công ty làm khóa quyền
status: ACTIVE                     # PENDING | ACTIVE | SUSPENDED | DELETING
plan: ENTERPRISE
isolation_model: SILO
gcp_project_id: saas-prod-acme
region: asia-southeast1
database_ref: orders-acme
bucket_ref: saas-orders-acme
kms_key_ref: projects/.../cryptoKeys/tenant-acme
~~~

Bản ghi này **không phải cấu hình đủ để triển khai**. Thực tế phải kiểm tra tính hợp lệ/phiên bản metadata, quyền đọc tenant catalog, sự thay đổi vùng dữ liệu và quyền tài khoản dịch vụ.

## 5. Xác thực, phân quyền và xác định tenant đáng tin cậy

Một API đa tenant điển hình thực hiện các bước sau:

1. Xác minh token OAuth 2.0/OIDC ở phía server: chữ ký, issuer, audience, thời hạn, chủ thể và các claim theo cơ chế IdP đã chọn.
2. Xác định người dùng hoặc workload đã được xác thực.
3. Nếu client yêu cầu chuyển tenant, **kiểm tra membership và vai trò** bằng claim đáng tin cậy hoặc dữ liệu phân quyền phía server. Không chấp nhận giá trị tenant_id trong URL/header/body như bằng chứng có quyền.
4. Kiểm tra tenant đang ACTIVE, gói dịch vụ, quyền theo hành động và quyền trên đối tượng (resource ownership).
5. Tạo **tenant context nội bộ** và truyền qua repository, cache, event, job, xuất báo cáo và log.
6. Mỗi tầng xử lý dùng tenant context để chọn tài nguyên và giới hạn đọc/ghi; trường hợp thiếu context phải thất bại an toàn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Cloud Run API
    participant AUTH as Identity & Tenant directory
    participant DB as Tenant data store
    C->>API: GET /tenants/A/orders/42 + Bearer token
    API->>AUTH: Xác minh token + membership + role trong A
    alt Hợp lệ
        AUTH-->>API: Principal + allowed tenant A
        API->>DB: SELECT ... WHERE tenant_id=A AND order_id=42
        DB-->>API: Bản ghi A hoặc không có dữ liệu
        API-->>C: 200 hoặc 404
    else Không hợp lệ
        AUTH-->>API: Từ chối
        API-->>C: 403
    end
~~~

### Pseudocode ở lớp ứng dụng

~~~java
// Pseudocode minh họa, không phải lớp Spring Boot hoàn chỉnh.
Order getOrder(VerifiedPrincipal principal, String requestedTenant, UUID orderId) {
    // Xác minh bằng dữ liệu/quyền phía server, bao gồm trạng thái tenant.
    TenantContext ctx = tenantAuthorization.requireMembershipAndRole(
        principal, requestedTenant, "orders:read");

    // Repository PHẢI giữ ràng buộc tenant trong chính truy vấn.
    return orderRepository.findByTenantIdAndOrderId(ctx.tenantId(), orderId)
        .orElseThrow(NotFoundException::new);
}
~~~

Các điểm cần chú ý:

- Client có thể chọn tenant khi người dùng thuộc nhiều tenant, nhưng **server phải cấp quyền độc lập** cho mỗi lựa chọn.
- Không để client tự khai báo role=admin hoặc một tenant_id tùy ý trong JWT do client tự tạo.
- Phân quyền **tenant-wide** không thay thế quyền trên một đối tượng: nhân viên cùng công ty có thể không được đọc mọi hóa đơn.
- Dữ liệu nhạy cảm nên được che trong phản hồi 403/404 để hạn chế dò tìm mã tài nguyên.
- Khi thay quyền hoặc vô hiệu hóa tenant, cơ chế cache token/membership cần có TTL hoặc cơ chế thu hồi phù hợp để tránh quyền cũ tồn tại quá lâu.
- Chỉ truyền tenant context qua header nội bộ khi đã xác thực nguồn gửi và bảo vệ chống giả mạo; ưu tiên context được tạo trực tiếp trong backend.
- Khi nhân viên hỗ trợ cần truy cập dữ liệu khách hàng, sử dụng cơ chế **break-glass** có phê duyệt, phạm vi, hạn sử dụng và audit log; không tạo tài khoản hỗ trợ toàn quyền dùng thường xuyên.

## 6. Cô lập tại Google Cloud project, IAM, mạng và compute

### 6.1 Project, folder và organization

Tùy mức bảo mật, có thể tạo **một project cho mỗi tenant**. Project tạo ranh giới quản lý IAM, cấu hình API, quota, billing label và phần lớn tài nguyên. Đặt project theo folder như production, sandbox, dedicated-tenants; áp chính sách tổ chức và chính sách quản trị phù hợp. Một project riêng vẫn phải được cấu hình bảo mật cẩn thận, vì các quyền cấp từ folder/organization có thể kế thừa xuống project.

Trong mô hình pool, project là ranh giới chung của nhiều tenant; không được gọi một project GCP là ranh giới dữ liệu riêng khi tất cả tenant cùng sử dụng nó.

**Mẫu phân quyền silo:**

- service account của workload tenant A chỉ có quyền cần thiết trên project/bucket/database của A;
- service account tenant B có quyền tương ứng trên B;
- control plane chỉ có các quyền cấp phát/quản lý cần thiết, tách khỏi vai trò đọc nội dung nghiệp vụ;
- pipeline CI/CD có quyền triển khai theo project hoặc scope được cấp, không mặc định có quyền đọc dữ liệu;
- chỉ cấp quyền tại resource thấp nhất có thể, tránh Editor/Owner trên project cho runtime.

GCP **IAM** quyết định principal nào được phép thao tác với tài nguyên GCP; nó không tự xác minh membership của user bên trong ứng dụng SaaS.

### 6.2 Cloud Run

**Cloud Run service identity** là service account mà container dùng khi gọi API Google Cloud. Dịch vụ chạy cùng một service account ở chế độ pool có thể đọc dữ liệu nhiều tenant nếu service account được cấp quyền rộng. Do đó:

- **Pool:** dùng service account quyền tối thiểu và kiểm tra tenant trong ứng dụng, đồng thời thêm giới hạn ở dữ liệu khi sản phẩm hỗ trợ.
- **Silo:** tách Cloud Run service/job theo tenant và gán service account riêng; cấp IAM trên bucket/database của tenant tương ứng.
- **Bridge:** giữ API/router dùng chung nhưng điều hướng tới service tenant hoặc dùng cơ chế truy cập tài nguyên được kiểm soát chặt. Không cho gateway công khai tự chọn service account quyền cao theo tham số bất kỳ.
- Ưu tiên credential tự động qua **Application Default Credentials** của runtime; không nhúng service account key dài hạn vào container.
- Khi có code do tenant cung cấp và có thể không tin cậy, đánh giá ranh giới riêng cấp project và yêu cầu bảo mật bổ sung; tách mỗi tenant thành project là phương án được Google Cloud đề xuất trong trường hợp này.

### 6.3 GKE

GKE hỗ trợ đa tenant bằng **namespace, Kubernetes RBAC, NetworkPolicy, ResourceQuota, LimitRange, Pod security controls** và **Workload Identity Federation for GKE**. Một thiết kế pool thường tạo namespace riêng cho team/tenant và ServiceAccount Kubernetes riêng cho từng workload.

Tuy nhiên **namespace không phải ranh giới bảo mật tuyệt đối**: các tenant vẫn có thể chia sẻ control plane, node, add-on và kernel tùy cách bố trí. Tách node pool, dùng GKE Sandbox (khi phù hợp), admission policy và network policy có thể giảm nguy cơ nhưng không thay thế ranh giới project/cluster trong trường hợp cần cô lập mạnh hoặc chạy mã không tin cậy.

Workload Identity Federation for GKE cho phép workload xác thực với Google Cloud mà không phải lưu khóa service account thủ công. Cần lưu ý danh tính workload có thể gắn với project workload identity pool; nếu nhiều cluster trong cùng project dùng trùng namespace/service account, phải kiểm tra tác động tới quyền truy cập.

### 6.4 Network và VPC Service Controls

VPC, firewall, egress policy, Private Service Connect, network policy và thiết kế kết nối riêng giúp giảm bề mặt tấn công và di chuyển ngang. **VPC Service Controls** bổ sung service perimeter cho các Google-managed service được hỗ trợ (ví dụ Cloud Storage, BigQuery) để giảm rủi ro lấy dữ liệu ra ngoài phạm vi cho phép. Đây không phải cơ chế thay thế kiểm tra tenant_id, IAM hay row-level access: hai tenant đặt trong cùng perimeter vẫn cần ranh giới truy cập riêng.

## 7. Cô lập dữ liệu theo từng loại dịch vụ

### 7.1 Cloud SQL for PostgreSQL: ràng buộc tenant_id và RLS

Trong mô hình pool, một database có thể chứa bảng orders/documents của nhiều tenant. Cần tối thiểu:

- tenant_id là trường **NOT NULL** có trong khóa chính hoặc khóa duy nhất phù hợp;
- mọi truy vấn phải ràng buộc tenant_id được xác minh, kể cả **UPDATE/DELETE, JOIN, batch, export**;
- index có tenant_id phù hợp với mẫu truy vấn;
- các khóa ngoại giữa bảng nhiều tenant phải bao gồm tenant_id để tránh gắn bản ghi khác tenant;
- dùng PostgreSQL **Row-Level Security (RLS)** như một tầng phòng thủ bổ sung.

Ví dụ SQL trên PostgreSQL, giả định đã tạo role **app_runtime** không sở hữu bảng, không có quyền BYPASSRLS và không được cấp các quyền quản trị đặc biệt:

~~~sql
CREATE TABLE documents (
  tenant_id   text NOT NULL,
  document_id uuid NOT NULL,
  title       text NOT NULL,
  PRIMARY KEY (tenant_id, document_id)
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_documents_policy
  ON documents
  FOR ALL
  TO app_runtime
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Quyền SELECT/INSERT/UPDATE/DELETE được cấp riêng theo nhu cầu.
-- Không chạy ứng dụng bằng superuser, chủ bảng hoặc role BYPASSRLS.
~~~

Ứng dụng đã xác thực tenant có thể thiết lập context **theo từng transaction** rồi chạy truy vấn tham số hóa:

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', 'tenant-acme', true);
SELECT document_id, title
FROM documents
WHERE tenant_id = 'tenant-acme'
ORDER BY document_id;
COMMIT;
~~~

Đoạn code chỉ minh họa: trên hệ thống thật, giá trị tenant phải đến từ authorization phía server và được binding bằng parameter; không chèn thẳng chuỗi không tin cậy. Phải đặt context và thực thi truy vấn trong **cùng transaction/connection**, tránh sót context khi sử dụng connection pool. Giá trị chưa được thiết lập phải cho kết quả bị chặn theo chính sách. Đặc biệt, PostgreSQL custom setting trong ví dụ có thể do người nắm quyền thực thi SQL với role ứng dụng tự gán; vì vậy **không cung cấp quyền kết nối DB trực tiếp cho tenant** và không coi RLS kiểu này là ranh giới chống lại ứng dụng đã bị chiếm quyền.

Một thiết kế silo có thể dùng **database/instance riêng mỗi tenant** để tăng cô lập, nhưng phải dự toán kết nối, chi phí nền, backup/restore và tự động hóa schema migration.

### 7.2 Cloud Storage: bucket riêng hoặc managed folder

**Silo:** bucket riêng tenant (hoặc project riêng + bucket riêng), IAM service account chỉ cho phép đọc/ghi bucket cần thiết. Có thể áp dụng chính sách mã hóa, retention, lifecycle, logging và vùng lưu trữ theo yêu cầu từng tenant.

**Pool:** bucket dùng chung, object key tổ chức theo tenant, ví dụ:

~~~text
gs://saas-shared-documents/tenants/tenant-acme/contracts/2026-001.pdf
gs://saas-shared-documents/tenants/tenant-beta/contracts/2026-008.pdf
~~~

Object prefix là **quy ước đặt tên**, không tự tạo ranh giới phân quyền. Nếu cần IAM tại prefix, Cloud Storage hỗ trợ **managed folders** với policy IAM trên nhóm object tương ứng; managed folders yêu cầu bucket bật **uniform bucket-level access**. Quyền IAM được cấp ở tầng bucket/project có thể vẫn rộng hơn quyền tại managed folder. Phải thiết kế phạm vi cấp quyền từ trên xuống, không suy diễn rằng policy hẹp ở folder sẽ phủ định quyền rộng kế thừa.

Các URL tải lên/tải xuống có chữ ký (signed URL) phải được tạo phía backend **sau khi kiểm tra quyền tenant và object cụ thể**, giới hạn thao tác, thời hạn và đường dẫn; không tạo theo tên file hoặc prefix do client cung cấp mà chưa kiểm chứng.

### 7.3 BigQuery: dataset riêng, row-level và column-level security

Đối với dữ liệu phân tích, có thể chọn:

- **Dataset/table riêng theo tenant:** phân tách IAM và việc xuất/xóa/đối soát dữ liệu rõ hơn, đổi lại nhiều dataset/table hơn.
- **Bảng chung có tenant_id:** tiết kiệm quản trị ở quy mô lớn nhưng phải có ranh giới người truy cập ở tầng BigQuery hoặc tại ứng dụng.
- **Row-level security:** tạo chính sách lọc hàng theo principal được cấp quyền.
- **Column-level security hoặc data masking:** bảo vệ cột nhạy cảm; độc lập với ranh giới hàng.

Ví dụ dùng **GoogleSQL** cho nhóm được ủy quyền đọc dữ liệu tenant-acme (giả sử bảng analytics.orders đã có cột tenant_id):

~~~sql
CREATE ROW ACCESS POLICY acme_orders_read
ON analytics.orders
GRANT TO ('group:acme-analysts@example.org')
FILTER USING (tenant_id = 'tenant-acme');
~~~

Quyền IAM ở project/dataset/table vẫn phải cấp phù hợp để principal có thể truy vấn; row access policy quyết định những **hàng** được xem. Các chính sách row access theo principal có quy tắc kết hợp riêng nên cần rà soát policy cấp quyền quá rộng.

Nếu **một service account dùng chung** chạy mọi truy vấn cho mọi tenant, BigQuery sẽ thấy cùng principal ở tất cả request. Chính sách theo principal không tự phân biệt người dùng SaaS đang đứng sau service account đó. Phải chọn service identity riêng cho trường hợp truy vấn trực tiếp, dùng dataset riêng hoặc giữ lớp kiểm tra tenant đáng tin cậy trong backend. Tránh cấp quyền quản trị BigQuery rộng cho runtime cần truy vấn giới hạn.

### 7.4 Firestore: Security Rules và danh tính của server

Với client web/mobile dùng Firestore, có thể tổ chức document theo đường dẫn tenant và kiểm tra **Firebase Authentication/custom claim** do hệ thống tin cậy phát hành. Ví dụ đơn giản khi mỗi token có claim tenant_id của tenant đang hoạt động:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /tenants/{tenantId}/documents/{docId} {
      allow read, write: if request.auth != null
        && request.auth.token.tenant_id == tenantId;
    }
  }
}
~~~

Đây là **minh họa tối thiểu**, chưa kiểm tra role, ownership từng document, schema, dữ liệu thay đổi hay quyền người dùng thuộc nhiều tenant. Claim phải được cập nhật/thực thi thu hồi khi quyền thay đổi và quy tắc cần kiểm thử trước triển khai. Security Rules **không hoạt động như bộ lọc truy vấn**; query phải phù hợp phạm vi mà rule cho phép.

**Bẫy quan trọng:** Firestore server client libraries và nhiều đường truy cập server/API sử dụng **IAM**, bỏ qua Firestore Security Rules. Nếu backend Cloud Run dùng Admin SDK để đọc Firestore, ứng dụng phải thực hiện authorization tenant của chính mình. Không dựa vào rules của client để bảo vệ backend.

### 7.5 Spanner và dữ liệu phân tán

Spanner hỗ trợ **fine-grained access control (FGAC)** dựa trên database roles gắn với IAM principals để cấp quyền trên bảng, cột, view và các đối tượng được hỗ trợ. Đây không phải tính năng tự động lọc mọi hàng theo tenant_id. Với bảng pooled, vẫn phải thiết kế schema và truy vấn theo tenant; với silo, có thể tách database hoặc instance tùy yêu cầu độ cô lập/chi phí.

Khi dữ liệu lớn, chọn khóa chính có tenant_id theo thứ tự phù hợp với mô hình truy vấn và phân bố tải. Đừng thiết kế khóa tuần tự đơn giản khiến tải dồn vào một khu vực: cần đánh giá kỹ chiến lược key và hotspot theo đặc thù Spanner.

### 7.6 Pub/Sub, Cloud Tasks, cache, search và bản sao thứ cấp

Cô lập tenant phải đi qua **mọi bản sao và đường xử lý**, không dừng tại database chính:

- **Pub/Sub / Cloud Tasks:** payload hoặc metadata có tenant_id đã được xác thực; consumer phải giải quyết và kiểm tra lại context trước khi ghi. Xác thực publisher/consumer với IAM và kiểm soát dead-letter/retry.
- **Cloud Storage export/import:** tên file, manifest và bucket đích phải ràng buộc với tenant hợp lệ.
- **Cache (ví dụ Memorystore):** key gồm tenant_id, loại tài nguyên, ID và version; hạn chế dữ liệu nhạy cảm, TTL và quyền đọc của admin tooling.
- **Search index/vector store:** mỗi query phải có filter tenant; nếu bộ máy chỉ filter phía client thì không đủ.
- **Tập dữ liệu BI/BigQuery:** việc sao chép dữ liệu từ DB sang warehouse là **một hệ thống quyền mới**, phải kiểm soát lại.
- **Logs, traces, error reporting:** tag tenant_id dạng mã nội bộ nhưng không ghi token, payload nhạy cảm, nội dung hóa đơn hoặc dữ liệu cá nhân chỉ để tiện debug.

Ví dụ tên cache key đúng phạm vi:

~~~text
tenant-acme:order:fa1d...:v3
tenant-beta:order:fa1d...:v3
~~~

Một event được xử lý lại nhiều lần cần **idempotency key có gắn tenant**. Nếu khóa idempotency chỉ dựa trên order ID và hai tenant có ID trùng nhau, một request của A có thể vô tình làm B bị bỏ qua hoặc ghi đè.

## 8. Mã hóa, khóa, sao lưu và tuân thủ

### Mã hóa và quản lý khóa

Google Cloud cung cấp mã hóa dữ liệu ở trạng thái lưu trữ và khi truyền theo cơ chế của dịch vụ. Với yêu cầu quản lý khóa của khách hàng, có thể xem xét **Cloud KMS / CMEK** cho các dịch vụ và phạm vi tài nguyên được hỗ trợ. Một số thiết kế silo chọn khóa riêng tenant để phục vụ chính sách vận hành hoặc crypto-shredding.

Không mặc định rằng **một khóa KMS riêng tự bảo đảm cô lập tenant**: account nào có quyền giải mã, quyền đọc dữ liệu mã hóa, quyền quản lý khóa và quyền chọn key đều phải được kiểm soát. Granularity của CMEK phụ thuộc dịch vụ, resource và cấu hình; cần xác minh trước khi ký hợp đồng.

### Backup, restore và xóa dữ liệu

Phải trả lời trước khi bán dịch vụ:

1. Có thể **khôi phục riêng một tenant** mà không khôi phục đè dữ liệu tenant khác không?
2. Bản sao lưu có chứa nhiều tenant chung một snapshot không? Làm sao xuất đúng tập dữ liệu?
3. Việc xóa tenant sau khi hết hợp đồng có bao gồm object versions, bản sao BI, cache, search index, log và backup theo lịch lưu giữ không?
4. Thời hạn retention, yêu cầu legal hold, RPO/RTO và region áp dụng cho tenant nào?
5. Có cần biên bản xác nhận xóa hoặc báo cáo truy cập của nhân viên hỗ trợ không?

Trong mô hình pool, PITR/snapshot khôi phục **cả database** thường không tương đương việc khôi phục một tenant. Cần công cụ export/import có tenant filter, tách restore environment và kiểm tra tránh ghi chồng tenant khác. Trong silo, phục hồi project/database riêng thuận tiện hơn nhưng vẫn phải kiểm tra dependencies dùng chung.

## 9. Tránh noisy neighbor và theo dõi mức sử dụng

**Noisy neighbor** là tình trạng một tenant tạo tải bất thường làm tăng độ trễ, số lỗi hoặc chi phí cho tenant khác. Rủi ro có thể đến từ CPU, RAM, connection pool, giới hạn Cloud Run concurrency, số Pod, quota API, throughput database hoặc các truy vấn BigQuery.

Nhóm kiểm soát thực tế:

| Lớp | Phương pháp |
| --- | --- |
| API | Quota, rate limiting theo tenant và theo user; giới hạn payload, concurrency |
| Cloud Run | Giới hạn concurrency/max instances phù hợp; tách service theo tenant lớn nếu cần |
| GKE | ResourceQuota, LimitRange, autoscaling, node pool/quy trình ưu tiên tài nguyên |
| Database | Connection pool theo tenant/lớp tải, timeout, giới hạn query, index có tenant_id |
| Job / event | Queue riêng hoặc công bằng, giới hạn worker theo tenant, backpressure, retry có jitter |
| BigQuery | Theo dõi workload/job, quota hoặc reservation theo mô hình phù hợp |
| Cost | Labels/tags, đơn vị đo GB, requests, CPU, query bytes, budget và chargeback/showback |

Định nghĩa SLO theo **tenant hoặc nhóm dịch vụ**, không chỉ số trung bình toàn hệ thống. Ví dụ: tỷ lệ HTTP 5xx, p95 latency, độ trễ xử lý event, job backlog, tỷ lệ throttling và chi phí mỗi tenant/1000 yêu cầu. Tránh đưa tenant_id có độ phân biệt cực cao vào metric không có chính sách kiểm soát cardinality; chọn nơi tổng hợp theo gói hoặc tenant quan trọng.

**Chi phí pool** không thể suy ra chính xác từ nhãn project vì nhiều tenant cùng dùng tài nguyên. Cần bổ sung thống kê ứng dụng theo tenant và phương pháp phân bổ phần hạ tầng chung. **Chi phí silo** dễ phân tách theo project hơn nhưng vẫn có shared control plane, network và chi phí vận hành cần phân bổ.

## 10. Vòng đời tenant và vận hành bằng tự động hóa

Một nền tảng đa tenant tốt cần quy trình nhất quán:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROVISIONING
    PROVISIONING --> ACTIVE
    ACTIVE --> SUSPENDED
    SUSPENDED --> ACTIVE
    ACTIVE --> DELETING
    SUSPENDED --> DELETING
    DELETING --> DELETED
    DELETED --> [*]
~~~

### Onboarding

- Tạo tenant_id bất biến và bản ghi tenant catalog với trạng thái PENDING.
- Kiểm tra yêu cầu vùng dữ liệu, gói dịch vụ, hình thức cô lập, nhu cầu khóa và budget.
- Dùng Infrastructure as Code (ví dụ Terraform) để tạo project, service account, IAM, network, bucket, database và policy nếu mô hình yêu cầu.
- Áp schema migration, cấu hình monitoring, backup, log, quota và mẫu cấu hình an toàn.
- Chạy kiểm tra truy cập: account A không thể đọc/ghi dữ liệu B; lỗi tạo tài nguyên phải có cơ chế rollback/cleanup.
- Chỉ chuyển ACTIVE khi provisioning hoàn tất, có record khả dụng và đủ bằng chứng.

### Thay đổi gói hoặc chuyển Pool sang Silo

- Chuẩn bị tài nguyên đích, xác minh cách chuyển dữ liệu nhất quán.
- Dùng batch copy/CDC hoặc cách sao chép phù hợp, ghi mốc và xác minh checksum/count.
- Duy trì phiên bản mapping trong tenant catalog để router không gửi request về hai đích không tương thích.
- Thực hiện chuyển luồng có thời điểm kiểm soát, kiểm tra dữ liệu delta, rollback plan và thời gian chấp nhận gián đoạn.
- Sau khi nghiệm thu mới thu hồi quyền nguồn và giải phóng tài nguyên cũ theo chính sách.

### Offboarding

- Khóa quyền truy cập tenant, ngăn job mới và dừng retry không còn hiệu lực.
- Thực hiện export theo hợp đồng, thu hồi service account token/quyền truy cập, hủy signed URL còn hiệu lực theo cơ chế khả thi.
- Xóa hoặc đặt lịch xóa dữ liệu chính, backup, object versions, search/cache, dữ liệu xuất, theo retention/legal hold.
- Ghi audit về các bước dọn dẹp và chỉ chuyển DELETED sau khi đáp ứng các điều kiện kiểm tra.

**Lưu ý:** Xóa project không phải một quy trình bảo đảm dọn đúng tất cả dữ liệu có thể đã xuất sang project dùng chung hay dịch vụ ngoài. Cần inventory luồng dữ liệu từ đầu.

## 11. Kiểm thử cô lập dữ liệu và bảo mật

Kiểm thử phải kiểm tra **quyền bị từ chối**, không chỉ đường đi thành công. Bộ kiểm thử tối thiểu gồm:

| Tình huống | Kỳ vọng |
| --- | --- |
| User A gọi URL dữ liệu tenant B | Từ chối theo policy; không lộ dữ liệu B |
| User A thay tenant_id trong JSON body | Không thể ghi object sang B |
| User thuộc A và B nhưng chỉ có vai trò read ở B | Không được ghi ở B |
| Truy vấn thiếu tenant context | Thất bại an toàn, không trả dữ liệu toàn bảng |
| Bảng có ID bản ghi trùng giữa A và B | Truy vấn/update chỉ tác động tenant được cấp |
| Cache key, job ID hoặc event ID trùng | Không làm lẫn kết quả, retry và trạng thái |
| Worker nhận event có tenant_id giả | Đối chiếu nguồn gửi/context và từ chối |
| Service account workload A thử đọc bucket B | IAM từ chối trong mô hình Silo |
| BigQuery row policy cho group A | Không thấy hàng tenant B; quyền bổ sung không vô tình vượt phạm vi |
| Tăng tải của tenant A | Tenant B vẫn trong mục tiêu latency/error rate đã quy định |
| Restore/export tenant A | Không chạm hoặc lộ dữ liệu tenant B |
| Vô hiệu hóa tenant A | Request và background job bị chặn đúng thời điểm |
| Nhân viên hỗ trợ truy cập tenant A | Phải có phê duyệt/quyền/hạn sử dụng và audit log |

Ví dụ kế hoạch kiểm thử SQL:

~~~sql
-- Trong transaction đã xác định tenant A từ backend đáng tin cậy:
SELECT COUNT(*) FROM documents WHERE tenant_id = 'tenant-acme';

-- Thử truy vấn vượt phạm vi khi PostgreSQL RLS dùng context tenant A:
SELECT * FROM documents WHERE tenant_id = 'tenant-beta';
-- Kỳ vọng: không trả hàng tenant-beta cho role app_runtime.
~~~

Kiểm thử lỗi logic khác: SQL JOIN không đủ điều kiện tenant, backup restore nhầm cơ sở dữ liệu, signed URL tạo theo object key chưa xác minh, BigQuery policy cấp cho group chứa nhầm user B, search query thiếu filter và request chạy qua admin endpoint.

Các kiểm thử nên được tự động hóa trong môi trường có ít nhất hai tenant giả lập với dữ liệu có cùng định dạng và ID có thể trùng nhau. Đồng thời cần đánh giá threat model và diễn tập khôi phục theo lịch.

## 12. Tình huống thiết kế: SaaS quản lý hợp đồng

Một nhóm phát triển sản phẩm trên Google Cloud dự kiến có **500 doanh nghiệp nhỏ** và **10 khách hàng Enterprise**. Mỗi tenant quản lý hợp đồng PDF, thông tin người ký, lịch sử duyệt và báo cáo. Enterprise có yêu cầu vùng lưu trữ, phục hồi riêng và audit chi tiết.

### Phương án đề xuất

- **Control plane dùng chung:** dịch vụ tenant registry, đăng nhập, billing và provisioning, chỉ nắm metadata cần thiết.
- **Standard (pool):** API trên Cloud Run; dữ liệu giao dịch trên Cloud SQL for PostgreSQL có tenant_id, composite keys, truy vấn có tenant filter và RLS như phòng thủ bổ sung; PDF trên Cloud Storage theo managed folder/bucket policy phù hợp.
- **Enterprise (silo):** project, Cloud Run service identity, database, bucket và cấu hình backup riêng; tách khu vực xử lý nếu hợp đồng yêu cầu, với IAM tối thiểu.
- **Báo cáo:** BigQuery dataset riêng cho enterprise hoặc bảng dùng chung có kiểm soát row access theo principal; luồng ETL phải mang tenant_id được xác thực.
- **Tác vụ bất đồng bộ:** Pub/Sub/Cloud Tasks mang context tenant có kiểm tra, retry và idempotency theo tenant, hạn chế backlog của tenant lớn.
- **Quan sát:** SLO chung và số liệu p95/5xx/job lag/cost theo từng tenant quan trọng; báo cáo audit theo quyền được cấp.

### Một chuỗi request minh họa

1. Người dùng ACME đăng nhập và yêu cầu tải hợp đồng 77.
2. Backend xác minh token, kiểm tra membership và quyền read trong tenant ACME.
3. Router xác định ACME thuộc gói Enterprise và tra mapping tới project/dịch vụ của ACME.
4. Workload ACME dùng service identity riêng để lấy metadata và object trong bucket ACME; IAM không cấp quyền sang project Beta.
5. Backend tạo signed URL chỉ cho object được cấp quyền, có thời gian hiệu lực giới hạn.
6. Audit log ghi principal, tenant_id dạng mã, object ID, kết quả và request trace, không ghi nội dung hợp đồng.

Nếu ACME chuyển từ Standard sang Enterprise, nền tảng phải có quy trình di chuyển có kiểm soát và xác minh dữ liệu sau khi chuyển. Nếu dùng chung service account để đọc cả hai bucket trong lúc di chuyển, phải thu hẹp quyền tạm thời và thu hồi đúng hạn.

### Phân tích quyết định

Với Standard, pool tối ưu chi phí khởi đầu nhưng bắt buộc kiểm thử phân quyền tenant ở ứng dụng và dữ liệu. Với Enterprise, silo đáp ứng yêu cầu cô lập và khôi phục riêng tốt hơn nhưng có thêm chi phí vận hành. Bridge là lựa chọn thực tế nếu hệ thống có nhiều phân khúc khách hàng và team đã có khả năng tự động provisioning.

## 13. Checklist trước khi phê duyệt kiến trúc

1. [ ] Có định nghĩa tenant, user, membership, role và cách chọn tenant hợp lệ.
2. [ ] Có phân loại dữ liệu, mức cô lập cần thiết và lý do chọn pool/silo/bridge.
3. [ ] Tenant context được xác minh tại API và truyền tới mọi query, event, job, cache, export và log.
4. [ ] IAM của runtime dùng quyền tối thiểu; xác định ranh giới project/service account/database/bucket.
5. [ ] Đã kiểm tra các lớp bảo vệ dữ liệu theo từng dịch vụ: SQL RLS, BigQuery row policy, Cloud Storage IAM/managed folder, Firestore rules hoặc IAM.
6. [ ] Hiểu rõ ngoại lệ: Cloud Run service account không phải danh tính người dùng SaaS; GKE namespace không phải ranh giới cứng; Firestore server SDK bỏ qua Security Rules.
7. [ ] Có biện pháp chống noisy neighbor và quota theo tenant.
8. [ ] Có quy trình onboarding, suspension, migration, backup/restore và offboarding riêng từng tenant.
9. [ ] Audit log, metric, billing, dữ liệu sao chép thứ cấp và quyền nhân viên hỗ trợ được kiểm soát.
10. [ ] Kiểm thử truy cập chéo tenant và diễn tập khôi phục được tự động hóa trước production.

## 14. Những điểm cần ghi nhớ

- Cô lập đa tenant là vấn đề **kiến trúc xuyên suốt**, bao gồm danh tính, ứng dụng, dữ liệu, mạng, workload, vận hành và chi phí.
- **Pool** phù hợp mật độ tenant cao khi hệ thống có chính sách tenant mạnh ở ứng dụng/dữ liệu; **silo** tăng mức tách biệt nhưng thêm chi phí; **bridge** kết hợp theo yêu cầu kinh doanh.
- Google Cloud **IAM bảo vệ tài nguyên GCP theo principal**; IAM không mặc nhiên biết khách hàng SaaS nào đứng sau một request từ shared service account.
- Khóa phân vùng, bucket prefix hay GKE namespace là công cụ tổ chức; chỉ an toàn khi đi cùng kiểm soát truy cập đúng phạm vi.
- Phòng thủ nhiều lớp: xác thực tenant phía server, IAM tối thiểu, ràng buộc tenant ở query, database policy khi có thể, kiểm thử chéo tenant, quan sát và quy trình vận hành.
- Mục tiêu của thiết kế tốt là để **một lỗi đơn lẻ khó dẫn đến rò rỉ dữ liệu hoặc ngừng dịch vụ trên diện rộng**, đồng thời vẫn có cách phát triển hệ thống khi số lượng tenant tăng.

## Tài liệu chính thức để tra cứu khi triển khai

- [Google Cloud — App Lifecycle Manager: mô hình silo, pool và hybrid](https://docs.cloud.google.com/app-lifecycle-manager/overview)
- [Cloud Run — Multi-tenant platforms running untrusted code](https://docs.cloud.google.com/run/docs/securing/multi-tenant)
- [Cloud Run — Introduction to service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [GKE — Cluster multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/multitenancy-overview)
- [GKE — Best practices for enterprise multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/enterprise-multitenancy)
- [GKE — Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Cloud Storage — Managed folders](https://docs.cloud.google.com/storage/docs/managed-folders)
- [BigQuery — Row-level security overview](https://docs.cloud.google.com/bigquery/docs/row-level-security-intro)
- [BigQuery — Managing row-level security](https://docs.cloud.google.com/bigquery/docs/managing-row-level-security)
- [Firestore — Structure security rules](https://docs.cloud.google.com/firestore/native/docs/security/rules-structure)
- [Firestore — Security for server client libraries](https://docs.cloud.google.com/firestore/native/docs/security/iam)
- [Spanner — Fine-grained access control overview](https://docs.cloud.google.com/spanner/docs/fgac-about)
- [VPC Service Controls — Overview](https://docs.cloud.google.com/vpc-service-controls/docs/overview)
