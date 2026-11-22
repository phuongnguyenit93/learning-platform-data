# Mô phỏng token bị đánh cắp và lựa chọn biện pháp giảm thiểu

## 1. Mục tiêu bài thực hành

JWT access token thường được dùng như bearer credential: bên nào sở hữu token và gửi được token tới resource server có thể sử dụng quyền được token đại diện, miễn là token vẫn hợp lệ và các điều kiện xác minh khác được đáp ứng. Chữ ký số bảo vệ tính toàn vẹn và nguồn phát hành; chữ ký không ngăn người khác sử dụng bản sao token đã bị lấy cắp.

Bài thực hành này mô phỏng một tình huống có kiểm soát: người dùng hợp lệ nhận access token, token bị sao chép sang một client khác, và client thứ hai thử gọi API bằng token đó. Người học sẽ quan sát hành vi mặc định của bearer token, sau đó áp dụng lần lượt các biện pháp giảm thiểu và đo mức cải thiện.

Các biện pháp được khảo sát:

- Giảm thời gian sống của access token.
- Thu hồi theo token ID bằng denylist hoặc trạng thái token.
- Refresh token rotation và phát hiện reuse.
- Sender-constrained token bằng DPoP hoặc mutual TLS (mTLS).
- Bảo vệ nơi lưu token và giảm khả năng token xuất hiện trong log.
- Quy trình ứng phó khi phát hiện token bị lộ.

Đây là bài thực hành tổng hợp thuộc module **Security - JSON Web Token (JWT)**. Các bước áp dụng chung cho hệ thống OAuth/JWT và API phân tán, không phụ thuộc Java, Spring hoặc một ngôn ngữ lập trình cụ thể.

## 2. Kết quả cần đạt

Sau bài thực hành, người học có thể:

1. Giải thích vì sao bản sao bearer token có thể được phát lại từ một client khác.
2. Phân biệt token bị đánh cắp với signing key bị lộ.
3. Chứng minh logout ở client không nhất thiết làm access JWT mất hiệu lực.
4. Đo cửa sổ rủi ro do access-token lifetime tạo ra.
5. Triển khai hoặc mô phỏng thu hồi theo jti và hiểu chi phí của trạng thái thu hồi.
6. Kiểm thử refresh token rotation và phát hiện reuse.
7. So sánh bearer token với DPoP-bound token và mTLS-bound token.
8. Kiểm tra token leakage trong browser storage, request log, proxy và telemetry.
9. Chọn tổ hợp biện pháp dựa trên threat model, mức độ nhạy cảm và yêu cầu vận hành.
10. Viết được runbook xử lý token bị lộ, có tiêu chí xác minh hiệu quả sau khi ứng phó.

## 3. Phạm vi an toàn của lab

Chỉ thực hiện bài tập trong môi trường lab được phép kiểm soát:

- Dùng issuer, signing key, client, tài khoản và dữ liệu giả lập.
- Chỉ sao chép token do chính lab phát hành cho mục đích mô phỏng.
- Không lấy token từ browser thật, tài khoản thật, log production hoặc thiết bị của người khác.
- Không gửi token lab lên website giải mã công khai hoặc dịch vụ bên thứ ba.
- Không dùng endpoint lab để truy cập API bên ngoài.
- Không đưa token hoặc private key vào báo cáo, ảnh chụp màn hình, ticket hay chat.
- Khi kết thúc, thu hồi session lab và xóa token fixture theo hướng dẫn.

Nếu phát hiện token production bị lộ trong khi thực hiện một hoạt động khác, dừng thao tác với token đó và chuyển sang quy trình incident response của tổ chức. Không tiếp tục dùng token thật để hoàn thành bài tập.

## 4. Tình huống mô phỏng

Một nhân viên có quyền đọc hồ sơ đơn hàng đăng nhập vào ứng dụng nội bộ. Issuer cấp access token có scope đọc hồ sơ. Token được lưu ở client để gửi trong header Authorization.

Một sự cố làm lộ bản sao token, chẳng hạn:

- Mã độc hoặc extension độc hại đọc được vùng lưu token.
- XSS thực thi trong origin có quyền sử dụng token.
- Người vận hành vô tình ghi Authorization header vào log.
- Token xuất hiện trong crash report hoặc công cụ debug.
- Thiết bị người dùng bị mất hoặc bị kiểm soát.

Attacker không cần private signing key. Attacker chỉ cần bản sao bearer token còn hiệu lực và khả năng gửi request tới API.

### 4.1. Các vai trò

| Vai trò | Trách nhiệm trong lab |
| --- | --- |
| Issuer | Phát hành access token và refresh token giả lập |
| Client A | Ứng dụng hợp lệ của user-100 |
| Attacker B | Client thứ hai chỉ có bản sao token bị lộ |
| Resource API | Xác minh token và thực hiện thao tác đọc hồ sơ |
| Security operator | Thu hồi token/session và xem audit event |
| Observer | Đo thời gian, kết quả request và các sự kiện log đã redact |

### 4.2. Sơ đồ luồng ban đầu

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Client A
    participant I as Issuer
    participant R as Resource API
    participant B as Attacker B
    U->>A: Đăng nhập
    A->>I: Yêu cầu token
    I-->>A: Access token T1
    A->>R: Bearer T1
    R-->>A: 200 OK
    Note over A,B: Bản sao T1 bị lộ trong lab
    B->>R: Bearer T1
    R-->>B: 200 OK nếu T1 vẫn hợp lệ
~~~

Sơ đồ mô tả hành vi cần kiểm chứng. Kết quả thực tế còn phụ thuộc signature validation, issuer, audience, expiry, scope, revocation và sender-constraint policy.

## 5. Kiến trúc và hợp đồng lab

Bài tập không yêu cầu một framework cụ thể. Có thể dùng mock issuer/resource API nội bộ hoặc một harness đào tạo đã được cung cấp. Để các bước có thể tái lập, lab cần cung cấp các thao tác tương đương với hợp đồng dưới đây.

### 5.1. Các endpoint giả lập

| Method | Endpoint | Mục đích |
| --- | --- | --- |
| POST | /lab/issue | Cấp access token và refresh token test |
| GET | /api/profile | API cần scope profile:read |
| POST | /lab/refresh | Đổi refresh token lấy cặp token mới |
| POST | /lab/logout | Thu hồi refresh session và mô phỏng xóa token tại client |
| POST | /lab/revoke | Operator thu hồi một jti trong lab |
| GET | /lab/status | Xem trạng thái giả lập của jti/session |
| GET | /lab/audit | Xem sự kiện đã redact |
| POST | /lab/clock/advance | Chỉ trong lab: tiến đồng hồ để kiểm tra expiry |

Các endpoint /lab/* chỉ là control surface của môi trường test. Không triển khai chúng như administrative API công khai trong production. /lab/clock/advance phải bị loại khỏi build production.

### 5.2. Yêu cầu đối với token fixture

Issuer nên phát hành một access JWT test có profile rõ ràng. Ví dụ payload minh họa:

~~~json
{
  "iss": "https://issuer.lab.invalid/",
  "sub": "user-100",
  "aud": "https://api.lab.invalid/profile",
  "iat": 1760000000,
  "exp": 1760000600,
  "jti": "lab-token-0001",
  "client_id": "lab-client-a",
  "scope": "profile:read"
}
~~~

Protected header có thể dùng:

~~~json
{
  "alg": "RS256",
  "kid": "lab-signing-key-01",
  "typ": "at+jwt"
}
~~~

Đây chỉ là dữ liệu minh họa; timestamp cần được issuer lab tạo theo đồng hồ hiện tại của lab. Không dùng payload này như token đã ký. Một JWT hợp lệ cần được issuer ký bằng key test và resource API xác minh bằng public key tương ứng.

### 5.3. Baseline validation

Trước khi bật biện pháp giảm thiểu, Resource API phải:

- Chỉ tin issuer lab đã cấu hình.
- Chỉ chấp nhận audience dành cho API profile.
- Chỉ cho phép thuật toán ký được cấu hình, không chấp nhận alg=none.
- Xác minh chữ ký bằng public key tin cậy.
- Kiểm tra exp và nbf nếu có.
- Kiểm tra token profile/type theo contract.
- Kiểm tra scope profile:read.

Trong baseline, lab cố ý chưa bật denylist access-token và sender constraint. Access token là bearer token thông thường. Refresh token được quản lý riêng.

### 5.4. Hợp đồng request

Ví dụ cấp token:

~~~http
POST /lab/issue HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "subject": "user-100",
  "audience": "https://api.lab.invalid/profile",
  "scopes": ["profile:read"],
  "access_ttl_seconds": 600,
  "refresh_enabled": true
}
~~~

Response minh họa:

~~~json
{
  "token_type": "Bearer",
  "access_token": "<LAB_ACCESS_TOKEN>",
  "refresh_token": "<LAB_REFRESH_TOKEN>",
  "expires_in": 600,
  "jti": "lab-token-0001"
}
~~~

Ví dụ gọi API:

~~~http
GET /api/profile HTTP/1.1
Host: localhost:8080
Authorization: Bearer <LAB_ACCESS_TOKEN>
~~~

Lab có thể dùng tên endpoint hoặc định dạng request khác, nhưng phải cung cấp hành vi tương đương và ghi rõ khác biệt trong kết quả thực hành.

## 6. Chuẩn bị môi trường và dữ liệu

### 6.1. Điều kiện trước khi bắt đầu

- Issuer và Resource API chạy trong mạng lab.
- Signing key là key test riêng; public key đã được cấu hình cho verifier.
- Có hai client độc lập A và B.
- Có operator channel riêng để revoke token/session.
- Có thể xem audit event đã redact.
- Đồng hồ lab có thể điều khiển hoặc chờ expiry một cách an toàn.
- Có thể bật/tắt denylist, refresh rotation và sender constraint.

Nếu lab không hỗ trợ một trong các control, ghi rõ control đó là phần thiết kế/mô phỏng và không đánh dấu đã kiểm thử thực thi.

### 6.2. Dữ liệu giả lập

Chỉ dùng:

- Subject: user-100.
- Resource: profile test.
- Scope: profile:read.
- Issuer: https://issuer.lab.invalid/.
- Audience: https://api.lab.invalid/profile.
- Client A: lab-client-a.
- Client B: lab-client-b.

Không sử dụng email, số điện thoại, địa chỉ, mã nhân viên hoặc dữ liệu người dùng thật.

### 6.3. Thiết lập URL

Ví dụ với shell tương thích Bash:

~~~bash
export LAB_URL="http://localhost:8080"
~~~

Trên PowerShell, có thể đặt biến tương đương:

~~~powershell
$env:LAB_URL = "http://localhost:8080"
~~~

Nếu dùng PowerShell, gọi curl.exe để tránh nhầm alias curl với Invoke-WebRequest.

## 7. Thực hành 1 — Cấp token và xác minh hoạt động bình thường

### 7.1. Cấp token

Gửi request đến /lab/issue theo contract của lab, yêu cầu subject user-100, audience profile API, scope profile:read và access TTL 600 giây.

Lưu access token vào vùng tạm của Client A. Không in toàn bộ token ra terminal transcript hoặc log dùng chung. Ghi lại jti, thời điểm cấp và expires_in.

### 7.2. Gọi API bằng Client A

~~~bash
curl -i "$LAB_URL/api/profile" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
~~~

Kết quả mong đợi:

- HTTP 200.
- Response chỉ chứa dữ liệu profile giả lập.
- Audit ghi nhận request hợp lệ, subject và client context đã xác minh.
- Audit không ghi raw Authorization header hoặc raw JWT.

### 7.3. Kiểm tra token profile

Giải mã header/payload trong công cụ local của lab hoặc parser nội bộ. Việc giải mã chỉ dùng để quan sát claims; nó không thay thế xác minh chữ ký.

Xác nhận:

- iss đúng issuer lab.
- aud đúng resource profile.
- exp nằm trong tương lai.
- jti có giá trị duy nhất cho token.
- scope có profile:read.
- typ/claims phù hợp profile access token.
- Không có secret hoặc dữ liệu cá nhân thật.

### 7.4. Ghi baseline

Ghi lại:

| Chỉ số | Giá trị cần lưu |
| --- | --- |
| Access TTL | 600 giây trong cấu hình baseline |
| Kết quả Client A | HTTP status và latency |
| jti | Chỉ lưu giá trị lab |
| Revocation check | Tắt trong baseline |
| Sender constraint | Không bật |
| Refresh rotation | Ghi rõ đang bật hay tắt |
| Log redaction | Ghi kết quả kiểm tra |

## 8. Thực hành 2 — Mô phỏng token bị đánh cắp

### 8.1. Tạo bản sao có kiểm soát

Trong lab, giả lập việc token bị lộ bằng cách sao chép chính access token test từ Client A sang vùng biến tạm của Client B. Đây là thao tác mô phỏng một bản sao đã bị lộ; không thực hiện việc trích xuất token từ thiết bị hoặc tài khoản thật.

Ví dụ:

~~~bash
ATTACKER_TOKEN="$ACCESS_TOKEN"
~~~

Trong môi trường thực hành hai terminal, truyền token qua kênh tạm chỉ dành cho lab. Không paste token vào ticket, chat, tài liệu hoặc shell history.

### 8.2. Gọi API từ Client B

~~~bash
curl -i "$LAB_URL/api/profile" \
  -H "Authorization: Bearer $ATTACKER_TOKEN"
~~~

Kết quả baseline dự kiến: HTTP 200, vì token còn hạn, chữ ký hợp lệ, issuer/audience/scope phù hợp và verifier chưa ràng buộc token với Client A.

Ghi lại:

- Client A và Client B có khác nhau nhưng token giống nhau.
- Resource API nhận cùng bearer credential.
- Token không tự biết request đến từ chủ thể hợp lệ hay người đang giữ bản sao.
- Việc có chữ ký hợp lệ không chứng minh người gửi request là thiết bị ban đầu.

### 8.3. Quan sát audit

Audit có thể cho thấy cùng jti hoặc cùng token fingerprint được dùng từ hai client/network context khác nhau. Nếu lab không có fingerprint, ghi lại correlation ID và request metadata giả lập.

Không dùng IP address đơn lẻ làm bằng chứng chắc chắn về attacker. NAT, proxy, VPN, mobile network và shared egress có thể làm nhiều người dùng chung địa chỉ IP.

### 8.4. Kết luận thực hành

Nếu Client B được chấp nhận, đó là hành vi đúng với bearer token không có sender constraint và không có trạng thái thu hồi. Đây là đặc tính cần được kiểm soát bằng kiến trúc và vận hành, không phải lỗi của chữ ký JWT.

## 9. Thực hành 3 — Chứng minh logout phía client chưa thu hồi access JWT

### 9.1. Thực hiện logout

Gọi /lab/logout từ Client A theo contract lab. Hành động này mô phỏng:

- Xóa access token khỏi bộ nhớ/storage của Client A.
- Thu hồi refresh session phía issuer.
- Ghi audit event logout.

Trong baseline, lab chưa đưa access-token jti vào denylist.

### 9.2. Kiểm tra Client A

Client A không còn access token local, vì vậy không thể tạo request có Authorization header bằng credential đó. Nếu gửi request không có token, API phải trả HTTP 401.

### 9.3. Kiểm tra Client B

Client B vẫn giữ bản sao token test. Gửi lại request:

~~~bash
curl -i "$LAB_URL/api/profile" \
  -H "Authorization: Bearer $ATTACKER_TOKEN"
~~~

Kết quả có thể vẫn là HTTP 200 cho tới khi access token hết hạn, bị revoke theo jti/session state hoặc bị chặn bởi một policy khác.

### 9.4. Trả lời câu hỏi

1. Vì sao Client A logout nhưng Client B vẫn gọi API được?
2. Refresh token đã bị revoke có làm access JWT đã phát hành mất hiệu lực ngay không?
3. Nếu API chỉ kiểm tra chữ ký và exp, nó có biết issuer đã logout session không?
4. Người dùng cần được thông báo điều gì về phạm vi logout trong kiến trúc hiện tại?

Kết luận cần ghi rõ: xóa bản token khỏi client là local cleanup; thu hồi refresh session và thu hồi access token là các thao tác khác nhau.

## 10. Thực hành 4 — Giảm access-token lifetime

### 10.1. Thay đổi cấu hình lab

Đổi access TTL từ 600 giây xuống 60 giây. Phát hành token T2 mới và ghi lại jti, iat, exp.

Không thay đổi issuer, audience, scope hoặc thuật toán trong lần thử này. Chỉ thay một biến để có thể quy kết kết quả.

### 10.2. Thử phát lại ngay sau khi cấp

Sao chép T2 sang Client B và gọi API ngay. Nếu token là bearer và chưa có sender constraint, request vẫn có thể thành công.

Điều này cho thấy short TTL không ngăn việc sử dụng token trong cửa sổ còn hiệu lực.

### 10.3. Tiến đồng hồ lab

Dùng clock control của lab để tiến thời gian vượt qua exp cộng clock-skew allowance, hoặc chờ token thực sự hết hạn nếu lab không hỗ trợ time travel.

Gọi API lại từ Client B. Kết quả mong đợi: HTTP 401 invalid_token hoặc lỗi tương đương theo API contract.

### 10.4. Đo cửa sổ replay

Ghi:

| Đại lượng | Ý nghĩa |
| --- | --- |
| t_issue | Thời điểm token được phát hành |
| t_exp | Thời điểm hết hạn theo claim exp |
| t_reject | Thời điểm verifier bắt đầu từ chối token |
| Clock skew | Dung sai thời gian của verifier |
| Replay window | Khoảng thời gian bản sao token còn được chấp nhận |

Không mặc định replay window bằng chính xác TTL. Clock skew, cache, verifier clock drift và cách triển khai policy có thể làm cửa sổ thực tế khác đi.

### 10.5. Đánh giá đánh đổi

TTL ngắn:

- Giảm thời gian token bị đánh cắp có thể được phát lại.
- Giảm thời gian claims cũ còn được chấp nhận.
- Tăng số lần refresh và tải lên issuer/token endpoint.
- Có thể làm ứng dụng gián đoạn khi refresh endpoint lỗi.
- Không thu hồi tức thì một token vừa bị lộ.

Không chọn TTL bằng một con số cố định cho mọi API. Dựa vào độ nhạy của resource, mức độ thiệt hại, latency, availability và khả năng refresh.

## 11. Thực hành 5 — Thu hồi access token theo jti

### 11.1. Bật trạng thái thu hồi

Resource API bổ sung một cơ chế denylist hoặc token-status lookup. Khi operator thu hồi một token, hệ thống ghi nhận jti đã bị revoke tới thời điểm token không còn có thể được chấp nhận.

Có thể lưu:

- jti hoặc fingerprint của jti.
- issuer namespace.
- exp của token.
- thời điểm revoke.
- lý do/incident reference đã được chuẩn hóa.

Không lưu raw JWT làm denylist key.

### 11.2. Phát hành token T3

Phát hành token mới có jti riêng. Xác nhận Client A gọi API thành công, Client B có thể replay token trong baseline bearer mode.

### 11.3. Operator revoke jti

Gọi control endpoint của lab:

~~~http
POST /lab/revoke HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Authorization: Bearer <LAB_OPERATOR_CREDENTIAL>

{
  "issuer": "https://issuer.lab.invalid/",
  "jti": "lab-token-0003",
  "reason": "simulated-token-theft"
}
~~~

Credential operator phải được cấp riêng trong lab. Không gửi credential operator cùng access token của user.

### 11.4. Phát lại sau khi revoke

Gửi lại token T3 từ Client A và Client B. Kết quả mong đợi là cả hai đều bị từ chối vì token ID đã bị thu hồi. Với Bearer token, revoke áp dụng cho credential, không phân biệt ai đang giữ bản sao.

API có thể trả HTTP 401 invalid_token. Nếu revoke store không truy cập được, hệ thống phải áp dụng failure policy đã định nghĩa; với yêu cầu thu hồi nghiêm ngặt, không được bỏ qua kiểm tra và cho phép truy cập.

### 11.5. Retention của denylist

Một entry denylist có thể được giữ tới exp cộng clock-skew allowance và biên vận hành cần thiết. Sau khi token không thể còn hợp lệ, entry có thể được dọn theo policy.

Không giữ entry vô hạn nếu không có mục đích. Không xóa quá sớm khi token vẫn có thể được chấp nhận bởi verifier có clock skew hoặc cache policy khác.

### 11.6. Đo chi phí

Ghi:

- Latency thêm vào mỗi request khi tra cứu trạng thái.
- Tỷ lệ cache hit/miss nếu có cache.
- Độ trễ từ lúc operator revoke tới khi mọi instance từ chối token.
- Hành vi khi revoke store timeout.
- Hành vi khi một instance chưa nhận invalidation event.

## 12. Thực hành 6 — Refresh token rotation và phát hiện reuse

### 12.1. Vì sao refresh token cần được bảo vệ?

Refresh token thường có vòng đời dài hơn access token và có thể cấp access token mới. Nếu refresh token bị đánh cắp, attacker có thể duy trì quyền truy cập sau khi access token cũ hết hạn.

Refresh token rotation cấp một refresh token mới sau mỗi lần sử dụng thành công và vô hiệu hóa token trước đó. Nếu token cũ bị dùng lại, đó có thể là dấu hiệu bản sao đã bị lộ.

### 12.2. Tạo refresh family

Phát hành một cặp access/refresh token test. Lab lưu family/session identifier ở server. Refresh token được xem là one-time-use theo policy.

### 12.3. Refresh hợp lệ

Client A gọi /lab/refresh bằng R1. Issuer trả access token mới và refresh token R2, đồng thời đánh dấu R1 đã dùng.

Kết quả mong đợi:

- R2 có thể dùng cho lần refresh tiếp theo.
- R1 không còn được chấp nhận.
- Audit ghi rotation event nhưng không ghi raw refresh token.

### 12.4. Mô phỏng reuse từ Client B

Trong lab, Client B giữ bản sao R1 từ trước. Sau khi Client A đã dùng R1 để lấy R2, Client B thử dùng lại R1.

Kết quả mong đợi theo reuse-detection policy:

- Server phát hiện token cũ đã được sử dụng.
- Refresh family/session liên quan bị revoke theo policy.
- Client A phải xác thực lại hoặc thực hiện recovery flow.
- Security event được ghi nhận.

Không mặc định rằng revoke refresh family sẽ lập tức làm mọi access JWT đã cấp mất hiệu lực. Nếu cần chặn access token đang còn hạn, cần denylist, introspection, session epoch hoặc cơ chế tương đương.

### 12.5. Xử lý retry hợp lệ

Mạng có thể mất response sau khi issuer đã rotate R1 sang R2. Client retry R1 có thể trông giống reuse attack.

Thiết kế cần quyết định:

- Có grace/idempotency window hay không.
- Có cơ chế client retry an toàn không.
- Cách phân biệt retry do mất response với reuse từ thiết bị khác.
- Mức độ chấp nhận false positive.
- Khi nào revoke toàn bộ family và yêu cầu re-authentication.

Không tạo grace window dài đến mức cho phép attacker dùng lại refresh token cũ nhiều lần.

## 13. Thực hành 7 — Sender-constrained token bằng DPoP

### 13.1. Mục tiêu

DPoP (Demonstrating Proof of Possession) ràng buộc access token với một public key của client. Khi đó, chỉ có bản sao access token thường chưa đủ; client cần tạo proof bằng private key tương ứng.

Access token có thể mang claim confirmation, ví dụ:

~~~json
{
  "cnf": {
    "jkt": "<JWK-THUMBPRINT-OF-CLIENT-PUBLIC-KEY>"
  }
}
~~~

### 13.2. Proof request

Client gửi DPoP proof JWT trong header DPoP. Proof có các thuộc tính điển hình:

- JOSE typ là dpop+jwt.
- Header jwk chứa public key dùng xác minh proof.
- Claim htm ràng buộc HTTP method.
- Claim htu ràng buộc target URI.
- Claim iat giới hạn thời gian proof.
- Claim jti định danh proof và hỗ trợ chống replay.
- Claim ath ràng buộc proof với access token.
- Nonce có thể được server yêu cầu theo profile.

Verifier phải xác minh chữ ký proof, thumbprint key khớp cnf.jkt, method/URI đúng, ath đúng, thời gian hợp lệ và jti chưa được dùng trong cửa sổ chống replay.

### 13.3. Thử nghiệm

1. Bật DPoP tại issuer và resource API trong lab.
2. Cấp token T4 gắn với public key của Client A.
3. Client A gửi access token cùng proof hợp lệ và nhận HTTP 200.
4. Copy riêng access token T4 sang Client B, không copy private key.
5. Client B gửi T4 mà không có proof: request phải bị từ chối.
6. Client B tạo proof bằng key khác: thumbprint không khớp, request bị từ chối.
7. Gửi lại cùng proof jti trong replay window: request thứ hai bị từ chối.
8. Thay method hoặc URI trong proof: request bị từ chối.
9. Thay access token nhưng giữ ath cũ: request bị từ chối.

### 13.4. Giới hạn của DPoP

DPoP làm giảm giá trị của token bị đánh cắp riêng lẻ, nhưng không giải quyết mọi trường hợp:

- Nếu attacker lấy được cả private key hoặc có thể yêu cầu client ký proof, rủi ro vẫn còn.
- XSS cùng origin có thể thao tác ứng dụng và gọi signing capability tùy thiết kế.
- Private key cần được bảo vệ và có lifecycle/rotation.
- Replay cache/nonce cần hoạt động đúng trên nhiều instance.
- DPoP proof không thay thế issuer, audience, scope và expiry validation.

Ghi rõ trong báo cáo attacker model nào được DPoP giảm thiểu và attacker model nào vẫn còn.

## 14. Thực hành 8 — Sender-constrained token bằng mTLS

### 14.1. Mục tiêu

Với OAuth mTLS certificate-bound access token, token được ràng buộc với client certificate. Access token có thể chứa confirmation claim:

~~~json
{
  "cnf": {
    "x5t#S256": "<BASE64URL-SHA256-CERTIFICATE-THUMBPRINT>"
  }
}
~~~

Resource server so sánh thumbprint certificate được trình bày trong TLS client authentication với thumbprint được ràng buộc trong token.

### 14.2. Thử nghiệm

1. Cấp token T5 ràng buộc với certificate C-A của Client A.
2. Client A kết nối mTLS bằng C-A và gửi T5: request thành công.
3. Copy riêng T5 sang Client B nhưng dùng certificate C-B: request bị từ chối.
4. Dùng T5 mà không có client certificate: request bị từ chối nếu endpoint yêu cầu mTLS.
5. Dùng certificate không còn hợp lệ hoặc bị thu hồi: áp dụng certificate validation policy và từ chối.

### 14.3. Giới hạn của mTLS

mTLS phù hợp với service-to-service hoặc client có khả năng quản lý certificate. Nó tạo thêm yêu cầu provisioning, renewal, revocation, TLS termination và truyền certificate identity qua proxy một cách an toàn.

Nếu TLS kết thúc ở gateway, backend chỉ được tin certificate identity do gateway chuyển tiếp khi kênh gateway-backend và header forwarding được bảo vệ, xác thực và không thể giả mạo từ client.

## 15. Thực hành 9 — Bảo vệ nơi lưu token và giảm token leakage

### 15.1. Kiểm tra nơi token có thể xuất hiện

Rà soát trong phạm vi lab:

- Browser local storage/session storage.
- Cookie và thuộc tính cookie.
- Memory của ứng dụng.
- Mobile secure storage.
- URL, query string và referrer.
- Application log và API gateway log.
- APM, tracing, crash report và error tracker.
- Clipboard, screenshot, debug dump.
- Queue, retry store và dead-letter queue.

### 15.2. Kiểm thử log redaction

Gửi request có token test qua gateway và API. Kiểm tra log đã redact:

- Authorization header.
- Cookie/Set-Cookie chứa credential.
- Body của token endpoint.
- Query parameter có credential.
- DPoP proof hoặc certificate metadata nhạy cảm nếu policy yêu cầu bảo vệ.

Log không được chứa raw access token hoặc refresh token. Nếu cần tương quan sự kiện, dùng jti hoặc fingerprint được xử lý theo policy, không dùng bearer token làm correlation identifier.

### 15.3. Browser storage

So sánh các lựa chọn:

| Nơi lưu | Đặc điểm | Rủi ro cần kiểm thử |
| --- | --- | --- |
| JavaScript-accessible storage | Ứng dụng đọc được qua script | XSS có thể đọc và gửi token ra ngoài |
| Memory | Có thể mất khi tab/app đóng | Script cùng origin vẫn có thể sử dụng token trong phiên |
| HttpOnly cookie | JavaScript không đọc trực tiếp cookie | Browser tự gửi cookie; cần CSRF defense và SameSite/Secure phù hợp |
| Backend-for-Frontend session | Browser giữ session cookie, backend giữ OAuth token | Cần bảo vệ session, CSRF và backend token store |
| Mobile secure storage | Dùng cơ chế bảo vệ do nền tảng cung cấp | Device compromise, backup, debug và key accessibility |

HttpOnly giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn XSS thực hiện request cùng origin. Cookie tự động được gửi nên cần đánh giá CSRF. Không có một storage option phù hợp cho mọi kiến trúc.

### 15.4. Không truyền token trong URL

Không đặt bearer token trong query string hoặc fragment như một giải pháp mặc định. URL có thể xuất hiện trong browser history, server log, analytics, proxy và referrer. Dùng Authorization header hoặc cơ chế cookie/session phù hợp với kiến trúc.

## 16. Thực hành 10 — Xây dựng quy trình ứng phó token bị lộ

### 16.1. Phân loại sự cố

Phân biệt ít nhất:

| Sự cố | Phạm vi ảnh hưởng |
| --- | --- |
| Access token bị sao chép | Một hoặc một số token/session có thể bị phát lại |
| Refresh token bị sao chép | Attacker có thể duy trì hoặc mở rộng phiên qua refresh |
| Client device bị compromise | Có thể lộ nhiều token và khả năng tạo proof |
| Signing private key bị lộ | Attacker có thể tự ký token giả theo phạm vi key |
| JWKS/issuer configuration bị thay đổi trái phép | Verifier có thể tin nhầm khóa hoặc issuer |

Token bị lộ không tự động có nghĩa signing private key bị lộ. Không rotate toàn bộ issuer signing key chỉ vì một access token bị sao chép nếu chưa có bằng chứng key compromise; hành động đó có thể gây outage mà không xử lý đúng nguồn rò rỉ.

### 16.2. Runbook ứng phó

1. **Xác nhận phạm vi**: xác định issuer, subject, audience, jti, thời điểm phát hành/hết hạn, client và resource liên quan từ log đã redact.
2. **Chặn credential**: revoke jti hoặc session theo khả năng của hệ thống; revoke refresh-token family nếu có nguy cơ refresh token bị lộ.
3. **Đánh giá access token còn hiệu lực**: kiểm tra resource server có denylist/introspection/session epoch hay chỉ dựa trên exp.
4. **Giảm nguồn rò rỉ**: xử lý XSS, malware, log redaction, storage hoặc thiết bị gây ra sự cố.
5. **Đánh giá hoạt động đã xảy ra**: rà soát request và thao tác nghiệp vụ từ thời điểm nghi ngờ bị lộ.
6. **Bảo vệ tài khoản**: yêu cầu re-authentication hoặc thu hồi các session liên quan theo risk policy.
7. **Xác minh propagation**: kiểm tra mọi resource server/instance đã nhận trạng thái revoke.
8. **Theo dõi**: quan sát replay attempts, refresh reuse và lỗi xác thực bất thường.
9. **Lưu bằng chứng an toàn**: giữ audit event đã redact theo incident retention policy.
10. **Đóng sự cố**: xác nhận token cũ bị từ chối, nguồn rò rỉ được xử lý và có hành động phòng ngừa.

### 16.3. Quyết định khi nào cần rotate signing key

Chỉ cần emergency signing-key rotation khi có dấu hiệu private signing key hoặc hệ thống quản lý khóa bị compromise, hoặc policy incident yêu cầu. Nếu chỉ một bearer token bị lộ, ưu tiên revoke token/session và xử lý nguồn lộ.

Nếu signing key bị compromise:

- Dừng ký bằng key bị ảnh hưởng.
- Phát hành key mới theo quy trình khẩn cấp.
- Phân phối trạng thái thu hồi tới verifier.
- Không stale-if-error với key đã bị compromise.
- Đánh giá token giả mạo có thể đã được phát hành.
- Thu hồi session và yêu cầu xác thực lại theo phạm vi ảnh hưởng.

### 16.4. Kiểm tra hiệu quả ứng phó

Sau khi operator revoke:

- Token bị lộ phải bị từ chối ở mọi resource server liên quan.
- Refresh token cũ không thể cấp token mới.
- Token mới hợp lệ vẫn hoạt động theo policy.
- Log không làm lộ token trong quá trình điều tra.
- Cache/revocation state được đồng bộ.
- Request đã commit trước thời điểm revoke được đánh giá riêng; revoke không tự hoàn tác giao dịch đã xảy ra.

## 17. So sánh các biện pháp giảm thiểu

| Biện pháp | Chặn replay token bị sao chép? | Tác động vận hành | Giới hạn |
| --- | --- | --- | --- |
| Short access-token TTL | Không chặn ngay; chỉ thu hẹp cửa sổ | Tăng refresh traffic | Token vẫn dùng được trước exp |
| jti denylist | Có, sau khi trạng thái revoke lan tới verifier | Cần state store/cache và invalidation | Có dependency online và consistency |
| Introspection | Có thể, nếu server đánh dấu inactive | Thêm network call/cache policy | Availability và latency phụ thuộc authorization server |
| Refresh rotation/reuse detection | Hạn chế duy trì phiên bằng refresh token bị sao chép | Cần quản lý token family và retry | Không tự vô hiệu hóa access token đã cấp |
| DPoP | Chặn việc dùng token đơn lẻ khi thiếu private key phù hợp | Key management, proof validation và replay cache | Không chặn attacker kiểm soát client hoặc lấy được key |
| mTLS-bound token | Chặn dùng token với certificate khác | Certificate lifecycle và TLS deployment | Phù hợp hơn với client có certificate management |
| Secure storage/BFF | Giảm khả năng token bị lấy từ client | Thay đổi kiến trúc và session handling | Không loại bỏ mọi XSS/device compromise |
| Log redaction | Ngăn token rò qua telemetry/log | Cần cấu hình mọi lớp | Không ngăn rò rỉ từ nguồn khác |
| Anomaly detection | Phát hiện hành vi đáng ngờ | Cần telemetry và tuning | Không bảo đảm chặn trước request đầu tiên |

Không có một biện pháp đơn lẻ xử lý mọi nguyên nhân token theft. Lựa chọn cần dựa trên attacker capability, độ nhạy API, thời gian phản ứng và mức độ chấp nhận dependency online.

## 18. Ma trận kiểm thử tổng hợp

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| ST-01 | Client A gọi API bằng token hợp lệ | 200 |
| ST-02 | Client B dùng bản sao bearer token còn hạn | Baseline có thể 200; ghi nhận replay |
| ST-03 | Client A logout và xóa token local | Client A không còn token để gửi |
| ST-04 | Client B dùng bản sao sau logout client-only | Có thể vẫn 200 nếu access token chưa revoke/hết hạn |
| ST-05 | Token vượt exp và clock-skew allowance | 401 |
| ST-06 | jti đã bị revoke | 401 invalid_token hoặc lỗi tương đương |
| ST-07 | Revoke store unavailable | Fail closed theo policy; không bỏ qua revoke |
| ST-08 | Refresh token hợp lệ được rotate | Token mới được cấp, token cũ inactive |
| ST-09 | Refresh token cũ bị reuse | Phát hiện reuse và revoke family theo policy |
| ST-10 | Access token cũ sau refresh-family revoke | Chỉ bị chặn ngay nếu có access-token revocation/state check |
| ST-11 | DPoP token với proof/key đúng | Accept |
| ST-12 | DPoP token chỉ có token, không có proof | Reject |
| ST-13 | DPoP proof dùng key khác | Reject |
| ST-14 | DPoP proof jti bị replay | Reject |
| ST-15 | mTLS token với certificate đúng | Accept |
| ST-16 | mTLS token với certificate khác | Reject |
| ST-17 | Authorization header đi qua gateway | Raw token không xuất hiện trong log |
| ST-18 | Thiếu scope profile:read | 403 |
| ST-19 | Sai audience hoặc issuer | 401 |
| ST-20 | Token đã revoke nhưng instance cache chưa nhận invalidation | Phát hiện propagation gap; không đánh dấu control PASS |
| ST-21 | Token bị lộ nhưng signing key không bị compromise | Revoke token/session; không rotate signing key vô cớ |
| ST-22 | Signing private key bị compromise | Emergency key rotation và revoke trust theo incident policy |

## 19. Đo lường và phân tích kết quả

### 19.1. Các chỉ số cần đo

| Chỉ số | Cách đo |
| --- | --- |
| Replay success rate | Số request từ Client B được chấp nhận / tổng replay request |
| Revocation latency | Thời gian từ operator revoke đến khi mọi verifier từ chối |
| Effective replay window | Khoảng thời gian từ lúc token lộ tới lúc token không còn được chấp nhận |
| Refresh reuse detection time | Thời gian từ lần reuse tới khi family bị revoke |
| Added request latency | Latency tăng do denylist/introspection/DPoP/mTLS |
| Availability impact | Request hợp lệ bị lỗi khi dependency revoke/introspection gặp sự cố |
| Log leakage count | Số vị trí phát hiện raw token trong log/test evidence |
| False positive rate | Request hợp lệ bị chặn do detection hoặc retry policy |

### 19.2. Bảng kết quả thực nghiệm

Điền dữ liệu đo được của lab; không dùng giá trị giả định để kết luận:

| Cấu hình | Replay ngay | Replay sau logout | Replay sau revoke | Replay sau exp | Latency thêm |
| --- | --- | --- | --- | --- | --- |
| Baseline bearer | | | | | |
| TTL 60 giây | | | | | |
| jti denylist | | | | | |
| Refresh rotation | | | | | |
| DPoP | | | | | |
| mTLS | | | | | |
| Tổ hợp được chọn | | | | | |

### 19.3. Cách diễn giải

- Nếu TTL ngắn nhưng replay ngay vẫn thành công, đó là kết quả dự kiến.
- Nếu logout chỉ xóa token local nhưng replay ở Client B vẫn thành công, hệ thống chưa thu hồi access token.
- Nếu denylist revoke thành công ở một instance nhưng instance khác vẫn accept, propagation/consistency chưa đạt.
- Nếu refresh reuse bị phát hiện nhưng access token cũ vẫn dùng được, cần đánh giá thêm access-token revocation.
- Nếu DPoP token bị từ chối khi thiếu key proof nhưng vẫn bị dùng được khi attacker kiểm soát browser runtime, cần xem lại threat model và key isolation.
- Nếu log không có raw token ở application nhưng gateway/APM còn token, redaction chưa bao phủ toàn tuyến.

## 20. Bài tập lựa chọn biện pháp theo threat model

Chọn biện pháp cho từng kịch bản và giải thích lý do:

### Kịch bản A — API hồ sơ thông thường

Access token có scope đọc dữ liệu ít nhạy cảm, TTL ngắn, client có thể refresh thường xuyên. Cân nhắc TTL ngắn, secure storage và log redaction; xác định liệu denylist online có đáng với chi phí vận hành không.

### Kịch bản B — API thay đổi thông tin thanh toán

Thao tác có tác động cao, cần thu hồi nhanh và xác minh trạng thái quyền gần thời gian thực. Cân nhắc access TTL ngắn, jti/session revocation hoặc introspection, step-up authentication và authorization check tại thời điểm thao tác.

### Kịch bản C — Service-to-service trong hạ tầng nội bộ

Workload có certificate identity và quản lý vòng đời máy chủ. Cân nhắc mTLS-bound token, audience riêng cho từng service, scope tối thiểu và certificate rotation.

### Kịch bản D — Ứng dụng public client

Không thể giữ client secret an toàn. Cân nhắc authorization code flow với PKCE, refresh token rotation, sender constraint phù hợp, secure storage và kiểm soát XSS/CSRF theo kiến trúc. Không coi một shared secret nhúng trong ứng dụng là bí mật.

### Kịch bản E — Phát hiện token trong log

Token có thể đã được sao chép sang hệ thống telemetry. Cần redaction ngay, xác định phạm vi log/index/backup, revoke token/session theo risk, giới hạn truy cập và retention của evidence, sau đó kiểm tra lại toàn tuyến.

### 20.1. Bảng quyết định

| Kịch bản | Biện pháp ưu tiên | Biện pháp bổ sung | Điều cần xác minh |
| --- | --- | --- | --- |
| A | Short TTL và storage hygiene | Refresh rotation | Tải refresh và replay window |
| B | Revocation/introspection | Step-up, short TTL, audit | Revocation latency và failure policy |
| C | mTLS-bound token | Audience/scope riêng | Certificate lifecycle và proxy boundary |
| D | PKCE và refresh rotation | DPoP, secure storage/BFF tùy kiến trúc | XSS, key protection, reuse detection |
| E | Redaction và token/session revoke | Log retention cleanup, incident review | Mọi bản sao và propagation |

Không áp dụng bảng máy móc. Người học phải giải thích vì sao lựa chọn phù hợp với attacker model và năng lực hệ thống.

## 21. Yêu cầu nộp kết quả

Mỗi nhóm hoặc người học nộp một báo cáo gồm:

1. Sơ đồ lab và trust boundary.
2. Token profile giả lập, claims cần thiết và access TTL.
3. Bằng chứng Client A và Client B dùng cùng bearer token trong baseline.
4. Kết quả logout và giải thích vì sao bản sao có thể vẫn hoạt động.
5. Bảng đo replay window khi giảm TTL.
6. Kết quả revoke theo jti và propagation latency.
7. Kết quả refresh rotation và reuse detection.
8. Kết quả DPoP hoặc mTLS nếu lab hỗ trợ.
9. Kết quả kiểm tra log redaction/storage hygiene.
10. Runbook xử lý token theft và tiêu chí xác nhận đã containment.
11. Biện pháp cuối cùng được chọn, đánh đổi, chi phí và residual risk.

Không đính kèm raw access token, refresh token, private key hoặc thông tin xác thực operator.

### 21.1. Mẫu kết luận kỹ thuật

~~~text
Threat model:
  Attacker có bản sao access token.
  Attacker không có signing private key.
  Attacker có thể gửi request tới resource API.

Baseline:
  Replay result:
  Logout behavior:
  Effective replay window:

Controls tested:
  Short TTL:
  jti revocation:
  Refresh rotation:
  DPoP or mTLS:
  Storage/log redaction:

Selected design:
  Primary control:
  Supporting controls:
  Revocation objective:
  Availability trade-off:
  Residual risk:

Evidence:
  Test run IDs:
  Revocation propagation:
  Log redaction result:
~~~

## 22. Tiêu chí đánh giá

| Hạng mục | Điểm | Tiêu chí |
| --- | ---: | --- |
| Hiểu bearer-token replay | 15 | Giải thích đúng vì sao token bị sao chép vẫn được sử dụng |
| Baseline và logout test | 10 | Chứng minh được khác biệt giữa local deletion và server revocation |
| Short TTL | 10 | Đo replay window và giải thích trade-off |
| jti revocation | 15 | Kiểm tra denylist, propagation và failure policy |
| Refresh rotation | 10 | Kiểm thử token reuse và phân tích access token đã cấp |
| Sender constraint | 15 | Kiểm thử DPoP hoặc mTLS đúng threat model |
| Storage/log hygiene | 10 | Xác minh redaction trên các lớp liên quan |
| Incident response | 10 | Runbook có containment, validation và recovery |
| Phân tích residual risk | 5 | Không tuyên bố một control loại bỏ mọi rủi ro |
| **Tổng** | **100** | |

Không chấm đạt nếu bài tập sử dụng token production, để raw token trong báo cáo hoặc đánh dấu control đã kiểm thử khi chỉ mới mô tả trên lý thuyết.

## 23. Lỗi thường gặp khi thực hiện

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ chữ ký JWT ngăn replay | Chữ ký xác minh nội dung, không ràng buộc người giữ token | Kiểm thử bearer replay và sender constraint |
| Nghĩ logout luôn revoke access token | Logout có thể chỉ xóa client state/revoke refresh session | Kiểm tra server-side access revocation |
| Nghĩ short TTL chặn token ngay lập tức | Token vẫn hợp lệ tới exp và clock-skew policy | Đo replay window thực tế |
| Nghĩ revoke refresh token thu hồi mọi access token | Access JWT đã cấp có thể còn hiệu lực | Kết hợp access-token revocation khi cần |
| Dùng jti nhưng không tra cứu trạng thái | Claim jti tự nó không tạo revocation | Verifier phải có denylist/introspection/epoch |
| Denylist không đồng bộ giữa instance | Một số API vẫn chấp nhận token | Đo propagation và consistency |
| Revoke store lỗi thì cho qua | Fail-open phá mục tiêu thu hồi | Định nghĩa fail-closed theo risk |
| Dùng IP làm bằng chứng duy nhất | NAT/proxy/VPN làm IP không định danh người dùng | Kết hợp tín hiệu và điều tra |
| Nghĩ DPoP ngăn attacker kiểm soát client | Attacker có thể gọi signing capability hoặc lấy key | Định nghĩa rõ key isolation và attacker capability |
| Chỉ bật mTLS ở gateway nhưng không ràng buộc tới backend | Certificate identity có thể bị giả qua header | Bảo vệ gateway-backend và xác thực forwarded identity |
| Không phát hiện refresh reuse | Token cũ có thể tiếp tục duy trì phiên | Rotation, family state và reuse policy |
| Ghi token vào log để debug | Tạo thêm bản sao credential | Redact và dùng correlation ID an toàn |
| Rotate signing key sau mọi token theft | Không xử lý đúng phạm vi sự cố | Chỉ rotate signing key khi key/system bị compromise |
| Không cleanup token fixture | Credential test còn tồn tại sau lab | Revoke session và xóa dữ liệu test |

## 24. Dọn dẹp môi trường lab

Sau khi hoàn thành:

1. Thu hồi mọi refresh-token family của lab.
2. Revoke các access token fixture còn hạn.
3. Xóa token khỏi biến môi trường, clipboard và file tạm.
4. Xóa key test theo quy trình lab nếu không còn dùng.
5. Dọn denylist/session/audit fixture theo retention của lab.
6. Tắt endpoint điều khiển clock và administrative lab endpoint.
7. Xác nhận không có token fixture trong log hoặc báo cáo.
8. Đưa cấu hình lab về trạng thái sạch trước nhóm tiếp theo.

Không xóa audit evidence cần thiết trước khi hoàn thành đánh giá, nhưng evidence phải được redact và giữ theo retention policy.

## 25. Câu hỏi tự kiểm tra

1. Vì sao một bản sao JWT bearer token có thể được dùng từ client khác?
2. Chữ ký JWS bảo vệ điều gì và không bảo vệ điều gì?
3. Vì sao logout ở client chưa chắc làm access token mất hiệu lực?
4. Short TTL làm giảm rủi ro nào và không giải quyết rủi ro nào?
5. jti có tự tạo khả năng revoke không? Vì sao?
6. Denylist nên giữ entry tới thời điểm nào?
7. Vì sao refresh-token reuse có thể là dấu hiệu token bị đánh cắp?
8. Vì sao refresh family revocation không nhất thiết vô hiệu access token đã phát hành?
9. DPoP ràng buộc access token với key như thế nào?
10. Những claim nào trong DPoP proof hỗ trợ chống replay và ràng buộc request?
11. mTLS-bound token khác bearer token thông thường ở đâu?
12. HttpOnly cookie giảm rủi ro gì và còn rủi ro gì?
13. Vì sao XSS vẫn có thể thực hiện request cùng origin dù không đọc được HttpOnly cookie?
14. Khi nào cần rotate issuer signing key sau sự cố?
15. Làm thế nào xác nhận mọi resource server đã áp dụng trạng thái revoke?
16. Chọn biện pháp nào cho API nhạy cảm cần thu hồi gần tức thì? Giải thích đánh đổi.

## 26. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), bearer-token semantics và nguy cơ sử dụng token bị lộ.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), claims thời gian, subject, audience và jti.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), chữ ký và bảo vệ tính toàn vẹn của JWS.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009), thu hồi access token và refresh token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), truy vấn trạng thái token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), bảo vệ refresh token, public client và sender-constrained token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449), proof-of-possession cho access token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705), mTLS và certificate-bound token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), access-token profile và typ=at+jwt.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), quản lý session và credential.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), bảo vệ dữ liệu nhạy cảm trong log.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), giảm nguy cơ XSS dẫn tới lộ hoặc sử dụng token.
