# Bind DN, bind password và xác thực khi tạo context

Một ứng dụng Spring LDAP có thể biết đúng URL của LDAP server nhưng vẫn không đọc được thư mục vì **bind DN không đúng**, **mật khẩu đã thay đổi** hoặc **quyền của tài khoản kết nối không đủ**. Những vấn đề này xuất hiện tại ranh giới giữa cấu hình `ContextSource`, việc tạo JNDI context và thao tác xác thực (*bind*) mà LDAP server thực hiện.

Bài học nằm trong chương **Cấu hình ContextSource** của SPRING_LDAP. Trọng tâm là vai trò của `bind DN` và `bind password`, lúc nào thông tin đó được dùng để xác thực, và làm sao kiểm thử đường truy cập an toàn. Ví dụ dùng `LdapContextSource`, `LdapTemplate`, query builder của Spring LDAP và một thư mục nhân sự thử nghiệm. Những khái niệm này cũng hữu ích khi chuyển sang `LdapClient` hoặc ODM, vì các API đó vẫn phải dựa trên một danh tính có quyền truy cập LDAP.

## 1. Bind là gì và tại sao cần bind?

Trong LDAP, **bind** là thao tác thiết lập danh tính xác thực trên một kết nối LDAP. Với *simple bind*, client gửi một định danh xác thực và mật khẩu; server kiểm tra chúng rồi gắn trạng thái xác thực tương ứng cho kết nối. Server sử dụng danh tính đã xác thực và chính sách truy cập để quyết định các thao tác tiếp theo có được phép hay không.

Ví dụ thư mục:

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

Ứng dụng quản lý nhân sự thường thực hiện tìm kiếm bằng tài khoản dịch vụ `cn=app-reader,ou=services,dc=example,dc=org`. Tài khoản này có thể được cấp quyền **chỉ đọc** người dùng dưới `ou=people` mà không có quyền cập nhật mật khẩu hoặc xóa entry.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Bind DN** | `cn=app-reader,ou=services,dc=example,dc=org` | Danh tính ứng dụng sử dụng để xác thực kết nối LDAP |
| **Bind password** | Bí mật được cấp cho `app-reader` | Credential dùng để chứng minh danh tính bind |
| **Base DN** | `dc=example,dc=org` | Gốc mà Spring LDAP dùng để diễn giải các DN thao tác tương đối |
| **Search base** | `ou=people` | Nhánh bắt đầu tìm kiếm, tương đối với base của `ContextSource` |
| **Người dùng cuối** | `uid=an,ou=people,dc=example,dc=org` | Người đang đăng nhập vào ứng dụng; có thể được xác thực bằng một lần bind khác |
| **ACL** | App reader chỉ có quyền đọc một số thuộc tính | Quy tắc trên server kiểm soát những thao tác danh tính đã bind được thực hiện |

**Bind DN không phải search base**: DN tài khoản dịch vụ trỏ tới danh tính xác thực, còn base của `ContextSource` là gốc đặt tên cho các thao tác. Hai DN này có thể nằm ở các nhánh khác nhau như trong ví dụ.

Cũng cần phân biệt “LDAP bind” của giao thức với `ldapTemplate.bind(...)` trong API Spring LDAP: phương thức `bind(...)` của `LdapTemplate` dùng để **tạo một entry LDAP**, không phải để xác thực người dùng bằng mật khẩu.

## 2. Luồng từ service đến việc xác thực LDAP

Khi service gọi một thao tác đọc qua `LdapTemplate`, Spring LDAP sử dụng `ContextSource` để lấy context phù hợp. `LdapContextSource` tạo ngữ cảnh JNDI với cấu hình URL và thông tin bảo mật; JNDI provider dùng kết nối LDAP để thực hiện bind và lệnh tiếp theo.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant T as LdapTemplate
    participant C as LdapContextSource
    participant J as JNDI LDAP provider
    participant L as LDAP server
    S->>T: search(query, mapper)
    T->>C: getReadOnlyContext()
    C->>J: Tạo/lấy DirContext với cấu hình bind
    J->>L: Kết nối TLS và simple bind khi cần
    L-->>J: Bind thành công hoặc LDAP error
    J-->>C: DirContext đã sẵn sàng
    C-->>T: DirContext
    T->>J: LDAP search
    J->>L: SearchRequest(base, filter, scope)
    L-->>J: Kết quả theo schema và ACL
    J-->>T: SearchResult
    T-->>S: Dữ liệu đã mapping
    Note over T,J: Template quản lý đóng/trả context sau thao tác
~~~

Sơ đồ diễn tả **luồng logic**. Thời điểm mở socket, thực hiện bind vật lý hoặc tái sử dụng kết nối phụ thuộc JNDI provider, cấu hình pooling và cơ chế kết nối. Không được mặc định rằng mỗi lần gọi `search(...)` luôn tạo một TCP connection mới, hoặc rằng ngay khi Spring tạo bean `LdapContextSource` thì server đã chấp nhận bind.

### Hai thời điểm dễ bị nhầm

**1. Khởi tạo bean `LdapContextSource`:** Spring đọc URL, base DN, user DN, password và chuẩn bị đối tượng cấu hình. Phần lớn các cấu hình có thể được khởi tạo mà chưa thực sự truy cập LDAP server. Khởi động Spring thành công **không tự chứng minh credential hợp lệ**.

**2. Lấy và sử dụng LDAP context:** khi `LdapTemplate` hoặc client khác yêu cầu context, JNDI provider mới cần có kết nối, xác thực và thực thi LDAP operation. Lỗi sai mật khẩu, máy chủ không reachable hoặc TLS có thể phát sinh lúc này. Với một số provider, kết nối có thể được khởi tạo hoặc kiểm tra muộn đến thao tác đầu tiên.

Nếu muốn phát hiện lỗi ngay khi deploy, cần một **startup readiness check** có chủ đích, ví dụ truy vấn đọc nhẹ ở nhánh được cho phép. Không nên dựa vào việc khởi tạo bean để bảo đảm ứng dụng sẵn sàng phục vụ truy vấn LDAP.

## 3. Cấu hình `LdapContextSource` với bind DN và password

`LdapContextSource` là triển khai `ContextSource` thường dùng trong Spring LDAP, cho phép khai báo endpoint, base DN và credential mặc định.

Ví dụ Spring Java Configuration:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfig {

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

Cấu hình tương ứng:

~~~yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Trong đó:

- `setUrl(...)`: chọn địa chỉ kết nối. `ldaps://` dùng TLS ngay từ đầu; `ldap://` cần cấu hình StartTLS nếu muốn nâng cấp kết nối an toàn.
- `setBase(...)`: chọn gốc DN để thao tác tương đối, chẳng hạn truy vấn `ou=people` được diễn giải dưới `dc=example,dc=org`.
- `setUserDn(...)`: đặt danh tính bind mặc định. Giá trị thông thường là **DN đầy đủ** của tài khoản dịch vụ; không tự thêm `base` của query vào bind DN.
- `setPassword(...)`: cung cấp password của **chính tài khoản bind đó**.

Spring quản lý lifecycle của bean và thực hiện các bước initialization cần thiết của `LdapContextSource`. Nếu tự khởi tạo đối tượng này bên ngoài Spring container, phải bảo đảm lifecycle/initialization được xử lý đúng trước khi dùng.

Với phiên bản Spring Boot hỗ trợ auto-configuration LDAP, có thể dùng các thuộc tính có sẵn:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Sự khác biệt về tên khóa đáng nhớ: **cấu hình Boot** dùng `spring.ldap.username`; **API `LdapContextSource`** dùng `setUserDn(...)`. Hai cách cùng mô tả danh tính xác thực, nhưng không nên trộn hai đường cấu hình hoặc tạo nhiều bean `ContextSource` mà không xác định rõ bean nào được inject.

## 4. Một bind DN hợp lệ trông như thế nào?

Với LDAP server sử dụng schema và tên DN thông thường, bind DN có thể là:

~~~text
cn=app-reader,ou=services,dc=example,dc=org
~~~

Trong đó:

- `cn=app-reader`: RDN của entry tài khoản dịch vụ;
- `ou=services`: nhánh chứa tài khoản;
- `dc=example,dc=org`: suffix/naming context trong ví dụ.

Để xác thực được, DN hoặc dạng định danh bind mà server hỗ trợ phải trỏ tới danh tính hợp lệ, và password phải đúng. Việc entry hiện hữu chưa đủ để kết luận tài khoản được phép bind: chính sách server có thể khóa tài khoản, cấm phương thức xác thực, giới hạn thời gian hoặc áp dụng điều kiện bảo mật khác.

Một số server như Active Directory có thể cho phép cách nhập danh tính bind khác DN chuẩn, ví dụ dạng UPN, tùy cấu hình. Không giả định mọi LDAP server đều cho phép các dạng định danh tương tự. Trong nội dung hướng dẫn dùng nhiều LDAP server, **DN đầy đủ được server chấp nhận** là lựa chọn minh bạch nhất.

### Tại sao không dùng DN tương đối cho bind DN?

Nếu `ContextSource.base=dc=example,dc=org`, search base `ou=people` được xử lý tương đối với base. Nhưng bind DN của tài khoản dịch vụ là **danh tính xác thực để tạo context**, không phải một điểm tìm kiếm: ví dụ vẫn cần `cn=app-reader,ou=services,dc=example,dc=org`.

Cấu hình sai như:

~~~text
ContextSource base: dc=example,dc=org
Bind user DN:      cn=app-reader,ou=services
~~~

không nên được cho là luôn được tự động biến thành DN đầy đủ. Hãy dùng danh tính bind đúng định dạng mà server và API `ContextSource` yêu cầu.

**Phân biệt hai lỗi:**

- **Sai bind DN:** server không thể xác thực đúng danh tính, thường báo lỗi credential/authentication.
- **Sai search base:** bind có thể hoàn toàn thành công nhưng thao tác tìm kiếm đi đến nhánh không tồn tại hoặc không có kết quả.

Việc sửa `spring.ldap.base` để “chữa” mật khẩu sai thường không giải quyết đúng nguyên nhân.

## 5. Bind password và an toàn thông tin xác thực

Bind password của tài khoản dịch vụ là một **secret**. Không nhúng giá trị thật trong ví dụ mã nguồn, tập tin cấu hình commit lên Git, CI log hoặc thông số JVM dễ bị lộ.

Ví dụ giá trị trong YAML:

~~~yaml
spring:
  ldap:
    password: ${LDAP_BIND_PASSWORD}
~~~

`${LDAP_BIND_PASSWORD}` là tham chiếu cấu hình của Spring tới biến môi trường hoặc nguồn cấu hình thích hợp. Biến này phải được cung cấp khi chạy ứng dụng. Nếu thiếu, cách ứng dụng phản hồi phụ thuộc cơ chế binding cấu hình và validation; nên kiểm tra sớm, thay vì để ứng dụng chạy với credential ngoài dự kiến.

**Những nguyên tắc vận hành:**

1. Tạo tài khoản dịch vụ riêng, cấp **quyền tối thiểu** cho phạm vi và các thuộc tính cần thiết.
2. Đọc password từ secret manager hoặc nguồn bí mật được quản trị; hạn chế quyền xem giá trị này.
3. Dùng **LDAPS/StartTLS có xác thực chứng chỉ** trước khi truyền simple bind password.
4. Có quy trình **rotation**: thay secret trên server, cập nhật ứng dụng và làm mới các context/connection cũ đúng cách.
5. Không ghi password, toàn bộ environment JNDI hoặc URL chứa credential vào log, error response hay metrics.
6. Khi dùng nhiều môi trường, không dùng chung password tài khoản dịch vụ của production cho test.
7. Xử lý lỗi authentication mà không hiển thị dữ liệu nhạy cảm hoặc tiết lộ quá nhiều về tài khoản.

Khi cần quan sát sự cố, hãy ghi operation, endpoint được phép, correlation ID, nhóm lỗi và mã LDAP phù hợp; tránh log giá trị password, mã xác thực người dùng hoặc dữ liệu cá nhân không cần thiết.

## 6. Xác thực khi lấy context: `getReadOnlyContext` và `getReadWriteContext`

Interface `ContextSource` trong Spring LDAP cung cấp các phương thức để lấy ngữ cảnh phục vụ thao tác:

- `getReadOnlyContext()`: cung cấp context theo cấu hình cho các thao tác đọc.
- `getReadWriteContext()`: cung cấp context để thực hiện thao tác ghi.
- `getContext(String principal, String credentials)`: lấy context với thông tin xác thực được chỉ định thay cho cấu hình bind mặc định, thường dùng khi cần xác thực danh tính khác.

**Tên `ReadOnly` và `ReadWrite` không tự cấp hoặc thu hồi quyền của tài khoản trên LDAP server.** Server áp dụng ACL cho danh tính thực tế đã bind; một context hướng đọc không có nghĩa tài khoản có quyền đọc tất cả, và context hướng ghi không làm tài khoản chỉ đọc trở thành quản trị viên.

Thông thường `LdapTemplate` tự lấy context phù hợp rồi đóng hoặc trả về pool theo cơ chế được cấu hình. Nếu ứng dụng tự gọi `ContextSource.getContext(...)`, chính ứng dụng phải chịu trách nhiệm đóng `DirContext` để tránh rò rỉ tài nguyên.

Ví dụ minh họa việc lấy context trực tiếp:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;

public final class DirectoryConnectionProbe {

    private final ContextSource contextSource;

    public DirectoryConnectionProbe(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void verifyServiceContext() throws NamingException {
        DirContext context = contextSource.getReadOnlyContext();
        try {
            // Thực hiện một lookup/search nhỏ trên entry thử nghiệm có quyền đọc
            // để kiểm tra cả kết nối và quyền truy cập.
        } finally {
            context.close();
        }
    }
}
~~~

Đoạn mã này thể hiện việc quản lý vòng đời context, nhưng **chưa thực hiện lệnh đọc** ở phần `try`. Chỉ có context được tạo ra có thể chưa chứng minh toàn bộ đường tìm kiếm hoạt động, tùy thời điểm provider thực thi kết nối/bind. Trong ứng dụng thực tế, `LdapTemplate` thuận tiện hơn cho phép thử truy vấn và quản lý tài nguyên.

### Tại sao không tạo context mới trong mỗi controller?

Một controller không nên tự tạo `LdapContextSource` mỗi lần nhận HTTP request. Điều đó trùng lặp cấu hình, khó kiểm soát timeout, pooling và lifecycle; cũng khiến credential bị truyền qua nhiều lớp hơn cần thiết. Tốt hơn là inject một `LdapTemplate` hoặc service LDAP đã được cấu hình trong Spring container.

## 7. Bind của ứng dụng và xác thực người dùng cuối là hai việc khác nhau

Một đăng nhập của nhân viên An thường có hai bước logic:

1. Ứng dụng dùng **service bind** để tìm entry An theo thuộc tính đăng nhập như `uid=an`.
2. Nếu hệ thống chọn xác thực bằng LDAP bind, ứng dụng thử xác thực **danh tính An** với mật khẩu An nhập; trả về thành công hoặc thất bại theo phản hồi server.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant L as LDAP server
    U->>A: uid và password
    A->>L: Service bind rồi search uid (filter an toàn)
    L-->>A: DN của user nếu được phép tìm
    A->>L: Xác thực bằng bind DN của user và password nhập
    L-->>A: Kết quả xác thực
    A-->>U: Kết quả đăng nhập theo chính sách ứng dụng
~~~

Cấu hình service bind DN/password **không có nghĩa** ứng dụng đã xác thực người dùng An. Ngược lại, mật khẩu của người dùng cuối cũng **không được ghi đè** lên password của `LdapContextSource` dùng chung.

### Dùng `LdapTemplate.authenticate(...)`

Khi dự án sử dụng cơ chế xác thực LDAP của Spring LDAP, có thể tìm người dùng qua query và yêu cầu kiểm tra credential:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryAuthenticationService {

    private final LdapTemplate ldapTemplate;

    public DirectoryAuthenticationService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean authenticate(String username, String password) {
        if (username == null || username.isBlank()
                || password == null || password.isEmpty()) {
            return false;
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        return ldapTemplate.authenticate(query, password);
    }
}
~~~

Giả sử `ContextSource.base=dc=example,dc=org`, query tìm `uid` dưới `ou=people`. Spring LDAP sử dụng cơ chế xác thực phù hợp để kiểm tra mật khẩu với DN người dùng tìm được. Query builder đảm bảo giá trị `username` không bị biến thành cú pháp LDAP filter.

Ở tầng HTTP thực tế, còn phải xử lý TLS giữa client–ứng dụng, giới hạn thử đăng nhập, chính sách tài khoản, logging an toàn, kết quả không tìm thấy/trùng người dùng và sự khác biệt exception giữa sai mật khẩu với lỗi kết nối. Tùy phiên bản và cấu hình Spring LDAP, hành vi exception cần được kiểm tra cụ thể. Nếu ứng dụng sử dụng Spring Security LDAP, nên đưa logic xác thực vào thành phần bảo mật phù hợp thay vì tự xây lại toàn bộ hệ thống đăng nhập.

**Không xác thực password bằng LDAP search filter**, ví dụ ghép `(userPassword=...)`. Thuộc tính mật khẩu có thể không đọc được hoặc không chứa mật khẩu thuần, và so sánh trong filter không phải cơ chế xác thực chuẩn đáng tin cậy của LDAP.

### Cảnh báo về context chứa danh tính người dùng

Khi dùng `getContext(userDn, userPassword)` theo cách thủ công để thử bind, phải **đóng context trong mọi trường hợp**, kể cả khi phát sinh exception. Không đưa context đã xác thực của một người dùng vào bean singleton hoặc pool dùng chung cho người dùng khác; nếu không, có nguy cơ thao tác sau chạy dưới nhầm danh tính.

## 8. Mã lỗi thường gặp: xác thực thất bại khác thiếu quyền

Khi kết nối đến LDAP, thất bại có thể xảy ra ở nhiều lớp:

| Tình huống | Biểu hiện thường gặp | Phân biệt nguyên nhân |
| --- | --- | --- |
| Server không truy cập được | Timeout, connection refused, name resolution | URL, port, DNS, firewall, server down |
| TLS không thiết lập được | Handshake/certificate/hostname error | Truststore, CA, hostname, LDAPS/StartTLS |
| Bind DN/password sai | `invalidCredentials (49)` | Thông tin xác thực hoặc chính sách tài khoản |
| Server yêu cầu xác thực mạnh hơn | `strongerAuthRequired (8)` hoặc lỗi security policy | Cơ chế bind/TLS được server yêu cầu |
| Bind thành công nhưng đọc bị từ chối | `insufficientAccessRights (50)` | ACL hoặc thuộc tính bị hạn chế |
| Bind thành công nhưng search base không có | `noSuchObject (32)` | Base DN/OU sai, suffix bị lặp |
| Truy vấn đúng nhưng không thấy người dùng | 0 kết quả hoặc lỗi phụ thuộc server | Filter, search scope, ACL, dữ liệu, giới hạn |
| Thử ghi vào nhánh chỉ đọc | `insufficientAccessRights (50)` | Quyền ghi, không phải mật khẩu sai |
| Tạo entry thiếu thuộc tính MUST | `objectClassViolation (65)` | Schema của object class, không phải lỗi service bind |

Cùng một điều kiện thực tế có thể được server thể hiện khác nhau tùy nhà cung cấp và chính sách, chẳng hạn account locked hoặc expired vẫn có thể dẫn tới thông báo credential không hợp lệ. Không dựa vào phần text chi tiết của một hãng server để xây logic authentication cho mọi hệ thống.

Trong Java, JNDI phát sinh exception tương ứng và Spring LDAP thường chuyển đổi sang hệ thống exception riêng. Để hiển thị thông báo cho người dùng cuối, nên giữ nội dung đủ chung (“Không thể xác thực” hoặc thông báo phù hợp nghiệp vụ). Để điều tra nội bộ, sử dụng mã và loại lỗi đã loại bỏ thông tin nhạy cảm.

## 9. Kiểm tra bind và quyền bằng thao tác đọc nhỏ

Muốn kiểm thử credential của tài khoản dịch vụ, hãy chạy một phép **đọc nhẹ** thay vì thay đổi entry thật. Ví dụ:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class ServiceBindProbe {

    private final LdapTemplate ldapTemplate;

    public ServiceBindProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findKnownUsers() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("an");

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("cn").get());
    }
}
~~~

Phép thử này có thể chứng minh nhiều yếu tố: endpoint/TLS hoạt động, service bind được chấp nhận, base DN đúng, account có quyền đọc và mapping nhận được thuộc tính `cn`. Tuy nhiên **0 kết quả không mặc nhiên là sai password**: có thể `uid=an` không tồn tại, nằm dưới OU khác hoặc không được nhìn thấy qua ACL/filter.

Để kiểm tra quyền, cần có **entry kiểm thử được biết chắc tồn tại**, với danh tính bind và OU đã được quản trị viên cho phép. Đừng “đi tìm rộng” trên thư mục sản xuất chỉ để kiểm tra connectivity.

### Readiness và health check

Có thể xây readiness check chỉ đọc ở vùng kiểm thử; khi LDAP không sẵn sàng, hệ thống ghi nhận trạng thái không đáp ứng phụ thuộc LDAP. Tuy nhiên tránh mỗi lần probe từ hệ thống giám sát đều tạo tìm kiếm subtree tốn chi phí. Nên có timeout, tần suất hợp lý, phân biệt LDAP tạm thời lỗi với ứng dụng hoàn toàn không hoạt động, và không log credential.

## 10. TLS, timeout và pooling ảnh hưởng gì tới bind?

### TLS: bảo vệ thông tin xác thực

**Simple bind truyền credential qua kênh LDAP**; nếu dùng `ldap://` không bật StartTLS, thông tin nhạy cảm có thể không được bảo vệ trên đường truyền. Với production, dùng `ldaps://` hoặc StartTLS được cấu hình chuẩn, có kiểm tra chứng chỉ và tên máy chủ.

Không khắc phục lỗi chứng chỉ bằng cách tắt xác thực hostname/CA, vì khi đó kết nối mã hóa chưa đủ bảo đảm đang nói chuyện với đúng LDAP server.

### Timeout: tránh treo quá lâu khi lấy context

Khi DNS, network hoặc server gặp sự cố, bước lấy context/bind và search có thể chậm. Cần cấu hình timeout kết nối và đọc theo JNDI provider và giới hạn nghiệp vụ; không mặc định mọi môi trường có timeout đủ ngắn. Trong ứng dụng, cũng cần quy định retry/backoff phù hợp và phân biệt retry lỗi mạng với việc thử lại **sai password**.

Không thực hiện vòng retry vô hạn với credential sai vì có thể kích hoạt khóa tài khoản hoặc làm trầm trọng tải lên LDAP server.

### Pooling: tái sử dụng kết nối theo danh tính

Một context hoặc connection pool giúp giảm chi phí tạo kết nối/bind cho nhiều thao tác. Tuy nhiên pooling cần xem xét:

- **Danh tính:** không tái sử dụng connection đang bind bằng người dùng A cho thao tác của người dùng B.
- **Rotation:** mật khẩu dịch vụ thay đổi cần làm mới connection/context đang sử dụng credential cũ; tùy pool mà phải invalidate hoặc recycle các kết nối.
- **TLS:** StartTLS và các cơ chế pooling của JNDI có hạn chế tương thích cần xác minh; không bật pooling tùy tiện.
- **Lỗi kết nối:** pool phải nhận biết kết nối đã đóng hoặc không còn hợp lệ; validate khi phù hợp.
- **Timeout và kích thước:** giới hạn số kết nối đồng thời theo tài nguyên LDAP server, tránh tạo tải quá lớn.

Khi một thao tác thất bại trong ứng dụng đã bật pooling, đừng kết luận “mật khẩu vừa nhập sai” nếu chưa xem pool có đang sử dụng context cũ hay không.

## 11. Các tình huống thường gặp với bind DN/password

### Tình huống A: sai mật khẩu dịch vụ

- Ứng dụng khởi động, bean `LdapContextSource` được tạo.
- Lần tìm kiếm đầu tiên phát sinh lỗi `invalidCredentials`.
- Query base và filter vẫn đúng về cú pháp.

**Cách xử lý:** kiểm tra secret đã được cấp phát, trạng thái tài khoản và thay đổi password gần đây. Không “sửa” filter hay mở quyền ACL khi chưa xác nhận bind có thành công.

### Tình huống B: bind thành công nhưng thiếu quyền

- Tài khoản `app-reader` dùng credential hợp lệ.
- Search dưới `ou=people` thành công, nhưng `modifyAttributes(...)` bị từ chối.

**Cách xử lý:** đây là vấn đề **ACL/quyền thao tác**. Nếu ứng dụng không cần ghi, giữ tài khoản chỉ đọc là thiết kế đúng. Nếu cần ghi, trao đổi với quản trị viên để cấp quyền hẹp cho nhánh/thuộc tính cụ thể, không dùng tài khoản quản trị toàn thư mục.

### Tình huống C: base DN sai

- App bind được bằng `cn=app-reader,ou=services,dc=example,dc=org`.
- `ContextSource.base` đã là `dc=example,dc=org`.
- Query tiếp tục truyền `ou=people,dc=example,dc=org` vào tham số search base tương đối.

**Hệ quả:** suffix base bị lặp, có thể gây `noSuchObject`. Cần đặt search base là `ou=people` khi API làm việc tương đối với base đã cấu hình.

### Tình huống D: credential mới nhưng pool chưa đổi

- Quản trị viên đã rotate password tài khoản dịch vụ.
- Secret manager có password mới, nhưng các context trong pool có thể vẫn được tạo từ credential cũ hoặc vẫn dùng phiên xác thực trước đó.

**Cách xử lý:** có quy trình làm mới cấu hình và pool/connection phù hợp. Cần kiểm tra cả credential hiện hành, trạng thái bind và cơ chế tái sử dụng kết nối; không dùng việc một search còn thành công để suy ra mọi context đã sử dụng password mới.

### Tình huống E: sử dụng user password để search

- Ứng dụng nhận username và password của nhân viên.
- Dev muốn viết `(&(uid=an)(userPassword=...))`.

**Sai về thiết kế:** LDAP bind là cơ chế xác thực phù hợp; `userPassword` có thể không được đọc, có định dạng hash hoặc không tồn tại. Hãy tìm DN bằng filter an toàn rồi dùng API xác thực LDAP hoặc thành phần Spring Security có thiết kế tương ứng.

## 12. Bài thực hành: cấu hình và kiểm tra bind

Giả sử có LDAP server lab (được phép sử dụng) với:

~~~text
Server:       ldaps://ldap.lab.example.org:636
Naming base:  dc=lab,dc=example,dc=org
User OU:      ou=people,dc=lab,dc=example,dc=org
Service DN:   cn=reader,ou=services,dc=lab,dc=example,dc=org
Known user:   uid=an,ou=people,dc=lab,dc=example,dc=org
~~~

Tài khoản dịch vụ `reader` được cấp quyền đọc `uid` và `cn` dưới `ou=people`. Password của `reader` đã được hệ thống cấp phát cho môi trường lab, không lưu vào Git.

**Nhiệm vụ 1 — Cấu hình:** viết `application.yml` dùng Spring Boot LDAP properties, đặt URL, base và bind identity; lấy password từ biến môi trường.

**Nhiệm vụ 2 — Xác định DN:** nếu `ContextSource.base` là `dc=lab,dc=example,dc=org`, query phải dùng search base nào để tìm dưới `ou=people`?

**Nhiệm vụ 3 — Tìm một entry đã biết:** dùng `LdapQueryBuilder` tạo filter `uid=an` dưới base ở nhiệm vụ 2; giải thích tại sao phép thử thành công chứng minh được nhiều hơn khởi tạo bean.

**Nhiệm vụ 4 — Giải thích lỗi:** dự đoán khác biệt giữa `invalidCredentials (49)` và `insufficientAccessRights (50)`.

**Nhiệm vụ 5 — Rotation:** mô tả các bước xử lý an toàn khi password dịch vụ bị thay đổi nhưng ứng dụng còn giữ connection pool cũ.

**Nhiệm vụ 6 — Bảo mật:** vì sao không thể dùng `LdapTemplate.search(...)` với `(userPassword=...)` thay cho việc bind bằng user credential?

### Đáp án tham khảo

**1. Cấu hình Boot:**

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.lab.example.org:636
    base: dc=lab,dc=example,dc=org
    username: cn=reader,ou=services,dc=lab,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**2.** Search base tương đối: `ou=people`. Base đầy đủ trên server là `ou=people,dc=lab,dc=example,dc=org`.

**3.** Truy vấn có thể dùng `LdapQueryBuilder.query().base("ou=people").where("uid").is("an")`; kết quả thành công với entry biết chắc tồn tại giúp kiểm tra cả khả năng kết nối, credential, base, filter và quyền đọc. Chỉ khởi tạo bean chưa kiểm tra được hết những điều đó.

**4.** `49` thường liên quan xác thực credential; `50` thường liên quan quyền với một thao tác cụ thể sau khi có danh tính bind. Không coi hai mã lỗi là một.

**5.** Cập nhật secret theo quy trình, làm mới cấu hình runtime và pool/context được quản lý, kiểm tra kết nối mới trên thao tác đọc an toàn, theo dõi lỗi và bảo đảm không để lộ secret qua log. Lưu ý thứ tự đổi password, triển khai cấu hình và chính sách cho thời gian chuyển đổi.

**6.** Search filter so sánh thuộc tính dữ liệu, không phải phép xác thực LDAP. Trường password có thể bị che hoặc hash; kiểm tra credential nên qua bind/API xác thực và kết nối TLS đáng tin cậy.

### Câu hỏi tự đánh giá

| Câu hỏi | Đáp án ngắn |
| --- | --- |
| Bean `LdapContextSource` tạo thành công có chứng minh password đúng không? | Không; phải xác minh ở thao tác LDAP thực tế |
| `ContextSource.base` có quyết định bind identity không? | Không; bind DN là thông tin xác thực riêng |
| `getReadWriteContext()` có tự nâng quyền ghi không? | Không; ACL server quyết định |
| `ldapTemplate.bind(...)` có dùng để đăng nhập người dùng không? | Không; API này dùng tạo entry |
| Có thể dùng bind DN của tài khoản dịch vụ thay cho user DN khi kiểm tra mật khẩu người dùng không? | Không; đây là hai danh tính khác nhau |
| Có nên bật JNDI pooling mặc định cho mọi StartTLS setup không? | Không; kiểm tra tính tương thích và lifecycle |
| Cần làm gì sau khi rotate password dịch vụ? | Làm mới secret runtime và connection/context theo chiến lược đã cấu hình |

## 13. Checklist trước khi đưa cấu hình vào môi trường thật

- [ ] URL LDAP đúng endpoint, DNS, port; LDAPS hoặc StartTLS được cấu hình và **kiểm tra chứng chỉ**.
- [ ] Base DN phù hợp với naming context và những OU mà ứng dụng cần truy cập.
- [ ] Bind DN là danh tính dịch vụ được LDAP server chấp nhận, tách biệt với search base.
- [ ] Bind password được cung cấp bằng cơ chế quản lý bí mật, có quy trình rotation.
- [ ] ACL chỉ cấp quyền cần thiết; thao tác đọc và ghi được phân quyền rõ.
- [ ] Có phép thử truy vấn nhẹ, tin cậy và có timeout để kiểm tra readiness.
- [ ] Nếu có pooling, cơ chế quản lý danh tính, giới hạn kết nối và làm mới context được xác minh.
- [ ] Các luồng xác thực người dùng cuối dùng bind/API xác thực thích hợp, không so sánh password trong filter.
- [ ] Log và health check không tiết lộ credential hoặc dữ liệu LDAP nhạy cảm.

## 14. Ghi nhớ

- **Bind DN và bind password** là credential mà `LdapContextSource` dùng để lấy context xác thực cho thao tác LDAP. **Base DN** là gốc đặt tên của thao tác, không phải bind identity.
- **Khởi tạo bean không đồng nghĩa đã bind thành công.** Xác thực/kết nối thực tế có thể diễn ra khi lấy hoặc sử dụng context; pooling có thể làm thay đổi số lần tạo kết nối vật lý.
- **Service bind** dùng cho truy vấn của ứng dụng; **user bind** dùng khi cần xác thực người dùng cuối. Không trộn credential hoặc dùng filter `userPassword` làm cơ chế đăng nhập.
- Dùng `LdapTemplate` để quản lý thao tác và lifecycle context. Phân biệt `ldapTemplate.bind(...)` (tạo entry) với **LDAP protocol bind** (xác thực).
- Bảo vệ simple bind bằng LDAPS/StartTLS đã xác thực chứng chỉ, quản lý secret và rotation, đặt timeout, thiết kế pooling có kiểm soát, và kiểm thử quyền trên thư mục lab trước khi vận hành.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Boot – LDAP application properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [RFC 4511 – Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4513 – LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)
