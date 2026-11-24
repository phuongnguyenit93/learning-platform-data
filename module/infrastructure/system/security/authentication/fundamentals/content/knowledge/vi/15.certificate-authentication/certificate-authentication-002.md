# Client certificate — Xác thực client bằng chứng chỉ số

> **Chương:** Certificate authentication  
> **Chủ đề:** Client certificate

**Client certificate** là chứng chỉ số mà một client trình bày để chứng minh danh tính của mình với server. Trong HTTPS thông thường, client xác minh chứng chỉ của server; với **mutual TLS (mTLS)**, server còn yêu cầu và kiểm tra chứng chỉ của client. Client phải chứng minh đang kiểm soát khóa riêng tương ứng trong quá trình bắt tay TLS. Vì vậy, xác thực client bằng chứng chỉ không phải là gửi một tệp chứng chỉ lên API, mà là kết hợp **chuỗi chứng chỉ đáng tin cậy, danh tính kỳ vọng và proof of possession** trong một giao thức bảo mật.

Client có thể là trình duyệt của nhân viên, ứng dụng desktop/mobile, thiết bị được quản lý, máy POS hoặc một workload/microservice. Mỗi loại chủ thể cần quy trình cấp phát và ánh xạ danh tính khác nhau. Một chứng chỉ hợp lệ chỉ xác lập danh tính theo chính sách cấp chứng chỉ; nó **không tự cấp quyền** đọc dữ liệu, gọi API hay thực hiện giao dịch.

Bài học đặt client certificate trong phạm vi **SECURITY_AUTHENTICATION_FUNDAMENTALS**: mô hình hóa ranh giới tin cậy, lựa chọn danh tính, kiểm chứng X.509, vận hành mTLS, bảo vệ khóa riêng, xử lý proxy/TLS termination, thu hồi và liên kết với phiên/token.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt xác thực server bằng server certificate với xác thực client bằng client certificate.
2. Mô tả luồng TLS/mTLS và giải thích client chứng minh sở hữu khóa riêng như thế nào.
3. Kiểm tra certificate chain, trust anchor, SAN, Key Usage, EKU, thời hạn và trạng thái thu hồi.
4. Ánh xạ client certificate thành principal nội bộ theo nguồn, phạm vi và tenant.
5. Thiết kế cấp phát, cài đặt, gia hạn, rotation và thu hồi client certificate.
6. Xử lý an toàn TLS termination tại load balancer/API gateway và việc chuyển danh tính tới backend.
7. Phân biệt client authentication với authorization, certificate pinning, bearer token và session.
8. Xây dựng test plan cho certificate sai, khóa không khớp, chứng chỉ hết hạn, proxy header giả và quyền truy cập vượt phạm vi.

## 2. Client certificate dùng để làm gì?

Client certificate phù hợp khi server cần xác thực một thiết bị, ứng dụng hoặc workload bằng mật mã khóa công khai thay vì chỉ dựa vào password/API key dùng chung.

| Chủ thể client | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Người dùng** | Nhân viên dùng smart card hoặc certificate trên thiết bị quản lý | Xác thực người dùng trong môi trường doanh nghiệp |
| **Trình duyệt** | Browser chọn certificate cá nhân khi truy cập cổng nội bộ | Xác thực client ở lớp TLS |
| **Thiết bị** | Máy kiosk, thiết bị y tế, thiết bị IoT | Chứng minh thiết bị được cấp và quản lý |
| **Ứng dụng** | Ứng dụng desktop/native được cấp certificate | Xác thực một client cụ thể theo chính sách |
| **Workload/service** | Microservice gọi API nội bộ | Xác thực service-to-service và giới hạn danh tính |
| **Đối tác tích hợp** | Hệ thống đối tác kết nối B2B | Xác thực kênh và client thuộc đối tác đã đăng ký |

Một certificate có thể đại diện cho **một thiết bị**, **một workload** hoặc **một người dùng**. Không được nhập nhằng các loại principal này. Nếu certificate xác thực thiết bị laptop, server không nên tự suy ra người đang ngồi trước laptop là nhân viên cụ thể nào nếu chưa có bước liên kết danh tính người dùng.

### 2.1. Server certificate và client certificate

| Thuộc tính | Server certificate | Client certificate |
| --- | --- | --- |
| Ai trình bày? | Server | Client |
| Ai xác minh? | Client | Server |
| Mục đích phổ biến | Chứng minh server identity, thường serverAuth | Chứng minh client identity, thường clientAuth |
| Danh tính thường kiểm tra | DNS SAN/hostname hoặc identity server kỳ vọng | URI SAN, DNS SAN, subject hoặc mapping theo policy |
| Proof of possession | Server chứng minh giữ private key trong TLS handshake | Client chứng minh giữ private key trong TLS handshake |
| Trust policy | Trust store của client | Trust store/client CA policy của server |

Một client xác minh server certificate đúng không có nghĩa server cũng đã xác minh client. **HTTPS một chiều** vẫn có thể bảo vệ kênh nhưng không xác thực danh tính client ở lớp chứng chỉ.

## 3. mTLS: client certificate được dùng trong TLS như thế nào?

Trong TLS thông thường, server gửi chứng chỉ để client xác minh tên server và chuỗi tin cậy. Trong mTLS, server yêu cầu client trình bày certificate; client gửi chuỗi cần thiết và chứng minh sở hữu private key tương ứng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as TLS Server
    participant T as Trust policy
    C->>S: ClientHello
    S-->>C: ServerHello + Server Certificate + proof
    C->>T: Xác minh server chain và server identity
    T-->>C: Kết quả kiểm tra
    S-->>C: CertificateRequest
    C->>S: Client Certificate (nếu được chọn)
    C->>S: CertificateVerify (proof of possession)
    C->>S: Finished
    S->>T: Xác minh client chain, purpose, SAN, trạng thái
    T-->>S: Kết quả theo trust policy
    S->>S: Ánh xạ certificate -> principal
    S-->>C: Hoàn tất TLS và cho phép request tiếp tục
~~~

Sơ đồ lược bớt một số thông điệp và chi tiết phiên bản TLS. Trong TLS 1.3, CertificateVerify ký dữ liệu gắn với handshake transcript; chữ ký chứng minh client giữ private key trong **phiên bắt tay hiện tại**. TLS 1.2 có trình tự và chi tiết khác. Triển khai phải dựa trên thư viện TLS chuẩn, không tự xây dựng handshake theo sơ đồ khái niệm.

### 3.1. Server yêu cầu certificate ở đâu?

Server gửi thông điệp **CertificateRequest** theo chính sách TLS. Nó có thể cung cấp gợi ý CA được chấp nhận và các thuật toán chữ ký phù hợp. Client có thể:

- Chọn certificate phù hợp từ kho chứng chỉ của hệ điều hành, smart card hoặc thiết bị;
- Gửi certificate chain cần thiết và proof of possession;
- Không có certificate phù hợp hoặc người dùng hủy chọn, khiến handshake bị từ chối hoặc tiếp tục như client chưa xác thực, tùy cấu hình server.

Với endpoint yêu cầu mTLS bắt buộc, server phải từ chối nếu không có client identity hợp lệ. Không nên cấu hình certificate optional rồi vô tình cho phép truy cập nhạy cảm khi client không trình bày chứng chỉ.

### 3.2. Chứng minh sở hữu khóa riêng

Certificate chứa public key. Client sử dụng private key để ký phần dữ liệu handshake theo TLS; server xác minh chữ ký bằng public key trong certificate. Private key không được gửi qua mạng. Chỉ sao chép certificate công khai không đủ để giả mạo client.

Tuy nhiên, nếu private key bị trích xuất hoặc thiết bị bị chiếm quyền sử dụng khóa, kẻ tấn công có thể tạo kết nối mới bằng certificate đó. Proof of possession chứng minh khả năng dùng khóa, không chứng minh thiết bị đang an toàn hay người dùng đang có mặt.

## 4. Kiểm tra client certificate

Server cần kiểm tra cả **độ tin cậy mật mã** và **danh tính ứng dụng mong đợi**. Một certificate được ký bởi CA nào đó không có nghĩa nó được phép đại diện cho bất kỳ client nào.

### 4.1. Các bước xác minh chính

1. **Xây dựng chain:** từ leaf certificate qua intermediate CA tới trust anchor được cấu hình cho client authentication.
2. **Kiểm tra chữ ký và constraints:** xác minh chữ ký từng mắt xích, Basic Constraints, path length, Key Usage, extension critical và Name Constraints.
3. **Kiểm tra thời hạn:** notBefore/notAfter của các chứng chỉ liên quan và đồng hồ hệ thống.
4. **Kiểm tra mục đích:** EKU có cho phép client authentication không; Key Usage có phù hợp với chữ ký không.
5. **Kiểm tra danh tính:** SAN hoặc mapping phải khớp principal kỳ vọng, đúng trust domain/tenant.
6. **Kiểm tra trạng thái:** áp dụng CRL, OCSP, denylist hoặc chính sách certificate ngắn hạn theo mức rủi ro.
7. **Kiểm tra proof of possession:** TLS handshake phải chứng minh client giữ private key tương ứng.
8. **Ánh xạ principal:** chuyển kết quả đã xác minh thành danh tính nội bộ có phạm vi rõ ràng.

Các thư viện TLS/PKIX có thể thực hiện phần lớn kiểm tra chain, nhưng ứng dụng vẫn cần kiểm tra **client identity kỳ vọng** và policy riêng. Không tắt certificate verification để làm kết nối “chạy được”.

### 4.2. Subject, SAN và danh tính client

Các trường thường được dùng:

| Trường | Cách dùng | Lưu ý |
| --- | --- | --- |
| **Subject** | Thông tin nhận diện trong chứng chỉ | CN không nên là cơ chế duy nhất để xác định client |
| **DNS SAN** | Tên DNS của máy hoặc workload | Kiểm tra đúng loại tên và trust domain |
| **URI SAN** | Định danh workload/service hoặc principal theo quy ước | Phải có namespace và quy tắc cấp phát được quản lý |
| **IP SAN** | Địa chỉ IP khi kiến trúc thực sự cần | IP có thể thay đổi; thường không phải định danh service bền vững |
| **Issuer + Serial** | Nhận diện một chứng chỉ cụ thể | Hữu ích cho inventory/revocation; không phải principal lâu dài |
| **Fingerprint** | Dấu vân tay certificate | Phù hợp pinning/inventory trong phạm vi cụ thể; thay đổi khi certificate thay |

Ví dụ mapping cho workload:

~~~text
Verified certificate:
  issuer: Internal Workload CA
  SAN URI: spiffe://learning.example/workload/report-worker
  EKU: clientAuth

Identity mapping:
  trust_domain: learning.example
  workload_id: report-worker
  internal_principal: svc_report_worker
  tenant_scope: platform-internal
~~~

Đây là dữ liệu minh họa. Không cấp quyền chỉ từ chuỗi CN hoặc SAN nếu certificate không đến từ CA được phép và không được kiểm tra đúng profile. Với client là con người, mapping có thể cần subject ID nội bộ và quy trình enrollment người dùng; với workload, principal thường đại diện service chứ không phải nhân viên vận hành.

### 4.3. EKU và Key Usage

Certificate client thường cần **Extended Key Usage** phù hợp với client authentication (OID clientAuth) và Key Usage cho phép mục đích chữ ký theo thuật toán/chính sách. Một certificate chỉ được phát hành cho server authentication không nên được chấp nhận làm client credential nếu policy yêu cầu phân tách mục đích.

Nếu EKU không có hoặc có nhiều mục đích, cách xử lý phụ thuộc profile và policy PKI. Hệ thống nên quy định rõ loại certificate nào được phép dùng ở từng endpoint; không suy luận mọi certificate từ một CA đều có thể làm cả server lẫn client.

## 5. Trust store và giới hạn CA được phép

Server cần một **trust store** hoặc cấu hình trust anchor cho client authentication. Đây là quyết định quản trị: tổ chức tin những CA nào được phép cấp client identity trong phạm vi nào.

Các nguyên tắc:

- Tách trust store client certificate khỏi trust policy dùng cho server certificate nếu yêu cầu nghiệp vụ khác nhau.
- Giới hạn issuer/intermediate/profile có thể cấp danh tính client, thay vì tin toàn bộ CA hệ điều hành một cách vô điều kiện.
- Quản lý root/intermediate certificate và thay đổi trust bundle qua quy trình được kiểm soát, có audit.
- Dùng Name Constraints hoặc policy mapping nếu cần giới hạn namespace danh tính.
- Không tin root chỉ vì client gửi nó trong chain; trust anchor phải đến từ cấu hình đáng tin cậy.
- Kiểm tra thuật toán chữ ký, kích thước khóa và profile theo chính sách hiện hành.

Một CA nội bộ có thể cấp certificate cho nhiều mục đích. Nếu cùng một CA cấp server, client, code signing và thiết bị, endpoint client authentication cần giới hạn profile/issuer/eku/SAN để tránh certificate của mục đích khác bị chấp nhận nhầm.

## 6. Ánh xạ certificate thành principal nội bộ

Sau khi TLS xác minh certificate, ứng dụng cần xác định **principal** mà certificate đại diện. Bước này không được để client tự khai danh tính.

### 6.1. Các cách ánh xạ

| Cách ánh xạ | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- |
| **SAN URI/DNS → principal** | Danh tính rõ, có thể ổn định theo namespace | Cần quy tắc cấp và thu hồi namespace |
| **Issuer + Subject** | Dùng thuộc tính X.509 phổ biến | Subject có thể không duy nhất hoặc thay đổi |
| **Issuer + Serial** | Nhận diện chính xác một certificate | Renewal tạo serial mới; cần cập nhật mapping |
| **Fingerprint → principal** | Ràng buộc chặt với certificate cụ thể | Rotation đòi hỏi cập nhật; khó vận hành số lượng lớn |
| **Certificate → inventory/device record** | Phù hợp thiết bị được quản lý | Cần inventory authoritative và đồng bộ trạng thái |

Không có một cách mapping phù hợp mọi chủ thể. Với workload, URI SAN có namespace rõ thường hữu ích; với thiết bị, có thể ánh xạ tới device record; với người dùng, cần quy trình enrollment liên kết certificate với user ID nội bộ.

### 6.2. Không nhầm thiết bị với người dùng

Một laptop có certificate thiết bị hợp lệ chỉ chứng minh thiết bị được cấp/đăng ký theo chính sách. Nhiều người có thể sử dụng cùng máy. Nếu nghiệp vụ cần xác định nhân viên cụ thể, cần thêm user authentication hoặc cơ chế đăng nhập phù hợp; không gán danh tính người dùng chỉ từ device certificate.

Ngược lại, certificate người dùng trên smart card cần có quy trình xác minh danh tính và bảo vệ PIN/khóa. Một chứng chỉ được cấp cho nhân viên không tự chứng minh người đang sử dụng thẻ là nhân viên đó nếu thẻ/PIN bị cho mượn hoặc thiết bị bị chiếm.

### 6.3. Tenant và namespace

Trong SaaS đa tenant, mapping phải ràng buộc tenant hoặc trust domain. Không cho phép client có certificate thuộc tenant A gửi một SAN trùng tên service ở tenant B rồi nhận quyền của B. Quy tắc uniqueness cần được xác định rõ: trong issuer, trust domain, tenant hay toàn hệ thống.

## 7. TLS termination tại load balancer và API gateway

Nhiều kiến trúc kết thúc TLS tại ingress, load balancer hoặc API gateway. Khi đó gateway là thành phần thực sự nhìn thấy và xác minh client certificate. Backend phía sau chỉ nhận kết quả được chuyển tiếp.

~~~mermaid
flowchart LR
    C["Client + certificate/private key"] -->|"mTLS"| G["Gateway / TLS terminator"]
    G -->|"Verify chain, SAN, EKU, proof"| I["Identity mapping"]
    I -->|"Trusted principal context"| B["Backend API"]
    B -->|"Authorization theo resource"| P["Policy engine"]
    X["Internet client"] -.->|"Header giả X-Client-Cert"| G
    G -.->|"Phải xóa/ghi đè header do client gửi"| B
~~~

Nếu gateway chuyển danh tính qua header như X-Client-Cert, X-Forwarded-Client-Cert hoặc header nội bộ tương đương, cần kiểm soát:

1. Gateway **xóa mọi header cùng tên** từ request bên ngoài trước khi tự tạo header tin cậy.
2. Backend chỉ nhận kết nối từ gateway được xác thực, tốt nhất qua mạng/kênh nội bộ được bảo vệ và service identity rõ ràng.
3. Backend không được truy cập trực tiếp từ Internet theo đường bỏ qua gateway.
4. Header phải có định dạng và ngữ nghĩa cố định; không nhận certificate tùy ý từ header rồi tự coi là đã qua TLS verification.
5. Gateway phải chuyển đúng principal/assurance cần thiết và bảo vệ tính toàn vẹn của dữ liệu chuyển tiếp.
6. Backend vẫn kiểm tra authorization theo action, resource, tenant và trạng thái tài khoản.

**Không tin header do client tự gửi.** Nếu backend nhận được request từ client trực tiếp, kẻ tấn công có thể tự đặt X-Client-Cert: admin hoặc một chuỗi certificate giả. TLS nội bộ giữa gateway và backend giúp xác thực gateway, nhưng cần cấu hình backend chỉ tin header từ gateway đó.

### 7.1. End-to-end mTLS và re-encryption

Một số kiến trúc gateway kết thúc mTLS bên ngoài rồi tạo kết nối TLS/mTLS mới tới backend. Khi đó backend xác thực **gateway**, không trực tiếp xác thực certificate gốc của client. Nếu cần chuyển danh tính client, phải có một assertion/header được gateway xác minh và ký/bảo vệ theo hợp đồng tin cậy.

Nếu yêu cầu backend tự xác minh client certificate gốc, cần kiến trúc TLS passthrough hoặc end-to-end mTLS phù hợp. Không được tuyên bố “mTLS xuyên suốt” khi thực tế có hai phiên TLS độc lập và backend chỉ nhìn thấy gateway.

## 8. Client certificate trên trình duyệt và thiết bị người dùng

Với browser, server có thể yêu cầu client certificate trong TLS handshake. Trình duyệt hoặc hệ điều hành có thể hiển thị hộp thoại chọn certificate nếu có nhiều chứng chỉ phù hợp. Trải nghiệm phụ thuộc hệ điều hành, browser, kho chứng chỉ và cách CA được cấu hình.

### 8.1. Những điểm cần thiết kế

- **Enrollment:** chứng chỉ được cấp sau khi xác minh người dùng/thiết bị và quyền nhận certificate.
- **Cài đặt:** private key nên được giữ trong smart card, TPM, secure enclave hoặc kho khóa của hệ điều hành khi khả thi.
- **Chọn chứng chỉ:** CA hint và certificate profile giúp browser chọn đúng chứng chỉ; không nên để người dùng phải đoán giữa nhiều chứng chỉ không rõ mục đích.
- **PIN/biometric:** có thể dùng để mở khóa private key trên thiết bị; server không nhận PIN như password của tài khoản.
- **Thiết bị dùng chung:** certificate trên máy dùng chung không chứng minh ai đang sử dụng; cần user login bổ sung hoặc chính sách phiên phù hợp.
- **Mất thiết bị/thẻ:** phải có quy trình thu hồi certificate và chặn truy cập; chỉ xóa certificate trong browser không đủ nếu private key đã bị sao chép.

### 8.2. Certificate và định danh người dùng

Nếu certificate được gắn với một nhân viên, server có thể ánh xạ sang user ID nội bộ sau khi kiểm tra issuer, SAN/subject và trạng thái enrollment. Cần quy định khi nhân viên đổi đơn vị, nghỉ việc, thay thẻ hoặc được cấp lại certificate. Email hoặc tên hiển thị trong certificate không nên là khóa nội bộ duy nhất.

### 8.3. Giới hạn của browser client certificate

Client certificate có thể phù hợp cổng nội bộ hoặc thiết bị doanh nghiệp được quản lý, nhưng việc triển khai rộng cho người dùng công khai có thể phức tạp: cấp chứng chỉ, cài đặt, hỗ trợ nhiều thiết bị, thay thiết bị, recovery và thu hồi. Cần so sánh trải nghiệm với passkey/WebAuthn và các phương thức khác trước khi chọn.

## 9. Client certificate cho API và service-to-service

mTLS thường được dùng giữa microservice, workload và API gateway. Mỗi service có certificate riêng, giúp server phân biệt caller và tránh một API key dùng chung cho toàn bộ hệ thống.

### 9.1. Nguyên tắc cấp certificate cho workload

- Cấp một danh tính riêng cho mỗi workload/service hoặc nhóm có ranh giới tin cậy thực sự giống nhau.
- Không đóng gói private key production vào source repository hoặc container image dùng chung.
- Sinh khóa trong môi trường workload hoặc hệ thống quản lý khóa; ưu tiên khóa không xuất được nếu hạ tầng hỗ trợ.
- Cấp certificate qua enrollment có kiểm soát quyền SAN/URI, tenant và EKU.
- Dùng thời hạn phù hợp, tự động renewal/rotation và giám sát certificate sắp hết hạn.
- Thu hồi hoặc chặn principal khi workload bị deprovision hoặc có dấu hiệu lộ khóa.
- Giới hạn quyền API theo principal và resource; không cấp quyền rộng chỉ vì mTLS thành công.

### 9.2. Không dùng một certificate cho nhiều service không liên quan

Nếu nhiều service chia sẻ một private key/certificate, server không thể phân biệt chính xác service nào đang gọi. Khi một service bị chiếm, kẻ tấn công có thể mạo danh các service còn lại. Tách credential theo workload làm giảm phạm vi ảnh hưởng và hỗ trợ audit tốt hơn.

### 9.3. Ví dụ authorization

~~~text
Verified client certificate:
  principal = svc_report_worker
  tenant = platform-internal

Request:
  action = read_billing_summary
  resource = course-101

Policy:
  allow if principal is svc_report_worker
        and tenant scope matches resource
        and course-101 is assigned to this workload

Result:
  PERMIT read_billing_summary
  DENY issue_refund
~~~

Ví dụ cho thấy certificate giúp xác định caller; policy quyết định caller được làm gì. Không đưa role vào certificate như một quyền vĩnh viễn nếu role có thể thay đổi thường xuyên và cần thu hồi nhanh.

## 10. Client certificate và access token

Một ứng dụng có thể xác thực client bằng mTLS rồi dùng access token cho các API. Cần hiểu token có ràng buộc với certificate hay chỉ là bearer token.

| Kiểu | Cách sử dụng | Rủi ro |
| --- | --- | --- |
| **Bearer token sau mTLS** | Client dùng mTLS khi lấy token; API nhận bearer token | Token bị lấy cắp có thể được dùng từ client khác nếu không có sender constraint |
| **Certificate-bound access token** | Token có confirmation claim gắn với certificate client; API kiểm tra token và certificate trên kênh mTLS | Cần xác minh đúng thumbprint và bảo vệ ranh giới proxy |
| **Session cookie sau client certificate login** | Browser xác thực bằng certificate rồi dùng cookie cho các request tiếp theo | Cookie vẫn có thể bị đánh cắp; certificate ban đầu không bảo vệ session tự động |

Với mô hình certificate-bound token, resource server kiểm tra chữ ký/issuer/audience/exp/scope và đối chiếu certificate thực sự dùng trên kết nối với ràng buộc token (ví dụ thumbprint theo chuẩn áp dụng). Không chỉ tin claim cnf do client gửi. Nếu gateway kết thúc mTLS, cách backend nhận bằng chứng về certificate cần được bảo vệ và thiết kế rõ.

**JWT có chữ ký hợp lệ không có nghĩa token chưa bị đánh cắp.** Nếu token là bearer, người giữ token có thể dùng nó trong phạm vi cho phép. Sender-constrained token giảm rủi ro này nhưng không thay thế bảo vệ private key, kiểm tra authorization và thu hồi.

## 11. Vòng đời client certificate

Certificate credential cần vòng đời được quản lý như một phần của identity lifecycle.

~~~mermaid
stateDiagram-v2
    [*] --> Enrollment: Xác minh subject và quyền xin cấp
    Enrollment --> Issued: CA phát hành
    Issued --> Active: Cài đặt và ánh xạ principal
    Active --> Renewal: Gần hết hạn
    Renewal --> Active: Certificate mới được xác minh và chuyển đổi
    Active --> Revoked: Khóa lộ / thiết bị mất / chấm dứt tin cậy
    Active --> Expired: Hết notAfter
    Active --> Deprovisioned: Chủ thể/workload ngừng hoạt động
    Revoked --> [*]
    Expired --> [*]
    Deprovisioned --> [*]
~~~

### 11.1. Enrollment

1. Xác định chủ thể: user, device, partner hay workload.
2. Xác minh quyền nhận danh tính/SAN theo nguồn có thẩm quyền.
3. Sinh key pair ở nơi sử dụng; private key không cần rời thiết bị nếu dùng CSR.
4. Tạo CSR và gửi tới registration/issuance service.
5. Kiểm tra quyền xin cấp, profile, SAN, EKU, Key Usage và thời hạn.
6. CA ký và trả leaf certificate/chain.
7. Cài đặt certificate và cấu hình trust; kiểm tra kết nối thật trước khi đưa vào sử dụng.
8. Ghi inventory metadata như principal, issuer, serial, fingerprint, ngày hết hạn và trạng thái.

CSR chứng minh người yêu cầu kiểm soát khóa riêng tương ứng với public key trong yêu cầu, nhưng **không tự chứng minh họ được phép nhận SAN**. Enrollment authority phải xác minh quyền cấp danh tính riêng.

### 11.2. Renewal và rotation

Renewal cấp certificate mới trước khi certificate cũ hết hạn. Rotation có thể thay cả cặp khóa. Quy trình cần:

- Cảnh báo trước hạn và có thời gian dự phòng cho lỗi cấp phát;
- Tạo khóa mới khi policy yêu cầu rekey hoặc khóa cũ có rủi ro;
- Kiểm tra certificate mới: chain, SAN, EKU, thời hạn và mapping;
- Chuyển client/server theo giai đoạn, có khoảng overlap kiểm soát;
- Thu hồi/ngừng dùng certificate cũ sau khi chuyển đổi;
- Cập nhật inventory, trust bundle và cảnh báo vận hành.

Không giữ certificate cũ vô thời hạn chỉ để tránh gián đoạn. Khoảng overlap phải có mục đích và ngày kết thúc.

### 11.3. Revocation và deprovisioning

Các cơ chế phổ biến:

- **CRL:** danh sách chứng chỉ bị thu hồi được bên kiểm tra tải/đọc theo chu kỳ;
- **OCSP:** truy vấn trạng thái certificate qua responder;
- **Short-lived certificates:** giảm thời gian credential bị chấp nhận sau khi mất kiểm soát;
- **Application denylist/status check:** chặn principal hoặc certificate cụ thể ở lớp ứng dụng.

Hỗ trợ và hành vi khi OCSP/CRL không truy cập được phụ thuộc TLS stack và cấu hình. Cần quy định fail-open/fail-closed theo rủi ro. Một chứng chỉ bị thu hồi không nhất thiết làm đóng ngay các kết nối TLS đã thiết lập hoặc token đã phát hành. Khi cần thu hồi nhanh, phải phối hợp **TLS connection lifecycle, session/token revocation và application authorization**.

Deprovisioning cần dừng cấp certificate mới, thu hồi/chặn certificate đang dùng, xóa hoặc vô hiệu private key trên thiết bị nếu có thể, cập nhật principal mapping và xử lý quyền/token/phiên liên quan. Chỉ đánh dấu workload inactive trong inventory mà không chặn verifier chưa chắc đã ngăn được truy cập.

## 12. Bảo vệ private key client

Private key là bí mật cần bảo vệ; certificate công khai có thể được gửi qua TLS handshake nhưng private key không được gửi.

Biện pháp:

- Dùng TPM, HSM, smart card, secure enclave hoặc keystore của hệ điều hành khi khả thi;
- Hạn chế quyền tiến trình được phép dùng khóa;
- Không lưu khóa riêng trong source code, container image, log, ticket hoặc kho artifact chia sẻ;
- Không dùng chung khóa giữa môi trường dev/staging/production;
- Có quy trình backup/escrow nếu nghiệp vụ yêu cầu, kèm quyền truy cập và audit nghiêm ngặt;
- Rotate/rekey khi nghi ngờ bị lộ; chỉ đổi certificate nhưng giữ nguyên khóa đã lộ là chưa đủ;
- Kiểm soát thiết bị bị mất, bị jailbreak/root hoặc không còn tuân thủ chính sách.

Một tệp PFX/PKCS#12 có mật khẩu vẫn có thể bị sao chép và giải mã nếu mật khẩu yếu hoặc file bị lộ. Không xem việc đặt password cho file khóa là tương đương với phần cứng bảo vệ private key không xuất được.

## 13. Session resumption và ranh giới xác thực

TLS session resumption giúp giảm chi phí handshake. Tuy nhiên, hệ thống phải hiểu chính sách client authentication khi một kết nối được tiếp tục từ session cũ. Không nên giả định mọi lần resumption đều thực hiện lại đầy đủ client certificate validation và proof như một handshake mới theo cách ứng dụng mong muốn.

Thiết kế cần xem xét:

- TLS library/server xử lý client-auth state khi resumption thế nào;
- Thời hạn session ticket và cách thu hồi/rotate ticket keys;
- Certificate có thể bị thu hồi trong khi TLS session còn được tiếp tục hay không;
- Backend có kiểm tra trạng thái principal/session hiện tại cho hành động nhạy cảm không;
- Khi policy hoặc membership thay đổi, làm thế nào vô hiệu hóa phiên cũ.

Không dùng session resumption để kéo dài quyền của một certificate đã mất hiệu lực hoặc principal đã bị deprovision. Hành vi cụ thể phụ thuộc TLS version, server implementation và cấu hình; phải kiểm thử với stack thực tế.

## 14. Lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Chỉ kiểm tra certificate được ký bởi một CA bất kỳ | Chấp nhận client không có thẩm quyền | Trust store và issuer policy giới hạn |
| Không kiểm tra SAN/danh tính kỳ vọng | Certificate hợp lệ của client khác bị dùng | Kiểm tra đúng SAN type/value và namespace |
| Chấp nhận EKU không phù hợp | Certificate server hoặc mục đích khác được dùng làm client | Kiểm tra clientAuth và Key Usage theo profile |
| Dùng CN làm role | Tên trong certificate biến thành quyền nghiệp vụ | Mapping principal và authorization riêng |
| Một private key dùng chung nhiều service | Một service bị chiếm có thể giả mạo các service khác | Credential riêng cho từng workload |
| Private key nằm trong container image | Mọi nơi có image có thể lấy khóa | Enrollment runtime/secret manager/HSM |
| Tin header client certificate từ Internet | Kẻ tấn công tự khai identity qua header | Gateway xóa/ghi đè header và backend xác thực gateway |
| Backend truy cập được trực tiếp, bỏ qua gateway | Bỏ qua xác thực client ở proxy | Network policy và service authentication |
| Bỏ qua revocation hoặc không theo dõi hạn | Credential mất hiệu lực vẫn được chấp nhận | CRL/OCSP/short TTL/denylist và monitoring |
| Nghĩ mTLS tự cấp quyền API | Client hợp lệ truy cập vượt phạm vi | Authorization theo action/resource/tenant |
| Giữ session/token sau deprovision | Principal đã ngừng hoạt động vẫn truy cập | Session/token revocation và policy check |
| Chỉ pin fingerprint mà không có rotation plan | Thay certificate gây outage hoặc buộc tắt kiểm tra | Pinning có overlap và quy trình cập nhật trust |

## 15. Ví dụ xuyên suốt: workload gọi API nội bộ

Một nền tảng học tập có report-worker gọi billing-api để đọc tổng hợp thanh toán. Cả hai service chạy trong hạ tầng nội bộ. Hệ thống dùng CA nội bộ cấp certificate riêng cho từng workload.

### 15.1. Luồng xác thực

1. Workload identity service xác minh report-worker đang chạy trong môi trường được phép và cấp certificate với URI SAN tương ứng.
2. report-worker giữ private key trong môi trường runtime/keystore; certificate public được cài cùng chain cần thiết.
3. report-worker kết nối tới billing-api qua mTLS; trước tiên xác minh server certificate và DNS SAN của billing-api.
4. billing-api yêu cầu client certificate, kiểm tra trust chain, clientAuth EKU, SAN URI, thời hạn, trạng thái và proof of possession.
5. billing-api ánh xạ SAN URI thành principal svc_report_worker.
6. Authorization policy cho phép read_billing_summary trong tenant và course được phân công; từ chối issue_refund.
7. Khi report-worker bị xóa hoặc nghi lộ khóa, hệ thống ngừng cấp mới, thu hồi/chặn certificate cũ, xử lý phiên/token và audit các request liên quan.

### 15.2. Những câu hỏi cần trả lời

- Ai có quyền xin certificate mang URI SAN của report-worker?
- Có thể tạo một certificate khác với cùng SAN từ CA khác được server tin không?
- Backend có nhận header danh tính từ client trực tiếp không?
- Nếu gateway kết thúc mTLS, backend xác thực gateway như thế nào?
- Nếu certificate bị thu hồi, kết nối hiện hữu và access token cũ bị xử lý ra sao?
- Nếu một container image bị sao chép, private key có bị mang theo không?

Các câu hỏi này xác định liệu certificate authentication có thật sự gắn với một workload được quản lý hay chỉ là một tệp chứng chỉ được chia sẻ.

## 16. Kiểm thử client certificate authentication

Kiểm thử trong môi trường được phép, với CA và client test riêng.

| Nhóm | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| No certificate | Client không trình bày certificate ở endpoint mTLS bắt buộc | Handshake/request bị từ chối |
| Unknown CA | Certificate chain không dẫn tới trust anchor được phép | Từ chối |
| Expired/not yet valid | Certificate ngoài khoảng hiệu lực | Từ chối |
| Wrong SAN | Chain hợp lệ nhưng SAN không phải identity kỳ vọng | Từ chối |
| Wrong EKU/Key Usage | Certificate không phù hợp client authentication | Từ chối |
| Wrong private key | Client không chứng minh được quyền kiểm soát public key trong certificate | Handshake thất bại |
| Revoked certificate | Certificate đã bị thu hồi theo cơ chế/policy đang bật | Từ chối theo chính sách |
| Wrong tenant | Certificate của tenant A yêu cầu resource tenant B | Authentication có thể hợp lệ nhưng authorization phải DENY |
| Shared certificate | Hai service dùng chung identity ngoài policy | Phát hiện/không cho phép theo enrollment policy |
| Forged proxy header | Client tự gửi X-Client-Cert hoặc principal header | Gateway xóa/ghi đè; backend không tin header giả |
| Direct backend access | Client bỏ qua gateway và gọi backend | Bị chặn hoặc yêu cầu xác thực service hợp lệ |
| Deprovision | Workload đã bị xóa nhưng certificate chưa hết hạn | Bị chặn bởi revocation/status/denylist theo yêu cầu |
| Resumption | TLS session được resume sau khi principal bị thu hồi | Hành vi đúng policy; không duy trì quyền trái phép |
| Authorization | Certificate hợp lệ gọi endpoint không có quyền | Trả về deny/403 |

### 16.1. Kiểm tra metadata bằng OpenSSL

Các lệnh dưới đây chỉ giúp xem metadata và kiểm tra sơ bộ chain trong môi trường thử nghiệm. Không in hoặc chia sẻ private key.

~~~bash
# Xem Subject, Issuer, validity và extensions
openssl x509 -in client.crt -noout -text

# Xem SAN và các thông tin cơ bản
openssl x509 -in client.crt -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage

# Kiểm tra leaf theo mục đích TLS client với CA đã chỉ định
openssl verify -purpose sslclient -CAfile root-ca.crt -untrusted intermediate-ca.crt client.crt
~~~

Kết quả OK không chứng minh client đang giữ private key, principal được phép truy cập API hoặc certificate chưa bị thu hồi theo cơ chế trực tuyến. Cần kiểm tra các phần còn lại bằng TLS endpoint và policy thực tế.

### 16.2. Kiểm tra mTLS với endpoint thử nghiệm

~~~bash
openssl s_client \
  -connect api.internal.example:443 \
  -servername api.internal.example \
  -cert client.crt \
  -key client.key \
  -CAfile server-ca.crt \
  -verify_return_error
~~~

Lệnh minh họa kết nối TLS với client certificate. Trong môi trường thực tế cần dùng file thử nghiệm, quyền truy cập khóa phù hợp, kiểm tra hostname server theo công cụ hỗ trợ và xác minh chính sách ở API. Không dùng certificate/khóa production để thử nghiệm tùy tiện.

## 17. Checklist production

1. **Client là ai?** Người, thiết bị, ứng dụng, workload hay đối tác; danh tính được cấp trong namespace nào?
2. **Ai được quyền cấp?** Enrollment xác minh subject và quyền yêu cầu SAN/EKU ra sao?
3. **Trust store:** Server chỉ tin CA/profile nào? Có tách mục đích client và server không?
4. **Chain:** Chữ ký, Basic Constraints, Key Usage, EKU, thời hạn và extension critical được kiểm tra đầy đủ không?
5. **Identity mapping:** SAN/issuer/subject được ánh xạ sang principal nội bộ thế nào? Có ràng buộc tenant không?
6. **Proof of possession:** mTLS handshake được kiểm tra bởi TLS stack chuẩn; private key không gửi qua mạng?
7. **Key protection:** Khóa được giữ trong TPM/HSM/keystore hoặc secret manager phù hợp; không nằm trong image/repository?
8. **TLS termination:** Gateway xóa header giả, backend xác thực gateway và không có đường bypass?
9. **Authorization:** Principal chỉ có quyền action/resource cần thiết; certificate hợp lệ không tự cấp role?
10. **Lifecycle:** Enrollment, renewal, rekey, rotation, revocation và deprovisioning có owner và lịch vận hành?
11. **Session/token:** Resumption, session cookie, refresh/access token được xử lý khi certificate/principal bị thu hồi?
12. **Monitoring:** Có inventory issuer/serial/fingerprint/expiry và cảnh báo certificate sắp hết hạn, lỗi chain, SAN mismatch?
13. **Incident response:** Có playbook khi mất thiết bị, lộ private key, CA compromise hoặc certificate bị cấp sai?
14. **Testing:** Đã kiểm tra certificate sai, header giả, bypass gateway, cross-tenant và quyền không được phép?

## 18. Bài tập tình huống

Một API nội bộ bật mTLS tại gateway. Gateway xác minh certificate client do một CA nội bộ cấp, sau đó gửi X-Client-CN tới backend. Backend tin mọi request có header này. Tất cả workload dùng chung một certificate mang CN internal-service. Certificate có hạn ba năm và private key được đóng gói trong container image. Khi một service bị xóa, không có quy trình thu hồi certificate hoặc token đã phát hành.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** trong xác thực client, ánh xạ principal và vòng đời credential.
2. Thiết kế lại trust boundary giữa client, gateway và backend.
3. Chọn SAN/namespace và quy tắc mapping cho từng workload.
4. Đề xuất bảo vệ private key và cấp certificate tự động mà không nhúng khóa vào image.
5. Thiết kế deprovisioning có tác động tới certificate, TLS session, session/token và quyền API.
6. Viết test cho header giả, client không có certificate, SAN sai, certificate hết hạn và workload hợp lệ gọi endpoint không có quyền.

**Gợi ý đối chiếu:** backend chỉ tin gateway được xác thực; gateway xóa header client gửi; mỗi workload có identity/certificate riêng; SAN được cấp qua enrollment authority; private key được giữ ở runtime/keystore; policy tách authentication và authorization; revocation/denylist/TTL và token revocation phải có hành vi được kiểm thử.

## 19. Ghi nhớ

- **Client certificate** là chứng chỉ X.509 mà client trình bày để server xác thực; client phải chứng minh giữ private key trong TLS handshake.
- mTLS xác thực hai phía ở lớp truyền tải. Kiểm tra chain thôi chưa đủ: cần kiểm tra **SAN/danh tính kỳ vọng, EKU, thời hạn, trạng thái và trust policy**.
- Certificate hợp lệ chỉ xác định principal theo quy tắc cấp phát. **Authorization** vẫn phải kiểm tra action, resource, tenant và trạng thái hiện thời.
- Khi TLS kết thúc ở gateway, backend chỉ tin danh tính chuyển tiếp nếu gateway được xác thực, header giả đã bị xóa và không có đường bypass.
- Private key cần được bảo vệ, tách theo workload và có vòng đời enrollment, renewal, rotation, revocation, deprovisioning.
- Certificate, TLS session, access token và session cookie có vòng đời khác nhau; thu hồi một thành phần không tự động thu hồi mọi thành phần còn lại.

Client certificate trở thành một cơ chế xác thực đáng tin khi tổ chức kiểm soát được **ai được cấp danh tính, khóa riêng được bảo vệ ra sao, server xác minh client nào, principal được phép làm gì và quyền bị chấm dứt như thế nào**.
