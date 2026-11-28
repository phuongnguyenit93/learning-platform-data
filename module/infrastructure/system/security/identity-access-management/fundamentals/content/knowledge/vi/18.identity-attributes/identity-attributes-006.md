# Tenant attribute

## 1. Tenant attribute là gì?

**Tenant attribute** là thuộc tính dùng để biểu diễn phạm vi tổ chức hoặc không gian khách hàng mà một danh tính, quan hệ thành viên, tài nguyên hay yêu cầu đang gắn với. Trong một ứng dụng SaaS, tenant có thể là một công ty khách hàng, một workspace hoặc một đơn vị sử dụng được quản trị độc lập theo thiết kế của ứng dụng.

Ví dụ, một nền tảng quản lý hóa đơn phục vụ hai khách hàng:

~~~text
Tenant T-A: Công ty An Phú
Tenant T-B: Công ty Bình Minh
~~~

Alice có thể được mời tham gia cả hai tenant. Khi Alice yêu cầu đọc hóa đơn, hệ thống cần biết không chỉ “đây có phải Alice không?” mà còn:

- Alice đang thao tác trong tenant nào?
- Alice có quan hệ thành viên còn hiệu lực ở tenant đó không?
- Quyền đang xét được cấp trong tenant nào?
- Hóa đơn đích có thuộc đúng phạm vi đó không?

Một trường `tenantId` chỉ có giá trị bảo mật khi hệ thống định nghĩa rõ ý nghĩa, nguồn cấp, cách xác minh và cách thực thi nó.

Trong IAM, tenant attribute kết nối danh tính với quản trị tài khoản, RBAC/ABAC, SSO, cấp phát thành viên, workload identity và kiểm toán. Nó hỗ trợ xác định ranh giới quyền; không tự thay thế toàn bộ chính sách phân quyền.

Sau bài này, người học có thể:

1. Phân biệt tenant của nhà cung cấp danh tính với tenant nghiệp vụ của ứng dụng.
2. Mô hình hóa người dùng tham gia nhiều tenant mà không làm lẫn quyền.
3. Phân biệt tenant do client lựa chọn với tenant context đã được server xác minh.
4. Truyền và thực thi tenant context trong API, dữ liệu và tác vụ nền.
5. Kiểm thử truy cập chéo tenant, thay đổi membership và rò rỉ ngữ cảnh.

## 2. “Tenant” không luôn chỉ cùng một loại ranh giới

### 2.1. Các nghĩa thường gặp

| Khái niệm | Ý nghĩa trong một thiết kế có thể có | Ví dụ |
| --- | --- | --- |
| Identity provider tenant | Phạm vi thư mục hoặc quản trị tại nhà cung cấp danh tính | Một Microsoft Entra tenant |
| Application tenant | Phạm vi khách hàng/workspace do ứng dụng quản lý | `T-A` trong nền tảng hóa đơn |
| Resource tenant | Tenant sở hữu một tài nguyên nghiệp vụ | Hóa đơn `INV-7` thuộc `T-A` |
| Active tenant | Tenant được chọn và xác minh cho thao tác hiện tại | Alice đang làm việc trong `T-B` |
| Home organization | Tổ chức gốc của một tài khoản theo mô hình liên kết danh tính | Công ty tuyển dụng Alice |
| Infrastructure partition | Đơn vị triển khai hoặc lưu trữ | Một database, schema hoặc cluster |

Các khái niệm này có thể ánh xạ một-một, nhưng không có lý do để mặc định chúng luôn trùng nhau.

Một application tenant có thể cho phép người dùng từ nhiều identity provider. Ngược lại, nhiều application tenant có thể dùng chung một nhà cung cấp đăng nhập. Một cụm cơ sở dữ liệu cũng có thể lưu nhiều tenant.

Do đó, trước khi dùng thuộc tính tên `tenant`, phải trả lời: “Tenant của hệ thống nào và của đối tượng nào?”.

### 2.2. Tenant không nhất thiết là pháp nhân hoặc đơn vị thanh toán

Một doanh nghiệp có thể có nhiều workspace độc lập. Một tenant có thể bao gồm cộng tác viên ngoài doanh nghiệp. Gói thuê bao, vùng lưu trữ và phòng ban cũng không nhất thiết là tenant.

Không nên dùng trực tiếp:

~~~text
tenantId = emailDomain
tenantId = department
tenantId = billingAccountName
~~~

trừ khi mô hình nghiệp vụ thực sự định nghĩa và kiểm soát quan hệ tương ứng.

Ngay cả khi ứng dụng dùng tên miền để hỗ trợ khám phá tổ chức lúc đăng nhập, tên miền đó vẫn chỉ là một đầu mối định tuyến. Việc xác định danh tính, membership và quyền phải tuân theo hợp đồng tin cậy của hệ thống.

## 3. Một người dùng có thể thuộc nhiều tenant

### 3.1. Tránh mô hình “một user chỉ có một tenant” khi nghiệp vụ không như vậy

Giả sử:

~~~text
Alice:
    T-A -> ADMIN
    T-B -> VIEWER

Bob:
    T-A -> VIEWER
~~~

Nếu lưu duy nhất:

~~~text
user.role = ADMIN
user.tenantId = T-A
~~~

rồi đổi `user.tenantId` thành `T-B` khi chuyển workspace, ứng dụng có thể giữ nguyên vai trò `ADMIN` và vô tình trao quyền quản trị trong `T-B`.

Một mô hình phù hợp hơn cho ví dụ là:

~~~text
Subject
    subjectId

Membership
    tenantId
    subjectId
    state
    authorizationVersion

RoleBinding
    tenantId
    subjectId
    roleId
~~~

Vai trò của Alice được giải quyết từ membership và role binding **trong tenant đang xét**, không lấy từ một cờ quản trị toàn cục trên hồ sơ người dùng.

### 3.2. Tách tenant được phép tham gia khỏi tenant đang hoạt động

Tập membership và active tenant có nhiệm vụ khác nhau:

~~~text
Alice có membership trong: {T-A, T-B}
Yêu cầu hiện tại hoạt động trong: T-B
Quyền hiện tại được lấy từ: membership(Alice, T-B)
~~~

Một danh sách `tenantIds` không nên tự được hiểu thành quyền gộp trên tất cả tenant trong mọi request.

Với API đọc dữ liệu theo một tenant, một ngữ cảnh rõ ràng giúp tránh truy vấn nhầm phạm vi. Nếu nghiệp vụ có báo cáo nhiều tenant, đó phải là một use case có chính sách riêng, xác định tập tenant được phép và cách bảo vệ kết quả tổng hợp.

### 3.3. Danh tính bên ngoài cần được ánh xạ có chủ đích

Trong OpenID Connect, cặp `iss` và `sub` là cơ sở định danh ổn định cho người dùng trong phạm vi issuer; không nên dùng email thay cho khóa danh tính. Email có thể thay đổi hoặc được tái sử dụng. [Nguồn: OpenID Connect Core, mục 5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability).

Ứng dụng có thể ánh xạ:

~~~text
(externalIssuer, externalSubject)
    -> internalSubjectId
~~~

rồi quản lý membership bằng `internalSubjectId`.

Nếu cùng một con người xuất hiện với nhiều danh tính liên kết, việc gộp tài khoản phải có quy trình xác minh riêng. Không tự gộp chỉ vì hai tài khoản có cùng email và từ đó kế thừa membership của nhau.

## 4. Hợp đồng dữ liệu của thuộc tính tenant

### 4.1. Đặt tên theo ý nghĩa

Những tên sau rõ nghĩa hơn việc dùng một trường `tenant` ở mọi nơi:

~~~text
idpTenantId
applicationTenantId
resourceTenantId
requestedTenantId
resolvedTenantId
~~~

Không phải hệ thống nào cũng cần tất cả các trường này. Mục tiêu là tránh nhầm một giá trị dùng để tìm cấu hình đăng nhập với một giá trị đã đủ tin cậy để giới hạn dữ liệu.

### 4.2. Ví dụ về hợp đồng cho application tenant

Trong nền tảng hóa đơn giả định của bài, có thể chọn hợp đồng:

| Thuộc tính hợp đồng | Quyết định của ví dụ |
| --- | --- |
| Định danh | `applicationTenantId` bất biến, không tái cấp cho một tenant khác |
| Kiểu dữ liệu | UUID nội bộ; `T-A` và `T-B` chỉ là ký hiệu dễ đọc trong diễn giải |
| Nhãn hiển thị | Tên tenant và slug có thể thay đổi, không làm khóa quyền |
| Nguồn quản lý | Dịch vụ quản trị tenant của ứng dụng |
| Trạng thái | `ACTIVE`, `SUSPENDED` hoặc `CLOSED` |
| Quan hệ thành viên | Bảng membership do server quản lý |
| Phạm vi mỗi request dữ liệu | Đúng một tenant đã giải quyết |
| Thiếu hoặc xung đột tenant | Từ chối trước khi truy cập dữ liệu |
| Truy cập nhiều tenant | Use case riêng, không dùng giá trị tenant rỗng để biểu diễn |

Đây là các lựa chọn thiết kế cho ví dụ, không phải một chuẩn tên trường áp dụng cho mọi IAM.

### 4.3. Thuộc tính cần có nguồn gốc và độ mới

Nếu tenant attribute tham gia quyết định quyền, cần biết:

~~~text
Giá trị là gì?
Ai cấp hoặc xác nhận?
Nó áp dụng cho danh tính/yêu cầu/tài nguyên nào?
Được ghi nhận khi nào?
Có còn hiệu lực theo chính sách hiện tại không?
~~~

Một giá trị có chữ ký không đồng nghĩa luôn còn mới. Một membership đã đúng hôm qua có thể bị thu hồi hôm nay. Tính toàn vẹn của dữ liệu và độ mới của quyền là hai yêu cầu khác nhau.

## 5. Nguồn nào được quyền xác nhận tenant?

### 5.1. Tenant do client gửi là một lựa chọn yêu cầu

Các cách chọn tenant thường gặp:

~~~http
GET /api/tenants/T-A/invoices
X-Tenant-Id: T-A
~~~

Hoặc:

~~~text
an-phu.example.test
~~~

Path, header và hostname có thể giúp định tuyến hoặc chọn workspace. Chúng không tự chứng minh người gọi là thành viên của tenant đó.

Một trình tự hợp lệ về mặt ý nghĩa là:

~~~text
Client yêu cầu tenant T-A
        ↓
Server xác minh danh tính
        ↓
Server kiểm tra ràng buộc token và membership cho T-A
        ↓
Server tạo tenant context đã xác minh
        ↓
Service chỉ dùng context đó để truy cập dữ liệu
~~~

Nếu nhiều vị trí được phép mang tenant, cần định nghĩa nguồn chuẩn và cách xử lý xung đột. Không nên âm thầm lấy tenant từ header cho truy vấn, nhưng lấy tenant từ path để ghi audit.

Trong ví dụ của bài, path là selector và token được ràng buộc tenant. Nếu hai giá trị không trùng sau bước ánh xạ, yêu cầu bị từ chối.

### 5.2. Thuộc tính trong hồ sơ tự sửa không phải bằng chứng quyền

Một hồ sơ người dùng có trường:

~~~json
{
  "displayName": "Alice",
  "company": "An Phú",
  "tenantId": "T-A"
}
~~~

không có giá trị cấp quyền nếu chủ thể tự sửa được `tenantId` mà không qua kiểm soát.

Cần tách những thuộc tính dùng để hiển thị khỏi thuộc tính quản trị membership. Đổi tên công ty trên hồ sơ không được trở thành cách gia nhập một tenant hoặc chuyển quyền dữ liệu.

### 5.3. Dịch vụ nội bộ cũng phải có hợp đồng tin cậy

Nếu gateway chuyển `X-Resolved-Tenant` xuống service, service cần biết header đó được ai tạo và có thể bị ghi đè ở đâu.

Thiết kế có thể bảo vệ bằng xác thực service-to-service, token nội bộ có audience phù hợp hoặc một cơ chế truyền ngữ cảnh được kiểm soát. Gateway phải xử lý các header tương tự từ bên ngoài theo quy tắc rõ ràng; không để header do client đặt được hiểu thành xác nhận nội bộ.

Mạng “nội bộ” không tự làm mọi giá trị tenant trở thành đáng tin cậy. Service vẫn cần ràng buộc tenant với danh tính gọi, quyền công việc và tài nguyên đích.

## 6. Tenant trong token và liên kết danh tính

### 6.1. Không áp dụng ý nghĩa claim của một nhà cung cấp cho tất cả nhà cung cấp

Microsoft identity platform định nghĩa `tid` là tenant mà người dùng đang đăng nhập vào; với tài khoản cơ quan hoặc trường học, đây là định danh tenant bất biến của tổ chức tương ứng. Tài liệu cũng yêu cầu xem xét claim này cùng các claim khác trong quyết định quyền. [Nguồn: Microsoft — Access token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference).

Điều đó không có nghĩa mọi token OIDC đều có `tid`, hoặc mọi `tid` đều bằng khóa tenant nghiệp vụ của một ứng dụng bất kỳ.

Ví dụ ánh xạ có thể là:

~~~text
Microsoft Entra tid = E-100
        ↓ cấu hình liên kết đã xác minh
Application tenant = T-A
~~~

Nếu một thư mục danh tính phục vụ nhiều workspace ứng dụng, ánh xạ còn cần thêm thông tin và chính sách lựa chọn. Không được suy ra một tenant ứng dụng chỉ từ tên claim.

Với tài khoản khách hoặc liên kết danh tính, tổ chức gốc và tenant đang truy cập cũng có thể khác nhau. Cần dùng ý nghĩa claim do provider công bố, không suy diễn rằng một claim luôn chỉ nơi tuyển dụng người dùng.

### 6.2. Xác minh token trước khi dùng claim tenant

Giải mã JSON của JWT chưa phải xác minh token. Resource server phải áp dụng profile token phù hợp, bao gồm kiểm tra mật mã, issuer, audience, thời hạn và các ràng buộc bắt buộc của profile.

RFC 8725 nhấn mạnh việc xác minh issuer/subject, audience và dùng quy tắc phân biệt các loại JWT để hạn chế thay thế token giữa các ngữ cảnh. [Nguồn: RFC 8725, mục 3.8–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.8).

Với API được thiết kế nhận access token, không tự chấp nhận ID token chỉ vì nó cũng có `sub` và tenant claim.

Khóa xác minh phải thuộc một quan hệ tin cậy đã được cấu hình hoặc khám phá theo quy trình kiểm soát. Không dùng một issuer hoặc URL khóa tùy ý do token chưa xác minh cung cấp để tự mở rộng tập nhà phát hành được tin cậy.

### 6.3. Hai mô hình ràng buộc tenant khác nhau

| Mô hình | Token/ngữ cảnh đầu vào | Cách chọn tenant |
| --- | --- | --- |
| Token ràng buộc một tenant | Token được cấp cho `T-A` theo profile ứng dụng | Request `T-B` bị từ chối; chuyển tenant cần lấy credential phù hợp |
| Chọn tenant bằng membership phía server | Credential xác thực chủ thể theo hợp đồng cho phép mô hình này | Server xác minh membership cho tenant được chọn ở mỗi luồng cần thiết |

Không nên lẫn hai mô hình. Nếu endpoint yêu cầu token ràng buộc tenant mà claim tenant bị thiếu, không được tự chuyển sang mô hình thứ hai để “cho chạy tiếp”.

Một đoạn claims giả định cho mô hình thứ nhất:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "subject-81",
  "aud": "invoice-api",
  "app_tenant_id": "T-A",
  "membership_version": 12
}
~~~

Đây chỉ là trích đoạn dữ liệu minh họa, không phải một token hoàn chỉnh hoặc token dùng được. `app_tenant_id` và `membership_version` là claim do ví dụ tự định nghĩa; chúng cần hợp đồng giữa bên cấp token và API.

Một token đúng tenant vẫn có thể không đủ quyền cho hành động cụ thể. Với mô hình của bài, API còn kiểm tra tenant đang hoạt động, membership và permission tương ứng.

## 7. Giải quyết tenant context theo một luồng rõ ràng

### 7.1. Chính sách của ứng dụng minh họa

Từ phần này, ứng dụng hóa đơn dùng mô hình:

1. Access token đã được xác minh và ràng buộc đúng một application tenant.
2. Path chứa tenant được client chọn.
3. Tenant trên path phải trùng tenant đã được ánh xạ từ token.
4. Tenant phải `ACTIVE` và membership phải `ACTIVE`.
5. Quyền được lấy từ membership trong chính tenant đó.
6. Tài nguyên phải nằm trong tenant context đã giải quyết.

Trong ví dụ, `INVOICE_READ` cho phép đọc hóa đơn trong tenant tương ứng. Nếu doanh nghiệp muốn hạn chế thêm theo owner, phòng ban hoặc độ nhạy hóa đơn thì phải bổ sung các điều kiện đó.

### 7.2. Không dùng tenant rỗng để vượt ranh giới

Những nhánh sau là lựa chọn nguy hiểm nếu xuất hiện ngầm trong API dữ liệu tenant:

~~~text
Không có tenant -> lấy tenant đầu tiên trong danh sách.
Tenant không tồn tại -> chuyển về tenant mặc định.
Tenant rỗng -> bỏ điều kiện tenant trong truy vấn.
role = ADMIN -> được đọc mọi tenant.
~~~

Một ứng dụng có thể có tenant mặc định để hỗ trợ trải nghiệm, nhưng server vẫn phải xác minh membership và chính sách trước khi dùng nó. Tenant mặc định không phải đường dự phòng để bỏ kiểm tra.

Quản trị viên tenant và người vận hành nền tảng cũng là hai loại quyền khác nhau. Truy cập quản trị nhiều tenant cần use case, phạm vi và audit riêng.

### 7.3. Phân biệt định tuyến với phân quyền

Một registry có thể ánh xạ:

~~~text
resolvedTenantId -> database/schema/storage partition
~~~

Đây là quyết định chọn nơi truy cập. Nó cần diễn ra sau khi tenant được giải quyết theo hợp đồng tin cậy, hoặc được kiểm soát sao cho selector chưa xác minh không mở quyền dữ liệu.

Một database riêng cho tenant không sửa được lỗi ứng dụng chọn nhầm database theo header giả mạo. Với tài nguyên dùng chung, điều kiện tenant cần được thực thi phù hợp ở truy vấn hoặc lớp kiểm soát dữ liệu.

AWS cũng phân biệt tenant isolation với việc người dùng đã được xác thực: xác thực thành công không tự chứng minh rằng tài nguyên giữa các tenant được cô lập. [Nguồn: AWS — Tenant isolation](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html).

## 8. Ví dụ Java: chỉ tạo context sau khi xác minh quan hệ

Đoạn mã Java 17 sau minh họa bước giải quyết tenant context cho mô hình token ràng buộc một tenant. `VerifiedPrincipal` phải được tạo bởi thành phần xác thực phía server sau khi token đã được kiểm tra và ánh xạ sang định danh nội bộ.

Các repository trong ví dụ là giao diện minh họa; chúng không được lấy dữ liệu membership hoặc quyền trực tiếp từ body của request.

~~~java
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

final class TenantContextResolver {
    enum TenantState {
        ACTIVE, SUSPENDED, CLOSED
    }

    enum MembershipState {
        INVITED, ACTIVE, SUSPENDED, REVOKED
    }

    enum Permission {
        INVOICE_READ, INVOICE_WRITE, MEMBER_INVITE
    }

    record VerifiedPrincipal(UUID subjectId, UUID tokenTenantId) {
        VerifiedPrincipal {
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(tokenTenantId);
        }
    }

    record Tenant(UUID id, TenantState state, long version) {}

    record Membership(
        UUID tenantId,
        UUID subjectId,
        MembershipState state,
        long authorizationVersion,
        Set<Permission> permissions
    ) {
        Membership {
            permissions = Set.copyOf(permissions);
        }
    }

    record ResolvedContext(
        UUID subjectId,
        UUID tenantId,
        long tenantVersion,
        long membershipVersion,
        Set<Permission> permissions
    ) {
        ResolvedContext {
            permissions = Set.copyOf(permissions);
        }
    }

    interface TenantDirectory {
        Optional<Tenant> findById(UUID tenantId);
    }

    interface MembershipDirectory {
        Optional<Membership> find(
            UUID tenantId,
            UUID subjectId
        );
    }

    static final class Denied extends RuntimeException {
        Denied(String reason) {
            super(reason);
        }
    }

    private final TenantDirectory tenants;
    private final MembershipDirectory memberships;

    TenantContextResolver(
        TenantDirectory tenants,
        MembershipDirectory memberships
    ) {
        this.tenants = Objects.requireNonNull(tenants);
        this.memberships = Objects.requireNonNull(memberships);
    }

    ResolvedContext resolve(
        VerifiedPrincipal principal,
        UUID requestedTenantId
    ) {
        if (principal == null || requestedTenantId == null) {
            throw new Denied("MISSING_TENANT_CONTEXT");
        }

        if (!requestedTenantId.equals(principal.tokenTenantId())) {
            throw new Denied("TOKEN_TENANT_MISMATCH");
        }

        Tenant tenant = tenants.findById(requestedTenantId)
            .orElseThrow(() -> new Denied("TENANT_UNAVAILABLE"));

        if (!requestedTenantId.equals(tenant.id())
                || tenant.state() != TenantState.ACTIVE) {
            throw new Denied("TENANT_UNAVAILABLE");
        }

        Membership membership = memberships.find(
            tenant.id(), principal.subjectId()
        ).orElseThrow(() -> new Denied("NO_ACTIVE_MEMBERSHIP"));

        if (!tenant.id().equals(membership.tenantId())
                || !principal.subjectId()
                    .equals(membership.subjectId())
                || membership.state() != MembershipState.ACTIVE) {
            throw new Denied("NO_ACTIVE_MEMBERSHIP");
        }

        return new ResolvedContext(
            principal.subjectId(),
            tenant.id(),
            tenant.version(),
            membership.authorizationVersion(),
            membership.permissions()
        );
    }

    static boolean canReadInvoice(
        ResolvedContext context,
        UUID invoiceTenantId
    ) {
        return context != null
            && context.tenantId().equals(invoiceTenantId)
            && context.permissions()
                .contains(Permission.INVOICE_READ);
    }
}
~~~

Ví dụ thể hiện một số quyết định quan trọng:

- Tenant do client chọn phải khớp tenant từ credential đã được xác minh.
- Tenant tồn tại chưa đủ; trạng thái tenant phải được phép phục vụ yêu cầu.
- Membership được tra bằng cả tenant và subject.
- Permission đi theo membership vừa tìm, không gộp quyền ở các tenant khác.
- Tập permission được sao chép bất biến để hạn chế việc sửa ngữ cảnh ngoài ý muốn.
- Thiếu context hoặc không có quan hệ hợp lệ làm luồng dừng trước khi đọc hóa đơn.

Đây chưa phải một thư viện xác thực hoàn chỉnh. Tên `VerifiedPrincipal` hoặc `ResolvedContext` không tự tạo ra bảo đảm; cần kiểm soát đường tạo và đường sử dụng các giá trị này trong ứng dụng thật.

Các số phiên bản chỉ ghi lại snapshot đã dùng. Nếu dữ liệu thay đổi sau khi context được tạo, việc có trường version không tự làm snapshot cũ trở thành mới. Service cần chính sách kiểm tra lại và cơ chế nhất quán phù hợp với hành động.

Nếu kho tenant hoặc membership gặp lỗi, không được bắt lỗi rồi tạo context mặc định. Có thể ánh xạ lỗi hạ tầng thành phản hồi phù hợp, nhưng không biến “không xác minh được” thành “được phép”.

## 9. Tenant attribute trên tài nguyên và trong cơ sở dữ liệu

### 9.1. Tài nguyên cần mang ranh giới tenant của chính nó

Một invoice có thể mang:

~~~text
Invoice
    tenantId
    invoiceId
    status
    amount
~~~

Nếu mã hóa đơn chỉ duy nhất trong mỗi tenant, `INV-7` có thể tồn tại ở cả `T-A` và `T-B`. Khóa logic phải bao gồm tenant:

~~~text
(tenantId, invoiceId)
~~~

Ngay cả khi `invoiceId` duy nhất toàn hệ thống, truy vấn vẫn cần bảo đảm tài nguyên thuộc tenant đang xét quyền. Tính duy nhất của ID và quyền truy cập là hai việc khác nhau.

### 9.2. Khóa ghép giúp ràng buộc quan hệ đúng tenant

Một schema SQL minh họa, dùng chuỗi để biểu diễn định danh:

~~~sql
CREATE TABLE tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(16) NOT NULL,
    authorization_version BIGINT NOT NULL
);

CREATE TABLE subjects (
    subject_id VARCHAR(64) PRIMARY KEY
);

CREATE TABLE memberships (
    tenant_id VARCHAR(64) NOT NULL,
    subject_id VARCHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    authorization_version BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, subject_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE invoices (
    tenant_id VARCHAR(64) NOT NULL,
    invoice_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE invoice_lines (
    tenant_id VARCHAR(64) NOT NULL,
    invoice_id VARCHAR(64) NOT NULL,
    line_id VARCHAR(64) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id, line_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES invoices(tenant_id, invoice_id)
);
~~~

Khóa ngoại ghép của `invoice_lines` buộc dòng hóa đơn tham chiếu hóa đơn trong cùng tenant. Tuy nhiên, schema này chưa tự biết người gọi được đọc gì; ứng dụng vẫn cần xét quyền.

Đây là phần schema tối thiểu để minh họa ranh giới. Các ràng buộc trạng thái, bảng role/permission, chỉ mục và kiểu dữ liệu cụ thể phải được bổ sung theo hệ quản trị và nghiệp vụ thật.

Với role tự định nghĩa theo tenant, role binding cũng cần ràng buộc đúng tenant của membership và role. Không join role của Alice trong `T-A` rồi dùng kết quả cho membership `T-B` chỉ vì cùng `subjectId`.

### 9.3. Truy vấn phải nhận tenant từ context đã giải quyết

~~~sql
SELECT invoice_id, status
FROM invoices
WHERE tenant_id = :context_tenant_id
  AND invoice_id = :requested_invoice_id;
~~~

Trước truy vấn, service đã phải xác minh permission cho hành động. `context_tenant_id` lấy từ `ResolvedContext`; `requested_invoice_id` là dữ liệu yêu cầu do client gửi.

Tạo mới cũng cần ràng buộc tenant:

~~~sql
INSERT INTO invoices (tenant_id, invoice_id, status)
VALUES (:context_tenant_id, :new_invoice_id, 'DRAFT');
~~~

Không bind `tenant_id` của bản ghi mới trực tiếp từ một trường body mà người gọi tùy ý sửa.

Khi join các bảng có ID cục bộ theo tenant:

~~~sql
SELECT i.invoice_id, l.line_id, l.description
FROM invoices i
JOIN invoice_lines l
  ON l.tenant_id = i.tenant_id
 AND l.invoice_id = i.invoice_id
WHERE i.tenant_id = :context_tenant_id
  AND i.invoice_id = :requested_invoice_id;
~~~

Bỏ điều kiện tenant trong join có thể trộn các đối tượng có cùng mã cục bộ.

### 9.4. Cô lập dữ liệu không chỉ nằm ở bảng chính

Cần áp dụng cùng ý nghĩa tenant cho:

- Danh sách, tìm kiếm, tổng số và số liệu tổng hợp.
- File xuất, bản xem trước và tệp đính kèm.
- Chỉ mục tìm kiếm hoặc bản sao dữ liệu.
- Cache và kết quả tính toán trung gian.
- Đường dẫn đọc, cập nhật và xóa theo batch.

Nếu bảng chính được lọc đúng nhưng endpoint tìm kiếm trả kết quả mọi tenant, ranh giới vẫn bị phá vỡ.

Cơ chế ở tầng dữ liệu như row policy hoặc database riêng có thể bổ sung việc thực thi. Cần xác minh quyền thực tế của tài khoản kết nối, cách chọn partition và đường truy cập có thể bỏ qua cơ chế đó; không chỉ dựa vào tên gọi của một tính năng.

## 10. Chuyển tenant trong phiên và giao diện nhiều tab

### 10.1. Chuyển tenant là thay ngữ cảnh quyền

Với Alice có `ADMIN` ở `T-A` và `VIEWER` ở `T-B`, việc chuyển workspace cần làm cho yêu cầu mới dùng quyền của `T-B`.

Trong mô hình token ràng buộc tenant, một luồng có thể là:

~~~text
1. Alice yêu cầu chuyển sang T-B.
2. Server xác minh Alice còn membership hợp lệ trong T-B.
3. Thành phần có thẩm quyền cấp hoặc thiết lập credential phù hợp T-B.
4. Client cập nhật ngữ cảnh cho các request tiếp theo.
5. API tiếp tục đối chiếu tenant selector với credential ở mỗi request.
~~~

Không sửa claim `app_tenant_id` bằng cách giải mã JWT rồi thay chuỗi ở client. Việc cấp credential phải thuộc thành phần được phép và theo profile xác thực của hệ thống.

Chuyển tenant không nhất thiết yêu cầu nhập lại mật khẩu trong mọi sản phẩm. Yêu cầu tái xác thực phụ thuộc session, độ nhạy thao tác và chính sách; điều bắt buộc trong thiết kế ví dụ là ngữ cảnh mới phải được xác minh.

### 10.2. Cẩn thận với active tenant dùng chung cho mọi tab

Giả sử:

~~~text
Tab 1: Alice đang sửa hóa đơn trong T-A.
Tab 2: Alice chuyển giao diện sang T-B.
Tab 1: Gửi request lưu nhưng sử dụng activeTenant toàn cục vừa đổi.
~~~

Nếu request không ràng buộc được tài nguyên, tenant và credential, người dùng có thể thao tác nhầm phạm vi.

Có thể thiết kế tenant theo route và credential của từng request, hoặc dùng một hợp đồng phiên khác xử lý rõ tình huống nhiều tab. Trong mọi trường hợp, server phải kiểm tra tài nguyên có thuộc tenant request đã xác minh.

Giao diện nên hiển thị tenant đang thao tác ở các màn hình quan trọng, nhưng nhãn hiển thị không phải kiểm soát quyền. Client có lỗi hoặc bị sửa vẫn phải không vượt được giới hạn server.

## 11. Vòng đời tenant và membership

### 11.1. Hai vòng đời độc lập

Một tenant còn hoạt động không có nghĩa mọi tài khoản từng tham gia vẫn có quyền. Một membership còn lưu trong dữ liệu cũng không có nghĩa tenant được tiếp tục phục vụ.

| Đối tượng | Thay đổi ví dụ | Ảnh hưởng cần định nghĩa |
| --- | --- | --- |
| Tenant | `ACTIVE -> SUSPENDED` | Những API dữ liệu nào phải bị chặn? |
| Tenant | `SUSPENDED -> ACTIVE` | Có khôi phục toàn bộ quyền trước đó không? |
| Membership | `INVITED -> ACTIVE` | Khi nào lời mời trở thành tư cách thành viên? |
| Membership | `ACTIVE -> SUSPENDED` | Credential và cache cũ còn được dùng bao lâu? |
| Membership | `ACTIVE -> REVOKED` | Job thay người dùng và quyền truy cập tiếp theo xử lý ra sao? |
| Role binding | `ADMIN -> VIEWER` | Phiên bản quyền và các quyết định đang cache được cập nhật thế nào? |

Trong ví dụ Java, chỉ `TenantState.ACTIVE` và `MembershipState.ACTIVE` được chấp nhận cho API dữ liệu. Các API phục hồi tenant, thanh toán hoặc vận hành có thể có chính sách khác, nhưng phải được định nghĩa riêng.

### 11.2. Mời và cấp phát tài khoản phải có nguồn có thẩm quyền

Một quy trình mời cần gắn lời mời với đúng tenant, người được mời hoặc cơ chế nhận lời mời, thời hạn và vai trò dự kiến. Người nhận không được tự sửa tenant hoặc nâng vai trò trong quá trình chấp nhận.

Với đồng bộ từ hệ thống quản lý danh tính, connector phải được giới hạn vào tenant mà nó được ủy quyền quản lý. Không cho phép một nguồn cấp phát của `T-A` tạo membership hoặc gán role trong `T-B` chỉ bằng cách gửi một tenant ID khác.

Đăng nhập SSO lần đầu cũng cần chính sách gia nhập rõ ràng. “Issuer được tin cậy để xác thực” và “mọi tài khoản từ issuer được gia nhập tenant này với quyền này” là hai quyết định khác nhau.

### 11.3. Đóng tenant không phải chỉ đổi nhãn trên giao diện

Khi tenant ngừng hoạt động, có thể cần xử lý session, membership, job, webhook, file xuất, credential workload và dữ liệu theo quy trình vận hành của ứng dụng.

Nếu xóa tenant rồi tạo tenant khác, không nên cấp lại định danh bảo mật cũ cho chủ thể mới. Một token, grant hoặc đường dẫn cũ còn tồn tại có thể bị hiểu là trỏ đến tenant mới.

Tên hiển thị hoặc slug có thể được thay đổi theo chính sách sản phẩm. Tuy nhiên, liên kết sử dụng slug cũ không được tự trở thành quyền trên một tenant khác vừa nhận cùng slug.

### 11.4. Phiên bản giúp phát hiện cũ, không tự thu hồi quyền

Một membership có `authorizationVersion = 12` tại thời điểm token được cấp. Sau khi hạ vai trò, dữ liệu server chuyển sang `13`.

API có thể đối chiếu version nếu hệ thống thiết kế cơ chế đó. Nhưng nếu API không đọc dữ liệu mới hoặc cache chưa cập nhật, số `12` trong token vẫn chỉ là một snapshot.

Cần tránh reset version theo cách làm dữ liệu cũ trông như hợp lệ trở lại. Nếu xóa và tạo lại membership, có thể cần định danh thế hệ membership hoặc cơ chế phiên bản không bị tái sử dụng ngoài ý muốn.

Với thu hồi đồng thời một thao tác đang chạy, cần định nghĩa điểm hiệu lực và cơ chế nhất quán. Một lần kiểm tra membership ở đầu request không tự bảo đảm mọi thay đổi quyền xảy ra sau đó đều chặn được giao dịch trước khi commit.

## 12. Truyền tenant context qua service và tác vụ nền

### 12.1. Mỗi hop cần giữ đúng ý nghĩa của ngữ cảnh

Một luồng có thể đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    A[Client chọn tenant] --> B[API xác minh credential và membership]
    B --> C[Resolved tenant context]
    C --> D[Service nghiệp vụ]
    D --> E[Kho dữ liệu trong tenant]
    D --> F[Job có tenant và chủ thể yêu cầu]
    F --> G[Worker xác minh phạm vi công việc]
    G --> H[Kết quả và audit gắn đúng tenant]
~~~

Tenant context truyền sang service khác phải được bảo vệ theo quan hệ tin cậy giữa các service. Bên nhận cần xác minh audience, danh tính bên gọi và phạm vi mà context được phép biểu diễn theo cơ chế đã chọn.

Đừng coi một chuỗi tenant trên HTTP header là một cơ chế ủy quyền hoàn chỉnh.

### 12.2. Workload identity và tenant scope là hai phần khác nhau

Một service account có thể được phép kết nối database dùng chung. Điều đó không có nghĩa mọi job do service account chạy được phép đọc mọi tenant.

Với job xuất hóa đơn thay người dùng, envelope do server tạo có thể chứa:

~~~json
{
  "jobId": "J-201",
  "tenantId": "T-A",
  "requestedBy": "subject-81",
  "action": "INVOICE_EXPORT",
  "selection": ["INV-7", "INV-9"]
}
~~~

Envelope cần được bảo vệ khỏi sửa trái phép. Worker xác minh nguồn job, tenant, phạm vi lựa chọn và quy tắc quyền tại thời điểm thực thi được nghiệp vụ yêu cầu.

Có hai loại công việc khác nhau:

| Loại job | Chủ thể và phạm vi cần xét |
| --- | --- |
| Thực hiện thay người dùng | Người yêu cầu, membership, tenant và hành động được ủy nhiệm |
| Tác vụ hệ thống | Workload được cấp quyền, tenant đích và phạm vi công việc hệ thống |

Không tự chuyển job thay người dùng thành job hệ thống khi membership của người yêu cầu không còn hợp lệ.

Nếu job chạy lâu, cần quy định quyền được xét lúc tạo, lúc bắt đầu, theo từng lô hay trước bước xuất kết quả. Không có một lựa chọn thời điểm duy nhất phù hợp mọi nghiệp vụ; lựa chọn phải được nêu rõ và thực thi được.

File kết quả tiếp tục thuộc một tenant và cần policy tải tương ứng. `jobId` hoặc đường dẫn file không tự là bằng chứng quyền.

### 12.3. Tác vụ nhiều tenant cần chia phạm vi có kiểm soát

Một tác vụ hệ thống xử lý nhiều tenant có thể chia thành các đơn vị công việc rõ ràng:

~~~text
Work item 1 -> tenant T-A
Work item 2 -> tenant T-B
Work item 3 -> tenant T-C
~~~

Mỗi đơn vị mang tenant riêng, có audit và trạng thái xử lý phù hợp. Không dùng tenant context còn sót lại từ vòng lặp trước.

Với báo cáo quản trị nhiều tenant, tập tenant được phép phải đến từ policy và dữ liệu có thẩm quyền. Không chấp nhận danh sách do client gửi như thể mọi tenant trong đó đã được ủy quyền.

## 13. Cache, luồng bất đồng bộ và rò rỉ tenant context

### 13.1. Khóa cache phải phản ánh phạm vi dữ liệu

Nếu `INV-7` tồn tại ở nhiều tenant, cache sau là thiếu:

~~~text
invoice:INV-7
~~~

Khóa dữ liệu cần phân biệt ít nhất ranh giới tenant theo mô hình định danh:

~~~text
invoice:T-A:INV-7
invoice:T-B:INV-7
~~~

Nếu nội dung trả về còn phụ thuộc người xem hoặc quyền trường, chỉ thêm tenant vẫn chưa đủ để tái sử dụng response an toàn. Có thể cache dữ liệu nền rồi xét quyền và chọn trường khi trả, hoặc thiết kế cache response theo các yếu tố thực sự ảnh hưởng kết quả.

Cache quyết định quyền cũng cần phân biệt chủ thể, tenant, hành động và dữ liệu phiên bản liên quan. Không cache `isAdmin(subject-81)` rồi dùng cho mọi tenant.

### 13.2. ThreadLocal không tự đi theo mọi tác vụ

Một biến `ThreadLocal` có thể giữ context trong luồng hiện tại, nhưng không tự giải quyết việc truyền context qua executor, reactive pipeline hoặc callback.

Hai lỗi có thể xảy ra:

- Tác vụ mới không nhận được tenant context.
- Luồng trong pool giữ context của yêu cầu trước và được tái sử dụng cho yêu cầu sau.

Nếu dùng cơ chế gắn context vào luồng, cần thiết kế rõ lúc thiết lập, lúc khôi phục và lúc dọn dẹp. Với tác vụ bất đồng bộ, truyền context bất biến một cách tường minh thường giúp thấy rõ ranh giới.

Không được dùng “không có context” làm tín hiệu bỏ lọc tenant.

Tương tự, nếu cơ sở dữ liệu dùng biến session để thực thi tenant scope, connection pooling đòi hỏi quy trình thiết lập và reset phù hợp. Không để connection của tenant A được dùng cho tenant B với trạng thái cũ.

### 13.3. Theo dõi không thay thế cô lập

Gắn tenant vào log hoặc trace giúp điều tra. Nó không làm truy vấn tự có điều kiện tenant.

Khi log ghi `T-A` nhưng truy vấn thật đọc `T-B`, hệ thống vừa lộ dữ liệu vừa để lại dấu vết sai. Nên lấy dữ liệu audit từ context đã giải quyết và kết quả thực thi, thay vì sao chép trực tiếp header chưa xác minh.

## 14. Truy cập chéo tenant có chủ đích

Một số sản phẩm có tư vấn viên, nhà cung cấp dịch vụ quản lý hoặc nhóm vận hành cần làm việc với nhiều khách hàng.

Nhu cầu đó không đồng nghĩa phải bỏ tenant attribute. Ngược lại, cần mô tả rõ quan hệ ủy quyền, chẳng hạn:

~~~text
actor = support-17
targetTenant = T-B
allowedActions = {DIAGNOSTIC_READ}
validUntil = thời điểm hết hiệu lực
approvalReference = phê duyệt phù hợp
~~~

Phạm vi có thể giới hạn thêm theo tài nguyên, thời gian hoặc mục đích.

Quyền `ADMIN` trong `T-A` không tự biến thành quyền hỗ trợ `T-B`. Một cờ `isInternal` hoặc tenant đặc biệt tên `system` cũng không nên ngầm bỏ mọi điều kiện dữ liệu.

Đối với chia sẻ tài nguyên ra ngoài tenant, cần policy riêng xác định tài nguyên vẫn thuộc tenant nào và chủ thể ngoài tenant được làm gì. Không tự gộp membership, chuyển tenant của tài nguyên hoặc coi phép so sánh tenant luôn có thể bỏ qua.

Các ví dụ truy vấn cùng tenant trong bài là chính sách của ứng dụng minh họa. Những use case chéo tenant cần hợp đồng khác được định nghĩa tường minh, không phải nhánh ngoại lệ do người gọi tùy ý kích hoạt.

## 15. Audit và thông tin công khai

Một sự kiện audit có thể ghi:

~~~text
actorSubjectId
callingWorkloadId
resolvedTenantId
resourceTenantId
action
decision
internalReason
membershipVersion
tenantVersion
requestId
occurredAt
~~~

`resolvedTenantId` cho biết ngữ cảnh đã được server chấp nhận. `resourceTenantId` giúp phát hiện tài nguyên không khớp khi thông tin đó được nạp và được phép ghi trong audit nội bộ.

Không cần log toàn bộ access token để chứng minh tenant. Token, nội dung tài liệu và danh sách membership có thể chứa dữ liệu nhạy cảm. Audit cũng cần được bảo vệ khỏi đọc hoặc sửa ngoài quyền.

API liệt kê tenant của người dùng chỉ nên công bố những tenant và thông tin mà người dùng được phép biết. Một endpoint kiểm tra slug hoặc tenant ID cũng cần hợp đồng phản hồi phù hợp; không mặc định ai biết mã tenant đều được xem danh sách thành viên.

Tenant ID thường được client biết để điều hướng. Biết ID không đồng nghĩa có quyền. Đồng thời, việc ID không phải mật khẩu không có nghĩa mọi metadata đi kèm đều được công khai.

## 16. Ma trận kiểm thử

Chuẩn bị dữ liệu trong môi trường được phép:

~~~text
T-A: ACTIVE
T-B: ACTIVE
T-C: SUSPENDED

Alice:
    T-A: ACTIVE, có INVOICE_READ, INVOICE_WRITE, MEMBER_INVITE
    T-B: ACTIVE, chỉ có INVOICE_READ

Bob:
    T-A: ACTIVE, chỉ có INVOICE_READ

INV-7 tồn tại ở cả T-A và T-B.
~~~

Các trường hợp cần kiểm tra theo chính sách của ví dụ:

| Tình huống | Kỳ vọng |
| --- | --- |
| Alice dùng token T-A, chọn T-A và đọc hóa đơn T-A | Cho phép nếu hành động đủ quyền |
| Alice dùng token T-A nhưng chọn T-B | Từ chối vì ràng buộc tenant không khớp |
| Alice dùng token T-B và đọc hóa đơn T-B | Cho phép theo quyền đọc của T-B |
| Alice dùng token T-B để mời thành viên T-B | Từ chối; quyền mời ở T-A không áp dụng |
| Bob sửa selector thành T-B | Từ chối; không có context hợp lệ cho T-B |
| Credential hợp lệ nhưng thiếu claim bắt buộc trong mô hình token-bound | Từ chối; không đổi mô hình ngầm |
| Token sai audience hoặc từ issuer không được tin cậy | Từ chối tại bước xác thực |
| Tenant T-C bị đình chỉ | Không tạo context API dữ liệu theo policy ví dụ |
| Membership chuyển sang REVOKED | Yêu cầu sau phải tuân thủ chính sách thu hồi đã định nghĩa |
| Client gửi tenant khác trong body tạo hóa đơn | Không được tạo dữ liệu ngoài tenant đã xác minh |
| Hai tenant cùng có INV-7 | Truy vấn và cache không trộn kết quả |
| Worker nhận job T-A sau khi vừa xử lý T-B | Không tái sử dụng context T-B |
| Request không có tenant context | Không được đọc tập dữ liệu toàn cục |
| Endpoint tìm kiếm hoặc đếm | Chỉ phản ánh phạm vi dữ liệu được phép |
| Alice mở hai tab ở hai tenant | Request vẫn giữ đúng ràng buộc tenant/tài nguyên/credential |
| Xóa rồi tạo lại tenant hoặc membership | Credential và quyền cũ không tự trở thành hợp lệ trở lại |

Cần kiểm thử cả đường thực thi, không chỉ hàm resolver:

1. Endpoint lấy tenant từ đúng nguồn đã công bố.
2. Repository nhận tenant từ context đã giải quyết.
3. Quyền role không bị join hoặc cache ngoài phạm vi tenant.
4. File xuất và endpoint tải kết quả có cùng ranh giới phù hợp.
5. Lỗi kho membership không làm hệ thống mở quyền.
6. Request bị từ chối không để lại dữ liệu hoặc side effect trái phép.
7. Các bảo đảm về thu hồi và đồng thời đúng với mức nhất quán đã cam kết.

Đây là ma trận để người học xây dựng kiểm thử cho ứng dụng của mình, không phải báo cáo rằng các đoạn mã trong tài liệu đã được chạy trên một hệ thống thật.

## 17. Ngộ nhận và bài tập vận dụng

| Ngộ nhận | Cách hiểu chính xác hơn |
| --- | --- |
| Có tenantId trong request là đủ | Selector cần được xác minh với credential và quan hệ quyền |
| Tenant của IdP luôn là tenant ứng dụng | Cần ánh xạ theo hợp đồng giữa hai hệ thống |
| Email cùng miền đồng nghĩa cùng tenant | Gia nhập tenant phải theo chính sách có thẩm quyền |
| Một user chỉ có một role | Role thường gắn với membership và phạm vi cụ thể |
| ADMIN ở tenant A là ADMIN toàn nền tảng | Quyền quản trị tenant và quyền vận hành nền tảng phải phân biệt |
| Database riêng tự giải quyết mọi cô lập | Việc chọn database và cấp quyền vẫn phải đúng tenant |
| Thêm tenant vào cache key là luôn đủ | Response còn có thể phụ thuộc chủ thể và quyền trường |
| Token có chữ ký thì membership luôn mới | Chữ ký bảo vệ tính toàn vẹn, không tự cập nhật thay đổi quyền |
| Không có context thì dùng tenant mặc định | Chỉ dùng mặc định nếu hợp đồng cho phép và đã xác minh |
| Workload đọc được database nên được đọc mọi tenant | Còn phải xét phạm vi công việc được ủy quyền |

Bài tập: thiết kế một nền tảng dự án có người dùng thuộc nhiều workspace. Một người có thể quản trị workspace A, chỉ xem workspace B và là cộng tác viên ngoài tổ chức ở workspace C.

Hãy xác định:

- Định danh tenant nào là bất biến và ai quản lý nó?
- Cặp danh tính bên ngoài được ánh xạ sang subject nội bộ như thế nào?
- Vai trò nằm trên user hay trên membership?
- API dùng token ràng buộc tenant hay chọn tenant bằng membership phía server?
- Nếu path, token và body có tenant khác nhau, server xử lý ra sao?
- Project, file, cache, job và audit giữ tenant context thế nào?
- Khi thu hồi membership hoặc đóng workspace, quyền cũ hết hiệu lực ở thời điểm nào?
- Truy cập hỗ trợ chéo tenant có phạm vi và phê duyệt riêng thế nào?

Một thiết kế đủ rõ phải mô tả được đường đi từ **tenant được yêu cầu**, qua **nguồn xác nhận có thẩm quyền**, đến **context đã xác minh** và **dữ liệu thực sự bị truy cập**. Mỗi chỗ sử dụng thuộc tính tenant cần giữ nguyên ý nghĩa và ranh giới đó.
