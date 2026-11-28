# Certificate pinning và giới hạn áp dụng trong PKI mạng

Một ứng dụng ngân hàng trên điện thoại kết nối tới `api.example.test` qua HTTPS. Thư viện TLS của hệ điều hành kiểm tra chứng chỉ máy chủ, tên miền và chuỗi tin cậy tới một CA đáng tin. Nhưng nếu một CA trong kho tin cậy cấp nhầm chứng chỉ hợp lệ cho tên miền đó, hoặc thiết bị bị cấu hình thêm một CA kiểm soát bởi bên khác, ứng dụng có thể gặp một endpoint có chứng chỉ **vượt qua kiểm tra PKI mặc định** dù không phải máy chủ dự định. Có nên yêu cầu chứng chỉ phải khớp thêm một khóa công khai mà ứng dụng đã biết?

Đó là ý tưởng của **certificate pinning**: client bổ sung một ràng buộc về chứng chỉ hoặc khóa công khai được chấp nhận cho một hostname/dịch vụ, bên cạnh quy trình xác thực TLS thông thường. Kỹ thuật này có thể thu hẹp phạm vi tin cậy trong một số threat model, nhưng tạo **rủi ro vận hành đáng kể**: thay chứng chỉ, đổi khóa, thay CA hoặc chuyển CDN có thể khiến ứng dụng không còn kết nối được nếu pin không được cập nhật đúng lúc.

Bài thuộc chương **PKI và chứng thư cho mạng** của module **SECURITY_NETWORK_SECURITY**, gắn với kiến trúc TLS, firewall, VPN, xác thực kết nối, DNS, Wi-Fi, IDS/IPS và các dịch vụ cloud. Trọng tâm là trả lời **pin cái gì, vì sao, ở đâu, kiểm chứng thế nào và khi nào không nên dùng**, thay vì chỉ đưa ra một đoạn mã so sánh hash.

> **Nguyên tắc quan trọng:** pinning là điều kiện **bổ sung** cho xác minh chứng chỉ và hostname, **không thay thế** việc xác minh CA, thời hạn, mục đích sử dụng khóa hoặc quyền truy cập ứng dụng. Pinning triển khai sai có thể vừa giảm an ninh vừa làm gián đoạn dịch vụ.

## 1. Kiến thức nền: TLS tin cậy chứng chỉ theo cách nào?

Khi client kết nối HTTPS, xác minh server thông thường cần trả lời:

1. Chứng chỉ được cung cấp có thể xây dựng **đường dẫn chứng thực** tới một trust anchor được client cho phép không?
2. Các chữ ký, giới hạn CA, key usage, extended key usage, thuật toán và thời hạn chứng chỉ có hợp lệ theo chính sách không?
3. Tên máy chủ mà client định kết nối có khớp **Subject Alternative Name (SAN)** theo quy tắc nhận diện tên thích hợp không?
4. Những chính sách bổ sung về revocation, Certificate Transparency (CT), doanh nghiệp hoặc ứng dụng có được áp dụng đúng không?
5. Server có chứng minh sở hữu private key liên quan trong **TLS handshake**, và các thông điệp bắt tay có được bảo vệ toàn vẹn không?

Các bước được thư viện TLS, hệ điều hành hoặc trình duyệt thực hiện theo nền tảng và cấu hình. Một certificate có thể **được ký bởi CA hợp lệ nhưng không khớp hostname**, hoặc khớp hostname nhưng **hết hạn**. Cả hai đều có thể bị từ chối dù public key của certificate trùng với giá trị đã pin.

### 1.1. Các thực thể cần phân biệt

| Thành phần | Vai trò | Lưu ý khi pin |
|---|---|---|
| **Root CA / trust anchor** | Điểm neo tin cậy do client/trust store chọn | Pin một root CA công khai quá phổ biến có thể mở phạm vi tin cậy rất rộng |
| **Intermediate CA** | CA trung gian ký chứng chỉ cấp dưới | Có thể bị thay khi CA chuyển nhà cung cấp hoặc thay cấu trúc chain |
| **Leaf/server certificate** | Chứng chỉ chứa public key và SAN của server | Đổi leaf cert hoặc đổi key có thể làm pin hỏng |
| **SubjectPublicKeyInfo (SPKI)** | Cấu trúc chuẩn mô tả public key và thuật toán/parameters | Thường dùng để tạo fingerprint cho public-key pinning |
| **Private key** | Bí mật tương ứng public key của server | Không đưa vào ứng dụng, repo, logs hoặc pin configuration |
| **Hostname/SNI** | Tên mà client muốn kết nối và có thể gửi trong handshake | Phải ràng buộc pin với hostname/phạm vi đích chính xác |
| **Trust store** | Các CA được client/phần mềm chấp nhận | Pin không tự biến trust store đã bị can thiệp thành an toàn trong mọi tình huống |
| **TLS endpoint** | Máy chủ/proxy thực sự kết thúc phiên TLS | Khi CDN/WAF terminate TLS, pin phải khớp **điểm TLS client gặp**, không phải khóa origin phía sau |

**SPKI không phải private key**, cũng không phải toàn bộ nội dung của file certificate. Hash SPKI có thể được sử dụng công khai vì nó được dẫn xuất từ **public key**.

### 1.2. Trust store và pinning giải quyết hai câu hỏi khác nhau

- **Xác minh PKI mặc định:** chứng chỉ này có hợp lệ với hostname theo những trust anchor và chính sách của client không?
- **Pinning:** trong các chứng chỉ/khóa đã vượt qua hoặc được xử lý theo chính sách xác minh, endpoint có chứa **đối tượng được ứng dụng chấp thuận trước** không?

Một mô hình an toàn thông thường là:

~~~text
Kết nối TLS đến hostname đích
    |
    v
Kiểm tra chain/CA + SAN hostname + validity + policy
    |
    +-- FAIL ------------------------> Từ chối
    |
    +-- PASS
           |
           v
       Kiểm tra pin trong phạm vi hostname đã định
           |
           +-- NO MATCH ------------> Từ chối
           |
           +-- MATCH ----------------> Tiếp tục handshake/kết nối
                                        và xác thực ứng dụng
~~~

Chi tiết thứ tự callback và khả năng đánh giá chain tùy TLS library, nhưng **kết quả cần đồng thời thỏa cả xác minh peer bình thường và yêu cầu pin**. Không “sửa” lỗi pin bằng cách bật `trustAllCertificates` hoặc bỏ kiểm tra hostname.

## 2. Pinning là gì, không phải là gì?

**Certificate pinning** là thuật ngữ thường dùng chung cho cơ chế ràng buộc client với một hoặc nhiều certificate/public keys được chấp nhận. Nên ghi rõ **kiểu pin** để tránh hiểu nhầm.

| Khái niệm | Ý nghĩa | Có phải pinning? |
|---|---|---|
| **Trust anchor mặc định** | Tin cậy những CA do nền tảng cung cấp | Không; đó là kiểm tra PKI cơ bản |
| **Custom trust store/private CA** | Chỉ hoặc thêm CA được tổ chức chọn | Có thể thu hẹp tin cậy, nhưng khác với pin một public key cụ thể |
| **Certificate fingerprint pin** | So khớp hash của toàn bộ chứng chỉ DER | Có; nhạy với thay đổi nội dung chứng chỉ |
| **SPKI/public-key pin** | So khớp hash của public-key structure trong certificate | Có; thường chịu được cấp lại cert với cùng key |
| **Intermediate CA public-key pin** | Chấp nhận chain có intermediate mang public key phù hợp | Có; phạm vi rộng hơn leaf key pin |
| **TOFU (Trust On First Use)** | Tin khóa thấy ở lần kết nối đầu tiên rồi nhớ để so sau | Cơ chế ghi nhớ khóa, không giống pin cấu hình trước |
| **mTLS** | Hai bên dùng chứng chỉ để xác thực lẫn nhau | Không tự động là server certificate pinning |
| **HSTS** | Yêu cầu trình duyệt sử dụng HTTPS đối với hostname theo chính sách | Không pin certificate/public key |
| **Certificate Transparency** | Cơ chế log và giám sát cấp phát chứng chỉ công khai | Không tự buộc server phải dùng một key cụ thể |

Certificate pinning cũng **không phải mã hóa bổ sung** cho payload. TLS vẫn sử dụng thuật toán thỏa thuận khóa và AEAD như bình thường; pinning thay đổi **điều kiện client chấp nhận danh tính server**.

### 2.1. Đừng nhầm pinning với HPKP

**HTTP Public Key Pinning (HPKP)** là cơ chế lịch sử cho phép website đưa chính sách pin qua HTTP header để trình duyệt ghi nhớ. Nó đã bị **ngừng hỗ trợ ở các trình duyệt lớn** do rủi ro khóa nhầm người dùng khỏi website, lạm dụng và vận hành khó khăn.

Vì vậy:

- **Không khuyến nghị triển khai HPKP header** cho website public hiện đại.
- Ứng dụng native **có thể thực thi application-managed pinning** bằng API/thư viện phù hợp; điều này khác hẳn việc trông chờ browser tự học HPKP.
- HSTS và CT có thể góp phần tăng độ tin cậy HTTPS, nhưng **không phải một cách “thay thế tương đương” mọi chức năng của app pinning**.
- Không suy rằng mọi trình duyệt đều hỗ trợ một cơ chế “pin server cert” cho website public chỉ vì ứng dụng mobile có thư viện pinning.

## 3. Pin cái gì? So sánh certificate pin và SPKI pin

### 3.1. Pin toàn bộ leaf certificate

Giả sử certificate leaf A được cấp cho `api.example.test`. Client giữ SHA-256 fingerprint của **toàn bộ DER certificate A**. Khi server đổi sang certificate B dù vẫn dùng **cùng public/private key**, các phần như serial number, validity, issuer và chữ ký có thể thay đổi; hash toàn certificate thường đổi.

**Ưu điểm:** ràng buộc rất cụ thể với certificate đã được phê duyệt.

**Nhược điểm lớn:** certificate renewal, reissuance hoặc CA migration dễ gây ngắt dịch vụ. Không phù hợp nếu quy trình phát hành ứng dụng cập nhật chậm mà certificate lại được tự gia hạn thường xuyên.

### 3.2. Pin SubjectPublicKeyInfo (SPKI)

Client lưu:

\[
\operatorname{pin}=\operatorname{Base64}\bigl(\operatorname{SHA256}(\operatorname{DER}(\operatorname{SPKI}))\bigr).
\]

Trong đó:

- **SPKI** gồm public key và thông tin thuật toán/parameters theo cấu trúc ASN.1.
- **DER** là dạng mã hóa nhị phân chuẩn, không phải văn bản PEM có dòng `BEGIN PUBLIC KEY`.
- **SHA-256** tạo fingerprint 32 byte.
- **Base64** là cách biểu diễn fingerprint để lưu trong cấu hình; bản thân Base64 **không phải hàm băm hoặc mã hóa bảo mật**.

Nếu server **cấp lại certificate bằng đúng cùng key pair**, SPKI fingerprint có thể giữ nguyên, dù issuer/serial/validity khác. Nếu **đổi sang key pair mới**, fingerprint thay đổi và cần chuẩn bị pin mới.

**Đánh đổi:** giữ key pair lâu để tránh thay pin có thể làm tăng rủi ro từ việc duy trì private key dài hạn. Không biến pinning thành lý do trì hoãn khóa xoay vòng vô thời hạn.

### 3.3. Pin intermediate CA hoặc root CA

Một số sản phẩm cho phép pin public key của **bất kỳ chứng chỉ phù hợp trong validated chain**, không nhất thiết leaf. Điều này thay đổi phạm vi:

- **Leaf SPKI pin:** rất hẹp, kiểm soát chặt key của endpoint, nhưng rotation khó.
- **Intermediate SPKI pin:** có thể cho phép nhiều leaf certificates từ cùng intermediate; dễ đổi leaf key hơn, nhưng **tăng số chứng chỉ có thể đạt pin** và phụ thuộc CA.
- **Root CA SPKI pin:** thường quá rộng cho mục tiêu ràng buộc một API cụ thể; nhiều site không liên quan cũng có thể xây chain tới root đó, nên mức bảo vệ bổ sung có thể thấp.

Không pin một CA chỉ vì “dễ quản lý hơn” mà bỏ qua threat model. Nếu bạn muốn chống rủi ro **một CA hợp lệ nhưng cấp sai leaf**, pin CA đó có thể **không đủ thu hẹp phạm vi** như pin một leaf key chuyên dụng.

### 3.4. So sánh bằng tình huống rotation

| Thay đổi ở server | Pin toàn certificate leaf | Pin leaf SPKI | Pin intermediate SPKI |
|---|---|---|---|
| Gia hạn cert, **giữ nguyên key** | Thường cần đổi pin | Thường không đổi | Không đổi nếu chain vẫn dùng intermediate được pin |
| Gia hạn cert và **đổi key** | Cần đổi pin | Cần đổi pin | Có thể tiếp tục nếu intermediate vẫn thuộc tập pin |
| Đổi intermediate CA | Có thể cần đổi pin do cert đổi | Có thể tiếp tục nếu leaf key giữ nguyên | Có thể hỏng pin |
| Đổi CDN/TLS endpoint với key khác | Thường hỏng | Hỏng nếu key chưa được pin | Tùy chain thực tế |
| Key bị đánh cắp | Pin không bảo vệ trước kẻ có key đó | Pin không bảo vệ trước kẻ có key đó | Phụ thuộc loại tấn công, thường không loại bỏ rủi ro |

Các ô trong bảng giả định **kiểm tra PKI/hostname vẫn thành công**. Khi cert hết hạn, bị thu hồi hoặc hostname không khớp, kết nối cần bị từ chối theo chính sách dù pin trùng.

## 4. Mô hình threat: pinning chống được ai?

Một quyết định dùng pinning cần mô tả rõ: **đối thủ là ai, họ kiểm soát phần nào, client chạy ở đâu, certificate được cấp thế nào và fail mode chấp nhận được là gì**.

### 4.1. Ví dụ đối thủ có chứng chỉ được CA tin cậy cấp nhầm

Giả sử:

1. Client muốn kết nối `api.example.test`.
2. Attacker điều khiển đường mạng và có một certificate **khớp hostname, chain hợp lệ**, nhưng sử dụng **public key không thuộc tập pin**.
3. Client xác minh PKI theo trust store và sẽ chấp nhận certificate nếu **không có ràng buộc pin thêm**.
4. Khi pinning được thực thi đúng, client nhận ra SPKI không nằm trong tập pin và **từ chối kết nối**.

~~~mermaid
flowchart TD
    C["Ứng dụng: kết nối api.example.test"] --> T["Handshake TLS và kiểm tra chain/SAN"]
    T --> D{"Certificate hợp lệ theo PKI?"}
    D -->|"Không"| F["Từ chối kết nối"]
    D -->|"Có"| P{"SPKI trong validated chain có khớp pin hợp lệ?"}
    P -->|"Không"| F
    P -->|"Có"| A["Tiếp tục kết nối TLS"]
    A --> Z["Ứng dụng tiếp tục AuthN/AuthZ"]
~~~

Kịch bản này chỉ đúng khi pinning được triển khai **ở ứng dụng thực sự thực hiện kết nối**, các dữ liệu pin được bảo vệ đủ tốt và không có cách bypass do cấu hình.

### 4.2. Những tình huống pinning không giải quyết

- **Endpoint đã bị compromise:** attacker có thể đọc dữ liệu trước khi đưa vào TLS, lấy token, can thiệp vào ứng dụng hoặc sửa code/runtime trên thiết bị có quyền phù hợp.
- **Server private key được pin bị lộ:** attacker có thể dùng chính danh tính mật mã được pin trong những điều kiện thích hợp; pin không thay việc revoke/rotate và điều tra.
- **Ứng dụng xác thực người dùng sai:** một kênh TLS đúng server vẫn có thể cho phép truy cập trái quyền nếu AuthZ ở API lỗi.
- **DNS sai nhưng cert/key vẫn hợp lệ:** pin không thay cơ chế kiểm tra hostname, policy DNS, định tuyến hoặc domain ownership.
- **DDoS/bão hòa đường truyền:** pin không cung cấp năng lực hấp thụ băng thông hay đảm bảo availability.
- **XSS, SQL injection, SSRF, malware:** pin không sửa lỗi nghiệp vụ hoặc lỗ hổng ứng dụng.
- **Insider có quyền kiểm soát pin policy/CI:** họ có thể sửa pin được ứng dụng chấp nhận nếu supply chain không được bảo vệ.
- **Sai endpoint/certificate ở phía server được quản trị:** nếu pin trỏ tới key cũ, hệ thống có thể từ chối kết nối chính đáng.

### 4.3. Pinning và corporate TLS inspection

Một số tổ chức thực hiện HTTPS inspection hợp lệ bằng proxy có CA riêng được cài vào trust store của thiết bị. Proxy sẽ **kết thúc TLS từ client và tạo một TLS session khác tới website**. Với client pin SPKI của endpoint gốc, certificate do proxy cấp **không khớp pin**, nên kết nối có thể thất bại.

Đây có thể là:

- **Hành vi bảo vệ mong muốn** khi ứng dụng cố tình không cho phép TLS interception đối với API nhạy cảm.
- **Xung đột vận hành** nếu tổ chức yêu cầu inspection để thực thi bảo vệ web/DLP cho dịch vụ khác.

Không khuyến nghị sửa bằng cách **tắt toàn bộ certificate validation** hoặc “bỏ pin khi gặp proxy” mà không có thiết kế an toàn được phê duyệt. Thay vào đó, xác định chính sách các domain không được inspection, endpoint compliance, egress controls và trách nhiệm hai bên.

## 5. Thiết kế ranh giới pinning trong kiến trúc mạng

### 5.1. Pin của client tới điểm kết thúc TLS

~~~mermaid
flowchart LR
    APP["Mobile app: pins cho api.example.test"] -->|"TLS phiên A"| W["CDN / WAF / LB"]
    W -->|"TLS phiên B, identity khác"| O["Origin API"]
    O -->|"mTLS/service identity khi có"| S["Backend"]
    APP -.->|"Kiểm tra pin"| W
~~~

Nếu client TLS kết thúc tại **CDN/WAF**, pin của client phải phù hợp với certificate/public key mà **edge đó thực sự trình bày**. Pin origin certificate không có tác dụng nếu client không gặp origin trong handshake.

Đường **edge → origin** là kết nối riêng: edge phải xác minh certificate/identity của origin và kiểm soát ingress. Pinning ở app không tự chứng minh rằng WAF đã kiểm tra đúng chứng chỉ origin.

### 5.2. Một FQDN có nhiều PoP, nhiều certificate

Khi ứng dụng dùng CDN toàn cầu, cùng hostname có thể được phục vụ từ:

- Các PoP ở nhiều khu vực.
- Nhiều vùng/quản trị chứng chỉ khác nhau.
- Hạ tầng IPv4 và IPv6.
- Cụm canary hoặc disaster recovery.
- TLS trên TCP và QUIC/HTTP/3.

Nếu **các điểm TLS termination dùng nhiều key hợp lệ**, tập pin phải được thiết kế phù hợp với chúng trước khi rollout. **Một handshake từ laptop ở một khu vực không chứng minh toàn bộ PoP cùng dùng một SPKI.**

### 5.3. Tên miền nào nằm trong phạm vi pin?

Không nên bật pin toàn bộ domain một cách vô thức. Ví dụ:

| Hostname | Mục đích | Cân nhắc |
|---|---|---|
| `api.example.test` | API nhạy cảm do doanh nghiệp quản lý | Có thể là ứng viên pinning khi kiểm soát key/rollout tốt |
| `login.example.test` | IdP hoặc SSO | Cần đánh giá ai quản lý cert/key, redirect và rotation |
| `assets.example.test` | Static files qua CDN nhiều tenant | Pinning cứng có thể phức tạp hơn lợi ích |
| `payments.vendor.test` | SDK/API bên thứ ba | Không pin khóa vendor khi không có thỏa thuận về key lifecycle |
| `telemetry.vendor.test` | Logging/analytics | Cần bảo đảm cập nhật key, hỗ trợ proxy, không làm tê liệt app |

Sử dụng domain trong `.test` chỉ để minh họa. Thực tế cần policy theo **hostname chính xác**, xử lý wildcard và subdomain inheritance theo API/platform; không tự động tin pin của `api.example.test` áp dụng cho mọi `*.example.test`.

## 6. Khi nào nên và không nên dùng certificate pinning?

### 6.1. Những điều kiện nên cân nhắc

Pinning có thể phù hợp khi **đồng thời** có các điều kiện:

1. Dữ liệu/kênh có rủi ro đặc thù mà **PKI mặc định + các lớp bảo vệ khác** chưa giảm đủ.
2. Nhà phát triển **kiểm soát cả client và chu kỳ phát hành ứng dụng**, hoặc có kênh cập nhật pin an toàn.
3. Tổ chức **kiểm soát hoặc có cam kết về lifecycle key** của TLS endpoint.
4. Có **backup pin/key**, khả năng rollout/rollback, monitoring và cơ chế khôi phục khả dụng.
5. Mọi pin đều được gắn với đúng hostname và kiểm tra chain/hostname **không bị vô hiệu hóa**.
6. Tác động khi khách hàng offline, dùng app cũ hoặc không cập nhật nhiều tháng đã được đánh giá.

Ví dụ có thể là ứng dụng mobile quản lý thiết bị, ứng dụng tài chính hoặc client trong môi trường đóng với những API nhạy cảm, **khi lợi ích kiểm soát danh tính có thể đo và vận hành được**.

### 6.2. Những trường hợp nên tránh hoặc xem lại

- **Website public trong trình duyệt:** không hồi sinh HPKP; ưu tiên PKI chuẩn, HSTS, CT, giám sát certificate và quản lý CA/DNS đúng.
- **Ứng dụng có tuổi thọ dài nhưng không có kênh cập nhật:** hard pin dễ khóa truy cập vĩnh viễn khi đổi khóa/cert.
- **API/CDN bên thứ ba mà mình không sở hữu key:** vendor có thể rotate key mà không thông báo; pinning làm tăng sự cố không kiểm soát.
- **Nhiều client/thiết bị legacy:** khó thu hồi pin cũ, khó xử lý certificate rotation.
- **Hệ thống bị TLS inspection doanh nghiệp bắt buộc:** cần đàm phán phạm vi và mô hình rủi ro; hard pin có thể xung đột.
- **Mục tiêu chỉ là “tăng điểm bảo mật”:** nếu không có threat model và runbook, độ rủi ro vận hành có thể vượt lợi ích.
- **Pin root CA công khai quá rộng:** thường không giảm đáng kể trust surface cho một service riêng.

**Kết luận chọn lựa:** không có quy tắc “mọi HTTPS API phải pin”. Pinning là **quyết định rủi ro và vận hành** gắn với quyền kiểm soát endpoint, không phải một checklist bắt buộc vô điều kiện.

## 7. Key rotation: bài toán khó nhất của pinning

### 7.1. Vì sao một pin duy nhất dễ gây outage?

Giả sử phiên bản app 1.0 chứa **pin duy nhất của public key K1**. Server hoạt động bình thường tới khi:

- Cert mới được triển khai với **key K2** vì bảo trì hoặc nghi ngờ K1 bị lộ.
- CA/CDN tự đổi certificate và tạo key pair khác.
- Region dự phòng dùng K2, trong khi region chính vẫn dùng K1.

App cũ chỉ biết K1 sẽ từ chối K2 dù K2 có certificate hợp lệ. Người dùng có thể **không đăng nhập được để nhận thông báo cập nhật**, gây hiện tượng khóa dịch vụ.

### 7.2. Active + backup pins

Một thiết kế có thể đóng gói **tập pin**:

~~~text
Ứng dụng phát hành:
  accepted SPKI pins:
    - K1 (khóa hoạt động hiện tại)
    - K2 (khóa dự phòng đã tạo, chưa phục vụ)

Thời điểm ban đầu:
  TLS endpoint dùng K1 -> PASS.

Sau rollout K2:
  TLS endpoint dùng K2 -> PASS (nếu cert/hostname hợp lệ).

Sau khi client fleet đã cập nhật và K1 không cần thiết:
  Phát hành cấu hình/ứng dụng mới bỏ K1 theo quy trình.
~~~

**Backup pin phải được chuẩn bị trước khi cần đổi khóa**, không phải sau khi người dùng đã bị khóa. Nếu pin K2 được đưa vào hệ thống qua **remote configuration**, cơ chế cập nhật phải có xác thực, toàn vẹn, kiểm soát chống rollback và không vô hiệu hóa kiểm tra TLS cơ bản.

### 7.3. Thứ tự rollout an toàn

~~~mermaid
flowchart TD
    I["Kiểm kê TLS endpoints và client versions"] --> K["Tạo key backup, kiểm soát private key"]
    K --> P["Phát hành client/policy chấp nhận K1 + K2"]
    P --> M["Đo adoption, kiểm tra clients cũ/offline"]
    M --> D{"Đủ điều kiện rotate endpoint?"}
    D -->|"Chưa"| P
    D -->|"Có"| R["Canary endpoint dùng K2"]
    R --> T["Kiểm thử mọi PoP, IPv4/IPv6, TCP/QUIC"]
    T --> S{"Pin error / business SLO ổn?"}
    S -->|"Không"| B["Rollback endpoint theo runbook"]
    S -->|"Có"| F["Mở rộng rollout K2 và tiếp tục quan sát"]
    F --> C["Loại K1 khi đã đảm bảo an toàn/client coverage"]
~~~

Đây là luồng phê duyệt ở mức khái niệm, không có nghĩa khi private key K1 **đã bị lộ** thì nên rollback về K1 chỉ để giữ dịch vụ. Trong sự cố lộ khóa, phải cân bằng việc **thu hồi ngay khóa nguy hiểm** với khả năng khôi phục an toàn, có kế hoạch truyền thông và ứng phó đặc biệt.

### 7.4. Pin expiration: không phải phương án thần kỳ

Một số framework có trường *expiration* cho pin set. Khi hết hạn, phần kiểm tra pin có thể không còn hiệu lực theo hành vi của nền tảng; đó là đánh đổi **availability so với mục đích pinning**.

Đừng ghi một ngày expiration rồi cho rằng mọi client sẽ tự đổi sang khóa mới. Cần hiểu chính xác:

- Khi pin hết hạn, framework bỏ kiểm tra pin hay chặn kết nối?
- Client dùng đồng hồ thiết bị thế nào? Đồng hồ sai gây tác động gì?
- Có telemetry cho các app phiên bản cũ/hết hạn không?
- Khi CA/leaf đổi đột xuất, app cũ chưa cập nhật xử lý thế nào?

**Không dùng pin expiration như thay thế cho backup pin, rotation plan hoặc khả năng phát hành ứng dụng**. Một cơ chế “fail-open sau ngày X” có thể loại bỏ lớp bảo vệ mà đội an ninh tưởng vẫn đang hoạt động.

## 8. Pin trong ứng dụng Android

Android có **Network Security Configuration** cho một số trường hợp sử dụng, hỗ trợ cấu hình pin cho host bằng hash SPKI và thiết lập chính sách trust theo môi trường. Cách áp dụng chính xác phụ thuộc Android version, networking stack và việc ứng dụng có sử dụng cơ chế này hay không.

### 8.1. Mẫu XML chỉ để đọc cấu trúc

~~~xml
<!-- MINH HỌA, KHÔNG PHẢI FILE CONFIG TRIỂN KHAI ĐƯỢC.
     Thay placeholder bằng Base64(SHA256(DER(SPKI))) hợp lệ sau review. -->
<network-security-config>
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="false">api.example.test</domain>
    <pin-set>
      <pin digest="SHA-256">PRIMARY_SPKI_SHA256_BASE64</pin>
      <pin digest="SHA-256">BACKUP_SPKI_SHA256_BASE64</pin>
    </pin-set>
  </domain-config>
</network-security-config>
~~~

**Placeholder không phải giá trị Base64 hợp lệ để triển khai.** Trong dự án thực, file phải được tích hợp đúng với ứng dụng và manifest, sử dụng pin tạo từ public-key data được kiểm chứng, kết hợp default/custom trust anchors được phê duyệt, rồi kiểm thử đầy đủ. Không copy XML này vào production.

Lưu ý:

- `includeSubdomains="false"` biểu thị ý định không tự mở rộng pin sang toàn bộ subdomain; cần xác minh rule thực tế của framework.
- Một số môi trường **debug trust anchors** có cơ chế ảnh hưởng tới enforcement của pinning; không suy kết quả debug bằng với bản release.
- Android app có thể dùng thư viện HTTP hoặc networking stack riêng không tuân đầy đủ hành vi mà đội phát triển tưởng do file XML quản lý.
- Pinning có thể được thực thi thêm ở **OkHttp/HTTP client hoặc SDK**; phải tránh hai bộ pin mâu thuẫn và những đường kết nối bỏ qua interceptor.
- Không dùng `HostnameVerifier` trả `true` cho mọi host hoặc `TrustManager` chấp nhận mọi certificate để “fix” lỗi pin.

### 8.2. Chú ý theo môi trường và phiên bản

Ứng dụng release, debug, staging và production có thể gặp những endpoint/cert khác nhau. Nên:

1. Dùng domain/PKI riêng cho staging hoặc profile rõ theo build configuration.
2. Không đưa private key hay khóa bí mật production vào repo/client.
3. Kiểm thử bản release thật với trust policy thật, không chỉ emulator/debug.
4. Lập ma trận Android version, HTTP stack, IPv4/IPv6 và proxy Wi-Fi/cellular.
5. Đảm bảo cập nhật app có thể phân phối **trước** khi backend xoay khóa.

## 9. Pin trong iOS, desktop và thiết bị quản lý

Trên iOS/macOS, ứng dụng có thể sử dụng các API của hệ thống bảo mật/trust evaluation và các cơ chế pinning do framework cung cấp. Khi dùng delegate của networking stack, điều kiện quan trọng là **giữ nguyên các bước xác thực peer theo nền tảng** rồi thêm kiểm tra pin đúng host.

### 9.1. Tránh lỗi tự viết trust handler

Một anti-pattern phổ biến là:

~~~text
Nếu SHA256(cert) == EXPECTED_PIN:
    chấp nhận server
Ngược lại:
    từ chối
~~~

Đoạn logic trên **không đủ**: nó không nói certificate có khớp hostname, còn hạn, có chain đáng tin, dùng cho server authentication và thực sự đang được server chứng minh private key hay không. Việc gọi API trust evaluation đúng theo nền tảng cũng phải xử lý redirect, SNI, host thay đổi và các session reuse.

Thiết kế đúng hơn ở mức khái niệm:

~~~text
1. Xác định hostname đích mà ứng dụng định kết nối.
2. Gọi cơ chế đánh giá trust/hostname chuẩn của platform.
3. Nếu trust evaluation FAIL -> từ chối, không fallback.
4. Nếu hostname thuộc scope phải pin:
     - đọc public-key data/SPKI của certificate thích hợp trong
       chain đã được đánh giá, theo semantics thư viện;
     - so fingerprint với tập pins còn hiệu lực của hostname đó;
     - không khớp -> từ chối.
5. Nếu cả hai PASS -> dùng TLS connection; API tiếp tục AuthN/AuthZ.
~~~

**Không khuyến nghị tự cài đặt X.509 path validation hoặc TLS handshake** khi nền tảng có API an toàn và đã được kiểm thử. Nên review implementation của thư viện/framework và có automated negative tests.

### 9.2. IoT và các client không thể cập nhật

Thiết bị IoT hoặc appliance có firmware khó cập nhật có thể bị khóa hàng loạt khi key/cert đổi. Nếu cân nhắc pinning cho thiết bị tuổi thọ dài:

- Xác định vòng đời firmware và khả năng phân phối bản sửa kể cả khi API chính bị mất kết nối.
- Đưa vào tập pin dự phòng có kế hoạch xoay khóa, secure boot và signed update khi thiết bị hỗ trợ.
- Phân biệt root trust store, vendor CA và leaf pin; tránh nhúng một leaf certificate sắp hết hạn mà không có phương án sửa.
- Kiểm thử certificate renewal, đồng hồ thời gian thực, CA expiration và khôi phục sau khi offline dài ngày.
- Không dùng pinning như cách che đi việc thiết bị **bỏ qua certificate validation**.

## 10. Tự kiểm tra SPKI fingerprint trong lab

Thao tác sau dùng **certificate công khai đã được tổ chức/lab cho phép kiểm tra**, không đọc private key. Không chạy công cụ trên hệ thống không thuộc phạm vi được ủy quyền.

### 10.1. Đọc chứng chỉ trước khi tính pin

~~~bash
# Đọc file certificate PEM có sẵn của lab.
openssl x509 -in /path/to/lab-server-cert.pem -noout -text

# In SHA-256 fingerprint của TOÀN BỘ certificate; đây không phải SPKI pin.
openssl x509 -in /path/to/lab-server-cert.pem -noout -fingerprint -sha256
~~~

Quan sát SAN, issuer, validity, public-key algorithm và chain expectation. **Không dùng fingerprint toàn cert thay cho SPKI hash** nếu thiết kế xác định phải pin public key.

### 10.2. Tạo SHA-256 fingerprint của DER-encoded SPKI

~~~bash
# Ví dụ Bash/OpenSSL cho certificate của lab:
# x509 -pubkey: trích xuất PUBLIC KEY (PEM SPKI) từ certificate.
# pkey -pubin -outform DER: chuyển public key/SPKI sang DER.
# dgst -sha256 -binary: SHA-256 trả 32 byte nhị phân.
# base64 -A: biểu diễn cùng 32 byte đó dưới dạng một dòng Base64.
openssl x509 -in /path/to/lab-server-cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256 -binary \
  | openssl base64 -A
~~~

Đường dẫn là placeholder; lệnh **chỉ có ý nghĩa khi bạn đã có file cert thực** và phiên bản OpenSSL hỗ trợ các tùy chọn trên. Trong PowerShell 5.1, cú pháp xuống dòng `\` của Bash không dùng giống nhau; có thể viết pipeline trên một dòng.

Chú ý:

- Lệnh chỉ tạo **fingerprint của public key**, không sinh private key.
- Một certificate mới dùng cùng key có thể cho **cùng SPKI pin**.
- Tính pin từ một certificate tải qua đường **chưa xác minh danh tính** rồi nhúng thẳng vào app có thể **pin nhầm khóa của attacker**. Nguồn certificate/key phải được kiểm chứng ngoài băng hoặc thông qua quy trình PKI/CI an toàn trước khi cho vào release.
- Phải kiểm tra chain/hostname và chứng chỉ đúng với **TLS termination thực tế**. Không lấy certificate origin khi app kết nối tới CDN edge.

### 10.3. Quan sát TLS endpoint được phép kiểm tra

~~~bash
# Máy chủ lab ở localhost phải thực sự tồn tại và có chứng chỉ phù hợp.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -showcerts
~~~

`-servername` dùng SNI; `-verify_hostname` kiểm tra danh tính theo tên; `-verify_return_error` ngăn chấp nhận lỗi xác minh; `-CAfile` phải trỏ tới trust anchor **được lab cho phép**. Nếu không có TLS server lab hoặc certificate/CA hợp lệ, ví dụ này sẽ báo lỗi là bình thường.

**Một lệnh OpenSSL s_client không chứng minh app pinning được bật:** nó chỉ kiểm tra TLS/PKI theo cách công cụ thực hiện, không chạy pin policy nằm trong ứng dụng. Muốn chứng minh pinning, phải kiểm thử **đúng binary/app và đúng TLS stack của nó** với tập key/cert được kiểm soát.

### 10.4. Bằng chứng cần ghi từ lab

| Trường | Ví dụ kết quả giả định | Mục đích |
|---|---|---|
| Hostname | `api.example.test` | Xác định scope của pin |
| TLS peer | Lab reverse proxy | Biết điểm kết thúc TLS |
| Certificate validation | PASS theo lab trust store | Điều kiện PKI độc lập |
| Leaf SPKI SHA-256 | `<BASE64_32_BYTE_DIGEST>` | Pin primary được kiểm chứng |
| Backup SPKI SHA-256 | `<BASE64_32_BYTE_DIGEST_BACKUP>` | Kiểm tra lộ trình rotation |
| Client build | `mobile-release-candidate` | Phiên bản thực thi pin |
| Kết quả pin check | MATCH / MISMATCH | Phân biệt lỗi pin và lỗi trust |
| Region / transport | Lab site, TCP/TLS hoặc QUIC nếu hỗ trợ | Phát hiện TLS endpoint dùng key khác |

Ví dụ trên là placeholder, **không phải mã fingerprint thật**. Nếu chia sẻ tài liệu với bên khác, không đưa session secret/private key vào bộ chứng cứ. Public-key fingerprint ít nhạy cảm hơn private key, nhưng mapping hạ tầng và danh sách endpoint vẫn cần quyền phù hợp.

## 11. Certificate pinning có quan hệ gì với những kiểm soát khác?

### 11.1. PKI trust, CT, HSTS và pinning

| Kiểm soát | Cơ chế | Pinning có thay thế không? |
|---|---|---|
| **TLS certificate validation** | Kiểm tra chain, hostname, validity, policy | **Không**; phải giữ |
| **Certificate Transparency** | Giúp phát hiện/giám sát certificate public được phát hành | Không; CT không chứng minh key đúng tập pin của app |
| **CAA DNS record** | Thông báo CA được phép cấp cert cho domain theo quy trình CA | Không; không kiểm soát mọi client TLS session |
| **HSTS** | Trình duyệt sử dụng HTTPS theo policy | Không; khác lớp ràng buộc |
| **DNSSEC** | Xác minh tính xác thực dữ liệu DNS trong phạm vi ký/validation | Không; DNSSEC không xác thực TLS peer thay cert |
| **mTLS** | Server xác thực certificate client và client xác thực server | Có thể phối hợp với pin server, nhưng không tự tương đương |
| **WAF / API auth** | Kiểm tra request, danh tính/authorization và hành vi | Không; TLS đúng peer không có nghĩa quyền data đúng |
| **Private networking / VPN** | Giới hạn và bảo vệ đường mạng theo policy | Không; đường riêng vẫn cần peer identity |
| **Endpoint security / MDM** | Bảo vệ client, cấu hình trust và vòng đời app | Không; pin không cứu được endpoint đã bị compromise |

**CAA và CT** hỗ trợ mô hình quản lý chứng chỉ nhưng không phải cơ chế “ngăn chặn tức thì mọi certificate cấp sai” tại client. Nếu phát hiện misissuance, cần quy trình xác minh, liên hệ CA, rotate/revoke và kiểm tra tác động.

### 11.2. Certificate pinning trong 802.1X/EAP-TLS và Wi-Fi

Ở Wi-Fi Enterprise, client phải xác minh **chứng chỉ server EAP/RADIUS** theo profile, CA và danh tính server mong đợi; đây là thành phần thiết yếu chống điểm truy cập/AAA giả. Một số nền tảng có thể ràng buộc thêm CA/server cụ thể theo policy quản trị.

Đừng tự động chuyển nguyên mẫu **HTTP certificate pinning** sang 802.1X: supplicant, EAP method, certificate trust và cơ chế profile có quy tắc riêng. Điểm chung là **không chấp nhận mọi certificate chỉ vì cùng tên SSID**, và không bỏ qua server identity validation.

### 11.3. Pinning không bảo vệ toàn bộ đường VPN/cloud

Nếu mobile app pin key của `api.example.test`, nó chỉ áp dụng cho **kết nối từ app tới TLS endpoint tương ứng**. Luồng từ VPN gateway tới proxy, CDN tới origin hoặc microservice A tới B cần cơ chế **xác thực/mTLS, firewall, IAM, service identity** riêng.

Khi có load balancer/ingress mesh thay key, phải xác định rõ **pin đang áp ở layer nào**. Một hệ thống có thể có ba TLS sessions và ba bộ certificate khác nhau trên cùng data flow.

## 12. Phân tích những rủi ro và lỗi triển khai thường gặp

| ID | Rủi ro | Biểu hiện | Cách ngăn ngừa/kiểm chứng |
|---|---|---|---|
| P01 | **Pin một leaf cert duy nhất** | Renew cert gây outage dù same key | Cân nhắc SPKI và backup pins theo threat model |
| P02 | **Pin một public root quá rộng** | Tưởng chống misissuance nhưng phạm vi chấp nhận vẫn lớn | Đánh giá trust surface, so với leaf/intermediate SPKI |
| P03 | **Không có backup key** | Rotation khẩn không thể duy trì app cũ | Dự phòng trước, thiết kế rollout theo client fleet |
| P04 | **Bỏ certificate/hostname validation** | Pin match nhưng kết nối vẫn không được xác thực đúng cách | Trust evaluation chuẩn + pin là điều kiện bổ sung |
| P05 | **Lấy pin qua kết nối chưa được tin cậy** | Pin nhầm khóa không thuộc service thật | Key provenance, review/approval, nguồn xác minh độc lập |
| P06 | **Đổi CDN/PoP không kiểm kê key** | Một region/IPv6/QUIC bị lỗi không đồng đều | Ma trận PoP, SNI, IPv4/IPv6, transport |
| P07 | **Pin SDK bên thứ ba** | Vendor rotate key không báo trước | SLA/ownership, tránh pin nếu không kiểm soát lifecycle |
| P08 | **Remote pin update thiếu bảo vệ** | Kẻ xấu thay tập pin từ config endpoint | Signed config, anti-rollback, trust bootstrap và audit |
| P09 | **Hết hạn pin không được theo dõi** | Tưởng còn pin nhưng enforcement đã vô hiệu | Quan sát trạng thái pin theo build và chính sách expiration |
| P10 | **TLS inspection xung đột** | Ứng dụng không dùng được trên mạng doanh nghiệp | Policy domain exemption/architecture review thay vì tắt validation |
| P11 | **Release/debug khác nhau** | Debug PASS nhưng production fail | Test đúng trust anchors và binary release |
| P12 | **Chứng chỉ/private key bị compromise** | Attacker có key được pin, pin không chặn | Incident response, rotate/revoke, thiết kế dự phòng |
| P13 | **Không có đường cập nhật client** | App offline lâu ngày bị khóa khi rotate | Signed update channel, supported-version policy |
| P14 | **Pin tự động theo lần đầu (TOFU) không kiểm soát** | Lần kết nối đầu bị can thiệp thành pin độc hại | Secure provisioning/bootstrap và provenance |
| P15 | **Chỉ dựa vào pin để xác thực API client** | Client hợp lệ vẫn có thể truy cập sai tenant | OAuth/mTLS khi phù hợp, AuthN/AuthZ ở application |
| P16 | **Log nhầm/thiếu phân loại lỗi** | Dồn mọi lỗi TLS thành “pinning failed” | Phân biệt network, DNS, PKI, pin mismatch, app auth |
| P17 | **Rollback về khóa đã lộ** | Phục hồi availability nhưng tái mở nguy cơ nghiêm trọng | Emergency key compromise runbook, không rollback mù |
| P18 | **Chồng pin ở nhiều HTTP stacks** | Một SDK bỏ qua pin hoặc hai policy mâu thuẫn | Inventory các library và mọi đường TLS connection |

### 12.1. Failure mode đáng sợ: “ứng dụng không thể tự chữa mình”

Ứng dụng bị lỗi pin có thể mất kết nối tới API tải cấu hình hoặc tải bản cập nhật nếu chúng dùng cùng host/pin. Điều này tạo vòng lặp:

~~~mermaid
flowchart TD
    A["Server đổi khóa sang K2"] --> B["Client cũ chỉ pin K1"]
    B --> C["TLS tới API thất bại"]
    C --> D["Client muốn tải pin mới từ chính API"]
    D --> E["Không thể kết nối để tải bản sửa"]
    E --> F["Cần kênh cập nhật độc lập hoặc khôi phục đã chuẩn bị"]
~~~

Vì vậy **kênh cập nhật ứng dụng/pin phải được thiết kế ngay từ đầu**, không trông chờ một response HTTPS từ endpoint mà client đã không thể xác thực.

## 13. Monitoring, lỗi và incident response

### 13.1. Phân loại lỗi theo lớp

| Triệu chứng | Có thể do | Bằng chứng cần xem |
|---|---|---|
| DNS lookup thất bại | Resolver, split DNS, DNSSEC, connectivity | QNAME/RCODE, resolver path, network logs |
| TCP/TLS không kết nối được | Firewall, route, proxy, server down, QUIC khác TCP | Connection errors, gateway/edge telemetry |
| Chain/SAN/time validation error | CA, hostname, certificate hết hạn/chưa hợp lệ | TLS library verify reason, cert metadata |
| **Pin mismatch** sau PKI pass | Key/CDN/PoP đổi, pin policy sai, can thiệp vào TLS endpoint | Fingerprint thực tế, build pin set, endpoint identity |
| Chỉ một số vùng lỗi | PoP dùng certificate/key khác | Region, SNI, IPv4/IPv6, transport, edge changes |
| Chỉ app cũ lỗi | Pin set quá cũ, không có backup pin | Client version/adoption và key rollout timeline |
| TLS PASS nhưng API trả 401/403 | Authentication/authorization ứng dụng | App/API logs, token, role và resource policy |
| TLS inspection môi trường doanh nghiệp lỗi | Proxy trình certificate khác pin | Trust/inspection policy, network path được phê duyệt |

### 13.2. Telemetry cần thiết

- App version/build, platform/OS version, HTTP stack, **pin policy version**.
- Hostname được pin, loại pin (leaf SPKI/intermediate/whole cert), kết quả **PKI validation** và **pin match** tách biệt.
- Loại lỗi, thời gian, khu vực/PoP nếu biết, transport TCP/TLS hay QUIC/HTTP3.
- Certificate expiration/key rotation event từ CA/CDN/edge.
- Tỷ lệ kết nối thành công, latency, login/transaction completion, số client offline và số thiết bị chưa cập nhật.
- Audit thay đổi pin config, code review, signed release và danh sách rollback được phê duyệt.

Không đưa raw private keys, access tokens hoặc toàn bộ TLS secrets vào telemetry. Dấu vân tay public key có thể ghi theo chính sách, nhưng **hostname nội bộ, thông tin thiết bị và địa điểm** vẫn có thể nhạy cảm. Hạn chế retention, truy cập và xuất log.

### 13.3. Runbook khi pin mismatch tăng đột ngột

1. **Xác nhận phạm vi:** app build nào, hostname nào, các vùng/PoP nào, tỷ lệ lỗi và tác động nghiệp vụ.
2. **Tách nguyên nhân:** chain/SAN/expiration lỗi hay PKI PASS nhưng pin mismatch? Không gọi mọi TLS error là lỗi pin.
3. **Đối chiếu thay đổi:** cert deployment, rekey, CA migration, CDN configuration, proxy inspection, release và signed pin policy.
4. **Xác minh provenance của key mới:** liên hệ owner PKI/CDN, kiểm tra key identity qua kênh được tin cậy, không tự học key từ traffic đang nghi bị can thiệp.
5. **Kích hoạt phương án đã phê duyệt:** dùng backup pin đã phát hành, rollback endpoint **chỉ khi khóa cũ chưa bị compromise**, hoặc triển khai client update qua kênh an toàn độc lập.
6. **Theo dõi phục hồi:** tỷ lệ pin match, login/transaction SLO, các client lâu không cập nhật; ghi timeline, owner và rollback decision.
7. **Hậu kiểm:** điều chỉnh rotation calendar, alerts, kế hoạch dự phòng và kiểm thử các edge/TLS stacks bị bỏ sót.

Nếu nghi ngờ **private key bị đánh cắp**, không mặc định quay về key cũ vì lý do availability; cần phối hợp security incident response và quy trình thay chứng chỉ/thu hồi đúng mức rủi ro.

## 14. Kiểm thử pinning bằng ma trận positive/negative

Kiểm thử chỉ thực hiện trong **lab hoặc môi trường được cấp phép**, sử dụng những certificate và key pairs do mình quản lý. Không cần tấn công người dùng khác hay intercept kết nối thật để xác minh.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| T01 | Cert hợp lệ, SPKI=K1 đã pin | PASS | PKI PASS, pin match, request thành công |
| T02 | Cert hợp lệ, SPKI=K2 backup đã pin | PASS | Pin match với backup, API hoạt động |
| T03 | Cert hợp lệ, SPKI=K3 không pin | **FAIL pin** | PKI PASS nhưng pin mismatch |
| T04 | Cert tự ký không trust, SPKI=K1 | **FAIL PKI** | Pin không bỏ qua trust validation |
| T05 | Cert chain hợp lệ, hostname không khớp SAN, SPKI=K1 | **FAIL hostname** | Verify error |
| T06 | Cert hết hạn, SPKI=K1 | **FAIL validity** | Certificate validation error |
| T07 | Renew leaf cert giữ K1 | SPKI pin vẫn PASS nếu chain/hostname hợp lệ | Compare old/new cert và SPKI |
| T08 | Renew và rekey K1→K2 | PASS khi backup pin tồn tại từ trước | Release version, pin set, edge key |
| T09 | Đổi intermediate CA, giữ leaf key K1 | Leaf SPKI pin có thể PASS; CA pin phải xem lại | Chain và pin semantics |
| T10 | Rollout K2 tại PoP A, K1 tại PoP B | Cả hai PASS trong giai đoạn migration | PoP/client sampling, canary SLO |
| T11 | Ứng dụng dùng IPv6/QUIC | Pin policy có hiệu lực đúng TLS endpoint | HTTP stack và transport-specific tests |
| T12 | App dùng một HTTP client phụ/SDK khác | Không đi qua đường bỏ kiểm tra pin ngoài ý định | HTTP stack inventory + test |
| T13 | Proxy TLS inspection với CA riêng | Hành vi reject/allow đúng policy đã phê duyệt | Proxy routing, pin/PKI reason |
| T14 | Client offline 90 ngày rồi quay lại | Không bị khóa nếu vẫn thuộc phiên bản hỗ trợ và pin plan hợp lệ | Reconnect test, rotation timeline |
| T15 | Thay đổi SAN/redirect sang host khác | Pin chỉ áp đúng domain policy, hostname validation vẫn giữ | Redirect + host/chain checks |
| T16 | App build debug khác release | Release vẫn enforce pin theo chính sách | Release-like device test |
| T17 | Expiration của pin policy | Hành vi được hiểu, theo dõi và phê duyệt | Platform-specific test + telemetry |
| T18 | Backend API trả 403 sau TLS PASS | Không bị nhầm thành pin failure | App AuthZ logs |
| T19 | Cấp nhầm certificate có PKI PASS nhưng key K3 | App từ chối theo pin | Controlled misissuance simulation trong lab |
| T20 | Thay key K1 vì bị compromise | Kích hoạt ứng cứu không rollback mù về K1 | Incident runbook và recovery plan |

**Quan trọng:** các ca T03/T04/T05/T06 tách riêng **pin check** và **PKI/hostname check**. Nếu một implementation chấp nhận cert không trust chỉ vì SPKI match, đó là dấu hiệu pinning đã bị dùng sai làm cơ chế trust tuyệt đối.

## 15. Bài tập thiết kế: ứng dụng mobile qua CDN

**Bối cảnh giả định:** một doanh nghiệp triển khai ứng dụng mobile truy cập `api.example.test` qua CDN. Công ty điều khiển origin API, nhưng CDN có hai TLS endpoints với key khác nhau ở hai vùng. Hiện tại:

| Thành phần | Trạng thái |
|---|---|
| Mobile app phiên bản 2.0 | Đã hardcode một leaf SPKI pin **K1** |
| CDN Region A | Cert hợp lệ, leaf SPKI **K1** |
| CDN Region B | Cert hợp lệ, leaf SPKI **K2** |
| Origin backend | Cert/key **K3**, không trực tiếp gặp mobile client |
| Lịch rotate tại CDN | Dự kiến thay key Region A thành **K4** |
| Người dùng | Có nhóm thiết bị offline nhiều tuần/tháng |
| Corporate proxy của một khách hàng | Có TLS inspection bằng CA riêng |
| Release pipeline | Có phát hành app store, signed app updates |

### Câu hỏi

1. Vì sao app 2.0 có thể kết nối thành công ở Region A nhưng thất bại ở Region B dù cả hai certificate đều hợp lệ theo PKI?
2. Có nên nhúng pin của origin K3 vào mobile app để khắc phục không?
3. Nếu chuyển từ leaf cert fingerprint sang leaf SPKI pin, những thay đổi nào giảm rủi ro outage và những thay đổi nào vẫn phá pin?
4. Hãy đề xuất lộ trình rotation K1/K2/K4 trước khi CDN đổi key.
5. Nếu app dùng thêm SDK telemetry với một HTTP stack khác, cần kiểm thử điều gì?
6. Proxy inspection của khách hàng sẽ tác động thế nào và làm sao phân biệt **xung đột policy** với chứng chỉ giả?
7. Nếu key K1 bị lộ, có nên rollback về K1 để cứu nhóm người dùng chưa cập nhật không?
8. Chứng chỉ hợp lệ + pin match có chứng minh API đã phân quyền đúng tenant chưa?

### Gợi ý lời giải

- App 2.0 **chỉ nhận K1**, nên kết nối trực tiếp đến TLS endpoint có K2 sẽ **pin mismatch** dù chain/hostname hợp lệ. Cần test mọi PoP/IPv4/IPv6/TCP/QUIC theo thực tế phân phối.
- Mobile app nhìn thấy **certificate của CDN edge**, không thấy K3 của origin ở phiên TLS đầu; pin K3 không giải quyết vấn đề.
- SPKI pin chịu được thay cert **giữ cùng public key**; rekey sang K2/K4 vẫn cần pin mới. Whole-certificate pin sẽ bị ảnh hưởng ngay cả khi cert được cấp lại với key cũ.
- Trước khi rotate: phát hành client chấp nhận **K1, K2, K4** theo scope đã review; đo tỷ lệ adoption và pin mismatch, thử canary, rồi mới mở rộng thay key. Xem lại mức độ cần thiết của từng pin, thỏa thuận lifecycle với CDN và chiến lược hỗ trợ client cũ.
- HTTP stack/SDK khác có thể không chạy qua cùng pinning policy; cần inventory và test riêng từng luồng HTTPS. Proxy inspection thay certificate mà client thấy, nên có thể bị từ chối theo đúng chính sách pin; không giải quyết bằng bỏ validation vô điều kiện.
- Nếu K1 compromise, **không rollback mù**; dùng runbook security incident, phương án cập nhật an toàn, truyền thông và thu hồi thay khóa. Cuối cùng, **AuthN/AuthZ của API vẫn độc lập** với TLS pinning.

## 16. Quy trình triển khai có thể vận hành lâu dài

### Bước 1 — Xác định mức rủi ro và mục tiêu

Mô tả tài sản, dữ liệu, các loại client, đối thủ và điểm kiểm soát trong tuyến kết nối. Chứng minh tại sao **PKI/hostname validation, HSTS/CT, kiểm soát CA và application security hiện tại** chưa đủ theo threat model. Nếu không chứng minh được lợi ích, cân nhắc **không pin**.

### Bước 2 — Kiểm kê TLS endpoints và key ownership

Ghi domain, CDN/edge/LB, regions, SNI, IPv4/IPv6, QUIC/TCP, public certificate issuers, ai giữ private key và ai có quyền rotate. Cần đánh giá các hệ thống failover, disaster recovery và app SDK sử dụng host khác.

### Bước 3 — Lựa chọn loại pin theo rủi ro

Quyết định leaf SPKI, intermediate SPKI hay một phương pháp khác dựa trên **mức thu hẹp trust surface và vòng đời key**. Tránh pin root CA rộng mà không giải thích được giá trị; tránh whole-cert pin cho dịch vụ tự renew nếu không có quy trình app update tương ứng.

### Bước 4 — Bảo vệ nguồn pin và cập nhật

Lấy fingerprint từ certificate/key đã được xác minh provenance; có code review, signed release, khả năng so sánh cấu hình đã phát hành. Backup pin phải sẵn **trước** rotation, được lưu và kiểm soát private key an toàn. Remote updates nếu có phải **authenticated, tamper-resistant và có chống rollback**.

### Bước 5 — Giữ nguyên validation bình thường

Không override TLS trust/hostname checks theo hướng chấp nhận mọi certificate. Khi pin mismatch, fail theo chính sách đã thiết kế, **không silently fallback sang HTTP hoặc chế độ bỏ pin**.

### Bước 6 — Canary và negative tests

Chạy đủ ma trận: cert hợp lệ/unpinned, pinned/untrusted, wrong SAN, expired cert, backup key, CDN PoP, app release, offline clients và proxy environment. Đánh giá impact về business SLO, không chỉ “request đã mã hóa”.

### Bước 7 — Theo dõi fleet và chuẩn bị incident

Đo app versions, số client chưa cập nhật, pin check result, cert expiry, key rotation logs, khả năng phân biệt lỗi. Có emergency contact giữa mobile team, network/PKI, CDN provider và SOC. Khi key compromise, ưu tiên an ninh danh tính và quy trình thu hồi thay vì chỉ cố giữ key cũ.

### Bước 8 — Rà soát định kỳ hoặc khi thay kiến trúc

Mỗi lần đổi CA, cert automation, CDN, API hostname, region, TLS stack, mobile runtime hoặc vendor SDK đều phải review pin policy. Xóa pin không còn được phép và cập nhật runbook; đừng để **pin bất biến trong app nhiều năm** mà không có người sở hữu.

## 17. Checklist certificate pinning và giới hạn áp dụng

- [ ] Có threat model chứng minh vì sao cần pinning ngoài xác minh TLS/PKI chuẩn.
- [ ] Biết điểm TLS termination thật mà client nhìn thấy: CDN/WAF/LB hay origin.
- [ ] Đã phân biệt whole-certificate fingerprint, leaf SPKI, intermediate/root SPKI và custom CA trust store.
- [ ] Ưu tiên SPKI theo nhu cầu nếu muốn hỗ trợ cert renewal giữ nguyên key, nhưng vẫn có rotation plan.
- [ ] Không coi root CA pin quá rộng là tương đương pin đúng endpoint key.
- [ ] Giữ chain validation, SAN/hostname, validity, usage và trust policies; pin phải là lớp bổ sung.
- [ ] Không bật HPKP header cho public website như một kiểm soát mới.
- [ ] Không dùng pinning để thay HSTS, CT, CAA, DNSSEC, mTLS, firewall hay AuthN/AuthZ.
- [ ] Nguồn pin được xác minh, không học khóa lần đầu từ một kết nối chưa đáng tin mà không có bootstrap bảo mật.
- [ ] Có primary và backup pins/keys phù hợp, backup sẵn trước khi rotate.
- [ ] Có thời gian đủ để phân phối client update và xử lý nhóm offline/không cập nhật.
- [ ] Không tái sử dụng private key quá lâu chỉ vì muốn giữ cùng SPKI pin.
- [ ] Kiểm thử rotation, CA/CDN migration, canary, rollback và tình huống private key compromise.
- [ ] Pin policy được gắn đúng hostname/scope, hiểu cách wildcard/subdomain/redirect hoạt động.
- [ ] Kiểm thử mọi PoP/region, IPv4/IPv6, TCP/TLS và QUIC/HTTP3 khi áp dụng.
- [ ] Đã kiểm tra tất cả HTTP stacks, SDKs, proxy hoặc TLS library có thể tạo kết nối riêng.
- [ ] Debug/staging và release có trust/pin behavior rõ; bản phát hành được kiểm thử thật.
- [ ] Phân biệt lỗi DNS/network, PKI, hostname, pin mismatch và API AuthZ trong logs.
- [ ] Có quyết định rõ với corporate TLS inspection và proxy, không tắt validation vô điều kiện.
- [ ] Remote pin update phải xác thực/toàn vẹn, chống thay đổi trái phép và xử lý rollback.
- [ ] Có monitoring client versions, pin expiration nếu có, certificate expiration và security control coverage.
- [ ] Không ghi private keys, session secrets hay token vào logs hoặc bundle ứng dụng.
- [ ] Có runbook riêng cho pin outage bình thường và lộ khóa xác thực dài hạn.
- [ ] Chấp nhận **không pin** khi rủi ro vận hành lớn hơn giá trị an ninh được chứng minh.

**Ghi nhớ:** **Certificate pinning không mã hóa thêm dữ liệu và không thay thế PKI**. Nó giúp client giới hạn **chứng chỉ/khóa công khai được chấp nhận** đối với một hostname trong những threat model cụ thể. Giá trị bảo vệ phụ thuộc vào **kiểm tra trust/hostname đúng, phạm vi pin đủ hẹp, nguồn key đáng tin và khả năng cập nhật/rotate an toàn**. Không có backup pin và kế hoạch khôi phục, một cơ chế tăng độ chắc chắn về danh tính có thể biến thành **nguyên nhân khiến toàn bộ ứng dụng mất khả dụng**.
