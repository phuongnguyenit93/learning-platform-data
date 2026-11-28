# Phân biệt bind của giao thức với bind tạo entry trong API JNDI/Spring LDAP

## 1. Vì sao từ “bind” dễ gây nhầm?

Khi làm việc với LDAP bằng Java, bạn có thể gặp hai dòng code đều có chữ **bind** nhưng làm hai việc hoàn toàn khác:

```java
// A. Xác thực một danh tính LDAP để mở context.
DirContext authenticated = contextSource.getContext(
    "uid=linh,ou=people,dc=example,dc=org",
    password
);

// B. Tạo một entry LDAP mới.
ldapTemplate.bind(userDn, null, attributes);
```

Ở trường hợp A, client thực hiện **LDAP Bind operation** để server xác thực danh tính và thiết lập trạng thái xác thực trên kết nối LDAP. Ở trường hợp B, API JNDI/Spring LDAP dùng tên phương thức `bind` theo mô hình naming để **thêm một entry mới** vào directory; LDAP provider thực hiện thao tác **Add** trên giao thức.

Nếu nhầm hai ý nghĩa này, ứng dụng có thể:

- Dùng nhầm tài khoản dịch vụ để tạo entry khi mục tiêu chỉ là kiểm tra password người dùng.
- Tưởng rằng `ldapTemplate.bind` là bước xác thực, trong khi nó đang ghi một entry mới.
- Dùng `Context.bind` để “bind connection”, rồi nhận lỗi `entryAlreadyExists`.
- Dùng `ContextSource.getContext` để “tạo user”, nhưng thực tế chỉ mở context đã xác thực.
- Dùng `rebind` như một cách cập nhật attribute và vô tình xóa/tạo lại entry theo semantics của provider.

Trong module **SPRING_DATA_LDAP**, Spring Data LDAP repository/ODM và Spring LDAP `LdapTemplate` giúp thao tác với entry phân cấp theo DN, `objectClass` và schema. Muốn sử dụng đúng các API CRUD, cần phân biệt **Bind của giao thức** với **bind tạo entry của JNDI/Spring LDAP**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả LDAP BindRequest và trạng thái xác thực của một kết nối.
2. Phân biệt Bind operation với Add operation ở tầng protocol.
3. Giải thích vì sao JNDI `DirContext.bind`/`InitialDirContext.bind` tạo entry.
4. Dùng `ContextSource.getContext(principal, credentials)` để lấy context xác thực.
5. Dùng `LdapTemplate.bind`/`create` để thêm entry mới và hiểu điều kiện schema/ACL.
6. Phân biệt `bind`, `rebind`, `unbind`, `modifyAttributes` và `rename`.
7. Không dùng bind của tài khoản dịch vụ thay cho xác thực người dùng cuối.
8. Kiểm thử hai luồng độc lập trên LDAP directory test.

## 2. Hai ý nghĩa bind: một bảng phân biệt

| Tiêu chí | LDAP protocol Bind | JNDI/Spring LDAP naming bind |
| --- | --- | --- |
| Mục tiêu | Xác thực client hoặc thiết lập anonymous/SASL authentication state trên kết nối. | Tạo binding của một tên tới object/attributes; với LDAP provider, thường tạo entry mới. |
| Protocol operation | **BindRequest / BindResponse**. | Thông thường là **AddRequest / AddResponse** khi tạo entry LDAP. |
| Đầu vào chính | Authentication mechanism, bind DN/principal và credential/token tùy cơ chế. | DN mới, object (thường null hoặc object được hỗ trợ) và tập LDAP attributes. |
| Kết quả | Kết nối LDAP có trạng thái xác thực tương ứng hoặc bị từ chối. | Một entry được thêm vào directory hoặc server trả lỗi. |
| Có tạo user entry không? | **Không.** Bind không thêm entry. | **Có**, khi thao tác bind vào DN chưa tồn tại và attributes hợp lệ. |
| API Java thường gặp | `InitialDirContext(env)`, `ContextSource.getContext(dn,password)`. | `DirContext.bind(name,obj,attrs)`, `LdapTemplate.bind(dn,obj,attrs)`. |
| Lỗi tiêu biểu | `invalidCredentials`, authentication mechanism unsupported, TLS/network failure. | `entryAlreadyExists`, `noSuchObject`, `objectClassViolation`, `insufficientAccessRights`. |

**Quy tắc ghi nhớ:**

```text
LDAP Bind operation  = "Tôi là ai? Hãy xác thực tôi trên kết nối này."
JNDI Context.bind    = "Hãy tạo entry tại DN này với các attributes này."
```

Tên method trong Java không đủ để kết luận protocol operation. Phải nhìn **package, object, overload và mục đích API**.

## 3. LDAP Bind ở tầng giao thức làm gì?

LDAP là giao thức client-server. Trước khi thực hiện một số thao tác, client có thể gửi **BindRequest** để server xác thực danh tính và thiết lập trạng thái xác thực của kết nối.

### 3.1. Luồng Bind đơn giản

```text
Java application
      |
      | TCP connect
      v
LDAP server
      |
      | TLS handshake (nếu LDAPS/StartTLS)
      v
LDAP BindRequest (mechanism + credentials)
      |
      v
BindResponse success / failure
      |
      v
SearchRequest / ModifyRequest
```

Các bước có thể được provider thực hiện lười (*lazy*). Ví dụ, tạo một JNDI context chưa chắc đã khiến socket và BindRequest được gửi ngay tại dòng khởi tạo; request đầu tiên có thể kích hoạt việc kết nối. Không nên phụ thuộc vào thời điểm kết nối nội bộ nếu không có contract rõ ràng.

### 3.2. Bind không phải Add

Hai operation có ý nghĩa khác:

- **BindRequest:** yêu cầu xác thực kết nối bằng cơ chế được chọn.
- **AddRequest:** yêu cầu server thêm một entry mới tại DN chỉ định, với các attribute và object classes tương ứng.

BindRequest không có danh sách `objectClass`, `cn`, `sn` để tạo user. AddRequest không kiểm tra password đăng nhập của user như một phép xác thực.

### 3.3. Các dạng authentication thường gặp

LDAP hỗ trợ nhiều cách xác thực:

- **Anonymous bind:** không cung cấp danh tính/credential; server có thể cho hoặc không cho phép thao tác anonymous.
- **Simple bind:** gửi bind DN và password. Nếu không được bảo vệ bằng TLS, password có thể bị lộ trên đường truyền.
- **SASL bind:** dùng cơ chế SASL được client và server hỗ trợ, ví dụ một số cơ chế tích hợp danh tính doanh nghiệp.

Bind operation có thể thay đổi trạng thái xác thực hiện tại của kết nối. Không chia sẻ một context đã xác thực bằng credential người dùng A sang thread/request của người dùng B. Với connection pooling, phải hiểu pool phân tách identity như thế nào và không tái sử dụng context sai principal.

### 3.4. Bind không phải session HTTP

LDAP authentication state gắn với **kết nối LDAP**. Nó không tự tạo session cookie trong Spring MVC, không cấp JWT và không thu hồi access token đã phát hành trước đó. Nếu ứng dụng dùng LDAP để xác thực người dùng, session/token của ứng dụng vẫn cần lifecycle riêng.

## 4. Bind protocol bằng JNDI: tạo context đã xác thực

JNDI LDAP provider cho phép cấu hình principal và credential qua environment:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.InitialDirContext;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
    "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL,
    "ldaps://ldap.example.org:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
    "uid=svc-reader,ou=service-accounts,dc=example,dc=org");
env.put(Context.SECURITY_CREDENTIALS,
    System.getenv("LDAP_BIND_PASSWORD"));

InitialDirContext context = new InitialDirContext(env);
try {
    // Context đã được cấu hình để dùng danh tính service account.
    // Provider có thể kết nối/bind khi thực hiện operation đầu tiên.
} finally {
    context.close();
}
```

Trong ví dụ:

- `Context.SECURITY_AUTHENTICATION` chọn cơ chế `simple`.
- `Context.SECURITY_PRINCIPAL` là DN dùng để bind.
- `Context.SECURITY_CREDENTIALS` là secret được lấy từ môi trường.
- `ldaps://...:636` chỉ là endpoint ví dụ; JVM vẫn cần truststore đúng và xác minh hostname.

**Đây là context xác thực**, không tạo entry `uid=svc-reader`. Entry service account phải được provision riêng bởi quy trình quản trị directory.

### 4.1. ContextSource trong Spring LDAP

Spring LDAP cung cấp `ContextSource` để tạo context theo credential cấu hình hoặc credential được truyền vào:

```java
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setUserDn(
    "uid=svc-reader,ou=service-accounts,dc=example,dc=org");
source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
source.afterPropertiesSet();

DirContext serviceContext = source.getReadOnlyContext();
try {
    // Thao tác đọc dưới danh tính service account đã cấu hình.
} finally {
    serviceContext.close();
}
```

Trong ứng dụng Spring Boot, `LdapContextSource` thường được cấu hình qua auto-configuration hoặc bean được quản lý; không cần tự tạo source mới mỗi request. `getReadOnlyContext()` lấy context theo cấu hình read-only của source, không phải tạo entry.

### 4.2. Xác thực một người dùng cuối khác service account

Nếu muốn kiểm tra password người dùng, cần bind bằng **DN của chính người đó** và credential người dùng:

```java
DirContext userContext =
    contextSource.getContext(userDn, suppliedPassword);
try {
    // Context dùng danh tính userDn, không phải service account.
} finally {
    userContext.close();
}
```

Ở đây `userDn` phải được xác định an toàn. Một flow thường gặp là:

1. Dùng service account quyền tìm kiếm tối thiểu để tìm DN theo UID đã được escape đúng.
2. Nếu tìm thấy đúng một entry, lấy DN đầy đủ từ kết quả.
3. Dùng DN đó cùng password người dùng để tạo authenticated context.
4. Xử lý lỗi authentication riêng với lỗi tìm kiếm, lỗi mạng, TLS và ACL.
5. Đóng context; không lưu password vào log/cache hoặc tái sử dụng context giữa người dùng.

**Không** nối trực tiếp input người dùng vào LDAP filter, ví dụ `"(uid=" + uid + ")"`. Dùng `LdapQueryBuilder` hoặc cơ chế escaping RFC 4515 phù hợp. Filter injection có thể khiến bước tìm DN chọn nhầm đối tượng.

### 4.3. Bind thành công không chứng minh có quyền đọc mọi entry

Một Bind thành công chứng minh server chấp nhận authentication mechanism/credential trên kết nối. Quyền Search, Read, Modify, Delete vẫn do **ACL** quyết định. User có thể bind được nhưng không có quyền đọc `ou=people` hoặc không có quyền xem attribute `mail`.

## 5. JNDI DirContext.bind: tạo một LDAP entry

`javax.naming.directory.DirContext` kế thừa naming API `Context` và có overload nhận attributes. Với LDAP provider, `bind(name, object, attributes)` dùng để tạo entry tại DN được chỉ định.

### 5.1. Ví dụ tạo người dùng trong directory test

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "lab-user")
    .build();

Attributes attrs = new BasicAttributes(true);
Attribute objectClasses = new BasicAttribute("objectClass");
objectClasses.add("top");
objectClasses.add("person");
objectClasses.add("organizationalPerson");
objectClasses.add("inetOrgPerson");
attrs.put(objectClasses);
attrs.put("uid", "lab-user");
attrs.put("cn", "Lab User");
attrs.put("sn", "User");
attrs.put("mail", "lab-user@example.org");

DirContext adminContext = source.getReadWriteContext();
try {
    adminContext.bind(dn, null, attrs);
} finally {
    adminContext.close();
}
```

Kết quả mong muốn là entry:

```ldif
dn: uid=lab-user,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lab-user
cn: Lab User
sn: User
mail: lab-user@example.org
```

Trong ví dụ, `adminContext` là một context đã được xác thực và có quyền Add tại `ou=people`; tên biến chỉ mang tính minh họa, không có nghĩa phải dùng tài khoản domain admin. `dn` là DN tương đối vì context đã có base `dc=example,dc=org`.

### 5.2. Add operation cần gì?

Để server chấp nhận entry mới:

1. Parent DN `ou=people,dc=example,dc=org` phải tồn tại.
2. DN đích chưa được sử dụng.
3. Các `objectClass` phải hợp lệ và được server hỗ trợ.
4. Các attribute `MUST` phải có, ví dụ `cn` và `sn` khi dùng `person`.
5. Attribute không được vượt cardinality `SINGLE-VALUE` hoặc vi phạm syntax.
6. Bind principal có quyền Add tại parent/target theo ACL.

`DirContext.bind` không tự tạo OU cha và không tự sinh schema.

### 5.3. DN và attribute naming cần nhất quán

Trong ví dụ, RDN `uid=lab-user` và attribute `uid: lab-user` cùng thể hiện naming attribute. Đối với schema và server cụ thể, cần bảo đảm naming AVA hợp lệ và entry có các attribute phù hợp. Đừng giả định mọi directory chấp nhận một DN mà entry không có naming attribute tương ứng.

### 5.4. Vì sao dùng null cho object?

Overload `DirContext.bind(Name, Object, Attributes)` cho phép client cung cấp tập attributes. Với LDAP entry thông thường, ví dụ thường truyền `null` làm object vì nội dung entry được biểu diễn bằng `Attributes`. Việc truyền object Java tùy ý không biến nó thành một LDAP object có thể serialize tự động; LDAP provider có quy tắc object factory/serialization riêng và không nên dựa vào chúng trong bài thực hành cơ bản.

## 6. Spring LDAP: LdapTemplate.bind và create

Spring LDAP bọc thao tác JNDI bằng `LdapTemplate`. Tên `bind` trong `LdapTemplate` cũng thuộc **naming/create entry**, không phải LDAP BindRequest xác thực.

### 6.1. bind với Name và Attributes

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "lab-user")
    .build();

Attributes attrs = new BasicAttributes(true);
BasicAttribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("person");
classes.add("organizationalPerson");
classes.add("inetOrgPerson");
attrs.put(classes);
attrs.put("uid", "lab-user");
attrs.put("cn", "Lab User");
attrs.put("sn", "User");

ldapTemplate.bind(dn, null, attrs);
```

`LdapTemplate` sử dụng `ContextSource` đã cấu hình để lấy context và thực hiện thao tác naming tương ứng. ContextSource credentials ở đây là **danh tính ứng dụng dùng để ghi entry**, không phải password của người dùng mới tạo.

### 6.2. bind một DirContextOperations

Nếu đã dựng một `DirContextAdapter`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "lab-user")
    .build();

DirContextAdapter entry = new DirContextAdapter(dn);
entry.setAttributeValues("objectClass", new String[] {
    "top", "person", "organizationalPerson", "inetOrgPerson"
});
entry.setAttributeValue("uid", "lab-user");
entry.setAttributeValue("cn", "Lab User");
entry.setAttributeValue("sn", "User");

ldapTemplate.bind(entry);
```

Adapter được dùng làm object mang DN và tập attribute để **tạo mới**. Đây không phải authenticated context và cũng không có nghĩa password người dùng đã được xác thực.

### 6.3. ODM create(Object)

Với entity Spring LDAP ODM:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
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

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public DirectoryPerson() {}
    // getters/setters cần thiết.
}
```

```java
DirectoryPerson person = new DirectoryPerson();
person.setUid("lab-user");
person.setCommonName("Lab User");
person.setSurname("User");

ldapTemplate.create(person);
```

`create(Object)` là ODM API để tạo entry từ entity mapping. Nó không phải phép xác thực người dùng và không tự tạo tài khoản có password hợp lệ nếu schema/credential policy yêu cầu thuộc tính hoặc quy trình khác.

## 7. Cấu hình Spring Boot: service bind và end-user bind là hai danh tính

Một ứng dụng thường có ít nhất hai luồng:

```text
LUỒNG A — ứng dụng truy cập directory
  Spring Boot -> ContextSource configured service DN/password
              -> LDAP Bind
              -> Search / Read / Modify / Add

LUỒNG B — xác thực người dùng
  username -> tìm DN bằng service context
           -> tạo context bằng user DN + password người dùng
           -> LDAP Bind của người dùng
           -> kết quả xác thực
```

Ví dụ cấu hình service account:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

`spring.ldap.username`/`password` là thông tin mà ứng dụng dùng để lấy context qua `ContextSource`. Đây không phải dữ liệu password của user mới tạo và không nên được trả về client.

### 7.1. Một service account cho mỗi vai trò

Trong hệ thống lớn, có thể phân biệt:

| Danh tính | Mục đích | Quyền gợi ý |
| --- | --- | --- |
| `svc-directory-reader` | Tìm DN và đọc dữ liệu được phép. | Search/Read trong subtree nghiệp vụ. |
| `svc-directory-writer` | Tạo/sửa/xóa entry theo use case. | Add/Modify/Delete có giới hạn OU/attribute. |
| User cuối | Xác thực bằng password của chính họ. | Quyền directory theo user/ACL; không dùng để ghi entry. |

Không dùng service account có quyền quản trị toàn bộ directory để kiểm tra mọi password người dùng nếu có một flow xác thực riêng phù hợp. Không lưu password end-user vào DB/log hoặc reuse password của user cho thao tác CRUD.

### 7.2. Khi nào bind tạo context không chứng minh kết nối đã mở?

JNDI provider có thể trì hoãn mở socket đến khi context thực hiện operation. Do đó:

- Dòng `new InitialDirContext(env)` có thể tạo object context trước khi network I/O thực sự xảy ra.
- Dòng `source.getContext(userDn, password)` tạo context theo credential được cung cấp, nhưng chi tiết kết nối có thể lazy tùy provider.
- Một operation LDAP tiếp theo có thể làm phát sinh BindRequest, SearchRequest hoặc lỗi kết nối.

Nếu cần health check, hãy thực hiện phép đọc nhỏ có timeout; đừng dựa duy nhất vào việc constructor không ném exception.

## 8. Phân biệt bind, rebind, unbind và modify

Tên method gần nhau nhưng semantics khác:

| API | Ý nghĩa trong JNDI/Spring LDAP | Tác động LDAP điển hình |
| --- | --- | --- |
| `getContext(principal, credentials)` | Lấy context dùng danh tính được chỉ định. | LDAP Bind để xác thực kết nối, có thể được thực hiện lazy. |
| `DirContext.bind(name,obj,attrs)` | Tạo binding/entry mới tại tên. | LDAP Add. |
| `LdapTemplate.bind(...)` | Tạo entry từ DN và attributes/ODM context. | LDAP Add. |
| `Context.rebind(...)` | Gán lại binding, thay binding cũ theo naming semantics. | Provider có thể thực hiện nhiều operation; không phải một protocol BindRequest. |
| `Context.unbind(name)` | Gỡ binding tại tên. | LDAP Delete cho entry tương ứng. |
| `LdapTemplate.modifyAttributes(...)` | Thay đổi attribute của entry đang tồn tại. | LDAP Modify. |
| `LdapTemplate.rename(oldDn,newDn)` | Đổi RDN/parent DN. | LDAP Modify DN. |

### 8.1. rebind không phải “bind lại kết nối”

`Context.rebind` thuộc naming API. Trong LDAP provider, LDAP không có operation giao thức tên `RebindRequest`; provider phải triển khai semantics “ghi đè binding” bằng những operation LDAP phù hợp.

Tùy provider và kiểu object, quá trình này có thể tương đương xóa entry cũ rồi thêm entry mới hoặc dùng một cách xử lý khác. **Không** giả định `rebind` là một LDAP ModifyRequest nguyên tử để thay vài attribute. Nếu muốn cập nhật attribute, dùng `modifyAttributes` hoặc API update ODM có contract rõ ràng.

Vì rebind có thể ảnh hưởng identity/metadata/operational attributes và tạo khoảng trống giữa delete/add, không dùng nó như cách “upsert” tùy tiện cho user production.

### 8.2. unbind là xóa, không phải đóng context

Có hai cách đóng/gỡ khác nhau:

- `context.close()` đóng **context/kết nối** và giải phóng tài nguyên client.
- `ldapTemplate.unbind(dn)` yêu cầu xóa **entry** tại DN.

Không gọi `unbind` để “đóng phiên LDAP”. Đóng context không xóa entry, còn unbind entry không phải thao tác đóng socket context của một đối tượng khác.

## 9. CRUD trong Spring Data LDAP: tạo entry khác xác thực

Một repository:

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

Các method CRUD thường có ý nghĩa:

```java
repository.save(person);       // Tạo/cập nhật entity theo repository contract.
repository.findById(dn);       // Đọc entry theo DN.
repository.deleteById(dn);     // Xóa entry.
```

`save` không phải BindRequest để xác thực người dùng. `findById` không xác thực password của user. `deleteById` không vô hiệu hóa tài khoản. Repository hoạt động trên **entry data** bằng context đã cấu hình.

### 9.1. Kiểm tra password không phải tạo entry

Nếu nghiệp vụ là “người dùng đăng nhập bằng username/password”, không được gọi:

```java
// Sai mục đích: đây là tạo entry, không phải xác thực.
ldapTemplate.bind(userDn, null, userAttributes);
```

Thay vào đó, tìm đúng user DN rồi dùng credential người dùng để thực hiện authentication flow được ứng dụng hỗ trợ. Trong Spring Security, có thể dùng các thành phần LDAP authentication phù hợp phiên bản; không tự xây cơ chế so sánh password bằng cách đọc `userPassword` vì attribute này thường bị bảo vệ, có thể được hash và có policy server riêng.

### 9.2. Tạo entry không tự cấp mật khẩu

Một entry `inetOrgPerson` có thể được tạo với `uid`, `cn`, `sn`, `mail` mà không có `userPassword`, tùy schema/policy. Entry đó có tồn tại **không có nghĩa** user có thể bind bằng password mong muốn.

Nếu ứng dụng cần cấp credential, hãy sử dụng quy trình quản trị password được directory hỗ trợ, gồm:

- Chính sách password/encoding/hash và quyền thay đổi.
- Cơ chế password modify extended operation nếu phù hợp.
- Bắt buộc TLS, không log credential.
- Kiểm thử authentication thật sau provision trong directory test.

Không tự ghi plaintext password vào `userPassword` trừ khi policy/server documentation xác nhận chính xác cơ chế được phép; tuyệt đối không lưu password ở log hoặc DTO phản hồi.

## 10. Lỗi thường gặp và cách phân biệt

| Exception/result | Ngữ cảnh | Ý nghĩa thường gặp |
| --- | --- | --- |
| LDAP `invalidCredentials` (49) | Protocol Bind | DN/credential không được chấp nhận, account policy hoặc credential sai. |
| LDAP `strongerAuthRequired` (8) | Bind hoặc thao tác yêu cầu bảo vệ mạnh hơn | Server yêu cầu cơ chế xác thực/bảo vệ kết nối phù hợp, ví dụ TLS theo policy. |
| LDAP `authMethodNotSupported` (7) | Protocol Bind | Server không hỗ trợ authentication mechanism client chọn. |
| `NameAlreadyBoundException` / LDAP `entryAlreadyExists` (68) | JNDI/Spring naming bind | DN tạo mới đã có entry. |
| LDAP `noSuchObject` (32) | Add/Modify/Search | Parent/base DN không tồn tại hoặc DN sai. |
| LDAP `objectClassViolation` (65) | Add/Modify | Entry không thỏa objectClass, thiếu MUST hoặc chứa attribute không được phép. |
| LDAP `invalidAttributeSyntax` (21) | Add/Modify | Giá trị không đúng syntax schema. |
| LDAP `insufficientAccessRights` (50) | Add/Modify/Delete | Bind identity không đủ ACL cho thao tác. |
| `CommunicationException` | Mọi operation | DNS, TCP, TLS, timeout hoặc server unavailable; không đồng nghĩa credential sai. |

### 10.1. Phân biệt credential sai với DN không tồn tại

Một số server cố ý trả thông tin lỗi authentication hạn chế để không tiết lộ account tồn tại hay không. Vì vậy, không xây logic bảo mật phụ thuộc vào chi tiết diagnostic message của server. Ghi nhận loại lỗi ở log nội bộ đã kiểm soát; phản hồi đăng nhập bên ngoài nên không tiết lộ username hợp lệ hay không.

### 10.2. Phân biệt Add thất bại với Bind thất bại

Ví dụ:

- `invalidCredentials` trong Bind: kiểm tra credential, DN principal, account lock/expiry, TLS và authentication mechanism.
- `entryAlreadyExists` trong Add: kiểm tra DN mới đã tồn tại, tránh retry tạo entry lặp.
- `objectClassViolation` trong Add: kiểm tra schema, MUST/MAY, naming attribute và attribute syntax.
- `insufficientAccessRights` trong Add: kiểm tra ACL của **service account ghi**, không đổi sang user password.

Đừng catch mọi lỗi rồi trả “đăng nhập thất bại” hoặc “user đã tồn tại”; cần phân loại theo operation đã thực hiện.

## 11. Bảo mật: Bind và Add có các rủi ro khác nhau

### 11.1. Bảo vệ password của protocol Bind

Simple Bind gửi credential dưới dạng có thể khôi phục nếu đường truyền không được bảo vệ. Vì vậy:

- Dùng LDAPS hoặc StartTLS được cấu hình đúng.
- Xác minh certificate chain bằng truststore và hostname/SAN.
- Khi dùng StartTLS, hoàn tất TLS handshake trước khi gửi simple Bind.
- Không fallback xuống `ldap://` plaintext khi TLS lỗi.
- Không log `Context.SECURITY_CREDENTIALS`, bind password hoặc raw environment.
- Giới hạn thời gian kết nối/đọc và đóng context đúng cách.

### 11.2. Bảo vệ thao tác Add

Tạo entry cũng cần bảo vệ:

- Bind principal của ứng dụng chỉ có quyền Add ở OU được phép.
- Không cho HTTP caller tự gửi raw DN hoặc tùy ý chọn `objectClass`.
- Dùng `LdapNameBuilder` để dựng DN và `LdapQueryBuilder` để dựng filter.
- Validate attribute theo schema và nghiệp vụ trước khi gửi.
- Chống duplicate DN và xử lý retry sau timeout.
- Audit ai đã provision entry và ở vùng nào.

### 11.3. Không để user context lọt vào connection pool của service

Nếu dùng `ContextSource.getContext(userDn,password)` để xác thực user:

- Đóng context ngay khi xong.
- Không đặt context user vào singleton bean hoặc thread-local tồn tại lâu.
- Không trả context user vào pool service account.
- Không đổi authentication state trên một context đang được request khác sử dụng.
- Tránh giữ password người dùng sau khi kết quả authentication đã được xác định.

Một context đã bind bằng danh tính A không được dùng như context của B. Pooling phải tôn trọng principal/credential và cấu hình validation.

### 11.4. Không đọc userPassword để so sánh

Attribute `userPassword` có thể bị ACL bảo vệ, được lưu dưới dạng hash và chịu password policy. Ứng dụng không nên đọc hash rồi tự so sánh password. Dùng Bind/authentication mechanism để server xác minh credential. Khi provision hoặc đổi password, dùng cơ chế được server hỗ trợ và tuân thủ TLS.

## 12. Ví dụ luồng provision và xác thực tách biệt

Một service tạo tài khoản mới và một service xác thực người dùng có thể cùng dùng directory nhưng có trách nhiệm khác:

```text
LUỒNG A — provision
  Admin request
      |
      v
  Validate actor and attributes
      |
      v
  Build DN and objectClass
      |
      v
  Service account Bind
      |
      v
  LDAP AddRequest via LdapTemplate.bind
      |
      v
  Entry created

LUỒNG B — login
  Username/password
      |
      v
  Search DN via reader service context
      |
      v
  Resolve one user DN
      |
      v
  BindRequest with user's own credential
      |
      v
  Authentication result
```

Hai nhánh có thể dùng chung endpoint LDAP nhưng **không dùng chung credential**:

- Nhánh provision dùng service account có quyền Add.
- Nhánh login dùng service context để tìm DN, sau đó xác thực bằng credential người dùng.
- Nếu provision có bước cấp password, đó là một quy trình riêng, không đồng nghĩa Add entry.

## 13. Integration test: chứng minh hai ý nghĩa khác nhau

Unit test mock có thể xác minh method được gọi, nhưng không chứng minh protocol operation thực tế. Cần integration test trên LDAP directory test với TLS, schema và ACL phù hợp.

### 13.1. Test Add qua LdapTemplate.bind

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class LdapBindSemanticsIT {

    @Autowired
    private LdapTemplate ldap;

    @Test
    void bindWithAttributesCreatesAnEntry() {
        String uid = "lab" + UUID.randomUUID()
            .toString().replace("-", "").substring(0, 12);
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
        attrs.put("cn", "Lab User " + uid);
        attrs.put("sn", "User");

        boolean created = false;
        try {
            ldap.bind(dn, null, attrs);
            created = true;

            assertThat(ldap.lookup(dn)).isNotNull();
            assertThatThrownBy(() -> ldap.bind(dn, null, attrs))
                .isInstanceOf(NameAlreadyBoundException.class);
        } finally {
            if (created) {
                ldap.unbind(dn);
            }
        }
    }
}
```

Test này minh họa **naming bind tạo entry**. Nó giả định DN chưa tồn tại, `ou=people` đã có và tài khoản cấu hình trong `ContextSource` có quyền Add/Delete fixture. Trong CI nhiều worker, hãy tạo UID ngẫu nhiên để tránh va chạm; dọn fixture trong directory test.

### 13.2. Test authenticated context không tạo entry

Một integration test riêng dùng một DN user **đã provision trước** và credential thử nghiệm:

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import javax.naming.directory.DirContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@SpringBootTest
class UserAuthenticationContextIT {

    @Autowired
    private BaseLdapPathContextSource contextSource;

    @Value("${directory.test-user.dn}")
    private String userDn;

    @Value("${directory.test-user.password}")
    private String password;

    @Test
    void getContextUsesTheSuppliedUserIdentity() throws Exception {
        DirContext userContext =
            contextSource.getContext(userDn, password);
        try {
            // Chỉ xác nhận context đã được tạo bằng credential user.
            // Không tạo entry và không ghi attributes.
            assertThat(userContext).isNotNull();
        } finally {
            userContext.close();
        }
    }
}
```

Lưu ý:

- `userDn`/`password` là fixture riêng trong test secret configuration; không dùng tài khoản production.
- Tùy provider, việc tạo context có thể chưa mở kết nối ngay. Nếu cần chứng minh BindRequest đã được gửi và được chấp nhận, phải thực hiện một operation được phép hoặc quan sát server test logs/tracing; không nhầm việc constructor trả object với bằng chứng network handshake đã hoàn tất.
- Không dùng `ldap.bind(dn, null, attrs)` trong test này: như vậy sẽ tạo entry, không xác thực user.

### 13.3. Ma trận kiểm thử

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Bind với credential đúng | `ContextSource.getContext(userDn,password)` | Context xác thực có thể được tạo; xác minh Bind thực bằng operation/trace nếu cần. |
| Bind với password sai | ContextSource theo credential sai | Authentication bị từ chối; không có entry mới. |
| Bind anonymous bị policy cấm | Anonymous context | Server từ chối hoặc hạn chế theo cấu hình. |
| Add DN mới | `LdapTemplate.bind(dn,null,attrs)` | Entry xuất hiện trên server. |
| Add DN trùng | Gọi bind lần hai | `entryAlreadyExists`/`NameAlreadyBoundException`; không ghi đè entry cũ. |
| Add thiếu `sn` cho `person` | Gửi attributes thiếu MUST | Schema từ chối. |
| Add dưới parent không tồn tại | DN có OU cha không có | `noSuchObject`. |
| Add bằng bind account chỉ đọc | Service account thiếu quyền Add | `insufficientAccessRights`. |
| Close authenticated context | `context.close()` | Giải phóng tài nguyên client; entry vẫn tồn tại. |
| Unbind entry | `ldapTemplate.unbind(dn)` | Entry bị xóa; không phải đóng authenticated context. |
| Rebind entry hiện có | `rebind` theo provider | Xác minh semantics cụ thể; không giả định atomic Modify. |

## 14. Chẩn đoán theo operation, không theo tên method

Khi lỗi xảy ra, trước tiên hãy hỏi: **client đang xác thực kết nối hay đang thêm entry?**

```text
Nếu code gọi:
  source.getContext(principal, credentials)
    -> kiểm tra Bind: principal, credential, mechanism, TLS, account state.

Nếu code gọi:
  ldapTemplate.bind(dn, null, attributes)
    -> kiểm tra Add: DN, parent, objectClass, MUST/MAY, syntax, ACL.
```

### 14.1. Lỗi Bind

| Triệu chứng | Kiểm tra |
| --- | --- |
| `invalidCredentials` | DN principal đúng chưa? Password/secret có đúng? Account lock/expiry? |
| `strongerAuthRequired` | Simple Bind có đang chạy trên plaintext? Server yêu cầu TLS/SASL? |
| `authMethodNotSupported` | Cơ chế Bind có được server hỗ trợ? |
| `CommunicationException` | DNS/TCP/TLS/timeout; phân biệt với credential sai. |
| Bind service account được nhưng Bind user không được | DN user tìm có chính xác? User password/account policy? |

### 14.2. Lỗi Add

| Triệu chứng | Kiểm tra |
| --- | --- |
| `entryAlreadyExists` | DN đích đã tồn tại; xử lý idempotency, không ghi đè. |
| `noSuchObject` | Parent OU/base DN có tồn tại? DN tương đối hay full DN? |
| `objectClassViolation` | Có đủ MUST? objectClass có hợp lệ/được phép? |
| `invalidAttributeSyntax` | Giá trị có đúng syntax/schema? |
| `insufficientAccessRights` | Service account có quyền Add trong OU? |
| `constraintViolation` | Cardinality, naming rule hoặc policy server. |

Không chuyển lỗi Add thành “password sai” và cũng không chuyển lỗi Bind thành “user đã tồn tại”.

## 15. Lưu ý đặc biệt về pooling và authentication state

Connection pooling có thể tái sử dụng kết nối LDAP để giảm TCP/TLS/Bind overhead. Tuy nhiên:

- Kết nối có **authentication state** của principal đã bind.
- Context user cuối không nên bị trả về pool service account nếu pool không quản lý identity đúng cách.
- Nếu ứng dụng đổi Bind identity trên một kết nối đang được chia sẻ, các request khác có thể bị ảnh hưởng.
- Pool validation có thể phát sinh Search/Bind phụ; cần đo và cấu hình hợp lý.
- Khi credential người dùng thay đổi hoặc account bị khóa, context đã mở trước đó không tự phản ánh mọi thay đổi chính sách; cần quản lý lifecycle và authorization ở ứng dụng.

Với một service account cố định, pool có thể phù hợp. Với **mỗi user một bind identity**, phải đánh giá kỹ isolation, thread safety và credential handling; không tùy tiện dùng cùng pool như khi mọi request dùng một service principal.

## 16. Checklist thiết kế

Trước khi viết code có chữ `bind`, hãy xác định:

- [ ] Đây là **LDAP protocol Bind** để xác thực, hay **naming bind** để tạo entry?
- [ ] Nếu xác thực, principal nào được dùng: service account hay user cuối?
- [ ] Nếu tạo entry, DN đích đã được dựng an toàn bằng `LdapNameBuilder` chưa?
- [ ] Parent DN có tồn tại và có đúng `ContextSource.base` không?
- [ ] `objectClass`, `MUST`/`MAY`, syntax và `SINGLE-VALUE` đã được kiểm tra chưa?
- [ ] Service account có đúng ACL Add/Read/Modify cần thiết không?
- [ ] Simple Bind có được bảo vệ bằng LDAPS/StartTLS và hostname verification không?
- [ ] Password/secret có tránh hard-code, log và lưu cache không?
- [ ] Có phân biệt lỗi authentication với lỗi Add/schema/ACL/network không?
- [ ] Có phân biệt `context.close()` với `unbind(entryDn)` không?
- [ ] Không dùng `rebind` như một phép Modify an toàn khi chưa xác minh provider?
- [ ] Có integration test riêng cho Bind và Add trên directory test không?

## 17. Bài tập vận dụng

1. Giải thích vì sao hai dòng `contextSource.getContext(dn,password)` và `ldapTemplate.bind(dn,null,attrs)` đều có chữ bind nhưng một dòng xác thực còn dòng kia tạo entry.
2. Vẽ sequence diagram gồm TCP, TLS, BindRequest, AddRequest và AddResponse cho luồng tạo user bằng service account.
3. Một lập trình viên gọi `InitialDirContext.bind` để “kiểm tra password user”. Hãy chỉ ra operation thực tế và sửa luồng.
4. Thiết kế service provision user sử dụng `LdapTemplate.bind`; liệt kê DN, objectClass, MUST attributes và ACL cần có.
5. Thiết kế luồng đăng nhập: tìm DN theo UID bằng service account, sau đó Bind bằng credential người dùng. Những lỗi nào cần được phân loại?
6. Tại sao `ldapTemplate.bind` thành công không có nghĩa user đăng nhập được? Nêu các yếu tố password policy và auth.
7. So sánh `bind`, `rebind`, `unbind`, `modifyAttributes` và `rename`. API nào là Add, Delete, Modify và Modify DN?
8. Một lần Add timeout. Vì sao không thể retry vô hạn? Làm sao kiểm tra entry có được tạo trước khi retry?
9. Tại sao không đọc `userPassword` rồi so sánh chuỗi người dùng gửi? Hãy đề xuất cách xác thực phù hợp.
10. Giải thích vì sao Bind thành công không tự cấp quyền Search/Read/Add.
11. Thiết kế test chứng minh `context.close()` không xóa entry, còn `unbind(dn)` thì xóa entry.
12. Nếu ứng dụng dùng một pool context cho service account và user cuối, phân tích rủi ro authentication state bị chia sẻ sai.

## 18. Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `BindRequest`/`BindResponse`, `AddRequest`/`AddResponse`, Modify, Delete và result codes.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): Simple Bind, SASL, TLS và bảo vệ credential.
- [Oracle Java SE 17 — Context](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html): naming `bind`, `rebind`, `unbind` và `close`.
- [Oracle Java SE 17 — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): `bind(Name,Object,Attributes)` và thao tác directory.
- [Oracle JNDI LDAP — Authentication](https://docs.oracle.com/javase/jndi/tutorial/ldap/security/auth.html): cấu hình principal, credentials và authentication mechanisms.
- [Oracle JNDI LDAP — SSL](https://docs.oracle.com/javase/jndi/tutorial/ldap/security/ssl.html): LDAPS/JSSE và truststore.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `bind`, `rebind`, `unbind`, `create` và thao tác LDAP.
- [Spring LDAP — ContextSource Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, service credentials và cách tạo context.
- [Spring LDAP — ODM](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@DnAttribute`, `@Attribute` và entity create.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): `LdapRepository` và CRUD trên entry.
- [Spring Security LDAP](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): authentication với LDAP, Bind authentication và cấu hình bảo mật.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute, schema, objectClass và naming.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escape DN và filter đúng cú pháp.
