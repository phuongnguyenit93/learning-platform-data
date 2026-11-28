# Không giả định có @Version và khóa lạc quan như JPA

Khi xây dựng ứng dụng **Spring Data LDAP**, lập trình viên quen **Spring Data JPA** có thể nghĩ rằng chỉ cần thêm **@Version** lên một field là **repository.save(...)** sẽ kiểm tra phiên bản trước khi ghi. Suy luận này **không an toàn** đối với LDAP. Directory không phải cơ sở dữ liệu quan hệ do Hibernate/JPA quản lý; **DN**, **objectClass**, **schema**, **LDAP Modify** và các **LDAP Control** có ngữ nghĩa riêng. Một request đọc entry, sửa đối tượng Java rồi ghi lại có thể ghi đè thay đổi của request khác, ngay cả khi tất cả lệnh LDAP đều trả thành công.

Bài thuộc chương **Đồng thời và nhất quán** của module **SPRING_DATA_LDAP**. Mục tiêu là phân biệt rõ khóa lạc quan trong JPA với những cơ chế thật sự có trên directory: **LDAP Modify nguyên tử cho một entry**, cập nhật **delta** cho thuộc tính nhiều giá trị, **Assertion Control (RFC 4528)** để cập nhật có điều kiện nếu server hỗ trợ, và chiến lược xử lý **race condition**, **replication**, **rename DN** và **timeout** khi dùng **LdapRepository/LdapTemplate**.

> **Thông điệp chính:** Không có bảo đảm mặc định rằng **@Version** trên entity LDAP làm repository tự thêm điều kiện phiên bản vào lệnh ghi, tự tăng phiên bản và ném **OptimisticLockingFailureException** giống một JPA entity. Muốn bảo vệ trước ghi đè đồng thời, phải kiểm tra năng lực LDAP server và triển khai điều kiện ghi phù hợp ở **đúng thao tác Modify/Delete/ModifyDN**.

## 1. Khóa lạc quan trong JPA hoạt động thế nào?

Trong một entity JPA, **@Version** có ngữ nghĩa do JPA provider thực thi:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class JpaAccount {
    @Id
    private Long id;

    private String displayName;

    @Version
    private long version;

    // Constructor, getters và setters được lược bỏ.
}
~~~

Khi hai transaction cùng đọc **version = 5**, framework có thể thực hiện cập nhật tương đương:

~~~sql
UPDATE account
   SET display_name = ?, version = 6
 WHERE id = ? AND version = 5;
~~~

Một transaction cập nhật thành công sẽ chuyển version sang **6**. Transaction còn lại dựa vào version **5** không thể cập nhật cùng hàng theo điều kiện cũ; JPA provider phát hiện xung đột khi số hàng bị ảnh hưởng không đúng kỳ vọng và báo lỗi khóa lạc quan.

Ở đây, bảo đảm không chỉ đến từ annotation. Nó đến từ **ba yếu tố phối hợp**:

1. **Mapping** xác định thuộc tính version và ID.
2. **Persistence provider** sinh thao tác ghi có **điều kiện version**.
3. **Cơ sở dữ liệu** đánh giá điều kiện cùng thao tác ghi một cách nguyên tử.

Thiếu bước 2 hoặc 3, chỉ có một field tên **version** trong Java không bảo vệ được dữ liệu.

## 2. Spring Data LDAP không tự cung cấp cùng hợp đồng @Version

Spring LDAP ODM sử dụng annotation thuộc package **org.springframework.ldap.odm.annotations**. Những annotation chính gồm **@Entry**, **@Id**, **@Attribute**, **@DnAttribute** và **@Transient**; **@Id** dành cho **DN của entry**, có kiểu **javax.naming.Name**.

Ví dụ entity LDAP hợp lệ:

~~~java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
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

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private Set<String> emails;

    // Constructor không tham số, getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

**Không đặt một field @Version vào ví dụ rồi mặc định nó có hiệu lực.** Có hai annotation mà người học thường gặp trong hệ sinh thái Java:

| Annotation | Bối cảnh đúng | Có tự bật optimistic locking cho Spring LDAP ODM? |
| --- | --- | --- |
| **jakarta.persistence.Version** | JPA entity do JPA provider quản lý | **Không** |
| **org.springframework.data.annotation.Version** | Một số module Spring Data có hỗ trợ version store-specific | **Không có bảo đảm tự động cho LDAP repository** |
| **org.springframework.ldap.odm.annotations.Id** | DN của entry LDAP | **Không**; ID không phải version |
| **org.springframework.ldap.odm.annotations.Attribute** | Ánh xạ một LDAP attribute | **Không**; ánh xạ dữ liệu không đồng nghĩa kiểm tra thay đổi đồng thời |

Nếu tự thêm field Java tên **version** mà không thiết kế schema LDAP, hãy nhớ ODM có thể ánh xạ các field theo quy tắc của nó. Field không hợp lệ có nguy cơ khiến **save/update** vi phạm schema hoặc ghi giá trị không mong muốn. Dùng **@Transient** cho field không được persist và chỉ đưa attribute phiên bản nghiệp vụ vào schema khi có kế hoạch cụ thể.

### 2.1. Vì sao tên phương thức save dễ gây nhầm?

API repository cho phép sử dụng cú pháp quen thuộc:

~~~java
DirectoryPerson person =
    personRepository.findByUid("linh").orElseThrow();
// Cập nhật qua setter hợp lệ của entity:
person.setCommonName("Linh N.");
personRepository.save(person);
~~~

Mã sử dụng setter **setCommonName(...)** (cần bổ sung getter/setter trong lớp minh họa ở trên). Hai lời gọi **find** và **save** là hai thao tác tách biệt; có thể có writer khác sửa directory trong khoảng giữa.

Ở tầng ODM, việc cập nhật có thể liên quan đến đọc lại trạng thái hiện tại và tính các **ModificationItem** cho các attribute thay đổi. Điều đó **không tương đương** một lệnh SQL có điều kiện **WHERE version = oldVersion**. Nếu đối tượng Java chứa dữ liệu cũ so với server, việc tính diff và ghi vẫn có thể làm mất thay đổi của client khác. Hành vi chi tiết phụ thuộc phương thức và phiên bản thư viện; không suy ra tính an toàn từ tên **save**.

## 3. Lost update: hai request đọc cùng một LDAP entry

Giả sử entry ban đầu:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
description: Initial
mail: linh@lab.example
~~~

Hai request đọc cùng trạng thái tại thời điểm **T0**:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant L as LDAP server
    participant B as Request B
    A->>L: Read description=Initial
    L-->>A: Initial
    B->>L: Read description=Initial
    L-->>B: Initial
    A->>L: Modify REPLACE description=A
    L-->>A: success
    B->>L: Modify REPLACE description=B
    L-->>B: success
    Note over L: Cuối cùng description=B
    Note over A,B: A không biết giá trị A đã bị ghi đè
~~~

| Thời điểm | Request A | Request B | LDAP server |
| --- | --- | --- | --- |
| T0 | Đọc **Initial** | Đọc **Initial** | Initial |
| T1 | Chuẩn bị A | Chuẩn bị B từ snapshot cũ | Initial |
| T2 | **REPLACE** thành A, success | Chưa ghi | A |
| T3 | Hoàn tất | **REPLACE** thành B, success | B |

Cả hai lệnh Modify đều có thể hợp lệ và thành công. **LDAP không tự biết request B đang dựa vào snapshot trước thay đổi của A**, nếu request B không mang theo điều kiện kiểm tra. Đây là **lost update**.

### 3.1. Lost update không chỉ xảy ra với một String

Với nhóm LDAP có **member** đa trị:

~~~text
Ban đầu:
  member = {Linh}

Request A đọc {Linh} và thêm An:
  REPLACE member = {Linh, An}

Request B cũng đọc {Linh} và thêm Bình:
  REPLACE member = {Linh, Bình}

Nếu B ghi cuối:
  member = {Linh, Bình}  // An bị mất
~~~

Chuyển Java field từ **List<String>** sang **Set<Name>** không giải quyết xung đột này. **Set** biểu diễn tính chất không thứ tự của attribute, nhưng không biến thao tác ghi thành kiểm tra-and-set.

### 3.2. Trùng DN và tái tạo entry

DN có thể thay đổi khi rename/move. Nếu entry bị xóa rồi tạo mới với cùng DN, nó không mặc nhiên là cùng đối tượng cũ. **entryUUID** ở OpenLDAP hoặc **objectGUID** ở Active Directory giúp nhận diện object trong vòng đời của nó, nhưng **không phải số phiên bản**: cùng object có thể thay đổi nhiều lần mà UUID/GUID vẫn giữ nguyên.

## 4. LDAP Modify nguyên tử đến mức nào?

Theo LDAPv3, **một ModifyRequest** tác động tới **một entry** có thể mang một danh sách thay đổi attribute. LDAP server áp dụng các modification theo thứ tự trong request, và phải bảo đảm **tất cả thay đổi của request thành công hoặc không thay đổi nào được áp dụng**. Điều này hữu ích nhưng không giống transaction xuyên nhiều operation.

Ví dụ một request:

~~~text
ModifyRequest trên uid=linh,ou=people,...
  1. REPLACE description = "Approved"
  2. REPLACE mail = "linh.work@lab.example"

Một request -> server xét và thực thi như một đơn vị nguyên tử trên entry.
~~~

Ngược lại:

~~~text
Request 1: Read entry
Request 2: Modify description
Request 3: Modify mail
~~~

Ba request trên **không được bọc thành một transaction ACID** chỉ vì chúng được thực hiện tuần tự trong cùng Java method hoặc cùng callback **LdapTemplate.executeReadWrite(...)**.

| Hành vi | Bảo đảm nào? |
| --- | --- |
| Một ModifyRequest với nhiều ModificationItem trên cùng entry | Server phải xử lý các modification trong request như một thao tác nguyên tử |
| Read, sau đó Modify trong hai request | **Không nguyên tử**; writer khác có thể can thiệp |
| Compare, sau đó Modify | **Không nguyên tử**; có khoảng trống TOCTOU |
| Hai lần Modify trên hai entry khác nhau | Không mặc định có transaction chung |
| Repository.find rồi repository.save | Không mặc định có optimistic locking |
| LDAP callback dùng cùng DirContext | Cùng context không có nghĩa đã khóa entry |

**Mục tiêu cần tách riêng:** Tính **atomicity của một ModifyRequest** không phải bảo đảm **isolation** cho chuỗi đọc–tính toán–ghi của nhiều client.

## 5. Biện pháp đơn giản: gửi thay đổi dạng delta, không REPLACE mọi thứ

Khi chỉ cần **thêm một member** của nhóm, đừng đọc cả tập rồi REPLACE bằng một bản sao đã chỉnh sửa. Dùng LDAP **ADD_ATTRIBUTE** trực tiếp:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class GroupMembershipService {
    private final LdapTemplate ldapTemplate;

    public GroupMembershipService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMember(String fullMemberDn) {
        ModificationItem add = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", fullMemberDn)
        );

        // ContextSource base: dc=lab,dc=example.
        ldapTemplate.modifyAttributes(
            "cn=developers,ou=groups",
            new ModificationItem[]{add}
        );
    }
}
~~~

Giả định **fullMemberDn** là DN hợp lệ, đã được tạo bằng **LdapName/Rdn** hoặc xác minh từ nguồn tin cậy. Ví dụ thực tế phải kiểm tra quyền của caller để tránh tự ý thêm bất kỳ user nào vào nhóm. **groupOfNames** thường yêu cầu ít nhất một **member**.

Hai request cùng **ADD hai member khác nhau** thường không làm mất giá trị cũ của nhau như thao tác REPLACE từ snapshot lỗi thời. LDAP server tự áp dụng từng modification lên trạng thái hiện tại của entry.

Đặc tính cần xử lý:

- **ADD_ATTRIBUTE** một giá trị đã tồn tại có thể trả **attributeOrValueExists (20)**. Đây có thể là dấu hiệu thao tác đã được thực hiện hoặc dữ liệu không hợp lệ, tùy contract.
- **REMOVE_ATTRIBUTE** một giá trị cụ thể có thể trả **noSuchAttribute (16)** nếu giá trị không còn tồn tại.
- Nếu nhóm cần ít nhất một member, xóa member cuối cùng có thể vi phạm schema.
- Thao tác delta giúp tránh một dạng lost update, nhưng **không áp đặt điều kiện nghiệp vụ phức tạp**, ví dụ “chỉ cho thêm nếu tổng member chưa quá 10” hoặc “chỉ sửa nếu description chưa đổi”.

### 5.1. Một ModifyRequest chứa nhiều thay đổi có liên quan

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] modifications = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("description", "Approved")
    ),
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.work@lab.example")
    )
};

ldapTemplate.modifyAttributes(
    "uid=linh,ou=people",
    modifications
);
~~~

Đoạn mã minh họa nằm trong method có **ldapTemplate**; **uid=linh,ou=people** là DN tương đối với ContextSource base. Hai thay đổi thuộc **một LDAP Modify**. Điều đó tránh trạng thái chỉ áp dụng một nửa các ModificationItem nếu request bị từ chối, nhưng **vẫn không kiểm tra giá trị cũ**. Nếu có hai writer ghi những bộ giá trị khác nhau, request đến sau vẫn có thể ghi đè request trước.

## 6. Vì sao “đọc, so sánh, rồi ghi” không phải optimistic locking?

Một mẫu code hay xuất hiện:

~~~java
String latest = readDescriptionFromLdap();
if (latest.equals(expectedDescription)) {
    // Tưởng rằng đã an toàn...
    replaceDescriptionInLdap(newDescription);
}
~~~

Hai hàm ở đây là **pseudocode nghiệp vụ**: một hàm đọc LDAP và một hàm Modify. Giữa thao tác **đọc** và **thay thế**, writer khác có thể sửa dữ liệu.

~~~text
T0: A đọc description = initial
T1: B đọc description = initial
T2: A kiểm tra == initial -> true
T3: B kiểm tra == initial -> true
T4: A ghi description = A
T5: B ghi description = B

Cả hai đã kiểm tra thành công, nhưng A vẫn bị mất cập nhật.
~~~

Đây là lỗi **TOCTOU (time of check to time of use)**. Cách giảm thời gian giữa hai lời gọi, khóa **synchronized** trong một instance hoặc đọc lại nhiều lần **không tự loại bỏ race** ở LDAP server. Những ứng dụng khác, pod khác, quản trị viên hoặc công cụ LDAP ngoài hệ thống vẫn có thể sửa cùng entry.

### 6.1. Dùng LDAP Compare trước Modify thì sao?

LDAP **CompareRequest** có thể hỏi server liệu một attribute hiện có một giá trị nhất định hay không. Tuy nhiên, **Compare** và **Modify** là **hai request riêng**. Sau Compare thành công, một writer khác vẫn có thể sửa entry trước khi Modify được xử lý.

**Kết luận:** Compare hữu ích cho nghiệp vụ đọc/kiểm tra, không đủ để thay thế một điều kiện được server kiểm tra **trong cùng Modify operation**.

## 7. Tạo một field version trong Java vẫn chưa giải quyết được

Giả sử đội phát triển tự thêm thuộc tính LDAP **appRevision** vào schema, gán:

~~~ldif
appRevision: 7
description: Initial
~~~

Hai request đọc revision **7** rồi cùng gửi:

~~~text
REPLACE description = giá trị mới
REPLACE appRevision = 8
~~~

Nếu **không gửi điều kiện rằng appRevision hiện vẫn là 7**, cả hai request vẫn có thể thành công. Giá trị revision cuối có thể là **8** trong khi một thay đổi bị mất. **Increment ở client** cũng không thay thế được điều kiện ghi nguyên tử.

Một version hữu dụng cần:

1. Attribute được **schema server cho phép**, có ngữ nghĩa so sánh rõ ràng.
2. Mọi writer thuộc hệ thống tuân thủ quy tắc thay đổi version.
3. Server kiểm tra **expected version** ngay trong thao tác ghi.
4. Nếu khác, server **từ chối** thay vì silently overwrite.
5. Ứng dụng xử lý xung đột và không coi nó như một kết quả thành công.

**appRevision không phải một thuộc tính LDAP chuẩn được đảm bảo sẵn có.** Muốn sử dụng nó cần thiết kế schema/objectClass hoặc một cơ chế tương đương được directory quản lý. Ví dụ trên chỉ minh họa nguyên lý, không phải file LDIF có thể import vào mọi OpenLDAP hoặc AD mặc định.

## 8. LDAP Assertion Control (RFC 4528): điều kiện và Modify phải cùng request

**RFC 4528** định nghĩa **LDAP Assertion Control**, có OID **1.3.6.1.1.12**. Control cho phép gửi một LDAP filter để server đánh giá trên **entry mục tiêu** của thao tác.

~~~mermaid
flowchart TD
    A["Client đọc entry với version=v7"] --> B["Client gửi ModifyRequest"]
    B --> C["Kèm Assertion Control: appRevision=v7"]
    C --> D{"Server đánh giá assertion trên entry ngay trong thao tác Modify"}
    D -->|TRUE| E["Thực hiện Modify + đổi appRevision sang v8"]
    D -->|FALSE hoặc Undefined| F["Không sửa; LDAP assertionFailed (122)"]
    E --> G["Client nhận success"]
    F --> H["Client báo conflict, đọc lại state"]
~~~

Điểm khác biệt là **kiểm tra assertion và thực hiện thay đổi là một hành động nguyên tử theo quy định RFC**. Khi hai writer cùng gửi điều kiện **appRevision=v7** và request đầu đổi version sang **v8**, request còn lại không còn thỏa điều kiện và được từ chối với **assertionFailed (122)** — **nếu server hỗ trợ control** và mọi writer sử dụng nó đúng cách.

Các đặc tính:

| Thuộc tính của Assertion Control | Chi tiết |
| --- | --- |
| OID | **1.3.6.1.1.12** |
| Control value | **Filter được BER-encode**, không phải chuỗi UTF-8 thô |
| Criticality | Có thể TRUE/FALSE theo RFC; với thao tác cần an toàn thì phải yêu cầu **critical** |
| Điều kiện TRUE | Server cho phép thao tác tiếp tục theo quyền/schema |
| Điều kiện FALSE hoặc Undefined | **assertionFailed (122)**, không thực hiện thao tác |
| Nơi hỗ trợ | Tùy LDAP server, phiên bản và chính sách ACL |
| Phạm vi atomic | Assertion cùng **một** thao tác LDAP, không tạo transaction nhiều request |

Theo RFC, Assertion Control có thể đi với **Modify, Add, Delete, ModifyDN** và một số thao tác khác. Tuy nhiên phải kiểm tra tính hỗ trợ và ngữ nghĩa cụ thể của server, đặc biệt khi thay đổi DN, referral hoặc nhiều backend.

### 8.1. Kiểm tra server công bố control

LDAP server có thể công bố **supportedControl** trong **Root DSE**. Ví dụ với OpenLDAP client:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export BIND_DN='uid=reader,ou=services,dc=lab,dc=example'

ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "" -s base '(objectClass=*)' supportedControl
~~~

Tìm OID **1.3.6.1.1.12** trong kết quả. Thiếu OID **chưa đủ** để kết luận mọi client hoặc danh tính không thể dùng control, vì server có thể quảng bá có điều kiện; ngược lại, có OID cũng chưa chứng minh một bind identity có quyền Modify trên entry mục tiêu. Phải kiểm chứng bằng thao tác **có kiểm soát trong lab**.

**Không bao giờ âm thầm bỏ control để “cho ghi tiếp” khi server từ chối critical assertion.** Nếu tính đúng đắn phụ thuộc điều kiện ghi nguyên tử, fallback sang Modify không có điều kiện sẽ làm mất chính bảo đảm mà ứng dụng muốn có.

### 8.2. Không nhầm LDAP filter với BER control value

Đối với JNDI **LdapContext.setRequestControls(...)**, có thể tạo request control qua **javax.naming.ldap.BasicControl**, nhưng **control value của Assertion Control là LDAP Filter đã được BER-encode**. Gắn trực tiếp bytes từ **"(appRevision=7)".getBytes(UTF_8)** vào BasicControl là **không đúng RFC 4528**.

Khi cần hiện thực production, ưu tiên một LDAP SDK có **AssertionRequestControl** hỗ trợ encoder đúng chuẩn, hoặc một implementation BER/filter được kiểm chứng. Nếu dùng JNDI và **setRequestControls** trên context có pooling, phải quản lý vòng đời request control và reset trạng thái cẩn thận để không làm ảnh hưởng request tiếp theo.

## 9. Thử Assertion Control bằng ldapmodify trong môi trường lab

Ví dụ dùng một thuộc tính **description** có sẵn ở nhiều schema, để không bắt buộc cài custom **appRevision** trước khi học cơ chế. Đây là **kiểm tra có điều kiện trên chính description**, không phải hệ thống version tổng quát cho toàn entry.

### 9.1. Chuẩn bị entry và kiểm tra state

Giả sử đã có entry **uid=linh,ou=people,dc=lab,dc=example** với một giá trị:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
description: Initial
~~~

LDAP lab phải có suffix và OU cha trước khi import, cùng tài khoản **writer** có quyền đọc description và Modify entry. Kiểm tra bằng:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export WRITER_DN='uid=writer,ou=services,dc=lab,dc=example'
export PERSON_DN='uid=linh,ou=people,dc=lab,dc=example'

ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -b "$PERSON_DN" -s base '(objectClass=*)' dn description
~~~

### 9.2. Chuẩn bị một LDAP Modify

Nội dung **change-description.ldif**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: description
description: Approved-A
~~~

Chạy với **assertion critical**, chỉ cho phép cập nhật nếu entry hiện có **description=Initial**:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -e '!assert=(description=Initial)' \
  -f change-description.ldif
~~~

Trong cú pháp OpenLDAP command-line, **-e** bật general extension và dấu **!** làm assertion control thành **critical**. Nếu điều kiện TRUE, lệnh Modify được phép thực thi (nhưng vẫn có thể bị từ chối bởi ACL/schema). Nếu điều kiện không còn khớp, server hỗ trợ RFC 4528 sẽ trả **assertionFailed (122)**.

Chạy lại **cùng lệnh** sau khi lần đầu đã đổi description thành **Approved-A**. Ở lần thứ hai, assertion **description=Initial** không còn đúng nên việc ghi bị từ chối. Đây là cách quan sát trực tiếp điều kiện ghi tại server.

### 9.3. Giới hạn của việc dùng description làm token

Theo schema thông thường, **description** có thể là thuộc tính **đa trị**. Filter **(description=Initial)** chỉ khẳng định **có ít nhất một giá trị phù hợp**, không chứng minh mọi attribute của entry đều chưa đổi. Nếu writer khác sửa **mail** mà không sửa description, assertion này vẫn có thể TRUE.

Do đó để mô phỏng **version bảo vệ nhiều field**, nên thiết kế một **revision attribute đơn trị, được mọi writer quản lý**, trong schema/objectClass của môi trường đó, rồi gửi **REPLACE revision và các field nghiệp vụ trong cùng ModifyRequest kèm assertion trên revision cũ**.

## 10. Java: gửi Modify có Assertion Control qua LDAP SDK

**LdapRepository.save(...)** không tự cấp Assertion Control tương ứng với một field Java tùy ý. Muốn cập nhật có điều kiện, cần triển khai một **writer riêng** có khả năng gửi request control cùng LDAP Modify, kiểm tra server và xử lý result code **122**. Trong Java có thể làm ở tầng **JNDI LdapContext** với filter BER-encoded đúng chuẩn, hoặc dùng một LDAP SDK có sẵn encoder.

Ví dụ sau dùng **UnboundID LDAP SDK** để minh họa ý tưởng. Đây là **dependency bổ sung, không phải phần mặc định bắt buộc của Spring Data LDAP**; lựa chọn SDK phải phù hợp chính sách vận hành và phiên bản của dự án.

~~~xml
<!-- Đặt trong dependencies của Maven project; BOM/version do dự án quản lý. -->
<dependency>
    <groupId>com.unboundid</groupId>
    <artifactId>unboundid-ldapsdk</artifactId>
</dependency>
~~~

Đoạn Java này minh họa **cập nhật description và revision có điều kiện** với schema **appRevision** đã được cấu hình. Giả định **connection** đã được tạo và bind an toàn bằng LDAPS/StartTLS, có quyền cần thiết; nó không mở một kết nối thiếu TLS:

~~~java
import com.unboundid.ldap.sdk.Filter;
import com.unboundid.ldap.sdk.LDAPConnection;
import com.unboundid.ldap.sdk.LDAPException;
import com.unboundid.ldap.sdk.Modification;
import com.unboundid.ldap.sdk.ModificationType;
import com.unboundid.ldap.sdk.ModifyRequest;
import com.unboundid.ldap.sdk.ResultCode;
import com.unboundid.ldap.sdk.controls.AssertionRequestControl;

public final class GuardedProfileWriter {

    public void updateDescription(
            LDAPConnection connection,
            String targetDn,
            long expectedRevision,
            String newDescription) throws LDAPException {

        long nextRevision = Math.addExact(expectedRevision, 1L);

        // Hai thay đổi nằm trong cùng một ModifyRequest.
        ModifyRequest request = new ModifyRequest(
            targetDn,
            new Modification(
                ModificationType.REPLACE,
                "description",
                newDescription
            ),
            new Modification(
                ModificationType.REPLACE,
                "appRevision",
                Long.toString(nextRevision)
            )
        );

        // Filter được LDAP SDK BER-encode đúng chuẩn RFC 4528.
        Filter expected = Filter.createEqualityFilter(
            "appRevision",
            Long.toString(expectedRevision)
        );
        request.addControl(new AssertionRequestControl(expected));

        try {
            connection.modify(request);
        } catch (LDAPException ex) {
            if (ResultCode.ASSERTION_FAILED.equals(ex.getResultCode())) {
                throw new DirectoryRevisionConflictException(
                    "Entry changed since it was read", ex);
            }
            throw ex;
        }
    }

    public static final class DirectoryRevisionConflictException
            extends RuntimeException {
        public DirectoryRevisionConflictException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

**Điều kiện bắt buộc trước khi dùng mã:**

1. Schema của server có attribute **appRevision** với giá trị đơn, matching rule thích hợp; objectClass của entry cho phép nó.
2. Entry thực sự có revision ban đầu, ví dụ **7**, và mọi writer muốn giữ hợp đồng này đều cập nhật revision đúng.
3. Server **hỗ trợ Assertion Control (OID 1.3.6.1.1.12)** và tài khoản bind có quyền đọc/đánh giá attribute trong assertion, đồng thời có quyền Modify.
4. Client đã kết nối bằng **LDAPS/StartTLS xác minh chứng chỉ**, với bind credentials an toàn.
5. Input **targetDn**, **newDescription** và quyền nghiệp vụ đã được validate trước thao tác ghi.

Nếu hai writer cùng gọi với **expectedRevision=7**, request đầu thành công sẽ đặt revision thành **8**. Request còn lại không thỏa assertion và nhận **122**. Nếu writer khác không tuân theo revision hoặc được cấp khả năng sửa dữ liệu mà không đổi revision, giải pháp này **không phát hiện được** thay đổi đó. Không tự hứa tính nhất quán tuyệt đối khi nhiều hệ thống ngoài dự án cùng ghi LDAP.

### 10.1. Nếu không muốn thêm LDAP SDK?

Có thể dùng JNDI **javax.naming.ldap.LdapContext** và **setRequestControls(...)** cùng **BasicControl**, nhưng phải có **BER-encoded LDAP Filter** đúng RFC 4528. Spring LDAP có **ContextExecutor** để dùng API JNDI cấp thấp, song không phải mọi wrapper/pool context đều bảo đảm tiện lợi như một LdapContext trực tiếp.

Nếu tự cài đặt, phải **kiểm tra server/provider, không tái sử dụng request control sai ngữ cảnh, reset trạng thái control khi phù hợp**, đóng context và kiểm thử trên directory đích. Một string LDAP filter là **đầu vào cần được encode**, không phải control bytes có thể đưa thẳng vào **BasicControl**.

**Đừng tự chế mã BER từ user input** nếu không thật sự nắm vững ASN.1/LDAP Filter và escaping. Nếu dự án không chấp nhận SDK khác, nên có adapter JNDI được kiểm thử riêng, thay vì phân tán logic control trong mỗi service.

## 11. Thiết kế service Spring Data LDAP với conditional writer

Repository rất hữu ích cho **đọc, tìm kiếm, ODM và CRUD đơn giản**; cơ chế conditional write nên được thể hiện thành hợp đồng rõ ràng của service thay vì đặt ẩn bên trong setter Java.

~~~mermaid
flowchart TD
    A["HTTP PUT /people/{id} + expectedRevision"] --> B["Service: kiểm tra quyền và input"]
    B --> C["LDAP reader: DN, profile, revision hiện tại"]
    C --> D["Người gọi tạo thay đổi dựa trên revision đã thấy"]
    D --> E["Guarded LDAP writer"]
    E --> F["ModifyRequest + critical Assertion Control"]
    F --> G{"LDAP result"}
    G -->|success| H["Trả profile mới / revision mới"]
    G -->|assertionFailed 122| I["HTTP 409 Conflict hoặc lỗi nghiệp vụ tương đương"]
    G -->|Lỗi mạng, ACL, schema| J["Phân loại và xử lý riêng"]
~~~

Ví dụ interface thể hiện contract, không ràng buộc domain service với chi tiết UnboundID hay JNDI:

~~~java
public interface ConditionalDirectoryWriter {
    void updateDescription(
        String fullDn,
        long expectedRevision,
        String newDescription
    );
}
~~~

Service gọi qua interface này để đảm bảo một code path có điều kiện thay vì gọi **repository.save(...)** tùy ý khi cần chống lost update. Adapter bên dưới triển khai Assertion Control hoặc cơ chế bảo đảm tương đương mà server hỗ trợ.

**Không đồng nhất HTTP 409 với mọi lỗi LDAP.** Trả conflict cho **assertionFailed (122)** phù hợp khi request có điều kiện và phiên bản đã đổi. Lỗi bind, timeout, noSuchObject hay schema cần được phân loại riêng:

| LDAP result / tình huống | Ý nghĩa | Phản hồi nghiệp vụ có thể chọn |
| --- | --- | --- |
| **0 success** | Modify được server chấp nhận | Thành công |
| **122 assertionFailed** | Điều kiện cũ không còn đúng hoặc không thể xác định là TRUE | Xung đột trạng thái, yêu cầu đọc lại; thường HTTP 409 |
| **12 unavailableCriticalExtension** | Server không hỗ trợ critical control | Lỗi năng lực hạ tầng/cấu hình; **không ghi không điều kiện** |
| **16 noSuchAttribute** | Attribute hoặc giá trị yêu cầu xử lý không có | Lỗi trạng thái dữ liệu/logic |
| **20 attributeOrValueExists** | ADD trùng giá trị | Quy tắc duplicate/idempotency |
| **32 noSuchObject** | DN đích bị xóa/đổi hoặc không được thấy | Tìm lại theo ID, kiểm tra ACL và rename |
| **49 invalidCredentials** | Bind không thành công | Lỗi xác thực LDAP |
| **50 insufficientAccessRights** | Không đủ quyền thực hiện thao tác | Lỗi phân quyền |
| **65 objectClassViolation** | Thay đổi trái schema | Lỗi schema/dữ liệu |
| **Timeout / mất kết nối** | Không biết chắc response/trạng thái commit | Xác minh lại trước retry |

### 11.1. Thay đổi API công khai

Một HTTP client có thể gửi **expectedRevision** từ lần GET trước. Đây là input giúp conditional writer kiểm tra trạng thái, **không phải bằng chứng quyền sửa**. Server ứng dụng vẫn phải authorize người gọi theo quy tắc nghiệp vụ, và LDAP server vẫn phải áp dụng ACL cho bind identity.

Nếu cần **ETag/If-Match**, ETag phải dựa trên một token có ngữ nghĩa phù hợp và việc so khớp phải kết thúc ở một **điều kiện ghi nguyên tử phía server**. Chỉ kiểm tra **If-Match** trong controller rồi gọi LDAP Modify không điều kiện sẽ vẫn có khoảng race.

## 12. Các thuộc tính “giống version” không tự thành @Version

Directory server có các operational attributes hữu ích để quan sát thay đổi. Tuy nhiên chúng **không tự cấp** optimistic locking trong Spring Data LDAP:

| Thuộc tính | Server/ngữ cảnh | Dùng để làm gì? | Tại sao không mặc định là JPA @Version? |
| --- | --- | --- | --- |
| **modifyTimestamp** | Nhiều LDAP server theo schema chuẩn | Ghi nhận thời gian thay đổi entry | Độ phân giải, thời điểm gán, khả năng matching và replication phụ thuộc server; không bảo đảm token duy nhất cho từng thay đổi |
| **entryCSN** | OpenLDAP với cơ chế đồng bộ/replication phù hợp | Quan sát change sequence của entry | Là metadata vận hành của server, không tự được mapper dùng làm điều kiện Modify |
| **uSNChanged** | Active Directory DS | Theo dõi thứ tự cập nhật trên một domain controller | **Không được replicate như một giá trị chung**; có thể khác giữa các DC |
| **whenChanged** | Active Directory | Thời điểm object bị thay đổi | Không phải CAS token chuẩn toàn directory |
| **entryUUID** | OpenLDAP hỗ trợ RFC 4530 | Nhận diện cùng entry qua rename/move | ID thường không đổi khi entry được sửa |
| **objectGUID** | Active Directory | Nhận diện cùng directory object | ID không thay đổi theo từng lần Modify |
| **appRevision** (tự thiết kế) | Schema custom của ứng dụng | Token version nếu được mọi writer duy trì | Cần schema, quy tắc update và **Assertion Control trong cùng Modify** |

### 12.1. Vì sao modifyTimestamp có giới hạn?

Nếu dùng **modifyTimestamp** để phát hiện thay đổi, cần xác nhận **server cập nhật trường này khi nào, độ phân giải và matching rule**. Hai thay đổi liên tiếp có thể không được biểu diễn thành hai token khác biệt đủ mạnh trong mọi môi trường. Việc giá trị nhìn thấy trong SearchResult cũng phụ thuộc requested operational attributes và ACL.

**Không giả định mọi server cho phép filter assertion trên modifyTimestamp** hoặc nó là một revision counter tăng tuần tự cho tất cả thao tác. Nếu môi trường cho phép dùng nó làm guard, phải chứng minh bằng integration test với thay đổi nhanh và đồng thời trên đúng directory.

### 12.2. Vì sao uSNChanged không dùng xuyên domain controller?

Trong **AD DS**, Microsoft nêu rõ **uSNChanged được domain controller địa phương gán và không được replicate**. Khi cùng object được đọc trên hai DC, giá trị uSNChanged có thể khác nhau. Một service load-balanced qua nhiều DC không thể lấy một giá trị uSNChanged ở DC A rồi mặc định xem nó là phiên bản tương đương ở DC B.

Nếu bài toán yêu cầu nhất quán giữa nhiều DC, cần thiết kế **nơi đọc/ghi, đường replication và token kiểm soát được hỗ trợ tại server đích** thay vì dùng một USN tùy tiện như row version toàn hệ thống.

### 12.3. Operational attributes có thể bị thiếu trong kết quả

Ví dụ kiểm tra trên OpenLDAP:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b 'uid=linh,ou=people,dc=lab,dc=example' -s base \
  '(objectClass=*)' dn entryUUID modifyTimestamp entryCSN
~~~

Nếu không thấy **entryCSN** hoặc một field metadata, chưa đủ để kết luận server không quản lý thay đổi. Có thể directory/backend không hỗ trợ, không trả operational attribute được yêu cầu, hoặc ACL hạn chế đọc. **Không dùng metadata rỗng để tự tạo token mới rồi ghi đè server**.

## 13. Rename, delete và recreate: xung đột không chỉ là sửa attribute

Một entry LDAP có thể đổi **DN** khi rename RDN hoặc move OU. Khi client giữ DN cũ:

~~~text
T0: A đọc DN uid=linh,ou=people,...
T1: Admin chuyển entry sang uid=linh,ou=engineering,...
T2: A gửi Modify vào DN cũ
T3: Server có thể trả noSuchObject (32)
~~~

Giữ **entryUUID/objectGUID** giúp ứng dụng tìm DN hiện tại, nhưng bản thân ID ổn định không chứng minh bản ghi chưa thay đổi kể từ lúc A đọc. Nếu cần bảo vệ thao tác **ModifyDN**, phải xét điều kiện ở chính thao tác tương ứng hoặc mô hình cập nhật khác được server hỗ trợ.

### 13.1. Xóa rồi tạo lại dưới cùng DN

Nếu một entry bị xóa rồi được tạo lại với cùng DN nhưng UUID/GUID khác, đây thường là **một object khác**. Không tự liên kết quyền, lịch sử và cached version cũ sang object mới chỉ vì DN/uid giống nhau.

Đối với thao tác update nhạy cảm, có thể cần điều kiện **nhận diện đúng object** cùng với **revision của object**. Một kiểm tra bằng DN đơn lẻ không bảo vệ khỏi trường hợp **delete + recreate**.

### 13.2. Xung đột khi ModifyDN

Hai client muốn chuyển một entry sang hai OU khác nhau có thể làm DN mà bên còn lại đang dùng trở nên không tồn tại. Không retry rename mù quáng khi gặp timeout hoặc noSuchObject; trước tiên tìm entry theo định danh ổn định, xem vị trí hiện tại và xác minh yêu cầu nghiệp vụ.

## 14. Replication: đọc ở một node, ghi ở node khác

Directory doanh nghiệp thường có nhiều LDAP replica hoặc domain controller:

~~~text
T0: LDAP node A chứa revision 7
T1: Writer cập nhật node A -> revision 8
T2: Node B chưa đồng bộ, vẫn cho kết quả revision 7
T3: Client đọc node B, tưởng dữ liệu mới nhất là 7
T4: Client gửi update sang node A
~~~

Nếu node A hỗ trợ Assertion Control và kiểm tra **revision=7** trong cùng Modify, request ở T4 sẽ bị từ chối vì node A đã có revision 8. Đây là hành vi an toàn hơn việc chỉ so sánh ở client.

Tuy nhiên:

- Một kết quả GET từ replica B có thể là **stale read** dù request thành công.
- Không phải LDAP node nào cũng nhận write; topology có thể gồm read-only replicas, writable DC hoặc proxy/referral.
- Replication có **độ trễ**, và các server khác nhau có thể có metadata vận hành khác nhau.
- Nếu hai writer ghi vào **hai writable replica** trước khi đồng bộ, kết quả phụ thuộc cơ chế conflict resolution của directory; **Assertion Control trên một node không tự tạo single-copy serializability toàn cluster**.
- Muốn read-after-write, có thể cần **sticky endpoint**, đợi replication hoặc API nhất quán được server cung cấp. Chọn giải pháp theo yêu cầu thực tế, không chỉ tăng LDAP time limit.

Một thiết kế có yêu cầu xung đột nghiêm ngặt phải xác định **directory authority** cho thao tác ghi, phạm vi nhận diện object và điều kiện server-side. Không giả định mở rộng số replica đồng nghĩa ứng dụng có transaction phân tán.

## 15. Retry, timeout và cách xử lý xung đột

Một read timeout xảy ra sau khi gửi LDAP Modify có thể khiến client **không biết** server đã áp dụng thay đổi hay chưa:

~~~text
Client -> server: Modify with assertion revision 7 -> 8
Server: Modify thành công, revision bây giờ 8
Đường mạng mất trước khi client nhận ModifyResponse
Client: read timeout
~~~

Client không nên lập tức retry với revision 7 rồi diễn giải **assertionFailed (122)** thành “lệnh đầu chắc chắn thất bại”. Lệnh đầu có thể đã thành công và điều kiện cũ không còn đúng **chính vì lệnh đó**.

Quy trình đề xuất:

1. **Phân loại lỗi:** conflict 122, timeout, TLS, quyền, schema và DN không tồn tại là các nhánh khác nhau.
2. **Đọc lại state trên nguồn đáng tin cậy** nếu thao tác ghi có trạng thái không rõ.
3. **So sánh kết quả thực với ý định nghiệp vụ**: description/membership/revision hiện tại.
4. Nếu trạng thái đã là điều mong muốn, quyết định coi request đã hoàn tất theo chính sách idempotency.
5. Nếu state khác kỳ vọng, trả conflict hoặc yêu cầu người dùng hòa giải; chỉ retry khi có **căn cứ an toàn**.
6. Với thao tác quan trọng, có thể lưu **operation ID** ở một hệ thống nhất quán khác để tránh áp dụng trùng — nhưng điều này tạo ra bài toán phối hợp nhiều hệ thống cần thiết kế riêng.

| Tình huống | Có thể retry tự động? | Lưu ý |
| --- | --- | --- |
| **Search/read** thất bại tạm thời | Có thể, có giới hạn | Cần deadline tổng và tránh tạo tải thừa |
| **assertionFailed (122)** | **Không retry bằng snapshot cũ** | Cần đọc lại, giải quyết conflict |
| **Modify ADD một member** gặp attributeOrValueExists | Xử lý theo mục đích nghiệp vụ | Nếu member đã có, có thể coi kết quả đạt mục tiêu sau khi xác minh |
| **Modify REPLACE** gặp read timeout | Không retry mù quáng | Có thể đã ghi và bị request khác sửa tiếp |
| **Delete/rename** gặp timeout | Cần xác minh trạng thái object | DN có thể đã thay đổi |
| **unavailableCriticalExtension (12)** | Không hạ cấp sang ghi không điều kiện | Chuyển lỗi cấu hình/năng lực server |
| **invalidCredentials (49)** | Không | Sửa thông tin xác thực |

### 15.1. Không lấy tên exception làm toàn bộ contract

**Spring LDAP** dịch nhiều **javax.naming.NamingException** sang runtime exception của Spring LDAP. LDAP assertion failure có thể xuất hiện qua một loại ngoại lệ phụ thuộc provider/thư viện; khi dùng UnboundID có thể lấy trực tiếp **LDAPException.getResultCode()**. Đừng giả định Spring Data LDAP sẽ tự ném **OptimisticLockingFailureException** khi server trả 122; adapter cần ánh xạ thành lỗi domain riêng.

## 16. Bảo mật khi thực hiện conditional update

**Chống lost update** không thay thế **ủy quyền** và **bảo mật LDAP**:

- **TLS:** gửi simple bind credentials qua **LDAPS/StartTLS** với certificate chain và hostname verification. Không tắt TLS kiểm tra để thử Assertion Control.
- **ACL:** bind DN của ứng dụng phải có quyền đọc attribute dùng trong assertion và quyền Modify mục tiêu theo chính sách server. Điều kiện filter thất bại có thể phản ánh quyền quan sát hạn chế, không chỉ version thay đổi.
- **Kiểm tra caller:** expectedRevision từ HTTP request không chứng minh người gửi được quyền sửa. Luôn thực hiện authorization ở tầng ứng dụng và LDAP.
- **DN an toàn:** dùng **LdapName/Rdn** khi dựng DN từ input; không nối chuỗi vào RDN tùy ý.
- **Filter an toàn:** dùng **LdapQueryBuilder**, **Filter.createEqualityFilter(...)** hoặc encoder RFC 4515 đúng chuẩn; không nhét input vào filter assertion bằng nối chuỗi.
- **Critical control:** nếu cần điều kiện ghi, phải bảo đảm server không bỏ qua control không hỗ trợ. Không dùng fallback nguy hiểm.
- **Thông tin log:** không log password, raw environment, sensitive attribute values hoặc full DN không cần thiết. Có thể log operation ID, mã kết quả, loại xung đột và directory endpoint đã được phép.
- **Giới hạn tài nguyên:** áp dụng connect/read timeout và giới hạn tìm kiếm để tránh bị request chờ vô hạn. Timeout không tự trả về thông tin commit chắc chắn.

### 16.1. Khi custom revision thay đổi qua nhiều ứng dụng

Nếu quản trị viên hoặc một ứng dụng khác có quyền sửa trực tiếp directory mà **không tăng appRevision**, điều kiện revision có thể vẫn TRUE dù entry bị sửa. Vì vậy cần:

1. Quy định **owner** của các attribute được kiểm soát.
2. Định tuyến mọi update liên quan qua một **conditional writer** hoặc một cơ chế server-side bảo đảm cập nhật revision.
3. Giới hạn ACL để ngăn các writer ngoài quy trình cập nhật những thuộc tính được bảo vệ, trong phạm vi thực tế.
4. Audit những đường ghi khác và kiểm thử xung đột khi dữ liệu bị thay bởi LDAP client độc lập.

Không có cách nào biến **@Version** thành bảo đảm toàn hệ thống nếu các writer bỏ qua điều kiện cập nhật.

## 17. Kiểm thử hai writer và những race condition quan trọng

Một unit test chỉ kiểm tra entity có field **version** hoặc repository mock đã gọi **save** **không chứng minh** server đang chống lost update. Cần kiểm thử qua LDAP server thật hoặc server test hỗ trợ **Assertion Control** theo RFC 4528.

### 17.1. Ma trận kiểm thử

| Ca thử | Cách tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| Update bình thường | Read revision 7 rồi Modify với assertion 7 | Success, revision thành 8 |
| **Hai writer cùng revision** | A/B cùng thấy revision 7, gửi hai Modify có assertion | **Chỉ một thành công; một conflict 122**, nếu cùng authority và mọi điều kiện hợp lệ |
| Update không có assertion | A/B cùng snapshot cũ rồi REPLACE | Có thể cả hai success, mất cập nhật |
| ADD hai member khác nhau | Hai client gửi ADD từng giá trị | Giữ cả hai member nếu server cho phép |
| ADD trùng member | Hai client ADD cùng DN | Một có thể success, bên kia nhận lỗi duplicate 20 |
| Assert trên attribute không được phép đọc | Reader/Writer thiếu quyền filter | Không giả định là version mismatch; kiểm tra ACL |
| Critical control không được hỗ trợ | Dùng server không hỗ trợ assertion | Phải bị từ chối; không ghi fallback |
| Delete + recreate | Xóa object cũ rồi tạo lại với cùng DN | Nhận diện object mới qua entryUUID/objectGUID khác |
| Rename khi client giữ DN cũ | Move entry sang OU khác trước Modify | Kiểm tra noSuchObject/định danh hiện tại |
| Read replica cũ | Đọc B trước replication, ghi A | Conditional write A kiểm tra trạng thái ở A |
| Timeout sau commit | Proxy chặn ModifyResponse sau khi server ghi | Client không retry mù quáng; kiểm tra state |
| Hai writable replica | Gửi concurrent writes tới hai node | Đánh giá quy tắc replication/conflict thực tế của directory |

### 17.2. Dùng CountDownLatch để tái hiện race

Trong integration test, tạo **hai LDAP client/connection riêng** để tránh chia sẻ cùng một connection JNDI/SDK không phù hợp giữa hai thread. Dùng **CountDownLatch** để hai writer sẵn sàng trước khi cùng gửi lệnh.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

// Pseudocode phần thân integration test:
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);
ExecutorService pool = Executors.newFixedThreadPool(2);

// writerA, writerB: hai Callable<Result> sử dụng hai kết nối riêng,
// cùng expectedRevision=7, nhưng newDescription khác nhau.
Future<?> first = pool.submit(() -> {
    ready.countDown();
    start.await();
    return writerA.call();
});
Future<?> second = pool.submit(() -> {
    ready.countDown();
    start.await();
    return writerB.call();
});

try {
    ready.await();
    start.countDown();
    first.get();
    second.get();
} finally {
    start.countDown(); // Không giữ hai worker đang chờ nếu test lỗi.
    pool.shutdownNow();
}
~~~

Đây là **pseudocode hướng dẫn tổ chức test**, chưa phải một test Java độc lập có thể biên dịch vì **writerA/writerB** phải được triển khai, quản lý kết nối và trả kết quả/exception phù hợp. Test hoàn chỉnh cần thiết lập schema, LDIF fixture, TLS, tài khoản được quyền Modify và assertions trên kết quả của cả hai Future.

**Mục tiêu xác minh:** Với **một authority hỗ trợ Assertion Control** và hai request tranh chấp revision giống nhau, một kết quả phải là success, kết quả còn lại là **assertionFailed (122)**. Sau khi đọc lại directory, revision mới phải phản ánh đúng **một** bước tiến, và description phải khớp writer thành công.

### 17.3. Tránh test có kết quả giả

- Đừng chỉ kiểm tra **hai thread đã chạy**: phải buộc chúng **đọc cùng revision cũ**.
- Đừng dùng **Thread.sleep** để điều phối; dùng latch/barrier giúp test có tính xác định hơn.
- Đừng dùng một **LDAPConnection** cho hai writer nếu SDK/client không cho phép cách dùng đó trong bài test.
- Nếu hai request vào **hai replica khác nhau**, kết quả không còn là test tính nguyên tử của một server đơn; đây là bài kiểm tra replication riêng.
- Đừng chạy lỗi mạng/timeout có chủ ý trên production.
- Mock JPA repository không chứng minh hỗ trợ LDAP assertion control.

## 18. Bài thực hành và câu hỏi ôn tập

### 18.1. Bài thực hành từng bước

1. Tạo directory lab có suffix **dc=lab,dc=example**, nhánh **ou=people**, entry **uid=linh** với **description=Initial**.
2. Dùng **ldapsearch** đọc DN, description và các operational attributes mà server cho phép.
3. Tạo hai chương trình ghi không điều kiện **REPLACE description** từ cùng trạng thái cũ. Quan sát rằng request ghi sau có thể che request trước.
4. Dùng **ldapmodify -e '!assert=(description=Initial)'** để thực hiện một lần update và thử lặp lại. Xác minh mã **122** lần thứ hai.
5. Tìm **1.3.6.1.1.12** trong **Root DSE supportedControl** và xác minh trên server lab rằng critical control được chấp nhận.
6. Nếu quản trị viên cho phép, bổ sung schema/attribute **appRevision**, đặt revision ban đầu và dùng writer Java có assertion để cập nhật cả revision lẫn description trong cùng ModifyRequest.
7. Viết integration test hai writer với expected revision giống nhau; kiểm tra đúng một success và một conflict.
8. Thử nhóm **groupOfNames** với hai lệnh **ADD_ATTRIBUTE member** khác nhau rồi so sánh với cách REPLACE từ snapshot cũ.
9. Thử một tình huống **rename DN** và, nếu lab có replica, đối chiếu state giữa các endpoint.
10. Viết lại chính sách API: phân biệt kết quả không tồn tại, lỗi timeout, lỗi ACL và conflict 122; không nuốt mọi lỗi thành danh sách rỗng.

### 18.2. Câu hỏi ôn tập

1. Vì sao **@Version** của JPA không có tác dụng chỉ nhờ được thêm vào một class ODM LDAP?
2. **@Id** trong Spring LDAP ODM đánh dấu gì và tại sao nó không thể thay phiên bản?
3. Khác nhau giữa **atomic ModifyRequest** và **read–modify–write** là gì?
4. Vì sao một lệnh LDAP **Compare** rồi **Modify** không chống lost update?
5. Tại sao **ADD_ATTRIBUTE member** thường an toàn hơn REPLACE cả tập member khi hai request thêm người khác nhau?
6. Assertion Control có OID nào, filter được encode ra sao và result code khi điều kiện sai là gì?
7. Tại sao criticality phải được giữ khi điều kiện ghi là bắt buộc?
8. Một thuộc tính **modifyTimestamp** có luôn là token version duy nhất cho mọi thay đổi không?
9. **uSNChanged** của AD có thể so sánh trực tiếp xuyên nhiều DC không? Vì sao?
10. Khi lệnh Modify timeout, ứng dụng có được kết luận server chắc chắn chưa ghi không?
11. Nếu một writer khác bỏ qua quy tắc tăng **appRevision**, liệu optimistic locking custom còn đầy đủ không?
12. Trong integration test, vì sao cần hai kết nối riêng và cùng một expected revision?

**Ghi nhớ:** Spring Data LDAP mang lại mô hình repository nhưng **không tự biến entry LDAP thành JPA entity có @Version**. **DN** là địa chỉ của entry; **entryUUID/objectGUID** là identifier, không phải version. **ModifyRequest** có tính nguyên tử trong phạm vi một entry nhưng **không tự ngăn lost update giữa nhiều request**. Khi chỉ muốn thay một giá trị trong thuộc tính đa trị, dùng **LDAP delta** phù hợp. Khi cần cập nhật có điều kiện thực sự, hãy sử dụng **Assertion Control (RFC 4528)** trên server hỗ trợ, với một token kiểm tra đáng tin cậy và sửa token cùng dữ liệu trong **một ModifyRequest**. Luôn xác minh ACL, TLS, giới hạn replication và hành vi timeout.

## Tài liệu tham khảo

- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): danh sách annotation LDAP và ID dạng DN.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository, LDAP ODM và yêu cầu ID kiểu **javax.naming.Name**.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): hoạt động CRUD và cách cập nhật entry qua ODM.
- [Spring Data Commons — @Version API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Version.html): ý nghĩa annotation ở những store có hỗ trợ optimistic locking.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): ngữ nghĩa ModifyRequest, LDAPResult, DN và thao tác LDAP.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): OID, BER-encoded filter, criticality, atomic test-and-set và result code 122.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp filter và escaping dữ liệu.
- [OpenLDAP — ldapmodify manual](https://man7.org/linux/man-pages/man1/ldapmodify.1.html): cú pháp **-e '!assert=(...)'**.
- [UnboundID LDAP SDK — Using Standard Controls](https://docs.ldap.com/ldap-sdk/docs/getting-started/controls.html): ví dụ **AssertionRequestControl** cùng **ModifyRequest** và cách xử lý result code.
- [Microsoft — Polling for Changes Using uSNChanged](https://learn.microsoft.com/en-us/windows/win32/ad/polling-for-changes-using-usnchanged): uSNChanged thay đổi theo domain controller và không replicate.
- [Microsoft — Replication Behavior in AD DS](https://learn.microsoft.com/en-us/windows/win32/ad/replication-behavior-in-active-directory-domain-services): version skew và độ trễ replication.
