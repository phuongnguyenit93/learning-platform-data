# Giới hạn khi pool dùng chung nhưng danh tính xác thực thay đổi

Trong **SPRING_DATA_LDAP**, ứng dụng Java dùng Spring Data LDAP repository, Spring LDAP ODM và `LdapTemplate` để truy cập directory gồm các entry có DN (*Distinguished Name*), `objectClass` và schema. Một kết nối LDAP sau khi Bind đã gắn với **danh tính xác thực** cụ thể. LDAP server áp dụng ACL (*Access Control List*) theo danh tính đó cho các thao tác đọc, tìm kiếm và sửa entry.

Connection pool tái sử dụng `DirContext` để giảm chi phí TCP, TLS và Bind. Điều này rất hiệu quả khi mọi thao tác trong pool dùng **cùng một service account**. Nhưng nếu ứng dụng dùng một `AuthenticationSource` lấy principal/password theo người dùng hiện tại rồi đưa `ContextSource` đó vào một pool dùng chung, một vấn đề bảo mật nghiêm trọng xuất hiện: **pool có thể trả lại context đã Bind bằng credential của người trước cho request của người sau**.

Ví dụ, Lan chỉ được đọc nhánh `ou=employees`, còn Bình chỉ được đọc `ou=partners`. Lan mượn context, thực hiện query và trả về pool. Request của Bình tiếp tục mượn context đó. Nếu context vẫn được Bind dưới danh tính Lan, LDAP server tiếp tục áp dụng ACL của Lan dù request hiện tại thuộc Bình. Tùy quyền của hai tài khoản, Bình có thể bị từ chối dữ liệu hợp lệ hoặc đọc nhầm dữ liệu mà Lan được phép xem.

Bài học này phân tích giới hạn của pool khi danh tính thay đổi, cách Spring LDAP lấy credential, khác biệt giữa `getReadOnlyContext()`/`getReadWriteContext()` và `getContext(principal, credentials)`, cách thiết kế pool cho service account cố định, xác thực Bind riêng cho từng user và các kiểm thử chống rò rỉ danh tính.

Sau bài này, bạn có thể:

- Giải thích vì sao một LDAP connection đã Bind không tự đổi principal theo HTTP request.
- Hiểu `AuthenticationSource` được hỏi khi tạo context, không phải trước mỗi thao tác LDAP.
- Nhận biết pool chuẩn của Spring LDAP phân biệt context read-only/read-write, **không phân vùng theo user DN/password**.
- Phát hiện nguy cơ khi kết hợp `AuthenticationSource` động với `PoolingContextSource`/`PooledContextSource` dùng chung.
- Chọn mô hình service-account pool hoặc per-user Bind không dùng chung context.
- Quản lý password rotation, session, pool lifecycle, TLS và quyền tối thiểu.
- Viết integration test chứng minh hai người dùng không bao giờ nhận context của nhau.

## 1. Một DirContext thuộc về danh tính đã Bind

Trong LDAP, client thường tạo một kết nối rồi thực hiện Bind. Sau khi Bind thành công, các operation tiếp theo trên context đó được server thực hiện dưới **authentication identity** của kết nối.

```text
HTTP request của Lan
       |
       v
LdapContextSource tạo DirContext
       |
       | Bind: uid=lan,ou=people,...
       v
LDAP server xác thực Lan
       |
       v
DirContext A gắn với danh tính Lan
       |
       +-- Search ou=employees -> ACL của Lan
       |
       +-- close() -> nếu là pooled wrapper, trả context về pool
```

`close()` trên một context được Spring LDAP pool bọc thường có nghĩa **trả context về pool**. Kết nối bên dưới có thể vẫn mở và vẫn giữ trạng thái Bind của Lan. Việc một request khác lấy lại wrapper không tự động thực hiện Bind lại bằng danh tính của request mới.

Một context không phải đối tượng stateless có thể tùy ý chia sẻ giữa người dùng. Nó giữ trạng thái kết nối, danh tính đã xác thực và có thể cả trạng thái LDAP control/session. **Danh tính Bind là một phần của trạng thái kết nối.**

## 2. Hai loại ContextSource method có mục đích khác nhau

Spring LDAP định nghĩa `ContextSource` với ba method quan trọng:

| Method | Mục đích | Credential |
|---|---|---|
| `getReadOnlyContext()` | Lấy context để thực hiện thao tác đọc | Theo cấu hình mặc định hoặc `AuthenticationSource` của ContextSource |
| `getReadWriteContext()` | Lấy context để thực hiện thao tác ghi | Theo cấu hình mặc định hoặc `AuthenticationSource` của ContextSource |
| `getContext(principal, credentials)` | Tạo context được Bind bằng principal/password cụ thể | Do caller truyền trực tiếp |

Hai method đầu thường được `LdapTemplate` sử dụng. Khi được bọc bởi pool, chúng đi qua các nhóm context được quản lý để tái sử dụng.

Method thứ ba là một luồng **xác thực theo danh tính cụ thể**. Spring LDAP dùng nó để tạo context được xác thực bằng principal/password được truyền trực tiếp, ví dụ xác minh password của người dùng. Đây là đường riêng với việc mượn context read-only/write từ pool. Javadoc `ContextSource` nêu method này không dùng native Java LDAP pooling, nhằm bảo đảm password đã thay đổi có hiệu lực đối với lần xác thực mới.

Khi cần Bind theo từng user, hãy coi đây là một thao tác tạo context riêng và đóng context sau khi dùng; không nhầm nó với việc mượn context read-only/write từ pool.

### 2.1. AuthenticationSource cung cấp credential khi nào?

Nếu `ContextSource` được cấu hình bằng `userDn` và `password`, principal/credential đó được dùng khi tạo context. Nếu cấu hình `AuthenticationSource`, Spring LDAP gọi source để lấy principal và password **mỗi khi cần tạo một context mới**.

Điều đó không có nghĩa `AuthenticationSource` được gọi cho mọi query. Khi pool đã có một context idle, pool có thể trả context đó mà không tạo connection mới. Vì vậy:

```text
Request A:
  AuthenticationSource -> principal A / password A
  Tạo context A, Bind thành công
  close() -> context A trở thành idle

Request B:
  AuthenticationSource không nhất thiết được gọi
  Pool trả context A đang idle
  Operation của B vẫn chạy dưới Bind identity A
```

Đây là nguồn gốc của lỗi khi danh tính xác thực thay đổi theo request.

## 3. Pool Spring LDAP không phải pool theo từng người dùng

Spring LDAP Pool2 dùng Apache Commons Pool 2. `PooledContextSource` lấy context từ keyed object pool. Trong implementation chuẩn, khóa phân loại context là `DirContextType` — hai loại chính là **READ_ONLY** và **READ_WRITE**.

```text
Shared PooledContextSource
          |
          +-- Key: READ_ONLY
          |      [context 1] [context 2] [context 3]
          |
          +-- Key: READ_WRITE
                 [context 4] [context 5]
```

Pool key không bao gồm:

- DN của người dùng đang đăng nhập.
- Password người dùng.
- Tenant/user identity trong `SecurityContext`.
- Principal hiện tại trong `ThreadLocal`.
- Phiên đăng nhập HTTP đang gọi `LdapTemplate`.

Do đó, `maxTotalPerKey` giới hạn số context theo loại key của pool, **không** tạo giới hạn độc lập cho từng user.

### 3.1. Vấn đề đã được Spring LDAP ghi nhận

Tài liệu Spring LDAP có mục **Custom Authentication** cảnh báo rằng `PoolingContextSource` giả định mọi context lấy từ `getReadOnlyContext()` có cùng environment; tương tự với `getReadWriteContext()`. Khi bọc một `LdapContextSource` dùng `AuthenticationSource` động, pool có thể được tạo bằng credential của người đầu tiên. Nếu không cần tạo connection mới, những request sau có thể nhận context mang credential của người đó thay vì credential hiện tại.

Nếu pool phải mở rộng trong lúc request của user khác đang chạy, context mới có thể được tạo dưới principal hiện tại ở thời điểm tạo. Khi đó cùng một pool key còn có thể chứa **nhiều context mang nhiều identity khác nhau**. Dù pool chứa một identity hay nhiều identity trộn lẫn, nó vẫn không có quy tắc bảo đảm request của Lan chỉ nhận context Lan và request của Bình chỉ nhận context Bình.

Pool2 cũng phải được xem xét theo cùng nguyên tắc: `PooledContextSource` mượn context theo `DirContextType` và không cung cấp pool key theo từng principal. Đổi từ pool cũ sang Pool2 **không tự biến pool thành pool đa danh tính**.

Không nhầm Spring LDAP Pool2 với **native JNDI pooling**. Native pooling là cơ chế riêng của JDK LDAP provider; tài liệu `AbstractContextSource` ghi nhận cơ chế này phân pool theo user DN và có nhiều giới hạn hơn. `ContextSource.getContext(principal, credentials)` được thiết kế để không dùng native JNDI pooling, giúp password vừa đổi có hiệu lực ở lần Bind mới. Điều đó **không** biến `PooledContextSource` thành pool theo user: hai cơ chế có key và vòng đời khác nhau.

### 3.2. Ví dụ lỗi với AuthenticationSource động

Giả sử source trả principal/password theo người dùng hiện tại:

```java
import org.springframework.ldap.core.support.AuthenticationSource;

public final class CurrentUserAuthenticationSource
        implements AuthenticationSource {

    @Override
    public String getPrincipal() {
        // Đọc DN của người đang đăng nhập từ SecurityContext.
        return CurrentRequestIdentity.userDn();
    }

    @Override
    public String getCredentials() {
        // Ví dụ minh họa: credential được lưu trong request context.
        return CurrentRequestIdentity.password();
    }
}
```

`CurrentRequestIdentity` ở đây là một abstraction minh họa do ứng dụng định nghĩa. Không nên tự tạo static mutable field chứa password hoặc dùng một `ThreadLocal` tự quản lý mà không xử lý async, executor và cleanup.

Nếu gắn source đó vào một `LdapContextSource` rồi bọc pool:

```java
LdapContextSource target = new LdapContextSource();
target.setUrl("ldaps://ldap.example.org:636");
target.setBase("dc=example,dc=org");
target.setAuthenticationSource(currentUserAuthenticationSource);

// ANTI-PATTERN: context được pool theo READ_ONLY/READ_WRITE,
// không theo principal hiện tại.
PoolConfig config = new PoolConfig();
PooledContextSource pool = new PooledContextSource(target, config);
```

Code trên chỉ minh họa **cấu hình nguy hiểm**. Không dùng nó cho ứng dụng có quyền theo từng người dùng. Nếu pool được tạo khi Lan là người đầu tiên cần context, connection được tạo có thể Bind dưới danh tính Lan. Khi Bình mượn lại context đó, ACL phía LDAP vẫn thấy Lan.

## 4. Minh họa lỗi rò rỉ identity

Giả sử directory có hai nhánh và ACL:

```text
dc=example,dc=org
├── ou=employees
│   └── uid=lan
└── ou=partners
    └── uid=binh

ACL:
  Lan  -> chỉ đọc ou=employees
  Binh -> chỉ đọc ou=partners
```

Luồng lỗi:

```text
1. Lan gọi GET /employees
   -> pool tạo context, Bind as Lan
   -> query thành công
   -> close(), context trở về idle

2. Binh gọi GET /partners
   -> pool trả context idle của Lan
   -> query chạy dưới ACL của Lan
   -> Binh có thể nhận lỗi hoặc kết quả ngoài dự kiến
```

Trong một hệ thống có ACL rộng hơn, hậu quả có thể là **đọc dữ liệu ngoài phạm vi của user hiện tại**. Không phải mọi trường hợp đều hiển thị ngay một lỗi rõ ràng. Nếu Lan có quyền rộng hơn Bình, request của Bình có thể vô tình sử dụng quyền của Lan.

### 4.1. Vì sao testOnBorrow không sửa được lỗi?

Validation của pool thường gửi một LDAP search nhỏ để kiểm tra context còn hoạt động. Nó kiểm tra **khả năng giao tiếp**, không kiểm tra context có đang Bind đúng principal mong muốn hay không.

```text
Borrow context
     |
     v
testOnBorrow:
  Search objectClass=*
     |
     v
Search thành công
     |
     v
Pool trả context đã Bind dưới danh tính cũ
```

Nếu tài khoản cũ vẫn được phép thực hiện probe, validation sẽ thành công. Vì vậy:

- `testOnBorrow` không đổi principal.
- `testOnReturn` không đổi principal.
- `testWhileIdle` không đổi principal.
- `DefaultDirContextValidator` không xác nhận context thuộc user hiện tại.

**Validation không phải cơ chế phân tách danh tính.** Muốn kiểm soát identity, phải thiết kế đúng ranh giới pool/context ngay từ đầu.

## 5. Mô hình phù hợp: pool dùng một service account cố định

Với phần lớn ứng dụng web, mô hình đơn giản và dễ kiểm soát nhất là:

1. Spring Security xác thực người dùng bằng LDAP Bind hoặc identity provider.
2. Ứng dụng lấy các quyền của người dùng.
3. Các thao tác nghiệp vụ với directory dùng một **service account cố định** có quyền tối thiểu.
4. `LdapTemplate` sử dụng pool được Bind bằng service account đó.
5. Tầng service kiểm tra quyền của người dùng trước khi gọi thao tác LDAP.

```text
User Lan / Binh
       |
       v
Spring Security: xác thực và phân quyền
       |
       v
Business Service: kiểm tra PEOPLE_READ / PEOPLE_EDIT
       |
       v
LdapTemplate
       |
       v
PooledContextSource (một service identity cố định)
       |
       v
LDAP server: ACL của service account
```

Ưu điểm:

- Context trong pool luôn có cùng danh tính Bind.
- Pool có thể tái sử dụng connection an toàn giữa các request nghiệp vụ.
- Không cần giữ password người dùng sau khi xác thực.
- Có thể cấp service account quyền đọc/ghi tối thiểu theo từng OU/attribute.
- Có thể theo dõi pool, giới hạn concurrency và rotate credential theo một quy trình tập trung.

Điểm cần hiểu: LDAP server nhìn thấy **service account** khi ứng dụng thao tác. Nó không tự nhìn thấy Lan hoặc Bình chỉ vì HTTP request thuộc người dùng đó. Nếu cần audit theo người dùng, ứng dụng phải ghi nhận actor identity ở tầng nghiệp vụ; nếu cần LDAP server thực thi ACL theo user, phải chọn một mô hình delegation/Bind riêng.

### 5.1. Cấu hình ContextSource cho service account

Ví dụ Spring LDAP Pool2, Java 17+:

**`ServiceLdapConfiguration.java`**

```java
package com.example.ldap;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class ServiceLdapConfiguration {

    @Bean("serviceTargetContextSource")
    LdapContextSource serviceTargetContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.service-dn}") String serviceDn,
            @Value("${app.ldap.service-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(serviceDn);
        source.setPassword(password);

        // Spring Pool2 quản lý pool; không bật thêm native JNDI pooling.
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "3000",
                "com.sun.jndi.ldap.read.timeout", "5000"));
        return source;
    }

    @Bean("servicePooledContextSource")
    PooledContextSource servicePooledContextSource(
            @Value("${app.ldap.pool.max-total}") int maxTotal,
            @Qualifier("serviceTargetContextSource")
            LdapContextSource serviceTargetContextSource) {

        PoolConfig config = new PoolConfig();
        config.setMaxTotal(maxTotal);
        config.setMaxTotalPerKey(16);
        config.setMaxIdlePerKey(8);
        config.setMinIdlePerKey(0);
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(800);
        config.setTestOnBorrow(true);
        config.setTestOnReturn(false);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(60_000);
        config.setNumTestsPerEvictionRun(3);

        PooledContextSource pooled =
                new PooledContextSource(serviceTargetContextSource, config);
        pooled.setDirContextValidator(new DefaultDirContextValidator());
        return pooled;
    }

    @Bean("serviceLdapTemplate")
    LdapTemplate serviceLdapTemplate(
            PooledContextSource servicePooledContextSource) {
        return new LdapTemplate(servicePooledContextSource);
    }
}
```

`PoolConfig` và constructor `PooledContextSource(ContextSource, PoolConfig)` thuộc Spring LDAP Pool2. Giá trị giới hạn trong ví dụ chỉ là điểm bắt đầu để thử nghiệm, không phải con số mặc định phù hợp cho mọi server.

**`application.yml` — tham chiếu secret**

```yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    service-dn: cn=directory-service,ou=service,dc=example,dc=org
    service-password: ${LDAP_SERVICE_PASSWORD}
    pool:
      max-total: 32
```

Secret cần được cấp qua môi trường runtime/secret manager. Không ghi password service account vào Git, log, exception hoặc JMX metadata.

### 5.2. Vì sao pool này an toàn hơn?

Tất cả context được tạo từ `serviceTargetContextSource` dùng cùng:

- LDAP endpoint và base DN.
- Bind DN của service account.
- Credential của service account.
- Authentication mechanism và TLS policy.

Request của Lan và Bình có thể mượn các context khác nhau hoặc cùng một context ở hai thời điểm, nhưng danh tính Bind ở tầng LDAP luôn là **service account cố định**. Việc phân quyền theo Lan/Bình phải được thực hiện trước khi gọi `LdapTemplate`.

Ví dụ service:

```java
public PersonCard getPerson(
        CurrentApplicationUser currentUser, String uid) {

    authorization.requireAuthority(currentUser, "PEOPLE_READ");

    // Query chạy dưới service account của serviceLdapTemplate.
    return personDirectory.findByUid(uid);
}
```

`CurrentApplicationUser` và `authorization` là abstraction nghiệp vụ của ứng dụng. Kiểm tra quyền phải còn bao gồm tenant, ownership hoặc phạm vi OU nếu đó là điều kiện bảo mật. Không nên chỉ kiểm tra role tổng quát rồi cho service account đọc mọi entry mà caller có thể đoán DN.

## 6. Xác thực từng user bằng Bind riêng, không tái sử dụng context giữa user

Đường Bind theo credential cụ thể dùng `ContextSource.getContext(principal, credentials)`; method này tạo context được xác thực bằng principal/password được truyền trực tiếp.

`ContextSource.getContext(principal, credentials)` là API cấp thấp mà Spring LDAP dùng cho Bind cụ thể. Nếu tự gọi trực tiếp, `principal` thường phải là **DN đầy đủ**, bất kể `ContextSource.base`; ứng dụng cần tự tìm DN trước và luôn đóng context.

Một lưu ý quan trọng: một số server/cơ chế xác thực chỉ hoàn tất việc xác thực sau khi có operation trên context. Với luồng đăng nhập ứng dụng, Spring LDAP khuyến nghị dùng `LdapClient.authenticate()` thay vì tự viết một hàm Bind thấp cấp.

### 6.1. Dùng LdapClient.authenticate()

`LdapClient.authenticate()` (có từ Spring LDAP 3.1) tìm entry theo `LdapQuery`, sau đó dùng DN tìm được và password người dùng để thực hiện Bind. Ví dụ này dùng raw `serviceTargetContextSource` có service account cố định để tìm user; bean đó không phải pooled wrapper:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapClient;

@Bean("userAuthenticationLdapClient")
LdapClient userAuthenticationLdapClient(
        @Qualifier("serviceTargetContextSource")
        ContextSource serviceTargetContextSource) {
    return LdapClient.create(serviceTargetContextSource);
}
```

Service xác thực:

```java
import org.springframework.ldap.core.LdapClient;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectoryLoginService {
    private final LdapClient ldapClient;

    public DirectoryLoginService(LdapClient ldapClient) {
        this.ldapClient = ldapClient;
    }

    public void verifyPassword(String uid, String password) {
        ldapClient.authenticate()
                .query(query()
                        .base("ou=people")
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid))
                .password(password)
                .execute();
    }
}
```

`execute()` hoàn tất khi xác thực thành công; nếu password sai, user không tồn tại hoặc truy vấn không trả đúng một entry, API ném lỗi. `uid` phải duy nhất trong search base. Filter được xây bằng `LdapQueryBuilder`, không nối chuỗi từ input.

Luồng này phân biệt rõ hai identity: service account dùng để **tìm DN**, còn Bind kiểm tra password của **user cuối**. Context Bind theo user chỉ tồn tại trong quá trình xác thực; nó không được đưa vào pool nghiệp vụ. Nếu ứng dụng cần thực hiện thao tác LDAP dưới quyền end-user sau login, đó là một thiết kế delegation/per-user context riêng, không phải hệ quả tự động của authentication.

`LdapClient.authenticate()` quản lý vòng đời context trong quá trình xác thực; không giữ context user trong session HTTP hoặc cache để dùng lại cho các request tương lai.

### 6.2. Spring Security LDAP Bind Authentication

Với ứng dụng Spring Security, thường nên dùng `LdapBindAuthenticationManagerFactory`/cấu hình LDAP authentication thay vì tự viết luồng so sánh password. Cơ chế Bind cho phép LDAP server xác minh password. Các context dùng để Bind từng user là **đường xác thực theo credential cụ thể**; không biến pool service account thành pool chứa context của mọi người dùng.

Sau khi đăng nhập thành công, ứng dụng thường không cần giữ lại password LDAP của user. Spring Security có thể xóa credential khỏi `Authentication` sau quá trình xác thực. Vì vậy, không giả định có thể lấy lại password từ `SecurityContextHolder` để dùng cho mọi LDAP operation sau đăng nhập.

## 7. AuthenticationSource và SpringSecurityAuthenticationSource

Spring LDAP có `AuthenticationSource` để cung cấp principal/password động. Spring Security còn có `SpringSecurityAuthenticationSource` để đọc identity từ authentication hiện tại.

Các source này hữu ích khi **mỗi lần tạo context mới** cần dùng credential của user hiện tại. Nhưng có hai giới hạn:

1. Pool có thể trả một context đã tạo trước đó, nên source không được hỏi lại.
2. Credential trong Spring Security authentication có thể đã bị xóa sau khi login; không nên lưu password plaintext lâu dài chỉ để tạo context sau này.

### 7.1. Khi nào có thể dùng AuthenticationSource?

Có thể cân nhắc khi:

- Không dùng pool cho các context gắn với user identity.
- Mỗi operation tạo context mới từ credential hiện có và đóng ngay sau operation.
- Có cơ chế bảo vệ credential rõ ràng, không lưu password lâu hơn cần thiết.
- Luồng chạy đồng bộ/async có context propagation được kiểm soát.
- Tài liệu và test chứng minh mọi context mới đều được tạo bằng identity đúng.

Không dùng source động làm bằng chứng rằng một pool dùng chung sẽ tự tách context theo user. Nếu một ứng dụng cần truy vấn LDAP với quyền end-user, hãy thiết kế per-user context lifecycle rõ ràng hoặc sử dụng cơ chế delegation/authorization của LDAP server nếu được hỗ trợ.

### 7.2. ThreadLocal không tạo pool key

Một triển khai `AuthenticationSource` có thể đọc principal từ `SecurityContextHolder` hoặc `ThreadLocal`. Cách này không thay đổi key của pool:

```text
Thread 1: SecurityContext = Lan
Thread 2: SecurityContext = Binh

Pool:
  READ_ONLY -> context A (Bind as Lan)

Thread 1 borrow -> A
Thread 1 return -> A idle
Thread 2 borrow -> A

ThreadLocal của Thread 2 = Binh
Nhưng DirContext A vẫn Bind as Lan.
```

Trong tác vụ async, scheduled job hoặc executor, `SecurityContext` còn có thể không được truyền tự động. Vì vậy, không dùng thread-local credential làm cơ chế phân tách bảo mật cho một pool context có vòng đời dài.

## 8. Có thể tạo pool riêng cho từng danh tính không?

Về mặt kiến trúc, có thể tạo một pool riêng cho **mỗi identity cố định hoặc mỗi tenant có số lượng giới hạn**, nhưng phải cân nhắc vòng đời credential và quy mô. Ví dụ:

```text
Service account pool:
  service-read  -> pool A
  service-write -> pool B

Tenant pools (số lượng tenant hữu hạn):
  tenant-1 -> pool T1 (credential cố định)
  tenant-2 -> pool T2 (credential cố định)
  tenant-3 -> pool T3 (credential cố định)
```

Mỗi pool có `ContextSource`/`PooledContextSource` riêng và credential không đổi trong suốt vòng đời pool. Cách này có thể phù hợp với một số multi-tenant system có tenant count được kiểm soát.

**Không tạo một pool không giới hạn cho từng user cuối.** Nếu có 20.000 người dùng và mỗi người có pool riêng, chi phí socket, thread eviction, JMX, memory, idle connections và quản lý secret có thể vượt khả năng directory và ứng dụng.

### 8.1. Không đưa password thô vào pool key

Một ý tưởng có vẻ hợp lý là custom pool key:

```text
key = principal + ":" + password
```

Không làm như vậy:

- Password trở thành dữ liệu key, có thể lộ qua debug, dump, log hoặc heap inspection.
- Mỗi lần user đổi password sẽ tạo key mới; pool cũ vẫn giữ context đã Bind bằng password cũ.
- Không có quy trình rõ ràng để hủy mọi context của key cũ khi credential bị thu hồi.
- Nhiều key theo từng credential có thể gây tăng cardinality và cạn tài nguyên.
- Hai password khác nhau của cùng principal không nhất thiết cần hai pool tồn tại lâu dài; một lần Bind mới là cách xác thực đơn giản hơn.

Nếu một hệ thống thực sự cần pool theo identity, phải thiết kế key bằng **identity/version không chứa secret**, cơ chế invalidation khi credential thay đổi, quota per identity, TTL và quy trình drain/destroy. Đây là custom pooling architecture, không phải tính năng tự động của `PooledContextSource`.

### 8.2. Tách pool theo role không giống tách theo user

Pool có thể có context read-only và read-write riêng. Nhưng đó là **loại context**, không phải user role của Spring Security:

| Khái niệm | Ý nghĩa |
|---|---|
| Pool key `READ_ONLY` | Context được dùng cho operation đọc |
| Pool key `READ_WRITE` | Context được dùng cho operation ghi |
| LDAP Bind identity | Account mà LDAP server xác thực |
| Application authority | Quyền của user trong Spring Security |
| LDAP ACL | Quyền server cho phép Bind identity thực hiện |

Không giả định `READ_WRITE` đồng nghĩa với quyền admin, hoặc `READ_ONLY` đồng nghĩa với user cuối chỉ có quyền đọc. ACL phía LDAP server mới quyết định identity đã Bind được phép làm gì.

## 9. Password rotation và context cũ

Khi password của một account thay đổi, những context đã Bind trước đó có thể vẫn đang tồn tại. Pool không tự động đổi password bên trong connection.

Ví dụ service account:

```text
T0: pool tạo 10 context bằng service password V1
T1: secret manager đổi password sang V2
T2: source/configuration được cập nhật
T3: 10 context cũ vẫn đang được giữ hoặc đang active
T4: context mới tạo có thể dùng V2; context cũ vẫn là kết nối cũ
```

Hành động cần thiết tùy server và cơ chế Bind, nhưng một quy trình an toàn thường gồm:

1. Cấp password mới và cập nhật secret runtime.
2. Khởi tạo ContextSource/pool mới hoặc cập nhật theo cơ chế được hỗ trợ.
3. Ngừng cho request mới mượn pool cũ.
4. Chờ/drain context active trong giới hạn thời gian.
5. Hủy context idle cũ và gọi `destroy()` cho pool cũ.
6. Xác minh connection mới Bind thành công bằng credential mới.
7. Thu hồi password cũ theo quy trình directory.

Không chỉ ghi đè biến môi trường rồi giả định context idle đã dùng password mới. Tương tự, một user bị khóa hoặc đổi password không có nghĩa mọi connection đã Bind từ trước lập tức bị hủy trên mọi LDAP server.

### 9.1. Password user cuối thay đổi

Với Bind riêng cho từng lần xác thực, lần gọi `getContext(userDn, newPassword)` tiếp theo thực hiện Bind bằng password mới và không tái sử dụng context của lần trước. Đây là một lý do Spring LDAP mô tả overload `getContext(principal, credentials)` là luồng không dùng native Java LDAP pooling.

Không giữ context user cuối trong pool để giảm một Bind. Lợi ích hiệu năng đó phải được so sánh với rủi ro credential stale, quyền bị thu hồi và việc dùng nhầm identity.

## 10. Validator không thay thế identity isolation

`DefaultDirContextValidator` thường kiểm tra một LDAP search nhỏ để xác nhận context còn phản hồi. Nó không được thiết kế để xác nhận context đang thuộc về user hiện tại.

| Kiểm tra | Có trả lời được không? |
|---|---|
| Socket/LDAP context còn hoạt động? | Có thể, qua validation query |
| LDAP server còn phản hồi? | Có thể |
| Context có thể search một entry mà Bind identity được phép đọc? | Có thể |
| Context đang Bind đúng Lan hay Bình? | **Không mặc định** |
| User hiện tại có quyền đọc entry đích? | Phải kiểm tra ACL/authorization cho operation đích |
| Password của user hiện tại còn hợp lệ? | Không, nếu đang dùng context đã Bind trước đó |

Nếu custom validator cố xác minh danh tính bằng truy vấn đặc biệt, nó vẫn cần biết **expected principal của lần borrow hiện tại** và pool key phải bảo đảm context được mượn theo principal đó. Chỉ thêm một query vào validator không sửa được pool key sai.

## 11. Kiểm thử chống dùng nhầm danh tính

Một unit test chỉ kiểm tra số lượng context active/idle không đủ. Hãy tạo directory test có hai user và ACL khác nhau:

```text
uid=lan,ou=people,dc=example,dc=org
uid=binh,ou=people,dc=example,dc=org

Lan:
  được đọc ou=employees
  không được đọc ou=partners

Binh:
  được đọc ou=partners
  không được đọc ou=employees
```

### 11.1. Test sequential reuse

Kịch bản bắt buộc:

1. Request Lan lấy context và đọc entry thuộc `ou=employees`.
2. Đóng context để pool nhận lại.
3. Request Bình lấy context tiếp theo.
4. Xác minh operation của Bình phản ánh ACL của Bình, không phải ACL của Lan.
5. Lặp lại theo thứ tự ngược: Bình trước, Lan sau.

Nếu pool dùng chung dynamic identity và có lỗi, test có thể phát hiện bằng cách:

- Bình đọc được entry chỉ Lan có quyền đọc.
- Bình bị từ chối entry thuộc quyền của chính Bình vì context vẫn mang identity Lan.
- Audit log của LDAP server cho thấy operation được thực hiện dưới principal không đúng.

### 11.2. Test concurrent reuse

Khi chạy đồng thời, cần kiểm tra:

- Nhiều request của Lan và Bình xen kẽ.
- Một request giữ context lâu trong khi request khác mượn context khác.
- Context trả về pool sau exception.
- Một user logout trong khi request khác vẫn đang chạy.
- Một request async không có SecurityContext như request HTTP ban đầu.

Kiểm thử concurrency cần lặp lại đủ nhiều và sử dụng ACL thực; không dựa vào một lần test thành công để khẳng định isolation.

### 11.3. Ma trận test

| Tình huống | Kết quả mong đợi |
|---|---|
| Shared pool, một service identity cố định | Nhiều request có thể tái sử dụng context; LDAP audit luôn thấy service DN |
| AuthenticationSource động + pool chung | Bị cấm trong thiết kế; integration test phải phát hiện context reuse sai principal |
| Lan bind riêng, đóng context, Bình bind riêng | Bình được xác thực bằng credential của Bình |
| Sai password của Bình | Bind thất bại; không mượn context của Lan |
| Password Bình vừa đổi | Bind mới bằng password cũ thất bại, password mới thành công |
| Service password rotation | Pool mới dùng secret mới; pool cũ được drain/destroy |
| testOnBorrow bật | Chỉ chứng minh context qua validation; không thay test identity |
| ThreadLocal thay đổi giữa request | Không làm thay đổi principal của context đã được pool tạo |
| Pool read-only và read-write | Mỗi pool type vẫn phải dùng identity đã được thiết kế rõ |
| Pool cạn khi nhiều request | Chờ/fail theo max wait; không mượn context của user khác để giải quyết |
| User bị khóa sau khi context được Bind | Test hành vi server và policy đóng/revoke context; không giả định mọi connection tự mất hiệu lực |
| User A và B cùng có uid ở hai tenant | Identity phải gắn đúng directory/tenant, không chỉ so sánh uid |

## 12. Quan sát pool và identity

Với Spring LDAP Pool2, có thể theo dõi:

- `getNumActive()`, `getNumIdle()` và `getNumWaiters()`.
- Active/idle theo loại read-only và read-write.
- Thời gian chờ borrow, thời gian tạo connection, TLS handshake và Bind.
- Tỷ lệ Bind thất bại, connection invalidation, LDAP operation bị ACL từ chối.
- Số lần pool bị drain/destroy khi rotate service credential.

Không đưa full user DN, password, token hoặc session ID vào metric tags. Các tag có cardinality cao và dữ liệu nhạy cảm khiến monitoring trở thành một nguồn rò rỉ.

Một log an toàn có thể dùng:

```text
event=ldap_context_borrow
pool=service-directory
context_type=READ_ONLY
outcome=success
principal_class=SERVICE_ACCOUNT
request_id=...
```

`principal_class` ở đây là nhãn do ứng dụng định nghĩa, không phải DN thật. Với per-user bind, có thể log một mã định danh đã được kiểm soát hoặc pseudonymous subject ID nếu chính sách audit cho phép.

**Audit hai tầng:** LDAP server thường thấy service account trong mô hình shared pool; ứng dụng cần ghi lại actor user và quyết định authorization tương ứng. Nếu yêu cầu kiểm toán đòi LDAP server thấy danh tính end-user, mô hình service account không đáp ứng một mình; cần delegation/Bind theo user được server hỗ trợ và được thiết kế riêng.

## 13. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Hướng xử lý |
|---|---|---|
| Một pool chung với AuthenticationSource đọc user hiện tại | Context của user trước được trả cho user sau | Pool chỉ dùng một service identity cố định |
| Lưu password user trong ThreadLocal lâu dài | Rò credential, lỗi async/cleanup | Bind theo request cần thiết, đóng context ngay |
| Bật testOnBorrow để sửa identity mismatch | Validator chỉ kiểm tra connectivity | Sửa pool/context lifecycle và identity boundary |
| Dùng pool READ_WRITE cho user admin, READ_ONLY cho user thường | Nhầm loại context với role | ACL + app authorization; identity pool rõ ràng |
| Đưa password vào pool key | Lộ secret, cardinality lớn, rotation khó | Không dùng password thô làm key |
| Một pool cho tất cả tenant nhưng mỗi tenant có credential khác | Context có thể bị tái sử dụng sai tenant | ContextSource/pool riêng cho tenant hữu hạn hoặc Bind riêng |
| Giữ context user trong HTTP session | Kết nối tồn tại lâu, logout không đồng nghĩa đóng context | Context ngắn hạn, close trong finally |
| Dùng service account admin để tránh lỗi ACL | Blast radius lớn nếu app bị compromise | Cấp quyền tối thiểu theo OU/attribute |
| Đổi credential runtime nhưng không drain pool | Context cũ tiếp tục sống | Rotate bằng pool lifecycle có kiểm soát |
| Chia sẻ DirContext qua nhiều thread | JNDI context không được thiết kế để chia sẻ tùy tiện | Một context cho một đơn vị công việc; close đúng vòng đời |

## 14. Checklist thiết kế production

Trước khi bật pool trong ứng dụng có nhiều người dùng:

1. **Xác định identity của pool:** mọi context trong pool sẽ Bind bằng một service DN cố định hay có principal động?
2. **Kiểm tra pool key:** pool có phân vùng theo principal không? Spring LDAP Pool2 chuẩn phân loại read-only/read-write, không phải từng user.
3. **Tách authentication và business access:** nếu user chỉ cần đăng nhập, dùng Bind riêng; truy vấn nghiệp vụ dùng service account pool và authorization ở app.
4. **Đặt ACL tối thiểu:** service account chỉ đọc/ghi đúng OU và attribute cần thiết.
5. **Không giữ password end-user:** tránh đưa credential vào session, log, pool key hoặc thread-local lâu dài.
6. **Dùng TLS:** LDAPS/StartTLS đúng, trust chain và hostname verification đầy đủ.
7. **Cấu hình pool:** max total, max per key, max idle, max wait và validation theo tải thực.
8. **Kiểm thử identity isolation:** hai user có ACL khác nhau, sequential và concurrent.
9. **Kiểm thử rotation:** đổi password service/user, drain context cũ và xác minh Bind mới.
10. **Đóng context đúng cách:** luôn close trong finally/try-with-resources wrapper phù hợp; không giữ context ngoài request cần thiết.
11. **Theo dõi audit:** phân biệt application actor với LDAP Bind identity.
12. **Có đường rollback:** khi pool identity có vấn đề, chuyển về context mới không pool trong thời gian điều tra.

## 15. Câu hỏi tự đánh giá

1. Sau khi LDAP Bind thành công, danh tính của một `DirContext` thay đổi thế nào?
2. Vì sao `AuthenticationSource` được gọi khi tạo context không có nghĩa nó được gọi trước mỗi request?
3. Pool Spring LDAP chuẩn phân biệt những loại context nào? Pool key có bao gồm user DN/password không?
4. Rủi ro khi bọc `LdapContextSource` dùng credential động bằng `PoolingContextSource` là gì?
5. Vì sao `testOnBorrow` không phát hiện context đang Bind bằng user trước?
6. `getReadOnlyContext()` và `getContext(principal, credentials)` khác nhau như thế nào?
7. Vì sao mô hình service account cố định thường phù hợp với pool dùng chung?
8. Nếu LDAP server phải audit chính xác end-user, service-account pool có đáp ứng yêu cầu đó không?
9. Vì sao không nên đưa password thô vào pool key?
10. Password rotation cần xử lý các context active/idle như thế nào?
11. Làm sao kiểm thử hai người dùng không nhận context của nhau?
12. Vì sao pool READ_ONLY/READ_WRITE không thay thế ACL và application authorization?

**Ghi nhớ:** một LDAP context đã Bind mang theo **danh tính của người đã xác thực**. Spring LDAP `AuthenticationSource` cung cấp credential khi tạo context, còn pool chuẩn tái sử dụng context theo loại READ_ONLY/READ_WRITE, không theo user DN/password. Vì vậy, hãy dùng **pool với service account cố định** cho thao tác nghiệp vụ dùng chung; dùng **Bind/context riêng và đóng ngay** khi cần xác thực theo từng user. Không dựa vào validation để sửa sai identity, không giữ password user trong pool/thread-local và luôn kiểm thử quyền bằng hai danh tính có ACL khác nhau.

### Tài liệu tham khảo

- Spring LDAP Reference — [Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): cơ chế pool, read-only/read-write context và mục Known Issues về Custom Authentication.
- Spring LDAP Reference — [Configuration: Custom Principal and Credentials Management](https://docs.spring.io/spring-ldap/reference/configuration.html): `AuthenticationSource`, principal/password tĩnh và động.
- Spring LDAP API — [`ContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html): `getReadOnlyContext`, `getReadWriteContext`, `getContext(principal, credentials)`.
- Spring LDAP API — [`PooledContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html): pool keyed theo context type, cấu hình validator và các số liệu active/idle/waiters.
- Spring LDAP API — [`PoolConfig`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/pool2/factory/PoolConfig.html): giới hạn pool, max wait và validation settings.
- Spring LDAP API — [`AuthenticationSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AuthenticationSource.html): hợp đồng lấy principal/credentials khi tạo context.
- Spring LDAP Reference — [User Authentication using Spring LDAP](https://docs.spring.io/spring-ldap/reference/user-authentication.html): `ContextSource.getContext`, tìm DN trước Bind, lưu ý operation bổ sung và `LdapClient.authenticate()`.
- Spring LDAP API — [`LdapClient.AuthenticateSpec`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapClient.AuthenticateSpec.html): truy vấn user, cung cấp password và thực hiện authentication.
- Spring LDAP API — [`AbstractContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `AuthenticationSource`, native JNDI pooling và context creation.
- Spring Security — [LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): xác thực LDAP Bind và quản lý Authentication.
- IETF [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): Bind, authentication identity và bảo vệ credential.
