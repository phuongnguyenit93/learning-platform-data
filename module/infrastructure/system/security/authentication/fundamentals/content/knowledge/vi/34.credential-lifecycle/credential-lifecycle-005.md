# Credential suspension — Tạm đình chỉ credential có kiểm soát

## 1. Credential suspension là gì?

**Credential suspension** (tạm đình chỉ credential) là thao tác tạm thời ngăn một credential được sử dụng để xác thực hoặc chứng minh quyền truy cập, trong khi vẫn giữ bản ghi và thông tin quản trị cần thiết để điều tra, khôi phục hoặc kích hoạt lại nếu đủ điều kiện. Credential có thể là mật khẩu, passkey, khóa bảo mật, TOTP secret, client certificate, API key hoặc khóa của một thiết bị.

Ví dụ: nhân viên báo mất điện thoại có passkey và ứng dụng TOTP. Hệ thống đánh dấu các credential gắn với thiết bị đó là suspended để chúng không được chấp nhận cho lần đăng nhập mới. Bản ghi vẫn được giữ để điều tra và đối chiếu audit. Nếu thiết bị được tìm lại và tổ chức xác minh không có dấu hiệu bị xâm nhập, policy có thể cho phép khôi phục; nếu nghi private key hoặc secret đã bị sao chép, credential phải bị revoke và thay thế.

Trong chương **Credential lifecycle** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, suspension liên hệ với credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần hiểu cách tạm ngừng một credential mà không nhầm với khóa toàn bộ tài khoản, thu hồi vĩnh viễn credential hoặc chỉ xóa thiết bị khỏi giao diện; đồng thời mô hình hóa ranh giới tin cậy, chống replay, phishing và lạm dụng đăng nhập.

**Suspended credential không được chấp nhận cho xác thực mới.** Việc giữ lại bản ghi không có nghĩa credential vẫn hợp lệ. Verifier phải kiểm tra trạng thái authoritative ở phía server và từ chối credential đã bị đình chỉ, kể cả khi chữ ký hoặc mật khẩu về mặt mật mã vẫn đúng.

## 2. Phân biệt suspend, revoke, expire, disable và delete

Các thao tác vòng đời credential có tác động khác nhau:

| Trạng thái/thao tác | Ý nghĩa | Có thể khôi phục? |
| --- | --- | --- |
| **Active** | Credential được phép sử dụng theo policy. | Không cần. |
| **Suspended** | Tạm thời không được dùng; bản ghi được giữ để xem xét hoặc khôi phục. | Có thể, sau khi xác minh và được policy cho phép. |
| **Revoked** | Credential bị thu hồi và không còn được tin cậy. | Thông thường không; cần đăng ký credential mới. |
| **Expired** | Credential đã quá thời hạn hợp lệ. | Thường cần gia hạn hoặc cấp mới theo policy. |
| **Disabled** | Trạng thái vận hành tổng quát; semantics phụ thuộc hệ thống. | Có thể, nhưng phải định nghĩa rõ. |
| **Deleted** | Bản ghi hoặc material được xóa theo chính sách retention. | Thường không thể khôi phục; có thể làm mất bằng chứng điều tra. |
| **Replaced** | Credential cũ đã được thay bằng credential mới. | Credential cũ không nên tự hoạt động trở lại. |

**Suspension có tính tạm thời; revocation biểu thị mất niềm tin.** Nếu private key bị lộ, TOTP secret bị sao chép hoặc API key xuất hiện trong repository công khai, chỉ suspend trong thời gian ngắn rồi resume lại chính credential đó có thể đưa bí mật đã lộ trở lại trạng thái hợp lệ. Khi đã có bằng chứng compromise, cần revoke và thay thế.

Từ “disable” thường được dùng không nhất quán. Thiết kế API, database và audit cần quy định rõ disable tương đương suspended hay revoked, ai được thực hiện và điều kiện khôi phục.

## 3. Khi nào cần tạm đình chỉ credential?

Một số tình huống thường yêu cầu suspension:

| Tình huống | Credential có thể bị suspend | Mục đích |
| --- | --- | --- |
| Người dùng báo mất thiết bị | Passkey, khóa bảo mật, TOTP hoặc device key gắn với thiết bị | Chặn sử dụng trong lúc xác minh thiết bị có bị chiếm hay không. |
| Phát hiện đăng nhập bất thường | Credential vừa được dùng hoặc credential có liên quan | Tạm giữ để điều tra và yêu cầu xác thực khác. |
| Nhân viên nghỉ phép dài hạn | Credential truy cập nội bộ theo policy | Tạm ngừng truy cập trong thời gian không làm việc. |
| Thiết bị doanh nghiệp không còn đạt posture | Device certificate hoặc device-bound key | Không cho thiết bị không đạt policy tiếp tục xác thực. |
| Thay đổi hệ thống hoặc bảo trì | Client certificate/API key cụ thể | Tạm ngừng một integration trong thời gian chuyển đổi. |
| Nghi ngờ secret bị chia sẻ | API key, password credential hoặc TOTP secret | Ngăn tiếp tục sử dụng trong lúc đánh giá phạm vi lộ lọt. |
| Quy trình kiểm soát nội bộ | Credential đặc quyền | Tạm giữ cho tới khi hoàn tất phê duyệt hoặc rà soát. |

Không phải mọi tình huống đều nên dùng suspension. Nếu đã xác nhận credential bị xâm nhập, revoke là phù hợp hơn. Nếu chỉ có lỗi dịch vụ, không nên đánh dấu credential của người dùng bị compromise. Cần phân biệt sự cố xác thực, rủi ro credential và lỗi hạ tầng.

## 4. Credential suspension khác account suspension

Đình chỉ một credential chỉ tác động đến một phương thức xác thực hoặc một binding cụ thể. Đình chỉ tài khoản tác động đến quyền sử dụng tài khoản nói chung.

Ví dụ, một người dùng có hai passkey, một TOTP authenticator và mật khẩu:

- Suspend passkey trên điện thoại bị mất: khóa đó không còn được dùng; passkey dự phòng và các phương thức khác có thể vẫn hoạt động theo policy.
- Suspend toàn bộ MFA: người dùng có thể còn mật khẩu nhưng không đạt policy yêu cầu MFA.
- Suspend account: mọi credential của tài khoản bị từ chối hoặc bị giới hạn theo account policy.

| Phạm vi | Đối tượng bị tác động | Ví dụ |
| --- | --- | --- |
| Credential-level | Một credential ID, secret hoặc key binding | Một passkey cụ thể. |
| Authenticator/device-level | Một thiết bị hoặc nhóm credential gắn với thiết bị | Điện thoại bị mất có TOTP và push key. |
| Account-level | Toàn bộ tài khoản | Nhân viên bị đình chỉ quyền truy cập. |
| Client/integration-level | Một ứng dụng hoặc workload | API client certificate bị tạm ngừng. |
| Tenant-level | Một tổ chức hoặc miền quản trị | Tạm dừng toàn bộ integration của tenant khi điều tra. |

Không suy ra rằng suspend một passkey đồng nghĩa account bị khóa. Ngược lại, không được để một credential khác tiếp tục cấp quyền nếu policy yêu cầu account-level suspension. Mỗi request phải kiểm tra cả credential state, account state, tenant state và authorization policy.

## 5. Mô hình ranh giới tin cậy

Suspension cần được thực thi ở verifier hoặc dịch vụ quản lý credential có thẩm quyền:

~~~mermaid
flowchart LR
    U["Người dùng / Admin / Risk engine"]
    C["Client / authenticator"]
    M["Credential management service"]
    R[("Credential registry<br/>status + version")]
    V["Authentication verifier"]
    S[("Session / token service")]
    A[("Audit / notification")]
    U -->|"Yêu cầu suspend"| M
    C -->|"Bằng chứng đăng nhập"| V
    M <--> R
    V -->|"Tra trạng thái authoritative"| R
    V -->|"Chỉ xác thực khi active"| S
    M --> A
    V --> A
~~~

Client có thể báo mất thiết bị hoặc gửi yêu cầu suspend, nhưng server quyết định trạng thái cuối cùng. Risk engine hoặc administrator có thể khởi tạo suspension theo quyền được cấp. Verifier phải đọc trạng thái credential từ nguồn authoritative hoặc cache có cơ chế invalidation phù hợp.

Không tin cờ do client gửi như credential_active=true. Không chỉ ẩn credential khỏi giao diện rồi vẫn để verifier chấp nhận. Nếu nhiều dịch vụ kiểm tra cùng một credential, cần đồng bộ trạng thái và định nghĩa hành vi khi registry không sẵn sàng.

## 6. Vòng đời trạng thái credential

Một state machine tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Provision / enrollment
    Pending --> Active: Verify và activate
    Pending --> Expired: Hết hạn
    Active --> Suspended: Tạm đình chỉ
    Suspended --> Active: Resume được phê duyệt
    Suspended --> Revoked: Xác nhận compromise / thay thế
    Active --> Revoked: Thu hồi trực tiếp
    Active --> Expired: Hết hạn
    Expired --> Revoked: Đóng vòng đời
    Active --> Replaced: Credential mới đã thay thế
    Suspended --> Replaced: Credential mới thay thế
    Revoked --> [*]
    Replaced --> [*]
~~~

Các trạng thái phải có semantics rõ:

- **Pending:** đang enrollment hoặc provision; chưa được dùng cho đăng nhập.
- **Active:** verifier có thể chấp nhận nếu các điều kiện khác đạt.
- **Suspended:** verifier từ chối; trạng thái có thể được xem xét để resume.
- **Revoked:** verifier từ chối vĩnh viễn; không được resume.
- **Expired:** không còn trong thời hạn; cần cấp/gia hạn theo policy.
- **Replaced:** credential cũ đã được thay; không quay lại active.

Một số hệ thống có thể không lưu trạng thái Replaced riêng mà lưu revoked cùng replacement reference. Điều quan trọng là không có chuyển trạng thái ngầm từ revoked/expired sang active.

### Bất biến trạng thái

- Mỗi credential có ID duy nhất và thuộc principal/tenant xác định.
- Chỉ transition được policy cho phép mới có thể commit.
- Verifier từ chối mọi credential không ở trạng thái active.
- Resume chỉ áp dụng với suspended credential và phải có bằng chứng/approval phù hợp.
- Revoked/replaced không thể resume.
- Mọi transition ghi actor, reason, timestamp và correlation ID.
- Cache trạng thái phải được invalidated hoặc giới hạn stale time theo risk.

## 7. Ai có quyền suspend và resume?

Quyền thay đổi credential cần được phân tách:

| Actor | Quyền có thể được cấp | Kiểm soát |
| --- | --- | --- |
| Chủ tài khoản | Báo mất và yêu cầu suspend credential của mình | Xác thực session còn tin cậy hoặc recovery channel phù hợp; yêu cầu được xử lý ngay theo policy. |
| Risk engine | Tự động suspend khi đạt ngưỡng rủi ro | Rule có version, audit, giới hạn false positive và quy trình review. |
| Helpdesk | Khởi tạo hoặc thực hiện thao tác được ủy quyền | Xác minh độc lập, least privilege, dual control cho thay đổi nhạy cảm. |
| Security administrator | Suspend/revoke theo incident | Phê duyệt, lý do bắt buộc và audit bất biến. |
| System operator | Vận hành dịch vụ/registry | Không mặc nhiên có quyền impersonate user hoặc đọc secret. |
| Service owner | Quản lý credential của integration thuộc phạm vi | Chỉ trong tenant/client được giao và có kiểm soát. |

Resume thường rủi ro hơn suspend vì nó mở lại một phương thức xác thực. Không nên để cùng một yêu cầu hỗ trợ yếu có thể vừa suspend vừa resume credential mà không có bước xác minh bổ sung. Với tài khoản đặc quyền hoặc credential đã bị nghi compromise, yêu cầu phê duyệt độc lập hoặc đăng ký credential mới.

## 8. Suspend và resume bằng chứng mật mã

Với passkey/WebAuthn, private key nằm ở authenticator và server giữ public key cùng credential ID. Server có thể suspend credential bằng cách thay trạng thái ở credential registry; authenticator vẫn giữ private key, nhưng verifier không chấp nhận assertion từ credential đó.

Với client certificate, suspension cần được thể hiện qua trạng thái phía PKI/credential registry và cơ chế xác minh mà relying service sử dụng. CRL/OCSP hoặc status service có thể cung cấp trạng thái thu hồi; semantics suspended riêng có thể cần registry/policy bổ sung. Không giả định mọi verifier hiểu trạng thái “suspended” trong cùng một cách.

Với TOTP, server ngừng xác minh mã bằng secret binding đang suspended. Secret có thể vẫn tồn tại trong kho được bảo vệ, nhưng không được chấp nhận. Nếu nghi secret bị sao chép, nên revoke và provision secret mới thay vì resume.

Với API key, server có thể từ chối key ID cụ thể ở gateway/resource server. Nếu key đã lộ, hãy rotate và revoke key cũ; giữ bản ghi metadata để điều tra.

## 9. Tạm đình chỉ passkey và security key

Một passkey thường có credential ID, public key và metadata như user handle, RP ID, thời điểm đăng ký, authenticator properties và trạng thái. Khi cần suspend:

1. Xác định đúng credential ID thuộc principal và tenant.
2. Xác minh quyền yêu cầu hoặc căn cứ risk/admin.
3. Đổi trạng thái credential sang suspended bằng transaction nguyên tử.
4. Làm mới cache/revocation view ở tất cả verifier liên quan.
5. Hủy challenge hoặc giao dịch đăng nhập đang chờ sử dụng credential đó nếu policy yêu cầu.
6. Đánh giá session/token được tạo từ credential đó.
7. Gửi thông báo an toàn cho chủ tài khoản.

### Resume passkey

Chỉ resume khi có căn cứ cho thấy thiết bị/credential vẫn do chủ tài khoản kiểm soát và không có dấu hiệu lộ private key. Có thể yêu cầu xác minh bằng passkey khác, identity proofing hoặc helpdesk recovery có phê duyệt.

Nếu thiết bị bị mất ngoài môi trường kiểm soát hoặc nghi private key bị sao chép, không resume chỉ vì người dùng tìm lại thiết bị. Revoke credential cũ và đăng ký passkey mới với challenge mới.

### Credential đồng bộ

Passkey có thể được đồng bộ giữa các thiết bị thông qua hệ sinh thái của nhà cung cấp. Vì vậy, “mất một thiết bị” không nhất thiết đồng nghĩa private key chỉ tồn tại trên thiết bị đó. Policy cần hiểu loại passkey, trạng thái đồng bộ và mức assurance được chấp nhận; không suy đoán rằng revoke một device record luôn thu hồi mọi bản sao credential.

## 10. Tạm đình chỉ mật khẩu và TOTP

### Password credential

Mật khẩu thường là một credential gắn với account, không phải một thiết bị riêng. Suspend password có thể có nghĩa:

- Tạm thời không cho password authentication, nhưng vẫn cho passkey hoặc federation.
- Buộc người dùng đi qua password reset trước khi dùng lại.
- Tạm giữ password login trong lúc điều tra credential stuffing hoặc compromise.

Không cần xóa password hash chỉ để suspend. Server có thể lưu trạng thái password credential riêng và từ chối password verifier khi trạng thái không active. Nếu password đã bị lộ, nên reset/revoke theo policy, kiểm tra reuse và thu hồi session liên quan.

### TOTP authenticator

TOTP binding gắn secret với account và có thể gắn nhãn thiết bị. Khi suspend, verifier không chấp nhận mã từ binding đó, kể cả mã tính đúng. Nếu secret bị lộ, resume không khắc phục được rủi ro; phải revoke binding và enrollment secret mới.

TOTP cần replay protection theo policy. Một mã hợp lệ đã được tiêu thụ không được chấp nhận lại trong cùng time step nếu hệ thống triển khai chống replay. Suspend/resume không được reset bộ đếm replay theo cách cho phép mã cũ được sử dụng lại.

## 11. Tạm đình chỉ certificate và API key

### Client certificate

Certificate có thời hạn và trạng thái PKI. Cần phân biệt:

- **Suspended trong registry nội bộ:** tổ chức tạm ngừng chấp nhận certificate dù chưa revoke ở CA.
- **Revoked tại CA:** certificate không còn đáng tin theo cơ chế PKI và relying party phải kiểm tra trạng thái.
- **Expired:** đã quá NotAfter; không được chấp nhận.
- **Renewed/replaced:** certificate mới được cấp; certificate cũ cần xử lý theo policy.

Nếu dùng CRL/OCSP, phải hiểu cache, freshness, responder availability và hành vi fail-open/fail-closed của verifier. Với hệ thống có rủi ro cao, không nên chấp nhận certificate chỉ vì chưa có phản hồi trạng thái khi policy yêu cầu kiểm tra revocation. Cần thiết kế availability và cache để không làm suy yếu kiểm tra.

### API key và workload credential

API key thường là bearer secret. Khi tạm đình chỉ:

- Đánh dấu key ID suspended ở authoritative registry/gateway.
- Từ chối request mới sử dụng key đó.
- Kiểm tra các integration khác có dùng chung key không.
- Xác định session/job/token được tạo từ key đó.
- Nếu key bị lộ, tạo key mới, cập nhật consumer rồi revoke key cũ.
- Không hiển thị secret đầy đủ trong console hoặc log.

Không dùng một API key chung cho nhiều ứng dụng hoặc môi trường nếu cần khả năng suspend/revoke độc lập. Tách credential theo workload và scope để giới hạn blast radius.

## 12. Suspension có tác động gì tới session và token?

Đây là điểm dễ bị bỏ sót. Suspend credential ngăn credential đó được dùng cho xác thực mới, nhưng không tự động làm mọi session hoặc token đã phát hành trước đó mất hiệu lực.

| Tài sản | Tác động khi suspend credential |
| --- | --- |
| Credential | Verifier từ chối sử dụng mới theo trạng thái suspended. |
| Pending authentication challenge | Có thể cần hủy nếu challenge được tạo bằng credential bị suspend. |
| RP/IdP session | Cần policy quyết định giữ, giới hạn hoặc revoke. |
| Access token | Có thể tiếp tục hợp lệ đến exp nếu resource server chỉ kiểm tra token tự chứa. |
| Refresh token | Có thể tiếp tục cấp token mới nếu grant/token family chưa bị revoke. |
| API key-derived session | Cần xác định các session/job/token được tạo từ key đó. |
| Federation session | Có thể vẫn active ở IdP hoặc RP độc lập với credential cụ thể. |

### Liên kết credential với authentication event

Để thu hồi chính xác, hệ thống nên ghi credential ID hoặc authentication event reference đã tạo session/token. Khi credential bị suspend vì nghi compromise, policy có thể:

- Revoke các session được tạo sau thời điểm nghi ngờ.
- Revoke tất cả session có authentication event dùng credential đó.
- Thu hồi refresh token family liên quan.
- Yêu cầu step-up bằng credential khác cho session còn lại.
- Chỉ giữ phiên có bằng chứng độc lập và rủi ro thấp.

Không nhất thiết phải revoke mọi session của người dùng khi một credential không còn dùng được, ví dụ khóa bảo mật hết pin nhưng không có dấu hiệu compromise. Tuy nhiên, nếu credential bị nghi đánh cắp, nên ưu tiên ngăn attacker tiếp tục dùng phiên/token đã có.

## 13. Cache và phân phối trạng thái suspension

Một credential có thể được kiểm tra bởi nhiều verifier, API gateway, IdP node hoặc resource server. Nếu một node vẫn dùng cache trạng thái active sau khi credential bị suspend, attacker có thể tiếp tục đăng nhập qua node đó.

Các lựa chọn:

- Tra trạng thái trực tiếp từ credential registry cho giao dịch rủi ro cao.
- Cache có TTL ngắn và invalidation event.
- Version credential hoặc account security epoch để phát hiện trạng thái cũ.
- Push revocation/suspension event tới verifier và gateway.
- Fail closed cho các thao tác nhạy cảm khi không thể xác minh trạng thái.
- Đặt giới hạn thời gian tối đa mà một verifier có thể dùng trạng thái cũ.

Không có một chiến lược cache phù hợp mọi hệ thống. Cần đo độ trễ lan truyền và xác định rõ khoảng thời gian credential có thể còn được chấp nhận sau suspension. Đây là một phần của security SLA.

## 14. Yêu cầu tính nguyên tử và xử lý đồng thời

Suspension có thể cạnh tranh với một lần đăng nhập hoặc token exchange đang diễn ra. Nếu verifier kiểm tra active, rồi credential bị suspend trước khi session được tạo, hệ thống cần định nghĩa request nào được phép hoàn tất.

Một số biện pháp:

- Kiểm tra credential status gần thời điểm commit session/token.
- Dùng version hoặc security epoch; session lưu version đã xác minh.
- Transaction state và credential state được cập nhật nhất quán.
- Hủy pending challenge khi trạng thái chuyển sang suspended/revoked.
- Idempotency key cho lệnh suspend/resume để retry không tạo tác động khác nhau.
- Định nghĩa thứ tự giữa suspend, authentication success và token issuance.

Với credential bị xác nhận compromise, có thể áp dụng quy tắc: mọi authentication transaction chưa commit tại thời điểm suspension phải bị từ chối. Request đã hoàn tất trước đó được xử lý theo session/token revocation policy.

## 15. Resume credential có điều kiện

Resume là chuyển credential từ suspended sang active. Vì thao tác này mở lại đường xác thực, cần kiểm tra:

1. Credential vẫn thuộc đúng principal/tenant và không bị revoked, expired hoặc replaced.
2. Lý do suspension đã được giải quyết.
3. Không có incident evidence cho thấy secret/private key bị lộ.
4. Người yêu cầu có quyền resume; với trường hợp rủi ro cao cần xác minh độc lập hoặc dual control.
5. Credential material và metadata vẫn hợp lệ theo policy.
6. Cache/verifier nhận trạng thái mới trước khi credential được dùng.
7. Session/token cũ được đánh giá riêng; resume không tự phục hồi session đã revoke.
8. Ghi audit và thông báo cho chủ tài khoản.

Nếu có bất kỳ nghi ngờ nào về tính bí mật hoặc quyền kiểm soát, hãy revoke và đăng ký credential mới. Không cho người dùng tự resume một credential đã bị security administrator suspend vì compromise mà không có quy trình review.

## 16. Tác động tới MFA và assurance

Khi một yếu tố bị suspend, mức assurance có thể giảm:

- Nếu policy yêu cầu passkey, tài khoản không thể dùng TOTP yếu hơn để thay thế nếu chưa có mapping cho phép.
- Nếu một trong hai yếu tố bắt buộc của MFA bị suspend, luồng đăng nhập không đạt MFA.
- Nếu tài khoản có nhiều authenticator độc lập, một credential bị suspend không nhất thiết làm toàn bộ MFA mất hiệu lực.
- Nếu credential được dùng để step-up cho hành động đang chờ, ứng dụng phải kiểm tra lại context và có thể yêu cầu phương thức khác.

Không tự động downgrade sang SMS/email hoặc mật khẩu đơn lẻ chỉ vì một authenticator bị suspend. Policy cần xác định phương thức thay thế đạt assurance floor. Nếu không có phương thức phù hợp, yêu cầu recovery hoặc trì hoãn hành động nhạy cảm.

## 17. Tấn công và lỗi vận hành liên quan suspension

| Rủi ro | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Credential state spoofing** | Client gửi cờ active hoặc bỏ qua registry. | Verifier tra trạng thái authoritative; không tin metadata client. |
| **Delayed propagation** | Một node cache trạng thái active sau khi credential đã suspend. | Invalidation, TTL, versioning và đo propagation delay. |
| **Unauthorized suspension** | Attacker suspend credential của nạn nhân để gây gián đoạn. | Xác minh actor, rate limit, audit, notification và approval theo rủi ro. |
| **Unauthorized resume** | Attacker resume credential đã bị nghi compromise. | Step-up/dual control, reason resolution và không resume credential đã revoked. |
| **Account lockout DoS** | Suspend nhiều credential của người dùng qua abuse endpoint. | Throttle, authorization và abuse detection. |
| **Session persistence** | Credential bị suspend nhưng session/token cũ vẫn hoạt động. | Credential-to-session mapping và revoke policy. |
| **Token persistence** | Refresh token tiếp tục cấp access token. | Revoke token family/grant hoặc kiểm tra security epoch. |
| **Race condition** | Login commit đồng thời với suspension. | Atomic state transition và recheck trước commit. |
| **False positive** | Risk engine suspend nhầm credential hợp lệ. | Review, recovery/resume có kiểm soát và đo false positive. |
| **Secret compromise treated as temporary** | Key bị lộ nhưng chỉ suspend rồi resume. | Revoke và rotate khi có bằng chứng compromise. |
| **PKI status gap** | Relying party không kiểm tra CRL/OCSP hoặc dùng dữ liệu stale. | Revocation checking, freshness policy và cache được quản trị. |
| **Audit tampering** | Actor xóa hoặc sửa lịch sử suspend/resume. | Audit append-only, phân quyền và integrity monitoring. |

## 18. Mã giả: suspend credential an toàn

Mã giả dưới đây minh họa logic khái niệm; không thay thế triển khai database, PKI hoặc credential verifier đã được kiểm thử:

~~~text
suspendCredential(actor, credentialId, reason, requestContext):
    credential = loadCredential(credentialId)
    require credential exists
    require actorCanSuspend(actor, credential, reason)
    require reason is allowlistedAndRecorded

    result = atomically:
        current = reloadCredentialForUpdate(credentialId)
        require current.status == "active"
        current.status = "suspended"
        current.statusVersion += 1
        current.suspendedAt = now
        current.suspendedBy = actor.id
        current.suspensionReason = reason
        save(current)
        cancelPendingChallengesForCredential(credentialId)
        appendAuditEvent(current, actor, requestContext)

    publishCredentialStatusChanged(credentialId, result.statusVersion)
    applyRelatedSessionAndTokenPolicy(credentialId, reason)
    notifyCredentialOwnerSafely(credentialId, reason)
    return suspended()

resumeCredential(actor, credentialId, evidence, approval):
    credential = loadCredential(credentialId)
    require credential.status == "suspended"
    require credential.notExpired
    require credential.notRevoked
    require credential.notReplaced
    require suspensionReasonResolved(credential)
    require evidenceMeetsResumePolicy(evidence, credential)
    require approvalPolicySatisfied(actor, approval, credential)

    atomically:
        reloadCredentialForUpdate(credentialId)
        require statusVersionUnchanged(credential)
        setStatus("active")
        incrementStatusVersion()
        appendAuditEvent()

    publishCredentialStatusChanged(credentialId, newStatusVersion)
    notifyCredentialOwnerSafely(credentialId, "credential_resumed")
    return resumed()
~~~

Trong triển khai thật:

- Kiểm tra quyền actor và tenant ở phía server.
- Lệnh suspend phải idempotent; request lặp không tạo nhiều trạng thái mâu thuẫn.
- Không cho resume nếu credential đã revoked, expired hoặc replaced.
- Publish event có retry/outbox để verifier nhận thay đổi; không báo hoàn tất lan truyền nếu chưa có xác nhận theo SLA.
- Session/token policy phải được thực thi riêng và có audit.
- Không ghi secret, private key, OTP hoặc token vào audit event.

## 19. Tình huống thực tế: nhân viên báo mất khóa bảo mật

Một nhân viên có hai passkey: một passkey trên điện thoại và một khóa bảo mật USB. Người dùng báo mất điện thoại trong lúc đi công tác. Tài khoản còn khóa USB dự phòng.

### Quyết định

| Thành phần | Trạng thái | Hành động |
| --- | --- | --- |
| Passkey trên điện thoại | Bị báo mất | Suspend ngay theo quy trình self-service đã xác minh; đánh giá compromise. |
| Khóa bảo mật USB | Active, còn kiểm soát | Có thể dùng để xác minh và tiếp tục đăng nhập theo policy. |
| TOTP trên điện thoại | Có thể cùng bị mất | Suspend binding gắn với thiết bị. |
| Session hiện tại | Đang active trên laptop | Đánh giá có cần revoke hay chỉ yêu cầu step-up. |
| Refresh token | Được tạo trước khi mất máy | Thu hồi nếu có dấu hiệu thiết bị/token bị chiếm. |
| Credential inventory | Cần cập nhật | Hiển thị trạng thái suspended và hướng dẫn thay thế. |

### Luồng xử lý

1. Người dùng báo mất thiết bị qua cổng bảo mật; server xác minh session/recovery evidence phù hợp.
2. Hệ thống suspend passkey và TOTP binding trên điện thoại, tăng status version và hủy challenge đang chờ.
3. Verifier nhận sự kiện; mọi đăng nhập mới bằng credential đó bị từ chối.
4. Người dùng xác thực bằng khóa USB dự phòng để kiểm tra tài khoản.
5. Hệ thống đánh giá session/token đã phát hành trong khoảng thời gian rủi ro.
6. Nếu thiết bị được xác nhận đã mất và có khả năng lộ key, revoke credential cũ; người dùng đăng ký passkey mới.
7. Gửi thông báo và ghi audit về suspend, revoke/replacement.

Nếu người dùng tìm lại điện thoại, không tự động resume. Cần xác minh thiết bị và rủi ro; nếu có dấu hiệu bị truy cập trái phép, giữ credential cũ ở trạng thái revoked và đăng ký mới.

## 20. Kiểm thử credential suspension

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Credential active được suspend | Registry chuyển suspended và verifier từ chối lần xác thực mới. |
| Credential đã suspended nhận request login | Từ chối dù mật khẩu/chữ ký/OTP có vẻ hợp lệ. |
| Client gửi trạng thái active giả | Verifier bỏ qua; dùng trạng thái authoritative. |
| Actor không có quyền suspend | Từ chối và ghi sự kiện bảo mật phù hợp. |
| Suspend request được gửi lặp | Idempotent; không tạo trạng thái hoặc audit mâu thuẫn. |
| Credential đã revoked yêu cầu resume | Từ chối; cần credential mới. |
| Credential expired/replaced yêu cầu resume | Từ chối. |
| Resume không có evidence/approval theo policy | Từ chối. |
| Credential bị suspend khi challenge đang pending | Challenge bị hủy hoặc không thể commit theo policy. |
| Login commit đồng thời với suspend | Kết quả tuân theo thứ tự/transaction policy; không tạo session trái phép sau suspension. |
| Verifier node dùng cache cũ | Invalidation/version/TTL giới hạn khoảng chấp nhận stale. |
| Refresh token tồn tại sau suspension | Xử lý theo credential-to-token policy; không giả định tự hết hiệu lực. |
| Certificate bị suspend/revoke | Relying party kiểm tra trạng thái theo PKI/internal registry policy. |
| API key bị lộ | Suspend/revoke key ID và kiểm tra integration/session liên quan. |
| Risk engine suspend nhầm | Có quy trình review/resume an toàn và audit. |
| Account bị suspended | Tất cả credential bị xử lý theo account-level policy, không chỉ một factor. |
| Credential bị suspend nhưng UI vẫn hiển thị active | Phát hiện consistency bug; UI lấy trạng thái từ nguồn authoritative. |

### Kiểm thử vận hành

- Đo thời gian từ commit suspension đến khi mọi verifier từ chối credential.
- Kiểm tra cache invalidation khi một node mất kết nối.
- Kiểm tra event delivery retry và outbox consistency.
- Kiểm tra audit có actor, reason, timestamp, old/new status và status version.
- Kiểm tra thông báo không chứa credential material.
- Kiểm tra người dùng vẫn có thể dùng authenticator khác nếu policy cho phép.
- Kiểm tra recovery/resume không làm credential bị compromise hoạt động trở lại.

## 21. Checklist thiết kế credential suspension

- [ ] Phân biệt suspended, revoked, expired, replaced và deleted.
- [ ] Xác định phạm vi credential-level, device-level, account-level, client-level hoặc tenant-level.
- [ ] Verifier chỉ chấp nhận credential ở trạng thái active.
- [ ] Trạng thái được lưu ở nguồn authoritative; client không thể tự khai active.
- [ ] Suspend có actor, reason, timestamp, status version và audit.
- [ ] Resume yêu cầu lý do suspension được giải quyết và bằng chứng/approval phù hợp.
- [ ] Không resume credential đã revoked, expired, replaced hoặc có secret/private key bị compromise.
- [ ] Hủy pending challenge và xử lý login/token exchange đồng thời.
- [ ] Có cache invalidation, propagation SLA và hành vi khi registry không sẵn sàng.
- [ ] Đánh giá session, access token, refresh token và workload credential liên quan.
- [ ] Không tự downgrade MFA khi một factor bị suspend.
- [ ] Certificate có revocation checking/freshness policy phù hợp.
- [ ] API key được tách theo workload và scope để giới hạn blast radius.
- [ ] Có thông báo cho chủ tài khoản qua kênh phù hợp và không lộ secret.
- [ ] Có quy trình recovery, replacement và điều tra compromise.
- [ ] Kiểm thử race condition, replay, unauthorized suspend/resume và stale cache.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Suspend khác revoke credential như thế nào?

**Gợi ý:** Suspend tạm ngừng sử dụng và có thể resume khi lý do được giải quyết; revoke thể hiện credential không còn được tin cậy và cần thay thế.

**Câu 2.** Vì sao không thể chỉ ẩn passkey khỏi giao diện để suspend?

**Gợi ý:** Verifier vẫn có thể chấp nhận assertion. Trạng thái phải được kiểm tra ở server và lan truyền tới mọi verifier.

**Câu 3.** Nếu một API key bị lộ, có nên suspend rồi resume chính key đó không?

**Gợi ý:** Không nên. Bí mật đã lộ cần revoke/rotate; resume sẽ làm key bị lộ hợp lệ trở lại.

**Câu 4.** Suspend một passkey có tự động thu hồi mọi session/token đã tạo từ nó không?

**Gợi ý:** Không. Credential, session và token có vòng đời riêng; cần mapping và revocation policy.

**Câu 5.** Vì sao resume cần kiểm soát chặt hơn một thao tác hiển thị thông tin?

**Gợi ý:** Resume mở lại một phương thức xác thực, có thể trao quyền truy cập cho người đang nắm credential.

**Câu 6.** Vì sao cache trạng thái credential có thể tạo lỗ hổng sau suspension?

**Gợi ý:** Verifier dùng cache active cũ vẫn chấp nhận credential; cần invalidation, versioning, TTL và propagation SLA.

**Câu 7.** Khi suspend một yếu tố MFA, ứng dụng có thể tự chuyển sang SMS không?

**Gợi ý:** Chỉ khi policy assurance cho phép. Không được âm thầm hạ mức chống phishing của hành động.

## 23. Ghi nhớ

**Credential suspension là biện pháp tạm ngừng một credential khi cần hạn chế rủi ro hoặc chờ xác minh, trong khi vẫn giữ trạng thái và lịch sử quản trị để xử lý tiếp.** Verifier phải từ chối credential suspended ở phía server; resume cần lý do được giải quyết và bằng chứng phù hợp; credential đã compromise nên revoke và thay thế. Suspension không tự động khóa tài khoản hoặc thu hồi mọi session/token, vì vậy hệ thống cần xác định phạm vi tác động, liên kết credential với authentication event, truyền trạng thái tới mọi verifier và áp dụng session/token policy riêng. Thiết kế tốt phân biệt rõ suspend/revoke/expire, kiểm soát actor, chống race/replay và giữ nguyên assurance floor khi một yếu tố không còn khả dụng.
