# Audit evidence

**Audit evidence** là dữ liệu được tạo, bảo vệ và lưu giữ để chứng minh một sự kiện hoặc quyết định đã xảy ra trong hệ thống: ai hoặc thành phần nào khởi tạo hành động, hành động nhắm tới tài khoản hay tài nguyên nào, hệ thống đã xác minh điều gì, policy nào được áp dụng, kết quả ra sao và bằng chứng được thu thập từ đâu. Trong xác thực, audit evidence giúp tái dựng vòng đời credential, authentication, token, session, identity linking, recovery và thay đổi quyền.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Các luồng này tạo ra những quyết định bảo mật quan trọng. Audit evidence cho phép tổ chức điều tra đăng nhập đáng ngờ, chứng minh thao tác quản trị, đánh giá việc thực thi policy, phát hiện thay đổi trái phép và hỗ trợ kiểm toán hoặc phản ứng sự cố.

Điểm cốt lõi: **audit evidence phải đáng tin, có ngữ cảnh, có thể kiểm chứng và được bảo vệ trong toàn bộ vòng đời**. Một dòng log ghi “login success” không đủ nếu không biết nguồn phát, principal, authentication method, thời điểm, kết quả policy và tính toàn vẹn của bản ghi. Ngược lại, thu thập quá nhiều dữ liệu như password, OTP, bearer token hoặc biometric template sẽ biến hệ thống audit thành nơi lưu trữ bí mật mới.

## 1. Audit evidence là gì?

Audit evidence là tập hợp record, metadata, liên kết và kiểm soát giúp người có thẩm quyền xác định một sự kiện đã diễn ra và đánh giá sự kiện đó có tuân thủ policy hay không. Evidence có thể được tạo bởi IdP, application, API gateway, session service, token service, certificate authority, recovery workflow hoặc hệ thống quản trị.

Trong authentication, evidence có thể trả lời:
- Một login attempt có được thực hiện hay không?
- Principal được xác định theo issuer và subject nào?
- Hệ thống đã kiểm tra password, passkey, certificate hay MFA?
- Authentication có thành công, thất bại hay bị policy từ chối?
- Token được phát hành cho audience và scope nào?
- Session được tạo, gia hạn, logout hay revoke khi nào?
- Recovery method hoặc authenticator nào đã được thêm/xóa?
- Ai đã thay đổi authentication policy hoặc signing key?
- Một request bị từ chối vì token invalid, session expired hay thiếu quyền?
- Bản ghi evidence có bị sửa, xóa, thiếu hoặc đến muộn không?

### 1.1. Evidence không chỉ là log

| Thành phần | Mục đích | Giá trị trong audit |
| --- | --- | --- |
| **Audit event** | Ghi nhận một sự kiện hoặc quyết định có ý nghĩa bảo mật. | Nguồn evidence chính, có schema và actor/target/result. |
| **Application log** | Hỗ trợ debug hoạt động của ứng dụng. | Có thể bổ sung ngữ cảnh nhưng không mặc nhiên đáng tin hoặc đầy đủ. |
| **Metric** | Đo số lượng, tỷ lệ, độ trễ và xu hướng. | Phát hiện bất thường ở quy mô tổng hợp; không chứng minh hành động cá nhân. |
| **Distributed trace** | Nối các bước xử lý của một request qua nhiều service. | Hỗ trợ điều tra luồng kỹ thuật; có thể bị sampling. |
| **Configuration history** | Lưu thay đổi policy, issuer, key và quyền. | Giải thích vì sao một quyết định được đưa ra tại thời điểm đó. |
| **External evidence** | Ticket, approval, change request hoặc xác nhận từ hệ thống có thẩm quyền. | Bổ sung lý do, phê duyệt và trách nhiệm vận hành. |

Không mặc định mọi log đều là audit evidence. Log có thể bị rotate, thiếu actor, chứa dữ liệu không chuẩn hóa hoặc cho phép ứng dụng ghi nội dung tùy ý. Muốn dùng log làm evidence, cần xác định nguồn, schema, access control, integrity, retention và quy trình truy xuất.

### 1.2. Evidence khác với kết luận điều tra

Evidence là dữ liệu ghi nhận; kết luận là diễn giải dựa trên nhiều nguồn. Ví dụ một bản ghi cho thấy login thành công từ một IP không tự chứng minh chủ tài khoản là người thực hiện. Có thể token bị đánh cắp, thiết bị bị chia sẻ hoặc IP thuộc NAT/VPN.

Báo cáo điều tra cần tách:
- **Observed fact:** dữ liệu hệ thống ghi nhận.
- **Interpretation:** ý nghĩa có thể suy ra.
- **Confidence:** mức độ chắc chắn và giới hạn.
- **Unknowns:** dữ liệu thiếu hoặc nguồn không đáng tin.
- **Action:** containment, revoke, recovery hoặc follow-up.

Không biến một correlation yếu thành khẳng định danh tính hoặc ý định.

## 2. Mục tiêu và nguyên tắc thiết kế

Một hệ thống audit authentication tốt cần đạt các mục tiêu sau:

1. **Accountability:** xác định actor hoặc service principal chịu trách nhiệm cho hành động.
2. **Traceability:** nối sự kiện với transaction, request, session hoặc change có liên quan.
3. **Integrity:** phát hiện sửa đổi, xóa hoặc chèn bản ghi trái phép.
4. **Completeness:** ghi nhận các sự kiện quan trọng và phát hiện khoảng trống thu thập.
5. **Context:** giữ đủ thông tin để hiểu quyết định đã xảy ra theo policy nào.
6. **Confidentiality:** không lưu credential hoặc dữ liệu cá nhân vượt quá mục đích.
7. **Availability:** evidence sẵn sàng cho điều tra trong thời hạn cần thiết.
8. **Verifiability:** người kiểm toán có thể kiểm tra nguồn, thời gian, chuỗi lưu trữ và quyền truy cập.

### 2.1. Nguyên tắc data minimization

Chỉ thu thập trường cần để chứng minh sự kiện. Audit không cần bản sao password, OTP, recovery code, private key hoặc token thô. Với dữ liệu định danh, dùng subject reference hoặc internal identifier theo policy và giới hạn người có thể truy cập.

### 2.2. Evidence phải gắn với policy tại thời điểm sự kiện

Một quyết định authentication phụ thuộc cấu hình tại thời điểm xảy ra: issuer allowlist, audience, algorithm, MFA requirement, assurance mapping, session timeout và revocation policy. Nếu policy thay đổi sau đó, auditor vẫn cần biết bản nào đã được áp dụng.

Ghi policy version, configuration revision hoặc immutable change reference. Không chỉ lưu “policy=default” nếu giá trị này có thể thay đổi theo thời gian.

## 3. Sự kiện authentication cần ghi nhận

Không phải mọi request đều cần một audit event riêng. Ưu tiên sự kiện có ảnh hưởng đến danh tính, quyền, credential, session hoặc quyết định bảo mật.

### 3.1. Authentication lifecycle

Các sự kiện thường cần:
- Login attempt bắt đầu, thành công, thất bại hoặc bị từ chối.
- Re-authentication hoặc step-up challenge được yêu cầu và hoàn tất.
- MFA factor được đăng ký, xác minh, thay thế hoặc xóa.
- Passkey/WebAuthn credential được đăng ký, sử dụng hoặc revoke.
- Certificate được cấp, gia hạn, thu hồi hoặc từ chối.
- Account bị khóa, mở khóa, disable hoặc enable.
- Password được đổi hoặc reset, chỉ ghi metadata và outcome.
- Recovery được khởi tạo, phê duyệt, từ chối hoặc hoàn tất.
- Identity được link, unlink hoặc merge theo quy trình.
- Session được tạo, refresh, expire, logout hoặc revoke.
- Token được phát hành, introspect, rotate hoặc revoke.
- Signing key, JWKS hoặc trust configuration được thay đổi.

### 3.2. Security và administrative events

Cũng cần xem xét:
- Thay đổi issuer, audience, client registration hoặc redirect URI.
- Thay đổi authentication/authorization policy.
- Cấp hoặc thu hồi role, group, tenant membership.
- Tạo, xóa hoặc rotate API key/client secret.
- Thay đổi certificate trust store hoặc CA configuration.
- Break-glass activation và emergency access.
- Thay đổi retention, audit sink, collector hoặc access policy.
- Truy cập, export, delete hoặc thay đổi audit evidence.
- Alert được xác nhận, đóng hoặc chuyển thành incident.

### 3.3. Không ghi mọi request thành audit event

Một API có thể nhận hàng triệu request mỗi giờ. Ghi một audit event cho mọi lần đọc thông thường có thể làm tăng chi phí, gây nhiễu và tạo thêm dữ liệu nhạy cảm. Chọn sự kiện theo rủi ro, tác động và yêu cầu truy vết. Với request volume cao, dùng metric/trace cho vận hành và audit event cho hành động có ý nghĩa bảo mật.

## 4. Event schema cho audit evidence

Schema thống nhất giúp các service phát sự kiện có thể kết hợp và kiểm tra. Một event nên có envelope chung và payload theo loại sự kiện.

### 4.1. Các trường cơ bản

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **event_id** | ID duy nhất của event. | Dùng để deduplicate và tham chiếu. |
| **event_type** | Loại sự kiện. | Enum có version, không dùng free text tùy ý. |
| **event_version** | Phiên bản schema. | Hỗ trợ migration và parser compatibility. |
| **occurred_at** | Thời điểm nguồn tạo sự kiện. | Timestamp UTC, nguồn clock được quản lý. |
| **recorded_at** | Thời điểm collector ghi nhận. | Phân biệt event time và ingest time. |
| **actor** | User, service hoặc administrator khởi tạo. | Principal reference đã xác minh. |
| **subject/target** | Account, session, credential hoặc resource bị tác động. | Chỉ ghi định danh cần thiết. |
| **action** | Hành động được thực hiện. | Chuẩn hóa theo taxonomy. |
| **outcome** | Success, failure, denied hoặc pending. | Phân biệt kết quả kỹ thuật và policy. |
| **reason_code** | Lý do chuẩn hóa. | Không nhúng raw input hoặc secret. |
| **source** | Service/component phát event. | Có service identity và deployment context. |
| **correlation_id** | Nối event trong cùng transaction. | Không dùng làm metric label. |
| **policy_reference** | Policy/config revision được áp dụng. | Có thể tham chiếu kho cấu hình bất biến. |
| **evidence_reference** | Liên kết tới evidence bổ sung. | Có access control và retention riêng. |

Không phải event nào cũng có user actor. Một token refresh do workload thực hiện có thể có service principal; một system cleanup có thể có system actor. Không gán một user làm actor nếu không có bằng chứng.

### 4.2. Ví dụ event JSON

Ví dụ dưới đây dùng dữ liệu giả, minh họa cấu trúc tối thiểu và không chứa token/password:

    {
      "event_id": "evt-test-000184",
      "event_type": "authentication.login",
      "event_version": 1,
      "occurred_at": "2026-11-22T09:15:31.420Z",
      "recorded_at": "2026-11-22T09:15:31.487Z",
      "actor": {
        "type": "user",
        "issuer": "https://id.example.test",
        "subject_ref": "sub-ref-7f31"
      },
      "target": {
        "type": "account",
        "account_ref": "acct-ref-0192"
      },
      "action": "login",
      "outcome": "success",
      "reason_code": "primary_auth_verified",
      "authentication": {
        "method": "passkey",
        "assurance_class": "phishing_resistant",
        "step_up": false
      },
      "source": {
        "service": "identity-gateway",
        "environment": "test",
        "region": "region-a"
      },
      "correlation_id": "txn-test-0042",
      "policy_reference": "auth-policy-rev-18"
    }

Ví dụ chỉ minh họa một schema có thể dùng. Tên trường và assurance class phải khớp protocol, policy và taxonomy thực tế. Không ghi raw authenticator data, assertion, cookie hoặc credential vào event chỉ vì chúng có trong request.

### 4.3. Event versioning

Khi schema thay đổi:
- Tăng event_version theo quy ước.
- Giữ parser có khả năng đọc version còn trong retention.
- Không đổi ý nghĩa field hiện hữu mà không migration.
- Định nghĩa required/optional field.
- Kiểm tra event producer và consumer tương thích.
- Ghi thời điểm rollout và service version.

Schema evolution không được làm mất actor, outcome hoặc timestamp cần cho evidence.

## 5. Actor, subject và nguồn danh tính

Một audit record đáng tin cần phân biệt người khởi tạo hành động, danh tính bị tác động và service thực thi.

### 5.1. Actor

Actor có thể là:
- End user đã xác minh.
- Service principal hoặc workload identity.
- Administrator.
- Helpdesk operator.
- Automated policy engine.
- System process.

Với hành động được ủy quyền, cần ghi actor thực hiện và principal thay mặt nếu protocol hỗ trợ delegation. Không ghi một service account duy nhất cho mọi thao tác nếu cần truy vết user initiator.

### 5.2. Subject/target

Target có thể là account, credential, session, token family, client registration, certificate, policy hoặc resource. Dùng reference ổn định, giới hạn quyền truy cập và tránh lưu dữ liệu trực tiếp nếu không cần.

Một event thay đổi MFA cần xác định account và loại factor bị thay đổi, nhưng không cần ghi seed hoặc OTP. Một event revoke token cần reference token family hoặc grant, không cần lưu bearer token.

### 5.3. Identity namespace

Subject chỉ duy nhất trong namespace/issuer phù hợp. Nếu hệ thống dùng federation, ghi issuer reference cùng subject reference. Không dựa riêng vào email hoặc display name vì có thể thay đổi, trùng hoặc chưa được xác minh.

Nếu mapping identity thay đổi, lưu reference tới link/unlink transaction và mapping version để có thể tái dựng quyết định tại thời điểm đó.

## 6. Evidence cho từng loại credential và authentication

### 6.1. Password authentication

Có thể ghi:
- Login attempt outcome.
- Password verifier version hoặc policy reference.
- Account lock/rate-limit decision.
- Password change/reset event.
- Kênh reset đã được xác minh ở mức phân loại.

Không ghi password, password hash, reset token, câu trả lời bảo mật hoặc nội dung form. Nếu cần phân tích password policy, ghi policy version và outcome, không ghi password thực.

### 6.2. MFA

Có thể ghi:
- Factor type: TOTP, push, security key hoặc phương thức khác.
- Challenge issued, approved, denied, timeout.
- Number of attempts theo aggregate hoặc bounded count.
- Factor enrollment/removal.
- Recovery/fallback path được dùng.
- Policy và assurance mapping.

Không ghi OTP, TOTP seed, push approval secret, recovery code hoặc biometric data. Push event nên có challenge reference không thể dùng để approve lại.

### 6.3. Passkey và WebAuthn

Có thể ghi:
- Credential registration/credential reference.
- RP ID/origin validation outcome.
- User verification requirement/result.
- Signature counter hoặc backup eligibility/state nếu policy cần và protocol cho phép.
- Credential added/removed/revoked.
- Challenge transaction reference.

Không ghi private key, raw authenticator assertion hoặc dữ liệu nhạy cảm không cần thiết. Credential ID cũng có thể là identifier liên kết lâu dài; bảo vệ theo privacy policy.

### 6.4. Certificate và mTLS

Có thể ghi:
- Certificate issuer/CA reference.
- Serial number hoặc fingerprint theo policy.
- Subject/SAN mapping result.
- Chain validation, expiry và revocation outcome.
- Client certificate authentication result.
- Certificate issue/renew/revoke event.

Không ghi private key hoặc secret của keystore. Fingerprint/serial vẫn có thể liên kết tới một thiết bị hoặc workload, nên hạn chế quyền và retention.

## 7. Evidence cho token và session

### 7.1. Token issuance

Ghi:
- Issuer/client reference.
- Token type/profile.
- Audience/resource class.
- Scope/authorization class được cấp.
- Token issue outcome và thời điểm.
- Policy reference và grant/transaction reference.

Không ghi raw access token, refresh token, ID Token hoặc JWT đầy đủ. Nếu cần đối chiếu token trong incident, dùng keyed fingerprint hoặc internal token-family reference với thiết kế chống lạm dụng và quyền truy cập riêng.

### 7.2. Token validation

Ghi kết quả và reason code đã chuẩn hóa:
- Signature valid/invalid.
- Issuer/audience/type validation.
- Expired/not-yet-valid.
- Unknown key hoặc key rotation state.
- Introspection active/inactive/unavailable.
- Revoked hoặc sender proof invalid.
- Scope/authorization outcome ở bước tiếp theo.

Không log raw token header/payload để “debug”. Claims có thể chứa PII, role hoặc tenant data; chỉ ghi field tối thiểu đã được phê duyệt.

### 7.3. Session lifecycle

Ghi:
- Session created, renewed, reauthenticated, expired, logged out hoặc revoked.
- Session type và client class.
- Actor/target reference.
- Reason code.
- Policy/timeout version.
- Revocation transaction và propagation result nếu có.

Session ID thường là bearer reference hoặc có thể giúp liên kết hoạt động. Không đưa raw session ID vào event stream rộng. Dùng reference bảo vệ hoặc keyed pseudonym theo mục đích điều tra.

### 7.4. Refresh và reuse detection

Ghi token family reference, rotation generation hoặc transaction reference nếu cần; outcome; reuse detection reason; family revoke decision; client class; policy version.

Không ghi refresh token. Một refresh failure không tự động chứng minh token theft; reason code cần phân biệt network failure, invalid grant, expired, revoked, reuse detection và concurrency conflict.

## 8. Evidence cho identity linking và account recovery

### 8.1. Identity linking

Ghi:
- Actor khởi tạo link.
- Issuer và subject namespace được liên kết.
- Account target reference.
- Proof-of-control result cho từng identity.
- Approval/policy reference.
- Link/unlink outcome.
- Thời điểm và transaction ID.

Không tự link chỉ vì email giống nhau. Audit evidence phải cho thấy hai phía đã được xác minh và policy mapping đã được áp dụng.

### 8.2. Account recovery

Ghi:
- Recovery request được khởi tạo.
- Recovery channel class hoặc proofing method.
- Verification/approval outcome.
- Actor requester, verifier và approver khi có.
- Authenticator được thêm hoặc revoke ở mức type/reference.
- Session/token revoke actions.
- Recovery completed/rejected/expired.
- Notification attempt và result.

Không ghi recovery code, OTP, ảnh giấy tờ, biometric template hoặc nội dung chứng minh danh tính thô vào event chung. Nếu evidence đặc biệt cần giữ, lưu trong kho riêng có mã hóa, access control, retention và legal basis phù hợp.

### 8.3. Helpdesk và break-glass

Ghi người yêu cầu, người xác minh, người phê duyệt, reason/ticket reference, scope, thời gian bắt đầu/kết thúc và hành động thực hiện. Với break-glass, ghi cả activation, access use, deactivation, credential rotation và post-incident review.

Tách người đề nghị khỏi người phê duyệt cho account đặc quyền khi policy yêu cầu dual control.

## 9. Timestamp, ordering và clock integrity

Thời gian là yếu tố quan trọng khi tái dựng authentication flow, token issue/expiry, session revoke và incident timeline.

### 9.1. Event time và ingest time

- **occurred_at:** thời điểm source ghi nhận hành động.
- **recorded_at:** thời điểm collector nhận/ghi event.
- **processed_at:** thời điểm pipeline xử lý hoặc index event nếu cần.

Khoảng chênh giữa các thời điểm giúp phát hiện pipeline lag. Không ghi đè event time bằng ingest time rồi mất thông tin nguồn.

### 9.2. Clock synchronization

- Dùng UTC và định dạng timestamp có timezone rõ.
- Đồng bộ clock bằng nguồn được quản lý.
- Theo dõi clock drift của IdP, gateway, service và collector.
- Ghi độ trễ ingest và cảnh báo khi vượt ngưỡng.
- Xác định nguồn timestamp cho event do queue hoặc batch tạo.
- Không tin timestamp do client tự khai làm thời gian xác thực chính.

Clock drift có thể làm sai thứ tự event hoặc đánh giá token/session. Khi điều tra, ghi rõ uncertainty nếu clock của một nguồn không đáng tin.

### 9.3. Ordering và sequence

Distributed system không luôn có thứ tự toàn cục. Có thể dùng event sequence theo aggregate, transaction ID hoặc version để sắp xếp các event liên quan. Không suy luận rằng event đến collector sau luôn xảy ra sau event khác.

Nếu một account có recovery và login đồng thời, cần correlation/sequence đủ để xác định transition nào đã commit trước.

## 10. Integrity và tamper resistance

Audit evidence chỉ có giá trị nếu có thể phát hiện sửa đổi trái phép và kiểm soát ai có quyền thay đổi.

### 10.1. Append-only và restricted write

- Producer chỉ được gửi event theo schema, không được sửa/xóa event đã lưu.
- Collector ghi vào storage bằng identity riêng.
- Reader và writer có quyền tách biệt.
- Admin hệ thống audit không mặc nhiên có quyền xóa evidence.
- Có audit riêng cho thao tác truy cập, export, retention và configuration.
- Dùng storage hỗ trợ retention lock/immutability khi yêu cầu.

Append-only ở API không đủ nếu administrator có thể sửa trực tiếp database hoặc object storage. Cần bảo vệ cả control plane, credentials, backups và quyền cloud/storage admin.

### 10.2. Hash và chữ ký

Có thể dùng hash, hash chain, batch digest hoặc digital signature để phát hiện thay đổi:
- Canonicalize event trước khi hash.
- Gắn event với sequence hoặc previous hash.
- Ký batch digest bằng key được quản lý độc lập.
- Lưu key ID và signature metadata.
- Verify định kỳ và khi export evidence.
- Bảo vệ signing key trong HSM/KMS hoặc boundary phù hợp.

Hash đơn lẻ không chứng minh nguồn phát. Attacker có quyền sửa cả event lẫn hash có thể tạo lại giá trị. Chữ ký chỉ hữu ích nếu private key và trust anchor được bảo vệ, key lifecycle được quản lý và verifier kiểm tra đúng.

### 10.3. Hash chain limitations

Hash chain có thể phát hiện sửa đổi hoặc xóa event ở giữa nếu anchor cuối được bảo vệ độc lập. Nó không tự chứng minh event bị thiếu trước khi collector nhận, cũng không bảo vệ trước producer đã bị compromise và phát event giả.

Cần kết hợp authenticated producer, sequence/reconciliation, independent checkpoint, restricted storage và monitoring cho pipeline gaps.

### 10.4. WORM và immutable storage

Write Once Read Many hoặc retention lock có thể ngăn sửa/xóa trong thời hạn đã cấu hình. Cần kiểm tra:
- Ai có quyền bật/tắt retention lock.
- Có thể rút ngắn retention không.
- Backup và replica có cùng integrity không.
- Export có giữ signature/hash metadata không.
- Legal hold có được áp dụng đúng không.
- Hết hạn retention thì deletion được kiểm soát thế nào.

Không coi nhãn “immutable” của storage là đủ nếu tài khoản quản trị có thể xóa bucket, key mã hóa hoặc policy bảo vệ.

## 11. Provenance và chain of custody

Provenance trả lời evidence đến từ đâu, được thu thập, chuyển giao, xử lý và lưu giữ bởi ai. Chain of custody đặc biệt quan trọng khi evidence dùng trong incident, kiểm toán hoặc quy trình pháp lý.

### 11.1. Ghi nhận nguồn

Mỗi nguồn nên có:
- Service identity hoặc producer certificate.
- Environment, deployment/version và region.
- Schema version.
- Collector identity.
- Transport authentication và encryption.
- Event timestamp và ingest timestamp.
- Batch/partition/sequence reference nếu có.

### 11.2. Bảo toàn evidence khi điều tra

Khi export evidence:
1. Xác định câu hỏi và phạm vi cần thu thập.
2. Dùng truy vấn có phân quyền và ghi ticket/reason.
3. Ghi nguồn, thời gian, filter và query version.
4. Export theo định dạng có thể kiểm tra.
5. Tính hash hoặc signature của artifact export.
6. Lưu bản gốc trong storage kiểm soát.
7. Ghi người tạo, người nhận và các lần chuyển giao.
8. Không sửa bản gốc; mọi redaction/annotation tạo bản dẫn xuất có liên kết tới original.
9. Ghi công cụ và phiên bản dùng để parse/verify.
10. Hạn chế bản sao và xóa bản tạm theo policy.

### 11.3. Evidence có thể đến muộn hoặc thiếu

Queue, retry, outage hoặc producer crash có thể tạo gap. Pipeline cần:
- Sequence/offset tracking.
- Dead-letter queue và retry visibility.
- Drop counter và source heartbeat.
- Reconciliation giữa event producer và collector.
- Gap detection và alert.
- Quy trình ghi nhận source unavailable trong incident.

Không tự tạo event giả để lấp gap. Ghi rõ evidence không có và nguyên nhân đã biết.

## 12. Confidentiality, privacy và redaction

Audit evidence thường chứa metadata nhạy cảm. Bảo vệ tính toàn vẹn mà bỏ qua confidentiality vẫn có thể gây lộ danh tính, thói quen và thông tin bảo mật.

### 12.1. Những dữ liệu không được ghi

Không ghi plaintext:
- Password hoặc password reset secret.
- OTP, TOTP seed và recovery code.
- Access token, refresh token, ID Token hoặc session cookie.
- Private key, client secret, API key hoặc HMAC secret.
- Biometric template hoặc dữ liệu sinh trắc học thô.
- Raw authorization header.
- Full request body có credential.
- Private assertion/authenticator payload nếu không có yêu cầu đặc biệt được phê duyệt.

### 12.2. Dữ liệu cần đánh giá

Các trường sau vẫn có thể nhạy cảm:
- Email, phone, username.
- IP address và approximate location.
- Device ID, certificate fingerprint, credential ID.
- Subject/tenant/role/group.
- User agent và browser attributes.
- Authentication method và recovery activity.
- Failure pattern có thể tiết lộ account tồn tại.

Chỉ lưu khi có mục đích rõ, retention phù hợp và access control. Cân nhắc pseudonymization hoặc aggregation khi không cần nhận diện trực tiếp.

### 12.3. Redaction ở nguồn

Redact trước khi event rời producer hoặc trước khi vào queue/log sink. Mask ở dashboard không xóa raw value khỏi storage, archive hoặc backup.

Dùng schema allowlist thay vì blacklist tên field đơn thuần. Secret có thể xuất hiện trong nested object, exception hoặc arbitrary text. Kiểm thử serialization và logging path bằng synthetic secret.

## 13. Access control và separation of duties

Audit system cần kiểm soát ai có thể tạo, đọc, export, sửa retention hoặc thay đổi pipeline.

### 13.1. Vai trò tham khảo

| Vai trò | Quyền phù hợp |
| --- | --- |
| **Event producer** | Gửi event theo schema, không đọc toàn bộ evidence. |
| **Collector** | Xác thực producer, validate schema và ghi event. |
| **Operator** | Xem dashboard/aggregate, không mặc nhiên xem PII. |
| **Investigator** | Truy vấn evidence chi tiết theo case và thời hạn. |
| **Auditor** | Đọc evidence và kiểm tra integrity, không sửa record. |
| **Storage administrator** | Quản lý hạ tầng với kiểm soát dual control và audit riêng. |
| **Key custodian** | Quản lý signing/encryption key theo quy trình tách biệt. |

### 13.2. Just-in-time access

Truy cập dữ liệu chi tiết nên:
- Có mục đích và ticket/case.
- Có thời hạn ngắn.
- Dùng step-up authentication.
- Chỉ mở phạm vi cần thiết.
- Được audit.
- Được review sau khi kết thúc.

Không cấp quyền đọc mọi audit evidence lâu dài cho tất cả developer hoặc support staff chỉ vì họ cần debug một sự cố.

### 13.3. Audit việc truy cập audit

Ghi nhận:
- Ai query hoặc export evidence.
- Phạm vi, thời điểm và reason.
- Ai thay đổi retention/access policy.
- Ai tạo hoặc thu hồi signing key.
- Ai xóa/đặt legal hold hoặc tạo bản dẫn xuất.
- Query có thất bại hoặc bị từ chối không.

Nếu audit administrator có thể xóa log truy cập của chính mình, cần nguồn giám sát độc lập hoặc separation of duties.

## 14. Retention, deletion và legal hold

Retention phải cân bằng yêu cầu điều tra, kiểm toán, privacy, chi phí và nghĩa vụ pháp lý. Không có một thời hạn phù hợp cho mọi loại event.

### 14.1. Xác định retention theo loại evidence

Có thể phân loại:
- Authentication event thông thường.
- Privileged/admin action.
- Credential enrollment/removal.
- Account recovery và identity linking.
- Token/key lifecycle.
- Incident evidence.
- Audit access/export event.
- Debug/operational log không phải evidence chính.

Mỗi loại có mục đích, rủi ro và retention riêng. Chính sách cần được tổ chức, pháp chế và privacy owner phê duyệt theo khu vực áp dụng.

### 14.2. Deletion

Khi hết retention:
- Xóa theo lifecycle rule có kiểm soát.
- Xử lý replica, backup và archive theo policy.
- Ghi deletion evidence mà không giữ lại dữ liệu đã cần xóa.
- Xác minh retention lock không bị bỏ qua.
- Giữ audit trail cho thao tác xóa và policy version.

Xóa record khỏi primary database không có nghĩa bản sao đã biến mất khỏi backup, export hoặc analytics warehouse.

### 14.3. Legal hold

Khi có legal hold hoặc incident hold:
- Xác định phạm vi account, event type và thời gian.
- Chỉ người có thẩm quyền tạo/gỡ hold.
- Ghi lý do, approver và thời điểm.
- Ngăn deletion theo policy đã phê duyệt.
- Theo dõi các bản sao và export liên quan.
- Gỡ hold có kiểm soát khi hết căn cứ.

Không tự suy diễn nghĩa vụ retention cụ thể từ một tiêu chuẩn hoặc luật nếu chưa xác định jurisdiction, loại dữ liệu và vai trò tổ chức.

## 15. Evidence collection architecture

Một pipeline tham khảo:

    Identity / Application / Gateway / CA
                    |
                    v
          Authenticated producers
                    |
                    v
          Schema validation + redaction
                    |
                    v
            Durable event queue
                    |
                    v
          Integrity / sequence checks
                    |
                    v
          Append-only evidence store
                    |
          +---------+----------+
          |                    |
          v                    v
     Monitoring             Archive / hold
          |
          v
    Authorized investigation

### 15.1. Producer

Producer phát event tại điểm có semantics rõ: IdP ghi authentication result, token service ghi issuance/refresh, session service ghi revoke, admin service ghi policy change. Mỗi producer có service identity riêng và chỉ được gửi loại event được cấp quyền.

### 15.2. Collector

Collector cần:
- Xác thực nguồn gửi.
- Validate schema/version.
- Giới hạn kích thước và rate.
- Redact hoặc reject field không được phép.
- Ghi received timestamp.
- Deduplicate theo event ID khi cần.
- Giữ metadata provenance.
- Không cho producer ghi đè event đã tồn tại.

### 15.3. Queue và delivery semantics

Queue có thể cung cấp at-least-once delivery, nên duplicate event cần được xử lý idempotently. Exactly-once end-to-end thường là một thuộc tính khó bảo đảm; đừng tuyên bố nếu chỉ có consumer dedup cục bộ.

Cần xác định:
- Retry policy.
- Dead-letter handling.
- Ordering scope.
- Retention trong queue.
- Encryption in transit/at rest.
- Consumer lag và backpressure.
- Behavior khi evidence store không sẵn sàng.

Nếu audit evidence bắt buộc cho một thao tác nhạy cảm, xác định transaction có được commit khi audit sink không xác nhận hay không. Có thể dùng transactional outbox hoặc durable local journal để tránh commit action mà không có record tương ứng. Không để một lỗi telemetry không quan trọng làm dừng mọi login.

### 15.4. Transactional outbox

Với thay đổi account, credential hoặc privilege, outbox giúp ghi business state và audit event trong cùng transaction database. Một publisher gửi event sau đó và retry idempotently.

Cần kiểm tra:
- Business transaction rollback thì event cũng không được phát như đã commit.
- Event commit nhưng publisher chưa gửi vẫn được retry.
- Duplicate delivery không tạo duplicate evidence logic.
- Outbox cleanup không xóa event trước khi delivery được xác nhận.
- Payload không chứa secret.

## 16. Kiểm chứng evidence

Evidence cần có quy trình xác minh định kỳ và khi export.

### 16.1. Kiểm tra integrity

- Verify signature/hash của batch.
- Kiểm tra sequence gap và duplicate.
- Kiểm tra event schema/version.
- Kiểm tra source identity và certificate validity.
- Kiểm tra timestamp/ingest delay.
- Đối chiếu event với configuration revision.
- Kiểm tra access/export/deletion audit.

### 16.2. Kiểm tra completeness

Dùng source heartbeat, event count reconciliation, queue offsets và transaction reference để xác định khoảng trống. Một khoảng thời gian không có event có thể là không có hoạt động hoặc producer bị lỗi; cần heartbeat/health evidence để phân biệt.

### 16.3. Kiểm tra semantic consistency

Ví dụ:
- Không có session.created nếu authentication outcome là denied.
- Không có token issued khi grant bị từ chối.
- Recovery completed phải có proofing/approval reference phù hợp.
- Credential revoke phải được phản ánh trong lifecycle state.
- Policy change phải có actor/approval.
- Logout local không được mô tả là global logout nếu IdP chưa xác nhận.

Đây là kiểm tra logic liên sự kiện; không nên chỉ xác minh chữ ký từng record.

## 17. Điều tra authentication incident bằng evidence

### 17.1. Dựng timeline

Một timeline account takeover có thể gồm:
1. Password/MFA failures tăng.
2. Login success từ một session hoặc device mới.
3. Recovery method được thay đổi.
4. Passkey hoặc authenticator mới được thêm.
5. Refresh token được sử dụng từ client khác.
6. Role hoặc linked identity thay đổi.
7. Session cũ bị revoke hoặc vẫn hoạt động.
8. Admin/helpdesk action diễn ra.

Mỗi bước cần event source và timestamp. Không kết luận tất cả do cùng actor nếu chưa có correlation đủ tin cậy.

### 17.2. Correlation

Có thể dùng:
- Account/subject reference.
- Issuer và tenant.
- Session/token-family reference đã bảo vệ.
- Transaction/request ID.
- Device/credential reference theo policy.
- Event sequence và timestamp.
- Source service/deployment.

Correlation ID giúp nối event nhưng không tự xác thực actor. Nếu client tự gửi correlation ID, server cần tạo hoặc validate transaction context thay vì tin giá trị tùy ý.

### 17.3. Ghi nhận mức độ chắc chắn

Báo cáo điều tra cần chỉ rõ:
- Evidence đã xác minh integrity hay chưa.
- Nguồn nào authoritative.
- Nguồn nào có thể bị attacker kiểm soát.
- Clock uncertainty.
- Event bị thiếu hoặc sampling.
- Suy luận nào là giả thuyết.
- Dữ liệu nào chưa thể kết luận.

## 18. Compliance và audit readiness

Audit evidence có thể hỗ trợ chứng minh control được thiết kế và vận hành, nhưng chỉ có log không tự chứng minh compliance.

### 18.1. Mapping control tới evidence

Tạo mapping:
- Control requirement.
- System/process chịu trách nhiệm.
- Expected event/evidence.
- Source of truth.
- Owner.
- Frequency.
- Retention.
- Integrity/access controls.
- Test procedure.
- Exception/remediation.

Ví dụ: control yêu cầu privileged access phải dùng MFA. Evidence cần cho thấy policy version, authentication method/assurance, principal, action và outcome ở mức phù hợp. Một dashboard chỉ đếm MFA success không chứng minh mọi privileged action đều có MFA.

### 18.2. Evidence package

Một package cho audit có thể gồm:
- Scope và period.
- Control mapping.
- Event extracts đã được phê duyệt.
- Schema và data dictionary.
- Source/provenance.
- Hash/signature verification result.
- Query/filter và tool version.
- Access/approval reference.
- Known gaps và limitations.
- Retention/legal hold status.

Chỉ export dữ liệu tối thiểu cần thiết. Bản dẫn xuất đã redact phải giữ reference/hash tới original và ghi rõ phép biến đổi.

### 18.3. Continuous control monitoring

Có thể tự động kiểm tra:
- Tỷ lệ event producer đang gửi heartbeat.
- Số event schema validation failure.
- Evidence store integrity verification.
- Retention policy drift.
- Privileged actions thiếu approval reference.
- Credential enrollment không có corresponding audit event.
- Revoke event không được propagate.
- Audit export/access bất thường.

Continuous monitoring giúp phát hiện control drift nhưng không thay thế kiểm toán độc lập và review ngoại lệ.

## 19. Ví dụ thực hành: kiểm tra một lần recovery và đăng ký passkey

**Bối cảnh:** Một nhân viên báo mất điện thoại, yêu cầu khôi phục account và sau đó đăng ký passkey trên thiết bị mới. Vài giờ sau, security team điều tra vì có một lần login từ thiết bị cũ.

**Evidence cần thu thập:**
- Recovery request ID, thời điểm và channel class.
- Actor requester, helpdesk verifier và approver.
- Proofing method và outcome, không lấy bản sao secret.
- Recovery policy version và approval reference.
- Session/token/device revoke events.
- Passkey enrollment event, RP ID/origin validation result và credential reference.
- Login event trên thiết bị cũ, token/session reference và outcome.
- Notification attempts tới channel đã xác minh.
- Clock/ingest metadata và integrity verification.

**Cách phân tích:**

1. Xác minh recovery event có source identity, signature/hash và policy reference.
2. Kiểm tra approval có gắn đúng account, transaction và target device không.
3. Xác định thời điểm server commit recovery và thời điểm passkey mới active.
4. Đối chiếu revoke propagation với login trên thiết bị cũ.
5. Kiểm tra login cũ dùng session trước recovery, credential khác hay một request đã được gửi trước revoke.
6. Nếu session revoked vẫn được chấp nhận sau propagation target, mở incident về enforcement.
7. Nếu event thiếu hoặc timestamp không đồng bộ, ghi rõ giới hạn và không kết luận quá mức.
8. Bảo toàn evidence export, hash/signature và chain of custody.

**Câu hỏi:** Nếu audit log chỉ ghi “recovery success” và “passkey added”, có đủ để chứng minh quy trình an toàn không? Không. Cần biết ai yêu cầu/phê duyệt, proofing và policy nào được dùng, credential/session cũ được xử lý ra sao và event có integrity/provenance hay không.

## 20. Checklist thiết kế audit evidence

- [ ] Xác định mục đích audit, control và câu hỏi điều tra cần trả lời.
- [ ] Liệt kê event quan trọng trong authentication, MFA, passkey, certificate, token, session, linking và recovery.
- [ ] Phân biệt audit event, application log, metric, trace và configuration history.
- [ ] Chuẩn hóa event schema, event ID, version, timestamp, actor, target, outcome và reason.
- [ ] Ghi issuer/subject namespace đúng; không định danh chỉ bằng email/display name.
- [ ] Gắn policy/config revision để tái dựng quyết định tại thời điểm xảy ra.
- [ ] Không ghi password, OTP, recovery code, bearer token, cookie, private key hoặc biometric template.
- [ ] Redact tại nguồn/collector trước queue và storage.
- [ ] Bảo vệ producer bằng service identity và transport encryption.
- [ ] Tách quyền producer, collector, reader, investigator, auditor, storage admin và key custodian.
- [ ] Dùng append-only/retention lock khi yêu cầu và bảo vệ control plane.
- [ ] Thiết kế hash/signature/checkpoint với key lifecycle được quản lý.
- [ ] Theo dõi sequence gap, duplicate, queue lag, source heartbeat và event loss.
- [ ] Phân biệt occurred time, recorded time và processed time; dùng UTC.
- [ ] Định nghĩa retention, deletion, backup và legal hold theo loại evidence.
- [ ] Audit mọi truy vấn, export, access policy change và deletion.
- [ ] Dùng transactional outbox hoặc cơ chế tương đương cho thay đổi nhạy cảm cần evidence bền vững.
- [ ] Kiểm tra schema, integrity, provenance, completeness và semantic consistency.
- [ ] Có runbook bảo toàn evidence và chain of custody khi incident.
- [ ] Ghi rõ uncertainty, missing data, sampling và giới hạn suy luận.
- [ ] Mapping control tới evidence source, owner, frequency và test procedure.
- [ ] Kiểm thử redaction bằng synthetic secret và rà soát raw queue/archive/backup.
- [ ] Diễn tập export, verify signature/hash, legal hold và restore evidence.

## 21. Câu hỏi tự kiểm tra

**1. Audit evidence là gì?**  
Là record và metadata được bảo vệ để chứng minh sự kiện hoặc quyết định đã xảy ra, từ nguồn nào, do actor nào và theo policy nào.

**2. Audit evidence khác application log thế nào?**  
Audit evidence có schema, provenance, integrity, access control và retention được thiết kế cho accountability; application log chủ yếu phục vụ vận hành/debug và không mặc nhiên đáp ứng các thuộc tính đó.

**3. Vì sao không ghi raw access token hoặc password?**  
Vì evidence store sẽ trở thành nơi lưu credential có thể replay hoặc bị lạm dụng; audit chỉ cần outcome và reference an toàn.

**4. Event cần những trường nào?**  
Tối thiểu thường gồm event ID/type/version, timestamp, actor, target, action, outcome, source, reason và policy/correlation reference phù hợp.

**5. Vì sao phải phân biệt issuer và subject?**  
Subject chỉ duy nhất trong namespace của issuer; cùng một subject string ở hai issuer không nhất thiết là cùng identity.

**6. Hash chain có chứng minh event source là đáng tin không?**  
Không. Hash chain giúp phát hiện sửa đổi trong chuỗi đã được anchor; cần authenticated producer, key protection và checkpoint độc lập để bảo vệ provenance.

**7. occurred_at và recorded_at khác nhau thế nào?**  
occurred_at là thời điểm nguồn ghi nhận hành động; recorded_at là lúc collector nhận/lưu event. Chênh lệch giúp phát hiện ingest delay và clock drift.

**8. Metric có thể thay audit event không?**  
Không. Metric aggregate xu hướng; audit event lưu quyết định và ngữ cảnh cụ thể. Metric không đủ để tái dựng actor/target/action.

**9. Làm thế nào giữ evidence có thể kiểm chứng?**  
Dùng producer identity, schema/version, timestamp, append-only storage, hash/signature/checkpoint, access audit và chain of custody.

**10. Một audit package cần thể hiện giới hạn gì?**  
Nguồn, phạm vi, thời gian, query/filter, integrity result, redaction, sampling/gap, clock uncertainty và những kết luận chưa thể xác minh.

**Ghi nhớ:** Audit evidence giúp chứng minh và tái dựng quyết định xác thực, nhưng chỉ đáng tin khi có provenance, integrity, context, completeness và access control. Hãy ghi nhận event quan trọng theo schema nhất quán, giữ policy version, bảo vệ chuỗi lưu trữ, giới hạn dữ liệu nhạy cảm và duy trì chain of custody. Không lưu secret để chứng minh rằng secret đã được dùng; hãy lưu bằng chứng an toàn về phương thức, quyết định và kết quả.
