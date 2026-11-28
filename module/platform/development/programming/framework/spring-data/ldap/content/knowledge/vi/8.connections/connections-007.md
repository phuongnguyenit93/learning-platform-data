# Lấy context với danh tính chỉ định bằng ContextSource

Trong Spring LDAP, `ContextSource` là thành phần tạo ra các đối tượng `DirContext` để ứng dụng giao tiếp với directory. Thông thường, `LdapTemplate` và Spring Data LDAP repository dùng một **tài khoản dịch vụ được cấu hình trước** để tra cứu hoặc cập nhật entry. Nhưng đôi khi ứng dụng cần lấy một context bằng **danh tính khác được chỉ định cho đúng một lần sử dụng**: chẳng hạn xác minh mật khẩu của người dùng, thực hiện một phép đọc theo ACL của họ hoặc kiểm thử quyền truy cập của một Bind DN cụ thể.

Phương thức trọng tâm là:

~~~java
DirContext ctx = contextSource.getContext(principal, credentials);
~~~

`principal` thường là **DN đầy đủ** của entry dùng để LDAP Bind, `credentials` là thông tin xác thực của danh tính đó, còn `ctx` là context đã được tạo với các thông số kết nối của `ContextSource`. Bạn **phải đóng context sau khi sử dụng**, không thay đổi username/password của bean `ContextSource` dùng chung và không nhầm context “read-only” với tài khoản chắc chắn không có quyền ghi.

Bài thuộc chương **Kết nối** của `SPRING_DATA_LDAP`. Chúng ta sẽ đi từ DN, `objectClass` và LDAP Bind đến ba phương thức của `ContextSource`, code Java an toàn, phương án dùng `LdapTemplate.authenticate`, liên hệ với Spring Security, Spring Data LDAP repository, ACL, TLS và kiểm thử trực tiếp với directory.

## 1. Sau bài này bạn làm được gì?

1. Giải thích vì sao `ContextSource` là **factory tạo context**, không phải một phiên đăng nhập toàn cục.
2. So sánh `getReadOnlyContext()`, `getReadWriteContext()` và `getContext(principal, credentials)`.
3. Xác định chính xác **DN đầy đủ dùng để Bind** và **DN tương đối dùng để lookup** khi `ContextSource` có cấu hình `base`.
4. Tạo một `DirContext` với danh tính chỉ định rồi đóng nó trong `finally` bằng `LdapUtils.closeContext`.
5. Phân biệt **xác thực thành công** với **được phép Search/Read/Modify theo ACL**.
6. Tìm DN người dùng theo `uid` bằng `LdapTemplate` và filter an toàn trước khi Bind.
7. Dùng `LdapTemplate.authenticate(LdapQuery, password)` khi chỉ cần xác thực, tránh tự viết lại toàn bộ luồng.
8. Hiểu khi nào nên dùng Spring Security hoặc `AuthenticationSource` thay vì đổi credential tạm thời.
9. Xử lý mật khẩu rỗng, lỗi Bind, lỗi quyền, giới hạn kết nối, TLS và referral.
10. Kiểm thử cả trường hợp **đúng danh tính**, **sai mật khẩu**, **không đủ ACL**, **thiếu entry** và **đóng context**.

## 2. Bối cảnh: cùng directory nhưng nhiều danh tính

Giả sử hệ thống danh bạ có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    ├── cn=svc-directory-reader
    └── cn=svc-account-admin
~~~

DN của Lan:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Entry minh họa:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
title: Backend Developer
~~~

Với schema `inetOrgPerson`, `cn` và `sn` là các thuộc tính bắt buộc kế thừa từ `person`. LDAP Bind để xác thực Lan dùng **DN của Lan và mật khẩu tương ứng**; không dùng `uid=lan` đơn lẻ trừ khi server cung cấp một cơ chế username/principal riêng đã được cấu hình và kiểm chứng.

### Ba danh tính cần tách

| Danh tính | DN dùng Bind | Mục đích |
| --- | --- | --- |
| Reader dịch vụ | `cn=svc-directory-reader,ou=service,dc=example,dc=org` | Search và đọc các thuộc tính danh bạ được phép. |
| Quản trị dịch vụ | `cn=svc-account-admin,ou=service,dc=example,dc=org` | Tạo/sửa entry theo một luồng quản trị hạn chế. |
| Người dùng Lan | `uid=lan,ou=people,dc=example,dc=org` | Xác thực Lan và, nếu nghiệp vụ cho phép, thao tác trong phạm vi ACL của Lan. |

Cùng một LDAP server không đồng nghĩa các danh tính có cùng quyền. `Bind` kiểm tra danh tính; **ACL** kiểm tra các thao tác tiếp theo. Mật khẩu tài khoản reader hoặc admin không nên được thử như một phương án thay thế khi Bind của người dùng thất bại.

## 3. ContextSource là gì?

`org.springframework.ldap.core.ContextSource` cung cấp các method tạo `javax.naming.directory.DirContext`.

~~~text
                  ContextSource
                        |
          +-------------+------------------+
          |             |                  |
  getReadOnlyContext  getReadWriteContext  getContext(principal, credentials)
          |             |                  |
      DirContext    DirContext          DirContext
  cấu hình mặc định cấu hình mặc định  danh tính truyền trực tiếp
          |             |                  |
       Search        Modify            Bind riêng / thao tác riêng
~~~

Trong Spring LDAP, `LdapContextSource` là implementation phổ biến. Bean này chứa endpoint, base DN, mặc định Bind DN/mật khẩu và các tùy chọn khác; nó **không phải chính kết nối mạng** được giữ làm “context của người dùng hiện tại”.

### Ba phương thức quan trọng

| Method | Danh tính kết nối | Phù hợp với | Điểm phải hiểu |
| --- | --- | --- | --- |
| `getReadOnlyContext()` | Theo cấu hình `ContextSource`; có thể anonymous nếu được cấu hình. | Search/Lookup. | Tên “read-only” không thay thế ACL LDAP. |
| `getReadWriteContext()` | Theo cấu hình `ContextSource`. | Add/Modify/Delete khi account được cấp quyền. | Không tự nâng quyền chỉ vì tên method. |
| `getContext(principal, credentials)` | **Chính principal/credentials đã truyền** cho context này. | Xác thực hoặc thao tác có chủ đích dưới danh tính khác. | Tạo context riêng, phải đóng và bảo vệ credential. |

Với `AbstractContextSource`, mặc định cả read-only và read-write dùng thông tin xác thực đã cấu hình. Tùy chọn `anonymousReadOnly=true` có thể khiến đường read-only dùng kết nối anonymous; đó là **một lựa chọn cấu hình khác**, không có nghĩa mọi thao tác read-only tự dùng danh tính người gọi HTTP.

**Một phép đọc vẫn có thể bị từ chối với account reader**, và một context lấy bằng `getReadWriteContext()` vẫn có thể không sửa được entry vì LDAP ACL không cho phép.

## 4. Điều gì xảy ra khi gọi getContext?

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Java Service
    participant CS as ContextSource
    participant LDAP as LDAP Server
    A->>CS: getContext(fullDn, password)
    CS->>LDAP: Kết nối TLS và LDAP Bind
    LDAP-->>CS: Kết quả xác thực
    alt Danh tính hợp lệ
        CS-->>A: DirContext với principal đã truyền
        A->>LDAP: Lookup / Search theo ACL của principal
        LDAP-->>A: Dữ liệu hoặc lỗi quyền
    else Không hợp lệ
        CS-->>A: NamingException / AuthenticationException
    end
    A->>CS: Đóng DirContext trong finally
~~~

Thứ tự là mô hình khái niệm. Một số nhà cung cấp JNDI/cơ chế xác thực có thể **trì hoãn việc kiểm tra Bind thực sự tới thao tác LDAP đầu tiên**. Vì vậy, việc method trả được đối tượng `DirContext` không luôn đủ để kết luận người dùng đã được xác thực trong mọi triển khai. Với hệ thống cần chứng minh Bind, hãy dùng API authenticate của Spring LDAP và kiểm thử với LDAP server/JDK thực tế; khi cần, thực hiện một thao tác đọc vô hại mà tài khoản được phép để kích hoạt xác thực.

### Không thay đổi ContextSource dùng chung

Không làm như sau:

~~~java
// KHÔNG LÀM: ContextSource singleton dùng chung giữa các request.
sharedContextSource.setUserDn(userDnFromRequest);
sharedContextSource.setPassword(passwordFromRequest);
ldapTemplate.search(...);
~~~

Đoạn mã trên có thể khiến hai request đồng thời **lẫn danh tính**, để lộ credential qua trạng thái bean, khiến repository dùng nhầm quyền người dùng và gây khó xoay vòng secret.

Đúng hơn, để bean giữ nguyên cấu hình và lấy context **cục bộ**:

~~~java
DirContext ctx = null;
try {
    ctx = contextSource.getContext(fullUserDn, userPassword);
    // Sử dụng ctx trong phạm vi ngắn của request này.
} finally {
    LdapUtils.closeContext(ctx);
}
~~~

`getContext` không đổi `setUserDn` hay `setPassword` của `ContextSource` cho các request khác.

## 5. Cấu hình LdapContextSource trong Spring Boot

Sử dụng Spring Boot và Spring LDAP tương thích trong module. Nếu chỉ có một directory, có thể dùng `spring.ldap.*` để Spring Boot cấu hình kết nối chung. Để minh họa rõ danh tính, bài này tạo **một bean được đặt tên** từ namespace riêng của ứng dụng.

`application.yml`:

~~~yaml
directory:
  url: ldaps://ldap.example.org:636
  base: dc=example,dc=org
  reader:
    bind-dn: cn=svc-directory-reader,ou=service,dc=example,dc=org
    password: "${LDAP_READER_PASSWORD}"
~~~

Đây là **configuration namespace tự định nghĩa**, không phải toàn bộ auto-configuration `spring.ldap.*`. Mật khẩu thật lấy từ secret manager hoặc biến môi trường, không commit vào Git.

`config/DirectoryConnectionConfig.java`:

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConnectionConfig {

    @Bean("directoryContextSource")
    public LdapContextSource directoryContextSource(
            @Value("${directory.url}") String url,
            @Value("${directory.base}") String base,
            @Value("${directory.reader.bind-dn}") String bindDn,
            @Value("${directory.reader.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);

        // Không tự động chuyển credential sang referral bất ngờ.
        source.setReferral("throw");

        // Không bật native JNDI pooling cho ví dụ authentication.
        source.setPooled(false);
        return source;
    }

    @Bean("directoryLdapTemplate")
    public LdapTemplate directoryLdapTemplate(
            @Qualifier("directoryContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

Spring container gọi `afterPropertiesSet()` trong lifecycle của bean `LdapContextSource`. Nếu tạo thủ công ngoài Spring container, cần tự hoàn tất lifecycle theo Javadoc trước khi dùng. Bean `directoryLdapTemplate` phục vụ Search bằng **reader account**; `contextSource.getContext(userDn,password)` vẫn có thể dùng **danh tính khác** cho một context riêng.

### Một cảnh báo về nhiều bean

Nếu dự án có thêm ContextSource cho quản trị và Spring Data LDAP repository, cần dùng `@Qualifier` và cấu hình repository `ldapTemplateRef` chính xác. Không dựa vào `@Primary` trỏ vào tài khoản admin rồi nghĩ các thao tác đọc luôn được thực hiện bằng reader.

## 6. DN dùng Bind phải là DN đầy đủ

Giả sử cấu hình:

~~~text
ContextSource.base = dc=example,dc=org
~~~

Có ba chuỗi dễ bị nhầm:

| Giá trị | Ý nghĩa | Có dùng trực tiếp làm principal Bind theo ví dụ không? |
| --- | --- | --- |
| `lan` | Username nghiệp vụ. | **Không**. Cần xác định DN trước. |
| `uid=lan,ou=people` | DN tương đối với `ContextSource.base`. | **Không** cho `getContext` theo hợp đồng Spring LDAP. |
| `uid=lan,ou=people,dc=example,dc=org` | DN đầy đủ của Lan. | **Có**. |

Tài liệu Spring LDAP nhấn mạnh rằng `principal` gửi vào `getContext(principal, credentials)` cần là **DN đầy đủ**, dù `ContextSource` đã cấu hình `base`.

Trái lại, **địa chỉ entry khi thực hiện lookup trên context** thường dùng DN **tương đối với base**. Ví dụ, để đọc entry Lan:

~~~text
Principal dùng Bind:
uid=lan,ou=people,dc=example,dc=org

DN dùng ctx.getAttributes(...) với ContextSource.base:
uid=lan,ou=people
~~~

**Không** tự bỏ `dc=example,dc=org` khỏi principal Bind, cũng không tự nối base thêm lần nữa vào DN của một LDAP operation.

### Xây DN bằng LdapNameBuilder

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name fullUserDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

Name relativeUserDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", "lan")
        .build();
~~~

Kết quả:

~~~text
fullUserDn     = uid=lan,ou=people,dc=example,dc=org
relativeUserDn = uid=lan,ou=people
~~~

`LdapNameBuilder` giúp escape và ghép DN theo cấu trúc; không làm:

~~~java
// Không dùng với dữ liệu đầu vào chưa tin cậy.
String dn = "uid=" + uidFromHttp + ",ou=people,dc=example,dc=org";
~~~

DN escaping theo RFC 4514 và LDAP filter escaping theo RFC 4515 **khác nhau**.

## 7. Ví dụ tối giản: lấy và đóng context bằng danh tính Lan

Đoạn sau minh họa API cốt lõi. `principalDn` phải lấy từ một bước chọn người dùng **đã giới hạn về OU**, không lấy trực tiếp DN tùy ý từ HTTP client.

`service/SelectedIdentityContextDemo.java`:

~~~java
package com.example.directory.service;

import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class SelectedIdentityContextDemo {

    private final ContextSource contextSource;

    public SelectedIdentityContextDemo(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public String readOwnDisplayName(
            String fullUserDn,
            String userPassword,
            String relativeUserDn) throws NamingException {

        if (fullUserDn == null || fullUserDn.isBlank()
                || userPassword == null || userPassword.isEmpty()) {
            throw new IllegalArgumentException(
                    "Principal and non-empty password are required");
        }

        DirContext ctx = null;
        try {
            // Bind với chính danh tính được chỉ định.
            ctx = contextSource.getContext(fullUserDn, userPassword);

            // DN của thao tác thường tương đối với ContextSource.base.
            // Đây cũng là một thao tác thực tế để kiểm tra hành vi
            // của provider có thể trì hoãn xác thực lúc tạo context.
            Attributes attrs = ctx.getAttributes(
                    relativeUserDn,
                    new String[] { "cn" });

            return attrs.get("cn").get().toString();
        } finally {
            // DirContext KHÔNG phải AutoCloseable trong ví dụ này.
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

**Giới hạn của ví dụ tối giản:** nhận `fullUserDn` và `relativeUserDn` độc lập tạo nguy cơ hai giá trị **không trỏ cùng một người** nếu caller không đáng tin. Trong code thật, chúng phải được service xây từ **cùng một UID đã được kiểm tra**, hoặc lấy từ kết quả Search đã xác minh tính duy nhất. `attrs.get("cn")` có thể null nếu ACL che thuộc tính; triển khai production cần xử lý thay vì mặc định đọc được.

### Vì sao phải đóng DirContext?

- Mỗi context có thể giữ tài nguyên kết nối/socket ở provider.
- Nếu không đóng, số lượng kết nối mở tăng dần dưới tải.
- `ContextSource#getContext(...)` **không dùng native Java LDAP pooling** theo hợp đồng API, kể cả khi ContextSource được cấu hình pooling kiểu đó, nhằm giúp thay đổi mật khẩu có tác dụng kịp thời.
- Không đưa context vào biến static, singleton, session HTTP hoặc cache ứng dụng.
- Không tái sử dụng context có danh tính A cho request của danh tính B.

Ngay cả khi Bind thất bại trước khi có context, `finally` với `LdapUtils.closeContext(null)` vẫn an toàn.

## 8. Xác thực DN người dùng nên bắt đầu từ Search có kiểm soát

Ở nhiều hệ thống, người dùng đăng nhập bằng `uid` chứ không biết DN đầy đủ. Bạn phải tìm được DN duy nhất trước khi gọi `getContext`.

Các bước:

1. Nhận `uid` và mật khẩu qua HTTPS.
2. Kiểm tra `uid` theo policy và mật khẩu **không rỗng**.
3. Dùng reader service account Search người dùng trong `ou=people` bằng filter builder.
4. Nếu tìm được **đúng một DN đầy đủ**, dùng DN đó cho Bind.
5. Nếu không tìm thấy, tìm nhiều hơn một hoặc Search không đầy đủ, **không tự Bind bằng DN đoán**.
6. Không tiết lộ cho HTTP client liệu username có tồn tại hay không; giới hạn thử đăng nhập để giảm nguy cơ enumeration.

### Search DN với LdapTemplate

`service/UserDnResolver.java`:

~~~java
package com.example.directory.service;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Component;

@Component
public class UserDnResolver {

    private final LdapTemplate readerTemplate;

    public UserDnResolver(
            @Qualifier("directoryLdapTemplate")
            LdapTemplate readerTemplate) {
        this.readerTemplate = readerTemplate;
    }

    public String resolveUniqueFullDn(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(2)
                .timeLimit(2_000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        List<String> fullDns = readerTemplate.search(
                query,
                (ContextMapper<String>) entry ->
                    ((DirContextOperations) entry)
                            .getNameInNamespace());

        if (fullDns.size() != 1) {
            // Trong login, bề mặt lỗi công khai là chung;
            // không để client đoán tài khoản có tồn tại hay không.
            throw new IllegalStateException(
                    "User entry was not resolved uniquely");
        }

        return fullDns.get(0);
    }
}
~~~

`DirContextOperations.getNameInNamespace()` cung cấp DN đầy đủ của entry mà Spring LDAP ánh xạ. `@Id Name` trong một entity ODM có thể chứa DN tương đối với context; không tự lấy `@Id.toString()` rồi giả định đó luôn là principal đầy đủ.

### Các lưu ý đối với Search trước Bind

- `SearchScope.SUBTREE` chỉ cần thiết khi người dùng nằm trong OU con. Nếu tất cả user trực tiếp dưới `ou=people`, dùng `ONELEVEL` sẽ hẹp hơn.
- `countLimit(2)` giúp phát hiện ít nhất hai kết quả trùng UID trong trường hợp thuận lợi; cần cấu hình **không bỏ qua lỗi size limit/partial result** khi kết quả phải là duy nhất.
- `timeLimit(2_000)` dùng **mili giây** ở Spring LDAP/JNDI; nó không thay thế connect/read timeout.
- `LdapQueryBuilder.where(...).is(uid)` escape giá trị filter; không ghép `"(uid=" + uid + ")"`.
- Search rỗng có thể do thiếu quyền, không có entry hoặc sai base/scope; lỗi môi trường cần được phân biệt với sai thông tin đăng nhập.
- Trên directory lớn, uniqueness của `uid` phải được đảm bảo theo policy/index phù hợp, không dựa riêng vào `List.size()`.

Với quy trình login production, phương án được framework quản lý ở mục 11 hoặc Spring Security ở mục 12 thường tốt hơn tự nối các bước Search + Bind.

## 9. Ví dụ service xác thực có phân biệt lỗi

Để hiểu rõ API `getContext`, đoạn dưới ghép bước tìm DN với bước tạo context. Nó phù hợp cho thực hành, **không thay thế đầy đủ cơ chế xác thực web**.

`service/DirectoryBindVerifier.java`:

~~~java
package com.example.directory.service;

import javax.naming.AuthenticationException;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;
import org.springframework.stereotype.Service;

@Service
public class DirectoryBindVerifier {

    public enum BindStatus {
        VALID,
        INVALID_CREDENTIALS
    }

    private final UserDnResolver resolver;
    private final ContextSource contextSource;

    public DirectoryBindVerifier(
            UserDnResolver resolver,
            @Qualifier("directoryContextSource")
            ContextSource contextSource) {
        this.resolver = resolver;
        this.contextSource = contextSource;
    }

    public BindStatus verify(String uid, String password) {
        if (uid == null || uid.isBlank()
                || password == null || password.isEmpty()) {
            // Không thử LDAP Bind với mật khẩu rỗng.
            return BindStatus.INVALID_CREDENTIALS;
        }

        // Lỗi Search/DNS/TLS/ACL phải được phân loại riêng.
        // Không coi mọi lỗi hạ tầng là mật khẩu sai.
        String userFullDn = resolver.resolveUniqueFullDn(uid);

        DirContext ctx = null;
        try {
            ctx = contextSource.getContext(userFullDn, password);

            // Tùy provider, Bind có thể được thực hiện trễ;
            // ứng dụng thật nên dùng authenticate API có callback
            // khi cần thao tác kiểm chứng dưới user context.
            return BindStatus.VALID;
        } catch (AuthenticationException invalid) {
            return BindStatus.INVALID_CREDENTIALS;
        } catch (NamingException infrastructureOrPolicy) {
            throw new IllegalStateException(
                    "Directory authentication unavailable",
                    infrastructureOrPolicy);
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

**Cảnh báo nghiệp vụ:** `resolveUniqueFullDn` ở ví dụ có thể ném lỗi nếu không có entry, nếu tìm trùng hoặc có lỗi tài nguyên. Trong một hệ thống đăng nhập, cần ánh xạ trường hợp “đã Search đầy đủ và không có entry” thành kết quả xác thực thất bại **cùng thông báo chung** như sai mật khẩu, trong khi lỗi ACL/timeout/TLS phải được ghi nhận là sự cố. Không trả nguyên exception hoặc DN ra API.

Ngoài ra, theo cảnh báo của tài liệu Spring LDAP, một số cơ chế/server yêu cầu **thực hiện thêm operation trên context mới** để kích hoạt xác thực thực sự. Vì vậy, logic `return VALID` ngay sau khi lấy context chỉ là minh họa cho luồng phổ biến; **không dùng ví dụ này làm bộ xác thực production** nếu chưa kiểm thử provider. Dùng `LdapTemplate.authenticate(...)`, `LdapClient.authenticate(...)` hoặc Spring Security và callback được hỗ trợ để tránh sai sót này.

## 10. Dùng danh tính chỉ định để thực hiện thao tác theo ACL

`getContext` không chỉ có thể được dùng để xác thực. Nó trả `DirContext` nên ứng dụng có thể thực hiện Lookup, Search hoặc Modify **dưới Bind identity đã truyền**, miễn server cho phép.

Ví dụ kiểm chứng một account chỉ đọc:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public String readLanAsSpecifiedIdentity(
        ContextSource source,
        String approvedPrincipalDn,
        String secret) throws NamingException {

    DirContext ctx = null;
    try {
        ctx = source.getContext(approvedPrincipalDn, secret);

        Attributes attrs = ctx.getAttributes(
                "uid=lan,ou=people",
                new String[] { "cn", "sn" });

        Attribute cn = attrs.get("cn");
        return cn == null ? null : cn.get().toString();
    } finally {
        LdapUtils.closeContext(ctx);
    }
}
~~~

Với `ContextSource.base=dc=example,dc=org`, `"uid=lan,ou=people"` là tên tương đối đúng trong ví dụ. Nếu account không có ACL đọc `cn`, server có thể trả dữ liệu thiếu hoặc ném exception tùy loại quyền và operation. **Không tự nâng quyền** bằng cách thử lại với account admin khi read bị từ chối.

### Thao tác Modify dưới danh tính được phê duyệt

Đối với một workflow quản trị cố định, `DirContext` hỗ trợ:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem changeTitle = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("title", "Senior Developer")
);

// Chỉ gọi khi ctx đang Bind bằng tài khoản được phép,
// và actor HTTP đã được kiểm tra quyền quản trị:
ctx.modifyAttributes(
        "uid=lan,ou=people",
        new ModificationItem[] { changeTitle });
~~~

**Không dùng** đoạn mã ghi này trong một phương thức xác thực người dùng. Nó chỉ cho thấy `DirContext` làm việc theo **quyền LDAP của danh tính đã Bind**. Việc được cấp context “read-write” hoặc truyền principal admin **không làm quy trình trở nên an toàn** nếu API để client tùy chọn target DN hay modifications.

Trong production, một service account **cố định cho chức năng quản trị** với `LdapTemplate` và ACL giới hạn thường dễ quản lý/kiểm toán hơn việc nhận principal/password quản trị tùy ý cho mỗi request.

## 11. Khi chỉ cần xác thực, ưu tiên LdapTemplate.authenticate

Spring LDAP đã cung cấp một luồng **Search entry rồi Bind bằng DN tìm được**, có xử lý context trong framework.

Ví dụ:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

// Kiểm tra password != null && !password.isEmpty() trước.
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(2)
        .timeLimit(2_000)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(validatedUid);

// Trên Spring LDAP hỗ trợ API này, thao tác xác thực
// thất bại sẽ được biểu diễn bằng exception thích hợp.
ldapTemplate.authenticate(query, password);
~~~

Ưu điểm:

- Dùng filter builder và search base chính xác.
- Không tự ghép DN đăng nhập từ chuỗi HTTP.
- Tầng framework thực hiện Bind cho entry tìm được thông qua `ContextSource#getContext(...)`.
- Không buộc service tự quản lý mọi chi tiết đóng context.
- Có overload nhận **`AuthenticatedLdapEntryContextMapper`** để thực hiện operation trên context đã xác thực.

### Thao tác trên context đã được xác thực

Một số môi trường cần thực hiện thêm một thao tác sau khi tạo context. Spring LDAP có overload:

~~~java
ldapTemplate.authenticate(
        query,
        password,
        (ctx, entryIdentification) -> {
            // entryIdentification.getRelativeName() là DN tương đối.
            // Một operation ở đây được thực hiện qua context
            // đã xác thực bằng người dùng, không phải reader template
            // lấy context mới.
            try {
                return ctx.getAttributes(
                    entryIdentification.getRelativeName(),
                    new String[] { "uid" }
                );
            } catch (javax.naming.NamingException error) {
                throw new IllegalStateException(
                        "Authenticated context lookup failed",
                        error);
            }
        }
);
~~~

Trong ví dụ, callback đọc thuộc tính `uid`. Nếu ACL người dùng **không cho đọc `uid`**, callback có thể thất bại dù Bind đúng; cần chọn một operation được phép hoặc một chiến lược authenticate phù hợp với directory. Không dùng operation có tác dụng phụ để “kiểm tra đã đăng nhập”.

Tài liệu Spring LDAP cũng có `LdapClient.authenticate()` với cú pháp fluent; tùy phiên bản, có thể dùng khi không cần ODM. Nếu ứng dụng làm web login thực sự, Spring Security hỗ trợ đầy đủ hơn cho session, quyền truy cập và xử lý người dùng.

### Chọn công cụ theo nhu cầu

| Nhu cầu | Hướng dùng |
| --- | --- |
| Hiểu và thao tác với `DirContext` theo principal cụ thể | `ContextSource.getContext(principal, credentials)`. |
| Xác thực người dùng từ `uid`, tìm DN rồi Bind | `LdapTemplate.authenticate` hoặc `LdapClient.authenticate`. |
| Login web có session/cookies/authorization/CSRF | Spring Security LDAP. |
| Search/CRUD thông thường bằng service account | `LdapTemplate`/Spring Data LDAP repository. |
| Thực hiện operation với identity từ Spring Security | Cấu hình `AuthenticationSource` có kiểm soát, hoặc service chuyên biệt. |

## 12. ContextSource AuthenticationSource: danh tính động có kiểm soát

`AbstractContextSource` hỗ trợ cấu hình `AuthenticationSource`. Khác với một lời gọi `getContext(principal,credentials)` cụ thể, `AuthenticationSource` cho phép cung cấp principal/password cho **mỗi context được tạo** khi đường getReadOnly/getReadWrite cần một authenticated environment.

Theo tài liệu Spring LDAP, có thể sử dụng `SpringSecurityAuthenticationSource` khi muốn context mặc định của một luồng LDAP được tạo bằng danh tính của user đang được Spring Security xác thực.

Nhưng đây là một lựa chọn kiến trúc có nhiều điều kiện:

1. Ứng dụng phải thực sự dùng `LdapAuthenticationProvider` hoặc một cơ chế xác thực bảo đảm principal/credential LDAP đúng kiểu.
2. Nguồn security context phải có credential phù hợp; session/JWT thường **không chứa** mật khẩu LDAP có thể dùng lại để Bind.
3. Không được giữ mật khẩu người dùng trong session hoặc log chỉ để tiện thực hiện các LDAP operation khác.
4. Khi HTTP request chạy bất đồng bộ hoặc scheduler, security context có thể không tồn tại/không được truyền theo cách mong đợi.
5. Connection pool không được tráo context giữa những principal khác nhau.
6. Quyền tại LDAP phụ thuộc ACL thật của tài khoản, không phụ thuộc `@PreAuthorize` riêng lẻ.

**Đừng tự thay userDn/password trên bean singleton** để giả lập `AuthenticationSource`. Nếu cần chuyển danh tính theo mỗi request, thiết kế bean/nguồn xác thực đúng chuẩn, rà soát security boundary và kiểm thử concurrency.

Trong phần lớn ứng dụng CRUD danh bạ, lựa chọn dễ kiểm soát hơn là **service account read-only** cho Search và **service account quản trị giới hạn** cho thao tác ghi, còn Spring Security quản lý quyền của người gọi API ở tầng Java.

## 13. Liên hệ với Spring Data LDAP repository và ODM

Spring Data LDAP cung cấp cách ánh xạ entry thành entity Java:

~~~java
package com.example.directory.model;

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
    private String name;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    // Constructor/getter/setter trong ứng dụng thực tế.
}
~~~

Repository:

~~~java
package com.example.directory.repo;

import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.DirectoryPerson;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

Repository thường dùng `LdapTemplate`/`LdapOperations` được cấu hình khi khởi tạo, rồi lấy context thông qua `ContextSource` của template đó.

**Một lời gọi `contextSource.getContext(userDn, password)` không tự đổi danh tính của repository** đang dùng chung bean `directoryLdapTemplate`. Tương tự, entity `@Entry(base="ou=people")` chỉ mô tả vị trí ánh xạ, **không chỉ định Bind identity**.

### Bảng trách nhiệm

| Thành phần | Quyết định |
| --- | --- |
| `@Entry(base="ou=people")` | Lớp entity nằm ở nhánh nào khi ODM tính DN. |
| `@Id Name dn` | DN của entry Java đang ánh xạ. |
| `LdapTemplate` | Gửi Search/CRUD thông qua ContextSource đã cấu hình. |
| `ContextSource.getContext(userDn,password)` | Tạo **một context riêng** dùng principal/credentials chỉ định. |
| Spring Security | Xác thực/ủy quyền người gọi ứng dụng. |
| LDAP ACL | Thực tế context có thể làm gì trên directory. |

Nếu use case cần repository thao tác theo danh tính người dùng hiện tại, không thể giải quyết chỉ bằng gọi `getContext` một lần bên ngoài rồi gọi repository thông thường. Cần một kiến trúc context/operations được cấu hình cho danh tính đó, có quản lý lifecycle và giới hạn quyền.

## 14. Phân biệt LDAP Bind với CRUD bind của LdapTemplate

Hai API có tên dễ gây nhầm:

| API | Ý nghĩa |
| --- | --- |
| `ContextSource.getContext(principal, credentials)` | Tạo context bằng LDAP **Bind xác thực** với danh tính chỉ định. |
| `LdapTemplate.bind(Name dn, Object obj, Attributes attrs)` | Tạo **entry mới** trong directory (LDAP Add ở ngữ nghĩa sử dụng template). |
| `LdapTemplate.unbind(Name dn)` | **Xóa entry** trong directory, không phải “đăng xuất”. |
| `DirContext.close()` / `LdapUtils.closeContext(ctx)` | Giải phóng context/kết nối đã dùng. |

**Không** dùng `LdapTemplate.unbind(...)` để “logout user”: nó có thể xóa **entry người dùng** nếu account có quyền. Đóng `DirContext` là thao tác vòng đời client; không xóa entry LDAP.

`getReadWriteContext()` cũng không đồng nghĩa người dùng “đã có quyền quản trị”. Chỉ ACL server có thể quyết định thao tác Add/Modify/Delete/Modify DN có được chấp nhận hay không.

## 15. Vòng đời context, pooling và thread safety

### 15.1. Vòng đời chuẩn

~~~text
Lấy ContextSource do Spring quản lý
       |
       v
getContext(principal, credentials)
       |
       v
Dùng DirContext trong phạm vi ngắn
       |
       v
finally { LdapUtils.closeContext(ctx); }
~~~

Các nguyên tắc:

- Lấy context càng gần thao tác thực tế càng tốt.
- Không lưu `DirContext` vào HTTP session hoặc chia sẻ giữa các request.
- Không truyền context sang thread khác mà không kiểm soát chặt lifecycle.
- Đóng context kể cả khi Search/Modify ném `NamingException`.
- Không ghi log object context hoặc JNDI environment; chúng có thể chứa principal/credential.
- Với số lượng login lớn, giới hạn tần suất và connection load; đừng giữ hàng nghìn context chưa đóng.

### 15.2. Pooling và getContext

Theo Javadoc `ContextSource#getContext`, lời gọi này **không sử dụng native Java LDAP pooling**, kể cả khi ContextSource được cấu hình bật, để thay đổi mật khẩu có tác dụng sớm nhất có thể.

Không suy ra rằng **mọi wrapper/pool tùy biến** trên thế giới đều có hành vi giống hệt; khi thêm `PoolingContextSource` hoặc một lớp proxy khác, cần kiểm tra hợp đồng và kiểm thử. Spring LDAP có tài liệu riêng về pooling; không sử dụng lại authenticated context của Lan cho Minh.

### 15.3. getReadOnlyContext có thật sự cấm ghi không?

Tên method biểu diễn **mục đích sử dụng**. Theo `AbstractContextSource`, mặc định hai method read-only và read-write có thể cùng Bind bằng principal đã cấu hình. Vì vậy, **chỉ ACL** mới là cơ chế bảo vệ chắc chắn không cho account reader viết vào directory.

Nếu reader được cấp quyền LDAP Modify nhầm, gọi `getReadOnlyContext()` **không phải biện pháp thay thế ACL** đáng tin cậy.

## 16. Bảo mật thông tin xác thực và kết nối

### 16.1. Không gửi Simple Bind qua plaintext

Mật khẩu người dùng/Bind account phải được truyền qua kênh an toàn:

- `ldaps://ldap.example.org:636` với certificate hợp lệ; hoặc
- StartTLS thành công **trước Simple Bind** trên kết nối được hỗ trợ.

Kiểm tra CA, certificate chain, hostname/SAN và chính sách TLS. Không “sửa” handshake failure bằng tắt xác minh hoặc tự động fallback từ LDAPS sang `ldap://` không mã hóa.

`getContext` không tự biến một URL `ldap://` thành kết nối mã hóa. Kết nối an toàn phải được thiết lập/cấu hình trước khi truyền credential.

### 16.2. Cẩn trọng mật khẩu rỗng

LDAP Simple Bind có các trường hợp đặc biệt liên quan **unauthenticated authentication** hoặc anonymous authentication. Tùy server/cấu hình, một yêu cầu Bind với DN nhưng mật khẩu rỗng có thể không mang nghĩa “kiểm tra tài khoản bằng mật khẩu rỗng” như ứng dụng tưởng.

Do đó:

~~~java
if (password == null || password.isEmpty()) {
    throw new IllegalArgumentException(
            "Non-empty credentials required");
}
~~~

**Không** dùng `password.strip()` hoặc `trim()` trước khi Bind: khoảng trắng có thể là một phần hợp lệ của mật khẩu. Việc chỉ kiểm tra `isEmpty()` không loại mật khẩu chỉ có khoảng trắng; nếu policy muốn cấm loại này, áp chính sách rõ ràng mà không âm thầm sửa chuỗi người dùng nhập.

### 16.3. Không log secret hoặc thông tin dùng cho enumeration

Không log:

- Mật khẩu người dùng.
- `Context.SECURITY_CREDENTIALS` hoặc JNDI environment.
- LDAP Bind DN đầy đủ khi không cần/không được phép.
- Raw exception chứa DN, endpoint hoặc chi tiết chính sách nội bộ vào response HTTP.

Log có thể gồm request ID, operation, trạng thái mã hóa như `AUTH_FAILURE`/`DIRECTORY_UNAVAILABLE`, vùng directory và thời gian, theo chính sách bảo vệ dữ liệu.

### 16.4. Bảo vệ khỏi brute force

Việc nhận username/password và gọi `getContext` thường là một phần của login:

- Thực thi rate limit, throttling và cơ chế phát hiện brute force/password spraying.
- Tôn trọng chính sách khóa tài khoản của directory; không thử nhiều username/mật khẩu với cùng target.
- Không hiển thị khác biệt “tài khoản có tồn tại” so với “mật khẩu sai” cho caller không được phép.
- Đảm bảo credential chỉ được giữ trong phạm vi cần thiết, không cache password.
- Khi dùng Spring Security, áp chính sách session, CSRF và authorization phù hợp với loại client.

### 16.5. Referral và danh tính

Một directory có thể trả referral sang server khác. Không bật auto-follow một cách vô điều kiện khi context có mật khẩu người dùng, vì provider có thể kế thừa môi trường JNDI và chuyển credential tới đích ngoài vùng tin cậy. Ví dụ này đặt `source.setReferral("throw")` để ứng dụng chủ động xử lý; nếu cần nhiều server, cấu hình endpoint/credential riêng và allowlist.

## 17. Nhận diện lỗi đúng tầng

Khi làm việc trực tiếp với `DirContext`, các ngoại lệ JNDI thường thuộc `javax.naming`.

| Lỗi hoặc trường hợp | Biểu hiện thường gặp | Không được kết luận nhầm |
| --- | --- | --- |
| DN/mật khẩu sai | `javax.naming.AuthenticationException`, LDAP 49. | Không tự chia nhỏ username sai/password sai từ message. |
| Context Bind thành công nhưng không đọc được attribute | Attribute bị ẩn hoặc lỗi quyền, có thể LDAP 50. | Không coi là xác thực thất bại. |
| DN không có | `NameNotFoundException`/LDAP 32. | Không đồng nghĩa mật khẩu sai. |
| DN thiếu cú pháp hợp lệ | `InvalidNameException`/LDAP 34 hoặc lỗi parser. | Không retry với admin. |
| Server từ chối kết nối | `CommunicationException` hoặc exception network. | Không bịa LDAP 49 nếu chưa có Bind response. |
| Chứng chỉ TLS sai | SSL/TLS handshake failure. | Không fallback plaintext. |
| Referral không được follow | `ReferralException`/`PartialResultException` tùy operation/provider. | Không xem Search đã đầy đủ. |
| ACL cấm Modify | LDAP `insufficientAccessRights (50)` hoặc exception tương ứng. | Không “nâng quyền” vì method Java tên read-write. |

### JNDI exception khác Spring LDAP exception

Nếu gọi trực tiếp `contextSource.getContext(...)` hoặc `ctx.getAttributes(...)`, bạn chủ yếu xử lý **checked `javax.naming.NamingException`**. Nếu gọi qua `LdapTemplate`/repository, Spring LDAP thường **dịch exception JNDI** thành hierarchy unchecked `org.springframework.ldap.*`.

Ví dụ có hai tên lớp gần giống:

~~~java
javax.naming.AuthenticationException
org.springframework.ldap.AuthenticationException
~~~

**Đừng import nhầm** khi viết `catch` cho lời gọi trực tiếp `getContext`. Với lỗi timeout/server unavailable, ghi nhận trạng thái dịch vụ thay vì trả “sai mật khẩu”; nếu xác thực là một phần API web, phản hồi công khai nên an toàn và nhất quán.

## 18. Thực hành kiểm tra danh tính bằng LDAP CLI

Trước khi viết code, hãy xác minh các Bind DN trên directory **thử nghiệm** bằng LDAP CLI. Những lệnh sau dùng LDAPS với chứng chỉ đã được tin cậy.

### 18.1. Bind bằng reader service account

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-reader,ou=service,dc=example,dc=org" -W
~~~

### 18.2. Bind bằng Lan

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=lan,ou=people,dc=example,dc=org" -W
~~~

`-W` yêu cầu nhập mật khẩu qua prompt, tránh đặt password trên command line. Kết quả thành công thường biểu diễn identity mà server đã xác thực. **Đừng thử liên tục mật khẩu sai** trên hệ thống thực vì có thể kích hoạt khóa tài khoản.

### 18.3. Thử quyền đọc của Lan

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=lan,ou=people,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" -s base \
  "(objectClass=inetOrgPerson)" \
  dn uid cn sn mail
~~~

### 18.4. Thử quyền ghi một cách có kiểm soát

Trong directory test, chuẩn bị một entry fixture riêng và một lệnh Modify dự định sẽ bị từ chối với account reader. Chỉ làm trên dữ liệu có thể khôi phục, sau đó đọc lại entry để chắc chắn không có thay đổi.

**Không** dùng `ldapmodify` thử sửa mật khẩu người dùng thật hay xóa một entry thực tế để “xem quyền hoạt động ra sao”.

### 18.5. Kiểm tra base DN của ContextSource

Nếu `ContextSource.base=dc=example,dc=org`, Spring LDAP có thể dùng `uid=lan,ou=people` khi lookup. Lệnh `ldapsearch` thường dùng DN **đầy đủ** trong `-b`, nên đừng nhầm lệnh CLI với naming context bên trong Java.

## 19. Kiểm thử tích hợp với hai danh tính

Một bài test hữu ích phải chứng minh rằng hai lần `getContext` lấy **hai context độc lập với ACL khác nhau**, không chỉ kiểm tra object khác null.

### Ma trận kiểm thử

| Ca kiểm thử | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Reader Bind đúng | `getContext(readerDn, readerPassword)` | Có context và thao tác đọc được phép. |
| Lan Bind đúng | `getContext(lanFullDn, lanPassword)` | Có context của Lan. |
| Lan Bind sai password | `getContext(lanFullDn, wrongPassword)` | Thất bại xác thực. |
| Mật khẩu rỗng | Kiểm tra input trước lời gọi. | Không gửi Bind xác thực rỗng. |
| DN tương đối gửi làm principal | `getContext("uid=lan,ou=people", password)` | Không dựa vào base tự nối; dùng full DN. |
| DN đầy đủ để lookup trong context có base | `ctx.getAttributes(fullDn)` | Không giả định framework tự cắt base; dùng relative. |
| Reader cố Modify | `ctx.modifyAttributes(...)` | Bị ACL từ chối. |
| Account writer Modify thuộc tính được cấp | Modify `title` trên fixture. | Được phép, không thay DN/thuộc tính khác. |
| Reader cố Modify sau khi writer dùng context riêng | Reader Modify lần nữa. | Vẫn bị từ chối; không lẫn identity. |
| Thiếu entry | Đọc DN không tồn tại. | Phân loại missing entry, không nhầm lỗi Bind. |
| LDAP mất kết nối | Dừng server test. | Lỗi transport, không phải wrong password. |
| TLS chứng chỉ sai | Dùng test CA/host không hợp lệ. | Bind thất bại; không bỏ TLS. |
| Không đủ quyền đọc base | User Bind thành công nhưng lookup base bị từ chối. | Phân biệt xác thực với phân quyền. |
| Referral tới server khác | Cấu hình referral test. | Không tự chuyển secret ngoài policy. |
| Nhiều request song song | Xác thực Lan/Minh đồng thời. | Không lẫn credential; ContextSource bean không bị mutate. |
| Quên close context | Test load/connection metrics. | Phải phát hiện số context/socket tăng. |
| Password đã đổi | Bind lại bằng secret cũ. | Không dựa vào pooled auth context cũ; xác minh theo server policy. |

### Ví dụ JUnit 5: đọc bằng user context

Đây là test **tích hợp** giả định directory fixture và secret test đã có trong environment. Tài khoản Lan phải được LDAP ACL cho phép đọc `cn` của chính entry mình.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

@SpringBootTest
class SelectedIdentityContextIntegrationTest {

    @Autowired
    @Qualifier("directoryContextSource")
    ContextSource contextSource;

    @Value("${test.ldap.lan-password}")
    String testPassword;

    @Test
    void contextUsesSpecifiedUserIdentity() throws Exception {
        DirContext ctx = null;
        try {
            ctx = contextSource.getContext(
                "uid=lan,ou=people,dc=example,dc=org",
                testPassword
            );

            Attributes attrs = ctx.getAttributes(
                "uid=lan,ou=people",
                new String[] {"cn"}
            );

            assertEquals(
                "Nguyen Thi Lan",
                attrs.get("cn").get().toString()
            );
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

Để test **không lẫn danh tính**, hãy Bind riêng reader, Lan và account admin; thực hiện cùng một thao tác Modify trên fixture và so sánh kết quả theo ACL. Đừng dùng mock `ContextSource` để “chứng minh” quyền thật; mock không thực thi LDAP Bind hoặc ACL server.

### Test cần phân biệt lỗi hạ tầng với sai mật khẩu

- Unit test: khi input password rỗng, service **không gọi** `getContext`.
- Integration test: secret sai -> lỗi xác thực dự kiến.
- Fault injection: LDAP server không phản hồi -> lỗi transport/timeout, **không** trả sai mật khẩu.
- Authentication lazy: buộc thực hiện một operation phù hợp hoặc dùng API authenticate với callback để chắc chắn hành vi provider.
- Cleanup: mọi context phải được đóng ở `finally`; test tải có thể quan sát số connection đang mở.

## 20. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách làm đúng |
| --- | --- | --- |
| `setUserDn`/`setPassword` trên singleton cho mỗi request | Rò rỉ/lẫn credential giữa thread. | `getContext(principal, credentials)` hoặc bean/context riêng. |
| Dùng `uid=lan` làm principal dù ContextSource có base | Bind có thể không chọn đúng danh tính. | Dùng DN đầy đủ. |
| Gửi DN đầy đủ cho Lookup có base và mong tự cắt | Nhân đôi base hoặc trỏ sai entry. | Dùng DN tương đối với ContextSource. |
| Không đóng DirContext | Rò rỉ tài nguyên/kết nối. | `LdapUtils.closeContext(ctx)` trong `finally`. |
| Coi `getReadOnlyContext` là ACL chỉ đọc | Reader có thể vẫn có quyền Modify ở server. | Kiểm tra và hạn chế LDAP ACL. |
| Coi context trả về là Bind chắc chắn thành công ở mọi provider | Lazy authentication có thể bị bỏ qua. | Authenticate API với callback hoặc operation kiểm chứng. |
| Xem mọi `NamingException` là mật khẩu sai | Che lỗi mạng, ACL, TLS, referral. | Phân loại exception theo tầng. |
| Cho phép HTTP client chọn full Bind DN tùy ý | Tăng nguy cơ abuse/enumeration, vượt scope policy. | Resolve UID trong OU tin cậy, xác minh uniqueness. |
| Ghép Search filter bằng chuỗi raw input | LDAP injection hoặc Search quá rộng. | `LdapQueryBuilder`/filter builder. |
| Dùng admin account để retry Bind của user | Đảo lộn ranh giới xác thực và cấp quyền. | Fail closed, không fallback credential. |
| Dùng pooling native cho user Bind rồi tin mật khẩu mới có hiệu lực ngay | Có thể dùng lại context sai/không phù hợp. | Theo hợp đồng `getContext` không native pooling; test wrapper. |
| Dùng LDAP Simple Bind qua `ldap://` không mã hóa | Mật khẩu có thể lộ trên mạng. | LDAPS/StartTLS với xác minh certificate. |
| Dùng `LdapTemplate.unbind` để “đăng xuất” | Xóa entry LDAP. | Đóng context, xử lý logout ở web security. |
| Cấp quyền reader ở tầng Java nhưng ACL reader vẫn được ghi | Sai lớp bảo vệ hạ tầng. | Kiểm thử LDAP ACL bằng Bind DN thật. |

## 21. Bài tập mở rộng

**Bài 1 — So sánh ba method.** Với reader account và một user account, ghi lại danh tính Bind của `getReadOnlyContext`, `getReadWriteContext` và `getContext(userDn,password)` bằng cách quan sát `ldapwhoami` và logs test. Giải thích tại sao “read-only” không đồng nghĩa quyền không thể ghi.

**Bài 2 — Tìm DN an toàn.** Viết `UserDnResolver` chỉ tìm trong `ou=people`, dùng `LdapQueryBuilder`, xử lý 0/1/nhiều kết quả và lỗi size limit. Dùng `DirContextOperations.getNameInNamespace()` thay vì tự ghép DN thô từ UID.

**Bài 3 — Đóng context.** Viết unit test/mock bao quanh một operation ném exception để bảo đảm `LdapUtils.closeContext` hoặc `DirContext.close()` vẫn được gọi theo đường cleanup phù hợp.

**Bài 4 — Thử ACL.** Dùng cùng target entry và hai principal reader/admin được cấu hình test. Với reader, Modify phải bị từ chối; với admin được cấp đúng quyền, Modify `title` có thể thành công. Sau đó đọc lại entry để kiểm chứng.

**Bài 5 — Authentication callback.** Dùng overload `LdapTemplate.authenticate(query,password,mapper)` để đọc `uid` trên context đã xác thực, so sánh với lời gọi `getContext` trực tiếp. Thảo luận vì sao callback giúp kiểm chứng hành vi của server có lazy Bind.

**Bài 6 — Spring Security.** Thiết kế luồng đăng nhập dùng LDAP Bind rồi map nhóm `groupOfNames.member` sang authority ứng dụng có allowlist, không lưu mật khẩu LDAP trong session.

**Bài 7 — TLS và pooling.** Cấu hình test server LDAPS và kiểm tra certificate hostname. Sau khi đổi mật khẩu test account, thử xác thực bằng mật khẩu cũ/mới. Đánh giá khác biệt với các wrapper/pool mà ứng dụng thực sự sử dụng.

**Bài 8 — Referral.** Cấu hình một LDAP referral từ test server tới endpoint không thuộc allowlist. Kiểm tra ứng dụng không tự chuyển mật khẩu người dùng sang target đó.

## 22. Câu hỏi tự đánh giá

1. `ContextSource` là factory hay một phiên đăng nhập duy nhất?
2. `getContext(principal, credentials)` khác `getReadOnlyContext()` ở điểm nào?
3. Principal gửi vào `getContext` có cần DN đầy đủ khi ContextSource đã có base không?
4. Vì sao khi context đã gắn base, tên dùng `ctx.getAttributes(...)` thường là DN tương đối?
5. Vì sao không nên gọi `setUserDn/setPassword` trên singleton cho từng HTTP request?
6. `getReadWriteContext` có cho phép bỏ qua ACL LDAP không?
7. Nếu Bind thành công nhưng lookup bị `insufficientAccessRights (50)`, người dùng có xác thực thất bại không?
8. Vì sao `getContext` phải đóng bằng `LdapUtils.closeContext`?
9. `getContext` có mặc định sử dụng native Java LDAP pooling không? Vì sao điều này quan trọng cho thay đổi mật khẩu?
10. Vì sao phải từ chối mật khẩu rỗng trước khi LDAP Simple Bind?
11. Nếu người dùng chỉ biết `uid`, làm thế nào tìm được DN đúng và duy nhất?
12. `LdapQueryBuilder` bảo vệ filter ra sao, khác `LdapNameBuilder` thế nào?
13. Khi nào nên dùng `LdapTemplate.authenticate` thay vì tự ghép Search + `getContext`?
14. Nếu provider trì hoãn xác thực, vì sao context được tạo không luôn đồng nghĩa Bind thành công?
15. `SpringSecurityAuthenticationSource` phù hợp trong điều kiện nào, và vì sao không nên lưu plaintext password trong session?
16. Vì sao repository `save` không tự chuyển sang danh tính được truyền vào một `getContext` độc lập?
17. Tại sao `LdapTemplate.unbind` không được dùng làm “logout LDAP”?
18. Cần test gì để khẳng định reader context không thể Modify entry?
19. Lỗi TLS handshake có nhất thiết là LDAP `invalidCredentials (49)` không?
20. Vì sao referral phải được kiểm soát trước khi quyết định dùng credential nào để theo?

**Ghi nhớ:** `ContextSource.getContext(principal, credentials)` tạo **một `DirContext` dưới danh tính được chỉ định**, thường dùng để xác thực hoặc thực hiện operation có chủ đích theo ACL của tài khoản đó. Hãy truyền **DN đầy đủ** khi Bind, dùng **DN tương đối** cho operation trên context có base, đóng context trong `finally`, không sửa credential của singleton và không nhầm quyền của `DirContext` với quyền người gọi HTTP. Với luồng login, nên ưu tiên API authenticate của Spring LDAP hoặc Spring Security và kiểm thử với directory thật.

### Tài liệu tham khảo

- [Spring LDAP — ContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextSource.html): `getReadOnlyContext`, `getReadWriteContext`, `getContext(principal,credentials)` và pooling.
- [Spring LDAP — User Authentication](https://docs.spring.io/spring-ldap/reference/user-authentication.html): DN đầy đủ khi Bind, đóng context và lưu ý lazy authentication.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `LdapContextSource`, base, `AuthenticationSource` và pooling.
- [Spring LDAP — AbstractContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): credential mặc định, `anonymousReadOnly` và lifecycle.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `authenticate(LdapQuery,password)`, callback, Search/Lookup.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): pooling, vòng đời context và validation.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): authentication, Bind và tích hợp bảo vệ web.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM và kết nối directory.
- [Java SE — DirContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): phương thức getAttributes/modifyAttributes/close.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Search và resultCode LDAP.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): Simple Bind, unauthenticated authentication và TLS.
- [RFC 4514 — LDAP DN String Representation](https://www.rfc-editor.org/rfc/rfc4514): cú pháp/escaping DN.
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515): escaping filter.
