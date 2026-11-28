# Mục tiêu của TLS trong bảo vệ đường truyền

## 1. TLS bảo vệ điều gì?

**Transport Layer Security (TLS)** là một họ giao thức mật mã dùng để thiết lập một kênh liên lạc được bảo vệ giữa hai đầu tham gia giao tiếp. Trên Internet, ví dụ quen thuộc nhất là **HTTPS**: ứng dụng HTTP được truyền qua một kết nối có TLS, nhằm hạn chế việc người ngoài đọc hoặc sửa dữ liệu khi dữ liệu đang đi giữa trình duyệt và máy chủ được xác thực.

Ba **mục tiêu an ninh cốt lõi** của TLS là:

1. **Tính bí mật (confidentiality):** bảo vệ nội dung trao đổi khỏi bị đọc bởi người quan sát đường truyền không nắm khóa phiên phù hợp.
2. **Tính toàn vẹn (integrity):** phát hiện những thay đổi trái phép đối với dữ liệu được bảo vệ trong quá trình truyền.
3. **Xác thực bên giao tiếp (authentication):** giúp một hoặc cả hai phía kiểm tra danh tính mật mã của bên kia theo cơ chế xác thực được chọn, chẳng hạn xác minh chứng chỉ máy chủ và tên miền trong TLS dùng PKI.

Ba mục tiêu này tạo nền tảng cho **bảo vệ trước nghe lén và tấn công xen giữa đường truyền (man-in-the-middle, MITM)** trong những điều kiện triển khai đúng. TLS **không tự bảo đảm tính sẵn sàng** khi xảy ra DDoS, không bảo đảm endpoint không bị xâm nhập, không tự phân quyền người dùng cho ứng dụng, và không mã hóa toàn bộ thông tin mạng ở mọi lớp.

Trong module **SECURITY_NETWORK_SECURITY**, hiểu TLS giúp liên kết các lớp phòng vệ: firewall và segmentation xác định đường được phép; DNS tìm địa chỉ dịch vụ; VPN bảo vệ một phạm vi kết nối; IDS/IPS giám sát traffic trong giới hạn nhìn thấy; Wi-Fi bảo vệ chặng vô tuyến; còn TLS giúp bảo vệ **nội dung và danh tính hai đầu kênh truyền** giữa những thành phần ứng dụng được thiết kế.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Diễn giải confidentiality, integrity, authentication bằng kịch bản mạng và phân biệt chúng với authorization, availability.
- Mô tả ranh giới **TLS endpoint**, handshake, chứng chỉ X.509, trust chain và khóa phiên.
- Hiểu vai trò của TLS 1.3, AEAD, trao đổi khóa tạm thời và forward secrecy; phân biệt điểm chính với TLS 1.2.
- Giải thích khác biệt giữa **TLS một chiều (server-authenticated)** và **mutual TLS (mTLS)**.
- Phân tích rủi ro DNS giả mạo, MITM, chứng chỉ sai, downgrade, TLS termination và traffic mã hóa đối với IDS/IPS.
- Đưa ra checklist cấu hình, quan sát kết nối bằng lệnh chỉ đọc và xây dựng bộ kiểm thử an toàn.

> **Giới hạn thực hành:** ví dụ dùng tên miền và địa chỉ IP của phòng lab/tài liệu như `api.lab.example.test` và `192.0.2.20`. Không truy cập, quét hoặc kiểm thử TLS đối với tài sản ngoài quyền quản trị. Các ví dụ lệnh chỉ dùng để **quan sát hoặc thực hiện một kết nối kiểm tra có phép**, không vô hiệu hóa xác minh chứng chỉ.

## 2. Bài toán: điều gì xảy ra nếu đường truyền không được bảo vệ?

Giả sử một nhân viên đăng nhập ứng dụng nội bộ qua một tuyến gồm Wi-Fi, gateway, mạng doanh nghiệp, ISP và máy chủ. Nếu nội dung **không được mã hóa**, một thiết bị có khả năng quan sát gói trên một chặng phù hợp có thể đọc các trường và dữ liệu ứng dụng gửi ở dạng rõ. Nếu thiếu cơ chế kiểm tra tính toàn vẹn, một đối thủ kiểm soát điểm chuyển tiếp còn có thể **sửa thông điệp**. Nếu ứng dụng không xác minh danh tính máy chủ, client có thể bị hướng tới một máy chủ giả.

~~~mermaid
flowchart LR
    C["Client"] --> W["Wi-Fi / Switch"]
    W --> R["Router / ISP"]
    R --> S["Máy chủ ứng dụng"]
    X["Bên quan sát hoặc kiểm soát một chặng"] -. "Có thể đọc/chỉnh traffic không được bảo vệ" .-> R
~~~

TLS được thiết kế để làm cho việc **đọc/sửa nội dung kênh hoặc giả mạo bên đích** trở nên khó khăn khi kẻ tấn công chỉ kiểm soát đường truyền, nhưng không có bí mật mật mã cần thiết và không thể vượt qua chính sách xác thực endpoint.

### 2.1. Ba tình huống tương ứng ba mục tiêu

| Rủi ro | Ví dụ | Cơ chế TLS hướng đến |
|---|---|---|
| **Eavesdropping** | Quan sát nội dung API request và response ở một router trung gian | Mã hóa dữ liệu bằng khóa phiên |
| **Tampering** | Sửa số tiền trong response hoặc nội dung body đang truyền | Mã xác thực/tính toàn vẹn gắn với bản ghi mã hóa |
| **Endpoint impersonation** | Đưa người dùng đến một máy chủ giả mang tên ứng dụng | Xác thực danh tính máy chủ, chứng chỉ và tên dịch vụ |

**Cần phân biệt:** TLS xác thực chứng chỉ và khóa gắn với một danh tính dự kiến **không có nghĩa** nội dung do máy chủ trả về luôn đúng về mặt nghiệp vụ, hoặc mã JavaScript từ máy chủ không có lỗi bảo mật.

## 3. TLS nằm ở đâu so với TCP, HTTP, Wi-Fi và VPN?

Một mô hình phổ biến cho HTTPS qua TCP là:

~~~text
Ứng dụng              HTTP request / response
TLS                   Handshake + protected application records
Vận chuyển             TCP
Mạng                   IP (IPv4 / IPv6)
Liên kết               Ethernet / Wi-Fi / mạng khác
~~~

Mô hình này hữu ích để học nhưng không mô tả mọi sản phẩm:

- **HTTPS qua HTTP/1.1 hoặc HTTP/2** thường sử dụng TLS trên TCP.
- **HTTP/3** sử dụng **QUIC trên UDP**; QUIC tích hợp TLS 1.3 để bắt tay và thiết lập khóa, nhưng **không truyền dữ liệu QUIC qua tầng TLS record thông thường**.
- **DTLS** là họ giao thức liên quan dành cho những ngữ cảnh datagram như UDP, có cách xử lý khác với TLS trên stream TCP.
- **Wi-Fi WPA2/WPA3** mã hóa chặng radio client–AP; sau AP, dữ liệu có thể đi qua những mạng khác.
- **IPsec VPN** bảo vệ một hoặc nhiều đoạn lưu lượng IP theo chính sách tunnel, không đồng nhất với TLS cho một ứng dụng.

~~~mermaid
flowchart LR
    C["Trình duyệt"] <-->|"WPA2/WPA3: chặng Wi-Fi"| AP["Access Point"]
    AP --> FW["Firewall / Router"]
    FW --> LB["Load Balancer / TLS endpoint"]
    LB --> APP["Application"]
    C -. "TLS/HTTPS: tới endpoint TLS được xác thực" .-> LB
    LB -. "Có thể cần TLS khác tới APP" .-> APP
~~~

**Ranh giới bảo vệ:** nếu load balancer kết thúc TLS, dữ liệu **được giải mã tại load balancer**. Đoạn tiếp theo từ LB tới application **chỉ được TLS bảo vệ nếu có một kết nối TLS khác**, hoặc một cơ chế bảo mật khác được thiết kế cụ thể cho đoạn đó. Không được suy toàn bộ client → database được mã hóa chỉ vì trình duyệt hiển thị biểu tượng HTTPS.

## 4. Mục tiêu thứ nhất: Confidentiality — giữ bí mật nội dung

### 4.1. Mã hóa đối xứng sau khi thiết lập khóa

TLS thường dùng mật mã **đối xứng** để bảo vệ application data sau handshake. Hai phía thiết lập/đạo xuất các khóa phiên và dùng chúng để biến plaintext thành ciphertext theo chế độ mật mã phù hợp. Người chỉ nhìn thấy packet trên đường truyền có thể quan sát **ciphertext**, nhưng không thể đọc lại plaintext nếu không có những khóa và khả năng phá vỡ giả định mật mã.

Các bộ mã hóa hiện đại dùng **AEAD (Authenticated Encryption with Associated Data)**, ví dụ AES-GCM hoặc ChaCha20-Poly1305 trong những cipher suite được hỗ trợ. AEAD kết hợp mã hóa với xác thực tính toàn vẹn và giúp phát hiện việc sửa nội dung được bảo vệ.

~~~text
Client TLS endpoint                       Server TLS endpoint
-------------------                       -------------------
Plaintext: "GET /account"                  (chưa nhận)
      |                                      ^
      v                                      |
AEAD encrypt (key, nonce, data)         AEAD decrypt / verify
      |                                      ^
      +---- ciphertext + authentication tag -+
                  qua TCP/IP / mạng
~~~

Đây là mô hình khái niệm. Việc phân mảnh, record metadata, nonce và key schedule phải theo đúng đặc tả TLS; **không tự tạo giao thức mã hóa riêng** dựa trên sơ đồ.

### 4.2. Confidentiality áp dụng đến đâu?

Khi TLS kết thúc tại reverse proxy, hệ thống đó là **một bên thấy plaintext**. Ở những kiến trúc có TLS inspection được phê duyệt, thiết bị trung gian cố ý trở thành endpoint một hoặc nhiều kết nối TLS và có thể quan sát nội dung đã giải mã; đây không phải điều một router thụ động bất kỳ đều làm được.

Những người có quyền trên **client, server, reverse proxy, hệ thống log hoặc bộ nhớ ứng dụng** vẫn có thể nhìn thấy plaintext ở các điểm xử lý tương ứng. TLS không ngăn ứng dụng tự ghi token vào log hoặc gửi dữ liệu bí mật cho một endpoint độc hại **được người dùng tin nhầm**.

### 4.3. Dữ liệu nào có thể vẫn lộ?

| Thành phần | Có thể quan sát từ đường mạng? | Ghi chú |
|---|---|---|
| IP nguồn/đích, thông tin định tuyến | Thường có | TLS không mã hóa IP header của gói |
| TCP/UDP ports, kích thước, timing | Thường có | Có thể dùng phân tích traffic pattern |
| SNI trong ClientHello thông thường | Thường thấy nếu không sử dụng ECH | **Encrypted ClientHello (ECH)** có thể bảo vệ một phần thông tin ClientHello khi được hỗ trợ |
| DNS query | Tùy DNS dùng plaintext hay DoT/DoH/DoQ | TLS của HTTPS **không tự mã hóa DNS riêng** |
| HTTP path, cookie, Authorization và body | Được bảo vệ trong kết nối HTTPS đúng | Không được đưa vào log rõ một cách thiếu kiểm soát |
| Tên ứng dụng/người dùng | Có thể suy ra qua metadata hoặc dịch vụ ngoài TLS | Mã hóa payload không bảo đảm ẩn danh |
| Nội dung sau điểm TLS termination | Tùy đoạn kế tiếp | Cần kiểm tra có TLS lại hay không |

TLS bảo vệ **nội dung của kênh được thiết lập**, không phải giao thức ẩn danh hoàn chỉnh và không loại bỏ khả năng suy đoán từ độ dài/tần suất gói.

## 5. Mục tiêu thứ hai: Integrity — chống thay đổi trái phép

### 5.1. Vì sao mã hóa đơn thuần chưa đủ?

Nếu chỉ giấu nội dung mà không xác minh tính toàn vẹn, một bên trung gian vẫn có thể thay đổi ciphertext theo cách gây lỗi hoặc, với những hệ thống yếu, tác động đến plaintext sau giải mã. TLS hiện đại dùng **authenticated encryption** và các cơ chế xác thực thông điệp của handshake để kiểm tra tính hợp lệ.

Khi một bản ghi dữ liệu đã được bảo vệ không vượt qua bước kiểm tra xác thực, endpoint TLS phải xử lý lỗi theo giao thức; nó **không được coi dữ liệu bị sửa là response hợp lệ từ bên kia**.

### 5.2. Integrity của record và handshake

TLS bảo vệ hai khía cạnh:

1. **Dữ liệu ứng dụng:** bản ghi TLS với AEAD gắn nội dung vào khóa, trạng thái record và dữ liệu liên quan.
2. **Quá trình thương lượng:** các thông điệp xác minh (như **Finished**) ràng buộc trạng thái handshake và góp phần phát hiện việc sửa thông số được hai bên chấp nhận.

Điều này quan trọng vì một MITM không chỉ muốn đổi nội dung ứng dụng mà còn có thể muốn **hạ phiên xuống giao thức/cipher yếu**. Client/server cần kiểm tra phiên bản, cipher suite, xác thực chứng chỉ và điều kiện negotiation.

### 5.3. Integrity không thay thế xác thực và kiểm tra nghiệp vụ

Một thông điệp có tính toàn vẹn mật mã có nghĩa nó được nhận đúng trong ngữ cảnh phiên TLS, **không có nghĩa giao dịch được phép**. Ví dụ, TLS bảo vệ một yêu cầu chuyển tiền khỏi bị sửa trên đường đi; **authorization, CSRF protection, xác thực người dùng và giới hạn nghiệp vụ** vẫn phải do ứng dụng đảm trách.

Hơn nữa, nếu chính server ứng dụng đã bị chiếm và tự tạo response sai, TLS có thể chuyển response đó nguyên vẹn tới client. Cơ chế mật mã đường truyền không phát hiện một endpoint được xác thực nhưng hoạt động sai.

## 6. Mục tiêu thứ ba: Authentication — biết mình đang nói chuyện với ai

### 6.1. Server authentication trong HTTPS

Khi client kết nối đến `api.lab.example.test` qua HTTPS, một triển khai TLS dùng chứng chỉ X.509 thông thường cần xác minh:

1. **Chuỗi chứng chỉ (certificate chain):** chứng chỉ máy chủ được liên kết tới một trust anchor/CA được client tin theo chính sách.
2. **Danh tính dịch vụ:** chứng chỉ phù hợp với **tên DNS mong đợi** của dịch vụ, thông thường qua `subjectAltName` (SAN), không chỉ khớp địa chỉ IP trả về từ DNS.
3. **Thời gian hiệu lực:** chứng chỉ chưa hết hạn và không nằm trước thời điểm bắt đầu hiệu lực.
4. **Mục đích sử dụng và thuật toán:** certificate/key usage, server authentication policy và các thuật toán phù hợp.
5. **Chính sách thu hồi và trust:** áp dụng cơ chế kiểm tra trạng thái/thu hồi theo khả năng platform và yêu cầu doanh nghiệp.
6. **Bằng chứng sở hữu private key:** trong handshake certificate-based, máy chủ chứng minh nắm khóa riêng tương ứng thông qua các thao tác ký/xác thực của giao thức.

~~~mermaid
flowchart TD
    A["Client muốn kết nối api.lab.example.test"] --> B["Nhận chứng chỉ và thông tin bắt tay"]
    B --> C{"Chain tới CA được tin?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D{"SAN đúng tên + thời gian + policy?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Handshake chứng minh khóa đúng?"}
    E -- "Không" --> X
    E -- "Có" --> F["Thiết lập kênh TLS theo policy"]
~~~

Sơ đồ chỉ minh họa một kịch bản **certificate-based HTTPS authentication**. TLS cũng có các chế độ **PSK/resumption** với ngữ nghĩa xác thực khác và yêu cầu chính sách riêng.

### 6.2. DNS đúng địa chỉ chưa đủ; chứng chỉ mới giúp ràng buộc danh tính

Giả sử một resolver trả IP sai cho hostname dịch vụ. Client có thể thử kết nối tới IP đó, nhưng kẻ mạo danh **không thể dễ dàng hoàn tất phiên TLS hợp lệ cho đúng hostname** nếu không có chứng chỉ/khóa phù hợp và hệ thống client thực thi kiểm tra danh tính chuẩn.

**Điều kiện bắt buộc:** client **không bỏ qua lỗi chứng chỉ hoặc tự chấp nhận một CA không được tin cậy**, hệ thống trust store không bị lạm dụng và endpoint không bị chiếm. DNSSEC, DNS filtering và bảo vệ cấu hình DNS bổ sung lớp tin cậy, nhưng **không thay thế xác minh chứng chỉ TLS**.

### 6.3. Các nhầm lẫn nguy hiểm về chứng chỉ

| Suy nghĩ sai | Cách hiểu đúng |
|---|---|
| “Có ổ khóa HTTPS nghĩa là website luôn an toàn.” | TLS xác thực kênh/danh tính theo tên, không xác nhận dịch vụ không lừa đảo hoặc ứng dụng không có lỗi |
| “Chứng chỉ được ký bởi một CA bất kỳ là đủ.” | CA/trust anchor phải được client chấp nhận đúng policy và danh tính trong SAN phải khớp |
| “Kết nối được IP đúng là đã xác thực server.” | Cần kiểm tra chứng chỉ và tên dịch vụ được yêu cầu |
| “Có chứng chỉ hợp lệ là được phép truy cập dữ liệu.” | Authorization của ứng dụng là một quyết định khác |
| “Bỏ kiểm tra chứng chỉ chỉ ảnh hưởng cảnh báo giao diện.” | Có thể làm mất lớp chống MITM quan trọng |

Không xử lý sự cố bằng cách vô hiệu hóa xác minh chứng chỉ trên ứng dụng production. Thay vào đó, sửa trust store, certificate chain, tên miền hoặc cấu hình TLS termination theo quy trình.

## 7. TLS một chiều và mutual TLS (mTLS)

### 7.1. Mô hình mặc định của nhiều kết nối HTTPS

Trong HTTPS phổ biến, client xác thực **server**, còn người dùng thường được xác thực ở tầng ứng dụng bằng session, OAuth/OIDC, token hoặc phương thức khác. Đây thường được gọi là **server-authenticated TLS**.

### 7.2. Khi cần mTLS

**Mutual TLS** yêu cầu cả client và server tham gia **xác thực bằng chứng chỉ/khóa** theo chính sách. Server phải kiểm tra certificate chain, identity và quyền của client; client cũng phải xác thực server.

~~~mermaid
sequenceDiagram
    participant C as Service A / Client
    participant S as Service B / Server
    C->>S: ClientHello
    S-->>C: ServerHello, server certificate, CertificateRequest
    C->>S: Client certificate / CertificateVerify
    Note over C,S: Hai bên hoàn tất xác thực và thiết lập khóa
    C->>S: Encrypted application request
    S-->>C: Encrypted application response
~~~

**Lưu ý:** thứ tự chi tiết và mã hóa các thông điệp phụ thuộc TLS version; sơ đồ chỉ minh họa ý tưởng. Trong TLS 1.3, những handshake messages sau ServerHello được bảo vệ bằng handshake traffic keys phù hợp.

### 7.3. mTLS hữu ích trong trường hợp nào?

- **Service-to-service traffic** giữa microservices, nhất là qua các trust boundary.
- **API nội bộ** hoặc giao tiếp đối tác cần xác thực định danh máy/ứng dụng ở lớp kênh.
- **Kết nối quản trị hoặc dịch vụ nhạy cảm** được quản lý chứng chỉ theo từng thực thể.
- **Service mesh** hỗ trợ mã hóa/xác thực workload khi áp dụng identity policy và rotation thích hợp.

mTLS **không tự tạo authorization** ở cấp API. Một chứng chỉ client hợp lệ vẫn cần được ánh xạ tới **service identity, vai trò, phạm vi quyền và chính sách truy cập**.

### 7.4. Vòng đời chứng chỉ và quản lý khóa

Khi áp dụng mTLS cần đặc biệt quan tâm:

- Quy trình **issuance, enrollment, renewal, revocation** và identity binding.
- Bảo vệ private key (OS secret store, TPM/HSM khi phù hợp, file permissions và chính sách workload).
- Certificate rotation tự động nhưng có giám sát và rollback.
- Đồng bộ thời gian để đánh giá thời hạn chứng chỉ chính xác.
- Kịch bản khi CA/RADIUS/identity service không khả dụng, tránh tự động chuyển sang “chấp nhận mọi certificate”.
- Tương tác với **service discovery, DNS, proxy và load balancer** để xác thực đúng endpoint tại mỗi hop.

**Kết luận phần này:** TLS cung cấp cơ chế xác thực ở lớp kênh; độ tin cậy vận hành còn phụ thuộc PKI, quản lý quyền và cấu hình ứng dụng.

## 8. TLS handshake: thiết lập kênh và khóa bí mật

### 8.1. Phân biệt handshake và record protection

TLS có hai nhiệm vụ lớn:

- **Handshake:** các bên chọn những khả năng tương thích, tạo/đạo xuất vật liệu khóa, xác thực bên giao tiếp theo cơ chế thích hợp và xác minh quá trình thương lượng.
- **Record protection:** dùng khóa đã thiết lập để bảo vệ dữ liệu ứng dụng trong phiên bằng thuật toán mã hóa/tính toàn vẹn.

Trong **TLS 1.3 thông thường với xác thực máy chủ bằng chứng chỉ**, một trình tự đơn giản hóa:

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>S: ClientHello (versions, suites, key_share)
    S-->>C: ServerHello (chosen parameters, key_share)
    Note over C,S: Tạo handshake traffic secrets; bảo vệ thông điệp kế tiếp
    S-->>C: EncryptedExtensions
    S-->>C: Certificate + CertificateVerify
    S-->>C: Finished
    C->>C: Xác minh certificate, server name, chữ ký, Finished
    C->>S: Finished
    Note over C,S: Application traffic keys được thiết lập
    C->>S: Protected application data
    S-->>C: Protected application data
~~~

Đây là **một luồng đại diện**, không bao quát mọi kiểu handshake. TLS 1.3 có thể dùng **pre-shared keys (PSK)**, resumption và tùy chọn client certificate; khi đó loại thông điệp và thứ tự có thể khác. Một số dữ liệu ban đầu như ClientHello và ServerHello thường vẫn quan sát được trên đường truyền, trong khi các phần handshake về sau được mã hóa phù hợp.

### 8.2. Các bước mang ý nghĩa bảo mật gì?

| Bước | Ý nghĩa | Nếu cấu hình/triển khai sai |
|---|---|---|
| ClientHello | Client công bố phiên bản, cipher suites và tham số hỗ trợ | Có nguy cơ chấp nhận cơ chế không đáp ứng security policy |
| ServerHello | Server chọn tham số và tham gia thiết lập khóa | Client cần kiểm tra lựa chọn hợp lệ và chống negotiation/downgrade không mong muốn |
| Key agreement | Hình thành vật liệu chung dùng tạo traffic keys | Thuật toán yếu hoặc secret bị lộ có thể làm giảm confidentiality |
| Certificate | Cung cấp danh tính mật mã của server theo mô hình PKI | Cert sai SAN, hết hạn hoặc không đáng tin phải bị từ chối |
| CertificateVerify | Chứng minh quyền sử dụng private key phù hợp trong certificate-based handshake | Nếu thiếu xác minh, danh tính không được ràng buộc đúng |
| Finished | Xác thực trạng thái transcript handshake | Sửa thông số handshake sẽ bị phát hiện khi xác minh chuẩn |
| Protected records | Truyền dữ liệu ứng dụng với AEAD | Lỗi key/nonce/record validation có thể ảnh hưởng tính bí mật/toàn vẹn |

**TLS không truyền trực tiếp khóa bí mật phiên ở dạng rõ qua mạng** theo cách có thể đọc được chỉ từ packet capture. Hai đầu sử dụng quy trình trao đổi và đạo xuất khóa theo giao thức.

### 8.3. Khóa tạm thời và forward secrecy

**Forward secrecy** là thuộc tính quan trọng của những phiên sử dụng trao đổi khóa **tạm thời (ephemeral)** thích hợp, chẳng hạn (EC)DHE. Mục tiêu: nếu private key chứng chỉ máy chủ bị lộ *sau khi* một phiên kết thúc, đối phương đã ghi lại packet của phiên cũ **không mặc nhiên giải mã được nội dung phiên** chỉ từ private key đó.

Điều này dựa trên nhiều giả định: secret phiên không bị lộ, triển khai crypto đúng, key material được quản lý và xóa phù hợp, và endpoint không bị xâm phạm tại thời điểm truyền. **Forward secrecy không bảo vệ dữ liệu nếu attacker đã đọc plaintext ở endpoint hoặc nắm session keys trong lúc phiên hoạt động.**

Trong TLS 1.3, các phiên certificate-based sử dụng cơ chế trao đổi khóa tạm thời theo đặc tả. Với **PSK-only** hoặc một số cách resumption, các thuộc tính về forward secrecy phải xem **chế độ trao đổi khóa thực tế**, không gắn nhãn an toàn tuyệt đối cho mọi kết nối TLS 1.3.

### 8.4. Session resumption và 0-RTT

**Session resumption** có thể giảm chi phí bắt tay bằng cách sử dụng thông tin được thiết lập trước đó. Trong TLS 1.3, một số triển khai hỗ trợ **0-RTT early data** để gửi dữ liệu rất sớm khi khôi phục phiên.

**Điểm đánh đổi:** 0-RTT có **rủi ro replay**. Vì vậy, không tự động cho các thao tác **không idempotent** như tạo đơn hàng, chuyển tiền hoặc thay đổi trạng thái nhạy cảm đi qua 0-RTT chỉ vì muốn giảm latency. Ứng dụng và proxy phải có chính sách rõ ràng để từ chối/hạn chế early data khi không thể xử lý replay an toàn.

## 9. TLS 1.2 và TLS 1.3: khác biệt phục vụ mục tiêu an ninh

| Khía cạnh | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Trạng thái sử dụng | Vẫn có thể dùng với cấu hình an toàn được kiểm chứng | Ưu tiên cho dịch vụ và client hiện đại |
| Cipher suites | Có nhiều dạng legacy, cần hạn chế lựa chọn yếu | Danh sách suite hiện đại, trọng tâm AEAD |
| Trao đổi khóa | Có thể dùng ECDHE cho forward secrecy; một số kiểu cũ thiếu thuộc tính này | Quy trình hiện đại hơn, có (EC)DHE và PSK theo trường hợp |
| Thuật toán/handshake cũ | Có các tùy chọn cần loại bỏ theo chính sách | Loại bỏ nhiều cơ chế legacy |
| Handshake thông thường | Có thể cần nhiều round-trip hơn | Thiết kế giảm round-trip trong một số trường hợp |
| 0-RTT early data | Không theo cơ chế TLS 1.3 | Có thể hỗ trợ khi resumption, phải kiểm soát replay |
| Quản trị | Cần profile cipher/key exchange hợp lệ, không dùng cấu hình mặc định cũ tùy tiện | Cần quản lý chứng chỉ, PSK/resumption, early data và firmware/library |

**TLS 1.0 và TLS 1.1 đã bị deprecated** và không phù hợp cho triển khai mới. Việc tắt các phiên bản/cipher cũ phải đi kèm **kiểm kê client và thử tương thích**, không mặc định mọi hệ thống legacy có thể đổi ngay mà không ảnh hưởng ứng dụng.

### 9.1. Phiên bản cao không bảo đảm cấu hình đúng

Một server bật TLS 1.3 nhưng cấp chứng chỉ hết hạn, hostname không khớp hoặc proxy phía sau dùng HTTP plaintext vẫn có vấn đề. Ngược lại, TLS 1.2 với ECDHE, cipher mạnh và certificate validation đúng có thể phục vụ một phạm vi legacy được quản lý.

**Không tạo cipher policy bằng cách chọn thuật toán có tên nghe “mạnh nhất” mà chưa kiểm tra khả năng tương thích và đặc tả của thư viện.** Nên sử dụng security profile hiện đại đã được chuẩn hóa, cập nhật library và quan sát kết quả negotiation thực.

### 9.2. Downgrade và version negotiation

**Downgrade attack** là tình huống đối thủ cố khiến hai phía sử dụng phiên bản hoặc thuật toán yếu hơn khả năng/chính sách dự định. TLS có những cơ chế phòng vệ ở mức giao thức, nhưng vẫn phải cấu hình **minimum TLS version, cipher allowlist và khả năng xác thực** đúng.

Nếu ứng dụng “tự sửa lỗi” bằng cách hạ xuống TLS 1.0, bỏ certificate verification hoặc cho phép cipher yếu, mục tiêu bí mật/xác thực có thể bị phá vỡ. Cần phân biệt lỗi **compatibility** với nhu cầu **hạ mức an toàn**: giải pháp đúng thường là nâng cấp client, server hoặc thư viện.

## 10. TLS termination: hiểu đúng các đoạn dữ liệu được bảo vệ

### 10.1. Client-to-origin không phải lúc nào cũng một kênh TLS

Trong hệ thống hiện đại, client thường kết nối đến **CDN, ingress proxy, API gateway hoặc load balancer** trước khi request tới ứng dụng. Một chuỗi ví dụ:

~~~mermaid
flowchart LR
    C["Browser"] <-->|"TLS #1"| E["CDN / Edge"]
    E <-->|"TLS #2 nếu cấu hình"| L["Load Balancer"]
    L <-->|"TLS #3 hoặc HTTP"| A["Application service"]
    A <-->|"TLS #4 hoặc kết nối khác"| D["Database"]
    S["SOC / SIEM"] -. "Logs có phân quyền" .-> E
    S -. "Logs" .-> A
~~~

**Mỗi TLS connection là một phạm vi bảo mật riêng** có endpoint, danh tính được xác minh, chứng chỉ, cipher, traffic keys và trust boundary tương ứng. TLS #1 hoạt động tốt không chứng minh TLS #2, #3 hoặc #4 tồn tại hay được cấu hình an toàn.

### 10.2. Những câu hỏi phải đặt khi thiết kế

1. **Ai là TLS endpoint?** Browser → CDN hay Browser → origin trực tiếp?
2. **Điểm nào thấy plaintext?** WAF, reverse proxy, sidecar, API gateway, service mesh?
3. **Đoạn nào được re-encrypt?** Nếu traffic đi vào network nội bộ ở dạng rõ, có cần TLS/mTLS không?
4. **Proxy xác thực origin thế nào?** Có kiểm tra certificate chain và hostname hay chỉ mã hóa nhưng không xác thực?
5. **Chứng chỉ được quản lý bởi ai?** Quy trình rotation, expiration alert, private key isolation?
6. **Logging và observability** có ghi token, cookie hoặc dữ liệu nhạy cảm sau giải mã không?

### 10.3. TLS pass-through và TLS termination

| Mô hình | Cách xử lý | Đánh đổi |
|---|---|---|
| **TLS pass-through** | Thiết bị trung gian chuyển tiếp dữ liệu TLS mà không giải mã nội dung ứng dụng | Giữ ciphertext đi qua, nhưng WAF tầng HTTP ở giữa có thể không quan sát được path/body |
| **TLS termination** | Proxy/CDN kết thúc TLS và thấy plaintext để xử lý HTTP | Cho phép routing/WAF/caching theo HTTP, nhưng proxy là điểm nắm dữ liệu nhạy cảm |
| **TLS re-encryption** | Sau khi giải mã, proxy mở một TLS connection mới tới backend | Bảo vệ hop tiếp theo nếu xác thực certificate đúng, có thêm quản lý cert/CPU |
| **End-to-end mTLS** | Các service endpoints xác thực nhau qua TLS/mTLS theo kiến trúc | Cải thiện service identity nhưng phức tạp hơn về PKI, rotation và policy |

**Không gọi cấu hình “encrypted end-to-end” nếu một hop trung gian được truyền plaintext**. Cũng cần lưu ý mTLS trong service mesh có thể chỉ bảo vệ **proxy-to-proxy**, còn traffic giữa ứng dụng và local sidecar có đặc tính riêng; tài liệu vận hành phải mô tả chính xác ranh giới.

### 10.4. IDS/IPS và kiểm tra nội dung TLS

Thiết bị IDS/IPS quan sát packet **bên ngoài điểm TLS termination** thường chỉ thấy ciphertext và metadata, không tự đọc được URL path/body HTTP. Một WAF tích hợp tại điểm termination có thể phân tích request đã được giải mã, nhưng cần bảo vệ quyền truy cập vào nội dung và giới hạn log.

**TLS inspection** trong doanh nghiệp có thể được triển khai theo chính sách hợp lệ, nhưng nó tạo điểm xử lý plaintext, yêu cầu quản lý CA/khóa, tương thích ứng dụng, quyền riêng tư và rủi ro quản trị. Không coi giải mã toàn bộ traffic là lựa chọn mặc định tốt nhất.

## 11. Threat modeling: TLS ngăn những gì và không ngăn những gì?

| Mối đe dọa / sự cố | TLS hỗ trợ thế nào? | Việc bổ sung bắt buộc xem xét |
|---|---|---|
| Người trung gian đọc nội dung | Mã hóa dữ liệu qua phiên đúng | Quản lý khóa, bảo vệ endpoint và log |
| Sửa packet đang truyền | AEAD và xác minh handshake giúp phát hiện | Xử lý lỗi đúng, không bỏ kiểm tra record |
| Giả mạo server khi DNS bị đổi | Cert chain + hostname validation chống giả danh nếu trust đúng | DNS security, quản lý CA, chống người dùng bypass warning |
| Server giả có chứng chỉ sai tên | Client phải từ chối khi xác thực chuẩn | Không bật insecure mode, sửa SAN/certificate |
| Credential/secret của ứng dụng bị lộ trong log | TLS không bảo vệ dữ liệu đã ghi rõ ra log | Redaction, secret management, RBAC cho logs |
| Server hoặc client bị nhiễm mã độc | TLS không ngăn endpoint đọc plaintext của chính nó | Patch, EDR, sandboxing, IAM, kiểm soát quyền |
| Phishing tại domain do attacker kiểm soát | TLS có thể hoạt động hợp lệ cho chính domain lừa đảo | Phòng chống phishing, identity-aware controls |
| User đăng nhập hợp lệ nhưng thao tác vượt quyền | Không phải mục tiêu TLS | Authentication + authorization + audit ở ứng dụng |
| Replay 0-RTT | Có hạn chế riêng; early data có thể bị phát lại | Không cho thao tác thay đổi trạng thái nguy hiểm qua 0-RTT |
| DDoS / volumetric flood | TLS không đảm bảo availability | CDN, rate limit, load shedding, DDoS mitigation |
| Metadata IP/SNI/traffic pattern | TLS không ẩn toàn bộ | ECH khi được hỗ trợ, DNS privacy và threat model phù hợp |
| Route sai đi qua vùng không tin | TLS giúp bảo vệ nội dung và danh tính cuối kênh | Segmentation, firewall, routing security, quan sát |
| Chứng chỉ hết hạn | Có thể khiến client từ chối truy cập | Rotation, expiry alert, PKI lifecycle và canary |
| Private key bị lộ | Có thể làm suy giảm xác thực và một số bí mật | Key isolation, revoke/replace, incident response |

**Một trang HTTPS vẫn có thể là trang giả mạo hoặc độc hại.** TLS cung cấp đảm bảo mật mã về kênh và danh tính được xác minh, không đánh giá đạo đức hay độ chính xác của nội dung trang.

### 11.1. Ví dụ phân tích MITM

Giả sử attacker kiểm soát một Wi-Fi hotspot và trả DNS sai cho `api.lab.example.test`:

- Nếu client kiểm tra certificate chain và SAN chính xác, máy chủ giả **không có chứng chỉ/khóa phù hợp** thường không vượt qua bước xác thực.
- Nếu client dùng thư viện HTTP cấu hình **skip certificate verification**, attacker có thể thiết lập một kênh TLS với **chính attacker** và đọc/sửa nội dung ở điểm đó.
- Nếu attacker chiếm quyền CA/trust store của client, hoặc có credential/key hợp lệ của server, rủi ro chuyển sang một mô hình nghiêm trọng hơn.

Do đó, **bật encryption nhưng bỏ authentication không đạt mục tiêu chống MITM**.

## 12. Những quyết định cấu hình an toàn quan trọng

### 12.1. Chính sách dịch vụ

Một profile TLS được quản trị tốt thường xem xét:

- **Minimum protocol version:** ưu tiên TLS 1.3, chỉ giữ TLS 1.2 khi cần và được cấu hình an toàn; không cho TLS 1.0/1.1.
- **Cipher suite/key exchange/signature algorithms:** chọn những thuật toán được hỗ trợ, không bật cipher cũ chỉ để qua bài test legacy.
- **Certificate chain và SAN:** server identity hợp lệ, chain đầy đủ và trust anchor theo policy.
- **Private key storage:** quyền truy cập tối thiểu, rotation, HSM/secret manager nếu phù hợp.
- **Client-side verification:** bật chain validation và hostname verification, không cấu hình `insecure` hoặc chấp nhận mọi certificate.
- **mTLS nếu cần:** xác thực client cert, ánh xạ identity và authorization ở đúng điểm.
- **Session ticket/resumption và 0-RTT:** key rotation, replay risk và session policy.
- **TLS termination topology:** các đoạn giữa gateway/origin/service được mã hóa và xác thực theo threat model.
- **Observability:** expiry alerts, handshake failures, protocol versions, reject reasons, không ghi secrets.

### 12.2. Ví dụ profile Nginx minh họa

~~~nginx
# Chỉ là ví dụ cấu trúc trong lab, không copy thẳng lên production.
# Đường dẫn cert/key phải tồn tại và được quản lý bảo mật.
server {
    listen 443 ssl;
    server_name api.lab.example.test;

    ssl_certificate     /etc/tls-lab/server-chain.pem;
    ssl_certificate_key /etc/tls-lab/server-key.pem;

    # Chỉ những phiên bản TLS đã được đánh giá và hỗ trợ.
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

**Chủ đích giáo dục:** đây là một TLS endpoint trên Nginx, nhưng dòng `proxy_pass http://...` cho thấy **hop Nginx → backend là HTTP plaintext**, dù frontend có HTTPS. Nếu backend nằm trong trust boundary cần bảo vệ bằng TLS, hãy thiết kế **TLS tới upstream và xác thực certificate upstream đúng cách** thay vì chỉ đổi URL sang `https://` mà bỏ verification.

Ví dụ không cấu hình đầy đủ ciphers, upstream trust, HSTS, mTLS, session tickets, logging, OCSP hay rate limiting. Nhiệm vụ đó phụ thuộc **phiên bản Nginx, bản build OpenSSL, certificate PKI và security policy**; đừng coi một config ngắn là template production đã được harden.

### 12.3. HSTS và HTTPS redirect

**HTTP Strict Transport Security (HSTS)** là cơ chế ứng dụng web thông báo cho trình duyệt phải dùng HTTPS khi truy cập hostname trong phạm vi chính sách đã ghi nhớ. HSTS giúp giảm một số rủi ro truy cập nhầm HTTP sau khi policy được thiết lập, nhưng:

- HSTS **không tự cấp chứng chỉ hợp lệ**.
- Cần cấu hình HTTPS và các subdomain phù hợp trước khi bật quy tắc phạm vi rộng.
- **Preload**, `includeSubDomains` và `max-age` dài có ảnh hưởng vận hành lớn, khó đảo ngược tức thì.
- Lần truy cập đầu tiên có thể có các khác biệt theo cơ chế preload và trạng thái policy của client.

Chuyển hướng HTTP → HTTPS hữu ích nhưng **không thay thế HSTS**, vì bước HTTP đầu tiên có thể nằm trong phạm vi cần bảo vệ. Phải thiết kế cả hai theo môi trường sản xuất.

## 13. TLS với DNS, VPN, Wi-Fi và cloud

### 13.1. DNS bảo vệ một phần khác trong chuỗi

DNS trả tên dịch vụ → địa chỉ; TLS xác thực endpoint ứng với **tên mà client định kết nối** theo chứng chỉ. **DNSSEC** có thể bổ sung xác thực dữ liệu DNS từ phía resolver validating, còn DoT/DoH/DoQ bảo vệ transport truy vấn DNS trong những phạm vi khác nhau. Một kết nối HTTPS dùng TLS **không tự làm DNS query thành riêng tư hoặc có DNSSEC**.

### 13.2. VPN và Wi-Fi

**VPN** có thể bảo vệ một tập IP flows giữa các điểm tunnel, còn **WPA2/WPA3** bảo vệ một chặng vô tuyến. TLS thường phục vụ **kênh ứng dụng**, nên nhiều lớp này có thể kết hợp. Không coi việc đã có VPN hoặc WPA3 là lý do tắt HTTPS/TLS ở ứng dụng nhạy cảm.

### 13.3. IDS/IPS, segmentation và dịch vụ cloud

Ở cloud hoặc Kubernetes, traffic giữa service pods có thể đi qua **sidecar, ingress controller, internal LB, service mesh, overlay hoặc virtual switch**. Cần xác định chính xác nơi TLS được thiết lập/kết thúc và **identity mà từng proxy xác minh**. Một nhóm security group hoặc network policy có thể giới hạn network access nhưng không tự xác thực identity của máy chủ ở tầng TLS.

### 13.4. Availability là mục tiêu riêng

TLS có thể tăng CPU/latency khi bắt tay/giải mã; cần capacity planning, session reuse, connection pooling, cache, HA và chống DDoS phù hợp. Chuyển sang TLS 1.3 có thể giảm độ trễ bắt tay trong một số trường hợp nhưng **không biến một máy chủ quá tải thành hệ thống chịu DDoS**.

## 14. Quan sát TLS an toàn trong phòng lab

### 14.1. Kiểm tra certificate và hostname qua OpenSSL

Những lệnh sau giả định một dịch vụ thử do bạn quản lý tại `api.lab.example.test`; tên này **không có DNS công khai mặc định**. Không dùng tùy chọn bỏ xác minh. Cú pháp cụ thể có thể khác theo phiên bản OpenSSL.

~~~bash
# Đọc thông tin TLS từ server lab và yêu cầu xác minh hostname.
# Phải có trust store phù hợp và kết nối mạng tới đúng dịch vụ.
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -brief < /dev/null

# Đọc certificate công khai đã xuất ra file trong lab; KHÔNG đọc private key.
openssl x509 -in lab-server-certificate.pem \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

**Quan sát:** kết quả certificate verification, TLS version, cipher, server identity, issuer và thời hạn. Với certificate verification, cần đọc cả **status lỗi và exit code**, không chỉ một dòng chứa chữ “CONNECTED”. Nếu server dùng CA nội bộ, phải cung cấp CA đáng tin theo chính sách bằng trust store hoặc tùy chọn CA phù hợp, **không dùng `-k` hoặc `-verify 0` như cách khắc phục**.

### 14.2. Kiểm tra một kết nối HTTPS qua curl

~~~bash
# HEAD request tới endpoint health của hệ thống lab được phép.
curl --head --verbose --connect-timeout 3 --max-time 10 \
  https://api.lab.example.test/health

# Tới IP lab cụ thể nhưng giữ hostname cho SNI và hostname validation.
curl --head --verbose --connect-timeout 3 --max-time 10 \
  --resolve api.lab.example.test:443:192.0.2.20 \
  https://api.lab.example.test/health
~~~

Lệnh `--resolve` cho phép phân biệt **DNS/route** với **TLS identity** khi thử một backend cụ thể. Nó không bảo đảm IP ví dụ có thể kết nối ngoài môi trường lab. **Không thêm `-k` / `--insecure`** nếu đang kiểm thử mục tiêu authentication, vì khi đó phép thử không chứng minh việc xác minh danh tính server đúng.

### 14.3. Một số tình huống cần phân biệt khi đọc log

| Biểu hiện | Giả thuyết | Đọc thêm gì? |
|---|---|---|
| TCP connect thành công nhưng TLS handshake lỗi | Không tương thích protocol/cipher, CA hoặc SNI | TLS alert, negotiated version, cert chain |
| TLS thành công nhưng HTTP 403 | Authorization hoặc WAF policy từ ứng dụng | Access logs, role, WAF rule ID |
| TLS thành công nhưng HTTP 502 | Backend/upstream lỗi hoặc xác thực TLS upstream sai | Reverse proxy logs, upstream health |
| Certificate đúng nhưng hostname mismatch | Dùng sai Host/SNI, SAN thiếu, route qua sai endpoint | URL mong đợi, SAN, SNI, LB routing |
| Chỉ một thiết bị không kết nối | Client trust store, thời gian, TLS library, proxy | OS/runtime version, CA, local logs |
| Người dùng thấy lỗi sau certificate rotation | Chain thiếu, CA không được tin, key/cert không khớp | Diff certificate, chain, reload status |
| IDS không thấy HTTP path | TLS chưa được giải mã tại điểm IDS | TLS termination topology, app/WAF logs |

**Một lần `curl` thành công không chứng minh toàn hệ thống an toàn.** Nó chỉ xác nhận một trường hợp với hostname, thời điểm, đường mạng và TLS client cụ thể. Cần so sánh nhiều client/đường đi và policy theo môi trường.

## 15. Ma trận kiểm thử ba mục tiêu bảo vệ

Một kết nối TLS có thể **thành công về mặt kỹ thuật** nhưng không thỏa chính sách nếu hostname bị bỏ qua, chứng chỉ client không được yêu cầu ở API mTLS hoặc một hop backend vẫn gửi HTTP plaintext. Vì thế, bộ test phải liên kết mục tiêu với **kết quả quan sát được và bằng chứng**.

| Test ID | Mục tiêu | Phép kiểm thử trong lab có phép | Điều kiện PASS |
|---|---|---|---|
| **CONF-01** | Dữ liệu ứng dụng được mã hóa trên hop được chỉ định | Capture thụ động ở đường mạng lab, đối chiếu TLS topology | Không thấy plaintext HTTP/body nhạy cảm trên hop cần bảo vệ |
| **CONF-02** | Hop proxy → backend được bảo vệ khi policy yêu cầu | Đối chiếu Nginx/LB config và telemetry backend | Kết nối backend dùng TLS được xác thực, không tự tin vào frontend TLS |
| **INT-01** | Record integrity được thực thi | Kiểm tra cấu hình và kết quả phiên TLS chuẩn; dùng test harness giao thức được phê duyệt nếu cần | Endpoint từ chối bản ghi không xác thực theo chuẩn, không xử lý dữ liệu giả |
| **AUTH-01** | Server hợp lệ được tin cậy | Dùng client bình thường với CA và hostname đúng | Certificate chain/SAN/time hợp lệ, kết nối thành công |
| **AUTH-02** | Hostname sai bị từ chối | Kết nối tới server thử có cert cho tên khác | Client từ chối, không bật insecure mode |
| **AUTH-03** | CA không được tin bị từ chối | Dùng certificate lab ký bởi CA chưa được trust | Client từ chối, ghi rõ nguyên nhân |
| **AUTH-04** | Certificate hết hạn bị từ chối | Dùng bộ cert giả định hết hạn trong lab cô lập | Xác minh thời gian thất bại đúng theo chính sách |
| **MTLS-01** | Chỉ client có cert được duyệt được kết nối | Kết nối đến endpoint mTLS bằng cert lab hợp lệ | Peer identity đúng và ứng dụng cho phép đúng quyền |
| **MTLS-02** | Client thiếu/sai cert bị từ chối | Kết nối lab không cung cấp credential được yêu cầu | Thất bại tại TLS/client-auth hoặc policy tương ứng, có log |
| **VERS-01** | Chỉ protocol version được duyệt | Kiểm tra cấu hình và phép thử compatibility có giới hạn | TLS 1.2/1.3 theo policy; phiên bản cấm không được chấp nhận |
| **CIPHER-01** | Bộ mật mã/key exchange phù hợp | Xem negotiated suite, key exchange và library config | Không có thuật toán yếu nằm ngoài policy |
| **EARLY-01** | Bảo vệ thao tác nhạy cảm khỏi 0-RTT replay | Review proxy/app policy và test request idempotency trong lab | Early data không thực thi thao tác không an toàn |
| **HSTS-01** | HTTPS được ưu tiên đúng | Kiểm tra redirect/HSTS trên tên thử | Không phá host/subdomain hợp lệ, chính sách phù hợp |
| **OBS-01** | Log không rò rỉ dữ liệu sau giải mã | Review redaction ở proxy/app | Không log password, token, private key, cookie nhạy cảm |
| **REG-01** | Sau rotation/upgrade vẫn giữ an ninh | Chạy lại test trước/sau thay cert hoặc TLS library | Client hợp lệ hoạt động; client sai danh tính vẫn bị từ chối |

### 15.1. PASS, FAIL, INCONCLUSIVE

- **PASS:** có bằng chứng phù hợp mục tiêu và đúng hop. Ví dụ browser xác minh cert của `api.lab.example.test`, cipher hợp policy, request thành công, proxy xác thực certificate khi kết nối backend.
- **FAIL:** có bằng chứng trái policy, ví dụ client chấp nhận chứng chỉ sai hostname, hop nội bộ bắt buộc TLS lại truyền HTTP rõ, hoặc dịch vụ mTLS cho client không có chứng chỉ được truy cập.
- **INCONCLUSIVE:** test thiếu điều kiện, ví dụ lab DNS chưa có bản ghi, server không chạy, chỉ có timeout TCP nhưng không có TLS logs, hoặc không biết endpoint nào thực sự giải mã request.

**Cẩn thận khi đánh giá:** một kết nối thất bại **không tự chứng minh cert validation đã chặn MITM**. Nó có thể thất bại vì route, firewall, DNS hoặc server đã ngừng hoạt động. Hãy có **positive control** và thu lỗi xác minh chứng chỉ cụ thể.

### 15.2. Bằng chứng nên lưu

~~~yaml
test_id: TLS-SERVER-AUTH-LAB-01
environment: authorized-isolated-lab
target_hostname: api.lab.example.test
target_ip: 192.0.2.20
tls_endpoint: edge-proxy
security_goals:
  - confidentiality
  - integrity
  - server-authentication
expected:
  certificate_chain: valid
  hostname_matches_san: true
  minimum_tls_version: policy-defined
  backend_hop: separately-verified
evidence:
  - timestamp-utc
  - client-validation-result
  - negotiated-protocol-and-cipher
  - certificate-subject-issuer-san-expiry
  - reverse-proxy-upstream-configuration
  - allowed-and-denied-app-tests
result: pending-execution
~~~

Mẫu **không tuyên bố đã thực hiện kiểm thử**. Không lưu session secrets, private key, password, auth token hoặc dữ liệu người dùng vào evidence.

## 16. Case study: HTTPS bên ngoài nhưng đường tới backend chưa được bảo vệ

### 16.1. Bối cảnh

Một công ty cung cấp API qua `api.lab.example.test`. Trình duyệt và mobile app kết nối đến load balancer bằng TLS 1.3; chứng chỉ công khai còn hiệu lực. LB chuyển request đến **API origin qua HTTP** bên trong subnet ứng dụng. API liên hệ database khác subnet. Đội vận hành đánh dấu hệ thống là “mã hóa end-to-end” vì trang quản trị LB hiển thị TLS enabled.

Một đợt rà soát threat model chỉ ra rằng mạng giữa LB và API được chia sẻ với những workload khác, trong khi request có **access token và dữ liệu nhạy cảm**. Việc chỉ có TLS phía client chưa đủ để khẳng định **tính bí mật và toàn vẹn trên đoạn LB → origin**.

### 16.2. Sơ đồ trước thay đổi

~~~mermaid
flowchart LR
    C["Client"] <-->|"TLS 1.3: bảo vệ"| L["Load Balancer"]
    L -->|"HTTP plaintext trên mạng nội bộ"| A["API origin"]
    A --> D["Database"]
    N["Quan sát traffic ở mạng nội bộ"] -. "Có thể thấy plaintext nếu có quyền trên đường" .-> A
~~~

**Phân tích ba mục tiêu:**

| Mục tiêu | Client → LB | LB → API |
|---|---|---|
| Confidentiality | Được TLS bảo vệ nếu phiên đúng | Không được TLS bảo vệ theo giả định |
| Integrity | Được TLS record protection | Phụ thuộc bảo vệ lớp khác, không có đảm bảo TLS |
| Authentication | Client kiểm tra certificate của LB | Chưa có TLS identity verification ở hop này |

Đoạn HTTP ở bên trong một mạng private **không tự động an toàn** chỉ vì các IP không public. Firewall và segmentation có thể giảm khả năng truy cập, nhưng không tạo các thuộc tính mật mã của TLS cho request trên hop đó.

### 16.3. Phương án cải thiện

1. **Xác định chính sách thực:** những luồng nào bắt buộc mã hóa giữa các dịch vụ, và service identity nào phải được xác minh?
2. **Bật TLS tới upstream** với certificate và hostname validation đúng. Với dịch vụ nhạy cảm, cân nhắc **mTLS** cho LB/sidecar → API.
3. **Quản lý PKI:** CA, SAN, client identity, private key rotation, expiry alert, chuẩn hóa trust store.
4. **Giảm tối đa plaintext** tại điểm termination bằng hạn chế quyền truy cập, tránh ghi token/body vào log và mã hóa những hop còn lại.
5. **Giữ segmentation:** chỉ LB hoặc identity đã duyệt được phép truy cập API; không mở toàn bộ subnet vì đã có mTLS.
6. **Kiểm tra hồi quy:** client đúng vẫn kết nối, client sai cert bị từ chối, API khỏe, latency/SLO không vượt giới hạn, IDS/WAF hiểu đúng vị trí quan sát.

### 16.4. Sơ đồ mục tiêu

~~~mermaid
flowchart LR
    C["Client"] <-->|"TLS #1 và server identity"| L["Load Balancer"]
    L <-->|"TLS #2 / mTLS đã xác thực"| A["API origin"]
    A <-->|"TLS #3 nếu chính sách yêu cầu"| D["Database"]
    LB["Firewall + allowlist"] -. "Hạn chế lưu lượng LB → API" .-> A
    M["Monitoring/SIEM"] -. "Audit và alert" .-> L
    M -. "Audit" .-> A
~~~

### 16.5. Kết quả mong muốn (giả định, chưa chạy)

~~~text
Scenario: LAB-TLS-ENDPOINT-01
Before:
  Browser -> LB: TLS validated
  LB -> API: plaintext HTTP
  Backend server identity: not cryptographically verified on that hop

After (target):
  Browser -> LB: authenticated TLS
  LB -> API: authenticated TLS or mTLS
  API -> DB: reviewed per application security policy
  Firewall: allowlist only
  Sensitive payload in logs: no
  Positive test: approved application transaction succeeds
  Negative test: invalid cert/identity is rejected

Status: proposed design; validation not executed
~~~

**Bài học:** tuyên bố “đã bật HTTPS” chỉ nói lên **một điểm hoặc một số điểm trong kiến trúc**. Muốn chứng minh mục tiêu bảo vệ đường truyền, phải liệt kê **tất cả trust boundaries và TLS endpoints**.

## 17. Troubleshooting theo từng mục tiêu TLS

### 17.1. Confidentiality

**Triệu chứng:** packet capture ở subnet giữa gateway và backend cho thấy HTTP body rõ, dù phía browser dùng HTTPS.

**Giả thuyết:** TLS đã kết thúc tại gateway và upstream dùng HTTP. **Xác minh:** xem proxy routing, protocol tới upstream, điểm bắt gói và các session thực. **Khắc phục:** TLS lại trên hop cần bảo vệ, đúng certificate validation, đồng thời review segmentation.

### 17.2. Integrity

**Triệu chứng:** ứng dụng bị lỗi handshake/record verification khi thiết bị mạng trung gian thay đổi.

**Giả thuyết:** một thiết bị TLS inspection, proxy hoặc middlebox có cấu hình sai, hoặc có lỗi phiên/record. **Xác minh:** TLS alert, version/cipher, certificate path, LB logs, thay đổi firmware và điểm termination. **Khắc phục:** sửa cơ chế tương thích và xác thực, **không tắt kiểm tra record/certificate**.

### 17.3. Authentication

**Triệu chứng:** `certificate verify failed`, `hostname mismatch` hoặc browser cảnh báo cert.

**Giả thuyết:** cert hết hạn, tên trong SAN không khớp, thiếu intermediate, CA không được tin, đồng hồ sai hoặc server/LB chọn nhầm certificate theo SNI. **Xác minh:** hostname URL thực, chain, SAN, issuer, expiry, trust store và server logs. **Khắc phục:** cấp/sửa cert hoặc trust cấu hình đúng; không yêu cầu client bỏ qua cảnh báo.

### 17.4. TLS thành công nhưng ứng dụng vẫn lỗi

**Triệu chứng:** TLS được xác minh thành công nhưng HTTP 401/403/404/5xx hoặc timeout nghiệp vụ.

**Diễn giải:** các mã HTTP này xảy ra **sau hoặc bên trong kênh TLS**, không tự chứng minh TLS thất bại. Kiểm tra identity token, authorization, WAF, route, backend, DNS, database hoặc dependency. Nên tách dashboard **TLS handshake success** khỏi **HTTP/application success**.

### 17.5. Thứ tự điều tra tiêu chuẩn

1. Ghi **hostname/port/SNI, thời gian UTC, nguồn client, route, TLS endpoint** và trạng thái lỗi.
2. Kiểm tra **DNS, TCP/QUIC reachability, firewall và endpoint lắng nghe**.
3. Kiểm tra **protocol version, cipher, key exchange và TLS alert**.
4. Với certificate-based authentication, kiểm tra **CA, chain, SAN/hostname, expiry, key possession và client-cert nếu dùng mTLS**.
5. Nếu handshake thành công, chuyển sang **HTTP status, application authn/authz, proxy/upstream, dependency**.
6. Đối chiếu **đúng hop** cần bảo vệ và bảo đảm không hạ an ninh khi xử lý.

## 18. Bài tập tự kiểm tra

### Bài 1 — Ba mục tiêu

Một API gửi thông tin người dùng qua HTTPS. Hãy cho một ví dụ riêng cho **confidentiality**, **integrity** và **authentication**.

*Gợi ý:* mã hóa body chống nghe lén; kiểm tra AEAD phát hiện sửa dữ liệu; client xác minh chain và SAN để tránh gửi credential đến server giả.

### Bài 2 — TLS và mạng Wi-Fi

Nhân viên truy cập HTTPS qua Wi-Fi WPA3. Nếu AP chuyển tiếp dữ liệu sau khi giải mã Wi-Fi, điều gì bảo vệ nội dung ứng dụng trên đường từ AP tới server?

*Gợi ý:* một phiên HTTPS/TLS đúng bảo vệ nội dung đến **TLS endpoint**; WPA3 chỉ bảo vệ chặng radio. Cần kiểm tra proxy/termination ở giữa.

### Bài 3 — DNS bị giả mạo

DNS đưa `api.lab.example.test` tới IP không đúng. Khi nào TLS giúp client từ chối máy chủ giả?

*Gợi ý:* client kiểm tra certificate chain, SAN/hostname và bằng chứng private key đúng; không bypass lỗi certificate và trust store đáng tin.

### Bài 4 — Chứng chỉ hợp lệ nhưng phân quyền sai

Server có chứng chỉ TLS hợp lệ, nhưng user không được phép tải báo cáo của người khác. TLS giải quyết lỗi này không?

*Đáp án:* không. Lỗi **authorization** cần được kiểm soát tại ứng dụng/API theo user/role, cùng audit.

### Bài 5 — Forward secrecy

Một đối thủ đã ghi ciphertext của những phiên cũ, sau đó lấy được private key của chứng chỉ server. Khi nào forward secrecy giúp giảm thiệt hại?

*Gợi ý:* khi phiên cũ dùng trao đổi khóa ephemeral phù hợp, session secrets không bị lộ và các giả định crypto vẫn đúng. Không bảo vệ nếu plaintext/session keys đã bị đánh cắp.

### Bài 6 — 0-RTT

Một ứng dụng thanh toán muốn bật TLS 1.3 0-RTT cho mọi request. Nguy cơ cần kiểm soát là gì?

*Gợi ý:* early data có khả năng bị **replay**; không cho phép thao tác ghi không idempotent được xử lý lặp ngoài ý muốn.

### Bài 7 — Chứng chỉ của backend

CDN kết nối HTTPS tới origin nhưng cấu hình **không xác minh chứng chỉ origin**. Có thể tuyên bố chống MITM trên hop CDN → origin như khi certificate validation đầy đủ không?

*Đáp án:* không. Chỉ mã hóa mà không xác thực danh tính peer làm giảm khả năng chống giả mạo bên đích. Cần cấu hình kiểm tra CA/hostname thích hợp.

### Bài 8 — mTLS và quyền truy cập

Service A có chứng chỉ client hợp lệ nhưng không được phép gọi API quản trị của Service B. mTLS có tự từ chối endpoint quản trị không?

*Gợi ý:* mTLS xác thực identity. Service B hoặc policy engine vẫn phải **ủy quyền theo identity và API scope**.

### Bài 9 — Quan sát IDS

NIDS trước reverse proxy không thấy path HTTP của request HTTPS. Đây có chứng minh sensor bị lỗi không?

*Gợi ý:* không. Sensor trước TLS termination thường thấy ciphertext; cần xác minh nơi TLS kết thúc và dùng WAF/app logs khi phân tích HTTP.

### Bài 10 — Chuyển phiên bản

Một hệ thống cũ chỉ hỗ trợ TLS 1.0 và không thể kết nối sau khi server tăng minimum version. Nên làm gì?

*Gợi ý:* lập inventory, nâng client/runtime, lên kế hoạch migration hoặc phân đoạn dịch vụ legacy được kiểm soát. Không hạ tiêu chuẩn toàn bộ hệ thống chỉ để một client cũ kết nối.

### Bài 11 — Giải thích handshake

Vì sao **Finished** và **CertificateVerify** là hai vai trò khác nhau?

*Gợi ý:* CertificateVerify trong kiểu xác thực chứng chỉ ràng buộc quyền sử dụng private key với handshake; Finished xác nhận trạng thái transcript và khóa handshake phù hợp.

### Bài 12 — Kiểm thử âm tính

Thiết kế phép thử chứng minh client từ chối certificate sai hostname. Vì sao cần thêm một positive control?

*Gợi ý:* nếu server đã tắt hoặc đường mạng bị lỗi, kết nối thất bại không chứng minh certificate validation có hiệu lực. Cần server lab đang hoạt động, cert đúng thành công và cert sai bị từ chối với lỗi cụ thể.

## 19. Checklist kiểm soát TLS trong bảo mật đường truyền

- Đã xác định **tài sản và dữ liệu nhạy cảm**, cùng những trust boundaries phải được bảo vệ.
- Có sơ đồ **mọi TLS endpoints và hop plaintext**, không nhầm HTTPS frontend với encrypted end-to-end.
- Bật **TLS 1.3** khi có thể; TLS 1.2 theo security policy an toàn, **không cho TLS 1.0/1.1**.
- Sử dụng **AEAD/cipher/key exchange/signature suites** phù hợp thư viện và yêu cầu.
- Client **xác minh certificate chain, SAN/hostname, thời gian và policy**; không có `--insecure`/skip validation trong production.
- Có **quy trình cấp, lưu khóa, tự động gia hạn, rotation, revocation và cảnh báo expiry** cho certificate.
- Nếu dùng **mTLS**, cả hai bên xác thực và chính sách **authorization** tách biệt.
- Proxy/LB/CDN **xác minh chứng chỉ upstream** nếu re-encrypt, có cấu hình TLS đúng cho từng hop.
- Quyết định **HSTS, resumption, ticket keys và 0-RTT** dựa trên rủi ro, không bật mặc định cho giao dịch nhạy cảm.
- Bảo vệ **DNS, firewall, segmentation, VPN/Wi-Fi và service identity** như những lớp hỗ trợ.
- Log/TLS inspection không tiết lộ **password, private key, token, session secrets hoặc dữ liệu khách hàng** ngoài quyền cho phép.
- Có phép thử **positive/negative**, certificate mismatch, expiry, CA trust, mTLS client identity, protocol versions và regression sau upgrade.
- Đánh giá tính sẵn sàng và tải TLS qua **SLO/latency/error**, bởi TLS không thay thế DDoS protection hoặc high availability.

**Ghi nhớ:** TLS tạo nền tảng **bí mật, toàn vẹn và xác thực cho một kênh truyền**, nhờ đó giảm khả năng nghe lén, sửa dữ liệu và giả mạo endpoint trên đường mạng. Đảm bảo đó chỉ có giá trị trong **phạm vi hai TLS endpoints, theo chính sách xác thực thực sự được thực thi**. Để bảo vệ dịch vụ mạng toàn diện, phải kết hợp TLS với quản lý chứng chỉ/khóa, phân quyền ứng dụng, phân đoạn, DNS security, firewall, giám sát và khả năng phục hồi.

### Tài liệu tham khảo

- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, key schedule, record protection và các thuộc tính TLS 1.3.
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325): hướng dẫn chọn phiên bản, bộ mật mã và cấu hình an toàn.
- [RFC 8996 — Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996): tình trạng các phiên bản TLS cũ.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cơ sở certificate chain và PKIX.
- [RFC 6066 — Transport Layer Security Extensions](https://www.rfc-editor.org/rfc/rfc6066): các extension TLS, gồm SNI.
- [RFC 7301 — Transport Layer Security Application-Layer Protocol Negotiation Extension](https://www.rfc-editor.org/rfc/rfc7301): ALPN và lựa chọn giao thức ứng dụng.
- [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797): cơ chế buộc truy cập HTTPS từ trình duyệt.
- [RFC 9001 — Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001): cách QUIC tích hợp TLS 1.3.
- [RFC 8470 — Using Early Data in HTTP](https://www.rfc-editor.org/rfc/rfc8470): lưu ý replay khi xử lý early data.
- [NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of TLS Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final): hướng dẫn xây chính sách TLS.


