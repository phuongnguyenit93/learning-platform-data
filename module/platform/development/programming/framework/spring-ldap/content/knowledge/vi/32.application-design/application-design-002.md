# Chọn aggregate và ranh giới dữ liệu khi dùng directory

## 1. Bài toán: một người dùng xuất hiện ở hai thế giới

Giả sử một nền tảng quản lý workspace dùng **Spring LDAP** để tra cứu nhân viên từ directory của doanh nghiệp. Directory lưu tài khoản, tên hiển thị, email, trạng thái tài khoản và nhóm LDAP. Ứng dụng có cơ sở dữ liệu riêng để lưu các workspace, vai trò trong từng workspace, lịch sử mời thành viên và quyền chỉnh sửa tài liệu.

Khi một nhân viên tham gia workspace, ứng dụng cần đọc danh tính từ LDAP rồi tạo một bản ghi thành viên trong cơ sở dữ liệu. Khi quản trị viên đổi tên hiển thị hoặc chuyển nhân viên sang đơn vị khác, directory thay đổi. Khi trưởng nhóm cấp quyền sửa tài liệu, chỉ dữ liệu nghiệp vụ của ứng dụng thay đổi.

Ba câu hỏi thiết kế quan trọng xuất hiện:

1. **Aggregate nào giữ các bất biến nghiệp vụ?** Ví dụ: thành viên bị khóa không được tự cấp quyền; một workspace phải luôn có ít nhất một chủ sở hữu.
2. **Nguồn nào sở hữu từng loại dữ liệu?** Thông tin định danh có thể thuộc LDAP; vai trò trong workspace có thể thuộc ứng dụng.
3. **Giao dịch có thể bảo đảm tính nhất quán đến đâu?** Một transaction JPA không tự bao phủ thao tác LDAP; tìm kiếm, bind và sửa entry thư mục không trở thành một phần của transaction cơ sở dữ liệu chỉ vì chúng được gọi trong cùng một service.

Chọn đúng ranh giới giúp **domain service** tập trung vào quy tắc nghiệp vụ, trong khi **Spring LDAP**, **LdapTemplate**, **LdapClient**, **ContextSource** hoặc ODM làm việc với schema, DN, filter và thao tác directory ở tầng hạ tầng.

## 2. Aggregate không đồng nghĩa với LDAP entry, OU hoặc bảng dữ liệu

Trong Domain-Driven Design (DDD), **aggregate** là một cụm đối tượng nghiệp vụ có **aggregate root** kiểm soát các thay đổi và bảo vệ những bất biến cần nhất quán trong một giao dịch. Các đối tượng khác chỉ được thay đổi thông qua root.

**LDAP entry** là một đơn vị dữ liệu trong Directory Information Tree (DIT), có distinguished name (DN), object class và các thuộc tính theo schema. **OU** tổ chức hoặc giới hạn phạm vi tìm kiếm. **LDAP group** thể hiện một tập thành viên theo cách tổ chức của directory. Chúng là cấu trúc lưu trữ/thư mục, không tự động trở thành aggregate nghiệp vụ.

| Khái niệm | Trả lời câu hỏi | Ranh giới bảo đảm |
| --- | --- | --- |
| Aggregate DDD | Những quy tắc nào phải đúng sau mỗi thay đổi nghiệp vụ? | Ranh giới tính nhất quán do ứng dụng thiết kế và cơ chế lưu trữ hỗ trợ |
| LDAP entry | Thuộc tính và object class nào đại diện một đối tượng thư mục? | Thao tác sửa một entry; khả năng kiểm tra điều kiện phụ thuộc server/control |
| LDAP OU / subtree | Dữ liệu được tổ chức và tìm trong phạm vi nào? | Ranh giới tên và tìm kiếm, không phải transaction nghiệp vụ |
| LDAP group | Những principal nào thuộc một tập do directory quản lý? | Quan hệ thành viên theo schema/cơ chế của directory |
| Bảng quan hệ / JPA entity | Dữ liệu được lưu và truy vấn như thế nào? | Ranh giới bảng/entity, không nhất thiết trùng aggregate |

Một thao tác **modifyAttributes** có thể cập nhật nhiều thuộc tính của **một entry**, nhưng không có nghĩa nhiều entry LDAP và nhiều hàng JPA sẽ được ghi atomically như một aggregate duy nhất. Việc đổi thành viên của group LDAP, thay trạng thái account và ghi membership trong SQL phải được xem là các thao tác khác hệ thống, với khả năng thất bại độc lập.

### Ba ranh giới phải tách bạch

~~~mermaid
flowchart TB
    subgraph Business["Ranh giới nghiệp vụ"]
      W["Workspace aggregate"]
      M["WorkspaceMember aggregate"]
      P["Quy tắc phân quyền ứng dụng"]
    end
    subgraph Application["Application / use case"]
      UC["JoinWorkspace / GrantRole"]
      DP["DirectoryPersonReader (port)"]
      RP["WorkspaceMemberRepository (port)"]
    end
    subgraph Infrastructure["Hạ tầng"]
      LA["Spring LDAP adapter"]
      RA["SQL/JPA adapter"]
      LDAP[("LDAP directory")]
      DB[("Application database")]
    end
    UC --> DP
    UC --> RP
    UC --> P
    P --> M
    DP -. "implemented by" .-> LA
    RP -. "implemented by" .-> RA
    LA --> LDAP
    RA --> DB
~~~

Sơ đồ minh họa một thiết kế thường gặp: directory là **hệ thống định danh bên ngoài**, còn các aggregate nghiệp vụ được lưu trong database của ứng dụng. Ở cách triển khai khác, directory có thể là nơi ghi dữ liệu chính, nhưng vẫn phải xác định bất biến và khả năng transaction một cách tường minh.

## 3. Cách chọn aggregate từ bất biến thay vì từ schema LDAP

Trước khi đặt tên aggregate, hãy viết quy tắc bằng ngôn ngữ nghiệp vụ, liệt kê **những dữ liệu phải thay đổi cùng nhau**, và hỏi hệ thống nào có khả năng cam kết chúng.

Ví dụ với hệ thống workspace:

| Quy tắc | Dữ liệu liên quan | Gợi ý ranh giới |
| --- | --- | --- |
| Thành viên bị khóa không thể được cấp thêm vai trò | Trạng thái và tập vai trò của **một WorkspaceMember** | Một aggregate **WorkspaceMember** |
| Không thể có hai membership trùng workspace và danh tính directory | Khóa **workspaceId + directorySubject** | Ràng buộc unique trong DB, kết hợp thao tác tạo idempotent |
| Workspace phải có ít nhất một OWNER | Nhiều membership trong cùng workspace | Cần cơ chế điều phối/quản lý chủ sở hữu có thể khóa và cập nhật nhất quán |
| Đổi email nhân viên phải tuân theo quy trình quản trị thư mục | Entry LDAP thuộc tổ chức | Directory là nguồn ghi; application không tự nhận quyền sở hữu thuộc tính |
| Nhân viên bị khóa tài khoản không được truy cập tài liệu mật | Trạng thái directory và quyết định truy cập ứng dụng | Chính sách cấp quyền kết hợp trạng thái bên ngoài với dữ liệu nội bộ; phải định nghĩa độ trễ chấp nhận được |

Quy tắc **“luôn còn ít nhất một OWNER”** cho thấy vì sao không thể gom mọi bất biến vào từng membership độc lập: khi hai OWNER đồng thời tự bỏ quyền, cả hai thay đổi riêng lẻ đều có thể hợp lệ nhưng kết quả cuối cùng không hợp lệ. Có thể dùng một aggregate hoặc thành phần quản lý owner riêng, hoặc transaction cơ sở dữ liệu kèm khóa/kiểm tra nguyên tử theo workspace. **Chỉ đếm owner rồi lưu từng membership không khóa không đủ bảo vệ bất biến dưới cạnh tranh.**

Ngược lại, đưa **tất cả hàng nghìn thành viên** vào một aggregate Workspace khổng lồ có thể gây tranh chấp khóa, truy vấn đắt và tải toàn bộ tập thành viên không cần thiết. Hãy chọn ranh giới nhỏ nhất thực sự bảo vệ được bất biến, rồi thiết kế cơ chế cho bất biến xuyên aggregate khi cần.

Một phép thử nhanh trước khi quyết định:

1. Thao tác nào buộc nhiều giá trị phải đúng *ngay sau một lần commit*?
2. Ai có quyền ghi và chịu trách nhiệm chuẩn hóa từng giá trị?
3. Giá trị nào có thể chậm cập nhật vài giây/phút mà không vi phạm an toàn hay nghiệp vụ?
4. Có cần kiểm soát cập nhật đồng thời hoặc ngăn trùng lặp không?
5. Nếu LDAP không khả dụng, thao tác này có được tiếp tục hay phải từ chối?

## 4. Vẽ bản đồ quyền sở hữu dữ liệu trước khi viết entity

Directory là một nguồn dữ liệu lớn nhưng không nhất thiết là nơi chứa mọi thuộc tính về người dùng. Một mapping phù hợp với ví dụ:

| Dữ liệu | Nguồn ghi chính | Ứng dụng nên lưu/cập nhật thế nào? |
| --- | --- | --- |
| Định danh thư mục bền vững, tên đăng nhập, tên hiển thị, email công việc | LDAP / hệ thống quản lý định danh | Đọc qua gateway; chỉ lưu khóa tham chiếu và bản sao tối thiểu khi có nhu cầu |
| Mật khẩu, trạng thái xác thực, cơ chế khóa tài khoản | Hệ thống định danh | Xác thực bằng bind hoặc tích hợp bảo mật; không sao chép mật khẩu |
| Nhóm tổ chức, phòng ban do doanh nghiệp quản lý | LDAP / hệ thống nhân sự | Đọc như dữ kiện bên ngoài, ánh xạ rõ sang policy nếu cần |
| Workspace, mô tả workspace, lịch sử nội bộ | Database ứng dụng | Aggregate nội bộ sở hữu vòng đời và các thay đổi |
| Vai trò VIEWER/EDITOR/OWNER trong từng workspace | Database ứng dụng (theo giả định bài toán) | WorkspaceMember hoặc mô hình quyền tương ứng sở hữu |
| Biệt danh riêng trong ứng dụng, cài đặt thông báo | Database ứng dụng | Có thể tồn tại khác tên hiển thị trong LDAP |
| Cache tên và email để hiển thị | Bản chiếu từ LDAP | Có thời hạn, chính sách làm mới và quy trình xóa/cập nhật |

**Đối với mỗi trường dữ liệu quan trọng, chỉ rõ một nơi được quyền quyết định giá trị chính.** Nếu email thuộc directory, không để giao diện sửa một bản email nội bộ rồi kỳ vọng LDAP sẽ tự đồng bộ. Nếu business role thuộc ứng dụng, không sửa thuộc tính group LDAP để ghi vai trò trừ khi điều đó là một phần của hợp đồng hệ thống định danh.

Trạng thái nhân viên rời tổ chức là ví dụ đáng chú ý: directory có thể khóa hoặc xóa account nhưng bản ghi membership, nội dung đã tạo và audit trail vẫn cần tồn tại theo chính sách ứng dụng. Hành vi truy cập có thể phải vô hiệu ngay, còn dữ liệu lịch sử được lưu theo yêu cầu bảo mật và thời hạn lưu trữ. Không xóa cascade toàn bộ nghiệp vụ chỉ vì không tìm thấy entry.

## 5. Khóa tham chiếu tới directory: ưu tiên ID ổn định, không dùng DN làm khóa nghiệp vụ

Một DN như **uid=lan,ou=people,dc=example,dc=org** có thể thay đổi khi entry bị rename hoặc move; **uid** hoặc **cn** cũng có thể bị đổi hoặc tái sử dụng. Nếu dùng những giá trị này làm primary key của membership, ứng dụng dễ tạo tài khoản trùng hoặc mất liên kết lịch sử.

Định danh nên gồm **mã nguồn directory** và **ID entry được phát hành ổn định trong nguồn đó**. Ví dụ:

- OpenLDAP thường có operational attribute **entryUUID**; cần yêu cầu tường minh attribute này khi truy vấn.
- Active Directory cung cấp **objectGUID** (giá trị nhị phân, cần mapper phù hợp); tên thuộc tính và cách truy vấn không giống OpenLDAP.
- Directory do tổ chức tự triển khai có thể công bố một ID khác. Không mặc định **uid** hoặc DN bền vững.

~~~java
// domain/DirectorySubject.java
package com.example.workspace.domain;

import java.util.Objects;

public record DirectorySubject(String source, String opaqueId) {
    public DirectorySubject {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(opaqueId, "opaqueId");
        if (source.isBlank() || opaqueId.isBlank()) {
            throw new IllegalArgumentException("DirectorySubject không được rỗng");
        }
    }
}
~~~

Ứng dụng có thể dùng một UUID riêng làm **WorkspaceMember.id**, đồng thời đặt unique constraint trên **(workspace_id, directory_source, directory_subject_id)**. Khóa riêng giúp tham chiếu nội bộ không phụ thuộc schema LDAP; khóa ghép giúp bảo đảm không đăng ký cùng danh tính hai lần trong một workspace.

Ngay cả ID như **entryUUID** hoặc **objectGUID** cũng có phạm vi sống và di chuyển cụ thể: xóa rồi tạo lại account, đổi directory hoặc migration dữ liệu có thể sinh ID mới. Nếu tổ chức cần giữ liên kết xuyên migration, phải có bảng ánh xạ được xác nhận và quy trình đối soát; không tự ghép hai danh tính chỉ vì cùng tên/email.

## 6. Mẫu aggregate: WorkspaceMember sở hữu quyền trong ứng dụng

Ví dụ này chọn **WorkspaceMember** làm aggregate root cho trạng thái và vai trò của **một người trong một workspace**. Mối liên hệ tới directory được lưu bằng **DirectorySubject**; model không biết DN, filter hoặc LDAP attribute.

~~~java
// domain/WorkspaceRole.java
package com.example.workspace.domain;

public enum WorkspaceRole {
    VIEWER, EDITOR, OWNER
}
~~~

~~~java
// domain/WorkspaceMember.java
package com.example.workspace.domain;

import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public final class WorkspaceMember {
    private final UUID id;
    private final UUID workspaceId;
    private final DirectorySubject subject;
    private final EnumSet<WorkspaceRole> roles;
    private boolean suspended;

    private WorkspaceMember(
            UUID id, UUID workspaceId, DirectorySubject subject) {
        this.id = Objects.requireNonNull(id);
        this.workspaceId = Objects.requireNonNull(workspaceId);
        this.subject = Objects.requireNonNull(subject);
        this.roles = EnumSet.of(WorkspaceRole.VIEWER);
    }

    public static WorkspaceMember enroll(
            UUID workspaceId, DirectorySubject subject) {
        return new WorkspaceMember(UUID.randomUUID(), workspaceId, subject);
    }

    public void grant(WorkspaceRole role) {
        Objects.requireNonNull(role);
        if (suspended) {
            throw new IllegalStateException(
                    "Không thể cấp vai trò cho thành viên đang bị khóa");
        }
        roles.add(role);
    }

    public void suspend() {
        suspended = true;
    }

    public boolean canEdit() {
        return !suspended
                && (roles.contains(WorkspaceRole.EDITOR)
                    || roles.contains(WorkspaceRole.OWNER));
    }

    public UUID id() { return id; }
    public UUID workspaceId() { return workspaceId; }
    public DirectorySubject subject() { return subject; }
    public Set<WorkspaceRole> roles() { return Set.copyOf(roles); }
    public boolean suspended() { return suspended; }
}
~~~

Đây là một **mô hình domain minh họa**, chưa gồm cơ chế tái dựng từ persistence, optimistic locking, chính sách thu hồi OWNER hay kiểm soát người thực hiện thao tác. Khi triển khai thực tế, phần ánh xạ JPA và version cần bảo đảm cập nhật cạnh tranh không ghi đè vai trò hoặc trạng thái vừa thay đổi.

Quy tắc “không cấp vai trò cho thành viên đang bị khóa” nằm trong aggregate và có thể kiểm thử hoàn toàn độc lập với LDAP. Ngược lại, “nhân viên chưa bị disable trong LDAP” là một **dữ kiện bên ngoài** cần được kiểm tra bằng policy tại thời điểm thích hợp; nếu không có hợp đồng consistency, không thể coi trạng thái LDAP là một trường đã được khóa atomically cùng WorkspaceMember.

## 7. Port chỉ mô tả nhu cầu, adapter mới hiểu Spring LDAP

Ứng dụng định nghĩa dữ liệu trả về từ directory và cổng đọc danh tính:

~~~java
// application/DirectoryPerson.java
package com.example.workspace.application;

import com.example.workspace.domain.DirectorySubject;

public record DirectoryPerson(
        DirectorySubject subject,
        String login,
        String displayName
) {}
~~~

~~~java
// application/DirectoryPersonReader.java
package com.example.workspace.application;

import java.util.Optional;

public interface DirectoryPersonReader {
    Optional<DirectoryPerson> findByLogin(String login);
}
~~~

Ở ví dụ OpenLDAP, adapter tập trung mapping **uid**, **cn** và **entryUUID**. Giả định **spring.ldap.base** đã là **dc=example,dc=org**, nên search base chỉ là **ou=people**.

~~~java
// infrastructure/ldap/SpringLdapDirectoryPersonReader.java
package com.example.workspace.infrastructure.ldap;

import com.example.workspace.application.DirectoryPerson;
import com.example.workspace.application.DirectoryPersonReader;
import com.example.workspace.domain.DirectorySubject;
import java.util.List;
import java.util.Optional;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class SpringLdapDirectoryPersonReader
        implements DirectoryPersonReader {

    private final LdapTemplate ldapTemplate;

    public SpringLdapDirectoryPersonReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public Optional<DirectoryPerson> findByLogin(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("Login không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "entryUUID")
                .where("uid").is(login);

        List<DirectoryPerson> matches = ldapTemplate.search(
                query, (ContextMapper<DirectoryPerson>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;
                    String stableId = entry.getStringAttribute("entryUUID");
                    String uid = entry.getStringAttribute("uid");
                    if (stableId == null || stableId.isBlank()
                            || uid == null || uid.isBlank()) {
                        throw new IllegalStateException(
                                "LDAP entry thiếu định danh bắt buộc");
                    }
                    return new DirectoryPerson(
                            new DirectorySubject("corp-openldap", stableId),
                            uid,
                            entry.getStringAttribute("cn"));
                });

        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "Directory trả nhiều entry cho một login");
        }
        return matches.stream().findFirst();
    }
}
~~~

Các điều kiện đi kèm quan trọng:

- **LdapQueryBuilder** thực hiện escaping cho giá trị filter; tránh nối chuỗi LDAP filter từ đầu vào người dùng. Nếu cần dựng DN động, dùng **LdapNameBuilder**.
- **entryUUID** là giả định của OpenLDAP. Với Active Directory, adapter có thể ánh xạ **objectGUID** nhưng domain và port vẫn dùng **DirectorySubject**.
- Nếu directory trả 0 entry, kết quả là **Optional.empty()**. Nếu LDAP timeout, bind thất bại, thiếu quyền đọc thuộc tính, schema sai hoặc có nhiều entry, đó là lỗi riêng cần được adapter phân loại thành exception ứng dụng phù hợp. **Không chuyển mọi lỗi thành “không tìm thấy”.**
- Dữ liệu như **displayName** có thể là bản đọc tại một thời điểm. Nó không đương nhiên trở thành thuộc tính mà aggregate được phép cập nhật.
- Với **LdapClient** hoặc **Spring LDAP ODM**, có thể thay cách truy vấn/ánh xạ trong adapter. Quyết định aggregate và quyền sở hữu dữ liệu không thay đổi theo API truy vấn.

Mã tập trung vào ranh giới thiết kế. Trong hệ thống thực, cần bổ sung exception mapping theo Spring LDAP, test schema thật, timeout và chiến lược quản lý kết nối.

## 8. Use case điều phối hai nguồn dữ liệu

Một use case **JoinWorkspace** trước tiên xác thực sự tồn tại của nhân viên qua cổng LDAP, sau đó yêu cầu tầng lưu trữ nghiệp vụ đăng ký membership bằng một transaction SQL riêng:

~~~java
// application/WorkspaceMemberWriter.java
package com.example.workspace.application;

import com.example.workspace.domain.DirectorySubject;
import java.util.UUID;

public interface WorkspaceMemberWriter {
    UUID enrollIfAbsent(UUID workspaceId, DirectorySubject subject);
}
~~~

~~~java
// application/JoinWorkspace.java
package com.example.workspace.application;

import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class JoinWorkspace {
    private final DirectoryPersonReader directory;
    private final WorkspaceMemberWriter members;

    public JoinWorkspace(
            DirectoryPersonReader directory,
            WorkspaceMemberWriter members) {
        this.directory = directory;
        this.members = members;
    }

    public UUID execute(UUID workspaceId, String login) {
        DirectoryPerson person = directory.findByLogin(login)
                .orElseThrow(() -> new NoSuchElementException(
                        "Tài khoản không tồn tại trong directory"));
        return members.enrollIfAbsent(workspaceId, person.subject());
    }
}
~~~

**WorkspaceMemberWriter** được hiện thực bằng repository JPA/SQL. Phương thức **enrollIfAbsent** phải có transaction database và unique constraint trên **(workspace_id, directory_source, directory_subject_id)**. Nếu hai request đồng thời cùng đăng ký, adapter cần xử lý xung đột unique một cách idempotent và trả về membership có sẵn, thay vì chèn hai dòng. Có thể dùng cơ chế insert-if-absent/UPSERT thích hợp với database hoặc xử lý duplicate key sau khi transaction thất bại.

Việc đọc LDAP được đặt **trước** lời gọi ghi SQL để tránh giữ transaction database mở trong lúc chờ mạng LDAP. Dù vậy, vẫn có **khoảng thời gian giữa việc đọc và ghi**: account có thể bị vô hiệu hóa ngay sau tra cứu. Nếu quyết định cấp quyền yêu cầu trạng thái directory phải còn hiệu lực ngay tại thời điểm truy cập, cần kiểm tra tại authorization path hoặc một cơ chế đồng bộ có cam kết độ trễ đủ chặt; không thể giải quyết chỉ bằng **@Transactional** của Spring.

Luồng xử lý:

~~~mermaid
sequenceDiagram
    actor Client
    participant UseCase as JoinWorkspace
    participant LDAP as DirectoryPersonReader
    participant SQL as MemberWriter (SQL)
    Client->>UseCase: join(workspaceId, login)
    UseCase->>LDAP: findByLogin(login)
    LDAP-->>UseCase: DirectoryPerson + stable subject
    UseCase->>SQL: enrollIfAbsent(workspaceId, subject)
    Note over SQL: Transaction + unique constraint
    SQL-->>UseCase: membershipId
    UseCase-->>Client: membershipId
~~~

Các kiểm tra phân quyền người gọi, giới hạn số thành viên hay duyệt lời mời là quy tắc của ứng dụng và phải được thực hiện trong luồng nghiệp vụ tương ứng. Chỉ vì tìm thấy tài khoản LDAP không có nghĩa tài khoản đó được phép tự tham gia mọi workspace.

## 9. Nhóm LDAP, vai trò ứng dụng và ranh giới phân quyền

Một người có thể là thành viên của LDAP group **cn=engineers**, nhưng được cấp role **VIEWER** trong workspace A và **OWNER** trong workspace B. Hai cấu trúc quyền phục vụ những mục đích khác nhau.

Có ba hướng thiết kế phổ biến:

| Cách sử dụng LDAP group | Khi phù hợp | Điều cần thiết kế |
| --- | --- | --- |
| Group chỉ làm dữ kiện cho policy | Chẳng hạn chỉ nhóm nhân viên chính thức mới được tham gia workspace | Đọc membership theo schema cụ thể; tách kiểm tra group khỏi quyền trong workspace |
| Group là nguồn quyền trực tiếp | Tổ chức chủ động quản lý quyền ứng dụng qua IdM/LDAP | Quy định ánh xạ group→permission, độ trễ đồng bộ và cách thu hồi quyền |
| Ứng dụng sở hữu role và có bản chiếu group | Role nội bộ có vòng đời riêng | Không cho dữ liệu chiếu từ LDAP ghi đè quyết định role do ứng dụng sở hữu nếu không có chính sách rõ ràng |

Đọc group trong LDAP không luôn giống nhau: **member**, **uniqueMember**, **memberOf**, nested group và dynamic group phụ thuộc schema, máy chủ và cấu hình. Một server có thể trả membership theo DN; một server khác dùng attribute khác hoặc cần tìm kiếm ngược. Vì vậy gateway nên trả về kiểu trung lập như **DirectoryGroupId** hoặc **DirectoryEntitlement**, còn policy ứng dụng quyết định ý nghĩa của nó.

Đặc biệt, không biến group **cn=admins** thành role **OWNER** mặc định nếu chưa có quyết định nghiệp vụ và kiểm soát rõ nguồn dữ liệu. Thu hồi group trên directory có thể đến ứng dụng muộn do cache, replication hoặc lịch đồng bộ. Với quyền nhạy cảm, phải xác định độ trễ thu hồi được phép và xử lý trường hợp directory không sẵn sàng.

## 10. Consistency và đồng bộ: không giả định một transaction bao phủ mọi hệ thống

Khi một use case vừa thay LDAP vừa thay database, các thao tác có thể thành công một phần. Transaction của JPA không tự rollback những thay đổi LDAP; ngược lại rollback LDAP không tự rollback SQL. Cần chọn thiết kế theo **system of record** và khả năng phục hồi thực tế.

| Tình huống | Phản ứng gợi ý |
| --- | --- |
| LDAP không thể tra cứu danh tính mới | Từ chối đăng ký mới với trạng thái tạm thời phù hợp; phân biệt outage với account không tồn tại |
| LDAP trả danh tính nhưng SQL ghi lỗi | Không coi đăng ký thành công; retry idempotent sau khi xử lý lỗi database |
| SQL đã lưu membership, account LDAP bị khóa ngay sau đó | Authorization phải tôn trọng chính sách vô hiệu hóa; đồng bộ trạng thái hoặc kiểm tra trực tiếp khi cần |
| Dữ liệu tên/email trong cache cũ | Làm mới theo TTL hoặc sự kiện; không dùng cache hiển thị để quyết định danh tính |
| ID directory đổi sau migration | Đối soát và map có kiểm chứng; không tự liên kết theo email hoặc login |
| Đồng bộ gửi cùng sự kiện nhiều lần | Consumer xử lý idempotent theo khóa sự kiện hoặc trạng thái nguồn; tránh tạo membership trùng |
| Event đến không đúng thứ tự | Dùng version/change token được **nguồn cụ thể** bảo đảm, hoặc cơ chế đọc lại trạng thái hiện tại |

Nếu directory có change log, synchronization connector hoặc cơ chế phát sự kiện, có thể cập nhật **projection** về danh tính/group trong ứng dụng. Tuy nhiên version và order của thay đổi phụ thuộc sản phẩm: không tự giả định mọi LDAP server đều cung cấp sequence number toàn cục. Với directory không có feed tin cậy, dùng job đối soát phân trang theo lịch và đánh dấu thời điểm dữ liệu được quan sát.

Một thiết kế đối soát nên nêu rõ:

1. **Khóa so khớp** là ID ổn định trong một directory source, không phải DN.
2. **Trường đồng bộ** là những trường được LDAP sở hữu; những trường ứng dụng sở hữu không bị ghi đè.
3. **Trường hợp xóa/khóa** có hành vi xác định: chặn truy cập, giữ dữ liệu lịch sử hay đặt trạng thái chờ điều tra.
4. **Khả năng lặp lại**: cùng sự kiện hoặc cùng trang dữ liệu xử lý lại không tạo tác dụng phụ ngoài ý muốn.
5. **Khả năng quan sát**: theo dõi lần đồng bộ cuối, số entry bị lỗi, độ trễ, cursor và cảnh báo.

Khi dùng **LdapTemplate** hoặc **LdapClient** để đồng bộ nhiều entry, cần đặt phạm vi tìm kiếm, size limit, xử lý phân trang theo server/control phù hợp, timeout và backoff. Không tải cả directory vào bộ nhớ mỗi request. Đừng mặc định tìm kiếm LDAP là snapshot nhất quán trên các bản sao hoặc qua nhiều trang.

## 11. Ranh giới bảo mật và quyền ghi directory

Những quyết định aggregate chỉ có ý nghĩa khi mỗi thành phần có quyền hạ tầng tương ứng:

- **ContextSource** đọc danh tính nên dùng service account có quyền đọc tối thiểu. Gateway cập nhật entry, nếu thực sự cần, nên dùng principal và ACL thích hợp; tách cổng đọc và cổng ghi nếu chính sách quyền khác nhau.
- Kết nối tới LDAP cần bảo vệ bằng **LDAPS** hoặc **StartTLS** được cấu hình đúng, xác minh chứng chỉ và tên máy chủ. Không dùng bind credential trong log hoặc source code.
- **Connection pooling** phải phù hợp với TLS và ngữ cảnh bind; không tái sử dụng bừa bãi kết nối mang danh tính người dùng khác. Cấu hình connect/read timeout và cách xử lý lỗi mạng ở adapter.
- Các tác vụ xác thực cần dùng cơ chế bind/identity provider hoặc Spring Security LDAP. **Không đọc và sao chép userPassword** vào aggregate.
- Tránh đưa email công việc, số điện thoại và các thuộc tính cá nhân vào bảng nội bộ nếu không có mục đích. Nếu cần snapshot cho audit hoặc hiển thị, quy định retention, quyền truy cập và cập nhật/xóa dữ liệu.

Trong trường hợp ứng dụng **thật sự sở hữu việc ghi LDAP entry**, có thể thiết kế aggregate xoay quanh một entry và dùng mapper/ODM để lưu các thuộc tính có liên quan. Tuy nhiên phải kiểm tra các bất biến có thể được thực thi bằng **một thao tác LDAP entry**; các bất biến liên quan nhiều entry hoặc nhiều hệ thống vẫn cần cơ chế nhất quán khác. Không nhầm annotation ODM hoặc object class với ranh giới transaction DDD.

## 12. Kiểm thử theo từng loại ranh giới

**Unit test domain (không cần LDAP):**

~~~java
import com.example.workspace.domain.DirectorySubject;
import com.example.workspace.domain.WorkspaceMember;
import com.example.workspace.domain.WorkspaceRole;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

// Đặt trong phương thức @Test của JUnit 5:
WorkspaceMember member = WorkspaceMember.enroll(
        UUID.randomUUID(),
        new DirectorySubject("corp-openldap", "stable-123"));
member.grant(WorkspaceRole.EDITOR);
assertTrue(member.canEdit());

member.suspend();
assertFalse(member.canEdit());
assertThrows(IllegalStateException.class,
        () -> member.grant(WorkspaceRole.OWNER));
~~~

**Application test:** dùng fake **DirectoryPersonReader** trả danh tính, trả **Optional.empty()**, hoặc ném lỗi tạm thời. Xác nhận use case không ghi membership khi người dùng không tồn tại/LDAP lỗi và truyền đúng **DirectorySubject** cho writer. Thử đồng thời nhiều lời gọi **enrollIfAbsent** để kiểm tra unique constraint và idempotency của SQL adapter.

**Spring LDAP integration test:** dùng OpenLDAP test server hoặc directory tương thích với schema đã chọn. Kiểm thử tra cứu **uid**, đọc **entryUUID**, entry thiếu attribute, zero/multiple matches, giá trị filter có ký tự đặc biệt, bind thiếu quyền, timeout và TLS. Nếu dùng Active Directory, cần bộ test mapping **objectGUID** riêng: không giả định OpenLDAP và AD trả cùng kiểu giá trị.

**End-to-end / failure test:** cố tình chặn LDAP khi API đăng ký, vô hiệu hóa account sau khi đã có membership, phát cùng sự kiện đồng bộ hai lần, chuyển OU/rename DN, thay đổi group, và tạo đồng thời hai membership trùng. Xác minh quyền truy cập tuân theo chính sách dù dữ liệu đang trễ, đồng thời lịch sử nghiệp vụ không bị mất.

Một số kiểm tra kiến trúc có thể dùng ArchUnit hoặc quy tắc review: package **domain** không import **org.springframework.ldap**, **javax.naming**, **LdapTemplate**, **LdapClient** hay lớp persistence. Port không trả về **Attributes**, **DirContextOperations** hoặc LDAP DN làm giao diện mặc định cho nghiệp vụ.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Tại sao gây vấn đề | Điều chỉnh |
| --- | --- | --- |
| Coi mỗi OU hoặc bảng LDAP là một aggregate | Cấu trúc directory không phản ánh các bất biến nghiệp vụ | Bắt đầu từ invariant và use case, rồi chọn nơi lưu |
| Dùng DN hoặc email làm khóa membership | Entry có thể move/rename; email có thể đổi và tái sử dụng | Dùng source + stable ID và chính sách migration |
| Sao chép tất cả thuộc tính LDAP vào domain entity | Tạo nhiều nguồn ghi, dữ liệu nhanh cũ và tăng rủi ro riêng tư | Chỉ lưu khóa tham chiếu và projection tối thiểu |
| Cấp vai trò dựa vào một group LDAP chưa có policy | Quyền dễ bị mở rộng ngoài ý muốn | Mapping group→permission rõ ràng, có audit và quy trình thu hồi |
| Gọi LDAP trong transaction DB dài | Chiếm connection/lock lâu trong khi chờ mạng | Tra cứu trước, transaction ngắn cho ghi nội bộ; xử lý race |
| Tin rằng @Transactional sẽ rollback LDAP | Tạo trạng thái ghi một phần khi lỗi | Idempotency, đối soát, bù trừ theo use case |
| Xóa membership khi LDAP không trả entry | Sự cố mạng hoặc replication bị hiểu là xóa tài khoản | Phân biệt absent và unavailable; quy trình deprovision |
| Gộp toàn bộ thành viên vào một aggregate lớn | Cạnh tranh ghi, tốn tải và khó mở rộng | Aggregate nhỏ; cơ chế riêng cho bất biến xuyên aggregate |

## 14. Bài tập thiết kế và checklist

**Tình huống:** công ty dùng OpenLDAP quản lý nhân viên. Ứng dụng dự án có **Project**, **ProjectMember** và quyền **READER/CONTRIBUTOR/MAINTAINER**. Nhân viên có thể đổi OU và tên đăng nhập; mỗi dự án phải còn ít nhất một MAINTAINER. Khi nhân viên nghỉ việc, directory khóa account nhưng các bình luận đã viết phải giữ để phục vụ audit.

Hãy xác định:

1. Aggregate root nào sở hữu quyền của một ProjectMember? Bất biến “ít nhất một MAINTAINER” được bảo vệ bằng cơ chế gì khi có hai request đồng thời?
2. Những trường nào lấy từ LDAP, những trường nào ứng dụng là nguồn ghi chính? Đặt khóa ổn định ra sao khi nhân viên đổi DN?
3. Port đọc directory sẽ trả kiểu dữ liệu nào để domain không biết **entryUUID**, **uid**, **LdapQuery**?
4. Tình huống nào phải từ chối truy cập ngay và tình huống nào có thể xử lý bằng đồng bộ định kỳ?
5. Cách kiểm thử khi LDAP timeout, account bị khóa, sự kiện lặp hoặc đăng ký thành viên đồng thời là gì?

Trước khi chốt thiết kế sản phẩm thực, kiểm tra đã có **bản đồ chủ sở hữu dữ liệu**, **danh sách invariant**, **khóa tham chiếu bền vững**, **chính sách lỗi và đồng bộ**, **cơ chế transaction/locking**, cùng **kiểm thử ở ranh giới LDAP và SQL**.

**Kết luận:** chọn aggregate từ những bất biến cần được bảo vệ và quyền sở hữu dữ liệu, không từ DN, OU, LDAP group hay annotation ODM. Directory là nguồn nhận diện có cấu trúc và vòng đời riêng; ứng dụng tham chiếu nó qua khóa ổn định, adapter Spring LDAP và các policy rõ ràng. Nhờ đó domain giữ được tính nhất quán trong phạm vi thực sự kiểm soát, đồng thời xử lý có chủ đích những thay đổi đến từ hệ thống thư mục.
