# Theo dõi lỗi TLS, referral và chuyển máy chủ

Một ứng dụng Spring Boot đang đọc danh bạ bằng Spring Data LDAP có thể hoạt động bình thường trên máy phát triển, nhưng lên môi trường staging lại gặp `SSLHandshakeException`. Một ngày khác, truy vấn tìm nhân viên ở OU con chỉ trả một phần kết quả vì directory gửi **referral** sang máy chủ khác. Khi domain controller chính mất kết nối, ứng dụng chuyển sang endpoint dự phòng nhưng cookie phân trang cũ không còn dùng được. Nếu log chỉ ghi “LDAP search failed”, đội vận hành sẽ rất khó xác định vấn đề nằm ở chứng chỉ, referral, quyền truy cập, replica hay chính sách retry.

Trong chương **Quan sát** của module **SPRING_DATA_LDAP**, bài này hướng dẫn theo dõi và chẩn đoán ba nhóm sự cố liên quan mật thiết đến kết nối LDAP: **TLS**, **referral** và **chuyển máy chủ/failover**. Spring Data LDAP ánh xạ entry phân cấp theo DN, `objectClass` và schema; `LdapTemplate`/repository thực hiện các thao tác trên `ContextSource`. Để vận hành tin cậy, ta cần quan sát cả quá trình bind, search, referral, paging, lỗi server, thời gian phản hồi và kết quả cuối cùng.

**Điểm cần phân biệt:** referral là chỉ dẫn chuyển một phần namespace sang một naming context/server khác; failover là chuyển sang endpoint thay thế để tiếp tục phục vụ cùng dịch vụ directory. Hai việc này có thể cùng xuất hiện trong một truy vấn nhưng có ngữ nghĩa và rủi ro khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi TLS handshake, lỗi bind, lỗi LDAP search và lỗi referral.
2. Kiểm tra certificate chain, hostname/SAN, thời hạn chứng chỉ và truststore JVM.
3. Hiểu ba chính sách referral JNDI: `follow`, `ignore` và `throw`.
4. Thiết kế chính sách referral an toàn, tránh tự động gửi credential tới máy chủ không được tin cậy.
5. Phân biệt referral với failover và hiểu giới hạn của nhiều LDAP URL trong `ContextSource`/JNDI.
6. Thiết kế retry có giới hạn cho read-only search, xử lý cookie paging khi đổi connection/server và tránh retry mù quáng với thao tác ghi.
7. Ghi metrics/log/trace có ích mà không làm lộ password, DN nhạy cảm, filter chứa PII hoặc cookie.
8. Xây health check và ma trận kiểm thử cho TLS, referral, replica và failover.

## 2. Sơ đồ kết nối và các điểm cần quan sát

Một request đi qua nhiều thành phần trước khi trả kết quả:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] --> B["Spring Security / authorization"]
    B --> C["LdapTemplate / Repository"]
    C --> D["ContextSource / JNDI"]
    D --> E["TLS handshake + hostname verification"]
    E --> F["LDAP bind"]
    F --> G["LDAP server / replica A"]
    G --> H{"Có referral?"}
    H -- "Không" --> I["Search result / response control"]
    H -- "Có" --> J["Referral target B"]
    J --> K["TLS + trust + credential policy"]
    K --> I
    G -- "Endpoint lỗi" --> L["Kết nối lại / failover policy"]
    L --> M["Replica hoặc endpoint dự phòng"]
    M --> E
    I --> N["Mapper + xử lý kết quả"]
    N --> O["Metrics, logs, trace, HTTP response"]
~~~

Những điểm quan sát cần tách riêng:

| Giai đoạn | Dấu hiệu thường gặp | Câu hỏi vận hành |
| --- | --- | --- |
| DNS/TCP | Không resolve host, connection refused, timeout. | Endpoint có truy cập được từ đúng pod/host không? |
| TLS handshake | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch. | JVM có tin certificate chain và tên máy chủ không? |
| LDAP bind | LDAP result code 49, invalid credentials. | Bind DN/secret/account state đúng không? |
| Authorization/ACL | LDAP code 50 hoặc entry/attribute không xuất hiện. | Service account có quyền search/read trên vùng cần thiết không? |
| Search | `timeLimitExceeded`, `sizeLimitExceeded`, `adminLimitExceeded`. | Filter/base/scope và policy server có phù hợp không? |
| Referral | `ReferralException`, `PartialResultException` hoặc kết quả thiếu. | Referral target nào được yêu cầu và có được phép theo không? |
| Failover | Primary lỗi, endpoint khác được thử. | Replica thay thế có cùng naming context/schema/ACL không? |
| Paging | Cookie bị từ chối sau khi kết nối đổi. | Chuỗi paging có bị đổi context/server giữa các trang không? |
| Mapping/downstream | Lỗi mapper, database timeout. | LDAP đã trả đủ dữ liệu hay lỗi xảy ra sau search? |

Không gom tất cả trường hợp vào một trạng thái `LDAP_UNAVAILABLE`. Phân loại đúng giúp biết cần sửa truststore, credential, ACL, referral topology, query hay code retry.

## 3. TLS với LDAP: xác minh danh tính máy chủ trước khi bind

LDAP có thể dùng TLS theo hai cách phổ biến:

| Cách kết nối | Mô tả | Endpoint thường gặp |
| --- | --- | --- |
| **LDAPS** | TLS được thiết lập ngay khi mở socket LDAP. | `ldaps://ldap.example.org:636`. |
| **StartTLS** | Kết nối LDAP được nâng cấp qua LDAP StartTLS extended operation trước khi trao đổi dữ liệu nhạy cảm. | `ldap://ldap.example.org:389` rồi thực hiện StartTLS. |

Khi dùng LDAPS, JVM cần xác minh certificate chain và hostname của endpoint. Khi dùng StartTLS, client cần thực hiện nâng cấp thành công **trước khi gửi bind credential**; nếu policy yêu cầu TLS, không được tiếp tục bind plaintext khi StartTLS thất bại.

### 3.1. Certificate chain và truststore

Giả sử endpoint:

~~~text
ldaps://ldap01.corp.example:636
Certificate:
  Subject CN = ldap01.corp.example
  SAN DNS = ldap01.corp.example
  Issuer = Corp Directory Issuing CA
~~~

JVM phải xây dựng được chuỗi tin cậy từ certificate máy chủ tới CA tin cậy. Nếu CA nội bộ không có trong truststore của JVM, kết nối có thể lỗi dù trình duyệt trên máy cá nhân vẫn truy cập được.

Các bước kiểm tra:

1. Xác định hostname ứng dụng thực sự kết nối, không chỉ hostname người vận hành thường dùng.
2. Kiểm tra certificate còn hạn, chain đầy đủ và SAN có hostname tương ứng.
3. Kiểm tra CA gốc/intermediate CA trong truststore mà **đúng JVM của ứng dụng** đang sử dụng.
4. Kiểm tra TLS protocol/cipher mà JVM và server cùng hỗ trợ.
5. Xác minh certificate trên mọi endpoint failover và referral target được phép truy cập.
6. Kiểm thử quy trình gia hạn/rotation certificate trước ngày hết hạn.

Ví dụ kiểm tra LDAPS từ terminal có OpenSSL:

~~~bash
openssl s_client \
  -connect ldap01.corp.example:636 \
  -servername ldap01.corp.example \
  -showcerts \
  -verify_return_error
~~~

Nếu kiểm tra StartTLS LDAP:

~~~bash
openssl s_client \
  -connect ldap01.corp.example:389 \
  -starttls ldap \
  -servername ldap01.corp.example \
  -showcerts \
  -verify_return_error
~~~

Các lệnh trên giúp quan sát handshake/certificate từ môi trường chạy lệnh; kết quả vẫn có thể khác JVM do truststore, DNS, proxy, container và cấu hình Java khác nhau.

### 3.2. Cấu hình truststore JVM

Nếu tổ chức dùng CA nội bộ, import CA đã được xác minh vào truststore được quản trị an toàn. Ví dụ JVM options:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/directory-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Password truststore (nếu có) nên được cung cấp qua cơ chế quản lý secret của nền tảng triển khai, không commit vào repository hoặc in trong log. Đường dẫn trong ví dụ chỉ minh họa; container/VM cần mount đúng file và quyền đọc tối thiểu.

**Không tắt xác minh hostname hoặc cài TrustManager chấp nhận mọi certificate** để làm cho kết nối “chạy được”. Điều đó cho phép client kết nối tới máy chủ giả mạo và có thể làm lộ bind credential/dữ liệu directory.

### 3.3. Lỗi TLS thường gặp

| Thông báo / triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `PKIX path building failed` | JVM không xây dựng được certificate chain tin cậy. | Kiểm tra CA/intermediate và truststore đúng process. |
| `No subject alternative DNS name matching ...` | Hostname URL không có trong SAN certificate. | Dùng đúng DNS name trong SAN hoặc cấp certificate đúng hostname. |
| `certificate expired` / validity error | Certificate hết hạn hoặc thời gian hệ thống sai. | Kiểm tra thời gian hệ thống, validity và quy trình rotation. |
| `handshake_failure` | Protocol/cipher/client certificate/policy không tương thích. | Kiểm tra TLS version/cipher và cấu hình server. |
| LDAPS timeout trước bind | Firewall, routing, DNS, endpoint hoặc TLS handshake bị treo. | Đo TCP/TLS từ đúng runtime, xem timeout và network policy. |
| OpenSSL thành công nhưng Java thất bại | Truststore/hostname/protocol JVM khác. | Chạy chẩn đoán từ đúng container/JVM và đọc cause chain. |
| Primary TLS tốt, referral TLS lỗi | Referral target dùng CA/certificate/hostname khác. | Kiểm tra từng referral hostname và chain. |

TLS lỗi xảy ra trước hoặc trong quá trình tạo context/bind; **đừng xử lý nó như lỗi LDAP filter**. Ngược lại, LDAP code 49 thường là lỗi xác thực sau khi kết nối TLS đã được thiết lập; sửa truststore sẽ không sửa được bind DN/password sai.

## 4. Cấu hình kết nối Spring Boot và quan sát TLS

Dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap01.corp.example:636
      - ldaps://ldap02.corp.example:636
    base: dc=corp,dc=example
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      java.naming.referral: throw
      com.sun.jndi.ldap.connect.timeout: "3000"
      com.sun.jndi.ldap.read.timeout: "5000"

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Các lưu ý:

- Danh sách `spring.ldap.urls` là ví dụ cấu hình nhiều endpoint. Cách JNDI provider chọn URL và hành vi khi lỗi phụ thuộc provider/version; **không giả định** đây là failover trong suốt ở giữa một search đang chạy.
- `java.naming.referral: throw` yêu cầu JNDI báo referral để ứng dụng/provider xử lý theo chính sách đã chọn; đây là giá trị cần kiểm thử với server thực tế.
- Connect/read timeout là thuộc tính JNDI LDAP provider của JVM. Chúng không thay thế search time limit, HTTP deadline hay timeout của database downstream.
- `management.endpoints.web.exposure` cần giới hạn qua Spring Security/network policy; không công khai mọi endpoint Actuator cho Internet.
- TLS truststore được cấu hình ở JVM/container theo chính sách nền tảng, không phải bằng cách tắt certificate validation trong `application.yml`.

Nếu tạo `LdapContextSource` bằng Java thay vì auto-configuration, phải đảm bảo danh sách URL, base, bind DN, secret và base environment properties được áp dụng trước khi khởi tạo context. Không tạo một context không mã hóa rồi chỉ thay endpoint sang LDAPS ở một lần search tiếp theo.

## 5. Referral là gì và khác failover như thế nào?

Một directory có thể phân chia namespace trên nhiều naming context/server. Khi client tìm dưới một nhánh mà server hiện tại không phục vụ trực tiếp, server có thể trả **referral** chỉ tới nơi có dữ liệu đó.

Ví dụ:

~~~text
dc=corp,dc=example
├── ou=employees
│   └── ldap01.corp.example
└── ou=partners
    └── ldap-partners.corp.example

Client tìm subtree từ dc=corp,dc=example
ldap01 trả referral tới ou=partners trên ldap-partners
~~~

**Failover** lại là trường hợp endpoint hiện tại không thể phục vụ, ứng dụng chọn một endpoint thay thế cho cùng dịch vụ/dữ liệu logic:

~~~text
Primary ldap01.corp.example  -- lỗi kết nối
             |
             v
Secondary ldap02.corp.example -- phục vụ cùng directory/replica
~~~

| Thuộc tính | Referral | Failover |
| --- | --- | --- |
| Mục đích | Điều hướng client tới naming context/partition khác. | Duy trì sẵn sàng khi endpoint hiện tại lỗi. |
| Nguyên nhân thường gặp | Dữ liệu nằm ở server/partition khác. | Server mất mạng, dừng dịch vụ, lỗi kết nối hoặc không khỏe. |
| Đích đến | Có thể là một naming context khác. | Thường là endpoint/replica thay thế của cùng dịch vụ logic. |
| Credential | Cần quyết định có được gửi tới referral target không và target có được tin cậy không. | Dùng credential cho endpoint dự phòng theo cùng chính sách identity. |
| TLS | Phải xác minh certificate/hostname của referral host. | Phải xác minh certificate/hostname của endpoint dự phòng. |
| Kết quả dữ liệu | Có thể là một phần namespace khác. | Có thể trễ replication hoặc khác trạng thái nếu replica chưa đồng bộ. |
| Paging cookie | Có thể không dùng chung giữa naming context/server. | Không mặc định dùng được cookie của connection/server đã mất. |

Một request có thể gặp referral rồi referral target lại lỗi; khi đó cần chẩn đoán cả referral policy lẫn failover. **Không gọi mọi lần đổi hostname là referral**, và cũng không gọi referral là “đổi server dự phòng”.

## 6. Chính sách referral trong JNDI

JNDI LDAP provider có thuộc tính `java.naming.referral` với các lựa chọn phổ biến:

| Giá trị | Hành vi khái quát | Khi nào cân nhắc? |
| --- | --- | --- |
| `follow` | Provider tự động theo referral. | Chỉ khi referral targets được quản trị/tin cậy, TLS/credential policy rõ ràng và hành vi đã được kiểm thử. |
| `ignore` | Provider không theo referral. | Khi ứng dụng chỉ được tìm trong naming context hiện tại; phải hiểu kết quả có thể thiếu một phần dữ liệu. |
| `throw` | Provider ném referral exception để caller có thể quyết định. | Khi cần allowlist target, kiểm soát credential và ghi nhận referral tường minh. |

Trong ví dụ ở mục 4 dùng `throw` để ưu tiên quan sát và quyết định rõ. Hành vi cụ thể của provider, Spring LDAP và cách xử lý partial result cần được kiểm chứng theo phiên bản.

### 6.1. Vì sao `follow` có rủi ro bảo mật?

Referral URL có thể chỉ tới hostname/port khác. Nếu provider tự động theo referral, client có thể kết nối sang máy chủ ngoài dự kiến. Những câu hỏi cần trả lời trước khi bật `follow`:

1. Referral target có thuộc allowlist DNS/domain/port của tổ chức không?
2. Certificate chain và hostname của target có được xác minh không?
3. Có nguy cơ referral trỏ từ LDAPS sang LDAP plaintext không?
4. Provider có gửi lại bind identity/credential tới target không? Hành vi có thể phụ thuộc provider và cấu hình; phải kiểm tra tài liệu/trace test.
5. Target có cùng chính sách ACL, schema, logging và dữ liệu nhạy cảm không?
6. Có giới hạn referral loop/depth và timeout không?
7. Nếu target yêu cầu credential khác, ứng dụng có quy trình xác thực được phê duyệt không?

**Không chuyển tiếp bind password tới một referral host chỉ vì server đầu tiên trả URL đó.** Referral cần được xem như dữ liệu đầu vào từ directory topology; chỉ follow các target được xác thực và cho phép.

### 6.2. Khi chọn `throw`, ứng dụng cần làm gì?

Khi nhận referral exception:

- Ghi nhận operation, endpoint nguồn, referral count và hostname đích đã được **làm sạch/ẩn danh phù hợp**.
- Kiểm tra referral URL có scheme/host/port trong allowlist.
- Kiểm tra TLS target, naming context và chính sách credential.
- Chỉ tiếp tục nếu ứng dụng có cơ chế rõ ràng để tạo context mới an toàn.
- Giới hạn số referral và phát hiện vòng lặp.
- Nếu không thể theo referral, trả lỗi/partial state phù hợp; không âm thầm coi kết quả hiện tại là đầy đủ.

Không nhất thiết phải tự triển khai referral client cho mọi ứng dụng. Nếu nghiệp vụ chỉ dùng một OU trong naming context cục bộ, có thể chọn không theo referral và thiết kế base/search phù hợp, miễn là API công bố đúng phạm vi dữ liệu.

### 6.3. Referral và partial result

Một search có thể trả entry trước khi provider phát hiện referral hoặc partial result. Spring LDAP/JNDI có thể biểu diễn qua exception như `ReferralException` hoặc `PartialResultException` tùy tình huống/provider.

Phân biệt:

- **COMPLETE:** mọi nhánh cần thiết được truy vấn thành công theo chính sách.
- **PARTIAL:** có entry nhưng một hoặc nhiều referral/partition chưa được xử lý.
- **FAILED:** không thể thực hiện truy vấn hoặc không thể tin cậy kết quả.

Nếu bật cấu hình bỏ qua partial exception, phải hiểu chính xác nhánh nào bị bỏ qua. **Không dùng danh sách partial để đồng bộ xóa user** hoặc hiển thị “đã đọc toàn bộ nhân viên”.

## 7. Theo dõi failover và nhiều endpoint

### 7.1. Nhiều URL không phải cam kết failover giữa mọi thao tác

Spring LDAP cho phép cấu hình nhiều URL trong context source. JNDI LDAP provider có thể dùng danh sách URL trong quá trình tạo context, nhưng chi tiết chọn URL/thử lại phụ thuộc implementation và cấu hình. Một danh sách hai endpoint **không tự bảo đảm**:

- Tự động phát hiện mọi kiểu lỗi giữa một search đang chạy.
- Chuyển request đang thực hiện sang endpoint khác mà không mất kết quả.
- Tiếp tục cookie paging cũ trên endpoint mới.
- Đảm bảo replica thứ hai đã nhận mọi thay đổi của primary.
- Đảm bảo referral và failover cùng sử dụng một credential/ACL.

### 7.2. Những điều kiện để endpoint dự phòng thay thế được

Trước khi cấu hình failover, xác minh:

| Điều kiện | Câu hỏi cần trả lời |
| --- | --- |
| Naming context | Cùng base DN và các partition cần truy vấn có sẵn không? |
| Schema | Attribute, objectClass, matching rule và operational attribute có tương thích không? |
| ACL | Bind account có cùng quyền cần thiết trên endpoint dự phòng không? |
| TLS | Certificate có hợp lệ với hostname endpoint dự phòng không? |
| Referral topology | Endpoint dự phòng có referral khác không? Target có được allowlist? |
| Replication | Độ trễ replica bao nhiêu? Có read-after-write guarantee không? |
| Search policy | Size/time/admin limits có giống nhau không? |
| Paging | Cookie chỉ dùng trong cùng connection; scan mới phải tạo cookie mới. |
| Write semantics | Có thể ghi ở secondary không, hay secondary chỉ read-only? |

Một endpoint “TCP mở được” chưa chắc là replica thay thế được về nghiệp vụ.

### 7.3. Chính sách failover ở tầng ứng dụng

Một chiến lược dễ quan sát:

1. Chọn endpoint từ danh sách được cấu hình.
2. Thực hiện connect/TLS/bind và một kiểm tra nhẹ phù hợp.
3. Khi có lỗi kết nối được phân loại là tạm thời, ghi nhận attempt và chọn endpoint khác theo retry budget.
4. Với read-only search, bắt đầu **một chuỗi search mới** trên endpoint mới; không tái sử dụng cookie paging từ endpoint cũ.
5. So sánh kết quả theo stable ID nếu có thể; ghi nhận endpoint/replica đã phục vụ.
6. Khi hết retry budget, mở circuit breaker hoặc trả lỗi phụ thuộc, không tiếp tục dồn request vào endpoint đang lỗi.

Không failover với mọi exception. Ví dụ:

- `invalidCredentials`: thử endpoint khác thường không sửa được secret sai; cần báo lỗi cấu hình/authentication.
- `insufficientAccessRights`: endpoint khác có thể che giấu ACL không đồng nhất; cần điều tra policy.
- `SSLHandshakeException`: chuyển endpoint có thể hữu ích nếu certificate riêng endpoint lỗi, nhưng không được bỏ xác minh TLS.
- `timeLimitExceeded`: có thể do query nặng hoặc server quá tải; retry ngay nhiều lần có thể làm tình hình tệ hơn.
- `CommunicationException`/connection reset: có thể là lỗi hạ tầng tạm thời, phù hợp retry có giới hạn nếu operation an toàn.

### 7.4. Read retry khác write retry

| Operation | Khi kết nối mất giữa chừng | Hành động |
| --- | --- | --- |
| Search/lookup | Không biết client đã nhận hết response hay chưa. | Có thể retry giới hạn; với paging, khởi tạo chuỗi mới và deduplicate/reconcile. |
| Add/bind entry | Server có thể đã tạo entry nhưng response bị mất. | Lookup theo DN/stable ID và đối soát trước khi thử lại. |
| Modify attributes | Server có thể đã sửa một phần/toàn bộ. | Đọc lại trạng thái và so sánh giá trị mong muốn; retry có điều kiện. |
| Delete | Entry có thể đã bị xóa dù client timeout. | Lookup kiểm tra trạng thái; phân biệt không tồn tại với không đủ quyền. |
| Rename/move | DN cũ có thể đã đổi sang DN mới. | Tra cứu cả vị trí dự kiến và stable ID; không gửi rename lại mù quáng. |

**Timeout không chứng minh thao tác ghi thất bại.** Nếu server đã commit mà response không tới client, retry có thể gây duplicate hoặc thay đổi ngoài ý muốn. LDAP và database cũng không có transaction nguyên tử chung chỉ vì service dùng `@Transactional`.

## 8. Paging cookie khi referral hoặc failover xảy ra

Đây là điểm dễ gây lỗi dữ liệu khi quét directory lớn:

~~~text
Trang 1: ldap01 -> 250 entry + cookie A
Trang 2: ldap01 -> connection reset
Failover: ứng dụng mở context tới ldap02
Trang 3: gửi cookie A tới ldap02  (KHÔNG được giả định hợp lệ)
~~~

Cookie RFC 2696 là dữ liệu opaque do server cấp cho một chuỗi search. Nó không phải offset toàn cục. Khi connection bị mất, referral chuyển naming context hoặc ứng dụng failover sang backend khác, hãy xem chuỗi paging cũ là **đã bị gián đoạn** trừ khi provider/server có bảo đảm rõ ràng khác.

Quy trình an toàn:

1. Đánh dấu scan cũ `FAILED/PARTIAL` và lưu thống kê đã xử lý, không đánh dấu full scan.
2. Tạo context mới tới endpoint hợp lệ, thực hiện TLS/bind và kiểm tra phạm vi.
3. Bắt đầu chuỗi paging mới với cookie rỗng.
4. Dùng stable ID và upsert idempotent để xử lý lại entry đã đọc.
5. Chỉ đánh dấu scan mới hoàn chỉnh khi hết cookie, không có lỗi referral/partial/timeout và mọi trang đã xử lý.
6. Không xóa entry nội bộ chỉ vì nó không xuất hiện trong scan cũ bị ngắt.

**Paged search không bảo đảm snapshot nhất quán.** Nếu replica có độ trễ, scan lại từ đầu trên endpoint khác có thể thấy trạng thái khác. Với yêu cầu đồng bộ quan trọng, cần reconciliation/change tracking và quy tắc chọn nguồn có thẩm quyền.

## 9. Thiết kế quan sát: metrics, logs và traces

Một dashboard chỉ có `ldap_requests_total` không đủ để chẩn đoán. Nên phân loại theo operation và outcome có cardinality thấp.

### 9.1. Metrics đề xuất

| Metric | Loại | Nhãn an toàn gợi ý | Mục đích |
| --- | --- | --- | --- |
| `ldap.operation.duration` | Timer | `operation`, `endpoint_alias`, `outcome`. | Latency search/lookup/bind/modify. |
| `ldap.operation.failures` | Counter | `operation`, `error_category`. | Theo dõi lỗi theo loại. |
| `ldap.tls.handshake.failures` | Counter | `endpoint_alias`, `error_category`. | Phát hiện certificate/protocol issue. |
| `ldap.referral.count` | Counter | `source_alias`, `target_alias` (allowlist). | Referral xảy ra bao nhiêu lần. |
| `ldap.referral.partial` | Counter | `operation`, `outcome`. | Theo dõi partial results do referral. |
| `ldap.failover.attempts` | Counter | `from_alias`, `to_alias`, `outcome`. | Số lần chuyển endpoint. |
| `ldap.paging.pages` | Counter | `endpoint_alias`, `outcome`. | Số trang được đọc trong scan. |
| `ldap.paging.entries` | Counter | `endpoint_alias`. | Số entry đã xử lý, không phải exact total. |
| `ldap.paging.incomplete` | Counter | `reason`. | Scan bị ngắt, timeout, referral thiếu. |
| `ldap.connection.active` | Gauge | `endpoint_alias`. | Số context/connection đang hoạt động nếu đo được. |
| `ldap.replica.lag` | Gauge | `replica_alias`. | Độ trễ replication nếu có nguồn đo đáng tin cậy. |

Không dùng DN, username, email, filter đầy đủ, cookie hoặc bind password làm metric label. Những giá trị đó tạo cardinality rất cao và có thể tiết lộ dữ liệu cá nhân/cấu trúc nội bộ.

### 9.2. Ví dụ instrument service bằng Micrometer

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
public class ObservedDirectoryReader {

    private final DirectoryReader delegate;
    private final MeterRegistry registry;

    public ObservedDirectoryReader(
            DirectoryReader delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public DirectoryResult search(String uid) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return delegate.search(uid);
        } catch (DataAccessException ex) {
            outcome = classify(ex);
            throw ex;
        } finally {
            sample.stop(Timer.builder("ldap.operation.duration")
                    .description("Duration of an LDAP search operation")
                    .tag("operation", "search")
                    .tag("endpoint_alias", "directory-primary")
                    .tag("outcome", outcome)
                    .register(registry));
        }
    }

    private static String classify(DataAccessException ex) {
        // Phân loại cause chain trong code thực; chỉ trả enum/cardinality thấp.
        String type = ex.getMostSpecificCause().getClass().getSimpleName();
        if (type.contains("Communication")) return "communication_error";
        if (type.contains("Authentication")) return "authentication_error";
        if (type.contains("PartialResult")) return "partial_result";
        if (type.contains("Referral")) return "referral_error";
        return "directory_error";
    }
}
~~~

`DirectoryReader` và `DirectoryResult` là các interface/DTO thuộc ứng dụng, cần được định nghĩa theo service thực tế. Ví dụ chỉ minh họa cách đo duration và gắn nhãn outcome. Không nên phân loại lỗi chỉ bằng tên class trong production nếu exception translation thay đổi; hãy xem root cause JNDI/Spring LDAP và chuẩn hóa thành enum rõ ràng.

Nếu cần đo TLS handshake riêng, nên instrument tại tầng tạo kết nối/transport hoặc quan sát log JSSE/metrics của nền tảng. Timer quanh `LdapTemplate.search` chỉ đo tổng thời gian operation, không tách được handshake nếu connection đã được tái sử dụng.

### 9.3. Structured logs có ích

Một log sự cố có thể chứa:

~~~json
{
  "event": "ldap_operation_failed",
  "operation": "search",
  "endpoint_alias": "directory-primary",
  "error_category": "tls_certificate_validation",
  "exception_type": "SSLHandshakeException",
  "elapsed_ms": 184,
  "correlation_id": "req-7f3a",
  "retryable": false
}
~~~

Các trường trong ví dụ là dữ liệu giả. Không log:

- Password, bind secret hoặc token xác thực.
- Raw paging cookie hoặc application token có thể tái sử dụng.
- Toàn bộ DN, filter chứa tên/email hoặc kết quả entry.
- Certificate private key hoặc nội dung truststore.
- URL referral chưa được làm sạch nếu URL có thông tin xác thực hoặc query nhạy cảm.

Log nên có endpoint **alias** thay vì lặp hostname nội bộ khắp nơi; hostname có thể được ghi trong log bảo vệ quyền truy cập khi cần điều tra. Nếu log exception, đảm bảo message/cause không chứa credential hoặc dữ liệu directory nhạy cảm.

### 9.4. Trace và correlation

Với distributed tracing, một trace cho request có thể gồm:

~~~text
HTTP GET /directory/search
  └── authorization.check
      └── ldap.search
          ├── ldap.connect-or-borrow
          ├── tls.handshake (nếu tạo kết nối mới)
          ├── ldap.bind (nếu bind mới)
          ├── ldap.referral.follow (nếu policy cho phép)
          └── ldap.map-results
~~~

Không phải lúc nào cũng tạo được span riêng cho mọi bước, đặc biệt nếu JNDI provider thực hiện referral/failover nội bộ. Khi không quan sát được bước handshake/follow bên trong, ghi rõ giới hạn instrumentation; không suy diễn rằng một span `ldap.search` thành công chứng minh không có referral.

## 10. Health check và cảnh báo vận hành

### 10.1. Readiness khác liveness

| Check | Câu hỏi | Thiết kế phù hợp |
| --- | --- | --- |
| **Liveness** | Process có còn hoạt động và có thể tiếp tục chạy không? | Thường không phụ thuộc một LDAP search đắt tiền; tránh restart liên tục chỉ vì directory tạm lỗi. |
| **Readiness** | Instance có thể phục vụ chức năng cần LDAP không? | Có thể thử bind/search nhẹ trên base/entry test phù hợp với ACL. |
| **Endpoint health** | LDAP endpoint nào đang kết nối được? | Probe ngắn, timeout rõ, phân loại TLS/bind/search. |
| **Referral health** | Những referral target cần thiết có hoạt động không? | Kiểm tra theo allowlist/partition cần thiết; không quét mọi referral liên tục. |
| **Replication health** | Replica có dữ liệu đủ mới không? | Dùng chỉ số replication/provider nếu có; không chỉ dựa vào TCP connect. |

Nếu LDAP là dependency bắt buộc cho mọi request, readiness có thể đánh dấu instance không sẵn sàng khi tất cả endpoint hợp lệ đều lỗi. Nếu chỉ một chức năng phụ thuộc LDAP, cần đánh giá theo chức năng để không làm toàn ứng dụng ngừng phục vụ.

### 10.2. Health check nhẹ

Một probe phù hợp thường:

- Kết nối tới endpoint alias cần kiểm tra với TLS xác minh đầy đủ.
- Bind bằng tài khoản dịch vụ có quyền phù hợp.
- Thực hiện lookup/base-object search rất nhỏ, không quét subtree lớn.
- Dùng timeout ngắn và không theo referral ngoài allowlist.
- Ghi metric success/failure và error category.
- Không log password, toàn bộ DN người dùng hoặc nội dung entry.

Không dùng `findAll()` hoặc search toàn OU làm liveness probe. Probe nặng tự tạo tải và có thể làm hệ thống càng mất ổn định khi LDAP đang chậm.

### 10.3. Cảnh báo nên có

| Cảnh báo | Điều kiện minh họa | Hành động |
| --- | --- | --- |
| TLS certificate sắp hết hạn | Certificate còn dưới ngưỡng vận hành đã định. | Lên lịch rotation và kiểm thử mọi endpoint/referral. |
| TLS handshake failures tăng | Tăng bất thường trong cửa sổ ngắn. | Kiểm tra CA, SAN, protocol, endpoint và rollout truststore. |
| LDAP bind failures | Tăng LDAP code 49 hoặc authentication error. | Kiểm tra secret rotation/account lockout. |
| Referral partial results | Có scan/search kết thúc partial. | Kiểm tra referral target, policy và ACL. |
| Failover liên tục | Nhiều lần chuyển endpoint trong thời gian ngắn. | Điều tra health/replication/network; tránh flapping. |
| Paging incomplete | Scan bị timeout/mất cookie/partial. | Không chạy reconciliation xóa dữ liệu; khởi động lại an toàn. |
| Replica lag cao | Vượt ngưỡng freshness nghiệp vụ. | Điều hướng read sang nguồn đủ mới hoặc tạm ngừng tác vụ nhạy cảm. |
| Connection pool cạn | Active/borrowed context cao và borrow wait tăng. | Giảm concurrency, kiểm tra đóng context/referral loop. |

Ngưỡng cảnh báo phải lấy từ SLO và vận hành thực tế, không sao chép nguyên các số ví dụ trong bài.

## 11. Quy trình chẩn đoán theo triệu chứng

### 11.1. `SSLHandshakeException` chỉ xảy ra trên pod mới

1. Xác định pod/JVM, image và truststore thực tế.
2. So sánh CA bundle/truststore giữa pod mới và pod cũ.
3. Xác minh DNS endpoint và hostname trong SAN.
4. Kiểm tra certificate chain và ngày giờ hệ thống.
5. Chạy OpenSSL từ đúng network namespace nếu có thể.
6. Kiểm tra JVM TLS protocol/cipher policy.
7. Sau khi cập nhật truststore, restart/refresh theo cách quản lý SSL context của ứng dụng; không giả định mọi context đã tạo tự nhận CA mới.

### 11.2. Search trả partial khi tìm từ root DN

1. Kiểm tra root base và scope có đi qua partition/OU được referral không.
2. Đặt referral policy rõ ràng; với `throw`, ghi nhận referral exception/target.
3. Xác minh target có trong allowlist, TLS và credential policy hợp lệ.
4. Kiểm tra ACL trên target và base DN được referral trỏ tới.
5. Xác minh Spring LDAP có đang bỏ qua `PartialResultException` hay không.
6. Nếu chỉ cần một OU cục bộ, giới hạn base thay vì quét root.
7. Đánh dấu scan PARTIAL nếu chưa đọc hết những nhánh cần thiết.

### 11.3. Failover xong, trang tiếp theo lỗi

1. Xác định trang nào đã xử lý và endpoint phục vụ trang đó.
2. Xác nhận context/connection cũ đã mất; không gửi cookie cũ sang endpoint mới.
3. Kiểm tra replica thay thế có cùng base/schema/ACL.
4. Đánh dấu chuỗi scan cũ FAILED/PARTIAL.
5. Bắt đầu paging sequence mới từ cookie rỗng.
6. Dedupe/upsert theo stable ID và reconciliation idempotent.
7. Chỉ công bố full scan khi chuỗi mới hoàn tất không lỗi.

### 11.4. Chuyển sang replica nhưng dữ liệu cũ

Đây có thể là **replication lag**, không phải lỗi failover logic. Xác định yêu cầu read-after-write của nghiệp vụ, đo độ trễ replica qua chỉ số có thẩm quyền và chọn endpoint phù hợp. Không mặc định mọi replica đều đồng bộ tức thì. Nếu thao tác vừa ghi xong cần đọc lại, có thể phải đọc từ nguồn authoritative hoặc dùng một cơ chế consistency được nhà cung cấp bảo đảm.

## 12. Mẫu kiểm thử tích hợp

Tạo một test profile với:

- Hai LDAP endpoint trong **môi trường test**: primary và secondary.
- CA/truststore test có chứng chỉ đúng hostname; một endpoint test riêng có certificate không tin cậy để kiểm tra thất bại.
- OU riêng, ví dụ `ou=observability-test`, với một số entry giả.
- Tài khoản reader giới hạn ACL trong OU test.
- Referral target test nằm trong allowlist; một referral target ngoài allowlist để xác nhận không follow.

### 12.1. Ma trận TLS

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Certificate hợp lệ, chain tin cậy, SAN khớp hostname. | TLS handshake thành công, sau đó bind/search theo ACL. |
| CA không có trong truststore. | Handshake fail; không fallback plaintext. |
| SAN không khớp URL hostname. | Hostname verification fail. |
| Certificate hết hạn. | Kết nối bị từ chối, metric TLS failure tăng. |
| Certificate mới được rotate. | Tất cả pod/endpoint tin chain mới trước khi certificate cũ hết hạn. |
| TLS protocol/cipher không tương thích. | Handshake fail được phân loại; không hạ xuống TLS yếu ngoài policy. |
| Primary cert đúng, secondary cert sai. | Failover không được coi là thành công; ghi endpoint gây lỗi. |

### 12.2. Ma trận referral

| Trường hợp | Policy/thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Referral target tin cậy, TLS đúng. | `follow` trên môi trường test. | Client theo referral theo đúng provider behavior; ghi metric target. |
| Referral target ngoài allowlist. | `throw` và kiểm tra host. | Không tự động gửi credential tới target. |
| Referral bị bỏ qua. | `ignore`. | Kết quả có thể partial; ứng dụng không báo full scan nếu cần partition đó. |
| Referral được ném cho caller. | `throw`. | Phân loại ReferralException và xử lý có kiểm soát. |
| Referral loop hoặc chain quá sâu. | Topology test có vòng lặp. | Giới hạn số lần/độ sâu, scan fail rõ ràng. |
| Referral target có CA khác. | Truststore thiếu CA target. | TLS failure được ghi nhận riêng với lỗi referral. |
| Target yêu cầu credential khác. | Referral test được kiểm soát. | Không chuyển tiếp credential tùy tiện; theo chính sách được phê duyệt. |

### 12.3. Ma trận failover và paging

| Trường hợp | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Primary hoạt động. | Search một entry test. | Dùng primary, metrics endpoint đúng. |
| Primary ngừng trước connect. | Kích hoạt read-only search. | Thử secondary theo retry/failover policy. |
| Primary mất giữa paged scan. | Ngắt kết nối sau trang 2. | Scan cũ PARTIAL; không tái sử dụng cookie trên secondary. |
| Secondary có replication lag. | Thêm entry ở primary rồi đọc secondary. | Phát hiện dữ liệu chưa mới; không tuyên bố consistency tức thì. |
| Cả hai endpoint lỗi. | Ngắt cả primary và secondary. | Retry budget kết thúc, circuit breaker/HTTP dependency error. |
| Sai credential. | Bind DN/secret test không hợp lệ. | Không retry vô hạn qua mọi endpoint; phân loại authentication. |
| ACL khác nhau. | Secondary thiếu quyền đọc attribute. | Không coi endpoint là thay thế tương đương; báo configuration/authorization issue. |
| Write response bị mất. | Ngắt mạng sau gửi Add/Modify test. | Đọc đối soát trạng thái trước retry. |
| Referral xảy ra trên secondary. | Secondary trả referral target. | Áp dụng cùng referral allowlist/TLS policy. |
| Lỗi mapper/downstream. | Consumer ném exception giữa scan. | Scan FAILED; không đánh dấu hoàn tất chỉ vì LDAP connection còn sống. |

### 12.4. Kiểm tra metrics/logs

Mỗi test cần xác minh:

- Có operation duration và outcome tương ứng.
- Lỗi TLS được phân loại riêng với bind/search/ACL.
- Referral/failover có counter và endpoint alias phù hợp.
- Partial scan tăng counter `ldap.paging.incomplete`.
- Không có password, raw cookie, DN/PII hoặc filter nhạy cảm trong log/metric labels.
- Correlation ID liên kết được request HTTP với log LDAP mà không cần log toàn bộ dữ liệu entry.

## 13. Checklist vận hành

Trước khi phát hành:

- [ ] Mọi endpoint LDAP sử dụng TLS theo policy và kiểm tra certificate/hostname.
- [ ] Truststore của từng runtime/pod có CA cần thiết; có lịch rotation certificate.
- [ ] Referral policy được cấu hình tường minh, không phụ thuộc mặc định không kiểm chứng.
- [ ] Referral targets được allowlist; không tự chuyển tiếp bind secret tới host tùy ý.
- [ ] Multi-URL/failover behavior đã được kiểm thử theo đúng JNDI provider/Spring LDAP version.
- [ ] Replica có cùng naming context/schema/ACL cần thiết; độ trễ replication được hiểu rõ.
- [ ] Paging không tiếp tục cookie cũ khi connection/server thay đổi.
- [ ] Retry chỉ áp dụng với lỗi phù hợp; write timeout có quy trình đối soát.
- [ ] Metrics/log/trace có đủ endpoint alias, operation, error category và latency.
- [ ] Không log credential, cookie hoặc dữ liệu danh bạ nhạy cảm.
- [ ] Readiness probe nhẹ, không quét subtree lớn hoặc tạo tải khi server đang lỗi.
- [ ] Partial/referral/timeout được phân biệt với scan COMPLETE.
- [ ] Job reconciliation không xóa dữ liệu dựa trên một scan chưa hoàn chỉnh.

## 14. Bài tập tình huống

Một ứng dụng Spring Boot đọc nhân viên từ hai domain controller:

~~~text
Primary:   ldaps://dc01.corp.example:636
Secondary: ldaps://dc02.corp.example:636
Base:      dc=corp,dc=example
Bind DN:   cn=app-reader,ou=services,dc=corp,dc=example
~~~

Ứng dụng quét danh bạ theo RFC 2696, page size 250. Root search đôi khi nhận referral tới `ldaps://partners.corp.example:636/ou=partners,dc=corp,dc=example`. Một buổi sáng, primary thay certificate; một pod mới lỗi `PKIX path building failed`. Sau đó primary bị restart giữa trang 3; app chuyển secondary và nhận lỗi invalid cookie. Một số nhân viên thuộc OU partners không xuất hiện trong bản đồng bộ.

**Yêu cầu:**

1. Vì sao pod mới có thể lỗi PKIX trong khi pod cũ vẫn kết nối được?
2. Liệt kê các bước xác minh certificate chain, SAN và truststore JVM.
3. Nên chọn `follow`, `ignore` hay `throw` cho referral? Nêu điều kiện để lựa chọn.
4. Nếu dùng `follow`, cần xác minh những gì trước khi credential được dùng ở `partners.corp.example`?
5. Phân biệt referral tới OU partners với failover từ dc01 sang dc02.
6. Có được gửi cookie trang 3 của dc01 sang dc02 không? Vì sao?
7. Khi scan bị ngắt sau trang 3, trạng thái job phải là gì và làm sao chạy lại an toàn?
8. Nếu secondary có replication lag, kết quả scan lại có thể khác thế nào?
9. Nếu app dùng `ignore` và không theo referral, tại sao không được đánh dấu danh bạ đầy đủ?
10. Nếu Modify/Add bị timeout, vì sao không retry mù quáng như một search?
11. Đề xuất ít nhất sáu metrics/log fields để xác định endpoint, TLS, referral và paging outcome mà không lộ PII.
12. Thiết kế một health check nhẹ để phân biệt app liveness, LDAP readiness và referral target health.

**Gợi ý lời giải:**

- Pod mới có thể thiếu CA/intermediate trong truststore, dùng image/JVM khác hoặc truy cập hostname khác không có trong SAN.
- Xác minh certificate chain, hostname, thời hạn, TLS protocol và truststore từ đúng pod.
- `throw` phù hợp khi muốn kiểm soát target/credential; `follow` chỉ khi mọi target đã được tin cậy và policy rõ; `ignore` chỉ khi chấp nhận phạm vi không bao gồm nhánh referral và báo partial phù hợp.
- Referral target cần allowlist, TLS/hostname hợp lệ, ACL/schema tương thích và credential policy được phê duyệt.
- Referral dẫn sang naming context khác; failover chọn endpoint thay thế của cùng dịch vụ/replica.
- Không giả định cookie portable; mất connection thì bắt đầu chuỗi mới trên secondary.
- Scan cũ PARTIAL/FAILED; scan mới dùng cookie rỗng và upsert/dedupe theo stable ID.
- Replica lag có thể làm thiếu entry mới hoặc trả dữ liệu cũ; phải đo freshness và chọn nguồn authoritative.
- Bỏ referral có thể bỏ sót partition partners, nên không thể công bố full scan.
- Write timeout có thể xảy ra sau khi server đã commit; phải đọc đối soát trước retry.
- Metrics: duration, error category, endpoint alias, TLS failure count, referral count, failover attempts, pages/entries, incomplete scans.
- Liveness kiểm tra process; readiness dùng bind/search nhỏ; referral health kiểm tra target cần thiết theo allowlist.

## 15. Ghi nhớ

**TLS, referral và failover là ba lớp vận hành khác nhau nhưng có thể ảnh hưởng cùng một LDAP request.** TLS xác minh danh tính và mã hóa kết nối; referral điều hướng tới naming context khác; failover chuyển sang endpoint thay thế khi dịch vụ hiện tại lỗi. Cần cấu hình TLS/truststore/hostname cho **mọi endpoint và referral target**, chọn referral policy rõ ràng và không gửi bind credential tới máy chủ không được tin cậy.

Khi chuyển server giữa một chuỗi paged search, **không mặc định cookie cũ còn hợp lệ**. Đánh dấu scan cũ partial, tạo kết nối mới và bắt đầu lại bằng cookie rỗng; xử lý idempotent theo stable ID và chỉ công bố COMPLETE khi mọi trang/partition cần thiết đã được đọc thành công. Metrics, logs, traces và health checks phải phân biệt TLS, bind, ACL, referral, replica lag, paging và lỗi downstream, đồng thời không làm lộ dữ liệu nhạy cảm.

### Tài liệu tham khảo

- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html)
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html)
- [Java SE 17 — JNDI Context and Referral](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html)
- [Java SE 17 — ReferralException](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ReferralException.html)
- [Java SE 17 — SSLHandshakeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html)
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [Spring Boot Actuator Reference](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)
