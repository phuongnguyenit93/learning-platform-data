# Kiểm chứng trường nào được đọc, được ghi hoặc bị bỏ qua

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, Spring LDAP Object-Directory Mapping (ODM) ánh xạ một LDAP entry sang Java object và chuyển Java object trở lại directory. Việc một field có trong class không có nghĩa nó luôn được đọc, luôn được ghi hoặc luôn bị bỏ qua. Kết quả phụ thuộc vào annotation, tên field, DN, objectClass, schema và quyền của bind identity.

Bài thuộc chương **Ánh xạ thực thể**, tập trung vào việc kiểm chứng chính xác từng field trong một entity:

- Field nào được đọc từ LDAP?
- Field nào được ghi khi tạo hoặc cập nhật entry?
- Field nào chỉ lấy dữ liệu từ DN?
- Field nào được đọc nhưng không được ghi?
- Field nào bị ODM bỏ qua hoàn toàn?
- Field nào tự động map theo tên Java dù không có annotation?

Bạn sẽ dùng **@Entry, @Id, @Attribute, @DnAttribute và @Transient**, sau đó chạy một integration test để so sánh giá trị trong Java object với giá trị thực tế trên LDAP server.

Sau bài học, bạn có thể:

- Phân biệt **readable**, **writable** và **ignored** field.
- Dùng **@Attribute(readonly = true)** để đọc field nhưng không persist field đó.
- Dùng **@Transient** để ODM bỏ qua field khi đọc/ghi.
- Nhận biết field không annotation vẫn được map theo tên field Java.
- Kết hợp **@DnAttribute** với **@Transient** để lấy thành phần RDN mà không tạo LDAP attribute trùng.
- Kiểm tra DN, objectClass, attribute syntax, cardinality và binary mapping.
- Viết test xác nhận field nào thực sự thay đổi sau create/update.
- Phân biệt hành vi ODM với giới hạn do schema, ACL và LDAP server.

## 1. Bài toán: một Java field có thể đi theo nhiều hướng

Giả sử entry của An trong directory:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
description: LDAP profile for An
employeeNumber: E-1042
mail: an@example.org
mail: an.tran@example.net
~~~

Ứng dụng cần đọc hồ sơ này, cập nhật tên hiển thị và description, đồng thời giữ employeeNumber do hệ thống nhân sự quản lý. Ứng dụng cũng cần một field tiện ích displayLabel để hiển thị trong giao diện, nhưng field này không tồn tại trong LDAP.

Nếu tất cả field đều được map giống nhau, có thể xảy ra:

- Ứng dụng ghi đè employeeNumber dù không phải chủ sở hữu dữ liệu.
- displayLabel bị tạo thành LDAP attribute ngoài ý muốn.
- Một field chỉ có trong DN lại bị ghi thành attribute.
- Attribute nhiều giá trị mail bị thu hẹp thành một giá trị.
- Field operational hoặc chỉ đọc khiến update bị server từ chối.

Vì vậy, trước khi viết repository hay service, hãy lập **bảng hợp đồng mapping cho từng field**.

## 2. Ma trận đọc/ghi/bỏ qua trong Spring LDAP ODM

Các quy tắc chính:

| Khai báo field | Đọc từ LDAP | Ghi vào LDAP | Ý nghĩa |
| --- | --- | --- | --- |
| Field không có annotation | Có | Có | Mặc định map theo tên field Java |
| @Attribute(name = "cn") | Có | Có | Map rõ field sang attribute cn |
| @Attribute(name = "employeeNumber", readonly = true) | Có, nếu server trả attribute | Không | Đọc được nhưng ODM không persist field |
| @Transient | Không | Không | ODM bỏ qua field hoàn toàn |
| @DnAttribute(value = "uid") | Có từ RDN của DN | Có thể tham gia tính DN nếu khai báo index phù hợp; field cũng map thành attribute theo tên mặc định nếu không có @Transient | Map một thành phần DN vào String field |
| @DnAttribute(value = "uid") + @Transient | Có từ RDN | Không ghi thành LDAP attribute | Chỉ dùng thành phần DN, không map attribute |
| @Attribute + @DnAttribute trên cùng field | Có từ attribute và DN | Có thể ghi attribute và tham gia tính DN | Khi cả LDAP attribute và RDN cùng biểu diễn một giá trị |
| @Id Name dn | Có DN của entry | Dùng làm định danh entry | Không phải LDAP attribute thông thường |

**Điểm dễ nhầm:** không có annotation không có nghĩa là field bị bỏ qua. ODM mặc định map field theo tên Java sang LDAP attribute cùng tên. Muốn bỏ qua field, dùng đúng **org.springframework.ldap.odm.annotations.Transient**.

### 2.1. @Attribute và readonly

@Attribute ánh xạ field Java sang LDAP attribute. Nếu chỉ định name, tên LDAP được dùng rõ ràng; nếu bỏ name, ODM dùng tên field Java.

Thuộc tính readonly của @Attribute có nghĩa:

- ODM vẫn có thể đọc field khi LDAP server trả attribute đó.
- ODM không ghi/persist field đó khi tạo hoặc cập nhật entry.
- Giá trị trong Java object có thể bị thay đổi, nhưng thay đổi đó không được ODM ghi trở lại LDAP.

Đây là lựa chọn phù hợp với dữ liệu do hệ thống khác quản lý hoặc thuộc tính chỉ đọc/operational. Nó không cấp quyền đọc ở server; ACL và search request vẫn quyết định attribute có được trả về hay không.

### 2.2. @Transient

@Transient yêu cầu ODM bỏ qua field:

- Không đọc field từ LDAP.
- Không ghi field vào LDAP.
- Field có thể dùng cho dữ liệu tính toán, trạng thái tạm hoặc presentation helper trong Java.

Hãy import annotation của **Spring LDAP ODM**:

~~~java
import org.springframework.ldap.odm.annotations.Transient;
~~~

Không nhầm với annotation cùng tên của JPA hoặc Spring Data. Các annotation này thuộc những mapping engine khác nhau.

### 2.3. @DnAttribute

@DnAttribute lấy giá trị từ một thành phần của distinguished name. Ví dụ DN:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Field được đánh dấu @DnAttribute(value = "uid") có thể nhận giá trị **an** từ RDN uid.

Chỉ field kiểu **String** được hỗ trợ cho @DnAttribute. Không dùng annotation này trực tiếp cho Name, UUID hoặc kiểu dữ liệu tùy chỉnh.

@DnAttribute không tự động làm field trở thành DN-only. ODM vẫn map field thành LDAP attribute theo tên field mặc định, trừ khi field được đánh dấu @Transient hoặc được cấu hình mapping phù hợp. Vì vậy:

- Dùng @DnAttribute cùng @Attribute khi field đại diện cho cả LDAP attribute và thành phần RDN.
- Dùng @DnAttribute cùng @Transient khi field chỉ lấy dữ liệu từ DN, không tạo attribute cùng tên.

Nếu khai báo index cho @DnAttribute, ODM có thể tính DN khi tạo hoặc cập nhật entity. Trong trường hợp update, thay đổi các thành phần DN có thể dẫn đến move/rename entry. Chỉ bật hành vi này khi naming policy và quyền rename đã được kiểm soát.

## 3. Mô hình entry để kiểm chứng

Ví dụ sau dùng một entity với đủ loại field:

~~~java
package org.example.directory.persistence;

import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    objectClasses = {
        "inetOrgPerson",
        "organizationalPerson",
        "person",
        "top"
    },
    base = "ou=people"
)
public class DirectoryPerson {

    @Id
    private Name dn;

    // Map LDAP attribute uid.
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Không có annotation: mặc định map sang LDAP attribute description.
    private String description;

    // Đọc được nhưng không persist thay đổi từ ứng dụng này.
    @Attribute(name = "employeeNumber", readonly = true)
    private String employeeNumber;

    // Attribute mail có thể nhiều giá trị.
    @Attribute(name = "mail")
    private List<String> emails;

    // Chỉ lấy uid từ DN, không map thành một LDAP attribute.
    @DnAttribute(value = "uid")
    @Transient
    private String uidFromDn;

    // Field Java dùng cho giao diện; ODM bỏ qua hoàn toàn.
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
    public void setSurname(String surname) { this.surname = surname; }
    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }
    public String getEmployeeNumber() { return employeeNumber; }
    public void setEmployeeNumber(String employeeNumber) {
        this.employeeNumber = employeeNumber;
    }
    public List<String> getEmails() { return emails; }
    public void setEmails(List<String> emails) { this.emails = emails; }
    public String getUidFromDn() { return uidFromDn; }
    public void setUidFromDn(String uidFromDn) {
        this.uidFromDn = uidFromDn;
    }
    public String getDisplayLabel() { return displayLabel; }
    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
~~~

### 3.1. Bảng kiểm chứng của entity

| Field Java | Mapping | Giá trị sau khi đọc fixture | Có được ghi khi update? |
| --- | --- | --- | --- |
| dn | @Id | DN của entry | Dùng làm identity; không phải attribute |
| uid | @Attribute(name = "uid") | an | Có, với LDAP attribute uid |
| commonName | @Attribute(name = "cn") | An Tran | Có |
| surname | @Attribute(name = "sn") | Tran | Có |
| description | Mapping mặc định theo tên field | LDAP profile for An | Có |
| employeeNumber | @Attribute(readonly = true) | E-1042 nếu được trả về | Không |
| emails | @Attribute(name = "mail") | Hai email | Có, theo semantics collection/ODM |
| uidFromDn | @DnAttribute + @Transient | an từ DN | Không ghi thành attribute |
| displayLabel | @Transient | null sau khi ODM đọc | Không |

Giá trị thực tế còn phụ thuộc server có trả attribute hay không, schema có cho phép và bind identity có ACL tương ứng. Bảng mô tả quy tắc mapping của ODM, không thay thế kiểm tra server.

## 4. @Entry và objectClass quyết định phạm vi entity

@Entry không chỉ là nhãn cho class. Nó mô tả objectClass mà entity đại diện và có thể xác định base DN.

Ví dụ entry thực tế có:

~~~ldif
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
~~~

Nếu entity cần quản lý các field được định nghĩa bởi inetOrgPerson, hãy khai báo đầy đủ chuỗi objectClass tương ứng trong @Entry. Nếu chỉ khai báo person và top, entity không nên được dùng để giả định có thể quản lý tất cả attribute của inetOrgPerson.

Để một entry được ODM xem là match với entity, các objectClass hiện diện trên entry phải được khai báo trong @Entry. Ví dụ entry có inetOrgPerson, organizationalPerson, person và top thì chỉ khai báo person/top là không đủ để match entry đó theo quy tắc ODM.

Một số quy tắc cần nhớ:

- @Entry và @Id là annotation bắt buộc đối với managed ODM entity.
- @Id phải là field kiểu javax.naming.Name hoặc lớp dẫn xuất phù hợp.
- Các objectClass được khai báo phải khớp với entry mà entity quản lý.
- Khi tạo entry mới bằng ODM, các objectClass khai báo trong @Entry được sử dụng.
- Schema server vẫn quyết định attribute MUST/MAY, syntax và constraint.

**Không dùng objectClass như một danh sách field được tự động ghi.** Việc một objectClass cho phép attribute không có nghĩa Java entity đã map attribute đó.

## 5. Field không annotation vẫn được map

Đây là nguồn lỗi phổ biến khi một class được mở rộng:

~~~java
@Entry(objectClasses = {"person", "top"})
public class PersonEntry {
    @Id
    private Name dn;

    private String description;

    private String internalNote;
}
~~~

Hai field description và internalNote mặc định được xem là LDAP attribute cùng tên. Nếu schema không cho phép internalNote hoặc server không chấp nhận attribute đó, create/update có thể thất bại.

Nếu internalNote chỉ dùng trong Java:

~~~java
@Transient
private String internalNote;
~~~

Nếu nó phải map sang một attribute khác tên:

~~~java
@Attribute(name = "employeeNumber")
private String staffCode;
~~~

Hãy rà soát entity theo nguyên tắc **mọi field phải có chủ đích**: mapping mặc định, mapping tường minh, read-only, DN-only hoặc transient.

## 6. Đọc entry: kiểm chứng giá trị từ LDAP

Có thể dùng các object mapping methods của LdapTemplate:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

DirectoryPerson person = ldapTemplate.findOne(
        query()
            .where("uid").is("an"),
        DirectoryPerson.class);
~~~

Hoặc tìm nhiều entry:

~~~java
List<DirectoryPerson> people = ldapTemplate.find(
        query()
            .where("objectClass").is("inetOrgPerson"),
        DirectoryPerson.class);
~~~

Trong ví dụ này, @Entry đã khai báo base là ou=people nên không lặp lại base đó trong query ODM. Nếu muốn override search base cho một use case, hãy xác minh quy tắc ghép base và DN của phiên bản Spring LDAP đang dùng.

Sau khi đọc, kiểm tra từng nhóm:

~~~java
assertEquals("an", person.getUid());
assertEquals("an", person.getUidFromDn());
assertEquals("An Tran", person.getCommonName());
assertEquals("Tran", person.getSurname());
assertEquals("LDAP profile for An", person.getDescription());
assertEquals("E-1042", person.getEmployeeNumber());
assertEquals(2, person.getEmails().size());
assertNull(person.getDisplayLabel());
~~~

Các assertion này giả định fixture và server test trả đủ attribute được yêu cầu. Nếu field employeeNumber bị null, cần kiểm tra search request, ACL và việc attribute có tồn tại trước khi kết luận annotation sai.

### 6.1. Read-only không đồng nghĩa operational attribute

@Attribute(readonly = true) là chính sách mapping của ứng dụng: ODM không persist field. Nó có thể dùng cho:

- Attribute do hệ thống nhân sự hoặc provisioning khác quản lý.
- Attribute server sinh ra.
- Operational attribute như createTimestamp hoặc entryUUID nếu server trả về.
- Giá trị chỉ cần đọc để hiển thị hoặc đối chiếu.

Nhưng operational attributes thường có quy tắc trả về riêng. Một số server yêu cầu client yêu cầu rõ attribute operational hoặc dùng ký hiệu phù hợp; ACL cũng có thể ẩn chúng. Với Active Directory, một số định danh như objectGUID là binary và cần mapping phù hợp.

Do đó, kiểm tra riêng hai việc:

1. **Server có trả attribute trong search/lookup không?**
2. **Nếu Java field có giá trị, ODM có ghi ngược field đó không?**

Không dùng @Attribute(readonly = true) để thay thế ACL hoặc để che giấu dữ liệu nhạy cảm khỏi Java object.

## 7. Ghi entry: kiểm chứng field nào được persist

Sau khi đọc entry, thay đổi một số field:

~~~java
person.setCommonName("An Tran Updated");
person.setDescription("Profile reviewed by directory app");

// Cố ý thay đổi hai field không được phép ghi.
person.setEmployeeNumber("SPOOFED-9999");
person.setDisplayLabel("An - Updated");

ldapTemplate.update(person);
~~~

Kết quả mapping mong đợi:

- commonName được ghi vào LDAP attribute cn.
- description được ghi vì field không annotation vẫn map theo tên.
- employeeNumber không được ODM persist vì readonly = true.
- displayLabel bị ODM bỏ qua vì @Transient.
- uidFromDn bị bỏ qua như LDAP attribute do có @Transient.

Sau update, **đọc lại entry từ server** để xác minh:

~~~java
DirectoryPerson reloaded = ldapTemplate.findOne(
        query()
            .where("uid").is("an"),
        DirectoryPerson.class);

assertEquals("An Tran Updated", reloaded.getCommonName());
assertEquals("Profile reviewed by directory app",
        reloaded.getDescription());
assertEquals("E-1042", reloaded.getEmployeeNumber());
assertNull(reloaded.getDisplayLabel());
~~~

Không chỉ assert trên object đang nằm trong memory. Object có thể giữ giá trị SPOOFED-9999 dù ODM không ghi giá trị ấy; chỉ kết quả đọc lại từ LDAP mới xác nhận server đang lưu gì.

### 7.1. Create và update có cùng quy tắc field không?

Với ODM, các field được map và writable tham gia quá trình persist khi tạo/cập nhật. Field readonly không được persist; field transient bị bỏ qua. Tuy nhiên, create và update khác nhau về trạng thái entry:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Create entry mới | DN hợp lệ, objectClass và MUST attributes đầy đủ; readonly/transient không bị ghi |
| Update entry hiện có | Field writable được cập nhật; readonly không bị ghi; transient không bị ghi |
| DN thay đổi | Chỉ xảy ra theo quy tắc @Id/@DnAttribute và cấu hình index; cần kiểm tra rename |
| Attribute bị bỏ khỏi Java object | Xác minh semantics của ODM update/version; không giả định mọi null đều giống nhau |
| Server từ chối update | Phân biệt schema violation, ACL, duplicate value và lỗi kết nối |

Nếu use case yêu cầu **chỉ sửa một attribute hoặc một value cụ thể**, hãy cân nhắc LdapTemplate.modifyAttributes thay vì phụ thuộc vào cách ODM đồng bộ toàn bộ entity. Với multi-valued attribute, test ADD/REMOVE/REPLACE rõ ràng.

## 8. @DnAttribute: field đến từ DN, không nhất thiết đến từ attribute

Giả sử DN là:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Mapping chỉ lấy uid từ DN:

~~~java
@DnAttribute(value = "uid")
@Transient
private String uidFromDn;
~~~

Field này nhận giá trị an từ RDN. @Transient bảo đảm ODM không tạo một LDAP attribute tên uidFromDn hoặc uid cho field này. Nếu entity cũng cần LDAP attribute uid, khai báo field riêng hoặc kết hợp @Attribute và @DnAttribute trên cùng field.

Trong entity minh họa, uid được map từ LDAP attribute bằng @Attribute, còn uidFromDn được map từ RDN bằng @DnAttribute + @Transient. Cách tách này giúp test thấy rõ hai nguồn dữ liệu. Nếu muốn một field Java duy nhất đại diện cho cả LDAP attribute và RDN, có thể kết hợp hai annotation:

~~~java
@Attribute(name = "uid")
@DnAttribute(value = "uid")
private String uid;
~~~

### 8.1. Khi nào @DnAttribute cần index?

Không có index, @DnAttribute có thể lấy thành phần DN theo tên khi đọc. Khi muốn ODM tính DN lúc create/update, cần khai báo index cho tất cả các field @DnAttribute tham gia phép tính DN. Khi index được chỉ định, index xác định vị trí RDN và name không còn được dùng để chọn thành phần.

Ví dụ cấu trúc DN tương đối:

~~~text
uid=an,ou=engineering
~~~

Các thành phần DN được đánh index theo thứ tự RDN mà LdapName sử dụng. Hãy kiểm tra ví dụ chính thức và viết test với DN thật của ứng dụng trước khi cho phép update một field RDN tự động move entry.

### 8.2. Phân biệt ba cách map RDN

| Khai báo | Giá trị Java đến từ | Có ghi LDAP attribute? | Có thể tham gia tính DN? |
| --- | --- | --- | --- |
| @DnAttribute(value = "uid") | RDN uid | Có, theo tên field mặc định nếu không có @Transient | Có khi khai báo index phù hợp |
| @DnAttribute(value = "uid") + @Transient | RDN uid | Không | Có khi khai báo index phù hợp |
| @Attribute(name = "uid") + @DnAttribute(value = "uid") | LDAP attribute uid và RDN uid | Có | Có khi khai báo index phù hợp |

Khi field DN component thay đổi, hệ quả có thể là rename hoặc move entry. Điều này có thể ảnh hưởng:

- Group attribute như member/uniqueMember.
- Attribute manager, seeAlso hoặc các DN reference khác.
- Cache, database, index và các service khác.
- ACL kế thừa theo OU và policy cấp quyền.

Không expose field RDN cho client cập nhật nếu use case không được phép đổi naming structure.

## 9. Thuộc tính nhiều giá trị và kiểu dữ liệu

ODM không chỉ map String. Kiểu Java phải tương thích với LDAP syntax và converter đang được cấu hình.

### 9.1. Multi-valued attribute

Ví dụ mail có hai giá trị:

~~~ldif
mail: an@example.org
mail: an.tran@example.net
~~~

Ánh xạ:

~~~java
@Attribute(name = "mail")
private List<String> emails;
~~~

Hoặc dùng Set khi ứng dụng cần semantics không trùng lặp:

~~~java
import java.util.Set;
import javax.naming.Name;

@Attribute(name = "uniqueMember")
private Set<Name> members;
~~~

Với DN-valued attribute, Spring LDAP ODM hỗ trợ kiểu Name. So sánh DN cần theo ngữ nghĩa Name, không dựa trên so sánh chuỗi thuần túy vì cách viết/escape có thể khác nhau.

Nếu một field cùng lúc có @Attribute và @DnAttribute, giá trị LDAP attribute và RDN cần nhất quán theo naming policy của ứng dụng. Hãy kiểm tra điều kiện này khi tạo/cập nhật; không dựa vào mapping để tự hòa giải hai giá trị mâu thuẫn.

### 9.2. Binary attribute

Ví dụ ảnh:

~~~java
@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY
)
private byte[] photo;
~~~

type BINARY cho biết JNDI provider trả dữ liệu dưới dạng byte[]. Với attribute chuỗi, kiểu mặc định là STRING. Không map binary thành String tùy tiện; dữ liệu có thể bị hỏng do encoding.

### 9.3. Attribute syntax và converter

@Attribute có thể khai báo syntax OID để ODM chọn conversion phù hợp hơn. Nếu Java type không được converter mặc định hỗ trợ, cấu hình Converter/ConversionService tương thích với ObjectDirectoryMapper.

Quy trình:

1. Xác định LDAP syntax của attribute trong schema.
2. Xác định kiểu dữ liệu Java mong muốn.
3. Kiểm tra converter mặc định có hỗ trợ không.
4. Nếu cần, đăng ký converter hai chiều.
5. Kiểm thử đọc và ghi với dữ liệu đại diện, bao gồm null, binary và giá trị biên.

Không chỉ kiểm tra Java compile thành công. Converter có thể compile nhưng parse thất bại khi dữ liệu LDAP thực tế khác format giả định.

## 10. Schema và ACL có thể làm kết quả khác với annotation

Annotation mô tả mapping của ứng dụng. LDAP server vẫn quyết định có cho phép đọc/ghi attribute không.

| Tình huống | Kết quả có thể thấy | Cách phân biệt |
| --- | --- | --- |
| Attribute không tồn tại | Java field null | Kiểm tra entry thực tế |
| Attribute tồn tại nhưng ACL không cho đọc | Field có thể không được trả về | Kiểm tra quyền bằng tài khoản test được cấp phép |
| Search không yêu cầu operational attribute | Field operational không được populate | Yêu cầu attribute đúng cách và xác minh server |
| Field map sai tên | Field null hoặc không được cập nhật | Kiểm tra @Attribute.name và schema |
| Attribute không thuộc objectClass phù hợp | ODM không match hoặc server từ chối create/update | Kiểm tra @Entry.objectClasses |
| Thiếu MUST attribute | Server trả schema violation | Bổ sung dữ liệu hợp lệ |
| Sai syntax/type | Conversion error hoặc constraint violation | Kiểm tra syntax OID và converter |
| Readonly attribute | ODM không ghi field | Kiểm tra giá trị server trước/sau update |
| Transient field | ODM không đọc/ghi field | Xác minh không có LDAP attribute tương ứng |
| Service account thiếu quyền ghi | Insufficient access rights | Kiểm tra ACL, không đổi annotation để lách quyền |

**Không kết luận field bị bỏ qua chỉ từ giá trị null.** Null có thể do attribute không tồn tại, ACL, projection, server behavior hoặc mapping sai. Dùng fixture và kiểm tra trực tiếp directory để phân loại.

## 11. Tách test mapping khỏi test nghiệp vụ

Nên có ít nhất ba loại test:

1. **Unit test mapping policy:** xác nhận mapper/service dùng field nào và không vô tình truyền field ignored vào response.
2. **ODM integration test:** đọc/ghi entity với LDAP server test để xác minh annotation thực thi như mong đợi.
3. **Schema/ACL integration test:** chạy với bind identity và schema gần production để xác minh server chấp nhận/từ chối đúng.

### 11.1. Fixture test

Nạp entry vào directory test:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
description: LDAP profile for An
employeeNumber: E-1042
mail: an@example.org
mail: an.tran@example.net
~~~

Fixture phải được reset trước mỗi test. Dùng directory test riêng, không chạy test ghi trên production.

### 11.2. Test đọc và ghi bằng LdapTemplate ODM

Ví dụ test tích hợp:

~~~java
package org.example.directory;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.example.directory.persistence.DirectoryPerson;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;

@SpringBootTest
class DirectoryPersonMappingIntegrationTest {
    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void readsWritableReadonlyAndTransientFieldsCorrectly() {
        DirectoryPerson person = ldapTemplate.findOne(
                query()
                    .where("uid").is("an"),
                DirectoryPerson.class);

        assertNotNull(person);
        assertEquals("an", person.getUid());
        assertEquals("an", person.getUidFromDn());
        assertEquals("An Tran", person.getCommonName());
        assertEquals("E-1042", person.getEmployeeNumber());
        assertEquals(2, person.getEmails().size());
        assertNull(person.getDisplayLabel());

        person.setCommonName("An Tran Updated");
        person.setDescription("Reviewed by directory app");
        person.setEmployeeNumber("SPOOFED-9999");
        person.setDisplayLabel("Temporary UI label");

        ldapTemplate.update(person);

        DirectoryPerson reloaded = ldapTemplate.findOne(
                query()
                    .where("uid").is("an"),
                DirectoryPerson.class);

        assertEquals("An Tran Updated", reloaded.getCommonName());
        assertEquals("Reviewed by directory app",
                reloaded.getDescription());
        assertEquals("E-1042", reloaded.getEmployeeNumber());
        assertNull(reloaded.getDisplayLabel());
    }
}
~~~

Test chứng minh bốn điểm:

- @Attribute thông thường được đọc và ghi.
- Field không annotation vẫn được map theo tên và được ghi.
- @Attribute(readonly = true) được đọc nhưng giá trị thay đổi trong Java không được ghi lại.
- @Transient không được ODM populate hoặc persist.

Nếu test employeeNumber trả null, xác minh fixture và ACL trước. Nếu server không trả attribute đó, dùng một attribute user-defined được phép đọc để kiểm chứng readonly; không suy ra readonly annotation không hoạt động.

### 11.3. Kiểm tra trực tiếp giá trị LDAP sau update

Để xác minh chính xác server đang lưu gì, đọc raw attribute bằng LdapTemplate:

~~~java
import org.springframework.ldap.core.AttributesMapper;

String employeeNumber = ldapTemplate.lookup(
        person.getDn(),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("employeeNumber").get());

assertEquals("E-1042", employeeNumber);
~~~

Đồng thời kiểm tra attribute không được tạo:

~~~java
Boolean ignoredAttributesExist = ldapTemplate.lookup(
        person.getDn(),
        (AttributesMapper<Boolean>) attrs ->
                attrs.get("displayLabel") != null
                || attrs.get("uidFromDn") != null);

assertFalse(ignoredAttributesExist);
~~~

Raw lookup xác minh trạng thái directory độc lập với Java object còn giữ trong memory.

### 11.4. Test field DN-only

Với field có @DnAttribute và @Transient:

~~~java
assertEquals("an", person.getUidFromDn());
~~~

Sau update, đọc LDAP attribute uid và DN để bảo đảm:

- LDAP attribute uid vẫn là an nếu field uid được map bằng @Attribute.
- DN vẫn đúng với naming policy.
- Không có attribute uidFromDn được tạo.

Nếu muốn thay đổi RDN, phải kiểm thử riêng cấu hình index, kết quả rename, old DN/new DN và references liên quan. Không dùng test trên để kết luận mọi @DnAttribute đều tự move entry.

## 12. Ma trận test cần hoàn thành

| Ca kiểm thử | Thao tác | Kết quả cần đạt |
| --- | --- | --- |
| Field có @Attribute | Đọc và update | Java field nhận giá trị; LDAP attribute đổi |
| Field không annotation | Đọc và update | ODM map theo tên field; attribute đổi |
| Field readonly | Đọc, sửa trong Java, update | Đọc được; LDAP giữ giá trị ban đầu |
| Field @Transient | Đọc và update | Không được populate; không tạo/cập nhật LDAP attribute |
| Field @DnAttribute | Đọc entry | Lấy đúng RDN component |
| @DnAttribute + @Transient | Đọc/update | Đọc từ DN; không ghi attribute tương ứng |
| @Attribute + @DnAttribute | Đọc/update | Field đại diện cả attribute và RDN theo cấu hình |
| @Id Name | Đọc entry | Có DN hợp lệ, không bị map như attribute |
| Multi-valued attribute | Đọc và ghi list | Không mất giá trị ngoài ý muốn |
| Binary attribute | Đọc/ghi byte[] | Không hỏng dữ liệu |
| Attribute không tồn tại | Đọc | Xử lý null theo policy |
| Attribute bị ACL ẩn | Đọc | Phân biệt với mapping sai nếu có thể |
| Operational attribute | Đọc | Chỉ có giá trị khi server trả và ACL cho phép |
| Thiếu MUST attribute | Create | Server từ chối theo schema |
| Sai objectClass | Find/create/update | ODM/server báo lỗi phù hợp |
| Sai DN index | Create/update | Test phát hiện DN tính sai trước khi release |

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field không annotation vẫn xuất hiện trong LDAP | ODM mặc định map theo tên field | Thêm @Transient nếu field chỉ dùng trong Java |
| Field readonly vẫn đổi trong object sau update | Readonly chỉ ngăn ODM persist; không reset Java field | Đọc lại entity để xác minh trạng thái server |
| @Transient field luôn null sau find | Đây là hành vi mong đợi | Tính field sau mapping trong service |
| DN component bị ghi thành attribute | @DnAttribute vẫn map attribute mặc định | Kết hợp @Transient nếu chỉ cần DN |
| Không đọc được operational attribute | Server không trả attribute hoặc ACL ẩn | Yêu cầu attribute đúng cách và kiểm tra server |
| ODM không match entry | @Entry thiếu objectClass cần thiết | Khai báo objectClass phù hợp với entry |
| Update làm mất giá trị multi-value | Collection/ODM update semantics không được kiểm tra | Test list và dùng modifyAttributes nếu cần thao tác value-level |
| Update bị schema violation | Thiếu MUST hoặc sai syntax | Đối chiếu schema và fixture |
| Binary field lỗi conversion | Sai Attribute.Type hoặc converter | Chọn BINARY và test byte[] |
| DN thay đổi ngoài ý muốn | @DnAttribute index và naming policy sai | Kiểm thử DN tính toán trước khi cho phép update |

## 14. Bài tập thực hành

1. Tạo DirectoryPerson với @Id, @Attribute, field mặc định, readonly và transient.
2. Seed một entry có uid, cn, sn, description, employeeNumber và hai mail values.
3. Viết test chứng minh field không annotation vẫn được map theo tên.
4. Đổi employeeNumber thành readonly, sửa giá trị trong Java rồi update; xác minh LDAP giữ giá trị gốc.
5. Đánh dấu displayLabel là @Transient; chứng minh nó không được đọc/ghi.
6. Tạo field uidFromDn dùng @DnAttribute + @Transient và kiểm tra giá trị từ RDN.
7. Thử khai báo @Attribute + @DnAttribute trên cùng field uid; giải thích hai nguồn mapping.
8. Thêm jpegPhoto dạng byte[] và kiểm thử Attribute.Type.BINARY.
9. Thử đọc operational attribute trên LDAP server test và ghi rõ điều kiện để server trả về.
10. Tạo test schema violation khi thiếu một MUST attribute; phân biệt lỗi mapping với lỗi server.
11. Thay đổi một thành phần RDN với cấu hình @DnAttribute index trong môi trường test; xác minh DN cũ/mới và reference.
12. Viết một bảng mapping cho entity của ứng dụng thật: field, nguồn đọc, đích ghi, annotation, ACL và test tương ứng.

## 15. Tổng kết

Muốn biết một field được đọc, ghi hay bỏ qua, hãy kiểm tra **annotation và hành vi thực tế của ODM**:

- **@Attribute** map field với LDAP attribute; mặc định field có thể được đọc và ghi.
- **@Attribute(readonly = true)** cho phép đọc nhưng không persist field.
- **@Transient** khiến ODM bỏ qua field khi đọc/ghi.
- Field không annotation vẫn được map theo tên Java.
- **@DnAttribute** lấy thành phần DN và mặc định cũng tham gia mapping attribute, trừ khi kết hợp @Transient.
- **@Id Name** giữ DN của entry.

Annotation chỉ định cách ứng dụng ánh xạ. Kết quả cuối còn phụ thuộc objectClass, schema, LDAP syntax, ACL, search request và server implementation. Vì vậy, hãy kiểm chứng bằng cách đọc entry, thay đổi từng field, gọi create/update và đọc lại trực tiếp từ LDAP server. Đây là cách phân biệt một field bị ODM bỏ qua với một field không được server trả về hoặc không được phép ghi.

### Tài liệu tham khảo

- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html) — @Entry, @Id, @Attribute, @DnAttribute, @Transient và object mapping methods.
- [Spring LDAP — Attribute annotation API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.html) — readonly, syntax, type và name.
- [Spring LDAP — Transient annotation API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Transient.html) — field không được persist.
- [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html) — entity ODM và repository usage.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — entry, objectClass, attribute type và schema.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Search, Add và Modify operations.
