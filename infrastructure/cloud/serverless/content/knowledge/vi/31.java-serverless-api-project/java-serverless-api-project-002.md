# Thiết kế mô hình dữ liệu và quyền truy cập theo người dùng

Một Java serverless API thường phục vụ nhiều người dùng cùng lúc, có thể thuộc các tổ chức (tenant) khác nhau và có vai trò khác nhau trên từng tài nguyên. Người tạo một project có thể chỉnh sửa project đó; thành viên khác chỉ được xem; quản trị viên tenant có thể quản lý thành viên; người dùng ở tenant khác tuyệt đối không được đọc dữ liệu dù họ đoán được ID của project.

Những yêu cầu này phải được thể hiện đồng thời trong mô hình dữ liệu, API contract và lớp authorization. Chỉ ẩn nút trên giao diện hoặc kiểm tra role ở API Gateway là chưa đủ. Mỗi thao tác đọc/ghi phải xác minh danh tính đã được xác thực, phạm vi tenant, membership và quyền trên đúng object. Database cần thêm ràng buộc để ngăn dữ liệu liên tenant bị liên kết nhầm; Java service cần thực thi policy trước side effect; test phải chứng minh user không thể truy cập object của người khác.

Bài học này dùng một API quản lý workspace, project và task làm ví dụ. Bạn sẽ thiết kế schema cho user, tenant, membership và resource ownership; phân biệt authentication với authorization; triển khai tenant-scoped repository và object-level access check bằng Java/Spring; xem xét Row-Level Security (RLS), index, transaction và các rủi ro riêng của function serverless.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt user identity, tenant membership, resource ownership và workload identity.
- Thiết kế mô hình dữ liệu hỗ trợ một user thuộc nhiều tenant.
- Chọn giữa shared schema, schema-per-tenant và database-per-tenant.
- Dùng foreign key, unique constraint và composite key để bảo vệ tenant boundary.
- Xác định RBAC, ABAC và quan hệ ownership cho từng API operation.
- Xác thực JWT/OIDC và ánh xạ issuer + subject thành user nội bộ.
- Thực hiện object-level authorization và tenant-scoped query trong Java.
- Ngăn IDOR, mass assignment và truy cập chéo tenant.
- Dùng transaction, optimistic locking và database RLS như lớp bảo vệ bổ sung.
- Truyền actor/tenant context an toàn qua event và background function.
- Kiểm thử quyền truy cập dương tính, âm tính, thu hồi membership và race condition.

## 1. Bài toán: một user, nhiều tenant, nhiều quyền trên object

Giả sử API cung cấp các chức năng:

- Người dùng đăng nhập bằng identity provider.
- Một người dùng có thể tham gia nhiều workspace/tenant.
- Mỗi tenant có nhiều project.
- Project có các thành viên với vai trò OWNER, EDITOR hoặc VIEWER.
- Project chứa task; task có người tạo và người được giao.
- Một số thao tác chỉ dành cho tenant admin hoặc project owner.

Ví dụ:

| Người dùng | Tenant | Vai trò | Project | Quyền |
|---|---|---|---|---|
| An | Acme | TENANT_ADMIN | Mobile App | Quản lý tenant và project |
| Bình | Acme | MEMBER | Mobile App | EDITOR | Đọc/sửa project và task |
| Chi | Acme | MEMBER | Mobile App | VIEWER | Chỉ đọc |
| Dũng | Beta | TENANT_ADMIN | Billing | Quản lý dữ liệu Beta |

Bình có thể là editor trong Mobile App nhưng chỉ là viewer trong một project khác. Vì vậy, role toàn cục gắn với user thường không đủ để biểu diễn quyền thực tế.

Một request:

~~~http
GET /tenants/{tenantId}/projects/{projectId}
Authorization: Bearer <access-token>
~~~

cần trả lời nhiều câu hỏi:

1. Token có hợp lệ và được cấp cho API này không?
2. Token đại diện cho user nội bộ nào?
3. User có membership đang hoạt động trong tenant được chọn không?
4. User có quyền xem project cụ thể không?
5. Project có thực sự thuộc tenant trong path không?
6. Response có chứa field mà user không được xem không?

Không câu hỏi nào trong số này có thể được thay thế bằng việc kiểm tra user đã đăng nhập.

## 2. Authentication và authorization là hai bước khác nhau

**Authentication (xác thực)** trả lời “request đến từ principal nào?”. **Authorization (phân quyền)** trả lời “principal đó được phép thực hiện hành động nào trên tài nguyên nào?”.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Identity provider | Xác thực user và phát token | OIDC provider |
| API Gateway/ingress | Kiểm tra token hoặc chuyển token tới API | JWT authorizer |
| Java API | Xác minh context, áp dụng policy nghiệp vụ | Có thể xem/sửa project không? |
| Database | Bảo vệ tính toàn vẹn và tenant boundary | Composite foreign key, RLS |
| Workload identity | Cho function quyền gọi dịch vụ khác | Service account, execution role |

Một request có token hợp lệ vẫn có thể không được phép đọc project. Một user là tenant member cũng chưa chắc được phép sửa task trong project mà họ chỉ có quyền VIEWER.

### Token nên chứa thông tin gì?

OIDC access token thường có các claim như:

- iss: issuer đã phát token.
- sub: subject ổn định trong phạm vi issuer.
- aud: audience, API hoặc resource server được phép nhận token.
- exp: thời điểm token hết hạn.
- nbf: thời điểm token bắt đầu có hiệu lực, nếu được dùng.
- scope hoặc role claim: quyền coarse-grained được cấp theo hợp đồng identity provider.

Không dùng email làm khóa định danh chính. Email có thể thay đổi, có thể được tái sử dụng và có thể chưa được xác minh. Ánh xạ user nội bộ bằng cặp (issuer, subject); cùng một chuỗi sub từ hai issuer khác nhau không nhất thiết là cùng người.

Token không nên chứa toàn bộ project membership nếu membership thay đổi thường xuyên. Claim role cũ có thể tồn tại đến khi token hết hạn. Với quyền cần thu hồi nhanh, truy vấn membership/policy hiện hành từ nguồn dữ liệu đáng tin cậy hoặc dùng token lifetime/revocation strategy phù hợp.

## 3. Chọn chiến lược data isolation cho multi-tenancy

Có ba mô hình phổ biến:

| Mô hình | Cách tổ chức | Ưu điểm | Trade-off |
|---|---|---|---|
| Shared database, shared schema | Mọi tenant dùng chung bảng; mỗi row có tenant_id | Chi phí thấp, dễ vận hành, query tổng hợp thuận tiện | Mọi query phải scope tenant; tác động lỗi có thể lan rộng |
| Shared database, schema-per-tenant | Mỗi tenant có schema riêng | Tách namespace và quyền ở mức schema | Migration nhiều schema phức tạp; connection/search path cần kiểm soát |
| Database-per-tenant | Mỗi tenant có database riêng | Cô lập mạnh, backup/restore và key policy riêng | Tốn chi phí, nhiều connection/secret và vận hành phức tạp |

Với project API có số tenant lớn và kích thước vừa phải, shared schema với tenant_id thường là điểm khởi đầu thực tế. Tenant lớn hoặc có yêu cầu compliance/cô lập cao có thể được chuyển sang database riêng theo mô hình hybrid.

Không có mô hình nào tự bảo vệ dữ liệu nếu ứng dụng xác định sai tenant. Database-per-tenant vẫn cần xác thực tenant routing và credential đúng; shared schema cần query scoping và constraint chặt chẽ.

### Những nguyên tắc chung

- Mọi bảng dữ liệu tenant-owned phải có tenant key hoặc quan hệ truy ngược rõ ràng đến tenant.
- Mọi unique constraint phải xét phạm vi tenant nếu giá trị chỉ duy nhất trong tenant.
- Mọi query đọc/ghi phải giới hạn tenant.
- Không suy ra tenant từ email domain hoặc một field do client gửi mà chưa kiểm tra membership.
- Không dùng tenant ID làm bằng chứng authorization; đó chỉ là selector của phạm vi cần truy cập.
- Có migration và test riêng khi chuyển tenant từ shared sang isolated database.

## 4. Thiết kế schema quan hệ

Ví dụ dùng PostgreSQL và UUID. Mô hình gồm:

- app_user: user nội bộ được ánh xạ từ identity provider.
- tenant: workspace/organization.
- tenant_membership: user tham gia tenant và có tenant role.
- project: tài nguyên thuộc tenant.
- project_member: quyền của user trên project.
- task: dữ liệu con thuộc project và tenant.

### Bảng user và tenant membership

~~~sql
CREATE TABLE app_user (
    id              UUID PRIMARY KEY,
    issuer          TEXT NOT NULL,
    subject         TEXT NOT NULL,
    email           TEXT,
    display_name    TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'))
);

CREATE TABLE tenant (
    id              UUID PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'))
);

CREATE TABLE tenant_membership (
    tenant_id       UUID NOT NULL REFERENCES tenant(id),
    user_id         UUID NOT NULL REFERENCES app_user(id),
    role            VARCHAR(30) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id),
    CHECK (role IN ('TENANT_ADMIN', 'MEMBER', 'BILLING_ADMIN')),
    CHECK (status IN ('INVITED', 'ACTIVE', 'SUSPENDED', 'REMOVED'))
);

CREATE INDEX idx_membership_user_active
    ON tenant_membership (user_id, tenant_id)
    WHERE status = 'ACTIVE';
~~~

Email không phải unique identity trong ví dụ vì người dùng có thể đổi email hoặc có nhiều identity provider. Nếu nghiệp vụ cần email unique trong tenant, tạo constraint phù hợp và xác định normalization/case-folding; không mặc định email toàn cục luôn duy nhất.

### Project và project membership

~~~sql
CREATE TABLE project (
    tenant_id       UUID NOT NULL,
    id              UUID NOT NULL,
    name            VARCHAR(200) NOT NULL,
    created_by      UUID NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version         BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED'))
);

CREATE TABLE project_member (
    tenant_id       UUID NOT NULL,
    project_id      UUID NOT NULL,
    user_id         UUID NOT NULL,
    role            VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, user_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES project (tenant_id, id),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (role IN ('OWNER', 'EDITOR', 'VIEWER')),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REMOVED'))
);

CREATE INDEX idx_project_member_user
    ON project_member (tenant_id, user_id, project_id);
~~~

Composite foreign key bảo đảm project member phải là tenant member của đúng tenant. Nếu chỉ lưu project_id và user_id mà không gắn tenant vào constraint, một lỗi ứng dụng có thể tạo quan hệ chéo tenant.

Khi tạo project, transaction nên:
1. Xác minh user có membership ACTIVE trong tenant.
2. Insert project.
3. Insert project_member cho creator với role OWNER.
4. Commit cả hai thay đổi cùng transaction.

### Task và ownership

~~~sql
CREATE TABLE task (
    tenant_id       UUID NOT NULL,
    id              UUID NOT NULL,
    project_id      UUID NOT NULL,
    title           VARCHAR(300) NOT NULL,
    description     TEXT,
    owner_user_id   UUID,
    created_by      UUID NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    version         BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES project (tenant_id, id),
    FOREIGN KEY (tenant_id, owner_user_id)
        REFERENCES tenant_membership (tenant_id, user_id),
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (status IN ('OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED'))
);

CREATE INDEX idx_task_project_created
    ON task (tenant_id, project_id, created_at DESC, id);

CREATE INDEX idx_task_owner_status
    ON task (tenant_id, owner_user_id, status)
    WHERE owner_user_id IS NOT NULL;
~~~

Foreign key bảo đảm task và project cùng tenant; owner và creator cũng phải có membership trong tenant. Nó chưa bảo đảm membership vẫn ACTIVE khi task được tạo hoặc user còn quyền EDITOR; điều đó thuộc authorization/transaction logic và có thể được củng cố bằng policy hoặc trigger nếu cần.

### Vì sao composite key hữu ích?

Nếu chỉ dùng project_id làm foreign key, database có thể không phát hiện việc task có tenant_id = A nhưng tham chiếu project của tenant B. Composite foreign key buộc cặp (tenant_id, project_id) phải tồn tại cùng nhau.

Cách này giúp database trở thành lớp bảo vệ tính toàn vẹn cuối cùng, ngay cả khi một code path quên kiểm tra tenant.

## 5. Chuẩn hóa quyền: RBAC, ABAC và ownership

**RBAC (Role-Based Access Control)** cấp quyền theo vai trò. **ABAC (Attribute-Based Access Control)** xét thuộc tính của principal, resource và context. Ownership là một quan hệ cụ thể giữa user và resource.

Ví dụ policy:

| Hành động | Tenant Admin | Project Owner | Editor | Viewer |
|---|---:|---:|---:|---:|
| Xem project | Có | Có | Có | Có |
| Sửa project metadata | Có | Có | Theo policy | Không |
| Quản lý project member | Có | Có | Không | Không |
| Tạo task | Có | Có | Có | Không |
| Sửa task bất kỳ | Có | Có | Có | Không |
| Sửa task được giao cho mình | Có | Có | Có | Theo policy |
| Xóa project | Có | Có | Không | Không |

Bảng chỉ là ví dụ. Hãy xác định role theo nghiệp vụ thật, tránh tạo role quá nhiều hoặc dùng một role ADMIN cho mọi quyền.

### RBAC không đủ cho mọi quyết định

Một policy có thể cần xét:
- User thuộc tenant nào?
- Membership còn ACTIVE không?
- Project có thuộc tenant đó không?
- User có project membership không?
- User là owner của task không?
- Project/task đã ARCHIVED chưa?
- Hành động có được phép trong trạng thái hiện tại không?

Ví dụ user có role EDITOR nhưng không còn membership active thì vẫn phải bị từ chối. Một task có thể chỉ cho owner cập nhật field cá nhân như estimate; còn chuyển trạng thái DONE cần editor. Đây là policy theo resource/action, không chỉ theo role.

### Default deny

Nếu không có rule cho phép rõ ràng, từ chối. Không suy luận rằng user đã đăng nhập thì mặc định có quyền đọc. Khi thêm action mới, phải bổ sung policy và test tương ứng; không để action mới tự động kế thừa quyền rộng.

## 6. Phân biệt tenant role, project role và object ownership

Có thể chia quyết định quyền thành ba tầng:

1. **Tenant membership:** user có được tham gia tenant không?
2. **Project membership:** user có được truy cập project không và vai trò gì?
3. **Object-level policy:** user có được thực hiện hành động trên task/project cụ thể không?

Tenant admin có thể được cấp quyền override project membership theo policy. Nhưng không nên mặc định mọi MEMBER trong tenant đều đọc mọi project nếu có project private.

Một policy service có thể nhận:
- Actor: user ID đã ánh xạ nội bộ.
- Tenant ID được yêu cầu.
- Resource: project/task và trạng thái.
- Action: READ, UPDATE, DELETE, ASSIGN.
- Context: membership, role, owner, trạng thái workflow.

Trả kết quả allow/deny cùng reason code nội bộ để audit. Không gửi toàn bộ policy detail cho client nếu điều đó tiết lộ sự tồn tại của resource khác tenant.

## 7. Xác thực JWT/OIDC trong Java API

Java API nên hoạt động như OAuth2 Resource Server. Framework xác minh chữ ký theo issuer/JWK, thời hạn và các claim cần thiết. Cấu hình cần xác minh audience đúng với API; không phải mọi JWT hợp lệ đều được phát cho service hiện tại.

Ví dụ cấu hình Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Cấu hình issuer trong application config và thêm audience validator theo API contract. Spring Resource Server với issuer decoder kiểm tra issuer và thời hạn token; cần xác minh audience bằng validator riêng nếu chưa được cấu hình. Không tự viết JWT parser hoặc chỉ base64-decode payload rồi tin claim.

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

issuer-uri phải là issuer thật của identity provider. URL minh họa không phải endpoint dùng trong production.

### Ánh xạ external subject sang user nội bộ

Dùng cặp iss + sub để tìm user:

~~~java
import java.util.UUID;

public record ExternalIdentity(String issuer, String subject) {
}

public record Actor(UUID userId) {
}
~~~

Service ánh xạ:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class ActorResolver {
    private final UserRepository users;

    public ActorResolver(UserRepository users) {
        this.users = users;
    }

    public Actor resolve(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        AppUser user = users.findByIssuerAndSubject(issuer, subject)
                .orElseThrow(() -> new UnknownUserException());

        if (!user.isActive()) {
            throw new AccountDisabledException();
        }
        return new Actor(user.id());
    }
}
~~~

Không tạo user chỉ vì request gửi một userId trong JSON. Nếu hỗ trợ auto-provisioning từ identity provider, hãy thực hiện qua flow đã xác minh issuer, invitation và chính sách tạo account.

## 8. Tenant ID do client chọn không đồng nghĩa client có quyền

API thường nhận tenant ID trong path:

~~~http
GET /tenants/tenant-123/projects/project-456
~~~

Path parameter chỉ nói client muốn truy cập tenant nào. Server phải kiểm tra actor là member đang hoạt động của tenant đó. Không lấy tenant từ:
- JSON body do client tự khai.
- Header tùy ý như X-Tenant-Id mà không kiểm tra.
- Email domain.
- Query parameter chưa được authorize.

Nếu gateway inject tenant/user headers, API chỉ được tin khi gateway xác thực token, loại bỏ header do client tự gửi và kết nối gateway-to-service được bảo vệ. Trong nhiều hệ thống, giữ access token và xác minh trong API sẽ dễ kiểm soát hơn.

### Không tin role hoặc owner ID từ request body

Payload tạo task có thể gồm:

~~~json
{
  "title": "Review deployment",
  "ownerUserId": "user-123",
  "status": "DONE",
  "tenantId": "tenant-999"
}
~~~

Nếu API bind thẳng payload vào entity database, client có thể tự gán task cho user khác, đổi tenant hoặc đánh dấu task DONE. Đây là mass assignment.

Dùng request DTO chỉ chứa field client được phép gửi:

~~~java
public record CreateTaskRequest(
        String title,
        String description,
        java.util.UUID assigneeUserId) {
}
~~~

Server tự gán tenant, creator, trạng thái ban đầu và kiểm tra assignee có quyền trong project. Không bind trực tiếp request JSON vào JPA entity.

## 9. Object-level authorization và IDOR

IDOR (Insecure Direct Object Reference) xảy ra khi API nhận object ID và trả dữ liệu mà không kiểm tra caller có quyền trên object đó.

Ví dụ nguy hiểm:

~~~java
@GetMapping("/projects/{projectId}")
public Project getProject(@PathVariable UUID projectId) {
    return projectRepository.findById(projectId).orElseThrow();
}
~~~

UUID khó đoán hơn số tăng dần nhưng không phải authorization. Attacker có thể lấy ID từ log, link, event, browser history hoặc một user khác chia sẻ.

Cách an toàn là truy vấn theo tenant và actor policy:

~~~sql
SELECT p.tenant_id, p.id, p.name, p.status, p.version
FROM project p
JOIN tenant_membership tm
  ON tm.tenant_id = p.tenant_id
 AND tm.user_id = :actor_user_id
 AND tm.status = 'ACTIVE'
LEFT JOIN project_member pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.id
 AND pm.user_id = :actor_user_id
 AND pm.status = 'ACTIVE'
WHERE p.tenant_id = :tenant_id
  AND p.id = :project_id
  AND p.status <> 'DELETED'
  AND (
      tm.role = 'TENANT_ADMIN'
      OR pm.role IN ('OWNER', 'EDITOR', 'VIEWER')
  );
~~~

Query này chỉ trả project khi actor là tenant admin hoặc project member hợp lệ. Nếu policy cho phép tenant member đọc project PUBLIC, bổ sung điều kiện đó một cách rõ ràng.

Dùng cùng nguyên tắc cho:
- GET by ID.
- PATCH/PUT/DELETE.
- Download attachment.
- Export/report.
- Search và list.
- Bulk operation.
- Nested resource như task trong project.

Không chỉ bảo vệ endpoint detail mà quên endpoint list hoặc export.

## 10. Java service: kiểm tra membership và quyền trên resource

Nên tập trung authorization vào application service hoặc policy component có thể test. Controller xử lý HTTP; service điều phối policy và nghiệp vụ.

Ví dụ service đọc project:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectQueryService {
    private final TenantAccessService tenantAccess;
    private final ProjectRepository projects;
    private final ProjectPolicy policy;

    public ProjectQueryService(
            TenantAccessService tenantAccess,
            ProjectRepository projects,
            ProjectPolicy policy) {
        this.tenantAccess = tenantAccess;
        this.projects = projects;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    public ProjectView getProject(
            Actor actor,
            UUID tenantId,
            UUID projectId) {

        TenantMembership membership =
                tenantAccess.requireActiveMember(actor.userId(), tenantId);

        Project project = projects.findByTenantIdAndId(tenantId, projectId)
                .orElseThrow(ProjectNotFoundException::new);

        ProjectMembership projectMembership =
                projects.findMembership(tenantId, projectId, actor.userId())
                        .orElse(null);

        if (!policy.canRead(membership, project, projectMembership)) {
            throw new AccessDeniedException("Not allowed to read project");
        }

        return ProjectView.from(project);
    }
}
~~~

Trong ứng dụng thực tế, nên gộp truy vấn theo tenant/actor khi phù hợp để tránh nhiều round trip và giảm khoảng cách giữa authorization check với read. Nếu policy dựa trên trạng thái resource, hãy đọc trạng thái và kiểm tra quyền trong cùng transaction hoặc trong query có predicate tương ứng.

Không trả entity JPA trực tiếp. DTO response giúp kiểm soát field nào được lộ và tránh serialize quan hệ nội bộ.

### Policy thuần Java

~~~java
public final class ProjectPolicy {
    public boolean canRead(
            TenantMembership tenant,
            Project project,
            ProjectMembership projectMember) {

        if (!tenant.isActive() || !project.isActive()) {
            return false;
        }
        if (tenant.role() == TenantRole.TENANT_ADMIN) {
            return true;
        }
        return projectMember != null
                && projectMember.isActive()
                && projectMember.role().canRead();
    }

    public boolean canEdit(
            TenantMembership tenant,
            Project project,
            ProjectMembership projectMember) {

        if (!tenant.isActive() || !project.isActive()) {
            return false;
        }
        if (tenant.role() == TenantRole.TENANT_ADMIN) {
            return true;
        }
        return projectMember != null
                && projectMember.isActive()
                && projectMember.role().canEdit();
    }
}
~~~

Policy này là ví dụ; enum và method phải được định nghĩa theo domain. Không đưa role string tùy ý từ client vào policy. Role cần được đọc từ database hoặc claim đã được xác minh theo một mô hình tin cậy có thời hạn rõ.

## 11. Ghi dữ liệu an toàn: scope tenant, authorization và optimistic locking

Với update, không nên:
1. Tải entity chỉ theo ID.
2. Tin client gửi owner/tenant mới.
3. Ghi lại toàn bộ object.

Thay vào đó:
- Lấy actor từ security context đã xác thực.
- Xác minh tenant membership và project role.
- Chỉ cho phép update các field trong allowlist.
- Dùng tenant ID trong predicate của UPDATE.
- Dùng optimistic locking/version để tránh ghi đè update đồng thời.
- Ghi audit record nếu hành động nhạy cảm.

Ví dụ SQL update task:

~~~sql
UPDATE task t
SET title = :title,
    description = :description,
    version = version + 1,
    updated_at = now()
WHERE t.tenant_id = :tenant_id
  AND t.id = :task_id
  AND t.version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM project p
      WHERE p.tenant_id = t.tenant_id
        AND p.id = t.project_id
        AND p.status = 'ACTIVE'
  )
  AND EXISTS (
      SELECT 1
      FROM tenant_membership tm
      WHERE tm.tenant_id = t.tenant_id
        AND tm.user_id = :actor_user_id
        AND tm.status = 'ACTIVE'
        AND (
            tm.role = 'TENANT_ADMIN'
            OR EXISTS (
                SELECT 1
                FROM project_member pm
                WHERE pm.tenant_id = t.tenant_id
                  AND pm.project_id = t.project_id
                  AND pm.user_id = tm.user_id
                  AND pm.status = 'ACTIVE'
                  AND pm.role IN ('OWNER', 'EDITOR')
            )
        )
  );
~~~

Nếu update count bằng 0, có thể do object không tồn tại trong tenant, actor không có quyền hoặc version đã thay đổi. API cần quyết định có phân biệt 404/403/409 hay trả cùng 404 để tránh tiết lộ object tồn tại. Không tự động coi update count 0 là lỗi database.

Với assignment, cần kiểm tra assignee là active tenant/project member trước khi update. Composite FK bảo vệ tenant consistency nhưng không tự bảo vệ project membership nếu assignee thuộc tenant nhưng không tham gia project.

## 12. Authorization cho list, search và pagination

Một lỗi phổ biến là endpoint detail có authorization nhưng endpoint list trả quá nhiều dữ liệu.

Mọi list/search query cần scope tenant và membership trước khi phân trang:

~~~sql
SELECT p.id, p.name, p.status, p.created_at
FROM project p
JOIN tenant_membership tm
  ON tm.tenant_id = p.tenant_id
 AND tm.user_id = :actor_user_id
 AND tm.status = 'ACTIVE'
LEFT JOIN project_member pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.id
 AND pm.user_id = :actor_user_id
 AND pm.status = 'ACTIVE'
WHERE p.tenant_id = :tenant_id
  AND (
      tm.role = 'TENANT_ADMIN'
      OR pm.role IN ('OWNER', 'EDITOR', 'VIEWER')
  )
  AND (p.created_at, p.id) < (:cursor_created_at, :cursor_id)
ORDER BY p.created_at DESC, p.id DESC
LIMIT :page_size;
~~~

Cursor cần gắn với filter/sort/tenant để không thể tái sử dụng cursor của tenant khác theo cách làm lộ dữ liệu. Có thể ký cursor hoặc lưu server-side. Giới hạn page size để tránh query quá lớn.

Nếu dùng offset pagination, dữ liệu thay đổi trong lúc đọc có thể làm bản ghi bị lặp hoặc bỏ qua giữa các trang. Keyset pagination thường ổn định hơn cho dataset lớn. Dù dùng kiểu nào, authorization predicate phải được áp dụng trên từng request/page.

## 13. Index theo access pattern và tenant key

Trong shared schema, nhiều query bắt đầu bằng tenant_id. Index nên phản ánh các access pattern thực tế:

| Access pattern | Index gợi ý |
|---|---|
| Tìm project theo tenant và ID | PK (tenant_id, id) |
| Liệt kê project member theo user | (tenant_id, user_id, project_id) |
| Liệt kê task theo project mới nhất | (tenant_id, project_id, created_at DESC, id) |
| Liệt kê task của owner theo status | (tenant_id, owner_user_id, status) |
| Tìm membership active của user | Partial index (user_id, tenant_id) WHERE status='ACTIVE' |

Không thêm index cho mọi cột. Index làm tăng chi phí write, storage và migration. Dùng query plan và production metrics để xác định index có ích.

Nếu tenant size rất khác nhau, một tenant lớn có thể tạo hot partition hoặc query chậm. Có thể cần partitioning, dedicated database hoặc workload isolation theo tenant tier.

## 14. Row-Level Security như defense in depth

PostgreSQL Row-Level Security (RLS) có thể giới hạn row dựa trên tenant context trong database session/transaction. RLS giúp giảm rủi ro khi một query quên điều kiện tenant, nhưng không thay thế business authorization.

Ví dụ policy:

~~~sql
ALTER TABLE project ENABLE ROW LEVEL SECURITY;
ALTER TABLE project FORCE ROW LEVEL SECURITY;

CREATE POLICY project_tenant_isolation
ON project
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Nếu app.tenant_id chưa được set, biểu thức trả NULL và không row nào thỏa điều kiện. Role ứng dụng không được là superuser, không có BYPASSRLS; FORCE RLS giúp table owner cũng chịu policy trong phạm vi PostgreSQL cho phép. Cần test bằng đúng DB role runtime.

### Set tenant context theo transaction

Với connection pool, không dùng session-level setting rồi để lại giá trị cho request tiếp theo. Dùng SET LOCAL hoặc set_config(..., true) trong transaction:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class TenantDatabaseContext {
    public void setTenant(Connection connection, UUID tenantId)
            throws SQLException {
        try (PreparedStatement statement =
                     connection.prepareStatement(
                             "select set_config('app.tenant_id', ?, true)")) {
            statement.setString(1, tenantId.toString());
            statement.execute();
        }
    }
}
~~~

Tham số thứ ba true làm setting có hiệu lực local trong transaction. Connection phải đang ở transaction phù hợp; sau commit/rollback, setting local được reset theo semantics PostgreSQL. Không chạy câu lệnh này trên autocommit connection rồi mong context tồn tại cho query kế tiếp.

RLS policy ở ví dụ chỉ giới hạn tenant cho bảng project. Cần áp dụng policy tương ứng cho mọi bảng tenant-owned như project_member và task; mỗi policy phải dùng tenant context nhất quán. Project membership, owner và action permission vẫn cần được kiểm tra trong ứng dụng hoặc policy DB bổ sung.

## 15. Serverless: không để tenant context rò giữa invocation

Function/container có thể được tái sử dụng. Các lỗi nguy hiểm gồm:
- Lưu currentTenantId trong static mutable field.
- Dùng ThreadLocal mà không clear trong finally.
- Tái sử dụng entity manager/connection có session setting cũ.
- Cache permission decision mà key không bao gồm tenant/user/resource hoặc không có expiry.
- Chuyển async task sang executor mà không truyền security context an toàn.

Mỗi invocation phải xây context từ token/event đã xác minh. Không dùng biến môi trường để lưu tenant của request. Environment variable chỉ dành cho cấu hình deployment, không phải state của user.

Nếu dùng ThreadLocal để tích hợp framework, phải đặt và clear context trong filter/interceptor với try/finally. Tốt hơn là truyền Actor/TenantContext rõ ràng qua application service để dependency dễ thấy và unit test được.

### Warm reuse và cache authorization

Cache membership có thể giảm query nhưng có rủi ro quyền cũ sau khi user bị remove hoặc role bị hạ. Nếu cache:
- Định nghĩa TTL ngắn theo mức nhạy cảm.
- Có invalidation khi membership thay đổi nếu cần revocation nhanh.
- Cache key bao gồm issuer/user, tenant và scope/resource.
- Không cache quyết định ALLOW lâu hơn thời gian policy có thể thay đổi.
- Với thao tác tài chính/admin, cân nhắc đọc quyền hiện tại từ store.

## 16. Event-driven worker và actor context

Khi HTTP API phát event để worker xử lý, end-user JWT thường không nên được chuyển nguyên vẹn qua queue. Token có thể hết hạn, lộ qua log/message hoặc tạo phụ thuộc không cần thiết.

Event có thể chứa metadata đã được server tạo:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "project.task.created",
  "tenantId": "tenant-123",
  "actor": {
    "userId": "user-456",
    "issuer": "https://identity.example.com/issuer",
    "subject": "subject-789"
  },
  "data": {
    "projectId": "project-1",
    "taskId": "task-9"
  }
}
~~~

Consumer cần:
- Xác minh event đến từ producer/service được phép.
- Kiểm tra schema và event type.
- Dùng workload identity riêng để truy cập database/queue.
- Dùng tenant ID từ event như context cần xác minh, không như bằng chứng tự thân.
- Áp dụng policy nghiệp vụ tương ứng.
- Ghi actor gốc vào audit nếu hành động được thực hiện thay mặt user.
- Dùng event ID/idempotency key để tránh xử lý lặp.

Nếu worker chỉ thực hiện một công việc hệ thống được ủy quyền, policy có thể dựa trên service principal thay vì re-check JWT user. Nếu công việc cần tuân theo quyền user tại thời điểm xử lý, phải xác định rõ kiểm tra quyền tại thời điểm nhận request hay thời điểm worker chạy; membership có thể đã bị thu hồi trong khoảng đó.

Không lưu raw access token vào event. Nếu cần delegation, dùng cơ chế token exchange/short-lived credential được nền tảng và identity provider hỗ trợ.

## 17. Tách user authorization khỏi workload IAM

Một Java function có thể có quyền IAM đọc database hoặc publish queue, nhưng quyền đó không nói user nào được xem row nào.

Hai lớp:

- **Workload IAM:** function được phép gọi dịch vụ cloud nào và trên resource nào.
- **Application authorization:** user/tenant được phép làm gì với business object nào.

Ví dụ:
- Lambda execution role có quyền đọc Orders table.
- API code vẫn phải giới hạn query theo tenant/user.
- Cloud Run service account có quyền đọc Secret Manager.
- User cuối không được đọc secret chỉ vì service có thể đọc nó.

Không truyền role cloud của user cuối hoặc credential dài hạn qua request. Function dùng execution role/service account; app dùng actor context đã xác thực để quyết định truy cập dữ liệu.

## 18. Xóa user, thu hồi membership và audit

Xóa tài khoản là thay đổi dữ liệu và quyền truy cập, không chỉ xóa một row.

Cần quyết định:
- Khi user bị suspend, token hiện tại còn được chấp nhận đến khi hết hạn không?
- Membership bị remove có thu hồi quyền ngay không?
- Task do user tạo có được giữ để audit không?
- Task được giao cho user có được reassign không?
- User có thể được mời lại vào tenant không?
- Dữ liệu cá nhân nào phải xóa/anonymize theo retention policy?
- Audit record cần giữ actor ID hay pseudonymous reference?

Không cascade delete mọi project/task chỉ vì user rời tenant. Business data có thể thuộc tenant chứ không thuộc user tạo ra. Thường nên giữ created_by như historical reference, xóa hoặc anonymize profile theo policy và thu hồi membership.

Audit log nên ghi actor, tenant, action, resource type/id, outcome, timestamp và correlation ID. Không ghi access token, password hoặc payload nhạy cảm.

## 19. API design và response behavior

Một số quy tắc API:

- Dùng HTTP 401 khi token thiếu/không hợp lệ.
- Dùng HTTP 403 khi actor đã xác thực nhưng không có quyền, nếu việc phân biệt không làm lộ tài nguyên.
- Dùng HTTP 404 cho resource không tồn tại hoặc không được phép nhìn thấy nếu policy yêu cầu tránh IDOR enumeration.
- Dùng HTTP 409 cho conflict nghiệp vụ hoặc optimistic lock conflict.
- Không trả stack trace, SQL hoặc policy internals cho client.
- Không để response chứa field nội bộ như tenant routing, secret reference hoặc audit metadata không được phép.

Response 404 cho object ngoài phạm vi có thể giảm khả năng dò object ID. Hãy áp dụng nhất quán trên GET, PATCH, DELETE và nested resource.

### Không để API trở thành confused deputy

Service có quyền truy cập nhiều tenant. Nếu client gửi tenantId/resourceId không được xác thực, service có thể vô tình dùng quyền rộng của chính nó để truy cập dữ liệu người khác. Luôn ràng buộc object query với actor và tenant đã authorize; không nhận một resource identifier rồi dùng service account đọc tùy tiện.

## 20. Kiểm thử authorization

Authorization test phải chứng minh cả allow và deny. Happy path một user đọc được project của mình không phát hiện lỗi IDOR.

| Tình huống | Kết quả mong đợi |
|---|---|
| User A active member và project editor | Đọc/sửa theo policy |
| User A là viewer | Đọc được, update bị từ chối |
| User B thuộc tenant khác | Không đọc/ghi được project |
| User bị suspended | Request bị từ chối |
| Membership đã removed | Quyền bị thu hồi theo policy |
| Tenant ID path khác tenant của project | Không tìm thấy/không truy cập |
| Client gửi ownerUserId/tenantId giả | Server bỏ qua hoặc từ chối |
| JWT audience sai | 401 |
| JWT issuer không tin cậy/hết hạn | 401 |
| Task owner không còn tenant membership | Không được assign theo policy |
| Cursor của tenant khác | Không truy cập dữ liệu tenant kia |
| Event giả mạo tenantId | Consumer từ chối hoặc quarantine |

### Unit test cho policy

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProjectPolicyTest {
    private final ProjectPolicy policy = new ProjectPolicy();

    @Test
    void viewerCanReadButCannotEdit() {
        TenantMembership member =
                TenantMembership.activeMember(TenantRole.MEMBER);
        Project project = Project.active();
        ProjectMembership viewer =
                ProjectMembership.active(ProjectRole.VIEWER);

        assertTrue(policy.canRead(member, project, viewer));
        assertFalse(policy.canEdit(member, project, viewer));
    }

    @Test
    void inactiveTenantMembershipDeniesAccess() {
        TenantMembership removed =
                TenantMembership.removed(TenantRole.MEMBER);

        assertFalse(policy.canRead(
                removed,
                Project.active(),
                ProjectMembership.active(ProjectRole.OWNER)));
    }
}
~~~

Factories ở đây là factory test của domain model. Test policy không cần JWT, database hoặc cloud runtime.

### Integration test chống cross-tenant access

Dùng database test thật hoặc container:
1. Tạo tenant A và tenant B.
2. Tạo user A trong tenant A và project của tenant A.
3. Tạo user B trong tenant B.
4. Gọi repository/service với user B và project A.
5. Xác nhận không có row được trả về hoặc mutation.
6. Thử cả GET, list, update, delete và export.
7. Chạy test bằng đúng database role runtime nếu có RLS.

Kiểm thử RLS bằng database owner/superuser có thể cho kết quả sai vì role đó có thể bypass policy. Test cần dùng role ứng dụng có quyền thực tế.

### Property/fuzz tests

Có thể sinh nhiều tenant/user/resource ID ngẫu nhiên và xác minh invariant: không actor nào đọc được row có tenant khác nếu không có explicit authorization. Với bulk API, test danh sách chứa ID hợp lệ và ID ngoài tenant; server không được trả một phần dữ liệu trái phép hoặc thực hiện side effect cho item bị từ chối.

## 21. Checklist thiết kế data model và access control

- [ ] User nội bộ được ánh xạ bằng issuer + subject, không dựa vào email làm ID.
- [ ] User có thể thuộc nhiều tenant qua membership riêng.
- [ ] Tenant membership và project membership có status/role rõ.
- [ ] Mọi resource tenant-owned có tenant key hoặc quan hệ tenant rõ ràng.
- [ ] Composite foreign key ngăn liên kết chéo tenant.
- [ ] Unique/index được thiết kế theo access pattern và tenant scope.
- [ ] RBAC/ABAC/ownership được định nghĩa theo từng action/resource.
- [ ] Default deny khi không có policy allow.
- [ ] JWT kiểm tra issuer, signature, expiry và audience.
- [ ] Tenant ID do client chọn luôn được xác minh membership.
- [ ] Object-level authorization áp dụng cho detail, list, update, delete và export.
- [ ] Request DTO không cho client mass-assign tenant, role, creator hoặc status nội bộ.
- [ ] Update query có tenant predicate và optimistic locking khi cần.
- [ ] RLS được xem là defense in depth và test bằng runtime DB role.
- [ ] Connection pool không giữ tenant context của invocation trước.
- [ ] Không dùng static mutable field/ThreadLocal không cleanup để lưu actor/tenant.
- [ ] Event không chứa raw user access token; consumer xác minh producer và tenant context.
- [ ] Workload IAM tách biệt với user authorization.
- [ ] Membership revocation và account deletion có policy rõ.
- [ ] Audit log không chứa credential/PII dư thừa.
- [ ] Có positive, negative, cross-tenant, revocation và RLS integration tests.

## Tự kiểm tra

1. Authentication và authorization khác nhau ở câu hỏi nào?
2. Vì sao issuer + subject ổn định hơn email để ánh xạ user?
3. Một user thuộc nhiều tenant cần mô hình membership như thế nào?
4. Composite foreign key bảo vệ tenant boundary ra sao?
5. RBAC khác ABAC và ownership như thế nào?
6. Vì sao tenant ID trong URL không chứng minh caller có quyền truy cập tenant?
7. IDOR vẫn xảy ra được dù resource ID là UUID vì sao?
8. Vì sao phải scope cả list/search query theo tenant và actor?
9. RLS bổ sung lớp bảo vệ nào và không thay thế điều gì?
10. Connection pool và warm instance có thể làm tenant context rò rỉ ra sao?
11. Vì sao không nên truyền raw JWT qua queue cho worker?
12. Workload IAM khác application authorization ở điểm nào?
13. Khi membership bị thu hồi, cache/token cũ ảnh hưởng quyết định quyền ra sao?
14. Những integration test nào cần có để chứng minh không truy cập chéo tenant?

Một API serverless an toàn cần mô hình dữ liệu thể hiện rõ user, tenant, membership và resource ownership; mỗi request được xác thực bằng identity tin cậy rồi authorize theo tenant, action và object cụ thể. Composite constraint, tenant-scoped query, RLS, workload IAM và test cross-tenant bổ sung cho nhau. Khi Java function được tái sử dụng qua nhiều invocation, actor/tenant context phải được tạo theo từng request và không được rò sang request tiếp theo.

