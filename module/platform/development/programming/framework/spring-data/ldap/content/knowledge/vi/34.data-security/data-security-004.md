# Phân quyền tài khoản dịch vụ theo nguyên tắc tối thiểu

## 1. Bài toán: một ứng dụng có thể làm gì với LDAP?

Trong **Spring Data LDAP**, ứng dụng Java thường kết nối đến dịch vụ thư mục bằng một danh tính kỹ thuật, gọi là **tài khoản dịch vụ** (*service account*). Thông qua `ContextSource`, `LdapTemplate` hoặc `LdapRepository`, ứng dụng có thể tìm kiếm entry, đọc các thuộc tính, tạo/sửa/xóa người dùng, cập nhật thành viên nhóm và đôi khi tác động đến thông tin dùng để xác thực.

Nếu dùng tài khoản quản trị LDAP cho mọi chức năng, một lỗi lập trình, lộ secret hoặc lỗ hổng ở API có thể biến thành quyền thay đổi **toàn bộ directory**. Nguyên tắc **quyền tối thiểu** (*least privilege*) yêu cầu cấp cho từng tài khoản **đúng phạm vi DN, loại thao tác và tập thuộc tính cần thiết**, không cấp các quyền chỉ để “khỏi bị lỗi”.

Bài học thuộc chương **Bảo mật dữ liệu** của module `SPRING_DATA_LDAP`. Người học sẽ liên hệ bảo mật LDAP với DN, `objectClass`, schema, repository/ODM, CRUD, filter an toàn, kết nối TLS và kiểm thử trên directory thực.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt danh tính **người dùng HTTP**, **tài khoản bind LDAP** và **quản trị viên directory**.
2. Thiết kế ma trận quyền theo **OU/subtree, LDAP operation, attribute và đối tượng đích**.
3. Tách tài khoản chỉ đọc khỏi tài khoản sửa hồ sơ hoặc cấp membership khi nghiệp vụ yêu cầu.
4. Giải thích vì sao `ContextSource.getReadOnlyContext()`, `@Transactional`, DTO validation và `@PreAuthorize` **không thay thế ACL trên LDAP server**.
5. Cấu hình Spring Boot/Spring LDAP không hard-code credentials; không tự động dùng admin bind cho repository.
6. Kiểm chứng **cả quyền được phép và quyền bị từ chối** bằng integration test và công cụ LDAP.
7. Lập quy trình xoay vòng secret, quan sát truy cập và rà soát định kỳ.

## 2. Ví dụ hệ thống và phạm vi dữ liệu

Giả sử doanh nghiệp có directory:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=linh                    (nhân viên)
│   ├── uid=an
│   └── uid=binh
├── ou=groups
│   ├── cn=developers               (nhóm nghiệp vụ)
│   └── cn=admins                   (nhóm nhạy cảm)
└── ou=service-accounts
    ├── uid=svc-people-reader
    ├── uid=svc-profile-editor
    └── uid=svc-group-maintainer
```

Entry người dùng:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
telephoneNumber: +84-28-5555-0101
```

Mỗi entry được định danh bằng **DN**. Chẳng hạn `uid=linh,ou=people,dc=example,dc=org` khác `uid=linh,ou=service-accounts,dc=example,dc=org`; quyền cho một subtree không tự lan sang subtree khác. Attribute `objectClass` và schema quy định những field nào hợp lệ hoặc bắt buộc, **nhưng schema không quyết định tài khoản nào được đọc/ghi**. Đó là trách nhiệm của cơ chế phân quyền trên LDAP server.

Giả sử ứng dụng có ba chức năng:

- **Tra cứu nhân viên:** tìm theo UID, hiển thị `cn`, `sn`, `mail`; không cần đọc mật khẩu hay sửa nhóm.
- **Sửa thông tin liên hệ:** chỉ được cập nhật `mail` và `telephoneNumber` của người dùng trong `ou=people`.
- **Quản lý membership nhóm developers:** chỉ thêm/gỡ giá trị `member` ở nhóm `cn=developers`; không được sửa nhóm `cn=admins`.

Nếu một tài khoản đơn lẻ có cả ba quyền, một đoạn code bị khai thác ở chức năng tra cứu có thể lạm dụng cả khả năng sửa nhóm. Tách danh tính dịch vụ giúp giảm **phạm vi tác động** (*blast radius*) khi một thành phần gặp sự cố.

## 3. Ba ranh giới quyền khác nhau

```text
Người dùng HTTP
     |
     | (1) Xác thực và phân quyền API: Spring Security
     v
Application Service (Spring Boot)
     |
     | (2) Quyền được phép trong code/DTO/use case
     v
LdapRepository / LdapTemplate
     |
     | (3) LDAP bind identity + TLS
     v
Directory Server
     |
     | LDAP ACL / ACI / security descriptor
     v
Entry, attribute, DN và quyền thao tác thực tế
```

| Tầng | Câu hỏi trả lời | Cơ chế ví dụ |
| --- | --- | --- |
| Người dùng/API | Ai được gọi endpoint cập nhật hồ sơ? | Spring Security, role/authority, `@PreAuthorize`, xác thực token. |
| Nghiệp vụ ứng dụng | Endpoint nào được sửa field gì, trong OU nào? | Service method cố định, DTO validation, allowlist field, DN builder. |
| LDAP server | Danh tính bind này **thực sự** có quyền đọc/ghi entry và attribute không? | ACL OpenLDAP, ACI của directory khác, quyền đối tượng trong Active Directory. |
| Kênh truyền và secret | Ai có thể quan sát/giả mạo kết nối hoặc đánh cắp credential? | LDAPS/StartTLS, kiểm tra chứng chỉ, secret manager, xoay vòng secret. |

**Điều quan trọng:** Spring Security có thể chặn người dùng trái phép, nhưng nếu tài khoản bind có quyền admin, một code path bị khai thác vẫn có thể gửi lệnh LDAP nguy hiểm. Ngược lại, LDAP ACL tối thiểu giúp giảm thiệt hại ngay cả khi kiểm soát tầng ứng dụng có lỗi.

### 3.1. Service account không đại diện tự động cho người gọi

Ví dụ cả Lan và Minh dùng cùng API để xem hồ sơ. Nếu `LdapTemplate` cấu hình `uid=svc-people-reader,...` thì LDAP server kiểm tra quyền của **svc-people-reader**, không tự nhận biết hai HTTP principal khác nhau.

Nếu nghiệp vụ chỉ cho mỗi nhân viên đọc hồ sơ của bản thân, ứng dụng phải kiểm tra điều đó ở tầng API hoặc dùng mô hình truy cập directory phù hợp để mang danh tính cuối xuống LDAP. **ACL của service account không tự thực hiện phân quyền theo từng người dùng HTTP**.

## 4. Thiết kế ma trận quyền tối thiểu

Thay vì hỏi “tài khoản có được đọc/ghi LDAP không?”, hãy tách ra:

1. **Who:** DN hoặc service principal nào thực hiện bind?
2. **Where:** OU/subtree/entry nào là đích?
3. **What:** attribute nào được phép truy cập?
4. **How:** search, compare, read, add entry, modify attribute, rename, delete hay quản trị schema?
5. **When/why:** use case nào yêu cầu quyền đó, ai sở hữu và khi nào phải rà soát?

### 4.1. Ví dụ ma trận theo vai trò

| Tài khoản | Vùng DN | Quyền cho phép | Quyền không nên cấp |
| --- | --- | --- | --- |
| `svc-people-reader` | `ou=people,dc=example,dc=org` | Search/đọc `uid`, `cn`, `sn`, `mail` và metadata tối thiểu để duyệt entry. | Add/Modify/Delete/Rename, đọc `userPassword`, sửa `objectClass`, truy cập `ou=service-accounts`. |
| `svc-profile-editor` | Các entry người dùng được quản lý trong `ou=people` | Tra cứu đủ để xác định entry; thay `mail`, `telephoneNumber` trên entry **đã tồn tại**. | Đổi RDN/UID, xóa user, sửa mật khẩu, sửa group, sửa schema/ACL. |
| `svc-group-maintainer` | Chính entry `cn=developers,ou=groups,dc=example,dc=org` | Đọc member khi cần; `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` cho `member`. | Sửa `cn=admins`, tạo/xóa group, đổi `objectClass` hoặc sửa tài khoản dịch vụ. |
| Tài khoản provisioning (nếu có) | Chỉ vùng onboarding thuộc `ou=people` | Quyền tạo entry mới với đúng schema và xóa/đổi tên theo quy trình đã duyệt. | Quyền toàn cục, quyền thay ACL/schema, quyền quản trị tài khoản dịch vụ. |

**Ma trận là chính sách nghiệp vụ minh họa, chưa phải một file ACL có thể áp trực tiếp lên mọi LDAP server.** Cú pháp, thứ tự áp dụng, loại quyền và điều kiện truy cập khác nhau giữa OpenLDAP, Active Directory và các directory khác.

### 4.2. Quyền đọc phải đủ cho tìm kiếm và mapping

Một repository như:

```java
public interface DirectoryPersonRepository
        extends org.springframework.data.ldap.repository.LdapRepository<DirectoryPerson> {
    java.util.Optional<DirectoryPerson> findByUid(String uid);
}
```

có thể cần quyền tìm theo `uid`, nhìn thấy entry trong `ou=people`, và đọc những attribute được ODM map như `cn`, `sn` hoặc `mail`. Tùy LDAP server và cách cấu hình, quyền **traverse/search/compare/read** có thể được phân biệt.

Nếu tài khoản chỉ được đọc `mail` nhưng không được dùng `uid` trong filter hoặc không thấy entry, kết quả có thể **rỗng**, dù entry vẫn tồn tại. Nếu attribute không có quyền đọc, server có thể **ẩn field** chứ không ném ngoại lệ rõ ràng. Vì vậy, kiểm thử chỉ “request trả HTTP 200” là chưa đủ.

Ngoài ra, với một số directory, quyền trên entry, parent/children và attribute được tách riêng. Tài khoản tạo user có thể cần quyền **tạo con tại OU cha**, không đơn thuần quyền sửa `cn` ở entry con; tài khoản xóa/rename cũng có yêu cầu quyền riêng. Phải kiểm tra theo server thực tế.

### 4.3. Quyền sửa attribute không bằng quyền sửa cả entry

Nhu cầu “đổi email” chỉ cần cập nhật `mail`. Không nên cấp quyền sửa tùy ý:

- `objectClass`: có thể làm thay đổi loại entry hoặc phá schema.
- `userPassword` và các thuộc tính xác thực: có ý nghĩa bảo mật riêng.
- `member` của nhóm đặc quyền: có thể dẫn đến leo thang quyền ở hệ thống downstream.
- `uid`/DN/RDN: đổi định danh có thể khiến tham chiếu và ACL lệch.
- Thuộc tính operational, owner, ACL hoặc metadata hệ thống (tùy directory).

Do đó, quyền write phải áp dụng **theo attribute** khi directory hỗ trợ, đồng thời service chỉ cho phép field được duyệt. Không dùng “quyền write toàn `ou=people`” chỉ để cập nhật một email.

## 5. Thực thi chính sách ở LDAP server

Tài khoản dịch vụ và ACL phải được **quản trị bởi người có quyền thay đổi directory**, không phải ứng dụng tự cấp quyền cho chính mình khi khởi động. Thực hiện thay đổi trên LDAP test trước, xác minh các thao tác bị cấm, rồi triển khai theo quy trình change management.

### 5.1. Chính sách ở dạng độc lập nhà cung cấp

Ví dụ chính sách **khái niệm**, không phải cú pháp `olcAccess` hay PowerShell:

```text
IDENTITY  uid=svc-people-reader,ou=service-accounts,dc=example,dc=org
ALLOW     search/compare/read trên ou=people
          cho uid,cn,sn,mail và phần quyền entry cần để trả kết quả
DENY      add,modify,delete,rename; đọc mật khẩu; truy cập vùng quản trị

IDENTITY  uid=svc-profile-editor,ou=service-accounts,dc=example,dc=org
ALLOW     tìm user trong ou=people bằng uid
ALLOW     modify chỉ mail và telephoneNumber trên entry user hợp lệ
DENY      member,objectClass,userPassword,uid/RDN,delete,rename

IDENTITY  uid=svc-group-maintainer,ou=service-accounts,dc=example,dc=org
ALLOW     đọc và modify member tại cn=developers,ou=groups
DENY      mọi nhóm khác, đặc biệt cn=admins
```

Cần làm rõ “modify” gồm những gì. Trong LDAP, `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE` đều là phép Modify; một số ACL **không** diễn đạt riêng ba loại thao tác này mà chỉ cho phép/không cho phép ghi attribute. Nếu nghiệp vụ chỉ cho **thêm một member** nhưng tuyệt đối không được xóa mọi member bằng REPLACE, phải có lớp kiểm soát nghiệp vụ, hoặc cơ chế policy/constraint đặc thù server; đừng giả định quyền `write member` tự phân biệt ADD và REPLACE.

### 5.2. OpenLDAP và Active Directory khác nhau

| Directory | Nơi kiểm soát điển hình | Lưu ý |
| --- | --- | --- |
| OpenLDAP | `olcAccess` trên cấu hình database (hoặc `slapd.conf` ở triển khai cũ). | Quy tắc có thứ tự, điều kiện target/subject, các mức như `auth`, `search`, `read`, `write`. Cấu hình sai thứ tự có thể chặn bind hoặc lộ dữ liệu. |
| Active Directory | Access Control Entries (ACE) trên security descriptor và quyền kế thừa của OU/object. | Nhóm bảo mật, quyền tạo/xóa đối tượng con, quyền thuộc tính và extended rights phải được đánh giá riêng. |
| Directory khác | ACI/ACL hoặc bộ policy riêng. | Không sao chép nguyên cú pháp OpenLDAP sang directory khác. |

Ví dụ **bảng quyết định khi cấu hình OpenLDAP**, không phải bộ rule production hoàn chỉnh:

| Target cần kiểm tra | Chủ thể | Quyền mong muốn |
| --- | --- | --- |
| Entry và thuộc tính `uid`, `cn`, `sn`, `mail` dưới `ou=people` | `svc-people-reader` | Đủ search/read theo chức năng, không write. |
| `mail`/`telephoneNumber` của entry user trong `ou=people` | `svc-profile-editor` | Write đúng các attribute đó; các attr khác không được write. |
| `member` của **đúng** `cn=developers,ou=groups` | `svc-group-maintainer` | Quyền sửa member; không sửa các nhóm khác. |
| `userPassword` của người dùng | Ba tài khoản trên | Không đọc giá trị và không thay đổi. |
| Entry tài khoản dịch vụ, ACL, schema | Ba tài khoản trên | Không được quản trị. |

Đối với OpenLDAP, đừng tùy tiện thêm một quy tắc `by * none` vào đầu danh sách: một ACL rộng và đặt sai thứ tự có thể vô hiệu hóa quyền `auth` cần thiết để bind, hoặc phủ lên các rule chi tiết bên dưới. Tất cả rule mới phải được kiểm thử cùng rule hiện có trong môi trường thử nghiệm.

## 6. Cấu hình một tài khoản chỉ đọc trong Spring Boot

Với API chỉ tra cứu người dùng, cấu hình một bind account chuyên đọc:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_READER_BIND_DN}
    password: ${LDAP_READER_PASSWORD}
```

Ví dụ các giá trị được cấp qua environment/secret store:

```text
LDAP_READER_BIND_DN=uid=svc-people-reader,ou=service-accounts,dc=example,dc=org
LDAP_READER_PASSWORD=(secret do hệ thống cấp; không commit vào Git)
```

Spring Boot thường tự cấu hình `ContextSource` và `LdapTemplate` khi dependency LDAP và cấu hình phù hợp. Với repository ODM, Spring Data LDAP sẽ dùng infrastructure liên quan để thực hiện query theo quyền bind account của nó.

**Điều không được hiểu nhầm:** đặt tên bean là `readOnlyLdapTemplate` hoặc gọi `ContextSource.getReadOnlyContext()` **không tự tước quyền ghi trên server**. API tạo context “read-only” biểu thị mục đích truy cập ở tầng framework/provider; **ACL của tài khoản bind** mới là ranh giới quyền thực tế. Cần test cố ý gửi lệnh Modify bằng chính bind account đọc và xác minh LDAP server từ chối.

### 6.1. Ví dụ tìm người dùng chỉ lấy thuộc tính cần thiết

```java
package com.example.directory;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PeopleLookupService {
    private final LdapTemplate ldapTemplate;

    public PeopleLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String uid) {
        return ldapTemplate.search(
            LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail")
                .where("uid").is(uid),
            (AttributesMapper<PersonSummary>) attrs ->
                new PersonSummary(
                    (String) attrs.get("uid").get(),
                    (String) attrs.get("cn").get(),
                    attrs.get("mail") == null
                        ? null
                        : (String) attrs.get("mail").get()
                )
        );
    }

    public record PersonSummary(
        String uid, String commonName, String email
    ) {}
}
```

Đoạn này chỉ tìm trong `ou=people` và yêu cầu các attr cần cho DTO; `LdapQueryBuilder` mã hóa giá trị filter, tránh ghép thô `"(uid=" + uid + ")"`. Việc thu hẹp attributes được trả về **giảm dữ liệu truyền** nhưng **không phải biện pháp phân quyền**: nếu một đoạn code khác yêu cầu `userPassword`, server vẫn phải chặn ở ACL.

Nếu quyền đọc `mail` bị thiếu, mapper phải xử lý giá trị `null`; riêng field `uid`/`cn` mà ứng dụng coi là bắt buộc cần kiểm thử sự hiện diện. Không coi danh sách rỗng là bằng chứng user không tồn tại khi ACL có thể ẩn entry.

## 7. Tách tài khoản đọc và tài khoản sửa trong Spring LDAP

Khi một ứng dụng có cả API tra cứu lẫn sửa hồ sơ, có thể cấu hình **hai `ContextSource`** khác principal và hai `LdapTemplate` riêng biệt. Ví dụ dưới đây chỉ minh họa lớp cấu hình Java; cả hai tài khoản phải được provision và gán ACL trên server **trước đó**.

```yaml
directory:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    reader-dn: ${LDAP_READER_BIND_DN}
    reader-password: ${LDAP_READER_PASSWORD}
    editor-dn: ${LDAP_EDITOR_BIND_DN}
    editor-password: ${LDAP_EDITOR_PASSWORD}
```

```java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryAccessConfig {

    @Bean("readerContextSource")
    LdapContextSource readerContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.reader-dn}") String bindDn,
            @Value("${directory.ldap.reader-password}") String password) {
        return contextSource(url, base, bindDn, password);
    }

    @Bean("editorContextSource")
    LdapContextSource editorContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.editor-dn}") String bindDn,
            @Value("${directory.ldap.editor-password}") String password) {
        return contextSource(url, base, bindDn, password);
    }

    @Bean("readerLdapTemplate")
    LdapTemplate readerTemplate(
            @Qualifier("readerContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("editorLdapTemplate")
    LdapTemplate editorTemplate(
            @Qualifier("editorContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    private static LdapContextSource contextSource(
            String url, String base,
            String bindDn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source; // Spring gọi lifecycle init của @Bean.
    }
}
```

Vì đây là **multi-context** configuration, ứng dụng phải nối các repository và template với **đúng bean**; đừng kỳ vọng mọi `LdapRepository` tự chuyển từ reader sang editor khi gọi `save()`. Nếu đang dùng `@EnableLdapRepositories` hoặc Spring Boot auto-configuration, cần cấu hình rõ repository infrastructure và xử lý bean ambiguity theo phiên bản thực tế. Một lựa chọn an toàn là để repository chỉ đọc ở một module, còn mọi thao tác sửa hồ sơ đi qua một service sử dụng `@Qualifier("editorLdapTemplate")`.

Ví dụ tách luồng sửa:

```java
package com.example.directory;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class ProfileMailEditor {
    private final LdapTemplate editor;

    public ProfileMailEditor(
            @Qualifier("editorLdapTemplate") LdapTemplate editor) {
        this.editor = editor;
    }

    public void changeMail(String uid, String newMail) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
        ModificationItem replace = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newMail)
        );
        editor.modifyAttributes(
            dn, new ModificationItem[] {replace}
        );
    }
}
```

`changeMail` phải được gọi từ một API **đã xác thực và phân quyền**, có validate email, giới hạn độ dài và kiểm tra người dùng được phép sửa DN nào. Bean editor không có nghĩa mọi người gọi Java method đều được phép thay hồ sơ. Server cũng phải giới hạn `svc-profile-editor` chỉ write `mail`/`telephoneNumber` trong subtree được duyệt.

### 7.1. Vì sao không dùng cùng bind account cho tất cả?

Một tài khoản duy nhất có quyền read/search, modify người dùng, thêm nhóm và delete sẽ tạo ra một ranh giới tin cậy quá rộng. Khi API tìm kiếm bị khai thác, attacker có thể dùng chính quyền bind đó để sửa hoặc xóa entry. Tách:

- `readerLdapTemplate` phục vụ truy vấn danh bạ;
- `editorLdapTemplate` phục vụ thay đổi hồ sơ;
- một service riêng, identity riêng nếu thực sự cần cập nhật `member`;

giúp giảm tác động, thuận tiện audit và xoay vòng secret độc lập. Với tác vụ ít xảy ra như onboarding, có thể đặt provisioning trong process/job riêng có kiểm soát, thay vì đưa credential ghi mạnh vào mọi instance web.

## 8. LDAP Repository và ODM không thay ACL

Entity Spring Data LDAP có thể biểu diễn entry qua các annotation:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    @Id private Name dn;
    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;
    @Attribute(name = "cn")
    private String commonName;
    @Attribute(name = "sn")
    private String surname;
    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}
    // Bổ sung getters/setters trong project thực tế.
}
```

Và repository:

```java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
```

`@Entry(base="ou=people")` thu hẹp **vị trí mặc định** được dùng cho entity; `@Attribute` chọn các field được map; `@Id` giữ DN. Nhưng đây là **cấu hình mapping, không phải chính sách ACL**. Nếu principal bind có quyền quản trị toàn directory, một code path khác có thể sử dụng `LdapTemplate` để tác động các vùng ngoài entity.

Ngược lại, nếu directory server chặn write, gọi `repository.save(...)` với reader principal phải thất bại dù Java method và entity đã hợp lệ. Nếu DTO chỉ chứa `mail`, điều đó cũng không ngăn một method khác cố sửa `member`; cần có ACL server và phân quyền theo use case.

### 8.1. Quyền áp dụng theo request thực tế

Repository `findByUid` có thể tìm bằng attribute `uid`, kiểm tra `objectClass` và đọc các field của entity. LDAP server có thể từ chối hoặc che dữ liệu khi thiếu quyền đọc cần thiết. Vì vậy, danh sách permission phải dựa trên **truy vấn thực tế được phát sinh**, không chỉ tên Java method.

Khi ứng dụng gặp lỗi không đọc được entry:

1. Xác định DN truy vấn tương đối với `ContextSource.base`.
2. Xác định filter/attribute được yêu cầu và `objectClass`.
3. Kiểm tra tài khoản bind đang sử dụng trong environment thực tế.
4. Thử lại trên directory test với chính principal đó.
5. Chỉ bổ sung **quyền tối thiểu cụ thể** nếu đã chứng minh thiếu; không đổi bind sang admin để “fix nhanh”.

## 9. Trường hợp đặc biệt: quản lý thành viên nhóm

Thuộc tính `member` của `groupOfNames` thường chứa nhiều DN đầy đủ. Thêm một người vào nhóm có thể triển khai bằng:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

Name targetGroup = LdapNameBuilder.newInstance("ou=groups")
    .add("cn", "developers")
    .build();

Name fullMember = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "linh")
    .build();

ModificationItem change = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("member", fullMember.toString())
);
// Chạy qua LdapTemplate của riêng service group maintenance.
groupTemplate.modifyAttributes(
    targetGroup, new ModificationItem[] {change}
);
```

Đây là đoạn minh họa logic; `groupTemplate` là một `LdapTemplate` được inject ở service quản lý nhóm, và account bind của nó phải chỉ có quyền ghi `member` ở `cn=developers`. Không đặt các giá trị DN đầy đủ do người dùng gửi trực tiếp vào member; xác minh người dùng thực sự tồn tại và thuộc phạm vi được quản lý, dùng `LdapNameBuilder` để tránh DN injection.

Lưu ý **`REPLACE_ATTRIBUTE(member, DN)`** có thể thay toàn bộ thành viên của nhóm. Nhiều LDAP ACL chỉ xác định quyền `write` trên thuộc tính `member` mà **không phân biệt** ADD với REPLACE. Do đó, chính sách ứng dụng phải giới hạn loại thao tác, ghi audit và kiểm tra tính nhất quán. Nếu không cần thiết, **không cấp write `member` cho service tra cứu người dùng**.

## 10. Bảo vệ secret và kết nối LDAP

### 10.1. Mật khẩu tài khoản dịch vụ

Không lưu secret trong code, repository Git, file cấu hình chung hoặc ví dụ copy/paste lên môi trường thật:

```yaml
# KHÔNG DÙNG trong production:
spring:
  ldap:
    username: cn=admin,dc=example,dc=org
    password: super-secret-hard-coded
```

Thay bằng secret manager, secret injection của môi trường triển khai hoặc kênh cấp phát chuyên dụng:

```yaml
spring:
  ldap:
    username: ${LDAP_READER_BIND_DN}
    password: ${LDAP_READER_PASSWORD}
```

Environment variables giúp tách secret khỏi source, nhưng **không mặc nhiên là kho secret an toàn nhất**: quyền đọc process/container, cấu hình orchestration, crash dump và hệ thống CI vẫn phải được kiểm soát. Không in `Environment`, properties hoặc exception chứa credentials ra log.

### 10.2. Sử dụng TLS đúng cách

- **LDAPS** dùng kết nối TLS ngay từ đầu; **StartTLS** nâng cấp kết nối LDAP theo quy trình riêng. Không dùng `ldap://` plaintext để gửi bind credentials qua mạng không tin cậy.
- **Xác minh chứng chỉ và tên máy chủ**, dùng truststore được quản lý; không tắt hostname verification hoặc thay trust manager “tin tất cả” để vượt lỗi.
- Cấu hình timeout kết nối và đọc, theo dõi lỗi TLS, tránh retry vô hạn khi chứng chỉ không hợp lệ.
- Nếu cấu hình nhiều `ContextSource`, kiểm tra **tất cả** đều dùng endpoint an toàn; đừng vô tình để context ghi dùng plaintext trong khi context đọc dùng LDAPS.
- Với directory có nhiều endpoint/server, xác minh chính sách ACL và đồng bộ trạng thái ở nơi failover; không giả định khác server sẽ có cùng quyền nếu cấu hình chưa nhất quán.

### 10.3. Xoay vòng credential

Một quy trình thực tế:

1. Lập danh sách ứng dụng/worker sử dụng từng principal.
2. Chuẩn bị credential mới hoặc principal thay thế có **cùng quyền tối thiểu**.
3. Cập nhật secret store, triển khai thay đổi có kiểm soát và kiểm thử bind/read/write được phép.
4. Kiểm thử thao tác **bị cấm vẫn bị từ chối** sau khi đổi.
5. Thu hồi credential cũ, kiểm tra connection pool/context còn sử dụng session cũ và theo dõi lỗi sau rollout.

Không nên dùng mã nguồn để tạo hoặc khôi phục admin secret. Nếu service account lộ credential, ngoài xoay vòng cần rà soát audit LDAP, phạm vi quyền và dữ liệu đã thay đổi.

## 11. Kiểm thử quyền: phải có negative test

Kiểm thử chỉ xác nhận “tìm thấy Linh” không chứng minh tài khoản chỉ đọc. Cần **test thao tác đúng được phép** và **thao tác sai bắt buộc bị từ chối**, dùng đúng bind identity và đúng LDAP server test.

### 11.1. Ma trận kiểm thử cho từng principal

| Kịch bản | `svc-people-reader` | `svc-profile-editor` | `svc-group-maintainer` |
| --- | --- | --- | --- |
| Tìm `uid=linh` dưới `ou=people` | Cho phép. | Cho phép ở phạm vi cần thiết. | Chỉ nếu thực sự cần; nếu không, từ chối. |
| Đọc `cn`/`mail` của Linh | Cho phép nếu trong danh sách attr được duyệt. | Cho phép ở mức cần để sửa. | Không mặc định cấp. |
| `REPLACE mail` của Linh | **Từ chối.** | Cho phép. | **Từ chối.** |
| `REMOVE userPassword` hoặc đổi password | **Từ chối.** | **Từ chối.** | **Từ chối.** |
| Tạo user mới trong `ou=people` | **Từ chối.** | **Từ chối.** | **Từ chối.** |
| Xóa `uid=linh` | **Từ chối.** | **Từ chối.** | **Từ chối.** |
| `ADD member` ở nhóm `developers` | **Từ chối.** | **Từ chối.** | Cho phép. |
| `ADD member` ở nhóm `admins` | **Từ chối.** | **Từ chối.** | **Từ chối.** |
| Sửa entry dưới `ou=service-accounts` | **Từ chối.** | **Từ chối.** | **Từ chối.** |

Tùy directory, “không được đọc” có thể thể hiện bằng **kết quả rỗng hoặc attribute bị ẩn**, không nhất thiết là exception `NoPermissionException`. Nhưng với Modify bị cấm, LDAP server thường trả `insufficientAccessRights` (result code **50**). Phải đối chiếu cả **trạng thái entry sau lệnh** để chắc chắn không có thay đổi ngoài ý muốn.

### 11.2. Unit test và integration test khác nhau

Unit test với mock:

- Xác minh controller/service chỉ gọi đúng template được inject theo vai trò.
- Xác minh validate/authorize trước khi tạo DN hoặc sửa thuộc tính.
- Không chứng minh LDAP server áp ACL đúng.

Integration test trên LDAP server test:

- Bind bằng chính `svc-people-reader`, không phải admin.
- Thử search được phép, Modify bị cấm, Delete bị cấm, truy cập subtree ngoài phạm vi bị chặn.
- Bind bằng `svc-profile-editor`, xác minh sửa `mail` thành công nhưng sửa `member`/`userPassword` thất bại.
- Kiểm tra ACL vẫn hoạt động sau xoay vòng secret và khi nhiều instance ứng dụng chạy.

### 11.3. Ví dụ integration test quyền reader bị từ chối ghi

Giả sử Spring Test đã inject hai bean `readerLdapTemplate` và `editorLdapTemplate` như mục 7, directory test có `uid=linh`. Đoạn test đọc trước/sau để bảo đảm bị từ chối không làm đổi mail:

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class DirectoryLeastPrivilegeIT {

    @Autowired
    @Qualifier("readerLdapTemplate")
    private LdapTemplate reader;

    @Autowired
    @Qualifier("editorLdapTemplate")
    private LdapTemplate editor;

    private final Name userDn =
        LdapNameBuilder.newInstance("ou=people")
            .add("uid", "linh")
            .build();

    @Test
    void readerCannotReplaceMail() {
        String before = reader.lookup(userDn,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("mail").get()
        );

        ModificationItem change = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "forbidden@example.org")
        );

        assertThatThrownBy(() ->
            reader.modifyAttributes(
                userDn, new ModificationItem[] {change}
            )
        ).isInstanceOf(NoPermissionException.class);

        String after = reader.lookup(userDn,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("mail").get()
        );
        assertThat(after).isEqualTo(before);
    }
}
```

Ví dụ giả định LDAP provider/Spring LDAP ánh xạ lỗi quyền thành `org.springframework.ldap.NoPermissionException`. Một số server có thể trả loại lỗi khác hoặc che dữ liệu; cần điều chỉnh assertion theo contract của directory thực tế. Test chạy trên **directory riêng, có dữ liệu seed và ACL thật**, không bao giờ dùng tài khoản production để chủ động thử ghi trái phép lên entry thật.

Khi môi trường test dùng dữ liệu chung và có cập nhật song song, giá trị trước/sau có thể đổi do người khác; dùng fixture riêng hoặc thiết kế isolation cho test.

### 11.4. Kiểm tra bằng công cụ ldapsearch và ldapmodify

Lệnh đọc LDAP test dưới danh tính reader, nhập password qua prompt:

```bash
ldapsearch -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-people-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(uid=linh)" dn uid cn sn mail
```

Để **test phủ định** quyền ghi, chuẩn bị LDIF chỉ sửa một entry kiểm thử và chạy bằng tài khoản reader trong môi trường cô lập:

```ldif
dn: uid=lab-user,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: forbidden-change@example.org
```

```bash
ldapmodify -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "uid=svc-people-reader,ou=service-accounts,dc=example,dc=org" -W \
  -f forbidden-change.ldif
```

Kỳ vọng LDAP server **từ chối** thao tác, và sau đó `ldapsearch` xác nhận mail của `lab-user` không đổi. Nếu lệnh modify thành công, đó là **lỗ hổng ACL** cần sửa ở server, không phải kết quả kiểm thử thành công. Không chạy lệnh này ở production; đây là kiểm thử chủ động thử thao tác bị cấm.

## 12. Phân biệt lỗi quyền, lỗi dữ liệu và lỗi dịch vụ

LDAP có nhiều mã lỗi; không phải lỗi nào cũng cần tăng quyền cho service account.

| Triệu chứng | Khả năng | Hướng chẩn đoán |
| --- | --- | --- |
| `insufficientAccessRights` / result code 50 | ACL không cho phép thao tác đích. | So sánh ma trận quyền; chỉ bổ sung quyền cần thiết nếu nghiệp vụ hợp lệ. |
| `noSuchObject` / code 32 | DN sai/không tồn tại **hoặc server che thông tin**. | Kiểm tra base DN, OU, entry và ACL bằng tài khoản kiểm thử có thẩm quyền. |
| Search trả `[]` | Không có entry khớp, filter sai, **hoặc thiếu quyền search**. | Đối chiếu truy vấn dưới principal có quyền phù hợp trên directory test. |
| Thiếu `mail` trong kết quả | Attribute không có giá trị **hoặc bị ACL ẩn**. | Kiểm tra thuộc tính thực tế và quyền đọc trên test server. |
| `invalidCredentials` / code 49 | Bind DN/secret sai, account bị khóa/hết hạn. | Kiểm tra secret lifecycle; không nhầm với quyền write. |
| `objectClassViolation` / code 65 | Entry sau sửa không còn hợp schema. | Kiểm tra attribute bắt buộc, `objectClass` và syntax. |
| `attributeOrValueExists` / code 20 | Thêm giá trị đã tồn tại. | Điều chỉnh nghiệp vụ idempotent, không tăng quyền. |
| `unavailable` / code 52 hoặc lỗi communication | Server/network không sẵn sàng. | Kiểm tra TLS, DNS, timeout, endpoint, health. |

Spring LDAP thường bọc các checked `javax.naming.NamingException` của JNDI thành runtime exception, ví dụ `org.springframework.ldap.NoPermissionException` và `org.springframework.ldap.CommunicationException`. Khi xây API, không chuyển thông điệp LDAP thô hoặc DN nhạy cảm trực tiếp vào HTTP response. Lỗi bind của **tài khoản dịch vụ** là sự cố backend, không mặc nhiên là HTTP `401` của người dùng cuối.

Nếu endpoint tra cứu chỉ trả `404` cho mọi kết quả rỗng, ứng dụng có thể vô tình che lỗi ACL; thêm health check và integration test với đúng principal để phát hiện.

## 13. Vận hành, audit và rà soát quyền định kỳ

### 13.1. Ghi audit đúng nguồn

LDAP server có thể chỉ thấy `svc-profile-editor` sửa `mail`. Để biết **người dùng HTTP nào** yêu cầu sửa, ứng dụng cần audit ở tầng nghiệp vụ:

```text
requestId=41ab2
actor=employee-847
operation=UPDATE_CONTACT_EMAIL
targetCategory=employee-profile
ldapPrincipal=svc-profile-editor
result=SUCCESS
```

Không cần ghi toàn bộ email cũ/mới, password, secret hoặc DN chứa dữ liệu cá nhân vào log công khai. Với yêu cầu forensic, tổ chức có thể dùng audit store được phân quyền và thời hạn lưu rõ ràng; correlate với log của directory qua request ID/thời điểm/đối tượng theo dữ liệu được phép.

### 13.2. Phát hiện dấu hiệu cấp quyền quá rộng

Theo dõi:

- Số lệnh Modify/Delete bị từ chối từ tài khoản vốn chỉ đọc.
- Truy vấn ở những OU tài khoản không có nhiệm vụ truy cập.
- Tăng đột biến số entry search hoặc số attribute được yêu cầu.
- Lỗi bind liên tục có thể do credential bị xoay vòng chưa đồng bộ hoặc hành vi bất thường.
- Ghi vào `member` của nhóm nhạy cảm hoặc thay `userPassword` từ tài khoản không có nghiệp vụ đó.
- Tài khoản không còn owner/ứng dụng sử dụng nhưng vẫn có quyền hoặc secret còn hiệu lực.

### 13.3. Quy trình cấp và thu hồi quyền

| Thời điểm | Hành động |
| --- | --- |
| Thiết kế chức năng | Ghi rõ use case, subtree, attribute, operation và người sở hữu. |
| Trước triển khai | Provision principal, đặt ACL tối thiểu, tạo secret an toàn. |
| Kiểm thử | Chạy test allow **và** deny với chính bind identity. |
| Khi thay đổi chức năng | Rà soát phần quyền mới cần thiết; không mở rộng wildcard theo thói quen. |
| Theo chu kỳ | Đối chiếu quyền đang cấp với ứng dụng/owner đang hoạt động. |
| Khi sự cố/lộ secret | Thu hồi/rotate credential, rà soát audit và trạng thái dữ liệu đã sửa. |
| Khi ngừng dịch vụ | Thu hồi ACL và vô hiệu hóa/xóa account theo chính sách tổ chức. |

Tài khoản admin/break-glass nếu tồn tại phải được quản lý riêng, có phê duyệt, audit và thời hạn sử dụng; không cấu hình nó làm tài khoản mặc định cho ứng dụng thường ngày.

## 14. Những sai lầm phổ biến

| Cách làm sai | Vì sao rủi ro | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng `cn=admin` cho mọi `LdapRepository`. | Lỗi ứng dụng có thể tác động toàn directory. | Tạo principal chuyên dụng, quyền theo use case/OU/attribute. |
| Tin rằng `getReadOnlyContext()` là ACL. | Không chứng minh server từ chối Modify. | Kiểm tra bằng negative integration test dưới đúng principal. |
| Chỉ giới hạn DTO, không giới hạn quyền bind. | Code path khác có thể đọc/ghi attribute nhạy cảm. | Server ACL + DTO allowlist + Spring Security. |
| Cấp `write` cả `ou=groups` để thêm user vào developers. | Có thể sửa nhóm admin. | Chỉ cấp đúng group/attribute cần thiết và giới hạn operation trong service. |
| Thấy search rỗng thì mặc định entry không tồn tại. | ACL có thể ẩn entry hoặc field. | Kiểm tra search/compare/read ACL và dữ liệu trên directory test. |
| Thiếu quyền thì tăng tài khoản lên admin. | Che lỗi thiết kế, mở rộng bề mặt tấn công. | Xác định chính xác quyền search/read/write cần bổ sung. |
| Gửi bind password qua `ldap://` plaintext. | Dễ bị lộ trên đường truyền. | LDAPS/StartTLS và xác thực chứng chỉ. |
| Log cả connection properties khi khởi động. | Có thể lộ credential từ environment/secret store. | Mask/redact và chỉ log metadata cần thiết. |
| Một bean `LdapTemplate` được dùng cho mọi nhiệm vụ. | Khó tách quyền và audit. | Tách context/service hoặc process theo mức đặc quyền. |
| Chỉ test trường hợp được phép. | ACL quá rộng vẫn có thể “pass”. | Bổ sung kiểm thử thao tác bị cấm và trạng thái sau lệnh. |
| Gắn `@Transactional` và coi mọi thao tác LDAP được rollback. | Không có ACID mặc định xuyên nhiều request/LDAP+SQL. | Thiết kế bù trừ hoặc giới hạn phạm vi cập nhật theo khả năng server. |

## 15. Bài tập thực hành

1. Thiết kế ma trận quyền cho ứng dụng chỉ cần tìm người dùng theo `uid` và trả `cn`/`mail`. Nêu rõ những attribute và thao tác **không** được cấp.
2. Một service thay `mail` của người dùng trong `ou=people`. Hãy đề xuất DN tài khoản dịch vụ, phạm vi subtree, quyền đọc tối thiểu để tìm entry và quyền write chính xác.
3. Vì sao một tài khoản có quyền sửa `member` của **mọi** group nguy hiểm hơn tài khoản chỉ sửa `cn=developers`? Nêu tình huống leo thang quyền.
4. Cấu hình `readerLdapTemplate` và `editorLdapTemplate` với hai `ContextSource`; giải thích tại sao repository không được tự động đổi principal theo tên method.
5. Viết integration test dùng reader account cố sửa `mail` và xác minh server từ chối. Sau đó thêm negative test sửa `userPassword` và truy cập `ou=service-accounts`.
6. Search `(uid=linh)` trả danh sách rỗng với reader account nhưng admin test thấy entry tồn tại. Liệt kê cách kiểm tra search base, filter, `objectClass` và ACL mà không vội tăng quyền.
7. Một backend dùng chung principal admin cho tra cứu và sửa group. Đề xuất kế hoạch phân tách tài khoản và xoay vòng secret theo từng bước, không làm gián đoạn các API chỉ đọc.
8. Giải thích vì sao `@PreAuthorize` chỉ là một lớp bảo vệ và cần LDAP ACL; đề xuất cách lưu audit để đối chiếu người dùng HTTP và service principal.

### Checklist nghiệm thu

- [ ] Mỗi tài khoản dịch vụ có owner và use case rõ ràng.
- [ ] Quyền đã giới hạn theo DN/subtree, operation và attribute.
- [ ] Không dùng tài khoản admin mặc định cho truy vấn thông thường.
- [ ] Đã phân biệt quyền người dùng API với quyền LDAP bind.
- [ ] Kết nối sử dụng LDAPS/StartTLS và xác thực chứng chỉ.
- [ ] Secret lấy từ kênh được quản lý, không hard-code hoặc ghi log.
- [ ] Repository/`LdapTemplate` dùng đúng `ContextSource` đã phân quyền.
- [ ] Test được **cả trường hợp cho phép và từ chối** trên LDAP server test.
- [ ] Hệ thống phân biệt lỗi ACL với lỗi DN, schema, xác thực và network.
- [ ] Có kế hoạch rotate credential, audit và thu hồi quyền.

## 16. Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, cấu hình và làm việc với directory.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM, query và CRUD.
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): phân quyền tại tầng HTTP/method.
- [Spring Boot Reference — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình kết nối và auto-configuration Spring LDAP.
- [OpenLDAP Administrator's Guide — Access Control](https://www.openldap.org/doc/admin24/access-control.html): mô hình `olcAccess`, phạm vi target, subject và quyền theo mức.
- [Microsoft Learn — Active Directory Security](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/): quản lý quyền đối tượng, OU và danh tính dịch vụ trong Active Directory.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Bind, Modify, result codes và authorization errors.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, entry, attribute, `objectClass` và schema.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): yêu cầu an toàn cho LDAP authentication.
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515): tạo filter và escaping an toàn.
