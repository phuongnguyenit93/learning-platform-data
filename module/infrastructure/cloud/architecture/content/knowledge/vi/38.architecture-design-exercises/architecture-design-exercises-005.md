# Chuyển hệ thống đơn tenant thành SaaS đa tenant

## 1. Bài toán thiết kế và mục tiêu học tập

Trong module **CLOUD_ARCHITECTURE**, thiết kế kiến trúc ứng dụng đám mây bắt đầu bằng yêu cầu nghiệp vụ, sau đó lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài thực hành thuộc chương **Thực hành thiết kế** này yêu cầu chuyển một ứng dụng phục vụ một khách hàng/tổ chức (**single-tenant**) thành nền tảng **Software as a Service (SaaS) đa tenant** để nhiều tổ chức sử dụng cùng sản phẩm với các mức cô lập và dịch vụ được kiểm soát.

**Tenant** là ranh giới tổ chức/khách hàng mà nền tảng cần quản lý về định danh, quyền truy cập, dữ liệu, cấu hình, sử dụng tài nguyên, chi phí và vòng đời. Tenant không nhất thiết trùng với một người dùng, một cơ sở dữ liệu, một tài khoản cloud hoặc một hostname.

Chuyển đổi thành công không chỉ là thêm cột **tenant_id** vào bảng. Người thiết kế phải chứng minh được:

- **Cô lập:** tenant A không thể đọc, sửa, xuất hay suy ra dữ liệu của tenant B qua API, CSDL, cache, tìm kiếm, file, tác vụ nền và quan sát hệ thống.
- **Độ tin cậy:** sự cố hoặc tải bất thường của một tenant không làm sụp đổ dịch vụ của tất cả tenant ngoài ngưỡng đã cam kết.
- **Khả năng mở rộng:** hạ tầng có thể đáp ứng tăng trưởng số tenant và tải không đồng đều.
- **Bảo mật:** định danh, phân quyền, bí mật, nhật ký kiểm toán và yêu cầu pháp lý được thực thi xuyên suốt.
- **Chi phí:** có thể phân bổ và dự báo chi phí, ngăn một tenant tiêu thụ tài nguyên không kiểm soát.
- **Vận hành:** đăng ký, cấp phát, nâng cấp, giám sát, hỗ trợ, sao lưu và chấm dứt tenant có thể vận hành ở quy mô lớn.

Sau bài học, bạn sẽ có thể chọn mô hình cô lập dữ liệu và compute, đề xuất kiến trúc đích, xây dựng kế hoạch chuyển đổi an toàn và đánh giá thiết kế theo các góc nhìn Well-Architected.

## 2. Tình huống doanh nghiệp giả định

Công ty cung cấp phần mềm quản lý đơn hàng cho một chuỗi cửa hàng. Hệ thống hiện tại phục vụ một tổ chức:

~~~mermaid
flowchart LR
    U[Nhân viên] --> W[Web / API]
    W --> DB[(PostgreSQL)]
    W --> C[Redis cache]
    W --> Q[Queue]
    Q --> J[Worker xử lý đơn]
    J --> DB
    W --> S[Object storage]
~~~

Đặc điểm ban đầu:

- Ứng dụng web/API và worker được triển khai theo một môi trường cho mỗi khách hàng.
- Mỗi môi trường dùng một CSDL; nhiều truy vấn ngầm hiểu “toàn bộ dữ liệu thuộc một khách hàng”.
- Cache, hàng đợi, file xuất báo cáo và tên đối tượng chưa có namespace theo tenant.
- Người dùng đăng nhập bằng tài khoản nội bộ, chưa có cơ chế thành viên của nhiều tổ chức.
- Nhóm vận hành phải tạo hạ tầng thủ công, cập nhật và hỗ trợ từng khách hàng.

**Mục tiêu 12 tháng** là phục vụ 120 tổ chức, trong đó có 10 tổ chức lớn với tải cao. Doanh nghiệp mong muốn giảm thời gian onboard, vận hành từ một nền tảng chung khi hợp lý, nhưng vẫn cung cấp mức cô lập mạnh hơn cho khách hàng có yêu cầu đặc biệt.

### 2.1. Yêu cầu đầu vào để học viên thực hành

Các giá trị sau là **giả định phục vụ bài tập**, cần thương lượng lại với chủ sản phẩm và đội vận hành trong dự án thực tế:

| Nhóm | Yêu cầu giả định |
| --- | --- |
| Tăng trưởng | 120 tenant năm đầu; 500 tenant sau ba năm |
| Tải hệ thống | 400 request/giây ở tải đỉnh thường; burst 1.000 request/giây trong 5 phút |
| Độ trễ | P95 của API tạo đơn dưới 300 ms tại tải mục tiêu đã định |
| Sẵn sàng | SLO 99,9% theo tháng cho dịch vụ cốt lõi, với định nghĩa và ngoại lệ rõ |
| Phục hồi | RTO 2 giờ, RPO 15 phút cho dữ liệu giao dịch |
| Cô lập | Không cho phép truy cập chéo tenant, kể cả qua truy vấn và background job |
| Cấu hình | Mỗi tenant có tên miền phụ, thương hiệu, hạn mức và tích hợp đối tác riêng |
| Thương mại | Gói Standard và Enterprise; phải đo mức sử dụng và quy đổi thành hóa đơn |
| Pháp lý | Một số khách hàng yêu cầu dữ liệu ở một khu vực nhất định; cần thẩm định hợp đồng |
| Triển khai | Mỗi tuần có thể phát hành nhiều phiên bản mà không cấu hình thủ công từng tenant |
| Vận hành | Có khả năng tra cứu sự cố theo tenant, cô lập tải và xử lý ngừng dịch vụ riêng lẻ |

**Đầu ra bắt buộc của bài thực hành:** tài liệu quyết định kiến trúc, sơ đồ trạng thái đích, mô hình dữ liệu/cô lập, luồng xác thực–phân quyền, kế hoạch chuyển dữ liệu, chiến lược test và ngân sách ước tính.

## 3. Làm rõ lựa chọn trước khi vẽ kiến trúc

Đội thiết kế cần hỏi và ghi lại câu trả lời, vì những câu trả lời này có thể thay đổi phương án:

1. **Ranh giới tenant:** một doanh nghiệp có nhiều chi nhánh là một hay nhiều tenant? Người dùng có được tham gia nhiều tenant không?
2. **Dữ liệu:** hệ thống có lưu thông tin định danh, thông tin thanh toán hoặc dữ liệu nhạy cảm? Có quy định vị trí lưu trữ, thời hạn xóa và quyền xuất không?
3. **Cách tùy biến:** khác biệt giữa tenant là cấu hình hay cần sửa logic/chạy plugin tùy ý?
4. **Mức cô lập:** gói Enterprise có yêu cầu riêng CSDL, khóa mã hóa, mạng hoặc region không?
5. **Hiệu năng:** yêu cầu SLO cho tất cả tenant có giống nhau? Có khách hàng tạo phần lớn lưu lượng không?
6. **Tính kinh tế:** mô hình giá theo người dùng, số đơn, request, dung lượng hay gói dịch vụ? Ai trả phần chi phí đột biến?
7. **Vận hành:** có cần dừng, chuyển vùng, xuất dữ liệu, khôi phục và xóa riêng một tenant mà không tác động tenant khác?
8. **Truyền dữ liệu hiện tại:** có bao nhiêu cơ sở dữ liệu/khách hàng đang hoạt động, dữ liệu trùng ID hay schema khác nhau không?

Không thể đánh giá thiết kế đúng nếu chưa phân biệt rõ **những điều bắt buộc** với những điều được phép đánh đổi. Ví dụ, mục tiêu chi phí thấp không thể thay thế điều kiện cô lập dữ liệu.

## 4. Chọn mô hình multi-tenancy: silo, bridge, pool

Có ba cách tổ chức phổ biến, có thể phối hợp trong cùng nền tảng:

| Mô hình | Minh họa | Lợi ích | Nhược điểm chính | Khi nên cân nhắc |
| --- | --- | --- | --- | --- |
| **Silo** | Mỗi tenant có tài nguyên riêng, ví dụ CSDL hoặc môi trường riêng | Ranh giới dữ liệu/tài nguyên mạnh, tùy biến riêng, blast radius nhỏ | Tài nguyên rỗi và công việc quản trị nhiều hơn | Tenant yêu cầu cô lập/tuân thủ đặc biệt |
| **Pool** | Nhiều tenant dùng chung ứng dụng, compute và một hoặc nhiều bảng dữ liệu chung | Hiệu quả tài nguyên, triển khai đồng nhất, onboard nhanh | Cần thực thi cô lập ở mọi lớp, kiểm soát noisy neighbor | Nhiều tenant Standard có mô hình tương tự |
| **Bridge** | Dùng chung một số lớp, tách riêng lớp khác | Cân bằng cô lập, vận hành và chi phí | Độ phức tạp định tuyến và quản lý nhiều cấu hình | Gói Enterprise có DB riêng nhưng dùng chung lớp API |

Khái niệm này có thể áp dụng riêng từng lớp: compute dạng pool nhưng CSDL dạng silo; hoặc ứng dụng pool và từng nhóm tenant có cluster riêng.

### 4.1. Ba mô hình dữ liệu cần so sánh

| Mô hình dữ liệu | Cách làm | Điểm cần chú ý |
| --- | --- | --- |
| **Database per tenant** | Cấp CSDL riêng cho từng tenant | Quản lý kết nối, nâng cấp hàng loạt, backup/restore và chi phí tenant nhỏ |
| **Schema per tenant** | Một hệ quản trị dữ liệu, nhiều schema | Di trú schema hàng loạt, giới hạn đối tượng, quản lý quyền và connection |
| **Shared schema với tenant_id** | Bảng chung, mọi bản ghi nghiệp vụ có tenant_id | RLS/kiểm tra quyền, khóa ngoại, index và mọi truy vấn phải đúng phạm vi |

Không có mô hình “an toàn tuyệt đối” nhờ tên gọi. Ngay cả database per tenant vẫn có thể lộ dữ liệu nếu lớp định tuyến, backup, file xuất hoặc quyền vận hành sai. Shared schema có thể bảo đảm cô lập mạnh khi nhiều lớp bảo vệ được thiết kế và kiểm chứng nghiêm ngặt.

### 4.2. Phương án khởi đầu được chọn cho tình huống

Giả định sau đánh giá, nhóm chọn **mô hình bridge**:

- **Standard:** API/worker dùng chung, shared PostgreSQL schema có tenant_id và chính sách cô lập ở tầng dữ liệu.
- **Enterprise:** cùng mã sản phẩm và một control plane nhưng định tuyến dữ liệu sang CSDL chuyên biệt theo yêu cầu; có thể tách compute nếu SLO/chi phí phù hợp.
- **Các dịch vụ dùng chung:** định danh, cổng cấu hình, cấp phát tenant, metering/billing, giám sát và quản lý phiên bản.
- **Region:** tenant được gán khu vực dữ liệu theo yêu cầu đã xác nhận; đường dữ liệu và backup phải tuân theo ràng buộc vị trí đã chọn.

Đây là **phương án mẫu có điều kiện**, không phải khuyến nghị chung cho mọi SaaS. Điểm cần chứng minh bằng PoC là shared schema vẫn đáp ứng cô lập và hiệu năng, đồng thời đường định tuyến enterprise không nhầm tenant.

## 5. Kiến trúc tham chiếu: control plane và data plane

~~~mermaid
flowchart TB
    CLIENT[Web / Mobile / API Client] --> EDGE[DNS / WAF / API Gateway]
    EDGE --> AUTH[Identity Provider / Auth]
    EDGE --> API[Stateless API]

    subgraph CP[Control plane]
      REG[Tenant registry / Lifecycle]
      CFG[Plan / Quota / Feature config]
      BILL[Metering / Billing]
      ADMIN[Admin / Audit / Support]
    end

    API --> REG
    API --> CFG
    API --> ROUTER[Data router theo tenant]
    ROUTER --> POOL[(Shared DB - Standard)]
    ROUTER --> DED[(Dedicated DB - Enterprise)]

    API --> CACHE[Cache có tenant namespace]
    API --> BUS[Queue / Event có tenant context]
    BUS --> WORKER[Worker áp quyền và quota]
    WORKER --> ROUTER
    API --> OBJ[Object storage có phân vùng tenant]
    WORKER --> OBJ

    API --> METER[Usage events]
    WORKER --> METER
    METER --> BILL
    API --> OBS[Metrics / Logs / Traces / Alerts]
    WORKER --> OBS
    REG --> ADMIN
~~~

**Control plane** quản lý tenant (đăng ký, gói dịch vụ, policy, cấu hình, provisioning, billing, hỗ trợ); **data plane** xử lý giao dịch và dữ liệu nghiệp vụ. Ranh giới hai plane giúp đội ngũ kiểm soát vòng đời tenant và phát hành nền tảng, nhưng control plane có thể trở thành phụ thuộc trọng yếu. Cần quyết định rõ trạng thái nào được cache hoặc dùng được khi registry tạm gián đoạn.

Ví dụ, một request đã xác thực có thể dùng cấu hình tenant được cache trong TTL ngắn nếu chính sách cho phép; việc thay đổi trạng thái **suspended** hoặc thu hồi quyền cần cơ chế invalidation phù hợp để tránh chậm hiệu lực ngoài quy định.

### 5.1. Đường đi của một yêu cầu

~~~mermaid
sequenceDiagram
    participant U as User
    participant G as Gateway
    participant A as API
    participant I as Tenant registry/IAM
    participant D as Data access
    participant DB as DB
    U->>G: HTTPS + access token
    G->>A: Forward request + claims đã kiểm chứng
    A->>I: Xác nhận user thuộc tenant được chọn
    I-->>A: Tenant context / plan / quyền
    A->>A: Kiểm tra quyền hành động và quota
    A->>D: Gửi tenant context đã xác thực
    D->>DB: Query trong ranh giới tenant
    DB-->>D: Dữ liệu đúng tenant
    D-->>A: Kết quả
    A-->>U: Response
~~~

Thông số tenant có thể đến từ hostname, đường dẫn, tham số hoặc chọn tổ chức trong giao diện. **Không tin tenant_id chỉ vì client gửi lên.** Backend phải đối chiếu tenant đã chọn với danh sách thành viên, trạng thái tenant và quyền của người gọi.

## 6. Mô hình danh tính, phân quyền và ngữ cảnh tenant

Cần phân biệt ba khái niệm:

- **Identity**: ai đang gọi? Ví dụ user id hoặc service identity.
- **Tenant context**: lời gọi đang thao tác thay mặt tổ chức nào?
- **Authorization**: với vai trò/quyền hiện tại, caller được làm gì trên tài nguyên thuộc tổ chức đó?

Một người dùng có thể là quản trị viên của tenant A, nhân viên của tenant B và không có quyền trong tenant C. Không nên gắn mỗi user vào đúng một tenant nếu nghiệp vụ cần nhiều tổ chức.

Ví dụ các thực thể:

| Thực thể | Trường cốt lõi | Vai trò |
| --- | --- | --- |
| tenants | id, status, tier, region, created_at | Định nghĩa tổ chức và chính sách |
| users | id, identity_subject, email | Định danh người dùng toàn cục |
| memberships | tenant_id, user_id, role, status | Ràng buộc người dùng với tenant và quyền |
| service_identities | id, tenant_scope, permissions | Tích hợp máy–máy có phạm vi |
| api_keys | id, tenant_id, scopes, expires_at, revoked_at | Quản trị khóa API tenant với vòng đời rõ |
| audit_events | tenant_id, actor_id, action, target, timestamp | Kiểm toán thay đổi và truy cập |

**Luồng đề xuất:**

1. Xác thực token theo issuer, audience, chữ ký, thời hạn và chính sách phiên; dùng TLS.
2. Xác định tenant cần truy cập; backend xác minh caller được phép chọn tenant đó.
3. Tính quyền dựa trên membership/role và policy cụ thể cho tài nguyên.
4. Tạo tenant context đáng tin (tenant id, user/service id, quyền, correlation id) và truyền xuyên tầng ứng dụng.
5. Khi gọi service khác hoặc đưa tác vụ vào queue, truyền tenant context bằng cơ chế có kiểm soát, bảo đảm nơi nhận xác thực nguồn và không thể sửa giá trị tùy tiện.
6. Tại tầng dữ liệu, tiếp tục thực thi ranh giới tenant độc lập với kiểm tra ở API.

**Quyền hỗ trợ liên tenant:** nhân viên vận hành cần công cụ chẩn đoán có lý do, phạm vi được duyệt, thời hạn truy cập, logging và quy trình kiểm soát. Không nên dùng tài khoản superadmin mặc định để truy cập mọi tenant.

## 7. Thiết kế dữ liệu đa tenant với shared schema

### 7.1. Nguyên tắc mô hình hóa

Với shared schema, mọi bảng chứa dữ liệu riêng của khách hàng cần có thuộc tính tenant rõ ràng. Một khóa ngoại chỉ theo **order_id** không đủ nếu hai tenant có các bản ghi trùng định danh hoặc mã có thể đoán. Nên thiết kế ràng buộc nhất quán theo cặp **(tenant_id, id)** ở nơi phù hợp.

Ví dụ PostgreSQL tối giản (các loại dữ liệu và index sẽ được điều chỉnh theo workload thực tế):

~~~sql
CREATE TABLE orders (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    external_order_no text NOT NULL,
    customer_id uuid NOT NULL,
    amount numeric(18, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, external_order_no)
);

CREATE TABLE order_lines (
    tenant_id uuid NOT NULL,
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, order_id)
      REFERENCES orders (tenant_id, id)
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at DESC);
~~~

Khóa ngoại trên ngăn một dòng chi tiết có tenant_id A vô tình trỏ đến đơn hàng tenant B. Mọi index, unique constraint và phân vùng dữ liệu phải được xem xét theo mô hình truy vấn từng tenant; không phải cột nào cũng phải ghép tenant_id vào index nếu có bằng chứng khác, nhưng phạm vi tính duy nhất cần được nêu rõ.

### 7.2. Phòng thủ nhiều lớp với Row Level Security

PostgreSQL hỗ trợ **Row Level Security (RLS)**, có thể làm lớp bảo vệ bổ sung:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation ON orders
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    );

ALTER TABLE order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_lines FORCE ROW LEVEL SECURITY;

CREATE POLICY order_lines_tenant_isolation ON order_lines
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    );
~~~

Một giao dịch ứng dụng có thể thiết lập ngữ cảnh đã được backend xác nhận trước mọi truy vấn:

~~~sql
BEGIN;
-- :verified_tenant_id là tham số được backend xác nhận,
-- không lấy trực tiếp từ header hoặc query parameter chưa kiểm chứng.
SELECT set_config('app.tenant_id', :verified_tenant_id, true);

SELECT id, amount, status
FROM orders
WHERE tenant_id = :verified_tenant_id;

COMMIT;
~~~

Đây là **mẫu minh họa**, không phải chương trình SQL chạy độc lập: cú pháp **:verified_tenant_id** là placeholder do driver bind an toàn. Giá trị cấu hình được đặt trong transaction và tự hết hiệu lực sau transaction; cần kiểm tra cơ chế connection pool, transaction pooling và mọi đường truy cập khác để tránh tái sử dụng ngữ cảnh sai.

Các lưu ý bảo mật bắt buộc:

- Vai trò truy cập của ứng dụng **không** sở hữu bảng, không là superuser, không có **BYPASSRLS**; không cho phép truy cập bypass qua vai trò khác, view hoặc hàm đặc quyền thiếu kiểm soát.
- Chính sách RLS không tự xác minh user là thành viên tenant. Ứng dụng phải chỉ thiết lập tenant context sau xác thực/phân quyền, không cho phép client gửi SQL hoặc tự đặt ngữ cảnh.
- Chạy thử SELECT, UPDATE, DELETE, INSERT với tenant hợp lệ, tenant sai, không có context và khi dùng connection pool.
- Các job analytics/backup dùng vai trò hoặc pipeline riêng phải được kiểm soát, kiểm toán, không tái sử dụng credential có quyền truy cập toàn cục trong API.
- Xem xét trigger, stored procedure, reporting view, migration script và export data; đây đều là đường có thể vượt qua kiểm soát ở code nghiệp vụ.

### 7.3. Hai đường dữ liệu Standard và Enterprise

Ứng dụng nên gọi một **data-access abstraction** thống nhất. Bộ định tuyến dữ liệu lấy tenant id từ context đã xác thực, tra tenant registry đã kiểm soát và chọn kết nối tương ứng:

~~~text
Standard tenant -> shared DB endpoint -> RLS + tenant-scoped queries
Enterprise tenant -> dedicated DB endpoint -> DB credentials của tenant/pool tương ứng
~~~

Không dùng id tenant do người dùng sửa tự do để tạo chuỗi kết nối, tên schema hoặc tên bảng. Phần cấu hình định tuyến phải có quyền ghi hạn chế, quản lý bí mật và cơ chế phản ứng khi mapping bị lỗi. Định tuyến sang CSDL riêng vẫn cần kiểm tra tenant ở lớp ứng dụng, vì lỗi mapping có thể làm lộ dữ liệu.

## 8. Cô lập ngoài cơ sở dữ liệu: cache, queue, file và tìm kiếm

Nhiều sự cố rò rỉ chéo tenant bắt nguồn từ hệ thống phụ, không phải truy vấn chính.

| Thành phần | Rủi ro | Biện pháp |
| --- | --- | --- |
| **Cache** | Hai tenant dùng cùng khóa order:123, nhận nhầm dữ liệu | Key namespace theo tenant và phiên bản dữ liệu; kiểm soát quyền trước khi trả kết quả |
| **Queue/event** | Worker nhận job không có tenant id hoặc xử lý sai tenant | Tenant context đã kiểm chứng, schema sự kiện, idempotency, dead-letter queue theo chính sách |
| **Object storage** | URL hoặc key đoán được, cho phép tải file tenant khác | Chính sách IAM, prefix/bucket riêng theo yêu cầu, URL ngắn hạn, xác thực quyền tải |
| **Full-text search** | Truy vấn trả tài liệu tenant khác | Bộ lọc tenant bắt buộc ở chỉ mục/truy vấn và test isolation |
| **Data warehouse** | ETL làm mất tenant_id hoặc join liên tenant | Tenant lineage, quyền xem báo cáo, kiểm tra transform và xuất dữ liệu |
| **Logging / tracing** | Log ghi dữ liệu nhạy cảm hoặc bảng điều khiển cho mọi khách xem chung | Redaction, phân quyền dashboard, tenant dimension và retention phù hợp |
| **Webhook / email** | Callback gửi tới endpoint tenant khác | Endpoint mapping theo tenant, chữ ký, retry tách tenant và kiểm tra cấu hình |
| **Feature flags** | Bật nhầm tính năng hoặc phiên bản cho tenant khác | Flags có scope và audit; fallback rõ ràng |

**Ví dụ cache key:** tenant:8f...:order:123:version:2. Key chỉ là một lớp phòng thủ; không vì có tiền tố tenant mà được bỏ qua xác thực quyền truy cập.

**Idempotency:** nếu queue phân phối lại message, worker phải tránh tạo đơn trùng. Chọn idempotency key có phạm vi tenant, định nghĩa thời hạn lưu khóa và dùng ràng buộc nhất quán trong CSDL. Không giả định message broker cung cấp “exactly once” xuyên cả nghiệp vụ và CSDL nếu chưa chứng minh.

## 9. Noisy neighbor và cách phân bổ tài nguyên

**Noisy neighbor** xảy ra khi một tenant dùng quá nhiều CPU, kết nối DB, IOPS, cache hoặc queue khiến tenant khác tăng độ trễ. Chia sẻ tài nguyên làm chi phí thấp hơn khi sử dụng hợp lý, nhưng phải có khả năng đo và kiểm soát sự tranh chấp.

Những lớp điều tiết đề xuất:

- **Ở gateway/API:** rate limit và quota theo tenant, người dùng và loại tác vụ; có phản hồi rõ khi vượt giới hạn.
- **Ở worker:** giới hạn concurrency mỗi tenant, tách hàng đợi hoặc phân bổ trọng số khi phù hợp, áp dụng backpressure.
- **Ở CSDL:** giới hạn kết nối, timeout cho truy vấn tốn kém, index theo mẫu truy cập, theo dõi truy vấn tiêu tốn tài nguyên.
- **Ở cache/storage:** tránh một tenant đẩy toàn bộ dữ liệu tenant khác khỏi cache, đặt TTL/quota hợp lý.
- **Ở gói Enterprise:** cân nhắc tách instance/cluster hoặc dùng CSDL riêng nếu yêu cầu SLO và khả năng chi trả xác nhận được.

Một tenant Enterprise chiếm 60% tải không nhất thiết phải chuyển sang compute riêng ngay; cần đo p95/p99 của **các tenant khác trong lúc tenant lớn tăng tải** trước khi chọn biện pháp.

### 9.1. Ví dụ phân bổ công suất

Giả sử tải thường là 400 req/s, burst 1.000 req/s trong 5 phút. Nếu công suất xử lý hữu dụng thực tế là 700 req/s khi vẫn đạt SLO, tốc độ tích hàng đợi ở burst có thể xấp xỉ:

**(1.000 − 700) × 300 giây = 90.000 yêu cầu**

Phép tính này chỉ có ý nghĩa nếu giao dịch được phép xếp hàng và các yêu cầu mới vẫn tới đều. API đồng bộ có timeout có thể bị lỗi trước khi hàng đợi tích đủ. Muốn đánh giá thiết kế, phải phân loại request nào **có thể chuyển sang bất đồng bộ**, dự báo thời gian tiêu backlog và kiểm thử tải thật.

Nếu sau burst tốc độ đến còn 400 req/s và công suất xử lý 700 req/s, lý thuyết cần **90.000 / (700 − 400) = 300 giây** để xóa backlog, chưa kể retry, tác vụ ưu tiên và giới hạn downstream. Cần kiểm tra latency tổng thời gian hoàn thành nghiệp vụ, không chỉ độ trễ trả HTTP 202.

## 10. Mạng, vùng dữ liệu, bảo mật và khả năng phục hồi

Chọn region theo nơi lưu dữ liệu, người dùng và dịch vụ sẵn có. Tách môi trường dev/test/prod và phân đoạn mạng. Các thành phần dữ liệu chỉ mở luồng cần thiết; tài nguyên private không mặc nhiên trở thành an toàn nếu IAM hoặc ứng dụng cấu hình sai.

Với SaaS, cần xem xét các failure domain:

| Sự cố | Phạm vi ảnh hưởng có thể gặp | Chiến lược giảm thiểu |
| --- | --- | --- |
| Một API instance lỗi | Một phần lưu lượng | Health check, tự thay thế và đủ bản sao |
| Một zone lỗi | Ứng dụng hoặc CSDL đặt tại zone đó | Cân nhắc đa AZ theo SLO/RTO, diễn tập |
| Shared DB cạn kết nối | Toàn bộ Standard tenant | Pooling, giới hạn, capacity plan, cảnh báo |
| Tenant gửi batch quá lớn | Nhiều tenant nếu tranh chấp | Quota, hàng đợi công bằng, tách worker |
| Tenant registry lỗi | Onboarding và request cần tra cứu policy | Cache kiểm soát, thiết kế degraded mode, DR |
| Region lỗi | Nhiều tenant thuộc region | DR theo ràng buộc dữ liệu và ngân sách |
| Sai quyền quản trị | Nhiều tenant | Least privilege, review thay đổi, audit và break-glass |
| Khôi phục shared DB từ backup | Có thể ảnh hưởng các tenant khác | Thiết kế tenant-level restore và đối soát riêng |

**RTO 2 giờ, RPO 15 phút** phải có kịch bản kiểm chứng rõ: sự cố nào, cách phát hiện, thời điểm bắt đầu, dữ liệu nào được tính là mất và các bước khôi phục. Backup tự động chưa chứng minh restore được trong RTO. Với shared database, **khôi phục riêng một tenant** có thể cần cơ chế trích xuất và nạp lại có kiểm soát, vì restore toàn bộ database sẽ ảnh hưởng mọi tenant khác.

Đối với yêu cầu lưu trú dữ liệu, phải tính cả bản sao lưu, log, cache, tìm kiếm, dữ liệu phân tích và nhà cung cấp phụ trợ; không chỉ location của primary DB. Cần xác nhận quy định/hợp đồng thực tế, tránh giả định mọi khách đều có cùng nghĩa vụ.

## 11. Vòng đời tenant và control plane

SaaS cần quản lý tenant như một thực thể có trạng thái rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Provisioning: Xác nhận đăng ký
    Provisioning --> Active: Cấp phát và kiểm thử thành công
    Provisioning --> Failed: Cấp phát lỗi
    Failed --> Provisioning: Thử lại có kiểm soát
    Active --> Suspended: Quá hạn/chính sách
    Suspended --> Active: Khôi phục hợp lệ
    Active --> Offboarding: Kết thúc hợp đồng
    Suspended --> Offboarding: Kết thúc hợp đồng
    Offboarding --> Retained: Lưu trữ theo chính sách
    Retained --> Deleted: Hết thời hạn / được phép xóa
    Deleted --> [*]
~~~

Các bước quan trọng:

1. **Onboarding:** xác minh thông tin tenant, vùng dữ liệu, gói và quyền; tạo cấu hình/khóa/bản ghi registry; cấp kết nối DB khi cần.
2. **Provisioning:** tạo tài nguyên bằng IaC hoặc workflow tự động có thể chạy lại an toàn; ghi kết quả từng bước và hỗ trợ retry.
3. **Activation:** chạy smoke test về định danh, truy cập dữ liệu, log và hóa đơn trước khi tenant nhận lưu lượng.
4. **Change plan:** cập nhật quota/tính năng và lịch áp dụng; có audit, không làm mất dữ liệu.
5. **Suspend:** chặn thao tác không được phép nhưng vẫn tôn trọng quyền xem/xuất theo hợp đồng; xác định tác vụ nền có phải dừng không.
6. **Offboarding:** xuất dữ liệu, thu hồi token/key/webhook, thanh toán đối soát và xử lý quyền lưu giữ.
7. **Delete:** xóa theo chính sách, xét backup, object storage, log và legal hold; ghi bằng chứng thực hiện.

**Provisioning cần idempotent:** nếu tạo CSDL thành công nhưng tạo DNS thất bại, chạy lại không được tạo hai tenant hoặc hai khoản billing. Nên có workflow state, correlation id và thao tác bù trừ khi cần.

## 12. Nâng cấp, cấu hình và tính năng theo tenant

Với mã ứng dụng chung, SaaS có lợi thế phát hành một lần cho nhiều tổ chức, nhưng một lỗi có thể lan rộng. Vì vậy:

- Dùng **một codebase** và cấu hình theo tenant khi khả thi; tránh fork mã theo khách hàng nếu chưa có lý do bắt buộc.
- Feature flag nên có phạm vi tenant hoặc nhóm tenant, có người sở hữu và thời hạn xóa flag cũ.
- Database migration phải tương thích với các phiên bản ứng dụng đang hoạt động trong quá trình rollout.
- Chọn thứ tự phát hành: môi trường thử → tenant nội bộ → nhóm canary → nhóm Standard → nhóm Enterprise, tùy rủi ro.
- Đối với CSDL riêng, tự động hóa schema migration theo lô, giám sát tiến độ và xử lý tenant thất bại.
- Tính năng tùy biến cần được kiểm soát bằng cấu hình và API extension có sandbox/quota nếu hỗ trợ plugin; tránh cho phép chạy mã tùy ý cùng quyền với nền tảng.

**Ví dụ chuyển schema an toàn:** bổ sung cột mới cho phép null, triển khai mã tương thích hai phiên bản, backfill từng phần, kiểm chứng, sau đó siết ràng buộc. Việc xóa cột ngay trong một lần phát hành có thể làm phiên bản API cũ thất bại.

## 13. Chiến lược di chuyển từ single-tenant sang multi-tenant

Không nên thay toàn bộ ứng dụng, CSDL, định danh và billing trong một đợt nếu chưa chứng minh đường chuyển đổi. Cần tạo các **cổng kiểm soát**:

### Giai đoạn A – Khảo sát và thiết kế

- Kiểm kê bảng, khóa, API, SQL, cache, queue, object storage, báo cáo và tài khoản vận hành đang ngầm giả định một tenant.
- Xác định mọi bảng/dữ liệu thuộc tenant, dữ liệu dùng chung thật sự và quy tắc chia sẻ có chủ đích.
- Chọn tenant registry, định danh, membership, hình thức định tuyến và mô hình dữ liệu.
- Lập kế hoạch backup/restore, versioning, quan sát, đo chi phí, yêu cầu region và đặc quyền.

### Giai đoạn B – Làm cho ứng dụng hiểu tenant

- Bổ sung tenant context được xác thực vào pipeline request và background job.
- Thay truy vấn dữ liệu bằng tenant-scoped repository/data-access; kiểm soát qua RLS hoặc cơ chế DB tương đương.
- Bổ sung tenant_id cho bảng nghiệp vụ, tạo composite key/foreign key/index đúng phạm vi.
- Đổi cache key, đường dẫn object storage, search index, webhook và sự kiện để mang phạm vi tenant.
- Thêm kiểm thử truy cập chéo tenant và kiểm thử role.

### Giai đoạn C – Chuẩn bị dữ liệu và tenant đầu tiên

Với một khách hàng ban đầu:

1. Gán một **tenant_id ổn định** và map mọi bản ghi hiện hữu.
2. Sao lưu và kiểm thử restore trước backfill.
3. Thực hiện backfill theo lô, kiểm chứng bảng nào được phép thiếu tenant_id.
4. Đối soát số bản ghi, tổng tiền, khóa ngoại, file và kết quả nghiệp vụ.
5. Kiểm tra các truy vấn/worker cũ không được phép chạy ngoài tenant context.
6. Bật enforcement khi đã chứng minh dữ liệu và truy cập đúng phạm vi.
7. Chạy canary/pilot có giám sát và đường quay lui phù hợp.

**Cảnh báo:** Khi dữ liệu đã có ghi mới trên kiến trúc đích, quay lại CSDL nguồn cũ không chỉ là chuyển DNS. Phải có cách đồng bộ ngược, restore có kiểm soát hoặc forward fix; xác định mốc không thể quay lui và người phê duyệt.

### Giai đoạn D – Mở rộng nhiều tenant

- Onboard tenant thử nghiệm mới với dữ liệu tổng hợp; chủ động truy cập sai tenant để kiểm tra từ chối.
- Triển khai tenancy-aware metering, quota và runbook.
- Thử hai tenant đồng thời, sau đó nhiều tenant với mẫu tải lệch nhau.
- Di chuyển khách hàng hiện hữu theo wave phù hợp, theo dõi từng tenant và điều kiện go/no-go.
- Chỉ ngừng hạ tầng cũ khi đáp ứng đối soát, lưu giữ, rollback và yêu cầu hợp đồng.

### Sơ đồ quyết định chuyển đổi

~~~mermaid
flowchart TD
    A[Inventory và kiến trúc đích] --> B[PoC tenant isolation + hiệu năng]
    B --> C{PoC có bằng chứng đạt?}
    C -- Không --> D[Sửa mô hình cô lập, định tuyến hoặc compute]
    D --> B
    C -- Có --> E[Thêm tenant context, schema và kiểm soát]
    E --> F[Backfill + đối soát + restore rehearsal]
    F --> G{Các hard gate đạt?}
    G -- Không --> H[Khắc phục và kiểm tra lại]
    H --> F
    G -- Có --> I[Canary tenant đầu tiên]
    I --> J[Đo SLO, rủi ro và dữ liệu]
    J --> K{Go / No-go}
    K -- No-go --> L[Rollback / Forward fix theo dữ liệu]
    K -- Go --> M[Mở wave nhiều tenant]
    M --> N[Quan sát, tối ưu và bàn giao]
~~~

## 14. Kiểm thử bắt buộc trước khi mở rộng

Một test suite multi-tenant cần kiểm tra cả **truy cập đúng** và **đường vượt rào**.

| Bài kiểm tra | Cách tiến hành | Tiêu chí đạt |
| --- | --- | --- |
| Truy cập API chéo tenant | User A gọi id đơn của B qua API, GraphQL, export | Không trả nội dung B; trạng thái theo policy và audit phù hợp |
| Truy vấn thiếu tenant context | Chạy repository/SQL không gắn tenant hợp lệ | Không đọc/ghi được dữ liệu tenant |
| RLS và pooling | Lặp request A/B trên cùng pool với concurrency cao | Không có kết quả chéo tenant; transaction context không rò |
| Khóa ngoại | Tạo line tenant A trỏ tới order tenant B | CSDL từ chối |
| Cache/search | Trùng business id giữa A/B, cùng truy vấn | Mỗi tenant chỉ thấy dữ liệu của mình |
| Queue và retry | Job A retry, job B chạy cùng lúc, worker restart | Không trộn tenant, không xử lý trùng ngoài chính sách |
| Object storage | Thử truy cập URL/key của tenant khác | Bị từ chối theo policy và kiểm tra ứng dụng |
| SSO/membership | User thuộc A/B chọn C hoặc bị thu hồi quyền | Backend không chấp nhận context không hợp lệ |
| Rate limit | Tenant lớn tạo tải vượt quota | Tenant khác giữ SLO theo giới hạn bài thử |
| Autoscaling | 400 req/s, burst 1.000 req/s/5 phút | P95, error rate và capacity đạt ngưỡng đã chốt |
| Backup/restore | Khôi phục sau lỗi dữ liệu và lỗi hạ tầng | Đạt RTO/RPO đã định; đối soát chính xác |
| Tenant restore | Khôi phục dữ liệu một Standard tenant | Không ghi đè dữ liệu tenant khác |
| Tạo/ngừng tenant | Provisioning fail giữa chừng, chạy lại, suspend | Không tạo duplicate, không phát sinh truy cập sai |
| Billing | Phát lại event, thiếu event, tenant đổi gói | Usage không tính hai lần và truy vết được |

**Kiểm thử phân tách tenant** không kết thúc ở test case GET. Phải kiểm tra những đường ít gặp như bulk API, reporting, import/export, webhook, file upload, admin console và quyền thực thi background job.

### 14.1. Kịch bản noisy-neighbor minh họa

Tạo ba tenant thử nghiệm: A dùng 70% lưu lượng, B và C mỗi bên 15%. Sau đó tăng đột biến A lên nhiều lần trong khoảng ngắn và đo p95/p99 của B/C, queue lag, DB connections và tỷ lệ lỗi. Điều kiện thành công phải được xác lập từ mục tiêu sản phẩm, chẳng hạn **p95 của B/C không vượt 300 ms ở tải cho phép**. Nếu không đạt, cân nhắc quota, tách queue/worker, giới hạn DB và phân tầng dịch vụ.

### 14.2. Hard gates trước go-live

Không phê duyệt chỉ dựa trên bảng điểm tổng hợp nếu còn:

- Bằng chứng truy cập chéo tenant hoặc đường bypass dữ liệu chưa xử lý.
- Chưa hoàn thành đối soát dữ liệu và thử restore.
- Không chứng minh được bảo mật quản trị, IAM, quản lý secrets, audit hoặc yêu cầu lưu trú dữ liệu áp dụng.
- Chưa có quy trình xử lý sự cố, rollback/forward fix và người chịu trách nhiệm.
- Không đo được chất lượng dịch vụ và tác động noisy neighbor ở tải mục tiêu.
- Chưa xác thực tính đúng đắn metering/billing cho nghiệp vụ có thu phí.

## 15. Quan sát, đo lường và hỗ trợ vận hành

Nền tảng cần nhìn được hai cấp độ:

- **Toàn hệ thống:** request rate, p50/p95/p99 latency, error rate, CPU/memory, DB saturation, queue lag, chi phí và trạng thái vùng.
- **Theo tenant:** lưu lượng, lỗi, giới hạn gói, latency theo nhóm tenant, trạng thái onboarding, chi phí/usage và sự kiện quản trị.

Đính **tenant_id** vào log, trace và sự kiện nghiệp vụ khi phù hợp, nhưng cẩn trọng với cardinality của metrics. Với hàng trăm nghìn tenant, không nên mặc định tạo mọi time-series theo tenant, endpoint và user; cần sampling, aggregation hoặc bảng phân tích phù hợp. Quyền xem dashboard phải được phân vùng: người dùng tenant A không thấy log hoặc số liệu nhạy cảm của B.

**SLO minh họa:** 99,9% khả dụng theo tháng của API tạo đơn, đo từ những request đủ điều kiện, định nghĩa rõ thế nào là yêu cầu thành công và phạm vi đo. Error budget phải được dùng để điều chỉnh tốc độ phát hành, cảnh báo và xử lý sự cố. Nếu phục vụ các tier khác nhau, có thể cần SLO và cơ chế hỗ trợ khác nhau nhưng phải công bố nhất quán.

## 16. Chi phí, metering và unit economics

Mô hình pool tiết kiệm chi phí nhờ chia sẻ tài nguyên, nhưng cần kiểm soát phần chi phí biến đổi theo số tenant và mức sử dụng. Bảng tính nên tách:

| Nhóm | Thành phần |
| --- | --- |
| Cố định nền tảng | Gateway, control plane, CI/CD, quan sát, trực sự cố |
| Theo tenant | Cấu hình, storage tối thiểu, email, khóa, chi phí hỗ trợ |
| Theo mức sử dụng | Compute, DB I/O, request, queue, object storage, truyền dữ liệu |
| Theo lựa chọn cô lập | Dedicated DB/compute/region, backup riêng, mạng riêng |
| Theo chuyển đổi | Chạy hai hệ, migrate dữ liệu, thử nghiệm, đào tạo |
| Theo rủi ro | Dự phòng capacity, phục hồi, hỗ trợ cao điểm |

**Ví dụ giả định** (chỉ dùng để thực hành tính toán, không phải đơn giá thật của cloud provider):

- Phí nền tảng chung: 6.000 đơn vị tiền tệ/tháng.
- Chi phí nền tảng theo tenant: 30 đơn vị/tenant/tháng.
- Chi phí biến đổi: 0,08 đơn vị/1.000 yêu cầu đã xử lý.
- 120 tenant phát sinh tổng 48 triệu yêu cầu/tháng.

Ước tính tháng:

**6.000 + (120 × 30) + (48.000.000 / 1.000 × 0,08) = 13.440 đơn vị/tháng.**

Bình quân là **112 đơn vị/tenant/tháng**, nhưng không có nghĩa mỗi tenant thực tế tốn bằng nhau. Tenant tải lớn phải được đo theo usage, đặc biệt với DB, storage, bandwidth và hỗ trợ. Nếu mô hình silo giả định mất 180 đơn vị/tenant/tháng, chi phí nền tảng là **21.600 đơn vị/tháng** trước khi cộng chi phí dùng chung khác; hai con số chỉ so được sau khi chuẩn hóa khả năng cung cấp dịch vụ và các khoản chi phí được tính.

**Metering** nên dùng event có định danh, tenant id, loại dịch vụ, thời điểm, số lượng, nguồn phát và quy tắc xử lý trùng. Billing cần quy trình đối soát với giao dịch nghiệp vụ; không dựa vào số request trong access log làm nguồn duy nhất nếu mô hình tính giá là “đơn hàng hoàn thành”. Có ngân sách/cảnh báo và quy trình xử lý tenant gây tăng đột biến chi phí.

## 17. Sổ rủi ro thiết kế mẫu

Đánh giá L (khả năng xảy ra) và I (mức tác động) từ 1–5, dùng **L × I** để ưu tiên thảo luận; không xem điểm này là xác suất thất bại. Rủi ro pháp lý và quyền riêng tư còn phải qua hard gate riêng.

| Rủi ro | L × I | Cách kiểm chứng/giảm thiểu | Owner |
| --- | ---: | --- | --- |
| Lộ dữ liệu chéo tenant do SQL thiếu filter | 4 × 5 = 20 | RLS, composite FK, security tests, review quyền | Security + DBA |
| Background job chạy sai tenant | 4 × 5 = 20 | Signed/verified context, schema event, test retry | Backend lead |
| Tenant lớn làm shared DB cạn kết nối | 4 × 4 = 16 | Quota, pool limit, load test theo tenant | Platform + DBA |
| Cấu hình registry định tuyến sai CSDL | 3 × 5 = 15 | Kiểm soát thay đổi, mapping có kiểm chứng, audit | Platform lead |
| Khôi phục một tenant gây mất dữ liệu tenant khác | 3 × 5 = 15 | Rehearsal tenant restore, tooling và đối soát | DBA + SRE |
| Sai chi phí do thiếu metering hoặc event trùng | 4 × 4 = 16 | Idempotency, reconciliation, usage audit | Billing owner |
| Triển khai schema mới làm một nhóm tenant lỗi | 3 × 4 = 12 | Expand/contract, canary, rollback | Release manager |
| Sao lưu/log đặt sai khu vực dữ liệu | 3 × 5 = 15 | Inventory data flow, policy và review tuân thủ | Security + Compliance |

Sau khi thử nghiệm, ghi **rủi ro còn lại**, người chấp nhận và thời điểm xem xét. Một thiết kế có thể đạt hiệu năng nhưng vẫn bị chặn vì không đủ bằng chứng cô lập hoặc phục hồi.

## 18. Bộ bài tập cần nộp

Hãy dùng tình huống ở phần 2 để hoàn thiện các nhiệm vụ sau; nếu thay đổi giả định, ghi rõ lý do và hệ quả.

### Bài tập A – Định nghĩa kiến trúc (30 điểm)

1. Vẽ kiến trúc gồm gateway, identity, tenant registry, API, worker, routing, shared/dedicated DB, storage, billing, observability.
2. Chọn silo/pool/bridge riêng cho compute và dữ liệu; nêu ba đánh đổi quan trọng.
3. Mô tả cách định tuyến tenant đến đúng vùng dữ liệu và đường xử lý nếu registry gặp sự cố.
4. Chọn tối thiểu hai cơ chế giảm noisy neighbor và nêu thước đo kiểm tra.

### Bài tập B – Bảo mật và dữ liệu (25 điểm)

1. Thiết kế bảng tenant, users, memberships, orders và order_lines với khóa và ràng buộc.
2. Trình bày luồng xác thực, chọn tenant, phân quyền và thiết lập tenant context.
3. Nêu cách bảo vệ cache, queue, file, search, log và reporting; viết tối thiểu năm ca kiểm thử chéo tenant.
4. Đề xuất chiến lược backup và restore **một tenant** trong shared database.

### Bài tập C – Kế hoạch chuyển đổi (25 điểm)

1. Lập roadmap bốn giai đoạn và điều kiện go/no-go.
2. Chỉ ra cách backfill tenant_id, xác thực nhất quán dữ liệu và xử lý mã/ID cũ.
3. Mô tả rollback hoặc forward fix khi hệ mới đã ghi dữ liệu.
4. Lập kế hoạch pilot với tenant nội bộ, khách hàng tự nguyện và wave tiếp theo.

### Bài tập D – Chất lượng và chi phí (20 điểm)

1. Thiết kế kiểm thử ở 400 req/s và burst 1.000 req/s, đo SLO theo tenant.
2. Diễn tập hỏng DB/zone, chứng minh RTO 2 giờ và RPO 15 phút theo tình huống.
3. Tính chi phí giả định ở phần 16; kiểm tra tác động khi một tenant tăng sử dụng gấp năm lần.
4. Xây ba metric và hai alert cho dịch vụ, cùng hai metric để quản trị chi phí.

**Tiêu chí chấm:** kết quả cần thể hiện ranh giới tin cậy đúng, phương án cô lập nhất quán, trade-off có căn cứ, kiểm thử có ngưỡng đo được, kế hoạch thực thi khả thi và có dữ liệu để quyết định. Điểm nội dung mẫu không thay thế yêu cầu an toàn: phương án lộ dữ liệu chéo tenant không được chấp nhận dù đạt các tiêu chí khác.

## 19. Hướng giải tham khảo và Architecture Decision Record

Đây là **một lời giải mẫu**, học viên có thể chọn phương án khác nếu biện minh được bằng yêu cầu, chi phí và kiểm thử.

| Quyết định | Hướng chọn | Lý do và điều kiện |
| --- | --- | --- |
| Mô hình tenancy | Bridge | Standard pool để tối ưu chi phí; Enterprise có lối nâng cấp sang DB riêng |
| Authentication | IdP dùng chung, membership per tenant | Người dùng có thể thuộc nhiều tenant; backend xác minh tenant được chọn |
| API và worker | Dùng chung, stateless, quota tenant | Phát hành đồng nhất, autoscale; kiểm tra noisy neighbor |
| Dữ liệu Standard | Shared PostgreSQL schema với tenant_id + RLS | Quản trị hiệu quả; cần lớp phòng thủ và test mạnh |
| Dữ liệu Enterprise | Dedicated DB và secret/route theo tenant | Cô lập dữ liệu và phục hồi độc lập; chi phí cao hơn |
| Cache/file/search | Namespace và authorization theo tenant | Bảo vệ những đường dễ bị bỏ sót |
| Tenant lifecycle | Control plane + provisioning idempotent | Onboard nhanh, audit rõ và xử lý lỗi có kiểm soát |
| Migration | Backfill, đối soát, canary rồi wave | Giảm rủi ro chuyển đổi và phát hiện lỗi sớm |
| Reliability | Multi-AZ theo yêu cầu và restore rehearsal | Kiểm chứng được RTO/RPO và hạn chế blast radius |
| Chi phí | Metering + quota + dashboards | Theo dõi unit economics và ngăn chi phí bất thường |

Một bản **ADR** ngắn có thể ghi:

~~~yaml
adr:
  id: ADR-SaaS-005
  title: "Mô hình bridge cho SaaS đa tenant"
  status: proposed
  context: "120 tenant năm đầu, hai tier, cần cô lập và tăng tốc onboarding"
  decision:
    standard: "Shared application + tenant-scoped shared DB"
    enterprise: "Shared application + dedicated DB when required"
    isolation: ["Backend authorization", "RLS", "tenant-scoped dependencies"]
  consequences:
    benefits: ["Giảm lặp hạ tầng", "Ra mắt tenant nhanh", "Có lựa chọn cô lập cao"]
    costs: ["Định tuyến phức tạp", "Test chéo tenant", "Quản lý migrations hai mô hình"]
  proof_needed:
    - "Không thể truy cập chéo tenant trong mọi đường dữ liệu"
    - "Đạt p95 và giới hạn lỗi dưới peak/burst"
    - "Restore riêng tenant Standard không ảnh hưởng tenant khác"
    - "Bảo đảm RTO/RPO và vùng lưu dữ liệu theo hợp đồng"
  next_step: "PoC cô lập dữ liệu và hiệu năng trước pilot"
~~~

Các kết luận trong ADR cần dựa trên phép thử thay vì giả định rằng tính năng cloud tự động thỏa mục tiêu. Nếu PoC cho thấy pool không đáp ứng noisy neighbor hoặc yêu cầu cô lập, có thể chuyển nhóm tenant gây tranh chấp sang data/compute silo hoặc thay đổi thiết kế queue/cache.

## 20. Checklist hoàn tất thiết kế

- [ ] Đã xác định tenant là gì, mối quan hệ user–tenant và nguồn tenant context đáng tin.
- [ ] Đã lập danh mục toàn bộ đường truy cập dữ liệu, không chỉ API và CSDL.
- [ ] Đã chọn rõ mô hình silo, pool hoặc bridge cho từng lớp và ghi lý do.
- [ ] API, DB, cache, queue, file, search, webhook và analytics có cô lập theo tenant.
- [ ] Có kiểm thử truy cập chéo tenant, job retry và connection pool.
- [ ] Có quota/rate limit, cơ chế giảm noisy neighbor và đo SLO riêng tenant.
- [ ] Có quy trình onboarding, suspension, offboarding, xóa và audit có thể vận hành.
- [ ] Có cách triển khai schema/ứng dụng và canary trên nhiều tenant.
- [ ] Kế hoạch migrate bao gồm backup, backfill, đối soát, cutover, rollback/forward fix.
- [ ] Đã thử backup/restore, mục tiêu RTO/RPO, ứng phó sự cố ở failure domain đã chọn.
- [ ] Có phân vùng dữ liệu theo yêu cầu hợp đồng, bao gồm bản sao phụ.
- [ ] Đã đánh giá IAM, secrets, quyền nhân viên hỗ trợ, logging và chính sách tuân thủ.
- [ ] Đã tính TCO, usage metering, unit economics và chi phí chạy song song.
- [ ] Rủi ro còn lại và hard gates có chủ sở hữu và phê duyệt rõ.
- [ ] Quyết định kiến trúc được ghi lại để có thể kiểm chứng và xem xét lại.

**Bài học chính:** Multi-tenancy là thiết kế **ranh giới tin cậy và vòng đời khách hàng xuyên suốt hệ thống**. Chuyển ứng dụng single-tenant sang SaaS cần phối hợp nghiệp vụ, nhận dạng, mạng, compute, dữ liệu, triển khai, giám sát và chi phí. Một kiến trúc tốt có thể dùng chung tài nguyên ở nơi phù hợp, tách biệt ở nơi cần thiết và chứng minh các đánh đổi bằng kiểm thử theo nguyên tắc Well-Architected.
