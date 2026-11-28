# Ảnh hưởng của TLS, truststore và hostname trên máy chủ được giới thiệu

## 1. Tình huống: kết nối LDAP ban đầu an toàn, nhưng referral lại thất bại

Ứng dụng sử dụng **Spring Data LDAP** để đọc entry bằng repository hoặc `LdapTemplate`. Kết nối đến LDAP server A qua `ldaps://ldap-a.example.org:636` hoạt động bình thường. Tuy nhiên, khi tìm kiếm dưới một nhánh khác, A trả về **referral** trỏ tới LDAP server B:

```text
Ứng dụng Spring Boot
        |
        | (1) LDAPS: ldap-a.example.org:636
        |     TLS OK, bind OK, search ou=external
        v
  LDAP server A
        |
        | (2) LDAP referral:
        |     ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example
        v
  Ứng dụng/JNDI nhận referral
        |
        | (3) Kết nối MỚI tới ldap-b.partner.example
        |     DNS -> TCP -> TLS -> kiểm chứng cert -> bind -> Search
        v
  LDAP server B
```

Ở bước (3), ứng dụng có thể gặp:

- `SSLHandshakeException` vì **CA ký chứng chỉ của B** không nằm trong truststore mà JVM sử dụng.
- Lỗi **hostname verification** vì tên `ldap-b.partner.example` không khớp danh tính DNS trong chứng chỉ B.
- Timeout/DNS error vì máy ứng dụng không phân giải hoặc không kết nối được tới hostname B.
- Lỗi bind/ACL vì credential dùng ở A không hợp lệ hoặc không có quyền ở B.
- Rủi ro **hạ cấp bảo mật** nếu referral lại trỏ đến `ldap://...` và client tự động follow mà không bắt buộc StartTLS.

**Chìa khóa:** TLS tới A thành công **không tự bảo đảm** an toàn hoặc tính khả dụng của kết nối tới B. Máy chủ được giới thiệu (*referred server*) có endpoint, chứng chỉ, chain CA, hostname và chính sách xác thực riêng.

Đây là bài trong chương **Referrals và topology** của module `SPRING_DATA_LDAP`. Người học cần liên hệ referral với LDAP DN, vùng đặt dữ liệu, truy vấn repository/`LdapTemplate`, bảo mật kết nối và kiểm thử trên directory thật.

### Sau bài học, bạn có thể

1. Phân biệt **referral**, **continuation reference**, **failover URL** và bản sao directory.
2. Giải thích vì sao cần kiểm tra TLS/CA/hostname **lại từ đầu** khi kết nối tới máy chủ được giới thiệu.
3. Nhận diện nguy cơ gửi credential qua referral không tin cậy hoặc qua kết nối plaintext.
4. Cấu hình `Context.REFERRAL` của JNDI và `ContextSource.setReferral(...)` của Spring LDAP.
5. Thiết kế **allowlist** endpoint và cơ chế xử lý referral theo hướng từ chối mặc định khi chưa xác minh.
6. Chẩn đoán lỗi PKIX, SAN/hostname, truststore, DNS, referral loop, bind và ACL.
7. Xây ma trận kiểm thử tích hợp với hai LDAP server, trong đó có các trường hợp cần bị từ chối.

## 2. Referral là gì trong topology LDAP?

Một directory có thể phân tán dữ liệu qua nhiều server, naming context, domain hoặc tổ chức. Ví dụ:

```text
ldap-a.example.org
  dc=example,dc=org
    ou=people
    ou=external     ----referral---->
                                      ldap-b.partner.example
                                        dc=partner,dc=example
                                          ou=people
```

Nếu A không giữ entry cần tìm nhưng biết nơi có khả năng đáp ứng, nó có thể trả về một hoặc nhiều **LDAP URLs** để client tiếp tục thao tác. Theo RFC 4511:

- **Referral result**: một LDAP operation nhận result code `referral` (**10**) kèm một hay nhiều URI tham chiếu tới server khác.
- **SearchResultReference** (*continuation reference*): trong quá trình Search, server có thể trả các tham chiếu để client tiếp tục tìm ở vùng dữ liệu không nằm tại server hiện tại.
- Client có thể chọn **không follow**, **follow tự động** hoặc **xử lý có kiểm soát** theo API và policy.
- Nếu follow, client phải tránh **vòng lặp referral** và giới hạn số lần chuyển hướng/độ sâu.

Referral không phải:

| Khái niệm | Có nghĩa gì? | Khác referral ở điểm nào? |
| --- | --- | --- |
| Referral | Server trả URI hướng client tới nơi có dữ liệu hoặc có thể xử lý request. | Client phải quyết định có kết nối đến endpoint mới không. |
| Continuation reference | Tham chiếu xuất hiện **trong** kết quả một Search đang duyệt nhiều vùng. | Có thể xuất hiện cùng với các entry hợp lệ của server ban đầu. |
| Failover URLs | Ứng dụng cấu hình nhiều endpoint ban đầu, ví dụ A1/A2. | Danh sách được ứng dụng cấu hình trước, không nhất thiết phát sinh từ referral. |
| Replica/load balancing | Nhiều node phục vụ cùng naming context. | Endpoint và chứng chỉ phải được quản trị phù hợp; không mặc nhiên có LDAP referral. |
| Alias LDAP | Entry biểu diễn tên khác theo cơ chế alias/dereference. | Không phải URL chuyển đến một LDAP server khác. |
| DN | Tên phân cấp của entry, ví dụ `uid=linh,ou=people,dc=example,dc=org`. | DN là vị trí/định danh dữ liệu, không phải hostname của TLS. |

Một referral URL có thể mang **server, port và DN đích**, đôi khi còn có attributes, search scope, filter theo cú pháp RFC 4516. Ví dụ:

```text
ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example
```

Không được tự động dùng DN tương đối của A như thể server B cũng có cùng `dc=example,dc=org`. B có thể phục vụ naming context khác; client theo referral phải xử lý DN/URL theo đúng contract của LDAP.

## 3. Điều gì thay đổi khi chuyển từ server A sang server B?

Mỗi kết nối TCP/TLS là một mối quan hệ riêng giữa client và server:

```text
                   KẾT NỐI A                       KẾT NỐI B
  URL              ldaps://ldap-a.example.org      ldaps://ldap-b.partner.example
  DNS              A records của ldap-a            A records của ldap-b
  TCP              đến port 636 của A               đến port 636 của B
  TLS cert         chứng chỉ A                      chứng chỉ B
  Certificate SAN  ldap-a.example.org               ldap-b.partner.example
  Chain/CA         CA của A                         CA của B (có thể khác)
  Bind/ACL         principal có quyền ở A          có thể cần principal khác
  Search base      OU/DN của A                      DN từ referral URL
```

### 3.1. Ba phép kiểm tra độc lập

Để kết nối an toàn tới **B**, phải kiểm tra đồng thời:

1. **Bản sắc endpoint được phép:** B có nằm trong danh sách máy chủ tổ chức **cho phép** ứng dụng truy cập không? Referral từ một server không nên tự cấp quyền truy cập mạng đến endpoint mới.
2. **Tin cậy chứng chỉ:** certificate chain của B có được ký/neo vào CA phù hợp trong **truststore thực sự JVM sử dụng** không, chứng chỉ còn hạn và đáp ứng yêu cầu TLS không?
3. **Tên máy chủ khớp chứng chỉ:** hostname được client dùng để nối đến B có khớp các DNS/IP identity hợp lệ trong chứng chỉ của B không?

Các điều kiện này khác nhau:

| Trường hợp | Trust chain hợp lệ? | Hostname khớp? | Có được tiếp tục tự động? |
| --- | --- | --- | --- |
| B được phép, CA tin cậy, SAN đúng. | Có. | Có. | Có thể, **nếu** policy referral và credential cũng hợp lệ. |
| B dùng CA nội bộ chưa import. | Không. | Có thể có. | **Không**; báo lỗi trust. |
| B có cert hợp lệ cho `ldap-a` nhưng URL dùng `ldap-b`. | Có. | **Không**. | **Không**; hostname mismatch. |
| B có cert hợp lệ, nhưng nằm ngoài allowlist. | Có. | Có. | **Không**; TLS tốt không thay thế authorization endpoint. |
| Referral chỉ có `ldap://B:389`. | Chưa thiết lập TLS. | Chưa kiểm tra. | Không gửi simple bind trừ khi client có cơ chế **bắt buộc** StartTLS thành công. |
| B đúng TLS nhưng principal không có quyền. | Có. | Có. | TLS có thể OK, nhưng Bind/Search vẫn phải bị từ chối theo policy. |

Đừng khắc phục hostname mismatch bằng cách tắt kiểm tra hostname, cũng đừng giải quyết CA chưa tin cậy bằng custom trust manager “accept all”. Những cách này làm mất bảo vệ chống server giả mạo.

## 4. TLS trên server được giới thiệu: LDAPS khác StartTLS

### 4.1. LDAPS

`ldaps://ldap-b.partner.example:636` chỉ định LDAP qua TLS ngay khi mở kết nối. JVM xác minh certificate chain và server identity trước khi gửi những thông tin nhạy cảm của LDAP Bind/Search.

Với JNDI/Spring LDAP, endpoint `ldaps://...` là tín hiệu cấu hình kênh TLS; **không** cần tự ghép chứng chỉ vào LDAP DN. Java JSSE sử dụng truststore và cấu hình TLS của JVM/SSL context.

### 4.2. StartTLS

`ldap://ldap-b.partner.example:389` không tự biểu thị kết nối đã mã hóa. Muốn sử dụng StartTLS, client cần:

1. Tạo kết nối LDAP chưa bind bằng mật khẩu nhạy cảm.
2. Yêu cầu **StartTLS** trên **chính kết nối đó**.
3. Hoàn tất TLS handshake và xác minh danh tính server B.
4. **Chỉ sau khi TLS đã thiết lập và được kiểm chứng** mới thực hiện simple Bind hoặc trao đổi dữ liệu nhạy cảm.

Theo RFC 4513, nếu định dùng cả StartTLS lẫn Bind, nên thực hiện StartTLS trước Bind để bảo vệ credential. **Không** xem “server có hỗ trợ StartTLS” tương đương “client thực sự đã nâng cấp thành công”.

### 4.3. Referral có thể làm mất bảo vệ TLS ban đầu

```text
Ứng dụng -- LDAPS 636 --> A              [TLS bảo vệ]
                               |
                               +-- referral: ldap://B:389
                                                    |
                                           [CHƯA CÓ TLS]
                                                    |
                                   BIND credential?  <- phải từ chối
```

`Context.REFERRAL="follow"` của JNDI yêu cầu **tự động follow**; nó không đồng nghĩa một chính sách được thiết kế riêng để **bắt buộc StartTLS rồi mới bind** đối với mọi `ldap://` referral. Không được giả định TLS của A sẽ “kế thừa” sang B.

**Chính sách an toàn:** nếu ứng dụng không kiểm soát chắc chắn quá trình StartTLS ở endpoint B, chỉ cho phép các referral tới endpoint **`ldaps://`** đã được xét duyệt. Nếu tổ chức cần StartTLS, phải triển khai và kiểm thử đường đi riêng, fail-closed khi TLS negotiation thất bại; không dùng fallback sang plaintext.

## 5. Truststore: vì sao A được tin nhưng B không?

Truststore là tập certificate/CA mà **client Java** sử dụng để xây và kiểm tra chuỗi chứng chỉ của server. Đây là truststore, không phải keystore chứa **private key của client**.

### 5.1. Mô hình hai chuỗi chứng chỉ

```text
LDAP server A                             LDAP server B
  cert: ldap-a.example.org                 cert: ldap-b.partner.example
            |                                          |
       Intermediate A                             Intermediate B
            |                                          |
         Root CA A                                  Root CA B
            |                                          |
            +-------------------+----------------------+
                                |
                         JVM truststore
                   phải tin CA của endpoint
                         thực sự truy cập
```

Nếu JVM chỉ tin Root CA A, đường kết nối ban đầu tới A có thể hoạt động hoàn toàn bình thường, nhưng khi follow referral sang B sẽ xuất hiện lỗi kiểu:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

Đây là dấu hiệu cần kiểm tra **chain/CA/truststore** của B, không phải bằng chứng mật khẩu tài khoản LDAP sai. Tuy nhiên, lỗi `PKIX` còn có thể đến từ intermediate certificate thiếu, certificate validity hoặc cấu hình TLS/PKI khác; không chỉ do “chưa import root CA”.

### 5.2. Java dùng truststore nào?

Với JNDI LDAPS mặc định, TLS thường đi qua **JSSE**. Nguồn trust có thể là:

- Truststore JVM mặc định, phụ thuộc JDK/runtime và cấu hình hệ thống.
- Truststore được chỉ định qua `javax.net.ssl.trustStore`, `javax.net.ssl.trustStoreType`, `javax.net.ssl.trustStorePassword`.
- SSL socket factory/trust manager được cấu hình riêng, nếu ứng dụng triển khai và tích hợp đúng API.

Khi khai báo một truststore tùy chỉnh, **không được mặc định rằng nó tự hợp nhất với các CA mặc định của JVM**. Một file chỉ chứa CA B có thể khiến kết nối A trước đây thành công nay thất bại nếu CA A không còn trong tập tin cậy.

### 5.3. Tạo truststore kiểm thử có kiểm soát

Giả sử đội quản trị đã cung cấp **public CA certificate** `partner-ca.pem` của B và đã xác nhận fingerprint qua kênh đáng tin cậy. Có thể tạo PKCS#12 truststore bằng:

```bash
keytool -importcert -trustcacerts \
  -alias partner-ldap-ca \
  -file partner-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
```

`keytool` sẽ yêu cầu tạo/nhập mật khẩu. **Chỉ import CA/chứng chỉ đã được xác minh nguồn gốc**; không tải chứng chỉ từ endpoint bất kỳ rồi tự động tin cậy nó chỉ vì kết nối báo lỗi.

Xem lại nội dung truststore:

```bash
keytool -list -v \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
```

Để JVM dùng truststore trong một lần chạy, cấu hình các Java system properties liên quan, ví dụ:

```text
-Djavax.net.ssl.trustStore=/etc/app/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Cách cấp password cho truststore phụ thuộc môi trường chạy và chính sách secret. Tránh đưa `trustStorePassword` như chuỗi literal vào tài liệu deploy, git hoặc command line bị ghi lại trong process list. Quản lý secret và quyền file, dùng cơ chế injection đáng tin cậy của môi trường.

**Đặc biệt:** truststore JVM là hạ tầng dùng chung trong nhiều ứng dụng Java. Đừng thay đổi `cacerts` của JDK đang dùng chung mà không có kiểm soát; nên dùng truststore riêng được quản lý hoặc một SSL context rõ ràng và kiểm thử cả A lẫn B sau thay đổi.

### 5.4. Khi nào chỉ trust CA không đủ?

Trường hợp B được ký bởi cùng Root CA với A **nhưng hostname không khớp**, kết nối vẫn phải thất bại. TLS authentication gồm cả chain validation **và** endpoint identity verification.

Truststore không giải quyết:

- Referral dẫn đến hostname không được DNS phân giải.
- Cổng B không mở hoặc listener không hỗ trợ TLS.
- Chứng chỉ dành cho host khác.
- Bind principal không có quyền ở B.
- Policy cấm đi tới endpoint B dù chứng chỉ hoàn toàn hợp lệ.

## 6. Hostname verification: tên trong referral quan trọng đến mức nào?

Giả sử referral URL:

```text
ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example
```

**Hostname tham chiếu** (*reference identity*) là `ldap-b.partner.example` — tên client thực sự dùng trong URL của kết nối B. Trong triển khai TLS đúng chuẩn, server certificate phải chứng minh quyền sử dụng tên đó, thường qua **Subject Alternative Name (SAN) DNS**.

### 6.1. Các trường hợp phổ biến

| Referral URL | SAN được cấp | Kết quả mong đợi |
| --- | --- | --- |
| `ldaps://ldap-b.partner.example:636` | DNS:`ldap-b.partner.example` | Khớp hostname, nếu chain cũng được tin. |
| `ldaps://ldap-b.partner.example:636` | DNS:`ldap-a.example.org` | **Không khớp**, dù CA được tin cậy. |
| `ldaps://directory.partner.example:636` | DNS:`ldap-b.partner.example` | Thường **không khớp alias**, trừ khi SAN có thêm `directory.partner.example`. |
| `ldaps://192.0.2.20:636` | Chỉ có DNS:`ldap-b.partner.example` | IP trong URL cần identity IP phù hợp; không tự coi DNS SAN là đủ. |
| `ldaps://directory.partner.example:636` | DNS:`directory.partner.example` | Có thể khớp khi TLS termination/LB dùng cert cho alias. |

Tên miền ví dụ, IP `192.0.2.20` và hostname trong bảng chỉ dùng minh họa.

### 6.2. DNS, CNAME và load balancer

Khi DNS `ldap-b.partner.example` trỏ CNAME hoặc A record tới một host vật lý khác, certificate verification vẫn cần kiểm tra **tên tham chiếu mà client dùng**, không tùy ý thay bằng tên reverse DNS của máy chủ phía sau.

Nếu referral dùng tên nội bộ của node `ldap-b-01.internal` trong khi chứng chỉ chỉ có SAN `directory.partner.example`, kết nối có thể thất bại. Các cách khắc phục hợp lệ:

1. Cấu hình referral URL dùng **hostname đã được cấp chứng chỉ** và client có thể truy cập.
2. Cấp chứng chỉ mới có SAN phù hợp cho endpoint thực tế, theo chính sách PKI.
3. Kiểm tra routing/load balancer để tên DNS trong referral khớp nơi kết thúc TLS.

**Không** tắt hostname verification, không thêm `trust-all`, không gán hostname cố định vào custom verifier để chấp nhận mọi endpoint.

### 6.3. Hostname trong referral khác DN của LDAP

```text
ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example
        ^^^^^^^^^^^^^^^^^^^^^^    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        hostname cần đối chiếu       DN mục tiêu của LDAP Search
        với certificate SAN         (schema/ACL/đường dẫn dữ liệu)
```

Thêm `dc=partner,dc=example` vào `ContextSource.base` không thể sửa mismatch giữa `ldap-b.partner.example` và SAN certificate. Chúng thuộc hai tầng khác nhau: **TLS server identity** và **LDAP namespace**.

## 7. Referral và credential: nguy cơ lớn hơn lỗi kết nối

Đối với JNDI, referral không chỉ thay endpoint. Khi follow, provider có thể dùng lại **thông tin môi trường** của context ban đầu, gồm cấu hình xác thực và credential. Tài liệu Oracle về `ReferralException.getReferralContext()` nêu rằng nếu không cung cấp môi trường khác, context được giới thiệu mặc định có thể được tạo bằng environment cũ, bao gồm các thuộc tính liên quan đến xác thực.

Điều này tạo rủi ro:

```text
Context A:
  principal = uid=svc-reader,ou=service-accounts,dc=example,dc=org
  secret    = ********
        |
        | referral tới server do bên khác vận hành
        v
Server B có thể nhận yêu cầu xác thực hoặc thông tin
mà ứng dụng không có chủ ý chia sẻ với B.
```

Một chứng chỉ TLS hợp lệ cho B **chỉ xác minh danh tính endpoint B**; nó không tự chứng minh rằng **B được phép nhận credential của A**. Ngược lại, B có thể có tài khoản dịch vụ khác, trust domain khác hoặc chỉ cho phép anonymous reads.

### 7.1. Quy tắc bảo vệ credential

- Không cho auto-follow referral đến server chưa được chủ sở hữu dữ liệu/PKI và đội bảo mật phê duyệt.
- Không chuyển simple bind credentials qua `ldap://` không được bảo vệ.
- Nếu B thuộc trust domain khác, đánh giá tài khoản bind **riêng cho B** với quyền tối thiểu; không mặc định reuse credential của A.
- Gắn allowlist theo **hostname/port/scheme**, loại DN, operation và chính sách mạng.
- Giới hạn redirect depth/hops và tránh referral loop.
- Khi có referral bất ngờ, **fail closed** hoặc xử lý thủ công có kiểm soát, không “thử theo mọi URL cho đến khi thành công”.
- Bảo vệ và giám sát secret ở runtime; không in `ReferralException.getReferralInfo()` nguyên trạng ra log public nếu URL chứa thông tin nhạy cảm.

### 7.2. LDAP referral cũng là một đường điều hướng mạng

Một referral URL độc hại hoặc cấu hình sai có thể khiến ứng dụng cố kết nối đến host bất ngờ, gây nguy cơ tương tự **server-side request forgery (SSRF)**. Kể cả hostname hợp lệ trong PKI, endpoint không được cho phép vẫn phải bị từ chối.

Không dùng **DNS resolution** làm tiêu chí phân quyền duy nhất: một tên được phép phải được ràng buộc với domain, port, identity và policy egress; DNS có thể thay đổi hoặc trỏ sang địa chỉ không mong đợi.

## 8. JNDI: ignore, follow và throw

JNDI cho phép cấu hình referral bằng `Context.REFERRAL`, tức property `java.naming.referral`:

| Chế độ | Ý nghĩa | Điểm cần lưu ý về bảo mật |
| --- | --- | --- |
| `ignore` | Không tự follow; xử lý theo semantics JNDI/provider. | Với LDAPv3, provider có thể gửi ManageDsaIT control; không đồng nghĩa luôn bỏ qua referral một cách im lặng. |
| `follow` | Tự động follow referral. | **Nguy hiểm nếu URL/credential/TLS chưa được xét duyệt**; client có thể kết nối sang B ngoài ý muốn. |
| `throw` | Gặp referral thì ném `ReferralException`. | Cho ứng dụng cơ hội xem xét/policy trước khi kết nối; code cần xử lý cả trong lúc duyệt search results. |

Theo JNDI của Oracle, `ignore` là mặc định và có tương tác với Manage Referral Control (RFC 3296). Một số server, đặc biệt trong một số topology Active Directory, vẫn có thể gây `PartialResultException` khi không follow được continuation references.

**Không** coi `PartialResultException` như “truy vấn hoàn tất” nếu nghiệp vụ cần kết quả đầy đủ từ nhiều nhánh. Việc cấu hình Spring LDAP bỏ qua `PartialResultException` có thể dẫn tới **mất kết quả một cách im lặng**.

### 8.1. Cấu hình minh họa bằng JNDI

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.InitialDirContext;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL,
        "ldaps://ldap-a.example.org:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
        System.getenv("LDAP_BIND_DN"));
env.put(Context.SECURITY_CREDENTIALS,
        System.getenv("LDAP_BIND_PASSWORD"));
env.put(Context.REFERRAL, "throw");
env.put("com.sun.jndi.ldap.connect.timeout", "3000");
env.put("com.sun.jndi.ldap.read.timeout", "5000");

InitialDirContext ctx = new InitialDirContext(env);
// Tìm kiếm/đóng context được minh họa ở phần kế tiếp.
```

Chú ý: đoạn code dùng `"throw"` có chủ đích, **không tự follow**. Cả kết nối ban đầu và một kết nối sau khi xét duyệt đều cần TLS/credential policy riêng.

### 8.2. Bắt referral khi tìm kiếm và khi duyệt kết quả

Referral có thể được báo ở lời gọi `search` **hoặc khi iterating `NamingEnumeration`**. Ví dụ Java 17:

```java
package com.example.directory;

import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.ReferralException;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public final class ReferralDiagnostics {
    private ReferralDiagnostics() {}

    public static void inspect() throws NamingException {
        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
            "ldaps://ldap-a.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
            System.getenv("LDAP_BIND_DN"));
        env.put(Context.SECURITY_CREDENTIALS,
            System.getenv("LDAP_BIND_PASSWORD"));
        env.put(Context.REFERRAL, "throw");
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        InitialDirContext ctx = new InitialDirContext(env);
        NamingEnumeration<SearchResult> results = null;
        try {
            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
            controls.setReturningAttributes(new String[] {"uid"});
            results = ctx.search(
                "ou=external,dc=example,dc=org",
                "(objectClass=inetOrgPerson)",
                controls
            );
            while (results.hasMore()) {
                SearchResult item = results.next();
                // Chỉ xử lý những thuộc tính thật sự cần thiết.
            }
        } catch (ReferralException referral) {
            Object info = referral.getReferralInfo();
            // CHƯA gọi getReferralContext(): phải xét duyệt URL,
            // scheme, host, port, DN và chính sách credential.
            throw referral;
        } finally {
            try {
                if (results != null) results.close();
            } finally {
                ctx.close();
            }
        }
    }
}
```

Ví dụ trên cố ý **dừng khi gặp referral** thay vì tiếp tục gửi credential tới một host chưa kiểm tra. Biến `info` là nội dung cần xử lý qua policy, không phải dữ liệu đáng tin cậy. Không dùng `getReferralContext()` trước khi có allowlist/cấu hình TLS và xác thực phù hợp; API này có thể lấy môi trường xác thực từ context gốc.

Để có quy trình follow thủ công hoàn chỉnh, cần quản lý nhiều referral URL, exception/continuation references, các request được tái thực hiện, tài nguyên context, số hop và việc phân biệt credential. Bài này chỉ minh họa **điểm chặn an toàn**, không khuyến khích tự viết LDAP referral engine sơ sài cho production.

## 9. Spring LDAP: referral policy ở ContextSource

Spring LDAP có `AbstractContextSource.setReferral(String)`, thường được sử dụng qua `LdapContextSource`. Giá trị hợp lệ là `ignore`, `follow` hoặc `throw`; JNDI provider thực hiện logic tương ứng.

### 9.1. Cấu hình cố định và fail-closed

```java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfig {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setReferral("throw");
        // Spring gọi init lifecycle của bean và tạo context khi dùng.
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource source) {
        LdapTemplate template = new LdapTemplate(source);
        // Không coi PartialResultException là Search thành công.
        template.setIgnorePartialResultException(false);
        return template;
    }
}
```

Và `application.yml`:

```yaml
directory:
  ldap:
    url: ${LDAP_INITIAL_URL:ldaps://ldap-a.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Lưu ý:

- `setReferral("throw")` cho provider phát hiện referral, không đồng nghĩa mọi `LdapTemplate` method sẽ trả **trực tiếp** checked `javax.naming.ReferralException`. Spring có thể **dịch hoặc bọc exception**; nếu phải điều phối referral theo URL, nên thiết kế tầng JNDI riêng hoặc kiểm tra contract/version cụ thể.
- `setIgnorePartialResultException(false)` dùng để **không che giấu** phần kết quả chưa được xử lý; không biến referral thành một danh sách rỗng.
- `@Entry(base=...)` của ODM và `spring.ldap.base` quy định LDAP DN, **không** điều chỉnh certificate trust hoặc TLS hostname.
- Trong ứng dụng có nhiều `ContextSource`, chỉ rõ bean mà repository và `LdapTemplate` sử dụng; đừng giả định mọi repository tự chọn đúng credential cho B.
- Chỉ dùng `setReferral("follow")` nếu **toàn bộ đích có thể xuất hiện trong referral** đã được kiểm soát, test và phù hợp chính sách mạng/TLS/credential. API `follow` không cung cấp allowlist hostname chuyên biệt sẵn có cho từng URL.

### 9.2. Nếu đã biết hai server hợp lệ?

Với topology nhỏ và hợp đồng rõ ràng, một lựa chọn ít bất ngờ hơn là cấu hình **hai `ContextSource`** riêng:

```text
LdapContextSource A
  url=ldaps://ldap-a.example.org:636
  bind=svc-a (quyền tối thiểu A)
  trust policy=CA/SAN A

LdapContextSource B
  url=ldaps://ldap-b.partner.example:636
  bind=svc-b (quyền tối thiểu B)
  trust policy=CA/SAN B
```

Application service chọn endpoint **đã được cấu hình và phê duyệt**, không nhận URL bất kỳ từ LDAP response. Cách này không phải lúc nào cũng thay thế được referral trong topology động, nhưng thường dễ kiểm soát trách nhiệm/credential khi dữ liệu phân tán cố định.

## 10. Kiểm tra referral URL trước khi kết nối

Một referral URL là **đầu vào từ server khác**, không nên sử dụng trực tiếp để tạo kết nối nếu chưa kiểm tra scheme/host/port, điều kiện truy vấn và policy.

### 10.1. Ví dụ allowlist tối thiểu cho endpoint

Đây là code kiểm tra **một điều kiện bắt buộc**, chưa phải hệ thống xử lý referral hoàn chỉnh:

```java
package com.example.directory.security;

import java.net.URI;
import java.util.Locale;
import java.util.Set;

public final class ReferralEndpointPolicy {
    private static final Set<String> ALLOWED_HOSTS =
        Set.of("ldap-b.partner.example");

    private ReferralEndpointPolicy() {}

    public static boolean allow(String rawUrl) {
        final URI uri;
        try {
            uri = URI.create(rawUrl);
        } catch (IllegalArgumentException ex) {
            return false;
        }

        if (!"ldaps".equalsIgnoreCase(uri.getScheme())) {
            return false; // Không follow LDAP plaintext.
        }

        String host = uri.getHost();
        if (host == null ||
                !ALLOWED_HOSTS.contains(host.toLowerCase(Locale.ROOT))) {
            return false;
        }

        if (uri.getRawUserInfo() != null || uri.getFragment() != null) {
            return false;
        }

        int port = uri.getPort();
        return port == -1 || port == 636;
    }
}
```

**Giới hạn:** policy trên chưa xác minh LDAP URL chứa DN/filter/scope hợp lệ hoặc được phép, chưa ngăn referral loop, chưa kiểm tra DNS/IP egress, chưa tạo SSLContext hay chọn credential cho B. Không dùng giá trị `true` làm bằng chứng referral “an toàn tuyệt đối”. Trong production, chỉ follow sau khi:

1. URI và cú pháp **LDAP URL** đầy đủ hợp lệ theo RFC 4516.
2. Scheme, hostname, port và **mạng đích** được phê duyệt.
3. DN/search scope/filter từ URL nằm trong phạm vi nghiệp vụ cho phép.
4. TLS handshake với B thành công, chain được tin và SAN phù hợp hostname.
5. Bind identity được chọn riêng hoặc được phép dùng tại B, không lộ credential của A.
6. Giới hạn số lần chuyển hướng, loop detection, timeout và số lượng kết quả.

Nếu một referral chứa nhiều URI, không chọn mù quáng URI tiếp theo sau khi URI đầu lỗi TLS; việc fallback phải tuân chính sách tương tự. **Không được chuyển sang endpoint kém bảo mật chỉ để hoàn tất truy vấn.**

## 11. Chẩn đoán theo loại lỗi

| Lỗi/triệu chứng | Tầng xảy ra | Nguyên nhân có thể | Cách điều tra an toàn |
| --- | --- | --- | --- |
| `PKIX path building failed` | TLS chain trust | CA B chưa được tin, intermediate thiếu, chain không hợp lệ. | So sánh chain B với truststore JVM thực dùng; xác minh nguồn CA trước khi import. |
| `No subject alternative DNS name matching ...` | TLS hostname | Referral URL dùng alias/nút khác với SAN. | Kiểm tra URL và SAN; sửa referral URL hoặc certificate hợp lệ. |
| `SSLHandshakeException` không rõ | TLS | Protocol/cipher mismatch, expired cert, mTLS, chain/hostname. | Kiểm tra cause, server logs, JSSE debug trong lab. |
| `UnknownHostException` | DNS | Tên B không được phân giải từ máy chạy ứng dụng. | Kiểm tra DNS từ chính pod/container/VM, không chỉ máy cá nhân. |
| `ConnectException: Connection refused` | TCP | Port sai, firewall hoặc B chưa mở listener. | Kiểm tra scheme/port, firewall và cấu hình dịch vụ. |
| `SocketTimeoutException` | TCP/network/LDAP | Routing, firewall, server chậm hoặc treo. | Timeout có giới hạn; theo dõi DNS, mạng và request. |
| `AuthenticationException`/LDAP 49 | LDAP Bind | Credential của A không hợp lệ trên B hoặc account bị khóa. | Xác minh danh tính/secret **được phép dùng ở B**, không dùng admin làm workaround. |
| `NoPermissionException`/LDAP 50 | LDAP ACL | Bind thành công nhưng thiếu quyền trên DN/attribute ở B. | Kiểm tra policy B và nhu cầu nghiệp vụ. |
| `NameNotFoundException`/LDAP 32 | LDAP namespace | DN trong referral không tồn tại hoặc base/scope sai. | Kiểm tra DN thực tế trên B bằng tài khoản test. |
| `ReferralException` | LDAP client policy | Chế độ `throw` và có referral. | Kiểm tra referral URL và chính sách, chưa tự động follow. |
| `PartialResultException` | Search references | Có continuation reference không được xử lý. | Xem chính sách referral; không nuốt lỗi nếu cần dữ liệu đầy đủ. |
| Vòng lặp A → B → A | Topology/client follow | Referral cycle/misconfiguration. | Giới hạn hop, ghi nhận cặp endpoint/request và sửa topology. |
| Truy vấn về ít kết quả | Search/ACL/referral | Chỉ một phần nhánh được tìm hoặc client bỏ qua reference. | Đối chiếu kết quả từng server test và phạm vi nghiệp vụ. |

Nhiều exception TLS phía dưới có thể được JNDI bọc trong `javax.naming.CommunicationException` rồi Spring LDAP chuyển thành exception runtime. Khi chẩn đoán, kiểm tra **cause chain** thay vì chỉ tên exception ở lớp service.

### 11.1. Phân biệt PKIX và hostname mismatch

```text
CA chưa được tin:
  B gửi cert -> JVM không xây được chain đến trust anchor -> lỗi PKIX

Hostname không khớp:
  B gửi cert, chain hợp lệ -> SAN không có hostname từ referral URL
  -> lỗi endpoint identification

Hai trường hợp đều phải thất bại, nhưng cách khắc phục KHÁC NHAU.
```

Nhập CA mới chỉ có thể giải quyết trust; nó **không sửa SAN sai**. Đổi hostname referral chỉ đúng khi hostname mới được phép, DNS trỏ đúng endpoint và certificate chứng minh danh tính hợp lệ.

## 12. Quy trình kiểm tra thực tế từ A đến B

Chỉ sử dụng endpoint test hoặc môi trường được cấp phép. Không thay truststore/chứng chỉ production, không tắt hostname verification và không thử bind bằng secret thật đến host không được phê duyệt.

### Bước 1 — Xác định referral URL thật

Ghi lại tối thiểu:

```text
Initial URL  : ldaps://ldap-a.example.org:636
Referral URL : ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example
Operation    : Search
Filter       : (uid=linh)
Bind alias   : svc-directory-reader
```

Đừng xuất raw secret, token hoặc toàn bộ thông tin LDAP nhạy cảm. Đừng giả định B có cùng `base DN` với A.

### Bước 2 — Kiểm tra DNS/TCP/TLS của B độc lập

Ở máy thực sự chạy ứng dụng:

```bash
nslookup ldap-b.partner.example
```

Nếu có OpenSSL và bạn đã có CA đáng tin để thử:

```bash
openssl s_client \
  -connect ldap-b.partner.example:636 \
  -servername ldap-b.partner.example \
  -verify_hostname ldap-b.partner.example \
  -CAfile partner-ca.pem \
  -verify_return_error
```

Kiểm tra certificate subject/SAN, chain và thông báo verification. Lệnh trên kiểm tra **TLS**, không tự chứng minh bind LDAP, ACL hay rằng JVM dùng đúng truststore. Một phiên OpenSSL kết nối được cũng không chứng minh Java sẽ thành công khi Java sử dụng tập CA khác.

### Bước 3 — Kiểm tra truststore của JVM

```bash
keytool -list -v \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
```

Xác nhận CA B đã được import đúng; CA A vẫn còn nếu cấu hình truststore thay thế mặc định; không chứa cert không được phê duyệt. Kiểm tra startup flags và image JDK/container thực tế, không chỉ môi trường development.

### Bước 4 — Thử LDAP Bind/Search trực tiếp tới B

**Chỉ sau khi endpoint, TLS và credential đã được phê duyệt**, dùng một bind account thử nghiệm có quyền trên B:

```bash
ldapsearch -x \
  -H "ldaps://ldap-b.partner.example:636" \
  -D "uid=svc-partner-reader,ou=services,dc=partner,dc=example" -W \
  -b "ou=people,dc=partner,dc=example" \
  "(uid=linh)" dn uid cn
```

Với `ldapsearch -b`, DN được truyền **đầy đủ**. Trong `LdapTemplate` đã cấu hình `ContextSource.base`, DN của các thao tác thông thường là tương đối với base đó. Thử trực tiếp B giúp tách lỗi TLS/ACL/B từ lỗi referral client-side.

### Bước 5 — So sánh với ứng dụng thực tế

Khi B truy vấn trực tiếp được nhưng ứng dụng theo referral lỗi:

1. Kiểm tra `Context.REFERRAL` / `ContextSource.setReferral`.
2. Kiểm tra truststore JVM, certificate identity và chính xác hostname được JNDI dùng.
3. Kiểm tra credential thực dùng khi `getReferralContext()`/auto-follow.
4. Kiểm tra DNS/routing **trong pod/container** và connection pooling.
5. Kiểm tra referral URL có DN/filter/scope khác với truy vấn ban đầu.
6. Kiểm tra error/partial results có bị Spring service che giấu không.

Trong môi trường thử nghiệm cô lập, Java JSSE có thể bật chẩn đoán:

```text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
```

Debug SSL có thể tạo log rất lớn, chứa metadata nhạy cảm về hạ tầng; giới hạn thời gian và quyền truy cập. Đừng chạy các debug flags này liên tục trong production hoặc đăng log đầy đủ công khai.

## 13. Ảnh hưởng đến Spring Data LDAP Repository/ODM

Repository giúp tìm và lưu entry:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    List<DirectoryPerson> findBySurname(String surname);
}
```

`DirectoryPerson` là entity ODM được ánh xạ với `@Entry`, `@Id`, `@Attribute` và `@DnAttribute`; ví dụ không trình bày lại toàn bộ entity để giữ trọng tâm vào referral.

**Repository không tự cấp các bảo đảm sau:**

- Tự thêm CA của máy chủ B vào truststore.
- Tự điều chỉnh DNS/SAN hostname cho referral URL.
- Tự tạo StartTLS khi URL referral là `ldap://`.
- Tự chọn credential tối thiểu phù hợp cho mỗi domain/trust boundary.
- Tự ngăn SSRF từ referral trỏ tới endpoint không được phép.
- Tự bảo đảm Search trả đầy đủ dữ liệu khi một continuation reference bị bỏ qua.

Trong một nghiệp vụ `findBySurname`, Search ban đầu có thể lấy kết quả từ A và sau đó gặp continuation reference từ B. Nếu ứng dụng đặt `ignorePartialResultException=true` để im lặng bỏ qua vấn đề, kết quả có thể thiếu những người ở B. **“Không có kết quả” khác với “không lấy được kết quả”**.

Nếu dữ liệu thuộc nhiều domain/trust boundary và cần tính đúng đắn cao, nên thiết kế service điều phối truy vấn rõ ràng:

```text
HTTP request -> DirectorySearchService
                       |
                       +-> Repository/Template A
                       |
                       +-> Repository/Template B
                       |
                       +-> Gộp kết quả theo khóa nghiệp vụ
                           + báo nguồn/lỗi từng nhánh
```

Phương án này áp dụng khi các nguồn được cấu hình trước, có thể truy vấn hợp lệ và đã được phê duyệt; không phải lời giải chung cho mọi topology LDAP động. Khi gộp, cần kiểm soát duplicate DN/UID, phân quyền và mức đầy đủ của kết quả.

## 14. Kiểm thử tích hợp: phải có trường hợp từ chối

Unit test có thể xác nhận code trả `false` với referral URL ngoài allowlist. Nó **không chứng minh** TLS handshake, CA chain, hostname verification hoặc credential isolation thực sự hoạt động. Cần integration test với **hai LDAP server riêng** và hạ tầng PKI thử nghiệm.

### 14.1. Topology lab đề xuất

```text
ldap-a.lab.example  -- LDAPS (CA-A) ->  initial directory
   |
   +-- referral to:
           ldaps://ldap-b.lab.example:636/ou=people,dc=partner,dc=lab
           |
           +-- LDAP B, cert SAN=ldap-b.lab.example (CA-B)

Ứng dụng:
  truststore LAB chứa CA-A + CA-B hợp lệ
  policy chỉ cho phép ldap-b.lab.example:636
  principal A và B được provision với quyền tối thiểu
```

Tất cả hostname trên chỉ minh họa, không phải endpoint công khai. Không test TLS downgrade bằng cách gửi production credential vào `ldap://`.

### 14.2. Ma trận kiểm thử

| Kịch bản | Thay đổi trong lab | Kết quả đúng |
| --- | --- | --- |
| Happy path | B có cert tin cậy/SAN đúng, URL `ldaps`, host được phép. | TLS tới B thành công; truy vấn hợp lệ theo quyền B. |
| CA-B chưa được tin | Truststore chỉ chứa CA-A. | **Fail TLS**; không chuyển sang plaintext. |
| Cert B sai SAN | Cert hợp lệ nhưng SAN chỉ chứa host khác. | **Fail hostname verification**. |
| Cert B hết hạn | Dùng cert hết hạn trong môi trường test. | **Fail TLS**, không disable verification. |
| Referral `ldap://` | A giới thiệu plaintext B:389. | Policy từ chối khi chưa có luồng StartTLS bắt buộc. |
| Referral host không có trong allowlist | A trả URL bất ngờ. | Không kết nối, không gửi credential. |
| Referral sang port không được phép | URL trỏ port khác 636. | Bị từ chối bởi endpoint policy. |
| B dùng principal khác | Credential A không hợp lệ ở B. | Lỗi auth được báo rõ; không tự nâng quyền hoặc thử admin. |
| B bind được nhưng không có read ACL | Reader thiếu quyền Search/Read. | Ghi nhận partial/unavailable theo nghiệp vụ, không báo user không tồn tại một cách chắc chắn. |
| DNS B lỗi từ container | Tên trong referral không resolve được. | Báo lỗi DNS/connection, không kết luận sai schema. |
| Vòng lặp A → B → A | Hai server trả referral qua lại. | Dừng theo giới hạn hop, không lặp vô hạn. |
| B unavailable sau khi A có kết quả | Ngắt B trong lúc Search. | Trả lỗi/đánh dấu partial; không âm thầm coi là dữ liệu đầy đủ. |
| Truststore thay thế thiếu CA-A | Chỉ import CA-B vào truststore mới. | Thấy A bắt đầu lỗi, sửa tập CA thay vì tắt TLS. |
| Referrals có DN lạ | B URL trỏ outside subtree được duyệt. | Từ chối theo policy DN/scope dù TLS hợp lệ. |

### 14.3. Kiểm thử an toàn bằng JUnit 5

Một unit test cho allowlist không cần kết nối mạng:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class ReferralEndpointPolicyTest {

    @Test
    void acceptsApprovedLdapsHost() {
        assertThat(ReferralEndpointPolicy.allow(
            "ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example"
        )).isTrue();
    }

    @Test
    void rejectsPlaintextAndUnapprovedHosts() {
        assertThat(ReferralEndpointPolicy.allow(
            "ldap://ldap-b.partner.example:389/ou=people"
        )).isFalse();

        assertThat(ReferralEndpointPolicy.allow(
            "ldaps://unapproved.example:636/ou=people"
        )).isFalse();

        assertThat(ReferralEndpointPolicy.allow(
            "ldaps://ldap-b.partner.example:1389/ou=people"
        )).isFalse();
    }
}
```

Trong project riêng, import `ReferralEndpointPolicy` từ package đã chọn ở mục 10. Unit test này chỉ kiểm tra allowlist; **integration test bắt buộc** phải dùng TLS server B với chứng chỉ thật (trong CA test), kết nối đúng Java truststore và xác thực/ACL như môi trường dự kiến.

**Không** tạo integration test “thành công” bằng cách cài custom TrustManager luôn trả true: làm vậy chỉ kiểm tra code bỏ qua xác minh, không kiểm tra an toàn TLS.

## 15. Sai lầm hay gặp và hướng sửa

| Nhận định/cách làm sai | Cách hiểu đúng |
| --- | --- |
| “LDAPS đến A thành công thì referral đến B cũng an toàn.” | B là kết nối TLS mới; cần kiểm tra lại chain, SAN và endpoint policy. |
| “Import CA của B sẽ chữa cả lỗi hostname.” | Trust chain và hostname verification độc lập. |
| “B có cert hợp lệ nên được gửi mật khẩu của A.” | TLS identity không thay thế quyền chia sẻ credential giữa các trust domain. |
| “B trả `ldap://` nhưng A là `ldaps://` nên đường đi vẫn mã hóa.” | B không tự kế thừa TLS của A; cần TLS riêng trước khi bind. |
| “`setReferral("follow")` luôn là cách tốt nhất.” | Auto-follow có thể mở kết nối tới URL chưa được xét duyệt và dùng lại credential. |
| “`ignorePartialResultException(true)` sửa xong lỗi referral.” | Có thể chỉ **che giấu dữ liệu bị thiếu**. |
| “Đổi `@Entry.base` để khắc phục PKIX.” | Base DN không ảnh hưởng certificate trust. |
| “Máy dev resolve được B thì container cũng resolve được.” | DNS/egress của pod/VM có thể khác. |
| “Nếu B bind thất bại, thử admin account.” | Cần tài khoản B đúng quyền; không mở rộng đặc quyền để che lỗi. |
| “Có truststore mới thì CA mặc định tự được kế thừa.” | Tập CA hiệu lực phải được kiểm tra; truststore tùy chỉnh có thể thay tập mặc định. |
| “Follow referral là tìm được tất cả entry chắc chắn.” | Có thể gặp loop, partial results, ACL, server lỗi hoặc duplicate. |
| “Tắt hostname verification để chạy qua load balancer.” | Sửa SAN/URL/routing đúng, không vô hiệu hóa bảo vệ TLS. |

## 16. Bài tập và checklist nghiệm thu

### Bài tập

1. A trả referral `ldaps://ldap-b.partner.example:636/ou=people,dc=partner,dc=example`. Mô tả chính xác những bước DNS/TCP/TLS/certificate/Bind/Search mà ứng dụng phải thực hiện tới B.
2. CA-A đã có trong truststore, CA-B chưa có. Giải thích vì sao A hoạt động nhưng B lỗi PKIX và cách sửa mà **không** vô tình loại bỏ CA-A.
3. B có cert SAN `ldap-b.partner.example` nhưng referral dùng `ldap-partner.example`. Có nên đổi truststore không? Đề xuất cách sửa hostname hợp lệ.
4. Một referral bất ngờ dùng `ldap://internal-host:389`. Trình bày rủi ro khi auto-follow với simple bind credentials và cơ chế từ chối an toàn.
5. So sánh `Context.REFERRAL` = `ignore`, `follow`, `throw`. Vì sao `ignorePartialResultException(true)` có thể làm sai kết quả truy vấn nghiệp vụ?
6. Viết bổ sung policy kiểm tra DN, scope, số hop và port; chứng minh qua unit test rằng URL ngoài phạm vi không được kết nối.
7. Thiết kế integration test hai server với CA khác nhau: happy path, thiếu CA-B, SAN mismatch, referral plaintext và credential A không dùng được ở B.
8. Ứng dụng `findBySurname` trả 30 người từ A nhưng bỏ qua continuation reference sang B. Giải thích vì sao kết quả có thể thiếu và cách thông báo tính đầy đủ.
9. Đề xuất cách quản lý service account riêng cho A/B trong kiến trúc có trust boundary; liên hệ DN, ACL và Spring `LdapTemplate`.
10. Diễn giải khác biệt giữa hostname của referral URL, DN trong referral URL, `spring.ldap.base` và Subject Alternative Name trong TLS certificate.

### Checklist

- [ ] Biết phân biệt referral và continuation reference với failover URL.
- [ ] Xác định được referral target **hostname, port, scheme và DN**.
- [ ] Không suy diễn TLS của server A bảo vệ kết nối tới B.
- [ ] Hiểu truststore và CA chain của cả A lẫn B.
- [ ] Xác minh SAN/hostname trên máy chủ được giới thiệu.
- [ ] Từ chối referral plaintext khi không có quy trình StartTLS bắt buộc.
- [ ] Có allowlist host/port/scheme, giới hạn hop/loop và policy credential.
- [ ] Phân biệt lỗi TLS với lỗi Bind/ACL, DNS, base DN và referral policy.
- [ ] Không tắt certificate hoặc hostname verification để “fix nhanh”.
- [ ] Không che `PartialResultException` khi nghiệp vụ đòi dữ liệu đầy đủ.
- [ ] Integration test trên directory lab có cả trường hợp thành công và thất bại.
- [ ] Secret/truststore được quản lý an toàn và không bị lộ qua log.

## 17. Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Referral result, SearchResultReference, yêu cầu tránh vòng lặp và cảnh báo referral độc hại.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): StartTLS, kiểm tra danh tính server và bảo vệ credentials.
- [RFC 4516 — LDAP URLs](https://www.rfc-editor.org/rfc/rfc4516): cấu trúc LDAP/LDAPS URL, DN, scope, filter và extensions.
- [RFC 3296 — Named Subordinate References in LDAP](https://www.rfc-editor.org/rfc/rfc3296): referral object và Manage Referral control.
- [Oracle — Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): `Context.REFERRAL`, `ignore/follow/throw` và `PartialResultException`.
- [Oracle — Manually Following Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/throw.html): `ReferralException`, `getReferralInfo()` và nguy cơ dùng lại authentication environment.
- [Oracle — SSL and Custom Sockets](https://docs.oracle.com/javase/jndi/tutorial/ldap/security/ssl.html): JNDI LDAPS, JSSE, truststore và socket TLS.
- [Oracle — The Start TLS Extension](https://docs.oracle.com/javase/jndi/tutorial/ldap/ext/starttls.html): `StartTlsResponse` và hostname verification.
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, `referral`, LDAP URLs và xử lý `PartialResultException`.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): `setReferral`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): phạm vi repository/ODM và `LdapTemplate`.
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): truststore, PKIX và kết nối TLS Java.
