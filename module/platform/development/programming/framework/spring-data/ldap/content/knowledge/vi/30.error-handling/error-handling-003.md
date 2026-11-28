# NameNotFoundException và search base không tồn tại

Trong **Spring Data LDAP**, việc kết nối được tới LDAP server và xác thực thành công không bảo đảm mọi lệnh truy vấn đều hợp lệ. Một lỗi phổ biến là ứng dụng tìm kiếm dưới một **search base DN** không có trong cây thư mục. Ở tầng LDAP, server có thể trả **noSuchObject (result code 32)**; ở tầng **JNDI**, lỗi này thường biểu hiện thành **javax.naming.NameNotFoundException**; khi đi qua **Spring LDAP**, nó thường được dịch sang **org.springframework.ldap.NameNotFoundException**.

Bài học thuộc chương **Xử lý lỗi**, giải thích nguyên nhân, cách phân biệt **search base không tồn tại** với **không có entry thỏa filter**, cách xác minh bằng **ldapsearch**, JNDI, **LdapTemplate** và **Spring Data LDAP Repository**, cùng các chiến lược xử lý lỗi an toàn. Đây là kiến thức cần thiết khi xây dựng repository, ánh xạ entry phân cấp sang Java, truy vấn DN/objectClass, kiểm tra ACL và triển khai ứng dụng với OpenLDAP hoặc directory khác.

## 1. NameNotFoundException biểu thị điều gì?

**Distinguished Name (DN)** định danh một entry trong cây thư mục LDAP (Directory Information Tree, DIT). Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=an
└── ou=groups
    └── cn=developers
~~~

Với cây này, các DN sau tồn tại:

- **dc=example,dc=org**: entry gốc của suffix.
- **ou=people,dc=example,dc=org**: nhánh chứa người dùng.
- **uid=linh,ou=people,dc=example,dc=org**: entry người dùng Linh.
- **ou=groups,dc=example,dc=org**: nhánh nhóm.

Trong khi đó, **ou=users,dc=example,dc=org** không tồn tại ở cây minh họa. Nếu gửi LDAP SearchRequest có **baseObject = ou=users,dc=example,dc=org**, server không thể bắt đầu tìm từ entry đó. Một kết quả thường gặp là:

~~~text
LDAP resultCode: noSuchObject (32)
JNDI: javax.naming.NameNotFoundException
Spring LDAP: org.springframework.ldap.NameNotFoundException
~~~

Tên exception trong Java không có nghĩa bản thân **filter** không tìm thấy người dùng; nó có thể chỉ ra rằng **điểm bắt đầu tìm kiếm không hợp lệ**. Cũng cần phân biệt lỗi trên với trường hợp truy vấn trực tiếp DN bằng **lookup** khi entry đích không có.

### 1.1. Phân biệt ba tình huống dễ nhầm

| Tình huống | Ví dụ | Kết quả thường gặp |
| --- | --- | --- |
| **Search base tồn tại, không entry nào khớp filter** | Tìm **(uid=khong-co)** dưới **ou=people** | Search thành công, **0 entry** |
| **Search base không tồn tại** | Tìm **(uid=linh)** dưới **ou=users** | Server trả **noSuchObject (32)**, có thể thành NameNotFoundException |
| **Lookup DN đích không tồn tại** | Lookup **uid=khong-co,ou=people,...** | Thường cũng là **noSuchObject (32)**, nhưng thao tác là lookup cụ thể |

**Nguyên tắc:** **0 kết quả** trong một truy vấn hợp lệ khác với **truy vấn bắt đầu tại DN không tồn tại**. Hệ thống xử lý hai tình huống này như nhau có thể che mất lỗi cấu hình nghiêm trọng.

## 2. LDAP SearchRequest sử dụng base, scope và filter ra sao?

Một tìm kiếm LDAP được xác định bởi nhiều tham số:

| Tham số | Chức năng | Ví dụ |
| --- | --- | --- |
| **baseObject (base DN)** | Entry bắt đầu tìm kiếm | ou=people,dc=example,dc=org |
| **scope** | Chọn chính base, các con trực tiếp hay cả cây con | base / one / sub |
| **filter** | Điều kiện chọn entry | (uid=linh) |
| **attributes** | Thuộc tính muốn trả về | uid, cn, mail |
| **sizeLimit/timeLimit** | Giới hạn số entry hoặc thời gian thực thi | 100 entry, 5 giây |
| **bind identity** | Danh tính được server kiểm tra quyền truy cập | uid=reader,ou=services,... |

LDAP phân biệt ba scope:

- **baseObject / OBJECT**: chỉ tìm trên entry ở đúng base DN.
- **singleLevel / ONELEVEL**: chỉ các entry con trực tiếp của base DN.
- **wholeSubtree / SUBTREE**: base DN và toàn bộ entry con bên dưới.

Ví dụ **ou=people** có hai người dùng nằm ngay bên dưới: ONELEVEL và SUBTREE có thể tìm **uid=linh**. Nhưng nếu base lại là **ou=users** và entry này không tồn tại, việc đổi scope từ ONELEVEL sang SUBTREE **không tạo ra nhánh còn thiếu**.

Thay đổi filter từ **(uid=linh)** sang **(objectClass=*)** cũng không thể sửa lỗi base DN không tồn tại. Khi base sai, cần sửa **điểm bắt đầu**, không chỉ sửa điều kiện lọc.

~~~mermaid
flowchart TD
    A["LDAP Search(base, scope, filter)"] --> B{"Base DN có thể được server định vị?"}
    B -->|Không| C["noSuchObject (32) / NameNotFoundException"]
    B -->|Có| D["Server áp dụng scope + filter + ACL"]
    D --> E{"Có entry được phép trả về?"}
    E -->|Có| F["Search success + danh sách entry"]
    E -->|Không| G["Search success + 0 entry"]
    D -. "Có thể có lỗi limit, referral, ACL..." .-> H["Result/exception riêng"]
~~~

Tùy sản phẩm LDAP server và chính sách **ACL**, sự tồn tại của entry có thể bị che bớt đối với một số danh tính. Vì thế kết quả **noSuchObject** cần được đối chiếu với quyền truy cập và endpoint trước khi kết luận entry đã bị xóa khỏi server.

## 3. Dữ liệu LDIF để tái hiện lỗi

Giả sử OpenLDAP server đã có suffix **dc=example,dc=org** và tài khoản có quyền tạo entry. Bộ dữ liệu thử nghiệm:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

Lưu nội dung vào **sample-directory.ldif** nếu đang khởi tạo một directory lab trống. **Thứ tự import là cha trước, con sau**. Nếu server đã tạo entry **dc=example,dc=org**, bỏ khối root khỏi file để tránh lỗi **entryAlreadyExists (68)**; tương tự, không nhập trùng các OU hoặc người dùng hiện có.

Những điều cần quan sát:

1. Base hợp lệ **ou=people,dc=example,dc=org**.
2. Entry hợp lệ **uid=linh,ou=people,dc=example,dc=org**.
3. Base cố ý **không tồn tại**: **ou=users,dc=example,dc=org**.
4. Filter **(uid=khong-co)** không khớp entry nào, nhưng search base **ou=people** vẫn hợp lệ.

Schema của **inetOrgPerson** thường kế thừa các yêu cầu **cn** và **sn** từ **person**. Việc thiếu objectClass/attribute bắt buộc khi nhập LDIF là vấn đề schema khác với **NameNotFoundException** lúc tìm kiếm.

## 4. Xác minh bằng ldapsearch trước khi sửa mã Java

Sử dụng công cụ **ldapsearch** của OpenLDAP client để tái hiện truy vấn độc lập với Spring. Ví dụ shell Bash:

~~~bash
export LDAP_URI='ldaps://ldap.example.org:636'
export BASE_DN='dc=example,dc=org'
export PEOPLE_DN='ou=people,dc=example,dc=org'
export BAD_BASE_DN='ou=users,dc=example,dc=org'
export BIND_DN='uid=reader,ou=services,dc=example,dc=org'
~~~

Các giá trị chỉ minh họa. Tài khoản **reader** cần tồn tại và có quyền phù hợp trong lab; không có tài khoản nào được tự tạo ra chỉ bằng cách khai báo biến môi trường. Trên hệ thống thực, dùng endpoint và bind DN đã được quản trị cấp.

### 4.1. Xác minh LDAP endpoint và suffix

Truy vấn **Root DSE**, thường dùng base DN rỗng:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -b "" -s base "(objectClass=*)" namingContexts
~~~

Nếu server công bố:

~~~ldif
dn:
namingContexts: dc=example,dc=org
~~~

thì ít nhất có một dấu hiệu server đang phục vụ naming context mong đợi. Tuy nhiên, không phải server nào cũng công bố mọi thông tin Root DSE giống nhau hoặc cho mọi bind identity; nếu thiếu **namingContexts**, cần xác nhận suffix từ cấu hình directory đáng tin cậy.

### 4.2. Kiểm tra base tồn tại

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s base "(objectClass=*)" \
  dn ou objectClass
~~~

Với quyền đọc phù hợp, kết quả chứa entry **ou=people,dc=example,dc=org**. Tham số **-s base** giúp kiểm tra chính entry base, trước khi thêm filter người dùng hoặc tìm nhiều tầng.

### 4.3. So sánh một truy vấn không khớp và một base không có

Base đúng, uid không tồn tại:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s sub "(uid=khong-co)" \
  dn uid
~~~

Kỳ vọng là **Search result: success (0)** với không entry phù hợp (dạng hiển thị chi tiết còn tùy flag của ldapsearch).

Base sai, uid có thật ở nhánh khác:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$BAD_BASE_DN" -s sub "(uid=linh)" \
  dn uid
~~~

Kết quả điển hình:

~~~text
ldap_search_ext: No such object (32)
~~~

Chuỗi thông báo của công cụ có thể khác giữa các phiên bản. **Mã LDAP 32** là tín hiệu quan trọng hơn cách diễn đạt. Một số server còn gửi **matched DN** của entry tổ tiên gần nhất có thể xác định trong LDAPResult, giúp khoanh vùng đoạn DN bị sai; không được coi đây là cơ chế luôn có hoặc luôn được trả cho mọi tài khoản.

### 4.4. Kiểm tra đúng danh tính ứng dụng

Khi **reader** gặp code 32, có thể kiểm tra cùng truy vấn bằng một tài khoản quản trị **trong lab, khi được phép**:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "cn=admin,dc=example,dc=org" -W \
  -b "$BAD_BASE_DN" -s base "(objectClass=*)" \
  dn
~~~

Nếu **admin cũng nhận 32**, nhiều khả năng DN thực sự không tồn tại hoặc trỏ sai suffix. Nếu **admin tìm được** còn **reader không thấy**, cần xem **ACL/visibility** thay vì sửa DN theo phỏng đoán. Không chuyển ứng dụng sang tài khoản admin để che lỗi quyền.

**Bảo mật lệnh:** Dùng **-W** để nhập mật khẩu tương tác, không dùng **-w matkhau** trong tài liệu hoặc script vì có nguy cơ lộ qua lịch sử/lệnh đang chạy. **ldaps://** yêu cầu xác minh chứng chỉ của server; không tắt kiểm tra TLS để điều tra lỗi search.

## 5. JNDI: bắt NameNotFoundException đúng tầng

JNDI là API Java để làm việc với directory qua **DirContext**. Với LDAP provider, một lệnh search tại DN không tồn tại có thể ném **javax.naming.NameNotFoundException**. Ví dụ dùng **InitialDirContext**:

~~~java
import java.util.Hashtable;
import java.util.Objects;
import javax.naming.Context;
import javax.naming.NameNotFoundException;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public final class JndiSearchExample {
    public static void main(String[] args) throws NamingException {
        String password = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "Missing LDAP_BIND_PASSWORD");

        Hashtable<String, Object> environment = new Hashtable<>();
        environment.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        environment.put(Context.PROVIDER_URL,
            "ldaps://ldap.example.org:636");
        environment.put(Context.SECURITY_AUTHENTICATION, "simple");
        environment.put(Context.SECURITY_PRINCIPAL,
            "uid=reader,ou=services,dc=example,dc=org");
        environment.put(Context.SECURITY_CREDENTIALS, password);
        environment.put("com.sun.jndi.ldap.connect.timeout", "5000");
        environment.put("com.sun.jndi.ldap.read.timeout", "5000");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[]{"uid", "cn"});
        controls.setCountLimit(20);
        controls.setTimeLimit(5000);

        DirContext context = null;
        NamingEnumeration<SearchResult> found = null;
        try {
            context = new InitialDirContext(environment);
            found = context.search(
                "ou=users,dc=example,dc=org",
                "(uid={0})",
                new Object[]{"linh"},
                controls);

            while (found.hasMore()) {
                SearchResult item = found.next();
                System.out.println(item.getNameInNamespace());
            }
        } catch (NameNotFoundException ex) {
            System.err.println("LDAP search base is not reachable.");
            throw ex;
        } finally {
            try {
                if (found != null) {
                    found.close();
                }
            } finally {
                if (context != null) {
                    context.close();
                }
            }
        }
    }
}
~~~

Trong đoạn mã:

- **context.search(...)** gửi **base DN đầy đủ** vì JNDI context được tạo trực tiếp, không đặt một Spring ContextSource base tương đối.
- Filter **(uid={0})** và **filterArgs** an toàn hơn việc ghép chuỗi đầu vào trực tiếp vào filter.
- **SearchControls** quyết định scope và các giới hạn; chúng không thể làm tồn tại một base bị thiếu.
- Catch đúng **javax.naming.NameNotFoundException** ở cấp JNDI giúp phân biệt nó với **AuthenticationException**, **CommunicationException**, **InvalidSearchFilterException** và lỗi khác cùng họ **NamingException**.
- Ngoại lệ có thể xuất hiện khi gọi **search(...)** hoặc lúc duyệt **NamingEnumeration**; do đó phần duyệt vẫn nằm trong khối try.
- **NamingEnumeration** và **DirContext** được đóng trong finally vì có thể giữ tài nguyên kết nối.

**Không xử lý bằng cách trả về danh sách rỗng ngay trong catch NameNotFoundException** nếu base là cấu hình cố định của ứng dụng. Cách đó biến sự cố cấu hình thành “không có người dùng”, gây khó điều tra và có thể khiến luồng nghiệp vụ đưa ra quyết định sai.

## 6. Spring LDAP: NameNotFoundException qua LdapTemplate

Trong ứng dụng Spring, **LdapTemplate** lấy context từ **ContextSource**, truy vấn LDAP qua JNDI và chuyển nhiều ngoại lệ thuộc **javax.naming** sang họ ngoại lệ truy cập LDAP của Spring. Khi base không tồn tại, ngoại lệ tương ứng thường là **org.springframework.ldap.NameNotFoundException**, khác package với JNDI.

Ví dụ cấu hình:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=reader,ou=services,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Giả sử app sử dụng bean **LdapTemplate** do Spring cấu hình. Một truy vấn:

~~~java
import java.util.List;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PeopleDirectoryService {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String uid) {
        try {
            return ldapTemplate.search(
                query()
                    .base("ou=users") // Cố ý sai: OU không tồn tại.
                    .where("uid").is(uid),
                (AttributesMapper<String>) attributes ->
                    attributes.get("cn").get().toString());
        } catch (NameNotFoundException ex) {
            throw new IllegalStateException(
                "Configured LDAP people search base does not exist",
                ex);
        }
    }
}
~~~

Trong ví dụ này, **spring.ldap.base** đã là **dc=example,dc=org**. Do đó, **query().base("ou=users")** biểu diễn base DN đầy đủ **ou=users,dc=example,dc=org**. Với cây dữ liệu ở phần 3, đó là nhánh không tồn tại. Khi sửa thành **query().base("ou=people")**, truy vấn có thể tìm thấy Linh nếu filter và ACL phù hợp.

**Cẩn trọng với cấu hình bỏ qua lỗi:** LdapTemplate có cơ chế cấu hình cách xử lý một số ngoại lệ, gồm khả năng bỏ qua lỗi tên không tìm thấy trong các đường xử lý hỗ trợ. Nếu môi trường đã bật cách bỏ qua **NameNotFoundException**, một số truy vấn có thể kết thúc bằng tập kết quả rỗng thay vì ném lỗi ra service. Hãy xác minh cài đặt thực tế, đường đi API và test trên directory đang dùng. Không dựa vào giả định mọi phiên bản/template đều xử lý giống nhau.

### 6.1. Phân biệt exception của JNDI và Spring

| Tầng | Kiểu ngoại lệ | Thường bắt ở đâu? |
| --- | --- | --- |
| JNDI trực tiếp | **javax.naming.NameNotFoundException** | Mã Java sử dụng DirContext / InitialDirContext |
| Spring LDAP | **org.springframework.ldap.NameNotFoundException** | Service sử dụng LdapTemplate / ContextSource |
| Spring Data LDAP | Ngoại lệ truy cập dữ liệu thông qua tầng Spring LDAP hoặc hành vi truy vấn repository | Service gọi repository; cần xem nguyên nhân gốc và phiên bản cụ thể |

Hai class đều có tên **NameNotFoundException** nhưng không cùng package. Khi viết code có cả JNDI và Spring LDAP, có thể dùng tên đầy đủ trong catch hoặc import đúng một loại phù hợp API đang gọi.

Không cố đoán loại exception chỉ từ chữ “not found”. Đọc **message, cause chain và LDAP result code** giúp phân biệt mất base, DN đích không tồn tại và các lỗi directory khác.

## 7. Spring Data LDAP Repository và nhầm lẫn @Entry(base)

Spring Data LDAP cung cấp **LdapRepository** để truy vấn entry dưới dạng Java object. Ví dụ một entity:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor không tham số, getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
}
~~~

Với **@Entry(base = "ou=people")** và **spring.ldap.base = dc=example,dc=org**, domain object **Person** được tìm trong nhánh **ou=people,dc=example,dc=org**. Nếu thay @Entry thành **ou=users** mà không tạo entry OU tương ứng, các phương thức tìm kiếm dựa trên mapping có thể phát sinh lỗi **noSuchObject**, hoặc biểu hiện rỗng nếu tầng truy cập đã cấu hình bỏ qua lỗi.

**@Id** của LDAP ODM đại diện cho DN của entry; nó không phải ID số tự tăng hoặc thuộc tính **uid**. Import đúng là **org.springframework.ldap.odm.annotations.Id**. Repository được Spring scan thành bean và có thể gọi method không có nghĩa DN hay entry đã tồn tại trên LDAP server.

### 7.1. Kết quả Optional.empty() có nghĩa gì?

~~~java
Optional<Person> result = personRepository.findByUid("khong-co");
~~~

**Optional.empty()** thường có nghĩa **không tìm được entry phù hợp** với truy vấn repository đã chạy thành công. Nhưng một kết quả rỗng tự nó không chứng minh toàn bộ directory không có user đó:

- Repository có thể đang tìm sai **@Entry(base)** hoặc sai domain/suffix.
- Filter có thể yêu cầu objectClass không khớp với entry thực.
- ACL có thể ẩn entry khỏi tài khoản bind.
- Tầng truy cập có thể đang bỏ qua một số lỗi **NameNotFoundException**.

**Không tự động chuyển mọi ngoại lệ truy vấn thành Optional.empty().** Chính sách này làm mất thông tin về môi trường sai hoặc kết nối/ACL bất thường, và khiến ứng dụng hiểu một lỗi vận hành thành kết quả nghiệp vụ.

## 8. Căn nguyên phổ biến nhất: sai DN tương đối và DN đầy đủ

Spring **ContextSource** thường có một **base DN** cấu hình sẵn. Khi gọi **LdapTemplate** với base tương đối, thư viện sẽ tính DN trên server bằng cách ghép vào ContextSource base.

~~~text
LDAP server suffix:
  dc=example,dc=org

spring.ldap.base:
  dc=example,dc=org

LdapTemplate query base đúng:
  ou=people

Search base gửi tới server:
  ou=people,dc=example,dc=org
~~~

Nếu nhầm và truyền full DN vào API đòi DN tương đối:

~~~java
// Nguy cơ lặp suffix do ContextSource đã có base:
query().base("ou=people,dc=example,dc=org")
    .where("uid").is("linh");
~~~

Base thực có thể bị ghép thành:

~~~text
ou=people,dc=example,dc=org,dc=example,dc=org
~~~

DN này không tồn tại và dễ dẫn đến **noSuchObject (32)**. Ngược lại, **ldapsearch -b** thường nhận **DN đầy đủ**, nên lệnh CLI:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=linh)" dn uid
~~~

không sử dụng cùng quy tắc base tương đối như Spring ContextSource. Do đó, muốn đối chiếu CLI với Java cần xác định **base cuối cùng thực gửi tới server**, không chỉ so sánh chuỗi viết trong code.

### 8.1. Các trường hợp sai DN thường gặp

| Sai lệch | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Sai tên OU** | ou=users trong khi thực là ou=people | Base không tồn tại |
| **Sai suffix** | dc=example,dc=com thay vì dc=example,dc=org | Truy vấn nhầm naming context |
| **Lặp suffix** | ou=people,dc=example,dc=org,dc=example,dc=org | noSuchObject, có thể là code 32 |
| **Thiếu OU trung gian** | ou=people trực tiếp trong khi dữ liệu ở ou=engineering,ou=people | Scope/base không phù hợp, có thể trả rỗng |
| **DN cú pháp sai** | Dấu phẩy/escape sai | Có thể là **invalidDNSyntax (34)**, không phải code 32 |
| **Alias/referral** | Base nằm ở nhánh được điều hướng | Hành vi phụ thuộc dereference/referral và server |

Với DN sinh từ dữ liệu động, dùng **javax.naming.ldap.LdapName** và **Rdn** thay vì nối chuỗi. Việc escape **LDAP filter** và escape **DN** là hai việc khác nhau. Không cho người dùng tùy ý điều khiển base DN vượt ra ngoài nhánh được phép.

## 9. NameNotFoundException có thể liên quan ACL và topology

Không phải mọi **noSuchObject** đều do lỗi chính tả. Khi điều tra trên directory doanh nghiệp, còn những yếu tố sau:

### 9.1. Quyền đọc/nhìn thấy entry

ACL của OpenLDAP hoặc chính sách của directory khác có thể che sự tồn tại của entry. Một danh tính chưa được cấp quyền có thể nhận thông báo trông giống **không có entry**, trong khi admin thấy entry tồn tại.

Do đó, khi gặp lỗi:

1. Giữ nguyên **endpoint, base, scope, filter**.
2. Chạy **ldapsearch bằng bind DN của ứng dụng**.
3. Chỉ trong môi trường được phép, đối chiếu với tài khoản đủ quyền đọc nhánh.
4. Nếu kết quả khác nhau, kiểm tra **quyền search/read trên entry và thuộc tính** trước khi sửa code.

Đừng đổi tài khoản ứng dụng sang rootDN hoặc admin để né lỗi: đó là mở rộng quyền và có thể che mất thiết kế ACL chưa đúng.

### 9.2. Nhiều suffix, referral hoặc alias

Một server có thể phục vụ nhiều **namingContexts**, dùng **referral** sang directory khác hoặc có **alias**. Search base nằm ngoài suffix được phục vụ có thể dẫn đến referral hoặc thông báo khác tùy sản phẩm và cấu hình. Cần xem Root DSE, referral handling, quyền truy cập và DN đích thực tế.

Việc bật tự theo referral có thể làm client kết nối đến server khác và đặt vấn đề về **forward credentials**. Chỉ bật khi hiểu rõ topology và chính sách xác thực, không coi đó là cách sửa mặc định cho code 32.

### 9.3. Replication và nhầm endpoint

Entry mới có thể đã được tạo trên LDAP node A nhưng chưa xuất hiện trên replica B. Trong khi đó, URL cấu hình của ứng dụng trỏ tới node B. Cùng một DN có thể tồn tại ở một thời điểm trên node này nhưng chưa có trên node kia.

Khi có nhiều node, ghi nhận **host thực**, thời điểm cập nhật, cơ chế replication và yêu cầu nhất quán. Không kết luận entry bị xóa khi chưa xác định đường đọc/ghi của ứng dụng.

### 9.4. Entry bị đổi DN hoặc xóa

Trong LDAP, **rename/move** thay DN của entry; vì vậy client giữ DN cũ có thể gặp NameNotFoundException sau khi đổi cấu trúc OU. Một ứng dụng chỉ lưu **uid** và dựng DN theo cấu trúc cố định có thể thất bại nếu người dùng được chuyển nhánh.

Giải pháp phụ thuộc bài toán: lưu định danh ổn định có sẵn của directory nếu phù hợp, tìm entry theo attribute với base hợp lệ hoặc cập nhật đường dẫn sau rename. Không tự xem DN là ID vĩnh viễn bất biến.

## 10. Chính sách xử lý lỗi đúng trong service Java

Cần phân biệt **không có kết quả nghiệp vụ** và **truy vấn không hợp lệ**:

| Trường hợp | Chính sách khuyến nghị | Lý do |
| --- | --- | --- |
| Filter không khớp dưới một base hợp lệ | Trả **Optional.empty()** hoặc danh sách rỗng | Kết quả tìm kiếm hợp lệ |
| Base cố định do ứng dụng cấu hình không tồn tại | Báo **lỗi cấu hình/hạ tầng** và giữ cause | Mọi kết quả dưới nhánh đó đều không đáng tin |
| Base do người dùng chọn từ danh sách OU cho phép nhưng OU đã bị xóa | Báo **tài nguyên không còn tồn tại** hoặc thông báo nghiệp vụ phù hợp | Là vấn đề trạng thái thực tế, cần quyết định ở contract API |
| Không đủ quyền read/search | Báo **lỗi phân quyền**, làm việc với quản trị LDAP | Không thể suy ra chỉ từ kết quả rỗng |
| Kết nối/TLS/authentication lỗi | Xử lý riêng theo loại lỗi, có thể trả lỗi dịch vụ tạm thời | Không nên hiển thị “không tìm thấy user” |
| Cấu hình bỏ qua NameNotFoundException gây kết quả rỗng | Điều chỉnh chính sách và test theo yêu cầu | Tránh che lỗi dữ liệu/cấu hình |

Ví dụ một service biết **base đúng phải là ou=people** và muốn giữ dấu vết nguyên nhân:

~~~java
import java.util.List;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryQueryService {
    private final LdapTemplate ldapTemplate;

    public DirectoryQueryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUserNames(String uid) {
        try {
            return ldapTemplate.search(
                query().base("ou=people").where("uid").is(uid),
                (AttributesMapper<String>) attrs ->
                    attrs.get("cn").get().toString()
            );
        } catch (NameNotFoundException ex) {
            // Lỗi base cấu hình: cần cảnh báo vận hành.
            // Giữ cause để quan sát nội bộ, không lộ raw LDAP detail
            // trong response cho người dùng cuối.
            throw new DirectorySearchConfigurationException(
                "LDAP people search base is unavailable", ex);
        }
    }

    public static final class DirectorySearchConfigurationException
            extends RuntimeException {
        public DirectorySearchConfigurationException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Đây là ví dụ về **phân loại lỗi**, không bắt buộc mọi dự án tạo đúng exception tên trên. Nếu tên lỗi ở tầng API cần được chuyển thành HTTP status hoặc thông điệp cho người dùng, hãy thiết kế contract rõ ràng, tránh phản hồi trực tiếp **DN, bind identity, stack trace hoặc mật khẩu**.

### 10.1. Có nên tự động tạo search base khi gặp NameNotFoundException?

Thông thường **không**. Search là thao tác đọc; nếu tự tạo **ou=people** sau khi search lỗi, ứng dụng có thể:

- Tạo cấu trúc sai ở một environment nhầm.
- Yêu cầu quyền ghi quá lớn cho tài khoản chỉ đọc.
- Che mất việc directory được quản lý bởi hệ thống khác.
- Gây xung đột schema hoặc ACL khi tự thêm OU.

Việc tạo nhánh directory nên nằm trong **provisioning/migration được ủy quyền**, không phải một nhánh xử lý exception của mọi request tìm kiếm.

### 10.2. Có nên retry?

Nếu base DN **không tồn tại do cấu hình sai**, retry cùng request không giải quyết được lỗi. Nếu nghi có **replication lag** hoặc provisioning đang tiến hành, có thể thiết kế retry có giới hạn dựa trên điều kiện hạ tầng được xác nhận, kèm timeout, backoff và quan sát trạng thái. Không retry vô hạn hoặc đổi sang endpoint bất kỳ vì làm tăng tải và che lỗi gốc.

## 11. Quy trình chẩn đoán theo thứ tự hiệu quả

Khi gặp **NameNotFoundException** hoặc một danh sách rỗng đáng ngờ:

1. **Ghi lại thao tác thật:** Search, lookup hay modify? Dùng đúng stack trace và LDAP result code (32 hay mã khác).
2. **Chốt endpoint và bind DN:** Xác nhận ứng dụng đang đọc đúng directory, đúng môi trường, đúng tài khoản dịch vụ và có kết nối TLS hợp lệ.
3. **Xác minh suffix/root:** Dùng Root DSE hoặc thông tin cấu hình tin cậy để xác định naming context.
4. **Kiểm tra search base cụ thể:** Dùng **ldapsearch -s base** với DN cuối cùng trên server; nếu không có, lần theo từng DN cha.
5. **Đặt filter tối giản:** Với base đúng, dùng **(objectClass=*)**, sau đó **(uid=linh)** và các điều kiện objectClass của repository.
6. **Kiểm tra scope:** OBJECT/ONELEVEL/SUBTREE có phù hợp cấu trúc OU thực không?
7. **Đối chiếu Spring ContextSource:** Kiểm tra **spring.ldap.base**, base tương đối trong LdapTemplate và **@Entry(base)** để tránh lặp suffix.
8. **Đối chiếu ACL:** Chạy cùng truy vấn với bind DN ứng dụng; so sánh với danh tính đủ quyền trong lab.
9. **Kiểm tra referral/alias/replica:** Nếu topology nhiều nhánh/node, xác định host và thời điểm dữ liệu được cập nhật.
10. **Tạo integration test:** Mô phỏng base hợp lệ/không hợp lệ và filter có/không có kết quả để tránh lặp sự cố.

~~~mermaid
flowchart TD
    A["Spring/JNDI báo NameNotFoundException"] --> B["Lấy base DN cuối cùng + LDAP code"]
    B --> C["ldapsearch -s base với cùng bind/endpoint"]
    C --> D{"Base tồn tại?"}
    D -->|Không| E["Kiểm tra suffix, OU cha, typo, DN tương đối"]
    D -->|Có| F["Kiểm tra scope, filter, objectClass"]
    F --> G{"Search có entry?"}
    G -->|Có| H["So sánh LdapTemplate và repository mapping"]
    G -->|Không| I["Xem ACL, referral, replica, dữ liệu"]
    E --> J["Sửa cấu hình/provisioning hợp lệ"]
    H --> K["Viết regression test"]
    I --> K
    J --> K
~~~

## 12. Phân biệt với các LDAP result code và ngoại lệ khác

| Mã LDAP | Tên LDAP | Ý nghĩa thường gặp | Liên hệ với NameNotFoundException |
| --- | --- | --- | --- |
| **0** | success | Search thành công, có thể trả 0 entry | Không phải lỗi |
| **32** | noSuchObject | Base/entry được yêu cầu không tồn tại hoặc không được thấy theo chính sách server | Thường thành NameNotFoundException |
| **34** | invalidDNSyntax | DN có cú pháp sai | Sửa cú pháp/escaping, không nhầm với 32 |
| **49** | invalidCredentials | Sai thông tin bind | Lỗi xác thực, không phải base |
| **50** | insufficientAccessRights | Không được phép thực hiện thao tác | Kiểm tra ACL |
| **4** | sizeLimitExceeded | Search bị giới hạn số entry | Không kết luận user không tồn tại |
| **3** | timeLimitExceeded | Hết thời gian tìm kiếm | Điều tra filter, index và giới hạn |
| **10** | referral | Yêu cầu được hướng sang server/naming context khác | Cần xử lý referral có kiểm soát |
| **65** | objectClassViolation | Entry CRUD vi phạm schema | Khác lỗi tìm kiếm base |
| **68** | entryAlreadyExists | Thêm entry trùng DN | Khác lỗi không tìm thấy DN |

**NameNotFoundException** ở tầng JNDI thường là biểu hiện của **noSuchObject**, nhưng tên exception và cause chain cần được kiểm tra thay vì suy diễn từ một chuỗi log rút gọn. Spring LDAP có cơ chế dịch exception; tên class ở tầng service có thể khác JNDI gốc.

Ví dụ, việc người dùng không có **mail** không tạo ra **NameNotFoundException** khi tìm entry bằng uid: server có thể trả entry không chứa mail, và mapper cần xử lý attribute vắng. **noSuchAttribute (16)** thường liên quan một thao tác yêu cầu thuộc tính/giá trị không tồn tại, chẳng hạn một số yêu cầu Modify; nó không đồng nghĩa với **noSuchObject (32)**.

## 13. Logging và an toàn bảo mật khi chẩn đoán

Log có ích khi biết **truy vấn được gửi đi đâu**, **base cuối cùng**, **filter** và **mã LDAP trả về**. Nhưng các giá trị đó cũng có thể chứa dữ liệu nhạy cảm. Nên ghi những thông tin đủ để tương quan:

| Trường log | Cách ghi phù hợp |
| --- | --- |
| Request/trace ID | ID kỹ thuật để truy vết request qua nhiều service |
| LDAP endpoint | Tên môi trường/host được cho phép, không kèm thông tin đăng nhập |
| Search base | DN được phép ghi theo chính sách; che phần nhận diện người dùng nếu cần |
| Scope | OBJECT / ONELEVEL / SUBTREE |
| Filter | Dạng có tham số hoặc thuộc tính + loại điều kiện; tránh log dữ liệu cá nhân thô |
| Result | Số entry, LDAP code, loại exception, thời gian thực thi |
| Cause | Giữ trong hệ thống log nội bộ có quyền truy cập phù hợp |

Trong môi trường development, có thể tăng log một cách giới hạn:

~~~yaml
logging:
  level:
    org.springframework.ldap: DEBUG
    org.springframework.data.ldap: DEBUG
~~~

**Không kỳ vọng mọi phiên bản Spring log nguyên filter/DN ở DEBUG**. Khi thêm log riêng, tránh **Context.SECURITY_CREDENTIALS**, password trong properties, bind secret, token hoặc nội dung đầy đủ của entry. Không bật network dump hay JNDI trace có nguy cơ lộ thông tin trong production.

### 13.1. Các nguyên tắc an toàn cần giữ

- Dùng **LDAPS hoặc StartTLS** với xác minh chứng chỉ trước khi gửi simple bind credentials.
- Dùng tài khoản đọc có **quyền tối thiểu**; chỉ dùng tài khoản admin trong lab và khi được phép chẩn đoán ACL.
- Xây LDAP filter bằng **JNDI filter arguments** hoặc **LdapQueryBuilder**, tránh LDAP injection.
- Dùng **LdapName/Rdn** khi tạo DN từ input động; giới hạn các OU mà người dùng được phép chọn.
- Không trả raw DN, LDAP error detail và stack trace trong API phản hồi công khai.
- Không biến lỗi cấu hình thành kết quả “không tồn tại” để rồi xóa/ghi đè dữ liệu liên quan trong hệ thống khác.

## 14. Kiểm thử phân biệt base thiếu với filter không khớp

Một bộ test nên có dữ liệu xác định, ví dụ nhánh **ou=people** chứa **uid=linh** còn **ou=users** không tồn tại. Nếu dùng Spring Boot với LDAP test server nhúng, nạp LDIF tương ứng và cấu hình **ContextSource base=dc=example,dc=org**.

### 14.1. Những ca kiểm thử cốt lõi

| Ca | Base | Filter | Kỳ vọng |
| --- | --- | --- | --- |
| Tìm đúng entry | ou=people | (uid=linh) | Một entry |
| Không khớp filter | ou=people | (uid=khong-co) | Success, 0 entry |
| Base thiếu | ou=users | (uid=linh) | **noSuchObject (32)** hoặc biểu hiện tương ứng theo cấu hình xử lý exception |
| Base lặp suffix | ou=people,dc=example,dc=org được truyền như DN tương đối | (uid=linh) | Phát hiện DN cuối cùng sai và xử lý như lỗi cấu hình |
| DN sai cú pháp | Giá trị DN malformed | Bất kỳ | Lỗi cú pháp DN (có thể ở client trước khi gửi) |
| ACL che entry | ou=people dưới reader bị hạn chế | (uid=linh) | Không suy ra dữ liệu không tồn tại chỉ từ kết quả |
| Đổi nhánh/rename | DN cũ của entry | Tìm/lookup | Phát hiện DN cũ không còn hợp lệ |
| Multi-server | Cùng DN trên hai endpoint | (uid=linh) | Xác minh replication và tính nhất quán thực tế |

### 14.2. Ví dụ integration test với LdapTemplate

Giả định test đã khởi tạo **Spring context**, bean **LdapTemplate**, directory có entry Linh và cơ chế **không bỏ qua NameNotFoundException**:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

class MissingSearchBaseIntegrationTest {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void existingBaseWithUnknownUidReturnsEmptyList() {
        List<String> results = ldapTemplate.search(
            query().base("ou=people")
                   .where("uid").is("khong-co"),
            (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString());

        assertEquals(0, results.size());
    }

    @Test
    void missingBaseRaisesNameNotFound() {
        assertThrows(NameNotFoundException.class, () ->
            ldapTemplate.search(
                query().base("ou=users")
                       .where("uid").is("linh"),
                (AttributesMapper<String>) attrs ->
                    attrs.get("uid").get().toString()));
    }
}
~~~

Đây là mã minh họa đặt **bên trong môi trường integration test đã cấu hình**; trong dự án thật cần thêm Spring test extension và cấu hình server theo framework đang dùng. Nếu template được cấu hình để **bỏ qua lỗi NameNotFoundException**, test kỳ vọng exception không còn phản ánh cấu hình đó; hãy kiểm thử đúng chính sách đang triển khai, đồng thời có một test tầng LDAP/JNDI để xác nhận mã kết quả gốc.

**Mock LdapRepository không đủ** để chứng minh server trả code 32, việc nối DN, ACL và hành vi exception translation. Cần ít nhất một test chạy với directory thật hoặc nhúng. Nếu kiểm thử yêu cầu hành vi riêng của OpenLDAP (ACL, schema, referral), dùng loại server tương ứng thay vì giả định UnboundID/LDAP mock hoàn toàn tương đương.

## 15. Bài tập tự thực hành và câu hỏi ôn tập

**Bài tập 1 — Sửa search base sai**

Cho Spring Boot cấu hình:

~~~yaml
spring:
  ldap:
    base: "dc=example,dc=org"
~~~

Mã truy vấn:

~~~java
query().base("ou=users")
    .where("uid").is("linh");
~~~

Trong directory chỉ tồn tại **ou=people,dc=example,dc=org**. Hãy giải thích vì sao **NameNotFoundException** có thể xuất hiện, sau đó sửa thành **query().base("ou=people")**.

**Bài tập 2 — Phân biệt lỗi và kết quả rỗng**

Chạy hai truy vấn từ phần 4 với cùng bind DN và cùng endpoint:

- Base **ou=people**, filter **(uid=khong-co)**.
- Base **ou=users**, filter **(uid=linh)**.

Ghi lại số entry, result code và thông báo. Giải thích tại sao không nên chuyển cả hai thành **Optional.empty()**.

**Câu hỏi ôn tập:**

1. LDAP **noSuchObject (32)** khác **Search success với 0 entry** như thế nào?
2. Package của **NameNotFoundException** ở JNDI và Spring LDAP khác nhau ở đâu?
3. Vì sao **spring.ldap.base** và **@Entry(base)** có thể cùng góp phần tạo ra search base sai?
4. Khi nào phải kiểm tra **ACL** trước khi kết luận OU/entry không tồn tại?
5. Vì sao chỉ sửa filter hoặc search scope không khắc phục được base DN thiếu?
6. Có nên tạo OU ngay trong catch **NameNotFoundException** của request đọc không? Vì sao?
7. Vì sao kết quả repository rỗng chưa đủ chứng minh người dùng không có trong directory?
8. Kiểm thử nào phải chạy với LDAP server thật hoặc nhúng để tái hiện code 32?

## 16. Ghi nhớ

**NameNotFoundException** khi tìm kiếm LDAP thường chỉ ra rằng **DN dùng làm search base hoặc DN đích không thể được server định vị**, thường liên quan **noSuchObject (32)**. Đây là tình huống khác với một filter không khớp dưới base hợp lệ. Khi gặp lỗi trong ứng dụng Spring Data LDAP, hãy xác minh **endpoint → bind DN → suffix → search base DN cuối cùng → scope → filter → ACL → mapping repository**, dùng **ldapsearch** làm đối chứng và giữ nguyên thông tin nguyên nhân trong log nội bộ. Hãy coi **base cố định không tồn tại** là vấn đề cấu hình/directory cần được khắc phục, thay vì âm thầm trả danh sách rỗng.

## Tài liệu tham khảo

- [RFC 4511 — LDAPv3 Search Operation](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.5): baseObject, scope, filter và SearchResultDone.
- [RFC 4511 — LDAPResult và result codes](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.1.9): mã kết quả LDAP và thông tin matchedDN.
- [Java JNDI — NameNotFoundException](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NameNotFoundException.html): loại ngoại lệ JNDI khi không tìm được tên.
- [Java JNDI — DirContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): search, scope và thuộc tính thư mục.
- [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): ContextSource, LdapTemplate và exception translation.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các API tìm kiếm và xử lý NameNotFoundException.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và LDAP object-directory mapping.
