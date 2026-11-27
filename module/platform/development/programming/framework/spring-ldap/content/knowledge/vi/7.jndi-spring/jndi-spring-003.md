# `ContextSource` tạo và quản lý kết nối LDAP trong Spring LDAP

## 1. Vì sao ứng dụng cần `ContextSource`?

Một ứng dụng Java dùng LDAP phải biết **kết nối đến máy chủ nào, dùng danh tính nào để bind, bắt đầu truy vấn tại DN nào và đóng tài nguyên ra sao**. Nếu thao tác trực tiếp bằng JNDI, các thông tin này thường được lặp lại trong từng phương thức tạo người dùng, đọc nhóm hoặc tìm tài khoản. Spring LDAP tách phần hạ tầng đó thành **`ContextSource`**, để các lớp nghiệp vụ chủ yếu làm việc với `LdapTemplate`, `LdapClient` hoặc ODM.

`ContextSource` thuộc API Spring LDAP, chịu trách nhiệm cung cấp các **directory context** để truy cập thư mục. `LdapContextSource` là một triển khai thông dụng dựa trên JNDI. Nó sử dụng cấu hình endpoint, base DN, thông tin xác thực và các thuộc tính môi trường JNDI để tạo context khi cần. `LdapTemplate` nhận `ContextSource` rồi thực hiện truy vấn/thao tác với vòng đời tài nguyên được quản lý nhất quán.

```text
                  Ứng dụng Spring
                        |
              Service / Repository
                        |
           LdapTemplate / LdapClient
                        |
                  ContextSource
                        |
           LdapContextSource (JNDI)
                        |
          DirContext / LDAP operation
                        |
                  LDAPS / LDAP
                        |
                   LDAP server
```

Trong module **Spring LDAP**, việc hiểu `ContextSource` liên kết các phần kiến thức DN, schema, filter, search scope và thao tác entry với các khía cạnh vận hành: **bind, xác thực người dùng, TLS, pooling, timeout, xử lý lỗi và kiểm thử truy cập thư mục an toàn**. Bài học thuộc chương **JNDI và Spring** và tập trung vào ranh giới giữa cấu hình kết nối và mã nghiệp vụ.

Kết thúc bài, người học cần có thể giải thích:

- `ContextSource` khác gì `DirContext`, `LdapTemplate` và một kết nối TCP thực tế.
- Vì sao cấu hình `base`, bind DN và mật khẩu không thể thay thế lẫn nhau.
- Khi nào framework lấy/đóng context và khi nào lập trình viên phải tự đóng.
- Cách dùng một tài khoản dịch vụ để đọc/ghi và cách xử lý danh tính người dùng khi xác thực.
- Những điều kiện cần đánh giá khi cấu hình TLS, pooling, timeout và kiểm thử.

## 2. Từ JNDI trực tiếp đến `ContextSource`

### 2.1. Một thao tác JNDI cơ bản

Để tìm người dùng trong LDAP qua JNDI, ứng dụng thường phải dựng môi trường kết nối, tạo `InitialDirContext`, cấu hình tìm kiếm, ánh xạ kết quả và đóng tài nguyên:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

Hashtable<String, String> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
        "cn=directory-reader,ou=system,dc=example,dc=org");
env.put(Context.SECURITY_CREDENTIALS,
        System.getenv("LDAP_BIND_PASSWORD"));

DirContext context = new InitialDirContext(env);
try {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);

    NamingEnumeration<SearchResult> results = context.search(
            "ou=people,dc=example,dc=org",
            "(uid=alice)", controls);
    try {
        while (results.hasMore()) {
            SearchResult entry = results.next();
            System.out.println(entry.getName());
        }
    } finally {
        results.close();
    }
} finally {
    context.close();
}
```

Đây là ví dụ minh họa trực tiếp, chưa giải quyết hết tình huống vận hành. Nếu có mười phương thức truy vấn, những đoạn thiết lập `env`, quản lý `DirContext`, duyệt `NamingEnumeration` và chuyển đổi `NamingException` có thể bị lặp mười lần. Khi thay endpoint hoặc cách cấp thông tin xác thực, mã ở nhiều vị trí phải được sửa.

### 2.2. `ContextSource` gom cấu hình, template gom vòng đời

Spring LDAP tách trách nhiệm thành các lớp sau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `ContextSource` | Giao diện cung cấp directory context | `getReadOnlyContext()`, `getReadWriteContext()`, `getContext(...)` |
| `LdapContextSource` | Triển khai `ContextSource` dựa trên JNDI, với URL, base, bind credentials và cấu hình môi trường | Bean cấu hình một lần |
| `DirContext` | Context JNDI cụ thể để tìm kiếm hoặc thay đổi entry | Gọi `search`, `lookup`, `modifyAttributes` |
| `LdapTemplate` | Thực hiện các thao tác LDAP và quản lý vòng đời context/tài nguyên cho lời gọi template | `search`, `lookup`, `bind`, `modifyAttributes` |
| `LdapClient` | API mức cao với cách gọi fluent trong các phiên bản Spring LDAP hỗ trợ | Tìm kiếm và thao tác thông qua context |
| ODM | Ánh xạ entry và thuộc tính LDAP sang mô hình đối tượng Java | Lớp ánh xạ người dùng, nhóm |

`ContextSource` **không phải một socket TCP cố định**. Nó là thành phần cung cấp context. Mỗi lần một thao tác cần truy cập LDAP, triển khai có thể tạo context mới hoặc lấy lại kết nối phù hợp từ cơ chế pooling đã cấu hình. Việc gọi `close()` trên context nghĩa là trả/giải phóng tài nguyên theo triển khai thực tế; khi có pool, thao tác này có thể trả context về pool thay vì đóng socket vật lý ngay lập tức.

> **Nguyên tắc:** ứng dụng nên tiêm một bean `ContextSource` đã cấu hình vào các thành phần truy cập LDAP, rồi sử dụng template/client cho các thao tác thông thường. Chỉ dùng `DirContext` trực tiếp khi cần hành vi đặc thù mà API mức cao chưa cung cấp.

## 3. Cấu hình `LdapContextSource` bằng Spring

### 3.1. Cấu hình Java Config

Ví dụ dưới đây dùng một máy chủ thử nghiệm tại `ldap.example.org`, có nhánh `dc=example,dc=org` và tài khoản dịch vụ được cấp quyền đọc cần thiết. Thông tin mật khẩu được đưa từ cấu hình bên ngoài, không ghi trực tiếp vào mã nguồn:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource contextSource(
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
    public LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Trong một `@Bean` được Spring quản lý, `LdapContextSource` nhận callback khởi tạo theo vòng đời bean, bao gồm kiểm tra/hoàn thiện các thông số cấu hình. Nếu bạn tự khởi tạo `LdapContextSource` **ngoài Spring container**, phải xem xét gọi phương thức khởi tạo cần thiết (chẳng hạn `afterPropertiesSet()`) theo hợp đồng của triển khai trước khi sử dụng.

Đây là cấu hình Spring Framework thuần. Nếu dùng Spring Boot với tính năng cấu hình LDAP được hỗ trợ, có thể dùng các thuộc tính `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username`, `spring.ldap.password` và cơ chế auto-configuration phù hợp. **Không cần đồng thời tạo các bean trùng chức năng** khi auto-configuration đã cung cấp bean mong muốn; hãy chọn một cách cấu hình nhất quán với dự án.

### 3.2. Phân biệt URL, base DN và bind DN

| Thiết lập | Ví dụ | Vai trò |
| --- | --- | --- |
| `url` | `ldaps://ldap.example.org:636` | Endpoint, giao thức và cổng của máy chủ |
| `base` | `dc=example,dc=org` | DN gốc dùng để giải quyết các DN tương đối trong thao tác |
| `bind-dn` | `cn=directory-reader,ou=system,dc=example,dc=org` | Danh tính đăng nhập của ứng dụng khi cần context đã xác thực |
| `bind-password` | Lấy từ biến môi trường/secret manager | Bí mật để bind bằng danh tính cấu hình |

**Bind DN** là một danh tính, còn **base DN** là gốc logic cho truy vấn. Chúng có thể ở những vị trí khác nhau. Không suy ra rằng một ứng dụng dùng base `dc=example,dc=org` bắt buộc phải bind bằng một user nằm trực tiếp dưới base.

Với cấu hình mẫu, gọi truy vấn có base tương đối `ou=people` có nghĩa truy vấn dưới `ou=people,dc=example,dc=org`. Không ghi cả `dc=example,dc=org` vào URL và tiếp tục cấu hình lặp lại DN này ở chỗ khác mà không hiểu cách nhà cung cấp thư viện xử lý: hãy giữ endpoint và base rõ ràng để tránh trùng hậu tố.

### 3.3. Base không phải search scope

`ContextSource.setBase(...)` thiết lập tiền tố/gốc cho DN tương đối; nó **không tự quyết định** tìm đúng entry, một cấp con hay toàn bộ subtree. Scope và filter là thông số của thao tác tìm kiếm, chẳng hạn:

```text
ContextSource base:   dc=example,dc=org
Search base:          ou=people
Effective search DN: ou=people,dc=example,dc=org
Search scope:         subtree
Filter:               (uid=alice)
```

Nếu LDAP server có nhiều naming context, việc chọn base vẫn cần căn cứ vào cấu trúc và quyền của thư mục. `ContextSource` không thể tự phát hiện “nhánh người dùng đúng” chỉ từ hostname.

## 4. Vòng đời của context khi dùng `LdapTemplate`

### 4.1. Context được lấy vào lúc thực hiện thao tác

Một luồng tìm kiếm điển hình có thể mô tả như sau:

```text
UserDirectoryRepository.findUser("alice")
        |
        v
LdapTemplate.search(query, mapper)
        |
        v
ContextSource.getReadOnlyContext()
        |
        v
JNDI tìm kiếm bằng DirContext
        |
        v
Mapper chuyển Attributes -> kết quả Java
        |
        v
Template giải phóng kết quả/context đúng vòng đời
        |
        v
Repository nhận dữ liệu hoặc ngoại lệ
```

Việc cấu hình bean `LdapContextSource` thành công **chưa chứng minh** rằng LDAP server đang truy cập được: nhiều triển khai chỉ thực sự mở kết nối/bind khi một context được lấy và dùng. Bài kiểm tra kết nối cần **thực hiện một thao tác LDAP thật**, không chỉ xác nhận bean được tạo.

### 4.2. Ví dụ repository tìm kiếm

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class UserDirectoryRepository {
    private final LdapTemplate ldapTemplate;

    public UserDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDisplayNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery q = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("uid").is(uid);

        return ldapTemplate.search(
                q,
                (AttributesMapper<String>) attrs -> {
                    if (attrs.get("cn") == null) {
                        return ""; // Thay bằng chính sách nghiệp vụ phù hợp.
                    }
                    return String.valueOf(attrs.get("cn").get());
                }
        );
    }
}
```

Repository không mở và đóng `DirContext` thủ công. `LdapTemplate` lấy context cần thiết qua `ContextSource`, xử lý tài nguyên của thao tác và ánh xạ kết quả vào `List<String>`. Query builder tạo filter từ giá trị `uid`, giúp escape giá trị theo cú pháp LDAP filter; nó **không** thay thế quy tắc validate danh tính hay phân quyền truy cập.

Nếu không có entry phù hợp, một thao tác `search` thông thường trả danh sách rỗng. Nếu bind sai, server không khả dụng, base DN không hợp lệ hoặc quyền truy cập bị từ chối, lỗi có thể được ánh xạ thành ngoại lệ Spring LDAP. Không nên bắt mọi ngoại lệ rồi trả danh sách rỗng, vì điều đó khiến sự cố kết nối trông giống một kết quả hợp lệ.

### 4.3. Tìm kiếm và cập nhật có nhu cầu context khác nhau

`ContextSource` có các phương thức thường gặp:

```java
DirContext readContext = contextSource.getReadOnlyContext();
DirContext writeContext = contextSource.getReadWriteContext();
DirContext userContext = contextSource.getContext(principal, credentials);
```

Tên `getReadOnlyContext()` và `getReadWriteContext()` phản ánh mục đích sử dụng API. **Không nên hiểu `getReadOnlyContext()` như một ranh giới phân quyền chắc chắn ở máy chủ**: quyền thực tế vẫn do danh tính bind, ACL và chính sách LDAP server quyết định. Context lấy cho tài khoản chỉ có quyền đọc không thể sửa entry nếu ACL không cho phép, bất kể ứng dụng gọi phương thức cấp context nào.

Khi dùng `LdapTemplate` cho các lời gọi chuẩn như `search`, `lookup`, `bind`, `modifyAttributes`, `unbind`, việc lấy và giải phóng context được quản lý bên trong template. Không giữ context giữa các HTTP request hoặc chuyển context đang hoạt động sang nhiều thread tùy ý.

## 5. Khi phải dùng `DirContext` trực tiếp

Một số thao tác LDAP/JNDI đặc thù có thể cần truy cập context cấp thấp. Nếu dùng `ContextSource` trực tiếp, **người gọi chịu trách nhiệm đóng context** ngay cả khi có lỗi:

```java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;

public final class LowLevelLdapCheck {
    private final ContextSource contextSource;

    public LowLevelLdapCheck(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public boolean canReadPeopleOu() throws NamingException {
        DirContext context = contextSource.getReadOnlyContext();
        try {
            return context.getAttributes("ou=people", new String[] {"ou"})
                    .get("ou") != null;
        } finally {
            context.close();
        }
    }
}
```

Đoạn mã trên **chỉ mang tính minh họa** và giả định context được cấp có cách giải quyết DN nhất quán với cấu hình đã chọn. Với phần lớn nhu cầu ứng dụng, `ldapTemplate.lookup("ou=people", ...)` hoặc `ldapTemplate.search(...)` đơn giản hơn và giúp tránh phải tự quản lý vòng đời context.

Nếu thao tác trực tiếp trả `NamingEnumeration` hoặc tài nguyên LDAP khác, cũng cần đóng chúng trong `finally`. Nếu dùng wrapper hoặc pool, gọi `close()` theo hợp đồng của wrapper giúp trả context về cơ chế quản lý, không tự ý giữ một context để tái dùng lâu dài sau khi đã đóng.

### 5.1. Template callback thay vì giữ context ở tầng service

Khi cần làm việc cấp thấp nhưng muốn template giúp quản lý lifecycle, Spring LDAP còn có các cơ chế callback thao tác trên context (chẳng hạn `ContextExecutor`/`DirContextProcessor`, tùy API và phiên bản). Hãy dùng callback phù hợp khi thao tác cần được thực hiện trong một ngữ cảnh LDAP nhất định, thay vì xuất `DirContext` ra khỏi tầng truy cập dữ liệu. Trong callback, không đóng context do template sở hữu nếu hợp đồng callback không yêu cầu.

## 6. Service bind và xác thực người dùng là hai việc khác nhau

### 6.1. Bind bằng tài khoản dịch vụ

`setUserDn(...)` và `setPassword(...)` cấu hình danh tính thường dùng khi `LdapContextSource` tạo context phục vụ ứng dụng. Ví dụ, một `directory-reader` có quyền đọc các entry người dùng nhưng không được sửa schema hoặc xóa tài khoản. Ngược lại, chức năng quản lý tài khoản có thể cần một danh tính khác với quyền ghi giới hạn trong OU xác định.

Không cấu hình tài khoản quản trị thư mục có quyền rộng làm tài khoản mặc định chỉ để ứng dụng tìm `uid` hoặc `mail`. Việc cấp quyền tối thiểu giảm hậu quả nếu mã ứng dụng có lỗi và giúp kiểm thử ACL rõ ràng hơn.

### 6.2. Kiểm tra thông tin xác thực của người dùng

Khi ứng dụng cần xác thực mật khẩu người dùng, không thể lấy kết quả `search` thành công bằng tài khoản dịch vụ rồi kết luận mật khẩu người dùng đúng. Một quy trình phổ biến là:

1. Dùng tài khoản dịch vụ có quyền tìm kiếm cần thiết để xác định entry người dùng và DN.
2. Thử bind hoặc sử dụng cơ chế `authenticate(...)` bằng DN và mật khẩu do người dùng cung cấp, trên kết nối TLS phù hợp.
3. Chuyển kết quả thành trạng thái xác thực theo chính sách ứng dụng; phân biệt sai thông tin đăng nhập với lỗi mạng, lỗi chứng chỉ hoặc dịch vụ LDAP không hoạt động.

Ví dụ, với các phiên bản Spring LDAP hỗ trợ `LdapTemplate.authenticate(LdapQuery, String)`:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

boolean authenticated = ldapTemplate.authenticate(
        query().base("ou=people").where("uid").is(username),
        suppliedPassword
);
```

Thao tác này là **xác thực người dùng** chứ không thay đổi tài khoản bind mặc định của `LdapContextSource`. Đừng đưa `suppliedPassword` vào log, cache, exception message hoặc lưu thành thuộc tính LDAP. Cần giới hạn số lần thử và làm rõ hành vi khi có nhiều entry khớp UID. Nếu dự án dùng Spring Security, lớp bảo mật có thể điều phối quá trình xác thực và ủy quyền; `ContextSource` vẫn là thành phần hạ tầng truy cập thư mục.

### 6.3. `getContext(principal, credentials)` và trách nhiệm đóng

Ở mức thấp hơn, `ContextSource.getContext(principal, credentials)` yêu cầu một context dùng thông tin đăng nhập được cung cấp. Chỉ gọi cách này khi thực sự cần kiểm soát bind cụ thể và hiểu hợp đồng của triển khai. Sau khi sử dụng cần đóng context đúng cách. **Không chia sẻ context đã bind bằng người dùng A cho yêu cầu của người dùng B**; đây là ranh giới danh tính quan trọng khi cấu hình pooling hoặc giữ session lâu dài.

## 7. TLS, endpoint và cấu hình bảo mật kết nối

`ContextSource` cấu hình cách tạo kết nối nhưng không tự thay thế chính sách bảo mật mạng của hệ thống. Với LDAP, các lựa chọn phổ biến là:

| Hình thức | Ví dụ endpoint | Điều cần kiểm tra |
| --- | --- | --- |
| LDAPS | `ldaps://ldap.example.org:636` | TLS ngay khi thiết lập kết nối, xác minh hostname và chứng chỉ |
| LDAP với StartTLS | `ldap://ldap.example.org:389` rồi nâng cấp TLS | Client phải thực hiện StartTLS trước khi gửi thông tin nhạy cảm; cấu hình có thể cần xử lý JNDI đặc thù |
| LDAP không TLS | `ldap://ldap.example.org:389` không nâng cấp | Không phù hợp để gửi mật khẩu simple bind hoặc dữ liệu nhạy cảm qua mạng không được bảo vệ |

Điểm quan trọng: chỉ đặt URL `ldap://...` **không tự khởi động StartTLS**. Khi cần StartTLS, ứng dụng phải cấu hình đúng cơ chế nâng cấp TLS mà API/phiên bản thư viện hỗ trợ; cần xem xét cách tạo và đóng context, pooling và hành vi TLS của máy chủ. Nếu tổ chức chuẩn hóa LDAPS, ví dụ `ldaps://...` có thể đơn giản hơn về mặt vòng đời kết nối.

Một số lỗi vận hành thường gặp là chuỗi chứng chỉ không được truststore tin cậy, chứng chỉ không khớp tên máy chủ, URL trỏ sai cổng hoặc mạng không cho phép kết nối. **Không vô hiệu hóa kiểm tra chứng chỉ/hostname để sửa lỗi**; hãy sửa endpoint, chứng chỉ và truststore. Secret nên đến từ secret manager hoặc biến môi trường được quản trị an toàn; tránh commit mật khẩu vào file cấu hình hoặc hiển thị trong log.

### 7.1. Nhiều LDAP server và failover

`LdapContextSource` có thể được cấu hình nhiều URL tùy phiên bản/thư viện và JNDI provider, ví dụ các endpoint phục vụ cùng thư mục. Nhưng đặt nhiều URL không tự đảm bảo mọi máy chủ chứa dữ liệu nhất quán, mọi thao tác ghi sẽ failover an toàn hoặc mọi lỗi đều được thử lại. Cần xác nhận đặc tính replication, read/write routing, timeout và chính sách retry của hạ tầng.

Đặc biệt, nếu request ghi đã được gửi nhưng kết nối đứt trước khi nhận response, **không biết chắc** server đã áp dụng thay đổi hay chưa. Trước khi tự thử lại thao tác tạo/sửa/xóa entry, cần đọc lại trạng thái để tránh lặp hoặc va chạm dữ liệu.

## 8. Pooling: giảm chi phí, nhưng phải kiểm soát danh tính

Tạo connection/bind mới cho mỗi thao tác có chi phí về mạng và TLS. Pooling có thể giúp tái sử dụng kết nối/context khi workload lớn, nhưng **không phải mọi kết nối LDAP đều nên được tái sử dụng như nhau**.

Spring LDAP có các cách phối hợp với pooling, ví dụ `PoolingContextSource` trong mô-đun tương ứng của các phiên bản thư viện hỗ trợ, hoặc khả năng pooling của JNDI provider. API, dependency và cách cấu hình khác nhau theo phiên bản. Cần lựa chọn một cơ chế phù hợp với thiết kế authentication, TLS và server; không bật đồng thời nhiều tầng pooling một cách vô thức.

### 8.1. Những thông số nên quan sát

| Chủ đề | Câu hỏi cần trả lời |
| --- | --- |
| Kích thước pool | Tải đồng thời cao nhất là bao nhiêu, server cho phép bao nhiêu kết nối? |
| Thời gian chờ | Nếu pool hết context, thao tác chờ bao lâu trước khi trả lỗi? |
| Validation | Context đã cũ/mất kết nối có được phát hiện trước khi dùng lại không? |
| Idle/eviction | Kết nối nhàn rỗi được giữ trong bao lâu, ai đóng chúng? |
| Danh tính bind | Context có thể được tái dùng dưới cùng danh tính không; xác thực người dùng có cần tách riêng? |
| TLS/StartTLS | Cơ chế pool có tương thích với vòng đời nâng cấp TLS không? |

Không dùng pooling để che giấu truy vấn subtree quá rộng hoặc filter không có chỉ mục. Nhiều kết nối nhàn rỗi còn có thể làm tăng tài nguyên tiêu thụ phía server. Khi hệ thống có người dùng xác thực bằng bind riêng, phải bảo đảm không có rò rỉ trạng thái danh tính giữa các request.

### 8.2. `close()` khi có pool

Ở tầng code, quy tắc vẫn là **đóng context khi xong việc**. Nếu `ContextSource` cấp context từ pool, thao tác đóng theo wrapper thường trả tài nguyên về pool; nếu là context không pool, nó có thể đóng kết nối. Vì vậy, cách đúng không phải bỏ `close()` để tự “tái sử dụng kết nối”, mà là cấu hình pool và tuân thủ hợp đồng đóng tài nguyên của thư viện.

## 9. Timeout, lỗi và khả năng quan sát

### 9.1. Timeout có thể thuộc nhiều lớp

Một ứng dụng LDAP cần xem xét ít nhất ba nhóm thời hạn:

1. **Thời hạn tạo kết nối:** server không phản hồi hoặc mạng chặn kết nối.
2. **Thời hạn đọc/nhận kết quả từ socket:** TCP đã kết nối nhưng thao tác không hoàn tất.
3. **Giới hạn của thao tác tìm kiếm:** count/time limit trong `SearchControls` hoặc giới hạn từ LDAP server.

Với JNDI LDAP provider, một số thuộc tính môi trường thường gặp là `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` (đơn vị mili-giây theo tài liệu provider). Cách truyền các thuộc tính này vào `LdapContextSource` có thể dùng cơ chế environment properties của phiên bản thư viện:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Object> env = new HashMap<>();
env.put("com.sun.jndi.ldap.connect.timeout", "3000");
env.put("com.sun.jndi.ldap.read.timeout", "5000");

source.setBaseEnvironmentProperties(env);
```

Đoạn mã trên là phần bổ sung trong phương thức cấu hình đang có biến `source` là `LdapContextSource`. Đây là các property **đặc thù JNDI LDAP provider**, không phải chuẩn cho mọi LDAP client hoặc mọi provider Java. Giá trị minh họa cần được điều chỉnh theo độ trễ, SLA và hành vi máy chủ thực tế.

### 9.2. Phân loại lỗi theo tình huống

| Triệu chứng | Nhóm nguyên nhân | Phản ứng phù hợp |
| --- | --- | --- |
| Search trả danh sách rỗng | Không có entry phù hợp với base/filter hoặc ACL che kết quả | Xác minh base, scope, filter và quyền, không coi là lỗi kết nối mặc định |
| Bind thất bại | Sai credentials, chính sách xác thực hoặc người dùng bị khóa | Xử lý xác thực theo chính sách, không lộ DN nội bộ |
| Kết nối bị từ chối/timeout | Server, firewall, network, pool hoặc endpoint lỗi | Đánh dấu lỗi hạ tầng, giám sát và retry có giới hạn khi thích hợp |
| TLS handshake thất bại | Chứng chỉ/hostname/truststore hoặc giao thức không tương thích | Sửa cấu hình bảo mật, không bỏ xác minh TLS |
| LDAP result `32` (`noSuchObject`) | DN gốc hoặc entry yêu cầu không tồn tại/không thể thấy | Kiểm tra DN đầy đủ và base đã cấu hình |
| LDAP result `50` (`insufficientAccessRights`) | Bind DN không có quyền cho thao tác | Sửa ACL hoặc chọn tài khoản đúng phạm vi đã được phê duyệt |
| LDAP result `65` (`objectClassViolation`) | Entry thêm/sửa không hợp lệ theo schema | Kiểm tra objectClass, MUST/MAY và thuộc tính |
| Kết quả bị giới hạn | Size/time limit hoặc paging không hoàn tất | Không coi dữ liệu đã đầy đủ; điều chỉnh query/paging |

Spring LDAP chuyển nhiều ngoại lệ JNDI thành hệ ngoại lệ của Spring LDAP. Lớp gọi nên xử lý lỗi theo **loại nghiệp vụ/hạ tầng**, không phụ thuộc chuỗi thông báo tự do của server. Log cần đủ thông tin cho chẩn đoán (loại thao tác, endpoint, mã LDAP khi có, correlation ID) nhưng không đưa mật khẩu hay dữ liệu cá nhân vượt mức cần thiết.

### 9.3. Health check cần truy cập LDAP thật

Tạo bean `LdapContextSource` hoặc mở TCP đến cổng LDAP không đủ chứng minh ứng dụng có thể bind và tìm kiếm. Health check nên thực hiện một thao tác đọc **nhẹ**, phù hợp quyền tài khoản, ví dụ lookup một entry cấu hình sẵn hoặc một truy vấn có base/filter giới hạn. Health check quá rộng hoặc tần suất cao có thể tự gây tải lên server; cũng không nên trả DN, credentials hay lỗi TLS chi tiết trong response health công khai.

## 10. Kiểm thử kết nối và quản lý context

Để xác minh ứng dụng, hãy dùng một thư mục LDAP thử nghiệm với nhánh `dc=example,dc=org`, người dùng mẫu và các tài khoản bind khác quyền. Một bài kiểm thử tích hợp phải thực sự kết nối LDAP server thay vì chỉ mock `LdapTemplate`, vì behavior của bind, ACL, TLS và pooling phụ thuộc server.

| Ca kiểm thử | Chuẩn bị | Kết quả nên quan sát |
| --- | --- | --- |
| Bean hợp lệ, server sẵn sàng | URL, base, bind credentials đúng | Search/lookup qua template thành công |
| Server tắt hoặc sai port | Endpoint không khả dụng | Thao tác thật thất bại theo thời hạn cấu hình; bean vẫn có thể được tạo |
| Sai mật khẩu bind | Bind DN tồn tại, mật khẩu sai | Không truy vấn được bằng context đã xác thực; lỗi được phân loại đúng |
| Sai base DN | ContextSource cấu hình hậu tố không có | Search/lookup thất bại hoặc không ra kết quả theo hành vi server, không kết luận lỗi schema |
| Tài khoản chỉ đọc cố ghi | ACL từ chối cập nhật | Lỗi quyền, entry vẫn giữ trạng thái trước thử nghiệm |
| Chứng chỉ TLS không tin cậy | Truststore không phù hợp | Kết nối bảo mật thất bại; không hạ cấp sang kết nối không mã hóa |
| Nhiều request đồng thời | Tải vừa phải trên LDAP test server | Theo dõi tài nguyên, pool, timeout và danh tính của mỗi context |
| Tra cứu người dùng không tồn tại | Filter hợp lệ, không có entry khớp | Search trả danh sách rỗng, không thành lỗi mạng |

### 10.1. Bài thực hành: từ JNDI sang Spring LDAP

1. Chuẩn bị LDAP thử nghiệm qua LDAPS, xác nhận chứng chỉ được truststore tin cậy. Tạo một tài khoản đọc trong `ou=system` và ít nhất hai user `inetOrgPerson` trong `ou=people`.
2. Với JNDI trực tiếp, viết một thao tác đọc theo DN và kiểm tra đoạn mã cần khởi tạo `DirContext`, cấu hình provider, sử dụng `NamingEnumeration` (nếu tìm kiếm) và đóng tài nguyên.
3. Chuyển sang Spring LDAP: tạo `LdapContextSource` với URL, base, bind DN, mật khẩu từ cấu hình ngoài, rồi tạo bean `LdapTemplate`.
4. Tìm cùng người dùng bằng `LdapTemplate.search(query().base("ou=people").where("uid").is(uid), ...)`. Xác nhận DN hiệu lực tương ứng với cấu hình `base`.
5. Thử sai mật khẩu bind và sai base DN. So sánh một danh sách kết quả rỗng hợp lệ với ngoại lệ kết nối hoặc LDAP result code khác.
6. Dùng tài khoản chỉ đọc thử cập nhật một entry thử nghiệm có kiểm soát; xác nhận ACL ngăn thao tác thay vì framework tự cấp quyền ghi.
7. Thiết lập timeout kết nối/đọc trong môi trường thử nghiệm, mô phỏng máy chủ không khả dụng và đo phản hồi. Xác minh không có retry vô hạn và không ghi credentials vào log.
8. Nếu thử pooling, theo dõi số context được mượn/trả, thời gian chờ và hành vi khi dùng nhiều danh tính. Đảm bảo mọi context lấy trực tiếp đều được đóng trong `finally`.

### 10.2. Tự đánh giá

1. Vì sao `LdapContextSource` không đồng nghĩa với một kết nối TCP duy nhất luôn mở?
2. Khi nào dùng `getReadOnlyContext()`, khi nào dùng `getReadWriteContext()` và quyền thực sự do đâu quyết định?
3. Nếu base của `ContextSource` là `dc=example,dc=org`, tìm dưới `ou=people` cần truyền DN tương đối nào?
4. Vì sao `LdapTemplate.search(...)` thường an toàn hơn việc giữ một `DirContext` dùng chung giữa các request?
5. Vì sao tạo bean thành công chưa đủ kết luận kết nối LDAP hoạt động?
6. Nếu người dùng đang xác thực bằng mật khẩu riêng, điều gì có thể sai khi một pool tái sử dụng context đã bind bằng người dùng khác?
7. Khi gặp timeout hoặc lỗi TLS, tại sao trả “không tìm thấy người dùng” lại là cách xử lý sai?

## 11. Ghi nhớ

**`ContextSource` là ranh giới giữa ứng dụng Spring và việc cung cấp directory context của LDAP.** `LdapContextSource` giữ cấu hình endpoint, base DN và danh tính bind; `LdapTemplate` cùng `LdapClient` sử dụng nó để thực hiện thao tác và quản lý vòng đời tài nguyên theo API. Một context có thể được tạo mới hoặc tái sử dụng từ pool, nhưng mọi thao tác vẫn phải tôn trọng ACL, schema, search scope và quy tắc DN/filter. Để kết nối an toàn, cần xác minh TLS, quản lý bí mật ngoài mã nguồn, kiểm soát danh tính người dùng, cấu hình timeout phù hợp và kiểm thử truy cập LDAP thực tế. Khi hiểu rõ `ContextSource`, ứng dụng sẽ dễ quản trị, chẩn đoán và mở rộng hơn mà không phải lặp lại mã JNDI ở từng chức năng.
