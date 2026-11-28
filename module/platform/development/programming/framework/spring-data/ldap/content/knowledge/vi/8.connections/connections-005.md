# Truyền thuộc tính môi trường cho JNDI

Khi ứng dụng **Spring Data LDAP** truy cập một LDAP directory, thao tác thường đi qua nhiều tầng: repository hoặc **LdapTemplate** của Spring, **ContextSource** quản lý context, rồi đến **JNDI LDAP provider** trong JDK. JNDI cần biết sẽ kết nối tới máy chủ nào, xác thực ra sao, có giới hạn thời gian chờ hay không, cách xử lý referral và những thuộc tính LDAP nào phải đọc dưới dạng nhị phân. Các thiết lập đó được chuyển tới provider dưới dạng **JNDI environment properties**.

Bài học thuộc chương **Kết nối** và tập trung vào việc truyền đúng các thuộc tính môi trường từ **Java**, **Spring LDAP** và **Spring Boot**. Người học sẽ biết phân biệt thuộc tính chuẩn của JNDI với thuộc tính riêng của LDAP provider, cấu hình **LdapContextSource**, bảo vệ mật khẩu bind, kiểm chứng timeout, đọc thuộc tính nhị phân như **objectGUID** của Active Directory, chẩn đoán lỗi khi cấu hình không có hiệu lực và xác minh bằng integration test.

> **Ý chính:** Một thuộc tính môi trường JNDI là cấu hình cho **client/provider**, không phải attribute của một LDAP entry. Việc khai báo một key trong environment không tạo ra **DN, objectClass**, dữ liệu người dùng hoặc quyền **ACL** trên server.

## 1. JNDI environment nằm ở đâu trong Spring Data LDAP?

**JNDI (Java Naming and Directory Interface)** là API Java dùng để truy cập các dịch vụ naming và directory. Khi làm việc với LDAP, provider mặc định của JDK dùng thông tin environment để tạo **DirContext/LdapContext** và thực hiện các thao tác như **search**, **lookup**, **bind**, **modify**, **add** và **delete**.

~~~mermaid
flowchart TB
  A["Spring service"] --> B["Spring Data LDAP: LdapRepository"]
  A --> C["Spring LDAP: LdapTemplate"]
  B --> C
  C --> D["ContextSource: LdapContextSource"]
  E["JNDI environment: URL, auth, timeout, referral, binary attrs"] --> D
  D --> F["JNDI provider của JDK"]
  F --> G[("LDAP server: schema, DN, ACL, entry")]
  H["Spring Boot: spring.ldap.* + base-environment"] -. "Cấu hình bean" .-> D
~~~

| Thành phần | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Spring Data LDAP Repository** | Ánh xạ entry vào domain object, hỗ trợ phương thức repository | **findByUid(...)**, **save(...)** |
| **LdapTemplate** | Gửi truy vấn hoặc thao tác LDAP với các API linh hoạt | **search(...)**, **modifyAttributes(...)** |
| **ContextSource** | Cấp context theo base DN, endpoint và thông tin xác thực | **LdapContextSource** |
| **JNDI environment** | Cấu hình cách client/provider thiết lập và sử dụng context | **java.naming.provider.url**, **com.sun.jndi.ldap.read.timeout** |
| **LDAP server** | Xác thực bind, thực thi truy vấn theo schema/ACL, trả entry | OpenLDAP, Active Directory |

Sơ đồ này giúp tránh một hiểu lầm: **LdapRepository không có bộ thuộc tính mạng tách biệt với mọi cấu hình khác**. Khi repository và LdapTemplate dùng chung ContextSource/JNDI provider, những thuộc tính môi trường mà ContextSource chuyển vào JNDI thường tác động đến cả hai.

## 2. Environment của InitialDirContext là gì?

JNDI dùng một tập cặp **tên thuộc tính → giá trị** khi khởi tạo context. API thường gặp là:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

Hashtable<String, Object> environment = new Hashtable<>();
environment.put(
    Context.INITIAL_CONTEXT_FACTORY,
    "com.sun.jndi.ldap.LdapCtxFactory"
);
environment.put(
    Context.PROVIDER_URL,
    "ldaps://ldap.lab.example:636"
);

DirContext context = new InitialDirContext(environment);
try {
    // LDAP lookup/search/modify...
} finally {
    context.close();
}
~~~

Đoạn mã minh họa cách truyền environment; trong ví dụ chạy thật sẽ cần chính sách **bind**, CA/truststore, kiểm tra TLS và xử lý lỗi phù hợp. Mỗi thuộc tính có **ngữ nghĩa riêng**, và kiểu giá trị được provider chấp nhận có thể khác nhau.

### 2.1. Nhóm thuộc tính JNDI chuẩn

Các key này được định nghĩa bằng hằng số trong **javax.naming.Context**:

| Hằng số Java | Giá trị key | Ý nghĩa |
| --- | --- | --- |
| **Context.INITIAL_CONTEXT_FACTORY** | **java.naming.factory.initial** | Chọn initial context factory, với LDAP provider JDK thường là **com.sun.jndi.ldap.LdapCtxFactory** |
| **Context.PROVIDER_URL** | **java.naming.provider.url** | Địa chỉ dịch vụ LDAP, ví dụ **ldaps://ldap.lab.example:636** |
| **Context.SECURITY_AUTHENTICATION** | **java.naming.security.authentication** | Cơ chế xác thực, ví dụ **simple** hoặc SASL mechanism được hỗ trợ |
| **Context.SECURITY_PRINCIPAL** | **java.naming.security.principal** | Danh tính để bind, thường là DN của tài khoản dịch vụ |
| **Context.SECURITY_CREDENTIALS** | **java.naming.security.credentials** | Thông tin xác thực; không được log hoặc commit vào source |
| **Context.REFERRAL** | **java.naming.referral** | Chính sách xử lý LDAP referral: **follow**, **throw**, **ignore** |
| **Context.SECURITY_PROTOCOL** | **java.naming.security.protocol** | Thuộc tính bảo mật theo JNDI provider; không thay thế cấu hình TLS/truststore một cách tùy tiện |

**javax.naming** vẫn là package của JNDI trong JDK hiện đại, kể cả khi dự án Spring dùng những package **jakarta.*** ở các tầng khác. JNDI thuộc module Java **java.naming**, không phải dependency Maven phải cài riêng.

### 2.2. Nhóm thuộc tính riêng của LDAP provider JDK

Đây không phải các hằng số trong Context, mà là tên key provider-specific:

| Key | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| **com.sun.jndi.ldap.connect.timeout** | **"3000"** | Giới hạn chờ mở kết nối TCP; có thể ảnh hưởng việc chờ mượn kết nối từ native JNDI pool |
| **com.sun.jndi.ldap.read.timeout** | **"5000"** | Giới hạn chờ phản hồi LDAP |
| **java.naming.ldap.attributes.binary** | **"objectGUID objectSid"** | Yêu cầu nhận các attribute này dưới dạng **byte[]** từ provider |
| **com.sun.jndi.ldap.connect.pool** | **"true"** | Yêu cầu native LDAP connection pooling trong điều kiện được provider hỗ trợ |

Các giá trị timeout ở đây tính bằng **mili giây** và truyền dạng **chuỗi số**; không truyền **"3s"** hoặc **"PT3S"** với hai key timeout này. Tránh áp dụng pooling mặc định nếu ứng dụng có **StartTLS**, thay đổi trạng thái xác thực hoặc yêu cầu bảo mật đặc biệt; cần hiểu điều kiện tương thích của provider và kiểm thử cụ thể.

**Tính di động:** key **com.sun.jndi.ldap.*** phản ánh cách hoạt động của LDAP provider JDK, không phải một phần của LDAP protocol. Nếu ứng dụng chuyển sang LDAP SDK khác, có thể cần cấu hình tương đương bằng API riêng của SDK đó.

## 3. Phân biệt JNDI environment, Spring config và thuộc tính LDAP entry

Ba loại “thuộc tính” dưới đây thường dễ bị lẫn:

| Loại | Nơi xuất hiện | Ví dụ | Chức năng |
| --- | --- | --- | --- |
| **Environment JNDI** | Hashtable hoặc ContextSource base environment | **com.sun.jndi.ldap.read.timeout** | Điều chỉnh hành vi client/provider |
| **Spring application properties** | application.yml / application.properties | **spring.ldap.urls**, **spring.ldap.base** | Cấu hình bean do Spring Boot quản lý |
| **LDAP entry attributes** | Dữ liệu directory theo DN và objectClass | **uid**, **cn**, **sn**, **mail**, **member** | Là thông tin nghiệp vụ được LDAP server lưu và trả về |

Ví dụ, thêm:

~~~text
com.sun.jndi.ldap.read.timeout = 5000
~~~

chỉ tác động đến việc chờ phản hồi. Nó **không thêm** thuộc tính **read.timeout** vào một LDAP entry. Ngược lại, thêm **@Attribute(name = "mail")** vào Java entity không làm thay đổi thuộc tính môi trường của ContextSource.

Phân biệt này đặc biệt quan trọng khi làm CRUD: cấu hình timeout có thể giúp kết nối thất bại sớm, nhưng các thao tác **save** vẫn phải tuân theo **schema**, **DN**, **objectClass** và **ACL** trên directory server.

## 4. Khởi tạo JNDI trực tiếp với môi trường đầy đủ

Ví dụ một chương trình Java thực hiện search người dùng với **simple bind qua LDAPS**, đặt timeout, referral policy và filter có tham số:

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

public final class JndiEnvironmentExample {
    private JndiEnvironmentExample() {}

    public static void main(String[] args) throws NamingException {
        String password = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "LDAP_BIND_PASSWORD is required"
        );

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
            "ldaps://ldap.lab.example:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
            "uid=reader,ou=services,dc=lab,dc=example");
        env.put(Context.SECURITY_CREDENTIALS, password);

        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");
        env.put(Context.REFERRAL, "throw");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[]{"uid", "cn", "mail"});
        controls.setCountLimit(100);
        controls.setTimeLimit(4000);

        DirContext ctx = null;
        NamingEnumeration<SearchResult> cursor = null;
        try {
            ctx = new InitialDirContext(env);
            cursor = ctx.search(
                "ou=people,dc=lab,dc=example",
                "(uid={0})",
                new Object[]{"linh"},
                controls
            );

            while (cursor.hasMore()) {
                SearchResult result = cursor.next();
                System.out.println(result.getNameInNamespace());
            }
        } finally {
            try {
                if (cursor != null) {
                    cursor.close();
                }
            } finally {
                if (ctx != null) {
                    ctx.close();
                }
            }
        }
    }
}
~~~

**Giải thích:**

1. **Context.INITIAL_CONTEXT_FACTORY** xác định cách khởi tạo context. Đừng dùng một factory của provider khác khi ý định là LDAP provider trong JDK.
2. **Context.PROVIDER_URL** dùng endpoint **ldaps://**. Máy chủ và chứng chỉ phải hợp lệ với truststore JVM; JNDI environment không tự cài đặt CA tin cậy.
3. **SECURITY_PRINCIPAL** là DN dùng để bind; **SECURITY_CREDENTIALS** được lấy từ biến môi trường, không hardcode hoặc log.
4. **connect.timeout** và **read.timeout** giới hạn hai giai đoạn khác nhau, không phải deadline tổng của toàn bộ thao tác.
5. **Context.REFERRAL = "throw"** yêu cầu chương trình tự nhận biết referral qua exception thay vì tự đi theo server khác; xử lý thực tế phụ thuộc provider và kết quả server.
6. **controls.setTimeLimit(...)** đặt **search time limit**, khác hai timeout trên.
7. **(uid={0})** với filter arguments giúp provider escape input theo cú pháp LDAP filter, an toàn hơn ghép chuỗi tùy ý.
8. Đóng **NamingEnumeration** và **DirContext** trong **finally**, kể cả khi xảy ra lỗi mạng hoặc LDAP exception.

**Không sử dụng mẫu simple bind qua ldap:// không mã hóa trên mạng thực.** Nếu tổ chức dùng StartTLS thay vì LDAPS, phải thực hiện StartTLS và xác minh TLS đúng trình tự trước khi gửi mật khẩu.

## 5. Spring LDAP: chuyển environment qua LdapContextSource

Phần lớn ứng dụng Spring Data LDAP không trực tiếp tạo **InitialDirContext** ở mỗi request. Chúng dùng **LdapContextSource** làm nguồn context chung. Để truyền thuộc tính bổ sung tới JNDI provider, Spring LDAP cung cấp phương thức **setBaseEnvironmentProperties(...)**.

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class DirectoryLdapConfiguration {
    @Bean
    LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        Map<String, Object> extra = new HashMap<>();
        extra.put("com.sun.jndi.ldap.connect.timeout", "3000");
        extra.put("com.sun.jndi.ldap.read.timeout", "5000");
        extra.put("java.naming.referral", "throw");

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setBaseEnvironmentProperties(extra);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

Ví dụ có cấu hình riêng cho bean trên (dùng **thay thế** auto-configuration LDAP tương ứng):

~~~yaml
directory:
  ldap:
    url: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    bind-dn: "uid=reader,ou=services,dc=lab,dc=example"
    bind-password: "${LDAP_BIND_PASSWORD}"
~~~

Spring quản lý lifecycle bean và thực hiện bước khởi tạo cần thiết của **LdapContextSource**. Nếu dùng bean như một đối tượng tạo thủ công ngoài Spring, phải tự thực hiện quá trình khởi tạo mà API yêu cầu.

### 5.1. Vì sao dùng setBaseEnvironmentProperties?

Spring LDAP xây dựng context với thông tin endpoint, base DN, tài khoản bind và các thuộc tính nền. **setBaseEnvironmentProperties** cho phép cung cấp thêm thuộc tính tới JNDI LDAP provider mà không phải tự tạo Hashtable lặp lại ở từng service.

Không cần đặt lại tất cả thông tin xác thực vào map này nếu đã gọi **setUserDn(...)** và **setPassword(...)**. Đặc biệt, tránh cấu hình **SECURITY_CREDENTIALS** ở nhiều nơi rồi không rõ giá trị nào được áp dụng.

**Chú ý:** Nếu ứng dụng Spring Boot đang tự tạo bean **LdapContextSource** hoặc sử dụng nhiều ContextSource, cần xác định rõ repository và template dùng bean nào. Việc thêm timeout vào **một** bean không tự truyền nó tới mọi context khác.

### 5.2. ContextSource base và tên DN tương đối

Giả sử:

~~~text
LdapContextSource base = dc=lab,dc=example
LDAP entry DN          = uid=linh,ou=people,dc=lab,dc=example
~~~

Trong **LdapTemplate**, base tìm kiếm có thể là:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

query().base("ou=people").where("uid").is("linh");
~~~

Nhưng khi dùng **DirContext.search(...)** trực tiếp trên **InitialDirContext** được tạo bằng URL mà không đặt base chung, lệnh thường cần DN đầy đủ **ou=people,dc=lab,dc=example**. Nhầm hai cơ chế có thể tạo **DN lặp suffix**, dẫn tới **noSuchObject (32)**; đó không phải lỗi do timeout hay do thuộc tính môi trường bị bỏ qua.

## 6. Spring Boot: spring.ldap.base-environment

Với **Spring Boot** có starter LDAP phù hợp, các thuộc tính bổ sung của JNDI có thể truyền qua **spring.ldap.base-environment**. Ví dụ hoàn chỉnh:

~~~yaml
spring:
  ldap:
    urls:
      - "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    username: "uid=reader,ou=services,dc=lab,dc=example"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
      "[java.naming.referral]": "throw"
~~~

Trong ví dụ, **spring.ldap.urls**, **base**, **username**, **password** là cấu hình Spring Boot dành cho nguồn LDAP; **base-environment** chứa các key bổ sung của JNDI.

**Vì sao key có dấu ngoặc vuông và được đặt trong dấu nháy?** Cơ chế binding từ YAML sang **Map** của Spring Boot có quy tắc xử lý tên key. Với tên có dấu chấm như **com.sun.jndi.ldap.read.timeout**, cú pháp **"[...]"** giúp giữ nguyên key khi binding, tránh việc đổi/diễn giải sai tên thuộc tính vốn phải khớp chính xác với JNDI provider.

### 6.1. Tương đương với application.properties

~~~properties
spring.ldap.urls=ldaps://ldap.lab.example:636
spring.ldap.base=dc=lab,dc=example
spring.ldap.username=uid=reader,ou=services,dc=lab,dc=example
spring.ldap.password=${LDAP_BIND_PASSWORD}
spring.ldap.base-environment.[com.sun.jndi.ldap.connect.timeout]=3000
spring.ldap.base-environment.[com.sun.jndi.ldap.read.timeout]=5000
spring.ldap.base-environment.[java.naming.referral]=throw
~~~

Không áp dụng cùng lúc cấu hình bean tùy biến ở phần 5 và auto-configuration ở phần này mà không biết bean nào thực sự được dùng. **Một nguồn cấu hình nhất quán** giúp tránh các lỗi “đã chỉnh file nhưng timeout không thay đổi”.

### 6.2. Map property không phải Duration

Các giá trị trong **base-environment** được truyền cho JNDI provider. Ví dụ:

~~~text
"3000" = 3000 milliseconds
"5000" = 5000 milliseconds
~~~

Không thay bằng **3s**, **5s** hay đối tượng **Duration** mà không kiểm tra provider. Khác với một số property thời gian của Spring Boot, hai key **com.sun.jndi.ldap.connect.timeout** và **com.sun.jndi.ldap.read.timeout** được JNDI LDAP provider xử lý như chuỗi số mili giây.

### 6.3. Profile và override cấu hình

Ở hệ thống có **dev/staging/prod**, các property có thể đến từ:

- File **application.yml** hoặc **application-{profile}.yml**.
- Biến môi trường, command-line argument hoặc hệ thống cấp secret.
- Cấu hình Spring Boot của một module hoặc bean tự khai báo.

Khi config không có hiệu lực, hãy kiểm tra profile đang chạy, property source được ưu tiên và ContextSource thật được inject, **không in ra toàn bộ configuration environment** vì có thể chứa mật khẩu bind.

## 7. Điều chỉnh referral bằng Context.REFERRAL

LDAP **referral** là thông tin từ server gợi ý client tìm entry ở LDAP server/naming context khác. Chúng thường xuất hiện trong directory có nhiều naming context hoặc phân chia cây.

~~~text
LDAP server A
  └── Trả referral tới LDAP server B
          └── Entry mà ứng dụng cần
~~~

JNDI provider nhận **Context.REFERRAL**:

| Giá trị | Ý nghĩa khái quát | Cần chú ý |
| --- | --- | --- |
| **follow** | Provider có thể tự theo referral | Có thể phát sinh kết nối sang endpoint khác; phải cân nhắc xác thực, TLS, timeout và trust |
| **throw** | Trả referral cho ứng dụng xử lý, thường qua **ReferralException** | Thích hợp nếu muốn kiểm soát rõ việc chuyển endpoint |
| **ignore** | Không tự theo referral theo cấu hình provider | Có thể dẫn tới **PartialResultException** hoặc hành vi khác tùy server/provider |

Ví dụ:

~~~java
environment.put(Context.REFERRAL, "throw");
~~~

Hoặc qua Spring Boot:

~~~yaml
spring:
  ldap:
    base-environment:
      "[java.naming.referral]": "throw"
~~~

**Không bật follow tùy tiện** trong hệ thống đa domain. Cần xác định server đích có đáng tin cậy không, chứng chỉ của nó có hợp lệ không, thông tin bind có được sử dụng hoặc chuyển tiếp như thế nào và có nguy cơ truy vấn vượt vùng dữ liệu được phép hay không. Một lần bind thành công vào server A không bảo đảm user có quyền trên server B.

### 7.1. Referral không tương đương search scope

**SearchScope.SUBTREE** mở rộng phạm vi trong cây từ base DN theo ngữ nghĩa search; nó không bảo đảm tự tìm trên mọi server hoặc mọi naming context. Nếu dữ liệu ở nơi được referral sang server khác, ứng dụng vẫn cần chính sách referral phù hợp.

## 8. Yêu cầu thuộc tính nhị phân đúng kiểu Java

Một số LDAP attributes chứa dữ liệu nhị phân như **jpegPhoto** hoặc **objectGUID** của **Active Directory**. Nếu provider chuyển dữ liệu thành String, mã Java có thể làm hỏng bytes hoặc gặp lỗi cast.

Với JNDI LDAP provider, thuộc tính:

~~~text
java.naming.ldap.attributes.binary = objectGUID objectSid
~~~

chỉ định danh sách thuộc tính cần được nhận dưới dạng **byte[]** (các tên phân tách bằng dấu cách).

Ví dụ cho ứng dụng Spring Boot kết nối AD:

~~~yaml
spring:
  ldap:
    urls: "ldaps://dc1.corp.example.com:636"
    base: "DC=corp,DC=example,DC=com"
    username: "CN=LDAP Reader,OU=Services,DC=corp,DC=example,DC=com"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[java.naming.ldap.attributes.binary]": "objectGUID objectSid"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

Khi JNDI trả về kết quả:

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

// 'attributes' lấy từ SearchResult.getAttributes().
Attribute objectGuid = attributes.get("objectGUID");
if (objectGuid == null) {
    throw new IllegalStateException("objectGUID not returned");
}

Object value = objectGuid.get();
if (!(value instanceof byte[] guidBytes) || guidBytes.length != 16) {
    throw new IllegalStateException("objectGUID must be 16 bytes");
}

// 'guidBytes' là byte[] trong định dạng binary của Active Directory.
~~~

Với **entryUUID** do OpenLDAP hỗ trợ RFC 4530, kết quả thường được đọc là **chuỗi UUID** nếu đã yêu cầu operational attribute đó. Không lấy converter byte của AD để áp dụng cho mọi identifier LDAP. Chú ý **objectGUID của AD có cách sắp byte riêng**: trước khi tạo **java.util.UUID** dạng văn bản, cần chuyển ba trường đầu theo little-endian, không đọc toàn bộ 16 byte như UUID big-endian.

**Không thêm objectGUID vào một file LDIF OpenLDAP thông thường** rồi hy vọng server hỗ trợ schema đó. Tên attribute, syntax và operational data khác nhau giữa các directory server.

### 8.1. Tham số binary và filter không phải một

**java.naming.ldap.attributes.binary** điều chỉnh cách client **trả giá trị attribute** về Java. Nó không tự viết filter đúng cho objectGUID. Nếu cần tìm theo GUID, phải mã hóa **16 byte theo định dạng AD** và dùng JNDI filter arguments **byte[]** hoặc biểu diễn octet-escaped chuẩn RFC 4515.

Do đó, trong môi trường AD, hai việc cần kiểm tra riêng là: **SearchResult nhận objectGUID dạng byte[]** và **filter tìm theo GUID được mã hóa đúng**.

## 9. Timeout: environment có tác động tới nhiều giai đoạn

Đặt hai key:

~~~java
env.put("com.sun.jndi.ldap.connect.timeout", "3000");
env.put("com.sun.jndi.ldap.read.timeout", "5000");
~~~

không có nghĩa mỗi lần repository tìm người dùng hoàn tất trong đúng 5 giây. Cần phân biệt:

~~~mermaid
sequenceDiagram
  participant App as Spring/JNDI client
  participant Net as TCP/TLS
  participant Ldap as LDAP server
  App->>Net: Kết nối TCP
  Note over App,Net: Connect timeout
  Net-->>App: Connected
  App->>Ldap: BindRequest
  Note over App,Ldap: Read timeout trong khi chờ BindResponse
  Ldap-->>App: BindResponse
  App->>Ldap: SearchRequest
  Note over App,Ldap: Read timeout khi chờ LDAP response
  Ldap-->>App: SearchResultEntry / Done
~~~

| Cơ chế | Định dạng | Điều gì được giới hạn? |
| --- | --- | --- |
| **connect.timeout** | Chuỗi mili giây | Thời gian chờ mở TCP; một số tình huống chờ native pool |
| **read.timeout** | Chuỗi mili giây | Thời gian chờ LDAP response từ provider |
| **SearchControls.setTimeLimit** | Số nguyên mili giây | Giới hạn một lần LDAP Search ở tầng search API/provider |
| **Timeout ở HTTP/job** | Tùy framework | Deadline tổng của tác vụ theo chính sách ứng dụng |

Ví dụ **SearchControls.setTimeLimit(4000)** không phải một JNDI environment property. Nó được đặt trên đối tượng điều khiển tìm kiếm, chỉ tác động tới thao tác search đang sử dụng SearchControls đó.

**Lưu ý:** Có thể có nhiều LDAP response trên một search, nhiều URL dự phòng, DNS/TLS và connection pool. Các timeout này không phải một deadline tổng cộng; đo thời gian thực tế và áp dụng giới hạn cấp ứng dụng khi có SLA.

## 10. Native connection pooling: không nhầm property

JNDI provider có cơ chế native LDAP connection pooling. Khi dùng, cần phân biệt:

| Thuộc tính | Phạm vi | Vai trò |
| --- | --- | --- |
| **com.sun.jndi.ldap.connect.pool** | Property trên JNDI context | Yêu cầu context sử dụng native pooling nếu đủ điều kiện |
| **com.sun.jndi.ldap.connect.pool.maxsize** | JVM system property của provider | Giới hạn số kết nối trong pool theo cấu hình |
| **com.sun.jndi.ldap.connect.pool.prefsize** | JVM system property | Số kết nối ưu tiên trong pool |
| **com.sun.jndi.ldap.connect.pool.timeout** | JVM system property | Thời gian idle trước khi pool có thể giải phóng connection |
| **com.sun.jndi.ldap.connect.timeout** | JNDI environment | Giới hạn mở TCP và một số tình huống chờ pool |

Một số thuộc tính cấu hình pool được đọc như **JVM system properties**, **không phải** key mà chỉ cần bỏ vào **spring.ldap.base-environment**. Ví dụ khởi chạy JVM:

~~~bash
java -Dcom.sun.jndi.ldap.connect.pool.maxsize=20 \
     -Dcom.sun.jndi.ldap.connect.pool.prefsize=5 \
     -jar application.jar
~~~

Chỉ dùng giá trị này như ví dụ cú pháp; sizing pool phải được tính theo tải và giới hạn directory thực tế. **Không dùng native pooling chỉ vì có nhiều request** nếu chưa xem điều kiện hỗ trợ **TLS/StartTLS**, bind identity và các cơ chế quản lý context.

### 10.1. StartTLS và pooling

**StartTLS** nâng cấp một kết nối LDAP thường lên TLS; nó có thể thay đổi trạng thái socket và bảo mật của context. Native JNDI pooling không nhất thiết theo dõi các thay đổi này để tái sử dụng an toàn. Theo hướng dẫn provider của Oracle, cần tránh pooling context mà trạng thái bảo mật bị thay đổi theo cách provider không thể quản lý.

Nếu dùng **LDAPS**, **StartTLS**, custom socket factory hoặc SASL, hãy xem tài liệu JDK và Spring LDAP đúng phiên bản, thử lifecycle của context trong integration test và xác minh certificate/hostname. Không bật native pooling bằng một thuộc tính rồi mặc định mọi mode xác thực đều tương thích.

## 11. Repository và LdapTemplate nhận environment từ đâu?

Ví dụ entity:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
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

    // Constructors và getters/setters được lược bỏ.
}
~~~

Repository:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Khi service gọi:

~~~java
Optional<DirectoryPerson> result =
    personRepository.findByUid("linh");
~~~

đường đi thông thường là **repository → Spring LDAP → ContextSource → JNDI**. Nếu ContextSource đã nhận **read timeout** hoặc **referral policy**, những yêu cầu repository gửi qua context đó cũng chịu ảnh hưởng của cấu hình client tương ứng.

Điều cần ghi nhớ:

- **@Id** trong Spring LDAP ODM đại diện cho **DN** của entry, không phải UUID hoặc số tự tăng.
- **@Entry(base = "ou=people")** chỉ định nhánh tương đối với **ContextSource base**, không định nghĩa một môi trường JNDI mới.
- **@Attribute(name = "uid")** ánh xạ attribute của entry sang Java field, **không** điều khiển JNDI bind hay timeout.
- Nếu **PersonRepository** và **LdapTemplate** được cung cấp từ các ContextSource khác nhau, có thể xuất hiện sự khác biệt về endpoint, bind DN, ACL, timeout và referral.
- Một bean repository được khởi tạo thành công **không chứng minh** LDAP server có thể truy cập. Kết nối thực có thể chỉ được mở khi thao tác đầu tiên chạy.

## 12. Thử xác minh environment thực sự có hiệu lực

Khi một property không tác động đến ứng dụng, nên kiểm tra từ lớp **Spring configuration** xuống **LDAP request** thay vì tăng giá trị một cách ngẫu nhiên.

### 12.1. Kiểm tra những property không nhạy cảm

Trong integration test với **ContextSource** đã cấu hình và LDAP server hoạt động, có thể kiểm tra environment của context được tạo:

~~~java
import java.util.Hashtable;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;
import static org.junit.jupiter.api.Assertions.assertEquals;

// Trong method @Test có 'contextSource' được inject.
DirContext context = contextSource.getReadOnlyContext();
try {
    Hashtable<?, ?> env = context.getEnvironment();
    assertEquals("3000",
        env.get("com.sun.jndi.ldap.connect.timeout"));
    assertEquals("5000",
        env.get("com.sun.jndi.ldap.read.timeout"));
} finally {
    context.close();
}
~~~

**Không log nguyên Hashtable của getEnvironment()**, vì nó có thể chứa **SECURITY_CREDENTIALS** hoặc thông tin xác thực khác. Khi kiểm tra, chỉ đọc những key đã được phép công bố và không chuyển giá trị environment vào HTTP response.

Việc environment có đúng key là **điều kiện cấu hình**, chưa chứng minh provider thực sự giới hạn một lần TCP connect hoặc LDAP read đúng thời gian. Muốn kiểm chứng hành vi timeout, phải có tình huống mạng/server bị trì hoãn có kiểm soát.

### 12.2. Mẫu kiểm thử tích hợp một thao tác truy vấn

Với **LdapTemplate** nhận cùng ContextSource:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonLookup {
    private final LdapTemplate ldapTemplate;

    public PersonLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> namesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .attributes("uid", "cn")
                   .where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Nếu **ldapsearch** với đúng bind identity tìm thấy người dùng, còn template trả lỗi **noSuchObject (32)**, hãy so sánh **ContextSource base**, DN tương đối và endpoint, không vội cho rằng read timeout đang gây lỗi.

### 12.3. Ma trận kiểm thử environment

| Tình huống | Điều khiển trong lab | Kết quả mong đợi |
| --- | --- | --- |
| ContextSource hoạt động | Directory có một entry giả và bind DN hợp lệ | Query trả đúng dữ liệu |
| Chờ TCP connect | Proxy mạng mô phỏng kết nối không hoàn tất | Connect timeout được quan sát theo provider |
| Chờ BindResponse | LDAP test double nhận TCP nhưng không trả bind | Read timeout hoặc lỗi liên lạc phù hợp |
| Bind được nhưng SearchResponse chậm | Server/proxy trì hoãn phản hồi | Read timeout hoặc search time limit |
| Referral | Server lab trả referral tới server khác | Chính sách **throw/follow/ignore** thể hiện đúng trong kết quả |
| AD objectGUID | Server AD test trả objectGUID | Nhận **byte[16]** khi binary property được áp dụng |
| Invalid credentials | Mật khẩu bind cố ý sai | Lỗi xác thực, không bị biến thành kết quả rỗng |
| Sai search base | Query OU không tồn tại | noSuchObject/NameNotFoundException phù hợp |
| ACL hạn chế | Bind bằng reader thiếu quyền | Không đọc được thuộc tính theo chính sách, không dùng admin để che lỗi |
| Nhiều ContextSource | Repository/template dùng bean khác nhau | Test phát hiện chênh lệch cấu hình/endpoint |

Với timeout, **một IP không sử dụng không bảo đảm gây timeout**: có thể trả lỗi **No route to host** hoặc **Connection refused** ngay. Muốn phép đo ổn định, dùng **test proxy/fault injector** có thể trì hoãn một giai đoạn cụ thể.

## 13. Lỗi thường gặp khi truyền environment

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Đặt timeout nhưng vẫn đợi rất lâu | Property nằm sai bean hoặc không được chuyển vào JNDI; lần chờ là DNS/TLS/nhiều URL | Kiểm tra profile, ContextSource, provider và thí nghiệm có kiểm soát |
| **Connect timeout** không giới hạn toàn request | Nó chỉ liên quan giai đoạn kết nối, không phải deadline tổng | Đặt chính sách deadline cấp API/job riêng |
| Dùng **3s** nhưng không thấy hiệu lực | JNDI provider cần chuỗi số mili giây | Dùng **"3000"** |
| Key có dấu chấm bị thay đổi khi Spring binding | Không dùng cú pháp bracket cho map key trong YAML/properties | Dùng **"[com.sun.jndi.ldap.read.timeout]"** |
| Repository timeout khác LdapTemplate | Hai bean dùng ContextSource khác nhau | Rà soát dependency injection/auto-config |
| **objectGUID** gây **ClassCastException** | Provider trả sai kiểu hoặc attribute chưa requested | Cấu hình **java.naming.ldap.attributes.binary**, kiểm tra byte[] |
| Referral gây lỗi ngoài ý muốn | Policy follow/throw/ignore không đúng yêu cầu | Xem topology và hành vi provider, không tự theo endpoint lạ |
| Pool không tuân theo maxsize trong environment | Pool maxsize là JVM system property | Đặt tại JVM và thử nghiệm với native JNDI pool |
| Bind thất bại khi đổi TLS | Truststore/certificate/StartTLS chưa đúng | Kiểm tra TLS; không tắt xác minh |
| Tìm kiếm rỗng dù bind thành công | Base DN, scope, filter, schema, ACL hoặc directory khác | So sánh LDAP search cùng danh tính trước khi đổi environment |
| Mật khẩu xuất hiện trong log | In toàn bộ environment hoặc cấu hình | Chỉ log whitelist, che credentials |
| Save sau timeout không rõ kết quả | Server có thể đã xử lý request nhưng response bị mất | Đối chiếu trạng thái và idempotency trước khi retry |

Một lỗi **CommunicationException** không có nghĩa chắc chắn phải tăng connect timeout. Nó có thể xuất hiện từ network failure, read timeout, TLS hoặc một giai đoạn liên lạc khác. Hãy đọc **cause chain** và thu thập các metric của kết nối, bind và search.

## 14. Bảo mật và vận hành với JNDI environment

Environment có thể chứa các bí mật quan trọng. Cần áp dụng các nguyên tắc:

1. **Secret:** chỉ cấp **SECURITY_CREDENTIALS** từ biến môi trường, secret manager hoặc một nguồn được bảo vệ; không hardcode password trong Java, LDIF hay repo.
2. **TLS:** dùng **LDAPS/StartTLS**, xác minh CA và tên máy chủ; không tắt TLS validation để “sửa” lỗi LDAP.
3. **Least privilege:** dùng bind DN có quyền search/read vừa đủ, tách tài khoản đọc và ghi nếu nghiệp vụ yêu cầu.
4. **Referral:** chỉ cho phép theo referral sang những server được tổ chức chấp thuận; xem xét nguy cơ lộ credentials.
5. **Filter escaping:** dùng **LdapQueryBuilder** hoặc JNDI filter arguments thay vì nối chuỗi từ input người dùng.
6. **DN escaping:** sử dụng **LdapName/Rdn** khi dựng DN từ dữ liệu động; filter escaping không thay thế DN escaping.
7. **Giới hạn tài nguyên:** đặt connect/read timeout, search time/size limit, base/search scope hợp lý và theo dõi pool.
8. **Observability:** chỉ ghi endpoint, mã lỗi, loại exception, thời gian, request ID và key environment đã được phép ghi; không dump toàn bộ context hoặc attributes nhạy cảm.

### 14.1. TLS truststore không thuộc LDAP entry schema

Đối với JDK, truststore/certificate thường được kiểm soát bằng **JSSE configuration** của JVM, chẳng hạn các hệ thống sử dụng system properties **javax.net.ssl.trustStore** và **javax.net.ssl.trustStorePassword** hoặc custom SSL context đã được thẩm định.

Không coi các property này là **LDAP attributes** hoặc mặc nhiên thêm chúng vào **spring.ldap.base-environment** rồi mong JSSE áp dụng. Khi sử dụng custom socket factory hoặc StartTLS, cách cài đặt TLS có thể khác; cần dùng API phù hợp, kiểm thử hostname/certificate verification và tránh tiết lộ thông tin truststore.

## 15. Quy trình thực hành đầy đủ

Giả sử directory lab:

~~~text
dc=lab,dc=example
├── ou=people
│   └── uid=linh
└── ou=services
    └── uid=reader
~~~

Trong nhánh people có entry tương ứng:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
~~~

Để hoàn thành bài thực hành:

1. **Chuẩn bị LDAP server lab** có suffix, các OU và tài khoản reader, với TLS hợp lệ.
2. **Chọn một con đường cấu hình:** Spring Boot **spring.ldap.base-environment** hoặc tự tạo **LdapContextSource**; không sao chép cả hai theo cách tạo bean mơ hồ.
3. **Đặt connect/read timeout** 3000/5000 ms; bảo đảm key là chuỗi đúng và môi trường chạy nhận chúng.
4. **Chạy ldapsearch** dưới chính bind identity ứng dụng để xác nhận DN/filter/ACL/dữ liệu trước khi chẩn đoán Java.
5. **Dùng LdapTemplate** đọc **uid=linh** từ **ou=people** bằng filter query builder.
6. **Ghi nhận kết quả và duration**, không in password, DN nhạy cảm hoặc mọi giá trị môi trường.
7. **Đổi referral policy** trong lab có referral thực, xác minh sự khác biệt và quyền đi tới server khác.
8. **Trên AD test**, yêu cầu objectGUID và kiểm tra bytes nếu bài học có cả backend AD.
9. **Kiểm thử fault injection** cho TCP stall và LDAP response stall; đối chiếu với timeout.
10. **Khôi phục cấu hình lab** và giữ test tự động để phát hiện thay đổi khi nâng cấp JDK/Spring.

Để xem dữ liệu từ terminal:

~~~bash
ldapsearch -LLL -x -H 'ldaps://ldap.lab.example:636' \
  -D 'uid=reader,ou=services,dc=lab,dc=example' -W \
  -b 'ou=people,dc=lab,dc=example' -s sub \
  '(uid=linh)' dn uid cn mail
~~~

Lệnh này dùng **OpenLDAP client**, không dùng JNDI provider nên **không thể tự chứng minh** các key **com.sun.jndi.ldap.*** có hiệu lực trong JVM. Nó chỉ cung cấp đối chứng về endpoint, bind identity, base DN, filter và dữ liệu/ACL.

## 16. Câu hỏi ôn tập

1. Thuộc tính môi trường JNDI khác thuộc tính của LDAP entry như **uid**, **cn**, **member** ở điểm nào?
2. **Context.PROVIDER_URL** và **spring.ldap.urls** có liên hệ gì, và hai tên thuộc về tầng nào?
3. Vì sao nên đưa các key bổ sung vào **LdapContextSource.setBaseEnvironmentProperties(...)** thay vì tạo Hashtable riêng tại mỗi service?
4. **spring.ldap.base-environment** và **spring.ldap.base** khác nhau như thế nào?
5. Vì sao key **"[com.sun.jndi.ldap.connect.timeout]"** được bọc bằng dấu ngoặc vuông trong YAML?
6. **connect timeout**, **read timeout** và **SearchControls.setTimeLimit** khác nhau ở đâu?
7. **Context.REFERRAL=follow** có những rủi ro bảo mật/vận hành nào?
8. Làm thế nào yêu cầu JNDI trả **objectGUID** dạng **byte[]** và vì sao không được cast thành String tùy ý?
9. Tại sao các thuộc tính **com.sun.jndi.ldap.connect.pool.maxsize** không thể được xem như một map key thông thường của mỗi LDAP context?
10. Nếu repository hoạt động bình thường nhưng LdapTemplate timeout, bạn sẽ kiểm tra điều gì ở ContextSource?
11. Có thể xác minh mọi timeout chỉ bằng cách kiểm tra getEnvironment() không? Vì sao?
12. Vì sao khi retry một thao tác LDAP Modify sau read timeout cần xác định kết quả trên server trước?

## 17. Ghi nhớ và tài liệu đối chiếu

**Ghi nhớ:** JNDI environment truyền các tham số để **LDAP client/provider** kết nối, xác thực và truy vấn directory. Với JNDI trực tiếp, cung cấp thuộc tính vào **Hashtable** khi tạo **InitialDirContext**. Với Spring LDAP, đưa các key bổ sung vào **LdapContextSource.setBaseEnvironmentProperties(...)**. Với Spring Boot, ưu tiên **spring.ldap.base-environment** khi dùng auto-configuration.

Hãy tách bạch **JNDI standard properties** như **java.naming.provider.url**, **java.naming.security.principal**, **java.naming.referral** khỏi **provider-specific properties** như **com.sun.jndi.ldap.connect.timeout**, **com.sun.jndi.ldap.read.timeout**, **java.naming.ldap.attributes.binary**. Đừng nhầm các key này với **DN, objectClass, LDAP filter** hoặc attribute của entry. Kiểm tra tính hiệu lực qua integration test thực tế, giữ bí mật credentials, bảo vệ TLS và chỉ cấp quyền LDAP cần thiết.

Tài liệu để đọc thêm:

- [Oracle JNDI — Context API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/Context.html): các thuộc tính environment chuẩn như factory, provider URL, authentication và referral.
- [Oracle JNDI — InitialDirContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/InitialDirContext.html): tạo context với environment.
- [Oracle JNDI LDAP Service Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): connect/read timeout, referral, binary attrs và các thuộc tính riêng.
- [Oracle JNDI LDAP Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html): điều kiện, system properties và vòng đời pool.
- [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): ContextSource, LdapTemplate và truy vấn LDAP.
- [Spring LDAP — AbstractContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): **setBaseEnvironmentProperties**.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): **spring.ldap.base-environment** và các LDAP connection properties.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): mapping DN/entry và repository.
- [RFC 4511 — LDAPv3](https://www.rfc-editor.org/rfc/rfc4511.html): các thao tác bind, search, modify và LDAP result codes.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp và escaping filter.
