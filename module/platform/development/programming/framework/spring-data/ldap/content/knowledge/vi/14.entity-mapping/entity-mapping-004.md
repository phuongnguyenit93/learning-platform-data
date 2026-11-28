# Cấu hình base của thực thể trong cây thư mục

Khi truy cập LDAP qua **Spring Data LDAP**, một đối tượng Java không được lưu vào một “bảng” như JPA. Nó tương ứng với một **entry** trong cây thư mục (Directory Information Tree – DIT). Vị trí của entry được xác định bằng **Distinguished Name (DN)**. Vì vậy, cấu hình base là một trong những quyết định quan trọng nhất khi ánh xạ thực thể: sai base có thể khiến ứng dụng tìm không thấy người dùng, tạo entry ở sai nhánh hoặc xử lý nhầm DN.

Bài này thuộc chương **Ánh xạ thực thể** của `SPRING_DATA_LDAP`. Bạn sẽ phối hợp ba khái niệm thường bị nhầm với nhau: **base DN của `ContextSource`**, **`@Entry(base=...)` của lớp Java** và **`@Id` chứa DN của từng entry**. Nội dung bao gồm ví dụ Java, LDIF, repository/`LdapTemplate`, CRUD, DN builder, phân cấp nhiều OU, bảo mật và kiểm thử với directory.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích DN, RDN, naming context, search base và vị trí của entry trong DIT.
2. Phân biệt tác dụng của `spring.ldap.base` với `@Entry(base=...)` và `@Id`.
3. Xác định DN tương đối/đầy đủ bằng một quy tắc ghép đường dẫn rõ ràng.
4. Khai báo `@Entry`, `@Id`, `@DnAttribute`, `@Attribute` và `@Transient` đúng vai trò.
5. Tạo và tìm entity trong nhánh `ou=people` bằng ODM hoặc Spring Data LDAP repository.
6. Dùng `LdapTemplate` với search base/scope phù hợp và filter an toàn.
7. Tránh lỗi lặp base, sai thứ tự RDN, dùng DN đầy đủ ở vị trí cần DN tương đối.
8. Kiểm thử cách ánh xạ với LDIF, LDAP server và chính tài khoản Bind của ứng dụng.

## 2. Bắt đầu từ cây LDAP, không bắt đầu từ Java

Giả sử directory phục vụ danh bạ công ty có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    └── cn=svc-reader
~~~

Một người dùng có DN đầy đủ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Các thành phần:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Naming context | `dc=example,dc=org` | Phần gốc dữ liệu được directory phục vụ. |
| OU chứa người dùng | `ou=people,dc=example,dc=org` | Nhánh trong cây. |
| RDN của Lan | `uid=lan` | Tên entry tương đối với entry cha trực tiếp. |
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` | Tên phân biệt entry trong directory. |
| Search base | `ou=people,dc=example,dc=org` | Điểm bắt đầu một phép Search. |
| Bind DN | `cn=svc-reader,ou=service,dc=example,dc=org` | Danh tính tài khoản kết nối, **không phải** search base. |

Trong ví dụ, `uid` là tên thuộc tính LDAP đồng thời được dùng làm RDN. Điều này là một **quy ước thiết kế**: bạn cũng có thể gặp entry dùng `cn` làm RDN, hoặc người dùng nằm trong nhiều OU con.

### LDIF của entry người dùng

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

Schema `inetOrgPerson` kế thừa `organizationalPerson` và `person`. Vì vậy `cn` và `sn` vẫn bắt buộc. `objectClass` mô tả **entry là kiểu gì**; DN cho biết **entry nằm ở đâu**. `@Entry(base)` không thay thế các yêu cầu của schema.

## 3. Ba tầng base cần phân biệt

Cùng một người dùng có thể được mô tả ở ba tầng:

~~~mermaid
flowchart TD
    A["ContextSource.base<br/>dc=example,dc=org"] --> B["@Entry(base)<br/>ou=people"]
    B --> C["RDN từ uid<br/>uid=lan"]
    C --> D["Entry LDAP đầy đủ<br/>uid=lan,ou=people,dc=example,dc=org"]
~~~

### 3.1. `spring.ldap.base`: gốc chung của ContextSource

Ví dụ Spring Boot:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
~~~

Ở cấu hình này, `ContextSource` đặt gốc **`dc=example,dc=org`**. Các DN được đưa vào hoạt động thông thường của `LdapTemplate` có thể là DN **tương đối** với gốc đó.

Ví dụ, thao tác trên DN tương đối:

~~~text
uid=lan,ou=people
~~~

sẽ tương ứng với entry LDAP đầy đủ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Cấu hình này áp dụng chung cho các thành phần dùng chính `ContextSource` đó: entity người dùng, nhóm, các truy vấn do `LdapTemplate` thực hiện.

**Lưu ý:** `spring.ldap.username` là DN dùng xác thực (Bind) và thông thường phải là **DN đầy đủ** cho tài khoản dịch vụ, kể cả khi `spring.ldap.base` đã được đặt. Không tự thêm hoặc cắt `dc=example,dc=org` vào Bind DN theo suy đoán.

### 3.2. `@Entry(base=...)`: gốc logic của một loại entity

~~~java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {
    // ...
}
~~~

`@Entry(base="ou=people")` xác định gốc của các entry mà lớp `DirectoryPerson` đại diện. Theo API ODM của Spring LDAP, **base này được thêm vào các DN do ODM tính toán** từ trường được đánh dấu `@DnAttribute`.

Đây là **metadata của entity**, không phải cấu hình kết nối đến server, không tạo entry `ou=people` và cũng **không phải một chính sách phân quyền**. Directory phải có nhánh `ou=people` sẵn thì mới tạo entry con được.

### 3.3. `@Id`: DN của một entry cụ thể

~~~java
@Id
private Name dn;
~~~

Trường này lưu danh tính LDAP của **một entry**. Kiểu yêu cầu là `javax.naming.Name`, có thể được biểu diễn bằng `LdapName`. Đừng dùng `Long`, `UUID` hoặc import nhầm `org.springframework.data.annotation.Id` như cách thường dùng với một số loại repository khác.

Khi `ContextSource` có base, các API LDAP của Spring thường làm việc với **DN tương đối với context**. Với entry Lan, ví dụ là `uid=lan,ou=people`. DN trong `@Id` không tự trở thành RDN đơn lẻ `uid=lan` chỉ vì entity đã có `@Entry(base="ou=people")`.

**Điểm cần kiểm thử:** khác biệt quan trọng là DN **được ODM tính từ `@DnAttribute`** hay DN **đã được lập trình viên gán trực tiếp vào `@Id`**. `@Entry(base)` được dùng cho việc tính DN; đừng giả định framework sẽ tự sửa mọi DN explicit hoặc an toàn loại bỏ base bị lặp. Hãy kiểm tra hành vi thực tế trước thao tác ghi.

## 4. Quy tắc ghép DN cho ví dụ cơ bản

Với một nhân viên nằm trực tiếp dưới `ou=people`:

| Tầng | Giá trị |
| --- | --- |
| ContextSource base | `dc=example,dc=org` |
| Entity base | `ou=people` |
| RDN | `uid=lan` |
| DN tương đối với ContextSource | `uid=lan,ou=people` |
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` |

Có thể ghi nhớ theo sơ đồ:

~~~text
uid=lan  +  ou=people  +  dc=example,dc=org
   |             |                |
   |             |                +-- ContextSource base
   |             +------------------- @Entry(base)
   +-------------------------------- RDN của entry
~~~

**Không đảo vị trí:** `uid=lan,ou=people` và `ou=people,uid=lan` là hai DN khác cấu trúc. Vế bên trái là RDN gần entry nhất; càng sang phải càng tiến về gốc của cây.

Không được tự cho rằng mọi DN đi qua Spring LDAP đều phải luôn ghép bằng dấu phẩy theo công thức thủ công. DN có cú pháp escaping và có thể chứa RDN phức tạp. Công thức trên giúp **hình dung cấu trúc**, còn mã Java nên dùng `LdapNameBuilder` hoặc `LdapName`.

## 5. Ví dụ entity có @Entry(base) và @DnAttribute

`@DnAttribute` dùng để ánh xạ một phần DN sang trường Java. Khi khai báo `index`, Spring LDAP ODM có thể **tính DN cho entity** khi tạo, tìm để sửa hoặc xóa, kết hợp với base của `@Entry`.

`DirectoryPerson.java`:

~~~java
package com.example.directory.model;

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

    @Id
    private Name dn;

    // index=0: RDN gần @Entry(base) nhất trong DN tính toán.
    // Đồng thời uid là thuộc tính LDAP cần lưu trên entry.
    @DnAttribute(index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Các vai trò không nên nhầm:

- `@Entry` khai báo **objectClass** và base của lớp entity. Khi **tạo mới**, ODM chỉ sử dụng tập object class đã khai báo trong metadata mapping.
- `@Id` giữ DN, kiểu `Name`. Không phải trường mã người dùng `uid`.
- `@DnAttribute(index=0)` làm `uid` tham gia vào DN được **tính toán**. Khi chỉ có một thành phần RDN trước `@Entry(base)`, `uid` chính là RDN đó.
- `@Attribute(name="uid")` làm `uid` tiếp tục được ánh xạ thành thuộc tính LDAP có giá trị. `@DnAttribute` **không tự làm trường trở thành transient**.
- `cn` và `sn` là thuộc tính bắt buộc do chuỗi object class `person → organizationalPerson → inetOrgPerson`.
- `mail` là thuộc tính tùy chọn theo schema thông thường, nhưng có thể là bắt buộc theo quy tắc nghiệp vụ của ứng dụng.

Nếu entry thực tế có các object class bổ sung ngoài cấu hình hoặc thuộc tính được quy định bởi schema mở rộng, cần điều chỉnh mapping cho phù hợp. Không coi `@Entry` như cơ chế tự động chuyển schema trên LDAP server.

## 6. Tạo entry bằng ODM để quan sát cách tính DN

Dùng `LdapTemplate` làm việc với ODM:

~~~java
import org.springframework.ldap.core.LdapTemplate;

public class PersonCreator {

    private final LdapTemplate ldapTemplate;

    public PersonCreator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createLan() {
        DirectoryPerson person = new DirectoryPerson();
        person.setUid("lan");
        person.setFullName("Nguyen Thi Lan");
        person.setSurname("Nguyen");
        person.setEmail("lan@example.org");

        // Không truyền DN đầy đủ từ HTTP request.
        // ODM tính DN từ @DnAttribute(index=0) và @Entry(base).
        ldapTemplate.create(person);
    }
}
~~~

Với `spring.ldap.base=dc=example,dc=org`, kết quả mong đợi được đọc lại từ directory:

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

**Các điều kiện để tạo thành công:**

1. Naming context `dc=example,dc=org` và entry cha `ou=people` phải tồn tại.
2. Server phải nạp schema `inetOrgPerson`.
3. Tài khoản kết nối phải có quyền **Add** ở đúng nhánh.
4. `uid` hợp lệ theo quy tắc nghiệp vụ và chưa có entry cùng DN.
5. `cn`, `sn` phải có giá trị phù hợp schema.
6. Kiểu field, mapper và phiên bản Spring LDAP phải hỗ trợ cấu hình ODM đang dùng.

Bởi vì đây là ví dụ tính DN qua `@DnAttribute`, hãy **để ODM tạo DN**; không đồng thời tự gán `@Id` bằng DN đã chứa `ou=people` rồi giả định framework luôn xử lý “chỉ một lần”. Nếu chọn cách gán DN tường minh, dùng quy tắc khác ở mục 8.

## 7. Tìm entity: repository và scope của truy vấn

Spring Data LDAP repository dùng entity đã khai báo ODM:

~~~java
import java.util.Optional;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Gọi:

~~~java
Optional<DirectoryPerson> person = repository.findByUid("lan");
~~~

Lưu ý:

- `findByUid` suy từ tên thuộc tính Java `uid` và mapping LDAP `@Attribute(name="uid")`.
- `Optional` có nghĩa ứng dụng kỳ vọng tối đa một kết quả. LDAP schema không tự đảm bảo giá trị `uid` duy nhất ở **mọi DN**, nên cần thiết kế ràng buộc dữ liệu theo phạm vi.
- `@Entry(base="ou=people")` mô tả nơi các entry của entity thường nằm, nhưng đừng dùng annotation này như **ACL**, hoặc giả định mọi truy vấn custom bất kể base/scope đều bị khóa trong `ou=people`.
- Với truy vấn tìm theo nhiều điều kiện, dùng `LdapTemplate` hoặc `LdapQueryBuilder` để nhìn rõ base, scope và filter.

### Tìm bằng LdapTemplate với base tường minh

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class PersonSearchService {

    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(20)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.find(query, DirectoryPerson.class);
    }
}
~~~

Ở đây `.base("ou=people")` của `LdapQueryBuilder` xác định **search base** cho phép Search này. Nó được hiểu tương đối với `ContextSource.base`, không phải mệnh lệnh “nối tiếp `ou=people` vào chính nó” do `@Entry`.

Với `SearchScope.ONELEVEL`, truy vấn tìm các entry **con trực tiếp** của `ou=people`. Nếu nhân viên nằm sâu hơn trong `ou=engineering,ou=people`, cần cân nhắc `SearchScope.SUBTREE`, đồng thời kiểm soát kích thước/thời gian Search.

### Bảng đối chiếu các loại base

| Nơi khai báo | Ví dụ | Phạm vi ảnh hưởng |
| --- | --- | --- |
| `spring.ldap.base` | `dc=example,dc=org` | Gốc chung cho các LDAP operation của ContextSource. |
| `@Entry(base)` | `ou=people` | Metadata gốc của entity, dùng khi ODM tính DN. |
| `LdapQueryBuilder.base(...)` | `ou=people` | Điểm bắt đầu riêng cho Search request đang xây. |
| `@Id Name dn` | `uid=lan,ou=people` | Tên của **một** entry, thường tương đối với ContextSource. |
| `groupOfNames.member` | `uid=lan,ou=people,dc=example,dc=org` | **Giá trị thuộc tính** tham chiếu entry, cần DN đầy đủ. |

## 8. Khi muốn gán DN tường minh thay vì để ODM tính

Có những nghiệp vụ sử dụng RDN phức tạp, cần tự quyết định OU hoặc phải di chuyển entry giữa nhánh. Khi đó có thể chọn **lập DN bằng mã service** và dùng `LdapTemplate.bind(...)` hoặc API ODM phù hợp.

Ví dụ tạo tên tương đối với context:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people
~~~

Tạo tên đầy đủ nếu thực sự cần:

~~~java
Name fullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people,dc=example,dc=org
~~~

**Không đưa `fullDn` trực tiếp vào mọi operation nếu `ContextSource` đã có base.** Trong cấu hình của bài, các thao tác thông thường của `LdapTemplate` cần DN tương đối `uid=lan,ou=people`. Sự khác biệt này là nguồn gốc của lỗi base bị lặp.

Khi sử dụng `@Id` tường minh trên entity, hãy thống nhất một quy ước về DN (tương đối với ContextSource) và kiểm thử read/create/update/delete. `@Entry(base)` áp dụng cho DN **được tính toán**; không nên phụ thuộc vào việc framework “sửa hộ” DN đặt sai bằng tay.

### Ví dụ tạo entry trực tiếp với LdapTemplate.bind

Nếu muốn tự kiểm soát DN và attributes, không phải dựa vào `@DnAttribute`:

~~~java
import java.util.List;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class ExplicitDnCreator {

    private final LdapTemplate ldapTemplate;

    public ExplicitDnCreator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(String uid, String cn, String sn) {
        if (uid == null || !uid.matches("[a-z][a-z0-9_-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Attributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        for (String clazz : List.of(
                "top", "person", "organizationalPerson", "inetOrgPerson")) {
            classes.add(clazz);
        }

        attrs.put(classes);
        attrs.put("uid", uid);
        attrs.put("cn", cn);
        attrs.put("sn", sn);

        ldapTemplate.bind(dn, null, attrs);
    }
}
~~~

Ở `LdapTemplate`, `bind(dn, null, attrs)` là thao tác **tạo entry**, không phải LDAP Bind dùng để đăng nhập kết nối. Đoạn code minh họa đường đi khi DN do service tạo; trong dự án thật, cần validate `cn`/`sn`, xử lý xung đột DN, giới hạn quyền ghi, và không cho client tự chọn OU.

Cách dùng ODM ở mục 6 và cách dùng `bind` ở mục này là **hai lối triển khai**. Chọn một cách chủ đạo cho mỗi use case để tránh tính/gắn base trùng lặp.

## 9. Cấu hình cây nhiều OU: base của entity có cố định không?

Với người dùng chia theo phòng ban, cây có thể là:

~~~text
dc=example,dc=org
└── ou=people
    ├── ou=engineering
    │   └── uid=lan
    └── ou=sales
        └── uid=mai
~~~

Ở đây `@Entry(base="ou=people")` có thể giữ **gốc chung**, còn các thành phần DN khác được tính từ thuộc tính được annotate `@DnAttribute(index=...)`.

### Cách đánh index của @DnAttribute

Ví dụ hai trường định danh ở một entity khác:

~~~java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DepartmentPerson {

    @Id
    private Name dn;

    @DnAttribute(index = 1)
    @Attribute(name = "uid")
    private String uid;

    @DnAttribute(index = 0)
    @org.springframework.ldap.odm.annotations.Transient
    private String ou;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor/getter/setter được bổ sung trong ứng dụng.
}
~~~

Nếu `uid=lan` và `ou=engineering`, DN tính toán dự kiến là:

~~~text
uid=lan,ou=engineering,ou=people
~~~

DN đầy đủ:

~~~text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
~~~

Tài liệu Spring LDAP minh họa `index=0` cho thành phần RDN **sát base nhất** và `index=1` cho thành phần nằm bên trái nó. `@Transient` cho trường `ou` trong ví dụ khiến nó chỉ được dùng để dựng DN, **không** ghi thành thuộc tính `ou` trên entry người dùng. Có thể giữ `ou` là một thuộc tính của entry nếu schema và nghiệp vụ cho phép, nhưng cần khai báo mapping phù hợp.

**Điều kiện quan trọng:** entry cha `ou=engineering,ou=people,dc=example,dc=org` phải tồn tại trước khi tạo Lan. `@Entry` và `@DnAttribute` không tự tạo OU cha. Ngoài ra, khi search:

- `ONELEVEL` dưới `ou=people` chỉ tìm OU con trực tiếp, **không** tìm Lan/Mai ở tầng sâu hơn.
- `SUBTREE` dưới `ou=people` có thể tìm cả entry ở các OU con (nếu filter phù hợp và ACL cho phép).
- Khi tổ chức đổi cấu trúc OU, hãy thiết kế quy trình Move/Rename; không chỉ sửa một chuỗi trong Java rồi giả định mọi liên kết `member` đã được cập nhật.

Với một cây nhiều OU phức tạp hoặc đổi nhánh thường xuyên, việc tự xây DN có thể dễ kiểm soát hơn việc yêu cầu ODM tính mọi trường hợp. Cần so sánh hai cách qua kiểm thử tích hợp.

## 10. Thay đổi base của entity có di chuyển dữ liệu không?

**Không.** Sửa annotation:

~~~java
@Entry(base = "ou=staff", objectClasses = { /* ... */ })
~~~

không tạo OU mới và không tự di chuyển các entry cũ khỏi `ou=people`. Nó chỉ thay đổi cách ứng dụng mô tả/tính toán vị trí entry.

Nếu nhân viên đã được lưu tại `ou=people` nhưng deploy code mới chỉ tìm dưới `ou=staff`, có thể xuất hiện:

- Query/repository không tìm thấy entry cũ.
- Các thao tác create mới đi vào OU khác.
- `NameNotFoundException` nếu `ou=staff` chưa tồn tại.
- Dữ liệu cùng người dùng nằm ở hai nhánh khác nhau, hoặc `uid` trùng tại các DN khác nhau.
- Nhóm có `member` trỏ tới DN cũ, còn hệ thống tìm theo base mới không nhìn thấy người dùng.

Khi chuyển từ `ou=people` sang `ou=staff`, cần một kế hoạch:

1. Tạo OU đích theo schema và ACL.
2. Xác định DN nguồn/đích của từng entry.
3. Dùng LDAP **Modify DN / Rename / Move** theo khả năng server và quyền liên quan.
4. Kiểm tra tham chiếu trong nhóm `member` hoặc thuộc tính DN khác; tính năng cập nhật tham chiếu không được mọi directory bật mặc định.
5. Kiểm tra các hệ thống khác đang lưu DN cũ.
6. Chuyển cấu hình ứng dụng và quan sát kết quả Search/CRUD.
7. Có khả năng khôi phục hoặc đối soát những entry chuyển dở dang.

Một bước thay đổi annotation **không phải migration dữ liệu**. Đừng coi thay base giống đổi tên table trong cơ sở dữ liệu quan hệ.

## 11. So sánh cách tổ chức base giữa nhiều entity

Một ứng dụng có thể có cả người dùng và nhóm:

~~~java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
class PersonEntry {
    @Id Name dn;
    // ...
}

@Entry(
    base = "ou=groups",
    objectClasses = { "top", "groupOfNames" }
)
class GroupEntry {
    @Id Name dn;
    // ...
}
~~~

Cả hai dùng chung `ContextSource.base=dc=example,dc=org`.

| Entity | `@Entry(base)` | Ví dụ DN đầy đủ |
| --- | --- | --- |
| `PersonEntry` | `ou=people` | `uid=lan,ou=people,dc=example,dc=org` |
| `GroupEntry` | `ou=groups` | `cn=engineering,ou=groups,dc=example,dc=org` |

Điều này giúp một module ánh xạ **entry phân cấp** mà vẫn có một cấu hình kết nối chung. Tuy nhiên, entity nhóm phải dùng schema riêng (`groupOfNames` yêu cầu `cn` và ít nhất một `member`); không thể gắn `inetOrgPerson` cho nhóm chỉ vì muốn tái sử dụng lớp Java.

### DN tham chiếu trong nhóm phải là DN đầy đủ

Trong `groupOfNames`, thuộc tính `member` chứa DN thành viên:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
~~~

Nếu dùng `LdapTemplate` với `ContextSource.base=dc=example,dc=org`, DN **để sửa nhóm** có thể là `cn=engineering,ou=groups`. Nhưng **giá trị của thuộc tính `member`** phải là `uid=lan,ou=people,dc=example,dc=org`.

Đây là ngoại lệ quan trọng của quy tắc “dùng DN tương đối”: **DN nằm trong giá trị thuộc tính hoặc dùng khi Bind thường phải được biểu diễn đầy đủ**, vì LDAP server cần hiểu đối tượng được tham chiếu trong toàn cây.

## 12. An toàn khi làm việc với base và DN

### 12.1. Đừng để client tự quyết định nhánh LDAP

Ví dụ request không nên được chấp nhận trực tiếp:

~~~json
{
  "uid": "lan",
  "dn": "uid=lan,ou=admins,dc=example,dc=org",
  "objectClasses": ["inetOrgPerson", "otherClass"]
}
~~~

Client nên gửi ID nghiệp vụ, còn service quyết định nhánh cho phép:

~~~java
Name safeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", validatedUid)
        .build();
~~~

`@Entry(base)` **không ngăn người dùng có quyền LDAP truy cập nhánh khác**; để bảo vệ dữ liệu, phải dùng ACL trên server và kiểm tra authorization của người gọi API. Đừng dựa riêng vào đường dẫn trong annotation.

### 12.2. DN escaping và filter escaping không giống nhau

- DN có cú pháp RFC 4514; dùng `LdapNameBuilder` hoặc `LdapName`.
- Search filter có cú pháp RFC 4515; dùng `LdapQueryBuilder`, `EqualsFilter` hoặc API escape phù hợp.
- `uid=lan*` trong filter là một tình huống khác với DN chứa ký tự `*` literal.
- Chỉ chấp nhận tên thuộc tính/filter từ danh sách cho phép; không nối nguyên biểu thức do HTTP client cung cấp.

Ví dụ query đúng cách:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(inputUid);
~~~

Tránh:

~~~java
// KHÔNG dùng với dữ liệu đầu vào không tin cậy:
String rawFilter = "(uid=" + inputUid + ")";
~~~

### 12.3. TLS và tài khoản kết nối

- Dùng **LDAPS** hoặc **StartTLS thành công trước Simple Bind**.
- Kiểm tra chuỗi chứng chỉ, CA tin cậy và hostname.
- Không commit mật khẩu Bind lên source control.
- Tài khoản chỉ đọc dùng cho tra cứu; quyền Add/Modify/Delete chỉ cấp khi API thực sự cần.
- Nếu có nhiều OU với chính sách bảo mật khác nhau, cấu hình ACL theo nhánh, không dùng `@Entry(base)` như ranh giới bảo mật.
- Đừng log DN nhạy cảm hoặc giá trị attributes của hồ sơ khi không cần.

## 13. Lỗi phổ biến khi cấu hình base

| Triệu chứng | Khả năng gây lỗi | Cách kiểm tra |
| --- | --- | --- |
| `No Such Object (32)` | Base DN sai hoặc OU chưa có. | Dùng `ldapsearch` kiểm tra naming context và entry cha. |
| Search trả rỗng | Search base/scope sai, LDAP filter không khớp hoặc ACL ẩn dữ liệu. | So sánh `base` + `scope` + filter với CLI, cùng Bind DN. |
| DN bị lặp `ou=people` hoặc `dc=example,dc=org` | Ghép thủ công DN đầy đủ dù ContextSource/ODM đã thêm base. | Phân biệt DN tính bởi `@DnAttribute` và DN gán tường minh. |
| Repository tìm không ra entry cũ sau deploy | `@Entry(base)` đổi nhưng entry thực vẫn nằm nhánh cũ. | Search trực tiếp và lập kế hoạch Move/Rename. |
| Tạo entry thất bại với `objectClassViolation` | Thiếu `cn`/`sn` hoặc object class mapping không đúng schema. | Kiểm tra LDIF và metadata `@Entry(objectClasses)`. |
| `Insufficient Access Rights (50)` | Tài khoản Bind không được phép đọc/ghi nhánh đó. | Kiểm tra ACL bằng đúng service account. |
| `NameAlreadyBoundException` | DN đã tồn tại; có thể do chạy fixture nhiều lần. | Search theo DN rồi xử lý conflict. |
| Đọc nhóm không ra thành viên | Dùng DN tương đối làm giá trị `member` hoặc thiếu quyền đọc. | Kiểm tra DN đầy đủ trong thuộc tính `member`. |
| `findByUid` trả nhiều kết quả | `uid` không được ràng buộc duy nhất trong phạm vi. | Thiết kế chính sách uniqueness và xử lý trùng dữ liệu. |
| Tìm ở `ONELEVEL` không thấy user trong OU con | Entry ở tầng sâu hơn search base. | Dùng `SUBTREE` có kiểm soát hoặc chuyển base phù hợp. |
| Đổi `@Entry(base)` rồi tưởng entry tự chuyển | Annotation không thực hiện migration. | Tạo kế hoạch Modify DN và kiểm tra tham chiếu nhóm. |
| TLS thất bại | CA không tin cậy hoặc hostname không khớp. | Sửa chứng chỉ/truststore, không tắt xác minh TLS. |

## 14. Thực hành kiểm tra với ldapsearch

Giả định một OpenLDAP test server có naming context `dc=example,dc=org`, nhánh `ou=people` và entry Lan từ mục 2. Dùng tài khoản thử nghiệm có quyền đọc đúng nhánh, và LDAPS đã có chứng chỉ hợp lệ.

### 14.1. Kiểm tra naming context

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn objectClass
~~~

Nếu không có entry gốc, các thao tác dưới `ou=people` cũng không thể hoạt động theo cấu trúc dự kiến.

### 14.2. Kiểm tra entry cha

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s base \
  "(objectClass=organizationalUnit)" dn ou
~~~

Kỳ vọng có entry `ou=people,dc=example,dc=org`. Việc có tên nhánh trong `@Entry(base)` không thể thay thế thao tác tạo OU cha trên server.

### 14.3. Kiểm tra người dùng trong OU

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn objectClass uid cn sn mail
~~~

Kỳ vọng tìm được `uid=lan,ou=people,dc=example,dc=org`. Nếu LDAP CLI tìm được nhưng repository không thấy, tập trung kiểm tra **ContextSource base**, `@Entry(base)`, `@Id`, search base/scope và cách ODM xây DN trước khi nghi ngờ dữ liệu mất.

Lệnh `-W` yêu cầu nhập mật khẩu theo lời nhắc, tránh ghi mật khẩu trên dòng lệnh. Không dùng dữ liệu thật và không vô hiệu hóa xác minh TLS trong bài lab.

## 15. Ma trận kiểm thử tích hợp

Một test tốt phải xác minh **DN trên directory**, không chỉ assert field Java.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| ODM tạo trong base đúng | `@Entry(base="ou=people")` + `@DnAttribute(index=0)` với `uid=lan`. | Entry ở `uid=lan,ou=people,dc=example,dc=org`. |
| Parent OU không tồn tại | Chưa có `ou=people`. | Tạo entry thất bại; ứng dụng báo lỗi có kiểm soát. |
| Thiếu thuộc tính schema bắt buộc | Không có `sn` khi tạo `inetOrgPerson`. | Directory từ chối theo schema. |
| Query base đúng | `LdapQueryBuilder.base("ou=people")`, scope ONELEVEL. | Tìm user trực tiếp dưới OU này. |
| Query scope quá hẹp | User nằm dưới `ou=engineering,ou=people`. | ONELEVEL không tìm; SUBTREE có thể tìm. |
| DN tương đối với context | Truy cập `uid=lan,ou=people`. | Đúng entry trong naming context. |
| DN đầy đủ truyền vào vị trí DN tương đối | Truy cập bằng `uid=lan,ou=people,dc=example,dc=org` khi context đã có base. | Không giả định framework tự cắt base; test để phát hiện lỗi lặp. |
| `@Entry(base)` và DN explicit không nhất quán | Gán `@Id` thủ công không đúng nhánh. | Phát hiện lỗi trước khi ghi nhầm entry. |
| `@DnAttribute` nhiều cấp | Có `ou=engineering` và `uid=lan` trong DN. | DN tính được ở `uid=lan,ou=engineering,ou=people` tương đối với context. |
| Đổi annotation nhưng không di chuyển dữ liệu | Chỉ sửa base từ people sang staff. | Entry cũ vẫn ở people; không tự tạo migration. |
| Group chứa `member` | Tham chiếu Lan từ Engineering. | Giá trị `member` là DN đầy đủ. |
| Service account chỉ đọc | Thử `save` hoặc `create`. | Directory từ chối thao tác ghi theo ACL. |
| Tên người dùng chứa ký tự đặc biệt | Gọi builder và filter với input test. | Escaping đúng, không chèn RDN hoặc filter ngoài ý muốn. |
| TLS sai chứng chỉ | Cấu hình CA/hostname không hợp lệ. | Kết nối thất bại; không hạ cấp về plaintext. |

### Ví dụ kiểm tra từ JUnit

Có thể dùng Spring Boot Test với một LDAP directory test đã chuẩn bị entry. Ví dụ sau chỉ đọc dữ liệu, không sửa dữ liệu dùng chung:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

@SpringBootTest
class EntityBaseIntegrationTest {

    @Autowired LdapTemplate ldapTemplate;

    @Test
    void findsPersonInExpectedOu() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("uid").is("lan");

        List<DirectoryPerson> people =
                ldapTemplate.find(query, DirectoryPerson.class);

        assertEquals(1, people.size());
        assertEquals("lan", people.get(0).getUid());
        assertEquals("Nguyen Thi Lan", people.get(0).getFullName());
    }
}
~~~

Kiểm thử tích hợp khác nên tạo người dùng với `@DnAttribute`, sau đó gọi `ldapsearch` hoặc lookup để xác định **DN đầy đủ thực tế**. Điều này đặc biệt quan trọng nếu cùng ứng dụng sử dụng nhiều context/base khác nhau.

## 16. Cách chọn chiến lược base trong dự án thật

Có ba hướng thường gặp:

| Thiết kế | Ưu điểm | Thận trọng |
| --- | --- | --- |
| Một ContextSource base chung, nhiều `@Entry(base)` | Dễ quản lý nhiều entity người dùng/nhóm trong cùng domain. | Cần hiểu DN tính toán và cách repository/ODM sử dụng base. |
| ContextSource base đến đúng OU ứng dụng | DN tương đối ngắn; phù hợp service chỉ dùng một nhánh. | Khó thao tác nhóm/nhánh khác với cùng context; chú ý DN đầy đủ cho tham chiếu. |
| ContextSource base chung + DN tường minh bằng `LdapNameBuilder` | Linh hoạt khi phân cấp, tạo và di chuyển entry. | Mã service phải giữ quy ước DN nhất quán; dễ trùng base nếu ghép sai. |

Lựa chọn phụ thuộc mô hình DIT, quyền truy cập, số loại entry và khả năng thay đổi OU. Một quy tắc hữu ích là chọn **một gốc ổn định ở ContextSource**, khai báo **gốc của từng entity rõ ràng**, rồi chỉ dùng **một chiến lược tính DN** cho từng use case.

## 17. Bài tập củng cố

**Bài 1 – Tính DN.** Với `spring.ldap.base=dc=example,dc=org`, `@Entry(base="ou=people")` và `uid=mai` làm RDN, hãy viết DN tương đối và DN đầy đủ. Đáp án: `uid=mai,ou=people` và `uid=mai,ou=people,dc=example,dc=org`.

**Bài 2 – Phát hiện sai base.** Một ứng dụng đã có `ContextSource.base=dc=example,dc=org` nhưng truyền `uid=lan,ou=people,dc=example,dc=org` vào một operation cần DN tương đối. Giải thích vì sao cần kiểm tra việc lặp gốc và sửa bằng DN builder.

**Bài 3 – Hai entity.** Tạo `@Entry(base="ou=groups")` cho entry `groupOfNames` và `@Entry(base="ou=people")` cho người dùng. Nêu DN dùng thao tác trên nhóm và DN đầy đủ cần ghi trong `member`.

**Bài 4 – OU nhiều cấp.** Đặt Lan ở `uid=lan,ou=engineering,ou=people,dc=example,dc=org`. Chọn `@DnAttribute` index phù hợp và so sánh kết quả search ONELEVEL/SUBTREE từ `ou=people`.

**Bài 5 – Migration.** Khi đổi nhánh từ `ou=people` sang `ou=staff`, thiết kế checklist chuyển entry và kiểm tra các nhóm tham chiếu bằng DN. Vì sao chỉ sửa annotation không đủ?

**Bài 6 – Security.** Với API nhận `uid` từ client, xây DN bằng `LdapNameBuilder` và xây Search filter bằng `LdapQueryBuilder`. Giải thích vai trò của ACL LDAP và authn/authz HTTP.

## 18. Câu hỏi tự ôn tập

1. `@Entry(base="ou=people")` có tạo entry `ou=people` trên directory không?
2. `spring.ldap.base` và `@Entry(base)` khác nhau về phạm vi áp dụng như thế nào?
3. `@Id` phải dùng kiểu dữ liệu gì? Nó biểu diễn DN hay `uid`?
4. Khi `@DnAttribute(index=0)` được khai báo cho `uid`, ODM dùng nó làm gì?
5. Vì sao `@DnAttribute` không tự khiến trường Java bị bỏ qua khi ghi thuộc tính LDAP?
6. Khi nào cần `@Transient` cho thành phần DN?
7. Với `ContextSource.base=dc=example,dc=org`, DN nào dùng cho thao tác tìm theo entry tương đối?
8. Vì sao `groupOfNames.member` phải chứa DN đầy đủ?
9. Vì sao `SearchScope.ONELEVEL` không tìm thấy entry ở OU cháu?
10. Sửa `@Entry(base)` có tự động Move/Rename entry cũ không?
11. Cần kiểm tra những gì khi `ldapsearch` thấy entry nhưng repository không tìm được?
12. Vì sao `@Entry(base)` không thay thế ACL và xác thực người gọi API?

**Ghi nhớ:** `spring.ldap.base` đặt gốc cho **ContextSource**; `@Entry(base)` mô tả gốc của **một lớp entity** và tham gia tính DN qua ODM; `@Id` biểu diễn DN của **một entry**. Với ví dụ người dùng Lan: **`uid=lan` + `ou=people` + `dc=example,dc=org`** tạo ra DN đầy đủ `uid=lan,ou=people,dc=example,dc=org`. Hãy tránh nối chuỗi DN thủ công, không nhầm search base với Bind DN, và kiểm chứng ánh xạ thực tế bằng directory thử nghiệm.

### Tài liệu tham khảo

- [Spring LDAP – Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@DnAttribute`, `@Attribute` và cách tính DN.
- [Spring LDAP – @Entry API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Entry.html): ý nghĩa của thuộc tính `base` và `objectClasses`.
- [Spring LDAP – Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource.base`, DN tương đối/đầy đủ và cấu hình Bind DN.
- [Spring Data LDAP – Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository với `@Id` kiểu `Name`.
- [Spring Data LDAP – Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html): ví dụ entity `@Entry(base)` và truy cập repository.
- [RFC 4512 – LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DIT, DN, schema và object class.
- [RFC 4514 – LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): DN/RDN và escaping.
- [RFC 4515 – LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): filter và escaping giá trị tìm kiếm.
