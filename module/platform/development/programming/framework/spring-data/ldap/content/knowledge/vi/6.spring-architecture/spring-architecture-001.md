# Vai trò của JNDI trong kết nối LDAP từ Java

Trong kiến trúc Spring, ứng dụng thường làm việc với LDAP thông qua **Spring Data LDAP Repository** hoặc **Spring LDAP LdapTemplate**. Tuy nhiên, ở tầng thấp hơn, các thao tác này vẫn cần một cơ chế Java để mở kết nối, xác thực, tìm kiếm và sửa đổi entry trong thư mục. **JNDI (Java Naming and Directory Interface)** chính là giao diện nền tảng giải quyết nhiệm vụ đó.

Bài học tập trung vào vị trí của JNDI trong chuỗi **Spring Data LDAP → Spring LDAP → JNDI → LDAP server**, từ đó giúp người học hiểu vì sao một câu lệnh repository có thể truy cập directory, dữ liệu nào được truyền qua từng tầng, cách sử dụng JNDI trực tiếp khi cần và những điều phải lưu ý về filter, DN, schema, kết nối an toàn.

## 1. Bối cảnh: dữ liệu LDAP được tổ chức thế nào?

LDAP (Lightweight Directory Access Protocol) là giao thức truy cập dịch vụ thư mục. Thay vì tổ chức dữ liệu thành các bảng và hàng như cơ sở dữ liệu quan hệ, LDAP tổ chức các **entry** theo cây phân cấp, gọi là Directory Information Tree (DIT). Mỗi entry có:

- **DN (Distinguished Name):** tên phân biệt duy nhất của entry trong cây, ví dụ **uid=linh,ou=people,dc=example,dc=org**.
- **RDN (Relative Distinguished Name):** thành phần định danh entry ở ngay dưới entry cha, ví dụ **uid=linh**.
- **Attribute:** thuộc tính như **uid**, **cn**, **sn**, **mail**; một số thuộc tính có thể có nhiều giá trị.
- **objectClass:** tập lớp đối tượng xác định entry thuộc loại gì và, theo schema, những thuộc tính nào bắt buộc hoặc được phép có.
- **Schema:** quy tắc về lớp đối tượng, kiểu thuộc tính, cú pháp và ràng buộc dữ liệu của directory.

Ví dụ cây thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   └── uid=an
└── ou=services
    └── cn=readonly
~~~

Một entry minh họa ở dạng LDIF:

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
~~~

Đây là entry hợp lệ về mặt ý tưởng khi LDAP server hỗ trợ các lớp đối tượng trên và các quy tắc schema liên quan. Trong hệ thống thực tế, giá trị DN, objectClass và thuộc tính cần tuân theo schema của directory đang dùng, chẳng hạn OpenLDAP hoặc Active Directory. Không thể giả định mọi directory đều có cùng cấu trúc.

## 2. JNDI là gì và vì sao Java cần JNDI?

**JNDI là API chuẩn của Java để làm việc với dịch vụ tên và dịch vụ thư mục**, không phải tên gọi khác của giao thức LDAP. JNDI cung cấp các interface và đối tượng lập trình; một **service provider** triển khai cách trao đổi với hệ thống cụ thể. Với LDAP, provider LDAP chuyển thao tác của JNDI thành yêu cầu giao thức gửi tới LDAP server.

Các API quan trọng trong JDK:

| Thành phần | Vai trò |
| --- | --- |
| **javax.naming.Context** | Giao diện cơ bản cho tra cứu, liên kết tên và quản lý môi trường context. |
| **javax.naming.directory.DirContext** | Mở rộng Context để đọc/sửa thuộc tính, tìm kiếm và tạo/xóa entry thư mục. |
| **javax.naming.ldap.LdapContext** | Mở rộng DirContext với các khả năng dành riêng cho LDAP như LDAP controls và extended operations. |
| **InitialDirContext / InitialLdapContext** | Khởi tạo context từ cấu hình môi trường và provider tương ứng. |
| **SearchControls / SearchResult** | Xác định phạm vi, giới hạn tìm kiếm và biểu diễn kết quả. |
| **NamingException** | Nhóm ngoại lệ mô tả lỗi đặt tên, xác thực, kết nối, tìm kiếm, schema... |

Các kiểu trên thuộc **javax.naming** do JDK cung cấp (module **java.naming**). Ngay cả khi ứng dụng sử dụng Spring Framework 6 hoặc Spring Boot 3 và Jakarta EE ở các phần khác, các lớp JNDI này vẫn mang package **javax.naming**, không đổi thành **jakarta.naming**.

JNDI chịu trách nhiệm cung cấp API để Java làm việc với directory; nó **không tự định nghĩa schema LDAP**, không bảo đảm dữ liệu hợp lệ nếu server từ chối và cũng không cung cấp mô hình repository của Spring Data.

## 3. JNDI nằm ở đâu trong kiến trúc Spring Data LDAP?

~~~mermaid
flowchart TD
    A["Ứng dụng / service Java"] --> B["Spring Data LDAP Repository"]
    B --> C["Spring LDAP: mapping và LdapTemplate"]
    C --> D["ContextSource: tạo/cấp LDAP context"]
    D --> E["JNDI: DirContext / LdapContext"]
    E --> F["LDAP service provider của JDK"]
    F --> G[("LDAP server: DIT + schema")]
    A -. "Có thể sử dụng trực tiếp" .-> E
~~~

Khi gọi một phương thức repository, các tầng tham gia theo trình tự:

1. **Repository** nhận lời gọi như tìm người dùng theo uid. Spring Data LDAP chuyển ý định đó thành thao tác tìm kiếm LDAP và ánh xạ entry sang đối tượng Java.
2. **Spring LDAP** thực hiện công việc truy cập directory, quản lý context, hỗ trợ tạo query/filter, chuyển đổi kết quả hoặc lỗi; **LdapTemplate** là API thường gặp ở tầng này.
3. **ContextSource** cung cấp context đã được cấu hình máy chủ, base DN và thông tin xác thực. Một triển khai thường dùng là **LdapContextSource**.
4. **JNDI DirContext/LdapContext** gửi thao tác qua LDAP provider: bind, search, lookup, modify, create, delete hoặc rename.
5. **LDAP server** kiểm tra quyền truy cập và schema, thực thi thao tác trên cây directory rồi trả kết quả; các tầng phía trên chuyển kết quả thành đối tượng/ngoại lệ phù hợp cho ứng dụng.

Phân biệt ba cấp độ sử dụng:

| Cấp độ | API tiêu biểu | Khi nào phù hợp |
| --- | --- | --- |
| JNDI trực tiếp | DirContext, LdapContext, SearchControls | Tích hợp thấp tầng, chẩn đoán vấn đề provider, hoặc tính năng LDAP đặc thù. |
| Spring LDAP | LdapTemplate, ContextSource, LdapQuery | Cần chủ động điều khiển filter, scope, thao tác thuộc tính mà vẫn muốn Spring quản lý tài nguyên. |
| Spring Data LDAP | LdapRepository, @Entry, @Attribute | Truy cập entry qua domain object và các phương thức repository thông dụng. |

**Điểm cốt lõi:** Spring Data LDAP cung cấp tầng trừu tượng tiện lợi cho ứng dụng, nhưng không thay thế giao thức LDAP hay loại bỏ vai trò nền tảng của JNDI trong quá trình kết nối.

## 4. Kết nối và tìm kiếm LDAP trực tiếp bằng JNDI

Ví dụ Java sau tra cứu entry có **uid** được cung cấp từ tham số dòng lệnh. Ví dụ sử dụng **LDAPS** để bảo vệ kết nối, một tài khoản chỉ đọc và filter có tham số.

~~~java
import java.util.Hashtable;
import java.util.Objects;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public class JndiLdapLookup {
    public static void main(String[] args) throws NamingException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: JndiLdapLookup <uid>");
        }

        String bindPassword = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "Missing LDAP_BIND_PASSWORD"
        );

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
            "cn=readonly,ou=services,dc=example,dc=org");
        env.put(Context.SECURITY_CREDENTIALS, bindPassword);

        // Thuộc tính timeout này dành cho LDAP provider của JDK.
        env.put("com.sun.jndi.ldap.connect.timeout", "5000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});
        controls.setCountLimit(20);
        controls.setTimeLimit(5000);

        DirContext context = null;
        NamingEnumeration<SearchResult> entries = null;
        try {
            context = new InitialDirContext(env);
            entries = context.search(
                "ou=people,dc=example,dc=org",
                "(uid={0})",
                new Object[] {args[0]},
                controls
            );

            while (entries.hasMore()) {
                SearchResult entry = entries.next();
                System.out.println(entry.getNameInNamespace());
                System.out.println(entry.getAttributes());
            }
        } finally {
            try {
                if (entries != null) {
                    entries.close();
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

**Cách đọc đoạn mã:**

- **INITIAL_CONTEXT_FACTORY** chỉ ra LDAP provider được JDK sử dụng; **PROVIDER_URL** xác định endpoint directory.
- **SECURITY_PRINCIPAL** là DN của tài khoản dùng để bind (xác thực) với LDAP server; nó khác DN của entry cần tìm.
- **InitialDirContext** mở context với cấu hình đã cung cấp. Với **simple bind**, thông tin xác thực sẽ được truyền tới server; vì vậy kết nối phải được bảo vệ bằng TLS và xác minh chứng chỉ.
- **context.search(...)** thực hiện tìm kiếm từ base DN **ou=people,dc=example,dc=org**, theo filter **(uid={0})** và phạm vi **SUBTREE_SCOPE**.
- **SearchControls** giới hạn thuộc tính trả về, số kết quả và thời gian tìm kiếm phía client; server có thể áp dụng thêm giới hạn riêng.
- **NamingEnumeration** và **DirContext** phải được đóng sau khi sử dụng. Đây là tài nguyên có thể gắn với kết nối mạng; không nên giả định garbage collector sẽ giải phóng kịp thời. Trong ví dụ dùng **finally** vì các interface JNDI này không phải kiểu AutoCloseable để đưa trực tiếp vào try-with-resources.

Để chạy được ví dụ, cần một LDAP server thực, entry và tài khoản bind đúng schema/quyền; Java phải tin cậy chứng chỉ TLS do server cung cấp. Tên miền trong mã chỉ là giá trị minh họa.

### Phạm vi tìm kiếm và DN có ý nghĩa gì?

JNDI hỗ trợ ba phạm vi cơ bản khi tìm kiếm:

| Scope | Phạm vi |
| --- | --- |
| **OBJECT_SCOPE** | Chỉ chính entry tại base DN. |
| **ONELEVEL_SCOPE** | Các entry con trực tiếp của base DN. |
| **SUBTREE_SCOPE** | Entry tại base DN và toàn bộ cây con, tùy quyền truy cập. |

Nếu đặt base DN quá rộng (ví dụ ở gốc cả tổ chức) cùng **SUBTREE_SCOPE**, một truy vấn tưởng như đơn giản có thể quét rất nhiều entry. Nên chọn base DN hẹp, chỉ trả về thuộc tính cần dùng, giới hạn kết quả và xem xét phân trang khi directory lớn.

## 5. Filter an toàn và xử lý DN đúng cách

**LDAP filter** dùng để chọn entry theo thuộc tính, còn **DN** xác định vị trí của entry trong cây. Hai loại giá trị này có quy tắc escaping khác nhau.

Ví dụ filter thường gặp:

~~~text
(uid=linh)
(&(objectClass=inetOrgPerson)(uid=linh))
(|(mail=linh@example.org)(mail=an@example.org))
~~~

Tuyệt đối không nối trực tiếp đầu vào người dùng vào filter:

~~~java
// Không an toàn: uid có thể chứa ký tự điều khiển cấu trúc LDAP filter.
String unsafeFilter = "(uid=" + userInput + ")";

// An toàn hơn: JNDI thay tham số và escape giá trị filter.
context.search(baseDn, "(uid={0})",
    new Object[] {userInput}, controls);
~~~

Trong ví dụ JNDI, overload **search(baseDn, filterExpr, filterArgs, controls)** cho provider xử lý escaping của **filterArgs**. Với Spring LDAP, có thể dùng builder filter/query như **LdapQueryBuilder** thay vì tự ghép chuỗi. Khi dựng một **DN/RDN** từ dữ liệu động, cần sử dụng **LdapName** và **Rdn** (thuộc javax.naming.ldap) để mã hóa giá trị tên đúng ngữ cảnh; **escaping filter không thể dùng thay escaping DN**.

Ví dụ dựng RDN từ uid đầu vào:

~~~java
import javax.naming.ldap.Rdn;

String entryDn = new Rdn("uid", userInput).toString()
    + ",ou=people,dc=example,dc=org";
~~~

Trong các ví dụ này, **base DN** là cấu hình cố định được tin cậy. Với base DN do người dùng tác động, cần kiểm soát phạm vi cho phép và xử lý tên theo API chuyên dụng để tránh truy cập nhầm nhánh directory.

## 6. Spring LDAP và Spring Data LDAP sử dụng JNDI như thế nào?

Trong ứng dụng Spring Boot, các thuộc tính LDAP thường được cấu hình ở tầng ứng dụng như sau:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=readonly,ou=services,dc=example,dc=org
~~~

Mật khẩu cần được cấp riêng qua môi trường triển khai, ví dụ biến **SPRING_LDAP_PASSWORD**, hoặc cơ chế quản lý secret tương đương. Certificate/truststore phải được cấu hình phù hợp để xác minh TLS; chỉ đặt URL **ldaps://** chưa đủ để giải quyết mọi vấn đề về chứng chỉ.

Spring LDAP thường tạo **LdapContextSource** từ cấu hình liên quan, sau đó **LdapTemplate** lấy context từ nguồn này để thực thi thao tác. Với base **dc=example,dc=org** đã được đặt ở ContextSource, các đường dẫn đưa vào template thường là **DN tương đối với base**, chẳng hạn **ou=people**; cần tránh vô tình ghép base DN hai lần.

Ví dụ tìm kiếm bằng LdapTemplate:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Ở đây **query().where("uid").is(uid)** giúp xây dựng filter đúng cách; **LdapTemplate** quản lý vòng đời context và chuyển kết quả attributes thành đối tượng trả về. Code giả định các entry phù hợp đều có **cn**, phù hợp với schema nhân sự trong ví dụ. Nếu tìm trên entry tùy ý, cần xử lý trường hợp thiếu thuộc tính.

Tầng Spring Data LDAP bổ sung ánh xạ entry thành domain object:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;

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

    // Constructors, getters, setters được lược bỏ cho ngắn gọn.
}
~~~

**Lưu ý về annotation:** Spring Data LDAP sử dụng các annotation ODM của Spring LDAP trong package **org.springframework.ldap.odm.annotations**, đặc biệt là **@Id** cho DN. Annotation **org.springframework.data.annotation.Id** dành cho các module Spring Data khác không thay thế được annotation ODM này.

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
}
~~~

Ứng dụng có thể gọi **personRepository.findByUid("linh")** mà không cần tự tạo **InitialDirContext**, tự xử lý **NamingEnumeration** hoặc ánh xạ thủ công từng **Attribute**. Tuy nhiên, repository vẫn phụ thuộc cấu hình ContextSource, schema, quyền bind và kết nối qua tầng JNDI. Tùy cấu hình dự án, cần bật repository scanning cho LDAP (chẳng hạn bằng **@EnableLdapRepositories**) để Spring phát hiện interface repository.

Ánh xạ **@Entry** và **@Attribute** không biến LDAP thành cơ sở dữ liệu quan hệ: **DN** vẫn xác định vị trí entry trong cây, **objectClass** vẫn quyết định quy tắc schema và LDAP filter vẫn là cơ chế tìm kiếm. Việc thêm/sửa entry phải bảo đảm thuộc tính bắt buộc, DN hợp lệ và quyền ghi của tài khoản ứng dụng.

## 7. Từ thao tác Java tới thao tác LDAP

Các thao tác thông dụng có thể được nhìn qua ba lớp:

| Mục tiêu | JNDI | Spring LDAP / Spring Data LDAP |
| --- | --- | --- |
| Tìm entry | DirContext.search, lookup, getAttributes | LdapTemplate.search/find hoặc phương thức find... trong repository |
| Tạo entry | DirContext.bind hoặc createSubcontext cùng tập attributes | LdapTemplate.bind; repository.save với entry mới và DN hợp lệ |
| Sửa thuộc tính | DirContext.modifyAttributes | LdapTemplate.modifyAttributes; repository.save tùy trạng thái entity |
| Xóa entry | DirContext.unbind hoặc destroySubcontext | LdapTemplate.unbind; repository.delete |
| Đổi DN/RDN | Context.rename | LdapTemplate.rename hoặc thao tác có hỗ trợ phù hợp |

Ví dụ, sửa thuộc tính **mail** trực tiếp qua JNDI có thể dùng:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@example.org")
    )
};

context.modifyAttributes(
    "uid=linh,ou=people,dc=example,dc=org",
    changes
);
~~~

Đoạn mã giả định biến **context** đã được khởi tạo, tài khoản bind có quyền sửa và thuộc tính **mail** được schema cho phép. Lệnh **REPLACE_ATTRIBUTE** thay toàn bộ giá trị thuộc tính được chỉ định, nên với thuộc tính đa trị phải xác định rõ hành vi mong muốn trước khi dùng. Ngoài ra, **rename** có thể làm thay đổi DN/RDN và có các quy tắc phía server về cập nhật giá trị thuộc tính; không nên xem nó như việc đổi một trường chuỗi thông thường.

## 8. Kết nối an toàn, quản lý tài nguyên và lỗi thường gặp

### Bảo vệ kết nối và danh tính bind

LDAP truyền thao tác liên quan đến người dùng và có thể truyền thông tin xác thực. Khi triển khai:

1. Ưu tiên **LDAPS** hoặc **StartTLS** theo chính sách của directory và hạ tầng. Nếu dùng **simple bind**, chỉ gửi credentials sau khi kết nối TLS đã được thiết lập và xác minh.
2. Xác minh chuỗi chứng chỉ và tên máy chủ; cấu hình truststore phù hợp. Không tắt certificate validation để làm cho môi trường lỗi chứng chỉ hoạt động.
3. Dùng tài khoản dịch vụ có **quyền tối thiểu** (read-only nếu chỉ truy vấn); không ghi password vào mã nguồn, YAML commit lên Git hoặc log.
4. Đặt timeout kết nối/đọc, giới hạn kết quả, phân trang khi cần và kiểm soát số lượng thao tác đồng thời.
5. Với **StartTLS** sử dụng JNDI **LdapContext** và các API **StartTlsRequest/StartTlsResponse**, phải thực hiện nâng cấp TLS và xác minh trước khi xác thực bằng mật khẩu. Không thiết lập simple bind trên kết nối rõ rồi mới bật TLS.

**LDAPS** thường dùng cổng 636; **StartTLS** nâng cấp kết nối LDAP thường bắt đầu ở cổng 389. Cổng thực tế có thể được cấu hình khác.

### Những lỗi cần phân biệt

| Triệu chứng / ngoại lệ điển hình | Nguyên nhân cần kiểm tra |
| --- | --- |
| **AuthenticationException** | DN bind, mật khẩu, phương thức xác thực hoặc chính sách xác thực. |
| **CommunicationException** | Host/port, DNS, mạng, timeout, TLS handshake hoặc chứng chỉ. |
| **NameNotFoundException** | Base DN hoặc DN đích không tồn tại; cũng cần kiểm tra cách dùng DN tương đối. |
| **InvalidSearchFilterException** | Cú pháp LDAP filter sai; tránh nối trực tiếp dữ liệu người dùng. |
| **SchemaViolationException** | objectClass hoặc tập attribute không đáp ứng quy tắc schema. |
| Kết quả tìm kiếm rỗng | Filter/scope/base DN không phù hợp, entry không có thuộc tính yêu cầu hoặc quyền đọc không đủ. |

Khi chẩn đoán lỗi, kiểm tra lần lượt **endpoint và TLS → tài khoản bind → base DN → scope/filter → ACL → schema**. Những lỗi này có thể bị bao bọc trong exception của Spring LDAP, nên thông điệp gốc và mã lỗi LDAP (nếu có) thường hữu ích hơn chỉ nhìn tên exception ở tầng repository. Ghi log đủ thông tin kỹ thuật nhưng phải che thông tin xác thực và dữ liệu nhạy cảm.

### Connection pooling và vòng đời context

Mỗi context có thể gắn với tài nguyên mạng. Với JNDI trực tiếp, người viết mã phải đóng context và kết quả tìm kiếm; không chia sẻ bừa một **DirContext** có trạng thái giữa các luồng. Với Spring LDAP, **ContextSource/LdapTemplate** giúp thống nhất cách lấy và trả tài nguyên. Pooling có thể cải thiện hiệu năng khi được cấu hình phù hợp, nhưng phải xét tính tương thích với TLS/StartTLS, bind identity, giới hạn kết nối và cách provider tái sử dụng context. Không bật pooling chỉ theo thói quen mà thiếu kiểm chứng trong môi trường vận hành thực.

## 9. Kịch bản thực hành: truy vấn tài khoản theo uid

Giả sử ứng dụng quản lý nhân sự cần hiển thị tên và email từ LDAP khi người dùng nhập mã **uid**.

1. **Chuẩn bị directory:** tạo nhánh **ou=people,dc=example,dc=org**, entry mẫu có **uid**, **cn**, **sn**, **mail** và objectClass phù hợp.
2. **Xác nhận kết nối:** cấu hình LDAPS/StartTLS, certificate trust, tài khoản bind có quyền đọc nhánh **ou=people**.
3. **Thử với JNDI:** dùng **InitialDirContext** và **search(..., "(uid={0})", ...)**, chỉ nhận các thuộc tính cần hiển thị. Kiểm tra uid có ký tự đặc biệt để bảo đảm tham số được xử lý đúng.
4. **Chuyển sang Spring LDAP:** cấu hình ContextSource, gọi **LdapTemplate.search** với query builder và đối chiếu tập kết quả với JNDI.
5. **Nâng lên Spring Data LDAP:** ánh xạ **Person**, tạo **PersonRepository**, gọi **findByUid**. Kiểm tra DN/attribute đã được ánh xạ đúng.
6. **Kiểm thử tình huống lỗi:** uid không tồn tại, bind sai mật khẩu, sai base DN, certificate không hợp lệ và người dùng không đủ quyền đọc. Xác minh ứng dụng xử lý ngoại lệ rõ ràng, không để lộ password.

Nên có **integration test với LDAP server kiểm thử và dữ liệu LDIF xác định trước**. Unit test mock repository chỉ xác minh logic ứng dụng, chưa thể khẳng định filter, mapping, schema và cơ chế xác thực hoạt động đúng với directory thực.

**Câu hỏi tự kiểm tra:**

- Vì sao JNDI vẫn xuất hiện trong một ứng dụng chỉ khai báo **LdapRepository**?
- Khác biệt giữa **base DN**, **RDN** và **LDAP filter** là gì?
- Điều gì xảy ra nếu dùng **SUBTREE_SCOPE** từ một base DN quá rộng?
- Vì sao phải dùng tham số filter hoặc query builder khi tìm uid từ dữ liệu người dùng?
- Khi gặp **AuthenticationException**, nên kiểm tra tầng nào trước? Khi gặp **SchemaViolationException** thì sao?

## 10. Ghi nhớ

JNDI là **cầu nối API của Java tới LDAP provider**, cho phép ứng dụng làm việc với directory thông qua **DirContext/LdapContext**. Spring LDAP xây trên cơ chế đó để quản lý context và cung cấp các thao tác dễ dùng hơn; Spring Data LDAP tiếp tục bổ sung **repository và ánh xạ entry thành đối tượng Java**. Hiểu tầng JNDI giúp giải thích hành vi của truy vấn repository, lựa chọn base DN/filter đúng, xử lý sự cố kết nối và triển khai CRUD tuân thủ schema, quyền truy cập và yêu cầu bảo mật.
