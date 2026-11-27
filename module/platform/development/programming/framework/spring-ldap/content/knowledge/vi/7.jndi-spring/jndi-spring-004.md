# LdapContextSource và cấu hình URL, base, user, password

Trong một ứng dụng dùng **Spring LDAP**, bước đầu tiên để đọc hoặc cập nhật thư mục là xác định **máy chủ LDAP**, **gốc tên được dùng trong ứng dụng** và **danh tính dùng để kết nối**. Các thông tin này thường nằm trong `LdapContextSource`, thành phần nối giữa cách lập trình quen thuộc của Spring và API JNDI do Java cung cấp.

Bài học thuộc chương **JNDI và Spring** của SPRING_LDAP. Trọng tâm là cấu hình bốn giá trị `URL`, `base`, `user DN` và `password`; sau đó sử dụng cấu hình đó qua `LdapTemplate`, hiểu những gì xảy ra khi bind, chọn kết nối TLS an toàn và chẩn đoán lỗi cơ bản. Những kiến thức này là nền tảng trước khi tìm kiếm bằng filter, mapping entry, xác thực người dùng, quản lý pooling hoặc thử nghiệm với LDAP server thật.

## 1. Từ JNDI đến `LdapContextSource`

**JNDI** (*Java Naming and Directory Interface*) là API Java để thao tác với dịch vụ tên và thư mục. Khi truy cập LDAP qua JNDI, ứng dụng thường làm việc với `DirContext` hoặc `LdapContext`, cấu hình môi trường kết nối và tự quản lý vòng đời context.

Ví dụ cách tiếp cận JNDI trực tiếp:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

String passwordFromSecretStore = System.getenv("LDAP_BIND_PASSWORD");
Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
        "cn=app-reader,ou=services,dc=example,dc=org");
env.put(Context.SECURITY_CREDENTIALS, passwordFromSecretStore);

DirContext context = new InitialDirContext(env);
try {
    // Tìm kiếm, đọc hoặc thao tác LDAP tại đây.
} finally {
    context.close();
}
~~~

Ở ví dụ này, ứng dụng phải tự khởi tạo context, đóng tài nguyên và xử lý exception. Đối với ứng dụng lớn, lặp lại các bước trên trong từng service dễ dẫn đến cấu hình không nhất quán.

Spring LDAP tách trách nhiệm:

~~~mermaid
flowchart TD
    A["Business service / Repository"] --> B["LdapTemplate hoặc LdapClient"]
    B --> C["ContextSource"]
    C --> D["LdapContextSource"]
    D --> E["JNDI DirContext"]
    E --> F[("LDAP server")]
    F --> E
    E --> B
    B --> A
~~~

- **`ContextSource`** là interface của Spring LDAP cung cấp context để truy cập thư mục.
- **`LdapContextSource`** là triển khai thường dùng, chứa cấu hình kết nối LDAP và tạo các JNDI context phù hợp.
- **`LdapTemplate`** sử dụng `ContextSource` để chạy thao tác, quản lý tài nguyên và chuyển các lỗi JNDI sang hệ thống exception của Spring LDAP.
- **`LdapClient`**, khi có trong phiên bản thư viện đang dùng, cung cấp một cách gọi API thao tác LDAP khác nhưng vẫn dựa trên cấu hình kết nối tương ứng.
- Mapper hoặc **ODM** quyết định cách entry được biểu diễn trong Java; chúng không thay thế việc cấu hình kết nối.

Trong ứng dụng thông thường, service nên phụ thuộc vào `LdapTemplate` hoặc API truy cập LDAP, thay vì tự tạo một `InitialDirContext` mới cho từng request.

## 2. Bốn thành phần cấu hình chính

Giả sử hệ thống quản lý tài khoản nhân sự trên server có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Cấu hình kết nối ví dụ:

| Thuộc tính | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| **URL** | `ldaps://ldap.example.org:636` | Chỉ ra server LDAP và cơ chế kết nối |
| **base** | `dc=example,dc=org` | Gốc DN tương đối cho các thao tác của ứng dụng |
| **user DN** | `cn=app-reader,ou=services,dc=example,dc=org` | Danh tính mà ứng dụng dùng khi bind |
| **password** | Giá trị đọc từ secret store | Chứng thực danh tính bind đó |

Đừng đánh đồng **user DN của tài khoản dịch vụ** với **DN của người dùng đang đăng nhập**. Tài khoản dịch vụ được dùng để tra cứu dữ liệu theo ACL của LDAP server; việc kiểm tra mật khẩu của An hoặc Bình là thao tác xác thực riêng.

Cũng đừng nhầm **base DN** với user DN. Base DN liên quan tới cách đặt tên của thao tác tìm kiếm/đọc/ghi; user DN là danh tính dùng để xác thực kết nối.

## 3. Cấu hình URL: máy chủ và giao thức

`LdapContextSource` nhận URL như:

~~~text
ldap://ldap.example.org:389
ldaps://ldap.example.org:636
~~~

- `ldap://` thường bắt đầu bằng kết nối LDAP chưa mã hóa; có thể nâng cấp bảo mật bằng **StartTLS** nếu client và server hỗ trợ và ứng dụng cấu hình đúng.
- `ldaps://` sử dụng LDAP qua TLS ngay từ khi kết nối; cổng 636 là cổng thường dùng.
- URL phải có **hostname** và **port** đúng theo hạ tầng. Nếu có firewall, DNS, reverse proxy hoặc load balancer, việc kết nối thành công còn tùy cấu hình các thành phần đó.

**URL đúng chưa đủ để bảo đảm an toàn.** Với LDAPS, ứng dụng cần xác minh chứng chỉ server, chuỗi tin cậy đến CA và tên máy chủ trong chứng chỉ. Tránh tắt kiểm tra chứng chỉ để xử lý nhanh lỗi TLS trong môi trường thật.

### Một hay nhiều LDAP endpoint?

Một `LdapContextSource` có thể được cấu hình một URL hoặc nhiều URL theo API và phiên bản đang dùng, ví dụ `setUrl(...)` hoặc `setUrls(...)`. Với nhiều URL, hành vi thử lại/failover phụ thuộc provider JNDI và cách các server được cấu hình. Không nên coi danh sách URL tự động đồng nghĩa với load balancing, health checking hay chuyển đổi liên tục giữa các node.

Nếu hệ thống có nhiều LDAP server, cần kiểm tra chúng có cùng naming context, schema, dữ liệu và quyền truy cập hay không. Nếu không, một query giống hệt có thể cho kết quả khác nhau theo endpoint.

### TLS và thông tin xác thực

Bind kiểu `simple` thường gửi username và mật khẩu theo cơ chế xác thực đơn giản của LDAP. **Chỉ dùng simple bind trên kênh đã được bảo vệ bằng TLS đáng tin cậy** khi có mật khẩu thật. Mật khẩu nên được nạp từ biến môi trường hoặc hệ thống quản lý bí mật; không đặt vào mã nguồn, log, URL hay file được commit.

Khi dùng StartTLS thay cho LDAPS, cần lưu ý cấu hình đặc thù của JNDI/LDAP provider và quản lý kết nối; tránh bật pooling một cách mặc định khi chưa xác minh tương thích với StartTLS.

## 4. `base`: gốc DN mà Spring LDAP sử dụng

`base` giúp các thao tác có thể nhận DN **tương đối** với gốc đã cấu hình.

Ví dụ, khi:

~~~text
ContextSource base:
dc=example,dc=org

Search base của query:
ou=people

Base DN hiệu lực:
ou=people,dc=example,dc=org
~~~

Bảng minh họa:

| DN truyền cho thao tác Spring LDAP | DN hiệu lực với `base=dc=example,dc=org` |
| --- | --- |
| `""` | `dc=example,dc=org` |
| `ou=people` | `ou=people,dc=example,dc=org` |
| `uid=an,ou=people` | `uid=an,ou=people,dc=example,dc=org` |
| `ou=groups` | `ou=groups,dc=example,dc=org` |

Nếu `base` đã bằng `dc=example,dc=org` mà ứng dụng truyền lại `ou=people,dc=example,dc=org` vào một API nhận DN tương đối, phần suffix `dc=example,dc=org` có thể bị thêm hai lần. Đây là nguyên nhân thường gặp của lỗi `noSuchObject` hoặc không tìm thấy entry.

Vì DN có cú pháp escape riêng, không nên tự ghép DN từ chuỗi người dùng bằng dấu phẩy. Có thể dùng `LdapNameBuilder`:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userSuppliedUid)
        .build();

// Ví dụ với uid=an:
// uid=an,ou=people
// Spring LDAP phân giải dưới base của ContextSource.
~~~

`base` có thể được đặt tại OU, chẳng hạn `ou=people,dc=example,dc=org`, nếu ứng dụng chỉ thao tác trong vùng nhân sự. Khi đó DN `uid=an` là tương đối với chính OU này. Quy tắc chọn base phải thống nhất giữa cấu hình và code.

**Base không phải cơ chế phân quyền.** Quyền đọc/ghi cuối cùng được LDAP server quyết định qua ACL và thông tin bind.

## 5. `user DN`: ứng dụng bind dưới danh tính nào?

Khi sử dụng bind có xác thực, `LdapContextSource` cần danh tính để lấy context phù hợp. Trong hệ thống thực tế, thường tạo tài khoản dịch vụ chuyên dụng:

~~~text
cn=app-reader,ou=services,dc=example,dc=org
~~~

Tài khoản đó có thể chỉ được phép đọc các thuộc tính công khai cần cho ứng dụng bên dưới `ou=people`. Nếu phải sửa entry, sử dụng tài khoản/quyền ghi được quản trị phù hợp; không cấp quyền quản trị toàn thư mục chỉ để thực hiện truy vấn.

Một số điểm cần lưu ý:

1. **Bind DN thường được cấu hình bằng DN đầy đủ.** Nó là danh tính của kết nối và không phải search base.
2. Một số directory hỗ trợ định danh bind khác DN theo cơ chế riêng, ví dụ kiểu UPN trong Active Directory. Chọn cách cấu hình tương thích với server, không giả định mọi server nhận cùng định dạng.
3. Tài khoản bind cần có quyền truy cập đúng phạm vi tìm kiếm. Filter hợp lệ không thể vượt qua ACL.
4. Nếu không cấu hình user/password, hành vi có thể là truy cập ẩn danh hoặc phụ thuộc cấu hình provider và server; không nên dựa vào anonymous bind trong hệ thống sản xuất nếu chức năng yêu cầu truy cập có kiểm soát.
5. Đối với xác thực người dùng cuối, thường sử dụng thao tác bind riêng với credential người dùng hoặc tích hợp Spring Security. Không biến mật khẩu người dùng thành giá trị trong LDAP search filter.

Đừng đưa user DN và password vào một endpoint chẩn đoán công khai hoặc ghi log cấu hình đầy đủ.

## 6. `password`: bí mật của tài khoản bind

Password của `LdapContextSource` là **thông tin xác thực của tài khoản dịch vụ** ở mục 5, không phải password của mọi entry được tìm thấy.

Quy tắc tối thiểu:

- Đọc password từ biến môi trường, secret manager hoặc cơ chế cấp phát bí mật được quản trị.
- Không hardcode trong code Java, YAML được commit, unit test hay log.
- Đảm bảo kênh LDAP có TLS hợp lệ trước khi gửi simple bind credential.
- Quy định cơ chế thay đổi (rotate) password và khởi động lại/làm mới cấu hình ứng dụng khi cần.
- Hạn chế quyền đọc bí mật và phân quyền tài khoản LDAP theo nguyên tắc tối thiểu.

Ví dụ file cấu hình có **tham chiếu** đến biến môi trường:

~~~yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`${LDAP_BIND_PASSWORD}` là cú pháp placeholder của Spring sau khi được chép vào file YAML thật; nó không phải mật khẩu. Ứng dụng cần được cung cấp biến môi trường `LDAP_BIND_PASSWORD` từ hạ tầng chạy ứng dụng.

Với hệ thống có quyền đọc/ghi khác nhau, nên suy nghĩ về chính sách tài khoản tách biệt và đường đi xử lý credential. Không đặt tài khoản LDAP quản trị làm mặc định cho mọi chức năng.

## 7. Cách 1: Spring Boot auto-configuration

Khi dự án đã sử dụng Spring Boot cùng các dependency LDAP thích hợp và auto-configuration đang được bật, có thể cấu hình các thuộc tính `spring.ldap.*`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Các khóa cần phân biệt:

| Thuộc tính Spring Boot | Giá trị mẫu | Liên hệ với `LdapContextSource` |
| --- | --- | --- |
| `spring.ldap.urls` | `ldaps://ldap.example.org:636` | Danh sách LDAP URL |
| `spring.ldap.base` | `dc=example,dc=org` | Base DN |
| `spring.ldap.username` | `cn=app-reader,...` | Bind identity |
| `spring.ldap.password` | `${LDAP_BIND_PASSWORD}` | Bind credential |

Boot có thể tự cấu hình `ContextSource` và các bean hỗ trợ dựa trên dependency, phiên bản và điều kiện auto-configuration. Để kiểm tra chính xác, xem các bean và log auto-configuration của **dự án đang chạy**. Không nên vừa khai báo thủ công một `ContextSource` khác vừa mặc nhiên mong các bean luôn dùng đúng cấu hình mong muốn.

Service nhận `LdapTemplate` do Spring cung cấp hoặc được dự án khai báo phù hợp:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryService {
    private final LdapTemplate ldapTemplate;

    public DirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Các phương thức tìm kiếm và thao tác LDAP sử dụng ldapTemplate.
}
~~~

Nếu trong dự án chưa có `LdapTemplate` bean, cần đăng ký nó từ `ContextSource` phù hợp; khả năng tạo sẵn bean cụ thể phụ thuộc Spring Boot/LDAP starter và phiên bản đang dùng.

## 8. Cách 2: khai báo `LdapContextSource` bean thủ công

Trong ứng dụng Spring không phụ thuộc auto-configuration, hoặc khi cần chủ động tùy chỉnh kết nối, có thể tạo bean `LdapContextSource` và `LdapTemplate`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfig {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String bindPassword) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

File `application.yml` tương ứng với đoạn mã trên là ví dụ ở mục 6 với nhóm `app.ldap.*`.

**Chọn một đường cấu hình chính:** dùng Boot auto-configuration hoặc bean tùy biến phù hợp với nhu cầu. Nếu có nhiều `ContextSource` vì kết nối tới nhiều directory, cần đặt tên bean và chọn rõ bean cần inject; không để framework tự đoán không xác định.

### Vòng đời bean

Khi `LdapContextSource` do Spring quản lý, Spring gọi các callback khởi tạo bean cần thiết trước khi các bean phụ thuộc dùng nó. Nếu tự khởi tạo `new LdapContextSource()` bên ngoài container Spring, cần đảm bảo thực hiện đúng bước initialization mà class yêu cầu trước khi dùng.

Không nên tạo mới `LdapContextSource` trong mỗi request HTTP. Nó đại diện cho cấu hình và được dùng lại; kết nối/context cụ thể sẽ được lấy theo nhu cầu thao tác.

## 9. Kiểm tra cấu hình bằng thao tác đọc an toàn

Sau khi cấu hình kết nối, hãy kiểm tra bằng một truy vấn **chỉ đọc** trên OU thử nghiệm. Ví dụ:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class DirectoryProbe {
    private final LdapTemplate ldapTemplate;

    public DirectoryProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
~~~

Ở ví dụ này:

- `ContextSource` có base `dc=example,dc=org`.
- Query dùng base tương đối `ou=people`.
- Filter cố định chỉ tìm các `inetOrgPerson`.
- Kết quả trả về tên `cn`, thuộc tính bắt buộc được kế thừa từ `person` trong schema chuẩn.

Nếu kết quả là danh sách rỗng, **chưa chắc cấu hình sai**: có thể không có entry nào khớp, search scope chưa tới OU con, hoặc tài khoản bind không được xem chúng. Hãy kiểm tra DN hiệu lực, filter, scope, quyền và server trả về gì.

Khi filter có dữ liệu người dùng, hãy dùng `LdapQueryBuilder`/filter builder để escape assertion value, tránh ghép chuỗi filter thô. Thao tác `search` chỉ đọc như ví dụ thích hợp hơn thao tác `bind` tạo entry để thử kết nối lần đầu.

## 10. Cấu hình cơ bản có liên quan gì đến search scope?

Một `LdapContextSource` không tự quyết định truy vấn sẽ lấy các entry **ở một cấp** hay **mọi cấp**. Search scope thuộc về từng lệnh search.

| Search scope | Ý nghĩa khi search base là `ou=people` |
| --- | --- |
| **Object** | Chỉ xét chính entry `ou=people` |
| **One level** | Xét các entry con trực tiếp |
| **Subtree** | Xét entry `ou=people` và tất cả descendant |

Ví dụ muốn tìm người dùng ở các OU nằm sâu hơn:

~~~java
import javax.naming.directory.SearchControls;
import org.springframework.ldap.query.LdapQuery;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchControls.SUBTREE_SCOPE)
        .where("objectClass").is("inetOrgPerson");
~~~

Lựa chọn search base, scope và filter ảnh hưởng phạm vi dữ liệu được xét và tải lên LDAP server. Một base quá cao kết hợp subtree có thể làm search tốn tài nguyên hoặc đụng giới hạn số lượng kết quả. Trong hệ thống thật, chọn OU cụ thể, limit phù hợp và tài khoản chỉ được truy cập dữ liệu cần thiết.

## 11. Các lỗi cấu hình thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân thường gặp | Nên kiểm tra |
| --- | --- | --- |
| Không phân giải được hostname | DNS/URL sai hoặc hostname không truy cập được | Tên máy, DNS, network, URL |
| `Connection refused`, timeout | Port, firewall, server ngừng hoạt động hoặc giới hạn kết nối | URL, port, reachability, timeout |
| Lỗi TLS/SSL handshake | CA, certificate chain, hostname mismatch, protocol TLS | Truststore, certificate, endpoint, chế độ TLS |
| `invalidCredentials (49)` | Bind DN hoặc password không được server chấp nhận | Danh tính bind, bí mật đã rotate, chính sách tài khoản |
| `noSuchObject (32)` | Base DN/search base không tồn tại hoặc lặp suffix | `ContextSource.base`, search base, cây DIT |
| `insufficientAccessRights (50)` | Bind có hiệu lực nhưng thiếu quyền | ACL, tài khoản bind, thuộc tính/vùng dữ liệu |
| Filter trả về 0 kết quả | Sai OU/scope/filter, hoặc chưa có dữ liệu phù hợp | Base DN hiệu lực, filter, scope và dữ liệu |
| Thao tác đọc thành công, ghi thất bại | Tài khoản chỉ đọc hoặc lỗi schema/ACL | Quyền ghi, object class, MUST attributes |
| Hai môi trường cho kết quả khác | Cấu hình base, URL hoặc schema khác nhau | Endpoint, naming context và cấu hình profile |

**Thành công khi kết nối không đồng nghĩa thao tác có quyền.** Ví dụ tài khoản `app-reader` có thể bind và search được `ou=people` nhưng thất bại khi sửa `mail` do ACL.

Các LDAP exception thường được Spring LDAP chuyển thành lớp exception của framework. Khi xử lý, cần phân biệt lỗi kết nối, xác thực, naming và quyền, không tự động chuyển mọi trường hợp thành “không tìm thấy người dùng”.

### Quy trình chẩn đoán được khuyến nghị

1. Xác nhận URL, cổng, DNS và khả năng truy cập server từ môi trường ứng dụng.
2. Xác minh TLS đúng chế độ, chứng chỉ tin cậy và hostname hợp lệ.
3. Kiểm tra danh tính bind và password bằng cách an toàn; tránh ghi password ra log hoặc terminal history.
4. Xác định rõ `ContextSource.base` và search base của query; dựng full DN dự kiến.
5. Kiểm tra search scope và filter bằng một entry kiểm thử đã biết.
6. Kiểm tra ACL, schema và giới hạn time/size khi truy vấn thành công nhưng kết quả không như mong đợi.
7. Sau khi đọc ổn định, mới thử các thao tác ghi được phép trên vùng dữ liệu thử nghiệm.

## 12. Pooling và timeout: đặt sau cấu hình kết nối đúng

Khi ứng dụng tải cao, có thể cần quản lý lại việc tạo context và kết nối. JNDI có cơ chế connection pooling, Spring LDAP có các cách tích hợp quản lý pooling tùy phiên bản; tuy nhiên **pooling không phải thuộc tính bắt buộc để `LdapContextSource` hoạt động**.

Một số lưu ý thực tế:

- Xác minh URL, base, bind và TLS trước khi tối ưu pooling.
- Với StartTLS, cần đặc biệt thận trọng về hỗ trợ pooling; một số cơ chế JNDI pooling không tương thích với cách nâng cấp kết nối hoặc các phiên làm việc TLS theo yêu cầu.
- Không trộn các bind identity/credential khác nhau vào cùng một pool theo cách làm sai ranh giới xác thực.
- Thiết lập timeout kết nối và đọc theo khả năng của JNDI provider/LDAP stack; có chiến lược xử lý lỗi mạng và thử lại phù hợp.
- Theo dõi số kết nối, timeout và lỗi xác thực, nhưng không xuất password hoặc dữ liệu nhạy cảm trong metrics/log.

Đừng bật `setPooled(true)` một cách máy móc chỉ vì số request tăng. Phải kiểm tra tương thích với TLS, cơ chế authentication, server, phiên bản thư viện và tải thực tế.

## 13. Bài thực hành: kết nối và giải thích DN

Giả sử có LDAP server thử nghiệm tại:

~~~text
URL:      ldaps://ldap.lab.example.org:636
Tree:     dc=lab,dc=example,dc=org
OU:       ou=people,dc=lab,dc=example,dc=org
Service:  cn=reader,ou=services,dc=lab,dc=example,dc=org
Users:    uid=an,ou=people,dc=lab,dc=example,dc=org
          uid=binh,ou=people,dc=lab,dc=example,dc=org
~~~

Tài khoản dịch vụ được cấp quyền **đọc** OU nhân sự. Người học chỉ sử dụng server và credential thử nghiệm được cấp; không dùng tài khoản quản trị sản xuất.

### Nhiệm vụ

1. Viết cấu hình Spring Boot dùng `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password` (password lấy từ biến môi trường).
2. Khi `ContextSource.base = dc=lab,dc=example,dc=org`, chọn search base nào để chỉ tìm dưới OU people?
3. Nếu đổi `ContextSource.base` thành `ou=people,dc=lab,dc=example,dc=org`, search base nào trỏ đến chính OU đó?
4. Nếu user DN của tài khoản dịch vụ nằm dưới `ou=services`, có cần đổi user DN khi base đổi từ naming context sang `ou=people` không?
5. Vì sao truy vấn LDAP trên kết nối chưa được TLS bảo vệ là lựa chọn không phù hợp khi truyền password bằng simple bind?
6. Mô tả ít nhất ba nguyên nhân có thể gây ra “bind thành công nhưng search trả rỗng”.

### Gợi ý đáp án

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.lab.example.org:636
    base: dc=lab,dc=example,dc=org
    username: cn=reader,ou=services,dc=lab,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

| Câu | Đáp án |
| --- | --- |
| 2 | Search base `ou=people` |
| 3 | Search base `""` (DN tương đối rỗng trong ngữ cảnh base mới) |
| 4 | Không đổi user DN chỉ vì thay base dùng cho thao tác; bind identity vẫn là danh tính tài khoản dịch vụ, trừ khi tài khoản/config thực sự thay đổi |
| 5 | Simple bind password không được bảo vệ đủ nếu đường truyền không mã hóa; cần LDAPS/StartTLS cùng xác thực chứng chỉ |
| 6 | Sai search base, scope không đủ sâu, filter không khớp, ACL giới hạn, không có entry phù hợp, hoặc server áp giới hạn |

### Bài kiểm thử bổ sung

Tạo hai cấu hình test trỏ tới **cùng OU người dùng**:

~~~text
Cấu hình A:
  ContextSource base: dc=lab,dc=example,dc=org
  Query search base:  ou=people

Cấu hình B:
  ContextSource base: ou=people,dc=lab,dc=example,dc=org
  Query search base:  ""

Effective search base trong cả hai:
ou=people,dc=lab,dc=example,dc=org
~~~

Chạy cùng filter `(objectClass=inetOrgPerson)` và cùng scope qua tài khoản có quyền đọc. Nếu kết quả khác nhau, kiểm tra thêm cấu hình môi trường và server thay vì mặc định sửa filter.

## 14. Những điểm cần nhớ

- `LdapContextSource` là cầu nối giữa Spring LDAP và JNDI, cung cấp context để `LdapTemplate` hoặc API truy cập LDAP thực hiện thao tác.
- **URL** xác định endpoint LDAP và chế độ kết nối; **base** là gốc dùng để diễn giải DN của thao tác; **user DN/password** dùng để bind với danh tính đã chọn.
- `base` thường được ghép theo ngữ nghĩa DN với **search base tương đối** của query; tránh lặp suffix và không nhầm search base rỗng với Root DSE khi base đã khác rỗng.
- Bind account của ứng dụng khác với người dùng đang đăng nhập. Quyền thực tế nằm ở ACL server; ứng dụng chỉ nên được cấp quyền cần thiết.
- Có thể dùng **Spring Boot `spring.ldap.*`** hoặc khai báo bean `LdapContextSource`/`LdapTemplate` trực tiếp. Cần kiểm soát rõ bean nào được inject.
- Dùng **LDAPS hoặc StartTLS** đã xác minh chứng chỉ, quản lý password bằng secret store, kiểm tra timeout và pooling theo hạ tầng trước khi sử dụng ở môi trường thật.
- Kiểm thử một truy vấn chỉ đọc với base/scope/filter rõ ràng trước khi triển khai thao tác ghi hoặc xác thực người dùng.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Boot LDAP Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [RFC 4511 – Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4513 – LDAP: Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)
