# Credential anomaly — Phát hiện hành vi sử dụng credential bất thường

Một tài khoản nhân viên thường đăng nhập từ laptop công ty, dùng passkey và truy cập một nhóm ứng dụng cố định. Trong vài phút, hệ thống ghi nhận hàng chục lần đăng nhập thất bại vào nhiều tài khoản từ cùng một dải mạng; ngay sau đó một tài khoản có lần đăng nhập thành công từ thiết bị mới, rồi tạo refresh token và truy cập API với scope hiếm khi được dùng. Mỗi sự kiện riêng lẻ có thể trông hợp lệ, nhưng chuỗi sự kiện cho thấy khả năng credential stuffing hoặc account takeover.

**Credential anomaly** là hành vi sử dụng, phát hành hoặc xác minh credential khác đáng kể so với baseline và policy dự kiến của principal, thiết bị, workload hoặc ứng dụng. Anomaly có thể là dấu hiệu tấn công, credential bị lộ, cấu hình sai, automation lỗi hoặc thay đổi vận hành hợp lệ. Một anomaly là tín hiệu cần điều tra, không tự động chứng minh có compromise.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học xây dựng khả năng quan sát và phát hiện bất thường xuyên suốt vòng đời xác thực: password, MFA, passkey, certificate, API key, access/refresh token, session và workload identity. Người học biết thu thập telemetry an toàn, tạo detection rule và correlation, đánh giá risk theo ngữ cảnh, giảm false positive, phản ứng có kiểm soát và kiểm chứng hiệu quả phát hiện. Mục tiêu là nhận ra sớm credential bị lạm dụng mà không biến hệ thống monitoring thành một kho bí mật mới.

## 1. Credential anomaly là gì?

Một credential hợp lệ có thể bị sử dụng theo cách bất thường. Ví dụ:

- Một password đúng được dùng từ thiết bị hoặc khu vực chưa từng xuất hiện.
- Nhiều account nhận các lần đăng nhập thất bại có pattern giống nhau.
- Một tài khoản thành công ngay sau một đợt password spraying.
- Một refresh token được dùng đồng thời từ hai thiết bị không liên quan.
- Một passkey assertion có origin/RP ID sai hoặc xuất hiện cùng chuỗi challenge bất thường.
- Một API key lâu không hoạt động đột nhiên gọi nhiều endpoint quản trị.
- Một workload xin lượng lớn short-lived token hoặc scope vượt baseline.
- Một certificate bị dùng từ nhiều host hoặc sau khi workload đã bị thu hồi.

Anomaly detection quan sát hành vi so với policy, lịch sử và ngữ cảnh. Nó bổ sung cho kiểm tra mật mã và authorization:

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication validation | Credential có hợp lệ về mặt giao thức không? | Chữ ký token đúng, password verifier khớp, certificate chain tin cậy |
| Authorization | Principal có quyền thực hiện hành động không? | Scope, role, tenant và object policy |
| Anomaly detection | Cách sử dụng có khác thường hoặc đáng ngờ không? | Token được dùng từ ASN mới, API key gọi endpoint lạ |
| Incident response | Cần hành động gì khi risk đủ cao? | Step-up, revoke session, disable credential, mở incident |

Một request có token hợp lệ vẫn có thể bất thường. Ngược lại, một đăng nhập từ thiết bị mới có thể là hành vi hợp lệ khi nhân viên đổi máy. Không dùng anomaly score để thay thế việc xác minh chữ ký, issuer, audience, expiry hoặc policy quyền truy cập.

### 1.1. Phân biệt anomaly, alert và incident

- **Anomaly:** quan sát khác baseline hoặc policy.
- **Detection:** logic xác định anomaly đủ đáng chú ý.
- **Alert:** thông báo có ngữ cảnh cho người hoặc hệ thống phản ứng.
- **Incident:** sự kiện bảo mật đã được xác nhận hoặc được xử lý theo quy trình incident.

Không phải anomaly nào cũng cần page on-call. Alert fatigue làm giảm khả năng nhận ra tín hiệu quan trọng. Hãy gộp các sự kiện liên quan, phân loại mức độ và chỉ nâng thành incident theo bằng chứng hoặc policy.

## 2. Threat model và tài sản cần quan sát

Credential anomaly thường liên quan đến các tình huống:

- Password reuse, credential stuffing và password spraying.
- Brute force hoặc enumeration có mục tiêu.
- MFA fatigue, OTP guessing và social engineering.
- Session theft, refresh-token replay hoặc token substitution.
- API key, client secret hoặc private key bị lộ.
- Certificate/workload identity bị dùng ngoài phạm vi.
- Account recovery bị lạm dụng để chiếm tài khoản.
- Automation, bot hoặc CI/CD runner bị compromise.
- Insider misuse hoặc quyền service principal quá rộng.

Tài sản cần bảo vệ gồm account, credential, session, token family, device binding, workload principal, secret manager, resource và audit trail.

### 2.1. Các câu hỏi threat model

1. Attacker có thể lấy credential từ đâu: phishing, malware, repository, log, backup, endpoint hay nhà cung cấp?
2. Attacker có thể sử dụng credential từ thiết bị, mạng hoặc quốc gia khác không?
3. Hệ thống có phân biệt user, client, workload và actor thực hiện hành động không?
4. Một credential có thể tạo thêm credential/session khác hay không?
5. Revocation lan tới gateway, API, session store và downstream trong bao lâu?
6. Log có đủ thông tin tương quan mà không chứa raw secret không?
7. Ai có thể tắt rule, sửa threshold hoặc xóa audit?
8. False positive có thể khóa nhầm người dùng, service hoặc quy trình khẩn cấp không?

### 2.2. Detection phải bao phủ cả user và workload

Không chỉ theo dõi đăng nhập người dùng. Workload identity và service credential cũng có hành vi bất thường:

- Service account xin token thường xuyên hơn baseline.
- Workload gọi secret path ngoài phạm vi.
- Certificate của một service xuất hiện trên node lạ.
- CI runner từ fork hoặc branch không tin cậy cố lấy production secret.
- API client dùng key từ ASN hoặc region mới.
- Một service bắt đầu gọi endpoint admin sau khi deployment thay đổi.

Baseline phải được tách theo principal type và role. Không so sánh một batch job với hành vi tương tác của người dùng; không gộp dev, staging và production vào cùng một baseline.

## 3. Nguồn telemetry và sự kiện xác thực

Detection tốt cần sự kiện nhất quán từ nhiều thành phần:

| Nguồn | Sự kiện hữu ích |
| --- | --- |
| Identity provider | Login success/failure, MFA challenge, password reset, account lock, risk decision |
| Authentication service | Password verification, passkey assertion, certificate validation, recovery flow |
| Authorization server | Token issue/refresh/revoke, client authentication, consent, introspection |
| Session service | Session create/rotate/revoke, concurrent session, device binding |
| API gateway | Principal, audience, scope, route, status, client/network metadata |
| Secret manager/KMS | Secret read, lease issue/renew/revoke, key operation, policy denial |
| PKI/certificate service | Certificate issue/renew/revoke, serial, SAN, trust bundle update |
| Workload platform | Pod/VM identity, deployment, node, service account, attestation |
| Endpoint/MDM | Device compliance, managed state, security posture |
| SIEM/SOAR | Correlation, alert, case, response action và analyst disposition |

### 3.1. Event taxonomy

Chuẩn hóa event type để nhiều nguồn có thể được tương quan:

- Authentication: attempt, success, failure, challenge, step-up, logout.
- Credential lifecycle: create, enroll, rotate, revoke, recover, disable.
- Token/session: issue, refresh, reuse, revoke, expire, bind/unbind.
- Authorization: allow, deny, privilege change, scope elevation.
- Device/workload: enroll, attest, posture change, deploy, terminate.
- Secret/key/certificate: read, sign, decrypt, issue, renew, revoke.
- Administrative: policy change, exception, break-glass, audit access.

Đừng gộp mọi lỗi vào một event login_failed. Password sai, OTP sai, token hết hạn, issuer unavailable và account bị disable cần reason code khác nhau để detection không nhầm tấn công với lỗi vận hành.

### 3.2. Schema sự kiện tối thiểu

Một event có thể mang các trường:

| Trường | Ý nghĩa |
| --- | --- |
| event_id | ID duy nhất để chống duplicate ingestion |
| event_time | Thời điểm nguồn tạo sự kiện |
| ingest_time | Thời điểm hệ thống monitoring nhận được |
| event_type / outcome | Loại sự kiện và kết quả |
| principal_ref | Account/workload ID đã pseudonymize |
| principal_type | User, service, workload, client hoặc admin |
| credential_ref | ID/fingerprint không thể dùng như credential |
| credential_type | Password, passkey, TOTP, certificate, API key, token |
| auth_method | Phương thức thực tế được dùng |
| client_id / audience / scope | Ngữ cảnh client và resource |
| session_ref / token_family_ref | Tham chiếu session hoặc nhóm refresh token |
| device_ref / posture | Thiết bị đã được nhận diện và trạng thái compliance |
| source_ip / network_context | IP và metadata mạng được kiểm soát |
| geo / ASN | Vị trí/nhà mạng suy ra, có độ bất định |
| request_id / trace_id | Tương quan request xuyên service |
| policy_version / risk_result | Policy và quyết định tại thời điểm đó |
| reason_code | Mã lý do chuẩn hóa, không chứa secret |

Không đưa password, OTP, recovery code, raw token, session cookie, private key hoặc Authorization header vào event. Với IP, device fingerprint và vị trí, chỉ thu thập khi có mục đích hợp lệ, giới hạn retention và quyền truy cập.

## 4. Chuẩn hóa dữ liệu trước khi phát hiện

Các hệ thống có thể dùng timezone, định dạng IP, user ID và tên event khác nhau. Trước khi chạy rule:

- Đồng bộ thời gian nguồn; giữ cả event_time và ingest_time để phát hiện trễ.
- Chuẩn hóa UTC và ghi rõ độ chính xác timestamp.
- Chuẩn hóa principal reference nhưng không ghép nhầm account giữa tenant.
- Dùng credential ID/fingerprint thay raw value.
- Chuẩn hóa IPv4/IPv6, proxy chain và trusted forwarding headers.
- Phân biệt IP client, edge proxy, gateway và egress NAT.
- Chuẩn hóa country/ASN với nguồn dữ liệu và confidence.
- Gắn môi trường, tenant, application và principal type.
- Deduplicate theo event ID hoặc idempotency key ingestion.
- Xử lý out-of-order events và late arrival.

### 4.1. Identity resolution

Một user có thể có nhiều account, email alias, employee ID và federated subject. Một workload có thể thay pod nhưng giữ service identity. Cần một identity mapping có lịch sử và tenant boundary rõ ràng.

Không chỉ dùng email làm principal key: email có thể thay đổi, tái sử dụng hoặc không duy nhất giữa tenant. Dùng stable subject/reference từ identity provider và giữ mapping/version để điều tra được hành vi trong quá khứ.

### 4.2. Network context không phải danh tính

IP, ASN, geolocation và user-agent là tín hiệu phụ. VPN, mobile carrier, corporate proxy, NAT, travel và cloud egress có thể làm IP thay đổi. Không coi một IP mới là bằng chứng compromise và không dùng IP đơn lẻ làm authentication factor.

## 5. Các nhóm credential anomaly

### 5.1. Password attack patterns

| Pattern | Dấu hiệu | Detection idea |
| --- | --- | --- |
| Brute force | Nhiều password thử vào một account | Đếm failure theo principal và time window |
| Password spraying | Một vài password thử trên nhiều account | Đếm distinct principals theo source và failure pattern |
| Credential stuffing | Nhiều cặp username/password bị thử, thường phân tán | Correlate failure burst, bot/network reputation và account diversity |
| Account enumeration | Thử xác định account tồn tại qua response/timing | So sánh response class và tần suất theo identifier hash |
| Targeted guessing | Tập trung vào account có quyền cao | Risk theo role, failure velocity và source novelty |
| Distributed low-and-slow | Nhiều source, mỗi source ít request | Correlate theo credential/account cohort, device/network clusters |

Không chỉ đếm theo IP. Attacker có thể phân tán nguồn; nhiều người dùng hợp lệ có thể chung IP. Kết hợp principal, source, device, ASN, client, failure reason và thời gian.

### 5.2. MFA và passkey anomaly

- Nhiều MFA push bị từ chối hoặc timeout rồi có một lần approve.
- OTP sai liên tiếp hoặc thử cùng một mã trên nhiều account.
- MFA method bị thêm/xóa ngay sau login từ thiết bị mới.
- Recovery code được dùng từ network/device khác baseline.
- Passkey enrollment xảy ra ngay sau recovery hoặc step-up bất thường.
- WebAuthn origin, RP ID, challenge hoặc credential mapping không hợp lệ.
- Một credential passkey có hành vi counter bất thường theo loại authenticator.

Không diễn giải sign counter của WebAuthn một cách máy móc: một số authenticator/passkey sync có thể không tăng counter như thiết bị roaming truyền thống. Dùng counter như tín hiệu bổ sung và ưu tiên các kiểm tra protocol bắt buộc.

### 5.3. Token và session anomaly

- Refresh token reuse sau rotation hoặc từ hai client/device không phù hợp.
- Token có audience, scope hoặc client khác baseline.
- Một session tạo nhiều session con hoặc đổi device binding liên tục.
- Token được dùng sau logout/revocation propagation window.
- Access token xuất hiện từ ASN/region mới kèm hành vi nhạy cảm.
- Một token family refresh với tần suất bất thường.
- Session có hoạt động sau khi password/MFA factor bị reset.

Bearer access token có thể được dùng nhiều lần trong lifetime bình thường. Không alert chỉ vì cùng token được gửi cho nhiều request; cần xem token type, sender-constraining, device, session, endpoint và reuse policy. Với refresh token rotation, reuse một token cũ có thể là tín hiệu mạnh nếu issuer định nghĩa token single-use.

### 5.4. API key, certificate và workload credential anomaly

- API key không hoạt động lâu đột nhiên gọi API nhạy cảm.
- Một key được dùng từ nhiều region hoặc principal không liên quan.
- Certificate serial/SAN xuất hiện từ host khác với workload mapping.
- Workload xin token với scope/audience không được policy thông thường yêu cầu.
- Secret manager nhận burst read từ một principal.
- Dynamic secret lease được tạo/renew vượt tần suất.
- CI identity từ branch/repository lạ xin production credential.
- Service account tiếp tục hoạt động sau khi workload bị terminate.

### 5.5. Recovery và administrative anomaly

- Recovery flow bắt đầu ngay sau password spray.
- Email/phone recovery bị thay đổi rồi session mới được tạo.
- Nhiều recovery attempt vào cùng account hoặc cùng contact.
- Admin thêm factor, disable MFA hoặc tạo API key ngoài change window.
- Break-glass account được sử dụng mà không có incident/ticket phù hợp.
- Policy hoặc audit configuration bị thay đổi trước khi credential misuse tăng.

## 6. Baseline: xác định hành vi bình thường

Baseline mô tả cách principal hoặc nhóm principal thường sử dụng credential. Có thể xây dựng theo:

- Principal: account, service hoặc workload.
- Role/persona: nhân viên, admin, partner, batch job, CI runner.
- Application/client: browser, mobile app, API client.
- Environment: dev, staging, production.
- Time: giờ làm việc, lịch batch, deployment window.
- Network/device: managed device, ASN, VPN, service subnet.
- Resource: audience, route, scope, secret path.
- Authentication method: password, passkey, certificate, workload assertion.

### 6.1. Cold start và nhóm tương đồng

Account mới chưa có lịch sử. Không nên kết luận mọi hành vi đầu tiên là bất thường. Có thể dùng baseline của nhóm tương đồng (role, tenant, department, workload class) và áp dụng risk thấp hơn cho đến khi có đủ dữ liệu.

Với service mới deploy, dùng deployment metadata để cập nhật baseline có kiểm soát. Không tự động coi mọi thay đổi sau deploy là hợp lệ; attacker có thể lợi dụng pipeline hoặc change window.

### 6.2. Baseline bị đầu độc

Nếu hệ thống tự học từ mọi hành vi mà không lọc incident, attacker có thể từ từ làm baseline dịch chuyển. Cần:

- Loại trừ event thuộc incident đã xác nhận.
- Tách training data và enforcement data.
- Review thay đổi baseline lớn.
- Version baseline và lưu lý do cập nhật.
- Không cho một principal tự phê duyệt ngoại lệ cho chính nó.

## 7. Detection rule và correlation

Bắt đầu bằng rule dễ giải thích, có thể tái hiện và kiểm thử. Sau khi có chất lượng dữ liệu và feedback, mới bổ sung mô hình thống kê hoặc machine learning.

### 7.1. Velocity và cardinality

Ví dụ metric:

- Số lần thất bại trên một principal trong cửa sổ thời gian.
- Số distinct principal bị thử từ một source.
- Số source khác nhau thử cùng một account.
- Số credential type thay đổi trong một session.
- Số token được phát hành cho một workload.
- Số secret path được đọc bởi một principal.

Dùng distinct count để phát hiện spraying và credential stuffing. Đếm request tổng có thể bị nhiễu bởi retry hoặc người dùng nhập sai nhiều lần.

### 7.2. Correlation theo chuỗi sự kiện

Một chuỗi đáng chú ý có thể là:

1. Nhiều login failure trên nhiều account.
2. Một account trong cohort có login success.
3. Account đó thêm MFA factor hoặc đổi recovery contact.
4. Một refresh token/session mới được tạo.
5. Principal truy cập resource nhạy cảm hoặc tăng scope.

Một detection chỉ nhìn bước 2 có thể bỏ sót. Correlation cần cửa sổ thời gian, principal mapping và causal reference để ghép các event.

~~~mermaid
flowchart TD
    A[Password failures across accounts] --> B{A success follows?}
    B -- No --> C[Track spraying / stuffing]
    B -- Yes --> D[Correlate device and network novelty]
    D --> E{MFA or recovery changed?}
    E -- Yes --> F[High-risk account takeover signal]
    E -- No --> G[Check token/session behavior]
    G --> H{Sensitive action or privilege change?}
    H -- Yes --> I[Step-up / contain / investigate]
    H -- No --> J[Monitor with bounded risk]
~~~

### 7.3. Ví dụ rule password spraying

Rule minh họa:

~~~sql
SELECT
  source_ip,
  COUNT(*) AS failures,
  COUNT(DISTINCT principal_ref) AS principals
FROM auth_events
WHERE event_time >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
  AND event_type = 'authentication.failure'
  AND reason_code = 'invalid_password'
GROUP BY source_ip
HAVING COUNT(DISTINCT principal_ref) >= 12
   AND COUNT(*) >= 20;
~~~

Các con số trong ví dụ chỉ để minh họa, không phải ngưỡng dùng chung. Tuning theo lưu lượng, NAT, tenant, loại ứng dụng và baseline. Rule production nên loại trừ health check/retry đã biết, nhưng mọi exclusion phải có owner, expiry và audit.

### 7.4. Distributed spraying

Khi attacker dùng nhiều IP, nhóm theo các tín hiệu khác:

- Account cohort và thời gian.
- User-agent/client fingerprint có độ tin cậy phù hợp.
- ASN, hosting provider hoặc proxy category.
- Password failure reason pattern.
- Request cadence và automation indicators.
- Device/automation signal từ bot defense.

Không tạo fingerprint xâm lấn hoặc dùng thuộc tính nhạy cảm không cần thiết. Hash identifier có thể giúp correlation nhưng không biến dữ liệu cá nhân thành vô danh tuyệt đối.

### 7.5. Successful login after failure burst

Một lần login success sau nhiều failure có thể là người dùng cuối cùng nhập đúng password. Nó trở nên đáng ngờ hơn khi kết hợp:

- Nhiều account cùng bị thử.
- Source/device mới hoặc có reputation xấu.
- MFA bị từ chối nhiều lần trước khi approve.
- Account có privilege cao.
- Recovery factor vừa bị thay.
- Token được phát hành với scope/audience mới.

Detection nên tạo risk context cho principal/session thay vì khóa account ngay trong mọi trường hợp.

## 8. Risk scoring và quyết định thích ứng

Risk score tổng hợp nhiều tín hiệu. Điểm số phải có thể giải thích, version và hiệu chỉnh; không nên là một con số bí ẩn quyết định mọi thứ.

### 8.1. Nhóm tín hiệu

| Nhóm | Tín hiệu ví dụ | Ý nghĩa |
| --- | --- | --- |
| Credential | Failure velocity, token reuse, key rotation anomaly | Credential có thể bị đoán hoặc đánh cắp |
| Device | Device mới, unmanaged, posture degraded | Client context thay đổi |
| Network | ASN mới, hosting/VPN, source reputation | Nguồn truy cập khác baseline |
| Behavior | Route/scope/resource mới, action velocity | Hành vi sau xác thực khác thường |
| Identity | Privileged role, dormant account, recovery vừa đổi | Tác động tiềm năng cao |
| Protocol | Issuer/audience/origin mismatch, invalid signature | Có thể là lỗi protocol hoặc tấn công |
| Environment | Deployment/change window, service version | Ngữ cảnh vận hành |

### 8.2. Ví dụ risk model

Một mô hình đơn giản có thể cộng điểm theo tín hiệu đã chuẩn hóa:

\[
R = w_c C + w_d D + w_n N + w_b B + w_i I
\]

Trong đó C là credential signal, D là device, N là network, B là behavior, I là identity impact; các trọng số w được hiệu chỉnh bằng dữ liệu và policy. Đây là khung tư duy, không phải công thức chuẩn. Cần tránh cộng trùng nhiều tín hiệu có cùng nguyên nhân.

### 8.3. Risk tier và hành động

| Mức | Ví dụ quyết định | Hành động |
| --- | --- | --- |
| Informational | Thiết bị mới nhưng passkey và device posture tốt | Ghi nhận, cập nhật baseline có kiểm soát |
| Low | Một số login failure đơn lẻ | Rate limit nhẹ, tiếp tục quan sát |
| Medium | Nhiều failure và source mới | Step-up MFA, challenge bổ sung, giảm tốc độ |
| High | Success sau spraying, recovery change và token anomaly | Revoke session/token family, yêu cầu reauthentication, mở case |
| Critical | Private key/API key bị lạm dụng hoặc admin takeover được xác nhận | Disable credential/workload, isolate, incident response |

Hành động phải theo khả năng và tác động. Không khóa mọi account chỉ vì IP mới; không tự động revoke certificate production của hàng loạt workload khi telemetry có lỗi.

### 8.4. Step-up thay cho block tuyệt đối

Với risk trung bình, có thể yêu cầu xác thực mạnh hơn:

- Reauthenticate bằng passkey hoặc factor độc lập.
- Xác minh device binding hoặc managed device posture.
- Yêu cầu approval cho thao tác nhạy cảm.
- Giới hạn scope hoặc chặn action rủi ro trong thời gian ngắn.
- Bắt người dùng kiểm tra và thu hồi session lạ.

Step-up cần bảo vệ khỏi MFA fatigue và phishing. Nếu attacker đã kiểm soát session hoặc thiết bị, thêm một OTP có thể không đủ.

## 9. Phát hiện theo từng loại credential

### 9.1. Password

- Theo dõi failure velocity theo principal, source và cohort.
- Phát hiện một source thử nhiều account với số password nhỏ.
- Phát hiện một account bị thử từ nhiều source.
- Correlate success với failure burst và action sau login.
- Theo dõi password reset/change và đăng nhập ngay sau đó.
- Không lưu password đã thử hoặc password plaintext trong telemetry.

### 9.2. MFA/TOTP/push

- Đếm challenge gửi, approve, deny, timeout và retry.
- Phát hiện push bombing: nhiều prompt không được chấp thuận trước một approve.
- Phát hiện OTP guessing và reuse trong time step theo policy server.
- Correlate MFA factor enrollment/removal với device/network/session.
- Cảnh báo recovery code được sử dụng, nhưng không log code.

### 9.3. Passkey/WebAuthn

- Ghi credential reference, RP ID/origin validation result và user verification result.
- Phát hiện challenge mismatch, origin sai, RP ID hash sai và credential mapping bất thường.
- Theo dõi enrollment/removal và thay đổi authenticator.
- Dùng sign counter như một tín hiệu phụ phù hợp với authenticator model.
- Không log raw authenticator data, client data chứa thông tin nhạy cảm hoặc private key.

### 9.4. Token và session

- Ghi token family reference, client, audience, scope, issued time và refresh outcome.
- Phát hiện refresh token reuse theo semantics của authorization server.
- Theo dõi session rotation, concurrent use và device binding change.
- Correlate token use sau logout/password reset/credential revocation.
- Không log raw token, JWT compact string hoặc cookie.

### 9.5. API key và client secret

- Gắn key ID với owner, client, environment, scope và expiry.
- Theo dõi key từ source/ASN/device mới và route mới.
- Phát hiện burst, unusual volume và access ngoài lịch sử.
- Theo dõi key rotation, key overlap và key cũ còn hoạt động.
- Không dùng raw key làm log field hoặc alert label.

### 9.6. Certificate và workload identity

- Theo dõi issuer, serial/fingerprint, SAN/SPIFFE ID, workload, node và expiry.
- Phát hiện certificate xuất hiện từ workload không tương ứng.
- Theo dõi issuance burst, renewal failure và attestation failure.
- Correlate workload deployment, service account và secret read.
- Alert khi workload bị terminate nhưng credential vẫn được sử dụng sau revocation SLA.

## 10. False positives và độ tin cậy của tín hiệu

Một hệ thống detection kém có thể khóa nhầm user đi công tác, service sau khi deploy hoặc partner đổi NAT. Cần đánh giá chất lượng từng tín hiệu:

- **Novelty:** mới đối với principal hay chỉ mới với log pipeline?
- **Reliability:** device identity có được xác minh hay chỉ dựa user-agent?
- **Coverage:** nguồn telemetry có đầy đủ hay một region đang mất event?
- **Specificity:** signal có phân biệt attack với retry hợp lệ không?
- **Impact:** nếu sai, hành động có thể làm gián đoạn bao nhiêu user/service?

### 10.1. Contextual allowlist

Có thể tạo ngoại lệ cho service account, health check hoặc deployment pipeline, nhưng:

- Gắn owner và lý do.
- Giới hạn principal, source, route và thời gian.
- Có expiry tự động.
- Ghi audit khi tạo/sửa.
- Review định kỳ.
- Không allowlist toàn bộ ASN hoặc IP range rộng chỉ để giảm alert.

### 10.2. Analyst feedback

Lưu disposition: true positive, false positive, benign expected change, duplicate, insufficient evidence. Dùng feedback để tuning rule nhưng không tự động học mọi quyết định analyst mà không review. Ghi version rule và baseline tại thời điểm alert để có thể tái hiện.

## 11. Correlation và incident timeline

Một alert đơn lẻ thường không đủ để hiểu sự kiện. Xây dựng timeline theo principal, session, credential family, device và request trace.

Ví dụ:

| Thời điểm | Event | Ý nghĩa |
| --- | --- | --- |
| 09:01 | 28 invalid-password events trên 19 account từ một source cluster | Password spraying có thể xảy ra |
| 09:03 | Login success cho account có quyền finance | Có thể credential đã bị đoán hoặc reuse |
| 09:04 | MFA push bị deny nhiều lần rồi approve | Có dấu hiệu fatigue hoặc user confusion |
| 09:06 | Refresh token family mới được tạo | Session mới hình thành |
| 09:08 | Recovery contact được cập nhật | Có thể là persistence attempt |
| 09:10 | API gọi export endpoint ngoài baseline | Hành vi sau đăng nhập đáng ngờ |

Investigator cần xem:

- Credential nào được dùng và phương thức xác minh.
- Token/session nào được tạo từ login.
- Thiết bị, network và location context có độ tin cậy ra sao.
- Những thay đổi factor/recovery/role xảy ra sau đó.
- Resource nào đã được truy cập hoặc dữ liệu nào có thể bị ảnh hưởng.
- Revocation đã lan tới gateway/downstream chưa.

## 12. Pipeline monitoring và detection architecture

~~~mermaid
flowchart LR
    S[IdP / API / Session / PKI / Workload events] --> C[Collector]
    C --> N[Normalize and redact]
    N --> Q[Event stream / SIEM]
    Q --> B[Baseline and correlation]
    B --> R[Rules / risk engine]
    R --> A[Alert and case management]
    A --> H[Human or SOAR response]
    H --> X[Step-up / revoke / contain]
    X --> F[Feedback and tuning]
    F --> B
~~~

### 12.1. Collector và ingestion

- Dùng transport có authentication và encryption.
- Định danh nguồn event và bảo vệ chống giả mạo.
- Deduplicate event khi source retry.
- Giữ event time và ingest time.
- Theo dõi event loss, lag và schema version.
- Tách pipeline security event khỏi log debug không có kiểm soát.

### 12.2. Normalization và redaction

Redact secret trước khi event đi vào stream chung. Nếu một source vô tình ghi Authorization header, collector nên loại hoặc mask trước khi index, alert và export. Đừng chờ analyst phát hiện rồi mới sửa.

### 12.3. Detection và alerting

- Rule có ID, version, owner, severity, window và rationale.
- Alert chứa principal reference, time range, evidence reference và recommended action.
- Gộp nhiều event liên quan thành một case.
- Deduplicate alert lặp.
- Rate limit alert và có suppression window có kiểm soát.
- Không suppression một alert chỉ vì nó xảy ra thường xuyên; có thể đó là attack đang tiếp diễn.

### 12.4. SOAR và automation

Automation có thể step-up, revoke session hoặc disable credential, nhưng cần guardrail:

- Kiểm tra confidence và phạm vi tác động.
- Có dry-run cho rule mới.
- Có approval cho hành động diện rộng hoặc không thể đảo ngược.
- Hành động phải idempotent và có audit.
- Có rollback/recovery path.
- Không để alert payload tùy ý điều khiển command hoặc query nguy hiểm.
- Không tự động khóa tài khoản quản trị khẩn cấp chỉ từ một tín hiệu yếu.

## 13. Privacy và bảo vệ telemetry

Monitoring credential có thể chứa dữ liệu cá nhân: IP, device, location, user-agent, account reference, lịch làm việc và hành vi truy cập. Thu thập quá mức có thể tạo rủi ro riêng tư và làm tăng tác động nếu SIEM bị compromise.

Nguyên tắc:

- Purpose limitation: chỉ thu thập dữ liệu phục vụ bảo vệ account/workload.
- Data minimization: ưu tiên stable reference, reason code và aggregate thay vì payload đầy đủ.
- Pseudonymization: hash/HMAC identifier với key được quản lý; nhớ rằng dữ liệu vẫn có thể được liên kết.
- Retention: đặt thời hạn theo mục đích, điều tra và yêu cầu pháp lý; xóa/aggregate khi hết hạn.
- Access control: phân quyền analyst, administrator, auditor và export.
- Encryption: bảo vệ dữ liệu khi truyền và lưu.
- Audit: ghi nhận ai truy cập hoặc export security telemetry.
- Segregation: không dùng telemetry authentication để theo dõi nhân viên ngoài mục đích đã thông báo.

Không ghi raw password, OTP, recovery code, bearer token, refresh token, session cookie, private key hoặc secret manager response. IP/geolocation không phải sự thật tuyệt đối; lưu confidence và tránh dùng chúng làm bằng chứng duy nhất.

## 14. Java: event schema và risk evaluation

Ví dụ Java minh họa cách tạo event đã được redaction và đánh giá một số tín hiệu. Trong production, nên dùng schema/version chuẩn của hệ thống, clock injection, immutable event và policy engine có kiểm thử.

~~~java
public record CredentialEvent(
    String eventId,
    Instant eventTime,
    String eventType,
    String outcome,
    String principalRef,
    String principalType,
    String credentialRef,
    String credentialType,
    String clientId,
    String audience,
    Set<String> scopes,
    String sessionRef,
    String deviceRef,
    String sourceNetworkRef,
    String reasonCode,
    String requestId
) {}

public record RiskSignal(
    String name,
    int score,
    String evidenceRef
) {}

public record RiskDecision(
    int score,
    String level,
    List<RiskSignal> signals
) {}
~~~

Event schema không có trường rawCredential hoặc authorizationHeader. Credential reference phải là ID/fingerprint an toàn, không phải giá trị có thể dùng để xác thực.

### 14.1. Rule evaluation minh họa

~~~java
RiskDecision evaluate(LoginContext context, AuthHistory history) {
    List<RiskSignal> signals = new ArrayList<>();

    if (history.failedAttemptsForPrincipal(context.principalRef(), Duration.ofMinutes(10)) >= 8) {
        signals.add(new RiskSignal(
            "principal_failure_velocity", 25, history.failureEvidenceRef()
        ));
    }

    if (history.distinctPrincipalsFromNetwork(context.sourceNetworkRef(),
            Duration.ofMinutes(10)) >= 12) {
        signals.add(new RiskSignal(
            "network_password_spray_pattern", 35, history.networkEvidenceRef()
        ));
    }

    if (context.isNewDevice() && !context.deviceIsManaged()) {
        signals.add(new RiskSignal(
            "new_unmanaged_device", 20, context.deviceEvidenceRef()
        ));
    }

    if (history.hasRecentRecoveryChange(context.principalRef(),
            Duration.ofHours(24))) {
        signals.add(new RiskSignal(
            "recent_recovery_change", 30, history.recoveryEvidenceRef()
        ));
    }

    int score = signals.stream().mapToInt(RiskSignal::score).sum();
    String level = score >= 70 ? "HIGH"
        : score >= 40 ? "MEDIUM"
        : score >= 15 ? "LOW"
        : "INFO";

    return new RiskDecision(Math.min(score, 100), level, List.copyOf(signals));
}
~~~

Các threshold chỉ là minh họa. Production cần:

- Tránh cộng trùng tín hiệu tương quan.
- Tách principal type, tenant, application và role.
- Tính quality/confidence của nguồn dữ liệu.
- Có suppression, cooldown và rate limit cho alert.
- Version rule/weight và lưu evidence reference.
- Không dùng score đơn độc để khóa account diện rộng.
- Bảo vệ history store và audit mọi automated response.

### 14.2. Response policy minh họa

~~~java
void applyDecision(RiskDecision decision, AuthenticationContext auth) {
    switch (decision.level()) {
        case "HIGH" -> {
            sessionService.revokeRelatedSessions(auth.principalRef());
            stepUpService.requireFreshStrongAuthentication(auth.principalRef());
            incidentService.openCase(decision, auth.safeEvidence());
        }
        case "MEDIUM" -> {
            stepUpService.requireAdditionalVerification(auth.principalRef());
            rateLimiter.tightenForPrincipal(auth.principalRef());
        }
        case "LOW" -> monitoring.recordForCorrelation(decision, auth.safeEvidence());
        default -> monitoring.recordBaselineObservation(decision, auth.safeEvidence());
    }
}
~~~

Đây là pseudocode, không phải policy khuyến nghị áp dụng nguyên trạng. Thu hồi session phải xác định phạm vi session/token family; step-up cần tránh MFA fatigue; mọi hành động phải idempotent, có audit và có cơ chế hỗ trợ người dùng hợp lệ.

## 15. Query và dashboard minh họa

Ví dụ query KQL-style để tìm source có nhiều account bị thử:

~~~text
AuthEvents
| where TimeGenerated > ago(10m)
| where EventType == "authentication.failure"
| where ReasonCode == "invalid_password"
| summarize
    FailureCount = count(),
    PrincipalCount = dcount(PrincipalRef)
  by SourceNetworkRef, bin(TimeGenerated, 5m)
| where FailureCount >= 20 and PrincipalCount >= 12
| order by FailureCount desc
~~~

Ví dụ query tìm login thành công sau một failure burst trên principal:

~~~text
let Failures =
    AuthEvents
    | where TimeGenerated > ago(30m)
    | where EventType == "authentication.failure"
    | summarize FailureCount = count()
      by PrincipalRef, SourceNetworkRef;
AuthEvents
| where TimeGenerated > ago(30m)
| where EventType == "authentication.success"
| join kind=leftouter Failures on PrincipalRef
| where FailureCount >= 5
| project TimeGenerated, PrincipalRef, SourceNetworkRef,
          DeviceRef, ClientId, FailureCount, RequestId
~~~

Query cần được điều chỉnh theo schema, event-time semantics và engine thực tế. Join theo principal có thể tạo false positive nếu failure thuộc người dùng hợp lệ; cần thêm source/device/time correlation và kiểm tra event sequence.

Dashboard nên có:

- Authentication success/failure theo principal type, client, tenant và method.
- Password spray/stuffing candidate theo source cluster và account cohort.
- MFA deny/timeout/approve sequence.
- New device/network và risk distribution.
- Token refresh/reuse, session create/revoke và audience/scope novelty.
- API key/certificate/workload issuance/use anomaly.
- Recovery/factor change trước hành động nhạy cảm.
- Detection latency, event loss, false positive rate và analyst disposition.
- Automated response count, rollback và support impact.

Không dùng raw email, IP hoặc token làm label cardinality cao nếu không cần. Dashboard chỉ hiển thị thông tin cá nhân cho nhóm có quyền.

## 16. Playbook phản ứng theo anomaly

### 16.1. Password spraying hoặc credential stuffing

1. Xác định account cohort, source cluster, application và time window.
2. Rate limit hoặc challenge traffic đáng ngờ; tránh khóa hàng loạt account hợp lệ.
3. Kiểm tra login success sau failure burst và hành động tiếp theo.
4. Với account có dấu hiệu takeover, revoke session/token family và yêu cầu xác thực mạnh.
5. Kiểm tra password reset, MFA enrollment, recovery contact và API access.
6. Phối hợp bot defense, IdP và support để giảm ảnh hưởng.

### 16.2. MFA fatigue

1. Đếm push deny/timeout và xác định account bị nhắm tới.
2. Liên hệ user qua kênh tin cậy nếu có login success đáng ngờ.
3. Revoke session mới, yêu cầu reauthentication bằng phương thức chống phishing.
4. Review factor enrollment và recovery changes.
5. Tuning policy để không cho push prompt liên tục và cung cấp cơ chế report prompt lạ.

### 16.3. Refresh token reuse hoặc session anomaly

1. Xác minh semantics của refresh token rotation và khả năng race từ client hợp lệ.
2. Kiểm tra token family, client/device, source network và event ordering.
3. Nếu reuse được xác nhận, revoke token family/session liên quan.
4. Buộc user/workload reauthenticate và kiểm tra resource đã truy cập.
5. Kiểm tra client storage, malware, logs và token propagation.

### 16.4. Workload/API key anomaly

1. Xác định key ID/principal, scope, audience, source workload và secret path.
2. So sánh với deployment/change event và baseline.
3. Tạm giới hạn scope/rate hoặc isolate workload theo risk.
4. Rotate/revoke key hoặc certificate nếu compromise có bằng chứng.
5. Kiểm tra secret manager audit, KMS operation và downstream API.
6. Khởi tạo lại workload từ image tin cậy và xác minh identity.

## 17. Đo lường chất lượng detection

Một detection system cần được đo như một sản phẩm vận hành:

| Metric | Ý nghĩa |
| --- | --- |
| Precision | Tỷ lệ alert được xác nhận là đáng ngờ trong số alert đã điều tra |
| Recall/coverage | Tỷ lệ attack simulation hoặc incident đã biết được phát hiện |
| False positive rate | Tỷ lệ benign event bị gắn nhãn sai |
| Detection latency | Thời gian từ event đầu tiên đến alert |
| Response latency | Thời gian từ alert đến containment |
| Event completeness | Tỷ lệ event cần thiết đã được ingest |
| Rule health | Rule chạy thành công, không bị lỗi schema hoặc stale data |
| Analyst workload | Số case và thời gian xử lý theo severity |
| Containment effectiveness | Mức độ credential/session bị chặn sau hành động |

Precision/recall cần định nghĩa trên tập dữ liệu có nhãn và cửa sổ thời gian rõ. Một alert bị đóng là false positive không nhất thiết chứng minh rule vô ích; có thể thiếu evidence hoặc analyst chưa đủ dữ liệu.

### 17.1. Detection testing

- Replay event fixture đã ẩn danh để kiểm tra rule.
- Tạo synthetic event cho brute force, spraying, refresh reuse và workload anomaly.
- Test negative case như NAT đông người, deployment, travel, VPN và client retry.
- Chaos test event delay, duplicate, out-of-order và source outage.
- Kiểm tra redaction bằng secret canary giả, không dùng credential thật.
- Đo detection latency và alert deduplication.
- Review threshold và exclusion sau mỗi incident/major release.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Chỉ đếm failure theo IP | Bỏ sót distributed attack, khóa nhầm NAT users | Correlate principal, source cluster, device và time |
| Coi mọi login từ quốc gia mới là compromise | False positive do VPN/travel | Dùng location như một tín hiệu có confidence |
| Log raw password/token/OTP | SIEM trở thành kho credential | Redaction tại nguồn/collector và test |
| Không phân biệt user và workload | Baseline sai, alert nhiễu | Principal type và baseline riêng |
| Alert cho mọi lần dùng token | Alert fatigue | Theo dõi semantics, audience, sender binding và hành vi |
| Dùng score bí ẩn | Analyst không thể giải thích quyết định | Evidence, weights, version và reason code |
| Tự động khóa account theo tín hiệu yếu | Gián đoạn diện rộng, attacker có thể DoS user | Step-up, rate limit và confidence threshold |
| Baseline học cả incident | Attacker đầu độc baseline | Exclude incident, review drift và version baseline |
| Không theo dõi event loss | Detection bỏ sót mà không biết | Completeness/lag monitoring |
| Exclusion không expiry | Attacker ẩn trong allowlist | Owner, scope, TTL và review |
| SIEM access quá rộng | Lộ hành vi và dữ liệu cá nhân | RBAC, encryption, audit và retention |
| SOAR command từ alert payload | Injection hoặc hành động sai phạm vi | Schema validation, allowlisted actions, approval |
| Không correlate factor/recovery changes | Bỏ sót persistence sau takeover | Liên kết auth, recovery, session và privilege events |
| Revoke chỉ tại IdP | Token/session còn hoạt động ở downstream | End-to-end revocation propagation |
| Không kiểm tra client retry | False positive token reuse | Model concurrency và idempotent client behavior |

## 19. Ma trận kiểm thử credential anomaly

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Một user nhập sai password vài lần | Không tự động coi là account takeover |
| Một source thử ít password trên nhiều account | Rule spraying phát hiện theo distinct principal và window |
| Nhiều source thử cùng account | Correlation phát hiện distributed guessing |
| Login success sau failure burst và MFA deny | Risk tăng, tạo alert có evidence |
| Nhiều push MFA bị từ chối rồi approve | Phát hiện fatigue pattern |
| OTP sai liên tiếp trên một account | Rate limit/challenge và audit |
| Passkey origin hoặc RP ID sai | Authentication validator từ chối; anomaly event được ghi |
| Passkey enrollment sau recovery bất thường | Correlate factor change với recovery/login |
| WebAuthn counter không tăng với authenticator hỗ trợ sync | Không kết luận compromise chỉ từ counter |
| Refresh token cũ bị reuse theo rotation policy | Revoke token family và tạo case |
| Hai refresh request hợp lệ đồng thời | Không gắn nhãn compromise nếu concurrency được policy hỗ trợ |
| Access token có audience sai | Authentication/resource validation từ chối, không chỉ anomaly alert |
| API key dormant đột nhiên gọi admin endpoint | Risk tăng và alert |
| Certificate dùng từ workload khác | Identity/policy từ chối và anomaly được ghi |
| Workload xin scope ngoài baseline | Policy deny hoặc step-up/approval theo rule |
| Secret manager read burst | Alert theo principal/path và workload context |
| CI từ fork xin production credential | Federation policy từ chối và audit |
| Workload đã terminate vẫn dùng credential | Revocation SLA alert và containment |
| User đổi thiết bị hợp lệ | Risk được điều chỉnh bằng device enrollment/step-up, tránh khóa account |
| VPN làm IP thay đổi | Không kết luận compromise chỉ từ IP |
| Event tới trễ hoặc out-of-order | Correlation dùng event_time và ingest_time, không ghép sai |
| Event bị duplicate | Ingestion deduplicate theo event ID |
| Log chứa secret canary | Redaction test phát hiện trước khi vào SIEM |
| Rule bị tắt hoặc threshold đổi | Administrative audit và alert |
| SOAR revoke cùng incident nhiều lần | Action idempotent, không tạo side effect lặp |
| Analyst đánh dấu false positive | Feedback được ghi, rule tuning có review/version |
| Baseline bị drift đột ngột | Change review phát hiện, không tự động học mù |

### Tình huống thực hành

Một công ty có 8.000 tài khoản. Trong 12 phút, telemetry ghi nhận 1.600 lần password failure trên 900 account từ nhiều IP cloud. Ba tài khoản có login success; một tài khoản sau đó nhận 14 MFA push, 12 lần deny và 2 lần timeout trước khi approve. Trong 5 phút tiếp theo, tài khoản này tạo refresh token mới, thêm recovery email và gọi API export dữ liệu. Cùng thời gian đó, một service account hợp lệ có burst đọc secret do deployment mới.

**Yêu cầu:** phân loại, điều tra và phản ứng mà không làm gián đoạn toàn bộ công ty.

**Hướng phân tích:**

1. Phân loại password failures là candidate distributed spraying/stuffing; correlate theo account cohort, IP/ASN, client và cadence thay vì chỉ từng IP.
2. Ưu tiên ba account có login success; tài khoản có MFA deny/timeout trước approve và recovery change là risk cao.
3. Revoke session/token family của account nghi compromise, buộc reauthentication chống phishing và kiểm tra export activity.
4. Tạm giới hạn export endpoint hoặc yêu cầu step-up/approval cho account rủi ro; không khóa toàn bộ 8.000 account.
5. Kiểm tra recovery email, factor enrollment và session mới; khôi phục account qua kênh tin cậy nếu compromise được xác nhận.
6. Với service account, đối chiếu deployment ID, workload identity, secret path và change approval. Nếu đúng deployment, cập nhật baseline có owner; nếu không, giới hạn/revoke credential và isolate workload.
7. Bảo toàn audit timeline, không export raw token/OTP vào case.
8. Tuning detection cho distributed source, MFA fatigue, post-login recovery change và service deployment context; đo false positive/latency sau xử lý.

## 20. Câu hỏi tự kiểm tra

1. **Credential anomaly là gì?** Hành vi phát hành, xác minh hoặc sử dụng credential khác đáng kể so với baseline/policy và cần được đánh giá.
2. **Anomaly có đồng nghĩa compromise không?** Không. Nó là tín hiệu; cần context, evidence và policy phản ứng.
3. **Vì sao chỉ đếm failure theo IP không đủ?** Attacker có thể phân tán IP, còn nhiều người dùng hợp lệ có thể chung NAT/VPN.
4. **Credential telemetry có nên chứa raw token hoặc OTP không?** Không. Dùng reference/fingerprint an toàn và reason code.
5. **Password spraying khác brute force thế nào?** Spraying thử ít password trên nhiều account; brute force thường tập trung nhiều lần thử vào một account hoặc credential.
6. **Vì sao login success sau failure burst cần correlation?** Có thể là người dùng nhập đúng sau lỗi; risk tăng khi kèm source/device novelty, MFA anomaly hoặc action nhạy cảm.
7. **Refresh token reuse có luôn là tấn công không?** Không. Cần xét rotation semantics, concurrency, retry và client behavior.
8. **Risk score nên quyết định gì?** Hỗ trợ chọn step-up, rate limit, revoke hoặc điều tra theo mức độ và confidence; không thay protocol validation.
9. **Baseline có thể bị đầu độc không?** Có. Loại trừ incident, version baseline và review drift.
10. **Monitoring phải bảo vệ privacy thế nào?** Purpose limitation, data minimization, pseudonymization, retention, RBAC, encryption và audit.

**Ghi nhớ:** Phát hiện credential anomaly bằng cách kết hợp telemetry có cấu trúc từ IdP, MFA, passkey, token/session, API, PKI, secret manager và workload platform. Chuẩn hóa principal, credential reference, thời gian và context; xây baseline theo role/environment; correlate chuỗi sự kiện thay vì tin một tín hiệu đơn lẻ. Risk score cần giải thích được, phản ứng theo confidence và impact, đồng thời bảo vệ telemetry khỏi chứa raw secret hoặc dữ liệu cá nhân không cần thiết.
