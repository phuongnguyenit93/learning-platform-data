# Kiểm tra chống phát lại khi hợp đồng yêu cầu dùng một lần

## 1. Bắt đầu từ hợp đồng one-time-use

Không phải mọi JWT đều được thiết kế để chỉ sử dụng một lần. Access token thông thường là bearer credential có thể được dùng cho nhiều request trong thời hạn hiệu lực. Ngược lại, authorization code, one-time token, nonce, proof hoặc một thao tác nghiệp vụ cụ thể có thể có hợp đồng giới hạn số lần sử dụng.

Vì vậy, trước khi viết test chống phát lại (replay), cần xác định chính xác **đối tượng nào chỉ được chấp nhận một lần, trong phạm vi nào, trong khoảng thời gian nào và kết quả của lần sử dụng đầu tiên được lưu ra sao**.

Các trường hợp khác nhau:

| Đối tượng | Hợp đồng thường gặp | Hành vi khi phát lại |
| --- | --- | --- |
| Access token | Được dùng nhiều lần đến khi hết hạn/thu hồi | Không mặc định từ chối chỉ vì token đã xuất hiện |
| One-time JWT/capability | Chỉ được consume một lần cho mục đích/phạm vi xác định | Từ chối lần consume tiếp theo |
| OAuth authorization code | Chỉ được redeem một lần | Token endpoint từ chối code đã dùng |
| OIDC nonce | Gắn kết ID Token với authentication request | Client từ chối response không khớp giao dịch |
| DPoP proof | Proof có định danh riêng và cửa sổ chấp nhận ngắn | Resource server áp dụng replay detection theo policy/profile |
| Refresh token rotation | Token cũ bị thay thế sau khi dùng | Reuse token cũ có thể kích hoạt thu hồi token family |
| Business operation | Một ý định nghiệp vụ chỉ tạo side effect một lần | Retry có thể trả kết quả cũ, không thực hiện side effect lần hai |

Không suy ra one-time-use chỉ từ sự hiện diện của claim jti, nonce hoặc exp. Các trường này cung cấp định danh/ngữ cảnh/thời gian; ứng dụng phải thực thi hợp đồng bằng trạng thái và logic phù hợp.

## 2. Định nghĩa thuộc tính cần kiểm thử

Một test chống replay tốt kiểm tra các thuộc tính quan sát được, không chỉ kiểm tra một hàm cache được gọi.

### 2.1. At-most-once acceptance

Với một credential có hợp đồng consume-once, trong phạm vi đã định nghĩa, không quá một yêu cầu được xác nhận là lần sử dụng đầu tiên.

Nếu có N request đồng thời cùng consume một credential, kết quả mong đợi là:

- Chính xác một request thắng nếu credential còn hợp lệ và không có lỗi khác.
- Các request còn lại nhận kết quả replay/already-consumed.
- Không có hai worker cùng nhận trạng thái “lần đầu” cho cùng định danh.

### 2.2. At-most-once side effect

Đối với thao tác nghiệp vụ, điều quan trọng thường là side effect chỉ xảy ra một lần. Ví dụ một thanh toán chỉ được ghi sổ một lần dù message hoặc HTTP request được gửi lại.

At-most-once acceptance và at-most-once side effect không giống nhau. Một proof có thể chỉ được chấp nhận một lần nhưng thao tác phía sau có thể thất bại. Ngược lại, một API có thể nhận nhiều retry hợp lệ nhưng dùng idempotency để chỉ tạo side effect một lần.

### 2.3. Phạm vi định danh

Test phải xác định khóa replay theo hợp đồng. Tùy giao thức, khóa có thể dựa trên issuer, token profile, audience/resource, client hoặc key thumbprint, cùng jti/nonce/code ID.

Không dùng jti đơn lẻ làm khóa toàn cục nếu hệ thống có nhiều issuer hoặc nhiều loại proof. Cũng không được thêm namespace tùy tiện làm thay đổi semantics của giao thức. Hãy dùng đúng profile và phạm vi uniqueness đã công bố.

### 2.4. Thời hạn tiêu thụ

Một credential đã dùng phải được ghi nhận đủ lâu để mọi verifier còn có thể chấp nhận nó đều nhìn thấy trạng thái đã dùng. Nếu replay marker hết hạn trước khi credential hết cửa sổ hợp lệ, attacker có thể phát lại sau khi marker bị xóa.

## 3. Xây dựng test oracle từ contract

Test oracle là quy tắc quyết định một kết quả có đúng hay không. Hãy viết oracle trước khi triển khai test.

Ví dụ hợp đồng cho one-time capability:

~~~text
Given:
  capability C is valid for job J and action A
  C has not been consumed

When:
  two or more requests attempt to consume C concurrently

Then:
  exactly one request is accepted as the first consumption
  all other requests are rejected as already consumed
  the protected action is committed no more than once
~~~

Với retry của business operation:

~~~text
Given:
  operation O has idempotency key K and request fingerprint F

When:
  the same request is submitted again with K and F

Then:
  return the stored/in-progress result
  do not execute the business side effect again

When:
  K is reused with a different fingerprint F2

Then:
  reject the conflicting reuse
~~~

Không dùng một oracle cho mọi trường hợp. Replay của one-time proof thường phải bị từ chối; retry của thao tác idempotent thường được trả lại kết quả trước đó.

## 4. Chuẩn bị test fixture an toàn và có thể lặp lại

Test cần tạo token/proof có thể kiểm soát chính xác:

- Issuer và audience.
- Token type/profile.
- jti hoặc nonce.
- iat, nbf và exp.
- Signing key và thuật toán được phép.
- Subject, client hoặc key thumbprint.
- Resource/action được ràng buộc.
- Trạng thái ban đầu trong replay store.

Nên dùng khóa kiểm thử riêng, không dùng private key, HMAC secret hoặc token production. Fixture cần tạo token hợp lệ và token đã bị sửa để phân biệt parser, signature verification và replay logic.

Đồng hồ trong test nên được kiểm soát bằng clock abstraction hoặc test clock. Tránh phụ thuộc sleep thật vì test có thể chậm và không ổn định. Với hệ thống phân tán, cần mô phỏng các node có clock skew khác nhau.

Không ghi raw token vào test report, log CI hoặc artifact chia sẻ. Nếu cần đối chiếu, ghi fingerprint không thể dùng lại làm credential.

## 5. Test lần đầu, lần thứ hai và ranh giới thời gian

Đây là nhóm kiểm thử cơ bản nhất cho one-time credential.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Consume credential hợp lệ lần đầu | Chấp nhận và ghi nhận đã dùng |
| Consume lại cùng credential ngay sau đó | Từ chối replay |
| Consume sau khi credential hết hạn | Từ chối vì hết hạn |
| Credential chưa đến nbf | Từ chối vì chưa có hiệu lực |
| Credential bị thu hồi trước lần dùng đầu | Từ chối |
| Credential sai issuer/audience/purpose | Từ chối và không đánh dấu nhầm một credential khác |
| Credential có jti trùng nhưng thuộc namespace khác theo contract | Xử lý độc lập nếu contract định nghĩa namespace khác nhau |
| Credential đã consume ở một action rồi dùng cho action khác | Từ chối hoặc cho phép đúng theo phạm vi binding đã định nghĩa |

Kiểm tra cả trạng thái replay store sau mỗi trường hợp. Một token sai chữ ký hoặc sai audience không nên làm tiêu thụ một credential hợp lệ có cùng định danh nếu bước xác minh bắt buộc chưa đạt.

## 6. Kiểm thử tính nguyên tử khi có request đồng thời

Lỗi nghiêm trọng thường xuất hiện khi triển khai theo hai thao tác riêng:

1. Đọc xem định danh đã tồn tại chưa.
2. Nếu chưa, ghi định danh vào cache.

Hai request có thể cùng đọc thấy “chưa tồn tại” rồi cả hai cùng ghi và được chấp nhận. Test tuần tự không phát hiện được race condition này.

### 6.1. Concurrent consume test

Tạo một credential hợp lệ, sau đó dùng barrier để N worker gửi consume gần như đồng thời. Không dùng sleep ngẫu nhiên để tạo race; barrier giúp các request bắt đầu cùng một thời điểm.

Đo các kết quả:

- Số request được đánh dấu first-consume.
- Số request bị đánh dấu replay.
- Số side effect đã commit.
- Số bản ghi replay được tạo.

Với hợp đồng consume-once, invariant là:

~~~text
accepted_first_consumption_count == 1
replay_rejected_count == N - 1
committed_side_effect_count <= 1
~~~

Chạy lặp nhiều vòng với nhiều N khác nhau, nhưng test phải có timeout và giới hạn tài nguyên để không biến kiểm thử thành tải không kiểm soát.

### 6.2. Kiểm tra primitive nguyên tử

Nếu hệ thống dùng unique constraint, compare-and-set, atomic add hoặc transaction, test nên chạy qua cơ chế thật đó. Mock một hàm cache luôn trả về “insert thành công” không chứng minh tính nguyên tử của kho trạng thái.

### 6.3. Race giữa consume và revoke

Kiểm thử hai luồng đồng thời:

- Request A consume credential.
- Request B revoke credential.

Hợp đồng cần định nghĩa thứ tự tuyến tính hóa (linearization point): nếu consume thắng trước revoke thì hành động có thể được phép; nếu revoke thắng trước consume thì request phải bị từ chối. Không để kết quả phụ thuộc ngẫu nhiên vào instance nhận request.

## 7. Kiểm thử nhiều instance và nhiều vùng

Replay prevention chỉ có ý nghĩa trong phạm vi verifier cùng chia sẻ trạng thái. Cache cục bộ riêng của mỗi instance có thể cho phép cùng proof được chấp nhận ở nhiều instance.

Các kịch bản cần có:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Dùng credential lần đầu ở instance A | Chấp nhận và lưu trạng thái dùng |
| Phát lại cùng credential ở instance B | B nhìn thấy trạng thái dùng và từ chối |
| Hai instance cùng consume đồng thời | Chỉ một instance thắng |
| Instance restart sau khi consume | Trạng thái đã dùng không bị mất nếu contract yêu cầu tồn tại qua restart |
| Failover sang replica | Không làm credential đã dùng trở lại trạng thái mới |
| Hai region cùng nhận một proof | Không có hai lần chấp nhận nếu contract yêu cầu one-time-use toàn cục |
| Region bị partition khỏi kho trạng thái | Hành vi đúng fail-closed hoặc policy dự phòng đã công bố |

Nếu thiết kế chỉ bảo đảm one-time-use trong một region, phải ghi rõ phạm vi đó và kiểm thử rằng request không thể vô tình vượt sang region khác mà làm rộng semantics.

## 8. Kiểm thử TTL, expiry và clock skew

Replay marker phải sống ít nhất đến khi credential không còn được bất kỳ verifier nào chấp nhận. Thời hạn cache cần được tính từ quy tắc chấp nhận thực tế, không chỉ sao chép exp một cách máy móc.

Ví dụ, nếu verifier cho phép clock skew S và chấp nhận proof đến thời điểm T theo policy, marker không được biến mất trước khi mọi verifier đã qua thời điểm cuối cùng có thể chấp nhận proof đó.

Các test thời gian:

- Consume ở ngay trước exp.
- Consume đúng ranh giới exp theo quy tắc so sánh của hệ thống.
- Consume ngay sau exp.
- Đặt clock của node A nhanh hơn node B.
- Đặt clock của node A chậm hơn node B.
- Replay sau khi cache TTL vừa hết.
- Replay sau khi credential đã hết hiệu lực ở mọi verifier.
- Restart node khi marker còn TTL.

Kiểm tra rằng cache không xóa marker quá sớm. Đồng thời, marker cần được dọn sau khi không còn khả năng replay để tránh tăng bộ nhớ vô hạn.

## 9. Kiểm thử retry và lỗi giữa chừng

Một request có thể được xác minh và consume thành công, nhưng worker có thể crash trước khi trả response. Client không biết kết quả và gửi lại.

Đây là điểm cần phân biệt:

- One-time proof đã tiêu thụ: proof cũ phải bị từ chối; client tạo proof mới nếu protocol cho phép retry.
- Business operation đã có idempotency key: retry cùng key và cùng payload có thể nhận kết quả đã lưu, không chạy side effect lần hai.

Các fault-injection test nên mô phỏng:

1. Crash trước khi ghi replay marker.
2. Crash sau khi ghi marker nhưng trước khi xử lý nghiệp vụ.
3. Crash sau side effect nhưng trước khi lưu kết quả.
4. Crash sau commit nhưng trước ACK message.
5. Timeout khi gọi dịch vụ downstream, không rõ side effect đã commit hay chưa.
6. Response bị mất trên đường về client.

Mỗi điểm lỗi phải có trạng thái phục hồi xác định. Không được xóa marker để “cho retry chạy lại” nếu việc đó cho phép replay credential cũ. Với nghiệp vụ, dùng transaction, outbox/inbox, operation ID hoặc idempotency record để đối soát side effect.

## 10. Kiểm thử authorization code và PKCE

Authorization code của OAuth 2.0 là credential dùng để đổi token và phải được redeem một lần. Token endpoint cần từ chối code đã dùng, hết hạn hoặc không khớp client/redirect URI/PKCE verifier.

Test nên bao gồm:

- Redeem code hợp lệ lần đầu thành công.
- Redeem lại cùng code bị từ chối.
- Hai token request đồng thời cùng code: chỉ một request thành công.
- Code của client A bị client B redeem: từ chối.
- Redirect URI khác với giao dịch ban đầu: từ chối.
- PKCE verifier sai: từ chối.
- Code hết hạn: từ chối.
- Code đã bị consume nhưng response bị mất: redeem lại vẫn không phát hành token lần hai.

Không dùng việc chữ ký JWT của access token đầu ra hợp lệ để kết luận authorization code flow an toàn. Replay protection nằm ở token endpoint và trạng thái authorization code.

## 11. Kiểm thử DPoP proof và nonce

DPoP proof là JWT được client ký để chứng minh possession của khóa và gắn request với method, URI và access token. Khi áp dụng replay detection, cần kiểm tra cả proof và trạng thái đã thấy.

Các test quan trọng:

- Proof hợp lệ với method và URI hiện tại được chấp nhận.
- Cùng proof JWT được gửi lại trong cửa sổ chấp nhận bị từ chối theo replay policy.
- jti khác nhau nhưng cùng khóa được xử lý như các proof riêng.
- jti trùng trong cùng phạm vi proof bị phát hiện.
- htm hoặc htu không khớp request: từ chối.
- ath không khớp access token: từ chối khi claim này được yêu cầu.
- Thumbprint khóa proof không khớp binding cnf.jkt của access token: từ chối.
- iat ngoài cửa sổ cho phép: từ chối.
- Nonce sai, hết hạn hoặc đã dùng theo semantics one-time: từ chối.
- Nonce mới được cấp có thể dùng trong request kế tiếp theo protocol.
- Replay cache mất kết nối: áp dụng fail-open/closed theo policy đã định, không âm thầm bỏ qua kiểm tra.

Không kết luận mọi DPoP proof phải bị từ chối chỉ vì cùng access token được sử dụng nhiều lần. Mỗi request hợp lệ có thể cần proof mới. Cần phân biệt access-token reuse hợp lệ với proof replay.

### 11.1. OIDC nonce gắn với authentication transaction

OIDC nonce trong ID Token khác DPoP server nonce. Client tạo nonce cho authentication request, lưu nó gắn với transaction đang chờ và so khớp chính xác với claim nonce trong ID Token đã xác minh. Khi callback đã được xử lý, transaction phải được đánh dấu hoàn tất để response cũ không thể hoàn tất lại cùng lần đăng nhập.

Test nên bao gồm:

- ID Token chứa đúng nonce của transaction đang chờ: tiếp tục xử lý nếu các validation khác đạt.
- Nonce bị thiếu khi request yêu cầu nonce: từ chối.
- Nonce không khớp hoặc thuộc transaction khác: từ chối.
- Callback cũ được gửi lại sau khi transaction hoàn tất: không tạo phiên đăng nhập thứ hai.
- Hai callback đồng thời cùng hoàn tất một transaction: chỉ một lần chuyển trạng thái transaction thành completed.
- Nonce của một issuer/client không được dùng để hoàn tất transaction của issuer/client khác.

Không dùng cùng một kho trạng thái hoặc semantics cho OIDC nonce và DPoP nonce chỉ vì cả hai đều có tên nonce. Phạm vi, bên tạo, bên kiểm tra và vòng đời của chúng khác nhau.

## 12. Kiểm thử refresh token rotation và reuse detection

Khi refresh token rotation được dùng, mỗi lần refresh thành công sẽ thay thế token cũ bằng token mới theo chính sách. Reuse token cũ có thể chỉ ra credential đã bị sao chép.

Test nên kiểm tra:

- Refresh token đang hoạt động được dùng một lần theo rotation contract.
- Token cũ bị từ chối sau khi đã rotate.
- Reuse token cũ kích hoạt xử lý token family theo policy.
- Token của family khác không bị ảnh hưởng.
- Refresh token hết hạn hoặc bị revoke bị từ chối.
- Hai refresh request đồng thời không tạo ra hai nhánh token hoạt động trái contract.
- Response bị mất sau khi rotate không làm token cũ tự hoạt động trở lại.
- Grace period, nếu có, được giới hạn đúng thời gian và điều kiện.

Kiểm thử phải tính đến client retry và nhiều tab/thiết bị. Nếu hệ thống cho phép grace period để giảm false positive, test phải chứng minh giới hạn đó không biến token cũ thành credential có thể sử dụng lại tùy ý.

## 13. Kiểm thử idempotency cho side effect nghiệp vụ

Idempotency không có nghĩa request lặp luôn bị từ chối. Nó thường có nghĩa cùng một ý định nghiệp vụ tạo ra hiệu ứng tối đa một lần.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Lần đầu với key K và payload P | Tạo operation và lưu kết quả |
| Retry key K, payload P | Trả kết quả trước đó hoặc trạng thái đang xử lý |
| Key K được dùng với payload P2 khác P | Từ chối xung đột |
| Hai request đồng thời với K/P | Một operation logic và tối đa một side effect |
| Worker crash sau side effect | Retry tra cứu operation result, không lặp side effect |
| Idempotency record hết retention | Hành vi theo hợp đồng; không vô tình nhận lại request cũ như mới nếu rủi ro vẫn tồn tại |
| Cùng key ở hai principal/tenant khác nhau | Namespace ngăn va chạm và rò rỉ kết quả |

Kiểm tra fingerprint của request, principal/tenant, endpoint và operation scope. Không để một người dùng đoán idempotency key rồi đọc kết quả của người khác.

## 14. Kiểm thử khi replay store không khả dụng

Nếu hợp đồng yêu cầu one-time-use nghiêm ngặt, hệ thống không thể biết credential đã dùng hay chưa khi kho trạng thái không truy cập được.

Kiểm thử hai chính sách:

- **Fail-closed:** từ chối hoặc tạm dừng thao tác khi không thể kiểm tra trạng thái.
- **Fail-open:** tiếp tục xử lý dù không thể xác minh replay state.

Với thanh toán, đổi mật khẩu, cấp quyền hoặc redeem one-time credential, fail-open có thể cho phép hành động trùng hoặc vượt qua bước bảo vệ. Nếu hệ thống chọn fail-open cho một loại thao tác ít rủi ro, giới hạn và hậu quả phải được ghi rõ.

Test cần mô phỏng:

- Timeout kết nối replay store.
- Connection pool cạn.
- Store trả lỗi ghi nhưng không rõ commit đã xảy ra hay chưa.
- Store failover và dữ liệu replication chưa đồng bộ.
- Cache node mất dữ liệu sau restart.
- Một phần region không nhận được lệnh revoke/consume.

Không chuyển lỗi hạ tầng thành kết quả “credential chưa dùng”. Trạng thái unknown phải được xử lý riêng với trạng thái unused.

## 15. Kiểm thử dữ liệu sai và tấn công đầu vào

Replay prevention không thay thế kiểm tra token. Trước khi consume trạng thái, token/proof phải vượt qua các kiểm tra cần thiết theo profile.

Các test âm:

- JWT sai định dạng hoặc vượt giới hạn kích thước.
- Chữ ký không hợp lệ.
- Thuật toán không nằm trong allowlist.
- Issuer hoặc audience sai.
- Token type/profile sai.
- Thiếu jti/nonce bắt buộc.
- jti quá dài hoặc chứa dữ liệu bất thường.
- Claim thời gian sai kiểu hoặc nằm ngoài giới hạn.
- Duplicate JSON member names có thể làm parser diễn giải khác nhau.
- Token dùng kid lạ gây refresh JWKS quá mức.
- Nhiều jti ngẫu nhiên để làm đầy replay cache.
- Gửi cùng định danh với payload khác để thử chiếm namespace.

Token không vượt qua validation không được tạo principal hoặc thực hiện side effect. Hạn chế rate, kích thước và số lần refresh để ngăn DoS vào replay store và key endpoint.

## 16. Kiểm thử observability mà không làm lộ token

Khi replay bị từ chối, hệ thống cần đủ thông tin để vận hành và điều tra nhưng không ghi raw credential.

Nên có metric/log theo các trường đã được kiểm soát:

- Kết quả: accepted-first-use, replay-detected, expired, invalid-proof, store-unavailable.
- Issuer/profile/audience đã chuẩn hóa.
- Fingerprint của định danh replay thay vì raw token.
- Instance/region xử lý.
- Độ trễ replay-store lookup/atomic consume.
- Số lượng conflict trong test concurrency.
- Số side effect đã commit và số request deduplicated.
- Độ trễ replication hoặc propagation của trạng thái.

Không ghi raw JWT, Authorization header, refresh token, nonce bí mật hoặc payload nhạy cảm vào log. Test observability cũng cần xác minh redaction trong exception, tracing, dead-letter queue và dashboard.

## 17. Ma trận test tổng hợp

| Nhóm | Test tối thiểu | Invariant cần giữ |
| --- | --- | --- |
| Contract | Xác định đúng đối tượng one-time | Không áp dụng one-time nhầm cho access token reusable |
| First use/replay | Dùng lần đầu và phát lại | Một lần consume thành công |
| Concurrency | N request đồng thời | Tối đa một first-consume |
| Distributed | Nhiều instance/region | Trạng thái dùng được chia sẻ theo phạm vi contract |
| Time | exp, nbf, TTL, skew | Marker tồn tại hết cửa sổ chấp nhận |
| Failure | Crash/timeout/response lost | Không mở lại credential đã tiêu thụ |
| OAuth code | Redeem lại code | Code không thể đổi token lần hai |
| DPoP | Proof trùng, sai binding, nonce | Proof gắn đúng request và không replay |
| Refresh rotation | Reuse token cũ | Reuse được phát hiện theo family policy |
| Idempotency | Retry cùng key/payload | Side effect tối đa một lần |
| Availability | Replay store outage/partition | Hành vi fail-open/closed đúng policy |
| Input abuse | Token malformed, jti flood | Không bypass validation hoặc làm cạn tài nguyên |
| Observability | Log/metric/trace | Phát hiện được replay mà không lộ credential |

## 18. Tình huống tự kiểm tra

Một API phát hành capability JWT cho phép xác nhận một giao dịch duy nhất. Capability có issuer, audience, exp và jti. Hai worker ở hai region nhận cùng message gần như đồng thời. Cả hai đều verify chữ ký thành công. Replay store đang dùng replication eventual consistency.

**Câu hỏi 1:** Chữ ký hợp lệ có đủ để cả hai worker thực hiện giao dịch không?

**Trả lời:** Không. Chữ ký chỉ xác minh token được ký bằng khóa phù hợp. Hợp đồng capability yêu cầu consume-once nên cần trạng thái dùng chung và thao tác ghi nguyên tử.

**Câu hỏi 2:** Vì sao eventual consistency có thể làm test thất bại?

**Trả lời:** Hai region có thể cùng đọc trạng thái chưa dùng trước khi replication cập nhật. Cả hai có thể chấp nhận capability. Nếu contract yêu cầu one-time-use toàn cục, cần primitive nhất quán/điều phối phù hợp hoặc thay đổi ranh giới bảo đảm được công bố.

**Câu hỏi 3:** Nếu worker thứ nhất đã consume capability nhưng crash trước khi ghi kết quả nghiệp vụ thì có nên cho worker thứ hai dùng lại capability không?

**Trả lời:** Không tự động. Capability cũ đã được tiêu thụ. Hệ thống cần trạng thái operation/checkpoint để phục hồi an toàn, hoặc một cơ chế reservation/lease có semantics rõ ràng. Không xóa replay marker chỉ để retry.

**Câu hỏi 4:** Nếu client gửi lại cùng yêu cầu thanh toán với idempotency key cũ thì có phải replay cần từ chối không?

**Trả lời:** Không nhất thiết. Theo hợp đồng idempotency, server có thể trả kết quả đã lưu cho cùng key và cùng payload, miễn side effect không chạy lần hai. Đây là retry an toàn của cùng operation, khác với việc chấp nhận lại one-time capability.

## 19. Ghi nhớ

Kiểm thử chống replay phải bắt đầu từ contract. Access token thường reusable; one-time token, authorization code, nonce, proof và business operation có semantics khác nhau. jti không tự làm token one-time-use; trạng thái phải được ghi và consume nguyên tử.

Test cần bao gồm lần đầu/lần lặp, concurrency, nhiều instance/region, TTL/clock skew, crash giữa chừng, retry, replay-store outage, protocol-specific cases như authorization code/DPoP/refresh rotation và idempotency ở lớp nghiệp vụ.

Với credential dùng một lần, bảo đảm at-most-once phụ thuộc vào phạm vi nhất quán và điểm commit của trạng thái. Với business retry, hãy bảo đảm side effect tối đa một lần và trả lại kết quả theo idempotency contract. Không đánh đổi các bảo đảm này một cách âm thầm khi hạ tầng gặp lỗi.

**Một test replay tốt chứng minh invariant dưới cạnh tranh và lỗi phân tán, không chỉ chứng minh request thứ hai bị từ chối khi chạy tuần tự.**

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code và quy tắc token endpoint.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc authorization code với code verifier.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): jti và claims thời gian.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): tra cứu trạng thái token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained access token bằng chứng thư.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof JWT, nonce và ràng buộc access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token và phát hiện reuse.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa method và tính idempotent.
