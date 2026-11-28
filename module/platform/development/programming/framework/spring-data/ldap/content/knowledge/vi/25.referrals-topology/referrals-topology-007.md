# Replication, nhiều naming context và giới hạn tìm kiếm xuyên miền

Trong ứng dụng **Spring Data LDAP**, truy vấn người dùng bằng `LdapRepository` hoặc `LdapTemplate` thường bắt đầu từ một **base DN** và một LDAP server cụ thể. Khi hệ thống chỉ có một nhánh `ou=people,dc=example,dc=org`, mô hình này khá dễ hình dung. Nhưng trong doanh nghiệp, danh tính có thể được chia giữa nhiều **naming context**, nhiều LDAP server, các bản sao (replica) và nhiều domain của **Active Directory (AD)**. Khi đó, gọi một lệnh `SUBTREE` không mặc nhiên có nghĩa đã tìm thấy mọi người dùng trong toàn bộ tổ chức.

Bài thuộc chương **Referrals và topology** này làm rõ ba khái niệm thường bị nhầm lẫn: **replication**, **naming context/partition** và **LDAP referral**. Người học sẽ biết một server thực sự giữ dữ liệu nào, vì sao truy vấn có thể trả referral hoặc kết quả từng phần, cách lựa chọn **Global Catalog** trong AD, thiết kế các `ContextSource` độc lập trong Spring LDAP, cách hợp nhất kết quả an toàn, xử lý độ trễ đồng bộ và kiểm thử với directory. Các ví dụ kết hợp kiến thức về DN, `objectClass`, schema, ODM, repository, LDAP filter, ACL và TLS của module **SPRING_DATA_LDAP**.

> **Nguyên tắc:** **replica** là bản sao dữ liệu; **naming context** xác định một phần không gian tên directory; **referral** là chỉ dẫn sang nơi khác để tiếp tục thao tác. Ba khái niệm có thể xuất hiện đồng thời nhưng **không thay thế nhau**.

## 1. Tình huống: một ứng dụng, nhiều miền danh tính

Giả sử doanh nghiệp có hai domain thuộc một AD forest:

```text
Forest: corp.example.org
│
├── Domain gốc: corp.example.org
│   Naming context: dc=corp,dc=example,dc=org
│   DC: dc-root-01.corp.example.org
│   └── ou=people
│       └── cn=An Nguyen
│
└── Domain con: apac.corp.example.org
    Naming context: dc=apac,dc=corp,dc=example,dc=org
    DC: dc-apac-01.apac.corp.example.org
    └── ou=people
        └── cn=Binh Tran
```

Ứng dụng cần hiển thị hai người dùng trong một danh sách. Về mặt cú pháp DN, tên của domain con kết thúc bằng hậu tố tên domain gốc; tuy nhiên **đây là hai domain naming context riêng**, không có bảo đảm rằng một search SUBTREE vào domain controller của domain gốc sẽ trả mọi entry từ domain con.

Giả sử một lệnh truy vấn:

```ldap
Base DN: dc=corp,dc=example,dc=org
Scope:   SUBTREE
Filter:  (objectClass=user)
```

Trên một **domain controller LDAP thường** của domain gốc, client có thể chỉ nhận kết quả thuộc partition mà DC có khả năng phục vụ, cùng referral/continuation reference cho partition khác. Kết quả cuối phụ thuộc topology, server, phạm vi, quyền và xử lý referral. **SUBTREE quy định độ sâu của search trong dữ liệu được server phục vụ; nó không phải một lệnh JOIN các domain.**

Ví dụ này dùng **`CN=...` và `objectClass=user` theo AD**. Với OpenLDAP và `inetOrgPerson`, cây và attribute truy vấn có thể khác. Không áp dụng máy móc một filter hoặc công thức DN cho mọi sản phẩm.

## 2. Thuật ngữ nền tảng: DIT, DN, naming context và partition

LDAP lưu entry trong **Directory Information Tree (DIT)**. Mỗi entry có một **Distinguished Name (DN)** được tạo từ các Relative Distinguished Name (RDN) theo đường từ entry lên gốc tên.

```text
dn: cn=An Nguyen,ou=people,dc=corp,dc=example,dc=org
    └── RDN     └─ OU ─┘└──── domain suffix ────┘
```

Cần phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| **DN** | `cn=An Nguyen,ou=people,dc=corp,dc=example,dc=org` | Tên định vị một entry trong cây |
| **RDN** | `cn=An Nguyen` | Thành phần tên dưới parent |
| **Naming context (NC)** | `dc=corp,dc=example,dc=org` | Phần không gian tên mà một directory server phục vụ dưới dạng một vùng dữ liệu |
| **Domain naming context** trong AD | `dc=apac,dc=corp,dc=example,dc=org` | Partition tương ứng domain AD |
| **Context base** của Spring LDAP | `dc=corp,dc=example,dc=org` | Tiền tố DN được client đặt để các API dùng DN tương đối |
| **Search base** | `ou=people` | Vị trí bắt đầu truy vấn tương đối với context base |
| **Search scope** | `OBJECT`, `ONELEVEL`, `SUBTREE` | Chỉ entry gốc, con trực tiếp hoặc toàn cây con được truy vấn |
| **LDAP endpoint** | `ldaps://dc-root-01.corp.example.org:636` | Server/port mà client kết nối |
| **Replica** | `dc-root-02` giữ bản sao của NC domain gốc | Bản sao dữ liệu được replication |
| **Referral** | URL LDAP trỏ tới server/NC khác | Gợi ý nơi có thể tiếp tục thao tác |

Trong tài liệu vận hành, **partition**, **suffix**, **naming context** thường xuất hiện gần nghĩa nhau, nhưng mức độ tương đương tùy sản phẩm. Đừng tự đồng nhất **DNS zone**, **AD domain**, **LDAP naming context** và **server vật lý**: một server có thể phục vụ nhiều naming context, còn một naming context có thể được nhân bản tới nhiều server.

### Ví dụ nhiều naming context trên cùng một server

Một AD domain controller thường giữ ít nhất:

- **Domain NC** của domain nó tham gia.
- **Configuration NC** của forest.
- **Schema NC** của forest.
- Có thể thêm **application directory partition** hoặc phần dữ liệu tùy cấu hình.

Do đó một server có thể báo nhiều giá trị trong RootDSE `namingContexts`. Điều này **không đồng nghĩa** server chứa bản sao đầy đủ, có quyền ghi, hoặc có thể tìm tất cả user của toàn forest.

## 3. Replication là sao chép dữ liệu, không phải mở rộng base DN

**LDAP replication** là quá trình giữ những bản sao dữ liệu directory gần nhau về trạng thái. Ví dụ domain gốc có hai domain controller:

```text
                  Logical NC
         dc=corp,dc=example,dc=org
                      │
             replication topology
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
     dc-root-01               dc-root-02
     Bản sao NC               Bản sao NC
          ▲                       ▲
          └──── thay đổi được đồng bộ ────┘
```

Ở **AD DS**, replication giữa nhiều writable domain controller thường là **multi-master** đối với các đối tượng và thuộc tính được phép ghi, có cơ chế xử lý xung đột/metadata riêng. Ở **OpenLDAP**, topology có thể dùng `syncrepl` và các mô hình provider/consumer, multi-provider hay bản sao chỉ đọc tùy cấu hình. **Không kết luận mọi LDAP server đều cho ghi trên mọi replica.**

Replication có thể tạo ra các tình huống:

1. `dc-root-01` nhận một thay đổi `mail`.
2. Ứng dụng đọc `dc-root-02` ngay sau đó.
3. Bản sao thứ hai **chưa nhận thay đổi**, nên search trả giá trị cũ.
4. Sau khi replication hội tụ, hai server trả cùng trạng thái.

Đây là vấn đề **replication lag/read-after-write consistency**, khác với LDAP referral. Client có thể nhận kết quả **thành công nhưng cũ** mà không có referral hay exception nào.

| Tình huống | Replication giải quyết được gì? | Replication không tự giải quyết |
|---|---|---|
| DC/LDAP node A ngừng hoạt động | Có thể truy cập bản sao khác khi topology cho phép | Client vẫn cần failover, DNS, TLS và chính sách kết nối |
| Tải đọc lớn | Có thể phân tán request sang replica phù hợp | Không sửa filter rộng, search thiếu index hoặc N+1 |
| Viết rồi đọc ngay | Dữ liệu có thể hội tụ sau replication | Không bảo đảm tức thời ở replica khác |
| Tìm kiếm domain khác | Một số topology có bản sao một phần/cơ chế riêng | Không mặc định nối mọi naming context |
| Truy vấn attribute nhạy cảm | Replica chỉ trả theo ACL/schema của nó | Không bỏ qua ACL hoặc quyền của người gọi |

### Failover không phải federation

Trong một `ContextSource`, danh sách URL có thể được dùng để lựa chọn/failover giữa **những endpoint tương đương về mặt dữ liệu và chính sách**. Nó không có nghĩa “hãy hỏi cả server domain gốc lẫn domain con rồi ghép kết quả”.

Nếu hai URL phục vụ **hai naming context khác nhau**, dùng chúng như những endpoint failover thay thế cho cùng một context base có thể tạo kết quả sai hoặc `noSuchObject`. Muốn truy vấn cả hai phải thiết kế **fan-out** rõ ràng, như phần sau.

## 4. Referral là chỉ dẫn chuyển hướng, không phải bản sao dữ liệu

Theo LDAP protocol, server có thể thông báo rằng nó **không thể hoặc không muốn thực hiện** operation và chỉ dẫn sang server/dịch vụ khác bằng **referral**. Một referral có thể chứa một hoặc nhiều LDAP URI.

Ví dụ minh họa:

```text
Client ── Search dưới dc=corp,... ──> DC domain gốc
                                         │
                                         ├─ Entry thuộc NC local
                                         │
                                         └─ Reference:
                                            ldap://dc-apac-01.apac.corp.example.org/
                                            dc=apac,dc=corp,dc=example,dc=org
```

Trong giao thức LDAP, cần phân biệt hai dạng phản hồi liên quan:

| Loại phản hồi | Khi nào có thể xuất hiện | Ý nghĩa |
|---|---|---|
| **Referral result code** | Server không thể phục vụ operation theo request, ví dụ target base không được giữ tại đây | Client có thể thử LDAP URI được giới thiệu |
| **SearchResultReference (continuation reference)** | Server tìm được search base nhưng muốn client tiếp tục truy vấn một vùng không local | Đang duyệt search mà gặp phạm vi khác |
| **Kết quả search hoàn tất** | Server đã trả các entry và hoàn tất trong phạm vi của request được phục vụ | Không tự chứng minh đã khảo sát mọi naming context của tổ chức |

RFC 4511 mô tả cả referral và `SearchResultReference`. **Không coi reference là entry thông thường**, cũng không cho rằng mọi LDAP client có thể tự theo những URL được giới thiệu một cách chính xác trong mọi topology.

### Referral URL có thể chứa nhiều thông tin hơn hostname

Theo RFC 4516, một LDAP URL có thể biểu diễn **server, DN, attribute list, scope và filter**. Ví dụ:

```text
ldap://ldap-b.example.org/dc=other,dc=example,dc=org??sub?(uid=u1001)
```

Từng phần của URL ảnh hưởng request tiếp theo. Không được chỉ trích xuất hostname rồi giữ nguyên mọi tham số một cách thiếu kiểm soát. Ngược lại, cũng không cho server bên ngoài tự quyết định filter hoặc base vượt phạm vi nghiệp vụ của ứng dụng.

**Referral không phải bảo đảm server đích sẽ chấp nhận cùng credentials**, hoặc sẽ cho thấy cùng các thuộc tính. Endpoint có thể thuộc tổ chức/chính sách khác, không hỗ trợ TLS tương thích, hoặc bị mạng/firewall từ chối.

## 5. Khám phá những naming context thực có qua RootDSE

**RootDSE** là một entry đặc biệt của LDAP server có DN rỗng (`""`), được dùng để công bố các khả năng và một số metadata của server hiện kết nối. Ở AD có nhiều thuộc tính giúp mô tả topology.

Các attribute thường cần hỏi:

| RootDSE attribute | Ý nghĩa thường gặp |
|---|---|
| `namingContexts` | Danh sách các naming context mà **server này** công bố/giữ |
| `supportedControl` | LDAP controls server hỗ trợ |
| `supportedExtension` | Các extended operations được công bố |
| `defaultNamingContext` (AD) | Domain NC mặc định của DC đang hỏi |
| `rootDomainNamingContext` (AD) | NC của forest root domain |
| `configurationNamingContext` (AD) | NC Configuration của forest |
| `schemaNamingContext` (AD) | NC Schema của forest |
| `dnsHostName` (AD) | Hostname DC hiện kết nối |
| `isGlobalCatalogReady` (AD) | Trạng thái GC của server khi thuộc tính có mặt |

Thử đọc RootDSE trong môi trường test được cấp quyền, qua **LDAPS với xác minh chứng chỉ**:

```bash
ldapsearch -LLL -x \
  -H ldaps://dc-root-01.corp.example.org:636 \
  -D 'cn=svc-reader,ou=service-accounts,dc=corp,dc=example,dc=org' -W \
  -b '' -s base '(objectClass=*)' \
  namingContexts supportedControl supportedExtension \
  defaultNamingContext rootDomainNamingContext \
  configurationNamingContext schemaNamingContext dnsHostName
```

**Khi đọc kết quả:**

- RootDSE phải được hỏi tại **base DN rỗng**, không phải `dc=corp,...`.
- `namingContexts` là thông tin của **endpoint đang hỏi**, không phải danh sách đầy đủ mọi domain trong doanh nghiệp.
- Một vài attribute là đặc thù AD, nên có thể **không có** trên OpenLDAP.
- Sự xuất hiện của NC trong RootDSE chưa cho biết bạn có quyền đọc/ghi toàn bộ NC.
- Một domain controller và một global catalog endpoint của cùng máy có thể có **phạm vi và mức độ đầy đủ dữ liệu khác nhau**.

**Trong Spring LDAP:** nếu `LdapContextSource` đã được cấu hình `base=dc=corp,dc=example,dc=org`, gọi `ldapTemplate.lookup("")` thường truy cập **entry ở context base**, không phải RootDSE. Để khám phá RootDSE, hãy dùng một context thích hợp với base rỗng hoặc công cụ LDAP độc lập.

## 6. Base DN và scope: chúng giới hạn một truy vấn như thế nào?

Giả sử `LdapContextSource` có context base:

```text
dc=corp,dc=example,dc=org
```

Còn query Spring LDAP sử dụng:

```java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson");
```

Lúc này search base thực tế là `ou=people,dc=corp,dc=example,dc=org`. Những DN truyền vào API Spring LDAP thường được diễn giải **tương đối với base path đã cấu hình**.

| Scope | Đọc những entry nào? | Rủi ro khi hiểu sai |
|---|---|---|
| `OBJECT` | Chính entry tại search base | Không tìm con |
| `ONELEVEL` | Con trực tiếp của search base | Bỏ qua user nằm sâu trong OU con |
| `SUBTREE` | Entry tại base và các descendant mà server có thể search | Không bảo đảm vượt qua naming context/referral/ACL |
| Search domain root | Có thể thấy OU/user thuộc domain NC local | Không mặc nhiên có toàn bộ domain khác |

**Truy vấn SUBTREE không thay đổi địa giới dữ liệu server giữ.** Trong AD forest có nhiều domain NC, NC của domain con **không trở thành các entry local của domain gốc** chỉ vì DN có hậu tố tương tự.

Cũng không nên tăng scope từ `ONELEVEL` lên `SUBTREE` hoặc đổi search base sang forest root chỉ để “chắc chắn tìm được”. Mọi thay đổi phạm vi cần có **authorization**, ngân sách query, quy tắc xử lý referral và test riêng.

## 7. Xử lý referral trong JNDI và Spring LDAP

Spring LDAP sử dụng **JNDI** ở tầng kết nối. Java JNDI cho phép cấu hình `Context.REFERRAL` với các giá trị `ignore`, `follow`, `throw`; Spring LDAP cung cấp setter `LdapContextSource.setReferral(...)` tương ứng.

| Chế độ | Hành vi tổng quát | Lưu ý |
|---|---|---|
| `ignore` | Không tự theo referral | Có thể nhận `PartialResultException` hoặc kết quả không đầy đủ tùy provider/server |
| `follow` | JNDI cố tự theo referral | Cần DNS, routing, TLS, credential và giới hạn an toàn; không nên bật tùy tiện |
| `throw` | Để referral thể hiện thành exception ở tầng JNDI | Phù hợp khi muốn phát hiện rõ nơi query không local, nhưng cần quản lý error handling |

Trong Spring LDAP, mặc định `AbstractContextSource` là `ignore` theo Javadoc. Đừng suy rằng mặc định này đồng nghĩa “mặc định trả kết quả đầy đủ và không lỗi”.

### Ví dụ cấu hình rõ chế độ

```java
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setUserDn("cn=svc-reader,dc=example,dc=org");
source.setPassword(secret);
source.setReferral("throw");  // Không bật auto-follow.
source.setPooled(false);
```

Đoạn trên **minh họa setter**, không phải một bean hoàn chỉnh: nếu tự khởi tạo source ngoài Spring container, cần hoàn tất lifecycle (`afterPropertiesSet()`) trước khi gọi LDAP. Trong Spring, có thể khai báo source thành `@Bean` để container quản lý.

### Vì sao `ignorePartialResultException(true)` nguy hiểm nếu hiểu sai?

Spring LDAP có tùy chọn:

```java
LdapTemplate template = new LdapTemplate(source);
template.setIgnorePartialResultException(false);
template.setIgnoreSizeLimitExceededException(false);
```

`setIgnorePartialResultException(true)` là workaround cho một số môi trường AD gặp `PartialResultException` khi referral không được xử lý. Nhưng nó **không tự tìm kiếm nốt các domain bị tham chiếu**. Bỏ qua exception có thể dẫn tới một danh sách **chỉ chứa kết quả đã lấy được**, đặc biệt nguy hiểm khi xác thực user, đồng bộ danh tính hoặc quyết định quyền.

Tương tự, `setIgnoreSizeLimitExceededException(true)` có thể khiến ứng dụng chỉ thấy phần dữ liệu đã đọc trước khi chạm giới hạn; nếu nghiệp vụ cần tập kết quả đầy đủ, hãy cấu hình phát hiện lỗi hoặc giải quyết bằng paging/giới hạn hợp lệ.

**Chính sách gợi ý:** đối với nghiệp vụ đòi tính đầy đủ, để lỗi referral/partial/size-limit **hiển thị rõ** và chọn cơ chế truy vấn khác được kiểm soát. Chỉ chấp nhận partial result khi API **công bố rõ** phạm vi không đầy đủ và không dùng nó cho quyết định bảo mật.

## 8. Theo referral tự động có rủi ro bảo mật gì?

Một referral không đáng tin có thể trỏ tới:

```text
ldap://unexpected.example.net/dc=other,dc=net
```

Nếu cấu hình `follow` tùy tiện:

- Client có thể kết nối tới **endpoint ngoài allowlist** do server khác chỉ ra.
- Có rủi ro gửi **bind credentials** hoặc dữ liệu truy vấn tới server không được tin cậy, tùy JNDI/provider và cơ chế xác thực.
- `ldap://` có thể tạo **kết nối không TLS** nếu không có chính sách bắt buộc StartTLS, làm lộ dữ liệu trong một số cấu hình.
- DNS hoặc certificate của referral target có thể khác endpoint ban đầu.
- Referral có thể tạo **vòng lặp hoặc chuỗi chuyển hướng sâu**, tăng latency và quá tải.
- Base/filter hoặc dữ liệu tìm kiếm có thể bị mở rộng ngoài **phạm vi đã duyệt**.
- Các domain có thể không cùng ACL, tài khoản hoặc trust boundary.

RFC 4511 yêu cầu client theo referral phải tránh lặp vô hạn. Trong ứng dụng danh tính, nguyên tắc phòng vệ thực tế là **không auto-follow referral tùy tiện**.

Nếu nghiệp vụ buộc phải theo referral, hãy xác nhận cơ chế client có hỗ trợ đầy đủ: allowlist endpoint, cơ chế cấp credential **riêng từng nguồn**, TLS xác minh server đích, tối đa số hop, deadline tổng, giới hạn scope/filter, log đường đi và phát hiện loop. Với `LdapTemplate`, đừng coi nó là một công cụ orchestration referral có khả năng kiểm soát tinh vi; khi topology phức tạp, **kết nối tường minh tới các endpoint đã duyệt** thường dễ kiểm chứng hơn.

**Referral không phải cơ chế xác thực xuyên domain.** AD forest trust và các giao thức xác thực có chính sách riêng; không được tự động chuyển mật khẩu/ngữ cảnh người dùng sang một hostname do LDAP referral chỉ tới.

## 9. Thiết kế tường minh: hai ContextSource cho hai domain NC

Một cách triển khai dễ hiểu trong Spring Boot là cấu hình **hai `LdapContextSource` và hai `LdapTemplate`**, mỗi cặp có endpoint, context base và principal bind được quản lý riêng.

```text
                 DirectorySearchService
                           │
             ┌─────────────┴──────────────┐
             │                            │
        rootLdapTemplate             apacLdapTemplate
             │                            │
       rootContextSource            apacContextSource
             │                            │
      DC phục vụ root NC            DC phục vụ apac NC
             │                            │
    dc=corp,dc=example,dc=org      dc=apac,dc=corp,...
```

### Cấu hình `application.yml` minh họa

```yaml
app:
  directory:
    root:
      url: ldaps://dc-root-01.corp.example.org:636
      base: dc=corp,dc=example,dc=org
      bind-dn: cn=svc-reader,ou=service-accounts,dc=corp,dc=example,dc=org
      password: ${LDAP_ROOT_READER_PASSWORD}
    apac:
      url: ldaps://dc-apac-01.apac.corp.example.org:636
      base: dc=apac,dc=corp,dc=example,dc=org
      bind-dn: cn=svc-reader,ou=service-accounts,dc=apac,dc=corp,dc=example,dc=org
      password: ${LDAP_APAC_READER_PASSWORD}
```

Các URL và DN ở trên là **ví dụ logic**. Directory thật có thể dùng dịch vụ tìm kiếm ở OU khác, cách bind principal khác hoặc yêu cầu SASL/Kerberos. Không tạo hai service account mà không kiểm tra quyền và bảo mật của từng domain.

### Hai ContextSource và hai LdapTemplate độc lập

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class MultiDomainLdapConfiguration {

    @Bean("rootContextSource")
    public LdapContextSource rootContextSource(
            @Value("${app.directory.root.url}") String url,
            @Value("${app.directory.root.base}") String base,
            @Value("${app.directory.root.bind-dn}") String dn,
            @Value("${app.directory.root.password}") String password) {
        return newSource(url, base, dn, password);
    }

    @Bean("apacContextSource")
    public LdapContextSource apacContextSource(
            @Value("${app.directory.apac.url}") String url,
            @Value("${app.directory.apac.base}") String base,
            @Value("${app.directory.apac.bind-dn}") String dn,
            @Value("${app.directory.apac.password}") String password) {
        return newSource(url, base, dn, password);
    }

    private static LdapContextSource newSource(
            String url, String base, String bindDn, String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setReferral("throw");
        source.setPooled(false);
        return source;
    }

    @Bean("rootLdapTemplate")
    public LdapTemplate rootLdapTemplate(
            @Qualifier("rootContextSource") ContextSource source) {
        return newTemplate(source);
    }

    @Bean("apacLdapTemplate")
    public LdapTemplate apacLdapTemplate(
            @Qualifier("apacContextSource") ContextSource source) {
        return newTemplate(source);
    }

    private static LdapTemplate newTemplate(ContextSource source) {
        LdapTemplate template = new LdapTemplate(source);
        template.setIgnorePartialResultException(false);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

**Những gì ví dụ bảo đảm về mặt thiết kế:**

1. Hai template **không chia sẻ cùng endpoint/base/principal**.
2. `setReferral("throw")` tránh mặc định auto-follow; referral cần được xử lý như một vấn đề topology có chủ đích.
3. `setIgnorePartialResultException(false)` giữ tín hiệu thiếu dữ liệu; không âm thầm bỏ phần chưa tìm được.
4. `setIgnoreSizeLimitExceededException(false)` giúp nghiệp vụ thấy lỗi khi kết quả có thể bị cắt.
5. `setPooled(false)` giúp bắt đầu kiểm thử ranh giới rõ ràng, chưa thêm một lớp pooling dễ che lỗi; khi bật pooling phải tách pool theo nguồn và TLS/credential.

Spring container quản lý lifecycle của các bean `LdapContextSource`. Nếu tự tạo source ngoài container, cần cấu hình hoàn chỉnh rồi gọi `afterPropertiesSet()` theo contract. Khi có nhiều bean cùng kiểu, **luôn dùng `@Qualifier`** để tránh wiring nhầm hoặc để auto-configuration chọn một nguồn không như ý. Kiểm tra version Spring Boot/Spring LDAP đang dùng trước khi copy cấu hình nguyên xi.

## 10. Fan-out search: hỏi từng domain rồi hợp nhất

Nếu ứng dụng thực sự cần search **cả hai domain**, hãy định nghĩa thao tác phân tán ở tầng service. Nó **khác** việc đưa nhiều URL vào một context source.

Ví dụ: tìm user có `uid` đúng bằng một giá trị, trả về tên nguồn và DN đầy đủ. Mỗi query giữ base/scope riêng và không tự theo referral.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class MultiDomainPersonSearch {

    public record PersonHit(
            String sourceId,
            String uid,
            String commonName,
            String fullDn
    ) {}

    private final LdapTemplate rootTemplate;
    private final LdapTemplate apacTemplate;

    public MultiDomainPersonSearch(
            @Qualifier("rootLdapTemplate") LdapTemplate rootTemplate,
            @Qualifier("apacLdapTemplate") LdapTemplate apacTemplate) {
        this.rootTemplate = rootTemplate;
        this.apacTemplate = apacTemplate;
    }

    public List<PersonHit> findCandidates(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        List<PersonHit> hits = new ArrayList<>();
        // Nếu một nguồn lỗi, để exception lan lên.
        // KHÔNG trả về như thể đã tìm đủ cả hai domain.
        hits.addAll(inDomain(rootTemplate, "root", uid));
        hits.addAll(inDomain(apacTemplate, "apac", uid));
        return List.copyOf(hits);
    }

    private static List<PersonHit> inDomain(
            LdapTemplate ldap, String sourceId, String uid) {

        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .timeLimit(2500)
                .countLimit(51)
                .attributes("uid", "cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        ContextMapper<PersonHit> mapper = ctx -> {
            DirContextOperations entry =
                    (DirContextOperations) ctx;
            return new PersonHit(
                    sourceId,
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("cn"),
                    entry.getNameInNamespace());
        };

        List<PersonHit> found = ldap.search(request, mapper);
        if (found.size() >= 50) {
            throw new IllegalStateException(
                    "Too many matches; result may be incomplete");
        }
        return found;
    }
}
```

Đoạn code là **ví dụ thiết kế đa nguồn**, chưa phải implementation production đầy đủ. Nó giả định hai domain có cùng schema `inetOrgPerson`, sử dụng `uid` và OU `people`; trong AD thực tế cần điều chỉnh filter/attribute như `objectClass=user`, `sAMAccountName` hoặc `userPrincipalName` theo chính sách từng domain. `timeLimit` chỉ đặt cho từng search; service sản xuất còn cần **deadline tổng**, quota, rate limit và chính sách retry.

### Những điều quan trọng khi hợp nhất kết quả

- **Không coi UID là khóa duy nhất trên mọi domain.** `uid=u1001` có thể tồn tại ở hai nguồn. Dùng `(sourceId, stableObjectId)` hoặc một identity key đã được định nghĩa; DN có thể đổi khi rename/move.
- `getNameInNamespace()` ở mapper trả tên theo namespace của context; cần kiểm chứng dạng DN trên server/adapter đang dùng. `getDn()` thường là DN tương đối với context base.
- Không dùng `cn` làm khóa vì tên hiển thị có thể trùng hoặc thay đổi.
- Nếu source root trả một người và source apac trả một người cùng `uid`, đây là **hai candidates**, không được tự chọn một người khi dùng cho đăng nhập.
- Nếu một source timeout, bị referral/ACL/size-limit hoặc không đủ kết quả, **không trả danh sách thành công giả**. Cần báo lỗi hoặc trả trạng thái *partial* tường minh cho những API cho phép.
- Với fan-out song song, phải có **giới hạn concurrency, deadline, cancellation và ngân sách kết nối**. Ví dụ tuần tự ở trên ưu tiên giải thích rõ flow.

**Lưu ý:** nếu hai endpoint chỉ là **hai replicas của cùng một naming context**, không nên truy vấn cả hai rồi cộng entry như hai miền khác nhau. Khi đó phải xem chúng là cùng một **logical data source**, lựa chọn một replica thích hợp hoặc đối soát kết quả theo chính sách consistency.

## 11. Search một user để đăng nhập: không được chọn ngẫu nhiên domain

Với xác thực LDAP, nhầm naming context có thể dẫn đến **xác thực sai danh tính**. Ví dụ trong hai domain đều có tài khoản `sam`.

Một triển khai an toàn cần:

1. Xác định tenant/domain từ **nguồn tin cậy** như email/UPN được chuẩn hóa, đăng ký danh tính hoặc mapping đã quản lý; không mặc định tên ngắn luôn duy nhất.
2. Search trong **phạm vi domain đã cho phép** với attribute và filter an toàn.
3. Yêu cầu **một DN duy nhất**, không lấy kết quả đầu tiên trong danh sách fan-out.
4. Bind bằng DN và credential của **đúng user** trên kênh TLS phù hợp, hoặc dùng giải pháp xác thực liên miền được tổ chức phê duyệt.
5. Tách LDAP bind authentication khỏi việc đọc group/role và quyền ứng dụng.

**Không thử password lần lượt trên mọi domain và chấp nhận domain đầu tiên bind thành công** nếu điều này không nằm trong chính sách đăng nhập đã xác định. Cách làm đó có thể gây khóa tài khoản, lộ tín hiệu enumeration, nhầm principal và phức tạp hóa audit.

Khi đọc group membership xuyên domain, một group DN có thể trỏ tới đối tượng thuộc NC khác. ODM `@Attribute(name="member")` chỉ ánh xạ **giá trị DN**, không tự resolve cross-domain reference như một SQL foreign key/JPA JOIN.

## 12. Active Directory Global Catalog có giúp tìm toàn forest không?

**Global Catalog (GC)** là dịch vụ tìm kiếm trong AD forest. Nó có thể cung cấp **bản sao một phần** các đối tượng thuộc các domain trong forest, cùng dữ liệu đầy đủ hơn của domain mà DC đang giữ theo vai trò của nó.

Các cổng thường gặp:

| Dịch vụ AD | Cổng | Chú thích |
|---|---|---|
| LDAP trên domain controller | TCP 389 | Có thể dùng StartTLS khi được cấu hình |
| LDAP over TLS trên domain controller | TCP 636 | LDAPS |
| Global Catalog | TCP 3268 | LDAP search GC; phải cân nhắc bảo vệ kết nối |
| Global Catalog over TLS | TCP 3269 | GC qua TLS |

Với việc **tìm người dùng xuyên nhiều domain trong cùng forest**, GC có thể là lựa chọn phù hợp hơn việc tự theo các referrals. Tuy nhiên:

- GC chỉ sao chép **tập thuộc tính một phần** (*Partial Attribute Set*) cho object của những domain khác; thuộc tính không thuộc tập này có thể thiếu.
- Một kết quả GC **không đồng nghĩa** đọc được mọi ACL, group membership, attribute nhạy cảm hoặc thuộc tính phục vụ provisioning.
- GC chủ yếu phục vụ search/discovery. **Không coi endpoint GC là nơi thực hiện mọi LDAP write**.
- Tính mới của dữ liệu GC phụ thuộc replication; kết quả có thể có độ trễ.
- GC không tự mở rộng phạm vi sang **forest khác** chỉ vì có trust.
- Cần kiểm tra domain, `objectGUID`/`objectSid` và các quy tắc identity để không gộp hai người khác nhau.

Ví dụ search minh họa trên GC qua TLS:

```bash
ldapsearch -LLL -x \
  -H ldaps://gc01.corp.example.org:3269 \
  -D 'cn=svc-gc-reader,ou=service-accounts,dc=corp,dc=example,dc=org' -W \
  -b 'dc=corp,dc=example,dc=org' -s sub \
  '(sAMAccountName=u1001)' \
  distinguishedName sAMAccountName cn
```

Các DN, bind account và quyền trong ví dụ phải được **cấu hình theo AD thực tế**. Không mặc định AD cho phép SIMPLE bind hoặc trả mọi thuộc tính theo cùng policy. Đối với thuộc tính không hiện diện trong GC, xác định **domain NC đích** rồi truy vấn domain controller phù hợp thay vì tự kết luận thuộc tính không tồn tại.

### Chiến lược GC + truy vấn trực tiếp

```text
Tìm người trên toàn forest
          │
          ▼
  GC (thông tin định vị)
          │
          ▼
  Xác định domain/object identity
          │
          ├── Cần thuộc tính trong Partial Attribute Set
          │       └── Dùng kết quả GC nếu đủ và được phép
          │
          └── Cần thuộc tính/ghi riêng domain
                  └── Truy cập DC phù hợp qua
                      ContextSource đúng domain, TLS và ACL
```

GC là **công cụ hỗ trợ discovery**, không phải giấy phép để bỏ qua xác thực, phân quyền và policy khác nhau giữa các domain.

## 13. Tính nhất quán khi replication và fan-out

Một nghiệp vụ có thể sửa entry ở writable DC, sau đó truy vấn từ replica hoặc GC khác và thấy dữ liệu cũ.

```text
writeTemplate → writable DC A
                  │
                  ├─ Modify thành công
                  │
                  └─ Replication (có thể chậm)
                          │
                          ▼
                    Read replica B / GC
                          │
                          └─ Có thể trả giá trị cũ
```

Đây là **read-after-write inconsistency**. Các giải pháp tùy nghiệp vụ:

| Nhu cầu | Chiến lược |
|---|---|
| Hiển thị danh sách người dùng ít thay đổi | Có thể chấp nhận eventual consistency với chỉ báo/caching hợp lý |
| Xác nhận email vừa cập nhật | Đọc hậu kiểm từ endpoint ghi hoặc cơ chế được bảo đảm thấy thay đổi |
| Vừa thu hồi quyền quản trị | Tránh dựa vào group cache/GC replica có thể trễ; thiết kế policy bảo mật mạnh hơn |
| Đồng bộ user giữa các hệ thống | Dùng change feed/cookie phù hợp, idempotency và reconciliation |
| Failover sang replica khác | Kiểm tra trạng thái bản sao, topology, read/write policy và độ trễ |

**Không giải quyết bằng cách “search tất cả replicas rồi chọn giá trị có vẻ mới nhất”** khi chưa hiểu version metadata và conflict resolution. Timestamp từ nhiều server cũng không nhất thiết cho một thứ tự toàn cục đáng tin cậy.

Ở Active Directory, `uSNChanged` là metadata liên quan DC; không tự dùng USN từ một DC như đồng hồ chung cho toàn forest. Với server khác, cần hiểu replication generation, cookie và retention của cơ chế tương ứng.

## 14. Multi-domain search không phải một transaction hay một snapshot

Khi service gọi hai domain tuần tự:

```text
T0: Search root domain → 100 entries
T1: Một user move/rename hoặc được tạo/xóa
T2: Search APAC domain → 80 entries
T3: Service hợp nhất → 180 entries
```

Hai kết quả có thể không phản ánh cùng **một thời điểm nguyên tử**. Nếu một user được chuyển giữa các NC trong khoảng T0–T2, có thể tạm **trùng hoặc thiếu** trong tổng hợp tùy trạng thái replication và cơ chế provisioning.

Vì vậy, cần định nghĩa:

- **Logical source** và ownership của từng entry/thuộc tính.
- Định danh ổn định nếu server cung cấp, ví dụ `objectGUID` của AD hoặc `entryUUID` trên một số LDAP server.
- Cách xử lý move/rename và object out of scope.
- Mức độ trễ/độ đầy đủ được phép của API.
- Khi nào phải full reconciliation hay dùng cơ chế đồng bộ theo server.

**Search của LDAP không phải JOIN xuyên domain, và fan-out không tự tạo ACID transaction xuyên NC.** Nếu sản phẩm đòi trạng thái danh tính nhất quán tuyệt đối cho quyết định bảo mật, cần một kiến trúc dữ liệu/authorization phù hợp hơn việc ghép các response search bất kỳ.

## 15. Phạm vi ACL, TLS và secret khi truy cập nhiều domain

Một endpoint hợp lệ về mặt DNS chưa có nghĩa ứng dụng **được phép** truy cập những entry/attribute bên trong.

**Nguyên tắc phân quyền:**

1. Mỗi context source có **tài khoản bind riêng** hoặc cơ chế xác thực được duyệt, chỉ có quyền tối thiểu trên đúng NC.
2. Truy vấn chỉ dùng **attribute allowlist** như `uid`, `cn`, `mail` cần thiết; không tự đồng bộ password, ACL, token hoặc group nhạy cảm.
3. Authorization ở API vẫn phải áp dụng cho người gọi; service account đọc được entry **không đồng nghĩa mọi người dùng web được xem entry đó**.
4. Không chuyển bind credentials từ domain A sang referral URL hoặc domain B trừ khi đã có hợp đồng bảo mật rõ ràng.
5. Bảo vệ secret, không hard-code password trong source code hoặc log.
6. Dùng LDAPS/StartTLS có **chứng chỉ và hostname verification trên từng endpoint**; chuyển host là một trust boundary mới.
7. Khi access control thay đổi và search không thấy entry, không tự kết luận entry bị xóa.

Đặc biệt, **không sử dụng `ignorePartialResultException(true)` rồi dùng kết quả để quyết định thu hồi hoặc cấp quyền**. Kết quả không đủ có thể dẫn đến xác thực sai, xóa nhầm dữ liệu đồng bộ hoặc cho phép truy cập ngoài dự kiến.

### Query an toàn vẫn cần base/scope an toàn

`LdapQueryBuilder.where("uid").is(userInput)` và `EqualsFilter` giúp escape **giá trị** theo cú pháp LDAP filter. Chúng **không giới hạn naming context tự động**. Ngược lại, một base hẹp không sửa được một filter nối chuỗi nguy hiểm.

Dùng đồng thời:

- Base/endpoint cố định hoặc ánh xạ từ tenant/domain đã xác thực.
- Scope phù hợp.
- Filter builder cho giá trị từ input.
- Attribute allowlist và size/time limit.
- ACL/TLS và kiểm tra completeness.

**Escaping DN** phải dùng `LdapNameBuilder`/`LdapName`; không lấy LDAP filter escaping thay cho DN escaping.

## 16. Hiệu năng, paging và ngân sách cho truy vấn đa nguồn

Một search đơn miền có chi phí gần với một LDAP operation logic; fan-out qua N nguồn có thể có **N search hoặc nhiều hơn**, chưa tính paging/referral/retry.

| Chỉ số | Tác dụng |
|---|---|
| Số LDAP search theo source | Biết fan-out tăng tải bao nhiêu |
| Độ trễ p50/p95/p99 theo source | Xác định domain chậm hoặc replica trễ |
| Deadline toàn request | Ngăn một domain treo làm request kéo dài vô hạn |
| Pool active/idle/wait | Ngăn nhiều fan-out chiếm hết connection |
| Số trang và continuation cookie | Kiểm tra đã đọc đủ entry chưa |
| Size/time limit errors | Phát hiện response có thể bị cắt |
| Referral/PartialResultException | Phát hiện phạm vi truy vấn chưa được hoàn tất |
| DNS/TLS/certificate errors | Nhận biết lỗi trust/endpoint |
| Số bản ghi duplicate hoặc collision | Phát hiện nhầm identity hoặc query trùng replicas |
| Replication lag theo nguồn | Giải thích dữ liệu cũ |

**Paging mỗi nguồn khác paging toàn cục.** Nếu ứng dụng gửi `pageSize=50` tới hai source rồi ghép, đó không tự là “trang đầu tiên 50 kết quả” của tập hợp đã sắp xếp toàn cục. Mỗi source có cookie, sort và tính nhất quán riêng; muốn phân trang tổng hợp ổn định cần thiết kế cursor/composite cursor hoặc tầng index tập trung.

**Không đồng nhất một referral hop với một trang LDAP.** Referral là chuyển sang nơi dữ liệu khác; paging là chia một tập search result theo cơ chế control. Cả hai đều có thể phát sinh thêm network round trips.

Khi fan-out song song, nên có concurrency cap và tổng timeout. Không dùng auto-follow referral không giới hạn như một phương án “tăng độ phủ” mà không đo chi phí.

## 17. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| Query SUBTREE không thấy user domain con | DC hiện tại chỉ phục vụ NC domain gốc | Xác minh RootDSE; dùng đúng DC domain con hoặc GC |
| `PartialResultException` khi search AD | JNDI/referral không được xử lý tương thích | Xác định topology, thiết kế explicit multi-source; không chỉ bỏ lỗi |
| Bật `ignorePartialResultException(true)` và thấy ít người | Các referral bị bỏ qua, dữ liệu thiếu | Báo incomplete; truy vấn các NC cần thiết |
| `follow` báo lỗi DNS | Referral host không giải được/tới được | Kiểm tra DNS/routing/endpoint whitelist |
| `follow` bị lỗi TLS hoặc credential | Endpoint đích khác trust domain, cấu hình không tương thích | Dừng auto-follow; cấu hình kết nối riêng |
| RootDSE không trả `defaultNamingContext` | Server không phải AD hoặc không công bố attribute | Dựa vào `namingContexts` và tài liệu server |
| `lookup("")` trả base entry | ContextSource có base khác rỗng | Dùng RootDSE context chuyên biệt |
| GC không trả attribute cần | Attribute không thuộc Partial Attribute Set/ACL | Đọc từ domain DC sau khi định vị object |
| Đọc replica thấy mail cũ | Replication lag | Hậu kiểm trên writable DC hoặc policy consistency |
| Duplicate user sau fan-out | Hai sources cùng NC/replica hoặc login trùng domain | Key theo source + stable identity, kiểm tra ownership |
| Ghi qua GC thất bại | GC không phải endpoint writable phù hợp | Xác định writable DC/NC và ACL |
| Search chỉ trả 1000 entries | Size limit/server policy/paging | Xử lý paging và lỗi completeness; không coi đủ |
| Parent DN giống suffix nhưng search không qua domain con | NC boundary chứ không chỉ cấu trúc RDN | Kiểm tra partition/referral/GC |
| Khi đổi domain, referral loop | Routing/config sai hoặc referral chaining | Giới hạn hop/visited set; dùng explicit targets |
| Group membership chéo domain bị thiếu | Attribute/GC/ACL/primary/nested group khác nhau | Chọn cơ chế group lookup theo từng domain và policy |
| Đổi nhiều URL failover làm mất user | URL phục vụ các NC khác nhau | Tách `ContextSource`, không dùng failover để fan-out |

Một lỗi quan trọng là **coi danh sách rỗng như “không tồn tại người dùng”** khi query thực tế bị ACL, referral hoặc size/time limit. Phân biệt **no match đã hoàn tất** với **cannot determine vì search chưa hoàn tất**.

## 18. Kiểm thử tích hợp topology với directory

Unit test service có thể xác nhận hai `LdapTemplate` được gọi, nhưng **không chứng minh một LDAP server giữ NC nào hoặc referral hoạt động ra sao**. Cần môi trường thử nghiệm có nhiều naming context/endpoint phù hợp, hoặc lab AD/OpenLDAP được cấu hình thật theo kịch bản.

| Ca thử | Thiết lập | Kỳ vọng |
|---|---|---|
| RootDSE của root DC | Hỏi `namingContexts` | Xác nhận NC server công bố |
| RootDSE của child DC | Hỏi `namingContexts` | Xác nhận domain NC riêng |
| Search chỉ root NC | Dùng root context source | Không tự cam kết tìm hết child domain |
| Search chỉ child NC | Dùng child context source | Trả user child đúng scope/ACL |
| Fan-out hai domain | Hai endpoint hợp lệ | Hợp nhất đúng candidates và source ID |
| Hai domain có cùng UID | Tạo hai user cùng login ngắn | Không tự chọn một người làm identity duy nhất |
| Hai replicas của cùng NC | Search cả hai để thử | Nhận biết đây là duplicate logical data source |
| Referral được trả | Search vượt phạm vi server giữ | Phát hiện referral/partial, không bỏ âm thầm |
| Referral tới host lạ | Referral URL nằm ngoài allowlist | Không tự kết nối/gửi credential |
| Referral lặp | Topology cấu hình thử loop | Giới hạn và thất bại có kiểm soát |
| Một domain down | Tắt một endpoint | API cần complete trả lỗi, không thành công giả |
| Bản sao trễ replication | Sửa mail trên writer rồi đọc replica | Hậu kiểm tuân theo consistency policy |
| GC cross-domain search | GC đã sẵn sàng | Tìm được object theo khả năng GC |
| Attribute ngoài GC PAS | Truy vấn thuộc tính không được nhân bản đầy đủ | Không hiểu thiếu attribute là bị xóa |
| Size limit/paging | Nhiều entry hơn một trang | Không công bố kết quả bị cắt là đầy đủ |
| ACL thiếu quyền | Tài khoản bind bị hạn chế trên một NC | Không tự nâng quyền hoặc bỏ qua domain |
| TLS certificate sai | Một host không xác minh được CA/hostname | Fail closed, không fallback cleartext |
| DN có ký tự đặc biệt | RDN chứa dấu phẩy/ngoặc | DN/filter escaping hoạt động đúng |
| Move/rename user | User đổi OU hoặc NC theo workflow test | Identity mapping/cache được cập nhật theo hợp đồng |
| Sort/page tổng hợp | Hai source trả kết quả khác thứ tự | Không giả định page theo từng nguồn là page toàn cục |

### Cách đối chiếu bằng công cụ LDAP

**1. Đọc RootDSE từng endpoint.** Dùng `ldapsearch -b '' -s base` từ phần 5, so `namingContexts` và các attribute AD nếu có.

**2. Search root NC độc lập:**

```bash
ldapsearch -LLL -x \
  -H ldaps://dc-root-01.corp.example.org:636 \
  -D 'cn=svc-reader,ou=service-accounts,dc=corp,dc=example,dc=org' -W \
  -b 'ou=people,dc=corp,dc=example,dc=org' -s sub \
  '(uid=u1001)' uid cn
```

**3. Search child NC độc lập:**

```bash
ldapsearch -LLL -x \
  -H ldaps://dc-apac-01.apac.corp.example.org:636 \
  -D 'cn=svc-reader,ou=service-accounts,dc=apac,dc=corp,dc=example,dc=org' -W \
  -b 'ou=people,dc=apac,dc=corp,dc=example,dc=org' -s sub \
  '(uid=u1001)' uid cn
```

Hai lệnh là **mẫu dùng trong test directory có `uid`/`inetOrgPerson`**; AD thường cần đổi filter. Không dùng tài khoản sản xuất đặc quyền và không thử referral sang host không được phép.

**4. So sánh.** Xác nhận một tìm kiếm root và một tìm kiếm child tạo ra hai tập riêng theo cấu hình; API fan-out phải báo đúng nguồn. Nếu một endpoint không trả đầy đủ, kiểm tra lỗi thay vì kết luận không có user.

## 19. Bài tập tình huống

Một ứng dụng Spring Boot đang có duy nhất một `LdapContextSource`:

```text
url  = ldaps://dc-root-01.corp.example.org:636
base = dc=corp,dc=example,dc=org
referral = ignore
```

Công ty bổ sung domain `apac.corp.example.org`. Đội phát triển tăng search scope lên `SUBTREE` để “tìm mọi nhân viên”, nhưng API vẫn không thấy một số user APAC; đôi khi Spring LDAP ghi nhận `PartialResultException`. Một developer đề nghị bật `setIgnorePartialResultException(true)` và thêm URL APAC vào `setUrls(...)` như một endpoint failover.

**Câu hỏi:**

1. Vì sao một SUBTREE search ở root DC không bảo đảm đọc toàn domain con?
2. RootDSE nào nên được kiểm tra và `namingContexts` cho biết những gì?
3. Replication giữa hai root DC có giải quyết việc tìm kiếm child domain không? Vì sao?
4. Phân biệt `Referral result code` với `SearchResultReference`.
5. Vì sao bỏ qua `PartialResultException` không phải giải pháp tìm kiếm toàn miền?
6. Vì sao đưa URL của hai NC khác nhau vào danh sách failover có thể gây sai dữ liệu?
7. Thiết kế hai `ContextSource`/`LdapTemplate` tách biệt hoặc GC nên lựa chọn khi nào?
8. Nếu root và APAC đều có `uid=u1001`, service có được chọn kết quả đầu tiên để xác thực không?
9. Vì sao GC có thể tìm user nhưng không trả đủ một số thuộc tính cần cho nghiệp vụ?
10. Nếu vừa sửa email tại DC root rồi đọc replica khác, vì sao có thể vẫn thấy dữ liệu cũ?
11. Cần bảo vệ những gì khi một referral trỏ tới hostname ngoài allowlist?
12. Một API trả 50 user/page từ hai domain cần thiết kế paging/ordering như thế nào?
13. Hãy đề xuất ít nhất sáu integration tests cho referral, ACL, TLS, GC, duplicate UID và replication lag.

**Gợi ý đối chiếu:** cần hiểu root NC và APAC NC là hai miền dữ liệu riêng. Replication trong một NC không tự hợp nhất các NC khác nhau. Referral là chỉ dẫn, có thể cần chuyển endpoint có kiểm soát; bỏ qua partial exception chỉ có nguy cơ giấu mất dữ liệu. GC hỗ trợ discovery xuyên forest nhưng có partial attribute set. Với nghiệp vụ cần đầy đủ, hãy định nghĩa source/endpoint/scope rõ, fail closed khi một phần truy vấn lỗi, và dùng khóa nhận dạng có phân biệt source/domain.

## 20. Checklist trước khi triển khai

Kiểm tra lần cuối:

- [ ] Phân biệt **replication**, **naming context/partition** và **referral**.
- [ ] Đã hỏi RootDSE từng endpoint; biết `namingContexts` và các attribute topology đặc thù AD.
- [ ] Biết mỗi `ContextSource` dùng **endpoint/base/principal** nào và phục vụ logical NC nào.
- [ ] Không suy rằng **SUBTREE** tự tìm được mọi domain hoặc forest.
- [ ] Không dùng danh sách URL failover để thay thế **fan-out trên nhiều NC**.
- [ ] Đã quyết định referral mode `ignore/follow/throw` dựa trên rủi ro; không auto-follow đến host lạ.
- [ ] Không đánh đồng `setIgnorePartialResultException(true)` với tìm kiếm đầy đủ.
- [ ] LDAP filter có escaping, base/scope và attribute allowlist; tránh LDAP injection.
- [ ] LDAPS/StartTLS xác minh CA/hostname cho mọi endpoint; credentials không bị chuyển bừa bãi.
- [ ] Có chính sách xử lý lỗi một source, size/time limit, paging và deadline toàn request.
- [ ] Kết quả được gắn source ID và stable identity; không chỉ dùng UID, CN hoặc DN cũ như khóa toàn cục.
- [ ] Biết thời điểm nên dùng AD Global Catalog và hạn chế Partial Attribute Set.
- [ ] Có chính sách replication lag/read-after-write cho dữ liệu danh tính nhạy cảm.
- [ ] Phân biệt authentication và authorization; group membership xuyên domain cần xác minh riêng.
- [ ] Đã kiểm thử referral, cross-domain search, ACL, TLS, GC, duplicate identity, failover và replica lag.

### Tài liệu tiêu chuẩn và chính thức

- [RFC 4511 — LDAP: The Protocol (referrals và SearchResultReference)](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4516 — LDAP Uniform Resource Locator](https://www.rfc-editor.org/rfc/rfc4516).
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html).
- [Spring LDAP — AbstractContextSource Java API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html).
- [Spring LDAP — LdapTemplate Java API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
- [Microsoft Learn — RootDSE](https://learn.microsoft.com/en-us/windows/win32/adschema/rootdse).
- [Microsoft Learn — Attributes Included in Global Catalog](https://learn.microsoft.com/en-us/windows/win32/ad/attributes-included-in-the-global-catalog).

**Kết luận:** khi ứng dụng Spring Data LDAP chạy trên hạ tầng nhiều server/domain, một truy vấn thành công không nhất thiết đã bao phủ mọi dữ liệu cần tìm. Cần hiểu server giữ **naming context nào**, dữ liệu được **replicate ra sao**, referral dẫn đến **endpoint nào**, và **Global Catalog** có thể cung cấp những thuộc tính nào. Bằng cách chọn `ContextSource` theo nguồn dữ liệu thật, xử lý partial/referral có chủ đích, giới hạn DN/scope/ACL, xác minh TLS và kiểm thử replication lag, ứng dụng Java có thể truy vấn danh tính xuyên miền **đúng phạm vi, có thể giải thích và không làm mất an toàn bảo mật**.
