# Identity provider outage

**Identity provider outage** là tình trạng một Identity Provider (IdP) hoặc một thành phần thiết yếu trong chuỗi xác thực không thể phục vụ đúng chức năng, đúng thời hạn hoặc đúng mức độ tin cậy. Sự cố có thể làm người dùng mới không đăng nhập được, ngăn ứng dụng làm mới token, khiến resource server không tra cứu được opaque token, hoặc làm hệ thống không tải được khóa công khai cần thiết để xác minh JWT.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. IdP là một authority quan trọng trong các luồng này: nó xác minh credential, áp dụng authentication policy, phát hành assertion/token và duy trì một số trạng thái federation. Khi IdP gặp sự cố, hệ thống cần duy trì availability trong giới hạn mà security policy cho phép, đồng thời tránh chấp nhận danh tính hoặc token chưa được xác minh.

Điểm cốt lõi: **IdP outage không đồng nghĩa mọi request đều phải dừng, cũng không có nghĩa mọi request nên được cho qua**. Tác động phụ thuộc vào loại credential, cách resource server xác minh token, trạng thái session hiện có, độ mới của key/metadata và độ nhạy của tài nguyên. Một thiết kế tốt xác định trước phần nào có thể tiếp tục bằng bằng chứng đã được xác minh, phần nào phải chờ IdP, và phần nào cần fail closed.

## 1. Identity provider và vai trò trong hệ thống

Identity Provider là hệ thống xác minh principal và cung cấp thông tin xác thực cho relying party (RP), application hoặc resource server theo một protocol và trust configuration đã thỏa thuận.

Một IdP có thể:
- Xác minh password, passkey, MFA, certificate hoặc authenticator khác.
- Quản lý account, authenticator, recovery và trạng thái người dùng.
- Phát hành ID Token, access token, SAML assertion hoặc authorization code.
- Cung cấp discovery document và signing keys.
- Cung cấp token introspection, userinfo hoặc federation metadata.
- Duy trì IdP session để hỗ trợ Single Sign-On (SSO).
- Áp dụng policy về authentication freshness, assurance và risk.

Một hệ thống có thể phụ thuộc vào IdP bên ngoài, IdP nội bộ hoặc nhiều IdP. Một số ứng dụng tự quản lý session sau khi xác minh assertion; một số resource server gọi introspection cho từng request; một số dùng JWT tự chứa và xác minh chữ ký cục bộ.

### 1.1. Phân biệt các thành phần

| Thành phần | Vai trò | Ảnh hưởng khi thành phần lỗi |
| --- | --- | --- |
| **Authorization endpoint** | Khởi tạo authentication/authorization tại IdP. | Người dùng mới hoặc người cần đăng nhập lại không bắt đầu được flow. |
| **Token endpoint** | Đổi authorization code hoặc refresh token thành token. | Login callback hoặc refresh có thể không hoàn tất. |
| **JWKS endpoint** | Cung cấp public key để verifier kiểm tra chữ ký JWT. | Verifier thiếu key mới hoặc không thể cập nhật key rotation. |
| **Introspection endpoint** | Trả trạng thái của opaque/reference token. | Resource server không xác minh được token theo mô hình online. |
| **Discovery/metadata endpoint** | Cung cấp issuer, endpoint và protocol metadata. | Client mới hoặc component khởi động lại có thể không cấu hình được. |
| **UserInfo endpoint** | Cung cấp claims user theo access token. | Ứng dụng có thể thiếu dữ liệu profile cần cho chức năng. |
| **MFA/push service** | Gửi hoặc xác minh yếu tố bổ sung. | Authentication flow có MFA có thể bị gián đoạn. |
| **Federation broker** | Kết nối với upstream IdP hoặc partner. | Chỉ các luồng liên kết qua upstream đó bị ảnh hưởng hoặc chậm. |

Không nên dùng một health check duy nhất để kết luận toàn bộ IdP khỏe hay hỏng. Authorization endpoint có thể hoạt động trong khi token endpoint lỗi; JWKS có thể truy cập được dù MFA provider đang outage.

### 1.2. IdP là trust authority, không chỉ là web login page

Một trang login không tải được là dấu hiệu dễ thấy, nhưng trust dependency còn nằm ở issuer identity, signing key, metadata, token status và federation relationship. Khi outage xảy ra, hệ thống phải biết bằng chứng nào đã được xác minh trước đó và bằng chứng nào cần authority online.

## 2. Phân loại outage

Phân loại sự cố theo thành phần và failure mode giúp chọn đúng phản ứng.

### 2.1. Authentication outage

Authorization endpoint, credential verification hoặc MFA service không phục vụ được. Người dùng chưa có session hợp lệ thường không thể hoàn tất đăng nhập. Những người đang có session có thể tiếp tục truy cập nếu session local vẫn hợp lệ và policy cho phép.

### 2.2. Token issuance/refresh outage

Token endpoint không thể đổi authorization code hoặc refresh token. Login flow có thể dừng ở callback; mobile app hoặc backend có thể không lấy được access token mới. Access token hiện tại có thể còn hiệu lực tới expiry, tùy loại token và cách resource server kiểm tra.

### 2.3. JWKS/key distribution outage

Verifier không thể tải signing key hoặc metadata mới. Nếu key đã biết và được cache hợp lệ, verifier có thể tiếp tục xác minh token được ký bằng key đó trong giới hạn cache/trust policy. Nếu token có kid chưa biết, không thể tự đoán hoặc chấp nhận chữ ký mà chưa có public key tin cậy.

### 2.4. Introspection outage

Resource server dùng opaque token hoặc cần trạng thái online không thể gọi introspection. Nếu không có cache còn hiệu lực theo policy, server không biết token active hay revoked. Không được coi timeout của introspection là kết quả active.

### 2.5. Federation/upstream outage

Một upstream IdP, social login provider hoặc enterprise federation partner không phản hồi. Các account dùng upstream đó bị ảnh hưởng; local account hoặc luồng khác có thể vẫn hoạt động. Không tự động đổi sang issuer khác chỉ vì email giống nhau.

### 2.6. Network và infrastructure outage

DNS, routing, TLS certificate, clock synchronization, proxy, load balancer, database hoặc secret manager có thể làm IdP trông như đang outage. Phải xác định lỗi nằm ở IdP hay ở đường kết nối từ client/service tới IdP.

### 2.7. Security incident giả dạng availability incident

Một số tình huống cần xem là security incident:
- Signing key bị thu hồi hoặc nghi bị compromise.
- Discovery/JWKS response bị thay đổi bất thường.
- DNS/TLS interception.
- Token validation thất bại sau key rotation không được kiểm soát.
- Credential stuffing hoặc request flood làm IdP quá tải.
- Attacker cố khai thác fallback trong thời gian outage.

Không hạ chuẩn xác minh chỉ để làm cho dashboard availability xanh trở lại.

## 3. Xác định phạm vi ảnh hưởng

Khi phát hiện IdP outage, trước tiên cần biết ai và thành phần nào bị ảnh hưởng.

### 3.1. Các nhóm principal

- Người dùng mới chưa có session.
- Người dùng đã có browser/application session.
- Người dùng cần re-authentication hoặc step-up.
- Mobile app cần refresh token.
- Backend workload dùng client credentials.
- Resource server dùng JWT local validation.
- Resource server dùng opaque token introspection.
- Service federation phụ thuộc upstream IdP.
- Administrator cần break-glass access.

Mỗi nhóm có dependency và mức rủi ro khác nhau. Không áp dụng một quyết định failover duy nhất cho tất cả.

### 3.2. Các lớp tác động

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| **User sign-in** | Người dùng mới có thể xác thực không? |
| **Existing session** | Session đã xác minh còn hiệu lực không? |
| **Token renewal** | Có thể refresh token hoặc đổi authorization code không? |
| **Token validation** | Verifier có key/status cần thiết không? |
| **Authorization** | Có đủ claims và dữ liệu quyền hiện tại không? |
| **Recovery/admin** | Có thể khôi phục account hoặc vận hành khẩn cấp không? |
| **Audit/monitoring** | Có thể ghi nhận và điều tra hành động trong outage không? |

### 3.3. Ma trận tác động theo loại token/session

| Cơ chế | Phụ thuộc IdP khi xử lý request? | Khả năng tiếp tục trong outage |
| --- | --- | --- |
| **JWT access token với key đã cache** | Có thể không, nếu verifier kiểm tra local và policy chấp nhận key/cache state. | Có thể tiếp tục tới giới hạn expiry, key trust và revocation policy. |
| **Opaque token với introspection online** | Có, trừ khi có cache trạng thái còn hiệu lực. | Chỉ tiếp tục nếu cache policy cho phép và freshness đủ. |
| **Browser session server-side** | Thường không cần IdP cho mỗi request sau khi RP đã xác minh. | Có thể tiếp tục tới idle/absolute timeout hoặc revoke policy. |
| **Mobile access token** | Tùy JWT/opaque và API validation. | Token hiện tại có thể dùng nếu còn hợp lệ và API xác minh được. |
| **Refresh token** | Thường cần token endpoint. | Không thể refresh khi endpoint không phục vụ. |
| **SAML/OIDC login mới** | Cần IdP hoặc upstream. | Không thể hoàn tất nếu authority không phản hồi. |
| **Workload certificate/mTLS** | Không nhất thiết cần IdP ở mỗi request. | Có thể tiếp tục nếu certificate, trust chain và revocation policy còn hợp lệ. |

Bảng chỉ mô tả dependency phổ biến. Quyết định thực tế phải theo protocol, token profile, key management và policy của hệ thống.

## 4. Nguyên tắc fail closed và degraded mode

Fail closed nghĩa là từ chối khi hệ thống không thể xác minh điều kiện bảo mật bắt buộc. Degraded mode là chế độ giới hạn chức năng có chủ đích trong khi một dependency không sẵn sàng.

Hai khái niệm không đối lập. Một hệ thống có thể tiếp tục phục vụ tài nguyên ít nhạy cảm bằng session đã được xác minh, đồng thời fail closed với login mới, token không xác minh được hoặc thao tác đặc quyền.

### 4.1. Khi nào phải fail closed?

- Không xác minh được chữ ký token hoặc không có key tin cậy.
- Token có issuer/audience/type không đúng.
- Token hết hạn hoặc chưa tới thời điểm hợp lệ.
- Introspection không phản hồi và không có cache hợp lệ theo policy.
- Không xác minh được account status cho action bắt buộc kiểm tra online.
- Session bị revoke hoặc version mismatch đã biết.
- MFA/step-up bắt buộc nhưng không thể hoàn tất.
- Recovery hoặc thay đổi authenticator không có proofing đủ mạnh.

Không biến timeout, DNS failure hoặc HTTP 5xx thành “authentication success”.

### 4.2. Khi nào có thể tiếp tục?

Có thể tiếp tục nếu ứng dụng có bằng chứng đã được xác minh trước đó và policy xác định rõ:
- Browser session local vẫn active, chưa idle/absolute expiry và không có revoke signal.
- JWT access token được xác minh bằng key đã cache và đáp ứng issuer, audience, algorithm, type, expiry và scope.
- Workload certificate còn hiệu lực và trust/revocation policy cho phép.
- Tài nguyên read-only hoặc ít nhạy cảm được phép dùng dữ liệu cache có freshness giới hạn.
- Một phần chức năng offline được thiết kế trước và có giới hạn rõ.

Tiếp tục sử dụng session/token đã được xác minh không phải là cấp một danh tính mới. Không tạo session mới hoặc nâng quyền chỉ dựa trên trạng thái cũ nếu policy yêu cầu authentication mới.

### 4.3. Degraded mode phải được thiết kế trước

Không nên để từng service tự quyết định khi IdP timeout. Cần policy trung tâm hoặc cấu hình đã review, định nghĩa:
- Resource nào có thể tiếp tục.
- Loại credential nào được chấp nhận.
- Cache freshness tối đa.
- Action nào bị disable.
- Thời hạn degraded mode.
- Người có thẩm quyền bật/tắt.
- Điều kiện thoát và reconciliation sau outage.

## 5. JWT validation khi JWKS endpoint không khả dụng

JWT access token có thể được xác minh cục bộ nếu resource server có public key hợp lệ. Đây là lợi thế về availability, nhưng chỉ đúng trong giới hạn trust và cache policy.

### 5.1. Cached signing key

Verifier có thể cache JWKS từ issuer đã cấu hình. Trong outage:
- Dùng key đã cache nếu key vẫn thuộc trust configuration và policy cho phép.
- Kiểm tra signature bằng algorithm allowlist.
- So khớp issuer và audience chính xác.
- Kiểm tra exp, nbf, token type và claims cần thiết.
- Không tự chấp nhận key do token cung cấp.
- Không bỏ qua kid không biết.

Cache key cần metadata về thời điểm tải, issuer, key ID, thuật toán và freshness. Không cache JWKS vô thời hạn.

### 5.2. Unknown kid

Nếu token có kid không nằm trong JWKS cache:
1. Thực hiện một lần refresh JWKS có giới hạn nếu endpoint có thể truy cập.
2. Dùng timeout và backoff; không tạo request storm.
3. Nếu endpoint vẫn outage hoặc key không xuất hiện, từ chối token.
4. Ghi reason code và alert theo mức phù hợp.
5. Không dùng key gần giống, key cũ không liên quan hoặc key do client gửi.

Unknown kid có thể là key rotation hợp lệ hoặc token giả mạo. Khi không lấy được key tin cậy, verifier không có cơ sở chấp nhận chữ ký.

### 5.3. Key rotation và emergency revocation

Key cache giúp availability nhưng tạo cửa sổ chấp nhận key cũ. Nếu signing key bị compromise, việc tiếp tục dùng key cache có thể chấp nhận token do attacker ký.

Cần quy định:
- Cache max-age và refresh schedule.
- Cách xử lý JWKS outage.
- Emergency key denylist/revocation channel độc lập.
- Propagation tới mọi verifier.
- Quy trình purge cache.
- Token lifetime trong giai đoạn key rotation.
- Cách phân biệt outage thông thường với key compromise.

Nếu có dấu hiệu key bị compromise, ưu tiên security incident response và revoke key theo emergency policy. Không kéo dài cache chỉ để giữ availability.

## 6. Opaque token và introspection outage

Opaque token thường không mang đủ thông tin để resource server tự xác minh. Server gọi introspection endpoint để biết token có active không và lấy metadata cần thiết.

### 6.1. Timeout không đồng nghĩa active

Nếu introspection timeout:
- Không coi response lỗi là active=true.
- Không tự suy ra subject hoặc scope từ token string.
- Không bỏ qua audience/resource binding.
- Không retry vô hạn trên request path.
- Không chuyển sang một issuer khác không được cấu hình.

### 6.2. Introspection cache

Có thể cache kết quả introspection để giảm dependency và chịu outage ngắn. Cache cần:
- Key được tạo từ token fingerprint an toàn, không lưu raw token trong cache key log.
- TTL ngắn và phù hợp với token expiry.
- Không cache negative/positive quá lâu ngoài policy.
- Cơ chế invalidation khi revoke event đến.
- Giới hạn stale-if-error.
- Phân biệt cache hit, miss, expired và stale.

Stale positive cache có thể tiếp tục cho phép token đã bị revoke. Vì vậy, giới hạn stale window theo mức nhạy cảm của resource; action đặc quyền hoặc giao dịch có hậu quả cao có thể cần online validation và fail closed.

### 6.3. Cache và revocation consistency

Nếu revocation event bị trễ hoặc không tới, cache active có thể cũ. Theo dõi event lag, invalidation success và maximum stale age. Với resource nhạy cảm, dùng check online hoặc version/epoch check có tính nhất quán phù hợp.

## 7. Existing session và người dùng đang đăng nhập

IdP outage thường ảnh hưởng login mới rõ nhất. Người dùng có RP/application session hiện tại có thể tiếp tục trong một khoảng thời gian nếu RP tự xác minh và quản lý session.

### 7.1. Browser session tại relying party

RP có thể:
- Xác minh cookie session server-side.
- Kiểm tra idle timeout và absolute timeout.
- Kiểm tra account/session version đã cache hoặc đồng bộ.
- Áp dụng authorization theo policy hiện hành.
- Tiếp tục request không cần IdP round-trip.

Không tự gia hạn absolute lifetime vô hạn trong outage. Nếu session hết hạn, yêu cầu authentication mới có thể thất bại; UI nên giải thích dịch vụ đăng nhập đang tạm gián đoạn.

### 7.2. Re-authentication và step-up

Nếu action cần authentication freshness hoặc MFA mới, session cũ không đáp ứng yêu cầu đó. Có thể:
- Cho phép user tiếp tục thao tác ít nhạy cảm.
- Tạm disable thao tác yêu cầu step-up.
- Giữ transaction ở trạng thái pending trong thời gian ngắn.
- Cho phép hủy an toàn và retry sau outage.
- Dùng authenticator local hoặc authority thay thế chỉ khi đã được policy phê duyệt.

Không giả định user presence hoặc biometric local tự thay thế step-up mà IdP yêu cầu, trừ khi protocol/policy có bằng chứng tương đương.

### 7.3. Logout trong outage

Logout local vẫn nên revoke RP session ở server và xóa cookie. Nếu global logout tới IdP không thực hiện được, phải ghi nhận phần nào đã hoàn tất và phần nào pending. Không tuyên bố đã sign out toàn bộ SSO khi chỉ revoke local session.

## 8. Refresh token và mobile application

Mobile app thường giữ refresh token để lấy access token mới. Khi IdP token endpoint outage:
- Access token còn hiệu lực có thể tiếp tục dùng nếu API validation hoạt động.
- Refresh request cần timeout và retry có backoff.
- Không xóa refresh token chỉ vì một lỗi mạng tạm thời.
- Không tạo nhiều refresh request song song.
- Không retry token đã bị xác định revoked hoặc reuse.
- Khi token hết hạn, app cần chuyển sang trạng thái signed-out/degraded phù hợp và giải thích cách retry.

Client nên phân biệt network timeout, server 5xx, invalid_grant, invalid_client và policy denial. Chỉ một số lỗi là transient. Refresh coordinator cần serialize request và chống response cũ ghi đè auth state mới.

### 8.1. Backoff và retry

Retry cần:
- Timeout hữu hạn.
- Exponential backoff có jitter.
- Retry budget theo client/service.
- Tôn trọng Retry-After nếu phù hợp.
- Circuit breaker khi dependency đang lỗi.
- Giới hạn concurrency.
- Không retry lỗi credential hoặc protocol không thể khắc phục bằng thời gian.

Một lượng lớn client retry cùng lúc có thể kéo dài outage. Có thể dùng jitter và server-side rate limit để giảm thundering herd.

### 8.2. Token đã hết hạn

Không kéo dài exp ở client hoặc tự sửa JWT. Nếu access token hết hạn và không thể refresh, resource server phải từ chối. App có thể giữ dữ liệu offline đã được phép cache, nhưng không gửi request protected bằng token hết hạn.

## 9. Federation và nhiều IdP

Một tổ chức có thể dùng nhiều upstream IdP, tenant hoặc broker. Redundancy chỉ có ích khi identity mapping và trust relationship được thiết kế rõ.

### 9.1. Failover sang IdP khác

Trước khi failover cần xác định:
- Issuer nào được trust cho client/resource đó.
- Subject mapping có ổn định và duy nhất không.
- MFA/assurance của IdP dự phòng có tương đương không.
- Redirect URI và client registration đã được cấu hình chưa.
- Claims, groups và tenant mapping có giống nhau không.
- User consent và account linking có yêu cầu lại không.
- Logout/revocation giữa các IdP được xử lý thế nào.

Không tự động chấp nhận issuer mới dựa trên email trùng hoặc display name giống nhau. Điều đó có thể tạo account linking nhầm hoặc account takeover.

### 9.2. Home realm discovery

Nếu người dùng chọn tenant hoặc domain để chọn IdP, outage của một tenant không nên làm các tenant khác bị ảnh hưởng. Routing cần allowlist issuer và cấu hình tin cậy. Không dùng user-supplied URL làm issuer endpoint.

### 9.3. Upstream outage

Broker có thể vẫn hoạt động dù một upstream IdP lỗi. Nó có thể tiếp tục phục vụ session đã xác minh, nhưng không thể tự xác minh user mới qua upstream đó nếu không có phương thức dự phòng đã đăng ký.

## 10. Workload identity và service-to-service authentication

IdP outage cũng ảnh hưởng service account, OAuth client credentials, workload identity federation hoặc certificate enrollment.

### 10.1. Client credentials

Nếu service lấy access token từ token endpoint, outage có thể ngăn phát hành token mới. Token hiện tại có thể tiếp tục tới expiry nếu resource server xác minh được. Service không nên nhúng client secret vào fallback code hoặc chuyển sang một account người dùng.

### 10.2. Certificate và mTLS

Workload dùng certificate có thể tiếp tục xác thực TLS nếu:
- Certificate chưa hết hạn.
- Private key còn được bảo vệ.
- Trust chain còn được verifier tin cậy.
- Revocation policy có thể đáp ứng.
- Certificate identity vẫn được authorization map đúng.

Certificate renewal có thể bị ảnh hưởng nếu CA/IdP enrollment endpoint outage. Cần renewal window đủ dài và quy trình emergency issuance được kiểm soát. Không chấp nhận certificate bất kỳ để tránh downtime.

### 10.3. Workload token cache

Cache token cho service-to-service cần:
- Audience/resource đúng.
- Expiry margin để tránh token hết hạn giữa request.
- Concurrency-safe refresh.
- Bounded stale behavior.
- Không log token.
- Revoke và rotate khi credential compromise.

Không chia sẻ token giữa workload khác trust boundary chỉ để giảm số lần gọi IdP.

## 11. Resilience patterns cho IdP dependency

Các pattern resilience giảm lỗi dây chuyền nhưng không thay đổi security semantics.

### 11.1. Timeout

Đặt timeout theo endpoint và ngân sách latency. Timeout quá dài giữ connection/thread; quá ngắn làm lỗi giả trong mạng chậm. Tính cả DNS, TLS handshake, connect, response và retry budget.

### 11.2. Circuit breaker

Circuit breaker tạm ngừng gọi dependency khi failure vượt ngưỡng, cho hệ thống thời gian phục hồi. Khi open:
- Trả lỗi dependency rõ ràng.
- Dùng cache chỉ theo stale policy đã định.
- Không biến lỗi thành authentication success.
- Cho phép half-open probe có giới hạn.
- Theo dõi state transition và thời gian open.

### 11.3. Bulkhead và concurrency limit

Tách pool/queue cho IdP calls khỏi request nội bộ khác. Giới hạn concurrent introspection/refresh/discovery request để IdP outage không làm cạn thread, connection hoặc memory của toàn bộ ứng dụng.

### 11.4. Retry với backoff

Chỉ retry lỗi transient và thao tác idempotent hoặc có transaction semantics rõ. Authorization code exchange và refresh token rotation cần cẩn thận vì retry mù có thể gặp one-time code/token đã được consume. Dùng idempotency hoặc client library xử lý đúng protocol nếu server hỗ trợ.

### 11.5. Cache metadata và keys

Cache discovery/JWKS để giảm dependency cho request path. Cache phải có:
- Issuer allowlist.
- Fetch timestamp và max-age.
- Refresh schedule.
- Stale-if-error policy.
- Unknown kid behavior.
- Emergency invalidation.
- Observability cho cache age và refresh result.

Không cache mọi response của IdP như nhau. Metadata, public key, token introspection và user profile có freshness/risk khác nhau.

## 12. Multi-region và high availability

IdP có thể cung cấp nhiều region hoặc replica. Ứng dụng cần hiểu consistency, routing và failover semantics.

### 12.1. Active-active và active-passive

Active-active có thể phân phối request qua nhiều region, nhưng session, key rotation, account state và revocation cần đồng bộ. Active-passive có thể đơn giản hơn nhưng failover time và RTO cần được đo.

Không chỉ dựa vào DNS failover. Client connection pool, TLS session, DNS cache và token issuer configuration có thể giữ endpoint cũ.

### 12.2. Consistency của session và revocation

Các câu hỏi cần trả lời:
- Logout/revoke ở region A mất bao lâu tới region B?
- Token refresh có thể chạy đồng thời ở hai region không?
- Session version/account epoch được cập nhật theo cơ chế nào?
- Cache invalidation có guaranteed delivery không?
- Khi partition mạng, region nào được phép phát hành token?
- Có nguy cơ hai region phát hành session khác nhau cho cùng transaction không?

Nếu consistency không thể bảo đảm, giới hạn chức năng trong partition thay vì cho hai phía tự phát hành credential có quyền rộng.

### 12.3. RTO và RPO

Recovery Time Objective (RTO) là thời gian mục tiêu để khôi phục dịch vụ. Recovery Point Objective (RPO) là mức mất dữ liệu/trạng thái chấp nhận được. Với IdP, RPO phải đặc biệt xem xét account disable, authenticator revoke, signing key status và revocation state. Khôi phục backup cũ không được làm sống lại account hoặc credential đã bị thu hồi.

## 13. Break-glass access

Break-glass là quyền truy cập khẩn cấp có kiểm soát khi authentication authority hoặc control plane chính không hoạt động. Nó có rủi ro cao và phải được thiết kế, diễn tập trước.

### 13.1. Nguyên tắc

- Chỉ dùng cho mục đích vận hành hoặc ứng cứu đã xác định.
- Tách biệt khỏi account cá nhân và IdP đang outage.
- Có số lượng account tối thiểu.
- Bảo vệ bằng credential mạnh, cất giữ/kiểm soát độc lập.
- Giới hạn network, host, resource và thời gian.
- Yêu cầu approval hoặc dual control nếu hoàn cảnh cho phép.
- Mọi lần sử dụng đều tạo audit evidence.
- Thu hồi/rotate ngay sau khi kết thúc incident.
- Review hành động và dữ liệu đã truy cập.

### 13.2. Không tạo backdoor lâu dài

Không dùng một password chung cho cả đội, không hardcode master secret, không tắt MFA toàn hệ thống hoặc mở admin endpoint công khai. Break-glass không phải cơ chế login thay thế cho người dùng thông thường.

### 13.3. Quy trình mẫu

1. Incident commander xác nhận IdP outage và phạm vi ảnh hưởng.
2. Người có thẩm quyền kích hoạt break-glass theo runbook.
3. Hai người xác minh/approve nếu policy yêu cầu.
4. Credential được lấy từ kho kiểm soát độc lập hoặc hardware authenticator.
5. Access chỉ cấp cho resource và thời gian cần thiết.
6. Ghi actor, approver, reason, start/end và action reference.
7. Khi IdP phục hồi, kết thúc quyền break-glass, rotate credential và review audit.

## 14. Degraded service và business continuity

Một ứng dụng có thể cung cấp chức năng giới hạn trong outage nếu đã phân loại resource và rủi ro.

### 14.1. Phân loại resource

| Loại resource/action | Ví dụ | Hướng xử lý tham khảo |
| --- | --- | --- |
| **Public** | Tài liệu công khai, status page. | Có thể phục vụ không cần authentication. |
| **Low-risk read-only** | Nội dung đã cache, không chứa dữ liệu nhạy cảm. | Có thể phục vụ trong giới hạn freshness và authorization đã xác minh. |
| **User private data** | Hồ sơ, tài liệu cá nhân. | Chỉ tiếp tục nếu session/token đã xác minh còn hợp lệ và quyền đủ mới. |
| **Sensitive action** | Đổi email, recovery method, tạo API key. | Thường yêu cầu IdP/step-up; tạm dừng nếu không xác minh được. |
| **Privileged/admin** | Cấp role, quản lý user, thay policy. | Fail closed hoặc break-glass có kiểm soát riêng. |
| **Financial/high-impact** | Chuyển tiền, phê duyệt giao dịch. | Yêu cầu authorization/freshness và transaction confirmation; không hạ chuẩn. |

### 14.2. Read-only mode

Read-only mode có thể cho phép xem dữ liệu đã được cache nếu:
- User/session đã được xác minh trước đó.
- Cache gắn với principal/tenant đúng.
- Dữ liệu không quá cũ theo policy.
- Không có revoke/disable signal đã biết.
- Không thực hiện write hoặc privilege change.
- Có giới hạn thời gian và audit.

Nếu không thể chứng minh cache thuộc đúng principal, không hiển thị dữ liệu riêng tư.

### 14.3. Pending operation

Một thao tác cần IdP có thể được lưu ở trạng thái pending thay vì thất bại hoàn toàn. Khi phục hồi:
- Revalidate user/session.
- Kiểm tra transaction còn hợp lệ.
- Xác nhận payload chưa thay đổi.
- Chống replay và double-submit.
- Yêu cầu approval/freshness mới nếu cần.
- Hủy transaction đã hết TTL.

Không tự thực hiện một giao dịch nhạy cảm chỉ vì user đã bấm nút trước outage.

## 15. Monitoring và SLI/SLO cho IdP dependency

Cần đo cả availability của IdP và khả năng ứng dụng sử dụng dependency đó.

### 15.1. Metric cần theo dõi

- Availability và latency theo từng endpoint.
- DNS resolution, TLS handshake và connection error.
- Token issuance/refresh success và failure.
- Introspection latency, timeout và cache hit/stale rate.
- JWKS fetch success, cache age, unknown kid và refresh failure.
- Discovery/metadata refresh status.
- Authentication/MFA challenge outcome.
- Session create/reject và refresh retry.
- Circuit breaker state, concurrency và queue depth.
- Revocation propagation và account status freshness.

Không đưa password, token, session ID, email hoặc user ID vào metric label. Dùng reason code và client class có cardinality hữu hạn.

### 15.2. SLI và SLO

Ví dụ SLI:
- Tỷ lệ authorization/token endpoint request hợp lệ hoàn tất thành công.
- Tỷ lệ resource request được xác minh trong latency budget.
- Tỷ lệ introspection hoàn tất trong ngưỡng.
- Tỷ lệ revoke event được enforce trong thời gian mục tiêu.
- Tỷ lệ login flow hoàn tất, tách lỗi người dùng nhập sai khỏi lỗi dependency.

SLO phải phân biệt IdP service SLO với application end-to-end SLO. IdP khỏe nhưng DNS/proxy từ một region lỗi vẫn làm application bị outage.

### 15.3. Synthetic monitoring

Dùng test account và transaction an toàn để kiểm tra:
- Discovery và authorization endpoint.
- Authorization code + PKCE end-to-end.
- Token endpoint và refresh.
- JWKS fetch và local signature validation.
- Introspection.
- Federation upstream.
- MFA challenge.
- Logout/revocation.

Synthetic test không dùng account production có quyền cao hoặc secret thật trong log. Giới hạn tần suất để không tạo tải đáng kể.

## 16. Incident response khi IdP outage

Một runbook nên giúp đội vận hành chẩn đoán, giới hạn tác động và khôi phục có kiểm soát.

### 16.1. Xác nhận và phân loại

1. Xác nhận alert từ nhiều nguồn: synthetic probe, service telemetry và IdP status.
2. Kiểm tra DNS, TLS, network, proxy và clock.
3. Xác định endpoint và tenant/upstream bị ảnh hưởng.
4. Phân biệt 4xx policy/credential errors với 5xx, timeout và connection failure.
5. Xác định có phải security incident như key compromise hay không.
6. Ghi nhận thời điểm bắt đầu và các deployment/config changes gần đây.

### 16.2. Containment và degraded mode

1. Kích hoạt incident owner và communication channel.
2. Áp dụng degraded policy đã được phê duyệt.
3. Giữ hard validation cho signature, issuer, audience, expiry và authorization.
4. Tạm disable login/step-up/privileged action nếu không thể xác minh.
5. Dùng cache chỉ trong freshness window được phép.
6. Giới hạn retry và concurrency để tránh overload.
7. Kích hoạt break-glass chỉ theo điều kiện đã định.
8. Ghi audit cho thay đổi policy và quyền khẩn cấp.

### 16.3. Khôi phục

1. Xác nhận IdP endpoint và dependencies ổn định.
2. Refresh discovery/JWKS theo allowlist và kiểm tra key rotation.
3. Xử lý refresh backlog có rate limit và jitter.
4. Revalidate session/token state và revocation events bị trễ.
5. Hủy pending transaction hết hạn hoặc không còn hợp lệ.
6. Tắt degraded mode theo từng lớp resource.
7. Revoke break-glass access và rotate credential.
8. Theo dõi error rate, latency và synthetic flow sau recovery.

### 16.4. Post-incident review

- Nguyên nhân gốc và thời gian từng phase.
- Endpoint, tenant, region và user group bị ảnh hưởng.
- Số login/refresh/session operation thất bại.
- Có request nào được chấp nhận trong stale window không.
- Revoke/key rotation có propagation đúng không.
- Fallback có bị dùng sai hoặc quá hạn không.
- Runbook, alert và communication có hiệu quả không.
- Hành động cải tiến có owner và deadline.

## 17. Threat model cho Identity Provider outage

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Fail-open authentication** | Timeout IdP bị coi như login thành công. | Attacker truy cập không có bằng chứng. | Fail closed cho bước xác minh bắt buộc; degraded mode theo resource. |
| **Stale positive introspection** | Cache active được dùng sau khi token đã revoke. | Token bị thu hồi vẫn truy cập. | TTL ngắn, invalidation và giới hạn stale-if-error. |
| **Unknown signing key** | Verifier chấp nhận token có kid không biết hoặc bỏ signature check. | JWT giả được chấp nhận. | Refresh bounded một lần; thiếu key tin cậy thì reject. |
| **Compromised key in stale cache** | Tiếp tục trust key đã bị thu hồi. | Attacker ký token hợp lệ về mặt cache. | Emergency key revocation channel và purge cache. |
| **Refresh retry storm** | Client retry đồng loạt khi token endpoint lỗi. | IdP và client cùng quá tải. | Backoff, jitter, retry budget, circuit breaker. |
| **Unsafe IdP failover** | Chuyển sang issuer khác chỉ vì cùng email. | Account linking nhầm hoặc takeover. | Issuer allowlist, subject mapping và assurance equivalence. |
| **Session lifetime extension** | Kéo dài session vô hạn trong outage. | Session cũ tồn tại quá policy. | Absolute timeout vẫn được enforce. |
| **Revocation propagation gap** | Region không nhận revoke event. | Session bị revoke vẫn dùng được. | Reconciliation, version check và synthetic negative test. |
| **Break-glass abuse** | Account khẩn cấp trở thành backdoor thường trực. | Privilege misuse khó phát hiện. | Dual control, scope/time limit, audit và post-incident rotation. |
| **Stale authorization data** | Role/group claim cũ tiếp tục được dùng. | User giữ quyền đã bị thu hồi. | Authorization freshness, version/epoch check và hạn chế action nhạy cảm. |
| **Monitoring blind spot** | Chỉ kiểm tra trang login, bỏ qua token/JWKS/introspection. | Phát hiện outage muộn hoặc sai phạm vi. | Synthetic probe theo từng dependency và endpoint. |
| **Recovery transaction replay** | Pending action được thực hiện sau khi outage kết thúc dù đã hết hạn. | Thay đổi account không còn hợp lệ. | TTL, one-time transaction và revalidation khi resume. |

## 18. Tình huống thực hành: IdP outage trong giờ cao điểm

**Bối cảnh:** Một doanh nghiệp dùng OIDC cho web app và mobile app. Authorization endpoint vẫn trả lời chậm; token endpoint timeout; JWKS endpoint đang hoạt động nhưng cache của một số region cũ; resource API xác minh JWT cục bộ. Một nhóm API khác dùng opaque token và introspection. Người dùng đang đăng nhập gặp refresh failure.

**Phân tích:**

1. Login mới và refresh token có thể thất bại vì token endpoint timeout.
2. JWT có key đã cache và còn hợp lệ có thể tiếp tục được xác minh cục bộ.
3. Verifier có cache JWKS cũ không được chấp nhận kid mới nếu chưa tải được public key tin cậy.
4. API opaque token không thể coi introspection timeout là active.
5. Browser RP session có thể tiếp tục tới idle/absolute timeout nếu không có revoke signal và policy cho phép.
6. Step-up và action đặc quyền cần IdP mới phải tạm dừng hoặc dùng cơ chế dự phòng đã được phê duyệt.
7. Retry đồng loạt có thể làm token endpoint quá tải lâu hơn.

**Phương án xử lý:**

- Incident commander xác nhận outage token endpoint và đánh giá riêng JWKS/introspection.
- Bật degraded mode đã review: cho phép session/JWT đã xác minh tiếp tục trong giới hạn; dừng login mới, refresh và action cần step-up khi không thể xác minh.
- Giữ signature, issuer, audience, expiry, token type và authorization checks.
- Opaque-token API dùng introspection cache còn freshness theo policy; khi cache hết hạn thì fail closed cho resource cần xác minh online.
- Client dùng backoff/jitter, không xóa refresh token chỉ vì timeout và không tạo refresh storm.
- Theo dõi key cache age, revoke propagation và request bị từ chối.
- Khi token endpoint phục hồi, refresh dần theo rate limit; revalidate session, revoke và pending transaction.
- Tắt degraded mode theo từng dependency sau synthetic test thành công.

**Câu hỏi:** Có nên bật chế độ chấp nhận mọi token đã ký bằng bất kỳ key nào đang cache không? Không. Chỉ chấp nhận key thuộc issuer trust configuration và còn được policy cho phép; unknown kid hoặc key bị nghi compromise phải bị từ chối.

## 19. Checklist thiết kế khả năng chịu IdP outage

- [ ] Liệt kê IdP, issuer, upstream, endpoint và dependency cho từng client/resource.
- [ ] Phân biệt authorization, token, JWKS, introspection, discovery, userinfo và MFA outage.
- [ ] Phân loại principal: user mới, existing session, mobile refresh, workload và admin.
- [ ] Ghi rõ session/token nào có thể xác minh offline và giới hạn của chúng.
- [ ] Định nghĩa fail-closed behavior cho signature, issuer, audience, expiry, MFA và authorization.
- [ ] Thiết kế degraded mode theo loại resource, action và assurance.
- [ ] Không biến timeout hoặc HTTP 5xx thành authentication success.
- [ ] Cache JWKS/discovery có max-age, refresh, stale policy và emergency invalidation.
- [ ] Từ chối unknown kid khi không lấy được key tin cậy.
- [ ] Cache introspection với TTL, revoke invalidation và stale-if-error giới hạn.
- [ ] Không kéo dài idle/absolute lifetime hoặc token expiry ngoài policy.
- [ ] Quản lý refresh retry bằng timeout, backoff, jitter, circuit breaker và concurrency limit.
- [ ] Bảo đảm client xử lý refresh rotation và response race an toàn.
- [ ] Chỉ failover tới issuer đã đăng ký, mapping subject và assurance tương đương.
- [ ] Có workload credential/certificate lifecycle và renewal window rõ.
- [ ] Định nghĩa multi-region consistency cho session, account status, key và revocation.
- [ ] Có break-glass account độc lập, scope hẹp, approval, audit và rotation.
- [ ] Phân loại resource public, read-only, private, sensitive, privileged và financial.
- [ ] Có synthetic test cho authorization, token, JWKS, introspection, MFA, federation và revoke.
- [ ] Đo endpoint availability, cache age, revoke propagation, retry và circuit breaker.
- [ ] Có runbook xác nhận, containment, degraded mode, recovery và post-incident review.
- [ ] Dùng UTC, reason code và correlation reference an toàn; không log token hoặc session ID.
- [ ] Diễn tập outage, key compromise, upstream failure và region partition.

## 20. Câu hỏi tự kiểm tra

**1. Identity Provider outage là gì?**  
Là sự cố khiến IdP hoặc dependency xác thực như authorization, token, JWKS, introspection, MFA hay federation không phục vụ đúng yêu cầu.

**2. IdP outage có làm mọi session hiện tại mất hiệu lực không?**  
Không. RP session hoặc JWT có thể tiếp tục nếu đã được xác minh, còn hạn và policy cho phép; login mới và refresh vẫn có thể thất bại.

**3. Khi introspection timeout có được coi token là active không?**  
Không. Timeout không phải kết quả xác minh. Chỉ dùng cache còn hợp lệ theo policy; nếu không thì fail closed.

**4. JWKS outage nhưng key đã cache thì sao?**  
Có thể tiếp tục xác minh token dùng key đã biết trong giới hạn freshness và revocation policy. Unknown kid phải bị từ chối nếu không lấy được key tin cậy.

**5. Có nên kéo dài session khi IdP outage?**  
Không tự động. Idle timeout, absolute timeout và token expiry vẫn phải được thực thi theo policy.

**6. Khi nào dùng degraded mode?**  
Khi có bằng chứng đã xác minh trước đó và resource/action được phân loại cho phép tiếp tục trong một cửa sổ giới hạn, với policy và owner rõ.

**7. Vì sao không tự failover sang IdP có cùng email?**  
Email không phải identity mapping duy nhất. Cần issuer trust, subject mapping, tenant và assurance equivalence.

**8. Break-glass khác backdoor thế nào?**  
Break-glass là quyền khẩn cấp có scope, thời hạn, approval, audit và quy trình revoke/rotate; backdoor là đường truy cập thường trực hoặc không kiểm soát.

**9. Refresh token timeout có nên xóa token khỏi app ngay không?**  
Không mặc nhiên. Timeout có thể transient; cần phân biệt lỗi mạng/5xx với invalid_grant hoặc revoked và retry có backoff.

**10. Sau khi IdP phục hồi cần làm gì?**  
Refresh metadata/key theo trust configuration, xử lý backlog có giới hạn, reconcile revocation/session state, hủy transaction hết hạn, tắt degraded mode và review incident.

**Ghi nhớ:** Khả năng chịu Identity Provider outage phải được thiết kế quanh bằng chứng đã xác minh, loại token/session và độ nhạy của resource. Cho phép session hoặc JWT hợp lệ tiếp tục trong giới hạn có thể giữ dịch vụ hoạt động; unknown key, introspection timeout không có cache hợp lệ, authentication mới và step-up bắt buộc phải được xử lý theo fail-closed policy. Cache, failover, degraded mode và break-glass đều cần giới hạn, giám sát, audit và diễn tập trước khi sự cố xảy ra.
