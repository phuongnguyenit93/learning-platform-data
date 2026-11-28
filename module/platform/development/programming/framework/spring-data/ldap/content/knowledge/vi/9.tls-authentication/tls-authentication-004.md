# Thương lượng StartTLS qua chiến lược xác thực của Spring LDAP

Khi ứng dụng Java dùng **Spring Data LDAP** để tra cứu người dùng, nhóm, đọc thuộc tính hoặc thực hiện CRUD qua `LdapRepository` và `LdapTemplate`, dữ liệu được truyền qua một kết nối tới LDAP server. Nếu kết nối không được bảo vệ, thông tin truy vấn, kết quả thư mục và đặc biệt là thông tin đăng nhập bằng **SIMPLE bind** có thể bị lộ trên đường truyền. **StartTLS** cho phép bắt đầu bằng kết nối `ldap://` rồi nâng cấp chính kết nối đó thành một kênh TLS **trước khi** gửi thông tin xác thực cần bảo vệ.

Bài thuộc chương **TLS và xác thực** này đi sâu vào cách Spring LDAP thương lượng StartTLS thông qua `DirContextAuthenticationStrategy`, lựa chọn `DefaultTlsDirContextAuthenticationStrategy` hoặc `ExternalTlsDirContextAuthenticationStrategy`, thiết lập `LdapContextSource`, kiểm tra chứng chỉ, xử lý lỗi và kiểm thử kết nối. Cần hiểu đúng điểm này trước khi tối ưu repository, chọn base DN, tìm theo LDAP filter, dùng ODM để ánh xạ entry sang Java object hoặc ghi dữ liệu vào directory.

## 1. Trước tiên, phân biệt LDAP, LDAPS và StartTLS

| Cơ chế | URL thường dùng | Kênh TLS hình thành khi nào? | Điểm cần nhớ |
|---|---|---|---|
| LDAP không TLS | `ldap://host:389` | Không có nếu client không nâng cấp | Không được gửi SIMPLE bind với mật khẩu qua kênh không bảo vệ |
| **StartTLS** | `ldap://host:389` | Sau yêu cầu mở rộng StartTLS trên kết nối LDAP ban đầu | Client phải yêu cầu nâng cấp và xác minh TLS **trước** khi bind bằng mật khẩu |
| **LDAPS** (LDAP over TLS) | `ldaps://host:636` | TLS được thiết lập ngay từ đầu kết nối | Không cần gửi thao tác StartTLS riêng |

Cổng **389** và **636** là các cổng thường gặp, không phải yêu cầu bất biến: môi trường thật có thể cấu hình các cổng khác. Điều quan trọng là **scheme và cơ chế TLS phải khớp**, ví dụ không đặt `ldaps://` rồi vẫn mong chiến lược StartTLS nâng cấp thêm một lần.

StartTLS là một **LDAP extended operation** (OID `1.3.6.1.4.1.1466.20037`). Đây không phải câu lệnh LDAP search, một thuộc tính của user hay phương thức xác thực. Sau khi server chấp nhận yêu cầu, client/server tiến hành TLS handshake; **chỉ khi handshake và xác minh chứng chỉ thành công** thì các bước xác thực LDAP và truy vấn mới được tiếp tục.

```text
Ứng dụng Java                   LDAP server
      |                               |
      |---- TCP tới ldap://:389 ----->|
      |                               |
      |---- StartTLS request -------->|
      |<--- StartTLS success ---------|
      |<==== TLS handshake ==========>|  kiểm tra CA, hostname, hạn chứng chỉ
      |                               |
      |---- SIMPLE bind (trong TLS) ->|  hoặc SASL EXTERNAL qua TLS
      |<--- bind result (trong TLS) --|
      |---- search/lookup/modify ---->|  các thao tác đều trên kênh TLS
      |<--- LDAP result -------------|
```

Sơ đồ thể hiện đường đi **thành công**. Nếu server không hỗ trợ StartTLS, từ chối nâng cấp, chứng chỉ không hợp lệ hoặc handshake thất bại, client **phải dừng** thao tác cần bảo vệ. Không được âm thầm tiếp tục bằng SIMPLE bind trên kết nối cleartext (*fail open*).

## 2. StartTLS không phải phương thức chứng minh danh tính LDAP

Trong thiết kế, phải tách hai khái niệm:

- **TLS (bảo mật kênh truyền):** mã hóa và kiểm tra danh tính máy chủ qua chứng chỉ; có thể xác thực chứng chỉ phía client khi được cấu hình.
- **LDAP authentication (xác thực bind):** quyết định danh tính/đặc quyền mà directory gắn với kết nối, chẳng hạn SIMPLE bind bằng DN + mật khẩu hoặc SASL EXTERNAL dựa trên chứng chỉ client.

Vì vậy, **“đã dùng TLS” không có nghĩa “đã bind thành công”**. Một kênh TLS có thể an toàn nhưng server vẫn từ chối mật khẩu, tài khoản không có ACL đọc nhánh `ou=people`, hoặc schema không cho phép thao tác `modify`.

Ví dụ:

```text
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
```

DN xác định vị trí entry trong directory; `objectClass` liên quan tới schema; `uid`, `cn`, `sn` là thuộc tính LDAP. Chúng **không phải tham số của TLS handshake**. TLS bảo vệ việc truy cập các entry này trên đường truyền, nhưng **DN, schema, LDAP filter, ACL** vẫn quyết định thao tác tra cứu/CRUD có hợp lệ và được phép hay không.

## 3. Vai trò của `DirContextAuthenticationStrategy`

Trong Spring LDAP, `LdapContextSource` tạo và quản lý vòng đời các `DirContext` dùng bởi `LdapTemplate` và repository. Theo cấu hình mặc định, Spring LDAP thường dùng **SIMPLE authentication**. Nếu cần StartTLS, ta thay đổi cách tạo/xác thực context bằng một `DirContextAuthenticationStrategy` dành cho TLS.

Về mặt khái niệm, chiến lược được gọi ở hai giai đoạn:

1. **Chuẩn bị môi trường JNDI** trước khi tạo context, tránh áp dụng SIMPLE credentials quá sớm trên kết nối chưa được nâng cấp.
2. **Xử lý context sau khi tạo:** thực hiện thao tác StartTLS, TLS handshake, rồi áp dụng cơ chế xác thực đã chọn trên kênh bảo mật. Khi đóng context, chiến lược còn quản lý cách đóng TLS tương ứng.

Đây là lý do **chỉ đặt `spring.ldap.urls=ldap://...` không tự bật StartTLS**. URL `ldap://` không yêu cầu nâng cấp; cần cấu hình chiến lược, sau đó kiểm chứng server thực sự nhận StartTLS trước bind.

Spring LDAP cung cấp hai chiến lược TLS quan trọng:

| Chiến lược | Cách xác thực LDAP sau khi thương lượng TLS | Điều kiện sử dụng |
|---|---|---|
| `DefaultTlsDirContextAuthenticationStrategy` | **SIMPLE bind** bằng principal và mật khẩu trên kênh TLS | Directory có tài khoản bind, hỗ trợ StartTLS và chính sách cho phép SIMPLE trên kênh bảo mật |
| `ExternalTlsDirContextAuthenticationStrategy` | **SASL EXTERNAL** dựa trên chứng chỉ client/TLS peer identity | Directory hỗ trợ SASL EXTERNAL, xác minh chứng chỉ client và ánh xạ chứng chỉ sang identity/ACL |

Đừng nhầm **EXTERNAL SASL** với “bật SSL verification”: cả hai chiến lược đều cần xác minh chứng chỉ **máy chủ**. Chiến lược EXTERNAL còn cần khả năng xác thực client theo chứng chỉ, **không chỉ một truststore** chứa CA của server.

## 4. Cấu hình StartTLS với SIMPLE bind bằng `DefaultTlsDirContextAuthenticationStrategy`

Một ví dụ Spring Boot dùng các thuộc tính **riêng của ứng dụng** để tránh nhầm với auto-configuration. Directory giả định là `ldap.example.org`, suffix `dc=example,dc=org` và service account được cấp quyền đọc hẹp.

```yaml
app:
  ldap:
    url: ldap://ldap.example.org:389
    base: dc=example,dc=org
    bind-dn: cn=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Không đưa mật khẩu thật vào YAML hay source code; biến môi trường ở đây chỉ biểu diễn cách cấp secret từ môi trường vận hành. Quyền file, log cấu hình và nền tảng quản lý secret vẫn cần được bảo vệ.

Ví dụ cấu hình Java đầy đủ, với các API Spring LDAP thông dụng:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapStartTlsConfiguration {

    @Bean
    public LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.password}") String password) {

        DefaultTlsDirContextAuthenticationStrategy tls =
                new DefaultTlsDirContextAuthenticationStrategy();
        tls.setShutdownTlsGracefully(false); // Giá trị mặc định; xem phần vòng đời.

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);            // ldap://, KHÔNG phải ldaps://
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setAuthenticationStrategy(tls);
        source.setPooled(false);       // Tắt native JNDI LDAP pooling.
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Khi chạy trong Spring container, `LdapContextSource` được gọi lifecycle initialization sau khi bean được tạo. Nếu tự khởi tạo source **ngoài Spring container**, cần hoàn tất cấu hình rồi gọi `afterPropertiesSet()` theo contract của `AbstractContextSource`.

**Điểm thiết kế cần xác minh theo phiên bản Spring Boot:** khi bạn tự khai báo `LdapContextSource` và `LdapTemplate`, các cấu hình auto-configuration có thể nhường chỗ cho bean tùy chỉnh. Không đồng thời khai báo thêm context source mặc định trùng chức năng rồi không biết repository đang dùng cái nào. Spring Data LDAP repository và `LdapTemplate` cần sử dụng đúng context source có chiến lược StartTLS.

### Biến thể: để Spring Boot auto-configure context source

Với những phiên bản Spring Boot hỗ trợ tự gắn bean `DirContextAuthenticationStrategy` vào `LdapContextSource` do Boot tạo, có thể dùng:

```yaml
spring:
  ldap:
    urls: ldap://ldap.example.org:389
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.DirContextAuthenticationStrategy;

@Configuration
public class LdapTlsStrategyBean {
    @Bean
    public DirContextAuthenticationStrategy ldapTlsStrategy() {
        return new DefaultTlsDirContextAuthenticationStrategy();
    }
}
```

**Không áp dụng cả hai biến thể đồng thời** nếu chúng tạo ra nhiều bean cạnh tranh. Phải đối chiếu tài liệu **đúng phiên bản Boot** đang dùng. Đặc biệt, cấu hình `spring.ldap.ssl.bundle` hoặc `spring.ldap.ssl.enabled` dành cho **LDAPS** ở các phiên bản Boot tương ứng **không thay thế cấu hình StartTLS trên `ldap://`**. Nếu cần socket factory tùy chỉnh cho StartTLS, cấu hình nó tại chiến lược TLS.

## 5. Đọc một entry qua kênh StartTLS đã cấu hình

Khi `LdapContextSource` được thiết lập đúng, code `LdapTemplate` hoặc `LdapRepository` thực hiện truy vấn **không phải tự gửi lệnh StartTLS mỗi lần**. Chiến lược xác thực xử lý điều đó tại bước tạo context/kết nối.

Ví dụ đọc người dùng theo `uid` dưới `ou=people`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class SecureDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public SecureDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        LdapQuery q = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<String> mapper =
                attrs -> (String) attrs.get("cn").get();

        return ldapTemplate.search(q, mapper);
    }
}
```

Đoạn code giả định context base `dc=example,dc=org`, vì vậy `ou=people` là **search base tương đối**. Filter builder escape giá trị `uid` đúng cú pháp LDAP filter; không viết `"(uid=" + uid + ")"` với input bên ngoài. `objectClass` và schema của directory quyết định entry nào hợp lệ; tài khoản bind phải có ACL đọc `cn`.

Nếu ứng dụng có entity ODM `@Entry`, `@Id` dạng `javax.naming.Name`, `@Attribute` và `LdapRepository`, chúng **đều dùng kết nối LDAP qua context source** được cấu hình, chứ không có cách thương lượng TLS riêng ở mỗi annotation. `save`, `delete`, `rename` hay `LdapTemplate.modifyAttributes` vẫn chịu ACL và schema, dù kênh truyền đã được bảo vệ.

## 6. Tại sao SIMPLE bind phải xảy ra sau TLS?

Trong SIMPLE bind, client gửi thông tin principal và credential theo cơ chế LDAP. **SIMPLE không tự mã hóa mật khẩu**: tính bảo mật trên đường truyền phụ thuộc vào lớp TLS bên dưới.

Một quy trình đúng yêu cầu:

1. Tạo kết nối `ldap://` tới server tin cậy.
2. Gửi **StartTLS extended request** trước khi truyền credential cần bảo vệ.
3. Nhận chấp nhận nâng cấp; thực hiện TLS handshake.
4. Xác minh **chuỗi chứng chỉ, hostname, hiệu lực và chính sách tin cậy**.
5. Thực hiện SIMPLE bind **bên trong TLS** bằng tài khoản đã cấu hình.
6. Thực hiện LDAP search/lookup/modify trên cùng kênh bảo mật.

Nếu server từ chối StartTLS, việc “thử lại với SIMPLE không TLS” là **downgrade nguy hiểm**. Cơ chế tự động failover cũng phải **thương lượng và xác minh TLS trên từng kết nối mới**. Có nhiều URL dự phòng không có nghĩa chứng chỉ của server thứ hai được bỏ qua.

> **Quan trọng:** StartTLS bảo vệ kết nối sau khi được thương lượng. Bước trao đổi LDAP ban đầu để yêu cầu StartTLS diễn ra khi chưa có TLS, nên ứng dụng **không gửi password hoặc dữ liệu nhạy cảm trước thời điểm đó**.

## 7. Xác minh chứng chỉ TLS của LDAP server

Có hai loại kiểm tra thường gặp:

- **Chain trust:** chứng chỉ server được ký bởi CA hoặc chuỗi CA mà ứng dụng tin cậy (hoặc được tin cậy theo cấu hình tương đương).
- **Hostname verification:** tên host trong URL `ldap://ldap.example.org:389` phải phù hợp với định danh trong chứng chỉ (thường là Subject Alternative Name).

**Truststore** chứa chứng chỉ CA/điểm tin cậy dùng để xác thực server; **keystore** có thể chứa certificate + private key của **client** nếu triển khai mutual TLS/SASL EXTERNAL. Đưa chứng chỉ server vào truststore không tự biến ứng dụng thành client có danh tính EXTERNAL.

Trong Java, có thể cung cấp trust material cho JSSE bằng cấu hình runtime được bảo vệ, chẳng hạn `javax.net.ssl.trustStore` và `javax.net.ssl.trustStorePassword`, hoặc tạo `SSLSocketFactory` từ `SSLContext` ứng dụng quản lý rồi truyền cho TLS strategy qua `setSslSocketFactory(...)`. Không đưa mật khẩu truststore/keystore trực tiếp vào source hoặc log; tránh cấu hình JVM-wide khi cần phân biệt trust material của nhiều dịch vụ trong cùng ứng dụng.

`AbstractTlsDirContextAuthenticationStrategy` còn có `setHostnameVerifier(...)`; để mặc định sẽ sử dụng cơ chế xác minh hostname mặc định theo triển khai. **Không cấu hình verifier luôn trả `true`**, không dùng trust manager chấp nhận mọi chứng chỉ và không đặt chế độ tin tưởng tất cả để “vượt lỗi chứng chỉ” trong production.

Một số lỗi thường gặp:

| Biểu hiện | Khả năng cần kiểm tra | Cách xử lý |
|---|---|---|
| `PKIX path building failed` | JVM không tin CA/chain của server | Cài đúng trust anchor vào truststore, kiểm tra full chain |
| Hostname verification thất bại | URL dùng alias/IP khác SAN của chứng chỉ | Dùng hostname đúng hoặc cấp lại chứng chỉ phù hợp |
| Chứng chỉ hết hạn | Không còn trong khoảng hiệu lực | Gia hạn/thay đúng chứng chỉ |
| Handshake lỗi phiên bản/cipher | Chính sách TLS client/server không tương thích | Xác minh phiên bản TLS/cipher được phép, cập nhật cấu hình hợp lệ |
| TLS handshake thành công, bind bị từ chối | Credential sai, tài khoản bị khóa hoặc policy directory | Kiểm tra bind DN, phương thức xác thực và ACL riêng |
| TLS thành công nhưng search rỗng | Sai DN, search base, filter, schema hoặc ACL | Kiểm tra phạm vi truy vấn; không đổ lỗi cho TLS |

## 8. SASL EXTERNAL qua `ExternalTlsDirContextAuthenticationStrategy`

Không phải môi trường nào cũng muốn ứng dụng dùng DN + password. Một số tổ chức cấu hình LDAP server **xác thực client bằng chứng chỉ** và ánh xạ certificate identity sang danh tính LDAP, sau đó sử dụng SASL EXTERNAL.

```text
StartTLS thành công
      ↓
Server xác minh chứng chỉ của client trong TLS handshake
      ↓
Client yêu cầu SASL EXTERNAL bind
      ↓
Server ánh xạ cert identity → LDAP authorization identity
      ↓
Directory kiểm tra ACL cho các thao tác LDAP
```

Spring LDAP có `ExternalTlsDirContextAuthenticationStrategy` để phục vụ cơ chế này:

```java
import org.springframework.ldap.core.support.ExternalTlsDirContextAuthenticationStrategy;

ExternalTlsDirContextAuthenticationStrategy strategy =
        new ExternalTlsDirContextAuthenticationStrategy();

// Context source dùng chiến lược này thay vì DefaultTls...
// Phải cấu hình TLS client key material và mapping SASL EXTERNAL ở server.
```

Khác biệt quan trọng:

| Câu hỏi | SIMPLE trên StartTLS | SASL EXTERNAL trên StartTLS |
|---|---|---|
| Cần mật khẩu LDAP để bind? | Có, theo chính sách tài khoản | Không theo cơ chế EXTERNAL; server xác thực từ danh tính TLS |
| Cần chứng chỉ client? | Không nhất thiết | Thường cần và server phải xác minh/ánh xạ |
| Có phải xác minh chứng chỉ server? | **Có** | **Có** |
| LDAP server có cần hỗ trợ cơ chế tương ứng? | SIMPLE bind qua TLS | SASL EXTERNAL và quy tắc ánh xạ chứng chỉ |
| Có tự cấp quyền quản trị? | Không | Không; cả hai đều chịu ACL |

Với EXTERNAL, chỉ thay class strategy **chưa đủ**: cần TLS key material, khả năng client gửi chứng chỉ, server chấp nhận certificate auth và ánh xạ danh tính đúng. Nếu chưa cấu hình hoàn chỉnh, đừng tự chuyển qua SIMPLE không TLS để “dự phòng”.

## 9. Native pooling, vòng đời context và `shutdownTlsGracefully`

Thương lượng TLS có chi phí handshake. Việc tạo kết nối mới liên tục có thể gây độ trễ và tăng CPU, nhưng cách pooling phải tương thích với TLS strategy.

**Spring LDAP khuyến nghị tắt native JNDI LDAP pooling khi sử dụng StartTLS** (`source.setPooled(false)`). Cơ chế pool nội bộ JNDI có thể tái sử dụng kết nối theo cách không phù hợp với vòng đời TLS/credential, đặc biệt khi TLS session không được đóng tường minh.

Nếu cần pooling, đánh giá **pooling của Spring LDAP** (ví dụ `PoolingContextSource` và thư viện pool tương ứng theo phiên bản). Pool cần có kiểm tra kết nối hợp lệ, xử lý kết nối chết, giới hạn idle/active và bảo đảm context đã được StartTLS/bind theo đúng danh tính trước khi đưa ra cho nghiệp vụ.

**Cẩn trọng với AuthenticationSource theo từng người dùng:** một pool vốn mặc định tái sử dụng những context có cùng cấu hình không thích hợp khi credential thay đổi theo request, vì có nguy cơ lấy nhầm context đã xác thực bằng người dùng khác. Hãy thiết kế tách luồng tài khoản dịch vụ với xác thực từng người và đối chiếu tài liệu pooling của phiên bản đang dùng.

`shutdownTlsGracefully`:

- `false` là mặc định của chiến lược TLS Spring LDAP: không yêu cầu đóng TLS tường minh trước khi context bị đóng.
- `true`: thử đóng TLS một cách tường minh trước khi đóng context.
- Hành vi tương thích khác nhau theo LDAP server/provider, vì vậy **chỉ đổi giá trị sau khi kiểm thử với directory thật** và theo dõi lỗi khi đóng/trả kết nối về pool.

Không suy luận `shutdownTlsGracefully=false` làm yếu TLS đang hoạt động: đây là **quy tắc kết thúc phiên TLS**, không phải công tắc bỏ qua chứng chỉ hay cho phép gửi mật khẩu không mã hóa.

## 10. Kiểm chứng kết nối StartTLS từ ngoài Java

Trước khi kết luận lỗi thuộc Spring Data LDAP, hãy xác nhận server, chứng chỉ và quyền bind bằng một client LDAP độc lập ở **môi trường kiểm thử được phép**.

Ví dụ CLI OpenLDAP:

```bash
ldapwhoami -x \
  -H ldap://ldap.example.org:389 \
  -ZZ \
  -D 'cn=svc-reader,ou=service-accounts,dc=example,dc=org' \
  -W
```

Với công cụ OpenLDAP:

- `-ZZ` **yêu cầu** StartTLS thành công; khác với chế độ chỉ thử nâng cấp nhưng có thể tiếp tục khi nâng cấp thất bại.
- `-D` chỉ định principal; `-W` yêu cầu nhập password tương tác.
- Client phải được cấu hình **tin cậy CA** theo cơ chế OpenLDAP, không đặt chính sách không xác minh chứng chỉ để vượt lỗi.
- Nếu thành công, kết quả xác nhận danh tính bind; nó **chưa xác nhận** tài khoản đó có quyền đọc mọi entry của directory.

Thử truy vấn hẹp sau khi bind qua StartTLS:

```bash
ldapsearch -LLL -x -ZZ \
  -H ldap://ldap.example.org:389 \
  -D 'cn=svc-reader,ou=service-accounts,dc=example,dc=org' -W \
  -b 'uid=u1001,ou=people,dc=example,dc=org' \
  -s base '(objectClass=*)' cn sn
```

Kết quả mong đợi là đúng entry, nếu nó tồn tại và ACL cho phép. Nếu `ldapwhoami` thành công nhưng `ldapsearch` trả rỗng, hãy kiểm tra base DN, `uid`, `objectClass`, ACL, search scope và tài khoản bind trước khi thay đổi TLS strategy.

Có thể dùng `openssl s_client -starttls ldap -connect ldap.example.org:389` để quan sát chứng chỉ/TLS nếu phiên bản OpenSSL hỗ trợ giao thức này; đây chỉ là công cụ chẩn đoán transport, **không thay thế phép thử LDAP bind/search**.

## 11. Gắn lỗi với đúng giai đoạn, tránh che lỗi bảo mật

| Giai đoạn | Dấu hiệu lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|---|
| TCP connect | Connection refused, timeout | Sai host/port, firewall, server down | Kiểm tra DNS, mạng, cổng và timeout |
| StartTLS extended operation | Server không hỗ trợ/từ chối | Chưa bật StartTLS, policy server hoặc proxy không chuyển đúng operation | Xác nhận server capability, không fallback cleartext |
| TLS handshake | PKIX, SAN mismatch, phiên bản/cipher | CA/chứng chỉ/hostname sai | Sửa trust material, hostname hoặc chính sách TLS |
| SIMPLE/SASL bind | Invalid credentials, cơ chế không hỗ trợ | Sai DN/password, cert mapping, account policy | Kiểm tra chiến lược và cấu hình xác thực |
| LDAP search/lookup | No such object, empty result, ACL | Base DN, DN, filter, scope, ACL | Kiểm tra directory model, không gộp vào TLS error |
| CRUD | Insufficient access, schema violation | ACL ghi, objectClass/MUST attribute | Kiểm chứng quyền và schema, không dùng admin vượt kiểm soát |
| Close/pool reuse | Connection reset/closed context | Vòng đời TLS/context/pool không tương thích | Kiểm tra shutdown strategy, native pooling và validation |

Một anti-pattern nguy hiểm là:

```text
try StartTLS
if error:
    continue with plain LDAP and SIMPLE bind
```

Thiết kế đúng phải **fail closed**: kết nối hoặc xác thực không bảo đảm điều kiện bảo mật thì dừng; ghi log đã che giá trị nhạy cảm; trả lỗi hạ tầng phù hợp. Không log password, private key, secret store token hoặc toàn bộ DN/thuộc tính cá nhân khi không cần.

### Metric cần quan sát

Nên phân biệt các chỉ số sau:

- Số lần mở connection/context mới và **số lần thương lượng StartTLS thành công/thất bại**.
- Thời gian TLS handshake, thời gian SIMPLE/SASL bind, thời gian LDAP search/modify.
- Số lần context bị tái sử dụng từ pool, lỗi validate pool và timeout chờ kết nối.
- Tỷ lệ lỗi chứng chỉ/hostname, lỗi xác thực, lỗi ACL/schema — mỗi loại cần nhãn lỗi khác nhau.

Một lời gọi `repository.findByUid(...)` **không nhất thiết tương đương một lần StartTLS** nếu hệ thống tái sử dụng context; ngược lại một HTTP request có thể kích hoạt nhiều LDAP operations. Đừng dùng mỗi latency toàn API để kết luận TLS handshake là nút thắt khi chưa đối chiếu log/metric ở đúng tầng.

## 12. Kiểm thử với directory: không chỉ kiểm thử happy path

Đối với StartTLS, mock `LdapTemplate` chỉ chứng minh logic Java, **không chứng minh kênh TLS có thực sự được thương lượng**. Cần kiểm thử tích hợp với LDAP server có TLS và schema tương thích, tài khoản bind/ACL như dự kiến.

| Ca kiểm thử | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| StartTLS + SIMPLE thành công | Server có chứng chỉ hợp lệ, account đúng | TLS thành công rồi mới bind; lookup trả entry hợp lệ |
| Server không hỗ trợ StartTLS | Endpoint thử nghiệm từ chối extended operation | Không SIMPLE bind bằng cleartext; request lỗi |
| Chứng chỉ CA chưa tin cậy | Không có CA đúng trong truststore | Handshake thất bại, không fallback |
| Chứng chỉ hostname sai | URL host không khớp SAN | Kết nối bị từ chối |
| SIMPLE bind mật khẩu sai | TLS đúng, password sai | Lỗi authentication, không chẩn đoán nhầm TLS |
| DN/base sai | TLS + bind thành công, search sai OU | Trả không tìm thấy hoặc lỗi tìm kiếm phù hợp |
| Account thiếu quyền | TLS + bind thành công, ACL giới hạn | Từ chối hoặc che kết quả theo server policy |
| EXTERNAL client certificate | Cert client hợp lệ, server map đúng | SASL EXTERNAL bind và ACL đúng |
| EXTERNAL thiếu mapping | TLS có thể được thiết lập, server không map được client | Bind bị từ chối; không chuyển sang SIMPLE không bảo vệ |
| Tắt native pool | `setPooled(false)` và chạy nhiều lookup | Không tái sử dụng kết nối JNDI không an toàn |
| Vòng đời context | Đóng/reopen nhiều lần, thử shutdown gracefully nếu cần | Không rò connection, không lỗi khi tái sử dụng |
| Lỗi giữa chừng | Server đóng kết nối sau TLS | Lỗi được phân loại, retry có giới hạn và thương lượng lại trên kết nối mới |

**Kiểm tra có thể xác minh:** dùng server access/audit log hoặc packet capture **trong môi trường được cấp phép** để quan sát có StartTLS request trước bind; sau TLS handshake, dữ liệu LDAP được mã hóa trên đường truyền. Packet capture không giải mã được payload LDAP trong TLS chỉ bằng cách đọc gói tin; không cần tắt TLS để chụp dữ liệu nhạy cảm.

Với Active Directory hoặc sản phẩm LDAP cụ thể, phải xác nhận policy **signing/channel binding**, TLS trust và yêu cầu xác thực riêng của directory. Không mặc định mọi server hỗ trợ cùng phiên bản TLS, cùng cơ chế SASL EXTERNAL hay cùng xử lý đóng phiên.

## 13. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Chỉ đặt `ldap://` rồi nghĩ đã có StartTLS | URL không tự gửi StartTLS extended operation | Cấu hình TLS authentication strategy và kiểm chứng |
| Dùng `ldaps://` với strategy StartTLS | Hai cơ chế bảo vệ khác nhau | Chọn một cơ chế tương ứng scheme và endpoint |
| SIMPLE bind trước khi nâng cấp | Mật khẩu không được TLS bảo vệ | Chỉ bind sau handshake đã xác thực |
| Dùng trust-all SSL để chạy test | Che lỗi MITM/certificate, tạo cấu hình nguy hiểm | Cấp CA/cert test hợp lệ vào truststore test |
| Chỉ import CA là đã có SASL EXTERNAL | Trust server cert khác việc có client cert và mapping | Cấu hình key material và server mapping |
| Bật native JNDI pooling | Không phù hợp vòng đời StartTLS/credential | Tắt native pool; nếu cần dùng pooling của Spring LDAP đã kiểm thử |
| Đặt `shutdownTlsGracefully=true` ở mọi môi trường | Server xử lý đóng TLS khác nhau | Kiểm thử với server đích; mặc định false |
| Bỏ qua lỗi TLS và thử LDAP thường | Cho phép downgrade bảo mật | Fail closed; không bao giờ gửi password trên cleartext |
| Kết luận lỗi search là lỗi TLS | Search còn phụ thuộc DN/filter/schema/ACL | Phân lớp TCP, TLS, bind và search |
| Cho rằng `spring.ldap.ssl.bundle` là StartTLS | Cấu hình này áp dụng LDAPS ở các Boot version hỗ trợ | Dùng `DirContextAuthenticationStrategy` cho StartTLS |

## 14. Bài tập thiết kế

Ứng dụng Spring Boot cần đọc LDAP directory `ldap://ldap.internal.example:389`, suffix `dc=example,dc=org`. Server yêu cầu **StartTLS trước khi chấp nhận SIMPLE bind**; service account `cn=svc-reader,ou=service-accounts,dc=example,dc=org` chỉ có quyền đọc `ou=people`. Ứng dụng dùng `LdapRepository` và `LdapTemplate` để tra cứu `inetOrgPerson`.

Hãy trả lời:

1. Chiến lược `DirContextAuthenticationStrategy` nào phù hợp nếu đã có service account + password, nhưng **không** có client certificate?
2. Chọn URL `ldap://` hay `ldaps://` và vì sao?
3. Ở bước nào phải xác minh chứng chỉ và hostname để tránh lộ SIMPLE bind password?
4. Nên cấu hình native pooling như thế nào? Nếu cần tái sử dụng kết nối, giải pháp nào cần đánh giá?
5. Khi RootDSE/search thành công nhưng `ldapTemplate.search(...)` không thấy user, cần kiểm tra những vấn đề gì ngoài TLS?
6. Nếu một server dự phòng từ chối StartTLS, ứng dụng có được phép tự thử SIMPLE bind không TLS không?
7. Đổi sang SASL EXTERNAL cần thêm những cấu hình phía client/server nào?

**Định hướng đáp án:** dùng `DefaultTlsDirContextAuthenticationStrategy`, `ldap://`, handshake + xác minh server cert **trước** SIMPLE bind; tắt native JNDI pooling. Nếu cần pooling, lựa chọn của Spring LDAP phải được kiểm thử với danh tính kết nối phù hợp. Tìm kiếm còn phụ thuộc base DN, schema, `objectClass`, filter và ACL; không fallback sang cleartext. SASL EXTERNAL cần client certificate/private key, server trust/mapping và chính sách tương ứng.

## 15. Tổng kết

- **StartTLS** nâng cấp kết nối `ldap://` thành kênh TLS; **LDAPS** thiết lập TLS ngay từ lúc connect. Chúng không phải một cơ chế đồng nhất chỉ khác cổng.
- `DefaultTlsDirContextAuthenticationStrategy` thương lượng TLS rồi dùng **SIMPLE bind** trên kết nối được bảo vệ; `ExternalTlsDirContextAuthenticationStrategy` dùng **SASL EXTERNAL** với danh tính chứng chỉ client khi directory hỗ trợ.
- Cấu hình `LdapContextSource.setAuthenticationStrategy(...)` hoặc một `DirContextAuthenticationStrategy` bean được Boot auto-configure hỗ trợ. `LdapRepository` và `LdapTemplate` sử dụng context này để thao tác DN, objectClass, LDAP filter và CRUD.
- Luôn **xác minh certificate chain và hostname**, bảo vệ secret, áp dụng ACL tối thiểu và **không hạ cấp** sang SIMPLE bind không TLS khi handshake lỗi.
- **Tắt native LDAP pooling** với StartTLS; xử lý `shutdownTlsGracefully` và pooling của Spring LDAP theo đặc tính server, kiểm thử vòng đời.
- Kiểm thử trực tiếp trên directory với cả đường đi thành công và lỗi: TCP, StartTLS, TLS certificate, LDAP bind, schema/ACL và context pooling.

### Tài liệu tham khảo chính thức

- [Spring LDAP — Configuration: Custom DirContext Authentication Processing / TLS](https://docs.spring.io/spring-ldap/reference/configuration.html).
- [Spring LDAP API — DefaultTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/DefaultTlsDirContextAuthenticationStrategy.html).
- [Spring LDAP API — AbstractTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractTlsDirContextAuthenticationStrategy.html).
- [Spring Boot — Working with NoSQL Technologies: LDAP/SSL](https://docs.spring.io/spring-boot/reference/data/nosql.html).

**Ghi nhớ:** StartTLS thành công là điều kiện **bảo vệ kênh truyền**, không thay thế việc kiểm tra DN, `objectClass`, schema, quyền LDAP hay tính an toàn của filter. Trong Spring Data LDAP, hãy cấu hình đúng chiến lược xác thực ở tầng `ContextSource`, xác minh server trước bind, fail closed khi TLS lỗi và kiểm thử với directory thật trước khi xử lý dữ liệu danh tính.
