# Phát hiện replay token làm mới

## 1. Bài toán cần giải quyết

Trong OAuth 2.0 và OpenID Connect (OIDC), **access token** được gửi đến resource server để truy cập tài nguyên, còn **refresh token** được gửi đến authorization server (máy chủ ủy quyền) để xin access token mới mà người dùng không phải đăng nhập lại. Refresh token thường có thời gian sống dài hơn access token, vì vậy việc nó bị lộ có thể cho phép kẻ tấn công duy trì phiên trong thời gian dài.

**Replay refresh token** là việc một refresh token đã được sử dụng hoặc đã bị thay thế lại xuất hiện trong một yêu cầu làm mới khác. Ví dụ, sau khi ứng dụng dùng **RT0** đổi lấy **RT1**, một bên tiếp tục gửi **RT0** đến token endpoint. Nếu hệ thống dùng **refresh token rotation** (xoay vòng token làm mới), sự kiện đó có thể được phát hiện nhờ trạng thái sử dụng được lưu ở máy chủ.

Cần phân biệt rõ:

- Việc cùng một **access token** xuất hiện trong nhiều API request thường là bình thường vì access token có thể được sử dụng nhiều lần trong thời hạn của nó.
- Việc một **refresh token loại dùng một lần** xuất hiện lại sau lần đổi thành công là dấu hiệu bất thường, nhưng **chưa đủ để khẳng định có kẻ tấn công**: retry do mất phản hồi hoặc hai request đồng thời cũng gây hiện tượng tương tự.
- Chỉ kiểm tra chữ ký, thời hạn và claims của JWT không cho biết token đã được sử dụng trước đó hay chưa. Muốn phát hiện replay với rotation, authorization server phải duy trì trạng thái, kể cả khi refresh token là JWT.

Bài học tập trung vào **phát hiện và xử lý việc sử dụng lại refresh token**, trong bối cảnh rộng hơn của vòng đời token, xác thực client, ràng buộc phiên và phòng chống token bị đánh cắp.

## 2. Mô hình đe dọa và ví dụ vòng đời

Một refresh token kiểu **bearer** có thể bị sử dụng bởi bất kỳ bên nào nắm được giá trị token và đáp ứng các điều kiện khác của token endpoint. Nó có thể bị lộ từ kho lưu trữ không an toàn, log, bản sao lưu, mã độc, lỗ hổng XSS hoặc thiết bị bị chiếm quyền.

Giả sử ứng dụng nhận một cặp **AT0 + RT0**. Authorization server áp dụng rotation: mỗi lần làm mới thành công sẽ vô hiệu hóa refresh token vừa dùng và phát hành refresh token mới.

~~~mermaid
sequenceDiagram
    participant C as Ứng dụng hợp lệ
    participant AS as Authorization Server
    participant X as Bên đang giữ RT0 cũ
    C->>AS: Đổi RT0 tại token endpoint
    AS->>AS: RT0: ACTIVE → USED
    AS-->>C: Access token AT1 + refresh token RT1
    X->>AS: Gửi lại RT0
    AS->>AS: Nhận ra RT0 đã USED; thu hồi họ token
    AS-->>X: invalid_grant
~~~

Trong ví dụ này, **lần gửi RT0 thứ hai** là một tín hiệu replay. Khi một refresh token đã dùng bị phát lại, máy chủ không thể biết chắc ai là bên hợp lệ, vì vậy biện pháp an toàn thường là **thu hồi toàn bộ họ refresh token (token family)** liên quan và yêu cầu đăng nhập lại.

Nếu kẻ tấn công đổi **RT0 trước**, họ có thể nhận **RT1**. Đến khi ứng dụng hợp lệ gửi **RT0**, chính yêu cầu của ứng dụng sẽ kích hoạt phát hiện reuse. Vì vậy, hệ thống phát hiện được **xung đột sử dụng**, chứ không có khả năng tự xác định phía nào là chủ sở hữu hợp pháp chỉ bằng token đã trình.

## 3. Cơ chế phát hiện: rotation kết hợp trạng thái máy chủ

### 3.1. Refresh token rotation

Mỗi lần làm mới thành công:

1. Kiểm tra refresh token, client/phiên liên quan và các điều kiện bảo mật.
2. Đánh dấu refresh token hiện tại là **USED** (không còn đổi được lần nữa).
3. Phát hành refresh token kế tiếp bằng nguồn ngẫu nhiên mật mã.
4. Cập nhật con trỏ đến refresh token hiện hành của phiên.
5. Lưu tất cả thay đổi **nguyên tử** trong một giao dịch.

Một chuỗi có thể được biểu diễn như sau:

~~~text
RT0 (USED) ──> RT1 (USED) ──> RT2 (ACTIVE)
     │              │               │
     └──────────────┴───────────────┘
                  family F
~~~

Trong một family đang hoạt động, chỉ một refresh token là token hiện hành. Khi **RT0** hoặc **RT1** được gửi lại sau khi đã đổi thành công, authorization server có thể xác định token đó thuộc **family F** và xử lý sự kiện reuse.

Không được xóa ngay mọi bản ghi token đã dùng. Nếu xóa lịch sử quá sớm, máy chủ có thể chỉ nhìn thấy một token không tồn tại, mất khả năng liên kết lần replay với family bị ảnh hưởng. Cần giữ trạng thái/token digest trong thời hạn phục vụ phát hiện, phù hợp với vòng đời family và chính sách lưu giữ.

### 3.2. Token family và phạm vi thu hồi

Một **token family** biểu diễn chuỗi các refresh token kế tiếp cho một phiên/ủy quyền của client. Nên gắn family với **user (subject), client_id, phiên hoặc thiết bị**, cùng phạm vi quyền đã cấp. Các phiên trên thiết bị khác nhau thường có family riêng để tránh thu hồi rộng hơn cần thiết.

Ví dụ mô hình dữ liệu tối thiểu:

| Thực thể | Trường tiêu biểu | Mục đích |
|---|---|---|
| Token family | family_id, subject_id, client_id, session_id, status, current_token_id, expires_at | Biết token hiện hành và phạm vi thu hồi |
| Refresh token record | token_id, family_id, token_digest, generation, status, issued_at, consumed_at, expires_at | Nhận ra token đã dùng lại |
| Dữ liệu ràng buộc (nếu áp dụng) | sender_key_thumbprint hoặc chứng chỉ/client binding | Kiểm tra token đang được đúng bên sở hữu dùng |
| Audit event | event_type, family_id, client_id, request_id, occurred_at | Điều tra và theo dõi bất thường |

Trạng thái tối thiểu nên được định nghĩa nhất quán:

- **ACTIVE**: refresh token hiện hành và còn đáp ứng điều kiện sử dụng.
- **USED**: refresh token đã được đổi thành công; gửi lại có thể là reuse.
- **REVOKED**: token/family đã bị thu hồi.
- **EXPIRED**: hết hiệu lực theo thời gian; có thể biểu diễn bằng kiểm tra expires_at thay vì lưu trạng thái riêng.

**Không lưu giá trị refresh token dạng rõ** trong cơ sở dữ liệu hoặc log. Với opaque token sinh từ bộ tạo số ngẫu nhiên mật mã, có thể tra cứu bằng digest của token; HMAC-SHA-256 với khóa bí mật phía máy chủ là một lựa chọn thực tế. Token cần đủ entropy (ví dụ 256 bit). Với refresh token dạng JWT, vẫn phải ghi nhận **jti** hoặc định danh tương đương và trạng thái family để phát hiện reuse; chữ ký JWT không thay thế được phép kiểm tra trạng thái.

### 3.3. Tại sao cần giao dịch nguyên tử?

Giả sử hai request đồng thời cùng gửi **RT3**. Nếu cả hai đều đọc trạng thái ACTIVE trước khi bên nào kịp cập nhật, máy chủ có thể phát hành **RT4a** và **RT4b**. Khi đó chuỗi token rẽ nhánh, làm hỏng giả định “một family có một token hiện hành”.

Cần bảo đảm thao tác **kiểm tra → đánh dấu USED → tạo token kế tiếp → cập nhật family** là một đơn vị đồng bộ. Có thể dùng:

- Khóa bản ghi family trong cơ sở dữ liệu (ví dụ SELECT ... FOR UPDATE), sau đó đọc lại trạng thái token bên trong giao dịch.
- Hoặc compare-and-swap/optimistic locking bằng version và kiểm tra chính xác số hàng được cập nhật.
- Ràng buộc duy nhất phù hợp để không thể tồn tại hai token ACTIVE của cùng một family.

Ở hệ thống nhiều instance, cache có độ nhất quán cuối cùng **không đủ** để quyết định một refresh token đã được dùng hay chưa. Nguồn trạng thái dùng để rotation cần có tính nhất quán phù hợp và thao tác cạnh tranh phải được giải quyết xác định.

## 4. Quy trình kiểm tra một yêu cầu refresh

Token endpoint nên xác minh đầy đủ các điều kiện trước khi cấp token mới:

1. **Xác thực client và kiểm tra ràng buộc** theo kiểu client và cấu hình OAuth: client_id, client authentication nếu có, phiên, sender-constraining nếu được áp dụng.
2. **Kiểm tra token**: giá trị tra cứu được/định dạng hợp lệ, chữ ký JWT nếu là JWT, issuer, audience dành cho authorization server, thời hạn, token type và các điều kiện liên quan. Không chấp nhận refresh token như access token tại resource server.
3. **Tải family và trạng thái dưới cơ chế đồng bộ** để bảo đảm chỉ một request có thể đổi token hiện tại.
4. **Phân loại kết quả**: token còn ACTIVE và đúng token hiện hành, token đã USED, token bị thu hồi/hết hạn, hoặc không xác định.
5. **Quyết định**: rotate thành công, trả lỗi bình thường, hoặc thu hồi family khi phát hiện reuse có căn cứ.

~~~mermaid
flowchart TD
    A[Nhận refresh token] --> B{Token, client và binding hợp lệ?}
    B -- Không --> X[Trả invalid_grant hoặc lỗi client thích hợp]
    B -- Có --> C[Khóa và tải trạng thái family/token]
    C --> D{Family còn ACTIVE?}
    D -- Không --> X
    D -- Có --> E{Token đã USED?}
    E -- Có --> F[Đánh dấu reuse và thu hồi family]
    F --> G[Commit, ghi sự kiện, trả invalid_grant]
    E -- Không --> H{Token là ACTIVE hiện hành và chưa hết hạn?}
    H -- Không --> X
    H -- Có --> I[Đánh dấu token cũ USED, tạo token mới, cập nhật family]
    I --> J[Commit và trả access token + refresh token mới]
~~~

Nếu token không tra cứu được, không nên tùy tiện thu hồi một family bất kỳ chỉ dựa trên IP, user agent hay client_id. Các dữ liệu đó không chứng minh token thuộc family nào.

### Giả mã phía authorization server

Đoạn dưới đây minh họa luồng xử lý gần với ứng dụng Java; tên hàm mang tính khái niệm, chưa phải chương trình có thể chạy ngay:

~~~text
refresh(presentedToken, clientContext):
    outcome = database.transaction(() -> {
        record = findByDigest(HMAC(serverSecret, presentedToken))
        if record == null:
            return INVALID_GRANT

        family = lockFamilyForUpdate(record.familyId)
        record = reloadToken(record.id)

        if !clientAndSenderMatch(record, family, clientContext):
            audit("refresh_binding_mismatch", family.id)
            return INVALID_GRANT

        if family.status != ACTIVE:
            return INVALID_GRANT

        if record.status == USED:
            revokeFamily(family.id, reason = "REFRESH_REUSE")
            revokeActiveRefreshTokens(family.id)
            audit("refresh_reuse_detected", family.id)
            return REUSE_DETECTED

        if record.status != ACTIVE
           or record.id != family.currentTokenId
           or record.isExpired():
            return INVALID_GRANT

        nextRawToken = secureRandomToken(256_bits)
        markUsed(record.id)
        nextRecord = insertActiveToken(
            family.id, digest(nextRawToken), record.generation + 1
        )
        setCurrentToken(family.id, nextRecord.id)
        accessToken = issueAccessTokenForAuthorizedScope(family)
        return ISSUED(accessToken, nextRawToken)
    })

    if outcome == ISSUED:
        return tokenResponse(outcome)
    return oauthError("invalid_grant")
~~~

**Điểm quan trọng khi triển khai bằng Spring/JPA hoặc framework có transaction:** trường hợp reuse cần **commit lệnh thu hồi** trước khi trả lỗi cho client. Nếu ném exception ngay bên trong transaction và framework tự rollback, việc thu hồi family có thể bị mất. Vì thế giả mã trả kết quả từ giao dịch rồi mới tạo OAuth error response.

Việc xác thực client không thành công có thể cần lỗi **invalid_client** theo quy định OAuth, thay vì luôn dùng invalid_grant như trong giả mã rút gọn. Đừng trả thông tin chi tiết về token bị đánh cắp hay family nội bộ cho bên gọi.

Ví dụ thông báo lỗi cho refresh token không còn hiệu lực:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{"error":"invalid_grant"}
~~~

## 5. Phân biệt replay thật với tình huống vận hành

| Tình huống | Hệ thống quan sát | Cách hiểu và xử lý |
|---|---|---|
| Ứng dụng dùng RT5 lần đầu | RT5 là ACTIVE hiện hành | Rotate RT5 → RT6, trả token mới |
| Kẻ tấn công gửi RT5 sau khi RT6 đã phát hành | RT5 đã USED | Phát hiện reuse; thu hồi family và yêu cầu xác thực lại |
| Kẻ tấn công dùng RT5 trước, người dùng dùng RT5 sau | Lần thứ hai vẫn thấy RT5 đã USED | Phát hiện xung đột, nhưng không xác định được ai dùng trước là hợp lệ |
| Client retry RT5 vì phản hồi chứa RT6 bị mất | RT5 đã USED | Có thể là replay giả; thiết kế retry/idempotency thận trọng |
| Hai tab cùng refresh bằng RT5 | Hai request tranh quyền đổi một token | Serialize ở client; máy chủ vẫn cần giao dịch nguyên tử |
| Token không tồn tại hoặc giả mạo | Không có bản ghi đáng tin cậy | Từ chối, ghi telemetry; không suy đoán family để thu hồi |
| Token hiện hành hết hạn theo chính sách | Hết hạn, không nhất thiết USED | Trả invalid_grant, yêu cầu phiên mới theo chính sách |
| Refresh token bị ràng buộc với khóa gửi từ thiết bị khác | Không chứng minh được quyền sở hữu khóa | Từ chối và ghi dấu hiệu rủi ro; cân nhắc thu hồi theo chính sách |

Rotation thuần túy coi **sử dụng lại token đã USED** là tín hiệu đáng kể, nhưng tín hiệu này còn có thể đến từ hành vi retry hợp lệ. Nếu chấp nhận “grace period” cho token cũ, phải hiểu rằng trong khoảng đó kẻ giữ token bị lộ cũng có thêm cơ hội sử dụng. Tránh thiết kế cho phép hai yêu cầu dùng cùng token cũ **tạo ra hai refresh token mới**.

Một số hệ thống dùng cơ chế idempotency có ràng buộc chặt với request, phiên hoặc bằng chứng sở hữu khóa để xử lý retry, nhưng cần phân tích kỹ khả năng kẻ tấn công tái sử dụng thông tin retry. Trả lại refresh token mới cho mọi bên chỉ vì họ giữ token cũ trong một khoảng thời gian không phải cách xử lý an toàn mặc định.

Ở phía client, nên **gom nhiều yêu cầu refresh thành một tác vụ duy nhất** (single-flight), lưu token mới một cách an toàn trước khi thực hiện refresh tiếp theo, và xử lý trường hợp mất kết nối bằng chính sách được định nghĩa rõ.

## 6. Biện pháp hỗ trợ để giảm khả năng replay

### Sender-constrained refresh token

Refresh token có thể được **ràng buộc với bên gửi**, chẳng hạn thông qua mutual TLS (mTLS) hoặc Demonstration of Proof-of-Possession (DPoP). Khi đó chỉ lấy được chuỗi token là chưa đủ; yêu cầu refresh còn phải chứng minh quyền sở hữu khóa tương ứng.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), refresh token được cấp cho **public client** cần áp dụng **rotation hoặc sender-constraining** để phát hiện/ngăn việc dùng token bị lộ. Hai cách có thể kết hợp nếu phù hợp với kiến trúc và mức độ rủi ro.

Lưu ý: nếu khóa riêng của bên gửi cũng bị đánh cắp, sender-constraining có thể mất tác dụng. Với DPoP, kiểm tra proof còn đòi hỏi các điều kiện riêng như chữ ký, phương thức/URI đích, thời gian và khả năng chống replay của proof; đừng nhầm replay của **DPoP proof** với reuse của **refresh token**.

### Giới hạn quyền và thời gian sống

- Gắn refresh token với đúng **client**, người dùng, quyền đã cấp và resource/scope phù hợp; không cho phép dùng nó để tăng quyền ngoài ủy quyền ban đầu.
- Áp dụng thời hạn tuyệt đối và/hoặc hết hạn do không hoạt động theo chính sách; rotation không có nghĩa một phiên được gia hạn vô hạn.
- Dùng HTTPS ở mọi chặng liên quan; không truyền token qua URL, log hoặc hệ thống phân tích dữ liệu.
- Bảo vệ nơi lưu trữ: phía máy chủ có thể dùng kho bí mật/phiên phù hợp; ứng dụng di động dùng vùng lưu trữ bảo vệ của hệ điều hành; với ứng dụng web cần cân nhắc BFF hoặc cookie Secure, HttpOnly, SameSite cùng biện pháp chống CSRF phù hợp. Cookie HttpOnly không tự loại bỏ mọi nguy cơ XSS hay lạm dụng phiên.
- Dùng access token ngắn hạn để giới hạn tác động sau khi family bị thu hồi. Access token tự chứa dạng JWT thường vẫn có thể được resource server chấp nhận cho đến khi hết hạn nếu không có cơ chế thu hồi/denylist hay kiểm tra trạng thái tại máy chủ.

### Thu hồi và phản ứng sự cố

Khi reuse được xác nhận theo chính sách:

1. Thu hồi family liên quan và mọi refresh token con còn hiệu lực.
2. Ngăn cấp thêm refresh/access token từ family đó.
3. Ghi sự kiện bảo mật; có thể thông báo cho người dùng và yêu cầu xác thực lại.
4. Cân nhắc thu hồi hoặc chặn access token đã phát hành nếu kiến trúc hỗ trợ; nếu không, phải tính đến thời gian sống còn lại của chúng.
5. Không tự động thu hồi toàn bộ phiên ở mọi thiết bị nếu chỉ một family bị ảnh hưởng, trừ khi mức rủi ro hoặc chính sách bảo mật yêu cầu.

## 7. Quan sát, kiểm thử và vận hành

Các sự kiện nên theo dõi gồm **refresh_rotated**, **refresh_reuse_detected**, **refresh_family_revoked**, **refresh_binding_mismatch** và **refresh_failed**. Dữ liệu kiểm toán hữu ích là family_id, token_id hoặc digest đã xử lý phù hợp, client_id, request_id, thời điểm, nguyên nhân, dấu hiệu thiết bị/IP ở mức cần thiết. **Không ghi raw refresh token, access token, khóa riêng hay secret** vào log và thông báo lỗi.

Các kịch bản kiểm thử thiết yếu:

- Đổi RT0 hợp lệ trả RT1; RT0 không còn được đổi tiếp.
- Gửi lại RT0 sau rotation làm family bị thu hồi; RT1 cũng không đổi được nữa.
- Hai request đồng thời dùng RT0 chỉ tạo tối đa **một** successor hợp lệ; trạng thái còn nhất quán.
- Nếu response của lần đổi đầu tiên bị mất, retry được xử lý đúng theo chính sách đã chọn và không vô tình tạo nhánh token.
- Token không tồn tại, sai client, sai sender binding, hết hạn hoặc family đã thu hồi đều bị từ chối.
- Sau khi revoke, access token đã phát hành được xử lý đúng với cơ chế introspection/denylist hoặc thời hạn sống thực tế.
- Hệ thống vẫn nhận ra token USED đã tồn tại trong thời gian lưu trạng thái; việc dọn dữ liệu không phá hỏng khả năng phát hiện mà chính sách yêu cầu.

Nên quan sát tỷ lệ reuse theo client, phiên bản ứng dụng, thiết bị và thời điểm triển khai. Nếu tỷ lệ này tăng đột biến sau khi thay đổi mã refresh ở client, nguyên nhân có thể là lỗi đồng thời hoặc retry; vẫn phải xử lý theo chính sách bảo mật, đồng thời sửa nguồn gây lỗi. Các hệ thống nhiều instance cần kiểm tra race condition với cơ sở dữ liệu thật hoặc môi trường có đặc tính đồng bộ tương đương.

## 8. Những hiểu nhầm phổ biến

**“JWT có chữ ký hợp lệ thì không thể bị replay.”** Sai. Chữ ký bảo đảm tính xác thực và toàn vẹn của claims, không chứng minh một JWT chưa từng được dùng. Rotation vẫn cần trạng thái phía server.

**“Có refresh token rotation là ngăn được mọi cuộc tấn công.”** Sai. Rotation giúp **phát hiện reuse**, thường sau khi đã có ít nhất một lần đổi token thành công. Nếu token bị đánh cắp được sử dụng trước hoặc bên tấn công lấy được refresh token mới, tác động vẫn có thể xảy ra.

**“Phát hiện RT0 bị dùng lại chứng minh người gửi RT0 lần thứ hai là kẻ tấn công.”** Sai. Người dùng hợp lệ cũng có thể là bên gọi thứ hai sau khi kẻ tấn công đổi token trước, hoặc ứng dụng có thể retry do lỗi mạng.

**“Đã revoke refresh token thì access token hiện tại mất hiệu lực tức thì.”** Không mặc nhiên đúng. Điều đó phụ thuộc resource server có tra cứu trạng thái, cơ chế denylist/introspection hay chỉ xác thực JWT độc lập.

**“Chỉ cần khóa refresh endpoint trên một instance.”** Không đủ trong hệ thống nhiều instance. Phải bảo đảm thao tác rotation dùng trạng thái đồng bộ có tính nhất quán xuyên instance.

## 9. Tự kiểm tra kiến thức

1. Vì sao phải giữ thông tin về token đã **USED** sau khi cấp token mới?
2. Nếu cả người dùng và kẻ tấn công đều có RT0, hệ thống có thể xác định chính xác ai là chủ hợp pháp bằng thứ tự request hay không?
3. Điều gì xảy ra khi hai request cùng đọc RT0 là ACTIVE và cùng cấp token mới mà không có khóa hoặc CAS?
4. Vì sao không nên throw exception làm rollback transaction ngay sau khi ghi quyết định thu hồi family?
5. Sender-constrained refresh token làm thay đổi điều kiện để sử dụng token bị đánh cắp ra sao, và nó còn rủi ro nào?
6. Khi family bị thu hồi, tại sao một access token JWT đã phát hành có thể tiếp tục hoạt động trong thời gian ngắn?

**Ghi nhớ:** phát hiện replay refresh token dựa trên **rotation + trạng thái sử dụng đáng tin cậy + cập nhật nguyên tử**. Tín hiệu token cũ được sử dụng lại giúp hệ thống chặn tiếp tục làm mới trong một phiên có khả năng bị lộ, nhưng vẫn cần xử lý đúng các tình huống retry, concurrency, sender binding và access token đã phát hành.

## Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** refresh token grant và lỗi token endpoint (đặc biệt mục 6 và 5.2).
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ refresh token, rotation và sender-constraining.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** cơ chế ràng buộc token với khóa và kiểm tra proof.

