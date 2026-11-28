# Certificate chain và xác minh máy chủ

Khi một ứng dụng kết nối đến dịch vụ HTTPS, VPN hoặc API qua TLS, việc **mã hóa lưu lượng** chỉ có ý nghĩa bảo mật mong muốn nếu ứng dụng còn xác minh rằng **mình đang trao đổi với đúng máy chủ**. Nếu bỏ qua xác minh danh tính, một đối tượng trung gian có thể thiết lập một kết nối mã hóa khác với client và khiến người dùng tưởng rằng dữ liệu đang được gửi tới dịch vụ thật.

**Certificate chain** (*chuỗi chứng thư số*) là tập hợp chứng thư X.509 liên kết chứng thư của máy chủ với một **điểm tin cậy (trust anchor)** thông qua chữ ký số và các ràng buộc của hạ tầng khóa công khai (**PKI**). **Server certificate validation** là quy trình client kiểm tra chuỗi đó, đồng thời kiểm tra tên máy chủ, thời hạn, mục đích sử dụng khóa và những điều kiện bảo mật liên quan.

Trong chương **TLS và bảo mật kênh truyền** của module **SECURITY_NETWORK_SECURITY**, đây là lớp phòng vệ thiết yếu khi xây dựng HTTPS/API an toàn, VPN, kết nối ứng dụng giữa các trust zone, dịch vụ DNS mã hóa, quản trị cloud và Wi-Fi Enterprise. Certificate chain giúp thiết lập **danh tính đầu bên kia của kênh TLS**, nhưng không thay thế firewall, phân quyền, IDS/IPS, xác thực người dùng hoặc kiểm tra tính an toàn của nội dung ứng dụng.

> **Nguyên tắc then chốt:** Có biểu tượng ổ khóa, có chứng thư hoặc kết nối TLS được mã hóa **chưa đủ** để kết luận client đang kết nối đúng máy chủ. Phải kiểm tra **đúng danh tính được yêu cầu** và chuỗi tin cậy hợp lệ theo chính sách của client.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác biệt giữa **leaf/server certificate**, **intermediate CA**, **root CA** và **trust anchor**.
2. Mô tả cách chứng thư X.509, chữ ký số và public/private key liên kết thành **certificate chain**.
3. Phân biệt **xây dựng đường chứng thực (path building)** với **kiểm tra đường chứng thực (path validation)**.
4. Nêu những bước client cần kiểm tra: CA tin cậy, chữ ký, Basic Constraints, Key Usage, EKU, thời hạn và SAN/hostname.
5. Giải thích vai trò **Server Name Indication (SNI)** và thông điệp Certificate trong TLS handshake; phân biệt chúng với việc xác minh danh tính.
6. Nhận biết các lỗi **unknown CA**, **hostname mismatch**, **expired certificate**, **missing intermediate** và sai mục đích chứng thư.
7. Hiểu giới hạn của **CRL/OCSP**, **Certificate Transparency (CT)** và cách tổ chức quản trị thời hạn, thu hồi, private key.
8. Kiểm tra dịch vụ và chứng thư trong lab bằng công cụ đọc cấu hình/chứng thư, không tắt xác minh để che lỗi.
9. Thiết kế và kiểm thử an toàn TLS ở reverse proxy, API, dịch vụ nội bộ, VPN và Wi-Fi 802.1X.

## 2. Bài toán: mã hóa nhưng kết nối nhầm máy chủ

Giả sử ứng dụng đặt hàng muốn gửi thông tin tới **api.company.example**. TLS có thể mã hóa dữ liệu giữa client với một điểm cuối mạng, nhưng client còn cần kiểm tra:

- Điểm cuối đó có **chứng thư được một nguồn tin cậy chấp nhận** hay không?
- Chứng thư có cho phép nhận diện **api.company.example** hay không?
- Chứng thư còn hiệu lực, có đúng mục đích **TLS server authentication** và đường CA có hợp lệ không?
- Máy chủ có chứng minh đang nắm **private key tương ứng** trong TLS handshake hay không?

Nếu một thiết bị trung gian đưa client tới máy chủ khác, máy chủ đó có thể sở hữu chứng thư HTTPS **hợp lệ cho một domain khác**. Việc chứng thư được CA công khai ký không tự khiến nó hợp lệ cho **api.company.example**. **Hostname validation** chính là bước ngăn nhầm lẫn này.

~~~mermaid
flowchart TD
    U["Client muốn kết nối api.company.example"] --> T["Thiết lập TLS tới endpoint trên mạng"]
    T --> C["Nhận chứng thư máy chủ và intermediate nếu có"]
    C --> P["Xây dựng và xác minh đường chứng thực đến trust anchor"]
    P --> N["Đối chiếu SAN với tên máy chủ client yêu cầu"]
    N --> K["Xác thực bằng chứng sở hữu khóa trong handshake"]
    K --> D{"Toàn bộ bước bắt buộc đều hợp lệ?"}
    D -->|Có| OK["Tiếp tục gửi dữ liệu ứng dụng qua TLS"]
    D -->|Không| NO["Dừng kết nối và báo lỗi xác thực"]
~~~

Sơ đồ mang tính khái niệm: thứ tự kiểm tra và điểm báo lỗi có thể khác nhau theo thư viện TLS. Điều quan trọng là **không được bỏ qua một điều kiện thất bại bắt buộc chỉ vì những điều kiện khác đã đạt**.

### 2.1. Ba thuộc tính cần phân biệt

| Thuộc tính | Ví dụ câu hỏi | Cơ chế liên quan |
| --- | --- | --- |
| **Confidentiality** | Người nghe lén có đọc được dữ liệu ứng dụng không? | Mã hóa phiên TLS với bộ mật mã thích hợp |
| **Integrity** | Dữ liệu được truyền có bị sửa mà không bị phát hiện không? | Cơ chế bảo vệ toàn vẹn của phiên TLS |
| **Peer authentication** | Client có đang nói chuyện với đúng server không? | Chứng thư, chuỗi tin cậy, xác minh hostname và handshake |

Một kết nối có thể sử dụng cơ chế mã hóa mạnh nhưng vẫn **xác thực sai endpoint** nếu client tắt việc xác minh chứng thư hoặc chấp nhận chứng thư không khớp tên.

## 3. Chứng thư X.509 và các thành phần PKI

### 3.1. Leaf / end-entity certificate

**Leaf certificate** là chứng thư cuối chuỗi, thường được cấp cho một máy chủ, dịch vụ hoặc tên miền. Nó chứa **public key**, danh tính và các thuộc tính hạn chế sử dụng. Private key tương ứng được giữ bí mật ở máy chủ hoặc hệ thống quản lý khóa.

Ví dụ HTTPS cho **api.company.example** có thể dùng một leaf certificate trong đó phần **Subject Alternative Name (SAN)** chứa tên DNS **api.company.example**.

**Chứng thư công khai public key; không công bố private key.** Private key có thể nằm trong HSM, KMS hoặc kho khóa được quản lý theo yêu cầu tổ chức, nhưng không được xuất vào log, tài liệu hay repository.

### 3.2. Intermediate Certificate Authority

**Intermediate CA** là CA trung gian được một CA khác ký và được phép cấp/ký chứng thư trong phạm vi ràng buộc cho phép. Việc dùng intermediate giúp CA vận hành, thay đổi và giới hạn vai trò khóa ký mà không phải luôn dùng private key của root.

Một root có thể ký nhiều intermediate; một intermediate có thể ký leaf. Không phải mọi hệ thống chỉ có đúng một intermediate: đường chứng thực có thể gồm nhiều cấp và có nhiều đường hợp lệ khác nhau.

### 3.3. Root CA và trust anchor

**Root CA** thường có chứng thư tự ký (*self-signed*). Nhưng **tính tự ký không tự khiến root đáng tin**. Client tin vào root vì khóa/chứng thư đó đã được đưa vào **trust store** hoặc cấu hình trust anchor qua một kênh quản trị được tin cậy.

**Trust anchor** là thông tin tin cậy ban đầu của validator; trong triển khai phổ biến nó được biểu diễn bằng root certificate, nhưng về mặt mô hình xác thực không nhất thiết mọi trust anchor phải xuất hiện và được xử lý như một chứng thư root được server gửi tới.

### 3.4. Chuỗi minh họa

~~~mermaid
flowchart TD
    ROOT["Root CA / trust anchor trong trust store client"]
    ROOT -->|"Ký chứng thư CA"| INT["Intermediate CA: quyền ký trong phạm vi cho phép"]
    INT -->|"Ký leaf certificate"| LEAF["Leaf: api.company.example + public key"]
    LEAF -->|"Máy chủ chứng minh sở hữu private key"| TLS["TLS endpoint"]
    CLIENT["TLS client"] -. "Kiểm tra chữ ký và ràng buộc từng cấp" .-> ROOT
    CLIENT -. "Đối chiếu SAN/hostname và handshake" .-> LEAF
~~~

Nếu server gửi **leaf + intermediate**, client thường dùng trust store của mình để nối tới root. **Server không cần và không nên xem việc gửi root là điều kiện khiến client tin tưởng**; một root do server cung cấp không thể tự cấp quyền tin cậy cho chính nó.

## 4. Những trường X.509 cần hiểu

| Trường / extension | Ý nghĩa | Vai trò khi xác minh server |
| --- | --- | --- |
| **Subject** | Thông tin đối tượng được chứng nhận | Không thay thế SAN trong cách xác minh danh tính DNS hiện đại |
| **Issuer** | Danh tính bên phát hành chứng thư | Hỗ trợ tìm CA cấp trên, chưa đủ chứng minh đường tin cậy |
| **Subject Public Key Info** | Public key và thuật toán tương ứng | Dùng trong xác minh chữ ký/handshake theo vai trò |
| **Serial Number** | Số định danh chứng thư do CA cấp | Hữu ích cho thu hồi và nhật ký |
| **Not Before / Not After** | Khoảng thời gian có hiệu lực | Client kiểm tra theo thời điểm đáng tin cậy |
| **SAN (Subject Alternative Name)** | DNS names, IP addresses hoặc danh tính khác | Dữ liệu chính để kiểm tra hostname/IP theo giao thức |
| **Basic Constraints** | Phân biệt CA và end entity, có thể giới hạn độ sâu CA | Intermediate ký chứng thư cần có quyền CA phù hợp |
| **Key Usage** | Các mục đích được phép dùng khóa, ví dụ digitalSignature, keyCertSign | Kiểm tra quyền sử dụng khóa trong chuỗi |
| **Extended Key Usage (EKU)** | Mục đích cụ thể, ví dụ serverAuth, clientAuth | Leaf dùng cho TLS server cần phù hợp mục đích server authentication theo chính sách |
| **Authority/Subject Key Identifier** | Hỗ trợ nhận diện khóa và xây dựng đường chứng thực | Không tự tạo niềm tin nếu chữ ký hoặc CA không hợp lệ |
| **AIA / CRL Distribution Points** | Thông tin hỗ trợ lấy intermediate hoặc trạng thái thu hồi | Khả năng truy cập và cách xử lý tùy client/PKI |
| **Name Constraints / Policy Constraints** | Giới hạn phạm vi danh tính hoặc chính sách CA | Phải được tôn trọng nếu áp dụng và được hỗ trợ theo chuẩn |

**Issuer/Subject giống nhau không đồng nghĩa chữ ký hợp lệ.** Validator phải dùng khóa công khai thích hợp để xác minh chữ ký và tuân thủ những điều kiện trong chuỗi.

### 4.1. Basic Constraints và Key Usage

Một leaf certificate cấp cho website không được mặc nhiên dùng làm **CA phát hành chứng thư khác**. Những intermediate cần có Basic Constraints cho phép vai trò CA, và Key Usage cho phép **keyCertSign** khi extension áp dụng.

Đối với leaf TLS server, một cặp khóa có thể được dùng để chứng minh sở hữu private key thông qua handshake. Thuật toán và mục đích khóa phải tương thích với giao thức, certificate profile và chính sách xác thực.

### 4.2. EKU serverAuth và clientAuth

- **serverAuth**: thường chỉ ra chứng thư được dự định dùng để xác thực TLS server.
- **clientAuth**: thường liên quan chứng thư dùng để xác thực TLS client trong **mutual TLS (mTLS)**.

Một chứng thư chỉ dành cho client authentication **không nên được chấp nhận làm chứng thư server** nếu chính sách yêu cầu serverAuth. Chi tiết đánh giá EKU còn phụ thuộc phần mở rộng thực tế và rules của thư viện/chính sách.

## 5. Xây dựng đường chứng thực (path building)

**Path building** là quá trình tìm một chuỗi phù hợp từ leaf đến trust anchor. Client thường có leaf và các intermediate server gửi, đồng thời có thể sở hữu một số intermediate trong cache/store hoặc tải thêm khi nền tảng cho phép.

Ví dụ:

1. Nhận chứng thư leaf **api.company.example**.
2. Xác định CA đã ký leaf từ issuer/identifier và dữ liệu chữ ký.
3. Tìm intermediate certificate tương ứng trong chuỗi server gửi hoặc nguồn khác được hỗ trợ.
4. Tiếp tục cho tới trust anchor phù hợp có trong trust store.
5. Đưa candidate path qua quá trình **path validation**.

Không phải mọi client tự tải intermediate qua AIA. Một server thiếu intermediate có thể vẫn hoạt động trên máy từng cache chứng thư đó, nhưng thất bại trên thiết bị sạch. Vì vậy phải kiểm thử từ **client chưa có cache** và nhiều hệ điều hành, không chỉ từ máy của quản trị viên.

### 5.1. Tại sao có nhiều đường chứng thực?

Một intermediate có thể tồn tại dưới những phiên bản chứng thư khác nhau hoặc được **cross-sign** để tạo các đường đến các trust anchor khác nhau. Validator có thể lựa chọn đường phù hợp với trust store, thuật toán, thời hạn và chính sách.

**Đường được chọn phụ thuộc implementation và trust store**; không nên giả định mọi client chọn cùng một đường chỉ vì server gửi cùng một tập chứng thư. Cần kiểm tra tác động khi CA thay đổi root/cross-sign hoặc chuyển chuỗi.

### 5.2. Chuỗi server gửi và chuỗi client tin khác nhau

Server thường gửi:

~~~text
Certificate 0: leaf cho api.company.example
Certificate 1: intermediate CA ký leaf
Certificate 2: intermediate cấp cao hơn (nếu cần)

Client trust store:
Trusted root CA hoặc trust anchor phù hợp
~~~

Root trong trust store của client mới là điểm neo tin cậy. **Tự thêm một chứng thư CA vào gói gửi từ server không khiến nó trở thành trusted CA**.

## 6. Kiểm tra đường chứng thực (path validation)

Một đường chứng thực chỉ được coi là hợp lệ khi vượt qua các điều kiện thích hợp, thường gồm:

1. **Trust anchor:** đường dẫn tới khóa/chứng thư root được client tin.
2. **Chữ ký:** chứng thư cấp dưới có chữ ký xác minh được bằng khóa hợp lệ của CA cấp trên.
3. **Chuỗi CA hợp lệ:** intermediate thực sự có quyền làm CA, cùng ràng buộc Key Usage, path length và name constraints nếu có.
4. **Thời hạn:** chứng thư liên quan có hiệu lực theo đồng hồ và quy tắc đánh giá.
5. **Thuật toán và kích thước khóa:** không dùng cơ chế bị chính sách client cấm hoặc không còn phù hợp.
6. **Mục đích sử dụng:** leaf và các ràng buộc liên quan phù hợp để xác thực TLS server.
7. **Danh tính endpoint:** tên DNS/IP mà client định kết nối phải khớp thông tin được chứng nhận theo tiêu chuẩn và quy tắc ứng dụng.
8. **Trạng thái thu hồi và chính sách nền tảng:** CRL/OCSP, CT hoặc các yêu cầu bổ sung khi được áp dụng.
9. **TLS proof of possession:** quá trình handshake phải chứng minh phía server nắm private key hợp lệ liên quan chứng thư.

Không có một “điểm số TLS” nào có thể thay thế các điều kiện bắt buộc. Một chứng thư vừa hết hạn vừa sai hostname không trở nên được phép dùng chỉ vì private key vẫn hoạt động.

### 6.1. Chữ ký số khác mã hóa phiên

**CA ký chứng thư** để chứng minh đã chứng nhận public key/danh tính theo chính sách cấp phát. **Server dùng private key** trong bước xác thực handshake phù hợp. Còn **khóa mã hóa dữ liệu ứng dụng** trong TLS hiện đại được thiết lập qua cơ chế trao đổi khóa, ví dụ (EC)DHE trong TLS 1.3.

**Không nên nói private key của chứng thư được dùng để mã hóa toàn bộ traffic HTTPS**. Việc ký chứng thư, xác thực phiên và mã hóa dữ liệu là các chức năng mật mã khác nhau.

## 7. SAN và hostname verification

**Subject Alternative Name (SAN)** là extension quan trọng nhất khi xác minh tên máy chủ TLS hiện đại. Trong một kết nối đến **api.company.example**, client cần kiểm tra chứng thư được cấp cho **chính tên đó** theo quy tắc matching của giao thức.

### 7.1. DNS name so với IP address

- Nếu kết nối theo **DNS hostname**, client cần đối chiếu tên với **dNSName SAN** theo quy tắc phù hợp.
- Nếu client định danh server bằng **IP literal**, cần đối chiếu với **iPAddress SAN** tương ứng; một dNSName chỉ tình cờ chứa chuỗi giống IP không mặc nhiên thay thế iPAddress.
- Đối với các định danh phức tạp như IDN/Unicode, cần chuẩn hóa theo quy tắc danh tính DNS được ứng dụng/hệ điều hành hỗ trợ trước khi so khớp.

Việc DNS trả về IP đúng hay sai **không thay thế hostname verification**. Dù bị dẫn tới IP khác, một server không sở hữu chứng thư hợp lệ cho hostname yêu cầu phải bị từ chối nếu policy xác thực còn nguyên vẹn.

### 7.2. Wildcard certificate

Ví dụ chứng thư có SAN **\*.company.example** có thể khớp với **api.company.example** theo cách so khớp wildcard DNS thông dụng, nhưng **không tự khớp**:

- **company.example** (tên ở mức cha).
- **internal.api.company.example** (nhiều nhãn DNS phía trước).
- Một địa chỉ IP bất kỳ.

Quy tắc wildcard có những ràng buộc từ chuẩn và chính sách triển khai, bao gồm vị trí wildcard và danh sách tên được phép. **Không nên coi wildcard là cách nhận diện “mọi tên con ở mọi độ sâu”**. Wildcard cũng mở rộng ảnh hưởng nếu private key bị lộ, vì khóa có thể phục vụ nhiều tên nằm trong phạm vi.

### 7.3. Subject Common Name (CN)

Trong cách xác thực HTTPS hiện đại, **SAN là nguồn danh tính cần dùng**. Một số thư viện/ứng dụng cũ từng fallback sang **Subject CN** nếu không có SAN, nhưng cách dựa vào CN là thực hành lỗi thời và không nên thiết kế chứng thư mới phụ thuộc vào fallback đó.

### 7.4. Ma trận hostname matching

| Tên client yêu cầu | SAN trong leaf | Kỳ vọng |
| --- | --- | --- |
| api.company.example | DNS:api.company.example | **Match** |
| api.company.example | DNS:web.company.example | **Mismatch** |
| admin.company.example | DNS:\*.company.example | **Match** theo wildcard một nhãn phù hợp |
| company.example | DNS:\*.company.example | **Mismatch** |
| v2.api.company.example | DNS:\*.company.example | **Mismatch** |
| 192.0.2.10 | IP:192.0.2.10 | **Match** theo iPAddress SAN |
| 192.0.2.10 | DNS:192.0.2.10 | **Không mặc nhiên hợp lệ** cho truy cập bằng IP |

Địa chỉ **192.0.2.10** thuộc dải TEST-NET dành cho tài liệu. Bảng chỉ mô tả hostname matching, **chưa** xét chữ ký, trust anchor, thời hạn và các điều kiện khác.

## 8. Trust store, CA công khai và private PKI

### 8.1. Public CA trust store

Trình duyệt và hệ điều hành thường có danh sách CA tin cậy theo chính sách riêng. Một CA có thể được một nền tảng tin nhưng không được nền tảng khác chấp nhận. Trust store và chương trình root CA cũng có thể cập nhật theo thời gian.

**Không được lấy việc chứng thư được một máy chấp nhận làm bằng chứng tất cả client đều chấp nhận.** Thiết bị cũ, container, JVM, appliance, mobile OS và browser có thể sử dụng trust store hoặc chính sách khác nhau.

### 8.2. Private CA cho dịch vụ nội bộ

Doanh nghiệp có thể tự vận hành **private CA** để cấp chứng thư cho API nội bộ, database TLS, VPN gateway hoặc dịch vụ quản trị. Các client chỉ tin chứng thư đó khi **trust anchor tương ứng được cấp phát an toàn và có phê duyệt**, ví dụ qua MDM/GPO/PKI quản lý.

**Không khuyên người dùng bấm “Trust this certificate” cho root CA lạ** để khắc phục lỗi. Thêm một CA vào trust store thường làm tăng phạm vi chứng thư mà thiết bị có thể chấp nhận, vì vậy cần kiểm soát nguồn, mục đích và thời hạn sử dụng.

### 8.3. Hạn chế phạm vi tin cậy

Một CA không phải cứ được tin là nên có quyền cấp chứng thư cho mọi tên trong tổ chức. Khi hạ tầng và công cụ hỗ trợ, có thể giới hạn bằng **name constraints, EKU, policy, phân tách CA, trust store riêng** hoặc các cơ chế cấp phát được quản lý.

Ví dụ một hệ thống CI chỉ cần tin private CA ký cho những service mesh workloads thuộc môi trường thử nghiệm; nó không nên tự động nhập một root không rõ nguồn vào trust store toàn hệ điều hành.

### 8.4. CA bị xâm nhập

Khi private key CA hoặc quy trình cấp phát bị xâm nhập, kẻ tấn công có thể có khả năng tạo những chứng thư mà client tin nếu không có lớp kiểm soát bổ sung. Cần phương án bảo vệ khóa bằng HSM/KMS phù hợp, quản lý quyền phát hành, audit, thu hồi và khôi phục hệ thống tin cậy.

## 9. Thời gian hiệu lực và đồng hồ

Chứng thư thường có hai mốc:

- **Not Before:** thời điểm bắt đầu có hiệu lực.
- **Not After:** thời điểm kết thúc có hiệu lực.

Client cần kiểm tra theo đồng hồ đáng tin. Một client có đồng hồ quá sai có thể từ chối chứng thư vốn hợp lệ hoặc đưa ra kết luận không đúng. Cả **leaf** và những chứng thư trung gian liên quan cần được đánh giá theo quy tắc xác thực đường chứng thực.

**Chứng thư chưa hết hạn không đồng nghĩa còn đáng tin**, vì nó có thể bị thu hồi, cấp sai tên, dùng sai EKU hoặc được ký bởi CA không tin cậy.

### 9.1. Giám sát trước khi hết hạn

Không nên chờ đến lúc trình duyệt hiện lỗi mới gia hạn. Hệ thống nên theo dõi:

- Ngày hết hạn của chứng thư đang được **thực sự phục vụ** tại mỗi endpoint.
- Ngày hết hạn intermediate và sự thay đổi chuỗi CA.
- Sự khác biệt giữa chứng thư lưu trong hệ thống và chứng thư đang được load balancer/CDN đưa ra.
- Thời gian đồng bộ của server, client và hệ thống cấp phát.
- Mức độ thành công của quy trình gia hạn tự động, reload cấu hình và kiểm thử sau triển khai.

## 10. Thu hồi chứng thư: CRL, OCSP và giới hạn

Một chứng thư có thể bị **revoked** trước ngày hết hạn, chẳng hạn khi private key bị lộ, tên miền/thiết bị thay đổi quyền hoặc CA phát hiện cấp phát không đúng.

### 10.1. Certificate Revocation List (CRL)

**CRL** là danh sách do CA công bố về những chứng thư bị thu hồi, thường gắn với số serial và thời điểm. Client có thể tải/đọc CRL theo chính sách.

Giới hạn: CRL có thể lớn, cần cập nhật và phụ thuộc khả năng truy cập nguồn dữ liệu. Khi không truy cập được CRL, hành vi **fail-open** hoặc **fail-closed** phụ thuộc ứng dụng và chính sách.

### 10.2. Online Certificate Status Protocol (OCSP)

**OCSP** cho phép tra cứu trạng thái của một chứng thư từ dịch vụ responder phù hợp. Cơ chế này có thể tạo phụ thuộc availability, quyền riêng tư và độ trễ; một số nền tảng có các chiến lược tối ưu, caching hoặc thay thế khác nhau.

**OCSP stapling** là cơ chế trong đó server có thể cung cấp một phản hồi trạng thái đã được ký kèm TLS handshake, giảm việc client phải tự hỏi responder trong những trường hợp được hỗ trợ. Các hành vi và yêu cầu đối với OCSP trong TLS 1.3 hoặc từng browser/library không giống nhau; không mặc định mọi client luôn kiểm tra OCSP hoặc fail-closed khi responder không sẵn sàng.

### 10.3. Revocation không phải cơ chế tức thời tuyệt đối

Các vấn đề cần cân nhắc:

- Dữ liệu trạng thái có thể cache và có thời gian hiệu lực.
- Chính sách kiểm tra có thể khác giữa browser, JVM, proxy và service-to-service TLS.
- Khó khăn khi truy cập responder có thể khiến một số client **không chặn** theo cùng cách.
- Việc thu hồi private key bị lộ còn cần **cấp khóa/chứng thư mới, đổi cấu hình server, thu hồi phiên/token nếu liên quan và điều tra**.

**Không suy rằng “đã revoke” đồng nghĩa mọi client trên Internet lập tức từ chối chứng thư đó.** Phải hiểu cơ chế kiểm tra và chính sách của từng client trong phạm vi chịu trách nhiệm.

## 11. Certificate Transparency không phải xác minh hostname

**Certificate Transparency (CT)** là hệ sinh thái ghi nhận công khai những chứng thư hoặc dữ liệu chứng thư theo cơ chế log được thiết kế để phát hiện cấp phát bất thường. Các chương trình trình duyệt hoặc CA có thể yêu cầu chứng minh chứng thư đã được log theo chính sách riêng.

CT có giá trị trong việc **quan sát phát hành chứng thư không mong muốn**, nhưng:

- CT log không tự chứng minh server nắm private key.
- Có mặt trong CT log không thay thế kiểm tra **SAN/hostname**, chữ ký, trust anchor và thời hạn.
- Một chứng thư được log vẫn có thể do CA cấp sai hoặc bị lạm dụng trước khi bị phát hiện.
- Private PKI không nhất thiết áp dụng cùng quy trình CT như public TLS theo chính sách browser.

Tổ chức nên giám sát certificate issuance cho tên miền quan trọng, kết hợp inventory, thay đổi DNS, quyền quản lý CA và runbook cấp phát trái phép.

## 12. Chứng thư nằm ở đâu trong TLS 1.3 handshake?

TLS 1.3 dùng các bước thương lượng thuật toán, trao đổi khóa và xác thực máy chủ. Trong một **full handshake dựa trên chứng thư**, client và server thường trao đổi các thông tin ở mức khái niệm như:

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>S: ClientHello (SNI, supported versions, key_share, ...)
    S-->>C: ServerHello (chọn tham số, key_share)
    Note over C,S: Thiết lập khóa handshake; nhiều bản tin sau được mã hóa
    S-->>C: EncryptedExtensions
    S-->>C: Certificate (leaf và chain cần thiết)
    S-->>C: CertificateVerify (chứng minh sở hữu khóa)
    S-->>C: Finished
    Note over C: Xác minh chain, hostname, chữ ký và handshake
    C->>S: Finished
    Note over C,S: Dữ liệu ứng dụng được bảo vệ bằng khóa phiên
~~~

**Sơ đồ giản lược:** TLS 1.3 có những biến thể như session resumption, PSK, client authentication và certificate compression; không phải mọi kết nối đều truyền lại đầy đủ chứng thư. Một số nội dung handshake sau ServerHello được mã hóa, nhưng không có nghĩa mọi metadata như IP, tên miền trong DNS hoặc mọi ClientHello đều được che giấu.

### 12.1. SNI: chọn chứng thư, không tự xác thực danh tính

**Server Name Indication (SNI)** thường được client gửi trong ClientHello để server/reverse proxy biết tên dịch vụ client định truy cập, đặc biệt khi nhiều hostname dùng chung IP/port.

SNI giúp server **chọn** chứng thư nhưng không chứng minh chứng thư được chọn là hợp lệ. Client vẫn cần kiểm tra leaf SAN và chuỗi tin cậy theo **hostname thực mà ứng dụng muốn kết nối**, không chỉ chấp nhận tên do server tự nói.

**Encrypted ClientHello (ECH)** có thể bảo vệ một phần thông tin ClientHello, tùy năng lực và triển khai; đừng mặc định mọi mạng TLS hiện đại đã bật ECH hoặc mọi metadata đều được che giấu.

### 12.2. CertificateVerify và sở hữu khóa

Trong handshake TLS 1.3 dựa trên chứng thư, **CertificateVerify** cung cấp chữ ký để phía còn lại xác minh server sở hữu private key tương ứng với public key trong chứng thư.

Đây là bước khác với việc CA **ký chứng thư**: CA chứng nhận liên kết danh tính–public key theo chính sách cấp phát, còn server chứng minh mình có khóa của chính chứng thư được đưa ra.

### 12.3. TLS 1.2 và khác biệt phiên bản

TLS 1.2 có bố cục handshake và các cipher suite khác với TLS 1.3; thuật toán trao đổi khóa và chức năng chữ ký có thể khác. Một tài liệu chẩn đoán phải nêu **phiên bản TLS được thử** trước khi giải thích cụ thể chứng thư hoặc thông điệp handshake.

**Không hạ cấp phiên bản TLS hoặc bật lại cipher yếu** chỉ để một client cũ kết nối, nếu chưa đánh giá chính sách an toàn và tác động.

## 13. Reverse proxy, CDN, load balancer và TLS termination

Trong hệ thống doanh nghiệp, client thường không kết nối trực tiếp tới application server. Đường đi có thể là:

~~~mermaid
flowchart LR
    U["Internet client"] -->|"TLS: www.company.example"| EDGE["CDN / Reverse proxy / LB"]
    EDGE -->|"TLS riêng hoặc kênh nội bộ theo policy"| APP["Application service"]
    APP -->|"TLS mTLS nếu yêu cầu"| DB[("Database / internal API")]
    EDGE -. "Certificate inventory, expiry" .-> SOC["Monitoring / SOC"]
    APP -. "Backend TLS validation" .-> SOC
~~~

### 13.1. Chứng thư client nhìn thấy là của đâu?

Nếu TLS được **kết thúc (terminate) tại CDN/reverse proxy/load balancer**, chứng thư mà browser nhìn thấy thường do điểm TLS termination trình bày. Chứng thư leaf cần hợp lệ cho **hostname công khai mà browser truy cập**.

Backend có thể dùng một chứng thư **khác**, với tên định danh của dịch vụ backend và trust policy nội bộ. Không nên chỉ kiểm tra browser thấy ổ khóa rồi kết luận **kết nối proxy → backend** đã được mã hóa và xác minh đúng.

### 13.2. Re-encryption và backend certificate validation

Nếu proxy mở TLS mới tới backend, nó đóng vai **TLS client** ở chặng đó và cần:

- Tin đúng CA hoặc trust anchor backend theo chính sách.
- Kiểm tra hostname/service identity của backend.
- Kiểm tra chứng thư còn hiệu lực, EKU/mục đích và các ràng buộc khác.
- Không bỏ kiểm tra chứng thư chỉ vì backend ở private subnet hoặc dùng VPN.

Một cấu hình **encrypt to backend but skip certificate verification** chỉ bảo vệ một phần rủi ro nghe lén, trong khi xác thực endpoint bị suy yếu.

### 13.3. SNI, multi-domain và cổng chung

Khi nhiều tên dùng một IP/443, reverse proxy chọn chứng thư theo SNI. Sai cấu hình có thể làm server trả **default certificate** cho một domain khác, dẫn đến **hostname mismatch**. Cần kiểm tra mỗi hostname đúng tên và cổng, cả IPv4/IPv6 và tuyến dự phòng.

### 13.4. TLS inspection tại firewall/WAF

Một proxy thực hiện TLS inspection có thể tạo kênh TLS riêng với client và server theo chính sách tổ chức. Việc này thường đòi hỏi **trust anchor được cấp phát có kiểm soát** ở client, quản trị khóa CA, quyền riêng tư và tuân thủ.

**Không tự cài một root CA không rõ nguồn hoặc tắt cảnh báo chứng thư để “cho WAF/IDS thấy HTTPS”.** Nếu tổ chức buộc kiểm tra TLS, phải có quy trình chấp thuận, giới hạn phạm vi, giám sát và công bố minh bạch phù hợp.

## 14. mTLS: xác minh máy chủ và xác minh client

**Mutual TLS (mTLS)** bổ sung việc máy chủ yêu cầu và xác minh **chứng thư client** theo chính sách. Trong TLS thông thường của browser, client chủ yếu xác minh server; còn với mTLS, **hai phía đều có công việc xác thực riêng**.

| Chiều xác thực | Bên kiểm tra | Điều cần kiểm tra |
| --- | --- | --- |
| **Server authentication** | TLS client | Chuỗi CA, SAN/hostname, EKU serverAuth, thời hạn, handshake |
| **Client authentication (mTLS)** | TLS server | Chuỗi CA, danh tính client, EKU clientAuth, thời hạn, policy ứng dụng |

Ví dụ API nội bộ yêu cầu client là service **payment-worker** và server là **billing-api**. Cả hai có thể có chứng thư do private PKI quản lý với danh tính dịch vụ cụ thể.

**Có chứng thư client hợp lệ không tự cấp mọi quyền API.** Server cần ánh xạ danh tính client vào role/permission và kiểm soát những hành động cụ thể. Ngược lại, client vẫn cần **xác minh danh tính server**, không chỉ trình bày chứng thư của mình.

## 15. VPN, Wi-Fi Enterprise và các trust zone

### 15.1. VPN

Một số công nghệ VPN sử dụng TLS hoặc chứng thư trong cơ chế xác thực. Client cần kiểm tra đúng danh tính gateway, CA tin cậy và certificate profile theo giao thức VPN thực tế.

**Không phải mọi VPN đều dùng TLS**: IPsec/IKE có cơ chế xác thực và trao đổi khóa riêng, dù có thể dùng chứng thư X.509. Phải xem tài liệu giao thức trước khi áp dụng các bước chẩn đoán của HTTPS nguyên xi cho IPsec.

### 15.2. Wi-Fi Enterprise / 802.1X

Trong Wi-Fi Enterprise, nhiều phương thức EAP (như EAP-TLS) có cơ chế xác thực **EAP server** bằng chứng thư. Thiết bị cần được cấu hình **CA và tên máy chủ xác thực dự kiến**, không chấp nhận vô điều kiện chứng thư của một EAP server bất kỳ.

Đây là lớp phòng vệ quan trọng trước mạng Wi-Fi giả mạo hoặc endpoint xác thực không được phê duyệt. Một SSID đúng tên **không thay thế** xác minh máy chủ EAP.

### 15.3. DNS, firewall và phân đoạn mạng

- **DNS** giúp client tìm địa chỉ của hostname; DNSSEC có thể xác thực dữ liệu DNS theo chuỗi tin cậy, nhưng không thay thế TLS hostname validation.
- **Firewall** giới hạn đường kết nối, không tự chứng minh public key/danh tính máy chủ.
- **Phân đoạn mạng** giới hạn kết nối giữa các zone; máy ở Data zone vẫn nên xác thực API/DB server theo chính sách.
- **IDS/IPS/WAF** hỗ trợ phát hiện và bảo vệ theo lớp; một số phân tích nội dung TLS có thể bị hạn chế khi payload được mã hóa.
- **Cloud IAM và service identity** kiểm soát quyền quản trị/cấp phát chứng thư và định danh workload; chứng thư hợp lệ không tự thay thế authorization.

## 16. Kiểm tra chứng thư bằng OpenSSL trong môi trường được phép

Những lệnh sau dùng để **quan sát và kiểm tra cấu hình** của dịch vụ được tổ chức cho phép hoặc dịch vụ công khai phục vụ bài học. Chúng không sửa chứng thư và không khai thác lỗ hổng. Cú pháp và tùy chọn có thể khác theo phiên bản OpenSSL; kiểm tra tài liệu bản cài trước khi sử dụng.

### 16.1. Đọc thông tin leaf certificate có sẵn

~~~bash
# leaf.pem là chứng thư thử nghiệm đã có sẵn, không phải private key.
openssl x509 -in leaf.pem -noout -subject -issuer -dates -serial

# Xem danh sách SAN được cấp.
openssl x509 -in leaf.pem -noout -ext subjectAltName

# Xem công dụng chứng thư theo EKU nếu extension được cung cấp.
openssl x509 -in leaf.pem -noout -ext extendedKeyUsage

# Xem Basic Constraints khi cần điều tra CA/leaf.
openssl x509 -in leaf.pem -noout -ext basicConstraints
~~~

**Không gửi private key vào công cụ phân tích trực tuyến** khi chỉ cần đọc chứng thư public. Các công cụ dựa trên PEM cần phân biệt rõ file **CERTIFICATE** với **PRIVATE KEY**.

### 16.2. Kiểm tra TLS endpoint trực tiếp

~~~bash
# Chỉ thay bằng hostname/endpoint mà bạn có quyền kiểm tra.
# -servername gửi SNI; -verify_hostname kiểm tra danh tính DNS.
# -verify_return_error làm handshake báo lỗi khi verify gặp vấn đề.
openssl s_client \
  -connect api.company.example:443 \
  -servername api.company.example \
  -verify_hostname api.company.example \
  -verify_return_error \
  -showcerts </dev/null
~~~

Trong bài học **api.company.example** là hostname giả lập; muốn chạy lệnh phải thay bằng endpoint **thật, thuộc phạm vi được phép**, với DNS có thể phân giải. Kết quả phụ thuộc trust store/OpenSSL build, cấu hình server và kết nối mạng.

**Không dùng cờ bỏ qua xác minh** để biến lỗi thành “PASS”. Nếu muốn chẩn đoán một endpoint có private CA, hãy cấu hình trust anchor đúng theo quy trình, không tắt bước xác thực.

### 16.3. Xác minh một chuỗi PEM trong lab

~~~bash
# Ví dụ trong lab có root CA tin cậy, intermediate và leaf.
# Các file PEM phải đến từ nguồn được quản lý/cấp phép.
openssl verify \
  -purpose sslserver \
  -verify_hostname api.company.example \
  -CAfile trusted-root.pem \
  -untrusted intermediate-chain.pem \
  leaf.pem
~~~

**trusted-root.pem** là CA mà bài lab chủ động chọn làm trust anchor. **intermediate-chain.pem** chỉ cung cấp chứng thư trung gian, không tự cấp quyền tin cậy. Kết quả **OK** ở lệnh này đánh giá việc xác minh chứng thư theo OpenSSL/policy; nó **không** tự kiểm tra endpoint online đang sở hữu private key hay đang trình bày cùng chứng thư.

### 16.4. Đọc kết quả thay vì chỉ tìm chữ OK

Khi xem output, xác định:

1. Chứng thư **leaf** nào đang được server cung cấp?
2. **SAN** có bao gồm hostname client yêu cầu không?
3. Server có đưa ra intermediate cần thiết không?
4. Chứng thư nào là **issuer** ở từng cấp và có đường tới trusted root không?
5. Chứng thư có hiệu lực theo đồng hồ đang dùng?
6. Công cụ có báo **verify return code** và lỗi nào?
7. Tên SNI và hostname dùng để verify có đúng với tên dịch vụ?
8. Có sự khác biệt khi thử IPv4, IPv6, CDN edge hoặc backend không?

**Một lệnh s_client không chỉ rõ -verify_hostname** có thể xác minh chữ ký/đường CA nhưng **chưa kiểm tra hostname như browser mong muốn**. Vì vậy hãy ghi rõ tham số xác minh khi dùng nó làm bằng chứng.

## 17. Các lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| **Unknown CA / untrusted issuer** | Trust anchor không nằm trong trust store, hoặc chain thiếu trung gian | Kiểm tra trust store, server chain, quyền cấp phát CA |
| **Hostname mismatch** | SAN không có hostname client yêu cầu | Kiểm tra DNS/IP, SNI, SAN và chứng thư endpoint đang phục vụ |
| **Certificate expired** | Leaf/intermediate đã qua Not After, hệ thống gia hạn/reload lỗi | Đọc thời hạn tại endpoint thực, trạng thái automation |
| **Certificate not yet valid** | Not Before chưa tới hoặc đồng hồ sai | Kiểm tra thời gian client/server và ngày phát hành |
| **Unable to get local issuer** | Thiếu intermediate hoặc đường chứng thực không xây được | So sánh chain server gửi và trust store client |
| **Invalid CA / key usage** | Intermediate thiếu quyền CA hoặc extension không phù hợp | Kiểm tra Basic Constraints, Key Usage, path |
| **Unsuitable certificate purpose** | EKU không phù hợp TLS server | Kiểm tra serverAuth và certificate profile |
| **Signature/algorithm rejected** | Thuật toán bị cấm hoặc implementation không hỗ trợ | Kiểm tra policy/phiên bản TLS và chứng thư |
| **Revoked certificate** | Trạng thái thu hồi bị phát hiện theo chính sách | Kiểm tra serial, CRL/OCSP và phương án cấp lại |
| **Chỉ client cũ lỗi** | Trust store/algorithm/chain compatibility khác | So sánh trust anchor, hệ điều hành và chain |
| **Chỉ một hostname trên cùng IP lỗi** | Default certificate/SNI sai | Thử từng hostname với -servername và verify |
| **Browser đúng, backend proxy lỗi** | Backend private CA hoặc hostname validation sai | Xem trust policy của proxy như một TLS client |
| **Chỉ lỗi sau đổi CA** | Cross-sign, root trust hoặc cache intermediate khác | Thử từ client sạch và nhiều trust stores |

### 17.1. Khi người dùng báo “trình duyệt hiện cảnh báo chứng thư”

Không hướng dẫn người dùng bấm bỏ qua cảnh báo trên hệ thống thật. Quy trình:

1. Ghi hostname/URL, thời gian, thiết bị, trình duyệt và mã lỗi **không chứa bí mật phiên**.
2. Xác minh tổ chức đang sở hữu hostname nào và endpoint TLS kết thúc ở đâu.
3. Kiểm tra chứng thư **thực sự được server/CDN/proxy gửi**, không chỉ file vừa upload.
4. Kiểm tra SAN, hạn, chuỗi và trust anchor trên client bị ảnh hưởng.
5. Nếu một số client bị lỗi, so sánh trust store, SNI, OS và cấu hình TLS inspection hợp pháp.
6. Khôi phục chứng thư/cấu hình đúng qua change control, rồi thử lại.

**Cảnh báo chứng thư có thể do lỗi vận hành hoặc dấu hiệu mạo nhận.** Không tự quy kết là tấn công khi chưa có bằng chứng, nhưng cũng không xóa cảnh báo bằng cách vô hiệu xác minh.

## 18. Quản lý vòng đời chứng thư và private key

### 18.1. Inventory có chủ sở hữu

Mỗi chứng thư nên có bản ghi:

- Hostname/SAN, nơi TLS termination, ứng dụng và môi trường.
- CA cấp, loại public/private PKI, người chịu trách nhiệm.
- Ngày phát hành/hết hạn, thuật toán và khóa liên quan theo mức metadata không nhạy cảm.
- Nơi giữ private key và cách cấp phát/rotation, **không ghi chính private key trong inventory**.
- Phụ thuộc CDN, load balancer, ingress, gateway, VPN hoặc các container replicas.
- Cách gia hạn, reload/redeploy, kiểm thử sau cập nhật và rollback.

### 18.2. Tự động hóa cấp phát/gia hạn

Các nền tảng có thể hỗ trợ **ACME** hoặc cơ chế PKI/secret manager tương đương để xin/gia hạn chứng thư. Tự động hóa cần:

1. Kiểm soát quyền phát hành và xác thực quyền sử dụng tên miền.
2. Bảo vệ private key, token và tài khoản quản lý CA.
3. Cập nhật **đúng leaf + intermediate chain** ở mọi endpoint.
4. Reload ứng dụng/proxy theo cách an toàn để dùng chứng thư mới.
5. Kiểm tra hostname, chain, hiệu lực, TLS handshake và ứng dụng sau triển khai.
6. Cảnh báo khi cấp/gia hạn **thất bại**, khi chứng thư phục vụ không đổi và trước hạn kết thúc.

### 18.3. Rotation khi khóa bị lộ

Nếu private key leaf bị lộ:

- Đánh giá phạm vi dịch vụ và tài khoản có liên quan.
- Cấp **cặp khóa mới và chứng thư mới** theo quy trình, không chỉ đổi tên file.
- Thu hồi chứng thư cũ khi cần và đánh giá giới hạn cơ chế revocation của client.
- Cập nhật endpoint, xóa khả năng sử dụng khóa cũ và rà soát các hệ thống sao chép bí mật.
- Điều tra log và tác động, bao gồm kết nối trong khoảng thời gian khóa có thể bị lạm dụng.

**Không chia sẻ private key qua email/chat/ticket** để “nhờ kiểm tra”; chỉ trao đổi chứng thư public và thông tin kỹ thuật không nhạy cảm.

## 19. Chính sách phòng vệ trung lập với sản phẩm

Đoạn YAML dưới đây là **mô hình yêu cầu vận hành**, không phải cấu hình trực tiếp cho Nginx, Apache, HAProxy, Envoy, Java TrustManager, cloud load balancer hoặc hệ thống PKI cụ thể:

~~~yaml
tlsServerIdentityPolicy:
  service: order-api
  environment: controlled-training
  publicEndpoint:
    expectedHostname: api.company.example
    expectedPort: 443
    requireTls: true
    requireCertificatePathValidation: true
    requireHostnameVerification: true
    requireValidServerPurpose: true
    trustedCaSet: approved-platform-trust-store
    disallowInsecureVerificationBypass: true
  certificateLifecycle:
    owner: platform-security
    inventoryEnabled: true
    privateKeyProtection: managed-secret-or-hsm
    monitorExpiry: true
    alertBeforeExpiry: policy-defined
    renewAndReloadAutomation: enabled-with-verification
    monitorUnexpectedIssuance: true
  proxyToBackend:
    useTls: true
    backendServiceIdentity: order-api.internal.example
    trustedCaSet: approved-internal-pki
    requireBackendHostnameVerification: true
    disableVerifyNone: true
  monitoring:
    observePresentedChain: true
    observeTlsHandshakeFailures: true
    correlateDnsAndProxyChanges: true
    checkIpv4AndIpv6: true
    redactSecrets: true
  changeControl:
    requireOwnerApproval: true
    testOnClientWithCleanTrustStore: true
    recordCertificateFingerprint: true
    keepRollbackPlan: true
~~~

Các trường như **disableVerifyNone** hay **requireBackendHostnameVerification** thể hiện chính sách mong muốn, **không bảo đảm tính năng đã bật trên thiết bị thật**. Phải chuyển sang cấu hình cụ thể và xác minh bằng phép thử chủ động trong lab/production được phê duyệt.

## 20. Nhật ký TLS và bằng chứng cần đối chiếu

Một cảnh báo TLS hữu ích cần chỉ rõ **endpoint, danh tính client mong đợi, chứng thư được trình bày và nguyên nhân xác minh thất bại**.

| Trường | Mục đích |
| --- | --- |
| Timestamp / environment / region | Xác định thời điểm và điểm TLS termination |
| Requested hostname / SNI | Biết client định truy cập tên nào |
| Presented SAN / subject / issuer | Đối chiếu danh tính và đường CA |
| Certificate fingerprint / serial | Liên kết chứng thư cụ thể, không cần ghi private key |
| Not Before / Not After | Kiểm tra thời gian hiệu lực |
| Validation outcome / error code | Phân biệt unknown CA, hostname mismatch, expired, revoked |
| TLS version và negotiated parameters | Chẩn đoán tương thích và chính sách kênh |
| Trust store / policy version | Giải thích khác biệt giữa client |
| Edge/backend hop | Biết lỗi ở client → proxy hay proxy → backend |
| Correlation/request ID | Liên kết log ứng dụng, proxy, DNS và monitoring |

### 20.1. Log mẫu giả lập

~~~json
{
  "timestamp": "2026-11-28T16:25:00+07:00",
  "environment": "training-lab",
  "client_component": "reverse-proxy",
  "tls_hop": "proxy-to-backend",
  "expected_hostname": "order-api.internal.example",
  "presented_san_dns": [
    "old-order-api.internal.example"
  ],
  "chain_trust_status": "valid-under-lab-pki",
  "hostname_validation": "failed",
  "error_category": "hostname-mismatch",
  "decision": "connection-rejected",
  "application_data_sent": false,
  "dataset": "synthetic-training-event"
}
~~~

Trong log, đường CA có thể hợp lệ nhưng tên máy chủ **không khớp** nên kết nối bị từ chối. Đây là hành vi bảo vệ đúng theo chính sách; không tự chứng minh có kẻ tấn công. Có thể là lỗi đổi tên backend, cấu hình SNI hoặc chứng thư không được triển khai đúng.

## 21. Kiểm thử xác minh máy chủ trong lab được ủy quyền

Phép thử nên sử dụng **CA, leaf certificates, endpoint và client trong lab thuộc quyền kiểm soát**. Không cần tấn công trung gian hoặc giả mạo dịch vụ công khai để chứng minh client có từ chối chứng thư sai hay không.

### 21.1. Ma trận kiểm thử

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T-01 | Leaf SAN đúng hostname, chain hợp lệ, chưa hết hạn | TLS kết nối thành công |
| T-02 | Leaf hợp lệ cho hostname **khác** | Client từ chối hostname mismatch |
| T-03 | Leaf ký bởi CA không nằm trong trust store | Client từ chối unknown/untrusted CA |
| T-04 | Server bỏ intermediate cần thiết, client sạch không có cache | Xác minh không dựng được chain, báo lỗi phù hợp |
| T-05 | Leaf hoặc intermediate hết hạn | Client từ chối theo chính sách |
| T-06 | Leaf chưa tới Not Before | Client từ chối theo đồng hồ hợp lệ |
| T-07 | Leaf có EKU không phù hợp serverAuth theo profile đã áp dụng | Client từ chối mục đích không hợp lệ |
| T-08 | Hostname yêu cầu là apex nhưng chứng thư chỉ có wildcard một nhãn | Client từ chối mismatch |
| T-09 | Client dùng IP literal, chứng thư chỉ có dNSName | Không mặc nhiên chấp nhận nếu thiếu iPAddress SAN |
| T-10 | Nhiều hostname trên một proxy, thử SNI tương ứng từng tên | Proxy trình bày đúng chứng thư cho từng hostname |
| T-11 | Proxy có TLS backend nhưng bật xác minh backend đúng | Chỉ cho kết nối khi backend name/CA hợp lệ |
| T-12 | Chứng thư mới được cập nhật nhưng một replica vẫn phục vụ bản cũ | Monitoring phát hiện không đồng bộ triển khai |
| T-13 | Private CA được phân phối đúng tới lab client | Xác minh thành công **chỉ** trong trust scope được duyệt |
| T-14 | CA khác lạ được server đính kèm nhưng client không tin | Client vẫn từ chối, không tự tin do server cung cấp root |
| T-15 | Chính sách kiểm tra revocation được bật trong lab | Kết quả phù hợp khả năng thư viện và fail mode được định nghĩa |
| T-16 | Thử IPv4/IPv6 và hai edge locations hợp lệ | SAN/chain/policy nhất quán theo dịch vụ |

### 21.2. Cách xác minh kết quả

1. Ghi lại **hostname mục tiêu, endpoint IP, SNI, TLS version, trust store và policy version**.
2. Chạy phép thử và lưu **error code/certificate chain** không chứa bí mật.
3. Đối chiếu chứng thư server thực sự phục vụ với inventory.
4. Xác minh client đã **từ chối trước khi gửi dữ liệu ứng dụng nhạy cảm** trong case âm tính.
5. Nếu là backend TLS, đối chiếu log phía proxy và application; không chỉ dựa trên HTTP 502 hoặc timeout.
6. Xác minh những case hợp lệ vẫn hoạt động sau khi siết chính sách.
7. Ghi phương án rollback và người chịu trách nhiệm.

**Negative test quan trọng không kém positive test:** một client kết nối thành công với chứng thư hợp lệ chỉ chứng minh luồng hợp lệ hoạt động, chưa chứng minh nó sẽ từ chối endpoint sai.

## 22. Tình huống tổng hợp: CDN hợp lệ nhưng backend chưa xác minh tên

Giả sử hệ thống bán hàng có:

- Public hostname **shop.company.example** được phục vụ bởi CDN.
- CDN có leaf certificate công khai hợp lệ cho tên này.
- CDN mở một kết nối TLS khác đến **origin.internal.example**.
- Cấu hình kết nối CDN → origin bật mã hóa nhưng **tắt kiểm tra hostname backend**.

Người dùng mở website thấy HTTPS bình thường. Tuy nhiên, lớp bảo vệ đoạn **CDN → origin** chưa đầy đủ vì proxy chưa xác minh đúng danh tính của endpoint backend.

### 22.1. Phân tích

1. Browser xác thực **shop.company.example** của CDN.
2. CDN đóng vai TLS client khi nói chuyện với backend, nên có **trách nhiệm xác thực origin.internal.example**.
3. Nếu backend trả chứng thư ký bởi CA được CDN tin nhưng cho **wrong.internal.example**, một client kiểm tra hostname đúng phải từ chối.
4. Nếu CDN được cấu hình **skip hostname verification**, kết nối có thể vẫn được mã hóa nhưng danh tính backend không được ràng buộc đúng; điều này tạo rủi ro khi đường mạng hoặc DNS sai lệch.

### 22.2. Cách cải thiện

- Thiết lập đúng tên backend, SAN và SNI tương ứng.
- Chọn trust anchor backend phù hợp, có thể là private CA nếu nội bộ quản lý.
- Bật **path validation và hostname verification** tại proxy/backend client.
- Kiểm thử bằng một backend giả lập có chứng thư hợp lệ nhưng **tên sai** để xác nhận proxy từ chối trong lab.
- Kiểm tra mọi điểm CDN, IPv4/IPv6, failover và origin pool.
- Giám sát khi chứng thư backend thay đổi, hết hạn hoặc private CA được xoay.

### 22.3. Kết luận

**HTTPS ở phía người dùng không chứng minh tất cả chặng phía sau đều được xác thực đầy đủ.** Mỗi lần kết thúc rồi tạo lại TLS là một **ranh giới tin cậy mới**; điểm đóng vai TLS client ở mỗi chặng phải xác minh server theo danh tính kỳ vọng.

## 23. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “TLS mã hóa rồi thì không cần kiểm tra chứng thư” | Kết nối mã hóa tới endpoint sai | Bắt buộc xác minh chain và hostname |
| “Chứng thư do public CA ký nên hợp lệ cho mọi domain” | Mismatch bị bỏ qua | Kiểm tra SAN theo hostname client yêu cầu |
| “Root CA do server gửi là tự đáng tin” | Có thể tin sai CA lạ | Trust anchor phải nằm trong trust store đáng tin của client |
| “Chỉ cần nhìn Subject CN” | Đánh giá sai danh tính hostname | Dùng SAN theo profile hiện đại |
| “Wildcard khớp mọi subdomain ở mọi cấp” | Sai quy tắc matching | Kiểm tra phạm vi wildcard và apex/multi-label |
| “Thiếu intermediate nhưng máy quản trị vẫn vào được nên server đúng” | Client khác thiếu cache sẽ lỗi | Gửi đúng full chain và thử client sạch |
| “Chứng thư chưa hết hạn nên chắc chắn an toàn” | Bỏ qua revoke/hostname/EKU/CA | Path validation đầy đủ và theo chính sách |
| “Bật OCSP đồng nghĩa mọi client chặn tức thì khi revoke” | Hiểu sai cache/fail mode | Kiểm tra chính sách revocation trên từng client |
| “CT log có chứng thư nghĩa là website an toàn” | Nhầm giám sát cấp phát với xác thực server | Vẫn cần TLS và ứng dụng bảo mật |
| “OpenSSL s_client luôn kiểm tra hostname mặc định” | Có thể bỏ sót mismatch | Chỉ rõ -verify_hostname và quan sát verify result |
| “Đã có TLS ở CDN thì backend không cần xác minh” | Ranh giới phía sau yếu | Xác minh riêng đoạn proxy → backend |
| “Có mTLS thì client có quyền gọi mọi API” | Quyền ứng dụng quá rộng | Tách identity của chứng thư và application authorization |
| “Lỗi cert cứ tắt verify để chạy lại” | Vô hiệu hóa một cơ chế bảo vệ cốt lõi | Sửa CA, SAN, chain, thời hạn và policy đúng |
| “Cài một root mới vào mọi thiết bị là sửa được” | Mở rộng trust store quá mức | Phân phối CA theo phạm vi có phê duyệt |

## 24. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Chứng thư leaf, intermediate CA và trust anchor khác nhau ở vai trò nào? Vì sao root được server gửi không tự làm client tin?

**Gợi ý:** leaf đại diện server, intermediate được cấp quyền ký, trust anchor phải có trong môi trường tin cậy của client.

### Câu hỏi 2

Một chứng thư được CA công khai ký, chưa hết hạn, nhưng SAN chỉ có **www.company.example**. Client kết nối **api.company.example** có nên chấp nhận không?

**Gợi ý:** không, vì hostname mismatch dù chữ ký/CA/thời gian có thể hợp lệ.

### Câu hỏi 3

Tại sao một server thiếu intermediate đôi khi vẫn chạy được trên laptop của quản trị viên nhưng lỗi trên thiết bị mới?

**Gợi ý:** máy cũ có thể cache hoặc tải bổ sung intermediate theo cách khác, còn client sạch không có đường chứng thực.

### Câu hỏi 4

SNI có phải cơ chế client dùng để tin tưởng máy chủ không? Nó liên quan thế nào tới SAN?

**Gợi ý:** SNI hỗ trợ server chọn chứng thư; SAN được client dùng để xác minh danh tính phù hợp với hostname.

### Câu hỏi 5

Chứng thư dùng cho clientAuth có thể mặc nhiên thay thế chứng thư serverAuth không?

**Gợi ý:** không; kiểm tra EKU và purpose theo profile/policy.

### Câu hỏi 6

OCSP/CRL và Certificate Transparency giải quyết hai bài toán khác nhau nào?

**Gợi ý:** tình trạng thu hồi và khả năng quan sát cấp phát; không thay thế kiểm tra tên và chữ ký.

### Câu hỏi 7

Tại sao reverse proxy kết nối tới backend bằng TLS vẫn phải kiểm tra chứng thư backend?

**Gợi ý:** mã hóa riêng không chứng minh endpoint backend là đúng; proxy là TLS client trong chặng đó.

### Câu hỏi 8

Trong một môi trường dùng private CA, tổ chức nên phân phối trust anchor như thế nào để không vô tình tin những CA không được phép?

**Gợi ý:** kênh cấp phát được quản lý, giới hạn phạm vi, quản trị vòng đời và auditing.

### Câu hỏi 9

Một kết nối TLS thành công có chứng minh người dùng được phép xem toàn bộ dữ liệu ứng dụng không?

**Gợi ý:** không; TLS xác thực endpoint/kênh, còn ứng dụng phải kiểm tra authorization.

### Câu hỏi 10

Khi dùng OpenSSL s_client để thử một hostname trên server đa tên, tại sao cần quan tâm cả **-servername** và **-verify_hostname**?

**Gợi ý:** một tham số giúp chọn chứng thư theo SNI, tham số còn lại xác minh tên được phục vụ.

### Bài tập thiết kế

Hãy lập một mô hình có **client Internet → CDN → reverse proxy → internal API → database**, với một kết nối VPN quản trị và Wi-Fi Enterprise cho nhân viên:

1. Xác định ở **mỗi chặng TLS** ai là client, ai là server, hostname nào cần xác minh.
2. Vẽ hai chuỗi chứng thư ví dụ: **public PKI** cho CDN và **private PKI** cho internal API.
3. Lập bảng SAN, EKU, CA tin cậy, thời hạn và nơi lưu private key cho từng dịch vụ.
4. Thiết kế bốn negative tests: hostname sai, CA không tin, thiếu intermediate, chứng thư hết hạn.
5. Giải thích nơi **mTLS** có giá trị và tại sao phải duy trì quyền ứng dụng riêng.
6. Đề xuất monitoring cho cert expiry, chain mismatch, CA thay đổi, proxy backend validation và phát hành chứng thư ngoài dự kiến.
7. Viết runbook khi hệ thống báo **TLS hostname mismatch** ngay sau khi đổi DNS, CDN origin hoặc load balancer.
8. Phân biệt nhiệm vụ của TLS với DNSSEC, firewall, VPN, 802.1X, IDS/IPS và cloud IAM.

**Tiêu chí đạt:** có khả năng giải thích **chính xác server identity được kiểm tra ở đâu, theo tên nào, dựa trên trust anchor nào, và hệ thống thực thi từ chối thế nào khi kiểm tra thất bại**.

## 25. Những điều cần ghi nhớ

- **Certificate chain nối leaf certificate đến trust anchor qua chữ ký và các ràng buộc của CA.** Một chứng thư hoặc root do server tự gửi không tự tạo niềm tin.
- **Server validation cần cả path validation, hostname/SAN matching, thời hạn, purpose và bằng chứng sở hữu private key**, cùng chính sách bổ sung áp dụng.
- **SAN là nguồn danh tính hostname quan trọng**; wildcard có phạm vi giới hạn và chứng thư hợp lệ cho một domain không hợp lệ cho domain khác.
- **TLS mã hóa, xác thực endpoint và bảo vệ toàn vẹn là các chức năng liên quan nhưng không đồng nhất**; bỏ qua cert verification làm suy yếu bảo mật kênh.
- **SNI chọn chứng thư, không xác thực máy chủ; CT hỗ trợ giám sát cấp phát, không thay thế hostname validation.**
- **Thu hồi bằng CRL/OCSP chịu giới hạn về cache, availability và chính sách client**; cần giám sát và phương án thay khóa khi private key bị lộ.
- **Mỗi chặng TLS sau reverse proxy/CDN/LB cần xác minh server riêng**, kể cả khi chặng phía người dùng đã có HTTPS hợp lệ.
- **mTLS, VPN và Wi-Fi Enterprise cần cấu hình đúng trust anchor, danh tính và quyền**, không dùng chứng thư để thay thế phân quyền ứng dụng.
- **Kiểm thử cả positive và negative cases, quản lý vòng đời chứng thư, không bỏ qua cảnh báo TLS** là nền tảng của vận hành kênh truyền an toàn.
