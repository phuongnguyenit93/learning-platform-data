# Quy trình ứng phó khi token truy cập hoặc refresh token bị lộ

> **Chương:** Vòng đời token  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho hệ thống sử dụng access token, refresh token và OAuth 2.0 nói chung, không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 1. Vì sao cần quy trình ứng phó riêng?

Access token và refresh token là credential có thể cho phép người sở hữu thực hiện hành động thay mặt một chủ thể hoặc client. Khi token bị lộ, kẻ tấn công có thể sử dụng nó trong phạm vi quyền và thời hạn còn hiệu lực.

Mức độ ảnh hưởng phụ thuộc vào loại token:

- **Access token:** thường được gửi đến resource server để truy cập API. Nếu là JWT self-contained, resource server có thể xác minh cục bộ mà không hỏi authorization server ở mỗi request.
- **Refresh token:** được gửi đến authorization server để xin access token mới. Token này thường có vòng đời dài hơn và có thể duy trì khả năng truy cập sau khi access token hiện tại hết hạn.
- **Token family/session:** một nhóm refresh token được liên kết qua rotation hoặc cùng một phiên. Việc lộ một token có thể cho thấy cả chuỗi phiên đã bị xâm phạm.
- **Signing key hoặc client credential:** đây không phải token người dùng, nhưng nếu bị lộ có thể ảnh hưởng đến nhiều token hoặc nhiều client hơn.

Không thể chỉ xóa token khỏi nơi bị lộ rồi coi sự cố đã kết thúc. Bản sao có thể đã được thu thập, đồng bộ hoặc sử dụng trước khi phát hiện. Cần phối hợp containment, revocation, điều tra, phục hồi và xác minh.

**Mục tiêu của incident response:**

1. Ngăn token tiếp tục được sử dụng trái phép.
2. Thu hồi đúng phạm vi, tránh bỏ sót credential liên quan.
3. Giữ bằng chứng cần thiết mà không phát tán thêm secret.
4. Khôi phục quyền truy cập hợp lệ cho người dùng và client.
5. Xác minh nguyên nhân rò rỉ đã được khắc phục.

## 2. Phân loại credential trước khi hành động

Không phải mọi loại token đều có cùng cách thu hồi. Bước đầu tiên là xác định chính xác credential bị lộ và vai trò của nó.

| Credential | Mục đích | Rủi ro khi bị lộ | Hành động trọng tâm |
|---|---|---|---|
| JWT access token | Gọi resource server | Kẻ khác có thể gọi API theo scope/audience đến khi token hết hạn hoặc bị chặn | Thu hồi jti/session/user state, introspection hoặc cơ chế trạng thái tương đương |
| Opaque access token | Gọi resource server | Có thể bị dùng như bearer token khi còn active | Thu hồi tại authorization server hoặc introspection state |
| Refresh token | Xin access token mới | Có thể duy trì truy cập và tạo access token mới | Revoke refresh token, token family hoặc authorization grant |
| Authorization code | Hoàn tất authorization flow | Có thể bị đổi lấy token nếu còn hiệu lực và chưa sử dụng | Ngăn redemption, kiểm tra PKCE/state, thu hồi phiên/grant liên quan |
| Session cookie | Duy trì phiên đăng nhập | Có thể cho phép chiếm phiên trình duyệt | Thu hồi session và xoay credential phiên |
| Client secret/private key | Xác thực confidential client | Có thể cho phép client giả mạo hoặc lấy token theo quyền client | Disable/rotate client credential, điều tra token phát hành cho client |
| Private signing key | Ký JWT | Có thể tạo JWT giả được xác minh như token của issuer | Ngừng tin key, rotate và cập nhật trust cache trên mọi resource server |

Trước khi thực hiện thu hồi, xác định token thuộc:

- Issuer nào.
- Subject hoặc client nào.
- Audience/resource server nào.
- Scope/role nào.
- Thời điểm phát hành và hết hạn.
- Session hoặc token family nào.
- Có sender constraint như mTLS hoặc DPoP hay không.

Chỉ dùng claims sau khi token đã được xác minh trong môi trường điều tra tin cậy. Nếu token chưa xác minh, các giá trị `iss`, `sub`, `aud`, `jti` bên trong chỉ là dữ liệu do người gửi cung cấp.

## 3. Dấu hiệu phát hiện token bị lộ hoặc bị lạm dụng

Sự cố có thể được phát hiện bởi người dùng, hệ thống giám sát hoặc bên thứ ba.

### 3.1. Dấu hiệu từ người dùng và vận hành

- Người dùng báo có request hoặc giao dịch họ không thực hiện.
- Token xuất hiện trong URL, browser history, screenshot, ticket, chat hoặc log.
- Refresh token được sử dụng từ thiết bị, địa chỉ mạng hoặc vị trí bất thường.
- Một refresh token cũ bị sử dụng lại sau khi rotation đã cấp token mới.
- Access token được dùng ngoài khung thời gian hoặc hành vi thông thường.
- API nhận nhiều request với cùng một token từ các nguồn không liên quan.
- Token bị phát hiện trong repository, artifact, backup hoặc hệ thống telemetry.
- Hệ thống bên thứ ba thông báo dữ liệu credential đã bị truy cập.

### 3.2. Dấu hiệu từ telemetry

Có thể theo dõi các tín hiệu:

| Tín hiệu | Điều cần xem xét |
|---|---|
| Cùng `jti` xuất hiện từ nhiều client/network khác nhau | Token có thể đã bị sao chép hoặc chia sẻ trái phép. |
| Refresh token reuse sau rotation | Có thể là replay hoặc hai bên cùng sử dụng một token đã bị thay thế. |
| Tăng đột biến request với scope nhạy cảm | Có thể là lạm dụng quyền của token bị lộ. |
| Đăng nhập/refresh từ thiết bị mới | Có thể là hành vi hợp lệ hoặc dấu hiệu chiếm đoạt phiên. |
| Token được dùng sau khi người dùng logout | Kiểm tra revocation propagation và cache. |
| Nhiều lỗi xác minh trước khi có request thành công | Có thể là dò token, key ID hoặc cấu hình xác thực. |
| Token được dùng từ hệ thống không nằm trong client inventory | Kiểm tra credential leakage và client identity. |

Không kết luận token bị đánh cắp chỉ dựa trên một địa chỉ IP khác. NAT, VPN, roaming và mạng di động có thể làm thay đổi IP hợp lệ. Cần kết hợp nhiều tín hiệu, mức quyền và hành vi.

### 3.3. Ghi nhận thời gian

Incident record nên có ít nhất:

- Thời điểm phát hiện.
- Thời điểm ước tính bắt đầu rò rỉ.
- Thời điểm token được phát hành và hết hạn.
- Thời điểm lần cuối token được sử dụng hợp lệ.
- Thời điểm revoke được yêu cầu và thời điểm mọi resource server xác nhận đã áp dụng.
- Múi giờ thống nhất, ưu tiên UTC trong log và timeline.

Thời gian phát hiện không nhất thiết là thời điểm token bắt đầu bị lộ.

## 4. Nguyên tắc ứng phó

### 4.1. Contain trước, điều tra song song

Nếu có bằng chứng hợp lý rằng token còn khả năng bị sử dụng, ưu tiên chặn khả năng lạm dụng. Không trì hoãn revoke chỉ để hoàn tất phân tích nguyên nhân.

Tuy vậy, cần lưu metadata và bằng chứng không chứa secret trước khi dữ liệu liên quan bị rotate hoặc xóa. Có thể ghi fingerprint, issuer, subject đã xác minh, jti, audience, scope, thời điểm và correlation ID thay vì sao chép nguyên token vào incident ticket.

### 4.2. Thu hồi theo phạm vi nhỏ nhất đủ bảo vệ

Chọn đúng phạm vi:

- Một token: revoke theo jti.
- Một phiên/thiết bị: revoke session hoặc sid.
- Một chủ thể: disable account hoặc tăng security/token version.
- Một token family/grant: revoke refresh token family hoặc authorization grant.
- Một client: disable client hoặc rotate client credential.
- Một signing key: loại key khỏi trust set khi chính key đó bị xâm phạm.
- Toàn tenant/hệ thống: chỉ dùng khi phạm vi ảnh hưởng thực sự rộng.

Thu hồi quá hẹp có thể bỏ sót token liên quan. Thu hồi quá rộng có thể làm gián đoạn dịch vụ và người dùng không bị ảnh hưởng. Phạm vi cần dựa trên bằng chứng và threat model.

### 4.3. Không phát tán token trong quá trình xử lý

- Không dán token nguyên vẹn vào chat, email, ticket hoặc báo cáo.
- Không gửi token cho người hỗ trợ để “kiểm tra giúp”.
- Không ghi token vào command history hoặc shell transcript.
- Không chụp màn hình chứa token.
- Không thêm token vào query string của công cụ nội bộ.
- Không dùng token bị nghi lộ để thử thủ công trên API production.

Nếu cần định danh token, dùng `jti` sau khi xác minh, hoặc fingerprint HMAC với khóa dành riêng cho incident correlation. Không dùng hash/fingerprint như bằng chứng token hợp lệ.

## 5. Quy trình phản ứng tổng quát

~~~mermaid
flowchart TD
    A["Phát hiện hoặc nhận báo cáo token bị lộ"] --> B["Phân loại credential và phạm vi"]
    B --> C["Đánh giá khả năng bị sử dụng"]
    C --> D["Contain: revoke/block/disable theo phạm vi"]
    D --> E["Phát tán trạng thái revoke đến resource servers"]
    E --> F["Xác minh token cũ bị từ chối"]
    F --> G["Điều tra log và nguyên nhân rò rỉ"]
    G --> H["Khắc phục nguồn rò rỉ và credential liên quan"]
    H --> I["Cấp lại credential và khôi phục truy cập"]
    I --> J["Theo dõi, audit và đóng sự cố"]
~~~

Các bước có thể diễn ra song song nếu cần. Ví dụ, nhóm vận hành thu hồi token trong khi nhóm bảo mật bảo toàn log và nhóm ứng dụng sửa điểm ghi token vào URL.

## 6. Ứng phó khi access token bị lộ

### 6.1. Xác định khả năng sử dụng

Thu thập metadata đã xác minh:

- `iss`, `sub`, `aud`, `jti`.
- `iat`, `nbf`, `exp`.
- Scope/role và mức nhạy cảm của API.
- Session ID hoặc token version nếu profile có.
- Client đã nhận token và nguồn phát hành.
- Token có sender-constrained hay là bearer token thuần túy.

Đánh giá liệu token còn hạn, audience có truy cập tài nguyên quan trọng không và có bằng chứng token đã được sử dụng trái phép không.

### 6.2. Chặn token cụ thể

Với JWT access token self-contained, resource server có thể xác minh chữ ký cục bộ và không biết token đã bị revoke nếu không có cơ chế trạng thái bổ sung.

Các lựa chọn:

- Thêm `(iss, jti)` vào denylist.
- Revoke session ID nếu token thuộc một phiên.
- Tăng token/security version của subject nếu cần chặn toàn bộ token cũ.
- Đánh dấu account/client bị disable nếu phạm vi sự cố yêu cầu.
- Dùng introspection hoặc trạng thái active tập trung nếu resource server hỗ trợ.
- Chờ `exp` chỉ khi mức rủi ro cho phép và không có yêu cầu revoke sớm.

Denylist cần được áp dụng ở mọi resource server nhận token. Một bản ghi chỉ có tác dụng ở instance đã cập nhật không đủ để containment toàn hệ thống.

### 6.3. Đánh giá access token đã được phát hành từ refresh token

Nếu access token bị lộ, cần xác định refresh token/session đã tạo ra nó có còn an toàn không.

- Nếu chỉ access token bị lộ do một log riêng lẻ, có thể revoke đúng access token và giữ session nếu không có dấu hiệu compromise rộng hơn.
- Nếu refresh token, session cookie hoặc thiết bị cũng bị lộ, cần revoke cả session/token family.
- Nếu có refresh token reuse hoặc hoạt động đáng ngờ, coi khả năng compromise rộng hơn và điều tra toàn bộ token được cấp từ phiên đó.

### 6.4. Giới hạn quyền trong thời gian điều tra

Nếu chưa thể xác định chính xác token nào bị lộ, có thể tạm thời:

- Disable subject hoặc client có liên quan.
- Tạm chặn scope/action có rủi ro cao.
- Yêu cầu re-authentication hoặc MFA.
- Giảm thời hạn token mới.
- Tăng giám sát các endpoint nhạy cảm.

Các biện pháp tạm thời cần có chủ sở hữu và thời hạn xem xét để tránh trở thành thay đổi quyền vô thời hạn.

## 7. Ứng phó khi refresh token bị lộ

Refresh token thường có mức rủi ro cao vì có thể được dùng để xin access token mới. Một refresh token bị lộ có thể tạo ra chuỗi truy cập kéo dài, đặc biệt nếu không có rotation, sender constraint hoặc reuse detection.

### 7.1. Thu hồi refresh token

- Gọi token revocation endpoint hoặc thao tác revoke tương đương tại authorization server.
- Xác định authorization grant và token family liên quan.
- Thu hồi các refresh token thay thế trong cùng family nếu có.
- Theo chính sách, thu hồi access token đã phát hành từ cùng grant.
- Chặn refresh token tiếp tục được sử dụng để mint access token mới.
- Yêu cầu người dùng xác thực lại nếu phiên không còn đáng tin.

RFC 7009 định nghĩa OAuth 2.0 Token Revocation. Khi revoke refresh token, authorization server được khuyến nghị thu hồi cả access token dựa trên cùng authorization grant. Tuy nhiên, điều này không bảo đảm mọi resource server đang xác minh JWT offline sẽ tự biết trạng thái mới. Cần cơ chế truyền trạng thái hoặc chặn access token còn hiệu lực.

### 7.2. Rotation và phát hiện reuse

Với refresh token rotation:

1. Client gửi refresh token hiện tại.
2. Authorization server cấp refresh token mới.
3. Refresh token cũ bị vô hiệu hóa.
4. Nếu token cũ bị dùng lại, đó có thể là dấu hiệu token đã bị sao chép hoặc client sử dụng đồng thời không đúng cách.
5. Authorization server có thể revoke token family và yêu cầu xác thực lại.

Khi phát hiện reuse, không chỉ đánh dấu refresh token cũ không hợp lệ rồi tiếp tục cấp token mới. Cần xác định family/session bị ảnh hưởng và vô hiệu hóa các token đang hoạt động trong family theo policy.

Cũng cần tránh false positive do client gửi request refresh đồng thời, retry sau timeout hoặc race condition. Client và authorization server phải tuân thủ giao thức rotation, xử lý refresh request tuần tự và xác định chính xác kết quả của request trước khi retry.

### 7.3. Nếu refresh token bị lộ nhưng chưa thấy reuse

Không có reuse event không chứng minh token chưa bị đánh cắp. Kẻ tấn công có thể chưa sử dụng hoặc đã sử dụng trong một khoảng thời gian chưa được log.

Nếu token có khả năng bị truy cập bởi người không được phép, nên revoke token/family theo phạm vi, kiểm tra access token đã được cấp và khắc phục điểm rò rỉ.

## 8. Phân biệt token bị lộ với signing key hoặc client credential bị lộ

Đây là ranh giới quan trọng để chọn đúng hành động.

| Sự cố | Hành động chính | Không nên làm |
|---|---|---|
| Một access token bị lộ | Revoke token/session/subject theo phạm vi | Rotate signing key nếu key không bị lộ |
| Một refresh token bị lộ | Revoke token family/grant và đánh giá access token liên quan | Chỉ chờ refresh token hết hạn |
| Client secret bị lộ | Disable hoặc rotate client credential; kiểm tra token do client lấy được | Chỉ revoke một access token quan sát được nếu client vẫn bị chiếm |
| Private signing key bị lộ | Ngừng ký bằng key, loại key khỏi trust set, rotate và purge cache | Chỉ thêm jti vào denylist rồi tiếp tục tin key |
| Khóa mã hóa JWE của recipient bị lộ | Thay key, đánh giá ciphertext và plaintext có thể bị giải mã, rotate key distribution | Coi đây là sự cố chỉ ảnh hưởng một token |
| Session cookie bị lộ | Revoke session và credential liên quan | Chỉ xóa cookie ở trình duyệt mà không revoke phía server |

### 8.1. Khi signing private key bị lộ

Nếu private signing key bị xâm phạm, kẻ tấn công có thể tự tạo JWT có chữ ký hợp lệ theo key đó. Cần:

1. Ngừng dùng key để ký token mới.
2. Loại key khỏi tập key được resource server tin cậy hoặc đánh dấu revoked.
3. Phát hành key mới và phân phối public key qua kênh tin cậy.
4. Purge hoặc cập nhật JWKS/trust cache trên tất cả resource server.
5. Xác định khoảng thời gian key có thể đã bị sử dụng trái phép.
6. Điều tra token giả mạo và các hành động đã thực hiện.
7. Re-authenticate/revoke grant trong phạm vi cần thiết.

Nếu chỉ xóa key khỏi JWKS nhưng resource server còn cache key cũ, token giả vẫn có thể được chấp nhận cho đến khi cache được cập nhật.

### 8.2. Khi client credential bị lộ

Nếu confidential client secret hoặc private key bị lộ, kẻ tấn công có thể giả mạo client để xin token. Cần disable hoặc rotate credential, xem xét grant/client permission và rà soát token đã được phát hành cho client trong khoảng thời gian ảnh hưởng.

Đổi client secret không tự động làm mọi access token đã phát hành mất hiệu lực. Resource server vẫn cần cơ chế revocation hoặc chờ token hết hạn theo chính sách.

## 9. Bảo toàn bằng chứng và điều tra

### 9.1. Lưu metadata, không nhân bản secret

Incident record nên lưu:

- Incident ID và correlation ID.
- Loại credential bị ảnh hưởng.
- Issuer, subject/client và audience đã xác minh.
- `jti` hoặc định danh session/token family nếu có.
- `iat`, `exp`, thời điểm phát hiện và thời điểm revoke.
- Scope/role và resource server liên quan.
- Nguồn phát hiện và vị trí rò rỉ.
- Kết quả revoke và propagation.
- Các request đáng ngờ và tác động nghiệp vụ.

Không lưu raw access token, refresh token, authorization code, session cookie, private key hoặc CEK trong ticket hay log điều tra thông thường.

### 9.2. Fingerprint token

Nếu cần đối chiếu token giữa nhiều hệ thống, có thể tạo fingerprint bằng HMAC với khóa dành riêng cho logging/incident response.

- HMAC key phải được bảo vệ và tách khỏi signing/encryption keys.
- Fingerprint không thể thay thế chữ ký hoặc introspection.
- Không dùng token hash làm authorization key nếu không có threat analysis.
- Hạn chế người có quyền truy cập fingerprint và khóa HMAC.
- Không tạo metric label có cardinality cao từ fingerprint.

### 9.3. Xác định nguồn rò rỉ

Kiểm tra các nguồn có thể chứa credential:

- URL, browser history, referrer và redirect.
- Reverse proxy, CDN, WAF, API gateway và access log.
- Application debug log, exception và audit record.
- APM, trace, analytics, crash report và session replay.
- Repository, CI artifact, build output và support bundle.
- Browser extension, clipboard, thiết bị thất lạc hoặc malware.
- Message broker, queue, cache, database snapshot và backup.
- Email/chat/ticket hoặc tài liệu được chia sẻ.

Giữ nguyên bằng chứng cần thiết theo quy trình incident và yêu cầu pháp lý. Đồng thời giới hạn truy cập dữ liệu chứa token, ngăn bản sao mới được tạo và xóa/expire theo chính sách khi không còn cần lưu.

### 9.4. Xác định hành động đã thực hiện bằng token

Không chỉ tìm request xác thực thành công. Cần xác định:

- Resource nào được truy cập.
- Thao tác đọc, ghi, export hoặc thay đổi quyền nào đã xảy ra.
- Có dữ liệu nào bị tải xuống hoặc thay đổi không.
- Có refresh token mới hoặc session mới được tạo không.
- Có thay đổi email, MFA, mật khẩu, payment destination hoặc client configuration không.
- Có dấu hiệu persistence hoặc token tiếp tục được phát hành không.

Nếu có tác động nghiệp vụ, mở rộng incident theo quy trình ứng phó của tổ chức.

## 10. Đồng bộ revocation đến mọi resource server

### 10.1. Vì sao revoke tại authorization server chưa đủ?

JWT access token self-contained có thể được xác minh cục bộ. Nếu resource server không gọi introspection hoặc không kiểm tra denylist/session/version, nó không tự biết token đã bị revoke ở authorization server.

Do đó cần xác định đường truyền trạng thái:

- Denylist hoặc session state dùng chung.
- Token/security version.
- Introspection.
- Event invalidation và cache purge.
- Signing key revocation/JWKS refresh nếu key bị compromise.

### 10.2. Xác nhận propagation

Không coi thao tác revoke đã hoàn tất chỉ vì API revoke trả thành công.

Cần kiểm tra:

1. Authorization server ghi nhận trạng thái revoke.
2. Event hoặc state update đã được phát tán.
3. Mọi region/cluster/resource server đã nhận update.
4. Cache cũ đã hết hạn hoặc được purge.
5. Token cũ bị từ chối ở từng endpoint cần bảo vệ.
6. Token mới chỉ được cấp sau khi trạng thái subject/session đã được xác minh.
7. Hệ thống monitoring không còn thấy token cũ được chấp nhận.

Ghi lại thời điểm từng bước để đo revocation propagation time.

### 10.3. Fail-open và fail-closed

Khi kho revocation hoặc introspection không khả dụng:

- Endpoint nhạy cảm như thay đổi quyền, thanh toán hoặc export dữ liệu thường nên fail-closed nếu không thể xác minh trạng thái cần thiết.
- Endpoint ít rủi ro có thể có chính sách availability khác, nhưng phải ghi rõ revocation window có thể tăng.
- Không để từng resource server tự chọn fallback không nhất quán.
- Timeout và retry phải có giới hạn; không retry vô hạn hoặc bỏ qua kiểm tra trạng thái.

## 11. Khôi phục và cấp lại credential

Sau containment, cần bảo đảm người dùng hợp lệ có thể tiếp tục sử dụng dịch vụ an toàn.

### 11.1. Xác thực lại

Tùy mức độ compromise:

- Yêu cầu đăng nhập lại.
- Yêu cầu MFA hoặc step-up authentication.
- Kiểm tra thiết bị và session mới.
- Đổi mật khẩu nếu credential đăng nhập có thể bị lộ.
- Thu hồi session khác nếu không thể xác định phạm vi.
- Xác minh thông tin liên hệ và phương thức khôi phục tài khoản.

Không tự động yêu cầu đổi mật khẩu cho mọi sự cố token nếu không có bằng chứng mật khẩu bị ảnh hưởng; nhưng phải thu hồi phiên/token bị xâm phạm.

### 11.2. Cấp access token và refresh token mới

- Chỉ cấp sau khi account/client và quyền hiện tại đã được xác minh.
- Cấp scope tối thiểu cần thiết.
- Dùng thời hạn phù hợp với mức rủi ro.
- Gắn token với session/client đúng profile.
- Nếu hỗ trợ sender-constrained token, cân nhắc sử dụng để giảm khả năng replay của bearer token bị sao chép.
- Đảm bảo refresh token mới thuộc token family/session mới nếu family cũ đã bị revoke.
- Không tái sử dụng token hoặc token family đã bị đánh dấu compromise.

### 11.3. Theo dõi sau khôi phục

Theo dõi trong khoảng thời gian do incident owner xác định:

- Request dùng token cũ.
- Refresh token reuse.
- Đăng nhập hoặc MFA bất thường.
- Hoạt động từ thiết bị/client không quen thuộc.
- Request đến endpoint nhạy cảm.
- Lỗi propagation hoặc cache stale.
- Credential tiếp tục xuất hiện trong log/trace sau khi đã sửa.

## 12. Runbook theo tình huống

### 12.1. Access token bị lộ trong log

1. Hạn chế quyền truy cập log và ngăn log pipeline tiếp tục ghi token.
2. Xác định token/subject/audience/scope và expiration bằng quy trình an toàn.
3. Revoke jti/session/user state theo phạm vi.
4. Xác minh mọi resource server đã nhận trạng thái revoke.
5. Kiểm tra request sử dụng token sau thời điểm lộ.
6. Redact hoặc expire bản sao trong log/archive theo chính sách.
7. Sửa logger, proxy/APM redaction và thêm regression test.

### 12.2. Refresh token bị lộ trong browser hoặc thiết bị

1. Revoke refresh token và token family/grant liên quan.
2. Thu hồi session/thiết bị bị ảnh hưởng.
3. Đánh giá access token đã được cấp từ family đó.
4. Kiểm tra refresh reuse và các lần cấp token mới.
5. Yêu cầu người dùng xác thực lại trên thiết bị tin cậy.
6. Xóa nguồn rò rỉ và kiểm tra browser sync/extension/telemetry nếu liên quan.
7. Theo dõi reuse hoặc đăng nhập bất thường.

### 12.3. Refresh token reuse được phát hiện

1. Đánh dấu token reuse event và liên kết với token family.
2. Revoke refresh token đang active trong family theo rotation policy.
3. Xem xét revoke access token được cấp từ family.
4. Chặn tiếp tục refresh và yêu cầu re-authentication.
5. Kiểm tra client concurrency, retry và race condition để phân biệt replay với lỗi triển khai.
6. Điều tra thiết bị/session và thời điểm sử dụng token cũ.
7. Ghi nhận kết quả và điều chỉnh rotation handling nếu cần.

### 12.4. Private signing key bị lộ

1. Ngừng ký bằng key bị lộ.
2. Loại key khỏi trust set của resource server.
3. Purge JWKS/trust cache và xác nhận từng vùng đã cập nhật.
4. Phát hành key mới, phân phối public key qua kênh tin cậy.
5. Đánh giá mọi JWT được ký trong khoảng thời gian key bị xâm phạm.
6. Revoke session/grant/token liên quan nếu cần.
7. Điều tra token giả mạo và các hành động đã thực hiện.

## 13. Mã giả điều phối ứng phó

Mã giả sau mô tả luồng điều phối khái niệm. Tên trạng thái và thao tác phụ thuộc hệ thống; đây không phải API của một thư viện cụ thể.

~~~text
function respond_to_token_compromise(incident, services):
    credential = classify_credential(incident.evidence)
    scope = determine_affected_scope(credential, incident)

    preserve_safe_evidence(
        incident_id = incident.id,
        metadata = verified_token_metadata(incident),
        correlation_ids = incident.correlation_ids
    )

    stop_leak_source(incident.source)

    if credential.type == "ACCESS_TOKEN":
        revoke_access_token_or_session(scope)
        invalidate_resource_server_state(scope)

    else if credential.type == "REFRESH_TOKEN":
        revoke_refresh_token_family_or_grant(scope)
        revoke_related_access_tokens_if_supported(scope)
        require_reauthentication(scope.subject)

    else if credential.type == "CLIENT_CREDENTIAL":
        disable_or_rotate_client_credential(scope.client)
        review_tokens_issued_to_client(scope.client)

    else if credential.type == "SIGNING_KEY":
        stop_signing_with_key(scope.key_id)
        remove_key_from_trust_sets(scope.key_id)
        purge_jwks_and_validation_caches(scope.key_id)
        rotate_signing_key()

    verify_old_credentials_are_rejected(scope, services)
    investigate_misuse_and_data_access(incident)
    remediate_leak_source(incident.source)
    restore_access_with_new_credentials(scope)
    monitor_for_replay_and_residual_use(scope)

    return incident_status_and_audit_record()
~~~

Trong triển khai thực tế, thao tác revoke phải idempotent, có audit, có deadline và có kết quả xác nhận. Không đánh dấu incident đã containment chỉ vì một request revoke được gửi đi; phải xác nhận trạng thái đã đến các thành phần thực thi.

## 14. Ma trận kiểm thử ứng phó sự cố

| Trường hợp | Kết quả mong đợi |
|---|---|
| Access JWT còn hạn và jti đã bị revoke. | Resource server từ chối token. |
| Access JWT bị revoke nhưng một region còn cache cũ. | Test phát hiện propagation gap; không coi revoke hoàn tất. |
| Refresh token bị revoke. | Authorization server không cấp access token mới từ token đó. |
| Refresh token cũ bị reuse sau rotation. | Token family bị xử lý theo reuse policy và yêu cầu re-authentication khi cần. |
| Refresh token bị revoke nhưng access JWT cũ chưa hết hạn. | Access token chỉ bị chặn nếu resource server có cơ chế revoke/status; không giả định revoke refresh tự động chặn JWT offline. |
| Một session bị revoke. | Token gắn với session đó bị từ chối; session khác không bị ảnh hưởng nếu policy yêu cầu phạm vi hẹp. |
| User token version tăng. | Token có version cũ bị từ chối ở mọi resource server kiểm tra version. |
| Client secret bị rotate. | Client dùng credential cũ không thể lấy token mới; token cũ được đánh giá riêng. |
| Signing key bị revoke. | Resource server không còn chấp nhận token ký bằng key đó sau khi trust cache cập nhật. |
| JWKS cache chưa được purge. | Test phát hiện token cũ vẫn được xác minh và cảnh báo containment chưa hoàn tất. |
| Token bị lộ trong access log. | Raw token được redacted/expire theo policy; log điều tra chỉ giữ metadata an toàn. |
| Token bị lộ trong APM trace. | Collector và archive được kiểm tra; không còn capture token mới. |
| Token bị dùng từ client bất thường. | SIEM/monitoring tạo alert và lưu correlation metadata. |
| Revocation store không khả dụng ở endpoint nhạy cảm. | Hành vi fail-closed đúng policy. |
| Người dùng đăng nhập lại sau incident. | Credential mới được cấp theo quyền hiện tại; token family cũ vẫn bị revoke. |

## 15. Checklist đóng sự cố

- [ ] Đã xác định loại credential bị lộ và mức quyền.
- [ ] Đã xác định issuer, subject/client, audience, session/token family và thời hạn.
- [ ] Đã chặn nguồn rò rỉ để không phát sinh thêm bản sao.
- [ ] Đã revoke đúng token/session/grant/client/key theo phạm vi.
- [ ] Đã xử lý refresh token family và reuse nếu liên quan.
- [ ] Đã đánh giá access token được cấp từ refresh token bị lộ.
- [ ] Đã xác nhận revocation propagation đến mọi resource server/region.
- [ ] Đã kiểm tra JWKS/trust cache nếu key bị compromise.
- [ ] Đã điều tra hành động trái phép và tác động dữ liệu.
- [ ] Đã bảo toàn bằng chứng cần thiết mà không lưu raw token.
- [ ] Đã khắc phục log, URL, browser, proxy, APM hoặc nguồn rò rỉ.
- [ ] Đã cấp lại credential theo quyền hiện tại và yêu cầu xác thực phù hợp.
- [ ] Đã thiết lập monitoring sau sự cố và người chịu trách nhiệm.
- [ ] Đã ghi timeline, quyết định, ngoại lệ và bài học kinh nghiệm.

## 16. Câu hỏi tự kiểm tra

1. Vì sao refresh token bị lộ thường có thể gây ảnh hưởng lâu hơn access token?
2. Thu hồi refresh token có tự động làm mọi JWT access token đã cấp mất hiệu lực không?
3. Khi nào nên revoke một jti, một session, một token family hoặc toàn bộ signing key?
4. Vì sao refresh token reuse sau rotation có thể là dấu hiệu compromise?
5. Cần làm gì để tránh false positive khi client refresh đồng thời hoặc retry sau timeout?
6. Vì sao JWT self-contained cần cơ chế bổ sung để resource server biết token đã bị revoke?
7. Khi nào việc lộ token thực chất là sự cố lộ client credential hoặc signing key?
8. Những metadata nào có thể lưu trong incident ticket mà không nhân bản bearer secret?
9. Vì sao revoke chỉ được xem là hoàn tất sau khi mọi resource server áp dụng trạng thái mới?
10. Cần xác minh những gì trước khi cấp lại access token và refresh token?

## 17. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): claims như issuer, subject, audience, expiration và JWT ID.
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): endpoint thu hồi access token và refresh token, cùng ảnh hưởng đến token liên quan trong authorization grant.
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): resource server kiểm tra trạng thái active của token.
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ refresh token, rotation, sender-constrained tokens và phát hiện refresh token reuse (§4.14).
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): ràng buộc access/refresh token với khóa của client để giảm khả năng sử dụng token bị đánh cắp.
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): profile access token dạng JWT và yêu cầu xác minh ở resource server.
