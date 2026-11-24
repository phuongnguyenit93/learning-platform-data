# Luồng certificate authentication — Xác thực bằng chứng chỉ số

## 1. Certificate authentication là gì?

**Certificate authentication** (xác thực bằng chứng chỉ số) là phương thức xác minh danh tính dựa trên chứng chỉ khóa công khai và bằng chứng rằng bên kết nối đang kiểm soát **khóa riêng tương ứng**. Chứng chỉ thường là chứng chỉ X.509 do một Certificate Authority (CA) phát hành. Nó chứa khóa công khai, thông tin chủ thể hoặc Subject Alternative Name (SAN), thời hạn, mục đích sử dụng và chữ ký của bên phát hành.

Ví dụ, một dịch vụ nội bộ chỉ cho phép máy chủ ứng dụng kết nối tới API thanh toán nếu máy chủ ứng dụng trình bày chứng chỉ client hợp lệ và chứng minh đang giữ khóa riêng tương ứng. API kiểm tra chuỗi tin cậy, mục đích sử dụng, danh tính trong chứng chỉ và chính sách của dịch vụ trước khi chấp nhận kết nối.

Trong chương **Certificate authentication** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, luồng này liên hệ với credential, mật khẩu, MFA, passkey, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học cần hiểu ranh giới tin cậy của PKI, cách xác minh danh tính và quyền kiểm soát khóa, cũng như cách phòng chống giả mạo, replay, dùng chứng chỉ sai mục đích và lạm dụng đăng nhập.

**Một chứng chỉ hợp lệ chưa tự chứng minh bên gửi đang giữ khóa riêng.** Chứng chỉ là dữ liệu công khai có chữ ký của CA. Trong TLS client authentication, bên client còn phải tạo bằng chứng mật mã trong handshake (ví dụ chữ ký \`CertificateVerify\` trong TLS 1.3) để chứng minh quyền kiểm soát khóa riêng. Nếu chỉ tải lên một tệp chứng chỉ mà không có proof of possession, server chưa xác minh được người gửi đang kiểm soát credential.

### Các thành phần cơ bản

| Thành phần | Vai trò |
| --- | --- |
| **Private key** | Bí mật dùng để ký hoặc thực hiện phép toán mật mã; phải được bảo vệ và không gửi cho server. |
| **Public key** | Khóa công khai tương ứng; có thể được chia sẻ và dùng để xác minh chữ ký. |
| **X.509 certificate** | Liên kết khóa công khai với danh tính/thuộc tính theo xác nhận của CA. |
| **CA (Certificate Authority)** | Phát hành và ký chứng chỉ theo chính sách xác minh danh tính. |
| **Trust anchor** | Điểm tin cậy được cấu hình sẵn, thường là root CA hoặc khóa tin cậy. |
| **Relying party / verifier** | Bên kiểm tra chứng chỉ, bằng chứng sở hữu khóa và ánh xạ danh tính sang tài khoản/quyền. |
| **PKI** | Hạ tầng quản lý khóa công khai: CA, chứng chỉ, chính sách, phát hành, gia hạn, thu hồi và phân phối trạng thái. |

## 2. Phân biệt xác thực server, client và mTLS

TLS thường được dùng để bảo vệ kênh và xác thực server. Trong kết nối HTTPS thông thường, trình duyệt kiểm tra chứng chỉ server để chắc rằng nó đang kết nối đúng website theo tên miền và chuỗi tin cậy. **Client certificate authentication** bổ sung việc server yêu cầu client chứng minh danh tính bằng chứng chỉ.

| Kiểu | Bên trình chứng chỉ | Bên kiểm tra | Ví dụ |
| --- | --- | --- | --- |
| **TLS server authentication** | Server | Client | Trình duyệt kiểm tra chứng chỉ của website. |
| **TLS client authentication** | Client | Server | API yêu cầu chứng chỉ của ứng dụng gọi. |
| **Mutual TLS (mTLS)** | Cả server và client | Mỗi bên kiểm tra bên kia | Hai workload xác thực lẫn nhau trước khi trao đổi dữ liệu. |

**mTLS** không có nghĩa hai bên chỉ gửi chứng chỉ cho nhau. Mỗi bên phải kiểm tra chứng chỉ theo trust store, tên/danh tính mong đợi, mục đích sử dụng và chính sách của mình; đồng thời TLS chứng minh quyền kiểm soát khóa riêng.

Một website có HTTPS hợp lệ chưa chắc yêu cầu client certificate. Ngược lại, một hệ thống nội bộ có thể dùng mTLS giữa các service mà không có tương tác mật khẩu của người dùng. Cần xác định chủ thể được xác thực là **người dùng, thiết bị, workload hay ứng dụng** trước khi thiết kế chính sách.

## 3. Mô hình ranh giới tin cậy của PKI

Một luồng certificate authentication đi qua nhiều bên:

~~~mermaid
flowchart LR
    O["Chủ thể / workload<br/>giữ private key"]
    CA["CA / PKI<br/>xác minh và phát hành"]
    C["X.509 certificate<br/>public key + identity + signature"]
    V["Verifier / API<br/>kiểm tra chain + proof"]
    T[("Trust store<br/>trust anchors / policy")]
    M[("Identity mapping<br/>subject/SAN → principal")]
    A["Authorization<br/>quyền trên resource"]
    O -->|"CSR / quy trình enrollment"| CA
    CA --> C
    C -->|"Trình certificate"| V
    O -->|"Proof of possession"| V
    T --> V
    V -->|"Danh tính đã xác minh"| M
    M --> A
~~~

Sơ đồ là mô hình khái niệm; thực tế CA có thể tách thành root CA, intermediate CA, registration authority (RA), dịch vụ cấp phát và kho chứng chỉ. Ranh giới quan trọng:

1. **CA xác nhận điều gì?** CA chỉ nên ký những thuộc tính mà quy trình xác minh và chính sách cấp phát cho phép.
2. **Verifier tin ai?** Trust anchor và chính sách phải được cấu hình từ nguồn tin cậy, không lấy tùy tiện từ certificate do client gửi.
3. **Ai đang giữ khóa riêng?** TLS handshake hoặc giao thức tương ứng cần proof of possession.
4. **Danh tính được hiểu thế nào?** Subject/SAN được ánh xạ sang principal theo quy tắc cụ thể; không suy quyền từ một chuỗi tên tự do.
5. **Chủ thể được phép làm gì?** Authorization được thực hiện sau authentication, ở phạm vi tenant, API và tài nguyên.

Nếu CA bị xâm phạm hoặc cấp nhầm chứng chỉ, chữ ký vẫn có thể hợp lệ về mặt mật mã nhưng mối liên kết danh tính không còn đáng tin. Vì vậy, certificate authentication phụ thuộc cả **mật mã lẫn quản trị PKI**.

## 4. Cấu trúc chứng chỉ X.509 cần hiểu

Một chứng chỉ X.509 thường có các trường và extension quan trọng:

| Trường/extension | Ý nghĩa | Cách verifier sử dụng |
| --- | --- | --- |
| **Subject** | Tên chủ thể theo cấu trúc X.500. | Thông tin nhận dạng; không nên mặc định CN là khóa định danh duy nhất. |
| **Subject Alternative Name (SAN)** | Danh sách định danh như DNS name, URI, IP hoặc email tùy loại. | Thường là nơi chứa danh tính cần so khớp theo loại chủ thể. |
| **Issuer** | CA phát hành chứng chỉ. | Dùng xây dựng chuỗi chứng chỉ và xác định bên ký. |
| **Serial Number** | Số định danh chứng chỉ trong phạm vi CA. | Dùng nhận diện chứng chỉ, tra trạng thái thu hồi cùng issuer. |
| **Validity (Not Before/Not After)** | Khoảng thời gian chứng chỉ có hiệu lực. | Từ chối chứng chỉ chưa bắt đầu hoặc đã hết hạn, có xét chính sách thời gian. |
| **Basic Constraints** | Xác định CA hay end-entity và giới hạn path length. | Ngăn chứng chỉ leaf bị dùng như CA. |
| **Key Usage** | Các phép dùng khóa được cho phép. | Kiểm tra khóa có được dùng cho mục đích cần thiết không. |
| **Extended Key Usage (EKU)** | Mục đích sử dụng mở rộng, ví dụ serverAuth/clientAuth. | Đảm bảo chứng chỉ dùng đúng vai trò. |
| **Certificate Policies** | Chính sách/đảm bảo của CA nếu có. | Áp dụng yêu cầu trust policy của hệ thống. |
| **Authority/Subject Key Identifier** | Gợi ý định danh khóa trong chuỗi. | Hỗ trợ xây dựng path; không tự chứng minh trust. |
| **CRL Distribution Points / AIA** | Thông tin điểm phân phối CRL hoặc issuer/OCSP tùy extension. | Hỗ trợ lấy thông tin chuỗi/trạng thái; chỉ tin nguồn phù hợp với chính sách. |

Đối với chứng chỉ website, kiểm tra tên máy chủ thường dựa trên **SAN** theo quy tắc hostname verification. Đối với client certificate, hệ thống cần xác định thuộc tính SAN/Subject nào đại diện cho client hoặc workload, và ràng buộc nó với danh tính được cấp phát. Không nên viết logic kiểu “nếu CN chứa chữ admin thì cho quyền quản trị”.

## 5. Luồng TLS client certificate authentication

Trong TLS 1.3, server có thể yêu cầu client certificate trong handshake bằng thông điệp \`CertificateRequest\`. Client phản hồi bằng chuỗi chứng chỉ phù hợp và chứng minh quyền kiểm soát khóa riêng qua chữ ký trong \`CertificateVerify\`. Server kiểm tra chuỗi, chữ ký và chính sách trước khi coi client đã được xác thực.

~~~mermaid
sequenceDiagram
    participant C as Client / workload
    participant S as TLS server / API
    participant P as PKI / trust store
    C->>S: ClientHello
    S-->>C: ServerHello + chứng chỉ server + CertificateRequest
    C->>C: Kiểm tra chứng chỉ server và danh tính mong đợi
    C->>S: Client Certificate chain
    C->>S: CertificateVerify (ký transcript bằng private key)
    C->>S: Finished
    S->>P: Xây dựng/kiểm tra chain, policy, trạng thái
    S->>S: Xác minh CertificateVerify và ánh xạ principal
    S-->>C: Finished / handshake hoàn tất nếu hợp lệ
    C->>S: Gửi request API trong kênh TLS
    S->>S: Authorization theo principal và resource
~~~

Sơ đồ khái niệm có thể lược bỏ một số thông điệp và chi tiết transcript của TLS. Trình tự thực tế phụ thuộc phiên bản TLS, cấu hình và thư viện. Trong TLS 1.3, client certificate authentication có thể diễn ra trong handshake ban đầu hoặc qua post-handshake authentication nếu hai bên hỗ trợ và cấu hình phù hợp.

### Các bước kiểm tra ở server

1. Nhận certificate chain do client trình bày.
2. Xây dựng đường dẫn chứng chỉ tới trust anchor được cấu hình; kiểm tra chữ ký trên từng mắt xích.
3. Kiểm tra thời hạn, Basic Constraints, Key Usage, EKU, name constraints, policy và các điều kiện path validation theo chuẩn/thư viện.
4. Kiểm tra trạng thái thu hồi theo chính sách (CRL/OCSP hoặc cơ chế PKI nội bộ).
5. Xác minh client chứng minh quyền kiểm soát private key trong handshake; chữ ký phải khớp transcript và public key.
6. Ánh xạ danh tính SAN/Subject đã xác minh sang principal nội bộ.
7. Kiểm tra principal có được phép kết nối và thực hiện request hay không.

**Không chỉ kiểm tra rằng certificate được ký bởi một CA nào đó.** Phải xác định CA ấy có nằm trong trust domain phù hợp, chứng chỉ dành cho đúng vai trò, đúng tên/danh tính và chưa bị thu hồi theo chính sách.

## 6. PKI: phát hành, gia hạn và quản lý chứng chỉ

### 6.1. Enrollment và Certificate Signing Request (CSR)

Một quy trình cấp chứng chỉ thường gồm:

1. Chủ thể tạo cặp khóa ở nơi được bảo vệ; private key không cần rời khỏi thiết bị/HSM/TPM nếu cơ chế hỗ trợ.
2. Chủ thể tạo **CSR** chứa public key và các thuộc tính đề nghị (ví dụ SAN).
3. RA/CA hoặc dịch vụ enrollment xác minh danh tính và quyền yêu cầu cấp certificate theo chính sách.
4. CA kiểm tra CSR, chính sách profile, Key Usage/EKU và ký certificate.
5. Chủ thể nhận certificate và cài đặt vào đúng workload/thiết bị; verifier tin cậy CA theo trust store riêng.

CSR thường được ký bằng private key tương ứng để chứng minh người gửi có quyền tạo yêu cầu với khóa đó. Tuy nhiên, chữ ký CSR **không tự xác minh danh tính con người hoặc quyền được cấp SAN tùy ý**. CA/RA phải xác minh quyền đối với thuộc tính yêu cầu trước khi ký.

### 6.2. Gia hạn và xoay vòng

Chứng chỉ có thời hạn hữu hạn. Hệ thống cần:

- Theo dõi ngày hết hạn và gia hạn trước khi đến hạn đủ lâu để xử lý sự cố.
- Có quy trình thay key/certificate; quyết định giữ hay tạo key mới theo chính sách.
- Cập nhật trust store và chain đúng thứ tự; kiểm thử tương thích giữa client/server.
- Thu hồi chứng chỉ cũ khi private key nghi bị lộ hoặc chủ thể không còn được phép.
- Có giám sát để tránh certificate hết hạn làm ngừng dịch vụ hàng loạt.

**Rotation không đồng nghĩa revocation.** Gia hạn bình thường tạo certificate mới và chuyển dịch vụ sang sử dụng nó; thu hồi là tuyên bố certificate cũ không còn được chấp nhận trước thời hạn vì một lý do cụ thể. Hai thao tác cần kế hoạch riêng.

### 6.3. Bảo vệ private key

Private key là bí mật quan trọng nhất trong mô hình này. Có thể dùng:

- HSM hoặc TPM để giữ khóa và thực hiện ký mà không xuất private key.
- Quyền truy cập theo service identity, process và vai trò quản trị.
- File permission, secret store và mã hóa phù hợp nếu khóa phải được lưu ở dạng có thể truy cập bởi workload.
- Quy trình backup/restore có kiểm soát; không sao chép khóa vào log, image, repository hoặc ticket hỗ trợ.
- Audit thao tác tạo, sử dụng, export, rotation và xóa khóa.

Nếu private key bị sao chép, kẻ tấn công có thể chứng minh quyền kiểm soát credential cho tới khi certificate bị thu hồi hoặc các cơ chế khác chặn được. Bảo vệ key vì thế quan trọng ngang với bảo vệ password verifier hoặc TOTP secret.

## 7. Xây dựng và xác minh certificate chain

Một chuỗi chứng chỉ phổ biến:

~~~text
End-entity certificate (client/server)
            |
            v
Intermediate CA certificate
            |
            v
Root CA / configured trust anchor
~~~

Verifier phải xây dựng và kiểm tra **certification path** theo trust anchor đã cấu hình. Certificate chain do client gửi có thể chứa intermediate certificate, nhưng client không được tự chọn root CA để bắt verifier tin cậy.

Các kiểm tra quan trọng:

- Chữ ký từng chứng chỉ trong path hợp lệ.
- Issuer/subject và quan hệ khóa phù hợp để nối path.
- Basic Constraints xác định CA; path length và name constraints được tuân thủ.
- Thời hạn từng chứng chỉ còn hiệu lực.
- Key Usage/EKU phù hợp với client authentication hoặc server authentication.
- Certificate Policies và thuật toán mật mã đáp ứng trust policy.
- Trust anchor thuộc đúng môi trường/tổ chức/tenant.
- Trạng thái thu hồi được xử lý theo chính sách.

### Vì sao “chứng chỉ được ký” chưa đủ?

Một chứng chỉ có chữ ký hợp lệ có thể:

- Được phát hành bởi CA không nằm trong trust store của dịch vụ.
- Được phát hành cho website server nhưng bị dùng làm client certificate.
- Có SAN không khớp principal mà API mong đợi.
- Đã hết hạn hoặc bị thu hồi.
- Thuộc một tenant hoặc môi trường khác.
- Có chuỗi tin cậy hợp lệ nhưng không được chính sách cho phép sử dụng cho hành động đang yêu cầu.

Do đó, **path validation, purpose validation và identity mapping** là ba bước khác nhau, đều cần thiết.

## 8. Thu hồi và trạng thái chứng chỉ

Chứng chỉ có thể cần bị thu hồi trước ngày hết hạn khi private key bị lộ, thiết bị mất, chủ thể rời tổ chức, thuộc tính danh tính sai hoặc CA phát hiện cấp phát nhầm.

### CRL và OCSP

| Cơ chế | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **CRL (Certificate Revocation List)** | CA công bố danh sách serial number đã thu hồi; verifier tải và kiểm tra. | Có thể cache và kiểm tra offline, nhưng danh sách lớn hoặc cập nhật chậm. |
| **OCSP (Online Certificate Status Protocol)** | Verifier hỏi responder về trạng thái một certificate. | Có thể cập nhật nhanh hơn, nhưng phụ thuộc mạng/responder và có cân nhắc riêng tư. |
| **OCSP stapling** | Server gửi kèm phản hồi OCSP được ký trong handshake phù hợp. | Giảm truy vấn từ client và cải thiện riêng tư; vẫn cần kiểm tra chữ ký/thời hạn phản hồi. |
| **PKI nội bộ / trạng thái workload** | Dịch vụ quản lý danh tính và vòng đời certificate, có thể hỗ trợ thu hồi/rotation tự động. | Phụ thuộc kiến trúc và tính nhất quán của hệ thống quản lý. |

### Fail-open hay fail-closed khi không kiểm tra được thu hồi?

Không có một lựa chọn đúng cho mọi hệ thống. Quyết định phải xuất phát từ **risk policy**:

- Với hệ thống yêu cầu bảo đảm cao, nếu kiểm tra thu hồi là điều kiện bắt buộc mà responder không sẵn sàng, có thể phải từ chối kết nối hoặc chuyển sang trạng thái tạm không khả dụng.
- Với một số hệ thống có ràng buộc vận hành khác, có thể cho phép dùng trạng thái đã cache còn trong thời hạn tin cậy; phải đặt giới hạn tuổi dữ liệu và giám sát.
- Không nên âm thầm coi certificate là “good” khi chưa có bằng chứng và chính sách không cho phép.

OCSP/CRL không thay thế việc quản lý vòng đời khóa. Khi key bị lộ, cần xác định phạm vi, thu hồi certificate liên quan, cấp key/certificate mới và rà soát phiên/token đã phát hành từ danh tính đó.

## 9. Ánh xạ danh tính từ certificate sang tài khoản

Sau khi xác minh certificate và proof of possession, ứng dụng cần ánh xạ danh tính được chứng nhận sang **principal** nội bộ. Một số thuộc tính có thể dùng:

- SAN URI chứa định danh workload theo quy ước của tổ chức.
- SAN DNS cho danh tính máy chủ hoặc service có tên DNS ổn định.
- SAN email trong một số trường hợp có chính sách xác minh rõ.
- Subject DN hoặc serial/issuer pair theo profile PKI cụ thể.
- URI/SPIFFE ID trong môi trường workload identity nếu hệ thống triển khai mô hình đó.

Không nên dùng CN đơn lẻ như khóa tài khoản nếu có khả năng trùng, thay đổi hoặc bị cấp phát sai. Một định danh certificate nên được xác định trong **phạm vi issuer/trust domain**. Cặp issuer + serial có thể nhận diện một certificate cụ thể; principal thường nên dựa vào định danh SAN/subject ổn định theo profile đã được CA xác minh.

Ví dụ ánh xạ:

~~~text
Certificate identity:
  issuer:    CN=Company Workload Intermediate CA
  SAN URI:   spiffe://corp.example/ns/payments/sa/checkout
  EKU:       clientAuth

Internal principal:
  workload_id: payments/checkout
  tenant:      finance
  environment: production
~~~

Ví dụ trên là dữ liệu khái niệm. Không cấp quyền chỉ vì chuỗi SAN chứa từ \`payments\`; cần kiểm tra issuer/trust domain, profile phát hành, danh tính chính xác và trạng thái workload trong hệ thống quản lý.

### Authentication khác Authorization

Certificate có thể chứng minh một workload là \`payments/checkout\`, nhưng không có nghĩa workload ấy được phép đọc mọi dữ liệu thanh toán. API vẫn phải kiểm tra:

- Principal có hoạt động và thuộc tenant phù hợp không?
- Request nhắm tới resource/action nào?
- Workload có scope/role cần thiết không?
- Quyền có bị thu hồi hoặc giới hạn theo môi trường không?

Không biến việc “có certificate từ CA nội bộ” thành quyền quản trị toàn bộ hệ thống.

## 10. Certificate authentication cho người dùng và cho workload

### Người dùng

Client certificate có thể được cài trong hệ điều hành, smart card hoặc thiết bị bảo mật. Trình duyệt/OS có thể hiển thị hộp thoại chọn certificate. Server xác minh chain và proof of possession, rồi ánh xạ certificate tới người dùng nội bộ.

Các vấn đề cần xử lý:

- Người dùng có nhiều certificate hoặc certificate hết hạn.
- Chứng chỉ được cấp cho thiết bị dùng chung hay tài khoản cá nhân.
- Cách thay certificate khi đổi máy hoặc mất smart card.
- Đăng nhập qua reverse proxy/load balancer và cách chuyển thông tin danh tính đã xác minh tới ứng dụng.
- Step-up hoặc MFA bổ sung cho hành động đặc biệt nếu certificate đơn lẻ không đáp ứng mức bảo đảm yêu cầu.

Không mặc định client certificate luôn chứng minh **người cụ thể đang ngồi trước máy**. Nếu chứng chỉ gắn với thiết bị, nó xác thực thiết bị hoặc khóa thiết bị; cần thêm cơ chế user verification nếu chính sách yêu cầu xác thực con người.

### Workload/service-to-service

Trong hệ thống microservices, mTLS có thể xác thực service gọi và service nhận. Certificate thường có vòng đời tự động, thời hạn ngắn và identity theo namespace/service account. Các nền tảng workload identity có thể cấp certificate động, rotation tự động và trust domain riêng.

Lợi ích:

- Không cần phân phối một password/API key tĩnh dùng lâu dài cho mọi service.
- Có thể xác minh service identity ở tầng transport.
- Hỗ trợ mã hóa và xác thực hai chiều trên kênh kết nối.
- Cho phép policy dựa trên principal thay vì địa chỉ IP đơn thuần.

Giới hạn:

- Private key hoặc workload runtime bị xâm nhập vẫn có thể dùng identity hợp lệ.
- Certificate không tự giới hạn quyền nghiệp vụ; authorization vẫn cần.
- Trust store, CA và quy trình cấp phát sai có thể tạo quyền tin cậy quá rộng.
- TLS termination ở proxy có thể làm thay đổi điểm mà ứng dụng nhìn thấy client identity.

## 11. TLS termination, proxy và chuyển tiếp danh tính

Trong kiến trúc thực tế, TLS/mTLS có thể kết thúc tại load balancer, API gateway hoặc service mesh proxy thay vì ứng dụng cuối. Khi đó phải xác định **thành phần nào đã xác minh client certificate** và cách kết quả được chuyển tiếp.

~~~mermaid
flowchart LR
    C["Client certificate + proof"]
    G["Gateway / ingress<br/>kết thúc mTLS"]
    H["Backend service"]
    P["Policy / identity mapping"]
    C -->|"TLS handshake"| G
    G -->|"Thông tin principal đã xác minh<br/>qua kênh nội bộ bảo vệ"| H
    H --> P
    X["Client không tin cậy"] -.->|"Giả header identity"| H
~~~

Nếu gateway xác minh certificate rồi gửi header như \`X-Client-Cert-Subject\` tới backend, backend chỉ được tin header đó khi:

- Backend chỉ nhận kết nối từ gateway được tin cậy qua kênh nội bộ bảo vệ.
- Gateway **xóa header cùng tên do client tự gửi** trước khi đặt giá trị đã xác minh.
- Có xác thực gateway-to-backend, ví dụ mTLS nội bộ hoặc cơ chế tương đương.
- Header được định dạng/escape và ánh xạ theo contract rõ ràng; không nhận chuỗi tùy ý làm quyền.
- Có audit cho principal gốc và điểm xác thực.

Nếu backend có thể bị gọi trực tiếp từ mạng ngoài hoặc client có thể tự chèn header, kẻ tấn công có thể giả danh bằng cách gửi \`X-Client-Cert-Subject: admin\`. Không để ứng dụng tin một header identity mà chưa có ranh giới tin cậy bảo vệ.

## 12. Các kiểu tấn công và lỗi cấu hình

| Rủi ro | Kịch bản | Kiểm soát |
| --- | --- | --- |
| **Private key theft** | Kẻ tấn công sao chép key và dùng certificate hợp lệ. | HSM/TPM, non-exportable key, quyền tối thiểu, rotation/revocation. |
| **Rogue/compromised CA** | CA không đáng tin hoặc bị xâm nhập phát hành certificate giả. | Quản lý trust anchor, phân tách CA, kiểm soát RA, audit và quy trình xử lý sự cố. |
| **Wrong EKU/Key Usage** | Certificate serverAuth bị dùng làm clientAuth hoặc ngược lại. | Kiểm tra purpose và extension theo policy. |
| **Hostname/SAN confusion** | Chấp nhận CN hoặc SAN không khớp danh tính mong đợi. | So khớp đúng SAN type, hostname/service identity và trust domain. |
| **Expired/revoked certificate** | Certificate hết hạn hoặc đã thu hồi vẫn được chấp nhận do bỏ kiểm tra. | Path validation, kiểm tra trạng thái và giám sát cache/clock. |
| **Weak certificate mapping** | Ánh xạ theo chuỗi CN/email không duy nhất hoặc do client cung cấp. | Identity mapping theo SAN/profile, issuer và dữ liệu provisioning tin cậy. |
| **Trust store quá rộng** | Tin mọi CA trong hệ điều hành cho một API nội bộ nhạy cảm. | Trust store chuyên biệt và giới hạn CA theo môi trường/tenant. |
| **TLS termination spoofing** | Backend tin header certificate do client gửi. | Chỉ tin gateway đã xác minh, strip header đầu vào, bảo vệ kênh nội bộ. |
| **Replay ở tầng ứng dụng** | Một request đã xác thực được phát lại để lặp thao tác. | TLS chống replay ở transport không thay thế idempotency, nonce, timestamp hoặc chống replay nghiệp vụ. |
| **Downgrade/fallback** | Khi mTLS lỗi, gateway cho truy cập bằng HTTP hoặc chỉ IP. | Không hạ cấp âm thầm; chính sách fallback phải giữ mức bảo đảm tối thiểu. |
| **Certificate mis-issuance** | SAN của service khác được cấp sai hoặc quá rộng. | Xác minh quyền đối với SAN, profile CA, kiểm soát enrollment và audit. |

**TLS chống nghe lén và giả mạo trên kênh, nhưng không tự chống replay ở tầng nghiệp vụ.** Một request thanh toán có thể được gửi lại qua một kết nối TLS mới nếu API không có idempotency key hoặc cơ chế chống thực hiện lặp. Cần phân biệt replay handshake/protocol với replay một hành động đã được xác thực.

## 13. Mã giả: xác minh certificate client

Đoạn mã sau mô tả các lớp quyết định; đây là **mã giả**, không thay thế thư viện TLS/X.509 đã được kiểm thử.

~~~text
authenticateClientCertificate(tlsPeer, request):
    cert = tlsPeer.leafCertificate
    if cert is missing:
        return unauthenticated()

    pathResult = x509Library.validatePath(
        leaf = cert,
        intermediates = tlsPeer.presentedChain,
        trustAnchors = configuredTrustAnchors(),
        validationTime = trustedClock.now(),
        requiredPurpose = "clientAuth",
        policy = configuredPkIValidationPolicy()
    )
    if not pathResult.valid:
        audit("certificate_path_invalid", safeMetadata(pathResult.reason))
        return unauthenticated()

    if revocationPolicy.requiresStatusCheck:
        status = checkCertificateStatus(cert, pathResult)
        if status == "revoked":
            return unauthenticated()
        if status == "unknown" and not revocationPolicy.allowsCachedStatus():
            return controlledUnavailableOrDenied()

    if not tlsPeer.proofOfPrivateKeyVerified:
        return unauthenticated()

    identity = extractAllowedIdentityFromSan(cert)
    if identity is missing:
        return unauthenticated()

    principal = trustedIdentityDirectory.lookup(
        issuer = pathResult.trustedIssuer,
        identity = identity
    )
    if principal is missing or not principal.active:
        return unauthenticated()

    if not authorizationPolicy.allows(principal, request.resource, request.action):
        return forbidden()

    audit("certificate_authentication_succeeded", safeMetadata(principal))
    return authenticatedAs(principal)
~~~

Trong TLS, proof of private key thường được xác minh bởi thư viện TLS trong handshake, không phải bằng một cờ do ứng dụng tự đặt. Ứng dụng chỉ nên sử dụng metadata peer certificate từ kết nối TLS đã được cấu hình xác minh đúng. Nếu TLS kết thúc ở proxy, cần xác minh proxy và contract chuyển tiếp danh tính như phần trước.

Không tự viết X.509 path validation, kiểm tra chữ ký hoặc TLS handshake bằng code nghiệp vụ. Dùng thư viện chuẩn, cập nhật và cấu hình đúng trust store, hostname/purpose, thuật toán, thời hạn và trạng thái thu hồi.

## 14. Vận hành: rotation, thu hồi và ứng phó sự cố

Khi nghi private key bị lộ:

1. Xác định certificate, issuer, principal, thiết bị/workload và phạm vi tài nguyên có thể bị truy cập.
2. Thu hồi certificate hoặc vô hiệu hóa principal theo quy trình PKI; cập nhật CRL/OCSP hoặc trạng thái nội bộ.
3. Tạo cặp khóa mới ở môi trường được bảo vệ; phát hành certificate mới sau khi xác minh lại danh tính/quyền cấp.
4. Cập nhật workload/client và trust configuration; xác nhận không còn dùng key cũ.
5. Thu hồi session/token/API credential đã phát hành từ principal nếu chính sách yêu cầu.
6. Rà soát log kết nối, hoạt động API, thay đổi quyền và dấu hiệu di chuyển ngang.
7. Thông báo các bên liên quan và lưu audit về thời điểm phát hiện, thu hồi, thay thế.

### Certificate rotation không nên làm gián đoạn toàn hệ thống

- Có thời gian chồng lấp có kiểm soát giữa certificate cũ và mới nếu chính sách cho phép.
- Cập nhật trust chain trước khi chuyển workload; kiểm tra cả hai phía mTLS.
- Theo dõi thời hạn và cảnh báo sớm; không chờ đến phút cuối mới cấp lại.
- Kiểm thử thay đổi CA/intermediate và khả năng tương thích của client cũ.
- Thu hồi ngay khi key bị xâm phạm, không giữ certificate cũ chỉ vì tiện triển khai.

Đối với workload identity có thể tự động hóa issuance/rotation theo vòng đời ngắn. Tuy nhiên, cần bảo vệ control plane cấp chứng chỉ và tránh cho workload yêu cầu SAN/identity tùy ý.

## 15. Kiểm thử luồng certificate authentication

Các trường hợp cần kiểm thử trước khi phát hành:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Certificate chain hợp lệ, đúng clientAuth, proof of possession hợp lệ | TLS client authentication thành công; principal được ánh xạ đúng. |
| Không gửi client certificate khi endpoint bắt buộc mTLS | Handshake hoặc yêu cầu bị từ chối theo cấu hình. |
| Certificate do CA ngoài trust store cấp | Từ chối. |
| Intermediate/root không hợp lệ hoặc chữ ký chain sai | Từ chối path validation. |
| Certificate hết hạn/chưa tới Not Before | Từ chối theo thời gian xác minh. |
| Certificate bị thu hồi | Từ chối theo chính sách trạng thái. |
| EKU thiếu clientAuth hoặc Key Usage không phù hợp | Từ chối dùng sai mục đích. |
| SAN không khớp principal hoặc thuộc tenant khác | Không ánh xạ sang tài khoản/quyền khác. |
| Certificate công khai hợp lệ nhưng client không có private key | Không hoàn tất proof of possession. |
| Client gửi header giả Subject/Identity khi đi qua proxy | Backend bỏ qua header do client cung cấp; chỉ tin metadata từ gateway xác thực. |
| Private key bị thu hồi nhưng session/token cũ còn sống | Xử lý thu hồi session/token theo chính sách, không giả định certificate revocation tự xóa mọi phiên. |
| CA hoặc OCSP responder tạm không sẵn sàng | Hành vi theo revocation policy đã định; không âm thầm chấp nhận trạng thái chưa kiểm chứng. |
| Certificate hợp lệ nhưng principal không có quyền gọi API | Authentication đạt nhưng authorization từ chối. |

### Kiểm thử cả đường thành công

Không chỉ thử certificate sai. Cần xác nhận:

- Client hợp lệ có thể gia hạn và rotation mà không tạo gián đoạn không cần thiết.
- Trust store đúng môi trường, không chấp nhận nhầm certificate từ staging ở production.
- Danh tính SAN được ánh xạ nhất quán sau khi thay certificate.
- Proxy/gateway truyền principal đúng qua kênh nội bộ được bảo vệ.
- Logout/thu hồi session và vô hiệu hóa principal có tác dụng theo chính sách.

## 16. Checklist thiết kế

- [ ] Xác định rõ chủ thể cần xác thực: người dùng, thiết bị hay workload.
- [ ] Dùng TLS/mTLS phù hợp và xác minh cả certificate lẫn proof of possession.
- [ ] Private key được tạo/lưu trong môi trường bảo vệ; không gửi hoặc ghi log private key.
- [ ] Trust anchors được cấu hình từ nguồn tin cậy và giới hạn theo môi trường/tenant.
- [ ] Xây dựng và kiểm tra certificate path, thời hạn, Basic Constraints, Key Usage, EKU, name constraints và policy.
- [ ] So khớp danh tính bằng SAN/identity profile rõ ràng; không dựa vào CN tùy tiện.
- [ ] Kiểm tra trạng thái thu hồi theo risk policy, có quyết định rõ khi CRL/OCSP không sẵn sàng.
- [ ] Có quy trình enrollment xác minh quyền đối với SAN/Subject; không tin CSR chỉ vì chữ ký hợp lệ.
- [ ] Có rotation, gia hạn, thu hồi, backup và ứng phó private key bị lộ.
- [ ] Identity mapping và authorization được tách riêng; certificate không tự cấp quyền rộng.
- [ ] Nếu TLS terminate ở proxy, bảo vệ kênh backend và loại bỏ header identity do client gửi.
- [ ] Session/token phát hành sau certificate authentication có TTL và cơ chế thu hồi riêng.
- [ ] Kiểm thử certificate sai issuer, EKU, SAN, hết hạn, revoked, thiếu private key và lỗi phụ thuộc.
- [ ] Audit đủ điều tra nhưng không ghi private key, session ID hoặc token thô.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một certificate X.509 hợp lệ chưa đủ để chứng minh client đang kiểm soát danh tính đó?

**Gợi ý:** Certificate chứa public key và chữ ký CA; client còn phải chứng minh giữ private key tương ứng, ví dụ qua TLS CertificateVerify.

**Câu 2.** Vì sao không nên chỉ kiểm tra CN trong certificate để cấp quyền quản trị?

**Gợi ý:** CN có thể trùng, thay đổi hoặc không phải định danh ổn định; cần SAN/profile, issuer/trust domain và identity mapping có kiểm soát, sau đó mới authorization.

**Câu 3.** mTLS có thay thế authorization ở API không?

**Gợi ý:** Không. mTLS xác thực peer và bảo vệ kênh; API vẫn kiểm tra principal được phép thực hiện action trên resource nào.

**Câu 4.** Nếu OCSP responder không phản hồi, có nên luôn coi certificate là hợp lệ không?

**Gợi ý:** Không. Quyết định phụ thuộc revocation policy, mức rủi ro và trạng thái cache đáng tin; không được âm thầm chấp nhận trạng thái chưa kiểm chứng.

**Câu 5.** Nếu gateway xác minh client certificate, tại sao backend không thể tin một header cùng tên do client gửi?

**Gợi ý:** Client có thể giả header. Backend chỉ tin metadata từ gateway sau khi xác minh gateway và kênh nội bộ, đồng thời gateway phải loại bỏ header đầu vào.

**Câu 6.** Thu hồi certificate có tự động vô hiệu hóa mọi JWT/session đã cấp trước đó không?

**Gợi ý:** Không nhất thiết. Credential certificate và session/token có vòng đời khác nhau; cần cơ chế thu hồi/TTL/introspection phù hợp.

## 18. Ghi nhớ

**Certificate authentication xác minh danh tính thông qua chứng chỉ được tin cậy và bằng chứng kiểm soát private key tương ứng.** Một luồng an toàn cần xác minh certificate path tới trust anchor phù hợp, kiểm tra thời hạn, mục đích sử dụng, SAN, trạng thái thu hồi và proof of possession; sau đó ánh xạ principal và thực hiện authorization riêng. PKI còn đòi hỏi quy trình enrollment, bảo vệ khóa, rotation, revocation và giám sát. mTLS giúp xác thực hai chiều giữa client và server, nhưng không tự giải quyết quyền nghiệp vụ hoặc bảo vệ session/token sau handshake.
