# Vai trò của LdapTemplate trong Spring LDAP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `LdapTemplate` là API trung tâm của **Spring LDAP core** khi làm việc với LDAP qua Java.
- Mô tả mối liên hệ giữa `ContextSource`, JNDI `DirContext`, `LdapTemplate`, LDAP server và các đối tượng ánh xạ kết quả.
- Dùng `search`, `lookup`, `modifyAttributes` và các thao tác quản lý entry đúng với DN, filter, schema và quyền truy cập.
- Chọn `AttributesMapper`, `ContextMapper`, `LdapQuery` hoặc các API thấp hơn tùy nhu cầu.
- Phân biệt vai trò của `LdapTemplate` với `LdapClient`, Spring Data LDAP repository và Spring Security LDAP.
- Áp dụng nguyên tắc escape filter/DN, giới hạn tìm kiếm, TLS, pooling, xử lý lỗi và kiểm thử tích hợp để thao tác directory an toàn.

Bài thuộc chương **LdapTemplate** của module **SPRING_LDAP**. Trong module này, bạn học từ DN, schema, LDAP filter và tìm kiếm đến thao tác entry, cấu hình `ContextSource`, xác thực, TLS và kiểm thử. `LdapTemplate` kết nối những khái niệm đó trong một API thực dụng của Spring LDAP.

## 1. Tại sao cần LdapTemplate?

LDAP là dịch vụ thư mục lưu dữ liệu theo **Distinguished Name (DN)** và các attribute. Một entry nhân viên có thể trông như sau:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Giả sử ứng dụng nhân sự cần tìm nhân viên bằng `uid`, đọc `cn` và `mail`, cập nhật `telephoneNumber`, hoặc đưa nhân viên vào một nhóm. Nếu dùng **JNDI thuần**, lập trình viên thường phải:

1. Chuẩn bị môi trường kết nối và credentials.
2. Tạo `DirContext`.
3. Tạo filter, DN, `SearchControls` và thực hiện thao tác.
4. Duyệt `NamingEnumeration` nếu truy vấn trả nhiều entry.
5. Chuyển `Attributes` thành DTO/entity.
6. Đóng enumeration, context và xử lý `NamingException` ngay cả khi thao tác thất bại.

Các bước quản lý tài nguyên và dịch ngoại lệ thường lặp lại. **`LdapTemplate` đưa những phần lặp đó vào một template**, để code ứng dụng tập trung vào **truy vấn nào cần chạy** và **kết quả phải được ánh xạ ra sao**.

Ví dụ ngắn:

~~~java
List<String> names = ldapTemplate.search(
    "ou=people",
    "(uid=lan)",
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
~~~

Ví dụ giả định tài khoản dịch vụ được đọc thuộc tính `cn` và entry khớp có `cn`. Trong code có input từ người dùng, cần tạo filter bằng `EqualsFilter` hoặc builder an toàn như các ví dụ phía sau.

**Lợi ích chính của `LdapTemplate` không phải biến LDAP thành SQL hay giấu hoàn toàn DN.** Nó là một lớp tiện ích cho các thao tác LDAP, quản lý context và callback một cách nhất quán trong ứng dụng Spring.

## 2. LdapTemplate nằm ở đâu trong kiến trúc?

~~~mermaid
flowchart TB
    App["Controller / Service nghiệp vụ"]
    Template["LdapTemplate<br/>search · lookup · modifyAttributes · bind · unbind"]
    Mapper["AttributesMapper / ContextMapper<br/>Chuyển entry thành Java object"]
    Context["ContextSource<br/>Cấu hình URL · base DN · credentials"]
    JNDI["JNDI DirContext<br/>Kết nối và thao tác LDAP"]
    Server[("LDAP server<br/>Entry · schema · ACL · index")]
    App --> Template
    Template --> Mapper
    Template --> Context
    Context --> JNDI
    JNDI <--> Server
    Mapper --> App
~~~

Trong luồng này:

- **Service** mô tả yêu cầu nghiệp vụ, chẳng hạn “tìm hồ sơ theo mã nhân viên”.
- **`LdapTemplate`** thực thi thao tác tìm kiếm/đọc/sửa bằng API Spring LDAP.
- **`ContextSource`** cung cấp context được cấu hình theo server, base DN và tài khoản kết nối.
- **JNDI LDAP provider** thực hiện yêu cầu tới LDAP server.
- **LDAP server** kiểm tra schema, search filter, ACL, matching rule và quyền bind.
- **Mapper** quyết định cách chuyển dữ liệu directory thành giá trị Java.

Đối tượng `LdapTemplate` thường được khai báo thành **bean dùng lại** và inject vào các service. Nó không lưu “người dùng đang đăng nhập” trong mỗi lời gọi `search`. Danh tính thực hiện thao tác tùy thuộc context được lấy qua `ContextSource` và cách luồng xác thực được cấu hình.

### 2.1. Mối quan hệ với JNDI

`LdapTemplate` được xây trên API JNDI, nhưng code ứng dụng thường không cần giữ `DirContext` hoặc tự đóng nó cho mỗi truy vấn. Template quản lý phần vòng đời tài nguyên mà các operation của nó sở hữu.

Với callback, code ứng dụng vẫn phải tuân theo hợp đồng API: nếu tự tạo tài nguyên độc lập, stream hoặc một enumeration bên ngoài vòng đời template thì chính code đó phải quản lý phần tài nguyên ấy. Không mặc định mọi object Java do callback tạo sẽ được Spring tự giải phóng.

### 2.2. Mối quan hệ với ContextSource

`ContextSource` của Spring LDAP gần với vai trò `DataSource` trong JDBC: nó cung cấp context truy cập directory. `LdapTemplate` nhận một `ContextSource` và dùng nó khi gọi các operation.

Cấu hình sai **URL, base DN, bind DN hoặc credential** sẽ ảnh hưởng kết quả template dù cú pháp Java đúng. Vì vậy cần biết chính xác:

~~~text
LDAP endpoint:       ldaps://ldap.example.org:636
ContextSource base:  dc=example,dc=org
Service bind DN:     uid=directory-reader,ou=services,dc=example,dc=org
Search base:         ou=people
Full target DN:      uid=lan,ou=people,dc=example,dc=org
~~~

Khi `ContextSource` đã đặt base `dc=example,dc=org`, nhiều API của `LdapTemplate` nhận tên **tương đối** với base đó. Truyền lại full DN vào vị trí yêu cầu relative DN có thể làm đường dẫn bị nhân đôi hoặc gây lỗi không tìm thấy entry.

## 3. Cấu hình LdapTemplate trong Spring Boot

Với ứng dụng Spring Boot có hỗ trợ LDAP phù hợp, cấu hình kết nối có thể là:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # Cấp spring.ldap.password qua secret manager hoặc biến môi trường.
~~~

Một lựa chọn dependency khi muốn dùng Spring LDAP và hạ tầng Spring Data LDAP do Boot quản lý:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Nếu chỉ cần Spring LDAP core mà không cần repository, có thể dùng dependency `org.springframework.ldap:spring-ldap-core` với các dependency Spring tương thích; khả năng auto-configuration phụ thuộc phiên bản và điều kiện của Spring Boot. Không nhất thiết phải có `spring-data-ldap` hay `spring-security-ldap` để gọi `LdapTemplate`.

Với classpath và cấu hình phù hợp, Spring Boot có thể tạo bean `ContextSource` và `LdapTemplate`. Service nhận template qua constructor:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmployeeDirectoryService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }
}
~~~

Không nên tạo `new LdapTemplate(...)` mỗi khi có HTTP request nếu đã có bean được quản lý sẵn. Reuse bean giúp cấu hình kết nối, xử lý ngoại lệ và các chính sách truy cập nhất quán.

### 3.1. Cấu hình thủ công trong Spring Framework

Khi không dựa vào auto-configuration, có thể tự tạo hai bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    LdapContextSource ldapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
            "uid=directory-reader,ou=services,dc=example,dc=org"
        );
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Đây là ví dụ cấu hình tối giản. Trong production, secret phải được cấp/luân chuyển bằng cơ chế được quản lý; chứng chỉ máy chủ phải được xác minh và quyền tài khoản bind phải được giới hạn. Khi bean được Spring quản lý, lifecycle của `LdapContextSource` do container đảm nhiệm. Nếu tự khởi tạo bên ngoài container, cần tuân theo hợp đồng khởi tạo của phiên bản Spring LDAP, chẳng hạn `afterPropertiesSet()`.

### 3.2. Không nhầm auto-configuration và bean tự tạo

Một số điều kiện auto-configuration có thể **back off** khi ứng dụng đã khai báo bean cùng loại. Nếu service không inject được `LdapTemplate`, hãy kiểm tra dependency, configuration properties, bean hiện có và điều kiện auto-configuration của phiên bản đang dùng. Không cố tạo nhiều template trỏ tới những base/server khác nhau mà không định danh bean rõ ràng.

## 4. Các nhóm thao tác LdapTemplate

`LdapTemplate` có API cho nhiều phép thao tác directory. Các tên sau mô tả nhóm chức năng điển hình, không có nghĩa mọi overload giống nhau giữa các phiên bản:

| Nhóm | API điển hình | Mục đích |
| --- | --- | --- |
| Tìm kiếm | `search(...)` | Tìm nhiều entry theo search base, scope và filter |
| Đọc entry theo DN | `lookup(...)` | Lấy entry đã biết DN và ánh xạ dữ liệu |
| Thêm entry | `bind(...)` | Tạo một entry mới trong directory |
| Sửa thuộc tính | `modifyAttributes(...)` | Thêm, thay thế hoặc xóa giá trị attribute |
| Xóa entry | `unbind(...)` | Xóa entry theo DN, phải tuân thủ quy tắc directory |
| Đổi tên/di chuyển | `rename(...)` | Thay DN/RDN theo khả năng và quyền của server |
| Xác thực ở mức LDAP | `authenticate(...)` | Kiểm tra thông tin đăng nhập trong một số luồng thao tác LDAP |
| Thao tác thấp hơn | Các callback/execute tùy API | Khi cần kiểm soát `DirContext` chi tiết hơn |

**Lưu ý thuật ngữ:** `bind` trong quản lý dữ liệu có thể nghĩa là **thêm entry**; còn “LDAP bind authentication” nghĩa là **xác thực danh tính kết nối** bằng credential. Không nhầm hai tác vụ này. Thêm entry không tự xác thực người dùng web.

Sự đầy đủ và sự hợp lệ của thao tác vẫn phụ thuộc server: schema có thể yêu cầu objectClass/attribute bắt buộc, ACL có thể cấm sửa/xóa, và rename/move có thể có giới hạn.

## 5. Search: thao tác thường dùng nhất

Một yêu cầu tìm kiếm gồm:

1. **Search base**: bắt đầu tại nhánh nào.
2. **Search scope**: xét base, các con trực tiếp hay toàn bộ cây con.
3. **Filter**: entry nào khớp điều kiện.
4. **Returning attributes**: cần lấy thuộc tính nào.
5. **Mapper**: dữ liệu kết quả chuyển thành kiểu Java nào.

Ví dụ dùng `LdapTemplate` để tìm nhân viên theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class EmployeeSearchService {

    public record EmployeeSummary(
        String uid,
        String commonName,
        String email
    ) {}

    private final LdapTemplate ldapTemplate;

    public EmployeeSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<EmployeeSummary> findByUid(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"}
        );
        controls.setCountLimit(50);
        controls.setTimeLimit(2_000);

        String filter = new EqualsFilter("uid", uid).encode();

        return ldapTemplate.search(
            "ou=people",
            filter,
            controls,
            (AttributesMapper<EmployeeSummary>) attrs ->
                new EmployeeSummary(
                    required(attrs, "uid"),
                    required(attrs, "cn"),
                    optional(attrs, "mail")
                )
        );
    }

    private static String required(Attributes attrs, String name)
            throws javax.naming.NamingException {

        Attribute value = attrs.get(name);
        if (value == null || value.size() == 0) {
            throw new IllegalArgumentException(
                "Thiếu thuộc tính LDAP: " + name
            );
        }
        return (String) value.get();
    }

    private static String optional(Attributes attrs, String name)
            throws javax.naming.NamingException {

        Attribute value = attrs.get(name);
        if (value == null || value.size() == 0) {
            return null;
        }
        return (String) value.get();
    }
}
~~~

Ví dụ giả định thuộc tính `uid` và `cn` là những chuỗi có thể đọc; `mail` là tùy chọn; cấu hình `ContextSource.base` bằng `dc=example,dc=org`. Nếu một attribute có kiểu binary hoặc nhiều giá trị, phải thay cách map tương ứng.

### 5.1. Vì sao dùng EqualsFilter?

Một lỗi phổ biến là nối chuỗi đầu vào:

~~~java
String filter = "(uid=" + username + ")";
~~~

Nếu `username` chứa `*`, `(`, `)` hoặc dấu gạch chéo ngược, filter có thể thay đổi ý nghĩa hoặc bị khai thác để mở rộng điều kiện tìm kiếm. `EqualsFilter` mã hóa **giá trị input** theo cú pháp LDAP filter:

~~~java
String filter = new EqualsFilter("uid", "lan*").encode();
// Dấu * thuộc giá trị được escape để không trở thành wildcard.
~~~

Khi muốn substring/prefix search một cách có chủ đích, hãy dùng query builder hoặc encode riêng phần dữ liệu rồi thêm wildcard do code kiểm soát. **Escape filter khác escape DN**: dấu phẩy trong DN, DN/RDN và các ký tự của filter có những quy tắc khác nhau.

### 5.2. Vì sao SearchControls quan trọng?

`SearchControls` thuộc JNDI (`javax.naming.directory`), không phải một class riêng của Spring. Nó xác định phạm vi và các giới hạn tìm kiếm:

| Scope | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `OBJECT_SCOPE` | Chỉ entry tại search base | Kiểm tra một DN đã biết |
| `ONELEVEL_SCOPE` | Chỉ các entry con trực tiếp | Liệt kê entry trong một OU phẳng |
| `SUBTREE_SCOPE` | Base và mọi entry hậu duệ | Tìm người dùng qua các OU lồng nhau |

Ở ví dụ trên, `SUBTREE_SCOPE` phù hợp nếu người dùng nằm cả ở `ou=people` và những OU bên dưới như `ou=engineering,ou=people`. `ONELEVEL_SCOPE` có thể bỏ sót các entry sâu hơn dù filter đúng.

`setCountLimit(50)` giới hạn số entry trả về theo yêu cầu; nó **không** chứng minh chỉ có 50 entry khớp hoặc server chỉ xét 50 entry. `setTimeLimit(2_000)` là giới hạn thời gian tìm kiếm của JNDI, **khác** với timeout kết nối/TLS. Khi giới hạn bị vượt, provider có thể báo ngoại lệ hoặc kết quả không đầy đủ tùy hành vi server.

### 5.3. Search không tương đương SQL query

LDAP filter ví dụ:

~~~ldap
(&(objectClass=inetOrgPerson)(|(sn=Nguyen)(cn=Lan*)))
~~~

Có nghĩa: entry thuộc `inetOrgPerson` và `sn=Nguyen` **hoặc** `cn` bắt đầu bằng `Lan`. Thứ tự, mức độ tối ưu, matching rule của attribute và các index đều do server quyết định.

Đừng cố suy từ syntax `(cn=Lan*)` sang SQL `LIKE 'Lan%'` một cách máy móc. LDAP là directory với schema, DN, RDN, scope và ACL; nó không có cùng mô hình join, quan hệ hoặc transaction như RDBMS.

## 6. Mapper: đầu ra của search là Java object nào?

`LdapTemplate` không tự biết nghiệp vụ muốn object `EmployeeSummary`, `GroupView` hay danh sách chuỗi. Bạn truyền callback mapper để quyết định cách xử lý.

### 6.1. AttributesMapper: chỉ cần thuộc tính

`AttributesMapper<T>` nhận `Attributes` của một entry. Nó phù hợp khi cần chuyển `cn`, `uid`, `mail` thành DTO nhẹ:

~~~java
List<String> emails = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs -> {
        var mail = attrs.get("mail");
        return mail == null ? null : (String) mail.get();
    }
);
~~~

Khi mapper có thể trả `null`, hãy xác định cách ứng dụng xử lý giá trị đó; dữ liệu được trả có thể cần lọc hoặc biểu diễn thành `Optional`/DTO theo hợp đồng. Không nên coi thuộc tính thiếu là điều bất khả thi chỉ vì schema thông dụng có `mail`.

Một số attribute là **binary** hoặc **multivalued**. `Attribute.get()` chỉ lấy **một** giá trị; muốn lấy toàn bộ, dùng `Attribute.getAll()` và đóng `NamingEnumeration` nếu code trực tiếp sở hữu nó.

### 6.2. ContextMapper: khi cần DN

Nếu kết quả cần cả DN hoặc các tiện ích thao tác context, dùng `ContextMapper<T>` và `DirContextOperations`:

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

record DirectoryIdentity(String dn, String uid) {}

public List<DirectoryIdentity> findIdentities(
        LdapTemplate template, String uid) {

    return template.search(
        "ou=people",
        new EqualsFilter("uid", uid).encode(),
        (ContextMapper<DirectoryIdentity>) context -> {
            DirContextOperations entry = (DirContextOperations) context;
            return new DirectoryIdentity(
                entry.getDn().toString(),
                entry.getStringAttribute("uid")
            );
        }
    );
}
~~~

`DirContextOperations` là abstraction của Spring LDAP thường được hiện thực qua `DirContextAdapter`. `getDn()` cung cấp DN theo ngữ cảnh của API; phải xác minh nó là DN tương đối hay đầy đủ trong cấu hình thực tế trước khi lưu làm định danh bên ngoài hệ thống.

### 6.3. Khi nào dùng ODM thay vì mapper?

Spring LDAP còn có **Object-Directory Mapping (ODM)** với annotation như `@Entry`, `@Id`, `@Attribute`. Nếu nhiều service truy cập một loại entry ổn định, ODM giảm số mapper thủ công. Spring Data LDAP có thể đặt `LdapRepository` phía trên ODM để cung cấp repository API.

Tuy vậy, **ODM không phải điều kiện để dùng `LdapTemplate`**. Khi truy vấn linh hoạt, làm việc với nhiều objectClass hoặc cần kiểm soát DN/filter/attributes đặc biệt, mapper trực tiếp có thể đơn giản và rõ ràng hơn.

## 7. Lookup: đọc một entry khi đã biết DN

`lookup` được dùng khi ứng dụng đã biết tên entry, chẳng hạn:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Nếu `ContextSource` có base `dc=example,dc=org`, DN tương đối là `uid=lan,ou=people`.

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public String readCommonName(LdapTemplate template, String uid) {
    Name dn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", uid)
        .build();

    return template.lookup(
        dn,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
    );
}
~~~

**Vì sao dùng `LdapNameBuilder`?** Giá trị của RDN có thể chứa dấu phẩy, dấu cộng, dấu cách đầu/cuối hoặc ký tự cần escape. Builder làm việc với thành phần DN thay vì ghép chuỗi `"uid=" + uid + ",ou=people"` một cách dễ sai. Đây là **DN escaping**, độc lập với `EqualsFilter` dùng cho filter.

`lookup` phù hợp khi **đã biết DN**. Nếu bạn chỉ biết username mà không biết DN hoặc người dùng phân tán nhiều OU, hãy search theo thuộc tính định danh trong scope thích hợp, rồi sử dụng DN thực của entry được tìm thấy.

Không được biến mọi ngoại lệ lookup thành `null` để kết luận user không tồn tại. `NameNotFoundException`, lỗi quyền, timeout, TLS và lỗi bind có các nguyên nhân và cách xử lý khác nhau.

## 8. Thao tác ghi: modify, bind, unbind và rename

`LdapTemplate` không chỉ là công cụ tìm kiếm. Nó còn cho phép quản lý entry, với điều kiện **LDAP server chấp nhận và tài khoản bind có quyền phù hợp**.

### 8.1. Cập nhật một thuộc tính bằng modifyAttributes

Ví dụ thay `telephoneNumber` của nhân viên:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void updatePhone(
        LdapTemplate template,
        String uid,
        String phone
) {
    Name dn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", uid)
        .build();

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", phone)
        )
    };

    template.modifyAttributes(dn, changes);
}
~~~

Ví dụ giả định `uid` là thành phần RDN ở đúng OU, `telephoneNumber` có trong schema hoặc được phép cập nhật, và tài khoản kết nối có quyền ghi. `REPLACE_ATTRIBUTE` thay giá trị thuộc tính; khi nghiệp vụ yêu cầu thêm/xóa một giá trị trong attribute nhiều giá trị, cần dùng phép sửa phù hợp (`ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE`), tránh thay cả tập giá trị ngoài ý muốn.

**Không dùng string DN trực tiếp từ HTTP request để sửa entry.** Hãy xác định entry theo định danh và kiểm tra quyền nghiệp vụ trước khi xây DN/truy cập directory.

### 8.2. Thêm entry bằng bind

Trong nhóm API quản lý dữ liệu của Spring LDAP, `bind` có thể tạo entry mới. Mẫu minh họa dùng đối tượng JNDI `Attributes`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void createPerson(
        LdapTemplate template,
        String uid,
        String commonName,
        String surname
) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

    Attributes attrs = new BasicAttributes(true);

    Attribute classes = new BasicAttribute("objectClass");
    classes.add("top");
    classes.add("person");
    classes.add("organizationalPerson");
    classes.add("inetOrgPerson");

    attrs.put(classes);
    attrs.put("uid", uid);
    attrs.put("cn", commonName);
    attrs.put("sn", surname);

    template.bind(dn, null, attrs);
}
~~~

Ví dụ dùng `BasicAttributes(true)` để tên attribute ID trong collection không phân biệt chữ hoa/thường. Nó **không thay đổi equality matching rule của LDAP server**. Entry còn phải tuân thủ objectClass, RDN, thuộc tính bắt buộc, tính hợp lệ của dữ liệu và ACL. Việc một server cho phép tạo entry `inetOrgPerson` dưới `ou=people` phụ thuộc directory và schema triển khai.

Trong LDAP, tên entry đã tồn tại hoặc vi phạm ràng buộc thường khiến server từ chối thao tác; template không tự biến thao tác thành “upsert” như một số ORM.

### 8.3. Xóa và đổi DN

- `unbind(...)` dùng để xóa một entry theo DN. Một số server không cho xóa entry còn con hoặc áp dụng ACL đặc thù.
- `rename(...)` thay DN/RDN theo khả năng server, có thể ảnh hưởng các thuộc tính đặt tên và tham chiếu trong directory.
- Không coi đổi `cn` hoặc `uid` bằng `modifyAttributes` là tương đương với đổi DN. Nếu `uid` thuộc RDN của entry, đổi RDN cần một thao tác rename phù hợp.

**Đặc biệt:** LDAP không cung cấp giao dịch nhiều entry tương đương transaction trong cơ sở dữ liệu quan hệ theo cách mặc định. Nếu tạo entry rồi thêm vào nhóm và bước thứ hai thất bại, cần thiết kế bù trừ, kiểm toán hoặc cơ chế idempotent thích hợp.

## 9. LdapTemplate với LdapClient, Spring Data LDAP và Spring Security LDAP

| Công cụ | Khi nào phù hợp | Điều không nên mặc định |
| --- | --- | --- |
| **`LdapTemplate`** | Cần search, lookup, CRUD entry, mapper/callback với quản lý JNDI context | Không tự tổ chức HTTP login/session |
| **`LdapClient`** | Muốn fluent API cho các thao tác LDAP trong Spring LDAP core | Không phải repository, không tự cung cấp ODM như `LdapTemplate` |
| **Spring LDAP ODM** | Có entity LDAP ổn định và cần ánh xạ bằng annotation | Không thay đổi schema và ACL của server |
| **Spring Data LDAP** | Muốn `LdapRepository` cho entity và các thao tác repository | Không phải `JpaRepository` hay công cụ authentication |
| **Spring Security LDAP** | Đăng nhập/bind authentication, lấy authorities và bảo vệ endpoint | Không cung cấp API quản lý entry nghiệp vụ tổng quát như template |

### Ví dụ phối hợp ba mục đích

Một ứng dụng nội bộ có ba service:

~~~text
SecurityConfiguration
  -> Spring Security LDAP: xác thực và ánh xạ quyền

EmployeeProfileService
  -> LdapTemplate: đọc thuộc tính hồ sơ theo uid/DN

GroupAdministrationService
  -> LdapTemplate hoặc repository: cập nhật group/member
~~~

Chúng có thể truy cập cùng LDAP server nhưng dùng **quyền tài khoản, search base và giới hạn** khác nhau. Một tài khoản dùng tìm kiếm thông tin nhân viên nên có quyền đọc tối thiểu; thao tác sửa group cần quyền ghi phù hợp.

Không dùng kết quả `ldapTemplate.search("(uid=lan)")` làm bằng chứng người dùng đã xác thực. Một entry có thể tồn tại mà password sai, tài khoản bị khóa hoặc người dùng không có quyền vào ứng dụng.

### Khi nào template authenticate có ích?

`LdapTemplate` có các khả năng xác thực ở mức LDAP cho những luồng cụ thể. Tuy nhiên đối với ứng dụng web dùng Spring Security, cách thích hợp thường là **Spring Security LDAP** để tích hợp kết quả bind với `SecurityContext`, cơ chế đăng nhập, authorities và phân quyền endpoint.

Tài khoản bind dịch vụ dùng bởi `LdapTemplate` để đọc entry cũng **không đồng nghĩa** với danh tính người dùng đang đăng nhập vào HTTP session.

## 10. Xử lý ngoại lệ và quản lý tài nguyên

Khi dùng JNDI trực tiếp, bạn thường xử lý `javax.naming.NamingException`. Spring LDAP chuyển đổi nhiều lỗi JNDI thành hệ thống ngoại lệ riêng theo cơ chế của Spring, giúp code ứng dụng không phải khai báo checked exception JNDI ở mọi service.

Điều này **không có nghĩa mọi lỗi LDAP đều trở thành một loại exception**. Hãy phân biệt:

| Nhóm lỗi | Biểu hiện điển hình | Hướng xử lý |
| --- | --- | --- |
| Entry không tồn tại | Lookup DN sai hoặc entry đã bị xóa | Xử lý “not found” theo nghiệp vụ |
| Filter/DN sai | Không parse được filter, naming error | Sửa cách tạo filter/DN, kiểm tra input |
| Schema violation | Thiếu `sn`, sai objectClass/kiểu thuộc tính | Kiểm tra schema và giá trị muốn ghi |
| Quyền không đủ | Không được đọc hoặc modify entry | Kiểm tra ACL và danh tính context |
| Bind thất bại | Credentials không hợp lệ hoặc chính sách account | Kiểm tra cấu hình hoặc luồng authentication |
| Kết nối/TLS | Server unreachable, timeout, certificate lỗi | Kiểm tra DNS, port, truststore và TLS |
| Size/time limits | Kết quả một phần hoặc ngoại lệ giới hạn | Giảm scope, filter, điều chỉnh giới hạn/paging |

**Tránh cách xử lý sau:**

~~~java
try {
    return ldapTemplate.search(...);
} catch (Exception ignored) {
    return List.of(); // Sai nếu biến mọi lỗi thành "không có dữ liệu"
}
~~~

Nếu operation lỗi do TLS hoặc thiếu quyền, trả danh sách rỗng có thể khiến nghiệp vụ kết luận sai rằng người dùng không tồn tại. Thay vào đó, phân loại lỗi và trả trạng thái phù hợp ở tầng ứng dụng, đồng thời ghi log kỹ thuật có kiểm soát.

### 10.1. Đừng log thông tin nhạy cảm

- Không log `userPassword`, password bind hoặc token.
- Hạn chế log full DN, số điện thoại, email và dữ liệu định danh nhạy cảm nếu không có nhu cầu vận hành.
- Không ghi toàn bộ môi trường JNDI vào log vì nó có thể chứa `Context.SECURITY_CREDENTIALS`.
- Đối với lỗi xác thực, không để lộ chi tiết tài khoản hoặc schema nội bộ cho client.

### 10.2. Template giảm lỗi quản lý tài nguyên nhưng không loại bỏ mọi việc vận hành

`LdapTemplate` hỗ trợ đóng và quản lý context/enumeration theo các thao tác chuẩn mà nó cung cấp. Tuy nhiên hiệu năng truy vấn còn phụ thuộc vào server, schema và connection pool. Nếu mapper của ứng dụng tự mở một kết nối khác hoặc giữ stream/tài nguyên ngoài vòng đời callback, ứng dụng vẫn phải quản lý các tài nguyên đó.

## 11. Hiệu năng: điều gì LdapTemplate giúp và điều gì không?

`LdapTemplate` giảm boilerplate JNDI, cung cấp API dễ dùng và hỗ trợ mapping. Nó **không** tự đảm bảo một filter quá rộng sẽ nhanh.

Các yếu tố quan trọng gồm:

- **Search base và scope**: tìm dưới `ou=people` thay vì toàn `dc=example,dc=org` khi chỉ cần nhân viên.
- **Filter và index**: equality trên `uid` thường khác với substring `(cn=*a*)`; server phải có index phù hợp nếu cần tối ưu.
- **Số attributes trả về**: chỉ yêu cầu `uid`, `cn` khi UI không cần ảnh, certificate hoặc thuộc tính lớn.
- **Giới hạn kết quả**: đặt `countLimit`, `timeLimit` và phương án paging theo hợp đồng nghiệp vụ.
- **Độ lớn dữ liệu map**: tạo hàng chục nghìn DTO có chi phí bộ nhớ và CPU.
- **Tải đồng thời và pooling**: tăng pool vô hạn có thể tăng áp lực lên LDAP server thay vì cải thiện độ trễ.
- **TLS và mạng**: LDAPS/StartTLS cần cấu hình chứng chỉ đúng, timeout phù hợp và tái sử dụng kết nối có kiểm soát.

### 11.1. Prefix và substring không tương đương

Ví dụ:

~~~ldap
(uid=lan)
(cn=Lan*)
(cn=*Lan*)
~~~

Filter đầu là equality; các filter sau là substring. Chúng có độ chọn lọc và khả năng dùng index khác nhau. Dấu `*` không phải “tìm kiếm thông minh”; `(cn=*)` còn là phép kiểm tra presence, thường có thể trả rất nhiều entry.

Đối với màn hình gợi ý, nên giới hạn prefix quá ngắn, debounce input, đặt số kết quả tối đa và đo hiệu năng trên server đại diện. Template không tự nhận biết một truy vấn có nguy cơ quá tải nếu ứng dụng truyền filter không được kiểm soát.

### 11.2. Paging và kết quả đầy đủ

Khi cần duyệt nhiều entry, LDAP có cơ chế Simple Paged Results (RFC 2696) nếu server/client hỗ trợ. Paging quản lý quá trình nhận kết quả, **không phải** lời đảm bảo query sẽ ít tốn tài nguyên hoặc không có giới hạn phía server.

Đừng coi `countLimit(100)` là phân trang. Nó chỉ giới hạn số entry được trả về theo một yêu cầu, không cung cấp cơ chế lấy trang tiếp theo hay chứng minh toàn bộ tập kết quả chỉ có 100 entry.

## 12. Bảo mật khi sử dụng LdapTemplate

### 12.1. Bảo vệ kênh truyền

Cấu hình `ldaps://` hoặc StartTLS phù hợp với directory, xác thực certificate chain và hostname, quản lý truststore đúng cách. Không tắt kiểm tra chứng chỉ để “chữa” lỗi `SSLHandshakeException`.

Secret manager giúp bảo vệ mật khẩu khi lưu/cấp cho ứng dụng, nhưng **không mã hóa dữ liệu trên đường truyền** nếu kết nối LDAP không được bảo vệ.

### 12.2. Phân quyền cho tài khoản dịch vụ

Không cấp quyền admin toàn directory cho một `ContextSource` chỉ vì có nhiều thao tác cần làm. Nếu phải sửa nhóm hoặc quản lý người dùng, cân nhắc các kết nối/tài khoản có ACL riêng và cơ chế kiểm soát quyền ở tầng ứng dụng.

Khi dùng `modifyAttributes`, quyền của người gọi API **và** quyền của tài khoản bind thực hiện thao tác LDAP là hai lớp kiểm soát khác nhau. Người dùng đăng nhập thành công không tự động được sửa toàn bộ directory.

### 12.3. Pooling và danh tính context

Connection pooling phải được cấu hình phù hợp với việc dùng tài khoản dịch vụ, bind theo danh tính người dùng, StartTLS và chính sách server. Không giả định mọi context có thể được tái sử dụng thay thế lẫn nhau. Đặc biệt, một context đã dùng danh tính người dùng phải được xử lý đúng vòng đời để không làm lẫn quyền giữa các request.

### 12.4. Escape đúng lớp

| Dữ liệu | Công cụ/phương pháp phù hợp | Sai lầm thường gặp |
| --- | --- | --- |
| Giá trị trong search filter | `EqualsFilter`, query builder, filter encoding | Ghép trực tiếp input vào `(uid=...)` |
| Giá trị trong DN/RDN | `LdapNameBuilder`, `Rdn` | Ghép `"uid=" + value + ",ou=people"` |
| Thuộc tính ghi xuống LDAP | `Attributes`, `ModificationItem`, mapper/ODM | Tin rằng Java field tự vượt qua schema |
| Quyền truy cập ứng dụng | Spring Security/authorization nghiệp vụ | Coi search ra entry là bằng chứng đăng nhập |

## 13. Kiểm thử LdapTemplate như thế nào?

### 13.1. Unit test cho phần ánh xạ

Nếu phép chuyển `Attributes` sang DTO đủ phức tạp, có thể tách nó ra thành hàm thuần và thử bằng `BasicAttributes`:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

Attributes attrs = new BasicAttributes(true);
attrs.put("uid", "lan");
attrs.put("cn", "Nguyen Lan");
attrs.put("mail", "lan@example.org");

String cn = (String) attrs.get("CN").get();
System.out.println(cn); // Nguyen Lan
~~~

`BasicAttributes(true)` chỉ quy định cách collection Java tìm attribute ID không phân biệt hoa/thường; nó **không** thay đổi LDAP matching rule trên server.

Unit test nên bao gồm attribute thiếu, nhiều giá trị, kiểu binary, tên attribute có option và mapper xử lý dữ liệu bất thường. Tuy nhiên, các test này không chứng minh search base, scope, filter hoặc ACL đúng trên server.

### 13.2. Integration test với LDAP thử nghiệm

Dùng một LDAP test server (ví dụ embedded UnboundID hoặc directory thử nghiệm cô lập) có dữ liệu và schema phù hợp. Nên kiểm tra:

1. **Search**: filter equality với `uid=lan`; giá trị đầu vào chứa `*`, `(`, `)`, `\` không làm biến đổi ý nghĩa.
2. **DN**: tên có dấu phẩy, dấu cách và ký tự escape; DN tương đối với base được giải đúng.
3. **Scope**: `ONELEVEL` bỏ qua entry ở OU lồng nhau; `SUBTREE` tìm thấy entry đó.
4. **Lookup**: entry tồn tại/không tồn tại; mapper xử lý thuộc tính thiếu.
5. **Write**: thêm entry, sửa số điện thoại, đổi DN, xóa entry theo schema và ACL.
6. **Multivalued attributes**: cập nhật thành viên group không xóa nhầm giá trị hiện có.
7. **Security**: tài khoản chỉ đọc không được modify; lỗi bind và TLS được phân loại.
8. **Giới hạn**: kết quả có nhiều entry, count/time limit, paging và timeout.
9. **Pooling**: tái sử dụng context không gây lẫn danh tính hoặc rò rỉ kết nối.
10. **Lỗi vận hành**: server không truy cập được hoặc chứng chỉ không hợp lệ; ứng dụng không trả sai “không có user”.

### 13.3. Chọn mức kiểm thử đúng

| Loại kiểm thử | Xác minh tốt | Không thể chứng minh đầy đủ |
| --- | --- | --- |
| Unit test mapper | Quy tắc chuyển `Attributes` thành DTO | Schema, search scope, ACL của LDAP server |
| Integration test embedded LDAP | Nhiều thao tác end-to-end, DN/filter/schema test | Toàn bộ khác biệt của server production |
| Test với server đại diện | ACL, TLS, indexing và cấu hình thực tế | Tải production nếu không đo tải |
| Performance test | Latency, throughput, timeout, biến động khi có index/pool | Mọi trường hợp tương lai không có trong dữ liệu đo |

Không cần benchmark giả định kiểu “`LdapTemplate` nhanh hơn JNDI X lần”. Template chủ yếu giúp **quản lý code và tài nguyên**; hiệu năng thực tế phụ thuộc nhiều hơn vào chính yêu cầu LDAP và server.

## 14. Tình huống thực hành

**Đề bài:** Ứng dụng quản lý nhân viên cần hiển thị hồ sơ theo `uid`, cho phép cập nhật `telephoneNumber` sau khi kiểm tra quyền HR, và tìm người dùng trong nhiều OU con.

Bạn được cung cấp:

~~~text
ContextSource.base = dc=example,dc=org

ou=people
├── uid=lan
└── ou=engineering
    └── uid=minh
~~~

Hãy thiết kế:

1. Một phương thức tìm theo `uid` có `SUBTREE_SCOPE`.
2. Mapper chỉ lấy `uid`, `cn` và `mail`, cho phép `mail` vắng mặt nếu nghiệp vụ cho phép.
3. Một phương thức cập nhật số điện thoại theo **DN đã được xác minh**.
4. Cơ chế bảo vệ API cập nhật bằng authorization trước khi gọi template.
5. Cách phát hiện timeout, lỗi ACL và không tìm thấy entry thay vì trả rỗng cho mọi lỗi.

**Gợi ý hướng giải:**

- Sử dụng `EqualsFilter("uid", input).encode()`, search base `ou=people` và `SearchControls.SUBTREE_SCOPE` để tìm cả người dùng trong `ou=engineering`.
- Giới hạn thuộc tính và số kết quả, sau đó ánh xạ sang DTO rõ field bắt buộc/tùy chọn.
- Lấy DN thực của entry bằng `ContextMapper` hoặc một nguồn định danh đáng tin cậy; dùng `Name`/`LdapNameBuilder` khi thực hiện cập nhật.
- Spring Security kiểm tra người gọi có authority HR trước khi service thay đổi directory; tài khoản bind của service phải có ACL ghi cần thiết.
- Tách lỗi không tìm thấy, sai credentials, lỗi schema/permission và lỗi kết nối; log an toàn, không tiết lộ credentials.

### Câu hỏi tự kiểm tra

1. `LdapTemplate` giải quyết vấn đề nào của JNDI thuần và **không** tự giải quyết vấn đề nào?
2. Vì sao `ContextSource.base` và search base truyền vào `search(...)` phải được hiểu cùng nhau?
3. Khi nào bạn chọn `AttributesMapper` thay vì `ContextMapper`?
4. Có nên dùng `String.equalsIgnoreCase()` để kiểm tra DN trong permission logic không? Vì sao?
5. Vì sao `modifyAttributes` có thể thất bại dù template đã kết nối LDAP thành công?
6. `bind` thêm entry và LDAP bind authentication khác nhau thế nào?
7. Vì sao `setCountLimit(50)` không chứng minh có đúng 50 entry khớp?
8. Chỉ có `spring-ldap-core` thì có bắt buộc phải dùng Spring Data LDAP repository không?
9. Khi ứng dụng đã tìm được entry `uid=lan`, có thể kết luận người dùng đã đăng nhập không?
10. Test mapper bằng `BasicAttributes` có đủ để xác nhận filter và ACL trên production không?

**Đáp án gợi ý:** (1) Quản lý context, callback và chuyển đổi ngoại lệ; schema/ACL/TLS vẫn do các lớp khác quyết định. (2) Nhiều API dùng DN tương đối với base đã cấu hình. (3) ContextMapper khi cần context/DN; AttributesMapper khi chỉ cần attributes. (4) Không, quy tắc so DN phụ thuộc cú pháp và schema server. (5) Quyền ghi, schema, DN hoặc dữ liệu không hợp lệ. (6) Thêm entry khác kiểm tra mật khẩu. (7) Giới hạn output khác tổng số match. (8) Không. (9) Không. (10) Không, cần integration test.

## 15. Những lỗi thiết kế phổ biến

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Tự tạo `DirContext`/`LdapTemplate` cho mọi request | Lặp code, khó quản lý lifecycle | Reuse bean `ContextSource` và template |
| Tự ghép LDAP filter từ input | Injection hoặc wildcard ngoài ý muốn | `EqualsFilter`/filter builder |
| Tự ghép DN từ input | Sai escape dấu phẩy/khoảng trắng/RDN | `LdapNameBuilder` |
| Dùng `ONELEVEL` khi có OU con | Mất kết quả ở nhánh sâu | `SUBTREE` với base phù hợp |
| Đọc tất cả attributes của mọi entry | Tốn mạng và memory | Chỉ yêu cầu attributes cần thiết |
| Ép mọi attribute thành `String` | Lỗi binary/multivalued | Xem schema và kiểm tra kiểu |
| Gọi `get()` một lần cho group member | Bỏ sót các giá trị khác | Xử lý `getAll()` nếu cần |
| Dùng service account quá rộng quyền | Mở rộng phạm vi tác động | ACL tối thiểu, phân quyền riêng |
| Coi search thành công là xác thực | Sai kiến trúc bảo mật | Spring Security LDAP/bind |
| Catch mọi lỗi thành empty list | Che lỗi hệ thống và kết luận sai | Phân loại exception |
| Dùng paging để chữa filter quá rộng | Vẫn tạo tải nặng cho server | Thu hẹp scope/filter và tối ưu index |
| Cho rằng template tạo transaction nhiều entry | Dễ ghi một phần khi thao tác nhiều bước | Thiết kế idempotency/bù trừ |

## 16. Ghi nhớ

**`LdapTemplate` là lớp thao tác trung tâm của Spring LDAP core:** nó dùng `ContextSource` để tiếp cận JNDI/LDAP, thực hiện tìm kiếm và thay đổi entry, quản lý tài nguyên cho các operation chuẩn, chuyển đổi lỗi và để ứng dụng ánh xạ kết quả qua callback.

Để dùng template đúng, luôn xác định **DN và base**, **filter**, **scope**, **schema**, **quyền bind**, **attributes trả về** và **giới hạn tài nguyên**. Dùng mapper khi cần DTO linh hoạt, ODM/repository khi mô hình entry ổn định và Spring Security LDAP khi cần tích hợp xác thực/phân quyền. Trong mọi trường hợp, LDAP server vẫn là nơi thực thi schema, matching rules và ACL.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Data LDAP — Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Java SE 17 — SearchControls](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
