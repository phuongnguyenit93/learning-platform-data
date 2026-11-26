# Chứng chỉ CA, TLS và xác minh máy chủ

## Mục tiêu bài học

Khi ứng dụng Spring hoặc một Kubernetes client gọi Kubernetes API qua HTTPS, kết nối chỉ an toàn khi client xác minh đúng máy chủ và trust chain. Biết địa chỉ API Server hoặc có token ServiceAccount chưa đủ. Client còn phải tin đúng CA, kiểm tra tên máy chủ trong chứng chỉ, dùng TLS version phù hợp và xử lý việc chứng chỉ được xoay vòng.

Bài thuộc chương **Kết nối Kubernetes API** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt CA, server certificate, private key, truststore và client credential.
- Mô tả quá trình TLS handshake giữa ứng dụng và Kubernetes API Server.
- Phân biệt kết nối in-cluster với kết nối từ máy ngoài cluster.
- Kiểm tra hostname, SAN, chain và thời hạn chứng chỉ.
- Cấu hình trust đúng cho Java client mà không tắt xác minh máy chủ.
- Phân biệt lỗi TLS với lỗi token, RBAC, DNS và NetworkPolicy.
- Chuẩn bị kế hoạch xoay vòng CA hoặc server certificate.

## 1. Vì sao HTTPS của Kubernetes API cần được hiểu đúng?

Kubernetes API Server thường được truy cập qua HTTPS. Khi một ứng dụng gửi request:

    Spring application
        → DNS hoặc địa chỉ API Server
        → TLS handshake
        → xác minh chứng chỉ
        → HTTP request có authentication
        → Kubernetes API Server

Có ít nhất ba lớp bảo vệ khác nhau:

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| DNS và mạng | Client có đến đúng endpoint không? | timeout, connection refused |
| TLS | Client có xác minh đúng máy chủ không? | unknown CA, hostname mismatch, expired |
| Authentication và authorization | Máy chủ có nhận diện và cho phép danh tính không? | 401, 403 |

Một token hợp lệ không sửa được lỗi unknown CA. Một CA đúng không cấp quyền RBAC. Một DNS đúng không bảo đảm chứng chỉ có SAN khớp hostname. Khi chẩn đoán, cần giữ ba lớp này tách biệt.

## 2. Các thành phần trong trust chain

### 2.1. Certificate Authority

CA là thực thể dùng private key để ký chứng chỉ. Client tin CA thông qua trust store hoặc CA bundle. Nếu server certificate được ký bởi CA mà client không tin, TLS handshake thất bại.

Trust chain có thể có:

    Root CA
        → Intermediate CA
            → Kubernetes API Server certificate

Client thường cần tin root hoặc CA phù hợp theo chính sách. Server cần gửi đủ intermediate certificate nếu chain yêu cầu.

### 2.2. Server certificate

Server certificate chứa public key, subject, thời hạn, issuer và Subject Alternative Name. Nó chứng minh endpoint đang trình bày identity được CA ký.

Client kiểm tra:

- chữ ký có dẫn đến CA được tin không;
- chứng chỉ còn hiệu lực không;
- hostname đang gọi có nằm trong SAN không;
- key usage và extended key usage có phù hợp không;
- chain có đầy đủ không.

Tên trong Common Name không nên được xem là thay thế SAN trong thiết kế hiện đại. Hostname cần xuất hiện trong SAN theo đúng dạng DNS hoặc IP mà client dùng.

### 2.3. Private key của máy chủ

Server private key phải được giữ tại API Server hoặc thành phần TLS termination. Client không cần và không được nhận private key của server để gọi API. Nếu một tài liệu yêu cầu copy server private key vào ứng dụng, đó là dấu hiệu thiết kế cần dừng lại và xem xét.

### 2.4. Truststore và CA bundle

Truststore chứa chứng chỉ CA mà client dùng để xác minh server. CA bundle có thể là một file PEM chứa nhiều certificate. Java thường dùng truststore dạng JKS hoặc PKCS12, nhưng thư viện HTTP client cũng có thể nhận PEM trực tiếp.

Truststore không chứa token. Nó trả lời câu hỏi “tôi tin CA nào”, còn token hoặc client certificate trả lời câu hỏi “tôi là ai”.

## 3. TLS handshake ở mức khái quát

Một handshake HTTPS thường gồm:

1. Client gửi ClientHello với TLS versions và cipher suites hỗ trợ.
2. Server gửi ServerHello và server certificate chain.
3. Client xác minh chain, thời hạn, SAN và chính sách key usage.
4. Hai bên thiết lập khóa phiên.
5. HTTP request được truyền trong kênh đã mã hóa.
6. Kubernetes API Server xác thực token, client certificate hoặc credential khác.
7. RBAC và admission policy quyết định request được phép làm gì.

TLS bảo vệ confidentiality và integrity của đường truyền. TLS server authentication giúp client biết đang nói chuyện với server nào. TLS không tự quyết định user được get ConfigMap hay watch EndpointSlice; đó là authentication và authorization.

## 4. Kết nối in-cluster

### 4.1. Service DNS của API Server

Pod chạy trong cluster thường dùng endpoint Kubernetes API được cung cấp qua Service và DNS của cluster. Tên cụ thể phụ thuộc cluster configuration và client library. Ứng dụng không nên ghi cứng một hostname tự suy đoán nếu client đã có cơ chế in-cluster configuration.

In-cluster configuration thường lấy:

- API server host và port từ môi trường hoặc cơ chế client;
- CA bundle từ filesystem được mount;
- ServiceAccount token từ volume hoặc token projection;
- namespace hiện tại từ file metadata nếu client hỗ trợ.

Các nguồn này phải được xem là ba loại dữ liệu khác nhau:

| Dữ liệu | Chức năng |
| --- | --- |
| API host/port | Địa chỉ kết nối |
| CA certificate | Trust server |
| ServiceAccount token | Authentication |

Không lấy token làm CA, không lấy CA làm token và không log nội dung của cả hai.

### 4.2. CA được mount vào Pod

Một Pod có thể nhận CA bundle qua volume do cluster cung cấp hoặc qua một cơ chế cấu hình được tổ chức chuẩn hóa. Client cần biết:

- file path thực tế;
- encoding PEM hay format khác;
- file có thể được cập nhật khi CA rotation không;
- process có đọc lại file không;
- permission của file có phù hợp không.

Nếu CA file được mount nhưng ứng dụng Java không được cấu hình trust manager để đọc file đó, file tồn tại cũng không làm handshake thành công.

### 4.3. ServiceAccount token không thay thế TLS

Token được gửi sau hoặc cùng lớp HTTP authentication trên một kết nối TLS. Nếu client tắt hostname verification để “dùng được token”, client có thể gửi credential đến endpoint giả mạo. Vì vậy, không tắt xác minh máy chủ để giải quyết lỗi certificate.

## 5. Kết nối từ ngoài cluster

Kết nối từ laptop, CI runner hoặc một hệ thống ngoài cluster cần nhiều thông tin hơn:

- endpoint API Server có thể truy cập;
- CA hoặc chain được tổ chức cấp;
- hostname client dùng phải khớp SAN;
- authentication credential;
- network route và firewall;
- proxy nếu có;
- context hoặc namespace mặc định.

Một kubeconfig có thể chứa cluster server URL, certificate-authority-data, client certificate, client key hoặc token. Kubeconfig là dữ liệu nhạy cảm nếu có private key hoặc credential; không commit vào repository và không đưa nguyên file vào log.

Khi chuyển kubeconfig giữa môi trường, không sửa server URL thành một địa chỉ khác mà không kiểm tra chứng chỉ. Thay đổi từ hostname sang IP có thể tạo hostname mismatch nếu IP không có trong SAN.

## 6. Hostname verification và SAN

### 6.1. Tên client gọi phải là tên certificate xác nhận

Giả sử certificate có SAN:

    DNS: kubernetes.default.svc
    DNS: kubernetes.default.svc.cluster.local

Nếu client gọi:

    https://kubernetes.default.svc

thì hostname có thể khớp. Nếu client gọi:

    https://10.0.0.1

thì chứng chỉ cũng cần có IP SAN 10.0.0.1, nếu không hostname verification thất bại.

Không sửa lỗi bằng cách tắt hostname verification. Hãy dùng hostname được cấp trong certificate hoặc cấp lại certificate có SAN đúng theo endpoint hợp lệ.

### 6.2. SNI

Server Name Indication cho phép client gửi hostname trong TLS handshake, đặc biệt quan trọng khi một proxy hoặc load balancer phục vụ nhiều certificate. Client cần giữ hostname thực tế thay vì kết nối bằng IP rồi tự đặt Host header.

HTTP Host header sau handshake không sửa được certificate đã được chọn trước đó. Nếu proxy định tuyến theo SNI, sai hostname có thể trả certificate của service khác hoặc lỗi handshake.

### 6.3. Proxy và TLS termination

Khi có proxy:

    client → TLS tới proxy → proxy → TLS hoặc HTTP tới API Server

Cần biết trust boundary nằm ở đâu:

- client có xác minh certificate của proxy không;
- proxy có xác minh certificate của API Server không;
- CA nào được dùng ở mỗi chặng;
- proxy có thay đổi hostname hoặc SNI không;
- audit và credential có đi qua proxy theo chính sách không.

Không gom CA của mọi hệ thống vào một truststore lớn chỉ để tránh lỗi. Truststore nên chứa CA cần thiết cho connection đó.

## 7. Java truststore và Spring

### 7.1. Truststore không phải keystore client

Trong Java:

- truststore chứa CA hoặc certificate mà client tin;
- keystore có thể chứa private key và certificate của chính client;
- client certificate dùng cho mutual TLS;
- token bearer thường là header HTTP, không phải truststore entry.

Một kết nối chỉ cần server authentication thường cần truststore. Mutual TLS cần thêm client key material và certificate chain.

### 7.2. PEM, JKS và PKCS12

Các định dạng thường gặp:

| Định dạng | Nội dung thường gặp | Lưu ý |
| --- | --- | --- |
| PEM | Certificate hoặc key dạng text base64 | Có thể chứa nhiều certificate |
| JKS | Java keystore/truststore | Định dạng Java truyền thống |
| PKCS12 | Container chuẩn hơn cho key và certificate | Có thể dùng cho keystore/truststore |

Đổi đuôi file không chuyển đổi định dạng. Một file PEM không trở thành PKCS12 chỉ vì được đặt tên .p12.

### 7.3. Cấu hình theo một connection

Ứng dụng có thể có nhiều HTTP client: client gọi Kubernetes API, client gọi database proxy, client gọi downstream nghiệp vụ. Không nên sửa global JVM truststore để thêm CA của một connection nếu điều đó mở rộng trust cho mọi connection.

Ưu tiên trust configuration theo client hoặc connection khi framework hỗ trợ:

- chỉ nạp CA cần thiết;
- tách timeout và proxy;
- tách metric;
- tránh ảnh hưởng outbound connection khác;
- kiểm soát rotation độc lập.

Tên property và cách cấu hình cụ thể phụ thuộc HTTP client, Spring Boot, Spring Cloud Kubernetes và release đang dùng. Cần đối chiếu bộ phiên bản thực tế, không sao chép thuộc tính từ dòng version khác.

## 8. Mutual TLS và client certificate

Một số cluster hoặc proxy yêu cầu client certificate. Khi đó:

    client certificate + client private key
        → server xác minh identity client
    server certificate + CA
        → client xác minh identity server

Đây là mutual TLS. Client private key phải được bảo vệ chặt:

- không commit vào source;
- không ghi vào log;
- permission file tối thiểu;
- rotation có lịch;
- không dùng chung key cho nhiều workload nếu không cần.

Mutual TLS không thay thế RBAC. Server có thể xác thực certificate nhưng vẫn từ chối request vì user hoặc group chưa có quyền.

## 9. Kiểm tra chứng chỉ bằng cách an toàn

### 9.1. Kiểm tra certificate metadata

Cần kiểm tra:

- Subject;
- Issuer;
- Not Before;
- Not After;
- Subject Alternative Name;
- Key Usage;
- Extended Key Usage;
- chain;
- fingerprint theo quy trình tin cậy.

Không gửi private key vào công cụ kiểm tra hoặc chat. Chứng chỉ public vẫn cần xử lý theo chính sách nếu chứa thông tin hạ tầng nhạy cảm.

### 9.2. Kiểm tra từ cùng network path

Certificate có thể đúng từ laptop nhưng sai từ Pod vì hai nơi dùng hostname, proxy hoặc CA khác nhau. Kiểm tra nên phản ánh đường đi thực:

    cùng namespace
    cùng Pod hoặc network policy
    cùng hostname
    cùng CA bundle
    cùng proxy mode

Một test thành công từ bên ngoài cluster không chứng minh Pod gọi được API Server.

### 9.3. Kiểm tra thời gian

TLS phụ thuộc đồng hồ. Nếu node hoặc container có clock lệch:

- certificate có thể bị xem là chưa có hiệu lực;
- certificate đã hết hạn sớm;
- log timestamp gây nhầm thứ tự.

NTP và time synchronization là điều kiện nền tảng. Không kéo dài NotAfter hoặc bỏ kiểm tra thời gian để che lỗi clock.

## 10. Phân loại lỗi TLS

| Triệu chứng | Nguyên nhân thường gặp | Cách phân biệt |
| --- | --- | --- |
| Unknown CA | Truststore thiếu CA hoặc chain thiếu | Client không xác minh issuer |
| Certificate expired | NotAfter đã qua hoặc clock sai | Kiểm tra thời gian hai phía |
| Not yet valid | NotBefore ở tương lai hoặc clock sai | So sánh clock và certificate |
| Hostname mismatch | Hostname không nằm trong SAN | Đối chiếu URL với SAN |
| Certificate path error | Intermediate thiếu hoặc chain sai | Kiểm tra toàn bộ chain |
| Handshake failure | TLS version, cipher, key usage hoặc mTLS | Xem negotiated protocol và server policy |
| Connection refused | Không có listener hoặc port sai | Lỗi TCP trước TLS |
| Timeout | DNS, route, NetworkPolicy hoặc proxy | Không có handshake hoàn tất |
| 401 | TLS đã qua, authentication thất bại | Đọc HTTP response |
| 403 | TLS và authentication đã qua, thiếu RBAC | Kiểm tra ServiceAccount và Role |

Một exception Java có thể bọc nhiều cause. Hãy giữ chain nội bộ để phân biệt SSLHandshakeException, SSLPeerUnverifiedException, UnknownHostException, ConnectException và HTTP status exception.

## 11. Quy trình chẩn đoán theo tầng

### Tầng 1: endpoint và DNS

Xác nhận hostname và port mà client thực sự dùng. Kiểm tra hostname từ cùng môi trường chạy ứng dụng. Nếu DNS không phân giải, chưa cần điều tra CA.

### Tầng 2: TCP

Xác nhận có kết nối đến port API Server hoặc proxy không. Connection refused thường là listener, port hoặc route. Timeout có thể là NetworkPolicy, firewall hoặc endpoint không thể truy cập.

### Tầng 3: TLS

Nếu TCP kết nối nhưng handshake thất bại, kiểm tra:

- CA bundle;
- server certificate chain;
- hostname và SAN;
- thời gian;
- TLS version và cipher policy;
- client certificate nếu mutual TLS;
- SNI và proxy.

### Tầng 4: HTTP authentication

Nếu nhận 401, TLS đã hoàn tất nhưng credential không được chấp nhận. Kiểm tra token hoặc client certificate theo cơ chế cấp phát, không thay đổi truststore để sửa 401.

### Tầng 5: RBAC

Nếu nhận 403, danh tính đã qua authentication nhưng thiếu quyền. Kiểm tra resource, verb, namespace, RoleBinding và ServiceAccount.

### Tầng 6: application integration

Nếu API trả 200 nhưng Spring không có property hoặc instance:

- kiểm tra module integration;
- namespace và tên resource;
- mapping dữ liệu;
- cache;
- watch hoặc refresh;
- bean lifecycle.

## 12. CA rotation và vòng đời chứng chỉ

### 12.1. Xoay vòng có thể tác động ở nhiều nơi

CA hoặc server certificate có thể được thay mới vì hết hạn, thay đổi policy hoặc sự cố bảo mật. Các thành phần cần phối hợp:

    CA issuer
        → API Server certificate
        → proxy hoặc load balancer
        → in-cluster CA bundle
        → Java truststore hoặc mounted file
        → client reload

Nếu client chỉ tin CA cũ, handshake sẽ thất bại sau rotation. Nếu truststore chỉ được đọc khi JVM khởi động, Pod cần rollout hoặc cơ chế reload được thư viện hỗ trợ.

### 12.2. Overlap trong rotation

Một chiến lược an toàn thường có giai đoạn overlap:

1. Phân phối CA mới cho client nhưng vẫn giữ CA cũ.
2. Xác nhận client tin được chain mới.
3. Thay server certificate bằng chain mới.
4. Theo dõi handshake error.
5. Loại CA cũ sau khi mọi client đã cập nhật.

Chiến lược cụ thể phụ thuộc cluster, certificate manager, proxy và chính sách bảo mật. Không xóa CA cũ trước khi biết mọi client đã nạp CA mới.

### 12.3. Rotation trong Pod

Nếu CA mount qua volume có thể được cập nhật, cần biết client có:

- đọc file mỗi request;
- reload SSLContext;
- chỉ đọc một lần khi khởi động;
- cache trust manager;
- cần restart Pod.

File đã đổi không đồng nghĩa JVM đã dùng file mới. Hãy kiểm chứng bằng một kết nối thực tế hoặc metric handshake an toàn.

## 13. Trust store tối thiểu và tránh trust quá rộng

Trust store chứa càng nhiều CA thì phạm vi server được tin càng rộng. Một trust store global chứa CA của mọi môi trường có thể khiến ứng dụng chấp nhận endpoint không nên được tin.

Nguyên tắc:

- tách CA theo môi trường;
- tách truststore theo connection khi cần;
- dùng fingerprint hoặc inventory có owner;
- kiểm tra NotAfter trước khi deploy;
- không bỏ hostname verification;
- không dùng trust-all manager trong production.

Một cấu hình “trust tất cả certificate” có thể làm test local chạy nhưng loại bỏ mục tiêu xác thực server. Nếu cần test với CA tự ký, hãy cấp CA test vào truststore riêng.

## 14. CA, token và RBAC trong Spring Cloud Kubernetes

Khi Spring Cloud Kubernetes gọi API:

    CA → xác minh API Server
    token hoặc client certificate → xác thực workload
    RBAC → quyết định quyền
    integration → map response vào discovery/config

Một lỗi ở mỗi lớp có triệu chứng khác:

| Thành phần | Lỗi ví dụ | Không nên sửa bằng |
| --- | --- | --- |
| CA hoặc hostname | SSL handshake failure | đổi token hoặc cấp cluster-admin |
| Token | 401 | thêm CA hoặc tắt hostname verification |
| RBAC | 403 | trust-all hoặc retry vô hạn |
| Integration mapping | instance rỗng hoặc property thiếu | mở quyền toàn cluster ngay lập tức |

Giữ các lớp tách biệt giúp thay đổi đúng nơi và giảm rủi ro.

## 15. Proxy, load balancer và endpoint API

Kubernetes API có thể được đặt sau load balancer hoặc reverse proxy. Khi đó cần biết:

- certificate được cấp cho hostname nào;
- proxy có terminate TLS không;
- client có cần CA của proxy hay CA của API Server;
- SNI được chuyển tiếp ra sao;
- proxy có yêu cầu client certificate không;
- path và HTTP method có bị rewrite không.

Nếu client gọi IP của load balancer nhưng certificate được cấp cho api.cluster.example, hostname mismatch là kết quả đúng. Cách sửa là dùng endpoint hostname hợp lệ hoặc cấp certificate có SAN phù hợp, không tắt verify.

## 16. Cấu hình timeout và bảo vệ lỗi

TLS handshake có thể chậm do DNS, proxy hoặc server load. Client cần:

- connect timeout;
- handshake hoặc read timeout;
- request timeout;
- giới hạn số lần retry;
- circuit breaker hoặc bulkhead nếu API nằm trên đường request;
- metric latency riêng cho Kubernetes API.

Không để request nghiệp vụ chờ vô hạn vì API Server. Với discovery hoặc config background, có thể dùng cache và fallback theo chính sách. Với cấu hình Secret bắt buộc, fallback phải được đánh giá về bảo mật và tính đúng.

## 17. Những hiểu nhầm thường gặp

**“Có ServiceAccount token là gọi được API.”** Token chỉ liên quan authentication. Client vẫn cần kết nối mạng, trust CA, hostname đúng và RBAC phù hợp.

**“CA certificate là private key.”** CA public certificate dùng để xác minh chữ ký. Private key của CA hoặc server phải được bảo vệ và không đưa vào Pod client.

**“Tắt hostname verification chỉ ảnh hưởng kiểm tra tên.”** Nó làm giảm khả năng client phát hiện endpoint giả mạo hoặc proxy sai, đặc biệt khi credential được gửi trong cùng kết nối.

**“Đổi hostname thành IP sẽ tránh lỗi DNS.”** Có thể tạo hostname mismatch nếu IP không nằm trong SAN và còn làm mất lợi ích của SNI.

**“Unknown CA là lỗi RBAC.”** Unknown CA xảy ra trước HTTP authentication và authorization. Cần sửa trust chain.

**“Thấy HTTP 403 nghĩa là TLS sai.”** 403 chứng minh request đã đi qua TLS và authentication đủ để server nhận diện danh tính; cần điều tra RBAC hoặc admission policy.

**“Mounted CA file đổi là JVM tự reload.”** Behavior phụ thuộc client và SSLContext. Có thể cần reload riêng hoặc rollout.

**“Một truststore dùng cho mọi outbound connection là đơn giản nhất.”** Nó mở rộng trust boundary và làm rotation khó kiểm soát. Tách theo connection khi phạm vi tin cậy khác nhau.

## 18. Checklist kết nối TLS đến Kubernetes API

### Endpoint và DNS

- [ ] Hostname và port là endpoint được cluster hoặc proxy cấp.
- [ ] Hostname dùng trong URL nằm trong SAN của server certificate.
- [ ] DNS và route hoạt động từ đúng môi trường chạy ứng dụng.
- [ ] SNI và proxy mode đã xác định.

### Trust

- [ ] Client nạp đúng CA bundle hoặc truststore.
- [ ] Chain có đủ intermediate cần thiết.
- [ ] Certificate còn hiệu lực và clock được đồng bộ.
- [ ] Truststore không chứa CA ngoài phạm vi cần thiết.
- [ ] Hostname verification vẫn được bật.

### Identity và quyền

- [ ] Token hoặc client certificate được cấp đúng cách.
- [ ] Private key không nằm trong source hoặc log.
- [ ] ServiceAccount đúng với Pod.
- [ ] Role và RoleBinding cấp đúng resource, verb, namespace.

### Vận hành

- [ ] Connect, handshake và request timeout có giới hạn.
- [ ] Lỗi TLS, 401 và 403 được phân biệt.
- [ ] Có metric cho handshake failure và certificate expiry.
- [ ] Có kế hoạch CA/server certificate rotation.
- [ ] Client biết có cần reload truststore hoặc rollout không.

## 19. Tự kiểm tra mức độ hiểu

**Câu 1: CA dùng để làm gì khi client gọi Kubernetes API?**

CA giúp client xác minh server certificate và trust chain. CA không cấp quyền đọc resource và không thay thế token hoặc client certificate.

**Câu 2: Vì sao hostname phải khớp SAN?**

Vì certificate cần xác nhận identity của endpoint mà client đang gọi. Nếu client gọi hostname hoặc IP không nằm trong SAN, việc từ chối là cần thiết để chống kết nối nhầm hoặc giả mạo.

**Câu 3: Unknown CA và 403 khác nhau ở đâu?**

Unknown CA xảy ra trong TLS handshake trước HTTP. 403 là response HTTP sau khi TLS và authentication đã qua nhưng danh tính thiếu quyền.

**Câu 4: Vì sao không nên copy server private key vào ứng dụng?**

Client chỉ cần public certificate hoặc CA để xác minh server. Server private key là bí mật của server; copy nó làm mở rộng rủi ro nghiêm trọng.

**Câu 5: CA rotation có thể làm gì?**

Nếu client không nạp CA mới hoặc chỉ đọc truststore khi startup, handshake có thể thất bại sau khi server dùng certificate chain mới. Cần overlap, reload hoặc rollout theo kế hoạch.

**Câu 6: Có thể sửa hostname mismatch bằng cách tắt verify không?**

Không. Cần dùng hostname hợp lệ trong SAN hoặc cấp certificate đúng endpoint. Tắt verify làm suy yếu xác thực server và có thể làm lộ credential.

## Kết luận

Kết nối đến Kubernetes API cần đồng thời đúng endpoint, đúng trust chain, đúng hostname, đúng credential và đúng RBAC. CA giúp xác minh server; token hoặc client certificate xác minh client; RBAC quyết định client được làm gì. Ba lớp này bổ sung cho nhau và không thể thay thế lẫn nhau.

Java client và Spring Cloud Kubernetes cần được cấu hình để đọc CA đúng định dạng, giữ hostname verification, giới hạn timeout và xử lý rotation. Khi gặp lỗi, hãy chẩn đoán theo thứ tự DNS và TCP, TLS, HTTP authentication, RBAC rồi integration. Cách phân tầng này giúp sửa đúng nguyên nhân mà vẫn giữ được tính an toàn của kết nối.
