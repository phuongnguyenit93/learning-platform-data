# Giới hạn của ràng buộc theo IP hoặc dấu vết thiết bị

## 1. Vì sao IP và dấu vết thiết bị thường được dùng để chống phát lại?

Khi một bearer token bị đánh cắp, kẻ tấn công có thể gửi lại token từ một máy hoặc mạng khác. Vì vậy, hệ thống đôi khi cố gắn token hoặc phiên đăng nhập với địa chỉ IP, thông tin trình duyệt hay một dấu vết thiết bị (device fingerprint). Nếu request sau có IP hoặc fingerprint khác request ban đầu, hệ thống có thể nghi ngờ token đã bị sao chép.

Ý tưởng này có ích như một **tín hiệu rủi ro**, nhưng có giới hạn lớn:

- IP có thể thay đổi trong một phiên hợp lệ hoặc được chia sẻ bởi nhiều người dùng.
- Fingerprint có thể thay đổi sau cập nhật phần mềm và có thể bị giả lập.
- Kẻ tấn công có thể dùng cùng VPN, proxy, mạng doanh nghiệp hoặc môi trường trình duyệt tương tự nạn nhân.
- Việc thu thập fingerprint có thể ảnh hưởng quyền riêng tư và tạo khả năng theo dõi người dùng.

Do đó, IP và device fingerprint không chứng minh mật mã rằng request đến từ đúng thiết bị đã nhận token. Chúng không tương đương với sender-constrained token, trong đó client phải chứng minh đang sở hữu khóa riêng hoặc chứng thư được ràng buộc với token.

Với JWT, một claim chứa IP hoặc fingerprint cũng không tự tạo ra cơ chế chống replay an toàn. Nếu hệ thống quyết định dùng các tín hiệu này, cần xác định rõ chúng chỉ phục vụ phát hiện bất thường, khi nào được phép từ chối, và cách xử lý khi dữ liệu thay đổi hợp lệ.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Chống phát lại. Phạm vi là bảo mật token tổng quát, không phụ thuộc Java, Spring Security hoặc nền tảng cụ thể.

## 2. Phân biệt ba khái niệm: tín hiệu, binding và proof-of-possession

Các cơ chế thường bị gọi chung là “device binding” nhưng mức bảo đảm rất khác nhau:

| Cơ chế | Dữ liệu được kiểm tra | Mức bảo đảm |
| --- | --- | --- |
| IP reputation / IP consistency | Địa chỉ IP, ASN, vùng mạng hoặc lịch sử truy cập | Tín hiệu rủi ro; không xác định duy nhất người dùng hay thiết bị |
| Device/browser fingerprint | Tập thuộc tính phần cứng, hệ điều hành, trình duyệt và môi trường | Tín hiệu xác suất; có thể thay đổi hoặc bị giả lập |
| Stored session context | Thông tin phiên đã ghi nhận phía máy chủ | Có thể phát hiện thay đổi ngữ cảnh; vẫn phụ thuộc chất lượng tín hiệu và trạng thái lưu trữ |
| Cryptographic sender constraint | Chữ ký proof bằng private key hoặc chứng thư client | Bằng chứng request có quyền sử dụng khóa tương ứng, nếu xác minh đúng |

**Binding dựa trên IP/fingerprint** thường là phép so sánh dữ liệu quan sát được. **Proof-of-possession** là phép kiểm tra mật mã chứng minh bên gửi có private key tương ứng.

Một hệ thống có thể kết hợp các cơ chế: dùng IP/fingerprint để đánh giá rủi ro, đồng thời dùng DPoP hoặc mTLS để ràng buộc token với khóa. Không nên nâng một tín hiệu xác suất thành bằng chứng xác thực mạnh.

## 3. Giới hạn của ràng buộc theo địa chỉ IP

### 3.1. Nhiều người dùng có thể dùng chung một IP

Địa chỉ IP công khai thường đại diện cho điểm thoát mạng, không phải một người dùng hay một thiết bị. Nhiều người có thể cùng xuất hiện dưới một IP:

- Mạng văn phòng hoặc trường học dùng NAT.
- Nhiều thuê bao di động đi qua carrier-grade NAT (CGNAT).
- Gia đình hoặc không gian công cộng dùng chung router.
- Người dùng của một VPN hoặc proxy cùng đi qua một egress IP.
- Nhiều workload trong cloud dùng chung NAT gateway.

Nếu một hệ thống coi IP là định danh duy nhất, các request hợp lệ của nhiều người có thể bị gộp thành một thiết bị. Ngược lại, kẻ tấn công có thể ở cùng mạng hoặc cùng VPN với nạn nhân nên phép so sánh IP vẫn khớp.

### 3.2. IP có thể thay đổi trong một phiên hợp lệ

Một người dùng hợp lệ có thể đổi IP mà không đổi thiết bị hoặc phiên:

- Điện thoại chuyển giữa Wi-Fi và mạng di động.
- Thiết bị di chuyển giữa các trạm di động.
- Nhà cung cấp Internet cấp địa chỉ động.
- VPN tự đổi máy chủ hoặc vùng thoát.
- Kết nối IPv4 và IPv6 được chọn khác nhau giữa các request.
- Mạng doanh nghiệp chuyển tuyến hoặc failover sang egress khác.

Ràng buộc cứng theo địa chỉ IP chính xác có thể khiến token hợp lệ bị từ chối giữa phiên. Điều này tạo false positive và gây trải nghiệm đăng nhập không ổn định.

### 3.3. Địa chỉ IP không chứng minh vị trí địa lý chính xác

IP geolocation thường chỉ ước lượng quốc gia, khu vực, thành phố hoặc nhà cung cấp mạng. Dữ liệu có thể sai hoặc không cập nhật. IP của VPN, proxy, cloud và mạng di động có thể xuất hiện ở nơi khác vị trí thực của người dùng.

Không nên suy luận rằng một request chắc chắn đến từ một thành phố hoặc quốc gia chỉ dựa trên IP. “Impossible travel” hoặc thay đổi quốc gia trong thời gian ngắn có thể là tín hiệu điều tra, nhưng cũng có thể do VPN, định tuyến hoặc dữ liệu định vị không chính xác.

### 3.4. Prefix binding cũng có đánh đổi

Một số hệ thống so khớp subnet hoặc prefix thay vì IP chính xác, ví dụ chỉ so phần mạng IPv4 hoặc một prefix IPv6. Cách này giảm một số false positive khi địa chỉ thay đổi trong cùng mạng, nhưng:

- Nhiều người dùng vẫn chia sẻ prefix.
- Người dùng hợp lệ có thể đổi sang prefix khác.
- Kẻ tấn công có thể ở cùng mạng hoặc cùng dải egress.
- Prefix quá rộng làm giảm khả năng phân biệt; prefix quá hẹp lại gây từ chối nhầm.

Không có một độ dài prefix phù hợp cho mọi nhà mạng, tổ chức và mô hình triển khai. Nếu dùng prefix, cần dựa trên dữ liệu vận hành, đánh giá rủi ro và không coi nó là cơ chế xác thực độc lập.

## 4. Proxy, VPN và nguồn IP không đáng tin cậy

### 4.1. Header chuyển tiếp không mặc nhiên là IP thật

Ứng dụng thường chạy sau reverse proxy, load balancer, CDN hoặc API gateway. Khi đó, địa chỉ kết nối trực tiếp mà ứng dụng nhìn thấy có thể là proxy. Một số hạ tầng chuyển tiếp địa chỉ client qua header như Forwarded hoặc X-Forwarded-For.

Các header này có thể bị client tự gửi hoặc giả mạo nếu proxy không loại bỏ và ghi đè chúng đúng cách. Nếu ứng dụng lấy phần tử đầu tiên của X-Forwarded-For mà không xác định chuỗi proxy tin cậy, kẻ tấn công có thể tự khai một IP bất kỳ.

Quy tắc an toàn:

1. Chỉ tin header IP forwarding từ proxy/gateway đã được cấu hình tin cậy.
2. Proxy biên phải xóa giá trị do client gửi và ghi lại header theo quy tắc chuẩn.
3. Xác định rõ thứ tự và số hop của chuỗi proxy.
4. Chỉ lấy client address sau khi xử lý chuỗi từ các proxy tin cậy.
5. Không dùng header forwarding làm bằng chứng xác thực; nó chỉ là nguồn tín hiệu mạng đã được chuẩn hóa.

### 4.2. VPN, proxy và Tor

VPN hoặc proxy có thể làm nhiều thiết bị xuất hiện dưới cùng IP, hoặc làm một thiết bị xuất hiện dưới nhiều IP. Một kẻ tấn công có thể chủ động chọn VPN/proxy gần với mạng của nạn nhân để làm giảm khác biệt.

Việc phát hiện IP thuộc VPN, hosting hoặc Tor có thể là tín hiệu rủi ro, nhưng không đủ để kết luận người dùng độc hại. Nhiều người dùng hợp lệ cần VPN vì công việc, quyền riêng tư hoặc chính sách mạng.

Không nên tự động khóa tài khoản chỉ vì phát hiện VPN/proxy. Có thể kết hợp tín hiệu này với bất thường khác và yêu cầu xác thực tăng cường.

## 5. Giới hạn của device fingerprint

Device fingerprint là tập hợp thuộc tính được quan sát từ thiết bị hoặc môi trường client. Trong trình duyệt, các thuộc tính có thể gồm:

- User-Agent hoặc Client Hints.
- Hệ điều hành, phiên bản trình duyệt.
- Kích thước màn hình, độ phân giải hoặc khả năng hiển thị.
- Ngôn ngữ, múi giờ và cấu hình vùng.
- Danh sách font, khả năng đồ họa hoặc đặc điểm canvas/WebGL.
- Khả năng API, codec, thiết bị đầu vào hoặc đặc điểm runtime.
- Một số tín hiệu mạng và hành vi tương tác.

Kết hợp nhiều thuộc tính có thể tạo ra một dấu vết tương đối đặc trưng tại một thời điểm. Tuy nhiên, nó không phải một khóa bí mật và không có bằng chứng rằng chỉ thiết bị ban đầu mới có thể tạo ra tập thuộc tính đó.

### 5.1. Fingerprint thay đổi theo thời gian

Fingerprint có thể thay đổi khi:

- Trình duyệt hoặc hệ điều hành được cập nhật.
- Người dùng cài extension hoặc thay đổi cấu hình.
- Độ phân giải màn hình, ngôn ngữ hoặc múi giờ thay đổi.
- Người dùng bật chế độ riêng tư hoặc tính năng chống fingerprinting.
- Thiết bị chuyển giữa màn hình, GPU hoặc môi trường hiển thị khác.
- Nhà cung cấp trình duyệt giảm độ chi tiết hoặc chuẩn hóa các API.

Vì vậy, cùng một thiết bị có thể tạo fingerprint khác nhau giữa hai lần truy cập. Nếu dùng fingerprint chính xác làm điều kiện bắt buộc, người dùng hợp lệ có thể bị yêu cầu đăng nhập lại hoặc bị khóa nhầm.

### 5.2. Fingerprint có thể bị giả lập

Kẻ tấn công có thể:

- Sao chép User-Agent, ngôn ngữ, múi giờ và các thuộc tính dễ điều khiển.
- Dùng cùng hệ điều hành, trình duyệt hoặc cấu hình phổ biến.
- Chạy trình duyệt tự động hoặc môi trường ảo với thuộc tính đã điều chỉnh.
- Dùng công cụ sửa đổi hoặc chuẩn hóa fingerprint.
- Chiếm quyền trên chính thiết bị hợp lệ, khi đó fingerprint vẫn có thể giống hoàn toàn.

Fingerprint có nhiều thuộc tính hơn không đồng nghĩa có bảo đảm mật mã cao hơn. Một tập thuộc tính có độ phân biệt cao vẫn có thể được sao chép hoặc phát lại nếu không có private key và challenge-response.

### 5.3. Fingerprint không phải device identity

Fingerprint là phép đo các đặc điểm quan sát được. Device identity có thể dựa trên một khóa mật mã được tạo và giữ trong phần cứng bảo mật hoặc kho khóa của nền tảng.

| Thuộc tính | Fingerprint | Khóa thiết bị |
| --- | --- | --- |
| Có private secret không? | Không | Có private key |
| Có thể chứng minh sở hữu bằng chữ ký? | Không | Có |
| Có thể thay đổi sau cập nhật? | Thường có | Có thể ổn định hơn, nhưng vẫn có vòng đời riêng |
| Có thể sao chép thuộc tính? | Thường có thể | Private key có thể được bảo vệ để khó xuất |
| Mục đích phù hợp | Tín hiệu rủi ro và nhận diện xác suất | Sender constraint hoặc xác thực thiết bị |

Ngay cả khóa thiết bị cũng cần quản lý vòng đời, đăng ký, thu hồi và bảo vệ khỏi malware hoặc compromise. Tuy nhiên, proof bằng private key cung cấp loại bằng chứng khác hẳn so với việc so sánh fingerprint.

## 6. Quyền riêng tư và rủi ro theo dõi

Fingerprinting có thể tạo ra định danh bền vững ngay cả khi người dùng xóa cookie hoặc chuyển sang chế độ duyệt riêng tư. Việc kết hợp nhiều thuộc tính để nhận diện người dùng có thể làm tăng khả năng theo dõi xuyên phiên hoặc xuyên dịch vụ.

Khi thiết kế cơ chế này, cần xem xét:

- Mục đích thu thập có cụ thể và cần thiết không?
- Có thể đạt mục tiêu bằng tín hiệu ít xâm lấn hơn không?
- Có cần lưu fingerprint đầy đủ hay chỉ cần kết quả rủi ro?
- Thời hạn lưu có giới hạn không?
- Có chia sẻ dữ liệu giữa các dịch vụ hoặc bên thứ ba không?
- Người dùng được thông báo và có quyền kiểm soát nào theo quy định áp dụng?
- Có cơ chế truy cập, xóa hoặc xử lý dữ liệu theo chính sách quyền riêng tư không?

Địa chỉ IP và fingerprint có thể được xem là dữ liệu cá nhân hoặc dữ liệu có khả năng nhận diện theo pháp luật áp dụng. Hash một fingerprint không tự động làm dữ liệu trở thành vô danh; giá trị hash ổn định vẫn có thể được dùng để liên kết hoạt động.

Áp dụng nguyên tắc data minimization: chỉ thu thập tín hiệu cần thiết, giới hạn mục đích và thời gian lưu, kiểm soát quyền truy cập và tránh chia sẻ fingerprint thô không cần thiết.

## 7. Vì sao không nên nhúng IP hoặc fingerprint thô vào JWT?

JWT JWS thông thường chỉ bảo vệ tính toàn vẹn, không che giấu nội dung payload. Bên giữ token có thể decode header và payload. Nếu nhúng địa chỉ IP, fingerprint, thông tin phần cứng hoặc dữ liệu định danh vào JWT, các giá trị đó có thể bị lộ khi token được lưu, truyền hoặc ghi log sai cách.

Nhúng một giá trị vào JWT cũng không giải quyết được việc nó thay đổi:

- Nếu IP thay đổi, token có thể bị từ chối dù người dùng hợp lệ.
- Nếu fingerprint thay đổi, token có thể bị từ chối sau cập nhật.
- Nếu attacker sao chép cả token và tái tạo được tín hiệu tương tự, binding vẫn bị vượt qua.
- Nếu cần thay đổi hoặc thu hồi binding, JWT đã phát hành không thể sửa mà vẫn giữ chữ ký cũ.

Một thiết kế thường phù hợp hơn là giữ tín hiệu rủi ro và session context ở phía máy chủ, gắn với session hoặc token family. Nếu cần đưa claim binding vào token theo một profile cụ thể, phải xác định rõ semantics, privacy, audience và cơ chế xác minh; không tự coi claim tùy biến là tiêu chuẩn chống replay.

## 8. Dùng IP và fingerprint như tín hiệu rủi ro

IP và device fingerprint có thể giúp phát hiện thay đổi bất thường khi được dùng kết hợp với ngữ cảnh khác:

- IP hoặc ASN thay đổi đột ngột so với lịch sử phiên.
- Một token xuất hiện ở nhiều vùng mạng trong khoảng thời gian không hợp lý.
- Cùng một refresh token được sử dụng từ các môi trường khác nhau.
- Fingerprint thay đổi đồng thời với user agent, session hoặc hành vi bất thường.
- Nhiều request nhạy cảm xuất hiện từ môi trường mới.
- Tốc độ hoặc tần suất request khác xa hành vi bình thường.

Những tín hiệu này chỉ làm tăng hoặc giảm mức rủi ro. Chúng không đủ để kết luận token đã bị đánh cắp. Một thay đổi IP đơn lẻ có thể là roaming di động; một fingerprint mới có thể là bản cập nhật trình duyệt.

### 8.1. Ví dụ policy risk-based

~~~yaml
sessionRiskPolicy:
  ipChange:
    weight: low
    action: record_signal
  newNetworkAsn:
    weight: medium
    action: combine_with_other_signals
  deviceFingerprintDrift:
    weight: low
    action: record_signal
  impossibleTravel:
    weight: medium
    action: step_up_if_confirmed
  cryptographicProofFailure:
    weight: critical
    action: reject_request
  confirmedRefreshTokenReuse:
    weight: critical
    action: revoke_token_family
~~~

Đây chỉ là ví dụ cách phân loại hành động, không phải thang điểm chuẩn. Không nên cộng điểm cơ học mà không đánh giá tương quan giữa các tín hiệu. Một IP mới và ASN mới có thể cùng xuất phát từ một lần chuyển VPN, không nhất thiết là hai bằng chứng độc lập.

### 8.2. Các hành động phản ứng theo mức rủi ro

| Mức độ | Ví dụ phản ứng |
| --- | --- |
| Thấp | Ghi nhận tín hiệu, tiếp tục request và theo dõi |
| Trung bình | Yêu cầu step-up authentication hoặc xác nhận thiết bị |
| Cao | Giới hạn tốc độ, yêu cầu xác thực lại hoặc chặn thao tác nhạy cảm |
| Rất cao, có bằng chứng bổ sung | Từ chối request, thu hồi session/token family và phát cảnh báo |

Không tự động thu hồi toàn bộ phiên chỉ vì IP hoặc fingerprint thay đổi. Trước khi áp dụng hành động mạnh, cần xem xét mức nhạy cảm của thao tác, tín hiệu độc lập, khả năng false positive và cách khôi phục tài khoản hợp lệ.

## 9. So sánh với sender-constrained token

Nếu mục tiêu là giảm khả năng sử dụng token bị đánh cắp từ một client khác, cơ chế sender constraint cung cấp bằng chứng mạnh hơn IP/fingerprint.

### 9.1. DPoP

DPoP (RFC 9449) ràng buộc Access Token với một public key của client. Client tạo một JWT proof và ký bằng private key tương ứng cho request. Resource Server kiểm tra chữ ký proof, public key thumbprint khớp claim cnf của Access Token, HTTP method, URI, thời gian, jti và các điều kiện profile khác.

Nếu attacker chỉ sao chép Access Token mà không có private key, họ không thể tạo proof hợp lệ cho request mới. DPoP vẫn cần chống replay proof, kiểm tra nonce khi áp dụng và bảo vệ private key của client.

### 9.2. Mutual-TLS certificate-bound token

OAuth mutual-TLS (RFC 8705) có thể ràng buộc Access Token với chứng thư client. Resource Server xác minh kết nối TLS client certificate và so khớp thumbprint với claim cnf trong token.

Kẻ tấn công chỉ có bearer token nhưng không có private key của chứng thư sẽ không thể thiết lập kết nối TLS phù hợp. Cần triển khai đúng TLS termination và proxy trust để chứng thư được xác minh thực sự.

### 9.3. Khóa thiết bị và WebAuthn/passkeys

Một ứng dụng có thể đăng ký public key của thiết bị hoặc sử dụng WebAuthn/passkey để yêu cầu chữ ký trên challenge. Server xác minh chữ ký bằng public key đã đăng ký. Đây là bằng chứng sở hữu khóa, khác với việc đoán thiết bị từ fingerprint.

WebAuthn chủ yếu dùng để xác thực người dùng hoặc step-up theo challenge; không tự động biến mọi JWT thành sender-constrained token. Nếu muốn ràng buộc từng request API với khóa, cần giao thức token binding/PoP phù hợp.

## 10. Lựa chọn cơ chế theo mục tiêu

| Mục tiêu | Cơ chế nên xem xét | Vai trò của IP/fingerprint |
| --- | --- | --- |
| Phát hiện đăng nhập từ mạng mới | Risk engine, IP/ASN reputation, lịch sử phiên | Tín hiệu phụ |
| Phát hiện token được dùng ở nhiều môi trường | Session telemetry, replay store, anomaly detection | Tín hiệu phụ |
| Ngăn bearer token bị dùng từ client không giữ khóa | DPoP hoặc mTLS | Không thay thế proof |
| Bảo vệ refresh token public client | Rotation/reuse detection hoặc sender constraint theo RFC 9700 | Không thay thế hai cơ chế này |
| Xác thực lại thao tác nhạy cảm | WebAuthn/passkey hoặc step-up authentication | Có thể bổ sung ngữ cảnh rủi ro |
| Phát hiện phiên bị chiếm quyền | Kết hợp telemetry, session state, proof-of-possession và hành vi | Một trong nhiều tín hiệu |

Không có một cơ chế phù hợp cho mọi hệ thống. Hãy bắt đầu từ mục tiêu: phát hiện bất thường, ngăn replay, ràng buộc client hay xác thực lại người dùng. Sau đó chọn bằng chứng tương ứng.

## 11. Mã giả đánh giá IP/fingerprint mà không biến chúng thành bằng chứng xác thực

~~~text
function evaluateRequestRisk(request, session, verifiedTokenContext):
    require verifiedTokenContext exists

    signals = []

    clientIp = resolveClientIpFromTrustedProxyChain(request)
    if clientIp is unknown:
        signals.add("ip_unavailable")
    else if networkContextChanged(clientIp, session.previousNetwork):
        signals.add("network_changed")

    fingerprint = collectPermittedDeviceSignals(request)
    if fingerprint is available:
        if fingerprintDriftIsSignificant(fingerprint, session.deviceProfile):
            signals.add("device_profile_changed")

    if unusualTravelPattern(signals, session.history):
        signals.add("travel_anomaly")

    if senderConstraintIsRequired(verifiedTokenContext.policy):
        require cryptographicProofIsValid(request, verifiedTokenContext)

    risk = evaluateSignalsWithCalibratedPolicy(signals, session.history)

    if risk is LOW:
        return ALLOW_WITH_MONITORING
    if risk is MEDIUM:
        return REQUIRE_STEP_UP
    if risk is HIGH:
        return RESTRICT_SENSITIVE_ACTIONS
    return REJECT_AND_INVESTIGATE
~~~

Đây là pseudocode khái quát. Hàm đánh giá phải dùng tín hiệu được thu thập hợp pháp, có giới hạn và được hiệu chỉnh trên dữ liệu vận hành. Kết quả risk không được ghi đè kết quả xác minh chữ ký, claims hoặc proof-of-possession.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Coi IP là định danh thiết bị | Nhiều người dùng bị gộp; người dùng hợp lệ bị khóa | Dùng IP như tín hiệu mạng |
| Ràng buộc cứng với IP chính xác | Roaming, NAT hoặc VPN làm request hợp lệ thất bại | Risk-based policy và step-up |
| Coi cùng IP là bằng chứng cùng người | Attacker dùng cùng VPN/NAT vẫn khớp | Dùng proof mật mã khi cần sender constraint |
| Tin X-Forwarded-For từ client | Attacker giả mạo địa chỉ nguồn | Chỉ tin proxy đã cấu hình và ghi đè header |
| Coi geolocation là vị trí chính xác | Khóa nhầm do dữ liệu định vị sai | Dùng như tín hiệu xác suất |
| Dùng fingerprint làm secret | Fingerprint có thể sao chép hoặc giả lập | Dùng khóa thiết bị và challenge-response |
| Fingerprint quá chi tiết, lưu lâu | Tăng rủi ro theo dõi và vi phạm quyền riêng tư | Data minimization, retention limit |
| Nhúng fingerprint/IP thô vào JWT | Lộ dữ liệu và khó cập nhật binding | Lưu context tối thiểu phía máy chủ |
| Thu hồi phiên chỉ vì fingerprint drift | False positive và khóa người dùng hợp lệ | Kết hợp tín hiệu, step-up và quy trình khôi phục |
| Dùng fingerprint thay DPoP/mTLS | Không có bằng chứng sở hữu private key | Dùng sender-constrained token |
| Bỏ qua NAT và mạng di động | Tỷ lệ từ chối hợp lệ cao | Kiểm thử nhiều loại mạng |

## 13. Ma trận kiểm thử

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| IP ổn định | Request liên tiếp cùng IP | Không tự suy ra danh tính; chỉ là tín hiệu nhất quán |
| NAT/CGNAT | Nhiều người dùng cùng IP công khai | Không gộp thành một chủ thể |
| Roaming | Điện thoại chuyển Wi-Fi sang 4G/5G | Không tự động từ chối phiên hợp lệ |
| Dynamic IP | ISP đổi địa chỉ trong phiên | Áp dụng risk policy, không khóa cứng |
| VPN | Người dùng hợp lệ đổi VPN endpoint | Ghi nhận tín hiệu và đánh giá theo ngữ cảnh |
| Proxy spoofing | Client tự gửi X-Forwarded-For giả | Proxy biên loại bỏ/ghi đè; ứng dụng không tin giá trị giả |
| IPv4/IPv6 | Request luân phiên giữa hai stack | Không coi khác địa chỉ là bằng chứng token bị đánh cắp |
| Fingerprint drift | Browser update hoặc thay đổi màn hình | Cho phép drift hợp lý hoặc step-up |
| Fingerprint spoofing | Attacker mô phỏng User-Agent và thuộc tính | Không coi fingerprint khớp là proof |
| Privacy mode | Browser giảm/chuẩn hóa fingerprint | Không tạo false positive nghiêm trọng |
| Token theft | Attacker có token nhưng không có private key DPoP | Proof bị từ chối |
| Token theft + same VPN | Attacker cùng IP egress với nạn nhân | IP không được coi là đủ để chấp nhận |
| mTLS | Token ràng buộc chứng thư nhưng client dùng cert khác | Từ chối |
| Risk engine | Một tín hiệu yếu thay đổi | Không tự động revoke toàn bộ session |
| Privacy | Fingerprint lưu quá thời hạn | Chính sách retention xóa hoặc rút gọn dữ liệu |

Nên kiểm thử cả false positive và false negative. Một hệ thống chỉ đo số lần phát hiện attacker mà không đo số người dùng hợp lệ bị chặn sẽ đánh giá sai hiệu quả của cơ chế.

## 14. Checklist thiết kế

1. [ ] IP được xem là tín hiệu mạng, không phải định danh người dùng hoặc thiết bị.
2. [ ] Không ràng buộc cứng IP chính xác cho mọi phiên nếu không có yêu cầu đặc biệt đã đánh giá.
3. [ ] Có xử lý NAT, CGNAT, mạng di động, VPN, proxy, IPv4/IPv6 và IP động.
4. [ ] Chỉ tin địa chỉ client từ proxy chain đã cấu hình; header do client gửi bị loại bỏ/ghi đè.
5. [ ] Geolocation và ASN chỉ là tín hiệu xác suất.
6. [ ] Fingerprint không được coi là secret hoặc bằng chứng sở hữu thiết bị.
7. [ ] Có giới hạn thu thập, mục đích, retention, truy cập và chia sẻ fingerprint/IP.
8. [ ] Không nhúng dữ liệu IP/fingerprint thô vào JWT nếu không có nhu cầu và profile rõ ràng.
9. [ ] Dùng session context phía máy chủ nếu cần theo dõi thay đổi tín hiệu.
10. [ ] Một tín hiệu yếu không tự động dẫn tới revoke hoặc khóa tài khoản.
11. [ ] Có step-up authentication cho trường hợp rủi ro tăng.
12. [ ] Khi cần chống token theft/replay mạnh, dùng DPoP, mTLS hoặc khóa thiết bị thay vì fingerprint.
13. [ ] Refresh token public client được bảo vệ bằng rotation/reuse detection hoặc sender constraint theo RFC 9700.
14. [ ] Có kiểm thử false positive/false negative trên nhiều loại mạng và thiết bị.

## 15. Tài liệu tiêu chuẩn liên quan

- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token và sender-constrained token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc Access Token với khóa client và proof cho request.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc token với chứng thư client.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT và claims; không định nghĩa IP/device fingerprint như cơ chế chống replay phổ quát.
- **W3C Web Authentication (WebAuthn):** xác thực dựa trên credential khóa công khai và challenge.
- **W3C Privacy Principles:** nguyên tắc giảm thiểu dữ liệu và hạn chế nhận diện/theo dõi người dùng.

**Nguyên tắc ghi nhớ:** IP và device fingerprint chỉ cho biết request có giống môi trường đã thấy trước đó hay không; chúng không chứng minh ai đang giữ token. Hãy dùng chúng như tín hiệu rủi ro có giới hạn, xử lý thay đổi hợp lệ bằng policy thích ứng và dùng DPoP, mTLS hoặc khóa thiết bị khi cần bằng chứng mật mã về quyền sở hữu credential.
