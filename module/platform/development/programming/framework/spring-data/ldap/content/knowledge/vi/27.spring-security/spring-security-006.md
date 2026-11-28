# Chuẩn hóa tên vai trò theo chính sách ứng dụng

Trong một hệ thống sử dụng **Spring Security** và **Spring Data LDAP**, tên nhóm được lưu trong directory không nhất thiết trùng với tên vai trò mà ứng dụng Java sử dụng để phân quyền. Directory có thể dùng `cn=directory-readers`, `cn=account-admins` hoặc `cn=group-managers`, trong khi mã nguồn chỉ nên hiểu những authority nhất quán như `ROLE_DIRECTORY_VIEWER`, `ROLE_ACCOUNT_ADMIN` và `ROLE_GROUP_MANAGER`.

Nếu ứng dụng chuyển mọi `cn` thành `ROLE_ + UPPERCASE(cn)`, một nhóm LDAP mới hoặc một thay đổi tên nhóm ngoài ý muốn có thể làm hỏng việc phân quyền. Ngược lại, nếu vô tình chấp nhận nhóm tên `admins` là `ROLE_ADMIN` mà không có chính sách rõ ràng, quyền có thể được cấp rộng hơn mong đợi.

Bài học thuộc chương **Spring Security** của mô-đun `SPRING_DATA_LDAP`. Nội dung tập trung vào **chuẩn hóa vai trò** tại ranh giới LDAP → Spring Security, tách xác thực khỏi ủy quyền, dùng `DefaultLdapAuthoritiesPopulator`, `GrantedAuthoritiesMapper`, `hasRole`/`hasAuthority`, đồng thời kiểm chứng với LDAP thật. Các phần về DN, `objectClass`, schema, filter, repository/`LdapTemplate` và ACL được gắn với ví dụ cụ thể.

> **Nguyên tắc cốt lõi:** LDAP cung cấp **bằng chứng thành viên nhóm**; ứng dụng quyết định **nhóm nào tương ứng quyền nào**. Không để tên nhóm bất kỳ, dữ liệu do client gửi hoặc sự khác biệt chữ hoa/chữ thường tự sinh quyền quản trị.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt LDAP group, application role, `GrantedAuthority`, privilege/permission và danh tính LDAP Bind.
2. Giải thích cách `DefaultLdapAuthoritiesPopulator` tìm nhóm từ `groupOfNames.member` và lấy tên vai trò từ `cn`.
3. Phân biệt `hasRole("X")` với `hasAuthority("ROLE_X")` theo tiền tố `ROLE_` mặc định.
4. Chuẩn hóa tên theo quy tắc cố định, không cấp quyền chỉ dựa vào phép chuyển uppercase/prefix.
5. Viết `GrantedAuthoritiesMapper` theo **allowlist**: chỉ những nhóm đã phê duyệt mới tạo authority.
6. Cấu hình `BindAuthenticator`, `LdapAuthenticationProvider`, `DefaultLdapAuthoritiesPopulator` và mapper trong Spring Security.
7. Dùng Spring Security `SecurityFilterChain`, `@EnableMethodSecurity` và `@PreAuthorize` nhất quán.
8. Phân biệt quyền của người gọi HTTP với ACL và service account dùng để quản lý directory qua Spring Data LDAP.
9. Kiểm thử cả trường hợp được phép và bị từ chối: nhóm lạ, thay đổi cách viết, trùng mapping, kết quả nhóm không đầy đủ và quyền bị thu hồi.
10. Nhận diện giới hạn của direct group membership, nested groups, `memberOf`, cache/session/JWT và mapping tùy directory.

## 2. Vấn đề: tên nhóm LDAP không phải hợp đồng phân quyền ứng dụng

Giả sử hệ thống có directory:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── uid=mai
├── ou=groups
│   └── ou=app-roles
│       ├── cn=directory-readers
│       ├── cn=account-admins
│       └── cn=group-managers
└── ou=service
    └── cn=svc-security-reader
~~~

Người dùng Lan thuộc nhóm đọc danh bạ:

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
~~~

Nhóm của Lan:

~~~ldif
dn: cn=directory-readers,ou=app-roles,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: directory-readers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Một nhóm quản trị tài khoản:

~~~ldif
dn: cn=account-admins,ou=app-roles,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: account-admins
member: uid=mai,ou=people,dc=example,dc=org
~~~

Và nhóm quản lý thành viên:

~~~ldif
dn: cn=group-managers,ou=app-roles,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: group-managers
member: uid=minh,ou=people,dc=example,dc=org
~~~

`groupOfNames` bắt buộc có `cn` và ít nhất một `member` theo schema LDAP. `member` mang **DN đầy đủ** của thành viên. Các entry cha `ou=groups` và `ou=app-roles` phải tồn tại trước khi tạo nhóm.

Ứng dụng cần một chính sách nhất quán:

| LDAP group `cn` | Authority chính thức của ứng dụng | Được làm gì |
| --- | --- | --- |
| `directory-readers` | `ROLE_DIRECTORY_VIEWER` | Đọc thông tin danh bạ đã được phê duyệt. |
| `account-admins` | `ROLE_ACCOUNT_ADMIN` | Đi vào các workflow quản trị tài khoản được ủy quyền. |
| `group-managers` | `ROLE_GROUP_MANAGER` | Quản lý thành viên các nhóm được phép. |
| Nhóm khác hoặc tên không được phê duyệt | **Không phát sinh authority** | Không được tự cấp quyền mới. |

Bảng này là **chính sách ứng dụng**, không phải một yêu cầu của giao thức LDAP hoặc của Spring Security. Một tổ chức khác có thể đặt tên nhóm khác nhưng phải giữ nguyên nguyên tắc: chỉ ánh xạ có chủ đích.

## 3. Năm khái niệm không nên đánh đồng

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| LDAP entry | `uid=lan,ou=people,dc=example,dc=org` | Đối tượng người dùng trong directory. |
| LDAP group | `cn=directory-readers,...` | Entry nhóm lưu các DN thành viên. |
| LDAP Bind identity | `uid=lan,...` hoặc `cn=svc-security-reader,...` | Danh tính của **một kết nối** xác thực với LDAP. |
| Application role | `DIRECTORY_VIEWER` | Vai trò nghiệp vụ do **ứng dụng** định nghĩa. |
| Spring Security `GrantedAuthority` | `ROLE_DIRECTORY_VIEWER` | Chuỗi/quyền được gắn vào `Authentication` và dùng khi kiểm tra authorization. |

**Xác thực** trả lời: người dùng là ai và có chứng minh được danh tính không?

**Ủy quyền** trả lời: người dùng đó được làm gì trong ứng dụng?

**LDAP ACL** trả lời: kết nối đã Bind bằng DN đang dùng có thể Search/Read/Add/Modify/Delete trên entry hoặc thuộc tính nào?

Một người dùng có `ROLE_ACCOUNT_ADMIN` trong Spring Security **không tự có quyền sửa LDAP server**. Ngược lại, một service account có quyền LDAP Modify **không chứng minh** người gọi HTTP được phép gọi API quản trị.

### Nhóm LDAP không phải ROLE_* tự sinh

Ví dụ nhóm có tên `cn=finance` có thể được dùng cho mailing list, cấu hình phần mềm hoặc một chức năng tổ chức khác. Việc chuyển tên nó thành `ROLE_FINANCE` chỉ nên xảy ra nếu ứng dụng định nghĩa chính thức phép ánh xạ đó.

Tương tự, nhóm LDAP có tên `cn=admin` ở một nhánh chung **không** nên tự tạo `ROLE_ADMIN` trong một ứng dụng nhạy cảm. Phải giới hạn cả **nguồn nhóm** lẫn **tên nhóm được chấp nhận**.

## 4. Vai trò của DN, groupSearchBase và groupSearchFilter

Spring Security LDAP có `DefaultLdapAuthoritiesPopulator` để tìm các nhóm mà người dùng là thành viên.

Ví dụ kết nối có base:

~~~text
ContextSource.base = dc=example,dc=org
~~~

Thì:

~~~text
groupSearchBase = ou=app-roles,ou=groups
~~~

là DN **tương đối với ContextSource**. Vùng Search đầy đủ là:

~~~text
ou=app-roles,ou=groups,dc=example,dc=org
~~~

Một filter điển hình:

~~~text
(&(objectClass=groupOfNames)(member={0}))
~~~

Trong `DefaultLdapAuthoritiesPopulator`, placeholder:

- `{0}` tương ứng với **DN đầy đủ của người dùng**.
- `{1}` tương ứng với **username**.

Với Lan, điều kiện thành viên có ý nghĩa:

~~~text
(member=uid=lan,ou=people,dc=example,dc=org)
~~~

**Đừng thay `{0}` bằng chuỗi `uid` đơn lẻ** khi schema nhóm là `groupOfNames.member`. Giá trị `member` chứa DN, không phải username.

### Sơ đồ truy xuất vai trò

~~~mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant Auth as LdapAuthenticator
    participant Dir as LDAP server
    participant Pop as AuthoritiesPopulator
    participant Map as GrantedAuthoritiesMapper
    participant Sec as Spring Security
    User->>Auth: Đăng nhập bằng username/password
    Auth->>Dir: LDAP Bind theo danh tính người dùng
    Dir-->>Auth: Thành công hoặc thất bại
    Auth->>Pop: Người dùng đã xác thực + DN
    Pop->>Dir: Search groupOfNames có member=DN
    Dir-->>Pop: cn=directory-readers
    Pop->>Map: Authority thô: directory-readers
    Map-->>Sec: ROLE_DIRECTORY_VIEWER
    Sec-->>User: Authentication với authorities chuẩn
~~~

Ở bước Search nhóm, kết nối phục vụ tra cứu có thể sử dụng **service Bind DN riêng**, khác với danh tính Bind lúc đăng nhập. Cả hai đều phải dùng TLS và quyền tối thiểu.

## 5. Chuẩn hóa để có một hợp đồng quyền ổn định

Thiết kế chính sách nên ghi rõ:

1. **Phạm vi nguồn:** chỉ nhóm dưới `ou=app-roles,ou=groups` tham gia ánh xạ.
2. **Thuộc tính tên:** chỉ đọc `cn` của entry đúng object class `groupOfNames`.
3. **Quy tắc chữ hoa/chữ thường:** trong ví dụ, cho phép khác biệt ASCII case nhưng kết quả luôn là tên canonical.
4. **Danh sách tên được phép:** `directory-readers`, `account-admins` và `group-managers`.
5. **Đầu ra:** `ROLE_DIRECTORY_VIEWER`, `ROLE_ACCOUNT_ADMIN`, `ROLE_GROUP_MANAGER`.
6. **Mặc định với tên không biết:** không cấp quyền (fail closed).
7. **Trùng tên sau chuẩn hóa:** loại trùng authority, không cấp thêm quyền.
8. **Không tự suy diễn phân cấp:** admin có được quyền viewer hay không do chính sách API/mapping quyết định, không phải do tên có chữ `ADMIN`.
9. **Quyền thay đổi nhóm:** chỉ nhà quản trị directory đã được phê duyệt mới sửa thành viên của các nhóm bảo mật này.
10. **Vòng đời thay đổi policy:** có kiểm thử âm tính và audit khi thêm/đổi/xóa ánh xạ.

### Tại sao không chỉ gọi uppercase?

So sánh:

| Dữ liệu nhóm LDAP | Uppercase + prefix thuần túy | Ánh xạ chính sách chặt |
| --- | --- | --- |
| `directory-readers` | `ROLE_DIRECTORY-READERS` | `ROLE_DIRECTORY_VIEWER` |
| `account-admins` | `ROLE_ACCOUNT-ADMINS` | `ROLE_ACCOUNT_ADMIN` |
| `group-managers` | `ROLE_GROUP-MANAGERS` | `ROLE_GROUP_MANAGER` |
| `admin` | `ROLE_ADMIN` | **Không cấp quyền** nếu không nằm trong allowlist. |
| `account-admins-extra` | `ROLE_ACCOUNT-ADMINS-EXTRA` | **Không cấp quyền**. |
| `ROLE_ACCOUNT_ADMIN` | Tùy cấu hình prefix/case | **Không tự chấp nhận** nếu không thuộc nguồn/tên hợp lệ. |

Uppercase và prefix giúp **đồng nhất hình thức**, nhưng không đủ để định nghĩa **ý nghĩa quyền**.

## 6. Chuẩn ROLE_ của Spring Security: hasRole và hasAuthority

Với cấu hình tiền tố mặc định:

~~~java
// Hai điều kiện thường tương đương nếu authority thực sự
// được lưu là "ROLE_DIRECTORY_VIEWER":
hasRole("DIRECTORY_VIEWER")
hasAuthority("ROLE_DIRECTORY_VIEWER")
~~~

Ví dụ trong Java DSL:

~~~java
.requestMatchers("/api/v1/directory/**")
.hasRole("DIRECTORY_VIEWER")
~~~

Và:

~~~java
.requestMatchers("/api/v1/directory/**")
.hasAuthority("ROLE_DIRECTORY_VIEWER")
~~~

Điểm dễ nhầm:

- `hasRole("DIRECTORY_VIEWER")` mặc định tìm authority `ROLE_DIRECTORY_VIEWER`.
- `hasAuthority("ROLE_DIRECTORY_VIEWER")` so khớp **đúng chuỗi** đã nêu.
- Không truyền `hasRole("ROLE_DIRECTORY_VIEWER")` với cấu hình mặc định; `hasRole` nhận tên **không có tiền tố**.
- `hasAuthority("DIRECTORY_VIEWER")` không khớp `ROLE_DIRECTORY_VIEWER`.

Spring Security có `GrantedAuthorityDefaults` để thay đổi tiền tố mặc định. **Nếu không thật sự cần**, nên giữ quy ước `ROLE_` để tránh sự khác biệt giữa cấu hình request, method security, test và các thư viện tích hợp.

### Đừng trộn role và permission tùy tiện

Một ứng dụng có thể có authority ở hai cấp:

~~~text
ROLE_DIRECTORY_VIEWER    (vai trò tổng quát)
ROLE_ACCOUNT_ADMIN       (vai trò tổng quát)
ACCOUNT_RESET_PASSWORD   (quyền nghiệp vụ cụ thể)
GROUP_MEMBER_WRITE      (quyền nghiệp vụ cụ thể)
~~~

`hasRole("ACCOUNT_ADMIN")` dành cho vai trò; `hasAuthority("ACCOUNT_RESET_PASSWORD")` dành cho quyền cụ thể. Đừng mặc định mọi vai trò có chữ `ADMIN` đều được cấp tất cả những quyền tinh vi. Nếu cần phân cấp role → permission, định nghĩa riêng trong policy, kiểm thử và kiểm soát khả năng thu hồi.

## 7. DefaultLdapAuthoritiesPopulator và các cài đặt mặc định

`DefaultLdapAuthoritiesPopulator` có các thuộc tính quan trọng:

| Thuộc tính | Mặc định thông dụng | Trong bài này |
| --- | --- | --- |
| `groupSearchBase` | Được đặt qua constructor; null tắt tìm nhóm | `ou=app-roles,ou=groups` |
| `groupSearchFilter` | Dùng group member với DN người dùng | `(&(objectClass=groupOfNames)(member={0}))` |
| `groupRoleAttribute` | `cn` | `cn` |
| `rolePrefix` | `ROLE_` | **Chuỗi rỗng**, vì mapper chính sách sẽ cấp tiền tố. |
| `convertToUpperCase` | `true` | **false**, để mapper chuẩn hóa có kiểm soát. |
| `searchSubtree` | `false` (ONELEVEL) | `false` khi các nhóm nằm trực tiếp dưới base. |
| `defaultRole` | Không bắt buộc cấp mặc định | Không dùng trong bài. |

Một populator có thể biến `cn=directory-readers` thành `ROLE_DIRECTORY-READERS` nếu giữ mặc định. Khi ứng dụng cần **ánh xạ alias sang tên canonical khác**, ta sẽ tắt chuyển đổi ở populator để nhận tên nhóm thô, rồi đặt một `GrantedAuthoritiesMapper` chuyên trách.

**Không nên xử lý tiền tố tại cả ba nơi** (populator, mapper và quy tắc `hasRole`) một cách độc lập. Hãy chọn đúng một tầng chuẩn hóa, có unit test.

### Tên nhóm từ cn không đảm bảo tính duy nhất toàn hệ thống

Hai nhóm có thể trùng `cn=account-admins` ở hai OU khác nhau. Vì thế phải giới hạn `groupSearchBase`, `searchSubtree` và quyền quản lý nhánh. Nếu sau này mở subtree, cần kiểm tra tình trạng trùng `cn` và quyết định có nên dựa trên **DN nhóm chính xác** thay vì mỗi giá trị `cn`.

Với hệ thống nhiều tenant, cùng một nhóm tên `account-admins` có thể tồn tại tại mỗi tenant nhưng **không đồng nghĩa** quyền quản trị liên tenant. Cần ràng buộc tenant/region vào policy, không chỉ so tên nhóm.

## 8. Khi nào SimpleAuthorityMapper là đủ?

Spring Security có `SimpleAuthorityMapper`, một implementation `GrantedAuthoritiesMapper` hữu ích khi mọi authority đầu vào đã có **ý nghĩa nghiệp vụ chính xác** và bạn chỉ muốn đổi chữ hoa/thường, thêm tiền tố.

~~~java
import org.springframework.security.core.authority.mapping.SimpleAuthorityMapper;

SimpleAuthorityMapper mapper = new SimpleAuthorityMapper();
mapper.setConvertToUpperCase(true);
mapper.setPrefix("ROLE_");
~~~

Ví dụ, `directory_viewer` có thể trở thành `ROLE_DIRECTORY_VIEWER`.

Nhưng `SimpleAuthorityMapper` **không có bảng “`directory-readers` → `ROLE_DIRECTORY_VIEWER`” theo chính sách riêng**; nó không tự biết nhóm LDAP nào đáng tin, ai được sửa nhóm hay nhóm nào bị cấm.

Một cài đặt `setDefaultAuthority(...)` còn có thể cấp authority cho **tất cả người dùng được map**; đây không phải lựa chọn tốt nếu ứng dụng cần **không có vai trò khi nhóm không được chứng minh**.

**Lựa chọn:** dùng `SimpleAuthorityMapper` cho bài toán chỉ đổi format, hoặc dùng **mapper allowlist** cho bài toán chuyển tên nhóm LDAP thành vai trò canonical theo policy ứng dụng. Với quyền quản trị, cách thứ hai thường an toàn và dễ kiểm toán hơn.

## 9. Viết GrantedAuthoritiesMapper theo allowlist

Ta tạo một mapper **không truy cập LDAP**, chỉ nhận những authority thô đã được populator tìm thấy và ánh xạ đúng ba tên nhóm hợp lệ.

`security/DirectoryRolePolicyMapper.java`:

~~~java
package com.example.directory.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;

public final class DirectoryRolePolicyMapper
        implements GrantedAuthoritiesMapper {

    private static final Map<String, String> GROUP_TO_AUTHORITY =
            Map.of(
                "directory-readers", "ROLE_DIRECTORY_VIEWER",
                "account-admins", "ROLE_ACCOUNT_ADMIN",
                "group-managers", "ROLE_GROUP_MANAGER"
            );

    @Override
    public Set<GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> input) {

        Set<GrantedAuthority> output = new LinkedHashSet<>();
        if (input == null) {
            return output; // Không tạo quyền từ dữ liệu không có.
        }

        for (GrantedAuthority item : input) {
            if (item == null || item.getAuthority() == null) {
                continue;
            }

            // Chỉ chuẩn hóa case/space để tra allowlist.
            String group = item.getAuthority()
                    .strip()
                    .toLowerCase(Locale.ROOT);

            // Không coi mọi ROLE_* từ LDAP là quyền ứng dụng.
            // Chỉ tên cn thuộc tập cho phép mới được ánh xạ.
            String canonical = GROUP_TO_AUTHORITY.get(group);
            if (canonical != null) {
                output.add(new SimpleGrantedAuthority(canonical));
            }
        }

        // Không tự thêm ROLE_USER, ROLE_ADMIN hoặc role mặc định.
        return output;
    }
}
~~~

### Quy tắc của mapper

1. **Có bảng chấp nhận chính thức**; không suy diễn authority mới từ tên lạ.
2. Dùng `Locale.ROOT` để không phụ thuộc locale máy chủ khi chuyển chữ hoa/thường.
3. Không bỏ tiền tố `ROLE_` của bất kỳ input nào rồi mặc định coi chúng là vai trò hợp lệ.
4. Không gán `ROLE_ADMIN` cho một tên như `admins` mà không có policy rõ ràng.
5. Dùng tập `Set` để loại bỏ authority trùng.
6. Không thêm authority mặc định chỉ vì người dùng đã đăng nhập thành công.
7. Kết quả của mapper **không xác nhận lại nguồn LDAP**; do đó populator phải chỉ truy vấn **nhóm trong base đã tin cậy** và LDAP ACL phải bảo vệ việc sửa nhóm.

### Tính nhất quán khi đổi tên nhóm

Nếu directory đổi `cn=directory-readers` thành `cn=people-viewers`, người dùng sẽ **mất `ROLE_DIRECTORY_VIEWER`** theo mapper hiện tại. Đây là hành vi **fail closed** được mong đợi khi tên mới chưa được duyệt.

Một migration an toàn có thể thực hiện:

1. Định nghĩa alias mới `people-viewers` → `ROLE_DIRECTORY_VIEWER` sau review.
2. Viết test cả hai tên trong thời gian chuyển đổi.
3. Thay tên nhóm trên LDAP theo kế hoạch.
4. Theo dõi authority thực tế sau đăng nhập mới.
5. Gỡ alias cũ khi dữ liệu đã ổn định.

Đừng tạo rule `contains("viewer")`, `startsWith("account-")` hoặc regex rộng chỉ để “hỗ trợ tương thích”. Điều đó khiến ý nghĩa quyền phụ thuộc tên nhóm do người khác có thể tạo.

## 10. Kiểm thử mapper bằng JUnit trước khi kết nối LDAP

`DirectoryRolePolicyMapperTest.java`:

~~~java
package com.example.directory.security;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class DirectoryRolePolicyMapperTest {

    private final DirectoryRolePolicyMapper mapper =
            new DirectoryRolePolicyMapper();

    private Set<String> map(String... names) {
        List<GrantedAuthority> input = java.util.Arrays.stream(names)
                .map(SimpleGrantedAuthority::new)
                .map(GrantedAuthority.class::cast)
                .toList();

        return mapper.mapAuthorities(input).stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void knownGroupsBecomeCanonicalAuthorities() {
        assertEquals(Set.of("ROLE_DIRECTORY_VIEWER"),
                map("directory-readers"));
        assertEquals(Set.of("ROLE_ACCOUNT_ADMIN"),
                map("account-admins"));
        assertEquals(Set.of("ROLE_GROUP_MANAGER"),
                map("group-managers"));
    }

    @Test
    void caseVariantsAndDuplicatesDoNotAddMoreRoles() {
        assertEquals(Set.of("ROLE_DIRECTORY_VIEWER"),
                map("DIRECTORY-READERS",
                    "directory-readers",
                    " Directory-Readers "));
    }

    @Test
    void unapprovedNamesNeverBecomeAdmin() {
        assertEquals(Set.of(),
                map("admin", "ROLE_ADMIN",
                    "account-admins-extra",
                    "account_admins",
                    "engineering"));
    }

    @Test
    void onlyApprovedMembersReceiveAGroupRole() {
        assertEquals(Set.of("ROLE_DIRECTORY_VIEWER"),
                map("directory-readers", "other-group"));
    }

    @Test
    void emptyInputGrantsNothing() {
        assertEquals(Set.of(), map());
    }
}
~~~

Các test này chỉ kiểm tra **mapping logic**. Chúng **không chứng minh** directory trả đúng group list, LDAP ACL không bị bypass hay HTTP policy đang dùng mapper này. Cần integration test ở các mục sau.

### Tại sao unit test cần tên “ROLE_ADMIN”?

Vì một anti-pattern nguy hiểm là tin authority đầu vào đã có `ROLE_` và chuyển thẳng thành quyền. Test `ROLE_ADMIN` đảm bảo **tên chưa được phê duyệt vẫn không tạo quyền**, dù có vẻ đúng format của Spring Security.

## 11. Cấu hình LDAP authentication + authorities mapping

Ví dụ dùng Spring Boot 3.x, Java 17+ và Spring Security 6.x (hoặc phiên bản tương thích của Spring LDAP). Các dependency thường cần:

~~~xml
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
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Các đoạn này là **dependency đặt trong `<dependencies>` của `pom.xml` đang có**, không phải một file Maven độc lập. Để test method authorization, thêm `spring-security-test` ở scope test. Giữ phiên bản do Spring Boot BOM quản lý, không trộn thư viện security và ldap từ các nhánh không tương thích.

### 11.1. Cấu hình kết nối bảo mật

`application.yml`:

~~~yaml
directory:
  security:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    reader-dn: cn=svc-security-reader,ou=service,dc=example,dc=org
    reader-password: "${LDAP_SECURITY_READER_PASSWORD}"
~~~

Ở đây `directory.security.*` là namespace tự định nghĩa của ứng dụng, **không phải cấu hình `spring.ldap.*` tự động**. Secret lấy từ biến môi trường hoặc secret manager. Máy chủ và JVM phải kiểm tra CA/hostname cho LDAPS.

Tài khoản `svc-security-reader` dùng để đọc entry/người dùng/nhóm cần thiết cho xác thực và truy xuất authorities. Quyền LDAP của nó phải **không cho Modify, Delete, Rename hoặc tạo nhóm**. Spring Security cũng thực hiện **user Bind** bằng thông tin đăng nhập của người dùng khi xác thực.

### 11.2. JavaConfig từ ContextSource tới LdapAuthenticationProvider

`security/LdapRoleSecurityConfig.java`:

~~~java
package com.example.directory.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.ldap.authentication.BindAuthenticator;
import org.springframework.security.ldap.authentication.LdapAuthenticationProvider;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

@Configuration
public class LdapRoleSecurityConfig {

    @Bean("securityLdapContextSource")
    public LdapContextSource securityLdapContextSource(
            @Value("${directory.security.url}") String url,
            @Value("${directory.security.base}") String base,
            @Value("${directory.security.reader-dn}") String bindDn,
            @Value("${directory.security.reader-password}") String secret) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(secret);
        source.setReferral("throw");
        return source;
    }

    @Bean
    public GrantedAuthoritiesMapper directoryRolePolicyMapper() {
        return new DirectoryRolePolicyMapper();
    }

    @Bean
    public LdapAuthenticationProvider ldapAuthenticationProvider(
            @Qualifier("securityLdapContextSource")
            LdapContextSource source,
            GrantedAuthoritiesMapper directoryRolePolicyMapper) {

        BindAuthenticator authenticator =
                new BindAuthenticator(source);

        // Chỉ hợp lệ khi DN của người dùng có cấu trúc cố định.
        authenticator.setUserDnPatterns(
                new String[] { "uid={0},ou=people" });

        DefaultLdapAuthoritiesPopulator populator =
                new DefaultLdapAuthoritiesPopulator(
                        source, "ou=app-roles,ou=groups");

        populator.setGroupSearchFilter(
                "(&(objectClass=groupOfNames)(member={0}))");
        populator.setGroupRoleAttribute("cn");
        populator.setSearchSubtree(false);

        // Không đổi uppercase/prefix ở đây;
        // mapper allowlist làm bước chuẩn hóa duy nhất.
        populator.setRolePrefix("");
        populator.setConvertToUpperCase(false);

        LdapAuthenticationProvider provider =
                new LdapAuthenticationProvider(
                        authenticator, populator);
        provider.setAuthoritiesMapper(
                directoryRolePolicyMapper);
        return provider;
    }
}
~~~

Spring container tự gọi lifecycle của bean `LdapContextSource`. Nếu dự án đã có nhiều ContextSource, `@Qualifier` phải chỉ chính xác bean dùng cho LDAP authentication; tránh tự động dùng service account quản trị từ một bean `@Primary` khác.

**Luồng xử lý:**

1. Người dùng nhập username/password qua kênh HTTPS.
2. `BindAuthenticator` xác thực bằng LDAP Bind với DN người dùng phù hợp pattern.
3. Nếu Bind thành công, `DefaultLdapAuthoritiesPopulator` tìm các entry nhóm ở `ou=app-roles,ou=groups` với `member={0}`.
4. Tên nhóm lấy từ `cn`, **không thêm `ROLE_` và không tự uppercase**.
5. `DirectoryRolePolicyMapper` chỉ chấp nhận ba tên nhóm chính thức và trả authority canonical.
6. `LdapAuthenticationProvider` đưa authorities đã chuẩn hóa vào `Authentication`.

**Quan trọng:** `LdapAuthenticationProvider` cần được đăng ký với cơ chế authentication đang xử lý HTTP request (chẳng hạn qua `HttpSecurity.authenticationProvider(...)`). Khai báo bean đơn lẻ chưa chứng minh mọi `AuthenticationManager` trong dự án thực sự dùng provider này; phải kiểm thử luồng login.

### 11.3. Khi DN người dùng không cố định

`setUserDnPatterns("uid={0},ou=people")` chỉ thích hợp khi entry người dùng nằm trực tiếp dưới OU đó. Nếu user nằm trong nhiều OU con, cấu hình `FilterBasedLdapUserSearch`/factory với `userSearchBase` và `userSearchFilter` có thể phù hợp hơn.

Ví dụ ý định:

~~~text
userSearchBase   = ou=people
userSearchFilter = (uid={0})
~~~

Hãy dùng API tìm kiếm của Spring Security LDAP có tham số placeholder được escape đúng, không tự nối filter `"(uid=" + username + ")"`. Đảm bảo Search nằm trong nhánh đã phê duyệt và không tự chuyển sang tài khoản quản trị khi tìm không thấy.

## 12. Cấu hình SecurityFilterChain và method authorization

### 12.1. HTTP authorization

`security/WebSecurityConfig.java`:

~~~java
package com.example.directory.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.ldap.authentication.LdapAuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LdapAuthenticationProvider ldapAuthenticationProvider)
            throws Exception {

        http.authenticationProvider(ldapAuthenticationProvider);

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/v1/directory/**")
                .hasAnyRole("DIRECTORY_VIEWER", "ACCOUNT_ADMIN")
            .requestMatchers(HttpMethod.POST, "/api/v1/accounts/**")
                .hasRole("ACCOUNT_ADMIN")
            .requestMatchers(HttpMethod.PUT, "/api/v1/groups/**")
                .hasRole("GROUP_MANAGER")
            .anyRequest().denyAll()
        );

        // Chỉ để minh họa authentication flow:
        // HTTP Basic phải chạy qua HTTPS; production có thể dùng
        // session/OIDC hoặc authentication scheme khác.
        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Code không tự tạo chứng chỉ HTTPS hoặc vô hiệu hóa CSRF; điều này phải được thiết kế trong cấu hình web/infrastructure phù hợp. Với `POST`/`PUT` và cơ chế cookie/session, cần chính sách CSRF đầy đủ. Đừng tắt CSRF đại trà chỉ để bài test có thể gửi request ghi.

### 12.2. Bảo vệ thêm ở tầng service

Ví dụ service nghiệp vụ:

~~~java
package com.example.directory.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountAdministrationService {

    @PreAuthorize("hasRole('ACCOUNT_ADMIN')")
    public void createEmployeeProfile(CreateEmployeeCommand command) {
        // Kiểm tra request, kiểm tra quyền trên đối tượng/tenant,
        // rồi dùng LdapTemplate có ACL ghi giới hạn.
    }

    @PreAuthorize("hasRole('GROUP_MANAGER')")
    public void addGroupMember(String groupId, String uid) {
        // Kiểm tra groupId/uid, quyền quản lý nhóm,
        // rồi Modify có chọn lọc thuộc tính member.
    }
}
~~~

`CreateEmployeeCommand` là DTO/command nghiệp vụ của ứng dụng (cần khai báo trong dự án thực tế). Ví dụ chỉ thể hiện **ranh giới quyền**, không phải một implementation CRUD hoàn chỉnh.

Trong Spring Security, `@PreAuthorize` phụ thuộc proxy của Spring (khi đã bật `@EnableMethodSecurity`). Lời gọi nội bộ từ method này sang method khác của **cùng object** có thể bỏ qua advice. Vì vậy các endpoint và service khác phải gọi qua bean được Spring quản lý.

### 12.3. ROLE_ACCOUNT_ADMIN không tự bao hàm mọi role

Trong ví dụ URL GET, quy tắc:

~~~java
.hasAnyRole("DIRECTORY_VIEWER", "ACCOUNT_ADMIN")
~~~

cho phép viewer **hoặc** account admin đọc danh bạ. Đó là một **quyết định policy có chủ đích**. Không phải Spring Security tự suy ra `ACCOUNT_ADMIN` là cấp cao hơn `DIRECTORY_VIEWER`.

Nếu muốn một hệ phân cấp cố định, có thể dùng cơ chế role hierarchy/authorization riêng, nhưng phải mô tả, kiểm thử và rà soát các đường thừa kế. Với quyền nhạy cảm như reset password, nên cân nhắc authority cụ thể thay vì phán đoán từ thứ tự tên role.

## 13. Kết hợp Spring Data LDAP và Spring Security: đúng trách nhiệm

Spring Data LDAP cung cấp mô hình entity/repository để đọc, sửa và tìm entry LDAP. Spring Security cung cấp cơ chế **authentication và authorization**. Chúng có thể chia sẻ directory nhưng không phải cùng một tầng xử lý.

Ví dụ entity nhóm để đọc/kiểm tra:

~~~java
package com.example.directory.model;

import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=app-roles,ou=groups",
    objectClasses = { "top", "groupOfNames" }
)
public class DirectoryRoleGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "member")
    private Set<Name> members;

    // Thêm constructor/getter/setter theo mô hình thực tế.
}
~~~

Repository đọc nhóm:

~~~java
package com.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.DirectoryRoleGroup;

public interface DirectoryRoleGroupRepository
        extends LdapRepository<DirectoryRoleGroup> {
}
~~~

**Cẩn trọng:** `LdapRepository` có sẵn `save/delete`. Nếu một repository được cấu hình bằng ContextSource của tài khoản **chỉ đọc**, LDAP ACL phải ngăn thao tác ghi bất kể repository expose method nào. Không coi việc đặt tên `ReadOnlyRepository` là một biện pháp kiểm soát quyền server.

### Search nhóm an toàn bằng LdapTemplate

Nếu cần một chức năng quản trị **kiểm tra** trạng thái nhóm (không phải thay cách Spring Security xác thực), có thể viết:

~~~java
import java.util.List;

import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;

// Chỉ dùng DN đầy đủ làm giá trị member.
Name fullUserDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", validatedUid)
        .build();

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=app-roles,ou=groups")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(30)
        .timeLimit(2_000)
        .attributes("cn")
        .where("objectClass").is("groupOfNames")
        .and("member").is(fullUserDn.toString());

List<String> matchingGroupNames = ldapTemplate.search(
        query,
        (AttributesMapper<String>)
                attrs -> attrs.get("cn").get().toString()
);
~~~

- `fullUserDn` là **DN đầy đủ** vì giá trị `groupOfNames.member` là DN đầy đủ.
- `LdapQueryBuilder` mã hóa giá trị filter theo cú pháp LDAP, tránh nối chuỗi thủ công.
- `countLimit` và `timeLimit` giúp giới hạn tài nguyên, nhưng **kết quả giới hạn hoặc partial không được tự coi là đầy đủ**.
- Service account của template phải có quyền Search/Read các thuộc tính cần thiết.
- **Không đưa `matchingGroupNames` trực tiếp thành authorities nếu chưa qua mapper chính sách.**

Ví dụ `LdapTemplate` trên là cách tự đọc directory phục vụ kiểm chứng. Khi đã sử dụng `DefaultLdapAuthoritiesPopulator` để lấy nhóm cho authentication, không cần tự viết một cơ chế đọc nhóm thứ hai chỉ để tạo authorities — tránh hai nguồn quy tắc khác nhau.

## 14. Vai trò nào được phép điều chỉnh nhóm quyền?

Vùng `ou=app-roles,ou=groups` là **dữ liệu ủy quyền**, không chỉ là danh sách liên hệ. Nếu một người có quyền tạo nhóm tùy ý hoặc sửa `member` của nhóm `account-admins`, họ có thể cấp `ROLE_ACCOUNT_ADMIN` cho chính mình trong lần xác thực kế tiếp.

Vì vậy cần:

1. Giới hạn LDAP ACL để chỉ tài khoản quản trị nhóm được phê duyệt mới có quyền Add/Modify/Delete trong vùng role groups.
2. Tách dịch vụ đọc nhóm khỏi dịch vụ ghi nhóm, bằng **Bind DN và secret riêng**.
3. Xác thực và phân quyền HTTP trước khi gọi Modify `member`.
4. Yêu cầu audit/approval đối với nhóm nhạy cảm như `account-admins`.
5. Không cho HTTP client gửi `memberDn`/`roleName` tùy ý rồi ghi trực tiếp mà không kiểm tra policy.
6. Dùng `LdapNameBuilder` cho DN và `ModificationItem` khi thêm/xóa **một giá trị member**, tránh thay toàn bộ danh sách.
7. Bảo đảm `groupOfNames` luôn có ít nhất một `member` theo schema.
8. Kiểm thử quyền LDAP từ chối request ghi với tài khoản đọc.

### ACL phải bảo vệ nguồn quyền

Một tên group được whitelist **không đủ** nếu bất kỳ nhân viên nào có thể tự thêm DN của họ vào group. Tính an toàn của mapping dựa trên **cả tính toàn vẹn của nhóm LDAP** và **hợp đồng authorization ứng dụng**.

Không dùng account rootdn của OpenLDAP để làm reader hoặc group writer trong ứng dụng; rootdn có thể vượt qua ACL thông thường, khiến các test phân quyền không còn ý nghĩa.

## 15. Những tình huống khác biệt schema và topology

### 15.1. groupOfNames với member

Trong bài, `groupOfNames` sử dụng thuộc tính `member` chứa DN đầy đủ của người dùng. Filter `(member={0})` phù hợp với mô hình này.

### 15.2. groupOfUniqueNames với uniqueMember

Một directory khác có thể sử dụng `groupOfUniqueNames` và thuộc tính `uniqueMember`. Khi đó filter phải dùng **đúng thuộc tính schema**; không thể thay tên field trong Java mà mong server coi là `member`.

### 15.3. posixGroup với memberUid

Trong nhiều triển khai POSIX, `posixGroup.memberUid` chứa **username**, không phải DN. Khi đó chiến lược filter có thể cần `{1}` thay `{0}`, đồng thời phải đánh giá tính duy nhất username trong phạm vi directory.

### 15.4. memberOf trên entry người dùng

Một số directory có overlay/plugin cung cấp `memberOf`, nhưng LDAP không mặc định bắt buộc có thuộc tính này. Không được kết luận “không có nhóm” chỉ vì entity `inetOrgPerson` không trả `memberOf`.

### 15.5. Nhóm lồng nhau

Giả sử:

~~~text
uid=lan thuộc cn=engineering
cn=engineering thuộc cn=directory-readers
~~~

`DefaultLdapAuthoritiesPopulator` với filter `member={0}` thông thường tìm **membership trực tiếp của user DN**, không tự tính đóng bắc cầu qua tất cả nhóm lồng nhau.

Nếu cần nested groups, phải có chính sách rõ ràng về độ sâu, vòng lặp, server extension, quyền Search và cách xử lý kết quả không đầy đủ. Một số directory hỗ trợ matching rule riêng cho nested membership; không giả định chúng tương thích giữa OpenLDAP và Active Directory.

**Đừng nới filter hay scope tùy tiện** chỉ để một account có role nếu chưa xác định mô hình nhóm và toàn bộ hậu quả phân quyền.

## 16. Lỗi directory, kết quả nhóm chưa đầy đủ và nguyên tắc fail closed

Một yêu cầu truy xuất nhóm có thể thất bại vì:

- `invalidCredentials (49)` khi Bind người dùng hoặc service account sai.
- `insufficientAccessRights (50)` khi account đọc nhóm không được Search/Read `member`/`cn`.
- `noSuchObject (32)` nếu `ou=app-roles,ou=groups` không tồn tại.
- `sizeLimitExceeded (4)` hoặc `timeLimitExceeded (3)` khiến Search chưa hoàn chỉnh.
- `referral (10)` hoặc continuation reference dẫn tới nhánh/server khác.
- TLS handshake, DNS, TCP timeout hoặc server `unavailable (52)`.

**Không mặc định biến mọi lỗi thành “user không có nhóm” rồi cho rằng hệ thống đã xử lý đúng.** Với quyền quản trị, nếu không xác minh được membership, **không cấp quyền**; đồng thời nên trả lỗi đăng nhập/ủy quyền phù hợp và ghi nhận sự cố thay vì âm thầm tiếp tục với kết quả được coi là đầy đủ.

Đặc biệt:

- Không tự bỏ qua `PartialResultException` và coi toàn bộ role đã được tìm.
- Không thay đổi credential sang rootdn khi Search nhóm thiếu quyền.
- Không follow referral sang server bất kỳ rồi chuyển mật khẩu Bind.
- Không thử “role mặc định” `ROLE_ACCOUNT_ADMIN` để khắc phục sự cố nhóm.
- Không log mật khẩu, LDAP Bind secret, token hoặc raw diagnostic message.

Một hệ thống có thể cho phép người dùng **đăng nhập nhưng không có authority ứng dụng** nếu không thuộc nhóm nào; đó là quyết định về access policy. Còn nếu **không truy xuất được nhóm vì lỗi hạ tầng**, phải phân biệt với trường hợp “đã truy vấn đầy đủ và người dùng không thuộc nhóm”.

## 17. Thu hồi quyền và vấn đề cache/session/JWT

Chuẩn hóa authority đúng tại login **không bảo đảm quyền thay đổi tức thì**.

Ví dụ:

1. Mai đăng nhập, thành viên `cn=account-admins`.
2. Spring Security cấp `ROLE_ACCOUNT_ADMIN` trong `Authentication` hiện tại.
3. Quản trị viên xóa DN của Mai khỏi `member` trên LDAP.
4. Session hoặc JWT cũ của Mai **có thể vẫn chứa quyền quản trị** cho đến khi có cơ chế refresh/invalidation.

### Những chiến lược xử lý

| Cách tiếp cận | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Lấy group khi đăng nhập | Hiệu quả, ít Search. | Quyền có thể cũ trong session/token. |
| Session TTL ngắn + đăng nhập lại | Giảm thời gian tồn tại của authority cũ. | Không thu hồi ngay nếu session chưa hết hạn. |
| Chủ động invalidation session/token | Phù hợp với vai trò nhạy cảm. | Cần cơ chế quản lý session/token tập trung. |
| Kiểm tra quyền lại khi thực hiện thao tác đặc quyền | Phản ánh thay đổi gần thực tế hơn. | Tăng độ trễ và phụ thuộc LDAP availability. |
| Policy-version/claim/authorization cache có TTL | Có thể giảm tải và hỗ trợ đổi policy. | Phải xác định thời điểm làm mới và xử lý sự cố nhất quán. |

Nếu JWT chứa danh sách `ROLE_*` từ thời điểm cấp token, resource server **không tự biết** membership LDAP đã đổi. Muốn thu hồi nhanh phải có thiết kế TTL/rotation/revocation hoặc kiểm tra động theo chính sách.

Cũng nên tránh lưu **LDAP group DN** không được xác minh như claim “admin” do client tự gửi. Authority đáng tin phải đến từ tầng authentication/authorization do server kiểm soát.

## 18. Kiểm thử tích hợp với LDAP thật

Unit test mapper là cần thiết nhưng chưa đủ. Để chứng minh kết nối LDAP và Spring Security hoạt động đúng, cần một directory test với schema `inetOrgPerson`, `groupOfNames`, OU và service account có ACL phù hợp.

### 18.1. Kịch bản dữ liệu

- Lan thuộc `directory-readers`.
- Mai thuộc `account-admins`.
- Minh thuộc `group-managers`.
- Một người dùng test khác không thuộc nhóm `app-roles`.
- Một group ngoài `ou=app-roles,ou=groups` có `cn=account-admins` nhưng **không được ánh xạ**.
- Một nhóm trong vùng cho phép có tên lạ như `account-admins-extra`.
- Directory có TLS hợp lệ, Bind user và service reader tách quyền.

### 18.2. Kiểm tra bằng ldapsearch

Dùng tài khoản reader của security service:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-security-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=app-roles,ou=groups,dc=example,dc=org" \
  -s one \
  "(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))" \
  dn cn member
~~~

Kỳ vọng chỉ thấy nhóm `cn=directory-readers`, nếu ACL cho phép. Đây là lệnh CLI với dữ liệu cố định; trong Java **không được ghép raw filter từ input HTTP** mà dùng API filter có escape.

Để kiểm tra Mai, đổi DN người dùng trong filter và kỳ vọng `cn=account-admins`. Để chứng minh chỉ nhóm ở đúng subtree được tính, chạy Search riêng tại OU bên ngoài và xác minh nhóm ngoài policy không ảnh hưởng authorities.

### 18.3. Ma trận tích hợp và âm tính

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Lan Bind đúng, thuộc `directory-readers` | Có `ROLE_DIRECTORY_VIEWER`, không có `ROLE_ACCOUNT_ADMIN`. |
| Mai Bind đúng, thuộc `account-admins` | Có `ROLE_ACCOUNT_ADMIN`. |
| Minh thuộc `group-managers` | Có `ROLE_GROUP_MANAGER`, không tự có quyền account admin. |
| Người dùng không có nhóm trong allowlist | Không có ba role ứng dụng. |
| Username/password sai | Authentication thất bại; không có quyền do group lookup. |
| Nhóm `account-admins` nằm ngoài groupSearchBase | Không cấp `ROLE_ACCOUNT_ADMIN`. |
| `cn=admin` hoặc `cn=ROLE_ADMIN` | Không cấp `ROLE_ACCOUNT_ADMIN` hay role admin không được phê duyệt. |
| `cn=ACCOUNT-ADMINS` trong đúng scope | Được map theo quy tắc case của policy, sau khi nguồn đã được kiểm soát. |
| Thêm cùng DN thành viên hai lần | Directory/logic group manager xử lý trùng; mapper không sinh authority trùng. |
| Xóa thành viên Lan khỏi `directory-readers` | Đăng nhập/refresh mới không có `ROLE_DIRECTORY_VIEWER`. |
| Session cũ của Lan | Có thể còn authority cũ; policy revocation phải xử lý. |
| Account reader thiếu quyền Search nhóm | Không được fallback sang admin service account. |
| Search nhóm bị limit/partial | Không đánh dấu membership đầy đủ để tự cấp quyền. |
| Directory trả referral không được phê duyệt | Không tự kết nối tới đích khác với credential hiện tại. |
| Nhóm lồng nhau nhưng chưa cấu hình recursive | Không coi membership gián tiếp là trực tiếp. |
| User gửi role trong JSON | Không có tác dụng thay đổi authorities của `Authentication`. |
| Người gọi chỉ có viewer gọi POST tài khoản | HTTP 403, service quản trị không chạy. |
| Người gọi có group manager gọi account admin API | Bị chặn nếu thiếu `ROLE_ACCOUNT_ADMIN`. |
| ACL reader bị thử Modify `member` | LDAP từ chối, nhóm không thay đổi. |
| TLS certificate/hostname sai | Bind/Search thất bại; không fallback plaintext. |

### 18.4. Test chính sách request bằng Spring Security Test

Ví dụ MockMvc, khi đã cấu hình authentication/authorization và controller tương ứng:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RoleAuthorizationHttpTest {

    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(roles = "DIRECTORY_VIEWER")
    void viewerCannotCreateAccount() throws Exception {
        mvc.perform(post("/api/v1/accounts/demo")
                .with(csrf()))
           .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ giả định có route `POST /api/v1/accounts/demo`. Cần bổ sung request body/content type hợp lệ hoặc mock boundary phù hợp để request thực sự đi tới authorization; với một controller yêu cầu JSON, body sai có thể sinh lỗi 400 nếu security không chặn trước.

`@WithMockUser(roles="DIRECTORY_VIEWER")` tự gắn authority `ROLE_DIRECTORY_VIEWER` trong test. Đó là cách kiểm tra **quy tắc phân quyền**, không kiểm thử luồng LDAP → `DefaultLdapAuthoritiesPopulator` → mapper. Phải có test tích hợp riêng cho phần xác thực.

### 18.5. Test tích hợp LDAP AuthenticationProvider

Một integration test có thể gọi `AuthenticationManager`/`LdapAuthenticationProvider` bằng **test user** đã có mật khẩu trong directory riêng, xác nhận:

- `Authentication.isAuthenticated()` là true khi Bind đúng.
- `Authentication.getAuthorities()` chỉ chứa role từ allowlist.
- Bind sai mật khẩu thất bại; không có fallback anonymous Bind.
- Khi xóa membership rồi đăng nhập lại, authority biến mất.
- Không có `ROLE_ADMIN` do nhóm lạ hoặc nhánh ngoài.
- Kết nối LDAP có TLS và đủ quyền đọc `cn`/`member`, không đủ quyền Modify nhóm.

Không lưu password thật trong source/test logs. Test có thể lấy secret test từ environment; fixture độc lập phải được reset sau mỗi test nếu có thay đổi membership.

## 19. Các lỗi hay gặp khi chuẩn hóa tên vai trò

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có LDAP group nhưng `hasRole` luôn false | Sai tiền tố/case hoặc mapper không được gắn vào provider đang dùng. | Kiểm tra `Authentication.getAuthorities()` ở môi trường test (không lộ dữ liệu nhạy cảm). |
| `hasRole("ROLE_ACCOUNT_ADMIN")` không hoạt động | Dùng prefix hai lần hoặc API không nhận tên có prefix. | Dùng `hasRole("ACCOUNT_ADMIN")`. |
| `hasAuthority("ACCOUNT_ADMIN")` không khớp | Authentication chứa `ROLE_ACCOUNT_ADMIN`. | Dùng `hasAuthority("ROLE_ACCOUNT_ADMIN")`. |
| Group tên `directory-readers` thành `ROLE_DIRECTORY-READERS` | Dùng uppercase/prefix thay vì alias mapping. | Dùng `GrantedAuthoritiesMapper` allowlist. |
| Bất kỳ group LDAP nào cũng tạo role | Không hạn chế groupSearchBase hoặc map input tự do. | Giới hạn subtree, group name allowlist, ACL. |
| Vai trò tự nâng sau khi user sửa nhóm | ACL trên `member` hoặc `cn` quá rộng. | Chỉ group manager được phép sửa role groups; audit. |
| Không thấy role trong OU con | `searchSubtree=false` trong khi nhóm nằm ở tầng sâu. | Thiết kế groupSearchBase/scope chính xác, không mở rộng không kiểm soát. |
| Không thấy role vì user DN khác | Filter dùng username thay DN, hoặc người dùng đã Move/Rename. | Kiểm tra `{0}`/`{1}` và tham chiếu `member`. |
| Phân quyền không cập nhật sau xóa nhóm | Session/JWT còn authorities cũ. | Thiết kế TTL, re-authentication hoặc revocation. |
| Có quyền ở môi trường test nhưng không ở production | Schema nhóm, ACL, attribute hoặc base khác nhau. | Kiểm chứng cùng directory type/config và Bind DN. |
| Role xuất hiện khi Search group thất bại | Fallback role nguy hiểm hoặc bắt lỗi sai. | Fail closed, không cấp quyền nếu không xác minh được. |
| Quyền chỉ đọc được dùng để Modify và vẫn thành công | Account reader có ACL ghi quá rộng hoặc dùng rootdn. | Sửa ACL, test âm tính bằng Bind DN thật. |
| Group lồng nhau không được nhận diện | Populator chỉ duyệt membership trực tiếp. | Định nghĩa chiến lược nested groups có kiểm soát. |
| Authority từ JWT và LDAP không đồng nhất | Có hai nơi chuẩn hóa với chính sách khác nhau. | Chuẩn hóa tại một ranh giới được tin cậy, version policy. |

## 20. Checklist chính sách trước khi triển khai

| Hạng mục | Yêu cầu |
| --- | --- |
| Mapping | Có bảng nguồn LDAP group → canonical role, được review và version. |
| Prefix | Chỉ một tầng quản lý `ROLE_`; `hasRole`/`hasAuthority` dùng đúng. |
| Case | Quy tắc locale/case rõ ràng, không dựa vào locale máy chạy. |
| Source | `groupSearchBase` cố định, đúng OU bảo mật, scope hợp lý. |
| Membership | `groupOfNames.member` là DN đầy đủ; xử lý Rename/Move người dùng. |
| Input | Client không thể gửi authority hoặc DN tùy ý để được cấp quyền. |
| LDAP ACL | Service reader không thể Modify/tạo/xóa nhóm; admin nhóm được quản lý chặt. |
| Authentication | User Bind qua TLS; không tự xác thực bằng dữ liệu `userPassword` được đọc ra. |
| Fail closed | Không cấp quyền khi nhóm không xác minh được; log lỗi theo chính sách. |
| Nested groups | Có hoặc không hỗ trợ được nêu rõ, không suy đoán. |
| Multi-tenant | Scope quyền gắn tenant/region, không trùng cn giữa vùng. |
| Authorization | SecurityFilterChain và method security dùng cùng canonical role. |
| Session/token | Có chính sách làm mới và thu hồi role. |
| Observability | Log role transition/authorization outcome, không log password/token/raw LDAP. |
| Tests | Mapper unit test, LDAP integration, HTTP positive/negative, revoked access. |
| Review | Khi nhóm/cấu trúc OU/ACL đổi, mapping và test được xem xét lại. |

## 21. Bài tập thực hành

**Bài 1 — Chuẩn hóa mapping.** Thêm một nhóm `cn=auditors` vào directory test và đề xuất authority canonical `ROLE_AUDITOR`. Đặt tên trong mapper theo allowlist và viết test bảo đảm `cn=audit-admin` không được cấp quyền auditor.

**Bài 2 — Prefix hai lần.** Bật `setRolePrefix("ROLE_")` tại populator nhưng giữ nguyên mapper đang mong raw `cn`. Dự đoán vì sao ánh xạ mất hiệu lực; đề xuất sửa bằng cách để một tầng duy nhất xử lý canonical names.

**Bài 3 — Giới hạn nguồn nhóm.** Tạo hai `cn=account-admins` ở hai nhánh LDAP khác nhau. Cấu hình Search chỉ lấy một nhánh và chứng minh nhóm nằm ngoài scope không được tạo `ROLE_ACCOUNT_ADMIN`.

**Bài 4 — Đổi username.** Rename `uid=lan` thành `uid=lan.nguyen` trong directory test. Kiểm tra `groupOfNames.member` có được server cập nhật DN hay không và vai trò sau đăng nhập mới.

**Bài 5 — Thu hồi quyền.** Gỡ Mai khỏi `account-admins`, thử session hiện tại và đăng nhập lại. Thiết kế thời gian tối đa được phép giữ quyền cũ theo mức rủi ro nghiệp vụ.

**Bài 6 — Quyền nhóm bị chặn.** Bind bằng `svc-security-reader` rồi thử sửa `member` của `cn=account-admins`. LDAP phải từ chối; viết integration test xác nhận dữ liệu nhóm không đổi.

**Bài 7 — Custom permission.** Giả sử chức năng reset mật khẩu yêu cầu `ACCOUNT_RESET_PASSWORD`. Thiết kế phép ánh xạ/chính sách riêng, không tự gán quyền này cho mọi role có chứa chữ `ADMIN`.

**Bài 8 — Mô hình khác.** Thay `groupOfNames.member` bằng `posixGroup.memberUid` trong directory test có schema tương ứng. Xác định vì sao `{0}` không còn là tham số phù hợp cho thuộc tính thành viên.

## 22. Câu hỏi tự đánh giá

1. Tên nhóm LDAP có đồng nghĩa tên vai trò Spring Security không?
2. `DefaultLdapAuthoritiesPopulator` lấy tên group từ thuộc tính nào theo mặc định?
3. `groupSearchFilter` dùng `{0}` và `{1}` cho hai giá trị nào?
4. Vì sao `groupSearchBase` phải nằm trong subtree tin cậy, không để client tự quyết định?
5. `SimpleAuthorityMapper` giải quyết được việc chuyển `directory-readers` sang `ROLE_DIRECTORY_VIEWER` theo alias không?
6. Khác biệt giữa `hasRole("ACCOUNT_ADMIN")` và `hasAuthority("ROLE_ACCOUNT_ADMIN")` là gì?
7. Vì sao không nên đặt `setDefaultRole("ROLE_ADMIN")` để xử lý trường hợp LDAP không trả nhóm?
8. Một `cn=admin` xuất hiện trong directory có nên tự tạo `ROLE_ADMIN` không? Vì sao?
9. Vì sao mapper cần loại trùng authority nhưng không được tự cấp quyền mới?
10. Nếu một người thuộc nhóm ở OU khác có cùng `cn`, mapping theo tên có an toàn không?
11. Vì sao `memberOf` không thể được giả định có trên mọi LDAP server?
12. Khi nhóm lồng nhau, filter `member={0}` có mặc định tìm được tổ tiên của nhóm đó không?
13. Người dùng có `ROLE_ACCOUNT_ADMIN` trong HTTP có tự được quyền LDAP Modify không?
14. Làm thế nào bảo vệ group `account-admins` trước tự ý thêm thành viên?
15. Vì sao sau khi bị xóa khỏi nhóm, session/JWT cũ vẫn có thể giữ role?
16. Kiểm thử mapper bằng mock có chứng minh được ACL LDAP và Bind thật không?
17. Vì sao không được gửi credential tới referral ngoài topology đã phê duyệt?
18. Nếu Search nhóm bị giới hạn/partial, nên quyết định authority như thế nào?
19. Khi đổi OU/naming context, phải kiểm tra những ranh giới nào trước khi chấp nhận role?
20. Tại sao canonical role names nên là hợp đồng versioned, không dựa vào tên nhóm hiện có một cách tùy tiện?

**Ghi nhớ:** trong Spring Security + Spring Data LDAP, tên nhóm LDAP là **dữ liệu đầu vào của quyết định ủy quyền**, không phải quyền ứng dụng tự nhiên. Hãy giới hạn nơi tìm nhóm, lấy membership theo DN đúng schema, **ánh xạ bằng allowlist sang authority canonical**, dùng `ROLE_`/`hasRole`/`hasAuthority` nhất quán, bảo vệ ACL thay đổi nhóm và kiểm thử cả quyền được cấp lẫn quyền bị từ chối. Với session/JWT, phải thiết kế cách làm mới/thu hồi authority khi membership LDAP thay đổi.

### Tài liệu tham khảo

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): LDAP Bind, user search và cách xác thực người dùng.
- [Spring Security — DefaultLdapAuthoritiesPopulator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html): `groupSearchBase`, `groupRoleAttribute`, `groupSearchFilter`, `{0}`, `{1}`, `rolePrefix` và `convertToUpperCase`.
- [Spring Security — LdapAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/LdapAuthenticationProvider.html): nối LdapAuthenticator, AuthoritiesPopulator và mapper.
- [Spring Security — SimpleAuthorityMapper API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/SimpleAuthorityMapper.html): chuẩn hóa case/prefix và default authority.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority`, `SimpleGrantedAuthority`, vai trò và prefix.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`, `hasAuthority` và quy tắc URL.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và proxy.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): Search, Modify và các giới hạn LDAP.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM `@Entry`/`@Id`/`@Attribute` và repository.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search/Bind/Modify, filter và result codes.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, objectClass và schema LDAP.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): `groupOfNames`, `member` và `cn`.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): escaping DN.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escaping giá trị LDAP filter.
