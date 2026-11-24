# Credential expiration

**Credential expiration** là việc một credential mất hiệu lực sau một thời điểm, thời hạn hoặc điều kiện được xác định bởi giao thức và chính sách của hệ thống. Hết hạn giới hạn khoảng thời gian một password, certificate, API key, recovery code, refresh token hoặc phương thức xác thực được phép sử dụng. Mục tiêu là giảm thời gian một credential bị lộ có thể bị lạm dụng, loại bỏ credential cũ không còn phù hợp và buộc hệ thống đánh giá lại quyền kiểm soát theo vòng đời.

Không phải credential nào cũng có ngày hết hạn được định nghĩa sẵn. X.509 certificate có trường thời gian hiệu lực; access token thường có claim hết hạn; recovery code có thể dùng một lần. Password, passkey, TOTP seed hoặc API key có thể tồn tại cho tới khi được thay đổi hay thu hồi, trừ khi hệ thống áp dụng thời hạn riêng. Vì vậy, thiết kế expiration phải dựa trên loại credential, khả năng thu hồi, mức rủi ro, cách phân phối và khả năng gia hạn.

Bài học thuộc chương **Credential lifecycle** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Người học cần phân biệt expiration với rotation, renewal, revocation và session timeout; thiết kế thời hạn theo loại credential; triển khai gia hạn an toàn; xử lý credential hết hạn trong hệ thống phân tán; và tránh làm gián đoạn người dùng hoặc workload hợp lệ.

Điểm cốt lõi: **hết hạn là một điều kiện hiệu lực, không phải bằng chứng rằng credential chưa từng bị lộ**. Một certificate còn hạn vẫn có thể đã bị compromise; một password chưa tới ngày hết hạn vẫn có thể bị đánh cắp. Hệ thống phải hỗ trợ thu hồi khẩn cấp và phản ứng theo rủi ro, không chỉ dựa vào lịch hết hạn.

## 1. Credential expiration là gì?

Credential là dữ liệu hoặc phương tiện được dùng để chứng minh quyền kiểm soát trong một lần xác thực hoặc để xin quyền truy cập. Credential expiration xác định thời điểm hoặc điều kiện mà hệ thống không còn chấp nhận credential đó.

Ví dụ:

- Một client certificate chỉ hợp lệ trong khoảng thời gian ghi ở trường `notBefore` và `notAfter`.
- Một access token có claim `exp`; sau thời điểm đó resource server phải từ chối token.
- Một recovery code chỉ dùng một lần và có thể có thêm thời hạn.
- Một API key được cấp cho integration trong 90 ngày theo policy nội bộ.
- Một password không có trường `expiresAt` trong bản thân password verifier, nhưng hệ thống có thể yêu cầu thay đổi theo policy hoặc khi phát hiện compromise.

Expiration cần được kiểm tra tại nơi sử dụng credential. Việc hiển thị ngày hết hạn trong giao diện hoặc gửi email nhắc nhở không tự làm credential mất hiệu lực.

### 1.1. Các khái niệm liên quan

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Expiration** | Credential hết hiệu lực theo thời gian hoặc điều kiện. | Certificate qua `notAfter`. |
| **Rotation** | Thay credential hiện tại bằng credential mới theo quy trình có overlap hoặc chuyển đổi. | Thay API key đang dùng bằng key mới. |
| **Renewal** | Gia hạn hoặc cấp lại credential để tiếp tục sử dụng. | Cấp certificate mới trước khi certificate cũ hết hạn. |
| **Revocation** | Thu hồi credential trước hoặc sau ngày hết hạn vì không còn được tin cậy. | Thu hồi certificate bị lộ private key. |
| **Suspension** | Tạm ngừng chấp nhận credential trong khi điều tra hoặc chờ xác minh. | Tạm khóa API key có hành vi bất thường. |
| **Session timeout** | Kết thúc trạng thái đăng nhập theo idle/absolute lifetime. | Session web hết hạn sau 30 phút không hoạt động. |
| **Re-authentication** | Yêu cầu xác thực lại bằng credential còn hợp lệ. | Người dùng xác thực lại bằng passkey trước thao tác nhạy cảm. |

Các khái niệm này có thể xuất hiện cùng nhau nhưng không thay thế nhau. Rotation có thể cấp credential mới trước khi credential cũ hết hạn; revocation có thể xảy ra ngay khi phát hiện compromise; session timeout không nhất thiết thu hồi password hoặc passkey đã đăng ký.

### 1.2. Expiration không đồng nghĩa credential đã bị lộ

Credential hết hạn vì policy hoặc giao thức quy định thời gian sử dụng. Credential bị compromise là sự kiện bảo mật riêng. Một credential có thể:
- Hết hạn nhưng chưa từng bị lộ.
- Còn hạn nhưng đã bị lộ và cần revoke ngay.
- Được rotate bình thường dù credential cũ chưa có dấu hiệu bất thường.
- Bị disable vì account owner rời tổ chức hoặc workload kết thúc.

Do đó, hệ thống cần cả expiration tự động lẫn quy trình revoke khẩn cấp.

## 2. Vì sao credential cần thời hạn?

Credential lâu năm làm tăng khoảng thời gian một bí mật hoặc khóa bị lộ có thể bị sử dụng. Credential cũ cũng có thể gắn với nhân viên đã nghỉ việc, integration đã ngừng, thiết bị bị mất hoặc quyền không còn phù hợp.

Thời hạn và rotation có thể giúp:
- Giới hạn thời gian sử dụng credential bị sao chép.
- Loại bỏ credential không còn owner hoặc mục đích rõ ràng.
- Buộc đánh giá lại account, thiết bị, thuật toán và phạm vi quyền.
- Đồng bộ với chu kỳ vận hành, hợp đồng, chứng chỉ và workload.
- Giảm nguy cơ một secret cũ tiếp tục tồn tại trong backup, log hoặc máy không còn quản lý.

Tuy nhiên, expiration quá ngắn hoặc rotation thủ công thường xuyên có thể tạo outage, thúc đẩy người dùng chọn password yếu, lưu secret vào file không an toàn hoặc bỏ qua quy trình. Thời hạn cần phản ánh rủi ro thực tế và khả năng thay thế an toàn.

### 2.1. Thời hạn là một phần của risk policy

Không có một con số duy nhất phù hợp cho mọi credential. Policy cần xét:
- Credential có thể được dùng để làm gì và phạm vi quyền rộng đến đâu.
- Credential có chống phishing hoặc sender-constrained không.
- Nó được lưu ở browser, thiết bị, HSM, vault hay file cấu hình.
- Có thể phát hiện việc sử dụng trái phép nhanh đến đâu.
- Có cơ chế revoke tức thời hoặc gần tức thời không.
- Việc cấp lại có tự động, an toàn và không gây downtime không.
- Credential thuộc người dùng, admin, service account hay workload.
- Yêu cầu giao thức, hợp đồng, quy định hoặc trust framework.

Một token ngắn hạn có audience hẹp có thể phù hợp cho request API; một certificate của workload có thể cần chu kỳ dài hơn nếu quy trình cấp lại an toàn và tự động. Quyết định phải được ghi trong policy và có owner.

## 3. Expiration theo từng loại credential

### 3.1. Password

Password thường không mang trường hết hạn bên trong. Thời hạn, nếu có, được áp dụng bởi verifier hoặc hệ thống quản lý account.

Chính sách hiện đại nên tránh buộc người dùng đổi password theo lịch cứng mà không có dấu hiệu compromise, vì việc đổi quá thường xuyên có thể dẫn tới password dễ đoán, biến thể tuần tự hoặc ghi chú không an toàn. Nên yêu cầu thay đổi khi:
- Có bằng chứng password bị lộ hoặc xuất hiện trong danh sách credential compromise.
- Có sự cố phishing, malware hoặc lộ dữ liệu ảnh hưởng account.
- Người dùng hoặc admin yêu cầu reset qua quy trình đã xác minh.
- Password bootstrap/tạm thời đã được dùng hoặc hết thời hạn.
- Chính sách tổ chức hoặc quy định áp dụng yêu cầu một chu kỳ cụ thể; khi đó cần kiểm soát tác động và hỗ trợ thay đổi an toàn.

Không nên coi “password còn trong thời hạn” là lý do bỏ qua risk signals. Password có thể bị lộ ngay sau khi người dùng đổi.

### 3.2. Passkey và security key

Passkey/WebAuthn thường không có ngày hết hạn mật mã cố định được nhúng trong credential. Credential có thể tiếp tục hoạt động cho tới khi RP xóa hoặc disable credential record, account bị đóng, authenticator bị thu hồi hoặc policy yêu cầu đăng ký lại.

Có thể đặt chính sách cho:
- Rà soát credential không dùng trong thời gian dài.
- Loại bỏ passkey gắn với thiết bị bị mất hoặc không còn thuộc người dùng.
- Yêu cầu re-enrollment khi đổi RP, thay đổi trust hoặc có incident.
- Thu hồi credential khi account bị disable hoặc người dùng rời tổ chức.
- Kiểm tra last-used metadata nhưng không coi inactivity là bằng chứng compromise.

Không xóa passkey chỉ vì một thời hạn tùy ý nếu điều đó khiến người dùng mất phương thức đăng nhập duy nhất. Cần phương thức dự phòng hoặc recovery đã được kiểm chứng trước khi loại bỏ credential.

### 3.3. TOTP và authenticator seed

Mã TOTP có thời gian sống rất ngắn theo time step; đó là **OTP code expiration**, khác với thời hạn của seed bí mật đã provision vào authenticator. Seed thường tồn tại tới khi bị rotate, reset hoặc revoke.

Nếu seed bị lộ, hãy revoke seed cũ và enrollment seed mới qua quy trình xác minh. Không chỉ chờ mã hiện tại hết hạn, vì attacker có thể tiếp tục tạo mã mới từ seed đã sao chép.

### 3.4. Recovery code

Recovery code thường được thiết kế để dùng một lần. Sau khi sử dụng thành công, code phải được đánh dấu consumed và không thể dùng lại. Bộ recovery code mới có thể làm vô hiệu toàn bộ bộ cũ.

Một hệ thống có thể đặt ngày hết hạn cho bộ code, nhưng cần:
- Hiển thị code chỉ một lần khi tạo.
- Lưu verifier/hash phù hợp thay vì plaintext.
- Không ghi code vào log, email hoặc ticket.
- Đánh dấu used atomically để hai request đồng thời không dùng cùng code.
- Cấp lại qua quy trình đã xác minh và thu hồi bộ cũ.

### 3.5. X.509 certificate

Certificate có thời gian hiệu lực rõ qua `notBefore` và `notAfter`. Client/server phải kiểm tra certificate hiện tại nằm trong khoảng hợp lệ, đồng thời xác minh chain, trust anchor, tên/subject phù hợp, key usage, extended key usage và các yêu cầu profile.

Certificate còn hạn không bảo đảm private key vẫn an toàn. Nếu private key bị lộ, certificate cần được revoke hoặc trust bị loại bỏ theo quy trình CA; không chờ `notAfter`.

Certificate renewal thường tạo certificate mới, có thể cùng public key hoặc key pair mới tùy policy. Với workload và service identity, nên tự động hóa issuance/renewal, theo dõi ngày hết hạn và cảnh báo trước đủ lâu.

### 3.6. SSH key, API key và client secret

SSH key và API key thường không tự hết hạn nếu hệ thống chỉ lưu public key hoặc secret hash. Thời hạn phải được thực thi bởi inventory/policy và hệ thống xác minh.

Mỗi key cần có:
- Owner và mục đích.
- Client/service hoặc account được phép sử dụng.
- Scope, resource và environment.
- Ngày tạo, ngày hết hạn, lần dùng gần nhất.
- Trạng thái active, pending rotation, revoked hoặc expired.
- Quy trình cấp mới, overlap và revoke.

API key nên có entropy cao, chỉ hiển thị secret một lần và lưu verifier/hash ở server. Không gửi secret mới qua ticket hoặc email. Client secret nên được quản lý trong secret manager và không nhúng vào source code.

### 3.7. Access token và refresh token

Access token thường có thời hạn ngắn; resource server kiểm tra `exp` cùng chữ ký, issuer, audience, scope và các điều kiện khác. Hết hạn access token không có nghĩa refresh token cũng hết hạn.

Refresh token có thể có:
- Absolute lifetime: thời điểm tối đa token family được sử dụng.
- Idle lifetime: hết hạn nếu không được sử dụng trong khoảng thời gian quy định.
- Rotation: mỗi lần refresh cấp token mới và vô hiệu token cũ.
- Reuse detection: phát hiện token đã tiêu thụ được dùng lại.
- Revocation: thu hồi token hoặc family khi logout, compromise hoặc grant bị thu hồi.

Không nhầm token expiration với password/passkey expiration. Token là credential đại diện quyền truy cập được cấp trong một flow; nó cần policy riêng về audience, scope, lifetime, sender constraint và revocation.

## 4. Xác định thời hạn phù hợp

Thời hạn nên xuất phát từ threat model và đặc tính credential. Có thể dùng ma trận sau làm điểm bắt đầu, sau đó hiệu chỉnh theo môi trường:

| Credential | Cơ chế hết hạn thường gặp | Điều cần chú ý |
| --- | --- | --- |
| Password | Không nhất thiết có expiration định kỳ; reset khi compromise hoặc theo policy có căn cứ. | Ưu tiên password screening, MFA/passkey và reset an toàn. |
| Passkey | Thường không có ngày hết hạn mật mã; revoke/re-enroll theo lifecycle. | Theo dõi thiết bị, account status và last-used; tránh xóa hàng loạt tùy tiện. |
| TOTP seed | Thường tồn tại tới khi revoke/rotate; OTP code hết hạn theo time step. | Seed compromise cần reset, không chỉ đợi code hết hạn. |
| Recovery code | One-time use; có thể thêm TTL cho bộ code. | Atomic consume, cấp bộ mới thì revoke bộ cũ. |
| X.509 certificate | `notBefore`/`notAfter` theo CA/profile. | Auto-renew, chain validation và revocation khi compromise. |
| SSH/API key | Thời hạn do inventory/policy thực thi. | Owner, scope, rotation và revoke phải rõ. |
| Access token | Claim `exp` hoặc introspection policy. | Lifetime ngắn theo audience và mức rủi ro. |
| Refresh token | Idle/absolute lifetime, rotation và revoke. | Phát hiện reuse và ràng buộc với client/grant. |

Không áp dụng thời hạn giống nhau cho mọi account. Admin, production workload và credential có quyền rộng thường cần scope hẹp, monitoring mạnh, rotation tự động và khả năng revoke nhanh.

### 4.1. Hết hạn theo thời gian và theo sự kiện

Có hai nhóm điều kiện:
- **Time-based expiration:** credential mất hiệu lực tại một thời điểm hoặc sau một khoảng thời gian.
- **Event-based invalidation:** credential mất hiệu lực khi có sự kiện như account disable, nhân viên rời tổ chức, private key compromise, device lost, role revoked hoặc grant bị thu hồi.

Một credential có thể còn trong thời hạn nhưng phải bị vô hiệu hóa do event. Policy nên hỗ trợ cả hai.

### 4.2. Idle expiration và absolute expiration

Idle expiration phụ thuộc thời gian không sử dụng; absolute expiration phụ thuộc thời gian kể từ khi credential hoặc token được cấp. Chỉ dùng idle expiration có thể khiến credential tồn tại vô hạn nếu attacker thỉnh thoảng sử dụng nó. Chỉ dùng absolute expiration có thể làm gián đoạn workload dài hạn nếu không có renewal tự động.

Với refresh token, kết hợp idle và absolute lifetime thường giúp giới hạn cả credential bị bỏ quên lẫn token hoạt động kéo dài. Với API key lâu dài, inactivity có thể kích hoạt review hoặc disable sau thông báo, nhưng phải xem xét lịch batch hiếm và owner xác nhận trước khi thu hồi.

## 5. Renewal và rotation an toàn

Renewal nên bắt đầu trước khi credential hết hạn đủ lâu để xử lý lỗi, phân phối credential mới và chuyển toàn bộ consumer. Không chờ tới phút cuối rồi thực hiện thay đổi thủ công trong production.

### 5.1. Quy trình renewal tham khảo

1. Xác định credential sắp hết hạn từ inventory đáng tin.
2. Kiểm tra owner, account/service, scope, trạng thái và mục đích còn hợp lệ.
3. Xác minh actor hoặc workload có quyền yêu cầu renewal.
4. Tạo credential mới qua quy trình chuẩn; dùng key pair mới khi policy yêu cầu.
5. Kiểm tra proof of possession, certificate chain hoặc credential registration response.
6. Phân phối credential mới qua kênh an toàn tới đúng consumer.
7. Chạy kiểm tra hoạt động với credential mới.
8. Kích hoạt credential mới và bắt đầu cửa sổ overlap có giới hạn nếu cần.
9. Xác nhận mọi consumer đã chuyển sang credential mới.
10. Revoke credential cũ, cập nhật inventory và audit kết quả.

Renewal không được âm thầm gia hạn một credential đã bị đánh dấu compromised. Nếu có dấu hiệu compromise, cần quy trình incident response và key replacement, không chỉ kéo dài thời hạn.

### 5.2. Overlap có giới hạn

Trong một số hệ thống, credential cũ và mới cần cùng hoạt động trong thời gian chuyển đổi. Ví dụ, API key mới được triển khai tới nhiều instance trước khi key cũ bị revoke.

Overlap cần:
- Có thời điểm bắt đầu/kết thúc rõ ràng.
- Giới hạn đúng client, scope và môi trường.
- Theo dõi việc sử dụng credential cũ để biết consumer nào chưa chuyển.
- Không kéo dài tự động khi migration lỗi.
- Revoke ngay nếu credential cũ bị compromise.

Nếu overlap không cần thiết, chỉ kích hoạt credential mới sau khi mọi điều kiện kiểm tra đạt và revoke credential cũ theo một transaction/sequence có kiểm soát.

### 5.3. Không rotate bằng cách gửi secret qua kênh không an toàn

Không đưa password, private key, API secret, TOTP seed hoặc recovery code vào email, chat, issue tracker hay log. Dùng secret manager, HSM, secure enrollment ceremony hoặc kênh provisioning được bảo vệ. Giới hạn quyền đọc và ghi nhận ai đã truy cập secret metadata.

## 6. Gia hạn certificate và quản lý khóa

Certificate hết hạn là nguyên nhân phổ biến gây outage vì TLS handshake, mutual TLS hoặc client authentication có thể thất bại ngay khi certificate qua `notAfter`.

### 6.1. Theo dõi certificate inventory

Inventory nên lưu:
- Certificate fingerprint/serial number.
- Subject, SAN và issuer.
- Key usage và extended key usage.
- Not-before/not-after.
- Owner, service, environment và dependency.
- CA/trust anchor và chain.
- Trạng thái revocation.
- Renewal method, automation owner và lần kiểm tra gần nhất.

Không chỉ theo dõi certificate ở load balancer. Certificate có thể nằm trong ingress, service mesh, database client, device, mobile app, signing service hoặc workload chưa được inventory.

### 6.2. Tự động hóa renewal

Với certificate có thể cấp lại tự động, sử dụng ACME, SPIFFE/SPIRE hoặc PKI automation phù hợp kiến trúc và trust model. Automation phải xác minh identity và quyền yêu cầu issuance; không cấp certificate chỉ vì một process có thể truy cập endpoint.

Theo dõi:
- Renewal attempt và kết quả.
- Thời gian còn lại trước expiry.
- Certificate mới đã được cài đặt trên mọi instance chưa.
- Service đã reload/restart để dùng certificate mới chưa.
- Chain và hostname validation sau khi triển khai.
- Certificate cũ đã revoke/loại bỏ đúng thời điểm chưa.

### 6.3. Revocation và trạng thái certificate

CRL và OCSP là các cơ chế phổ biến để công bố trạng thái thu hồi certificate; cách client xử lý khi không truy vấn được status phụ thuộc profile và policy. Một số môi trường dùng short-lived certificate và quy trình trust update để giảm phụ thuộc vào revocation check trực tuyến.

Hệ thống cần xác định rõ:
- Client có kiểm tra CRL/OCSP không.
- Cache status trong bao lâu.
- Hành vi khi responder không khả dụng.
- Certificate bị compromise có cần denylist nội bộ khẩn cấp không.
- Trust anchor hoặc intermediate CA bị thu hồi thì phạm vi ảnh hưởng ra sao.

Certificate hết hạn và certificate bị revoke đều phải bị từ chối, nhưng nguyên nhân và quy trình xử lý khác nhau.

## 7. Hết hạn trong hệ thống token và session

Credential expiration thường bị nhầm với session timeout. Một lần đăng nhập có thể tạo session cookie, access token và refresh token; mỗi thành phần có thời hạn và cơ chế thu hồi riêng.

### 7.1. Access token expiration

Resource server phải kiểm tra thời hạn access token theo profile. Với JWT, kiểm tra chữ ký, issuer, audience, `exp` và các claim bắt buộc. Nếu token hết hạn, client cần xin token mới qua flow được cấp phép; không tự kéo dài `exp` hoặc chấp nhận token cũ để tránh lỗi UX.

Access token ngắn hạn giới hạn thời gian token bị đánh cắp có thể sử dụng. Tuy nhiên, nếu refresh token còn hoạt động, attacker có thể xin token mới. Do đó cần bảo vệ refresh token, rotation/reuse detection và revoke theo grant/session.

### 7.2. Refresh token expiration

Refresh token nên có lifetime và trạng thái rõ ràng. Có thể áp dụng:
- Absolute expiration từ thời điểm cấp hoặc lần xác thực ban đầu.
- Idle expiration từ lần sử dụng hợp lệ cuối.
- Rotation sau mỗi lần refresh.
- Reuse detection và revoke token family khi phát hiện token cũ được dùng lại.
- Revocation khi logout, account disable, password/MFA reset theo policy hoặc grant bị thu hồi.

Không phải mọi lần đổi password đều phải thu hồi mọi token trong mọi hệ thống; semantics phải được xác định theo threat model và policy. Với account compromise, thu hồi session/token liên quan thường là một phần của containment.

### 7.3. Session expiration

Session có thể có idle timeout và absolute timeout. Khi hết hạn, server phải ngừng chấp nhận session ID; xóa cookie ở browser là bước dọn dẹp bổ sung. Session timeout không tự thu hồi passkey, password hoặc certificate.

Với thao tác nhạy cảm, có thể yêu cầu authentication freshness ngay cả khi session chưa hết hạn. Một session còn active không chứng minh lần xác thực ban đầu vẫn đủ mới cho mọi hành động.

## 8. Kiểm tra thời gian và clock skew

Expiration phụ thuộc thời gian. Nếu server, client, CA, resource server và container có đồng hồ lệch, credential có thể bị từ chối quá sớm hoặc được chấp nhận quá lâu.

Thực hành:
- Dùng UTC cho thời điểm lưu trữ và audit.
- Đồng bộ clock bằng nguồn thời gian được quản lý.
- Dùng clock server tin cậy để kiểm tra credential; không tin thời gian do client tự khai.
- Áp dụng clock-skew allowance nhỏ, có lý do và thống nhất theo profile.
- Không cộng grace period dài tùy tiện để làm credential hết hạn tiếp tục được chấp nhận.
- Monitor clock drift và cảnh báo khi vượt ngưỡng.
- Kiểm tra biên thời gian, múi giờ, leap second và định dạng timestamp theo thư viện chuẩn.

Với X.509, kiểm tra khoảng hiệu lực gồm cả not-before và not-after. Với JWT, xử lý `exp` và `nbf` theo specification và clock tolerance được cấu hình. Không bỏ qua expiry khi clock service gặp lỗi.

### 8.1. Grace period có kiểm soát

Grace period có thể giúp migration hoặc xử lý sự cố đồng hồ, nhưng phải được định nghĩa rõ:
- Credential loại nào được hưởng.
- Mức tối đa và lý do.
- Resource/action nào vẫn bị chặn.
- Có yêu cầu step-up hoặc fallback credential không.
- Ai phê duyệt và thời điểm kết thúc.
- Audit và alert nào được tạo.

Không dùng grace period để duy trì certificate hoặc API key đã bị compromise. Trong trường hợp key compromise, cần revoke/deny ngay theo incident policy.

## 9. Hành vi khi credential hết hạn

Khi credential hết hạn, hệ thống phải từ chối nó tại điểm xác minh và trả kết quả có thể xử lý an toàn.

### 9.1. Người dùng tương tác

Với password, passkey, MFA hoặc certificate người dùng:
- Giải thích credential/phương thức cần cập nhật mà không tiết lộ chi tiết nội bộ.
- Cung cấp renewal hoặc recovery flow chính thức.
- Xác minh bằng phương thức còn tin cậy.
- Không yêu cầu người dùng gửi secret cũ qua helpdesk.
- Không tự động hạ xuống phương thức yếu hơn để tránh friction.
- Thông báo tới kênh đã xác minh khi credential bị thu hồi hoặc thay mới.

Nếu passkey không có expiry tự nhiên, UI không nên hiển thị “passkey hết hạn” chỉ vì một policy review. Hãy phân biệt credential bị disabled/revoked, cần re-enrollment hoặc authenticator không còn hỗ trợ.

### 9.2. Workload và machine identity

Workload không thể luôn mở browser để người vận hành nhập password. Cần:
- Renewal tự động trước expiry.
- Identity bootstrap có thẩm quyền.
- Secret manager, HSM hoặc workload identity provider.
- Credential ngắn hạn và tự động cấp lại khi phù hợp.
- Monitoring và alert đủ sớm.
- Overlap để rollout an toàn.
- Runbook khi issuer/CA/metadata service outage.

Không hardcode secret mới vào image/container đã build sẵn. Ưu tiên lấy credential lúc runtime qua identity provider được tin cậy.

### 9.3. Không chấp nhận fallback vô hạn

Nếu credential hết hạn, hệ thống không nên âm thầm chấp nhận credential cũ, tắt kiểm tra expiry hoặc chuyển sang password yếu không có proofing. Fallback phải là phương thức đã được đăng ký và đáp ứng assurance cần thiết, hoặc một quy trình recovery có thẩm quyền.

## 10. Notification và inventory

Nhắc trước ngày hết hạn giúp người dùng và owner có thời gian gia hạn. Notification là hỗ trợ vận hành, không phải cơ chế bảo mật thực thi expiry.

Một thông báo hữu ích nên nêu:
- Credential hoặc service nào sắp hết hạn, bằng reference không nhạy cảm.
- Owner và application/resource bị ảnh hưởng.
- Thời điểm hết hạn theo múi giờ rõ ràng.
- Hành động cần thực hiện và link tới portal chính thức.
- Trạng thái renewal và nơi liên hệ hỗ trợ.

Không gửi secret hoặc link cho phép tự thay credential mà không có xác minh. Không chỉ gửi tới email mới vừa được thay đổi nếu chưa xác minh; dùng contact channel đã được tin cậy theo policy.

### 10.1. Inventory là nguồn sự thật

Mỗi credential cần được quản lý bằng inventory hoặc registry có owner. Các trường tham khảo:
- Credential ID/reference và loại.
- Subject/account/client/workload.
- Owner và contact đã xác minh.
- Scope, audience, environment và resource.
- Created-at, not-before, expires-at, last-used-at.
- Rotation/revocation status và version.
- Issuer/CA/key ID khi phù hợp.
- Renewal automation và dependency.
- Policy version, exception và approval.

Không lưu raw secret trong inventory. Với API key hoặc password, chỉ lưu verifier/hash ở nơi xác minh chuyên trách; inventory giữ metadata và reference tới secret manager.

### 10.2. Cảnh báo nhiều mốc

Có thể cảnh báo theo nhiều mốc, ví dụ 30 ngày, 7 ngày và 24 giờ trước khi hết hạn, tùy chu kỳ credential. Với certificate ngắn hạn hoặc workload tự động, dùng monitoring theo phần trăm lifetime còn lại và alert khi renewal thất bại.

Không gửi cảnh báo quá nhiều khiến owner bỏ qua. Gộp theo service/owner và ưu tiên mức ảnh hưởng.

## 11. Credential hết hạn trong hệ thống phân tán

Một credential có thể được xác minh ở nhiều node, region hoặc resource server. Nếu mỗi nơi có cache và clock khác nhau, việc hết hạn hoặc revoke có thể không đồng nhất.

### 11.1. Consistent enforcement

- Dùng nguồn thời gian và thư viện validation thống nhất.
- Định nghĩa rõ ai là authority phát hành và trạng thái credential.
- Cache public key/certificate status với TTL có giới hạn.
- Cập nhật denylist/revocation state qua event có version.
- Xử lý event duplicate, trễ và sai thứ tự.
- Kiểm tra trạng thái online cho action nhạy cảm khi cần revoke nhanh.
- Đặt maximum propagation delay và monitor thực tế.

Với JWT tự chứa, resource server có thể xác minh chữ ký mà không hỏi issuer ở mỗi request. Điều này tăng availability nhưng làm revocation khó tức thì. Token ngắn hạn, introspection hoặc state check có thể cân bằng theo yêu cầu.

### 11.2. Hết hạn khi offline

Thiết bị hoặc workload có thể hoạt động offline. Khi không kết nối được issuer hoặc revocation service:
- Không kéo dài credential hết hạn vô thời hạn.
- Dùng offline validity window chỉ khi threat model và policy cho phép.
- Giới hạn tài nguyên/hành động trong thời gian offline.
- Lưu event và kiểm tra lại khi kết nối phục hồi.
- Có phương án fail-safe cho thao tác đặc quyền.

Offline grace không nên vượt qua sự kiện revoke đã biết. Nếu thiết bị nhận được thông báo credential compromise, phải ưu tiên containment theo policy.

## 12. Threat model cho credential expiration

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Credential tồn tại quá lâu** | Secret/key không có owner hoặc expiry policy. | Credential bị lộ có thể bị lạm dụng dài hạn. | Inventory, owner, scope, review và expiration/rotation phù hợp. |
| **Expired credential accepted** | Node bỏ qua `exp`/`notAfter` hoặc clock sai. | Credential hết hạn vẫn truy cập được. | Validation thống nhất, clock sync, boundary tests. |
| **Compromised credential chưa revoke** | Hệ thống chờ tới expiry dù đã có dấu hiệu lộ. | Attacker tiếp tục truy cập. | Emergency revocation và incident response. |
| **Renewal outage** | Certificate/key hết hạn trước khi rollout hoàn tất. | TLS/API/authentication ngừng hoạt động. | Auto-renew, alert, staging và overlap có giới hạn. |
| **Unsafe overlap** | Credential cũ được giữ active quá lâu sau rotation. | Secret cũ vẫn là đường truy cập cho attacker. | Deadline, usage monitoring và revoke tự động. |
| **Rotation race** | Consumer dùng key cũ trong khi issuer đã loại bỏ key. | Request hợp lệ bị lỗi hoặc validation không nhất quán. | Versioning, staged rollout và overlap có kiểm soát. |
| **Clock manipulation/drift** | Đồng hồ node sai hoặc client cung cấp thời gian giả. | Token/certificate được chấp nhận sai thời điểm. | Trusted time source và server-side validation. |
| **Notification phishing** | Attacker gửi email giả “credential sắp hết hạn”. | Người dùng nhập secret vào trang giả. | Portal chính thức, signed notification policy, không yêu cầu gửi secret. |
| **Inactivity misclassification** | Key ít dùng do batch hiếm bị revoke tự động. | Workload production bị outage. | Owner review, lịch sử workload và grace có phê duyệt. |
| **Fallback downgrade** | Expiry khiến hệ thống tự chuyển sang password/OTP yếu. | Mất assurance và mở đường tấn công. | Minimum assurance policy và recovery proofing. |
| **Inventory gap** | Certificate/key không được ghi nhận. | Hết hạn bất ngờ hoặc không thể xác định owner. | Discovery scan, registry reconciliation và ownership. |

## 13. Tình huống thực hành: certificate production sắp hết hạn

**Bối cảnh:** Một service nội bộ dùng mutual TLS với client certificate còn 5 ngày hiệu lực. Certificate được cài trên 40 instance ở ba region. Team vận hành tạo certificate mới nhưng chỉ cập nhật 35 instance. Một số instance vẫn dùng certificate cũ; sau ngày hết hạn, các kết nối từ chúng bị từ chối.

**Phân tích:**

1. Certificate mới được cấp không có nghĩa rollout đã hoàn tất.
2. Inventory cần theo dõi từng instance/consumer, không chỉ một record certificate tổng.
3. Việc để certificate cũ hết hạn gây outage; giữ nó active vô thời hạn lại làm tăng rủi ro.
4. Nếu certificate cũ bị compromise, overlap dài có thể không chấp nhận được.
5. Cần kiểm tra chain, SAN, EKU, trust store và việc service đã reload certificate mới.

**Thiết kế lại:**

- Bắt đầu renewal đủ sớm và tạo rollout job có trạng thái theo từng instance.
- Kiểm tra certificate mới bằng test handshake và policy validation.
- Phân phối qua secret/certificate manager; không gửi private key qua email.
- Theo dõi instance đã cài, đã reload và đã kết nối thành công.
- Chỉ duy trì overlap tới deadline đã phê duyệt.
- Sau khi xác nhận tất cả consumer chuyển đổi, revoke hoặc loại bỏ certificate cũ theo policy.
- Alert nếu còn instance dùng certificate cũ gần ngày hết hạn.
- Nếu private key cũ bị compromise, chuyển sang incident rotation khẩn cấp và không chờ overlap thông thường.

**Câu hỏi:** Nếu 5 instance chưa thể cập nhật trước expiry, có nên tự động gia hạn certificate cũ? Không. Cần đánh giá lý do, mức rủi ro và phương án rollback/containment. Gia hạn hoặc grace chỉ được thực hiện nếu CA/policy cho phép, không có dấu hiệu compromise và có approval rõ; nếu không, phải cập nhật consumer hoặc chuyển sang phương án dự phòng đã kiểm thử.

## 14. Checklist thiết kế credential expiration

- [ ] Inventory mọi credential, owner, subject, client/workload, scope và resource.
- [ ] Phân biệt expiration, rotation, renewal, revocation, suspension và session timeout.
- [ ] Xác định credential nào có expiry theo giao thức và credential nào cần policy riêng.
- [ ] Đặt thời hạn theo threat model, quyền, khả năng revoke và chi phí renewal.
- [ ] Không buộc đổi password định kỳ một cách máy móc nếu không có căn cứ; reset khi compromise theo policy.
- [ ] Phân biệt thời hạn OTP code với vòng đời TOTP seed.
- [ ] Xử lý passkey/security key theo trạng thái account, thiết bị và revoke; không giả định mọi passkey có ngày hết hạn.
- [ ] Dùng one-time consume cho recovery code và revoke bộ cũ khi cấp lại.
- [ ] Kiểm tra certificate validity, chain, SAN, key usage, EKU và revocation status.
- [ ] Quản lý API/SSH key bằng owner, scope, expiry metadata, rotation và secret manager.
- [ ] Đặt access/refresh token lifetime riêng; hỗ trợ rotation, reuse detection và revocation.
- [ ] Tự động hóa renewal trước expiry; kiểm thử credential mới trước khi chuyển traffic.
- [ ] Chỉ cho overlap có giới hạn, theo dõi consumer và revoke key cũ đúng hạn.
- [ ] Dùng UTC, trusted time source và clock-skew allowance nhỏ có lý do.
- [ ] Không chấp nhận credential hết hạn hoặc compromised vì grace period tùy tiện.
- [ ] Xác định fail-open/fail-closed và offline behavior theo độ nhạy tài nguyên.
- [ ] Theo dõi inventory, last-used, renewal result, propagation và owner acknowledgement.
- [ ] Gửi notification qua kênh tin cậy; không yêu cầu người dùng gửi secret.
- [ ] Có emergency revoke/rotation runbook và kiểm tra session/token downstream.
- [ ] Kiểm thử expiry boundary, clock drift, node cache, partial rollout, race và renewal outage.

## 15. Câu hỏi tự kiểm tra

**1. Credential expiration là gì?**  
Là thời điểm hoặc điều kiện mà hệ thống không còn chấp nhận credential theo giao thức hoặc policy.

**2. Expiration khác revocation như thế nào?**  
Expiration xảy ra theo thời hạn/điều kiện; revocation chủ động thu hồi credential trước hoặc sau expiry vì không còn được tin cậy.

**3. Password có bắt buộc phải hết hạn định kỳ không?**  
Không phải mọi hệ thống đều cần. Nên tránh thay đổi định kỳ máy móc khi không có dấu hiệu compromise; yêu cầu reset khi có bằng chứng lộ hoặc theo policy có căn cứ.

**4. Passkey có ngày hết hạn cố định không?**  
Thông thường không có expiry mật mã cố định. RP quản lý trạng thái credential và có thể revoke, disable hoặc yêu cầu đăng ký lại theo lifecycle.

**5. TOTP code hết hạn có làm seed TOTP hết hạn không?**  
Không. OTP code hết hạn theo time step; seed vẫn có thể tạo mã mới cho tới khi bị rotate hoặc revoke.

**6. Certificate còn hạn có chắc chắn an toàn không?**  
Không. Private key có thể đã bị compromise; certificate cần được revoke hoặc trust bị loại bỏ ngay khi có căn cứ.

**7. Vì sao cần overlap khi rotation?**  
Để các consumer chuyển sang credential mới mà không gián đoạn. Overlap phải có thời hạn, scope và điều kiện revoke rõ.

**8. Access token hết hạn có làm refresh token hết hạn không?**  
Không. Hai token có lifetime và policy riêng. Refresh token có thể tiếp tục xin access token mới cho tới khi idle/absolute expiry hoặc revoke.

**9. Vì sao clock synchronization quan trọng?**  
Vì kiểm tra not-before, not-after và exp dựa trên thời gian. Clock drift có thể gây từ chối sai hoặc chấp nhận credential ngoài thời hạn.

**10. Khi phát hiện credential bị lộ, có nên đợi tới ngày hết hạn?**  
Không. Cần revoke/rotate khẩn cấp, đánh giá session/token/grant liên quan và thực hiện incident response theo phạm vi ảnh hưởng.

**Ghi nhớ:** Credential expiration giới hạn thời gian một credential được chấp nhận, nhưng không thay thế rotation, revocation hoặc giám sát compromise. Hãy đặt thời hạn theo từng loại credential và mức rủi ro, tự động hóa renewal, kiểm tra thời gian nhất quán, quản lý overlap có giới hạn và thu hồi ngay khi credential không còn đáng tin. Một vòng đời tốt phải bảo vệ account lẫn tính liên tục của dịch vụ.
