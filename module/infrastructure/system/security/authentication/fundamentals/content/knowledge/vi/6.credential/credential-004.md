# Certificate credential — Xác thực bằng chứng chỉ số

> **Chương:** Credential  
> **Chủ đề:** Certificate credential

**Certificate credential** là cơ chế dùng chứng chỉ số, thường theo chuẩn **X.509**, kết hợp với việc chứng minh quyền kiểm soát **khóa riêng** tương ứng để xác thực một chủ thể. Chủ thể có thể là máy chủ, dịch vụ nội bộ, thiết bị hoặc người dùng. Khóa công khai trong chứng chỉ được một bên cấp chứng chỉ (*Certificate Authority*, CA) ký xác nhận theo chính sách; bên kiểm tra chỉ chấp nhận danh tính khi chuỗi tin cậy, thuộc tính, thời hạn và bằng chứng sở hữu khóa đều đạt yêu cầu.

Điểm mấu chốt: **bản thân chứng chỉ là dữ liệu công khai, không phải bí mật dùng để đăng nhập**. Chỉ tải lên một tệp .crt hay biết số serial của chứng chỉ không chứng minh được người yêu cầu đang sở hữu credential. Hệ thống cần một giao thức *proof of possession* (chứng minh sở hữu khóa riêng), chẳng hạn **mutual TLS (mTLS)**, trong đó bên được xác thực ký dữ liệu gắn với phiên bắt tay TLS. Ngược lại, giữ được khóa riêng nhưng chứng chỉ không thuộc nguồn tin cậy hoặc không mang đúng danh tính cũng chưa đủ để được chấp nhận.

Bài học đặt chứng chỉ vào bức tranh của **SECURITY_AUTHENTICATION_FUNDAMENTALS**: hiểu ranh giới tin cậy và vận hành credential từ lúc cấp phát, xác thực, gia hạn đến thu hồi; phân biệt xác thực với phân quyền; phòng ngừa giả mạo danh tính, replay, phishing và lạm dụng truy cập.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích quan hệ giữa **chứng chỉ số**, **khóa công khai**, **khóa riêng**, **CA** và cơ chế chứng minh sở hữu khóa.
2. Đọc những trường X.509 quan trọng: Subject, SAN, Issuer, thời hạn, Key Usage, Extended Key Usage và Basic Constraints.
3. Mô tả việc xây dựng và xác minh **certificate chain** theo ranh giới tin cậy.
4. Giải thích một luồng **mTLS** và cách ánh xạ chứng chỉ sang danh tính nội bộ mà không nhầm lẫn với authorization.
5. Thiết kế cấp phát, lưu khóa, rotation, renewal, revocation và deprovisioning cho certificate credential.
6. Phát hiện những lỗi như bỏ qua kiểm tra SAN, tin mọi CA, lấy header client certificate chưa được bảo vệ hoặc sử dụng token mà không ràng buộc đúng danh tính.

## 2. Certificate credential gồm những gì?

Một chứng chỉ X.509 liên kết **khóa công khai** với một hoặc nhiều thông tin nhận diện, dưới chữ ký của CA hoặc bên phát hành tương ứng. Khóa riêng được tạo và quản lý bởi chủ thể, không được nhúng vào chứng chỉ công khai.

| Thành phần | Vai trò | Mức bí mật |
| --- | --- | --- |
| **Private key** | Ký bằng chứng để chứng minh đang kiểm soát credential | **Bí mật đặc biệt quan trọng**; ưu tiên phần cứng bảo vệ khóa |
| **Public key** | Cho bên xác minh kiểm tra chữ ký của chủ thể | Công khai |
| **Certificate (leaf/end-entity)** | Liên kết public key với tên định danh và các điều kiện do issuer ký | Công khai; phải kiểm tra tính hợp lệ |
| **Intermediate CA certificate** | Cho phép xây dựng chuỗi từ leaf tới root được tin | Thường công khai |
| **Trust anchor/root CA** | Điểm tin cậy do hệ thống kiểm tra chủ động cấu hình | Chứng chỉ công khai, nhưng quyết định tin cậy phải được bảo vệ |
| **Identity mapping / policy** | Quyết định chứng chỉ hợp lệ tương ứng với principal nào và có quyền gì | Cấu hình/phần mềm nội bộ cần bảo vệ |

Một tệp **PKCS#12/PFX** có thể đóng gói cả chứng chỉ lẫn khóa riêng, đôi khi được mã hóa bằng mật khẩu. Vì vậy không được suy luận mọi tệp có chữ “certificate” đều an toàn để chia sẻ. Ngược lại, tệp .cer/.crt thông thường chứa chứng chỉ công khai; kiểm tra **nội dung thực tế** trước khi phát hành hoặc lưu trữ.

### 2.1. Certificate, credential, assertion và quyền truy cập

Phân biệt bốn câu hỏi:

- **Certificate có hợp lệ không?** Chữ ký và chuỗi chứng chỉ có dẫn tới trust anchor được chấp nhận, đúng thời hạn, mục đích và ràng buộc không?
- **Bên kết nối có giữ khóa riêng không?** Có thực hiện được proof of possession theo giao thức an toàn không?
- **Đó là principal nào?** SAN/thuộc tính nhận diện có khớp danh tính kỳ vọng và quy tắc ánh xạ không?
- **Principal được phép làm gì?** Policy có cho principal gọi API, xem tài nguyên hoặc thực hiện hành động cụ thể không?

Ví dụ: chứng chỉ của dịch vụ lập báo cáo hợp lệ không đồng nghĩa dịch vụ được phép chuyển tiền. **Authentication** thiết lập danh tính theo mức tin cậy; **authorization** kiểm tra quyền trên hành động và tài nguyên. Hai bước phải tách biệt.

## 3. Bên trong chứng chỉ X.509

Chứng chỉ X.509 có cấu trúc dữ liệu được mã hóa DER, thường được biểu diễn dạng PEM với phần nội dung base64 và nhãn BEGIN CERTIFICATE/END CERTIFICATE. Những trường quan trọng:

| Trường / extension | Ý nghĩa | Điểm kiểm tra |
| --- | --- | --- |
| **Subject** | Tên hoặc thông tin nhận diện được nêu trong chứng chỉ | Không tự tin CN làm danh tính nếu hệ thống yêu cầu SAN |
| **Subject Alternative Name (SAN)** | DNS name, IP, URI, email hoặc loại tên được hỗ trợ | Kiểm tra **loại và giá trị** đúng danh tính kỳ vọng |
| **Issuer** | Bên đã phát hành/ký chứng chỉ | Chỉ tên Issuer chưa đủ; phải xác minh chữ ký và chuỗi |
| **Serial Number** | Số nhận diện chứng chỉ trong phạm vi issuer | Có thể phục vụ truy vết/thu hồi; không phải bằng chứng sở hữu |
| **Validity: notBefore/notAfter** | Khoảng thời gian chứng chỉ dự kiến có hiệu lực | Đồng hồ hệ thống cần đáng tin; hết hạn phải từ chối |
| **Subject Public Key Info** | Thuật toán và khóa công khai của chủ thể | Kiểm tra thuật toán/kích thước phù hợp chính sách |
| **Signature Algorithm/Value** | Cách CA ký chứng chỉ và chữ ký | Kiểm tra bằng khóa của issuer đúng chuỗi tin cậy |
| **Key Usage** | Mục đích mật mã được phép, như digitalSignature | Không sử dụng khóa sai mục đích |
| **Extended Key Usage (EKU)** | Mục đích cấp cao như serverAuth/clientAuth | Đúng mục đích xác thực phía server/client theo policy |
| **Basic Constraints** | Chứng chỉ có được dùng làm CA không, giới hạn chuỗi CA | Leaf không được tùy ý đóng vai issuer |
| **SKI/AKI** | Định danh khóa chủ thể/issuer hỗ trợ xây dựng chuỗi | Hỗ trợ tìm khóa, không thay việc kiểm chứng chữ ký |
| **AIA/CDP** | Tham chiếu tới issuer/OCSP/CRL trong một số hệ thống | Không tự tải và tin mọi URL theo nội dung chứng chỉ |

Một chứng chỉ có thể có thêm **Name Constraints**, **Certificate Policies** và các extension khác. Thành phần kiểm chứng cần tuân thủ cách xử lý extension critical: nếu gặp extension critical không hiểu và không đáp ứng được thì phải từ chối theo quy tắc kiểm chứng phù hợp.

### 3.1. Subject và SAN: tên nào thực sự được tin?

Với HTTPS công khai, tên miền cần đối chiếu với **DNS SAN** theo quy tắc hostname verification; không chấp nhận chỉ vì Common Name (CN) hiển thị “đúng”. Với chứng chỉ workload, tổ chức có thể dùng **URI SAN** để mang service identity hoặc **DNS SAN** theo hợp đồng cấp phát. Bên xác minh phải kiểm tra cả **loại tên**, tên cụ thể, phạm vi trust domain/tenant và danh sách CA được phép cấp tên đó.

Ví dụ:

~~~text
Leaf certificate:
  Issuer: Example Internal Workload CA
  Subject: CN=report-worker
  SAN: URI:spiffe://campus.example/workload/report-worker
  EKU: TLS Web Client Authentication

Application mapping:
  trusted_ca: internal-workload-ca
  expected_san_uri: spiffe://campus.example/workload/report-worker
  internal_principal: svc_report_worker
~~~

Tên trong ví dụ chỉ minh họa. **CN** không phải căn cứ cấp quyền admin; **URI SAN** chỉ có ý nghĩa khi được cấp bởi CA/trust domain đúng và được xác minh chính xác. Không suy ra hai chứng chỉ có cùng tên là cùng một chủ thể nếu nguồn cấp và phạm vi khác nhau.

## 4. PKI và chuỗi tin cậy

**Public Key Infrastructure (PKI)** bao gồm các vai trò, quy trình, khóa, CA, chứng chỉ và cơ chế vận hành để tạo và xác minh những liên kết giữa khóa công khai với danh tính. Mô hình phổ biến có root CA, intermediate CA và leaf certificate.

~~~mermaid
flowchart TD
    T["Trust Store: Root CA đã được cấu hình tin cậy"] --> I["Intermediate CA"]
    I --> L["Leaf certificate của report-worker"]
    L --> P["Private key của report-worker<br/>giữ riêng, không phát tán"]
    V["Verifier / mTLS endpoint"] -->|"Kiểm tra đường dẫn chứng chỉ"| T
    V -->|"Kiểm tra SAN, EKU, thời hạn, policy"| L
    V -->|"Yêu cầu proof of possession"| P
~~~

Sơ đồ biểu thị mối quan hệ tin cậy; **private key không được truyền tới verifier**. Trong giao thức thực, client dùng private key ký dữ liệu cần thiết, verifier dùng public key để kiểm tra chữ ký.

### 4.1. Quy trình xác minh chuỗi

Một thành phần xác minh thường cần:

1. **Xây dựng đường dẫn** từ leaf qua các CA trung gian đến một trust anchor đã cấu hình. Root không tự nhiên đáng tin vì được đưa kèm trong handshake.
2. **Xác minh chữ ký** ở từng mắt xích theo thuật toán và khóa phù hợp; chặn thuật toán yếu hoặc không được phép.
3. **Kiểm tra Basic Constraints, Key Usage, path length, các extension critical và Name Constraints** theo quy tắc của chứng chỉ.
4. **Kiểm tra thời hạn** của các chứng chỉ liên quan và độ đáng tin của thời gian hệ thống.
5. **Kiểm tra mục đích** sử dụng chứng chỉ, bao gồm EKU/policy cần thiết cho server hoặc client.
6. **Đối chiếu danh tính kỳ vọng** bằng SAN đúng loại và đúng phạm vi. Đây là bước phân biệt “chứng chỉ được CA tin cậy cấp” với “chứng chỉ thuộc đúng dịch vụ mà tôi định kết nối”.
7. **Áp dụng chính sách trạng thái** như revocation/OCSP/CRL hoặc chứng chỉ ngắn hạn phù hợp, đồng thời kiểm tra trạng thái chủ thể ở ứng dụng khi cần.

Các thư viện TLS/PKIX thường làm phần lớn việc kiểm tra đường dẫn, nhưng cấu hình mặc định không nhất thiết biết **service identity** hoặc quyền nghiệp vụ kỳ vọng. Bỏ qua hostname/SAN verification để “sửa lỗi certificate” thường phá vỡ ranh giới xác thực.

### 4.2. Root CA đáng tin là một quyết định bảo mật

Máy chủ có thể đưa cho client cả chuỗi chứng chỉ, nhưng **không thể tự tuyên bố root của mình đáng tin**. Trust anchor phải được cấu hình theo quản trị hệ thống, trust store của thiết bị, chính sách doanh nghiệp hoặc một cơ chế phân phối tin cậy tương đương.

Nếu API nội bộ cấu hình tin mọi root CA của hệ điều hành mà không giới hạn các issuer được phép cấp chứng chỉ workload, nó có thể chấp nhận danh tính từ nguồn ngoài ý muốn. Ngược lại, một chứng chỉ tự ký có thể sử dụng trong mô hình trust pinning được triển khai đúng, nhưng “có chữ ký tự ký” tự nó không tạo lòng tin.

## 5. Proof of possession: chứng minh giữ khóa riêng

Trong xác thực bằng chứng chỉ, kẻ tấn công có thể sao chép certificate công khai. Vì vậy cần thử thách mà chỉ bên có **private key** mới hoàn thành được. Bằng chứng này phải gắn với **phiên/giao dịch hiện tại** và có cơ chế chống replay.

**Trong mTLS**, việc chứng minh sở hữu khóa được tích hợp vào bắt tay TLS. Ở TLS 1.3, phía trình diện chứng chỉ ký dữ liệu có cấu trúc dựa trên *handshake transcript* trong thông điệp CertificateVerify. Vì transcript phụ thuộc các thông điệp bắt tay của phiên, một chữ ký sao chép từ phiên khác không thể dùng lại đơn giản để đăng nhập vào phiên mới. Thông điệp Finished còn xác nhận tính toàn vẹn tiến trình bắt tay.

Lưu ý: chữ ký transcript bảo vệ **bắt tay TLS**; nó không tự ngăn việc một thiết bị đã bị chiếm khóa riêng tạo các phiên TLS mới. Cũng không tự giải quyết replay của một access token bearer bị lấy cắp ở lớp ứng dụng.

### 5.1. Vì sao “gửi một chữ ký” chưa đủ?

Thiết kế tự chế như “client ký chuỗi login bằng private key rồi server chấp nhận mãi” có thể bị replay. Nếu buộc phải thiết kế giao thức challenge–response ngoài TLS, thử thách cần ngẫu nhiên, mới, một lần, có thời hạn, gắn principal/mục đích/giao dịch và được xác minh theo chuẩn an toàn đã đánh giá. Trong đa số trường hợp, ưu tiên **TLS/mTLS và thư viện giao thức chuẩn**, tránh tự phát minh định dạng thông điệp ký.

## 6. mTLS: hai phía xác thực qua TLS

Trong HTTPS thông thường, **client xác thực server** qua server certificate. Với **mutual TLS**, server còn yêu cầu và xác minh **client certificate**, nhờ đó hai phía có thể xác thực lẫn nhau ở lớp truyền tải.

~~~mermaid
sequenceDiagram
    participant C as Client / report-worker
    participant S as Server / billing-api
    participant CA as Trust configuration
    C->>S: ClientHello
    S-->>C: ServerHello, server Certificate, proof
    C->>CA: Xác minh chain và server identity
    CA-->>C: Kết quả theo trust policy
    S-->>C: CertificateRequest (yêu cầu client cert)
    C->>S: Client Certificate, CertificateVerify
    S->>CA: Kiểm tra client chain, SAN, purpose
    CA-->>S: Kết quả theo trust policy
    S->>S: Ánh xạ cert -> service principal
    C-->>S: Hoàn tất bắt tay TLS
    C->>S: Gọi API qua kênh đã bảo vệ
    S->>S: Authorization trên principal + resource
    S-->>C: Kết quả theo quyền
~~~

Sơ đồ đã lược bớt thông điệp và khác biệt thứ tự giữa các phiên bản TLS nhằm diễn đạt ý tưởng. **Trình tự thực tế phải tuân thủ giao thức TLS của thư viện sử dụng**; không dùng sơ đồ như bản triển khai handshake.

Một endpoint mTLS cần **hai lớp quyết định**:

1. **Lớp TLS/PKI:** chứng chỉ client và proof of possession có đạt chính sách về CA, SAN, EKU, thời gian và trạng thái không?
2. **Lớp ứng dụng:** danh tính đã ánh xạ có được gọi phương thức và tài nguyên hiện tại không?

Một kết nối mTLS thành công không có nghĩa request tới bất kỳ endpoint nào cũng được phép. API vẫn phải kiểm tra quyền ở mỗi thao tác.

### 6.1. Khi TLS được kết thúc tại gateway

Nhiều hệ thống dùng load balancer, ingress hoặc API gateway làm điểm kết thúc TLS. Khi đó **gateway** là thành phần trực tiếp kiểm tra client certificate; service phía sau không nhìn thấy trực tiếp handshake gốc.

Nếu gateway chuyển thông tin danh tính tới backend qua header, ví dụ giá trị client SAN, cần bảo vệ ranh giới này:

- Gateway phải **xóa/ghi đè header danh tính do client tự gửi**.
- Backend chỉ nhận request từ gateway được xác thực qua mTLS nội bộ hoặc cơ chế tin cậy khác.
- Header hoặc assertion chuyển tiếp phải có hợp đồng trường dữ liệu, phạm vi và bảo đảm tính toàn vẹn; backend không được tin header từ Internet hoặc từ service chưa được ủy quyền.
- Gateway phải thực hiện đầy đủ kiểm tra chuỗi và danh tính trước khi cấp ngữ cảnh xác thực; backend vẫn kiểm tra authorization theo policy.

Không dùng HTTP header tùy ý như một bằng chứng người dùng có certificate nếu bất kỳ client nào cũng tự đặt được header đó. Nếu ứng dụng cần bằng chứng sở hữu khóa end-to-end, cần thiết kế cách truyền và kiểm chứng riêng chứ không mặc định còn mTLS xuyên suốt sau TLS termination.

## 7. Các dạng sử dụng certificate credential

| Trường hợp | Chủ thể | Ví dụ | Kiểm tra quan trọng |
| --- | --- | --- | --- |
| **TLS server certificate** | Web/API server | Trình duyệt kết nối cổng học tập | DNS SAN/hostname, chain, hạn, serverAuth |
| **mTLS client certificate** | Service gọi API | Worker gửi dữ liệu tới billing API | Client identity/SAN, CA được phép, clientAuth, policy |
| **Device certificate** | Thiết bị được quản lý | Thiết bị kiosk kết nối máy chủ trường | Enrollment, thiết bị có còn được quản lý không, trạng thái thu hồi |
| **User certificate/smart card** | Người dùng | Nhân viên đăng nhập bằng thẻ thông minh | Proof of possession, quy trình cấp thẻ, ánh xạ user và PIN/biometric theo chính sách |
| **Workload identity** | Pod/job/service | Service mesh với CA nội bộ | Danh tính workload, trust domain, vòng đời ngắn, quyền API |

Chứng chỉ **code signing** dùng để xác minh nguồn gốc/tính toàn vẹn của phần mềm trong quy trình ký phát hành. Nó cũng dùng PKI, nhưng **không mặc nhiên là credential để đăng nhập tương tác**; mục đích và chính sách kiểm chứng khác.

### 7.1. Certificate khác password, passkey và token thế nào?

| Phương thức | Bằng chứng chính | Vấn đề vòng đời nổi bật |
| --- | --- | --- |
| **Mật khẩu** | Bí mật do người dùng biết | Lộ/tái sử dụng, phishing, password hash, MFA |
| **Passkey/WebAuthn** | Chữ ký bằng khóa riêng ràng buộc RP ID/origin và challenge | Thêm/xóa authenticator, đồng bộ, recovery, chống phishing |
| **Certificate credential** | Chuỗi chứng chỉ tin cậy + proof of possession khóa riêng | CA, SAN/policy, cấp/renew/revoke, bảo vệ private key |
| **Bearer token** | Sở hữu một chuỗi token còn hiệu lực | Trộm/replay token, TTL, audience, scope, thu hồi |

Passkey cũng dùng mật mã khóa công khai nhưng mô hình ràng buộc danh tính với RP, giao thức WebAuthn và quy trình đăng ký khác PKI X.509 truyền thống. Certificate credential mạnh trong xác thực máy–máy và thiết bị được quản lý; dùng cho người dùng cần tính toán trải nghiệm cấp phát khóa, thiết bị mất và recovery.

## 8. Vòng đời cấp phát certificate credential

Một chứng chỉ chỉ an toàn nếu cách **cấp phát danh tính trước khi ký** đáng tin. Nếu kẻ tấn công xin được chứng chỉ mang SAN của dịch vụ khác, chữ ký CA có thể hợp lệ nhưng hệ thống đã thất bại ở khâu enrollment.

### 8.1. Luồng đăng ký và phát hành

1. **Xác định subject và chính sách:** chủ thể người/thiết bị/workload nào, trust domain nào, loại SAN gì, EKU nào, thời hạn bao lâu.
2. **Tạo cặp khóa:** sinh khóa ở nơi sẽ sử dụng, ưu tiên TPM/HSM/secure enclave nếu khả thi; hạn chế xuất khóa riêng.
3. **Gửi yêu cầu cấp chứng chỉ (CSR):** chứa khóa công khai và thông tin yêu cầu; CSR có chữ ký chứng minh nắm khóa tương ứng nhưng **không tự chứng minh người xin được phép có tên trong SAN**.
4. **Xác thực người/thiết bị/workload xin cấp:** CA hoặc hệ thống registration authority phải kiểm tra quyền sở hữu/ủy quyền đối với danh tính được yêu cầu.
5. **CA ký và phát hành:** áp dụng profile chứng chỉ, EKU, SAN, hạn, constraints, serial theo chính sách.
6. **Cài đặt certificate chain và cấu hình kiểm chứng:** phía nhận chỉ chấp nhận trust anchor và danh tính được kỳ vọng.
7. **Theo dõi:** lưu metadata issuer/serial/fingerprint/hạn, nguồn cấp và chủ thể được ánh xạ; cảnh báo sắp hết hạn, kiểm soát luân chuyển khóa.

~~~mermaid
flowchart LR
    A["Identity / Enrollment authority"] -->|"Chứng minh đủ điều kiện"| B["Registration / Issuance"]
    C["Client tạo private key"] -->|"CSR: public key + yêu cầu"| B
    B -->|"CA ký profile hợp lệ"| D["Leaf Certificate"]
    D -->|"Cài kèm private key ở chủ thể"| E["Client / Device / Workload"]
    E -->|"mTLS proof of possession"| F["Verifier"]
    G["Trust store & identity policy"] -->|"Quy định nguồn và SAN được tin"| F
~~~

Quy trình không bắt buộc tách Registration Authority thành một dịch vụ riêng. Quan trọng là bước cấp phép danh tính **không bị bỏ qua** khi tự động hóa CSR.

### 8.2. Tự động hóa và thời hạn ngắn

Với số lượng lớn workload, cấp phát thủ công và chứng chỉ sống nhiều năm dễ gây gián đoạn hoặc rủi ro khi khóa bị lộ. Các hệ thống có thể tự động hóa qua giao thức enrollment/quản lý chứng chỉ phù hợp, sử dụng danh tính workload và chứng chỉ sống ngắn.

Chứng chỉ ngắn hạn giúp giảm thời gian sử dụng credential sau khi bị lộ nhưng **không thay thế hoàn toàn** khả năng thu hồi hoặc cơ chế chặn principal trong ứng dụng. Nếu một service bị deprovision mà vẫn có chứng chỉ còn hạn, bên nhận cần quyết định mức độ chấp nhận cho tới khi hết hạn và có thể áp dụng chặn tại policy.

## 9. Bảo vệ private key và trust anchor

**Private key** là thành phần nhạy cảm nhất của certificate credential. Nếu nó bị sao chép, kẻ tấn công có thể dùng chứng chỉ hợp lệ để tạo một phiên xác thực mới trong khoảng thời gian chứng chỉ còn được chấp nhận.

Biện pháp thực tế:

- **Ưu tiên khóa không xuất được** khi nền tảng cho phép: HSM, TPM, smart card hoặc hệ thống quản lý khóa phù hợp.
- **Giảm phạm vi đọc:** tiến trình/service chỉ có quyền dùng khóa của mình; không lưu private key trong repository, image container, log hoặc tệp cấu hình công khai.
- **Bảo vệ khi lưu và sao lưu:** phân quyền hệ điều hành, mã hóa khi cần, kiểm soát bản sao, backup và key escrow theo chính sách.
- **Phân tách môi trường:** không dùng một cặp khóa cho development, staging và production; không chia sẻ khóa giữa nhiều service chỉ vì tiện.
- **Luân chuyển khóa riêng:** gia hạn certificate có thể giữ nguyên khóa nếu chính sách cho phép, nhưng việc **rekey** định kỳ hoặc khi nghi lộ giúp giảm rủi ro kéo dài.
- **Kiểm soát quyền của CA:** khóa riêng CA cần bảo vệ đặc biệt; quyền phát hành và quy tắc SAN/profile cần có kiểm soát thay đổi, audit và giám sát.

Mật khẩu của file PFX chỉ bảo vệ file khi lưu/truyền trong những điều kiện nhất định. Khi một tiến trình đã giải mã và sử dụng khóa riêng, khả năng bảo vệ phụ thuộc cả vào an ninh runtime/thiết bị. Không xem PFX có mật khẩu là tương đương HSM không xuất khóa.

### 9.1. CA bị lộ và private key leaf bị lộ khác nhau

**Lộ private key của leaf:** cần phát hành credential mới, thu hồi hoặc ngừng chấp nhận credential cũ theo chính sách, kiểm tra dấu hiệu truy cập trái phép, xác định phạm vi tác động và cập nhật ứng dụng/thiết bị.

**Lộ khóa của intermediate/root CA:** phạm vi lớn hơn vì kẻ tấn công có thể phát hành chứng chỉ giả. Cần quy trình khẩn cấp về thay trust anchor, rút CA/đường dẫn tin cậy, thay các chứng chỉ liên quan và thông báo hệ thống phụ thuộc. Chỉ thu hồi một chứng chỉ leaf không xử lý được sự cố CA.

## 10. Renewal, rotation, revocation và deprovisioning

Một credential có vòng đời riêng, không trùng hoàn toàn với vòng đời principal. Cùng một service có thể trải qua nhiều lần cấp chứng chỉ; một certificate hết hạn không đồng nghĩa service đã bị xóa; một service bị vô hiệu hóa không mặc nhiên khiến mọi certificate còn hạn bị các bên nhận từ chối.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Xin cấp/CSR
    Requested --> Issued: Được thẩm định và ký
    Issued --> Active: Cài đặt, ánh xạ danh tính
    Active --> Renewing: Gần hết hạn
    Renewing --> Active: Chứng chỉ mới, kiểm tra và chuyển đổi
    Active --> Revoked: Khóa lộ hoặc chấm dứt tin cậy
    Active --> Expired: Quá notAfter
    Active --> Deprovisioned: Chủ thể ngừng hoạt động
    Revoked --> [*]
    Expired --> [*]
    Deprovisioned --> [*]
~~~

Sơ đồ đơn giản hóa: hệ thống có thể có nhiều chứng chỉ đồng thời để rotation không gây downtime; certificate bị thu hồi nhưng đã được dùng trong một phiên có thể cần thêm chính sách đóng phiên/thu hồi quyền ở ứng dụng.

### 10.1. Renewal và rotation

**Renewal** cấp chứng chỉ mới khi chứng chỉ cũ sắp hết hạn. **Rotation** là thay credential đang sử dụng; có thể gồm thay certificate, cặp khóa hoặc cả chuỗi CA. Nên:

1. Giám sát hạn và cảnh báo trước khi certificate không dùng được.
2. Tự động xin và cài chứng chỉ mới theo quy trình enrollment an toàn.
3. Kiểm thử chuỗi, tên, EKU, proof of possession và kết nối thực tế.
4. Chuyển dần client/server và trust store khi cần; duy trì khoảng chồng lấn có kiểm soát.
5. Ngừng chấp nhận credential cũ, dọn bản sao khóa cũ và ghi audit.

**Rotation CA** khó hơn rotation leaf: verifier có thể phải tin đồng thời CA cũ và mới trong một khoảng thời gian được kiểm soát, rồi gỡ CA cũ đúng kế hoạch. Giữ hai CA mãi mãi làm tăng bề mặt tin cậy.

### 10.2. Revocation: không chỉ đổi cờ trong cơ sở dữ liệu

Cơ chế phổ biến gồm **CRL** (Certificate Revocation List), **OCSP** (Online Certificate Status Protocol) và chính sách dùng chứng chỉ có thời hạn ngắn. Hỗ trợ và hành vi khi mạng/OCSP gặp lỗi tùy thư viện, hệ thống và mức rủi ro; không được mặc định mọi client sẽ từ chối chứng chỉ vừa bị thu hồi ngay lập tức.

Quyết định thiết kế cần trả lời:

- Ai được yêu cầu thu hồi? Thu hồi theo sự kiện nào: lộ khóa, mất thiết bị, kết thúc hợp đồng, CA thay đổi?
- Bên kiểm tra có thực hiện revocation check không? Cập nhật dữ liệu thu hồi bao lâu một lần?
- Nếu kênh kiểm tra trạng thái không truy cập được, chính sách **fail-open/fail-closed** cho từng loại hành động ra sao?
- Phiên mTLS đã thiết lập còn hoạt động bao lâu sau khi credential bị thu hồi?
- Có cần thêm một **denylist principal/credential** hoặc kiểm tra account status ở cấp ứng dụng để thu hồi quyền nhanh không?

Với workload, chứng chỉ sống ngắn cộng với cơ chế ngừng cấp mới thường rất hữu ích, nhưng trong khoảng sống còn lại vẫn cần đánh giá rủi ro. **Không nhầm thu hồi chứng chỉ với thu hồi access token hoặc quyền nghiệp vụ**; những trạng thái này có thể độc lập.

## 11. Certificate credential và token: cùng tồn tại thế nào?

Hệ thống thường dùng mTLS để xác thực client với authorization server, gateway hoặc resource server, rồi nhận **access token** cho các API. Cần xác định token là **bearer** hay được **ràng buộc với credential**.

- **Bearer access token:** ai lấy được token còn hạn thường có thể dùng trong phạm vi audience/scope; kết nối mTLS lúc cấp token không tự khiến token trở thành sender-constrained.
- **mTLS certificate-bound access token:** token được gắn với một chứng chỉ client cụ thể; resource server kiểm tra token và đối chiếu chứng chỉ đã dùng ở kết nối mTLS với ràng buộc của token.

Ví dụ khái niệm một claim xác nhận:

~~~json
{
  "iss": "https://auth.example.org",
  "aud": "billing-api",
  "sub": "svc_report_worker",
  "exp": 1790000300,
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-client-certificate"
  }
}
~~~

Đây chỉ là **payload minh họa**: chuỗi thumbprint ở trên là placeholder, không phải giá trị băm thật. Với mô hình mTLS-bound token theo chuẩn tương ứng, bên nhận kiểm tra cả tính hợp lệ/token audience/scope **và** ràng buộc chứng chỉ đã được dùng để xác thực trên kênh truyền. Nếu tài nguyên nằm sau reverse proxy, việc cung cấp chứng cứ về client certificate phải an toàn như đã phân tích ở phần gateway. Không được chỉ tin trường cnf do client tự khai trong request.

### 11.1. Mối quan hệ với phiên người dùng

Một ứng dụng có thể xác thực người dùng bằng smart card/certificate, rồi phát hành session cookie cho trình duyệt. Sau đó cookie là bằng chứng duy trì phiên theo mô hình riêng. Nếu cookie bị đánh cắp, việc đăng nhập ban đầu dùng certificate **không tự động bảo vệ cookie** khỏi session hijacking. Cần cookie Secure/HttpOnly/SameSite phù hợp, chống CSRF, TTL, xác thực lại khi cần và cơ chế thu hồi phiên.

Tương tự, một certificate hợp lệ không đồng nghĩa có thể bỏ qua MFA. Một số triển khai dùng smart card kèm PIN hoặc thao tác người dùng; mức bảo đảm phụ thuộc tính bảo vệ khóa, xác minh người dùng, quy trình cấp thẻ và chính sách recovery, không chỉ nhãn “certificate”.

## 12. Chống phishing, replay và lạm dụng xác thực

### 12.1. Phishing

mTLS với khóa riêng được bảo vệ giúp bên kiểm tra yêu cầu **proof of possession**, làm giảm rủi ro đối với việc bị đánh cắp một “mật khẩu dùng chung”. Tuy vậy, certificate **không bảo đảm chống phishing cho mọi tình huống người dùng**:

- Máy/thiết bị bị chiếm có thể khiến khóa được sử dụng trái phép dù không xuất được.
- Một CA/trust anchor cấu hình sai hoặc kiểm tra SAN bị tắt có thể khiến client kết nối nhầm server.
- Một user vẫn có thể bị dụ chấp thuận thao tác hoặc lộ session/token trong ứng dụng sau bước mTLS.
- Các luồng recovery/enrollment yếu có thể cho kẻ tấn công xin một credential mới hợp lệ.

Muốn có tính chống phishing theo chuẩn cho login người dùng trên web, **passkey/WebAuthn** thường phù hợp hơn vì ràng buộc bằng chứng với RP ID/origin trong giao thức. mTLS có ưu thế riêng với thiết bị và workload được quản lý.

### 12.2. Replay

Proof of possession được gắn với transcript bắt tay TLS chống việc chép một chữ ký cũ để mở phiên mới. Tuy nhiên:

- Kẻ giữ private key thật có thể tạo phiên mới; phải bảo vệ khóa và thu hồi credential.
- Kẻ lấy bearer access token có thể replay ở lớp ứng dụng nếu không có sender constraint.
- Một client đã xác thực vẫn có thể gửi lại request chuyển tiền/hành động nhạy cảm; ứng dụng cần **idempotency key**, nonce giao dịch hoặc kiểm soát nghiệp vụ tùy use case.

Không gộp **replay ở lớp TLS**, **replay token** và **replay một giao dịch nghiệp vụ** thành một vấn đề duy nhất; mỗi loại có biện pháp phòng vệ khác nhau.

### 12.3. Lạm dụng enrollment và xác thực

Giới hạn tốc độ xin cấp chứng chỉ, kiểm soát quyền của registration authority, phát hiện yêu cầu SAN bất thường, cảnh báo các đợt xác thực thất bại, inventory credential đang hoạt động và cô lập quyền của mỗi workload. “Máy đã có chứng chỉ” chưa đủ để cho truy cập hàng loạt API; chính sách phải tuân thủ nguyên tắc **least privilege**.

## 13. Ví dụ thực tế: service gọi API nội bộ

Giả sử nền tảng học tập có dịch vụ **report-worker** tạo báo cáo cho giảng viên và dịch vụ **billing-api** quản lý hóa đơn. Hai service giao tiếp qua mTLS nội bộ.

**Yêu cầu:** report-worker chỉ được đọc trạng thái thanh toán của các khóa học được giao; không được sửa số tiền hay thực hiện hoàn tiền.

~~~text
Trusted issuer:
  Internal Workload CA of learning-platform

Expected client certificate:
  SAN URI = spiffe://learning.example/workload/report-worker
  EKU     = clientAuth

Identity mapping:
  SAN URI -> principal svc_report_worker

Authorization:
  principal = svc_report_worker
  action    = read_billing_summary
  resource  = course under authorized tenant
  result    = PERMIT if assignment and tenant policy match

Not authorized:
  action    = issue_refund
  result    = DENY
~~~

Luồng:

1. report-worker nhận chứng chỉ từ CA được ủy quyền sau khi hệ thống xác minh workload identity và sinh/cấp khóa an toàn.
2. report-worker kết nối tới billing-api; kiểm tra **server certificate** khớp server identity, trust chain và policy.
3. billing-api yêu cầu **client certificate**, kiểm tra CA được phép, SAN, EKU, thời hạn, trạng thái phù hợp và proof of possession.
4. billing-api ánh xạ URI SAN thành principal nội bộ **svc_report_worker** từ cấu hình đáng tin cậy.
5. Mỗi API request dùng principal và thông tin tenant/resource để kiểm tra quyền. Dù certificate hợp lệ, endpoint hoàn tiền vẫn trả **403 Forbidden** nếu không được cấp quyền.
6. Khi workload ngừng chạy hoặc bị phát hiện xâm nhập, hệ thống dừng cấp credential, thu hồi/chặn credential cũ theo chính sách và xem xét những phiên hiện hữu.

### 13.1. Ba kiểu cấu hình sai

| Sai lầm | Hậu quả | Sửa thế nào? |
| --- | --- | --- |
| Chỉ kiểm tra certificate có chữ ký từ một CA bất kỳ | Có thể chấp nhận certificate của nguồn không có thẩm quyền cấp service identity | Giới hạn trust anchor và issuer theo domain, xác minh SAN kỳ vọng |
| Dùng CN làm role trực tiếp, ví dụ CN=admin | Một tên trong certificate thành quyền nghiệp vụ không được phê duyệt | Ánh xạ principal cụ thể và policy riêng, kiểm soát đăng ký SAN |
| Tin header X-Client-Cert từ Internet | Client tự giả mạo chứng chỉ đã được gateway kiểm tra | Xóa header từ client; backend chỉ tin gateway đã được xác thực |

## 14. Quan sát và chẩn đoán chứng chỉ

Các lệnh sau giúp **xem metadata** của một chứng chỉ và kiểm tra sơ bộ chuỗi tin cậy trong môi trường thử nghiệm. Không in hoặc sao chép private key lên hệ thống công khai.

### 14.1. Đọc trường chứng chỉ

~~~bash
# Xem Subject, Issuer, hạn và extensions
openssl x509 -in client.crt -noout -text

# Xem hạn, subject và issuer ngắn gọn
openssl x509 -in client.crt -noout -dates -subject -issuer

# Xem dấu vân tay SHA-256 dùng cho inventory/đối chiếu
openssl x509 -in client.crt -noout -fingerprint -sha256
~~~

Đọc kỹ phần **X509v3 Subject Alternative Name**, **Key Usage**, **Extended Key Usage** và **Basic Constraints**. Một fingerprint chỉ giúp nhận diện một bản chứng chỉ cụ thể; **nó không chứng minh bên đưa fingerprint có private key**, cũng không chứng minh chứng chỉ được CA tin cậy ký.

### 14.2. Kiểm tra chain với CA được chỉ định

~~~bash
# Minh họa: kiểm tra leaf dành cho TLS client với chain và trust anchor được cấp sẵn
openssl verify \
  -purpose sslclient \
  -CAfile root-ca.crt \
  -untrusted intermediate-ca.crt \
  client.crt
~~~

Kết quả “OK” chỉ phản ánh các điều kiện mà lệnh và phiên bản thư viện thực sự đã kiểm tra. **Nó không thay thế kiểm tra principal/SAN kỳ vọng, ownership của khóa riêng, trạng thái account hoặc authorization ở API**, và không mặc định đã thực hiện revocation check trực tuyến theo chính sách triển khai.

### 14.3. Kiểm tra chứng chỉ server từ xa

~~~bash
openssl s_client \
  -connect api.example.org:443 \
  -servername api.example.org \
  -verify_hostname api.example.org \
  -verify_return_error \
  -showcerts
~~~

Lệnh sử dụng trust store mặc định theo môi trường OpenSSL; trong hệ thống dùng CA riêng cần chỉ rõ CA tin cậy thích hợp. **SNI** hỗ trợ máy chủ chọn đúng chứng chỉ; **hostname verification** mới kiểm tra danh tính server được mong đợi. In chuỗi certificate và thấy chữ ký hợp lệ chưa đủ nếu tên server bị sai hoặc trust store bị cấu hình quá rộng.

## 15. Những lưu ý khi vận hành production

### 15.1. Hệ thống phải quan sát được gì?

Theo dõi các sự kiện: chứng chỉ mới được cấp, principal liên kết, issuer/serial/fingerprint, thời hạn, certificate renewal/rotation, yêu cầu revocation, lỗi chuỗi tin cậy, SAN/EKU không khớp, lỗi proof of possession và hành vi gọi API bị từ chối theo policy.

Không log private key, dữ liệu nhạy cảm trong CSR hoặc token nguyên dạng. Certificate công khai thường có thể ghi metadata nhưng **SAN có thể tiết lộ tên thiết bị, nội bộ tổ chức hoặc người dùng**, vì vậy vẫn cần giới hạn truy cập log và thời gian lưu.

Các chỉ số vận hành hữu ích:

- Số certificate sắp hết hạn theo môi trường/service/issuer.
- Tỷ lệ cấp mới, renewal thành công/thất bại, thời gian cấp phát.
- Tỷ lệ lỗi bắt tay do expired, unknown CA, SAN mismatch, unsupported purpose.
- Số principal hoặc workload còn certificate hoạt động sau khi deprovisioning.
- Tốc độ cập nhật trust bundle khi xoay CA và tỷ lệ client đã chuyển đổi.

### 15.2. Kịch bản ứng phó sự cố

**Tình huống:** một bản sao private key của report-worker bị đưa nhầm vào artifact build.

Quy trình xử lý theo rủi ro:

1. Xác định credential/issuer/serial/fingerprint bị ảnh hưởng; loại bỏ đường lộ và chặn phát tán tiếp.
2. Thu hồi hoặc chủ động từ chối chứng chỉ cũ theo khả năng hệ thống; dừng/giới hạn các request đáng ngờ.
3. **Sinh cặp khóa mới**, cấp chứng chỉ mới sau khi xác minh workload; không chỉ thay thời hạn trên certificate giữ nguyên private key đã lộ.
4. Cập nhật ứng dụng dùng credential mới, đóng phiên liên quan khi cần, cập nhật token bị ràng buộc với chứng chỉ cũ.
5. Xem lại audit truy cập, quyền mà certificate cũ có thể đã dùng; khắc phục nguyên nhân khóa bị đưa vào build.

Nếu nguồn phát hành CA bị xâm nhập, cần kế hoạch rộng hơn về trust anchor và các chứng chỉ khác; quy trình leaf rekey không đủ.

## 16. Bài tập tình huống

Một hệ thống cho 100 microservice truy cập API nội bộ. Mỗi service có client certificate do cùng Internal CA cấp; certificate được đặt vào container image. Backend tin mọi client certificate từ CA và tự gán role từ trường Common Name. Chứng chỉ có hạn ba năm, không theo dõi revocation; khi service bị xóa, bản image chứa private key vẫn nằm trong registry. Gateway kiểm tra certificate rồi gửi header X-Client-Cert cho backend mà không xóa header phía client.

**Câu hỏi:**

1. Chỉ ra ít nhất **sáu rủi ro** trong quy trình lưu, cấp và sử dụng certificate credential.
2. Đề xuất mô hình phân phối private key và certificate an toàn hơn cho workload.
3. Thiết kế ánh xạ **SAN → principal → quyền**, phân biệt authentication và authorization ở mỗi bước.
4. Nêu cách rotation và deprovisioning để quyền của service bị xóa không còn hiệu lực theo thời gian yêu cầu.
5. Nếu hệ thống dùng bearer JWT sau mTLS, giải thích vì sao token có thể vẫn bị replay; đề xuất TTL/thu hồi hoặc sender-constrained token phù hợp.
6. Viết các trường hợp kiểm thử cho certificate hết hạn, sai issuer, SAN khác, thiếu clientAuth, private key không khớp, gateway header giả mạo và service hợp lệ gọi endpoint không có quyền.

**Gợi ý đối chiếu:** private key không nằm trong image chia sẻ; enrollment giới hạn SAN được xin; CA/trust bundle có phạm vi; client chứng minh sở hữu khóa trên mTLS; backend chỉ nhận assertion từ gateway đã được xác thực; policy dựa trên principal nội bộ và quyền theo tài nguyên; chứng chỉ cần theo dõi hạn/rotation/revocation; token và phiên có vòng đời riêng.

## 17. Checklist thiết kế certificate credential

Trước khi triển khai một luồng xác thực bằng chứng chỉ, hãy trả lời:

1. **Subject là ai?** Người, máy, workload hay server; danh tính được ánh xạ từ SAN nào, ở trust domain/tenant nào?
2. **Ai được cấp certificate?** Quy trình enrollment có kiểm soát quyền đặt SAN, EKU và certificate profile không?
3. **Private key ở đâu?** Khóa có được bảo vệ, khó trích xuất, phân tách theo service và môi trường không?
4. **Chain tin vào ai?** Trust anchor được quản lý ra sao; có kiểm tra chữ ký/constraints/thuật toán/hạn không?
5. **Đúng danh tính và mục đích?** Đã đối chiếu SAN hoặc service identity kỳ vọng, Key Usage/EKU tương ứng chưa?
6. **Proof of possession đúng phiên?** Dùng mTLS hoặc giao thức chuẩn chống replay; có bỏ qua bước verify vì “đã có certificate” không?
7. **Proxy có làm mất ranh giới?** Gateway xóa header client tự gửi và backend xác thực gateway chưa?
8. **Quyền có tách biệt?** Mỗi principal chỉ được hành động/resource theo least privilege chưa?
9. **Thu hồi có hiệu lực như thế nào?** Có monitoring hạn, rotation, revocation policy, chặn principal và xử lý phiên đang mở không?
10. **Sự cố và recovery?** Có hướng dẫn xử lý lộ private key, mất thiết bị, CA bị xâm nhập và đổi trust store không?

## 18. Ghi nhớ

- **Chứng chỉ X.509 là lời xác nhận về public key và thuộc tính nhận diện; private key mới là bí mật cần được chứng minh quyền kiểm soát.**
- Xác thực bằng certificate đòi hỏi **hai phần**: đường dẫn tin cậy phù hợp và proof of possession gắn với phiên; sau đó phải ánh xạ đúng danh tính kỳ vọng.
- **CA hợp lệ không đồng nghĩa chủ thể được cấp mọi quyền.** SAN, mục đích sử dụng, phạm vi issuer và policy của API đều quan trọng.
- **mTLS bảo vệ xác thực kênh**, nhưng bearer token, phiên web và giao dịch nghiệp vụ vẫn có rủi ro riêng về replay, đánh cắp và authorization.
- **Vòng đời credential không dừng ở cấp phát**: bảo vệ khóa, renewal, rotation, revocation, giám sát và deprovisioning quyết định độ an toàn thực tế.

Nếu một hệ thống biết chính xác **ai được phép xin chứng chỉ**, **khóa riêng được giữ ở đâu**, **bên nhận tin CA và SAN nào**, **chủ thể đã xác thực được làm gì** và **làm cách nào chấm dứt quyền sử dụng credential**, certificate credential mới có thể trở thành một nền tảng xác thực an toàn, có thể vận hành và kiểm chứng lâu dài.
