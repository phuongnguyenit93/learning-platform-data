# Trách nhiệm bảo vệ danh tính khi một đối tác hoặc máy chủ trung gian bị xâm nhập

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Ranh giới tin cậy. Bài này giải thích ai phải bảo vệ danh tính, hệ thống nào có thể tiếp tục tin điều gì, và cần làm gì khi một đối tác tích hợp SSO, một proxy hoặc một máy chủ trung gian bị chiếm quyền.

## 1. Vấn đề cốt lõi: tin cậy có phạm vi và có thể bị thu hồi

Trong **federation**, nhiều hệ thống cùng tham gia một hành trình đăng nhập. Một **Identity Provider (IdP)** hoặc **OpenID Provider (OP)** xác thực người dùng; **Service Provider (SP)** trong SAML hoặc **Relying Party (RP)** trong OIDC tiêu thụ kết quả đó; **CAS service** dựa vào CAS server để xác minh ticket; **OAuth Resource Server (RS)** bảo vệ API dựa trên access token. Giữa chúng có thể có API gateway, reverse proxy, identity broker, WAF, service mesh hoặc đối tác SaaS.

Mỗi bên chỉ nên được tin **trong một chức năng đã xác định**. Một đối tác được phép sử dụng danh tính để đăng nhập ứng dụng của họ **không mặc nhiên được phép** mạo danh người dùng ở API của ta, sửa vai trò quản trị, phát hành token thay IdP hay xác nhận rằng người dùng đã đạt mức xác thực cao hơn.

Ví dụ mô hình:

```text
Người dùng
    |
    v
[IdP / OP / CAS server] -- assertion / ID token / ticket --> [SP / RP / CAS service]
          |                                                |
          | OAuth access token                              | phiên ứng dụng
          v                                                v
 [Authorization Server] ---- access token ----> [Resource Server / API]
                                                ^
                                                |
                               [Gateway / Proxy / Broker]
                                     (điểm trung gian)
```

Sơ đồ này minh họa **vai trò**, không nhất thiết là sơ đồ triển khai: OP thường cũng đóng vai trò Authorization Server; gateway có thể nằm trên nhiều đường truyền; CAS dùng luồng ticket/validation riêng.

Một giao dịch nhận dạng cần trả lời được năm câu hỏi:

1. **Ai là nguồn khẳng định danh tính?** Issuer/IdP/OP/CAS server nào được phê duyệt, cho tenant và tập người dùng nào?
2. **Bằng chứng được cấp cho ai?** SAML `AudienceRestriction`, OIDC `aud`, OAuth access token audience hoặc CAS `service` có khớp bên nhận không?
3. **Ai đã xử lý bằng chứng trên đường đi?** Có broker, proxy, gateway nào có thể đọc/sửa header hoặc tự phát hành bằng chứng mới?
4. **Bằng chứng cho phép hành động gì?** Đăng nhập phiên web, gọi một API, đọc dữ liệu cá nhân hay thực hiện giao dịch nhạy cảm?
5. **Khi một mắt xích mất an toàn, bên nhận còn được tin điều gì?** Chữ ký hợp lệ, HTTP 200 hoặc IP nội bộ **không tự chứng minh** danh tính và ý định của người dùng là đáng tin trong tình huống issuer/intermediary đã bị kiểm soát.

**Nguyên tắc:** Không có “tin cậy một lần, tin toàn bộ chuỗi”. Thiết kế phải giới hạn **issuer, đối tượng nhận, phạm vi quyền, thời hạn, đường truyền và điều kiện thu hồi** tại từng ranh giới.

## 2. Điều gì thực sự xảy ra khi mỗi bên bị xâm nhập?

| Thành phần bị chiếm quyền | Kẻ tấn công có thể kiểm soát hoặc đánh cắp | Phạm vi ảnh hưởng cần đánh giá | Điều không được mặc định kết luận |
| --- | --- | --- | --- |
| **SP / OIDC RP / CAS service của đối tác** | Phiên ứng dụng, dữ liệu lưu cục bộ, token còn trong hệ thống, client secret, refresh token, tài khoản quản trị ứng dụng, cấu hình redirect | Người dùng của đối tác; API và dữ liệu mà token/quyền của đối tác truy cập được | Việc chiếm RP **không tự động** cho phép tạo SAML assertion hoặc ID token hợp lệ dưới khóa riêng IdP chưa bị lộ |
| **Identity broker / SSO gateway** | Ánh xạ thuộc tính, kết nối upstream/downstream, token được chuyển đổi, phiên SSO, khóa ký nếu broker là issuer | Nhiều ứng dụng dựa vào broker; nguy cơ mở rộng khi broker tự ký assertion/token mới | Token có chữ ký hợp lệ từ broker **không chứng minh** upstream IdP không bị giả mạo hoặc dữ liệu claim không bị nâng quyền |
| **Reverse proxy / API gateway** | Header chuyển tiếp, cookie/bearer token đi qua điểm kết thúc TLS, request routing, chính sách xác thực tại gateway | Dịch vụ phía sau tin vào header hoặc chính sách gateway; rò rỉ token/PII | `X-Forwarded-User` hoặc `X-User-Role` là dữ liệu đáng tin chỉ vì request đến từ mạng nội bộ |
| **IdP / OP / Authorization Server** | Tài khoản, phiên, quy trình xác thực, khóa ký, endpoint phát hành token, chính sách cấp quyền | Toàn bộ RP/RS/SP còn tin issuer hoặc khóa bị ảnh hưởng | Chữ ký còn xác minh được **không chứng minh** việc phát hành token đã được người dùng thật cho phép |
| **OAuth Resource Server / API** | Dữ liệu, token trong request/log/cache, credential gọi downstream, logic phân quyền | Tài nguyên của API và dịch vụ khác mà API có quyền gọi | Xâm nhập API **không nhất thiết** làm IdP mất an toàn; nhưng có thể lan rộng qua token và khóa service bị lộ |
| **CAS server hoặc kênh xác minh ticket** | Tài khoản, phiên CAS, quyền phát/xác minh Service Ticket, câu trả lời validation | Mọi CAS service phụ thuộc server hoặc kết quả xác minh của nó | CAS ticket hợp lệ ở một service có thể tùy tiện tái sử dụng ở mọi service |

**Phân biệt mức độ:** Bị lộ **public key/JWKS** công khai không đồng nghĩa mất khóa ký. Nhưng nếu **private signing key** hoặc quyền phát token của issuer bị xâm phạm, một token giả được ký bằng khóa đó có thể vượt qua kiểm tra mật mã thông thường. Khi ấy cần tạm ngừng tin issuer/khóa bị ảnh hưởng và điều tra, chứ không thể chỉ “bật thêm kiểm tra chữ ký”.

## 3. Ai chịu trách nhiệm? Phân định theo quyền kiểm soát

### 3.1. Chủ hệ thống IdP / OP / CAS server / Authorization Server

Bên phát hành bằng chứng danh tính chịu trách nhiệm bảo vệ **cơ sở danh tính và các khả năng phát hành**: xác thực người dùng, chính sách MFA/step-up, bảo vệ signing key và quản trị, quản lý phiên SSO, cấu hình ứng dụng được cấp quyền, thu hồi/đổi credential, phát hiện cấp token bất thường và thông báo sự cố cho những relying party có liên quan. Khi sử dụng broker, cần khai báo rõ broker nào **được quyền phát hành token riêng** và broker đó lấy bằng chứng upstream bằng cách nào.

Khi issuer có dấu hiệu bị chiếm quyền, chủ issuer cần xác minh nguồn xâm nhập, cô lập quyền phát token, vô hiệu hóa credential bị lộ, luân chuyển khóa và cung cấp danh sách issuer/client/đối tượng nhận/khoảng thời gian ảnh hưởng. **Luân chuyển khóa chỉ là một phần của khắc phục**: token đã phát, token đã bị đánh cắp, phiên RP đang tồn tại và bộ nhớ đệm JWKS của các bên nhận còn phải được xử lý.

### 3.2. Bên tiếp nhận: SP, RP hoặc CAS service

Bên tiếp nhận vẫn chịu trách nhiệm **xác minh bằng chứng đúng giao thức** và bảo vệ tài khoản/phiên/quyền bên mình. Ví dụ: chỉ chấp nhận IdP đã đăng ký; kiểm tra chữ ký và đối tượng nhận; áp dụng `state`/`nonce`/PKCE trong luồng thích hợp; ngăn replay; bảo vệ session cookie; giới hạn thời hạn phiên; không tự động nâng quyền từ claim thiếu kiểm chứng.

Khi đối tác hoặc issuer bị nghi xâm nhập, RP/SP phải có khả năng **ngừng chấp nhận nguồn tin cậy bị ảnh hưởng**, từ chối lần đăng nhập mới, vô hiệu hóa phiên đang liên quan khi cần, tạm ngừng tính năng nhạy cảm và kiểm tra dấu hiệu chiếm tài khoản. Không thể đổ toàn bộ trách nhiệm bảo vệ người dùng cho IdP chỉ vì ứng dụng dùng SSO.

### 3.3. Resource Server và chủ dữ liệu/API

Resource Server là **điểm quyết định cuối cùng** đối với tài nguyên API. API phải kiểm tra token có đúng issuer được cho phép, đúng audience của API, còn hạn, hợp lệ theo chính sách token type/sender-constrained nếu có, đúng scope/role **và** quyền nghiệp vụ đối với bản ghi được yêu cầu.

Một token hợp lệ chỉ nói rằng issuer đã cấp quyền nào đó; token **không tự chứng minh** người dùng được đọc đơn hàng của người khác. API phải kiểm tra ownership/tenant/đối tượng tài nguyên. Chủ API chịu trách nhiệm giới hạn dữ liệu cấp cho đối tác, phát hiện hoạt động bất thường và tạm khóa client/token/route liên quan khi có sự cố.

### 3.4. Bên vận hành gateway / proxy / identity broker

Chủ gateway phải bảo vệ đường đi request và ranh giới giữa dữ liệu **do client tự gửi** với dữ liệu **do thành phần đáng tin xác thực**. Header nhận dạng như `X-Authenticated-User`, `X-User-Id` hay `X-Roles` chỉ được backend chấp nhận nếu gateway tự xác minh danh tính, **xóa header cùng tên từ phía client**, chèn lại giá trị đáng tin và kết nối gateway–backend được bảo vệ để không thể bypass.

Nếu gateway xử lý TLS hoặc giữ bearer token, chủ gateway chịu trách nhiệm bảo vệ log, memory, credential và khóa; giới hạn quyền hệ thống; phân vùng đường truyền; cô lập dịch vụ và điều tra dấu hiệu lộ token. Nếu broker **phát hành token mới**, downstream phải có chính sách rõ broker được phép khẳng định claim nào; không tự cho broker quyền quản trị chỉ vì token có chữ ký đúng.

### 3.5. Đơn vị sở hữu quan hệ liên kết và ứng cứu sự cố

Tổ chức triển khai federation cần có **danh bạ quan hệ tin cậy**: đối tác nào, issuer/entityID nào, endpoint/key nào, client/service nào, quyền dữ liệu nào, người phụ trách kỹ thuật và kênh liên hệ sự cố. Hợp đồng/quy trình phải xác định trách nhiệm thông báo, chia sẻ bằng chứng, tạm dừng tích hợp, luân chuyển khóa, khôi phục và hỗ trợ người dùng, dựa trên pháp luật và nghĩa vụ áp dụng trong từng trường hợp.

**Không nên nhầm “người gây ra sự cố” với “người có hành động khẩn cấp”.** Đối tác có thể là bên bị hack, nhưng chủ API vẫn phải chặn truy cập nguy hiểm ở API; IdP có thể đang điều tra, nhưng RP vẫn phải bảo vệ phiên và dữ liệu cục bộ của mình.

## 4. Bốn tình huống điển hình và giới hạn lan truyền

### Tình huống A — Một đối tác OIDC RP bị xâm nhập

**Diễn biến:** RP của đối tác bị cài mã độc; token trong kho lưu trữ hoặc log bị lộ. Kẻ tấn công có thể gọi API của ta nếu nắm được **Access Token hợp lệ cho API**, thậm chí khi tài khoản IdP vẫn an toàn. Nếu refresh token/client credential bị lộ, khả năng duy trì truy cập có thể lâu hơn access token ban đầu.

**Ranh giới cần giữ:**

- **Access Token dành cho API A** không được dùng để gọi **API B** nếu `aud` khác nhau.
- Chỉ cấp scope tối thiểu cho client đối tác; scope không thay thế kiểm tra quyền trên từng tài nguyên.
- Giảm khả năng token bị tái sử dụng bằng thời hạn ngắn, token rotation khi thích hợp và sender-constrained token (mTLS/DPoP) nếu hệ sinh thái hỗ trợ; không giả định mọi Bearer token đều ràng buộc thiết bị.
- Đăng ký chính xác redirect URI, sử dụng Authorization Code + PKCE theo loại client và chính sách, bảo vệ client secret, hạn chế token lưu ở trình duyệt/log.
- Khi phát hiện sự cố: tạm ngừng client của đối tác, thu hồi refresh token/các token có thể thu hồi, đóng quyền API liên quan, xem xét phiên và dữ liệu đã bị truy cập, phối hợp đổi credential và kiểm tra lại tích hợp.

**Giới hạn cần hiểu:** Nếu đối tác có thể tạo phiên trong ứng dụng của chính họ, ta không thể dựa vào phiên đó làm chứng cứ độc lập rằng người dùng thật đã cho phép gọi API. Chỉ nhận token/claim đã được bên có thẩm quyền phát hành và đúng hợp đồng tin cậy.

### Tình huống B — Proxy hoặc gateway bị chiếm, backend tin header nhận dạng

**Diễn biến:** Backend dùng `X-User-Email` và `X-User-Role` từ reverse proxy để tạo tài khoản và cấp quyền. Kẻ tấn công kiểm soát proxy có thể chèn `X-User-Role: admin`; chữ ký ID Token upstream không giúp gì nếu backend **chỉ đọc header bị sửa**.

**Phòng vệ theo lớp:**

1. Chỉ định rõ backend **được phép nhận** identity header từ proxy nào; chặn đường kết nối trực tiếp từ internet/sidecar không được tin.
2. Proxy gỡ bỏ header nhận dạng do client gửi, **xác minh token/session trước khi tự tạo header**, và dùng đường truyền được xác thực tới backend (mTLS hoặc biện pháp tương đương trong mô hình triển khai).
3. Với giao dịch quan trọng, ưu tiên backend tự xác minh bằng chứng mật mã đầu cuối hoặc một assertion nội bộ có issuer/audience/thời hạn cụ thể, thay cho chỉ tin chuỗi text header.
4. Không biến `X-Forwarded-For`, `X-Forwarded-Proto` hay IP client thành xác thực danh tính. Header mạng phục vụ routing/origin và cần cấu hình trusted proxies riêng.
5. Nếu proxy/broker đã bị kiểm soát, tạm khóa đường tích hợp, loại bỏ phiên và credential đi qua điểm đó theo mức rủi ro, kiểm tra hành động bị nâng quyền và chỉ khôi phục sau khi thiết lập lại kênh tin cậy.

**Điểm tinh tế:** Nếu broker ký token downstream bằng khóa hợp lệ của **chính broker**, kiểm tra chữ ký downstream vẫn thành công. Vì vậy phải xác định broker chỉ được phát hành claim nào, mapping nào được phê duyệt và cách audit nguồn gốc khẳng định danh tính.

### Tình huống C — IdP/OP hoặc khóa ký bị xâm nhập

**Diễn biến:** Kẻ tấn công có thể sử dụng quyền phát token hợp lệ hoặc khóa ký bị lộ để tạo ID Token/SAML Assertion có nội dung giả. SP/RP thực hiện đúng thao tác kiểm tra chữ ký **vẫn có thể bị đánh lừa** bởi một issuer thực sự không còn đáng tin.

**Xử lý:** Tạm dừng hoặc thu hẹp quan hệ tin cậy với issuer/khóa/client bị ảnh hưởng; chặn đăng nhập/federation mới; đánh giá hủy phiên và thực hiện bước xác minh bổ sung độc lập cho tác vụ nhạy cảm. Chủ issuer cô lập tài khoản/khóa bị ảnh hưởng, phát hành lại khóa từ môi trường tin cậy và công bố quy trình chuyển đổi; các RP/RS đồng bộ trust store, kiểm soát cache JWKS/metadata, đánh giá lại token đã phát và các phiên cục bộ.

**Không ngộ nhận:** Chỉ đổi `kid`, cập nhật JWKS hoặc giảm `exp` tương lai **không lập tức thu hồi** mọi JWT đã phát hoặc phiên ứng dụng đã được tạo. JWT tự chứa thường không có cơ chế revocation tức thì nếu các verifier chỉ kiểm tra chữ ký và thời hạn. Có thể cần denylist theo `jti`/phiên, token introspection cho trường hợp phù hợp, thay đổi chính sách gateway/API, xóa phiên hoặc vô hiệu hóa toàn bộ issuer trong thời gian điều tra.

### Tình huống D — CAS service hoặc thành phần xác minh CAS bị xâm nhập

**Diễn biến:** CAS service bị chiếm có thể lộ phiên của ứng dụng và ticket trong log/redirect. Với cấu hình đúng, **Service Ticket** chỉ sử dụng một lần và được gắn với `service`; service phải gọi CAS server để xác minh ticket. Nếu CAS server hoặc kết quả validation bị làm giả, các service dựa trên câu trả lời ấy cũng chịu ảnh hưởng.

**Phòng vệ:** Đăng ký chính xác service URL; dùng HTTPS; xác minh ticket qua server tin cậy; không coi chuỗi `ST-...` xuất hiện trong query là danh tính đã xác thực; không ghi ticket vào log; xử lý replay và session fixation; tạm dừng đăng nhập CAS nếu không thể tin endpoint validation. Khi service bị hack, vô hiệu hóa phiên tại service và rà soát ticket/log; khi CAS server bị hack, phạm vi đánh giá phải mở rộng tới các service liên kết.

## 5. Kiểm tra bằng chứng đúng giao thức tại ranh giới

| Giao thức và vai trò nhận | Điều phải kiểm tra | Khi nghi ngờ bên phát hoặc trung gian |
| --- | --- | --- |
| **SAML SP** | IdP/entityID tin cậy, chữ ký ở vị trí đúng, điều kiện thời gian, `AudienceRestriction`, `Recipient`/`Destination`, `InResponseTo` khi dùng SP-initiated SSO, chống replay, certificate rollover có kiểm soát | Tạm ngừng metadata/khóa IdP bị nghi, không nhận assertion từ nguồn không được đăng ký, kiểm tra ACS và các phiên ứng dụng |
| **OIDC RP** | OP `issuer`, chữ ký ID Token, `aud`/`azp` khi áp dụng, `exp`, `nonce` khi được dùng, `state`, authorization code + PKCE phù hợp, redirect URI đã đăng ký | Tạm dừng registration/issuer bị nghi, hủy hoặc đánh giá phiên RP, kiểm tra liên kết tài khoản theo cặp `iss` + `sub` |
| **CAS service** | Service Ticket trả về đúng `service`, xác minh với CAS server, ticket còn hợp lệ/chưa dùng, nguồn validation an toàn | Dừng chấp nhận validation từ CAS server bị nghi và hủy phiên ứng dụng liên quan |
| **OAuth Resource Server** | Access Token có chữ ký/issuer được tin, `aud` dành cho API, thời hạn, chính sách token type, scope/quyền và ownership/tenant | Thu hẹp/khóa client, issuer, route hoặc scope; xử lý token bị lộ và điều tra truy cập dữ liệu |
| **Gateway / identity broker** | Nguồn gốc request, token/claim upstream, chính sách ánh xạ danh tính, issuer/audience của token downstream, integrity của kênh tới backend | Cô lập đường đi/khóa ký của broker, ngừng tin identity header hoặc token downstream bị ảnh hưởng |

**Không thay ID Token cho Access Token**: ID Token là khẳng định xác thực **dành cho OIDC RP**; Resource Server cần **Access Token dành cho API** theo hợp đồng OAuth. **Không chỉ so sánh email** giữa các issuer/tenant khi liên kết tài khoản: địa chỉ email có thể thay đổi, tái cấp phát hoặc không được xác minh. Dùng định danh ổn định theo issuer/tenant, thường là `iss` + `sub` trong OIDC, và quy trình liên kết có chứng minh sở hữu phù hợp.

Nếu dùng nhiều issuer, **không chọn khóa xác minh một cách vô điều kiện dựa trên `iss` do token chưa xác thực tự khai báo**. Chỉ dispatch tới **danh sách issuer đã được phê duyệt** và bảo đảm mỗi issuer có cấu hình audience, thuật toán, claim mapping, scope, tenant và chính sách riêng. Không tự tải JWKS từ URL bất kỳ lấy trong token do client gửi.

## 6. Những lớp kiểm soát nên thiết kế trước khi sự cố xảy ra

### 6.1. Hợp đồng tin cậy kỹ thuật

Với mỗi đối tác, lưu và phê duyệt rõ: môi trường (dev/staging/prod), issuer/entityID và certificate/JWKS, endpoint metadata, audience/service/ACS/redirect URI, tenant hợp lệ, client ID, scope/claim mapping, mức xác thực yêu cầu, quyền dữ liệu, phương thức logout/revocation, thời hạn/chu kỳ thay khóa, chủ sở hữu và điểm liên hệ sự cố.

Không cho phép tự mở rộng trust bằng cách chấp nhận wildcard redirect URI, mọi issuer, mọi audience, mọi thuật toán ký hoặc mọi địa chỉ proxy. Khóa ký công khai có thể luân chuyển hợp lệ; cần quản lý rollover được xác thực và có đường hủy tin cậy khẩn cấp.

### 6.2. Quyền tối thiểu và hạn chế lan truyền

- Tách issuer, client và khóa/credential theo **môi trường và đối tác**; tránh client dùng chung cho nhiều đối tác.
- Cấp scope, audience và role tối thiểu; Resource Server kiểm tra quyền trên **đối tượng cụ thể**, không chỉ ở tầng route.
- Tránh gửi PII không cần thiết trong token, header, redirect hoặc log. Mã hóa dữ liệu nhạy cảm khi lưu và truyền; bảo vệ secret bằng cơ chế quản lý bí mật.
- Đặt thời hạn token/phiên phù hợp; giới hạn refresh token, ràng buộc token với client hoặc sender khi có thể. Bảo vệ cookie bằng `Secure`, `HttpOnly`, `SameSite` khi phù hợp, CSRF và chống session fixation.
- Với yêu cầu rủi ro cao (thay email phục hồi, chuyển tiền, cấp quyền quản trị), dùng **reauthentication/step-up qua nguồn còn đáng tin** và kiểm tra nghiệp vụ độc lập; không tin tuyệt đối claim `amr`/`acr` được relay từ broker bị nghi.
- Thiết kế một công tắc vận hành để vô hiệu hóa **một đối tác/issuer/route** mà không làm sập mọi tích hợp khác; kiểm tra quy trình này định kỳ.

### 6.3. Quan sát và điều tra mà không làm lộ thêm bí mật

Ghi log cấu trúc của sự kiện xác thực/ủy quyền: timestamp chuẩn hóa, issuer, `client_id` hoặc `azp` khi có, audience, tenant, mã tương quan request, kết quả validation, endpoint và quyết định cho/không cho truy cập. Các thông tin như `sub` cần xử lý theo chính sách bảo vệ dữ liệu; cân nhắc pseudonymization và quyền truy cập log.

**Không ghi nguyên văn** Access Token, ID Token, SAML Assertion, CAS ticket, password, refresh token, session cookie hoặc Authorization header. Log bị lộ có thể tự trở thành nguồn token dùng để tấn công. Giới hạn quyền truy cập logs và giữ bằng chứng sự cố theo chính sách lưu giữ.

Tín hiệu cảnh báo hữu ích gồm: đột biến token issuance, nhiều token cho cùng chủ thể từ client lạ, scope/audience bất thường, token từ issuer mới, đăng nhập tenant khác, chuyển đổi vai trò khó giải thích, nhiều lỗi signature/nonce, replay ticket/assertion, gọi API hàng loạt và thay đổi JWKS/metadata không theo lịch.

## 7. Áp dụng trong Spring Security: API tự kiểm tra token ở ranh giới của mình

Giả sử backend Spring Boot bảo vệ `/partner-api/**` và chỉ tin **Access Token JWT** từ issuer đối tác đã đăng ký. Ví dụ dưới đây dùng **Spring Security servlet với Java 17+**, dependency Spring Web, Spring Security, OAuth2 Resource Server và JOSE (hoặc Spring Boot starter tương ứng). Đây là **class cấu hình của một ứng dụng Spring Boot**, không phải file Java độc lập chạy bằng `javac` khi chưa có các dependency và issuer thật.

```yaml
# application.yml — URI/định danh minh họa; thay bằng cấu hình đã phê duyệt
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.partner.example/realms/partners
          audiences:
            - api://profile
```

Khai báo `issuer-uri` giúp Spring Security lấy cấu hình xác thực phù hợp và kiểm tra issuer khi xử lý JWT; `audiences` yêu cầu token dành cho **API này**. JWT còn cần vượt kiểm tra chữ ký, thời gian và các ràng buộc của decoder. Endpoint chỉ mở cho scope dự định:

```java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PartnerApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/partner-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/partner-api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain defaultDeny(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
    }
}
```

**Ý nghĩa bảo vệ:** API tự xác minh JWT trước khi cấp dữ liệu, kiểm tra `iss` và `aud` theo cấu hình; GET `/partner-api/profile` đòi `SCOPE_profile.read`. Các route khác trong cùng vùng `/partner-api/**` bị từ chối; chuỗi mặc định từ chối các route còn lại trong ví dụ tối giản. `STATELESS` và tắt CSRF chỉ dành cho chuỗi API nhận Bearer token không dựa vào session cookie; **không sao chép lựa chọn này sang trang web có cookie login**. Với dữ liệu nhiều người dùng, controller/service **vẫn phải kiểm tra** người gọi được phép đọc đúng profile cụ thể.

**Giới hạn không được bỏ qua:** Nếu chính issuer đối tác đã bị chiếm và phát Access Token giả có `iss`, `aud`, scope, chữ ký và thời hạn hợp lệ, cấu hình trên **có thể chấp nhận token giả** vì nguồn chứng thực đã mất an toàn. Phải có quy trình **tạm ngừng chấp nhận issuer hoặc route bị ảnh hưởng**, cập nhật trust configuration và triển khai biện pháp chứa sự cố ở API/network. Việc chỉ luân chuyển public key trong cấu hình mà không xử lý phiên/token cũ không đủ.

Đối với ứng dụng web dùng **`oauth2Login`**, Spring Security xử lý OIDC RP theo client registration; cần giới hạn issuer, redirect URI, scope, session và liên kết `iss`/`sub`. Với **SAML**, dùng `saml2Login`/`RelyingPartyRegistration` và kiểm tra assertion theo SAML. Với **CAS**, dùng cơ chế validation ticket CAS tương thích dự án. Ba loại SSO này **không thể thay thế** bằng cách tự parse JWT trong controller.

### Ví dụ kiểm thử ở cấp tích hợp

Trong môi trường thử nghiệm có issuer và dữ liệu mẫu, xác nhận các trường hợp:

| Dữ liệu yêu cầu | Kết quả mong muốn |
| --- | --- |
| Access Token hợp lệ, đúng `iss`, `aud`, còn hạn, có `profile.read`, đúng quyền bản ghi | Được phép truy cập endpoint được khai báo |
| Token ký bởi issuer khác hoặc JWT có `aud` của API khác | Bị từ chối xác thực |
| Token hết hạn hoặc chữ ký không hợp lệ | Bị từ chối xác thực |
| Token hợp lệ nhưng thiếu `profile.read` | Không được cấp quyền endpoint |
| Token đúng scope nhưng truy cập profile thuộc user/tenant khác | Bị từ chối bởi kiểm tra quyền nghiệp vụ |
| ID Token OIDC được gửi thay Access Token | Bị từ chối theo chính sách token type/audience dành cho API; kiểm thử riêng để bảo đảm cấu hình issuer không vô tình chấp nhận loại token sai |
| Đối tác bị đưa vào chế độ đình chỉ | Mọi request phụ thuộc trust đó bị chặn, kể cả token chưa hết hạn |

HTTP `401` thường thể hiện xác thực chưa hợp lệ; `403` thường thể hiện đã xác thực nhưng không đủ quyền. Kết quả cụ thể phụ thuộc exception handling, endpoint và cách kiểm tra quyền; kiểm thử kết quả thực tế thay vì đoán từ biểu mẫu token.

## 8. Playbook ứng cứu khi phát hiện xâm nhập

### Giai đoạn 1 — Xác định và hạn chế ngay phạm vi tin cậy

1. Ghi lại tín hiệu, mốc thời gian, đối tác, issuer/tenant/client, service và loại artifact có thể bị lộ; mở đầu mối xử lý sự cố chung.
2. **Đóng đường có thể bị khai thác**: đình chỉ client/issuer/route, vô hiệu hóa khóa hoặc trust store liên quan, cô lập gateway/broker bị chiếm. Chọn phạm vi chặn hẹp nhất **mà vẫn bảo vệ được** toàn bộ đường tấn công; nếu chưa rõ phạm vi, áp dụng điều kiện an toàn hơn.
3. Thu hồi token/refresh token và phiên theo khả năng thực tế; nếu JWT không có revocation tức thời, chặn tại resource server, gateway, issuer trust hoặc chính sách phân quyền. Buộc xác thực lại khi thích hợp.
4. Bảo vệ bằng chứng và dịch vụ liên quan: snapshot/forensic theo quy trình, giữ log cần thiết, tránh ghi secret/ticket mới vào hệ thống đã bị nghi xâm nhập.

### Giai đoạn 2 — Điều tra ảnh hưởng thực tế

1. Xác định **bị lộ gì**: private signing key, client secret, refresh/access token, session cookie, CAS ticket, thông tin cá nhân, identity header hay quyền chỉnh claim.
2. Xác định **đường lan truyền**: token nào có audience API nào, scopes nào, tenant nào, thời gian hiệu lực và các downstream service nào được gọi.
3. Đối chiếu log issuer, RP/SP, CAS server, gateway, API và dữ liệu nghiệp vụ. Chỉ log thành công/thất bại có thể không đủ; kiểm tra các thao tác bất thường và thay đổi dữ liệu.
4. Đánh giá liên kết tài khoản, tạo tài khoản tự động (JIT), cấp vai trò, thay đổi thông tin khôi phục, phiên còn sống và thao tác nhạy cảm trong cửa sổ ảnh hưởng.
5. Phối hợp thông báo với đối tác và chủ dữ liệu; xác định nghĩa vụ thông báo người dùng/cơ quan quản lý theo hợp đồng và quy định áp dụng, không mặc định một thời hạn pháp lý chung cho mọi tình huống.

### Giai đoạn 3 — Khôi phục tin cậy có điều kiện

1. Chỉ mở lại khi đối tác chứng minh đã cô lập nguyên nhân gốc, thay credential/key cần thiết, khắc phục cấu hình/ứng dụng, rà soát các khả năng truy cập trái phép và cung cấp bằng chứng kiểm thử.
2. Cập nhật issuer metadata/JWKS/trust store thông qua kênh có xác thực; xác nhận mọi consumer đã xử lý cache và khóa/credential cũ theo kế hoạch.
3. Kiểm thử toàn bộ luồng hợp lệ **và** luồng giả mạo: token sai audience, token cũ, signature/nonce/replay, header do client chèn, khác tenant, scope thừa, service ticket không đúng service.
4. Xem xét vô hiệu hóa phiên cũ, yêu cầu người dùng đăng nhập lại, xác nhận mọi quyền đã cấp bất thường được thu hồi và kiểm tra tính toàn vẹn dữ liệu.
5. Mở lại theo từng client/route/tenant, giám sát chặt dấu hiệu tái diễn; lưu quyết định, chủ sở hữu và bài học sau sự cố.

**Thực hành quan trọng:** Xác minh **cả hành vi của issuer lẫn hành vi của consumer** sau khi sửa. Chỉ nói “đối tác đã vá máy chủ” chưa đủ để chứng minh các access token bị đánh cắp, phiên RP hoặc role sai trước đó đã hết tác dụng.

## 9. Quyền, bằng chứng và giới hạn của từng biện pháp

| Biện pháp | Giải quyết tốt điều gì? | Không tự giải quyết điều gì? |
| --- | --- | --- |
| HTTPS/mTLS giữa các hop | Giảm nghe lén, giả mạo kết nối; xác thực peer khi triển khai đúng | Thành phần endpoint **đã bị chiếm quyền** vẫn có thể đọc/sửa dữ liệu mà nó được phép xử lý |
| Ký số assertion/JWT | Phát hiện sửa đổi trên đường truyền khi khóa phát hành còn đáng tin | Bên phát hành hoặc private signing key **đã bị xâm nhập** có thể tạo bằng chứng giả nhưng chữ ký hợp lệ |
| `issuer` + `audience` | Giới hạn nguồn và đối tượng nhận token | Token do chính issuer tin cậy nhưng bị chiếm phát hành có thể vẫn qua kiểm tra |
| `scope`/role + kiểm tra quyền bản ghi | Hạn chế thao tác và tài nguyên có thể truy cập | Nếu claim nâng quyền do broker được tin phát sai, cần chính sách nhận claim chặt và đối chiếu quyền nội bộ |
| Token ngắn hạn + rotation/revocation | Giảm thời gian tận dụng token bị lộ, hỗ trợ ứng cứu | JWT tự chứa và phiên cục bộ có thể tiếp tục tồn tại khi không có đường cưỡng chế chặn |
| `state`, `nonce`, PKCE và replay protection | Giảm CSRF/login injection, tráo response, lạm dụng authorization code và tái sử dụng assertion/ticket trong luồng tương ứng | Không chống được mọi hành vi từ IdP/OP thực sự đã bị chiếm |
| Network segmentation và loại bỏ identity header giả | Hạn chế bypass gateway hoặc thao túng danh tính từ client không được tin | Chưa đủ nếu chính gateway được tin đã bị chiếm |
| Log, cảnh báo và phối hợp sự cố | Rút ngắn thời gian phát hiện, xác định tác động và xử lý | Không thay thế kiểm tra truy cập ở thời điểm nhận request |

## 10. Bài tập tình huống có đáp án

**Tình huống 1:** Đối tác SaaS bị lộ client secret. Người dùng vẫn đăng nhập IdP an toàn. Có thể tiếp tục cho client đó gọi API vì IdP chưa bị hack?

**Đáp án:** Không thể kết luận an toàn chỉ từ trạng thái IdP. Cần xác định secret lộ có thể đổi authorization code hay sử dụng grant nào, có lộ refresh/access token không, scope/audience nào đã cấp. Tạm khóa hoặc thay credential client bị ảnh hưởng, xử lý token/phiên liên quan, kiểm tra log và chỉ khôi phục sau khi giới hạn đường lạm dụng.

**Tình huống 2:** Gateway gửi `X-User-Role: admin` tới backend. Request đi qua mTLS hợp lệ nhưng gateway đã bị chiếm. Backend có thể cấp quyền admin?

**Đáp án:** mTLS xác thực gateway như một peer, không bảo đảm gateway đang phát claim đúng. Backend phải có chính sách quyền riêng, giới hạn claim trusted, có thể yêu cầu bằng chứng xác minh độc lập hoặc từ chối đường giao dịch khi nguồn claim bị nghi xâm nhập.

**Tình huống 3:** IdP thông báo đã xoay khóa ký. Một token cũ vẫn được API chấp nhận do JWKS cache và `exp` còn hạn. Sự cố đã kết thúc?

**Đáp án:** Chưa. Cần điều phối cập nhật khóa và cache, thu hồi hoặc chặn token có rủi ro, kiểm tra phiên cục bộ, xác định mốc xâm nhập và khả năng issuer đã cấp token giả trước khi xoay khóa. Có thể phải đình chỉ tin issuer/đường tích hợp tạm thời.

**Tình huống 4:** API nhận JWT đúng chữ ký và scope `orders.read`, nhưng `aud` thuộc API khác. Có cho phép?

**Đáp án:** Không. Token không dành cho Resource Server hiện tại. Phải từ chối dù chữ ký/issuer/scope hợp lệ; đồng thời kiểm tra quyền truy cập đơn hàng cụ thể ngay cả khi audience đúng.

**Tình huống 5:** Broker bị xâm nhập nhưng vẫn ký token downstream bằng khóa riêng hợp lệ, đồng thời biến thuộc tính `employee` thành `administrator`. Có thể dựa vào chữ ký để tiếp tục tin token?

**Đáp án:** Không. Chữ ký xác nhận token được phát bởi broker; nó không đảm bảo broker đã trung thực với dữ liệu upstream. Phải cô lập broker, ngừng chấp nhận claim bị ảnh hưởng, kiểm tra mapping/quyền và các hành động đã thực thi.

## 11. Checklist vận hành và kết luận kỹ thuật

- [ ] Mỗi liên kết federation có owner, issuer/entityID, audience/service, key, tenant, client, scope và kênh liên hệ đã phê duyệt.
- [ ] SP/RP/CAS service/Resource Server xác thực đúng artifact và không dùng token sai mục đích.
- [ ] Mọi header danh tính từ proxy được kiểm soát nguồn, xóa giá trị do client tự gửi, bảo vệ kênh proxy–backend và chống bypass.
- [ ] Không cấp quyền dữ liệu dựa riêng vào email, role text header hoặc claim của broker chưa kiểm soát.
- [ ] Khóa, token, session và client credential có chính sách luân chuyển/thu hồi phù hợp; log không chứa bí mật.
- [ ] Có thể khóa từng partner/issuer/route và cưỡng chế ở **điểm sử dụng tài nguyên**, kể cả khi token chưa hết hạn.
- [ ] Có quy trình đối chiếu log nhiều bên, đánh giá tài khoản/dữ liệu ảnh hưởng, liên hệ đối tác, khôi phục và hậu kiểm.
- [ ] Các ca thử về sai issuer/audience/scope/tenant, replay, giả header và issuer bị đình chỉ được diễn tập.

**Điểm cần nhớ:** Trong SSO/federation, mỗi bên bảo vệ **ranh giới mà mình kiểm soát**. Khi đối tác hoặc trung gian bị xâm nhập, bằng chứng được phát trước đó và những assertion/token tiếp tục đi qua điểm bị chiếm phải được **đánh giá lại niềm tin**. Chữ ký, TLS, scope và phiên SSO đều hữu ích nhưng không có cơ chế đơn lẻ nào bảo vệ được danh tính nếu hệ thống có quyền phát hoặc biến đổi bằng chứng đã bị chiếm. Khả năng ngừng tin cậy có chọn lọc, giới hạn quyền và thu hồi phiên/token là phần không thể thiếu của kiến trúc.

## Tài liệu tham khảo

- [NIST SP 800-63C-4 — Digital Identity Guidelines: Federation and Assertions (2025)](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): ranh giới federation và bảo vệ assertion.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validation, issuer/audience, decoder và scope.
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `issuer-uri` và `audiences` trong cấu hình.
- [Spring Security — SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): cấu hình Service Provider và kiểm tra assertion.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, validation và vai trò Relying Party.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ luồng OAuth, client, redirect và token.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tách biệt mục đích token, thuật toán và dữ liệu xác minh.
