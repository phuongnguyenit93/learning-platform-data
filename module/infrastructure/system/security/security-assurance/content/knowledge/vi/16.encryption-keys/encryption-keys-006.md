# Certificate management

Trong chương **Mã hóa và khóa**, **certificate management** (quản lý chứng thư số) là quá trình quản trị toàn bộ vòng đời của chứng thư số và những thành phần liên quan: **xác lập danh tính cần chứng thực, lựa chọn nơi phát hành, tạo và bảo vệ khóa, yêu cầu cấp chứng thư, triển khai, kiểm tra chuỗi tin cậy, theo dõi, gia hạn, thay khóa, thu hồi và loại bỏ**. Mục đích là bảo đảm rằng một hệ thống đang tin **đúng khóa công khai gắn với đúng danh tính trong đúng phạm vi**, theo chính sách và thời điểm được kiểm tra.

Một nền tảng học trực tuyến dùng HTTPS trên miền công khai, mTLS giữa API và report worker, chứng thư của một CA nội bộ cho dịch vụ quản trị, và chứng thư ký mã/artifact cho pipeline phát hành. Mỗi loại có **mục đích, nguồn tin cậy, điều kiện sử dụng, hạn dùng và rủi ro khác nhau**. Nếu hệ thống chỉ xem bảng điều khiển của CA có trạng thái “Issued” rồi kết luận mọi kết nối an toàn, có thể bỏ sót certificate hết hạn thực tế đang được load bởi một pod cũ, một chain thiếu intermediate, trust store không được cập nhật hoặc một private key đã bị sao chép trái phép.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**: xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện và tổ chức chương trình security assurance liên tục trong phát triển/vận hành. Vì vậy, thay vì chỉ học lệnh tạo chứng thư, chúng ta sẽ nối **risk → certificate requirements → controls → tests/evidence → assessment → finding/remediation → residual risk**.

**Ý chính:** Chứng thư số không tự tạo an toàn. Nó hỗ trợ xác thực và thiết lập tin cậy **nếu** khóa riêng được bảo vệ, danh tính được kiểm chứng phù hợp, client xác minh chứng thư đúng, chứng thư được sử dụng cho mục đích thích hợp và vòng đời được vận hành/kiểm tra liên tục.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích certificate, public/private key, CSR, CA, PKI, trust anchor và certificate chain.
2. Đọc các trường X.509 quan trọng: subject, issuer, SAN, validity, serial number, key usage, extended key usage, basic constraints và fingerprint.
3. Phân biệt chứng thư server TLS, client/mTLS, workload, CA, code signing và những use cases khác.
4. Phân tích rủi ro từ certificate hết hạn, cấu hình validation sai, CA/trust store sai, private key bị lộ hoặc cấp nhầm danh tính.
5. Xây quy trình inventory, issuance, deployment, renewal, rotation, revocation, retirement và xử lý sự cố.
6. Xác định rõ ownership giữa service owner, PKI/CA team, platform, application, security assurance và risk owner.
7. Thiết kế kiểm thử **chain validation, identity matching, certificate purpose, key continuity/rotation, revocation behavior, fail closed** trong môi trường Java và dịch vụ phân tán.
8. Xây evidence catalog và **Claim–Argument–Evidence (CAE)**; phân biệt design, implementation và operating effectiveness.
9. Tổ chức giám sát certificate expiry, thay đổi trust, phát hành bất thường và chất lượng automation.
10. Nhận diện finding, evidence gap, exception và quyết định residual risk theo thẩm quyền.

## 2. Chứng thư số thực chất là gì?

### 2.1. Khái niệm cơ bản

Trong nhiều hệ thống, một chứng thư theo định dạng **X.509** chứa:

- **Public key** của chủ thể;
- **Danh tính và thuộc tính** mà chứng thư mô tả;
- **Tổ chức phát hành** và các thông số nhận diện;
- **Khoảng thời gian hiệu lực**;
- **Hạn chế/công dụng** của khóa hoặc chứng thư;
- **Chữ ký số** của bên phát hành đối với phần nội dung chứng thư.

Chứng thư nói theo ngôn ngữ đơn giản: “bên phát hành xác nhận khóa công khai này gắn với những thông tin danh tính/thuộc tính được nêu, trong những điều kiện đã định”.

**Chứng thư thường là dữ liệu công khai; private key tương ứng mới là bí mật phải bảo vệ.** Không lưu trữ, gắn vào ticket hoặc gửi private key cho người khác chỉ vì đã có file certificate hợp lệ.

### 2.2. Certificate, key pair, CSR và private key

| Thành phần | Vai trò | Bảo vệ/vận hành |
|---|---|---|
| **Private key** | Dùng ký hoặc thực hiện thao tác mật mã tương ứng, chứng minh quyền kiểm soát khóa | Phải hạn chế truy cập; ưu tiên cơ chế quản lý khóa phù hợp rủi ro |
| **Public key** | Khóa được các bên dùng xác minh chữ ký/thao tác theo thuật toán | Có thể công bố; cần ràng buộc đúng danh tính qua trust |
| **Certificate** | Gắn public key với chủ thể và điều kiện do issuer ký | Phải xác minh chain, tên, purpose, thời gian và policy |
| **CSR — Certificate Signing Request** | Yêu cầu cấp certificate chứa public key và thông tin yêu cầu, thường có proof of possession | Không thông thường chứa private key; nội dung yêu cầu vẫn phải kiểm tra |
| **CA — Certificate Authority** | Thực thể cấp và ký chứng thư theo chính sách | CA signing keys là tài sản bảo mật trọng yếu |
| **Trust anchor** | Điểm xuất phát được client tin theo cấu hình/chính sách | Phải quản trị chặt việc thêm/xóa, phiên bản và phân phối |
| **Chain** | Chuỗi từ leaf qua các CA trung gian tới trust anchor | Phải xác minh các ràng buộc, không chỉ thấy issuer name |

**Định danh trong certificate không bằng authorization.** Một service có certificate hợp lệ với tên “report-worker” chưa đương nhiên có quyền xuất mọi bảng điểm.

### 2.3. Certificate khác mật khẩu và bearer token

Certificate cung cấp bằng chứng về một **public key** và danh tính trong phạm vi tin cậy. Khi thực hiện TLS/mTLS, các bên cần xác minh chain và chứng minh quyền kiểm soát private key tương ứng thông qua handshake. Điều này khác bearer token: ai có token hợp lệ có thể dùng theo những điều kiện hệ thống chấp nhận.

Tuy nhiên, nếu **private key bị sao chép**, một bên khác có thể giả mạo chủ thể trong những điều kiện sử dụng nhất định. Vì vậy “certificate là dữ liệu công khai” **không đồng nghĩa có thể chia sẻ file keystore chứa cả private key**.

## 3. PKI và chuỗi tin cậy

### 3.1. Các thành phần điển hình

**Public Key Infrastructure (PKI)** bao gồm công nghệ, quy trình và vai trò để cấp, quản lý, kiểm tra và thu hồi chứng thư cũng như quản trị tin cậy.

Một cấu trúc minh họa:

~~~mermaid
flowchart TD
    P["Policy, identity vetting, roles"] --> RA["Registration / approval process"]
    RA --> ICA["Issuing CA / intermediate CA"]
    ROOT["Root CA / trust anchor"] --> ICA
    ICA --> LEAF["Server, client, workload certificates"]
    LEAF --> APP["TLS/mTLS applications"]
    TRUST["Trust-store governance"] --> APP
    REV["Revocation/status services"] --> APP
    INV["Certificate inventory and monitoring"] --> LEAF
    INV --> A["Evidence / assurance assessment"]
    APP --> A
~~~

Trong thực tế, một **root CA** có thể được giữ offline và dùng để ký các issuing/intermediate CAs. Một số môi trường dùng public CAs, private CAs, managed certificate services hoặc mô hình mesh/workload identity. Mỗi mô hình có ranh giới trách nhiệm khác nhau; không phải mọi PKI đều có một bộ phận RA tách riêng.

### 3.2. Root CA, intermediate CA và leaf

- **Root CA:** điểm tin cậy được phân phối hoặc cấu hình trong trust store. Self-signed root certificate không tự được tin chỉ vì tự ký; client tin nó vì được **chọn làm trust anchor**.
- **Intermediate/issuing CA:** phát hành các chứng thư trong phạm vi được root/CA cao hơn ủy quyền, chịu constraint và policy.
- **Leaf/end-entity certificate:** chứng thư được server, client hoặc workload sử dụng cho mục đích cụ thể, thông thường không được quyền ký chứng thư như CA.

Đường xác thực có thể là:

~~~text
Trusted root (được cấu hình)
  └── Intermediate CA (chữ ký/constraints hợp lệ)
         └── Leaf certificate (đúng tên và công dụng)
~~~

**Tìm được chuỗi issuer-subject phù hợp không tự chứng minh chain hợp lệ.** Client phải thực hiện path validation theo quy tắc áp dụng: chữ ký, validity, basic constraints, key usage, name constraints/policy khi có, độ mạnh thuật toán, trust anchor, và quy tắc revocation/status theo cách client đã cấu hình.

### 3.3. Trust store và keystore

- **Trust store:** tập các CA/trust anchors hoặc đối tượng được tin theo chính sách để xác minh certificate của bên kia.
- **Keystore:** kho chứa key material hoặc certificate entries dùng bởi một hệ thống; tùy định dạng/công cụ có thể chứa private key cùng chain hoặc chỉ public certificates.
- **Key management system/HSM:** hệ thống/cơ chế quản lý và thực hiện hoạt động với khóa; mức bảo vệ, exportability và audit tùy loại.

Không nên diễn giải keystore luôn đồng nghĩa “an toàn” hoặc trust store luôn chỉ có root CA. Cần kiểm tra **entries thực tế, quyền đọc/sửa, cách phân phối và runtime configuration**.

### 3.4. Root of trust là quyết định quản trị

Một root/CA được cài vào trust store có thể ảnh hưởng **rất nhiều phiên giao tiếp**. Nếu ứng dụng thêm một CA không được kiểm soát vào trust store “để TLS hết lỗi”, rủi ro là mở rộng số tổ chức/khóa có khả năng chứng thực những danh tính mà ứng dụng chấp nhận.

Vì vậy thêm/xóa root phải có **owner, căn cứ, approval, kiểm thử kết nối và rollback**. Không được coi root rollout chỉ là thay file cấu hình.

## 4. Cấu trúc X.509 cần biết

### 4.1. Các trường thường xuất hiện

| Thuộc tính | Mục đích | Câu hỏi assurance |
|---|---|---|
| **Version** | Phiên bản cấu trúc X.509 | Client/tool có xử lý đúng extension cần thiết không? |
| **Serial number** | Nhận diện certificate trong phạm vi issuer | Dùng được khi theo dõi, revoke và điều tra không? |
| **Issuer** | CA phát hành chứng thư | Issuer thuộc chain được phê duyệt không? |
| **Subject** | Thông tin định danh/chủ thể | Có được xác minh theo policy không? |
| **Subject Alternative Name (SAN)** | Các tên/định danh bổ sung như DNS hoặc IP | Tên endpoint thật có khớp với chứng thư không? |
| **Not Before / Not After** | Khoảng hiệu lực | Có còn hiệu lực theo đồng hồ và policy không? |
| **Subject Public Key Info** | Thuật toán và public key | Thuật toán/độ mạnh phù hợp baseline? |
| **Signature algorithm** | Thuật toán chữ ký của issuer | Có được client chấp nhận và thuộc policy hiện hành? |
| **Basic Constraints** | Phân biệt CA và khả năng ký cấp dưới | Leaf có bị dùng như CA trái phép không? |
| **Key Usage** | Các công dụng mật mã được phép | Sử dụng khóa có phù hợp chứng thư không? |
| **Extended Key Usage (EKU)** | Mục đích cấp cao như server/client auth tùy certificate | Dùng certificate đúng role không? |
| **SKI/AKI** | Gợi ý định danh khóa chủ thể/issuer | Chain building có nhất quán không? |
| **CRL Distribution Points/AIA** | Nguồn status/issuer bổ trợ khi có | Client có kiểm tra hoặc sử dụng theo thiết kế? |
| **Certificate Policies / Name Constraints** | Điều kiện/policy bổ sung khi xuất hiện | Path validator có thực thi ràng buộc phù hợp không? |
| **Fingerprint** | Dấu băm để nhận diện certificate bytes | Có truy vết đúng certificate runtime không? |

Chỉ xem hai trường subject/expiry **không đủ** cho chứng nhận an toàn của một kết nối.

### 4.2. SAN và hostname verification

Trong HTTPS hiện đại, **DNS names/IPs được kỳ vọng nằm trong SAN** theo quy tắc của client/chứng thư tương ứng. Không thiết kế ứng dụng chỉ so Common Name (CN) theo cách tự viết rồi bỏ qua SAN. Khi client truy cập hostname, cần xác minh **certificate hợp lệ cho đúng hostname** đang gọi, không chỉ chữ ký CA.

Ví dụ certificate chứa SAN DNS cho API công khai không có nghĩa có thể dùng với một hostname nội bộ khác, hoặc với IP literal không có quy tắc khớp tên tương ứng.

**SNI (Server Name Indication)** giúp server lựa chọn certificate khi phục vụ nhiều tên trên một địa chỉ; nó không thay hostname verification ở client.

### 4.3. Basic Constraints, KU và EKU

Một leaf TLS có thể được cấp cho **server authentication**, trong khi client certificate mTLS phục vụ **client authentication**; chứng thư CA lại có giới hạn riêng về khả năng ký. Hãy xác định **công dụng được phép** theo trường X.509, loại certificate, chính sách phát hành và cách TLS client/server kiểm tra.

Không nên suy ra certificate do một CA được tin phát hành thì hợp lệ **cho mọi mục đích**. Một certificate chỉ phù hợp code signing cũng không được tự dùng làm server TLS mà không xác minh các ràng buộc.

### 4.4. Certificate fingerprint dùng để đối chiếu

Fingerprint giúp nhận diện phiên bản certificate trong inventory hoặc khi điều tra. Thường chọn hash có độ mạnh phù hợp policy, ví dụ SHA-256 cho việc nhận diện; **fingerprint không phải secret** và không chứng minh chủ thể đáng tin nếu không có chain/identity validation.

Khi certificate được **gia hạn với key mới hoặc cùng key**, fingerprint sẽ thay đổi nếu nội dung certificate thay đổi; hệ thống inventory phải theo dõi **instance/version**, không chỉ subject name.

## 5. TLS certificate verification: client thực sự kiểm tra gì?

### 5.1. Các bước mang tính khái niệm

Một TLS client được cấu hình đúng thường cần:

1. Nhận certificate chain của server và **xây đường tin cậy** tới trust anchor được chấp nhận.
2. Xác minh chữ ký/constraints/validity và các quy tắc path validation liên quan.
3. Xác minh **tên endpoint** tương ứng với định danh trong certificate.
4. Kiểm tra certificate phù hợp **công dụng server TLS** và chính sách thuật toán.
5. Xử lý **trạng thái thu hồi** theo khả năng, yêu cầu và cơ chế client thực tế.
6. Xác minh proof of possession/handshake, các thuật toán phiên và policy TLS phù hợp.
7. Chỉ khi xác thực bên kia thành công mới tin kênh giao tiếp, đồng thời vẫn thực hiện **application authorization**.

Đây là mô hình tổng quát. Chi tiết thay đổi giữa TLS versions, client libraries và policy. Quan trọng là **không tự viết một phép so sánh issuer đơn giản rồi coi bằng path validation**.

### 5.2. Một số chống mẫu nguy hiểm

- Bỏ kiểm tra chain/hostname khi certificate tự ký làm môi trường thử nghiệm lỗi.
- Dùng trust-all verifier trong Java hoặc HTTP client cho cả production.
- Cho phép một certificate sai tên vì “được ký bởi CA đúng”.
- Chấp nhận certificate hết hạn để “giữ dịch vụ sống” mà không đánh giá rủi ro/biện pháp hạn chế.
- Trust tất cả certificates do client gửi, không giới hạn CA và mapping identity cho mTLS.
- Gắn private key vào image hoặc repository vì triển khai thủ công cho tiện.
- Không kiểm tra certificate thực tại **ingress/proxy/sidecar**, chỉ xem file trong hệ thống cấp phát.

**Không nên giải quyết lỗi TLS bằng việc tắt certificate validation.** Cần xác minh nguyên nhân: tên, chain, trust store, đồng hồ, đường mạng, SNI, certificate purpose hoặc cấu hình sai.

### 5.3. Chứng thư hợp lệ không bằng hệ thống được cấp quyền

Khi ứng dụng gọi dịch vụ analytics vendor, chứng thư TLS đúng chỉ hỗ trợ việc client giao tiếp với endpoint có danh tính tương ứng trong mô hình tin cậy. Nó **không chứng minh** việc chuyển dữ liệu học viên qua endpoint đó được data owner, privacy policy hoặc hợp đồng cho phép. Mã hóa và xác thực đường truyền là **một control trong chuỗi**.

## 6. Các loại certificate và ranh giới áp dụng

| Loại | Dùng để | Owner/risk nổi bật | Evidence điển hình |
|---|---|---|---|
| **Public TLS server** | Xác thực endpoint công khai qua HTTPS | Domain owner, ingress/platform; hết hạn và sai SAN | Certificate runtime, chain/name tests, inventory |
| **Private/internal TLS server** | Xác thực endpoint nội bộ | Private CA trust và service identity governance | Internal CA policy, runtime trust-store tests |
| **mTLS client certificate** | Chứng minh danh tính client/workload trong TLS | Workload owner, mapping và revoke | Cert issuance, SAN/EKU, authz and negative tests |
| **Service-mesh workload identity** | Danh tính service trong mesh khi dùng certificate | Workload scope, control plane, sidecar, policy | Mesh config, actual peer auth, rotation logs |
| **Device certificate** | Định danh thiết bị trong phạm vi hệ thống | Device onboarding, reissue, loss/decommission | Device inventory, enrollment/revoke evidence |
| **Code signing certificate** | Chữ ký artifact/mã theo policy | Signer key custody, build provenance và verifier | Signed artifact, verification, signer lifecycle |
| **Document/email signing certificate** | Chữ ký tài liệu hoặc thông điệp theo mục đích | Danh tính người ký, keys, verification | Signature validation, certificate policy |
| **CA/intermediate certificate** | Cấp chứng thư thuộc phạm vi ủy quyền | Key custody, constraints, audit và compromise impact | CA audit, profile, key control, trust review |
| **Certificate trong môi trường thử nghiệm** | Kiểm thử TLS và luồng phát hành nội bộ | Tách biệt production/test trust | Scope/config, negative trust tests |

Vì các use cases khác nhau, **một danh sách “certificate hết hạn” không phải toàn bộ chương trình assurance**. Cần kiểm soát issuer, identity, key use, trust, deployment và revoke cho từng nhóm.

## 7. Các risk scenarios trọng yếu

| Risk ID | Kịch bản | Hậu quả có thể | Biện pháp thường cần |
|---|---|---|---|
| CERT-R01 | Certificate endpoint production hết hạn mà không đổi kịp | Gián đoạn TLS, giảm availability | Inventory, expiry monitoring, automated renewal/reload |
| CERT-R02 | Server triển khai certificate sai tên/SAN | Client không xác minh được endpoint hoặc có người bỏ validation | SAN testing, deployment gate |
| CERT-R03 | Chain thiếu intermediate hoặc dùng trust anchor chưa được cài | Một số clients không xây được chain, sự cố không đồng nhất | Chain tests theo client population |
| CERT-R04 | Private key server/workload bị sao chép trái phép | Khả năng giả mạo endpoint/chủ thể trong phạm vi sử dụng | Protected key custody, revoke/reissue, incident response |
| CERT-R05 | CA cấp nhầm certificate cho danh tính khác | Giả mạo đối tượng bị ảnh hưởng | Identity/domain control validation, issuance governance |
| CERT-R06 | Client tự tắt hostname/chain verification | Chấp nhận bên kia không đáng tin, tăng nguy cơ trung gian | Safe TLS defaults, negative tests, code/config review |
| CERT-R07 | Trust store chứa CA không được phê duyệt | Mở rộng ngoài ý muốn nguồn có thể chứng thực | Trust anchor inventory, change approval |
| CERT-R08 | CA root/intermediate bị xâm phạm hoặc phải thay | Ảnh hưởng lớn tới chuỗi tin cậy/phát hành | Protected CA keys, rollover/recovery planning |
| CERT-R09 | Renew thành công ở CA nhưng pod/edge chưa reload | Certificate runtime hết hạn dù dashboard báo OK | Runtime probes, rollout/reload checks |
| CERT-R10 | mTLS certificate hợp lệ nhưng mapping identity quá rộng | Service ngoài nhiệm vụ được gọi API nhạy cảm | Authorization policy, SAN/SPIFFE mapping tests |
| CERT-R11 | Certificate bị thu hồi nhưng peer không kiểm tra khi policy yêu cầu | Đường giả mạo/ủy quyền cũ có thể tiếp tục | Revocation design, actual client behavior tests |
| CERT-R12 | Certificate/key dùng lại quá rộng nhiều môi trường | Một key lộ ảnh hưởng nhiều service/tenants | Key isolation, issuance profiles và scoped keys |
| CERT-R13 | ACME/issuance automation bị chiếm hoặc DNS challenge sai quyền | Phát hành certificate trái phép, thao túng domain validation | Credential controls, DNS/IAM review, CT monitoring |
| CERT-R14 | Cert inventory bỏ sót server cũ, sidecar hoặc API vendor | Hết hạn hoặc trust drift không được phát hiện | Discovery + reconciliation |
| CERT-R15 | Certificate hết hạn ở pipeline ký artifact | Ngưng phát hành hoặc sai verification policy | Signer lifecycle, build/release tests |

Mức rủi ro phải đánh giá theo **asset, impact, likelihood, hiện trạng control, phạm vi và evidence**, không mặc định mọi certificate hết hạn đều cùng mức nghiêm trọng. Ví dụ lỗi endpoint công khai có thể gây gián đoạn học vụ; lỗi mTLS client certificate có thể làm hệ thống export bất hoạt; CA key compromise có thể ảnh hưởng toàn bộ chuỗi của nhiều dịch vụ.

## 8. Vòng đời certificate từ đầu tới cuối

~~~mermaid
flowchart TD
    A["Nhận diện nhu cầu + identity + service owner"] --> B["Policy/CA profile + approval"]
    B --> C["Key generation + CSR/enrollment"]
    C --> D["Identity validation + issuance"]
    D --> E["Deploy certificate + key + chain"]
    E --> F["Runtime verification + evidence"]
    F --> G["Monitoring expiry, trust, status, inventory"]
    G --> H{"Sự kiện nào?"}
    H -->|"Gần hết hạn"| I["Renew/reissue + rollout/reload + retest"]
    H -->|"Lộ key / sai issuance"| J["Contain, revoke, reissue, investigate"]
    H -->|"Ngừng service"| K["Retire cert/key, remove trust/access"]
    I --> F
    J --> F
    K --> L["Archive records theo policy + cập nhật inventory"]
~~~

Vòng đời thực tế không nhất thiết tuyến tính. Một leaf cert có thể được **reissue vì SAN thay đổi** trước khi hết hạn; một CA có thể cần rollover; một credential có thể bị thu hồi do key compromise; một service có thể dùng certificate ngắn hạn được cấp tự động nhiều lần trong ngày.

### 8.1. Phân biệt các hành động

- **Renewal:** nhận certificate mới khi sắp hết hạn; key có thể được giữ hoặc thay tùy policy/profile.
- **Rekey/key rotation:** tạo/thay key pair, đòi hỏi cập nhật certificate và những quan hệ dùng khóa.
- **Reissue:** cấp certificate mới vì thay danh tính, SAN, issuer, policy hoặc sự cố.
- **Revocation:** đánh dấu certificate không còn được tin trước khi hết hạn theo cơ chế PKI; mức hiệu quả phụ thuộc client/usage.
- **Retirement:** đưa cert/key/service ra khỏi vận hành; xử lý trust, logs và dữ liệu liên quan.
- **CA rollover:** thay signing chain/trust anchor với kế hoạch tương thích và kiểm thử.
- **Reload:** bảo đảm thành phần thực tế sử dụng cert/key/chain mới thay vì tiếp tục giữ bản cũ trong memory.

**Renewed trong hệ thống CA không đồng nghĩa deployed, và deployed không đồng nghĩa toàn bộ clients đã tin đúng.**

## 9. Phân công trách nhiệm và quyền phê duyệt

| Vai trò | Trách nhiệm chính |
|---|---|
| **Service/application owner** | Xác định endpoint, dữ liệu/risk, domain/identity, yêu cầu availability, dependency và owner certificate |
| **PKI/CA team** | Certificate profiles, issuance/revocation services, CA security, trust governance trong phạm vi |
| **Platform/Cloud/SRE** | Key/secret storage, ingress/sidecar/keystore deployment, renew/reload, monitoring và rollback |
| **Application/Java team** | TLS/mTLS client behavior, hostname validation, authz, trust configuration và regression tests |
| **Identity/workload owner** | Chứng minh quyền được cấp tên/service identity, lifecycle khi đổi/thu hồi |
| **Security/GRC/Assurance** | Baseline, evidence contract, kiểm tra control, findings, reporting |
| **Incident response** | Điều tra key compromise, misissuance, containment, escalation |
| **Vendor/procurement owner** | Điều kiện chứng thư/trust với bên thứ ba và báo thay đổi |
| **Risk owner** | Quyết định xử lý residual risk trong thẩm quyền |
| **Independent assessor/auditor** | Đánh giá evidence theo scope, method và mức độc lập được giao |

### 9.1. Phân biệt accountability

Một tên service owner trong certificate inventory giúp liên hệ khi certificate sắp hết hạn, nhưng **owner kỹ thuật** mới vận hành renewal, **CA owner** vận hành issuance policy và **risk owner** quyết định những ngoại lệ có tác động lớn. Một team có thể kiêm vai trò trong tổ chức nhỏ, song phải giữ rõ **ai phê duyệt, ai thực hiện, ai kiểm chứng**.

### 9.2. RACI mẫu

R = Responsible, A = Accountable, C = Consulted, I = Informed.

| Hoạt động | Service owner | PKI/CA | Platform | App team | Assurance | Risk owner |
|---|---|---|---|---|---|---|
| Xác định identity, SAN và criticality | A/R | C | C | C | C | I |
| Phê duyệt profile và CA trust | C | A/R | C | C | C | I |
| Tạo/bảo vệ workload key | C | C | A/R tùy thiết kế | R khi tự quản lý | C | I |
| Cấp và revoke certificate | C | A/R | R automation | C | I | I |
| Triển khai/reload/rollback | I | C | A/R | R kiểm tra ứng dụng | C | I |
| Kiểm thử endpoint/mTLS | C | C | R | A/R theo scope | C | I |
| Thu thập và review evidence | C | R | R | R | A/R hoặc assessor | I |
| Chấp nhận residual risk | C | C | C | C | C | A/R |

Bảng chỉ là ví dụ tổ chức. Khi nhiều người tham gia thực thi, cần **một accountable owner thật** cho từng service/control và điều kiện escalation rõ.

## 10. Certificate inventory: biết có những gì để quản lý

### 10.1. Vì sao inventory quan trọng?

Một tổ chức có thể có:

- Certificates ở public load balancers/ingress.
- Certificates trên máy chủ reverse proxy hoặc Java application server.
- mTLS leaf certs trong sidecars, containers hoặc service mesh.
- Chứng thư VPN, thiết bị, agent, CI/CD, API gateway.
- Certificates của database, message broker, search/monitoring.
- Private root/intermediate CAs và trust bundles.
- Code-signing certificates và khóa ký release.
- Chứng thư của vendor endpoints mà ứng dụng dựa vào.
- Legacy certificates vẫn còn trong image/keystore hoặc job batch.

Nếu chỉ kiểm kê những certificate mua từ một CA công khai, nhiều certificates nội bộ có thể bị bỏ sót.

### 10.2. Trường của inventory record

| Trường | Mục đích |
|---|---|
| **Certificate/asset ID** | ID nội bộ ổn định; phân biệt service với certificate instance |
| **Fingerprint, issuer, serial** | Nhận diện certificate đang sử dụng |
| **Subject, SAN, EKU, KU** | Xác định danh tính và công dụng |
| **Validity and renewal horizon** | Theo dõi trước khi hết hạn |
| **Key algorithm/properties** | Đối chiếu baseline/key custody, không lưu private key |
| **CA/profile/trust anchor** | Nguồn phát hành và policy tin cậy |
| **Environment and endpoint** | URL/host/port/service/workload/cloud account/region |
| **Deployment location** | Ingress, JVM keystore, sidecar, HSM hoặc secret reference |
| **Service, technical, risk owners** | Quyền quyết định và vận hành |
| **Automation/renewal mechanism** | ACME, managed service, internal issuer hoặc manual |
| **Dependencies/client population** | Những clients cần tin certificate/CA |
| **Certificate state** | Requested, issued, deployed, expiring, revoked, retired… |
| **Last runtime verification** | Kết quả test thực tế, scope, time, tool |
| **Alert and escalation route** | Khi renew fail/expiry/compromise ai xử lý? |
| **Linked evidence/findings** | Truy vết kết luận, remediation và ngoại lệ |

Không đặt private key, password hoặc recovery secret vào inventory. Nếu ghi secret reference, quyền truy cập tới secret store phải được quản lý theo vai trò.

### 10.3. Inventory có thể mồ côi

Một certificate vẫn còn trong ingress cũ nhưng owner/team đã giải thể là rủi ro vì không ai nhận alert hoặc thay khóa. Các bước xử lý:

1. Xác minh endpoint và luồng sử dụng thực, không chỉ nhìn tên CN.
2. Xác định service và data criticality, các client phụ thuộc.
3. Giao interim owner và giới hạn exposure nếu cần.
4. Xác định CA/renewal mechanism và thời gian còn lại.
5. Đánh giá quyền private key, trust store và sử dụng certificate.
6. Chọn khôi phục ownership hoặc retirement có kiểm soát.
7. Ghi evidence cho việc gỡ bỏ/thu hồi và kiểm tra không ảnh hưởng service khác.

### 10.4. Discovery và reconciliation

Có thể kết hợp:

- Export từ public/private CA và certificate manager.
- Cloud/ingress, Kubernetes secret/cert manager, load balancer inventories.
- JVM keystore và các secret/certificate references có kiểm soát.
- TLS scanning đối với **endpoint do tổ chức quản lý và được phép kiểm tra**.
- Service registry/CMDB và deployment inventory.
- Code-signing/key management records.
- Kết quả thực tế từ app client, synthetic probes và logs.

**Không một nguồn duy nhất chắc chắn đầy đủ.** Chương trình assurance phải đối chiếu CA-issued inventory với những certs thực sự deployed, cũng như những endpoints thực có với service registry.

## 11. Nguồn phát hành, certificate profiles và chính sách

### 11.1. Lựa chọn CA phù hợp mục đích

Một service công khai thường cần certificate phù hợp với trust ecosystem của client; một workload nội bộ có thể dùng private CA hoặc identity issuer được tổ chức quản lý. Không nên buộc mọi service dùng **cùng một CA** hoặc cùng profile chỉ vì dễ vận hành.

Cần đánh giá:

- Client population tin CA nào?
- Identity/domain validation được thực hiện ở mức nào?
- Có yêu cầu giới hạn SAN, EKU, key algorithm, validity, issuance authority không?
- Private key được tạo/bảo vệ ở đâu?
- Cơ chế renew/revoke/reissue có thể tự động và đo được không?
- CA compromise hoặc CA downtime ảnh hưởng hệ thống ra sao?
- Có yêu cầu pháp lý/hợp đồng về loại chứng thư hoặc nhà cung cấp không?
- Rollover CA và phân phối trust bundles được thiết kế thế nào?

### 11.2. Certificate profile

Một **certificate profile** mô tả những thuộc tính và ràng buộc được phép cho một nhóm certificates, ví dụ:

- Loại identity: public DNS server, internal service, client identity, code signing.
- Nguồn và cách xác minh danh tính trước phát hành.
- Allowed subjects/SAN patterns, namespaces, tenants và ownership.
- Key algorithms/key sizes/curves và cách lưu private key được duyệt.
- EKU/KU, basic constraints, CA vs leaf và validity policy.
- Policy về renew/reissue/key rotation/revoke.
- Cơ chế approval, audit, rate/abuse control và separation of duties.
- Mức giám sát/phản ứng với misissuance.

Không nên đặt một thời hạn/thuật toán như quy tắc vĩnh viễn cho mọi môi trường. Yêu cầu có thể thay đổi theo **client compatibility, baseline, CA rules và nghĩa vụ áp dụng**. Hồ sơ vận hành phải ghi phiên bản profile được phê duyệt.

## 12. Enrollment, CSR và certificate issuance

### 12.1. Ai được yêu cầu cấp chứng thư?

Một yêu cầu cấp certificate phải có **service/identity owner** và quy trình kiểm chứng quyền đối với danh tính cần chứng thực. Với DNS của một endpoint công khai, bên phát hành phải xác minh quyền kiểm soát domain theo policy và các yêu cầu áp dụng; với private PKI, tổ chức phải xác minh quyền yêu cầu identity/namespace.

Các điều kiện **không đủ**:

- Client tự điền tên service vào CSR nên mặc định được cấp.
- Người có quyền DNS tạm thời được coi là chủ của mọi domain vĩnh viễn.
- CI/CD runner có thể yêu cầu bất kỳ SAN nào trong công ty.
- CA chỉ kiểm tra CSR được ký, không kiểm tra requester có quyền với danh tính.
- Cấp certificate theo tin nhắn thiếu approval/evidence theo policy.

CSR có thể chứng minh quyền kiểm soát private key tương ứng nhưng **không tự chứng minh quyền sở hữu domain, service hoặc danh tính nghiệp vụ**.

### 12.2. Luồng issuance

1. **Request:** service ID, subject, SAN, purpose, environment, owner và hạn cần thiết.
2. **Policy/profile:** quyết định CA, thuật toán, công dụng, validity và yêu cầu bảo vệ khóa.
3. **Identity validation:** xác thực quyền yêu cầu name/namespace hoặc domain.
4. **Key generation:** tạo private key tại cơ chế được phê duyệt, kiểm soát export.
5. **CSR/enrollment:** gửi public key và thông tin yêu cầu tới issuer.
6. **Approval/issuance:** CA áp dụng policy, ký certificate và ghi audit.
7. **Distribution:** certificate/chain đến nơi dùng; private key không chuyển qua ticket hoặc kênh trái policy.
8. **Deployment/reload:** ứng dụng/ingress nạp đúng key, leaf cert và chain.
9. **Verification:** kiểm tra served certificate, trust chain, identity, purpose và client behavior.
10. **Record:** lưu issuer, serial, fingerprint, owner, approval, evidence và kỳ review.

### 12.3. Phép kiểm thử issuance

- Request SAN nằm **ngoài namespace được phép** phải bị từ chối.
- Requester không có quyền không được yêu cầu certificate cho service của nhóm khác.
- Certificate thực tế phải có SAN, KU/EKU, validity, issuer theo profile.
- Private key được tạo/bảo vệ theo approved key custody.
- Certificate mới chỉ ở trạng thái Issued không được coi là Deployed/Loaded.
- Issuance và reissue có dấu vết, owner và khả năng đối chiếu.
- Misissuance phải có đường containment, revoke/reissue và incident handling.

**Claim có thể kiểm chứng:** chỉ những yêu cầu được phê duyệt mới được cấp danh tính thuộc namespace X trong kỳ Y. Cần xem **population issuance events**, approval records và negative tests, không chỉ một CSR mẫu hợp lệ.

## 13. Bảo vệ private key và key custody

### 13.1. Private key là tài sản mật mã trọng yếu

Một certificate có chain hợp lệ vẫn có thể bị lạm dụng nếu private key bị sao chép. Kiểm soát thường cần:

- Key generation với thư viện, thuật toán và nguồn ngẫu nhiên phù hợp baseline.
- Quyền dùng private key giới hạn vào workload/owner đúng scope.
- Không hardcode private key/keystore passwords trong repository, image, logs, ticket.
- Giới hạn quyền file, secret store, backup, dump và công cụ quản trị.
- HSM/managed key service hoặc non-exportable keys khi phù hợp tác động.
- Tách các quyền tạo, phê duyệt, phân phối, dùng, thu hồi và review theo risk.
- Quy tắc key reuse, rotation, mất khóa, compromise và decommission.
- Kế hoạch phục hồi dịch vụ khi key mất nhưng không sao chép key tùy tiện.
- Audit logging cho thao tác nhạy cảm và xử lý khi key bị nghi lộ.

### 13.2. Không nhầm public certificates với private keys

| Artifact | Tính nhạy cảm | Kiểm soát |
|---|---|---|
| Public leaf certificate | Thông thường công khai; có thể lộ metadata service | Integrity, correct chain/identity |
| Root/intermediate certificate | Public trong nhiều mô hình | Quyền **tin** phải được phê duyệt |
| CSR | Thường chứa public key và thông tin yêu cầu, không chứa private key | Identity validation và bảo vệ metadata phù hợp |
| Private key | Bí mật | Key custody, access limits, rotation và incident response |
| Keystore chứa private key | Bí mật dù file chứa cả certificate công khai | Bảo vệ file/password và runtime |
| Trust store | Thường chứa public certs | Bảo vệ integrity và quyền thay anchors |
| HSM credential/PIN/keystore password | Bí mật | Secret management, access/audit |
| Certificate fingerprint | Định danh public | Dùng đối chiếu; không thay TLS validation |

**Đuôi file không chứng minh nội dung**: PEM có thể chứa cả private key, PKCS#12 thường có thể đóng gói key và certificates. Đừng tự đưa bất kỳ PEM bundle nào lên hệ thống quản lý ticket mà chưa kiểm tra thành phần nhạy cảm.

### 13.3. HSM không làm mất trách nhiệm assurance

HSM hoặc managed key service có thể giới hạn khả năng export key và hỗ trợ audit. Nhưng vẫn phải kiểm tra:

- Ai có quyền yêu cầu **ký** hoặc **phát hành** cho danh tính?
- Key có thể bị sử dụng cho purpose trái policy không?
- Có phân tách người đề nghị/duyệt/thực hiện quyền lớn không?
- Quyền truy cập HSM có được review và giám sát không?
- HSM unavailable/compromised thì issuance và recovery ra sao?
- Backup/replication có tăng blast radius không?
- Evidence từ provider có bao phủ **scope, kỳ, loại khóa và operation** cần kết luận không?

Một câu “key nằm trong HSM” chỉ hỗ trợ **một phần** control claim.

### 13.4. Key reuse và blast radius

Khi cùng một private key/certificate được dùng trên nhiều service, mất quyền kiểm soát tại một endpoint có thể ảnh hưởng các endpoint khác. Dùng SAN certificate chung hay centralized key distribution có thể có lý do vận hành, nhưng phải cân đối **blast radius, quyền phân phối, compatibility, key rotation và khả năng khoanh vùng**. Không mặc định một phương án luôn đúng cho mọi hệ thống.

## 14. Trust stores, keystores và ứng dụng Java

### 14.1. TLS có thể kết thúc ở nhiều nơi

Trong hệ thống Java:

- Reverse proxy/load balancer có thể terminate TLS trước Java backend.
- Java server có thể tự terminate TLS qua keystore/SSL configuration.
- Java outbound HTTP client cần trust anchors để xác minh remote server.
- mTLS có thể yêu cầu identity certificate/private key và trust store của peer.
- Sidecar/service mesh có thể quản lý mTLS ngoài tiến trình JVM.
- JDK/runtime version, framework và native proxy có thể dùng trust settings khác nhau.
- Thay file keystore trên disk **chưa chắc** JVM/proxy đang nạp certificate mới.

Muốn đánh giá chính xác phải xác định **TLS endpoint thực**, cấu hình runtime và client population, không chỉ một đường dẫn file config.

### 14.2. JKS, PKCS#12 và managed secrets

**JKS** là định dạng keystore đặc thù Java; **PKCS#12** là định dạng container có thể mang private keys và certificates. Khả năng mặc định, mật mã và compatibility phụ thuộc phiên bản Java/tool. Nên chọn theo policy và yêu cầu tương tác, không dựa vào một nhận định “JKS luôn tốt hơn” hoặc “PKCS#12 tự bảo mật hơn”.

Trong cloud, key có thể do secret manager, KMS/HSM hoặc proxy giữ. Khi đó việc review một JVM keystore không nhất thiết bao phủ server TLS đang hoạt động.

### 14.3. Trust store change là thay đổi bảo mật

Khi Java HTTP client báo certificate error, không nên thêm tùy tiện một CA vào trust store chỉ để tránh lỗi. Cần:

1. Xác minh issuer, chain, SAN, SNI, đồng hồ và trust anchor kỳ vọng.
2. Phân biệt server gửi chain không đầy đủ với client thiếu CA hợp lệ.
3. Xác nhận quyền và approval trước khi thêm trust anchor.
4. Đánh giá phạm vi ảnh hưởng tới mọi kết nối dùng trust store.
5. Test kết nối hợp lệ **và negative tests** với chain/tên sai.
6. Lưu config/version/build/deployment evidence và rollback plan.

**Không dùng trust-all verifier hoặc bỏ hostname verification trong production.** Ngoại lệ test phải được cô lập và kiểm tra không lan sang release.

## 15. Renewal, rotation và rollout không gián đoạn

### 15.1. Expiry phải được nhìn từ client thực

CA manager báo chứng thư đã Renewed không chứng minh endpoint đang phục vụ bản mới. Một load balancer, pod, JVM hoặc sidecar có thể vẫn giữ certificate cũ trong memory.

Cần phân biệt:

| Trạng thái | Ý nghĩa | Evidence |
|---|---|---|
| **Issued** | CA đã cấp certificate | Issuance record, serial/fingerprint |
| **Available** | Cert/chain và key material sẵn sàng theo policy | Secret reference/version |
| **Deployed** | Deployment/config đã được cập nhật | Change/release event |
| **Loaded/served** | Runtime thật đang dùng certificate mong muốn | TLS handshake/fingerprint probe |
| **Trusted by clients** | Client population trọng yếu xác minh thành công | Client tests, handshake telemetry |
| **Old version retired** | Certificate/key cũ không còn sử dụng trái policy | Scan, secret cleanup, revoke khi cần |
| **Renewal mechanism healthy** | Job có thể tiếp tục cấp/rollout | Health and failure alert evidence |

### 15.2. Renewal không tự bằng key rotation

**Renewal** tạo certificate mới, có thể với key pair cũ hoặc mới theo profile. **Rekey** mới thay private/public key pair. **Reissue** có thể do SAN, issuer, profile, compromise hoặc identity thay đổi. Phải ghi từng operation chính xác, không suy ra đã rotate key chỉ từ số serial mới.

### 15.3. Quy trình rollout gợi ý

1. Inventory endpoints, owners và nhóm clients phụ thuộc.
2. Cấp cert mới theo profile, xác minh ownership và key custody.
3. Deploy tới một phần hệ thống/canary nếu kiến trúc cho phép.
4. Xác minh **served cert**, chain, SAN, TLS version/policy và mTLS nếu có.
5. Test clients quan trọng, kể cả Java runtime khác nhau trong scope.
6. Rollout tiếp, theo dõi handshake failures, traffic, errors.
7. Xác nhận mọi instance/pod/region dùng bản mới.
8. Retire bản cũ, revoke nếu cần, xử lý secrets theo policy.
9. Cập nhật inventory, evidence và đánh giá residual risk.

### 15.4. CA rollover và trust migration

Khi đổi CA/root, có thể phải phân phối **trust anchors mới tới clients trước**, kiểm tra một giai đoạn tương thích rồi chuyển leaf chain. Sau khi clients được xác minh tin chain mới, mới loại trust cũ theo kế hoạch.

Cần xét client embedded/legacy, JVM runtime cũ, private mesh, offline workloads và third-party clients. Không bỏ CA cũ đột ngột nếu chưa biết client dependencies; cũng không giữ một CA không còn đáng tin vô thời hạn.

## 16. Revocation và trạng thái chứng thư

### 16.1. Revocation không tự cưỡng chế ở mọi client

**Certificate revocation** có nghĩa issuer hoặc hệ thống tin cậy biểu thị certificate không nên được chấp nhận trước khi Not After, chẳng hạn do key compromise, sai danh tính hoặc kết thúc dịch vụ. Nhưng kết quả phụ thuộc **cách client kiểm tra certificate status**.

Một certificate xuất hiện trong CRL nhưng client không kiểm tra CRL/OCSP có thể vẫn được chấp nhận trong một số cấu hình. Vì vậy không thể lấy screenshot “Revoked” của CA làm bằng chứng mọi endpoint/client đã ngừng tin.

### 16.2. Cơ chế thường gặp

| Cơ chế | Ý nghĩa | Câu hỏi assurance |
|---|---|---|
| **CRL** | Danh sách các certificate đã thu hồi do issuer ký | Client có dùng, cập nhật cache và fail mode thế nào? |
| **OCSP** | Truy vấn trạng thái cert qua OCSP responder | Client có kiểm tra phản hồi, xử lý timeout? |
| **OCSP stapling** | Server chuyển status response trong handshake khi hỗ trợ | Client có dùng/verify, policy yêu cầu gì? |
| **Short-lived certificate** | Giới hạn thời gian certificate cũ còn hiệu lực | Automation/rekey/issuance có đáng tin không? |
| **Trust anchor removal** | Client không còn tin nguồn cấp phát cụ thể | Blast radius, rollback, compatibility? |
| **Identity/authorization revocation** | Hạn chế quyền service/actor trên ứng dụng | Certificate vẫn hợp lệ nhưng authz có chặn không? |

### 16.3. Soft fail và hard fail

- **Hard-fail:** từ chối kết nối nếu yêu cầu kiểm tra status không được đáp ứng.
- **Soft-fail:** có thể tiếp tục khi status service unreachable.
- **Không kiểm tra trực tuyến:** phụ thuộc validity, trust, identity hoặc cơ chế thay thế.

Mỗi cách có đánh đổi giữa availability và khả năng ngăn certificate bị thu hồi. **Không áp một quy tắc bất biến** cho mọi client. Phải xác định requirement theo risk, test hành vi thực và ghi limitations.

### 16.4. Khi key bị lộ

1. Xác định phạm vi key, certificate, endpoints và người có thể truy cập.
2. Bảo vệ evidence và thực hiện containment.
3. **Không renew bằng chính private key đã bị compromise**.
4. Tạo key mới từ nguồn đáng tin, cấp certificate mới.
5. Deploy/reload, kiểm tra chain/identity và các clients.
6. Revoke cert cũ và áp thêm biện pháp khi client không kiểm tra revocation.
7. Rotate credentials/permissions liên quan nếu có rủi ro lan rộng.
8. Đối chiếu logs, issuance events, hệ thống chia sẻ key.
9. Gỡ private key copies không hợp lệ, cập nhật inventory/incident/risk.
10. Retest đường sử dụng certificate cũ theo client policy.

## 17. Incident response cho key, CA và trust

### 17.1. Sự cố có thể gặp

- Private key/PKCS#12 bị commit vào repository hoặc gửi nhầm.
- Cert được cấp cho hostname không đúng owner.
- Intermediate CA signing key bị nghi xâm nhập.
- Trust store bị thêm CA ngoài phê duyệt.
- Client chấp nhận certificate bị thu hồi trái policy.
- Certificate hết hạn gây outage tại API, database hoặc worker.
- mTLS certificate hợp lệ được map thành quá nhiều quyền.
- Pipeline ký artifact có key signer bị lộ.

### 17.2. Quy trình xử lý và bằng chứng

**Triage → scope → containment → evidence preservation → impact assessment → revoke/reissue/rekey → deploy/trust changes → retest → post-incident review**.

Cần ghi issuer/serial/fingerprint, SAN, key references, service owners, environments, relevant logs, changes và clients impacted. Nếu key bị lộ, **không tự khẳng định đã xảy ra impersonation**, nhưng cũng không coi “không thấy traffic lạ” là bằng chứng an toàn khi telemetry không bao phủ mọi đường.

Trong những tình huống cần thông báo bên thứ ba hoặc tuân thủ nghĩa vụ, Security/IR, Legal, Privacy và risk owner phối hợp theo quy trình; không dùng bài học này để tự áp mốc pháp lý chung.

## 18. mTLS và workload identity

### 18.1. Mutual TLS thêm lớp xác thực nào?

Trong **mutual TLS (mTLS)**, server không chỉ đưa certificate để client kiểm tra; client cũng trình certificate và chứng minh quyền kiểm soát khóa riêng trong handshake theo cơ chế giao thức. Điều này hỗ trợ **xác thực hai chiều**.

Tuy nhiên cần phân biệt:

- **TLS identity validation:** certificate chain, validity, purpose và client/server identity được xác minh.
- **Workload binding:** certificate được cấp cho đúng service/namespace/identity đang chạy.
- **Application authorization:** service đó có được gọi endpoint, tenant, hành động cụ thể không?
- **Lifecycle:** service còn hiệu lực, certificate/key có thuộc profile hợp lệ không?
- **Monitoring/response:** log peer identity, denial, authz decision và sự kiện lạm dụng.

Một report-worker có certificate hợp lệ do private CA cấp **không tự có quyền tải toàn bộ điểm học viên**. mTLS xác thực peer; hệ thống vẫn cần giới hạn authorization theo data owner và policy.

### 18.2. Những câu hỏi assurance cho mTLS

| Lĩnh vực | Điều cần chứng minh |
|---|---|
| **CA trust** | Client/server chỉ tin issuer/trust anchors được phê duyệt theo thiết kế |
| **Client identity** | Certificate SAN/identity được map đúng workload |
| **Issuer authorization** | Chỉ workload được phép yêu cầu certificate cho identity đó |
| **Private key custody** | Key ở đúng workload, không bị chia sẻ trái policy |
| **Certificate purpose** | EKU/KU và chain đáp ứng vai trò server/client theo policy |
| **Effective authorization** | Peer không thể dùng cert hợp lệ để vượt tenant/function/object |
| **Endpoint coverage** | Không tồn tại đường plaintext hoặc cổng admin bypass control |
| **Rotation/revocation** | Sau đổi/thu hồi identity, quyền truy cập thay theo policy |
| **CA rollover** | Cả hai phía nhận đúng trust update và kiểm thử |
| **Audit** | Truy vết peer identity, API action và decisions có độ tin cậy |

### 18.3. Negative tests quan trọng

1. Client không có certificate khi endpoint yêu cầu mTLS bị từ chối.
2. Client có cert từ untrusted CA bị từ chối.
3. Client có cert đúng CA nhưng sai identity/namespace không vượt authentication/authorization boundary.
4. Cert hết hạn, sai EKU/identity hoặc sai chain được xử lý đúng.
5. Client hợp lệ nhưng không được quyền với learner/class/tenant khác bị từ chối.
6. Path admin/health/debug/internal port được kiểm tra theo chính sách, không bỏ bypass.
7. Khi trust CA được đổi, clients cũ/mới xử lý đúng trong rollout.
8. Revocation/failure mode phải được test trong những trường hợp threat model yêu cầu.
9. Không chỉ kiểm tra client cert; client vẫn phải xác minh server certificate.
10. Logs/evidence gắn từng test với certificate serial/fingerprint, service version và môi trường.

## 19. Service mesh, Kubernetes và certificate ngắn hạn

### 19.1. Workload certificate trong mesh

Trong một service mesh, control plane hoặc một authority có thể cấp certificate identity cho workload; sidecars/gateways xử lý TLS và thay cert tự động. Các rủi ro cần xét:

- Service account hoặc namespace bị gán sai identity.
- Policy mTLS chỉ áp dụng một phần đường vào/ra.
- Sidecar bypass cho phép kết nối không được kiểm tra.
- Issuer trust quá rộng hoặc client mapping không gắn đúng tenant.
- Rotation thất bại và nhiều pods hết hạn gần nhau.
- Workload đã retired nhưng còn secret/cert hoặc quyền ứng dụng.
- Control plane/CA bị lạm dụng để cấp certificate trái phép.

**Không thể chỉ nhìn cờ “mTLS enabled” để kết luận mọi luồng đã được mã hóa và xác thực.** Cần traffic inventory, sidecar/gateway config, runtime verification và kiểm tra các đường bypass.

### 19.2. Certificate ngắn hạn có đánh đổi

Một certificate ngắn hạn có thể giảm thời gian sử dụng key/cert cũ trong một số mô hình, nhưng yêu cầu **automation đáng tin** và không bảo vệ khỏi issuer bị chiếm hoặc authorization sai. Đặc biệt:

- Renew job có thể chết âm thầm.
- Chứng thư mới ở secret nhưng process không reload.
- Client trust store không cập nhật kịp khi CA đổi.
- Pod khởi động khi CA unavailable.
- Key dùng chung hoặc quyền service quá rộng vẫn tồn tại.
- Evidence pipeline không thu được trạng thái served cert.

Tần suất renew và thời gian hiệu lực cần theo profile/threat model, không có một số giờ/ngày mặc định cho mọi workload.

### 19.3. Kubernetes Secret không tự chứng minh bảo vệ key

Nếu private key nằm trong Kubernetes Secret, cần kiểm tra **RBAC, quyền đọc secret, encryption-at-rest ở nơi lưu khi áp dụng, namespace isolation, audit, secret rotation, người có quyền cluster và kiểm soát triển khai**. Tên đối tượng Secret không đủ để kết luận key không thể bị truy cập trái phép.

Nếu cert-manager hoặc issuer controller tự gia hạn, cần đối chiếu **issuance records → Secret version → ingress/sidecar reference → actual served certificate → client acceptance**.

## 20. ACME và automation cấp/gia hạn

### 20.1. ACME là gì?

**Automated Certificate Management Environment (ACME)** là giao thức hỗ trợ tự động hóa yêu cầu, xác minh quyền đối với tên/identity theo các challenge/flow được hỗ trợ và phát hành/gia hạn certificate. Với các use cases TLS công khai, một số challenge có thể dựa trên kiểm soát HTTP hoặc DNS tùy profile.

Automation giảm thao tác thủ công nhưng tạo những **quyền có khả năng yêu cầu danh tính** phải quản trị.

### 20.2. Rủi ro của issuance automation

| Risk | Dấu hiệu | Control |
|---|---|---|
| ACME credentials lộ | Actor không được phép có thể yêu cầu cấp certificate | Secret management, scoped permissions |
| DNS API quyền quá rộng | Controller sửa record không thuộc zone/namespace cần | Least privilege và owner review |
| Challenge sai cấu hình | Renew liên tục fail hoặc luồng xác minh không được bảo vệ | Challenge validation và health monitoring |
| Request SAN quá rộng | Dev cấp cert cho tên không thuộc service | Profile và namespace constraints |
| CAA/DNS drift | Chính sách CA/domain thay ngoài ý muốn | DNS change review, monitoring |
| Retry liên tục | Issuance churn, gián đoạn do rate/operational limits | Retry/backoff, test environment |
| Issued nhưng runtime cũ | Dashboard CA xanh nhưng endpoint hết hạn | Runtime probes và rollout verification |
| CA unavailable | Không cấp kịp certificate | Buffer, alert, recovery plan |
| Trust change không báo | Client không chấp nhận new chain | Client compatibility tests |
| Cert issuance bất thường | Có thể cấp cho domain ngoài approval | Issuance/CT monitoring và incident process |

**CAA (Certification Authority Authorization)** hỗ trợ giới hạn những CA được phép phát hành trong những bối cảnh DNS/public CA thích hợp. Nó không thay kiểm soát DNS credentials, owner approvals và kiểm chứng certificates đang được phát hành.

### 20.3. Tự động hóa không đồng nghĩa tự cấp mọi danh tính

Trong private PKI, nếu developer có thể dùng một API key để xin certificate mang tên bất kỳ production service nào, hệ thống đã trao quyền chứng thực identity quá rộng. Cần kiểm tra **requester entitlement, namespace restrictions, key custody và audit**.

## 21. Certificate Transparency và phát hành bất thường

**Certificate Transparency (CT)** tạo khả năng quan sát những certificates được đưa vào các public logs theo hệ sinh thái hỗ trợ. Giám sát CT cho domain có thể giúp phát hiện:

- Certificates mới nhưng không có request/approval trong inventory.
- Issuer/SAN không dự kiến.
- Cấp phát do DNS/ACME automation bị thay đổi.
- Certificates cho các subdomains mà service owner không nhận ra.

Tuy nhiên:

- CT không thay identity/domain control validation trước issuance.
- Một certificate trong CT chưa chứng minh endpoint sử dụng certificate đó.
- Không thấy trong CT không chứng minh private PKI hoặc mTLS certs không tồn tại.
- CT log entry không chứng minh private key được bảo vệ.
- Alert cần người điều tra theo issuer, serial, SAN, domain owner và issuance history.

Một CT monitor chỉ có ích khi có **monitoring owner, process triage, danh sách domain, false-positive handling, thời gian phản hồi theo risk và bằng chứng xử lý**.

## 22. Chứng thư ký mã, thiết bị và use cases khác

### 22.1. Code-signing certificate

Certificate ký mã hỗ trợ xác minh artifact được ký bởi **key/signing identity** được chấp nhận theo chính sách và chữ ký gắn với nội dung artifact. Nhưng nó **không tự chứng minh** source code an toàn, build reproducible hoặc pipeline không bị xâm nhập.

Các control cần đánh giá:

- Signer identity và cấp quyền ký.
- Private key custody, HSM/managed signer nếu phù hợp.
- Commit/build/artifact digest, approval và deployment provenance.
- Chữ ký có được verifier thật sự kiểm tra không?
- Key/cert được rotate, revoke, retired thế nào?
- Thời điểm ký và chính sách xác minh signatures lịch sử.
- Có thể ký artifact trái quy trình bằng cùng một key không?
- Audit log của signing operation và control với pipeline account.

### 22.2. Historical signatures

Với một số hệ thống ký mã/tài liệu, một chữ ký từ quá khứ có thể được xác minh bằng policy liên quan đến **thời điểm ký, trusted timestamp, chain/revocation status và tài liệu đi kèm**. Không mặc định chứng thư ký hết hạn ngày hôm nay làm mọi chữ ký được tạo hợp lệ trước đây tự trở thành vô giá trị.

Quy tắc xác minh lịch sử phụ thuộc mục đích và chính sách riêng, không nên áp cách kiểm tra thời gian hiện tại của HTTPS server một cách máy móc.

### 22.3. Device/client certificates

Một thiết bị bị mất hoặc nhân sự nghỉ việc có thể khiến client certificate **cần revoke/rekey hoặc thay quyền trên server**. Certificate còn hiệu lực mật mã không đồng nghĩa người dùng/thiết bị còn được phép truy cập. Phải đồng bộ **identity lifecycle, device registry, certificate inventory và authorization**.

## 23. Security assurance cho certificate management

### 23.1. Từ certificate inventory tới assurance

Một tổ chức có thể có danh sách 10.000 certificates, tỷ lệ hết hạn thấp và một service ACME tự gia hạn. Nhưng để chứng minh mục tiêu bảo mật, cần biết:

1. Certificate nào thuộc **production và tài sản trọng yếu**?
2. Những certificate nào **đang thực sự được phục vụ**?
3. Endpoint và client có **xác minh đúng danh tính, chain và purpose**?
4. Certificate được cấp bởi **đúng issuer** qua approval và identity proofing phù hợp?
5. Private keys có **được bảo vệ và quản lý vòng đời**?
6. Rotation/revocation có được **thực thi** theo phương pháp đã thiết kế?
7. Clients, proxy, JVM, devices và vendor connections nào chưa có evidence?
8. Khi có lỗi, finding và risk owner quyết định thế nào?

Inventory là **điểm khởi đầu của scope**, không phải bằng chứng mọi control đạt.

### 23.2. Control statements ví dụ

| Control ID | Objective | Control statement | Owner |
|---|---|---|---|
| CERT-CTRL-01 | Không có endpoint trọng yếu vô chủ | Tất cả TLS/mTLS services trong scope có certificate, identity, owner và expiry metadata | Platform + service owners |
| CERT-CTRL-02 | Không cấp certificate sai identity | Issuance tuân theo validated ownership, approved CA/profile và audit | PKI/CA |
| CERT-CTRL-03 | Bảo vệ key | Private key chỉ tạo/lưu/sử dụng trong cơ chế được phê duyệt và theo least privilege | PKI/Platform |
| CERT-CTRL-04 | Đúng danh tính peer | TLS client/server kiểm tra trust chain, SAN/purpose và policy không bị disable | App/Platform |
| CERT-CTRL-05 | Không gián đoạn vì expiry đã biết | Renew/reissue và runtime rollout trong khoảng thời gian theo policy | SRE/Platform |
| CERT-CTRL-06 | Giảm lạm dụng cert/key cũ | Revocation/rekey/identity retirement được thực hiện và test phù hợp | PKI/Identity |
| CERT-CTRL-07 | mTLS không vượt quyền nghiệp vụ | Peer identity mapping và authz scope được kiểm soát | App + service owner |
| CERT-CTRL-08 | Trust anchors được quản trị | Thêm/xóa CA và rollover có approval, test, evidence và rollback | PKI/Security |
| CERT-CTRL-09 | Giám sát và ứng phó | Certificate health/issuance anomalies, key compromise được phát hiện và xử lý | SecOps/Platform |
| CERT-CTRL-10 | Phát hành artifact đáng tin | Signer identity, key custody và verification có trace tới build | Release Engineering |

Đây là **control IDs nội bộ minh họa**, không phải mã lấy từ một standard bên ngoài.

### 23.3. Design, implementation, operating effectiveness

| Lớp | Câu hỏi | Bằng chứng | Không được kết luận thay |
|---|---|---|---|
| **Design** | Policy, CA topology, profile, trust boundary, rotation/revocation plan có đúng risk? | PKI design, threat model, certificate baseline, RACI | Chưa chứng minh runtime đã triển khai |
| **Implementation** | Certificate/key/chain/trust settings thật có đúng trên endpoint/client? | Runtime probes, config/keystore inspection, validation tests | Một snapshot không chứng minh hoạt động cả kỳ |
| **Operating** | Issuance, renewal, reload, monitoring, revocation và incident control hoạt động ổn định trong kỳ? | Job histories, rotation records, access reviews, alert tests, incident/retest | Không tự bao phủ những endpoints chưa inventoried |

Một policy “mọi certificate sẽ tự gia hạn trước expiry” chỉ mô tả **kỳ vọng**. Bằng chứng operating effectiveness phải cho thấy cơ chế **đã hoạt động**, hoặc chí ít có test health/negative cases đủ cơ sở cho claim được nêu.

## 24. Claim–Argument–Evidence (CAE) cho certificate assurance

### 24.1. Claim mẫu cho API production

> Trong phạm vi các endpoint HTTPS production của nền tảng học được liệt kê và kỳ đánh giá xác định, server certificates được cấp cho đúng danh tính và mục đích, đang được triển khai với chain/trust phù hợp, được giám sát và gia hạn theo chính sách; các sai lệch và phần chưa đủ bằng chứng được báo riêng.

### 24.2. Argument

1. Có một endpoint inventory đầy đủ dựa trên service registry và discovery đã được đối chiếu.
2. Certificate identity/SAN/issuer/profile gắn với owner và danh tính được phê duyệt.
3. Private keys được bảo vệ theo key custody baseline; có audit khi thao tác nhạy cảm.
4. Runtime endpoint phục vụ certificate/chain đúng; clients trọng yếu xác minh đúng.
5. Renewal/reissue tự động hoặc quy trình thủ công có alerts, owners và runbooks.
6. Sau rollout, old certificates/trust thay đổi được kiểm soát.
7. Khi compromise/revocation xảy ra, có test và khả năng phản ứng phù hợp.
8. Assessor đánh giá evidence, không dùng approval thay technical validation.

### 24.3. Evidence

- Service/domain/endpoint inventory và owners.
- CA issuance log, serial/fingerprint, identity validation/approval.
- Certificate profile, key custody/access review, secret references đã che nhạy cảm.
- TLS client/server runtime probes, SAN/chain/purpose validation results.
- Keystore/trust-store versions và deployment mapping.
- CI/CD/config changes, reload/renew job logs và alerts.
- CA rollover, revocation/rekey test reports và incident records.
- Exception/finding/remediation/retest history.
- Assessment report ghi **scope, period, clients, limitations và reviewer**.

### 24.4. Phạm vi kết luận phải chính xác

Nếu mới kiểm tra public ingress nhưng chưa kiểm tra database mTLS, không được viết “tất cả kết nối được xác thực bằng chứng thư hợp lệ”. Nếu CA manager cho thấy issued cert mới nhưng endpoint runtime vẫn chưa được probe, chưa đủ evidence cho claim **loaded/served**. Nếu không có log để kiểm tra renew trong cả kỳ, cần ghi giới hạn **operating evidence**, không suy từ một certificate hiện đang hợp lệ rằng automation đã ổn định suốt kỳ.

Một claim đúng phạm vi và có ghi ngoại lệ đáng tin hơn tuyên bố “certificate compliant 100%” không giải thích nguồn hay phương pháp.

## 25. Evidence standard cho certificate management

### 25.1. Evidence phải chứng minh đúng claim

| Thuộc tính | Câu hỏi cần đối chiếu | Ví dụ evidence chưa đủ |
|---|---|---|
| **Relevance** | Artifact chứng minh issuance, key custody, trust validation hay runtime expiry? | Bản PDF chính sách để khẳng định certificate đang loaded |
| **Scope** | Những endpoints, ports, regions, pods, JVMs, client groups nào đã kiểm tra? | Chỉ test một public domain, bỏ internal mTLS |
| **Completeness** | Inventory có public/private CA, mesh, clients, devices, signing keys? | CA export chỉ từ một issuer |
| **Freshness/period** | Bằng chứng đúng thời điểm/phiên bản và kỳ kết luận? | Screenshot certificate cũ trước deployment |
| **Provenance** | Tool, nguồn, người thu thập, hostname/SNI, timestamp, config có rõ? | File certificate không biết lấy từ endpoint nào |
| **Integrity** | Có thể phát hiện thay đổi nội dung, đối chiếu bản gốc? | Bản đã chỉnh sửa metadata không còn audit history |
| **Reliability** | Probe có thực hiện đúng chain/name/purpose và xử lý lỗi không? | Tool chỉ so Not After, không verify trust |
| **Representativeness** | Sample bao phủ nhóm clients và CA/algorithms quan trọng? | Test một JVM mới, bỏ client cũ đang dùng |
| **Repeatability** | Người khác có thể lặp cách thu và so expected/actual? | “SRE kiểm tra thấy ổn” thiếu phương pháp |
| **Confidentiality** | Evidence có làm lộ private key, password, secrets hoặc kiến trúc nhạy cảm? | Đính kèm cả PKCS#12 và password trong ticket |

### 25.2. Evidence metadata tối thiểu

Một record cần ghi:

1. **Evidence ID, claim/control/risk IDs**.
2. **Service, hostname, port, environment, region/pod/client** thuộc phạm vi.
3. **Certificate identity:** issuer, serial, fingerprint, SAN, EKU và validity metadata, không lưu key.
4. **Trust source:** CA/profile/trust anchor version.
5. **Kỳ và thời điểm:** event time, collection time, timezone, assessment period.
6. **Method/tool:** command/script, client/JDK/proxy version và expected behavior.
7. **Certificate deployment mapping:** secret version, config, commit, build, release.
8. **Expected và actual:** chain/name/purpose/expiry/revoke/handshake behavior.
9. **Owner và reviewer:** ai tạo evidence, ai kiểm tra và quyết định.
10. **Exclusions/limitations:** endpoints hoặc client populations chưa đánh giá.
11. **Linked findings/retest:** tình trạng lệch, remediation và kết luận lại.
12. **Data handling:** mức nhạy cảm, nơi lưu và retention của hồ sơ.

### 25.3. Mẫu certificate assurance record YAML

Mẫu chỉ chứa **giá trị giả định để học**, không phải kết quả kiểm chứng production.

~~~yaml
evidence_id: EVD-CERT-LEARNING-API-001
claim_id: CLAIM-CERT-PROD-01
control_ids:
  - CERT-CTRL-01
  - CERT-CTRL-04
  - CERT-CTRL-05
scope:
  service_id: "learning-api"
  environments: ["production"]
  endpoints:
    - "api.learning.example:443"
  clients:
    - "browser-population"
    - "approved-java-clients"
  exclusions:
    - "legacy-internal-batch-path-pending-assessment"
owners:
  business_service_owner: "Learning Platform Owner"
  technical_control_owner: "Platform SRE"
  certificate_issuer_owner: "Approved PKI or managed CA"
  evidence_reviewer: "Security Assurance"
expected:
  - "Certificate matches approved DNS identity"
  - "Chain and intended purpose validate for client population"
  - "Certificate is valid and served by actual TLS endpoint"
  - "Renewal/rotation can be completed before expiry by policy"
  - "Old certificate is retired according to rotation plan"
sources:
  - "Certificate inventory and CA issuance records"
  - "TLS runtime probe with SNI and hostname verification"
  - "Keystore/secret version and deployment mapping"
  - "Renewal job, alerts and rollback runbook"
  - "Negative chain/hostname trust tests"
  - "Revocation and incident records when relevant"
cert_identity:
  issuer: "Populate from actual approved certificate"
  serial: "Populate from actual approved certificate"
  sha256_fingerprint: "Populate from runtime evidence"
  san: ["api.learning.example"]
  key_reference: "Protected secret reference, no private key"
assessment:
  period: "Set real period when assessed"
  status: "Pending validation"
  assumptions:
    - "Client inventory reconciled with service registry"
  limitations:
    - "No claim for legacy path until tested"
triggers:
  - "Renew/reissue/rekey or CA rollover"
  - "Hostname, TLS config, client or trust-store change"
  - "Key exposure, misissuance or TLS incident"
~~~

Không được điền sẵn status “Pass” khi chưa kiểm tra. Chỉ vì certificate trong YAML có SAN đúng không có nghĩa endpoint đang phục vụ nó.

### 25.4. Không thu private key như bằng chứng audit

Assessor không nên yêu cầu đội kỹ thuật gửi private key/keystore password để “kiểm tra đúng key”. Có thể kiểm tra **certificate/key public correspondence bằng cơ chế phù hợp, cấu hình, key reference, access controls và test handshake** mà không lấy bản sao private key. Với HSM non-exportable, cần chọn kỹ thuật chứng minh quyền kiểm soát key qua operation/test và audit được phê duyệt.

## 26. Test matrix cho certificate assurance

| Test ID | Risk/control | Kiểm tra | Kỳ vọng |
|---|---|---|---|
| CERT-T01 | Certificate inventory | Đối chiếu service registry, endpoints và CA records | Mọi endpoint trọng yếu có owner/cert record hoặc gap |
| CERT-T02 | Runtime expiry | Kiểm tra cert thực ở host/SNI/port | Not Before/Not After đúng và chưa hết hạn theo policy |
| CERT-T03 | SAN/hostname | Kết nối với tên đúng và tên không phù hợp trong môi trường test | Đúng được tin, sai tên bị từ chối |
| CERT-T04 | Chain/trust anchor | Xác minh chain tới trust store đã duyệt | Không chấp nhận CA không được tin |
| CERT-T05 | Key usage/EKU | Đối chiếu certificate profile với server/client role | Không dùng cert sai purpose |
| CERT-T06 | Issuance authorization | Request SAN ngoài phạm vi đã duyệt | CA/issuer từ chối và audit |
| CERT-T07 | Key custody | Review quyền secret/HSM/keystore | Chỉ identities có thẩm quyền được dùng key |
| CERT-T08 | Renewal/reload | Diễn tập gia hạn và rollout | Endpoint thật dùng cert mới; clients thành công |
| CERT-T09 | Revocation behavior | Simulate cert revoked trong phạm vi test được phép | Client phản ứng theo chính sách cụ thể |
| CERT-T10 | mTLS missing cert | Gọi endpoint bắt buộc mTLS không có client cert | Từ chối ở TLS boundary |
| CERT-T11 | mTLS unauthorized identity | Dùng cert hợp lệ nhưng service ngoài quyền | Không vượt authorization |
| CERT-T12 | Session/connection lifetime | Kiểm tra kết nối lâu, cert thay giữa chừng | Hành vi phù hợp thiết kế reconnect/rotation |
| CERT-T13 | Trust-store change | Thử thay anchor theo approval/rollout | Trust đúng và wrong-CA test fail |
| CERT-T14 | CA rollover | Phân phối bundle mới, chuyển leaf chain | Client groups được hỗ trợ tiếp tục hợp lệ |
| CERT-T15 | Expiry alert | Synthetic near-expiry event và lỗi renewal | Alert tới owner, ticket/escalation hoạt động |
| CERT-T16 | Compromise response | Tabletop key leak/misissuance | Owner, rotate/revoke/retest được xác định và diễn tập |
| CERT-T17 | Code signing | Verify artifact signature và identity | Artifact trái signer policy không được chấp nhận |
| CERT-T18 | Device/service retirement | Retire identity/certificate | Quyền cũ mất hiệu lực theo policy |
| CERT-T19 | Private PKI audit | Review CA permissions, log, profile, key controls | Không có cấp phát sai/ngoài policy chưa xử lý |
| CERT-T20 | Legacy endpoint | Discovery scan đối chiếu owner/renewal | Endpoint chưa quản lý được tạo finding hoặc đưa scope rõ |
| CERT-T21 | Clock skew | Kiểm tra ranh giới validity trong test | Validation không bỏ qua hạn hoặc thời điểm |
| CERT-T22 | Runtime drift | So CA-issued cert với ingress/JVM/pod đang dùng | Mismatch được phát hiện, không báo pass giả |
| CERT-T23 | Monitoring health | Cố ý làm probe thất bại trong test | Monitoring báo mất quan sát, không báo 0 lỗi |
| CERT-T24 | Certificate/key misbinding | Nạp cert và key không khớp trong môi trường test | Deploy/handshake thất bại, có cảnh báo |
| CERT-T25 | Certificate purpose/identity | Client đúng CA nhưng khác endpoint identity | Hostname/peer mapping bị từ chối |

### 26.1. Positive và negative testing

**Positive tests** kiểm tra clients hợp lệ kết nối được đúng endpoint với chính sách cần thiết; chúng bảo vệ availability và đúng chức năng.

**Negative tests** cố gắng dùng chain không đáng tin, sai hostname, sai purpose, expired/revoked certificate, không có client cert, hoặc cert hợp lệ nhưng **không có application authorization**. Chỉ khi kết hợp hai chiều mới có cơ sở rằng policy không quá chặt gây outage hoặc quá rộng gây chấp nhận giả.

### 26.2. Kiểm tra fail mode

Mô hình bảo đảm cần hỏi:

- Certificate hết hạn hoặc sai danh tính có bị **từ chối**?
- Nếu CA/status server unreachable, client làm gì?
- Khi trust store thiếu intermediate/root, client có fallback không đúng không?
- Khi renewal job thất bại, có cảnh báo trước thời hạn có thể khắc phục không?
- Khi trust new CA chưa được rollout, có rollback an toàn không?
- Khi client cert hợp lệ nhưng role/service bị revoke, ứng dụng có **deny** không?

Test trong môi trường kiểm soát và được phép; không phá kết nối production của người dùng thật chỉ để diễn tập.

### 26.3. Sampling và coverage

Không có tỷ lệ cố định đủ cho mọi PKI. Với nhiều endpoints, có thể kết hợp **continuous runtime probes**, sampling cấu hình các nhóm tương đương, test canary và kiểm tra chuyên sâu trên services critical. Tuy nhiên không được suy rộng từ một load balancer đã test sang các JVM, native agents hoặc services khác nếu trust settings/versions không tương đương.

## 27. Công cụ và lệnh kiểm tra certificate

Các ví dụ dưới dùng **tên miền giả định, file giả định**. Chúng nhằm hỗ trợ inspection trong môi trường bạn sở hữu hoặc được phép kiểm tra, **không phải yêu cầu chạy thực tế trên hệ thống của người học**.

### 27.1. Đọc certificate public từ file bằng OpenSSL

~~~bash
openssl x509 -in server.crt -noout -subject -issuer -serial -dates
openssl x509 -in server.crt -noout -fingerprint -sha256
openssl x509 -in server.crt -noout -ext subjectAltName
openssl x509 -in server.crt -noout -ext keyUsage
openssl x509 -in server.crt -noout -ext extendedKeyUsage
~~~

Các tùy chọn phụ thuộc phiên bản OpenSSL và nội dung extension. Khi extension không tồn tại hoặc không in được, cần xem profile hoặc dùng công cụ phù hợp, không tự coi đó là lỗi ở mọi use case.

**Điều chứng minh được:** certificate bytes trong file có những trường nhất định. **Chưa chứng minh:** certificate đó đang được load ở production, private key được bảo vệ hoặc client thực tin chain.

### 27.2. Kiểm tra thời điểm hết hạn

~~~bash
# 2,592,000 giây tương đương 30 ngày minh họa.
# Exit code cho biết certificate còn hiệu lực sau khoảng này hay không.
openssl x509 -in server.crt -noout -checkend 2592000
~~~

Đây là **phép kiểm tra validity theo thời điểm**, không kiểm tra SAN, chain, usage, revocation hoặc endpoint đang sử dụng cert đó. Khoảng 30 ngày chỉ là **tham số ví dụ**, phải chọn threshold theo policy và khả năng khắc phục.

### 27.3. Xem certificate thực đang được phục vụ

~~~bash
# Thay hostname bằng endpoint thật thuộc phạm vi được phép kiểm tra.
openssl s_client \
  -connect api.learning.example:443 \
  -servername api.learning.example \
  -verify_hostname api.learning.example \
  -verify_return_error \
  -showcerts
~~~

Cần đối chiếu chain, served leaf, issuer, fingerprint và tên; kiểm tra trust theo store thật của client đang xét. Kết quả từ một máy chạy OpenSSL **không bảo đảm mọi browser/JVM/embedded client** có cùng trust behavior, và một handshake thành công không chứng minh application authorization.

### 27.4. Kiểm tra path validation bằng CA bundle được phê duyệt

~~~bash
openssl verify \
  -CAfile approved-root.pem \
  -untrusted approved-intermediates.pem \
  server.crt
~~~

Kết quả verify với bộ root/intermediate đã cho hỗ trợ claim **chain trust trong điều kiện tool sử dụng**. Không dùng như bằng chứng tự động cho hostname, revocation, full TLS handshake hoặc runtime endpoint. Tùy policy có thể cần các tùy chọn purpose/hostname và kiểm thử riêng.

### 27.5. Kiểm tra certificate/keystore bằng keytool

~~~bash
# Đọc certificate public.
keytool -printcert -file server.crt -v

# Xem entries trong PKCS#12 keystore do bạn có quyền quản lý.
# Công cụ có thể nhắc nhập mật khẩu tương tác.
keytool -list -v \
  -storetype PKCS12 \
  -keystore service-identity.p12
~~~

**Không thêm password thật vào command line, source code hoặc file log** để chạy ví dụ. Output có thể lộ metadata service, alias, path, thông tin organization; giới hạn nơi lưu báo cáo. Keytool listing không thay chứng minh runtime đang dùng đúng entry.

### 27.6. Java HTTPS client: ưu tiên validation mặc định

Ví dụ Java tiêu chuẩn minh họa dùng TLS client behavior mặc định, **không cài TrustManager chấp nhận mọi certificate**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class LearningApiHealthCheck {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.learning.example/health"))
                .GET()
                .build();

        // TLS certificate, chain và endpoint identity được
        // xử lý bởi HTTPS implementation và cấu hình trust.
        // Không thay bằng trust-all hoặc vô hiệu hostname check.
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status = " + response.statusCode());
    }
}
~~~

Đây là ví dụ **một HTTPS request**, chưa đầy đủ xử lý timeout, observability, application authorization hoặc business logic. Chính sách trust của chương trình phụ thuộc JDK, trust configuration và môi trường. Test runtime cần xác định cụ thể **JVM và endpoint version**.

### 27.7. Code parsing X.509 không phải path validation

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class CertificateMetadata {
    public static void main(String[] args) throws Exception {
        try (InputStream in = Files.newInputStream(
                Path.of("server.crt"))) {
            X509Certificate cert =
                (X509Certificate) CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(in);

            System.out.println("Subject: " +
                    cert.getSubjectX500Principal());
            System.out.println("Issuer: " +
                    cert.getIssuerX500Principal());
            System.out.println("Not after: " +
                    cert.getNotAfter());
            System.out.println("SAN: " +
                    cert.getSubjectAlternativeNames());
        }
    }
}
~~~

**Cảnh báo:** CertificateFactory **chỉ parse certificate** ở ví dụ này; nó không thiết lập trust anchor, không chạy PKIX path validation, không kiểm tra hostname hoặc revocation. Không dùng output này để đánh dấu endpoint “trusted”.

## 28. Case study: certificate lifecycle cho nền tảng học Java

### 28.1. Bối cảnh

Nền tảng học gồm:

- Public API HTTPS cho web và mobile.
- Java Learning API chạy sau ingress/load balancer.
- Java Report Worker xử lý job export.
- PostgreSQL/managed database có TLS.
- Một internal certificate issuer cung cấp workload identities.
- Partner analytics được gọi qua HTTPS.
- CI/CD ký release artifacts.
- Cloud secret manager và certificate automation.

Lãnh đạo hỏi: **“Làm sao chứng minh các kết nối và danh tính được quản lý bằng chứng thư đúng chính sách, không bị hết hạn bất ngờ, và một key bị lộ có thể xử lý được?”**

### 28.2. Data flow và trust boundaries

~~~mermaid
flowchart LR
    B["Browser / Mobile"] -->|"HTTPS server TLS"| I["Public Ingress"]
    I -->|"Internal TLS theo design"| A["Java Learning API"]
    A -->|"mTLS workload identity"| W["Export Worker"]
    A -->|"TLS"| D[("Database")]
    W -->|"Private storage / TLS"| O[("Export Objects")]
    A -->|"HTTPS"| V["Analytics Vendor"]
    P["Approved CA / PKI"] -->|"Issue / renew"| I
    P -->|"Issue / rotate"| A
    P -->|"Issue / rotate"| W
    M["Monitoring + evidence"] --> I
    M --> A
    M --> W
~~~

Sơ đồ là **một phương án kiến trúc minh họa**. Trong thực tế TLS có thể terminate ở nơi khác; phải xác minh runtime thay vì suy đoán từ sơ đồ.

### 28.3. Risk scenarios ưu tiên

| Risk | Đường gây hại | Impact |
|---|---|---|
| R-1: Public certificate expires | Ingress vẫn phục vụ leaf cũ dù CA renew | Web/mobile không kết nối được |
| R-2: Wrong SAN/chain | Java/mobile clients không tin endpoint mới | Outage hoặc nhóm kỹ thuật có xu hướng bỏ validation |
| R-3: Worker identity compromised | Private key mTLS bị lộ hoặc dùng chung | Service giả mạo worker, tăng rủi ro dữ liệu |
| R-4: mTLS mapped too broadly | Cert của một service hợp lệ gọi export ngoài scope | Truy cập dữ liệu ngoài quyền |
| R-5: Trust store drift | Java service thêm CA không được duyệt | Chấp nhận peer ngoài nguồn tin cậy |
| R-6: CA rollover fails | JVM cũ chưa có root mới | Internal service outage |
| R-7: Monitoring blind spot | Chỉ theo dõi CA dashboard, bỏ runtime | Không phát hiện cert vẫn hết hạn |
| R-8: Vendor changed chain | External HTTPS dependency thay certificate/issuer | Kết nối fail hoặc bị xử lý không an toàn |
| R-9: Signing key misuse | Pipeline hoặc signer account bị chiếm | Artifact có chữ ký nhưng không được phép phát hành |

### 28.4. Xây control map

| Control | Technical implementation | Evidence/test |
|---|---|---|
| Certificate inventory | Service registry, CA, cloud, mesh discovery | Inventory reconciliation, owner and criticality |
| Public TLS identity | Approved SAN/issuer/profile, ingress rollout | Runtime SNI/name/chain tests |
| Internal mTLS identity | Issuer namespace constraints, service mapping | Peer cert and unauthorized identity tests |
| Key custody | Secret/HSM/IAM policies, workload binding | Permissions review, key-handling tests |
| Rotation | ACME/issuer controller, reload mechanism | Job history, fingerprint diff, client test |
| Client trust | JVM/proxy truststore approval and rollout | Config version, wrong-CA/hostname tests |
| Authorization | Report-worker API permissions, tenant checks | Negative export tests, job/file side effects |
| Incident | Key compromise runbook and responders | Tabletop exercise, issue/revoke/retest record |
| Code signing | Signing service policy and release verification | Signed artifact, build provenance, verifier output |

### 28.5. Chuỗi hoạt động renewal

Giả sử public ingress certificate được xác định là sắp hết hạn:

1. Monitoring phát hiện theo **certificate thực được served**; ticket gắn service owner.
2. Renewal controller kiểm tra quyền domain và lấy certificate mới.
3. Certificate/key/chain được phân phối vào secret hoặc managed certificate resource đúng.
4. Ingress được rollout/reload; kiểm tra từng region/instance.
5. Probe TLS với SNI và expected hostname, ghi fingerprint/serial.
6. Browser/mobile và Java clients đại diện kết nối thành công.
7. Kiểm tra lỗi handshake và dữ liệu availability theo thời gian rollout.
8. Loại secret/cert cũ theo policy, revoke khi cần.
9. Đối chiếu CA issuance record với runtime và inventory.
10. Reviewer xác nhận evidence, không chỉ nhìn ticket Renewed.

**Assurance conclusion hợp lệ:** các endpoints/clients được kiểm tra đang sử dụng cert mới đúng policy tại thời điểm và trong phạm vi xác định, còn các đường chưa probe được ghi riêng.

### 28.6. Kịch bản nghi lộ worker key

Một secret chứa mTLS private key của report-worker bị phát hiện trong artifact cũ có nhiều người đọc.

**Cần làm:**

- Đánh giá ai có thể truy cập artifact, trong thời kỳ nào; bảo toàn bằng chứng.
- Giới hạn quyền và tạo key pair mới.
- Cấp certificate cho đúng worker identity qua issuer đã được kiểm soát.
- Deploy mới, kiểm tra worker/API tin đúng chain và authz scope.
- Revoke/retire certificate cũ; nếu client không dùng revocation, áp control bổ sung.
- Kiểm tra actor có cert hợp lệ nhưng không được quyền tenant có bị chặn.
- Kiểm tra logs để xác định có dấu hiệu lạm dụng; ghi độ bất định.
- Thu hồi secret cũ, tăng kiểm soát artifacts và xây regression/audit.
- Đánh giá residual risk và quyết định sự cố theo thẩm quyền.

**Không nên** chỉ renew certificate với chính key bị lộ, cũng không được tuyên bố không có ảnh hưởng vì chưa thấy log mTLS bất thường khi log coverage chưa được kiểm chứng.

## 29. Quản lý finding, exception và residual risk

### 29.1. Trạng thái đánh giá

| Kết luận | Điều kiện | Cách xử lý |
|---|---|---|
| **Pass/Supported** | Control đạt tiêu chí với evidence đủ trong scope/kỳ | Ghi claim, limitations và tiếp tục monitoring |
| **Fail/Unsupported** | Có bằng chứng chain/identity/key/lifecycle sai requirement | Finding, containment, remediation và retest |
| **Insufficient evidence** | Thiếu inventory, runtime test, log, client coverage hoặc hồ sơ đáng tin | Bổ sung chứng cứ, không tự gắn Pass |
| **Not applicable** | Không có đối tượng/điều kiện áp dụng, được giải thích và phê duyệt | Lưu rationale và trigger đánh giá lại |
| **Exception/risk acceptance** | Sai lệch nội bộ có quyết định đúng thẩm quyền và điều kiện | Theo dõi riêng; control failure vẫn tồn tại |

### 29.2. Finding: CA dashboard xanh nhưng runtime cũ

**Observation:** Issuance system cấp certificate mới, nhưng một ingress instance ở region phụ vẫn phục vụ certificate cũ đã quá hạn.

**Evidence:** endpoint hostname/SNI, served cert fingerprint, time, instance/region mapping, CA issuance record, secret/deployment version, client errors.

**Root causes cần điều tra:** reload không diễn ra, controller bỏ sót target, ingress reference sai, secret mount không cập nhật, monitoring chỉ xem CA status hoặc target không nằm trong inventory.

**Remediation:** giới hạn tác động nếu cần, deploy/reload đúng, bổ sung retry/monitoring/alert, chạy test trên mọi instances quan trọng, đối chiếu registry và retest cả client population.

**Không đóng finding** chỉ vì certificate manager báo Active. Phải xác minh **certificate thực đang served và các client có khả năng xác thực nó**.

### 29.3. Exception: legacy client chưa tin CA mới

Một client cũ không hỗ trợ chain mới và chưa thể thay ngay. Nhóm vận hành có thể đề xuất migration plan và kiểm soát bù trừ. Hồ sơ phải ghi:

- Client và service scope, certificate/CA identity, traffic và data sensitivity.
- Thời hạn, nguyên nhân và những phương án đã đánh giá.
- Tác động tới availability và trust/security.
- Những control bù trừ đã thực thi và kiểm thử.
- Người phê duyệt đúng thẩm quyền, nghĩa vụ áp dụng.
- Timeline thay thế client, monitoring và review trigger.
- Bằng chứng rollout/retirement cuối cùng.

**Không được xử lý bằng cách tắt hostname verification mặc định cho toàn ứng dụng.** Khi có ngoại lệ trong một môi trường kiểm soát, cần bảo đảm không tạo đường tin cậy quá rộng.

### 29.4. Risk acceptance không đổi sự thật kỹ thuật

Nếu certificate chain fail theo tiêu chí được phê duyệt, risk owner có thể cân nhắc **cách xử lý/tác động kinh doanh** trong thẩm quyền, nhưng bản ghi kiểm thử vẫn là Fail. Không được coi một chữ ký acceptance là bằng chứng chứng thư hợp lệ hoặc là quyền bỏ qua nghĩa vụ pháp lý/hợp đồng bắt buộc.

## 30. Continuous certificate assurance và metrics

### 30.1. Continuous không có nghĩa một job hết hạn

Một chương trình certificate assurance trưởng thành có thể kết hợp:

- **Inventory reconciliation:** so CMDB/service registry, endpoints thực, CA issued lists và secret stores.
- **Runtime health probes:** TLS handshake, served fingerprint, SAN, issuer, trust chain, thời hạn và client compatibility.
- **Issuance anomaly detection:** request trái phép, SAN/issuer bất thường, certificate ngoài inventory.
- **Key custody monitoring:** secret access, keystore/file access, HSM usage và những thay đổi quyền.
- **Renewal automation health:** job success/failure, retry, target rollout và thời gian còn lại.
- **Revocation/retirement verification:** certificate không còn sử dụng trái policy; effective access của service bị loại bỏ.
- **Trust-store change review:** CA import/removal, JVM image updates và CA rollover.
- **mTLS policy testing:** peer identity mapping, authorization và bypass coverage.
- **Incident and tabletop exercises:** khả năng phản ứng khi key exposure hoặc CA misissuance.
- **Evidence quality checks:** monitor/probe hoạt động, data sources đủ, time/region rõ.
- **Periodic risk review:** điều chỉnh profile, thuật toán, CA service, dependency và scope khi có thay đổi.

Các phép kiểm tra có thể chạy theo **mỗi release, theo lịch, trước expiry, sau trust change hoặc theo sự kiện incident**. Chu kỳ do tổ chức xác định theo rủi ro; không cần chạy mọi kiểm thử mỗi phút.

### 30.2. Trigger phải tái đánh giá

- Thêm hostname, SAN, internal service, tenant, region hoặc API vendor.
- Thay CA/issuer, root/intermediate trust, certificate profile hoặc thuật toán.
- Đổi JVM, proxy, ingress, sidecar, SSL library, device clients hoặc trust stores.
- Tạo/hủy workload identity, IAM/service account mapping.
- Thêm ACME controller hoặc thay DNS credentials/records.
- Phát hiện key exposure, misissuance hoặc endpoint có cert bất thường.
- Renewal/rollout/reload thất bại, incident TLS handshake.
- Có requirement thuật toán, policy hoặc nghĩa vụ mới liên quan.
- Một certificate không còn owner hoặc inventory/monitoring coverage giảm.
- Application authorization gắn certificate identity đã đổi.

### 30.3. Metrics và giới hạn

| Metric | Mục tiêu | Cảnh báo diễn giải |
|---|---|---|
| **% endpoints trọng yếu có owner và inventory** | Accountability | Nếu discovery chưa đủ, mẫu số có thể sai |
| **% runtime certificates được probe thành công** | Độ phủ trạng thái thực | Probe một region không bao phủ mọi nơi |
| **Số certs critical gần hết hạn không có plan** | Dự phòng availability | Chỉ theo dõi issued certs bỏ sót deployed certs |
| **% renewals verified loaded/served** | Chất lượng rollout | CA status không tự chứng minh runtime |
| **Số failed renew/reload jobs quá hạn** | Khả năng khắc phục automation | Một failure critical có thể nghiêm trọng hơn nhiều success |
| **% certificate keys có owner/custody policy** | Quản trị key material | Có owner không chứng minh quyền thực tế đúng |
| **% unauthorized issuance tests bị từ chối** | Chất lượng identity governance | Samples không đủ có thể che lỗi policy khác |
| **Số unapproved trust anchors** | Trust-store hygiene | Phải xác minh cả trust anchors embedded trong apps |
| **% mTLS endpoints có peer identity/authz tests** | Xác thực và phân quyền service | mTLS configured không chứng minh không có bypass |
| **% client populations đạt CA rollover test** | Compatibility và resilience | Một JVM hiện đại không đại diện embedded clients |
| **Số certificates/key exposure findings mở/quá hạn** | Rủi ro tồn đọng | Ít finding có thể do chưa quan sát đủ |
| **% remediations đã retest trên target thật** | Độ tin cậy khắc phục | Ticket Done hoặc renewed không đủ |
| **Thời gian phát hiện và xử lý key compromise** | Incident capability | Không phản ánh incidents không được phát hiện |
| **Số certificate instances không có owner/không dùng** | Dọn nợ hạ tầng | Thao tác xóa vội có thể làm hỏng dependency |
| **Số evidence gaps critical còn mở** | Độ bất định chưa giải quyết | Không được tính gap là Pass |

### 30.4. Dashboard tránh “100% TLS green” giả

Một dashboard có thể hiển thị 100% certificates chưa hết hạn nhưng bỏ sót:

- Endpoint legacy không nằm trong inventory.
- JVM client tắt hostname verification.
- Private key chung nhiều services.
- mTLS identity mapping cho phép truy cập trái scope.
- Certificate ở CA manager không trùng served certificate.
- Intermediate CA có vấn đề hoặc trust store chứa CA ngoài policy.
- Service dùng self-signed cert và client bỏ validation.
- Sidecar bị bypass hoặc plaintext fallback.
- Revocation status không được kiểm tra khi requirement đòi hỏi.

Do đó báo cáo phải đi kèm **scope, mẫu số, thời kỳ, nguồn, loại phép kiểm tra, những gì chưa chứng minh và residual risk**.

## 31. Những sai lầm thường gặp

### “Certificate còn hạn nghĩa kết nối an toàn”

Chưa đủ. Cần kiểm tra chain/trust, SAN/hostname, công dụng, client behavior, key protection và authorization. Một certificate đúng ngày có thể bị phát hành cho identity sai.

### “Certificate do một CA được tin cấp có thể dùng cho mọi tên”

Không. Hostname/SAN matching, key usage/EKU và các ràng buộc path/identity phải được thực thi theo use case. Tin CA không mặc định tin mọi danh tính mà CA có thể cấp.

### “CSR được ký nghĩa requester sở hữu domain”

Không. CSR thường chứng minh quyền kiểm soát private key, nhưng phải có **domain/identity validation** riêng theo profile/CA policy.

### “Root tự ký nên không đáng tin, hoặc tự ký nên tự đáng tin”

Cả hai cách nói quá đơn giản. Một trust anchor được chấp nhận vì **quyết định trust distribution/policy**, không phải chỉ vì tính self-signed. Client cần trust anchor và path validation phù hợp.

### “Có file .crt nghĩa có cả private key”

Không mặc định. Certificate thường chứa public key. Ngược lại, PEM/P12 có thể chứa private key, phải bảo vệ và kiểm tra trước chia sẻ.

### “Mã hóa TLS thay application authorization”

Không. TLS bảo vệ/xác thực kênh trong mô hình, không tự giới hạn người dùng hoặc service có quyền xem điểm học viên lớp nào.

### “Client lỗi TLS thì tắt verification để giữ uptime”

Đây là anti-pattern nguy hiểm: nó làm mất căn cứ xác thực bên kia. Phải sửa chain, SAN, trust store, key/cert, CA rollover hoặc client config đúng.

### “CA manager báo Renewed là endpoint đã an toàn”

Chưa đủ. Cần runtime probe, reload, các instance/regions, client trust và deployment mapping.

### “Renew certificate đồng nghĩa rotate key”

Không luôn đúng. Một cert mới có thể dùng cùng key; key rotation cần được chứng minh qua sự kiện tạo/thay key và key custody.

### “Revoke trên CA là tất cả client lập tức ngừng tin”

Không mặc định. Các clients có thể khác nhau về CRL/OCSP/status/fail mode, và một số hệ thống dùng short-lived cert hoặc trust changes. Phải test behavior thật.

### “Certificate ngắn hạn giải quyết mọi vấn đề”

Không nếu automation lỗi, issuer bị lạm dụng, service identity sai hoặc runtime không reload.

### “Dùng mTLS là không cần authz”

Không. Một peer được xác thực vẫn có thể thiếu quyền nghiệp vụ đối với endpoint, tenant hoặc đối tượng.

### “Kubernetes Secret tự bảo vệ mọi private key”

Không. Cần xem RBAC, encryption, access logs, pod/namespace boundaries, deployment privileges và secret lifecycle.

### “Dùng một wildcard certificate cho mọi service luôn đơn giản và an toàn”

Không thể kết luận như vậy. Cần cân đối phạm vi tên, chia sẻ key, blast radius, secret distribution và khả năng rotation.

### “Certificate Transparency chứng minh endpoint đang dùng certificate”

CT có thể giúp theo dõi certificates công khai được log; không chứng minh deployment, key custody, TLS validation hoặc inventory private PKI.

### “Một OpenSSL verify thành công chứng minh Java client sẽ luôn kết nối”

Không. Trust store, thuật toán, hostname checks, TLS policy và JDK/client population có thể khác. Phải kiểm tra runtime ứng dụng thật.

### “Code signing certificate chứng minh ứng dụng không có lỗ hổng”

Không. Signature chỉ hỗ trợ xác minh nội dung được ký và signer theo policy. Cần thêm build provenance, secure SDLC và application testing.

### “Không có alert có nghĩa không có certificate issue”

Không nếu inventory/probe/alert routing lỗi. Phải kiểm tra sức khỏe hệ thống monitoring.

### “Thiếu evidence nghĩa certificate chắc chắn bị lỗi”

Thiếu evidence là **bất định**, không tự chứng minh fail; nhưng cũng không có cơ sở kết luận pass.

### “Risk acceptance đổi Fail thành Pass”

Acceptance là quyết định quản trị có giới hạn, không thay kết quả kiểm thử hoặc nghĩa vụ bắt buộc.

### “Certificate chỉ cần review khi gần hết hạn”

Certificate/CA/key/trust có thể thay đổi vì service deployment, DNS, identity, vendor, incident, chính sách hay thuật toán. Cần **change-driven reassessment**.

## 32. Bài tập thực hành

### Bài tập A — Phân biệt certificate, key và trust

Một backend Java cần gọi HTTPS API của đối tác. Nhân viên vận hành thấy lỗi xác minh certificate và đề xuất đưa toàn bộ certificate server cùng private key vào Java truststore.

Hãy giải thích:

1. Trust store có vai trò gì; client cần public certificates hay private key của server?
2. Phải kiểm tra SAN, chain, trust anchor và client runtime nào?
3. Vì sao gửi private key của đối tác vào trust store là không phù hợp?
4. Những rủi ro nào xuất hiện nếu thay bằng TrustManager luôn chấp nhận?
5. Evidence nào xác nhận sau sửa client chỉ tin đúng danh tính?
6. Những điều gì vẫn cần kiểm tra ở application authorization?

**Gợi ý:** Client kiểm tra public certificate/trust chain; private key của server không phải tài liệu cần phân phối cho client.

### Bài tập B — Renewal không bằng served certificate

Một cloud certificate manager báo certificate mới đã cấp, còn 90 ngày tới hạn. Nhưng một số người học trên ứng dụng mobile nhận lỗi TLS.

Hãy lập kế hoạch điều tra:

- Endpoint/SNI, region, proxy, load balancer và runtime instances.
- Served fingerprint/serial, chain, hostname và validity.
- Deployment/secret references và reload history.
- Khác biệt về trust store giữa mobile/JVM/browser clients.
- Lựa chọn containment/rollback an toàn.
- Điều kiện đánh dấu renewal hoàn thành.
- Monitoring bổ sung để tránh false-green.

**Gợi ý:** Dashboard CA và certificate được served có thể khác nhau; ghi evidence tại từng đường ảnh hưởng.

### Bài tập C — mTLS không thay authorization

Learning API chỉ cho report-worker xuất dữ liệu lớp đã được cấp nhiệm vụ. Worker có mTLS certificate hợp lệ nhưng do lỗi policy, nó có thể xuất mọi tenant.

Hãy phân biệt:

1. Những gì mTLS đã chứng minh.
2. Những gì authorization chưa chứng minh.
3. Service identity được lấy từ SAN/namespace/issuer theo mô hình nào?
4. Test một client certificate sai CA, một client đúng CA nhưng sai identity và một client hợp lệ nhưng không được phép tới tenant khác.
5. Bằng chứng cần từ TLS, app audit, job/file và deployment.
6. Risk owner nên nhận báo cáo ra sao?

### Bài tập D — Thiết kế issuance policy

Tổ chức dùng private CA cho production. Team A có một automation token và xin certificate mang tên service của Team B.

Tạo security requirements cho:

- Requester authentication và identity ownership validation.
- Namespace/service account entitlement.
- CSR/public key verification và SAN/EKU constraints.
- Approval, audit và key custody.
- Negative tests đối với unauthorized SAN.
- Reissue/revoke và incident response.
- Evidence review theo kỳ.

**Gợi ý:** CA ký đúng thuật toán vẫn có thể cấp **nhầm identity** nếu quy trình authorization sai.

### Bài tập E — Private key bị lộ

Một file PKCS#12 chứa server private key production xuất hiện trong một artifact repository có quyền đọc quá rộng.

Hãy viết incident response plan:

1. Xác định phạm vi service, cert serial, key reuse và người có thể đọc.
2. Bảo toàn evidence mà không chia sẻ lại private key.
3. Containment, rekey/reissue, deployment/reload và rollback hợp lệ.
4. Revocation behavior của clients và biện pháp bổ sung.
5. Điều tra dấu hiệu giả mạo hoặc lạm dụng, nêu uncertainties.
6. Retest client trust và application behavior.
7. Quy trình đánh giá impact, approval, communications theo thẩm quyền.
8. Cập nhật key custody, pipeline và alert rules.

**Gợi ý:** Không renew với chính compromised key. Không kết luận chắc chắn chưa bị lạm dụng chỉ từ việc không có alert.

### Bài tập F — CA rollover cho JVM cũ

Một internal CA phải đổi intermediate/root theo kế hoạch, trong khi hệ thống có Java services chạy nhiều JDK versions và một client thiết bị không thường xuyên được cập nhật.

Hãy xây thứ tự rollout:

- Inventory clients, trust stores và certificate dependencies.
- Kế hoạch phân phối trust anchors trước khi chuyển leaf.
- Test chain/name/EKU trong những nhóm clients.
- Cơ chế giữ trust giai đoạn giao nhau và thời điểm retire.
- Rollback và xử lý client không tương thích.
- Evidence về trust-store version, runtime handshake và remediation.
- Điều kiện go/no-go và residual risk của legacy device.

### Bài tập G — Đọc certificate chưa phải assurance

Assessor nhận ảnh chụp một file certificate có SAN đúng, Not After còn ba tháng, issuer là CA được duyệt. Service owner đề nghị kết luận tất cả traffic tới API được xác thực đúng suốt quý.

Hãy chỉ ra:

- Claim nào được hỗ trợ thực sự?
- Những evidence nào thiếu về runtime, client, trust store, private key, kỳ?
- Những đường TLS terminate nào cần inventoried?
- Cần test sai hostname/chain và kiểm tra revocation khi policy yêu cầu không?
- Nếu chưa có evidence về mobile SDK cũ, kết luận nên viết thế nào?

### Bài tập H — Tạo control register và metrics

Một nền tảng có 200 TLS endpoints, 10% là internal mTLS, một số certs được cấp từ CA khác và 15 endpoints chưa có owner rõ. Certificate manager theo dõi chỉ những certs do nó cấp.

Hãy tạo:

1. Data model inventory với owners, SAN, issuer, serial, expiry, key reference, runtime locations.
2. Discovery và reconciliation plan giữa CA, ingress, JVM, mesh và service registry.
3. Risk-based priority cho endpoints không owner.
4. Tối thiểu năm controls có test methods và evidence.
5. Metrics không đánh đồng “CA managed” với “runtime trusted”.
6. Findings và exception process cho legacy certs.
7. Lộ trình automation/monitoring theo criticality.

### Bài tập I — Certificate signing và release chain

Một pipeline tạo artifact Java JAR, ký nó bằng key trong hệ thống signing, sau đó deploy lên production. Security team chỉ có bản ghi “signature valid”.

Hãy phân tích:

- Chữ ký hợp lệ chứng minh điều gì?
- Làm sao đối chiếu signer identity, key custody, commit, build, artifact digest và deployment?
- Nếu signing key bị lộ, hệ thống có biết những artifacts nào cần review?
- Revocation/cert expiry và historical signatures được kiểm tra theo policy nào?
- Cần những controls nào để ngăn artifact sai vẫn được ký bằng key hợp lệ?

### Bài tập J — Assurance report có failure và evidence gaps

Một kỳ đánh giá giả định ghi nhận:

- Inventory có 80 public endpoints; discovery phát hiện thêm 6 endpoints chưa biết.
- 70 certificates do CA manager quản lý đã được tự renew gần đây.
- 2 ingress production vẫn phục vụ certificate cũ, một cái đã hết hạn.
- 15 internal mTLS services chưa có negative trust/authorization tests.
- Một nhóm Java client tắt hostname verification để xử lý lỗi trust.
- CT monitor phát hiện một certificate mới cho subdomain không có owner.
- Chưa có log chứng minh private CA key custody được review trong kỳ.

Hãy viết báo cáo:

1. Những phần nào là **control failure**, **inventory gap** và **insufficient evidence**?
2. Risk scenarios, impact và ưu tiên remediation theo business criticality.
3. Việc nào cần containment tức thời và ai sở hữu?
4. Những tests/evidence để đóng từng finding?
5. Có được kết luận “100% certificate compliant” không?
6. Cách báo scope, kỳ, assumptions và residual risk cho CISO.
7. Trigger nào cần bổ sung để tránh tái diễn?

**Gợi ý:** Runtime cert expired và hostname verification disabled là sai lệch quan sát được; missing mTLS tests và CA custody logs là evidence gaps. Certificate trong CT cần điều tra trước khi khẳng định phát hành trái phép.

## 33. Checklist cho certificate management có bằng chứng

Checklist sau giúp rà soát chương trình; **tích đủ ô không tự chứng minh mọi certificate/control đã đạt**.

- [ ] Có inventory public/internal TLS, mTLS, device, CA và signing certificates thuộc scope.
- [ ] Những endpoints/identities trọng yếu có service owner, technical owner và risk owner rõ.
- [ ] Inventory có SAN, issuer/serial/fingerprint, validity, purpose, endpoint và deployment references.
- [ ] Không lưu private key hoặc password trong inventory/evidence.
- [ ] CA/profile, identity vetting và issuance authorization được phê duyệt.
- [ ] CSR/public key không bị coi thay bằng chứng quyền sở hữu domain/identity.
- [ ] Private keys có key custody controls, RBAC, rotation và incident plan theo risk.
- [ ] Đã phân biệt trust store, keystore, CA certificate, leaf cert và key material.
- [ ] TLS clients thực hiện chain, hostname/identity, purpose và policy checks phù hợp.
- [ ] Không có trust-all hoặc hostname verification disabled ngoài ngoại lệ cô lập có kiểm soát.
- [ ] mTLS peer identities được map đúng workload và application authorization.
- [ ] Có kiểm tra bypass/plaintext paths khi kiến trúc cần mTLS.
- [ ] Certificate renew/reissue và key rotation được phân biệt rõ trong records.
- [ ] Runtime served certificate được so với CA issuance/deployment, không chỉ dashboard.
- [ ] Có alert trước expiry, health checks và escalation tới owner theo criticality.
- [ ] Renewal controller, DNS/ACME credentials, issuer scopes được bảo vệ.
- [ ] Revocation/status/fail behavior được hiểu và test trong clients cần thiết.
- [ ] CA/trust rollover có compatibility plan, review và rollback.
- [ ] Certificate Transparency/issuance anomaly monitoring được áp dụng khi phù hợp.
- [ ] Service/devices retired có certificate/key/trust/authorization cleanup.
- [ ] Code signing certificate và verifier được quản lý nếu nằm trong scope.
- [ ] Có test matrix positive/negative, key mismatch, expiry, chain, identity và mTLS.
- [ ] Bằng chứng đúng client/JDK/proxy, environment, deployment/build và kỳ đánh giá.
- [ ] Evidence có provenance, completeness, reliability, integrity và limitations.
- [ ] Phân biệt design, implementation và operating effectiveness.
- [ ] Assessment ghi rõ Pass, Fail, Insufficient evidence, N/A và exception theo policy.
- [ ] Findings có impact, owner, deadline, fix, retest và residual risk decision.
- [ ] Không dùng risk acceptance để đổi Fail thành Pass hoặc bỏ nghĩa vụ bắt buộc.
- [ ] Có trigger reassessment khi CA, SAN, clients, vendor, key, trust, cert hoặc app policy đổi.
- [ ] Báo cáo lãnh đạo nêu **đã chứng minh điều gì, chưa chứng minh điều gì và những rủi ro nào vẫn còn**.

## 34. Ghi nhớ

- **Certificate management là quản trị vòng đời certificate và tin cậy**, từ xác minh danh tính, tạo/bảo vệ key, issuance, deployment tới renewal, revocation, retirement và assurance.
- **Certificate gắn public key với identity theo chữ ký/policy issuer; private key phải được bảo vệ**. CSR không tự chứng minh quyền sở hữu danh tính.
- **Chain trust, SAN/hostname, validity, KU/EKU, thuật toán, trust anchor và client behavior** đều quan trọng; chỉ xem Not After không đủ.
- **CA issued không bằng deployed, deployed không bằng loaded/served, served không bằng client trusted**. Cần evidence cho từng mắt xích.
- **Renewal khác key rotation**; khi key compromised, phải xử lý rekey/reissue, trust, revoke và các đường lạm dụng phù hợp.
- **mTLS xác thực peer nhưng không thay application authorization** đối với chức năng, tenant hoặc dữ liệu.
- Trust store/CA roots là **quyết định bảo mật lớn**, còn tắt hostname verification hoặc trust-all là anti-pattern nghiêm trọng.
- ACME, short-lived certificates, HSM và managed CA hỗ trợ automation/custody nhưng **không tự loại bỏ rủi ro identity, authorization và vận hành**.
- Revocation phải được đánh giá qua **hành vi client thực**, không chỉ trạng thái Revoked trong CA dashboard.
- Security assurance cần **risk → requirements/controls → test/evidence → claim/assessment → finding/remediation → residual risk**, với scope, period và limitations rõ ràng.
- Chương trình trưởng thành duy trì **inventory reconciliation, runtime verification, alerting, key/CA lifecycle governance, incident response và continuous reassessment** trong phát triển và vận hành.





