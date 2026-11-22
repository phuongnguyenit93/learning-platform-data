# ABAC: phân quyền theo thuộc tính người dùng, tài nguyên và ngữ cảnh

> **Trọng tâm:** cách ra quyết định phân quyền từ **thuộc tính của người dùng (subject)**, **tài nguyên (resource/object)**, **hành động (action)** và **ngữ cảnh (environment)**; cách hiện thực hóa an toàn trong Spring Security. Ví dụ chính dùng Java 17, chạy độc lập để quan sát quyết định; ví dụ tích hợp Spring là các đoạn cấu hình minh họa có ghi rõ phụ thuộc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ABAC (Attribute-Based Access Control) và phân biệt xác thực (**authentication**) với phân quyền (**authorization**).
2. Viết chính sách dựa trên thuộc tính người dùng, tài nguyên, hành động và môi trường; hiểu **Permit**, **Deny**, điều kiện thiếu dữ liệu và nguyên tắc **deny by default**.
3. So sánh ABAC với RBAC, ACL và ReBAC; biết khi nào kết hợp thay vì thay thế hoàn toàn RBAC.
4. Thiết kế luồng lấy thuộc tính đáng tin cậy, đánh giá chính sách và chặn truy cập ở backend bằng Spring Security.
5. Kiểm thử các tình huống tenant chéo, thiếu MFA, thiết bị không tuân thủ, tài nguyên của người khác, thời gian truy cập và thay đổi quyền.

## 2. ABAC là gì?

ABAC là mô hình kiểm soát truy cập: hệ thống quyết định một **chủ thể** được thực hiện **hành động** trên **đối tượng/tài nguyên** trong **điều kiện ngữ cảnh** cụ thể hay không, bằng cách đánh giá các thuộc tính với chính sách. Đây là cách hiểu tương ứng với NIST SP 800-162.

Thay vì chỉ hỏi *“người này có vai trò EDITOR không?”*, ABAC có thể hỏi:

> “Người dùng còn hiệu lực, thuộc cùng tenant với tài liệu, là chủ sở hữu hoặc thuộc phòng ban được phép, đã xác thực MFA, đang dùng thiết bị được quản lý; và nếu sửa tài liệu thì có đang trong khung giờ làm việc không?”

Quyết định phụ thuộc **tập hợp** điều kiện; cùng một người có thể được đọc tài liệu A nhưng không được đọc B, hoặc được đọc hôm nay nhưng không được chỉnh sửa ngoài khung giờ quy định.

### Bốn loại thông tin khi đánh giá chính sách

| Thành phần | Câu hỏi | Ví dụ thuộc tính |
| --- | --- | --- |
| **Subject** (người dùng/chủ thể) | Ai đang yêu cầu? | `userId`, `tenantId`, `department`, `roles`, `accountStatus`, trạng thái xác thực MFA, nhóm dự án |
| **Resource/Object** | Đang truy cập cái gì? | `documentId`, `ownerId`, `tenantId`, `classification`, `department`, trạng thái lưu trữ/khóa |
| **Action/Operation** | Muốn làm gì? | `READ`, `EDIT`, `APPROVE`, `EXPORT`, `DELETE` |
| **Environment/Context** | Yêu cầu diễn ra trong điều kiện nào? | Thời gian server, vùng mạng tin cậy, trạng thái thiết bị, mức rủi ro, phiên đăng nhập |

**Action cũng là đầu vào của chính sách:** đọc và sửa cùng một tài nguyên thường có yêu cầu khác nhau. Thuộc tính không nhất thiết phải là chuỗi; có thể là tập vai trò, giá trị enum, nhãn bảo mật, thời điểm, số lượng hoặc quan hệ đã kiểm chứng. Hệ thống cần xác định kiểu dữ liệu, nguồn cấp và độ tin cậy của từng thuộc tính.

Một dạng biểu diễn đơn giản:

```text
Decision = EvaluatePolicy(subjectAttributes,
                          resourceAttributes,
                          action,
                          environmentAttributes)
         ∈ {PERMIT, DENY}
```

Trong các kiến trúc ABAC/Policy Engine lớn hơn, kết quả nội bộ có thể phân biệt thêm `NotApplicable` hay `Indeterminate`. Tuy nhiên, tại điểm thực thi bảo vệ tài nguyên, **không có quyết định cho phép rõ ràng thì phải từ chối**. Không được biến lỗi đọc thuộc tính thành cho phép truy cập.

### ABAC nằm ở bước nào?

- **Authentication**: chứng minh “ai đang gọi” (session, password, bearer token, OAuth2/OIDC...); tạo `Authentication`/principal đáng tin cậy.
- **Authorization**: xác định principal ấy được thực hiện thao tác nào đối với tài nguyên cụ thể trong ngữ cảnh hiện tại.
- **Enforcement**: backend thực sự chặn/cho phép thao tác, kể cả khi giao diện không hiển thị nút tương ứng.

Ví dụ: người dùng đã đăng nhập hợp lệ nhưng tài liệu thuộc tenant khác thì ABAC vẫn phải trả `DENY`. `isAuthenticated()` một mình không thể bảo vệ quyền sở hữu, tenant hay phân loại dữ liệu.

## 3. So sánh với RBAC, ACL và ReBAC

| Mô hình | Căn cứ chính | Thích hợp khi | Hạn chế cần lưu ý |
| --- | --- | --- | --- |
| **RBAC** (Role-Based) | Quyền gán cho vai trò như `ADMIN`, `EDITOR` | Chức năng quản trị, nhóm quyền ổn định | Role không tự mô tả tài liệu nào thuộc ai/tenant nào |
| **ACL** (Access Control List) | Danh sách quyền gắn từng tài nguyên với user/group | Chia sẻ từng tệp, cấp quyền đích danh | Danh sách có thể phình to, tốn công đồng bộ |
| **ReBAC** (Relationship-Based) | Quan hệ trong đồ thị: “thành viên”, “người quản lý”, “được chia sẻ bởi” | Hệ thống cộng tác với quan hệ lồng nhau | Việc giải quan hệ/đồ thị có thể phức tạp |
| **ABAC** | Kết hợp nhiều thuộc tính và ngữ cảnh trong policy | Nhiều tenant, phân loại dữ liệu, yêu cầu tuân thủ/ngữ cảnh động | Policy khó kiểm soát nếu nguồn thuộc tính, ưu tiên rule và test không rõ ràng |

Các mô hình **có thể kết hợp**: role `REPORT_READER` là một thuộc tính của subject trong ABAC; tài liệu cũng có thể có ACL người được chia sẻ; quan hệ “là thành viên nhóm sở hữu” có thể do ReBAC giải quyết trước khi đánh giá policy.

**Phản ví dụ cho RBAC thuần:** `hasRole('MANAGER')` cho phép manager của tenant A đọc báo cáo nhạy cảm của tenant B nếu không có kiểm tra tenant và resource. Phải kết hợp kiểm tra phạm vi đối tượng. **Phản ví dụ cho ABAC thiết kế kém:** chỉ so `department == finance` rồi cho đọc mọi báo cáo finance của mọi tenant cũng không an toàn.

## 4. Xác định chính sách trước khi viết code

Giả sử một nền tảng quản lý tài liệu có nhiều tenant. Tài liệu có `ownerId`, `tenantId`, `department`, `sensitivity` (INTERNAL/CONFIDENTIAL) và `archived`. Chính sách phiên bản đầu:

1. Người dùng phải được xác thực, tài khoản phải hoạt động; **tenant người dùng và tenant tài liệu phải trùng nhau**.
2. Tài liệu đã lưu trữ không cho đọc/sửa qua API nghiệp vụ này.
3. Subject phải là **owner** hoặc thuộc cùng `department` với tài liệu để được xem xét tiếp.
4. Tài liệu `CONFIDENTIAL` còn yêu cầu **MFA đã được xác minh**, **thiết bị quản lý đạt chuẩn**, và **vùng mạng CORPORATE**.
5. Hành động `READ` được cho phép sau các điều kiện trên.
6. Hành động `EDIT` chỉ cho **owner**, và chỉ trong khoảng **08:00–17:59 theo Asia/Ho_Chi_Minh**.
7. Thuộc tính bắt buộc bị thiếu, nguồn không đáng tin cậy, action không biết hoặc lỗi đánh giá → **DENY**, đồng thời ghi audit nội bộ theo chính sách.

Có thể biểu diễn logic ở dạng ngôn ngữ gần nghiệp vụ:

```text
PERMIT(subject, document, action, context) IF
  subject.active
  AND subject.tenantId == document.tenantId
  AND NOT document.archived
  AND (subject.userId == document.ownerId
       OR document.department IN subject.departments)
  AND (
       document.sensitivity != CONFIDENTIAL
       OR (
           subject.mfaVerified
           AND context.managedDevice
           AND context.networkZone == CORPORATE
       )
  )
  AND (
       action == READ
       OR (
           action == EDIT
           AND subject.userId == document.ownerId
           AND 08:00 <= context.localTime < 18:00
       )
  )
DENY otherwise.
```

Ở đây “owner hoặc cùng department” chỉ đáp ứng **một** điều kiện. Người dùng vẫn bị chặn nếu tenant sai hoặc yêu cầu MFA chưa đáp ứng. Chính sách không định nghĩa `DELETE` nên thao tác đó mặc định bị từ chối, chứ không được tự suy ra từ `EDIT`.

### Các tình huống ra quyết định

| Chủ thể | Tài nguyên/hành động/ngữ cảnh | Quyết định | Lý do |
| --- | --- | --- | --- |
| Alice, tenant A, owner, MFA có | Tài liệu confidential tenant A; đọc từ máy quản lý/mạng công ty | PERMIT | Đủ mọi điều kiện |
| Alice, tenant A, owner | Sửa tài liệu trên vào 10:00 giờ Việt Nam | PERMIT | Là owner và trong khung giờ |
| Bob, tenant B, cùng department | Đọc tài liệu confidential tenant A | DENY | Tenant khác, bất kể department |
| Carol, tenant A, cùng department, chưa MFA | Đọc tài liệu confidential tenant A | DENY | Thiếu MFA |
| Alice, owner, MFA có | Đọc confidential từ thiết bị không đạt chuẩn | DENY | Điều kiện thiết bị không đạt |
| Alice, owner, MFA có | Sửa lúc 22:00 giờ Việt Nam | DENY | Ngoài giờ |
| Alice | Xóa tài liệu khi policy chỉ có READ/EDIT | DENY | Action không được cho phép |

Đó là **chính sách minh họa**, không phải mặc định của Spring Security/NIST. Mỗi sản phẩm phải xác nhận nguyên tắc nghiệp vụ với chủ sở hữu dữ liệu; tránh suy ra quyền dựa trên cảm tính.

## 5. Luồng thành phần ABAC: PEP, PDP, PIP, PAP

```text
Client / API caller
       |
       v
Authentication -> principal/subject identity đã xác minh
       |
       v
PEP: điểm thực thi (controller/service/gateway)
       |  yêu cầu: subject, resource ID, action, context
       v
PIP: nạp attributes đáng tin
       |-- user/tenant/group từ identity store
       |-- owner/tenant/classification từ database tài nguyên
       |-- thời gian server, trạng thái device/session từ nguồn tin cậy
       v
PDP: đánh giá policy -> PERMIT / DENY
       |
       v
PEP: thực thi -> cho chạy nghiệp vụ hoặc từ chối
       |
       +--> audit: rule/policy version, decision, thời điểm, correlation ID

PAP: nơi soạn/phê duyệt/kiểm soát phiên bản policy
        -> cung cấp policy được áp dụng cho PDP
```

- **PEP** (Policy Enforcement Point): nơi **bắt buộc** tuân thủ quyết định; chỉ ẩn nút ở frontend là chưa đủ.
- **PDP** (Policy Decision Point): thực thi điều kiện policy; có thể là mã Java hoặc policy engine riêng.
- **PIP** (Policy Information Point): lấy thuộc tính; không mặc nhiên tin giá trị trong request.
- **PAP** (Policy Administration Point): quản lý policy, kiểm duyệt, triển khai, rollback và audit thay đổi.

Đây là **vai trò kiến trúc**, không nhất thiết là bốn interface có tên tương ứng trong Spring Security. Với dự án nhỏ, PEP và PDP có thể nằm cùng tiến trình. Khi tách dịch vụ, phải xử lý timeout, lỗi mạng, consistency và cache an toàn: **không được tự động Permit khi PDP/PIP không truy cập được**.

### Nguồn thuộc tính nào đáng tin?

- `userId`/`tenantId` của subject: lấy từ principal/claims **đã được xác minh** hoặc identity store và ánh xạ có kiểm soát; claim JWT chỉ đáng tin sau khi kiểm tra chữ ký, issuer, audience, expiry và policy áp dụng.
- `resource.tenantId`/`ownerId`: tải từ kho dữ liệu thực theo resource ID; **không lấy** owner/tenant do client gửi rồi coi như sự thật.
- Thời gian: dùng đồng hồ server với `Clock`/`Instant`; nếu chính sách giờ địa phương, chuyển bằng `ZoneId` rõ ràng. Không tin header “current-time”.
- “MFA verified”: trạng thái đáng tin của phiên/identity provider và đủ mới theo yêu cầu; việc frontend báo `mfa=true` không tạo ra đảm bảo.
- Mạng/thiết bị: nguồn quản lý hoặc gateway được tin cậy, có bảo đảm provenance; `X-Forwarded-For` hay IP do client trực tiếp cung cấp không tự chứng minh được vị trí/vùng mạng.

## 6. Ví dụ Java 17 hoàn chỉnh, chạy độc lập

Ví dụ sau chỉ dùng Java SE 17, không cần Spring Boot. Đây là **policy engine nhỏ để học**, với cấu trúc dữ liệu bất biến ở các giá trị mẫu. Chính sách đúng như mục 4. Lưu tệp **`AbacDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.util.Set;

public class AbacDemo {
    enum Action { READ, EDIT }
    enum Sensitivity { INTERNAL, CONFIDENTIAL }

    record Subject(
            String userId,
            String tenantId,
            Set<String> departments,
            boolean active,
            boolean mfaVerified) {}

    record Document(
            String documentId,
            String tenantId,
            String ownerId,
            String department,
            Sensitivity sensitivity,
            boolean archived) {}

    record RequestContext(
            Instant requestTime,
            String networkZone,
            boolean managedDevice) {}

    record Decision(boolean permitted, String reason) {
        static Decision permit() {
            return new Decision(true, "allowed");
        }
        static Decision deny(String reason) {
            return new Decision(false, reason);
        }
        String display() {
            return permitted ? "PERMIT" : "DENY (" + reason + ")";
        }
    }

    static Decision evaluate(
            Subject subject,
            Document document,
            Action action,
            RequestContext context) {

        // Thiếu thông tin quan trọng: fail closed.
        if (subject == null || document == null
                || action == null || context == null
                || subject.userId() == null
                || subject.tenantId() == null
                || subject.departments() == null
                || document.tenantId() == null
                || document.ownerId() == null
                || document.department() == null
                || document.sensitivity() == null
                || context.requestTime() == null
                || context.networkZone() == null) {
            return Decision.deny("missing attributes");
        }

        if (!subject.active()) {
            return Decision.deny("inactive account");
        }
        if (!subject.tenantId().equals(document.tenantId())) {
            return Decision.deny("tenant mismatch");
        }
        if (document.archived()) {
            return Decision.deny("archived document");
        }

        boolean owner = subject.userId().equals(document.ownerId());
        boolean sameDepartment =
                subject.departments().contains(document.department());

        if (!owner && !sameDepartment) {
            return Decision.deny("no matching relation");
        }

        if (document.sensitivity() == Sensitivity.CONFIDENTIAL) {
            if (!subject.mfaVerified()) {
                return Decision.deny("MFA required");
            }
            if (!context.managedDevice()) {
                return Decision.deny("managed device required");
            }
            if (!"CORPORATE".equals(context.networkZone())) {
                return Decision.deny("corporate network required");
            }
        }

        if (action == Action.EDIT) {
            if (!owner) {
                return Decision.deny("owner required for edit");
            }
            int hour = context.requestTime()
                    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                    .getHour();
            if (hour < 8 || hour >= 18) {
                return Decision.deny("outside business hours");
            }
        }

        return Decision.permit();
    }

    static void print(String label, Decision decision) {
        System.out.println(label + ": " + decision.display());
    }

    public static void main(String[] args) {
        Subject alice = new Subject(
                "alice", "tenant-a", Set.of("finance"), true, true);
        Subject bob = new Subject(
                "bob", "tenant-b", Set.of("finance"), true, true);
        Subject carol = new Subject(
                "carol", "tenant-a", Set.of("finance"), true, false);

        Document report = new Document(
                "report-7", "tenant-a", "alice", "finance",
                Sensitivity.CONFIDENTIAL, false);

        // 03:00 UTC = 10:00 tại Việt Nam ngày 04/11/2026.
        RequestContext office = new RequestContext(
                Instant.parse("2026-11-04T03:00:00Z"),
                "CORPORATE", true);
        RequestContext unmanaged = new RequestContext(
                office.requestTime(), "CORPORATE", false);
        // 15:00 UTC = 22:00 tại Việt Nam cùng ngày.
        RequestContext night = new RequestContext(
                Instant.parse("2026-11-04T15:00:00Z"),
                "CORPORATE", true);

        print("alice read", evaluate(alice, report, Action.READ, office));
        print("alice edit", evaluate(alice, report, Action.EDIT, office));
        print("bob read", evaluate(bob, report, Action.READ, office));
        print("carol read", evaluate(carol, report, Action.READ, office));
        print("alice unmanaged", evaluate(
                alice, report, Action.READ, unmanaged));
        print("alice edit at night", evaluate(
                alice, report, Action.EDIT, night));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 AbacDemo.java
java AbacDemo
```

**Stdout dự kiến chính xác:**

```text
alice read: PERMIT
alice edit: PERMIT
bob read: DENY (tenant mismatch)
carol read: DENY (MFA required)
alice unmanaged: DENY (managed device required)
alice edit at night: DENY (outside business hours)
```

### Giải thích các nhánh

- **Alice/READ:** cùng tenant, là owner, tài liệu chưa archived, có MFA, thiết bị quản lý và network zone được chấp nhận → Permit.
- **Alice/EDIT lúc 10:00:** ngoài các điều kiện chung, là owner và thời gian server quy đổi về Việt Nam trong `[08:00,18:00)` → Permit.
- **Bob/READ:** dù cùng department, `tenant-b != tenant-a` → Deny. Tenant boundary phải được kiểm tra trước khi cho phép trên quan hệ/role.
- **Carol/READ:** cùng tenant và cùng department nhưng chưa MFA với tài liệu confidential → Deny.
- **Alice/READ từ thiết bị không đạt chuẩn:** dù là owner, thiếu điều kiện ngữ cảnh → Deny.
- **Alice/EDIT lúc 22:00:** credential và owner đúng nhưng ngoài khoảng thời gian → Deny.

Điểm đáng chú ý: Java `record` giúp biểu diễn dữ liệu nhưng **không tự chứng minh thuộc tính có thật**. Ví dụ dựng subject/context từ giá trị cố định để dễ quan sát; khi tích hợp sản phẩm, các thuộc tính phải đến từ nguồn tin cậy. Nếu collection truyền vào record có thể thay đổi, cân nhắc `Set.copyOf(...)` ở constructor để tránh thay đổi thuộc tính sau khi tạo snapshot chính sách.

**Giới hạn có chủ đích:** `Action` chỉ gồm `READ`/`EDIT`; nếu nghiệp vụ thêm `EXPORT`/`DELETE`, phải định nghĩa rule riêng và kiểm thử. Đừng tự cho rằng quyền EDIT kéo theo mọi quyền khác.

## 7. Đưa ABAC vào Spring Security

Spring Security cung cấp cơ chế xác thực, principal, interceptors và `AuthorizationManager` để thực thi quyết định. **Spring Security không tự biết `tenantId`, `ownerId`, `classification` hay policy nghiệp vụ của bạn**. Hệ thống phải cung cấp dữ liệu và logic tương ứng.

### 7.1. Thực thi nhiều lớp

1. Ở tầng HTTP: dùng `authorizeHttpRequests` cho Servlet hoặc `authorizeExchange` cho WebFlux để buộc request vào đường đi được xác thực.
2. Ở tầng **service/method**: đánh giá thuộc tính của **resource thật** và chủ thể đã xác thực, vì policy phụ thuộc đối tượng cụ thể.
3. Ở tầng truy vấn: áp dụng tenant scoping và row-level constraints phù hợp để không lộ dữ liệu hoặc vô tình tải đối tượng khác tenant.
4. Ở tầng nghiệp vụ cập nhật/xóa: kiểm tra quyền đúng hành động và bảo đảm thuộc tính xét quyền không bị thay đổi sau kiểm tra một cách nguy hiểm.

Không dùng kiểm tra frontend, hidden button hoặc `@PreAuthorize("isAuthenticated()")` làm **cơ chế duy nhất** bảo vệ quyền trên từng tài liệu.

### 7.2. Servlet: @EnableMethodSecurity và @PreAuthorize

Với Spring Security 6.x/7.x ở ứng dụng Servlet, bật method security và gọi bean policy từ SpEL:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class DocumentService {
    private final DocumentRepository documents;

    DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public DocumentDetails read(String documentId) {
        return documents.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);
    }
}
```

Đây là **mảnh mã tích hợp minh họa**, không phải tệp biên dịch độc lập. Cần cung cấp `DocumentRepository`, `DocumentDetails`, `DocumentNotFoundException`, bean `documentPolicy`, import Spring tương ứng và cấu hình ứng dụng. Method security yêu cầu lời gọi đi **qua Spring-managed proxy**; một lời gọi nội bộ `this.read(...)` thường không đi qua advice của proxy. Hãy đặt boundary bảo vệ ở method thực sự được gọi qua bean hoặc dùng một cơ chế enforcement phù hợp khác.

Hợp đồng mong muốn của bean policy:

```java
@Component("documentPolicy")
class DocumentPolicy {
    // Repository / identity adapter / trusted context được inject tại đây.

    public boolean canRead(Authentication authentication, String documentId) {
        // 1. Kiểm tra principal hợp lệ và đã xác thực.
        // 2. Tải tài liệu thật theo documentId; lấy tenant/owner/classification
        //    từ database, không lấy từ tham số gửi lên.
        // 3. Lấy subject attributes và context từ nguồn được xác minh.
        // 4. Chạy policy READ; trả true khi PERMIT, còn lại false.
        // 5. Ghi audit trong tầng phù hợp, tránh log token/credential.
        throw new UnsupportedOperationException("Integration contract illustration");
    }
}
```

Đoạn `DocumentPolicy` này **chỉ minh họa hợp đồng triển khai** và không được dùng nguyên trạng: production phải thay bằng logic policy thật, tương tự hàm `evaluate` ở ví dụ Java độc lập. `throw` biểu thị thiếu implementation, không phải một phản hồi hợp lệ khi chạy ứng dụng. Một cách tổ chức tốt là tách `DocumentAttributeProvider`, `SubjectMapper`, `ContextProvider` và `AbacPolicy` để kiểm thử riêng; hãy đặt **deny** an toàn ở đường xử lý lỗi trước khi triển khai thực tế.

**Lưu ý về tham số SpEL:** tên `#documentId` phải được phát hiện đúng (ví dụ compile với `-parameters` hoặc dùng annotation chỉ rõ tên tham số). Nếu không, có thể dùng tham chiếu chỉ số `#p0` theo cấu hình hỗ trợ; hãy kiểm thử method security thực tế. Các tham số đầu vào như `documentId` chỉ dùng **định vị tài nguyên**. Không lấy `ownerId` hoặc `tenantId` từ client làm chứng cứ để cấp quyền.

### 7.3. Nơi đặt chính sách khi có nhiều API

Một policy độc lập có thể được gọi từ:

- `@PreAuthorize` trên service method cho thao tác đơn lẻ.
- `AuthorizationManager` tùy biến ở một boundary cần áp dụng thống nhất.
- Lớp nghiệp vụ dùng cả khi request đến từ REST, batch job, messaging hoặc workflow nền.

Ví dụ, endpoint `GET /documents/{id}` và `POST /documents/{id}/approve` có **action khác nhau**, nên không được dùng chung điều kiện `canRead` cho cả hai. Kiểm tra đường dẫn HTTP trước không thể thay việc đọc owner/classification của tài liệu thật.

`@PostAuthorize` có thể kiểm tra `returnObject` sau khi service trả về; phù hợp một số use case read-only, nhưng không nên dùng như cơ chế chính để bảo vệ thao tác **đã gây tác dụng phụ** (ghi/xóa/chuyển tiền) trước khi quyết định.

### 7.4. WebFlux/reactive khác Servlet

Với WebFlux, dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và khi cần method security thì `@EnableReactiveMethodSecurity`. Các method được bảo vệ thường trả `Mono<T>` hoặc `Flux<T>` để kết hợp với Reactor Context. PIP lấy dữ liệu từ repository reactive và policy evaluation phải đi theo pipeline; **không `block()` trong event loop**.

Hình dạng minh họa (các bean/tên miền nghiệp vụ cần do ứng dụng cung cấp):

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}

@Service
class ReactiveDocumentService {
    private final ReactiveDocumentRepository documents;

    ReactiveDocumentService(ReactiveDocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@reactiveDocumentPolicy.canRead(authentication, #documentId)")
    public Mono<DocumentDetails> read(String documentId) {
        return documents.findById(documentId);
    }
}
```

Bean `reactiveDocumentPolicy.canRead` có thể trả `Mono<Boolean>` khi cấu hình phiên bản/method security hỗ trợ, đồng thời phải lấy document attributes bằng publisher reactive và trả **true/false rõ ràng**. Với yêu cầu bảo vệ, đừng để `Mono.empty()` của policy bị hiểu tùy tiện thành Permit. Kiểm tra hợp đồng chính xác theo phiên bản Spring Security đang sử dụng. Cách làm chắc chắn hơn là đưa logic policy vào service với composition reactive, rồi dùng authorization ở boundary phù hợp mà không bỏ qua dữ liệu.

**Không trộn API Servlet và WebFlux:** `HttpSecurity`/`@EnableMethodSecurity` thuộc hướng Servlet, trong khi `ServerHttpSecurity`/`@EnableReactiveMethodSecurity` là hướng reactive.

## 8. Dữ liệu, chính sách và an toàn vận hành

### 8.1. Thiếu thuộc tính, lỗi nguồn dữ liệu và policy xung đột

Cần quy định rõ nếu `ownerId` null, tenant không tìm được, kho thuộc tính timeout hoặc data classification không xác định. Với dữ liệu nhạy cảm, lựa chọn hợp lý là **Deny** kèm ghi nhận nguyên nhân nội bộ; lỗi hạ tầng có thể trả phản hồi kỹ thuật phù hợp (thường là 5xx) nhưng **không được cấp quyền vì không đánh giá được**.

Nếu có nhiều rule (ví dụ rule “phòng finance được đọc” và “tài liệu bị legal hold thì cấm đọc”), phải chỉ rõ **ưu tiên** hoặc cơ chế kết hợp như `deny-overrides`. Các rule chặn cứng (tenant mismatch, account disabled, explicit deny) không được vô tình bị một rule rộng như `hasRole('ADMIN')` bỏ qua. Mọi ngoại lệ kiểu “super admin cross-tenant” cần policy rõ ràng, audit và test riêng.

### 8.2. Kiểm soát tenant là ranh giới dữ liệu

Trong SaaS đa tenant, kiểm tra tenant nên thực hiện ở nhiều lớp bổ trợ:

```text
Authenticated tenant
      |
      +--> Query: WHERE id = :id AND tenant_id = :tenant
      |
      +--> Policy: document.tenantId == subject.tenantId
      |
      +--> Mutation: UPDATE ... WHERE id = :id AND tenant_id = :tenant
      |
      +--> Audit: documentId, tenantId, action, decision
```

Đây là bản phác thảo logic; tên cột/bảng và giao dịch tùy hệ thống. Việc lọc ngay tại query giảm nguy cơ lộ thông tin tài nguyên chéo tenant. **Không** lấy `tenant_id` trong SQL từ body/header chưa kiểm chứng. Trạng thái “không tồn tại” và “không được phép” có thể được chuẩn hóa phản hồi để tránh lộ sự tồn tại của tài nguyên, theo threat model của ứng dụng.

### 8.3. Time-of-check/time-of-use (TOCTOU)

Nếu policy đọc `ownerId` ở thời điểm T1 rồi cập nhật tài liệu ở T2, owner/tenant/classification có thể đã đổi. Với thao tác nhạy cảm, cân nhắc kiểm tra và mutate trong cùng transaction/điều kiện SQL, versioning/optimistic locking hoặc update có điều kiện. Đọc và quyết định trên snapshot rõ ràng; không tin một lần kiểm tra mãi mãi.

### 8.4. Cache thuộc tính và quyền thay đổi

Cache `roles`, `groups`, `tenant memberships`, `resource classification` hay `PERMIT` giúp giảm chi phí nhưng tạo rủi ro quyền cũ:

- Quyền đã bị thu hồi nhưng cache vẫn cho phép.
- Resource vừa chuyển tenant/owner.
- MFA hết hiệu lực hoặc yêu cầu mức bảo đảm cao hơn.
- Policy phiên bản mới chưa đồng bộ giữa các instance.

Cần xác định TTL/invalidation/version, phạm vi cache theo subject, resource, action và context. **Không** cache mỗi `userId` rồi tái dùng kết quả cho mọi tài liệu, mọi hành động. Với quyền nhạy cảm, có thể cần đánh giá trực tiếp và cơ chế thu hồi sớm.

### 8.5. Logging và khả năng giải thích

Audit hữu ích gồm: `correlationId`, `subjectId` giả danh/định danh theo policy bảo mật, `resourceId`, `action`, `policyVersion`, `decision`, `reasonCode`, thời điểm server và dấu vết nguồn thuộc tính phù hợp. Tránh ghi raw password, bearer token, session cookie, PII không cần thiết hoặc giá trị nhạy cảm nguyên bản. Bản audit giúp giải thích vì sao cùng một người ở hai ngữ cảnh có kết quả khác nhau.

Nếu policy có “nghĩa vụ” (obligation) như masking field hay yêu cầu log sự kiện, PEP phải **thực hiện nghĩa vụ đó**, không chỉ nhận một boolean và trả dữ liệu thô.

## 9. Kiểm thử ABAC có hệ thống

Không dừng ở một test “admin được phép”. Ma trận sau nên được diễn đạt thành unit tests của policy và integration tests của API:

| Case | Thay đổi so với trường hợp hợp lệ | Kỳ vọng |
| --- | --- | --- |
| Người dùng được phép đọc | Tất cả thuộc tính đúng | PERMIT |
| Subject khác tenant | Giữ owner/department giả giống nhau nhưng đổi tenant | DENY |
| User bị khóa | `active=false` | DENY |
| Document archived | `archived=true` | DENY |
| Không phải owner và khác department | Mọi điều kiện khác đúng | DENY |
| Thiếu MFA khi đọc confidential | `mfaVerified=false` | DENY |
| Thiết bị không quản lý | `managedDevice=false` | DENY |
| Không đúng network zone | `networkZone=PUBLIC` | DENY |
| Editor không phải owner | Subject cùng department, action EDIT | DENY |
| Owner sửa ngoài giờ | Giờ server là 22:00 ở Việt Nam | DENY |
| Thiếu tenant/classification hoặc lỗi PIP | Thuộc tính chưa xác định | DENY; xử lý lỗi nội bộ |
| Role cao nhưng tenant khác | Có `ADMIN`, sai tenant | DENY trừ ngoại lệ được quy định và kiểm thử |
| Đổi tenant/owner giữa check và write | Race condition khi cập nhật | Không được mutate vượt phạm vi |
| Quyền đã thu hồi | Cache cũ còn `PERMIT` | Thu hồi có hiệu lực theo yêu cầu hệ thống |
| Thao tác chưa được định nghĩa | `DELETE`/`EXPORT` khi policy không cho phép | DENY |

**Biên thời gian cần test:** 07:59, 08:00, 17:59, 18:00 trong đúng `ZoneId`; không lấy timezone của browser. Với nhiều quốc gia, quy tắc business time phải lấy từ cấu hình tenant/chính sách và xử lý DST khi có.

**Property/invariant nên giữ:** “Mọi quyết định Permit đều có tenant match và account active”; “Không một resource confidential nào được đọc khi MFA chưa đáp ứng”; “EDIT chỉ Permit nếu là owner”. Các invariant này tìm lỗi hiệu quả hơn kiểm tra vài câu lệnh if riêng lẻ.

Kiểm thử hai tầng:

1. **Unit test policy** từ dữ liệu thuần, không khởi động HTTP; bao phủ bảng quyết định và ưu tiên rule.
2. **Integration test Spring Security** với principal thật và resource repository: request không đăng nhập, tài liệu cross-tenant, resource không tồn tại, quyền bị thu hồi, action khác nhau; kiểm tra cả response và việc service **không thực thi thao tác bị cấm**. Test proxy method security bằng lời gọi qua Spring bean, không gọi trực tiếp method trên object `new`.

**401 và 403:** thông thường request chưa xác thực dẫn đến authentication entry point (thường 401), còn đã xác thực nhưng thiếu quyền dẫn đến access denied (thường 403); kết quả HTTP chính xác tùy cơ chế bảo mật và chính sách xử lý lỗi. ABAC policy trả quyết định, **không tự đồng nghĩa với một mã HTTP**.

## 10. Quy trình thực hành khi thêm policy mới

1. **Định nghĩa action và resource**: tránh điều kiện chung chung “có quyền với hệ thống”.
2. **Viết policy dưới dạng bảng quyết định** gồm Permit/Deny, rule ưu tiên, ranh giới tenant và điều kiện bắt buộc.
3. **Chỉ ra nguồn cấp thuộc tính** cho subject/resource/context, xác định độ tin cậy, độ mới và fallback khi lỗi.
4. **Tách engine khỏi transport** để policy có thể kiểm thử bằng Java thuần; Spring adapter chỉ làm nhiệm vụ xây dựng context/đưa quyết định vào enforcement.
5. **Gắn enforcement vào mọi đường đi**: HTTP, method, batch, event, update; không để có “đường tắt” đi qua logic bảo vệ.
6. **Kiểm thử negative cases** và invariant; kiểm tra race/caching ở thao tác nhạy cảm.
7. **Quản trị vòng đời policy**: người phê duyệt, phiên bản, audit quyết định, khả năng rollback và migration khi đổi schema thuộc tính.

Một điểm thiết kế quan trọng: policy phức tạp nên được đặt ở một nơi được đặt tên rõ, thay vì rải hàng chục chuỗi SpEL dài trong controller. Trong Spring Security, bean policy/`AuthorizationManager` hoặc dịch vụ quyết định riêng dễ kiểm thử và theo dõi hơn.

## 11. Sai lầm thường gặp

| Sai lầm | Rủi ro | Cách làm đúng |
| --- | --- | --- |
| Chỉ kiểm tra `hasRole('EDITOR')` | Role có hiệu lực quá rộng trên mọi tài nguyên | Kết hợp tenant, owner, classification, action và context |
| Lấy `tenantId`/`ownerId` từ request body rồi cấp quyền | Người gọi có thể tự khai thuộc tính | Nạp thuộc tính tài nguyên từ database, subject từ identity đã xác minh |
| Chỉ chặn nút sửa ở frontend | Có thể gọi API trực tiếp | Thực thi tại backend/service/data boundary |
| Không phân biệt READ/EDIT/EXPORT | Một quyền bị dùng sai cho hành động khác | Liệt kê action và rule riêng |
| Cho phép khi policy service lỗi | Bypass bảo mật khi timeout | Fail closed, ghi audit và phân loại lỗi |
| Ghi `@PreAuthorize` vào method bị gọi qua `this` | Spring AOP proxy thường không chặn self-invocation | Tổ chức boundary qua bean/proxy hoặc enforcement trong service |
| Cache Permit không có resource/action/context | Dùng kết quả cho đối tượng hoặc phiên khác | Cache theo đầy đủ khóa policy, có invalidation và version |
| Dùng đồng hồ browser hoặc header tùy ý | Đối tượng thay đổi thời gian/ngữ cảnh | Dùng server clock và nguồn context tin cậy |
| Bỏ qua transaction khi quyết định trước cập nhật | TOCTOU: thuộc tính có thể đổi sau kiểm tra | Constraint/update trong transaction, optimistic locking nếu phù hợp |
| Dùng reactive handler nhưng truy vấn blocking trong policy | Chặn event loop, giảm thông lượng | Dùng I/O reactive, composition publisher, không `block()` |
| Cho rằng Spring Security tự biết ABAC nghiệp vụ | Không hề bảo vệ owner/tenant cụ thể | Định nghĩa policy và adapter lấy attribute rõ ràng |

## 12. Tự kiểm tra

**Câu 1.** Cùng role `MANAGER`, vì sao user A không mặc nhiên được xem tài liệu tenant B?

**Đáp án:** Vai trò là một thuộc tính; policy vẫn phải kiểm tra `subject.tenantId == resource.tenantId`. Nếu không có ngoại lệ cross-tenant được thiết kế và giám sát, phải Deny.

**Câu 2.** Một tài liệu confidential thuộc cùng tenant và department nhưng subject chưa MFA. ABAC nên trả gì?

**Đáp án:** Deny nếu policy yêu cầu MFA cho confidential. Các điều kiện Permit phải cùng đúng, không cộng điểm để bù nhau.

**Câu 3.** Tại sao không dùng `ownerId` do frontend gửi khi đánh giá quyền?

**Đáp án:** Client điều khiển được dữ liệu request; phải tải owner thực từ tài nguyên trong backend.

**Câu 4.** Vì sao policy READ không thay thế policy EDIT?

**Đáp án:** Action là đầu vào độc lập. Các điều kiện (owner, giờ làm việc, giao dịch nhạy cảm) có thể khác nhau; cho phép đọc không suy ra cho phép sửa.

**Câu 5.** Khi PIP không lấy được classification, có được giả định INTERNAL để tiếp tục không?

**Đáp án:** Không. Việc hạ độ nhạy mặc định có thể cấp quyền sai. Từ chối quyết định Permit, báo lỗi/audit thích hợp và xử lý nguồn dữ liệu.

**Câu 6.** `@PreAuthorize` đã đủ để bảo vệ một thao tác cập nhật mọi trường hợp?

**Đáp án:** Chỉ khi invocation thật đi qua interception, policy đánh giá thuộc tính đúng và không có race giữa kiểm tra với mutation; cần thêm ràng buộc tenant/dữ liệu và xử lý giao dịch tùy nghiệp vụ.

## 13. Tài liệu tham khảo

- [NIST SP 800-162 — Guide to Attribute Based Access Control (ABAC)](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): định nghĩa subject, object, operation, environment và policy.
- [Spring Security — Servlet Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, bean policy và method interception.
- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` và URL/request boundary.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity` và reactive authorization.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình `SecurityWebFilterChain` trong WebFlux.

**Ghi nhớ:** ABAC quyết định dựa trên **ai**, **tài nguyên nào**, **hành động gì**, **trong ngữ cảnh nào**. Chính sách chỉ có ý nghĩa bảo mật khi thuộc tính đáng tin, backend thực sự chặn hành động không được phép, và mọi trường hợp thiếu/không chắc chắn đều được xử lý an toàn.
