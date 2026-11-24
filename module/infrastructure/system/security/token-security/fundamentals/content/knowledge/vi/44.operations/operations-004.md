# Revoke sau incident

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định những credential và trạng thái ủy quyền cần thu hồi khi token bị lộ, bị đánh cắp hoặc bị sử dụng trái phép.
- Phân biệt khả năng thu hồi access token JWT, opaque token, refresh token, session, client credential và signing key.
- Lập trình tự ứng phó có kiểm soát: khoanh vùng, chặn phát hành mới, thu hồi, phân phối trạng thái thu hồi và xác minh.
- Xử lý khác nhau giữa sự cố lộ một token, lộ refresh token, lộ client secret và lộ signing key.
- Duy trì bằng chứng điều tra, giảm thiểu gián đoạn dịch vụ và ghi nhận quyết định vận hành.

## 1. Revoke sau incident là gì?

Khi phát hiện token bị lộ hoặc bị sử dụng trái phép, đội vận hành phải làm cho credential đó không còn cấp quyền truy cập theo phạm vi và thời điểm cần thiết. Công việc này thường được gọi là **token revocation** hoặc thu hồi token. Tuy nhiên, một sự cố token hiếm khi chỉ liên quan đến một chuỗi token. Token có thể đã được dùng để tạo token khác, mở session, cấp quyền cho client hoặc truy cập nhiều resource server.

Ví dụ:

~~~text
Refresh token bị lộ
       |
       v
Access token được cấp lại nhiều lần
       |
       +------> Orders API
       |
       +------> Billing API
       |
       +------> Files API
~~~

Chỉ xóa refresh token khỏi trình duyệt của người dùng không thu hồi các access token đã phát hành. Chỉ thu hồi một access token cũng không ngăn refresh token bị lộ tiếp tục xin token mới. Đội ứng phó cần xác định **phạm vi credential**, **quan hệ giữa các grant/token**, **resource bị ảnh hưởng** và **cơ chế kiểm tra token tại từng dịch vụ**.

Thu hồi token là một phần của incident response. Nó cần phối hợp với khóa ký, client secret, session, quyền truy cập, cache, gateway, workload và các hệ thống phụ thuộc.

## 2. Bắt đầu bằng phân loại sự cố

Trước khi chọn thao tác revoke, xác định loại thông tin bị lộ và phạm vi ảnh hưởng. Không phải mọi sự cố đều cần xoay signing key toàn hệ thống; ngược lại, nếu private signing key thực sự bị lộ thì chỉ thu hồi một JWT là không đủ.

| Dấu hiệu sự cố | Nguy cơ chính | Hành động cần xem xét |
| --- | --- | --- |
| Một access token bị lộ | Token bị replay tới khi hết hạn hoặc bị chặn | Thu hồi token nếu có trạng thái; denylist theo token ID/hash; chặn tại resource server |
| Refresh token bị lộ | Kẻ tấn công có thể tiếp tục lấy access token | Thu hồi refresh token/family, session và grant liên quan; yêu cầu xác thực lại |
| Client secret bị lộ | Kẻ tấn công có thể mạo danh confidential client | Vô hiệu hóa/đổi secret, kiểm tra client grants và token đã cấp |
| Signing private key bị lộ | Kẻ tấn công có thể tự ký token giả mạo | Ngừng tin key, loại khỏi JWKS/trust store, xoay key và xử lý cache |
| Opaque token bị lộ | Token có thể còn active trong token store | Revoke tại authorization server, xác minh introspection inactive |
| Thiết bị hoặc session bị chiếm | Nhiều token/cookie có thể cùng bị lộ | Thu hồi session, refresh family, device grant và token liên quan |
| Workload credential bị lộ | Dịch vụ khác có thể bị gọi thay mặt workload | Vô hiệu hóa credential workload, chặn token issuance và kiểm tra service-to-service grants |

Thu thập thông tin tối thiểu: thời điểm phát hiện, issuer, subject/client, token type, audience/resource, token ID hoặc fingerprint an toàn, phạm vi tenant, thời hạn, nơi token xuất hiện và hoạt động bất thường đã quan sát. Không yêu cầu người báo cáo gửi nguyên bearer token qua ticket, chat hoặc email.

## 3. Mô hình revoke theo từng loại credential

### 3.1 Opaque access token

Opaque token thường có trạng thái phía authorization server. Khi nhận yêu cầu thu hồi, authorization server có thể đánh dấu token không còn active hoặc xóa record theo mô hình lưu trữ. Resource server kiểm tra trạng thái bằng introspection hoặc một cơ chế tra cứu tin cậy khác.

Sau khi revoke:

- Introspection phải trả `active=false` cho token bị thu hồi.
- Resource server phải từ chối token khi nhận trạng thái inactive.
- Cache introspection và cache authorization phải được vô hiệu hóa hoặc hết hạn theo thời gian đã kiểm soát.
- Các bản sao token ở client, gateway và worker cần được xóa khỏi nơi lưu trữ phù hợp.

Nếu resource server cache kết quả `active=true` trong 5 phút, token có thể vẫn được chấp nhận trong khoảng cache đó. Thời gian cache vì vậy là một phần của **revocation latency** và phải được tính trong runbook.

### 3.2 Refresh token

Refresh token thường là credential quan trọng nhất trong sự cố vì nó có thể tiếp tục cấp access token. Thu hồi cần xác định:

- Token cụ thể bị lộ.
- Token family nếu hệ thống dùng rotation.
- Session/grant đã tạo token family.
- Các thiết bị hoặc client liên quan đến subject.
- Các access token đã được phát hành từ refresh token đó.

Với refresh token rotation, nếu authorization server phát hiện token cũ đã bị dùng lại sau khi rotation, nó có thể thu hồi token family theo policy. Khi incident đã xác nhận refresh token bị lộ, không chỉ thu hồi bản token cũ mà cần vô hiệu hóa cả nhánh liên quan để ngăn kẻ tấn công tiếp tục dùng token descendant.

RFC 7009 định nghĩa OAuth 2.0 Token Revocation endpoint. Khi revoke refresh token, authorization server có thể thu hồi các token liên quan theo policy và implementation; client không nên giả định mọi access token đã cấp đều bị thu hồi tức thì nếu server không cung cấp bảo đảm đó.

### 3.3 JWT access token

JWT access token thường được xác minh cục bộ bằng chữ ký và claims. Nếu resource server chỉ kiểm tra chữ ký, issuer, audience và expiration, nó có thể không biết token vừa bị revoke.

Các cách triển khai revoke sớm gồm:

1. **Denylist/token status:** resource server kiểm tra token ID như `jti` hoặc fingerprint của token với trạng thái revoke tập trung.
2. **Introspection/stateful validation:** resource server hỏi authorization server hoặc dịch vụ trạng thái trước khi chấp nhận token.
3. **Short lifetime:** giảm khoảng thời gian token còn giá trị nếu không có revoke tức thì.
4. **Issuer/key-level block:** chặn một issuer hoặc signing key khi sự cố ảnh hưởng đến toàn bộ token được ký bằng key đó.

Không có một thao tác xóa JWT khỏi client nào có thể làm mọi bản sao JWT mất hiệu lực. Nếu không có denylist, introspection hoặc thay đổi trust/key, token tự chứa có thể tiếp tục được chấp nhận đến `exp`.

### 3.4 Signing key bị lộ

Đây là tình huống nghiêm trọng hơn lộ một token. Kẻ tấn công có thể tự tạo JWT với claims tùy ý và ký bằng private key bị lộ. Cần:

- Dừng phát hành token bằng key bị ảnh hưởng.
- Đánh dấu key ID (`kid`) bị xâm phạm trong hệ thống quản lý khóa.
- Gỡ key khỏi JWKS/trust set theo kế hoạch khẩn cấp và phân phối thay đổi tới resource server.
- Tạo key mới trong KMS/HSM hoặc môi trường bảo vệ phù hợp; không tái sử dụng private key đã lộ.
- Xác minh verifier đã làm mới JWKS cache và từ chối token được ký bằng key cũ.
- Xác định token hợp lệ đã phát hành trước sự cố và token giả mạo có thể đã được tạo trong khoảng key bị lộ.

Trong key rotation thông thường, có thể duy trì key cũ trong thời gian overlap để xác minh token cũ còn hạn. **Khi private key đã bị xâm phạm, overlap có thể cho phép token giả mạo tiếp tục được chấp nhận.** Quyết định gỡ key phải dựa trên mức độ sự cố, khả năng gián đoạn và phạm vi hệ thống, đồng thời phải được truyền tới tất cả verifier.

### 3.5 Client secret, certificate và workload credential

Nếu client secret bị lộ, disable hoặc rotate secret tại authorization server/secret manager; kiểm tra client có thể tạo token với grant nào và revoke token/grant được cấp qua client đó. Nếu dùng mTLS, đánh giá certificate/private key và binding của access token. Nếu workload dùng credential từ cloud identity hoặc service account, vô hiệu hóa credential tương ứng và kiểm tra token descendant.

Đừng chỉ cập nhật secret trong một nơi. Các replica, worker, sidecar, CI variable, secret cache và deployment cũ có thể vẫn giữ credential cũ. Xác minh rollout đã hoàn tất và credential cũ bị từ chối.

## 4. Quy trình ứng phó theo thứ tự

Một runbook thực tế có thể đi theo các bước sau:

~~~mermaid
flowchart TD
    A["Phát hiện token/credential bị lộ"] --> B["Phân loại loại credential và phạm vi"]
    B --> C["Khoanh vùng subject, client, tenant, audience"]
    C --> D["Chặn phát hành mới và thu hồi grant/session"]
    D --> E["Revoke token, family hoặc key theo phạm vi"]
    E --> F["Phân phối denylist/JWKS/cache invalidation"]
    F --> G["Xác minh token cũ bị từ chối ở các resource"]
    G --> H["Theo dõi replay và token issuance bất thường"]
    H --> I["Lưu bằng chứng, khôi phục và đóng incident"]
~~~

### Bước 1: Xác nhận và khoanh vùng

Xác định token type, issuer, subject/client, audience, tenant, thời gian phát hành và expiration. Tìm các request bất thường theo token ID/fingerprint, subject, client, source network và resource. Nếu chỉ có một token cụ thể bị lộ, khoanh vùng token đó và các token descendant. Nếu signing key hoặc client credential bị lộ, mở rộng phạm vi theo toàn bộ token/grant có thể bị ảnh hưởng.

### Bước 2: Ngăn phát hành mới

Tùy loại sự cố, disable client, chặn refresh grant, tạm dừng token issuance cho subject/client hoặc ngừng ký bằng key bị xâm phạm. Đây là bước quan trọng để ngăn attacker tạo thêm token trong lúc đội vận hành đang thu hồi token cũ.

Không khóa toàn bộ authorization server nếu chỉ có một credential bị ảnh hưởng và có thể cô lập chính xác. Tuy nhiên, nếu chưa thể xác định phạm vi của signing key bị lộ, biện pháp chặn rộng hơn có thể cần thiết để giảm rủi ro.

### Bước 3: Thu hồi token và quyền liên quan

Revoke refresh token family, session, authorization grant, opaque token và các credential liên quan. Với JWT, cập nhật denylist hoặc trạng thái kiểm tra; nếu key bị lộ, thực hiện key emergency rotation và chặn key cũ. Đánh giá cả token được phát hành cho service-to-service hoặc delegated actor.

### Bước 4: Phân phối thay đổi

Đẩy trạng thái revoke tới authorization server, resource server, API gateway, introspection cache, JWKS cache, edge node, background worker và các dịch vụ đang giữ token. Xác định SLA phân phối; nếu có node chưa nhận thay đổi, node đó vẫn có thể chấp nhận credential cũ.

### Bước 5: Xác minh từ chối

Thử lại bằng token đã bị revoke tại mọi loại resource server liên quan. Xác minh access token không còn truy cập được, refresh token không cấp token mới, opaque token inactive, JWT bị denylist hoặc verifier từ chối key cũ. Kiểm tra cả cache hit và cache miss, nhiều replica và vùng triển khai.

### Bước 6: Giám sát sau thu hồi

Theo dõi các dấu hiệu replay, token issuance bất thường, refresh reuse, client authentication thất bại, request bị từ chối theo token ID/key ID và các node còn dùng cấu hình cũ. Nếu attacker tiếp tục thử token cũ, giữ nguyên log/telemetry phục vụ điều tra và cập nhật phạm vi incident.

## 5. Bảng quyết định thao tác theo tình huống

| Tình huống | Thao tác chính | Xác minh bắt buộc |
| --- | --- | --- |
| Một opaque access token bị lộ | Revoke token record | Introspection inactive; API trả 401 |
| Một JWT bị lộ, key không bị lộ | Denylist theo jti/fingerprint nếu có; xem xét revoke session/grant | Mọi verifier liên quan từ chối token |
| Refresh token bị lộ | Revoke token family, session/grant và access token descendant theo khả năng | Refresh thất bại; token descendant không truy cập được theo policy |
| Client secret bị lộ | Disable/rotate client credential, chặn grant và xem token client đã cấp | Secret cũ không xác thực; token/grant bị ảnh hưởng bị chặn |
| Signing private key bị lộ | Dừng ký, gỡ key, phát hành key mới, refresh trust cache | Token giả mạo/cũ ký bằng key bị xâm phạm bị từ chối |
| Workload credential bị lộ | Disable workload identity/secret/certificate và revoke grants | Service-to-service request dùng credential cũ bị từ chối |
| Session/device bị chiếm | Revoke session/device grant và refresh family | Cookie/session cũ và token liên quan không còn dùng được |

## 6. Xây dựng denylist cho JWT

Nếu kiến trúc yêu cầu thu hồi JWT trước `exp`, resource server cần một tín hiệu trạng thái có thể kiểm tra. Một lựa chọn là denylist theo issuer và `jti`:

~~~text
key = revoked:<issuer-id>:<jti>
value = incident-id
ttl = exp - now + clock-skew
~~~

TTL của denylist nên ít nhất bao phủ đến thời điểm token không còn được chấp nhận, có tính clock skew của verifier. Khi token hết hạn, record có thể được dọn tự động. Nếu không có `jti` đáng tin cậy, có thể dùng fingerprint/hash của token đã xác minh; tránh lưu raw bearer token trong kho denylist.

Các lưu ý:

- `jti` phải được lấy từ JWT sau khi chữ ký và claims đã được xác minh.
- Kết hợp issuer với `jti` vì ID có thể không duy nhất giữa các issuer.
- Chỉ cho phép hệ thống vận hành có quyền ghi denylist; client không được tự đánh dấu token khác bị revoke.
- Phân phối denylist tới mọi verifier hoặc dùng kho trạng thái có độ nhất quán phù hợp.
- Xác định hành vi khi kho denylist không khả dụng: fail-closed cho tài nguyên nhạy cảm hoặc áp policy fallback đã được đánh giá rõ ràng.
- Đặt rate limit và monitoring để tránh denylist bị lợi dụng làm vector tiêu thụ bộ nhớ.

Ví dụ pseudo-code:

~~~java
boolean accept(VerifiedJwt token) {
    if (token.isExpired(clock.instant(), allowedClockSkew)) {
        return false;
    }

    String revocationKey =
            token.issuer() + ":" + token.jwtId();

    if (revocationStore.isRevoked(revocationKey)) {
        return false;
    }

    return true;
}
~~~

`VerifiedJwt` ở đây là kiểu dữ liệu chỉ được tạo sau khi thư viện JWT đã xác minh chữ ký, issuer, audience, expiration và các policy khác. Không đưa một payload chỉ mới decode vào hàm kiểm tra denylist rồi coi đó là token đáng tin cậy.

## 7. Kiểm soát revocation latency

**Revocation latency** là thời gian từ lúc hệ thống ghi nhận revoke đến khi mọi điểm thực thi quyền từ chối token. Độ trễ có thể đến từ:

- Cache introspection hoặc cache kết quả authorization.
- JWKS cache ở resource server.
- Event bus chậm hoặc mất sự kiện.
- Replica chưa đồng bộ trạng thái.
- Worker/sidecar giữ credential cũ trong memory.
- Client tiếp tục gửi token đã bị revoke.

Đặt mục tiêu rõ ràng theo mức độ nhạy cảm. Ví dụ, hệ thống thanh toán có thể yêu cầu revoke propagation trong vài giây, trong khi một môi trường nội bộ ít nhạy cảm có thể chấp nhận khoảng dài hơn. Đây là SLA thiết kế, không có một con số chuẩn áp dụng cho mọi hệ thống.

Nên đo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `revocation_requested_at` | Thời điểm bắt đầu thao tác |
| `revocation_committed_at` | Thời điểm authorization server ghi trạng thái revoke |
| `last_verifier_ack_at` | Thời điểm verifier cuối cùng xác nhận cập nhật |
| `revocation_propagation_seconds` | Thời gian phân phối trạng thái |
| `post_revoke_accept_count` | Số lần token bị revoke vẫn được chấp nhận |
| `revocation_failure_count` | Số thao tác revoke hoặc xác minh thất bại |

Nếu `post_revoke_accept_count` lớn hơn 0 sau SLA, incident chưa được kiểm soát hoàn toàn. Cần xác định verifier nào còn nhận token và chặn hoặc cập nhật node đó.

## 8. Bằng chứng, audit và bảo vệ dữ liệu điều tra

Ghi lại sự kiện vận hành với dữ liệu tối thiểu:

- Incident ID và người/đội thực hiện.
- Subject/client/tenant/issuer đã được xác định.
- Token ID hoặc fingerprint an toàn, key ID và loại credential.
- Thời điểm yêu cầu revoke, thời điểm hoàn tất và verifier đã xác nhận.
- Kết quả từng thao tác, lỗi, retry và ngoại lệ được phê duyệt.
- Các resource server đã thử xác minh token sau revoke.

Không ghi raw access token, refresh token, authorization header, client secret, private key hoặc cookie session vào log. Log phải có access control, retention và integrity phù hợp. Nếu cần bảo toàn bằng chứng về token bị lộ, lưu fingerprint và metadata an toàn theo quy trình evidence handling, không phát tán credential thật qua hệ thống ticket.

Không xóa log bảo mật hoặc audit trail trong quá trình cleanup incident. Việc thu hồi credential và việc bảo toàn bằng chứng điều tra là hai nhiệm vụ khác nhau.

## 9. Ví dụ runbook: refresh token bị đánh cắp

Giả sử một refresh token của user-42 thuộc Tenant A xuất hiện trong log của một hệ thống không đáng tin cậy. Authorization server dùng refresh token rotation và phát hành access token JWT cho Orders API, Billing API.

**Khoanh vùng**

- Xác định subject user-42, tenant-a, client ID, token family và thời điểm lộ.
- Dùng token family ID hoặc fingerprint an toàn để tìm refresh events.
- Xác định access token descendant, audience, `jti` và resource server đã được gọi.

**Containment**

- Thu hồi refresh token family và session/grant liên quan.
- Nếu phát hiện token đã bị sử dụng lại, áp dụng policy reuse detection và giữ nguyên audit event.
- Ngăn client dùng refresh token cũ để xin access token mới.
- Đưa các access JWT descendant vào denylist nếu hệ thống hỗ trợ; nếu không, đánh giá TTL còn lại và biện pháp chặn ở gateway/resource server.

**Verification**

- Thử refresh bằng token cũ: phải thất bại.
- Thử refresh bằng token mới nhất trong family đã bị revoke: phải thất bại.
- Gọi Orders API và Billing API bằng access token descendant: phải bị từ chối theo cơ chế revoke đã triển khai.
- Kiểm tra các replica và cache đều nhận trạng thái revoke.

**Recovery**

- Yêu cầu người dùng xác thực lại theo policy và kiểm tra thiết bị/session.
- Cấp token mới chỉ sau khi credential compromise đã được xử lý.
- Theo dõi refresh reuse, login bất thường và request bị từ chối trong khoảng giám sát sau incident.

## 10. Những sai lầm thường gặp

1. **Chỉ xóa token khỏi client:** bản sao ở attacker hoặc token store vẫn tồn tại.
2. **Chỉ revoke refresh token:** access token đã cấp có thể vẫn hoạt động đến `exp` nếu không có cơ chế chặn.
3. **Coi JWT luôn revoke được tức thì:** verifier stateless không tự biết trạng thái revoke.
4. **Xóa private key nhưng giữ public key cache:** verifier vẫn có thể chấp nhận token ký bằng key cũ.
5. **Rotate key bình thường khi private key đã bị lộ:** overlap có thể cho phép attacker tiếp tục ký token giả.
6. **Không kiểm tra token descendant:** token đã được exchange hoặc cấp tiếp có thể còn hiệu lực.
7. **Chỉ cập nhật một replica:** các node chưa nhận denylist/JWKS update vẫn có thể chấp nhận token.
8. **Ghi raw token vào ticket/log:** incident response vô tình tạo thêm nơi rò rỉ credential.
9. **Không đo revocation latency:** đội vận hành không biết khi nào mọi resource server đã được cập nhật.
10. **Đóng incident ngay khi API revoke trả 200:** chưa chứng minh token thực sự bị từ chối ở điểm thực thi quyền.

## 11. Checklist đóng incident

- [ ] Đã xác định token/credential type, issuer, subject/client, audience và phạm vi tenant.
- [ ] Đã ngăn credential bị lộ phát hành thêm token hoặc session.
- [ ] Đã revoke refresh family, session, grant và opaque token liên quan.
- [ ] Đã chặn JWT theo denylist/stateful check hoặc xác định rõ thời điểm hết hạn và biện pháp bù.
- [ ] Nếu signing key bị lộ, đã dừng ký, thay key, gỡ key cũ và xử lý JWKS/verifier cache.
- [ ] Đã rotate/disable client secret, certificate hoặc workload credential nếu bị ảnh hưởng.
- [ ] Đã xác minh token cũ bị từ chối ở mọi resource server liên quan.
- [ ] Đã xác minh không còn cache/replica/worker dùng trạng thái cũ.
- [ ] Revocation latency nằm trong SLA và không còn post-revoke acceptance.
- [ ] Audit evidence được lưu an toàn, không chứa raw token hoặc private key.
- [ ] Đã theo dõi replay, refresh reuse và issuance bất thường sau containment.
- [ ] Đã ghi nhận nguyên nhân gốc, phạm vi ảnh hưởng và hành động phòng ngừa.

## Ghi nhớ

**Revoke sau incident phải chặn cả khả năng dùng token hiện tại lẫn khả năng tạo token mới từ credential đã lộ.** Opaque token thường được thu hồi tại token store; refresh token cần xem xét cả family và session; JWT stateless cần denylist, introspection, key-level block hoặc chờ expiration theo policy; signing key bị lộ cần emergency rotation và phân phối trust update. Chỉ đóng incident khi đã xác minh mọi verifier liên quan từ chối credential bị ảnh hưởng và độ trễ revoke nằm trong mục tiêu vận hành.

### Tài liệu tham khảo

- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 7517 — JSON Web Key (JWK), JWKS và key identifiers: https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 7519 — JSON Web Token (JWT), claims như `iss`, `aud`, `exp`, `jti`: https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- OWASP Session Management Cheat Sheet — session invalidation and lifecycle: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
