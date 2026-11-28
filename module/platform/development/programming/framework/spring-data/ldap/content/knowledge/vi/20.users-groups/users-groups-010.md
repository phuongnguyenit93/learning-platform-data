# Tránh giả định mọi máy chủ đều có cùng schema nhóm

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng thường phải đọc và thay đổi quan hệ giữa người dùng với nhóm để phân quyền, cấp quyền truy cập hoặc đồng bộ danh bạ. Tuy nhiên, LDAP không có một schema nhóm duy nhất được mọi máy chủ sử dụng. Một directory có thể biểu diễn nhóm bằng **groupOfNames**, **groupOfUniqueNames**, **posixGroup**, trong khi Active Directory dùng objectClass **group** và các thuộc tính riêng.

Các mô hình này khác nhau về:

- Attribute dùng để lưu thành viên: **member**, **uniqueMember** hay **memberUid**.
- Giá trị thành viên là DN hay username.
- Attribute bắt buộc khi tạo group và khả năng group rỗng.
- Cách server biểu diễn membership ngược như **memberOf**.
- Cách xử lý nested group, primary group và membership hiệu lực.
- Quy tắc ACL, matching rule và operation khi thêm/xóa thành viên.

Bài thuộc chương **Người dùng và nhóm**, tập trung vào cách nhận diện schema nhóm của server đang kết nối và thiết kế ứng dụng không phụ thuộc vào một mô hình duy nhất. Bạn sẽ xem các schema phổ biến, cách ánh xạ bằng Spring LDAP ODM, cách thao tác bằng **LdapTemplate** và cách đặt một adapter riêng cho từng loại directory.

Sau bài học, bạn có thể:

- Phân biệt **groupOfNames**, **groupOfUniqueNames**, **posixGroup** và Active Directory **group**.
- Nhận biết thành viên được lưu bằng DN hay username.
- Kiểm tra MUST/MAY attributes, syntax, objectClass và ACL trước khi viết CRUD.
- Phân biệt direct membership, nested membership và effective membership.
- Hiểu giới hạn của **memberOf**, primary group và server-specific matching rules.
- Tạo ODM entity/repository riêng cho từng schema.
- Dùng **LdapTemplate.modifyAttributes** để thêm/xóa thành viên đúng attribute.
- Thiết kế domain service và adapter để business logic không bị gắn chặt với vendor.
- Viết integration test trên từng loại LDAP server được hỗ trợ.

## 1. Vì sao không thể giả định mọi LDAP group giống nhau?

Một ứng dụng có thể bắt đầu với entry:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Ở mô hình này, thành viên được lưu trong attribute **member** dưới dạng DN. Nhưng một directory Unix/POSIX có thể lưu:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: posixGroup
cn: developers
gidNumber: 2201
memberUid: an
memberUid: binh
~~~

Hai entry có cùng ý nghĩa nghiệp vụ “nhóm developers gồm An và Binh”, nhưng cấu trúc dữ liệu khác nhau. Nếu ứng dụng luôn tìm **member**, nó sẽ không tìm thấy thành viên của **posixGroup**. Nếu ứng dụng ghi DN vào **memberUid**, server có thể từ chối hoặc lưu dữ liệu sai semantics.

Active Directory còn có mô hình riêng: group sử dụng attribute **member** để tham chiếu DN của thành viên, **memberOf** là backlink do directory quản lý, và primary group được biểu diễn bằng **primaryGroupID** trên user. Một số truy vấn membership đệ quy dùng matching rule riêng của Microsoft.

**Không có một entity Group duy nhất có thể tự động đại diện đúng mọi schema nếu không có adapter và policy rõ ràng.**

## 2. Bốn mô hình nhóm thường gặp

| Mô hình | Attribute thành viên | Giá trị thành viên | Ghi chú |
| --- | --- | --- | --- |
| **groupOfNames** | member | DN | Schema chuẩn phổ biến; cn và ít nhất một member là MUST |
| **groupOfUniqueNames** | uniqueMember | DN hoặc NameAndOptionalUID | cn và uniqueMember là MUST |
| **posixGroup** | memberUid | Username/uid dạng chuỗi | cn và gidNumber là MUST |
| **Active Directory group** | member | DN | Có groupType, memberOf, primaryGroupID và semantics riêng của AD |

Các attribute tùy chọn và schema mở rộng có thể khác theo server. Hãy xem bảng này như bản đồ nhận diện ban đầu, không phải thay thế schema thực tế của directory.

### 2.1. groupOfNames

groupOfNames được định nghĩa trong LDAP schema chuẩn. Ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
description: Backend development team
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Đặc điểm:

- **cn** là tên nhóm.
- **member** chứa DN của các entry thành viên.
- **member** là attribute nhiều giá trị.
- Theo schema chuẩn, **cn** và **member** là MUST.
- Vì **member** bắt buộc, group không có thành viên không thể được biểu diễn bằng entry groupOfNames hợp lệ theo schema chuẩn.

Khi thêm thành viên, ứng dụng phải resolve username thành DN trước khi ghi. Khi user được move/rename, các DN tham chiếu có thể cần được cập nhật; không giả định mọi server tự rewrite mọi custom reference.

### 2.2. groupOfUniqueNames

Ví dụ:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=an,ou=people,dc=example,dc=org
uniqueMember: uid=binh,ou=people,dc=example,dc=org
~~~

Đặc điểm:

- Thành viên được lưu trong **uniqueMember**.
- Giá trị theo schema là **NameAndOptionalUID**; thường gặp là DN, nhưng cú pháp còn cho phép thành phần UID tùy chọn.
- **cn** và **uniqueMember** là MUST.
- Nếu ứng dụng chỉ hỗ trợ giá trị DN thuần, cần xác nhận dữ liệu directory không dùng phần UID tùy chọn.

Không thay uniqueMember bằng member chỉ vì cả hai đều tham chiếu DN. Attribute name và syntax được schema định nghĩa; server sẽ áp dụng đúng loại attribute.

### 2.3. posixGroup

Ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: posixGroup
cn: developers
gidNumber: 2201
memberUid: an
memberUid: binh
~~~

Đặc điểm:

- **gidNumber** là định danh nhóm POSIX.
- **memberUid** chứa username/uid dạng chuỗi, không phải DN.
- **cn** và **gidNumber** là MUST theo schema POSIX group phổ biến; **memberUid** là MAY.
- Group có thể không có memberUid mà vẫn hợp lệ nếu schema/server cho phép, khác với MUST member của groupOfNames.

Do memberUid chỉ lưu username, việc đổi username có thể làm tham chiếu cũ bị stale. Ứng dụng cần policy đồng bộ group membership khi account rename.

### 2.4. Active Directory group

Active Directory sử dụng objectClass **group**. Một entry thường có cấu trúc tương tự:

~~~ldif
dn: CN=Developers,OU=Groups,DC=corp,DC=example
objectClass: top
objectClass: group
cn: Developers
sAMAccountName: Developers
groupType: -2147483646
member: CN=An Tran,OU=People,DC=corp,DC=example
member: CN=Binh Le,OU=People,DC=corp,DC=example
~~~

Các điểm cần chú ý:

- **member** là linked attribute chứa DN của thành viên.
- **memberOf** là backlink được directory quản lý; ứng dụng không nên ghi trực tiếp.
- **groupType** mã hóa loại group và scope/security semantics của AD.
- **sAMAccountName**, **objectSid**, **objectGUID** và một số thuộc tính khác có thể cần cho tích hợp Windows.
- **primaryGroupID** nằm trên user và biểu diễn primary group theo RID; primary group không được xử lý như một member value thông thường trong member.
- Nested group và transitive membership có quy tắc riêng; không thể suy ra effective membership chỉ từ một lần đọc memberOf.

Giá trị groupType trong LDIF chỉ là ví dụ cho một loại group cụ thể. Không hardcode số này cho mọi group; hãy đọc và diễn giải các bit scope/security theo policy của AD.

Đây là mô hình vendor-specific. Không đưa groupType, primaryGroupID hoặc matching rule của AD vào adapter OpenLDAP/POSIX.

## 3. Sơ đồ khác nhau ở đâu?

~~~mermaid
flowchart TD
    G["Group entry"]
    G --> N["groupOfNames"]
    G --> U["groupOfUniqueNames"]
    G --> P["posixGroup"]
    G --> A["Active Directory group"]
    N --> M["member: DN"]
    U --> UM["uniqueMember: NameAndOptionalUID"]
    P --> MU["memberUid: username"]
    A --> AM["member: DN"]
    A --> MO["memberOf: backlink"]
    A --> PG["primaryGroupID: trên user"]
~~~

Hãy xác định rõ **cái gì được lưu trong group entry**, **cái gì được server tính hoặc duy trì**, và **cái gì thuộc mô hình account**. Những khái niệm này thường bị gộp thành một field members trong ứng dụng, gây sai khi đổi server.

## 4. Kiểm tra schema của directory trước khi mapping

Không nên suy luận schema từ tên sản phẩm hoặc một entry mẫu duy nhất. Hãy kiểm tra server đang chạy, naming context, schema và quyền của bind identity.

### 4.1. Khám phá Root DSE

Root DSE cung cấp thông tin về directory server và các naming context được hỗ trợ. Ví dụ dùng ldapsearch:

~~~bash
ldapsearch -H ldaps://ldap.example.org:636 -x -b "" -s base "(objectClass=*)" namingContexts subschemaSubentry supportedLDAPVersion
~~~

Lệnh trên minh họa truy vấn Root DSE; cách xác thực và các thuộc tính được trả về phụ thuộc server. Không truyền password thật trên command line vì process list, shell history hoặc log có thể ghi lại.

### 4.2. Đọc subschema

Nếu server trả subschemaSubentry, dùng DN đó để đọc objectClasses và attributeTypes:

~~~bash
ldapsearch -H ldaps://ldap.example.org:636 -x -b "cn=subschema" -s base "(objectClass=subschema)" objectClasses attributeTypes
~~~

cn=subschema chỉ là ví dụ DN phổ biến; hãy dùng đúng giá trị subschemaSubentry do server trả về. Một số directory có schema discovery và quyền đọc schema khác nhau.

Khi đọc schema, kiểm tra:

- **NAME/OID:** tên và định danh objectClass/attribute.
- **SUP:** objectClass kế thừa từ class nào.
- **STRUCTURAL/AUXILIARY/ABSTRACT:** loại objectClass.
- **MUST/MAY:** attribute bắt buộc và tùy chọn.
- **SYNTAX:** kiểu dữ liệu LDAP.
- **SINGLE-VALUE:** attribute chỉ được có một value hay nhiều value.
- **NO-USER-MODIFICATION/USAGE:** attribute do server quản lý hay user được sửa.
- **Matching rule:** cách so sánh và filter giá trị.

### 4.3. Schema trên Active Directory

Active Directory có schema partition riêng. Root DSE thường cung cấp schemaNamingContext; schema object chứa class/attribute definitions. Ngoài schema, cần đọc tài liệu Microsoft về group, groupType, member, memberOf, primaryGroupID và matching rules. Không dùng kết quả schema OpenLDAP để kết luận AD có cùng semantics.

### 4.4. Tạo bảng tương thích trước khi code

| Kiểm tra | Câu hỏi phải trả lời |
| --- | --- |
| Group objectClass | Server dùng groupOfNames, groupOfUniqueNames, posixGroup hay group? |
| Member attribute | member, uniqueMember hay memberUid? |
| Member value syntax | DN, NameAndOptionalUID hay username? |
| Empty group | Schema có cho phép group không có member không? |
| Reverse membership | Có memberOf không? Do server/overlay nào duy trì? |
| Nested groups | Có hỗ trợ? Search nào trả direct/transitive? |
| Primary group | Có khái niệm riêng như AD primaryGroupID không? |
| Rename | Server có tự cập nhật DN references nào? |
| ACL | Bind identity được đọc/thêm/xóa thành viên ở đâu? |
| Vendor extensions | Có matching rule/control riêng nào cần adapter? |

Không bắt đầu mapping cho đến khi các câu hỏi ảnh hưởng use case đã có câu trả lời.

## 5. Ánh xạ riêng từng schema bằng Spring LDAP ODM

Không nên tạo một entity rồi đổi tên attribute bằng cấu hình tùy ý trong runtime nếu các schema có semantics khác nhau. Hãy tạo mapping class rõ ràng cho từng loại entry, sau đó chọn repository/adapter theo cấu hình directory.

Khi dùng ODM, mọi objectClass hiện diện trên entry phải được khai báo trong @Entry để entry được xem là match với entity. Nếu server hoặc provisioning system thêm objectClass phụ, hãy cập nhật mapping sau khi xác minh schema; đừng bỏ qua class chỉ vì ứng dụng không map field của class đó.

### 5.1. Entity cho groupOfNames

~~~java
package org.example.directory.ldap.openldap;

import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class GroupOfNamesEntry {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    // member chứa DN của từng thành viên.
    @Attribute(name = "member")
    private Set<Name> members;

    @Attribute(name = "description")
    private String description;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }
    public Set<Name> getMembers() { return members; }
    public void setMembers(Set<Name> members) {
        this.members = members;
    }
    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

Ở đây **Set<Name>** phù hợp khi member luôn chứa DN thuần. Nếu server có dữ liệu đặc biệt hoặc cách biểu diễn DN khác, xác minh converter và schema trước khi dùng.

### 5.2. Repository cho groupOfNames

~~~java
package org.example.directory.ldap.openldap;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface GroupOfNamesRepository
        extends LdapRepository<GroupOfNamesEntry> {

    List<GroupOfNamesEntry> findByCn(String cn);
}
~~~

Repository này chỉ dành cho entry được ánh xạ theo groupOfNames. Không dùng nó để đọc posixGroup hoặc AD group rồi kỳ vọng field members tự map sang attribute khác.

### 5.3. Entity cho posixGroup

~~~java
package org.example.directory.ldap.posix;

import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "posixGroup"}
)
public class PosixGroupEntry {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "gidNumber")
    private String gidNumber;

    // memberUid là username, không phải DN.
    @Attribute(name = "memberUid")
    private Set<String> memberUids;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }
    public String getGidNumber() { return gidNumber; }
    public void setGidNumber(String gidNumber) {
        this.gidNumber = gidNumber;
    }
    public Set<String> getMemberUids() { return memberUids; }
    public void setMemberUids(Set<String> memberUids) {
        this.memberUids = memberUids;
    }
}
~~~

Để ý sự khác biệt: **memberUids** là Set<String>. Nếu thay bằng Set<Name>, mapping sẽ không còn đúng với kiểu dữ liệu mà posixGroup lưu.

### 5.4. Entity cho groupOfUniqueNames

uniqueMember có syntax NameAndOptionalUID. Nếu ứng dụng bảo đảm directory chỉ dùng DN thuần, có thể map thành Name. Nếu cần giữ cả dạng optional UID, dùng String hoặc converter chuyên biệt để không làm mất phần dữ liệu bổ sung:

~~~java
@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfUniqueNames"}
)
public class GroupOfUniqueNamesEntry {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    // String bảo toàn cả DN và phần optional UID nếu có.
    @Attribute(name = "uniqueMember")
    private Set<String> uniqueMembers;
}
~~~

Ví dụ rút gọn này chỉ minh họa phần mapping attribute; class sử dụng thật cần constructor/getter/setter theo yêu cầu ODM và application.

### 5.5. Active Directory cần mapping riêng

Một mapping AD có thể cần các field như cn, sAMAccountName, groupType, member và các identifier đặc thù. Ví dụ khung:

~~~java
@Entry(
    base = "OU=Groups",
    objectClasses = {"top", "group"}
)
public class ActiveDirectoryGroupEntry {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sAMAccountName")
    private String samAccountName;

    @Attribute(name = "groupType")
    private String groupType;

    @Attribute(name = "member")
    private Set<Name> members;
}
~~~

Đây là mapping khởi đầu, không phải schema AD đầy đủ. Hãy xác minh objectClass thực tế, thuộc tính bắt buộc, binary identifiers, quyền ghi và semantics của groupType trên domain đang tích hợp. Không đưa memberOf vào luồng ghi; đây là backlink do directory duy trì.

### 5.6. Vì sao cần entity riêng?

| Entity | Thành viên Java | Attribute LDAP | Ý nghĩa |
| --- | --- | --- | --- |
| GroupOfNamesEntry | Set<Name> | member | DN của member |
| GroupOfUniqueNamesEntry | Set<String> hoặc kiểu chuyên biệt | uniqueMember | NameAndOptionalUID |
| PosixGroupEntry | Set<String> | memberUid | Username |
| ActiveDirectoryGroupEntry | Set<Name> | member | DN với semantics AD |

Các class có thể cùng có field cn và members, nhưng field members không có cùng type/semantics. Tách class giúp compiler, mapper và reviewer nhìn thấy khác biệt ngay từ code.

## 6. Tìm group theo đúng objectClass và base

Với repository, finder dựa trên property của entity:

~~~java
List<GroupOfNamesEntry> groups =
        groupOfNamesRepository.findByCn("developers");
~~~

Với LdapTemplate, chỉ định rõ base, scope và objectClass:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;
import org.springframework.ldap.query.SearchScope;

List<GroupOfNamesEntry> groups = ldapTemplate.find(
        query()
            .searchScope(SearchScope.ONELEVEL)
            .where("objectClass").is("groupOfNames")
            .and("cn").is("developers"),
        GroupOfNamesEntry.class);
~~~

Ví dụ trên dùng base đã khai báo trong @Entry của GroupOfNamesEntry; query chỉ bổ sung scope và filter. Khi tìm POSIX group, filter phải dùng objectClass posixGroup. Không dùng filter chung chỉ dựa trên cn vì cùng tên nhóm có thể tồn tại ở các schema hoặc OU khác nhau.

### 6.1. Không dùng objectClass như tên hiển thị

Tên objectClass xác định cấu trúc và schema. Tên hiển thị của nhóm thường đến từ cn hoặc thuộc tính ứng dụng quy định. Không suy ra loại group chỉ từ chuỗi tên nhóm như developers, admins hoặc operators.

### 6.2. Xử lý kết quả trùng

Tên cn không nhất thiết duy nhất toàn directory. Nếu search trả nhiều group cùng cn:

- Giới hạn base theo OU/naming context.
- Dùng một identifier nghiệp vụ đã được kiểm soát.
- Phân biệt group type/schema.
- Trả lỗi ambiguous thay vì chọn phần tử đầu.

Không coi DN do client gửi là đã hợp lệ hoặc được phép thao tác. Resolve group theo phạm vi mà application service cho phép.

## 7. Thêm và xóa thành viên bằng LdapTemplate

Khi cần cập nhật một thành viên, thao tác trực tiếp lên đúng attribute thường rõ ràng hơn việc load toàn bộ group, sửa collection rồi save entity.

### 7.1. Thêm thành viên vào groupOfNames

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void addMemberToGroupOfNames(
        LdapTemplate ldapTemplate) {
    Name groupDn = LdapNameBuilder
            .newInstance("ou=groups")
            .add("cn", "developers")
            .build();

    Name userDn = LdapNameBuilder
            .newInstance("ou=people")
            .add("uid", "an")
            .build();

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", userDn.toString()))
    };

    ldapTemplate.modifyAttributes(groupDn, changes);
}
~~~

Giá trị được thêm là DN của user. Trước khi gọi modify, application service cần xác minh user tồn tại, group thuộc phạm vi được phép và caller có quyền quản lý membership.

### 7.2. Xóa thành viên khỏi groupOfNames

~~~java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", userDn.toString()))
};

ldapTemplate.modifyAttributes(groupDn, changes);
~~~

Nếu đây là member cuối cùng, server có thể từ chối vì groupOfNames yêu cầu member theo schema. Không tự xóa attribute member rồi coi group vẫn hợp lệ. Policy có thể là giữ một member kỹ thuật được kiểm soát, xóa group, hoặc chuyển sang schema cho phép empty group nếu directory hỗ trợ.

### 7.3. Thêm thành viên vào posixGroup

Ở POSIX, giá trị là username:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("memberUid", "an"))
};

ldapTemplate.modifyAttributes(posixGroupDn, changes);
~~~

Không đưa user DN vào memberUid. Nếu username thay đổi, cần cập nhật các group đang chứa username cũ theo một workflow có kiểm soát.

### 7.4. Thêm thành viên vào groupOfUniqueNames

Thao tác dùng attribute uniqueMember:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("uniqueMember", userDn.toString()))
};

ldapTemplate.modifyAttributes(groupDn, changes);
~~~

Ví dụ trên chỉ dùng DN thuần. Nếu directory dùng NameAndOptionalUID, phải giữ và xử lý phần optional UID đúng syntax thay vì ép về Name hoặc bỏ phần suffix.

### 7.5. Thêm thành viên vào Active Directory group

AD cũng dùng attribute member chứa DN, nhưng có các quy tắc riêng về group scope, security/distribution group, linked attribute và quyền ghi. Thao tác add/remove member phải được kiểm thử trên domain test. Không ghi trực tiếp memberOf; server tự duy trì backlink.

### 7.6. ADD, REMOVE và REPLACE không giống nhau

| LDAP modification | Ý nghĩa | Rủi ro cần tránh |
| --- | --- | --- |
| ADD_ATTRIBUTE | Thêm attribute hoặc value | Duplicate value có thể bị server từ chối |
| REMOVE_ATTRIBUTE | Xóa attribute hoặc một value | Có thể vi phạm MUST nếu xóa value cuối |
| REPLACE_ATTRIBUTE | Thay toàn bộ tập value | Có thể vô tình xóa những thành viên khác |

Để thêm/xóa một thành viên, dùng ADD/REMOVE với đúng value. Tránh REPLACE toàn bộ member list khi request chỉ muốn thay đổi một người; hai request đồng thời có thể ghi đè thay đổi của nhau nếu ứng dụng đọc-sửa-ghi toàn collection.

## 8. Direct membership, nested membership và effective membership

Một group entry thường thể hiện **direct membership**: các member được liệt kê trực tiếp trong attribute. Nhưng nghiệp vụ phân quyền thường hỏi một câu rộng hơn: user có thuộc nhóm này hay không, kể cả thông qua nhóm con?

Ví dụ:

~~~text
developers
├── uid=an
├── uid=binh
└── group: backend
    ├── uid=chi
    └── uid=dung
~~~

- An và Binh là direct member của developers.
- Chi và Dung là direct member của backend.
- Nếu backend được liệt kê làm member của developers, Chi và Dung có thể là nested/effective member của developers theo policy.

LDAP schema cơ bản không làm mọi ứng dụng tự động tính membership đệ quy. Ứng dụng phải biết server có hỗ trợ truy vấn transitive hay phải tự duyệt graph.

### 8.1. Direct membership

Direct membership là value hiện diện trực tiếp trong member/uniqueMember/memberUid. Đây là mức portable nhất vì nó phản ánh dữ liệu được lưu trên entry.

### 8.2. Nested membership

Nested membership xuất hiện khi một group có thể là member của group khác. Việc có thể lưu DN của group trong member không có nghĩa mọi server đều tự mở rộng group lồng nhau khi đọc hoặc authorize.

Nếu tự duyệt graph:

- Dùng visited set để tránh vòng lặp A → B → A.
- Giới hạn độ sâu và số entry được duyệt.
- Xử lý group bị xóa hoặc DN stale.
- Áp dụng cùng một quy tắc phân biệt user và group.
- Có cache TTL và cơ chế invalidate khi membership thay đổi.

### 8.3. Effective membership trên Active Directory

AD có matching rule in-chain với OID **1.2.840.113556.1.4.1941** để truy vấn quan hệ DN theo chuỗi liên kết. Đây là extension riêng của Microsoft, không phải filter portable cho mọi LDAP server.

Ví dụ hình dạng filter:

~~~text
(member:1.2.840.113556.1.4.1941:=CN=An Tran,OU=People,DC=corp,DC=example)
~~~

Nếu xây filter từ DN động, phải escape giá trị theo LDAP filter syntax. Không nối DN do client cung cấp trực tiếp vào raw filter.

Ví dụ dùng Spring LDAP:

~~~java
import javax.naming.directory.SearchControls;
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapEncoder;

String encodedDn = LdapEncoder.filterEncode(userDn.toString());
String filter =
        "(member:1.2.840.113556.1.4.1941:=" + encodedDn + ")";

List<String> groups = ldapTemplate.search(
        "OU=Groups",
        filter,
        SearchControls.SUBTREE_SCOPE,
        new String[] {"cn"},
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Chỉ dùng truy vấn này trên Active Directory có hỗ trợ matching rule tương ứng. Trên server khác, dùng adapter/query strategy riêng hoặc tự duyệt nested groups.

### 8.4. Primary group trong Active Directory

AD lưu primary group qua **primaryGroupID** trên user. Nó tham chiếu RID của group trong cùng domain. Quan hệ này không nhất thiết xuất hiện như một value thông thường trong member của group hoặc trong memberOf của user.

Do đó, nếu nghiệp vụ yêu cầu effective membership chính xác trên AD, cần tính cả primary group theo quy tắc AD. Không chỉ đọc memberOf rồi kết luận danh sách group đầy đủ.

## 9. memberOf không phải attribute portable

Tên memberOf xuất hiện ở nhiều directory, nhưng semantics không giống nhau:

- Trong Active Directory, memberOf là backlink do linked attribute member duy trì. Ứng dụng không ghi trực tiếp.
- Trong OpenLDAP, memberOf thường cần overlay/configuration riêng để duy trì reverse membership; không thể giả định server nào cũng cài overlay.
- Với POSIX group, memberUid không tự tạo một attribute memberOf chuẩn cho user.
- Với groupOfUniqueNames, reverse membership cần cơ chế server hoặc ứng dụng cụ thể.

Khi đọc memberOf, hãy hỏi:

1. Attribute có tồn tại trong schema hoặc được server cung cấp không?
2. Nó được lưu, tính động hay do overlay/plugin duy trì?
3. Nó phản ánh direct membership hay cả nested membership?
4. Nó có bao gồm primary group không?
5. ACL có cho bind identity đọc không?

Không dùng memberOf làm nguồn ghi chính nếu server quản lý nó như backlink. Cập nhật attribute gốc theo schema, sau đó đọc lại backlink nếu cần xác minh.

## 10. Thiết kế domain model không phụ thuộc schema

Domain model nên mô tả ý nghĩa nghiệp vụ mà ứng dụng cần, đồng thời giữ được semantics direct/effective membership. Ví dụ:

~~~java
package org.example.directory.domain;

import java.util.Set;

public record DirectoryGroup(
        String groupId,
        String displayName,
        GroupMembershipKind membershipKind,
        Set<String> directMemberIds) {
}

public enum GroupMembershipKind {
    DIRECT_ONLY,
    NESTED_SUPPORTED,
    VENDOR_RESOLVED_EFFECTIVE
}
~~~

Application service không nên biết thành viên được lưu trong memberUid hay uniqueMember. Đặt contract theo identity nghiệp vụ:

~~~java
package org.example.directory.application;

import java.util.Set;

public interface GroupMembershipDirectory {
    Set<String> findDirectMemberIds(String groupId);

    void addDirectMember(String groupId, String userId);

    void removeDirectMember(String groupId, String userId);
}
~~~

Mỗi adapter chịu trách nhiệm chuyển userId thành representation của server:

| Adapter | Resolve userId thành | Attribute ghi |
| --- | --- | --- |
| GroupOfNames adapter | User DN | member |
| GroupOfUniqueNames adapter | DN/NameAndOptionalUID | uniqueMember |
| POSIX adapter | Username | memberUid |
| Active Directory adapter | User DN và AD policy | member; memberOf do server duy trì |

Nếu cần effective membership, dùng contract riêng hoặc trả kết quả có loại membership rõ ràng. Không âm thầm trả nested/transitive results từ method có tên findDirectMemberIds.

### 10.1. Ví dụ adapter POSIX

~~~java
package org.example.directory.ldap.posix;

import java.util.Set;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.example.directory.application.GroupMembershipDirectory;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Component;

@Component
public class PosixGroupMembershipAdapter
        implements GroupMembershipDirectory {

    private final LdapTemplate ldapTemplate;
    private final PosixGroupRepository repository;
    private final PosixUserLookup userLookup;
    private final PosixGroupDnResolver groupDnResolver;

    public PosixGroupMembershipAdapter(
            LdapTemplate ldapTemplate,
            PosixGroupRepository repository,
            PosixUserLookup userLookup,
            PosixGroupDnResolver groupDnResolver) {
        this.ldapTemplate = ldapTemplate;
        this.repository = repository;
        this.userLookup = userLookup;
        this.groupDnResolver = groupDnResolver;
    }

    @Override
    public Set<String> findDirectMemberIds(String groupId) {
        PosixGroupEntry group = requireGroup(groupId);
        return userLookup.toApplicationIds(group.getMemberUids());
    }

    @Override
    public void addDirectMember(String groupId, String userId) {
        PosixGroupEntry group = requireGroup(groupId);
        String uid = userLookup.requireUid(userId);

        ldapTemplate.modifyAttributes(
                group.getDn(),
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.ADD_ATTRIBUTE,
                        new BasicAttribute("memberUid", uid))
                });
    }

    @Override
    public void removeDirectMember(String groupId, String userId) {
        PosixGroupEntry group = requireGroup(groupId);
        String uid = userLookup.requireUid(userId);

        ldapTemplate.modifyAttributes(
                group.getDn(),
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.REMOVE_ATTRIBUTE,
                        new BasicAttribute("memberUid", uid))
                });
    }

    private PosixGroupEntry requireGroup(String groupId) {
        Name authorizedDn = groupDnResolver.resolveAuthorized(groupId);
        return repository.findById(authorizedDn)
                .orElseThrow(GroupNotFoundException::new);
    }
}
~~~

Đây là skeleton để thể hiện ranh giới adapter; **PosixGroupRepository**, **PosixUserLookup**, **PosixGroupDnResolver** và exception là thành phần của ứng dụng cần triển khai. Resolver chỉ trả DN sau khi kiểm tra groupId và quyền caller; adapter không parse DN tùy ý do client gửi.

PosixUserLookup cũng chịu trách nhiệm chuyển memberUid thành application user ID khi đọc, và chuyển application user ID về uid khi ghi. Nếu username chính là user ID của ứng dụng, bước chuyển đổi có thể đơn giản hơn; vẫn giữ trách nhiệm đó bên trong adapter.

### 10.2. Định nghĩa contract rõ về membership

Không nên đặt một method mơ hồ như isMember(group, user) nếu chưa quyết định nó có tính nested/primary membership hay không. Tách rõ:

- isDirectMember: entry group có chứa user trực tiếp không?
- isEffectiveMember: user có quyền thông qua direct, nested hoặc primary group không?
- listDirectMembers: trả representation trực tiếp được lưu.
- listEffectiveMembers: trả kết quả đã mở rộng theo policy server/adapter.

Tên method phải nói đúng semantics để code phân quyền không vô tình bỏ qua nested group hoặc cấp quyền rộng hơn dự kiến.

## 11. Những khác biệt cần giữ trong adapter

| Khía cạnh | groupOfNames | groupOfUniqueNames | posixGroup | Active Directory |
| --- | --- | --- | --- | --- |
| Member attribute | member | uniqueMember | memberUid | member |
| Value type | DN | NameAndOptionalUID | Username | DN |
| Empty group | Không theo MUST member | Không theo MUST uniqueMember | Có thể nếu schema cho phép | Thường có thể |
| Reverse membership | Không mặc định | Không mặc định | Không mặc định | memberOf backlink |
| Primary group | Không có khái niệm chuẩn tương đương | Không có khái niệm chuẩn tương đương | gidNumber/Unix account semantics | primaryGroupID |
| Nested membership | Phụ thuộc ứng dụng/server | Phụ thuộc ứng dụng/server | Không được định nghĩa như group DN nesting trong RFC2307 | Có, với quy tắc AD |
| Transitive query | Không portable | Không portable | Không portable | Có matching rule riêng |

Không ép tất cả khác biệt vào một Boolean hoặc một Set<String> rồi bỏ metadata. Nếu application cần phân biệt membership source, hãy lưu membership kind và directory provider trong kết quả.

## 12. Bảo mật khi quản lý group membership

Group thường được dùng để cấp quyền truy cập. Một lỗi ghi membership có thể cấp quyền quá rộng hoặc xóa quyền của nhiều người. Vì vậy, quản lý group cần authorization ở application layer và ACL tối thiểu ở directory.

### 12.1. Không tin DN hoặc group name từ client

Client chỉ nên gửi identifier nghiệp vụ đã được API công bố. Service cần:

1. Resolve group identifier trong naming context được phép.
2. Resolve user identifier thành DN hoặc uid theo adapter.
3. Kiểm tra caller có quyền quản lý đúng group đó.
4. Xác minh user/group tồn tại và loại entry phù hợp.
5. Chỉ sửa attribute membership mà use case được phép.

Không nhận raw DN từ client rồi đưa thẳng vào modifyAttributes. DN là tên định danh trong directory, không phải bằng chứng caller được phép thao tác entry đó.

### 12.2. Filter escaping và DN escaping là hai việc khác nhau

Khi tìm group theo giá trị do người dùng cung cấp, dùng LdapQueryBuilder:

~~~java
ldapTemplate.search(
        query()
            .base("ou=groups")
            .where("cn").is(validatedGroupName),
        mapper);
~~~

Query builder giúp encode giá trị filter. Khi xây DN, dùng LdapNameBuilder/Rdn. Khi phải tạo raw LDAP filter cho extension của server, encode assertion value bằng API filter encoder của phiên bản Spring LDAP đang dùng. **Không dùng DN escaping thay cho filter escaping** vì hai cú pháp có quy tắc riêng.

### 12.3. Least privilege và ACL

Tách quyền đọc và ghi nếu use case cho phép:

- Service chỉ đọc group không cần quyền modify membership.
- Service quản lý một số OU chỉ được sửa member attribute trong OU đó.
- Không cấp quyền thay đổi objectClass, groupType, gidNumber hoặc schema nếu use case chỉ thêm user vào group.
- Không cấp quyền ghi memberOf/backlink do server quản lý.
- Dùng service identity riêng cho provisioning và authentication nếu quyền của chúng khác nhau.

Kiểm tra ACL bằng đúng bind identity mà ứng dụng dùng. Một truy vấn thành công với tài khoản administrator không chứng minh service account production có cùng quyền.

### 12.4. Idempotency và cập nhật đồng thời

ADD một value đã tồn tại có thể trả lỗi duplicate/attributeOrValueExists. REMOVE một value không tồn tại cũng có thể trả lỗi. Application service cần quyết định:

- Add member đã có: trả thành công như no-op hay báo conflict?
- Remove member không có: trả thành công như no-op hay báo not found?
- Hai request đồng thời: có retry hoặc map result code phù hợp không?
- Một group được cập nhật bởi nhiều service: ai là owner của membership?

Có thể đọc trạng thái trước để tránh operation lặp, nhưng read-then-write vẫn có race. Hãy xử lý result code sau Modify và định nghĩa idempotency rõ ràng.

Một LDAP ModifyRequest trên một entry được server xử lý như một operation nguyên tử theo protocol. Nhưng chuỗi thay đổi user, group, database và audit ở nhiều hệ thống không tự trở thành một transaction phân tán. Cần workflow, retry, journal hoặc reconciliation.

### 12.5. Không ghi dữ liệu nhạy cảm vào log

Không log password, token, raw DN, raw filter, toàn bộ member list hoặc attribute values không cần thiết. Có thể ghi metadata:

~~~text
operation=group-member-add
directory=people-primary
groupType=GROUP_OF_NAMES
memberRepresentation=DN
outcome=SUCCESS
correlationId=<opaque-id>
~~~

Nếu audit cần xác định actor và target, dùng opaque reference được kiểm soát, giới hạn quyền truy cập và retention. Không biến application log phổ thông thành bản sao danh sách group membership.

## 13. Hiệu năng và quy mô membership

### 13.1. Chọn base, scope và projection

Khi tìm group, đặt base hẹp và scope phù hợp:

- ONELEVEL nếu group nằm trực tiếp trong OU đã biết.
- SUBTREE nếu cấu trúc OU lồng nhau là một phần use case.
- Projection chỉ lấy cn, member hoặc attribute thực sự cần.
- Đặt count/time limit cho search do request kích hoạt.

Không search toàn naming context chỉ để tìm một group có identifier đã biết.

### 13.2. Tránh N+1 khi resolve member DN

Một group có hàng nghìn member DN. Nếu ứng dụng lookup từng user một, nó tạo ra hàng nghìn LDAP round-trip. Thay vào đó:

- Trả member reference khi API không cần profile đầy đủ.
- Batch resolve theo filter được xây an toàn.
- Giới hạn kích thước response và dùng paging/control khi phù hợp.
- Cache profile/member metadata với TTL và invalidate khi directory thay đổi.
- Xử lý entry bị xóa, DN stale và referral.

Với Active Directory, attribute member của group lớn có thể được trả theo cơ chế ranged retrieval (ví dụ member;range=0-1499). Không giả định một lần đọc Attributes luôn chứa toàn bộ member list; kiểm thử giới hạn của server và triển khai đọc tiếp các range khi use case cần toàn bộ thành viên.

Với posixGroup, memberUid là username nên batch resolution phải dùng uid filter. Với groupOfNames/AD, thành viên là DN nên batch resolution theo DN hoặc chiến lược search tương ứng.

### 13.3. Không tính effective membership bằng cách tải toàn directory

Nested group có thể tạo graph lớn hoặc có cycle. Hãy dùng matching rule được server hỗ trợ nếu semantics đã được kiểm chứng; nếu tự duyệt, giới hạn depth, visited set, số entry và thời gian. Không giữ kết quả effective membership vô thời hạn nếu quyền truy cập cần cập nhật nhanh.

### 13.4. Cache membership phải có policy

Membership thay đổi có thể ảnh hưởng quyền truy cập. Khi cache:

- Đặt TTL ngắn theo yêu cầu bảo mật.
- Invalidate sau thao tác add/remove thành công.
- Có cơ chế xử lý thay đổi được thực hiện ngoài ứng dụng.
- Không cache lỗi/empty result như membership không tồn tại nếu lỗi ACL hoặc timeout chưa được phân biệt.
- Xác định rõ cache lưu direct hay effective membership.

## 14. Kiểm thử tương thích theo từng server

Một integration test chạy với một schema không chứng minh ứng dụng tương thích với schema khác. Tạo **contract test suite** cho từng adapter và chạy trên server/profile tương ứng.

### 14.1. Test fixture groupOfNames

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

Test cần xác minh:

- ODM đọc cn và tất cả member DN.
- Add member thêm đúng một DN vào member.
- Remove member xóa đúng DN.
- Không xóa member cuối nếu schema yêu cầu ít nhất một value.
- Duplicate add được xử lý theo idempotency policy.

### 14.2. Test fixture posixGroup

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: posixGroup
cn: developers
gidNumber: 2201
memberUid: an
~~~

Test cần xác minh:

- Mapping dùng Set<String> cho memberUid.
- Add/remove ghi username, không ghi DN.
- Group có thể rỗng nếu schema server cho phép.
- Đổi username có workflow cập nhật membership tương ứng.

### 14.3. Test fixture Active Directory

Dùng domain test hoặc môi trường tương thích AD để xác minh:

- Group objectClass và các thuộc tính được trả về.
- Add/remove cập nhật member.
- memberOf được server duy trì, không ghi trực tiếp.
- groupType/security scope đúng policy.
- primaryGroupID được tính riêng.
- Nested membership query dùng đúng matching rule và trả kết quả như mong đợi.

Không dùng OpenLDAP test container để kết luận AD matching rule, primary group hoặc groupType hoạt động đúng.

### 14.4. Ví dụ integration test cho adapter groupOfNames

~~~java
package org.example.directory.ldap.openldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class GroupOfNamesIntegrationTest {
    @Autowired
    private LdapTemplate ldapTemplate;

    @Autowired
    private GroupOfNamesRepository repository;

    @Test
    void mapsMemberAsDnAndAddsOneMember() {
        Name groupDn = LdapNameBuilder
                .newInstance("ou=groups")
                .add("cn", "developers")
                .build();
        Name userDn = LdapNameBuilder
                .newInstance("ou=people")
                .add("uid", "binh")
                .build();

        GroupOfNamesEntry before = repository.findById(groupDn)
                .orElseThrow();
        assertTrue(before.getMembers().stream()
                .anyMatch(member -> member.toString().contains("uid=an")));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.ADD_ATTRIBUTE,
                        new BasicAttribute("member", userDn.toString()))
                });

        GroupOfNamesEntry after = repository.findById(groupDn)
                .orElseThrow();
        assertEquals(2, after.getMembers().size());
    }
}
~~~

Fixture phải seed user Binh trước test; test phải cleanup hoặc reset directory sau khi chạy. Đây là ví dụ khung, không phải test có thể chạy độc lập khi chưa có cấu hình LDAP test.

### 14.5. Ma trận contract test

| Ca | groupOfNames | groupOfUniqueNames | posixGroup | AD group |
| --- | --- | --- | --- | --- |
| Đọc direct members | member DN | uniqueMember | memberUid | member |
| Add member | DN | NameAndOptionalUID/DN | username | DN |
| Remove member | DN | NameAndOptionalUID/DN | username | DN |
| Empty group | Schema MUST member | Schema MUST uniqueMember | Theo schema | Theo AD policy |
| Reverse membership | Không mặc định | Không mặc định | Không mặc định | memberOf backlink |
| Nested membership | Policy ứng dụng/server | Policy ứng dụng/server | Không mặc định | Matching rule/AD semantics |
| Primary group | Không | Không | POSIX gid semantics | primaryGroupID |
| Duplicate add | Result code/idempotency | Result code/idempotency | Result code/idempotency | Result code/idempotency |
| ACL denied | Kiểm tra result | Kiểm tra result | Kiểm tra result | Kiểm tra result |
| Rename user | Kiểm tra DN references | Kiểm tra uniqueMember references | Kiểm tra username membership | Kiểm tra linked attributes/AD |

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Search không thấy thành viên POSIX | Đang tìm attribute member thay vì memberUid | Dùng posixGroup adapter và filter đúng attribute |
| Server từ chối tạo group rỗng | groupOfNames/groupOfUniqueNames yêu cầu member/uniqueMember | Chọn schema cho phép empty group hoặc policy khác |
| Add member báo duplicate | Value đã tồn tại | Xử lý result code theo idempotency contract |
| Remove member cuối thất bại | Vi phạm MUST attribute | Không xóa value cuối hoặc xóa group theo policy |
| DN user bị lưu vào memberUid | Nhầm member representation | Resolve DN thành uid trước khi ghi |
| Username bị lưu vào member | Nhầm member representation | Resolve user thành DN |
| memberOf không có giá trị | Server không hỗ trợ/không cấu hình reverse membership hoặc ACL ẩn | Kiểm tra server/overlay/schema và ACL |
| Ghi memberOf không thành công | Đây là backlink do server quản lý | Sửa attribute gốc member hoặc cấu hình server phù hợp |
| AD báo thiếu group membership | Chỉ đọc memberOf, bỏ qua primary group | Tính primaryGroupID theo semantics AD |
| User trong nested group không được tìm thấy | Chỉ kiểm tra direct membership | Dùng traversal hoặc query transitive được server hỗ trợ |
| Nested membership bị lặp vô hạn | Group graph có cycle | Dùng visited set và giới hạn depth |
| Rename user làm membership stale | DN hoặc uid được lưu làm reference | Thiết kế workflow đồng bộ và reconciliation |
| Mapping ODM sai | Entity dùng objectClass/attribute của schema khác | Tách entity và repository theo server profile |
| Test pass trên một LDAP nhưng fail trên production | Schema/ACL/vendor behavior khác | Chạy contract test trên đúng loại server |

## 16. Checklist trước khi hỗ trợ một LDAP server mới

- [ ] Xác định vendor, version và naming context.
- [ ] Đọc Root DSE và schema definitions.
- [ ] Xác định group objectClass và MUST/MAY attributes.
- [ ] Xác định member attribute và syntax của value.
- [ ] Kiểm tra group rỗng có hợp lệ không.
- [ ] Kiểm tra memberOf/reverse membership có tồn tại và ai duy trì.
- [ ] Xác định nested group và primary group semantics.
- [ ] Xác định DN/username rename có ảnh hưởng membership ra sao.
- [ ] Kiểm tra ACL của service bind identity.
- [ ] Tạo entity/adapter riêng và không dùng nhầm repository.
- [ ] Viết contract test cho read/add/remove/duplicate/empty/ACL.
- [ ] Kiểm thử trên đúng server/version sẽ chạy ở production.

## 17. Bài tập thực hành

1. So sánh LDIF của groupOfNames và posixGroup. Chỉ ra vì sao member DN không thể thay trực tiếp cho memberUid.
2. Tra schema groupOfUniqueNames và giải thích NameAndOptionalUID khác DN thuần ở điểm nào.
3. Tạo GroupOfNamesEntry và PosixGroupEntry. Vì sao nên dùng Set<Name> cho member và Set<String> cho memberUid?
4. Viết hai adapter addMember: một adapter ghi member bằng DN, một adapter ghi memberUid bằng username.
5. Thử xóa thành viên cuối cùng của groupOfNames trên server test. Giải thích schema result.
6. Phân biệt direct membership và effective membership bằng ví dụ nested group.
7. Vì sao memberOf trên OpenLDAP có thể không tồn tại nhưng trên AD thường được cung cấp?
8. Viết policy tính primary group của AD và nêu vì sao chỉ đọc memberOf là chưa đủ.
9. Thiết kế API phân biệt findDirectMemberIds và findEffectiveMemberIds.
10. Viết contract test chạy cùng interface trên OpenLDAP và AD test environment; nêu phần nào cần implementation riêng.
11. Thiết kế workflow khi user được rename nhưng membership đang lưu DN hoặc username.
12. Đưa ra cách xử lý add/remove idempotent khi có hai request đồng thời.

## 18. Tổng kết

LDAP group không có một schema đồng nhất. **groupOfNames** lưu DN trong member và yêu cầu member; **groupOfUniqueNames** dùng uniqueMember với syntax NameAndOptionalUID; **posixGroup** lưu username trong memberUid và có gidNumber; **Active Directory group** dùng member/memberOf cùng groupType, primaryGroupID và các semantics riêng.

Trước khi viết mapping, hãy đọc schema và xác minh ACL, MUST/MAY, syntax, direct/nested membership, empty group và reverse membership. Trong Spring Data LDAP, tạo entity/repository riêng cho từng schema; dùng LdapTemplate khi cần sửa đúng một member value. Đặt business contract ở domain layer và chuyển representation bằng adapter. Nhờ vậy, việc đổi LDAP server trở thành công việc thay adapter và contract tests thay vì phải viết lại toàn bộ business logic.

### Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — ODM, LdapTemplate, query builder và LDAP operations.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html) — objectClass matching, @Entry, @Attribute, @DnAttribute và mapping collection Name.
- [Spring LDAP — LdapEncoder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html) — filterEncode và nameEncode.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — LdapRepository và mapping entity.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519) — groupOfNames, groupOfUniqueNames và các schema phổ biến.
- [RFC 2307 — An Approach for Using LDAP as a Network Information Service](https://www.rfc-editor.org/rfc/rfc2307) — posixGroup, memberUid và POSIX account information.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Search, Modify và result codes.
- [Microsoft Learn — Group Objects](https://learn.microsoft.com/en-us/windows/win32/ad/group-objects) — Active Directory group object và membership.
- [Microsoft Learn — LDAP_MATCHING_RULE_IN_CHAIN](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax) — matching rule mở rộng để tìm linked attribute theo chuỗi.
