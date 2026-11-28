# SASL và xác thực bằng chứng chỉ khi hạ tầng hỗ trợ

Trong **SPRING_DATA_LDAP**, ứng dụng Java kết nối LDAP directory bằng `ContextSource`, thực thi `LdapTemplate` hoặc Spring Data LDAP repository, đọc/ghi các entry có DN (*Distinguished Name*), `objectClass` và các thuộc tính theo schema. Mỗi kết nối cần được bảo vệ khỏi nghe lén, giả mạo máy chủ; mỗi thao tác còn phải chạy dưới **danh tính LDAP được xác thực** và chịu sự kiểm soát của **ACL** (*Access Control List*).

Cấu hình phổ biến nhất là **SIMPLE Bind qua TLS**: ứng dụng gửi bind DN và mật khẩu trên một kênh đã mã hóa. Tuy nhiên, khi hạ tầng có **PKI**, LDAP server yêu cầu chứng chỉ client và hỗ trợ **SASL EXTERNAL**, ứng dụng có thể xác thực bằng chứng chỉ X.509 mà không phải gửi mật khẩu bind LDAP. Trong hệ thống Kerberos, **SASL GSSAPI** lại là một lựa chọn khác không dựa vào chứng chỉ X.509 của client.

Điều kiện **“khi hạ tầng hỗ trợ”** là trọng tâm: chỉ có chứng chỉ trong Java keystore hoặc chỉ đổi `ldap://` thành `ldaps://` **không tự làm LDAP Bind chuyển sang xác thực bằng chứng chỉ**. Directory server phải hỗ trợ cơ chế tương ứng, cấu hình yêu cầu/kiểm tra chứng chỉ và ánh xạ danh tính xác thực sang quyền truy cập hợp lệ.

Sau bài này, người học có thể:

- Phân biệt TLS, mutual TLS (*mTLS*), LDAP Bind, SASL, authorization và LDAP ACL.
- Chọn đúng giữa SIMPLE Bind qua TLS, SASL EXTERNAL với client certificate và SASL GSSAPI/Kerberos.
- Hiểu trình tự kết nối qua **LDAPS** hoặc **StartTLS**; tránh gửi credential trên kênh chưa bảo vệ.
- Cấu hình `LdapContextSource` với `ExternalTlsDirContextAuthenticationStrategy` khi dùng StartTLS, hoặc JNDI SASL EXTERNAL qua LDAPS.
- Quản lý keystore/truststore, kiểm chứng hostname, luân chuyển chứng chỉ và kiểm thử cấu hình *fail closed*.
- Chẩn đoán các lỗi bắt tay TLS, chứng chỉ client, mapping identity, Bind và quyền đọc/ghi LDAP.

## 1. Bốn lớp dễ bị nhầm lẫn

Một kết nối LDAP an toàn có nhiều bước **khác nhau**:

```text
Ứng dụng Java / Spring Data LDAP
             |
             | 1. Kết nối TCP
             v
LDAP endpoint: ldap://:389 hoặc ldaps://:636
             |
             | 2. TLS bảo mật kênh và xác minh server certificate
             |    (có thể xác minh thêm client certificate nếu mTLS)
             v
Kênh kết nối được bảo vệ
             |
             | 3. LDAP Bind:
             |    SIMPLE / SASL EXTERNAL / SASL GSSAPI / ...
             v
Danh tính đã được LDAP server xác nhận
             |
             | 4. Mapping danh tính + ACL/authorization
             v
Search / lookup / add / modify / delete
```

| Lớp | Câu hỏi được trả lời | Cơ chế ví dụ |
|---|---|---|
| **TLS server authentication** | “Tôi có đang nói chuyện với LDAP server đúng tên, đúng chứng chỉ không?” | X.509 server cert, trust chain, hostname verification |
| **TLS client authentication / mTLS** | “Client của kết nối TLS có chứng chỉ hợp lệ không?” | Client X.509 cert + private key, server yêu cầu và kiểm tra |
| **LDAP authentication (Bind)** | “Danh tính LDAP/SASL nào đang thực hiện các thao tác?” | SIMPLE, SASL EXTERNAL, SASL GSSAPI |
| **Authorization** | “Danh tính đó được đọc hay sửa entry nào?” | Mapping authc/authz identity, LDAP ACL, policy của directory |

**TLS không đồng nghĩa với LDAP Bind.** Một kết nối `ldaps://` có thể chạy SIMPLE Bind, SASL EXTERNAL hoặc một cơ chế được server hỗ trợ. Ngược lại, mTLS chứng minh client sở hữu private key tương ứng với chứng chỉ, nhưng không tự cho phép người đó sửa `cn=admins,ou=groups,...`.

Thuật ngữ:

- **Authentication identity (authcID):** danh tính được dùng để xác thực.
- **Authorization identity (authzID):** danh tính mà server sử dụng để xét quyền; có thể được ánh xạ từ authcID và không nhất thiết là cùng chuỗi.
- **SASL:** *Simple Authentication and Security Layer* (RFC 4422), khung cơ chế xác thực, **không phải một thuật toán mã hóa TLS**.

## 2. Chọn cơ chế đúng thay vì cấu hình theo cảm tính

| Phương án | Credential client dùng để xác thực LDAP | Điều kiện hạ tầng | Khi phù hợp |
|---|---|---|---|
| **SIMPLE Bind qua LDAPS** | Bind DN + password | TLS server, tài khoản LDAP, chính sách bảo mật phù hợp | Service account phổ biến, dễ vận hành |
| **SIMPLE Bind qua StartTLS** | Bind DN + password **sau khi StartTLS thành công** | Server hỗ trợ StartTLS, client bắt tay thành công | Endpoint `ldap://:389` hỗ trợ nâng cấp kênh |
| **SASL EXTERNAL qua mTLS** | Xác thực ở lớp TLS bằng client cert/private key; SASL EXTERNAL dùng danh tính đã xác thực | PKI, server yêu cầu/kiểm tra client cert, hỗ trợ EXTERNAL và ánh xạ quyền | Service-to-directory khi đã có PKI và nhu cầu bỏ bind password |
| **SASL GSSAPI** | Kerberos ticket/service principal | KDC, DNS/SPN, đồng bộ giờ, JAAS/GSSAPI, LDAP server hỗ trợ | Môi trường tích hợp Kerberos/AD theo chính sách tổ chức |
| **SASL EXTERNAL qua Unix socket** | Danh tính hệ điều hành/peer credentials | `ldapi:///`, server có hỗ trợ và chính sách tương ứng | Công cụ quản trị local; **không phải** chứng chỉ TLS |

SASL EXTERNAL nghĩa là dùng **danh tính đã được xác thực bởi một lớp bên ngoài**. Với TLS, lớp đó có thể là **chứng chỉ client**; với OpenLDAP qua `ldapi:///`, danh tính có thể là UID/GID của tiến trình. Vì vậy nói “EXTERNAL luôn bằng chứng chỉ” là chưa chính xác.

**Không có cơ chế nào thay thế ACL.** Sau Bind thành công, server vẫn phải hạn chế đúng quyền theo từng entry/attribute. Không gán quyền quản trị chỉ vì client có một chứng chỉ do CA nội bộ cấp.

## 3. LDAPS và StartTLS khác nhau ở bước nào?

### 3.1. LDAPS: TLS ngay khi thiết lập kết nối

```text
Client                       LDAP server :636
  | -------- TCP -----------------> |
  | <======= TLS handshake ======> |
  |   xác minh server cert         |
  |   client cert nếu server yêu cầu
  |                                |
  | -- LDAP Bind (SIMPLE/EXTERNAL) ->|
  | <-------- Bind result -------- |
  | -- Search / Modify -----------> |
```

Ví dụ URL: `ldaps://ldap.example.org:636`. TLS đã được thiết lập **trước** LDAP Bind. Cần kiểm tra chứng chỉ máy chủ, tên host và trust chain; khi dùng SASL EXTERNAL còn cần chứng chỉ client và cơ chế mapping phù hợp.

### 3.2. StartTLS: nâng cấp kết nối LDAP thường

```text
Client                       LDAP server :389
  | -------- TCP -----------------> |
  | -- StartTLS ExtendedRequest --> |
  | <---- StartTLS success ------- |
  | <======= TLS handshake ======> |
  |   xác minh server/client cert  |
  |                                |
  | -- LDAP Bind ---------------->  |
  | <-------- Bind result -------- |
  | -- Search / Modify -----------> |
```

Ví dụ URL: `ldap://ldap.example.org:389` kèm thao tác **StartTLS** theo RFC 4511. Với credential cần bảo mật, bắt buộc thành công ở bước StartTLS **trước** khi thực hiện Bind. Nếu server không hỗ trợ nâng cấp, client phải **từ chối** luồng yêu cầu bảo mật, không tự hạ cấp về SIMPLE trên kết nối chưa mã hóa.

| Vấn đề | LDAPS | StartTLS |
|---|---|---|
| TLS được thiết lập | Ngay đầu kết nối | Sau LDAP StartTLS Extended Operation |
| URL thường gặp | `ldaps://...:636` | `ldap://...:389` |
| Có thể dùng SASL EXTERNAL với cert | Có, **nếu server hỗ trợ** | Có, **nếu server hỗ trợ** |
| Có thể dùng SIMPLE qua TLS | Có | Có, **sau khi nâng cấp thành công** |
| Cấu hình Spring LDAP đặc trưng | URL LDAPS hoặc JNDI SSL | `DefaultTlsDirContextAuthenticationStrategy` / `ExternalTlsDirContextAuthenticationStrategy` |

Không kết hợp **`ldaps://` và chiến lược tự gọi StartTLS** chỉ vì muốn “bảo mật gấp đôi”. Chúng là hai cách thiết lập kênh TLS khác nhau; chọn đúng một cách theo endpoint và tài liệu server.

## 4. Điều kiện hạ tầng để SASL EXTERNAL dùng chứng chỉ

Một hệ thống thực sự có thể xác thực LDAP bằng chứng chỉ khi **cả phía Java và phía LDAP server** được chuẩn bị.

### 4.1. Phía Java client

1. Có **chứng chỉ X.509 dành cho client authentication** và private key tương ứng.
2. Private key nằm trong **keystore** bảo vệ, ví dụ PKCS#12, hoặc secret store/HSM tương thích.
3. Có **truststore** chứa CA đáng tin để kiểm tra chứng chỉ server, nếu CA không có sẵn trong truststore mặc định.
4. TLS stack chọn đúng chứng chỉ/client key khi LDAP server yêu cầu; kiểm tra thời hạn, chuỗi tin cậy và chính sách mở rộng *Extended Key Usage* khi cần.
5. Endpoint LDAP có hostname hợp lệ, khớp chứng chỉ máy chủ và đáp ứng yêu cầu phiên bản TLS/cipher suite.
6. Ứng dụng cấu hình **SASL EXTERNAL**, không vô tình gửi SIMPLE Bind username/password.

### 4.2. Phía LDAP server

1. Cấu hình LDAPS hoặc StartTLS và cung cấp **server certificate** hợp lệ.
2. Cấu hình **yêu cầu hoặc chấp nhận client certificate** ở TLS handshake, có trust chain kiểm chứng CA cấp chứng chỉ client.
3. Hỗ trợ cơ chế **SASL EXTERNAL** và cho phép sử dụng nó trên kết nối tương ứng.
4. Có quy tắc **ánh xạ chứng chỉ/Subject DN** sang LDAP authentication/authorization identity được phép.
5. ACL chỉ cấp quyền cần thiết cho danh tính sau ánh xạ.
6. Có quy trình thu hồi/rotation chứng chỉ và theo dõi lỗi TLS/Bind.

Ví dụ với **OpenLDAP**, server cần chính sách `TLSVerifyClient` phù hợp như `try` hoặc `demand` để yêu cầu chứng chỉ; nếu `never`, client thường không được mời trình bày certificate và SASL EXTERNAL dựa trên TLS không xuất hiện. Cách cấu hình cụ thể khác nhau giữa OpenLDAP, Active Directory, 389 Directory Server và sản phẩm thương mại; **không sao chép cấu hình vendor này sang vendor khác**.

Lưu ý: kiểm tra certificate hợp lệ ở TLS có thể thành công nhưng **SASL Bind vẫn thất bại** nếu server không ánh xạ được certificate sang account. Không gộp hai loại lỗi này thành một.

## 5. Chứng chỉ máy chủ, chứng chỉ client, keystore và truststore

Hai nhóm chứng chỉ có mục đích khác nhau:

| Vật liệu | Ai sở hữu? | Dùng để làm gì? | Có private key không? |
|---|---|---|---|
| LDAP **server certificate** | LDAP server | Client xác minh endpoint server | Server có private key của mình |
| **Client certificate** | Ứng dụng Java | Server kiểm tra danh tính TLS client | Java client cần private key tương ứng |
| Java **keystore** (client) | Ứng dụng Java | Chứa private key + certificate chain của client | **Có** |
| Java **truststore** (client) | Ứng dụng Java | Chứa CA/certificate đáng tin để xác minh server | Thông thường **không** chứa client private key |
| Server trust anchors | LDAP server | Xác minh certificate chain của client | Không cần private key của client |

Ví dụ triển khai:

```text
/run/secrets/ldap-client.p12        # PKCS12: PrivateKeyEntry + certificate chain
/etc/ssl/private/ldap-trust.p12     # PKCS12: CA tin cậy của LDAP server
```

Các đường dẫn trên chỉ là ví dụ Linux/container. Trên Windows có thể dùng Windows Certificate Store hoặc cơ chế quản lý bí mật được doanh nghiệp phê duyệt. Không đặt certificate private key trong repository; không in password keystore ra log, trace hay lệnh shell hiển thị trong lịch sử.

JSSE thường đọc các JVM system properties tương tự:

```properties
javax.net.ssl.keyStore=/run/secrets/ldap-client.p12
javax.net.ssl.keyStoreType=PKCS12
javax.net.ssl.trustStore=/etc/ssl/private/ldap-trust.p12
javax.net.ssl.trustStoreType=PKCS12
```

**Lưu ý:** đây là các **JVM system properties**, không phải mặc định là key trong `application.yml` của Spring Boot. Cần thiết lập qua cách khởi chạy JVM/secret manager hoặc qua một `SSLContext`/`SSLSocketFactory` được cấu hình rõ ràng. Password của private key/keystore/truststore phải được cấp bằng cơ chế bí mật an toàn phù hợp; không viết giá trị thật trong tài liệu hoặc source code.

Các system properties JSSE có phạm vi **toàn JVM** theo cách dùng mặc định. Ứng dụng kết nối nhiều LDAP directory/tenant với các chứng chỉ client khác nhau có thể cần `SSLContext` và socket factory riêng, thay vì thay đổi `System.setProperty(...)` ở runtime giữa các request.

**Không tắt hostname verification** và không dùng một `TrustManager` “tin mọi chứng chỉ” để làm test production chạy được. Nếu gặp `PKIX path building failed`, phải sửa trust chain/server certificate; nếu gặp hostname mismatch, sửa URL/SAN/certificate hoặc DNS, không bỏ xác minh tên máy chủ.

## 6. Spring LDAP: StartTLS + SASL EXTERNAL bằng client certificate

Spring LDAP có `DirContextAuthenticationStrategy` cho các trường hợp tạo `DirContext` cần TLS và cơ chế Bind không phải SIMPLE mặc định.

- `DefaultTlsDirContextAuthenticationStrategy`: StartTLS, sau đó **SIMPLE Bind** bằng user DN/password.
- `ExternalTlsDirContextAuthenticationStrategy`: StartTLS, sau đó **SASL EXTERNAL**, dùng danh tính chứng chỉ client đã xác thực tại TLS.

### 6.1. Cấu hình bean chuyên biệt

Ví dụ dưới đây giả định endpoint `ldap://ldap.example.org:389` hỗ trợ StartTLS + SASL EXTERNAL và JVM đã nạp đúng keystore/truststore.

**`CertificateLdapConfiguration.java`**

```java
package com.example.ldap;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.ExternalTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class CertificateLdapConfiguration {

    @Bean("certificateContextSource")
    public LdapContextSource certificateContextSource() {
        LdapContextSource source = new LdapContextSource();

        // StartTLS phải bắt đầu từ ldap://, không phải ldaps://.
        source.setUrl("ldap://ldap.example.org:389");
        source.setBase("dc=example,dc=org");
        source.setAnonymousReadOnly(false);
        source.setPooled(false); // Tắt native JNDI connection pooling.

        source.setAuthenticationStrategy(
                new ExternalTlsDirContextAuthenticationStrategy());

        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "3000",
                "com.sun.jndi.ldap.read.timeout", "5000"));

        // Không set userDn/password của SIMPLE Bind trong ví dụ EXTERNAL.
        // Credential thực tế được cung cấp bởi TLS client certificate.
        return source;
    }

    @Bean("certificateLdapTemplate")
    public LdapTemplate certificateLdapTemplate(
            @Qualifier("certificateContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ứng dụng Spring gọi `afterPropertiesSet()` trong vòng đời bean; nếu tự khởi tạo `LdapContextSource` **ngoài Spring**, phải gọi phương thức khởi tạo cần thiết sau khi đặt thuộc tính.

**Các giả định không thể bỏ qua:**

- `source.setUrl("ldap://...:389")` dùng **StartTLS** do chiến lược thực hiện; nếu server không có StartTLS, việc tạo context phải thất bại.
- Chứng chỉ client/private key nằm trong keystore hoặc TLS socket factory đã cấu hình; Java không tự lấy certificate của LDAP server rồi xem nó là client credential.
- Phải chứng minh server nhận và ánh xạ danh tính từ certificate vào LDAP account với ACL đúng.
- `setPooled(false)` tắt **native JNDI pooling**. Nếu cần context pooling vì lưu lượng cao, dùng cơ chế Spring LDAP pooling phù hợp sau khi kiểm thử vòng đời TLS/context và tránh tái sử dụng sai identity.
- `read.timeout` khác `connect.timeout` và cũng khác giới hạn thời gian một LDAP search; điều chỉnh theo SLO và môi trường.

### 6.2. Dùng LdapTemplate với identity đã được ánh xạ

**`CertificateDirectoryReader.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class CertificateDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public CertificateDirectoryReader(
            @Qualifier("certificateLdapTemplate")
            LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readNameByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            if (cn == null || cn.size() == 0) {
                throw new InvalidAttributeValueException("Thiếu cn");
            }
            return (String) cn.get();
        };

        return ldapTemplate.lookup(dn, mapper);
    }
}
```

Đoạn code chỉ đọc `cn` theo DN tương đối với base `dc=example,dc=org`. Nếu hạ tầng server ánh xạ certificate thành **service account chỉ được đọc `ou=people`**, truy vấn có thể thành công; nếu ACL cấm, nó phải thất bại hoặc không trả đủ thuộc tính theo semantics server. **Không kiểm tra certificate chỉ bằng việc Java bean khởi tạo thành công**; cần chạy một truy vấn có xác nhận danh tính/ACL.

Khi ứng dụng đồng thời cấu hình Spring Boot LDAP auto-configuration, cần bảo đảm **repository và `LdapTemplate` thực sự dùng `certificateContextSource`**, không vô tình dùng một `ContextSource` khác có SIMPLE Bind. Có thể đặt tên bean/`@Qualifier` rõ ràng như ví dụ.

## 7. JNDI thuần: LDAPS + SASL EXTERNAL

Nếu endpoint cung cấp **LDAPS ngay từ đầu**, có thể dùng JNDI với `Context.SECURITY_AUTHENTICATION="EXTERNAL"`. Ví dụ sau sử dụng Java 17 và JSSE system properties đã được cấu hình trước khi chạy.

**`ExternalBindExample.java`**

```java
package com.example.ldap;

import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.ldap.InitialLdapContext;

public final class ExternalBindExample {

    public static void main(String[] args) throws Exception {
        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
                "ldaps://ldap.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "EXTERNAL");
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        // Không đặt Context.SECURITY_PRINCIPAL / SECURITY_CREDENTIALS.
        // Danh tính dùng cho EXTERNAL đến từ TLS/client certificate.
        DirContext context = new InitialLdapContext(env, null);
        try {
            Attributes attrs = context.getAttributes(
                    "uid=lan,ou=people,dc=example,dc=org",
                    new String[] {"cn"});

            Attribute cn = attrs.get("cn");
            System.out.println(
                    cn == null ? "<không đọc được cn>" : cn.get());
        } finally {
            context.close();
        }
    }
}
```

Với `ldaps://`, JNDI mở kênh TLS từ đầu; ví dụ **không gọi StartTLS một lần nữa**. Nếu LDAP server không cấp certificate identity thích hợp hoặc không hỗ trợ EXTERNAL, Bind phải thất bại. Trên một số provider, kết nối không có client certificate có thể dẫn đến hành vi khác mong đợi; **đừng coi việc có `EXTERNAL` trong environment là bằng chứng đã xác thực đúng service account**.

**Khác biệt với code Spring LDAP:** ở JNDI thuần không có `ContextSource.base`, nên ví dụ `getAttributes(...)` dùng **DN đầy đủ**. Với `LdapContextSource.setBase("dc=example,dc=org")`, các lời gọi `LdapTemplate` thường truyền DN **tương đối**.

## 8. SASL GSSAPI: phương án khác cho môi trường Kerberos

SASL GSSAPI dùng Kerberos v5, **không dùng client TLS certificate làm credential chính của cơ chế này**. Nó có thể phù hợp khi hạ tầng doanh nghiệp đã có Kerberos KDC, LDAP service principal và quy trình quản lý keytab/ticket.

```text
Java service
    |
    | JAAS/Kerberos: có Ticket Granting Ticket / service ticket
    v
KDC / Kerberos realm
    |
    | GSSAPI trao đổi token SASL trong LDAP Bind
    v
LDAP server: xác thực principal, ánh xạ identity, áp dụng ACL
```

Trong JNDI:

```java
// Mã minh họa một phần cấu hình, không phải chương trình hoàn chỉnh.
env.put(Context.SECURITY_AUTHENTICATION, "GSSAPI");

// Tùy chính sách backend và provider:
env.put("javax.security.sasl.qop", "auth-int");

// Trước khi tạo context:
// - JAAS/Subject phải có Kerberos credentials thích hợp;
// - DNS, FQDN, SPN ldap/<host>@REALM phải đúng;
// - KDC/time sync và ticket lifetime phải hợp lệ.
```

Các giá trị SASL QOP thường gặp:

| QOP | Ý nghĩa | Lưu ý |
|---|---|---|
| `auth` | Chỉ xác thực | Không tự mã hóa mọi dữ liệu ứng dụng |
| `auth-int` | Xác thực + bảo vệ tính toàn vẹn | Cần provider/server hỗ trợ |
| `auth-conf` | Xác thực + toàn vẹn + bảo mật nội dung | Cần provider/server hỗ trợ |

Khi dùng GSSAPI, nhiều hệ thống vẫn triển khai thêm TLS để xác minh endpoint và đáp ứng chính sách mã hóa. Không dựa vào `auth-int` như thể nó có cùng bảo đảm bí mật với `auth-conf` hoặc TLS. **Không chuyển sang SIMPLE trên TCP rõ** khi Kerberos thất bại.

Đối với ứng dụng dùng Kerberos, phải thiết lập chính xác JAAS, `Subject`/execution context, quản lý keytab/ticket renewal và quy tắc mapping principal của server. Đây là luồng cấu hình khác với `ExternalTlsDirContextAuthenticationStrategy`.

## 9. Ánh xạ chứng chỉ X.509 sang danh tính LDAP

Chứng chỉ client có thể có Subject:

```text
CN=directory-reader,OU=Applications,O=Example Org,C=VN
```

Đó là **X.509 Subject DN**, không nhất thiết chính là DN entry trong directory:

```text
X.509 Subject DN:
  CN=directory-reader,OU=Applications,O=Example Org,C=VN

LDAP authorization identity có thể được ánh xạ thành:
  cn=directory-reader,ou=service,dc=example,dc=org
```

Ở OpenLDAP, SASL EXTERNAL lấy thông tin identity từ kết nối đã xác thực; cơ chế **authz-regexp** hoặc cấu hình mapping tương ứng có thể chuyển authentication identity thành LDAP authorization DN. Sản phẩm LDAP khác có thể ánh xạ bằng SAN, Subject, issuer, certificate mapping rules hoặc thuộc tính tài khoản.

**Cần thiết kế mapping chặt chẽ:**

1. Một chứng chỉ service phải tương ứng **đúng danh tính ứng dụng** được phép.
2. Kiểm chứng CA, mục đích certificate, thời hạn và chính sách thu hồi theo PKI của tổ chức.
3. Không coi “có chữ `CN=admin`” trong Subject là đủ quyền admin.
4. Không dùng một quy tắc mapping quá rộng làm nhiều chứng chỉ khác nhau cùng thành account đặc quyền.
5. Nếu dùng nhiều tenant/directory, bảo đảm mapping xác định đúng phạm vi và tránh cấp quyền chéo.
6. Kiểm tra **authorization identity thực tế** sau Bind, không suy luận từ client keystore alias.

Ví dụ nếu mapping đưa service thành `cn=directory-reader,ou=service,dc=example,dc=org`, ACL nên chỉ cho phép đọc các thuộc tính danh bạ phục vụ ứng dụng. Việc đổi email, xóa người dùng hoặc quản lý `groupOfNames.member` phải sử dụng service identity có quyền phù hợp hoặc bị từ chối theo chính sách.

**Phân biệt ba tên:** X.509 Subject DN, LDAP entry DN và DN truyền cho `LdapTemplate.lookup(...)` có thể đều là chuỗi trông giống DN, nhưng **không đại diện cho cùng một thực thể**.

## 10. Kiểm tra từ ngoài ứng dụng trước khi tích hợp Spring

Trước khi sửa cấu hình Spring Boot, kiểm tra endpoint/server bằng công cụ LDAP của hạ tầng. Ví dụ cho **OpenLDAP client tools** trên Linux:

```bash
# Cấu hình file PEM client cert/key cho ldap-utils, không phải Java PKCS12.
export LDAPTLS_CACERT=/etc/ldap/tls/ldap-ca.pem
export LDAPTLS_CERT=/run/secrets/ldap-client.pem
export LDAPTLS_KEY=/run/secrets/ldap-client.key

# StartTLS bắt buộc (-ZZ), rồi SASL EXTERNAL:
ldapwhoami -H ldap://ldap.example.org:389 -ZZ -Y EXTERNAL

# Hoặc LDAPS ngay từ đầu:
ldapwhoami -H ldaps://ldap.example.org:636 -Y EXTERNAL

# Tra cứu một entry chỉ đọc sau khi bind thành công:
ldapsearch -LLL \
  -H ldap://ldap.example.org:389 -ZZ -Y EXTERNAL \
  -b "ou=people,dc=example,dc=org" \
  -s one "(uid=lan)" dn cn
```

Các lệnh giả định đã cài LDAP client tools và certificate files được cấp quyền truy cập phù hợp. Thư viện Java **không tự đọc** các biến `LDAPTLS_CERT`/`LDAPTLS_KEY` của OpenLDAP tools; Java dùng JSSE keystore/truststore hoặc TLS socket factory theo cấu hình riêng.

Khi xác thực thành công, `ldapwhoami` có thể hiển thị authz identity thực tế; đối chiếu với account và ACL mong đợi. Nếu Bind thất bại ngay khi thiếu cert, đó là tín hiệu quan trọng để xác minh chính sách server — **không sửa bằng cách bật anonymous read hoặc tắt kiểm tra certificate**.

Nếu directory là sản phẩm khác OpenLDAP, sử dụng CLI và hướng dẫn tương ứng. Không mặc định mọi server hiển thị danh tính hoặc hỗ trợ SASL EXTERNAL theo đúng cấu trúc của OpenLDAP.

## 11. Pooling, vòng đời TLS và xác thực người dùng cuối

### 11.1. Không bật native JNDI pooling tùy tiện với StartTLS

Spring LDAP khuyến nghị **tắt native LDAP pooling** khi dùng các `TlsDirContextAuthenticationStrategy`. Cơ chế StartTLS thay đổi trạng thái kênh và quản lý đóng TLS có các yêu cầu riêng; dùng pooling sai có thể tái sử dụng kết nối không đúng trạng thái hoặc khó kiểm soát.

```java
source.setPooled(false);
source.setAuthenticationStrategy(
        new ExternalTlsDirContextAuthenticationStrategy());
```

Nếu tải cao, có thể xem xét **Spring LDAP pooling support** (Commons Pool 2) theo phiên bản và khả năng tương thích. Cần quan sát context active/idle/waiters, thời gian mượn context, lỗi kết nối/TLS, thời hạn certificate và cách trả context về pool. Không trộn native pooling với Spring pool một cách ngẫu nhiên.

### 11.2. Không tái sử dụng service certificate như xác thực end user

Có hai bài toán khác nhau:

- **Service-to-directory:** Spring ứng dụng dùng certificate service account để đọc/ghi entry theo ACL được cấp.
- **User authentication:** chứng minh người dùng cuối có credential tương ứng với tài khoản của họ.

Một `LdapTemplate.lookup(...)` dùng service certificate thành công **không xác minh password của người dùng cuối**. Khi ứng dụng cho phép người dùng đăng nhập bằng mật khẩu, cần một luồng xác thực riêng (ví dụ bind user theo mô hình được phê duyệt) hoặc giải pháp identity provider/SSO. Không coi `ldapTemplate.authenticate(...)` hoặc pool service certificate là cách tự động “nhập vai” từng user.

Nếu có nhiều service identity/certificate, chọn đúng identity cho từng loại nghiệp vụ; tránh chia sẻ một context đã xác thực với quyền admin cho mọi request do người dùng cuối điều khiển.

## 12. Bảo mật trong vòng đời chứng chỉ và kết nối

| Rủi ro | Biện pháp |
|---|---|
| Keystore chứa private key bị lộ | Secret manager/HSM, mount read-only, quyền file tối thiểu, không commit lên Git |
| Mật khẩu keystore xuất hiện trong shell history/log | Cấp secret qua cơ chế runtime an toàn, không hard-code/print |
| Server certificate không hợp lệ | Duy trì trust chain và hostname verification, không sử dụng `trustAll` |
| Certificate client hết hạn | Giám sát hạn sử dụng và kế hoạch rotation trước khi hết hạn |
| Certificate bị thu hồi nhưng vẫn được dùng | Áp dụng chính sách revocation/CRL/OCSP theo khả năng PKI và LDAP server |
| Mapping certificate quá rộng | Quy tắc identity mapping rõ ràng, ACL least privilege và kiểm thử negative cases |
| StartTLS thất bại rồi tự gửi SIMPLE Bind | **Fail closed**, không downgrade sang cleartext |
| Sai endpoint/referral sang host khác | Allowlist, xác minh TLS hostname/CA và credential forwarding policy |
| Dùng certificate vừa rotate nhưng pool giữ connection cũ | Thiết kế restart/rebuild TLS context và drain connection an toàn |
| LDAP log chứa password, certificate private key hoặc thông tin user | Sanitize log, không ghi TLS key material/filter có dữ liệu cá nhân |

**Rotation:** thay file keystore dưới cùng đường dẫn không nhất thiết làm các connection hoặc `SSLContext` đã được tạo **nạp lại chứng chỉ mới**. Tùy cơ chế TLS, cần tái khởi tạo bean/SSLContext, drain pool hoặc rolling restart. Thiết kế quá trình này trước khi certificate gần hết hạn.

**TLS policy:** dùng phiên bản giao thức và cipher suite được bảo trì (thường TLS 1.2/1.3 theo quy định tổ chức), kiểm tra SAN/hostname và chuỗi tin cậy. Không bật giao thức/cipher cũ chỉ để tương thích mà chưa đánh giá rủi ro.

## 13. Kiểm thử tích hợp: xác thực thành công lẫn thất bại

Không thể chứng minh cơ chế EXTERNAL bằng unit test chỉ mock `LdapTemplate`. Cần LDAP directory test hoặc môi trường staging có endpoint TLS, certificate authority, client certificate, mapping và ACL tương đương production.

### 13.1. Dữ liệu và danh tính giả lập

Ví dụ test:

```text
LDAP endpoint:
  ldap://ldap-test.example.org:389 + StartTLS

Service certificate:
  Subject CN=directory-reader,OU=Applications,O=Example Org

Expected mapped LDAP identity:
  cn=directory-reader,ou=service,dc=example,dc=org

Test entry:
  uid=lan,ou=people,dc=example,dc=org
  objectClass=inetOrgPerson
  uid=lan
  cn=Lan Nguyen
  sn=Nguyen
```

```java
// PSEUDOCODE tích hợp (cần môi trường TLS/LDAP thật):
// 1. Tạo ContextSource với ExternalTlsDirContextAuthenticationStrategy.
// 2. Lấy context -> StartTLS thành công -> EXTERNAL Bind thành công.
// 3. Thực hiện read CN của uid=lan bằng LdapTemplate.
// 4. Xác minh identity đã bind (ldapwhoami/server audit).
// 5. Thử một thao tác mà reader KHÔNG được phép ghi:
//    LDAP server phải từ chối theo ACL, không ghi dữ liệu.
```

### 13.2. Ma trận trường hợp cần kiểm chứng

| Tình huống | Kết quả mong đợi |
|---|---|
| Cert client hợp lệ, mapping đúng, đủ ACL đọc | Bind EXTERNAL thành công; đọc đúng thuộc tính được phép |
| Không cung cấp client certificate | Luồng yêu cầu cert không được xác thực thành service identity |
| Client certificate hết hạn/không được tin cậy | TLS hoặc Bind thất bại theo chính sách server |
| Client certificate hợp lệ nhưng không có mapping | Không tự có quyền của tài khoản khác; lỗi xác thực/authorization rõ ràng |
| Mapping thành reader nhưng cố ghi nhóm admin | Server từ chối theo ACL |
| Server certificate do CA lạ cấp | Java từ chối trust chain; không dùng trust-all |
| Server certificate có SAN không khớp hostname | Java từ chối hoặc test phát hiện sai cấu hình; không tắt endpoint identification |
| Server không hỗ trợ StartTLS | Kết nối bắt buộc TLS thất bại; không gửi credential trên cleartext |
| Server hỗ trợ TLS nhưng không hỗ trợ EXTERNAL | EXTERNAL Bind thất bại; không tự fallback sang SIMPLE |
| TLS được thiết lập nhưng certificate client không được gửi | Phát hiện cấu hình key material/server request sai |
| Native pooling bật nhầm khi StartTLS | Test config fail hoặc sửa về `setPooled(false)` |
| Cert rotation khi nhiều context còn sống | Kết nối mới dùng credential mới; không kéo dài dùng cert cũ vô hạn |
| GSSAPI thiếu ticket, SPN hoặc lệch giờ | Bind thất bại có nguyên nhân Kerberos riêng, không nhầm lỗi cert |
| Referral sang host khác | Không gửi credential/certificate ra endpoint chưa được cho phép |

Các trường hợp tiêu cực nên có **assertion về danh tính và ACL thực tế**, không chỉ `assertThrows(Exception.class)`. Với test có thao tác ghi, dùng naming context riêng và tài khoản có quyền giới hạn; không chạy test ghi/xóa trên directory production.

### 13.3. Kiểm thử cấu hình Spring

Một số test tự động nên kiểm tra:

```java
// PSEUDOCODE JUnit/Spring:
// assertSame(certificateContextSource,
//            beanFactory.getBean("certificateContextSource"));
// assertFalse(certificateContextSource.isPooled());
// assertEquals("dc=example,dc=org",
//              certificateContextSource.getBaseLdapPathAsString());
// Integration test cần mở TLS và bind thật;
// kiểm tra bean bằng reflection/config KHÔNG chứng minh xác thực thành công.
```

Khi có nhiều `ContextSource` trong một ứng dụng, cần xác minh repository của Spring Data LDAP thực sự được kết nối với bean đúng. Nếu không, một bài test `LdapTemplate` có certificate thành công vẫn chưa chứng minh code repository đang dùng EXTERNAL thay vì credential khác.

## 14. Chẩn đoán lỗi theo từng lớp

| Triệu chứng | Nguyên nhân cần xem | Hướng xử lý |
|---|---|---|
| `SSLHandshakeException`, `PKIX path building failed` | Client không tin CA/server certificate chain | Cài đúng CA trong truststore, kiểm tra chain và thời hạn |
| Hostname mismatch | URL endpoint khác SAN của server cert | Sửa DNS/SAN/URL, không tắt verification |
| TLS handshake đòi client cert nhưng không có | Keystore thiếu `PrivateKeyEntry`, alias sai, server yêu cầu cert khác | Kiểm tra private key, certificate chain, TLS client auth policy |
| `AuthenticationNotSupportedException` / unsupported mechanism | Server không quảng bá/cho phép EXTERNAL hoặc GSSAPI | Kiểm tra `supportedSASLMechanisms`, chính sách server sau TLS |
| TLS thành công nhưng `invalidCredentials (49)` hoặc Bind lỗi | Mapping certificate, account, SASL policy sai | Kiểm tra authc/authz mapping và audit phía server |
| Bind thành công nhưng search rỗng/bị từ chối | ACL, base DN, scope, filter hoặc thuộc tính thiếu quyền | Kiểm tra quyền và DN, không suy ra cert lỗi |
| StartTLS strategy dùng với `ldaps://` | Nhầm hai cơ chế TLS | Dùng `ldap://` cho StartTLS strategy hoặc JNDI LDAPS thuần |
| SASL GSSAPI báo thiếu credential | JAAS/`Subject`/keytab/ticket sai | Kiểm tra Kerberos login, SPN, KDC, clock skew |
| Mỗi lần restart phải sửa keystore path | Chứng chỉ/secret chưa được mount hoặc cấu hình runtime sai | Chuẩn hóa secret provisioning, startup validation |
| Sau rotation vẫn thấy client cert cũ | SSLContext/connection pool chưa refresh | Drain/recreate TLS contexts, rolling restart |
| Một user đăng nhập thành công chỉ vì service cert đọc được entry | Nhầm service-to-directory với user authentication | Dùng luồng xác thực người dùng riêng |

Tại bước điều tra, ưu tiên log **phase** và **error category**:

```text
event=ldap_connect_failed phase=tls_handshake reason=untrusted_server_cert
event=ldap_bind_failed phase=sasl_external reason=identity_mapping
event=ldap_operation_denied phase=search reason=insufficient_access
```

Đây là ví dụ cách đặt tên sự kiện, **không phải log thực tế của một sản phẩm LDAP**. Không log private key, password, mã token Kerberos hoặc dữ liệu attribute nhạy cảm; DN người dùng và Subject certificate có thể là dữ liệu cá nhân nên cần kiểm soát mức log.

## 15. Checklist triển khai production

Trước khi bật xác thực bằng certificate:

1. **Chọn cơ chế có thật:** xác nhận LDAP server hỗ trợ StartTLS/LDAPS, yêu cầu client cert và SASL EXTERNAL; hoặc chọn GSSAPI nếu tổ chức dùng Kerberos.
2. **Chuẩn hóa trust:** xác minh CA, SAN/hostname, certificate chain, thời hạn, revocation và chính sách TLS.
3. **Bảo vệ private key:** dùng secret store, file permission tối thiểu, không commit keystore hoặc mật khẩu.
4. **Kiểm tra mapped identity:** biết chính xác sau Bind server cấp authzID nào và ACL cho phép gì.
5. **Fail closed:** nếu TLS hoặc SASL EXTERNAL thất bại, không tự hạ cấp sang SIMPLE không mã hóa hoặc anonymous.
6. **Tách vai trò:** certificate service dùng cho service-to-directory, không tự chứng minh người dùng cuối.
7. **Kiểm soát pooling:** tắt native pooling với StartTLS strategy và kiểm thử context lifecycle khi cần Spring pooling.
8. **Giới hạn kết nối:** connect/read timeout, search scope và projection phù hợp; không cấp quyền đọc/ghi toàn directory ngoài nhu cầu.
9. **Kiểm thử chứng chỉ và ACL:** cả happy path lẫn cert sai, không mapping, thiếu quyền, rotation và failover.
10. **Quan sát vận hành:** latency handshake/bind/search, tỷ lệ thất bại theo lớp lỗi và thời hạn cert — không đưa credential vào metrics/logs.

## 16. Câu hỏi tự đánh giá

1. TLS server authentication, TLS client authentication, LDAP Bind và ACL khác nhau thế nào?
2. Vì sao chỉ đổi `ldap://` sang `ldaps://` không làm LDAP tự chuyển từ SIMPLE sang SASL EXTERNAL?
3. SASL EXTERNAL dùng danh tính từ đâu? Khi nào nó không dựa vào chứng chỉ TLS?
4. `DefaultTlsDirContextAuthenticationStrategy` và `ExternalTlsDirContextAuthenticationStrategy` khác nhau ở bước xác thực nào?
5. Vì sao StartTLS phải thành công **trước** khi gửi SIMPLE Bind credential?
6. Keystore chứa private key của ai, còn truststore chứa CA để xác minh ai?
7. Một client certificate hợp lệ nhưng không có identity mapping trên LDAP server sẽ gây vấn đề gì?
8. Vì sao X.509 Subject DN có thể khác LDAP authorization DN và DN của entry cần `lookup`?
9. SASL GSSAPI cần hạ tầng nào? Nó có bắt buộc dùng client X.509 certificate không?
10. Khi kết nối LDAP dùng StartTLS, tại sao cần tránh native JNDI pooling nếu chưa có thiết kế cụ thể?
11. Vì sao `LdapTemplate.lookup` bằng service certificate thành công không chứng minh người dùng cuối đã đăng nhập?
12. Nên phản ứng thế nào nếu server certificate không được tin cậy hoặc server không hỗ trợ SASL EXTERNAL?

**Ghi nhớ:** xác thực bằng chứng chỉ chỉ khả thi khi **LDAP server yêu cầu/kiểm tra client X.509 certificate, hỗ trợ SASL EXTERNAL và ánh xạ danh tính đó đến ACL phù hợp**. Spring LDAP hỗ trợ `ExternalTlsDirContextAuthenticationStrategy` cho StartTLS + EXTERNAL; JNDI cũng có thể dùng `EXTERNAL` trên LDAPS. Với Kerberos, `GSSAPI` là cơ chế SASL khác. TLS bảo vệ kênh, SASL/Bind xác lập danh tính, còn LDAP ACL quyết định quyền. Không đánh đổi an toàn bằng cách tắt kiểm chứng TLS, dùng fallback rõ dữ liệu hoặc chia sẻ credential sai vai trò.

### Tài liệu tham khảo

- IETF [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): các cơ chế LDAP Bind, sử dụng SASL và bảo mật kênh.
- IETF [RFC 4422 — Simple Authentication and Security Layer (SASL)](https://www.rfc-editor.org/rfc/rfc4422): khung cơ chế SASL, authentication/authorization identity và EXTERNAL.
- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Bind, StartTLS Extended Operation và kết quả giao thức.
- Spring LDAP Reference — [Configuration: TLS / Authentication Strategies](https://docs.spring.io/spring-ldap/reference/configuration.html): `DefaultTlsDirContextAuthenticationStrategy`, `ExternalTlsDirContextAuthenticationStrategy` và cảnh báo native pooling.
- Spring LDAP API — [`ExternalTlsDirContextAuthenticationStrategy`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/ExternalTlsDirContextAuthenticationStrategy.html), [`AbstractContextSource`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html).
- Oracle Java JNDI — [SSL and Custom Sockets](https://docs.oracle.com/javase/tutorial/jndi/ldap/ssl.html): LDAPS, TLS client certificate và SASL EXTERNAL.
- Oracle — [Java SASL API Programming and Deployment Guide](https://docs.oracle.com/en/java/javase/12/security/java-sasl-api-programming-and-deployment-guide1.html): GSSAPI, Kerberos, JAAS và SASL QOP.
- OpenLDAP — [Administrator's Guide: Using SASL](https://openldap.com/doc/admin25/sasl.html): SASL EXTERNAL, danh tính certificate và `ldapi`.
- OpenLDAP — [Administrator's Guide: Using TLS](https://directory.openldap.org/doc/admin26/guide.html): TLS client certificate, `TLSVerifyClient` và yêu cầu server.
