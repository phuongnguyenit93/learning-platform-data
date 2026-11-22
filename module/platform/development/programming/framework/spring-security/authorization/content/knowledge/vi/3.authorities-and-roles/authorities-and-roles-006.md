# Ánh xạ role, nhóm và quyền từ nguồn danh tính

## 1. Bức tranh tổng thể: danh tính và quyền truy cập đến từ đâu?

Trong Spring Security, **xác thực (authentication)** xác định chủ thể đang gửi yêu cầu; **phân quyền (authorization)** quyết định chủ thể ấy được làm hành động nào với tài nguyên nào. Một nguồn danh tính như cơ sở dữ liệu người dùng, LDAP/Active Directory hoặc nhà cung cấp danh tính (Identity Provider, **IdP**) có thể cho biết người dùng thuộc nhóm nào, có những role nào hoặc mang scope nào. Nhưng ứng dụng vẫn phải quyết định những dữ kiện đó tương ứng với **quyền ứng dụng** nào.

Hãy hình dung người dùng An được nguồn danh tính xác nhận thuộc nhóm có ID `g-finance-reviewers`. Hệ thống nghiệp vụ muốn nhóm này có quyền đọc báo cáo và gửi đề nghị phê duyệt. Spring Security không tự biết `g-finance-reviewers` phải được biến thành `report:read` hoặc `report:approve`; ứng dụng phải có **quy tắc ánh xạ (mapping)** tường minh, dựa trên dữ liệu đáng tin và có thể kiểm thử.

Luồng dữ liệu:

```text
[Người dùng / dịch vụ]
         |
         v
[Đăng nhập hoặc gửi access token]
         |
         v
[Nguồn danh tính đáng tin / xác thực token]
         |
         | chủ thể, issuer, nhóm, role, scope, tenant ...
         v
[Ánh xạ có kiểm soát]
  - kiểm tra nguồn và định dạng
  - chuẩn hóa mã nhóm/role
  - tra bảng ánh xạ được duyệt
  - kết hợp quyền của ứng dụng
         |
         v
[Authentication.getAuthorities()]
  [ROLE_REPORT_REVIEWER, report:read, report:approve, SCOPE_reports]
         |
         v
[Quy tắc Spring Security + chính sách đối tượng]
  - quyền chức năng?
  - đúng tenant?
  - có quyền với bản ghi này?
  - đúng trạng thái/quy trình?
         |
         v
           ALLOW / DENY
```

Điểm mấu chốt là **một claim tồn tại trong token không đồng nghĩa nó đã là một `GrantedAuthority`**. Một `GrantedAuthority` hợp lệ cũng chưa tự chứng minh người dùng có quyền truy cập mọi đối tượng: còn phải xét tenant, chủ sở hữu, trạng thái, quan hệ chia sẻ hoặc chính sách khác.

Mục tiêu của bài là hiểu và thực hiện đúng chuỗi: **nguồn danh tính → thông tin tin cậy → ánh xạ role/nhóm/quyền → GrantedAuthority → quyết định phân quyền**, sau đó kiểm thử vòng đời cấp và thu hồi quyền.

## 2. Phân biệt những tên gọi dễ nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Danh tính (identity/principal) | Ai đang được hệ thống nhận diện? | User ID `u-1024` |
| Nhóm (group) | Tập người dùng do nguồn danh tính quản lý | Group ID `g-report-approvers` |
| Role nguồn (IdP role) | Nhãn vai trò được IdP/ứng dụng bên ngoài phát hành | `finance-reviewer` |
| Role ứng dụng | Nhóm quyền theo trách nhiệm nghiệp vụ | `REPORT_REVIEWER` |
| Permission | Quyền thao tác cụ thể trong ứng dụng | `report:read`, `report:approve` |
| Scope | Phạm vi ủy quyền được phát hành cho token/client | `reports.read` |
| `GrantedAuthority` | Đại diện một quyền được Spring Security sử dụng | `ROLE_REPORT_REVIEWER`, `report:read` |
| Resource policy | Điều kiện quyền trên tài nguyên cụ thể | Cùng tenant, thuộc nhóm được giao |
| Nguồn sự thật (source of truth) | Nơi một loại thông tin được quản lý có thẩm quyền | IdP quản lý nhóm; ứng dụng quản lý hạn mức duyệt |

Ví dụ, người dùng có `ROLE_REPORT_REVIEWER` không có nghĩa ứng dụng phải cho duyệt mọi báo cáo. Vai trò có thể được dùng như một **điều kiện chức năng**, trong khi việc duyệt báo cáo số 123 vẫn cần kiểm tra doanh nghiệp sở hữu báo cáo và người tạo.

### 2.1. `hasAuthority` và `hasRole` so khớp thế nào?

Trong cấu hình thông dụng của Spring Security:

- `hasAuthority("report:read")` kiểm tra **chính xác** authority `report:read`.
- `hasAuthority("ROLE_ADMIN")` kiểm tra **chính xác** authority `ROLE_ADMIN`.
- `hasRole("ADMIN")` thông thường tìm authority `ROLE_ADMIN`; tiền tố mặc định là `ROLE_`.
- `hasAuthority("SCOPE_reports.read")` kiểm tra chuỗi `SCOPE_reports.read`, có thể do bộ chuyển scope từ JWT tạo ra.

Vì vậy, `ADMIN`, `ROLE_ADMIN`, `SCOPE_ADMIN` và `admin` **không tương đương**. Nếu hệ thống thay tiền tố role bằng cấu hình riêng, quy ước so khớp cũng phải được điều chỉnh nhất quán. Đừng “sửa nhanh” bằng cách gán thêm tất cả biến thể chuỗi, vì như vậy có thể vô tình mở quyền.

### 2.2. Role nguồn, role ứng dụng và permission không bắt buộc 1–1

Một nhóm tổ chức có thể ánh xạ thành nhiều quyền:

```text
Group ID: g-report-approvers
       |
       +--> ROLE_REPORT_REVIEWER
       +--> report:read
       +--> report:approve
```

Ngược lại, quyền `report:read` có thể được cấp cho nhiều nhóm. Một người có thể thuộc nhiều nhóm và được tổng hợp các quyền hiệu lực; nhưng việc **hợp nhất** phải có quy tắc rõ, đặc biệt khi có giới hạn tenant, quyền phủ định hoặc vai trò xung đột.

Bảng ánh xạ có thể đặt trong cấu hình được quản lý phiên bản hoặc kho dữ liệu chính sách. Cần ghi rõ chủ sở hữu nghiệp vụ và quy trình phê duyệt thay đổi. Không nên xem tên nhóm dễ đọc trên màn hình là định danh bất biến; nếu IdP cung cấp group ID ổn định, ưu tiên dùng ID ấy để tránh lỗi do đổi tên nhóm.

## 3. Xác định rõ loại nguồn danh tính và dữ liệu có thể tin

Nguồn danh tính cung cấp các loại thông tin khác nhau. Không có một claim chuẩn chung bắt buộc mọi IdP đều phải đặt nhóm trong `groups`, quyền trong `permissions` hay role trong `roles`. Trước khi viết mã, hãy xác minh **nhà cung cấp**, **kiểu thông tin**, **nơi lấy thông tin** và **cơ chế xác thực nguồn**.

| Nguồn | Thông tin thường gặp | Cách dữ liệu đến Spring Security | Điều phải kiểm chứng |
| --- | --- | --- | --- |
| Database người dùng ứng dụng | User ID, role/permission nội bộ, trạng thái tài khoản | `UserDetailsService` hoặc dịch vụ xác thực riêng | Quyền có hiệu lực và tài khoản còn hoạt động |
| LDAP/Active Directory | User DN/ID, nhóm, thuộc tính thư mục | Cấu hình xác thực LDAP và lớp ánh xạ nhóm/role | Nhóm trực tiếp/lồng nhau, quy ước DN, giới hạn dữ liệu |
| OAuth2/OIDC đăng nhập | ID người dùng, một số claim nhóm/role, quyền của token | `OAuth2User`/`OidcUser`, user service và authority mapper | Claim đến từ ID token hay UserInfo; nguồn/cấu hình tin cậy |
| OAuth2 Resource Server JWT | `iss`, `sub`, `aud`, `scope`/`scp`, claim riêng | `JwtDecoder`, `JwtAuthenticationConverter` | Chữ ký, issuer, audience, hiệu lực token, nguồn claim |
| Token opaque | Phạm vi/dữ liệu do nơi introspection trả về | OAuth2 introspection và converter phù hợp | Endpoint introspection đáng tin, trạng thái active, dữ liệu trả về |
| Nguồn quản lý quyền nội bộ | Gán role theo tenant, hạn mức, tài nguyên | Truy vấn hoặc dịch vụ chính sách của ứng dụng | Bảo vệ API quản trị, tính mới dữ liệu, kiểm toán |

Khi có hai nguồn khác nhau, cần định nghĩa **ai quản lý điều gì**. Ví dụ, IdP sở hữu danh tính và nhóm bộ phận, trong khi ứng dụng sở hữu quyền phê duyệt giao dịch theo tenant và hạn mức. Không nên cho một nhóm chung ở IdP tùy tiện biến thành quyền quản trị toàn cục của ứng dụng.

### 3.1. ID token, access token và claims khác nhau

Trong OIDC, **ID token** phục vụ xác nhận thông tin đăng nhập với client; **access token** được cấp để truy cập tài nguyên/API theo mục đích và đối tượng nhận phù hợp. Một API resource server không được tự chấp nhận một ID token làm bearer access token chỉ vì nó có chữ ký hợp lệ.

Trước khi ánh xạ JWT thành authority, máy chủ phải xác thực token bằng bộ giải mã tin cậy, bao gồm chữ ký/thuật toán được cho phép, thời gian hiệu lực, issuer và audience phù hợp với API. Một JWT được ký đúng nhưng phát hành **cho API khác** không vì thế trở thành quyền truy cập API hiện tại. Với đa issuer, cần cấu hình một danh sách nguồn được tin cậy; không dùng giá trị `iss` chưa được xác minh để tự động tin mọi issuer.

### 3.2. Claim nhóm/role có thể vắng mặt, đổi định dạng hoặc quá lớn

Một số nhà cung cấp đặt nhóm trong `groups`, nhà cung cấp khác đặt role trong claim tùy biến hoặc nested object. Có nơi không đưa toàn bộ danh sách nhóm vào token khi người dùng thuộc quá nhiều nhóm, thay bằng chỉ báo yêu cầu truy vấn bổ sung. Nếu thiếu claim hoặc không đọc được định dạng, **không tự đoán quyền quản trị**. Hãy dùng một API tra cứu nhóm có xác thực và phân quyền rõ, hoặc từ chối theo chính sách khi không có đủ dữ liệu.

Không nhận dạng nhóm bằng tìm chuỗi con:

```text
SAI:
  nếu "admin" xuất hiện ở đâu đó trong tên nhóm -> ROLE_ADMIN

ĐÚNG HƠN:
  map["group-id-đã-duyệt"] -> các authority cụ thể,
  group khác hoặc không biết -> không có quyền từ mapping này
```

Tên nhóm, chữ hoa/thường, ký tự khoảng trắng và tiền tố phải được chuẩn hóa theo hợp đồng với IdP, không chuẩn hóa tùy tiện thành một group khác có đặc quyền.

## 4. Thiết kế bảng ánh xạ trước khi viết Spring Security

Giả sử ứng dụng báo cáo có ba nhóm do IdP quản lý và một số permission do ứng dụng sở hữu:

| Group ID đáng tin | Quyền ứng dụng được cấp | Vai trò ứng dụng (nếu dùng) | Phạm vi/giới hạn |
| --- | --- | --- | --- |
| `g-report-viewers` | `report:read` | `ROLE_REPORT_VIEWER` | Chỉ báo cáo của tenant mà user có quyền |
| `g-report-editors` | `report:read`, `report:update` | `ROLE_REPORT_EDITOR` | Chỉ dự án được giao |
| `g-report-approvers` | `report:read`, `report:approve` | `ROLE_REPORT_REVIEWER` | Không tự phê duyệt, có thể cần hạn mức |
| Group không được duyệt | Không cấp quyền ứng dụng | Không cấp role | Mặc định từ chối |

Đây là **quy ước minh họa**, không phải schema mặc định của Spring Security hay nhà cung cấp danh tính nào.

### 4.1. Ai chịu trách nhiệm cho mapping?

Nên có ít nhất ba ranh giới:

1. **IdP/nguồn danh tính:** xác minh user, cấp/quản lý nhóm, phát hành các claim đáng tin.
2. **Bộ ánh xạ ứng dụng:** chuyển group/role/scope được công nhận thành tập `GrantedAuthority` theo chính sách đã được duyệt.
3. **Bộ đánh giá nghiệp vụ:** dựa trên authority cùng tenant, chủ sở hữu, trạng thái, thời hạn và quan hệ tài nguyên để quyết định thao tác cụ thể.

Đừng cấp `ROLE_ADMIN` chỉ vì người dùng thuộc nhóm có tên `Administrators` của hệ điều hành hoặc một nhóm tenant khác. **Đặc quyền ứng dụng** cần sự phê duyệt riêng và phải gắn với ID nhóm/scope do hệ thống đã xác minh.

### 4.2. Quyền cuối cùng là phép hợp hay phép giao?

Nhiều hệ thống có thể hợp (union) quyền từ các nhóm được tin cậy:

```text
quyền_ứng_dụng = union(mapping(groupA), mapping(groupB), ...)
```

Nhưng đây chỉ là **tập quyền chức năng**. Quyết định thực tế có thể là phép giao:

```text
ALLOW =
  có authority cần thiết
  AND tài khoản còn hiệu lực
  AND thuộc tenant đang xử lý
  AND được phép trên resource cụ thể
  AND thỏa mãn điều kiện nghiệp vụ hiện tại
```

Nếu một nhóm được định nghĩa là **quyền cấm/phủ định**, hoặc hai role xung đột vì nguyên tắc phân tách nhiệm vụ, không thể hợp quyền rồi bỏ qua chính sách xung đột. Phải xác định thứ tự ưu tiên của deny, ràng buộc SoD và cách xử lý lỗi.

### 4.3. Phạm vi tenant không được mất khi chuyển thành authority

Xét hai tổ chức A và B cùng dùng hệ thống. Một người là người phê duyệt báo cáo tại A không mặc nhiên được duyệt báo cáo B. Nếu `ROLE_REPORT_REVIEWER` là authority toàn cục nhưng thực tế chỉ có hiệu lực trong A, phải giữ **tenant scope** ở lớp chính sách:

- Dùng mapping được tính theo tenant đã được xác thực.
- Hoặc cấp authority chức năng chung và luôn kiểm tra tenant ở tầng service/repository.
- Hoặc mô hình hóa quyền có phạm vi tường minh, ví dụ các bản ghi permission có cột tenant.

Đừng đặt tên tùy ý `ROLE_TENANT_A_REVIEWER` rồi tưởng rằng chỉ cần string matcher là đủ: đó mới là quy ước, vẫn phải kiểm tra tenant của tài nguyên trong server. Tenant ID trong header/body do client chọn phải được đối chiếu với quyền thành viên đáng tin.

## 5. Ví dụ Java 17 độc lập: ánh xạ nhóm an toàn

Trước khi dùng API Spring Security, nên thử logic ánh xạ bằng Java thuần. Ví dụ này mô phỏng **danh tính đã được phía máy chủ xác minh** cùng các group ID đáng tin, sau đó ánh xạ qua danh sách được duyệt. Nó không thực hiện kiểm tra mật mã của JWT; bước đó thuộc adapter xác thực thật.

Tạo file `IdentityAuthorityMappingDemo.java`:

```java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class IdentityAuthorityMappingDemo {
    private static final String TRUSTED_ISSUER =
        "https://id.example.test";

    private static final Map<String, Set<String>> GROUP_PERMISSIONS =
        Map.of(
            "g-report-viewers",
                Set.of("report:read"),
            "g-report-editors",
                Set.of("report:read", "report:update"),
            "g-report-approvers",
                Set.of("report:read", "report:approve")
        );

    // Trong sản phẩm thật, chỉ lớp xác thực đáng tin được tạo
    // dữ liệu này. Client không được tự gắn tokenValidated=true.
    record IdentityContext(
        String subject,
        String issuer,
        String tenantId,
        Set<String> groupIds,
        boolean active,
        boolean tokenValidated
    ) {}

    static Set<String> mapAuthorities(IdentityContext identity) {
        if (identity == null
                || !identity.tokenValidated()
                || !identity.active()
                || !TRUSTED_ISSUER.equals(identity.issuer())
                || identity.groupIds() == null) {
            return Set.of();
        }

        Set<String> authorities = new HashSet<>();
        for (String groupId : identity.groupIds()) {
            authorities.addAll(
                GROUP_PERMISSIONS.getOrDefault(groupId, Set.of())
            );
        }
        return Set.copyOf(authorities);
    }

    static boolean canReadReport(
            IdentityContext identity,
            String reportTenantId
    ) {
        return identity != null
            && reportTenantId != null
            && reportTenantId.equals(identity.tenantId())
            && mapAuthorities(identity).contains("report:read");
    }

    static void show(String label, Set<String> authorities) {
        System.out.println(label + ": " + new TreeSet<>(authorities));
    }

    public static void main(String[] args) {
        IdentityContext reader = new IdentityContext(
            "u-1", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-viewers"), true, true
        );
        IdentityContext editor = new IdentityContext(
            "u-2", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-viewers", "g-report-editors"),
            true, true
        );
        IdentityContext unknown = new IdentityContext(
            "u-3", TRUSTED_ISSUER, "tenant-A",
            Set.of("unknown-external-group"), true, true
        );
        IdentityContext inactive = new IdentityContext(
            "u-4", TRUSTED_ISSUER, "tenant-A",
            Set.of("g-report-approvers"), false, true
        );
        IdentityContext untrusted = new IdentityContext(
            "u-5", "https://fake.example.test", "tenant-A",
            Set.of("g-report-approvers"), true, true
        );

        show("reader", mapAuthorities(reader));
        show("editor", mapAuthorities(editor));
        show("unknown", mapAuthorities(unknown));
        show("inactive", mapAuthorities(inactive));
        show("untrusted issuer", mapAuthorities(untrusted));

        System.out.println(
            "same tenant: " + canReadReport(reader, "tenant-A")
        );
        System.out.println(
            "different tenant: " + canReadReport(reader, "tenant-B")
        );
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac IdentityAuthorityMappingDemo.java
java IdentityAuthorityMappingDemo
```

Kết quả chuẩn (stdout):

```text
reader: [report:read]
editor: [report:read, report:update]
unknown: []
inactive: []
untrusted issuer: []
same tenant: true
different tenant: false
```

Vì dùng `TreeSet` khi in, thứ tự quyền luôn xác định. Trường hợp unknown không tự biến thành admin; người bị vô hiệu hóa và nguồn không được tin không nhận quyền; người đọc không vượt tenant dù có `report:read`. Chú ý rằng `tokenValidated` chỉ **mô phỏng kết quả xác minh đã xảy ra trên server**. Không được cho client gửi cờ này, và không được cho rằng so sánh chuỗi issuer tương đương xác minh chữ ký/audience/hiệu lực token.

Bộ ánh xạ thật có thể bổ sung role `ROLE_REPORT_VIEWER`; ví dụ thuần Java dùng permission để người học thấy cơ chế rõ hơn. Quyền cuối cùng vẫn cần ràng buộc theo tài nguyên trong ứng dụng.

## 6. Ánh xạ trong Spring Security: từ dữ liệu tin cậy đến `GrantedAuthority`

Spring Security dùng `Authentication` để biểu diễn principal đã được xác thực và những `GrantedAuthority` liên quan. Cách đưa authority vào đối tượng này phụ thuộc **cơ chế xác thực đang sử dụng**.

### 6.1. Người dùng nội bộ với `UserDetailsService`

Ở hệ thống dùng tài khoản lưu tại database, một `UserDetailsService` hoặc thành phần xác thực tương ứng tải người dùng, trạng thái tài khoản và quyền hiệu lực. Sau khi xác thực thông tin đăng nhập, Spring Security có thể tạo `UsernamePasswordAuthenticationToken` chứa authorities từ `UserDetails` hoặc từ bước xử lý được cấu hình.

Ví dụ khái niệm:

```text
User row: userId=u-1, active=true
UserGroup rows: (u-1, g-report-editors)
ApplicationPolicy: g-report-editors -> report:read, report:update
UserDetails.getAuthorities():
  SimpleGrantedAuthority("report:read")
  SimpleGrantedAuthority("report:update")
```

Với role, Spring thường dùng chuỗi `ROLE_...`. Không lấy role từ trường form đăng nhập do người dùng tự nhập. Khi tài khoản bị khóa hoặc quyền đổi, cần chính sách phiên/cache để đảm bảo request sau đó phản ánh thay đổi đúng mức yêu cầu.

### 6.2. LDAP / Active Directory

LDAP có thể trả về DN, thuộc tính nhóm hoặc danh sách member; một bộ `AuthoritiesPopulator`/mapper có thể chuyển membership thành authorities. Phải xác định group DN/ID và quy tắc nhóm lồng nhau. Cùng tên `Developers` ở hai vùng thư mục khác nhau có thể không phải cùng group. Cũng cần kiểm tra trường hợp nhóm không được trả đủ, vòng lặp nhóm lồng nhau hoặc thư mục tạm thời không truy cập được.

Nếu không giải quyết được membership mà nó là điều kiện bắt buộc để cấp quyền, đừng coi “không tải được” là “được phép”. Có thể từ chối truy cập hoặc báo lỗi kỹ thuật phù hợp, tùy cơ chế phân quyền.

### 6.3. JWT Resource Server: scope mặc định khác group tùy biến

Với Resource Server dùng JWT, `JwtDecoder` chịu trách nhiệm xác thực token theo cấu hình. Sau đó `JwtAuthenticationConverter` chuyển `Jwt` thành một `Authentication`, và `JwtGrantedAuthoritiesConverter` thường ánh xạ các giá trị trong `scope` hoặc `scp` thành authority có tiền tố `SCOPE_`.

Ví dụ token đã được xác minh có:

```json
{
  "iss": "https://id.example.test",
  "sub": "u-2",
  "aud": ["report-api"],
  "scope": "reports.read",
  "groups": ["g-report-editors"]
}
```

Trong hành vi thông dụng, scope có thể thành `SCOPE_reports.read`. Claim `groups` **không tự động** biến thành `report:update` hay `ROLE_REPORT_EDITOR` nếu không có converter tùy chỉnh. Token minh họa trên cũng cố ý rút gọn các trường; ứng dụng thực phải kiểm tra chữ ký, thời hạn và mọi trường cần thiết.

#### Cấu hình minh họa với mapping allowlist

Đoạn mã sau là **cấu hình tích hợp Spring Boot 3 / Spring Security 6**, cần phụ thuộc OAuth2 Resource Server, `JwtDecoder` đáng tin và ứng dụng có cơ chế phân quyền dữ liệu cụ thể.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ReportAuthorizationConfig {
    // Khóa là group ID có nguồn gốc đáng tin, đã được duyệt.
    private static final Map<String, List<String>> GROUP_TO_AUTHORITIES =
        Map.of(
            "g-report-viewers",
                List.of("report:read", "ROLE_REPORT_VIEWER"),
            "g-report-editors",
                List.of("report:read", "report:update",
                        "ROLE_REPORT_EDITOR"),
            "g-report-approvers",
                List.of("report:read", "report:approve",
                        "ROLE_REPORT_REVIEWER")
        );

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> result = new ArrayList<>();

            // Giữ lại quyền scope đã xác minh, ví dụ SCOPE_reports.read.
            Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            // groups là claim tùy biến của IdP, không có mapping
            // mặc định; nhóm lạ không cấp thêm quyền.
            List<String> groups = jwt.getClaimAsStringList("groups");
            if (groups != null) {
                for (String group : groups) {
                    List<String> mapped =
                        GROUP_TO_AUTHORITIES.getOrDefault(
                            group, List.of()
                        );
                    for (String authority : mapped) {
                        result.add(
                            new SimpleGrantedAuthority(authority)
                        );
                    }
                }
            }
            return result;
        });
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("report:read")
            .requestMatchers(HttpMethod.PATCH, "/api/reports/**")
                .hasAuthority("report:update")
            .requestMatchers(HttpMethod.POST,
                    "/api/reports/*/approve")
                .hasAuthority("report:approve")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth -> oauth
            .jwt(jwt -> jwt.jwtAuthenticationConverter(
                jwtAuthenticationConverter()
            ))
        );
        return http.build();
    }
}
```

Giải thích từng phần:

1. Bộ chuyển scope mặc định được giữ lại, nên `SCOPE_reports.read` có thể tồn tại cùng các permission ứng dụng. Chúng **không có nghĩa như nhau** trừ khi chính sách ứng dụng quy định điều đó.
2. Claim `groups` được đọc từ JWT **đã qua bước xác thực** của resource server. Mỗi group chỉ được tra bảng `GROUP_TO_AUTHORITIES`; group không khớp không cấp quyền.
3. Bộ chuyển trả lại một collection của `GrantedAuthority`. Trong ứng dụng lớn, có thể khử trùng authorities và lưu mapping ở kho chính sách được quản lý phiên bản.
4. HTTP matcher chặn quyền theo thao tác. Đọc báo cáo, sửa báo cáo hay duyệt báo cáo vẫn phải kiểm tra tenant, chủ sở hữu và điều kiện nghiệp vụ tại tầng service/dữ liệu.
5. `anyRequest().denyAll()` chặn endpoint chưa được xem xét. Cấu hình minh họa không đề cập đăng nhập tương tác, CSRF hoặc CORS; lựa chọn phải phù hợp với kiến trúc xác thực thực tế.

**Không dùng nguyên mẫu mà bỏ qua chính sách trust.** Cần cấu hình issuer/audience đúng với token API; phân biệt token access và ID; xác minh IdP có phát hành claim nhóm trên access token hay không, claim ID nhóm dùng để mapping có ổn định và giới hạn trong tenant nào.

Ví dụ cấu hình khởi đầu cho Spring Boot có thể dùng `spring.security.oauth2.resourceserver.jwt.issuer-uri` để thiết lập issuer đáng tin. **Audience validation** phải được cấu hình/kiểm chứng theo hợp đồng API và phiên bản framework; chỉ có issuer hợp lệ chưa đủ để bảo đảm token dành cho resource server này. Nếu dùng nhiều issuer, phải có quy tắc trust và converter theo từng nguồn, tránh trộn dữ liệu từ các bên phát hành khác nhau.

### 6.4. OIDC login khác JWT Resource Server

Với `oauth2Login()`/OIDC login, Spring Security thường tạo một `OAuth2AuthenticationToken`, principal có thể là `OidcUser`. Dữ liệu nhóm/role có thể nằm trong ID token hoặc UserInfo, tùy IdP và scope đã xin. Việc ánh xạ có thể thực hiện bằng một `GrantedAuthoritiesMapper` hoặc một `OidcUserService` tùy chỉnh; không sao chép nguyên `JwtAuthenticationConverter` của Resource Server sang luồng đăng nhập OIDC rồi cho rằng nó sẽ được gọi.

Các bước cần làm khi dùng OIDC login:

1. Xác định issuer/provider, client, claims thực nhận trong ID token và UserInfo.
2. Ánh xạ nhóm/role được tin theo bảng allowlist.
3. Xây `OidcUser`/Authentication có authorities phù hợp và xác nhận principal, tenant.
4. Kiểm tra role trên HTTP/method và chính sách tài nguyên.
5. Thiết kế cơ chế làm mới/thu hồi quyền trong phiên đăng nhập; một quyền đã chụp vào session có thể không tự thay đổi ngay khi IdP sửa membership.

Không giả định `ROLE_ADMIN` có sẵn chỉ vì IdP gửi `roles:["admin"]`. Tên claim, nơi claim xuất hiện và quy tắc mapper phụ thuộc provider.

### 6.5. Spring Security chỉ nhìn thấy authorities cuối cùng

Sau khi xác thực, phần nhiều quy tắc như `hasAuthority`, `hasAnyAuthority`, `hasRole` hoặc `@PreAuthorize` sử dụng `Authentication.getAuthorities()`. Nếu bộ ánh xạ bỏ sót authority, người dùng sẽ bị từ chối dù nhóm trong IdP đúng; nếu ánh xạ quá rộng, ứng dụng sẽ cấp nhầm quyền.

Một câu hỏi chẩn đoán hữu ích là:

```text
IdP có nhóm/role?
  -> Claim hoặc UserDetails đã được lấy đúng chưa?
    -> Mapper có tra trúng group ID không?
      -> GrantedAuthority sinh ra có đúng chuỗi không?
        -> HTTP / method rule so khớp chuỗi đó không?
          -> Chính sách tài nguyên có cho phép không?
```

Không nên giải quyết mọi lỗi `403 Forbidden` bằng cách đổi `hasAuthority("report:approve")` thành `authenticated()`; việc này che đi lỗi mapping và mở rộng quyền quá mức.

## 7. Chính sách chống mở quyền sai từ role và group

### 7.1. Không đồng nhất nhóm ngoài với admin toàn cục

Một nhóm có tên `Administrators` có thể chỉ quản trị một máy, một tenant hoặc một hệ thống khác. Không cấp `ROLE_ADMIN` cho ứng dụng dựa trên so sánh tên hiển thị. Mapping phải dùng định danh nhóm ổn định, issuer đúng và, khi cần, tenant/realm của nhóm.

Ngay cả khi nhiều nguồn danh tính phát hành một group ID giống nhau, quyền của chúng vẫn không mặc nhiên giống nhau. Khóa mapping có thể phải gồm `(issuer, tenant, groupId)` thay vì chỉ `groupId`.

### 7.2. Không tin role/tenant từ HTTP request

Ví dụ sai:

```text
POST /api/documents/123/approve
X-Role: ADMIN
X-Tenant-Id: tenant-A
```

Nếu máy chủ dùng hai header này làm quyền, người gọi tự cấp quyền cho mình. Kể cả khi user chọn tenant trong giao diện, server phải xác minh membership và quyền tương ứng với tenant đã chọn rồi kiểm tra tài nguyên 123 thực thuộc tenant ấy.

### 7.3. Tránh tự suy diễn role từ email hoặc tên nhóm

Các quy tắc kiểu “email kết thúc bằng @company.com nên là ADMIN”, “group chứa chữ finance nên được phê duyệt”, “mọi tài khoản thuộc LDAP domain là manager” đều rủi ro cao. Danh tính, thuộc tính và nhóm không phải lời khẳng định quyền ứng dụng trừ khi **chính sách đã định nghĩa rõ** và **nguồn thực sự tin cậy**.

Email có thể thay đổi; một số thuộc tính có thể chưa được xác minh; tên nhóm có thể trùng hoặc đổi; nested groups có thể mở rộng vượt dự kiến. Nên dựa trên ID ổn định và mapping được kiểm toán.

### 7.4. Kiểm tra xung đột vai trò và phân tách nhiệm vụ

Hợp quyền từ nhiều group có thể tạo ra tổ hợp nguy hiểm: ví dụ quyền tạo yêu cầu lẫn quyền duyệt. Nếu nghiệp vụ yêu cầu phân tách nhiệm vụ, phải kiểm tra **tổ hợp quyền hiệu lực** khi cấp group và/hoặc điều kiện hành động trên mỗi bản ghi.

Quyền `request:approve` không đồng nghĩa “được tự duyệt”. Dù mapper đúng, tầng nghiệp vụ vẫn phải kiểm tra khác người tạo, cùng tenant, đúng trạng thái/hạn mức và quy trình phê duyệt.

## 8. Thời gian sống quyền, thu hồi, đồng bộ và cache

Ánh xạ đúng tại thời điểm đăng nhập không bảo đảm quyền còn đúng về sau. Ví dụ user bị chuyển khỏi nhóm `g-report-approvers` lúc 15:00 nhưng vẫn có access token chứa group cũ đến 15:30. Nếu resource server tin vào claim của token còn hiệu lực, quyền có thể tồn tại đến khi token hết hạn trừ khi có cơ chế cập nhật/thu hồi.

### 8.1. Mỗi nguồn có một độ trễ cập nhật

| Nơi lưu quyền | Điều làm quyền cập nhật | Rủi ro |
| --- | --- | --- |
| Role trong database tra cứu mỗi request | DB/chính sách đã cập nhật | Truy vấn chậm, cache sai hoặc DB lỗi |
| Authorities trong session | Làm mới session hoặc nạp lại quyền | Session còn giữ quyền cũ |
| Groups/roles trong JWT tự chứa | Token mới, hết hạn hoặc cơ chế revocation bổ sung | Token cũ tiếp tục chứa quyền trước khi thu hồi |
| LDAP group tra theo lịch hoặc cache | Đồng bộ/invalidate cache | Nested membership, dữ liệu cũ |
| API tra cứu quyền tập trung | Dịch vụ chính sách trả kết quả | Phụ thuộc hạ tầng và độ trễ |

Phải xác định yêu cầu **thời gian thu hồi tối đa** cho từng loại quyền, đặc biệt quyền admin, export hay thao tác tài chính. Với quyền nhạy cảm, cân nhắc token ngắn hạn, phiên được quản lý, kiểm tra quyền động, version quyền hoặc cơ chế thu hồi phù hợp. Không có một cách làm tối ưu cho mọi hệ thống.

### 8.2. Chính sách cache theo đúng phạm vi

Nếu quyết định phụ thuộc issuer, user, tenant, action, resource, thời điểm và phiên bản quyền, cache theo mỗi `userId` có thể dùng nhầm kết quả cho tenant hoặc tài nguyên khác. Cache phải xét đúng khóa ngữ cảnh và có thời hạn/invalidation phù hợp. Khi nguồn quyền không sẵn sàng, không được tự cho phép một hành động nhạy cảm vì “tạm không kiểm tra được”.

### 8.3. Cấp lại quyền và phiên bản chính sách

Việc đổi mapping `g-report-viewers` từ `report:read` thành `report:approve` là một **thay đổi chính sách phân quyền** dù không có ai thay nhóm trong IdP. Nó cần code review hoặc phê duyệt tương đương, kiểm thử quyền bị từ chối, ghi lịch sử phiên bản và cơ chế triển khai/rollback.

Nên tách rõ thao tác quản trị danh tính (thêm người vào nhóm) với thao tác quản trị chính sách (thay group thành permission). Một nhóm người kiểm soát được cả hai đường mà không có giám sát có thể tự nâng quyền.

## 9. Kiểm thử mapping theo chuỗi từ IdP đến API

Tối thiểu cần ba mức: kiểm tra bộ mapper, kiểm tra Spring Security nhận authorities đúng, và kiểm tra thao tác thực tế trên tài nguyên bị giới hạn đúng.

### 9.1. Ma trận unit test cho mapper

| Đầu vào từ nguồn | Authority kỳ vọng | Lý do |
| --- | --- | --- |
| Group được duyệt, nguồn đúng, tài khoản active | Các quyền được liệt kê trong mapping | Trường hợp hợp lệ |
| Group ID không biết | Không cấp quyền ứng dụng từ group đó | Mặc định từ chối |
| Claim nhóm không tồn tại | Không tự cấp role/permission từ group | Không đoán |
| Nhóm có tên tương tự admin | Không cấp admin nếu không đúng ID/mapping | Chống suy diễn tên |
| Issuer khác nhưng group ID giống | Không cấp quyền của issuer tin cậy | Chống trộn nguồn |
| Account inactive/bị khóa | Không được thực hiện hành động được bảo vệ | Kiểm tra trạng thái |
| User thuộc nhóm editor và viewer | Quyền chức năng hợp đúng theo chính sách | Mapping nhiều nhóm |
| User thuộc hai nhóm xung đột | Theo quy tắc conflict/SoD | Không hợp quyền mù |
| Claim nhóm sai định dạng | Bị từ chối hoặc không cấp quyền theo chính sách | Không tự parse tùy tiện |
| Tenant khác, cùng permission | Không có quyền đối tượng ngoài tenant | Scope kiểm tra ở nghiệp vụ |

### 9.2. Test converter JWT và test lớp xác thực riêng

Khi unit-test `JwtAuthenticationConverter` tùy chỉnh, có thể xây một đối tượng `Jwt` trong test với claims đã biết rồi gọi converter, so sánh tập `GrantedAuthority`. Test này **chỉ chứng minh mapping** và không kiểm tra chữ ký JWT.

Một bài test khác phải xác minh `JwtDecoder`/resource server từ chối token sai chữ ký, sai issuer, sai audience, hết hạn hoặc không được phát hành cho API. Không nhầm **token giả dùng trong test** với bằng chứng cấu hình xác thực thật đã an toàn.

Với `MockMvc` và `spring-security-test`, có thể mô phỏng principal/JWT cho test quyền URL; nhiều bộ hỗ trợ test bỏ qua bước decoder thật. Vì vậy phải tách ca test mapping, ca test HTTP authorization và ca test xác minh token thật ở tầng tích hợp tương ứng.

### 9.3. Test theo đường đi thực

Sau khi mapping đúng, thử cùng principal đọc/sửa/duyệt tài nguyên:

- Người có `report:read` được xem tài nguyên hợp lệ, không được sửa.
- Người có `report:update` không được sửa báo cáo ở tenant khác.
- Người có `report:approve` vẫn không được tự duyệt báo cáo của mình nếu quy trình cấm.
- Người bị gỡ khỏi group không tiếp tục được thao tác sau thời hạn thu hồi đã thiết kế.
- Endpoint chưa được khai báo phải bị `denyAll()` chặn.
- Export, batch job, message consumer và lời gọi service không có đường đi vòng qua chính sách.
- Khi thiếu dữ liệu IdP/policy, hệ thống không cho phép thao tác nhạy cảm.

Không chỉ kiểm tra mã HTTP 200/403/404; còn xác minh dữ liệu trả về có đúng phạm vi không và thao tác bị cấm có làm thay đổi dữ liệu/ghi sự kiện hay không. 403 cũng có thể đến từ CSRF, nên cần xác định đúng nguyên nhân của test.

### 9.4. Tình huống lỗi ánh xạ cần chẩn đoán

Nếu user bị 403 dù có nhóm hợp lệ, kiểm tra lần lượt:

1. **Token/đăng nhập:** đã được xác thực bằng issuer/audience đúng chưa?
2. **Claim:** nhóm nằm ở access token, ID token hay UserInfo? Có bị giới hạn danh sách hoặc đổi key không?
3. **Mapping:** group ID có đúng với bảng ánh xạ đang triển khai không?
4. **Authorities cuối:** `Authentication.getAuthorities()` chứa chuỗi gì? Có lỗi `ROLE_`/`SCOPE_` không?
5. **Rule:** `hasRole` hoặc `hasAuthority` yêu cầu đúng chuỗi đó không?
6. **Đối tượng:** tenant, ownership, trạng thái và chính sách nghiệp vụ có cho phép không?

Không ghi raw token vào log để điều tra. Có thể log ID tương quan, issuer đã xác minh, subject theo chính sách riêng tư, mã lý do mapping và kết quả deny; hạn chế dữ liệu nhóm nhạy cảm.

## 10. Những lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giả định claim `groups` tự thành `GrantedAuthority` | Có nhóm nhưng 403, hoặc mapper chạy sai | Tạo converter theo đúng luồng xác thực |
| Dùng `hasRole("ADMIN")` với authority `ADMIN` | Không khớp tiền tố `ROLE_` | Thống nhất convention role/authority |
| Nhầm `scope` với permission ứng dụng | Token có scope bị cấp chức năng quá rộng | Mapping cụ thể, kiểm tra client/audience |
| Nhận raw `X-Role` hoặc `tenantId` từ request | Client có thể nâng quyền | Dùng principal, claim và nguồn server đã xác minh |
| Mapping group bằng tên hiển thị hoặc substring | Đổi tên/trùng tên tạo quyền ngoài dự kiến | Dùng ID ổn định và allowlist |
| Không xét issuer/tenant trong mapping | Trộn group khác nguồn hoặc tenant | Ràng buộc nguồn và phạm vi |
| Chỉ kiểm tra authority khi đọc/sửa tài nguyên | Vượt quyền dữ liệu bằng cách đổi ID | Kiểm tra chính sách đối tượng và query |
| Giữ quyền quá lâu trong JWT/session | Thu hồi quyền không có hiệu lực kịp | Thiết kế TTL, refresh/revocation/quyền động |
| Coi quyền của nhiều group luôn có thể hợp | Vượt quy tắc SoD hoặc deny | Kiểm tra tổ hợp quyền hiệu lực |
| Dữ liệu IdP thiếu thì cấp quyền mặc định | Lỗi hạ tầng biến thành mở quyền | Fail closed với thao tác bảo vệ |
| Sửa mapping không có kiểm thử hồi quy | Nâng quyền ngoài ý muốn | Version mapping, kiểm thử ca deny |
| Test chỉ dùng JWT giả | Không phát hiện lỗi issuer/audience/chữ ký | Thêm kiểm thử xác thực token thật |
| Log cả JWT và thông tin định danh quá chi tiết | Rò rỉ dữ liệu/credential | Log mã lý do và định danh tối thiểu |

## 11. Bài tập củng cố

### Bài 1 — Phân biệt role và group

Cho dữ liệu: user U thuộc nhóm `g-report-editors`, token có scope `reports.read`; ứng dụng ánh xạ group này thành `report:update` và `ROLE_REPORT_EDITOR`. Hãy liệt kê authority dự kiến. Đáp án phụ thuộc mapping cụ thể; trong cấu hình ví dụ ở mục 6, có thể có `SCOPE_reports.read`, `report:read`, `report:update` và `ROLE_REPORT_EDITOR`. Giải thích vì sao `SCOPE_reports.read` không tự thay `report:read` khi rule kiểm tra exact string.

### Bài 2 — Thử mapping khi nhóm lạ

Chạy chương trình `IdentityAuthorityMappingDemo.java`, thêm một group ID tên `g-report-admins-copy` chưa có trong bảng mapping. Xác nhận không được cấp `report:approve` hay admin. Sau đó gán nhóm đã duyệt và kiểm tra chuỗi quyền được in đúng.

### Bài 3 — Tài nguyên khác tenant

Giữ nguyên `report:read` trong Authentication nhưng gọi báo cáo của tenant khác. Thiết kế unit test cho policy và test service/repository để chắc chắn không trả dữ liệu. Hỏi: vì sao đổi mapping trong token không đủ giải quyết lỗi này?

### Bài 4 — JWT hết hiệu lực quyền

Giả lập người dùng bị gỡ khỏi nhóm phê duyệt trong khi access token cũ còn hạn. Mô tả quyền còn hiệu lực đến lúc nào trong kiến trúc dùng JWT tự chứa, và đề xuất một cơ chế thu hồi phù hợp với yêu cầu rủi ro cao. Viết test cho thời điểm trước/sau khi thu hồi có hiệu lực.

### Bài 5 — Đổi mapping có kiểm soát

Giả sử muốn cho nhóm `g-report-viewers` quyền `report:approve`. Hãy lập phương án thay đổi: bên phê duyệt, kiểm tra xung đột role, test thiếu quyền, triển khai, giám sát và khả năng rollback. Giải thích vì sao đây là thay đổi bảo mật dù IdP không đổi membership.

## 12. Tự kiểm tra cuối bài

1. **Group có tự trở thành role Spring Security không?** Không. Cần xác định cách mapper đưa dữ kiện nguồn thành `GrantedAuthority`.
2. **`hasRole("EDITOR")` thường tìm authority nào?** `ROLE_EDITOR` trong cấu hình mặc định.
3. **Scope JWT và role ứng dụng có cùng nghĩa không?** Không bắt buộc. Scope biểu thị phạm vi ủy quyền của token, còn role/permission ứng dụng có quy ước và chính sách riêng.
4. **Có nên chấp nhận claim `roles` từ token chưa xác thực không?** Không. Phải xác thực token, issuer, audience và ràng buộc nguồn.
5. **Hai group khác issuer nhưng trùng ID có mặc nhiên cùng quyền không?** Không. Mapping phải xét nguồn/namespace cần thiết.
6. **Một người thuộc nhóm phê duyệt tenant A có được duyệt tài nguyên tenant B?** Không, trừ khi chính sách thật sự cấp quyền B và mọi điều kiện đều được xác minh.
7. **Thu hồi group trong IdP có luôn làm JWT cũ mất quyền ngay không?** Không. Phụ thuộc vòng đời token, session và cơ chế thu hồi.
8. **Khi ánh xạ đúng nhưng 403, nên làm gì?** Kiểm tra lần lượt xác thực, claim, mapping, authority cuối, rule và chính sách đối tượng; không mở toàn bộ API bằng `authenticated()`.

**Ghi nhớ:** nguồn danh tính xác nhận **ai là ai** và có thể cung cấp **người đó thuộc những nhóm/role nào**. Ứng dụng phải **ánh xạ những dữ kiện đã được xác minh thành authority đúng, có phạm vi**, rồi tiếp tục kiểm tra **điều kiện truy cập tài nguyên thực tế**. Mapping chỉ an toàn khi có nguồn tin cậy, bảng quy tắc tường minh, kiểm thử quyền bị từ chối và cơ chế cập nhật/thu hồi theo thời gian.