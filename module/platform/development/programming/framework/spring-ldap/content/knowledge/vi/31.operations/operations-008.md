# Certificate rotation và thay đổi bind password trong Spring LDAP

## 1. Bối cảnh và mục tiêu vận hành

Một ứng dụng **Spring LDAP** kết nối tới directory server để tìm DN, thực hiện search bằng filter, bind xác thực, đọc nhóm hoặc thay đổi entry qua `ContextSource`, `LdapTemplate`, `LdapClient` và ODM. Hai loại bí mật và danh tính thường cần xoay vòng định kỳ là:

1. **Chứng chỉ TLS của LDAP server và tập CA đáng tin cậy của client**: bảo vệ tính xác thực server và mã hóa kết nối LDAPS/StartTLS.
2. **Bind password của tài khoản dịch vụ**: cho phép ứng dụng tạo LDAP context với quyền đọc/ghi đúng theo ACL.

Cả hai có thể khiến ứng dụng mất khả năng truy cập thư mục nếu thay đổi không đồng bộ. Ví dụ, LDAP server bắt đầu trình diện chứng chỉ do CA mới ký trước khi các JVM tin cậy CA đó; hoặc mật khẩu bind trên directory đã đổi nhưng một số instance Spring vẫn dùng credential cũ và liên tục tạo context thất bại.

Bài học thuộc chương **Vận hành** của module **SPRING_LDAP** giúp người học:

- Phân biệt vòng đời **server certificate**, **CA/truststore**, **client certificate khi dùng mTLS**, và **bind password**.
- Lập kế hoạch thay đổi với khả năng chồng lấp (overlap), thứ tự cập nhật, kiểm tra trước/sau và phương án khôi phục.
- Hiểu tác động của **JNDI context**, TLS handshake, pooling, JVM truststore và cơ chế nạp secret.
- Xác minh LDAPS/StartTLS và bind bằng các công cụ hỗ trợ mà không làm lộ credential.
- Thiết kế health check, cảnh báo, kiểm thử lab và quy trình xử lý khi rotation thất bại.

Các ví dụ giả lập dùng **Spring Boot 3.x, Java 17+, Spring LDAP**, URL `ldaps://ldap.example.org:636`, base DN `dc=example,dc=org` và dữ liệu thử nghiệm. Thông số, endpoint và danh tính đều minh họa. Quy trình thực tế phải phù hợp chính sách CA, directory server, secret manager và môi trường triển khai.

## 2. Hai thay đổi, hai điểm tin cậy khác nhau

### 2.1. TLS certificate không phải bind password

| Thành phần | Ai sở hữu/cấp? | Ứng dụng dùng để làm gì? | Dấu hiệu khi sai |
| --- | --- | --- | --- |
| **LDAP server leaf certificate** | Directory operator hoặc hệ thống cấp chứng chỉ | Server trình diện để client xác minh danh tính và mã hóa kênh | TLS handshake/certificate validation thất bại |
| **Intermediate CA và trust anchor** | PKI/CA, được phân phối theo chính sách | Client kiểm tra đường dẫn chứng chỉ tới CA tin cậy | `PKIX path building failed` hoặc lỗi xác minh chuỗi |
| **Server private key** | LDAP server/secret store được quản lý | Chứng minh server sở hữu khóa tương ứng chứng chỉ | Server không thể phục vụ TLS đúng; **không bao giờ chuyển sang client** |
| **Client certificate/key (nếu mTLS)** | Ứng dụng client/PKI | Xác thực client ở tầng TLS, nếu directory yêu cầu | TLS client-auth failure; khác với simple bind password |
| **Bind DN** | Directory admin/schema | Định danh được dùng trong phép LDAP bind | Không tìm thấy DN, sai account hoặc không đủ quyền |
| **Bind password** | Directory/secret manager | Xác thực LDAP simple bind dưới danh tính dịch vụ | LDAP result code 49 hoặc exception xác thực |
| **ACL của bind account** | Directory operator | Giới hạn thao tác search/lookup/modify được phép | LDAP result code 50 hoặc thất bại quyền truy cập |

**Mấu chốt:** chứng chỉ TLS đã hợp lệ không có nghĩa bind thành công; bind thành công không chứng minh kênh đã được cấu hình TLS an toàn nếu ứng dụng cho phép truyền credential qua LDAP thuần.

Dùng **LDAPS** (thường cổng 636) hoặc **StartTLS bắt buộc** trên LDAP (thường cổng 389) với hostname verification và CA trust phù hợp. Với StartTLS, nâng cấp kết nối thành TLS **trước khi gửi credential** và không cho phép fallback im lặng về simple bind không mã hóa.

### 2.2. Các thành phần trong luồng kết nối

~~~mermaid
flowchart LR
    A["Spring service"] --> B["LdapTemplate / LdapClient"]
    B --> C["ContextSource / JNDI context"]
    C --> D["Kết nối TCP và TLS"]
    D --> E["LDAP directory server"]
    F["JVM truststore / CA bundle"] -.-> D
    G["Secret manager / env / volume"] -.-> C
    H["ACL và bind account trên directory"] -.-> E
~~~

Client kiểm tra TLS khi **thiết lập kênh bảo mật mới**. Một kết nối đang mở từ trước có thể tiếp tục dùng phiên TLS cũ tới khi đóng hoặc tạo lại. Thay file CA trên đĩa cũng không tự bảo đảm mọi context/JVM trust manager đang chạy sẽ nạp lại; phải kiểm tra hành vi thực tế và vòng đời bean/pool.

## 3. Tiền kiểm: thu thập những gì trước khi rotation?

Đầu tiên lập bản đồ các ứng dụng và các đường truy cập LDAP thực tế.

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Ứng dụng dùng LDAPS hay StartTLS? | Quyết định cách kiểm tra handshake và cấu hình TLS |
| Tên DNS kết nối là gì? | Chứng chỉ cần phù hợp hostname được client sử dụng, không chỉ tên máy chủ vật lý |
| Truststore dùng của JVM, container, hay custom SSL socket factory? | Xác định vị trí phân phối CA và có cần restart JVM không |
| Server certificate đổi **cùng CA** hay sang **CA mới**? | Nếu cùng CA và không pin leaf, thường không cần đổi trust anchor |
| Có pin chứng chỉ/khóa công khai không? | Leaf/key rotation có thể yêu cầu cập nhật pin trước |
| Ứng dụng có dùng JNDI pooling hay `PoolingContextSource` không? | Kết nối cũ và context đã xác thực có thể tồn tại sau thay đổi |
| Secret được nạp từ biến môi trường, file mount hay secret manager? | Xác định có hot reload thật hay cần rollout/restart |
| Bao nhiêu instance, job nền, cron và service dùng cùng bind DN? | Tránh một thành phần bị bỏ sót và tiếp tục dùng password cũ |
| Directory hỗ trợ hai credential hợp lệ đồng thời hoặc hai service account không? | Quyết định khả năng đổi mật khẩu không gián đoạn |
| Có read replica, failover hoặc referral? | Phải kiểm tra mọi endpoint có thể nhận kết nối và mọi đường TLS |
| Tài khoản bind có ACL nào? | Probe sau rotation phải kiểm tra **đúng quyền tối thiểu cần dùng** |

**Ghi chú an toàn:** inventory nên chứa tên logic của backend, owner, phiên bản chứng chỉ và secret version; không sao chép private key, bind password hoặc toàn bộ directory entry vào ticket hay log vận hành.

### 3.1. Xác định chứng chỉ hiện tại và mới

Ghi lại những thông tin có thể kiểm toán nhưng không phải secret: thời gian `notBefore/notAfter`, CA issuer, subject/SAN, fingerprint của **public certificate**, key usage/extended key usage, mã thay đổi và danh sách máy chủ. Fingerprint của public certificate hữu ích để xác định phiên bản được trình diện, nhưng **không dùng fingerprint làm lý do tự động tin một chứng chỉ chưa được PKI phê duyệt**.

Đối với các LDAP endpoint sau load balancer, một số node có thể trình diện chứng chỉ khác nhau khi đang rolling update. Kiểm tra cả tên DNS logic và từng node theo chính sách vận hành; nếu dùng SNI hoặc TLS termination, bảo đảm cách kiểm tra phản ánh đúng đường kết nối mà client sẽ đi qua.

### 3.2. Phân loại thay đổi và mức rủi ro

| Kịch bản | Thay đổi truststore client? | Thay đổi credential ứng dụng? | Rủi ro chính |
| --- | --- | --- | --- |
| Renew leaf certificate, **cùng CA tin cậy**, hostname không đổi | Thường **không** | Không | Phân phối nhầm chain/SAN, pinning, node chưa được cập nhật |
| Đổi CA/intermediate root trust anchor | **Có**, nếu đường dẫn mới chưa được tin | Không | Cắt trust quá sớm, handshake fail |
| Đổi hostname hoặc endpoint kết nối | Có thể | Có thể không | SAN không khớp, DNS/LB và referral khác nhau |
| Đổi bind password của account đang dùng | Không | **Có** | Các instance vẫn dùng secret cũ, account lockout |
| Đổi service bind DN/account | Không | **Có**, cả DN và password | ACL không tương đương, owner/scope chưa được duyệt |
| Đổi client certificate cho mTLS | Có thể cần keystore client mới | Không nhất thiết | Server client-auth trust và key/cert không đồng bộ |

Chỉ xoay vòng chứng chỉ hoặc password khi có đầu mối phụ trách xác nhận thay đổi. Kết hợp cả hai trong một lần deploy làm khó xác định nguyên nhân và rollback; nên chia pha nếu không có yêu cầu buộc thực hiện cùng thời điểm.

## 4. Certificate rotation: thay đổi có thứ tự để tránh ngắt kết nối

### 4.1. Khi vẫn dùng cùng trust anchor

Nếu chỉ gia hạn server leaf certificate do **CA cũ mà JVM đang tin cậy** ký, thường không cần thay truststore client. Quy trình:

1. PKI phát hành certificate mới với SAN chứa đúng hostname LDAP; kiểm tra hiệu lực, issuer, chain và định dạng.
2. Directory operator xác minh private key khớp leaf certificate và cài đặt chain đầy đủ theo quy trình của LDAP server.
3. Rolling update từng LDAP node, theo dõi handshake mới và rollback capability của node.
4. Từ **kết nối mới** trên client/test runner, kiểm tra TLS validation và LDAP bind/search nhỏ.
5. Quan sát TLS error, authentication failures, latency và các instance có thể còn kết nối cũ.

Không tự xuất private key khỏi server để thực hiện kiểm thử trên máy client. Với pinning certificate/public key, phải phối hợp cập nhật pin theo chiến lược overlap ngay cả khi CA không đổi.

### 4.2. Khi thay CA: trust-before-switch, remove-after-verify

Thay CA có thể làm tất cả JVM từ chối certificate mới nếu cập nhật server trước. Một phương án nhiều pha:

~~~mermaid
flowchart TD
    A["Trust hiện có: CA cũ"] --> B["Chuẩn bị CA mới đã phê duyệt"]
    B --> C["Phân phối trust bundle gồm CA cũ + CA mới"]
    C --> D["Rollout client / tạo kết nối TLS mới để xác minh"]
    D --> E["Thay server certificate + chain bằng rolling update"]
    E --> F["Kiểm tra handshake/bind/search trên tất cả đường kết nối"]
    F --> G{"Đã hết mọi phụ thuộc vào CA cũ?"}
    G -->|Chưa| H["Giữ overlap và xử lý phụ thuộc"]
    H --> F
    G -->|Rồi| I["Gỡ CA cũ khỏi truststore theo chính sách"]
    I --> J["Rollout và xác minh lần cuối"]
~~~

**Thứ tự logic:**

- **Pha A – chuẩn bị:** CA mới cần được xác minh qua kênh tin cậy (PKI, fingerprint ngoài băng, quy trình phê duyệt). Không tải CA từ endpoint lạ và import chỉ để “hết lỗi”.
- **Pha B – phân phối trust:** cho phép client tin **cả CA cũ và CA mới** trong một khoảng chuyển tiếp được kiểm soát. Rollout/tạo JVM hoặc SSL context mới nếu cần để cấu hình trust có hiệu lực.
- **Pha C – thay certificate server:** cập nhật từng LDAP node, bảo đảm certificate chain hoàn chỉnh và SAN khớp DNS client sử dụng.
- **Pha D – xác minh:** thử **kết nối mới** tới từng đường có thể được chọn, gồm LB/read replicas, cùng bind/search cần thiết; theo dõi lỗi handshake trên mọi instance.
- **Pha E – thu hẹp trust:** chỉ gỡ CA cũ sau khi không còn server/ứng dụng nào phụ thuộc vào nó và đã qua cửa sổ chuyển tiếp.

**Overlap làm tăng tập CA đáng tin cậy trong thời gian giới hạn**, nên phải xác định thời hạn, owner và công việc xóa CA cũ. Không để truststore mở rộng vô thời hạn. Nếu CA cũ bị **compromise**, không kéo dài overlap máy móc: quy trình thu hồi khẩn cấp và đánh giá rủi ro có thể yêu cầu cắt trust sớm, phối hợp giảm gián đoạn có kiểm soát.

### 4.3. Truststore JVM và lưu ý reload

Một ứng dụng Java có thể sử dụng truststore mặc định của JDK hoặc truststore riêng (thường dạng PKCS#12). Ví dụ cấu hình tại lúc **khởi động JVM**:

~~~text
-Djavax.net.ssl.trustStore=/run/ldap-certs/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đây là các Java system properties, không phải dòng YAML. Mật khẩu truststore nếu cần phải được quản lý theo cơ chế triển khai và secret manager thích hợp; tránh đưa mật khẩu trực tiếp vào command line, build log, crash dump hoặc ticket. Quyền filesystem phải giới hạn cho process cần đọc.

Lưu ý:

- Thay file truststore đã mount **không bảo đảm** TLS context/JNDI pool đang chạy sẽ nạp lại.
- Với rollout an toàn, nhiều môi trường chọn **thay version truststore, khởi động lại instance theo từng nhóm, kiểm tra rồi tiếp tục**, thay vì tự giả định hot reload.
- Khi xoay vòng CA, kiểm tra cả các ứng dụng không dùng Java hoặc được chạy bởi các JVM khác nhau; `cacerts` có thể khác theo base image/JDK.
- Cập nhật truststore không thay thế kiểm tra hostname. Phải xác minh hostname/SAN, certificate chain, hạn hiệu lực và trust anchor đã phê duyệt.
- Với **StartTLS**, client phải fail closed khi nâng cấp TLS hoặc validation thất bại; không được chuyển tiếp bind trên LDAP không mã hóa.

Không dùng `trustAll`, tắt hostname verification, hoặc import ngẫu nhiên public certificate của server chỉ để vượt lỗi handshake. Những “sửa lỗi” này vô hiệu hóa ý nghĩa của certificate rotation an toàn.

## 5. Xác minh TLS bằng công cụ trên môi trường test/được phép

Các lệnh bên dưới chỉ mang tính mẫu; chạy với endpoint và file CA được quản trị viên phê duyệt.

### 5.1. Kiểm tra server certificate trên LDAPS

~~~bash
# Kiểm tra kết nối TLS mới. File CA là trust bundle đã phê duyệt.
# -verify_return_error khiến lệnh thất bại khi validation gặp lỗi.
openssl s_client \
  -connect ldap.example.org:636 \
  -servername ldap.example.org \
  -verify_hostname ldap.example.org \
  -verify_return_error \
  -CAfile approved-ldap-ca.pem \
  -showcerts </dev/null
~~~

Kiểm tra hostname trong SAN, issuer/chain, thời hạn và dòng `Verify return code`. Đối với triển khai có load balancer, lần chạy trên một endpoint không chứng minh tất cả backend giống nhau: cần kiểm tra từng node theo cách được phép và đường thực sự mà JVM kết nối.

Với StartTLS, OpenSSL hỗ trợ chế độ `-starttls ldap` trên các bản dựng có tùy chọn này; đồng thời phải kiểm tra hành vi **client LDAP thực sự**. Không suy ra rằng TLS thành công với OpenSSL nghĩa là Spring LDAP đã yêu cầu StartTLS đúng thứ tự.

### 5.2. Kiểm tra bind qua kênh TLS

~~~bash
# LDAPS: yêu cầu mật khẩu tương tác, không đưa vào command line.
LDAPTLS_CACERT=approved-ldap-ca.pem ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service,dc=example,dc=org" -W

# StartTLS bắt buộc (-ZZ), chỉ dành cho môi trường dùng cổng 389.
LDAPTLS_CACERT=approved-ldap-ca.pem ldapwhoami -x -ZZ \
  -H ldap://ldap.example.org:389 \
  -D "uid=svc-reader,ou=service,dc=example,dc=org" -W
~~~

Lệnh `-W` đọc mật khẩu tương tác thay vì chèn password vào command-line history hoặc process arguments. Dùng credential **thử nghiệm hoặc credential đã được cấp quyền** đúng chính sách; không đưa secret thực vào CI log. Tùy bộ công cụ LDAP, cách cấu hình CA và xác minh hostname có thể khác JVM; **kiểm tra bằng `ldapwhoami` không thay thế kiểm tra từ Spring LDAP/JNDI đang chạy**.

### 5.3. Kiểm tra search nhẹ sau rotation

~~~bash
# Base và thuộc tính của probe phải được phép đọc theo ACL đã duyệt.
LDAPTLS_CACERT=approved-ldap-ca.pem ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=health,dc=example,dc=org" -s base \
  "(objectClass=*)" objectClass
~~~

Probe chỉ nên đọc entry/attribute ít nhạy cảm với tần suất hợp lý. Không lấy toàn bộ subtree, dump user/group hoặc thử modify production chỉ để kiểm tra chứng chỉ. Nếu account không có ACL xem entry probe, thất bại đó không mặc nhiên là lỗi TLS: tách kiểm tra handshake, bind và search trong runbook.

## 6. Bind password rotation: tại sao khó hơn thay certificate?

Tài khoản dịch vụ có thể được ứng dụng dùng để bind khi tạo context, tìm kiếm DN hoặc thực hiện modify được cấp quyền. Nếu password bị thay ở server, **context mới** dùng password cũ có thể bị từ chối ngay. Context đã được bind và đang mở có thể còn thực hiện được một số thao tác đến khi session bị đóng; điều đó khiến rollout lỗi **không đồng đều**, không có nghĩa mọi instance đã cập nhật đúng.

Các triệu chứng thường gặp:

- `javax.naming.AuthenticationException` hoặc exception tương đương của Spring LDAP, LDAP result code **49**;
- lỗi chỉ ở các instance vừa restart hoặc khi pool cần tạo connection mới;
- tỷ lệ bind lỗi tăng sau một khoảng idle, trong khi một số query qua connection cũ vẫn thành công;
- account lockout do ứng dụng thử bind lặp lại với mật khẩu đã hết hiệu lực;
- job nền/quy trình đồng bộ hiếm chạy hơn bị bỏ sót trong đợt rotation.

### 6.1. Không mặc định hỗ trợ đồng thời hai password cho một bind DN

Nhiều directory chỉ có **một mật khẩu hợp lệ hiện hành** cho một account, trừ khi sản phẩm có tính năng grace password, dual credential hoặc cơ chế chuyên biệt. Do đó trình tự “đổi password ở server rồi rolling update client” có thể tạo cửa sổ lỗi đáng kể; trình tự ngược lại cũng thất bại nếu password mới chưa hợp lệ.

Phải xác nhận khả năng của directory và chính sách tổ chức trước khi hứa có **zero downtime**.

| Khả năng directory | Hướng triển khai | Điều kiện |
| --- | --- | --- |
| Hỗ trợ **hai credential đồng thời** hoặc grace period | Kích hoạt password mới trong khi giữ password cũ hợp lệ ngắn hạn; rollout client; vô hiệu hóa cũ | Xác minh feature thực tế, có deadline loại bỏ password cũ |
| Cho phép **hai service account** cùng ACL tối thiểu | Tạo account B với secret mới; thử ACL; chuyển từng client; khóa account A sau khi không còn dùng | Audit và quyền không bị tăng quá mức; mọi consumer đã chuyển |
| Chỉ một password cho một account, không có overlap | Cutover phối hợp chặt, có kế hoạch hạn chế lỗi/ngừng dịch vụ ngắn hoặc maintenance | Không hứa không gián đoạn; dừng retry sai credential |
| Có cơ chế broker/secret provider hỗ trợ credential chuyển tiếp | Theo runbook của provider, kiểm tra toàn bộ kết nối mới | Không suy ra reload tự động từ việc secret file được cập nhật |

**Khuyến nghị vận hành:** khi yêu cầu không gián đoạn nghiêm ngặt, chiến lược **hai service account độc lập, quyền tối thiểu tương đương** thường dễ kiểm soát hơn việc thay một password duy nhất, nếu directory và chính sách bảo mật cho phép.

### 6.2. Mô hình account A → B

~~~mermaid
sequenceDiagram
    participant Ops as Directory/Secret Operator
    participant Dir as LDAP Server
    participant App as Spring LDAP Instances
    Ops->>Dir: Tạo svc-reader-b với ACL tối thiểu được phê duyệt
    Ops->>App: Phân phối credential B qua secret manager
    App->>Dir: Bind B trên kết nối mới + search probe
    Dir-->>App: Success và ACL như dự kiến
    Ops->>App: Rolling switch từng instance từ A sang B
    App->>Dir: Các connection mới dùng B
    Ops->>Dir: Đối chiếu còn bind A không
    Ops->>Dir: Khóa/thu hồi account A sau cửa sổ kiểm tra
    Note over Ops,App: Không log, sao chép hoặc trả lại password A/B
~~~

**Các bước chi tiết:**

1. Directory operator phê duyệt account B với cùng tập quyền **thật sự cần**, base DN thích hợp, chính sách TLS và hạn sử dụng.
2. Secret manager lưu password B và cấp quyền đọc cho workload đích. Không nhét mật khẩu vào Git, CI variables hiển thị, chat hay command line.
3. Dùng **kết nối mới** bằng B để thử bind, probe search và các thao tác cần thiết trong phạm vi an toàn (modify chỉ với fixture ở môi trường thử nghiệm).
4. Cập nhật cấu hình `bind DN + password` của từng instance/consumer theo từng nhóm; restart hoặc tái tạo `ContextSource`/pool theo cơ chế hỗ trợ.
5. Theo dõi account A có còn xuất hiện ở server bind audit hay không; kiểm tra cả job nền, công cụ bảo trì, lần tạo connection sau idle và đường failover.
6. Khi chắc chắn mọi consumer dùng B, thu hồi secret A và khóa/vô hiệu hóa account A theo quy trình; sau đó xác nhận không còn truy cập được bằng A.
7. Hoàn tất hồ sơ thay đổi, owner, thời điểm, kết quả kiểm thử và lịch rotation tiếp theo.

Khi account A và B cùng hoạt động, cần tránh mở rộng ACL hoặc tạo tình huống cả hai tài khoản đều tồn tại vĩnh viễn. Quyền tạm trong giai đoạn overlap phải có thời điểm thu hồi rõ ràng.

### 6.3. Nếu bắt buộc đổi password của cùng một account

Với directory chỉ chấp nhận một password, quy trình nên có **cutover window** phối hợp:

- Chuẩn bị và phân phối bản secret mới nhưng không kích hoạt client dùng nó trước khi server chấp nhận.
- Hạn chế công việc phát sinh LDAP; thông báo bảo trì nếu SLA không chịu được cửa sổ lỗi.
- Đổi password trên directory qua kênh quản trị đã được phê duyệt.
- Kích hoạt/rollout ngay các workload dùng password mới, bảo đảm các context/pool cũ được thay thế theo cơ chế an toàn.
- Xác minh các **kết nối mới** bind thành công, probe có đúng ACL và không xuất hiện auth failure tăng bất thường.
- Dừng những instance vẫn dùng password cũ; không để chúng retry liên tục và gây khóa account.

**Rollback không đơn giản là triển khai lại bản ứng dụng cũ**: password cũ có thể đã bị vô hiệu hóa trên directory. Nếu cutover thất bại, cần runbook cấp lại secret hợp lệ hoặc chuyển về account còn hoạt động theo phê duyệt. Không tự ý “đặt lại password cũ” nếu vi phạm chính sách rotation.

## 7. Spring Boot và ContextSource: mật khẩu lấy từ đâu, có reload không?

Ví dụ cấu hình các property để tránh đưa secret vào source code:

~~~yaml
# application.yml — chỉ là ví dụ của ứng dụng Spring Boot
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
    connect-timeout-ms: 1000
    read-timeout-ms: 2500

# Biến môi trường phải được cấp bằng secret deployment/secret manager.
# Không commit password thật, không in danh sách env variables ra log.
~~~

Đăng ký `LdapContextSource` và `LdapTemplate`:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    public LdapContextSource directoryContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String bindPassword,
            @Value("${app.ldap.connect-timeout-ms}") int connectMs,
            @Value("${app.ldap.read-timeout-ms}") int readMs) {

        if (connectMs <= 0 || readMs <= 0) {
            throw new IllegalArgumentException("LDAP timeout must be positive");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);

        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout",
                Integer.toString(connectMs),
                "com.sun.jndi.ldap.read.timeout",
                Integer.toString(readMs)));

        // Minh họa đơn giản, không tái sử dụng context giữa các lượt gọi.
        // Production có thể cần pool có validation, max size và borrow timeout.
        source.setPooled(false);
        return source;
    }

    @Bean
    public LdapTemplate directoryLdapTemplate(
            LdapContextSource directoryContextSource) {
        return new LdapTemplate(directoryContextSource);
    }
}
~~~

Spring quản lý lifecycle của bean `LdapContextSource` trong đoạn mã trên. Đặt timeout dương giúp tránh chờ quá lâu nhưng **connect/read timeout không phải deadline cho toàn bộ API**; các lời gọi search, bind và retry có thể tiếp tục nhiều bước.

### 7.1. Vì sao đổi Secret trong Kubernetes hoặc secret manager chưa chắc đủ?

Có hai tình huống:

- **Secret được inject qua environment variables:** process đang chạy thường giữ bản environment đã nhận khi khởi động. Cập nhật secret phía deployment **không tự thay giá trị trong process**; thường cần rolling restart/redeploy.
- **Secret được mount qua file hoặc đọc trực tiếp từ secret manager:** file/giá trị có thể thay đổi nhưng bean `ContextSource` và các connection đã bind có thể vẫn giữ credential cũ. Cần cơ chế reload được thiết kế, kiểm thử thread safety và làm mới context/pool; không mặc định Spring LDAP có tự động hot reload password.

Vì vậy **chiến lược an toàn mặc định** khi không có cơ chế reload đã được kiểm chứng là rolling restart với cấu hình/secret version mới, sau mỗi nhóm đều kiểm tra tạo connection mới.

Không gọi `setPassword(...)` trên bean `LdapContextSource` đang được nhiều thread dùng và giả định tất cả request/pool tự chuyển sang credential mới. Thay đổi runtime phải tuân theo API và lifecycle của thư viện, bao gồm việc tạo context mới, loại bỏ connection cũ và xử lý request đang chạy.

### 7.2. Kiểm tra chứng chỉ mới cũng phải tạo connection mới

Lỗi TLS có thể không xuất hiện ngay nếu một instance vẫn giữ kết nối LDAPS cũ qua pool. Một health check dùng lại context cũ có thể báo “UP” trong khi **mọi kết nối mới đều thất bại** với chứng chỉ mới. Để xác minh rotation, cần một probe có kiểm soát buộc thiết lập TLS + bind mới, không chỉ tận dụng pool.

Khi dùng `LdapContextSource.setPooled(true)`, phải phân biệt JNDI native pooling với các wrapper như `PoolingContextSource`. Mỗi dạng pool có giới hạn, validation và cách đóng/loại bỏ context khác nhau. Với StartTLS, kiểm tra tương thích với pooling đặc biệt kỹ; không tái sử dụng một kết nối ở trạng thái TLS/bind không phù hợp.

## 8. Kiểm thử theo tầng: TLS, bind, search và quyền tối thiểu

Không gom mọi thất bại thành “LDAP down”. Sau một đợt rotation, kiểm tra các tầng độc lập:

| Tầng | Kiểm tra | Nếu thất bại, xem xét |
| --- | --- | --- |
| DNS/TCP | Host/cổng reachable, không timeout | DNS, firewall, service endpoint, LB |
| TLS | Chain, CA trust, hostname/SAN, thời hạn chứng chỉ | Truststore cũ, server chain thiếu, cert chưa valid |
| Bind | Tạo context mới với bind account dự kiến | Password cũ, bind DN sai, account bị khóa/hết hạn |
| Read probe | Lookup/search nhỏ trong OU test/health | ACL, schema, DN sai, replica chưa đồng bộ |
| Nghiệp vụ thật | Ví dụ search user, nhóm và lookup các thuộc tính cần thiết | Bind account mới thiếu quyền so với cũ |
| Write test (lab) | Modify một entry giả được phép | ACL modify, trạng thái commit, quyền tăng ngoài ý muốn |
| Pool/idle | Mượn context sau idle hoặc sau reload | Connection stale, pool vẫn giữ credential cũ |
| Failover/replica | Kết nối mới đến từng endpoint có thể nhận traffic | Chưa cập nhật cert/account/ACL ở một node |

### 8.1. Health check không thay thế test chuyên biệt

Health check của ứng dụng nên hữu hạn, rẻ và không gây tác dụng phụ. Ví dụ có một entry `ou=health` mà account dịch vụ được cấp quyền đọc phù hợp:

~~~java
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryProbe {
    private final LdapTemplate ldap;

    public DirectoryProbe(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public boolean canReadProbeEntry() {
        return ldap.lookup(
                "ou=health",
                (AttributesMapper<Boolean>) attrs ->
                        attrs.get("objectClass") != null);
    }
}
~~~

Phép lookup chỉ xác nhận account có thể đọc entry probe tại thời điểm kiểm tra. **Nó không chứng minh một kết nối TLS mới đã bắt tay lại** nếu pool có thể cung cấp context cũ; cũng không chứng minh account có đủ quyền cho mọi thao tác nghiệp vụ. Trường hợp LDAP server trả zero result, ACL từ chối hoặc DN không tồn tại cần được phân loại, không trả “healthy” bằng cách nuốt exception.

Đối với readiness, quyết định phụ thuộc LDAP có bắt buộc để phục vụ request không. Liveness thường không nên fail chỉ vì directory tạm không sẵn sàng, tránh restart loop. Khi cần kiểm tra rotation riêng, dùng probe có chủ đích với tần suất thấp và credential tối thiểu.

### 8.2. Quan sát các metric chính

Theo dõi trước, trong và sau rotation:

- `ldap_tls_handshake_failures` hoặc số lỗi TLS đã phân loại từ client/server;
- `ldap_bind_attempts` chia theo thành công, auth failure, network, server unavailable;
- `ldap_search_latency` và tỷ lệ lỗi lookup/search;
- `ldap_pool_active`, `ldap_pool_idle`, `ldap_pool_borrow_timeout` nếu pool có API đo thật;
- số instance đang dùng secret/config version mới (mã phiên bản không nhạy cảm);
- `LDAP result code 49` và mức account lockout nếu directory hỗ trợ metric;
- tỷ lệ lỗi API cần LDAP, p95/p99 latency và mức retry amplification;
- exporter/logging không chứa password, DN thực, filter hoặc certificate private key.

Không bắt buộc mọi metric đều đã có từ Spring LDAP mặc định; cần instrument tại đúng boundary hoặc lấy từ LDAP server/secret manager theo khả năng thực tế. Đừng tạo metric giả cho TLS handshake hay pool khi không đo được.

## 9. Kế hoạch rollback và ngưỡng dừng

Một kế hoạch rotation tốt phải định nghĩa trước **khi nào dừng rollout** và **cái gì thực sự có thể khôi phục**.

| Tình huống | Dấu hiệu phát hiện | Hành động phù hợp |
| --- | --- | --- |
| Client chưa tin CA mới | TLS handshake fail khi tạo kết nối mới | Dừng server cert rollout; xác minh/phân phối trust bundle được duyệt |
| Server cấp sai SAN hoặc chain | Hostname/PKIX validation fail ở một hoặc nhiều node | Cài chứng chỉ/chain hợp lệ; không tắt TLS validation |
| Chỉ một replica LDAP lỗi | Lỗi tập trung ở endpoint/node | Rút node lỗi khỏi LB theo quy trình và sửa cấu hình |
| Secret B mới không bind được | Invalid credentials cho B | Dừng client switch; kiểm tra secret version/account B trên directory |
| Secret B bind được nhưng search bị ACL denied | Mã lỗi 50 ở thao tác nghiệp vụ | Chỉnh quyền đã được phê duyệt hoặc dùng account còn hiệu lực trong pha overlap |
| Nhiều app vẫn dùng A sau hạn | Audit bind A còn xuất hiện, job nền lỗi | Tìm consumer còn sót, rollout lại trước khi vô hiệu hóa A |
| Single-account password đã đổi, client dùng cũ | Auth failure diện rộng | Kích hoạt credential hợp lệ mới hoặc kế hoạch bảo trì đã phê duyệt |
| Pool giữ kết nối cũ sau cập nhật | Lỗi sau idle/restart khác nhau giữa instance | Thay/đóng pool theo lifecycle, buộc probe trên kết nối mới |
| LDAP server không đáp ứng, retry tăng | p95 latency/throughput suy giảm | Dừng rollout, giới hạn retry/backoff; không retry mật khẩu sai |

**Ngưỡng dừng** nên gắn với SLO và baseline trước thay đổi: ví dụ tỷ lệ bind `auth error` tăng liên tục, probe TLS mới thất bại, hoặc nhiều instance không thể search. Giá trị cụ thể do team vận hành đặt dựa trên lưu lượng, không tự coi một request thất bại là điều kiện chung cho mọi hệ thống.

### 9.1. Khác biệt rollback certificate và rollback password

- Với **server certificate rollout chưa hoàn tất**, có thể quay về chứng chỉ cũ **nếu còn hợp lệ và chưa bị thu hồi**, đồng thời trust bundle client vẫn chứa CA cũ. Không rollback về key/certificate đã bị compromise.
- Với **CA trust rotation**, phân phối lại trust bundle đã được phê duyệt có thể khôi phục client, nhưng cần kiểm tra JVM reload và máy chủ nào đang dùng cert mới.
- Với **password rotation**, khôi phục ứng dụng dùng credential A chỉ hoạt động nếu A còn hiệu lực. Nếu A bị đổi/vô hiệu hóa, rollback image hoặc cấu hình cũ đơn thuần sẽ không khắc phục. Cần cấp credential hợp lệ hoặc dùng account B đang hoạt động.
- Với **account A → B**, rollback trong cửa sổ overlap dễ hơn nếu A vẫn hợp lệ; sau khi A đã vô hiệu hóa, phải tuân theo quy trình cấp lại/đổi tài khoản và audit phù hợp.

## 10. Bảo mật secret và logging trong suốt rotation

Dữ liệu đặc biệt nhạy cảm trong quá trình thay đổi bao gồm bind password, keystore password, client private key, server private key, token secret manager và thông tin danh tính trong LDAP filter/DN.

**Không được đưa vào log hoặc hệ thống quan sát:**

- Password gốc, chuỗi `Authorization`, file private key hoặc nội dung `Secret`;
- bind DN/entry DN/LDAP filter có thể chứa thông tin người dùng;
- dump toàn bộ `ContextSource`, environment, request DTO hoặc exception message chưa qua kiểm soát;
- output của công cụ có bật JNDI BER trace (`com.sun.jndi.ldap.trace.ber`) trong môi trường production;
- thông tin từ `javax.net.debug` nếu không qua quy trình chẩn đoán bảo mật có thời hạn.

**Được phép ghi theo chính sách:** mã đợt thay đổi, tên cụm logic, phiên bản certificate công khai đã xác minh, credential **version ID không nhạy cảm**, operation kind, outcome, error category, elapsed time, thời điểm rollout và số instance đã chuyển.

Ví dụ event hợp lý:

~~~json
{
  "event": "ldap.rotation.verify",
  "backend": "primary",
  "rotation_kind": "bind_credential",
  "credential_version": "release_2026_11_b",
  "probe": "fresh_bind_and_lookup",
  "outcome": "success",
  "elapsed_ms": 83
}
~~~

Không ghi fingerprint của password hoặc HMAC password để “xác minh” hai secret giống nhau. Có thể ghi fingerprint của **public TLS certificate** trong hệ thống kiểm toán được kiểm soát, nhưng nó không phải bằng chứng độc lập về CA trust hay hostname validation.

### 10.1. Mật khẩu và khả năng rò rỉ qua công cụ

Không dùng những ví dụ nguy hiểm như `ldapwhoami -w MySecret`, `curl -u user:password`, hoặc echo secret ra shell. Đối với automation, ưu tiên secret manager và input an toàn do công cụ/runner hỗ trợ, vô hiệu hóa shell xtrace khi xử lý secret, hạn chế quyền đọc file tạm và xóa theo quy trình.

Một lệnh an toàn hơn cho thao tác thủ công là `ldapwhoami -W` để nhập password tương tác. Nếu test tự động yêu cầu cung cấp secret, triển khai qua stdin/file descriptor hoặc API an toàn theo công cụ thực tế, tránh truyền secret trong process arguments và log pipeline.

## 11. Kịch bản thực hành trong LDAP test environment

**Mô hình:** hai LDAP test nodes sau endpoint logic `ldap.example.org`, một Spring Boot service gồm hai replica, một tài khoản dịch vụ `svc-reader-a` và một account thay thế `svc-reader-b` có ACL đọc các entry giả. Tất cả dùng LDAPS với truststore được quản lý. Không sử dụng tài khoản hay chứng chỉ production để luyện tập.

### 11.1. Chuẩn bị lab

1. Cấp certificate server hợp lệ cho hostname test, CA cũ và CA mới đã được xác minh, thời gian hiệu lực phù hợp.
2. Tạo `ou=health` hoặc một probe DN không nhạy cảm cho tài khoản test.
3. Tạo bind account A và B với cùng **quyền đọc tối thiểu**; dùng secret khác nhau.
4. Bật logging có phân loại lỗi nhưng không chứa DN/filter/password; đo số lỗi TLS và LDAP bind.
5. Chọn ít nhất hai replica ứng dụng để quan sát quá trình rolling update.
6. Chuẩn bị phương án khôi phục mỗi thay đổi: cả certificate cũ còn hợp lệ và account A trong lab còn dùng được tới khi xác minh B.

### 11.2. Ma trận kiểm thử

| Ca | Tình huống | Kỳ vọng và điều cần quan sát |
| --- | --- | --- |
| C1 | Kết nối LDAPS với CA hiện hành | TLS handshake, bind, lookup probe thành công |
| C2 | Server chuyển sang cert CA mới trước khi client tin CA mới | Fresh connection thất bại validation, không fallback TLS |
| C3 | Client tin đồng thời CA cũ+mới | Trong overlap, node cũ và node mới đều kết nối được |
| C4 | Server cert mới có SAN không khớp endpoint | Hostname verification thất bại; không tắt kiểm tra |
| C5 | Server thiếu intermediate certificate | Validation có thể thất bại; bổ sung chain hợp lệ |
| C6 | Client vẫn giữ context/pool từ trước khi đổi cert | Health cũ có thể còn xanh; probe fresh TLS phát hiện sai lệch |
| C7 | Thay secret ở secret manager nhưng không restart instance dùng env var | Process vẫn dùng phiên bản cũ, xác nhận cần rollout |
| C8 | Account B bind được nhưng không đọc được probe | Phân loại ACL issue, không coi là TLS error |
| C9 | Rollout instance thứ nhất sang B, instance thứ hai còn dùng A | Cả hai hoạt động trong pha overlap; audit cho thấy hai identity |
| C10 | Vô hiệu hóa account A sau khi B đã được xác minh | Chỉ B còn dùng được; không còn client tạo bind A |
| C11 | Đổi password một account không có grace window | Nhìn thấy cửa sổ auth failure và lý do không thể hứa zero downtime |
| C12 | Secret sai hoặc account bị khóa | LDAP invalidCredentials, dừng retry vô điều kiện |
| C13 | LDAP replica bị lỗi khi rotation | Failover chỉ tới endpoint tin cậy, cert và ACL được kiểm tra |
| C14 | Log/trace trong suốt đợt chuyển | Không có password, raw DN/filter hay private key |
| C15 | Đổi cert client mTLS (nếu test server bật mTLS) | Client key/cert mới được server xác thực trước khi simple bind |

Chỉ chạy các ca gây lỗi TLS/password hoặc khóa account trên **directory lab có kiểm soát**; không phá kết nối production hoặc thay tài khoản thật để tạo lỗi giả lập.

### 11.3. Bài tập phân tích sự cố

Tình huống A: 20 phút sau khi thay chứng chỉ, HTTP API vẫn có 95% request thành công nhưng 5% request thất bại với PKIX. Hãy tìm hiểu khả năng các instance có truststore/JVM version khác nhau, một LDAP node còn chain lỗi hoặc những connection cũ chưa được đóng. Đối chiếu **fresh handshake theo từng node** thay vì chỉ kiểm tra một search từ một instance.

Tình huống B: Sau khi đổi password của `svc-reader-a`, chỉ các pod vừa restart bị lỗi mã 49, pod cũ vẫn search thành công. Giải thích vì sao connection đã bind có thể còn sống, vì sao readiness qua pool không phát hiện ngay, và tại sao restart tất cả pod với secret cũ sẽ làm sự cố tệ hơn.

Tình huống C: Account B xác thực thành công nhưng modify trên fixture báo `insufficientAccessRights`. Điều này chứng minh TLS và credential B hoạt động, còn **ACL không tương đương**; không giải quyết bằng retry hay tăng quyền bừa bãi. Đối chiếu phạm vi thuộc tính, object class, subtree và tài khoản quản trị cấu hình ACL.

### 11.4. Tiêu chí hoàn thành

Một bài lab đạt yêu cầu khi chứng minh:

- Client xác minh certificate chain và hostname trên **kết nối mới**;
- Pha trust overlap cho phép chuyển sang CA mới mà không phải tắt TLS validation;
- Secret version mới được dùng thật bởi các context mới, không chỉ thay file cấu hình;
- Quy trình account A → B có điểm kiểm tra ACL và thời điểm thu hồi A;
- Không gửi password qua log/command line/trace và không bật BER tracing trong vận hành;
- Health, metrics và audit phân biệt TLS, bind, ACL, pool và lỗi nghiệp vụ;
- Runbook có stop condition, owner, rollback thực tế và bằng chứng xác minh sau thay đổi.

## 12. Runbook đề xuất cho production

### Pha 0 — Lập kế hoạch

- [ ] Xác định phạm vi endpoint LDAP, ứng dụng, số instance, service account, job nền và các consumers khác.
- [ ] Phân loại kịch bản: leaf renewal cùng CA, CA change, mTLS client cert hoặc bind password/account.
- [ ] Lấy chứng chỉ/CA hoặc secret version mới qua hệ thống được phê duyệt, không đưa private key/password vào ticket.
- [ ] Xác định SLO, baseline lỗi, ngưỡng dừng, owner và kênh phối hợp directory/PKI/ứng dụng.
- [ ] Kiểm tra khả năng overlap; nếu directory chỉ một password, công bố cửa sổ bảo trì/cutover phù hợp.

### Pha 1 — Chuẩn bị và canary

- [ ] Với CA change: phân phối trust bundle gồm CA cũ+mới **trước** khi thay cert server; làm mới JVM/SSL context theo cách hỗ trợ.
- [ ] Với bind account: tạo/kiểm thử account B hoặc bảo đảm grace period thật sự được hỗ trợ.
- [ ] Triển khai canary trên một instance hoặc nhóm nhỏ, thử fresh TLS, bind, search và quyền tối thiểu.
- [ ] Xác minh metric error rate, latency, retry và dấu hiệu pool stale; log không rò rỉ credential.

### Pha 2 — Cutover có quan sát

- [ ] Thay cert server theo nhóm node hoặc chuyển từng client sang bind credential mới đúng thứ tự.
- [ ] Theo dõi health/readiness, connection mới, auth error, TLS handshake, search/ACL và hoạt động của job nền.
- [ ] Dừng rollout khi vượt ngưỡng đã xác định; không tắt validation hoặc tự retry mật khẩu sai để vượt lỗi.
- [ ] Nếu dùng pool, xử lý connection cũ theo lifecycle/thủ tục được hỗ trợ để bảo đảm cấu hình mới có hiệu lực.

### Pha 3 — Hoàn tất và thu hồi

- [ ] Kiểm tra toàn cụm, mọi failover path và các consumer chạy không thường xuyên.
- [ ] Với CA change: gỡ CA cũ sau khi hết phụ thuộc và đúng thời hạn chuyển tiếp.
- [ ] Với account A → B: thu hồi secret A và khóa A sau khi chắc chắn không còn bind A.
- [ ] Lưu kết quả kiểm thử, thời điểm, certificate public fingerprint/secret version ID không nhạy cảm, owner và audit.
- [ ] Đặt lịch rotation tiếp theo và bổ sung bài học từ sự cố nếu có.

## 13. Những sai lầm cần tránh

1. **Đổi cert server trước khi cập nhật CA trust** khi client chưa tin CA mới.
2. **Tắt hostname verification hoặc dùng trust-all** để sửa lỗi PKIX.
3. **Cho rằng file truststore mới trên volume sẽ tự được JVM và pool đọc lại**.
4. **Cho rằng LDAP bind account tự hỗ trợ hai password đang hiệu lực** nếu chưa xác minh tính năng.
5. **Cho rằng sửa Secret object đồng nghĩa mọi Spring bean đang chạy có password mới**.
6. **Chỉ kiểm tra qua connection pool cũ**, không thử một TLS + bind connection mới.
7. **Retry liên tục invalidCredentials**, có thể dẫn tới account lockout và tăng tải directory.
8. **Bỏ sót cron/background jobs**, consumer không thường xuyên hoặc LDAP replicas khác.
9. **Dùng rollback image cũ khi password cũ đã vô hiệu hóa**, khiến mọi request thất bại.
10. **Ghi password, DN, LDAP filter hoặc exception nguyên văn** trong ticket, trace, metric hoặc log để chứng minh rotation.
11. **Cho rằng bind thành công là đủ**, dù account mới có thể không đọc/ghi đúng ACL.
12. **Để overlap vô thời hạn**: CA cũ và service account cũ phải được thu hồi đúng mốc đã phê duyệt.

**Nguyên tắc kết thúc:** certificate rotation và bind password rotation trong **Spring LDAP** là hai quy trình khác nhau nhưng cùng đòi hỏi **thứ tự chuyển đổi, xác minh bằng kết nối mới, quan sát phân tầng và kế hoạch khôi phục thực tế**. Khi quản lý rõ lifecycle của `ContextSource`/pool, truststore, secret version và ACL, có thể giảm thiểu gián đoạn mà không phải đánh đổi tính an toàn của kết nối và dữ liệu thư mục.
