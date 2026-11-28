# Đưa LdapQuery vào findOne và findAll

Spring Data LDAP cung cấp hai phương thức repository nhận trực tiếp một đối tượng `LdapQuery`: `findOne(LdapQuery)` và `findAll(LdapQuery)`. Cách này hữu ích khi điều kiện tìm kiếm được quyết định ở runtime, chẳng hạn người dùng nhập UID, bộ lọc theo phòng ban thay đổi theo màn hình, hoặc service cần giới hạn tìm kiếm vào một nhánh cụ thể của directory.

`LdapQuery` mô tả **cách tìm**: base DN, search scope, LDAP filter, danh sách attribute cần trả về, count limit và time limit. Repository dùng query đó để tìm entry rồi ánh xạ kết quả thành entity ODM đã khai báo bằng `@Entry`, `@Id` và `@Attribute`.

Hai phương thức có mục đích khác nhau:

- `findOne(query)` dùng khi nghiệp vụ mong đợi **không có hoặc đúng một** entry. Kết quả có kiểu `Optional<T>`; nếu nhiều entry cùng khớp, Spring Data ném `IncorrectResultSizeDataAccessException`.
- `findAll(query)` dùng khi nghiệp vụ chấp nhận **không, một hoặc nhiều** entry. Kết quả là `List<T>`; không có kết quả thì danh sách rỗng.

Bài thuộc chương **LDAP Repository** của mô-đun `SPRING_DATA_LDAP`. Chúng ta sẽ tạo repository, xây query bằng `LdapQueryBuilder`, chọn base/scope/filter, dùng cả hai phương thức, hiểu giới hạn cardinality, bảo vệ filter khỏi LDAP injection và kiểm thử trên directory có dữ liệu thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `LdapQuery` trong Spring Data LDAP.
2. Phân biệt `LdapRepository` với `CrudRepository` khi cần truyền query động.
3. Khai báo entity ODM có DN, objectClass và các attribute cần ánh xạ.
4. Tạo `LdapQuery` bằng `LdapQueryBuilder.query()`.
5. Chọn search base và `SearchScope` đúng với cây DIT.
6. Kết hợp điều kiện `is`, `like`, `isPresent`, `gte`, `lte`, `and` và `or`.
7. Dùng `findOne(LdapQuery)` cho truy vấn có tối đa một kết quả.
8. Dùng `findAll(LdapQuery)` cho truy vấn trả về danh sách.
9. Hiểu hành vi khi không có kết quả, có nhiều kết quả hoặc directory trả lỗi giới hạn.
10. Tránh LDAP injection khi điều kiện có dữ liệu do người dùng nhập.
11. Dùng `attributes`, `countLimit` và `timeLimit` có chủ đích.
12. Hiểu vì sao repository LDAP không hỗ trợ paging/sorting như repository cơ sở dữ liệu quan hệ.
13. Viết integration test cho kết quả đơn, nhiều kết quả, rỗng và filter không an toàn.

## 2. LdapQuery là gì?

`LdapQuery` là một mô tả truy vấn LDAP. Nó không tự kết nối server và không chứa entity kết quả. Repository nhận query, thực hiện Search thông qua Spring LDAP rồi dùng ODM để ánh xạ các entry phù hợp thành kiểu entity của repository.

Một query có thể mô tả các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Base DN | Vị trí bắt đầu Search trong DIT | `ou=people` |
| Search scope | Độ sâu của Search | `ONELEVEL` |
| Filter | Điều kiện entry cần khớp | `(objectClass=inetOrgPerson)` |
| Attributes | Các attribute server cần trả về | `uid`, `cn`, `mail` |
| Count limit | Số entry tối đa client yêu cầu | `100` |
| Time limit | Thời gian tối đa cho Search | `2000` mili giây |

Có thể hình dung:

~~~mermaid
flowchart TD
    A["LdapQueryBuilder"] --> B["LdapQuery"]
    B --> C["LdapRepository.findOne(query)"]
    B --> D["LdapRepository.findAll(query)"]
    C --> E["LDAP Search + ODM mapping"]
    D --> E
    E --> F["Optional<Entity>"]
    E --> G["List<Entity>"]
~~~

Query là đối tượng có thể được tạo trong service dựa trên tham số runtime. Ví dụ cùng một repository có thể tìm theo UID, email, họ tên hoặc nhóm mà không cần viết một method repository mới cho mỗi tổ hợp điều kiện.

## 3. Repository phải mở rộng LdapRepository

Để nhận tham số `LdapQuery` trực tiếp, interface cần mở rộng `org.springframework.data.ldap.repository.LdapRepository`.

~~~java
package com.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;

import com.example.directory.model.DirectoryPerson;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

`LdapRepository<T>` là repository đặc thù cho LDAP và mặc định ID có kiểu `javax.naming.Name`. Nó cung cấp các method CRUD kế thừa cùng hai overload LDAP-specific:

~~~java
Optional<T> findOne(LdapQuery ldapQuery);

List<T> findAll(LdapQuery ldapQuery);
~~~

Nếu interface chỉ mở rộng `CrudRepository`, bạn có các thao tác CRUD thông thường nhưng không có hai overload `findOne(LdapQuery)` và `findAll(LdapQuery)` này.

### 3.1. Bật repository scanning

Ví dụ cấu hình Java:

~~~java
package com.example.directory.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
        basePackages = "com.example.directory.repository"
)
public class DirectoryRepositoryConfiguration {
}
~~~

Spring Data LDAP quét package đã khai báo và tạo bean cho các interface repository. Ứng dụng cũng phải có `ContextSource` và `LdapTemplate` được cấu hình. Theo quy ước mặc định, repository sử dụng bean `LdapTemplate` có tên `ldapTemplate`; nếu ứng dụng có nhiều template/directory, cần cấu hình tham chiếu đúng template cho repository theo phiên bản đang dùng.

Ví dụ trên giả định connection bean đã được cấu hình ở phần khởi tạo ứng dụng. Hãy dùng endpoint, Bind DN, TLS và ACL phù hợp với môi trường; không đưa mật khẩu thật vào source code.

## 4. Entity ODM mà repository quản lý

Spring Data LDAP repository dùng Object-Directory Mapping (ODM) của Spring LDAP. Entity phải có annotation trong package `org.springframework.ldap.odm.annotations`.

Ví dụ directory có entry người dùng:

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

Entity tương ứng:

~~~java
package com.example.directory.model;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
})
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getCommonName() {
        return commonName;
    }

    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Các annotation quan trọng:

- `@Entry` khai báo những objectClass mà entity đại diện.
- `@Id` ánh xạ DN của entry vào field kiểu `javax.naming.Name`.
- `@Attribute` ánh xạ field Java vào tên attribute LDAP.
- `@DnAttribute` có thể ánh xạ thành phần RDN từ DN vào field Java.
- `@Transient` đánh dấu field không được ODM ánh xạ thành LDAP attribute.

**Lưu ý về objectClass:** entry thực tế có thể chứa nhiều objectClass kế thừa và cấu trúc. Các objectClass mà ODM cần quản lý phải được khai báo phù hợp trong `@Entry`. Nếu entity cần ánh xạ attribute thuộc `inetOrgPerson`, hãy khai báo cả objectClass liên quan như ví dụ trên. Không dùng annotation `@Id` của Spring Data Commons thay cho annotation `@Id` của Spring LDAP ODM.

## 5. Tạo LdapQuery bằng LdapQueryBuilder

Import builder:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;
~~~

Một query đơn giản tìm người dùng theo UID:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan");
~~~

Filter logic tương ứng:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

Đây là Search bắt đầu tại `ou=people` và chỉ xét entry con trực tiếp trong OU đó. QueryBuilder cho phép đặt search parameters trước, sau đó khai báo filter.

### 5.1. Các giá trị mặc định

| Thuộc tính | Mặc định/ý nghĩa |
| --- | --- |
| `base` | DN rỗng tương đối với root đã cấu hình trong `ContextSource`. |
| `searchScope` | `SUBTREE` nếu dùng mặc định Spring LDAP. |
| `countLimit` | `0` nghĩa là không đặt giới hạn từ query. |
| `timeLimit` | `0` nghĩa là không đặt giới hạn từ query. |
| `attributes` | `null` nghĩa là yêu cầu các attribute mặc định/toàn bộ theo Search controls. |
| Filter | **Bắt buộc** phải có. |

Nếu không khai báo base, Search có thể bắt đầu từ root của `ContextSource` và scope mặc định có thể quét toàn bộ subtree. Với ứng dụng thực tế, nên chỉ định base và scope để tránh truy vấn rộng ngoài ý muốn.

### 5.2. Thứ tự xây query

Hãy đặt base, scope, attributes và giới hạn trước khi bắt đầu filter:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("objectClass", "uid", "cn", "sn", "mail")
        .countLimit(100)
        .timeLimit(2_000)
        .where("objectClass").is("inetOrgPerson")
        .and("sn").is("Nguyen");
~~~

Sau khi bắt đầu khai báo filter bằng `where` hoặc `filter`, QueryBuilder không cho phép quay lại thay đổi các tham số Search không phải filter. Hãy xây query theo trình tự: **base/scope/projection/limits → filter**.

### 5.3. Base DN và ContextSource base

Giả sử `ContextSource` có:

~~~text
base = dc=example,dc=org
~~~

Thì `base("ou=people")` trong `LdapQuery` là DN tương đối với base này. Search bắt đầu tại:

~~~text
ou=people,dc=example,dc=org
~~~

Không ghép lại `dc=example,dc=org` vào query base nếu `ContextSource` đã áp dụng nó. Ngược lại, nếu ContextSource không cấu hình base, query cần dùng DN đầy đủ theo cấu hình thực tế.

`@Entry(base = "ou=people")` là metadata về root DN cho entity ODM. `LdapQuery.base(...)` xác định search base của một truy vấn cụ thể. Hai khái niệm liên quan nhưng có vai trò khác nhau; cần giữ nhất quán để tránh search nhầm nhánh hoặc tạo DN sai.

## 6. SearchScope: OBJECT, ONELEVEL và SUBTREE

`SearchScope` quyết định độ sâu LDAP Search:

| Scope | Phạm vi | Trường hợp sử dụng |
| --- | --- | --- |
| `OBJECT` | Chỉ entry tại chính base DN | Kiểm tra một entry đã biết DN. |
| `ONELEVEL` | Các entry con trực tiếp của base | Liệt kê user trực tiếp trong `ou=people`. |
| `SUBTREE` | Base và toàn bộ descendants | Tìm người dùng trong các OU con/phòng ban. |

Minh họa:

~~~text
ou=people
├── uid=lan
├── uid=minh
└── ou=engineering
    ├── uid=mai
    └── uid=nam
~~~

- `OBJECT` tại `ou=people` chỉ xét entry OU.
- `ONELEVEL` tại `ou=people` xét Lan, Minh và OU engineering.
- `SUBTREE` tại `ou=people` xét cả Lan, Minh, OU engineering, Mai và Nam.

### Chọn scope theo nghiệp vụ

Nếu tìm user trực tiếp trong OU người dùng, `ONELEVEL` thường rõ ràng hơn `SUBTREE`. Nếu tổ chức phân cấp nhiều OU và cần tìm mọi user bên dưới, dùng `SUBTREE` cùng filter đủ hẹp.

Không chọn `SUBTREE` chỉ vì “dễ tìm thấy dữ liệu”. Search rộng có thể:
- Tăng tải directory.
- Trả về entry từ nhánh không liên quan.
- Làm lộ dữ liệu vượt quyền ứng dụng.
- Gặp size limit hoặc time limit sớm hơn.

## 7. Dùng findOne(LdapQuery)

`findOne` phù hợp khi filter được kỳ vọng khớp tối đa một entry, chẳng hạn UID đã được quản trị bảo đảm duy nhất trong phạm vi tìm kiếm.

~~~java
import java.util.Optional;

public Optional<DirectoryPerson> findByUid(String uid) {
    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.ONELEVEL)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

    return personRepository.findOne(ldapQuery);
}
~~~

Có thể sử dụng kết quả:

~~~java
Optional<DirectoryPerson> person = findByUid("lan");

if (person.isPresent()) {
    System.out.println(person.get().getCommonName());
} else {
    System.out.println("Không tìm thấy người dùng");
}
~~~

Hoặc dùng các thao tác của `Optional`:

~~~java
DirectoryPerson person = findByUid("lan")
        .orElseThrow(() ->
                new PersonNotFoundException("Person not found"));
~~~

### 7.1. Ba trường hợp của findOne

| Số entry khớp | Kết quả |
| ---: | --- |
| 0 | `Optional.empty()` theo hợp đồng Optional của repository. |
| 1 | `Optional.of(entity)`. |
| Lớn hơn 1 | `IncorrectResultSizeDataAccessException`. |

`findOne` không phải “lấy entry đầu tiên bất kỳ”. Nó thể hiện kỳ vọng có tối đa một kết quả. Nếu dữ liệu có nhiều entry cùng khớp, đây là dấu hiệu filter quá rộng hoặc dữ liệu vi phạm giả định uniqueness của nghiệp vụ.

### 7.2. Vì sao không nên dùng countLimit(1) để giả lập findOne?

Ví dụ không phù hợp khi cần kiểm tra tính duy nhất:

~~~java
LdapQuery queryWithLimit = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(1)
        .where("mail").is(email);
~~~

Nếu nhiều entry có cùng email, count limit có thể giới hạn số entry trả về trước khi ứng dụng phát hiện có nhiều kết quả. Khi đó bạn có thể không nhận được lỗi cardinality mà chỉ thấy một entry.

Hãy xây filter có tính chọn lọc và bảo đảm uniqueness bằng schema/policy hoặc cơ chế quản trị dữ liệu. Không dựa vào giới hạn kết quả để che dữ liệu trùng.

### 7.3. Tìm theo thuộc tính có thể trùng

Ví dụ `cn` (common name) thường không duy nhất. Một directory có thể có nhiều người tên “Nguyen Van An”. Truy vấn:

~~~java
LdapQuery queryByCommonName = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("cn").is("Nguyen Van An");
~~~

Nếu nghiệp vụ muốn hiển thị tất cả người cùng tên, dùng `findAll`. Nếu nghiệp vụ muốn một người cụ thể, bổ sung định danh duy nhất như UID hoặc employee ID đã được quản lý uniqueness.

## 8. Dùng findAll(LdapQuery)

`findAll` phù hợp khi truy vấn có thể trả về nhiều entry:

~~~java
public List<DirectoryPerson> findBySurname(String surname) {
    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("sn").is(surname);

    return personRepository.findAll(ldapQuery);
}
~~~

Nếu không có entry khớp, method trả về danh sách rỗng. Có thể xử lý:

~~~java
List<DirectoryPerson> people = findBySurname("Nguyen");

if (people.isEmpty()) {
    System.out.println("Không có kết quả");
} else {
    people.forEach(person ->
            System.out.println(person.getUid()));
}
~~~

### 8.1. Khi nào dùng findAll thay cho findOne?

| Nhu cầu | Phương thức |
| --- | --- |
| Tra cứu một người theo UID duy nhất | `findOne` |
| Tìm mọi người có cùng họ | `findAll` |
| Tìm mọi user thuộc OU con của một phòng ban | `findAll` |
| Kiểm tra email có bị dùng bởi nhiều entry | `findAll` hoặc `findOne` kèm xử lý duplicate |
| Tìm mọi group có chứa một DN thành viên | `findAll` |
| Đảm bảo chỉ có một entry thỏa điều kiện | `findOne` |

### 8.2. Thứ tự kết quả

LDAP Search không tự bảo đảm thứ tự kết quả theo tên, UID hoặc thời gian tạo. `findAll` trả về một `List` nhưng không nên mặc định phần tử đầu tiên là người mới nhất hoặc có ưu tiên cao nhất.

Không viết logic:

~~~java
DirectoryPerson first = repository.findAll(query).get(0);
~~~

rồi xem phần tử đầu là kết quả đúng nếu filter có thể khớp nhiều entry. Nếu nghiệp vụ cần một entry duy nhất, dùng `findOne` với điều kiện duy nhất. Nếu cần sắp xếp, repository LDAP không cung cấp sorting như SQL; hãy chọn cơ chế phù hợp ở tầng truy vấn/server và kiểm chứng hỗ trợ của directory.

## 9. Kết hợp điều kiện filter

`LdapQueryBuilder` hỗ trợ các điều kiện filter phổ biến.

| Cú pháp | LDAP filter | Ý nghĩa |
| --- | --- | --- |
| `where("uid").is("lan")` | `(uid=lan)` | So sánh bằng. |
| `where("cn").like("Lan*")` | `(cn=Lan*)` | Match theo wildcard. |
| `where("mail").isPresent()` | `(mail=*)` | Attribute tồn tại. |
| `where("sn").not().is("Nguyen")` | `(!(sn=Nguyen))` | Phủ định điều kiện. |
| `where("employeeNumber").gte("1000")` | `(employeeNumber>=1000)` | So sánh lớn hơn/bằng theo matching rule. |
| `where("employeeNumber").lte("1999")` | `(employeeNumber<=1999)` | So sánh nhỏ hơn/bằng theo matching rule. |

### 9.1. Kết hợp AND

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson")
        .and("departmentNumber").is("ENG")
        .and("employeeType").is("Employee");
~~~

Filter logic:

~~~text
(&(objectClass=inetOrgPerson)
  (departmentNumber=ENG)
  (employeeType=Employee))
~~~

### 9.2. Kết hợp OR

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and(query()
                .where("uid").is("lan")
                .or("uid").is("minh"));
~~~

Filter logic tương đương:

~~~text
(&(objectClass=inetOrgPerson)
  (|(uid=lan)(uid=minh)))
~~~

### 9.3. Tìm theo tiền tố hoặc wildcard

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like("Nguyen*");
~~~

`like` cho phép sử dụng wildcard `*`. Nếu giá trị tìm kiếm do người dùng nhập và nghiệp vụ chỉ muốn so khớp chính xác, hãy dùng `is`. Chỉ dùng `like` khi ứng dụng chủ động cung cấp chức năng tìm kiếm theo mẫu.

### 9.4. Kiểm tra attribute tồn tại

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("mail").isPresent();
~~~

Filter này hữu ích khi cần tìm các entry có email. Attribute tồn tại không đồng nghĩa giá trị hợp lệ hoặc duy nhất; validation nghiệp vụ vẫn cần được thực hiện riêng.

### 9.5. Lưu ý với gte/lte

`gte` và `lte` tạo filter LDAP `>=` và `<=`. Cách so sánh phụ thuộc syntax và matching rule của attribute trên server. Nếu attribute được lưu dưới dạng chuỗi, không tự giả định directory so sánh số học như Java:

~~~text
"100" và "20"
~~~

Có thể được so sánh theo quy tắc chuỗi thay vì số nguyên nếu schema không định nghĩa matching rule số phù hợp. Hãy xác minh schema và matching rule trước khi dùng các điều kiện khoảng cho số, ngày hoặc version.

## 10. Filter an toàn và chống LDAP injection

Một query thường nhận dữ liệu từ HTTP request, message hoặc form. Giá trị như UID, email, tên người dùng phải được đưa vào filter an toàn.

### 10.1. Dùng where().is() với giá trị động

~~~java
public List<DirectoryPerson> searchByName(String name) {
    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("cn").is(name);

    return personRepository.findAll(ldapQuery);
}
~~~

`where("cn").is(name)` tạo điều kiện filter bằng builder; giá trị được encode để bảo vệ filter. Tên attribute `cn` phải do ứng dụng định nghĩa, không lấy tùy ý từ client.

### 10.2. Không nối chuỗi input vào filter

Không viết:

~~~java
String filter = "(uid=" + uidFromRequest + ")";

LdapQuery ldapQuery = query()
        .base("ou=people")
        .filter(filter);
~~~

Nếu người dùng gửi giá trị chứa ký tự điều khiển filter như `*`, `(`, `)` hoặc `\`, filter có thể thay đổi ý nghĩa ngoài dự kiến. Đây là rủi ro LDAP injection.

### 10.3. Dùng filter format có tham số

Khi cần filter string, overload có tham số của QueryBuilder encode giá trị:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .filter("(&(objectClass=inetOrgPerson)(uid={0}))", uidFromRequest);
~~~

Các placeholder theo `MessageFormat` dùng dạng `{0}`, `{1}`. Giá trị tham số được encode bằng `LdapEncoder.filterEncode` trước khi đưa vào filter.

### 10.4. Hardcoded filter chỉ dùng với nội dung tin cậy

Overload:

~~~java
query().filter("(objectClass=inetOrgPerson)");
~~~

dùng filter literal và không tự escape/validate nội dung. Nó phù hợp với filter tĩnh do lập trình viên kiểm soát. Không nối user input vào overload này.

### 10.5. Filter escaping khác DN escaping

Hai loại encoding giải quyết hai ngữ cảnh khác nhau:

| Dữ liệu | Mục đích | API liên quan |
| --- | --- | --- |
| Giá trị trong LDAP search filter | Ngăn giá trị thay đổi cấu trúc filter | `LdapEncoder.filterEncode` |
| Giá trị RDN trong DN | Biểu diễn đúng thành phần tên DN | `LdapNameBuilder` hoặc encoder DN phù hợp |

Không dùng DN escaping thay cho filter escaping hoặc ngược lại. Khi truy vấn attribute `member` có giá trị là DN, giá trị DN vẫn phải được đưa vào filter theo quy tắc filter encoding.

## 11. Chọn attributes cần trả về

`LdapQueryBuilder.attributes(...)` chỉ định các LDAP attribute server cần trả về:

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("objectClass", "uid", "cn", "sn", "mail")
        .where("objectClass").is("inetOrgPerson");
~~~

Projection giúp giảm lượng dữ liệu truyền qua mạng khi directory có nhiều attribute hoặc attribute lớn.

### 11.1. ODM entity cần đủ attribute để mapping

Nếu entity có:

- `uid`
- `cn`
- `sn`
- `mail`

nhưng query chỉ yêu cầu `uid` và `cn`, các field còn lại có thể không được populate trong entity trả về. DN ở field `@Id` được lấy từ entry context, còn các field `@Attribute` phụ thuộc attribute được trả.

Với repository trả entity đầy đủ, hãy:
- Yêu cầu mọi attribute mà caller cần.
- Bao gồm các attribute ODM cần để xác định/mapping entry, như `objectClass` khi phù hợp.
- Không truyền entity projection thiếu dữ liệu vào service update rồi lưu ngược như thể đó là entity hoàn chỉnh.
- Dùng DTO/projection ở tầng ứng dụng nếu chỉ muốn hiển thị một phần dữ liệu.

### 11.2. Không trả toàn bộ attribute nhạy cảm

Directory có thể chứa:
- Thuộc tính xác thực.
- Thông tin nhân sự.
- Dữ liệu nhị phân/chứng thư.
- Thuộc tính nội bộ phục vụ quản trị.

Chỉ yêu cầu các attribute cần thiết. Quyền Search/Read của Bind DN và authorization của API phải giới hạn dữ liệu được trả cho caller. Projection không thay thế ACL.

## 12. Count limit và time limit

QueryBuilder có hai giới hạn thường dùng:

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(2_000)
        .where("objectClass").is("inetOrgPerson")
        .and("departmentNumber").is("ENG");
~~~

- `countLimit(100)` yêu cầu tối đa 100 entry.
- `timeLimit(2_000)` đặt thời gian Search tối đa 2.000 mili giây trong Search controls của JNDI.

### 12.1. Count limit không phải paging

`countLimit` giới hạn số entry trả về cho một Search. Nó không tạo page number, cursor hoặc cơ chế tự động lấy trang tiếp theo.

Nếu directory có 5.000 entry phù hợp và query giới hạn 100, ứng dụng chỉ yêu cầu tối đa 100 entry. Không được hiển thị kết quả như thể đã lấy đầy đủ 5.000 entry.

### 12.2. Server có thể áp giới hạn thấp hơn

LDAP server có thể có policy giới hạn Search theo Bind identity, base, filter hoặc cấu hình quản trị. Vì thế, count limit trong query không bảo đảm client luôn nhận đủ số entry mong muốn.

Các lỗi/hiện tượng cần nhận biết:
- Size limit exceeded.
- Time limit exceeded.
- Partial result/referral.
- Communication failure.
- ACL không cho đọc một số entry/attribute.

Nếu nghiệp vụ cần kết quả đầy đủ, hãy cấu hình xử lý limit nghiêm ngặt và kiểm thử với server thật. Một số cấu hình `LdapTemplate` có thể bỏ qua `SizeLimitExceededException` và trả phần kết quả đã nhận; không coi danh sách partial là dữ liệu đầy đủ.

### 12.3. Time limit không thay thế network timeout

`timeLimit` là giới hạn cho LDAP Search operation. Nó không thay thế connect timeout hoặc read timeout của JNDI provider. Ứng dụng vẫn cần timeout kết nối và timeout chờ response để kiểm soát các lỗi mạng.

## 13. Paging và sorting trong Spring Data LDAP repository

Không giống repository SQL, Spring Data LDAP repository **không hỗ trợ paging và sorting** qua các kiểu `Pageable`, `Page<T>` hoặc `Sort` như một repository quan hệ thông thường.

Lý do liên quan đến semantics và khả năng của LDAP Search; việc phân trang/sắp xếp có thể cần control riêng mà repository abstraction này không cung cấp.

Điều đó có nghĩa:
- `findAll(LdapQuery)` trả về một `List<T>`.
- Không có tham số `Pageable` để yêu cầu page 2.
- Không có `Sort` để yêu cầu sắp xếp theo surname.
- `countLimit` chỉ giới hạn số entry của một truy vấn, không phải phân trang.

Nếu cần xử lý directory lớn:
1. Thu hẹp base DN và scope.
2. Dùng filter có tính chọn lọc.
3. Chỉ yêu cầu attribute cần thiết.
4. Đặt count/time limit hợp lý.
5. Nếu cần paged results, dùng API Spring LDAP thấp hơn với control phù hợp và kiểm tra server có hỗ trợ RFC 2696.
6. Nếu cần sorting, xác minh server hỗ trợ sort control và thiết kế adapter riêng.

Không tải toàn bộ directory vào một List chỉ để phân trang ở bộ nhớ nếu directory có hàng trăm nghìn entry.

## 14. So sánh repository findOne với LdapTemplate.findOne

Tên method gần giống nhau nhưng ngữ nghĩa API khác nhau.

| API | Kiểu trả về | Khi không có kết quả | Khi có nhiều kết quả |
| --- | --- | --- | --- |
| `LdapRepository.findOne(LdapQuery)` | `Optional<T>` | Optional không có giá trị | `IncorrectResultSizeDataAccessException` |
| `LdapRepository.findAll(LdapQuery)` | `List<T>` | List rỗng | Trả tất cả entry nhận được theo query |
| `LdapTemplate.findOne(LdapQuery, Class<T>)` | `T` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| `LdapTemplate.find(LdapQuery, Class<T>)` | `List<T>` | List rỗng | Trả danh sách |

Đừng chuyển code từ `LdapTemplate.findOne` sang repository `findOne` rồi giữ nguyên cách bắt `EmptyResultDataAccessException` mà không kiểm tra hợp đồng mới. Repository method có kiểu `Optional<T>` nên thường được xử lý qua `isPresent`, `orElse` hoặc `orElseThrow`.

## 15. Tổ chức query trong service

Không nên đặt toàn bộ query builder trong controller. Hãy tạo service có nhiệm vụ nhận tham số nghiệp vụ, validate input và xây query có base/scope cố định.

~~~java
package com.example.directory.service;

import java.util.List;
import java.util.Optional;

import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import com.example.directory.model.DirectoryPerson;
import com.example.directory.repository.DirectoryPersonRepository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class PersonSearchService {

    private final DirectoryPersonRepository repository;

    public PersonSearchService(DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public Optional<DirectoryPerson> findByUid(String uid) {
        validateUid(uid);

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return repository.findOne(ldapQuery);
    }

    public List<DirectoryPerson> findBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("Surname is required");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("sn").is(surname);

        return repository.findAll(ldapQuery);
    }

    public List<DirectoryPerson> searchByNamePrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("Prefix is required");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("cn").like(prefix + "*");

        return repository.findAll(ldapQuery);
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid UID");
        }
    }
}
~~~

Service giữ các quy tắc:
- Base DN được xác định bởi ứng dụng.
- Scope được chọn theo cấu trúc directory.
- Attribute name do code kiểm soát.
- Giá trị filter đi qua builder.
- UID được validate theo quy tắc định danh của hệ thống.
- Kết quả đơn và danh sách được biểu diễn bằng kiểu trả về riêng.

`validateUid` là validation nghiệp vụ của ví dụ, không phải thay thế LDAP filter encoding. Giá trị vẫn được builder encode trong filter.

## 16. Truy vấn group theo DN thành viên

Một use case khác là tìm các nhóm có chứa một user DN. Với schema OpenLDAP dùng `groupOfNames`, attribute `member` thường chứa DN của user.

~~~java
public List<DirectoryGroup> findGroupsContaining(Name userDn) {
    LdapQuery ldapQuery = query()
            .base("ou=groups")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("groupOfNames")
            .and("member").is(userDn.toString());

    return groupRepository.findAll(ldapQuery);
}
~~~

Ví dụ entity:

~~~java
@Entry(objectClasses = {"top", "groupOfNames"})
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "member")
    private Set<Name> members;

    // Getter/setter được lược bớt.
}
~~~

Một số điểm cần nhớ:
- DN là giá trị của attribute `member`, nhưng toàn bộ giá trị vẫn phải được encode đúng trong LDAP filter.
- `groupOfNames` và `member` là schema cụ thể; Active Directory thường dùng `objectClass=group` với thuộc tính `member`.
- Tìm membership trực tiếp khác với tính toán nested group/transitive membership.
- ACL có thể cho phép tìm group nhưng không cho đọc toàn bộ danh sách thành viên.
- Không trả danh sách group nhạy cảm cho caller nếu họ không có quyền.

## 17. Lỗi và trường hợp kết quả không đầy đủ

Một truy vấn không phải lúc nào cũng kết thúc bằng một danh sách hợp lệ. Cần phân biệt kết quả nghiệp vụ rỗng với lỗi truy cập directory.

| Tình huống | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Không có entry khớp filter | Optional rỗng hoặc List rỗng | Xử lý như không tìm thấy theo nghiệp vụ. |
| Filter quá rộng, nhiều kết quả cho findOne | `IncorrectResultSizeDataAccessException` | Thu hẹp filter hoặc đổi sang findAll. |
| Search base sai/không tồn tại | Có thể nhận lỗi NameNotFound hoặc hành vi tùy template/provider | Kiểm tra base DN và cấu hình ignore-name-not-found. |
| Filter sai cú pháp | InvalidSearchFilterException hoặc exception Spring LDAP tương ứng | Sửa filter và test schema. |
| Search vượt time limit | TimeLimitExceededException hoặc lỗi tương ứng | Tối ưu base/filter và kiểm tra server. |
| Search vượt size limit | SizeLimitExceededException hoặc kết quả partial tùy cấu hình | Không coi partial là đầy đủ. |
| Referral/partial result | PartialResultException hoặc lỗi referral | Xác minh topology và referral policy. |
| Không đủ quyền đọc | Có thể thiếu entry/attribute hoặc bị từ chối | Kiểm tra Bind identity và ACL. |
| Directory không kết nối được | CommunicationException/ServiceUnavailableException | Xử lý lỗi hạ tầng, không coi là rỗng. |

Không viết:

~~~java
try {
    return repository.findAll(query);
} catch (Exception ex) {
    return List.of();
}
~~~

Cách này biến lỗi mạng, ACL, schema hoặc partial result thành “không có người dùng”. Hệ thống phía trên sẽ không phân biệt được dữ liệu thực sự rỗng với việc directory không trả được dữ liệu.

## 18. Kiểm thử findOne và findAll

Hãy dùng LDAP test server riêng hoặc container disposable. Fixture cần có:
- Một entry UID duy nhất.
- Nhiều entry cùng surname.
- Một entry nằm trong OU con.
- Hai entry có cùng giá trị email hoặc thuộc tính không được bảo đảm uniqueness để kiểm tra cardinality.
- Một group có các DN thành viên.

### 18.1. Test findOne trả đúng một entry

~~~java
@SpringBootTest
class DirectoryPersonRepositoryTest {

    @Autowired
    DirectoryPersonRepository repository;

    @Test
    void findOneReturnsPersonByUid() {
        LdapQuery query = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("lan");

        Optional<DirectoryPerson> result = repository.findOne(query);

        assertTrue(result.isPresent());
        assertEquals("lan", result.get().getUid());
    }
}
~~~

Fixture cần được nạp trước test và phải nằm dưới đúng base DN mà query sử dụng.

### 18.2. Test không có kết quả

~~~java
@Test
void findOneReturnsEmptyWhenNoEntryMatches() {
    LdapQuery query = query()
            .base("ou=people")
            .searchScope(SearchScope.ONELEVEL)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is("uid-does-not-exist");

    assertTrue(repository.findOne(query).isEmpty());
}
~~~

### 18.3. Test nhiều kết quả cho findOne

Chuẩn bị hai entry khác nhau có cùng email trong phạm vi Search. Không giả định schema mặc định luôn enforce unique email.

~~~java
@Test
void findOneRejectsMultipleMatchingEntries() {
    LdapQuery query = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("mail").is("shared@example.org");

    assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> repository.findOne(query)
    );
}
~~~

Test này xác nhận filter có nhiều match không bị chọn tùy tiện một entry. Nếu directory schema/overlay có unique constraint cho email, hãy tạo fixture test phù hợp với policy của server hoặc dùng thuộc tính khác có thể trùng.

### 18.4. Test findAll

~~~java
@Test
void findAllReturnsAllMatchingPeople() {
    LdapQuery query = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("sn").is("Nguyen");

    List<DirectoryPerson> result = repository.findAll(query);

    assertEquals(2, result.size());
    assertTrue(result.stream()
            .allMatch(person -> "Nguyen".equals(person.getSurname())));
}
~~~

Không nên assert thứ tự nếu query không có cơ chế sorting được bảo đảm. So sánh tập UID hoặc các thuộc tính định danh sẽ phù hợp hơn.

### 18.5. Test filter chống injection

~~~java
@Test
void userInputIsTreatedAsFilterValue() {
    String suspiciousValue = "*)(objectClass=*)";

    LdapQuery query = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("uid").is(suspiciousValue);

    List<DirectoryPerson> result = repository.findAll(query);

    // Kỳ vọng filter so sánh UID với đúng literal đã encode,
    // không mở rộng thành một filter OR/AND khác.
    assertTrue(result.isEmpty());
}
~~~

Test cần chạy với fixture không có UID đúng literal đó. Không chỉ test output; có thể kiểm tra filter đã encode trong unit test riêng nếu dự án cần kiểm chứng chính xác biểu diễn filter.

### 18.6. Ma trận kiểm thử tối thiểu

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| UID có một entry | findOne trả Optional có giá trị. |
| UID không tồn tại | findOne trả Optional rỗng. |
| Email trùng nhiều entry | findOne ném IncorrectResultSizeDataAccessException. |
| Họ khớp nhiều entry | findAll trả toàn bộ entry khớp. |
| Filter không khớp | findAll trả list rỗng. |
| Scope ONELEVEL | Không lấy entry nằm sâu trong OU con. |
| Scope SUBTREE | Lấy entry ở các OU con phù hợp filter. |
| Base DN cố định | Không Search ngoài nhánh được phép. |
| Attribute projection | Entity chỉ có các field được yêu cầu/mapping hỗ trợ. |
| Count limit | Kết quả không vượt quá giới hạn client yêu cầu. |
| Time limit | Search bị giới hạn thời gian theo Search controls. |
| User input chứa ký tự filter | Không thể thay đổi cấu trúc filter. |
| Reader thiếu ACL | Lỗi/quyền được nhận diện, không chuyển thành list rỗng giả. |
| Directory unavailable | Báo lỗi hạ tầng, không coi là không có kết quả. |
| Server trả partial result | Không báo kết quả là đầy đủ. |

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Repository chỉ extends CrudRepository nhưng gọi findOne(LdapQuery) | Không có overload LDAP-specific | Mở rộng LdapRepository<T>. |
| Entity thiếu @Entry hoặc @Id ODM | ODM không thể map entry đúng | Dùng annotation trong org.springframework.ldap.odm.annotations. |
| Dùng @Id của Spring Data Commons | Mapper Spring LDAP không nhận metadata mong muốn | Dùng Spring LDAP ODM @Id. |
| Không chỉ định base DN | Search có thể rộng từ ContextSource root | Đặt base rõ ràng theo use case. |
| Dùng SUBTREE cho mọi truy vấn | Search sâu và tốn tài nguyên ngoài ý muốn | Chọn OBJECT/ONELEVEL/SUBTREE đúng. |
| Dùng findOne cho thuộc tính không duy nhất | IncorrectResultSizeDataAccessException | Thu hẹp filter hoặc dùng findAll. |
| Dùng countLimit(1) để che duplicate | Có thể không phát hiện nhiều entry khớp | Bảo đảm uniqueness và không cắt kết quả khi kiểm tra cardinality. |
| Nghĩ findAll tự phân trang | Tải toàn bộ List, có thể tốn bộ nhớ | Dùng base/filter hẹp hoặc API paging phù hợp. |
| Giả định kết quả có thứ tự | Chọn nhầm phần tử đầu | Không dựa vào thứ tự nếu không có sort control. |
| Nối user input vào filter | LDAP injection | Dùng where/is hoặc filter có tham số. |
| Dùng filter(String) với chuỗi động | Không tự encode | Chỉ dùng literal tin cậy hoặc overload tham số. |
| Đưa tên attribute từ HTTP vào where | Có thể cho phép thay đổi cấu trúc query | Allowlist attribute names. |
| Dùng like khi muốn exact match | Wildcard có thể mở rộng kết quả | Dùng is. |
| Projection thiếu attribute nhưng vẫn dùng entity để update | Entity không đầy đủ dữ liệu | Yêu cầu đủ field hoặc dùng DTO. |
| Coi size/time limit là paging | Dữ liệu bị giới hạn nhưng không có trang tiếp theo | Dùng paging control ở tầng LDAP thấp hơn nếu cần. |
| Catch mọi exception rồi trả List rỗng | Che lỗi ACL/network/partial result | Xử lý từng loại lỗi đúng ngữ nghĩa. |
| Giả định uid/mail luôn unique trên mọi LDAP | Dữ liệu trùng có thể làm findOne lỗi | Kiểm tra schema/policy và test server thực tế. |

## 20. Checklist trước khi dùng LdapQuery trong service

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Repository interface | Extends LdapRepository<T>. |
| Entity ODM | Có @Entry, @Id và mapping attribute cần thiết. |
| ID | Field @Id có kiểu javax.naming.Name. |
| Base DN | Chỉ rõ nhánh directory cần tìm. |
| Search scope | Phù hợp cấu trúc DIT và nghiệp vụ. |
| Filter | Có điều kiện objectClass và điều kiện nghiệp vụ cần thiết. |
| User input | Giá trị được encode; attribute name nằm trong allowlist. |
| findOne | Filter có thể khớp tối đa một entry; duplicate được xử lý. |
| findAll | Caller chấp nhận danh sách nhiều entry và kích thước kết quả. |
| Attributes | Có đủ attribute cần map/hiển thị; không trả dư dữ liệu nhạy cảm. |
| Count/time limit | Có giới hạn hợp lý và hiểu rõ partial result. |
| Paging/sorting | Không giả định repository hỗ trợ Pageable/Sort. |
| ACL | Bind DN có quyền Search/Read phù hợp. |
| Testing | Có test zero/one/multiple, scope, injection và server errors. |

## 21. Bài tập thực hành

**Bài 1 — Repository đầu tiên.** Tạo `DirectoryPerson` với `@Entry`, `@Id Name` và các field `uid`, `cn`, `sn`, `mail`. Tạo `DirectoryPersonRepository extends LdapRepository<DirectoryPerson>` và bật `@EnableLdapRepositories`.

**Bài 2 — Tìm một người.** Viết query base `ou=people`, scope `ONELEVEL`, filter `objectClass=inetOrgPerson` và `uid=lan`. Gọi `findOne`, xử lý Optional rỗng và có giá trị.

**Bài 3 — Tìm nhiều người.** Viết query tìm theo `sn` và gọi `findAll`. Tạo ít nhất ba entry cùng surname, xác minh list có đầy đủ.

**Bài 4 — Cardinality.** Tạo hai entry có cùng mail dưới hai OU con. Gọi `findOne` với filter mail và xác minh `IncorrectResultSizeDataAccessException`. Sau đó đổi sang `findAll`.

**Bài 5 — Search scope.** Tạo một user trực tiếp dưới `ou=people` và một user dưới `ou=engineering,ou=people`. So sánh kết quả ONELEVEL với SUBTREE.

**Bài 6 — OR filter.** Tìm người có UID lan hoặc minh. Viết filter có cấu trúc OR và kiểm tra LDAP filter được tạo.

**Bài 7 — Filter injection.** Thử input chứa `*)(objectClass=*)`. So sánh cách dùng `where("uid").is(value)` với cách nối chuỗi raw. Chứng minh input không thể mở rộng filter.

**Bài 8 — Projection.** Chỉ yêu cầu `uid`, `cn` và `mail`. Quan sát các field entity khác và giải thích vì sao projection không phù hợp nếu code cần entity đầy đủ.

**Bài 9 — Limit.** Đặt `countLimit(2)` và `timeLimit(1000)`. Kiểm tra hành vi khi có nhiều kết quả hoặc directory phản hồi chậm; không coi hai limit là paging.

**Bài 10 — Directory khác nhau.** Chạy query tương đương trên OpenLDAP và Active Directory. So sánh objectClass, attribute username, base DN, ACL và filter được hỗ trợ.

## 22. Câu hỏi tự đánh giá

1. `LdapQuery` mô tả những thành phần nào của LDAP Search?
2. Vì sao repository cần extends `LdapRepository<T>` để nhận `LdapQuery`?
3. Kiểu ID mặc định của `LdapRepository` là gì?
4. Vì sao entity phải có `@Entry` và `@Id` của Spring LDAP ODM?
5. `LdapQueryBuilder.query()` có yêu cầu filter không?
6. Base DN của query tương đối với `ContextSource.base` như thế nào?
7. `OBJECT`, `ONELEVEL` và `SUBTREE` khác nhau ở đâu?
8. Khi nào nên dùng `findOne`?
9. `findOne` xử lý 0, 1 và nhiều kết quả như thế nào?
10. Vì sao `countLimit(1)` có thể che dữ liệu trùng?
11. `findAll` trả kiểu gì khi không có entry khớp?
12. Vì sao không được dựa vào thứ tự List nếu không có sort control?
13. `where("uid").is(value)` bảo vệ filter như thế nào?
14. Vì sao `filter(String)` không phù hợp với dữ liệu người dùng?
15. Overload `filter(String, Object...)` encode tham số theo cách nào?
16. `like` khác `is` như thế nào?
17. `attributes` ảnh hưởng mapping entity ra sao?
18. `countLimit` khác paging như thế nào?
19. Vì sao Spring Data LDAP repository không hỗ trợ Pageable/Sort?
20. Vì sao không nên catch mọi exception rồi trả List rỗng?
21. LDAP schema có luôn đảm bảo UID hoặc mail duy nhất không?
22. `LdapTemplate.findOne` khác `LdapRepository.findOne` như thế nào?
23. Khi nào Search result có thể partial?
24. Cần test những trường hợp nào trước khi dùng query động trong production?

**Ghi nhớ:** `LdapQuery` mô tả base, scope, filter, attributes và giới hạn của LDAP Search. `LdapRepository.findOne(query)` dùng cho truy vấn có tối đa một kết quả và phát hiện trường hợp nhiều entry; `findAll(query)` trả danh sách. Hãy giới hạn base/scope, dùng filter builder để encode giá trị, không dùng count limit như paging hoặc cách che duplicate, và luôn phân biệt kết quả rỗng với lỗi directory/partial result.

### Tài liệu tham khảo

- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html): chữ ký `findOne(LdapQuery)`, `findAll(LdapQuery)`, kiểu trả về và lỗi khi nhiều kết quả.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories`, `ContextSource`, `LdapTemplate` và yêu cầu ODM.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): base, scope, filter, attributes, count/time limit và quy tắc encode.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): filter criteria, AND/OR, wildcard và hardcoded filter.
- [Spring LDAP — SearchScope API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/SearchScope.html): OBJECT, ONELEVEL và SUBTREE.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và ánh xạ objectClass.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): Search controls và xử lý size limit/partial results.
- [Spring LDAP — LdapEncoder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html): encode giá trị cho LDAP filter và DN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): SearchRequest, SearchResultEntry, scope, sizeLimit và timeLimit.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp và escaping LDAP search filter.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): DN, entry, attribute và objectClass schema.
