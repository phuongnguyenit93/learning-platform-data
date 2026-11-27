# Hồ sơ hoàn chỉnh: mô hình DIT, truy vấn, bảo mật, kiểm thử và vận hành với Spring LDAP

Một ứng dụng kết nối được LDAP và tìm thấy một tài khoản chưa có nghĩa là hệ thống đã sẵn sàng vận hành. Để xây dựng giải pháp thực tế, chúng ta phải thiết kế **Directory Information Tree (DIT)**, chọn schema và định danh, viết truy vấn an toàn, kiểm soát quyền truy cập, bảo vệ mật khẩu và kết nối, kiểm thử lỗi, rồi chuẩn bị giám sát và quy trình khôi phục.

Bài thực hành tổng hợp này đưa các kiến thức của module **SPRING_LDAP** vào một hồ sơ triển khai xuyên suốt. Tình huống là xây dựng **dịch vụ danh bạ nhân viên** bằng Spring Boot và Spring LDAP: backend tìm nhân viên theo `uid`, hiển thị thông tin cần thiết, xác thực đăng nhập qua LDAP khi được yêu cầu, tra nhóm để hỗ trợ phân quyền, và có khả năng cập nhật một số thuộc tính theo chính sách.

Đây là **môi trường giả định dùng cho học tập**, không phải cấu hình áp dụng nguyên xi cho mọi LDAP server. Những phần phụ thuộc OpenLDAP, Active Directory, ACL, schema, StartTLS, transaction và connection pooling đều phải được xác minh trên sản phẩm và phiên bản thực tế.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau khi học xong, bạn có thể:

1. Đề xuất một DIT có phân vùng người dùng, nhóm và tài khoản kỹ thuật; giải thích cách chọn base DN, RDN và search scope.
2. Thiết kế ánh xạ giữa entry LDAP và domain object Java mà không làm lộ các thuộc tính nhạy cảm.
3. Sử dụng `LdapQueryBuilder`, `LdapTemplate` và `ContextMapper` để truy vấn, đọc và cập nhật entry trong phạm vi cho phép.
4. Phân biệt service bind, user bind, authentication và authorization; kiểm soát quyền bằng LDAP ACL và ở tầng Spring Security.
5. Cấu hình LDAPS hoặc StartTLS với kiểm tra CA, certificate chain và hostname; quản lý secrets, timeout và pooling.
6. Viết kế hoạch unit test, integration test, security test và failure test để kiểm chứng cả hành vi bình thường và trường hợp lỗi.
7. Xây dựng runbook triển khai, giám sát, thay đổi chứng chỉ, xử lý sự cố, backup/restore và rollback.

**Tiêu chí đạt:** một bản thiết kế DIT/schema có lý do; các truy vấn chỉ lấy dữ liệu cần thiết; không cho LDAP filter injection; account có quyền tối thiểu; mật khẩu không đi trên kênh plaintext; có kiểm thử phát hiện trùng định danh và lỗi TLS/ACL; có kế hoạch vận hành khi LDAP không khả dụng.

## 2. Bối cảnh hệ thống và kiến trúc tham chiếu

Nhân viên đăng nhập qua cổng nội bộ. Các chức năng:

- **Tra cứu:** tìm nhân viên theo `uid` hoặc email, xem tên và một số thông tin danh bạ đã được phép công bố.
- **Xác thực:** kiểm tra mật khẩu người dùng bằng LDAP user bind, không đọc password hash về backend.
- **Phân quyền:** chỉ người có authority `DIRECTORY_READ` mới gọi API tra cứu; thao tác cập nhật cần quyền riêng và quy tắc nghiệp vụ.
- **Quản lý hồ sơ:** nhóm vận hành được cấp phép có thể cập nhật `telephoneNumber` hoặc `description` cho entry được phê duyệt.
- **Vận hành:** khi LDAP chậm, TLS lỗi, account bị khóa hoặc server failover, ứng dụng cần có log, metric, cảnh báo và hành vi an toàn.

### 2.1. Luồng thành phần

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"HTTPS"| API["Spring Security + REST API"]
    API --> SVC["Directory Service"]
    SVC --> REPO["Repository dùng LdapTemplate"]
    REPO -->|"LDAPS / StartTLS"| LDAP["LDAP server / cluster"]
    API --> AUTH["LDAP Authentication Provider"]
    AUTH -->|"User bind qua TLS"| LDAP
    LDAP --> DIT["DIT: people / groups / system"]
    SVC --> OBS["Log, metrics, tracing"]
    AUTH --> OBS
~~~

**Phân chia trách nhiệm:**

| Lớp | Nhiệm vụ | Không nên làm |
|---|---|---|
| Controller/API | Validate input, trả DTO, xử lý HTTP status | Ghép filter LDAP từ request; đưa thẳng LDAP context ra response |
| Spring Security | Xác thực request và kiểm tra authority/quyền tài nguyên | Coi chỉ cần tìm thấy DN là đã đăng nhập |
| Directory service | Quy tắc nghiệp vụ, uniqueness, dữ liệu được hiển thị/cập nhật | Bỏ qua kiểm tra quyền vì service account đọc được LDAP |
| Spring LDAP repository | Dựng query, map entry, thao tác LDAP có phạm vi | Tự cấp quyền HTTP hoặc quản lý session |
| LDAP server | Lưu DIT/schema, thực thi bind, ACL, search và thay đổi entry | Hiểu các chính sách nghiệp vụ của toàn bộ ứng dụng |
| Vận hành/PKI | TLS, secret, backup, alert, capacity và incident | Tắt certificate validation để xử lý sự cố |

## 3. Thiết kế Directory Information Tree (DIT)

DIT là cây các entry; mỗi entry có **Distinguished Name (DN)** duy nhất trong cây. Một DN gồm các thành phần Relative Distinguished Name (RDN), chẳng hạn `uid=lan`, `ou=people` và `dc=example`.

### 3.1. DIT đề xuất

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=contractors
│       └── uid=ngoc
├── ou=groups
│   ├── cn=directory-readers
│   └── cn=directory-editors
└── ou=system
    ├── cn=svc-directory-read
    └── cn=svc-directory-write
~~~

Ví dụ DN đầy đủ:

~~~text
uid=lan,ou=people,dc=example,dc=org
uid=ngoc,ou=contractors,ou=people,dc=example,dc=org
cn=directory-readers,ou=groups,dc=example,dc=org
cn=svc-directory-read,ou=system,dc=example,dc=org
~~~

Lý do tách các nhánh:

| Nhánh | Mục đích | Quyền đề xuất |
|---|---|---|
| `ou=people` | Entry nhân viên và hợp đồng | Service read chỉ tìm/đọc attribute cần thiết |
| `ou=groups` | Nhóm dùng để cấp quyền ứng dụng | Group lookup chỉ đọc membership phù hợp |
| `ou=system` | Account kỹ thuật, cấu hình riêng | Không cho người dùng thường xem credential hoặc quản lý |
| `ou=contractors,ou=people` | Phân vùng người dùng hợp đồng | Có thể áp ACL/search scope riêng theo chính sách |

**Base DN không phải bind DN.** `dc=example,dc=org` là gốc truy vấn; `cn=svc-directory-read,ou=system,dc=example,dc=org` là danh tính kết nối. Đổi base DN không có nghĩa tự đổi account hoặc quyền.

### 3.2. Chọn định danh ổn định

Ví dụ dùng `uid` làm RDN vì thuận tiện học tập, nhưng trong production cần xác định:

- `uid` có duy nhất trong vùng người dùng không, kể cả OU con?
- Username có thể đổi khi nhân viên đổi tên hoặc hợp nhất tài khoản không?
- Nếu một entry chuyển OU, DN đổi; ứng dụng có phụ thuộc DN như khóa dữ liệu dài hạn không?
- Có thuộc tính ID bất biến do directory quản lý phù hợp hơn (ví dụ `entryUUID` trong một số triển khai hoặc `objectGUID` của Active Directory) không?
- Với LDAP nhiều domain hoặc AD, `userPrincipalName`/`sAMAccountName` có quy tắc duy nhất và tìm kiếm khác nhau.

**Không mặc định DN là khóa bất biến.** DN phụ thuộc vị trí entry và có thể thay đổi khi rename/move. Với dữ liệu nghiệp vụ cần tham chiếu ổn định, hãy chọn identifier bền vững do hệ thống thực tế cung cấp và quản lý cách đồng bộ sau thay đổi.

### 3.3. Schema và thuộc tính

Ví dụ hồ sơ nhân viên với schema `inetOrgPerson`:

| Attribute | Ý nghĩa | Yêu cầu của domain | Ghi chú bảo mật |
|---|---|---|---|
| `uid` | Tên tài khoản | Bắt buộc cho lookup | Chỉ dùng như identifier sau khi kiểm tra tính duy nhất |
| `cn` | Tên hiển thị | Bắt buộc | Có thể chứa Unicode |
| `sn` | Họ | Bắt buộc theo schema `person` kế thừa | Không đồng nhất với full name |
| `mail` | Email | Tùy chọn | Có thể đa giá trị và không duy nhất |
| `telephoneNumber` | Điện thoại | Tùy chọn | Có thể là dữ liệu cá nhân; cân nhắc quyền đọc |
| `description` | Ghi chú nghiệp vụ | Tùy chọn | Không chứa secret/password |
| `userPassword` | Thuộc tính credential trong một số schema | Không lấy về domain | Không cấp quyền đọc để phục vụ lookup thông thường |

LDIF mẫu dùng trong phòng lab:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
description: active-directory-demo

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Le
sn: Le
~~~

LDIF này chỉ là **mẫu dữ liệu tối thiểu**. Người học phải tạo sẵn các OU gốc, nhóm, account và dữ liệu bằng công cụ quản trị có quyền trong môi trường test; không sao chép từ production. Nếu schema/ACL của directory không hỗ trợ một attribute, cần điều chỉnh dữ liệu theo chính sách server thay vì vô hiệu hóa schema checking.

### 3.4. Nhóm và membership

Nhóm ví dụ dùng `groupOfNames` với `member` chứa DN của thành viên:

~~~ldif
dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=directory-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: directory-readers
member: uid=lan,ou=people,dc=example,dc=org
~~~

`groupOfNames` yêu cầu ít nhất một `member` theo schema tiêu chuẩn, vì vậy ví dụ có thành viên cụ thể. Các directory khác có thể sử dụng `groupOfUniqueNames`/`uniqueMember`, `memberOf` hoặc nhóm lồng nhau; không tự áp dụng cấu trúc này cho mọi server.

## 4. Hợp đồng dữ liệu Java và quy tắc mapping

Định nghĩa domain object bất biến theo dữ liệu thực sự cần:

~~~java
// DirectoryUser.java — Java 17+
public record DirectoryUser(
        String relativeDn,
        String uid,
        String fullName,
        String email,
        String phone
) {}
~~~

`relativeDn` là DN ở ngữ cảnh `ContextSource`; ứng dụng không nên gửi nó ra API công khai nếu không có lý do nghiệp vụ. Domain object này phục vụ tra cứu, **không tự động là entity có thể lưu ngược**.

DTO cho HTTP API:

~~~java
// DirectoryUserView.java
public record DirectoryUserView(
        String uid,
        String fullName,
        String email
) {
    public static DirectoryUserView from(DirectoryUser user) {
        return new DirectoryUserView(
                user.uid(), user.fullName(), user.email());
    }
}
~~~

Để tránh lộ dữ liệu:

- Chỉ đọc attribute ứng dụng sử dụng.
- Ánh xạ thiếu `mail` hoặc `telephoneNumber` sang `null`/optional theo hợp đồng, không tự tạo giá trị giả.
- Với attribute đa giá trị, định nghĩa kiểu danh sách và quy tắc chọn cụ thể thay vì lấy ngẫu nhiên giá trị đầu.
- Không đưa `userPassword`, binary attribute hoặc metadata nội bộ không cần thiết vào DTO.
- Ràng buộc dữ liệu không được phép tự động trở thành authority/role chỉ vì có một thuộc tính tên giống role.

## 5. Kết nối Spring LDAP và bảo vệ đường truyền

### 5.1. Dependencies và cấu hình

Ví dụ Maven trên dự án Spring Boot:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Chọn các phiên bản tương thích qua cơ chế dependency management của Spring Boot. Ví dụ chỉ nêu dependency theo nhiệm vụ; các ứng dụng REST thực tế còn cần Web starter và thư viện kiểm thử security tương ứng.

~~~yaml
# application.yml — giá trị runtime lấy từ môi trường/secret manager
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.lab.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các biến môi trường cho môi trường lab:

~~~text
LDAP_URL=ldaps://ldap.lab.example.org:636
LDAP_BIND_DN=cn=svc-directory-read,ou=system,dc=example,dc=org
LDAP_BIND_PASSWORD=(secret do secret manager cấp)
~~~

Spring Boot có thể tạo `LdapContextSource` và `LdapTemplate` từ các thuộc tính `spring.ldap` khi dependency và auto-configuration phù hợp. Nếu ứng dụng khai báo `ContextSource` riêng, phải bảo đảm cùng URL, base, TLS, timeout và quyền bind mong muốn.

### 5.2. LDAPS, StartTLS, truststore

Hai phương án:

| Phương án | Hình thức | Điều kiện an toàn |
|---|---|---|
| **LDAPS** | `ldaps://...:636` | Bắt tay TLS, xác minh CA/hostname rồi mới bind |
| **StartTLS** | `ldap://...:389`, sau đó StartTLS | Nâng cấp và xác minh TLS **trước khi truyền credential** |

Đối với LDAPS, JVM sử dụng truststore/cấu hình JSSE được cấp phép. Ví dụ chạy trên lab:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/secure/ldap-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar directory-app.jar
~~~

Truststore phải chứa CA được quản trị PKI cung cấp và chứng chỉ server phải có SAN hợp lệ cho hostname ứng dụng kết nối. Không dùng trust manager “accept all”, không tắt hostname verification và không chuyển sang plaintext nếu TLS lỗi. Với StartTLS, cần cấu hình `ContextSource`/JNDI để yêu cầu nâng cấp bắt buộc; đặt `ldap://` đơn thuần không bật TLS.

**HTTPS từ browser đến backend không thay thế TLS từ backend đến LDAP.** Hai chặng đều mang dữ liệu cần bảo vệ.

## 6. Truy vấn Spring LDAP: tìm user an toàn

### 6.1. Bốn quyết định trước khi query

| Quyết định | Giá trị lab | Lý do |
|---|---|---|
| Search base | `ou=people` tương đối với `dc=example,dc=org` | Không quét toàn directory |
| Scope | `SUBTREE` | Tìm cả nhân viên ở OU con |
| Filter | `(&(objectClass=inetOrgPerson)(uid=lan))` | Xác định entry user theo schema và uid |
| Projection | `uid`, `cn`, `mail`, `telephoneNumber` | Không tải thuộc tính không cần thiết |

**Không nối giá trị username vào filter dưới dạng string.** Dùng query builder để escape ký tự đặc biệt theo ngữ cảnh LDAP filter. DN có quy tắc escape khác filter; nếu dựng DN từ dữ liệu nhập, dùng `LdapNameBuilder` hoặc JNDI `LdapName`/`Rdn`.

### 6.2. Repository tra cứu và mapping

~~~java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

@Repository
public class DirectoryUserRepository {
    private final LdapTemplate ldapTemplate;

    private static final ContextMapper<DirectoryUser> USER_MAPPER =
            context -> {
                DirContextOperations entry =
                        (DirContextOperations) context;

                String uid = entry.getStringAttribute("uid");
                String cn = entry.getStringAttribute("cn");
                if (uid == null || cn == null) {
                    throw new IllegalStateException(
                        "LDAP entry missing required uid or cn");
                }

                return new DirectoryUser(
                        entry.getDn().toString(),
                        uid,
                        cn,
                        entry.getStringAttribute("mail"),
                        entry.getStringAttribute("telephoneNumber")
                );
            };

    public DirectoryUserRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryUser> searchByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query, USER_MAPPER);
    }
}
~~~

**Lưu ý kỹ thuật:**

1. `.where(...).is(uid)` biến `uid` thành giá trị equality literal. Input chứa `*` không được phép chuyển thành wildcard presence filter `(uid=*)`.
2. `attributes(...)` giảm dữ liệu trả về; điều kiện filter vẫn phải có quyền search/evaluate theo LDAP ACL.
3. `ContextMapper` dùng `DirContextOperations` để đọc attribute và DN. Với `spring.ldap.base` đã cấu hình, `getDn()` thường là DN tương đối với context base; phải kiểm chứng khi cần DN tuyệt đối.
4. Kết quả `search(...)` là danh sách. **Không mặc định chỉ có một entry** nếu schema/OU không bảo đảm tính duy nhất.
5. Lỗi kết nối, TLS, quyền truy cập hoặc schema không được chuyển bừa thành danh sách rỗng vì sẽ che khuất sự cố vận hành.

### 6.3. Service bảo đảm định danh không mơ hồ

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class DirectoryUserService {
    private final DirectoryUserRepository repository;

    public DirectoryUserService(DirectoryUserRepository repository) {
        this.repository = repository;
    }

    public Optional<DirectoryUser> findByUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            return Optional.empty();
        }

        List<DirectoryUser> matches = repository.searchByUid(uid);
        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "Ambiguous LDAP uid within search base");
        }
        return matches.stream().findFirst();
    }
}
~~~

Ba hậu trạng thái cần phân biệt: `0` kết quả → không tìm thấy; `1` kết quả → mapping hợp lệ; `>1` kết quả → định danh mơ hồ và **không chọn entry đầu tiên**. Giới hạn 128 ký tự là chính sách minh họa của ứng dụng, không phải giới hạn LDAP chung.

### 6.4. Tra cứu nhóm và domain authorization

Với `groupOfNames`, nhóm `cn=directory-readers` có `member` bằng **DN đầy đủ** của user. Một quy trình an toàn:

1. Xác thực đúng người dùng hoặc có principal từ phiên đã được xác thực.
2. Xác định entry và DN tương ứng bằng nguồn dữ liệu đáng tin.
3. Tìm nhóm đã được phê duyệt dưới `ou=groups` với filter equality trên `member`.
4. Map **đúng nhóm** sang authority ứng dụng như `DIRECTORY_READ` theo danh sách cấu hình.
5. Tại từng API, kiểm tra quyền của người gọi và ràng buộc theo tài nguyên.

LDAP schema có thể dùng `memberOf`, `uniqueMember`, nhóm lồng nhau hoặc cơ chế AD khác. Group lookup cần ACL tương ứng và có thể trả kết quả rỗng vì thiếu quyền, không phải luôn vì user không thuộc nhóm. **Không tự cấp authority khi truy vấn nhóm lỗi**.

## 7. Authentication, authorization và ACL

### 7.1. Hai danh tính bind khác nhau

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Spring application
    participant L as LDAP server
    U->>App: Username và password qua HTTPS
    App->>L: Service bind qua TLS
    L-->>App: Danh tính service được xác thực
    App->>L: Search DN user bằng filter an toàn
    L-->>App: DN của user
    App->>L: User bind bằng DN và password
    alt LDAP chấp nhận credential
        L-->>App: User bind thành công
        App->>L: Tra nhóm theo quyền được cấp
        L-->>App: Membership
        App->>App: Map authority và kiểm tra policy
        App-->>U: Tạo phiên ứng dụng nếu được phép
    else LDAP từ chối
        L-->>App: Lỗi xác thực
        App-->>U: Đăng nhập thất bại
    end
~~~

Service bind chứng minh backend được LDAP cho phép tra cứu; user bind mới là bước server kiểm tra mật khẩu người dùng cuối. `LdapTemplate.authenticate(...)` hỗ trợ xác thực dựa trên tìm DN rồi bind, còn Spring Security LDAP cung cấp bộ xác thực tích hợp vào `AuthenticationManager`, `SecurityContext` và các authority.

### 7.2. Mã minh họa xác thực credential

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryCredentialVerifier {
    private final LdapTemplate ldapTemplate;

    public DirectoryCredentialVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean verify(String uid, String password) {
        if (uid == null || uid.isBlank()
                || uid.length() > 128
                || password == null || password.isEmpty()) {
            return false;
        }
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.authenticate(query, password);
    }
}
~~~

Đoạn code này **chỉ minh họa credential verification**. Nó chưa tạo session hoặc JWT, chưa map authority, chưa giải quyết toàn bộ chính sách unique identifier và chưa tự cấp quyền API. Với HTTP login production, hãy tích hợp bằng Spring Security LDAP hoặc authentication provider được kiểm thử đầy đủ thay vì đặt cờ `loggedIn=true` trong controller.

### 7.3. Ma trận quyền

| Danh tính | Search user | Đọc mail/phone | Modify hồ sơ | Delete user | Sửa ACL/schema |
|---|---|---|---|---|---|
| `svc-directory-read` | Cho phép trong OU được cấp | Chỉ attribute được phê duyệt | Không | Không | Không |
| `svc-directory-write` | Giới hạn theo nghiệp vụ | Giới hạn | Chỉ thuộc tính và entry được phê duyệt | Mặc định không | Không |
| Người dùng cuối | Theo chính sách server | Theo ACL server | Theo ACL và backend policy | Không mặc định | Không |
| Admin vận hành | Theo phân công riêng | Theo phân công | Theo phân công | Theo phân công | Chỉ người được ủy quyền |

ACL trên LDAP kiểm soát thao tác theo **danh tính của kết nối thực tế**. Nếu backend dùng service account có quyền đọc rộng, một user HTTP không tự được phép đọc mọi hồ sơ. Backend cần kiểm tra authorization trước khi dùng quyền service account thực hiện truy vấn, đặc biệt với API có ID tài nguyên do client chọn.

Không dùng password comparison hoặc đọc `userPassword` để “lách” quyền bind. Server có thể lưu hash và áp chính sách khóa/hết hạn riêng, nên user bind là phương án nền tảng cho xác thực LDAP do máy chủ quản lý.

## 8. Thao tác ghi entry an toàn

Ứng dụng thực tế có thể cần cập nhật số điện thoại cho user. Để không trộn với dịch vụ read-only, nên dùng **tài khoản ghi chuyên dụng** và repository riêng, hoặc cơ chế thực thi dưới quyền được ủy quyền theo thiết kế tổ chức.

### 8.1. Dựng DN và cập nhật một thuộc tính

Ví dụ sau dành cho môi trường thử nghiệm trong đó user chỉ nằm trực tiếp dưới `ou=people`, và repository được inject `LdapTemplate` gắn với **write-specific `ContextSource`** đã cấu hình riêng:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryUserWriteRepository {
    private final LdapTemplate writeLdapTemplate;

    public DirectoryUserWriteRepository(LdapTemplate writeLdapTemplate) {
        this.writeLdapTemplate = writeLdapTemplate;
    }

    public void updatePhone(String uid, String phone) {
        if (uid == null || uid.isBlank()
                || phone == null || phone.isBlank()) {
            throw new IllegalArgumentException("Invalid update input");
        }

        // Ví dụ chỉ đúng khi DN thực sự có mẫu uid=<uid>,ou=people.
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        ModificationItem item = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone)
        );
        writeLdapTemplate.modifyAttributes(
                relativeDn, new ModificationItem[] {item});
    }
}
~~~

**Không dùng nguyên mẫu DN cố định này cho hệ thống có nhiều OU hoặc DN không suy ra trực tiếp từ uid.** Trong trường hợp đó, hãy tìm entry thực và lấy DN đã kiểm chứng từ directory, sau đó áp chính sách quyền và kiểm tra thay đổi đồng thời. `LdapNameBuilder` giúp escape DN component, nhưng không thay thế input validation và authorization.

Tầng service phải kiểm tra **người gọi có quyền sửa đúng entry và thuộc tính `telephoneNumber` hay không** trước khi gọi write repository. Với thao tác viết, cần kiểm soát race condition, audit và luồng xác nhận; không chuyển trực tiếp JSON tùy ý thành LDAP ModificationItem với mọi attribute do client gửi.

### 8.2. Add và Delete

`LdapTemplate.bind(dn, null, attributes)` dùng để **tạo LDAP entry**; `LdapTemplate.unbind(dn)` dùng để **xóa entry**. Từ `bind` trong API tạo entry khác hẳn **LDAP Bind Request** dùng để xác thực kết nối.

Quy trình create/delete cần giới hạn OU, xác minh schema, uniqueness, sự tồn tại của entry con và quyền ACL. Trong môi trường production, deletion có thể yêu cầu quy trình phê duyệt, khóa account hoặc đánh dấu vô hiệu hóa trước khi xóa dữ liệu vĩnh viễn.

### 8.3. Transaction và xử lý trạng thái dở dang

Các thao tác LDAP Add/Modify/Delete là các request riêng; một chuỗi gồm nhiều request **không tự rollback nguyên tử** khi lời gọi Java sau đó gặp lỗi. Spring LDAP có cơ chế transaction bù ở những cấu hình/phiên bản hỗ trợ, nhưng compensation không phải transaction nguyên tử của server và vẫn có thể thất bại.

Nếu workflow tạo user → thêm nhóm → cập nhật hồ sơ gặp lỗi ở giữa, cần có:

1. Operation ID và hậu điều kiện mong đợi cho từng bước.
2. Cách xác định entry đã được tạo/sửa hay chưa khi network timeout.
3. Thao tác bù có kiểm soát trên đúng dữ liệu do workflow sở hữu.
4. Đối soát sau lỗi, tránh retry mù rồi xóa/sửa nhầm dữ liệu.
5. Nhật ký audit đủ để vận hành xử lý trạng thái còn dở dang.

Không mặc định `@Transactional` của JDBC/JPA sẽ rollback được thay đổi LDAP.

## 9. Thiết kế kiểm thử theo nhiều lớp

### 9.1. Dữ liệu test và môi trường

Dựng LDAP test hoặc staging với:

- Một user `uid=lan` có `cn`, `sn`, `mail`; một user `uid=minh` không có email.
- Một user dưới `ou=contractors,ou=people` để kiểm tra `SUBTREE`.
- Nhóm `directory-readers` với membership đúng DN.
- Tài khoản chỉ đọc và tài khoản ghi test có ACL giới hạn.
- Endpoint LDAPS/StartTLS với CA thử nghiệm được tin cậy.
- Các entry test và mật khẩu **riêng**, không dùng dữ liệu người dùng production.

### 9.2. Integration test: tra cứu end-to-end

Ví dụ dùng Spring Boot/JUnit 5; test chỉ chạy khi biến môi trường cho phép:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-it")
@EnabledIfEnvironmentVariable(
        named = "RUN_LDAP_IT", matches = "true"
)
class DirectoryLookupIntegrationTest {
    @Autowired
    private DirectoryUserService service;

    @Test
    void mapsSingleUser() {
        DirectoryUser user = service.findByUid("lan").orElseThrow();
        assertThat(user.uid()).isEqualTo("lan");
        assertThat(user.fullName()).isEqualTo("Lan Tran");
        assertThat(user.email()).isEqualTo("lan@example.org");
        assertThat(user.relativeDn()).contains("uid=lan");
    }

    @Test
    void keepsOptionalEmailNull() {
        DirectoryUser user = service.findByUid("minh").orElseThrow();
        assertThat(user.email()).isNull();
    }

    @Test
    void doesNotExpandWildcardInput() {
        assertThat(service.findByUid("*")).isEmpty();
    }
}
~~~

Test dấu `*` giả định directory test không có entry với `uid` literal bằng dấu sao; mục tiêu là kiểm tra filter không bị nới rộng thành điều kiện `uid=*`. Nếu schema/dataset khác, assertion cần phản ánh giá trị literal hợp lệ thay vì nhầm lẫn với wildcard.

### 9.3. Ma trận kiểm thử bắt buộc

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| DIT | Search trong `ou=people` | Chỉ trả entry thuộc scope được cấu hình |
| DIT | User nằm dưới OU con | `SUBTREE` tìm thấy; `ONELEVEL` không tìm user ở cấp sâu |
| Schema | User thiếu `mail` | Domain vẫn hợp lệ, `email=null` |
| Schema | User thiếu attribute bắt buộc | Lỗi dữ liệu rõ ràng |
| Filter | `uid=*` hoặc chuỗi có ngoặc | Được escape thành literal, không đổi cấu trúc filter |
| Filter | User không tồn tại | Trả kết quả rỗng có chủ đích |
| Uniqueness | Hai entry khác DN cùng `uid` | Báo danh tính mơ hồ, không chọn phần tử đầu |
| Security | Service bind sai mật khẩu | Không có kết nối/search hợp lệ |
| Security | User bind sai mật khẩu/rỗng | Không tạo phiên đăng nhập |
| Security | User đã bind đúng nhưng không có authority | Bị từ chối endpoint được bảo vệ |
| ACL | Read account thử modify | Server từ chối |
| ACL | Write account thử sửa attribute ngoài phạm vi | Server từ chối |
| TLS | CA không tin cậy hoặc SAN sai | Handshake thất bại, không gửi credential |
| Operations | LDAP timeout/không khả dụng | Lỗi hạ tầng riêng, không bị hiểu là user không tồn tại |
| Operations | Node failover/cert rotation | Kết nối mới vẫn xác minh TLS và search đúng |
| Writes | Modify thành công | Readback xác minh giá trị mới |
| Writes | Modify bị từ chối | Không báo thành công; readback giữ trạng thái hợp lệ |
| Writes | Timeout sau Delete | Đối soát trạng thái thay vì retry mù |

### 9.4. Ba loại test không thay thế nhau

- **Unit test:** mock repository để kiểm tra input validation, uniqueness, mapping và policy không cần LDAP server.
- **LDAP integration test:** dùng directory test có schema/ACL thực để kiểm tra ContextSource, query, entry mapping, bind, TLS và ghi.
- **HTTP authorization test:** với Spring Security, xác nhận 401/403 và kiểm tra quyền tài nguyên. `@WithMockUser` có thể kiểm tra authorization nhưng **không chứng minh LDAP bind/group lookup thực hoạt động**.

Khi test kết nối TLS, phải có ca âm chứng minh ứng dụng **từ chối certificate không tin cậy**. Một test query trả dữ liệu thành công sẽ không đủ nếu code vô tình tắt xác minh chứng chỉ.

## 10. Hiệu năng, giới hạn truy vấn và pooling

### 10.1. Search base, scope, index

Với directory có hàng triệu entry:

1. Giới hạn base/scope theo nghiệp vụ; chỉ dùng `SUBTREE` khi thực sự cần OU con.
2. Tra cứu equality theo attribute đã được server index và đo thời gian thực tế; index cụ thể do directory admin cấu hình.
3. Chỉ yêu cầu những attribute cần thiết thay vì đọc mọi giá trị.
4. Cân nhắc size limit, time limit, server result limit, paging khi chức năng là danh sách lớn; với lookup một định danh phải bảo đảm phát hiện duplicate.
5. Đo latency p50/p95/p99 trên cả search, bind, group lookup và TLS handshake; phân loại timeout kết nối với timeout LDAP operation.

**Không tự chọn `countLimit(1)` cho chức năng đòi tính duy nhất**, vì kết quả giới hạn có thể che các entry trùng. Nếu dùng paging hay giới hạn truy vấn, phải thiết kế cách xử lý `sizeLimitExceeded` và kết quả chưa đầy đủ.

### 10.2. Connection/context và pool

Pooling có thể giảm chi phí mở kết nối nhưng làm phức tạp quản lý danh tính:

- Tách service context và user-bound context; không đưa connection đã bind với người dùng khác vào pool chung.
- Xác minh pooling hỗ trợ kiểu TLS đang dùng, đặc biệt với StartTLS.
- Cấu hình timeout và cơ chế loại kết nối lỗi/stale sau khi LDAP server đổi node.
- Khi rotation certificate hoặc CA, kiểm tra **kết nối mới** bên cạnh request dùng kết nối cũ.
- Giới hạn connection count và concurrency để không gây quá tải server khi ứng dụng tăng số bản sao.

Không bật/tinh chỉnh pooling chỉ dựa vào throughput mà bỏ qua kiểm soát security context, cách reconnect và chính sách vận hành.

## 11. Quan sát, xử lý sự cố và phân loại lỗi

### 11.1. Metric và log đề xuất

| Tín hiệu | Ý nghĩa | Hành động khi bất thường |
|---|---|---|
| `ldap_connect_duration` / handshake latency | Độ trễ mở kết nối bảo mật | Kiểm tra DNS, mạng, node hoặc TLS |
| `ldap_search_duration` | Độ trễ truy vấn | Rà soát index, base, scope, server load |
| `ldap_bind_failures` | Lỗi tài khoản dịch vụ hoặc user bind | Phân loại không để credential trong log |
| `ldap_tls_failures` | Chứng chỉ/CA/hostname hoặc TLS handshake | Kiểm tra PKI/truststore và node |
| `ldap_access_denied` | ACL không cho phép thao tác | Kiểm tra quyền tối thiểu và policy thay đổi |
| `ldap_pool_active` / `idle` | Mức sử dụng pool | Kiểm tra cạn pool, leak, stale connections |
| `ldap_timeouts` | LDAP không đáp ứng đúng hạn | Kiểm tra server/network, retry/backoff |
| Certificate days-to-expiry | Chứng chỉ sắp hết hạn | Chuẩn bị rotation trước khi gián đoạn |

Đây là **tên metric đề xuất**, không phải các metric mà Spring LDAP tự động xuất ra dưới đúng tên như vậy. Có thể dùng Micrometer/Actuator hoặc tầng instrumentation riêng để ghi duration, outcome, error category mà không lưu secret.

Log kỹ thuật tối thiểu nên có: correlation ID, operation name (`search`/`bind`/`modify`), endpoint hoặc cluster ID, loại lỗi, thời gian và DN đã được giảm thiểu thông tin khi cần. Không log mật khẩu, token, password hash hoặc toàn bộ entry nhạy cảm.

### 11.2. Cây quyết định khi request LDAP thất bại

~~~mermaid
flowchart TD
    A["LDAP request thất bại"] --> B{"Có kết nối TLS hợp lệ?"}
    B -->|Không| C["Kiểm tra DNS, route, cert, CA, SAN, TLS version"]
    B -->|Có| D{"Service bind hợp lệ?"}
    D -->|Không| E["Kiểm tra service DN, secret và trạng thái account"]
    D -->|Có| F{"Search trả dữ liệu đúng?"}
    F -->|Không| G["Kiểm tra base, scope, filter, schema, ACL và index"]
    F -->|Có| H{"Bước xác thực/quyền hoặc ghi lỗi?"}
    H -->|Có| I["Kiểm tra user bind, group mapping, ACL, modify và business policy"]
    H -->|Không| J["Đối chiếu metric, pool, timeout và trạng thái trả về"]
~~~

| Lỗi phổ biến | Nơi điều tra trước |
|---|---|
| `PKIX path building failed` | JVM truststore và certificate chain |
| `No subject alternative DNS name matching` | SAN/hostname trong LDAP URL |
| `invalidCredentials (49)` | Credential của danh tính đang bind |
| `insufficientAccessRights (50)` | ACL của entry/attribute và bind DN |
| `noSuchObject (32)` | Base DN, DN entry hoặc vùng directory |
| `sizeLimitExceeded` | Query scope, server/client limits hoặc truy vấn quá rộng |
| Timeout/mất kết nối | Mạng, node, pool, server load và retry policy |

Với lỗi đăng nhập, phản hồi bên ngoài nên tránh tiết lộ username có tồn tại. Đồng thời log nội bộ phải phân biệt lỗi **credential** với lỗi **hạ tầng/TLS**; một khối `catch (Exception) { return false; }` cho mọi trường hợp sẽ che khuất sự cố quan trọng.

## 12. Runbook triển khai và vận hành

### 12.1. Trước khi triển khai

1. **Xác nhận DIT/schema:** base DN, OU, attribute, group type, uniqueness, dữ liệu test, sơ đồ nhóm lồng nhau nếu có.
2. **Đánh giá ACL:** tài khoản read-only và write account chỉ có quyền cần thiết; test thao tác bị cấm và xác nhận fail closed.
3. **Kiểm chứng TLS:** CA và SAN hợp lệ; truststore ứng dụng đúng; ca chứng chỉ sai phải thất bại.
4. **Cấp secrets:** account tách biệt giữa dev/staging/prod, có quy trình rotation và thu hồi.
5. **Kiểm thử kết nối:** trên cùng mạng và phiên bản JDK/Spring Boot gần production, test service bind, search, user bind và group lookup.
6. **Capacity:** chốt giới hạn timeout, connection pool, concurrency, index và ngưỡng cảnh báo.
7. **Phương án rollback:** cấu hình versioned, thay đổi schema/ACL được phê duyệt, bảo toàn dữ liệu và có điểm khôi phục.

### 12.2. Trong khi triển khai

- Triển khai từng đợt nhỏ (canary) với chỉ số lỗi kết nối/bind/search và latency.
- Chạy smoke test `uid` test, nhóm test và endpoint yêu cầu authority.
- Kiểm tra log các node LDAP nếu có load balancer hoặc DNS nhiều địa chỉ.
- Không thử tạo/xóa entry thật để kiểm tra trên production; thao tác ghi test chỉ được chạy trên OU được phép và có cleanup.
- Nếu tỷ lệ lỗi TLS tăng hoặc các bài test ACL thất bại, **chặn mở rộng rollout** và xử lý theo quy trình incident.

### 12.3. Sau triển khai

- Theo dõi bão lỗi credential, TLS và timeout; đặt ngưỡng báo động theo baseline.
- Lập lịch đánh giá quyền của service account và rotation secret/certificate.
- Định kỳ kiểm chứng backup/restore directory theo quy trình nhà cung cấp; không xem snapshot chưa restore thử là đủ.
- Rà soát DN đã chuyển OU, nhóm thay đổi, attribute/schema drift và dữ liệu trùng định danh.
- Bảo đảm quyền thu hồi có hiệu lực với session/token theo TTL hoặc cơ chế refresh phù hợp.

### 12.4. Bảng thao tác khi có sự cố

| Tình huống | Bước đầu tiên | Hành vi ứng dụng an toàn |
|---|---|---|
| Chứng chỉ LDAP hết hạn | Xác minh CA/SAN, điều phối PKI thay cert trên mọi node | Không tắt TLS hoặc fallback plaintext |
| Secret service account hết hiệu lực | Kiểm tra secret manager, trạng thái account, lịch rotation | Tạm dừng truy vấn phụ thuộc; không chuyển sang admin DN tùy tiện |
| LDAP cluster không sẵn sàng | Kiểm tra health, network, failover | Trả lỗi hạ tầng hoặc dữ liệu cache được cho phép; không giả định xác thực thành công |
| User search trả nhiều DN | Cô lập nguyên nhân trùng định danh | Từ chối chọn user; không cho đăng nhập dưới một entry bất kỳ |
| Nhóm LDAP bị sai membership | Xác minh thay đổi và nguồn quyền | Thu hồi/refresh authority theo chính sách |
| Modify timeout không rõ kết quả | Đọc lại entry và đối soát operation ID | Không retry ghi mù quáng |
| Backend trả lộ thông tin nhạy cảm | Ngắt luồng API liên quan, thu hồi quyền nếu cần | Giảm dữ liệu trả về, xử lý incident/audit |

## 13. Checklist nghiệm thu cuối khóa

Đánh dấu từng mục sau dựa trên **bằng chứng test**, không chỉ dựa trên kết luận chủ quan:

| Hạng mục | Bằng chứng cần có |
|---|---|
| DIT/schema | Sơ đồ OU/DN, attribute bắt buộc/tùy chọn, quy tắc uniqueness |
| Search | Test equality filter an toàn, base/scope, projection, 0/1/nhiều entry |
| Mapping | Test domain object, DN tương đối, field thiếu và dữ liệu Unicode |
| Security | Service/user bind tách biệt, quyền ACL tối thiểu, API authorization |
| TLS | Certificate CA/SAN được xác minh, negative tests không chấp nhận cert sai |
| Operations | Test timeout, lỗi LDAP, failover, cert rotation, pooling |
| Writes | Audit thao tác sửa, readback và test quyền từ chối |
| Data integrity | Kế hoạch xử lý nhiều bước, retry/idempotency và đối soát |
| Observability | Duration, error category, correlation ID và alert đã cấu hình |
| Release | Staging pass, canary, runbook, backup/restore và rollback có người phụ trách |

### 13.1. Câu hỏi tự đánh giá

1. Vì sao nên tách `ou=people`, `ou=groups` và `ou=system` thay vì dùng một vùng directory không phân quyền?
2. `spring.ldap.base` và `spring.ldap.username` khác nhau thế nào?
3. Tại sao `LdapQueryBuilder.where("uid").is(input)` an toàn hơn ghép chuỗi filter?
4. Nếu search trả hai DN có cùng `uid`, vì sao không chọn entry đầu tiên?
5. Tại sao service bind thành công chưa chứng minh người dùng cuối được xác thực?
6. LDAP ACL đã cho tài khoản dịch vụ đọc một entry. Người gọi API có tự được xem entry đó không?
7. Test search thành công qua LDAPS có đủ chứng minh hostname verification bật đúng không?
8. Nếu Modify timeout sau khi server đã xử lý, tại sao retry ngay có thể không an toàn?
9. Vì sao không nên dùng `@Transactional` của JDBC để mặc định rollback LDAP?
10. Những tín hiệu vận hành nào cho biết sắp cần rotate certificate hoặc tăng capacity LDAP?

**Gợi ý trả lời:** (1) Tách phạm vi và ACL theo nhiệm vụ. (2) Một bên là gốc tìm kiếm, bên kia là danh tính kết nối. (3) Query builder escape literal theo cú pháp LDAP filter. (4) Định danh mơ hồ, thứ tự không có ý nghĩa nghiệp vụ. (5) Chỉ xác thực service account. (6) Không, cần application authorization. (7) Chưa, cần negative tests CA/SAN. (8) Chưa biết hậu trạng thái và có thể ghi đè dữ liệu đồng thời. (9) LDAP là tài nguyên khác, cần cơ chế bù/transaction phù hợp. (10) Cert expiry, handshake failures, p95 latency, timeout, pool exhaustion.

## Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, query builder, mapping, ODM và thao tác entry.
- [Spring Security LDAP](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): user bind, search và nạp authorities.
- [Spring Boot LDAP configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap): thuộc tính `spring.ldap` và auto-configuration.
- [RFC 4511](https://www.rfc-editor.org/rfc/rfc4511): LDAP protocol, DN, search, add, modify, delete, bind.
- [RFC 4515](https://www.rfc-editor.org/rfc/rfc4515): representation và escaping của LDAP search filter.

## Kết luận

Một hồ sơ tích hợp **Spring LDAP** hoàn chỉnh phải liên kết được các quyết định về **DIT/schema → truy vấn và mapping → quyền truy cập → TLS và xác thực → kiểm thử → vận hành**. Truy vấn đúng chưa đủ nếu tài khoản dịch vụ có quyền quá rộng; bind đúng chưa đủ nếu API không kiểm tra quyền; kết nối TLS thành công chưa đủ nếu không kiểm tra chứng chỉ; và thao tác ghi thành công một lần chưa đủ nếu chưa thiết kế đối soát khi mất phản hồi. Hãy xem đây là bộ tiêu chí để biến một bài lab LDAP thành dịch vụ directory đáng tin cậy, có thể bảo trì và kiểm toán.
