# Phiên bản phiên hoặc người dùng để vô hiệu hóa một nhóm token

## 1. Vì sao cần phiên bản token?

JWT thường là credential tự chứa: resource server có thể kiểm tra chữ ký và các claim như exp, iss, aud mà không cần hỏi Authorization Server (AS) ở mọi request. Cách này giảm phụ thuộc vào kho phiên tập trung, nhưng tạo ra một vấn đề: sau khi phát hành, token đã ký vẫn có thể được chấp nhận cho tới khi hết hạn, kể cả khi người dùng đăng xuất, đổi mật khẩu hoặc bị khóa tài khoản.

Nếu cần vô hiệu hóa nhiều token cùng lúc, hệ thống có thể dùng một **phiên bản token (token version)** hoặc **phiên bản phiên (session version)**. Mỗi token mang giá trị phiên bản tại thời điểm phát hành. Khi cần thu hồi một nhóm token, server tăng phiên bản hiện tại trong kho dữ liệu có thẩm quyền. Những token cũ mang phiên bản thấp hơn sẽ không còn khớp và bị từ chối.

Ví dụ:

- Alice đang có ba access token và hai refresh token được phát hành với token_version = 4.
- Alice đổi mật khẩu và hệ thống tăng phiên bản tài khoản lên 5.
- Các token mang phiên bản 4 bị từ chối ở lần kiểm tra tiếp theo.
- Token mới chỉ được phát hành với phiên bản 5 sau khi quy trình xác thực/ủy quyền cho phép.

Pattern này giúp thu hồi theo nhóm mà không phải lưu riêng từng jti của mọi token. Đổi lại, mỗi lần xác minh cần đọc hoặc kiểm tra một trạng thái phiên bản hiện tại, trực tiếp hoặc qua cache. Vì vậy, JWT sử dụng version check không còn hoàn toàn stateless.

## 2. Hai phạm vi phiên bản thường dùng

Không có một claim JWT chuẩn chung tên token_version hoặc session_version được mọi hệ thống dùng giống nhau. Đây thường là claim riêng của profile ứng dụng. Cần định nghĩa rõ phạm vi, kiểu dữ liệu và nơi lưu giá trị hiện tại.

### Phiên bản cấp người dùng/tài khoản

Một trường như token_version được lưu trên bản ghi người dùng. Tất cả token của người dùng đều mang cùng giá trị tại thời điểm phát hành.

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-4821",
  "aud": "orders-api",
  "token_version": 4,
  "iat": 1893450000,
  "exp": 1893450900
}
~~~

Khi server tăng token_version từ 4 lên 5, mọi token của user có phiên bản 4 đều không còn hợp lệ theo policy kiểm tra version.

Phạm vi này phù hợp khi muốn thu hồi tất cả phiên đăng nhập của một tài khoản, ví dụ:

- Người dùng đổi hoặc đặt lại mật khẩu.
- Tài khoản bị khóa, vô hiệu hóa hoặc nghi bị xâm phạm.
- Quản trị viên buộc đăng xuất mọi thiết bị.
- Quyền hoặc trạng thái bảo mật của tài khoản thay đổi theo chính sách yêu cầu thu hồi credential cũ.

Nhược điểm là người dùng không thể giữ phiên trên thiết bị A trong khi chỉ đăng xuất thiết bị B nếu chỉ có một version toàn tài khoản.

### Phiên bản cấp phiên đăng nhập

Nếu cần thu hồi một phiên hoặc một nhóm token thuộc một lần đăng nhập, có thể tạo bản ghi phiên riêng. Mỗi token mang định danh phiên và version của phiên đó.

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-4821",
  "aud": "payments-api",
  "session_id": "sess-7d2f91",
  "session_version": 2,
  "iat": 1893450000,
  "exp": 1893450900
}
~~~

Server lưu trạng thái tương ứng:

~~~json
{
  "session_id": "sess-7d2f91",
  "user_id": "user-4821",
  "session_version": 2,
  "status": "active"
}
~~~

Khi người dùng đăng xuất một thiết bị, server tăng session_version hoặc đánh dấu session là revoked. Các access token và refresh token thuộc session đó sẽ bị từ chối, trong khi phiên ở thiết bị khác vẫn có thể tiếp tục.

session_id phải là định danh khó đoán, duy nhất trong phạm vi hệ thống và không được dùng như bí mật thay cho xác thực. Giá trị này chỉ giúp tra cứu đúng bản ghi phiên; chữ ký token và các kiểm tra khác vẫn bắt buộc.

### So sánh phạm vi

| Cơ chế | Trạng thái hiện tại được lưu ở đâu? | Khi tăng/thu hồi | Phạm vi token bị ảnh hưởng |
| --- | --- | --- | --- |
| User token version | Bản ghi user/account | Tăng version của user | Tất cả token của user |
| Session version | Bản ghi của từng session | Tăng version hoặc revoke session | Token thuộc một session |
| Token family state | Bản ghi refresh-token family | Revoke family hoặc đánh dấu reuse | Token thuộc một chuỗi refresh cụ thể |
| jti denylist | Danh sách token ID bị thu hồi | Thêm một jti | Một token cụ thể |

Các cơ chế có thể kết hợp. Ví dụ, kiểm tra user version để thu hồi toàn tài khoản, session version để đăng xuất một thiết bị và refresh-token family để phát hiện việc sử dụng lại refresh token.

## 3. Mô hình dữ liệu và claim

Một thiết kế đơn giản có thể dùng hai loại bản ghi:

~~~sql
CREATE TABLE user_security_state (
    user_id             VARCHAR(128) PRIMARY KEY,
    token_version       BIGINT NOT NULL,
    account_status      VARCHAR(32) NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE login_session (
    session_id          VARCHAR(128) PRIMARY KEY,
    user_id             VARCHAR(128) NOT NULL,
    session_version     BIGINT NOT NULL,
    status              VARCHAR(32) NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    expires_at          TIMESTAMP NOT NULL,
    revoked_at          TIMESTAMP NULL
);
~~~

Đây là schema minh họa. Một hệ thống có thể dùng database khác, key-value store hoặc session service; điều quan trọng là dữ liệu phiên bản phải được cập nhật nguyên tử và tra cứu theo đúng user/session.

Khi phát hành JWT, AS đọc trạng thái hiện tại rồi đưa version vào claim:

~~~text
userState = loadCurrentUserSecurityState(userId)
session = createOrLoadLoginSession(userId)

claims = {
    sub: userId,
    token_version: userState.tokenVersion,
    session_id: session.id,
    session_version: session.version,
    iss: configuredIssuer,
    aud: requestedAudience,
    iat: now,
    exp: now + accessTokenLifetime
}

return signJwt(claims, configuredSigningKey)
~~~

Tên claim trong ví dụ là private application claims. Các bên phát hành và xác minh phải thống nhất tên, kiểu dữ liệu và ngữ nghĩa trong token profile. Không dùng một claim version với ý nghĩa khác nhau giữa các API.

### Kiểu dữ liệu và giá trị

- Version nên là số nguyên không âm, có miền giá trị được xác định rõ.
- Không chấp nhận string "4", số thực 4.0, boolean hoặc object thay cho integer nếu profile yêu cầu integer.
- Không tự mặc định claim bị thiếu thành 0 khi profile yêu cầu version.
- Không để client tự chọn hoặc tự tăng version.
- Không giảm version, tái sử dụng giá trị cũ hoặc reset về 0 khi xóa/tạo lại tài khoản.
- Version không phải secret và không thay thế chữ ký, session identifier hoặc credential.

Nếu cần hỗ trợ token được phát hành trước khi triển khai versioning, phải có chính sách migration riêng với thời điểm cắt chuyển rõ ràng. Không âm thầm coi mọi token thiếu version là phiên bản hiện tại.

## 4. Quy trình xác minh token có version

Version trong JWT chỉ đáng tin sau khi token đã qua xác minh chữ ký bằng khóa thuộc nguồn tin cậy. Không được đọc sub, token_version hoặc session_id từ token chưa xác minh rồi dùng các giá trị đó để quyết định phiên nào được chấp nhận.

Quy trình cho một access token:

1. Parse token theo profile và giới hạn kích thước.
2. Xác minh chữ ký bằng thuật toán allowlist và khóa tin cậy.
3. Kiểm tra iss, aud, exp, nbf, loại token và các claim bắt buộc.
4. Đọc sub và token_version từ claims đã xác minh.
5. Tải trạng thái bảo mật hiện tại của đúng user.
6. Từ chối nếu user không tồn tại, bị khóa hoặc trạng thái không cho phép đăng nhập.
7. So sánh version trong token với version hiện tại theo đúng quy tắc profile.
8. Nếu dùng session version, tra cứu session, xác minh session thuộc đúng user, còn active/chưa hết hạn và version khớp.
9. Chỉ tạo authenticated context và thực hiện authorization sau khi mọi bước đều thành công.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Xác minh chữ ký và token profile"]
    B --> C{"Token và claims hợp lệ?"}
    C -- Không --> X["Từ chối"]
    C -- Có --> D["Đọc sub và token_version đã xác minh"]
    D --> E["Đọc trạng thái user hiện tại"]
    E --> F{"Tài khoản active và version khớp?"}
    F -- Không --> X
    F -- Có --> G{"Profile có yêu cầu session version?"}
    G -- Không --> H["Tiếp tục authorization"]
    G -- Có --> I["Đọc session theo session_id"]
    I --> J{"Session active, thuộc user và version khớp?"}
    J -- Không --> X
    J -- Có --> H
    H --> K["Cho phép xử lý request theo scope/role"]
~~~

### So sánh bằng hay nhỏ hơn?

Có hai quy ước phổ biến:

- **Exact match:** chấp nhận khi token_version == current_token_version.
- **Minimum version:** chấp nhận khi token_version >= minimum_accepted_version, với quy tắc phát hành bảo đảm không thể có token mang version tương lai tùy ý.

Exact match thường dễ hiểu và phù hợp với một bộ đếm epoch được tăng mỗi khi thu hồi. Minimum version hữu ích trong một số mô hình migration hoặc phát hành phân tán nhưng cần policy chặt chẽ để tránh token có version cao bất thường.

Không dùng phép so sánh token_version >= current_version một cách tùy tiện nếu token được ký bởi issuer nhưng issuer có thể phát hành version tương lai do cache stale hoặc lỗi đồng bộ. Với pattern thông thường, nên dùng exact match.

## 5. Vô hiệu hóa tất cả token của một người dùng

Khi cần đăng xuất toàn bộ thiết bị hoặc xử lý sự cố tài khoản, server tăng version cấp user bằng thao tác nguyên tử.

Ví dụ:

~~~sql
UPDATE user_security_state
SET token_version = token_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id;
~~~

Các bước nghiệp vụ:

1. Xác thực người thực hiện hành động (người dùng, quản trị viên hoặc quy trình bảo mật).
2. Cập nhật version trong kho trạng thái có thẩm quyền bằng transaction/atomic operation.
3. Commit thay đổi trước khi báo thao tác thu hồi đã hoàn tất.
4. Phát sự kiện invalidate cache tới các resource server/region nếu có cache.
5. Thu hồi refresh-token family/session theo policy nếu chúng có trạng thái riêng.
6. Ghi audit event gồm user, lý do, thời điểm và actor thực hiện; không ghi token thô.
7. Những token cũ bị từ chối ở lần kiểm tra version tiếp theo.

Ví dụ:

| Thời điểm | Version tài khoản | Token | Kết quả |
| --- | ---: | --- | --- |
| Trước thu hồi | 4 | Token A: version 4 | Hợp lệ nếu các kiểm tra khác đạt |
| Trước thu hồi | 4 | Token B: version 4 | Hợp lệ nếu các kiểm tra khác đạt |
| Sau thu hồi | 5 | Token A: version 4 | Từ chối |
| Sau thu hồi | 5 | Token B: version 4 | Từ chối |
| Sau thu hồi và xác thực lại | 5 | Token C: version 5 | Có thể hợp lệ nếu được phát hành đúng policy |

Việc tăng version không tự làm token mới trở nên hợp lệ. Người dùng vẫn phải vượt qua quy trình xác thực và authorization để nhận token mới.

## 6. Vô hiệu hóa token của một phiên hoặc thiết bị

Khi người dùng chọn "đăng xuất thiết bị này" hoặc quản trị viên cần thu hồi một phiên cụ thể, không nên tăng version toàn user nếu muốn các thiết bị khác tiếp tục hoạt động.

Một cách là tăng version của session:

~~~sql
UPDATE login_session
SET session_version = session_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE session_id = :session_id
  AND user_id = :user_id
  AND status = 'active';
~~~

Một cách khác là đánh dấu session revoked:

~~~sql
UPDATE login_session
SET status = 'revoked',
    revoked_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE session_id = :session_id
  AND user_id = :user_id
  AND status = 'active';
~~~

Khi kiểm tra token, server phải xác minh session thuộc đúng sub. Không chỉ tra cứu session_id rồi chấp nhận; nếu một session ID bị ghép với user khác do lỗi mapping, có thể tạo nhầm quyền.

Session version hữu ích khi một session có nhiều access token hoặc refresh token qua các lần làm mới. Tăng version sẽ thu hồi cả nhóm token của session mà không cần biết từng jti.

## 7. Kết hợp user version và session version

Hệ thống có thể kiểm tra cả hai:

- token_version đại diện epoch bảo mật cấp tài khoản.
- session_id xác định một lần đăng nhập.
- session_version đại diện epoch của session.

Một token chỉ được chấp nhận khi:

~~~text
token.token_version == user.current_token_version
AND
session.status == "active"
AND
token.session_id == session.id
AND
session.user_id == token.sub
AND
token.session_version == session.current_session_version
~~~

Nhờ đó:

- Tăng user version: thu hồi token trên mọi thiết bị.
- Tăng session version hoặc revoke một session: thu hồi token của một thiết bị/phiên.
- Revoke refresh-token family: chặn một chuỗi refresh cụ thể nếu phát hiện reuse hoặc compromise.

Không bắt buộc mọi hệ thống phải dùng cả ba lớp. Chọn mức chi tiết phù hợp với yêu cầu thu hồi, chi phí đọc trạng thái và độ phức tạp vận hành.

## 8. Refresh token phải tuân theo version hiện tại

Nếu access token có version nhưng refresh endpoint không kiểm tra version, người dùng có thể tiếp tục dùng refresh token cũ để nhận access token mới. Điều đó vô hiệu hóa mục tiêu thu hồi theo nhóm.

Khi refresh:

1. Xác minh refresh token bằng cơ chế tương ứng; không coi việc decode là đủ.
2. Kiểm tra issuer, audience/token type, expiration và trạng thái refresh-token family.
3. Đọc user version hiện tại và so sánh với version trong refresh token.
4. Nếu có session binding, kiểm tra session active và session version khớp.
5. Nếu version không khớp hoặc session đã bị revoke, từ chối refresh và xử lý family theo policy.
6. Nếu hợp lệ, phát hành access token mới mang version hiện tại; áp dụng refresh token rotation nếu profile yêu cầu.
7. Lưu trạng thái refresh token mới và vô hiệu hóa token cũ theo quy tắc rotation.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant DB as Security State Store
    C->>AS: Refresh token
    AS->>AS: Verify refresh token
    AS->>DB: Read user/session version and status
    DB-->>AS: Current version and active state
    AS->>AS: Compare token versions
    alt Version and session valid
        AS->>AS: Rotate refresh token if required
        AS-->>C: New access token with current version
    else Revoked or version mismatch
        AS-->>C: Reject refresh; apply family/session policy
    end
~~~

Không cho refresh token tự khai version mới. Giá trị version trong token đầu vào phải được xác minh, sau đó đối chiếu với trạng thái hiện tại do server quản lý.

## 9. So sánh versioning với jti denylist và token introspection

Versioning là một cách thu hồi theo nhóm; nó không thay thế mọi cơ chế thu hồi.

| Cơ chế | Độ hạt thu hồi | Trạng thái online cần kiểm tra? | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- | --- |
| User token version | Toàn bộ token của user | Có, hoặc cache | Thu hồi toàn tài khoản đơn giản | Không thu hồi riêng một thiết bị |
| Session version/status | Token thuộc một session | Có, hoặc cache | Đăng xuất riêng thiết bị/phiên | Cần session record và lookup |
| jti denylist | Một token cụ thể | Có, hoặc cache | Thu hồi chính xác từng token | Tăng số bản ghi theo số token bị thu hồi |
| Token introspection | Theo trạng thái token tại AS | Có request tới AS hoặc cache response | AS có thể trả trạng thái và metadata tập trung | Tăng phụ thuộc mạng/AS |
| Access token lifetime ngắn | Tự hết hiệu lực theo thời gian | Không cần lookup nếu chỉ dùng chữ ký/claims | Giảm cửa sổ rủi ro và chi phí trạng thái | Không thu hồi ngay lập tức |

Một hệ thống có thể kết hợp:

- Access token ngắn hạn để giới hạn thời gian lạm dụng.
- User version cho sự kiện bảo mật ảnh hưởng toàn tài khoản.
- Session version để đăng xuất một thiết bị.
- jti denylist cho token bị lộ cần thu hồi riêng.
- Introspection hoặc centralized authorization cho resource có yêu cầu thu hồi gần như tức thời.

## 10. Cache, tính nhất quán và độ trễ thu hồi

Nếu mọi request đều đọc database để so sánh version, chi phí và tải hệ thống có thể tăng. Cache version giúp giảm tải nhưng tạo ra khoảng trễ: resource server có thể tiếp tục thấy version cũ sau khi server đã tăng version.

Ví dụ:

1. Database đổi version từ 4 lên 5.
2. Resource Server A đã cache version 4 trong 60 giây.
3. Token cũ mang version 4 vẫn có thể được chấp nhận ở A trong thời gian cache chưa hết hạn.
4. Sau khi cache hết hạn hoặc nhận sự kiện invalidate, A đọc version 5 và từ chối token cũ.

Vì vậy, thời gian cache là một phần của **revocation latency**, không chỉ là tối ưu hiệu năng.

Các lựa chọn:

- **Strongly consistent lookup:** đọc trạng thái hiện tại từ kho dữ liệu có consistency phù hợp ở mỗi lần xác minh. Độ trễ thu hồi thấp hơn nhưng tăng tải và phụ thuộc hạ tầng.
- **Short-lived cache:** cache version trong thời gian ngắn. Thu hồi có độ trễ tối đa gần với TTL cộng độ trễ phân phối.
- **Event-driven invalidation:** phát sự kiện khi version thay đổi để xóa cache trên các node. Nên kết hợp TTL làm cơ chế dự phòng vì sự kiện có thể thất lạc.
- **Hybrid:** dùng cache ngắn, event invalidation và authoritative lookup cho thao tác rủi ro cao.

### Multi-region và replica lag

Nếu version được ghi ở region A nhưng resource server ở region B đọc replica chưa đồng bộ, region B có thể tiếp tục chấp nhận token cũ. Cần xác định:

- Nơi nào là nguồn dữ liệu có thẩm quyền.
- Mức consistency cần thiết cho thao tác thu hồi.
- Cách phân phối sự kiện invalidate qua region.
- Cách xử lý khi một region mất kết nối với nguồn trạng thái.
- Thời gian tối đa token cũ còn được chấp nhận sau khi revoke.

Không tuyên bố "logout tức thời" nếu cache, replica hoặc request đang xử lý vẫn có thể dùng trạng thái cũ. Hãy định nghĩa và đo revocation latency thực tế.

## 11. Race condition khi phát hành và thu hồi

Versioning cần xử lý các thao tác đồng thời:

### Phát hành token cùng lúc với tăng version

Giả sử AS đọc version 4, sau đó quản trị viên tăng lên 5, rồi AS mới ký token chứa version 4. Token đó sẽ bị từ chối ở lần kiểm tra tiếp theo nếu resource server đã thấy version 5. Điều này an toàn nhưng có thể khiến client vừa đăng nhập nhận token không dùng được.

Để giảm lỗi:

- Đọc version và tạo session trong transaction hoặc qua thao tác nhất quán phù hợp.
- Có thể kiểm tra lại version ngay trước khi hoàn tất phát hành nếu quy trình yêu cầu.
- Đảm bảo token không được phát hành từ cache version cũ sau một sự kiện revoke đã commit.
- Chấp nhận rằng token được phát hành đồng thời với revoke có thể bị từ chối; client cần xử lý yêu cầu xác thực lại.

### Request đang xử lý khi version thay đổi

Một request có thể đã kiểm tra version 4 ngay trước khi server tăng lên 5, rồi tiếp tục xử lý sau thời điểm revoke. Version check không tự hủy một request đã qua bước xác minh.

Với thao tác rủi ro cao, có thể cần kiểm tra trạng thái trong transaction nghiệp vụ hoặc kiểm tra lại quyền ngay trước khi commit thay đổi. Không phải mọi request đều có thể bị thu hồi giữa chừng.

### Tăng version phải nguyên tử

Tránh mô hình read-modify-write không khóa:

~~~text
current = readVersion(user)
writeVersion(user, current + 1)
~~~

Hai request đồng thời có thể cùng đọc 4 và cùng ghi 5, làm mất một lần tăng. Dùng atomic increment, optimistic locking có retry hoặc transaction/row lock phù hợp.

Version phải tăng đơn điệu. Không reset hoặc tái sử dụng version khi xóa rồi tạo lại tài khoản; dùng định danh user bất biến và trạng thái bảo mật mới có epoch riêng để tránh token cũ vô tình khớp lại.

## 12. Các trường hợp nên tăng version hoặc revoke session

| Sự kiện | Phạm vi thường phù hợp | Ghi chú |
| --- | --- | --- |
| Đổi mật khẩu theo yêu cầu người dùng | User version hoặc các session khác theo policy | Một số hệ thống giữ phiên hiện tại; phải quy định rõ |
| Đặt lại mật khẩu do nghi bị chiếm quyền | User version và revoke mọi session/refresh family | Thường cần thu hồi toàn bộ credential cũ |
| Tài khoản bị khóa/vô hiệu hóa | User status + user version | Không chỉ dựa vào version nếu account inactive |
| Đăng xuất một thiết bị | Session status/version | Giữ các thiết bị khác hoạt động |
| Đăng xuất mọi thiết bị | User version và revoke toàn bộ session | Cần đồng bộ trạng thái cache |
| Phát hiện refresh token reuse | Revoke token family hoặc session; có thể tăng user version tùy mức độ | Phụ thuộc chính sách AS |
| Vai trò/quyền quan trọng thay đổi | Tăng user version nếu token chứa quyền cũ không được phép tiếp tục | Hoặc đọc quyền hiện tại ở authorization layer |
| Khóa ký JWT bị compromise | Xử lý theo key/issuer-wide policy | User version không đủ để thu hồi token của mọi user ký bằng khóa đó |
| Người dùng đóng một session cụ thể | Revoke session | Không cần tăng toàn user version |

Không phải mọi thay đổi profile đều bắt buộc tăng version. Cần đánh giá liệu token cũ có còn được phép giữ quyền đã cấp hay không và chọn phạm vi thu hồi nhỏ nhất đáp ứng yêu cầu bảo mật.

## 13. Các lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tăng version nhưng không kiểm tra ở resource server | Token cũ vẫn được chấp nhận tới exp | Kiểm tra version trong mọi luồng xác minh cần thu hồi theo nhóm |
| Kiểm tra version trước khi xác minh chữ ký | Token giả có thể điều khiển user/session lookup | Chỉ dùng claims sau khi chữ ký và profile hợp lệ |
| Chỉ kiểm tra access token, bỏ qua refresh token | Refresh token cũ tiếp tục cấp access token mới | Kiểm tra version và trạng thái family ở refresh endpoint |
| Dùng một user version cho đăng xuất riêng thiết bị | Thu hồi cả các thiết bị khác ngoài ý muốn | Dùng session version/status |
| Dùng session version nhưng không ràng buộc session với sub | Token có thể tham chiếu session của user khác | Kiểm tra session.user_id bằng subject đã xác minh |
| Mặc định claim thiếu bằng 0 | Token cũ hoặc token sai profile có thể được chấp nhận | Bắt buộc claim theo profile hoặc xử lý migration rõ ràng |
| Cho client tự gửi version mong muốn | Client có thể cố vượt trạng thái revoke | Version chỉ do server quản lý |
| Dùng >= không có policy | Token version tương lai có thể được chấp nhận | Ưu tiên exact match hoặc định nghĩa minimum-version semantics chặt chẽ |
| Cache version quá lâu | Token cũ còn được chấp nhận sau revoke | Đặt revocation-latency objective và TTL tương ứng |
| Không invalidate cache giữa các node/region | Một số node tiếp tục dùng version cũ | Event invalidation, TTL dự phòng và consistency policy |
| Tăng version bằng read-modify-write không nguyên tử | Mất lần tăng khi có concurrency | Atomic increment hoặc transaction có concurrency control |
| Reset version khi xóa/tạo lại user | Token cũ có thể khớp lại nếu định danh bị tái sử dụng | Giữ ID bất biến/epoch riêng, không tái sử dụng trạng thái |
| Xem versioning là thay thế hoàn toàn jti/introspection | Không đáp ứng nhu cầu thu hồi riêng lẻ hoặc tức thời | Kết hợp cơ chế theo độ hạt cần thiết |
| Tuyên bố logout tức thời dù có cache/request đang chạy | Kỳ vọng bảo mật sai | Công bố và đo revocation latency thực tế |

## 14. Bộ ca kiểm thử

Giả sử user user-4821 có token_version = 4, session sess-A và sess-B đều active với session_version = 1.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Token user version 4, session A version 1, mọi kiểm tra khác hợp lệ | **Chấp nhận** |
| Tăng user version lên 5, dùng token cũ version 4 | **Từ chối** |
| Tăng user version lên 5, phát hành token mới version 5 sau xác thực | **Có thể chấp nhận** |
| Tăng session A version lên 2, token session A version 1 | **Từ chối** |
| Revoke session A, token session B còn active và version khớp | **Chấp nhận** nếu các kiểm tra khác đạt |
| Token thiếu token_version trong profile bắt buộc claim này | **Từ chối** |
| token_version là string "4" thay vì integer | **Từ chối** |
| Token version cao hơn current version trong profile exact-match | **Từ chối** |
| Token có chữ ký không hợp lệ nhưng chứa version khớp | **Từ chối trước khi tin claim** |
| Token có subject A nhưng session thuộc user B | **Từ chối** |
| Session đã hết hạn hoặc status revoked | **Từ chối** |
| Refresh token version cũ sau khi user version tăng | **Từ chối refresh** |
| Refresh token version đúng nhưng family đã revoked/reuse detected | **Từ chối refresh** |
| Cache còn version cũ trong TTL sau revoke | Hành vi phải khớp revocation-latency policy; test xác nhận thời gian tối đa |
| Invalidation event thất lạc | TTL/authoritative refresh vẫn phải đưa cache về version mới trong giới hạn |
| Hai yêu cầu revoke đồng thời | Atomic increment không được làm mất lần cập nhật |
| Token được phát hành đồng thời với revoke | Không được tạo token có version cũ được chấp nhận sau khi trạng thái mới có hiệu lực |
| User bị disabled nhưng version vẫn khớp | **Từ chối** do account status |
| Version bị reset về giá trị cũ sau khi tái tạo user | Test phải ngăn ID/version reuse làm token cũ hợp lệ lại |

Kiểm thử nên bao gồm cả nhiều node và nhiều region nếu hệ thống phân tán. Đo thời gian từ lúc commit revoke tới lúc mọi resource server từ chối token cũ; đây là bằng chứng thực tế cho mục tiêu thu hồi.

## 15. Ghi nhớ

- Token version là epoch do server quản lý; JWT mang version tại thời điểm phát hành để server so sánh với trạng thái hiện tại.
- User token version tăng sẽ vô hiệu hóa nhóm token của toàn tài khoản; session version/status cho phép thu hồi riêng một phiên hoặc thiết bị.
- Version claim là dữ liệu đáng tin chỉ sau khi chữ ký và token profile được xác minh.
- Refresh endpoint cũng phải kiểm tra version và session/family state; nếu không, refresh token cũ có thể tạo access token mới.
- Version check cần trạng thái online hoặc cache; TTL và replica lag quyết định độ trễ thu hồi.
- Unknown/missing version, user không tồn tại/disabled hoặc session không active phải được xử lý theo policy rõ ràng, thường là từ chối.
- Tăng version phải nguyên tử, đơn điệu và không được reset/reuse.
- Versioning không thay thế mọi cơ chế: jti denylist phù hợp thu hồi từng token, introspection phù hợp kiểm tra trạng thái tập trung, còn access token ngắn hạn giới hạn cửa sổ rủi ro.
- Không thể bảo đảm thu hồi tức thời nếu cache, replica hoặc request đang xử lý vẫn dùng trạng thái cũ; cần định nghĩa và đo revocation latency.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim, thời hạn và cấu trúc JWT; token version/session version là quy ước riêng của profile ứng dụng.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token tại Authorization Server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): truy vấn trạng thái và metadata của token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation và phát hiện reuse.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo issuer, thuật toán và ngữ cảnh.
