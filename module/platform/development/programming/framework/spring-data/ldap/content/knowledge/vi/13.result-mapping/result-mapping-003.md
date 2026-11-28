# Đọc thuộc tính một giá trị hoặc nhiều giá trị

Trong **Spring Data LDAP**, kết quả tìm kiếm là những **entry** của LDAP directory, được ánh xạ thành đối tượng Java bằng **repository** và cơ chế Object-Directory Mapping (ODM) của Spring LDAP. Không phải mọi thuộc tính LDAP đều tương ứng với một chuỗi đơn: cùng một entry có thể có một giá trị **uid**, nhiều giá trị **mail**, nhiều **objectClass** hoặc một tập **member** chứa DN của các thành viên nhóm. Nếu chỉ đọc giá trị đầu tiên, ứng dụng có thể làm mất dữ liệu hoặc hiểu sai kết quả truy vấn.

Bài học thuộc chương **Ánh xạ kết quả**, tập trung vào cách phân biệt thuộc tính một giá trị và đa trị; cách đọc an toàn bằng JNDI **Attributes/Attribute**, Spring LDAP **AttributesMapper/DirContextOperations**; và cách ánh xạ sang **String**, **List**, **Set** hoặc **Set<Name>** trong Spring Data LDAP. Các ví dụ dùng cây LDAP minh họa, giải thích trường hợp thuộc tính thiếu, giới hạn ACL, kiểu nhị phân, thứ tự giá trị và kiểm thử với directory thật.

## 1. Thuộc tính LDAP là gì?

LDAP tổ chức dữ liệu thành một cây entry gọi là **Directory Information Tree (DIT)**. Mỗi entry được nhận diện bằng **Distinguished Name (DN)** và chứa các cặp tên thuộc tính/giá trị. Thuộc tính thuộc schema LDAP, không phải cột SQL.

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=an
└── ou=groups
    └── cn=developers
~~~

Ví dụ entry nhân viên ở dạng **LDIF**:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
mail: linh.work@example.org
~~~

Và entry nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
~~~

Ở dữ liệu trên, entry người dùng có **một giá trị uid** và **hai giá trị mail**; entry nhóm có **hai giá trị member**. **objectClass** cũng là thuộc tính có nhiều giá trị. Thuộc tính **member** của **groupOfNames** chứa các **DN đầy đủ**, khác với một mã uid đơn giản.

### 1.1. Phân biệt “đang có một giá trị” với “SINGLE-VALUE”

Một thuộc tính chỉ có một giá trị trong entry hiện tại **không chứng minh schema bắt buộc nó là thuộc tính đơn trị**. Schema có thể cho phép thêm giá trị khác. Ngược lại, thuộc tính được khai báo **SINGLE-VALUE** trong schema chỉ được lưu tối đa một giá trị hợp lệ trên entry.

| Trường hợp | Diễn giải | Biểu diễn trong Java |
| --- | --- | --- |
| Một giá trị đang hiện diện | Ví dụ **uid: linh**; cần xem schema trước khi kết luận có được thêm giá trị hay không | **String**, nếu nghiệp vụ chỉ cần một |
| Nhiều giá trị đang hiện diện | Ví dụ hai dòng **mail** của một người | **List<String>**, **Set<String>** hoặc mảng |
| Nhiều DN | Hai dòng **member** của nhóm | **Set<Name>**, **Set<String>** hoặc danh sách DN đã parse |
| Thuộc tính không trả về | Không thấy **mail** trong kết quả search | Có thể là thiếu dữ liệu, không yêu cầu, bị ACL chặn hoặc là lỗi mapping |
| Giá trị nhị phân | Ví dụ **jpegPhoto** | **byte[]**, không ép về **String** |

**Schema** quy định cú pháp, matching rule, objectClass nào được phép dùng thuộc tính, các thuộc tính **MUST/MAY** và tính đơn trị/đa trị. **ACL** quyết định danh tính bind được phép search/read thuộc tính nào. Vì thế việc đọc ra một danh sách không chỉ phụ thuộc Java class mà còn phụ thuộc cấu hình LDAP server.

## 2. Ba tầng ánh xạ kết quả trong ứng dụng Spring

~~~mermaid
flowchart TD
    A["LDAP SearchResult: DN + attributes"] --> B["JNDI Attributes / Attribute"]
    B --> C["Spring LDAP: AttributesMapper, ContextMapper, DirContextOperations"]
    C --> D["Spring Data LDAP: @Entry, @Attribute, @Id"]
    D --> E["Java domain object: String, Set<String>, Set<Name>"]
    F["Schema + ACL + requested attributes"] -. "Quyết định giá trị trả về" .-> A
~~~

| Tầng | API thường gặp | Mục đích |
| --- | --- | --- |
| **JNDI** | **javax.naming.directory.Attributes**, **Attribute**, **NamingEnumeration** | Đọc tên thuộc tính, giá trị đơn hoặc liệt kê tất cả giá trị |
| **Spring LDAP** | **LdapTemplate.search(...)** với **AttributesMapper** | Tự kiểm soát cách chuyển **Attributes** thành DTO |
| **Spring LDAP** | **ContextMapper**, **DirContextOperations** | Đọc thuộc tính bằng helper và đồng thời lấy DN |
| **Spring Data LDAP / ODM** | **@Entry**, **@Attribute**, **@Id**, **LdapRepository** | Ánh xạ nhiều entry thành các entity Java qua repository |

**JNDI** nằm trong JDK (module **java.naming**). Kể cả với Spring Framework 6+ và Spring Boot mới, package của nó vẫn là **javax.naming**, không phải **jakarta.naming**. Các annotation ODM đúng thuộc **org.springframework.ldap.odm.annotations**, dù dự án cũng có thể dùng những module Spring Data khác.

## 3. Đọc thuộc tính bằng JNDI: Attributes và Attribute

Với một entry đã được tìm thấy bằng **DirContext.search(...)**, **SearchResult.getAttributes()** cung cấp một đối tượng **Attributes**. Mỗi thuộc tính bên trong là **Attribute**:

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

// 'result' là SearchResult lấy được từ một truy vấn JNDI.
Attributes attributes = result.getAttributes();
Attribute uid = attributes.get("uid");
Attribute mails = attributes.get("mail");
~~~

Phân biệt:

- **Attributes.get("uid")** trả một **Attribute** hoặc **null** nếu không có tên đó trong tập thuộc tính được trả về.
- **Attribute.get()** trả một trong các giá trị của thuộc tính; với attribute đa trị không có thứ tự, đây **không phải “giá trị chính”**.
- **Attribute.size()** đếm số giá trị của một attribute; **Attributes.size()** đếm số **thuộc tính** có trong tập.
- **Attribute.getAll()** trả **NamingEnumeration<?>** chứa các giá trị; **Attributes.getAll()** lại là enumeration của các **Attribute**.
- **Attribute.isOrdered()** mô tả tính thứ tự theo representation của attribute. Nhiều thuộc tính LDAP phổ biến không có thứ tự có ý nghĩa.

### 3.1. Hàm đọc một giá trị String

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class LdapValues {
    private LdapValues() {}

    public static String firstString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }

        Object value = attribute.get();
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                "LDAP attribute is not textual: " + name);
        }
        return text;
    }
}
~~~

Ví dụ:

~~~java
String uid = LdapValues.firstString(attributes, "uid");
String oneMail = LdapValues.firstString(attributes, "mail");
~~~

Lấy **uid** theo cách này hợp lý nếu nghiệp vụ mong muốn đúng một giá trị. Với **mail** có hai giá trị, **oneMail** chỉ nhận một giá trị và làm mất giá trị còn lại ở phía Java. Nếu thật sự cần một “email chính”, ứng dụng phải có quy tắc nghiệp vụ riêng hoặc thuộc tính chuyên dụng; không được mặc nhiên coi giá trị đầu tiên của **mail** là địa chỉ chính.

Hàm trên chủ động kiểm tra kiểu trước khi cast. Với thuộc tính nhị phân, JNDI có thể trả **byte[]**; ép thẳng thành **String** gây lỗi kiểu dữ liệu hoặc làm hỏng nội dung.

### 3.2. Hàm đọc **tất cả** giá trị String

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class MultiValueReader {
    private MultiValueReader() {}

    public static List<String> allStrings(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            return List.of();
        }

        List<String> values = new ArrayList<>();
        NamingEnumeration<?> cursor = attribute.getAll();
        try {
            while (cursor.hasMore()) {
                Object value = cursor.next();
                if (!(value instanceof String text)) {
                    throw new IllegalArgumentException(
                        "LDAP attribute is not textual: " + name);
                }
                values.add(text);
            }
        } finally {
            cursor.close();
        }
        return List.copyOf(values);
    }
}
~~~

Ví dụ:

~~~java
List<String> emails = MultiValueReader.allStrings(attributes, "mail");
// Có thể chứa: ["linh@example.org", "linh.work@example.org"].
// Không dựa vào thứ tự của hai phần tử.
~~~

**NamingEnumeration** có thể giữ tài nguyên và nên được đóng trong **finally**. **List.copyOf(...)** trả bản sao không thay đổi được từ các giá trị đọc, tránh vô tình chỉnh sửa một danh sách trong DTO. Mã dùng **Java 17+** cho pattern matching của **instanceof**; với Java cũ có thể dùng cast sau khi kiểm tra kiểu.

Hàm trả danh sách rỗng nếu attribute vắng trong **Attributes**. Điều đó chỉ có nghĩa **không quan sát được giá trị trong kết quả đã nhận**, không chứng minh entry ở directory tuyệt đối không có attribute này: search có thể không yêu cầu nó hoặc ACL có thể ẩn nó.

### 3.3. Đọc số lượng và phát hiện trường hợp bất thường

Một trường nghiệp vụ yêu cầu đúng một giá trị có thể được kiểm tra:

~~~java
Attribute attr = attributes.get("uid");
if (attr == null || attr.size() != 1) {
    throw new IllegalStateException(
        "Expected exactly one visible uid value");
}
String uid = (String) attr.get();
~~~

Đây là **kiểm tra dữ liệu quan sát được** trong ứng dụng. Kiểu thuộc tính một giá trị hay nhiều giá trị ở cấp LDAP vẫn do **schema của server** quyết định. Nếu thuộc tính cần thiết bị ACL ẩn, ứng dụng nên báo lỗi dữ liệu/quyền có ngữ cảnh rõ ràng thay vì tự điền một giá trị giả.

## 4. LdapTemplate với AttributesMapper: biến Attributes thành DTO

**AttributesMapper<T>** phù hợp khi ứng dụng chỉ cần một vài thuộc tính và muốn kiểm soát chính xác cách tạo DTO. Dưới đây là ví dụ tìm người dùng theo uid và thu thập **tất cả** địa chỉ email.

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record PersonContact(
    String uid,
    String commonName,
    List<String> emails
) {}

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonContact> findByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .where("uid").is(uid),
            (AttributesMapper<PersonContact>) attrs ->
                new PersonContact(
                    LdapValues.firstString(attrs, "uid"),
                    LdapValues.firstString(attrs, "cn"),
                    MultiValueReader.allStrings(attrs, "mail")
                )
        );
    }
}
~~~

Giả định **ContextSource** đã đặt base **dc=example,dc=org**, nên **query().base("ou=people")** là DN tương đối. **query().where("uid").is(uid)** xây dựng filter với giá trị được escape đúng cách; không nối trực tiếp input người dùng vào chuỗi LDAP filter.

Trong ví dụ này, **LdapTemplate.search(...)** trả về danh sách DTO, kể cả khi chỉ kỳ vọng một entry. Đừng mặc định uid là duy nhất trong toàn bộ directory: tính duy nhất của DN, phạm vi tìm kiếm và chính sách uid là những vấn đề khác nhau. Nếu nghiệp vụ yêu cầu đúng một kết quả, cần xử lý rõ **0**, **1** hoặc **nhiều hơn 1** entry.

**Lưu ý:** Các khối **LdapValues**, **MultiValueReader**, **PersonContact**, **PersonLookupService** minh họa các type trong cùng package Java; khi đưa vào project, nên tách những top-level type đó vào file phù hợp hoặc tổ chức thành nested class theo quy ước dự án.

### 4.1. Khi nào dùng AttributesMapper?

| Tình huống | AttributesMapper có phù hợp? |
| --- | --- |
| API chỉ cần uid, cn và tất cả mail | Rất phù hợp: ánh xạ DTO gọn, dễ kiểm soát |
| Muốn xử lý thiếu thuộc tính theo quy tắc nghiệp vụ | Phù hợp: tự quyết định giá trị thay thế hay lỗi |
| Cần thao tác với DN của kết quả | Dùng **ContextMapper** để có thêm thông tin context |
| Muốn thao tác CRUD trên domain entity với repository | Cân nhắc ODM và Spring Data LDAP |
| Thuộc tính nhị phân hoặc cần chuyển đổi chuyên biệt | Có thể dùng mapper tùy chỉnh kiểm tra kiểu rõ ràng |

## 5. ContextMapper và DirContextOperations: đọc một hoặc nhiều chuỗi

**ContextMapper<T>** nhận context của entry, thường được biểu diễn dưới dạng **DirContextOperations**. API này bổ sung các helper thuận tiện:

| API | Kết quả và giới hạn |
| --- | --- |
| **getStringAttribute("cn")** | Một **String**; nếu có nhiều giá trị chỉ trả giá trị đầu tiên, không bảo đảm đó là giá trị chính |
| **getStringAttributes("mail")** | Mảng **String[]** chứa toàn bộ giá trị; trả **null** nếu attribute không hiện diện |
| **getObjectAttribute("jpegPhoto")** | Một giá trị kiểu **Object**, cần xử lý đúng kiểu |
| **getObjectAttributes("jpegPhoto")** | Mảng các giá trị Object, hoặc **null** nếu attribute không tồn tại |
| **getAttributeSortedStringSet("mail")** | Tập String đã sắp xếp cho mục đích trình bày/so sánh; **null** nếu attribute thiếu |
| **getDn()** | DN của entry **tương đối với base path** do ContextSource quản lý |

Ví dụ dùng ContextMapper để nhận tên nhóm và toàn bộ DN thành viên:

~~~java
import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record GroupView(
    String relativeDn,
    String commonName,
    List<String> memberDns
) {}

public class GroupLookupService {
    private final LdapTemplate ldapTemplate;

    public GroupLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<GroupView> findDevelopers() {
        return ldapTemplate.search(
            query().base("ou=groups")
                   .where("cn").is("developers"),
            (ContextMapper<GroupView>) context -> {
                DirContextOperations entry =
                    (DirContextOperations) context;
                String[] rawMembers = entry.getStringAttributes("member");
                List<String> members = rawMembers == null
                    ? List.of()
                    : List.copyOf(Arrays.asList(rawMembers));

                return new GroupView(
                    entry.getDn().toString(),
                    entry.getStringAttribute("cn"),
                    members
                );
            }
        );
    }
}
~~~

**GroupView.memberDns** giữ toàn bộ giá trị **member**, còn **getStringAttribute("cn")** phù hợp khi một entry nhóm được thiết kế có một tên cn cần hiển thị. Vì LDAP group membership về bản chất là tập DN, không nên dùng vị trí trong mảng để suy ra mức ưu tiên thành viên. **getDn()** thường là DN tương đối theo ContextSource, trong khi giá trị **member** chứa DN đầy đủ của các entry người dùng.

**Cảnh báo về null:** Theo API Spring LDAP, **getStringAttributes(...)** có thể trả **null** khi attribute vắng mặt; kiểm tra null trước khi tạo List/Set. Nếu bạn muốn phân biệt “attribute vắng” và “attribute có mặt nhưng không có giá trị trong biểu diễn Java”, hãy kiểm tra thêm **entry.attributeExists("mail")**. Tuy nhiên, LDAP server thường không trả một thuộc tính trống trong kết quả search.

## 6. Ánh xạ repository: String và Set<String>

Đối với ứng dụng sử dụng **Spring Data LDAP Repository**, Spring LDAP ODM cho phép khai báo mapping ngay trên entity:

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

    // Constructor không tham số, getters và setters được lược bỏ.
}
~~~

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    List<DirectoryPerson> findByUid(String uid);
}
~~~

Trong entity này:

- **@Id** đánh dấu **DN** của entry; dùng **javax.naming.Name**, không phải số ID tự tăng. Đây là annotation **org.springframework.ldap.odm.annotations.Id**.
- **@Attribute(name = "uid")** đưa giá trị LDAP **uid** vào Java **String**.
- **@Attribute(name = "mail")** đưa nhiều giá trị LDAP **mail** vào **Set<String>**, biểu diễn một tập email và tránh suy diễn thứ tự.
- **@Entry** khai báo nhánh **ou=people** tương đối với base của **ContextSource** và các objectClass phù hợp với entry nhân sự.

Khi một entry chỉ có một mail, **emails** có thể có một phần tử; khi có nhiều mail, **emails** có thể chứa nhiều phần tử. **Set** hữu ích khi nghiệp vụ coi giá trị như tập không thứ tự. Nếu API trả JSON và cần thứ tự ổn định để hiển thị hoặc kiểm thử, hãy sắp xếp **ở tầng trình bày** theo quy tắc rõ ràng, thay vì giả định server bảo đảm thứ tự.

**Không lấy giá trị đầu tiên từ Set** để xem đó là email chính. Tập hợp không có khái niệm “phần tử chính”. Nếu yêu cầu chỉ lưu một email chính, hãy thiết kế thuộc tính/logic riêng dựa trên schema và quy tắc nghiệp vụ.

### 6.1. Thiếu dữ liệu và ràng buộc domain

Một số thuộc tính có thể thiếu hoặc bị ACL chặn. Tùy mapper và trạng thái entity, trường Java tương ứng có thể là **null** hoặc tập rỗng. Phần mềm cần quy định rõ:

1. Thuộc tính nào **bắt buộc theo nghiệp vụ** dù schema LDAP chỉ đánh dấu MAY.
2. Trường nào được phép thiếu và API trả về **null**, danh sách rỗng hoặc không xuất hiện.
3. Khi nào phải báo lỗi **quyền đọc** hoặc lỗi **dữ liệu không hợp lệ**.
4. Có cần giữ bản sao bất biến ở DTO để không vô tình thay đổi entity quản lý hay không.

**Đừng đồng nhất “không đọc thấy attribute” với “attribute không tồn tại trên server”.** Nếu thao tác cập nhật lại entity khi chưa đọc đủ thông tin, có nguy cơ ghi đè hoặc xóa các giá trị bị ẩn, tùy cơ chế mapping/cập nhật. Đối với update nhạy cảm, nên xác định cụ thể phần dữ liệu được phép sửa và kiểm soát đồng thời.

## 7. Thuộc tính đa trị chứa DN: dùng Set<Name>

Thuộc tính **member** của **groupOfNames** chứa **DN** của các thành viên. Dùng **Set<Name>** giúp đối tượng Java biểu diễn giá trị như tên LDAP có cấu trúc, đồng thời thuận tiện hơn khi so sánh DN so với chuỗi ghép thủ công.

~~~java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "member")
    private Set<Name> members;

    // Constructor, getters/setters được lược bỏ.
}
~~~

Khi cần tạo một giá trị member an toàn từ input, hãy dùng API DN:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName userDn =
    new LdapName("ou=people,dc=example,dc=org");
userDn.add(new Rdn("uid", userInput));

Name memberDn = userDn;
// Giá trị minh họa: uid=linh,ou=people,dc=example,dc=org
~~~

Đây là phần mã đặt trong method có biến **userInput**. **Rdn** escape giá trị tên theo cú pháp DN, tránh ghép trực tiếp dữ liệu người dùng vào DN. Đừng dùng cách escape LDAP **filter** để xử lý DN vì hai ngữ cảnh có quy tắc khác nhau.

Spring LDAP ODM hỗ trợ thuộc tính **Set<Name>** cho các giá trị DN. Khi Spring LDAP tính thay đổi cho những giá trị **Name**, nó có thể sử dụng cách so sánh DN thay vì chỉ so sánh định dạng văn bản. Tuy nhiên, việc dùng Set<Name> **không tự bảo đảm** quyền thành viên, tồn tại entry được tham chiếu, hay an toàn trước hai writer thay nhóm đồng thời.

Đối với **groupOfNames**, schema thông thường đòi ít nhất **một** giá trị member. Muốn xóa thành viên cuối cùng, ứng dụng phải xử lý chính sách nhóm rõ ràng; máy chủ có thể từ chối nếu kết quả vi phạm schema. Việc có **member** trong nhóm cũng không tự bảo đảm entry thành viên sẽ có thuộc tính **memberOf**: thuộc tính ngược đó tùy cấu hình server hoặc overlay.

## 8. Đọc thuộc tính đa trị không có nghĩa phải ghi đè cả tập

Nội dung bài này tập trung vào **đọc và ánh xạ**, nhưng lựa chọn kiểu dữ liệu liên quan trực tiếp tới cách cập nhật.

Giả sử hai request cùng đọc nhóm với:

~~~text
member = {Linh}

A đọc {Linh} và muốn thêm An
B đọc {Linh} và muốn thêm Bình

A ghi REPLACE member = {Linh, An}
B ghi REPLACE member = {Linh, Bình}

Cuối cùng: {Linh, Bình}; mất An.
~~~

Đây là **lost update**: hai request dùng dữ liệu cũ để thay toàn bộ thuộc tính đa trị. Việc Java sử dụng **Set<String>** hay **Set<Name>** không ngăn được vấn đề.

Nếu nghiệp vụ chỉ muốn **thêm một thành viên**, ưu tiên thao tác LDAP Modify có chủ đích:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem addition = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute(
        "member",
        "uid=an,ou=people,dc=example,dc=org"
    )
);

ldapTemplate.modifyAttributes(
    "cn=developers,ou=groups",
    new ModificationItem[]{addition}
);
~~~

Đoạn mã minh họa nằm trong method có **ldapTemplate** và **ContextSource base=dc=example,dc=org**. **ADD_ATTRIBUTE** gửi yêu cầu thêm đúng một giá trị; nó không yêu cầu client REPLACE toàn bộ member từ snapshot cũ. Xóa đúng một giá trị có thể dùng **REMOVE_ATTRIBUTE** với giá trị cụ thể. **REPLACE_ATTRIBUTE** phù hợp khi muốn chủ đích thay cả tập và có cơ chế kiểm soát xung đột.

**Nhắc lại:** Một LDAP Modify có thể nguyên tử trên một entry, nhưng chuỗi **đọc → sửa bản sao → ghi** gồm nhiều thao tác vẫn có thể gặp cạnh tranh. Nếu cần ghi toàn bộ tập theo snapshot, cân nhắc optimistic concurrency với cơ chế hỗ trợ từ server, chẳng hạn Assertion Control nếu LDAP server triển khai.

## 9. Những khác biệt giữa chuỗi, DN và dữ liệu nhị phân

Không phải giá trị LDAP nào cũng nên ép thành **String**. Bảng sau giúp chọn kiểu:

| Thuộc tính minh họa | Cách biểu diễn hợp lý | Điều cần kiểm tra |
| --- | --- | --- |
| **uid**, **cn**, **sn** | **String** khi kỳ vọng một giá trị cụ thể | Schema và nghiệp vụ có thể cho phép nhiều giá trị |
| **mail** | **Set<String>** hoặc **List<String>** | Không có thứ tự email chính mặc định |
| **objectClass** | **Set<String>** khi cần kiểm tra lớp của entry | So sánh theo schema; thường không cần expose ra API công khai |
| **member**, **uniqueMember** | **Set<Name>** hoặc tập DN đã parse | Giá trị là DN; cần xử lý đúng cú pháp DN |
| **jpegPhoto**, **userCertificate;binary** | **byte[]** hoặc cấu trúc lưu bytes thích hợp | Không chuyển byte ngẫu nhiên thành UTF-8 String |
| **userPassword** | Thường **không đọc** trong ứng dụng nghiệp vụ | ACL phải bảo vệ; không log hay trả qua API |

Với nhị phân, hành vi provider phụ thuộc schema, cú pháp attribute và cấu hình JNDI/Spring LDAP. Có trường hợp cần thông báo cho provider rằng tên thuộc tính cụ thể phải được xử lý dạng binary. Nếu tự ánh xạ bytes, hãy kiểm tra **instanceof byte[]**, giới hạn kích thước payload và trả dữ liệu qua API phù hợp, không dùng **Object.toString()** hoặc ép charset tùy tiện.

Với DN, chỉ so sánh nguyên văn chuỗi có thể tạo khác biệt không cần thiết bởi escape/case/định dạng. **LdapName** hữu ích khi cần parse và làm việc với cấu trúc tên. Tuy vậy, quy tắc equality cụ thể vẫn phải phù hợp với schema và server; không nên coi mọi chuỗi giống hình thức là DN hợp lệ.

## 10. Bảo mật khi đọc dữ liệu LDAP

Một truy vấn lấy nhiều giá trị có thể vô tình đọc lượng dữ liệu lớn hoặc các giá trị nhạy cảm. Các quy tắc quan trọng:

1. **Kết nối:** dùng **LDAPS** hoặc **StartTLS** với xác minh chứng chỉ. Bind thành công chưa đủ chứng minh dữ liệu được truyền qua kết nối được bảo vệ.
2. **Phân quyền:** tài khoản ứng dụng chỉ có quyền cần thiết để search/read thuộc tính; ACL phía server quyết định thuộc tính nào được trả về.
3. **Giới hạn dữ liệu:** chỉ yêu cầu attribute cần cho DTO, giới hạn phạm vi base, search scope, size/time limit và xem xét paging khi danh sách entry lớn.
4. **Filter an toàn:** dùng **LdapQueryBuilder** hoặc JNDI filter parameters. Không ghép input trực tiếp vào biểu thức LDAP filter.
5. **Dữ liệu nhạy cảm:** không log mật khẩu, userPassword, ảnh, chứng chỉ, email thật hoặc toàn bộ member list của tổ chức mà không có nhu cầu.
6. **Kích thước và số lượng:** thuộc tính đa trị có thể rất nhiều giá trị, đặc biệt danh sách thành viên nhóm. Kiểm tra giới hạn nghiệp vụ trước khi đưa toàn bộ dữ liệu ra HTTP response.
7. **Phân biệt thiếu dữ liệu:** null hoặc tập rỗng do dữ liệu không trả về cần được xử lý theo yêu cầu nghiệp vụ; không âm thầm kết luận user “không có email”.

Nếu một **AttributesMapper** được cấu hình chỉ trả **uid** và **cn**, nó không thể đọc **mail** dù server lưu attribute đó. Tương tự, nếu ACL chỉ cho phép search **uid** nhưng không cho phép read **mail**, ứng dụng có thể tìm thấy entry mà không thấy email.

## 11. Kiểm chứng dữ liệu với ldapsearch trước khi sửa Java

Khi mapping không đúng, hãy bắt đầu bằng việc xem giá trị thực của một entry qua công cụ **ldapsearch**. Ví dụ dùng OpenLDAP client:

~~~bash
export LDAP_URI='ldaps://ldap.example.org:636'
export BIND_DN='uid=reader,ou=services,dc=example,dc=org'
export PERSON_DN='uid=linh,ou=people,dc=example,dc=org'
export GROUP_DN='cn=developers,ou=groups,dc=example,dc=org'
~~~

Các lệnh minh họa dùng **-W** để nhập mật khẩu tương tác, không đặt password trong command line:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PERSON_DN" -s base \
  '(objectClass=*)' dn uid cn sn mail
~~~

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$GROUP_DN" -s base \
  '(objectClass=*)' dn cn member
~~~

Nếu server lưu hai giá trị **mail** và tài khoản có quyền đọc, output thường chứa **hai dòng mail:**. Một **member** hiện diện nhiều lần xuất hiện thành nhiều dòng **member:**. LDAP client có thể liệt kê các dòng theo thứ tự khác nhau; không dùng thứ tự dòng để xác nhận giá trị “đầu tiên”.

### 11.1. Checklist khi Java chỉ nhận một phần tử

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| LDAP trả hai **mail**, DTO có một | Dùng **Attribute.get()** hoặc **getStringAttribute()** | Dùng **getAll()**, **getStringAttributes()** hoặc Set mapping |
| LDAP thấy hai giá trị, Java bị lỗi cast | Thuộc tính trả **byte[]** hoặc mapper ép sai kiểu | Chọn kiểu đúng; không ép dữ liệu binary thành String |
| DTO có danh sách rỗng | Thuộc tính không được trả, không được đọc, hoặc không tồn tại | Kiểm tra requested attributes và ACL bằng cùng bind DN |
| Kết quả mảng đổi thứ tự qua mỗi truy vấn | Thuộc tính không có thứ tự bảo đảm | So sánh như Set; sắp xếp riêng khi hiển thị |
| Repository không ánh xạ đúng mail | Sai **@Attribute(name=...)**, base, objectClass hoặc repository scan | So sánh **LdapTemplate** với ODM trên cùng context |
| DN thành viên xử lý sai | Member được coi như uid hoặc tự ghép chuỗi DN | Dùng **Name/LdapName/Rdn** đúng ngữ cảnh |
| API trả “không có email” dù LDAP có | ACL ẩn mail hoặc search chỉ lấy vài attribute | Phân biệt thiếu quan sát với thiếu dữ liệu ở server |

### 11.2. Chọn base DN đúng trong Spring

Giả sử:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=reader,ou=services,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Thì **LdapTemplate** dùng **query().base("ou=people")** khi muốn tìm entry ở **ou=people,dc=example,dc=org**. Đừng ghép lại **dc=example,dc=org** trong một API đã coi base là tương đối, vì dễ tạo DN lặp suffix.

Trong các lệnh **ldapsearch -b**, ngược lại, dùng **DN đầy đủ**. Nhầm DN tương đối/full DN có thể dẫn đến truy vấn rỗng hoặc **noSuchObject (32)**, rồi bị hiểu nhầm là lỗi mapping đa trị.

## 12. Kiểm thử ánh xạ thuộc tính đơn trị và đa trị

Nên kiểm thử bằng **directory có dữ liệu LDIF xác định trước**, vì mock mapper đơn thuần chưa xác nhận schema, objectClass, DN, quyền truy cập và hành vi provider.

### 12.1. Dữ liệu kiểm thử

Tối thiểu, directory test chứa:

- Một entry **inetOrgPerson** có **uid=linh**, **cn**, **sn** và **hai giá trị mail**.
- Một entry **inetOrgPerson** khác có **uid=an**, **cn**, **sn** và **không có mail** (nếu schema cho phép).
- Một nhóm **groupOfNames** có **cn=developers** và **hai giá trị member** trỏ tới các DN tương ứng.
- Một tài khoản read-only có quyền đọc những thuộc tính cần kiểm tra nhưng không có quyền đọc thuộc tính nhạy cảm.

Có thể sử dụng LDIF minh họa ở đầu bài để khởi tạo các entry (thêm entry cha trước khi thêm entry con). Những giá trị **mail** không bắt buộc trong schema **inetOrgPerson** thông dụng, nhưng cần kiểm tra schema thực của directory test.

### 12.2. Các ca kiểm thử cần có

| Ca kiểm thử | Hành động | Kỳ vọng |
| --- | --- | --- |
| Một giá trị | Đọc **uid** và **cn** của Linh | Nhận đúng chuỗi |
| Nhiều giá trị | Đọc **mail** của Linh bằng **getAll()** hoặc **getStringAttributes()** | Nhận **cả hai** địa chỉ |
| Không có thuộc tính | Đọc **mail** của An | Kết quả vắng/null hoặc tập rỗng theo contract mapper |
| Nhiều DN | Đọc **member** nhóm developers | Nhận hai DN dưới dạng tập, không dựa vào thứ tự |
| Repo mapping | Dùng **DirectoryPersonRepository.findByUid("linh")** | Entity có **emails.size() == 2** và DN đúng |
| Requested attribute | Chỉ yêu cầu uid,cn | Không giả định mapper nhìn thấy mail |
| ACL | Bind bằng tài khoản không có quyền đọc mail | Mapping xử lý thiếu mail đúng chính sách |
| Nhị phân | Lấy thuộc tính binary của một entry test | Không cast nhầm thành String |
| Filter an toàn | Tìm uid có ký tự đặc biệt qua query builder | Giá trị được escape; không thay đổi cấu trúc filter |

Ví dụ mã khẳng định không phụ thuộc thứ tự khi dùng **LdapTemplate** (bên trong integration test đã cấu hình ContextSource và LDAP test data):

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

class PersonMultiValueIntegrationTest {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void readsAllMailValues() {
        List<List<String>> results = ldapTemplate.search(
            query().base("ou=people").where("uid").is("linh"),
            (AttributesMapper<List<String>>) attrs ->
                MultiValueReader.allStrings(attrs, "mail")
        );

        assertEquals(1, results.size());
        assertEquals(
            Set.of("linh@example.org", "linh.work@example.org"),
            new HashSet<>(results.get(0))
        );
    }
}
~~~

Đoạn kiểm thử trên được thiết kế để đặt trong **Spring test context** (ví dụ Spring Boot test hoặc LDAP test slice phù hợp phiên bản), có bean **LdapTemplate** và dữ liệu LDIF đã nạp. Để chạy được, phải cấu hình extension/context Spring test và dependency JUnit tương ứng; bản thân đoạn class tối giản chưa đủ làm một ứng dụng hoàn chỉnh.

Ở case đa trị, hãy so sánh **Set** thay vì assert thứ tự **List**. Nếu nghiệp vụ cho phép giá trị trùng ở representation đặc biệt, cần dựa trên schema/matching rule và đặc tả LDAP server thay vì tự động loại trùng mọi kiểu dữ liệu.

## 13. Những sai lầm cần tránh

**Sai lầm 1 — “Một giá trị LDAP luôn là một chuỗi.”** Nhiều thuộc tính có thể có nhiều giá trị; một số giá trị là DN hoặc bytes. Kiểu Java cần phản ánh kiểu giá trị thực.

**Sai lầm 2 — “Attribute.get() trả giá trị ưu tiên nhất.”** Với thuộc tính không thứ tự, get() chỉ trả một giá trị và không định nghĩa “primary”.

**Sai lầm 3 — “Không thấy mail tức là nhân viên không có email.”** Search có thể không yêu cầu mail, tài khoản bị ACL hạn chế hoặc mapping không đúng.

**Sai lầm 4 — “List có hai mail theo thứ tự từ server nên phần tử 0 là mail chính.”** Với thuộc tính không có ngữ nghĩa thứ tự, việc suy diễn đó không đúng; cần quy tắc nghiệp vụ riêng.

**Sai lầm 5 — “@Id là trường uid trong entity.”** Trong LDAP ODM, **@Id** biểu diễn **DN** của entry. Một **uid** có thể là attribute và một phần của RDN, nhưng không thay thế toàn bộ DN.

**Sai lầm 6 — “Thay toàn bộ Set rồi save không có rủi ro.”** Hai writer có thể đọc snapshot cũ và làm mất cập nhật. Tùy nghiệp vụ, sử dụng delta **ADD/DELETE** hoặc điều kiện cập nhật phù hợp.

**Sai lầm 7 — “Dữ liệu DN cứ để String tự ghép là đủ.”** DN có escaping và cấu trúc; cần **LdapName/Rdn** hoặc API tương đương khi nhận input động.

## 14. Câu hỏi ôn tập và tổng kết

1. Sự khác nhau giữa **Attributes.getAll()** và **Attribute.getAll()** là gì?
2. Vì sao **Attribute.get()** hoặc **getStringAttribute("mail")** không phù hợp khi ứng dụng cần mọi email?
3. Khi nào nên dùng **Set<String>**, **List<String>** và **Set<Name>**?
4. **getStringAttributes(...)** trả gì nếu attribute không hiện diện? Tại sao điều đó không nhất thiết chứng minh attribute không có trên server?
5. **@Id** trong Spring LDAP ODM dùng cho uid hay DN? Package đúng của annotation là gì?
6. Vì sao một nhóm có hai giá trị **member** không tự chứng minh mỗi thành viên đều có **memberOf**?
7. Kiểm thử như thế nào để phát hiện mapper vô tình chỉ lấy một trong hai giá trị mail?
8. Vì sao cần tránh dùng thao tác **REPLACE** cả tập member khi chỉ muốn thêm một người?

**Ghi nhớ:** Một entry LDAP là tập thuộc tính; mỗi thuộc tính có thể chứa một hoặc nhiều giá trị tùy schema. Khi chỉ cần một giá trị, hãy kiểm tra giả định và xử lý null/kiểu dữ liệu. Khi cần toàn bộ giá trị, dùng **Attribute.getAll()**, **DirContextOperations.getStringAttributes()** hoặc ánh xạ **Set/List** trong Spring Data LDAP. Với DN, ưu tiên **Name**; với dữ liệu nhị phân, dùng kiểu bytes phù hợp. Luôn kiểm tra **schema, ACL, base DN, filter, requested attributes** và so sánh tập giá trị trong integration test.

## Tài liệu tham khảo

- [Java JNDI — Attribute API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/Attribute.html): cách lấy một hoặc tất cả giá trị, khái niệm ordered/unordered.
- [Java JNDI — Attributes API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/Attributes.html): tập các thuộc tính của entry.
- [Spring LDAP — LdapDataEntry API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/LdapDataEntry.html): **getStringAttribute**, **getStringAttributes**, **getObjectAttributes** và **getDn**.
- [Spring LDAP — DirContextOperations API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html): thao tác đọc giá trị từ context của entry.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): **@Entry**, **@Attribute**, **@Id**, ánh xạ tập **Set<Name>**.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): mô hình repository trên các LDAP entry.
