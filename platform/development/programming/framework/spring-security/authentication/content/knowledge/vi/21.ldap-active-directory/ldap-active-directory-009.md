# LDAPS, bí mật kết nối, timeout và phân biệt lỗi tài khoản với lỗi hạ tầng

> **Phạm vi:** Xác thực người dùng qua LDAP hoặc Active Directory (AD) trong ứng dụng Spring Security. Trọng tâm là bảo vệ kênh kết nối đến directory, giữ an toàn thông tin bí mật, đặt timeout hữu hiệu và phân biệt **thông tin đăng nhập/tình trạng tài khoản không hợp lệ** với **sự cố LDAP/AD, mạng, TLS hoặc cấu hình**. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x và JNDI LDAP provider của JDK; khi dùng phiên bản khác phải kiểm tra lại API và cấu hình tương ứng.

## 1. Kết quả cần đạt và luồng xác thực

Sau bài này, bạn cần có khả năng:

1. Giải thích sự khác nhau giữa **LDAPS** (LDAP trên TLS ngay khi kết nối) và **StartTLS** (nâng cấp kết nối LDAP sang TLS trước khi gửi bí mật); xác minh certificate chain, hostname và truststore.
2. Phân biệt mật khẩu người dùng với credentials của **service/bind account** dùng để tra cứu; thiết kế lưu trữ, phân quyền, luân chuyển và kiểm soát log cho từng loại.
3. Đặt được **connect timeout**, **read timeout** của JNDI và ngân sách thời gian toàn request; phát hiện các điểm còn có thể chờ vô hạn.
4. Nhận biết LDAP result code, AD subcode, exception Spring Security và nguyên nhân từ hạ tầng mà không trả chi tiết nhạy cảm cho người đăng nhập.
5. Thực hành kiểm tra thành công, sai mật khẩu, tài khoản bị khóa, LDAP không sẵn sàng, sai chứng chỉ, chậm kết nối và đứt dịch vụ theo hướng **fail closed**.

Một luồng xác thực bind phổ biến:

~~~text
Client --HTTPS--> Ứng dụng Spring Security
                      |
                      v
             AuthenticationManager
                      |
           [tra cứu DN người dùng] ----(có thể dùng service account)---> LDAP/AD
                      |
           [bind bằng username + password người dùng] -----------------> LDAP/AD
                      |
           [đọc nhóm/quyền nếu cần] -----------------------------------> LDAP/AD
                      |
           kết quả -> Authentication thành công | từ chối | lỗi dịch vụ
                      |
          Chỉ tạo session/token khi đủ điều kiện xác thực
~~~

**Hai loại bí mật không đồng nhất:** Password người dùng được gửi theo từng lần xác thực để bind; password của service account chỉ dùng cho thao tác mà service account được cấp phép (như tìm kiếm người dùng, nhóm). Với chiến lược DN pattern cố định, có thể không cần service account để tìm DN. AD có thể dùng UPN (`user@domain`) để bind trực tiếp. Không lưu password người dùng vào cơ sở dữ liệu hay log của ứng dụng sau khi xác thực.

## 2. LDAPS và StartTLS bảo vệ điều gì?

| Phương án | Khởi tạo kênh | Cổng thường gặp | Điều kiện an toàn |
| --- | --- | --- | --- |
| LDAPS | TLS handshake trước, rồi trao đổi LDAP qua kênh TLS | TCP 636 (hoặc cổng do hệ thống đặt) | Chứng chỉ máy chủ hợp lệ, chuỗi tin cậy và tên host khớp, cấu hình TLS hiện đại |
| LDAP + StartTLS | Kết nối LDAP ban đầu rồi thực hiện StartTLS **trước** SIMPLE bind/search nhạy cảm | TCP 389 | Bắt buộc nâng cấp thành công, không fallback sang cleartext, xác minh chứng chỉ đầy đủ |
| LDAP không mã hóa | Trao đổi LDAP trên kênh không có TLS | TCP 389 | **Không dùng cho SIMPLE bind có mật khẩu** trên mạng tin cậy hoặc không tin cậy |

LDAPS là lựa chọn thực tế khi hệ thống hỗ trợ cổng TLS riêng. StartTLS cũng có thể đáp ứng yêu cầu bảo mật nếu được cấu hình đúng và **từ chối hẳn kết nối nếu nâng cấp TLS thất bại**. Đổi `ldap://` thành `ldaps://` là bước đầu tiên, chưa đủ nếu ứng dụng bỏ qua xác minh chứng chỉ.

Sự bảo vệ do TLS cung cấp gồm tính bí mật và toàn vẹn dữ liệu truyền trên mạng, đồng thời xác thực danh tính máy chủ theo chuỗi tin cậy và hostname. TLS **không** mã hóa bí mật lưu trong cấu hình, không ngăn ứng dụng tự ghi password ra log và không thay thế giới hạn quyền service account.

### Vì sao cần kiểm tra hostname?

Giả sử cấu hình:

~~~text
ldaps://dc01.corp.example.test:636
~~~

Chứng chỉ của DC phải có định danh DNS phù hợp với `dc01.corp.example.test` (thường ở Subject Alternative Name), còn CA phát hành hoặc CA trung gian phù hợp phải được truststore JVM tin cậy. Dùng địa chỉ IP khi certificate chỉ cấp cho DNS name có thể dẫn tới lỗi hostname verification.

Trên JDK hiện đại, LDAPS endpoint identification được bật theo mặc định. **Không chữa lỗi bằng cách tắt endpoint identification**, cài TrustManager luôn tin cậy mọi chứng chỉ, hạ cấp xuống `ldap://` hoặc cho phép fallback sang plain LDAP. Cách khắc phục đúng là cấp/chọn chứng chỉ, hostname, CA chain và truststore phù hợp.

Một số môi trường AD còn sử dụng cổng Global Catalog TLS (thường là 3269) để tìm kiếm xuyên domain. Cần chọn endpoint theo thiết kế AD của tổ chức; không thay máy chủ 636 bằng 3269 chỉ dựa vào số cổng.

## 3. Truststore, chứng chỉ và kiểm tra kết nối

**Kiểm tra theo lớp:**

1. **DNS và network:** ứng dụng phân giải đúng FQDN, kết nối TCP đến endpoint/cổng đã duyệt; firewall và Network Policy cho phép.
2. **TLS:** server trình certificate chain đầy đủ, chưa hết hạn, thuật toán/protocol được hỗ trợ, hostname khớp; JVM tin đúng CA.
3. **LDAP bind:** service account hoặc user có thể bind theo cơ chế đã chọn; quyền tìm kiếm/đọc thuộc tính đủ dùng.
4. **Ứng dụng:** filter tìm người dùng, base DN và group mapping đúng; Spring Security nhận principal/authorities dự kiến.

Có thể dùng lệnh sau từ **máy hoặc container có đường mạng tương đương môi trường ứng dụng** để xem handshake và certificate chain:

~~~bash
openssl s_client -connect dc01.corp.example.test:636 -servername dc01.corp.example.test -showcerts
~~~

Lệnh này hữu ích để quan sát certificate chain và TLS ở phía máy chạy lệnh; nó **không chứng minh** truststore Java đã tin CA, không thực hiện LDAP bind, cũng không thay thế kiểm thử danh tính endpoint bên trong ứng dụng. Nếu dùng truststore riêng, cấu hình đường dẫn/loại truststore và password qua cơ chế secret của runtime, đồng thời kiểm tra CA trung gian và kế hoạch xoay chứng chỉ. Ưu tiên quản lý tin cậy từ CA đã phê duyệt hơn nhập tùy tiện một chứng chỉ leaf không có quy trình gia hạn.

**Cảnh báo khi dùng failover:** Mọi DC trong danh sách endpoint cần có certificate hợp lệ với hostname tương ứng. Việc DC thứ nhất có TLS đúng không đảm bảo DC dự phòng cũng đúng. Khi đi qua load balancer hoặc proxy TLS, cần xác định bên nào kết thúc TLS và có TLS đến backend hay không.

## 4. Quản lý bí mật kết nối

Trong LDAP/AD, cần lập danh mục bí mật riêng cho hai nhóm:

| Nhóm | Ai sử dụng | Chính sách tối thiểu |
| --- | --- | --- |
| **Service/bind account** | Ứng dụng để search DN, đọc nhóm/quyền theo chính sách | Chỉ có quyền đọc đúng OU/thuộc tính cần thiết; không dùng tài khoản Domain Admin; bí mật trong secret manager, Vault hoặc cơ chế cấp phát bảo mật; có kế hoạch rotate |
| **User password** | LDAP/AD xác minh ở lần đăng nhập | Chỉ nhận qua HTTPS; dùng để bind trên kênh TLS đã xác minh; không cache bừa bãi, không ghi log/metric/exception, không đưa vào URL |
| **Truststore/key material** | JVM/LDAP client hoặc client certificate nếu mutual TLS | File và password được cấp quyền đọc tối thiểu; quản lý CA, expiry và rotation; phân biệt truststore (tin server) với keystore (giữ private key) |

Các sai lầm thường gặp:

- Commit secret vào `application.yml`, `application.properties`, file test, README, Dockerfile, lịch sử Git hoặc ảnh chụp màn hình.
- Để password trong tham số dòng lệnh (`-D...password=...`) và log toàn bộ command line; nhiều môi trường cho phép xem process arguments.
- Dùng account đặc quyền cao để “dễ kết nối”, bỏ qua yêu cầu rotate, tái sử dụng một password giữa staging và production.
- Đưa `Authentication`, LDAP `DirContext` hoặc exception chứa credentials vào structured log; bật JNDI/LDAP trace để chạy production không giới hạn.
- Nhầm lỗi **service account hết hạn/khóa** thành “mật khẩu người dùng sai”, gây cảnh báo giả và khóa nhầm tài khoản người dùng.

Cấu hình có thể được cung cấp qua hệ thống quản lý secret và cơ chế cấu hình ngoài của Spring Boot. Ví dụ đặt các thuộc tính logic `app.ldap.url`, `app.ldap.base`, `app.ldap.bind-dn` và `app.ldap.bind-password`. Với biến môi trường, Spring Boot hỗ trợ dạng `APP_LDAP_URL`, `APP_LDAP_BASE`, `APP_LDAP_BIND_DN`, `APP_LDAP_BIND_PASSWORD` theo cơ chế ánh xạ cấu hình; chỉ cấp secret vào runtime. **Không chép giá trị secret vào ví dụ hoặc biến môi trường của shell dùng chung.**

Khi rotate password service account, kiểm tra liệu ứng dụng/connection pool đang giữ credentials cũ hay không. Có thể cần reload bean/connection hoặc triển khai rolling restart đúng cách; chạy test bind bằng credentials mới, giám sát tỷ lệ lỗi sau rotate, rồi thu hồi credential cũ. Đừng ghi lại giá trị cũ trong ticket để debug.

## 5. Timeout: connect, read và toàn bộ request là ba lớp khác nhau

JNDI LDAP provider trong JDK có hai thuộc tính môi trường quan trọng:

| Thuộc tính JNDI | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | Giới hạn thời gian thiết lập kết nối LDAP (và có thể thời gian chờ lấy pooled connection) | `"2000"` = 2.000 ms |
| `com.sun.jndi.ldap.read.timeout` | Giới hạn thời gian chờ response cho thao tác LDAP sau khi đã kết nối | `"3000"` = 3.000 ms |

Giá trị là **chuỗi biểu diễn số nguyên mili giây**, không phải `Duration`. Trên JNDI provider mặc định, giá trị không có hoặc bằng/nhỏ hơn 0 có thể cho phép chờ theo timeout TCP hoặc chờ đọc không giới hạn. Đặt giá trị dương và kiểm chứng bằng thử nghiệm mất mạng thực tế.

Ví dụ một lời gọi xác thực thực hiện DNS/TCP/TLS, bind dịch vụ, search DN, bind người dùng, lấy groups, rồi trả response. Giới hạn `connect=2s` và `read=3s` **không đảm bảo** tổng login sẽ nhỏ hơn 5 giây:

- Một lượt đăng nhập có **nhiều LDAP operation**; thời gian chờ từng operation có thể cộng dồn.
- Nhiều LDAP URL dự phòng, referrals hoặc retries có thể lặp lại các kết nối.
- Chờ queue/thread pool, DNS, TLS handshake hoặc backend chậm có thể làm vượt ngân sách quan sát ở cấp HTTP.
- Một client gọi dịch vụ nội bộ khác trước/sau LDAP cũng cần ngân sách riêng.

Hãy bắt đầu từ **deadline toàn request** (ví dụ 5 giây theo SLA minh họa), phân bổ thời gian cho các bước thực tế theo đo đạc, rồi đặt timeout client/driver sao cho không để một operation chiếm toàn bộ thời gian cho phép. Khi timeout, **không trả Authentication thành công** và không biến `CommunicationException` thành `BadCredentialsException` chỉ để giữ mã HTTP 401.

**Sử dụng Java reactive:** Nếu LDAP/JNDI client đồng bộ đang nằm trong WebFlux, cách bọc trong `Mono` chỉ thay kiểu API. I/O vẫn blocking; cần cô lập khỏi event-loop, có scheduler/pool phù hợp và vẫn phải đặt connect/read timeout ngay tại JNDI. Tín hiệu cancellation/`Mono.timeout` không bảo đảm ngắt được mọi lời gọi I/O cũ. Trong ứng dụng Servlet, thread xử lý request cũng có thể bị giữ cho đến khi timeout.

## 6. Cấu hình Spring Security LDAP với LDAPS và timeout

Ví dụ sau giả sử directory dạng LDAP có user nằm dưới `ou=people` với thuộc tính đăng nhập `uid`. Cấu hình sử dụng **service account chỉ đọc** để search và sau đó **bind dưới danh tính người dùng** để xác minh password.

Dependencies phù hợp cho dự án Spring Boot Servlet dùng Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-ldap'
}
~~~

Spring Boot BOM quản lý version các dependency tương thích. Nếu ứng dụng đã có web stack, không thêm một stack thứ hai chỉ vì ví dụ này.

~~~java
package demo.ldap;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
public class LdapAuthenticationConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(Environment properties) {
        String url = properties.getRequiredProperty("app.ldap.url");

        if (!url.startsWith("ldaps://")) {
            throw new IllegalArgumentException("LDAPS endpoint is required");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(properties.getRequiredProperty("app.ldap.base"));
        source.setUserDn(properties.getRequiredProperty("app.ldap.bind-dn"));
        source.setPassword(properties.getRequiredProperty("app.ldap.bind-password"));
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.<String, Object>of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "3000"
        ));
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource ldapContextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(ldapContextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }
}
~~~

Ví dụ cấu hình, dùng với địa chỉ và DN phù hợp directory của bạn:

~~~text
app.ldap.url              = ldaps://ldap01.corp.example.test:636
app.ldap.base             = dc=corp,dc=example,dc=test
app.ldap.bind-dn          = uid=svc-search,ou=service,dc=corp,dc=example,dc=test
app.ldap.bind-password    = [được secret manager cấp vào runtime]
~~~

Phần `[được secret manager cấp vào runtime]` là **chú thích** để phân biệt loại dữ liệu, không phải giá trị cấu hình đưa vào file thực tế. Có thể cấp bằng environment/secret mounting, bảo đảm runtime đọc được đúng property. Các số timeout minh họa phải được điều chỉnh theo mạng, SLA, số operation và kiểm thử tải.

Giải thích:

- `LdapContextSource` là nguồn tạo các LDAP context; các thuộc tính JNDI được áp dụng khi tạo kết nối.
- `setUserDn`/`setPassword` cấu hình service bind để tìm user; phần xác thực người dùng dùng username/password đi vào `AuthenticationManager` khi thực hiện user bind. Hạn chế ACL của service account.
- `factory.setUserSearchFilter("(uid={0})")` tìm user bằng tham số được Spring xử lý trong filter template. Đừng tự nối username chưa escape vào LDAP filter. Với AD, filter, base DN và kiểu login thường khác.
- `setPooled(false)` ở ví dụ giúp tránh giả định dùng native JNDI pooling cho các ngữ cảnh nhạy cảm; trong ứng dụng có tải cao cần thiết kế pool cụ thể, có giám sát và kiểm tra cách xử lý credentials/context.
- Các bean này **không phải một ứng dụng độc lập có `main`**; cần dự án Spring Boot có dependencies, property thực, CA trust hợp lệ, SecurityFilterChain/đường đăng nhập được cấu hình đúng và directory có thể kết nối.

**Lưu ý với StartTLS:** Cấu hình trên dùng `ldaps://`, **không** triển khai StartTLS. Nếu yêu cầu dùng StartTLS, phải dùng `DirContextAuthenticationStrategy` thích hợp của Spring LDAP, đảm bảo TLS được nâng cấp và xác minh **trước SIMPLE bind**. Không thay `ldaps://` bằng `ldap://` rồi giả định cùng mức bảo mật. Đặc biệt không bật native JNDI pooling cho context đang thay đổi trạng thái TLS hoặc bind principal.

## 7. Trường hợp Active Directory: subcode giúp điều tra, không phải thông báo công khai

AD thường xác thực bằng `user@domain` và có `ActiveDirectoryLdapAuthenticationProvider`. Khi cấu hình provider, vẫn phải dùng LDAPS URL được tin cậy và timeout JNDI.

~~~java
package demo.ldap;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;

@Configuration
public class AdAuthenticationConfig {

    @Bean
    ActiveDirectoryLdapAuthenticationProvider adProvider() {
        ActiveDirectoryLdapAuthenticationProvider provider =
                new ActiveDirectoryLdapAuthenticationProvider(
                        "corp.example.test",
                        "ldaps://dc01.corp.example.test:636/");

        provider.setContextEnvironmentProperties(Map.<String, Object>of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "3000"
        ));

        // Chỉ bật nếu ứng dụng có chính sách xử lý lỗi chi tiết an toàn.
        provider.setConvertSubErrorCodesToExceptions(true);
        return provider;
    }
}
~~~

Mảnh cấu hình trên chỉ khai báo provider; cách gắn provider vào `AuthenticationManager` và `SecurityFilterChain` phải phù hợp ứng dụng cụ thể. Không dùng đồng thời hai cấu hình LDAP và AD minh họa nếu không chủ ý tạo nhiều authentication provider. Với production, xác minh phiên bản API, chính sách AD, domain/URL thực và quy tắc trả lỗi.

Khi AD trả LDAP result code `49`, bản tin chẩn đoán đôi khi chứa subcode:

| AD subcode thường gặp | Ý nghĩa chẩn đoán |
| --- | --- |
| `525` | Không tìm thấy người dùng |
| `52e` | Thông tin đăng nhập không hợp lệ |
| `530` | Không được phép đăng nhập vào thời điểm này |
| `532` | Password đã hết hạn |
| `533` | Account bị vô hiệu hóa |
| `701` | Account hết hạn |
| `773` | Người dùng phải đổi password |
| `775` | Account bị khóa |

Đây là **subcode riêng của AD**, không phải bộ mã lỗi LDAP chuẩn dùng đồng nhất cho mọi directory. Theo API của Spring Security, mặc định lỗi bind `49` có thể trở thành `BadCredentialsException`. Khi bật `setConvertSubErrorCodesToExceptions(true)`, một số subcode được ánh xạ thành `CredentialsExpiredException`, `DisabledException`, `AccountExpiredException` hoặc `LockedException`; các mã khác vẫn có thể là `BadCredentialsException`. Không suy diễn rằng mọi subcode đều có một exception riêng hoặc rằng exception đã có sẵn do phía LDAP bất kỳ gửi về.

Subcode nên dùng cho **audit nội bộ/điều tra có kiểm soát**, không trả nguyên văn vào API, HTML, cookie, redirect query string hoặc metric label có định danh tài khoản. Thông báo công khai kiểu “tài khoản này tồn tại nhưng bị khóa” có thể tạo user enumeration; nếu cần mở luồng khôi phục tài khoản, bảo vệ luồng đó bằng cơ chế xác minh riêng.

## 8. Phân biệt lỗi tài khoản và lỗi hạ tầng

Phân loại lỗi cần xét **giai đoạn xảy ra lỗi** và **exception/cause chain**. Ví dụ service account bind thất bại vì secret bị rotate là sự cố cấu hình dịch vụ đối với người đăng nhập, không phải lỗi password của họ.

| Tín hiệu | Loại cần điều tra | Hành vi thích hợp |
| --- | --- | --- |
| LDAP `49` khi bind **user** / `BadCredentialsException` | Sai credentials hoặc trạng thái account không hợp lệ theo thông tin directory | Không cấp phiên; thông báo đăng nhập chung, ghi nhận audit có giới hạn |
| `LockedException`, `DisabledException`, `CredentialsExpiredException` từ AD (khi bật chuyển subcode) | Chính sách/trạng thái account | Không cấp phiên; xử lý hỗ trợ/khôi phục theo policy; tránh lộ chi tiết công khai |
| LDAP `49` khi bind **service account** | Bí mật/service account sai, hết hạn, bị khóa hoặc quyền bind thay đổi | **Lỗi cấu hình/hạ tầng**; báo vận hành, không đổ lỗi cho user |
| `javax.naming.CommunicationException`, socket timeout, DNS failure, LDAP server unreachable | Không kết nối/không nhận phản hồi | **Hạ tầng**; không tạo session; cảnh báo health và điều tra |
| `SSLHandshakeException`, lỗi CA/hostname/certificate | TLS trust hoặc cấu hình chứng chỉ | **Hạ tầng/bảo mật**; không downgrade; cần sửa chứng chỉ/truststore |
| LDAP `51 busy` / `52 unavailable` (nếu directory trả) | Backend bận hoặc không sẵn sàng | **Hạ tầng**; kiểm soát retry/backoff và tải |
| LDAP `32 noSuchObject`, `50 insufficientAccessRights` | Sai DN/search base hoặc thiếu quyền; đôi khi liên quan dữ liệu | Cần xác minh giai đoạn và policy; không tự kết luận password sai |
| Lỗi Java/logic mapping groups, parsing user DN | Cấu hình hoặc bug ứng dụng | Không cấp quyền mặc định; có cảnh báo và kiểm thử hồi quy |

**Hai lỗi rất dễ bị nhầm:**

- **Bad credentials:** LDAP server được kết nối thành công, TLS hợp lệ, và từ chối user bind vì credential/status. Trả một thông báo chung để tránh tiết lộ tài khoản.
- **Directory unavailable:** Hệ thống chưa thể xác minh user vì network/TLS/timeout/backend. Không có bằng chứng password sai. Trả lỗi tạm thời hoặc thông báo hỗ trợ dịch vụ, gắn correlation ID để vận hành tra cứu.

### Bảng quyết định HTTP/API minh họa

| Kết luận sau phân loại an toàn | Kết quả đề xuất | Lưu ý |
| --- | --- | --- |
| Sai username/password hoặc trạng thái account không cho đăng nhập | `401 Unauthorized` và thông báo chung | Không phân biệt user không tồn tại/khóa/sai password ở giao diện public |
| Đã xác thực thành công nhưng thiếu quyền truy cập tài nguyên | `403 Forbidden` | Đây là lỗi **authorization**, không phải LDAP bind thất bại |
| LDAP/AD tạm thời unavailable, timeout, kết nối lỗi | `503 Service Unavailable` khi hệ thống có thể xác định đây là outage | Cần handler riêng trong API; mặc định Spring Security không nhất thiết tự chọn 503 |
| Sai cấu hình truststore, service bind hoặc bug không thể hồi phục tức thời | `500` hoặc `503` tùy chính sách vận hành | Không lộ nội dung exception/cert DN/secret cho client |

**Bất biến bảo mật:** Nếu directory không thể xác nhận danh tính, không phát JWT, không tạo security session, không tự chuyển sang principal mặc định, không “cho phép tạm” để giữ uptime. Đó là nguyên tắc **fail closed**. Hệ thống phải phân biệt thông báo cho người dùng và log có quyền truy cập của vận hành.

## 9. Mẫu phân loại exception tại ranh giới Spring Security

Đây là helper dành cho một luồng xác thực LDAP cụ thể. Nó phân loại các exception Spring Security thường gặp; **không phải** adapter bắt mọi lỗi JNDI trong mọi cấu hình, nên vẫn phải kiểm tra `cause` và giai đoạn bind trong integration test.

~~~java
package demo.ldap;

import org.springframework.security.authentication.AccountStatusException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class LdapFailurePolicy {

    public enum Category {
        CREDENTIAL_REJECTED,
        ACCOUNT_RESTRICTED,
        DIRECTORY_SERVICE_ERROR,
        UNKNOWN
    }

    private LdapFailurePolicy() {
    }

    public static Category classify(AuthenticationException error) {
        if (error instanceof AccountStatusException) {
            return Category.ACCOUNT_RESTRICTED;
        }
        if (error instanceof BadCredentialsException
                || error instanceof UsernameNotFoundException) {
            return Category.CREDENTIAL_REJECTED;
        }
        if (error instanceof AuthenticationServiceException) {
            return Category.DIRECTORY_SERVICE_ERROR;
        }
        return Category.UNKNOWN;
    }
}
~~~

Lưu ý giới hạn:

- `InternalAuthenticationServiceException` thuộc nhóm `AuthenticationServiceException`; tuy nhiên exception lớp trên còn phụ thuộc authentication provider đang dùng. Trước khi gửi HTTP response, code gọi phải xem **ngữ cảnh lỗi và nguyên nhân thực tế**.
- `BadCredentialsException` khi một provider tùy biến bọc sai lỗi mạng có thể cho kết quả phân loại không chính xác. Hãy sửa ở provider/adapter nơi còn biết giai đoạn xử lý, thay vì vá bằng việc dò chuỗi message.
- Không dùng `exception.getMessage()` hoặc LDAP diagnostic text làm thông báo người dùng; có thể chứa DN, server name hoặc AD subcode. Giữ một mã lỗi nội bộ ổn định và correlation ID, có kiểm soát quyền xem log.
- Không catch mọi `RuntimeException` rồi biến thành `BadCredentialsException`. Làm vậy che khuất sự cố production và khiến giám sát khó phát hiện outage.
- Helper là **mảnh mã trong dự án Spring Security**, không chạy riêng bằng `javac` nếu không có các dependency tương ứng. Các code path thực tế vẫn cần authentication failure handler/entry point tùy Servlet hoặc WebFlux để trả HTTP đúng chính sách.

## 10. Ví dụ Java 17 độc lập: kiểm tra LDAPS bind có timeout

Khi cần tách vấn đề TLS, đường mạng và credentials khỏi cấu hình Spring, có thể chạy một chương trình JDK nhỏ. **Mục đích chỉ là thăm dò bind có kiểm soát**, không phải API login và không thử nhiều username/password.

Tệp `LdapsProbe.java`:

~~~java
import java.net.URI;
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public final class LdapsProbe {

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String url = required("LDAP_URL");
        if (!"ldaps".equalsIgnoreCase(URI.create(url).getScheme())) {
            throw new IllegalArgumentException("LDAP_URL must use ldaps://");
        }

        Hashtable<String, String> environment = new Hashtable<>();
        environment.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        environment.put(Context.PROVIDER_URL, url);
        environment.put(Context.SECURITY_AUTHENTICATION, "simple");
        environment.put(Context.SECURITY_PRINCIPAL, required("LDAP_BIND_DN"));
        environment.put(Context.SECURITY_CREDENTIALS, required("LDAP_BIND_PASSWORD"));
        environment.put("com.sun.jndi.ldap.connect.timeout", "2000");
        environment.put("com.sun.jndi.ldap.read.timeout", "3000");

        DirContext context = null;
        try {
            context = new InitialDirContext(environment);
            System.out.println("LDAPS bind: OK");
        } catch (NamingException ex) {
            System.err.println("LDAPS bind: FAILED ("
                    + ex.getClass().getSimpleName() + ")");
            System.exit(2);
        } finally {
            if (context != null) {
                try {
                    context.close();
                } catch (NamingException ignored) {
                    // Bỏ qua lỗi đóng context trong tiện ích kiểm tra đơn giản.
                }
            }
        }
    }
}
~~~

Biên dịch/chạy (JDK 17+, không cần dependency Spring):

~~~bash
javac LdapsProbe.java
java LdapsProbe
~~~

Trước khi chạy, **cấp ba biến môi trường `LDAP_URL`, `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD` từ nơi lưu secret an toàn**, dùng endpoint thử nghiệm được cấp quyền và CA đã được JVM tin cậy. Ví dụ URL hợp lệ: `ldaps://dc01.corp.example.test:636`. Với bind thành công, stdout chính xác:

~~~text
LDAPS bind: OK
~~~

Nếu bind thất bại, stderr có dạng `LDAPS bind: FAILED (TênException)`, ví dụ `CommunicationException` hoặc `AuthenticationException`; tên exception phụ thuộc nguyên nhân thực tế, vì vậy không hứa một stdout cố định cho lỗi. Việc không in message/cause là chủ ý để tránh ghi DN và thông tin nhạy cảm vào log thao tác. Nếu thiếu biến môi trường, chương trình dừng với lỗi cấu hình trước khi mở kết nối.

Chương trình chỉ chứng minh có thể TLS-connect và **bind một tài khoản cụ thể**; chưa kiểm tra search filter, user bind, phân quyền nhóm, retry, SLA hay Spring SecurityFilterChain. Không chạy thử hàng loạt mật khẩu hoặc account thật ngoài kịch bản vận hành được cho phép.

## 11. Quan sát, cảnh báo và chiến lược xử lý khi có sự cố

Theo dõi với nhãn có giới hạn cardinality:

- `ldap_auth_success_total`, `ldap_auth_reject_total`, `ldap_infra_error_total`; giữ phân biệt *account rejected* và *service unavailable*.
- Độ trễ bind/search/group lookup, p50/p95/p99; timeout rate; thread/connection pool saturation; TLS handshake failure count.
- Directory endpoint có định danh nội bộ, môi trường triển khai, loại bước (`service_bind`/`user_bind`/`search`) và correlation ID.
- Số lần bị rate limit, lockout (dưới chính sách nội bộ); không gắn password/token/username thô làm nhãn metric.

Nếu cần log chẩn đoán, log loại lỗi đã phân loại và request ID ở cấp thông tin; thông tin sâu về TLS/LDAP (DN, DC, mã lỗi chi tiết) chỉ ghi ở kênh vận hành được kiểm soát và có cơ chế che dữ liệu. Không bật protocol trace/JNDI BER tracing lâu dài trên production.

**Retry:** Có thể cân nhắc retry hạn chế, backoff + jitter cho một số lỗi kết nối tạm thời nếu request còn ngân sách thời gian và không gây bão tải. Không retry tự động khi LDAP trả bad password/account locked; việc lặp bind sai có thể gây lockout tài khoản. Với load balancer nhiều DC, tránh chuyển sang DC khác mà không kiểm chứng certificate/trust tương ứng. Cần điều tra xem retry một thao tác bind có tạo tác động đến chính sách khóa account của AD hay không.

**Failover:** Có nhiều LDAP URL hoặc nhiều DC giúp chịu lỗi khi một node mất kết nối, nhưng không giải quyết DNS lỗi toàn miền, CA/truststore sai, hết hạn service password, hoặc quá tải đồng thời trên mọi node. Khi có nhiều endpoint, thời gian chờ có thể cộng dồn; kiểm tra đường đi và timeout thực tế trước khi khẳng định SLA.

## 12. Quy trình xử lý sự cố theo triệu chứng

| Triệu chứng | Kiểm tra ưu tiên | Hướng xử lý |
| --- | --- | --- |
| Trước đây hoạt động, sau rotate certificate mọi request lỗi | Truststore Java, CA chain, SAN/FQDN, thời điểm certificate | Cập nhật truststore/chứng chỉ và rollout hợp lệ; **không tắt hostname check** |
| Chỉ một DC lỗi, các DC khác ổn | Certificate và DNS riêng của DC, đường mạng, cổng TLS | Loại node lỗi theo runbook, sửa DC và kiểm tra failover |
| Mọi user cùng lúc không đăng nhập, có `CommunicationException` | DNS/firewall/route, TLS, LDAP server state, connect/read timeout | Báo outage, không đổ lỗi account; không trả token |
| Chỉ service search DN thất bại sau rotate credential | Bind DN/secret mới, trạng thái/ACL của service account, restart/reload | Sửa cấu hình và quyền; bảo đảm không leak secret |
| Một user sai mật khẩu, các user khác thành công | Lỗi user bind `49`, AD subcode nội bộ, lockout policy | Trả thông báo chung, audit phù hợp và hướng dẫn recovery riêng |
| Kết nối được nhưng search không thấy user | Base DN, OU, filter, quyền đọc, loại tài khoản, referrals | Sửa search policy; không tự coi `noSuchObject` là password sai |
| Tăng tải làm p99 login tăng mạnh | Số connection, thread, backend LDAP, retry storm, timeout | Giới hạn tải, tối ưu lookup/cache phù hợp, điều chỉnh pool sau benchmark |

Trong sự cố thật, xác minh **lớp nào thất bại**: handshake/TCP → service bind → user search → user bind → groups/authorities → session/token. Đừng nhảy thẳng đến “mật khẩu người dùng sai” chỉ vì toàn bộ endpoint đăng nhập trả lỗi.

## 13. Kiểm thử bắt buộc trước production

Có thể tổ chức integration test bằng directory thử nghiệm hoặc môi trường AD staging có tài khoản dùng cho kiểm thử, với tình huống được chủ động tạo ra:

| Test | Kết quả mong đợi |
| --- | --- |
| CA/hostname đúng + credentials hợp lệ | Xác thực thành công với principal/authorities đúng |
| Mật khẩu user sai | Không cấp token/session; phản hồi chung; ghi nhận loại credential rejection |
| User không tồn tại | Không cho login; thông báo công khai không tạo user enumeration rõ ràng |
| User khóa/disable/password hết hạn trên AD | Không cấp phiên; phân loại nội bộ đúng theo provider/subcode thực tế |
| Service account password sai, bị khóa hoặc thiếu ACL | Phân loại lỗi dịch vụ/cấu hình, không gắn thành sai password của tất cả user |
| Certificate hết hạn, CA không được tin hoặc SAN không khớp | TLS handshake thất bại; **không downgrade và không tiếp tục bind** |
| LDAP port bị chặn hoặc server không trả response | Connect/read timeout hữu hạn, phản hồi lỗi hạ tầng có kiểm soát |
| Một trong nhiều DC bị lỗi | Chuyển tuyến theo chính sách, xác minh TLS trên DC dự phòng và deadline tổng |
| Directory trả `busy`/`unavailable` | Không cho phép đăng nhập; giới hạn retry/backoff, cảnh báo vận hành |
| 100+ login đồng thời trong tải thử được phép | Không cạn thread/connection bất ngờ; p95/p99 và rejection được đo |
| Đăng nhập bị hủy, trình duyệt đóng kết nối | Không tạo session/token khi kết quả không được chấp nhận; tài nguyên được giải phóng theo khả năng thư viện |
| Log/tracing/metric scan sau test | Không có password người dùng, service secret, access token hoặc LDAP diagnostic nhạy cảm công khai |

Nếu dùng Spring Security Servlet, kiểm thử `MockMvc`/integration HTTP để xác minh authentication entry point, success/failure handlers và response semantics. Nếu ứng dụng dùng WebFlux, dùng `WebTestClient` và kiểm soát blocking LDAP client trên scheduler. Unit test helper phân loại lỗi không đủ thay cho bài test kết nối TLS và LDAP provider thật.

## 14. Checklist cấu hình để vận hành

- [ ] Chỉ kết nối đến các FQDN/port LDAP/AD được duyệt; LDAPS hoặc StartTLS được **xác minh** trước khi truyền mật khẩu.
- [ ] Truststore hợp lệ, CA chain đầy đủ, SAN khớp hostname; không có trust-all, tắt endpoint identification hoặc fallback xuống cleartext.
- [ ] Service account có quyền tối thiểu, bí mật được cấp tại runtime, có rotation/expiry monitoring; user password không lưu/log.
- [ ] Connect/read timeout dương được cấu hình đúng trong JNDI; deadline HTTP, nhiều operation, referrals và failover đã được đo.
- [ ] Mọi lỗi TLS, timeout, network, provider và service bind thất bại đều **fail closed** và không trả session/token.
- [ ] Phân biệt `BadCredentialsException`/trạng thái account với lỗi `AuthenticationServiceException`; không phụ thuộc duy nhất vào exception message.
- [ ] Frontend/API không lộ account enumeration hoặc AD subcode; log/metric có quyền truy cập và che dữ liệu.
- [ ] Test sai password, khóa account, cert sai, hết hạn, mất DC, delay, rotate secret, lỗi ACL và tải đồng thời.
- [ ] Quy trình ứng cứu có phân công người phụ trách directory, secret, TLS và ứng dụng; có bản ghi audit đủ để truy cứu sự cố.

**Ý chính:** LDAPS/StartTLS đảm bảo kênh bảo mật khi **xác minh đúng endpoint**; quản lý secret và timeout là các biện pháp độc lập bắt buộc. Lỗi tài khoản là kết quả xác thực được directory từ chối; lỗi hạ tầng nghĩa là **chưa thể xác minh danh tính**. Cả hai trường hợp đều phải từ chối cấp quyền, nhưng phải được phân loại, ghi nhận và phản hồi khác nhau để vừa an toàn vừa dễ vận hành.

## Tài liệu chính thức và đối chiếu

- [Spring Security 6.5 — LDAP Authentication](https://www.springframework.org/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security — ActiveDirectoryLdapAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html)
- [Spring LDAP — Configuration, ContextSource, TLS](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Java SE 21 — java.naming module và JNDI LDAP timeouts](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/module-summary.html)
- [OWASP — Authentication Cheat Sheet: Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Oracle Java 8u181 release notes — LDAPS endpoint identification](https://www.java.com/en/download/help/release_changes.html)
