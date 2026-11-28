# Dùng các thao tác ODM create, update và delete

## 1. ODM giúp ghi entry LDAP bằng object Java như thế nào?

Trong **Spring Data LDAP**, ứng dụng có thể ánh xạ một entry trong directory thành object Java bằng cơ chế **Object-Directory Mapping (ODM)**. Các annotation mô tả `objectClass`, DN và thuộc tính LDAP; `LdapTemplate` sử dụng metadata đó để tạo, đọc, cập nhật hoặc xóa entry.

Ví dụ một nhân viên được lưu trong directory:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84 28 1234 5678
~~~

Ứng dụng có thể ánh xạ entry này thành `PersonEntry`, thay đổi email rồi gọi `ldapTemplate.update(person)`. Spring LDAP đọc trạng thái hiện tại và tạo các LDAP modification cần thiết cho object đã ánh xạ.

Ba thao tác ghi chính của ODM là:

- **Create:** tạo entry mới theo DN và `objectClass` đã khai báo.
- **Update:** đồng bộ trạng thái của object đã ánh xạ với entry đang tồn tại.
- **Delete:** xóa entry theo DN của object.

ODM giúp giảm việc tự tạo `Attributes` và `ModificationItem` cho những trường hợp thông thường. Tuy nhiên, LDAP vẫn là directory phân cấp, có schema, DN và quy tắc liên kết riêng. Các thao tác ODM không có nghĩa LDAP trở thành một cơ sở dữ liệu quan hệ có cascade, upsert hoặc transaction nhiều entry.

Sau bài này, người học có thể:

1. Khai báo entity ODM với `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient`.
2. Tạo entry bằng `LdapTemplate.create`.
3. Cập nhật attribute bằng `LdapTemplate.update`.
4. Xóa entry bằng `LdapTemplate.delete`.
5. Dùng `LdapRepository` cho CRUD theo DN.
6. Phân biệt cập nhật attribute, di chuyển entry và thao tác ModifyDN.
7. Xử lý schema, quyền, tham chiếu và lỗi ghi một cách an toàn.
8. Kiểm thử vòng đời CRUD trên LDAP directory.

> **Nguyên tắc:** ODM quản lý việc ánh xạ object với entry. DN, schema, ACL và hành vi của LDAP server vẫn quyết định thao tác có hợp lệ hay không.

## 2. Mô hình ánh xạ ODM

Một class được ODM quản lý cần có metadata để Spring LDAP biết cách tạo và đọc entry.

### 2.1. Các annotation chính

| Annotation | Vai trò | Ghi chú |
| --- | --- | --- |
| `@Entry` | Khai báo các `objectClass` và base DN tùy chọn | Bắt buộc với entity ODM |
| `@Id` | Ánh xạ DN của entry vào object | Field phải có kiểu `javax.naming.Name` hoặc kiểu dẫn xuất |
| `@Attribute` | Ánh xạ field Java tới LDAP attribute | Dùng khi tên field khác tên attribute hoặc cần khai báo kiểu |
| `@DnAttribute` | Ánh xạ field với một thành phần RDN trong DN | Chỉ hỗ trợ field kiểu `String` |
| `@Transient` | Đánh dấu field không được lưu thành LDAP attribute | Hữu ích với field tính toán hoặc dữ liệu chỉ dùng trong ứng dụng |

`@Entry` và `@Id` là hai annotation bắt buộc. Các field không có annotation đặc biệt thường được ánh xạ theo tên field Java sang LDAP attribute cùng tên. Vì vậy, không nên thêm field phụ vào entity mà không quyết định rõ nó có được lưu vào directory hay không.

### 2.2. `@Entry` và objectClass

Ví dụ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    base = "ou=people",
    objectClasses = {
        "inetOrgPerson",
        "organizationalPerson",
        "person",
        "top"
    }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute("uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Transient
    private String displayLabel;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getDisplayLabel() { return displayLabel; }
    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
~~~

Trong ví dụ:

- `@Entry` khai báo nhóm object class mà entity quản lý và base `ou=people`.
- `@Id` giữ DN của entry.
- `uid` vừa là LDAP attribute vừa là thành phần RDN, nên có cả `@Attribute` và `@DnAttribute`.
- `displayLabel` chỉ dùng trong Java, không được ghi vào LDAP vì có `@Transient`.

Khi tạo entry, ODM chỉ sử dụng các `objectClass` đã khai báo. Những object class và attribute phải phù hợp schema của directory. Khi đọc/mapping entry đã tồn tại, tất cả `objectClass` của entry phải nằm trong danh sách `@Entry` để entry được xem là phù hợp với entity ODM. Vì vậy, hãy khai báo đủ các object class mà entity cần quản lý; không giả định ODM tự giữ mọi object class không có trong metadata khi tạo entry mới.

### 2.3. `@Id` và DN

DN là định danh của entry trong cây LDAP. Field `@Id` phải có kiểu `Name`:

~~~java
@Id
private Name dn;
~~~

Một DN có thể được cung cấp trực tiếp:

~~~java
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "alice")
    .build();

person.setDn(dn);
~~~

Đoạn ví dụ giả định `ContextSource.base=dc=example,dc=org`; DN truyền cho Spring LDAP là DN tương đối với base đó. Khi cấu hình base khác, hãy xác định rõ DN đang dùng là relative hay full DN để tránh lặp suffix.

Không ghép DN bằng phép cộng chuỗi hoặc tách bằng dấu phẩy. Dùng `LdapNameBuilder` hoặc `LdapName` để xử lý escape và cấu trúc RDN đúng quy tắc.

### 2.4. `@DnAttribute` và giá trị RDN

`@DnAttribute` cho phép ODM đọc một giá trị từ DN thay vì chỉ đọc LDAP attribute cùng tên:

~~~java
@DnAttribute("uid")
private String uid;
~~~

Với DN:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

ODM có thể lấy `alice` từ thành phần `uid=alice` của DN. Nếu không có DN tường minh trong `@Id`, ODM có thể tính DN từ các field được đánh dấu `@DnAttribute`; khi tính được, DN được gán lại vào object.

`@DnAttribute` chỉ hỗ trợ field kiểu `String`. Có thể dùng `index` khi DN có nhiều thành phần RDN cùng cần ánh xạ; nếu chỉ định `index`, giá trị `name` bị bỏ qua. Chỉ số phải tuân theo cách Spring LDAP xử lý thứ tự RDN; hãy kiểm tra bằng test cho DN thực tế thay vì tự suy ra từ cách chuỗi DN được viết.

Một lưu ý dễ bỏ qua: `@DnAttribute` không tự làm field trở thành transient. Field này vẫn được ánh xạ thành LDAP attribute theo mặc định. Nếu field chỉ biểu diễn một thành phần DN và không phải attribute cần lưu, hãy kết hợp `@Transient`.

### 2.5. Kiểu dữ liệu và converter

ODM cần chuyển đổi giữa Java type và LDAP attribute value. Những trường chuỗi đơn giản thường được ánh xạ trực tiếp. Với thuộc tính đa trị, binary hoặc kiểu miền riêng, cần kiểm tra converter và syntax của attribute.

Ví dụ:

| LDAP attribute | Java representation thường gặp | Lưu ý |
| --- | --- | --- |
| `cn`, `sn`, `mail` | `String` | Attribute chuỗi đơn trị hoặc đa trị tùy schema |
| `uniqueMember` | `Set<Name>` | Giá trị là DN; phải bảo toàn cấu trúc Name |
| `jpegPhoto` | `byte[]` | Dữ liệu binary |
| `objectGUID` | `byte[]` | Binary identifier trong Active Directory |
| Ngày giờ tùy schema | Kiểu Java phù hợp hoặc `String` | Cần converter và định dạng thống nhất |

Không chuyển binary attribute bằng `String.valueOf(byte[])`. Nếu ứng dụng cần kiểu Java riêng, có thể đăng ký `Converter` phù hợp với `ObjectDirectoryMapper`/`ConversionService` theo cấu hình phiên bản đang dùng.

## 3. Cấu hình LdapTemplate và repository

### 3.1. LdapTemplate

`LdapTemplate` sử dụng `ContextSource` để kết nối directory. Nó có thể tạo `ObjectDirectoryMapper` mặc định để xử lý các annotation ODM.

Ví dụ cấu hình Java tối giản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn("uid=app-writer,ou=service-accounts,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Đây là ví dụ minh họa. Trong production, credential nên được cấp từ secret manager hoặc cấu hình bảo mật của môi trường; xác minh TLS certificate và hostname. Tài khoản ghi chỉ nên có quyền trên các nhánh và attribute cần thiết.

### 3.2. Repository ODM

Spring Data LDAP hỗ trợ repository trên entity đã khai báo ODM:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {
}
~~~

`LdapRepository<T>` dùng `Name` làm kiểu ID mặc định vì ID của entity LDAP là DN. Có thể dùng các thao tác CRUD như:

~~~java
personRepository.save(person);
personRepository.findById(dn);
personRepository.existsById(dn);
personRepository.delete(person);
personRepository.deleteById(dn);
~~~

Nếu muốn truyền `LdapQuery` vào repository, hãy mở rộng `LdapRepository` thay vì chỉ `CrudRepository`.

Spring Data LDAP sử dụng annotation ODM của Spring LDAP, đặc biệt là `org.springframework.ldap.odm.annotations.Id`. Không thay bằng annotation `org.springframework.data.annotation.Id` hoặc annotation `@Id` của JPA trong entity LDAP.

### 3.3. Bật repository scanning

Có thể kích hoạt repository bằng `@EnableLdapRepositories`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(basePackages = "com.example.directory.repository")
public class LdapRepositoryConfiguration {
}
~~~

Hãy bảo đảm repository được nối với `LdapTemplate`/`ContextSource` đúng directory. Nếu ứng dụng có nhiều directory hoặc nhiều `LdapTemplate`, cần cấu hình repository tương ứng để không ghi nhầm nguồn.

## 4. Create: tạo entry mới bằng ODM

### 4.1. Tạo DN từ `@DnAttribute`

Với `PersonEntry` ở trên, base của entity là `ou=people` và field `uid` là DN attribute. Ta có thể để ODM tính DN:

~~~java
import org.springframework.ldap.core.LdapTemplate;

public PersonEntry createPerson(
        LdapTemplate ldapTemplate,
        String uid,
        String commonName,
        String surname,
        String email) {

    PersonEntry person = new PersonEntry();
    person.setUid(uid);
    person.setCommonName(commonName);
    person.setSurname(surname);
    person.setEmail(email);

    ldapTemplate.create(person);

    // Sau create, ODM có thể gán DN đã tính vào field @Id.
    return person;
}
~~~

Với base `ou=people` và `ContextSource.base=dc=example,dc=org`, DN dự kiến là:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Để tránh xung đột, `uid` phải phù hợp naming rule và chưa được dùng trong phạm vi cần duy nhất. DN mới cũng cần parent `ou=people` đã tồn tại.

### 4.2. Create với DN tường minh

Nếu không muốn tính DN từ `@DnAttribute`, có thể set `@Id` trước khi gọi create:

~~~java
Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "alice")
    .build();

PersonEntry person = new PersonEntry();
person.setDn(dn);
person.setUid("alice");
person.setCommonName("Alice Nguyen");
person.setSurname("Nguyen");
person.setEmail("alice@example.org");

ldapTemplate.create(person);
~~~

Khi `@Id` đã có giá trị, ODM sử dụng DN đó cho entry mới. Cách này hữu ích khi DN được xác định bởi một quy tắc nghiệp vụ rõ ràng hoặc khi entity không có đủ `@DnAttribute` để tự tính.

Không cung cấp đồng thời một DN tường minh và các field RDN mâu thuẫn. Ví dụ `@Id` trỏ tới `uid=alice` nhưng field `uid` lại là `bob` sẽ tạo ra một object không nhất quán; cần validate trước khi ghi.

### 4.3. Điều kiện để create thành công

Create phải thỏa những điều kiện chính:

1. DN có thể được xác định từ `@Id` hoặc `@DnAttribute`.
2. Parent entry tồn tại.
3. DN chưa được entry khác sử dụng.
4. Các `objectClass` được khai báo tồn tại trong schema.
5. Các MUST attributes của object class có đủ giá trị.
6. Attribute syntax, cardinality và naming rule hợp lệ.
7. Bind identity có quyền Add tại parent đích.

Ví dụ `inetOrgPerson` yêu cầu các thuộc tính theo schema của nó, trong đó `cn` và `sn` là các thuộc tính bắt buộc. Nếu thiếu, server có thể trả lỗi schema violation.

### 4.4. Create không phải upsert

`ldapTemplate.create(person)` tạo entry mới. Nếu DN đã tồn tại, thao tác sẽ thất bại với lỗi entry đã tồn tại; nó không tự chuyển thành update.

Đừng viết logic kiểu “gọi create, nếu có lỗi thì bỏ qua”. Cần xác định nghiệp vụ:

- Nếu phải tạo mới, kiểm tra collision và trả lỗi rõ.
- Nếu muốn cập nhật khi đã tồn tại, đọc entry theo DN rồi thực hiện update có kiểm soát.
- Nếu muốn hành vi create-or-update, xây service riêng để phân giải trạng thái và xử lý race condition.

Kiểm tra `existsById` trước create chỉ là preflight; client khác vẫn có thể tạo cùng DN giữa lần kiểm tra và thao tác Add. LDAP server là nơi quyết định xung đột cuối cùng.

## 5. Read: đọc object đã ánh xạ

ODM cũng cung cấp các thao tác đọc để lấy object trước khi update/delete.

### 5.1. Tìm theo DN

~~~java
import javax.naming.Name;

PersonEntry person = ldapTemplate.findByDn(dn, PersonEntry.class);
~~~

`findByDn` đọc entry tại DN và ánh xạ sang class ODM. DN phải trỏ tới entry phù hợp với `@Entry` metadata.

### 5.2. Tìm theo filter

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

PersonEntry person = ldapTemplate.findOne(
    query()
        .base("ou=people")
        .where("uid").is("alice"),
    PersonEntry.class
);
~~~

Với giá trị input động, dùng query builder để tạo filter an toàn; không nối chuỗi filter từ input. Nếu không tìm thấy, xử lý kết quả theo API và phiên bản đang dùng, không giả định lúc nào cũng có object.

### 5.3. Repository findById

~~~java
Optional<PersonEntry> result =
    personRepository.findById(dn);
~~~

`findById` dùng DN làm ID. DN có thể thay đổi nếu entry được rename/move, do đó không nên coi DN là stable business identifier nếu nghiệp vụ cần nhận diện cùng một đối tượng qua các lần di chuyển.

## 6. Update: cập nhật attribute của entry

### 6.1. Đọc rồi thay đổi object

Một workflow cập nhật thường gồm:

1. Đọc entry hiện tại.
2. Thay đổi những field nghiệp vụ cần thiết.
3. Gọi `ldapTemplate.update(entry)`.
4. Đọc lại entry để xác minh.

Ví dụ:

~~~java
public PersonEntry updateEmail(
        LdapTemplate ldapTemplate,
        Name dn,
        String newEmail) {

    PersonEntry person =
        ldapTemplate.findByDn(dn, PersonEntry.class);

    person.setEmail(newEmail);

    ldapTemplate.update(person);

    return ldapTemplate.findByDn(dn, PersonEntry.class);
}
~~~

`update` dùng metadata ODM để xác định attribute cần ghi. Khi DN không đổi, Spring LDAP đọc trạng thái hiện tại trong directory, tính các khác biệt và thực hiện LDAP Modify với những `ModificationItem` tương ứng.

Điều này giúp ứng dụng không phải tự tạo `BasicAttribute` và `ModificationItem` cho từng field thông thường.

### 6.2. Update là đồng bộ trạng thái object, không phải PATCH tùy ý

Hãy đọc object đầy đủ trước khi thay đổi:

~~~java
PersonEntry person = ldapTemplate.findByDn(dn, PersonEntry.class);
person.setEmail("alice.new@example.org");
ldapTemplate.update(person);
~~~

Không tạo một object mới chỉ có `dn` và `email`, rồi dùng nó như một PATCH object nếu chưa thiết kế rõ cách các field còn lại được xử lý. ODM làm việc với các field được ánh xạ; field null hoặc tập giá trị rỗng có thể dẫn tới thay đổi/xóa attribute tùy mapping và trạng thái hiện tại.

Nếu chỉ muốn thay một attribute mà không đọc/mapping toàn entity, `LdapTemplate.modifyAttributes(...)` có thể phù hợp hơn vì thay đổi được chỉ định rõ ràng. Hãy phân biệt hai nhu cầu:

- **ODM update:** cập nhật object đã ánh xạ và so sánh với entry hiện tại.
- **Explicit attribute modification:** chỉ thay đổi attribute cụ thể theo yêu cầu.

### 6.3. Attribute đa trị

Với attribute đa trị, ODM có thể ánh xạ vào collection phù hợp. Ví dụ nhóm dùng `uniqueMember` chứa các DN:

~~~java
@Entry(
    objectClasses = {"top", "groupOfUniqueNames"},
    base = "ou=groups"
)
public class GroupEntry {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute("cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members;

    // getters/setters
}
~~~

Sau khi đọc group, có thể thêm hoặc xóa một thành viên:

~~~java
group.getMembers().add(memberDn);
ldapTemplate.update(group);

group.getMembers().remove(memberDn);
ldapTemplate.update(group);
~~~

ODM hỗ trợ giá trị attribute kiểu `Name`; khi tính khác biệt, DN được so sánh theo ngữ nghĩa của `Name`, không chỉ theo cách viết chuỗi. Điều này hữu ích khi định dạng textual DN khác nhau nhưng DN tương đương.

Tuy nhiên, `groupOfUniqueNames` yêu cầu `uniqueMember` theo schema. Không xóa thành viên cuối cùng nếu việc đó khiến entry vi phạm schema. Cũng cần giữ đúng cú pháp `NameAndOptionalUID` nếu ứng dụng dùng optional UID component.

### 6.4. Field tính toán và `@Transient`

Một field chỉ phục vụ hiển thị không nên vô tình trở thành LDAP attribute:

~~~java
@Transient
private String displayLabel;
~~~

Nếu bỏ `@Transient`, ODM có thể ánh xạ field theo tên Java. Khi object được update, field đó có thể tham gia quá trình ghi và dẫn tới lỗi attribute không có trong schema hoặc lưu dữ liệu ngoài dự kiến.

Với `@DnAttribute`, hãy nhớ field vẫn được ánh xạ như LDAP attribute theo mặc định. Chỉ thêm `@Transient` khi thành phần DN đó không cần được lưu thành attribute riêng.

## 7. Khi update làm thay đổi DN

Đây là khác biệt quan trọng trong ODM.

### 7.1. Thay đổi RDN field có thể dẫn tới move

Nếu class dùng `@DnAttribute` để tính DN và field cấu thành DN thay đổi, DN tính được có thể khác DN cũ. API ODM `update` hỗ trợ trường hợp này: nếu DN được tính lại khác DN hiện tại, implementation có thể thực hiện **unbind entry cũ rồi bind entry mới**.

Ví dụ:

~~~text
DN cũ:
uid=alice,ou=people,dc=example,dc=org

DN tính mới:
uid=alice.nguyen,ou=people,dc=example,dc=org
~~~

Khi field `uid` đổi, DN được tính từ `@DnAttribute` có thể thay đổi theo.

### 7.2. ODM move không giống LDAP ModifyDN

Theo API Spring LDAP, đường update khi DN tính được khác có thể là:

~~~text
unbind(old DN)
bind(new DN)
~~~

Đây là một thao tác xóa entry cũ rồi bind entry mới theo mapping. Nó **khác với LDAP ModifyDN** được server thực hiện bằng `modrdn`.

Sự khác biệt có ý nghĩa thực tế:

- Server-side referential integrity có thể hoạt động khác khi nhận ModifyDN so với chuỗi unbind/bind.
- DN references trong `member`, `uniqueMember`, `manager` hoặc custom attributes có thể cần được cập nhật riêng.
- Operational metadata, audit và replication có thể khác.
- Nếu bind mới thất bại sau khi unbind cũ thành công, entry có thể tạm thời không tồn tại ở cả hai DN.

Nếu nghiệp vụ thực sự yêu cầu rename/move theo semantics của LDAP ModifyDN, hãy dùng `LdapTemplate.rename(oldDn, newDn)` và xử lý tham chiếu theo chính sách của directory. Không đổi field `@DnAttribute` rồi giả định `update` luôn gọi ModifyDN.

### 7.3. Khi nào nên dùng `LdapTemplate.rename`?

Dùng explicit rename khi:

- Cần đổi RDN hoặc parent theo thao tác ModifyDN của server.
- Muốn tận dụng cơ chế referential integrity/linked attributes đã cấu hình.
- Cần kiểm soát rõ old DN và new DN.
- Muốn tách việc đổi vị trí entry khỏi việc cập nhật các attribute nghiệp vụ khác.

Ví dụ:

~~~java
ldapTemplate.rename(oldDn, newDn);
~~~

Sau rename, object Java đã nạp trước đó có thể vẫn giữ DN cũ. Hãy đọc lại entry theo DN mới, xác minh stable ID nếu có và cập nhật field `@Id`/mapping nội bộ theo trạng thái mới.

## 8. Delete: xóa entry theo ODM

### 8.1. Xóa object đã đọc

~~~java
PersonEntry person = ldapTemplate.findByDn(dn, PersonEntry.class);

ldapTemplate.delete(person);
~~~

`LdapTemplate.delete(Object)` lấy DN từ field `@Id`; nếu không có DN tường minh, ODM có thể tính DN từ các field `@DnAttribute`.

Delete yêu cầu entry tồn tại và bind identity có quyền xóa. Nếu entry đã bị xóa hoặc DN không hợp lệ, server/provider có thể trả lỗi.

### 8.2. Delete theo repository

~~~java
personRepository.delete(person);
personRepository.deleteById(dn);
~~~

Repository cung cấp các method CRUD chuẩn. `deleteById` sử dụng DN làm ID. Nếu ứng dụng cần xác minh trước khi xóa, nên thực hiện kiểm tra nghiệp vụ và quyền tại service layer thay vì để controller gọi thẳng repository.

### 8.3. LDAP không tự cascade delete như ORM

Nếu entry có child entries, server LDAP thông thường không cho phép xóa parent trước khi xử lý các entry con. Ví dụ:

~~~text
ou=people,dc=example,dc=org
└── uid=alice,ou=people,dc=example,dc=org
~~~

Không thể giả định xóa `ou=people` sẽ tự xóa Alice. Với subtree, cần quy trình rõ ràng:

1. Xác định phạm vi subtree được phép xóa.
2. Liệt kê descendants và các DN references liên quan.
3. Xử lý child entries theo thứ tự phù hợp, thường từ leaf lên parent.
4. Cập nhật/xóa references ở các entry khác theo chính sách.
5. Xóa parent sau khi không còn child.
6. Xác minh kết quả và ghi audit.

Không dùng `deleteAll()` trên repository trong một service nghiệp vụ thông thường; đây là thao tác có phạm vi rộng và có thể xóa toàn bộ entity thuộc repository base.

### 8.4. Delete và tham chiếu từ entry khác

LDAP không tự đảm bảo mọi attribute chứa DN sẽ được cập nhật hoặc xóa khi entry đích bị xóa. Tùy server, overlay hoặc linked attributes có thể hỗ trợ một số quan hệ; các custom attributes có thể không được quản lý.

Trước khi xóa user, kiểm tra:

- `member` và `uniqueMember` của các nhóm.
- `manager`, `owner`, `seeAlso`.
- Custom DN-valued attributes.
- Database và cache bên ngoài.
- Các hệ thống tích hợp sử dụng DN.

Nếu quan hệ cần được duy trì, hãy xóa/thay reference theo workflow có kiểm tra. Không giả định `ldapTemplate.delete(person)` sẽ cascade sang mọi group.

### 8.5. Xóa cứng hay vô hiệu hóa?

Một số hệ thống IAM không xóa entry ngay khi nhân viên nghỉ việc. Thay vào đó, chúng có thể khóa tài khoản, chuyển OU, xóa quyền hoặc giữ tombstone theo chính sách lưu trữ.

Các attribute vô hiệu hóa tài khoản khác nhau giữa directory vendor. Ví dụ một số thuộc tính account-control của Active Directory không có semantics tương đương trong OpenLDAP. Hãy dùng policy/attribute đúng server và nghiệp vụ; không tự đặt một attribute chung rồi cho rằng mọi directory hiểu như nhau.

## 9. Repository `save`: create hay update?

### 9.1. Save phụ thuộc vào trạng thái mới của entity

`LdapRepository` kế thừa CRUD contract của Spring Data. Với implementation mặc định, repository cần quyết định entity là mới hay đã tồn tại để chọn create hoặc update.

Trong cách xác định mặc định, DN là ID của entity:

- ID chưa có (`null`): entity được xem là mới và luồng save gọi create.
- ID đã có: entity được xem là đã tồn tại và luồng save gọi update.
- Nếu entity triển khai `Persistable`, trạng thái `isNew()` có thể được dùng để điều khiển quyết định này.

Điểm cần chú ý: ODM có thể tính DN từ `@DnAttribute` trong lúc create. Nếu dùng repository `save`, hãy kiểm tra cách entity được nhận diện là mới trong phiên bản Spring Data LDAP đang dùng. Khi cần chắc chắn thao tác là create hoặc update, gọi trực tiếp `ldapTemplate.create(...)` hoặc `ldapTemplate.update(...)` ở service phù hợp.

### 9.2. `save` không phải upsert nguyên tử

Không coi `save` là SQL `INSERT ... ON CONFLICT DO UPDATE`. Việc xác định entity mới và thao tác LDAP là các bước có thể gặp race:

~~~text
Worker A: kiểm tra entity chưa tồn tại
Worker B: tạo entry tại DN đó
Worker A: gọi create
LDAP server: entryAlreadyExists
~~~

Nếu có nhiều writer, phải xử lý conflict theo nghiệp vụ. Không bắt mọi lỗi create rồi gọi update một cách mù quáng vì có thể cập nhật nhầm entry hoặc ghi đè dữ liệu của một đối tượng khác.

### 9.3. `saveAll` không tạo transaction cho toàn bộ batch

`saveAll` thuận tiện khi lưu nhiều object, nhưng không có nghĩa tất cả LDAP operations trở thành một transaction nguyên tử. Nếu entry thứ 5 thất bại, các entry trước đó có thể đã được ghi thành công.

Với batch lớn:

- Xác định trạng thái thành công/thất bại theo từng entry.
- Dùng stable identifier và idempotent handling.
- Lưu progress nếu cần resume.
- Không đánh dấu cả batch thành công chỉ vì một số entry đã ghi được.

## 10. Lỗi thường gặp khi thực hiện ODM CRUD

| Lỗi | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Entry đã tồn tại khi create | DN bị trùng hoặc create được gọi hai lần | Đọc lại theo DN/stable ID và phân giải conflict |
| Không tính được DN | Thiếu `@Id` và `@DnAttribute` không đủ dữ liệu | Bổ sung DN hoặc field RDN hợp lệ |
| Parent không tồn tại | Base/OU đích chưa được tạo | Tạo parent theo thứ tự và kiểm tra naming context |
| ObjectClass violation | Thiếu MUST attribute hoặc object class không hợp schema | Kiểm tra schema và fixture |
| Insufficient access rights | Bind identity thiếu quyền Add/Modify/Delete | Cấp quyền tối thiểu trên đúng subtree/attribute |
| Attribute syntax error | Java type hoặc giá trị không đúng LDAP syntax | Kiểm tra converter, binary và multivalue mapping |
| Entry không tìm thấy khi update | DN sai, entry bị move/xóa hoặc ID stale | Resolve lại theo stable ID và trạng thái nguồn |
| Delete bị từ chối | Entry có child hoặc ACL không cho phép | Xử lý subtree/permission theo policy |
| Update xóa field ngoài ý muốn | Entity không đầy đủ hoặc null/empty mapping chưa được hiểu | Đọc đầy đủ entity và test null/empty semantics |
| Move làm mất group reference | ODM update thực hiện unbind/bind | Dùng ModifyDN khi cần semantics server và reconcile references |
| Lỗi giao tiếp sau write | Không biết server đã commit hay chưa | Đọc lại DN và attributes trước khi retry |

### 10.1. CommunicationException sau create/update/delete

Nếu client mất kết nối trong lúc ghi, response có thể bị mất sau khi server đã xử lý operation. Không retry mù quáng.

- **Create:** lookup DN đích và xác minh stable ID/attributes. Nếu entry đã được tạo đúng, coi bước create đã hoàn thành.
- **Update:** đọc lại entry và so sánh các attribute cần thay đổi.
- **Delete:** lookup DN; xác minh entry đã vắng mặt và không phải một endpoint/replica khác đang trả dữ liệu cũ.
- Nếu không thể xác định trạng thái, giữ operation ở trạng thái chưa rõ và đối soát trước khi tiếp tục.

Với thao tác có tác động nhiều entry, cần lưu operation ID và trạng thái từng bước. LDAP không mặc định cung cấp transaction ACID xuyên nhiều entry; `@Transactional` của database ứng dụng không tự bao trùm LDAP.

## 11. Kiểm thử ODM create, update và delete

Unit test có thể kiểm tra service gọi đúng method, nhưng integration test với LDAP directory mới xác minh được schema, DN, objectClass và ACL thực tế.

### 11.1. Fixture LDIF

Một fixture tối thiểu:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

Root `dc=example,dc=org` phải được tạo bởi directory bootstrap hoặc fixture trước đó. Không nạp lại entry root nếu test server đã có sẵn.

### 11.2. Integration test vòng đời CRUD

Ví dụ với `LdapTemplate`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PersonOdmIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void createReadUpdateDeleteEntry() {
        PersonEntry person = new PersonEntry();
        person.setUid("alice-test");
        person.setCommonName("Alice Test");
        person.setSurname("Test");
        person.setEmail("alice-test@example.org");

        ldapTemplate.create(person);

        assertThat(person.getDn()).isNotNull();

        PersonEntry loaded =
            ldapTemplate.findByDn(person.getDn(), PersonEntry.class);

        assertThat(loaded.getUid()).isEqualTo("alice-test");
        assertThat(loaded.getEmail())
            .isEqualTo("alice-test@example.org");

        loaded.setEmail("alice-updated@example.org");
        ldapTemplate.update(loaded);

        PersonEntry updated =
            ldapTemplate.findByDn(loaded.getDn(), PersonEntry.class);

        assertThat(updated.getEmail())
            .isEqualTo("alice-updated@example.org");

        ldapTemplate.delete(updated);

        assertThat(ldapTemplate.findAll(
            PersonEntry.class
        )).noneMatch(p -> "alice-test".equals(p.getUid()));
    }
}
~~~

Test giả định `PersonEntry` sử dụng `@Entry(base="ou=people")`, `@DnAttribute("uid")` và fixture OU đã tồn tại. Dùng UID riêng cho từng test để tránh xung đột. Trong suite thực tế, nên xác minh entry không còn bằng lookup DN cụ thể và xử lý exception “not found” theo đúng phiên bản Spring LDAP.

### 11.3. Test schema và collision

Tạo các test riêng cho:

- Thiếu `sn` hoặc `cn` bắt buộc.
- DN đã tồn tại.
- Parent OU không tồn tại.
- `objectClass` không được schema hỗ trợ.
- Giá trị attribute sai syntax.
- Bind identity chỉ đọc.
- DN được tính từ `@DnAttribute` khi field thiếu.
- Field `@Transient` không được ghi.
- Field `@DnAttribute` đồng thời map attribute theo đúng annotation.

Các test này giúp phát hiện lỗi mapping trước khi triển khai lên directory dùng chung.

### 11.4. Test hành vi update khi DN thay đổi

Nếu class sử dụng `@DnAttribute`, hãy kiểm thử riêng hai tình huống:

1. Chỉ đổi email: ODM update chỉ sửa attribute và giữ DN.
2. Đổi field cấu thành DN: xác minh implementation đang dùng thực hiện move theo semantics ODM, và kiểm tra references liên quan.

Nếu nghiệp vụ cần server-side ModifyDN, test phải gọi `LdapTemplate.rename` và xác minh hành vi của đúng LDAP vendor. Không dùng kết quả test ODM unbind/bind để kết luận server referential integrity đã hoạt động.

### 11.5. Test delete với entry có child

Tạo một OU có entry con, thử delete parent và xác minh server từ chối theo semantics của directory. Sau đó xóa child rồi xóa parent theo thứ tự phù hợp. Test này ngăn ứng dụng giả định có cascade delete.

## 12. Bảo mật khi ghi dữ liệu directory

- Chỉ cấp quyền Add, Modify, Delete trên đúng OU và attribute mà service cần.
- Tách bind identity đọc khỏi identity ghi nếu nghiệp vụ và kiến trúc yêu cầu.
- Dùng LDAPS/StartTLS và xác minh certificate/hostname.
- Không ghi password, token hoặc secret attribute vào entity ODM dùng chung.
- Validate DN và naming attribute trước khi create/move.
- Dùng filter builder cho các truy vấn kiểm tra trước khi ghi.
- Không log toàn bộ entity hoặc `Attributes` nếu có dữ liệu nhạy cảm.
- Ghi audit operation ID, stable ID, DN và loại thay đổi theo chính sách bảo vệ dữ liệu.
- Kiểm soát quyền xóa và subtree delete chặt hơn quyền update attribute thông thường.

ODM chỉ giúp mapping. Nó không thay thế authorization ở application service hoặc ACL ở LDAP server.

## 13. Checklist trước khi đưa CRUD ODM lên production

**Mapping**

- [ ] Entity có `@Entry` và `@Id Name`.
- [ ] `objectClasses` phù hợp schema và các attribute được quản lý.
- [ ] Field được ánh xạ rõ bằng `@Attribute`, `@DnAttribute` hoặc `@Transient`.
- [ ] Binary/multivalue attributes có kiểu Java và converter phù hợp.
- [ ] DN được tính hoặc gán rõ ràng.

**Create/update**

- [ ] Parent tồn tại và DN không collision.
- [ ] MUST attributes có giá trị.
- [ ] Create không bị hiểu nhầm thành upsert.
- [ ] Update dùng object đầy đủ, không dùng sparse patch ngoài ý muốn.
- [ ] Null/empty attribute semantics đã được kiểm thử.
- [ ] Nếu DN thay đổi, đã chọn rõ ODM move hay LDAP ModifyDN.
- [ ] References và stable ID được xử lý sau rename/move.

**Delete**

- [ ] Xác minh đúng entry và quyền xóa.
- [ ] Kiểm tra child entries và subtree.
- [ ] Kiểm tra DN references từ group và entry khác.
- [ ] Không dựa vào cascade delete.
- [ ] Có audit và chính sách phục hồi phù hợp.

**Vận hành**

- [ ] Có integration test với directory đúng vendor/schema.
- [ ] Xử lý lỗi giao tiếp sau write bằng read-back/reconciliation.
- [ ] Không giả định transaction bao trùm nhiều entry.
- [ ] Credential lấy từ secret store và không xuất hiện trong log.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng annotation `@Id` của JPA/Spring Data | ODM không nhận đúng DN | Dùng `org.springframework.ldap.odm.annotations.Id` |
| Thiếu `@Entry` hoặc `@Id` | Entity không đủ metadata | Khai báo hai annotation bắt buộc |
| Khai báo thiếu objectClass | ODM không quản lý đúng các field/schema | Khai báo các object class cần thiết |
| Cho rằng mọi field Java đều chỉ tồn tại trong RAM | Field không annotation có thể được map thành attribute | Dùng `@Transient` cho field không persistent |
| Chỉ dùng `@DnAttribute` nhưng quên `@Transient` | Field DN-only có thể được map thành LDAP attribute | Kết hợp annotation đúng mục đích |
| Gọi create như upsert | Entry collision hoặc ghi sai trạng thái | Phân biệt create và update |
| Dùng entity rỗng để update | Có thể xóa hoặc thay đổi attribute ngoài ý muốn | Đọc entity đầy đủ rồi mutate |
| Coi update đổi DN là ModifyDN | References/operational behavior khác dự kiến | Dùng `LdapTemplate.rename` khi cần ModifyDN |
| Xóa parent có child | Directory từ chối xóa | Xử lý descendants trước |
| Nghĩ delete tự xóa group references | Dangling DN references | Reconcile references riêng |
| Retry write ngay sau timeout | Ghi lặp hoặc xử lý sai trạng thái | Đọc lại directory trước khi retry |
| Dùng một bind identity admin cho mọi CRUD | Tăng phạm vi thiệt hại khi credential lộ | Least privilege và tách quyền |

## 15. Câu hỏi tự kiểm tra

1. ODM trong Spring LDAP giải quyết vấn đề gì?
2. Vì sao `@Entry` và `@Id` là bắt buộc?
3. Field `@Id` phải có kiểu dữ liệu nào?
4. `@Attribute` và `@DnAttribute` khác nhau như thế nào?
5. Vì sao field `@DnAttribute` vẫn có thể được map thành LDAP attribute?
6. Khi nào cần dùng `@Transient`?
7. Spring LDAP lấy `objectClass` nào khi tạo entry ODM?
8. Vì sao schema MUST attributes ảnh hưởng trực tiếp tới create?
9. `LdapTemplate.create` có tự update khi DN đã tồn tại không?
10. `LdapTemplate.update` tạo LDAP Modify như thế nào khi DN không đổi?
11. Khi nào ODM update có thể di chuyển entry?
12. Vì sao move theo ODM unbind/bind khác với LDAP ModifyDN?
13. Khi nào nên gọi `LdapTemplate.rename` trực tiếp?
14. Vì sao update nên bắt đầu từ entity đã đọc đầy đủ?
15. `LdapRepository.save` quyết định create/update theo trạng thái nào?
16. Vì sao `save` không phải một upsert nguyên tử?
17. `LdapTemplate.delete` lấy DN từ đâu?
18. Vì sao LDAP không tự cascade delete entry con?
19. Các group references có được tự cập nhật khi xóa entry không?
20. Làm thế nào kiểm thử partial failure khi update nhiều entry?
21. Khi `CommunicationException` xảy ra sau create, cần xác minh điều gì trước khi retry?
22. Vì sao `@Transactional` của database không bao trùm LDAP CRUD?
23. Những quyền LDAP nào cần tách giữa reader và writer?
24. Hãy thiết kế integration test cho vòng đời create-read-update-delete.

## 16. Tổng kết

Spring LDAP ODM ánh xạ entry LDAP thành object Java thông qua `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient`. `LdapTemplate.create`, `update`, `delete` cung cấp các thao tác ghi dựa trên metadata đó; Spring Data LDAP repository bổ sung giao diện CRUD dùng DN (`Name`) làm ID.

Create tạo entry mới theo DN và object class; update đọc trạng thái hiện tại rồi tạo các modification cần thiết; delete xóa entry được xác định bằng DN. Schema, parent DN, quyền và attribute syntax vẫn phải hợp lệ. LDAP không tự cung cấp cascade delete hoặc transaction ACID cho nhiều entry như ORM quan hệ.

Đặc biệt, khi DN tính từ `@DnAttribute` thay đổi, ODM update có thể di chuyển entry bằng unbind/bind. Nếu cần thao tác LDAP ModifyDN do server xử lý và muốn dựa vào referential integrity của directory, hãy dùng `LdapTemplate.rename` rõ ràng rồi xác minh các references. Với CRUD production, luôn đọc lại trạng thái sau ghi, xử lý lỗi giao tiếp theo hướng đối soát, kiểm thử đúng vendor/schema và cấp quyền tối thiểu.

### Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — LdapOperations (`create`, `update`, `delete`)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [Spring LDAP Reference — Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html).
- [Spring Data LDAP API — LdapRepository](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html).
- [Spring Data LDAP Reference — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html).
- [RFC 4511 — LDAPv3 Protocol: Add, Modify, Delete and ModifyDN Operations](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models and Schema](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514).
