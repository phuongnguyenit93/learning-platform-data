# Đồng bộ metadata hai phía trước khi loại bỏ khóa cũ trong SAML 2.0

**Mục tiêu:** Xoay chứng thư/khóa SAML 2.0 của Identity Provider (IdP, hay Asserting Party) hoặc Service Provider (SP, hay Relying Party) mà không làm đứt đăng nhập SSO, xác minh chữ ký, giải mã assertion hoặc Single Logout. Để làm được điều đó, bên **phát hành khóa mới phải công bố metadata phù hợp trước**, bên **tiêu thụ phải nạp, kiểm chứng và chứng minh đã sử dụng được khóa mới**, sau đó mới chuyển hoạt động sang khóa mới. **Chỉ loại bỏ khóa cũ khi không còn bên nào hoặc thông điệp nào cần nó** và quy trình được phê duyệt. Ngoại lệ là khóa đã bị lộ/compromised, cần ứng phó khẩn cấp thay vì giữ overlap theo lịch.

Bài này thuộc **Spring Security – federation → Khóa và chứng thư**. Trọng tâm là **đồng bộ metadata hai phía**: metadata IdP mà SP đọc và metadata SP mà IdP đọc; những việc phải làm trước, trong và sau key rotation; kiểm tra thực tế; cấu hình Spring Security; lỗi phổ biến và kế hoạch rollback.

**Ghi nhớ quan trọng:** Xoay khóa ký, xoay khóa giải mã và cập nhật chứng thư HTTPS/TLS là **ba quy trình khác nhau**. Không được kết luận “metadata có cert mới” đồng nghĩa mọi instance/đối tác đã nạp và sẵn sàng; phải kiểm tra và có xác nhận vận hành.

## 1. Vấn đề cốt lõi: hai phía giữ hai bản cấu hình tin cậy

Trong SAML Web Browser SSO, SP sử dụng thông tin của IdP, còn IdP sử dụng thông tin của SP. Các metadata có thể nằm trong XML tại URL, trong file cấu hình đã triển khai hoặc trong giao diện quản trị của đối tác.

~~~text
  SP / Spring Security                               IdP / SSO
  --------------------                               ----------
  Có metadata IdP                                    Có metadata SP
  - IdP entityID                                     - SP entityID
  - IdP SSO/SLO URL                                  - SP ACS/SLO URL
  - IdP signing cert(s) <--------------------------  - SP signing cert(s)
  - encryption preferences                            - SP encryption cert(s)
            |                                                    |
            | (1) AuthnRequest ký bằng SP private key ------------>
            |                                                    | xác minh bằng SP cert
            | <---------- (2) SAMLResponse ký bằng IdP private key
            | xác minh bằng IdP signing cert                      |
            | <---------- (3) EncryptedAssertion dùng SP pubkey
            | giải mã bằng SP private key                         |
~~~

Hai bên có thể refresh metadata theo lịch khác nhau: một bên tải trực tuyến mỗi vài giờ, một bên import thủ công, một bên cache qua nhiều node, hoặc một bên giữ certificate pinned đến đợt triển khai kế tiếp. Vì vậy **thay khóa trên bên phát hành rồi xóa khóa cũ ngay lập tức** dễ làm thông điệp bị từ chối.

Ví dụ: IdP đang ký assertion bằng **I-old**; SP hiện chỉ biết I-old. Nếu IdP chuyển sang ký **I-new** trước khi SP đã nạp I-new, SAML Response mới có thể bị báo `invalid signature`. Ngược lại, nếu SP đổi khóa ký AuthnRequest **S-new** trước khi IdP nạp S-new, IdP sẽ từ chối AuthnRequest.

**Nguyên tắc thiết kế:** Bên nhận phải biết và tin khóa mới **trước khi** bên gửi bắt đầu dùng khóa mới.

## 2. Ba luồng khóa cần phân biệt

| Loại khóa | Ai sở hữu private key? | Ai cần public certificate? | Vai trò |
| --- | --- | --- | --- |
| **IdP signing key** | IdP | SP | SP xác minh chữ ký SAML Response/Assertion và một số thông điệp SAML từ IdP |
| **SP signing key** | SP | IdP | IdP xác minh AuthnRequest, LogoutRequest hoặc thông điệp được SP ký theo chính sách |
| **SP decryption key** | SP | IdP dùng public encryption key của SP | SP giải mã assertion/NameID IdP mã hóa cho SP |
| **IdP decryption key** | IdP | SP dùng public encryption key của IdP khi cần | IdP giải mã những phần tử được SP mã hóa |
| **Metadata signing key/trust anchor** | Bên ký metadata hoặc federation operator | Bên tiêu thụ metadata | Xác minh xuất xứ và toàn vẹn metadata XML theo trust policy |
| **HTTPS/TLS key** | Web server hoặc reverse proxy | Client TLS | Bảo vệ kênh truyền; không tự thay thế SAML message signature |

Một chứng thư X.509 có thể được cấu hình cho nhiều mục đích trong một số federation, nhưng không nên mặc định “certificate dùng để ký” cũng là “certificate dùng để mã hóa” hoặc “certificate TLS”. Khi xoay khóa, cần biết **chính xác luồng nào bị ảnh hưởng**.

**Thuật ngữ:** Trong bài, I-old/I-new là cặp khóa ký của IdP, S-old/S-new là cặp khóa ký của SP, E-old/E-new là cặp khóa giải mã tại SP. Đây là ký hiệu minh họa; thực tế dùng fingerprint SHA-256 và metadata phiên bản cụ thể để định danh.

## 3. Metadata KeyDescriptor: công bố khóa và phạm vi sử dụng

Trong SAML metadata, `KeyDescriptor` gắn public-key information vào một vai trò SAML. Ví dụ rút gọn cho IdP ở thời gian overlap:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>BASE64_IDP_OLD_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>BASE64_IDP_NEW_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <!-- SingleSignOnService và các thành phần metadata thực tế -->
</md:IDPSSODescriptor>
~~~

**Chỉ là mảnh cấu trúc**, không phải metadata hợp lệ để sử dụng: không có EntityDescriptor/entityID, chứng thư Base64 thật hoặc SSO URL. Không tự dùng các chuỗi `BASE64_...` làm certificate.

Các quy tắc:

- Có thể công bố **nhiều KeyDescriptor**, mỗi mục chứa khóa công khai khác nhau trong giai đoạn rollover.
- `use="signing"` áp dụng cho việc xác minh chữ ký; `use="encryption"` áp dụng cho mục đích mã hóa; khi `use` bị bỏ trống cần áp dụng đúng quy tắc SAML metadata.
- Chứng thư trong `ds:KeyInfo` của metadata là **thông tin công khai**, không bao gồm private key.
- IdP/SP có thể áp dụng chính sách về thứ tự chọn khóa và endpoint riêng; chỉ nhìn thấy hai certificate trong metadata **không chứng minh** cả hai đã được ứng dụng thực tế tải hoặc dùng được.
- `EntityDescriptor entityID`, `IDPSSODescriptor`/`SPSSODescriptor`, SSO/ACS, binding, signing requirements và thời hạn phải tiếp tục đúng.
- Khóa có thể được biểu diễn bởi `ds:KeyValue` hoặc X.509; không buộc mọi federation chỉ dùng một hình thức. Với các ví dụ Spring Security, X.509 certificate là cách cấu hình thông dụng.

Theo **OASIS Metadata Interoperability Profile**, khóa dành cho sử dụng trong tương lai có thể được công bố trước để chuẩn bị rollover, và khóa cũ không còn dùng được loại bỏ sau một khoảng chuyển tiếp phù hợp chính sách. Điều này **không cho phép** giữ khóa đã bị xâm phạm để đảm bảo availability.

## 4. Dòng thời gian chuẩn khi IdP đổi khóa ký Response/Assertion

**Trước khi đổi**, IdP đang ký bằng private key I-old và SP đang tin certificate I-old.

| Giai đoạn | IdP làm gì? | SP làm gì? | Điều kiện chuyển |
| --- | --- | --- | --- |
| **P0 – Inventory** | Xác định issuer, current signing cert, lịch đổi và consumer list | Xác định từng registrationId, trusted fingerprint và các instance | Hai phía thống nhất phạm vi |
| **P1 – Publish** | Sinh I-new an toàn; công bố **I-old + I-new** trong metadata IdP có nguồn tin cậy | Lấy candidate metadata, thẩm định issuer/nguồn/signature/time | Không xóa I-old |
| **P2 – Consumer ready** | Vẫn ký bằng I-old | Cập nhật trust config để chấp nhận chữ ký bằng **I-old hoặc I-new** trong registration đúng | Mọi SP/consumer cần xác nhận |
| **P3 – Cutover** | Chuyển ký SAMLResponse/Assertion sang **I-new** | Tiếp tục chấp nhận I-new và I-old trong khoảng được duyệt | Login mới bằng I-new thành công |
| **P4 – Drain** | Ngừng tạo chữ ký mới bằng I-old; xử lý outstanding flows | Đợi hết thời hạn message hợp lệ/replay window và kiểm tra thực tế | Không còn message cần I-old |
| **P5 – Retire** | Loại I-old khỏi IdP metadata/trust state theo chính sách | Sau xác minh consumer readiness, loại I-old khỏi trusted IdP credentials | Có bằng chứng hoàn tất và rollback được |

**Điểm quan trọng:** Ở P2, SP phải có I-new **trước** khi IdP ký bằng I-new. Ở P5, IdP không được kết luận mọi SP đã bỏ I-old chỉ vì URL metadata của mình đang hiển thị I-new.

**Trong môi trường multi-tenant**, mỗi SP consumer có thể là một nhóm ứng dụng, staging/prod, một vùng cloud, một cluster riêng hoặc một đối tác B2B. Lịch rollout phải bao trùm **mọi consumer còn được phép** của IdP đó.

### Nếu SP đã tin cả hai khóa, có tự đăng nhập được không?

Chưa chắc. Mỗi response vẫn phải đúng `Issuer`, `Audience`, `Recipient`, `InResponseTo`, Conditions và các yêu cầu signature. Nếu IdP đổi entityID, binding hoặc ACS đồng thời với đổi khóa thì đó là **thay đổi giao thức** riêng, không thể chỉ thay certificate.

**Không thử khóa của IdP khác** khi signature fails; chỉ dùng verification credentials thuộc asserting party đúng của registration đang xử lý.

## 5. Khi SP xoay khóa ký AuthnRequest: thứ tự đảo chiều

Trong luồng này **SP là bên phát hành chữ ký**, còn **IdP là consumer**. Vì vậy trình tự đồng bộ hướng ngược lại:

1. SP tạo S-new trong HSM/KMS hoặc kho bí mật được quản trị. Private key không đi vào metadata.
2. SP **công bố S-new public certificate trong SP metadata**, cùng S-old ở giai đoạn overlap; hoặc thông báo/cung cấp certificate cho IdP qua cơ chế quản trị được hỗ trợ.
3. IdP tải/import SP metadata và cấu hình chấp nhận chữ ký AuthnRequest bằng **S-old và S-new**, xác minh được cả hai trong môi trường thử nghiệm.
4. Chỉ sau xác nhận IdP ready, SP chuyển việc ký AuthnRequest/LogoutRequest mới sang S-new.
5. Theo dõi các request/callback còn liên quan đến khóa cũ; giữ khả năng xử lý thông điệp cần thiết trong khoảng hợp lệ.
6. Khi xác nhận không còn consumer/phần tử giao thức phụ thuộc S-old, xóa S-old khỏi SP metadata và khỏi trust list IdP theo lịch đã duyệt, thu hồi/tiêu hủy private key cũ đúng chính sách.

**Sai thứ tự thường gặp:** SP đổi cấu hình keystore để ký ngay bằng S-new, nhưng IdP vẫn đang kiểm tra bằng S-old duy nhất. User nhấn Login, IdP từ chối AuthnRequest trước khi xác thực.

**Lưu ý theo Spring Security:** `RelyingPartyRegistration.signingX509Credentials` chứa credentials của **SP** để ký. Chứng thư public tương ứng phải được IdP nhận trước khi ký thực sự đổi. **Đừng suy đoán chỉ dựa vào thứ tự phần tử trong Collection** rằng Spring Security chắc chắn đã chọn khóa mới; kiểm tra thuật toán và certificate thực tế của request phát ra với phiên bản triển khai.

Một số IdP chỉ cho cấu hình **một** SP signing certificate ở một thời điểm. Trường hợp đó không có seamless overlap chỉ bằng metadata; cần lịch cutover đồng bộ, maintenance window, có cơ chế rollback hoặc kế hoạch dự phòng với phía IdP.

## 6. Khi SP xoay khóa giải mã EncryptedAssertion: vì sao phải giữ private key cũ?

Luồng mã hóa khác với luồng ký. IdP mã hóa dữ liệu cho SP bằng **public encryption certificate** của SP; SP dùng **private decryption key** tương ứng để giải mã.

Một kế hoạch an toàn:

1. SP tạo E-new và lưu private key ở nơi an toàn; xác nhận các instance SP có thể giải mã bằng E-new.
2. SP công bố **E-new public encryption certificate** trong SP metadata, song song với E-old khi hệ thống hỗ trợ.
3. IdP nạp metadata mới và được cấu hình để **chọn E-new khi mã hóa những assertion mới**. Chỉ “nhìn thấy hai encryption certs” chưa xác định khóa nào IdP đang thực sự sử dụng.
4. SP giữ **cả E-old private key lẫn E-new private key** để giải mã các response đang trong quá trình truyền và request tồn đọng trong thời gian chuyển tiếp.
5. Thử login qua mỗi IdP, mỗi node SP, các trường hợp có `EncryptedAssertion`, `EncryptedID` và SLO nếu áp dụng.
6. Xác nhận IdP không còn mã hóa bằng E-old, message tồn đọng đã hết hiệu lực và không còn luồng hợp lệ cần E-old; khi đó mới xóa E-old khỏi metadata và retire private key cũ.

**Lỗi nghiêm trọng:** Sau khi IdP chuyển sang E-new, SP xóa ngay E-old private key. Các encrypted responses đã tạo trước thời điểm đổi nhưng còn đang trong browser/network có thể **không giải mã được**. Dù signature vẫn hợp lệ, authentication vẫn thất bại.

**Khác biệt cần nhớ:** Public certificate công bố trước để bên kia chuẩn bị; private key cũ phải được lưu có kiểm soát cho giai đoạn giải mã overlap. Thời gian retention phải dựa trên TTL/binding/flow thực tế và chính sách lưu trữ khóa; không giữ vô thời hạn.

## 7. Các luồng bổ sung: Logout, artifact, NameID và encryption của IdP

Ngoài đăng nhập Web Browser SSO cơ bản, federation có thể dùng:

- **Single Logout (SLO):** LogoutRequest/LogoutResponse có thể được ký; khi SP hoặc IdP thay signing key phải xác minh SLO với certificate mới và xử lý các message đang tồn đọng.
- **Artifact binding:** có thể có back-channel SOAP và trust/transport credentials riêng; không kết luận chỉ thử HTTP-POST/Redirect là đủ.
- **Encrypted NameID/Attribute:** bên nhận cần private decryption key tương ứng; luồng mã hóa không nhất thiết chỉ là EncryptedAssertion.
- **IdP encryption key:** nếu SP mã hóa dữ liệu gửi tới IdP (theo profile tích hợp), SP cần nạp public encryption cert mới của IdP trước khi bắt đầu mã hóa bằng nó; IdP giữ private decryption key cũ cho message tồn đọng.
- **Metadata signed by federation operator:** nếu khóa ký metadata thay đổi, cần xử lý rotation trust anchor **độc lập** trước khi tiếp tục tin metadata mới.

Lập **ma trận chức năng** theo thực tế dự án; không mặc định mọi SAML federation có SLO, encryption hoặc artifact. Trước khi retire khóa, phải đánh giá **tất cả nơi khóa đó đã được dùng**, không chỉ tính năng login thông thường.

## 8. Thời hạn metadata: validUntil và cacheDuration không giống nhau

Một nguồn gốc gây gián đoạn là SP/IdP có cache metadata, khiến việc công bố khóa mới **không được áp dụng ngay** ở bên tiêu thụ.

| Khái niệm | Ý nghĩa | Khi rollover cần làm gì? |
| --- | --- | --- |
| **cacheDuration** | Khoảng thời gian cache tối ưu trước khi thử refresh lại | Lên lịch publish đủ sớm để consumer tải lại |
| **validUntil** | Thời điểm metadata không còn hợp lệ theo chuẩn | Không dùng bản metadata đã hết hạn để thiết lập trust |
| **HTTP Cache-Control/ETag** | Cơ chế caching HTTP/conditional GET | Kiểm tra proxy/CDN và cache thực tế |
| **Import thủ công** | Quản trị viên tải XML/cert một lần | Cần acknowledgement và lịch deploy cụ thể |
| **Application-level cache** | Spring/cache provider giữ registration snapshot | Cần cache eviction/refresh rõ ràng |
| **Cluster/node cache** | Các node có bản metadata khác thời điểm | Xác minh đủ mọi node trước cutover |

Theo OASIS Errata 05, cache đến hạn chỉ có nghĩa **nên làm mới**; nó không tự làm metadata vô hiệu nếu không có giới hạn hiệu lực khác. Ngược lại, khi `validUntil` tới hạn, metadata **phải bị xem là không hợp lệ**. `validUntil` hiệu lực còn có thể bị giới hạn bởi phần tử cha trong `EntitiesDescriptor`.

Một phương án hoạch định an toàn:

~~~text
T0: IdP publish [I-old, I-new] trong metadata hợp lệ
T1: SP/proxy/IdP consumers refresh theo cacheDuration hoặc manual import
T2: từng consumer xác nhận fingerprint I-new đang được tin và test pass
T3: IdP chuyển signer từ I-old sang I-new
T4: hết cửa sổ in-flight/TTL và xác nhận không còn chữ ký cũ mới tạo
T5: loại I-old khỏi metadata/trust policy sau phê duyệt
~~~

**Không tự đặt một khoảng chờ cố định như “sau 24 giờ thì chắc chắn mọi SP đã refresh”.** Consumer import thủ công có thể chưa đồng bộ dù đã qua 24 giờ hoặc vài ngày. Thời gian chỉ là một điều kiện; điều kiện quan trọng hơn là **xác nhận thực tế của tất cả bên liên quan**.

### Metadata hết validUntil nhưng IdP đang outage?

Không sử dụng bản metadata đã hết `validUntil` chỉ để duy trì login. Có thể dùng **last-known-good** khi metadata vẫn hợp lệ theo chuẩn/chính sách, nhưng không tự mở grace period sau mốc hết hiệu lực. Nếu trust không còn hợp lệ, tạm dừng đăng nhập mới cho registration đó và báo lỗi có kiểm soát.

## 9. Metadata signature: đừng quên nguồn tin cậy trong chính quá trình đổi khóa

Khi một bên gửi metadata công bố signing cert mới, bên kia phải xác minh **metadata xuất phát từ nguồn được phê duyệt**. Nếu kẻ tấn công thay metadata bằng một file chứa public key của mình, mọi signature của attacker sẽ có thể kiểm tra thành công với key giả nếu bên tiêu thụ tự coi file đó là trusted.

Ranh giới tin cậy gồm:

1. **Nguồn metadata:** URL HTTPS được kiểm soát, trust store nội bộ, hoặc artifact được ký qua federation operator.
2. **XML metadata signature (nếu policy yêu cầu):** kiểm tra bằng **metadata-verification credential/trust anchor đã cấu hình từ trước**, không lấy certificate tự cung cấp trong chính metadata làm trust anchor.
3. **EntityID và role:** đúng IdP `IDPSSODescriptor` hoặc SP `SPSSODescriptor`, không chọn entity đầu tiên bất kỳ.
4. **KeyDescriptor/use:** certificate mới dành cho signing hay encryption phải khớp vai trò thực tế.
5. **ValidUntil:** metadata mới còn hiệu lực và các parent constraints được áp dụng.
6. **Ràng buộc tới registration:** không lấy key từ tenant/IdP B rồi đưa vào registration của A.

Spring Security hiện đại có `AssertingPartyMetadataRepository` và triển khai OpenSAML hỗ trợ refresh metadata và xác minh metadata signature bằng credentials được cấu hình. **Nếu không cung cấp verification credentials cho metadata signature validator, không mặc nhiên có XML metadata signature verification**. Việc tin HTTPS endpoint do quản trị phê duyệt là một trust model khác và phải được đánh giá rõ.

**Xoay khóa ký metadata riêng** với khóa ký SAML Response. Khi metadata signer đổi, phải phân phối trust anchor mới tới metadata consumers trước khi họ thẩm định metadata được ký bằng khóa mới.

## 10. Thế nào là “hai phía đã đồng bộ” — tiêu chí phải kiểm chứng được

Đồng bộ không phải “đã gửi email thông báo” hoặc “metadata URL đã đổi”. Một cặp SP–IdP đạt trạng thái **READY_TO_SWITCH** khi:

- **Publisher:** metadata mới đúng entityID, chứa certificate mới theo đúng usage, còn hiệu lực và truy cập được từ nguồn tin cậy.
- **Consumer:** đã import/cập nhật đúng phiên bản metadata/cert, ghi nhận **SHA-256 fingerprint** mong muốn và đúng scope registration.
- **Runtime:** mọi instance đang chạy đã nhận cấu hình, không chỉ một máy hoặc một pod.
- **Protocol:** đã thử chữ ký mã hóa/giải mã bằng khóa mới, đúng binding và luồng giao tiếp thực tế.
- **Security:** chữ ký, audience, issuer, recipient, InResponseTo, time và replay validation vẫn bật.
- **Rollback:** đã thống nhất hành động nếu một consumer lỗi, nhưng không làm sống lại khóa đã bị compromise.

Chỉ khi các điều kiện trên đủ, **bên phát hành chữ ký** mới có thể bật khóa mới. Để **RETIRE_OLD**, cần thêm:

- Không còn message mới được ký/mã hóa bằng khóa cũ.
- In-flight messages, browser sessions và pending requests liên quan đã được xử lý/hết khoảng hiệu lực phù hợp.
- Mọi consumer có bằng chứng vẫn hoạt động khi **khóa cũ được giả lập rút khỏi tập trust** trong môi trường kiểm thử hoặc đã qua canary được giám sát.
- Kết quả kiểm thử SSO/SLO/encryption đúng policy, không có đột biến lỗi signature/decryption.
- Người chịu trách nhiệm SP và IdP xác nhận rollback window, owner và thời điểm retire.
- Khi xử lý khóa compromised, sử dụng **quy trình thu hồi khẩn**, không chờ các điều kiện overlap bình thường.

**Định danh bằng fingerprint** giúp tránh nhầm file `idp-cert-new.pem` được thay đổi ngầm mà tên tệp vẫn giữ nguyên. Chỉ fingerprint không đủ chứng minh nguồn tin cậy; vẫn phải kiểm tra certificate được phê duyệt đúng IdP.

## 11. Spring Security: registration nào chứa những credential nào?

Trong Spring Security SAML2 Login, `RelyingPartyRegistration` mô tả kết nối SP–IdP. Những điểm cần biết:

| API/cấu hình | Credential thuộc ai? | Mục đích |
| --- | --- | --- |
| `assertingPartyMetadata(...).verificationX509Credentials` | **IdP** public certificates | SP xác minh chữ ký Response/Assertion từ IdP |
| `assertingPartyMetadata(...).encryptionX509Credentials` | **IdP** public encryption certs | SP mã hóa dữ liệu gửi cho IdP khi profile cần |
| `RelyingPartyRegistration.signingX509Credentials` | **SP** private key + certificate | SP ký AuthnRequest/SLO messages |
| `RelyingPartyRegistration.decryptionX509Credentials` | **SP** private key + certificate | SP giải mã EncryptedAssertion/NameID |
| `RelyingPartyRegistrations.fromMetadataLocation` | IdP metadata đã tin | Dựng registration từ IdP metadata |
| `InMemoryRelyingPartyRegistrationRepository` | Cấu hình SP/IdP đã dựng | Không tự poll/cập nhật IdP metadata khi IdP đổi |
| `saml2Metadata` | Xuất metadata **SP** | IdP dùng để đăng ký/chấp nhận SP certificate và ACS |

Đừng nhầm `signingX509Credentials` của SP với `verificationX509Credentials` của IdP. Cũng đừng giả định Spring tự chọn active signer theo ngày bắt đầu hiệu lực của cert hay thứ tự metadata; cần kiểm tra hành vi thực tế của provider/version.

### Phiên bản

Ví dụ Java dưới đây theo **Spring Boot 3.x / Spring Security 6.5.x, Servlet, Java 17+**. Các bản Spring Security 7.x tiếp tục có RelyingPartyRegistration nhưng có các thay đổi ở provider/OpenSAML; phải biên dịch và kiểm thử theo BOM dependency thực tế. Spring Security 5.x có API khác, không áp code hiện đại nguyên xi.

## 12. Ví dụ Spring Security: tin hai certificate ký của cùng một IdP

Giả sử SP đang tin `idp-old.crt` và muốn chuẩn bị tin `idp-new.crt`. **Hai file này là certificates X.509 thật đã được phê duyệt cho cùng một IdP**; code không nhận tệp từ browser. Chúng không phải private key và không thuộc SP signing credentials.

Tệp **src/main/java/com/example/security/SamlRolloverConfig.java**:

~~~java
package com.example.security;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlRolloverConfig {

    private static X509Certificate readCertificate(Resource resource)
            throws Exception {
        try (InputStream in = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository(
            @Value("classpath:saml/idp-old.crt") Resource oldCert,
            @Value("classpath:saml/idp-new.crt") Resource newCert)
            throws Exception {

        Saml2X509Credential oldVerifier = Saml2X509Credential
                .verification(readCertificate(oldCert));
        Saml2X509Credential newVerifier = Saml2X509Credential
                .verification(readCertificate(newCert));

        RelyingPartyRegistration corp = RelyingPartyRegistration
                .withRegistrationId("corp")
                .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                .assertionConsumerServiceLocation(
                    "{baseUrl}/login/saml2/sso/{registrationId}")
                .assertingPartyMetadata(idp -> idp
                    .entityId("https://idp.example.test/entity")
                    .singleSignOnServiceLocation(
                        "https://idp.example.test/sso")
                    .wantAuthnRequestsSigned(false)
                    .verificationX509Credentials(credentials -> {
                        credentials.add(oldVerifier);
                        credentials.add(newVerifier);
                    }))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điều kiện để ứng dụng chạy:** Spring Web, Spring Security, `spring-security-saml2-service-provider` phiên bản tương thích; các file cert thật ở `src/main/resources/saml/`; IdP có thật; SP đã đăng ký Entity ID/ACS và ký/mã hóa theo hợp đồng. Mẫu không có SP private key để ký AuthnRequest hoặc giải mã assertion; `wantAuthnRequestsSigned(false)` chỉ minh họa trường hợp IdP **không yêu cầu signed AuthnRequest**. Nếu IdP yêu cầu ký hoặc mã hóa assertion, phải bổ sung SP credentials. Domain `example.test` là minh họa, không phải endpoint hoạt động.

**Mã là class cấu hình trong ứng dụng Spring**, không phải chương trình độc lập với stdout cố định. Nó chỉ mở rộng tập **IdP verification credentials** từ I-old sang I-old + I-new. Đây là **giai đoạn chuẩn bị trước khi IdP đổi signer**.

**Ranh giới quan trọng:** Hai khóa trong mẫu phải thuộc **cùng IdP**. Không đưa certificate của đối tác B vào assertingPartyMetadata của đối tác A chỉ để tránh lỗi `invalid signature`.

### Sau khi chuyển đổi hoàn tất

Khi IdP đã ký bằng I-new, các consumer đã dùng I-new thành công, các flow cũ đã drain và kế hoạch retire được duyệt, mới xóa `oldVerifier` khỏi danh sách rồi deploy/refresh cấu hình theo lịch. **Không chỉnh sửa sớm chỉ vì certificate I-new đã có mặt trong metadata**.

### Nếu IDP metadata được tải từ URL

Thay vì chỉ định cert trực tiếp, `RelyingPartyRegistrations.fromMetadataLocation("https://...")` có thể đọc IdP metadata và dựng registration. Nhưng khi được khởi tạo cùng `InMemoryRelyingPartyRegistrationRepository`, registration đã dựng là snapshot trong bộ nhớ; **không tự động refresh metadata sau mọi lần IdP cập nhật**.

Spring Security còn có `AssertingPartyMetadataRepository` hỗ trợ mô hình load/refresh theo metadata expiry, và `OpenSaml5AssertingPartyMetadataRepository` ở nhánh API tương ứng. Khi dùng cơ chế refresh/caching, phải xác định source trust, cache eviction/TTL, error fallback và thời hạn metadata; không suy đoán URL metadata mới có nghĩa mọi node đang dùng version mới.

## 13. Mở rộng cho SP signing và decryption: khác nhau ở thứ tự dùng khóa

Một số code minh họa builder với các khóa SP:

~~~java
// signing credentials: SP sở hữu cả private key và certificate.
// Các biến spOldSigningKey, spOldSigningCert, spNewSigningKey,
// spNewSigningCert đã được tải từ secret store tin cậy.
builder.signingX509Credentials(creds -> {
    creds.add(Saml2X509Credential.signing(
            spNewSigningKey, spNewSigningCert));
    creds.add(Saml2X509Credential.signing(
            spOldSigningKey, spOldSigningCert));
});

// decryption credentials: trong giai đoạn overlap,
// SP vẫn giữ cả private keys để đọc message đang truyền.
builder.decryptionX509Credentials(creds -> {
    creds.add(Saml2X509Credential.decryption(
            spNewDecryptKey, spNewDecryptCert));
    creds.add(Saml2X509Credential.decryption(
            spOldDecryptKey, spOldDecryptCert));
});
~~~

**Đây là snippet trong code cấu hình có `builder` và credential variables đã được ứng dụng cấp từ KMS/HSM/secret manager**, không phải Java standalone và không thể biên dịch một mình. Nó minh họa **hai collections có vai trò khác nhau**, không phải chỉ dẫn tự động lựa chọn active signing key.

**Điểm cần kiểm tra theo phiên bản:** Ở nhiều implementation, chỉ **một** signing credential được dùng cho message mới (có thể theo thứ tự cấu hình); với decryption có thể thử nhiều credentials để giải mã. Đừng giả định cách chọn khóa ở Spring Security 6.x giống mọi nhánh 5.x/7.x hoặc mọi IdP. **Sau khi thay đổi thứ tự/active key, phải tạo SAMLRequest và xác minh public certificate nào thật sự kiểm tra được chữ ký**.

**Không công bố private key** của SP trong metadata, không log giá trị private-key PEM. SP metadata chỉ công bố public certificate. Private decryption key cũ cần nằm trong secret store an toàn cho đến khi message tồn đọng đã xử lý, sau đó retire có audit.

### Không gộp signing và encryption rotation nếu không cần

Nếu cùng một certificate đang được dùng cho SP signing và encryption, có thể cùng lúc thay public cert, nhưng **quy trình sử dụng lại có hai cutover khác nhau**:

- Signing cutover: SP bắt đầu ký request mới bằng private key mới, IdP phải tin public signing cert mới.
- Encryption cutover: IdP bắt đầu mã hóa response mới bằng public encryption cert mới, SP phải giữ private decrypt key tương ứng.

Bởi vậy nên điều phối hai hạng mục riêng nếu có thể. Tránh xóa private key cũ chỉ vì đường ký đã qua; nó có thể vẫn cần cho giải mã.

## 14. Kiểm tra SP metadata thực sự phát ra

Spring Security có thể công bố SP metadata bằng:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Các đường dẫn tiêu biểu:

- `GET /saml2/metadata`: metadata SP cho các registrations khi khả năng enumeration phù hợp.
- `GET /saml2/metadata/{registrationId}`: metadata SP của registration được chỉ định.
- `GET /saml2/service-provider-metadata/{registrationId}`: đường dẫn tương thích được hỗ trợ.

Có thể dùng:

~~~bash
curl -fsS https://portal.example.test/saml2/metadata/corp
~~~

Đây là **lệnh minh họa**; URL `example.test` không hoạt động nếu không thay bằng SP thật. Trong production cần authentication/authorization phù hợp nếu có chính sách hạn chế công bố metadata và phải đảm bảo URL/HTTPS/Host header do reverse proxy được quản lý đúng.

**Các phép kiểm tra cần làm trên XML thật:**

1. `EntityDescriptor entityID` có đúng định danh SP đã đăng ký tại IdP không?
2. ACS `Location` có trỏ tới HTTPS public URL đúng không?
3. `SPSSODescriptor` có hiển thị signing/encryption KeyDescriptor phù hợp không?
4. Trong giai đoạn overlap, certificate public cũ và mới có được công bố **đúng purpose** không?
5. Certificate nào đang được đưa ra khi có nhiều `RelyingPartyRegistration`?
6. Metadata có được ký theo trust policy mà IdP thực sự hỗ trợ không?
7. Sau mỗi deployment/refresh, IdP đã thực sự **import bản mới** hay chỉ có URL metadata mới?

Không giả định mọi phiên bản Spring Security đều serialise credential list thành metadata giống nhau. **Kiểm tra output thực tế** và thông tin được IdP nhập vào; nếu IdP nhập certificate bằng tay thì endpoint SP metadata cập nhật không có nghĩa IdP đã được cập nhật.

## 15. Java 17 độc lập: mô hình “gate” trước khi loại bỏ khóa cũ

Ví dụ dưới đây mô phỏng **điều kiện retire một signing key bình thường**, không thực hiện SAML/XML Signature hoặc chứng minh trạng thái đối tác từ xa. Đầu vào `confirmed` và `trustedKeyFingerprints` phải đại diện cho **bằng chứng đã được vận hành kiểm chứng** từ từng consumer, không phải lời tự khai của browser.

Tạo tệp **SamlKeyRetirementGateDemo.java**:

~~~java
import java.util.List;
import java.util.Set;

public class SamlKeyRetirementGateDemo {

    record Consumer(String name,
                    Set<String> trustedKeyFingerprints,
                    boolean confirmed) {}

    static String decide(List<Consumer> consumers,
                         String newKey,
                         boolean newSignerActive,
                         boolean oldMessagesDrained) {

        if (consumers.isEmpty() || consumers.stream().anyMatch(
                c -> !c.confirmed()
                    || !c.trustedKeyFingerprints().contains(newKey))) {
            return "WAIT: consumers not ready";
        }

        if (!newSignerActive) {
            return "WAIT: new signer not active";
        }

        if (!oldMessagesDrained) {
            return "WAIT: old messages in flight";
        }

        return "READY: planned retirement permitted";
    }

    public static void main(String[] args) {
        Consumer sp1 = new Consumer(
                "sp1", Set.of("I-old", "I-new"), true);
        Consumer sp2 = new Consumer(
                "sp2", Set.of("I-old", "I-new"), true);
        Consumer staleSp2 = new Consumer(
                "sp2", Set.of("I-old"), false);

        List<Consumer> ready = List.of(sp1, sp2);

        System.out.println(decide(ready, "I-new", true, true));
        System.out.println(decide(
                List.of(sp1, staleSp2), "I-new", true, true));
        System.out.println(decide(ready, "I-new", false, true));
        System.out.println(decide(ready, "I-new", true, false));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac SamlKeyRetirementGateDemo.java
java SamlKeyRetirementGateDemo
~~~

**Stdout chính xác:**

~~~text
READY: planned retirement permitted
WAIT: consumers not ready
WAIT: new signer not active
WAIT: old messages in flight
~~~

Giải thích:

- Case 1: hai consumers đã xác nhận tin I-new, signer mới đang hoạt động, flow cũ đã drain → đạt điều kiện **mô phỏng** để lập lịch retire.
- Case 2: SP2 chưa nạp I-new → phải chờ, dù SP1 đã hoạt động tốt.
- Case 3: chưa chuyển signer sang I-new → chưa được loại I-old.
- Case 4: còn message cũ đang truyền → phải chờ trước khi xóa I-old.

**Không dùng kết quả READY của demo làm approval tự động trong production.** Hệ thống thật còn cần metadata trust validation, issuer/tenant scope, expiration, SSO/SLO tests, canary rollout, chính sách thu hồi, xác nhận của đối tác và audit. Fingerprint trong demo chỉ là chuỗi ký hiệu, không phải fingerprint thực. Không áp dụng logic “chờ” này khi key đã bị lộ: trường hợp đó cần incident response riêng và có thể phải từ chối login cho đến khi khôi phục trust.

## 16. Runbook triển khai: trước, trong và sau cutover

### A. Trước khi công bố khóa mới

1. Lập inventory cho **IdP signing, SP signing, SP decryption, IdP encryption, metadata signing, SLO** theo mỗi federation link.
2. Ghi `registrationId`, IdP `entityID`, SP `entityID`, ACS, binding, hostname và mọi consumer/proxy/node.
3. Ghi fingerprint SHA-256, key ID, mục đích sử dụng, ngày hết hạn, thời hạn metadata và owner.
4. Xác định nơi lưu private key: KMS/HSM/keystore và chính sách backup/restore.
5. Thỏa thuận **dự kiến publish**, thời điểm metadata consumers phải sẵn sàng, giờ cutover, drain window và rollback criteria.
6. Kiểm tra certificate mới có đúng thuật toán/kích thước key/usage theo chính sách; không làm giảm bảo mật.
7. Thử thay cert ở staging với cùng cấu trúc SSO/SLO/encryption và issuer/tenant routing.

### B. Công bố và đồng bộ metadata

1. Publisher thêm public certificate mới cạnh certificate cũ trong metadata hoặc gửi qua cơ chế import được IdP/SP hỗ trợ.
2. Nếu metadata được ký, ký bản mới bằng metadata-signing key mà consumers đang tin; nếu signer metadata cũng được xoay, xử lý trust anchor riêng.
3. Consumer tải lại metadata và xác minh **nguồn, entityID, signature nếu policy yêu cầu, key purpose, validity và fingerprint**.
4. Consumer nạp và áp dụng cấu hình trên mọi node/service/region; xóa cache cũ theo chính sách hoặc rebuild registration.
5. Mỗi consumer phản hồi acknowledgement kèm key fingerprint, metadata version/hash, thời điểm áp dụng và kết quả test.
6. **Không chuyển signer/encryption target** chỉ vì thao tác publish hoàn tất; phải qua kiểm tra readiness.

### C. Cutover có giám sát

1. Chọn canary flow/consumer nếu kiến trúc cho phép.
2. Đổi active signing/encryption behavior tại publisher, **không xóa khóa cũ ngay**.
3. Phát AuthnRequest/SAMLResponse/SLO/EncryptedAssertion mẫu trên môi trường đã kiểm soát để kiểm tra khóa mới.
4. Theo dõi `SignatureException`, `InvalidSignature`, lỗi recipient/audience, decryption errors, login latency và redirect loops.
5. Đối chiếu fingerprint/certificate thực sự dùng để ký/mã hóa thay vì chỉ xem tên file trong cấu hình.
6. Nếu lỗi, dừng mở rộng rollout; rollback về khóa cũ chỉ khi khóa cũ **chưa bị compromise** và còn được phép tin.

### D. Sau cutover và trước retire

1. Xác nhận không tạo thông điệp mới bằng khóa cũ ở tất cả publisher instances.
2. Chờ các request/response hợp lệ đang truyền hết thời hạn xử lý tương ứng.
3. Giám sát login mới và logout, gồm mọi IdP/SP consumers, tenants, vùng triển khai, browser binding và encrypted assertions nếu dùng.
4. Diễn tập bỏ khóa cũ trong staging/canary hoặc config snapshot thử nghiệm; không phá cấu hình toàn bộ traffic trước khi có backup.
5. Lấy phê duyệt của owner SP/IdP và change management.
6. Xóa key cũ khỏi metadata/trust config theo đúng hướng; xóa private key cũ khỏi secret store khi retention không còn yêu cầu; cập nhật audit và runbook.
7. Tiếp tục theo dõi lỗi trong post-change window.

**Tiêu chí hoàn tất:** Không chỉ “hết lịch rollout”, mà là **phía phát không còn dùng khóa cũ + phía nhận đã tin và dùng khóa mới + không còn message hợp lệ cần khóa cũ + metadata phản ánh trạng thái cuối + có bằng chứng kiểm thử**.

## 17. Các sự cố thường gặp khi đồng bộ không đủ

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý an toàn |
| --- | --- | --- |
| SP báo invalid signature ngay sau IdP đổi cert | SP vẫn chỉ tin I-old | Nạp I-new từ nguồn IdP đáng tin, đúng registration, kiểm tra rollout |
| Chỉ một số người dùng login thất bại | Một số node SP dùng metadata cũ | Xác minh fingerprint tại mọi instance/region |
| IdP từ chối AuthnRequest sau SP đổi signing key | IdP chưa import S-new | Đồng bộ SP metadata, xác nhận IdP tin S-new rồi thử |
| EncryptedAssertion không giải mã được sau cutover | SP xóa E-old quá sớm hoặc IdP còn mã hóa bằng E-old | Giữ các private decrypt keys được phép cho overlap, phối hợp IdP |
| SP metadata chứa cả S-old/S-new nhưng IdP vẫn báo unknown key | IdP import thủ công chưa được cập nhật | Kiểm tra trust store thực tế của IdP, không chỉ URL metadata |
| Metadata mới có cert mới nhưng signature metadata lỗi | Trust anchor metadata chưa sẵn sàng | Không thay trusted metadata trước khi xác minh |
| `validUntil` đã hết hạn | Consumer đang dùng metadata không còn hợp lệ | Tạm ngừng trust dựa vào bản expired, lấy metadata mới hợp lệ |
| SSO thành công nhưng SLO thất bại | Quên luồng LogoutRequest/Response được ký | Bổ sung SLO vào test matrix, giữ đúng signing/verification keys |
| Staging hoạt động, production thất bại | Entity IDs, ACS, certs hoặc tenant khác môi trường | So fingerprint + metadata theo đúng environment |
| IdP A dùng được, IdP B hỏng | SP cập nhật trust cho một IdP nhưng chưa tất cả | Lập ma trận per-registration, không trộn keys hai IdP |
| SP đã chuyển signing key nhưng vẫn thấy chữ ký cũ | Một số node/keystore/order chưa cập nhật | Xác minh chữ ký phát ra thực tế ở từng node |
| Sau xoay chứng thư, một ứng dụng trả HTTP 403 | Authentication đã hợp lệ nhưng authorization/role mapping sai | Kiểm tra quyền nghiệp vụ; không tắt SAML signature validation |
| Metadata endpoint có HTTP 200 nhưng consumer không refresh | Cache/ETag/manual import giữ snapshot cũ | Kiểm tra chính sách cache và bằng chứng consumer đã áp dụng |
| Cùng một khóa được dùng cho signing và decryption | Xóa key sau signing cutover phá khả năng decryption | Tách đánh giá mọi usage và lưu giữ key đến khi tất cả luồng đã drain |

**Không chữa lỗi bằng cách:** tắt SAML signature verification; tự tin certificate từ `ds:KeyInfo` của một response chưa kiểm chứng; chấp nhận mọi issuer/audience; sử dụng certificate IdP B như cert dự phòng cho A; nới lỏng metadata `validUntil`; hoặc đưa private key vào metadata công khai.

## 18. Khóa bị lộ: quy trình khẩn cấp khác với rollover thông thường

Nếu private signing/decryption key **có dấu hiệu bị lộ**, duy trì overlap “cho đến khi mọi consumer đồng bộ” có thể tiếp tục cho phép kẻ tấn công lợi dụng khóa cũ.

Phản ứng phù hợp tùy phạm vi và mức độ:

1. Kích hoạt incident response, xác nhận affected key ID/fingerprint, SP/IdP và các message/registrations liên quan.
2. **Ngừng dùng và thu hồi trust đối với khóa bị xâm phạm** sớm nhất theo khả năng triển khai; ưu tiên bảo vệ tính xác thực hơn thông suốt SSO.
3. Thay khóa qua kênh phê duyệt độc lập, thẩm định metadata mới và hướng dẫn consumer cập nhật khẩn.
4. Có thể phải **tạm dừng login/SLO/encryption** phụ thuộc khóa đó cho đến khi hệ thống có trust an toàn.
5. Xem xét replay, phiên đã tạo trong giai đoạn rủi ro, thu hồi session và audit access theo policy.
6. Xóa secrets cũ theo quy trình khẩn, không ghi chúng ra log hoặc ticket.
7. Sau xử lý, rà soát nguyên nhân compromise, quy trình rotation và khả năng phát hiện.

**Phân biệt:** **Planned rollover** ưu tiên overlap và tính liên tục; **compromise revocation** ưu tiên loại bỏ khả năng giả mạo. Không đánh đồng hai bài toán và không dùng điều kiện “old messages drained” để trì hoãn thu hồi khóa bị lộ khi policy yêu cầu khóa phải bị vô hiệu ngay.

## 19. Giám sát, bằng chứng và trách nhiệm

Mỗi đợt rotation nên có một bản ghi change/audit bao gồm:

| Trường | Mục đích |
| --- | --- |
| Federation pair | IdP entityID, SP entityID, registrationId |
| Direction & purpose | IdP signing / SP signing / SP decryption / metadata signing |
| Key fingerprints | SHA-256 fingerprint cũ/mới, không bao gồm private key |
| Metadata source | URL/path được phê duyệt, version/hash, signature verification result |
| Metadata validity | validUntil hữu hiệu và cache refresh status |
| Publisher active key | Key thực tế được dùng trong message mới |
| Consumers readiness | Danh sách đối tác/nodes đã import + test thành công |
| Cutover timestamps | Publish, import, switch, drain complete, retire |
| Test evidence | Response/Request signing, ACS, SLO, decryption, tenant checks |
| Rollback status | Đã thử rollback ra sao nếu khóa chưa compromised |
| Owners and approvals | Người chịu trách nhiệm IdP/SP, change/incident ticket |

Một số metrics **do ứng dụng tự định nghĩa**, không mặc định sẵn trong Spring Security:

- `saml_rotation_peer_ready`: số consumer ready theo federation link.
- `saml_metadata_last_refresh_success_timestamp`: lần nạp metadata gần nhất.
- `saml_metadata_valid_until_timestamp`: hạn metadata còn hiệu lực.
- `saml_signature_verification_failures_total`: số lỗi chữ ký theo registration.
- `saml_decryption_failures_total`: số lỗi giải mã do key mismatch/cipher.
- `saml_signing_fingerprint_observed`: fingerprint key signer thực tế (label/hash phù hợp bảo mật).
- `saml_sso_login_failures_total`: lỗi SSO mới phân loại theo issuer/registration.
- `saml_slo_failures_total`: lỗi Single Logout.

Không ghi raw `SAMLResponse`, NameID, email, attributes hoặc private keys ra production logs. Khi cần fingerprint, có thể dùng SHA-256 trên chứng thư public đã được quản trị chấp nhận; không gửi secret keystore/truststore ra hệ thống giám sát.

## 20. Ma trận kiểm thử trước khi chấp thuận xóa khóa cũ

| Case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| A | IdP ký I-old, SP đang tin I-old + I-new | Response được xác minh nếu các điều kiện SAML khác hợp lệ |
| B | IdP ký I-new, SP đã nạp I-old + I-new | Response được xác minh nếu các điều kiện khác hợp lệ |
| C | IdP ký I-new, một node SP chưa có I-new | Test phải phát hiện node này; **chưa retire I-old** |
| D | SP ký AuthnRequest bằng S-new, IdP mới tin S-old | IdP từ chối; chưa được cutover đến khi IdP ready |
| E | SP ký S-new, IdP tin S-old + S-new | AuthnRequest hợp lệ khi signature/binding đúng |
| F | IdP mã hóa bằng E-old, SP còn E-old + E-new private keys | Giải mã được thông điệp hợp lệ |
| G | IdP mã hóa bằng E-new, SP có E-new private key | Giải mã được; sau đó validate SAML signature |
| H | SP xóa E-old khi còn encrypted response E-old đang truyền | Được phát hiện là failure, không retire sớm |
| I | SLO message ký bằng key mới | Đúng đối tác tin và kiểm tra được chữ ký |
| J | Metadata đã hết `validUntil` | Không dùng metadata expired làm trust |
| K | Metadata bị thay certificate/issuer trái phép | Từ chối candidate mới, không nhận key giả |
| L | Hai IdP dùng cùng Portal nhưng certificate khác | Chỉ tin keys của đúng registration |
| M | Người dùng còn session SP cũ, IdP vừa đổi key | Kiểm tra session policy/step-up; không tự kéo dài quyền |
| N | Tất cả peers báo ready nhưng signer mới chưa hoạt động | Chưa xóa key cũ |
| O | Key cũ bị compromise | Chạy incident revocation, không áp dụng overlap bình thường |

**Phương pháp kiểm thử:** Dùng test IdP/SP và certificate thật đã phê duyệt trong staging; kiểm chứng chữ ký trên request/response theo đúng binding, so audience/issuer/recipient và chạy qua reverse proxy. Không coi một lệnh `curl` lấy metadata hoặc một unit test mock chữ ký là bằng chứng end-to-end.

## 21. Câu hỏi tự kiểm tra

**1. IdP đã công bố certificate mới trong metadata; có thể xóa certificate cũ ngay không?**  
Không. Phải xác nhận mọi SP consumers đã nạp và kiểm tra được khóa mới, IdP đã chuyển signer và không còn message hợp lệ cần khóa cũ.

**2. Tại sao xoay khóa ký SP đòi hỏi IdP nạp metadata SP trước?**  
Vì IdP kiểm chứng AuthnRequest do SP ký. Nếu IdP chỉ biết S-old còn SP đã ký bằng S-new, request sẽ bị từ chối.

**3. Tại sao SP phải giữ cả private decryption key cũ và mới khi IdP đổi encryption certificate?**  
Vì assertion đang trong quá trình truyền có thể được mã hóa bằng public key cũ; chỉ private key cũ mới giải mã được chúng.

**4. cacheDuration đã qua có đồng nghĩa metadata không hợp lệ?**  
Không tự động. Đó là dấu hiệu nên refresh, khác với `validUntil` là giới hạn hiệu lực cứng.

**5. Metadata HTTPS có public key mới; có thể tin ngay mà không kiểm tra entityID và nguồn không?**  
Không. Phải thẩm định nguồn/trust policy, đúng entityID, role, key usage, hiệu lực và XML signature nếu federation yêu cầu.

**6. Một node SP đã đăng nhập được với I-new; đủ bằng chứng retire I-old chưa?**  
Chưa. Cần kiểm tra mọi node/consumer được hỗ trợ, các flow khác và thông điệp tồn đọng.

**7. IdP A có lỗi certificate; có thể dùng certificate của IdP B để kiểm tra không?**  
Không. Chữ ký phải được xác minh bằng các khóa được phép của đúng IdP/registration.

**8. Khóa cũ bị lộ thì có tiếp tục overlap để tránh outage không?**  
Không mặc định. Cần quy trình thu hồi khẩn theo incident policy; có thể phải tạm dừng SSO để bảo vệ danh tính.

**9. Chỉ đổi signing key có cần thử SLO không?**  
Có nếu SLO của hệ thống dùng cùng signing credential; mọi luồng sử dụng khóa phải được inventory và kiểm thử.

**10. Trong Spring Security, `saml2Metadata` xuất metadata của ai?**  
Nó xuất **SP metadata**, giúp IdP biết thông tin SP; nó không tự đồng bộ IdP metadata đang được lưu tại SP.

## 22. Checklist hoàn tất

- [ ] Phân biệt IdP signing, SP signing, SP decryption, IdP encryption, metadata signing và TLS credentials.
- [ ] Xác định toàn bộ SP/IdP consumers, instances, tenants, environments và các binding được dùng.
- [ ] Thu thập fingerprint SHA-256 cũ/mới, metadata source, entityIDs, ACS/SLO, owner và lịch rollout.
- [ ] Công bố public key mới đúng KeyDescriptor `use`, **không công bố private key**.
- [ ] Metadata mới có issuer/role/endpoint chính xác, nguồn/signature/trust hợp lệ và `validUntil` chưa qua.
- [ ] Mỗi consumer đã nạp metadata/cert mới vào đúng registration và xác nhận fingerprint.
- [ ] Thử signed AuthnRequest và signed Response/Assertion trước khi đổi active signer.
- [ ] Nếu có encrypted assertion/NameID, giữ private decryption keys cũ/mới trong transition.
- [ ] Không mặc định browser/cache/app/node cập nhật metadata ngay khi URL thay đổi.
- [ ] Khi IdP/SP đổi signer, xác minh fingerprint của **message mới thực tế**.
- [ ] Thử Single Logout, tenant routing, recipient/audience, InResponseTo và expiry theo cấu hình.
- [ ] Không xóa khóa cũ trước khi mọi consumer sẵn sàng và thông điệp cũ đã drain.
- [ ] Có giám sát signature/decryption failure, refresh age và certificate/metadata expiry.
- [ ] Có rollback và change approval cho planned rollover; có incident response riêng cho key compromise.
- [ ] Không tắt kiểm tra chữ ký, không pha keys giữa các IdP, không kéo dài metadata hết hiệu lực.
- [ ] Sau retire, cập nhật trust config và metadata ở hai phía, xóa secrets cũ an toàn, lưu bằng chứng QA.

## 23. Kết luận

**Đồng bộ metadata hai phía trước khi loại bỏ khóa cũ** là một quy trình nhiều giai đoạn: **công bố key mới → xác minh metadata và import ở consumer → kiểm thử consumer ready → chuyển ký/mã hóa sang key mới → đợi message tồn đọng → retire key cũ có kiểm soát**. Đối với IdP signing, SP phải tin khóa mới trước; đối với SP signing, IdP phải tin khóa mới trước; đối với SP decryption, SP phải giữ cả private keys đến khi IdP ngừng mã hóa bằng khóa cũ.

Trong Spring Security, `RelyingPartyRegistration` và metadata repositories là điểm cấu hình trust, nhưng **mỗi hệ thống vẫn phải tự thiết kế ownership, cache refresh, cutover và monitoring**. Không coi kết quả metadata endpoint có certificate mới là bằng chứng mọi đối tác đã cập nhật; chỉ loại bỏ khóa cũ sau khi có xác nhận qua giao thức thực tế, trừ trường hợp compromise cần thu hồi khẩn.

### Tài liệu chính thức

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata / AssertingPartyMetadataRepository: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing AuthnRequests, signing credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 Javadoc — RelyingPartyRegistration.Builder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html
- OASIS — SAML 2.0 Metadata Interoperability Profile (key rollover): https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop.html
- OASIS — SAML 2.0 Errata 05 (cacheDuration vs validUntil): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- OASIS — SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
