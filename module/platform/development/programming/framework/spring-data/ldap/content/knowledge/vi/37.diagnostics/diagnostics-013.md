# Danh sách kiểm tra DN, bộ lọc, schema, quyền và cấu hình kết nối

> **Chương:** Chẩn đoán  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP bằng mô hình repository và ánh xạ entry phân cấp sang đối tượng Java. Người học hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Khi một thao tác Spring Data LDAP thất bại, nguyên nhân có thể nằm ở DN, search base, filter, schema, ACL, bind identity, DNS, TCP, TLS, timeout, referral hoặc connection pool. Các lỗi này đôi khi xuất hiện dưới cùng một thông báo tổng quát như `CommunicationException` hoặc `DataAccessException`, khiến việc sửa sai tầng rất dễ xảy ra.

Cách chẩn đoán hiệu quả là kiểm tra theo từng lớp và giữ nguyên bằng chứng của lần lỗi: endpoint, thời điểm, operation, DN/base, scope, filter đã redact, principal, result code và root cause. Bắt đầu từ một thao tác LDAP nhỏ, độc lập; sau đó mới kiểm tra mapping/repository và luồng nghiệp vụ.

Bài này cung cấp checklist theo thứ tự từ cấu hình kết nối tới dữ liệu: xác minh DN/base, filter, objectClass/schema, quyền, bind, DNS/TCP/TLS, timeout/pool và referral. Mỗi mục nêu dấu hiệu, cách kiểm tra và hướng khắc phục để người học có thể xử lý sự cố có hệ thống.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Thu thập thông tin cần thiết trước khi thay đổi cấu hình LDAP.
2. Phân biệt lỗi DN, search base, filter và lỗi không tìm thấy kết quả.
3. Kiểm tra objectClass, attribute type, MUST/MAY và syntax theo schema.
4. Phân biệt bind failure với thiếu quyền đọc/ghi.
5. Kiểm tra DNS, port, firewall, TLS certificate và hostname verification.
6. Phân biệt LDAPS với StartTLS và kiểm tra đúng endpoint.
7. Cấu hình timeout kết nối, timeout đọc và search time limit ở đúng lớp.
8. Nhận biết connection pool cạn, context cũ và referral/partial result.
9. Đọc LDAP result code và exception chain của Spring LDAP.
10. Dùng ldapsearch, ldapwhoami, openssl, keytool và công cụ hệ điều hành để cô lập lỗi.
11. Thiết kế log, health check và integration test hỗ trợ điều tra.
12. Áp dụng runbook mà không làm lộ credential hoặc dữ liệu nhạy cảm.

## 2. Quy trình chẩn đoán tổng thể

Không bắt đầu bằng cách đổi nhiều thuộc tính cấu hình cùng lúc. Chạy theo thứ tự dưới đây để xác định lớp đầu tiên không hoạt động:

~~~mermaid
flowchart TD
    A["Ghi nhận lỗi, operation và thời điểm"]
    B["Kiểm tra URL, base DN, bind principal"]
    C["DNS và TCP tới đúng host/port"]
    D["TLS handshake, trust chain, hostname"]
    E["Bind thành công với đúng identity"]
    F["Đọc Root DSE / naming context"]
    G["Kiểm tra DN và search base"]
    H["Kiểm tra filter, scope và attribute"]
    I["Kiểm tra schema và objectClass"]
    J["Kiểm tra ACL đọc/ghi"]
    K["Kiểm tra timeout, pool, referral"]
    L["Xác minh bằng Spring LdapTemplate/repository"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> K --> L
~~~

Nếu lỗi xuất hiện trước bước Bind, chưa cần sửa repository mapping. Nếu CLI bind/search thành công nhưng Spring thất bại, tập trung vào khác biệt giữa CLI và ứng dụng: URL, base, principal, truststore JVM, environment properties, pooling và bean wiring.

### Checklist nhanh trước khi điều tra

- [ ] Ghi chính xác URL LDAP/LDAPS, hostname, port và server/DC được kết nối.
- [ ] Xác định Spring LDAP, Spring Data LDAP và JDK đang chạy.
- [ ] Ghi base DN cấu hình trong ContextSource.
- [ ] Ghi DN đích hoặc search base ở dạng đã redact phù hợp.
- [ ] Ghi search scope, filter template và attribute projection.
- [ ] Xác nhận bind principal đang dùng, không ghi password.
- [ ] Ghi operation: bind, search, lookup, add, modify, delete hay rename.
- [ ] Lưu result code, exception class và toàn bộ cause chain.
- [ ] Ghi timeout, pool wait, số lần retry và correlation ID.
- [ ] Xác định lỗi xảy ra trên tất cả instance hay chỉ một host/replica.

## 3. Thu thập bằng chứng trước khi sửa

Một ticket chẩn đoán nên có một bản tóm tắt tối thiểu:

| Dữ liệu | Ví dụ |
|---|---|
| Thời điểm | 2026-11-26T14:30:00Z |
| Operation | Search |
| Endpoint alias | ldap-primary |
| Transport | LDAPS |
| Base alias | people-base |
| Scope | ONELEVEL |
| Filter template | (&(objectClass=inetOrgPerson)(uid={uid})) |
| Attribute list | uid, cn, mail |
| Principal | svc-ldap-reader (không ghi secret) |
| Result code | 32 / noSuchObject |
| Root cause | javax.naming.NameNotFoundException |
| Latency | 2.4 s |
| App instance | ldap-service-2 |
| Correlation ID | request-... |

Không đưa password, token, userPassword, private key, toàn bộ attribute values hoặc raw filter chứa dữ liệu người dùng vào log. Nếu cần chia sẻ DN, email hoặc UID trong ticket, áp dụng quy tắc redact của tổ chức.

### Ghi nhận exception chain

Spring LDAP dịch nhiều NamingException/JNDI exception sang exception thuộc hệ thống DataAccessException của Spring. Khi log, giữ exception gốc và cause chain; không chỉ ghi message ngoài cùng.

~~~java
try {
    ldapTemplate.lookup(personDn);
} catch (DataAccessException ex) {
    log.error(
            "LDAP lookup failed: operation={}, correlationId={}",
            "lookup",
            correlationId,
            ex);
    throw ex;
}
~~~

Ví dụ trên cố ý giữ stack trace để điều tra. Trong production, logger và appender phải có policy redact; không serialize toàn bộ request/attributes vào log.

Không dựa vào nội dung `diagnosticMessage` để parse logic. RFC 4511 quy định trường này là thông điệp tùy chọn, không chuẩn hóa; server có thể thay result code hoặc nội dung để tránh tiết lộ thông tin. Hãy dùng result code, exception type, matched DN nếu được phép và log phía server làm bằng chứng.

## 4. Phân loại LDAP result code thường gặp

| Code | Tên | Hướng kiểm tra đầu tiên |
|---:|---|---|
| 3 | timeLimitExceeded | Search quá lâu, filter/scope/index hoặc server load |
| 4 | sizeLimitExceeded | Số entry vượt limit |
| 8 | strongerAuthRequired | Server yêu cầu cơ chế xác thực/bảo vệ mạnh hơn |
| 10 | referral | Operation cần xử lý referral hoặc endpoint khác |
| 11 | adminLimitExceeded | Vượt administrative policy của server |
| 13 | confidentialityRequired | Server yêu cầu TLS hoặc bảo vệ confidentiality |
| 16 | noSuchAttribute | Attribute cần xóa/sửa không tồn tại |
| 17 | undefinedAttributeType | Attribute không được schema nhận biết |
| 18 | inappropriateMatching | Matching rule không phù hợp syntax |
| 19 | constraintViolation | Vi phạm constraint/schema |
| 20 | attributeOrValueExists | Giá trị đã tồn tại khi ADD |
| 21 | invalidAttributeSyntax | Giá trị không đúng syntax |
| 32 | noSuchObject | DN/base/entry không tồn tại hoặc không nhìn thấy |
| 34 | invalidDNSyntax | DN/RDN không hợp lệ |
| 48 | inappropriateAuthentication | Cơ chế xác thực không được chấp nhận |
| 49 | invalidCredentials | Principal/password không hợp lệ hoặc bị policy từ chối |
| 50 | insufficientAccessRights | Bind thành công nhưng không đủ quyền operation |
| 51 | busy | Server tạm thời bận |
| 52 | unavailable | Server hoặc subsystem không khả dụng |
| 53 | unwillingToPerform | Server từ chối thực hiện theo policy/trạng thái |
| 64 | namingViolation | Vi phạm quy tắc đặt tên/RDN |
| 65 | objectClassViolation | Entry thiếu/thừa attribute hoặc objectClass không hợp lệ |
| 66 | notAllowedOnNonLeaf | Không thể xóa/đổi entry cha khi còn child |
| 67 | notAllowedOnRDN | Đang xóa giá trị được dùng trong RDN |
| 68 | entryAlreadyExists | DN đích đã tồn tại |
| 69 | objectClassModsProhibited | Server không cho sửa objectClass theo cách yêu cầu |

Result code là điểm bắt đầu, không phải lúc nào cũng xác định duy nhất nguyên nhân. RFC cho phép server thay một số lỗi bằng code khác để tránh tiết lộ thông tin, ví dụ che thiếu quyền bằng noSuchObject. Xem thêm log directory server và thử lại bằng đúng bind identity.

## 5. Kiểm tra URL và base DN trong ContextSource

Spring LDAP `ContextSource` định nghĩa endpoint, bind identity và base path. Các giá trị này ảnh hưởng trực tiếp cách Spring diễn giải DN trong mọi operation.

Ví dụ cấu hình:

~~~java
@Bean
LdapContextSource ldapContextSource(
        LdapConnectionProperties properties) {

    LdapContextSource source = new LdapContextSource();
    source.setUrl(properties.url());
    source.setBase(properties.baseDn());
    source.setUserDn(properties.bindDn());
    source.setPassword(properties.bindPassword());
    return source;
}
~~~

Đây là ví dụ cấu hình; lấy password từ secret manager/environment đã được bảo vệ, không hardcode vào source control. Khi Spring quản lý bean, container tự gọi lifecycle callback của InitializingBean; không cần gọi afterPropertiesSet thủ công trong factory method.

### Phân biệt base DN với bind DN

Giả sử:

- ContextSource base: `dc=example,dc=org`
- Search base truyền cho LdapTemplate: `ou=people`
- Bind DN: `cn=svc-reader,ou=services,dc=example,dc=org`

Khi đã cấu hình base, DN thao tác với Spring LDAP thường là tương đối với base. Không truyền lại toàn bộ DN vào nơi đang mong đợi DN tương đối, nếu không có thể tạo đường dẫn bị lặp.

Ngược lại, bind principal trong ContextSource nếu là DN thì phải là DN đầy đủ tính từ gốc DIT, ngay cả khi base đã được cấu hình. Đây là điểm dễ gây lỗi khi một ứng dụng dùng cùng một chuỗi DN cho cả bind user và entry target.

### Checklist base/DN

- [ ] URL đúng scheme, host và port.
- [ ] Base DN thuộc naming context mà server phục vụ.
- [ ] Bind DN đầy đủ từ root DIT.
- [ ] DN truyền vào LdapTemplate là relative hay full đúng với ContextSource.
- [ ] Không ghép base DN hai lần.
- [ ] RDN attribute/value tồn tại đúng trong entry.
- [ ] DN có dấu phẩy, cộng, dấu cách, dấu thăng hoặc ký tự đặc biệt được encode đúng.
- [ ] Referral/failover không chuyển sang server có naming context khác.

## 6. Chẩn đoán DN và RDN

DN là chuỗi có cấu trúc gồm một hoặc nhiều RDN. Không nên tạo DN bằng cách nối chuỗi từ input:

~~~java
// Không an toàn khi uid chứa ký tự có ý nghĩa trong DN.
String dn = "uid=" + uid + ",ou=people,dc=example,dc=org";
~~~

Dùng `LdapNameBuilder` để dựng tên từ từng thành phần:

~~~java
Name personDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", validatedUid)
        .build();
~~~

Nếu ContextSource đã đặt base `dc=example,dc=org`, ví dụ trên tạo DN tương đối với base đó. Nếu không đặt base, hãy xây DN đầy đủ theo đúng DIT.

### Các dấu hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| invalidDNSyntax (34) | Dấu phẩy, escape hoặc RDN không đúng cú pháp | Parse DN bằng LdapName; xem đúng giá trị sau encode |
| noSuchObject (32) | Entry hoặc một thành phần của DN không tồn tại | Search từng cấp OU; kiểm tra base |
| entryAlreadyExists (68) | DN đích đã tồn tại | Lookup DN đích và xác minh identity |
| notAllowedOnRDN (67) | Xóa attribute value đang tạo RDN | Giữ lại RDN value hoặc rename entry |
| namingViolation (64) | Vi phạm quy tắc naming server | Kiểm tra schema, RDN attribute và naming policy |
| notAllowedOnNonLeaf (66) | Xóa/rename parent còn child | Xử lý subtree theo thứ tự phù hợp |

Không coi mọi lỗi noSuchObject là “user không tồn tại”. Có thể base DN sai, server đang ở replica khác hoặc ACL khiến server không tiết lộ entry.

## 7. Kiểm tra search base, scope và filter

Search có ba thành phần độc lập:

1. Base DN: bắt đầu tìm từ đâu.
2. Scope: chỉ entry, child trực tiếp hay toàn bộ subtree.
3. Filter: entry nào phù hợp.

Nếu một thành phần sai, search có thể trả rỗng dù dữ liệu vẫn tồn tại.

Ví dụ query có giới hạn và filter an toàn:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(validatedUid);

List<PersonSummary> results =
        ldapTemplate.search(ldapQuery, personSummaryMapper);
~~~

### Checklist filter

- [ ] Attribute có đúng tên theo schema.
- [ ] ObjectClass có thực sự được gắn trên entry.
- [ ] Matching rule phù hợp syntax attribute.
- [ ] Equality, substring, presence và ordering filter không bị nhầm.
- [ ] Giá trị input được encode theo filter syntax.
- [ ] Không nối chuỗi filter trực tiếp từ input.
- [ ] Search base/scope đủ hẹp và đúng OU.
- [ ] Query có count/time limit phù hợp.
- [ ] Chỉ lấy attribute cần thiết.

Nếu cần xây filter string thủ công, dùng API như `EqualsFilter`/`AndFilter` hoặc `LdapEncoder.filterEncode(value)`. Không dùng DN encoder để escape filter value; hai ngữ cảnh có grammar khác nhau.

### Phân biệt không có kết quả với base không tồn tại

- Search base hợp lệ nhưng filter không khớp: thường trả về tập kết quả rỗng.
- Search base không tồn tại: thường nhận noSuchObject/NameNotFoundException.
- Server che thông tin do ACL: có thể trả noSuchObject thay vì insufficientAccessRights.

Thử trước một OBJECT-scope lookup trên base DN bằng cùng bind identity, sau đó mở rộng ONELEVEL/SUBTREE và filter từng bước. Không thay đổi tất cả cùng lúc.

## 8. Kiểm tra schema và objectClass

Khi Add/Modify bị từ chối, kiểm tra schema trước khi sửa code mapping.

| Result code | Câu hỏi |
|---|---|
| undefinedAttributeType (17) | Attribute có được khai báo trong schema đang nạp không? |
| inappropriateMatching (18) | Filter/matching rule có phù hợp syntax không? |
| constraintViolation (19) | Có vi phạm constraint hoặc policy của server không? |
| invalidAttributeSyntax (21) | Giá trị có đúng syntax/format không? |
| namingViolation (64) | RDN có đúng quy tắc naming không? |
| objectClassViolation (65) | Thiếu MUST, có MAY không hợp lệ hay structural class sai? |
| objectClassModsProhibited (69) | Server có cấm thay structural objectClass không? |

### Kiểm tra objectClass

Đối với entry mới:

1. Xác định structural objectClass.
2. Kiểm tra mọi attribute MUST đã có giá trị.
3. Kiểm tra attribute chỉ được thêm nếu objectClass cho phép.
4. Kiểm tra auxiliary objectClass đã được schema khai báo và server cho phép.
5. Kiểm tra syntax và matching rule của từng attribute.
6. Kiểm tra RDN attribute/value có mặt trong entry.
7. Xác minh schema được nạp trên đúng server/replica mà ứng dụng đang kết nối.

Không giả định `inetOrgPerson` cho phép mọi custom attribute. Nếu ứng dụng cần employeeCode, employeeStatus hoặc appRevision, schema phải khai báo attribute và objectClass phù hợp. Annotation `@Attribute` chỉ ánh xạ field Java; nó không tự cài schema trên directory.

### Tra cứu schema metadata

Có thể đọc Root DSE để tìm naming context và subschema entry:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" \
  namingContexts subschemaSubentry supportedControl supportedExtension
~~~

Giá trị `subschemaSubentry` cho biết nơi đọc schema nếu server công bố theo cách chuẩn. Đường dẫn và quyền đọc schema có thể khác nhau giữa OpenLDAP, Active Directory và sản phẩm directory khác. Không giả định một DN schema cụ thể dùng được trên mọi server.

## 9. Kiểm tra quyền và bind identity

Bind thành công chỉ chứng minh server chấp nhận phiên xác thực. Nó không chứng minh account có quyền search, đọc attribute, Add, Modify, Delete hoặc đổi DN.

Phân biệt:

- Authentication: principal/password có được chấp nhận không?
- Authorization: identity đó được phép thực hiện operation trên entry/attribute nào?

### Result code liên quan

- `invalidCredentials (49)`: principal/password sai, account bị khóa/disable, credential hết hạn hoặc policy bind từ chối.
- `inappropriateAuthentication (48)`: cơ chế xác thực không phù hợp.
- `insufficientAccessRights (50)`: bind có thể thành công nhưng ACL không cho phép operation.
- `confidentialityRequired (13)`: server yêu cầu bảo vệ confidentiality, thường cần TLS.
- `strongerAuthRequired (8)`: server yêu cầu cơ chế xác thực/bảo vệ mạnh hơn.

### Checklist ACL

- [ ] Search account có quyền traverse/search ở base OU.
- [ ] Account có quyền đọc attribute cần projection.
- [ ] Account có quyền đọc objectClass và attribute cần mapping.
- [ ] Writer có quyền Add tại parent OU.
- [ ] Writer có quyền Modify đúng attribute.
- [ ] Writer có quyền Delete/ModifyDN nếu use case cần.
- [ ] ACL trên group/member và user entry được kiểm tra riêng.
- [ ] Đang test bằng đúng bind identity mà ứng dụng sử dụng.
- [ ] Không dùng Directory Manager/domain admin để che lỗi quyền của service account.

Nếu search trả được entry nhưng mapper thiếu attribute, có thể ACL chỉ cho phép đọc một phần attribute. Hãy so sánh kết quả bằng account được phép đọc đầy đủ và account runtime, nhưng không dùng quyền rộng hơn trong production để né ACL.

## 10. Kiểm tra DNS và kết nối TCP

Trước khi kiểm tra Spring, xác minh máy chạy ứng dụng có thể phân giải và mở kết nối tới đúng endpoint.

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName ldap.example.org
Test-NetConnection ldap.example.org -Port 636
Test-NetConnection ldap.example.org -Port 389
~~~

Trên Linux/macOS:

~~~bash
getent hosts ldap.example.org
nc -vz ldap.example.org 636
nc -vz ldap.example.org 389
~~~

Diễn giải:

| Kết quả | Hướng điều tra |
|---|---|
| DNS không phân giải | DNS zone, search suffix, VPN, split DNS, SRV record |
| Connection refused | Host reachable nhưng port không listen hoặc firewall reject |
| Timeout | Firewall drop, routing, VPN, server không phản hồi hoặc port sai |
| TCP thành công nhưng LDAP lỗi | TLS, Bind, protocol, server policy hoặc request |
| Chỉ một instance lỗi | DNS cache, route, firewall, truststore/JDK hoặc cấu hình instance |

Nếu ContextSource có nhiều URL failover, kiểm tra từng host. Một host hoạt động không chứng minh tất cả endpoint đều có cùng certificate, naming context, ACL và schema.

## 11. Kiểm tra scheme, port và transport

Phân biệt hai cách bảo vệ kết nối:

| Cách kết nối | URL thường gặp | Luồng |
|---|---|---|
| LDAP thuần | ldap://host:389 | Kết nối LDAP trực tiếp |
| LDAPS | ldaps://host:636 | TLS ngay từ khi thiết lập kết nối |
| StartTLS | ldap://host:389 | Kết nối LDAP rồi nâng cấp bằng StartTLS extended operation |

Không cấu hình `ldap://host:636` chỉ vì server có port 636. Cũng không dùng `ldaps://host:389` nếu endpoint đó không được cấu hình TLS.

Với simple bind, không gửi password qua kết nối không được bảo vệ bằng TLS. Nếu server yêu cầu LDAP signing/SASL integrity hoặc channel binding, kiểm tra chính sách của server và cơ chế client hỗ trợ.

## 12. Chẩn đoán TLS certificate và hostname

Các lỗi TLS thường xuất hiện trước khi LDAP Bind:

- PKIX path building failed.
- unable to find valid certification path.
- certificate expired/not yet valid.
- No subject alternative DNS name matching.
- handshake_failure hoặc protocol_version.
- peer closed connection during handshake.

Kiểm tra lần lượt:

1. Certificate còn hiệu lực theo thời gian hệ thống.
2. Certificate server được ký bởi CA nằm trong truststore của JVM.
3. Intermediate CA được server gửi đầy đủ hoặc có trong trust chain.
4. SAN chứa hostname đúng với URL ứng dụng dùng.
5. EKU/key usage phù hợp server authentication.
6. JDK hỗ trợ protocol/cipher mà server yêu cầu.
7. Mỗi endpoint failover có certificate hợp lệ.
8. Đồng hồ máy chạy ứng dụng và directory server đồng bộ.

Ưu tiên dùng FQDN có trong SAN của certificate. Nếu ứng dụng kết nối bằng IP nhưng certificate chỉ có DNS SAN, hostname verification sẽ thất bại. Không sửa bằng cách tắt hostname verification hoặc dùng TrustManager chấp nhận mọi certificate.

### Kiểm tra certificate từ terminal

LDAPS:

~~~bash
openssl s_client \
  -connect ldap.example.org:636 \
  -servername ldap.example.org \
  -showcerts \
  -verify_return_error
~~~

StartTLS:

~~~bash
openssl s_client \
  -starttls ldap \
  -connect ldap.example.org:389 \
  -servername ldap.example.org \
  -showcerts \
  -verify_return_error
~~~

Các lệnh trên giúp xem handshake và certificate chain. Kết quả OpenSSL trên máy developer không thay thế kiểm tra truststore của JVM trong container/host chạy ứng dụng.

Kiểm tra truststore:

~~~bash
keytool -list -keystore /secure/path/ldap-truststore.p12 -storetype PKCS12
~~~

Không ghi password truststore vào shell history, script chia sẻ hoặc ticket. Dùng prompt/secret manager.

## 13. Bật JSSE debug có kiểm soát

Khi lỗi chỉ xảy ra trong JVM, bật JSSE debug trên một instance test hoặc một lần chạy có kiểm soát:

~~~bash
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Dữ liệu có thể giúp xác định:

- Trust manager chọn trust anchor nào.
- Certificate chain được server gửi.
- TLS protocol/cipher negotiation.
- Handshake dừng ở giai đoạn nào.
- Hostname verification có thành công không.

JSSE debug tạo log lớn và có thể chứa thông tin hạ tầng nhạy cảm. Chỉ bật tạm thời, giới hạn instance/thời gian, bảo vệ file log và tắt sau khi thu thập đủ bằng chứng. Không bật `all` trong production như cấu hình thường trực.

### StartTLS

Với JNDI, StartTLS dùng extended operation OID `1.3.6.1.4.1.1466.20037` trên LDAP association hiện có, sau đó gọi `StartTlsResponse.negotiate()`. Phải hoàn tất TLS handshake và hostname verification trước khi gửi simple bind credentials. Không tái sử dụng một context đã chuyển đổi TLS sai cách qua connection pool không hỗ trợ trạng thái đó.

## 14. Chẩn đoán LDAP signing và channel binding trên Active Directory

Nếu chỉ một số client hoặc JDK/driver bị từ chối sau khi bật policy bảo mật AD, kiểm tra LDAP signing và channel binding.

LDAP signing cung cấp integrity/authenticity cho SASL session không dùng TLS; nó không cung cấp confidentiality. TLS bảo vệ confidentiality, integrity và server identity. Channel binding gắn authentication vào TLS session trong các trường hợp SASL phù hợp.

Một số Event ID hữu ích trong Directory Service log:

| Event ID | Ý nghĩa khái quát |
|---:|---|
| 2886 | Cảnh báo cấu hình LDAP signing trên domain controller |
| 2887 | Tổng hợp bind không đáp ứng signing/TLS được chấp nhận trong khoảng thời gian |
| 2888 | Tổng hợp bind không đáp ứng policy đã bị từ chối |
| 2889 | Chi tiết client/identity của bind không đáp ứng signing |
| 3039 | LDAP over TLS bind có lỗi channel binding validation |
| 3074/3075 | Sự kiện audit liên quan channel binding, tùy phiên bản/cấu hình |

Event ID, mức diagnostic và policy behavior phụ thuộc Windows Server version và cấu hình. Tra cứu event phía domain controller cùng thời điểm với lỗi client. Không hạ signing/channel binding policy để che lỗi; cập nhật client và cấu hình TLS/SASL phù hợp.

## 15. Kiểm tra Bind và credential

Dùng công cụ LDAP độc lập để kiểm tra cùng endpoint, principal và cơ chế xác thực.

Ví dụ simple bind qua LDAPS:

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=services,dc=example,dc=org" \
  -W
~~~

Tùy hệ điều hành, gói OpenLDAP client có thể cung cấp ldapwhoami/ldapsearch. Tham số `-W` yêu cầu nhập password tương tác; tránh đặt password trực tiếp trong command line.

Nếu bind thất bại:

- Kiểm tra DN đầy đủ, chính tả, OU và naming context.
- Kiểm tra credential secret có bị rotate nhưng ứng dụng vẫn dùng bản cũ.
- Kiểm tra account locked, disabled, expired hoặc yêu cầu đổi password.
- Kiểm tra server cho phép simple bind trên endpoint đang dùng.
- Kiểm tra TLS và LDAP signing/channel binding policy.
- Kiểm tra principal format: full DN, UPN hay dạng khác theo server.
- Kiểm tra có nhầm service account với end-user credentials không.

Nếu CLI bind thành công nhưng Spring bind thất bại, so sánh truststore/JDK, URL, principal, authentication mechanism và environment properties. CLI có thể dùng OS trust store trong khi JVM dùng truststore khác.

## 16. Kiểm tra Search độc lập sau khi Bind thành công

Sau khi bind thành công, đọc Root DSE để xác định server/naming context:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" \
  namingContexts defaultNamingContext subschemaSubentry
~~~

Không phải server nào cũng trả mọi attribute được liệt kê; Active Directory có thể cung cấp defaultNamingContext, còn namingContexts là thông tin thường dùng để xác định naming context.

Sau đó kiểm tra base DN cụ thể:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" dn objectClass
~~~

Nếu base OBJECT search thành công, thử ONELEVEL và filter hẹp. Cách này tách lỗi kết nối/Bind khỏi lỗi base/filter/mapping.

## 17. Kiểm tra timeout ở đúng lớp

Một thao tác có thể chờ ở nhiều giai đoạn:

| Lớp | Ví dụ timeout | Ý nghĩa |
|---|---|---|
| DNS | Resolver timeout | Không tìm được IP |
| TCP connect | Connection timeout | Không thiết lập được socket |
| TLS handshake | Handshake/network timeout | Không hoàn tất TLS |
| LDAP Bind/read | JNDI read timeout | Không nhận response từ server |
| Search | SearchControls time limit | Server dừng search khi vượt giới hạn |
| Pool | Max wait | Chờ context/connection được trả lại |
| HTTP request | Application deadline | Tổng thời gian API cho phép |

Với JDK LDAP provider, hai environment property thường dùng là:

- `com.sun.jndi.ldap.connect.timeout`: thời gian thiết lập kết nối, milliseconds.
- `com.sun.jndi.ldap.read.timeout`: thời gian chờ LDAP response, milliseconds.

Đây là property riêng của JDK LDAP provider, không phải mọi JNDI provider đều bắt buộc hỗ trợ. Giá trị nên là số milliseconds dạng chuỗi và lớn hơn 0. Đừng nhầm read timeout với search time limit.

### Cấu hình trong LdapContextSource

Spring LDAP cho phép truyền custom environment properties qua `setBaseEnvironmentProperties`:

~~~java
@Bean
LdapContextSource ldapContextSource(
        LdapConnectionProperties properties) {

    LdapContextSource source = new LdapContextSource();
    source.setUrl(properties.url());
    source.setBase(properties.baseDn());
    source.setUserDn(properties.bindDn());
    source.setPassword(properties.bindPassword());

    Map<String, Object> environment = new HashMap<>();
    environment.put(
            "com.sun.jndi.ldap.connect.timeout",
            "3000");
    environment.put(
            "com.sun.jndi.ldap.read.timeout",
            "5000");

    source.setBaseEnvironmentProperties(environment);
    return source;
}
~~~

Các giá trị 3 giây/5 giây chỉ minh họa. Chọn timeout theo latency baseline, số endpoint failover, pool wait và deadline của request. Nếu có nhiều URL failover, tổng thời gian connect có thể tăng theo số endpoint được thử.

Search time limit có thể đặt riêng qua `SearchControls.setTimeLimit(...)` hoặc query builder. Timeout connect/read không thay thế search limit và ngược lại.

## 18. Chẩn đoán connection pool

Khi ứng dụng chậm hoặc thỉnh thoảng timeout dù LDAP server vẫn khỏe, kiểm tra pool:

- Số context đang active.
- Số context idle.
- Thời gian chờ mượn context.
- Context bị invalid/closed.
- Validation on borrow/return/idle.
- Số bind principal khác nhau.
- Connection age và server idle timeout.
- Tỷ lệ CommunicationException/AuthenticationException.

Spring LDAP PoolingContextSource có thể validate DirContext khi borrow, return hoặc idle. Các thuộc tính như `max-active`, `max-total`, `max-wait`, `test-on-borrow` và `test-while-idle` quyết định cách pool vận hành.

Một số mặc định quan trọng trong tài liệu Spring LDAP hiện hành: max-active mặc định 8 cho mỗi loại context; max-total và max-wait mặc định -1, nghĩa là không giới hạn theo cách diễn giải của pool. Cấu hình wait vô hạn có thể làm request treo khi pool cạn. Hãy đặt giới hạn và theo dõi pool exhaustion.

### Native JNDI pooling và Spring LDAP pooling

Native JNDI pooling có ít tùy chọn validation/maintenance hơn. Spring LDAP cung cấp pool cấu hình chi tiết hơn và khả năng kiểm tra context. Không bật nhiều cơ chế pool chồng lấn nếu chưa hiểu cách chúng tương tác.

Nếu ứng dụng dùng StartTLS hoặc thay đổi security state trên context, cần đặc biệt cẩn thận với pooling: JNDI pooling không theo dõi mọi thay đổi state của connection. Không trả context đã thay đổi trạng thái bảo mật vào pool như thể đó là context bình thường.

Nếu dùng credential theo từng người dùng, kiểm tra cách pool phân tách principal. Không chia sẻ connection đã bind bằng user A cho thao tác của user B.

## 19. Chẩn đoán referral và PartialResultException

LDAP server có thể trả referral khi entry/naming context nằm trên server khác hoặc operation cần được xử lý ở endpoint khác.

Spring LDAP ContextSource có chiến lược referral như:

- `ignore`: bỏ qua referral.
- `follow`: client/provider theo referral.
- `throw`: ném exception để ứng dụng xử lý.

Với Active Directory, một số search gặp referral có thể dẫn tới `PartialResultException` nếu provider không xử lý referral như mong đợi. Spring LDAP có thuộc tính `ignorePartialResultException`, nhưng bật nó có thể khiến ứng dụng bỏ qua một phần kết quả.

Trước khi thay đổi referral policy:

1. Xác định search base có nằm ngoài naming context của server không.
2. Xem referral URL trả về trỏ tới host/port nào.
3. Kiểm tra DNS, firewall và TLS certificate của server đích.
4. Kiểm tra bind identity có quyền trên server đích.
5. Xác định use case cần toàn bộ kết quả hay chỉ subtree hiện tại.
6. Chỉ bỏ qua partial result nếu nghiệp vụ chấp nhận thiếu dữ liệu và có metric/audit phù hợp.

Không đặt ignorePartialResultException=true như cách sửa chung cho mọi lỗi search.

## 20. Phân biệt lỗi cấu hình với lỗi repository/ODM

Nếu CLI và một thao tác LdapTemplate cơ bản đều thành công nhưng repository thất bại, chuyển sang kiểm tra mapping:

- Entity có đúng annotation `@Entry`, `@Id` và `@Attribute` từ Spring LDAP ODM không?
- ID có kiểu `javax.naming.Name` theo yêu cầu Spring Data LDAP không?
- ObjectClass khai báo có khớp entry/schema không?
- Attribute đa trị có được ánh xạ thành collection phù hợp không?
- Binary attribute có khai báo BINARY đúng không?
- Converter đọc/ghi đã đăng ký đúng mapping layer chưa?
- Repository có dùng đúng LdapTemplate/ContextSource không?
- DN trong entity là full hay relative so với base?

Một mapper có thể lỗi do field type/converter dù Bind/Search ở tầng LDAP hoạt động bình thường. Đừng sửa ACL hoặc truststore khi lỗi nằm ở ODM.

## 21. Kiểm tra Spring configuration và dependency

Các giá trị cần đối chiếu giữa profile local, test, staging và production:

| Thành phần | Cần xác minh |
|---|---|
| ContextSource URL | Scheme, host, port, failover URL list |
| Base DN | Đúng naming context, không lặp base |
| Bind DN | Principal đầy đủ và đúng authentication mechanism |
| Secret | Secret version hiện hành, không có whitespace/encoding ngoài ý muốn |
| Environment properties | Connect/read timeout, referral, TLS strategy |
| Truststore | JVM process thực tế dùng đúng file/type/CA |
| LdapTemplate | Đúng ContextSource, scope/count/time defaults |
| Pool | Max active, max wait, validation, credential strategy |
| Repository | Dùng đúng LdapTemplate bean |
| Runtime | JDK version, Spring LDAP/Spring Data LDAP version |
| DNS/failover | Mỗi URL được phân giải và truy cập từ đúng host/container |

Không so cấu hình chỉ bằng file application.yml. Environment variable, secret injection, JVM system properties và profile có thể ghi đè giá trị. Ghi log cấu hình đã resolve theo dạng đã redact khi ứng dụng khởi động.

## 22. Bảng triệu chứng và hướng điều tra nhanh

| Triệu chứng | Kiểm tra trước | Hướng xử lý |
|---|---|---|
| Connection refused | Host/port, listener, firewall | Sửa endpoint/network |
| Connect timeout | DNS, route, firewall, connect timeout | Sửa network hoặc timeout policy |
| SSLHandshakeException | Certificate chain, SAN, truststore, protocol | Cài CA đúng, dùng hostname phù hợp, thống nhất TLS |
| PKIX path building failed | JVM trust anchors/intermediate CA | Bổ sung CA tin cậy vào truststore JVM |
| Hostname mismatch | URL host và certificate SAN | Dùng FQDN đúng hoặc cấp certificate phù hợp |
| invalidCredentials (49) | Bind DN, secret, account state | Sửa principal/secret/account policy |
| confidentialityRequired (13) | Scheme/transport | Dùng LDAPS hoặc StartTLS theo policy |
| strongerAuthRequired (8) | Bind mechanism/signing | Dùng SASL/TLS phù hợp server |
| noSuchObject (32) | Base DN, full/relative DN, replica | Sửa base hoặc naming context |
| invalidDNSyntax (34) | DN escaping/RDN grammar | Dùng LdapNameBuilder |
| Search trả rỗng | Scope, filter, objectClass, matching rule | Kiểm tra từng thành phần |
| undefinedAttributeType (17) | Schema attribute | Cài schema/đổi attribute |
| objectClassViolation (65) | MUST/MAY, structural/auxiliary class | Sửa entry mapping/schema |
| invalidAttributeSyntax (21) | Format/Java type/encoding | Sửa giá trị và converter |
| insufficientAccessRights (50) | ACL entry/attribute/operation | Cấp quyền tối thiểu cần thiết |
| entryAlreadyExists (68) | DN đích | Kiểm tra identity/idempotency |
| notAllowedOnRDN (67) | Attribute tạo RDN | Không xóa RDN value hoặc rename |
| PartialResultException | Referral/naming context | Xử lý referral đúng policy |
| CommunicationException sau idle | Stale pooled context/network idle timeout | Validate/evict connection |
| Request treo | Pool wait, connect/read/search timeout | Đặt deadline từng lớp |
| Repository lỗi, CLI thành công | ODM mapping/bean wiring | Kiểm tra entity, converter, template |

## 23. Runbook chẩn đoán theo từng bước

Khi có sự cố production, thực hiện theo checklist:

### Bước 1 — Cô lập phạm vi

- Xác định một endpoint/operation cụ thể.
- Xác định một app instance và một LDAP endpoint.
- Ghi thời điểm, correlation ID và exception chain.
- Xác định lỗi xảy ra cho mọi user hay một identity.

### Bước 2 — Kiểm tra endpoint

- Resolve DNS từ chính host/container ứng dụng.
- Test TCP tới đúng port.
- Kiểm tra failover URL riêng từng host.
- Không dùng hostname khác khi test TLS.

### Bước 3 — Kiểm tra TLS

- Kiểm tra certificate chain, expiry và SAN.
- Xác nhận JVM truststore.
- Bật JSSE debug tạm thời nếu cần.
- Không tắt hostname verification/trust validation.

### Bước 4 — Kiểm tra Bind

- Dùng ldapwhoami hoặc ldapsearch với cùng endpoint/principal.
- Nhập password tương tác.
- Kiểm tra account state và bind policy.
- Đối chiếu LDAP signing/channel binding nếu dùng AD.

### Bước 5 — Kiểm tra base/DN/filter

- Đọc Root DSE/namingContexts.
- OBJECT search trên base.
- ONELEVEL search với filter hẹp.
- Kiểm tra DN relative/full và filter escaping.

### Bước 6 — Kiểm tra schema/ACL

- Xác minh objectClass, MUST/MAY, attribute syntax.
- Thử read và write bằng đúng service account.
- Xác minh quyền theo entry và attribute.

### Bước 7 — Kiểm tra runtime

- Đối chiếu ContextSource, truststore, timeout và referral.
- Kiểm tra pool wait/validation.
- So sánh LdapTemplate với repository/ODM.
- Xác nhận dependency version và runtime JDK.

### Bước 8 — Xác minh và đóng sự cố

- Chạy lại thao tác nhỏ nhất có thể tái hiện.
- Xác nhận không còn partial result/hidden failure.
- Ghi root cause và thay đổi đã thực hiện.
- Thêm test/metric để phát hiện tái diễn.
- Thu hồi debug logging và quyền tạm thời sau điều tra.

## 24. Logging và metric hỗ trợ chẩn đoán

Metric gợi ý:

- `ldap_connection_attempts_total{endpoint,result}`
- `ldap_bind_failures_total{reason}`
- `ldap_operation_duration_seconds{operation}`
- `ldap_operation_errors_total{result_code}`
- `ldap_pool_active`
- `ldap_pool_idle`
- `ldap_pool_wait_seconds`
- `ldap_tls_handshake_failures_total{reason}`
- `ldap_referrals_total`
- `ldap_partial_results_total`

Tên trên là gợi ý, không phải metric tự có của Spring LDAP. Không dùng DN, UID, email, filter raw hoặc password làm metric label. Những giá trị đó có thể chứa PII và tạo cardinality rất lớn.

Log có thể ghi:

- Correlation ID.
- Endpoint alias, transport và app instance.
- Operation type.
- Base alias, scope và filter template đã redact.
- Bind principal alias.
- Result code, exception class và cause chain.
- Latency, pool wait, timeout và retry count.

Không ghi credential, userPassword, private key, certificate bytes hoặc toàn bộ attributes.

## 25. Kiểm thử chẩn đoán trong môi trường test

Một bộ integration test nên bao phủ:

| Kịch bản | Kết quả mong đợi |
|---|---|
| ContextSource URL sai | Lỗi connect rõ ràng |
| Base DN sai | Phân biệt noSuchObject với search rỗng |
| Bind DN/password sai | Authentication failure |
| Bind đúng nhưng ACL thiếu | Search/read/write bị từ chối phù hợp |
| Filter có ký tự đặc biệt | Được encode đúng |
| Attribute không có trong schema | Lỗi schema được nhận diện |
| Thiếu MUST attribute | ObjectClass violation |
| Giá trị sai syntax | Invalid attribute syntax |
| Certificate CA không tin cậy | TLS handshake thất bại |
| Hostname không khớp SAN | Hostname verification thất bại |
| Referral xuất hiện | Theo policy follow/throw/ignore đã chọn |
| Pooled connection bị đóng | Validation/eviction hoạt động |
| Server chậm | Connect/read/search timeout phân biệt được |
| Partial result | Không bị coi là thành công đầy đủ |
| Repository mapping sai | Phân biệt được với lỗi kết nối/Bind |

Test TLS cần dùng certificate test có CA và SAN thực tế. Không viết test pass bằng TrustManager chấp nhận mọi certificate.

## 26. Bài tập thực hành

**Bối cảnh:** ứng dụng Spring Data LDAP tìm nhân viên trong `ou=people,dc=example,dc=org` nhưng đôi lúc gặp `CommunicationException`, `NameNotFoundException` và `SchemaViolationException`. Một số lần deploy mới còn gặp TLS handshake failure.

Thực hiện trên LDAP test:

1. Ghi lại ContextSource URL, base DN, bind DN và timeout đã resolve.
2. Dùng Resolve-DnsName/Test-NetConnection hoặc getent/nc để kiểm tra DNS/TCP.
3. Dùng openssl s_client kiểm tra LDAPS và StartTLS đúng port.
4. Dùng keytool kiểm tra truststore JVM và certificate chain.
5. Bật JSSE debug tạm thời để xác định giai đoạn TLS handshake thất bại.
6. Dùng ldapwhoami kiểm tra bind với cùng principal.
7. Đọc Root DSE để xác nhận namingContexts/subschemaSubentry.
8. OBJECT search trên base, sau đó ONELEVEL search bằng filter cụ thể.
9. Tạo UID có ký tự đặc biệt hợp lệ và xác nhận filter/DN builder encode đúng.
10. Cố tình dùng attribute không tồn tại và objectClass thiếu MUST; phân loại result code.
11. Kiểm tra ACL bằng read-only account và write account riêng.
12. Mô phỏng referral/PartialResultException và ghi rõ kết quả theo từng referral policy.
13. Giảm timeout trong test để xác nhận connect/read/search timeout khác nhau.
14. Mô phỏng pooled connection cũ; xác nhận validation và eviction.
15. Chạy cùng truy vấn qua LdapTemplate rồi LdapRepository để cô lập lỗi ODM.
16. Viết bảng triệu chứng → bằng chứng → root cause → remediation.
17. Thêm metric/log đã redact và viết runbook để một người khác có thể tái hiện chẩn đoán.

**Tiêu chí hoàn thành:** người học xác định được lớp gây lỗi bằng bằng chứng, phân biệt lỗi kết nối/TLS/Bind/DN/filter/schema/ACL/runtime, sửa đúng cấu hình hoặc dữ liệu và kiểm chứng lại bằng cả LDAP CLI lẫn Spring LDAP.

## 27. Tổng kết và tài liệu tham khảo

Chẩn đoán Spring Data LDAP cần đi theo lớp. Xác minh endpoint và TLS trước, sau đó Bind, Root DSE, base/DN, filter, schema, ACL và cuối cùng là pool/referral/ODM. Giữ nguyên result code và cause chain để tránh sửa nhầm tầng.

Các nguyên tắc cần nhớ:

- ContextSource base làm DN thao tác trở thành relative; bind DN vẫn phải đúng dạng đầy đủ.
- Dùng LdapNameBuilder cho DN và Filter API/LdapEncoder cho filter.
- Search rỗng khác với base DN không tồn tại.
- Bind thành công không đồng nghĩa có quyền đọc/ghi.
- Annotation ODM không cài schema trên directory.
- LDAPS và StartTLS có luồng thiết lập khác nhau; kiểm tra trust chain và hostname.
- Connect/read timeout khác search time limit.
- Pool exhaustion và stale context có thể trông giống lỗi network.
- Referral/PartialResultException có thể làm kết quả không đầy đủ.
- Không tắt certificate validation, hostname verification hoặc bỏ qua partial result để che lỗi.
- Log đủ bằng chứng nhưng không ghi credential/PII.
- Xác minh bằng LDAP CLI độc lập và Spring integration test.

Tài liệu tham khảo:

- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511): DN, Search, Bind, referrals và result codes.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): simple bind, SASL và yêu cầu bảo vệ credential.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource URL/base/bind DN, referral và LdapTemplate defaults.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): xây DN động bằng LdapNameBuilder và thao tác cơ bản.
- [Spring LDAP — AbstractContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): base path, bind DN, environment properties và pooling.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): validation, pool sizing, max wait và context lifecycle.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): search, lookup, exception translation và referral behavior.
- [Spring LDAP — LdapEncoder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html): filterEncode và nameEncode.
- [Oracle JNDI LDAP Provider](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/module-summary.html): connect/read timeout và provider-specific properties.
- [Oracle JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): TLS handshake diagnostics và javax.net.debug.
- [Java StartTlsResponse API](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/javax/naming/ldap/StartTlsResponse.html): StartTLS negotiation và hostname verification.
- [Microsoft Learn — LDAP Signing Overview](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing): LDAP signing, TLS và event diagnostics trên Active Directory.
- [Microsoft Learn — LDAP Channel Binding](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding): channel binding và event IDs.
