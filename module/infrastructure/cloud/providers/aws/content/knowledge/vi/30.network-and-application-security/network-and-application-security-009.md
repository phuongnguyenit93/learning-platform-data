# TLS policy, mTLS và quản lý trust giữa các thành phần

## Mục tiêu học tập

Trong một hệ thống phân tán, mã hóa kết nối chỉ giải quyết một phần bài toán bảo vệ. Một dịch vụ cần biết nó đang nói chuyện với máy chủ nào; trong nhiều luồng nội bộ, máy chủ cũng cần biết chính xác workload nào đang gọi mình. TLS cung cấp kênh truyền được mã hóa và xác thực máy chủ. Mutual TLS (mTLS) mở rộng quá trình đó bằng cách yêu cầu cả hai phía chứng minh danh tính bằng chứng thư số.

Sau bài học, người học có thể:

- Phân biệt TLS, xác thực máy chủ, mTLS và authorization ở tầng ứng dụng.
- Đọc một certificate chain và giải thích vai trò của root CA, intermediate CA, leaf certificate, trust store và key store.
- Chọn TLS security policy theo yêu cầu bảo mật, tương thích và tuân thủ.
- Thiết kế vòng đời chứng thư cho giao tiếp public, partner-to-service và service-to-service.
- Chọn cách triển khai mTLS phù hợp với Application Load Balancer, Network Load Balancer, API Gateway hoặc ứng dụng chạy trên EC2, ECS và EKS.
- Vận hành trust bundle, xoay vòng CA, thu hồi chứng thư và điều tra lỗi handshake.

## 1. Bối cảnh: bảo vệ đường đi của request

Hãy xét một hệ thống thương mại điện tử có các thành phần sau:

- Ứng dụng di động và trình duyệt gọi API công khai.
- API gateway hoặc load balancer nhận kết nối từ bên ngoài.
- Dịch vụ Checkout gọi Order, Inventory và Payment.
- Một đối tác vận chuyển gửi webhook vào hệ thống.
- Các workload chạy trên ECS, EKS và EC2, có thể nằm ở nhiều subnet hoặc account.

Security group, network ACL và route table quyết định đường đi của packet. Chúng giúp giới hạn nguồn và đích, nhưng không chứng minh danh tính ở cấp workload. Nếu hai dịch vụ cùng nằm trong một VPC, việc kết nối được phép qua security group không tự động có nghĩa request đến từ đúng dịch vụ Checkout.

TLS bảo vệ dữ liệu trên từng kết nối. mTLS bổ sung xác thực danh tính phía client bằng certificate. Ứng dụng vẫn cần authorization để quyết định danh tính đã xác thực được phép thực hiện hành động nào.

| Câu hỏi | Cơ chế giải quyết |
|---|---|
| Ai có thể mở kết nối đến cổng 443? | Security group, network ACL, firewall, routing |
| Dữ liệu trên đường truyền có bị đọc hoặc sửa trái phép không? | TLS và cấu hình cipher/protocol phù hợp |
| Client có đang kết nối đúng máy chủ không? | Server certificate và hostname verification |
| Client hoặc workload gọi API có danh tính được tin cậy không? | Client certificate trong mTLS |
| Danh tính đó được phép đọc đơn hàng hay hoàn tiền không? | Authorization trong ứng dụng hoặc policy engine |

Không nên gộp các câu hỏi này thành một. Một kết nối mTLS thành công vẫn có thể mang một request không được phép.

## 2. TLS bảo vệ điều gì?

TLS (Transport Layer Security) tạo một kênh truyền giữa hai endpoint. Trong handshake, hai bên thương lượng phiên bản giao thức và bộ thuật toán mật mã, xác lập khóa phiên, sau đó bảo vệ dữ liệu bằng mã hóa có xác thực. TLS hiện đại giúp đạt ba thuộc tính chính:

1. **Confidentiality:** người quan sát trên đường truyền không đọc được nội dung.
2. **Integrity:** dữ liệu bị sửa trong lúc truyền sẽ bị phát hiện.
3. **Authentication:** thông thường client xác minh danh tính server thông qua certificate. Với mTLS, server cũng xác minh client.

TLS không tự mã hóa dữ liệu khi dữ liệu đã đến process đích. Nó cũng không bảo vệ một endpoint đã bị chiếm quyền, không xác minh tính đúng đắn nghiệp vụ và không thay thế mã hóa dữ liệu lưu trữ.

### 2.1. Server authentication

Khi trình duyệt truy cập https://shop.example.com, server gửi certificate. Client kiểm tra:

- Certificate còn hiệu lực tại thời điểm hiện tại.
- Certificate được ký bởi CA nằm trong trust store của client, qua một chuỗi chữ ký hợp lệ.
- Tên miền mà client truy cập khớp với Subject Alternative Name (SAN) trong certificate.
- Thuật toán, key size và chữ ký đáp ứng chính sách của client.
- Các kiểm tra thu hồi mà client hoặc môi trường thực hiện, nếu được cấu hình và hỗ trợ.

Nếu certificate có tên shop.example.net nhưng client gọi shop.example.com, xác minh hostname phải thất bại dù certificate được ký bởi một CA công khai đáng tin cậy.

### 2.2. Client authentication

Trong TLS một chiều thông thường, server không yêu cầu client trình certificate. Server có thể xác thực người dùng ở tầng HTTP bằng session, OAuth 2.0, OIDC, API key hoặc cơ chế khác.

Trong mTLS, server gửi yêu cầu certificate trong handshake. Client gửi certificate và chứng minh đang sở hữu private key tương ứng. Server kiểm tra certificate chain và các điều kiện liên quan trước khi chấp nhận handshake.

Certificate chỉ chứng minh một public key được CA cấp cho một danh tính theo chính sách của CA. Nó không tự chứng minh người sở hữu certificate có quyền gọi mọi API.

## 3. Đọc certificate và certificate chain

Certificate X.509 gắn một public key với danh tính và được CA ký. Các trường quan trọng gồm:

| Trường | Ý nghĩa vận hành |
|---|---|
| Subject | Danh tính được ghi trong certificate; không nên chỉ dựa vào Common Name cho thiết kế mới |
| Subject Alternative Name (SAN) | DNS name, URI hoặc định danh khác mà certificate đại diện |
| Issuer | CA đã ký certificate |
| Serial Number | Số định danh certificate trong phạm vi CA |
| Not Before / Not After | Khoảng thời gian certificate có hiệu lực |
| Public Key | Khóa công khai dùng trong cơ chế mật mã |
| Key Usage / Extended Key Usage | Giới hạn cách dùng key, ví dụ serverAuth hoặc clientAuth |
| Signature Algorithm | Thuật toán CA dùng để ký certificate |

Một certificate thường không tự tạo thành một trust chain hoàn chỉnh. Ví dụ:

~~~text
Corporate Root CA
  └── Workload Issuing CA
        ├── checkout.prod.internal
        ├── inventory.prod.internal
        └── payment.prod.internal
~~~

- **Root CA:** trust anchor ở đỉnh hệ thống PKI. Private key của root CA cần được bảo vệ nghiêm ngặt; nhiều tổ chức giữ root CA offline.
- **Intermediate CA:** được root CA ký và dùng để phát hành certificate cho workload. Có thể phân tách theo môi trường, đơn vị hoặc mục đích.
- **Leaf certificate:** certificate của server, client, service hoặc workload cụ thể.
- **Certificate chain:** các certificate nối từ leaf qua intermediate đến trust anchor.

Một client thường cài root CA hoặc trust anchor phù hợp vào trust store. Server có trách nhiệm trình bày các intermediate cần thiết theo cách tương thích với client. Việc thiếu intermediate là nguyên nhân phổ biến gây lỗi xác minh dù root CA đã được cài.

### 3.1. Trust store và key store

Hai khái niệm này thường bị nhầm:

- **Trust store** chứa CA certificate mà một process tin cậy để xác minh certificate peer.
- **Key store** chứa private key và certificate của chính process, thường kèm certificate chain.

Trong kết nối mTLS giữa Service A và Service B:

- A cần key store chứa certificate và private key của A để chứng minh danh tính client.
- A cần trust store chứa CA mà A tin để xác minh certificate server của B.
- B cần key store chứa certificate và private key của B để chứng minh danh tính server.
- B cần trust store chứa CA mà B tin để xác minh certificate client của A.

Mỗi bên có thể dùng một file PKCS#12 chứa nhiều entry hoặc tách riêng trust store và key store. Điều quan trọng là phân biệt private key của workload với public certificate của CA.

### 3.2. Không chia sẻ private key

Không đưa private key của root CA hoặc workload vào source code, container image, Git, AMI dùng chung hay log. Mỗi workload cần một key pair riêng. Quyền đọc secret phải giới hạn theo workload; quy trình cấp phát và xoay vòng phải có thể kiểm toán.

AWS Certificate Manager quản lý private key của các certificate được tích hợp với dịch vụ AWS. Khi cần triển khai certificate private ra máy chủ hoặc ứng dụng do mình quản lý, có thể xuất private certificate qua ACM theo điều kiện hỗ trợ và phải bảo vệ file key đã xuất. AWS Private CA trực tiếp cấp certificate theo CSR là một luồng khác; trong luồng này caller tự tạo và giữ private key.

## 4. TLS policy: phiên bản và cipher suite

Certificate trả lời câu hỏi danh tính; TLS security policy quyết định các phiên bản giao thức và cipher suite mà endpoint chấp nhận. Chọn certificate tốt nhưng vẫn cho phép TLS lỗi thời hoặc cipher yếu có thể làm giảm mức bảo vệ của toàn kết nối.

### 4.1. TLS 1.2 và TLS 1.3

Với hệ thống mới, nên đặt TLS 1.2 làm mức tối thiểu tương thích rộng và ưu tiên TLS 1.3 khi client hỗ trợ. TLS 1.0 và TLS 1.1 đã lỗi thời; không nên bật chỉ để giữ một client cũ mà chưa đánh giá rủi ro và kế hoạch thay thế.

TLS 1.3 đơn giản hóa bộ cipher được phép, loại bỏ nhiều lựa chọn cũ và cải thiện handshake. TLS 1.2 vẫn có thể an toàn nếu cấu hình cipher hiện đại, có forward secrecy và loại bỏ các thuật toán yếu.

**Forward secrecy** giúp bảo vệ các phiên đã ghi lại trong quá khứ nếu private key dài hạn của server bị lộ về sau, với điều kiện phiên dùng cơ chế trao đổi khóa ephemeral phù hợp.

### 4.2. Cách chọn policy

Không chọn policy chỉ vì tên có chữ “TLS 1.3”. Trước khi áp dụng, hãy xác định:

1. Tập client thực tế và phiên bản TLS/cipher chúng hỗ trợ.
2. Yêu cầu tối thiểu của tiêu chuẩn nội bộ hoặc quy định.
3. Có cần FIPS validated cryptographic module hoặc policy FIPS hay không.
4. Có yêu cầu về thuật toán hậu lượng tử hoặc RFC cụ thể hay không.
5. Các kết nối backend có tương thích với policy mà dịch vụ AWS sử dụng hay không.

Elastic Load Balancing cung cấp nhiều nhóm policy cho ALB và NLB, gồm policy TLS 1.2/1.3, FIPS, policy có thuật toán hậu lượng tử và một số policy tương thích. Danh sách và tên policy thay đổi theo dịch vụ. Dùng danh sách hiện hành trong tài liệu của đúng loại load balancer và Region trước khi triển khai.

Ví dụ tên policy ALB có hỗ trợ TLS 1.3 và TLS 1.2:

~~~text
ELBSecurityPolicy-TLS13-1-2-2021-06
~~~

Tên trên là ví dụ để nhận diện cách đặt tên, không phải lựa chọn mặc định cho mọi workload. Nếu tổ chức cần policy FIPS hoặc hậu lượng tử, phải kiểm tra cả front-end, backend, client và target trước khi chuyển đổi.

### 4.3. Kiểm tra tương thích trước khi siết policy

Một lần đổi policy có thể làm client cũ không kết nối được. Quy trình triển khai nên gồm:

- Thu thập TLS protocol, cipher và lỗi handshake hiện tại từ access log hoặc connection log nếu dịch vụ hỗ trợ.
- Phân nhóm client theo phiên bản ứng dụng, hệ điều hành, thư viện TLS và mức độ quan trọng.
- Thử policy mới ở môi trường test với cùng loại client.
- Theo dõi tỷ lệ handshake thất bại và request lỗi sau thay đổi.
- Có phương án rollback policy đã được kiểm thử.

Với ALB, access log và connection log cung cấp dữ liệu để quan sát giao thức và cipher được thương lượng. Dữ liệu log giúp quyết định dựa trên client thực tế thay vì giả định.

## 5. mTLS handshake và mô hình tin cậy

Trong mTLS, cả hai bên đều xác minh certificate của peer. Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant A as Client / Service A
    participant B as Server / Service B
    A->>B: ClientHello (protocol, cipher, key share)
    B->>A: ServerHello + server certificate + CertificateRequest
    A->>A: Verify server chain, SAN, validity
    A->>B: Client certificate + proof of private key
    B->>B: Verify client chain, usage, validity, revocation policy
    A->>B: Finished
    B->>A: Finished
    A->>B: Encrypted application request
    B->>B: Map certificate identity to authorization policy
~~~

Chi tiết message khác nhau giữa TLS 1.2 và TLS 1.3, nhưng nguyên tắc vận hành giống nhau: hai bên thống nhất khóa phiên và xác minh danh tính theo trust policy.

Một hệ thống mTLS cần trả lời rõ:

- CA nào được phép cấp certificate cho workload?
- Certificate được phép dùng cho clientAuth, serverAuth hay cả hai?
- Danh tính workload nằm ở SAN nào?
- Service nào được phép tin CA đó?
- Certificate bị thu hồi hoặc hết hạn được xử lý thế nào?
- Danh tính đã xác minh được ánh xạ sang quyền nghiệp vụ ra sao?

### 5.1. Trust boundary

Trust store định nghĩa trust boundary. Nếu tất cả service cùng tin một root CA rộng, mọi certificate do CA đó cấp có thể vượt qua bước xác minh TLS. Vì vậy, việc phân chia CA theo môi trường và mục đích giúp giảm blast radius.

Ví dụ:

| Trust domain | Workload | Quy tắc |
|---|---|---|
| dev | checkout-dev, inventory-dev | Chỉ dùng cho môi trường phát triển |
| staging | checkout-stg, payment-stg | Không chấp nhận certificate từ dev |
| production | checkout-prod, payment-prod | Issuing CA riêng, quyền cấp phát hạn chế |
| partner | đối tác vận chuyển | Trust riêng theo đối tác hoặc nhóm đối tác |

Không đưa certificate của từng client vào trust store như một danh sách tĩnh nếu có thể dùng CA chuyên biệt. Trust theo CA giúp vận hành quy mô lớn hơn, nhưng yêu cầu kiểm soát quyền phát hành certificate chặt chẽ.

### 5.2. Xác thực certificate không phải authorization

Sau khi handshake thành công, ứng dụng cần lấy danh tính đã được xác minh và ánh xạ sang policy. Ví dụ:

| Danh tính certificate | Quyền ứng dụng |
|---|---|
| spiffe://shop/prod/checkout hoặc SAN URI tương đương | Gọi Order API để tạo đơn |
| spiffe://shop/prod/inventory | Cập nhật tồn kho qua endpoint nội bộ |
| Certificate của partner-carrier-a | Gửi trạng thái vận chuyển cho shipment của partner A |

Đây là ví dụ định danh logic; định dạng SAN URI cụ thể phải thống nhất với hệ thống cấp certificate. Không nên cấp quyền chỉ dựa trên chuỗi Subject do client tự gửi trong HTTP header. Hãy xác minh certificate tại TLS endpoint và chỉ chuyển identity đã được xác thực qua một đường truyền backend được bảo vệ.

## 6. Xây dựng PKI và vòng đời certificate

Một PKI dùng cho workload cần quy trình xuyên suốt:

~~~mermaid
flowchart TD
    A[Định nghĩa identity và trust domain] --> B[CA policy và quyền phát hành]
    B --> C[Tạo key pair tại workload hoặc nơi quản lý key]
    C --> D[CSR / yêu cầu cấp certificate]
    D --> E[CA xác minh và ký]
    E --> F[Phân phối certificate chain]
    F --> G[Thiết lập TLS hoặc mTLS]
    G --> H[Theo dõi expiry và lỗi handshake]
    H --> I[Renew / rotate / revoke]
    I --> F
~~~

### 6.1. Phát hành

Quy trình cấp certificate cần xác minh caller được phép đại diện cho identity yêu cầu. Một role có quyền gọi API cấp certificate không nên được phép yêu cầu tùy ý SAN của một workload khác. Giới hạn template, subject, SAN, key usage và thời hạn để giảm khả năng lạm dụng.

### 6.2. Gia hạn và xoay vòng

Certificate có ngày hết hạn. Gia hạn certificate và xoay key pair là hai thao tác liên quan nhưng khác nhau. Nếu chỉ cấp lại certificate với cùng key pair, rủi ro khi private key đã bị lộ vẫn còn.

Một quy trình xoay vòng an toàn thường:

1. Tạo key pair mới cho workload.
2. Xin certificate mới từ CA được tin cậy.
3. Cài certificate và chain mới, nhưng chưa xóa certificate cũ nếu còn client cần nó.
4. Kiểm tra kết nối hai chiều bằng certificate mới.
5. Chuyển toàn bộ traffic sang certificate mới.
6. Thu hồi hoặc ngừng tin certificate cũ theo chính sách.
7. Xóa key cũ khỏi nơi lưu trữ sau khi hết thời gian rollback.

Khi thay CA, nên có giai đoạn overlap: trust store chấp nhận CA cũ và CA mới, workload chuyển dần sang certificate từ CA mới, sau đó loại CA cũ khỏi trust store. Nếu xóa CA cũ trước khi mọi client và server chuyển đổi, kết nối sẽ thất bại đồng loạt.

### 6.3. Thu hồi

Certificate có thể cần bị thu hồi trước ngày hết hạn khi private key bị lộ, workload bị xóa hoặc danh tính không còn hợp lệ. Các cơ chế thường gặp:

- **CRL (Certificate Revocation List):** danh sách serial number bị thu hồi do CA phát hành.
- **OCSP (Online Certificate Status Protocol):** truy vấn trạng thái certificate qua responder.
- **Short-lived certificate:** rút ngắn thời gian sống để giảm cửa sổ rủi ro, nếu hệ thống cấp phát và phân phối đáp ứng được.

Không phải mọi dịch vụ AWS đều kiểm tra thu hồi giống nhau. Ví dụ, API Gateway mTLS không kiểm tra certificate đã bị revoke hay chưa. Nếu yêu cầu thu hồi tức thời, phải chọn kiến trúc có cơ chế đáp ứng yêu cầu đó hoặc bổ sung kiểm tra ở tầng ứng dụng.

### 6.4. Quản lý private key

Private key của root CA cần mức bảo vệ cao hơn key của leaf certificate. Hãy giới hạn quyền phát hành CA, bật audit, bảo vệ quy trình backup và có quy trình xử lý compromise. Với key của workload, ưu tiên tạo key trong môi trường kiểm soát được và không phân phối một key dùng chung cho nhiều replica.

AWS Private CA quản lý CA hierarchy và private key CA trong dịch vụ. IAM policy và CA policy quyết định ai được tạo CA, cấp certificate, thu hồi hoặc thay đổi cấu hình. Dùng role chuyên biệt và giới hạn quyền cấp certificate theo template/identity.

## 7. Các lựa chọn certificate trong AWS

| Dịch vụ | Phù hợp khi | Điểm cần nhớ |
|---|---|---|
| AWS Certificate Manager (ACM) public certificate | Endpoint public dùng dịch vụ AWS tích hợp như ALB, CloudFront, API Gateway | ACM quản lý certificate và private key cho tích hợp được hỗ trợ; DNS validation thường phù hợp cho tự động gia hạn |
| ACM private certificate với AWS Private CA | Endpoint hoặc workload cần PKI riêng, đặc biệt khi gắn với dịch vụ tích hợp ACM | Trust được thiết lập khi client cài CA phù hợp |
| AWS Private CA cấp trực tiếp | Cần tự tạo CSR, tự giữ private key hoặc tích hợp PKI tùy biến | Caller chịu trách nhiệm quản lý key và vòng đời certificate |
| Certificate import | Đã có PKI bên ngoài hoặc certificate do CA khác phát hành | Tổ chức tự quản lý renewal, key và quy trình cập nhật ở nơi triển khai |

ACM public certificate phù hợp với domain công khai. ACM private certificate phù hợp với trust domain nội bộ. Certificate private không tự động được browser hoặc client bên ngoài tin; client phải được cài CA tương ứng.

### 7.1. ACM và managed renewal

ACM có thể tự gia hạn certificate đủ điều kiện. Với private certificate được yêu cầu qua ACM console hoặc ACM RequestCertificate API, ACM có thể thực hiện managed renewal khi CA còn hoạt động và điều kiện sử dụng được đáp ứng. Certificate được cấp trực tiếp bằng AWS Private CA IssueCertificate API không thuộc luồng managed renewal của ACM.

Nếu certificate private được export và cài thủ công trên máy chủ, việc ACM tạo certificate mới không đồng nghĩa máy chủ đã được cập nhật. Cần một pipeline phân phối, reload process, kiểm tra kết nối và theo dõi phiên bản đang hoạt động.

### 7.2. AWS Private CA hierarchy

AWS Private CA cho phép xây dựng root CA và subordinate CA cho PKI nội bộ. Có thể tách CA theo môi trường hoặc mục đích, đồng thời cấu hình CRL và OCSP khi phù hợp.

Một mô hình tham khảo:

~~~text
Organization Root CA
  ├── Production Issuing CA
  │     ├── Server certificates
  │     └── Client/workload certificates
  ├── NonProduction Issuing CA
  │     ├── Development
  │     └── Staging
  └── Partner Issuing CA
        └── Certificates for approved integrations
~~~

Không nên tạo nhiều CA chỉ để tăng số lượng. Mỗi CA mới làm tăng chi phí, quy trình vận hành và số trust anchor cần quản lý. Chọn ranh giới CA theo trust boundary và blast radius.

## 8. mTLS trên Application Load Balancer

Application Load Balancer (ALB) hỗ trợ mTLS ở HTTPS listener. ALB có hai mode với mục đích khác nhau:

| Mode | Hành vi | Khi phù hợp |
|---|---|---|
| Verify | ALB kiểm tra X.509 client certificate bằng trust store; có thể cấu hình certificate revocation list | Muốn ALB thực hiện xác thực client trước khi forward request |
| Passthrough | ALB nhận certificate chain và chuyển thông tin certificate đến target qua HTTP header; ứng dụng target tự xác minh và quyết định | Muốn ứng dụng kiểm soát logic xác thực hoặc dùng thông tin chain đầy đủ |

Trong verify mode, tạo trust store từ CA bundle, có thể thêm CRL, rồi gắn trust store vào HTTPS listener. Một secure listener chỉ gắn một trust store tại một thời điểm; một trust store có thể được nhiều listener sử dụng.

### 8.1. Luồng verify mode

~~~mermaid
flowchart LR
    C[Partner client] -->|TLS + client certificate| A[ALB HTTPS listener]
    A -->|Verify chain / expiry / revocation policy| T[Trust store]
    T -->|Trusted| F[Forward request]
    T -->|Untrusted| X[Reject handshake]
    F --> B[Application target]
    B --> Z[Authorization theo partner identity]
~~~

ALB xác minh certificate ở front end. Ứng dụng vẫn cần xác định certificate identity tương ứng với partner nào và partner đó được phép truy cập resource nào. Khi ứng dụng sử dụng các HTTP header X-Amzn-Mtls-*, chỉ tin các header này khi target chỉ nhận traffic từ ALB đáng tin cậy và đường truy cập trực tiếp đến target đã được chặn. Không để client tự gửi header cùng tên qua một đường khác rồi được ứng dụng xem như identity đã xác thực.

### 8.2. Ví dụ tạo trust store và gắn vào listener

Giả sử CA bundle PEM đã được đặt trong một S3 bucket bảo mật. Ví dụ sau minh họa cấu hình ALB hiện có; thay giá trị ARN, bucket và key theo môi trường:

~~~bash
aws elbv2 create-trust-store --name partner-client-ca --ca-certificates-bundle-s3-bucket security-artifacts --ca-certificates-bundle-s3-key pki/partner-ca-bundle.pem
~~~

Sau khi tạo trust store, lấy TrustStoreArn từ kết quả và gắn vào listener:

~~~bash
aws elbv2 modify-listener --listener-arn arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/shop/abc/def --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 --mutual-authentication "Mode=verify,TrustStoreArn=arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:truststore/partner-client-ca/1234567890"
~~~

Các lệnh trên cần quyền IAM phù hợp với Elastic Load Balancing và quyền đọc S3 object tương ứng. Trust store chỉ được dùng sau khi được gắn vào listener. Trong triển khai thật, hãy kiểm tra trạng thái trust store, bundle PEM, CRL, quota và log handshake trước khi mở traffic.

### 8.3. Passthrough mode

Passthrough mode không có nghĩa ALB đã xác minh client certificate. ALB chuyển certificate chain đến target bằng header theo định dạng được tài liệu AWS mô tả. Target phải xác minh chain, thời hạn, usage và chính sách thu hồi cần thiết. Nếu ứng dụng chỉ decode Subject rồi tin ngay giá trị đó, client có thể giả mạo danh tính bằng certificate không hợp lệ.

Chọn passthrough khi ứng dụng cần tự điều khiển logic certificate hoặc phải sử dụng các thuộc tính chain cụ thể. Chọn verify khi ALB có thể thực hiện phần xác minh phù hợp và muốn giảm trách nhiệm xử lý certificate trong ứng dụng.

## 9. mTLS trên Network Load Balancer

Network Load Balancer (NLB) hỗ trợ mTLS verify mode trên TLS listener. NLB xác minh X.509 client certificate với trust store, sau đó có thể áp dụng identity filters và kiểm tra thu hồi theo cấu hình.

Nếu cần chuyển nguyên TLS connection đến target để ứng dụng hoặc proxy tự thực hiện mTLS, dùng TCP listener trên cổng TLS thay vì TLS listener. Với TCP listener, NLB chuyển tiếp traffic đã mã hóa; target kết thúc TLS và chịu trách nhiệm xác minh certificate.

| Kiểu listener | Nơi kết thúc TLS | mTLS |
|---|---|---|
| NLB TLS listener | NLB | Có verify mode theo tính năng mTLS của NLB |
| NLB TCP listener trên 443 | Target | Target tự triển khai mTLS |

Một lưu ý quan trọng ở chiều backend: khi target group dùng protocol TLS, NLB tạo kết nối TLS tới target nhưng không xác minh certificate của target. Do đó không được xem cấu hình này là cơ chế xác thực danh tính target bằng certificate. AWS mô tả traffic trong VPC được bảo vệ ở cấp packet trong mô hình đó; nếu threat model yêu cầu xác minh identity của backend, hãy thiết kế mTLS ở target hoặc proxy và kiểm soát network path tương ứng.

## 10. mTLS trên Amazon API Gateway

API Gateway hỗ trợ mTLS cho custom domain Regional của REST API và HTTP API. Client phải gửi certificate được trust store chấp nhận khi gọi API qua custom domain.

Các điều kiện chính:

- Dùng Regional custom domain.
- REST API yêu cầu security policy TLS_1_2.
- HTTP API yêu cầu phiên bản TLS tối thiểu 1.2.
- Trust store được lưu trong Amazon S3.
- Certificate của client phải có issuer và chain đầy đủ tới root CA nằm trong trust store.
- mTLS không được hỗ trợ cho private API.
- API Gateway không kiểm tra certificate đã bị revoke hay chưa.

### 10.1. Ví dụ cấu hình HTTP API custom domain

~~~bash
aws apigatewayv2 create-domain-name --domain-name api.partner.example.com --domain-name-configurations CertificateArn=arn:aws:acm:ap-southeast-1:111122223333:certificate/12345678-1234-1234-1234-123456789012,EndpointType=REGIONAL,SecurityPolicy=TLS_1_2 --mutual-tls-authentication TruststoreUri=s3://security-artifacts/pki/partner-truststore.pem
~~~

Sau khi tạo custom domain, cần cấu hình API mapping và DNS record theo thiết kế. Trust store có thể chứa certificate của public hoặc private CA. Với API Gateway, bật versioning cho bucket để có thể chỉ định phiên bản trust store khi cập nhật.

### 10.2. Cập nhật trust store

Khi thêm hoặc thay CA, tải bundle mới lên S3 rồi cập nhật custom domain sang object version phù hợp. Với REST API, API Gateway hỗ trợ cập nhật trường truststoreVersion; với HTTP API, cấu hình mutual TLS cũng có trường version tương ứng.

API Gateway trả warning khi xử lý trust store có certificate không hợp lệ tại thời điểm cập nhật domain. Dịch vụ không tự gửi cảnh báo khi một certificate trong trust store hết hạn sau đó. Đội vận hành cần tự giám sát ngày hết hạn của CA và leaf certificate.

### 10.3. Chọn API Gateway hay ALB

API Gateway phù hợp với lớp quản lý API, custom domain, API mapping, throttling và tích hợp API. ALB phù hợp với routing HTTP/HTTPS tới target group và các workload web. Nếu yêu cầu thu hồi client certificate phải được thực thi ở điểm kết thúc TLS, lưu ý API Gateway mTLS không kiểm tra revocation; ALB có thể cấu hình CRL cho verify mode.

## 11. TLS giữa các workload trên EC2, ECS và EKS

Khi service gọi service, mỗi hop cần được xem như một kết nối riêng. TLS ở public ALB không tự bảo vệ kết nối từ ALB đến target, hoặc từ Checkout đến Payment.

Một kiến trúc tham khảo:

~~~mermaid
flowchart LR
    subgraph VPC
      A[Checkout workload<br/>client cert + private key]
      B[Payment workload<br/>server cert + client trust]
      C[Inventory workload<br/>server cert + client trust]
      A -->|mTLS| B
      A -->|mTLS| C
    end
    CA[AWS Private CA / enterprise CA] -->|Issue identities| A
    CA -->|Issue identities| B
    CA -->|Issue identities| C
~~~

Có thể triển khai mTLS tại:

- **Ứng dụng:** Spring Boot, Netty, Node.js, Go hoặc server tự cấu hình TLS.
- **Sidecar/proxy:** Envoy hoặc một service mesh phù hợp quản lý TLS và certificate ở cạnh workload.
- **Load balancer/API gateway:** kết thúc mTLS tại điểm vào hệ thống rồi chuyển identity đã xác thực cho backend qua kênh được bảo vệ.

Trên ECS hoặc EKS, việc dùng sidecar không tự động tạo ra mTLS. Cần cấu hình cấp certificate, phân phối trust bundle, policy giữa service, readiness khi certificate được xoay vòng và giới hạn quyền đọc private key. Đừng giả định VPC encryption hoặc security group đã cung cấp xác thực workload.

### 11.1. TLS termination và từng chặng kết nối

Giả sử client kết nối HTTPS đến ALB, sau đó ALB forward HTTP đến ECS. Kết nối client–ALB được mã hóa, nhưng chặng ALB–ECS không dùng TLS.

Nếu ALB forward HTTPS đến target, chặng backend được mã hóa. Tuy nhiên, ALB không xác minh certificate của target trong target group HTTPS. Nếu cần xác minh identity backend bằng certificate, phải bổ sung một cơ chế phù hợp ở ứng dụng/proxy hoặc thiết kế lại điểm kết thúc TLS.

| Chặng | Mục tiêu | Cấu hình có thể dùng |
|---|---|---|
| Client → ALB | Bảo vệ kết nối public | HTTPS listener, ACM certificate, TLS security policy |
| Client → ALB | Xác minh client/partner | ALB mTLS verify hoặc passthrough |
| ALB → target | Mã hóa traffic nội bộ | HTTPS target group |
| Service A → Service B | Xác minh hai workload | mTLS tại app hoặc sidecar/proxy |
| Partner → API Gateway | Xác minh partner certificate | Regional custom domain và mTLS trust store |

Không gọi một kiến trúc là “end-to-end mTLS” nếu TLS kết thúc ở ALB và backend chỉ nhận HTTP. Hãy ghi rõ từng TLS hop, nơi giải mã và nơi thực hiện authorization.

## 12. Ví dụ cấu hình mTLS cho ứng dụng Java

Ví dụ dưới đây dùng Spring Boot để minh họa server yêu cầu client certificate. Trong thực tế, secret chứa key store phải được cấp qua cơ chế quản lý secret phù hợp và không đưa vào image.

### 12.1. Tạo trust store từ CA certificate

Giả sử workload-root-ca.pem là CA certificate mà server dùng để xác minh client:

~~~bash
keytool -importcert -noprompt -alias workload-root-ca -file workload-root-ca.pem -keystore client-ca-truststore.p12 -storetype PKCS12
~~~

Lệnh sẽ hỏi mật khẩu trust store nếu chưa cung cấp. Trong pipeline, không ghi mật khẩu thật vào command history hoặc repository.

### 12.2. Cấu hình server

Server cần key store chứa server certificate, private key và chain; trust store chứa CA được phép cấp client certificate:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:payment-server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=<injected-secret>
server.ssl.trust-store=classpath:client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=<injected-secret>
server.ssl.client-auth=need
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
~~~

client-auth=need yêu cầu client gửi certificate. Giá trị want cho phép client không gửi certificate, do đó không phù hợp nếu endpoint bắt buộc mTLS. Sau khi TLS handshake thành công, ứng dụng vẫn cần đọc principal/certificate đã được xác minh và áp dụng authorization.

### 12.3. Gọi bằng curl

Client cần certificate và private key của chính nó. --cacert chỉ CA dùng để xác minh server; --cert và --key dùng để chứng minh identity client:

~~~bash
curl --verbose --cacert server-root-ca.pem --cert checkout-client-chain.pem --key checkout-client.key https://payment.internal.example:8443/health
~~~

Không dùng --insecure để xử lý lỗi certificate trong production. Tùy chọn đó tắt xác minh certificate server và có thể che giấu lỗi trust hoặc hostname.

### 12.4. Kiểm tra handshake bằng OpenSSL

~~~bash
openssl s_client -connect payment.internal.example:8443 -servername payment.internal.example -CAfile server-root-ca.pem -cert checkout-client.pem -key checkout-client.key -verify_return_error -tls1_3
~~~

Nếu server không hỗ trợ TLS 1.3, có thể kiểm tra TLS 1.2 riêng trong môi trường test. Đừng hạ policy production chỉ để làm cho một lệnh test thành công.

## 13. Thiết kế trust policy giữa các service

Một trust policy tốt mô tả được cả identity, issuer, mục đích và quyền:

| Thuộc tính | Ví dụ chính sách |
|---|---|
| Issuer | Chỉ chấp nhận Production Workload Issuing CA |
| Environment | Certificate production không được dùng ở staging |
| SAN | Chỉ chấp nhận identity theo namespace đã đăng ký |
| EKU | Client certificate phải có clientAuth; server certificate phải có serverAuth |
| Validity | Certificate còn hiệu lực và nằm trong thời hạn tối đa được phép |
| Revocation | Kiểm tra CRL/OCSP nếu endpoint hỗ trợ và yêu cầu cần |
| Authorization | Checkout chỉ gọi các endpoint Order đã được cấp quyền |

### 13.1. Tách CA theo vai trò

Không nhất thiết phải có một CA cho mỗi microservice. Tuy nhiên, cần tránh một CA có quyền phát hành tùy ý cho toàn bộ môi trường. Có thể tách CA theo:

- Production và non-production.
- Server identity và client/workload identity nếu chính sách yêu cầu.
- Partner hoặc nhóm partner có mức tin cậy khác nhau.
- Account hoặc business unit có ranh giới quản trị riêng.

Quyết định tách CA cần cân bằng blast radius, chi phí, giới hạn dịch vụ và độ phức tạp vận hành.

### 13.2. Định danh workload

SAN là nơi phù hợp để gắn định danh máy chủ hoặc workload. DNS SAN phù hợp với tên DNS. URI SAN có thể biểu diễn một workload identity theo quy ước của tổ chức. Ứng dụng phải xác minh identity theo quy ước đó; không suy ra quyền chỉ từ IP address hoặc hostname do request tự khai báo.

## 14. Bảo vệ trust store và certificate artifact

Trust bundle là cấu hình bảo mật. Nếu kẻ tấn công thêm CA của họ vào trust bundle, các certificate do CA đó phát hành có thể được chấp nhận ở những nơi sử dụng bundle.

Đối với trust store trên S3:

- Bật block public access và bucket policy giới hạn principal được đọc/ghi.
- Dùng versioning để khôi phục phiên bản và triển khai thay đổi có kiểm soát.
- Bật mã hóa phù hợp, có thể dùng SSE-KMS theo yêu cầu quản trị.
- Ghi nhận thay đổi object, người cập nhật và phiên bản được triển khai.
- Không cho workload thông thường có quyền ghi trust bundle.
- Kiểm tra nội dung PEM và chain trước khi publish.

Với private key:

- Lưu trong secret manager hoặc hệ thống key management phù hợp.
- Giới hạn quyền đọc theo workload identity.
- Không log private key, passphrase hoặc toàn bộ secret.
- Không bake key vào container image, source repository hoặc AMI dùng chung.
- Xoay vòng khi nghi ngờ compromise và có quy trình thay thế certificate.

## 15. Giám sát và vận hành

TLS/mTLS thường chỉ được chú ý khi certificate hết hạn hoặc handshake thất bại. Hệ thống production cần chủ động theo dõi:

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Số ngày còn lại của server certificate | Có đủ thời gian gia hạn và phân phối không? |
| Số ngày còn lại của CA/intermediate | Có thể cấp certificate mới trong suốt vòng đời workload không? |
| TLS handshake failure | Lỗi tăng sau khi đổi policy, bundle hoặc certificate? |
| Protocol/cipher distribution | Client cũ nào còn dùng TLS yếu? |
| mTLS authentication failure | Client không gửi certificate, chain sai hay certificate hết hạn? |
| Trust store version | Listener/domain đang dùng bundle nào? |
| CA issuance/revocation events | Có yêu cầu cấp certificate bất thường hoặc thu hồi khẩn cấp không? |

Kết hợp các nguồn log phù hợp:

- ALB access log và connection log để điều tra request và TLS connection.
- CloudTrail để audit thao tác quản trị ACM, AWS Private CA, ELB và API Gateway.
- CloudWatch metrics/logs và EventBridge để cảnh báo, định tuyến sự kiện vận hành.
- Log ứng dụng để ghi identity đã xác minh, quyết định authorization và correlation ID.

Không ghi private key, passphrase hoặc dữ liệu certificate nhạy cảm không cần thiết vào log. Nếu log serial number hoặc subject để điều tra, xác định retention và quyền truy cập.

### 15.1. Quy trình cảnh báo certificate expiry

Một cảnh báo hữu ích nên có:

1. Tên service/domain hoặc workload identity.
2. Certificate ARN hoặc serial number, issuer và ngày hết hạn.
3. Nơi certificate đang được triển khai.
4. Owner chịu trách nhiệm gia hạn.
5. Trạng thái renewal và bước phân phối còn thiếu.
6. Link runbook và mức độ ưu tiên.

Đối với certificate do ACM quản lý, theo dõi trạng thái renewal và sự kiện liên quan. Đối với certificate được export hoặc cấp trực tiếp qua Private CA, theo dõi cả bước triển khai thực tế vì việc phát hành certificate mới chưa đảm bảo endpoint đã sử dụng nó.

## 16. Xử lý sự cố TLS và mTLS

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| certificate has expired | Leaf hoặc intermediate hết hạn; đồng hồ máy sai | Kiểm tra Not Before/Not After và thời gian hệ thống |
| unknown ca / unable to get local issuer certificate | Trust store thiếu root/intermediate hoặc dùng sai CA | In chain và kiểm tra issuer từng cấp |
| Hostname mismatch | SAN không chứa hostname client gọi | Kiểm tra DNS SAN và SNI |
| bad certificate | Client certificate sai chain, key usage hoặc không được chấp nhận | Kiểm tra EKU, key usage, CA và certificate request |
| handshake failure | Không có protocol/cipher chung hoặc cấu hình mTLS không khớp | So sánh TLS policy ở client/server và log handshake |
| ALB trả lỗi khi bật verify | Trust store không hợp lệ, CA bundle sai định dạng hoặc certificate client không trusted | Kiểm tra trust store, PEM, chain và CRL |
| API Gateway trả 403 khi gọi mTLS | Certificate không trusted, hết hạn hoặc thuật toán không hỗ trợ | Kiểm tra trust store và certificate client |
| Chỉ một nhóm client lỗi sau đổi policy | Client không hỗ trợ protocol/cipher mới | Đối chiếu connection log theo client và thời điểm thay đổi |
| Service A gọi B thất bại sau rotate | A chưa tin CA mới, B chưa nhận certificate mới hoặc chain thiếu | Kiểm tra trust bundle ở cả hai chiều |

### 16.1. Bộ lệnh kiểm tra certificate

Xem thông tin certificate:

~~~bash
openssl x509 -in client.pem -noout -subject -issuer -serial -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Kiểm tra chain với root CA và intermediate:

~~~bash
openssl verify -CAfile root-ca.pem -untrusted intermediate-ca.pem client.pem
~~~

Kiểm tra endpoint và TLS negotiation:

~~~bash
openssl s_client -connect api.example.com:443 -servername api.example.com -showcerts -verify_return_error
~~~

Khi điều tra, ghi lại hostname, thời điểm, client runtime, protocol, cipher, certificate issuer/serial và lỗi cụ thể. Không chia sẻ private key hoặc file keystore trong ticket.

## 17. Thực hành: bật mTLS cho partner gọi ALB

Mục tiêu lab là cho một partner đã được cấp client certificate gọi endpoint qua ALB. Chỉ certificate do CA trong trust store phát hành mới vượt qua bước xác thực.

### 17.1. Chuẩn bị

- Một ALB có HTTPS listener.
- Một server certificate hợp lệ trong ACM.
- Một CA bundle PEM chỉ chứa CA được phép cấp client certificate cho partner.
- Một S3 bucket private chứa CA bundle.
- Một client certificate và private key dành cho lab.
- IAM principal được phép quản lý trust store/listener và đọc object cần thiết.

Trong production, nên dùng CA được quản trị bằng AWS Private CA hoặc PKI doanh nghiệp. Không dùng root CA tự tạo cho lab làm trust anchor production.

### 17.2. Tạo trust store và bật verify mode

1. Upload CA bundle lên S3 private bucket.
2. Tạo trust store bằng aws elbv2 create-trust-store.
3. Gắn trust store vào HTTPS listener với Mode=verify.
4. Chọn TLS security policy đáp ứng chuẩn của tổ chức và tương thích với client.
5. Kiểm tra listener và trust store đã ở trạng thái sử dụng được.
6. Giới hạn security group của target chỉ nhận traffic từ ALB.

Lệnh minh họa:

~~~bash
aws elbv2 describe-listeners --listener-arns arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/shop/abc/def
~~~

### 17.3. Kiểm thử dương

Gọi endpoint bằng certificate do CA được tin cậy phát hành:

~~~bash
curl --verbose --cacert server-root-ca.pem --cert partner-client.pem --key partner-client.key https://partner-api.example.com/health
~~~

Kỳ vọng: TLS handshake hoàn tất và request đến ứng dụng. Ứng dụng nhận diện partner theo certificate metadata đã được ALB xác minh và áp dụng authorization phù hợp.

### 17.4. Kiểm thử âm

Thử lần lượt:

- Không gửi client certificate.
- Gửi certificate do CA không nằm trong trust store phát hành.
- Gửi certificate hết hạn.
- Gửi certificate không có mục đích client authentication phù hợp.
- Gửi request bằng hostname không khớp server certificate.

Kỳ vọng: các trường hợp không đáp ứng trust policy bị từ chối ở TLS hoặc tại lớp xác minh tương ứng. Ghi nhận chính xác lỗi ở phía client, ALB và ứng dụng; không chỉ dựa vào HTTP status để kết luận lỗi xảy ra ở lớp nào.

### 17.5. Xoay vòng CA trong lab

1. Chuẩn bị CA bundle mới có CA cũ và CA mới.
2. Cập nhật trust store theo quy trình của ALB.
3. Cấp client certificate mới từ CA mới.
4. Chuyển client sang certificate mới và xác nhận handshake.
5. Khi mọi client đã chuyển, loại CA cũ khỏi bundle.
6. Kiểm tra certificate cũ không còn được chấp nhận.

Lab hoàn tất khi certificate trusted được chấp nhận, certificate không trusted bị từ chối và quá trình chuyển CA không làm gián đoạn client hợp lệ.

## 18. Lựa chọn kiến trúc theo tình huống

| Tình huống | Lựa chọn gợi ý | Lý do và giới hạn |
|---|---|---|
| Website public cần HTTPS | ACM public certificate + ALB/CloudFront/API Gateway | Quản lý server certificate cho endpoint public |
| Đối tác gọi API qua HTTP API | API Gateway Regional custom domain + mTLS | API Gateway xác minh client certificate; không kiểm tra revocation |
| Đối tác gọi ứng dụng web qua ALB | ALB mTLS verify | ALB xác minh chain và hỗ trợ CRL theo cấu hình |
| Ứng dụng cần tự xử lý certificate chain | ALB passthrough | Backend phải tự xác minh đầy đủ |
| TCP service cần NLB và mTLS tại NLB | NLB TLS listener với verify mode | NLB xác minh client certificate theo trust store |
| Muốn giữ TLS handshake ở workload phía sau NLB | NLB TCP listener | Target kết thúc TLS và tự thực hiện mTLS |
| Hai microservice gọi nhau | mTLS tại ứng dụng hoặc sidecar/proxy | Mỗi workload có identity và policy riêng |
| Cần PKI nội bộ | AWS Private CA hoặc PKI doanh nghiệp | Kiểm soát issuer, trust domain và vòng đời certificate |

Không có một lựa chọn tối ưu cho mọi kết nối. Chọn điểm kết thúc TLS dựa trên nơi cần xác minh identity, yêu cầu thu hồi, khả năng vận hành certificate và mức độ kiểm soát backend.

## 19. Các lỗi thiết kế cần tránh

1. **Chỉ bật HTTPS ở ingress rồi cho rằng toàn hệ thống đã mã hóa.** Vẽ từng hop và xác định giao thức trên mỗi chặng.
2. **Dùng một CA cho mọi môi trường.** Certificate dev có thể bị chấp nhận ở production nếu cùng trust anchor.
3. **Chia sẻ một client private key cho nhiều service.** Không thể cô lập hoặc thu hồi từng identity.
4. **Tin Subject hoặc HTTP header mà không xác minh certificate.** Danh tính phải đến từ một bước xác thực đáng tin cậy.
5. **Nhầm TLS thành authorization.** Certificate hợp lệ không tự cấp quyền nghiệp vụ.
6. **Bỏ qua hostname verification.** Certificate được CA tin cậy ký vẫn có thể thuộc hostname khác.
7. **Đổi trust bundle và xóa CA cũ ngay lập tức.** Client chưa được rotate sẽ mất kết nối.
8. **Cho rằng ACM renewal đồng nghĩa workload đã cập nhật.** Certificate mới cần được phân phối và reload.
9. **Dùng API Gateway mTLS khi yêu cầu bắt buộc kiểm tra revocation tại gateway.** API Gateway không kiểm tra trạng thái revoke.
10. **Cho rằng HTTPS target group của ALB hoặc TLS target group của NLB xác minh certificate backend.** Hai load balancer không xác minh certificate target theo cách xác thực danh tính backend.
11. **Tắt xác minh bằng --insecure hoặc trust-all trong code.** Điều này mở cửa cho kết nối giả mạo.
12. **Không theo dõi CA expiry.** Leaf certificate có thể còn hạn nhưng CA ký nó đã hết hạn.
13. **Không audit quyền phát hành certificate.** Kẻ tấn công có thể xin certificate cho identity khác nếu quyền cấp phát quá rộng.
14. **Không thử certificate âm.** Chỉ kiểm thử happy path không chứng minh trust policy từ chối đúng.

## 20. Bài tập tự kiểm tra

### Câu 1

Một API public chạy HTTPS và xác minh server certificate. Điều gì còn thiếu nếu chỉ các hệ thống partner được phép gọi API?

**Đáp án:** Cần xác thực client/partner, ví dụ mTLS hoặc cơ chế identity khác. Sau khi xác thực, vẫn cần authorization để giới hạn partner vào đúng API và dữ liệu của họ.

### Câu 2

Trust store của Service A chứa root CA của Service B. A có cần private key của B không?

**Đáp án:** Không. A chỉ cần CA certificate để xác minh certificate server của B. Private key của B phải được giữ ở B. A cần key pair riêng nếu B yêu cầu A xác thực bằng mTLS.

### Câu 3

Vì sao certificate hợp lệ nhưng hostname verification vẫn có thể thất bại?

**Đáp án:** Certificate có thể được ký bởi CA đáng tin cậy nhưng SAN không chứa hostname mà client đang truy cập.

### Câu 4

ALB mTLS verify và passthrough khác nhau ở đâu?

**Đáp án:** Verify mode để ALB xác minh client certificate bằng trust store. Passthrough chuyển certificate chain đến target và target phải tự xác minh.

### Câu 5

API Gateway mTLS có phù hợp khi tổ chức yêu cầu gateway kiểm tra CRL trước mỗi kết nối không?

**Đáp án:** Không phù hợp nếu yêu cầu đó bắt buộc phải được thực hiện tại API Gateway, vì API Gateway mTLS không kiểm tra certificate revocation. Cần chọn endpoint có hỗ trợ revocation hoặc bổ sung thiết kế kiểm tra phù hợp.

### Câu 6

Vì sao không nên xóa CA cũ khỏi trust store ngay khi đã tạo CA mới?

**Đáp án:** Một số client/server vẫn có certificate do CA cũ cấp. Cần giai đoạn overlap để chuyển toàn bộ workload sang CA mới trước khi loại CA cũ.

### Câu 7

NLB TLS target group có xác minh certificate của target không?

**Đáp án:** Không. NLB tạo TLS connection tới target nhưng không validate certificate target. Nếu cần xác minh identity backend, phải thực hiện ở target/proxy hoặc kiến trúc khác.

### Câu 8

Một certificate do AWS Private CA IssueCertificate API cấp trực tiếp có tự động được ACM managed renewal không?

**Đáp án:** Không. Managed renewal của ACM áp dụng cho private certificate được yêu cầu qua ACM console hoặc ACM RequestCertificate API theo điều kiện của ACM.

### Câu 9

Nếu client và server đều hỗ trợ TLS 1.3 nhưng handshake thất bại sau khi đổi security policy, nên kiểm tra gì?

**Đáp án:** Kiểm tra cipher suite, signature algorithm, key type, SNI, certificate chain, client implementation và policy thực tế ở cả front-end/backend. Cùng hỗ trợ TLS 1.3 không đảm bảo mọi điều kiện handshake khác đều tương thích.

### Câu 10

Một client certificate hợp lệ có được phép gọi mọi endpoint của Payment không?

**Đáp án:** Không. Certificate chỉ xác thực identity. Payment cần ánh xạ identity sang authorization policy và giới hạn endpoint, action, tenant hoặc resource được phép.

## 21. Checklist trước khi đưa vào production

- [ ] Đã xác định TLS termination point cho từng hop.
- [ ] TLS 1.2 là mức tối thiểu tương thích; TLS 1.3 được bật khi các client hỗ trợ.
- [ ] Security policy đã được đối chiếu với yêu cầu bảo mật và compliance.
- [ ] Server certificate có SAN đúng hostname và chain đầy đủ.
- [ ] Client certificate có identity, EKU và validity phù hợp.
- [ ] Trust store chỉ chứa CA được phê duyệt cho đúng trust domain.
- [ ] Private key không nằm trong source code, image hoặc log.
- [ ] Quyền phát hành và thu hồi certificate được giới hạn, audit.
- [ ] Có quy trình renewal, distribution, reload và rollback.
- [ ] Có giai đoạn overlap khi xoay CA.
- [ ] Đã xác định dịch vụ nào kiểm tra revocation và dịch vụ nào không.
- [ ] Backend chỉ nhận identity header từ proxy/load balancer đáng tin cậy.
- [ ] Authorization được áp dụng sau xác thực certificate.
- [ ] Có cảnh báo certificate expiry và CA expiry.
- [ ] Có log/metrics để điều tra TLS handshake và client identity.
- [ ] Đã kiểm thử positive, negative, expiry, unknown CA và CA rotation.
- [ ] Có runbook xử lý private key compromise.

## 22. Tài liệu tham khảo chính thức

- [AWS: Configuring mutual TLS on an Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/configuring-mtls-with-elb.html)
- [AWS: Mutual authentication with TLS in Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/mutual-authentication.html)
- [AWS: Security policies for Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/describe-ssl-policies.html)
- [AWS: Authenticate clients using mutual TLS for Network Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/mutual-authentication.html)
- [AWS: Security policies for Network Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/describe-ssl-policies.html)
- [AWS: Mutual TLS for REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html)
- [AWS: Mutual TLS for HTTP APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-mutual-tls.html)
- [AWS: Certificate authorities in AWS Private CA](https://docs.aws.amazon.com/privateca/latest/userguide/creating-managing.html)
- [AWS: Manage the private CA lifecycle](https://docs.aws.amazon.com/privateca/latest/userguide/ca-lifecycle.html)
- [AWS: Private certificate renewal in ACM](https://docs.aws.amazon.com/acm/latest/userguide/renew-private-cert.html)
- [AWS: Export a private certificate from ACM](https://docs.aws.amazon.com/acm/latest/userguide/export-private.html)
- [AWS: Infrastructure security in Elastic Load Balancing](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/infrastructure-security.html)

Các tên policy, giới hạn quota và khả năng tích hợp có thể thay đổi theo dịch vụ và Region. Khi triển khai, đối chiếu tài liệu hiện hành của đúng dịch vụ AWS và kiểm thử với client thực tế.
