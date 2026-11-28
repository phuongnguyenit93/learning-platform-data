# Kiểm soát referral để tránh gửi thông tin xác thực ngoài phạm vi

Một ứng dụng Spring Boot kết nối tới directory nội bộ bằng tài khoản kỹ thuật `cn=app-reader,ou=services,...`. Khi tìm kiếm từ root DN, LDAP server trả về một **referral** trỏ tới `ldap://partner-directory.example.net:389`. Nếu client tự động theo referral, nó có thể mở kết nối tới một máy chủ khác với máy chủ ban đầu. Điều đáng quan tâm là JNDI có thể dùng lại **environment của context gốc**, bao gồm thông tin xác thực, khi tạo referral context theo cách mặc định.

Đây là ranh giới bảo mật quan trọng. Referral là dữ liệu điều hướng do directory trả về; nó không tự chứng minh máy chủ đích thuộc cùng tổ chức, được tin cậy, dùng TLS hoặc có quyền nhận bind credential của ứng dụng. Một referral không được kiểm soát có thể chuyển hướng client tới máy chủ ngoài phạm vi, làm lộ danh tính bind, mật khẩu và dữ liệu truy vấn.

Trong chương **Bảo mật dữ liệu** của module **SPRING_DATA_LDAP**, bài này trình bày cách kiểm soát referral khi sử dụng Spring LDAP, `LdapTemplate`, `ContextSource` và JNDI. Ta sẽ chọn chính sách referral tường minh, xác minh URL và naming context đích, tách credential theo target, giới hạn mạng/TLS, xử lý kết quả partial và kiểm thử bằng directory test. Trọng tâm là **không gửi thông tin xác thực tới một target chỉ vì referral yêu cầu client chuyển hướng**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích referral và continuation reference trong LDAP search.
2. Mô tả nguy cơ gửi bind credential sang máy chủ được referral chỉ định.
3. Phân biệt ba chính sách JNDI `follow`, `ignore` và `throw`.
4. Cấu hình Spring LDAP để xử lý referral một cách tường minh.
5. Kiểm tra scheme, hostname, port, DN và phạm vi naming context của referral URL.
6. Sử dụng `ReferralException.getReferralContext(env)` với môi trường xác thực riêng cho target đã được duyệt.
7. Phân biệt credential của service account, credential của người dùng và credential dành riêng cho referral target.
8. Xử lý referral không được phép, referral loop, referral thiếu TLS và kết quả search không đầy đủ.
9. Viết integration test chứng minh credential không bị gửi tới host ngoài allowlist.

## 2. Referral là gì?

Một directory có thể phân chia dữ liệu trên nhiều naming context hoặc máy chủ. Server đang nhận request có thể không chứa entry cần tìm, nhưng biết máy chủ khác có thể phục vụ nhánh đó. Khi đó, nó gửi một **referral** cho client.

Ví dụ cây directory:

~~~text
dc=corp,dc=example
├── ou=employees
│   └── ldap01.corp.example
├── ou=partners
│   └── partner-directory.corp.example
└── ou=services
    └── cn=app-reader
~~~

Ứng dụng tìm kiếm subtree từ `dc=corp,dc=example`. Máy chủ `ldap01` có thể trả referral cho `ou=partners`, chỉ tới một URL LDAP của máy chủ đối tác.

~~~text
Ứng dụng
   |
   | Search: dc=corp,dc=example
   v
ldap01.corp.example
   |
   | Referral: ldap(s)://partner-directory.../ou=partners,...
   v
Máy chủ referral target
~~~

Referral có thể xuất hiện dưới dạng:

- **Referral result:** server trả một kết quả LDAP chỉ dẫn client tới nơi khác.
- **Search result reference / continuation reference:** trong khi search, server trả các tham chiếu tới những naming context khác có thể chứa kết quả phù hợp.
- **Referral entry:** một entry đặc biệt chứa thông tin tham chiếu, tùy server và control được sử dụng.

Client phải quyết định có theo chỉ dẫn đó hay không. Referral URL có thể chứa hostname, port, DN và các thành phần truy vấn như attributes, scope, filter hoặc extensions. Vì vậy, việc kiểm tra chỉ hostname là chưa đủ nếu ứng dụng cần bảo vệ phạm vi dữ liệu.

### 2.1. Referral không phải failover

| Referral | Failover |
| --- | --- |
| Điều hướng tới naming context hoặc partition khác. | Chuyển sang endpoint thay thế khi endpoint hiện tại lỗi. |
| Target có thể phục vụ một nhánh dữ liệu khác. | Target thường là replica/endpoint của cùng dịch vụ logic. |
| Có thể cần credential và ACL khác. | Có thể dùng cùng loại service identity nếu policy replica cho phép. |
| Phải xác minh referral URL như dữ liệu đầu vào chưa tin cậy. | Endpoint dự phòng phải nằm trong danh sách cấu hình tin cậy. |

Không bật `follow` chỉ vì muốn ứng dụng tự động chuyển sang server dự phòng. Failover nên dựa trên danh sách endpoint do ứng dụng quản trị; referral cần một quy trình xác minh riêng.

## 3. Mối nguy: credential của context gốc có thể được dùng cho referral

Giả sử ứng dụng tạo JNDI context bằng:

~~~text
Context.SECURITY_AUTHENTICATION = simple
Context.SECURITY_PRINCIPAL      = cn=app-reader,ou=services,dc=corp,dc=example
Context.SECURITY_CREDENTIALS    = <secret của app-reader>
Context.REFERRAL                = follow
~~~

Server trả referral tới `ldap://untrusted.example.net:389`. Nếu provider tự động theo referral bằng environment xác thực ban đầu, client có thể gửi bind identity/credential tới target đó. Kết quả có thể là:

1. Credential của service account rời khỏi trust boundary dự kiến.
2. Mật khẩu simple bind có thể đi qua kết nối không mã hóa nếu target dùng `ldap://` và client không nâng cấp TLS.
3. Target có thể ghi lại bind DN, mật khẩu hoặc metadata truy vấn.
4. Target có thể trả dữ liệu giả, dữ liệu bị thay đổi hoặc referral tiếp theo để chuyển hướng thêm lần nữa.
5. Service account có thể có quyền đọc rộng hơn mức cần thiết tại target ngoài dự kiến.

Oracle JNDI mô tả rõ rằng `ReferralException.getReferralContext()` không tham số sử dụng environment của context gốc, bao gồm các thuộc tính bảo mật. API `getReferralContext(env)` được cung cấp để tạo referral context bằng environment khác khi cần dùng thông tin xác thực khác. Vì vậy, **không gọi overload không tham số trước khi target đã được xác minh và được phép nhận credential**.

RFC 4511 cũng cảnh báo một ứng dụng độc hại có thể chèn referral để chuyển hướng client tới máy chủ giả mạo. Client nên thận trọng hoặc từ chối referral khi chưa có biện pháp bảo mật phù hợp; referral từ thao tác StartTLS cần được xử lý đặc biệt và không nên được chấp nhận như một đường chuyển hướng tùy ý.

## 4. Ba chính sách referral trong JNDI

JNDI LDAP provider sử dụng environment property `java.naming.referral` (hằng `Context.REFERRAL`) để quyết định xử lý referral:

| Giá trị | Hành vi | Ý nghĩa bảo mật |
| --- | --- | --- |
| `follow` | Provider tự động theo referral. | Có thể dùng lại security environment của context ban đầu; chỉ cân nhắc khi topology và credential forwarding đã được kiểm soát. |
| `ignore` | Provider không theo referral. | Không chuyển bind credential theo referral, nhưng kết quả có thể thiếu; không được coi mọi search là đầy đủ. |
| `throw` | Provider ném `ReferralException` để ứng dụng quyết định. | Phù hợp khi cần kiểm tra target, allowlist và credential trước khi theo referral. |

Nếu không cấu hình, mặc định phụ thuộc provider. Với Oracle JNDI LDAP provider và Spring LDAP `AbstractContextSource`, mặc định thường là `ignore`. Không nên dựa vào mặc định này như một chính sách bảo mật đã được kiểm chứng; hãy cấu hình tường minh.

### 4.1. follow: tiện lợi nhưng mở rộng trust boundary

`follow` khiến provider tự động xử lý referral. Cách này có thể phù hợp với một directory topology được quản trị chặt, mọi target đều thuộc cùng trust domain, TLS/hostname hợp lệ và service account được phép bind trên tất cả target. Tuy nhiên, nếu không kiểm soát referral URL, ứng dụng có thể bị điều hướng sang host không mong muốn.

Trước khi dùng `follow`, cần có:

- Danh sách target được quản trị và xác minh.
- TLS bắt buộc, certificate chain và hostname hợp lệ trên mọi target.
- Credential được phép dùng tại tất cả target; quyền tối thiểu và phạm vi dữ liệu đã rõ.
- Network egress rule chỉ cho phép kết nối tới những host/port cần thiết.
- Giới hạn referral depth/count, timeout và phát hiện vòng lặp.
- Integration test chứng minh provider không gửi credential ngoài phạm vi.

Nếu không thể chứng minh các điều kiện này, không bật `follow` tự động.

### 4.2. ignore: không theo referral nhưng có thể trả partial result

Với Oracle JNDI LDAP provider, khi đặt `ignore` trên LDAPv3, provider tự động gửi **ManageDsaIT control** để yêu cầu server trả referral entry như entry thông thường thay vì chuyển hướng. Nếu server không hỗ trợ control đó và vẫn trả referral, provider có thể ném `PartialResultException` để báo rằng có thể còn kết quả chưa được lấy.

Do đó:

- `ignore` không có nghĩa “search luôn thành công và đầy đủ”.
- `ignore` không có nghĩa “server không gửi referral”.
- Nếu ứng dụng cần dữ liệu ở partition được referral chỉ tới, việc bỏ qua referral sẽ làm kết quả không đầy đủ.
- Không dùng một danh sách partial để đồng bộ xóa user hoặc kết luận user không tồn tại.

Đây có thể là lựa chọn phù hợp khi nghiệp vụ cố ý chỉ tìm trong naming context cục bộ và không cần theo các nhánh ngoài phạm vi. API cần thể hiện rõ phạm vi tìm kiếm.

### 4.3. throw: từ chối tự động và kiểm tra trước khi theo

`throw` yêu cầu JNDI ném `ReferralException` khi gặp referral. Ứng dụng có thể đọc `getReferralInfo()`, kiểm tra target và quyết định:

- Theo referral bằng environment xác thực riêng nếu target được cho phép.
- Bỏ referral bằng `skipReferral()` nếu không được phép.
- Dừng thao tác và báo kết quả partial/failed nếu referral là cần thiết cho truy vấn.

Với search trả `NamingEnumeration`, referral có thể xuất hiện sau khi một số entry bình thường đã được trả. Khi `ReferralException` xuất hiện, enumeration cũ không còn hợp lệ; chương trình phải gọi lại thao tác search ban đầu trên referral context theo hướng dẫn JNDI. Vì vậy, xử lý thủ công cần quản lý cả enumeration, trạng thái referral và kết quả partial.

**Khuyến nghị cho ứng dụng có service account quyền rộng:** đặt `throw` làm chính sách ban đầu, rồi chỉ theo những target đã được xác minh và có credential riêng. Nếu ứng dụng không cần partition được referral trỏ tới, từ chối referral và báo phạm vi dữ liệu không đầy đủ theo hợp đồng API.

## 5. Cấu hình Spring LDAP tường minh

Spring LDAP `AbstractContextSource` cung cấp `setReferral(String)` để cấu hình chính sách JNDI. Ví dụ tạo `LdapContextSource` bằng Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    LdapContextSource ldapContextSource(
            DirectoryProperties properties) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(properties.url());
        source.setBase(properties.baseDn());
        source.setUserDn(properties.bindDn());
        source.setPassword(properties.bindPassword());

        // Không tự động theo referral trước khi ứng dụng kiểm tra target.
        source.setReferral("throw");

        return source;
    }
}
~~~

`DirectoryProperties` là cấu hình do ứng dụng định nghĩa, lấy secret từ secret manager hoặc cơ chế quản lý secret của nền tảng. Spring gọi lifecycle initialization của bean sau khi tạo; nếu tự khởi tạo `LdapContextSource` ngoài Spring container thì cần gọi `afterPropertiesSet()` sau khi đặt đầy đủ thuộc tính.

Nếu dùng Spring Boot auto-configuration, cấu hình referral qua thuộc tính môi trường LDAP tương ứng hoặc cấu hình `ContextSource` tường minh. Hãy kiểm tra giá trị thực tế được áp dụng trong context; không giả định mọi version Boot bind cùng một property name nếu chưa xác minh.

### 5.1. Giới hạn khi xử lý referral qua LdapTemplate

`LdapTemplate` tự quản lý context, enumeration và việc dịch `NamingException` sang exception của Spring LDAP. Khi dùng `throw`, ứng dụng có thể gặp `org.springframework.ldap.LdapReferralException` hoặc exception liên quan tùy provider. Với một số Active Directory server, referral trong search có thể xuất hiện thành `PartialResultException`; tài liệu Spring LDAP lưu ý không có cách theo thủ công các referral kiểu này qua `LdapTemplate` ở trường hợp đó.

Nếu use case bắt buộc phải duyệt từng referral, xác minh target và cấp credential riêng, hãy kiểm thử đúng server/provider/version. Có thể cần một adapter JNDI cấp thấp quản lý `LdapContext` và enumeration trực tiếp. Không giả định `LdapTemplate.search(...)` luôn đưa một JNDI `ReferralException` nguyên bản tới caller. Đặc biệt, không bật `ignorePartialResultException=true` để che lỗi khi nghiệp vụ cần dữ liệu từ mọi partition; tùy chọn này có thể làm search trả về mà không thông báo nhánh referral đã bị bỏ qua.

### 5.2. Những cấu hình liên quan

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap01.corp.example:636
    base: dc=corp,dc=example
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      com.sun.jndi.ldap.connect.timeout: "3000"
      com.sun.jndi.ldap.read.timeout: "5000"
~~~

Ví dụ trên minh họa endpoint TLS và timeout của JNDI LDAP provider. Chính sách referral cần được đặt tường minh bằng `LdapContextSource.setReferral("throw")` hoặc property đã xác minh tương ứng. Không đưa credential vào URL, query string, file cấu hình commit lên Git hoặc log.

### 5.3. Đừng nhầm ContextSource với authorization của người dùng

Một ứng dụng thường dùng service account để bind tới LDAP. Service account là danh tính kỹ thuật của ứng dụng, không phải danh tính người đang đăng nhập HTTP. Việc LDAP ACL cho phép service account đọc entry không đồng nghĩa caller HTTP được phép xem entry đó.

Vì vậy:

- LDAP ACL giới hạn những gì bind identity có thể đọc/ghi.
- Spring Security/service authorization giới hạn những gì caller được phép xem.
- Referral allowlist giới hạn những máy chủ mà ứng dụng được phép kết nối.
- Credential policy giới hạn danh tính nào được phép bind vào từng target.

Bốn lớp này giải quyết bốn câu hỏi khác nhau và phải được kiểm tra riêng.

## 6. Xác minh referral URL trước khi kết nối

Referral URL là dữ liệu nhận từ directory. Hãy coi nó như input chưa tin cậy, kể cả khi server nguồn là server nội bộ.

### 6.1. Kiểm tra scheme

Nếu ứng dụng yêu cầu TLS, chỉ chấp nhận:

- `ldaps://` với certificate chain và hostname được xác minh.
- Hoặc một quy trình StartTLS được ứng dụng kiểm soát tường minh, bảo đảm StartTLS thành công trước bind.

Từ chối `ldap://` plaintext khi policy yêu cầu mã hóa. Không tự động downgrade từ LDAPS sang LDAP. RFC 4511 khuyến nghị client từ chối referral phát sinh từ thao tác StartTLS; không dùng StartTLS như một bước mở đường cho referral tới host chưa được xác minh.

### 6.2. Kiểm tra hostname và port

Không chấp nhận mọi hostname chỉ vì kết thúc bằng `corp.example`. So khớp **exact hostname** đã được cấu hình, ví dụ:

~~~text
Allowed:
  ldap01.corp.example
  ldap-partners.corp.example

Rejected:
  ldap01.corp.example.attacker.net
  ldap-evil.corp.example
  127.0.0.1
  169.254.169.254
~~~

Quy tắc nên gồm:

1. Chỉ chấp nhận scheme đã định, thường là `ldaps`.
2. Chỉ chấp nhận port đã định, thường là 636 cho LDAPS.
3. Chuẩn hóa hostname theo IDNA và chữ thường trước khi so sánh.
4. So khớp exact allowlist, không dùng `endsWith("corp.example")`.
5. Từ chối URL có user-info, fragment hoặc dạng authority không hợp lệ.
6. Kiểm tra DNS/network egress để target không thể phân giải tới IP ngoài phạm vi.
7. Giữ hostname trong URL để TLS hostname verification có thể xác minh đúng SAN.

Allowlist hostname không thay thế network egress policy. Nếu DNS bị thay đổi hoặc bị chiếm quyền, hostname được allowlist vẫn có thể trỏ tới địa chỉ IP không mong muốn. Network policy/firewall cần giới hạn đích thực tế.

### 6.3. Kiểm tra DN và naming context

Một referral tới host hợp lệ vẫn có thể trỏ tới **nhánh dữ liệu ngoài phạm vi**. Ví dụ ứng dụng chỉ được đọc `ou=employees,dc=corp,dc=example` nhưng referral lại chỉ tới `ou=finance,dc=corp,dc=example`.

Phải kiểm tra:

- DN trong referral URL có nằm trong naming context được phép không.
- Scope/filter/attributes của URL có phù hợp use case ban đầu không.
- Referral có yêu cầu mở rộng truy vấn sang nhánh không được caller/service account truy cập không.
- Target có đúng partition đã được quản trị trong topology không.

Khi so sánh DN, dùng `LdapName`/`Rdn` để phân tích cấu trúc, không so sánh bằng `String.endsWith(...)`. DN là chuỗi phân cấp có escape và thứ tự RDN; so sánh chuỗi thô có thể cho kết quả sai.

### 6.4. Không cho referral tự quyết định query tùy ý

Referral URL có thể mang thông tin về DN, attributes, scope, filter và extensions. Ứng dụng nên áp chính sách:

- Giữ filter nghiệp vụ đã được xây dựng an toàn; không thay bằng filter tùy ý do target cung cấp nếu không có use case.
- Chỉ yêu cầu attribute cần thiết.
- Không cho referral mở rộng scope ngoài phạm vi ban đầu.
- Từ chối extension không được ứng dụng hỗ trợ.
- Không dùng raw referral URL như một URL người dùng có thể truyền vào API.

## 7. Allowlist referral target bằng Java

Ví dụ sau kiểm tra phần authority của referral URL. Đây là **một lớp kiểm tra ban đầu**, không phải bộ phân tích đầy đủ RFC 4516. Trong production, parser phải xử lý referral info theo kiểu mà JNDI provider thực tế trả về, giải mã DN/URL đúng chuẩn và kiểm tra naming context trước khi tạo context.

~~~java
import java.net.IDN;
import java.net.URI;
import java.util.Locale;
import java.util.Set;

public final class ReferralTargetPolicy {

    private final Set<String> allowedHosts;

    public ReferralTargetPolicy(Set<String> allowedHosts) {
        this.allowedHosts = allowedHosts.stream()
                .map(host -> IDN.toASCII(host).toLowerCase(Locale.ROOT))
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    public boolean allowsAuthority(URI referralUri) {
        if (referralUri == null) {
            return false;
        }

        if (!"ldaps".equalsIgnoreCase(referralUri.getScheme())) {
            return false;
        }
        if (referralUri.getRawUserInfo() != null
                || referralUri.getFragment() != null) {
            return false;
        }

        String host = referralUri.getHost();
        if (host == null || host.indexOf(':') >= 0 || host.matches("[0-9.]+")) {
            // Ví dụ này chỉ cho phép DNS hostname, không nhận IPv4/IPv6 literal.
            return false;
        }

        final String canonicalHost;
        try {
            canonicalHost = IDN.toASCII(host).toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException ex) {
            return false;
        }

        int port = referralUri.getPort() == -1
                ? 636
                : referralUri.getPort();

        return port == 636 && allowedHosts.contains(canonicalHost);
    }
}
~~~

Ví dụ khởi tạo:

~~~java
ReferralTargetPolicy policy = new ReferralTargetPolicy(Set.of(
        "ldap01.corp.example",
        "ldap-partners.corp.example"
));
~~~

**Không dừng ở `allowsAuthority`.** Trước khi theo referral, cần dùng parser LDAP URL đã được kiểm chứng để đọc DN/scope/filter/extensions; xác minh DN thuộc naming context được phép; kiểm tra TLS certificate/hostname; và áp network egress policy. Không thay thế các bước đó bằng một phép so khớp hostname đơn giản.

### 7.1. Không giả định getReferralInfo luôn là một String

`ReferralException.getReferralInfo()` trả về `Object`. Với LDAP provider, thông tin có thể chứa một URL hoặc nhiều URL theo cách biểu diễn phụ thuộc provider. Không gọi `toString().split(" ")` rồi xem mỗi mảnh là URL hợp lệ.

Tạo một adapter chuyên biệt:

~~~java
public interface ReferralInfoParser {
    java.util.List<java.net.URI> parse(Object referralInfo);
}
~~~

Adapter phải được kiểm thử với provider/server đang sử dụng, xử lý encoding URL theo RFC 4516, giới hạn độ dài/số lượng URL và từ chối dữ liệu không parse được. Nếu không thể phân tích chính xác, hãy từ chối referral.

## 8. Tách credential theo từng referral target

Đây là phần quan trọng nhất của bài.

### 8.1. Tránh overload không tham số

~~~java
// NGUY HIỂM nếu chưa xác minh target:
Context referred = referralException.getReferralContext();
~~~

Theo JNDI, overload không tham số tạo referral context bằng environment của context đã ném `ReferralException`. Environment đó có thể chứa:

- `Context.SECURITY_PRINCIPAL`
- `Context.SECURITY_CREDENTIALS`
- `Context.SECURITY_AUTHENTICATION`
- Các thuộc tính TLS/provider liên quan.

Nếu context gốc dùng service account có quyền rộng, việc gọi overload này trước khi kiểm tra referral có thể gửi thông tin xác thực sang target ngoài phạm vi.

### 8.2. Dùng getReferralContext(env) với environment riêng

JNDI cung cấp `ReferralException.getReferralContext(Hashtable<?, ?> env)` để tạo referral context bằng environment được chỉ định. Khi cần dùng credential khác, hãy tạo environment riêng cho target đã được xác minh:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.ReferralException;
import javax.naming.directory.DirContext;

public final class ApprovedReferralConnector {

    public DirContext connect(
            ReferralException referral,
            ReferralTarget target,
            ReferralCredential credential) throws NamingException {

        if (!target.approved()) {
            throw new SecurityException("Referral target is not approved");
        }

        Hashtable<String, Object> targetEnvironment = new Hashtable<>();
        targetEnvironment.put(
                Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        targetEnvironment.put(Context.SECURITY_AUTHENTICATION, "simple");
        targetEnvironment.put(
                Context.SECURITY_PRINCIPAL,
                credential.bindDn());
        targetEnvironment.put(
                Context.SECURITY_CREDENTIALS,
                credential.secret());
        targetEnvironment.put(
                "com.sun.jndi.ldap.connect.timeout", "3000");
        targetEnvironment.put(
                "com.sun.jndi.ldap.read.timeout", "5000");

        // Không sao chép environment gốc có thể chứa credential rộng quyền.
        return (DirContext) referral.getReferralContext(targetEnvironment);
    }
}
~~~

`ReferralTarget` và `ReferralCredential` là kiểu dữ liệu do ứng dụng định nghĩa. `ReferralCredential` chỉ được lấy từ credential provider dành cho target đã duyệt; không lấy password từ URL, referral payload hoặc input HTTP.

**Lưu ý quan trọng:** `getReferralContext(env)` sử dụng environment được truyền để tạo referral context. Ví dụ trên minh họa JNDI LDAP provider chuẩn và chỉ là khung cấu hình; hãy kiểm tra hành vi cụ thể của provider/runtime. URL referral đã được duyệt phải dùng `ldaps://`; truststore và hostname verification vẫn phải được cấu hình ở JVM. Không sao chép environment gốc rồi chỉ thay hostname; environment riêng phải chứa đúng context factory, timeout và authentication cần cho target, đồng thời không mang credential ngoài phạm vi.

Nếu target hỗ trợ anonymous read và nghiệp vụ cho phép, có thể tạo referral context không có credential. Nếu cần bind, dùng service account **riêng cho target hoặc trust domain đó**, với quyền tối thiểu.

### 8.3. Credential provider theo target

Không hard-code password hoặc dùng một service account toàn quyền cho mọi referral. Có thể tách trách nhiệm bằng interface:

~~~java
public interface ReferralCredentialProvider {
    ReferralCredential credentialFor(ReferralTarget target);
}
~~~

Một implementation có thể ánh xạ:

| Referral target | Credential | Quyền |
| --- | --- | --- |
| `ldap01.corp.example` | `corp-directory-reader` | Read trong OU nhân viên. |
| `ldap-partners.corp.example` | `partner-directory-reader` | Read trong OU đối tác được cấp. |
| Host không nằm allowlist | Không cấp credential. | Từ chối referral. |

Credential provider cần:

- Chỉ trả credential sau khi target được xác minh.
- Lấy secret từ secret manager/vault, không từ config commit.
- Không log hoặc serialize secret.
- Không trả credential dùng cho một trust domain khác.
- Hỗ trợ rotation/revocation và audit lần cấp credential.
- Có thể từ chối hoàn toàn target dù hostname đã nằm trong allowlist nếu target không còn được phép.

### 8.4. Không dùng credential người dùng HTTP làm credential referral

Người dùng đăng nhập ứng dụng bằng một danh tính HTTP, còn ứng dụng bind bằng service account. Hai credential có mục đích khác nhau.

Không chuyển access token/session/password của caller HTTP vào LDAP referral trừ khi kiến trúc xác thực đã được thiết kế riêng, có cơ chế delegation được phê duyệt và target hỗ trợ. Thông thường, ứng dụng dùng một credential kỹ thuật có quyền tối thiểu, rồi thực thi authorization theo caller ở tầng service.

## 9. Quy trình xử lý referral an toàn

Một luồng xử lý có kiểm soát có thể diễn đạt như sau:

~~~mermaid
flowchart TD
    A["LDAP search trên context gốc"] --> B{"Có ReferralException?"}
    B -- "Không" --> C["Xử lý kết quả bình thường"]
    B -- "Có" --> D["Đọc referralInfo"]
    D --> E["Parse URL theo provider/RFC 4516"]
    E --> F{"Scheme, host, port hợp lệ?"}
    F -- "Không" --> X["Từ chối referral"]
    F -- "Có" --> G{"DN/scope/filter thuộc phạm vi?"}
    G -- "Không" --> X
    G -- "Có" --> H["Kiểm tra TLS + egress policy"]
    H --> I{"Target được tin cậy?"}
    I -- "Không" --> X
    I -- "Có" --> J["Lấy credential riêng cho target"]
    J --> K["getReferralContext(targetEnv)"]
    K --> L["Thực hiện lại thao tác ban đầu"]
    L --> M{"Còn referral khác?"}
    M -- "Có" --> D
    M -- "Không" --> N["Đánh giá completeness"]
    X --> O["PARTIAL hoặc FAILED"]
~~~

Các bước cụ thể:

1. Cấu hình `Context.REFERRAL` thành `throw`.
2. Thực hiện thao tác LDAP với base/scope/filter được ứng dụng kiểm soát.
3. Khi có `ReferralException`, dừng enumeration hiện tại và ghi nhận trạng thái.
4. Đọc `getReferralInfo()` qua parser đã được kiểm thử.
5. Kiểm tra scheme, host, port, URL components và naming context.
6. Kiểm tra target nằm trong allowlist, TLS/hostname hợp lệ và network egress được phép.
7. Lấy credential riêng hoặc chọn anonymous read theo policy.
8. Gọi `getReferralContext(targetEnvironment)`; không dùng overload không tham số.
9. Gọi lại thao tác ban đầu trên referral context với cùng tham số đã được kiểm soát.
10. Đóng context/enumeration đúng vòng đời và xử lý referral tiếp theo nếu có.
11. Chỉ đánh dấu search hoàn tất nếu mọi nhánh cần thiết đã được xử lý và không có lỗi partial.

### 9.1. Pseudocode cho manual follow

Do `ReferralException` có thể xuất hiện trong lúc đọc enumeration, vòng `try/catch` cần bao cả lời gọi search và quá trình lặp kết quả. Mỗi referral cần xác minh riêng:

~~~java
while (true) {
    try {
        NamingEnumeration<SearchResult> results =
                currentContext.search(base, filter, controls);

        try {
            while (results.hasMore()) {
                process(results.next());
            }
        } finally {
            results.close();
        }

        break; // Search và mọi referral cần thiết đã hoàn tất.

    } catch (ReferralException referral) {
        Object info = referral.getReferralInfo();

        List<URI> urls = referralInfoParser.parse(info);
        ReferralTarget target = policy.approve(urls);

        if (target == null) {
            // Fail closed: không tạo context và không tiếp tục với credential nguồn.
            throw new ReferralRejectedException("Referral target is not approved");
        }

        ReferralCredential credential =
                credentialProvider.credentialFor(target);

        DirContext referredContext =
                approvedConnector.connect(referral, target, credential);

        currentContext = referredContext;
        // Vòng lặp gọi lại search với cùng base/filter/controls.
    }
}
~~~

Đây là **pseudocode minh họa luồng**, không phải một implementation hoàn chỉnh có thể sao chép nguyên xi. `ReferralRejectedException`, parser, policy và quản lý `currentContext` cần được định nghĩa theo ứng dụng. Khi referral bị từ chối, ví dụ dừng toàn bộ thao tác; kết quả đã nhận trước đó phải được đánh dấu PARTIAL/FAILED nếu nhánh bị từ chối cần thiết cho kết quả đầy đủ. Không được đóng nhầm context gốc hoặc để context referral không được đóng.

### 9.2. Bỏ qua referral và kết quả partial

`ReferralException.skipReferral()` bỏ qua referral hiện tại và trả về `true` nếu còn referral cần xử lý. Theo quy trình JNDI, sau đó có thể cần gọi `getReferralContext()` để tiếp tục xử lý referral tiếp theo. Nếu bỏ qua một referral mà nhánh đó cần thiết để trả kết quả đầy đủ, kết quả phải được đánh dấu PARTIAL.

Trong ứng dụng có credential nhạy cảm, không gọi `getReferralContext()` không tham số chỉ để tiếp tục sau `skipReferral()`: overload này dùng environment của context nguồn. Nếu cần xử lý các referral còn lại, hãy dùng quy trình có environment đã được kiểm soát cho từng target; nếu không thể bảo đảm điều đó, dừng search và trả trạng thái PARTIAL/FAILED.

Không được:

- Bắt `ReferralException` rồi trả list hiện tại như kết quả đầy đủ.
- Bắt `PartialResultException` rồi trả list rỗng.
- Ghi nhận scan hoàn tất khi một partition bắt buộc chưa được truy cập.
- Dùng dữ liệu partial để xóa hoặc vô hiệu hóa entry trong hệ thống nội bộ.

## 10. Ranh giới tin cậy và quyền truy cập

Một referral được phép kết nối không có nghĩa ứng dụng được phép đọc mọi entry ở target. Cần đánh giá ba danh tính/phạm vi:

| Thành phần | Câu hỏi | Cơ chế kiểm soát |
| --- | --- | --- |
| Caller HTTP | Người dùng được xem tenant/OU nào? | Spring Security, authorization theo tenant/ownership. |
| Bind identity tại LDAP nguồn | Service account được search/read gì? | LDAP ACL, least privilege. |
| Bind identity tại referral target | Credential nào được phép bind và đọc nhánh nào? | Credential provider theo target, ACL riêng. |

### 10.1. Kiểm tra naming context theo cấu trúc DN

Ví dụ ứng dụng chỉ cho phép:

~~~text
ou=employees,dc=corp,dc=example
ou=partners,dc=corp,dc=example
~~~

Referral tới:

~~~text
ou=finance,dc=corp,dc=example
~~~

phải bị từ chối nếu `ou=finance` không thuộc phạm vi được cấu hình. Không so sánh DN bằng chuỗi suffix vì các RDN có thể chứa escape, dấu phẩy và Unicode. Dùng `LdapName` và so sánh các RDN theo cấu trúc; đồng thời áp dụng base DN được phép cho từng target.

### 10.2. Credential ít quyền nhất

Tài khoản referral reader nên:

- Chỉ có quyền bind và search/read trên naming context được giao.
- Chỉ đọc attribute cần thiết.
- Không có quyền add/delete/modify nếu ứng dụng chỉ tìm kiếm.
- Không có quyền đọc password hash hoặc dữ liệu nhạy cảm không cần thiết.
- Có secret riêng theo trust domain và lịch rotation.
- Có thể revoke độc lập với service account nguồn.

Không dùng Domain Admin/Directory Manager làm credential chung để “cho chắc chắn referral chạy được”.

### 10.3. TLS và network egress

Với mỗi target được allowlist:

- Bắt buộc LDAPS hoặc StartTLS theo policy.
- Xác minh certificate chain và hostname/SAN.
- Không tắt hostname verification.
- Không cho phép redirect/downgrade sang plaintext.
- Giới hạn outbound traffic bằng firewall/network policy.
- Không cho phép kết nối tới loopback, link-local, metadata endpoint hoặc dải mạng không thuộc directory trust domain.
- Theo dõi certificate expiry và thay đổi DNS.

RFC 4511 cảnh báo referral có thể bị lợi dụng để chuyển hướng client. TLS bảo vệ kết nối tới target và xác minh danh tính target; allowlist và egress policy xác định **target nào được phép kết nối**. Cả ba cần phối hợp.

## 11. Những lỗi thường gặp khi kiểm soát referral

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Dùng mặc định referral mà không kiểm tra. | Hành vi mặc định phụ thuộc provider; Spring LDAP/JNDI thường ignore nhưng có thể gây partial result. | Cấu hình `throw` hoặc chính sách được chọn rõ ràng. |
| Bật `follow` để “tự động tìm hết”. | Có thể gửi lại security environment gốc tới target. | Allowlist, TLS, credential scope và integration test trước khi bật. |
| Gọi `getReferralContext()` không tham số. | Dùng environment context gốc, có thể gồm bind credential. | Chỉ dùng sau khi đã có chính sách; ưu tiên overload có environment target riêng. |
| Chỉ kiểm tra hostname bằng `endsWith`. | Có thể chấp nhận `corp.example.attacker.net`. | Exact allowlist sau canonicalization. |
| Chỉ kiểm tra host, bỏ qua DN. | Có thể truy cập naming context ngoài phạm vi. | So sánh DN cấu trúc và allowed base. |
| Chấp nhận `ldap://` khi yêu cầu TLS. | Bind credential/dữ liệu có thể đi plaintext. | Yêu cầu `ldaps` hoặc StartTLS có kiểm soát. |
| Dùng một bind account toàn quyền cho mọi target. | Credential compromise có phạm vi ảnh hưởng lớn. | Credential provider và least privilege theo target. |
| Log toàn bộ referral URL và environment. | Có thể lộ DN, filter, query hoặc credential. | Log target alias, scheme, outcome và correlation ID đã làm sạch. |
| Bỏ qua `PartialResultException`. | Ứng dụng có thể tuyên bố kết quả đầy đủ dù thiếu partition. | Đánh dấu PARTIAL/FAILED và xử lý theo hợp đồng. |
| Không giới hạn referral loop. | Có thể tạo vòng lặp kết nối/tiêu thụ tài nguyên. | Giới hạn depth/count, timeout và visited-target set. |
| Theo referral từ StartTLS tùy ý. | Có thể phá vỡ ranh giới bảo mật của nâng cấp TLS. | Từ chối theo policy/RFC và chỉ dùng target được xác minh. |

## 12. Kiểm thử bảo mật referral

Nên có một môi trường test gồm:

- LDAP server nguồn với service account reader.
- Referral target hợp lệ dùng LDAPS và credential riêng.
- Referral target không nằm trong allowlist.
- Referral target dùng LDAP plaintext.
- Target có DN nằm ngoài allowed naming context.
- Target ghi lại bind attempts để xác minh credential có bị gửi tới hay không.

Không dùng credential production trong các test này.

### 12.1. Ma trận kiểm thử

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Referral target hợp lệ. | Host, port, scheme, DN và TLS nằm trong policy. | Ứng dụng có thể theo bằng credential target riêng. |
| Referral target ngoài allowlist. | URL tới hostname không được cấu hình. | Từ chối; target không nhận bind attempt. |
| Referral target có suffix giả mạo. | `ldap01.corp.example.attacker.net`. | Exact allowlist từ chối. |
| Referral dùng `ldap://`. | Policy yêu cầu TLS. | Từ chối trước khi bind. |
| Referral dùng port lạ. | Port không nằm allowlist. | Từ chối. |
| Referral URL có user-info. | URL chứa phần user/password. | Từ chối; không lấy credential từ URL. |
| DN ngoài phạm vi. | Host hợp lệ nhưng referral DN ở OU finance. | Từ chối theo naming context. |
| Filter/scope ngoài policy. | Referral URL mang filter/scope không được cho phép. | Từ chối hoặc chuẩn hóa theo policy đã định. |
| Certificate không tin cậy. | Target TLS dùng CA không có trong truststore. | Handshake fail; không fallback plaintext. |
| Hostname mismatch. | SAN không khớp referral hostname. | TLS validation fail. |
| Credential riêng cho target. | Target có account riêng, ACL giới hạn. | Chỉ credential của target được dùng. |
| Không có credential cho target. | Host allowlisted nhưng credential provider từ chối. | Referral bị từ chối; không thử credential nguồn. |
| follow ngoài ý muốn. | Cấu hình context phải là `throw`. | Kiểm tra runtime property và xác nhận không tự động follow. |
| ignore với server hỗ trợ ManageDsaIT. | Referral được trả như referral entry. | Không follow; API thể hiện đúng phạm vi. |
| ignore với server không hỗ trợ ManageDsaIT. | Server vẫn trả referral. | Có thể nhận `PartialResultException`; không đánh dấu complete. |
| Referral loop. | A trỏ B, B trỏ lại A. | Dừng theo depth/count/visited set. |
| Nhiều referral URL. | Một referral info chứa nhiều target. | Mỗi URL được parse và kiểm tra độc lập. |
| Referral trong search enumeration. | Một số entry trả trước khi referral xuất hiện. | Enumeration cũ được xử lý đúng; search được gọi lại trên context referral. |
| Referral không bắt buộc. | Query trong base OU cục bộ. | Có thể từ chối referral và vẫn trả kết quả cục bộ theo hợp đồng. |
| Referral bắt buộc. | Kết quả nghiệp vụ nằm ở partition được referral chỉ tới. | Từ chối referral thì outcome PARTIAL/FAILED, không trả full success. |

### 12.2. Xác minh credential không rời trust boundary

Đây là test quan trọng nhất:

1. Tạo service account nguồn có một mật khẩu test duy nhất.
2. Tạo referral target giả lập có log bind DN và kết quả bind, nhưng không ghi mật khẩu thô.
3. Tạo referral trỏ tới target không nằm allowlist.
4. Gọi API tìm kiếm.
5. Xác minh target không nhận kết nối/bind từ ứng dụng.
6. Xác minh log ứng dụng chỉ ghi `referral_rejected`, target alias hoặc hostname đã làm sạch.
7. Lặp lại với target hợp lệ và credential riêng; xác minh bind identity là tài khoản dành cho target.

Không kiểm tra bằng cách ghi password vào log để so sánh. Có thể kiểm tra số lần bind, bind DN đã làm sạch hoặc dùng test credential có giá trị giả và kiểm soát được.

### 12.3. Kiểm tra partial result

Chuẩn bị search có entry cục bộ và một referral bắt buộc. Khi ứng dụng từ chối target:

- Kết quả không được gắn trạng thái COMPLETE.
- Nếu API trả entry cục bộ, phải thể hiện trạng thái PARTIAL hoặc lỗi phụ thuộc theo hợp đồng.
- Job đồng bộ không được xóa entry không xuất hiện từ partition bị bỏ qua.
- Metric referral rejection/partial phải tăng.
- Caller không được nhận thông tin nhạy cảm của referral target ngoài mức cần thiết.

## 13. Quan sát và audit

Ghi nhận sự kiện referral đủ để điều tra nhưng không tiết lộ credential:

| Field | Ví dụ | Ghi chú |
| --- | --- | --- |
| `event` | `ldap_referral_rejected` | Tên sự kiện cố định. |
| `source_alias` | `corp-directory-primary` | Alias endpoint nguồn. |
| `target_alias` | `partner-directory` | Chỉ ghi alias đã map allowlist; nếu không rõ thì ghi `unapproved`. |
| `scheme` | `ldaps` | Không ghi URL đầy đủ nếu có thành phần nhạy cảm. |
| `decision` | `REJECTED_SCHEME` | Enum có cardinality thấp. |
| `operation` | `search` | Search/lookup/update. |
| `referral_depth` | `1` | Đếm độ sâu referral. |
| `correlation_id` | `req-4a92` | Liên kết log cùng request. |
| `elapsed_ms` | `24` | Thời gian xử lý referral. |
| `result_state` | `PARTIAL` | Trạng thái completeness. |

Không ghi:

- Password, bind secret hoặc toàn bộ JNDI environment.
- Raw referral URL chưa làm sạch.
- Raw cookie hoặc token.
- Filter có username/email/PII.
- Toàn bộ DN nếu chính sách log không cho phép.
- Nội dung entry hoặc attribute nhạy cảm.

### 13.1. Metrics đề xuất

- `ldap.referral.received`: số referral nhận được.
- `ldap.referral.followed`: số referral được theo sau sau khi phê duyệt.
- `ldap.referral.rejected`: số referral bị từ chối theo policy.
- `ldap.referral.partial_results`: số search kết thúc partial.
- `ldap.referral.target_tls_failures`: lỗi TLS khi kết nối target đã duyệt.
- `ldap.referral.credential_denied`: credential provider từ chối cấp credential.
- `ldap.referral.loop_detected`: số lần phát hiện vòng lặp.

Không dùng referral URL, DN hoặc filter làm metric label. Dùng alias đã được cấu hình và enum outcome.

## 14. Bài tập tình huống

Một ứng dụng HR dùng Spring LDAP để tìm nhân viên. Context gốc kết nối:

~~~text
ldaps://ldap01.corp.example:636
Bind DN:
cn=app-reader,ou=services,dc=corp,dc=example
Allowed base:
ou=employees,dc=corp,dc=example
~~~

Khi search subtree, server trả referral:

~~~text
ldap://directory-partner.attacker.net:389/ou=employees,dc=corp,dc=example
~~~

Ứng dụng hiện cấu hình `referral=follow`. Service account nguồn có quyền đọc nhiều thuộc tính nhân viên. Nhóm vận hành phát hiện target nhận một bind request từ ứng dụng.

**Yêu cầu:**

1. Giải thích vì sao `follow` có thể khiến credential của context gốc được dùng tại referral target.
2. Nêu khác biệt giữa `getReferralContext()` và `getReferralContext(env)`.
3. Chính sách referral nào phù hợp để ứng dụng kiểm tra target trước khi kết nối?
4. Liệt kê các bước xác minh scheme, hostname, port và DN của referral.
5. Vì sao kiểm tra `host.endsWith("corp.example")` không an toàn?
6. Nếu target hợp lệ nhưng cần credential riêng, ứng dụng lấy credential từ đâu?
7. Nếu target chỉ hỗ trợ `ldap://`, có nên gửi service account password không?
8. Nếu ứng dụng đặt `ignore` và nhận `PartialResultException`, có được trả danh sách hiện có như full success không?
9. Nếu target được allowlist nhưng referral DN trỏ sang OU finance ngoài phạm vi, xử lý thế nào?
10. Cần kiểm tra gì để chứng minh credential nguồn không bị gửi sang target ngoài allowlist?
11. Nếu referral bị lặp A → B → A, cơ chế nào dừng vòng lặp?
12. Nếu referral xuất hiện giữa enumeration sau khi một số entry đã được trả, trạng thái kết quả cần được xử lý ra sao?

**Gợi ý đáp án:**

- `getReferralContext()` dùng environment của context nguồn, có thể gồm security properties; `getReferralContext(env)` cho phép tạo referral context bằng environment riêng.
- Dùng `throw` để kiểm tra target trước khi quyết định theo.
- Chỉ cho phép scheme TLS, exact hostname/port, DN trong allowed naming context và URL components phù hợp.
- `endsWith` có thể chấp nhận hostname giả mạo như `corp.example.attacker.net`; cần exact allowlist sau canonicalization.
- Credential phải được cấp từ provider/secret manager theo target, với quyền tối thiểu.
- Từ chối LDAP plaintext khi policy yêu cầu TLS; không downgrade.
- `PartialResultException` là dấu hiệu kết quả có thể thiếu; không gắn COMPLETE.
- Target hợp lệ về host nhưng sai DN vẫn phải bị từ chối.
- Test target giả lập ghi nhận bind attempts; xác minh target ngoài allowlist không nhận kết nối/bind và log không chứa secret.
- Dùng visited-target set, referral depth/count và deadline.
- Enumeration cũ có thể không còn hợp lệ; xử lý referral theo JNDI, gọi lại thao tác trên referral context và chỉ công bố COMPLETE khi mọi nhánh cần thiết đã xử lý.

## 15. Ghi nhớ

**Referral là dữ liệu điều hướng, không phải bằng chứng về độ tin cậy của máy chủ đích.** Khi dùng service account LDAP, `follow` có thể khiến provider dùng lại environment xác thực của context gốc. JNDI xác nhận `getReferralContext()` không tham số dùng environment nguồn, bao gồm security properties; `getReferralContext(env)` cho phép ứng dụng cung cấp environment khác cho referral context.

Với ứng dụng có credential quyền rộng, hãy cấu hình referral tường minh, ưu tiên `throw`, xác minh scheme/host/port/DN/scope/filter, kiểm tra TLS và egress policy, rồi mới cấp credential riêng cho target được duyệt. Không gửi credential nguồn tới host chưa xác minh, không dùng `ldap://` khi policy yêu cầu TLS và không coi kết quả bị bỏ referral/partial là đầy đủ. Kiểm thử bằng target giả lập để chứng minh credential không rời trust boundary.

### Tài liệu tham khảo

- [Oracle JNDI Tutorial — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html)
- [Oracle JNDI Tutorial — Manually Following Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/throw.html)
- [Java SE — ReferralException](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ReferralException.html)
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 3296 — Named Subordinate References in LDAP](https://www.rfc-editor.org/rfc/rfc3296)
- [RFC 4516 — LDAP URL Format](https://www.rfc-editor.org/rfc/rfc4516)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
