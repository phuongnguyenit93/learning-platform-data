# OCSP, CRL và kiểm tra trạng thái chứng thư

**OCSP (Online Certificate Status Protocol)** và **CRL (Certificate Revocation List)** là hai cơ chế chủ yếu trong hạ tầng khóa công khai (**Public Key Infrastructure – PKI**) dùng để kiểm tra một chứng thư số có bị **thu hồi (revoked)** trước thời điểm hết hạn hay không. Chúng giúp bên xác minh đánh giá xem CA hoặc bên có thẩm quyền về trạng thái chứng thư có còn chấp nhận chứng thư đó được sử dụng theo chính sách hay không.

Chứng thư X.509 có khoảng hiệu lực từ **Not Before** đến **Not After**, nhưng một chứng thư đang trong khoảng đó **không mặc nhiên còn đáng tin**. Ví dụ, private key của một máy chủ bị lộ, một thiết bị nghỉ hoạt động hoặc CA phát hiện cấp chứng thư sai: tổ chức có thể cần tuyên bố chứng thư **không còn được sử dụng** trước khi đến ngày hết hạn. Đây là bài toán của **certificate revocation**.

Trong chương **PKI và chứng thư cho mạng** thuộc module **SECURITY_NETWORK_SECURITY**, kiểm tra trạng thái chứng thư là một lớp bảo vệ quan trọng cho **TLS/HTTPS, API, mTLS, VPN, Wi-Fi Enterprise/802.1X, thiết bị mạng, DNS mã hóa, workload cloud** và các dịch vụ phải xác minh danh tính qua chứng thư. Tuy nhiên, **OCSP/CRL không thay thế** kiểm tra chữ ký của chuỗi CA, hostname/SAN, EKU, phân quyền người dùng, firewall hay giám sát xâm nhập.

> **Nguyên tắc quan trọng:** Một câu trả lời OCSP **good** hoặc một chứng thư **không có trong CRL** chỉ cung cấp thông tin trạng thái thu hồi **theo nguồn, phạm vi và thời điểm được xác minh**. Nó không tự chứng minh chứng thư được cấp đúng tên, còn private key an toàn hoặc dịch vụ phía sau không độc hại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt chứng thư **hợp lệ về thời gian**, **được tin theo chuỗi PKI**, **đúng danh tính** và **chưa bị thu hồi**.
2. Giải thích khi nào và vì sao CA thực hiện revocation, các thông tin như serial number, issuer và lý do thu hồi.
3. Mô tả CRL, CRL Distribution Point, thisUpdate/nextUpdate, full CRL, delta CRL và cách client đánh giá danh sách.
4. Mô tả yêu cầu/phản hồi OCSP, CertID, các trạng thái **good/revoked/unknown**, chữ ký responder và kiểm tra độ mới.
5. Giải thích **OCSP stapling**, giới hạn của TLS Feature/Must-Staple và sự khác biệt giữa TLS 1.2 và TLS 1.3.
6. Phân tích ưu/nhược điểm về độ trễ, cache, tính riêng tư, khả dụng và chi phí vận hành giữa OCSP và CRL.
7. Phân biệt **soft-fail** và **hard-fail** khi không xác định được trạng thái, với tác động tới an toàn và tính sẵn sàng.
8. Xây dựng chính sách kiểm tra trạng thái chứng thư cho HTTPS, mTLS, VPN, RADIUS/EAP-TLS và dịch vụ nội bộ.
9. Đọc chứng thư, CRL và phản hồi OCSP có sẵn bằng OpenSSL trong lab được cấp phép.
10. Chẩn đoán lỗi thu hồi, lập kế hoạch giám sát và xây dựng runbook khi một chứng thư hoặc CA bị xâm phạm.

## 2. Revocation nằm ở đâu trong quá trình xác minh chứng thư?

Giả sử client muốn kết nối dịch vụ **api.company.example** bằng HTTPS. Một quy trình xác minh chứng thư có thể xem xét:

1. **Xây dựng chuỗi chứng thư:** leaf → intermediate CA → trust anchor.
2. **Xác minh chữ ký và ràng buộc CA:** các chứng thư trong chuỗi được ký đúng, CA có quyền cấp, thuật toán/phạm vi sử dụng phù hợp.
3. **Xác minh thời gian:** Not Before và Not After hợp lệ theo đồng hồ và quy tắc kiểm tra.
4. **Xác minh danh tính:** SAN/hostname hoặc định danh dịch vụ phải khớp tên client thật sự yêu cầu.
5. **Xác minh mục đích:** Key Usage, EKU và chính sách ứng dụng phù hợp, ví dụ TLS server authentication.
6. **Xác minh trạng thái thu hồi:** kiểm tra OCSP, CRL hoặc cơ chế được nền tảng chấp nhận theo chính sách.
7. **Xác minh handshake:** server chứng minh sở hữu private key liên quan chứng thư theo giao thức TLS.

Thứ tự cụ thể phụ thuộc thư viện và quy trình handshake, nhưng **không thể dùng kết quả revocation để bỏ qua kiểm tra danh tính hoặc chuỗi CA**.

~~~mermaid
flowchart TD
    A["Client nhận certificate chain"] --> B["Xác minh trust anchor, chữ ký và ràng buộc CA"]
    B --> C["Kiểm tra hostname/SAN, EKU và thời hạn"]
    C --> D["Tra cứu hoặc nhận trạng thái thu hồi theo chính sách"]
    D --> E{"Trạng thái và bằng chứng đủ tin cậy?"}
    E -->|Đạt| F["Hoàn tất xác thực handshake và chấp nhận kênh"]
    E -->|"Revoked hoặc lỗi bắt buộc"| G["Từ chối kết nối"]
    E -->|"Không tra cứu được"| H["Áp dụng chính sách fail-open/fail-closed có kiểm soát"]
~~~

Sơ đồ là mô hình **logic**, không phải hướng dẫn về thứ tự gọi API TLS trong mọi phiên bản giao thức. Trong thực tế, TLS 1.3 có thể trao đổi chứng thư trong phần handshake đã mã hóa, và client có thể thực hiện nhiều phép kiểm tra trước khi cho ứng dụng gửi dữ liệu nhạy cảm.

### 2.1. Bốn câu hỏi không được đánh đồng

| Câu hỏi | Cơ chế chính | Vì sao OCSP/CRL không thay thế? |
| --- | --- | --- |
| Chứng thư còn trong khoảng thời gian hợp lệ? | Not Before / Not After | Chứng thư có thể chưa hết hạn nhưng đã revoked |
| Chứng thư có được một CA được tin cậy cấp hợp lệ? | Path validation / trust store | OCSP good không tạo trust anchor hoặc chữa lỗi chữ ký |
| Chứng thư có đại diện đúng endpoint không? | SAN/hostname hoặc service identity | OCSP good cho tên khác vẫn không hợp lệ |
| Chứng thư có bị thu hồi theo cơ chế đã chọn? | CRL, OCSP hoặc dữ liệu trạng thái tương đương | Trạng thái có giới hạn độ mới, phạm vi và hỗ trợ của client |

**Revocation là một điều kiện bên trong việc đánh giá chứng thư**, không phải dịch vụ “quét website sạch mã độc”.

## 3. Vì sao chứng thư bị thu hồi?

Một số tình huống cần cân nhắc revocation:

- **Private key bị lộ hoặc nghi bị lộ:** kẻ khác có thể sử dụng khóa để giả danh chủ chứng thư trong phạm vi phù hợp.
- **CA cấp sai:** chứng thư chứa danh tính không được phép hoặc không đáp ứng quy trình cấp phát.
- **Thay đổi quyền sở hữu/quản lý:** chứng thư không còn được phép gắn với dịch vụ hay người dùng cũ.
- **Thiết bị hoặc nhân viên rời tổ chức:** chứng thư client không còn hợp lệ cho truy cập mạng doanh nghiệp.
- **Thay thế khóa hoặc profile chứng thư:** có thể cần thu hồi chứng thư cũ theo chính sách vận hành.
- **CA/intermediate bị xâm nhập:** rủi ro ảnh hưởng một tập lớn chứng thư; việc khôi phục có thể cần thay trust anchor hoặc phát hành chuỗi mới.

### 3.1. Thu hồi khác hết hạn và khóa tài khoản

**Expiration** là mốc thời gian hiệu lực đã được định nghĩa trong chứng thư. **Revocation** là thay đổi trạng thái trước hạn, được CA hoặc hệ thống có thẩm quyền công bố theo cơ chế phù hợp. **Account disabling** trong IdP hoặc ứng dụng là quyết định phân quyền tài khoản, không tự cập nhật danh sách thu hồi của CA.

Ví dụ một nhân viên bị khóa tài khoản AD nhưng vẫn còn chứng thư client mTLS: nếu ứng dụng chỉ dựa vào chứng thư và không kiểm tra trạng thái/ủy quyền hiện tại, quyền truy cập có thể chưa bị thu hồi như tổ chức mong muốn.

### 3.2. Revocation có thể không được áp dụng giống nhau ở mọi client

Một số browser, thư viện TLS, VPN gateway, RADIUS server và thiết bị nhúng có cách kiểm tra khác nhau. Có nền tảng không kiểm tra trạng thái mặc định ở một số ngữ cảnh, hoặc chỉ kiểm tra dưới điều kiện cấu hình riêng. **Không nên nói “CA đã revoke thì tất cả ứng dụng sẽ chặn ngay”**.

## 4. Định danh chứng thư: issuer và serial number

Trong X.509, **serial number** do CA cấp và dùng để phân biệt chứng thư trong phạm vi **issuer** tương ứng. Chỉ đọc một serial không đủ để biết đó là chứng thư nào trên toàn Internet: các CA khác nhau có thể có những số serial giống nhau.

Khi kiểm tra CRL hay OCSP, cần biết **issuer thực sự cấp chứng thư** và thông tin định danh thích hợp, không chỉ so chuỗi tên hiển thị của Subject.

| Thành phần | Vai trò |
| --- | --- |
| **Issuer** | CA phát hành chứng thư hoặc danh tính định vị CA |
| **Serial number** | Định danh chứng thư trong phạm vi issuer |
| **Authority Key Identifier (AKI)** | Giúp liên hệ khóa CA phát hành trong nhiều quy trình |
| **Subject Key Identifier (SKI)** | Hỗ trợ nhận diện khóa public được công bố |
| **CRL issuer / scope** | Xác định danh sách thu hồi được phép áp dụng tới chứng thư nào |
| **OCSP CertID** | Định danh chứng thư cần tra cứu bằng issuer name hash, issuer key hash và serial, cùng thuật toán băm |

**Không sử dụng tên file PEM hoặc địa chỉ URL của CA làm định danh tin cậy duy nhất** cho việc xác minh trạng thái.

## 5. CRL là gì?

**Certificate Revocation List (CRL)** là danh sách dữ liệu được **ký số** để công bố những chứng thư trong phạm vi áp dụng đã bị thu hồi. Trong mô hình phổ biến, CA phát hành một CRL với các serial number bị thu hồi, thời điểm và có thể kèm lý do.

Client cần đánh giá **chữ ký CRL, thẩm quyền của CRL issuer, phạm vi CRL, tính mới của dữ liệu và mối liên hệ tới issuer của chứng thư** trước khi dùng nó để quyết định.

~~~mermaid
sequenceDiagram
    participant CA as CA / CRL issuer
    participant DP as Kho phân phối CRL
    participant C as Client kiểm tra chứng thư
    CA->>DP: Công bố CRL đã ký (serial revoked + metadata)
    C->>DP: Tải CRL qua điểm phân phối phù hợp
    DP-->>C: CRL và chữ ký
    Note over C: Kiểm tra chữ ký, issuer, scope, thisUpdate/nextUpdate
    Note over C: Đối chiếu serial của chứng thư cần kiểm tra
    Note over C: Ra quyết định theo policy và trạng thái thu hồi
~~~

### 5.1. Những trường quan trọng trong CRL

| Trường / extension | Ý nghĩa |
| --- | --- |
| **Issuer** | Danh tính bên phát hành CRL |
| **thisUpdate** | Thời điểm thông tin CRL có hiệu lực hoặc được công bố theo định dạng |
| **nextUpdate** | Thời điểm dự kiến có CRL mới; hỗ trợ đánh giá độ mới trong profile áp dụng |
| **Revoked certificates** | Danh sách serial number đã bị thu hồi thuộc phạm vi |
| **revocationDate** | Thời điểm thu hồi được ghi cho một entry |
| **Reason code** | Lý do nếu được cung cấp, ví dụ keyCompromise hoặc cessationOfOperation |
| **CRL Number** | Số phiên bản tăng dần để hỗ trợ nhận diện và đồng bộ |
| **Authority Key Identifier** | Hỗ trợ gắn CRL với khóa issuer thích hợp |
| **Issuing Distribution Point** | Có thể giới hạn phạm vi CRL cho một tập chứng thư hoặc đối tượng |
| **Delta CRL Indicator** | Cho biết đây là delta CRL liên quan đến một base CRL thích hợp |

Một CRL **không có serial** của chứng thư đang hỏi **không tự chứng minh chứng thư hợp lệ** nếu CRL bị hết hiệu lực, sai issuer, sai scope hoặc chữ ký không xác minh được.

### 5.2. CRL Distribution Point (CDP)

Chứng thư X.509 có thể mang extension **CRL Distribution Points**, cung cấp một hoặc nhiều vị trí để client tìm CRL phù hợp. Vị trí có thể là HTTP/HTTPS, LDAP hoặc kiểu khác tùy PKI.

CDP là **thông tin định vị**, không phải bằng chứng rằng nội dung ở URL đáng tin. Client vẫn phải kiểm tra chữ ký và phạm vi của CRL. Không phải thư viện nào cũng tự tải CRL từ CDP theo mặc định.

### 5.3. Full CRL và delta CRL

- **Full/base CRL:** tập dữ liệu thu hồi làm mốc trong phạm vi được bao phủ.
- **Delta CRL:** chứa những thay đổi trạng thái liên quan base CRL theo cơ chế được chuẩn hóa, có thể giảm dữ liệu tải về.

Nếu dùng delta CRL, validator phải có **base CRL tương thích**, xác minh cả hai và áp dụng quy tắc kết hợp. Một delta CRL độc lập **không thay thế full CRL** khi cần dữ liệu gốc.

### 5.4. Bảo trì và phân phối CRL

Một CA quy mô lớn có thể có danh sách nhiều chứng thư bị thu hồi. CRL cần được:

1. Phát hành đúng lịch và gia hạn trước khi dữ liệu trở nên quá cũ.
2. Ký bằng khóa có quyền phát hành CRL theo PKI.
3. Phân phối tại những endpoint đủ khả dụng với client trong mạng.
4. Phục vụ qua các đường mạng được firewall/proxy cho phép theo nhu cầu.
5. Giám sát kích thước, thời gian tải, chứng thực chữ ký và độ trễ phát hành.

Nếu doanh nghiệp có nhiều zone hoặc site mạng phân đoạn, cần xác định **client thực sự có thể truy cập CRL** ở chặng nào; đừng chỉ kiểm tra từ máy quản trị ở management VLAN.

## 6. Những trạng thái CRL cần phân tích đúng

| Tình huống | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Serial xuất hiện trong CRL hợp lệ đúng issuer/scope | Chứng thư đã được báo revoked theo dữ liệu đó | Không tự chứng minh kẻ nào sử dụng khóa |
| Serial không xuất hiện trong CRL hợp lệ còn mới | Không bị liệt kê là revoked trong phạm vi và thời điểm của CRL | Không chứng minh key an toàn hoặc chứng thư được cấp đúng |
| CRL hết nextUpdate theo chính sách áp dụng | Dữ liệu có thể quá cũ để quyết định | Không được tự cho rằng chứng thư chưa bị thu hồi |
| Không tải được CRL | Không có bằng chứng thu hồi mới từ nguồn đó | Không đồng nghĩa CA báo good |
| CRL chữ ký sai | Không thể tin nội dung CRL theo đường tin cậy đang dùng | Không nên lấy nội dung để cho phép hoặc từ chối như dữ liệu đã xác thực |
| CRL đúng chữ ký nhưng sai issuer hoặc scope | Dữ liệu không phù hợp chứng thư đang hỏi | Không sử dụng để kết luận trạng thái của chứng thư đó |

**Phân biệt “not listed”, “not checked”, “unknown” và “revoked”** là yêu cầu vận hành thiết yếu. Nếu phần mềm không thực hiện kiểm tra CRL, không thể ghi trạng thái “not revoked” như thể đã kiểm chứng.

## 7. OCSP là gì?

**Online Certificate Status Protocol (OCSP)** là giao thức cho phép client hỏi một **OCSP responder** về trạng thái của một chứng thư xác định. Thay vì tải toàn bộ danh sách CRL, client gửi thông tin định danh chứng thư và nhận **phản hồi trạng thái có ký số** theo mô hình được hỗ trợ.

~~~mermaid
sequenceDiagram
    participant C as Validating client
    participant S as TLS server
    participant O as OCSP responder
    C->>S: Thiết lập TLS và nhận chứng thư
    Note over C: Xây dựng chain, xác định issuer và CertID
    C->>O: OCSP request (CertID của leaf)
    O-->>C: OCSP response đã ký, status + thời gian
    Note over C: Kiểm tra responder được phép ký, chữ ký, CertID, độ mới
    Note over C: Kết hợp với path/hostname validation và policy
~~~

Đây là đường **OCSP trực tiếp** từ client đến responder. Với **OCSP stapling**, server có thể cung cấp một phản hồi trạng thái đã ký để client kiểm tra, không nhất thiết client phải hỏi responder cho mỗi kết nối.

### 7.1. OCSP CertID

Yêu cầu OCSP chỉ ra chứng thư cần kiểm tra bằng dữ liệu như:

- Thuật toán băm định danh issuer.
- **issuerNameHash** và **issuerKeyHash**.
- **serialNumber** của chứng thư.

Các trường này giúp responder và client xác định chứng thư thuộc issuer nào. **Không gửi private key của chứng thư** trong OCSP request.

### 7.2. Ba trạng thái certificate status

| Trạng thái OCSP | Ý nghĩa theo giao thức | Cách hiểu đúng |
| --- | --- | --- |
| **good** | Responder không xác định chứng thư là revoked theo thông tin của mình trong ngữ cảnh trạng thái trả về | Không tự bảo đảm chứng thư từng được cấp hợp lệ, đúng hostname hoặc website an toàn |
| **revoked** | Responder báo chứng thư đã bị thu hồi, có thể kèm thời điểm và lý do | Client nên áp dụng chính sách từ chối phù hợp, điều tra và thay khóa/chứng thư |
| **unknown** | Responder không xác định được trạng thái chứng thư theo phạm vi nó biết | Không phải good; không nên gán “hợp lệ” khi chính sách đòi hỏi bằng chứng trạng thái |

**Good không có nghĩa “chứng thư được CA chứng nhận là sạch”**. Theo mô hình OCSP truyền thống, good chủ yếu nói không có thông tin revoked theo responder; cần xác minh **path, danh tính và các kiểm soát khác**.

Một số responder có chính sách cho chứng thư chưa từng phát hành và hành vi trả **revoked** theo mở rộng giao thức thích hợp. Vì vậy không nên thiết kế logic chỉ dựa vào giả định **mọi serial chưa tồn tại đều trả unknown**.

### 7.3. OCSP response status khác certificate status

Giao thức còn có **trạng thái xử lý phản hồi** ở mức OCSP như successful, malformedRequest, internalError, tryLater, sigRequired hoặc unauthorized trong những tình huống thích hợp.

**Phản hồi OCSP có status successful chỉ cho biết thông điệp được xử lý thành công ở mức giao thức**, không có nghĩa chứng thư là good. Client còn cần kiểm tra **SingleResponse, chữ ký, tính hợp lệ của responder và certificate status**.

## 8. Ai được quyền ký phản hồi OCSP?

Một phản hồi trạng thái chỉ đáng tin khi được ký bởi **chủ thể có thẩm quyền phù hợp** đối với chứng thư được hỏi và validator kiểm tra đúng.

Những mô hình thường gặp:

- **CA đã cấp chứng thư** trực tiếp ký phản hồi.
- **OCSP responder được CA ủy quyền**, với chứng thư ký phù hợp, thường bao gồm EKU **id-kp-OCSPSigning**, có ràng buộc đúng issuer và quy tắc ủy quyền áp dụng.
- Một số trường hợp có **responder được tin cậy cục bộ** theo chính sách riêng của client, phải được thiết kế và đánh giá cẩn thận.

**Không thể tin một phản hồi chỉ vì HTTPS URL của responder trông hợp lệ.** Nguồn vận chuyển và **chữ ký OCSP bên trong** là hai khái niệm khác nhau. Nếu một responder không được phép ký phản hồi cho issuer tương ứng, dữ liệu đó phải bị từ chối theo quy tắc xác minh.

### 8.1. Các trường thời gian của OCSP

| Trường | Ý nghĩa |
| --- | --- |
| **producedAt** | Thời điểm phản hồi OCSP được tạo |
| **thisUpdate** | Thời điểm trạng thái được xác nhận là hiện hành theo phản hồi |
| **nextUpdate** | Thời điểm dự kiến có trạng thái cập nhật; có thể không được cung cấp trong một số profile, cần áp dụng chính sách giới hạn độ mới |
| **revocationTime** | Thời điểm thu hồi đối với response revoked |
| **revocationReason** | Lý do thu hồi nếu được cung cấp |

Một phản hồi ký đúng nhưng **quá cũ hoặc chưa có hiệu lực theo chính sách** không nên được tái sử dụng vô hạn. Client phải kiểm tra các mốc thời gian, sai số đồng hồ cho phép và giới hạn tuổi dữ liệu.

### 8.2. OCSP nonce và cache

**Nonce** là extension tùy chọn để ràng buộc response với một request cụ thể, giúp giảm một số tình huống phát lại phản hồi. Tuy nhiên:

- Không phải mọi responder hoặc client đều hỗ trợ/đòi hỏi nonce theo cùng cách.
- Sử dụng nonce riêng cho mỗi request có thể làm giảm khả năng sử dụng cache chung.
- Một response không có nonce **không tự là giả mạo**, nếu được xác minh chữ ký, thời gian và chính sách tương ứng.
- Nonce không bảo đảm private key CA còn an toàn hoặc response không bị lạm dụng trong khoảng hiệu lực.

Do vậy phải hiểu **trade-off giữa freshness, khả dụng và khả năng cache** của từng hệ thống.

## 9. So sánh OCSP và CRL

| Tiêu chí | CRL | OCSP |
| --- | --- | --- |
| Cách truy vấn | Tải danh sách trạng thái bị thu hồi trong phạm vi | Hỏi trạng thái một hoặc nhiều CertID |
| Bằng chứng chính | CRL được ký bởi issuer có thẩm quyền | OCSP response được ký bởi responder có thẩm quyền |
| Kích thước dữ liệu | Có thể lớn nếu nhiều chứng thư bị thu hồi | Thường nhỏ hơn cho một chứng thư |
| Cache | Có thể cache cả CRL tới giới hạn hiệu lực | Có thể cache từng response theo thời hạn |
| Mức riêng tư | Một bản CRL có thể dùng lại cho nhiều chứng thư | Tra cứu trực tiếp có thể tiết lộ chứng thư/issuer đang được hỏi |
| Điểm nghẽn | Phân phối CRL, kích thước, thời gian cập nhật | Responder availability, request volume, độ trễ |
| Dữ liệu mới | Phụ thuộc chu kỳ phát hành và phân phối CRL/delta | Phụ thuộc responder cập nhật, tuổi response và cache |
| Khi bị lỗi mạng | Không tải được CRL mới hoặc phải dựa cache | Không hỏi responder được; stapling/cache có thể hữu ích |
| Chính sách client | Phải hỗ trợ tải, kiểm tra chữ ký, issuer/scope | Phải hỗ trợ xác minh OCSP response và tùy chọn stapling |
| Phạm vi dùng | Phổ biến trong PKI nội bộ, thiết bị/ứng dụng có CRL | Thường thấy trong TLS/PKI, tùy nền tảng và profile |

**Không có một cơ chế thắng tuyệt đối trong mọi môi trường**. Nhiều PKI công bố cả CRL và OCSP; client có thể chỉ dùng một nguồn, dùng phối hợp hoặc không kiểm tra trong một ngữ cảnh cụ thể. Đánh giá phải theo **client thực tế và yêu cầu dịch vụ**, không chỉ theo thông tin CA cung cấp.

## 10. OCSP stapling

**OCSP stapling** là cơ chế cho phép TLS server lấy phản hồi OCSP đã được ký trước, sau đó **đính kèm phản hồi đó trong TLS handshake** để client xác minh, thay vì client phải tự kết nối đến OCSP responder mỗi lần.

~~~mermaid
sequenceDiagram
    participant O as OCSP responder
    participant S as TLS server / edge proxy
    participant C as TLS client
    S->>O: Lấy OCSP response theo lịch
    O-->>S: Response có chữ ký và thời hạn
    Note over S: Lưu cache, làm mới trước khi hết hạn
    C->>S: TLS ClientHello (thể hiện hỗ trợ theo giao thức)
    S-->>C: Chứng thư + OCSP status response được staple
    Note over C: Kiểm tra chain, hostname, responder, status và freshness
    C->>S: Hoàn tất handshake nếu mọi điều kiện bắt buộc đạt
~~~

### 10.1. Lợi ích

- **Giảm độ trễ** do client không phải luôn tạo request riêng tới responder.
- **Giảm tiết lộ dữ liệu truy cập** cho responder CA trong những mô hình mà client bình thường sẽ tự hỏi OCSP.
- **Giảm tải responder** nhờ server có thể làm mới response theo chu kỳ.
- **Giảm một số lỗi kết nối OCSP trực tiếp** khi client không thể tới responder nhưng server còn response hợp lệ.

### 10.2. Giới hạn

OCSP stapling **không sửa chứng thư bị revoked, hết hạn, sai SAN hoặc được cấp bởi CA không tin**. Một response staple cũng có thể bị hết hạn, sai CertID, sai chữ ký hoặc không áp dụng cho chain đang trình bày.

Không phải mọi client đều yêu cầu hoặc kiểm tra staple giống nhau. Nếu server chưa kịp tải được OCSP response, có thể xảy ra các hành vi khác nhau tùy client và profile. **Một server bật stapling không bảo đảm mọi client đều thực sự thực hiện revocation checking**.

### 10.3. TLS 1.2 và TLS 1.3 khác nhau ở cách mang response

- **TLS 1.2** có cơ chế *certificate status request* và, khi được thương lượng/phù hợp, có thể dùng thông điệp **CertificateStatus** trong handshake.
- **TLS 1.3** có thể mang thông tin OCSP response qua extension liên quan **CertificateEntry** thay vì sử dụng CertificateStatus độc lập theo cách TLS 1.2.

Khi chẩn đoán, cần xem **phiên bản TLS, khả năng hỗ trợ của client/server và phản hồi thực tế**, không mặc định bắt buộc phải thấy đúng một tên thông điệp trong mọi phiên.

### 10.4. Must-Staple / TLS Feature

Chứng thư X.509 có thể chứa **TLS Feature extension**, thường được nhắc đến với tên **OCSP Must-Staple** khi yêu cầu hỗ trợ kiểm tra trạng thái qua cách thức stapling thích hợp.

Điểm cần lưu ý:

- **Không phải mọi client/browser đều thực thi Must-Staple giống nhau**.
- Nếu client thực thi nghiêm mà server thiếu response hợp lệ, **khả năng kết nối có thể bị gián đoạn**.
- Must-Staple không thay thế chuỗi CA, hostname, thời hạn và những điều kiện khác.
- Chỉ kích hoạt khi có cơ chế **tự động làm mới, quan sát, failover và kiểm thử** đối với các endpoint TLS liên quan.

## 11. Cache, tính mới và nguy cơ phát lại phản hồi

OCSP và CRL đều có **thời gian hiệu lực**. Điều này giúp cache và giảm tải nhưng tạo ra một **khoảng thời gian giữa lúc chứng thư bị thu hồi và lúc client nhận được thông tin mới**.

Giả sử một response OCSP trạng thái good được tạo trước sự cố lộ khóa. Nếu response đó vẫn còn được chính sách client xem là mới, client có thể chấp nhận nó cho đến khi cần kiểm tra lại. Điều này không tự chứng minh đã có tấn công; đó là đặc tính vận hành phải được tính vào mô hình rủi ro.

### 11.1. Những tham số cần quản lý

- **thisUpdate/nextUpdate** và giới hạn tuổi response/CRL.
- Khả năng làm mới OCSP staple trước khi response cũ hết giá trị.
- Độ trễ phân phối CRL mới giữa các site.
- Chênh lệch đồng hồ client, CA, responder và server.
- Khả năng client lưu cache và **không tự cập nhật ngay** khi CA thay đổi trạng thái.
- Cách hệ thống xử lý stale response, không có nextUpdate hoặc sai lệch thời gian.

### 11.2. Không đặt “freshness” bằng một con số tùy ý

Một tổ chức có thể có yêu cầu nghiêm ngặt với chứng thư dùng cho quản trị hoặc client mTLS, trong khi truy cập web công khai có yêu cầu khả dụng khác. Giới hạn tuổi dữ liệu phải dựa trên **chính sách rủi ro, profile chứng thư, quy tắc giao thức và khả năng client**, không áp dụng một ngưỡng cứng giống nhau cho mọi hệ thống.

## 12. Soft-fail và hard-fail

Một tình huống khó là client **không lấy được bằng chứng trạng thái thu hồi đáng tin cậy** do timeout, phản hồi lỗi, cache hết hạn hoặc responder/CRL server không thể truy cập.

**Soft-fail** và **hard-fail** là hai chiến lược chính:

| Chiến lược | Hành vi khi không xác định được trạng thái | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| **Soft-fail** | Có thể tiếp tục kết nối khi kiểm tra trạng thái không khả dụng theo chính sách | Giảm gián đoạn do responder/CRL outage | Có thể chấp nhận chứng thư đã bị thu hồi nhưng chưa xác minh được |
| **Hard-fail** | Từ chối kết nối khi không có bằng chứng trạng thái đạt yêu cầu | Tăng nghiêm ngặt đối với yêu cầu thu hồi | Có thể gây từ chối dịch vụ diện rộng khi nguồn trạng thái lỗi |

**Soft-fail không đồng nghĩa bỏ qua một kết quả revoked đã được xác minh.** Một hệ thống được thiết kế hợp lý thường phân biệt:

- **Revoked có bằng chứng hợp lệ:** từ chối theo chính sách bảo mật.
- **Good có bằng chứng hợp lệ và còn mới:** tiếp tục những bước xác minh khác.
- **Unknown, lỗi giao thức, chữ ký sai, không liên hệ được responder hoặc dữ liệu stale:** xử lý theo **quy tắc khác nhau**, không gộp tất cả thành good.

Một số chính sách có thể có **nhiều trạng thái trung gian** như “không kiểm tra được nhưng có thể dùng cache chưa hết hạn” hoặc “chỉ cho phép remediation”; không phải chỉ một công tắc toàn cục.

### 12.1. Tính sẵn sàng cũng là bảo mật

Với VPN công ty, nếu tất cả gateway hard-fail và OCSP responder nội bộ bị nghẽn, toàn bộ nhân viên từ xa có thể không đăng nhập được. Với mạng Wi-Fi Enterprise, nếu RADIUS không truy cập được CRL theo chính sách bắt buộc, thiết bị có thể không được cấp quyền mạng.

Giải pháp không phải mặc định **tắt revocation checking**. Cần có nguồn trạng thái dự phòng, khả năng cache hợp lệ, theo dõi SLA, mạng quản trị phù hợp và thủ tục khẩn cấp được phê duyệt.

## 13. CRL, OCSP và private PKI doanh nghiệp

Trong một PKI nội bộ, doanh nghiệp có thể quản lý:

- **Root CA** được bảo vệ riêng, ít sử dụng để cấp chứng thư trực tiếp.
- **Issuing/intermediate CA** cấp chứng thư máy chủ, chứng thư thiết bị và người dùng.
- **CRL distribution service** cho các client cần tải danh sách.
- **OCSP responder** nếu profile/công nghệ có yêu cầu.
- **Trust distribution** qua MDM, GPO, hệ điều hành, container image hoặc service configuration được quản lý.
- **Inventory và monitoring** theo serial, issuer, SAN, expiration và tình trạng revoke.

~~~mermaid
flowchart TD
    ROOT["Root CA / Trust anchor được cấp phát an toàn"] --> ISS["Issuing CA"]
    ISS --> SRV["Server certificate: TLS / VPN"]
    ISS --> CLI["Client certificate: mTLS / Wi-Fi"]
    ISS --> CRL["CRL service: danh sách thu hồi đã ký"]
    ISS --> OCSP["OCSP responder có quyền trả trạng thái"]
    SRV --> V["Client xác minh server"]
    CLI --> G["Gateway / RADIUS xác minh client"]
    CRL -. "Revocation evidence" .-> V
    CRL -. "Revocation evidence" .-> G
    OCSP -. "Status response" .-> V
    OCSP -. "Status response" .-> G
    V -. "Security events" .-> SOC["SOC / PKI Monitoring"]
    G -. "Authentication events" .-> SOC
~~~

### 13.1. Chứng thư client thường có yêu cầu khác chứng thư server

Với mTLS, gateway/API server phải xác minh chứng thư **client**; với HTTPS browser, browser phải xác minh chứng thư **server**. Bên kiểm tra revocation là bên thực hiện **certificate validation ở chặng đó**.

Ví dụ:

- Browser xác minh server certificate của trang HTTPS.
- API server kiểm tra client certificate của một workload mTLS.
- VPN gateway kiểm tra chứng thư client khi sử dụng cơ chế certificate authentication.
- Wi-Fi Enterprise RADIUS/EAP server xác minh chứng thư client theo phương thức EAP được triển khai.

**Chỉ vì CA công bố OCSP/CRL không có nghĩa tất cả các bên trên đã bật kiểm tra.** Cần xác minh tính năng, phạm vi, chứng thư được xét và hành vi fail mode ở từng hệ thống.

### 13.2. Không nhầm thu hồi chứng thư với thu hồi quyền ứng dụng

Nếu chứng thư client còn hiệu lực nhưng tài khoản đã bị xóa khỏi nhóm truy cập VPN, ứng dụng vẫn phải từ chối theo chính sách IAM. Ngược lại, gỡ user khỏi nhóm IAM **không tự khiến serial chứng thư xuất hiện trong CRL**.

Mô hình đúng là **certificate status + identity mapping + authorization + session revocation**, đặc biệt với quyền quản trị hoặc dịch vụ nhạy cảm.

## 14. Phân phối trạng thái qua mạng phân đoạn, firewall và VPN

OCSP/CRL có thể phụ thuộc vào **dịch vụ mạng ngoài đường ứng dụng chính**. Ví dụ ứng dụng phía sau firewall chỉ gọi HTTPS tới API, nhưng validator cần lấy CRL từ một HTTP endpoint hoặc truy cập OCSP responder.

Khi thiết kế segmentation:

| Nguồn truy cập | Đích cần thiết | Điều phải kiểm tra |
| --- | --- | --- |
| Browser / TLS client | OCSP responder hoặc CRL DP theo chính sách | DNS, route, firewall/proxy và giới hạn quyền riêng tư |
| Reverse proxy | OCSP responder để làm mới stapled response | Khả năng làm mới, cache, giám sát expiry |
| RADIUS server | PKI CRL/OCSP service | Không làm xác thực Wi-Fi Enterprise lỗi do thiếu đường trạng thái |
| VPN gateway | CA revocation endpoints | Không khiến remote access bị hard-fail ngoài kế hoạch |
| Workload mTLS | PKI endpoints hoặc proxy phân phối trạng thái | Mỗi phía kiểm tra chứng thư mà mình nhận |
| PKI/CA | CRL publishing / OCSP responders | Kiểm soát quyền ghi và ký dữ liệu trạng thái |

**Không mở cổng đến mọi địa chỉ Internet chỉ để “OCSP chạy được”.** Cần xác định endpoint thật, giao thức, DNS, proxy có hỗ trợ, và các chính sách đường ra tối thiểu của từng vùng.

### 14.1. VPN bootstrap và phụ thuộc vòng

Một VPN dùng chứng thư client có thể cần kiểm tra CRL/OCSP **trước khi tunnel hình thành**. Nếu gateway chỉ truy cập được responder thông qua chính tunnel đang đợi thiết lập, có thể tạo **phụ thuộc vòng** dẫn tới lỗi xác thực.

Trong thiết kế, phải xác định **ai cần tra cứu, ở phía nào của tunnel, vào thời điểm nào**. Kiểm thử từ đường mạng có thật của gateway, không chỉ từ laptop bên trong LAN.

### 14.2. Wi-Fi Enterprise và thiết bị chưa có địa chỉ mạng

Với 802.1X, một thiết bị có thể đang ở giai đoạn xác thực EAP trước khi có quyền truy cập bình thường vào mạng. **RADIUS/EAP server** thường là nơi kiểm tra chứng thư client trong EAP-TLS; đường đến responder hoặc CRL của chính server đó phải tồn tại và phù hợp chính sách.

Nếu client xác minh chứng thư EAP server, việc kiểm tra trạng thái và tải intermediate ở phía client có thể có các giới hạn khác do thiết bị chưa có kết nối đầy đủ. Cần xem **hành vi thật của OS/supplicant** và bảo đảm trust profile được MDM quản lý; không mặc định mọi OS tự tra cứu OCSP qua mạng trong bước EAP.

### 14.3. Cloud và service mesh

Cloud load balancer, API gateway hoặc service mesh có thể kết thúc TLS ở một chặng và tạo mTLS chặng khác. Mỗi chặng có **certificate verifier và chính sách trạng thái riêng**. Một số hệ thống dùng **chứng thư ngắn hạn và rotation tự động** thay cho việc phụ thuộc chủ yếu vào OCSP/CRL trong thời gian sống ngắn.

Chứng thư ngắn hạn giảm cửa sổ hiệu lực tối đa nhưng **không làm private key không thể bị lộ**, cũng không tự thay thế identity/authorization hoặc thu hồi quyền phiên đang hoạt động.

## 15. Mô hình quyết định trạng thái chứng thư

Một chính sách kiểm tra có thể được mô tả như sau:

~~~mermaid
flowchart TD
    A["Chứng thư cần xác minh"] --> B{"Path, hostname, time, EKU hợp lệ?"}
    B -->|Không| X["Từ chối: không phải lỗi cần chữa bằng OCSP"]
    B -->|Có| C{"Policy có yêu cầu revocation checking?"}
    C -->|Không| N["Ghi nhận not checked; đánh giá chính sách tổng thể"]
    C -->|Có| D["Lấy staple / OCSP / CRL phù hợp"]
    D --> E{"Bằng chứng có chữ ký, đúng scope, còn mới?"}
    E -->|Không| U["Trạng thái unavailable/unknown/stale"]
    U --> POLICY{"Fail mode theo rủi ro"}
    POLICY -->|Hard-fail| DENY["Từ chối"]
    POLICY -->|Soft-fail có điều kiện| ALLOW2["Tiếp tục có log và kiểm soát bù"]
    E -->|Có| F{"Trạng thái được xác minh"}
    F -->|Revoked| DENY
    F -->|Not revoked theo bằng chứng| ALLOW["Tiếp tục xác minh handshake và quyền"]
~~~

Lưu ý: sơ đồ dùng nhãn **not revoked theo bằng chứng** để tránh hiểu sai rằng OCSP good chứng minh toàn bộ danh tính hoặc key an toàn. Trong sản phẩm thật, còn có **unknown**, cơ chế fallback hoặc hành vi cụ thể của responder và client.

### 15.1. Không trộn kết quả kỹ thuật với quyết định policy

Một hệ thống giám sát nên phân biệt:

- **certificateValidationStatus:** path/name/time/EKU hợp lệ hay không.
- **revocationEvidenceStatus:** good, revoked, unknown, not-checked, stale, fetch-error, invalid-signature...
- **policyDecision:** allow, deny, defer, limited-access.
- **policyReason:** rule và phiên bản cấu hình gây ra quyết định.

Nếu chỉ ghi một cờ **valid=true**, SOC sẽ khó phân biệt người dùng được cho phép vì có bằng chứng trạng thái hay vì soft-fail.

## 16. Mẫu cấu hình vận hành trung lập với sản phẩm

YAML dưới đây chỉ mô tả **ý định kiểm soát**, không phải cấu hình có thể dán vào OpenSSL, Nginx, Java, Windows PKI, VPN hay RADIUS:

~~~yaml
pkiRevocationPolicy:
  name: certificate-status-validation
  environment: authorized-training
  trust:
    trustAnchors: organization-approved
    verifyCertificatePath: true
    verifyHostnameOrServiceIdentity: true
    verifyIntendedUsage: true
    verifyValidityPeriod: true
  certificateStatus:
    enabled: true
    acceptedSources:
      - validated-ocsp-response
      - validated-crl-with-correct-scope
    requireMatchingIssuerAndCertificateId: true
    requireAuthorizedResponseSigner: true
    requireFreshEvidence: true
    maxStaleness: defined-by-risk-and-client-capability
    revokedDecision: deny
    unknownDecision: review-client-profile
    timeoutDecision: policy-specific
  edgeTls:
    ocspStapling: enable-if-supported-and-monitored
    refreshBeforeExpiry: true
    monitorStapleValidity: true
    tlsFeatureMustStaple: only-with-tested-client-support
  internalMtls:
    validateClientCertificates: true
    revocationMode: strict-when-supported-and-high-availability
    sessionReauthorization: defined-by-service-risk
  availability:
    redundantResponders: evaluate
    crlDistributionMonitoring: enabled
    detectUnreachableRevocationEndpoints: true
    testHardFailAndSoftFail: true
  operations:
    requireChangeApproval: true
    recordEvidenceAndDecisionSeparately: true
    monitorKeyCompromiseIncidents: true
    protectResponderSigningKeys: true
    keepRecoveryRunbook: true
~~~

Không có ý nghĩa kỹ thuật nào chỉ vì trường **revokedDecision: deny** xuất hiện trong YAML mô tả. Cần chuyển từng điều kiện thành **tính năng được xác minh của client**, kiểm tra khả năng thư viện/thiết bị và thử nghiệm các kết quả thực tế.

### 16.1. Policy khác nhau cho các trường hợp sử dụng

| Trường hợp | Mức ưu tiên | Quyết định cần đánh giá |
| --- | --- | --- |
| Trang HTTPS công khai | Sẵn sàng phục vụ và an toàn cho client đa dạng | Client thực sự kiểm tra nguồn nào? stapling hỗ trợ ở đâu? |
| Admin VPN | Danh tính và quyền nhạy cảm | Hard-fail, HA responder, quy trình break-glass có kiểm soát |
| Wi-Fi EAP-TLS cho nhân viên | Không cấp quyền cho cert revoked, vẫn duy trì truy cập hợp lệ | CRL/OCSP availability tại RADIUS, profile client |
| API mTLS thanh toán | Danh tính workload, kiểm soát client cert | Kết hợp revocation, short-lived certs và authorization |
| Thiết bị IoT offline | Truy cập mạng hạn chế và khả năng kết nối kém | CRL distribution hoặc cơ chế thay khóa/thu hồi phù hợp |
| Cloud service mesh | Rotation nhanh và nhiều workload | Tuổi chứng thư, identity policy và tính năng trạng thái được hỗ trợ |

## 17. OpenSSL: đọc và kiểm tra CRL an toàn

Các lệnh dưới đây dùng trong **lab được cấp phép**, với file PEM/DER đã được tạo hoặc cung cấp hợp pháp. Chúng phục vụ **quan sát**, không tự thu hồi hay tạo chứng thư ngoài quyền quản lý.

### 17.1. Đọc thông tin chứng thư

~~~bash
# File leaf.pem chỉ chứa chứng thư công khai, KHÔNG phải private key.
openssl x509 -in leaf.pem -noout -subject -issuer -serial -dates

# Xem nơi phân phối CRL và OCSP khi chứng thư có extension tương ứng.
openssl x509 -in leaf.pem -noout -ext crlDistributionPoints
openssl x509 -in leaf.pem -noout -ext authorityInfoAccess

# Kiểm tra mục đích sử dụng chứng thư.
openssl x509 -in leaf.pem -noout -ext extendedKeyUsage
~~~

Các extension có thể **không tồn tại** trong mọi chứng thư; sự thiếu AIA/CDP không tự có nghĩa chứng thư chắc chắn không được dùng với mọi cơ chế trạng thái khác. Có thể có dữ liệu ngoài chứng thư hoặc chính sách riêng của nền tảng.

### 17.2. Đọc CRL PEM có sẵn

~~~bash
# Đọc CRL ở định dạng PEM đã tải từ hạ tầng PKI lab.
openssl crl -in issuer.crl.pem -noout -text

# Xem issuer và lịch cập nhật của CRL.
openssl crl -in issuer.crl.pem -noout -issuer -lastupdate -nextupdate
~~~

Nếu CRL được lưu dưới dạng **DER**, chỉ rõ định dạng:

~~~bash
openssl crl -inform DER -in issuer.crl.der -noout -text
~~~

**Lệnh đọc CRL không tự xác minh rằng CRL đáng tin hoặc áp dụng đúng certificate**. Phải kiểm tra chữ ký, issuer/scope và trust chain bằng chức năng validator phù hợp; không chỉ thấy serial rồi kết luận.

### 17.3. Kiểm tra trạng thái bằng CRL trong lab

Khi có một CRL đã được PKI lab cấp và đúng scope, có thể tham khảo chức năng kiểm tra CRL của OpenSSL:

~~~bash
# Ví dụ cho bài lab có CA chain và CRL phù hợp.
# Dòng này không tự tải CRL từ URL CDP.
openssl verify \
  -CAfile trusted-ca-bundle.pem \
  -CRLfile issuer.crl.pem \
  -crl_check \
  leaf.pem
~~~

Lệnh dùng **-crl_check** kiểm tra revocation của **end-entity certificate** theo khả năng và dữ liệu được cung cấp; nếu cần kiểm tra CRL cho các cấp CA trong chain, có thể cần tùy chọn/chính sách khác (ví dụ **-crl_check_all**) và CRL tương ứng.

**Không tự suy rằng verify OK chứng minh OCSP hoặc hostname đã được kiểm tra**, vì lệnh ở đây chưa yêu cầu hai bước đó. Để kiểm tra hostname, cần thêm tùy chọn xác minh tên phù hợp với phiên bản OpenSSL và ngữ cảnh giao thức.

## 18. OpenSSL: kiểm tra phản hồi OCSP

### 18.1. Đọc phản hồi OCSP đã được lưu

Trong môi trường thử nghiệm có **response.der**, chứng thư leaf và issuer:

~~~bash
# Phân tích response đã lưu trong lab, không gửi request ra Internet.
openssl ocsp \
  -respin ocsp-response.der \
  -issuer issuing-ca.pem \
  -cert leaf.pem \
  -CAfile trusted-ca-bundle.pem \
  -resp_text
~~~

Đầu ra có thể chứa status, CertID, thisUpdate/nextUpdate, responder và thông tin xác minh. **Không coi từ good trong bản in là đủ**: phải xác nhận chương trình đã kiểm tra chữ ký phản hồi và chứng thư responder phù hợp chính sách.

### 18.2. Hỏi OCSP responder của lab

Khi đang quản lý responder và được phép thử mạng lab:

~~~bash
# URL .example chỉ để minh họa; thay bằng OCSP URL lab được phê duyệt.
openssl ocsp \
  -issuer issuing-ca.pem \
  -cert leaf.pem \
  -url http://ocsp.lab.example \
  -CAfile trusted-ca-bundle.pem \
  -resp_text \
  -timeout 5
~~~

Lệnh này **có gửi truy vấn mạng** khi chạy. Không thử tới hệ thống của bên thứ ba khi không có yêu cầu; với URL *.example, cần môi trường lab tự cung cấp DNS/service. Tùy phiên bản OpenSSL, cách kiểm tra responder được ủy quyền và chain có thể đòi hỏi cấu hình thêm; tham chiếu hướng dẫn của phiên bản thực tế.

### 18.3. OCSP status không phải lỗi TLS duy nhất

Nếu OCSP trả good nhưng TLS client vẫn báo **hostname mismatch**, việc sửa OCSP không giải quyết được lỗi. Ngược lại, nếu chứng thư đúng hostname và trust anchor nhưng OCSP phản hồi revoked, **không nên bỏ qua revoked** chỉ vì website vẫn có thể chạy khi tắt kiểm tra.

### 18.4. Kiểm tra OCSP stapling của một TLS endpoint

~~~bash
# Chỉ kiểm tra endpoint được phép; ví dụ tên là giả lập.
openssl s_client \
  -connect api.company.example:443 \
  -servername api.company.example \
  -verify_hostname api.company.example \
  -verify_return_error \
  -status </dev/null
~~~

Tùy hỗ trợ của OpenSSL/server và TLS version, output có thể hiển thị **OCSP response stapled** hoặc thông báo chưa có response. **Không thấy staple không tự khẳng định cert bị thu hồi**; đồng thời một staple có mặt nhưng chưa được client kiểm tra đúng vẫn không phải bằng chứng đầy đủ.

## 19. Những lỗi thường gặp khi kiểm tra trạng thái

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| OCSP responder timeout | DNS, route, firewall, proxy, responder lỗi | Kết nối từ đúng validator, HTTP status, telemetry responder |
| OCSP trả unknown | Responder không biết CertID, sai issuer/serial hoặc chưa đồng bộ | CertID, issuer hash, phạm vi responder và dữ liệu CA |
| OCSP trả revoked cho chứng thư đang sử dụng | Chứng thư đã thu hồi, lỗi đồng bộ hoặc nhầm certificate | Serial/issuer, revocationTime, nguồn dữ liệu và change ticket |
| Response ký không hợp lệ | Sai signer, sai chain/EKU hoặc dữ liệu bị thay | Chứng thư responder, OCSP signature, quyền ủy nhiệm |
| OCSP good nhưng client TLS vẫn lỗi | Hostname, trust anchor, expiry, EKU hoặc handshake không hợp lệ | Tách revocation khỏi path/hostname validation |
| CRL không tải được | CDP sai, firewall chặn, proxy lỗi hoặc hạ tầng chưa xuất CRL | URL, DNS, quyền truy cập, trạng thái endpoint |
| CRL đã quá hạn cập nhật | CA publishing thất bại hoặc cache sai | thisUpdate/nextUpdate, CRL Number, lịch phát hành |
| Có serial trong CRL nhưng hệ thống vẫn allow | Không bật kiểm tra, dùng dữ liệu khác hoặc soft-fail sai | Client policy, logs, nguồn CRL thực sự được dùng |
| Chỉ một số client báo revoked | Khác trust store, cache, profile hoặc endpoint kiểm tra | Client version/policy, thời điểm, chain, nguồn status |
| Bật Must-Staple rồi nhiều client lỗi | Stapling không ổn định hoặc response hết hạn | Staple freshness, TLS feature support, edge replicas |
| EAP-TLS/VPN bị lỗi hàng loạt | RADIUS/gateway không truy cập được responder/CRL | PKI dependency, fail mode và đường truy cập trước tunnel |
| Thu hồi chứng thư nhưng phiên đang mở vẫn tồn tại | TLS session hoặc authorization chưa được đánh giá lại | Thời hạn phiên, reauthentication/revocation và policy ứng dụng |

### 19.1. “OCSP good nhưng browser báo nguy hiểm”

Không nên tắt cảnh báo browser chỉ vì OCSP good. Cần kiểm tra **SAN, hostname, trust store, chữ ký, thuật toán, thời gian và chính sách của browser**. OCSP là một dữ liệu trạng thái, không có quyền ghi đè các lỗi khác.

### 19.2. “Không tải được CRL nhưng ứng dụng vẫn kết nối”

Đây có thể là **soft-fail**, sử dụng cache vẫn hợp lệ hoặc thực tế ứng dụng chưa bật kiểm tra CRL. Phải xác minh chính xác **cơ chế nào đã dẫn tới allow** trước khi đưa kết luận bảo mật.

### 19.3. “Đã revoke nhưng một số client vẫn cho phép”

Những nguyên nhân cần điều tra:

- Client không bật revocation checking cho loại kết nối đó.
- Client đang sử dụng CRL hoặc OCSP response **còn nằm trong cửa sổ cache**.
- Responder hoặc cache của một site chưa nhận trạng thái mới.
- Certificate bị dùng ở endpoint khác, với chain hoặc serial khác dự kiến.
- Client soft-fail do không thể truy cập nguồn trạng thái.
- Phiên TLS/mTLS đã được thiết lập từ trước chưa bị chấm dứt hoặc kiểm tra lại.

Việc thu hồi chứng thư **không nhất thiết tự cắt mọi kết nối đã được thiết lập**. Cần phân biệt thay đổi khả năng xác thực **phiên mới** với việc chấm dứt **phiên cũ** theo quy trình ứng phó.

## 20. Logging và giám sát CRL/OCSP

Để biết một biện pháp revocation hoạt động, SOC/NOC/PKI cần thấy cả **tình trạng của nguồn dữ liệu** và **quyết định của client**.

| Nhóm chỉ số | Ví dụ cần theo dõi | Vì sao hữu ích |
| --- | --- | --- |
| CRL publication | Lần phát hành cuối, nextUpdate, CRL Number, lỗi ký/xuất | Tránh danh sách stale |
| CRL distribution | HTTP availability, latency, kích thước và lỗi tải | Kiểm tra đường client → CDP |
| OCSP responder | Good/revoked/unknown, error rate, timeout, CPU, cache hit | Phát hiện lỗi responder hoặc dữ liệu |
| OCSP freshness | thisUpdate, nextUpdate, thời gian còn lại | Tránh dùng response quá hạn |
| OCSP stapling | Staple present/valid, refresh failure, edge coverage | Biết proxy/CDN có làm mới response không |
| Client validation | allow/deny theo lý do, trust/hostname/revocation | Phân biệt sai CA với revoked |
| VPN/RADIUS/mTLS | Số phiên lỗi vì nguồn trạng thái, certificate serial/issuer | Khoanh vùng tác động xác thực |
| PKI lifecycle | Key compromise, CA rollover, serial revoked, change ticket | Phân tích nguyên nhân và thu hồi |
| Service health | TLS handshake failure, login success, business availability | Đánh giá bảo mật và độ sẵn sàng cùng lúc |

### 20.1. Log giả lập

~~~json
{
  "timestamp": "2026-11-28T15:40:00+07:00",
  "environment": "synthetic-training",
  "service": "admin-vpn-gateway",
  "verifier": "vpn-certificate-validator",
  "certificate": {
    "issuer": "Lab Issuing CA",
    "serial": "0A1F22",
    "fingerprint": "synthetic-fingerprint-not-a-real-certificate"
  },
  "certificate_path_validation": "pass",
  "revocation_source": "ocsp",
  "ocsp_response_signature": "valid",
  "ocsp_certificate_status": "revoked",
  "ocsp_revocation_time": "2026-11-28T14:55:00+07:00",
  "freshness": "acceptable",
  "policy_decision": "deny",
  "policy_rule": "vpn-client-cert-revoked-deny",
  "note": "Dữ liệu học tập, không phải sự kiện thật"
}
~~~

Log cần phân biệt rõ **dữ liệu trạng thái được xác minh** và **quyết định từ chối**. Nếu một OCSP fetch timeout dẫn đến soft-fail, không được ghi **ocsp_certificate_status: good** vì responder chưa xác nhận điều đó.

### 20.2. Dữ liệu nhạy cảm

Thông tin serial, issuer, định danh thiết bị hoặc thông tin xác thực có thể liên quan cá nhân/tài sản. Chỉ lưu dữ liệu cần thiết, quản lý retention và RBAC log. Không ghi **private key, token, mật khẩu, OTP** hoặc toàn bộ nội dung lưu lượng người dùng để chứng minh OCSP/CRL hoạt động.

## 21. Quy trình phản ứng khi chứng thư hoặc khóa bị xâm phạm

### Giai đoạn 1 – Xác định phạm vi và bằng chứng

1. Ghi serial, issuer, SAN, chủ sở hữu tài sản, vị trí sử dụng private key và nơi chứng thư được trình bày.
2. Xác định phạm vi tác động: **một leaf**, một nhóm chứng thư client hay cả **issuing CA**.
3. Bảo toàn log truy cập, cấp phát chứng thư, deployment và sự kiện nghi lộ khóa.
4. Kiểm tra ai có quyền thao tác CA, responder, HSM/KMS và kho secret.
5. Xác định các ứng dụng/client **thực sự kiểm tra** CRL/OCSP, chứ không chỉ CA có hỗ trợ.

### Giai đoạn 2 – Giảm thiểu và thu hồi

1. Với leaf private key bị lộ, chuẩn bị **cặp khóa mới** và chứng thư mới phù hợp.
2. Thu hồi chứng thư cũ qua CA **theo quyền và quy trình chính thức**.
3. Xác minh trạng thái revoked đã được phản ánh ở responder/CRL và có chữ ký/độ mới hợp lệ.
4. Thay khóa/chứng thư ở mọi endpoint liên quan, kiểm tra chứng thư đang được phục vụ thật.
5. Nếu có quyền người dùng hoặc phiên đặc quyền, thực hiện **account/session/token revocation** riêng theo IAM.
6. Khi CA bị xâm nhập, kích hoạt kế hoạch PKI cấp CA: thay/thu hồi CA, sửa trust stores, cấp lại chứng thư và phối hợp những phụ thuộc quy mô lớn.

**Không tự giả định revoke intermediate CA là công việc giống revoke leaf.** Các client có thể kiểm tra trạng thái CA theo profile khác nhau, và thay đổi trust anchor/certificate path có thể gây gián đoạn rộng.

### Giai đoạn 3 – Xác minh sau hành động

- Client lab kiểm tra chứng thư cũ **bị từ chối** theo chính sách.
- Chứng thư mới với đúng danh tính **được chấp nhận**.
- Những endpoint phía CDN/LB/reverse proxy đều đã đổi chứng thư và reload.
- Responder, CRL và OCSP staple còn mới và truy cập được.
- VPN, RADIUS/EAP-TLS, API mTLS và cloud workloads không bị ngắt ngoài dự kiến.
- Log/phát hiện không còn thấy private key cũ được triển khai hoặc sử dụng sai.

### Giai đoạn 4 – Rút kinh nghiệm

Rà soát bảo vệ private key, quyền cấp phát, thời hạn chứng thư, quá trình ký CRL/OCSP, độ sẵn sàng responder, SLA thu hồi và kiểm thử toàn tuyến. Ghi lại **khoảng thời gian từ lúc quyết định revoke tới lúc client thực sự từ chối**.

## 22. Kiểm thử trong lab an toàn

Các phép thử chỉ thực hiện với **CA, OCSP responder, CRL, TLS endpoint và client do tổ chức sở hữu hoặc được cấp phép**. Không tự làm gián đoạn OCSP/CRL công khai, không thử gây outage trên mạng bên thứ ba, không yêu cầu người dùng thật kết nối tới endpoint giả.

### 22.1. Ma trận kiểm thử

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T-01 | Leaf được CA lab cấp, chưa revoked, chain/hostname đúng | Kết nối hợp lệ theo policy |
| T-02 | Leaf đã được CA lab thu hồi, OCSP báo revoked | Client từ chối, ghi đúng nguồn/trạng thái |
| T-03 | CRL lab còn hiệu lực chứa serial của leaf | CRL-based check từ chối chứng thư |
| T-04 | CRL còn hiệu lực không liệt kê leaf, đúng issuer/scope | Revocation check đạt trong phạm vi CRL; vẫn kiểm tra path/hostname |
| T-05 | CRL hết hạn theo freshness policy | Không tự gán not revoked; áp dụng fail mode |
| T-06 | CRL đúng chữ ký nhưng của issuer khác | Không dùng sai CRL để kết luận |
| T-07 | OCSP responder trả unknown | Client xử lý riêng, không coi là good |
| T-08 | Response OCSP bị sửa sau khi ký trong lab | Validator phát hiện chữ ký sai |
| T-09 | OCSP response good nhưng quá cũ theo policy | Không dùng như trạng thái mới |
| T-10 | OCSP good nhưng leaf sai hostname | Client vẫn từ chối vì hostname mismatch |
| T-11 | OCSP good nhưng leaf được CA không tin cấp | Client vẫn từ chối unknown CA |
| T-12 | OCSP responder offline **trong lab cô lập** | Hard/soft fail và giám sát đúng thiết kế |
| T-13 | Edge có OCSP stapling response hợp lệ | Client hỗ trợ nhận và kiểm tra response phù hợp |
| T-14 | Edge có staple hết hạn hoặc sai CertID | Client kiểm tra đúng và từ chối theo policy hỗ trợ |
| T-15 | Gateway mTLS xác minh chứng thư client revoked | Client bị từ chối, session cũ xử lý theo runbook |
| T-16 | RADIUS/EAP-TLS kiểm tra CRL/OCSP không truy cập được | Lỗi xác thực/khôi phục đúng fail mode đã duyệt |
| T-17 | CRL base + delta trong PKI lab hỗ trợ | Validator kết hợp đúng dữ liệu và scope |
| T-18 | Hai edge replicas dùng trạng thái staple khác nhau | Monitoring phát hiện lệch trạng thái và làm mới |

### 22.2. Bằng chứng cần lưu

- Phiên bản CA/PKI lab, serial và issuer của mỗi leaf.
- Trust store và chính sách xác minh thực tế của client.
- CRL/OCSP đã được ký, thông tin thisUpdate/nextUpdate.
- Trạng thái TLS path/hostname validation tách riêng trạng thái thu hồi.
- Thông điệp policy allow/deny, log từ gateway/server/client.
- Nơi dữ liệu được cache và thời gian thay đổi có hiệu lực.
- Kết quả dịch vụ hợp lệ sau siết policy và phương án rollback.

**Kết quả chỉ đạt khi cả positive test và negative test đúng**, không gây gián đoạn các kết nối hợp lệ ngoài phạm vi lab.

## 23. Tình huống tổng hợp: VPN không đăng nhập được sau đợt đổi CA

Một doanh nghiệp sử dụng chứng thư client cho VPN quản trị. Sau khi thay intermediate CA và di chuyển dịch vụ OCSP, nhiều nhân viên không đăng nhập được VPN. Gateway hiển thị lỗi **certificate status unavailable**; một số người kết nối qua gateway dự phòng vẫn thành công.

### 23.1. Những giả thuyết cần xem xét

1. **Đường mạng:** gateway chính không truy cập được OCSP responder mới do ACL/proxy/DNS.
2. **Trust:** gateway chưa tin chuỗi CA hoặc responder delegated signer mới.
3. **Dữ liệu:** CertID/issuer mismatch, response chưa cập nhật hoặc trả unknown.
4. **Freshness:** response được cache tại gateway chính đã hết hạn, gateway phụ còn cache khác.
5. **Thời gian:** đồng hồ gateway sai khiến OCSP response bị coi là chưa hợp lệ hoặc stale.
6. **Policy:** gateway chính hard-fail, gateway phụ soft-fail hoặc chạy phiên bản chính sách khác.
7. **Chứng thư client:** một số thiết bị thật sự dùng chứng thư hết hạn, bị thu hồi hoặc sai chain.

### 23.2. Thứ tự điều tra

1. Ghi thời gian bắt đầu, gateway, user/session lab, issuer/serial, lỗi và phiên bản policy.
2. Kiểm tra trust anchor, issuing CA và quyền ký của responder.
3. Kiểm tra độ mới, trạng thái và chữ ký response tương ứng chứng thư.
4. Kiểm tra DNS, firewall, proxy và đường từ từng gateway tới responder.
5. Đối chiếu khác biệt cấu hình giữa gateway chính và dự phòng.
6. Thử một chứng thư lab chưa revoked và một chứng thư lab revoked, kiểm tra kết quả trước/sau sửa.
7. Giám sát VPN login success và tình trạng người dùng hợp lệ.

### 23.3. Quyết định giảm thiểu

Nếu nguồn lỗi là firewall chặn OCSP URL đã được phê duyệt, chỉnh đúng rule có kiểm soát. Nếu responder ký sai hoặc không được gateway tin, sửa cấu hình responder/CA chain. Nếu client cert revoked thật, **không biến nó thành good** để phục hồi dịch vụ.

Không nên giải quyết bằng cách **tắt mọi revocation checking cho nhóm quản trị** khi chưa được đánh giá và phê duyệt. Thay vào đó, dùng kế hoạch redundancy/rollback đã kiểm thử và giới hạn thời gian biện pháp khẩn cấp nếu thật sự cần.

### 23.4. Xác nhận khôi phục

- Chứng thư hợp lệ đăng nhập đúng quyền.
- Chứng thư revoked vẫn bị từ chối.
- Hai gateway nhất quán policy và responder/trust store.
- Không còn lỗi status unavailable không được giải thích.
- Session và group authorization vẫn hoạt động theo yêu cầu bảo mật.

**Bài học:** Độ sẵn sàng của PKI revocation endpoints là một phần của thiết kế VPN; bảo mật phải được xác minh bằng **cả chặn chứng thư bị thu hồi lẫn duy trì dịch vụ hợp lệ**.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao rủi ro | Cách làm đúng |
| --- | --- | --- |
| “Chưa hết hạn nghĩa là chưa bị thu hồi” | Revocation xảy ra trước Not After | Kiểm tra status theo chính sách |
| “OCSP good chứng minh website an toàn” | Good không kiểm tra hostname, key compromise hoặc mã độc | Path/hostname/TLS/app security độc lập |
| “Không có serial trong mọi CRL thì good” | CRL phải đúng issuer, scope, chữ ký và freshness | Xác minh chính xác CRL áp dụng |
| “OCSP successful nghĩa là certificate good” | Protocol response status khác certificate status | Kiểm tra SingleResponse và trạng thái thực |
| “Có URL OCSP/CDP là ứng dụng đã kiểm tra” | URL chỉ là metadata; client có thể không gọi | Kiểm tra tính năng và log validator |
| “CRL tải qua HTTPS là khỏi cần chữ ký CRL” | Kênh vận chuyển không chứng minh thẩm quyền CRL | Kiểm tra chữ ký và scope |
| “Một phản hồi OCSP có chữ ký dùng mãi được” | Revocation thay đổi theo thời gian | thisUpdate/nextUpdate/cache policy |
| “Hard-fail luôn tốt hơn mà không cần HA” | Responder outage có thể làm ngắt VPN/Wi-Fi | Kết hợp nghiêm ngặt và availability plan |
| “Soft-fail có nghĩa revoked được phép” | Trộn lỗi truy vấn với trạng thái revoked đã xác thực | Phân biệt kết quả chứng cứ và fail mode |
| “Stapling bảo đảm mọi client xác minh” | Hỗ trợ/thực thi khác theo client, TLS version | Kiểm tra client và telemetry thực tế |
| “Must-Staple cứ bật là xong” | Staple không mới có thể làm mất kết nối | Automation, HA, test support trước rollout |
| “Revoke cert tự cắt mọi phiên cũ” | Session có thể còn hiệu lực tới khi reauth | Quản lý session/token riêng |
| “Thu hồi CA giống thu hồi leaf” | Tác động trust chain rộng và khác chính sách | Kế hoạch CA incident, trust store rollout |
| “OCSP timeout thì ghi status good” | Không có bằng chứng trạng thái | Log not-checked/unavailable đúng sự thật |
| “Chỉ kiểm tra từ máy quản trị là đủ” | Client/Gateway ở zone khác có đường mạng khác | Kiểm tra từ từng điểm thực thi thật |
| “Thiết bị chỉ dùng TLS nên chẳng cần firewall/DNS/IAM” | TLS không cấp quyền hay bảo vệ mọi lớp | Defense in depth theo module |

## 25. Câu hỏi tự kiểm tra

### Câu hỏi 1

Một chứng thư còn hiệu lực 90 ngày nhưng bị CA thu hồi hôm nay. Kiểm tra Not After có phát hiện được vấn đề không?

**Gợi ý:** Không. Not After chỉ giới hạn thời gian; cần revocation evidence hoặc cơ chế quản trị tương ứng.

### Câu hỏi 2

Vì sao không thể dùng một CRL của CA X để kết luận trạng thái của chứng thư được CA Y cấp?

**Gợi ý:** CRL có issuer, quyền ký và phạm vi áp dụng; serial chỉ là một phần của định danh.

### Câu hỏi 3

Ba trạng thái OCSP good, revoked, unknown khác nhau thế nào? Tại sao good không chứng minh chứng thư đã được cấp hợp lệ?

**Gợi ý:** OCSP báo trạng thái thu hồi theo responder; client vẫn cần path/hostname validation và chính sách.

### Câu hỏi 4

OCSP protocol response successful khác certificate status good như thế nào?

**Gợi ý:** một trạng thái mô tả request/response xử lý được; trạng thái khác mô tả chứng thư cụ thể.

### Câu hỏi 5

Một response OCSP ký đúng nhưng nextUpdate đã qua. Có được dùng như response mới vô thời hạn không?

**Gợi ý:** Không. Cần kiểm tra thời gian, cache policy và fail mode.

### Câu hỏi 6

OCSP stapling giúp cải thiện riêng tư và hiệu năng như thế nào? Nó có tự sửa chứng thư bị revoked không?

**Gợi ý:** server cung cấp response đã ký, giảm truy vấn trực tiếp từ client; response revoked vẫn phải xử lý.

### Câu hỏi 7

Nếu revocation endpoint không thể truy cập, soft-fail và hard-fail có đánh đổi gì?

**Gợi ý:** bảo mật trước thông tin trạng thái thiếu so với tính sẵn sàng của dịch vụ.

### Câu hỏi 8

Vì sao VPN gateway và RADIUS server phải có đường tới CRL/OCSP phù hợp ngay cả khi mạng người dùng chưa hoạt động?

**Gợi ý:** certificate validation có thể diễn ra trước khi VPN tunnel hoặc quyền Wi-Fi hình thành.

### Câu hỏi 9

Đã revoke client certificate nhưng API mTLS vẫn có phiên đang mở. Cần làm gì ngoài phát hành trạng thái revoked?

**Gợi ý:** thu hồi/reauthorize phiên và quyền ứng dụng theo quy trình; chứng thư bị thu hồi không tự cắt mọi kết nối.

### Câu hỏi 10

Một leaf được CA tin ký, SAN đúng và OCSP good nhưng private key server đã bị lộ. Có thể kết luận server an toàn không?

**Gợi ý:** Không. OCSP good phản ánh trạng thái theo thông tin responder; cần incident response, thay khóa và revoke khi phù hợp.

### Bài tập thiết kế

Một doanh nghiệp có **HTTPS public API**, **admin VPN**, **Wi-Fi Enterprise EAP-TLS**, **service-to-service mTLS** và một **PKI nội bộ**. Hãy:

1. Vẽ sơ đồ CA, issuing CA, CRL distribution, OCSP responder và các bên thực hiện certificate validation.
2. Lập ma trận **dịch vụ → loại chứng thư → ai kiểm tra → nguồn trạng thái → fail mode**.
3. Phân biệt **revoked, unknown, stale, not-checked và good** trong log của hệ thống.
4. Đề xuất chu kỳ phát hành, monitoring và cache/freshness cho CRL hoặc OCSP theo mức rủi ro của từng dịch vụ.
5. Giải thích đường mạng cần mở trong các zone, đặc biệt khi VPN chưa thiết lập và thiết bị Wi-Fi chưa có quyền truy cập.
6. Thiết kế ít nhất **sáu positive/negative tests**, gồm cert revoked, CRL sai issuer, OCSP unknown, responder unavailable, stapling stale và cert sai hostname.
7. Viết runbook thu hồi private key của một VPN admin và cách xác minh rằng chứng thư cũ bị chặn **cả trên gateway chính và gateway dự phòng**.
8. Nêu vì sao OCSP/CRL không thay cho **TLS hostname validation, IAM, phân quyền ứng dụng, firewall, IDS/IPS và bảo vệ DNS**.

**Tiêu chí đạt:** hệ thống chỉ dùng dữ liệu trạng thái **có nguồn tin cậy, đúng chứng thư, đúng phạm vi và đủ mới**, có hành vi minh bạch khi nguồn trạng thái không khả dụng và không đánh đổi hoàn toàn kết nối hợp lệ.

## 26. Những điều cần ghi nhớ

- **CRL và OCSP cung cấp bằng chứng về trạng thái thu hồi**, là một phần của kiểm tra chứng thư bên cạnh trust chain, SAN/hostname, EKU, thời hạn và handshake.
- **CRL là danh sách có chữ ký theo issuer/scope**, còn **OCSP trả trạng thái cho CertID**; cả hai đòi hỏi xác minh chữ ký, thẩm quyền và độ mới.
- **OCSP good không chứng minh certificate được cấp đúng, private key không lộ hoặc website an toàn**; revoked/unknown phải được phân biệt rõ.
- **OCSP response successful khác good**, và một CRL không có serial chỉ có ý nghĩa khi CRL áp dụng đúng chứng thư và đủ mới.
- **OCSP stapling giảm nhu cầu client hỏi responder**, nhưng tính năng, Must-Staple và cách client thực thi có giới hạn khác nhau.
- **Soft-fail/hard-fail là quyết định bảo mật lẫn availability**; không tự chuyển trạng thái unavailable thành good.
- **PKI endpoints phải được thiết kế cùng firewall, mạng phân đoạn, VPN, RADIUS/EAP và cloud**, vì certificate validation phụ thuộc đường mạng tại điểm xác minh.
- **Thu hồi không tự chấm dứt mọi phiên đang mở**: cần quản lý session/token, quyền truy cập và quy trình thay khóa riêng.
- **Giám sát CRL, OCSP, cache, chữ ký, responder, TLS handshake và kết quả ứng dụng**; kiểm thử cả chứng thư hợp lệ lẫn chứng thư bị thu hồi trong lab được phép.
