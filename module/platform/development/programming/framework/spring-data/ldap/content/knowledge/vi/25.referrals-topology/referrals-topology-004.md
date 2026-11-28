# Kiểm soát danh tính và thông tin xác thực khi theo referral

Trong hệ thống LDAP có nhiều domain, máy chủ hoặc phân vùng dữ liệu, một thao tác tìm kiếm đôi khi nhận được **referral**: lời giới thiệu đến một LDAP server khác có thể biết vị trí entry cần truy cập. Theo referral có thể làm tăng khả năng tìm đúng dữ liệu, nhưng đồng thời mở ra một **ranh giới tin cậy mới**. Khi client tạo kết nối tới máy chủ được chỉ dẫn, nó sẽ dùng danh tính nào, có truyền lại mật khẩu cũ không, đường truyền có được bảo vệ không và server đích có được phép đọc dữ liệu người dùng không?

Bài học thuộc chương **Referrals và topology** của mô-đun `SPRING_DATA_LDAP`. Ta sẽ xây chính sách bảo vệ danh tính và thông tin xác thực khi dùng Spring Data LDAP, Spring LDAP `LdapTemplate`, JNDI và nhiều `ContextSource`. Mục tiêu không phải bật tùy chọn `follow` để mọi referral tự hoạt động, mà là biết khi nào được phép theo, **theo bằng tài khoản nào** và kiểm chứng rằng không có thông tin xác thực bị gửi đến đích ngoài chính sách.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích **LDAP Referral** và **SearchResultReference**, phân biệt chúng với alias, replication và load-balancing.
2. Đọc một LDAP URL và nhận ra địa chỉ máy chủ đích, base DN, scope, filter cùng rủi ro bảo mật.
3. Phân biệt `java.naming.referral=ignore`, `follow`, `throw` trong JNDI; cấu hình qua Spring LDAP hoặc Spring Boot.
4. Hiểu vì sao **Bind DN và mật khẩu trên kết nối nguồn không được coi là hợp lệ cho mọi referral**.
5. Thiết kế chính sách **fail closed**: endpoint được phép, TLS, quyền tối thiểu, credential riêng, giới hạn số lần chuyển tiếp và kết quả một phần.
6. Cấu hình nhiều `LdapContextSource`/`LdapTemplate` cho các domain đã được phê duyệt, tránh tự động chuyển credential.
7. Tích hợp repository/ODM, DN, `objectClass` và filter an toàn mà không làm mất ranh giới xác thực.
8. Kiểm thử referral giả mạo, downgrade sang `ldap://`, loop, lỗi chứng chỉ, ACL và kết quả Search chưa đầy đủ.

## 2. Bối cảnh: nhiều directory trong một topology

Giả sử công ty có hai directory:

~~~text
LDAP A – ldap-core.example.org
  Suffix: dc=example,dc=org
  ├── ou=people
  │   └── uid=lan
  └── dc=emea  ── referral ──┐
                            │
LDAP B – ldap-emea.example.org
  Suffix: dc=emea,dc=example,dc=org
  └── ou=people             │
      └── uid=anna ◀────────┘
~~~

Hai server quản lý những naming context khác nhau. Khi client truy vấn dữ liệu ở vùng EMEA thông qua LDAP A, máy chủ A có thể trả về URL gợi ý:

~~~text
ldaps://ldap-emea.example.org:636/dc=emea,dc=example,dc=org
~~~

URL này có nghĩa **máy chủ đích có thể xử lý tiếp yêu cầu**. Nó không tự chứng minh máy chủ đó thuộc tổ chức, được tin cậy, có TLS hợp lệ hay được phép nhận credential của client.

### Danh tính của hai service account

| Thành phần | LDAP A | LDAP B |
| --- | --- | --- |
| URI kết nối | `ldaps://ldap-core.example.org:636` | `ldaps://ldap-emea.example.org:636` |
| Base của ContextSource | `dc=example,dc=org` | `dc=emea,dc=example,dc=org` |
| Bind DN | `cn=svc-core-reader,ou=service,dc=example,dc=org` | `cn=svc-emea-reader,ou=service,dc=emea,dc=example,dc=org` |
| Secret | `LDAP_CORE_PASSWORD` | `LDAP_EMEA_PASSWORD` |
| Quyền | Search được các entry được cấp tại A | Search được các entry được cấp tại B |

**Không chia sẻ mật khẩu mặc định giữa hai nơi.** Tên Bind DN chỉ là một phần của danh tính; quyền đọc/sửa do ACL, quy tắc xác thực và chính sách của từng directory quyết định. Ngay cả khi cùng một username xuất hiện ở hai server, không có nghĩa mật khẩu hoặc quyền sử dụng được phép chuyển qua lại.

## 3. Referral ở mức giao thức là gì?

Theo RFC 4511, một LDAP server có thể trả **resultCode 10 – referral** nếu nó không thể/không muốn xử lý yêu cầu và biết nơi có thể xử lý. Referral chứa một hay nhiều URI của dịch vụ khác.

Với Search, có thêm tình huống **SearchResultReference**: server tìm được search base, bắt đầu trả các entry tại chỗ, nhưng gặp dữ liệu được phân chia trên server khác. Khi đó response có thể gồm **các entry cục bộ và continuation reference**. Không được tự hiểu rằng các entry đã nhận là **toàn bộ** kết quả.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant A as LDAP A
    participant B as LDAP B
    App->>A: Search dưới dc=example,dc=org
    A-->>App: SearchResultEntry (vùng core)
    A-->>App: SearchResultReference (URL vùng EMEA)
    Note over App: Quyết định có được truy cập B không
    alt B được phê duyệt, có credential riêng
        App->>B: Kết nối TLS, Bind bằng svc-emea-reader
        B-->>App: Kết quả theo ACL tại B
    else Referral không được phép
        App-->>App: Không kết nối tới B; báo partial/blocked
    end
~~~

### Referral không phải alias hoặc replica

| Cơ chế | Bản chất | Ảnh hưởng đến danh tính |
| --- | --- | --- |
| **Referral** | Server giới thiệu URI khác để xử lý tiếp. | Client có thể tạo kết nối/Bind mới. |
| **SearchResultReference** | Phần tham chiếu tới phân vùng khác trong kết quả Search. | Kết quả có thể chưa đầy đủ nếu không theo. |
| **Alias** | Entry LDAP tham chiếu tên khác, có cơ chế dereference riêng. | Không đồng nghĩa tự kết nối sang server khác. |
| **Replication / failover URL** | Nhiều server có dữ liệu sao chép/phục vụ cùng mục tiêu. | Phải đánh giá chính sách từng server; không phải referral theo nghĩa giao thức. |

Cấu hình một mảng URL trong `LdapContextSource` cho dự phòng kết nối **không thay thế** thiết kế referral. Ngược lại, việc theo referral không bảo đảm các đích đều là bản sao của nhau.

## 4. Cấu trúc LDAP URL và những dữ liệu cần kiểm tra

Theo RFC 4516, một LDAP URL có thể mang:

~~~text
ldap[s]://host:port/dn?attributes?scope?filter?extensions
~~~

Ví dụ để hình dung:

~~~text
ldaps://ldap-emea.example.org:636/ou=people,dc=emea,dc=example,dc=org
~~~

Các thành phần cần chính sách kiểm soát:

| Phần URL | Ý nghĩa | Rủi ro nếu tin vô điều kiện |
| --- | --- | --- |
| Scheme `ldap`/`ldaps` | Giao thức kết nối, bảo vệ transport. | Hạ cấp từ TLS sang kết nối không mã hóa. |
| Host | Server đích. | Truy cập host không được phê duyệt, DNS độc hại hoặc SSRF. |
| Port | Cổng máy chủ. | Kết nối tới dịch vụ bất ngờ. |
| DN | Base hoặc entry mới của operation. | Truy vấn/sửa ngoài nhánh được cấp phép. |
| Attribute list | Thuộc tính được yêu cầu trả về. | Lộ thuộc tính không cần thiết nếu ACL/ứng dụng yếu. |
| Scope | Phạm vi Search. | Tăng từ ONELEVEL sang SUBTREE ngoài chủ đích. |
| Filter | Điều kiện Search có thể thay đổi trên referral. | Nới phạm vi truy vấn, thay đổi nghĩa nghiệp vụ. |
| Extension | Thông tin bổ sung, có thể mang quy tắc đặc thù. | Hành vi không dự kiến của provider. |

**Chính sách không được chỉ so sánh chuỗi host đơn thuần.** Cần kiểm tra scheme, host chuẩn hóa, port, đích DNS/IP phù hợp, vùng DN được phép, loại thao tác, giới hạn Search và tính hợp lệ của certificate. Nếu referral URL không có DN hoặc tham số Search, RFC có quy tắc kế thừa một số thành phần của request ban đầu; ứng dụng vẫn phải xét **yêu cầu hiệu dụng cuối cùng** chứ không chỉ phần xuất hiện trong URL.

Không đặt username/password vào LDAP URL và không coi referral URL là chỉ thị cấp quyền.

## 5. Ba chế độ JNDI: ignore, follow và throw

JNDI có thuộc tính `Context.REFERRAL` (tên môi trường `java.naming.referral`) với ba giá trị:

| Chế độ | Hành vi khái quát | Đánh giá bảo mật |
| --- | --- | --- |
| `ignore` | Không chủ động theo referral. Provider có thể dùng control đặc thù; Search thiếu phần đích có thể sinh `PartialResultException`. | Tránh việc tự kết nối tới đích khác, nhưng phải xử lý dữ liệu thiếu. |
| `follow` | Cho phép provider tự động theo referral. | Chỉ dùng khi đã hiểu/cấu hình chính sách target, credentials, TLS và giới hạn follow. |
| `throw` | Đưa sự kiện referral lên cho tầng gọi xử lý (thường qua `ReferralException`). | Thích hợp khi muốn fail closed và tự phê duyệt đích. |

Hành vi chi tiết phụ thuộc JNDI provider và LDAP server. **Không mặc định cả ba chế độ luôn cho cùng số entry Search** hoặc kết quả đã hoàn chỉnh.

### Điều gì xảy ra khi bật follow?

Một lỗi tư duy thường gặp là: “Referral chỉ như chuyển hướng HTTP, provider sẽ tự xử lý an toàn.” Thực tế, provider cần tạo kết nối tới server khác và chọn thông tin xác thực để Bind. Tùy implementation/cách gọi, nó có thể **kế thừa môi trường JNDI** từ context nguồn, gồm principal hoặc credentials. Bởi vậy **không có cơ sở để kết luận bật follow sẽ không chuyển credential**.

Theo Java JNDI API, `ReferralException.getReferralContext()` tạo context referral từ **environment của context nguồn**; bản `getReferralContext(Hashtable env)` cho phép chỉ định environment khác. Gọi phiên bản không tham số khi chưa kiểm soát môi trường là rủi ro nếu context nguồn có mật khẩu dịch vụ nhạy cảm.

**Chính sách đề xuất cho ứng dụng không kiểm soát hoàn toàn topology:** mặc định `throw`, không theo referral ngoài kế hoạch; sau đó kết nối tới các server đã biết bằng context/credential **được cấu hình riêng**.

## 6. Danh tính phải được tách cho từng đích

Có ba danh tính khác nhau cần giữ rõ:

1. **Danh tính người gọi HTTP:** người đã xác thực vào ứng dụng (ví dụ qua session hoặc OAuth/OIDC).
2. **Danh tính Bind tới LDAP A:** tài khoản dịch vụ, chẳng hạn `svc-core-reader`.
3. **Danh tính Bind tới LDAP B:** tài khoản khác, chẳng hạn `svc-emea-reader`.

~~~mermaid
flowchart TD
    U["Người gọi API<br/>quyền theo ứng dụng"] --> S["DirectorySearchService"]
    S --> A["ContextSource A<br/>svc-core-reader + secret A"]
    S --> B["ContextSource B<br/>svc-emea-reader + secret B"]
    A --> OA["ACL LDAP A<br/>dc=example,dc=org"]
    B --> OB["ACL LDAP B<br/>dc=emea,dc=example,dc=org"]
    A -. "Không sao chép mật khẩu A" .-> B
~~~

**Bind LDAP thành công không đồng nghĩa người gọi API đã được xác thực.** Ngược lại, một người dùng được phép xem danh bạ ở vùng core chưa chắc được xem danh bạ ở vùng EMEA. Authorization phải đánh giá cả **actor**, **vùng dữ liệu** và **operation**.

### Không dùng mật khẩu người dùng cuối làm credential fallback

Nếu một ứng dụng xử lý login người dùng bằng LDAP, không được mặc định gửi mật khẩu họ vừa nhập tới mọi target được referral giới thiệu. Điều này có thể làm lộ mật khẩu sang directory khác hoặc endpoint bị chiếm quyền.

Khi thật sự cần xác thực liên vùng, nên dùng cơ chế federation hoặc phương án authentication được tổ chức phê duyệt; nếu phải Bind trực tiếp tới một vùng khác, xác định rõ destination, trust, user identity, consent/policy và TLS trước khi làm. Không giải quyết bằng “thử Bind mật khẩu của người dùng lên mọi referral”.

## 7. Các quyết định an toàn trước khi theo referral

Một referral chỉ được tiếp tục nếu tất cả kiểm tra bắt buộc đều đạt.

~~~mermaid
flowchart TD
    A["Nhận referral/continuation reference"] --> B{"Đích có trong allowlist?"}
    B -->|"Không"| F["Từ chối và đánh dấu kết quả không đầy đủ"]
    B -->|"Có"| C{"Scheme, host, port,<br/>DNS/IP và TLS hợp lệ?"}
    C -->|"Không"| F
    C -->|"Có"| D{"Base DN, scope, filter<br/>và operation được phép?"}
    D -->|"Không"| F
    D -->|"Có"| E{"Có credential riêng<br/>với quyền tối thiểu?"}
    E -->|"Không"| F
    E -->|"Có"| G{"Giới hạn hop,<br/>timeout, visited targets?"}
    G -->|"Không"| F
    G -->|"Có"| H["Tạo context đích được kiểm soát"]
    H --> I["Search theo ACL của đích"]
    I --> J["Gắn provenance và trạng thái completeness"]
~~~

Các quy tắc cụ thể:

- **Allowlist rõ ràng:** dùng một danh sách cấu hình có kiểm soát của `scheme + hostname + port + base DN`; đừng nhận địa chỉ bất kỳ từ response LDAP hoặc HTTP client.
- **Chống SSRF:** áp egress firewall/network policy, kiểm tra DNS/IP không đi tới metadata service, loopback hoặc mạng không được phép; cân nhắc DNS rebinding và thay đổi kết quả phân giải giữa lúc kiểm tra và kết nối.
- **TLS bắt buộc:** chỉ nối đến server đích bằng LDAPS hoặc StartTLS được thiết lập đúng **trước Simple Bind**, kiểm tra hostname/SAN và chain CA; không fallback sang plaintext.
- **Credential theo đích:** mỗi target có Bind DN và secret riêng; tuyệt đối không copy `Context.SECURITY_CREDENTIALS` từ nguồn.
- **Giới hạn quyền:** reader chỉ Search/đọc thuộc tính được phép, không dùng admin để “cho referral hoạt động”.
- **Giới hạn độ sâu:** hạn chế số bước chuyển tiếp, số server, tổng thời gian, số entry và ghi lại target đã ghé để ngăn vòng lặp.
- **Chính sách dữ liệu:** nếu một region bắt buộc mà không truy cập được, trả trạng thái lỗi hoặc kết quả một phần **có đánh dấu**, không âm thầm báo “không có user”.
- **Không tự động follow với thao tác ghi:** Add/Modify/Delete/Rename chuyển sang naming context khác cần kiểm tra quyền, tính duy nhất DN, idempotency và hậu quả khi thao tác không thành công.

## 8. Cấu hình Spring Boot để không tự theo referral

Nếu ứng dụng chỉ kết nối một directory bằng Spring Boot có hỗ trợ thuộc tính referral (ví dụ Spring Boot 3.5+), có thể cấu hình như sau. Toàn bộ các thiết lập LDAP cần nằm trong **cùng một nhánh** `spring.ldap`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap-core.example.org:636
    base: dc=example,dc=org
    username: cn=svc-core-reader,ou=service,dc=example,dc=org
    password: "${LDAP_CORE_PASSWORD}"
    referral: throw
    template:
      ignore-partial-result-exception: false
~~~

`spring.ldap.referral` được bổ sung trong Spring Boot 3.5; nếu ứng dụng dùng bản Boot cũ hơn, hãy cấu hình `LdapContextSource#setReferral("throw")` trực tiếp hoặc tùy biến ContextSource đúng cách. Đừng giả định một property không được phiên bản đang dùng nhận sẽ có tác dụng.

`ignore-partial-result-exception: false` giúp tránh tình huống vô tình bỏ qua lỗi PartialResultException. Thuộc tính này **không làm kết quả được tự hoàn tất**; nó chỉ quyết định cách `LdapTemplate` phản ứng khi provider báo kết quả không đầy đủ.

**Mặc định bảo thủ:** `throw` giúp hệ thống nhận biết khi gặp referral; sau đó tầng tích hợp quyết định xử lý theo chính sách, thay vì để một provider tự chọn endpoint và môi trường Bind.

## 9. Cấu hình ContextSource riêng cho hai LDAP server

Nếu hệ thống biết trước các vùng LDAP được tin cậy, một cách đơn giản và dễ kiểm toán là **không parse referral URL để kết nối**, mà ánh xạ vùng nghiệp vụ tới các endpoint được cấu hình sẵn.

Ví dụ cấu hình `application.yml` có hai tập thông tin:

~~~yaml
directory:
  core:
    url: ldaps://ldap-core.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=svc-core-reader,ou=service,dc=example,dc=org
    password: "${LDAP_CORE_PASSWORD}"
  emea:
    url: ldaps://ldap-emea.example.org:636
    base: dc=emea,dc=example,dc=org
    bind-dn: cn=svc-emea-reader,ou=service,dc=emea,dc=example,dc=org
    password: "${LDAP_EMEA_PASSWORD}"
~~~

Đây là **configuration namespace riêng của ứng dụng**, không phải toàn bộ thuộc tính tự động của Spring Boot. Ta sẽ inject từng giá trị qua `@Value` để tạo bean.

`config/DirectoryTopologyConfig.java`:

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryTopologyConfig {

    @Bean("coreContextSource")
    public LdapContextSource coreContextSource(
            @Value("${directory.core.url}") String url,
            @Value("${directory.core.base}") String base,
            @Value("${directory.core.bind-dn}") String bindDn,
            @Value("${directory.core.password}") String secret) {
        return source(url, base, bindDn, secret);
    }

    @Bean("emeaContextSource")
    public LdapContextSource emeaContextSource(
            @Value("${directory.emea.url}") String url,
            @Value("${directory.emea.base}") String base,
            @Value("${directory.emea.bind-dn}") String bindDn,
            @Value("${directory.emea.password}") String secret) {
        return source(url, base, bindDn, secret);
    }

    @Bean("coreLdapTemplate")
    public LdapTemplate coreLdapTemplate(
            @Qualifier("coreContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    @Bean("emeaLdapTemplate")
    public LdapTemplate emeaLdapTemplate(
            @Qualifier("emeaContextSource")
            LdapContextSource source) {
        return new LdapTemplate(source);
    }

    private LdapContextSource source(
            String url, String base, String bindDn, String secret) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(secret);

        // Không tự động follow referral phát sinh trong từng vùng.
        source.setReferral("throw");
        return source;
    }
}
~~~

Spring gọi lifecycle `afterPropertiesSet` cho bean `LdapContextSource` theo cơ chế container. Ví dụ chỉ minh họa **wiring xác thực và referral**; để production cần cấu hình truststore/certificate, timeout và network policy tương ứng. Không để debug dump ra bean có chứa password.

### Tại sao cấu hình như vậy?

- `coreContextSource` chỉ có credential của vùng core; `emeaContextSource` chỉ có credential vùng EMEA.
- Mỗi `LdapTemplate` gắn với đúng ContextSource; không có hành vi copy secret từ LDAP A sang LDAP B.
- Nếu một vùng lại trả referral khác, `setReferral("throw")` bảo đảm không tự follow theo cách provider.
- Có thể cấp quyền và xoay vòng secret cho từng vùng mà không cần đổi vùng khác.
- Khi dùng Spring Data LDAP repository, cần xác nhận repository nào dùng đúng `LdapTemplate`/`ContextSource`. Trong ứng dụng có nhiều repository, nên tách repository configuration theo vùng hoặc dùng `LdapTemplate` tường minh cho luồng đa vùng.

**Đừng dùng một bean `LdapTemplate` duy nhất rồi thay URL/username/password trên ContextSource trước mỗi request.** Singleton ContextSource được chia sẻ giữa các thread; thay mutable credential động rất dễ gây lẫn danh tính, rò rỉ secret và race condition.

## 10. Route theo vùng đã phê duyệt, không theo URL từ client

Ứng dụng có thể chỉ nhận một enum vùng đã được cấp quyền, thay vì nhận một host hoặc referral URL tự do.

`service/DirectoryPeopleService.java`:

~~~java
package com.example.directory.service;

import java.util.List;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPeopleService {

    public enum Region { CORE, EMEA }

    public record PersonSummary(String uid, String fullName) {}

    private static final Pattern UID =
            Pattern.compile("[a-z][a-z0-9._-]{1,31}");

    private final LdapTemplate core;
    private final LdapTemplate emea;

    public DirectoryPeopleService(
            @Qualifier("coreLdapTemplate") LdapTemplate core,
            @Qualifier("emeaLdapTemplate") LdapTemplate emea) {
        this.core = core;
        this.emea = emea;
    }

    public List<PersonSummary> findPerson(
            Region region, String uid) {

        if (region == null || uid == null
                || !UID.matcher(uid).matches()) {
            throw new IllegalArgumentException("Invalid region or uid");
        }

        // Quyền actor -> region phải kiểm tra ở service/security layer.
        LdapTemplate template = switch (region) {
            case CORE -> core;
            case EMEA -> emea;
        };

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(10)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return template.search(
                query,
                (AttributesMapper<PersonSummary>) attributes ->
                    new PersonSummary(
                        (String) attributes.get("uid").get(),
                        (String) attributes.get("cn").get()
                    )
        );
    }
}
~~~

Tại runtime:

- `Region.CORE` sử dụng base `dc=example,dc=org`, nên `ou=people` trỏ đến `ou=people,dc=example,dc=org`.
- `Region.EMEA` sử dụng base `dc=emea,dc=example,dc=org`, nên cùng search base tương đối trỏ đến `ou=people,dc=emea,dc=example,dc=org`.
- `uid` là giá trị filter; `LdapQueryBuilder` encoding giá trị an toàn. Không ghép trực tiếp `"(uid=" + uid + ")"`.
- Trả về DTO hai trường, không trả toàn entity có DN hoặc thông tin xác thực.
- Mỗi truy vấn vẫn có thể gặp referral riêng; service cần xử lý exception/cảnh báo theo chính sách hệ thống, **không mặc nhiên coi lỗi bằng “không tìm thấy”**.

Đây là một ví dụ **phân tuyến tới endpoint đã phê duyệt**, không phải một thư viện tự động xử lý mọi `ReferralException` có thể có. Với trường hợp cần tự động khai thác referral tùy biến, xem mục tiếp theo.

## 11. Khi bắt buộc xử lý ReferralException thủ công

Ở mức JNDI, ứng dụng có thể gặp `javax.naming.ReferralException`, có các API:

~~~java
// API JNDI minh họa, không phải vòng follow đầy đủ:
Object info = referralException.getReferralInfo();

// Dùng context từ môi trường nguồn: KHÔNG dùng không điều kiện
// nếu môi trường đó có credential cần bảo vệ:
// referralException.getReferralContext();

// Có thể chỉ định một environment khác:
// referralException.getReferralContext(approvedEnvironment);
~~~

`getReferralInfo()` cho biết thông tin referral, thường có URL. Cần **kiểm tra thông tin đó trước** khi gọi bất kỳ method tạo context đích nào.

`getReferralContext(Hashtable env)` cho phép cung cấp environment mới, nhưng **không thay thế kiểm tra endpoint**. Nếu chưa xác nhận server đích được phép, chỉ việc đổi mật khẩu đã không đủ: bạn vẫn có thể gửi query tới nơi độc hại, vi phạm chính sách truy cập mạng hoặc để lộ dữ liệu qua kết quả/log.

### Quy trình xử lý thủ công nên có

1. Nhận referral từ provider, **không kết nối ngay**.
2. Trích xuất địa chỉ và các tham số cần thiết (không log secret).
3. Kiểm tra URL theo chuẩn RFC 4516; so với allowlist host/port/scheme/base DN. Kiểm tra thêm IP đích, TLS và loại operation.
4. Kiểm tra số hop và server đã ghé, tránh vòng lặp.
5. Chọn **Bind DN + secret riêng** của destination từ secret manager, không kế thừa secret của context nguồn.
6. Tạo connection đến destination theo cấu hình riêng, có timeout/truststore đúng.
7. Lặp lại Search với base/scope/filter đã được kiểm soát; không để target URL mở rộng quyền tùy ý.
8. Đóng context, ghi kết quả/provenance, đánh dấu Search hoàn chỉnh hay một phần.
9. Nếu bất kỳ kiểm tra nào thất bại: **không follow** và trả lỗi/partial có kiểm soát.

Khi thao tác qua `LdapTemplate`, Spring LDAP có thể **dịch bọc ngoại lệ** JNDI thành exception của Spring LDAP. Vì vậy code bắt trực tiếp `javax.naming.ReferralException` ngoài một lời gọi `LdapTemplate.search(...)` không nhất thiết nhận đúng exception. Cần thiết kế tầng xử lý dựa trên API/cause thật của phiên bản framework, hoặc tách hẳn truy vấn đến destination được cấu hình sẵn như mục 9–10.

### Quy tắc không được quên

**Không gọi `getReferralContext()` không tham số trong môi trường chứa mật khẩu service account khi chưa phê duyệt đích.** JNDI API quy định cách này sử dụng environment của context nguồn; phải xem nó là thao tác có nguy cơ đưa credential sang ranh giới tin cậy khác.

## 12. Trường hợp follow tự động có thể chấp nhận

Không phải mọi hệ thống bắt buộc phải cấm `follow`. Có thể cân nhắc nếu tất cả điều kiện sau đã được kiểm chứng:

- Topology referral do một đơn vị đáng tin cậy quản lý và thay đổi qua quy trình phê duyệt.
- Toàn bộ destination nằm trong vùng mạng và tên miền được phép, có certificate hợp lệ, không có downgrade từ TLS sang plaintext.
- Cách provider xử lý principal/credential đã được kiểm chứng bằng network trace/log **không chứa secret** và kiểm thử trên các phiên bản JDK đang dùng.
- Danh tính dùng tại target được ủy quyền rõ ràng, ít quyền và được chính sách bảo mật chấp nhận.
- Có giới hạn số hop, timeout, size limit và khả năng phát hiện loop.
- Có kiểm thử khi một target thất bại, từ chối xác thực hoặc trả kết quả một phần.

Nếu không chứng minh được các điều kiện trên, lựa chọn an toàn hơn là **không bật automatic follow**, kết nối riêng đến target đã biết.

## 13. Không giấu lỗi PartialResultException

Giả sử tìm `uid=anna` từ LDAP A. Server có thể trả các entry tại vùng core và một continuation reference sang EMEA. Nếu client không theo referral, kết quả trả về là **một phần**; điều này khác với “không có Anna”.

Spring LDAP có thuộc tính:

~~~java
ldapTemplate.setIgnorePartialResultException(false);
~~~

Nếu đặt thành `true` để tránh exception trong các môi trường như Active Directory, ứng dụng có thể tiếp tục và **không nhận được cảnh báo** rằng Search chưa hoàn chỉnh. Đây là một quyết định sản phẩm và bảo mật, không chỉ là “mẹo sửa lỗi”.

| Tình huống | Xử lý nên chọn |
| --- | --- |
| Ứng dụng chỉ cần dữ liệu của một vùng | Search đúng base của vùng đó, không hứa bao phủ toàn topology. |
| Ứng dụng yêu cầu kết quả liên vùng đầy đủ | Query các vùng đã phê duyệt; nếu một vùng lỗi, trả failure hoặc partial có đánh dấu. |
| Dùng ignore partial result | Phải chứng minh việc bỏ qua là có chủ đích; không báo kết quả là đầy đủ. |
| Referral sang đích không tin cậy | Không kết nối; ghi nhận blocked referral, có thể trả lỗi chính sách. |
| Referral sang đích được tin cậy nhưng mất kết nối | Không trả kết quả rỗng giả; ghi trạng thái vùng lỗi. |

Ví dụ hợp đồng API tổng hợp minh họa:

~~~json
{
  "complete": false,
  "searchedRegions": ["CORE"],
  "failedRegions": ["EMEA"],
  "results": [
    {"uid": "lan", "fullName": "Nguyen Thi Lan"}
  ]
}
~~~

Cấu trúc này là **đề xuất của tầng HTTP**, không phải cấu trúc response LDAP chuẩn. Nếu sản phẩm không cho phép trả partial, có thể trả lỗi gateway/service unavailable với request ID thay vì JSON trên.

## 14. Referral với Spring Data LDAP entity/repository

Các entity Spring Data LDAP ánh xạ entry theo DN, `@Entry` và `@Attribute`. Ví dụ:

~~~java
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
    private String fullName;

    // Getter/setter được bổ sung trong project thật.
}
~~~

Với hai ContextSource khác base, **cùng một annotation `@Entry(base="ou=people")`** có thể ánh xạ các entry tại hai vùng khác nhau. Entity không chứa “danh tính đăng nhập”; môi trường kết nối quyết định server, base và Bind account.

**Chú ý khi dùng repository:**

- Một repository không tự quyết định credentials theo `@Entry`; nó phụ thuộc `LdapOperations`/`LdapTemplate` và ContextSource được cấu hình.
- Nếu có nhiều `LdapTemplate`/repository manager, cần wiring rõ ràng bằng `@Qualifier` và cấu hình repository theo vùng; tránh để dependency injection chọn nhầm target.
- `@Id` giữ DN của entry. Đối với thao tác giữa hai vùng, có thể cùng giá trị `uid` nhưng DN khác, do đó phải dùng khóa nghiệp vụ gồm **region + DN/uid theo chính sách**.
- Không coi việc tìm thấy `objectClass=inetOrgPerson` ở server B là chứng cứ người dùng có quyền HTTP tại A.
- Không trả trực tiếp entity cho HTTP client nếu có DN, thông tin quyền, thuộc tính nhạy cảm; map sang DTO được kiểm soát.

## 15. Rủi ro đặc biệt khi referral phát sinh từ thao tác ghi

Referral không chỉ xuất hiện trong Search. Theo RFC 4511, server có thể trả referral cho nhiều operation LDAP. Với `Add`, `Modify`, `Delete` hoặc `Modify DN`, theo referral có nghĩa ứng dụng có thể **ghi vào máy chủ khác**.

Ví dụ ứng dụng gọi cập nhật email cho:

~~~text
uid=anna,ou=people,dc=emea,dc=example,dc=org
~~~

Nếu server core không có quyền xử lý và trả referral sang EMEA, việc tự động follow với credential writer của core có thể:

- Gửi mật khẩu writer của core tới server khác.
- Ghi vào một entry khác naming context dự kiến.
- Dẫn đến xung đột dữ liệu, ghi một phần hoặc ghi vào hệ thống không được phép.
- Gây khó kiểm toán khi log chỉ ghi “Modify core” dù thực tế server đích là EMEA.

**Khuyến nghị:** route các thao tác ghi tới đúng authoritative directory **trước khi gọi LDAP**, sử dụng service account riêng có ACL chỉ sửa các thuộc tính cần thiết tại vùng đó. Nếu nhận referral bất ngờ trong thao tác ghi, dừng và đưa vào luồng xử lý/đối soát, không tự động retry hàng loạt.

Không dùng `ContextSourceTransactionManager` như bảo đảm ACID xuyên nhiều LDAP server: Spring LDAP compensating transactions (nếu cấu hình) là **nỗ lực bù trừ ở client**, không cung cấp distributed transaction nguyên tử hay isolation giữa các đích.

## 16. Kiểm thử topology và chính sách credential

Chuẩn bị hai directory test tương ứng LDAP A và B, mỗi directory có schema `inetOrgPerson`, entry `ou=people` và **tài khoản dịch vụ riêng**. Thiết lập referral hoặc continuation reference từ A sang B bằng tính năng của directory test. Một số server cần cấu hình referral entry hoặc superior/subordinate knowledge riêng; không giả định LDIF referral của mọi server giống nhau.

### Fixture tối thiểu theo vùng

LDAP A có:

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
~~~

LDAP B có:

~~~ldif
dn: uid=anna,ou=people,dc=emea,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: anna
cn: Anna Smith
sn: Smith
mail: anna@example.org
~~~

Các entry cha phải tồn tại trước khi nạp người dùng. Dữ liệu trên chỉ là fixture; **không dùng hồ sơ hoặc mật khẩu thật**. Người vận hành cần tạo bind account tại mỗi directory, thiết lập ACL và TLS phù hợp.

### Kiểm chứng trực tiếp bằng ldapsearch

Kết nối **riêng tới từng server**, không dùng tùy chọn tự động chase referral khi chưa kiểm soát đích:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap-core.example.org:636 \
  -D "cn=svc-core-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(uid=lan)" dn uid cn
~~~

Tương tự ở EMEA:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap-emea.example.org:636 \
  -D "cn=svc-emea-reader,ou=service,dc=emea,dc=example,dc=org" -W \
  -b "ou=people,dc=emea,dc=example,dc=org" -s one \
  "(uid=anna)" dn uid cn
~~~

`-W` yêu cầu nhập mật khẩu tại lời nhắc, tránh đặt mật khẩu vào tham số command. Kiểm tra rằng:

1. Core credential chỉ được dùng ở Core; EMEA credential chỉ được dùng ở EMEA.
2. Mỗi tài khoản được ACL giới hạn đúng OU/attribute mà ứng dụng cần đọc.
3. Chứng chỉ TLS có tên host hợp lệ, CA được tin cậy; không bật chế độ bỏ qua xác minh.
4. Với `follow=throw`, một referral bất ngờ dẫn đến lỗi/nhánh policy; không có kết nối mới được mở tự động đến host khác.
5. Lỗi một vùng không được chuyển thành kết quả rỗng của cả topology.

### Ma trận kiểm thử bảo mật

| Tình huống | Kỳ vọng |
| --- | --- |
| Search CORE hợp lệ | Bind bằng `svc-core-reader`, trả đúng entry core. |
| Search EMEA hợp lệ | Bind bằng `svc-emea-reader`, trả đúng entry EMEA. |
| Referral A → B được phê duyệt | Hệ thống chỉ nối B theo policy, dùng credential B riêng, không copy secret A. |
| Referral tới `ldap://` plaintext | **Chặn** nếu có mật khẩu hoặc dữ liệu cần bảo vệ; không tự downgrade. |
| Referral đến host không có trong allowlist | **Chặn**, không gọi DNS/kết nối ngoài chính sách nếu có thể ngăn từ trước. |
| Referral đến port bất thường | Chặn, không cho phép kết nối đến dịch vụ tùy ý. |
| Chứng chỉ hết hạn/hostname không khớp | TLS thất bại, không tắt xác minh để retry. |
| Sai mật khẩu B | Chỉ báo lỗi B; không retry bằng mật khẩu A. |
| Referral lặp A → B → A | Dừng do loop/hop limit. |
| Search trả một phần entry rồi referral | Đánh dấu `complete=false` hoặc báo lỗi; không coi là đủ. |
| ACL B cấm đọc `mail` | Không coi `mail=null` là dữ liệu chắc chắn thiếu; không nâng quyền. |
| URL chứa filter/scope rộng hơn | Chỉ thực thi phạm vi đã được nghiệp vụ cho phép. |
| Client HTTP cung cấp URL LDAP tùy ý | Từ chối; chỉ nhận vùng nghiệp vụ đã đăng ký. |
| Referral trong thao tác ghi | Không tự động Modify/Delete server đích ngoài policy. |
| Mất kết nối sau một thao tác ghi | Kiểm tra trạng thái thực tế/đối soát, không retry mù. |
| Nhiều request đồng thời | Không thay credential của ContextSource singleton theo request. |

## 17. Giám sát, audit và xử lý sự cố

Một sự cố liên quan referral có thể là lỗi topology thông thường **hoặc** dấu hiệu thay đổi điểm tin cậy. Vì thế việc ghi log cần đủ thông tin để điều tra mà không chứa secret.

Thông tin có thể ghi (sau khi áp chính sách bảo vệ dữ liệu):

- Request/correlation ID.
- Operation (`Search`, `Add`, `Modify`, `Delete`) và vùng nghiệp vụ.
- Destination ID trong allowlist, không cần log đầy đủ credential hoặc dữ liệu riêng tư.
- Kết quả: `ALLOWED`, `BLOCKED`, `PARTIAL`, `FAILED`, `COMPLETE`.
- Lý do: `UNTRUSTED_TARGET`, `TLS_FAILURE`, `AUTH_FAILURE`, `HOP_LIMIT`, `POLICY_DENIED`.
- Thời gian và số kết quả ở mức tổng hợp, đủ để phát hiện latency hoặc loop bất thường.

**Không log** `Context.SECURITY_CREDENTIALS`, mật khẩu người dùng, LDAP URL chứa dữ liệu nhạy cảm, access token hoặc stack trace đầy đủ vào response HTTP.

Các lỗi thường gặp:

| Triệu chứng | Khả năng | Kiểm tra |
| --- | --- | --- |
| `ReferralException` sau Search | Đã cấu hình `throw` và server giới thiệu vùng khác. | Kiểm tra URL theo policy; không bật follow ngay. |
| `PartialResultException` | Kết quả Search bị thiếu do continuation reference/referral. | Xác định nhu cầu dữ liệu đầy đủ, trạng thái vùng và cách xử lý. |
| `Invalid credentials (49)` ở vùng B | Credential B sai hoặc không hợp lệ tại target. | Kiểm tra secret B, Bind DN B; không dùng lại secret A. |
| `Insufficient access (50)` | Bind thành công nhưng ACL không cho operation/attribute. | Kiểm tra tài khoản B trong phạm vi OU và thuộc tính cần đọc. |
| TLS/SSL handshake failure | CA/hostname/SAN hoặc cấu hình TLS sai. | Kiểm tra truststore và certificate, không tắt xác minh. |
| Referral đi lặp lại | A → B → A hoặc topology sai. | Hop limit, visited set và log topology; dừng retry. |
| Kết quả người dùng “biến mất” | Chưa theo continuation reference hoặc query sai base. | So sánh trực tiếp từng directory bằng Bind DN phù hợp. |
| Truy vấn quá chậm | Referral nhiều hop, mạng xa hoặc Search SUBTREE quá rộng. | Giới hạn size/time/scope, theo dõi latency từng vùng. |
| API trả 200 nhưng thiếu vùng EMEA | Bỏ qua partial result hoặc nuốt exception. | Bổ sung `complete`/`failedRegions` hoặc trả lỗi theo hợp đồng. |
| Identity lẫn giữa các request | Đổi username/secret của ContextSource singleton trong runtime. | Dùng các bean/credential riêng, không mutate config dùng chung. |

## 18. Checklist trước khi đưa vào môi trường chia sẻ

| Mục | Tiêu chí đạt |
| --- | --- |
| Topology | Danh sách authoritative server và naming context được kiểm soát. |
| Referral policy | Đã chọn `throw`/`ignore`/`follow` một cách có chủ đích, không phụ thuộc default mơ hồ. |
| Endpoint allowlist | Scheme, host, port, base DN, scope và operation được kiểm soát. |
| Credential | Mỗi target có Bind DN/secret riêng, quyền tối thiểu, cơ chế xoay vòng. |
| TLS | Xác minh certificate chain, hostname và không fallback sang plaintext. |
| Network | Egress giới hạn, có biện pháp chống SSRF và DNS/IP bất ngờ. |
| Partial results | Không biến lỗi referral thành kết quả đầy đủ giả. |
| Loop/timeouts | Có hop limit, time limit, size limit và cơ chế phát hiện lặp. |
| Search filter | Dùng `LdapQueryBuilder`, không nối filter bằng input tự do. |
| DN | Xây bằng `LdapNameBuilder`, không để client chọn naming context. |
| HTTP | Phân quyền theo actor và vùng; không dựa vào việc service account Bind thành công. |
| Audit | Có correlation ID, destination ID, trạng thái mà không lộ secret. |
| Integration test | Đã thử referral tin cậy/không tin cậy, TLS, ACL, loop và partial result. |

## 19. Bài tập và câu hỏi tự đánh giá

**Bài 1 – Ba chính sách JNDI.** Dự đoán hành vi khác nhau của `ignore`, `follow` và `throw` nếu LDAP A trả continuation reference sang LDAP B. Với mỗi lựa chọn, nêu tác động lên tính đầy đủ của Search và rủi ro credential.

**Bài 2 – Credential theo vùng.** Dùng hai `LdapContextSource` như mục 9, mỗi nguồn có Bind DN và mật khẩu riêng. Test `Region.CORE` và `Region.EMEA`. Thử cố tình đặt sai secret B và chứng minh lỗi B **không** kích hoạt retry bằng secret A.

**Bài 3 – Chặn referral không tin cậy.** Trong directory test, tạo referral đến `ldap://unknown.example.invalid:389`. Kiểm tra ứng dụng không thiết lập kết nối tới host đó, không bỏ qua lỗi rồi kết luận “không có user”.

**Bài 4 – Rà soát ranh giới quyền.** Giả sử người dùng HTTP được xem vùng Core nhưng không được xem EMEA. Thiết kế lớp authorization kiểm tra `Region` **trước** khi chọn `LdapTemplate`, dù EMEA service account có quyền Search.

**Bài 5 – Kết quả một phần.** Thiết kế response DTO chứa `complete`, `searchedRegions`, `failedRegions` và danh sách DTO người dùng. Bổ sung unit test khi một vùng mất kết nối.

**Bài 6 – Referral trong Modify.** Giả sử thao tác sửa `mail` được referral từ A sang B. Nêu ba lý do không nên tự động gửi Modify đến B và thiết kế workflow idempotent/đối soát nếu vùng B là authoritative directory.

### Câu hỏi tự ôn

1. Referral khác SearchResultReference ở điểm nào?
2. Một LDAP referral URL có thể chứa những thành phần nào ngoài hostname?
3. Vì sao `java.naming.referral=follow` không tự bảo đảm credential an toàn?
4. Vì sao `getReferralContext()` không tham số cần thận trọng khi context nguồn đã có mật khẩu Bind?
5. `spring.ldap.referral` được hỗ trợ từ phiên bản Spring Boot nào trong nhánh 3.x? Phương án thay thế khi phiên bản cũ không có property là gì?
6. Tại sao `setIgnorePartialResultException(true)` có thể gây hiểu nhầm kết quả?
7. Nên định danh người dùng liên vùng bằng một `uid` trần hay tổ hợp vùng và định danh LDAP? Vì sao?
8. Nếu TLS server B lỗi chứng chỉ, có được fallback sang `ldap://` hoặc tắt xác minh không?
9. Vì sao một tài khoản LDAP được phép đọc email ở Core không tự có quyền đó ở EMEA?
10. Trong ứng dụng có repository và nhiều `LdapTemplate`, phải kiểm tra wiring nào?
11. Làm sao chống referral loop và kết nối tới địa chỉ mạng bị cấm?
12. Vì sao referral trong Add/Modify/Delete cần chính sách nghiêm ngặt hơn việc tra cứu?

**Ghi nhớ:** referral là một **đề nghị chuyển thao tác LDAP sang đích khác**, không phải chứng chỉ tin cậy. **Không tự động chuyển Bind DN và secret sang bất kỳ referral URL nào.** Hãy dùng `throw` hoặc chiến lược được kiểm soát, allowlist đích, TLS, credential riêng, ACL tối thiểu, giới hạn hop và đánh dấu kết quả chưa đầy đủ; với Spring Data LDAP, cần nối đúng repository/`LdapTemplate` với `ContextSource` của từng vùng.

### Tài liệu tham khảo

- [RFC 4511 – Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): referral result code, SearchResultReference và quy tắc follow/loop.
- [RFC 4516 – LDAP: Uniform Resource Locator](https://www.rfc-editor.org/rfc/rfc4516): thành phần LDAP URL dùng trong referral.
- [RFC 4513 – LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): xác thực, bảo mật kết nối và Bind.
- [Oracle JNDI LDAP Provider Guidelines](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html): `java.naming.referral` với `ignore`/`follow`/`throw`.
- [Java ReferralException API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ReferralException.html): `getReferralInfo()` và `getReferralContext(env)`.
- [Spring LDAP – Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, referral policy và `LdapTemplate`.
- [Spring LDAP – AbstractContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): `setReferral(String)`.
- [Spring Boot 3.5 – Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.ldap.referral` và `spring.ldap.template.ignore-partial-result-exception`.
- [Spring Data LDAP – Reference](https://docs.spring.io/spring-data/ldap/reference/): mapping `@Entry`, repository và thao tác với entry.
