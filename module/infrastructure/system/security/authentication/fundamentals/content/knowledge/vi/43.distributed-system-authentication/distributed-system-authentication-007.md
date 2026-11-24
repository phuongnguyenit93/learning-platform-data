# Partial failure

## 1. Partial failure là gì?

**Partial failure (lỗi từng phần)** xảy ra khi một phần của hệ thống phân tán không hoạt động đúng, trong khi các thành phần khác vẫn hoạt động. Một request đăng nhập hoặc kiểm tra quyền có thể đi qua browser, gateway, authentication service, Identity Provider (IdP), token service, session store, policy service và ứng dụng đích. Nếu chỉ một dependency timeout hoặc trả dữ liệu lỗi, toàn bộ luồng có thể thất bại dù các thành phần còn lại vẫn khỏe.

Ví dụ: người dùng đã có access token hợp lệ và gửi request tới Orders API. API có thể tự xác minh chữ ký JWT bằng public key đã cache, nhưng dịch vụ introspection hoặc policy engine đang mất kết nối. Request đọc một trang thông thường có thể vẫn được xử lý theo policy đã xác định; request chuyển tiền hoặc thay đổi quyền quản trị có thể phải từ chối vì không kiểm tra được trạng thái thu hồi hoặc policy mới nhất.

Partial failure khác với việc toàn hệ thống ngừng hoạt động. Một service có thể trả lỗi cho một nhóm request, một vùng mạng, một tenant hoặc một loại credential, trong khi các request khác vẫn thành công. Vì vậy, việc thiết kế authentication trong distributed system cần giả định dependency có thể chậm, mất kết nối, trả dữ liệu cũ hoặc chỉ phục hồi một phần.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, partial failure là vấn đề cốt lõi khi xác thực qua nhiều service, federation, token, session và authorization boundary. Thiết kế phải xác định rõ khi nào được tiếp tục với bằng chứng đã xác minh, khi nào cần từ chối an toàn và cách phục hồi mà không tạo thêm lỗ hổng hoặc gây retry storm.

## 2. Vì sao authentication dễ gặp partial failure?

Một luồng xác thực thường phụ thuộc nhiều thành phần có vòng đời và miền lỗi khác nhau:

| Thành phần | Dạng lỗi có thể gặp | Ảnh hưởng |
| --- | --- | --- |
| DNS/service discovery | Không phân giải được tên, trả endpoint cũ. | Không tìm được IdP hoặc service đích. |
| Network/TLS | Timeout, reset, certificate hết hạn hoặc trust chain lỗi. | Không thiết lập được kênh tin cậy. |
| Identity Provider | Mất kết nối, quá tải hoặc một vùng không khả dụng. | Không đăng nhập mới hoặc không hoàn tất federation. |
| Token endpoint | Timeout sau khi xử lý request, trả 5xx hoặc rate limit. | Không biết token đã được phát hành hay chưa. |
| JWKS endpoint | Không tải được key mới hoặc cache hết hạn. | Không xác minh được token có key ID chưa biết. |
| Introspection/revocation service | Không truy vấn được trạng thái opaque token. | Không xác định được token còn active hay đã revoke. |
| Session store | Mất kết nối, replication lag hoặc lỗi ghi. | Không tạo, đọc hoặc thu hồi session đúng cách. |
| Policy/authorization service | Timeout hoặc dữ liệu policy không đồng bộ. | Không đánh giá được quyền hiện tại. |
| MFA provider | Push/SMS/TOTP backend lỗi hoặc phản hồi chậm. | Không hoàn tất factor bổ sung. |
| Database/credential store | Lỗi đọc verifier, lock contention hoặc failover. | Không xác minh credential hoặc trạng thái account. |
| Message broker | Queue chậm, consumer dừng hoặc message lặp. | Tác vụ cấp/thu hồi quyền bị trễ. |
| Clock/NTP | Đồng hồ lệch giữa node hoặc vùng. | Token bị coi là chưa hiệu lực/hết hạn sai thời điểm. |

Một luồng có càng nhiều synchronous dependency thì càng dễ thất bại khi một dependency chậm. Chẳng hạn, nếu mọi API request đều gọi IdP để introspect token và gọi thêm policy service, hai dịch vụ này trở thành dependency trực tiếp trên đường request.

## 3. Phân biệt lỗi, timeout và kết quả không xác định

Không phải mọi lỗi đều có cùng ý nghĩa:

- **Definite rejection:** server trả kết quả rõ ràng rằng credential/token không hợp lệ hoặc policy từ chối.
- **Dependency unavailable:** không thể kết nối hoặc dependency trả lỗi tạm thời.
- **Timeout with unknown outcome:** caller không nhận được response; request có thể chưa tới server, đang xử lý hoặc đã hoàn tất nhưng response bị mất.
- **Stale response:** nhận được dữ liệu hợp lệ về định dạng nhưng không còn mới so với trạng thái thực tế.
- **Partial response:** một phần dữ liệu hoặc một số dependency có kết quả, phần còn lại lỗi.

Timeout không đồng nghĩa request chưa được thực hiện. Ví dụ, token endpoint có thể đã tiêu thụ authorization code và phát token, nhưng response bị mất trên đường về. Nếu client retry cùng code một cách mù quáng, authorization server có thể từ chối vì code đã dùng. Với lệnh revoke, timeout cũng không cho biết revoke đã hoàn tất hay chưa; cần kiểm tra trạng thái hoặc dùng operation ID có tính idempotent.

Hệ thống phải phân biệt lỗi xác thực thật với lỗi hạ tầng. Không ghi mọi timeout thành “password sai”, vì điều đó làm sai số liệu, gây khóa nhầm và che giấu sự cố dependency.

## 4. Nguyên tắc thiết kế khi có partial failure

Một kiến trúc authentication có khả năng chịu lỗi cần:

1. **Đặt timeout có chủ đích:** mỗi dependency và toàn bộ request có deadline rõ ràng.
2. **Giới hạn retry:** retry chỉ với lỗi tạm thời, có backoff và jitter; không retry vô hạn.
3. **Chặn retry amplification:** dùng circuit breaker, bulkhead và quota để tránh một dependency lỗi làm sập cả hệ thống.
4. **Định nghĩa fail policy theo hành động:** phân biệt đọc ít rủi ro với chuyển tiền, đổi credential hoặc thao tác quản trị.
5. **Dùng cache có giới hạn:** cache key, metadata và policy có TTL; xác định rõ tác động của dữ liệu cũ.
6. **Giữ bằng chứng đã xác minh:** không yêu cầu người dùng đăng nhập lại vô ích khi dependency chỉ tạm chậm và session/token hiện tại vẫn hợp lệ theo policy.
7. **Không hạ thấp assurance:** không bỏ MFA hoặc bỏ authorization chỉ để giữ availability.
8. **Thiết kế idempotency và reconciliation:** xử lý được request lặp và kết quả không xác định.
9. **Giám sát theo dependency và trust boundary:** phát hiện lỗi theo vùng, tenant, issuer, resource và loại credential.
10. **Có quy trình phục hồi:** khi dependency trở lại, đồng bộ trạng thái, xử lý event tồn đọng và kiểm tra quyền đã thay đổi.

Availability là mục tiêu quan trọng nhưng không thể đạt bằng cách chấp nhận mọi request khi không xác minh được danh tính hoặc quyền. Policy phải nêu rõ dữ liệu nào được cache, trong bao lâu và loại hành động nào được phép khi dependency không sẵn sàng.

## 5. Fail closed và fail open

Hai cách xử lý thường được nhắc đến:

- **Fail closed:** nếu không thể xác minh điều kiện bảo mật bắt buộc, từ chối request.
- **Fail open:** nếu dependency lỗi, vẫn cho phép request theo một quy tắc dự phòng.

Không nên áp dụng một lựa chọn duy nhất cho toàn hệ thống. Cần đánh giá mức độ nhạy cảm, khả năng thu hồi, thời gian cache, loại token và hậu quả khi chấp nhận nhầm.

| Tình huống | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Đăng nhập mới nhưng không xác minh được password/MFA | Fail closed. | Chưa có bằng chứng xác thực đủ tin cậy. |
| JWT hợp lệ, chữ ký xác minh được bằng key đã cache, IdP tạm mất | Có thể tiếp tục trong giới hạn token và policy. | Không cần gọi IdP cho mọi request nếu token đã được xác minh đầy đủ. |
| Opaque token cần introspection nhưng introspection không khả dụng | Thường fail closed; chỉ dùng cache response trong TTL/policy đã duyệt. | Không thể xác định trạng thái active/revoked mới nhất. |
| Policy service lỗi khi đọc dữ liệu ít nhạy cảm | Có thể dùng policy snapshot gần nhất nếu được phê duyệt và còn hạn. | Giữ availability với giới hạn rõ. |
| Policy service lỗi khi chuyển tiền hoặc đổi quyền admin | Fail closed. | Quyết định cần policy và trạng thái hiện hành. |
| Session store lỗi với session opaque | Fail closed hoặc dùng phương án dự phòng đã thiết kế. | Không thể xác minh session/revocation state. |
| MFA provider lỗi | Không tự bỏ MFA; dùng factor dự phòng được phê duyệt hoặc từ chối tạm thời. | Tránh downgrade authentication. |
| Audit sink lỗi | Có thể ghi durable local/outbox theo policy; không được làm mất sự kiện quan trọng. | Cần bảo toàn khả năng điều tra và truy vết. |

Fail open phải là một chế độ có chủ đích, giới hạn theo resource, action, thời gian và assurance. Không dùng thông điệp “dịch vụ xác thực đang lỗi” làm lý do tự động bỏ qua authentication hoặc authorization.

## 6. JWT validation khi IdP hoặc mạng bị gián đoạn

Với JWT access token, resource server có thể xác minh token cục bộ nếu đã có public key đáng tin và token còn hiệu lực. Điều này giảm phụ thuộc vào IdP trên từng request.

Các bước xác minh vẫn phải thực hiện:

- Chữ ký theo thuật toán được allowlist và key tin cậy.
- Issuer đúng cấu hình.
- Audience dành cho resource server hiện tại.
- Token type/profile đúng mục đích.
- Các claim thời gian exp, nbf và clock skew trong giới hạn.
- Scope/role/tenant và các claim bắt buộc theo policy.
- Sender constraint hoặc confirmation binding nếu token yêu cầu.

Nếu IdP tạm ngừng hoạt động nhưng JWKS key đã cache còn được tin cậy, token đã phát hành có thể tiếp tục được xác minh cho tới thời điểm hết hạn. Đây là một dạng resilience có chủ đích, nhưng có trade-off: token bị revoke hoặc account bị khóa có thể chưa bị phát hiện ngay nếu resource server không có kênh cập nhật trạng thái.

### 6.1. Cache JWKS an toàn

Resource server nên cache JWKS theo cấu hình issuer và TTL phù hợp. Khi gặp key ID chưa biết:

1. Thử refresh JWKS từ issuer đã cấu hình, không lấy key từ URL do token tự khai.
2. Gộp các request refresh đồng thời để tránh một đợt token lạ tạo ra hàng nghìn fetch.
3. Giới hạn số lần refresh và timeout.
4. Nếu key vẫn không có hoặc endpoint không truy cập được, từ chối token đó.
5. Không chấp nhận chữ ký không xác minh được chỉ vì JWKS endpoint đang lỗi.

Khi JWKS endpoint lỗi, key cũ đã cache có thể được dùng trong thời gian stale-if-error đã định nghĩa nếu key đó vẫn nằm trong trust policy. Không nên dùng key cũ vô thời hạn; cần giới hạn stale window, cảnh báo và quy trình xử lý key compromise.

### 6.2. Key rotation và overlap

Issuer nên công bố public key mới trước khi bắt đầu ký token bằng key đó, giữ key cũ trong JWKS đủ lâu để resource server cập nhật và xác minh token cũ trong thời hạn. Khi rotation, cần có khoảng overlap hợp lý và quy trình khẩn cấp để loại bỏ key bị compromise.

Nếu resource server chưa tải được key mới và nhận token có key ID mới, nó phải từ chối token đó. Việc tiếp tục dùng key cũ để xác minh một token không có chữ ký tương ứng là không an toàn.

## 7. Opaque token và introspection failure

Opaque access token không mang đủ thông tin để resource server tự xác minh trạng thái chỉ bằng chữ ký. Resource server thường gọi introspection endpoint hoặc một dịch vụ kiểm tra token.

Nếu introspection timeout:

- Không coi timeout là kết quả active=true.
- Có thể dùng kết quả introspection đã cache trong TTL ngắn nếu policy cho phép và mức rủi ro phù hợp.
- Với quyền cao hoặc dữ liệu nhạy cảm, yêu cầu introspection thành công hoặc từ chối.
- Theo dõi tuổi cache, issuer, audience, token reference và thời điểm kiểm tra gần nhất.
- Không cache phản hồi active quá lâu vì token có thể đã bị revoke sau đó.

Cache trạng thái inactive cũng cần TTL và invalidation hợp lý; không giữ kết quả inactive vô thời hạn nếu token có thể được cấp lại với cùng reference theo một hệ thống không bảo đảm uniqueness.

## 8. Session store và lỗi tạo/thu hồi session

Với session opaque lưu phía server, mọi request được bảo vệ thường cần kiểm tra session record hoặc một cache có cơ chế invalidation.

Các trường hợp:

- **Session store read failure:** không thể xác nhận session còn active. Không tự coi cookie tồn tại là bằng chứng đủ.
- **Session creation write failure:** không phát cookie báo đăng nhập thành công nếu session chưa được lưu bền vững.
- **Session revoke timeout:** kết quả chưa xác định; cần operation ID và kiểm tra lại trạng thái.
- **Replication lag:** một node đã revoke nhưng node khác vẫn đọc bản ghi cũ.

Để giảm lỗi:

- Dùng session ID ngẫu nhiên, không suy ra từ user ID.
- Ghi session bền vững trước khi phát cookie.
- Xoay session ID sau authentication và step-up.
- Có session version hoặc revocation epoch để thu hồi theo principal.
- Dùng cache invalidation/event có bảo đảm và TTL giới hạn.
- Với sự cố revoke diện rộng, có thể tăng version hoặc disable principal ở nguồn có thẩm quyền.

Nếu session store lỗi, không nên chuyển tự động sang chế độ coi mọi cookie là hợp lệ. Có thể giữ một luồng degraded riêng chỉ cho nội dung công khai hoặc tài nguyên ít rủi ro, còn hành động được bảo vệ phải tuân theo policy rõ.

## 9. Token endpoint timeout và kết quả không xác định

Một request tới token endpoint có thể timeout ở nhiều thời điểm:

1. Request chưa tới authorization server.
2. Server nhận request nhưng chưa xử lý.
3. Server đã tiêu thụ authorization code và phát token nhưng response bị mất.
4. Server trả response nhưng client không nhận được do network reset.

Client không thể suy ra trường hợp nào chỉ từ timeout. Với Authorization Code Flow, code thường dùng một lần; retry cùng code có thể bị từ chối hoặc kích hoạt kiểm soát reuse.

Hướng xử lý:

- Không log authorization code, access token, refresh token hoặc client secret.
- Không retry vô hạn hoặc song song cùng một code.
- Nếu kết quả exchange không xác định, xử lý theo protocol/provider: bắt đầu authorization flow mới khi cần, thay vì giả định code vẫn còn dùng được.
- Với refresh token rotation, nếu response bị mất sau khi token cũ đã bị tiêu thụ, dùng recovery/retry semantics do provider hỗ trợ; không tự gửi refresh token cũ lặp lại tùy tiện.
- Theo dõi correlation ID và token request ID không chứa secret.

Các API nghiệp vụ phía sau token issuance cũng cần idempotency. Không dùng cùng một request retry để tạo nhiều giao dịch chỉ vì client không nhận được response đầu tiên.

## 10. Timeout, deadline và retry

Mỗi request nên có deadline tổng thể và timeout riêng cho dependency. Timeout của dependency phải ngắn hơn deadline còn lại của request để service có thời gian trả kết quả có kiểm soát.

Ví dụ khái niệm:

~~~text
Request deadline: 2.0 giây

JWKS cache lookup: nội bộ, không chặn nếu cache hit
JWKS refresh: tối đa 300 ms
Policy service: tối đa 400 ms
Session store: tối đa 250 ms
Response reserve: ít nhất 200 ms
~~~

Đây chỉ là ví dụ minh họa; con số thật phụ thuộc latency budget, vùng triển khai và SLO. Không cộng các timeout độc lập vượt quá deadline request.

Retry chỉ phù hợp khi:

- Lỗi có khả năng tạm thời, như một số lỗi network hoặc 503.
- Request có thể retry an toàn hoặc có idempotency key.
- Còn thời gian trong deadline.
- Retry không vượt quota và không làm dependency quá tải.

Không retry các lỗi xác thực xác định như invalid password, invalid signature, wrong audience hoặc expired token. Retry có thể thực hiện với exponential backoff và jitter, nhưng phải giới hạn số lần và tổng thời gian.

### 10.1. Tránh retry storm

Khi dependency chậm, nhiều caller có thể đồng loạt retry, làm tải tăng và khiến dependency càng khó phục hồi. Đây là retry storm.

Biện pháp:

- Exponential backoff với jitter.
- Giới hạn retry count và retry budget.
- Circuit breaker khi tỷ lệ lỗi vượt ngưỡng.
- Bulkhead để một dependency không chiếm hết thread/connection.
- Queue hoặc shed load cho công việc không khẩn cấp.
- Cache hợp lệ cho dữ liệu public key/policy có thể cache.
- Tránh nhiều tầng retry độc lập; gateway, SDK và service không nên mỗi tầng tự retry nhiều lần.

## 11. Circuit breaker và bulkhead

**Circuit breaker** tạm ngừng gọi dependency khi nó liên tục lỗi, để hệ thống không tiếp tục tạo tải vào một dịch vụ đang suy giảm. Các trạng thái thường gồm:

- **Closed:** request được gửi bình thường; thống kê lỗi.
- **Open:** tạm từ chối hoặc chuyển sang fallback khi lỗi vượt ngưỡng.
- **Half-open:** cho một số request thử để xác định dependency đã phục hồi chưa.

**Bulkhead** cô lập tài nguyên cho từng dependency hoặc nhóm request. Ví dụ, pool kết nối tới IdP không được phép chiếm hết connection của Orders API.

Fallback của circuit breaker vẫn phải tuân thủ authentication policy. Nếu introspection circuit đang open, không được mặc định mọi opaque token là active. Có thể dùng cached result trong giới hạn đã duyệt hoặc từ chối request cần introspection.

## 12. MFA và partial failure

MFA flow có nhiều điểm có thể lỗi: tạo challenge, gửi push/SMS, nhận callback, kiểm tra OTP, ghi trạng thái factor và hoàn tất session.

Các nguyên tắc:

- Challenge phải có ID ngẫu nhiên, expiry, purpose và binding với login transaction.
- Không tạo challenge vô hạn khi provider chậm.
- Không coi timeout của push provider là user đã từ chối hoặc đã chấp thuận.
- Không bỏ qua factor bắt buộc khi MFA provider không khả dụng.
- Dùng factor dự phòng đã được đăng ký và policy cho phép; không hạ assurance tùy tiện.
- Tiêu thụ OTP/challenge thành công một lần bằng thao tác nguyên tử.
- Ghi trạng thái pending/verified/expired rõ ràng để xử lý callback trễ hoặc trùng.

Nếu push callback đến sau khi login transaction đã hết hạn, server phải từ chối hoàn tất session từ transaction đó. Không dùng callback cũ để mở một login flow mới.

## 13. Policy service không khả dụng

Authorization service có thể phụ thuộc policy store, relationship graph hoặc dữ liệu entitlement. Khi dependency lỗi, cần phân loại policy:

- **Static, low-risk policy:** có thể cache snapshot đã ký hoặc versioned trong thời gian giới hạn.
- **Dynamic resource policy:** cần kiểm tra ownership, trạng thái record hoặc quan hệ hiện thời; cache lâu có thể tạo quyền sai.
- **High-impact policy:** chuyển tiền, xóa dữ liệu, thay đổi quyền, export dữ liệu nhạy cảm; thường cần dữ liệu hiện hành và fail closed khi không thể đánh giá.

Một policy cache nên có version, source, timestamp, expiry và scope. Không cache một kết quả allow chung rồi áp dụng cho mọi tenant/resource. Khi policy version tăng hoặc quyền bị revoke, hệ thống cần invalidation hoặc giới hạn thời gian stale.

Nếu policy service trả partial response, không được diễn giải phần thiếu thành allow. Ví dụ, nếu không lấy được SoD constraint hoặc tenant ownership, cần từ chối hoặc chuyển review tùy hành động.

## 14. Clock skew và token thời gian

JWT, TOTP, certificate và session timeout phụ thuộc đồng hồ. Nếu node lệch thời gian:

- Token hợp lệ có thể bị từ chối vì exp hoặc nbf.
- Token đã hết hạn có thể được chấp nhận quá lâu.
- TOTP có thể không khớp time step.
- Certificate có thể bị coi là chưa hiệu lực hoặc hết hạn.
- Audit timeline giữa service có thể không nhất quán.

Biện pháp:

- Đồng bộ đồng hồ qua NTP/time service tin cậy.
- Theo dõi offset và cảnh báo khi vượt ngưỡng.
- Dùng clock source nhất quán và UTC trong log.
- Chỉ cho phép clock skew nhỏ, được policy định nghĩa.
- Không tăng skew quá rộng chỉ để che giấu lỗi đồng hồ.
- Trong TOTP, giới hạn time window và chống replay kể cả khi cho phép lệch một bước.

Clock skew tolerance không được dùng để kéo dài token vô thời hạn. Cần tính cả sai lệch giữa issuer, gateway và resource server.

## 15. Thu hồi credential khi event propagation bị trễ

Trong hệ thống phân tán, sự kiện revoke có thể được phát qua message bus tới nhiều service. Một số node nhận event chậm hoặc mất kết nối, khiến credential đã revoke vẫn được chấp nhận tạm thời.

Các biện pháp:

- Dùng event có ID duy nhất, version/sequence và timestamp.
- Consumer xử lý idempotent và lưu offset/checkpoint bền vững.
- Có cơ chế reconcile định kỳ với nguồn trạng thái có thẩm quyền.
- Dùng TTL ngắn cho cache authorization và session state.
- Với principal bị khóa khẩn cấp, có đường truyền deny/kill switch ưu tiên.
- Không coi việc publish event thành công là bằng chứng mọi resource server đã áp dụng revoke.

Một hệ thống cần biết revoke propagation lag tối đa là bao lâu. Với thao tác nhạy cảm, nếu không thể đảm bảo trạng thái mới nhất, có thể cần introspection hoặc kiểm tra version trực tiếp.

## 16. Degraded mode có kiểm soát

Degraded mode là chế độ hoạt động giới hạn khi một số dependency không sẵn sàng. Chế độ này cần được thiết kế trước, không tạo ra ngẫu hứng trong lúc incident.

Ví dụ:

| Chức năng | Khi dependency lỗi | Degraded behavior có thể chấp nhận |
| --- | --- | --- |
| Nội dung công khai | Session store lỗi | Tiếp tục phục vụ nội dung không cần authentication. |
| Đọc profile ít nhạy cảm | Policy service lỗi | Có thể dùng policy snapshot mới, đúng tenant và còn TTL nếu đã phê duyệt. |
| Đăng nhập mới | IdP/credential store lỗi | Từ chối tạm thời và hiển thị lỗi dịch vụ; không bỏ qua xác thực. |
| Thanh toán | Policy/introspection lỗi | Từ chối hoặc giữ pending; không tự động thực hiện. |
| Đăng ký factor mới | Session/re-auth service lỗi | Không cho thay đổi factor khi không xác minh được session/re-auth. |
| Thu hồi session | Session store lỗi | Ghi durable revoke request và kích hoạt đường khẩn cấp; không tuyên bố hoàn tất trước khi xác nhận. |
| Audit | Log collector lỗi | Ghi outbox/durable buffer theo policy, giới hạn dung lượng và cảnh báo. |

Mỗi degraded mode cần xác định:

- Điều kiện kích hoạt và dependency liên quan.
- Hành động nào được phép/không được phép.
- Thời hạn tối đa và cách tự thoát chế độ.
- Nguồn dữ liệu cache được tin cậy và TTL.
- Ai có quyền kích hoạt thủ công.
- Cách audit, thông báo và rollback.

## 17. Observability và chẩn đoán

Để phát hiện partial failure, không chỉ theo dõi tỷ lệ login thành công. Cần đo theo từng dependency và theo loại flow:

- Latency p50/p95/p99 của IdP, JWKS, introspection, session store và policy service.
- Tỷ lệ timeout, 5xx, connection reset, TLS error và DNS error.
- Tỷ lệ token invalid theo nguyên nhân: signature, issuer, audience, expiry, unknown key.
- JWKS cache hit/miss, refresh failure và tuổi key cache.
- Session create/read/revoke error và replication lag.
- MFA challenge pending/expired/callback duplicate.
- Token refresh failure và authorization code exchange unknown outcome.
- Policy cache age/version mismatch và decision failure.
- Revoke event lag, consumer backlog và reconciliation mismatch.
- Retry count, circuit breaker state, bulkhead saturation và request shed.

Log cần có request ID, correlation ID, issuer, resource, tenant và dependency name ở mức được phép. Không ghi password, OTP, authorization code, bearer token, refresh token, session cookie hoặc private key.

Thông báo lỗi cho người dùng nên phân biệt “thông tin xác thực không hợp lệ” với “dịch vụ đăng nhập tạm thời không khả dụng” ở mức không tiết lộ chi tiết nhạy cảm. Việc phân biệt giúp người dùng không đổi password vô ích và giúp đội vận hành nhận diện dependency failure.

## 18. Ví dụ pseudocode: xác minh token với JWKS cache

~~~ts
async function verifyAccessTokenWithCachedKeys(token, issuerConfig) {
  const header = readAndValidateJwtHeader(token);
  if (!issuerConfig.allowedAlgorithms.includes(header.alg)) {
    throw new UnauthorizedError();
  }

  let key = await jwksCache.find(issuerConfig.issuer, header.kid);

  if (!key) {
    try {
      await jwksCache.refreshSingleFlight(issuerConfig.issuer, {
        timeoutMs: 300,
        maxAttempts: 1
      });
      key = await jwksCache.find(issuerConfig.issuer, header.kid);
    } catch (error) {
      metrics.increment("jwks.refresh.failure");
    }
  }

  if (!key) {
    throw new UnauthorizedError();
  }

  const claims = verifyJwtSignatureAndClaims(token, key, {
    issuer: issuerConfig.issuer,
    audience: "orders-api",
    allowedAlgorithms: issuerConfig.allowedAlgorithms,
    clockSkewSeconds: 30
  });

  return claims;
}
~~~

Đây là pseudocode minh họa. Không tự đọc URL JWKS từ JWT header; issuer và endpoint phải đến từ cấu hình tin cậy. Hàm refresh cần chống nhiều request cùng refresh. Nếu key ID vẫn chưa biết sau refresh, từ chối token. Việc dùng cached key khi JWKS lỗi chỉ hợp lệ trong stale window đã được policy cho phép và không có tín hiệu key bị compromise.

## 19. Ví dụ: IdP gián đoạn trong giờ cao điểm

Một hệ thống thương mại có Web Portal, Orders API và Payments API. IdP ở một vùng bị lỗi mạng trong 10 phút.

**Tình huống:**

- Người dùng mới không thể hoàn tất login hoặc MFA.
- Một số JWT access token đã phát hành vẫn còn hiệu lực và có key xác minh trong JWKS cache.
- Một số API dùng opaque token cần introspection.
- Policy service vẫn hoạt động, nhưng một số cache policy đã cũ.

**Cách xử lý:**

1. Gateway phát hiện lỗi IdP và mở circuit breaker cho các request gọi token endpoint.
2. Login mới và MFA mới được thông báo tạm thời không khả dụng; không bỏ qua factor.
3. Orders API tiếp tục xác minh JWT có issuer, audience, chữ ký và expiry hợp lệ bằng key đã cache, trong stale window được phê duyệt.
4. Payments API từ chối opaque token nếu introspection không có kết quả hợp lệ hoặc cache active đã quá TTL.
5. Giao dịch có rủi ro cao cần policy hiện hành; nếu policy cache hết hạn, request bị từ chối hoặc chuyển pending.
6. Các request không khẩn cấp được giới hạn tải; retry dùng backoff và jitter.
7. Khi IdP phục hồi, circuit breaker chuyển half-open rồi closed sau các probe thành công.
8. Hệ thống refresh JWKS, kiểm tra token refresh và xử lý event revoke tồn đọng.
9. Reconcile session/grant và kiểm tra các request pending có kết quả không xác định.
10. Đội vận hành đối chiếu SLO, revoke lag, token issuance và số request bị từ chối trước khi đóng incident.

Degraded mode này giữ một số thao tác ít rủi ro hoạt động dựa trên bằng chứng còn hợp lệ, trong khi các thao tác cần trạng thái mới nhất vẫn được bảo vệ.

## 20. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Fail open cho mọi request khi IdP lỗi | Attacker có thể truy cập mà không có bằng chứng mới. | Phân loại theo resource/action và fail closed cho điều kiện bắt buộc. |
| Gọi introspection trên mọi request không timeout | Dependency chậm làm cạn thread/connection. | Deadline, cache có TTL, circuit breaker và bulkhead. |
| Dùng JWKS cache vô thời hạn | Key bị revoke/compromise vẫn được tin. | TTL, stale window, rotation và emergency key removal. |
| Chấp nhận token khi key ID không tìm thấy | Bỏ qua xác minh chữ ký. | Refresh JWKS có giới hạn rồi từ chối nếu vẫn không có key. |
| Retry token exchange vô hạn | Retry storm hoặc authorization code reuse. | Deadline, retry budget và xử lý unknown outcome theo protocol. |
| Phát cookie trước khi session được lưu | Browser có session ID không tồn tại hoặc trạng thái không nhất quán. | Ghi session bền vững trước khi phát cookie. |
| Coi timeout revoke là đã hoàn tất | Session/token có thể vẫn active. | Operation ID, kiểm tra trạng thái và reconciliation. |
| Cache allow decision quá lâu | Quyền đã revoke vẫn được dùng. | Version, TTL, invalidation và policy theo rủi ro. |
| Bỏ MFA khi provider lỗi | Downgrade làm giảm assurance. | Factor dự phòng được phê duyệt hoặc từ chối tạm thời. |
| Retry ở nhiều tầng cùng lúc | Tải nhân lên khi dependency lỗi. | Một retry owner, retry budget, jitter và circuit breaker. |
| Bỏ qua clock skew | Token/TOTP bị chấp nhận hoặc từ chối sai. | NTP, monitoring và skew tolerance nhỏ. |
| Coi publish revoke event là đã revoke toàn hệ thống | Consumer chậm vẫn chấp nhận credential cũ. | Theo dõi lag, ack, version và reconcile. |
| Gộp timeout thành invalid credential | Người dùng bị khóa hoặc đổi password vô ích. | Phân biệt auth rejection với dependency failure. |
| Không có degraded mode định nghĩa trước | Quyết định ứng phó tùy tiện trong incident. | Runbook theo action, TTL, owner và điều kiện rollback. |

## 21. Checklist thiết kế authentication chịu partial failure

Trước khi đưa hệ thống phân tán vào production, hãy kiểm tra:

1. Đã lập danh sách dependency của login, token, session, MFA, federation và authorization chưa?
2. Mỗi dependency có timeout và deadline tổng thể phù hợp không?
3. Có phân biệt invalid credential, dependency unavailable, timeout unknown outcome và stale response không?
4. Fail closed/open được định nghĩa riêng cho từng action và resource chưa?
5. JWT validation có thể chạy cục bộ với key cache đáng tin khi IdP lỗi không?
6. JWKS refresh có allowlist issuer, timeout, single-flight, stale window và xử lý unknown key an toàn không?
7. Opaque token introspection có TTL cache, timeout và policy khi unavailable không?
8. Session store có ghi bền vững trước khi phát cookie và có cơ chế revoke/version không?
9. Token endpoint/refresh flow có xử lý timeout và kết quả không xác định theo protocol không?
10. Retry có giới hạn, backoff, jitter, idempotency và retry budget không?
11. Circuit breaker và bulkhead có bảo vệ dependency và thread/connection pool không?
12. MFA provider lỗi có giữ nguyên assurance, không downgrade tùy tiện không?
13. Policy cache có version, timestamp, TTL và giới hạn theo tenant/resource/action không?
14. Clock/NTP, token expiry, TOTP và certificate validity có được giám sát không?
15. Revoke event có ID/version, consumer idempotent, theo dõi lag và reconciliation không?
16. Degraded mode có scope, TTL, owner, audit và rollback rõ ràng không?
17. Log/trace có đủ correlation nhưng không chứa password, token, cookie hoặc secret không?
18. Có kiểm thử IdP outage, JWKS rotation, unknown key, introspection timeout, session store failure, delayed revoke, clock skew, duplicate callback và retry storm không?

**Kết luận:** Partial failure là trạng thái bình thường cần dự liệu trong authentication phân tán: IdP, JWKS, introspection, session store, MFA và policy service có thể lỗi độc lập hoặc trả kết quả chậm/cũ. Hệ thống cần timeout, retry có giới hạn, cache có TTL, circuit breaker, idempotency và degraded mode theo rủi ro. JWT đã xác minh bằng key cache có thể tiếp tục hoạt động trong giới hạn; opaque token hoặc hành động nhạy cảm cần trạng thái mới nhất có thể phải từ chối khi dependency không sẵn sàng. Không dùng fail open để bỏ qua authentication hoặc authorization, và chỉ tuyên bố revoke hoàn tất sau khi đã xác nhận trạng thái thực tế.
