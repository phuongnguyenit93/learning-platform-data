# Phân biệt authentication với authorization trong Spring LDAP

Một người dùng nhập đúng mật khẩu LDAP chưa chắc được phép xem báo cáo lương, quản lý tài khoản hoặc truy cập dữ liệu của người khác. Hai quyết định đó thuộc về hai lớp bảo mật khác nhau:

- **Authentication (xác thực):** xác định người truy cập là ai và có chứng minh được danh tính đó hay không.
- **Authorization (phân quyền/ủy quyền truy cập):** quyết định danh tính đã xác thực được thực hiện hành động nào trên tài nguyên cụ thể.

Trong ứng dụng dùng **Spring LDAP**, xác thực thường dựa vào **LDAP bind**; thông tin về nhóm hoặc thuộc tính của directory có thể hỗ trợ phân quyền. Tuy nhiên, Spring LDAP là thư viện truy cập dịch vụ thư mục: nó không tự cấp quyền API, tạo session hoặc đưa role vào Spring Security chỉ vì LDAP bind thành công.

Bài học thuộc chương **Authentication** của module **SPRING_LDAP**. Nội dung tập trung vào ranh giới giữa xác thực bằng `ContextSource`/`LdapTemplate`, truy vấn nhóm và quyền của LDAP server, sau đó liên hệ cách Spring Security bảo vệ ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa authentication và authorization qua ví dụ đăng nhập thực tế.
2. Phân biệt **LDAP bind** với **LDAP Access Control List (ACL)** và quyền truy cập chức năng của ứng dụng.
3. Hiểu vì sao search bằng tài khoản dịch vụ không chứng minh người dùng cuối có quyền tương ứng.
4. Mô tả luồng tìm DN → user bind → đọc nhóm/quyền → kiểm tra truy cập tài nguyên.
5. Sử dụng `LdapTemplate.authenticate(...)` cho việc kiểm tra mật khẩu và `LdapTemplate.search(...)` để tra cứu dữ liệu liên quan đến phân quyền.
6. Nhận diện lỗi **privilege escalation**, **IDOR**, thông tin nhóm giả mạo, mật khẩu rỗng và phân quyền bị lỗi thời.
7. Thiết kế kiểm thử để chứng minh cả “chưa xác thực” lẫn “đã xác thực nhưng thiếu quyền” đều bị chặn đúng cách.

## 2. Authentication trả lời “bạn là ai?”

Trong hệ thống LDAP, một người dùng thường có entry dạng:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
~~~

Giả sử Lan đăng nhập vào ứng dụng bằng `uid=lan` và mật khẩu. Một luồng xác thực điển hình là:

1. Backend nhận username và mật khẩu qua **HTTPS**.
2. Dùng tài khoản dịch vụ LDAP có quyền search để tìm DN thực của entry `uid=lan`.
3. Từ chối kết quả không tìm thấy hoặc định danh mơ hồ (nhiều entry cùng tên).
4. Thử **user bind** tới LDAP bằng DN đã tìm và mật khẩu người dùng cung cấp, trên kết nối có TLS được xác minh.
5. Nếu máy chủ chấp nhận bind theo chính sách của nó, coi bước **xác thực credential LDAP** là thành công.
6. Tầng bảo mật ứng dụng tạo `Authentication`/principal và cơ chế duy trì phiên thích hợp sau khi kiểm tra thêm các điều kiện cần thiết.

**LDAP bind thành công không đồng nghĩa với người dùng được phép gọi mọi API.** Nó chứng minh server chấp nhận thông tin xác thực cho danh tính đã bind. Backend vẫn phải thực hiện các bước còn lại để tạo phiên được quản lý và ra quyết định truy cập.

### 2.1. Authentication có thể dựa vào gì?

| Bằng chứng | Ví dụ | Vai trò |
|---|---|---|
| Mật khẩu | User bind bằng DN và password | Xác minh thông tin xác thực LDAP |
| Chứng chỉ hoặc Kerberos | LDAP SASL hoặc cơ chế tích hợp riêng | Phương thức xác thực khác simple bind |
| Phiên đăng nhập hợp lệ | Cookie phiên đã được backend cấp và xác minh | Duy trì danh tính giữa các HTTP request |
| Access token hợp lệ | JWT được kiểm tra chữ ký, issuer, audience, expiry | Xác thực danh tính/ủy quyền dựa trên token theo thiết kế ứng dụng |

Lựa chọn phương thức xác thực nào còn tùy kiến trúc. Bài học dùng **simple bind qua TLS** làm ví dụ vì đây là kịch bản phổ biến của Spring LDAP.

### 2.2. Tìm thấy entry không phải đã xác thực

Nếu tìm thấy `uid=lan` bằng `LdapTemplate.search(...)`, ứng dụng chỉ biết entry tồn tại trong phạm vi và quyền tìm kiếm. Không được chấp nhận đăng nhập chỉ vì search có kết quả; người gửi request vẫn chưa chứng minh biết mật khẩu của Lan.

Tương tự, bind thành công bằng `cn=svc-ldap-reader,ou=system,dc=example,dc=org` chỉ xác thực **tài khoản dịch vụ của backend**. Đó không phải phiên user bind của Lan.

## 3. Authorization trả lời “bạn được làm gì?”

Sau khi ứng dụng đã xác thực Lan, các câu hỏi tiếp theo có thể là:

- Lan có được phép mở trang báo cáo nhân sự không?
- Lan có được xem **hồ sơ của chính mình** nhưng bị từ chối xem hồ sơ người khác không?
- Lan có thuộc nhóm được quản lý tài khoản hay không?
- Lan có được sửa entry LDAP ở nhánh `ou=people` hay chỉ đọc?

Các câu hỏi này không thể trả lời chỉ từ kết quả **bind = success**.

Authorization thường sử dụng một hoặc nhiều dữ kiện:

| Dữ kiện | Cách dùng | Giới hạn |
|---|---|---|
| Nhóm LDAP | Map `cn=report-readers,...` thành quyền `REPORT_READ` | Schema nhóm và cách suy ra membership tùy server |
| Thuộc tính tài khoản | `department`, `employeeType`, trạng thái | Thuộc tính có thể thay đổi, thiếu hoặc không đủ để quyết định |
| Vai trò ứng dụng | `ROLE_ADMIN`, `ROLE_STAFF` | Phải map từ nguồn đáng tin cậy và cập nhật theo chính sách |
| Chủ sở hữu tài nguyên | User A chỉ xem tài nguyên thuộc User A | Không thể xác định chỉ từ nhóm LDAP |
| Chính sách nghiệp vụ | Người phê duyệt chỉ xử lý hồ sơ thuộc phòng ban | Cần thông tin và kiểm tra ở tầng service/domain |

Ví dụ: Lan bind thành công nhưng không thuộc nhóm `report-readers`. Hệ thống nên xác nhận Lan đã đăng nhập, đồng thời **từ chối thao tác đọc báo cáo**. Đây là kết quả hoàn toàn bình thường: authentication thành công, authorization thất bại.

## 4. So sánh hai khái niệm

| Tiêu chí | Authentication | Authorization |
|---|---|---|
| Câu hỏi | Người dùng là ai? | Danh tính này có quyền làm việc được yêu cầu không? |
| Dữ liệu thường dùng | Credential, danh tính LDAP, session/token | Nhóm, role, ACL, quyền tài nguyên, policy |
| Ví dụ Spring LDAP | `LdapTemplate.authenticate(...)` | `LdapTemplate.search(...)` để tra nhóm hoặc thuộc tính |
| Ví dụ Spring Security | `AuthenticationManager`, authentication provider | `authorizeHttpRequests`, `@PreAuthorize`, kiểm tra quyền ở tầng service |
| Kết quả | Đã/không được xác thực | Được phép/bị từ chối hành động cụ thể |
| Thời điểm | Đăng nhập hoặc xác minh credential/request | Mỗi lần truy cập tài nguyên cần bảo vệ |
| Phụ thuộc vào | Cách xác minh credential | Chính sách cho danh tính và tài nguyên đang xét |
| Sai lầm điển hình | Tìm thấy entry rồi cho đăng nhập | Bind thành công rồi cho phép tất cả thao tác |

Một cách diễn đạt dễ nhớ: **authentication xác định chủ thể; authorization kiểm tra quyền của chủ thể đối với hành động và tài nguyên**. Với một request cần đăng nhập, authentication thường được kiểm tra trước authorization. Tuy nhiên, hệ thống cũng có thể có tài nguyên công khai được phép truy cập ẩn danh.

## 5. Hai lớp authorization trong hệ thống LDAP

Khi tích hợp Spring LDAP, cần phân biệt **quyền trên chính máy chủ LDAP** với **quyền trong ứng dụng**. Chúng bảo vệ những loại tài nguyên khác nhau.

### 5.1. LDAP ACL: ai được thao tác trên directory?

LDAP server kiểm tra quyền đối với các thao tác như:

- Search một vùng trong cây thư mục.
- Đọc/so sánh thuộc tính của entry.
- Thêm, sửa, xóa hoặc đổi tên entry.
- Xem cấu hình quản trị hoặc truy cập vùng nhạy cảm.

Quyền này dựa trên **danh tính đã bind trên kết nối** và ACL/chính sách của máy chủ. Cú pháp ACL, khả năng kế thừa và quyền cụ thể khác nhau giữa OpenLDAP, Active Directory và các implementation khác.

Ví dụ:

~~~text
Service DN: cn=svc-ldap-reader,ou=system,dc=example,dc=org
Allowed:    search/read uid, cn ở ou=people
Denied:     modify/delete entry, read userPassword

User DN:    uid=lan,ou=people,dc=example,dc=org
Allowed:    read một số thuộc tính theo ACL
Denied:     sửa entry của người khác
~~~

Nếu `LdapTemplate` dùng `ContextSource` đã cấu hình tài khoản dịch vụ, server áp ACL **của tài khoản dịch vụ** đối với các thao tác qua context đó. Không được ngầm cho rằng LDAP server sẽ tự áp ACL của người dùng cuối chỉ vì ứng dụng đã xác thực họ ở một bước khác.

### 5.2. Application authorization: ai được gọi API?

Ứng dụng Spring có thể có API:

~~~text
GET    /api/me
GET    /api/reports
POST   /api/users
GET    /api/users/{userId}
~~~

Việc LDAP cho phép tài khoản dịch vụ **search** hoặc **modify** entry không có nghĩa người dùng trên giao diện được phép gọi tương ứng `/api/users`. Ứng dụng phải đặt chính sách authorization cho endpoint và kiểm tra quyền trong lớp nghiệp vụ.

| Request | Authentication | Authorization ở ứng dụng |
|---|---|---|
| Chưa đăng nhập → `GET /api/reports` | Chưa có danh tính hợp lệ | Từ chối |
| Lan đã đăng nhập, chỉ có `PROFILE_READ` → `GET /api/reports` | Thành công | Từ chối vì thiếu `REPORT_READ` |
| Lan đã đăng nhập, có `REPORT_READ` → `GET /api/reports` | Thành công | Cho phép nếu các điều kiện khác cũng đạt |
| Lan đã đăng nhập → `GET /api/users/<id của người khác>` | Thành công | Cần kiểm tra quyền xem tài nguyên cụ thể, không dựa vào đăng nhập đơn thuần |
| Tài khoản dịch vụ LDAP có quyền modify | Đây là danh tính backend → LDAP | Không cấp quyền sửa dữ liệu cho người dùng web vì lý do đó |

Với HTTP, phản hồi thường là **401 Unauthorized** khi request thiếu hoặc không có xác thực hợp lệ và cần authentication, còn **403 Forbidden** khi request đã xác thực nhưng bị từ chối quyền. Tùy loại ứng dụng, Spring Security và cơ chế entry point/access denied handler có thể làm thay đổi cách trình bày phản hồi.

### 5.3. Rủi ro “confused deputy” với tài khoản dịch vụ

Giả sử backend dùng `svc-ldap-reader` có quyền đọc mọi hồ sơ. Nếu API `GET /api/users/{id}` chỉ lấy tham số `id` rồi dùng tài khoản dịch vụ đọc LDAP, người dùng đã đăng nhập có thể thay `id` và đọc dữ liệu của người khác.

LDAP server chỉ thấy **service DN có quyền đọc**, nên có thể chấp nhận search. Lỗi nằm ở **application authorization**, vì backend chưa kiểm tra người gọi được phép xem `id` đó hay không. Đây là dạng **Insecure Direct Object Reference (IDOR)** hoặc kiểm soát truy cập tới đối tượng không đầy đủ.

Biện pháp: kiểm tra quyền ở tầng nghiệp vụ với **principal đã xác thực** và **định danh tài nguyên đích** trước khi chạy truy vấn bằng service account. Không tin ID, role hoặc username do client tự khai là bằng chứng phân quyền.

## 6. Luồng xác thực rồi phân quyền hoàn chỉnh

Một kiến trúc phổ biến là:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Spring Security và ứng dụng
    participant Dir as LDAP server
    U->>App: Username + password qua HTTPS
    App->>Dir: Service bind và search user bằng filter an toàn
    Dir-->>App: DN của tài khoản
    App->>Dir: User bind bằng DN + password
    alt User bind không hợp lệ
        Dir-->>App: Từ chối xác thực
        App-->>U: Đăng nhập thất bại
    else User bind hợp lệ
        Dir-->>App: Bind thành công
        App->>Dir: Đọc nhóm/quyền bằng context được cấp phép
        Dir-->>App: Dữ liệu membership
        App->>App: Map nhóm thành authorities đáng tin cậy
        App-->>U: Tạo phiên/token theo chính sách
        U->>App: Gọi API được bảo vệ
        App->>App: Kiểm tra authority và quyền tài nguyên
        alt Đủ quyền
            App-->>U: Trả tài nguyên
        else Thiếu quyền
            App-->>U: Từ chối truy cập
        end
    end
~~~

Ở mỗi bước, loại bằng chứng có mục đích riêng:

1. **Search** giải quyết bài toán tìm DN. Username phải đi qua LDAP filter builder an toàn, ví dụ `LdapQueryBuilder`, và kết quả cần duy nhất.
2. **User bind** xác thực mật khẩu với máy chủ directory, không phải phép search/compare thuộc tính tùy ý.
3. **Tra nhóm/quyền** dựa trên danh tính đã xác thực hoặc DN được liên kết chắc chắn với danh tính đó.
4. **Map authorities** chuyển thông tin directory thành tên quyền mà ứng dụng hiểu, theo danh sách cho phép và chính sách tổ chức.
5. **Kiểm tra API/resource** được áp dụng khi truy cập; cần cả chính sách dựa trên role và điều kiện của tài nguyên nếu nghiệp vụ yêu cầu.

Không nên xem quá trình đọc nhóm như bằng chứng thay thế cho user bind. Một người có thể thuộc nhóm quản trị mà không đăng nhập được vì mật khẩu sai, tài khoản bị khóa hoặc cơ chế xác thực từ chối.

## 7. Ví dụ Spring LDAP: xác thực credential

Trong Spring Boot, có thể cấu hình `ContextSource` mặc định dùng tài khoản dịch vụ để tìm entry:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-ldap-reader,ou=system,dc=example,dc=org
    password: ${LDAP_READER_PASSWORD}
~~~

Các giá trị trên là minh họa; mật khẩu phải lấy từ biến môi trường hoặc secret manager. Cần thiết lập truststore và kiểm tra certificate/hostname cho kết nối TLS. Ví dụ giả định ứng dụng đã cấu hình dependency Spring LDAP tương ứng và inject được `LdapTemplate`.

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class LdapCredentialVerifier {

    private final LdapTemplate ldapTemplate;

    public LdapCredentialVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean verify(String username, String password) {
        if (username == null || username.isBlank()
                || username.length() > 128
                || password == null || password.isEmpty()) {
            return false;
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        // Search DN rồi bind để server kiểm tra mật khẩu người dùng.
        return ldapTemplate.authenticate(query, password);
    }
}
~~~

Ví dụ trên chỉ thực hiện phần **credential verification**:

- `base("ou=people")` tương đối với `spring.ldap.base=dc=example,dc=org`.
- `where(...).is(username)` đặt username làm giá trị literal được escape an toàn theo LDAP filter.
- `ldapTemplate.authenticate(query, password)` là thao tác xác thực theo query và user bind. Kết quả trả về không chứa role/quyền ứng dụng.
- Phải xử lý tình huống cùng username khớp nhiều entry, dịch vụ LDAP lỗi và giới hạn truy cập trong kiến trúc thực tế. Ví dụ không tự triển khai toàn bộ xác thực của Spring Security.
- Không đọc `userPassword` về ứng dụng để tự so sánh hash nếu LDAP server đã cung cấp cơ chế bind xác thực phù hợp.

**Lưu ý:** Không viết HTTP controller theo kiểu “nếu `verify(...)` trả true thì mọi API đều được gọi”. Trong web app có Spring Security, cần tích hợp quy trình này vào authentication provider/manager phù hợp để tạo một `Authentication` hợp lệ và áp dụng authorization ở các điểm được bảo vệ.

## 8. Ví dụ Spring LDAP: lấy quyền từ nhóm

Sau khi người dùng được xác thực, ứng dụng có thể tra nhóm LDAP để suy ra quyền. Một mô hình thường gặp với OpenLDAP là nhóm dạng `groupOfNames` chứa thuộc tính `member` trỏ tới DN thành viên:

~~~ldif
dn: cn=report-readers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: report-readers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Giả định tổ chức định nghĩa: thành viên của **đúng nhóm** `cn=report-readers,ou=groups,dc=example,dc=org` được cấp authority `REPORT_READ`. Không cho phép mọi nhóm có tên gần giống hoặc do người dùng tự nhập đều sinh ra quyền.

Một cách tra membership với `LdapTemplate`:

~~~java
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class LdapReportGroupLookup {

    private final LdapTemplate ldapTemplate;

    public LdapReportGroupLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // authenticatedUserDn phải đến từ lookup LDAP đã xác thực,
    // không được lấy nguyên vẹn từ request do client gửi.
    public boolean belongsToReportReaders(String authenticatedUserDn) {
        if (authenticatedUserDn == null || authenticatedUserDn.isBlank()) {
            return false;
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("cn=report-readers,ou=groups")
                .searchScope(SearchScope.OBJECT)
                .attributes("cn")
                .where("objectClass").is("groupOfNames")
                .and("member").is(authenticatedUserDn);

        return !ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString()
        ).isEmpty();
    }
}
~~~

**Điều kiện để dùng ví dụ đúng:**

1. `authenticatedUserDn` phải được xác định bằng tra cứu đáng tin cậy sau khi đã xác thực tài khoản tương ứng; không nhận một DN tùy ý do browser gửi lên.
2. Search chỉ nhắm tới **một DN nhóm đã cấu hình cố định**, với scope `OBJECT`. Đây là ví dụ cho quyền `REPORT_READ`, không phải bộ phân giải toàn bộ nhóm trong hệ thống.
3. Filter so sánh `member` với DN đã xác định, dựa trên cách biểu diễn nhóm `groupOfNames`; không tự giả định mọi LDAP server dùng cùng cấu trúc.
4. Tài khoản dịch vụ phải có ACL cho phép tìm/đọc thông tin nhóm cần dùng. Nếu không đủ quyền hoặc LDAP lỗi, không được mặc nhiên cấp quyền.
5. Kết quả `true` là **dữ kiện để map thành authority**; bản thân phương thức này không tạo `GrantedAuthority`, `SecurityContext` hay HTTP session.

Các hệ thống khác có thể dùng `groupOfUniqueNames/uniqueMember`, thuộc tính `memberOf`, nhóm lồng nhau, hoặc cơ chế riêng như Active Directory. Cần kiểm tra schema, matching rule, cách đồng bộ nhóm và cách giải quyết nested membership trước khi sử dụng trong production. Nếu không biết cách map hợp lệ, ứng dụng nên **từ chối quyền tương ứng** cho tới khi có dữ kiện đáng tin cậy.

### 8.1. Quy tắc map nhóm thành authority

| Nhóm LDAP được xác minh | Authority trong Spring Security | Quyền ứng dụng |
|---|---|---|
| `cn=report-readers,ou=groups,dc=example,dc=org` | `REPORT_READ` | Xem báo cáo được cấp phép |
| `cn=directory-support,ou=groups,dc=example,dc=org` | `USER_SUPPORT` | Chức năng hỗ trợ tài khoản theo phạm vi |
| Không thuộc nhóm được khai báo | Không thêm quyền từ LDAP | Chỉ nhận các quyền mặc định nếu chính sách cho phép |

Đây chỉ là **mapping minh họa do ứng dụng định nghĩa**. Không nên tự biến mọi giá trị `cn` lấy từ directory thành role quản trị hoặc giữ nguyên chuỗi nhóm do client gửi lên. Phải có danh sách mapping được kiểm soát và kiểm tra quyền thực sự trên tài nguyên.

## 9. Spring Security thực thi authorization ở đâu?

Spring Security có thể chặn request ở HTTP filter chain, tại phương thức service/controller hoặc cả hai. Ví dụ sau **giả định** authentication đã được tích hợp đúng và principal hiện tại có authorities lấy từ nguồn đáng tin cậy.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "Du lieu bao cao"; // Minh họa, không có dữ liệu thực.
    }
}
~~~

Để `@PreAuthorize` hoạt động, ứng dụng cần bật method security, chẳng hạn với Spring Security hỗ trợ `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

**Điểm thiết kế quan trọng:** Spring Security phải nhận một `Authentication` hợp lệ kèm authority `REPORT_READ` từ cơ chế tích hợp LDAP đã được kiểm chứng. Ví dụ `LdapCredentialVerifier.verify(...)` và `LdapReportGroupLookup.belongsToReportReaders(...)` chỉ là các thành phần chức năng; chúng chưa tự tạo `Authentication` cho Spring Security. Với ứng dụng sử dụng Spring Security LDAP, có thể cân nhắc bộ xác thực LDAP và thành phần nạp authorities phù hợp phiên bản, hoặc một integration tự triển khai có kiểm thử đầy đủ.

Nếu cần chính sách **chủ sở hữu tài nguyên**, kiểm tra role chung vẫn chưa đủ:

~~~java
// Mô tả quy tắc nghiệp vụ, không phải toàn bộ implementation.
// Người dùng có PROFILE_READ chỉ được xem hồ sơ mình sở hữu;
// người có USER_SUPPORT cần được giới hạn phạm vi theo chính sách.
boolean mayReadProfile =
        authorities.contains("PROFILE_READ")
        && principalUserId.equals(requestedProfileOwnerId);
~~~

Trong thực tế, nên thực hiện kiểm tra trên đối tượng tài nguyên thực sự và dữ liệu chủ sở hữu từ **nguồn đáng tin cậy ở backend**. Tránh so sánh hai chuỗi cùng lấy từ request rồi tưởng đã phân quyền.

## 10. Các tình huống dễ nhầm lẫn

### 10.1. “Bind đúng mật khẩu là được quyền admin”

**Sai.** Bind chỉ xác thực danh tính. Nếu ứng dụng có role quản trị, role đó phải được cấp dựa trên chính sách và nguồn thông tin phân quyền tin cậy. Việc LDAP cho phép entry `uid=lan` bind không nói gì về quyền `USER_ADMIN` trong ứng dụng.

### 10.2. “Service account LDAP có quyền sửa là người dùng cũng có quyền sửa”

**Sai.** Backend có thể dùng một service account đủ quyền để thực hiện tác vụ theo yêu cầu hợp lệ. LDAP server xét ACL của service account, còn backend **phải tự xét** người dùng đang gọi API có được phép yêu cầu tác vụ đó hay không. Nên thu hẹp quyền service account và tránh dùng tài khoản quản trị toàn thư mục cho các nghiệp vụ thông thường.

### 10.3. “Nhìn thấy `memberOf` thì đã xác thực”

**Sai.** Đọc được thuộc tính nhóm chỉ cho biết thông tin về entry. Không có chuyện thuộc tính `memberOf` tự chứng minh người gọi sở hữu tài khoản. Cần xác thực trước và liên kết chính xác danh tính đã xác thực với entry được tra nhóm.

### 10.4. “Không thấy nhóm nghĩa là chắc chắn người dùng không có nhóm”

Không hẳn. Search có thể bị chặn bởi ACL, scope sai, schema khác hoặc chưa xét nhóm lồng nhau. Ứng dụng cần **không cấp quyền** khi không có bằng chứng đáng tin cậy; đồng thời phân biệt “không thuộc nhóm” với “lỗi truy vấn/quyền truy vấn” trong log và giám sát.

### 10.5. “Đã kiểm tra role khi đăng nhập thì đủ”

Không phải lúc nào cũng đủ. Membership và policy có thể thay đổi sau khi session/token được cấp. Quyền đã lưu trong phiên hoặc JWT có thể bị **cũ** cho tới khi phiên hết hạn hoặc quyền được làm mới. Với hệ thống nhạy cảm, cân nhắc TTL ngắn, cơ chế thu hồi, cập nhật authority hoặc kiểm tra bổ sung khi thực hiện thao tác quan trọng.

### 10.6. “LDAP ACL thay thế hoàn toàn bảo mật ứng dụng”

Không. LDAP ACL chỉ bảo vệ **thao tác LDAP thực sự đi tới server**, theo danh tính của connection. Ứng dụng có thể còn dữ liệu SQL, cache, file, API khác và quy tắc nghiệp vụ phức tạp; những tài nguyên này cần chính sách authorization tương ứng.

## 11. Nguyên tắc an toàn cần áp dụng

1. **Authentication và authorization độc lập về quyết định.** Khi chưa có danh tính được xác thực, không cấp quyền yêu cầu đăng nhập; khi đã xác thực nhưng thiếu quyền, vẫn từ chối thao tác.
2. **Dùng user bind để xác thực credential LDAP.** Không coi kết quả LDAP search hoặc service bind là xác thực của người dùng cuối.
3. **Dùng LDAP filter builder để tìm user/nhóm.** Không nối dữ liệu request trực tiếp vào filter; dùng `LdapQueryBuilder`/`EqualsFilter` và giới hạn base/scope.
4. **Giữ danh tính nhất quán.** Username, DN, principal và ánh xạ group phải gắn với cùng một tài khoản duy nhất, tránh nhầm giữa các OU hoặc miền.
5. **Giới hạn quyền service account.** Chỉ cấp search/read cần thiết, không lạm dụng tài khoản admin LDAP để phục vụ endpoint thường ngày.
6. **Thực thi authorization ở backend.** Kiểm tra trên API/service và trên tài nguyên thực; không coi nút bị ẩn ở frontend là kiểm soát quyền.
7. **Áp dụng nguyên tắc fail closed.** Khi thiếu dữ liệu phân quyền, gặp lỗi tra nhóm hoặc kết quả mơ hồ, không tự động cấp quyền.
8. **Bảo vệ kết nối và credential.** Dùng HTTPS phía client; dùng LDAPS/StartTLS có xác minh chứng chỉ giữa Spring và LDAP; từ chối password rỗng trước khi bind.
9. **Kiểm soát vòng đời authority.** Định nghĩa lúc nạp quyền, thời điểm refresh và cách xử lý session/token khi nhóm đổi.
10. **Ghi log phù hợp.** Theo dõi lỗi xác thực, quyền bị từ chối và lỗi directory riêng; không ghi mật khẩu, token, hash hoặc thông tin nhạy cảm không cần thiết.

## 12. Thực hành phân biệt hai bước

Giả sử directory thử nghiệm có:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan       (mật khẩu đúng, thuộc report-readers)
│   └── uid=minh      (mật khẩu đúng, không thuộc report-readers)
└── ou=groups
    └── cn=report-readers
~~~

Ứng dụng có API `GET /api/reports` yêu cầu `REPORT_READ` và API `GET /api/me` cho người đã đăng nhập.

**Bước 1 — Xác thực:** thử user bind bằng `uid=lan` với mật khẩu đúng và sai. Đảm bảo chỉ credential đúng mới được coi là xác thực thành công.

**Bước 2 — Ánh xạ quyền:** chỉ sau khi xác thực thành công, đọc nhóm tương ứng với DN đã xác định. Map đúng nhóm `report-readers` thành `REPORT_READ`.

**Bước 3 — Kiểm tra authorization:** cho Lan gọi `/api/reports` và cho Minh gọi cùng API. Cả hai có thể đăng nhập thành công, nhưng chỉ Lan được quyền báo cáo trong dữ liệu thử nghiệm đã mô tả.

**Bước 4 — Kiểm tra trên tài nguyên:** thử đọc hồ sơ của một người khác dù đã đăng nhập. Bảo đảm kiểm tra chủ sở hữu hoặc quyền hỗ trợ cho tài nguyên đó.

### 12.1. Ma trận kiểm thử

| Tình huống | Authentication | Authorization/kết quả kỳ vọng |
|---|---|---|
| Không có phiên/token hợp lệ, gọi API bảo vệ | Thất bại/chưa có | Từ chối; HTTP thường là `401` |
| Lan nhập sai mật khẩu | Thất bại | Không cấp phiên/role dựa trên tài khoản Lan |
| Lan nhập đúng mật khẩu, thuộc `report-readers` | Thành công | Có `REPORT_READ` theo mapping, cho xem báo cáo nếu thỏa policy khác |
| Minh nhập đúng mật khẩu nhưng không thuộc nhóm | Thành công | Bị từ chối báo cáo, thường là `403` |
| Lan nhập đúng mật khẩu nhưng cố đọc tài nguyên của người khác | Thành công | Từ chối nếu không có quyền trên đối tượng đó |
| Client tự gửi header `X-Role: ADMIN` | Không đổi bằng chứng xác thực | Bỏ qua role tự khai; không tự cấp quyền |
| Service bind LDAP thành công nhưng user bind sai | Người dùng thất bại | Không cấp quyền dù tài khoản dịch vụ tìm được entry |
| Search nhóm bị từ chối do ACL hoặc LDAP offline | Có thể đã xác thực | Không cấp quyền dựa trên nhóm chưa xác minh; ghi nhận sự cố |
| Có hai entry LDAP cùng `uid` | Danh tính mơ hồ | Không chọn entry bất kỳ để cấp quyền |
| Mật khẩu rỗng | Chặn trước bind | Không tạo phiên |
| Nhóm bị thu hồi khi session còn hiệu lực | Credential có thể vẫn hợp lệ | Quyền được cập nhật theo cơ chế refresh/thu hồi đã thiết kế |
| Thử gọi API không được bảo vệ bởi annotation/filter | Có thể đã xác thực | Phải có kiểm tra quyền bổ sung; test phát hiện lỗ hổng |

Trong kiểm thử Spring Security, nên có cả test cho **người chưa đăng nhập**, **người đã đăng nhập nhưng thiếu authority** và **người đủ authority nhưng không sở hữu tài nguyên**. Tùy cấu hình bảo mật, dùng các bài test tích hợp HTTP hoặc method security phù hợp; không cần kết nối LDAP thật để kiểm tra toàn bộ điều kiện authorization nếu có principal và authorities giả lập đáng tin cậy trong test.

### 12.2. Câu hỏi tự kiểm tra

1. Nếu `LdapTemplate.authenticate(...)` trả `true`, người dùng có được quyền gọi `POST /api/users` ngay không?
2. ACL của LDAP server đang xét danh tính nào khi `LdapTemplate` dùng tài khoản `svc-ldap-reader` để search?
3. Nếu user bind sai nhưng search thấy entry thuộc nhóm `report-readers`, có được cấp `REPORT_READ` không?
4. Hai người đều bind thành công nhưng chỉ một người thuộc `report-readers`. Vì sao kết quả mở báo cáo khác nhau?
5. Vì sao kiểm tra `@PreAuthorize("hasAuthority('REPORT_READ')")` chưa chắc ngăn được việc đọc nhầm dữ liệu của người khác?
6. Điều gì có thể xảy ra khi người dùng đã bị xóa khỏi nhóm nhưng token mang role cũ vẫn chưa hết hạn?

**Gợi ý trả lời:** (1) Không; cần authorization cụ thể. (2) ACL xét service DN đã bind trên kết nối. (3) Không; chưa xác thực người dùng. (4) Khác nhau về quyền được map. (5) Cần kiểm tra tài nguyên và chủ sở hữu, ngoài role. (6) Quyền cũ có thể còn hiệu lực theo TTL/chính sách refresh và cần cơ chế thu hồi phù hợp.

## Kết luận

**Authentication** trong Spring LDAP thường xác minh danh tính bằng **user bind** sau khi tìm DN, còn **authorization** xác định những hành động và tài nguyên mà danh tính đó được phép truy cập. LDAP server tự áp ACL cho các thao tác LDAP theo danh tính đã bind, trong khi **ứng dụng Spring và Spring Security** phải kiểm tra quyền truy cập API và nghiệp vụ của người dùng cuối. Thiết kế đúng cần tách rõ service bind, user bind, group/authority mapping và kiểm tra quyền trên từng tài nguyên; kết quả đăng nhập thành công không tự động trao đặc quyền.
