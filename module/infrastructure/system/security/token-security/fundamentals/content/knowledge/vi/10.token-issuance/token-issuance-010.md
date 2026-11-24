# Xử lý request cấp token lặp lại

## 1. Vì sao cùng một request cấp token có thể xuất hiện nhiều lần?

Trong chương **Token issuance** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, authorization server (AS) phát hành access token và, ở những luồng phù hợp, refresh token sau khi xác thực và kiểm tra quyền. Token có thể là JWT hoặc opaque; resource server dùng JWT/JWKS hoặc introspection để xác minh issuer, audience, thời hạn, scope và trạng thái. Trước cả bước kiểm tra token ở API, quá trình **cấp token** đã có một bài toán khó: **điều gì xảy ra khi cùng một yêu cầu đến token endpoint hai lần?**

Ví dụ hệ thống `orders-worker` cần token `aud=inventory-api`, `scope=inventory.read`. Client POST đến token endpoint, AS phát hành token, nhưng kết nối bị ngắt **sau khi AS commit kết quả, trước khi client nhận response**. Client không biết request đã thành công hay chưa và có thể thử lại. Một tình huống khác: hai instance cùng dùng refresh token và cùng xin làm mới. Cũng có kẻ tấn công cố ý gửi lại authorization code hoặc refresh token lấy được.

Những tình huống bề ngoài đều là “request lặp lại”, nhưng phải xử lý **khác nhau tùy grant và credential**:

- Một request `client_credentials` lặp lại có thể dẫn đến **hai access token hợp lệ**; không có bảo đảm chuẩn rằng hai response sẽ giống nhau.
- Một `authorization_code` **chỉ được đổi token một lần**; request thứ hai với code đã dùng phải bị từ chối.
- Một refresh token thuộc cơ chế **rotation** thường chỉ được sử dụng cho **một lần đổi**, sau đó được thay bằng refresh token mới; gửi lại bản cũ có thể bị xem là hành vi replay.
- Với **device authorization grant**, việc polling token endpoint nhiều lần trước khi người dùng chấp thuận là một phần **được dự kiến trong giao thức**, nhưng phải tuân thủ chu kỳ polling và lỗi `slow_down`.

Do đó, câu trả lời an toàn không phải là “mọi request POST phải idempotent” hay “mọi request lặp lại đều là tấn công”. Phải xét **grant type**, trạng thái credential và kết quả đã commit tại AS.

### Mục tiêu sau bài học

1. Phân biệt **retry**, **duplicate**, **concurrent request**, **idempotency** và **credential replay**.
2. Quyết định khi nào được retry token request và khi nào phải bắt đầu lại luồng cấp quyền.
3. Giải thích yêu cầu **single-use** của authorization code và refresh token rotation.
4. Thiết kế **single-flight**, lưu token an toàn và cơ chế cập nhật nguyên tử để tránh refresh race.
5. Thiết kế AS xử lý token issuance đúng khi có nhiều node và sự cố mạng.
6. Kiểm thử cấp token lặp lại mà vẫn bảo vệ scope, audience, key material và quyền của người dùng/service.

## 2. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Ví dụ | Cách xử lý điển hình |
| --- | --- | --- | --- |
| **Retry** | Client chủ động thử lại sau lỗi hoặc không nhận response | HTTP timeout khi xin token | Chỉ retry theo ngữ nghĩa grant và lỗi; có giới hạn |
| **Duplicate request** | Hai request có nội dung giống hoặc gần giống nhau | User nhấn nút đăng nhập hai lần | Client giảm trùng lặp, AS bảo vệ credential dùng một lần |
| **Concurrent request** | Hai request đến gần đồng thời, chưa request nào hoàn tất | Hai node cùng dùng refresh token cũ | Đồng bộ phía client; AS kiểm tra/cập nhật nguyên tử |
| **Idempotency** | Thao tác lặp lại tạo hiệu ứng tương đương một thao tác | Hệ thống có hỗ trợ `Idempotency-Key` riêng | Không mặc định token endpoint OAuth có khả năng này |
| **Replay** | Sử dụng lại credential hoặc proof để thực hiện quyền không được phép | Kẻ tấn công đổi lại authorization code đã dùng | Từ chối; phát hiện và ứng phó theo policy |
| **Refresh token rotation** | Cấp refresh token mới và vô hiệu bản trước sau khi dùng | `RT-1 → RT-2` | Bảo vệ chuỗi thay thế và xử lý reuse |
| **Token reuse tại resource server** | Gửi lại access token trong nhiều API request hợp lệ | Gọi GET nhiều lần bằng bearer access token | Bình thường nếu token còn hiệu lực và đúng audience/scope |

**Lặp request cấp token khác với lặp request dùng access token.** Bearer access token thông thường được sử dụng nhiều lần tới lúc hết hạn hoặc bị thu hồi; không áp yêu cầu “access token chỉ dùng một lần” cho toàn bộ OAuth nếu AS/RS không thiết kế như vậy.

### 2.1. “Cùng request” phải được định nghĩa cẩn thận

Hai token request có cùng `client_id` và `scope` chưa chắc là cùng **logical operation**: chúng có thể thuộc hai người dùng, hai tenant, hai audience, hai khóa DPoP hoặc hai phiên đăng nhập khác nhau.

Ví dụ:

~~~text
Request A: issuer=AS-1, client=orders-worker, audience=inventory-api,
           scope=inventory.read, grant=client_credentials

Request B: issuer=AS-1, client=orders-worker, audience=payments-api,
           scope=payments.read, grant=client_credentials
~~~

Nếu cache/single-flight chỉ khóa theo `client_id`, client có thể dùng nhầm access token của `inventory-api` để gọi `payments-api`. Khóa đồng bộ/cache phải bao gồm **đủ ngữ cảnh xác thực và ủy quyền** để không trộn token.

## 3. Điều gì thực sự xảy ra tại token endpoint?

Một token request đi qua các bước logic: xác thực client khi cần, xác minh grant/credential, đánh giá chính sách, quyết định scope/audience/TTL, phát hành token và ghi trạng thái. Với grant có credential dùng một lần, **kiểm tra và tiêu thụ credential phải là một thao tác nguyên tử về mặt logic**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant S as Kho trạng thái token/grant
    C->>AS: POST /token
    AS->>AS: Xác thực client, grant, audience và scope
    AS->>S: Kiểm tra + cập nhật trạng thái grant nguyên tử
    S-->>AS: Commit thành công
    AS-->>C: Access token (+ refresh token nếu có)
    Note over C,AS: Response có thể mất sau khi server đã commit
    C->>AS: POST /token lại do timeout
    AS->>S: Kiểm tra trạng thái đã cập nhật
    S-->>AS: Credential đã dùng / bị thay thế
    AS-->>C: Kết quả theo grant: reject hoặc xử lý idempotency riêng
~~~

Điểm khó là **client không thể biết chắc AS đã commit hay chưa chỉ dựa vào timeout**. Khi request POST thất bại do mạng, ba khả năng đều có thể tồn tại:

1. Request chưa tới AS.
2. AS nhận request nhưng chưa hoàn tất hoặc đã rollback.
3. AS đã commit, tạo token và gửi response nhưng response bị mất.

Trường hợp 1 và 2 có thể cho phép client thử lại tùy grant; trường hợp 3 biến retry thành **sử dụng lại credential đã bị tiêu thụ** nếu đó là authorization code hoặc refresh token rotation.

### 3.1. Idempotency của HTTP POST không phải thuộc tính mặc định của OAuth

HTTP POST đến `/token` là một thao tác có thể **tạo trạng thái bảo mật mới**. OAuth 2.0 **không định nghĩa một `Idempotency-Key` chung** và cũng không yêu cầu token endpoint trả lại cùng token cho mọi POST trùng nội dung. Vì vậy:

- Không coi response của hai token request giống nhau là bắt buộc.
- Không retry tự động mọi HTTP 5xx/timeout một cách không giới hạn.
- Không dùng trùng `authorization_code` hoặc refresh token đã rotate rồi yêu cầu AS “bỏ qua cảnh báo replay”.
- Chỉ dùng cơ chế idempotency của một AS cụ thể nếu **AS thực sự công bố và bảo đảm** hợp đồng đó.

## 4. Ma trận hành vi theo từng OAuth grant

| Loại request tại token endpoint | Credential có tính dùng một lần? | Khi gửi lần thứ hai | Hành vi client nên chọn |
| --- | --- | --- | --- |
| `authorization_code` + PKCE | **Có:** authorization code phải single-use | Code đã dùng phải bị từ chối (`invalid_grant` thường gặp) | Không lặp vô hạn; xử lý kết quả callback và bắt đầu lại authorization flow nếu mất kết quả |
| `refresh_token` **có rotation** | Bản refresh token cũ được thay sau lần dùng thành công | Reuse có thể kích hoạt phát hiện replay và revoke chuỗi token | Đồng bộ refresh; lưu cặp token mới nguyên tử; nếu trạng thái không rõ, xử lý theo policy AS |
| `refresh_token` **không rotation** | Không nhất thiết là một lần; phụ thuộc AS | Có thể cấp nhiều access token mới nếu grant còn hợp lệ | Hạn chế đồng thời, bảo vệ refresh token, không tự giả định idempotent |
| `client_credentials` | Client credential thường dùng được nhiều lần | AS có thể cấp thêm token độc lập | Cache token hợp lệ, single-flight và backoff khi có lỗi |
| `urn:ietf:params:oauth:grant-type:token-exchange` | Phụ thuộc profile và loại subject token | Có thể tạo token mới; policy/credential một lần có thể thay đổi kết quả | Không mặc định subject token được replay; tuân theo STS/AS |
| `urn:ietf:params:oauth:grant-type:device_code` | `device_code` dùng cho polling theo RFC 8628 | Poll nhiều lần có chủ đích khi chưa được chấp thuận | Tuân thủ `interval`, `authorization_pending`, `slow_down`; dừng khi thành công/hết hạn |

**Lưu ý phạm vi:** RFC 6749 yêu cầu authorization code chỉ dùng một lần; refresh-token rotation là biện pháp bảo vệ được tiêu chuẩn bảo mật OAuth khuyến nghị trong những điều kiện phù hợp và hiện diện ở nhiều AS, nhưng **không được mặc định mọi AS đều rotate**. Client phải biết hợp đồng AS đang sử dụng.

## 5. Authorization Code + PKCE: request lặp lại phải xử lý thế nào?

Authorization Code flow có hai loại request: yêu cầu ủy quyền và yêu cầu đổi **authorization code** ở token endpoint. Một authorization code được ràng buộc với client, redirect URI và các điều kiện luồng như PKCE; nó phải có thời hạn ngắn và **không được dùng nhiều hơn một lần**.

### 5.1. User tải lại callback hoặc hai thread cùng đổi code

Ví dụ callback:

~~~text
GET /callback?code=CODE-123&state=STATE-123
~~~

Client gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE-123&client_id=web-client&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&code_verifier=<pkce-verifier>
~~~

Nếu hai request token cùng mang `CODE-123`, AS phải bảo đảm **tối đa một lần đổi code thành công**. Hai node AS không thể cùng đọc trạng thái `UNUSED` rồi cùng phát token. Một cách triển khai là kiểm tra và chuyển trạng thái `UNUSED → CONSUMED` bằng transaction/CAS trong kho chia sẻ.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Callback handler A
    participant B as Callback handler B
    participant AS as AS / Token endpoint
    participant DB as Kho authorization code
    par Hai request cùng code
        A->>AS: Redeem CODE-123
        B->>AS: Redeem CODE-123
    end
    AS->>DB: Atomic claim CODE-123
    DB-->>AS: Chỉ một request nhận quyền claim
    AS-->>A: Một request có thể nhận token
    AS-->>B: Request còn lại bị từ chối
~~~

Sơ đồ nhấn mạnh nguyên tắc **chỉ một winner**; trong thực tế request A hoặc B đều có thể là winner. Việc phát hành token và ghi trạng thái code cần phối hợp giao dịch để tránh trạng thái nửa chừng, đồng thời không đánh đổi single-use lấy khả năng trả response sau timeout.

### 5.2. Nếu response đầu tiên bị mất thì sao?

Trường hợp AS đã đổi code và cấp token nhưng client bị mất response, client không nên mong dùng lại code để nhận cùng token. RFC 6749 quy định code chỉ được dùng một lần; khi AS phát hiện code bị dùng nhiều lần, nó phải từ chối và **nên thu hồi token đã cấp dựa trên code đó nếu khả thi**.

Phía client:

1. Lưu một trạng thái xử lý callback theo phiên `state` và code, ngăn nhiều thread cùng gửi request.
2. Khi nhận token thành công, **lưu kết quả phiên/token an toàn trước khi cho luồng callback hoàn thành**.
3. Nếu callback bị gửi lần nữa sau khi đã xử lý thành công, dùng **trạng thái phiên đã lưu** để điều hướng người dùng, không POST lại cùng code.
4. Nếu không có kết quả hợp lệ và code bị từ chối (`invalid_grant`), hủy transaction đăng nhập lỗi và **bắt đầu một authorization request mới** theo giao thức.

Không ghi `code`, `code_verifier`, access token hoặc refresh token vào URL log, distributed trace và thông báo lỗi. `state` và PKCE bảo vệ những rủi ro khác (CSRF/code interception); chúng không tạo ra quyền dùng code nhiều lần.

### 5.3. Phía AS khi gặp code đã tiêu thụ

AS cần từ chối mà không tiết lộ token đã cấp trước đó; phát hiện và ghi nhận reuse có kiểm soát. Khi phù hợp, thực hiện chính sách thu hồi các token đã phát hành từ code bị dùng nhiều lần theo RFC 6749. Cần phân biệt double-click hợp lệ và tấn công để hỗ trợ điều tra, **nhưng không nới yêu cầu single-use** chỉ để giảm lỗi người dùng.

## 6. Refresh token rotation: race condition nguy hiểm nhất

Refresh token là credential cho phép client xin access token mới từ AS theo grant đã được cấp. Với **rotation**, AS cấp refresh token mới trong mỗi lần refresh hợp lệ, vô hiệu refresh token cũ, đồng thời ghi quan hệ giữa các token để phát hiện reuse.

~~~text
Ban đầu:   access=A1, refresh=RT-1
Refresh 1: dùng RT-1 → nhận access=A2, refresh=RT-2
Refresh 2: dùng RT-2 → nhận access=A3, refresh=RT-3
~~~

Nếu hai request đồng thời sử dụng `RT-1`:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Browser tab A
    participant B as Browser tab B
    participant AS as Authorization Server
    A->>AS: refresh_token=RT-1
    B->>AS: refresh_token=RT-1
    AS->>AS: Đổi RT-1 → RT-2 (atomic)
    AS-->>A: access=A2, refresh=RT-2
    AS->>AS: Phát hiện RT-1 đã sử dụng
    AS-->>B: invalid_grant / replay handling
    Note over A,B: Tùy policy AS, reuse có thể ảnh hưởng cả RT-2
~~~

Ở một số AS, request thứ hai bị coi là reuse đáng ngờ và có thể dẫn đến **thu hồi refresh token đang hoạt động hoặc cả token family**. Tại AS khác, phản hồi có thể khác hoặc có khoảng dung sai rất ngắn được thiết kế riêng. **Không có một hành vi rotation/replay duy nhất mà mọi nhà cung cấp OAuth bắt buộc trả về cho mọi race.**

### 6.1. Phân biệt ba nguy cơ khi refresh đồng thời

1. **Refresh reuse:** Cả hai request dùng RT cũ; AS có thể kích hoạt phát hiện replay.
2. **Lost update ở client:** Request A lưu RT mới, nhưng request B ghi đè bằng token cũ hoặc response đến sau.
3. **Cross-session/tenant mix-up:** Cache hoặc lock chỉ khóa theo client ID khiến token của user A ghi đè token của user B.

Mỗi nguy cơ cần cơ chế riêng: AS rotation với trạng thái nguyên tử, client **single-flight**, và token store có version/CAS theo đúng session/subject/audience.

### 6.2. Client nên đồng bộ thế nào?

Trong **một process**, các request cần refresh cho cùng một phiên nên dùng **single-flight**: chỉ một tác vụ gọi token endpoint, các tác vụ còn lại chờ **cùng kết quả** thay vì gửi request mới.

Trong **nhiều process hoặc nhiều Pod**, khóa trong memory không đủ. Có thể sử dụng distributed coordination theo user/session/grant, hoặc cơ chế token store với version/CAS và lock/fencing được thiết kế chắc chắn.

Quy trình:

1. Đọc bản ghi token trong kho an toàn, gồm `access_token`, `refresh_token`, `expires_at` và `version`.
2. Nếu access token còn hiệu lực đủ lâu, sử dụng luôn.
3. Nếu sắp hết hạn, cố lấy quyền refresh cho **đúng grant/session**, rồi đọc lại bản ghi.
4. Nếu một instance khác đã hoàn tất refresh, dùng bản ghi mới; **không gửi RT cũ**.
5. Nếu mình là worker refresh, gọi AS đúng một lần theo policy; khi thành công, lưu **access token và refresh token mới như một cặp** với điều kiện version phù hợp.
6. Phát tín hiệu/hoàn tất tác vụ để các request còn lại dùng bản ghi mới. Khi lỗi `invalid_grant`, không thử RT cũ nhiều lần.

Không dùng lock hết TTL quá sớm rồi cho worker khác refresh khi request đầu vẫn đang chờ. Với distributed lock, cần xử lý lease/fencing, thời gian chết node và recovery khi tiến trình mất response để không tạo hai tác vụ cùng dùng RT cũ.

### 6.3. Race ở phía AS vẫn phải được xử lý

Dù client triển khai single-flight, AS vẫn phải bảo vệ token state bằng phép kiểm tra/cập nhật nguyên tử trên **các node AS**. Không dựa vào việc “client chuẩn sẽ không bao giờ gửi hai lần”: attacker hoặc retry từ proxy luôn có thể tạo cạnh tranh.

Một update có điều kiện mang ý nghĩa:

~~~text
UPDATE refresh_tokens
SET status = 'CONSUMED'
WHERE token_id = :id
  AND status = 'ACTIVE'
  AND client_binding = :client
  AND expires_at > :now
RETURNING family_id;

Nếu không update được đúng 1 bản ghi: từ chối theo replay policy.
Nếu thành công: phát hành và commit token thay thế như một transaction.
~~~

Đây là **pseudo-SQL** để diễn tả yêu cầu single-winner, không phải cấu trúc schema bắt buộc. Việc cập nhật token cũ, tạo token mới, ghi token family và bảo đảm nhất quán khi crash cần được thiết kế chung theo storage architecture. Chỉ có câu UPDATE đơn lẻ chưa đủ bảo đảm an toàn nếu issuance ở bước khác không được commit nhất quán.

### 6.4. “Grace period” có giải quyết được retry không?

Một số AS cung cấp cơ chế **reuse interval/overlap** rất ngắn để giảm lỗi khi client mất response hoặc có concurrent refresh. Đây là **lựa chọn triển khai riêng**, không phải quy tắc OAuth phổ quát. Nếu nới quá rộng, attacker có RT cũ có thêm thời gian đổi token; nếu trả lại token đã cấp, AS cần ràng buộc request đúng client/sender, ngữ cảnh grant, idempotency key và chính sách bảo mật.

Đội phát triển phải cân nhắc mục tiêu UX với yêu cầu replay detection và biết rõ AS đang làm gì. **Không tự thêm grace period không được chứng minh an toàn** và không vô hiệu hóa reuse detection chỉ để che lỗi refresh race ở client.

## 7. Client Credentials: tránh phát hành token không cần thiết

Grant `client_credentials` thường dành cho confidential client hoặc machine identity truy cập API bằng quyền của chính client. Khác authorization code, credential của client **không phải bằng chứng dùng một lần**: client được phép xác thực lại để xin access token khi cần.

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

Nếu client POST hai lần gần nhau, AS **có thể cấp hai access token khác nhau**, với `jti`, `iat`, `exp` hoặc bytes JWT khác nhau. Đây không tự động là lỗ hổng replay. Nhưng gửi request không cần thiết làm tăng tải và số token còn hiệu lực, khiến giám sát, thu hồi và giới hạn tần suất khó hơn.

### 7.1. Cache access token theo đúng ngữ cảnh

Với `orders-worker` chỉ gọi `inventory-api`, client có thể cache access token theo khóa logic:

~~~text
(
  trusted_issuer,
  client_registration,
  principal_or_workload_identity,
  tenant,
  audience_or_resource,
  normalized_granted_scope,
  token_binding_identity
)
~~~

Đây là gợi ý các chiều phân biệt; khóa thực tế phụ thuộc framework/token profile. **Không** cache access token của Alice rồi trả cho Bob chỉ vì cùng scope. Không dùng token `aud=inventory-api` cho `payments-api`. Với DPoP/mTLS, token có thể gắn với một khóa/chứng chỉ cụ thể nên cache phải phân vùng theo danh tính khóa tương ứng.

Nên tái sử dụng access token còn hiệu lực và đúng resource, có khoảng dự phòng nhỏ trước `exp`, rồi **một tác vụ** lấy token mới. Không mặc định client credentials grant có refresh token: RFC 6749 quy định refresh token **SHOULD NOT** được cấp trong phản hồi grant này; client có thể xác thực lại bằng credential của nó.

### 7.2. Single-flight cho nhiều request đồng thời

Giả sử 100 request tới `orders-worker` ngay khi token đã hết hạn. Nếu mỗi thread đều POST `client_credentials`, AS có thể phải xử lý 100 lần xác thực, ký JWT và ghi audit. Single-flight gộp các lời gọi **cùng mục đích cấp token**:

~~~mermaid
flowchart TD
    A["100 request cần access token"] --> B{"Có token cache còn hiệu lực?"}
    B -->|"Có"| C["Dùng token đã cache"]
    B -->|"Không"| D{"Đã có request lấy token đang chạy?"}
    D -->|"Có"| E["Chờ cùng kết quả, không POST thêm"]
    D -->|"Không"| F["Một worker POST /token"]
    F --> G{"Thành công?"}
    G -->|"Có"| H["Lưu token + expires_at đúng key"]
    H --> E
    G -->|"Lỗi"| I["Phân loại lỗi và backoff có giới hạn"]
~~~

Single-flight giảm tải và trùng lặp **ở phía client**. Nó không thay thế giới hạn tần suất và chính sách bảo mật **ở AS**.

## 8. Khi nào được retry một token request?

“Retry tất cả lỗi HTTP” là chính sách nguy hiểm, đặc biệt với credential dùng một lần. Nên phân loại theo **loại grant**, **kết quả HTTP/OAuth** và **khả năng request đầu đã commit**.

| Kết quả hoặc sự cố | Ý nghĩa có thể có | Hướng xử lý |
| --- | --- | --- |
| `200 OK` với response hợp lệ | Request cấp token thành công | Lưu token/cặp token mới an toàn, không tự gửi lại |
| `invalid_client` hoặc `401` vì client authentication | Client secret/assertion/chứng chỉ không hợp lệ | Sửa cấu hình/credential; không retry liên tục cùng credential |
| `invalid_grant` với authorization code | Code hết hạn, đã dùng, sai redirect/PKCE hoặc không hợp lệ | Không lặp cùng code; xử lý phiên và bắt đầu authorization flow mới khi phù hợp |
| `invalid_grant` với refresh token | Refresh token hết hạn, thu hồi, bị rotate hoặc không hợp lệ | Ngừng dùng token đó; tuân thủ chính sách re-auth/recovery của AS |
| `invalid_scope`/`unauthorized_client` | Không đủ quyền xin scope/grant này | Sửa request/quyền bằng luồng hợp lệ; không backoff rồi thử mãi |
| `429 Too Many Requests` | Bị rate limit | Tôn trọng `Retry-After` khi có, giảm concurrency; chỉ retry nếu an toàn theo grant |
| `503`, một số `5xx` | AS gặp sự cố hoặc proxy lỗi | Backoff và theo dõi; **kết quả cấp token vẫn có thể không rõ** |
| Timeout trước khi chắc chắn gửi request | Có thể AS chưa nhận, nhưng client không nên tự kết luận | Chỉ retry theo bảo đảm transport và grant |
| Timeout/connection reset sau khi gửi POST | AS có thể đã commit, response bị mất | Xem là **unknown outcome**; không retry mù quáng với credential single-use |
| JSON response thiếu field hoặc không xác thực TLS | Không có kết quả đáng tin | Không sử dụng token; ghi lỗi an toàn và áp dụng recovery tương ứng |

`429` và header `Retry-After` là cơ chế HTTP phổ biến, **không phải mã lỗi OAuth bắt buộc** của token endpoint. Client phải tuân thủ hợp đồng nhà cung cấp và giới hạn số lần retry. Việc máy chủ trả `500` không tự chứng minh phát hành token đã rollback.

### 8.1. Retry policy theo grant

**Với client credentials:**

- Nếu request thất bại tạm thời, retry số lần ít với exponential backoff, jitter và tổng thời gian chờ tối đa.
- Cache kết quả khi thành công và phân phối cho các request chờ cùng token.
- Kiểm tra lại `aud`, `scope`, `expires_in` và policy trước khi dùng; AS có thể cấp scope hẹp hơn yêu cầu.

**Với authorization code:**

- Bảo vệ callback khỏi double-submit và cố gắng một lần đổi code theo transaction.
- Nếu kết quả bị mất, không kỳ vọng lặp code sẽ trả cùng token.
- Nếu nhận `invalid_grant` hoặc mất trạng thái, hủy transaction lỗi và hướng người dùng thực hiện lại authorization.
- Chỉ dùng recovery/idempotency đặc thù nếu AS có cơ chế được thiết kế, công bố và không phá single-use.

**Với refresh token rotation:**

- Trước hết loại bỏ concurrent refresh bằng single-flight/distributed coordination.
- Nếu request đầu có unknown outcome, **không** cho mọi worker retry với refresh token cũ.
- Nếu token store đã nhận refresh token mới từ worker khác, tiếp tục dùng bản mới.
- Nếu không thể khôi phục trạng thái, xử lý theo cơ chế của AS, thường yêu cầu đăng nhập lại hoặc cấp quyền mới; không vô hiệu reuse detection một cách tùy tiện.

### 8.2. Exponential backoff và jitter

Ví dụ với request **được phép retry theo grant**:

~~~text
attempt 1: gọi token endpoint
attempt 2: chờ khoảng 200-500 ms ngẫu nhiên
attempt 3: chờ khoảng 500-1000 ms ngẫu nhiên
stop: hết giới hạn số lần hoặc deadline tổng thể
~~~

Các giá trị chỉ minh họa, cần dựa trên quota AS và SLA của ứng dụng. Jitter làm giảm **thundering herd** khi hàng nghìn instance cùng gặp AS outage. Không retry vô hạn, không bỏ qua rate limit, và không gửi credential nhạy cảm vào logs khi ghi retry diagnostics.

## 9. Idempotency-Key: chỉ dùng khi AS hỗ trợ rõ ràng

Một số hệ thống đưa vào cơ chế idempotency riêng, ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Idempotency-Key: 3f7f7c8d-7fb2-4e39-b699-8d2dd56a2a1b
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

Đây là **header giả định của một API có hợp đồng mở rộng**, không phải header bắt buộc hay tiêu chuẩn chung của OAuth 2.0 token endpoint. Nếu AS bỏ qua header, hai POST vẫn có thể tạo hai token khác nhau.

### 9.1. Nếu thiết kế idempotency cho token issuance

Một triển khai có chủ đích cần:

1. **Ràng buộc key với client đã xác thực:** Không để client A tra lại kết quả token của client B bằng một key đoán được.
2. **Ràng buộc key với request fingerprint:** Phân biệt grant type, token endpoint/issuer, resource/audience, scope, subject/grant, token binding và những tham số quan trọng khác.
3. **Tạo key đủ ngẫu nhiên, giới hạn TTL:** Không dùng một key cố định suốt vòng đời client.
4. **Ghi nhận request đang xử lý nguyên tử:** Hai request cùng key phải chỉ có một thao tác phát hành được commit; request khác có thể nhận kết quả đã lưu hoặc trạng thái “đang xử lý” theo hợp đồng.
5. **Bảo vệ cached response:** Nếu lưu lại access/refresh token để trả cùng kết quả, phải mã hóa, giới hạn quyền đọc, thời hạn lưu và ràng buộc chặt client/session.
6. **Không làm vô hiệu quy tắc single-use:** Authorization code và refresh-token rotation không thể được mở rộng thành “cứ gửi lại sẽ được token” nếu phá bảo đảm ngăn replay.
7. **Kiểm tra key tái sử dụng với request khác:** Cùng key nhưng payload/binding khác phải bị từ chối, không trả token của request đầu.

Ở nơi nhạy cảm, trả lại response token lần trước đồng nghĩa **tiết lộ credential lần nữa**. Vì vậy idempotency không đơn thuần là cache HTTP response; nó là quyết định bảo mật phải được AS chứng minh cho đúng grant/client/session và phải có khả năng thu hồi khi cần.

### 9.2. Idempotency key khác replay nonce

| Thuộc tính | Idempotency key (nếu AS hỗ trợ) | `jti`/nonce chống replay |
| --- | --- | --- |
| Mục tiêu | Nhận diện cùng logical operation để tránh hiệu ứng lặp | Phát hiện bằng chứng xác thực/proof bị phát lại |
| Nơi sử dụng | Thường ở API/AS theo hợp đồng riêng | JWT client assertion, DPoP proof hoặc cơ chế có quy định |
| Khi thấy lại | Có thể trả kết quả cũ, in-progress hoặc conflict | Thường từ chối proof/credential đã dùng, theo profile |
| Có quyền thay đổi single-use code/RT? | Không tự động | Không; phải tuân thủ rule của credential |

Không lấy `jti` của JWT rồi dùng làm idempotency key chung; hai trường có **ngữ nghĩa khác nhau**. Với DPoP, proof mới cho request mới cần thỏa quy định `htu`, `htm`, `iat`, `jti`, nonce/`ath` tương ứng. Khi token endpoint và client dùng DPoP, phải giữ ràng buộc của access token với khóa DPoP; không cache và trả token ràng buộc khóa cho một client/key khác.

## 10. Phía authorization server: trạng thái nguyên tử và phòng chống replay

Một AS an toàn phải đưa ra **kết quả nhất quán** ngay cả khi nhiều node nhận cùng credential đồng thời.

### 10.1. Mô hình trạng thái cho credential dùng một lần

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> CONSUMED: Redeem thành công (atomic)
    ISSUED --> EXPIRED: Quá hạn
    ISSUED --> REVOKED: Thu hồi
    CONSUMED --> REPLAY_DETECTED: Lại dùng credential cũ
    EXPIRED --> [*]
    REVOKED --> [*]
    REPLAY_DETECTED --> [*]
~~~

Đây là mô hình logic cho authorization code hoặc refresh token **được thiết kế single-use**. Một refresh token không rotate sẽ có vòng đời khác; token exchange hay device polling có state machine riêng. Các trạng thái nội bộ có thể khác nhau, nhưng trạng thái đã tiêu thụ không được tự hồi sinh do retry.

AS cần:

- **Kiểm tra binding:** Client ID và client authentication, redirect URI/PKCE cho authorization code, audience/resource, scope, session và sender-constrained key khi có.
- **Atomicity:** Chỉ một request được tiêu thụ authorization code hoặc RT cũ; bảo vệ trên toàn cụm AS, không chỉ khóa trong JVM.
- **Consistent storage:** Ghi trạng thái code/RT, quan hệ token family và metadata phát hành đủ để phục hồi hoặc từ chối nhất quán sau crash.
- **Expiry/revocation:** Loại bỏ grant quá hạn, đã bị revoke và token bị dùng sai mục đích.
- **Rate limiting:** Giới hạn tốc độ theo client, IP hoặc risk signals phù hợp, nhưng tránh thiết kế làm nghẽn toàn hệ thống chỉ vì một client lỗi.
- **Security telemetry:** Ghi sự kiện replay, client ID, grant type, outcome, correlation ID; không lưu raw code, refresh token, private key hoặc access token trong log.

### 10.2. Hash/fingerprint token trong kho

AS có thể lưu **hash hoặc HMAC fingerprint** của authorization code/refresh token đủ ngẫu nhiên thay vì raw credential trong bảng tra cứu, tùy token design và yêu cầu vận hành. Điều này giảm nguy cơ nếu chỉ cơ sở dữ liệu trạng thái bị lộ; với token giá trị entropy thấp hoặc cần bảo vệ chống dò ngoại tuyến, phải dùng cơ chế lưu phù hợp. Không đưa hash/fingerprint đó ra ngoài như một secret dùng gọi API.

### 10.3. Atomic consume và cấp token trong một hệ thống phân tán

Ví dụ pseudo-code:

~~~text
redeemAuthorizationCode(code, client, redirect, pkce):
    authenticateAndValidateClient()
    begin transaction
        grant = loadCodeForUpdate(code)
        require grant.status == UNUSED
        require grant.client == client
        require grant.redirectUri == redirect
        require pkceMatches(grant.challenge, pkce)
        require now < grant.expiry
        mark grant CONSUMED
        createAccessTokenRecord(boundTo = grant, audience = approvedResource)
        createRefreshTokenRecordIfPolicyAllows()
    commit transaction
    return securelySerializedTokenResponse()
~~~

Đây là mô hình khái niệm. Với JWT tự chứa, việc tạo bytes ký số có thể xảy ra trong hoặc ngoài transaction tùy kiến trúc; AS phải thiết kế **điểm commit phát hành** và quy trình recovery rõ ràng để không có hai winner hay trạng thái grant mâu thuẫn. Không thể chỉ dùng `synchronized` trên một node nếu token endpoint được scale ngang.

### 10.4. Khi phát hiện reuse refresh token

AS cần xác định chính sách phát hiện replay dựa trên mô hình rotation, family, sender constraint và threat model. Khi phát hiện RT cũ bị dùng lại sau rotation, AS có thể revoke RT đang hoạt động trong family vì không thể chắc chắn bên nào là client thật; các access token đã cấp có thể tiếp tục tồn tại đến `exp` nếu không có cơ chế thu hồi tương ứng. Ghi sự kiện bảo mật và yêu cầu client đăng nhập/cấp quyền lại khi cần.

Phải tránh **báo động giả do chính client gây ra**: một frontend gửi ba refresh request song song có thể tự làm hỏng phiên. Điều đó không có nghĩa nên bỏ rotation, mà nghĩa client phải đồng bộ và AS cần công bố rõ failure/recovery semantics.

## 11. Client-side coordination với Java/Spring

### 11.1. Tránh tự tạo token request ở mỗi HTTP call

Với Spring Security OAuth2 Client, nên sử dụng `OAuth2AuthorizedClientManager` (hoặc tiện ích tương đương của phiên bản đang dùng) để quản lý authorized client/token, kết hợp cache/coordination phù hợp. Ví dụ client credentials:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
        registration:
          inventory:
            provider: company-as
            client-id: orders-worker
            client-secret: ${ORDERS_WORKER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: inventory.read
~~~

Biến `ORDERS_WORKER_CLIENT_SECRET` là ví dụ tham chiếu secret từ môi trường; không hardcode credential vào repository. Đối với request qua proxy, cần timeout có giới hạn, che token khỏi log và cấu hình retry theo grant thay vì gắn interceptor tự động replay mọi POST.

Ví dụ manager:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService store) {

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, store);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());

    return manager;
}
~~~

`OAuth2AuthorizedClientService` lưu authorized client/token theo profile framework. Cấu hình manager giúp tái sử dụng token đã cấp, nhưng **không tự bảo đảm single-flight toàn cụm** khi nhiều node dùng cùng một refresh credential; concurrency semantics phải được xác minh theo phiên bản và token store thực tế.

### 11.2. Single-flight Java (minh họa nguyên lý)

Ví dụ dưới đây minh họa cách nhiều thread trong **một JVM** chia sẻ một tác vụ xin token cho cùng khóa:

~~~java
final class TokenSingleFlight {
    private final ConcurrentHashMap<TokenKey, CompletableFuture<TokenPair>>
            inFlight = new ConcurrentHashMap<>();

    TokenPair load(TokenKey key, Supplier<TokenPair> requestToken) {
        for (;;) {
            CompletableFuture<TokenPair> current = inFlight.get(key);
            if (current != null) {
                return current.join();
            }

            CompletableFuture<TokenPair> candidate = new CompletableFuture<>();
            if (inFlight.putIfAbsent(key, candidate) != null) {
                continue;
            }

            try {
                TokenPair result = requestToken.get();
                candidate.complete(result);
                return result;
            } catch (Throwable failure) {
                candidate.completeExceptionally(failure);
                throw failure;
            } finally {
                inFlight.remove(key, candidate);
            }
        }
    }
}
~~~

Đây là ví dụ thuật toán, giả sử `TokenKey`, `TokenPair` và `requestToken` đã được định nghĩa. `TokenKey` phải bao gồm đúng thông tin grant/subject/tenant/audience/scope/key binding; không dùng một key cho nhiều user. Với Java checked exceptions, cần thiết kế thêm mapping exception; trong ví dụ `Supplier` chỉ ném unchecked exception, nên `catch (Throwable)` là mô tả cơ chế hoàn tất future kể cả lỗi. Ở production cần lựa chọn xử lý interruption/error và không chặn event loop.

**Điểm giới hạn:** Map `inFlight` chỉ chống trùng **đang diễn ra trong một JVM**. Sau khi request hoàn tất, cần cache access token còn hạn trong store có bảo vệ; khi chạy nhiều JVM/Pod, cần distributed coordination hoặc một token broker chuyên trách. Không dùng ví dụ như bảo đảm an toàn tuyệt đối cho refresh-token rotation ở hệ thống phân tán.

### 11.3. Lưu refresh token mới theo version

Một bản ghi minh họa:

~~~json
{
  "grant_key": "issuer|client|subject|tenant|resource",
  "version": 14,
  "access_token": "<encrypted-access-token>",
  "refresh_token": "<encrypted-refresh-token>",
  "expires_at": "2026-11-23T02:10:00Z"
}
~~~

Khi worker refresh xong, nó cập nhật **cả access token và refresh token cùng lúc** với điều kiện `version=14` và tăng lên 15. Nếu CAS thất bại, worker phải đọc lại bản ghi hiện tại, xác định có worker khác đã cập nhật và **không ghi đè bằng refresh token cũ**. Việc ghi token dưới dạng mã hóa/secret reference tùy storage; ví dụ không hiển thị giá trị thật.

Đặc biệt: version/CAS tại storage **không đủ để tránh hai refresh POST đã xảy ra**; nó chỉ ngăn lost update. Muốn tránh reused RT gây family revocation, phải phối hợp **trước khi** gửi request qua lock/single-flight hoặc token broker.

## 12. Device Authorization Grant: polling nhiều lần là hợp lệ

OAuth 2.0 Device Authorization Grant (RFC 8628) cho thiết bị có input giới hạn. Client được cấp `device_code`, `user_code`, `verification_uri` và khoảng polling `interval`. Trong khi user chưa hoàn thành xác thực/ủy quyền trên thiết bị khác, client phải **gửi token request lặp lại theo khoảng quy định**.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=<device-code>&client_id=device-client
~~~

Phản hồi có thể là:

~~~json
{
  "error": "authorization_pending"
}
~~~

hoặc:

~~~json
{
  "error": "slow_down"
}
~~~

Theo RFC 8628, client phải tuân thủ `interval` từ device authorization response hoặc giá trị mặc định được chuẩn quy định khi không có; khi gặp `slow_down`, tăng khoảng polling theo yêu cầu của chuẩn (tối thiểu thêm 5 giây). Khi AS trả `access_denied` hoặc `expired_token`, dừng polling; khi được cấp token thành công, dừng polling và lưu token an toàn.

Nếu connection timeout, giảm tần suất polling theo hướng dẫn của RFC 8628, không mở hàng chục concurrent polling request. Khi token đã cấp nhưng response bị mất, việc tiếp tục polling có thể thấy state đã tiêu thụ: cần làm theo ngữ nghĩa AS, không mong nhận lại cùng token.

**Bài học:** Repeated request là **thiết kế hợp lệ** ở device flow trước khi grant hoàn tất. Chính vì vậy server không được áp một luật “mọi POST lặp là replay” cho tất cả grant.

## 13. Bảo vệ scope, audience và danh tính khi xử lý request trùng

Mọi kỹ thuật chống lặp đều phải giữ nguyên **mô hình tin cậy token**. Một cache/idempotency implementation sai có thể tránh được hai POST, nhưng lại trả token của user A cho user B hoặc token của `inventory-api` cho `payments-api`. Khi đó thiệt hại vượt xa việc gửi thêm request.

### 13.1. Không gộp token khác ngữ cảnh

| Token request A | Token request B | Có thể dùng chung access token không? |
| --- | --- | --- |
| Cùng issuer, client credentials, scope/audience và key binding, cùng machine principal | Giống hệt và token còn hiệu lực | Có thể, nếu AS/client policy cho phép tái sử dụng |
| `aud=inventory-api` | `aud=payments-api` | **Không** |
| Alice với `scope=orders.read` | Bob với `scope=orders.read` | **Không** |
| Tenant `shop-a` | Tenant `shop-b` | **Không**, trừ hợp đồng quyền đa tenant được thiết kế riêng |
| OAuth client A | OAuth client B | **Không** |
| DPoP key A | DPoP key B | **Không** nếu token ràng buộc với key |
| Có `orders.read` | Có `orders.read orders.write` | Không được xem là cùng quyền; chỉ sử dụng token có scope thực tế được phép theo policy |
| Access token cho cùng client và resource nhưng đã bị revoke | Request mới có cùng tham số | Không được sử dụng token đã revoke từ cache |

Client không nên quyết định “chọn token quyền lớn nhất vì dùng được nhiều nơi”. AS có thể cấp scope ít hơn request; resource server phải validate `scope` **được cấp**, `aud`, `iss` và thời hạn của token nhận được. Một token được cache không vượt qua được revocation/rotation policy chỉ vì có `exp` còn xa.

### 13.2. Refresh token cũng gắn với ngữ cảnh tin cậy

Refresh token có thể bị ràng buộc với client, user/session, resource, consent, sender proof hoặc token family theo cách AS định nghĩa. Khi lưu token trong database, cần **partition theo danh tính và grant**. Không bao giờ lấy refresh token theo một khóa quá rộng như `"global-refresh-token"` hoặc `client_id` đơn lẻ cho ứng dụng nhiều người dùng.

Với sender-constrained access token, RS phải xác minh DPoP proof hoặc chứng chỉ mTLS phù hợp; client cache phải giữ liên kết token–key. Việc lặp token request không tự thay thế cơ chế chống replay của proof (ví dụ `jti`/nonce theo RFC 9449).

## 14. Quan sát, bảo mật log và ứng phó sự cố

Phải có đủ thông tin để phân biệt **client retry do mạng**, **refresh race do code lỗi** và **kẻ tấn công replay credential** nhưng vẫn bảo vệ chính các token.

### 14.1. Những thông tin có thể giám sát

- Số token request theo **grant type**, client đăng ký, tenant (nếu phù hợp), kết quả và mã lỗi.
- `invalid_grant` tăng đột ngột sau release, nhất là refresh-token rotation.
- Tỷ lệ `authorization_pending`/`slow_down` của device polling so với giới hạn mong đợi.
- Số refresh attempt trên cùng phiên trong thời gian rất ngắn và số session bị buộc đăng nhập lại.
- Độ trễ token endpoint, timeout, `429`, `5xx` và số request đang chờ.
- Sự kiện RT reuse, code reuse, token family revoked, credential rotation và các thay đổi chính sách AS.

Log nên dùng **correlation ID**, grant type và client ID được phép hiển thị; không ghi nguyên `Authorization`, `code`, `code_verifier`, `refresh_token`, `access_token`, signed assertion hoặc token response. Nếu cần liên kết sự kiện theo credential, dùng fingerprint/HMAC do hệ thống quản lý khóa tạo ra; không xuất credential thật vào telemetry.

### 14.2. Một lỗi client có thể trông như tấn công

Nếu sau khi deploy frontend, số `invalid_grant` tăng và session liên tục đăng xuất, kiểm tra xem nhiều tab cùng refresh token hay không. Chẩn đoán vấn đề **không đồng nghĩa** bỏ phát hiện replay của AS. Điều chỉnh single-flight, shared token store, lock và cách xử lý response. Nếu thực sự có dấu hiệu đánh cắp RT, phải bảo vệ user và có thể revoke grant/session theo chính sách sự cố.

Nếu token endpoint bị quá tải bởi client credentials requests, xem xét token TTL, cache hiệu lực, cache key, clock skew, thundering herd và retry storm. Chỉ tăng quota AS mà không giảm request lặp có thể che giấu vấn đề vận hành.

## 15. Bộ kiểm thử cấp token lặp lại

Một test có ý nghĩa phải sử dụng môi trường AS riêng, khóa test và token test; không gửi access/refresh token thật vào log hoặc report. Đối với mỗi ca, kiểm tra **trạng thái token/grant cuối cùng**, số token được cấp, phản hồi client và tính nhất quán trên nhiều node — không chỉ HTTP status.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| I01 | Client credentials request lần đầu | Cấp token theo đúng scope/audience/policy |
| I02 | Client credentials gửi lại cùng tham số sau khi thành công | Có thể cấp token mới; không mặc định trả cùng bytes |
| I03 | 100 request client credentials đồng thời, client có single-flight | Phần lớn request chia sẻ một tác vụ cấp token/cache phù hợp |
| I04 | Client credentials `aud` khác nhưng dùng chung cache key | Test phải phát hiện token dùng sai audience; sửa key trước production |
| I05 | Authorization code đổi lần đầu với đúng PKCE | Một request thành công, code bị tiêu thụ |
| I06 | Redeem lại cùng authorization code sau thành công | AS từ chối; không phát hành token mới từ code đó |
| I07 | Hai node AS đổi cùng code đồng thời | Chỉ tối đa một winner |
| I08 | Authorization code sai `redirect_uri` hoặc `code_verifier` | Không cấp token; không bypass binding |
| I09 | Token response cho code bị mất sau commit | Không phát lại token chỉ do cùng code; client xử lý flow mới/recovery được hỗ trợ |
| I10 | Refresh token RT-1 đổi thành RT-2 | RT-1 không còn usable theo rotation policy, RT-2 được lưu |
| I11 | Hai thread cùng refresh RT-1 trong một JVM | Single-flight chỉ tạo một outbound refresh request |
| I12 | Hai Pod cùng refresh RT-1 | Distributed coordination/CAS được kiểm tra; không tạo hai request có thể kích hoạt replay |
| I13 | RT-1 đã rotate nhưng request lại bằng RT-1 | AS xử lý reuse theo policy; không cấp quyền mới trái phép |
| I14 | Client nhận RT-2 nhưng bản lưu RT-1 được ghi muộn | CAS/version chặn lost update |
| I15 | Refresh request timeout sau AS commit | Không retry mù quáng bằng RT cũ; phục hồi/reauth theo hợp đồng |
| I16 | RT đã bị revoke hoặc hết hạn | `invalid_grant` hoặc lỗi tương ứng; client không thử mãi |
| I17 | RT thuộc Alice được dùng với Bob/client khác | Từ chối theo binding |
| I18 | AS trả `invalid_client` | Không retry credential hỏng vô hạn |
| I19 | AS trả `429` và `Retry-After` | Giảm tải; retry có giới hạn khi grant cho phép |
| I20 | AS timeout/`503` diện rộng | Backoff+jitter, circuit breaker, không retry storm |
| I21 | Hai request cùng idempotency key nhưng khác scope/tenant | AS có hỗ trợ phải trả conflict/reject; không rò token |
| I22 | Idempotency key của client A bị client B sử dụng | Không trả lại token của A |
| I23 | Device grant trả `authorization_pending` | Client polling đúng khoảng được phép |
| I24 | Device grant trả `slow_down` | Tăng interval và không tạo parallel polling |
| I25 | Device grant `expired_token`/`access_denied` | Dừng polling và báo kết quả |
| I26 | Token `aud=inventory-api` bị sử dụng ở `payments-api` | Resource server từ chối dù issuer/chữ ký đúng |
| I27 | Refresh đã xảy ra nhưng access token mới thiếu quyền mong muốn | Client/API tuân theo scope thực tế, không tự mở rộng |
| I28 | Hệ thống ghi token endpoint request/response khi gặp lỗi | Không rò `code`, RT, AT, client secret, PKCE verifier |

### 15.1. Đừng để “test chạy xanh” vì mọi request đều bị từ chối

Mỗi kiểm thử âm nên có cặp kiểm thử dương:

- Cùng authorization code **đổi lần đầu thành công**, **lần sau bị từ chối**.
- Cùng refresh token hợp lệ **rotate lần đầu thành công**, dùng token cũ **không thành công**.
- Client credentials token còn hạn **được tái sử dụng hợp lệ** và **không** lấy nhầm token sai audience.
- Device grant **polling đúng tần suất** cuối cùng nhận token khi user đã chấp thuận.

Chạy kiểm thử ở môi trường nhiều node để phát hiện race: cùng code/RT phải có **nhiều request thực sự tới các node AS** trong bài kiểm thử server-side, còn test client-side single-flight phải xác nhận **số outbound POST được giảm**. Đây là hai thuộc tính khác nhau.

## 16. Ba tình huống ứng dụng

### Tình huống A: Người dùng double-click đăng nhập

Trình duyệt điều hướng callback hai lần với cùng authorization code. Handler thứ nhất đã đổi code thành công và lưu phiên; handler thứ hai cố POST lại code, nhận `invalid_grant`.

**Thiết kế đúng:** Client kiểm tra state/transaction đã hoàn tất, trả về session hợp lệ nếu có; nếu chưa có session và không thể khôi phục, mở một authorization flow mới. AS chỉ cho một lần đổi code thành công. Không “sửa” bằng cách cho code đổi nhiều lần.

### Tình huống B: Hai tab cùng refresh token

Tab A và B cùng thấy access token sắp hết hạn, cả hai dùng RT-1 để xin token mới. A nhận RT-2; B nhận lỗi reuse, khiến AS có thể revoke family.

**Thiết kế đúng:** Các tab phối hợp qua cơ chế session/token manager được thiết kế cho trình duyệt hoặc backend-for-frontend, sao cho một tác vụ refresh đang chạy được chia sẻ; token mới được lưu nguyên tử và tất cả tab dùng lại. Nếu AS đã coi RT-1 bị replay, tuân thủ recovery policy, không cứ tiếp tục thử lại RT-1.

### Tình huống C: Hệ thống batch làm quá tải AS

Mỗi job `inventory-sync` khởi động một HTTP client và POST `client_credentials` trước từng API request. Sau deploy 100 instance, AS nhận hàng nghìn token request/phút dù access token có TTL 5 phút.

**Thiết kế đúng:** Cache access token theo đúng issuer, client, audience, scope và key binding; dùng single-flight trong process và phối hợp phù hợp giữa instance; thêm backoff/jitter, giới hạn lỗi và metrics. Access token vẫn phải được kiểm tra đúng ở `inventory-api`; cache không được trả token cho resource khác.

## 17. Checklist và câu hỏi tự kiểm tra

Trước khi triển khai token issuance có request lặp lại:

1. **Grant semantics:** Đã xác định từng grant có credential dùng một lần, rotation hay polling có chủ đích chưa?
2. **Single-use:** AS có atomic consume authorization code/RT rotation qua nhiều node và bảo vệ client/PKCE binding?
3. **Unknown outcome:** Client biết xử lý response bị mất sau commit chưa? Có tránh retry mù quáng credential single-use?
4. **Client coordination:** Có single-flight trong process, cơ chế đa instance khi cần và token store version/CAS?
5. **Cache isolation:** Cache key có phân biệt principal, tenant, issuer, client, audience, granted scope, sender binding?
6. **Retry:** Có phân loại lỗi OAuth, `429`, `5xx`, timeout, backoff+jitter và deadline thay vì retry vô hạn?
7. **Token validation:** Access token cấp lại vẫn giới hạn `iss`, `aud`, `exp`, `scope`, profile và quyền nghiệp vụ?
8. **Idempotency:** Nếu dùng `Idempotency-Key`, AS có công bố hỗ trợ và bảo vệ client/request binding, token response, TTL?
9. **Incident response:** Khi refresh reuse, đã xác định token family revocation, session recovery, audit và cảnh báo?
10. **Tests:** Có test cả kết quả commit trước timeout, double-submit, multi-node race, concurrent tabs, device polling và dữ liệu ghi log?

### Câu hỏi 1

**Hai request client credentials giống nhau bắt buộc trả cùng access token không?**

Không. OAuth không yêu cầu token endpoint có idempotency tự động. AS có thể phát hành hai token hợp lệ; client nên cache và giảm request trùng theo policy.

### Câu hỏi 2

**Authorization code đã đổi thành công nhưng client mất response. Có được dùng lại code để lấy token cũ không?**

Không thể mặc định. Code single-use; AS phải từ chối lần sử dụng lặp, còn client cần hoàn tất bằng trạng thái phiên đã lưu hoặc khởi tạo authorization mới khi không có kết quả.

### Câu hỏi 3

**Hai Pod đều dùng RT-1, một Pod nhận RT-2. Chỉ cập nhật database bằng version/CAS có đủ không?**

Không. CAS ngăn lost update sau khi request chạy, nhưng **không ngăn** hai POST bằng RT-1 đã tới AS. Cần coordination trước refresh hoặc token broker có ngữ nghĩa phù hợp.

### Câu hỏi 4

**Gặp `invalid_grant` do RT đã rotate, client có nên retry ngay cùng RT không?**

Không. Phải ngừng dùng RT cũ và tuân thủ cơ chế recovery/re-auth của AS; retry liên tục có thể kích hoạt replay detection hoặc làm tình trạng xấu hơn.

### Câu hỏi 5

**Có thể dùng chung `Idempotency-Key` cho request cấp token của Alice và Bob không?**

Không. Nếu AS hỗ trợ idempotency, key phải được ràng buộc với client, subject/session và request fingerprint, không được để một bên nhận token của bên khác.

### Câu hỏi 6

**Device authorization flow gửi nhiều token request có phải luôn là tấn công replay?**

Không. Polling lặp là cơ chế được thiết kế trước khi user hoàn thành grant, nhưng phải tuân thủ `interval`, `authorization_pending`, `slow_down` và dừng khi grant kết thúc.

## Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `authorization_code` single-use, `invalid_grant`, `client_credentials` và refresh token.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc authorization code với `code_verifier`.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, replay detection và bảo vệ OAuth.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token theo cơ chế AS hỗ trợ.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): polling, `authorization_pending`, `slow_down` và giới hạn tần suất.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): cấp token dựa trên subject/actor token theo policy.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): xin access token cho resource đích cụ thể.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sử dụng access token, bearer và lỗi xác thực.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái access token và ảnh hưởng của cache.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof replay protection và sender-constrained tokens.

**Điểm cần ghi nhớ:** “Request cấp token bị lặp” không có một cách xử lý duy nhất. **Authorization code phải single-use**, refresh token rotation cần tránh race và phát hiện reuse, còn client credentials có thể xin nhiều token nhưng nên cache/single-flight để giảm tải. Với sự cố mạng, **timeout không chứng minh AS chưa commit**; retry phải dựa trên grant và hợp đồng cụ thể. Mọi phương án phải giữ nguyên ranh giới issuer, client, subject, scope, audience, token binding và bảo vệ credential khỏi bị đánh cắp hoặc phát lại.
