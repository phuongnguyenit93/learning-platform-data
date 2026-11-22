# Kiểm tra hostname và chứng chỉ máy chủ

Khi ứng dụng gửi email bằng **Spring Framework Mail**, việc bật TLS chưa đủ để chứng minh nó đang kết nối đến **đúng máy chủ SMTP**. TLS có thể mã hóa dữ liệu, nhưng ứng dụng còn phải xác minh chứng chỉ mà server đưa ra có đáng tin cậy và có thực sự đại diện cho hostname SMTP mà ứng dụng định kết nối hay không.

Ví dụ, ứng dụng được cấu hình gửi qua `smtp.example.com`. Nếu một proxy, DNS bị thay đổi hoặc máy chủ giả mạo trả một chứng chỉ hợp lệ cho `mail.attacker.example`, kết nối không được phép chấp nhận chứng chỉ đó chỉ vì chứng chỉ có chữ ký của một CA đáng tin. Cần thêm bước kiểm tra **tên máy chủ**. Ngược lại, một chứng chỉ có tên `smtp.example.com` nhưng được ký bằng CA không đáng tin cũng không đủ an toàn.

Với Jakarta Mail được Spring Mail sử dụng, một thuộc tính rất quan trọng là `mail.smtp.ssl.checkserveridentity=true`. Kết hợp thuộc tính này với hệ thống truststore/PKI đúng, cấu hình STARTTLS hoặc implicit TLS chính xác và kiểm tra vận hành có thể giúp ứng dụng chống giả mạo endpoint, bảo vệ SMTP credential và tránh gửi nội dung thư qua kênh không xác thực.

Bài học trình bày mô hình tin cậy, quy tắc đối chiếu hostname với Subject Alternative Name (SAN), sự khác biệt giữa certificate chain và server identity, cấu hình Spring Boot/`JavaMailSenderImpl`, cách kiểm tra bằng OpenSSL và `keytool`, các nguyên nhân lỗi thường gặp, quy trình xử lý và bài tập thực hành.

## 1. Hai câu hỏi phải trả lời khi kết nối TLS

Một kết nối TLS được xác minh đúng phải trả lời được hai câu hỏi độc lập:

1. **Chứng chỉ có đáng tin cậy không?** Có xây được certificate chain hợp lệ tới một trust anchor được ứng dụng/JVM tin cậy, đồng thời thỏa các điều kiện cần thiết về thời hạn, thuật toán, mục đích sử dụng và chính sách xác minh hay không?
2. **Chứng chỉ có thuộc đúng máy chủ cần kết nối không?** Hostname mà ứng dụng định truy cập có khớp định danh được chứng chỉ xác nhận, thường là `dNSName` trong extension `Subject Alternative Name` hay không?

Có thể hình dung:

```text
Spring application
      |
      v
Connect to smtp.example.com:587
      |
      v
STARTTLS negotiation
      |
      v
Server sends certificate chain
      |
      +--> Certificate chain trusted?
      |        |
      |        +-- No  -> reject TLS connection
      |
      +--> SAN matches smtp.example.com?
      |        |
      |        +-- No  -> reject TLS connection
      |
      v
Authenticated TLS channel
      |
      v
SMTP AUTH -> MAIL FROM -> RCPT TO -> DATA
```

Hai điều kiện đều cần thiết. Chỉ kiểm tra chain mà không kiểm tra tên có thể khiến ứng dụng tin một server có chứng chỉ hợp lệ cho **một hostname khác**. Chỉ khớp tên nhưng bỏ qua chữ ký/CA có thể khiến ứng dụng tin chứng chỉ tự tạo của kẻ tấn công.

### 1.1. Minh họa ba trường hợp

| Chứng chỉ | Chain tin cậy? | SAN khớp host đang kết nối? | Kết quả nên có |
|---|---|---|---|
| Được CA hợp lệ cấp cho `smtp.example.com` | Có | Có | Có thể chấp nhận nếu các kiểm tra khác đạt. |
| Được CA hợp lệ cấp cho `mail.other.example` | Có | Không | **Từ chối** vì sai định danh máy chủ. |
| Chứng chỉ tự ký ghi `smtp.example.com` nhưng chưa được tin cậy | Không | Có | **Từ chối** vì không có đường tin cậy hợp lệ. |
| Chứng chỉ đúng tên nhưng đã hết hạn | Không đạt thời hạn | Có | **Từ chối**. |
| Chứng chỉ có tên và CA hợp lệ nhưng server không chứng minh được sở hữu private key | Không hoàn tất handshake | Có về mặt tên | **Từ chối**. |

Những kiểm tra này diễn ra trước khi ứng dụng trao đổi thông tin SMTP nhạy cảm qua kênh đã xác thực.

## 2. Rủi ro khi không kiểm tra hostname và chứng chỉ

### 2.1. Server impersonation

Kẻ tấn công hoặc một thành phần cấu hình sai có thể đưa ứng dụng tới endpoint khác:

```text
Ứng dụng
  |
  | smtp.example.com
  v
DNS / proxy / route bị điều hướng
  |
  v
SMTP endpoint không đúng
  |
  +--> Trình ra certificate của tên khác
```

Nếu ứng dụng chỉ quan tâm “có TLS hay không” mà không xác thực đúng hostname, nó có thể thiết lập kênh mã hóa **với sai đối tượng**. Mã hóa với máy chủ giả mạo không bảo vệ thông tin khỏi chính máy chủ đó.

### 2.2. Lộ SMTP credential

SMTP AUTH có thể dùng password, app password hoặc token. Nếu endpoint không đáng tin được chấp nhận, credential có thể bị cung cấp cho bên không có quyền.

Do đó, **không gửi credential trước khi TLS bắt buộc và xác thực server thành công** đối với cấu hình submission yêu cầu TLS.

### 2.3. Lộ nội dung email và attachment

Thông điệp có thể chứa:
- mã xác nhận;
- hóa đơn;
- thông tin giao dịch;
- dữ liệu khách hàng;
- file attachment;
- liên kết hành động có token.

Nếu server SMTP nhận dữ liệu không phải server định gửi, các thông tin này có thể bị tiết lộ. Không nên xem “đã mã hóa bằng TLS” là bảo đảm đủ khi chưa biết server ở đầu bên kia là ai.

### 2.4. STARTTLS downgrade

Với STARTTLS, client bắt đầu bằng một phiên SMTP trước khi nâng cấp TLS. Nếu kênh mạng hoặc proxy can thiệp làm server không quảng cáo STARTTLS và client vẫn tiếp tục gửi plaintext, dữ liệu có thể bị lộ.

Vì vậy, khi provider yêu cầu STARTTLS, cần cấu hình:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

Hai property không thay thế hostname verification; chúng giúp đảm bảo **TLS phải được dùng**, còn việc xác thực danh tính server cần `mail.smtp.ssl.checkserveridentity=true` và truststore hợp lệ.

## 3. Hostname nào phải được kiểm tra?

Một ứng dụng có thể thấy nhiều tên liên quan đến email:
- domain của người gửi như `example.com`;
- địa chỉ recipient như `customer@recipient.example`;
- SMTP submission host như `smtp.mail-provider.example`;
- tên server bên trong DNS/CNAME;
- reverse DNS/PTR;
- MX record của domain người nhận.

**Khi ứng dụng kết nối trực tiếp tới SMTP submission server, hostname cần đối chiếu với chứng chỉ là hostname mà client sử dụng cho kết nối SMTP**, ví dụ giá trị `spring.mail.host`.

Nếu app cấu hình:

```yaml
spring:
  mail:
    host: smtp.mail-provider.example
    port: 587
```

thì chứng chỉ server phải chứng minh danh tính phù hợp với `smtp.mail-provider.example`, không phải domain phần sau dấu @ của recipient, không phải Subject của email và không nhất thiết là domain của người gửi.

### 3.1. Ví dụ về MX, SMTP relay và domain người gửi

```text
From: billing@store.example
To: user@customer.example

Ứng dụng gửi qua:
smtp.provider.example:587
```

Tại chặng từ ứng dụng tới provider, kiểm tra TLS identity đối với `smtp.provider.example`. Việc provider chuyển tiếp thư đến MX của `customer.example` là chặng khác, do MTA/provider quản lý theo chính sách vận chuyển của họ.

Những cơ chế như MTA-STS hoặc DANE/TLSA liên quan nhiều tới bảo vệ vận chuyển SMTP giữa các MTA. Chúng **không thay thế** việc ứng dụng Spring Mail xác thực hostname của submission server theo cấu hình kết nối trực tiếp.

### 3.2. Host alias, CNAME và load balancer

Giả sử ứng dụng dùng `smtp.internal.example`, CNAME tới `smtp.service.example`. Nếu hostname thực tế dùng để thiết lập TLS và đối chiếu danh tính là `smtp.internal.example`, certificate cần phù hợp với tên đó theo chính sách hostname verification, ngay cả khi hai tên trỏ cùng địa chỉ IP.

Không tự giả định CNAME làm hai hostname tương đương để xác minh TLS. Khi cần, cấu hình:
- đúng hostname chính thức được SMTP provider hỗ trợ;
- certificate SAN cho alias mà tổ chức thực sự sử dụng;
- SNI/load balancer trả về certificate phù hợp với tên client kết nối;
- DNS và TLS termination nhất quán giữa các node.

### 3.3. Kết nối trực tiếp bằng IP

Một chứng chỉ có `DNS:smtp.example.com` không mặc nhiên hợp lệ cho kết nối tới `203.0.113.10`. Nếu client dùng IP làm identity, chứng chỉ cần định danh IP phù hợp (thường là `iPAddress` SAN) theo quy tắc của TLS stack.

Trong phần lớn ứng dụng, nên dùng hostname chính thức thay vì hardcode IP. IP có thể thay đổi sau failover, gây mất SNI đúng hoặc làm certificate hostname check thất bại.

## 4. Subject Alternative Name (SAN) và quy tắc khớp tên

Certificate X.509 hiện đại thường chứa extension **Subject Alternative Name**. Đối với một hostname DNS, client kiểm tra các định danh `dNSName` trong SAN.

Ví dụ:

```text
Subject: CN=mail.example.com
X509v3 Subject Alternative Name:
    DNS:smtp.example.com,
    DNS:mail.example.com
```

Với ví dụ này, certificate có thể hợp lệ về tên cho `smtp.example.com` hoặc `mail.example.com` nếu chain, thời hạn và các kiểm tra khác hợp lệ.

### 4.1. Common Name không phải lựa chọn ưu tiên

Chứng chỉ cũ thường đặt tên máy chủ ở trường `Subject CN`. Các hệ thống hiện đại ưu tiên SAN; hành vi fallback sang CN khi không có SAN có thể khác nhau theo phiên bản thư viện, quy tắc chuẩn và chính sách hạ tầng.

Để tránh không tương thích:
- cấp certificate có SAN DNS/IP đúng;
- không chỉ dựa vào CN;
- kiểm tra trên chính Java runtime/Jakarta Mail implementation mà ứng dụng dùng.

### 4.2. Wildcard không khớp mọi cấp

Một certificate có:

```text
DNS:*.example.com
```

có thể phù hợp với `smtp.example.com` trong phạm vi quy tắc wildcard mà TLS stack áp dụng. Không nên giả định nó khớp:
- `example.com` (không có nhãn con);
- `a.b.example.com` (có hai nhãn con);
- mọi biến thể tên quốc tế hoặc IDN;
- host thuộc domain khác như `smtp.example.net`.

Hãy kiểm chứng chính xác bằng hostname verification của Java và hạn chế wildcard rộng khi không cần.

### 4.3. DNS không phải bằng chứng sở hữu certificate

Một A/AAAA/CNAME record trỏ tới server không chứng minh certificate của server hợp lệ. DNS có thể cấu hình sai hoặc bị thay đổi, trong khi certificate identity vẫn cần được đối chiếu độc lập với hostname client định truy cập.

### 4.4. Server Name Indication (SNI)

Với một IP phục vụ nhiều hostname, TLS server có thể dùng **SNI** từ ClientHello để chọn certificate đúng.

Nếu client không gửi SNI phù hợp, hoặc proxy/load balancer dùng default certificate của hostname khác, ứng dụng có thể gặp hostname mismatch dù endpoint nhìn có vẻ hoạt động.

Khi chẩn đoán bằng OpenSSL, truyền hostname tường minh qua `-servername`. Với Java, kiểm tra thực tế trong JSSE debug và cấu hình endpoint; không tự sửa truststore để chữa một server đang trả nhầm certificate do SNI.

## 5. Certificate chain: tin cậy là một bước khác với khớp tên

Một certificate chain thường có dạng:

```text
Trusted Root CA / trust anchor
           |
           v
Intermediate CA
           |
           v
Server certificate
  SAN: DNS:smtp.example.com
```

Để tin server certificate, TLS client cần xác minh:
- chain dẫn tới trust anchor được tin cậy;
- chữ ký và các ràng buộc của chứng chỉ hợp lệ;
- chứng chỉ đang trong thời gian hiệu lực;
- mục đích sử dụng phù hợp với TLS server authentication;
- thuật toán/độ mạnh khóa thỏa chính sách JDK;
- các điều kiện mở rộng khác tùy cấu hình xác minh.

**Chứng chỉ có SAN đúng nhưng không xây được chain đáng tin vẫn phải bị từ chối.** Ngược lại, certificate chain hợp lệ cho hostname khác cũng phải bị từ chối.

### 5.1. Root CA và intermediate CA

Root CA thường là trust anchor nằm trong truststore của JVM hoặc truststore riêng được phê duyệt. Server cần gửi leaf và intermediate thích hợp để client xây chain. Không phải server nào cũng gửi root certificate; đó không nhất thiết là lỗi.

Nếu server thiếu intermediate, Java có thể báo:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
Caused by:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

Hướng xử lý ưu tiên:
1. Xác minh server trả đúng chain.
2. Sửa cấu hình server để trả intermediate cần thiết.
3. Kiểm tra truststore thực sự của JVM.
4. Xác minh CA/trust anchor đúng với chính sách tổ chức.

Không import mọi chứng chỉ hiện thấy trên mạng vào truststore để dập lỗi.

### 5.2. Thời hạn chứng chỉ

Hai mốc `notBefore` và `notAfter` quyết định thời gian hiệu lực. Clock của container/VM lệch, leaf certificate hết hạn hoặc intermediate có vấn đề có thể dẫn đến failure.

Kiểm tra:
- thời gian thực tế của máy chạy JVM;
- đồng bộ NTP;
- expiry của leaf và intermediate;
- quy trình gia hạn và deploy chain.

Không thay đổi đồng hồ giả hoặc bỏ kiểm tra thời hạn để cho hệ thống kết nối.

### 5.3. Key usage và Extended Key Usage

Certificate dùng cho SMTP TLS server cần phù hợp với mục đích TLS server authentication theo chuẩn và policy mà Java áp dụng. Một chứng chỉ được thiết kế chỉ cho client authentication hoặc mục đích khác có thể không phù hợp.

Đừng suy ra chứng chỉ hợp lệ chỉ từ subject/issuer. Các extension `KeyUsage`, `ExtendedKeyUsage`, `BasicConstraints` và policy của trust manager cũng là một phần của xác minh.

### 5.4. Kiểm tra thu hồi chứng chỉ

Việc xác minh OCSP/CRL và các ràng buộc bổ sung **phụ thuộc chính sách, cấu hình và triển khai TLS**. Không nên mặc định khẳng định Jakarta Mail/JVM luôn kiểm tra thu hồi cho mọi kết nối.

Nếu tổ chức yêu cầu kiểm tra revocation, hãy thiết kế và kiểm thử cấu hình PKIX/JSSE tương ứng, bao gồm hành vi khi dịch vụ OCSP/CRL không truy cập được. Đặt chính sách rõ ràng, không coi `checkserveridentity=true` là cơ chế revocation.

## 6. JavaMailSender, Jakarta Mail và JSSE

Trong Spring Framework Mail, việc gửi MIME message thường diễn ra qua `JavaMailSender` hoặc `JavaMailSenderImpl`. Dưới tầng này, Jakarta Mail triển khai SMTP transport và sử dụng các cơ chế TLS của Java/JSSE.

Cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `JavaMailSender` | API gửi mail ở mức Spring. |
| `JavaMailSenderImpl` | Triển khai sender, nhận host/port/JavaMail properties. |
| Jakarta Mail SMTP Transport | Kết nối SMTP, EHLO, STARTTLS, AUTH, DATA. |
| Java JSSE | TLS handshake, chứng chỉ, trust manager, protocol/cipher. |
| Truststore | Tập trust anchor mà JVM/tổ chức chấp nhận. |
| Hostname verification | Kiểm tra server certificate có đại diện hostname cần kết nối không. |

### 6.1. Bật hostname verification một cách tường minh

Thuộc tính quan trọng:

```properties
mail.smtp.ssl.checkserveridentity=true
```

Jakarta Mail SMTP transport hỗ trợ kiểm tra server identity qua property này; không nên trông chờ mặc định của một bản thư viện hoặc một cách tạo socket cụ thể. Hãy bật tường minh và kiểm thử khi nâng cấp JDK/Jakarta Mail.

Tên property chứa `ssl` nhưng áp dụng cho xác thực identity của TLS connection được SMTP transport thiết lập, bao gồm cả TLS sau STARTTLS trong cấu hình tương ứng.

### 6.2. Hostname verification khác với truststore

`mail.smtp.ssl.checkserveridentity=true` không thêm CA vào truststore và không làm một chain không tin cậy trở thành hợp lệ.

Ngược lại, việc Java tin một CA không tự chứng minh SAN của certificate khớp với hostname. Do đó cần **cả trust path validation và hostname validation**.

### 6.3. Không dùng trust-all

Những cấu hình cần tránh trong production:

```properties
mail.smtp.ssl.trust=*
```

và custom `TrustManager` luôn chấp nhận mọi certificate.

Cách “cho tất cả pass” có thể che giấu server giả, chain sai hoặc CA không được phê duyệt. Kể cả khi hostname verification vẫn bật, bỏ qua chain validation là phá hỏng một nửa mô hình tin cậy.

Thay vì trust-all:
- sửa server certificate/chain;
- chọn đúng hostname;
- dùng CA nội bộ đã được xác minh và phân phối có kiểm soát;
- cấu hình truststore phù hợp;
- cập nhật JDK/trust anchors an toàn.

## 7. STARTTLS và implicit TLS: xác thực diễn ra lúc nào?

Cả hai mode đều cần certificate validation và hostname verification. Khác biệt là **thời điểm bắt đầu TLS**.

### 7.1. STARTTLS, thường trên port 587

```text
Application                      SMTP server :587
    |---------- TCP ----------------->|
    |<--------- 220 greeting ---------|
    |---------- EHLO ---------------->|
    |<--------- 250-STARTTLS ---------|
    |---------- STARTTLS ----------->|
    |<--------- 220 Ready -----------|
    |=========== TLS handshake ======|
    |       chain + hostname check   |
    |---------- EHLO (TLS) --------->|
    |---------- AUTH --------------->|
    |---------- MAIL FROM ... ------>|
```

Với SMTP submission cần TLS, cấu hình:
- `mail.smtp.starttls.enable=true`;
- `mail.smtp.starttls.required=true`;
- `mail.smtp.ssl.checkserveridentity=true`.

Chỉ bật `enable` mà không bắt buộc `required` có thể làm session tiếp tục không mã hóa ở những điều kiện server không hỗ trợ STARTTLS theo hành vi SMTP transport. Việc đó không phù hợp khi gửi credential và dữ liệu nhạy cảm cho provider yêu cầu TLS.

### 7.2. Implicit TLS, thường trên port 465

```text
Application                      SMTP server :465
    |---------- TCP ----------------->|
    |=========== TLS handshake ======|
    |       chain + hostname check   |
    |<--------- 220 greeting (TLS) ---|
    |---------- EHLO (TLS) --------->|
    |---------- AUTH --------------->|
    |---------- MAIL FROM ... ------>|
```

Với implicit TLS, thường dùng:
- `mail.smtp.ssl.enable=true`;
- `mail.smtp.ssl.checkserveridentity=true`.

Không cần dùng STARTTLS trong mode này. Nếu trộn sai mode/port, client có thể báo handshake failure, `wrong version number` hoặc `Unsupported or unrecognized SSL message`. Đó có thể là lỗi cấu hình transport chứ chưa chắc do certificate.

### 7.3. Port 25 không phải mặc định cho application submission

Port 25 thường xuất hiện trong chuyển tiếp giữa MTA hoặc relay nội bộ. Nhiều nhà mạng/cloud chặn outbound port 25. Không đoán rằng port 25 hoạt động giống 587 hoặc 465; chỉ dùng khi cấu hình provider/hạ tầng xác nhận và có chính sách TLS thích hợp.

## 8. Cấu hình Spring Boot: STARTTLS với kiểm tra server identity

Ví dụ `application.yml` cho SMTP submission qua port 587:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Các điểm chính:
- `spring.mail.host` là **hostname dự kiến**, phải được xác minh với SAN.
- `starttls.enable` cho phép nâng cấp từ SMTP sang TLS.
- `starttls.required` buộc TLS phải thành công.
- `ssl.checkserveridentity` bật kiểm tra danh tính server.
- Truststore/JSSE vẫn phải xác minh certificate chain.
- Timeout tính bằng mili giây theo SMTP transport; chọn giá trị phù hợp với hạ tầng.

Không bật `mail.smtp.ssl.enable=true` cho port 587 nếu SMTP provider dùng STARTTLS trên cổng này.

### 8.1. Chọn SMTP host từ cấu hình tin cậy

Không lấy hostname SMTP tùy ý từ người dùng rồi cho `JavaMailSender` kết nối để gửi thư. Host do client chọn có thể biến chức năng gửi mail thành một dạng **SSRF hoặc credential exfiltration**.

Với ứng dụng multi-tenant cần hỗ trợ nhiều SMTP provider:
- quản lý connector profile đã được admin xác thực;
- giới hạn host/port theo policy;
- xác minh và lưu cấu hình riêng từng tenant;
- kiểm soát DNS/IP/egress nếu có kết nối động;
- không cho cùng một tenant đọc secret/truststore của tenant khác;
- luôn giữ hostname verification cho từng endpoint.

## 9. Cấu hình Spring Boot: implicit TLS với kiểm tra hostname

Ví dụ port 465:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Ở đây TLS được bắt đầu ngay khi socket kết nối tới server. Không sử dụng `starttls.required` thay cho `ssl.enable`.

### 9.1. Không đánh đồng TLS mode với hostname verification

Bảng tổng hợp:

| Cấu hình | STARTTLS 587 | Implicit TLS 465 |
|---|---|---|
| `mail.smtp.starttls.enable` | `true` | Thường không cần |
| `mail.smtp.starttls.required` | `true` khi yêu cầu TLS | Thường không cần |
| `mail.smtp.ssl.enable` | Không bật cho STARTTLS-only endpoint | `true` |
| `mail.smtp.ssl.checkserveridentity` | `true` | `true` |
| Kiểm tra chain/truststore | Bắt buộc | Bắt buộc |
| Credential sau TLS đã xác thực | Bắt buộc theo policy | Bắt buộc theo policy |

Cổng thực tế phải theo tài liệu SMTP provider, không chỉ theo con số phổ biến.

## 10. Cấu hình JavaMailSenderImpl khi không dùng Spring Boot auto-configuration

Trong một ứng dụng Spring Framework tự cấu hình sender:

```java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

Ví dụ dùng STARTTLS port 587. Nếu SMTP provider yêu cầu implicit TLS port 465, thay cấu hình theo provider, bật `mail.smtp.ssl.enable=true` và giữ `checkserveridentity=true`.

Không hardcode password. Trong triển khai thật, cấp credential từ secret manager hoặc cấu hình môi trường được bảo vệ và có rotation. Không ghi environment variables, app passwords hoặc access tokens vào log.

### 10.1. Ví dụ gửi sau khi cấu hình TLS

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(
            String recipient,
            String subject,
            String plainText,
            String htmlText) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        // Kết nối, handshake và hostname verification
        // được thực hiện bởi SMTP transport/JSSE khi gửi.
        mailSender.send(message);
    }
}
```

`MimeMessageHelper` không chịu trách nhiệm tự kiểm tra certificate SAN. Đây là trách nhiệm của SMTP transport và TLS stack được cấu hình trong `JavaMailSenderImpl`. Không tự triển khai một bước so sánh CN bằng chuỗi để thay thế hostname verifier của TLS.

## 11. Truststore của JVM và certificate do CA nội bộ cấp

### 11.1. Truststore thực tế có thể khác trên từng môi trường

Java thường có tập trust anchors theo bản phân phối JDK và cấu hình JSSE. Một số yếu tố thay đổi kết quả:
- JDK vendor/version khác nhau;
- file `cacerts` khác nhau;
- container image cũ hơn laptop;
- JVM startup flags trỏ tới truststore tùy biến;
- proxy nội bộ thay certificate bằng certificate do CA doanh nghiệp ký;
- certificate chain bị thiếu intermediate;
- môi trường staging dùng CA riêng nhưng production dùng CA khác.

Các system properties JSSE thường gặp:

```text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

Việc một website hoặc `openssl` trên laptop tin certificate không chứng minh tiến trình Java trong container cũng tin. Cần kiểm tra **runtime thật** của ứng dụng.

### 11.2. Dùng CA nội bộ được phê duyệt

Nếu SMTP relay là server nội bộ có certificate do CA doanh nghiệp ký, có thể tạo truststore chuyên biệt theo chính sách tổ chức:

```bash
keytool -importcert \
  -alias approved-internal-smtp-ca \
  -file /secure/certs/approved-smtp-ca.pem \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Kiểm tra truststore:

```bash
keytool -list -v \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Lệnh có thể yêu cầu mật khẩu tương tác. Trước khi import, cần xác minh CA certificate bằng kênh đáng tin cậy với đội PKI/hạ tầng. Đừng tải certificate bất kỳ từ một endpoint đang bị lỗi rồi tin ngay certificate đó.

Khi cần chỉ định truststore:

```text
-Djavax.net.ssl.trustStore=/secure/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Cung cấp mật khẩu qua secret/launch configuration được quản lý an toàn nếu cần. Không đặt password plaintext trong source code hoặc command line được nhiều người nhìn thấy.

**Lưu ý:** những JSSE system properties này có thể ảnh hưởng các kết nối TLS khác trong cùng JVM. Một truststore tùy biến chỉ chứa CA nội bộ có thể vô tình loại bỏ public CAs cần cho các HTTP client khác. Phải đánh giá toàn bộ runtime; nếu cần isolation riêng, thiết kế cấu hình TLS/SSLContext theo giới hạn của stack đang sử dụng và kiểm thử đầy đủ.

### 11.3. Không import leaf certificate vô điều kiện

Import leaf certificate tạm thời có thể gây phụ thuộc vào một cert sẽ bị thay khi renewal. Khi provider đổi leaf/CA, hệ thống dễ lỗi lại.

Ưu tiên:
- dùng hệ thống public CA/JDK truststore cập nhật khi đó là provider public;
- dùng root/intermediate CA nội bộ đã được tổ chức phê duyệt khi đó là relay riêng;
- có kế hoạch CA rollover;
- không pin leaf nếu không có chính sách pinning và rollout phù hợp.

## 12. Chẩn đoán certificate và hostname bằng OpenSSL

OpenSSL giúp quan sát certificate mà endpoint trả về qua đúng đường mạng. Nên chạy từ **cùng server, container hoặc egress network** của ứng dụng nếu có thể, vì laptop cá nhân có thể đi qua DNS/proxy khác.

### 12.1. Kiểm tra STARTTLS trên port 587

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error \
  -showcerts
```

Các tùy chọn:
- `-starttls smtp`: nói chuyện SMTP và yêu cầu nâng cấp STARTTLS trước khi xác minh TLS.
- `-connect`: host/port mục tiêu.
- `-servername`: gửi SNI để server chọn certificate.
- `-verify_hostname`: đối chiếu hostname theo cơ chế kiểm tra của OpenSSL.
- `-verify_return_error`: không chỉ in lỗi verification mà yêu cầu fail khi không xác minh được.
- `-showcerts`: hiển thị certificates server gửi.

### 12.2. Kiểm tra implicit TLS trên port 465

```bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error \
  -showcerts
```

Không dùng `-starttls smtp` khi kết nối tới implicit TLS endpoint đang chờ ClientHello ngay từ đầu.

### 12.3. Đọc các trường quan trọng

Quan sát:
- Subject và Subject Alternative Name.
- Issuer.
- Certificate chain server trình ra.
- `notBefore` và `notAfter`.
- TLS protocol/cipher negotiated.
- Verification result.
- Lỗi handshake trước hoặc sau bước certificate.

Nếu công cụ trả `Verify return code: 0 (ok)`, điều đó chỉ xác nhận theo truststore/policy đang dùng của **OpenSSL**. Java vẫn có thể dùng một tập trust anchors khác.

Không nhập SMTP password hoặc token vào phiên debug để “thử nhanh”. Nếu cần kiểm tra AUTH, dùng công cụ/quy trình được tổ chức cho phép và bảo vệ output.

### 12.4. Tránh kiểm tra sai tên

Nếu app dùng `smtp.internal.example` nhưng người vận hành chạy:

```bash
openssl s_client \
  -connect smtp.internal.example:587 \
  -starttls smtp \
  -servername public-mail.example \
  -verify_hostname public-mail.example
```

thì kết quả có thể chỉ chứng minh endpoint trả cert hợp lệ cho `public-mail.example`, **không chứng minh cấu hình app dùng `smtp.internal.example` là đúng**. Đảm bảo `-verify_hostname` và SNI phản ánh hostname thực tế ứng dụng định xác thực, trừ khi đang cố tình điều tra mismatch ở một endpoint cụ thể.

## 13. Xác minh certificate chain bằng keytool và Java runtime

### 13.1. Xem danh sách trust anchors

Ví dụ nếu bạn có truststore chuyên biệt:

```bash
keytool -list -v \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Với truststore JVM mặc định, có thể dùng `keytool` để liệt kê `cacerts` theo hướng dẫn của JDK đang chạy. Không kết luận một CA “đã được tin” chỉ vì nó xuất hiện trong file `cacerts` của máy khác.

Cần đối chiếu:
- file truststore thực tế;
- JDK được ứng dụng chạy;
- CA/root fingerprint được tổ chức phê duyệt;
- issuer/chain của endpoint;
- quyền đọc file.

### 13.2. Bật JSSE debug khi cần

Có thể bật tạm thời JVM flags:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

Các cờ này giúp quan sát:
- handshake và phiên bản TLS;
- certificate chain đang được kiểm tra;
- trust manager có chấp nhận issuer/trust anchor không;
- điểm thất bại của path validation;
- tình huống không khớp certificate identity hoặc protocol/cipher.

Log JSSE có thể rất dài, chứa hostname/certificate metadata và thông tin kết nối. Chỉ bật trong môi trường kiểm soát, hạn chế quyền xem log và tắt sau khi xử lý.

### 13.3. Phân biệt debug OpenSSL và Java

| Công cụ | Có thể xác minh điều gì? | Giới hạn |
|---|---|---|
| `openssl s_client` | Chứng chỉ endpoint, SNI, protocol/cipher, verify theo OpenSSL | Không dùng đúng Java truststore/policy mặc định. |
| `keytool` | Nội dung keystore/truststore/certificate | Không tự chứng minh network path của app. |
| `javax.net.debug` | Handshake và quyết định JSSE của Java runtime | Log có thể dài; cần bảo vệ. |
| `JavaMailSenderImpl.testConnection()` | Kết nối sender thật với network/TLS/AUTH tùy config | Không gửi message, không chứng minh delivery. |
| Provider SMTP logs | Endpoint nào xử lý và phản hồi gì | Phụ thuộc quyền truy cập và retention. |

Kết hợp nhiều nguồn giúp phân biệt một lỗi Java truststore với một server đang đưa ra chain hoặc SAN sai.

## 14. Các lỗi thường gặp và cách phân loại

Khi Spring `send(...)` thất bại, exception ngoài có thể là `MailSendException`; cần đọc nguyên nhân lồng sâu như `MessagingException`, `SSLHandshakeException` hoặc `CertificateException`.

| Lỗi / triệu chứng | Khả năng thường gặp | Hướng xử lý |
|---|---|---|
| `PKIX path building failed` | Không xây được trust chain tới CA được JVM tin | Kiểm tra intermediate, CA, truststore, proxy. |
| `unable to find valid certification path` | Thiếu hoặc không tin trust anchor | Xác minh chain và JVM truststore thực tế. |
| `No subject alternative DNS name matching ...` | SAN không khớp hostname | Dùng hostname đúng hoặc cấp lại certificate có SAN phù hợp. |
| `No name matching ... found` | Hostname verification thất bại | Kiểm tra host, alias, CN/SAN theo implementation. |
| `CertificateExpiredException` | Certificate hết hạn | Gia hạn và deploy đúng chain, xác minh clock. |
| `CertificateNotYetValidException` | Certificate chưa hiệu lực hoặc đồng hồ lệch | Kiểm tra NTP và validity. |
| `Unsupported or unrecognized SSL message` | Nhầm implicit TLS với SMTP plaintext | Kiểm tra port và TLS mode. |
| `wrong version number` | Gửi TLS tới endpoint không chạy TLS ở thời điểm đó | Kiểm tra STARTTLS/implicit/proxy. |
| `handshake_failure` | Không thống nhất protocol/cipher hoặc cert policy | Kiểm tra JSSE/server logs, mTLS, TLS versions. |
| `protocol_version` | Một bên không hỗ trợ phiên bản TLS | Cập nhật relay/JDK và policy. |
| `no cipher suites in common` | Cipher suites không có tập hợp chung | Kiểm tra JDK disabled algorithms và relay. |
| `Connection reset` hoặc `EOFException` | Proxy/server ngắt kết nối; mode sai; network issue | Kiểm tra egress, SNI, server logs. |
| `STARTTLS is required but host does not support STARTTLS` | Server không quảng cáo STARTTLS | Kiểm tra đúng host/port, relay/gateway. |
| `530 Must issue STARTTLS first` | Client chưa nâng cấp TLS nhưng server yêu cầu | Bật STARTTLS mode đúng. |
| `535 Authentication failed` | TLS có thể đã thành công nhưng AUTH sai | Kiểm tra credential, OAuth2/app password, account policy. |

Đây là bảng khoanh vùng, không phải bộ luật phân loại tuyệt đối. `handshake_failure` có thể do nhiều nguyên nhân và phải đọc ngữ cảnh giao thức, log và thời điểm thất bại.

### 14.1. Trường hợp chain hợp lệ nhưng hostname sai

```text
Connected hostname: smtp.example.com

Certificate chain:
  Root CA: trusted
  Intermediate CA: trusted
  Leaf SAN: DNS:mail.other.example

Result: hostname mismatch
```

Không cần import thêm CA. Chain đã được tin; lỗi nằm ở **server identity**. Sửa hostname app hoặc certificate SAN của đúng relay.

### 14.2. Trường hợp SAN đúng nhưng CA không tin

```text
Connected hostname: smtp.example.com

Certificate:
  SAN: DNS:smtp.example.com
  Issuer: Internal Test CA

Java truststore:
  Internal Test CA not trusted

Result: PKIX path validation failed
```

Không sửa hostname vì hostname đã đúng. Cần xác minh Internal Test CA có được phê duyệt hay không, sau đó cấu hình trust anchor hoặc thay certificate server bằng chain được tin.

### 14.3. Trường hợp cả chain và SAN đúng nhưng vẫn lỗi

Các nguyên nhân khác có thể là:
- hết hạn/chưa hiệu lực;
- thuật toán yếu bị JDK từ chối;
- KeyUsage/ExtendedKeyUsage không phù hợp;
- mTLS client certificate được yêu cầu;
- protocol/cipher không tương thích;
- proxy/network reset;
- cert bị thu hồi theo policy được cấu hình;
- SNI/server farm có node trả cert khác khi test thực tế.

**Không kết luận kiểm tra SAN là nguyên nhân duy nhất của mọi handshake failure.**

## 15. Lỗi bảo mật khi cấu hình sai và cách phòng tránh

### 15.1. Tắt hostname verification để “cho chạy”

Nếu cấu hình `mail.smtp.ssl.checkserveridentity=false`, ứng dụng có thể chấp nhận certificate hợp lệ nhưng cho **hostname khác** theo hành vi SMTP transport. Việc này làm giảm bảo đảm chống server impersonation.

Không sửa sự cố bằng cách tắt property này. Hãy xử lý DNS/alias/certificate SAN đúng.

### 15.2. Tin mọi certificate

Dùng `mail.smtp.ssl.trust=*` hoặc trust manager chấp nhận tất cả certificate có thể cho phép chain không tin cậy vượt qua kiểm tra. Đây không phải lựa chọn an toàn cho production.

Không dùng trust-all để chữa `PKIX path building failed`. Nguồn certificate phải được xác minh bằng kênh tin cậy.

### 15.3. Bỏ STARTTLS required

Nếu relay yêu cầu TLS mà client chỉ đặt `starttls.enable=true`, trong một số trường hợp nó có thể tiếp tục SMTP không TLS khi capability bị thiếu. Điều này là rủi ro downgrade.

Hãy đặt `required=true` để fail closed và không gửi credential qua plaintext.

### 15.4. Hạ TLS protocol để vượt lỗi

Một số relay cũ chỉ hỗ trợ TLS 1.0/1.1 hoặc cipher yếu. Không nên nới lỏng `jdk.tls.disabledAlgorithms` hoặc ép protocol yếu chỉ để gửi được email.

Ưu tiên nâng cấp relay/provider hoặc dùng gateway được tổ chức phê duyệt, cấu hình TLS hiện đại và có kế hoạch thay thế.

### 15.5. Dùng certificate pinning không có kế hoạch rotation

Pinning leaf certificate có thể tăng kiểm soát trong môi trường đặc biệt, nhưng dễ gây outage khi cert rotate, có nhiều node hoặc nhà cung cấp đổi CA. Nếu tổ chức áp dụng pinning, phải có:
- cơ chế backup pin/rollover;
- quy trình phân phối/thu hồi;
- integration test;
- kế hoạch ứng phó khi certificate bị thay.

Với SMTP submission phổ biến, thường nên dựa vào hệ thống truststore CA đáng tin cùng hostname verification thay vì tự pin một leaf certificate tùy tiện.

## 16. Certificate từ reverse proxy và TLS interception

Một số tổ chức dùng SMTP gateway hoặc proxy để kiểm soát egress. Đường đi có thể là:

```text
Spring application
       |
       v
SMTP proxy / TLS inspection gateway
       |
       v
Provider SMTP server
```

TLS identity mà app thấy sẽ phụ thuộc proxy có thực sự terminate TLS hay passthrough:
- Nếu passthrough, app cần nhận đúng cert từ provider và kiểm tra hostname provider.
- Nếu proxy terminate TLS, app có thể thấy certificate của proxy, cần được phát hành và quản lý theo chính sách nội bộ với SAN phù hợp cho tên ứng dụng dùng.
- Nếu proxy thay cert bằng một CA nội bộ chưa được JVM tin, có thể gây PKIX.
- Nếu proxy dùng default certificate không khớp SNI, có thể gây hostname mismatch.

Không tự import cert “nhìn thấy trên đường đi” khi chưa xác minh với đội hạ tầng. Cần biết ai quản lý TLS termination, CA nào được phép và hostname nào là endpoint ứng dụng định tin.

### 16.1. Khi chỉ một số pod hoặc node bị lỗi

Một hostname có thể trỏ tới nhiều IP hoặc relay backend. Nếu một node dùng cert cũ/sai chain, lỗi sẽ ngẫu nhiên theo đường kết nối.

Nên thu thập:
- timestamp và pod/node;
- tên SMTP host, port, TLS mode;
- resolved DNS/IP (trong log quyền hạn phù hợp);
- certificate subject/SAN/issuer/fingerprint nếu phục vụ chẩn đoán;
- JSSE failure category.

Đối chiếu với đội provider để sửa đồng nhất certificate và chain trên tất cả nodes. Không tắt verification chỉ vì lỗi không liên tục.

## 17. Kiểm tra thực tế với Spring Mail

### 17.1. testConnection()

`JavaMailSenderImpl` có thể kiểm tra kết nối:

```java
JavaMailSenderImpl sender = ...;
sender.testConnection();
```

Hàm này có thể phát hiện lỗi TCP, TLS hoặc AUTH trong giai đoạn connect theo cấu hình sender. Tuy nhiên, nó **không gửi một email đầy đủ**, không kiểm tra MIME attachment và không đảm bảo delivery.

Nếu dùng Spring Boot, thuộc tính kiểm tra kết nối lúc startup có thể có trong một số phiên bản:

```yaml
spring:
  mail:
    test-connection: true
```

Cân nhắc kỹ: khi SMTP provider lỗi tạm thời, kiểm tra kết nối bắt buộc lúc khởi động có thể khiến ứng dụng không start được. Chỉ bật nếu đó là hành vi mong muốn của hệ thống.

### 17.2. Integration test với certificate hợp lệ và certificate sai

Một bộ test hữu ích nên kiểm tra ba tình huống:
1. Certificate do CA test được tin và SAN khớp hostname: connect thành công.
2. Certificate do CA test được tin nhưng SAN **không khớp**: connect thất bại.
3. Certificate có SAN đúng nhưng ký bởi CA **không tin**: connect thất bại.

Lưu ý:
- dùng SMTP TLS test server được quản lý trong CI/staging;
- cấp certificate test có SAN thích hợp;
- giữ truststore test độc lập, không ghi đè production truststore;
- chạy với đúng TLS mode (STARTTLS/implicit);
- không phải chỉ mock `JavaMailSender` vì mock không thực hiện JSSE handshake.

Thử thêm:
- certificate hết hạn;
- intermediate thiếu;
- STARTTLS không được quảng cáo với `required=true`;
- sai TLS mode;
- SNI trả certificate khác;
- nhiều endpoint load balanced;
- CA rollover.

### 17.3. Test lỗi phải không gửi credential/body

Với cert không đáng tin hoặc hostname mismatch, mong đợi kết nối không đi tiếp tới bước AUTH/MAIL FROM/DATA. Đây là tính chất bảo mật cần được xác minh trong integration test.

Không dùng một SMTP test server chấp nhận mọi certificate rồi suy ra production sẽ an toàn. Trong test có thể dùng CA tự tạo **được trust có chủ đích**; không dùng trust-all.

## 18. Runbook chẩn đoán hostname/certificate

Khi gặp lỗi TLS/certificate trong ứng dụng Spring Mail:

1. **Xác nhận endpoint**: ghi đúng `spring.mail.host`, port, TLS mode theo tài liệu provider.
2. **Xác nhận DNS/TCP**: kiểm tra app có thật sự tới đúng đường mạng không. TCP success không đồng nghĩa TLS success.
3. **Kiểm tra certificate trên đường đi**: dùng OpenSSL `s_client` với đúng STARTTLS/implicit mode, `-servername` và `-verify_hostname`.
4. **Đối chiếu SAN với host**: không kiểm tra nhầm domain người gửi, domain người nhận hoặc hostname proxy khác.
5. **Kiểm tra chain và thời hạn**: leaf, intermediate, trust anchor, EKU, validity.
6. **Kiểm tra JVM truststore**: đúng JDK/container, trustStore path/type/permission, CA được phê duyệt.
7. **Bật JSSE debug có giới hạn** nếu root cause chưa rõ: lấy protocol/cipher/certificate validation details.
8. **Kiểm tra proxy/SNI/load balancer**: có node nào cấp cert khác hoặc TLS interception hợp lệ không.
9. **Sửa đúng nguồn**: host/certificate/CA/chain/proxy/TLS mode; tuyệt đối không dùng trust-all hoặc plaintext fallback.
10. **Chạy testConnection và integration test** theo môi trường được phép.
11. **Khôi phục worker/backlog** với retry có kiểm soát; phân biệt lỗi handshake trước gửi với kết quả SMTP không rõ sau DATA.
12. **Cập nhật monitoring**: expiry, handshake errors, hostname mismatch và truststore drift.

### 18.1. Logging hữu ích nhưng không lộ dữ liệu

Nên ghi:
- message key và attempt ID;
- SMTP host alias/port/TLS mode;
- exception class và root cause category;
- thời điểm, service instance, JDK version;
- metric TLS handshake failure count.

Không nên ghi:
- mật khẩu SMTP, app password, OAuth token;
- AUTH exchange;
- nội dung body, attachment/Base64;
- reset/verification token trong URL;
- private key hoặc truststore password.

Nếu bật `mail.debug=true` hoặc Java `javax.net.debug`, giới hạn quyền truy cập vì debug log có thể chứa nhiều metadata hoặc thông tin nhạy cảm. Tắt sau khi điều tra.

## 19. Các tình huống vận hành đặc biệt

### 19.1. Certificate rotation

Provider có thể đổi certificate leaf hoặc intermediate. Nếu hệ thống dùng CA/truststore hợp lý và hostname không đổi, rotation thường có thể diễn ra ít gián đoạn hơn.

Chuẩn bị:
- monitor expiry trước hạn;
- biết CA hiện tại và CA dự kiến;
- kiểm thử chain mới từ staging;
- phân phối trust anchors theo kế hoạch nếu cần rollover;
- kiểm tra SAN vẫn bao phủ host mà app dùng;
- có phương án rollback an toàn nếu deploy sai cert.

Đừng chờ chứng chỉ hết hạn rồi mới tắt verification để khôi phục dịch vụ.

### 19.2. JDK upgrade

JDK mới có thể thay tập trust anchors hoặc cấm thuật toán TLS yếu. Một relay cũ từng kết nối được có thể bắt đầu lỗi sau khi nâng cấp JDK.

Trước upgrade:
- kiểm tra protocol/cipher và certificate chain của SMTP provider;
- chạy integration test với image/JDK mới;
- kiểm tra custom truststore/CA;
- nâng cấp relay nếu dùng thuật toán không còn an toàn.

Không sửa bằng cách vô hiệu hóa mặc định bảo mật của JDK trên toàn hệ thống nếu chưa có đánh giá và phê duyệt.

### 19.3. Mail relay mTLS

Ở relay doanh nghiệp yêu cầu **mutual TLS**, server không chỉ xuất trình certificate cho client mà còn yêu cầu client certificate.

Hai kiểm tra khác nhau:
- **Ứng dụng kiểm tra server**: chain + hostname của SMTP relay.
- **Relay kiểm tra client**: certificate và private key của ứng dụng theo policy relay.

Lỗi thiếu client certificate có thể hiện dưới dạng `certificate_required` hoặc `bad_certificate`, không đồng nghĩa SAN của server sai. Cần cấu hình client keystore/key material theo hướng dẫn quản trị SMTP; không vô hiệu hóa kiểm tra server để vượt qua lỗi mTLS.

### 19.4. Revoke hoặc thay CA nội bộ

Nếu một CA nội bộ bị thu hồi hoặc không còn được phê duyệt:
- cập nhật truststore theo quy trình PKI;
- thay certificate của các relay liên quan;
- kiểm soát thời gian phối hợp rollout;
- xác định hành vi fail closed;
- không để CA cũ tiếp tục tồn tại vô hạn chỉ để tránh outage.

### 19.5. Nhiều SMTP profiles

Trong ứng dụng có transactional và marketing sender khác nhau, mỗi profile phải có:
- hostname được xác nhận;
- TLS mode phù hợp;
- `checkserveridentity=true`;
- trust policy tương ứng;
- secret riêng nếu cần;
- logging/metric riêng cho kết nối.

Không lấy cấu hình an toàn của sender thứ nhất làm bằng chứng sender thứ hai cũng an toàn. Nếu có relay per-tenant, kiểm tra và cấp quyền cấu hình cho từng tenant.

## 20. Các lỗi thiết kế nên tránh

| Thói quen sai | Vì sao sai | Thay bằng |
|---|---|---|
| Chỉ bật TLS, không kiểm tra hostname | Có thể tin server có cert cho host khác | `mail.smtp.ssl.checkserveridentity=true`. |
| Dùng `mail.smtp.ssl.trust=*` | Bỏ qua trust chain, tăng rủi ro MITM | CA/truststore được xác minh. |
| Tắt hostname check khi SAN mismatch | Che giấu sai endpoint/certificate | Sửa host, DNS/SNI hoặc SAN. |
| Import certificate chưa xác minh từ endpoint lỗi | Có thể tin attacker certificate | Xác nhận fingerprint/CA qua kênh đáng tin cậy. |
| Kết nối IP trong khi certificate chỉ có DNS SAN | IP không nhất thiết khớp DNS SAN | Dùng hostname chính thức hoặc IP SAN phù hợp. |
| Đoán certificate theo sender/recipient domain | Đó không phải hostname submission | Kiểm tra `spring.mail.host`. |
| Dùng 465 với STARTTLS-only config | Sai thời điểm bắt đầu TLS | Dùng implicit TLS đúng cổng. |
| Dùng 587 với implicit TLS trên endpoint STARTTLS | Sai giao thức | Dùng STARTTLS + required. |
| Bỏ `starttls.required` để tiếp tục plaintext | Rủi ro downgrade và lộ dữ liệu | Fail closed khi yêu cầu TLS. |
| Xem OpenSSL verify OK là đủ cho Java | OpenSSL và JSSE có truststore khác nhau | Kiểm tra JDK/truststore thực tế. |
| Pin certificate leaf mà không có rollover | Outage khi rotation | Trust CA phù hợp hoặc pinning có kế hoạch. |
| Cho user nhập arbitrary SMTP host | Rủi ro SSRF/credential exfiltration | Admin-managed profile, allowlist, egress policy. |
| Dùng mock mail sender để khẳng định TLS an toàn | Mock không bắt tay TLS | Integration test có chứng chỉ và hostname thực. |
| Ghi đầy đủ SMTP debug vào log công khai | Dễ lộ host, recipient, token, secret | Debug hạn chế, lọc dữ liệu, tắt sau điều tra. |

## 21. Bài tập thực hành

### Bài 1 — Kiểm tra hai điều kiện độc lập

Cho ba certificate:
- Cert A: CA tin cậy, SAN khớp `smtp.example.com`.
- Cert B: CA tin cậy, SAN chỉ là `mail.other.example`.
- Cert C: SAN khớp `smtp.example.com`, nhưng CA không tin cậy.

Phân tích cert nào có thể được chấp nhận sau khi mọi điều kiện TLS khác cũng hợp lệ.

### Bài 2 — Bật hostname verification

Cấu hình Spring Boot dùng STARTTLS port 587, có `starttls.required=true` và `mail.smtp.ssl.checkserveridentity=true`. Giải thích khác biệt giữa hai property.

### Bài 3 — Implicit TLS

Chuyển cấu hình port 587 sang port 465 implicit TLS theo provider. Chỉ rõ property nào phải bật, property nào không còn cần, và tại sao hostname verification vẫn giữ nguyên.

### Bài 4 — SAN và wildcard

Certificate có `DNS:*.example.com`. Xác định các tên cần kiểm thử: `smtp.example.com`, `a.b.example.com`, `example.com` và `smtp.example.net`. Không giả định wildcard khớp vô hạn.

### Bài 5 — Host alias

App dùng `smtp.internal.example`, CNAME tới `relay.vendor.example`. Certificate chỉ có SAN `relay.vendor.example`. Hãy giải thích vì sao DNS alias không đủ, rồi đề xuất đổi hostname hoặc cấp SAN thích hợp.

### Bài 6 — OpenSSL và SNI

Chạy `openssl s_client` với đúng `-servername` và `-verify_hostname` ở SMTP sandbox. Quan sát kết quả khi đổi sang hostname không có trong SAN. Không nhập SMTP credential vào phiên chẩn đoán.

### Bài 7 — Java truststore khác OpenSSL

OpenSSL trên laptop xác minh thành công nhưng Java trong container báo PKIX. Hãy liệt kê các yếu tố cần đối chiếu: JDK image, truststore flags, CA bundle, proxy và certificate chain.

### Bài 8 — Internal CA

Dùng một CA test đã được tổ chức phê duyệt, import vào truststore PKCS12 chỉ dành cho test. Chứng minh cert có SAN đúng và CA được tin thì connect thành công, nhưng cert có SAN sai vẫn phải bị từ chối.

### Bài 9 — Test hostname mismatch

Dựng SMTP test server với certificate hợp lệ cho `smtp.test.local` nhưng client kết nối tên `wrong.test.local`. Kiểm tra `JavaMailSenderImpl.testConnection()` thất bại khi hostname verification bật.

### Bài 10 — Certificate rotation

Viết runbook thay leaf certificate, rồi thay intermediate/CA. Nêu bước chuẩn bị trust anchor, kiểm thử SAN, kiểm tra các node và rollback không làm yếu TLS.

### Bài 11 — Proxy TLS inspection

Một relay nội bộ chặn TLS và cấp certificate bằng Enterprise CA. Nêu các bước cần xác minh với đội hạ tầng trước khi tin CA đó; giải thích vì sao import cert ngẫu nhiên là không an toàn.

### Bài 12 — Khôi phục sự cố

Sau một lỗi hostname verification, còn nhiều job email chờ gửi. Hãy phân biệt các job chưa qua TLS handshake với job có kết quả submission không rõ, rồi thiết kế retry có giới hạn mà không gửi trùng không kiểm soát.

## 22. Tổng kết

**Kiểm tra hostname và chứng chỉ máy chủ** là điều kiện nền tảng khi bảo vệ SMTP submission bằng TLS trong Spring Framework Mail. Một kết nối chỉ đáng tin khi **certificate chain hợp lệ theo truststore/chính sách của JVM** và **server certificate thực sự đại diện hostname SMTP mà ứng dụng định kết nối**.

Để triển khai an toàn:
1. Dùng hostname SMTP chính thức và đối chiếu với `Subject Alternative Name`, không dựa vào domain người gửi hoặc người nhận.
2. Bật `mail.smtp.ssl.checkserveridentity=true` một cách tường minh.
3. Với STARTTLS, bật `starttls.enable=true` và `starttls.required=true` khi provider yêu cầu TLS; với implicit TLS, dùng `ssl.enable=true` đúng endpoint.
4. Giữ PKIX path validation và truststore đúng; không dùng `ssl.trust=*` hoặc trust manager chấp nhận mọi chứng chỉ.
5. Kiểm tra SNI, alias, IP, proxy và certificate chain khi gặp mismatch.
6. Chẩn đoán từ đúng Java runtime và đường mạng bằng OpenSSL, keytool, JSSE debug và `testConnection()`.
7. Quản lý certificate expiry, CA rollover và JDK update bằng integration test và runbook.

TLS mã hóa kết nối, còn **hostname và certificate validation bảo đảm kênh mã hóa đó được thiết lập với đúng SMTP server đáng tin cậy**. Không nên đánh đổi hai lớp kiểm tra này chỉ để làm cho việc gửi mail tạm thời thành công.
