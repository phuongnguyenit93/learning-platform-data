# Read-only context và context dùng để thay đổi dữ liệu trong Spring LDAP

## 1. Vì sao cần phân biệt context đọc và context ghi?

Một ứng dụng tích hợp dịch vụ thư mục LDAP thường có hai loại công việc: **tra cứu** (tìm người dùng theo UID, đọc email, tra nhóm) và **thay đổi dữ liệu** (tạo entry, sửa thuộc tính, đổi DN/RDN hoặc xóa entry). Ở tầng Spring LDAP, giao diện **ContextSource** thể hiện sự phân biệt mục đích này bằng hai phương thức:

~~~java
DirContext getReadOnlyContext();
DirContext getReadWriteContext();
~~~

**getReadOnlyContext()** yêu cầu một directory context phục vụ các thao tác chỉ đọc. **getReadWriteContext()** yêu cầu context dành cho các thao tác có thể thay đổi entry. Cả hai đều cung cấp giao diện **javax.naming.directory.DirContext** của JNDI.

**Điểm quan trọng nhất:** tên phương thức không phải một ranh giới bảo mật. **Quyền thực tế do tài khoản bind, ACL và chính sách của LDAP server quyết định.** Lấy read-only context không tự động ngăn mọi lệnh ghi nếu bind identity có quyền ghi. Tương tự, lấy read-write context không tự động cấp quyền ghi cho tài khoản chỉ có quyền đọc.

Bài học thuộc chương **Cấu hình ContextSource** của module **Spring LDAP**. Nó liên hệ việc cấp context với DN, schema, search filter, LdapTemplate, LdapClient, ODM, xác thực, TLS, pooling, xử lý lỗi và kiểm thử truy cập thư mục an toàn.

Sau bài này, bạn cần hiểu:

- Khi nào Spring LDAP xin context phục vụ đọc hoặc ghi.
- Vì sao nên phân biệt **ý định của API** với **quyền của tài khoản trên máy chủ**.
- Cách cấu hình một hoặc nhiều LdapContextSource.
- Cách dùng LdapTemplate và khi nào cần dùng DirContext cấp thấp.
- Cách kiểm thử ACL, TLS, pooling và xử lý lỗi khi thao tác sửa thất bại.

## 2. ContextSource, DirContext và LdapTemplate có trách nhiệm gì?

~~~text
                   Service / Repository
                            |
                        LdapTemplate
                       /            \
               search / lookup   bind / modify / rename
                     |                  |
              read-only context   read-write context
                      \                /
                        ContextSource
                             |
                       LdapContextSource
                             |
                         JNDI LDAP
                             |
                      LDAP server + ACL
~~~

Đây là sơ đồ **mục đích sử dụng context**. Nó không khẳng định hai nhánh luôn tạo hai kết nối mạng vật lý khác nhau hoặc dùng hai bind DN khác nhau.

| Thành phần | Nhiệm vụ | Không đảm bảo điều gì? |
| --- | --- | --- |
| **ContextSource** | Cung cấp directory context theo yêu cầu | Không tự tạo chính sách ACL của server |
| **LdapContextSource** | Triển khai ContextSource dựa trên JNDI; cấu hình URL, base DN, credentials | Không chứng minh server đã kết nối được khi mới tạo bean |
| **DirContext** | Cung cấp các API JNDI đọc/sửa thư mục | Không phải kiểu Java chỉ đọc/chỉ ghi riêng biệt |
| **LdapTemplate** | Điều phối thao tác, lấy context, ánh xạ kết quả, quản lý tài nguyên | Không vượt qua ACL, schema hay chính sách LDAP |
| **LdapClient/ODM** | Cung cấp API fluent/ánh xạ entry nếu phiên bản hỗ trợ | Không thay đổi ngữ nghĩa quyền đọc/ghi |

ContextSource có các phương thức thường gặp:

~~~java
DirContext readContext = contextSource.getReadOnlyContext();
DirContext writeContext = contextSource.getReadWriteContext();
DirContext userContext = contextSource.getContext(principal, credentials);
~~~

Phương thức cuối nhận **danh tính và bí mật do lời gọi cung cấp**, có thể cần khi xác thực hoặc thao tác dưới một danh tính cụ thể. Nó không đồng nghĩa với việc thay đổi credentials mặc định của bean ContextSource.

Khi sử dụng **LdapTemplate** cho các phương thức như search, lookup, bind, modifyAttributes, rename hoặc unbind, template thường chịu trách nhiệm lấy và giải phóng context của thao tác. Khi gọi ContextSource trực tiếp, **lập trình viên phải đóng DirContext** sau khi sử dụng, kể cả khi phát sinh lỗi.

## 3. Ví dụ về quyền đọc và ghi trên cây LDAP

Giả sử thư mục thử nghiệm có cây:

~~~text
dc=example,dc=org
|-- ou=people
|   |-- uid=alice
|   |-- uid=bob
|   +-- ou=engineering
|       +-- uid=carol
|-- ou=groups
|   +-- cn=developers
+-- ou=system
    |-- cn=directory-reader
    +-- cn=directory-editor
~~~

Quản trị viên quy định:

- Tài khoản **directory-reader** được đọc những thuộc tính cần thiết của entry trong ou=people nhưng không có quyền thay đổi.
- Tài khoản **directory-editor** được đọc và sửa một số thuộc tính cho các entry thử nghiệm trong ou=people, chẳng hạn mail; không được tùy ý sửa schema hoặc các OU khác.

Đây chỉ là **mô hình quyền minh họa**, không phải ACL mà Spring LDAP tự tạo.

### 3.1. Ma trận phân quyền cần nhớ

| Context được xin | Bind identity | Đọc entry | Ghi entry |
| --- | --- | --- | --- |
| getReadOnlyContext() | reader chỉ có quyền đọc | Có, nếu ACL cho phép | Bị LDAP từ chối |
| getReadWriteContext() | reader chỉ có quyền đọc | Có, nếu ACL cho phép | **Vẫn bị LDAP từ chối** |
| getReadOnlyContext() | editor có quyền ghi | Có, nếu ACL cho phép | **Không tự bị chặn chỉ bởi tên API** |
| getReadWriteContext() | editor có quyền ghi | Có, nếu ACL cho phép | Có, trong giới hạn ACL/schema |

Trong cấu hình LdapContextSource thông thường, cả hai loại context **có thể dùng cùng danh tính bind đã cấu hình**. Một số cấu hình hoặc triển khai có thể dùng anonymous context cho thao tác đọc, chẳng hạn tùy chọn anonymous-read-only ở các phiên bản hỗ trợ. Khi dùng anonymous, cần kiểm tra LDAP server có cho phép anonymous read hay không, thay vì giả định mọi dữ liệu đều được trả về.

Phương thức getReadOnlyContext() là một **quy ước định hướng sử dụng**; nếu cần đảm bảo chức năng đọc không thể ghi, hãy sử dụng **tài khoản chỉ đọc thực sự** và **ACL do server thực thi**.

### 3.2. Search thành công không đảm bảo modify thành công

Một tài khoản có thể được cấp quyền tìm user có uid=alice, nhưng không được phép sửa mail, userPassword hay nhóm. Ngoài ACL, LDAP server còn kiểm tra DN có tồn tại, thuộc tính có hợp schema không, objectClass có phù hợp không và thao tác có được phép trong OU hay không. Vì vậy thao tác sửa thất bại không nên tự động được diễn giải là “ContextSource tạo sai loại context”.

## 4. Cấu hình một LdapContextSource và LdapTemplate

Ví dụ sau dùng một tài khoản dịch vụ trên LDAP thử nghiệm, với URL LDAPS, base DN và mật khẩu được cung cấp từ cấu hình ngoài:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Trong ví dụ:

1. **URL** ldaps://ldap.example.org:636 là endpoint và giao thức kết nối.
2. **Base DN** dc=example,dc=org là gốc giải quyết DN tương đối của template.
3. **Bind DN** là danh tính kết nối, không đồng nghĩa base DN; nó có thể nằm trong ou=system.
4. **Bind password** là bí mật; phải lưu trong secret manager hoặc môi trường được quản trị, không hard-code vào mã hoặc commit vào Git.

Các thuộc tính app.ldap.* là property tự định nghĩa. Nếu dùng Spring Boot auto-configuration, có các property LDAP khác như spring.ldap.urls, spring.ldap.base, spring.ldap.username và spring.ldap.password; hãy chọn cách cấu hình nhất quán, tránh vô ý tạo bean trùng chức năng.

### 4.1. Đọc bằng LdapTemplate

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonReader {
    private final LdapTemplate template;

    public PersonReader(LdapTemplate template) {
        this.template = template;
    }

    public List<String> findNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery q = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("uid").is(uid);

        return template.search(q, (AttributesMapper<String>) attrs -> {
            if (attrs.get("cn") == null) {
                return "";
            }
            return String.valueOf(attrs.get("cn").get());
        });
    }
}
~~~

Với ContextSource base dc=example,dc=org, query base tương đối ou=people có nghĩa bắt đầu từ ou=people,dc=example,dc=org. Scope SUBTREE cho phép tìm tại entry base và mọi hậu duệ; điều kiện uid lọc các entry phù hợp. Query builder escape **giá trị filter** thay vì ghép chuỗi từ đầu vào chưa tin cậy.

LdapTemplate lấy context đọc phù hợp qua ContextSource và đóng tài nguyên sau thao tác. Khi không có entry, search thường trả danh sách rỗng; khi bind, ACL, TLS hoặc base DN gặp lỗi, ứng dụng có thể nhận ngoại lệ thay vì kết quả rỗng.

### 4.2. Sửa thuộc tính bằng LdapTemplate

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonWriter {
    private final LdapTemplate template;

    public PersonWriter(LdapTemplate template) {
        this.template = template;
    }

    public void updateMail(String uid, String newMail) {
        if (uid == null || uid.isBlank() ||
                newMail == null || newMail.isBlank()) {
            throw new IllegalArgumentException("Missing required value");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem[] changes = {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("mail", newMail)
            )
        };

        template.modifyAttributes(dn, changes);
    }
}
~~~

**REPLACE_ATTRIBUTE** thay tập giá trị mail theo yêu cầu; nếu một thuộc tính đa trị thì cách dùng này có thể thay thế cả những giá trị khác. LdapNameBuilder xử lý escaping DN nhưng không quyết định username nào hợp lệ hoặc người dùng có quyền sửa entry không.

Nếu account cấu hình trong ContextSource chỉ có quyền đọc, lời gọi modifyAttributes này **vẫn bị LDAP server từ chối**, dù mã Java dùng API ghi. Trường hợp dữ liệu sai schema có thể bị từ chối kể cả khi dùng tài khoản editor hợp lệ.

## 5. Dùng DirContext trực tiếp: đọc/ghi và đóng tài nguyên

Khi cần JNDI cấp thấp, có thể lấy context theo ý định thao tác. Ví dụ sau **chỉ đọc** để minh họa việc xin hai loại context; không yêu cầu thay đổi dữ liệu thật.

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;

public class DirectDirectoryCheck {
    private final ContextSource contextSource;

    public DirectDirectoryCheck(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public boolean hasCn(String relativeDn) throws NamingException {
        DirContext context = contextSource.getReadOnlyContext();
        try {
            return context.getAttributes(relativeDn, new String[] {"cn"})
                    .get("cn") != null;
        } finally {
            context.close();
        }
    }

    public boolean hasMailWithWriteContext(String relativeDn)
            throws NamingException {
        DirContext context = contextSource.getReadWriteContext();
        try {
            // Loại context được xin không bắt buộc thao tác phải là ghi.
            return context.getAttributes(relativeDn, new String[] {"mail"})
                    .get("mail") != null;
        } finally {
            context.close();
        }
    }
}
~~~

DN tương đối ở đây, chẳng hạn uid=alice,ou=people, được giải quyết theo base đã cấu hình cho LdapContextSource.

**Nguyên tắc quản lý tài nguyên:**

- Luôn đóng DirContext lấy trực tiếp trong finally; không giữ chung context qua nhiều request/thread nếu không có hợp đồng rõ ràng.
- Khi search trực tiếp tạo NamingEnumeration, cũng cần đóng enumeration dù kết quả rỗng hay xảy ra lỗi.
- Nếu context do pool cấp, close() thường là bước trả tài nguyên về pool; **không bỏ close()** để mong tự tái sử dụng.
- Khi dùng LdapTemplate và callback do template quản lý, không tự đóng context mà framework đang sở hữu trong lúc callback thực thi.
- Ưu tiên template/client cho thao tác phổ biến vì giảm rủi ro rò rỉ tài nguyên và lặp mã JNDI.

## 6. Tách reader và writer bằng hai tài khoản dịch vụ

Trong hệ thống thực tế, tách trách nhiệm đọc/ghi bằng **hai tài khoản bind với ACL độc lập** là một mô hình quyền tối thiểu rõ ràng:

~~~text
                Spring application
                  /           \
             ReadRepository   WriteService
                   |              |
            readerTemplate   writerTemplate
                   |              |
             readerSource     writerSource
                   |              |
             LDAP reader      LDAP editor
                    \           /
                       LDAP ACL
~~~

Cùng một URL và base DN có thể được dùng cho cả hai, nhưng credentials khác nhau. Nếu cần endpoint đọc và ghi khác nhau, hãy xác nhận replication, quyền và đặc tính read-after-write của hạ tầng.

### 6.1. Ví dụ cấu hình hai ContextSource

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class SplitDirectoryConfig {
    private LdapContextSource create(
            String url, String base, String dn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(dn);
        source.setPassword(password);
        return source;
    }

    @Bean("readerSource")
    public LdapContextSource readerSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.reader.dn}") String dn,
            @Value("${app.ldap.reader.password}") String password) {
        return create(url, base, dn, password);
    }

    @Bean("writerSource")
    public LdapContextSource writerSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.writer.dn}") String dn,
            @Value("${app.ldap.writer.password}") String password) {
        return create(url, base, dn, password);
    }

    @Bean("readerTemplate")
    public LdapTemplate readerTemplate(
            @Qualifier("readerSource") LdapContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("writerTemplate")
    public LdapTemplate writerTemplate(
            @Qualifier("writerSource") LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

~~~yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    reader:
      dn: ${LDAP_READER_DN}
      password: ${LDAP_READER_PASSWORD}
    writer:
      dn: ${LDAP_WRITER_DN}
      password: ${LDAP_WRITER_PASSWORD}
~~~

Khi trong Spring container có hai bean cùng kiểu, phải đảm bảo tiêm đúng bean vào đúng service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryAccountService {
    private final LdapTemplate reader;
    private final LdapTemplate writer;

    public DirectoryAccountService(
            @Qualifier("readerTemplate") LdapTemplate reader,
            @Qualifier("writerTemplate") LdapTemplate writer) {
        this.reader = reader;
        this.writer = writer;
    }

    // Phương thức đọc gọi reader.search()/reader.lookup().
    // Phương thức cập nhật gọi writer.modifyAttributes(),
    // writer.bind(), writer.rename() hoặc writer.unbind().
}
~~~

Các bean minh họa chỉ tạo kết nối; ACL vẫn cần được cấu hình phía server. Nếu coder vô tình gọi reader.modifyAttributes(...) thì quyền đọc-only của **tài khoản reader** là lớp ngăn chặn ở server. Việc dùng nhiều template cũng yêu cầu kiểm tra bean auto-configuration nếu dự án có Spring Boot LDAP starter, để tránh tiêm nhầm hoặc phát sinh các bean không rõ vai trò.

### 6.2. Vì sao phải kiểm tra cả phạm vi và thuộc tính được ghi?

Một tài khoản editor không nên có quyền sửa mọi entry. Nếu nghiệp vụ chỉ cập nhật mail trong ou=people, ACL nên giới hạn đúng nhánh và đúng thuộc tính; không cấp quyền xóa người dùng, đổi objectClass hoặc sửa schema chỉ để đơn giản hóa code. Phạm vi base DN trong client giúp tổ chức truy vấn, nhưng **không thay thế ACL trên server**.


## 7. Xác thực người dùng khác với tài khoản dịch vụ

ContextSource có thể cung cấp context theo danh tính được chỉ định bằng getContext(principal, credentials). Trường hợp thường gặp là xác thực người dùng đăng nhập bằng cách bind dưới DN của họ. Quy trình điển hình:

1. Dùng tài khoản dịch vụ có quyền tìm kiếm để xác định DN của người dùng dưới một base phù hợp.
2. Kiểm tra mật khẩu do người dùng nhập bằng thao tác bind hoặc API authenticate của Spring LDAP, qua kết nối TLS an toàn.
3. Chỉ cấp phiên đăng nhập sau khi xác thực thành công; phân biệt sai mật khẩu với lỗi mạng, lỗi TLS hoặc LDAP server không khả dụng.
4. Không giữ, log, cache hoặc chia sẻ mật khẩu người dùng giữa các request.

Ví dụ Spring LDAP ở phiên bản hỗ trợ chữ ký authenticate tương ứng:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Giả định ldapTemplate, username, suppliedPassword đã có.
boolean valid = ldapTemplate.authenticate(
        query().base("ou=people").where("uid").is(username),
        suppliedPassword
);
~~~

Việc tài khoản dịch vụ tìm thấy người dùng **không chứng minh mật khẩu của người dùng đúng**. Nếu có nhiều entry khớp cùng UID hoặc account bị khóa, ứng dụng phải xử lý theo chính sách xác thực, không tự chọn ngẫu nhiên một entry.

**Không dùng chung context đã bind bằng người dùng A cho yêu cầu của người dùng B.** Vấn đề này càng quan trọng nếu ứng dụng sử dụng pooling hoặc đa luồng; ranh giới danh tính quan trọng hơn việc context được gọi là read-only hay read-write.

## 8. TLS, pooling và giới hạn truy cập

### 8.1. Read-only không đồng nghĩa không cần TLS

Tìm kiếm LDAP vẫn có thể lộ thông tin cá nhân như tên, email, nhóm và DN. Đặc biệt, thao tác simple bind có thể truyền credentials nếu đường truyền không được bảo vệ.

- **LDAPS** (ví dụ ldaps://ldap.example.org:636) thiết lập TLS từ đầu; client phải xác minh chuỗi chứng chỉ và hostname.
- **LDAP với StartTLS** bắt đầu trên ldap:// rồi nâng cấp TLS trước khi gửi mật khẩu hoặc dữ liệu nhạy cảm. Chỉ cấu hình ldap:// **không tự kích hoạt StartTLS**.
- Không hạ cấp xuống LDAP không mã hóa hoặc bỏ kiểm tra chứng chỉ chỉ để tránh lỗi kết nối.
- Tài khoản reader và writer đều cần cơ chế bảo vệ secrets, timeout và logging an toàn.

### 8.2. ContextSource không nhất thiết là một socket duy nhất

ContextSource cung cấp DirContext. Tùy cách cấu hình và provider, thao tác có thể tạo context mới hoặc dùng lại kết nối nhờ pooling. Pooling không tự:

- Cấp quyền ghi cho read-only identity.
- Sửa lỗi filter quá rộng, index thiếu hoặc base DN sai.
- Đảm bảo mọi connection còn hoạt động khi mượn lại.
- Bảo vệ khỏi rò rỉ danh tính khi tái sử dụng context của nhiều user.
- Đảm bảo tương thích với mọi cách dùng StartTLS.

Khi chọn cơ chế pooling Spring LDAP hoặc JNDI provider, cần xác minh cấu hình cụ thể theo phiên bản thư viện, đặc biệt với StartTLS và các kiểu bind. Không tự bật nhiều tầng pool cùng lúc nếu chưa hiểu vòng đời tài nguyên của từng tầng.

**Đóng context đúng cách vẫn bắt buộc.** Nếu wrapper lấy context từ pool, close() có thể trả tài nguyên về pool; nếu không có pool, nó có thể đóng kết nối thật. Không giữ context lâu dài với kỳ vọng giúp hệ thống nhanh hơn.

### 8.3. Giới hạn tìm kiếm và timeout

Một reader context có thể thực hiện subtree search trên hàng triệu entry. Vì thế, quyền đọc hạn chế về **thao tác ghi** không đồng nghĩa hạn chế về **chi phí truy vấn**.

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(200L);
controls.setTimeLimit(5000); // mili-giây
controls.setReturningAttributes(new String[] {"uid", "cn"});
~~~

Số liệu 200 kết quả và 5.000 ms chỉ là minh họa. Size/time limit của LDAP server có thể nghiêm ngặt hơn; khi bị vượt giới hạn, client có thể nhận lỗi thay vì toàn bộ tập kết quả. Với dữ liệu lớn, chọn base hẹp, filter có chỉ mục phù hợp và paging nếu server hỗ trợ.

Ngoài thời hạn tìm kiếm, có thể cần timeout mở kết nối và timeout đọc của JNDI LDAP provider. Không nên coi timeout là “không tìm thấy người dùng”; đó là một lỗi hạ tầng hoặc vận hành cần phân loại riêng.

## 9. Xử lý lỗi khi đọc hoặc cập nhật

| Tình huống | Dấu hiệu thường gặp | Cách xử lý |
| --- | --- | --- |
| Filter hợp lệ không khớp entry | Search trả danh sách rỗng | Kiểm tra base, scope, filter nếu kết quả bất thường |
| DN mục tiêu/base không tồn tại | LDAP result 32 / noSuchObject | Đối chiếu DN đầy đủ và DN tương đối |
| Reader bị từ chối sửa entry | LDAP result 50 / insufficientAccessRights hoặc phản hồi bảo vệ tương đương | Kiểm tra ACL, bind DN và template được tiêm |
| Writer ghi sai schema | LDAP result 65 / objectClassViolation | Kiểm tra objectClass, thuộc tính MUST/MAY và cú pháp |
| Tạo entry trùng DN | LDAP result 68 / entryAlreadyExists | Trả lỗi xung đột; không ghi đè |
| Xác thực sai thông tin | Lỗi bind/invalid credentials | Tách khỏi lỗi dịch vụ không hoạt động; tránh tiết lộ thông tin nội bộ |
| TLS hoặc kết nối hỏng | Handshake failure, connection failure, timeout | Sửa truststore, chứng chỉ, hostname, endpoint hoặc network |
| Kết quả bị cắt | Size/time limit, paging chưa hoàn tất | Không coi danh sách hiện có là tập kết quả đầy đủ |

Các mã LDAP ở bảng phản ánh những tình huống thường gặp; thông báo chi tiết có thể khác nhau theo máy chủ. Spring LDAP ánh xạ nhiều ngoại lệ JNDI thành ngoại lệ framework, nhưng việc đặt một catch-all rồi trả empty list cho cả lỗi kết nối và lỗi ACL sẽ che giấu sự cố.

Khi log, chỉ ghi thông tin cần thiết như loại thao tác, mã lỗi khi có, tên bean reader/writer, correlation ID và DN đã được hạn chế dữ liệu nhạy cảm. **Không log mật khẩu, toàn bộ bản ghi người dùng hoặc diagnostic message chưa được kiểm soát vào API công khai.**

### 9.1. Đọc lại trạng thái sau khi lỗi ghi

Nếu thao tác sửa đã gửi đi nhưng kết nối đứt trước khi nhận response, không thể chắc chắn server chưa áp dụng thay đổi. Trước khi retry một lệnh tạo, sửa, đổi DN hoặc xóa, nên đọc lại DN/thuộc tính liên quan bằng tài khoản có quyền phù hợp. Lời gọi LDAP không tự tạo một transaction phân tán bao trùm database, cache và các dịch vụ khác.

## 10. Kiểm thử read-only và read-write bằng LDAP server

Không chỉ mock ContextSource: **mock không chứng minh được ACL trên máy chủ**. Hãy dùng directory thử nghiệm riêng, chứng chỉ được xác minh, dữ liệu giả và hai tài khoản đã được cấp quyền theo chính sách của bài học.

### 10.1. Thử đọc bằng tài khoản reader

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=training-01,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn mail
~~~

Tham số -W nhập mật khẩu qua lời nhắc, tránh đưa bí mật vào lịch sử shell. Kết quả phụ thuộc ACL và sự tồn tại của entry. Nếu không nhận được dữ liệu, hãy kiểm tra cả filter, DN và quyền.

### 10.2. Thử cập nhật bằng tài khoản editor

Trên **entry thử nghiệm** do bạn kiểm soát, có thể chuẩn bị một thay đổi LDIF:

~~~ldif
dn: uid=training-01,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: training-01-updated@example.org
~~~

Lưu nội dung trên thành file update-test-mail.ldif trong môi trường thực hành và chạy:

~~~bash
ldapmodify -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -f update-test-mail.ldif
~~~

Sau khi editor sửa thành công, thực hiện phép kiểm thử từ chối bằng **reader identity** trên entry thử nghiệm, không trên tài khoản thật. Quan sát server chặn thay đổi theo ACL dự kiến, rồi đọc lại entry để chứng minh không phát sinh thay đổi trái phép.

Không nâng quyền tài khoản reader, không thay ACL sản xuất và không dùng dữ liệu thật để làm cho bài test “thành công”.

### 10.3. Ma trận tích hợp Spring LDAP

| Ca kiểm thử | Context được dùng | Kết quả kỳ vọng |
| --- | --- | --- |
| Search UID có thật | readerTemplate | Đọc được các thuộc tính có quyền |
| Search UID không tồn tại | readerTemplate | Danh sách rỗng nếu tìm kiếm thành công |
| Reader cố sửa mail | readerTemplate | Server từ chối; entry giữ nguyên |
| Writer sửa mail ở OU thử nghiệm | writerTemplate | Thành công khi đúng ACL/schema |
| Writer sửa ở OU ngoài phạm vi | writerTemplate | Server từ chối |
| Reader/writer dùng sai mật khẩu bind | ContextSource tương ứng | Lỗi xác thực |
| Truststore sai hoặc hostname TLS không khớp | Cả hai | Kết nối từ chối an toàn |
| Base DN sai | Cả hai | Lỗi DN hoặc kết quả phản ánh chính sách server |
| Lấy context trực tiếp và đóng | Cả hai | Tài nguyên được giải phóng/trả pool đúng vòng đời |

Không phụ thuộc thứ tự các entry được trả về. Test nên tạo và dọn dữ liệu riêng cho từng ca, tránh race condition nếu chạy song song.

## 11. Bài thực hành có hướng dẫn

**Bối cảnh:** một ứng dụng Spring LDAP cần tìm người dùng trên toàn bộ ou=people, nhưng chỉ được sửa thuộc tính mail của tài khoản thử nghiệm.

1. Xác định base DN, server URL, search scope và filter cho chức năng tìm người dùng.
2. Cấu hình LdapContextSource bằng reader bind DN; chạy LdapTemplate.search(...) để xác nhận quyền đọc.
3. Dùng chính ContextSource này yêu cầu getReadWriteContext() và giải thích vì sao quyền trên LDAP server vẫn không tăng lên.
4. Cấu hình writerSource và writerTemplate với tài khoản editor. Dùng @Qualifier để tiêm đúng template vào service sửa dữ liệu.
5. Tạo một entry training-01 tuân thủ schema trong OU thử nghiệm bằng tài khoản được cấp phép. Thực hiện tìm kiếm bằng reader và sửa mail bằng writer.
6. Kiểm thử reader cố thay đổi mail, writer cố sửa ngoài phạm vi và ghi nhận loại lỗi; xác minh trạng thái entry sau từng ca.
7. Tắt hoặc làm gián đoạn LDAP test server để quan sát timeout. Phân biệt lỗi kết nối với kết quả search không khớp.
8. Kiểm tra chứng chỉ, truststore, logging bí mật và lifecycle khi nhiều lời gọi chạy song song; nếu dùng pooling, xác minh việc trả context.
9. Viết báo cáo ngắn mô tả cách ACL phía server thực thi quyền tối thiểu và vì sao tên phương thức read-only/read-write không đủ thay thế ACL.

### Câu hỏi tự kiểm tra

1. Tại sao getReadOnlyContext() không phải một biện pháp đảm bảo chặn thao tác ghi ở server?
2. Nếu getReadWriteContext() dùng tài khoản chỉ có quyền đọc, modifyAttributes có được phép chạy thành công không?
3. LdapTemplate lấy context khác nhau thế nào cho search và thao tác sửa?
4. Vì sao hai bean ContextSource có credentials khác nhau cần các qualifier rõ ràng?
5. Trong trường hợp nào cần tự gọi close() và pooling có thay đổi nguyên tắc đó không?
6. Vì sao kết quả rỗng hợp lệ khác với lỗi bind, ACL hoặc TLS?
7. Sau khi write timeout, tại sao cần đọc lại entry trước khi tự retry?
8. Khi xác thực bằng mật khẩu người dùng, có thể tái sử dụng context bind của người dùng khác không?

## 12. Tổng kết

**ContextSource.getReadOnlyContext()** và **ContextSource.getReadWriteContext()** biểu đạt **mục đích sử dụng directory context**, không tự thiết lập quyền đọc/ghi trên server. Quyền thực tế thuộc về **danh tính bind, ACL, schema và chính sách LDAP server**. Spring LDAP cho phép thao tác với LdapTemplate hoặc LdapClient để giảm mã JNDI và quản lý tài nguyên; khi dùng DirContext trực tiếp, phải đóng context sau sử dụng. Nếu ứng dụng có cả chức năng tra cứu và cập nhật, tách reader/writer credentials cùng bean rõ ràng giúp áp dụng quyền tối thiểu. Cuối cùng, TLS được xác minh, timeout, pooling đúng ngữ cảnh, chẩn đoán lỗi và kiểm thử trên directory thử nghiệm là nền tảng để đọc và thay đổi LDAP an toàn.
