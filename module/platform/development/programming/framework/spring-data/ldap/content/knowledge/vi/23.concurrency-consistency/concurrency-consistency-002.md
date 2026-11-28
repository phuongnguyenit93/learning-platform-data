# Nguy cơ mất cập nhật khi thay thế toàn bộ thuộc tính

Trong ứng dụng **Spring Data LDAP**, nhiều request có thể cùng đọc một entry rồi ghi thay đổi vào LDAP directory. Nếu hai request dựa trên những ảnh chụp dữ liệu cũ và cùng **thay thế toàn bộ giá trị của một thuộc tính**, yêu cầu đến sau có thể ghi đè kết quả của yêu cầu đến trước. Hiện tượng này gọi là **lost update (mất cập nhật)**.

Chủ đề thuộc chương **Đồng thời và nhất quán**. Bài học giải thích lost update ở cấp **thuộc tính LDAP**, đặc biệt là thuộc tính đa trị như **member** của nhóm; so sánh các thao tác **ADD**, **DELETE**, **REPLACE**; chỉ ra rủi ro khi dùng **repository.save(...)** với đối tượng Java cũ; và hướng dẫn lựa chọn cập nhật từng giá trị, kiểm soát xung đột, bảo mật và kiểm thử với directory thật.

## 1. Vì sao LDAP có nguy cơ mất cập nhật?

LDAP tổ chức dữ liệu theo các **entry** nằm trong cây directory. Mỗi entry có một **DN (Distinguished Name)** xác định vị trí, các **objectClass** xác định quy tắc schema và một tập **attribute**. Một số attribute chỉ cho phép một giá trị, trong khi nhiều attribute khác có thể chứa nhiều giá trị.

Ví dụ một nhóm phát triển trong OpenLDAP:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
~~~

Ở đây:

- **cn=developers,ou=groups,dc=example,dc=org** là DN của entry nhóm.
- **groupOfNames** là objectClass nhóm; attribute **member** lưu **DN đầy đủ** của các thành viên.
- **member** là thuộc tính **đa trị**: nhóm có thể có nhiều dòng **member**.
- Theo schema thông dụng của **groupOfNames**, phải có **ít nhất một giá trị member**.

Giả sử hai người quản trị thao tác gần như đồng thời: A muốn thêm **uid=an**, B muốn thêm **uid=binh**. Cả hai đều đọc nhóm lúc nó mới có một thành viên **uid=linh**. Nếu mỗi người ghi lại **toàn bộ danh sách member** theo dữ liệu mình vừa đọc, kết quả có thể chỉ giữ lại thay đổi của người cuối cùng.

Điểm gây lỗi là tổ hợp **đọc dữ liệu → sửa trong bộ nhớ → ghi đè toàn bộ** mà không kiểm tra xem dữ liệu trên server đã đổi trong khoảng thời gian đó hay chưa.

## 2. Tình huống mất cập nhật từng bước

Giả sử ban đầu:

~~~text
LDAP member = {Linh}

Request A đọc: {Linh}
Request B đọc: {Linh}

A bổ sung An vào bản sao:   {Linh, An}
B bổ sung Bình vào bản sao: {Linh, Bình}

A REPLACE member = {Linh, An}
B REPLACE member = {Linh, Bình}

LDAP sau cùng = {Linh, Bình}
Mất thành viên An do A vừa thêm.
~~~

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant L as LDAP server
    participant B as Request B
    Note over L: member = {Linh}
    A->>L: Đọc member
    L-->>A: {Linh}
    B->>L: Đọc member
    L-->>B: {Linh}
    A->>L: REPLACE member = {Linh, An}
    L-->>A: Thành công
    Note over L: member = {Linh, An}
    B->>L: REPLACE member = {Linh, Bình}
    L-->>B: Thành công
    Note over L: member = {Linh, Bình}
    Note over A,B: A đã thành công nhưng An biến mất
~~~

| Thời điểm | Request A nhìn thấy | Request B nhìn thấy | Dữ liệu thực trên server |
| --- | --- | --- | --- |
| T0 | Chưa đọc | Chưa đọc | {Linh} |
| T1 | {Linh} | Chưa đọc | {Linh} |
| T2 | {Linh} | {Linh} | {Linh} |
| T3 | Gửi {Linh, An} | Giữ bản sao {Linh} | {Linh, An} |
| T4 | Đã nhận thành công | Gửi {Linh, Bình} | {Linh, Bình} |

**Cả hai lời gọi ghi có thể trả về thành công**. Máy chủ chỉ biết mỗi yêu cầu REPLACE là hợp lệ theo schema và quyền truy cập; nếu client không cung cấp điều kiện kiểm tra phiên bản, server không có cơ sở để biết danh sách của B là một bản sao cũ. Đây là lỗi nhất quán ở cấp nghiệp vụ dù từng yêu cầu LDAP độc lập đều thành công.

Nếu đảo thứ tự hai lần ghi, thành viên **Bình** có thể bị mất thay vì **An**. Việc xảy ra phụ thuộc thời điểm, nên bug thường khó tái hiện trên máy phát triển ít người dùng.

## 3. Ý nghĩa thực tế của ADD, DELETE và REPLACE trong LDAP Modify

Theo **LDAPv3 Modify** (RFC 4511), client có thể gửi một hoặc nhiều thay đổi cho **một entry**. Ba loại thao tác chính:

| Thao tác LDAP | API JNDI tương ứng | Ý nghĩa khi làm việc với member |
| --- | --- | --- |
| **add** | **DirContext.ADD_ATTRIBUTE** | Thêm một hoặc nhiều **giá trị** vào member, giữ lại các giá trị khác |
| **delete** | **DirContext.REMOVE_ATTRIBUTE** | Xóa các **giá trị được chỉ rõ**; nếu không liệt kê giá trị thì xóa toàn bộ attribute |
| **replace** | **DirContext.REPLACE_ATTRIBUTE** | Thay **toàn bộ tập giá trị** member bằng tập giá trị mới |

Ví dụ với **member = {Linh, An}**:

~~~text
ADD    member: Bình        => {Linh, An, Bình}
DELETE member: An          => {Linh}
REPLACE member: {Bình}     => {Bình}
REPLACE member: {Linh}     => {Linh}
~~~

**Lưu ý quan trọng về tính nguyên tử:** Theo RFC 4511, **toàn bộ danh sách sửa đổi trong một yêu cầu LDAP Modify cho cùng một entry** phải được server xử lý theo thứ tự như **một thao tác nguyên tử**. Nếu yêu cầu có hai sửa đổi và một sửa đổi không hợp lệ, server không được để lại kết quả cập nhật dở dang.

Tuy nhiên, một chuỗi gồm **Search/Lookup** rồi **Modify** là **hai thao tác mạng độc lập**, không được ghép thành một transaction chỉ bởi vì chúng nằm trong cùng một phương thức Java. Giữa hai thao tác đó, client khác có thể thay đổi entry.

Do đó:

> **Modify nguyên tử không đồng nghĩa với read–modify–write an toàn trước cạnh tranh.** Nguy cơ mất cập nhật nằm ở thời gian giữa lúc đọc bản sao và lúc gửi yêu cầu ghi.

Thao tác **REPLACE_ATTRIBUTE** không phải lúc nào cũng sai. Nó đúng khi nghiệp vụ thật sự muốn thay toàn bộ tập giá trị và có chính sách kiểm soát xung đột phù hợp. Vấn đề phát sinh khi **REPLACE** được dùng để mô phỏng một thay đổi nhỏ như “thêm đúng một thành viên”.

## 4. Tái hiện lỗi bằng LDIF và ldapmodify

Phần thực hành giả định server có suffix **dc=example,dc=org**, nhánh **ou=groups**, nhánh **ou=people**, cùng ba người dùng **uid=linh**, **uid=an**, **uid=binh**. Các entry phải tuân thủ schema và tài khoản thử nghiệm phải được ACL cho phép sửa **member**.

Kết nối sử dụng LDAPS với chứng chỉ được xác minh:

~~~bash
export LDAP_URI='ldaps://ldap.example.org:636'
export GROUP_DN='cn=developers,ou=groups,dc=example,dc=org'
export ADMIN_DN='cn=admin,dc=example,dc=org'
~~~

Đây là các giá trị minh họa. Tài khoản **ADMIN_DN** chỉ dùng trong lab, không đưa vào cấu hình ứng dụng production. Các lệnh sử dụng **-W** để nhập mật khẩu tương tác; không đặt password vào dòng lệnh hay LDIF.

### 4.1. Tạo nhóm ban đầu

File **group-initial.ldif**:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
~~~

Nếu nhóm chưa tồn tại, nhập file:

~~~bash
ldapadd -x -H "$LDAP_URI" -D "$ADMIN_DN" -W \
  -f group-initial.ldif
~~~

Nếu đã có nhóm, hãy dùng một directory lab sạch hoặc khôi phục danh sách member phù hợp; **ldapadd** không phải lệnh để ghi đè entry đã tồn tại. Kiểm tra dữ liệu ban đầu:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" -D "$ADMIN_DN" -W \
  -b "$GROUP_DN" -s base '(objectClass=*)' cn member
~~~

### 4.2. Mô phỏng hai bản sao cũ

Giả sử A và B đã đọc cùng trạng thái **{Linh}**. A chuẩn bị file **a-replace.ldif**:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
changetype: modify
replace: member
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
~~~

B chuẩn bị file **b-replace.ldif** từ cùng bản sao ban đầu:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
changetype: modify
replace: member
member: uid=linh,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Chạy lần lượt:

~~~bash
ldapmodify -x -H "$LDAP_URI" -D "$ADMIN_DN" -W \
  -f a-replace.ldif

ldapmodify -x -H "$LDAP_URI" -D "$ADMIN_DN" -W \
  -f b-replace.ldif
~~~

Tìm kiếm lại **member**:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" -D "$ADMIN_DN" -W \
  -b "$GROUP_DN" -s base '(objectClass=*)' member
~~~

Nếu cả hai file được áp dụng thành công theo đúng thứ tự, tập giá trị cuối là **{Linh, Bình}**; **An** không còn. Không cần chạy hai tiến trình thật sự song song để chứng minh lỗi: hai file đại diện cho **hai bản sao đọc ở cùng thời điểm**, còn chuỗi ghi tuần tự chỉ mô phỏng một thứ tự kết thúc có thể xảy ra trong thực tế.

### 4.3. Cách đúng cho thao tác thêm một thành viên

Nếu nghiệp vụ chỉ yêu cầu “thêm An”, gửi **add: member**:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
changetype: modify
add: member
member: uid=an,ou=people,dc=example,dc=org
~~~

Nếu yêu cầu khác thêm Bình với file tương tự, cả hai giá trị có thể được giữ lại dù hai client không đọc trước toàn bộ danh sách. Máy chủ tự áp dụng các thao tác **add** vào trạng thái member đang có khi từng Modify được thực thi.

**Giới hạn:** nếu cùng một thành viên được thêm hai lần, lần thứ hai có thể trả lỗi **attributeOrValueExists (LDAP code 20)**. Client cần phân biệt “đã tồn tại” với lỗi kết nối hoặc quyền truy cập; nếu nghiệp vụ muốn thao tác idempotent, hãy kiểm tra trạng thái và xử lý mã lỗi theo chính sách, không retry vô hạn.

### 4.4. Xóa đúng một giá trị thay vì xóa cả thuộc tính

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
changetype: modify
delete: member
member: uid=an,ou=people,dc=example,dc=org
~~~

Lệnh trên chỉ yêu cầu xóa **member=An**. Trái lại, đoạn sau yêu cầu xóa **toàn bộ attribute member**:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
changetype: modify
delete: member
~~~

Với objectClass **groupOfNames** thông thường, việc xóa thành viên cuối cùng sẽ vi phạm ràng buộc **member là thuộc tính bắt buộc** và server từ chối, thường bằng lỗi **objectClassViolation (65)**. Không nên dựa vào lỗi schema để thay cho kiểm tra điều kiện nghiệp vụ “nhóm không được rỗng”.

## 5. Rủi ro khi thao tác qua Spring Data LDAP Repository

Spring Data LDAP cung cấp mô hình **repository** và ánh xạ entry sang đối tượng Java. Ví dụ:

~~~java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=groups", objectClasses = {"top", "groupOfNames"})
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "member")
    private Set<String> members;

    // Constructors, getters và setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {
    Optional<DirectoryGroup> findByCommonName(String commonName);
}
~~~

Đoạn mã minh họa **@Entry**, **@Id** và **@Attribute** dùng trong ánh xạ Spring LDAP ODM. Khi dùng derived query, tên thuộc tính trong phương thức repository cần phù hợp tên property Java hoặc quy ước mapping thực tế; cần kiểm chứng truy vấn trên phiên bản Spring Data LDAP của dự án.

Trong một service, kiểu mã sau có **nguy cơ** nếu dữ liệu nhóm có thể bị cập nhật bởi nhiều request:

~~~java
// Minh họa luồng nghiệp vụ, lược bỏ xử lý lỗi và getters/setters.
DirectoryGroup group =
    repository.findByCommonName("developers").orElseThrow();

group.getMembers().add(
    "uid=an,ou=people,dc=example,dc=org");

repository.save(group);
~~~

Nếu request khác đã đọc entry trước đó và sau đó cũng lưu một **group object cũ** của riêng nó, các giá trị thành viên đã thay đổi ngoài request có thể bị đưa về trạng thái cũ. Tùy phiên bản và đường đi implementation, Spring LDAP ODM có thể đọc entry hiện tại và tính những **ModificationItem** cần gửi, nhưng việc đó **không tự bảo đảm phát hiện xung đột với snapshot nghiệp vụ** mà request đã tải từ trước.

Không nên kết luận rằng **save(...) luôn phát ra một LDAP REPLACE cho mọi thuộc tính**, vì cách tạo phép sửa phụ thuộc API, mapping và trạng thái entry. Điều quan trọng là: **một Java entity được tải cũ rồi save lại không mặc nhiên có optimistic locking**. Muốn bảo vệ thuộc tính đa trị trước concurrent additions, hãy xem xét thao tác **ADD_ATTRIBUTE** hoặc cơ chế kiểm tra xung đột phía server.

Tình huống với thuộc tính **đơn trị** cũng có thể mất cập nhật: A và B cùng đọc **telephoneNumber=100**, A sửa thành **101**, B sửa thành **102**. Nếu B ghi sau, giá trị thành **102** dù A đã được báo thành công. **ADD_ATTRIBUTE** không giải quyết được xung đột kiểu “hai người muốn đặt hai giá trị khác nhau cho cùng một trường đơn trị”.

## 6. Cập nhật chính xác bằng LdapTemplate và JNDI

Nếu yêu cầu là **thêm đúng một member** vào nhóm, có thể gọi **LdapTemplate.modifyAttributes(...)** với **ModificationItem** ở cấp LDAP, tránh việc dựng lại toàn bộ tập member từ bản sao cũ.

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.springframework.ldap.core.LdapTemplate;

public class MembershipService {
    private final LdapTemplate ldapTemplate;

    public MembershipService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMember(String uid) throws NamingException {
        // ContextSource đã cấu hình base = dc=example,dc=org.
        Name groupRelativeDn =
            new LdapName("cn=developers,ou=groups");

        // Rdn escape giá trị uid theo quy tắc DN.
        LdapName memberFullDn =
            new LdapName("ou=people,dc=example,dc=org");
        memberFullDn.add(new Rdn("uid", uid));

        ModificationItem addMember = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", memberFullDn.toString())
        );

        ldapTemplate.modifyAttributes(
            groupRelativeDn, new ModificationItem[]{addMember});
    }
}
~~~

**Giải thích:**

1. **groupRelativeDn** tương đối với **dc=example,dc=org** đã đặt ở **ContextSource**. Nếu truyền luôn full DN trong mô hình cấu hình này, rất dễ ghép base DN hai lần.
2. **memberFullDn** phải là DN thực của người dùng vì **groupOfNames.member** chứa DN đầy đủ, không chỉ uid.
3. **Rdn("uid", uid)** giúp escape giá trị RDN; ứng dụng vẫn phải kiểm tra quyền thêm thành viên và giới hạn uid thuộc nhánh cho phép.
4. **ADD_ATTRIBUTE** nói trực tiếp với LDAP server rằng chỉ cần thêm một **giá trị** vào member. Hai yêu cầu thêm **hai DN khác nhau** không phải ghi đè toàn bộ set lên nhau.
5. Lời gọi vẫn có thể thất bại vì ACL, schema, DN không tồn tại, thành viên đã có, mạng hoặc các chính sách khác của server.

Để **xóa một thành viên cụ thể**, đổi thao tác thành:

~~~java
ModificationItem removeMember = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("member", memberFullDn.toString())
);
ldapTemplate.modifyAttributes(
    groupRelativeDn, new ModificationItem[]{removeMember});
~~~

Các biến trên thuộc cùng phạm vi phương thức minh họa. **REMOVE_ATTRIBUTE** với một giá trị cụ thể tránh xóa toàn bộ attribute. Nếu giá trị không còn tồn tại, directory có thể trả lỗi **noSuchAttribute (16)**; nếu nghiệp vụ xem “đã vắng mặt” là thành công, cần xử lý riêng theo chính sách idempotency.

### 6.1. JNDI trực tiếp cũng làm được điều tương tự

Khi không dùng Spring LDAP, **DirContext.modifyAttributes(...)** nhận cùng kiểu **ModificationItem[]**:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public final class RawLdapWriter {
    // context do caller cung cấp, đã bind qua kết nối có TLS.
    public static void addMember(DirContext context)
            throws NamingException {
        context.modifyAttributes(
            "cn=developers,ou=groups,dc=example,dc=org",
            new ModificationItem[]{
                new ModificationItem(
                    DirContext.ADD_ATTRIBUTE,
                    new BasicAttribute(
                        "member",
                        "uid=an,ou=people,dc=example,dc=org")
                )
            }
        );
    }
}
~~~

Khi viết ứng dụng thật, bên gọi phải khởi tạo **DirContext** với provider/bind/TLS và đóng context sau khi dùng. Spring LDAP giúp quản lý context và dịch ngoại lệ, nhưng **ngữ nghĩa ADD/DELETE/REPLACE do LDAP protocol và server quy định**.

### 6.2. Một Modify có nhiều thay đổi vẫn nguyên tử

Ví dụ cần thêm thành viên và cập nhật ghi chú như một thao tác logic trên **cùng một entry**:

~~~java
ModificationItem[] modifications = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute(
            "member", "uid=an,ou=people,dc=example,dc=org")),
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute(
            "description", "Team members maintained by HR"))
};

ldapTemplate.modifyAttributes(
    "cn=developers,ou=groups",
    modifications
);
~~~

Theo LDAPv3, danh sách này được áp dụng nguyên tử đối với **một entry**. Tuy nhiên, nếu có request khác đồng thời sửa **description**, thao tác REPLACE ở ví dụ vẫn có nguy cơ ghi đè giá trị của request đó. Việc ghép nhiều thay đổi vào một Modify chỉ bảo đảm tính nguyên tử **bên trong một yêu cầu**, không tự ngăn mất cập nhật **giữa hai yêu cầu**.

## 7. Khi nào ADD/DELETE đủ, khi nào cần kiểm tra xung đột?

Thao tác cập nhật nên biểu diễn **ý định nghiệp vụ nhỏ nhất** thay vì ghi lại toàn bộ dữ liệu hiện nhìn thấy:

| Nhu cầu | Cách ưu tiên | Cần cân nhắc |
| --- | --- | --- |
| Thêm một thành viên vào nhóm | **ADD member=DN** | Có thể gặp lỗi nếu giá trị đã tồn tại |
| Xóa một thành viên | **DELETE member=DN** | Có thể gặp lỗi nếu giá trị không tồn tại; kiểm tra ràng buộc không xóa thành viên cuối |
| Thêm một email dự phòng vào thuộc tính đa trị | **ADD** đúng giá trị | Schema có thể giới hạn số lượng hoặc loại giá trị |
| Cập nhật số điện thoại đơn trị | **REPLACE** có kiểm tra xung đột nếu nhiều nguồn ghi | Hai giá trị khác nhau không thể được giữ đồng thời trong một thuộc tính đơn trị |
| Thay **toàn bộ danh sách thành viên** theo quyết định quản trị | **REPLACE** có điều kiện phiên bản / chính sách khóa | Thay thế phải dựa trên snapshot được xác minh còn hiệu lực |
| Sửa nhiều thuộc tính trong một entry như một lệnh | **Một LDAP Modify** chứa nhiều phần tử | Nguyên tử trong request nhưng không bảo vệ khỏi request khác |
| Đồng bộ hàng loạt nhiều entry | Thiết kế idempotency, phân vùng ghi và cơ chế phối hợp | LDAP Modify tiêu chuẩn không là transaction ACID xuyên nhiều entry |

Không có giải pháp duy nhất cho mọi loại cạnh tranh:

- **ADD/DELETE theo giá trị** đặc biệt hiệu quả khi các yêu cầu độc lập thêm/xóa các giá trị khác nhau của thuộc tính đa trị.
- **Kiểm tra xung đột phía server** cần thiết khi ứng dụng thay toàn bộ tập giá trị hoặc hai bên chỉnh **cùng một giá trị**.
- **Tuần tự hóa** các thay đổi theo một DN ở tầng ứng dụng có thể hữu ích nếu mọi writer thực sự đi qua cùng cơ chế phối hợp. Lock trong một JVM không bảo vệ được các instance khác hay công cụ quản trị LDAP bên ngoài.

## 8. Optimistic concurrency: kiểm tra điều kiện ngay trên server

Đối với thao tác bắt buộc **REPLACE toàn bộ attribute**, cách bền vững hơn là thực hiện cập nhật có **điều kiện**: “chỉ ghi nếu entry chưa thay đổi kể từ lúc tôi đọc”.

LDAP có **Assertion Control** được mô tả trong **RFC 4528**, với OID **1.3.6.1.1.12**. Khi server hỗ trợ và client gửi control phù hợp cùng yêu cầu Modify, server kiểm tra điều kiện trước khi sửa entry như **một thao tác nguyên tử**. Nếu điều kiện sai, server trả **assertionFailed (LDAP result code 122)** thay vì áp dụng thay đổi.

~~~mermaid
flowchart TD
    A["Đọc member cùng phiên bản V"] --> B["Chuẩn bị danh sách mới"]
    B --> C["Gửi Modify + Assertion Control: phiên bản vẫn là V?"]
    C --> D{"Điều kiện khớp ở server?"}
    D -->|Có| E["Áp dụng REPLACE và đổi phiên bản nguyên tử"]
    D -->|Không| F["assertionFailed 122, không ghi"]
    F --> G["Đọc lại, hợp nhất/đưa người dùng giải quyết"]
~~~

### 8.1. Ví dụ về cơ chế phiên bản ở mức thiết kế

Giả sử tổ chức đã định nghĩa trong schema một thuộc tính riêng **appRevision**, có ACL cho phép đọc và chỉ cho phép ứng dụng quản lý việc ghi phiên bản:

~~~text
T0: đọc entry với appRevision = 8
T1: người khác cập nhật member và appRevision = 9
T2: yêu cầu của ta:
      Assertion: (appRevision=8)
      Modify:
        REPLACE member = tập giá trị dự định
        REPLACE appRevision = 9
T3: server thấy appRevision = 9 -> từ chối, không sửa gì
T4: client nạp lại dữ liệu và giải quyết xung đột
~~~

Nếu không có người khác cập nhật giữa T0 và T2, server cho phép Modify và thay member cùng revision trong **một yêu cầu nguyên tử**. Hai writer cùng đọc revision 8 không thể cùng thành công khi cả hai yêu cầu đều kiểm tra 8 và thay revision sang 9 trên cùng server tuân thủ Assertion Control.

**appRevision chỉ là tên thuộc tính minh họa**, không phải thuộc tính tiêu chuẩn có sẵn trong mọi LDAP server. Muốn triển khai thực tế, cần thiết kế schema, sinh giá trị phiên bản theo quy tắc nhất quán, ACL ngăn sửa revision ngoài quy trình và kiểm thử support của server/client. Không tự thêm tên thuộc tính chưa được schema cho phép vào entry.

Để khảo sát server có quảng bá Assertion Control hay không:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -b "" -s base '(objectClass=*)' supportedControl
~~~

Tìm giá trị **1.3.6.1.1.12** trong **supportedControl**. Một số server chỉ công bố control theo quyền của client hoặc cấu hình; phải xác nhận trên server mục tiêu. Khi yêu cầu tính nhất quán nghiêm ngặt, **criticality** của Assertion Control nên được đặt phù hợp để không âm thầm thực thi cập nhật khi server không hỗ trợ control.

**Không dùng read → ldapcompare → modify tách rời** để thay thế cơ chế này: giữa lần so sánh và Modify vẫn có một cửa sổ race condition.

### 8.2. Có nên dùng modifyTimestamp hoặc entryUUID làm version?

- **entryUUID** thường dùng làm định danh ổn định của entry trong một số server; **không phải phiên bản thay đổi**. Nó không giúp phát hiện một entry đã bị chỉnh sửa sau khi đọc.
- **modifyTimestamp** là operational attribute phản ánh thời điểm cập nhật theo quy định của server. Tuy nhiên, nó có giới hạn về độ phân giải, hành vi triển khai, quyền đọc và tình huống replication; không nên coi là cơ chế optimistic locking đủ mạnh nếu chưa kiểm chứng.
- **@Id** trong Spring Data LDAP lưu DN hoặc tên entry, **không phải khóa phiên bản**. Không suy ra rằng repository **save(...)** có cơ chế **@Version** tương tự Spring Data JPA; chỉ sử dụng khả năng concurrency đã được thư viện và directory xác nhận.

Với workload nhạy cảm về xung đột, cần chọn một token thay đổi thực sự phù hợp, kiểm tra ở phía server và xác định rõ điều gì xảy ra khi nhận **assertionFailed**. Không retry nguyên payload REPLACE cũ một cách mù quáng, vì lệnh retry sẽ lặp lại mục tiêu ghi đè dữ liệu mới.

## 9. Những tình huống thực tế cần đặc biệt chú ý

### 9.1. Giao diện quản trị có biểu mẫu chỉnh sửa cả entry

Người quản trị A mở form cập nhật email lúc 09:00; người quản trị B sửa số điện thoại lúc 09:01; A nhấn Lưu lúc 09:03. Nếu form gửi lại toàn bộ dữ liệu cũ và backend đồng bộ toàn bộ object sang directory, số điện thoại có thể bị khôi phục về giá trị cũ.

Giải pháp: backend xác định **field thực sự thay đổi** và áp dụng Modify chỉ cho các field đó; nếu hai bên sửa cùng field, sử dụng cơ chế phát hiện xung đột hoặc chính sách ghi cuối cùng có chủ đích. Không dựa vào so sánh snapshot cũ ở UI để bảo đảm an toàn trước concurrent writes.

### 9.2. Đồng bộ thành viên nhóm từ hai hệ thống

Hệ thống nhân sự thêm người từ phòng ban, hệ thống dự án thêm người theo assignment. Nếu mỗi hệ thống định kỳ **REPLACE toàn bộ member** từ dữ liệu riêng, hai hệ thống có thể liên tục xóa kết quả của nhau. Nên xác định **chủ sở hữu dữ liệu** theo tập giá trị hoặc nhóm riêng, sử dụng delta **ADD/DELETE** khi phù hợp, hay đồng bộ qua một nguồn điều phối duy nhất.

### 9.3. Nhiều instance ứng dụng

Hai pod Spring Boot có thể cùng đọc một entry và lưu gần nhau. **synchronized**, **ReentrantLock** hoặc cache trong một instance không phối hợp được tất cả instance. Cơ chế tại LDAP server như Modify theo giá trị và Assertion Control có phạm vi bảo vệ sát nơi dữ liệu được cập nhật hơn.

### 9.4. Directory có nhiều server hoặc replication

Khi client đọc từ replica A rồi ghi sang server B, có thể gặp dữ liệu chưa đồng bộ. Replication delay, topology đa master và chính sách giải quyết xung đột của từng sản phẩm directory **khác** bài toán lost update trong một server. Muốn bảo đảm nhất quán ở phạm vi nhiều server, cần kiểm chứng khả năng hỗ trợ của chính kiến trúc directory, chọn endpoint đọc/ghi phù hợp và kiểm thử lúc replication chậm.

## 10. Cách thiết kế thao tác cập nhật an toàn

Một quy trình tham khảo cho service Spring Data LDAP:

1. **Định danh đúng entry:** xác định DN, base DN tương đối với **ContextSource** và objectClass theo schema; không xây DN từ chuỗi người dùng thiếu escaping.
2. **Diễn đạt đúng ý định:** “thêm thành viên X” là ADD, “xóa thành viên X” là DELETE, “đặt lại danh sách” mới là REPLACE.
3. **Giới hạn phạm vi sửa:** chỉ gửi các attribute/giá trị cần đổi. Với LDAP multi-valued attribute, tránh gửi snapshot cũ nếu không có kiểm tra xung đột.
4. **Kiểm tra điều kiện nghiệp vụ:** quyền thêm người, nhóm tồn tại, người dùng thuộc nhánh được chấp nhận, tránh nhóm rỗng và các quy tắc nghiệp vụ khác.
5. **Chọn bảo vệ cạnh tranh:** delta operation đủ cho thay đổi độc lập; với thay toàn bộ set cần server-side compare-and-modify hoặc cơ chế phối hợp writer tương đương.
6. **Phân biệt lỗi:** attributeOrValueExists (20), noSuchAttribute (16), constraintViolation (19), insufficientAccessRights (50), objectClassViolation (65), assertionFailed (122) và lỗi kết nối có cách xử lý khác nhau.
7. **Xác minh kết quả:** khi cần độ chắc chắn cao, đọc lại entry từ endpoint có bảo đảm nhất quán phù hợp; không xem phản hồi “success” của một REPLACE là bằng chứng không có cập nhật khác bị mất.
8. **Giữ an toàn:** dùng LDAPS/StartTLS có xác minh chứng chỉ, bind DN có quyền tối thiểu, filter có tham số, ghi log đủ để đối chiếu request nhưng không làm lộ mật khẩu hoặc dữ liệu nhạy cảm.

### 10.1. Bảng lựa chọn nhanh

| Câu hỏi | Nếu câu trả lời là “có” | Hướng xử lý |
| --- | --- | --- |
| Chỉ muốn thêm một phần tử vào thuộc tính đa trị? | Có | **ADD_ATTRIBUTE** trực tiếp |
| Chỉ muốn xóa một phần tử cụ thể? | Có | **REMOVE_ATTRIBUTE** kèm giá trị |
| Muốn ghi đè toàn bộ tập giá trị dựa trên dữ liệu vừa đọc? | Có | **REPLACE** kèm kiểm tra phiên bản/điều kiện ở server |
| Cần cập nhật nhiều thuộc tính của cùng entry cùng lúc? | Có | Đặt nhiều phần tử trong **một Modify request** |
| Cần cập nhật nhiều entry như một transaction? | Có | Thiết kế workflow/reconciliation riêng; không kỳ vọng một Modify bao trùm các entry |
| Có nhiều instance hoặc nhiều nguồn ghi? | Có | Tránh lock cục bộ; kiểm chứng phối hợp tại server và chính sách replication |

## 11. Kiểm thử mất cập nhật với LDAP directory

Kiểm thử liên quan concurrency phải xác nhận **trạng thái sau cùng trên server**, không chỉ xác nhận hai phương thức Java không ném exception.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Hai bản sao cũ dùng REPLACE | Đọc trạng thái ban đầu một lần cho A và B, sau đó ghi hai danh sách khác nhau theo thứ tự A → B | Mô phỏng thấy mất cập nhật của A |
| Hai request ADD khác giá trị | Reset nhóm về {Linh}, cho A thêm An và B thêm Bình bằng ADD | Cả An và Bình đều còn |
| ADD trùng giá trị | Gửi ADD An hai lần | Lần hai bị báo đã tồn tại hoặc được service xử lý idempotent đúng chính sách |
| DELETE đúng một giá trị | Nhóm có {Linh, An, Bình}, xóa An | Linh và Bình vẫn còn |
| REPLACE có assertion | Hai request cùng đọc revision 8, cùng gửi Modify kiểm tra revision=8 | Tối đa một thành công; request còn lại nhận conflict |
| Xóa thành viên cuối | Với groupOfNames chỉ còn một member, yêu cầu xóa giá trị đó | Server chặn nếu kết quả vi phạm schema |
| Thiếu quyền ghi | Bind bằng tài khoản chỉ đọc rồi MODIFY member | Server từ chối, dữ liệu không đổi |
| Replication delay | Đọc/ghi qua nhiều server trong topology thử nghiệm | Ghi nhận hành vi nhất quán thực tế, không giả định như single-server |

Để kiểm thử xác định, không cần tạo hàng trăm thread hoặc chèn **sleep** ngẫu nhiên. Có thể tạo trước **hai bản sao dữ liệu giống nhau**, kiểm soát thứ tự lệnh ghi và kiểm tra trạng thái LDAP sau mỗi lệnh. Sau đó bổ sung integration test có **barrier** đồng bộ hai writer, thu thập kết quả của từng request để kiểm tra hành vi dưới áp lực cạnh tranh thực.

Với Spring, test dùng mock **LdapRepository** chỉ kiểm tra logic service và không thể chứng minh LDAP Modify có đúng semantics hoặc server có hỗ trợ Assertion Control. Cần integration test trên **directory thực/nhúng** có schema, ACL và các control phù hợp. Nếu môi trường dùng OpenLDAP production, nên có kiểm thử OpenLDAP tương ứng vì server nhúng khác có thể xử lý control và quyền truy cập khác.

Ví dụ tiêu chí đánh giá hai lệnh ADD:

~~~text
Ban đầu:       member = {Linh}
Thực hiện A:   ADD member An
Thực hiện B:   ADD member Bình
Kỳ vọng:       member = {Linh, An, Bình}
Không yêu cầu: thứ tự liệt kê các giá trị member phải cố định
~~~

Đa số LDAP attributes đa trị không bảo đảm thứ tự có ý nghĩa. Trong test, so sánh **tập giá trị**, không so sánh thứ tự các dòng **member** từ kết quả ldapsearch.

## 12. Sai lầm thường gặp và câu hỏi ôn tập

**Sai lầm 1 — “LDAP Modify là atomic, vậy chắc chắn không mất cập nhật.”** Một Modify có tính nguyên tử trong phạm vi entry được sửa, nhưng hai Modify độc lập vẫn có thể ghi đè kết quả của nhau.

**Sai lầm 2 — “Trước khi REPLACE, đọc lại entry lần nữa là đủ.”** Một writer khác vẫn có thể ghi sau lần đọc cuối cùng và trước lệnh Modify. Đây là lỗi **time-of-check to time-of-use**.

**Sai lầm 3 — “Repository.save(...) luôn bảo vệ được concurrency như một ORM có @Version.”** Không được tự suy diễn từ tên method. Cần xem đúng phiên bản, request LDAP thực gửi và cơ chế phát hiện xung đột có được cấu hình hay không.

**Sai lầm 4 — “Muốn bỏ một member thì dùng delete member không kèm giá trị.”** Cách đó xóa toàn bộ attribute; muốn bỏ một giá trị phải chỉ rõ DN cần xóa.

**Sai lầm 5 — “Thành công nghĩa là không có vấn đề nhất quán.”** Lost update có thể xảy ra dù cả hai yêu cầu đều nhận thành công và LDAP vẫn đúng schema.

**Câu hỏi tự kiểm tra:**

1. Tại sao hai người cùng thêm thành viên bằng REPLACE có thể dẫn đến lost update?
2. Khác biệt giữa nguyên tử của **một Modify request** và chuỗi **read–modify–write** là gì?
3. Khi nào nên dùng **ADD_ATTRIBUTE**, **REMOVE_ATTRIBUTE**, **REPLACE_ATTRIBUTE**?
4. Nếu hai người cùng sửa thuộc tính **telephoneNumber** đơn trị, ADD có giải quyết xung đột không?
5. Vì sao **entryUUID** và **DN** không tự đóng vai trò phiên bản của entry?
6. Assertion Control giúp giải quyết cửa sổ race condition như thế nào? Client cần làm gì khi nhận **assertionFailed 122**?
7. Tại sao cần integration test với LDAP server thay vì chỉ mock repository?

## 13. Tổng kết và tài liệu tham khảo

**Nguy cơ mất cập nhật khi thay thế toàn bộ thuộc tính** xuất hiện khi nhiều client đọc các bản sao cũ và gửi **REPLACE** cho cùng một thuộc tính LDAP. Với thuộc tính đa trị như **groupOfNames.member**, cách sửa tốt hơn cho thay đổi độc lập thường là **ADD/DELETE đúng giá trị**. Với yêu cầu thay cả tập dữ liệu hoặc sửa cùng một thuộc tính đơn trị, cần phát hiện xung đột **ngay tại server**, chẳng hạn qua LDAP Assertion Control nếu directory hỗ trợ. Cần phân biệt tính nguyên tử của từng yêu cầu Modify với tính nhất quán của toàn bộ quy trình nghiệp vụ.

Tài liệu đối chiếu:

- [RFC 4511 — LDAPv3 Modify Operation](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.6): ngữ nghĩa add/delete/replace và tính nguyên tử của các sửa đổi trong một request.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): điều kiện thực thi thao tác, OID **1.3.6.1.1.12** và kết quả **assertionFailed**.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): các overload **modifyAttributes(...)**, **lookupContext(...)** và thao tác ODM.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): cập nhật attribute qua LDAP Modify và các API hỗ trợ.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): mô hình repository và ánh xạ object sang LDAP entry.
