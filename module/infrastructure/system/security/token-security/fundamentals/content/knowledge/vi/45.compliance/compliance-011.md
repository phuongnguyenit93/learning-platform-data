# Không lưu token lâu hơn nhu cầu: áp dụng data minimization và storage limitation

## 1. Bối cảnh và mục tiêu

Token là thông tin xác thực mang quyền truy cập. Một access token có thể cho phép gọi API; refresh token có thể cấp access token mới trong thời gian dài; ID token mang thông tin xác thực người dùng cho OIDC. Việc lưu token quá lâu làm tăng thời gian và phạm vi mà token bị đánh cắp có thể bị khai thác. Việc giữ metadata không cần thiết cũng làm tăng rủi ro lộ thông tin về người dùng, client, tenant, phạm vi quyền và lịch sử truy cập.

Nguyên tắc **không lưu token lâu hơn nhu cầu** kết hợp hai kiểm soát:

- **Data minimization:** chỉ thu thập và lưu dữ liệu cần thiết cho mục đích đã xác định.
- **Storage limitation:** chỉ giữ dữ liệu trong khoảng thời gian cần thiết cho mục đích đó, sau đó xóa, ẩn danh hoặc chuyển sang trạng thái lưu trữ được kiểm soát nếu có căn cứ hợp lệ.

Trong nền tảng **Security Token Security Fundamentals**, nguyên tắc này áp dụng cho JWT, opaque token, access token, refresh token, ID token, token introspection, session, cache, log, backup và dữ liệu audit. Token hết hạn không tự động có nghĩa mọi bản sao của nó đã biến mất; token có thể còn trong log, trace, cache, bản sao database, backup hoặc thiết bị client.

Sau bài này, người học có thể:

- Xác định dữ liệu token nào cần thiết ở authorization server, resource server và OAuth client.
- Phân biệt thời hạn hiệu lực của token với thời hạn lưu trữ dữ liệu token.
- Xây dựng retention schedule theo mục đích, loại token và rủi ro.
- Thiết kế TTL, revocation, cleanup và xóa dữ liệu trên các hệ thống liên quan.
- Giảm token xuất hiện trong log, trace, metric, cache, analytics và backup.
- Chứng minh việc xóa/giữ dữ liệu bằng audit, kiểm thử và kiểm soát ngoại lệ.

## 2. Token, metadata và dữ liệu liên quan

Một hệ thống xác thực không chỉ lưu chuỗi token. Nó còn có thể lưu trạng thái phát hành, fingerprint, grant, session, consent, cache entry, kết quả introspection, dấu vết thu hồi và sự kiện bảo mật. Mỗi loại dữ liệu có mục đích và thời hạn khác nhau.

| Dữ liệu | Mục đích thường gặp | Rủi ro khi lưu quá lâu |
| --- | --- | --- |
| Access token | Gọi resource server trong thời gian ngắn. | Token bị lộ vẫn có thể bị replay trong thời gian còn hiệu lực; bản sao trong log có thể bị dùng sai mục đích. |
| Refresh token | Xin access token mới khi token hiện tại hết hạn. | Có thể duy trì quyền truy cập lâu dài nếu bị đánh cắp. |
| ID token | Truyền kết quả xác thực người dùng tới OIDC client. | Có thể lộ claims định danh và bị dùng sai mục đích nếu coi nhầm là access token. |
| Opaque token record | Tra cứu trạng thái, expiry, client, grant và revocation. | Metadata có thể liên kết hành vi và danh tính; record cũ làm tăng chi phí và bề mặt lộ dữ liệu. |
| JWT claims/logged payload | Điều tra lỗi hoặc thống kê. | Có thể chứa subject, email, tenant, scope và dữ liệu cá nhân; raw JWT là bearer credential nếu là access token. |
| Token fingerprint/hash | Tra cứu token hoặc phát hiện reuse. | Vẫn có thể liên kết với token/user và không mặc nhiên là dữ liệu vô danh. |
| Session/grant metadata | Duy trì đăng nhập, consent và quan hệ client-user. | Có thể giữ quyền hoặc liên kết định danh sau khi mục đích đã kết thúc. |
| Introspection/cache entry | Giảm số lần gọi authorization server. | Metadata active cũ có thể trì hoãn việc nhận biết token đã bị thu hồi. |
| Audit/security event | Điều tra, chứng minh thao tác và phát hiện lạm dụng. | Giữ quá chi tiết hoặc quá lâu có thể tạo kho dữ liệu nhạy cảm thứ hai. |

Token không phải lúc nào cũng là dữ liệu cá nhân khi đứng riêng. Tuy nhiên, token và metadata có thể trở thành dữ liệu định danh hoặc dữ liệu liên kết khi gắn với subject, client, session, tenant, địa chỉ IP hay hành vi truy cập. Phân loại theo khả năng liên kết và mục đích sử dụng thực tế.

## 3. Phân biệt token expiry và data retention

`exp` trong JWT hoặc expiry được lưu ở authorization server xác định thời điểm token không còn được chấp nhận theo policy. **Retention period** xác định dữ liệu liên quan còn được lưu trong hệ thống bao lâu. Hai mốc này có liên hệ nhưng không giống nhau.

Ví dụ:

1. Access token hết hạn sau 10 phút.
2. Resource server vẫn giữ cache introspection trong 5 phút tiếp theo.
3. Reverse proxy đã ghi bearer token vào access log trong 30 ngày.
4. Backup database có token metadata được giữ 90 ngày.

Token có thể đã hết hiệu lực ở bước 1, nhưng dữ liệu vẫn tồn tại ở bước 2–4. Nếu log chứa raw bearer token, việc token hết hạn không xóa được nguy cơ lộ claims hoặc vi phạm quy định lưu trữ; nếu token vẫn còn hiệu lực do clock skew hoặc policy khác, rủi ro còn nghiêm trọng hơn.

Phân biệt bốn mốc:

- **Validity:** token được chấp nhận tới khi nào.
- **Operational retention:** dữ liệu cần cho xác thực, refresh, revocation, cache và hỗ trợ vận hành.
- **Security/audit retention:** dữ liệu tối thiểu cần để điều tra, phát hiện replay hoặc chứng minh thao tác.
- **Backup retention:** thời gian bản sao được giữ theo chính sách khôi phục và yêu cầu lưu trữ.

Không kéo dài `exp` chỉ vì muốn giữ log lâu hơn. Cũng không giữ raw token trong log chỉ vì audit cần lưu sự kiện. Hãy giữ dữ liệu phù hợp với mục đích riêng của từng lớp.

## 4. Xác định mục đích và căn cứ lưu trữ

Trước khi chọn TTL hoặc retention period, chủ sở hữu hệ thống cần trả lời:

1. Dữ liệu này phục vụ chức năng nào: xác thực request, refresh token, thu hồi, phát hiện replay, xử lý sự cố hay đáp ứng yêu cầu lưu trữ?
2. Thành phần nào thực sự cần dữ liệu: authorization server, resource server, BFF, mobile app, logging platform hay security operations?
3. Có thể đạt mục đích bằng dữ liệu ít nhạy cảm hơn không, ví dụ token ID nội bộ thay vì raw token?
4. Khi nào mục đích kết thúc: token hết hạn, grant bị revoke, session logout, user offboard hay sự kiện điều tra hoàn tất?
5. Có yêu cầu pháp lý, hợp đồng, điều tra hoặc legal hold hợp lệ nào cần giữ một phần dữ liệu không?
6. Ai phê duyệt thời hạn và ai chịu trách nhiệm xóa dữ liệu khi hết hạn?

Các nguyên tắc data minimization và storage limitation được nêu trong nhiều khung bảo vệ dữ liệu, ví dụ GDPR Article 5(1)(c) và 5(1)(e). Nghĩa vụ cụ thể phụ thuộc phạm vi áp dụng, ngành, quốc gia, hợp đồng và mục đích xử lý. Tổ chức cần ánh xạ yêu cầu pháp lý áp dụng vào retention schedule được phê duyệt; không suy ra một thời hạn chung cho mọi loại token.

## 5. Xây dựng retention schedule

Retention schedule là bảng quy định loại dữ liệu, mục đích, thời hạn, điều kiện bắt đầu tính và hành động khi hết hạn. Không nên để mỗi service tự chọn TTL mà không có quy ước chung.

Ví dụ khung tham khảo, các thời hạn cụ thể phải được điều chỉnh theo threat model và yêu cầu áp dụng:

| Loại dữ liệu | Thời hạn vận hành tham khảo | Hành động khi hết hạn/mục đích kết thúc |
| --- | --- | --- |
| Access token ở client memory | Chỉ trong thời gian cần gọi API hoặc tới `exp`. | Bỏ tham chiếu và không ghi ra storage/log. |
| JWT access token phía resource server | Thường không cần lưu raw token sau khi request kết thúc. | Xóa khỏi memory/request context; chỉ giữ metric tổng hợp. |
| Opaque access token state | Tới expiry cộng cửa sổ ngắn cần cho cleanup, introspection consistency hoặc audit tối thiểu. | Đánh dấu expired, sau đó xóa record theo policy. |
| Refresh token đang active | Tới expiry, revoke hoặc kết thúc grant/family. | Revoke tại AS và xóa credential phía client theo quy trình. |
| Refresh token đã consumed | Giữ fingerprint/status đủ lâu cho reuse detection và điều tra. | Xóa hoặc giảm định danh sau khi hết cửa sổ cần thiết. |
| ID token | Trong thời gian cần hoàn tất đăng nhập/session bootstrap theo kiến trúc. | Không dùng làm credential API; bỏ khỏi storage không cần thiết. |
| Introspection cache | TTL ngắn, không vượt giới hạn revocation policy và expiry của token. | Evict; không dùng kết quả active đã stale. |
| Token trong log/trace | Mặc định không ghi raw token. | Redact tại nguồn; nếu đã lỡ ghi, xử lý theo incident và retention của log. |
| Security audit event | Theo mục đích điều tra, kiểm toán và yêu cầu pháp lý. | Giữ trường tối thiểu; xóa/ẩn danh khi hết retention. |
| Backup metadata | Theo RPO/RTO, chu kỳ backup và yêu cầu lưu trữ. | Xóa theo retention lock; bảo đảm restore không hồi sinh token đã revoke. |

Bảng này là điểm khởi đầu, không phải cấu hình mặc định cho mọi hệ thống. Một hệ thống có yêu cầu phát hiện refresh token reuse có thể cần giữ fingerprint của token consumed lâu hơn thời hạn access token. Ngược lại, không có lý do để giữ raw bearer token trong log trong suốt thời hạn audit.

### 5.1. Xác định thời điểm bắt đầu

Retention phải có mốc bắt đầu rõ ràng. Tùy dữ liệu, mốc có thể là:

- `issued_at`: token được phát hành.
- `expires_at`: token hết hiệu lực.
- `revoked_at`: grant/family bị thu hồi.
- `last_used_at`: lần sử dụng cuối cùng.
- `session_ended_at`: session kết thúc.
- `incident_closed_at`: sự cố/điều tra được đóng.
- `backup_created_at`: bản backup được tạo.

Không dùng `created_at` cho mọi loại dữ liệu nếu mục đích yêu cầu tính từ sự kiện khác. Ví dụ, thời hạn lưu audit phục vụ điều tra có thể bắt đầu khi sự kiện xảy ra hoặc khi case đóng theo chính sách, còn thời hạn cache phải gắn với expiry/revocation.

### 5.2. Absolute lifetime và idle lifetime

Refresh token nên có giới hạn absolute lifetime và idle lifetime nếu policy yêu cầu. Rotation không được vô tình kéo dài family vô hạn chỉ vì token được dùng thường xuyên. Mỗi lần phát hành token kế tiếp phải kế thừa giới hạn tối đa của grant/family và không vượt quyền ban đầu.

## 6. Chính sách theo từng loại token

### 6.1. Access token

Access token nên có thời hạn phù hợp với độ nhạy của API, khả năng thu hồi và trải nghiệm client. Với JWT, resource server thường xác minh chữ ký và claims; không cần lưu raw JWT sau khi request xử lý xong. Với opaque token, authorization server cần trạng thái để introspection, nhưng record có thể được dọn sau expiry và cửa sổ vận hành cần thiết.

Các kiểm soát:

- Giữ access token trong memory trong thời gian ngắn nhất có thể.
- Không lưu trong URL, query string, browser history hoặc log.
- Không ghi token vào database nghiệp vụ chỉ để tiện debug.
- Dùng scope và audience hẹp để giới hạn hậu quả khi token bị lộ.
- Chọn expiry dựa trên latency, khả năng refresh, revocation và mức độ nhạy cảm.
- Khi token bị revoke, cập nhật introspection/cache/denylist theo thời hạn phát hiện đã cam kết.

### 6.2. Refresh token

Refresh token thường là credential dài hạn hơn access token và cần được bảo vệ nghiêm ngặt. Chỉ giữ tại thành phần thực sự cần gọi token endpoint. Với web app có backend, BFF thường cho phép giữ refresh token phía server và dùng session cookie cho browser.

- Authorization server có thể lưu hash/fingerprint cùng trạng thái family, client, grant và expiry.
- Backend client cần khôi phục token để refresh nên lưu ciphertext bằng AEAD và quản lý key qua KMS/HSM.
- Mobile app dùng secure storage của hệ điều hành.
- Browser không nên giữ refresh token dài hạn trong `localStorage` nếu kiến trúc BFF có thể đáp ứng.
- Dùng rotation/reuse detection hoặc sender-constrained token theo threat model.
- Xóa credential phía client khi logout, revoke, offboarding hoặc family bị compromise.

Khi refresh token đã consumed, không xóa mọi dấu vết ngay nếu authorization server cần fingerprint/status để phát hiện reuse. Giữ metadata tối thiểu trong cửa sổ detection, không giữ raw token.

### 6.3. ID token

ID token là assertion dành cho OIDC client, không phải access token gọi API. Client chỉ cần giữ nó trong thời gian và phạm vi cần thiết để xác minh đăng nhập hoặc duy trì session theo kiến trúc. Tránh sao chép toàn bộ ID token vào log hay analytics. Nếu ứng dụng chỉ cần subject reference và một số claims đã được cho phép, lưu các trường tối thiểu đó thay vì giữ nguyên token.

### 6.4. Opaque token và JWT

Opaque token thường cần server-side state/introspection; JWT có thể tự chứa claims và được xác minh bằng chữ ký. Sự khác biệt này ảnh hưởng cách lưu metadata:

- Với opaque token, giữ fingerprint và trạng thái cần cho introspection/revocation; dọn sau khi hết cửa sổ cần thiết.
- Với JWT, tránh lưu raw token; nếu cần revoke trước `exp`, giữ denylist hoặc trạng thái grant tối thiểu theo TTL phù hợp.
- Không giả định JWT không cần retention policy chỉ vì resource server không lưu token.
- Không giữ denylist vô thời hạn nếu token đã hết hạn và không thể được chấp nhận nữa; dọn theo thời gian cộng clock skew và policy liên quan.

## 7. Giảm dữ liệu ở log, trace và metric

Logging là một trong những nơi token tồn tại lâu hơn dự kiến. HTTP access log, reverse proxy, API gateway, exception tracker, APM agent và debug log có thể ghi URL, header hoặc body chứa token.

### 7.1. Không ghi bearer secret

Không ghi các giá trị sau:

- `Authorization: Bearer ...` hoặc raw access/refresh token.
- Token endpoint body có `refresh_token`, `access_token`, `id_token` hoặc authorization code.
- Client secret, private key, HMAC secret, PKCE verifier.
- Toàn bộ JWT payload nếu có claims cá nhân hoặc quyền truy cập.

Redact ở nơi dữ liệu đi vào hệ thống log, không chỉ dựa vào quy tắc lọc ở dashboard. Kiểm tra reverse proxy, gateway, web server, framework security filter, HTTP client wire logging, APM agent và error reporting SDK.

### 7.2. Giữ audit event tối thiểu

Thay raw token bằng định danh nội bộ hoặc sự kiện có cấu trúc:

```json
{
  "event": "refresh_token.revoked",
  "client_alias": "web-bff",
  "token_family_ref": "family-ref-opaque",
  "reason": "user_logout",
  "occurred_at": "2026-11-23T10:00:00Z",
  "request_ref": "correlation-ref"
}
```

Ví dụ trên chỉ minh họa cấu trúc. `token_family_ref` và `request_ref` vẫn phải được bảo vệ vì có thể liên kết với hồ sơ hoặc sự kiện khác. Không gắn raw token hoặc token hash vào log chỉ để tra cứu.

### 7.3. Metric không mang định danh cá nhân

Metric nên dùng label hữu hạn như `outcome=active|inactive|error`, `client_type=web|mobile|service`, `issuer=primary|partner` hoặc `reason=user_logout|admin_revoke|reuse_detected`. Không dùng `sub`, email, tenant ID tùy ý, `jti`, token hash, session ID hoặc request ID làm label. Cardinality cao vừa gây chi phí vừa làm dữ liệu liên kết khó kiểm soát.

## 8. Cache và thời hạn lưu metadata active

Cache introspection có thể tăng hiệu năng nhưng kéo dài khoảng thời gian resource server dựa vào kết quả cũ. TTL phải phù hợp với cam kết phát hiện revocation.

Ví dụ, nếu chính sách yêu cầu token bị revoke được phát hiện trong tối đa 60 giây, cache active không được tồn tại 10 phút. Có thể đặt TTL nhỏ hơn giới hạn đó để dành ngân sách cho network, clock skew và propagation.

Quy tắc:

- TTL cache active không vượt `exp` hoặc giới hạn revocation policy.
- Có thể dùng TTL ngắn hơn cho token/operation nhạy cảm.
- Xử lý cache invalidation khi nhận revocation event đáng tin cậy.
- Không cache timeout hoặc lỗi mạng thành `active=true`.
- Negative cache cho token inactive cũng cần TTL và giới hạn riêng.
- Khi thay đổi issuer, key hoặc policy, xác định cache entry nào phải invalidated.

Cache key có thể dựa trên token fingerprint nội bộ, nhưng không đưa fingerprint vào log/metric. Nếu cache lưu claims, chỉ giữ trường cần cho authorization decision và giới hạn thời gian.

## 9. Quy trình xóa dữ liệu hết hạn

Một cleanup job cần có phạm vi, điều kiện và hành vi rõ ràng. Không chỉ chạy `DELETE WHERE expires_at < now()` nếu record còn liên quan đến family, audit, reuse detection hoặc legal hold.

### Bước 1 — Phân loại trước khi xóa

Tách dữ liệu theo trạng thái và mục đích:

- Token active: giữ tới expiry/revocation theo policy.
- Token consumed: giữ fingerprint/status trong cửa sổ reuse detection.
- Token revoked: giữ metadata tối thiểu trong thời gian cần cho audit và propagation.
- Token expired: giữ metadata ngắn hạn nếu cần xử lý request trễ, clock skew hoặc báo cáo; sau đó dọn.
- Audit event: áp dụng retention schedule riêng.
- Legal hold/incident hold: đưa vào phạm vi ngoại lệ có phê duyệt, thời hạn xem xét và owner.

### Bước 2 — Xóa theo batch có giới hạn

- Chạy batch nhỏ để tránh khóa bảng hoặc tạo tải lớn.
- Dùng index trên expiry/status/retention date.
- Có thể partition theo thời gian để xóa nhanh các partition đã hết retention nếu mô hình dữ liệu cho phép.
- Ghi nhận số row dự kiến, số row xóa, thời gian và lỗi theo batch.
- Dùng transaction phù hợp và xử lý retry idempotent.
- Không xóa token family đang có token active hoặc event chưa được xử lý.

### Bước 3 — Propagate deletion

Xóa hoặc invalidation tại các lớp liên quan:

- Primary database và read replica theo cơ chế replication.
- Cache phân tán, local cache và in-memory cache.
- Search index, data warehouse, analytics export và reporting table.
- Log, trace và error tracker theo retention/redaction process.
- Client credential store và thiết bị nếu có kênh quản lý phù hợp.
- Backup khi hết retention; với backup immutable, đánh dấu chờ hết thời hạn lock và không phục hồi bản chứa dữ liệu đã phải xóa vào production mà không replay deletion/revocation state.

### Bước 4 — Xác minh và audit

Sau cleanup, kiểm tra số lượng còn lại theo trạng thái và phạm vi. Lưu kết quả tổng hợp, job version, thời điểm, policy version, số record xóa/giữ và lý do giữ. Không lưu raw token trong báo cáo cleanup.

## 10. Backup, restore và xóa dữ liệu

Backup có thể giữ dữ liệu sau khi bản chính đã bị xóa. Vì vậy, retention schedule phải nói rõ:

- Backup được giữ trong bao lâu và ai được đọc/restore.
- Bản backup có immutable retention hay legal hold không.
- Khi restore, làm sao áp dụng lại revocation/deletion event xảy ra sau snapshot.
- Khi backup hết retention, quy trình xóa object, replica, snapshot và key material là gì.
- Nếu cần xóa sớm theo yêu cầu hợp lệ, có thể thực hiện selective deletion, crypto-erasure hoặc chờ backup hết retention theo policy/pháp luật áp dụng hay không.

Không tuyên bố dữ liệu đã bị xóa hoàn toàn nếu vẫn còn trong backup bất biến. Ghi nhận chính xác trạng thái: bản chính đã xóa, cache đã invalidated, backup còn trong retention và sẽ hết hạn vào mốc nào. Khi restore, không để dữ liệu/token đã bị revoke hoặc xóa sống lại; cần replay tombstone/revocation event hoặc áp dụng biện pháp thu hồi rộng hơn nếu không thể xác minh.

Cryptographic erasure có thể hữu ích khi dữ liệu được mã hóa bằng key riêng và key bị hủy có kiểm soát, khiến ciphertext không còn giải mã được. Tuy nhiên, phải kiểm tra key có bản sao/backup hay không, có dùng chung cho dữ liệu khác không và liệu phương pháp đó đáp ứng yêu cầu xóa áp dụng hay không. Hủy key dùng chung có thể làm mất dữ liệu hợp lệ ngoài phạm vi.

## 11. Ngoại lệ: legal hold, điều tra và yêu cầu lưu trữ

Có trường hợp dữ liệu cần được giữ lâu hơn retention thông thường, ví dụ điều tra sự cố, tranh chấp, yêu cầu của cơ quan có thẩm quyền hoặc nghĩa vụ lưu trữ theo hợp đồng/pháp luật. Ngoại lệ cần được kiểm soát:

1. Xác định đúng phạm vi dữ liệu và mục đích giữ.
2. Ghi người phê duyệt, căn cứ, ngày bắt đầu và ngày xem xét lại.
3. Chỉ giữ trường dữ liệu cần thiết; ưu tiên token ID/family reference và sự kiện thay cho raw bearer token.
4. Tách quyền truy cập legal hold khỏi quyền vận hành thông thường.
5. Mã hóa và ghi audit mọi lần truy cập/export.
6. Đánh giá định kỳ xem căn cứ giữ còn hiệu lực không.
7. Xóa hoặc ẩn danh ngay khi hold kết thúc và không còn mục đích hợp lệ khác.

Legal hold không phải lý do để vô hiệu hóa toàn bộ cleanup job hoặc giữ mọi token của người dùng. Ngoại lệ phải có giới hạn cụ thể và không làm token đã bị revoke trở lại có hiệu lực.

## 12. Trách nhiệm và kiểm soát tuân thủ

Một mô hình trách nhiệm rõ ràng giúp retention policy được thực thi:

| Vai trò | Trách nhiệm |
| --- | --- |
| Product/service owner | Xác định mục đích, loại dữ liệu và nhu cầu nghiệp vụ. |
| Security architect | Đánh giá rủi ro token, expiry, revocation, cache và storage. |
| Privacy/legal/compliance owner | Ánh xạ nghĩa vụ áp dụng, retention và ngoại lệ. |
| Platform/data owner | Triển khai TTL, cleanup, backup lifecycle và deletion propagation. |
| SRE/operations | Theo dõi job, alert, RPO/RTO và xử lý lỗi xóa/restore. |
| Auditor/security assurance | Kiểm tra bằng chứng, quyền truy cập, ngoại lệ và kết quả diễn tập. |

Mỗi dataset cần có owner, purpose, classification, retention start event, retention period, deletion method, backup policy và evidence location. Không để thời hạn lưu trữ chỉ tồn tại trong tài liệu mà không có cấu hình hoặc job thực thi.

## 13. Kiểm thử data minimization và retention

Kiểm thử phải chứng minh cả dữ liệu không được thu thập dư thừa lẫn dữ liệu được xóa đúng lúc.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| RET-01 | API request thành công có bearer token. | Access log không chứa raw Authorization header. |
| RET-02 | Token endpoint trả refresh token mới. | HTTP wire log, trace và error tracker không chứa token response secret. |
| RET-03 | JWT chứa claims cá nhân. | Không lưu raw JWT/payload vào analytics nếu không có mục đích được phê duyệt. |
| RET-04 | Access token hết hạn. | Token không còn được chấp nhận; cache/metadata được dọn theo retention. |
| RET-05 | Refresh token bị revoke. | Client credential bị xóa theo policy; AS giữ metadata tối thiểu cho detection/audit. |
| RET-06 | Refresh token đã consumed. | Fingerprint/status được giữ đủ cửa sổ reuse detection rồi mới dọn. |
| RET-07 | Introspection cache active hết TTL. | Cache entry bị evict; request sau kiểm tra lại nguồn trạng thái. |
| RET-08 | Token bị revoke trong lúc cache còn active. | Invalidation/TTL đáp ứng giới hạn revocation đã cam kết. |
| RET-09 | Cleanup job chạy nhiều lần. | Job idempotent, không xóa nhầm record active hoặc family đang xử lý. |
| RET-10 | Record nằm trong legal hold. | Cleanup bỏ qua đúng phạm vi được phê duyệt và ghi audit. |
| RET-11 | Legal hold kết thúc. | Dữ liệu trở lại lịch cleanup bình thường. |
| RET-12 | Database replica và cache. | Deletion/revocation được propagate theo SLA. |
| RET-13 | Backup chứa metadata cũ. | Retention được áp dụng; restore replay tombstone/revocation event. |
| RET-14 | Restore snapshot trước khi token bị revoke. | Token không sống lại; trạng thái mới hơn được tái áp dụng. |
| RET-15 | Kiểm tra metric label. | Không có token, hash, subject, tenant hoặc request ID. |
| RET-16 | Kiểm tra trace/APM. | Không có Authorization header, token body hoặc sensitive claims. |
| RET-17 | Yêu cầu xóa dữ liệu hợp lệ. | Xóa theo phạm vi, ghi nhận phần còn trong backup và ngày hết retention. |
| RET-18 | Token hết hạn nhưng audit event còn trong retention. | Chỉ giữ event tối thiểu; không giữ bearer token để phục vụ audit. |

Nên kiểm tra bằng dữ liệu fixture có giá trị dễ nhận biết, sau đó tìm kiếm trong log, trace, database, cache và export để xác nhận không có bản sao ngoài dự kiến. Dữ liệu kiểm thử phải giả lập; không dùng token production để kiểm tra redaction.

## 14. Checklist triển khai

- [ ] Có inventory token, metadata, cache, log, trace, backup và client storage.
- [ ] Mỗi loại dữ liệu có mục đích, owner, classification và retention period.
- [ ] Phân biệt expiry token với retention dữ liệu.
- [ ] Access token không được lưu raw trong log, URL hoặc database nghiệp vụ.
- [ ] Refresh token chỉ được giữ tại thành phần cần dùng và được bảo vệ bằng storage phù hợp.
- [ ] ID token chỉ được giữ trong phạm vi cần cho OIDC client.
- [ ] Opaque token fingerprint/status được giữ đủ cho introspection, revocation và reuse detection rồi dọn.
- [ ] Cache TTL phù hợp expiry và revocation SLA.
- [ ] Cleanup job có batch, idempotency, legal hold và audit.
- [ ] Deletion được propagate tới replica, cache, analytics, log và backup theo policy.
- [ ] Restore không làm sống lại token, grant hoặc metadata đã bị revoke/xóa.
- [ ] Ngoại lệ retention có phê duyệt, phạm vi và ngày xem xét lại.
- [ ] Metric/trace/audit không chứa raw bearer secret hoặc dữ liệu không cần thiết.
- [ ] Có test cho redaction, expiry, cleanup, backup, restore và yêu cầu xóa.
- [ ] Có bằng chứng vận hành để chứng minh retention policy đang được thực thi.

**Ghi nhớ:** Hết hạn token chỉ kết thúc khả năng sử dụng token theo policy; nó không tự xóa các bản sao trong log, cache, backup hay client storage. Hãy xác định mục đích và thời hạn riêng cho từng loại dữ liệu, giữ metadata tối thiểu cần cho revocation/audit, rồi tự động xóa hoặc ẩn danh khi mục đích kết thúc.

## Tài liệu đối chiếu

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và xử lý trạng thái token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái active và metadata token cho resource server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access/refresh token, rotation và replay detection.
- [GDPR — Regulation (EU) 2016/679, Article 5](https://eur-lex.europa.eu/eli/reg/2016/679/oj): nguyên tắc data minimisation và storage limitation khi GDPR áp dụng.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): quản trị rủi ro quyền riêng tư và dữ liệu theo mục đích.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): giảm dữ liệu nhạy cảm trong log và bảo vệ log.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, truy cập, rotation và vòng đời secret.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): bảo vệ dữ liệu lưu trữ và quản lý khóa.
