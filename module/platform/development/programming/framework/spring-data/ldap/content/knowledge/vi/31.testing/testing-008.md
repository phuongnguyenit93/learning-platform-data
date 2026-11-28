# Kiểm thử ODM, Repository và thuộc tính nhiều giá trị

## 1. Vì sao kiểm thử LDAP cần một directory thật?

Một entity Spring LDAP có thể trông giống một Java object thông thường:

```java
@Entry(objectClasses = {"top", "groupOfUniqueNames"}, base = "ou=groups")
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute("cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members;
}
```

Nhưng object này được lưu trong một **directory phân cấp**, có DN, RDN, `objectClass`, schema, ACL và các attribute có thể chứa nhiều giá trị. Một test chỉ mock `LdapTemplate` có thể xác nhận service đã gọi một method, nhưng không chứng minh:

- ODM đọc đúng DN và ánh xạ đúng `@DnAttribute`/`@Attribute`.
- Một attribute đa trị như `uniqueMember` được chuyển thành `Set<Name>`.
- Repository tìm đúng entry theo DN hoặc query.
- `save`/`update` chỉ thêm hoặc gỡ đúng giá trị, không làm mất member khác.
- LDAP server chấp nhận entry theo schema và từ chối dữ liệu sai.
- DN có ký tự cần escape được dựng và tìm đúng.

Vì vậy, bài này kết hợp **unit test cho logic thuần Java** với **integration test chạy trên LDAP server cô lập**. Phần thực hành dùng Spring Boot, Spring Data LDAP, Spring LDAP ODM, JUnit 5 và embedded UnboundID LDAP server.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn đúng test level cho mapper, ODM, repository và LDAP server.
2. Dựng LDAP test directory có base DN, OU, user và group bằng LDIF.
3. Dùng `@DataLdapTest` để kiểm thử slice của Spring Data LDAP.
4. Viết entity ODM có `@Id Name`, `@DnAttribute` và attribute đa trị `Set<Name>`.
5. Kiểm tra CRUD, derived query, query theo `LdapQuery` và DN.
6. Kiểm tra add/remove nhiều giá trị mà không phụ thuộc thứ tự LDAP trả về.
7. Phân biệt lỗi mapping với lỗi schema, ACL, DN, filter và server.
8. Tạo fixture cô lập, cleanup rõ ràng và tránh test phụ thuộc thứ tự chạy.

## 2. Những gì cần kiểm thử trong một ứng dụng Spring Data LDAP

| Tầng | Thành phần | Câu hỏi kiểm thử |
| --- | --- | --- |
| Mapping thuần | Hàm dựng DN, chuyển đổi value, validation | UID có được dựng thành DN đúng? Giá trị đầu vào có bị nối chuỗi nguy hiểm? |
| ODM | `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`, `@Transient` | Entry LDAP được đọc thành entity đúng và ghi trở lại đúng schema? |
| Multi-valued attributes | `Set<Name>`, `Set<String>`, `uniqueMember`, `member` | Tập giá trị được đọc đủ, so sánh đúng và cập nhật đúng từng giá trị? |
| Repository | `LdapRepository<T>`, CRUD, query methods | `findById`, `save`, `deleteById` và query trả đúng entry? |
| LDAP integration | Bind, Search, Add, Modify, Delete | Server thực sự chấp nhận/từ chối thao tác theo schema và ACL? |
| System behavior | Sync, concurrency, retry, paging/referral | Nhiều writer, timeout hoặc replica lag có làm mất membership? |

Không nên dùng một test duy nhất để chứng minh tất cả. Ví dụ:

- Unit test có thể xác minh helper tạo DN, nhưng không kiểm tra server có entry ở DN đó.
- Repository test có thể chứng minh derived query hoạt động với fixture, nhưng không chứng minh ACL production giống test server.
- Integration test trên UnboundID chứng minh mapping và schema của fixture; không thay thế kiểm thử tương thích với Active Directory hoặc OpenLDAP đang vận hành.

## 3. Chọn LDAP server cho test

Có ba lựa chọn thường gặp:

| Lựa chọn | Khi nên dùng | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Embedded UnboundID | Unit/integration test nhanh cho ODM, repository, DN và schema chuẩn. | Chạy trong tiến trình test, không cần cài server ngoài. | Không mô phỏng mọi behavior vendor, ACL, replication hoặc extension. |
| Container chạy OpenLDAP/Active Directory-compatible test server | Kiểm thử schema, overlay, ACL, referral hoặc behavior vendor. | Gần môi trường triển khai hơn. | Cần Docker/CI service, startup và cleanup. |
| LDAP test environment dùng chung | Smoke/contract test với cấu hình gần production. | Xác minh TLS, bind identity, schema và policy thực tế. | Phải cô lập dữ liệu, tránh test phá dữ liệu của nhóm khác. |

**Mặc định cho bài học:** dùng embedded UnboundID để test mapping và CRUD cơ bản. Khi một behavior phụ thuộc vendor (ví dụ overlay `memberof`, linked attribute AD, range retrieval, password policy, referral hoặc ACL), bổ sung test trên đúng loại server đó.

## 4. Cấu hình embedded LDAP với Spring Boot

Spring Boot có thể tự cấu hình LDAP server nhúng từ UnboundID khi dependency có mặt. Server thường khởi động trên port ngẫu nhiên; Spring Boot cấu hình các thành phần LDAP thông thường để ứng dụng/test dùng được.

### 4.1. Dependency mẫu cho Gradle

Ví dụ theo Spring Boot 3.x:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("com.unboundid:unboundid-ldapsdk")
}
```

Dùng Spring Boot dependency management/BOM để chọn version tương thích. Không nên tự ghim version UnboundID cũ nếu BOM hoặc hướng dẫn Spring Boot hiện hành đã quản lý phiên bản phù hợp.

### 4.2. Cấu hình test profile

Ví dụ `src/test/resources/application.yml`:

```yaml
spring:
  ldap:
    base: dc=example,dc=org
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap-test.ldif
```

- `spring.ldap.embedded.base-dn` khai báo naming context của server nhúng.
- `spring.ldap.embedded.ldif` chỉ định fixture nạp vào server.
- `spring.ldap.base` giúp các thao tác ứng dụng dùng DN tương đối với `dc=example,dc=org`.
- Nếu dùng nhiều base DN, cấu hình đúng dạng danh sách YAML; dấu phẩy trong DN phải nằm trong một chuỗi.

Nếu test cần service account riêng, cấu hình `spring.ldap.username`/`password` cùng fixture tài khoản và quyền tương ứng. Với test mapping cơ bản, không cần tạo thêm credential chỉ để làm cho ví dụ phức tạp hơn.

### 4.3. @DataLdapTest

Spring Boot cung cấp `@DataLdapTest` để kiểm thử slice Spring Data LDAP. Với embedded LDAP khả dụng trên classpath, annotation này cấu hình LDAP nhúng, `LdapTemplate`, quét các class `@Entry` và cấu hình repository LDAP.

Ví dụ import của Spring Boot 3.x:

```java
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
```

Ở Spring Boot 4.x, package annotation đã chuyển sang:

```java
import org.springframework.boot.data.ldap.test.autoconfigure.DataLdapTest;
```

Hãy dùng package tương ứng với major version của dự án. `@DataLdapTest` là test slice: các bean `@Component` và `@ConfigurationProperties` thông thường không được quét tự động; nếu test cần chúng, hãy import hoặc bật configuration có chủ đích.

### 4.4. Khi cần kiểm thử trên LDAP server bên ngoài

Có thể loại embedded auto-configuration khỏi `@DataLdapTest` rồi cấu hình `ContextSource` tới test server. Tên package của `EmbeddedLdapAutoConfiguration` cũng thay đổi giữa major version Spring Boot, nên lấy từ tài liệu của đúng version.

Đối với test server bên ngoài:

- Dùng hostname/port test riêng.
- Tạo suffix/base DN riêng cho build hoặc test run.
- Dùng bind identity chỉ có quyền cần thiết.
- Không dùng directory production.
- Dọn fixture bằng API quản trị hoặc reset container sau test.

## 5. Fixture LDIF: tạo cây directory nhất quán

Tạo file `src/test/resources/ldap-test.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org

dn: uid=hoa,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: hoa
cn: Hoa Pham
sn: Pham
mail: hoa@example.org

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: developers
uniqueMember: uid=linh,ou=people,dc=example,dc=org
uniqueMember: uid=an,ou=people,dc=example,dc=org
```

Fixture này tạo:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=an
└── ou=groups
    └── cn=developers
        ├── uniqueMember: uid=linh,...
        └── uniqueMember: uid=an,...
```

Lưu ý schema:

- `groupOfUniqueNames` dùng `uniqueMember` và yêu cầu có member theo schema chuẩn; vì vậy fixture không tạo group rỗng.
- `inetOrgPerson` kế thừa các object class liên quan và cần các thuộc tính bắt buộc như `cn`, `sn`.
- Tên attribute và object class không nên tùy tiện thay đổi trong LDIF chỉ để test pass.
- Embedded server thường dùng schema chuẩn; nếu test custom schema, phải nạp schema extension đúng cách hoặc dùng server test hỗ trợ extension đó.

## 6. Viết entity ODM cho group có nhiều DN member

Spring LDAP ODM hỗ trợ ánh xạ attribute đa trị chứa DN thành `Set<Name>`. Đây là kiểu phù hợp cho membership, vì thứ tự các giá trị trong LDAP attribute không được đảm bảo như thứ tự phần tử trong một Java List.

### 6.1. Entity DirectoryGroup

```java
package com.example.directory.group;

import java.util.LinkedHashSet;
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfUniqueNames"}
)
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute("cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members = new LinkedHashSet<>();

    public DirectoryGroup() {
    }

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Set<Name> getMembers() {
        return members;
    }

    public void setMembers(Set<Name> members) {
        this.members = new LinkedHashSet<>(members);
    }

    public void addMember(Name memberDn) {
        members.add(memberDn);
    }

    public void removeMember(Name memberDn) {
        members.remove(memberDn);
    }
}
```

Giải thích:

- `@Entry` xác định object classes và base của các group entity.
- `@Id` giữ DN dưới kiểu `javax.naming.Name`.
- `@DnAttribute("cn")` lấy tên group từ RDN `cn=...`.
- `@Attribute(name="cn")` ánh xạ cùng field tới attribute `cn` trong entry.
- `@Attribute(name="uniqueMember")` ánh xạ attribute đa trị thành `Set<Name>`.
- `Set<Name>` thể hiện tập DN; không giả định thứ tự server trả về.
- `LinkedHashSet` giúp thứ tự iteration trong Java ổn định theo thứ tự thêm vào, nhưng **không** biến thứ tự LDAP thành một contract.

**Không dùng `Set<String>` cho DN-valued attribute nếu mục tiêu là tận dụng so sánh DN.** `Name` biểu diễn DN có cấu trúc; so sánh DN không nên phụ thuộc chuỗi hiển thị.

### 6.2. Group repository

```java
package com.example.directory.group;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {

    List<DirectoryGroup> findByName(String name);
}
```

`LdapRepository<T>` mặc định dùng `javax.naming.Name` làm kiểu ID. Khác với một số repository SQL, Spring LDAP repository không hỗ trợ paging/sorting theo cùng cách thông thường vì giới hạn giao thức và implementation.

### 6.3. Dựng DN trong test

Không nối chuỗi DN từ input:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name groupDn = LdapNameBuilder.newInstance("ou=groups")
    .add("cn", "developers")
    .build();

// DN trong uniqueMember phải là DN đầy đủ, gồm cả naming context.
Name linhDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "linh")
    .build();
```

`groupDn` là DN tương đối với `ContextSource.base=dc=example,dc=org` vì được dùng làm đích thao tác repository. Ngược lại, `uniqueMember` lưu DN của user như **giá trị attribute**, nên phải chứa DN đầy đủ: `uid=linh,ou=people,dc=example,dc=org`. Không cắt bỏ naming context khỏi DN-valued attribute.

## 7. Kiểm thử repository bằng @DataLdapTest

Ví dụ test slice dùng JUnit 5 và Spring Boot 3.x:

```java
package com.example.directory.group;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Optional;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.support.LdapNameBuilder;

@DataLdapTest
class DirectoryGroupRepositoryTests {

    @Autowired
    private DirectoryGroupRepository repository;

    private Name groupDn(String cn) {
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", cn)
            .build();
    }

    private Name personDn(String uid) {
        // uniqueMember là DN-valued attribute: dùng DN đầy đủ.
        return LdapNameBuilder.newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }

    @Test
    void findByIdMapsDnAndAllUniqueMembers() {
        DirectoryGroup group = repository.findById(
            groupDn("developers")
        ).orElseThrow();

        assertThat(group.getName()).isEqualTo("developers");
        assertThat(group.getDn()).isNotNull();
        assertThat(group.getMembers())
            .containsExactlyInAnyOrder(
                personDn("linh"),
                personDn("an")
            );
    }

    @Test
    void derivedQueryFindsGroupByMappedProperty() {
        List<DirectoryGroup> groups = repository.findByName("developers");

        assertThat(groups)
            .hasSize(1)
            .first()
            .extracting(DirectoryGroup::getName)
            .isEqualTo("developers");
    }
}
```

Test này kiểm tra cả hai chiều:

1. Repository truy xuất entry theo DN.
2. ODM populate field `name` từ RDN và `cn`.
3. ODM chuyển toàn bộ `uniqueMember` thành `Set<Name>`.
4. Derived query dùng property `name` đã map tới LDAP attribute `cn`.

Nếu test chạy trên Spring Boot 4.x, đổi import `DataLdapTest` sang package của Boot 4 như đã nêu ở mục cấu hình. Không thay import ngẫu nhiên giữa major version.

## 8. Kiểm thử CRUD và nhiều giá trị bằng repository

LDAP không cung cấp transaction rollback kiểu database quan hệ cho mỗi test. Test cần dùng DN riêng và cleanup entry đã tạo. Ví dụ sau tạo group mới, đọc lại, cập nhật tập member rồi xóa:

```java
package com.example.directory.group;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.support.LdapNameBuilder;

@DataLdapTest
class DirectoryGroupCrudTests {

    @Autowired
    private DirectoryGroupRepository repository;

    private Name groupDn(String cn) {
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", cn)
            .build();
    }

    private Name personDn(String uid) {
        // uniqueMember là DN-valued attribute: dùng DN đầy đủ.
        return LdapNameBuilder.newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }

    @Test
    void createReadUpdateAndDeleteMultiValuedMembership() {
        String groupName = "lab-" + java.util.UUID.randomUUID();
        Name dn = groupDn(groupName);

        DirectoryGroup group = new DirectoryGroup();
        group.setDn(dn);
        group.setName(groupName);
        group.setMembers(Set.of(
            personDn("linh"),
            personDn("an")
        ));

        boolean created = false;
        try {
            // CREATE
            repository.save(group);
            created = true;

            // READ
            DirectoryGroup loaded = repository.findById(dn)
                .orElseThrow();
            assertThat(loaded.getMembers())
                .containsExactlyInAnyOrder(
                    personDn("linh"),
                    personDn("an")
                );

            // UPDATE: thêm một DN, gỡ một DN.
            loaded.addMember(personDn("hoa"));
            loaded.removeMember(personDn("an"));
            repository.save(loaded);

            DirectoryGroup updated = repository.findById(dn)
                .orElseThrow();
            assertThat(updated.getMembers())
                .containsExactlyInAnyOrder(
                    personDn("linh"),
                    personDn("hoa")
                )
                .doesNotContain(personDn("an"));

            // DELETE
            repository.deleteById(dn);
            created = false;
            assertThat(repository.findById(dn)).isEmpty();
        } finally {
            if (created) {
                repository.deleteById(dn);
            }
        }
    }
}
```

Các điều kiện của test:

- `ou=groups` và các user member phải tồn tại trong fixture.
- `groupOfUniqueNames` yêu cầu `uniqueMember`; test luôn giữ ít nhất một member.
- UID/group CN được tạo riêng để tránh đụng fixture của test khác.
- Nếu server kiểm tra referential integrity, member DN phải trỏ tới entry thực.
- Khi test fail giữa chừng, khối `finally` dọn group fixture đã tạo.

Đây là ví dụ CRUD trên **một directory test**, không phải lời khẳng định `repository.save` có transaction. Nếu server trả timeout sau khi Add/Modify thành công, cleanup cần đọc lại DN trước khi quyết định trạng thái.

## 9. Kiểm thử ODM cập nhật tập DN theo equality

Spring LDAP ODM hỗ trợ attribute đa trị có giá trị kiểu `Name`. Khi gọi `addMember`/`removeMember` rồi `ldapTemplate.update(group)`, ODM tính các modification dựa trên **DN equality**, không dựa vào cách viết chuỗi DN.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.UUID;
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@DataLdapTest
class DirectoryGroupOdmUpdateTests {

    @Autowired
    private LdapTemplate ldapTemplate;

    private Name groupDn(String cn) {
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", cn)
            .build();
    }

    private Name personDn(String uid) {
        // uniqueMember là DN-valued attribute: dùng DN đầy đủ.
        return LdapNameBuilder.newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }

    @Test
    void odmTracksAddedAndRemovedDnValues() {
        String cn = "lab-" + UUID.randomUUID();
        Name dn = groupDn(cn);
        DirectoryGroup group = new DirectoryGroup();
        group.setDn(dn);
        group.setName(cn);
        group.setMembers(Set.of(personDn("linh"), personDn("an")));

        boolean created = false;
        try {
            ldapTemplate.create(group);
            created = true;

            DirectoryGroup loaded = ldapTemplate.findByDn(
                dn, DirectoryGroup.class);
            loaded.addMember(personDn("hoa"));
            loaded.removeMember(personDn("an"));
            ldapTemplate.update(loaded);

            DirectoryGroup reloaded = ldapTemplate.findByDn(
                dn, DirectoryGroup.class);
            assertThat(reloaded.getMembers())
                .containsExactlyInAnyOrder(
                    personDn("linh"),
                    personDn("hoa")
                )
                .doesNotContain(personDn("an"));
        } finally {
            if (created) {
                ldapTemplate.unbind(dn);
            }
        }
    }
}
```

Điều test cần chứng minh:

- `addMember` thêm đúng DN Hoa.
- `removeMember` chỉ gỡ DN An.
- Linh vẫn còn.
- Reload từ LDAP cho kết quả đúng; không chỉ assert trên object Java đang ở memory.

**Không chỉ gọi getter rồi assert ngay sau setter.** Cách đó kiểm tra Java Set, chưa kiểm tra ODM ghi đúng LDAP. Phải đọc lại entry bằng một operation LDAP mới.

## 10. Thuộc tính nhiều giá trị: không phụ thuộc thứ tự

LDAP attribute là một tập các giá trị theo schema/matching rule, không phải một danh sách có thứ tự ổn định.

### 10.1. Nên dùng Set khi semantics là membership

```java
@Attribute(name = "uniqueMember")
private Set<Name> members;
```

Test đúng:

```java
assertThat(group.getMembers())
    .containsExactlyInAnyOrder(linhDn, anDn);
```

Test không phù hợp:

```java
// Không nên giả định server trả theo thứ tự ghi.
assertThat(group.getMembers())
    .containsExactly(linhDn, anDn);
```

Nếu dùng `List`, hãy coi thứ tự chỉ là thứ tự collection Java sau khi map, không phải cam kết của LDAP server.

### 10.2. DN-valued attribute khác string-valued attribute

| LDAP attribute | Ví dụ value | Java mapping gợi ý |
| --- | --- | --- |
| `uniqueMember` | `uid=linh,ou=people,dc=example,dc=org` | `Set<Name>` |
| `member` | DN đầy đủ của user/group | `Set<Name>` khi ODM converter/schema phù hợp |
| `memberUid` | `linh` | `Set<String>` |
| `mail` (nếu schema cho phép nhiều value) | `linh@example.org` | `Set<String>` hoặc kiểu collection phù hợp converter |
| `objectClass` | `top`, `person`, `inetOrgPerson` | Đọc như tập/collection string qua API phù hợp |

`memberUid` chỉ chứa UID, không chứa DN. Không map nó thành `Set<Name>` vì chuỗi UID không phải một distinguished name.

### 10.3. So sánh DN bằng Name

Hai chuỗi có thể biểu diễn cùng một DN nhưng khác cách viết/format. Ví dụ:

```text
uid=linh,ou=people,dc=example,dc=org
UID=linh,OU=people,DC=example,DC=org
```

Không nên dùng `String.equals` trên `Name.toString()` để xác định DN tương đương. Dùng `LdapNameBuilder`/`LdapName` để xây DN và kiểm tra bằng semantics DN. ODM của Spring LDAP dùng DN equality khi tính delta cho các giá trị kiểu `Name`.

## 11. Kiểm thử bằng LdapTemplate và DirContextAdapter

Repository/ODM không phải cách duy nhất đọc multi-value attribute. `LdapTemplate` và `DirContextAdapter` giúp test trực tiếp giá trị LDAP trước hoặc sau mapping.

### 11.1. Đọc tất cả giá trị string

```java
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations context = ldapTemplate.lookupContext(groupDn);
String[] values = context.getStringAttributes("uniqueMember");
```

Đối với DN-valued attribute, nếu cần nhận object `Name` thay vì chuỗi, hãy dùng mapping ODM `Set<Name>` hoặc API đọc object attributes và chuyển đổi theo schema/representation đã xác minh. Không parse một mảng DN string bằng split dấu phẩy: dấu phẩy có thể xuất hiện trong RDN đã escape.

### 11.2. Kiểm tra delta trước khi ghi

```java
import javax.naming.Name;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

// groupDn là DN tương đối; member DN trong uniqueMember phải đầy đủ.
Name hoaDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people").add("uid", "hoa").build();
Name anDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people").add("uid", "an").build();

DirContextOperations context =
    ldapTemplate.lookupContext(groupDn);

context.addAttributeValue(
    "uniqueMember",
    hoaDn
);
context.removeAttributeValue(
    "uniqueMember",
    anDn
);

ModificationItem[] modifications =
    context.getModificationItems();

assertThat(modifications).isNotEmpty();
ldapTemplate.modifyAttributes(context);
```

Đây là test mức Spring LDAP context adapter:

- Kiểm tra số lượng và loại modification được tạo nếu test cần xác minh delta.
- Sau khi gửi, đọc lại LDAP để xác minh state.
- Không gọi `context.update()` để ghi; `update()` cập nhật snapshot nội bộ của adapter, không gửi ModifyRequest.
- Nếu chỉ muốn thêm/xóa một DN, tránh `setAttributeValues` với toàn bộ snapshot cũ vì có thể tạo REPLACE.

### 11.3. Projection và quyền đọc

Nếu query chỉ yêu cầu một số attribute, hoặc bind account không có quyền đọc `uniqueMember`, kết quả có thể không chứa attribute đó. Test cần phân biệt:

- Attribute thực sự không tồn tại.
- Projection không yêu cầu attribute.
- ACL ẩn attribute.
- Server trả partial result/referral hoặc lỗi đọc.

Không coi `null` là tập rỗng trong mọi tình huống; nếu test muốn xác nhận attribute vắng mặt, hãy dùng bind identity có quyền đọc và truy vấn đầy đủ attribute cần kiểm tra.

## 12. Test filter và query repository

Spring Data LDAP repository có thể sinh query từ tên method hoặc khai báo query. Cần kiểm tra **scope**, **objectClass** và escaping.

### 12.1. Derived query

```java
public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {

    List<DirectoryGroup> findByName(String name);
}
```

Method `findByName` được suy ra từ property entity `name`, được mapping tới LDAP attribute `cn`. Test nên tạo ít nhất hai group fixture và xác minh query trả đúng group, không trả group khác.

### 12.2. LdapQuery trực tiếp

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<DirectoryGroup> groups = repository.findAll(
    query()
        .base("ou=groups")
        .where("cn").is("developers")
);
```

Lợi ích của test trực tiếp:

- Xác nhận search base tương đối đúng.
- Xác nhận filter theo attribute thật.
- Tránh vô tình tìm toàn subtree ngoài phạm vi.
- Dễ viết case âm: không có group, sai OU hoặc filter không khớp.

### 12.3. Kiểm tra filter injection

Không nối chuỗi filter từ input:

```java
// KHÔNG an toàn:
String filter = "(cn=" + userInput + ")";
```

Dùng query builder hoặc repository query parameter được Spring Data LDAP encode theo RFC 4515/RFC 2254 phù hợp version. Với query khai báo có SpEL hoặc property placeholder, cần chú ý các giá trị biểu thức có thể không tự được escape; kiểm thử input có ký tự đặc biệt như `*`, `(`, `)` và `\\`.

## 13. Test schema và trường hợp lỗi

Một test tốt cần chứng minh server **từ chối** entry không hợp lệ, không chỉ kiểm tra đường thành công.

| Trường hợp | Fixture/thao tác | Kỳ vọng |
| --- | --- | --- |
| Thiếu `uniqueMember` trong `groupOfUniqueNames` | Add entry chỉ có `cn` | Server từ chối do vi phạm MUST. |
| Thiếu `cn` | Add group thiếu naming/mandatory attribute | Server từ chối theo schema/naming. |
| `uniqueMember` chứa DN sai syntax | Add giá trị không phải DN hợp lệ | Server/schema từ chối hoặc converter báo lỗi. |
| Member DN không tồn tại | Add group tham chiếu DN giả | Hành vi phụ thuộc server/schema/overlay; không giả định mọi LDAP server kiểm tra referential integrity. |
| Duplicate DN member | ADD cùng value hai lần | Kết quả theo equality matching rule; xử lý duplicate có chủ đích. |
| Remove member không tồn tại | REMOVE một value không có | Server có thể trả noSuchAttribute; service xử lý theo desired state. |
| Remove member cuối cùng | Gỡ giá trị duy nhất của `groupOfUniqueNames` | Server từ chối nếu vi phạm MUST. |
| Bind identity thiếu quyền Modify | Thêm/xóa member | `insufficientAccessRights`. |
| Entry không khớp `objectClasses` của entity | ODM read | Mapping không được coi entry là entity phù hợp hoặc phát sinh lỗi theo API/version. |
| Attribute bị ACL ẩn | Read bằng principal giới hạn | Phân biệt access denied/hidden với attribute rỗng. |
| DN có dấu phẩy escaped | Tạo/tìm member DN đặc biệt | DN builder và ODM map đúng; không split string. |

### 13.1. Đừng tắt schema để làm test xanh

Embedded LDAP có thể cho phép tắt validation hoặc nạp schema tùy chỉnh. Chỉ tắt validation khi test có mục tiêu cụ thể là kiểm tra client mapping trên server không enforce schema. Nếu mục tiêu là xác minh dữ liệu directory hợp lệ, hãy để schema validation hoạt động và tạo fixture đúng.

### 13.2. Không áp quy tắc của groupOfUniqueNames cho mọi nhóm

`groupOfNames`, `groupOfUniqueNames`, `posixGroup` và Active Directory group có schema/semantics khác nhau. Ví dụ `groupOfUniqueNames` dùng `uniqueMember`; `posixGroup` thường dùng `memberUid`; Active Directory dùng linked attribute `member` và có thêm quy tắc riêng. Test phải dùng đúng object class của hệ thống đích.

## 14. Test đồng thời và thay đổi nhiều member

Một lỗi phổ biến là đọc toàn bộ membership, sửa Set trong Java rồi REPLACE toàn bộ attribute. Khi hai test/service cùng làm việc, một writer có thể ghi đè thay đổi của writer khác.

### 14.1. Test delta độc lập

Giả sử nhóm ban đầu có Linh và An:

```text
Initial = {Linh, An}

Writer A: add Hoa
Writer B: remove An

Expected = {Linh, Hoa}
```

Nếu ODM dùng `Set<Name>` và `addMember`/`removeMember` để tạo delta, Spring LDAP tính modification theo DN equality. Tuy nhiên, test vẫn cần đọc lại từ server sau khi cả hai thao tác hoàn tất.

### 14.2. Hai thao tác trên cùng member

Nếu một writer ADD Hoa và writer khác REMOVE Hoa, kết quả phụ thuộc thứ tự server xử lý. LDAP không tự hiểu business rule “event mới hơn thắng”. Nếu nghiệp vụ yêu cầu thứ tự xác định, cần:

- Serialize event theo group stable ID.
- Dùng source version/sequence để loại bỏ event cũ.
- Reconcile từ authoritative membership source.
- Cân nhắc LDAP Assertion Control nếu server hỗ trợ và cần conditional update.

### 14.3. Không dùng @Transactional như rollback LDAP

`@DataLdapTest` không biến LDAP thành database quan hệ có rollback tự động. Một test gọi repository.save/delete hoặc `LdapTemplate.modifyAttributes` đã gửi thao tác tới server; `@Transactional` trên test không đảm bảo hoàn tác các LDAP operation đó.

Hãy dùng DN fixture riêng, `@AfterEach` cleanup, reset embedded server hoặc tạo container mới theo test suite.

## 15. Test cleanup và tính độc lập giữa các test

Các test cần chạy được:

- Một mình.
- Theo thứ tự khác nhau.
- Song song khi fixture độc lập.
- Sau khi test trước thất bại.

### 15.1. Dùng DN duy nhất cho dữ liệu tạo mới

```java
String cn = "test-" + UUID.randomUUID();
Name groupDn = LdapNameBuilder.newInstance("ou=groups")
    .add("cn", cn)
    .build();
```

Không dùng một CN cố định cho test tạo mới nếu suite có thể chạy song song hoặc chạy lại trên server không reset.

### 15.2. Cleanup rõ ràng

```java
@AfterEach
void cleanup() {
    if (createdGroupDn != null) {
        try {
            repository.deleteById(createdGroupDn);
        } catch (EmptyResultDataAccessException ignored) {
            // Fixture đã được xóa trước cleanup.
        }
    }
}
```

Chỉ bắt lỗi “entry không còn tồn tại” khi đó là trạng thái cleanup chấp nhận được. Không catch mọi `DataAccessException` rồi bỏ qua; nếu cleanup lỗi do ACL, schema hoặc network, test environment cần báo lỗi.

### 15.3. Reset fixture khi test thay đổi dữ liệu gốc

Nếu test cập nhật group `developers` có sẵn trong LDIF, có thể:

- Tạo lại embedded server/context cho suite.
- Lưu state ban đầu và khôi phục sau test.
- Dùng một group test riêng thay vì sửa fixture dùng chung.

Không để một test add/remove member làm test kế tiếp phụ thuộc vào trạng thái còn sót.

## 16. Test trên OpenLDAP hoặc Active Directory

Embedded UnboundID phù hợp với kiểm thử mapping và repository cơ bản. Một số behavior cần test trên vendor:

| Behavior | Vì sao cần server tương ứng |
| --- | --- |
| OpenLDAP `memberof` overlay | Overlay phải được cấu hình; UnboundID không tự mô phỏng behavior này. |
| OpenLDAP ACL | Cú pháp và thứ tự ACL phụ thuộc cấu hình OpenLDAP. |
| Active Directory linked `member` | AD quản lý linked attributes và backlink theo semantics riêng. |
| Active Directory range retrieval | Group lớn có thể yêu cầu đọc attribute theo range. |
| Referral/multiple naming context | Cần topology và server endpoint thật. |
| TLS, certificate, SASL/Kerberos | Cần cấu hình truststore, identity và authentication mechanism phù hợp. |
| Password policy/lockout | Phụ thuộc overlay hoặc vendor-specific account policy. |
| Replication lag | Cần nhiều replica hoặc test environment hỗ trợ replication. |

Đối với integration test container:

1. Pin image version, không dùng tag thay đổi theo thời gian.
2. Khởi tạo suffix và schema fixture.
3. Cấu hình bind identity có quyền tối thiểu.
4. Đợi LDAP port và Bind/Search probe thành công trước test.
5. Dùng base DN riêng cho test run.
6. Dọn container sau suite.

Không chạy test destructive trên directory dùng chung hoặc production.

## 17. Ma trận kiểm thử đầy đủ

| Nhóm | Test case | Điều cần assert |
| --- | --- | --- |
| ODM DN | Đọc group theo DN | `@Id Name` đúng, `@DnAttribute` populate đúng. |
| ODM attribute | Đọc `cn` | `@Attribute` ánh xạ đúng. |
| ODM multi-value | Đọc `uniqueMember` | Đủ member trong `Set<Name>`, không phụ thuộc thứ tự. |
| ODM create | Tạo group mới | DN, object classes, mandatory attributes đúng. |
| ODM update | Add/remove một member | Delta đúng, member khác không mất. |
| ODM delete | Xóa fixture group | DN không còn trong directory test. |
| Repository CRUD | save/findById/deleteById | Hành vi CRUD trên server đúng. |
| Repository query | findByName/findAll(LdapQuery) | Search base/filter và kết quả đúng. |
| DN equality | Hai cách biểu diễn cùng DN | Không tạo duplicate do khác format chuỗi. |
| Schema | Thiếu MUST/attribute sai syntax | Server từ chối. |
| ACL | Reader/writer khác quyền | Đúng operation được phép/từ chối. |
| Filter | Ký tự đặc biệt | Parameter encoding không tạo filter injection. |
| Concurrency | Hai delta khác member | Cả hai ý định được giữ. |
| Same-value race | ADD và REMOVE cùng member | Kết quả theo ordering policy, không giả định cố định. |
| Timeout | Response bị mất | Re-read/reconcile trước retry. |
| Cleanup | Test fail giữa chừng | Fixture được dọn hoặc test báo cleanup failure. |
| Vendor | Overlay/AD linked attribute/referral | Behavior khớp server triển khai. |

## 18. Các lỗi thường gặp khi kiểm thử

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho repository | Slice không quét đúng package/repository. | Kiểm tra package test và repository scanning; không tự thêm cấu hình production không cần thiết. |
| `NoSuchObjectException` | Base DN/parent OU hoặc fixture LDIF sai. | Xác minh LDIF, `spring.ldap.base` và DN tương đối. |
| `ObjectClassViolationException` | Thiếu object class hoặc MUST attribute. | Đối chiếu schema và fixture. |
| `ConverterException` | Java field type không có converter tương ứng. | Kiểm tra kiểu attribute, `Set<Name>` và converter mapping. |
| `members` null | Attribute không có, bị projection/ACL ẩn hoặc mapping sai. | Đọc bằng principal có quyền và yêu cầu đúng attribute. |
| Test thứ tự lúc pass lúc fail | Assert List order từ multi-valued attribute. | Dùng Set hoặc assert không phụ thuộc thứ tự. |
| Repository tìm sai OU | Search base rộng/hẹp không đúng. | Ghi rõ base DN và filter trong test. |
| Test pass đơn lẻ nhưng fail cả suite | Fixture dùng chung bị sửa và không cleanup. | DN duy nhất, reset fixture, cleanup trong finally/AfterEach. |
| Test transaction rollback nhưng entry vẫn còn | LDAP operation không được rollback bởi transaction SQL. | Cleanup LDAP tường minh. |
| Member bị mất sau update | Snapshot cũ bị REPLACE hoặc test sửa cùng fixture song song. | Kiểm tra modification delta và cô lập fixture. |
| Test embedded pass, production fail | ACL/schema/overlay/vendor khác nhau. | Thêm contract test trên đúng LDAP server. |
| Assertion DN string thất bại | So sánh chuỗi DN format khác nhau. | So sánh bằng `Name`/DN equality. |

## 19. Checklist trước khi merge

- [ ] Test chạy trên LDAP server cô lập, không dùng production.
- [ ] Fixture LDIF có base DN, parent OU, entry và group đúng schema.
- [ ] Entity có `@Entry` và `@Id Name`.
- [ ] `@DnAttribute` và `@Attribute` được kiểm tra cả khi đọc và ghi.
- [ ] Attribute DN-valued được map thành `Set<Name>`.
- [ ] Assertion không phụ thuộc thứ tự LDAP trả về.
- [ ] Repository test có CRUD và ít nhất một query theo đúng scope.
- [ ] Update test reload entry từ LDAP trước khi assert.
- [ ] Có negative test cho schema, DN và ACL.
- [ ] Test không dựa vào `@Transactional` để rollback LDAP.
- [ ] Fixture mới có DN duy nhất; cleanup xử lý cả đường thành công và lỗi.
- [ ] Test concurrency phân biệt delta khác member với race cùng member.
- [ ] Query parameter được encode an toàn; không nối raw filter.
- [ ] Behavior vendor-specific có integration test trên đúng loại directory.
- [ ] Version Spring Boot và package `@DataLdapTest` được khớp.

## 20. Bài tập thực hành

1. Tạo embedded LDAP server có base `dc=example,dc=org` và nạp LDIF chứa hai user, một group `groupOfUniqueNames`.
2. Viết entity `DirectoryGroup` với `@Id Name`, `@DnAttribute("cn")` và `Set<Name> uniqueMember`.
3. Viết `DirectoryGroupRepository extends LdapRepository<DirectoryGroup>`.
4. Kiểm thử `findById` và `findByName`; giải thích attribute `name` được map tới `cn` như thế nào.
5. Tạo group mới có hai member; lưu qua repository và đọc lại từ LDAP.
6. Thêm một member, gỡ một member; xác minh member thứ ba không bị mất.
7. Viết test xác nhận thứ tự member không được giả định.
8. Tạo test thiếu `uniqueMember` và quan sát schema violation.
9. Thay `Set<Name>` bằng `Set<String>`; mô tả khác biệt trong equality và conversion khi xử lý DN.
10. Tạo test với DN chứa dấu phẩy trong RDN; dựng bằng `LdapNameBuilder` và xác minh không split chuỗi thủ công.
11. Chạy hai test song song với fixture group riêng; chứng minh không có collision.
12. Tạo test timeout giả lập sau ModifyRequest và thiết kế bước reconcile trước retry.
13. Chạy cùng test trên OpenLDAP/Active Directory test server; ghi lại khác biệt schema, ACL và membership behavior.

## 21. Tài liệu tham khảo

- [Spring Boot — Testing Applications, Auto-configured Data LDAP Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataLdapTest`, embedded LDAP, `LdapTemplate` và repository scan.
- [Spring Boot — Working with NoSQL Technologies, LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): embedded UnboundID, `spring.ldap.embedded.base-dn` và LDIF initialization.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `Set<Name>` cho DN-valued attribute.
- [Spring LDAP — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): đọc attribute nhiều giá trị và theo dõi modification delta.
- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): embedded server, UnboundID, ApacheDS và fixture LDIF.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories`, kiểu ID `Name`, giới hạn paging/sorting.
- [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html): entity ODM và repository CRUD.
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): derived query, `@Query` và parameter encoding.
- [Oracle Java SE 17 — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html): biểu diễn, so sánh và thao tác DN.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Add, Modify, Delete và kết quả LDAP.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute, objectClass, schema và matching rule.
- [RFC 4514 — Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN và escaping.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escaping giá trị.
