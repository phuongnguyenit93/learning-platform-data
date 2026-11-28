# Naming context, suffix và gốc của một miền thư mục

Trong **Spring Data LDAP**, một lời gọi `LdapRepository` hoặc `LdapTemplate` chỉ trả kết quả đúng khi ứng dụng biết **đang tìm ở nhánh nào của cây thư mục**. Hai hệ thống cùng chứa entry `uid=u1001` có thể trả kết quả khác nhau vì sử dụng những **naming context**, **suffix** hoặc **base DN** khác nhau. Việc cấu hình sai gốc tìm kiếm là một trong những nguyên nhân phổ biến khiến ứng dụng báo “không tìm thấy tài khoản” dù entry thực sự tồn tại.

Bài thuộc chương **Mô hình thư mục** này giải thích naming context, suffix và gốc của một miền thư mục trong LDAP; phân biệt chúng với RootDSE, tên miền DNS, OU và search base. Từ đó, người học có thể chọn DN phù hợp khi ánh xạ entry phân cấp sang đối tượng Java, truy vấn bằng repository/`LdapTemplate`, thực hiện CRUD đúng phạm vi, áp dụng LDAP filter an toàn, cấu hình kết nối bảo mật và kiểm thử với directory thực tế.

## 1. Nhìn một directory như cây các tên phân biệt

LDAP tổ chức entry thành **Directory Information Tree (DIT)**. Mỗi entry được nhận diện bằng **Distinguished Name (DN)**, ghép từ các **Relative Distinguished Name (RDN)** theo đường đi tới gốc đặt tên.

Ví dụ về cây thư mục của tổ chức:

```text
             (gốc logic của DIT)
                     │
          dc=example,dc=org               ← naming context root / suffix
              ├── ou=people
              │     ├── uid=u1001
              │     └── uid=u1002
              └── ou=groups
                    └── cn=developers
```

DN của người dùng `u1001` là:

```text
uid=u1001,ou=people,dc=example,dc=org
```

Các thành phần cần tách bạch:

- **RDN** `uid=u1001` đặt tên entry tương đối với entry cha.
- **DN của cha** `ou=people,dc=example,dc=org` xác định nơi chứa entry.
- **DN đầy đủ** `uid=u1001,ou=people,dc=example,dc=org` xác định entry theo vị trí hiện tại trong cây.
- **Gốc của miền dữ liệu đang xét** `dc=example,dc=org` là entry ở đầu cây con mà server quản lý cho naming context trong ví dụ.

Một directory có thể phục vụ **nhiều cây con độc lập**, vì vậy sơ đồ trên chưa chứng minh `dc=example,dc=org` là gốc duy nhất của mọi thông tin mà máy chủ LDAP cung cấp.

### Entry ví dụ ở mỗi tầng

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

LDIF chỉ minh họa các entry liên quan, giả định schema directory có các object class đó. Các trường `objectClass`, `dc`, `ou`, `cn`, `sn` và `uid` có quy tắc bắt buộc/được phép theo schema; bạn không thể tạo entry bằng một DN hợp lệ nhưng bỏ qua schema hoặc quyền ghi của server.

## 2. Naming context là gì?

**Naming context (NC)** là một **cây con có tên gốc xác định** mà một dịch vụ thư mục quản lý, lưu trữ hoặc công bố là một đơn vị đặt tên. Naming context thường gắn với ranh giới lưu trữ, định tuyến yêu cầu, nhân bản hoặc quyền quản trị, tùy sản phẩm LDAP.

Ví dụ, một server có thể phục vụ:

```text
dc=example,dc=org            ← NC A
dc=partners,dc=example,dc=org ← NC B nếu được cấu hình là NC riêng
```

NC B có DN trông như nằm dưới NC A, nhưng nếu là **phân vùng quản lý độc lập**, không nên mặc nhiên cho rằng một thao tác subtree search ở NC A sẽ đi xuyên qua NC B. Cách xử lý referral, subordinate database và phạm vi truy vấn phụ thuộc vào LDAP server/cấu hình cụ thể.

Trong một hệ thống khác, các NC có thể hoàn toàn không cùng hậu tố:

```text
dc=example,dc=org
o=contractors
```

Do đó, **naming context không bắt buộc bắt đầu bằng `dc=`** và không bắt buộc ánh xạ một-một với tên miền DNS.

Một NC trả lời câu hỏi: **“Máy chủ này có trách nhiệm cung cấp dữ liệu dưới gốc tên nào?”** Nếu client gửi DN nằm ngoài các vùng server có thể phục vụ, server có thể báo không có đối tượng, cung cấp referral, hoặc từ chối tùy triển khai và chính sách.

### Root của naming context có phải entry thật không?

Trong mô hình LDAP thường gặp, DN của NC root cũng biểu diễn một entry thật (ví dụ `dc=example,dc=org`) mà người dùng có thể tìm hoặc đọc nếu có quyền. Tuy nhiên việc server **công bố NC** và việc dữ liệu entry được **provision** theo schema là hai vấn đề khác nhau. Một số server có bootstrap tự tạo gốc, một số môi trường cần tạo entry gốc hợp lệ. Đừng dựa vào việc thấy `namingContexts` để suy ra mọi thuộc tính của root entry đã tồn tại hoặc có thể đọc.

## 3. Suffix là gì và liên hệ thế nào với naming context?

**Suffix** trong nhiều LDAP server là **DN gốc được cấu hình cho một database/backend hoặc vùng directory được phục vụ**. Trong nhiều tài liệu vận hành OpenLDAP, `suffix` chính là hậu tố DN của các entry dưới database đó, và thường tương ứng với root của naming context.

Ví dụ mô tả cấu hình (chỉ để minh họa ý nghĩa, không phải tệp cấu hình đầy đủ):

```text
OpenLDAP backend X:
    suffix = dc=example,dc=org

Entry trong backend X:
    uid=u1001,ou=people,dc=example,dc=org
    cn=developers,ou=groups,dc=example,dc=org
```

Để biết một entry thuộc suffix nào, xem **phần kết thúc DN**, không chỉ thành phần đầu tiên:

| DN | Thuộc suffix `dc=example,dc=org`? | Giải thích |
|---|---|---|
| `dc=example,dc=org` | Có | Chính entry gốc |
| `ou=people,dc=example,dc=org` | Có | Nằm dưới gốc |
| `uid=u1001,ou=people,dc=example,dc=org` | Có | Có hậu tố DN đúng ranh giới RDN |
| `dc=another,dc=org` | Không | Cây tên khác |
| `dc=notexample,dc=org` | Không | Không phải cùng RDN `dc=example` |

Việc xác định “nằm dưới” phải so sánh **các thành phần DN theo cú pháp LDAP**, không chỉ dùng `String.endsWith(...)`. DN có escaping, nhiều cách biểu diễn và quy tắc chuẩn hóa riêng; sử dụng đối tượng `javax.naming.ldap.LdapName`/`Name` khi cần thao tác với DN trong Java.

### Naming context và suffix có luôn đồng nghĩa?

Trong bài học nhập môn, có thể xem **suffix là tên DN gốc được cấu hình** và **NC là phạm vi directory tương ứng**, nên hai thuật ngữ thường xuất hiện cạnh nhau. Tuy nhiên, cách gọi phụ thuộc sản phẩm:

- **OpenLDAP** thường nói tới `olcSuffix` hoặc database suffix.
- **389 Directory Server** dùng thuật ngữ suffix gắn với backend/database.
- **Active Directory Domain Services (AD DS)** thường dùng thuật ngữ **naming context/partition** (domain, configuration, schema, application), không mô tả toàn hệ thống bằng một suffix duy nhất.

Vì vậy, không nên lấy cách đặt tên của một server áp dụng máy móc cho sản phẩm LDAP khác. Khi làm việc với Spring Data LDAP, điều có thể kiểm tra trực tiếp nhất là **NC nào được server phục vụ, DN của entry là gì và base DN mà client đang sử dụng**.

## 4. Gốc của miền thư mục khác RootDSE như thế nào?

Thuật ngữ “gốc” dễ gây nhầm vì có **ít nhất ba khái niệm**:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Gốc logic của DIT | DN rỗng `""` | Điểm gốc của toàn namespace LDAP |
| **RootDSE** | Entry đặc biệt truy cập tại DN rỗng | Công bố metadata và capability của directory server |
| Gốc naming context / suffix | `dc=example,dc=org` | Gốc dữ liệu của một miền/partition cụ thể |

**RootDSE không phải entry `dc=example,dc=org`**. RootDSE là đối tượng đặc biệt ở DN rỗng, thường cho biết server công bố những naming context nào. Nó không phải OU, không phải một user và không phải gốc schema của domain mà ứng dụng tự tạo.

Hãy phân biệt rõ hai thao tác:

```text
Base DN = ""                         → đọc RootDSE (base-object scope)
Base DN = "dc=example,dc=org"        → đọc/search dưới naming context đó
```

RootDSE không nhất thiết liệt kê tất cả phần dữ liệu mà một client có quyền xem; kết quả còn phụ thuộc sản phẩm, máy chủ đích, chính sách và trạng thái kết nối. Trong một số hệ thống, truy vấn RootDSE có thể thực hiện trước khi xác thực, nhưng không nên dựa vào điều này cho mọi directory.

## 5. Khám phá naming context từ RootDSE

Trước khi cấu hình Spring Data LDAP cho một directory lạ, nên hỏi server về naming context đang được công bố, rồi xác minh cùng đội quản trị.

Ví dụ dùng công cụ dòng lệnh `ldapsearch` qua LDAPS (giá trị host và tài khoản là minh họa):

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=readonly,ou=service-accounts,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" \
  namingContexts supportedLDAPVersion supportedControl
```

Các thành phần chính:

- `-b ""`: đặt base DN rỗng để đọc RootDSE.
- `-s base`: chỉ đọc entry tại đúng DN đó, không tìm kiếm toàn cây.
- `namingContexts`: thuộc tính RootDSE công bố các naming context mà server cung cấp.
- `-H ldaps://...`: kết nối qua TLS; cần cấu hình tin cậy chứng chỉ CA hợp lệ cho client.

Output **minh họa**, thay đổi theo sản phẩm và cấu hình:

```ldif
dn:
namingContexts: dc=example,dc=org
namingContexts: o=partners
supportedLDAPVersion: 3
```

Một số thuộc tính có thể không hiện nếu server không hỗ trợ, không công bố hoặc chính sách truy cập hạn chế. Để xác nhận một suffix thực sự chứa dữ liệu mà ứng dụng cần, hãy **search có giới hạn** dưới suffix đó bằng tài khoản bind dự kiến sử dụng.

### Trường hợp Active Directory

AD DS thường công bố thêm các thuộc tính RootDSE như:

```text
defaultNamingContext
rootDomainNamingContext
configurationNamingContext
schemaNamingContext
```

Ví dụ một domain AD `corp.example.com` có thể có:

```text
defaultNamingContext: DC=corp,DC=example,DC=com
configurationNamingContext: CN=Configuration,DC=corp,DC=example,DC=com
schemaNamingContext: CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com
```

Đó là các **NC khác nhau**, không phải các OU tùy ý nằm trong domain NC. AD có thể có nhiều domain NC trong forest, application NC và dịch vụ **Global Catalog** với hành vi/thuộc tính được phục vụ khác một domain controller thông thường. Khi cần dữ liệu ở domain khác, phải kiểm chứng đúng DC/GC, base và phạm vi tìm kiếm; một subtree search ở domain NC hiện tại không bảo đảm tự đi qua các NC của domain khác.

**Chú ý khi dùng Spring LDAP:** nếu `LdapContextSource` đã đặt base `dc=example,dc=org`, thì `ldapTemplate.lookup("")` trên context đó thường tham chiếu **entry tại base đã cấu hình**, không phải RootDSE. Hãy sử dụng client/context **không có base DN** nếu muốn truy cập DN rỗng thực sự để lấy RootDSE.

## 6. So sánh suffix, LDAP base, search base và OU

Trong ứng dụng Java, bốn giá trị này có mục đích riêng:

| Thành phần | Ai định nghĩa? | Ví dụ | Tác dụng |
|---|---|---|---|
| Suffix / NC root | Cấu hình/dịch vụ LDAP | `dc=example,dc=org` | Ranh giới cây dữ liệu server phục vụ |
| LDAP context base | Cấu hình client `LdapContextSource` | `dc=example,dc=org` | Base mặc định của các thao tác Spring LDAP |
| Search base | Từng truy vấn | `ou=people` (tương đối với context base) | Chỉ nhánh bắt đầu tìm kiếm |
| OU | Entry trong DIT | `ou=people,dc=example,dc=org` | Một loại container trong cây |

Hai cấu hình ứng dụng đều hợp lý nếu được dùng nhất quán:

**Cấu hình A: context base ở suffix**

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=readonly,ou=service-accounts,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
```

Trong cấu hình A:

```text
Context base:          dc=example,dc=org
Search base truyền vào: ou=people
DN lookup truyền vào:   uid=u1001,ou=people
DN đầy đủ trên server:  uid=u1001,ou=people,dc=example,dc=org
```

**Cấu hình B: context base ngay tại nhánh người dùng**

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: ou=people,dc=example,dc=org
    username: cn=readonly,ou=service-accounts,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
```

Trong cấu hình B, DN tương đối để lookup cùng người dùng là `uid=u1001`; tìm ngay dưới base có thể dùng search base rỗng. Nhánh `ou=groups` không còn thuộc subtree của context base này, do đó nếu cũng cần đọc groups, phải thiết kế lại vùng truy cập hoặc dùng context/đường đi phù hợp.

**Sai lầm phổ biến:** context đã có `dc=example,dc=org` nhưng mỗi truy vấn lại truyền DN đầy đủ kết thúc bằng cùng hậu tố đó, tạo đường đi bị lặp hoặc sai vị trí. Ngược lại, chỉ gửi `uid=u1001` trong cấu hình A cũng sai vì thiếu `ou=people`.

## 7. Tra cứu đúng cây bằng Spring Data LDAP và LdapTemplate

Ví dụ sau dùng `LdapTemplate` tìm người theo `uid` trong OU `people`. Giả định context base đã cấu hình `dc=example,dc=org` như cấu hình A.

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record DirectoryUser(String uid, String commonName) {}

@Service
public class DirectoryUserReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryUserReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryUser> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        LdapQuery ldapQuery = query()
            .base("ou=people")
            .where("uid").is(uid);

        AttributesMapper<DirectoryUser> mapper = attrs ->
            new DirectoryUser(
                (String) attrs.get("uid").get(),
                (String) attrs.get("cn").get());

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Giải thích:

1. `base("ou=people")` chọn nhánh **tương đối với base DN của context**.
2. `.where("uid").is(uid)` xây LDAP filter; cách này giúp escape giá trị filter thay vì nối `"(uid=" + uid + ")"` từ dữ liệu bên ngoài.
3. Kết quả là danh sách vì `uid` không nhất thiết duy nhất trên phạm vi mọi subtree hoặc nhiều suffix. Với nghiệp vụ yêu cầu một người duy nhất, kiểm tra trường hợp **0, 1, nhiều** entry.
4. `attrs.get(...).get()` là cách đọc tối giản, giả định những thuộc tính đã có và là kiểu chuỗi. Trong ứng dụng thật phải xử lý thuộc tính tùy chọn, kiểu binary, thuộc tính đa trị và ACL.

Nếu đã biết **DN hiện tại** của entry, không cần search theo thuộc tính:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "u1001")
    .build();

AttributesMapper<String> nameMapper = attrs ->
    (String) attrs.get("cn").get();

String cn = ldapTemplate.lookup(relativeDn, nameMapper);
```

`LdapNameBuilder` tạo RDN đúng cú pháp và escape ký tự đặc biệt trong giá trị. **LDAP DN escaping khác LDAP filter escaping**. Việc một entry có DN hiện tại không bảo đảm DN đó sẽ không đổi khi entry bị rename hoặc move sang OU khác.

### Repository và ODM dùng base ra sao?

Spring Data LDAP ánh xạ entry sang Java object thông qua **Object–Directory Mapping (ODM)**. Ví dụ:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }
}
```

`@Entry(base = "ou=people")` nói tới vùng entry trong mapping ODM; `@Id` giữ DN theo `javax.naming.Name`. Nếu ánh xạ `DirectoryPerson` bằng `LdapRepository<DirectoryPerson>`, cần thống nhất **context base**, **base trên annotation** và DN mà mapper hoặc repository sử dụng. `@Entry` không tạo NC mới và không cấp quyền đọc vùng nằm ngoài suffix mà server phục vụ.

Khi tạo/sửa/xóa LDAP entry, DN mới phải thuộc naming context hợp lệ và entry phải đáp ứng **schema**, `objectClass`, thuộc tính bắt buộc cũng như ACL. Không được mặc định `repository.save()` có thể di chuyển entry giữa hai suffix hoặc tự xử lý đổi DN.

## 8. Cùng một UID nhưng khác naming context

Giả sử directory có hai suffix:

```text
dc=example,dc=org
    └── ou=people
          └── uid=u1001

o=partners
    └── ou=people
          └── uid=u1001
```

Hai DN:

```text
uid=u1001,ou=people,dc=example,dc=org
uid=u1001,ou=people,o=partners
```

đều có giá trị `uid=u1001`, nhưng là **hai entry khác nhau**. Vì vậy:

- Không xem `uid` hoặc `cn` là khóa duy nhất toàn cục nếu chưa có ràng buộc rõ ở toàn hệ thống.
- Không cấu hình một `spring.ldap.base` rồi mặc định mọi tenant/đơn vị đều nằm dưới đó.
- Với nhiều suffix, thiết kế cách **chọn directory/context** từ thông tin đáng tin cậy của ứng dụng, không cho client tùy ý nhập base DN để truy cập mọi nhánh.
- Nếu cần gộp dữ liệu từ nhiều NC, thu thập kết quả theo đúng từng phạm vi được cấp quyền, xử lý trùng định danh và khác biệt schema.

Trong Active Directory, mỗi domain có thể có một **domain naming context** riêng. Global Catalog có thể hỗ trợ tìm qua các domain trong cùng forest với bộ thuộc tính được cung cấp một phần; không nên coi một search ở domain NC hiện tại là tự động bao phủ toàn forest.

## 9. Suffix, search scope và giới hạn của kết quả

**Base DN** xác định nơi bắt đầu tìm; **scope** xác định độ sâu được phép tìm bên dưới base. Trong LDAP:

| Scope | Ý nghĩa | Ví dụ khi base là `ou=people,dc=example,dc=org` |
|---|---|---|
| **BASE / OBJECT** | Chỉ entry tại base | Đọc chính entry `ou=people` |
| **ONELEVEL** | Các entry con trực tiếp của base | Tìm `uid=u1001` nằm ngay dưới `ou=people` |
| **SUBTREE** | Base và mọi entry con trong nhánh | Tìm cả entry nằm trong OU con dưới `ou=people` |

Một search có thể trả **0 kết quả** vì dùng `ONELEVEL` trong khi entry nằm ở OU con, dùng base quá hẹp, filter không khớp, ACL giới hạn hoặc kết quả bị server hạn chế. **0 kết quả không đủ chứng minh entry không tồn tại ở toàn directory.**

Mở rộng scope tới `SUBTREE` không bảo đảm đi qua các **naming context khác**. Một số server trả referral khi truy vấn tới phân vùng khác; việc theo referral và chuyển kết nối phải được thiết kế/kiểm chứng rõ, kể cả hostname, TLS, quyền bind và timeout. Không bật follow referral tùy tiện chỉ để “tìm cho ra dữ liệu”.

Tìm kiếm đúng phạm vi còn ảnh hưởng hiệu năng: base quá rộng, search scope sâu, bộ lọc thiếu index hoặc truy vấn nhiều suffix có thể làm tăng tải directory. Hãy đo độ trễ, số LDAP operations và số entry thực trả về trước khi thay đổi cấu hình để tối ưu.

## 10. Chẩn đoán khi gốc thư mục hoặc suffix bị cấu hình sai

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách đối chiếu |
|---|---|---|
| Lookup trả `NameNotFoundException` | DN tương đối sai; base bị thêm hai lần; entry đã chuyển OU | So sánh DN đầy đủ với context base và vị trí hiện tại |
| Search trả danh sách rỗng | Base/scope quá hẹp, filter sai, tài khoản không có quyền | Dùng truy vấn test có cùng bind account và scope cụ thể |
| Search lỗi `No such object` / LDAP result code 32 | Base DN không tồn tại, không được phục vụ hoặc tên sai | Đọc RootDSE, kiểm tra entry base và suffix phù hợp |
| Đọc được user nhưng không đọc được groups | Context base chỉ tới `ou=people` | Kiểm tra groups nằm ở nhánh ngang hay NC khác |
| Chỉ tìm được user của một domain | Ứng dụng đang dùng domain NC của một DC | Kiểm tra domain đúng và kiến trúc DC/GC/referral |
| Entry cùng UID bị gộp sai | Dùng `uid` thay vì định danh ổn định có phạm vi xác định | Ghép định danh với nguồn/NC phù hợp, rà soát bản ghi trùng |
| Đọc RootDSE ra entry tại `dc=example,dc=org` | Gọi DN rỗng trên context đã đặt base | Tạo client/context không base để truy cập RootDSE |
| Ghi entry lỗi schema hoặc quyền | Root DN hợp lệ nhưng thiếu objectClass/MUST hoặc bind không có ACL | Kiểm tra schema thực tế, quyền và thao tác LDAP cụ thể |

### Trình tự kiểm tra hiệu quả

1. **Xác nhận endpoint:** hostname, cổng, TLS và directory server mà ứng dụng thực sự kết nối.
2. **Đọc RootDSE đúng cách:** xem `namingContexts` và các thuộc tính riêng của server như `defaultNamingContext` trên AD.
3. **Xác nhận NC cần dùng:** đối chiếu dữ liệu nghiệp vụ thật với suffix/partition; không suy từ tên DNS một cách máy móc.
4. **Kiểm tra context base:** ghi nhận giá trị `spring.ldap.base` và cách tạo `LdapContextSource`.
5. **Kiểm tra DN/search base:** so phần tương đối với context base; dùng `LdapNameBuilder` cho DN, builder filter cho dữ liệu đầu vào.
6. **Phân loại lỗi:** lỗi không tìm thấy, lỗi bind, ACL, TLS, referral, timeout và lỗi schema có nguyên nhân khác nhau.
7. **Kiểm chứng bằng tài khoản thật của ứng dụng:** thao tác bằng admin có thể thành công trong khi tài khoản dịch vụ bị hạn chế.

Không ghi mật khẩu bind, giá trị secret hay toàn bộ entry nhạy cảm vào log chỉ để debug DN.

## 11. Bảo mật và khả năng mở rộng khi quản lý nhiều suffix

**Đặt base đúng là một phần của thiết kế an toàn**, nhưng không thay cho cơ chế phân quyền:

- Dùng LDAPS hoặc StartTLS với **xác thực chứng chỉ máy chủ**, quản lý secret bên ngoài source code và đặt timeout thích hợp.
- Tài khoản bind chỉ đọc cần quyền đọc đúng vùng và thuộc tính cần thiết. Quyền ghi entry nên tách khỏi quyền tra cứu khi nghiệp vụ không cần cập nhật.
- Giới hạn lựa chọn tenant/directory theo cấu hình đáng tin cậy; không đưa DN thô do client tự gửi trực tiếp vào `lookup` hoặc `search` ngoài phạm vi nghiệp vụ.
- Sử dụng filter builder khi tìm theo `uid`, `mail`, `cn`; sử dụng DN builder khi đặt RDN. Tránh LDAP injection cũng như đọc nhầm cây do ghép chuỗi sai.
- Theo dõi LDAP server thực sự phục vụ suffix nào, đặc biệt khi có replica, proxy, referral hoặc thay đổi topology.
- Xác định cách đồng bộ và đối chiếu identity khi user **rename/move**: DN có thể đổi mà định danh nghiệp vụ vẫn như cũ.

Nếu tổ chức định tuyến các đơn vị khách hàng tới nhiều suffix, nên có **bảng ánh xạ định danh tổ chức → context/base được ủy quyền** và kiểm thử cả trường hợp tenant A không thể đọc tenant B. Tầng ứng dụng cũng phải kiểm soát quyền người dùng cuối, kể cả khi tài khoản bind LDAP có thể đọc nhiều nhánh.

## 12. Kiểm thử tích hợp với directory

Mock `LdapTemplate` có thể kiểm tra nhánh logic Java nhưng **không chứng minh được** naming context, suffix, base DN, schema hay quyền truy cập đã đúng. Hãy có directory thử nghiệm với ít nhất một suffix và các OU/entry tương ứng.

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
|---|---|---|
| RootDSE | Context không base, query DN rỗng | Nhận các naming context mà server công bố |
| Đọc NC root | Lookup `dc=example,dc=org` từ context không base hoặc lookup DN rỗng với context base là suffix | Nhận entry root nếu tồn tại và tài khoản có quyền |
| Lookup đúng DN tương đối | Context base `dc=example,dc=org`; DN `uid=u1001,ou=people` | Đọc đúng entry người dùng |
| DN bị thêm base hai lần | Truyền DN đầy đủ vào API cần DN tương đối | Kiểm thử phát hiện lỗi định vị |
| Search theo UID | Search base `ou=people`, filter `uid=u1001` | Trả đúng các entry phù hợp |
| Scope khác nhau | Entry ở OU con dưới `ou=people` | ONELEVEL không thấy, SUBTREE có thể thấy |
| Hai suffix độc lập | Hai entry trùng `uid` trong NC khác nhau | Không nhầm hai entry thành một tài khoản |
| Không có quyền | Bind bằng tài khoản chỉ đọc hạn chế ACL | Không tự suy ra lỗi quyền là entry không tồn tại |
| DN ký tự đặc biệt | UID/CN thử nghiệm có giá trị cần escape hợp lệ với schema | DN builder đọc đúng; filter builder không mở rộng tìm kiếm |
| Rename/move | Chuyển entry sang OU khác trong directory test | DN cũ không còn dùng được, DN mới được nhận diện |
| Đổi context base | Chuyển từ suffix sang `ou=people` | Các DN/search base tương đối được điều chỉnh và trả cùng entry mong đợi |

Tùy mục tiêu, có thể dùng embedded LDAP hoặc LDAP server trong môi trường test; riêng các đặc tính partition/referral/Global Catalog của AD cần kiểm thử với **AD hoặc môi trường mô phỏng đúng tính năng AD**. Khi log hoặc đo hiệu năng, ghi nhận số search/bind, thời gian truy vấn, số entry và lỗi theo đúng server/NC đã thử.

## 13. Bài tập vận dụng

Một ứng dụng dùng Spring Data LDAP có cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
```

Directory công bố hai naming context: `dc=example,dc=org` và `o=partners`. Trong đó có:

```text
uid=u1001,ou=people,dc=example,dc=org
uid=u1001,ou=people,o=partners
uid=u2001,ou=contractors,dc=example,dc=org
```

Hãy tự trả lời:

1. `spring.ldap.base` đang trỏ tới gốc naming context nào? Đây có phải RootDSE không?
2. DN tương đối cần truyền vào `ldapTemplate.lookup` để đọc `u1001` thuộc `ou=people` trong suffix `dc=example,dc=org` là gì?
3. Với context base hiện tại, có thể mặc nhiên lookup `uid=u1001,ou=people,o=partners` bằng cách truyền đúng DN đầy đủ không? Vì sao?
4. Để tìm `u2001`, nên chọn search base nào tương đối với context base? Nếu chỉ search `ou=people`, vì sao kết quả rỗng?
5. Khi muốn hỏi server các NC nó phục vụ, cần dùng DN/base nào và scope nào?
6. Nếu các LDAP entry có cùng `uid` trên nhiều NC, ứng dụng cần bổ sung gì vào quy tắc định danh để tránh nhầm tài khoản?

**Gợi ý kiểm tra:** context base là `dc=example,dc=org`, khác RootDSE. DN tương đối của người `u1001` đầu tiên là `uid=u1001,ou=people`; người `u2001` nằm trong `ou=contractors`. Với `o=partners`, cần context/endpoint và quyền phù hợp cho NC đó; không tùy tiện dùng DN đầy đủ với context đã có suffix khác. Đọc RootDSE dùng DN rỗng và scope BASE trên kết nối không áp đặt context base. Quy tắc định danh cần xét cả nguồn/NC và một khóa ổn định theo nghiệp vụ.

## 14. Ghi nhớ

- **Naming context** mô tả cây con/partition mà directory quản lý; **suffix** thường là DN gốc được cấu hình cho vùng đó, cách gọi khác nhau theo sản phẩm LDAP.
- **Gốc naming context** như `dc=example,dc=org` khác với **RootDSE** tại DN rỗng. RootDSE công bố các thuộc tính quản trị và có thể cho biết server phục vụ những NC nào.
- **LDAP context base** và **search base** là lựa chọn của client. Chúng cần khớp với naming context và vị trí thực của entry; **OU** chỉ là một entry container bên trong cây.
- Trong Spring Data LDAP, `LdapTemplate`, `LdapRepository` và ODM không làm mất ý nghĩa của DN, `objectClass` hay schema. DN có thể thay đổi khi entry bị đổi tên hoặc chuyển nhánh.
- Khi tìm kiếm, dùng LDAP filter builder và DN builder phù hợp, bảo vệ kết nối bằng TLS, cấp quyền tối thiểu và kiểm thử trực tiếp với directory để phát hiện lỗi base/suffix/ACL.

**Kết luận:** xác định đúng naming context và suffix giúp bạn chọn gốc tra cứu chính xác, thiết kế phạm vi truy cập an toàn và giải thích vì sao một LDAP entry có thể hiện diện trên server nhưng không xuất hiện trong kết quả Spring Data LDAP của ứng dụng.
