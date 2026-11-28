# Active Directory: domain, organizational unit và naming context

Trong **Spring Data LDAP**, ứng dụng Java thường dùng `LdapRepository` hoặc `LdapTemplate` để đọc và ghi các entry trong cây LDAP. Khi directory phía sau là **Microsoft Active Directory Domain Services (AD DS)**, ba khái niệm dễ bị nhầm là **domain**, **organizational unit (OU)** và **naming context (NC)**. Chúng liên quan với nhau nhưng không có cùng ý nghĩa: domain là đơn vị quản trị danh tính của AD, OU là một loại container trong một domain, còn naming context là một phân vùng của directory được lưu trữ và nhân bản theo phạm vi nhất định.

Hiểu đúng ba khái niệm giúp bạn xác định **base DN**, chọn **search scope**, nhận biết entry thuộc domain nào, phân biệt schema AD với LDAP directory khác và xử lý các trường hợp LDAP search không tìm thấy user dù tài khoản vẫn tồn tại. Bài thuộc chương **Khác biệt máy chủ** và tập trung vào những quyết định thiết kế quan trọng khi Spring Data LDAP truy cập AD, gồm DN, `objectClass`, repository, `LdapTemplate`, bảo mật kết nối và kiểm thử.

## 1. Bắt đầu từ một cây Active Directory

Giả sử tổ chức có domain AD tên DNS là **`corp.example.com`**. Một số entry được bố trí như sau:

```text
DC=corp,DC=example,DC=com              ← domain naming context (domain NC)
├── OU=Engineering                     ← organizational unit
│   ├── CN=An Nguyen                   ← user
│   └── CN=Developers                  ← group
├── OU=Operations
│   └── CN=Lan Tran                    ← user
└── CN=Users                           ← container mặc định, không phải OU
    └── CN=Guest                       ← một tài khoản ví dụ
```

Ví dụ DN đầy đủ của An Nguyen là:

```text
CN=An Nguyen,OU=Engineering,DC=corp,DC=example,DC=com
```

Đọc DN từ trái sang phải:

- **`CN=An Nguyen`** là **Relative Distinguished Name (RDN)** của entry người dùng trong container cha.
- **`OU=Engineering`** là OU chứa entry đó.
- **`DC=corp,DC=example,DC=com`** là DN gốc của **domain naming context** tương ứng với domain DNS `corp.example.com`.

Mỗi entry có DN riêng và các thuộc tính khác do schema của AD quy định, chẳng hạn `objectClass`, `cn`, `distinguishedName`, `sAMAccountName`, `userPrincipalName`, `objectGUID` và `memberOf` khi có. **DN là địa chỉ trong cây, không phải định danh nghiệp vụ bất biến:** nếu đổi RDN hoặc chuyển entry sang OU khác, DN sẽ thay đổi.

## 2. Domain là gì trong Active Directory?

Trong **AD DS**, một **domain** là phạm vi tổ chức các đối tượng như user, group, computer cùng các chính sách và quy tắc quản trị bảo mật. Domain có tên DNS, chẳng hạn `corp.example.com`, và thường được phục vụ bởi nhiều **domain controller (DC)**.

| Khía cạnh | Ý nghĩa |
|---|---|
| Tên domain DNS | Ví dụ `corp.example.com`; dùng cho định vị dịch vụ và tổ chức namespace |
| DN gốc của domain | Thường là `DC=corp,DC=example,DC=com` |
| Domain controller | Máy chủ AD DS phục vụ xác thực, LDAP và nhân bản dữ liệu theo vai trò |
| Domain naming context | Phân vùng chứa những đối tượng thuộc domain |
| OU bên trong domain | Các nhánh con dùng để sắp xếp, ủy quyền quản trị và áp dụng chính sách |
| Forest | Tập hợp một hoặc nhiều domain AD chia sẻ cấu hình và schema toàn forest |

**Một domain không phải là một OU.** Nếu có domain con `branch.corp.example.com`, nó có domain NC riêng:

```text
DC=branch,DC=corp,DC=example,DC=com
```

Đây là **một domain khác** bên trong forest, không phải `OU=branch,DC=corp,DC=example,DC=com`. Tên DNS dạng phân cấp không đồng nghĩa các entry của domain con sẽ tự xuất hiện trong một subtree search tới domain NC của domain cha.

Mỗi domain có các DC phục vụ domain đó; forest có thể có nhiều domain. Việc một DC có thể hỗ trợ yêu cầu nào phụ thuộc các naming context nó lưu trữ, vai trò Global Catalog và chính sách truy cập. Kết nối tới một DC của domain `corp.example.com` rồi search tại `DC=corp,DC=example,DC=com` **không bảo đảm** tự động tìm được mọi user thuộc những domain khác trong forest.

## 3. Organizational unit (OU) là gì?

**OU** là một loại đối tượng/container của AD dùng để **tổ chức các entry trong một domain**, thường theo bộ phận, khu vực hoặc mục đích quản trị. Ví dụ:

```text
OU=Engineering,DC=corp,DC=example,DC=com
OU=Backend,OU=Engineering,DC=corp,DC=example,DC=com
```

Một OU có thể chứa user, group, computer và OU con tùy cấu trúc của directory. OU giúp áp dụng **Group Policy** và phân quyền quản trị theo nhánh (delegation). Tuy nhiên, OU **không phải security group**: đưa user vào `OU=Engineering` không đồng nghĩa tài khoản tự động trở thành thành viên của nhóm `CN=Developers`.

### OU và container `CN=...` khác nhau thế nào?

AD có nhiều loại container. Đặc biệt:

```text
OU=Engineering,DC=corp,DC=example,DC=com
CN=Users,DC=corp,DC=example,DC=com
CN=Computers,DC=corp,DC=example,DC=com
```

`CN=Users` và `CN=Computers` là các **container mặc định** trong nhiều domain AD, không phải các OU chỉ vì bên trong chứa user/computer. Không thể thay `CN=Users` thành `OU=Users` khi viết DN rồi mong kết quả giống nhau.

| Đặc điểm | OU | Container thông thường |
|---|---|---|
| RDN hay gặp | `OU=Engineering` | `CN=Users` |
| Vai trò | Sắp xếp và ủy quyền quản trị, liên kết GPO | Chứa đối tượng theo mục đích của container |
| Có thể chứa user/group | Có, tùy tổ chức và schema | Có, tùy loại container |
| Có thể coi là nhóm quyền? | Không | Không |
| Tìm kiếm trong LDAP | Dùng DN chính xác làm search base | Dùng DN chính xác làm search base |

**Tác động thực tế:** một ứng dụng chỉ tìm trong `OU=Employees` sẽ bỏ sót user đang nằm ở `CN=Users`, dù cả hai thuộc cùng một domain. Khi user chuyển OU, phép lookup dùng DN cũ cũng không còn truy cập đúng entry. Phải chọn search base dựa trên cấu trúc AD thực tế, không suy đoán rằng mọi user đều nằm trong một OU chuẩn.

## 4. Naming context (NC) là gì?

**Naming context** là một **phân vùng (directory partition)** có DN gốc xác định, được directory server lưu trữ và phục vụ theo phạm vi nhân bản. Trong AD DS, các NC quan trọng gồm:

| Naming context | DN minh họa khi forest root là `corp.example.com` | Nội dung chính | Phạm vi thường gặp |
|---|---|---|---|
| **Domain NC** | `DC=corp,DC=example,DC=com` | User, group, computer, OU và dữ liệu của domain | Các DC thuộc domain đó |
| **Configuration NC** | `CN=Configuration,DC=corp,DC=example,DC=com` | Cấu hình forest, site, dịch vụ, topology | Các DC trong forest |
| **Schema NC** | `CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com` | Định nghĩa class, attribute và schema AD | Các DC trong forest |
| **Application NC** | Ví dụ `DC=DomainDnsZones,DC=corp,DC=example,DC=com` | Dữ liệu ứng dụng như một số phân vùng AD-integrated DNS | Tùy phân vùng và scope nhân bản |

Một forest có **một configuration NC và một schema NC dùng chung**, nhưng **mỗi domain có domain NC riêng**. Application NC không nhất thiết hiện diện ở mọi DC; nó được nhân bản theo cấu hình của phân vùng.

Sơ đồ phân biệt các NC trong một forest:

```text
Forest: corp.example.com
├── Domain NC: DC=corp,DC=example,DC=com
│   └── OU=Engineering → CN=An Nguyen
├── Domain NC khác: DC=branch,DC=corp,DC=example,DC=com
│   └── OU=Employees → CN=Minh Le
├── Configuration NC: CN=Configuration,DC=corp,DC=example,DC=com
├── Schema NC: CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com
└── Application NC: ví dụ DC=DomainDnsZones,DC=corp,DC=example,DC=com
```

Sơ đồ là **phân loại logic theo phân vùng**, không hàm ý tất cả các NC luôn là nhánh có thể tìm bằng một subtree search từ domain NC. Dù các DN trông có chung hậu tố, chúng có thể là **các partition khác nhau**.

### NC khác LDAP base thế nào?

- **NC** là phân vùng dữ liệu được server quản lý; nó tồn tại ở phía directory.
- **Base DN** trong `LdapContextSource` hoặc một search là điểm bắt đầu mà ứng dụng chọn để định vị entry.
- **Search base** có thể trỏ tới một OU nhỏ hơn domain NC, chẳng hạn `OU=Engineering,DC=corp,DC=example,DC=com`.
- Base DN không tự tạo phân vùng mới và không cho phép ứng dụng truy vấn tùy ý qua mọi NC.

Vì vậy, cần biết **DC đang kết nối phục vụ những NC nào** trước khi chọn base phù hợp.

## 5. Dùng RootDSE để khám phá naming context

LDAP cung cấp một entry đặc biệt gọi là **RootDSE** ở DN rỗng (`""`). Với AD DS, RootDSE thường cung cấp metadata cần thiết để xác định phạm vi directory mà DC đang phục vụ.

| Thuộc tính RootDSE | Ý nghĩa trong AD DS |
|---|---|
| `defaultNamingContext` | Domain NC mặc định của DC kết nối; thường là điểm bắt đầu cho user/group của domain đó |
| `rootDomainNamingContext` | Domain NC của domain gốc forest |
| `configurationNamingContext` | DN gốc configuration NC |
| `schemaNamingContext` | DN gốc schema NC |
| `namingContexts` | Các naming context được server công bố/đang phục vụ |
| `supportedCapabilities` và `supportedControl` | Một số năng lực và LDAP control mà server công bố |

Ví dụ truy vấn RootDSE bằng công cụ `ldapsearch` ở máy có thể truy cập DC (lệnh dùng giả định dịch vụ có xác thực simple bind qua TLS):

```bash
ldapsearch -LLL -x \
  -H ldaps://dc01.corp.example.com:636 \
  -D 'svc-reader@corp.example.com' -W \
  -b '' -s base \
  defaultNamingContext rootDomainNamingContext \
  configurationNamingContext schemaNamingContext namingContexts
```

Phần kết quả minh họa có thể có dạng:

```ldif
dn:
defaultNamingContext: DC=corp,DC=example,DC=com
rootDomainNamingContext: DC=corp,DC=example,DC=com
configurationNamingContext: CN=Configuration,DC=corp,DC=example,DC=com
schemaNamingContext: CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com
namingContexts: DC=corp,DC=example,DC=com
namingContexts: CN=Configuration,DC=corp,DC=example,DC=com
namingContexts: CN=Schema,CN=Configuration,DC=corp,DC=example,DC=com
```

Đây là **ví dụ dự kiến**, không phải output bắt buộc của mọi DC. Một số giá trị thay đổi theo domain, forest và partition được lưu trữ; một số thuộc tính phải được yêu cầu rõ khi đọc RootDSE.

**Cảnh báo quan trọng khi dùng Spring LDAP:** nếu `LdapContextSource` đã cấu hình base `DC=corp,DC=example,DC=com`, thì `LdapTemplate.lookup("")` thường trỏ tới **entry tại base đó**, không tự động quay về **RootDSE của server**. Để đọc RootDSE, hãy dùng một `ContextSource` riêng **không đặt base DN** hoặc API kết nối trực tiếp hỗ trợ query RootDSE. Đừng dùng `lookup("")` trên context có base rồi coi kết quả như RootDSE.

RootDSE có thể thay đổi theo **DC đích**. Nếu ứng dụng dùng DNS/load balancer chọn DC khác, hãy ghi nhận DC mà kết nối thực sự đang dùng khi kiểm tra `defaultNamingContext` và các partition có sẵn.

## 6. Domain NC và search base trong Spring Data LDAP

Giả sử ứng dụng chỉ cần tìm user của domain `corp.example.com`, còn LDAP endpoint là một DC phục vụ domain đó. Một cấu hình Spring Boot minh họa:

```yaml
spring:
  ldap:
    urls: ldaps://dc01.corp.example.com:636
    base: DC=corp,DC=example,DC=com
    username: svc-reader@corp.example.com
    password: ${LDAP_BIND_PASSWORD}
```

Ở cấu hình này, **DN truyền vào các API của `LdapTemplate` thường là DN tương đối với `spring.ldap.base`**:

| Entry hoặc nhánh muốn truy cập | DN tương đối với base |
|---|---|
| OU Engineering | `OU=Engineering` |
| User An Nguyen trong OU Engineering | `CN=An Nguyen,OU=Engineering` |
| Group Developers trong OU Engineering | `CN=Developers,OU=Engineering` |
| Container mặc định Users | `CN=Users` |

Đừng truyền DN đầy đủ `CN=An Nguyen,OU=Engineering,DC=corp,DC=example,DC=com` vào context đã có cùng hậu tố base khi API yêu cầu relative DN: bạn có thể bị nhân đôi hậu tố và gặp lỗi không tìm thấy.

### Ví dụ truy vấn AD bằng `LdapTemplate`

Giả sử ứng dụng cần tìm tài khoản người dùng thực sự thuộc `OU=Engineering`, theo `sAMAccountName`. Sử dụng `LdapQueryBuilder` để xây LDAP filter an toàn:

```java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class ActiveDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public ActiveDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByAccountName(String accountName) {
        LdapQuery ldapQuery = query()
                .base("OU=Engineering")
                .where("objectCategory").is("person")
                .and("objectClass").is("user")
                .and("sAMAccountName").is(accountName);

        AttributesMapper<String> mapper = attributes ->
                (String) attributes.get("cn").get();

        return ldapTemplate.search(ldapQuery, mapper);
    }

    public String lookupNameAtKnownDn(String cn) {
        Name dn = LdapNameBuilder.newInstance("OU=Engineering")
                .add("CN", cn)
                .build();

        AttributesMapper<String> mapper = attributes ->
                (String) attributes.get("cn").get();

        return ldapTemplate.lookup(dn, mapper);
    }
}
```

Giải thích:

1. `base("OU=Engineering")` chọn nhánh tương đối với domain NC đã cấu hình. Truy vấn mặc định không tự mở rộng sang OU của domain khác.
2. `(objectCategory=person)` kết hợp với `(objectClass=user)` là kiểu lọc thông dụng trong AD để chọn user, tránh nhầm một số loại đối tượng khác có quan hệ kế thừa object class với `user` (chẳng hạn computer).
3. `sAMAccountName` là thuộc tính tài khoản theo quy ước AD; không nên mặc định AD có `uid` hoặc user luôn dùng `UID=...` làm RDN như một số LDAP directory khác.
4. `LdapNameBuilder` escape giá trị RDN phù hợp, quan trọng khi `CN` có dấu phẩy/ký tự đặc biệt. **LDAP DN escaping và LDAP filter escaping là hai quy tắc khác nhau.**
5. `lookup` cần **biết đúng CN và OU hiện tại**; nếu chỉ biết tên đăng nhập, `search` theo thuộc tính thường hợp lý hơn. Search có thể trả 0, 1 hoặc nhiều entry; kiểm tra tính duy nhất theo phạm vi nghiệp vụ.

Đoạn code giả định base, OU, quyền tài khoản bind và dữ liệu đã được chuẩn bị đúng trong AD test. Với thuộc tính có thể không tồn tại, nên kiểm tra `attributes.get(...)` trước khi lấy giá trị. Search scope, requested attributes, size/time limit và lựa chọn DC cũng ảnh hưởng kết quả và hiệu năng.

## 7. Ánh xạ AD entry bằng ODM và repository

Spring Data LDAP hỗ trợ mô hình repository dựa trên **Object–Directory Mapping (ODM)** của Spring LDAP. Với AD, cần ánh xạ **tên thuộc tính thực tế của AD**, không lấy nguyên giả định của một LDAP server khác.

```java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "OU=Engineering",
    objectClasses = {"top", "person", "organizationalPerson", "user"}
)
public class AdPerson {

    @Id
    private Name dn;

    @Attribute(name = "sAMAccountName")
    private String accountName;

    @Attribute(name = "userPrincipalName")
    private String principalName;

    @Attribute(name = "cn")
    private String commonName;

    public AdPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getAccountName() { return accountName; }
    public void setAccountName(String accountName) {
        this.accountName = accountName;
    }
    public String getPrincipalName() { return principalName; }
    public void setPrincipalName(String principalName) {
        this.principalName = principalName;
    }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
}
```

Lớp `AdPerson` minh họa mapping để **đọc** entry AD trong một OU cụ thể. `@Id` biểu diễn DN dưới dạng `javax.naming.Name`, không phải khóa chính số. `@Entry` nêu các object class mong đợi, nhưng **AD schema và quyền ACL** vẫn quyết định entry nào có thể đọc hoặc ghi. Không coi `userPrincipalName` và `sAMAccountName` là những khóa định danh bất biến hoặc mặc định có cùng định dạng DN.

Nếu dùng `LdapRepository<AdPerson>`, thao tác truy vấn kế thừa hoặc query method vẫn phải tôn trọng **domain NC**, **base**, **OU**, cấu hình context và điều kiện tìm kiếm. Đối tượng chuyển OU sẽ đổi DN, ảnh hưởng `findById` hoặc các tham chiếu đang lưu. Việc ghi tài khoản AD không chỉ là một lệnh `save()`: tạo account, đặt mật khẩu, trạng thái enabled và các quyền cần đáp ứng quy trình cùng quy định riêng của AD. Hãy kiểm thử trên directory được phép ghi trước khi áp dụng CRUD thực tế.

## 8. Thuộc tính định danh AD: tránh suy luận từ tên và DN

Một AD user có thể có:

```ldif
dn: CN=An Nguyen,OU=Engineering,DC=corp,DC=example,DC=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: user
cn: An Nguyen
sAMAccountName: an.nguyen
userPrincipalName: an.nguyen@corp.example.com
displayName: An Nguyen
mail: an.nguyen@example.com
```

LDIF chỉ minh họa các thuộc tính thường đọc được; entry AD còn có nhiều thuộc tính khác (gồm thuộc tính do server quản lý), và không nên dùng ví dụ này làm bản ghi đầy đủ để tự tạo AD user.

| Thuộc tính | Ý nghĩa và lưu ý |
|---|---|
| `distinguishedName` | DN hiện tại của entry; thay đổi khi rename/move |
| `cn` | Tên chung của object; thường dùng làm RDN user nhưng không bảo đảm là login |
| `sAMAccountName` | Tên đăng nhập kiểu SAM, thường được quản lý trong domain; có thể đổi |
| `userPrincipalName` | Tên principal dạng `user@suffix`; hậu tố UPN có thể khác domain DNS và có thể được thay đổi |
| `objectGUID` | Định danh nhị phân do AD cấp, thường ổn định trong vòng đời entry; cần giải mã đúng kiểu GUID |
| `objectSid` | Định danh bảo mật (SID); có ngữ nghĩa vòng đời/migration riêng, không xem như DN |
| `memberOf` | Danh sách liên kết nhóm trực tiếp trong nhiều trường hợp; không đủ để kết luận toàn bộ nhóm hiệu lực |

Ví dụ, user chuyển từ `OU=Engineering` sang `OU=Operations`, hoặc CN đổi vì đổi tên hiển thị: DN cũ không còn trỏ đúng entry. Khi đồng bộ danh tính, nên chọn khóa liên kết theo hợp đồng nghiệp vụ hoặc ID directory phù hợp; cần hiểu vòng đời `objectGUID`, migration qua domain/forest và cách đối chiếu identity thực tế.

`memberOf` không mặc định phản ánh **nhóm lồng nhau** hay **primary group**; mô hình phân quyền trên AD phải đánh giá riêng cơ chế xác định group membership. Không dùng `OU` như một security group.

## 9. Truy vấn nhiều domain: referral, Global Catalog và giới hạn

Khi có nhiều domain trong cùng forest, ứng dụng có thể cần tìm tài khoản ở phạm vi rộng hơn một domain NC. Có ba hướng kiến trúc thường gặp:

1. **Kết nối DC của đúng domain** và tìm trong domain NC đó: phù hợp nếu đã biết domain sở hữu entry.
2. **Truy vấn Global Catalog (GC)** khi cần tìm danh tính across-domain trong forest: GC lưu thông tin một phần của đối tượng từ các domain khác nhau; thường truy cập qua cổng **3268 (LDAP)** hoặc **3269 (LDAP bảo vệ bằng TLS)**, tùy cấu hình thực tế.
3. **Đi theo referral hoặc chủ động định tuyến tới DC domain khác** khi thao tác/truy vấn yêu cầu domain NC ngoài vùng DC đang phục vụ.

### Global Catalog không phải toàn bộ dữ liệu của mọi domain

GC cung cấp **partial attribute set** đối với bản sao của các object thuộc domain khác. Vì vậy, search qua GC có thể tìm thấy entry nhưng **không trả đầy đủ mọi thuộc tính** mà bạn nhận được khi query một DC của domain sở hữu entry. Những thao tác cần dữ liệu đặc thù hoặc ghi entry nên được thực hiện với DC và partition thích hợp, cùng ACL tương ứng.

Đừng hiểu `DC=corp,DC=example,DC=com` là search base tự động bao trùm cả `DC=branch,DC=corp,DC=example,DC=com` khi kết nối một DC thông thường. Nếu dùng GC, phải kiểm chứng **search base và scope mà GC endpoint hỗ trợ**, cùng những thuộc tính thực sự có trong kết quả.

### Referral và nhiều connection

LDAP referral có thể hướng client tới directory server khác. Cách JNDI/Spring LDAP xử lý referral, credentials, TLS và timeout ảnh hưởng cả bảo mật lẫn hiệu năng. Không bật follow referral một cách thiếu kiểm soát: cần xác nhận hostname đích, chứng chỉ, danh tính bind và mức truy cập tương ứng. Referral cũng có thể khiến một thao tác nghiệp vụ tạo nhiều lần kết nối/truy vấn hơn dự kiến.

## 10. Bảo mật khi Spring Data LDAP truy cập AD

Việc biết DN và có thể tìm thấy entry **không có nghĩa** ứng dụng được phép đọc hoặc sửa mọi thuộc tính. AD áp dụng ACL và cơ chế bảo mật riêng cho các object/attribute. Khi tích hợp:

- Dùng **LDAPS hoặc StartTLS** theo chính sách hạ tầng; chứng chỉ DC phải được xác thực đúng. Một endpoint LDAP không bảo vệ không phù hợp để truyền thông tin nhạy cảm hoặc simple bind credentials trên mạng.
- Dùng tài khoản dịch vụ có **quyền tối thiểu** cho nhu cầu tra cứu; tài khoản chỉ đọc không cần quyền quản trị domain. Nếu cần tạo/sửa account, tách riêng luồng provisioning có quyền và kiểm toán rõ ràng.
- Tránh đưa mật khẩu bind vào source code hoặc log. Trong ứng dụng thực tế, đọc secret từ hệ thống cấu hình/secret store và bảo vệ quyền truy cập.
- Giới hạn query theo OU hoặc domain khi có thể, dùng `LdapQueryBuilder` cho filter từ input và `LdapNameBuilder` cho DN, tránh LDAP injection hoặc truy cập ngoài nhánh cho phép.
- Không đồng nhất **phân cấp OU** với **security authorization**. Đọc được một entry dưới OU nào đó không chứng minh người dùng cuối của API có quyền xem dữ liệu nhạy cảm của entry đó.
- Xử lý riêng lỗi **authentication**, **authorization**, **not found**, **referral**, **timeout** và **TLS**; không che mọi lỗi thành “không tồn tại tài khoản”.

Đặc biệt, thay đổi trạng thái user, mật khẩu, nhóm hoặc các thuộc tính đặc thù AD như `userAccountControl` có quy tắc riêng. Không triển khai CRUD tổng quát trên tất cả thuộc tính nếu chưa kiểm tra schema, quyền quản trị và chính sách vận hành AD.

## 11. Kiểm thử domain, OU và naming context

Cần kiểm thử trên **AD thử nghiệm** hoặc môi trường directory tương đương phù hợp với yêu cầu, bởi LDAP server generic không thể mô phỏng đầy đủ mọi hành vi đặc thù AD. Một ma trận kiểm thử hữu ích:

| Tình huống | Thiết lập | Kỳ vọng |
|---|---|---|
| Đọc RootDSE | Kết nối DC với context không có base | Lấy đúng `defaultNamingContext`, `namingContexts` và các NC server công bố |
| Đọc user dưới OU | Base là domain NC, query `OU=Engineering` | Nhìn thấy user có DN thuộc nhánh này |
| User ở `CN=Users` | Query chỉ trong `OU=Engineering` | Không tự xuất hiện; phải chọn base phù hợp |
| Đổi OU | Rename/move entry giữa các OU trong test | DN cũ không lookup được; DN mới truy cập được nếu có quyền |
| Nhầm domain con và OU | Domain `branch.corp.example.com` | Không coi domain con là một OU trong domain cha |
| Query qua GC | Search trên endpoint GC đã cấu hình | Quan sát phạm vi cross-domain và danh sách thuộc tính được cung cấp |
| Thuộc tính AD | User có `sAMAccountName`, `userPrincipalName`, `objectGUID` | Mapper xử lý đúng kiểu text/binary, không nhầm ID |
| Phân quyền LDAP | Service account chỉ đọc | Không đọc được thuộc tính/nhánh bị ACL chặn; từ chối thao tác ghi |
| Ký tự đặc biệt | `CN` chứa dấu phẩy/ký tự cần escape | DN builder tạo đúng RDN; filter builder an toàn |
| Lỗi mạng và TLS | DC không sẵn sàng hoặc chứng chỉ không hợp lệ | Lỗi được phân loại; không tự giảm mức bảo mật |

Khi thử nghiệm, ghi rõ **DC kết nối**, **forest/domain**, **port**, **base DN**, **search scope**, **objectClass/filter**, số entry và thuộc tính trả về. Có thể thu thập log/metric của ứng dụng và directory để phân biệt lỗi định vị DN với lỗi phân quyền hoặc hiệu năng.

## 12. Bài tập tình huống

Tổ chức có forest root `corp.example.com`, một child domain `branch.corp.example.com` và các entry:

```text
CN=An Nguyen,OU=Engineering,DC=corp,DC=example,DC=com
CN=Binh Le,CN=Users,DC=corp,DC=example,DC=com
CN=Minh Tran,OU=Engineering,DC=branch,DC=corp,DC=example,DC=com
```

Ứng dụng Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://dc01.corp.example.com:636
    base: DC=corp,DC=example,DC=com
```

Hãy tự trả lời:

1. Đâu là **domain NC** của `corp.example.com`? DN của child domain có phải một OU không?
2. Khi `LdapTemplate.search` chọn `base("OU=Engineering")`, ứng dụng có chắc chắn tìm thấy cả An và Minh không? Vì sao?
3. DN **tương đối** để lookup An và Binh là gì? Vì sao dùng `OU=Users` cho Binh sẽ sai?
4. Nếu chỉ biết `sAMAccountName`, nên chọn **lookup** theo DN hay **search** theo filter?
5. Khi muốn tìm tài khoản trên nhiều domain, GC có ưu điểm gì và giới hạn thuộc tính nào cần kiểm chứng?
6. Vì sao `ldapTemplate.lookup("")` trên context có base domain không phải cách chắc chắn để đọc RootDSE?

**Gợi ý đối chiếu:** domain NC của domain chính là `DC=corp,DC=example,DC=com`. DN của An tương đối là `CN=An Nguyen,OU=Engineering`; DN của Binh tương đối là `CN=Binh Le,CN=Users`. Child domain có NC riêng nên tìm trên một DC/domain base thông thường không bảo đảm trả Minh. Biết tên đăng nhập nhưng không chắc CN/OU thì nên search có filter an toàn. GC có thể hỗ trợ tìm cross-domain nhưng có giới hạn về thuộc tính được nhân bản.

## 13. Ghi nhớ khi triển khai Spring Data LDAP với Active Directory

- **Domain** là đơn vị quản trị/danh tính trong AD; domain DNS `corp.example.com` thường có domain NC `DC=corp,DC=example,DC=com`.
- **OU** là nhánh quản trị trong một domain, có RDN `OU=...`. Nó không phải domain và cũng không phải security group; `CN=Users` là container, không phải OU.
- **Naming context** là directory partition. Domain NC chứa các user/group/OU của domain; configuration/schema NC dùng chung trong forest, ngoài ra có application NC.
- Đọc **RootDSE của DC thực sự kết nối** để xác định các NC và khả năng server; chú ý không nhầm DN rỗng trong context đã cấu hình base với RootDSE.
- Trong **`LdapTemplate`/`LdapRepository`**, hãy chọn đúng base DN, OU, scope và filter. Các thuộc tính AD như `sAMAccountName`, `userPrincipalName` và `objectGUID` có ngữ nghĩa khác `uid`/DN trong LDAP directory khác.
- Khi cần cross-domain, đánh giá **Global Catalog**, khả năng referral và hạn chế về thuộc tính/ghi dữ liệu. Dùng TLS, quyền tối thiểu và kiểm thử tích hợp với AD.

Việc xác định đúng domain, organizational unit và naming context là cơ sở để ánh xạ các LDAP entry phân cấp thành đối tượng Java chính xác, truy vấn an toàn và tránh những lỗi “không tìm thấy” khó chẩn đoán khi Spring Data LDAP chạy trên Active Directory.
