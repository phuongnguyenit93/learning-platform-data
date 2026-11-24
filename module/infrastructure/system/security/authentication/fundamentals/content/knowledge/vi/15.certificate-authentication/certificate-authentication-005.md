# Certificate validation

## 1. Certificate validation là gì?

**Certificate validation** là quá trình kiểm tra một chứng chỉ số có thể được tin cậy cho **mục đích và danh tính cụ thể** hay không. Trong PKI (Public Key Infrastructure), chứng chỉ X.509 thường liên kết một public key với subject hoặc các định danh như DNS name, URI, email hay danh tính dịch vụ. Chữ ký số của CA bảo vệ tính toàn vẹn của chứng chỉ và xác nhận CA đã phát hành nó; tuy nhiên, chữ ký hợp lệ **không tự động chứng minh chứng chỉ phù hợp với mọi kết nối hoặc mọi hành động**.

Bên xác minh cần trả lời các câu hỏi:

- Chứng chỉ có nối được tới một **trust anchor** mà hệ thống chấp nhận không?
- Chữ ký của từng CA trong chuỗi có hợp lệ và các ràng buộc CA có được tuân thủ không?
- Chứng chỉ hiện tại có trong thời hạn hiệu lực, chưa bị thu hồi theo chính sách và dùng đúng mục đích không?
- Danh tính trong chứng chỉ có khớp với **đối tượng mà client định kết nối** không?
- Public key có được dùng trong đúng giao thức, thuật toán và ngữ cảnh không?
- Nếu chứng chỉ xác thực client/service, danh tính được xác minh có được ánh xạ tới principal và quyền phù hợp không?

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, certificate validation kết nối danh tính số, chứng chỉ, khóa riêng, TLS/mTLS, credential, session và authorization. Người học cần phân biệt kiểm tra chuỗi tin cậy với kiểm tra tên máy chủ, kiểm tra chứng chỉ với proof of possession, và xác thực với cấp quyền.

## 2. X.509 và các thành phần trong PKI

Một chứng chỉ X.509 v3 thường chứa các thông tin chính:

| Trường/extension | Ý nghĩa | Vì sao bên xác minh cần quan tâm |
| --- | --- | --- |
| **Subject** | Chủ thể được mô tả trong chứng chỉ | Có thể chứa tên X.500; không phải lúc nào cũng là định danh dùng để kiểm tra hostname |
| **Subject Alternative Name (SAN)** | Các tên/định danh thay thế như DNS, IP, URI, email | Thường là nơi kiểm tra hostname hoặc service identity |
| **Issuer** | CA đã ký/phát hành chứng chỉ | Xác định issuer cần được kiểm chứng trong chuỗi |
| **Serial Number** | Số sê-ri do issuer gán | Kết hợp với issuer để định danh chứng chỉ, ví dụ khi tra cứu thu hồi |
| **Validity (Not Before/Not After)** | Khoảng thời gian chứng chỉ có hiệu lực | Chứng chỉ ngoài thời hạn không được chấp nhận theo quy tắc thông thường |
| **Subject Public Key Info** | Thuật toán và public key | Dùng để xác minh chữ ký hoặc thiết lập khóa theo giao thức |
| **Signature Algorithm / Signature** | Thuật toán và chữ ký của issuer | Kiểm tra tính toàn vẹn và chữ ký phát hành |
| **Basic Constraints** | Xác định CA hay end-entity và giới hạn path length nếu có | Ngăn chứng chỉ máy chủ/người dùng tự đóng vai CA |
| **Key Usage (KU)** | Các mục đích sử dụng khóa được phép | Ví dụ digitalSignature, keyCertSign, cRLSign |
| **Extended Key Usage (EKU)** | Mục đích sử dụng mở rộng | Ví dụ serverAuth, clientAuth, codeSigning |
| **Certificate Policies** | OID chính sách áp dụng | Có thể cần kiểm tra trong PKI có yêu cầu policy cụ thể |
| **CRL Distribution Points / AIA** | Tham chiếu CRL, OCSP hoặc issuer certificate | Hỗ trợ xây dựng đường dẫn và kiểm tra trạng thái, tùy chính sách |

Các trường và extension phải được diễn giải theo tiêu chuẩn và profile chứng chỉ áp dụng. Không phải extension nào cũng bắt buộc có trong mọi loại chứng chỉ; việc thiếu hoặc có giá trị khác nhau có thể dẫn tới kết quả khác theo mục đích sử dụng.

### 2.1. CA, intermediate và trust anchor

PKI thường có cấu trúc phân cấp:

~~~mermaid
flowchart TD
    R[Root CA / Trust Anchor] --> I[Intermediate CA]
    I --> L[Leaf certificate: server / client / service]
    L --> K[Public key được dùng trong giao thức]
~~~

- **Root CA:** thường là trust anchor được cài đặt hoặc cấu hình riêng trong trust store. Root có thể tự ký, nhưng độ tin cậy không đến từ việc tự ký; nó đến từ việc bên xác minh đã chọn và tin root đó.
- **Intermediate CA:** chứng chỉ CA được CA cấp trên ký, dùng để phát hành chứng chỉ phía dưới. Có thể có nhiều intermediate.
- **Leaf/end-entity certificate:** chứng chỉ cuối dành cho máy chủ, client, người dùng, thiết bị hoặc workload; thông thường không được phép ký chứng chỉ khác.

Trust anchor là đầu vào chính sách của quá trình path validation. Một chứng chỉ có chữ ký hợp lệ từ một CA không nằm trong trust store thích hợp không tự trở thành đáng tin cậy.

## 3. Chain building và path validation

Hai việc thường đi cùng nhau nhưng không giống nhau:

- **Path building:** tìm một chuỗi chứng chỉ có thể nối từ leaf qua các intermediate tới trust anchor phù hợp. Chứng chỉ intermediate có thể đến từ server, local store hoặc nguồn được hệ thống cấu hình.
- **Path validation:** kiểm tra chuỗi đã chọn có thỏa các quy tắc tin cậy và chính sách hay không.

Một chuỗi có thể được xây dựng thành công nhưng validation vẫn thất bại vì chữ ký sai, hết hạn, CA constraint không hợp lệ, thuật toán không được phép, sai mục đích sử dụng hoặc không đáp ứng policy.

~~~mermaid
flowchart TD
    A[Leaf certificate] --> B[Build candidate chain]
    B --> C{Có đường tới trust anchor?}
    C -- Không --> X[Reject: untrusted / incomplete path]
    C -- Có --> D[Verify signatures và issuer links]
    D --> E[Check validity, constraints, policies]
    E --> F[Check KU/EKU và purpose]
    F --> G[Check revocation theo policy]
    G --> H[Check expected identity: SAN/hostname]
    H --> I{Tất cả điều kiện đạt?}
    I -- Không --> X
    I -- Có --> Y[Certificate hợp lệ cho mục đích cụ thể]
~~~

Sơ đồ thể hiện các nhóm kiểm tra ở mức khái niệm; thứ tự và cách triển khai cụ thể phụ thuộc thư viện, giao thức và profile. **Hostname verification** là kiểm tra danh tính bên kết nối, thường cần thực hiện cùng quá trình xác minh chứng chỉ máy chủ. Không được xem chỉ riêng path validation thành công là đủ để tin server đang kết nối đúng tên.

### 3.1. Chữ ký và issuer relationship

Với mỗi certificate phía dưới, verifier kiểm tra chữ ký bằng public key của issuer tương ứng. Đồng thời phải kiểm tra issuer/subject relationship, các ràng buộc CA và quy tắc path. Không được chỉ đọc trường Issuer rồi tin chuỗi tên đó; trường tên không phải chữ ký.

Chứng chỉ leaf thường phải có Basic Constraints thể hiện không phải CA. CA certificate cần đáp ứng CA:TRUE và các yêu cầu Key Usage như keyCertSign khi profile yêu cầu. Nếu CA có pathLenConstraint, chuỗi không được vượt quá giới hạn intermediate CA được phép.

### 3.2. Trust store và trust anchor

Trust store là cấu hình chứa hoặc tham chiếu các trust anchor mà ứng dụng chấp nhận. Hệ điều hành, runtime, trình duyệt, Java keystore, container image và ứng dụng riêng có thể sử dụng trust store khác nhau.

Các câu hỏi vận hành:

- Root nào được tin và ai phê duyệt việc thêm/bỏ?
- Ứng dụng dùng trust store hệ điều hành, runtime hay trust store riêng?
- Khi CA bị compromise, làm thế nào phân phối cập nhật trust?
- Có môi trường test/dev vô tình tin CA không phù hợp trong production không?
- Có cấu hình trust rộng hơn mức cần thiết cho tenant/service không?

Không nên thêm một CA vào trust store chỉ để “hết lỗi chứng chỉ” mà không hiểu CA đó phát hành cho ai, ai kiểm soát private key và phạm vi trust được cấp.

## 4. Kiểm tra danh tính server: SAN và hostname

Khi client kết nối HTTPS tới api.example.test, nó cần xác minh chứng chỉ phù hợp với **tên server mà client dự định kết nối**. Chữ ký chain có thể hợp lệ nhưng chứng chỉ lại được cấp cho một tên khác.

Quy tắc thực hành hiện đại là kiểm tra tên DNS/IP theo **Subject Alternative Name (SAN)** phù hợp với kiểu định danh. Không dựa vào Common Name (CN) như một fallback tùy tiện nếu SAN không khớp.

| Địa chỉ client truy cập | Kiểu SAN cần kiểm tra |
| --- | --- |
| https://api.example.test | dNSName: api.example.test |
| https://192.0.2.10 | iPAddress: 192.0.2.10 |
| Một service identity URI trong hệ thống workload | uniformResourceIdentifier theo profile đã thống nhất |

Tên DNS và IP không phải cùng kiểu. Một chuỗi IP đặt trong dNSName không tương đương iPAddress SAN. Nếu client kết nối bằng IP literal, verifier cần kiểm tra IP SAN tương ứng.

### 4.1. Wildcard

Wildcard certificate có thể phù hợp một số tên con theo quy tắc hostname matching, nhưng không nên tự viết logic wildcard. Ví dụ *.example.test thường khớp api.example.test nhưng không khớp v1.api.example.test hoặc example.test. Hãy dùng verifier của TLS stack đáng tin cậy và tuân thủ quy tắc hostname hiện hành.

### 4.2. SNI không phải xác minh danh tính

**Server Name Indication (SNI)** cho phép client gửi tên server mong muốn trong TLS ClientHello để server chọn chứng chỉ phù hợp. SNI giúp chọn đúng virtual host/certificate; nó không thay thế việc client xác minh SAN và chain sau khi nhận certificate.

Một server có thể trả chứng chỉ dựa trên SNI, nhưng client vẫn phải kiểm tra chứng chỉ đó khớp hostname dự định.

## 5. Validity, thuật toán và ràng buộc mục đích

### 5.1. Thời hạn hiệu lực

Verifier kiểm tra thời điểm hiện tại nằm trong khoảng Not Before và Not After, có xét xử lý clock skew theo giao thức/chính sách. Đồng hồ hệ thống sai có thể gây lỗi chứng chỉ hợp lệ hoặc vô tình chấp nhận chứng chỉ ngoài hạn nếu logic tùy chỉnh yếu.

Chứng chỉ còn hạn không có nghĩa khóa chưa bị lộ hoặc chứng chỉ chưa bị thu hồi. Validity và revocation là hai kiểm tra riêng.

### 5.2. Key Usage và Extended Key Usage

**Key Usage** giới hạn loại thao tác mật mã được phép với khóa. **Extended Key Usage** mô tả mục đích sử dụng rộng hơn, chẳng hạn TLS server authentication hoặc client authentication. Verifier cần áp dụng profile đúng cho mục đích cụ thể; không nên chấp nhận một chứng chỉ chỉ vì chữ ký chain hợp lệ nếu EKU/KU không phù hợp.

Ví dụ:

- Chứng chỉ server TLS thường cần mục đích serverAuth theo profile.
- Chứng chỉ client TLS có thể cần clientAuth.
- CA certificate cần quyền ký chứng chỉ phù hợp, không phải chỉ có public key hợp lệ.
- Chứng chỉ ký code không tự phù hợp cho xác thực client TLS.

### 5.3. Thuật toán và kích thước khóa

Chính sách cần loại bỏ thuật toán yếu hoặc cấu hình không còn được chấp nhận. Verifier phải kiểm tra thuật toán chữ ký và loại khóa phù hợp với policy; không tự chấp nhận mọi thuật toán mà thư viện hỗ trợ.

Đừng viết kiểm tra chuỗi tên thuật toán thủ công rồi giả định đã bao quát mọi encoding/parameter. Dùng thư viện PKI/TLS cập nhật và cấu hình rõ danh sách thuật toán/curve/chính sách tương ứng.

### 5.4. Name Constraints và Certificate Policies

CA có thể bị giới hạn về namespace hoặc policy. **Name Constraints** có thể giới hạn DNS name, IP range, URI hoặc namespace khác mà CA được phép cấp. **Certificate Policies** có thể biểu thị policy OID mà relying party cần kiểm tra trong một PKI chuyên biệt.

Nếu ứng dụng bỏ qua constraint hoặc tự xây path validation không đầy đủ, chứng chỉ có thể được chấp nhận ngoài phạm vi CA được phép. Trong môi trường có yêu cầu tuân thủ, cần định nghĩa rõ policy OID, trust anchor, path length, name constraints và cách xử lý extension critical.

## 6. Revocation: CRL, OCSP và trạng thái chứng chỉ

Một certificate có thể bị thu hồi trước ngày hết hạn do private key bị lộ, thông tin sai, thiết bị bị mất, nhân viên rời tổ chức hoặc CA phát hành nhầm. Bên xác minh cần áp dụng chính sách revocation phù hợp.

| Cơ chế | Cách hoạt động | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **CRL (Certificate Revocation List)** | CA ký danh sách serial number đã thu hồi, phát hành theo chu kỳ | Có thể tải và cache để kiểm tra nhiều chứng chỉ | Danh sách có thể lớn hoặc chậm cập nhật; cần kiểm tra chữ ký và thời gian CRL |
| **OCSP (Online Certificate Status Protocol)** | Client hỏi responder về trạng thái của một certificate | Có thể lấy trạng thái gần thời điểm sử dụng hơn | Phụ thuộc mạng/responder; privacy, availability và caching |
| **OCSP stapling** | TLS server gửi OCSP response được CA/responder ký kèm handshake | Giảm truy vấn trực tiếp từ client và giảm lộ thông tin truy cập | Phải kiểm tra response, thời hạn, chữ ký và xử lý khi thiếu/hết hạn theo policy |
| **Short-lived certificates** | Chứng chỉ có thời hạn ngắn để giảm cửa sổ sử dụng | Giảm phụ thuộc vào revocation trong một số hệ thống | Cần tự động cấp mới, thu hồi/rotation và xử lý sự cố nhanh |

### 6.1. Good, revoked, unknown

OCSP có thể trả các trạng thái như good, revoked, unknown. Không nên diễn giải good như một lời khẳng định tuyệt đối rằng chứng chỉ chưa từng bị compromise; đó là trạng thái mà responder báo tại thời điểm và theo dữ liệu nó quản lý.

unknown không đồng nghĩa good. Hệ thống phải có chính sách rõ khi không xác định được trạng thái. Tùy mức rủi ro, hệ thống có thể fail closed (từ chối) hoặc dùng quyết định có kiểm soát; không được âm thầm bỏ qua kiểm tra ở mọi trường hợp.

### 6.2. Soft-fail và hard-fail

- **Hard-fail:** nếu không kiểm tra được trạng thái thu hồi theo yêu cầu thì từ chối kết nối.
- **Soft-fail:** trong một số cấu hình, nếu dịch vụ revocation không truy cập được thì vẫn tiếp tục theo policy.

Không có quy tắc “soft-fail luôn đúng” hoặc “hard-fail luôn đúng”. Máy chủ thanh toán, control plane hoặc hệ thống đặc quyền có thể cần chính sách chặt hơn dịch vụ ít rủi ro. Quyết định phải xét availability, khả năng tấn công bằng cách làm nghẽn responder, thời gian cache, độ ngắn của certificate và yêu cầu tuân thủ.

## 7. TLS server authentication và mutual TLS

### 7.1. TLS server authentication

Trong HTTPS thông thường:

1. Client kết nối tới hostname/IP và bắt đầu TLS handshake.
2. Server gửi certificate chain.
3. Client xây path và xác minh chain tới trust anchor.
4. Client kiểm tra thời hạn, mục đích, thuật toán, revocation theo policy và tên server trong SAN.
5. TLS handshake xác minh server giữ private key tương ứng với chứng chỉ thông qua chữ ký hoặc cơ chế handshake phù hợp phiên bản TLS.
6. Hai bên thiết lập kênh mã hóa.

**Certificate validation và proof of possession** phối hợp với nhau. Một file certificate bị sao chép không đủ để server hoàn tất handshake như chủ sở hữu private key nếu private key không bị lộ.

### 7.2. Mutual TLS (mTLS)

Trong mTLS, server cũng yêu cầu client gửi certificate. Server xác minh chain và các thuộc tính của client certificate, đồng thời TLS handshake chứng minh client kiểm soát private key tương ứng.

~~~mermaid
sequenceDiagram
    participant C as Client / Workload
    participant S as Server / API Gateway
    C->>S: ClientHello
    S-->>C: Server certificate chain
    C->>C: Validate server chain + SAN/hostname
    C->>S: Client certificate request
    C->>S: Client certificate + proof of private key
    S->>S: Validate client chain, EKU, identity, revocation
    S-->>C: TLS handshake complete
    C->>S: API request over mTLS
    S->>S: Map certificate identity to principal
    S->>S: Authorization by resource/action
~~~

mTLS phù hợp service-to-service, workload identity, thiết bị quản lý hoặc client doanh nghiệp. Nhưng cần nhớ:

- Chứng chỉ client xác định danh tính theo PKI và profile đã cấu hình; không tự chứng minh một con người đang ngồi trước thiết bị.
- Server phải ánh xạ certificate identity (ví dụ SAN URI/DNS hoặc subject theo profile) tới principal được phép.
- Certificate hợp lệ không cấp quyền truy cập mọi API; authorization vẫn riêng.
- Cần quản lý cấp phát, rotation, thu hồi, private key, trust store và offboarding.
- Nếu TLS kết thúc ở gateway, backend phải nhận danh tính qua kênh nội bộ được chứng thực; không tin header do client bên ngoài tự gửi.

## 8. Xác thực certificate không giống xác thực danh tính pháp lý

Certificate xác nhận rằng issuer đã liên kết public key với một số thông tin subject/SAN theo profile. Mức độ proofing danh tính phụ thuộc CA, loại certificate và chính sách cấp phát.

| Loại chứng chỉ | Điều có thể chứng minh | Không nên suy diễn |
| --- | --- | --- |
| Domain-validated TLS | CA xác nhận người yêu cầu kiểm soát domain theo phương thức validation của CA | Danh tính pháp lý của tổ chức sở hữu domain |
| Organization-validated TLS | Một số thông tin tổ chức được CA kiểm tra theo profile | Người vận hành kết nối là đúng nhân viên được ủy quyền |
| Client certificate nội bộ | Thiết bị/workload hoặc danh tính nội bộ được CA tổ chức cấp | Có quyền gọi mọi API trong hệ thống |
| User certificate theo PKI | Danh tính/thuộc tính người dùng được xác minh theo quy trình cấp | User đã thực hiện MFA gần đây hoặc session còn an toàn |
| Code-signing certificate | Khóa được CA chứng nhận cho mục đích ký mã theo profile | Mã đã an toàn hoặc không chứa malware |

Đừng lấy Subject CN hoặc email trong certificate làm principal mà không có profile và quy tắc mapping được kiểm soát. Một tên hiển thị có thể trùng; SAN URI/DNS hoặc identifier ổn định theo PKI nội bộ thường thích hợp hơn khi được chuẩn hóa.

## 9. Ranh giới tin cậy và ánh xạ principal

Một quy trình certificate authentication có các bên tin cậy khác nhau:

1. **CA/issuer:** chịu trách nhiệm phát hành theo chính sách.
2. **Trust store owner:** quyết định CA nào được tin.
3. **TLS stack/verifier:** kiểm tra chain, purpose, thời hạn, tên và trạng thái.
4. **Application:** ánh xạ identity đã xác minh thành principal nội bộ.
5. **Authorization service:** quyết định principal có quyền với resource/action hay không.

~~~mermaid
flowchart TD
    A[Certificate từ peer] --> B[TLS / PKI verifier]
    B --> C{Path + name + purpose + status hợp lệ?}
    C -- Không --> X[Reject handshake/request]
    C -- Có --> D[Verified certificate identity]
    D --> E[Map identity to principal]
    E --> F[Authorization policy]
    F --> G{Có quyền?}
    G -- Không --> H[403 / deny]
    G -- Có --> I[Thực hiện hành động]
~~~

Việc xác minh chứng chỉ thường diễn ra ở TLS layer; application nhận được thông tin peer đã được TLS stack xác minh. Tuy nhiên, cần biết **TLS stack đang dùng trust store và policy nào**, certificate identity được chuyển sang application ra sao, và proxy/gateway có thể bị bỏ qua hay không.

Nếu gateway thêm header X-Client-Cert-Subject, backend chỉ được tin header đó khi:
- Chỉ gateway được phép kết nối tới backend.
- Gateway loại bỏ header cùng tên do client gửi và tự tạo giá trị mới.
- Kết nối gateway–backend được bảo vệ và chứng thực phù hợp.
- Backend xác minh danh tính đã chuyển tiếp theo một hợp đồng nội bộ rõ ràng.
- Quyền vẫn được kiểm tra ở backend theo principal/resource/action.

## 10. Cấu hình client/server và các lỗi phổ biến

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Tắt certificate verification để sửa lỗi TLS | Chấp nhận server giả mạo hoặc MITM | Sửa trust store, chain hoặc hostname; không tắt verification trong production |
| Chỉ kiểm tra chữ ký chain | Chấp nhận chứng chỉ đúng CA nhưng sai hostname | Kiểm tra SAN/hostname cùng path validation |
| Tin CN thay SAN tùy tiện | Nhận dạng hostname sai hoặc khác kỳ vọng | Dùng hostname verifier hiện hành theo SAN |
| Trust mọi CA trong môi trường production | Mở rộng miền tin cậy quá mức | Trust store tối thiểu, quản lý thay đổi và audit |
| Không kiểm tra EKU/KU | Dùng certificate sai mục đích | Áp dụng certificate purpose/profile đúng |
| Không xử lý revocation | Tiếp tục tin khóa/chứng chỉ đã bị thu hồi | CRL/OCSP hoặc short-lived certificate theo policy |
| Soft-fail mọi lỗi OCSP/CRL | Đối thủ có thể gây lỗi kiểm tra để né revocation | Quy định fail behavior theo rủi ro và ghi nhận sự cố |
| Chấp nhận self-signed không kiểm soát | Bất kỳ peer nào cũng có thể tự tạo identity | Chỉ pin/trust certificate cụ thể qua quy trình quản lý rõ ràng nếu dùng |
| Map CN/email thành role | Identity collision hoặc nâng quyền | Mapping ổn định, allowlist và authorization riêng |
| Tin header certificate từ client | Giả mạo danh tính qua proxy | Gateway strip/overwrite, chứng thực kết nối nội bộ |
| Không rotate key/certificate | Khóa cũ bị dùng lâu, khó ứng phó lộ khóa | Tự động hóa issuance, renewal, rotation và revoke |
| Chỉ test happy path | Lỗi ở chain thiếu, cert hết hạn hoặc sai mục đích không được phát hiện | Test đầy đủ trường hợp thành công và thất bại |

### 10.1. Không tắt xác minh TLS trong production

Các cấu hình như rejectUnauthorized=false, trust-all manager hoặc callback luôn trả về true có thể làm mất kiểm tra danh tính server. Khi gặp lỗi certificate, cần tìm nguyên nhân thực: CA chain thiếu, trust store sai, hostname không khớp, đồng hồ hệ thống sai, certificate hết hạn hoặc proxy TLS inspection.

Nếu môi trường phát triển cần CA nội bộ, cài đặt CA test có kiểm soát vào trust store riêng của môi trường đó. Không dùng cách tắt verification để “cho chạy được”.

## 11. Ví dụ kiểm tra certificate trong vận hành

Các lệnh sau là ví dụ chẩn đoán; cú pháp và đầu ra có thể khác theo phiên bản OpenSSL và hệ điều hành.

### 11.1. Xem thông tin certificate

~~~bash
openssl x509 -in server.crt -noout -subject -issuer -dates -serial -ext subjectAltName -ext keyUsage -ext extendedKeyUsage
~~~

Lệnh giúp xem các trường quan trọng, nhưng **không tự chứng minh certificate được tin cậy**. Cần kiểm tra chain và mục đích riêng.

### 11.2. Kiểm tra chain và hostname

~~~bash
openssl verify -CAfile trusted-roots.pem -untrusted intermediates.pem -purpose sslserver -verify_hostname api.example.test server.crt
~~~

Lệnh minh họa xác minh path với trust root được chỉ định, intermediate cung cấp và mục đích server TLS, kèm hostname. Cần chọn file trust/intermediate đúng và kiểm tra tùy chọn theo phiên bản OpenSSL.

### 11.3. Quan sát handshake TLS

~~~bash
openssl s_client -connect api.example.test:443 -servername api.example.test -showcerts -verify_return_error -verify_hostname api.example.test
~~~

SNI gửi tên server để server chọn certificate; verify_hostname yêu cầu kiểm tra tên; verify_return_error giúp trả lỗi xác minh thay vì chỉ in cảnh báo trong một số trường hợp. Cần đảm bảo trust store được cấu hình đúng cho môi trường kiểm thử.

Các lệnh này phục vụ **chẩn đoán và xác minh**, không nên nhúng vào production application thay cho TLS library. Ứng dụng nên dùng API TLS/PKI được duy trì và cấu hình xác minh rõ ràng.

## 12. Quy trình cấp phát, rotation và thu hồi

Certificate authentication chỉ an toàn khi vòng đời PKI được vận hành:

1. **Identity proofing/enrollment:** xác minh chủ thể hoặc workload được phép nhận certificate.
2. **Key generation:** tạo private key tại nơi phù hợp; ưu tiên giữ khóa trong HSM/TPM/secure enclave hoặc kho khóa bảo vệ khi yêu cầu.
3. **CSR và issuance:** tạo Certificate Signing Request, CA kiểm tra yêu cầu và phát hành certificate theo profile.
4. **Distribution:** phân phối certificate/public chain tới đúng workload; không gửi private key qua kênh không bảo vệ.
5. **Validation/use:** verifier kiểm tra chain, identity, purpose, thời hạn và revocation theo policy.
6. **Renewal/rotation:** cấp certificate mới trước khi hết hạn, thay key khi policy yêu cầu và cập nhật service không gây downtime.
7. **Revocation:** khi khóa bị lộ, thiết bị mất hoặc identity không còn hợp lệ, thu hồi certificate và xử lý cache/session liên quan.
8. **Offboarding:** khi service hoặc nhân viên rời hệ thống, thu hồi identity và credential tương ứng, xóa quyền truy cập và audit.

Nên tự động hóa issuance/renewal ở quy mô lớn, nhưng hệ thống tự động phải được bảo vệ: CA signing key, workload identity bootstrap, quyền tạo CSR và policy issuance đều là tài sản trọng yếu.

### 12.1. Rotation không chỉ là thay file certificate

Nếu server đổi certificate nhưng private key cũ vẫn bị lưu ở nhiều nơi, rotation chưa hoàn tất. Cần xác định mọi bản sao khóa, service dùng credential, cache, client trust và thời điểm revoke. Với mTLS, cả hai phía phải có kế hoạch overlap để cập nhật certificate mới mà không làm gián đoạn kết nối.

## 13. Checklist review certificate validation

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Trust anchor được chọn ở đâu? | Trust store có quản trị, không trust mọi CA |
| Chain có được xây và validate đúng? | Chữ ký, issuer link, CA constraints, path length và policy được kiểm tra |
| SAN/hostname có khớp? | Kiểm tra DNS/IP đúng kiểu, không fallback tùy tiện |
| Thời hạn có hợp lệ? | NotBefore/NotAfter và clock được xử lý |
| KU/EKU có phù hợp? | Certificate purpose được xác minh theo giao thức |
| Thuật toán và key size có được kiểm soát? | Policy loại bỏ cấu hình yếu, thư viện cập nhật |
| Revocation được xử lý ra sao? | CRL/OCSP/short-lived theo policy; unknown/unavailable có quyết định rõ |
| Có proof of possession? | TLS handshake hoặc giao thức chứng minh peer giữ private key |
| Identity được map thế nào? | Subject/SAN ổn định, đúng tenant và principal |
| Authorization có tách biệt? | Certificate hợp lệ không tự cấp quyền; policy xét resource/action |
| Proxy có chuyển identity an toàn? | Strip header client, chứng thực gateway/backend |
| Vòng đời certificate được quản lý? | Issuance, renewal, rotation, revoke và offboarding |
| Có test negative cases? | Sai hostname, chain thiếu, expired, revoked, wrong EKU, bad signature |
| TLS verification có bị tắt? | Không có trust-all hoặc bỏ qua kiểm tra trong production |

### Tình huống tự kiểm tra

**Tình huống 1:** Certificate có chữ ký hợp lệ từ CA được tin nhưng SAN là other.example.test, trong khi client kết nối api.example.test. Có chấp nhận không?

**Trả lời:** Không. Path hợp lệ không thay thế hostname verification. Danh tính trong SAN phải khớp tên mà client định kết nối.

**Tình huống 2:** Certificate còn hạn nhưng OCSP trả revoked. Có được dùng tiếp vì NotAfter chưa tới không?

**Trả lời:** Không theo chính sách revocation thông thường. Revoked là trạng thái riêng với validity period và cần xử lý từ chối/thu hồi tương ứng.

**Tình huống 3:** mTLS xác minh certificate của workload inventory-reader. Có được mặc định workload này được gọi mọi API không?

**Trả lời:** Không. Certificate xác minh danh tính theo PKI; authorization vẫn phải kiểm tra quyền của principal trên resource/action.

**Tình huống 4:** Ứng dụng gặp lỗi chain thiếu intermediate và tạm tắt TLS verification để tiếp tục. Có phải cách xử lý đúng không?

**Trả lời:** Không. Cần cung cấp intermediate/trust chain phù hợp hoặc sửa cấu hình trust store; tắt verification làm mất khả năng chống giả mạo server.

**Tình huống 5:** OCSP responder không truy cập được. Có nên luôn chấp nhận certificate không?

**Trả lời:** Không có đáp án chung. Cần chính sách soft-fail/hard-fail theo rủi ro, loại dịch vụ, TTL certificate, cache và yêu cầu tuân thủ; không âm thầm bỏ qua.

## 14. Ghi nhớ

**Certificate validation là đánh giá chứng chỉ có đáng tin cho một mục đích và một danh tính cụ thể hay không.** Việc này cần chain tới trust anchor, xác minh chữ ký và CA constraints, thời hạn, thuật toán, KU/EKU, revocation và danh tính SAN/hostname. Chữ ký hợp lệ hoặc certificate còn hạn riêng lẻ đều chưa đủ.

Trong TLS/mTLS, certificate validation phối hợp với **proof of possession private key** để xác thực peer. Sau đó ứng dụng vẫn cần ánh xạ identity đã xác minh sang principal và kiểm tra authorization. Hãy quản lý toàn bộ vòng đời issuance, trust store, renewal, rotation, revoke và offboarding; tuyệt đối không tắt xác minh certificate trong production chỉ để vượt qua lỗi kết nối.
