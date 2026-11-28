# Rủi ro khi tin cậy quá nhiều CA: kiểm soát phạm vi tin cậy trong PKI mạng

**Certificate Authority (CA)** là thực thể ký và phát hành chứng thư số theo một chính sách xác minh danh tính. Trong **Public Key Infrastructure (PKI)**, một ứng dụng thường tin các chứng thư khi có thể xây dựng và xác minh một đường chứng thực hợp lệ từ chứng thư đầu cuối đến **trust anchor** đã được cấu hình. Nếu hệ thống chấp nhận quá nhiều CA, đặc biệt là **CA gốc hoặc CA trung gian được trao quyền không cần thiết**, bề mặt tin cậy mở rộng: một CA khác trong danh sách có thể cấp chứng thư mà ứng dụng chấp nhận cho những tên hoặc danh tính ngoài kỳ vọng.

Trong chương **PKI và chứng thư cho mạng** của học phần **SECURITY_NETWORK_SECURITY**, đây là rủi ro nền tảng đối với HTTPS/TLS, mTLS giữa dịch vụ, VPN, 802.1X/EAP-TLS, Wi-Fi doanh nghiệp, DNS mã hóa, proxy, cloud load balancer và kiến trúc phân đoạn. **Mã hóa TLS mạnh không giải quyết được việc client tin sai CA hoặc bỏ xác minh danh tính máy chủ.** Khi một chứng thư không đúng được chấp nhận, client có thể thiết lập một kênh mã hóa hoàn toàn hợp lệ về mặt kỹ thuật nhưng tới endpoint không được dự định.

Bài học xây dựng mô hình tin cậy, phân tích các kiểu lạm dụng và sai cấu hình, thiết kế chính sách giảm phạm vi CA, phát hiện chứng thư cấp sai, duy trì trust store và xử lý sự cố. Các ví dụ dùng tên miền **.example**, địa chỉ dành cho tài liệu và dữ liệu giả định. Lệnh kiểm tra chỉ dành cho thiết bị, chứng thư và dịch vụ mà người học được phép quản trị.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **root CA, intermediate CA, end-entity certificate** và **trust anchor**.
2. Giải thích cách **certificate path building/validation** hoạt động và vì sao một CA tin cậy có thể ảnh hưởng nhiều hostname.
3. Phân tích rủi ro khi thêm CA gốc/cấp dưới vào OS, browser, Java, container, gateway hoặc store ứng dụng.
4. Nhận diện các tình huống **misissuance, CA compromise, TLS interception, trust-store poisoning, cross-signing** và chứng thư không đạt chính sách.
5. Phân biệt public WebPKI, enterprise/private PKI, mTLS và các trust domain chuyên biệt.
6. Hiểu tác dụng và giới hạn của **Basic Constraints, Key Usage, EKU, Name Constraints, path length**.
7. Phân biệt **CAA, Certificate Transparency (CT), OCSP/CRL** với cơ chế xác thực danh tính và quyết định tin cậy.
8. Thiết kế mô hình **least-trust CA** theo ứng dụng, môi trường, workload và vòng đời.
9. Kiểm tra chứng thư và đường xác thực bằng công cụ chỉ đọc trong môi trường được phép.
10. Đề xuất runbook khi phát hiện CA lạ, chứng thư cấp sai hoặc cần loại bỏ một trust anchor.

## 2. PKI và đường chứng thực

Một chứng thư X.509 thường gắn **public key** với thông tin danh tính và các ràng buộc sử dụng. CA ký chứng thư; ứng dụng xác minh chữ ký, chuỗi chứng thư và chính sách phù hợp trước khi dùng public key đó để xác thực endpoint.

~~~mermaid
flowchart TD
    R[Root CA được cấu hình làm trust anchor]
    R -->|Ký chứng thư CA cấp dưới| I[Intermediate CA]
    I -->|Ký chứng thư đầu cuối| E[Server certificate cho api.corp.example]
    C[TLS client] -->|Nhận chứng thư từ server| E
    C -.Xây và xác minh đường chứng thực.-> I
    C -.Kết thúc tại anchor được phép.-> R
~~~

Đường đi minh họa:

~~~text
Trust anchor được client chấp nhận
    |
    +-- Root CA
          |
          +-- Intermediate CA (CA:TRUE)
                |
                +-- api.corp.example (end entity, CA:FALSE)
~~~

**Điểm quyết định:** server gửi chứng thư không làm chứng thư ấy tự được tin. Client phải có **đường chứng thực hợp lệ tới trust anchor được phép**, đồng thời xác minh **tên đích, thời hạn, mục đích dùng, chữ ký và các ràng buộc** theo chính sách.

### 2.1. Trust anchor không nhất thiết là “mọi root trong một file”

Một **trust anchor** là điểm khởi đầu tin cậy được cấu hình trong hệ thống xác minh đường chứng thư; nó có thể được biểu diễn bởi chứng thư gốc và metadata chính sách. Một chứng thư tự ký (**self-signed**) không tự trở thành đáng tin chỉ vì tự ký.

Tùy hệ điều hành/ứng dụng, store có thể hỗ trợ **giới hạn mục đích tin cậy**, chặn CA cụ thể, tin một CA trung gian trong phạm vi hẹp hoặc lưu những thuộc tính bổ sung. Không phải mọi store triển khai các giới hạn giống nhau.

### 2.2. Vai trò của root, intermediate và leaf

| Đối tượng | Vai trò | Rủi ro nếu cấu hình sai |
|---|---|---|
| **Root CA** | Điểm gốc hoặc đại diện của chuỗi phát hành | Tin thêm một root quá rộng có thể chấp nhận rất nhiều chứng thư |
| **Intermediate CA** | Phát hành chứng thư theo quyền được CA cấp trên giao | Nếu quyền phát hành rộng hoặc private key bị lộ, có thể cấp chứng thư trái phép |
| **End-entity/leaf certificate** | Chứng thực một server, client, workload hoặc thiết bị | Không nên có quyền ký CA; identity/key usage phải đúng |
| **Trust store** | Nơi client lấy các anchor/chính sách trust | CA lạ trong store mở rộng tập bên có thể cấp chứng thư hợp lệ |
| **Certificate chain** | Tập chứng thư chứng minh đường từ leaf tới anchor | Chuỗi thiếu, sai, hết hạn hoặc có đường thay thế gây lỗi/nhầm lẫn |

**Issuer** ghi trong chứng thư là tên bên phát hành, nhưng chỉ tên giống nhau **không chứng minh chữ ký hoặc public key đúng**. Path validation phải sử dụng các thuộc tính, chữ ký và ràng buộc mật mã thực tế.

## 3. “Tin cậy quá nhiều CA” nghĩa là gì?

Đó không chỉ là số lượng CA trong một danh sách. Rủi ro tăng khi **phạm vi những bên có thể khiến client chấp nhận một chứng thư vượt nhu cầu nghiệp vụ**, hoặc khi trust anchors không được quản trị/kiểm toán.

Ví dụ:

- Một laptop của nhân viên tin bộ root công khai để truy cập web; đây là **một mô hình WebPKI được thiết kế có kiểm soát**, không tự động là cấu hình sai.
- Một ứng dụng nội bộ chỉ cần kết nối tới **một API riêng**, nhưng lại dùng toàn bộ public root store, cộng thêm nhiều root thử nghiệm và root của đối tác không còn sử dụng.
- Một hệ thống mTLS dùng shared trust store, trong đó CA của môi trường staging cũng được coi hợp lệ cho production.
- Một container image hoặc Java truststore chứa CA nội bộ do nhóm không có trách nhiệm đối với dịch vụ đó phát hành.
- Một thiết bị được cài root phục vụ TLS inspection, nhưng quyền sửa và phạm vi hoạt động không được quản trị.

**Kết luận:** “Quá nhiều” được xác định bởi **mục đích, trust domain, quyền phát hành, ràng buộc và khả năng giám sát**, không chỉ bằng cách đếm root certificates.

### 3.1. Hai lớp tin cậy khác nhau

**Tin CA** có nghĩa client chấp nhận CA đó làm một nhánh xác thực chứng thư **trong những điều kiện nhất định**. **Tin endpoint** cần thêm việc kiểm tra chứng thư đại diện đúng danh tính mà client định kết nối, ví dụ hostname trong SAN, mục đích server authentication và các kiểm tra khác.

Một CA đã được tin **không khiến mọi chứng thư của nó tự hợp lệ**. Chứng thư sai tên, hết hạn, không đạt ràng buộc, bị chặn hoặc có đường chứng thực không hợp lệ phải bị từ chối theo chính sách.

## 4. Vì sao tập CA rộng làm tăng rủi ro?

Giả sử một client chấp nhận N trust anchors. Trong những điều kiện kiểm tra và giới hạn policy cụ thể, nhiều anchor mở rộng tập những bên có thể tạo ra một đường chứng thực được chấp nhận. Hệ quả:

1. **Thêm bên có quyền phát hành** mà tổ chức phải tin vào quy trình xác minh, khóa và quản trị.
2. **Tăng phụ thuộc vào bảo mật của CA bên ngoài**: khoá phát hành, sub-CA, nhân viên, automation và kiểm soát miền.
3. **Mở đường cho chứng thư cấp sai** nếu một CA được tin cấp cho hostname/danh tính không thuộc quyền người yêu cầu.
4. **Khó kiểm soát lifecycle** vì không biết root nào đang được dùng, root nào là dư thừa.
5. **Khó kiểm chứng chính sách** nếu Windows, Linux, Java, browser, container và thiết bị mạng có những store khác nhau.
6. **Tăng ảnh hưởng khi CA bị distrust**: thay đổi trust policy có thể làm nhiều ứng dụng hỏng nếu phụ thuộc không được nhận diện.

Không nên dùng công thức kiểu **“rủi ro = N nhân xác suất một CA bị hack”** như một phép tính thực tế. Các CA không độc lập về hệ sinh thái, có quy trình và phạm vi khác nhau, còn chính sách client có thể giới hạn mục đích, tên hoặc anchor. Có thể dùng mô hình định tính:

~~~text
Rủi ro tổng thể phụ thuộc:
  trust anchors/paths được chấp nhận
  x phạm vi danh tính mà từng path có thể xác thực
  x xác suất hoặc điều kiện phát hành sai / lộ khóa / cấu hình sai
  x khả năng attacker điều hướng traffic hoặc kiểm soát endpoint
  x tác động đến dữ liệu/dịch vụ
  x mức phát hiện và khắc phục
~~~

Dấu “x” ở trên là cách nhấn mạnh **các yếu tố cùng ảnh hưởng**, không phải phương trình xác suất chuẩn.

## 5. Chuỗi sự kiện khi một CA bị lạm dụng

Một tình huống minh họa: một CA được máy tính tin để xác thực HTTPS có thể ký một chứng thư cho tên **pay.corp.example** mà chủ sở hữu hệ thống không ủy quyền. Nếu một attacker có thể **điều hướng kết nối của client** tới server dùng chứng thư ấy, client có nguy cơ chấp nhận một endpoint không đúng dự định.

~~~mermaid
flowchart TD
    CA[CA nằm trong trust store client]
    ISSUE[Chứng thư sai cho pay.corp.example]
    ROUTE[Traffic bị điều hướng đến endpoint không được duyệt]
    TLS[Client xác minh chứng thư theo policy]
    DATA[Dữ liệu gửi tới endpoint sai]

    CA -->|Ký hoặc cấp sai| ISSUE
    ISSUE --> TLS
    ROUTE --> TLS
    TLS -->|Nếu được chấp nhận và attacker kiểm soát endpoint| DATA
~~~

**Hai điều kiện quan trọng:**

- **Chứng thư cấp sai** không tự tạo khả năng đọc mọi traffic trên Internet. Đối thủ còn cần kiểm soát endpoint, đường đi, DNS/proxy, thiết bị hoặc cơ chế điều hướng khác.
- Nếu client có **policy chặt**, như danh tính đích đúng, anchor hạn chế, pinning được quản trị hoặc cơ chế chống cấp sai khác, một chứng thư do CA ngoài phạm vi phát hành vẫn có thể bị từ chối.

### 5.1. CA compromise và misissuance khác nhau

- **CA compromise:** private key/khả năng ký hoặc hệ thống cấp phát bị kiểm soát trái phép.
- **Misissuance:** chứng thư phát hành sai yêu cầu xác minh, chính sách hoặc thẩm quyền; không nhất thiết root key bị đánh cắp.
- **Validation failure:** client chấp nhận chứng thư đáng lẽ phải từ chối vì trust store, hostname verification hoặc implementation sai.
- **Key compromise của leaf:** private key server bị lộ, có thể ảnh hưởng danh tính server đó mà không đồng nghĩa CA bị chiếm.

Phải xác định đúng loại sự cố để chọn biện pháp. **Thu hồi một leaf** thường không giống xử lý một **CA cấp dưới** bị lộ khóa.

## 6. Rủi ro do CA công khai cấp sai chứng thư

Trong **WebPKI**, nhiều hệ thống tin một tập root công khai được hệ điều hành/trình duyệt hoặc nhà cung cấp ứng dụng quản lý. Các root này tham gia các chương trình chính sách, audit và cơ chế xử lý sự cố. Tuy nhiên, **một sự cố tại CA được tin có thể ảnh hưởng nhiều domain**.

### 6.1. Các nguyên nhân có thể dẫn đến misissuance

| Nguồn vấn đề | Ví dụ | Tác động |
|---|---|---|
| Xác minh quyền kiểm soát domain sai | Cơ chế domain validation bị lỗi hoặc bị lạm dụng | Chứng thư cấp cho bên không được phép |
| CA issuance automation sai | Nhầm account hoặc namespace | Chứng thư ngoài phạm vi dự kiến |
| Intermediate có quyền rộng | Intermediate được vận hành bởi bên thứ ba | Mở rộng nơi phải tin vào quy trình phát hành |
| Private key CA bị lộ | Actor trái phép có thể ký | Rủi ro cấp nhiều chứng thư trái phép |
| Quản lý danh tính trong DNS sai | CNAME, DNS zone hoặc delegation do nhóm khác kiểm soát | Người khác có thể chứng minh quyền đối với tên không mong muốn |
| Chính sách client không cập nhật | Root bị distrust nhưng client legacy vẫn tin | Chứng thư không còn được duyệt vẫn được chấp nhận trên một số máy |

### 6.2. Mô hình đe dọa phải xét ai điều khiển traffic

Một chứng thư hợp lệ về cú pháp chỉ tạo **một điều kiện**. Để giả mạo một HTTPS server trước một client dùng xác minh đúng, attacker thường còn cần đưa client kết nối tới endpoint mình kiểm soát, ví dụ bằng DNS compromise, proxy bị lạm dụng, kiểm soát mạng hoặc endpoint.

Do đó phòng vệ phải kết hợp **CA governance + DNS security + quản trị proxy + endpoint security + certificate monitoring**, không chỉ thay thuật toán mã hóa.

## 7. CA nội bộ và CA phục vụ TLS interception

Một tổ chức đôi khi thêm **enterprise root CA** để phát hành chứng thư cho dịch vụ nội bộ, thiết bị, mTLS hoặc để kiểm tra traffic HTTPS trong môi trường được quản trị.

### 7.1. Vì sao CA nội bộ có thể cần thiết?

- Phát hành chứng thư cho API nội bộ và service mesh.
- Cấp danh tính thiết bị qua MDM, 802.1X/EAP-TLS hoặc VPN.
- Xác thực proxy/gateway, load balancer hoặc thiết bị quản trị.
- Quản trị vòng đời chứng thư private không cần đưa toàn bộ tên nội bộ ra WebPKI.

Nhưng **CA nội bộ không nên tự trở thành trust anchor cho mọi ứng dụng ở mọi môi trường** nếu nhiệm vụ chỉ là cấp chứng thư cho một nhóm workload.

### 7.2. TLS inspection và “điểm giải mã” được tin cậy

~~~text
Trình duyệt managed
   |
   | TLS A tới proxy
   v
Enterprise proxy / TLS inspection
   |
   | TLS B tới website gốc
   v
Public website
~~~

Nếu client tin root của proxy và mạng được cấu hình để chuyển HTTPS qua proxy, proxy có thể cấp một chứng thư thay thế được client chấp nhận cho website đang truy cập, giải mã traffic tại điểm proxy rồi tạo phiên TLS khác tới website.

Điều này có thể được tổ chức sử dụng hợp pháp cho security filtering, nhưng kéo theo:

- **Tập trung dữ liệu nhạy cảm** tại proxy và hệ thống log.
- **Quyền phát hành chứng thư rộng** trong phạm vi thiết bị đã cài root.
- **Rủi ro khi khóa proxy CA hoặc quyền cấu hình bị lộ**.
- **Rủi ro privacy/compliance** và tác động tới app pinning, mTLS hoặc protocol có xác thực riêng.
- **Yêu cầu kiểm tra TLS upstream thật sự**, tránh proxy chấp nhận chứng thư website không hợp lệ.
- **Yêu cầu minh bạch chính sách** và giới hạn những luồng không nên giải mã.

**Không tự cài một root lạ hoặc tắt certificate verification để giúp proxy hoạt động.** Việc triển khai phải theo quyền quản trị, đánh giá pháp lý/quyền riêng tư và giới hạn phạm vi.

### 7.3. CA phục vụ Wi-Fi/VPN khác CA xác thực HTTPS

Một root dành cho **EAP-TLS client identity** không nhất thiết cần được mọi browser chấp nhận để xác thực các website. Ngược lại, CA dùng cấp server certificates cho HTTPS không mặc định phải được chấp nhận để cấp chứng thư client cho VPN.

**Tách trust domain theo mục đích** là cơ chế giảm blast radius hiệu quả.

## 8. Quá nhiều trust store: rủi ro lệch chính sách

Một hệ thống hiện đại có thể có nhiều kho tin cậy độc lập hoặc tương tác:

| Nơi cấu hình | Đặc điểm cần xem | Rủi ro |
|---|---|---|
| Windows certificate stores | Root/Intermediate theo máy hoặc người dùng và chính sách tổ chức | Một user/store có CA lạ, policy khác giữa máy |
| macOS Keychain/trust settings | System/user roots và trust decisions | CA được tin ngoài phạm vi mong muốn |
| Linux OS CA bundle/p11-kit | Distro trust bundle, p11-kit hoặc cấu hình ứng dụng | App không dùng bundle được cập nhật |
| Browser-specific root store | Một số browser dùng chương trình root riêng hoặc OS trust có điều kiện | Browser A tin root, browser B không |
| Java truststore | JVM default cacerts hoặc truststore tùy ứng dụng | Một service Java tiếp tục tin CA đã bỏ khỏi OS |
| Container image | CA bundle đóng gói trong image | Image cũ, truststore stale hoặc không theo policy host |
| Reverse proxy/API gateway | CA bundle để xác minh upstream, mTLS client | Tin quá nhiều CA cho backend nội bộ |
| Kubernetes/service mesh | Root bundle/workload CA trong control/data plane | Cross-namespace/cluster trust mở rộng |
| Thiết bị mạng/IoT | Truststore/vendor firmware riêng | Khó cập nhật hoặc không theo lifecycle tổ chức |
| Cloud managed service | Root policy do provider và config quyết định | Không kiểm soát được toàn bộ danh sách hoặc version |

**Tắt một root ở hệ điều hành không chứng minh mọi runtime đã ngừng tin root đó.** Ngược lại, cập nhật Java cacerts không thay đổi tự động trust settings của browser, VPN client hoặc thiết bị mạng.

### 8.1. Nhiều store tạo rủi ro điều tra sai

Giả sử trình duyệt từ chối một certificate, nhưng ứng dụng Java vẫn kết nối thành công. Hai ứng dụng có thể dùng trust anchors, thuật toán path building, chính sách revocation, hostname verification hoặc runtime khác nhau.

Trước khi gọi đó là “lỗi TLS”, cần xác định **ứng dụng kiểm chứng đang dùng store nào và ràng buộc nào**.

## 9. Root được tin nhưng phạm vi quá rộng

Một CA được đặt làm trust anchor cho mục đích **server authentication** có thể có vai trò xác thực những tên miền rất rộng nếu không có ràng buộc hiệu quả. Đặc biệt nguy hiểm khi root ấy chỉ đáng lẽ phát hành cho **một vùng nội bộ**.

### 9.1. Không coi mỗi trust anchor là “giống nhau”

Một số hệ thống có thể gán:
- Mục đích **serverAuth** và/hoặc **clientAuth**.
- Cờ distrust hoặc hạn chế với CA cụ thể.
- Policy riêng cho application truststore.
- Các giới hạn đối với subordinate CA/certificate.
- Những kiểm tra bổ sung do browser/root program quy định.

Khả năng thực thi và semantics **khác nhau giữa library và nền tảng**, vì thế cần kiểm chứng bằng client thực. Không giả định một trust store file PEM thuần có thể mã hóa mọi chính sách.

### 9.2. Lựa chọn kiến trúc ít quyền hơn

Nếu API client chỉ cần kết nối **api.corp.example**, hãy cân nhắc:
1. Truststore riêng chỉ chứa anchor cần cho API đó.
2. Xác minh **SAN/hostname** và EKU đúng.
3. Sử dụng subordinate CA đã giới hạn tên/mục đích khi hỗ trợ.
4. Duy trì inventory cert chain, owner và key rotation.
5. Xác thực ở lớp ứng dụng và firewall/route theo least privilege.

Không tự tạo “trust all” để tránh lỗi cấu hình CA, vì như vậy loại bỏ một mục tiêu cốt lõi của PKI.

## 10. Basic Constraints, Key Usage, EKU và Name Constraints

X.509 có các extension nhằm diễn đạt **chứng thư có thể làm gì** và trong phạm vi nào. Chúng là điều kiện quan trọng nhưng **không thay thế quyết định trust anchor**.

### 10.1. Các extension quan trọng

| Extension | Chức năng | Lỗi hay gặp |
|---|---|---|
| **Basic Constraints** | CA:TRUE/CA:FALSE và giới hạn pathLen khi áp dụng | Chứng thư leaf bị cấu hình thành CA hoặc intermediate không có ràng buộc đúng |
| **Key Usage** | Ràng buộc mục đích dùng khóa như keyCertSign, digitalSignature | Cho quyền ký CA khi không cần |
| **Extended Key Usage (EKU)** | Mục đích như serverAuth/clientAuth tùy profile | Dùng chứng thư clientAuth cho serverAuth trái policy |
| **Name Constraints** | Hạn chế loại/tập tên DNS, IP, email... được CA subordinate cấp | CA cấp dưới vẫn được phát hành quá rộng |
| **Certificate Policies** | Nêu chính sách cấp và các quy tắc liên quan | Coi OID policy là bảo đảm độc lập mà không kiểm tra |
| **Subject Alternative Name (SAN)** | Danh tính DNS/IP/URI theo loại chứng thư | Client chỉ so tên Common Name hoặc không kiểm tra SAN |
| **Authority/Subject Key Identifier** | Hỗ trợ tìm issuer/path building | Dựa vào tên issuer mà bỏ kiểm tra chữ ký |

### 10.2. Name Constraints giảm rủi ro thế nào?

Nếu một **intermediate CA** chỉ cần cấp server certificate cho **.corp.example**, việc ràng buộc namespace có thể ngăn đường chứng thực hợp lệ vượt phạm vi đó khi client hỗ trợ và thực thi đúng.

~~~text
Enterprise Root (trust anchor cho một nhóm client)
    |
    +-- Restricted Intermediate
          Name Constraints: chỉ tên DNS thuộc corp.example
          EKU/purpose: phù hợp server authentication
          |
          +-- api.corp.example
~~~

**Cần đặc biệt thận trọng:** extension trên chính chứng thư được dùng làm **trust anchor** không được mọi implementation xử lý giống ràng buộc của một subordinate CA; nhiều profile chỉ áp constraint qua phần được validate trong đường chain. Do đó muốn giảm quyền, thiết kế **subordinate được giới hạn**, truststore riêng và **kiểm thử client cụ thể**.

### 10.3. pathLen không giới hạn tên miền

**pathLenConstraint** hạn chế số CA cấp dưới có thể xuất hiện trong đường chứng thực theo quy tắc X.509. Nó **không giới hạn hostname** mà một intermediate được cấp phép ký. Muốn giới hạn tên cần Name Constraints hoặc các policy/proxy-specific checks khác.

### 10.4. EKU không thay thế kiểm soát định danh

EKU serverAuth có thể cho biết chứng thư thích hợp dùng xác thực máy chủ, nhưng một server cert với serverAuth vẫn cần **SAN đúng tên**. Tương tự mTLS clientAuth không mặc nhiên cấp quyền cho mọi API.

## 11. Cross-signing và nhiều đường chứng thực

**Cross-signing** cho phép một CA được ký bởi một CA khác để xây các đường xác thực thay thế. Nó có thể hữu ích cho việc chuyển đổi root, tương thích client cũ và duy trì dịch vụ.

~~~text
                 Root-New (anchor trên client mới)
                  |
                  +-- Intermediate X --> Leaf

Root-Old (anchor trên client cũ)
    |
    +-- Cross-signed Intermediate X --> Leaf
~~~

Trong một số tình huống, cùng một endpoint có thể xây nhiều đường tới những anchors khác nhau; **client chọn đường nào còn phụ thuộc store, certificate chain được gửi, policy và path builder**.

### 11.1. Rủi ro khi root cũ vẫn được tin

- Một root đã định loại bỏ còn được client legacy chấp nhận thông qua alternate chain.
- Một đường chứng thực kết thúc ở anchor khác policy dự kiến.
- Có sự khác biệt về expiry, algorithm constraints hoặc distrust giữa các hệ điều hành.
- Server chỉ gửi một chain không phù hợp với một nhóm client.
- Team vận hành tưởng “đã gỡ root” nhưng app-specific store vẫn cho phép chain cũ.

**Không chỉ nhìn chứng thư đầu cuối hoặc trường Issuer** để kết luận trust anchor cuối cùng. Nên kiểm chứng **chain được chọn trên client đại diện** và danh sách trust anchors của client đó.

### 11.2. Cross-signing không tự là lỗ hổng

Cross-signing là cơ chế vận hành hợp lệ. Rủi ro xuất hiện khi **đường thay thế kéo dài một quyền tin cậy không mong muốn**, hoặc khi tổ chức không có inventory về những client vẫn phụ thuộc vào anchor cũ.

## 12. Phân biệt CA store poisoning và CA compromise

Hai tình huống có tác động khác nhau:

**Trust-store poisoning:** một actor có quyền không phù hợp thêm root/anchor hoặc sửa trust policy của client. Khi đó nhiều chứng thư do root này ký có thể trở nên hợp lệ với client đó, ngay cả khi public CA không hề có sự cố.

**CA compromise/misissuance:** CA vốn được tin bị lạm dụng hoặc cấp sai chứng thư; client không cần bị sửa truststore để chịu ảnh hưởng.

### 12.1. Nguồn thay đổi trust store cần audit

- MDM/GPO hoặc hệ thống triển khai certificate.
- Package update, hệ điều hành hoặc browser root program.
- Script cài ứng dụng, installer và agent có đặc quyền.
- Java truststore được đóng gói trong ứng dụng.
- Container image build pipeline, base image và sidecar.
- Gateway/firewall management UI hoặc config-as-code.
- Người dùng có quyền import root vào user store.
- Provisioning của thiết bị/IoT và firmware updates.

**Không suy đoán CA lạ luôn là malware**: đó có thể là root enterprise phục vụ proxy hoặc onboarding. Nhưng cần xác minh **owner, mục đích, fingerprint, đường triển khai và policy cho phép**, không tự chấp nhận chỉ vì tên nghe hợp pháp.

## 13. Certificate Transparency: phát hiện chứng thư public cấp sai

**Certificate Transparency (CT)** là hệ sinh thái nhật ký công khai có thể kiểm toán, chủ yếu được áp dụng cho nhiều chứng thư TLS **công khai được browser tin cậy** theo chính sách liên quan. CT giúp chủ sở hữu tên miền và cộng đồng **phát hiện** chứng thư không mong muốn.

### 13.1. CT giải quyết phần nào?

~~~mermaid
flowchart LR
    CA[Public CA] -->|Chứng thư hoặc precertificate| CT[CT Log]
    CT --> MON[Giám sát tên miền]
    MON --> REVIEW[Review cấp phép, issuer, SAN, thời gian]
    REVIEW --> RESP[Điều tra / yêu cầu revoke / khắc phục]
~~~

Nếu một chứng thư mới xuất hiện cho **login.corp.example** từ CA không thuộc chính sách, đội bảo mật có thể điều tra: chứng thư thuộc hệ thống doanh nghiệp, đối tác CDN hay phát hành trái phép?

**CT không phải cơ chế cấp phép phát hành** và không tự bảo đảm một chứng thư có chủ sở hữu hợp pháp. Một certificate có mặt trong CT vẫn có thể do CA cấp sai. CT là bằng chứng quan sát; một số client/browser còn yêu cầu đáp ứng CT theo chính sách.

### 13.2. Giới hạn của CT

- **Private PKI** không nhất thiết đăng chứng thư vào public CT logs.
- Không phải mọi client và trust domain đều kiểm tra CT giống nhau.
- Có thể có độ trễ giữa phát hành, ghi log, ingest và cảnh báo.
- CT logs chứa metadata chứng thư/tên miền công khai; cần cân nhắc lộ thông tin về hostname.
- Không phải thấy hostname trên CT đồng nghĩa endpoint đang hoạt động hoặc có dữ liệu bị lộ.
- CT không tự xóa trust anchor hay thu hồi chứng thư.

### 13.3. Quy trình giám sát CT

1. Định nghĩa những **domain/subdomain** tổ chức sở hữu và phạm vi theo dõi.
2. Thu các sự kiện CT phù hợp từ nguồn được duyệt.
3. So sánh issuer, SAN, thời gian, public key và ticket/CMDB/phê duyệt.
4. Phân loại chứng thư của CDN/đối tác/cloud đã được ủy quyền.
5. Điều tra chứng thư bất thường và liên hệ CA khi có dấu hiệu misissuance.
6. Theo dõi xử lý, revocation, sửa DNS/account và tác động thực tế.
7. Kiểm chứng rằng monitoring không bị thiếu do filter, delay hoặc pipeline lỗi.

Không cần thu và công bố mọi raw certificate của tổ chức vào nơi không được phép.

## 14. CAA trong DNS: giới hạn CA được phép cấp chứng thư

**Certification Authority Authorization (CAA)** là loại bản ghi DNS cho phép chủ sở hữu domain diễn đạt **CA nào được phép cấp chứng thư** theo những điều kiện tiêu chuẩn. Đây là lớp hạn chế quan trọng đối với public issuance.

Ví dụ minh họa:

~~~dns
; Dữ liệu giả định, không trỏ tới nhà cung cấp thực tế
corp.example. 3600 IN CAA 0 issue "ca-approved.example"
corp.example. 3600 IN CAA 0 issuewild ";"
corp.example. 3600 IN CAA 0 iodef "mailto:pki-alerts@corp.example"
~~~

Những tên CA trong ví dụ là placeholder. Cú pháp cụ thể và semantics phải được xem theo RFC/CA hỗ trợ; **iodef** chỉ là thông tin báo cáo yêu cầu/đề xuất, không bảo đảm có thông báo được gửi.

### 14.1. CAA làm được gì?

- Giảm số CA public **tuân thủ CAA** có thể phát hành cho domain theo policy.
- Giúp phát hiện/khắc phục việc phát hành từ CA ngoài danh sách mong muốn.
- Là một phần của quản trị quyền phát hành cho domain, đặc biệt khi có nhiều nhóm vận hành.

### 14.2. CAA không làm được gì?

- **Không sửa trust store của client** và không chặn một root bị cài trái phép tại endpoint.
- **Không bảo đảm một CA bị chiếm quyền sẽ tuân thủ CAA**.
- **Không thu hồi chứng thư cũ** khi thay CAA.
- **Không thay thế DNS account security, domain validation hoặc CT monitoring**.
- Không tự kiểm soát tất cả private CA không tham gia mô hình public issuance.
- Không tự chứng minh đường tới website được bảo vệ; DNS và CA policy vẫn phải được quản trị.

Cần kiểm tra phạm vi subdomain, delegation/CNAME, wildcard issuance và các domain do đối tác quản lý trước khi siết CAA, nếu không có thể làm gián đoạn cấp/renew chứng thư hợp lệ.

## 15. Thu hồi chứng thư: CRL, OCSP và giới hạn thực tế

Một chứng thư có thể cần thu hồi trước hạn khi key bị lộ, identity không còn hợp lệ hoặc CA phát hành sai. Các phương pháp phổ biến gồm:

- **CRL (Certificate Revocation List):** CA xuất danh sách chứng thư bị thu hồi.
- **OCSP (Online Certificate Status Protocol):** cơ chế truy vấn trạng thái thu hồi theo profile.
- **OCSP stapling:** server có thể gửi bằng chứng trạng thái do responder ký theo cơ chế hỗ trợ.
- **Short-lived certificates:** thời hạn ngắn để giảm cửa sổ giá trị của chứng thư, nhưng không thay thế đầy đủ quản lý vòng đời và chính sách.

### 15.1. Revocation không đồng nhất trên mọi client

Hành vi browser, OS, Java, thư viện TLS, VPN, mTLS gateway và IoT **khác nhau** theo cách kiểm tra revocation, cache, network failures, hard-fail/soft-fail và chính sách nhà cung cấp.

**Không kết luận chứng thư đã revoke thì mọi client sẽ lập tức từ chối**. Một số client có thể không kiểm tra OCSP/CRL trong mọi tình huống; cache và offline policy có thể làm trạng thái phản ánh chậm.

### 15.2. Root/Intermediate distrust khác revoke leaf

- **Leaf bị lộ:** thu hồi/thay leaf, xoay private key và rà soát server.
- **Intermediate bị lộ:** có thể phải ngừng toàn bộ nhánh phát hành, thay chứng thư phụ thuộc và cập nhật client trust/policy.
- **Root bị distrust:** phải phối hợp ứng dụng/OS/browser/gateway và khách hàng để cập nhật truststore, thay chain, xử lý compatibility.
- **Rogue root trong endpoint:** loại bỏ trust anchor trái phép cùng lúc điều tra quyền cài đặt và các phiên có thể bị ảnh hưởng.

Chỉ đặt một chứng thư vào CRL **không đủ** nếu client không có cơ chế thực thi trạng thái thu hồi đó.

## 16. Quản lý CA nội bộ theo nguyên tắc tối thiểu quyền

Một tổ chức cần PKI cho nhiều nhóm nhưng không nhất thiết phải có một CA được tin dùng cho mọi mục tiêu.

### 16.1. Phân tách chức năng

| Trust domain | Mục đích | Ranh giới nên áp dụng |
|---|---|---|
| Public WebPKI | HTTPS public | Root store/browser policy được cập nhật, hostname verification |
| Internal server TLS | API, DB, service nội bộ | Truststore của ứng dụng/workload, SAN/EKU phù hợp |
| mTLS client identity | Chứng thư client của service/đối tác | CA và authorization theo service/tenant |
| Wi-Fi/NAC EAP-TLS | Danh tính máy/người dùng kết nối 802.1X | CA client cert và policy RADIUS/NAC |
| VPN / IKEv2 | Danh tính peer/gateway/client | CA đúng profile và role cụ thể |
| Device/IoT PKI | Thiết bị có vòng đời dài | CA chuyên dụng, quyền phát hành hạn chế |
| Staging/testing | Dịch vụ và chứng thư không production | Không import root test vào production mặc định |

**Không dùng root staging trên máy production chỉ để tiện kiểm thử.** Một chứng thư hợp lệ trong staging không nên tự được chấp nhận như production identity.

### 16.2. Root CA và issuing CA nên có vai trò khác nhau

Một mô hình vận hành thường tách:
- **Offline/controlled root:** ít thao tác ký, private key bảo vệ nghiêm ngặt, thường qua HSM theo nhu cầu.
- **Issuing intermediate:** phát hành thường xuyên theo policy, tích hợp quy trình enrollment.
- **Registration/approval:** xác minh quyền xin chứng thư và domain/device/service owner.
- **Certificate lifecycle:** cấp, gia hạn, thay khóa, thu hồi, lưu audit.
- **Client trust distribution:** MDM/GPO/CI/CD/agent với danh sách được phê duyệt.

Không có mô hình nào “offline root” tự giải quyết hết rủi ro nếu intermediate có quyền phát hành rộng, key storage yếu hoặc store client chấp nhận quá nhiều anchors.

### 16.3. Không lạm dụng dùng chung private key

Private key của root/intermediate/leaf cần được phân quyền và bảo vệ theo mức rủi ro. Không đưa private key vào container image, Git, ticket hoặc chat. **Chỉ phân phối chứng thư public CA** để tạo trust anchor; không phân phối key ký của CA cho client.

## 17. Dùng truststore riêng theo ứng dụng và workload

Một số ứng dụng không cần biết mọi public root CA để giao tiếp với một backend cố định. **Truststore riêng** là một cách giới hạn tập CA được phép xác thực trong bối cảnh đó.

### 17.1. Mô hình cho một API nội bộ

~~~text
Order Service
    |
    | HTTPS/mTLS tới payment-api.corp.example
    |
    +-- Truststore: chỉ CA được phê duyệt cho payment-api
    +-- Kiểm tra SAN = payment-api.corp.example
    +-- serverAuth / clientAuth theo chính sách
    +-- Authorization theo service identity
    +-- Rotate CA/cert và giám sát expiry
~~~

Điểm cần tránh: chỉ cài một CA cụ thể **nhưng bỏ hostname verification**. Nếu cùng CA cấp cho nhiều server, một leaf của server khác có thể bị chấp nhận sai khi app không kiểm tra tên.

### 17.2. Root trust và client authentication trong mTLS

Server mTLS phải quyết định **CA nào được phép xác thực client** và cách ánh xạ certificate identity tới account/service/role. Nếu server tin một tập CA công khai hoặc nhiều CA nội bộ không kiểm soát cho clientAuth, có nguy cơ chấp nhận một chứng thư client từ nguồn ngoài kỳ vọng.

Hệ thống nên:
1. Trust đúng CA/issuer cho client của nhóm đó.
2. Kiểm tra path, EKU, thời hạn, policy và revocation theo yêu cầu.
3. Ràng buộc SAN/URI/service identity với account hoặc workload được phê duyệt.
4. Phân quyền đến từng operation, không chỉ kiểm tra “có cert hợp lệ”.
5. Lưu audit identity và phiên để hỗ trợ điều tra.

### 17.3. Không pin leaf certificate tùy tiện

**Certificate pinning** hoặc pin SPKI có thể giảm một số rủi ro từ CA công khai, nhưng tạo nguy cơ **outage khi rotate key/cert hoặc mất đường dự phòng**, nhất là với ứng dụng không có cơ chế cập nhật nhanh.

Nên ưu tiên truststore được quản lý, hostname validation, CA restrictions và pinning có chiến lược **backup pins/rotation/recovery** trong bối cảnh sản phẩm hỗ trợ. Không nhầm **certificate fingerprint** với **SPKI hash**; hai thứ khác nhau và có hành vi khác khi thay chứng thư.

## 18. PKI trong Wi-Fi, NAC, VPN và DNS mã hóa

### 18.1. Wi-Fi doanh nghiệp và 802.1X/EAP-TLS

Một thiết bị dùng EAP-TLS có thể phải xác minh **RADIUS/EAP server certificate** để tránh kết nối tới server xác thực giả; RADIUS/NAC cũng kiểm tra chứng thư client theo policy.

Nếu máy được cấu hình **tin bất kỳ CA** hoặc không kiểm tra server name, một mạng giả mạo có thể tạo rủi ro đánh lừa quá trình xác thực. Trong managed Wi-Fi cần cấu hình:
- Root CA được phép xác thực server RADIUS.
- Tên server expected và policy xác minh đúng.
- Cấp/chuyển/revoke client certificates theo thiết bị.
- NAC role và VLAN segmentation sau xác thực.
- Log phiên và thay đổi policy.

**EAP-TLS chứng minh danh tính mật mã theo chính sách**; nó không tự cập nhật endpoint, vá lỗi hay bảo đảm thiết bị sạch malware.

### 18.2. VPN IKEv2/IPsec và TLS VPN

- **IKEv2:** chứng chỉ gateway/client và trust anchors cần đúng peer identities và IKE profile.
- **TLS VPN:** cần kiểm tra server certificate, trust store của client, user/device auth, MFA và authorization.
- **WireGuard:** lõi dùng public-key peer model chứ không dùng X.509 CA mặc định; tổ chức có thể dùng PKI ở lớp enrollment/controller, nhưng không nên áp khái niệm X.509 trực tiếp cho mọi WireGuard handshake.

### 18.3. DoT/DoH

TLS tới DNS resolver phải xác thực **đúng resolver**, không chỉ tin “một CA đã biết”. DoH đi qua HTTPS, DoT thường qua TCP/853, và cả hai đều cần kiểm tra identity/trust theo profile.

Một resolver có TLS certificate hợp lệ nhưng không thuộc policy doanh nghiệp vẫn không mặc nhiên được phép xử lý dữ liệu DNS của nhân viên.

## 19. Trust boundary trong cloud và Kubernetes/service mesh

### 19.1. Cloud TLS termination

Trong cloud, một request có thể đi qua **client → CDN/WAF → load balancer → application → database**. Mỗi hop có TLS peer và truststore riêng.

~~~mermaid
flowchart LR
    C[Client] -->|TLS A| CDN[CDN/WAF]
    CDN -->|TLS B| LB[Load Balancer]
    LB -->|mTLS C| APP[Application]
    APP -->|TLS D| DB[(Database)]
    TR[Trust inventory] -.Policy và owner.-> CDN
    TR -.Origin CA.-> LB
    TR -.Service CA.-> APP
    TR -.DB CA.-> DB
~~~

Một root thêm vào truststore ứng dụng có thể khiến ứng dụng tin quá nhiều upstream CAs, ngay cả khi edge public vẫn dùng chứng chỉ do CA chính thức cấp. **Kiểm toán phải theo từng hop**, không chỉ theo browser.

### 19.2. Kubernetes và service mesh

Trong service mesh, workload identity có thể dựa vào chứng thư ngắn hạn do control plane/CA nội bộ cấp. Nếu các cluster chia sẻ trust domain quá rộng, một workload hoặc CA ở môi trường ít tin cậy có thể có đường chứng thực được chấp nhận ở môi trường khác, tùy authorization.

Nên xem:
- Trust domain và identity namespace có phân biệt theo cluster/tenant/env?
- Workload CA, trust bundle và key rotation được quản lý bởi ai?
- Các gateway/sidecar có xác minh SAN/URI identity đúng không?
- Có **authorization policy** cho service-to-service sau mTLS không?
- Có đường bỏ qua proxy/mesh không?
- Khi CA rotate hoặc cluster được ngừng, trust bundle đã cập nhật chưa?

**mTLS kết nối thành công không có nghĩa workload được quyền gọi tất cả API.** Đây là trách nhiệm của identity-based authorization.

### 19.3. Java runtime và container drift

Một microservice Java có thể dùng **cacerts riêng** trong JDK hoặc truststore được truyền qua cấu hình ứng dụng. Nếu root đã bị gỡ khỏi OS nhưng image vẫn đóng gói JDK cũ, service vẫn có thể tin root ấy.

Cần lập inventory theo **image digest, runtime version, truststore checksum/version, certificate chain và owner**. Không xem việc update host CA bundle là bằng chứng mọi container đã được cập nhật.

## 20. Quản trị trust anchors như tài sản bảo mật

Danh sách root CA là một loại **security-critical configuration**, cần lifecycle và quy trình thay đổi tương tự firewall rules hoặc IAM trust policies.

### 20.1. Dữ liệu inventory cần lưu

Một record trust anchor gợi ý:

~~~yaml
trust_anchor_id: "enterprise-api-root-01"
certificate_sha256_fingerprint: "<SHA256_CERT_FINGERPRINT>"
subject: "CN=Enterprise API Root CA, O=Example Organization"
issuer: "self-signed-lab-root"
purpose: ["internal-server-auth"]
allowed_environments: ["production"]
allowed_workloads: ["orders-api", "billing-api"]
owner_team: "platform-security"
deployed_via: "managed-truststore-pipeline"
approved_change: "PKI-CHANGE-EXAMPLE"
certificate_not_after: "2030-12-31T00:00:00Z"
last_inventory_verified_at: "2026-11-28T00:00:00Z"
rotation_plan: "documented-and-tested"
revocation_or_distrust_plan: "documented"
~~~

Đây chỉ là **schema minh họa**, không phải format bắt buộc của phần mềm PKI. Trường fingerprint trong ví dụ là placeholder và phải được lấy từ chứng thư thật khi vận hành.

### 20.2. Vì sao fingerprint cần đi kèm owner và mục đích?

Một fingerprint giúp nhận diện **byte chứng thư cụ thể**, nhưng không chứng minh:
- CA được phép cấp cho môi trường nào.
- Có ứng dụng nào đang dùng hoặc sẽ bị lỗi khi gỡ.
- CA có bị kiểm soát tốt hay không.
- Quyền phát hành subordinate thế nào.
- Root đã được phân phối tới thiết bị nào.

Nên lưu **ai đã phê duyệt**, **ứng dụng nào tin** và **tiêu chí thu hồi niềm tin**. Nếu cùng một subject có nhiều chứng thư khác nhau (cross-sign/renew), đừng gộp chỉ theo subject text.

### 20.3. Phân loại nguồn cài CA

- System/vendor root program.
- Enterprise PKI được phê duyệt.
- Partner CA cho tích hợp cụ thể.
- Test/lab CA chỉ dùng trong lab.
- TLS inspection CA có yêu cầu riêng.
- CA không rõ nguồn: **cần điều tra**.

Đừng tự xóa nhiều CA trên máy production khi chưa biết hệ quả. Nhưng cũng không chấp nhận vĩnh viễn một CA không có owner hoặc business need.

## 21. Quy trình phê duyệt một CA mới

Một CA root/intermediate mới không nên được nhập vào truststore chỉ vì một ứng dụng báo lỗi.

### 21.1. Câu hỏi bắt buộc

1. Ứng dụng **đang kết nối tới endpoint nào**? Hostname/SAN là gì?
2. Chứng thư bị từ chối vì **thiếu issuer**, **sai tên**, **hết hạn**, **revocation** hay **lỗi cấu hình khác**?
3. Có thật sự cần **tin một root mới**, hay server đang gửi thiếu intermediate?
4. CA này do ai vận hành? Ai bảo vệ khóa, cấp chứng thư và quản lý sub-CA?
5. CA có thể cấp những **tên hoặc mục đích khác** ngoài nhu cầu của ứng dụng không?
6. Có thể chỉ thêm CA vào **application truststore** thay vì system-wide?
7. Có thể dùng subordinate CA giới hạn namespace/purpose không?
8. Có chính sách kiểm tra hostname/identity, EKU, path validation và revocation?
9. Có kế hoạch rotate/expire/distrust, rollback và test trên client đại diện?
10. Ai phê duyệt thay đổi và ai chịu trách nhiệm giám sát?

### 21.2. Decision tree minh họa

~~~mermaid
flowchart TD
    A[Ứng dụng báo lỗi xác minh chứng thư] --> B{Đúng hostname và server không?}
    B -->|Không| FIX[Khắc phục DNS/SNI/SAN/endpoint]
    B -->|Có| C{Server gửi chain đúng?}
    C -->|Không| CHAIN[Sửa intermediate chain ở server]
    C -->|Có| D{CA đã được phê duyệt cho mục đích này?}
    D -->|Có| VERIFY[Kiểm tra store/path/expiry/EKU/revocation]
    D -->|Không| E{Có nhu cầu nghiệp vụ và rủi ro được chấp nhận?}
    E -->|Không| REJECT[Không thêm CA]
    E -->|Có| SCOPE[Thiết kế truststore hạn chế, owner và rollback]
~~~

Không có nhánh “tắt verify” vì đây không phải biện pháp xử lý hợp lệ cho hệ thống cần xác thực TLS.

## 22. Thực hành chỉ đọc: xem CA và chứng thư trong lab

Các ví dụ dưới đây **không tạo CA, không phát hành chứng thư giả và không thay truststore**. Chỉ chạy trên file, thiết bị hoặc endpoint do người học quản trị. Tên **api.lab.example** và đường dẫn **./lab-...** là placeholder; chúng không bắt buộc tồn tại trên máy.

### 22.1. Dùng OpenSSL đọc X.509 certificate

~~~bash
# Xem Subject, Issuer, thời hạn và fingerprint của cert lab
openssl x509 -in ./lab-root-ca.pem -noout \
  -subject -issuer -dates -fingerprint -sha256

# Kiểm tra Basic Constraints, Key Usage, EKU, SAN, Name Constraints
openssl x509 -in ./lab-intermediate.pem -noout -text
~~~

**Lưu ý:** output của OpenSSL có thể rất dài. Chứng thư CA public không chứa private key; tuy nhiên subject/hostname của chứng thư nội bộ có thể nhạy cảm, nên không đăng toàn bộ vào nơi không được phép.

Một subject hiển thị “Root CA” không có nghĩa chứng thư được tin. Cần kiểm tra **store và trust policy thực tế**.

### 22.2. Xác minh chain bằng trust bundle được chọn

~~~bash
# Giả sử trong lab có:
# approved-roots.pem: CA được ứng dụng phê duyệt
# lab-intermediates.pem: intermediate cần cho đường chứng thực
# api-cert.pem: chứng thư đầu cuối

openssl verify \
  -purpose sslserver \
  -verify_hostname api.lab.example \
  -CAfile ./approved-roots.pem \
  -untrusted ./lab-intermediates.pem \
  ./api-cert.pem
~~~

Lệnh trên kiểm tra một đường chứng thực theo chính sách của **OpenSSL và tập CA được đưa vào**, chứ không chứng minh mọi browser/Java client cũng chấp nhận. Việc kiểm tra revocation có thể cần nguồn CRL/OCSP và cấu hình bổ sung, không tự có trong ví dụ.

### 22.3. Quan sát TLS endpoint được phép

~~~bash
openssl s_client \
  -connect api.lab.example:443 \
  -servername api.lab.example \
  -verify_hostname api.lab.example \
  -verify_return_error \
  -showcerts < /dev/null
~~~

**-servername** gửi SNI để server chọn certificate phù hợp. **-verify_hostname** giúp kiểm tra tên theo chức năng OpenSSL được dùng, còn **-verify_return_error** không cho bỏ qua lỗi xác minh; kết quả phụ thuộc truststore và version của công cụ.

**-showcerts** hiển thị chain do peer gửi; **nó không nhất thiết cho thấy chính xác đường chain cuối cùng mà ứng dụng khác sẽ xây**. Muốn so sánh, phải kiểm tra đúng client/runtime và anchor store.

### 22.4. Linux: quan sát truststore

~~~bash
# Trên hệ thống dùng p11-kit, lệnh có thể khả dụng
trust list --filter=ca-anchors

# Liệt kê tên file chứng thư được hệ thống liên kết
ls -l /etc/ssl/certs
~~~

Distro hoặc container có thể dùng đường khác; một số ứng dụng tự mang bundle riêng. **Không suy từ /etc/ssl/certs rằng mọi chương trình đều dùng cùng store**.

### 22.5. Windows PowerShell: xem CA trong store

~~~powershell
# Chỉ đọc danh sách cert trong Root store ở mức máy
Get-ChildItem Cert:\LocalMachine\Root |
  Select-Object Subject, Thumbprint, NotAfter

# Root store theo người dùng hiện tại
Get-ChildItem Cert:\CurrentUser\Root |
  Select-Object Subject, Thumbprint, NotAfter
~~~

Trường **Thumbprint** do công cụ Windows hiển thị thường là fingerprint kiểu SHA-1 của chứng thư; có ích cho nhận diện trong UI nhưng **không nên dùng một mình như bằng chứng mật mã mạnh chống giả mạo**. Để đối chiếu chính xác, có thể tính SHA-256 fingerprint bằng công cụ được tổ chức cho phép.

### 22.6. Java keytool: truststore của runtime

~~~bash
# Kiểm tra kho cacerts của JDK hiện dùng, nhập mật khẩu khi được hỏi
keytool -list -cacerts

# Kiểm tra truststore riêng của ứng dụng, không in mật khẩu ra terminal
keytool -list -v \
  -keystore ./lab-app-truststore.p12 \
  -storetype PKCS12
~~~

Các lệnh này có thể hỏi mật khẩu truststore. **Không đưa mật khẩu trên dòng lệnh, log, commit hoặc chat**. Kiểm tra runtime/JDK cụ thể vì một host có thể cài nhiều JDK với cacerts khác nhau.

### 22.7. Kiểm chứng cần cả positive và negative case

- **Positive:** cert server đúng tên và đúng CA được phê duyệt phải kết nối được.
- **Negative:** cert ký bởi CA lab ngoài truststore phải bị từ chối.
- **Negative:** cert đúng CA nhưng **sai SAN** phải bị từ chối.
- **Negative:** cert hết hạn, sai EKU hoặc có chain vi phạm policy phải bị từ chối theo profile.
- **Regression:** khi gỡ root không còn dùng, client hợp lệ vẫn hoạt động; client dựa vào root cũ bị phát hiện để xử lý có kế hoạch.

Nên thực hiện trong **lab/staging** và lưu bằng chứng; không tự thay chứng thư production để “thử” khi chưa được duyệt.

## 23. Ma trận kiểm thử giảm phạm vi CA

| Test | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| T01 | Client kết nối đúng server, chain tới CA được phê duyệt | PASS | Path verification + TLS logs |
| T02 | Server gửi thiếu intermediate | Phát hiện/sửa chain, không thêm root vô căn cứ | s_client/verify + server config |
| T03 | Cert đúng CA nhưng SAN sai | Bị từ chối | Hostname verification result |
| T04 | Cert ký bởi CA test ngoài phạm vi | Bị từ chối trên production client | App/OS trust test |
| T05 | Client truststore có root không có owner | Tạo finding và review, không mặc định chấp nhận | Inventory + ticket |
| T06 | Intermediate vi phạm Name Constraints | Bị từ chối khi client/profile thực thi đúng | Path validation logs |
| T07 | Leaf yêu cầu serverAuth nhưng EKU không phù hợp | Bị từ chối theo policy | Verification report |
| T08 | Public certificate mới xuất hiện trên CT | Alert được phân loại theo owner/CA | CT event + issuance ticket |
| T09 | CAA chỉ cho CA được chọn | Hệ thống issuance hợp lệ vẫn renew đúng | DNS CAA + issuance logs |
| T10 | Root được gỡ khỏi OS nhưng vẫn ở Java truststore | Phát hiện drift | OS vs JDK inventory |
| T11 | Container dùng base image stale | Bị phát hiện, cập nhật và kiểm chứng | Image digest + truststore diff |
| T12 | Certificate bị revoke trong lab | Client phản ứng theo chính sách đã định | CRL/OCSP/client telemetry |
| T13 | Cross-signed chain có hai trust paths | Client xây đường phù hợp policy | Selected path + store version |
| T14 | mTLS cert từ CA đối tác không được phép | Từ chối client | Gateway + authorization logs |
| T15 | Wi-Fi EAP-TLS server tên sai/CA sai | Client không kết nối vào server giả định | Supplicant policy/log |
| T16 | Root TLS inspection triển khai tới nhóm không thuộc phạm vi | Phát hiện sai lệch và có rollback | MDM/GPO inventory |
| T17 | LB client-facing TLS đúng, origin TLS sai CA | Upstream verification không được bỏ qua | Proxy/upstream TLS logs |
| T18 | Cert renewal từ CA mới đã duyệt | Client hoạt động sau rotate, không nới trust thừa | Canary + truststore version |
| T19 | Distrust root theo kế hoạch | Ứng dụng còn hoạt động được xác minh | Dependency map + regression tests |
| T20 | Sự cố CA nghiêm trọng | Có owner, audit và bước khôi phục | Incident runbook + test evidence |
| T21 | Client chỉ có public CA nhưng cần private API | Truststore app riêng được cấu hình đúng | App-specific handshake logs |
| T22 | Device offline lâu, không cập nhật root store | Có risk assessment và kế hoạch remediation | Device inventory + last policy update |

Không ghi **PASSED** chỉ vì tên test tồn tại trong tài liệu. Cần môi trường, phiên bản client, truststore, certificate identifiers, timestamp và evidence của lần chạy.

## 24. Runbook khi phát hiện CA lạ hoặc chứng thư cấp sai

### Giai đoạn A — Phát hiện và xác minh

1. Xác định **sự kiện**: root mới trong store, CT báo chứng thư lạ, TLS interception bất thường hay key compromise.
2. Thu **subject, issuer, serial, SHA-256 fingerprint, SAN, AKI/SKI, thời hạn và chain** từ nguồn được phép.
3. Ghi truststore nào đang tin chứng thư, phạm vi máy/ứng dụng và thời điểm xuất hiện.
4. Kiểm tra owner, MDM/GPO/package changes, CI/CD, cloud policy và change ticket.
5. Phân biệt **phát hành hợp lệ do nhóm khác quản lý** với dấu hiệu cấp sai hoặc sửa store trái phép.
6. Ước lượng những hostname, client, phiên và trust domain có thể chịu ảnh hưởng.

### Giai đoạn B — Giảm tác động

- Nếu có chứng thư **cấp sai**, phối hợp chủ domain/CA, xác minh CT evidence, yêu cầu revoke và kiểm soát đường giả mạo liên quan.
- Nếu có **root trái phép** trên endpoint, dùng quy trình quản lý thiết bị để loại bỏ/quarantine phù hợp sau khi đánh giá bằng chứng, không xóa bừa ảnh hưởng hệ thống trọng yếu.
- Nếu **CA key bị lộ**, xem phạm vi cấp phát, dừng issuance, thay CA/keys/chains và cập nhật trust anchors theo kế hoạch được phê duyệt.
- Nếu **TLS inspection proxy** bị lạm dụng, kiểm soát quyền proxy/MDM, khóa/CA và các điểm giải mã có thể đã thấy dữ liệu.
- Nếu **client không thể cập nhật** (IoT/OT), cân nhắc cô lập vùng và kiểm soát compensating cho đến khi thay thế.

### Giai đoạn C — Khôi phục

1. Phát hành/triển khai chain mới từ CA được phê duyệt.
2. Kiểm thử hostname, EKU, revocation, mTLS và client compatibility.
3. Rollout theo nhóm nhỏ/canary, không bỏ verification để giảm lỗi.
4. Gỡ anchor cũ theo phụ thuộc đã xác minh; có cơ chế xử lý client offline.
5. Theo dõi handshake errors, service SLO, CA inventory drift.
6. Giữ audit/timeline đủ để truy vết và làm hậu kiểm.

### Giai đoạn D — Hậu kiểm

Ghi rõ **lỗi quy trình nào đã cho CA ngoài phạm vi được tin**, cách phát hiện, vì sao truststore thiếu owner, ảnh hưởng tới người dùng và biện pháp ngăn tái diễn. Không chỉ ghi “đã xóa cert” nếu root hoặc key issuance vẫn tồn tại ở store khác.

## 25. Chỉ số đo chất lượng CA trust governance

| Chỉ số | Ý nghĩa | Cách tính gợi ý |
|---|---|---|
| **Approved-anchor coverage** | Các anchor đang dùng có record phê duyệt | CA được phê duyệt/CA quan sát trong scope |
| **Orphan CA count** | CA không có owner/mục đích | Đếm theo store, env, application |
| **Truststore drift rate** | Mức sai lệch so với baseline | Số store khác policy / số store kiểm tra |
| **Exception age** | Ngoại lệ CA legacy tồn tại bao lâu | Ngày hiện tại trừ ngày phê duyệt |
| **Certificate expiry lead time** | Thời gian còn lại để thay cert | NotAfter trừ thời điểm quan sát |
| **Unexpected issuance alerts** | Cert công khai không có ticket/owner | CT events cần điều tra theo domain |
| **Revocation/distrust latency** | Độ trễ thực thi loại bỏ trust | Khi phát hiện → khi client được xác minh từ chối |
| **Key rotation coverage** | CA/leaf có kế hoạch đổi khóa | Assets có kế hoạch / assets thuộc scope |
| **Client verification coverage** | Client có positive/negative test | Client profiles được kiểm chứng / profiles mục tiêu |
| **Path diversity awareness** | Đường chứng thực thay thế đã được biết | Chains/anchors được inventory cho những service trọng yếu |

### 25.1. Một tỷ lệ cao không luôn chứng minh an toàn

Ví dụ, 95% root CA trong inventory có owner không chứng minh 5% còn lại vô hại. Nếu 5% đó là root phục vụ traffic của hệ thống thanh toán, mức rủi ro có thể rất cao.

Cần kết hợp **mức độ quan trọng của tài sản, phạm vi CA có thể ký, dấu hiệu sai lệch và độ tin cậy của dữ liệu**. Một chỉ số tổng không thay thế threat model.

### 25.2. Lưu bằng chứng về thay đổi và kiểm chứng

Mỗi bản cập nhật truststore nên có:
- ID và fingerprint của anchor được thêm/gỡ.
- Nhóm endpoint/ứng dụng liên quan.
- Owner, phê duyệt, lý do và thời hạn.
- Version cấu hình/truststore và phương thức phân phối.
- Trạng thái trước/sau và thời điểm hiệu lực.
- Positive/negative tests, kết quả thực tế, rollback.
- Các ứng dụng lệch policy hoặc chưa cập nhật.

## 26. Tình huống thực hành có đáp án gợi ý

### Tình huống A — API nội bộ tin mọi public root

Một service chỉ gọi **db-api.corp.example**, nhưng dùng hệ thống public root store cùng với ba root lab cũ.

**Gợi ý:** đánh giá lại trust domain. Cần xác định CA thật sự cấp cho db-api, sử dụng truststore ứng dụng/namespace phù hợp và SAN verification. Gỡ root lab khi có bằng chứng không còn phụ thuộc; lưu rotation/rollback.

### Tình huống B — Trình duyệt báo an toàn, ứng dụng Java thất bại

Browser kiểm tra HTTPS thành công nhưng Java client báo **PKIX path building failed**.

**Gợi ý:** so sánh JDK truststore, chain server gửi, SAN, runtime version, policy revocation và security provider. Không import root mới vào Java ngay; lỗi có thể chỉ do intermediate bị thiếu hoặc truststore cũ.

### Tình huống C — Root enterprise cài vào tất cả laptop

Tổ chức muốn dùng TLS inspection và cấp root qua MDM. Một số người cho rằng đây là “bảo mật tuyệt đối vì mọi traffic được kiểm tra”.

**Gợi ý:** proxy trở thành điểm giải mã dữ liệu nhạy cảm và có quyền tạo chứng thư được thiết bị tin. Cần owner, HSM/khóa, quyền sửa, log privacy, chính sách ngoại lệ, TLS upstream validation, audit và giới hạn thiết bị. Không coi inspection là vô rủi ro.

### Tình huống D — CT báo chứng thư từ CA lạ

Một certificate cho **login.corp.example** xuất hiện trong CT, issuer không phải CA thường dùng.

**Gợi ý:** kiểm tra SAN, thời gian, CA, ticket cấp phát, đối tác CDN/cloud, domain validation và CAA. Nếu không có authorization, điều tra misissuance, liên hệ CA và đánh giá khả năng điều hướng traffic. CT là tín hiệu phát hiện, chưa chứng minh xâm nhập đã thành công.

### Tình huống E — CAA đã khóa CA, vẫn có certificate lạ

Đội vận hành thêm CAA giới hạn CA được cấp phát nhưng một chứng thư ngoài danh sách vẫn được client chấp nhận.

**Gợi ý:** CAA không phải policy runtime của client và không thu hồi chứng thư đã cấp; cần xem thời điểm phát hành, CAA có hiệu lực lúc đó không, CA có tuân thủ không, CT logs và trạng thái chain. Nếu client tin một root trái phép, CAA không loại bỏ root đó.

### Tình huống F — Subordinate CA không có Name Constraints

Một intermediate dành cho staging được root production ký nhưng không ràng buộc namespace; sản phẩm cho phép chứng thư staging trong production trust domain.

**Gợi ý:** tách trust domain, giới hạn issuer, triển khai subordinate có constraints khi hỗ trợ, và xác minh mTLS/application identity. Một tên staging trên certificate không tự khiến production client từ chối nếu policy chỉ kiểm tra path mà không ràng buộc tên đúng.

### Tình huống G — Cross-sign giữ đường tin cậy tới root cũ

Một root dự kiến ngừng dùng đã bị xóa khỏi một số store, nhưng các client khác vẫn xây chain qua một cross-sign hợp lệ tới anchor khác.

**Gợi ý:** inventory đường chain có thể xây được theo client, phân biệt leaf/intermediate/anchor, kiểm tra path builder và chính sách distrust. Không dựa vào issuer string của leaf.

### Tình huống H — EAP-TLS Wi-Fi không kiểm tra tên server

Máy nhân viên tin một CA rộng và không hạn chế danh tính máy chủ RADIUS.

**Gợi ý:** phải cấu hình expected server name và CA đúng policy cho supplicant, kết hợp EAP-TLS certificate validation và NAC controls. Không chỉ giới hạn MAC/VLAN; sai identity server có thể tạo điều kiện giả mạo.

### Tình huống I — Revoked leaf vẫn được một client legacy chấp nhận

Chứng thư đã thu hồi trên CA, nhưng thiết bị IoT cũ vẫn kết nối như bình thường.

**Gợi ý:** kiểm tra khả năng revocation của client, CRL/OCSP/fail-open, firmware, cache và đường kết nối. Với thiết bị không hỗ trợ, cần compensating controls và kế hoạch thay thế; đừng giả định revoke làm mọi thiết bị lập tức từ chối.

### Tình huống J — Chỉ cần mTLS cho một đối tác

Một gateway mTLS thêm cả public WebPKI trust bundle làm danh sách CA chấp nhận client certificate.

**Gợi ý:** rủi ro trust quá rộng. Nên giới hạn đúng **đối tác/issuer** và identity client, kiểm tra EKU clientAuth và ràng buộc SAN/role, rồi authorization cho API. Chứng thư được public CA cấp không tự chứng minh tư cách đối tác.

### Tình huống K — K8s service mesh dùng chung CA cho test và production

Workload test có certificate được xác thực bởi CA mà sidecar production cũng tin.

**Gợi ý:** tách trust domain hoặc ràng buộc identity/authorization mạnh, quản lý trust bundle riêng và luồng cross-cluster; không coi mTLS alone bảo đảm segmentation.

### Tình huống L — Cert chain lỗi sau chuyển CDN

Sau khi đổi CDN, chứng thư client-facing hợp lệ nhưng CDN từ chối chứng thư origin. Một kỹ sư muốn tắt verification để khôi phục nhanh.

**Gợi ý:** kiểm tra hostname/SNI origin, intermediate chain, truststore, EKU và policy CDN; phát hành/điều chỉnh đúng cert chain, không bỏ verify. Test canary/rollback tới cấu hình trước đã an toàn.

### Tình huống M — Root có cùng Subject nhưng fingerprint khác

Hai chứng thư mang Subject giống nhau, một cũ một mới, được ghi như một dòng inventory.

**Gợi ý:** subject không phải unique ID. Cần xem public key, SHA-256 fingerprint, issuer, serial, SKI/AKI, cross-sign và đường chain; quản lý như các đối tượng/hồ sơ có phiên bản riêng.

### Tình huống N — Thêm CA root để hết lỗi hostname

Ứng dụng báo **certificate verify failed: hostname mismatch**, admin import thêm root CA.

**Gợi ý:** việc thiếu CA không sửa được sai SAN/hostname. Xác định endpoint và cấu hình SNI/DNS; cấp cert đúng tên nếu server được phê duyệt. Không tắt kiểm tra hostname để che lỗi.

## 27. Sai lầm thường gặp

1. **Tin càng nhiều CA càng an toàn.** Tập CA lớn hơn có thể mở rộng những bên có quyền phát hành được client chấp nhận.
2. **Coi root self-signed là tự đáng tin.** Phải là trust anchor được cấu hình.
3. **Chỉ kiểm tra chứng thư có chữ ký hợp lệ.** Còn phải xác minh chain, SAN, EKU, thời hạn và policy.
4. **Dùng một root nội bộ cho mọi mục đích.** Làm tăng blast radius giữa server TLS, Wi-Fi, VPN và mTLS.
5. **Import CA vào OS cho một lỗi Java riêng.** Có thể không sửa lỗi và làm mở rộng trust không cần thiết.
6. **Thêm root mới khi server thiếu intermediate.** Sai nguyên nhân, tăng rủi ro.
7. **Bỏ certificate/hostname verification để kết nối thành công.** Làm mất xác thực endpoint.
8. **Coi CA tin cậy đồng nghĩa endpoint được phép.** Trust và authorization khác nhau.
9. **Tin public root cho mTLS clientAuth của mọi đối tác.** Có thể chấp nhận issuer ngoài phạm vi.
10. **Coi Name Constraints trên root anchor luôn được mọi client thực thi.** Cần kiểm chứng path/constraints và truststore.
11. **Nhầm pathLen với giới hạn namespace.** pathLen chỉ giới hạn chuỗi CA cấp dưới.
12. **Dùng chung CA staging và production.** Làm mờ trust boundary.
13. **Coi CT là cơ chế ngăn cấp phát.** CT chủ yếu hỗ trợ transparency và detection.
14. **Coi CAA là cơ chế chặn runtime.** CAA giới hạn issuance đối với CA tuân thủ, không thay truststore.
15. **Cho rằng revoke có hiệu lực tức thì với mọi client.** Revocation behavior khác nhau và có cache/fail-open.
16. **Chỉ nhìn cert chain do server gửi.** Client có thể xây đường khác tới anchor khác.
17. **Xóa root trên host và tin mọi container/Java đã hết trust.** Mỗi runtime có thể dùng store riêng.
18. **Dùng Subject làm khóa duy nhất.** Cross-sign/renew có thể có subject giống nhau.
19. **Không giám sát CA trong endpoint khi cài TLS inspection.** Có nguy cơ truy cập dữ liệu nhạy cảm tại proxy.
20. **Không có owner và quy trình thay root.** Khó xử lý khi CA hết hạn, bị lộ hoặc distrust.
21. **Không kiểm thử negative cases.** Một root ngoài phạm vi vẫn được chấp nhận mà không ai biết.
22. **Gộp tất cả certificate thành asset với IP.** Certificate có thể dùng trên nhiều endpoint và IP thay đổi.
23. **Coi leaf key compromise là root compromise.** Mức độ phản ứng khác nhau.
24. **Coi certificate pinning là cách chữa mọi vấn đề.** Có thể tạo outage nếu rotation/recovery không được thiết kế.
25. **Đăng private key hoặc session secret để debug.** Làm hỏng bảo mật ngay cả khi chain đúng.
26. **Tin CA chỉ vì tên hoặc logo.** Phải xác minh fingerprint, owner, deployment và trust policy.
27. **Không kiểm tra client offline lâu ngày.** Truststore lỗi thời có thể tiếp tục tin root đã distrust.
28. **Thay root đồng loạt không có rollback.** Có thể gây gián đoạn VPN, Wi-Fi, API, cloud và IoT.
29. **Chỉ đếm số root CA làm thước đo bảo mật.** Cần xét scope, authorization, path alternatives và tài sản trọng yếu.
30. **Chỉ quan tâm WebPKI.** Private CA và identity PKI của workload cũng tạo rủi ro nếu trust quá rộng.

## 28. Checklist kiểm soát rủi ro tin cậy quá nhiều CA

- [ ] Xác định các **trust domains**: public WebPKI, internal TLS, mTLS, VPN, Wi-Fi, IoT, staging/prod.
- [ ] Có inventory root/intermediate anchors theo **fingerprint, owner, mục đích, môi trường và store**.
- [ ] Ghi rõ vì sao mỗi CA cần được tin và phạm vi hostname/identity có thể cấp.
- [ ] Loại bỏ root không có nhu cầu sau đánh giá dependency và approval.
- [ ] Không cài root lab/staging vào production mặc định.
- [ ] Không thêm CA system-wide khi chỉ một ứng dụng cần trust riêng.
- [ ] Xác minh **SAN/hostname**, path validation, EKU, Basic Constraints và Key Usage.
- [ ] Dùng Name Constraints/subordinate scope và pathLen khi phù hợp, thử trên client thực.
- [ ] Không coi trust anchor constraints được tất cả client áp như nhau.
- [ ] Có chính sách mTLS client trust riêng và authorization sau cert validation.
- [ ] Với Wi-Fi/EAP-TLS, kiểm tra **RADIUS server identity**, CA policy và client cert lifecycle.
- [ ] Với VPN/DoT/DoH, chỉ tin đúng gateway/resolver được phê duyệt.
- [ ] Dùng truststore riêng cho application/workload khi điều đó giảm blast radius.
- [ ] Quản lý OS, browser, Java, container, cloud LB, service mesh và network device trust stores.
- [ ] Theo dõi cross-sign/alternate chains và đường validation của client đại diện.
- [ ] Có CAA cho domain public phù hợp, lưu owner và kiểm thử certificate renewal.
- [ ] Giám sát CT cho domain sở hữu và phân loại issuance của CDN/đối tác.
- [ ] Hiểu giới hạn OCSP/CRL/revocation trên browser và client legacy.
- [ ] Có phương án key compromise, revoke, CA rotation và distrust.
- [ ] Với TLS inspection, giới hạn deployment, logging, quyền admin và bảo vệ dữ liệu giải mã.
- [ ] Lưu audit add/remove trust anchor, ứng dụng chịu ảnh hưởng và người phê duyệt.
- [ ] Bảo vệ private keys/HSM/secrets, không lưu khóa CA vào thiết bị client.
- [ ] Kiểm thử positive và negative cases (CA sai, hostname sai, EKU sai, root bị gỡ).
- [ ] Đánh giá client offline/IoT và các thiết bị không nhận cập nhật truststore đúng hạn.
- [ ] Có SLO, runbook, change window và rollback cho việc thay CA trọng yếu.
- [ ] Theo dõi orphan CAs, store drift, certificate expiry, unexpected issuance và remediation lag.
- [ ] Không đánh dấu PASS từ một công cụ duy nhất; đối chiếu ứng dụng và runtime thực tế.

## 29. Tổng kết

**Rủi ro khi tin cậy quá nhiều CA** không nằm đơn thuần ở số root certificates, mà ở **quyền phát hành nào được một endpoint chấp nhận, tại trust domain nào, với những kiểm tra và giám sát gì**. Một root hoặc intermediate được tin vượt phạm vi có thể làm tăng tác động của misissuance, lộ khóa, TLS interception, cấu hình sai hoặc cross-sign ngoài dự kiến. Khi OS, browser, Java, container và service mesh dùng những trust stores khác nhau, việc kiểm soát phải dựa trên **inventory và bằng chứng từ client thật**.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, phòng vệ bền vững là **chọn đúng trust anchor, tách public/private/mTLS/Wi-Fi/VPN trust domains, kiểm chứng SAN/chain/EKU/constraints, quản lý chứng thư và khóa, giám sát CT/CAA, xử lý revocation/distrust có kế hoạch và giữ authorization sau TLS**. Khi mọi CA đều có **owner, mục đích, phạm vi, phương án thu hồi và ca kiểm thử**, PKI hỗ trợ bảo mật kênh truyền mà không vô tình mở rộng ranh giới tin cậy của cả hệ thống.
