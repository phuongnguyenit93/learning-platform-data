# Root CA, intermediate CA và trust store: Xây dựng chuỗi tin cậy chứng thư số trong mạng

## 1. Bức tranh tổng quan

**Public Key Infrastructure (PKI)** là tập hợp thành phần, quy trình và chính sách dùng để phát hành, phân phối, xác minh, gia hạn và thu hồi **chứng thư số** gắn khóa công khai với một danh tính hoặc quyền hạn. Trong các hệ thống mạng, PKI hỗ trợ xác thực máy chủ TLS, thiết bị/người dùng trong mTLS, EAP-TLS của Wi-Fi doanh nghiệp, một số giải pháp VPN, API gateway và kết nối giữa các workload.

Ba khái niệm trọng tâm:

- **Root Certificate Authority (Root CA):** tổ chức/chức năng phát hành chứng thư ở tầng gốc của hệ thống phân cấp PKI. Chứng thư root thường tự ký (*self-signed*) và được sử dụng làm **trust anchor** khi được bên kiểm chứng tin cậy theo chính sách.
- **Intermediate CA (Issuing/Subordinate CA):** CA cấp dưới được CA cấp trên ký chứng thư và được quyền cấp các chứng thư tiếp theo **trong giới hạn** mà chuỗi chứng thư và chính sách cho phép. Root thường ký intermediate, còn intermediate cấp chứng thư cho máy chủ, client hoặc CA cấp dưới khác.
- **Trust store:** kho những **trust anchor hoặc cấu hình tin cậy** mà phần mềm, thiết bị hay hệ điều hành sử dụng khi xây dựng và xác minh chuỗi chứng thư. Cùng một chứng thư có thể được tin bởi ứng dụng A nhưng bị từ chối bởi ứng dụng B vì dùng trust store khác nhau.

Trong chương **PKI và chứng thư cho mạng** của học phần **SECURITY_NETWORK_SECURITY**, việc hiểu ba thành phần này là nền tảng cho **bảo vệ kết nối**, triển khai VPN, Wi-Fi 802.1X, firewall, WAF, bảo vệ DNS, phân đoạn mạng và giám sát xâm nhập. Một tunnel được mã hóa nhưng xác thực sai máy chủ, hoặc một ứng dụng tin nhầm CA, vẫn có nguy cơ bị kết nối tới điểm cuối không mong muốn.

**Ví dụ:** một client kết nối tới máy chủ VPN TLS ở tên miền được phê duyệt. Server đưa ra chứng thư TLS được một intermediate CA ký. Client kiểm tra chữ ký và các điều kiện theo chuỗi cho tới root được cấu hình tin cậy, đồng thời xác minh **tên máy chủ** và những ràng buộc của chứng thư. Nếu client chỉ thấy chứng thư có chữ ký hợp lệ nhưng không kiểm tra tên máy hoặc không có trust anchor phù hợp, kết nối chưa đáp ứng đầy đủ yêu cầu xác thực máy chủ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **root CA, intermediate CA, leaf/end-entity certificate và trust anchor**.
2. Giải thích **certificate chain**, xác thực chữ ký, đường dẫn chứng thư (*certification path*) và kiểm tra danh tính đích.
3. Hiểu ý nghĩa của **Basic Constraints, Key Usage, Extended Key Usage, SAN, AKI/SKI, pathLenConstraint và Name Constraints**.
4. Phân biệt **root store hệ điều hành, browser, JVM, container và application-specific CA bundle**.
5. Chẩn đoán lỗi TLS do thiếu intermediate, sai hostname, hết hạn, nhầm trust store hoặc thu hồi chứng thư.
6. Thiết kế vận hành PKI nội bộ: bảo vệ root key, phân cấp issuing CA, vòng đời trust distribution, rotation, thu hồi và giám sát.
7. Áp dụng tư duy chuỗi tin cậy cho VPN, 802.1X/EAP-TLS, mTLS và dịch vụ mạng mà không bỏ qua xác minh TLS.

## 2. Chứng thư X.509 là gì?

Chứng thư X.509 là cấu trúc dữ liệu chứa **khóa công khai** và thông tin được CA ký số. Phần mềm kiểm chứng dùng chữ ký CA cùng các điều kiện bảo mật để đánh giá tính hợp lệ của một chuỗi chứng thư. Khóa riêng tương ứng với khóa công khai của một máy chủ/client phải được bảo vệ; **chứng thư công khai không chứa khóa riêng**.

### 2.1. Những trường thông dụng

| Trường | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| **Subject** | Tên thực thể được chứng thư mô tả | Không mặc định Subject CN là tên TLS hợp lệ |
| **Subject Alternative Name (SAN)** | Danh tính DNS/IP hoặc loại tên khác theo profile | Phải khớp danh tính đích và cách kết nối |
| **Issuer** | Danh tính CA ký chứng thư | Chỉ là thông tin tìm CA; không tự chứng minh chữ ký đúng |
| **Subject Public Key Info (SPKI)** | Khóa công khai và thuật toán của chủ thể | Độ mạnh khóa, thuật toán, ràng buộc mục đích |
| **Signature algorithm/value** | Cách và giá trị CA ký phần nội dung được chứng thực | Xác minh bằng public key của issuer phù hợp |
| **Not Before / Not After** | Khoảng thời gian chứng thư được chấp nhận | Đồng hồ, timezone, hạn của toàn bộ chuỗi |
| **Basic Constraints** | Chứng thư có được làm CA hay không | CA:TRUE cho CA, CA:FALSE cho leaf thường |
| **Key Usage (KU)** | Những cách được phép dùng khóa, nếu có extension | CA ký chứng thư cần keyCertSign; leaf TLS cần KU phù hợp |
| **Extended Key Usage (EKU)** | Mục đích mở rộng, ví dụ serverAuth/clientAuth | Đúng profile server/client theo policy xác minh |
| **Authority Key Identifier (AKI)** | Hỗ trợ nhận diện khóa CA cấp trên | Giúp chọn issuer khi có nhiều chứng thư |
| **Subject Key Identifier (SKI)** | Định danh khóa công khai của subject | Hỗ trợ xây chuỗi; không thay xác minh chữ ký |
| **CRL Distribution Points / AIA** | Thông tin về tra cứu trạng thái hoặc issuer | Khả năng kiểm tra revocation/chain tùy client |
| **Certificate Policies** | Policy OID và phạm vi cấp phát | Chỉ có tác dụng khi bên kiểm chứng áp dụng chính sách |

Một chứng thư có trường **Issuer = “Example Root CA”** không chứng minh nó do root đó phát hành thật; phải xác minh **chữ ký, khóa issuer và chuỗi tin cậy**. Tương tự, CN ghi đúng tên miền không đủ nếu profile TLS yêu cầu SAN nhưng SAN không khớp.

### 2.2. Leaf, intermediate và root

| Loại chứng thư | Ai ký? | Có thể ký chứng thư khác? | Thường đặt ở đâu? |
| --- | --- | --- | --- |
| **Leaf / end-entity** | Intermediate CA hoặc CA có thẩm quyền theo thiết kế | Thông thường **không**, CA:FALSE | Máy chủ VPN/TLS, website, client, thiết bị |
| **Intermediate CA** | Root CA hoặc intermediate cấp trên | **Có**, nếu ràng buộc CA/KU/path và policy cho phép | CA issuing service, kho CA certificates, server chain |
| **Root CA certificate** | Thường **tự ký** | Có thể ký intermediate/CA khác trong quyền hạn | Trust store hoặc nguồn phân phối trust anchor được phê duyệt |

**Self-signed** không đồng nghĩa **trusted**. Một chứng thư tự ký do người lạ tạo không tự trở thành CA được hệ thống tin. Việc tin cậy bắt đầu khi bên kiểm chứng **cấu hình trust anchor**, không phải vì chứng thư có trường Subject trùng Issuer.

### 2.3. Phân biệt ký số với mã hóa

CA dùng **private key của CA** để ký chứng thư. Client dùng **public key của CA** để xác minh chữ ký. Điều này khác với khóa phiên TLS dùng bảo vệ dữ liệu truyền, hoặc private key của máy chủ dùng để chứng minh quyền sở hữu khóa tương ứng trong TLS.

Không cần — và không được — gửi private key của root/intermediate cho client chỉ để client “tin” chứng thư. Client thường chỉ cần **public certificate/trust anchor phù hợp** và khả năng kiểm tra chuỗi.

## 3. Mô hình phân cấp Root → Intermediate → Leaf

~~~mermaid
flowchart TD
    ROOT["Root CA<br/>Trust anchor do client cấu hình"]
    ICA["Intermediate / Issuing CA<br/>Được Root ký, CA:TRUE"]
    LEAF1["Leaf: vpn.lab.example<br/>SAN, serverAuth, CA:FALSE"]
    LEAF2["Leaf: radius.lab.example<br/>SAN, serverAuth, CA:FALSE"]
    LEAF3["Leaf: client hoặc workload<br/>Profile clientAuth phù hợp"]
    ROOT -->|"Ký chứng thư CA cấp dưới"| ICA
    ICA -->|"Phát hành"| LEAF1
    ICA -->|"Phát hành"| LEAF2
    ICA -->|"Phát hành"| LEAF3
~~~

Sơ đồ **mô tả quan hệ cấp phát** từ trên xuống. Khi client kiểm tra kết nối TLS, nó thường phải **xây chuỗi theo chiều từ leaf lên CA cấp trên cho tới trust anchor**.

### 3.1. Bước 1 — Root CA là điểm neo tin cậy

Root CA có khóa riêng rất nhạy cảm: nếu khóa bị chiếm, kẻ xấu có thể tạo chuỗi chứng thư có khả năng được nhiều hệ thống tin cậy, tùy phạm vi root đã được triển khai. Trong PKI nội bộ, root thường được thiết kế **offline hoặc giảm tối đa thời gian trực tuyến**, được bảo vệ bằng thiết bị/quy trình quản lý khóa và chỉ tham gia các hoạt động hiếm gặp như phát hành/thu hồi intermediate.

**Trust anchor** có thể được biểu diễn bởi chứng thư root tự ký nhưng về mặt mô hình tin cậy, nó là một **điểm bắt đầu được cấu hình đáng tin**, không phải kết quả “chứng minh root bằng chính chữ ký của nó”. Việc xác minh chữ ký tự ký của root có thể kiểm tra tính nhất quán của đối tượng, nhưng **không tự sinh ra lòng tin** vào root đó.

### 3.2. Bước 2 — Intermediate CA nhận quyền hạn giới hạn

Root cấp chứng thư CA cho intermediate. Chứng thư intermediate thường có:

- **Basic Constraints: CA:TRUE**, thông thường là extension critical.
- **Key Usage: keyCertSign**, và **cRLSign** khi CA dùng khóa đó ký CRL.
- **Path length constraint** nếu tổ chức cần giới hạn số tầng CA cấp dưới.
- Có thể có **Name Constraints** hoặc **Certificate Policies** để giới hạn phạm vi phát hành theo thiết kế tương thích.
- Thời hạn, định danh và thuật toán phù hợp chính sách.

Intermediate phát hành chứng thư cho dịch vụ/thiết bị; có thể tách thành những intermediate riêng cho **VPN, 802.1X/EAP-TLS, mTLS máy chủ, workload** hoặc môi trường production/lab theo mức rủi ro. Việc tách CA giúp giới hạn blast radius về mặt vận hành và quyền cấp, nhưng **nếu ứng dụng tin root rộng và policy không hạn chế, mọi intermediate được phép trong chuỗi vẫn có thể tạo chứng thư thuộc phạm vi mà client chấp nhận**. Chỉ tạo nhiều intermediate chưa tự bảo đảm quyền bị thu hẹp về mặt kỹ thuật.

### 3.3. Bước 3 — Leaf dùng xác thực dịch vụ/thiết bị

Leaf thường phải có **CA:FALSE** và mục đích dùng khóa phù hợp. Với TLS server, **SAN** ghi tên DNS hoặc địa chỉ IP mà client kết nối; **EKU serverAuth** thường cần theo profile TLS/server policy. Với EAP-TLS client certificate, EKU **clientAuth** và mối quan hệ với danh tính/tài khoản phải tuân theo RADIUS/IdP và policy tương ứng.

**Một chứng thư được ký đúng không đủ**: phải kiểm tra đúng danh tính, mục đích, thời gian, trạng thái thu hồi theo policy và chuỗi tin cậy. Chứng thư clientAuth hợp lệ không nên được chấp nhận như chứng thư web server nếu profile kiểm chứng không cho phép.

## 4. Certificate chain và quá trình xác minh

Ví dụ dịch vụ mạng:

~~~text
Client muốn kết nối: https://vpn.lab.example

Server gửi:
  [0] Leaf: SAN DNS:vpn.lab.example
      Issuer: Internal Issuing CA
  [1] Intermediate: Internal Issuing CA
      Issuer: Internal Root CA

Client có trong trust store:
  [T] Root: Internal Root CA

Đường dẫn xác thực dự kiến:
  Leaf → Intermediate → Root (trust anchor)
~~~

**Máy chủ thường gửi leaf và những intermediate cần thiết**, không nhất thiết gửi root vì root phải được client tin sẵn; gửi một root bất kỳ từ server **không khiến client tự tin root đó**. Một số ứng dụng có thể lấy intermediate từ cache hoặc URL AIA, nhưng **không nên phụ thuộc vào khả năng tự tải intermediate của mọi client**.

### 4.1. Các kiểm tra chính

Đối với một kết nối TLS thông thường, hệ thống xác minh thường cần kiểm tra:

1. **Đường dẫn issuer:** có thể nối leaf đến issuer thích hợp rồi đến một trust anchor được phép dùng không?
2. **Chữ ký:** chứng thư từng cấp có được ký bởi private key tương ứng với public key của issuer không?
3. **Tính hợp lệ thời gian:** các chứng thư trong path còn trong khoảng Not Before/Not After thích hợp không?
4. **Basic Constraints và path length:** chứng thư dùng làm CA có đủ quyền ký, số tầng CA có tuân ràng buộc không?
5. **Key Usage và Extended Key Usage:** từng khóa/chứng thư được sử dụng đúng chức năng theo profile không?
6. **Name Constraints, policy và các extension critical:** path có tuân ràng buộc mà client cần hỗ trợ không?
7. **Revocation:** client/policy có kiểm tra CRL hoặc OCSP và xử lý được kết quả không?
8. **Danh tính endpoint:** SAN của leaf có khớp hostname hoặc IP thực sự đang kết nối theo chuẩn áp dụng không?
9. **Chính sách ứng dụng:** có yêu cầu CA riêng, mutual TLS, pinning, thuật toán tối thiểu hoặc danh tính thiết bị không?

Các bước trên là **khung khái niệm**, không khẳng định thứ tự thực thi giống nhau trong mọi TLS library. RFC 5280 định nghĩa path validation cho PKIX; xác minh tên TLS được chuẩn hóa trong các tài liệu như RFC 9525. Hệ điều hành/trình duyệt/ứng dụng có thể áp dụng thêm yêu cầu riêng.

### 4.2. Chữ ký đúng nhưng root không tin cậy

Giả sử một leaf và intermediate có chữ ký, thời hạn và SAN đều đúng nhưng trust store của client **không có trust anchor phù hợp**. Kết nối có thể thất bại với lỗi như *unknown CA*, *unable to get local issuer certificate* hoặc lỗi path construction, tùy thư viện.

Không nên sửa bằng cách **tắt certificate validation**. Nếu đây là PKI nội bộ thực sự được tổ chức phê duyệt, phân phối đúng **root trust anchor** qua MDM/GPO/quy trình quản lý thiết bị, giữ nguyên kiểm tra tên và cấu trúc chain.

### 4.3. Root đã tin nhưng server thiếu intermediate

Client đã tin root không có nghĩa client **tự biết mọi intermediate do root cấp**. Khi server chỉ gửi leaf, client có thể thiếu chứng thư intermediate để xác minh chữ ký và tạo path.

Một số client tìm được intermediate trong cache hoặc tự tải theo **Authority Information Access (AIA)**; client khác không làm vậy hoặc không truy cập được nơi tải. Vì thế cấu hình TLS server nên cung cấp **đầy đủ chain cần thiết (leaf + intermediates)**. Hướng sửa ưu tiên là hoàn thiện chain của server, không phải “cài intermediate vào kho root” cho toàn bộ thiết bị.

### 4.4. Name/SAN và mục đích xác thực

Nếu leaf chỉ có **SAN DNS:api.lab.example** nhưng client kết nối tới **vpn.lab.example**, chữ ký và root vẫn có thể hợp lệ nhưng **hostname verification phải thất bại** theo policy TLS server phù hợp.

Tương tự, chứng thư có SAN cho hostname nhưng ứng dụng kết nối trực tiếp bằng **địa chỉ IP** thường cần **iPAddress SAN** khớp IP, không dựa vào chuỗi DNS SAN chứa văn bản giống địa chỉ. **Subject Common Name (CN)** không phải cách thay SAN hiện đại đáng tin cho xác thực DNS TLS.

Không dùng wildcard tùy tiện trên nhiều cấp miền; quy tắc matching wildcard bị giới hạn theo chuẩn và triển khai. Một chứng thư cấp cho **`*.lab.example`** không có nghĩa nó hợp lệ cho **`a.b.lab.example`**.

### 4.5. Basic Constraints và Key Usage

Một certificate có public key và chữ ký hợp lệ nhưng không được phép làm CA **không thể tự nhiên được dùng để ký subordinate certificates**. Path validation phải tôn trọng **CA:TRUE**, **keyCertSign** và các điều kiện liên quan.

Ví dụ:

~~~text
Root CA:
  Basic Constraints: CA:TRUE, pathlen:1
  Key Usage: keyCertSign, cRLSign

Intermediate CA:
  Basic Constraints: CA:TRUE, pathlen:0
  Key Usage: keyCertSign, cRLSign

Leaf VPN server:
  Basic Constraints: CA:FALSE
  Key Usage: digitalSignature (theo TLS profile)
  Extended Key Usage: serverAuth
  SAN: DNS:vpn.lab.example
~~~

**pathLenConstraint** giới hạn số **CA trung gian không self-issued** được phép nằm dưới CA đó trên certification path, không phải số leaf certificate được phát hành. Ví dụ intermediate có **pathlen:0** vẫn có thể cấp **nhiều leaf**, nhưng không thể tạo tiếp một intermediate thông thường hợp lệ bên dưới theo path validation.

### 4.6. EKU: serverAuth và clientAuth

| Profile | Mục đích | Rủi ro khi kiểm tra quá lỏng |
| --- | --- | --- |
| **serverAuth** | Xác thực TLS server | Chấp nhận chứng thư không dành cho máy chủ |
| **clientAuth** | Xác thực TLS client | Dùng chứng thư không đúng vai trò hoặc nhóm người dùng |
| **Code signing** | Xác thực mã/phần mềm được ký | Nhầm chứng thư ký code với chứng thư TLS |
| **Các EKU chuyên dụng khác** | Theo chuẩn và ứng dụng cụ thể | Quyền khóa bị dùng sai mục đích |

Không phải mọi môi trường đều dùng đúng một EKU trong mọi chứng thư, và path validation về EKU có chi tiết theo profile. Một thiết kế an toàn phải **quy định mục đích cấp chứng thư và cách bên nhận kiểm tra mục đích**, thay vì chỉ cần “được CA ký là được”.

## 5. Trust store: Nơi quyết định CA nào được tin

Một ứng dụng kiểm tra TLS phải có **tập trust anchor được phép** và policy xác minh phù hợp. Tập này có thể do hệ điều hành, nhà cung cấp trình duyệt, JVM/runtime, ứng dụng hoặc quản trị viên doanh nghiệp kiểm soát.

**Điểm cốt lõi:** *cài một root CA vào một máy* **không đồng nghĩa** *mọi ứng dụng trên máy đó đều tin root ấy*. Ngược lại, một ứng dụng dùng trust store riêng có thể tin một CA mà hệ điều hành không tin.

### 5.1. Trust store khác certificate chain server gửi

| Thành phần | Do ai quản lý? | Nội dung điển hình | Vai trò |
| --- | --- | --- | --- |
| **Server certificate chain** | Chủ quản TLS server/load balancer/VPN gateway | Leaf + intermediate cần thiết | Cung cấp chứng thư để client xây path |
| **System trust store** | Nhà cung cấp OS và quản trị thiết bị | Root/anchor được phê duyệt | Tin hoặc không tin CA theo phạm vi OS |
| **Browser trust store** | Trình duyệt, OS hoặc phối hợp tùy sản phẩm/cấu hình | Root/CA theo chính sách trình duyệt | Xác thực TLS mà browser sử dụng |
| **JVM truststore** | Runtime Java, ứng dụng và quản trị viên | Các trust anchor đã cấu hình, thường qua cacerts hoặc store riêng | Dùng bởi các Java TLS clients tương ứng |
| **Application CA bundle** | Ứng dụng/thư viện/packaging | Root bundle hoặc danh sách CA riêng | Xác minh theo cấu hình của ứng dụng |
| **Mutual TLS trust config** | Server/API gateway/ứng dụng | Các CA được phép cấp client certificate | Xác thực client, không chỉ xác thực server |
| **Certificate/key store** | Dịch vụ cần dùng private key | Leaf + private key, đôi khi chain | Chứng minh danh tính khi làm server/client |

**Trust store** và **keystore** có thể dùng chung định dạng file (PEM, PKCS#12, JKS tùy nền tảng) nhưng **khác vai trò**. Một nơi chứa private key không mặc nhiên là kho trust anchor, và một trust bundle chỉ gồm public certificates không cần giữ private key của CA.

### 5.2. Hệ điều hành và trình duyệt

- **Windows:** có các kho chứng thư phân theo **Local Machine** và **Current User**, cùng các nhóm trust như Trusted Root Certification Authorities, Intermediate Certification Authorities hoặc chính sách doanh nghiệp. Phạm vi cài đặt ảnh hưởng ứng dụng nào nhận được anchor.
- **Linux:** nhiều bản phân phối quản lý **CA bundle/certificate directories** bằng cơ chế riêng. Vị trí file và lệnh cập nhật khác nhau theo distro, container image và thư viện TLS.
- **macOS/iOS:** có hệ thống trust và các cơ chế profile/MDM; trạng thái tin cậy có thể phụ thuộc mục đích, chính sách thiết bị và tùy chọn explicit trust.
- **Android:** các phiên bản, chính sách ứng dụng và cấu hình trust có thể khác nhau. Không mặc định một app Android sẽ tin mọi root CA do người dùng thêm.
- **Trình duyệt:** một số browser sử dụng **trust program/store riêng**, trong khi trình duyệt hoặc phiên bản khác có thể dùng tích hợp với OS hoặc chính sách doanh nghiệp. Không thể suy ra tất cả trình duyệt trên cùng máy đều có kết quả xác minh giống nhau.

Đây là **nguyên tắc triển khai**, không phải cam kết rằng một trình duyệt luôn dùng một kho nhất định trên mọi OS/phiên bản. Khi có lỗi, phải xác định **ứng dụng và TLS backend cụ thể đang dùng trust source nào**.

### 5.3. Java, ứng dụng server và container

Ứng dụng Java có thể dùng truststore mặc định của JVM như **cacerts**, một truststore riêng được chỉ định qua cấu hình, hoặc một thư viện với cơ chế TLS khác. Nếu một đội thêm root vào trust store của OS nhưng ứng dụng Java vẫn báo **PKIX path building failed**, nguyên nhân có thể là JVM **không sử dụng chính bundle vừa thay đổi**.

Tương tự, một container chạy trong Kubernetes có filesystem/CA bundle riêng. Root được tin ở **host node** không tự xuất hiện trong container, đặc biệt với image tối giản. Dù service mesh tạo kênh mTLS riêng, ứng dụng vẫn có thể thực hiện HTTPS đến dịch vụ khác bằng trust bundle riêng.

### 5.4. Public CA và Private CA

| Khía cạnh | Publicly trusted CA | Private/internal CA |
| --- | --- | --- |
| Ai kiểm soát trust anchor? | Chương trình root trust của OS/browser và chính sách liên quan | Tổ chức chủ động phân phối cho thiết bị/ứng dụng được phép |
| Phạm vi thông dụng | Website và dịch vụ công khai với client không quản trị | VPN nội bộ, 802.1X, mTLS workload, thiết bị |
| Triển khai lên khách ngoài tổ chức | Thường không cần thêm root thủ công nếu client cập nhật hợp lệ | Cần kênh phân phối trust được quản lý hoặc giải pháp khác |
| Quy trình cấp phát | Theo tiêu chuẩn và yêu cầu của chương trình public trust | Theo chính sách PKI nội bộ, không mặc định tương đương public WebPKI |
| Rủi ro riêng | Root program/phạm vi trình duyệt, chứng thư công khai và vận hành CA | Cài root quá rộng, phân phối root thiếu kiểm soát, private key CA bị lộ |

**Không phải “internal CA” là không có rủi ro.** Khi một root nội bộ được thêm làm trust anchor vào toàn bộ thiết bị, phạm vi tin cậy được mở ra. Nếu issuing CA dưới root được phép cấp chứng thư cho mọi hostname mà ứng dụng chấp nhận, cấp phát sai hoặc lộ khóa có thể ảnh hưởng tới nhiều kết nối hơn phạm vi ứng dụng dự kiến.

### 5.5. Trust store và certificate pinning

**Certificate/public-key pinning** là một cơ chế ứng dụng có thể dùng để ràng buộc tin cậy chặt hơn với chứng thư hoặc khóa nhất định. Nó **khác với** cài một root CA vào trust store. Pinning có thể ngăn những chứng thư hợp lệ theo CA nhưng không thuộc tập đã được ứng dụng cho phép, song cũng có thể làm dịch vụ ngừng hoạt động khi leaf/key được xoay mà pin không được cập nhật.

Không dùng cách **import leaf vào Trusted Root store** như một phương pháp “pinning” tùy tiện. Quy tắc trust anchor, kiểm tra EKU, pinning và xoay khóa phải do ứng dụng/nền tảng hỗ trợ, có chiến lược backup/rotation.

## 6. Ai cần tin CA nào trong các mô hình mạng?

### 6.1. VPN TLS / SSL VPN

Khi một người dùng kết nối vào VPN gateway qua TLS:

1. **Gateway** trình chứng thư máy chủ và những intermediate cần thiết.
2. **VPN client** kiểm chứng chain đến trust anchor được phép và kiểm tra **tên gateway** mà client cấu hình.
3. Nếu VPN hỗ trợ **mTLS/device certificate**, gateway còn kiểm tra chứng thư phía client theo trust policy riêng.
4. Sau xác thực TLS có thể còn các bước **IdP/MFA, posture, authorization và cấp VPN profile**.

Root CA để **VPN client xác thực gateway** không nhất thiết là root CA để **gateway xác thực client certificates**. Hai trust sets có thể khác nhau và nên được thiết kế rõ.

**Rủi ro:** chỉ cài root mà không bật kiểm tra hostname có thể khiến client tin một máy chủ khác cũng có chứng thư hợp lệ từ cùng CA. Cần cấu hình expected server name/identity, không chỉ chọn “Accept any certificate issued by our CA”.

### 6.2. Wi-Fi WPA-Enterprise / EAP-TLS

Trong Wi-Fi doanh nghiệp, thiết bị đầu cuối (*supplicant*) xác thực **máy chủ EAP/RADIUS** theo phương thức EAP và chuỗi chứng thư, thường thông qua cấu hình CA tin cậy cùng **expected server identity**. Với EAP-TLS, phía máy chủ cũng kiểm tra **client certificate** và ánh xạ danh tính/quyền theo chính sách.

~~~mermaid
sequenceDiagram
    participant C as Supplicant / laptop
    participant A as Access point / authenticator
    participant R as RADIUS / EAP server
    C->>A: Kết nối SSID 802.1X
    A->>R: Chuyển thông điệp EAP theo cơ chế hệ thống
    R-->>C: Server certificate chain qua EAP/TLS
    Note over C: Kiểm tra chain đến CA được phép và tên server
    C-->>R: Client certificate / TLS proof khi EAP-TLS
    Note over R: Kiểm tra client chain, EKU, danh tính và policy
    R-->>A: Kết quả xác thực/ủy quyền
    A-->>C: Cấp kết nối theo chính sách nếu thành công
~~~

Sơ đồ đơn giản hóa EAP/TLS handshake và quan hệ AP–RADIUS; **AP không mặc nhiên là máy chủ TLS được supplicant xác thực**. Khi một thiết bị Wi-Fi chỉ “trust any RADIUS server certificate”, nó có thể bị lừa tương tác với một server giả mạo trong các điều kiện tấn công thích hợp. Phải quản lý **CA và danh tính EAP server được kỳ vọng**, không chỉ SSID.

### 6.3. Mutual TLS giữa workload/API

Trong **mTLS**, cả hai phía có thể trình chứng thư:

- Client xác minh chứng thư **server** với truststore server-side trust roots và tên/identity đích.
- Server xác minh chứng thư **client** theo truststore được phép, EKU/client identity và authorization.
- Service mesh có thể quản lý CA ngắn hạn, workload identity và xoay chứng thư tự động.

**mTLS bảo đảm danh tính theo chứng thư và chính sách kiểm tra**, không tự động cấp quyền vào mọi API. Sau khi xác thực, ứng dụng vẫn cần authorization theo workload, endpoint và action.

### 6.4. Reverse proxy, WAF và ingress

Trong một dịch vụ HTTPS qua WAF/reverse proxy:

- Client kiểm tra certificate chain của **điểm kết thúc TLS phía public**.
- Proxy có thể lập **một kết nối TLS khác** tới backend và phải có truststore/hostname verification tương ứng.
- Nếu proxy yêu cầu mTLS từ client, nó cần trust set xác minh **client certificates** riêng.

Một HTTPS “xanh” ở trình duyệt **không chứng minh** kết nối proxy → backend cũng được xác minh chính xác. Kiến trúc phải mô tả **hai cạnh TLS** và trust boundary của mỗi cạnh.

### 6.5. DNS over TLS và các dịch vụ khác

Kết nối **DNS over TLS (DoT)**, HTTPS API, syslog over TLS hoặc LDAP over TLS đều cần danh tính server và trust source phù hợp. Khi ứng dụng kết nối tới tên dịch vụ khác với SAN hiện có, lỗi hostname không thể được giải quyết an toàn bằng cách chỉ thêm nhiều CA vào trust store.

### 6.6. TLS inspection và CA được phân phối nội bộ

Một số doanh nghiệp có hệ thống kiểm tra HTTPS được quản lý, yêu cầu thiết bị tin **một CA chuyên dụng của hệ thống kiểm tra** theo chính sách. Vì CA đó có thể phát hành chứng thư mà client tin cho các tên miền đi qua điểm kiểm soát, phạm vi rủi ro và ảnh hưởng quyền riêng tư rất lớn.

Cần thiết kế **ủy quyền, phạm vi, phân tách vai trò, bảo vệ khóa, audit, ngoại lệ theo pháp lý/quy định và vòng đời trust**. Không dùng root CA cấp rộng cho mọi mục đích, không yêu cầu thiết bị không được quản lý tự cài CA lạ và không hướng dẫn người dùng tắt cảnh báo certificate.

## 7. Name Constraints, path length và phạm vi ủy quyền

Một mô hình PKI an toàn cần kiểm soát **CA nào được ký cho những danh tính nào**.

### 7.1. pathLenConstraint không giới hạn số leaf

Giả sử Root CA có **pathLenConstraint = 1**; nó có thể cấp một intermediate CA thông thường, intermediate đó có thể cấp nhiều leaf. Nếu intermediate có **pathLenConstraint = 0**, nó không được tạo một intermediate cấp dưới thông thường trên một path hợp lệ (trừ những chi tiết ngoại lệ self-issued được chuẩn quy định).

Giới hạn path length không tự giới hạn:

- Số leaf có thể cấp.
- Danh sách DNS SAN trong leaf.
- Nhóm máy chủ hoặc user được cấp chứng thư.
- Những ứng dụng chấp nhận CA đó như trust anchor.

Muốn giới hạn phạm vi phát hành cần thêm **chính sách issuance, Name Constraints khi tương thích và authorization ở ứng dụng**.

### 7.2. Name Constraints

Một subordinate CA có thể mang **Name Constraints** để giới hạn tên cho phép trong các chứng thư phía dưới, ví dụ chỉ DNS dưới một namespace được phép. Đây là cơ chế PKIX có các quy tắc chi tiết về **permitted/excluded subtrees**, loại tên và khả năng áp dụng.

**Không nên hiểu “Name Constraints cho `lab.example`” như một bộ lọc chuỗi đơn giản**: cần kiểm tra semantics DNS/IP name, path validation và các client mà tổ chức sử dụng. Client không hỗ trợ đúng các ràng buộc critical có thể từ chối path; cấu hình không nhất quán có thể gây lỗi kết nối.

### 7.3. Phân cấp CA theo mục đích

| Phân cấp đề xuất | Chức năng | Lý do |
| --- | --- | --- |
| **Offline Root CA** | Ký intermediate và vận hành root lifecycle | Giảm sử dụng root private key |
| **VPN / RADIUS issuing CA** | Cấp certificate cho VPN server hoặc EAP infrastructure | Tách policy, key access và vòng đời của hạ tầng truy cập |
| **Client/device issuing CA** | Cấp cert clientAuth/thiết bị | Gắn với MDM, danh tính và thu hồi thiết bị |
| **Workload/service issuing CA** | Cấp certificate mTLS ngắn hạn | Phù hợp workload automation, xoay thường xuyên |
| **Lab/test PKI riêng** | Môi trường thử nghiệm | Tránh root thử nghiệm được tin rộng ở production |

Đây là mẫu tổ chức chứ không phải kiến trúc cứng. Nếu tất cả intermediate đều có phạm vi cấp và được clients tin rộng như nhau, việc tách nhánh chỉ giúp vận hành mà **chưa hạn chế quyền tin cậy ở bên nhận**. Quyền cấp phải gắn với enforcement thực tế ở CA và verifier.

## 8. Cross-signing và nhiều đường xây chuỗi

Một intermediate có thể có **nhiều chứng thư** chứa cùng public key/subject nhưng được ký bởi các CA cấp trên khác nhau. Điều này thường liên quan đến **cross-signing**, chuyển đổi root hoặc hỗ trợ các tập client có trust store khác nhau.

~~~mermaid
flowchart TD
    OLD["Old Root CA<br/>Có trong trust store client cũ"]
    NEW["New Root CA<br/>Có trong trust store client mới"]
    IC1["Intermediate CA<br/>Chứng thư do Old Root ký"]
    IC2["Intermediate CA<br/>Chứng thư do New Root ký"]
    LEAF["Leaf dịch vụ<br/>Được intermediate ký"]
    OLD --> IC1
    NEW --> IC2
    IC1 -. "Cùng identity/key issuer theo thiết kế" .-> LEAF
    IC2 -. "Đường thay thế" .-> LEAF
~~~

Khi có nhiều đường hợp lệ, **path building** có thể chọn một chuỗi tới root client đang tin. Kết quả tùy thuật toán tìm chain, store, dữ liệu intermediate sẵn có, constraints, revocation và chính sách runtime.

### 8.1. Vì sao cùng server, hai client có kết quả khác?

Giả sử:

- Client A chỉ tin **Old Root**.
- Client B chỉ tin **New Root**.
- Server đang gửi một phiên bản intermediate được ký bởi **Old Root**.
- Client B không có chứng thư intermediate tương ứng được ký bởi **New Root**.

Client A có thể xây được path, còn B có thể báo lỗi dù leaf/public key của dịch vụ không đổi. Một số client có thể tìm intermediate thay thế trong cache/AIA; không nên dựa vào điều đó khi vận hành.

### 8.2. Đừng chẩn đoán chain chỉ bằng Subject/Issuer

Trong tình huống cross-signing, Subject và Issuer có thể trông giống nhau hoặc không đủ phân biệt nhiều chứng thư. Hãy kiểm tra **fingerprint, SPKI, AKI/SKI, chữ ký, thời hạn, trust anchor và chuỗi cụ thể được verifier chọn**.

Việc một certificate “đã hết hạn” trong danh sách server gửi không tự có nghĩa mọi client đều thất bại nếu client có một **đường thay thế hợp lệ**; ngược lại, client không có đường thay thế có thể thất bại. Cần xem path cuối cùng trên ứng dụng đó.

## 9. Thu hồi chứng thư và trạng thái tin cậy

PKI không chỉ cấp chứng thư rồi đợi hết hạn. Trong một số trường hợp cần **thu hồi** quyền tin cậy trước khi Not After, ví dụ lộ private key, cấp sai danh tính, tài khoản/thiết bị bị thu hồi hoặc intermediate có sự cố.

### 9.1. CRL

**Certificate Revocation List (CRL)** là danh sách chứng thư bị CA thu hồi, thường được CA hoặc thành phần được ủy quyền ký và công bố theo policy. Verifier có thể tải/kiểm tra CRL từ địa chỉ trong chứng thư hoặc cơ chế nội bộ được cấu hình.

Cần xem:

- CRL có được ký bởi issuer phù hợp không?
- Thời điểm **thisUpdate / nextUpdate** và dữ liệu có đủ mới không?
- Certificate serial number có bị thu hồi không?
- Verifier có được phép truy cập CRL Distribution Point không?
- Các vấn đề về delta CRL/indirect CRL có được stack hỗ trợ khi dùng không?

### 9.2. OCSP

**Online Certificate Status Protocol (OCSP)** cho phép hỏi về trạng thái chứng thư qua responder theo chuẩn. Một số server TLS có thể đưa **OCSP stapled response** khi client hỗ trợ và cấu hình thích hợp.

Không cho rằng mọi trình duyệt, API client hoặc thiết bị mạng đều **bắt buộc từ chối** khi OCSP/CRL không truy cập được. **Soft-fail, hard-fail, caching và chính sách revocation** khác nhau theo nền tảng, profile và môi trường. Một hệ thống cần bảo đảm thu hồi nhanh phải kiểm chứng **hành vi thực sự**, không chỉ bật một ô “Check revocation”.

### 9.3. Thu hồi leaf, intermediate và root khác nhau

| Sự kiện | Biện pháp thường cần | Điểm cần chú ý |
| --- | --- | --- |
| **Leaf bị lộ private key** | Revoke leaf, cấp leaf/key mới, cập nhật server/client | Đánh giá các hệ thống đã dùng chứng thư đó |
| **Intermediate CA bị lộ** | Ngừng issuance, thu hồi CA certificate nếu cơ chế hỗ trợ, thay CA/leaf, phối hợp trust và revocation | Ảnh hưởng nhiều dịch vụ/thiết bị, cần kế hoạch di chuyển |
| **Root CA bị lộ hoặc không còn đáng tin** | Phân phối chính sách **distrust/remove trust anchor**, chuyển chuỗi sang root mới và xử lý CA cấp dưới | Không thể trông chờ vào việc “root tự thu hồi chính nó” để mọi client tự bỏ tin |
| **Certificate hết hạn** | Cấp/gia hạn và triển khai lại chain đúng | Cần kiểm tra đồng thời private key, SAN, policy và ràng buộc |

Đối với root, **trust store update/distrust** là một thành phần quan trọng vì tin cậy gốc được cấp bởi cấu hình của bên kiểm chứng. Việc thu hồi một chứng thư ở repository không thay thế quản lý root trust anchor đang nằm trong hàng nghìn thiết bị.

### 9.4. Certificate Transparency và PKI nội bộ

**Certificate Transparency (CT)** là cơ chế nhật ký công khai quan trọng của **WebPKI**, đặc biệt với chương trình public trust cho TLS website. Nó giúp quan sát chứng thư đã được phát hành và hỗ trợ phát hiện sai sót.

**Private PKI** không tự phải đáp ứng cùng toàn bộ quy tắc CT của public root programs; tuy nhiên vẫn cần **issuance audit, asset inventory, phát hiện cấp phát bất thường và policy review**. Không coi CT là cơ chế thu hồi hay thay thế việc kiểm tra chữ ký và trust store.

## 10. Vòng đời khóa và chứng thư trong kiến trúc PKI

Một mô hình PKI tốt không chỉ hoạt động khi chứng thư mới được phát hành; nó phải tiếp tục an toàn khi **khóa bị nghi lộ, CA hết hạn, thiết bị được thu hồi, ứng dụng đổi hostname hoặc root được thay thế**.

### 10.1. Quản lý root private key

Root private key là tài sản nhạy cảm nhất trong phần lớn PKI phân cấp. Thực hành quản trị thường gồm:

1. **Root offline** hoặc hạn chế nghiêm ngặt thời điểm có thể dùng private key.
2. **Key ceremony** khi tạo hoặc sử dụng root key, với danh sách người có quyền và hồ sơ kiểm toán.
3. **HSM hoặc cơ chế bảo vệ khóa phù hợp** với yêu cầu tổ chức; bảo đảm backup/khôi phục không làm lộ key.
4. **Phân tách nhiệm vụ:** người quản lý tài nguyên, người duyệt issuance và người vận hành hệ thống không cần có toàn quyền như nhau.
5. **Tài liệu CP/CPS** hoặc quy định tương đương về issuance, revocation, key algorithms, certificate profiles và thời hạn.
6. **Thử nghiệm recovery** trên môi trường phù hợp; HSM có backup nhưng chưa bao giờ thử khôi phục vẫn có rủi ro vận hành.

Root private key **không cần có mặt** trên VPN gateway, web server, Wi-Fi controller hoặc thiết bị người dùng. Máy chủ thường chỉ dùng **private key của leaf** tương ứng.

### 10.2. Bảo vệ intermediate CA

Issuing CA thường có tần suất hoạt động cao hơn root. Nếu intermediate bị chiếm quyền, attacker có thể cấp những chứng thư được chuỗi CA cho phép, tùy ràng buộc và chính sách client.

Cần:

- Bảo vệ signing key, hệ điều hành, API và tài khoản quản trị issuing CA.
- Tách quyền **approve** và **issue**, hạn chế cấp phát tùy tiện theo template.
- Giới hạn SAN/DNS/URI/IP và subject phù hợp chính sách; không tin đầu vào CSR khi chưa xác minh quyền kiểm soát tên hoặc thiết bị.
- Giám sát mọi phát hành/thu hồi cùng serial, requester, CA identity và ticket.
- Có runbook **disable issuance**, revoke intermediate nếu cần, phân phối chain thay thế và kiểm chứng lại client.

**CA certificate chứa CA:TRUE** không có nghĩa CA đó tự áp dụng mọi chính sách nghiệp vụ; hệ thống issuance và bên verifier phải cùng thực thi những giới hạn được thiết kế.

### 10.3. Tính thời hạn CA và leaf

Chứng thư CA thường sống lâu hơn leaf, nhưng **không có một tỷ lệ thời hạn bắt buộc cho mọi tổ chức**. Một số workload sử dụng chứng thư rất ngắn hạn nhờ tự động hóa; thiết bị IoT có khả năng cập nhật kém có thể cần chiến lược đặc biệt với phương án thu hồi/đổi khóa phù hợp.

Quan trọng:

- Leaf không nên được phát hành với thời hạn vượt policy và khả năng chứng thực của CA.
- **Một path chỉ hợp lệ khi các chứng thư cần thiết trên path còn được chấp nhận**; leaf còn hạn không cứu được chain khi intermediate đã hết hạn theo policy.
- Không đợi đến sát Not After mới phát hành lại: cần thời gian rollout, cache refresh, restart/reload và hỗ trợ thiết bị offline.
- Với chứng thư ngắn hạn, **automated renewal** giúp giảm lỗi vận hành nhưng chỉ an toàn nếu bảo vệ enrollment identity và private keys.

### 10.4. ACME, EST và cơ chế cấp phát tự động

Một số môi trường dùng **ACME (RFC 8555)** để tự động hóa quản lý chứng thư phù hợp use case; hệ thống doanh nghiệp/thiết bị có thể dùng **EST (RFC 7030)** hoặc giao thức enrollment khác. Các giải pháp này hỗ trợ vòng đời issuance/renewal nhưng **không tự xác định đúng quyền cấp chứng thư nếu policy enrollment bị sai**.

Ví dụ nếu một service account có thể yêu cầu chứng thư cho hostname không thuộc quyền, tự động hóa sẽ **cấp sai nhanh hơn**. Phải xác thực requester, SAN được phép, scope và audit mỗi certificate issuance.

## 11. Xoay CA và phân phối trust store không gián đoạn

### 11.1. Xoay leaf certificate

Một quy trình thường dùng:

1. Kiểm tra hostname/SAN, algorithm, EKU, private key policy và các client đang dùng.
2. Tạo CSR hoặc làm enrollment theo phương thức được phê duyệt, **không chuyển private key qua kênh không an toàn**.
3. Issuing CA ký leaf mới và cung cấp chain đúng.
4. Cấu hình dịch vụ dùng **leaf + private key tương ứng + intermediates phù hợp**.
5. Kiểm thử từ client thật hoặc lab tương đương: hostname, trust path, TLS, backend mTLS nếu có.
6. Triển khai theo canary/rollout, theo dõi lỗi handshake và khả năng rollback.
7. Thu hồi/loại khóa cũ khi chính sách yêu cầu, tránh để private key cũ nằm không bảo vệ trong backup cấu hình.

**Không cần thay root trên mọi thiết bị** chỉ vì leaf được gia hạn bằng cùng intermediate/chuỗi còn được tin, trừ khi mục tiêu của lần thay đổi là chuyển trust anchor.

### 11.2. Xoay intermediate CA

Khi issuing CA sắp hết hạn hoặc được thay bằng khóa mới:

1. Chuẩn bị issuing CA mới với profile/constraints phù hợp.
2. Cho phép hệ thống enrollment phát hành leaf từ CA mới theo kế hoạch.
3. Phân phối **intermediate chain** mới trên server hoặc tới client nơi thật sự cần, không tự động đưa intermediate vào root store.
4. Kiểm thử những thiết bị khác nhau: OS, JVM, browser, Wi-Fi supplicant, VPN client và container.
5. Theo dõi leaf còn ký bởi CA cũ, các workload chưa cập nhật và trạng thái revocation.
6. Ngừng issuance ở CA cũ, thu hồi/loại chứng thư cũ theo kế hoạch và quản lý thời kỳ chuyển tiếp.

Một **root trust anchor** vẫn có thể giữ nguyên trong khi intermediate đổi. Tuy nhiên các chính sách ràng buộc chain, pinning, cache và revocation có thể làm một số client thất bại; cần đo đạc trước rollout.

### 11.3. Xoay root CA

**Root rollover** phức tạp hơn do trust anchor phải được phân phối tới các bên kiểm chứng. Một hướng triển khai có kiểm soát:

~~~mermaid
flowchart LR
    A["1. Có Root A<br/>Thiết bị đang tin"] --> B["2. Phân phối Root B<br/>Trong khi vẫn tin Root A"]
    B --> C["3. Dựng chain/issuance mới<br/>Kiểm thử trên client"]
    C --> D["4. Chuyển dịch vụ sang chain Root B<br/>Theo rollout"]
    D --> E["5. Xác minh mọi client quan trọng<br/>và khả năng thu hồi"]
    E --> F["6. Loại Root A khỏi trust<br/>Khi an toàn và được phê duyệt"]
~~~

Trong giai đoạn **overlap**, client có thể tin cả root cũ và root mới. Đây là rủi ro cần được quản trị: thời gian overlap càng dài, phạm vi trust của cả hai root càng tồn tại lâu.

**Không xóa root cũ đầu tiên** khi dịch vụ và client chưa chuyển xong: ứng dụng offline, máy in, thiết bị IoT, JVM dùng cacerts riêng hoặc VPN client ngoài văn phòng có thể mất kết nối. Ngược lại, cũng không duy trì root cũ vô thời hạn khi nó không còn được phép tin.

### 11.4. Thay trust store và sự khác biệt giữa “file đã cập nhật” với “app đang dùng”

Sau khi cập nhật CA bundle hoặc truststore:

- Ứng dụng có thể cần **reload/restart** để sử dụng trust mới.
- Container cũ có thể cần **rebuild/redeploy**; sửa trust store ở host không đủ.
- Browser/profile khác nhau có thể có kết quả khác nhau.
- Device đang offline có thể chưa nhận policy MDM/GPO.
- Một số ứng dụng có certificate pinning cần cập nhật pin/backup pin trước rollout.

Không ghi “đã triển khai trust root” chỉ dựa vào trạng thái công cụ quản lý. Cần xác minh từ **endpoint và ứng dụng cụ thể** bằng kết nối test được phép.

## 12. Các lỗi PKI thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| **unknown ca / untrusted issuer** | Trust anchor không có hoặc không được phép dùng | Xác định truststore thật của ứng dụng và root đang cần |
| **unable to get local issuer certificate** | Thiếu intermediate, sai chain, thiếu trust anchor | Server gửi gì, AKI/issuer nào, chain nào client xây được |
| **hostname mismatch** | SAN không chứa danh tính client dùng để kết nối | Kiểm tra DNS/IP SAN, SNI, FQDN, proxy/redirect |
| **certificate has expired** | Leaf/intermediate hết hạn, client clock sai | In NotBefore/NotAfter cả chain và đồng bộ thời gian |
| **certificate not yet valid** | Chứng thư chưa đến NotBefore hoặc đồng hồ sai | Kiểm tra UTC/time sync và thời gian phát hành |
| **unsupported certificate purpose** | KU/EKU hoặc certificate profile không phù hợp | ServerAuth/clientAuth, path constraints và policy |
| **invalid CA / basic constraints failure** | Intermediate không được phép ký, pathLen vượt giới hạn | Basic Constraints, keyCertSign, chain thực tế |
| **certificate revoked** | CRL/OCSP/policy báo trạng thái bị thu hồi | Serial, issuer, responder, thời điểm và chính sách |
| **unable to check revocation** | Không tới được CRL/OCSP hoặc dữ liệu lỗi | Network, DNS, firewall, proxy và fail policy |
| **chain works on some clients** | Khác trust store, AIA/cache, cross-signing, thuật toán | Test từng runtime, path thực tế, intermediates |
| **mTLS client rejected** | Server không tin client CA, EKU/client identity sai | Truststore phía server và authorization mapping |
| **EAP-TLS Wi-Fi authentication fails** | Server cert name/trust sai hoặc client cert/policy bị từ chối | Supplicant, RADIUS/EAP logs, profile thiết bị |
| **VPN TLS báo lỗi sau rotation** | Chain trên gateway cũ/mới khác nhau, thiếu root rollout | Gateway cluster nodes, client trust, SAN, intermediates |

### 12.1. Lỗi chain không đồng nghĩa bị tấn công

Người dùng thấy cảnh báo certificate sau một lần đổi CA có thể do triển khai chain thiếu, root chưa phân phối đến mọi thiết bị hoặc đồng hồ hệ thống sai. Tuy nhiên, **cũng có thể** kết nối bị chuyển hướng tới một dịch vụ khác hoặc có can thiệp bất hợp pháp.

Vì không thể biết ngay nguyên nhân, **không khuyên người dùng bấm “Proceed anyway”** hoặc sử dụng tùy chọn bỏ xác minh. Cần thu thập **hostname thực, certificate chain đang được trình, fingerprint, kết nối mạng và thông báo lỗi** rồi xử lý theo quy trình.

### 12.2. Phân biệt root trust với trust policy của ứng dụng

Một CA trong hệ điều hành có thể được đánh dấu tin cậy, nhưng client VPN hoặc Wi-Fi đã được cấu hình **chỉ tin một CA/issuer hoặc server name cụ thể**; khi đó nó có thể từ chối chứng thư mới dù root nằm trong kho OS.

Đây thường là **tính năng bảo vệ đúng** của policy chặt. Khi thay CA, cần cập nhật policy đúng nguồn đã được phê duyệt, không gỡ ràng buộc danh tính chỉ để kết nối thành công.

### 12.3. Chain không hoàn chỉnh trên một node cụm

Trong hệ thống có nhiều load balancer, VPN gateway hoặc WAF instance, một node có thể đang chạy leaf mới còn node khác vẫn chạy leaf/chain cũ. Client luân phiên kết nối sẽ thấy lỗi **không ổn định, chỉ xuất hiện trên một số request**.

Khi điều tra, kiểm tra từng endpoint/node theo đường mạng và SNI/hostname đúng, đồng thời đối chiếu **fingerprint, serial, validity và chain**. Không giả định một phép thử tới VIP phản ánh toàn bộ các node.

## 13. Thực hành kiểm tra chuỗi chứng thư bằng OpenSSL

Phần này ưu tiên **lệnh chỉ đọc/kiểm tra** trên chứng thư của **phòng lab được phép**. Giả định người quản trị lab đã cấp:

~~~text
root-ca.pem           # Public certificate của Root CA tin cậy
issuing-ca.pem        # Public certificate của Intermediate CA
vpn-server.pem        # Public leaf certificate của vpn.lab.example

Đích TLS lab: vpn.lab.example:443
~~~

Các file và tên dịch vụ là **ví dụ**, không có sẵn trong workspace của người đọc. Không sử dụng private key của root hoặc issuing CA để làm bài kiểm tra path validation; không cần đưa bất kỳ private key nào vào nhóm chat, file báo cáo hay lệnh kiểm chứng.

### 13.1. Xem chủ thể, issuer, thời hạn và fingerprint

~~~bash
# Kiểm tra dữ liệu public của chứng thư server.
openssl x509 -in vpn-server.pem -noout -subject -issuer -dates -serial -fingerprint -sha256

# Kiểm tra các extension như SAN, EKU, KU và Basic Constraints.
openssl x509 -in vpn-server.pem -noout -text

# Xem thông tin Intermediate và Root.
openssl x509 -in issuing-ca.pem -noout -subject -issuer -dates -text
openssl x509 -in root-ca.pem -noout -subject -issuer -dates -fingerprint -sha256
~~~

**Đọc kết quả:**

1. Leaf có SAN cho **vpn.lab.example** không?
2. Leaf có EKU/mục đích dùng khóa phù hợp với TLS server không?
3. Intermediate có **CA:TRUE** và **keyCertSign** đúng không?
4. Intermediate có issuer tương ứng root được dự kiến không?
5. Các chứng thư còn hiệu lực tại thời điểm kiểm tra không?
6. Fingerprint của root có khớp **thông tin root do kênh quản trị đáng tin cung cấp** không?

**Không dùng Subject name một mình để xác nhận đúng CA.** Fingerprint phải được đối chiếu với bản được phê duyệt qua một kênh tin cậy độc lập; việc in fingerprint từ chính file không tự bảo đảm file đó đúng.

### 13.2. Kiểm chứng chain và hostname

~~~bash
# Root là trust anchor được phép; Intermediate là chứng thư
# hỗ trợ dựng path, không được tự nâng thành trust anchor.
openssl verify \
  -CAfile root-ca.pem \
  -untrusted issuing-ca.pem \
  -purpose sslserver \
  -verify_hostname vpn.lab.example \
  vpn-server.pem
~~~

Nếu path và tên đích hợp lệ theo các điều kiện mà phiên bản OpenSSL/lệnh thực thi kiểm tra, kết quả mong đợi có thể là:

~~~text
vpn-server.pem: OK
~~~

**Lưu ý:** chữ **OK** không thay thế toàn bộ điều kiện của một **TLS client production**: ứng dụng có thể yêu cầu kiểm tra revocation, policies, CT, pinning hoặc authorization khác. Các hành vi kiểm tra mặc định của OpenSSL cũng cần được xem theo phiên bản và tùy chọn đang dùng.

### 13.3. Kiểm tra certificate chain từ dịch vụ lab

Nếu máy lab có DNS và dịch vụ TLS thực sự chạy:

~~~bash
# Thay hostname/port chỉ bằng dịch vụ lab được phép.
# Thêm root trust anchor riêng vì đây là ví dụ private PKI.
openssl s_client \
  -connect vpn.lab.example:443 \
  -servername vpn.lab.example \
  -verify_hostname vpn.lab.example \
  -verify_return_error \
  -CAfile root-ca.pem \
  -showcerts < /dev/null
~~~

Cần phân biệt:

- **Certificate chain mà server gửi** (một danh sách public certificates).
- **Path mà OpenSSL xây để xác minh** (có thể tận dụng trust/certificate store tùy cấu hình).
- **Kết quả verify**, bao gồm hostname check và các lỗi đã được báo.

Nếu server dùng chain thiếu intermediate, cách xử lý ưu tiên thường là **cấu hình server gửi đầy đủ intermediate đúng**, không phải thêm root của bên thứ ba không rõ nguồn vào client.

### 13.4. Lệnh kiểm tra trust store trên Windows

Trên máy Windows mà bạn có quyền xem, PowerShell cho phép liệt kê một số kho chứng thư:

~~~powershell
# Liệt kê public certificates trong kho root tin cậy theo máy.
Get-ChildItem Cert:\LocalMachine\Root |
  Select-Object Subject, Thumbprint, NotAfter

# Liệt kê kho root theo tài khoản hiện tại.
Get-ChildItem Cert:\CurrentUser\Root |
  Select-Object Subject, Thumbprint, NotAfter

# Liệt kê intermediate certificates theo máy.
Get-ChildItem Cert:\LocalMachine\CA |
  Select-Object Subject, Thumbprint, NotAfter
~~~

Những lệnh này chỉ cho thấy dữ liệu của **các kho Windows được chỉ định**. Một browser/VPN client/Java application có thể dùng trust source khác hoặc đặt hạn chế CA/hostname riêng. Quyền xem chứng thư **không đồng nghĩa** được phép thêm hoặc xóa trust anchor trong môi trường production.

### 13.5. Quan sát Java truststore

Với runtime Java hỗ trợ tùy chọn tương ứng, có thể xem truststore mặc định của JVM:

~~~bash
# Lệnh chỉ đọc; có thể yêu cầu mật khẩu truststore.
keytool -list -cacerts

# Nếu ứng dụng dùng truststore riêng và người quản trị đã cung cấp path:
keytool -list -keystore /path/to/approved-truststore.p12 -storetype PKCS12
~~~

Đường dẫn ở ví dụ thứ hai **chỉ là placeholder**. Không nhập mật khẩu truststore vào tham số dòng lệnh công khai, history hoặc tài liệu. Không suy ra JVM đang dùng **cacerts** nếu ứng dụng hoặc TLS library được cấu hình dùng một truststore riêng.

### 13.6. Các trường hợp âm tính nên thử trong lab

| Điều kiện thử có kiểm soát | Kết quả mong đợi |
| --- | --- |
| Leaf hợp lệ, chain đủ, trust root đúng, SAN khớp | Verify thành công theo profile |
| Client không tin root phù hợp | Verify thất bại do thiếu trust anchor/path |
| Server không gửi intermediate và client không có bản thay thế | Verify thất bại do thiếu issuer/path |
| Leaf có SAN khác hostname kết nối | Verify thất bại do hostname mismatch |
| Leaf hết hạn hoặc chưa đến hiệu lực | Verify thất bại do thời gian |
| Intermediate không có quyền CA theo profile | Verify thất bại do path constraints |
| Leaf dùng sai EKU đối với profile client kiểm tra | Verify thất bại do purpose/policy |
| CA bị revoke và client thực thi revocation check phù hợp | Không chấp nhận path bị thu hồi |
| Server gửi root lạ nhưng client chưa cài trust | Vẫn không tin root chỉ vì server gửi |
| Client có truststore riêng khác OS | Kết quả khác giữa hai ứng dụng có thể hợp lệ về mặt cấu hình |

Các ca âm tính nên được dựng bằng **cấu hình lab/certificate test đã chuẩn bị**. Không cần can thiệp TLS của người dùng thật, giả mạo Wi-Fi hoặc thay trust store production để chứng minh bài học.

## 14. Một quy trình xử lý lỗi TLS/PKI có hệ thống

~~~mermaid
flowchart TD
    A["Client báo lỗi chứng thư"] --> B{"Tên đích và SAN có khớp?"}
    B -->|Không| C["Kiểm tra FQDN/IP, SNI, SAN, DNS/Proxy"]
    B -->|Có| D{"Leaf và intermediates còn hạn?"}
    D -->|Không| E["Kiểm tra NotBefore/NotAfter, đồng hồ, rotation"]
    D -->|Có| F{"Server gửi intermediates cần thiết?"}
    F -->|Không| G["Sửa server full chain, không thêm CA lạ"]
    F -->|Có| H{"Ứng dụng có trust anchor được phép?"}
    H -->|Không| I["Xác minh root và phân phối qua quản trị"]
    H -->|Có| J{"KU/EKU/constraints và revocation đúng?"}
    J -->|Không| K["Kiểm tra profile, policy, CRL/OCSP"]
    J -->|Có| L["Kiểm tra ứng dụng truststore, pinning, mTLS và runtime"]
    C --> M["Kiểm thử lại từ đúng client"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

Trong thực tế các lỗi có thể tồn tại đồng thời, ví dụ **SAN sai và intermediate hết hạn**. Sơ đồ nhằm sắp xếp bước điều tra, không thay thế log/diagnostics của ứng dụng cụ thể.

### 14.1. Lỗi VPN: Khách chỉ lỗi trên thiết bị cá nhân

**Bối cảnh:** VPN client trên laptop công ty chạy bình thường, nhưng laptop BYOD báo unknown CA.

**Khả năng:** root nội bộ được phân phối qua MDM chỉ cho thiết bị quản trị; BYOD không có trust anchor hoặc VPN client đặt chính sách riêng. Không nên giải quyết bằng cách gửi một file root trên kênh không xác thực và yêu cầu người dùng cài bừa.

**Hướng xử lý:** xác minh chính sách cho BYOD; nếu BYOD được phép, dùng kênh onboarding được phê duyệt để xác thực root fingerprint, cấp profile và kiểm tra server name. Nếu BYOD không được phép, chặn theo policy và cung cấp phương án truy cập được cấp quyền.

### 14.2. Lỗi EAP-TLS: Có CA nhưng xác thực vẫn thất bại

**Bối cảnh:** thiết bị đã tin root dùng cho RADIUS server nhưng 802.1X vẫn từ chối.

**Khả năng:** server SAN không khớp expected name, server gửi chain thiếu; client certificate bị thiếu/hết hạn/không có EKU phù hợp; RADIUS không ánh xạ được danh tính, policy NAC từ chối hoặc revocation check không đạt.

**Hướng xử lý:** đối chiếu **cả hai chiều xác thực**, logs của supplicant và RADIUS/EAP, trạng thái profile, policy người dùng/thiết bị. Không tắt chức năng xác minh RADIUS server để “sửa” lỗi client certificate.

### 14.3. Lỗi mTLS: Reverse proxy tin root nhưng backend từ chối

**Bối cảnh:** proxy xác minh được backend, nhưng backend trả lỗi TLS khi proxy trình client certificate.

**Khả năng:** backend **không tin issuing CA dùng cấp chứng thư client**, EKU không đúng, leaf identity không được authorization, hoặc certificate chain từ phía proxy thiếu intermediate. Truststore của proxy để **xác minh backend server** không phải truststore của backend để **xác minh proxy client**.

**Hướng xử lý:** xác định đúng TLS edge và chiều kiểm chứng, đọc alert/log mỗi phía, kiểm tra clientAuth EKU, SAN/identity và trust policy.

### 14.4. Lỗi sau thay intermediate CA

**Bối cảnh:** hôm nay một số container Java báo PKIX path building failed, trong khi browser trên máy nhân viên vẫn truy cập được.

**Khả năng:** JVM/container có truststore và intermediate cache riêng; server chỉ gửi một chain phù hợp browser nhưng không phù hợp runtime khác; hoặc có cross-signed path và Java chọn đường khác.

**Hướng xử lý:** kiểm tra chain thực server gửi, root truststore **thật** của JVM/container, phiên bản CA bundle, thời hạn và policy. Ưu tiên khắc phục ở chain/trust distribution đúng nơi, không tắt kiểm chứng TLS trong ứng dụng.

## 15. Nghiệm thu kiến trúc Root CA, Intermediate CA và Trust Store

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng phù hợp |
| --- | --- | --- |
| Root key | Root private key có được bảo vệ, kiểm soát người dùng và backup đúng quy trình? | Key management policy, audit và kết quả thử recovery |
| Root trust | Root được phân phối đến **đúng** nhóm client theo chính sách? | Inventory MDM/GPO/runtime và kết nối kiểm thử |
| Issuing CA | Intermediate có CA:TRUE, keyCertSign và path constraints đúng? | Certificate inspection và validator test |
| Issuance policy | CA chỉ cấp SAN/identity được phép? | Template/policy, authn/authz enrollment và audit |
| Certificate profile | Leaf SAN/KU/EKU phù hợp server/client workload? | Profile và mẫu cert kiểm chứng |
| Server chain | Mọi node gửi leaf + intermediate cần thiết? | SNI test từ các điểm khác nhau |
| Hostname | Client luôn xác minh tên đúng khi kết nối? | Cấu hình ứng dụng/VPN/EAP profile và negative test |
| Truststore inventory | Biết OS/browser/JVM/container/app đang dùng nguồn trust nào? | Bản đồ runtime, cấu hình và kết quả thử |
| Revocation | CRL/OCSP hoạt động theo policy, biết fail behavior? | Negative tests và log checker |
| Rotation | Có lịch expiry, reissue, canary và rollback? | Runbook, alert và bài kiểm thử |
| Root rollover | Có overlap có kiểm soát và kế hoạch xóa root cũ? | Timeline, telemetry và policy trust |
| mTLS | Xác thực và authorization **hai chiều** được kiểm chứng? | Log hai phía, test EKU/identity trái phép |
| Wi-Fi/VPN | EAP/VPN client kiểm tra CA lẫn server identity? | Policy thiết bị và thử với server name sai |
| Quan sát | Có log lỗi handshake, issuance, revoke, trust change? | SIEM, CA logs và owner cảnh báo |
| Incident readiness | Có kịch bản lộ intermediate/root key và kế hoạch distrust? | Tabletop/runbook đã được phê duyệt |

## 16. Câu hỏi thực hành tổng hợp

**Bối cảnh:** doanh nghiệp có Root CA **Company Root**, Intermediate **Network Issuing CA**, ba loại dịch vụ:

- VPN gateway: **vpn.lab.example**, dùng TLS server certificate.
- RADIUS EAP-TLS: **radius.lab.example**, yêu cầu client kiểm tra server name.
- Một API backend dùng mTLS cho các workload được quản trị.

Tất cả dùng chứng thư được cấp qua issuing CA theo các profile khác nhau. Nhóm vận hành dự định thay intermediate sau khi phát hiện chứng thư CA sắp hết hạn. Các thiết bị gồm Windows quản trị bằng MDM, Java services trong container và một số máy khách ngoài doanh nghiệp.

### 16.1. Câu hỏi

1. Một chứng thư root tự ký có tự động được client tin không? Nếu không, ai quyết định?
2. Tại sao máy chủ TLS nên gửi intermediate nhưng thường không cần gửi root?
3. Khi leaf được ký đúng nhưng SAN không có **vpn.lab.example**, client nên làm gì?
4. Nếu intermediate có CA:TRUE, pathlen:0, nó có được cấp leaf không? Có được cấp intermediate cấp dưới thông thường không?
5. Cài Company Root vào Windows Local Machine Root có chắc Java app trong container tin root này không?
6. Tại sao chỉ phân phối CA cho supplicant Wi-Fi mà không cấu hình expected RADIUS server identity là chưa đủ?
7. Một proxy xác minh được backend server có đồng nghĩa backend xác minh được client certificate của proxy không?
8. Nếu issuing CA bị thu hồi, vì sao chỉ gia hạn leaf trên một server không đủ khôi phục hệ thống?
9. Khi chuẩn bị đổi Root CA, tại sao phải có giai đoạn client tin root mới **trước** khi dịch vụ chuyển chain?
10. Nếu client báo unknown CA nhưng server vẫn gửi root certificate, điều gì có thể đang thiếu?
11. Vì sao browser làm việc được nhưng ứng dụng Java báo lỗi PKIX path building failed?
12. Khi CA root bị nghi lộ private key, vì sao chỉ chờ root hết hạn là rủi ro?
13. Vì sao một certificate có EKU clientAuth không nên mặc nhiên được dùng làm TLS server certificate?
14. Vì sao phép thử **openssl verify ... OK** chưa đủ để khẳng định mọi ứng dụng production đều an toàn?

### 16.2. Gợi ý đáp án

**(1)** Trust anchor phải được cấu hình bởi hệ điều hành, ứng dụng, quản trị viên hoặc chương trình trust phù hợp. **(2)** Client cần intermediate để xây path nhưng phải tự tin root theo chính sách. **(3)** Từ chối xác thực hostname, sửa certificate/SNI/cấu hình hợp lệ, không bypass. **(4)** Được cấp leaf nếu các điều kiện khác đáp ứng; không được thêm intermediate thông thường bên dưới khi pathLen=0. **(5)** Không; Java/container có thể dùng truststore riêng. **(6)** Một CA có thể cấp cert cho nhiều server; phải ràng buộc server được mong đợi. **(7)** Không; mỗi phía có truststore/policy riêng. **(8)** Nhiều leaf ký dưới CA cũ phải được chuyển sang chain được phép và trust/revocation được cập nhật. **(9)** Nếu client chưa tin root mới, chain mới sẽ bị từ chối. **(10)** Trust anchor không có/không được tin hoặc chain/path/policy sai. **(11)** Runtime/store khác nhau, hoặc khác path/chain building. **(12)** Root bị lộ có thể cấp chứng thư giả cho các client vẫn tin; cần hành động distrust có kế hoạch. **(13)** Mục đích dùng khóa và danh tính không đúng TLS server profile. **(14)** Ứng dụng còn có chính sách riêng về revocation, pinning, hostname, CT, truststore và authorization.

## 17. Giám sát thay đổi và phát hiện bất thường trong PKI

PKI có thể thất bại **mà không có bất kỳ dấu hiệu xâm nhập mạng trực tiếp nào**: root được cài sai vào một thiết bị, máy chủ được cấp certificate cho hostname ngoài quyền hạn, intermediate hết hạn hoặc một gateway không được cập nhật chain. Vì thế cần theo dõi **phát hành, trust change và xác thực kết nối**, không chỉ các phiên TLS đã thành công.

### 17.1. Những sự kiện nên giám sát

| Sự kiện / chỉ số | Nguy cơ cần nhận diện | Hướng điều tra |
| --- | --- | --- |
| Root mới xuất hiện trong trust store của nhóm thiết bị | Trust anchor không được phê duyệt | Kiểm tra MDM/GPO, fingerprint, owner và lý do thay đổi |
| Trust anchor cũ bị xóa hàng loạt | Mất khả năng xác thực các dịch vụ còn dùng root cũ | Đối chiếu kế hoạch rollover và ảnh hưởng client |
| Intermediate phát hành nhiều cert bất thường | Issuance policy bị lạm dụng hoặc automation lỗi | Kiểm tra requestor, SAN, template, approvals và CA logs |
| Cert mới có SAN thuộc mạng/dịch vụ ngoài phạm vi | Cấp sai danh tính | Xác minh quyền kiểm soát tên và certificate policy |
| Hàng loạt TLS handshake failure | Chain/hostname/expiry/revocation hoặc client change | Phân loại theo lỗi, node, runtime, policy và thời gian |
| Chứng thư quan trọng sắp hết hạn | Nguy cơ downtime | Owner, renewal job, triển khai trên từng gateway/node |
| Leaf/intermediate bị revoke | Khả năng mất tin cậy hoặc sự cố key compromise | Phạm vi phụ thuộc, phương án thay chain và trạng thái cập nhật |
| CA private key access ngoài lịch | Nguy cơ lạm dụng khóa | HSM/CA audit, quy trình xác thực và incident response |
| Client/EAP thiết lập truststore “accept all” | Mất xác thực danh tính server | Xác minh policy, sửa cấu hình qua quản trị thiết bị |
| Java/container còn trust bundle cũ | Một phần workload lỗi hoặc giữ trust quá rộng | Inventory image, deployment, pinning và rolling updates |

### 17.2. Tính nhất quán giữa log và tài sản

Nên liên kết dữ liệu:

- **Certificate inventory:** serial, SAN, Subject, Issuer, fingerprint, SPKI, NotAfter, CA chain dự kiến, owner.
- **Issuance logs:** ai yêu cầu, tài khoản/thiết bị, template, approval, CA và thời điểm phát hành.
- **Deployment logs:** gateway/ingress/AP/RADIUS hoặc service version đang dùng leaf và intermediates nào.
- **Trust inventory:** thiết bị/ứng dụng/JVM/container nào tin root nào, policy nguồn và ngày nhận cập nhật.
- **TLS errors:** client, hostname, thông báo xác minh, thời gian và đường mạng.
- **Revocation logs:** trạng thái CRL/OCSP, thời gian cập nhật, sự kiện certificate bị từ chối.

Các thông tin này cần được bảo vệ khỏi truy cập trái phép. **Certificate thường là dữ liệu công khai**, nhưng danh sách SAN nội bộ, mối quan hệ thiết bị và các log issuance có thể làm lộ kiến trúc; **private keys và token enrollment** phải được giữ bí mật nghiêm ngặt.

### 17.3. Phân biệt sự cố vận hành với hành vi ác ý

Một root mới trên máy có thể đến từ việc cập nhật OS/MDM hợp lệ hoặc bị cài trái phép. Một intermediate phát hành nhiều chứng thư có thể là đợt tự động đổi leaf theo lịch hoặc là dấu hiệu issuance account bị lộ.

Không báo **Confirmed compromise** chỉ từ một biến động số lượng chứng thư. Cần đối chiếu ticket, signer, danh tính requester, chain, policy, thiết bị nhận trust update và hành vi kết nối trước/sau thay đổi.

## 18. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Root certificate tự ký thì đương nhiên đáng tin.” | Self-signed không tự tạo trust; cần trust anchor được cấu hình đúng. |
| “CA trong trường Issuer là đã chứng minh chứng thư được CA đó ký.” | Phải xác minh chữ ký và chuỗi đến root được phép. |
| “Cài Root CA vào Windows thì mọi phần mềm đều tin.” | Browser/JVM/container/app có thể sử dụng trust store và policy riêng. |
| “Server gửi root là client phải tin.” | Trust anchor không được quyết định chỉ bằng dữ liệu server gửi. |
| “Thiếu intermediate thì cứ import intermediate thành root.” | Ưu tiên server gửi chain đúng; không tùy ý mở rộng trust. |
| “Cert có chữ ký đúng là đủ xác thực website.” | Còn SAN/hostname, KU/EKU, thời gian, constraints, revocation/policy. |
| “Subject CN đúng tên là đủ.” | TLS DNS identity hiện đại cần kiểm tra SAN theo chuẩn và policy. |
| “Trusted Root store nên chứa private key của CA.” | Client xác minh chỉ cần public trust material; root private key phải được bảo vệ. |
| “Intermediate pathlen:0 chỉ được cấp một leaf.” | pathLen giới hạn các CA cấp dưới, không giới hạn số leaf. |
| “Một intermediate riêng tự bảo đảm chỉ được cấp hostname nội bộ.” | Cần constraints và issuance/verifier policy thực tế. |
| “mTLS xác thực xong thì client được truy cập mọi API.” | Authentication và authorization vẫn là hai bước khác nhau. |
| “Root bị lộ có thể giải quyết chỉ bằng revoke root.” | Phải điều phối distrust/remove trust anchor và chuyển chain. |
| “OCSP lỗi thì mọi client bắt buộc chặn.” | Soft/hard fail và phương pháp kiểm tra revocation khác nhau. |
| “CT log thay được revocation.” | CT hỗ trợ quan sát phát hành, không thay kiểm tra trạng thái hoặc quyền CA. |
| “Đổi root chỉ cần sửa chứng thư trên server.” | Root mới phải được client nhận và tin trước khi chuyển; cần rollback. |
| “Thay leaf không cần quan tâm intermediate.” | Server phải gửi chain phù hợp với trust path mà client sử dụng. |
| “Không cần kiểm tra server name khi dùng Wi-Fi EAP-TLS.” | Supplicant cần xác minh EAP server identity và CA theo policy. |
| “Vì TLS server an toàn nên traffic WAF → backend cũng an toàn.” | Mỗi cạnh TLS và truststore cần kiểm tra riêng. |
| “Một lần verify OK bảo đảm mọi thiết bị/ứng dụng đều OK.” | Client có runtime, truststore, revocation và policy khác nhau. |

## 19. Tổng kết

**Root CA** là tầng gốc của một hệ thống CA phân cấp; khi được client **chọn làm trust anchor**, nó tạo điểm bắt đầu cho việc xác minh chuỗi. **Intermediate CA** được cấp trên ký và có thể phát hành chứng thư trong phạm vi ràng buộc phù hợp, giảm nhu cầu sử dụng root private key. **Trust store** là chính sách và kho trust anchor tại **bên kiểm chứng**, không phải danh sách chứng thư mà server tự gửi để yêu cầu được tin.

Để xác thực một kết nối mạng, cần kết hợp **certificate chain + chữ ký + hạn/constraints/KU/EKU + SAN/đúng danh tính + revocation theo policy + authorization ứng dụng**. Thực hành an toàn gồm bảo vệ khóa CA, phân phối trust có kiểm soát, chạy issuance theo chính sách, cấu hình server gửi intermediates cần thiết, tự động hóa vòng đời, giám sát và lập kế hoạch root/intermediate rollover.

Trong **SECURITY_NETWORK_SECURITY**, PKI giúp xác thực các điểm cuối cho **VPN, Wi-Fi EAP-TLS, mTLS, API gateway, WAF, kết nối quản trị và dịch vụ mạng**. Nó bổ sung cho firewall, phân đoạn, IDS/IPS, DNS security và kiểm soát danh tính. Một đường truyền mã hóa chỉ thật sự có ý nghĩa bảo vệ chống giả mạo endpoint khi **đối tượng kết nối được xác minh đúng, trust anchor được cấp quyền và private key vẫn an toàn**.

### Tài liệu tham khảo và hướng đọc thêm

- **RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile:** cấu trúc chứng thư, Basic Constraints, Key Usage, Name Constraints, certificate path validation và CRL.
- **RFC 9525 — Service Identity in TLS:** quy tắc định danh và xác minh service identity của TLS client.
- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** chứng thực trong TLS và quá trình thiết lập kênh bảo mật.
- **RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP):** kiểm tra trạng thái chứng thư.
- **RFC 3647 — Internet X.509 Public Key Infrastructure Certificate Policy and Certification Practices Framework:** khung xây dựng chính sách CP/CPS.
- **RFC 8555 — Automatic Certificate Management Environment (ACME):** tự động hóa quản lý chứng thư.
- **RFC 7030 — Enrollment over Secure Transport (EST):** cấp phát/enrollment chứng thư cho client/thiết bị qua kênh được bảo vệ.
- **RFC 5216 / RFC 9190 — EAP-TLS và EAP-TLS 1.3:** chứng thực EAP-TLS trong môi trường 802.1X.
- **NIST SP 800-57 — Recommendation for Key Management:** quản lý vòng đời và bảo vệ khóa mật mã.
- **NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of TLS Implementations:** thiết kế cấu hình TLS.
- **NIST SP 800-153 — Guidelines for Securing Wireless Local Area Networks:** bảo vệ WLAN và phương án xác thực.
- **Tài liệu chính thức OpenSSL, hệ điều hành, JVM và nhà cung cấp VPN/WLAN:** kiểm tra tùy chọn xác minh, truststore và khả năng hỗ trợ theo đúng phiên bản thực tế.
