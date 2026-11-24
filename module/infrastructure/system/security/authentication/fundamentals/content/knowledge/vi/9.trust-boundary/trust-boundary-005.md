# Tenant và tenant — Ranh giới tin cậy trong hệ thống đa tenant

> **Chương:** Trust boundary  
> **Chủ đề:** Tenant và tenant  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tập trung vào xác thực danh tính, credential, token, phiên và liên kết danh tính. Tenant là một miền tổ chức có dữ liệu, thành viên và chính sách riêng; tenant context là ngữ cảnh mà server phải xác lập và duy trì an toàn trong từng yêu cầu.

## 1. Tenant là gì và vì sao nó là ranh giới tin cậy?

**Tenant** là một tổ chức, khách hàng, workspace hoặc miền sử dụng độc lập trong ứng dụng phục vụ nhiều tổ chức. Mỗi tenant có thể có thành viên, tài nguyên, vai trò, cấu hình, miền đăng nhập và chính sách bảo mật riêng. Một ứng dụng đa tenant (multi-tenant application) dùng chung một phần hạ tầng để phục vụ nhiều tenant, nhưng phải giữ dữ liệu và quyền truy cập của từng tenant tách biệt.

Ví dụ một nền tảng đào tạo phục vụ hai doanh nghiệp Alpha và Beta. Cả hai đều có người dùng tên đăng nhập **lan**, cùng tạo khóa học có mã hiển thị **SEC-101**, và có quản trị viên riêng. Lan thuộc Alpha không được xem điểm, hồ sơ hoặc tài liệu nội bộ của Beta chỉ vì hai tổ chức sử dụng cùng ứng dụng.

Trong bài này, cần phân biệt hai khái niệm liên quan:

- **Tenant entity (đối tượng tenant):** bản ghi đại diện cho tổ chức/workspace, có ID nội bộ ổn định, trạng thái, cấu hình và vòng đời.
- **Tenant context (ngữ cảnh tenant):** tenant mà một request, phiên hoặc tác vụ đang hoạt động trong đó. Đây là thông tin runtime do server xác định và kiểm tra, không phải một chuỗi tùy ý mà client có thể tự đặt.

Hai khái niệm gắn với nhau nhưng không đồng nhất. Một người có thể là thành viên của nhiều tenant; tenant entity vẫn tồn tại độc lập, còn tenant context được chọn cho từng lần truy cập. **Xác định được tenant không có nghĩa người dùng có quyền trong tenant đó.**

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích tenant như một miền dữ liệu, danh tính và chính sách riêng.
2. Phân biệt tenant ID, tenant slug, tenant membership và tenant context.
3. Thiết kế cách xác định tenant từ host, URL hoặc SSO mà không tin dữ liệu client một cách mù quáng.
4. Giữ tenant context nhất quán từ xác thực đến database, cache, queue, storage và API.
5. Phát hiện và ngăn lỗi cross-tenant access, IDOR/BOLA, rò rỉ cache và confused deputy.
6. Xây dựng kiểm thử chứng minh tenant A không thể đọc hoặc thay đổi tài nguyên của tenant B.

## 2. Mô hình dữ liệu: tenant, account, membership và resource

Không nên gộp tenant với user account. Một tài khoản có thể tham gia nhiều tenant, và một tenant có nhiều tài khoản. Quan hệ thường gặp:

~~~text
Tenant
  id = tenant-alpha
  state = ACTIVE
  policy = policy-alpha

Account
  id = account-1742
  credential(s) = passkey, password, ...
  profile = ...

Membership
  account_id = account-1742
  tenant_id = tenant-alpha
  roles = [LEARNER]
  state = ACTIVE

Resource
  id = course-SEC-101
  tenant_id = tenant-alpha
  owner / ACL = ...
~~~

| Thành phần | Ý nghĩa | Câu hỏi bảo mật |
| --- | --- | --- |
| **Tenant** | Tổ chức hoặc workspace | Tenant có đang hoạt động? Chính sách nào áp dụng? |
| **Account** | Tài khoản đăng nhập nội bộ | Ai đang kiểm soát credential của account? |
| **Membership** | Quan hệ account tham gia tenant | Account có còn là thành viên? Vai trò nào trong tenant này? |
| **Tenant role** | Vai trò trong phạm vi một tenant | Vai trò có áp dụng cho hành động và tài nguyên cụ thể không? |
| **Tenant context** | Tenant đang được chọn cho request/job | Server đã xác định và xác minh context từ nguồn đáng tin chưa? |
| **Resource** | Dữ liệu thuộc tenant | Resource có thuộc tenant context và actor có quyền không? |

Ví dụ Lan là một account nội bộ nhưng tham gia Alpha với vai trò LEARNER và Beta với vai trò INSTRUCTOR. Không nên gắn một vai trò toàn cục duy nhất vào account rồi dùng ở mọi nơi. Vai trò cần được đánh giá trong **membership của tenant hiện hành**.

### Identifier không tự tạo quyền

Tenant ID, tenant slug hoặc resource ID là giá trị tham chiếu. Biết một ID không chứng minh người gọi có quyền. UUID khó đoán có thể làm giảm việc dò tuần tự nhưng không thay thế authorization.

Một request như GET /tenants/tenant-beta/grades/123 phải được kiểm tra theo các bước: account đã xác thực, membership hợp lệ trong Beta, quyền đọc điểm và resource thực sự thuộc Beta. Không chỉ dựa vào việc URL có chứa tenant ID hợp lệ.

## 3. Chọn mô hình cô lập dữ liệu

Mô hình lưu trữ ảnh hưởng cách thực thi ranh giới tenant. Không có một cách duy nhất phù hợp mọi quy mô; lựa chọn phải tính đến yêu cầu cô lập, vận hành, chi phí, phục hồi và tuân thủ.

| Mô hình | Cách tổ chức | Ưu điểm | Rủi ro/công việc cần kiểm soát |
| --- | --- | --- | --- |
| **Shared database, shared schema** | Nhiều tenant dùng chung bảng; mỗi hàng có tenant_id | Chi phí thấp, dễ triển khai và cập nhật chung | Mọi truy vấn phải scope tenant; sai một query có thể lộ dữ liệu chéo tenant. |
| **Shared database, schema per tenant** | Mỗi tenant có schema riêng trong một database | Có thể tách namespace và quyền theo schema | Quản lý migration, kết nối động, quyền database và backup phức tạp. |
| **Database per tenant** | Mỗi tenant có database riêng | Cô lập dữ liệu và backup rõ hơn | Chi phí, pooling, migration, giám sát và vận hành nhiều database. |
| **Hybrid** | Tenant theo nhóm hoặc cấp độ rủi ro dùng mô hình khác nhau | Linh hoạt cho khách hàng có yêu cầu đặc biệt | Phải quản lý nhiều đường thực thi và kiểm tra nhất quán. |

Với mô hình shared schema, cột tenant_id phải hiện diện trong mọi bảng dữ liệu tenant-scoped và được dùng trong khóa, truy vấn, index, quan hệ. Cần ràng buộc ở database để giảm nguy cơ một lỗi ứng dụng gắn nhầm resource của tenant khác.

Với schema/database riêng, vẫn cần kiểm tra tenant context ở tầng ứng dụng. Kết nối nhầm database hoặc chọn sai schema do request có thể tạo ra rủi ro tương đương. Cô lập vật lý hoặc logic ở database là một lớp phòng thủ, không thay thế xác thực và phân quyền.

## 4. Xác định tenant context từ đâu?

Tenant context thường được xác định khi request đi vào hệ thống. Nguồn có thể là hostname, subdomain, path, lựa chọn workspace trong UI hoặc claim từ IdP. Mỗi nguồn đều cần được kiểm chứng.

### 4.1. Hostname và custom domain

Ví dụ:

~~~text
alpha.learning.example   -> tenant-alpha
beta.learning.example    -> tenant-beta
learn.alpha-corp.example -> tenant-alpha (custom domain đã xác minh)
~~~

Server có thể ánh xạ hostname đã chuẩn hóa sang tenant ID nội bộ trong cấu hình do hệ thống quản lý. Phải xử lý đúng reverse proxy và header Host: chỉ tin proxy đã cấu hình, không để client tự giả mạo forwarded host để chọn tenant. Custom domain cần quy trình xác minh quyền kiểm soát domain trước khi gắn vào tenant; khi gỡ domain cần vô hiệu ánh xạ và cache liên quan.

Không lấy một chuỗi Host bất kỳ rồi tự tạo tenant. Nếu hostname không nằm trong registry hợp lệ, request phải bị từ chối hoặc chuyển sang luồng chọn tenant an toàn.

### 4.2. Tenant slug trong URL

Ví dụ đường dẫn /t/alpha/courses giúp người dùng hiểu đang làm việc trong workspace nào. Slug là **selector**, không phải credential. Server tra slug từ registry, xác định tenant ID nội bộ rồi kiểm tra membership và quyền.

Nếu người dùng sửa alpha thành beta, server phải kiểm tra họ có quyền trong Beta. Không được mặc định vì họ đã có phiên hợp lệ ở Alpha nên có thể truy cập mọi slug khác.

### 4.3. Tenant được chọn trong UI

Một người có thể chọn workspace từ danh sách. UI gửi lựa chọn lên server, nhưng server phải kiểm tra danh sách membership còn hiệu lực. Không lưu lựa chọn ở local storage rồi tin rằng nó là ngữ cảnh bảo mật. Server có thể lưu tenant hiện hành trong session hoặc phát hành token có tenant scope sau khi kiểm tra.

### 4.4. Tenant claim từ IdP

Một IdP có thể trả claim về tổ chức, group hoặc tenant. RP chỉ sử dụng claim sau khi xác minh token/assertion, issuer, audience, chữ ký, thời hạn và hợp đồng ánh xạ. Cần kiểm tra claim đó biểu diễn điều gì: domain của email, group, tổ chức đã xác minh hay tenant nội bộ. Không tự suy ra membership chỉ vì email kết thúc bằng @alpha.example.

### 4.5. Header do client gửi

Header như X-Tenant-Id có thể được dùng làm selector trong một API, nhưng giá trị này vẫn là input không tin cậy. Server phải đối chiếu với membership và policy. Nếu kiến trúc dùng gateway để ghi header tenant đã xác minh, gateway phải loại bỏ header cùng tên từ client trước khi chèn giá trị tin cậy; service downstream phải chỉ nhận từ kênh nội bộ đã xác thực.

**Quy tắc chung:** client có thể yêu cầu tenant nào được chọn; server quyết định tenant context nào được chấp nhận.

## 5. Authentication, tenant resolution và authorization là ba bước riêng

Một luồng an toàn phải tránh nhập nhằng ba việc:

1. **Authentication:** xác minh account bằng password, passkey, MFA, chứng chỉ hoặc kết quả IdP.
2. **Tenant resolution:** xác định tenant context cho request từ nguồn hợp lệ.
3. **Authorization:** kiểm tra membership, vai trò, quyền và quan hệ với resource trong tenant đó.

~~~mermaid
flowchart TD
    A["Request từ client"] --> B["Xác minh session/token"]
    B --> C{"Principal hợp lệ?"}
    C -- "Không" --> X["401 / từ chối"]
    C -- "Có" --> D["Resolve tenant selector"]
    D --> E{"Tenant hợp lệ và hoạt động?"}
    E -- "Không" --> Y["Từ chối"]
    E -- "Có" --> F["Kiểm tra membership của principal"]
    F --> G{"Membership còn hiệu lực?"}
    G -- "Không" --> Y
    G -- "Có" --> H["Load resource trong tenant context"]
    H --> I["Kiểm tra action + resource permission"]
    I --> J{"Được phép?"}
    J -- "Không" --> Z["403 / từ chối"]
    J -- "Có" --> K["Thực hiện và audit"]
~~~

Một session có thể chứng minh account đã xác thực nhưng không chứng minh account là thành viên của mọi tenant. Membership cũng không tự cấp mọi quyền: thành viên LEARNER có thể xem khóa học được phân công nhưng không sửa cấu hình tenant.

### Ví dụ

Lan đã xác thực bằng passkey và có membership ở Alpha. Lan gửi request chọn Beta. Kết quả xác thực passkey vẫn hợp lệ cho account Lan, nhưng server cần kiểm tra membership Beta. Nếu Lan không có membership, request phải bị từ chối trước khi truy vấn dữ liệu Beta.

Nếu Lan có membership Beta nhưng chỉ là LEARNER, request xóa người dùng Beta vẫn phải bị từ chối ở bước authorization. **Xác thực mạnh không làm tăng vai trò.**

## 6. Tenant context phải được xác lập một lần và truyền nhất quán

Trong mỗi request, server nên tạo một context bất biến hoặc chỉ có thể thay đổi qua một thao tác được kiểm soát:

~~~text
TenantContext {
  tenantId: tenant-alpha
  actorAccountId: account-1742
  membershipId: membership-882
  roles: [LEARNER]
  policyVersion: tenant-policy-v4
  requestId: req-...
}
~~~

Đây là cấu trúc khái niệm. Không để bất kỳ handler nào tự đọc một tenant ID khác từ body rồi ghi đè context đã xác minh. Nếu cần chuyển tenant, thực hiện quy trình resolve và membership check mới, sau đó tạo context mới cho request/session phù hợp.

Một request lifecycle có thể là:

1. Xác minh session/token và lấy principal.
2. Resolve selector sang tenant ID nội bộ.
3. Kiểm tra tenant active và membership của principal.
4. Tạo TenantContext chứa tenant ID, actor, membership và policy version.
5. Truyền context đến service/repository theo kiểu tham số rõ ràng hoặc request-scoped dependency.
6. Kiểm tra resource ownership và quyền ngay trước thao tác.
7. Ghi audit với tenant ID và actor ID đã được xác minh.

Không dùng biến toàn cục hoặc static mutable để lưu tenant hiện tại trong server xử lý nhiều request đồng thời. Request A và B có thể chạy xen kẽ trên cùng thread pool hoặc coroutine; context dùng chung có thể bị ghi đè và gây rò rỉ cross-tenant.

### Ví dụ lỗi context dùng chung

~~~text
Request A: set currentTenant = Alpha
Request B: set currentTenant = Beta
Request A: query courses using currentTenant
           -> vô tình truy vấn Beta
~~~

Cần dùng request-scoped context được quản lý bởi framework, truyền tham số tường minh hoặc cơ chế context-local có vòng đời rõ ràng. Với async job, không dựa vào ThreadLocal được giữ lại sau khi thread quay về pool.

## 7. Database isolation: đặt tenant vào truy vấn và ràng buộc

Trong shared schema, cách đơn giản là mọi bảng tenant-scoped có tenant_id và mọi truy vấn đều lọc theo context đã xác minh.

~~~sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    state TEXT NOT NULL
);

CREATE TABLE memberships (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    account_id UUID NOT NULL,
    state TEXT NOT NULL,
    UNIQUE (tenant_id, account_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE courses (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    id UUID NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE lessons (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    course_id UUID NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, course_id)
      REFERENCES courses (tenant_id, id)
);
~~~

Điểm quan trọng của khóa ngoại kép: lesson thuộc tenant Alpha không thể tham chiếu course của Beta chỉ bằng cách đưa course_id của Beta vào. Database kiểm tra cả tenant_id và course_id. Tương tự, quan hệ giữa user, project, invoice hoặc document cần mang tenant scope ở các khóa liên quan.

Truy vấn cần đưa tenant context vào:

~~~sql
SELECT id, title
FROM courses
WHERE tenant_id = :verified_tenant_id
  AND id = :requested_course_id;
~~~

verified_tenant_id phải đến từ TenantContext do server xác lập, không lấy trực tiếp từ JSON body hoặc query string mà không kiểm tra.

### 7.1. Unique constraint theo tenant

Nếu mỗi tenant được phép có username lan, unique constraint toàn cục trên username sẽ sai nghiệp vụ. Có thể cần:

~~~sql
CREATE UNIQUE INDEX uq_username_per_tenant
ON tenant_login_names (tenant_id, canonical_username)
WHERE active = TRUE;
~~~

Tương tự, mã khóa học hoặc mã hóa đơn có thể duy nhất trong tenant chứ không phải toàn ứng dụng. Xác định namespace trước khi thiết kế unique key.

### 7.2. Row-level security

Một số database hỗ trợ Row-Level Security (RLS). Chính sách có thể giới hạn hàng theo tenant context được đặt trong transaction:

~~~sql
ALTER TABLE courses ENABLE ROW LEVEL SECURITY;

CREATE POLICY courses_tenant_isolation
ON courses
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
~~~

Đây là ví dụ khái niệm cho PostgreSQL; phải kiểm tra quyền owner, role có BYPASSRLS, superuser, cách đặt biến, connection pool và mọi bảng liên quan. RLS không tự an toàn nếu ứng dụng có thể đặt tenant ID tùy ý vào session DB.

Nếu dùng connection pool, tenant setting phải được đặt trong transaction và reset đúng cách trước khi connection quay về pool. Tránh session-level state bị rò từ request trước. Kiểm thử trường hợp connection tái sử dụng giữa tenant A và B.

### 7.3. Ràng buộc ở database là phòng thủ nhiều lớp

Tầng ứng dụng vẫn cần kiểm tra authorization, nhưng database có thể giảm hậu quả của lỗi code bằng composite foreign key, unique constraint, RLS và quyền DB tối thiểu. Cần tránh dùng một database role có quyền bỏ qua mọi policy cho tất cả request của người dùng nếu không thật sự cần.

## 8. Authorization phải kiểm tra tenant và resource

Một lỗi phổ biến là chỉ kiểm tra account có membership tenant rồi tin mọi resource ID được gửi lên. Điều đó vẫn có thể gây **Broken Object Level Authorization (BOLA/IDOR)**.

Ví dụ API:

~~~http
GET /api/tenants/tenant-alpha/invoices/invoice-900
Authorization: Bearer <token>
~~~

Server cần kiểm tra:

- Token hợp lệ, đúng issuer/audience và còn hiệu lực.
- Tenant context được resolve thành tenant-alpha.
- Principal có membership hợp lệ và trạng thái tenant cho phép truy cập.
- Invoice-900 thực sự thuộc tenant-alpha.
- Principal có quyền đọc invoice này theo role/ownership/ACL.

Nếu invoice-900 thuộc tenant-beta, server không được trả dữ liệu chỉ vì ID tồn tại. Có thể trả 404 để tránh tiết lộ sự tồn tại tùy chính sách, nhưng điều quan trọng là không thực hiện thao tác trái quyền.

Không nên tìm invoice chỉ bằng ID rồi trả kết quả trực tiếp. Nên tìm theo cả tenant ID và resource ID, sau đó kiểm tra quyền hành động với actor. Việc repository có filter tenant giúp giảm lỗi; authorization vẫn cần ở service/domain.

## 9. Token, session và tenant scope

Một người có thể thuộc nhiều tenant. Token/session phải biểu diễn rõ **tenant nào đang được sử dụng**, hoặc có một cơ chế xác định membership/tenant cho từng request.

Ví dụ JWT access token minh họa:

~~~json
{
  "iss": "https://auth.example",
  "aud": "learning-api",
  "sub": "account-1742",
  "tenant_id": "tenant-alpha",
  "scope": ["course:read"],
  "iat": 1795320000,
  "exp": 1795320900
}
~~~

Claim tenant_id chỉ đáng tin sau khi API xác minh chữ ký, issuer, audience, thời gian, thuật toán được phép và cách token được cấp. API phải biết token được phát hành theo policy nào và membership còn hiệu lực ra sao. Không cho client sửa payload JWT rồi tin tenant_id; chữ ký phải được kiểm tra đúng cách.

Các lựa chọn kiến trúc:

- **Token tenant-scoped:** sau khi user chọn tenant và server xác minh membership, token được phát hành với tenant ID và scope của tenant đó. Đổi tenant cần flow cấp token/context mới.
- **Session account-scoped với tenant context riêng:** session xác định account, mỗi request chọn tenant rồi server kiểm tra membership. Cần bảo đảm context không bị thay đổi tùy tiện giữa các bước nhạy cảm.
- **Token chứa nhiều membership:** có thể dùng cho ứng dụng nhỏ, nhưng claim dễ cũ khi role hoặc membership bị thu hồi; cần token ngắn hạn, introspection hoặc kiểm tra trạng thái ở server.

Không nhầm account ID với tenant ID; không lấy tenant từ trường do client tự gửi để ghi vào principal. Token hợp lệ không đồng nghĩa actor có quyền trên mọi resource thuộc tenant claim.

### Chuyển tenant

Khi người dùng đổi workspace, server cần resolve tenant mới, xác minh membership và quyền, áp dụng policy của tenant mới rồi mới cập nhật context hoặc cấp token mới. Hành động đang chờ ở tenant Alpha không nên được tiếp tục bằng context Beta. Với giao dịch nhạy cảm, gắn step-up transaction với account, tenant, session, action và resource để ngăn đổi tenant giữa chừng.

## 10. SSO và liên kết danh tính trong môi trường đa tenant

Trong OpenID Connect, danh tính ngoài thường được ánh xạ bằng cặp **(issuer, subject)**. Trong hệ thống multi-tenant, còn phải xác định danh tính đó được phép tham gia tenant nào.

~~~text
(issuer = https://id.alpha.example, subject = 00u-123)
   -> account-1742
   -> membership (tenant-alpha, account-1742)

(issuer = https://id.beta.example, subject = 00u-123)
   -> có thể là một danh tính khác
   -> không tự động là account-1742
~~~

Không dùng email domain làm bằng chứng duy nhất cho membership. Một tenant có thể yêu cầu domain email công ty đã xác minh để hỗ trợ quy trình mời, nhưng cần xác minh domain và quy tắc cấp membership. Nhân viên cũ có thể mất quyền ở công ty dù vẫn giữ email cá nhân; email có thể được tái cấp hoặc chuyển chủ.

Khi IdP trả claim về tenant/organization:

1. Xác minh issuer, audience, chữ ký, expiry, nonce/state theo flow và các điều kiện giao thức.
2. Hiểu claim theo hợp đồng đã cấu hình với IdP: đó là tổ chức, group hay một thuộc tính profile?
3. Ánh xạ sang tenant nội bộ bằng registry tin cậy; không lấy một chuỗi claim bất kỳ làm tenant ID trực tiếp.
4. Kiểm tra membership, trạng thái tenant và policy nội bộ.
5. Tạo principal/session với tenant context đã xác minh.
6. Ghi audit và xử lý thay đổi membership/IdP theo vòng đời.

Nếu một IdP phục vụ nhiều tenant, cần ràng buộc cấu hình kết nối và issuer/audience để ngăn confused deputy. Không để client chọn một issuer tùy ý rồi chấp nhận token của issuer đó như đăng nhập hợp lệ.

## 11. Tenant isolation phải xuyên suốt cache, file, queue và search

Lỗi tenant không chỉ xuất hiện trong SQL. Mọi hệ thống lưu trữ hoặc truyền dữ liệu đều có thể trở thành đường rò.

| Thành phần | Lỗi thường gặp | Cách bảo vệ |
| --- | --- | --- |
| **Application cache** | Key chỉ là course:123, tenant khác nhận dữ liệu cache | Thêm tenant ID vào key, kiểm tra authorization trước khi trả cache. |
| **Distributed cache** | Cache entry hoặc invalidation event không scope tenant | Namespace theo tenant, xác minh nguồn event và quyền xóa. |
| **Object storage** | Người dùng đoán path của file tenant khác | Kiểm tra metadata/owner, tenant scope và cấp URL ký ngắn hạn sau authorization. |
| **Search index** | Truy vấn quên filter tenant hoặc filter chỉ ở UI | Tenant filter bắt buộc ở server/index policy, test cross-tenant. |
| **Message queue** | Consumer xử lý event thiếu tenant context hoặc dùng context mặc định | Message có tenant ID, actor/system identity, schema/version; consumer xác minh và scope lại. |
| **Background job** | Job chạy sau request nhưng mất tenant context | Truyền tenant ID rõ ràng trong payload tin cậy, kiểm tra trạng thái tenant và quyền service. |
| **Analytics/export** | Báo cáo tổng hợp trộn dữ liệu ngoài phạm vi | Kiểm tra quyền export, tenant filter, masking và phê duyệt khi dữ liệu tổng hợp nhạy cảm. |
| **Logs/traces** | Log chứa dữ liệu tenant khác hoặc tenant ID bị giả | Gắn tenant ID đã xác minh, phân quyền truy cập log, hạn chế PII và secrets. |

### 11.1. Cache key phải có tenant

Ví dụ không an toàn:

~~~text
cache key = "course:SEC-101"
~~~

Nếu Alpha và Beta đều có mã SEC-101, cache có thể trả nhầm nội dung. Nên dùng key có tenant scope:

~~~text
cache key = "tenant:tenant-alpha:course:SEC-101"
~~~

Nhưng key có tenant ID vẫn chưa đủ: server phải kiểm tra membership/quyền trước khi sử dụng dữ liệu. Cache là tối ưu hiệu năng, không phải nguồn cấp quyền.

### 11.2. Object storage và signed URL

Một signed URL có thể cho phép tải file mà không cần gửi lại session tới ứng dụng. Do đó URL cần thời hạn ngắn, quyền tối thiểu, ràng buộc đúng object và chỉ được cấp sau khi kiểm tra tenant/resource authorization. Không dùng đường dẫn file có thể đoán làm kiểm soát truy cập.

### 11.3. Queue và background worker

Một event như CourseExportRequested cần chứa tenant ID, resource ID, request ID và danh tính service/actor thích hợp. Consumer phải kiểm tra tenant tồn tại, trạng thái hoạt động, resource thuộc tenant và service có quyền xử lý. Không dựa vào một biến tenant hiện tại còn sót từ job trước.

## 12. Các cuộc tấn công cross-tenant thường gặp

| Kiểu tấn công/lỗi | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| **Tenant IDOR/BOLA** | Đổi tenant/resource ID trong URL hoặc body | Membership và authorization trên từng resource; query có tenant scope. |
| **Tenant spoofing** | Giả header, Host, tenant slug hoặc claim | Chỉ resolve từ registry/cấu hình tin cậy; kiểm tra nguồn và membership. |
| **Confused deputy** | Service có quyền rộng thực hiện yêu cầu thay caller nhưng không giữ tenant context | Truyền actor/tenant/action rõ ràng; service authorization và least privilege. |
| **Cache poisoning/leak** | Cache key thiếu tenant hoặc invalidation sai | Key có tenant namespace; kiểm tra quyền trước cache hit; test xen kẽ tenant. |
| **Connection pool leakage** | DB session setting từ request A còn khi xử lý request B | Transaction-local context, reset, kiểm thử connection reuse. |
| **Async context loss** | Job/consumer thiếu tenant ID hoặc dùng mặc định | Tenant-scoped payload, xác minh lại trong worker. |
| **SSO mapping collision** | Cùng sub ở hai issuer hoặc email giống nhau bị gộp | Mapping theo issuer + subject và membership riêng. |
| **Custom domain takeover** | Domain không còn thuộc tenant nhưng ánh xạ cũ còn hiệu lực | Domain verification, lifecycle, revalidation và revoke mapping. |
| **Privilege escalation** | Vai trò admin ở Alpha bị áp dụng nhầm cho Beta | Role gắn với membership và tenant; kiểm tra policy hiện hành. |
| **Cross-tenant export** | Batch/report query thiếu filter hoặc dùng service account quá rộng | Export scoped, approval, row-level checks và audit. |

### Ví dụ confused deputy

Một dịch vụ export có quyền đọc mọi tenant để tạo báo cáo. User Alpha yêu cầu export course Alpha nhưng gửi thêm resource ID của Beta. Nếu export service chỉ kiểm tra caller đã đăng nhập rồi dùng quyền DB rộng, nó trở thành confused deputy và làm lộ dữ liệu Beta.

Giải pháp: service phải nhận actor và tenant context đã xác minh, kiểm tra membership/quyền của actor, kiểm tra resource thuộc tenant và dùng service credential có scope/ủy quyền phù hợp. Quyền rộng của service không được chuyển thành quyền rộng của caller.

## 13. Tenant lifecycle: tạo, mời, chuyển và đóng tenant

Ranh giới tin cậy thay đổi theo vòng đời. Tạo tenant, xác minh domain, mời thành viên, thay IdP hoặc đóng tenant đều là sự kiện bảo mật.

### Provisioning

Khi tạo tenant, server sinh ID nội bộ, tạo cấu hình và trạng thái ban đầu, áp dụng policy mặc định và tạo owner theo quy trình xác minh phù hợp. Không cho client tự chọn ID tenant có thể trùng hoặc chiếm tenant khác. Với custom domain, phải chứng minh quyền kiểm soát domain trước khi kích hoạt.

### Invitation và membership

Lời mời cần gắn với tenant, người mời, vai trò dự kiến, người nhận hoặc điều kiện chấp nhận, thời hạn và trạng thái sử dụng. Token mời nên khó đoán, có mục đích, ngắn hạn và chỉ dùng một lần. Khi chấp nhận, server phải xác minh account và tạo membership đúng tenant theo policy. Không coi việc biết slug tenant là lời mời.

### Thay đổi vai trò

Role assignment là thay đổi quyền. Cần kiểm tra người thực hiện có quyền quản lý membership, tenant context hợp lệ và vai trò mới nằm trong phạm vi được cấp. Với quyền quản trị cao, có thể cần step-up, phê duyệt thứ hai và audit.

### Chuyển người dùng giữa tenant

Không nên đổi tenant ID của một account rồi kéo toàn bộ dữ liệu/role sang tenant mới. Chuyển tenant có thể là tạo membership mới, chuyển tài nguyên theo quy trình nghiệp vụ và thu hồi membership cũ. Cần giữ provenance, quyền sở hữu và lịch sử audit.

### Suspend và deprovision

Khi tenant bị khóa hoặc hợp đồng kết thúc, cần xác định hành vi của session/token, API, custom domain, IdP, queue job, export, cache và backup. Một tenant đã bị suspend không được tiếp tục truy cập chỉ vì JWT còn hạn nếu policy yêu cầu thu hồi ngay. Có thể cần token ngắn hạn, introspection hoặc denylist/version check cho thao tác nhạy cảm.

## 14. Thiết kế API và service không làm rơi tenant context

Tenant context nên được truyền tường minh qua các lớp. Ví dụ giả mã:

~~~java
Response getCourse(Request request, Session session) {
    Principal actor = sessionVerifier.requirePrincipal(session);

    TenantId tenantId = tenantResolver.resolve(request.tenantSelector());
    Membership membership = membershipService.requireActive(
        tenantId, actor.accountId());

    TenantContext context = new TenantContext(
        tenantId, actor.accountId(), membership.id(), membership.roles());

    Course course = courseRepository.findByTenantAndId(
        context.tenantId(), request.courseId())
        .orElseThrow(NotFoundException::new);

    authorizationService.requireAllowed(
        actor, membership, "course:read", course);

    return courseMapper.toResponse(course);
}
~~~

Đây là giả mã để minh họa thứ tự trách nhiệm. Trong production, cần bảo đảm TenantContext không thể bị tạo tùy tiện ở controller, repository luôn nhận tenant scope, quyền được kiểm tra theo policy hiện hành và dữ liệu được kiểm tra lại trước commit khi có concurrency.

Một số nguyên tắc:

- Repository tenant-scoped nên yêu cầu TenantContext/TenantId tường minh; tránh method chung như findById cho dữ liệu nhạy cảm nếu caller dễ quên filter.
- Service-to-service cần mang tenant scope và danh tính service; xác thực service không tự cấp quyền truy cập tất cả tenant.
- Không dùng tenant ID từ body để ghi dữ liệu mà chưa đối chiếu với context.
- Với batch, mỗi item cần được kiểm tra cùng tenant hoặc chia batch theo tenant; không gom danh sách ID rồi truy vấn toàn cục.
- Khi có thao tác cross-tenant hợp lệ (ví dụ nền tảng vận hành), phải có quyền hệ thống riêng, mục đích rõ ràng, audit và phê duyệt theo policy.

## 15. Kiểm thử tenant isolation

Một kiểm thử chỉ xác minh user Alpha truy cập được dữ liệu Alpha là chưa đủ. Cần kiểm tra **negative cases** chứng minh user Alpha không thể truy cập Beta bằng cách sửa bất kỳ selector hoặc identifier nào.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| User Alpha truy cập resource Alpha với membership và role phù hợp | Cho phép. |
| User Alpha sửa URL tenant thành Beta nhưng không có membership | Từ chối trước khi trả dữ liệu. |
| User Alpha có membership Beta nhưng không có quyền trên resource | Từ chối theo authorization. |
| Cùng resource ID tồn tại ở Alpha và Beta | Trả đúng resource trong tenant context, không nhầm cache. |
| Gửi X-Tenant-Id giả mạo | Server resolve/check lại; không nâng quyền. |
| Giả Host hoặc forwarded host không từ proxy tin cậy | Từ chối hoặc resolve theo host đã xác minh. |
| Token có tenant claim sai chữ ký/audience/issuer | Từ chối token. |
| Token hợp lệ của Alpha dùng ở endpoint Beta | Membership và tenant scope được kiểm tra; từ chối nếu không hợp lệ. |
| Role ADMIN ở Alpha, LEARNER ở Beta | ADMIN không được áp dụng sang Beta. |
| Query thiếu tenant filter | RLS/DB constraint hoặc test phát hiện; không trả hàng của tenant khác. |
| Connection DB được tái sử dụng A rồi B | Không còn session setting của A trong request B. |
| Cache cùng resource key ở hai tenant | Cache key tách namespace, dữ liệu không trộn. |
| Object storage URL của file Beta được gửi cho Alpha | Không cấp URL mới; URL cũ phải theo expiry/revoke policy. |
| Queue message thiếu tenant ID hoặc tenant đã suspend | Consumer từ chối/quarantine theo policy. |
| User bị gỡ membership nhưng access token còn hạn | Quyền bị thu hồi theo SLA/policy, không dựa mù quáng vào token cũ. |
| Invite token đã dùng hoặc hết hạn | Không thể tạo membership lần nữa. |
| Custom domain bị gỡ hoặc hết xác minh | Không còn resolve vào tenant cũ. |
| Background job chạy đồng thời cho Alpha và Beta | Mỗi job giữ context riêng, không lẫn dữ liệu. |
| Tenant bị suspend giữa thao tác nhạy cảm | Điểm commit kiểm tra lại trạng thái và từ chối theo policy. |

### Test invariant

Có thể định nghĩa một bất biến kiểm thử:

~~~text
Với mọi request R có TenantContext T:
  mọi resource được đọc/ghi phải thuộc T
  hoặc phải được truy cập qua một policy cross-tenant đặc biệt đã phê duyệt.

Không có membership hợp lệ của actor trong T:
  request không được truy cập tài nguyên tenant-scoped của T.

Mọi cache, queue, storage, report và log:
  phải giữ tenant scope tương đương với đường xử lý gốc.
~~~

Nên có integration test chạy song song hai tenant để phát hiện context leak; test repository/SQL/RLS; test API thay tenant ID; test cache hit/miss; test queue consumer; và test thu hồi membership/token. Security test cần xác minh cả phản hồi lẫn **không có side effect**: một request bị từ chối không được tạo export, thay đổi dữ liệu hoặc phát sự kiện cho tenant khác.

## 16. Audit, giám sát và xử lý sự cố cross-tenant

Audit log nên lưu tenant ID đã xác minh, actor account ID, membership/role tại thời điểm hành động, action, resource ID, kết quả, request/correlation ID, policy version và nguồn xác thực cần thiết. Tránh lưu password, OTP, secret, private key, bearer token hoặc nội dung dữ liệu cá nhân không cần thiết.

Khi phát hiện cross-tenant leak:

1. Xác định tenant bị ảnh hưởng, loại dữ liệu, resource và khoảng thời gian.
2. Thu hồi session/token hoặc credential liên quan nếu có dấu hiệu chiếm tài khoản; khóa endpoint/job có thể tiếp tục rò.
3. Chặn đường truy cập gây lỗi: query, cache, search, object URL, queue, export hoặc custom domain.
4. Bảo toàn log và bằng chứng; xác định request/actor/service nào đã truy cập.
5. Đánh giá cả read và write: dữ liệu đã xem, thay đổi, export hoặc gửi ra ngoài.
6. Thực hiện thông báo và quy trình ứng phó theo nghĩa vụ tổ chức/pháp lý.
7. Bổ sung test hồi quy cho nguyên nhân gốc và kiểm tra những đường tương tự ở tenant khác.

Không nên chỉ sửa một query cụ thể rồi kết luận sự cố đã đóng. Nếu nguyên nhân là TenantContext không được truyền, cần rà soát các service, cache, job và repository cùng dùng cơ chế đó.

## 17. Checklist review thiết kế

- [ ] Tenant entity có ID ổn định, trạng thái và vòng đời được quản lý.
- [ ] Account, membership, role và tenant context được mô hình hóa riêng.
- [ ] Nguồn tenant selector được xác minh; Host/proxy/header/IdP claim không được tin mù quáng.
- [ ] Mỗi request kiểm tra tenant active và membership của principal.
- [ ] TenantContext được tạo phía server, bất biến trong request và truyền tường minh qua async/job.
- [ ] Database có tenant scope, composite key/foreign key và RLS nếu phù hợp.
- [ ] Cache, search, object storage, queue, export và log đều mang tenant namespace/context.
- [ ] Token/session có issuer, audience, expiry, tenant scope và chiến lược thu hồi phù hợp.
- [ ] SSO mapping theo issuer + subject; membership được kiểm tra riêng.
- [ ] Authorization kiểm tra actor, action, tenant và resource ở mỗi API.
- [ ] Có kiểm thử negative cross-tenant, race condition, cache, pool reuse và background job.
- [ ] Quy trình provisioning, invitation, role change, suspend và deprovision có audit.
- [ ] Có quy trình phát hiện, cô lập và xử lý sự cố cross-tenant.

## 18. Bài tập tình huống

Một nền tảng SaaS có hai tenant: **Northwind** và **Contoso**. Cả hai có người dùng tên **alex**, khóa học mã **SEC-101** và hóa đơn mã **INV-009**. Alex có membership LEARNER ở Northwind và ADMIN ở Contoso. Một API nhận tenant từ header X-Tenant-Id, lưu cache theo resource ID, và worker xuất hóa đơn dùng service account có quyền đọc tất cả tenant.

**Yêu cầu:**

1. Chỉ ra vì sao tên người dùng, mã khóa học và mã hóa đơn không đủ để xác định tài nguyên toàn cục.
2. Thiết kế cách resolve tenant context và kiểm tra membership cho từng request.
3. Sửa mô hình cache để không trả nhầm dữ liệu giữa hai tenant.
4. Mô tả quyền của worker export và cách ngăn caller Northwind yêu cầu export hóa đơn Contoso.
5. Đề xuất schema database và các ràng buộc cần thiết.
6. Viết các negative test chứng minh role ADMIN ở Contoso không được áp dụng cho Northwind.

**Hướng phân tích:**

- Account Alex là một danh tính nội bộ; role thuộc membership, nên ADMIN ở Contoso không có nghĩa ADMIN ở Northwind.
- Header chỉ là selector. Server resolve nó, kiểm tra tenant active và membership, rồi tạo TenantContext.
- Cache key phải chứa tenant ID và resource ID; authorization vẫn phải diễn ra trước khi trả cache.
- Worker phải kiểm tra actor, tenant, action và resource trước khi dùng quyền service; quyền rộng của worker không được chuyển cho caller.
- Database dùng tenant_id trong khóa và quan hệ, composite foreign key để resource không tham chiếu nhầm tenant.
- Test sửa header, resource ID, cache key, role, queue payload và token claim để chứng minh mọi đường đều giữ tenant boundary.

### Câu hỏi tự đánh giá

1. Tenant entity khác tenant context ở điểm nào?
2. Vì sao tenant ID không phải bằng chứng xác thực hay quyền truy cập?
3. Tại sao user có membership ở nhiều tenant không nên có một role toàn cục duy nhất?
4. Nếu client gửi X-Tenant-Id, server phải kiểm tra những gì?
5. Vì sao composite foreign key có thể ngăn quan hệ resource chéo tenant?
6. RLS có thể bị vô hiệu hóa hoặc cấu hình sai trong những trường hợp nào?
7. Vì sao cache key thiếu tenant ID gây rò dữ liệu?
8. Khi chuyển tenant, tại sao step-up transaction đang chờ phải bị ràng buộc với tenant ban đầu?
9. SSO claim về email domain có đủ để tự cấp membership không?
10. Một service account có quyền đọc mọi tenant có thể trở thành confused deputy như thế nào?
11. Khi membership bị thu hồi nhưng JWT còn hạn, hệ thống xử lý theo chính sách nào?
12. Vì sao cần integration test chạy đồng thời hai tenant?

**Gợi ý đáp án:** (1) entity là đối tượng tổ chức bền vững, context là tenant đang áp dụng cho request/job; (2) ID chỉ là tham chiếu; (3) quyền khác nhau theo tenant; (4) resolve tenant, kiểm tra trạng thái, membership, role và resource; (5) khóa ngoại kiểm tra cả tenant ID và resource ID; (6) role có BYPASSRLS, owner/superuser hoặc context DB không được đặt/reset đúng; (7) hai tenant có thể trùng resource ID; (8) ngăn dùng challenge của tenant A cho hành động ở B; (9) không, cần xác minh và policy membership; (10) service thực hiện yêu cầu vượt quyền caller; (11) token ngắn hạn/introspection/version/thu hồi tùy SLA; (12) phát hiện request context hoặc connection pool bị lẫn.

## 19. Ghi nhớ

**Tenant là miền tổ chức và dữ liệu cần được cô lập; tenant context là ngữ cảnh runtime mà server xác lập cho từng request hoặc job.** Một thiết kế an toàn phải xác thực principal, resolve tenant, kiểm tra membership, phân quyền resource và giữ cùng tenant scope xuyên database, token, session, cache, storage, queue, search và audit. Bất kỳ lớp nào làm rơi tenant context đều có thể trở thành đường truy cập chéo tenant.

Khi review một request, hãy hỏi: **Ai đang gọi? Họ đang chọn tenant nào? Server dựa vào nguồn nào để tin lựa chọn đó? Actor có membership và quyền gì trong tenant ấy? Resource có thực sự thuộc tenant context? Context có còn nguyên khi đi qua database, cache và background job không?**
