# Tách quyền đọc danh bạ với quyền quản trị tài khoản

Một ứng dụng Spring Data LDAP thường cần **tra cứu thông tin danh bạ** cho rất nhiều người dùng, nhưng chỉ một nhóm nhỏ được phép **tạo tài khoản, đổi thuộc tính quản trị, đặt lại mật khẩu, khóa tài khoản hoặc thay đổi nhóm quyền**. Nếu mọi chức năng đều dùng cùng một tài khoản LDAP có quyền quản trị, một lỗi trong API đọc danh bạ có thể trở thành lỗi có khả năng sửa hoặc xóa dữ liệu.

Giải pháp là **tách quyền theo chức năng và theo lớp bảo vệ**: tài khoản dịch vụ đọc danh bạ chỉ được xem thuộc tính cần thiết; tài khoản dịch vụ quản trị được cấp quyền ghi đúng phạm vi nghiệp vụ; người gọi HTTP vẫn phải qua xác thực và phân quyền; ACL tại directory phải là chốt chặn độc lập với mã Java.

Bài học thuộc chương **Bảo mật dữ liệu** của mô-đun `SPRING_DATA_LDAP`. Ta sẽ thiết kế hai luồng đọc/ghi dùng `LdapTemplate` và Spring Data LDAP, phân tích ACL OpenLDAP, DN, `objectClass`, schema, filter an toàn, CRUD và kiểm thử trực tiếp với LDAP server.

> **Nguyên tắc xuyên suốt:** `@PreAuthorize` kiểm soát **ai được gọi một method Java**; `ContextSource` xác định **LDAP Bind DN thực hiện lời gọi tới directory**; ACL LDAP xác định **Bind DN đó được làm gì với entry/attribute nào**. Ba tầng này bổ sung cho nhau, không thay thế nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt quyền **xem danh bạ** với quyền **quản trị vòng đời tài khoản**, quyền sửa hồ sơ và quyền quản lý nhóm.
2. Giải thích sự khác biệt giữa **HTTP identity**, **service Bind DN** và quyền **LDAP ACL**.
3. Thiết kế ma trận quyền theo nguyên tắc *least privilege* và *deny by default*.
4. Áp dụng ACL theo **subtree**, **entry**, **children**, **thuộc tính** và **danh tính Bind** trong OpenLDAP.
5. Khai báo hai `LdapContextSource` và hai `LdapTemplate` dùng **credential riêng**, không dùng admin account cho Search thông thường.
6. Thiết lập Spring Security `@EnableMethodSecurity`/`@PreAuthorize` ở tầng service mà không dựa chỉ vào URL.
7. Xây DTO đọc danh bạ và service quản trị riêng, dùng `LdapNameBuilder`/`LdapQueryBuilder` thay vì nối DN/filter.
8. Kiểm thử cả các ca **được phép** và **bị từ chối**, đặc biệt từ chối Modify/Add/Delete khi Bind bằng tài khoản đọc.
9. Nhận diện các trường hợp ACL che thuộc tính khiến Search/Lookup có vẻ “không có dữ liệu”.
10. Lên kế hoạch TLS, secret rotation, audit, xử lý lỗi và kiểm soát quyền trong môi trường triển khai.

## 2. Bối cảnh và mô hình đe dọa

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    ├── cn=svc-directory-reader
    └── cn=svc-account-admin
~~~

Ví dụ entry `uid=lan`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
title: Backend Developer
~~~

Một API tra cứu cần trả `uid`, `cn`, `sn`, `mail`, `title`. Nhưng tài khoản LDAP có thể còn lưu các thuộc tính khác như:

- `userPassword` hoặc thuộc tính phục vụ xác thực.
- Mã nhân sự, dữ liệu cá nhân, số điện thoại riêng, mã tổ chức.
- Dữ liệu trạng thái/khóa tài khoản đặc thù nhà cung cấp.
- Tham chiếu nhóm `member` trong các entry `groupOfNames`.
- Thuộc tính vận hành (`entryUUID`, thời điểm thay đổi) và metadata phục vụ kiểm toán.

Không phải tất cả thuộc tính đó đều được phép xem qua API danh bạ. Đặc biệt, **schema cho phép một thuộc tính tồn tại không đồng nghĩa ai cũng được đọc/ghi thuộc tính đó**.

### Những kịch bản cần phòng tránh

| Kịch bản | Nếu chỉ có một Bind account toàn quyền | Khi tách quyền |
| --- | --- | --- |
| API tìm kiếm có lỗi và thực hiện nhầm Modify | Có thể sửa entry thật. | Bind account đọc bị ACL từ chối ghi. |
| Client gửi thêm `userPassword` vào JSON | Nếu entity bind tràn lan có thể chạm thuộc tính nhạy cảm. | DTO không nhận trường; reader không có quyền ghi; admin service kiểm tra use case. |
| Lộ mật khẩu dịch vụ tra cứu | Kẻ tấn công có thể quản trị toàn directory nếu dùng admin account. | Phạm vi thiệt hại giới hạn ở những dữ liệu reader được ACL cho đọc; vẫn là sự cố cần xử lý. |
| Nhân viên có quyền đọc gọi endpoint quản trị | Có thể qua nếu authorization chỉ dựa vào đăng nhập. | Spring Security từ chối ở controller/service. |
| Lỗi filter hoặc đổi DN dẫn đến nhánh nhạy cảm | Tài khoản toàn quyền có thể đọc/sửa vượt phạm vi. | Cố định base, escaping và LDAP ACL giảm ảnh hưởng. |
| Một service yêu cầu thêm quyền “cho chạy được” | Dễ bị cấp rootdn. | Tách request quyền theo operation/attribute, có test âm tính. |

**Không dùng OpenLDAP `rootdn` làm tài khoản chạy ứng dụng.** Với OpenLDAP, rootdn của database được đặc quyền và có thể vượt qua ACL thông thường. Nếu ứng dụng Bind bằng rootdn, bài kiểm thử phân tách quyền sẽ cho kết quả sai lệch so với chính sách dự kiến.

## 3. Ba lớp danh tính và ranh giới tin cậy

~~~mermaid
flowchart TD
    U["Người dùng HTTP<br/>JWT/session/API identity"] --> H["Spring Security<br/>DIRECTORY_READ / ACCOUNT_ADMIN"]
    H --> S["Application services<br/>DTO + kiểm tra nghiệp vụ"]
    S --> R["DirectoryReaderService<br/>LdapTemplate đọc"]
    S --> A["AccountAdminService<br/>LdapTemplate ghi"]
    R --> RC["Bind: svc-directory-reader<br/>Secret chỉ đọc"]
    A --> AC["Bind: svc-account-admin<br/>Secret quản trị giới hạn"]
    RC --> L["LDAP Server: schema + ACL"]
    AC --> L
    L --> P["ou=people<br/>entry/attribute kiểm soát độc lập"]
~~~

Có **ba loại quyền**:

| Lớp | Danh tính | Quyết định |
| --- | --- | --- |
| HTTP/API | Người dùng đã xác thực vào ứng dụng | Người đó có được xem danh bạ, tạo/sửa tài khoản nào không? |
| LDAP client | `cn=svc-directory-reader,...` hoặc `cn=svc-account-admin,...` | Ứng dụng dùng credential nào để Bind vào directory? |
| LDAP server | Bind DN và ACL | Credential đó có quyền Search/Read/Add/Modify/Delete/Rename entry/attribute mục tiêu không? |

Một người gọi API có authority `ACCOUNT_ADMIN` **không có nghĩa** phải biết mật khẩu LDAP admin. Ứng dụng giữ credential dịch vụ ở phía server. Ngược lại, nếu ứng dụng Bind thành công bằng admin service account, điều đó **không chứng minh người gọi HTTP đã được phép quản trị**.

### Luồng đọc và ghi

~~~mermaid
sequenceDiagram
    autonumber
    actor Client as Người gọi HTTP
    participant Sec as Spring Security
    participant Read as ReaderService
    participant Admin as AccountAdminService
    participant LDAP as LDAP Server
    Client->>Sec: GET /api/v1/people/lan
    Sec->>Read: Cho phép khi có DIRECTORY_READ
    Read->>LDAP: Bind/Search bằng svc-directory-reader
    LDAP-->>Read: uid,cn,sn,mail,title theo ACL
    Read-->>Client: PersonResponse (whitelist)
    Client->>Sec: POST /api/v1/people
    alt Thiếu ACCOUNT_ADMIN
        Sec-->>Client: 403 Forbidden
    else Có ACCOUNT_ADMIN
        Sec->>Admin: CreatePersonRequest
        Admin->>LDAP: Bind/Add bằng svc-account-admin
        LDAP-->>Admin: Success hoặc lỗi schema/ACL
        Admin-->>Client: Kết quả được lọc
    end
~~~

Với yêu cầu có thể làm thay đổi tài khoản, **kiểm tra quyền API trước khi gửi LDAP Modify/Add/Delete**. ACL tiếp tục từ chối nếu mã Java có lỗi hoặc yêu cầu đi qua một đường khác không được bảo vệ.

## 4. Thiết kế ma trận quyền tối thiểu

Ví dụ chia ba vai trò vận hành:

| Operation / dữ liệu | Reader account | Profile editor (nếu có) | Account admin |
| --- | :---: | :---: | :---: |
| Bind vào LDAP bằng secret riêng | Có | Có | Có |
| Search `ou=people` theo `uid`/`cn` | Có | Có thể | Có |
| Đọc `uid,cn,sn,mail,title` | Có | Có thể | Có |
| Đọc `userPassword` | **Không** | **Không** | **Thông thường cũng không cần** |
| Sửa `title`/`mail` | Không | Chỉ khi được cấp | Theo use case được phép |
| Thêm entry `inetOrgPerson` | Không | Không | Có, trong OU được phép |
| Xóa/đổi RDN/move entry | Không | Không | Qua luồng đặc quyền riêng |
| Quản lý `member` của nhóm | Không | Không | Chỉ khi vai trò đó thực sự quản lý nhóm |
| Đặt lại thông tin xác thực | Không | Không | Qua workflow riêng được kiểm soát |
| Thay ACL, schema, cấu hình directory | Không | Không | **Không** cho account admin ứng dụng; dành cho directory operator |

Đây là một mô hình mẫu; tổ chức có thể tách tiếp thành **profile editor**, **provisioner**, **group manager** và **password reset operator**. Tài khoản “account admin” trong ví dụ **không nên mặc nhiên có quyền quản trị toàn LDAP server**.

**Quan trọng:** quyền xem danh bạ không phải quyền xem *mọi thuộc tính*. Đọc `mail` công việc có thể được phép nhưng `homePhone` hoặc các thuộc tính bí mật không nên nằm trong cùng allowlist.

## 5. Hiểu ACL của OpenLDAP: không chỉ có read/write

OpenLDAP hỗ trợ kiểm soát theo **entry, attribute, scope của DN và danh tính yêu cầu**. Các cấp thông dụng:

| Cấp ACL | Ý nghĩa khái quát |
| --- | --- |
| `none` | Không có quyền. |
| `disclose` | Có thể hỗ trợ thông tin lỗi cho biết đối tượng tồn tại, không đồng nghĩa được đọc nội dung. |
| `auth` | Đủ điều kiện dùng thuộc tính cho mục đích xác thực; không phải quyền đọc giá trị mật khẩu. |
| `compare` | So sánh giá trị theo chính sách server. |
| `search` | Sử dụng thuộc tính trong filter. |
| `read` | Đọc giá trị thuộc tính được cho phép, bao gồm các đặc quyền thấp hơn theo mô hình OpenLDAP. |
| `write` | Sửa thuộc tính/entry khi các điều kiện schema và ACL khác cũng cho phép. |
| `manage` | Quyền quản lý cao hơn; tránh cấp cho ứng dụng nếu không cần. |

### 5.1. Search không hoàn toàn đồng nghĩa Read

Một tài khoản có thể được phép dùng `uid` trong filter nhưng không được đọc một thuộc tính khác. Khi ứng dụng gửi:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

ACL phải cho phép mức thích hợp để **Search** trên `objectClass`/`uid`, và **Read** những trường muốn trả ra (`cn`, `sn`, `mail`, `title`).

Nếu `mail` không xuất hiện trong response, chưa chắc entry không có `mail`: thuộc tính có thể bị ACL ẩn, bị request projection bỏ qua hoặc thực sự không tồn tại.

### 5.2. `entry` và `children` là các mục tiêu ACL đặc biệt

OpenLDAP dùng các mục tiêu `entry` và `children` để kiểm soát truy cập đối tượng và thao tác trên danh sách con. Thông thường:

- Đọc entry cần quyền thích hợp trên `entry` và thuộc tính muốn đọc.
- **Add/Delete** entry cần đánh giá quyền với entry và **`children` của parent** theo quy tắc server.
- Rename/Move có thể cần quyền tại tên nguồn và parent nguồn/đích.

Vì vậy, chỉ cấp `write` vào `cn`/`mail` **không đủ để tự cho phép tạo tài khoản mới**. Quyền create/delete và quản trị vòng đời cần được thiết kế riêng.

### 5.3. Thứ tự các ACL ảnh hưởng trực tiếp kết quả

OpenLDAP đánh giá ACL theo thứ tự và thường dừng khi gặp quy tắc phù hợp. Nếu đặt một rule rộng kiểu `access to * by * read` lên trước các rule hạn chế, bạn có thể vô tình công khai dữ liệu không định công khai.

Một cấu hình ACL đầy đủ cần được thử trên **phiên bản directory và backend cụ thể**; không thể suy ra nó an toàn chỉ bằng việc nhìn một đoạn ví dụ.

## 6. Ví dụ chính sách ACL tại directory

Đây là **đoạn minh họa chính sách** cho database chứa `dc=example,dc=org` trong OpenLDAP. Có thể biểu diễn trong cấu hình `slapd.conf` hoặc chuyển sang các giá trị `olcAccess` có thứ tự trong `cn=config`. Cú pháp và cách nạp phụ thuộc cách server được triển khai.

> **Không dán nguyên đoạn này vào production.** Nó minh họa quyền reader/admin đối với `ou=people`, **chưa** chứa toàn bộ quy tắc Bind cho service account dưới `ou=service`, các nhánh khác, chính sách user tự đổi mật khẩu, replication và ACL quản trị của hệ thống. Phải review toàn bộ ACL hiện hữu và kiểm thử trước khi áp dụng.

~~~text
# 1. Không cho reader nhìn thấy hay sửa mật khẩu người dùng.
#    Anonymous auth phục vụ cơ chế xác thực khi chính sách yêu cầu.
access to dn.subtree="ou=people,dc=example,dc=org" attrs=userPassword
    by dn.exact="cn=svc-account-admin,ou=service,dc=example,dc=org" write
    by anonymous auth
    by * none

# 2. Tạo/xóa entry con trực tiếp dưới ou=people chỉ cho provisioner.
access to dn.base="ou=people,dc=example,dc=org" attrs=children
    by dn.exact="cn=svc-account-admin,ou=service,dc=example,dc=org" write
    by * none

# 3. Reader chỉ đọc các thuộc tính danh bạ được phê duyệt.
#    Admin có thể viết tập thuộc tính này theo workflow quản trị.
access to dn.subtree="ou=people,dc=example,dc=org" attrs=entry,objectClass,ou,uid,cn,sn,mail,title
    by dn.exact="cn=svc-account-admin,ou=service,dc=example,dc=org" write
    by dn.exact="cn=svc-directory-reader,ou=service,dc=example,dc=org" read
    by * none

# 4. Các thuộc tính khác trong ou=people không dành cho reader.
#    Giới hạn bổ sung quyền admin ở ứng dụng/ACL chi tiết nếu cần.
access to dn.subtree="ou=people,dc=example,dc=org"
    by dn.exact="cn=svc-account-admin,ou=service,dc=example,dc=org" write
    by * none
~~~

### Phân tích đoạn ACL

- **Reader** có quyền đọc các thuộc tính danh bạ nằm trong danh sách cho phép dưới `ou=people`. Không được tự ghi `title`, `mail` hoặc thêm/xóa entry.
- **Account admin** có quyền ghi trong subtree mẫu, nhưng **chưa có quyền quản trị toàn directory**. Với triển khai thực tế, hãy thu hẹp tiếp theo operation, attribute và subtree; không dùng role này cho chức năng chỉ đọc.
- `userPassword` có rule riêng đặt **trước** rule thuộc tính công khai. `anonymous auth` chỉ cấp mức cần thiết cho quá trình xác thực theo chính sách LDAP, **không phải quyền đọc mật khẩu**.
- Rule `children` cho parent minh họa một phần quyền tạo/xóa trực tiếp. Nếu tạo entry ở OU con hoặc Move, phải kiểm tra parent đích cùng các mục tiêu `entry/children` khác.
- Các entry `svc-directory-reader` và `svc-account-admin` ở `ou=service` **cũng cần ACL riêng cho phép Bind theo phương thức được chọn**, nếu bạn xác thực bằng mật khẩu nằm trong directory. Đừng để rule ẩn `userPassword` làm hỏng Bind của chính tài khoản dịch vụ.
- Một entry có thể yêu cầu nhiều điều kiện quyền; đoạn ví dụ không thay thế kiểm tra cụ thể bằng `ldapsearch`, `ldapadd`, `ldapmodify` và `ldapdelete` trên directory test.

### Không dùng rootdn để kiểm thử ACL

Nếu dùng `cn=admin,dc=example,dc=org` làm OpenLDAP `rootdn` của database, các lệnh LDAP có thể **bỏ qua cơ chế ACL áp cho người dùng bình thường**. Do đó kiểm thử phải Bind bằng **đúng hai account không có đặc quyền rootdn**; Bind thành công với rootdn không chứng minh reader/admin rule đúng.

### Tách quyền đối với nhóm

Nhóm `groupOfNames` nằm dưới `ou=groups`. Nếu ứng dụng quản trị tài khoản còn sửa nhóm, cần ACL riêng cho `member` ở subtree nhóm và tài khoản `svc-group-manager` (nếu có). Không nên cấp quyền ghi `ou=groups` cho reader hoặc cho mọi admin nếu người quản lý tài khoản không có nhu cầu đó.

## 7. Hai ContextSource và hai LdapTemplate độc lập

Tại tầng Spring, sử dụng hai bộ credential ngay cả khi cả hai account kết nối cùng LDAP server. Đừng “nâng cấp” quyền bằng cách thay username/password của singleton `ContextSource` trước khi gọi method: nhiều request đồng thời có thể làm lẫn danh tính và khiến reader dùng credential admin.

`application.yml` (configuration namespace do ứng dụng định nghĩa):

~~~yaml
directory:
  url: ldaps://ldap.example.org:636
  base: dc=example,dc=org
  reader:
    bind-dn: cn=svc-directory-reader,ou=service,dc=example,dc=org
    password: "${LDAP_READER_PASSWORD}"
  account-admin:
    bind-dn: cn=svc-account-admin,ou=service,dc=example,dc=org
    password: "${LDAP_ACCOUNT_ADMIN_PASSWORD}"
~~~

Cấu hình trên **không phải** mặc định `spring.ldap.*` mà Spring Boot tự đọc. Ta sẽ dựng hai bean từ `directory.*`. Secret là biến môi trường của tiến trình chạy ứng dụng, hoặc được cấp bởi secret manager; không đặt giá trị thật trong file YAML, Docker image hoặc source control.

### JavaConfig: wiring tường minh

`config/DirectoryContextsConfig.java`:

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryContextsConfig {

    @Bean("directoryReaderContextSource")
    public LdapContextSource directoryReaderContextSource(
            @Value("${directory.url}") String url,
            @Value("${directory.base}") String base,
            @Value("${directory.reader.bind-dn}") String bindDn,
            @Value("${directory.reader.password}") String secret) {
        return createSource(url, base, bindDn, secret);
    }

    @Bean("accountAdminContextSource")
    public LdapContextSource accountAdminContextSource(
            @Value("${directory.url}") String url,
            @Value("${directory.base}") String base,
            @Value("${directory.account-admin.bind-dn}") String bindDn,
            @Value("${directory.account-admin.password}") String secret) {
        return createSource(url, base, bindDn, secret);
    }

    @Bean("directoryReaderTemplate")
    public LdapTemplate directoryReaderTemplate(
            @Qualifier("directoryReaderContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("accountAdminTemplate")
    public LdapTemplate accountAdminTemplate(
            @Qualifier("accountAdminContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    private static LdapContextSource createSource(
            String url, String base, String bindDn, String secret) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(secret);
        source.setReferral("throw"); // Không tự chuyển credential sang target lạ.
        return source;
    }
}
~~~

**Giải thích:**

| Bean | Bind DN | Mục đích |
| --- | --- | --- |
| `directoryReaderContextSource` | `svc-directory-reader` | Danh tính kết nối cho các hoạt động Search/Lookup. |
| `directoryReaderTemplate` | Reader context | Chỉ dùng trong `DirectoryReaderService`. |
| `accountAdminContextSource` | `svc-account-admin` | Danh tính kết nối cho Create/Modify/Remove được ủy quyền. |
| `accountAdminTemplate` | Admin context | Chỉ inject trong `AccountAdminService`. |

`LdapContextSource` là bean do Spring quản lý, vì vậy lifecycle sẽ gọi khởi tạo context phù hợp. Ví dụ dùng kết nối LDAPS; môi trường thật còn phải cấu hình truststore, timeout, giới hạn Search và chính sách network/connection pooling thích hợp.

**Không tạo `@Primary` cho admin template** để vô tình mọi service inject admin. Ở mỗi constructor, chỉ rõ `@Qualifier` của tài khoản đúng với mục đích. Nếu có repository do Spring Data LDAP tự sinh, cần kiểm tra chúng dùng `LdapTemplate` nào; mặc định `@EnableLdapRepositories` có thể tìm bean tên `ldapTemplate`.

## 8. Repository: tránh dùng nhầm template có quyền quản trị

Entity ODM có thể dùng:

~~~java
package com.example.directory.model;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    // Constructor/getter/setter trong project thực tế.
}
~~~

Nếu muốn repository chỉ phục vụ **tra cứu**, đặt interface trong package reader riêng:

~~~java
package com.example.directory.reader.repo;

import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.DirectoryPerson;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Cấu hình repository rõ ràng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.directory.reader.repo",
    ldapTemplateRef = "directoryReaderTemplate"
)
public class ReaderRepositoryConfig {
}
~~~

`ldapTemplateRef` là thuộc tính của `@EnableLdapRepositories` dùng khi có nhiều `LdapTemplate`. Nhờ vậy, repository đặt trong package reader **sử dụng credential reader**. Tuy nhiên `LdapRepository` vốn có phương thức CRUD; **mapping vào reader không làm biến mất các method `save/delete`** khỏi interface. ACL LDAP là chốt chặn; ở tầng API hãy chỉ công khai các service/method tra cứu cần thiết, không inject repository reader vào một workflow ghi.

Với thao tác quản trị có rủi ro, việc dùng `accountAdminTemplate` trực tiếp tại một service nhỏ và có review rõ ràng thường dễ kiểm soát hơn việc cho cả ứng dụng biết một repository có thể ghi. Nếu muốn admin repository riêng, cần tách package, `ldapTemplateRef` và kiểm thử bean wiring.

## 9. Tách API đọc danh bạ khỏi API quản trị

Một API nên có **hợp đồng dữ liệu** và **quyền riêng** cho từng use case.

| API | Caller authority | LDAP Bind | Mục đích |
| --- | --- | --- | --- |
| `GET /api/v1/people/{uid}` | `DIRECTORY_READ` | Reader | Tra cứu thông tin công khai được phép. |
| `POST /api/v1/people` | `ACCOUNT_ADMIN` | Account admin | Tạo entry hồ sơ LDAP. |
| `PATCH /api/v1/people/{uid}/title` | `ACCOUNT_ADMIN` | Account admin | Chỉnh một thuộc tính nghiệp vụ được chỉ định. |
| Đổi mật khẩu/khóa tài khoản | Quyền đặc biệt hơn, tùy chính sách | Workflow/credential riêng nếu cần | Không gộp vào endpoint chỉnh hồ sơ. |
| Quản lý nhóm | `GROUP_ADMIN` hoặc chính sách tương đương | Group manager, nếu tách | Chỉ sửa `member` ở nhóm được ủy quyền. |

Đừng trả thẳng `DirectoryPerson` làm JSON: entity có thể được mở rộng chứa DN, thuộc tính nội bộ và thông tin không được phép công bố.

### DTO đọc và DTO tạo riêng

`api/PersonResponse.java`:

~~~java
package com.example.directory.api;

public record PersonResponse(
        String uid,
        String fullName,
        String surname,
        String email,
        String jobTitle
) {}
~~~

`api/CreatePersonRequest.java`:

~~~java
package com.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePersonRequest(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9._-]{2,31}")
        String uid,

        @NotBlank @Size(max = 120)
        String fullName,

        @NotBlank @Size(max = 80)
        String surname,

        @NotBlank @Email @Size(max = 254)
        String email
) {}
~~~

Request chỉ có các trường cần thiết. Không nhận `dn`, `objectClass`, `userPassword`, `memberOf`, `employeeNumber` hay toàn bộ attributes từ client.

**Hợp đồng “tạo hồ sơ” không đồng nghĩa “cấp quyền đăng nhập”.** `inetOrgPerson` có thể được tạo mà chưa có `userPassword`; tài khoản đăng nhập, mật khẩu, MFA, disable/enable phải thuộc một quy trình riêng phù hợp chính sách directory.

## 10. DirectoryReaderService chỉ dùng quyền đọc

Service đọc nhận reader template, không có reference tới admin template:

`service/DirectoryReaderService.java`:

~~~java
package com.example.directory.service;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import com.example.directory.api.PersonResponse;

@Service
public class DirectoryReaderService {

    private final LdapTemplate reader;

    public DirectoryReaderService(
            @Qualifier("directoryReaderTemplate") LdapTemplate reader) {
        this.reader = reader;
    }

    @PreAuthorize("hasAuthority('DIRECTORY_READ')")
    public PersonResponse findByUid(String uid) {
        validateUid(uid);
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return reader.lookup(
                dn,
                new String[] { "uid", "cn", "sn", "mail", "title" },
                (AttributesMapper<PersonResponse>) attrs ->
                    new PersonResponse(
                        value(attrs, "uid"),
                        value(attrs, "cn"),
                        value(attrs, "sn"),
                        value(attrs, "mail"),
                        value(attrs, "title"))
        );
    }

    private static String value(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : (String) attr.get();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

Điểm an toàn của service:

1. Dùng **reader context** ngay ở constructor, không có quyền sử dụng credential admin.
2. `@PreAuthorize` kiểm tra **caller** trước method khi Spring method security đã bật.
3. Client chỉ gửi `uid`; DN được xây dưới `ou=people` bằng `LdapNameBuilder`.
4. `lookup` chỉ yêu cầu **năm thuộc tính đã phê duyệt**. Không trả raw entity/context.
5. Nếu một thuộc tính bị ACL ẩn, mapper nhận giá trị thiếu; không được mặc định điều đó có nghĩa người dùng không có thuộc tính.
6. Nếu không tìm thấy entry, Spring LDAP thường ném `NameNotFoundException`; handler API phân loại đúng 404 hoặc lỗi cấu hình.

Đây là Lookup theo DN với UID được validate. Khi thiết kế **Search** nhiều người, dùng `LdapQueryBuilder` để escape filter thay vì ghép `"(uid=" + uid + ")"`:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(100)
        .timeLimit(1000)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(requestUid);
~~~

`countLimit` và `timeLimit` là giới hạn Search, không thay thế timeout TCP/socket hoặc quyền ACL. Bản Search rỗng có thể xuất phát từ filter không khớp hoặc thiếu quyền; phải xác minh bằng chính reader account.

## 11. AccountAdminService dùng quyền ghi cho thao tác cụ thể

Service quản trị dùng **admin template** nhưng không nhận raw LDAP modifications/attributes từ HTTP client.

`service/AccountAdminService.java`:

~~~java
package com.example.directory.service;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import com.example.directory.api.CreatePersonRequest;

@Service
public class AccountAdminService {

    private final LdapTemplate admin;

    public AccountAdminService(
            @Qualifier("accountAdminTemplate") LdapTemplate admin) {
        this.admin = admin;
    }

    @PreAuthorize("hasAuthority('ACCOUNT_ADMIN')")
    public void createProfile(CreatePersonRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("Request is required");
        }

        validateUid(request.uid());

        // Bean Validation trong controller + kiểm tra ở service
        // vì service cũng có thể được gọi từ những nguồn khác.
        String cn = required(request.fullName());
        String sn = required(request.surname());
        String mail = required(request.email());

        Name dn = personDn(request.uid());

        Attributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");

        attrs.put(classes);
        attrs.put("uid", request.uid());
        attrs.put("cn", cn);
        attrs.put("sn", sn);
        attrs.put("mail", mail);

        // Tạo entry hồ sơ; KHÔNG nhận mật khẩu, objectClass, DN
        // hay quyền nhóm từ payload client.
        admin.bind(dn, null, attrs);
    }

    @PreAuthorize("hasAuthority('ACCOUNT_ADMIN')")
    public void changeJobTitle(String uid, String title) {
        validateUid(uid);
        String newTitle = required(title);

        ModificationItem replaceTitle = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("title", newTitle));

        // Chỉ thay một thuộc tính được phép.
        admin.modifyAttributes(
                personDn(uid),
                new ModificationItem[] { replaceTitle });
    }

    private static Name personDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }

    private static String required(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Required value is blank");
        }
        return value.strip();
    }
}
~~~

Đoạn mã minh họa **quyền ghi có giới hạn**, không phải ứng dụng quản trị tài khoản hoàn chỉnh:

- `admin.bind(dn, null, attrs)` trong `LdapTemplate` nghĩa là **Add entry**, khác với LDAP BindRequest dùng để xác thực tài khoản dịch vụ.
- `modifyAttributes` chỉ thay `title`; không ghi lại toàn entry và không đổi `uid`/DN.
- `@PreAuthorize` từ chối người gọi không có authority `ACCOUNT_ADMIN`.
- Directory vẫn kiểm tra schema, ACL, DN trùng, constraint và trạng thái kết nối.
- Create không đặt mật khẩu hay kích hoạt login. Việc cấp tài khoản đăng nhập phải có luồng/provisioning khác được kiểm soát.
- `required` chỉ kiểm tra giá trị rỗng. Giới hạn độ dài/định dạng từ Bean Validation hoặc policy mạnh hơn phải được thực thi cho cả các đường gọi không đi qua controller.

### Vì sao reader service không gọi admin “nếu đọc thất bại”?

Không triển khai phương án:

~~~java
// Anti-pattern: thiếu quyền thì âm thầm thử lại bằng admin!
try {
    return directoryReader.findByUid(uid);
} catch (Exception e) {
    return adminTemplate.lookup(...);
}
~~~

Một lỗi `insufficientAccessRights (50)` hoặc Search không thấy thuộc tính do ACL có thể biểu thị **chính sách cấm truy cập**. Tự fallback sang admin sẽ biến cơ chế kiểm soát bảo mật thành “lỗi có thể bỏ qua”.

Nếu chức năng quản trị thật sự cần đọc thuộc tính đặc quyền, nó phải đi qua **endpoint/service riêng có authorization và audit**, không mượn lỗi reader làm tín hiệu nâng quyền.

## 12. Bật Spring Security Method Security

Để `@PreAuthorize` thực thi, ứng dụng phải bật method security:

~~~java
package com.example.directory.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodAuthorizationConfig {
}
~~~

Dependency cho ví dụ Spring Boot 3+ gồm `spring-boot-starter-data-ldap`, `spring-boot-starter-security`, `spring-boot-starter-web` và `spring-boot-starter-validation`.

- `hasAuthority('DIRECTORY_READ')` kiểm tra chính xác tên authority trong `Authentication` của người gọi.
- `hasAuthority('ACCOUNT_ADMIN')` chỉ cho phép quản trị theo policy đang dùng.
- Không tự động gán `ACCOUNT_ADMIN` chỉ vì người gọi đã đăng nhập.
- Method security bổ sung cho route security; đừng dựa chỉ vào việc ẩn nút “quản trị” trên frontend.
- `@PreAuthorize` qua **Spring-managed proxy**: nếu một method cùng bean tự gọi method khác, lời gọi nội bộ có thể bỏ qua advice trong chế độ proxy mặc định. Thiết kế service boundary sao cho caller đi qua bean proxy.

Cần cấu hình nguồn xác thực HTTP (OIDC/JWT/session, tùy hệ thống), authorization theo đối tượng và chính sách CSRF phù hợp với client. Không nên vô hiệu hóa CSRF cho ứng dụng dùng cookie/session chỉ vì API đang truy cập LDAP.

### API ví dụ

~~~java
package com.example.directory.web;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.directory.api.CreatePersonRequest;
import com.example.directory.api.PersonResponse;
import com.example.directory.service.DirectoryReaderService;
import com.example.directory.service.AccountAdminService;

@RestController
@RequestMapping("/api/v1/people")
public class PeopleController {

    private final DirectoryReaderService reader;
    private final AccountAdminService admin;

    public PeopleController(
            DirectoryReaderService reader,
            AccountAdminService admin) {
        this.reader = reader;
        this.admin = admin;
    }

    @GetMapping("/{uid}")
    public PersonResponse get(@PathVariable String uid) {
        return reader.findByUid(uid);
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreatePersonRequest request) {
        admin.createProfile(request);
        return ResponseEntity.status(201).build();
    }

    @PatchMapping("/{uid}/title")
    public ResponseEntity<Void> changeTitle(
            @PathVariable String uid,
            @RequestBody String title) {
        admin.changeJobTitle(uid, title);
        return ResponseEntity.noContent().build();
    }
}
~~~

Ví dụ chỉ minh họa ranh giới gọi service. Trong hệ thống thật, hãy dùng `UpdateTitleRequest` với validation, JSON chuẩn và giới hạn kích thước body; xử lý `NameNotFoundException` thành 404 khi phù hợp, `NameAlreadyBoundException` thành 409, lỗi directory thành response an toàn. Đồng thời thực hiện xác thực/ủy quyền trước khi controller nhận các thao tác nhạy cảm.

## 13. Tác động của ACL lên kết quả đọc

Một thiết kế tốt phải tránh hai nhầm lẫn sau:

**(1) Không nhìn thấy thuộc tính ≠ thuộc tính không tồn tại.**

Nếu reader hỏi `userPassword`, directory có thể không trả thuộc tính đó, thay vì gửi lỗi 50 trực tiếp. Với một số server, thiếu quyền Search còn có thể làm kết quả filter rỗng. Do đó, kiểm thử phân quyền không chỉ assert “request không ném exception”; cần xác minh đúng **tập thuộc tính nhìn thấy**.

**(2) Không tìm thấy entry ≠ chắc chắn entry không tồn tại.**

Directory có thể che sự tồn tại của một DN, hoặc Search base/scope của client chưa phù hợp. Thông báo HTTP cần phản ánh hợp đồng ứng dụng và bảo vệ dữ liệu, không đưa ra kết luận tuyệt đối dựa trên một response từ reader account.

### Chỉ số thuộc tính công khai

Ví dụ response người dùng:

~~~json
{
  "uid": "lan",
  "fullName": "Nguyen Thi Lan",
  "surname": "Nguyen",
  "email": "lan@example.org",
  "jobTitle": "Backend Developer"
}
~~~

Không trả:

~~~json
{
  "dn": "uid=lan,ou=people,dc=example,dc=org",
  "userPassword": "secret-value",
  "employeeNumber": "E1042",
  "memberOf": ["cn=admins,ou=groups,dc=example,dc=org"]
}
~~~

Khối thứ hai chỉ minh họa **các trường không được cho vào DTO công khai**. LDAP `userPassword` có thể là chuỗi hash hoặc giá trị theo định dạng riêng; dù có vẻ “không phải mật khẩu gốc”, **vẫn là dữ liệu xác thực cần bảo vệ**.

## 14. Kiểm thử bằng ldapwhoami và ldapsearch

Trong directory test, thiết lập hai tài khoản Bind thật (không phải rootdn), ACL và fixture người dùng Lan. Dùng LDAPS với certificate hợp lệ. Các lệnh sau chạy bằng công cụ LDAP CLI tương thích OpenLDAP.

### 14.1. Xác minh danh tính Reader

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W
~~~

Dự kiến hiển thị danh tính đã xác thực. `-W` yêu cầu nhập mật khẩu theo lời nhắc, tránh đưa secret vào shell history/process list.

**Không kết luận tài khoản có quyền chỉ đọc chỉ từ việc Bind thành công.** Phải kiểm tra các operation khác.

### 14.2. Reader tìm được danh bạ

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn objectClass uid cn sn mail title
~~~

Kỳ vọng nhận Lan cùng các thuộc tính danh bạ được phép. Các thuộc tính khác có thể không hiển thị do ACL hoặc do không yêu cầu.

### 14.3. Reader không được đọc thuộc tính mật khẩu

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" -s base \
  "(objectClass=inetOrgPerson)" \
  dn uid userPassword
~~~

Kỳ vọng **không được trả giá trị `userPassword`**. Nếu directory từ chối thao tác hoặc ẩn entry, phải ghi nhận loại lỗi thực tế; mục tiêu bảo mật là **không tiết lộ giá trị**, không bắt buộc một mã lỗi duy nhất.

### 14.4. Reader phải bị chặn Modify

Tạo file thử nghiệm `title-change.ldif` trong môi trường test:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
changetype: modify
replace: title
title: Principal Engineer
-
~~~

Gọi bằng **reader Bind DN**:

~~~bash
ldapmodify -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W \
  -f title-change.ldif
~~~

Kỳ vọng thao tác **thất bại** do quyền không đủ, thường với `Insufficient access (50)`. Sau đó dùng tài khoản kiểm thử được phép đọc để xác nhận `title` **không bị thay đổi**.

**Không áp dụng bài thử sửa trên production.** Reader bị chặn cũng cần kiểm tra Add/Delete/Modify DN, không chỉ một Modify đơn lẻ.

### 14.5. Admin được phép đúng nghiệp vụ

Sử dụng cùng file `title-change.ldif` nhưng Bind bằng `cn=svc-account-admin,...`:

~~~bash
ldapmodify -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-account-admin,ou=service,dc=example,dc=org" -W \
  -f title-change.ldif
~~~

Trên directory test có ACL đúng, thao tác có thể thành công. Nếu bị `Object class violation (65)` hoặc `Insufficient access (50)`, kiểm tra schema/ACL. **Không sửa bằng cách đổi ứng dụng thành Bind rootdn**.

Sau đó đọc lại bằng reader và xác nhận chỉ `title` đổi, `uid`/DN và thuộc tính khác không bị ảnh hưởng.

## 15. Ma trận kiểm thử phân tách quyền

Kiểm thử cả **HTTP authorization** và **LDAP server-side ACL**. Một bộ test chỉ mock `LdapTemplate` không chứng minh ACL thực tế.

| Ca kiểm thử | Reader identity | Admin identity | Kết quả mong đợi |
| --- | --- | --- | --- |
| Bind bằng password đúng | Có thể Bind | Có thể Bind | Danh tính riêng, không nhầm credential. |
| Search `uid=lan` | Cho phép | Có thể cho phép | Reader trả đúng DTO công khai. |
| Đọc `userPassword` | **Không** | Thường không cần quyền đọc | Không lộ giá trị. |
| Modify `title` | **Bị từ chối** | Cho phép theo policy | Server kiểm tra ACL. |
| Add `inetOrgPerson` vào `ou=people` | **Bị từ chối** | Có thể cho phép | Kiểm tra quyền `children` và `entry`. |
| Delete entry người dùng | **Bị từ chối** | Chỉ khi nghiệp vụ cấp quyền | Không cấp quyền xóa quá rộng. |
| Rename/Move entry | **Bị từ chối** | Chỉ trong OU được phép | Kiểm tra ACL nguồn/đích. |
| Sửa `member` ở `ou=groups` | **Bị từ chối** | Không mặc định | Dành cho group manager nếu có. |
| Client HTTP thiếu `DIRECTORY_READ` gọi GET | – | – | HTTP 403, không gọi LDAP. |
| Client HTTP chỉ có `DIRECTORY_READ` gọi POST | – | – | HTTP 403, không gọi admin template. |
| Client HTTP có `ACCOUNT_ADMIN` gọi POST | – | – | Gọi đúng admin template và tuân schema/ACL. |
| Client gửi `userPassword` vào Create DTO | – | – | JSON ngoài hợp đồng bị từ chối hoặc không được ánh xạ; không ghi password. |
| Sai mật khẩu reader | Bind thất bại | Admin vẫn hoạt động | Không tự fallback sang credential admin. |
| Sai mật khẩu admin | Reader vẫn tra cứu | Bind thất bại | Không tự nâng/cấp lại secret từ source khác. |
| ACL reader đọc được thuộc tính lạ | **Không đạt** | – | Báo lỗi policy, sửa ACL. |
| TLS hết hạn hoặc host mismatch | Không kết nối | Không kết nối | Không bỏ kiểm tra certificate. |

### 15.1. Test Spring Security bằng MockMvc

Khi dùng `spring-security-test`, có thể viết test chỉ xác minh **quyền người gọi** mà không liên hệ LDAP thật. Ví dụ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DirectoryHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(authorities = "DIRECTORY_READ")
    void directoryReaderCannotCallAdminApi() throws Exception {
        // Khi security và route policy áp dụng đúng, POST sẽ bị
        // chặn trước khi service quản trị được thực thi.
        mvc.perform(org.springframework.test.web.servlet.request
                .MockMvcRequestBuilders.post("/api/v1/people")
                .contentType("application/json")
                .content("{}"))
           .andExpect(status().isForbidden());
    }
}
~~~

**Lưu ý test web:** tùy loại xác thực HTTP, CSRF và route security, test cần cấu hình `csrf()` cho request thay đổi trạng thái hoặc dùng token đúng dạng. Một response 403 do **thiếu CSRF** không chứng minh `@PreAuthorize` đã bảo vệ endpoint. Để test quyền chính xác, phải cung cấp đầy đủ các điều kiện HTTP khác và **xác minh service admin không được gọi** (ví dụ mock/spy). Code trên là khung minh họa, không phải đủ mọi cấu hình bảo mật cho mọi loại API.

### 15.2. Test tích hợp LDAP phải dùng hai Bind DN thật

Thiết lập test directory (container/directory dành riêng), tạo hai account service, đưa ACL vào môi trường test rồi thực hiện các phép thử:

1. Reader Bind thành công.
2. Reader Search đọc được `uid,cn,sn,mail,title` theo chính sách.
3. Reader không đọc được `userPassword`.
4. Reader Modify `title` **thất bại**, dữ liệu không đổi.
5. Reader Add/Delete/Rename **thất bại**.
6. Admin Bind thành công, có thể Modify `title` và tạo entry ở nhánh được phép.
7. Admin không thể thay cấu hình `cn=config` hoặc quyền root của server.
8. Admin không thể ghi nhóm/nhánh ngoài phạm vi nếu chính sách không cấp.
9. Kiểm tra thuộc tính mới được bổ sung vào schema/entity không tự trở thành thuộc tính công khai cho reader.
10. Đánh giá lại toàn bộ bằng **đúng ACL đang chạy**, không chỉ kết quả của mock hoặc test đăng nhập.

Có thể dùng JUnit 5 và `LdapTemplate` đã được cấu hình trong ứng dụng để viết integration test. Nếu test tạo/xóa entry, nên dùng fixture duy nhất và dọn sau test; không đụng đến tài khoản thật.

## 16. Sai sót phổ biến khi phân quyền

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Dùng `rootdn`/admin cho cả Search và CRUD | Lỗi reader có thể biến thành thao tác phá hoại; ACL test không có ý nghĩa. | Reader và admin service account tách riêng, không rootdn. |
| Chỉ phân quyền ở HTTP Controller | Scheduler hoặc service nội bộ có thể gọi logic ghi ngoài đường HTTP. | Method security/service boundary + LDAP ACL. |
| Chỉ phân quyền ở Java | Một đường truy cập khác có thể bypass logic app. | Thực thi ACL tại directory. |
| Bind thành công = có quyền quản trị | Sai ranh giới identity và authorization. | Kiểm tra operation/attribute cụ thể qua ACL. |
| `@Entry(base)` được xem là hàng rào bảo mật | Chỉ là metadata ánh xạ, không ngăn account đọc/ghi nhánh khác. | Đặt ACL trên server và cố định search/write base trong code. |
| `@Primary` trỏ vào admin ContextSource | Dependency không có qualifier có thể dùng admin. | Dùng qualifier tường minh, không chọn admin làm default. |
| Thay username/password singleton theo request | Nhầm credential giữa các thread, leak quyền. | ContextSource riêng bất biến theo vai trò. |
| Đọc được `userPassword` vì “chỉ là hash” | Lộ dữ liệu xác thực nhạy cảm. | Tách thuộc tính xác thực, không cấp read. |
| Tạo entity từ JSON rồi `repository.save` | Mass assignment và ghi những thuộc tính không cần thiết. | Request DTO và mapper theo allowlist. |
| Fallback sang admin khi Search bị ACL từ chối | Vượt kiểm soát quyền. | Fail closed, báo lỗi hoặc yêu cầu quyền đúng. |
| Dùng `ldap://` với Simple Bind | Lộ credential trên đường truyền không mã hóa. | LDAPS/StartTLS, kiểm tra certificate và hostname. |
| Thêm ACL deny sau rule `access to * by * read` | Rule rộng có thể thắng trước. | Rà soát thứ tự và test âm tính. |
| Cho account admin quyền sửa `cn=config` | Tăng phạm vi tấn công và cấu hình hạ tầng. | Tách directory operator khỏi application operator. |

## 17. Mật khẩu, khóa tài khoản và quản lý nhóm là các use case riêng

Để tránh nhầm giữa **hồ sơ danh bạ** và **tài khoản xác thực**, cần phân định các thao tác nhạy cảm:

### 17.1. Password reset

Thay mật khẩu không giống đổi `title`. Directory có thể hỗ trợ cơ chế Password Modify Extended Operation (RFC 3062), password policy và cách băm/lưu trữ riêng. Thiết kế một workflow reset có:

- Kiểm tra danh tính người yêu cầu và quyền reset.
- Yêu cầu kiểm soát đặc biệt (MFA, approval, audit) theo chính sách.
- Tài khoản/Bind context riêng chỉ đủ quyền thay thông tin xác thực mục tiêu.
- Truyền secret qua TLS, không log/plaintext lưu trữ tại application.
- Không cho client chỉnh trực tiếp `userPassword` qua endpoint cập nhật hồ sơ.

Không nên coi việc đọc `userPassword` là điều kiện cần cho password reset. Nhiều directory áp quy tắc quyền và password policy riêng; server có thể thực hiện thay đổi mà không tiết lộ giá trị cũ cho ứng dụng.

### 17.2. Khóa/mở tài khoản

Không có một thuộc tính “account disabled” chung có cùng ngữ nghĩa trên mọi LDAP server. OpenLDAP với password policy overlay, Active Directory và các directory khác có schema/operational attribute riêng.

Vì vậy, không đưa `enabled: false` từ DTO rồi tự đoán sẽ map thành một attribute cụ thể. Phải nêu rõ directory type, schema, quyền quản trị, hành vi Bind sau khi khóa và kiểm thử với server tương ứng.

### 17.3. Quản lý nhóm

Thêm/xóa thành viên `groupOfNames` cần cập nhật **thuộc tính `member` của entry nhóm**. Đó không phải việc người gọi có quyền đọc danh bạ tự động được phép thực hiện. Nên dùng group manager role/service account, ACL theo nhóm và `ModificationItem` để cập nhật chọn lọc một giá trị DN.

Thay đổi nhóm quyền có thể ảnh hưởng đến ủy quyền ở nhiều hệ thống: yêu cầu audit và đôi khi approvals cao hơn việc đổi email/chức danh.

## 18. Xử lý lỗi và khả năng vận hành

Tách reader/admin cũng giúp phân loại lỗi chính xác:

| Tình huống | Phản ứng phù hợp |
| --- | --- |
| Người gọi không có HTTP authority | HTTP 403, chặn trước khi gọi LDAP. |
| Reader Bind sai mật khẩu | Lỗi tích hợp/cấu hình, **không** retry bằng admin. |
| Reader Search không có entry | Có thể trả 404 cho lookup hoặc `[]` cho list, tùy hợp đồng; kiểm tra base/ACL. |
| Reader bị LDAP 50 khi thử Modify | **Kỳ vọng bảo mật**: thao tác phải bị chặn; ghi nhận test, không nâng quyền. |
| Admin bị LDAP 50 khi Modify hợp lệ | Kiểm tra ACL/schema/Bind DN, không dùng rootdn để sửa nhanh. |
| Tạo entry trùng DN (LDAP 68) | HTTP 409 theo use case, không ghi đè entry cũ. |
| Sai schema (`objectClassViolation 65`) | Lỗi dữ liệu/mapping; kiểm tra `cn`/`sn`, không retry mù. |
| Referral ngoài topology cho phép | Không chuyển secret tự động; fail closed. |
| LDAP không kết nối/TLS lỗi | HTTP 503 hoặc mã lỗi phù hợp; không báo “người dùng không tồn tại”. |

### Audit tối thiểu

Nên ghi: request ID, người gọi HTTP (identifier đã được phép), operation, entry/group mục tiêu ở mức phù hợp chính sách, service account/vai trò đã dùng và kết quả. Không log mật khẩu, `userPassword`, token, raw LDAP exception chứa thông tin nhạy cảm hay dữ liệu cá nhân không cần thiết.

Cần cảnh báo khi **reader cố Modify/Add/Delete** hoặc khi **admin credential được dùng ngoài endpoint quản trị**. Đây có thể là lỗi lập trình hoặc dấu hiệu xâm nhập.

### Xoay vòng secret không làm gián đoạn ranh giới quyền

Reader và admin có secret riêng nên có thể rotate độc lập. Tuy nhiên, đổi giá trị trong secret manager không nhất thiết tự cập nhật những `LdapContextSource` đang sống; cần xác định cơ chế refresh/restart an toàn và kiểm chứng bằng Bind trong môi trường test.

Không cấu hình fallback để khi secret reader sai sẽ tự thử admin. Các lỗi cấu hình phải được phát hiện và sửa ở tầng vận hành.

## 19. Checklist trước khi triển khai

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| Service account | Có ít nhất reader và account admin tách biệt; không dùng rootdn. |
| ACL dữ liệu | Reader chỉ được Search/Read tập thuộc tính danh bạ được phê duyệt. |
| ACL ghi | Reader bị từ chối Modify/Add/Delete/Rename. |
| ACL nhánh | Admin chỉ được ghi subtree/attribute cần thiết; operator cấu hình directory là vai trò khác. |
| Mật khẩu | `userPassword` không xuất hiện trong response reader và không log. |
| Spring wiring | `@Qualifier` rõ ràng, repository đọc dùng `ldapTemplateRef` của reader. |
| HTTP security | `@EnableMethodSecurity` và `@PreAuthorize` được kích hoạt; role tests kiểm tra cả chấp nhận/từ chối. |
| Validation | Request DTO không nhận DN/`objectClass`/thuộc tính quyền tùy ý; DN/filter builder an toàn. |
| TLS | LDAPS hoặc StartTLS, CA và hostname được xác minh. |
| Referral | Không tự chuyển credential sang host ngoài allowlist. |
| Testing | Có integration test bằng reader/admin Bind DN thật, test âm tính sau mỗi thay đổi ACL. |
| Audit | Có phân biệt actor HTTP và Bind account, không log secret. |
| Failure | Không tự fallback sang admin hoặc che lỗi thành Search rỗng. |
| Review | ACL ordering, default policy, password policy và rootdn đã được rà soát. |

## 20. Bài tập thực hành

**Bài 1 — Ma trận quyền:** thêm một vai trò `svc-profile-editor` chỉ được sửa `title` và `mail` nhưng không được tạo/xóa account. Viết bảng quyền cho cả reader, editor và admin; xác định các ACL cần có ở `entry` và từng attribute.

**Bài 2 — Test quyền âm tính:** dùng reader account cố `modifyAttributes` trên `title` của `uid=lan`. Kiểm tra thao tác thất bại và title không đổi. Sau đó làm với admin account trên directory test để so sánh.

**Bài 3 — Chặn thông tin nhạy cảm:** thêm một thuộc tính nội bộ giả vào entry test. Kiểm tra LDAP ACL không trả thuộc tính đó cho reader và response DTO cũng không chứa nó.

**Bài 4 — Repository wiring:** tạo một `DirectoryPersonRepository` dưới package riêng và cấu hình `@EnableLdapRepositories(ldapTemplateRef="directoryReaderTemplate")`. Viết kiểm thử đọc thành công, `save` bị LDAP từ chối theo ACL reader.

**Bài 5 — Kiểm thử phân quyền HTTP:** với Spring Security Test, xác nhận user chỉ có `DIRECTORY_READ` được GET nhưng bị từ chối POST/PATCH. Đồng thời assert admin service không bị gọi khi thiếu quyền.

**Bài 6 — Quản trị tài khoản chuyên biệt:** đề xuất workflow password reset dùng directory-specific extension/policy, không lấy lại userPassword cũ, không đưa password vào endpoint quản lý hồ sơ.

**Bài 7 — Kiểm tra ACL ordering:** trong một directory test, thử hoán đổi rule hạn chế `userPassword` và rule rộng. Giải thích vì sao thứ tự có thể thay đổi kết quả, sau đó thiết kế lại default deny hợp lý.

## 21. Câu hỏi tự ôn tập

1. Vì sao không dùng cùng một Bind account có quyền admin cho cả Search và CRUD?
2. Người gọi HTTP có authority `ACCOUNT_ADMIN` có cần biết mật khẩu LDAP admin không?
3. Tài khoản reader Bind thành công có chứng minh nó được quyền Modify không?
4. `@Entry(base="ou=people")` có phải ACL giới hạn nhánh không?
5. Vì sao cần phân biệt quyền `search` và `read` trong OpenLDAP?
6. `entry` và `children` ảnh hưởng thế nào đến Add/Delete/Rename?
7. Vì sao rule cho `userPassword` thường đặt riêng trước rule thuộc tính danh bạ?
8. Nếu API Search không trả `mail`, có thể kết luận chắc chắn entry không có email không?
9. Một `LdapRepository` được gắn reader template có còn method `save/delete` không? Vì sao LDAP ACL vẫn cần?
10. `@EnableMethodSecurity` có tự bật chỉ nhờ thêm dependency Security không?
11. Vì sao không fallback sang admin template khi reader gặp `insufficientAccessRights`?
12. Khi nào cần service account riêng cho password reset hoặc group membership?
13. Vì sao tài khoản admin ứng dụng không nên là OpenLDAP `rootdn`?
14. Vì sao TLS giúp bảo vệ credential nhưng **không thay thế** ACL?
15. Một bộ test chỉ dùng mock có chứng minh ACL trên server đã đúng không?

**Ghi nhớ:** **đọc danh bạ** và **quản trị tài khoản** là hai quyền nghiệp vụ khác nhau. Tại Spring, dùng service, `LdapTemplate`/`ContextSource`, DTO và HTTP authority riêng; tại LDAP, dùng Bind DN có quyền tối thiểu và ACL giới hạn **subtree + entry + thuộc tính + operation**. Luôn kiểm thử quyền bị từ chối bằng tài khoản reader thật, không dùng rootdn để “chứng minh” phân quyền.

### Tài liệu tham khảo

- [OpenLDAP 2.6 Administrator's Guide – Access Control](https://www.openldap.org/doc/admin26/access-control.html): mô hình ACL, các mức `auth/search/read/write`, `entry`, `children`, thứ tự rule và tình huống rootdn.
- [OpenLDAP 2.6 Administrator's Guide](https://www.openldap.org/doc/admin26/guide.html): triển khai LDAP, schema, bảo mật và vận hành.
- [Spring LDAP – Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `LdapContextSource`, Bind DN, credential và `LdapTemplate`.
- [Spring LDAP – LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `lookup`, `search`, `bind` và `modifyAttributes`.
- [Spring Data LDAP – Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories` và `ldapTemplateRef` khi dùng nhiều template.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
- [RFC 4511 – LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Search, Modify, Add, Delete và mã kết quả LDAP.
- [RFC 4512 – LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, entry, objectClass và schema.
- [RFC 4513 – LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): các phương thức Bind và yêu cầu bảo mật.
- [RFC 4514 – LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp và escaping DN.
- [RFC 4515 – LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escaping giá trị filter.
- [RFC 3062 – LDAP Password Modify Extended Operation](https://www.rfc-editor.org/rfc/rfc3062): tùy chọn thay mật khẩu chuyên biệt, phụ thuộc hỗ trợ của directory.
