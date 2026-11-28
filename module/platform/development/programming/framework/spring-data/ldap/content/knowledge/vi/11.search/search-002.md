# Chọn search base phù hợp với ranh giới dữ liệu

> **Chương:** Tìm kiếm  
> **Phạm vi:** Spring Data LDAP — truy cập directory theo cây DN, ánh xạ LDAP entry sang đối tượng Java và tìm kiếm qua repository hoặc `LdapTemplate`.

Trong LDAP, **search base** là Distinguished Name (DN) xác định **điểm bắt đầu của một phép tìm kiếm** trong cây thư mục. Nếu chọn search base quá rộng, truy vấn có thể quét nhiều nhánh không liên quan, trả về dữ liệu ngoài phạm vi nghiệp vụ và làm khó việc thực thi chính sách phân quyền. Nếu chọn quá hẹp hoặc nhầm DN tương đối, ứng dụng không tìm thấy entry dù dữ liệu vẫn tồn tại.

Ví dụ, một ứng dụng nhân sự chỉ cần tìm nhân viên trong `ou=staff,ou=people,dc=example,dc=org`. Thực hiện cùng bộ lọc `(uid=lan)` ở gốc `dc=example,dc=org` có thể tìm thấy thêm tài khoản dịch vụ hoặc tài khoản của đối tác nếu chúng có `uid` giống nhau. **Filter quyết định entry nào khớp điều kiện; search base và search scope quyết định server sẽ xem xét vùng nào trong cây.**

Trong Spring Data LDAP, cần phối hợp đúng ba tầng:

1. Base DN của `ContextSource` (thường từ `spring.ldap.base`).
2. Search base và search scope của truy vấn hoặc phạm vi entity/repository.
3. Quyền truy cập thực tế do directory server áp dụng (ACL và các chính sách khác).

Bài học hướng dẫn cách chọn và kiểm thử các tầng này khi dữ liệu được phân chia theo OU, loại tài khoản, tổ chức hoặc tenant.

## 1. Search base là gì?

Xét một cây thư mục đơn giản:

~~~text
dc=example,dc=org
├── ou=people
│   ├── ou=staff
│   │   ├── uid=lan
│   │   └── uid=binh
│   └── ou=partners
│       └── uid=lan
├── ou=service-accounts
│   └── uid=sync
├── ou=groups
│   └── cn=developers
└── ou=archive
    └── uid=former
~~~

Từ cây này có thể thực hiện nhiều phép tìm kiếm khác nhau:

| Mục tiêu | Search base tuyệt đối phù hợp | Lý do |
|---|---|---|
| Tìm nhân viên | `ou=staff,ou=people,dc=example,dc=org` | Chỉ quan tâm nhánh nhân viên |
| Tìm đối tác | `ou=partners,ou=people,dc=example,dc=org` | Tránh lẫn người dùng nội bộ |
| Tìm tài khoản dịch vụ | `ou=service-accounts,dc=example,dc=org` | Mô hình và quyền khác tài khoản cá nhân |
| Tìm nhóm | `ou=groups,dc=example,dc=org` | Không cần quét nhánh người dùng |
| Tìm mọi người dùng đang hoạt động thuộc hai nhánh | `ou=people,dc=example,dc=org` | Bao phủ staff và partners; cần lọc thêm nếu chỉ chọn một loại |
| Truy vấn theo DN chính xác | `uid=lan,ou=staff,ou=people,dc=example,dc=org` | Có thể dùng `OBJECT` scope cho đúng một entry |

Một **entry** được định danh bằng DN đầy đủ. Một **RDN** là phần tên tương đối đối với parent, ví dụ `uid=lan`. Nhiều entry có thể dùng cùng RDN nhưng nằm ở các parent khác nhau; do đó, `uid=lan,ou=staff,...` và `uid=lan,ou=partners,...` là hai DN khác nhau.

**Search base không phải filter.** `(uid=lan)` là điều kiện lọc theo thuộc tính; `ou=staff,ou=people,...` là vị trí tìm kiếm. Cả hai cùng tác động đến kết quả, nhưng không thay thế cho nhau.

## 2. Base DN, search base và search scope khác nhau ra sao?

Từ “base” thường xuất hiện ở nhiều lớp nên dễ bị nhầm:

| Khái niệm | Nơi cấu hình | Tác dụng |
|---|---|---|
| **ContextSource base DN** | `spring.ldap.base` hoặc cấu hình `LdapContextSource` | Gốc tương đối cho các DN mà Spring LDAP gửi tới directory |
| **Search base của truy vấn** | `query().base(...)`, các overload `LdapTemplate.search(...)` hoặc metadata truy vấn | Entry bắt đầu tìm trong phạm vi kết nối |
| **Search scope** | `SearchScope.OBJECT`, `ONELEVEL`, `SUBTREE` | Quyết định duyệt chính entry gốc, con trực tiếp hay cả cây con |
| **Search filter** | Ví dụ `(objectClass=inetOrgPerson)` | Chọn entry khớp điều kiện bên trong phạm vi đã xác định |
| **ACL/server policy** | Cấu hình directory server | Quyết định client có được tìm hoặc đọc dữ liệu thực sự hay không |

Giả sử cấu hình kết nối:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Với `spring.ldap.base=dc=example,dc=org`, lời gọi Spring LDAP:

~~~java
query().base("ou=staff,ou=people")
~~~

được hiểu trong ngữ cảnh base của `ContextSource`. Vùng tìm kiếm thực tế bắt đầu từ:

~~~text
ou=staff,ou=people,dc=example,dc=org
~~~

Không thêm `dc=example,dc=org` lần nữa vào `query().base(...)` khi `ContextSource` đã cấu hình base tương ứng; một số trường hợp sẽ tạo thành DN sai hoặc đường dẫn không tồn tại.

Nếu `ContextSource` không có base DN, đường dẫn truy vấn phải được thiết kế cho phạm vi thực tế của directory (có thể cần DN đầy đủ). Tổ chức nên dùng một quy ước nhất quán để tránh nhầm lẫn giữa DN **tuyệt đối** và DN **tương đối với `ContextSource`**.

### Ba giá trị search scope

Xét base `ou=people,dc=example,dc=org`:

| Scope | Những entry nằm trong phạm vi |
|---|---|
| `OBJECT` | Chỉ entry `ou=people,dc=example,dc=org` |
| `ONELEVEL` | Chỉ các con trực tiếp, ví dụ `ou=staff` và `ou=partners` |
| `SUBTREE` | Chính entry `ou=people` và toàn bộ con/cháu, gồm người dùng ở `staff` và `partners` |

Chọn `ONELEVEL` với base `ou=people` sẽ **không** trả về `uid=lan,ou=staff,ou=people,...` vì entry này nằm ở cấp cháu. Nếu muốn lấy nhân viên trực tiếp dưới `ou=staff`, có thể đặt base là `ou=staff,ou=people` và scope là `ONELEVEL`.

Ngược lại, `SUBTREE` bao gồm cả base entry. Nếu bộ lọc phù hợp với object class của OU, chính entry OU có thể được trả về; đừng giả định subtree chỉ gồm các lá.

## 3. Chọn search base theo ranh giới nghiệp vụ

**Ranh giới dữ liệu** là phạm vi entry mà một chức năng có lý do hợp lệ để truy cập: nhóm nhân viên, đối tác, tài khoản dịch vụ, bộ phận, khách hàng thuê hệ thống hoặc dữ liệu lưu trữ.

Một quy trình chọn base thực tế:

1. **Xác định câu hỏi nghiệp vụ.** Chức năng cần tìm “nhân viên đang làm việc” hay “mọi danh tính trong directory”?
2. **Xác định nhánh chứa các entry cần thiết.** Đọc thiết kế DIT và DN mẫu; không suy nhánh từ tên lớp Java.
3. **Chọn nhánh nhỏ nhất bao phủ tất cả kết quả hợp lệ.** Ví dụ `ou=staff,ou=people` thay cho `dc=example,dc=org`.
4. **Chọn scope nhỏ nhất vẫn đúng.** Nếu nhân viên là con trực tiếp, dùng `ONELEVEL`; nếu có OU con theo bộ phận, dùng `SUBTREE` khi cần bao phủ chúng.
5. **Thêm filter theo objectClass và thuộc tính nghiệp vụ.** Đừng trông đợi base tự loại bỏ mọi loại entry khác cùng nhánh.
6. **Xác minh ACL và các chính sách server.** Search base giới hạn phạm vi truy vấn do ứng dụng gửi; nó không phải biện pháp phân quyền độc lập.
7. **Kiểm thử cả kết quả hợp lệ và dữ liệu ngoài phạm vi.** Truy vấn đúng phải tìm thấy entry ở nhánh được phép và không trả entry ở nhánh bị loại.

### Ví dụ: nhân viên và đối tác có cùng uid

Cây thư mục tồn tại hai DN:

~~~text
uid=lan,ou=staff,ou=people,dc=example,dc=org
uid=lan,ou=partners,ou=people,dc=example,dc=org
~~~

Một bộ lọc `(uid=lan)` chạy từ `ou=people` với `SUBTREE` có thể trả về **hai** entry. Ứng dụng không được giả định `uid` duy nhất trên toàn directory. Nếu chức năng quản trị chỉ quản lý nhân viên, base phải là `ou=staff,ou=people`; nếu cần cả hai loại, thiết kế API cần xử lý rõ nhiều kết quả.

### Khi không có nhánh nhỏ nhất chung phù hợp

Một số directory phân bố nhân viên ở các naming context hoặc backend khác nhau. Không phải cứ chọn base tổ tiên ở mức cao là server có thể tìm xuyên qua mọi naming context. Lúc đó cần truy vấn từng base được cho phép hoặc dùng cơ chế tìm kiếm liên miền do hệ thống LDAP thực sự hỗ trợ (ví dụ referral/global catalog theo directory cụ thể), rồi hợp nhất kết quả theo quy tắc nghiệp vụ.

Đừng đặt base quá rộng chỉ vì muốn gộp nhiều nguồn; phạm vi tìm kiếm hiệu lực còn chịu giới hạn topology, naming context, quyền truy cập và referral.

## 4. Minh họa kết quả bằng sơ đồ

~~~mermaid
flowchart TD
    ROOT["dc=example,dc=org"]
    ROOT --> PEOPLE["ou=people"]
    ROOT --> SERVICES["ou=service-accounts"]
    ROOT --> GROUPS["ou=groups"]
    PEOPLE --> STAFF["ou=staff"]
    PEOPLE --> PARTNERS["ou=partners"]
    STAFF --> LAN1["uid=lan · staff"]
    PARTNERS --> LAN2["uid=lan · partner"]
    STAFF --> BINH["uid=binh"]

    classDef focus fill:#e2f3e8,stroke:#2a8053,color:#17402b
    class STAFF,LAN1,BINH focus
~~~

Trong ví dụ, khi mục tiêu là nhân viên, nhánh được tô nổi bật là `ou=staff` và các entry bên dưới. Mã Java nên biểu diễn quyết định chọn nhánh này rõ ràng để người đọc có thể kiểm tra ngay ranh giới của truy vấn.

## 5. LdapTemplate: chỉ rõ base, scope và filter

`LdapQueryBuilder` trong Spring LDAP cung cấp `base(...)`, `searchScope(...)`, `attributes(...)`, `countLimit(...)` và `timeLimit(...)`. Ví dụ sau tìm common name của nhân viên nằm trực tiếp dưới `ou=staff,ou=people`:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class StaffDirectorySearch {

    private final LdapTemplate ldapTemplate;

    public StaffDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=staff,ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("cn")
                .countLimit(100)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Giả định ví dụ: context base `dc=example,dc=org`; nhân viên là con trực tiếp của `ou=staff,ou=people`; các entry `inetOrgPerson` có `cn` theo schema được áp dụng. Với một entry có nhiều giá trị `cn`, mapper trên chỉ lấy giá trị đầu tiên; nếu nghiệp vụ cần toàn bộ giá trị, hãy ánh xạ thành collection.

Giải thích các tham số:

| Dòng mã | Ý nghĩa |
|---|---|
| `base("ou=staff,ou=people")` | Bắt đầu tìm dưới nhánh nhân viên |
| `searchScope(SearchScope.ONELEVEL)` | Chỉ tìm các entry con trực tiếp |
| `attributes("cn")` | Chỉ yêu cầu trả thuộc tính cần đọc |
| `countLimit(100)` | Đặt giới hạn số entry mà client yêu cầu server trả |
| `timeLimit(2000)` | Đặt giới hạn thời gian tìm kiếm, đơn vị mili giây |
| `where("objectClass").is("inetOrgPerson")` | Chỉ chọn entry thuộc loại người dùng phù hợp |
| `and("uid").is(uid)` | Lọc theo giá trị uid được encode qua API builder |

Một số giới hạn có thể bị directory server áp dụng chặt hơn (size limit, time limit), và `countLimit` không phải cơ chế phân trang để bảo đảm đọc hết mọi kết quả. `timeLimit` của phép tìm kiếm cũng khác timeout thiết lập kết nối mạng.

**An toàn filter:** không tự nối chuỗi `"(uid=" + uid + ")"` từ đầu vào bên ngoài. API builder tạo filter thích hợp và escape giá trị. Giới hạn ranh giới bằng search base và escape filter là **hai yêu cầu độc lập**.

### Tìm trên nhiều cấp trong cùng nhánh

Nếu nhân viên được chia tiếp thành `ou=engineering,ou=staff,...` và `ou=finance,ou=staff,...`, có thể đổi scope thành:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=staff,ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("cn")
        .where("objectClass").is("inetOrgPerson");
~~~

`SUBTREE` bao phủ cả nhân viên ở các OU con, nhưng không mở rộng sang `ou=partners`, vì nhánh `ou=partners` nằm ngoài search base.

### Tìm entry ở DN chính xác

Khi ứng dụng biết chính xác DN của một entry, tìm subtree là không cần thiết. Có thể dùng `lookup` theo DN hoặc `OBJECT` scope:

~~~java
LdapQuery ldapQuery = query()
        .base("uid=lan,ou=staff,ou=people")
        .searchScope(SearchScope.OBJECT)
        .attributes("cn")
        .where("objectClass").is("inetOrgPerson");
~~~

Trong trường hợp này, phạm vi tìm chỉ gồm entry ở DN đích. Nếu chỉ cần đọc entry theo DN mà không cần lọc, `ldapTemplate.lookup(...)` thường biểu diễn ý định trực tiếp hơn.

## 6. Repository và phạm vi của entity

Trong **Spring Data LDAP**, repository thường truy vấn các entity được định nghĩa bằng annotation ODM. Ví dụ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=staff,ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class StaffPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor và accessor được lược bỏ.
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface StaffPersonRepository
        extends LdapRepository<StaffPerson> {

    List<StaffPerson> findByUid(String uid);
}
~~~

Ở đây, `@Entry(base = "ou=staff,ou=people")` khai báo base ánh xạ cho loại entity người dùng nội bộ; `findByUid(...)` tạo điều kiện lọc dựa vào thuộc tính Java `uid`. Cấu hình context base, annotation entity, schema và cây OU thực tế phải nhất quán.

Không nên xem `@Entry(base)` là cơ chế **bảo vệ tenant** thay cho kiểm tra quyền. Một service vẫn có thể dùng `LdapTemplate` hay cấu hình khác để truy vấn phạm vi rộng hơn nếu credential/server cho phép. Với nhiều chức năng có ranh giới dữ liệu khác nhau, hãy xác định rõ repository nào dùng cho mỗi nhánh và kiểm tra mọi đường truy cập LDAP.

### Khi cần chọn base khác nhau theo từng truy vấn

Một repository cố định theo entity giúp code dễ đọc trong mô hình một nhánh, nhưng một ứng dụng có nhiều OU động (như từng tenant) thường cần service tìm kiếm tường minh với `LdapTemplate` hoặc phương thức repository có custom query được kiểm soát.

Spring Data LDAP có `@Query` với các thuộc tính như `base`, `searchScope`, `countLimit`, `timeLimit` và filter được khai báo. Tuy nhiên, với base được lựa chọn theo quyền của từng request, nên thiết kế một lớp service kiểm soát việc chọn DN trước khi gọi truy vấn để tránh rải logic ủy quyền vào nhiều method.

**Lưu ý:** repository có thể áp dụng quy tắc suy diễn truy vấn và phạm vi ODM theo phiên bản đang dùng. Nếu dùng custom `@Query(base = ...)`, cần kiểm thử kết quả thật với `@Entry(base = ...)` và context base để xác nhận phạm vi mong muốn, tránh dựa vào suy đoán về cách ghép các lớp base.

## 7. Chọn base an toàn trong hệ thống nhiều tenant

Giả sử directory chứa:

~~~text
dc=example,dc=org
└── ou=tenants
    ├── ou=tenant-a
    │   ├── ou=people
    │   │   └── uid=lan
    │   └── ou=groups
    └── ou=tenant-b
        ├── ou=people
        │   └── uid=lan
        └── ou=groups
~~~

Ứng dụng chỉ được phép xem người dùng của tenant mà phiên đăng nhập đã được cấp quyền. Cùng một `uid=lan` hoàn toàn có thể xuất hiện trong cả hai tenant.

**Điều cần tránh:** nhận nguyên chuỗi DN của client như:

~~~text
ou=people,ou=tenant-b,ou=tenants
~~~

rồi dùng trực tiếp làm `query().base(requestDn)`. Nếu tài khoản bind có quyền đọc hai tenant, người dùng tenant A có thể tìm được dữ liệu tenant B.

Thay vào đó, ứng dụng phải **ủy quyền tenant trước**, tra tenant đó trong danh sách/registry server tin cậy, sau đó tạo DN từ các thành phần RDN đã được kiểm soát.

Ví dụ service tìm tên người dùng trong một tenant **đã được tầng ủy quyền cho phép**:

~~~java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class TenantPersonSearch {

    private final LdapTemplate ldapTemplate;

    public TenantPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String authorizedTenantOu) {
        // authorizedTenantOu lấy từ policy/registry tin cậy,
        // đã được đối chiếu với danh tính caller; không lấy
        // trực tiếp một DN bất kỳ từ HTTP request.
        Name tenantPeopleBase = LdapNameBuilder
                .newInstance("ou=tenants")
                .add("ou", authorizedTenantOu)
                .add("ou", "people")
                .build();

        LdapQuery ldapQuery = query()
                .base(tenantPeopleBase)
                .searchScope(SearchScope.ONELEVEL)
                .attributes("cn")
                .countLimit(200)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Với `authorizedTenantOu="tenant-a"` và context base `dc=example,dc=org`, DN dùng để tìm sẽ là:

~~~text
ou=people,ou=tenant-a,ou=tenants,dc=example,dc=org
~~~

`LdapNameBuilder` xử lý thành phần RDN theo cú pháp DN, giúp tránh lỗi do nối chuỗi DN không an toàn. **DN được escape đúng vẫn chưa chắc được phép truy cập.** Quyết định caller được tìm tenant nào phải đến từ một policy/registry đáng tin cậy; không cho caller tự chọn tenant khác chỉ vì chuỗi có cú pháp hợp lệ.

Khi cần bảo đảm cách ly tenant mạnh, directory server nên áp dụng ACL/service account hoặc phân vùng/instance phù hợp với yêu cầu. Base của truy vấn chỉ giúp ứng dụng hạn chế vùng tìm kiếm trong hoạt động thông thường; nó không thay thế cơ chế phân quyền tại server.

## 8. Search base và mô hình phân quyền

Có ba lớp bảo vệ thường cần kết hợp:

| Lớp | Cơ chế | Kiểm soát điều gì? |
|---|---|---|
| **Ứng dụng** | Chọn base từ policy, kiểm tra tenant/role, giới hạn scope | Chức năng gửi truy vấn vào nhánh nào |
| **Directory server** | ACL, phạm vi quyền của bind account, chính sách search | Dữ liệu nào thực sự được trả và thao tác nào được phép |
| **Kết nối/hạ tầng** | LDAPS/StartTLS, network policy, tách credential | Ai có thể kết nối và bảo mật dữ liệu trên đường truyền |

Ví dụ, một dịch vụ chỉ đọc nhóm ở `ou=groups` có thể sử dụng credential riêng chỉ được phép đọc nhánh này. Dù code có lỗi mở rộng search base sang `ou=people`, ACL giúp hạn chế tác động. Ngược lại, nếu ứng dụng dùng tài khoản quản trị rộng quyền, việc chọn search base chính xác trong một phương thức vẫn không ngăn được sai sót ở phương thức khác.

**Không đánh đồng “không có kết quả” với “không tồn tại”.** Directory server có thể ẩn entry hoặc thuộc tính do ACL. Một truy vấn sai base cũng có thể trả rỗng; một số server trả lỗi khi base không tồn tại. Cần ghi nhận và phân biệt kết quả rỗng, quyền hạn và lỗi `noSuchObject` trong quá trình chẩn đoán.

### Search base không giới hạn quyền ghi

`query().base("ou=staff,ou=people")` chỉ áp dụng cho **phép tìm kiếm cụ thể**. Nó không ngăn service gọi `ldapTemplate.bind(...)`, `unbind(...)` hay `rename(...)` trên DN khác nếu credential có quyền. Khi xử lý CRUD, mỗi thao tác phải xác định và xác minh DN đích theo quy tắc riêng, cùng ACL tại server.

## 9. Tối ưu hiệu năng bằng base và scope hợp lý

Đặt base hẹp thường giúp server hạn chế số entry phải xem xét và giúp truy vấn dễ dự đoán hơn. Nhưng hiệu quả cụ thể còn phụ thuộc vào chỉ mục, khả năng tối ưu của directory server, độ phức tạp filter, số entry dưới nhánh và giới hạn tài nguyên.

| Tình huống | Lựa chọn hợp lý |
|---|---|
| Tìm một entry biết DN | `lookup` hoặc `OBJECT` scope |
| Liệt kê nhân viên trực tiếp dưới một OU | Base OU đó + `ONELEVEL` |
| Tìm mọi nhân viên ở nhiều OU bộ phận con | Base OU cấp trên phù hợp + `SUBTREE` |
| Tìm user theo UID trong một tenant | Base tenant đã ủy quyền + scope theo cấu trúc tenant |
| Tìm nhóm trong OU riêng | Base `ou=groups`, filter theo object class của nhóm |
| Báo cáo hợp nhất từ nhiều nhánh độc lập | Các truy vấn riêng trên base cho phép, rồi hợp nhất ở ứng dụng |

Bên cạnh base/scope:

- Chỉ yêu cầu thuộc tính cần dùng với `attributes(...)`, tránh lấy giá trị nhạy cảm không cần thiết.
- Giới hạn số kết quả và thời gian hợp lý với `countLimit(...)`, `timeLimit(...)`; kiểm tra thêm size/time limit của server.
- Với kết quả lớn, nghiên cứu **LDAP Simple Paged Results** hoặc cơ chế phân trang phù hợp mà server và Spring LDAP hỗ trợ. Không coi count limit là phân trang hoàn chỉnh.
- Theo dõi latency, tỉ lệ timeout và số kết quả; dùng log tránh ghi toàn bộ DN cá nhân hoặc thuộc tính bí mật.
- Nếu cần filter thường xuyên theo `uid`, `mail` hay `member`, phối hợp quản trị directory để đánh giá index thực tế.

Mặc dù `SUBTREE` có thể là scope mặc định trong nhiều cấu hình `LdapTemplate`, một phương thức nhạy cảm về ranh giới dữ liệu nên **chỉ định scope tường minh** để người review hiểu rõ mức độ bao phủ.

## 10. Lỗi phổ biến khi chọn search base

### Lỗi 1: Dùng DN tuyệt đối trong bối cảnh đã có context base

~~~yaml
spring:
  ldap:
    base: dc=example,dc=org
~~~

~~~java
// Sai nếu cố ý tìm dưới context base đã cấu hình:
query().base("ou=staff,ou=people,dc=example,dc=org");
~~~

Cần sử dụng:

~~~java
query().base("ou=staff,ou=people");
~~~

Nếu kết quả rỗng bất thường, kiểm tra DN hiệu lực (base context + base query), cách thư viện/provider xử lý DN và entry có thật trong cây.

### Lỗi 2: Tìm từ gốc vì “filter đã đủ chính xác”

~~~java
query()
    .base("")
    .searchScope(SearchScope.SUBTREE)
    .where("uid").is(uid);
~~~

Trong cây có nhiều nhánh, cách này có thể tìm thấy nhiều entry khớp UID hoặc dữ liệu ngoài chức năng. Chọn base đúng trước, rồi mới thêm filter.

### Lỗi 3: Chọn ONELEVEL trong khi entry nằm ở OU con

Với `ou=staff` chứa các nhánh `ou=engineering` và `ou=finance`, `ONELEVEL` chỉ bao phủ các OU con trực tiếp, không tới các user bên trong. Chuyển sang `SUBTREE` **khi đúng với ranh giới nghiệp vụ**, hoặc tìm trong OU cụ thể hơn.

### Lỗi 4: Lấy search base trực tiếp từ request

~~~java
// Không nhận DN tùy ý từ client làm ranh giới tìm kiếm:
query().base(userSuppliedDn);
~~~

Giải pháp: ánh xạ role/tenant đã xác thực sang base từ danh sách cho phép tại server ứng dụng và kiểm tra quyền tại directory server.

### Lỗi 5: Nhầm filter escaping với DN escaping

- **Filter:** các ký tự như `*`, `(`, `)`, `\` cần được xử lý theo cú pháp filter LDAP; dùng `LdapQueryBuilder` hoặc API filter tương ứng.
- **DN/RDN:** các ký tự như dấu phẩy, dấu bằng, dấu cộng hoặc dấu cách ở vị trí đặc biệt cần được xử lý theo cú pháp DN; dùng `LdapNameBuilder` hoặc `LdapName`.

Hai kiểu escaping khác nhau. Dùng đúng API cho mỗi ngữ cảnh và vẫn phải kiểm tra quyền của caller trước khi chọn base.

### Lỗi 6: Bỏ qua naming context và referral

LDAP server có thể chia dữ liệu theo nhiều naming context hoặc trỏ tới server khác bằng referral. Truy vấn subtree từ một DN “trông giống cha” không bảo đảm tìm xuyên mọi vùng dữ liệu. Cần hiểu topology và chính sách referral; không tự bật follow referral khi chưa xác minh bảo mật và quyền truy cập.

### Lỗi 7: Dùng ranh giới tìm kiếm thay cho phân quyền

Ngay cả khi mọi truy vấn bình thường sử dụng base hẹp, server vẫn phải thực thi ACL. Khi credential được cấp quyền quá rộng, một lỗi chọn base hoặc API mới có thể khiến dữ liệu nhạy cảm bị truy xuất.

## 11. Chẩn đoán search base bằng ldapsearch

Khi chưa biết lỗi nằm ở base, scope, filter hay quyền, hãy tái hiện bằng `ldapsearch` với **cùng bind identity**, server và phạm vi tương ứng. Ví dụ dùng LDAPS và yêu cầu nhập mật khẩu tương tác:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-app,ou=service-accounts,dc=example,dc=org" \
  -W \
  -b "ou=staff,ou=people,dc=example,dc=org" \
  -s one \
  "(objectClass=inetOrgPerson)" dn cn uid
~~~

Trong lệnh này:

| Tham số | Tác dụng |
|---|---|
| `-H` | Chọn LDAP URL |
| `-D` | Bind DN của tài khoản được phép dùng |
| `-W` | Nhập mật khẩu không đưa thẳng vào command line |
| `-b` | Search base **tuyệt đối** truyền tới `ldapsearch` |
| `-s one` | Scope một cấp; `base` cho OBJECT, `sub` cho SUBTREE |
| `"(objectClass=inetOrgPerson)"` | Filter |
| `dn cn uid` | Các thuộc tính yêu cầu trả về (DN hiển thị riêng) |

Khác với `LdapTemplate` khi đã cấu hình context base, công cụ `ldapsearch` trong ví dụ nhận trực tiếp DN tuyệt đối ở `-b`. Cần quy đổi phạm vi cho đúng trước khi so sánh kết quả.

Có thể chạy cùng filter với `-s sub` để xác định có user nằm dưới OU con hay không, hoặc thay `-b` thành nhánh khác đã được cấp phép. Nếu một truy vấn trả rỗng, kiểm tra lần lượt entry gốc có tồn tại, quyền đọc, scope và filter. Không sử dụng tài khoản quản trị để kết luận tài khoản ứng dụng chắc chắn có cùng quyền đọc.

## 12. Kiểm thử tích hợp ranh giới tìm kiếm

Một test directory hữu ích cần chứa **dữ liệu có thể gây nhầm lẫn**, không chỉ một entry khớp. Ví dụ fixture:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=staff,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: staff

dn: ou=partners,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: partners

dn: uid=lan,ou=staff,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lan Staff
sn: Lan
uid: lan

dn: uid=lan,ou=partners,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lan Partner
sn: Lan
uid: lan
~~~

Chú ý: LDIF trên là fixture của một directory test độc lập; parent `dc=example,dc=org` cũng phải được tạo trước nếu chưa tồn tại. Dùng schema server hỗ trợ `organizationalUnit` và `inetOrgPerson`.

Kiểm thử có ý nghĩa:

| Kịch bản | Đầu vào | Kỳ vọng |
|---|---|---|
| Tìm nhân viên `lan` | Base `ou=staff,ou=people`, ONELEVEL, `uid=lan` | Chỉ entry `Lan Staff` |
| Tìm đối tác `lan` | Base `ou=partners,ou=people`, ONELEVEL | Chỉ entry `Lan Partner` |
| Tìm từ `ou=people` | SUBTREE, `uid=lan` | Có thể có cả hai entry, cho thấy UID không duy nhất toàn cây |
| Sai scope | Base `ou=people`, ONELEVEL, `uid=lan` | Không tìm thấy hai entry nằm dưới OU con |
| Sai base | Base `ou=missing,ou=people` | Server báo lỗi thích hợp hoặc ứng dụng xử lý theo cấu hình; không đánh đồng với 0 match |
| Đầu vào filter đặc biệt | UID chứa `*` hoặc dấu ngoặc | API builder escape, không mở rộng thành filter tùy ý |
| Tenant vượt quyền | Tenant A yêu cầu xem tenant B | Bị ứng dụng từ chối trước khi gọi LDAP; ACL server ngăn nếu bỏ sót |
| Sai quyền bind | Tài khoản chỉ được đọc staff tìm partners | Không nhận dữ liệu partners; xem thông điệp và chính sách server |

Một bài kiểm thử tốt phải **assert cả tập entry trả về và DN của chúng**, vì hai entry khác nhau có thể có cùng `uid` hoặc `cn`. Việc chỉ assert “có kết quả” có thể bỏ sót lỗi lấy sai nhánh.

### Ví dụ kiểm thử chức năng search

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class StaffDirectorySearchIntegrationTest {

    @Autowired
    private StaffDirectorySearch search;

    @Test
    void doesNotReturnPartnerWithSameUid() {
        List<String> names = search.findNamesByUid("lan");

        assertEquals(List.of("Lan Staff"), names);
    }
}
~~~

Ví dụ giả định fixture đã được nạp, service `StaffDirectorySearch` đã đăng ký thành Spring bean (qua `@Service` hoặc cấu hình `@Bean`), directory test hỗ trợ schema và base DN tương ứng. Đây là test tích hợp **chỉ có giá trị khi thực sự kết nối LDAP test**, không chỉ khởi tạo `ApplicationContext`.

Trong production, không kiểm thử các thao tác ghi/xóa bằng tài khoản và dữ liệu thật. Dùng LDAP test riêng với cấu trúc tương đương; có thể bổ sung smoke test chỉ đọc trên nhánh không nhạy cảm được cấp phép.

## 13. Checklist để review một phép tìm kiếm LDAP

Trước khi chấp nhận thay đổi code hoặc triển khai một endpoint tìm kiếm, hãy trả lời:

- **Dữ liệu:** Nhánh nào chứa tất cả entry hợp lệ? Có OU/tenant nào tuyệt đối không được quét?
- **Context base:** `spring.ldap.base` hiện là DN nào? `query().base(...)` đang nhận DN tương đối hay được cố ý cấu hình toàn phần?
- **Scope:** OBJECT, ONELEVEL hay SUBTREE? Scope có bao phủ đúng chiều sâu của DIT?
- **Filter:** Có lọc đúng objectClass và thuộc tính theo schema? Giá trị bên ngoài đã được escape?
- **Ủy quyền:** Ai quyết định base? Có lấy DN hoặc tenant trực tiếp từ input chưa kiểm tra?
- **ACL:** Credential LDAP có đúng phạm vi quyền; server có ngăn truy cập các nhánh ngoài quyền?
- **Hiệu năng:** Có giới hạn thuộc tính, số lượng, thời gian và cơ chế xử lý kết quả lớn?
- **Kiểm thử:** Có fixture trùng UID ở hai nhánh; có kiểm thử dữ liệu ngoài phạm vi và search base không tồn tại?
- **Triển khai:** Base DN, naming context và cấu trúc OU của dev/test/prod có được xác minh?

Khi một kết quả sai xuất hiện, kiểm tra theo thứ tự: **context base → search base → scope → filter → ACL → schema và dữ liệu**. Thứ tự này giúp tránh sửa filter khi thực chất đang tìm trong nhánh khác.

## 14. Bài tập thực hành

**Bối cảnh:** một ứng dụng Spring Data LDAP quản lý nhân viên và đối tác. Hai nhánh có `uid` trùng nhau. Service cần cung cấp hai phương thức: tìm nhân viên và tìm đối tác. Một màn hình quản trị cấp cao có thể xem cả hai loại nếu được cấp quyền.

Hãy thực hiện:

1. Dựng LDAP test với cây `ou=people` gồm `ou=staff` và `ou=partners`; nạp hai entry có cùng `uid` nhưng DN khác nhau.
2. Cấu hình `spring.ldap.base=dc=example,dc=org` và kết nối qua `LdapTemplate`.
3. Tạo hai truy vấn dùng cùng filter `uid=lan` nhưng search base tương ứng từng nhánh.
4. So sánh `ONELEVEL` và `SUBTREE` khi thêm một `ou=engineering` nằm dưới staff.
5. Thử lệnh tìm kiếm từ `ou=people` với SUBTREE; giải thích vì sao hai entry cùng UID đều xuất hiện.
6. Thực hiện kiểm thử chứng minh user chỉ được phép xem staff không thể chọn base partners qua API.
7. Giới hạn các thuộc tính trả về thành `cn` và `uid`; thêm count/time limit và so sánh log/thời gian trước sau trên dữ liệu test lớn.
8. Ghi lại chính sách ACL tương ứng để directory server cũng thực thi ranh giới nếu code ứng dụng có lỗi.

**Tiêu chí hoàn thành:** truy vấn trả đúng entry theo nhánh và scope, dữ liệu ngoài ranh giới không lọt vào kết quả, không có filter/DN ghép trực tiếp từ chuỗi người dùng và các trường hợp lỗi được xử lý rõ ràng.

## 15. Ghi nhớ và nguồn tham khảo

**Search base trả lời “tìm bắt đầu ở nhánh nào”; search scope trả lời “tìm sâu tới đâu”; filter trả lời “entry nào khớp”; ACL trả lời “client được phép xem gì”.** Thiết kế một truy vấn Spring Data LDAP đúng phải phối hợp cả bốn yếu tố, đồng thời hiểu rõ base DN của `ContextSource`.

Các tài liệu kỹ thuật nên tham khảo theo phiên bản thư viện đang dùng:

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `base`, `searchScope`, `attributes`, `countLimit`, `timeLimit` và filter.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): phương thức `LdapQueryBuilder`.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): base DN của `ContextSource` và cấu hình `LdapTemplate`.
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): repository query, tham số và escaping.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, baseObject, scope và kết quả tìm kiếm.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn DN và escaping.
