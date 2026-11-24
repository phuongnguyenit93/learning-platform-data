# Post recovery session issuance

## Mục tiêu và phạm vi

**Post recovery session issuance** là quá trình quyết định có cấp session sau khi khôi phục tài khoản hay không, cấp loại session nào và dựa trên sự kiện xác thực nào. Đây là ranh giới chuyển từ quyền sửa phương thức xác thực sang quyền sử dụng tài khoản.

Trong chương **Session Continuity** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bài học tập trung vào ranh giới này khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Một luồng recovery an toàn cần liên kết đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session; đổi được credential chưa đủ để kết luận mọi session cũ đã vô hiệu hoặc người dùng nên nhận quyền đầy đủ ngay.

Sau bài này, người học cần có khả năng:

- Tách hoàn tất recovery, hoàn tất xác thực và phát hành session thành những quyết định rõ ràng.
- Chọn giữa chưa cấp session, recovery session, session sau recovery có giới hạn và session thông thường.
- Cấp session mới sau khi thay đổi bảo mật đã commit, với đúng tài khoản, quyền hạn và mức tin cậy.
- Xử lý thu hồi session cũ, refresh token, retry và sự cố phân tán mà không mở lại quyền truy cập đã bị thu hồi.

Các tên trạng thái, thời hạn và chính sách trong bài là thiết kế minh họa của một dịch vụ giả định. Chúng không phải giá trị mặc định của mọi framework hoặc yêu cầu đủ để tự tuyên bố đáp ứng một chuẩn bảo đảm xác thực.

## 1. Hoàn tất recovery không đồng nghĩa với đã đăng nhập

### 1.1. Ba sự kiện khác nhau

Một người dùng bấm “Lưu mật khẩu mới” có thể tạo ra ba sự kiện độc lập:

1. Server chấp nhận bằng chứng cho phép đặt lại mật khẩu.
2. Server cập nhật credential và trạng thái bảo mật của tài khoản.
3. Server xác thực người dùng theo chính sách đăng nhập rồi cấp session.

Nếu bước 2 thành công, chỉ có thể khẳng định thay đổi credential đã được ghi nhận. Không tự suy ra bước 3 đã xảy ra.

OWASP khuyến nghị sau khi đặt lại mật khẩu, người dùng đăng nhập bằng cơ chế thông thường thay vì được tự động đăng nhập, nhằm tránh làm phức tạp và mở thêm lỗi trong xử lý xác thực/session. Đây là một mặc định phù hợp cho luồng password reset. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password)

Đối với các loại recovery khác, sản phẩm vẫn phải có chính sách phát hành session rõ ràng. Nếu muốn tiếp tục vào tài khoản ngay, cần xác định ceremony nào thực sự đáp ứng điều kiện xác thực, không chỉ thêm lệnh tạo cookie vào endpoint hoàn tất recovery.

### 1.2. Tách các loại vật mang quyền

| Thành phần | Chứng minh hoặc cho phép điều gì? | Không được tự hiểu thành |
| --- | --- | --- |
| Recovery token | Quyền thực hiện một bước recovery cụ thể trong thời hạn | Quyền đăng nhập đầy đủ |
| Recovery session | Quyền đi qua các bước recovery được cho phép | Session nghiệp vụ thông thường |
| Authentication event | Kết quả xác minh một hoặc nhiều authenticator theo ceremony | Quyền thực hiện mọi hành động của tài khoản |
| Login grant nội bộ | Quyền đổi kết quả xác thực đã được chấp nhận thành một session, nếu thiết kế dùng bước này | Token recovery có thể tái sử dụng |
| Application session | Quyền duy trì tương tác theo chính sách của ứng dụng | Bằng chứng xác thực mới ở mỗi request |
| Access token | Quyền gọi tài nguyên theo audience, scope và điều kiện của token | Quyền tự tạo session ở một ứng dụng bất kỳ |
| Refresh token | Quyền xin access token mới theo một grant cụ thể | Bằng chứng người dùng vừa thực hiện MFA |
| ID Token trong OpenID Connect | Thông tin về xác thực người dùng do issuer cung cấp cho client | Access token dùng thay thế để gọi API |

Một hệ thống không nhất thiết triển khai tất cả các thành phần trong bảng. Tuy nhiên, thành phần nào được dùng phải có đúng mục đích và đường kiểm tra riêng.

### 1.3. Session không được có mức tin cậy cao hơn sự kiện tạo ra nó

NIST mô tả session secret được tạo để ràng buộc phần mềm của người dùng với bên cung cấp session. Session có thể kế thừa mức AAL thấp hơn, nhưng không được được xem là cao hơn sự kiện xác thực đã tạo ra nó. [NIST SP 800-63B-4 — Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b/session/#session-bindings)

Vì vậy, không gắn `mfaCompleted=true` chỉ vì helpdesk đã duyệt recovery. Cũng không coi việc người dùng vừa tạo passkey mới là bằng chứng độc lập rằng họ là chủ tài khoản cũ. Kẻ được cấp nhầm quyền recovery cũng có thể tạo và sử dụng thành công một credential mới.

## 2. Chọn kết quả phát hành session

Một quyết định sau recovery nên mô tả loại quyền thực tế, không chỉ trả `success=true`.

| Kết quả minh họa | Khi nào phù hợp? | Quyền có thể có |
| --- | --- | --- |
| `NO_SESSION_REQUIRE_LOGIN` | Credential đã đổi thành công, nhưng chưa có xác thực đáp ứng chính sách đăng nhập | Xem thông báo hoàn tất và đi vào luồng đăng nhập |
| `RECOVERY_ONLY` | Còn bước recovery được cấp quyền nhưng chưa hoàn tất | Chỉ các endpoint recovery cần thiết |
| `POST_RECOVERY_RESTRICTED` | Có xác thực được chấp nhận nhưng còn giới hạn sau recovery | Một tập hành động ứng dụng được chính sách cho phép |
| `STANDARD_SESSION` | Đã đạt yêu cầu xác thực và không còn giới hạn cản trở loại session này | Quyền tài khoản theo chính sách hiện tại |
| `SECURITY_REVIEW_REQUIRED` | Có hold, dấu hiệu chiếm đoạt hoặc điều kiện chưa giải quyết | Chưa cấp session nghiệp vụ; chuyển đường xử lý phù hợp |

Một `POST_RECOVERY_RESTRICTED` session không nhất thiết yếu về mặt mật mã. Người dùng có thể vừa xác thực bằng passkey chống phishing, nhưng tài khoản vẫn bị hạn chế đổi kênh recovery hoặc xuất dữ liệu trong một khoảng thời gian do chính sách sự cố.

Ngược lại, một recovery session có quyền hẹp chưa phải phiên đăng nhập nghiệp vụ. Không đưa nó tới một API chỉ hiểu “đã có session” rồi cho phép toàn bộ chức năng.

### 2.1. Ma trận theo tình huống

| Tình huống sau bước recovery | Quyết định phù hợp trong ví dụ |
| --- | --- |
| Reset mật khẩu qua liên kết, chưa thực hiện MFA còn bắt buộc | Yêu cầu đăng nhập thông thường; giữ yêu cầu MFA |
| Đã đặt lại MFA nhưng factor mới còn chờ xác nhận | Chỉ tiếp tục recovery theo quyền được cấp |
| Đã xác thực đủ bằng credential hiện hành, còn thời gian hạn chế thao tác nhạy cảm | Cấp session sau recovery có giới hạn |
| Hoàn tất recovery tài khoản đặc quyền nhưng chưa qua đường xác thực quản trị | Chưa cấp session quản trị |
| Credential mới đã được xác nhận, nhưng account đang có security hold | Không cấp session nghiệp vụ vượt qua hold |
| Xác thực mới đáp ứng chính sách và không còn hạn chế liên quan | Có thể cấp session thông thường |

Quyết định phải dựa trên trạng thái ở server. Không nhận các cờ như `recoveryDone`, `isTrustedDevice` hoặc `mfaVerified` từ client rồi dùng chúng làm căn cứ phát hành session.

## 3. Điều kiện trước khi phát hành

### 3.1. Thay đổi bảo mật đã commit

Trước khi cấp session dựa trên kết quả recovery, phải xác nhận:

- Recovery attempt đúng tài khoản, tenant và mục đích.
- Credential thay thế đã được lưu ở trạng thái phù hợp.
- Recovery token hoặc grant hoàn tất đã được tiêu thụ theo chính sách.
- Phạm vi thu hồi credential/session cũ đã được xác định và trạng thái có thẩm quyền đã cập nhật.
- Các giới hạn sau recovery, security hold và phiên bản bảo mật đã được ghi nhận.

Không phát cookie rồi mới thử cập nhật credential. Nếu giao dịch sau đó rollback, client có thể đang giữ một session mô tả một thay đổi chưa từng thành công.

Thông báo thành công cũng cần phản ánh đúng kết quả. Ví dụ: “Mật khẩu đã được thay đổi. Hãy đăng nhập lại để tiếp tục.” Câu này không cam kết tất cả ứng dụng liên kết đã đăng xuất nếu hệ thống chưa thực thi được việc đó.

### 3.2. Có kết quả xác thực đúng và đủ mới

Chính sách phát hành cần biết người dùng đã xác thực bằng gì, khi nào, cho mục đích nào và với phiên bản bảo mật nào. Một kết quả xác thực từ trước khi credential bị thay thế có thể không còn thích hợp để tạo session mới sau recovery.

Nếu dùng ceremony đăng nhập mới, server phát challenge/context mới và xác minh bằng cơ chế thông thường. Nếu tích hợp ceremony xác thực vào cuối recovery, ceremony đó vẫn phải đáp ứng cùng các điều kiện tương ứng, có ranh giới và mục đích rõ ràng.

Không dùng việc “vừa xác nhận sử dụng được factor mới” để xóa lỗi thiếu bằng chứng ở đầu recovery. Xác thực bằng credential mới chỉ đáng tin khi việc cấp quyền gắn credential trước đó đã có căn cứ phù hợp.

### 3.3. Quyền hiện tại và giới hạn hiện tại

Role, trạng thái account và quyền truy cập phải lấy từ nguồn có thẩm quyền ở thời điểm phát hành. Không sao chép role từ session cũ, recovery token hoặc một bản cache không còn phù hợp.

Điều kiện xác thực và điều kiện phân quyền cần được kiểm tra riêng. Một người có thể xác thực thành công nhưng tài khoản đã bị vô hiệu hóa, bị gỡ vai trò hoặc không còn quyền vào tenant đích.

Nếu còn thời gian hạn chế sau recovery, ghi nhận giới hạn ở cấp account hoặc cơ chế chính sách chung. Một session mới từ trình duyệt khác cũng phải chịu giới hạn đó.

### 3.4. Context nhận session thuộc đúng luồng

Session phải được cấp cho đúng client hoặc browser context đã hoàn tất xác thực. Việc biết mã recovery attempt, email hoặc ID giao dịch không đủ để nhận session.

Với cookie, bảo vệ thao tác phát hành khỏi CSRF và login CSRF theo kiến trúc ứng dụng. Với callback, khóa account, issuer, client và redirect theo giao thức được sử dụng. Không chấp nhận URL quay về tùy ý hoặc một `userId` trong body để quyết định subject.

Nếu trình duyệt đang đăng nhập tài khoản B nhưng hoàn tất recovery cho A, không âm thầm gắn credential hoặc quyền của A vào session B. Cần một luồng chuyển tài khoản rõ ràng và session mới cho đúng subject.

## 4. Thứ tự xử lý và ranh giới giao dịch

### 4.1. Luồng cơ sở đề xuất

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as Recovery service
    participant A as Account state
    participant V as Verifier
    participant S as Session service
    U->>R: Hoàn tất thay đổi bằng grant hợp lệ
    R->>A: Commit credential, trạng thái thu hồi, giới hạn và phiên bản
    A-->>R: Recovery đã commit
    R-->>U: Thông báo kết quả và yêu cầu đăng nhập
    U->>V: Thực hiện xác thực mới
    V->>A: Kiểm tra credential và trạng thái hiện tại
    V-->>S: Kết quả xác thực gắn đúng account và phiên bản
    S->>A: Kiểm tra điều kiện phát hành hiện tại
    S->>S: Tạo session ID mới và lưu session
    S-->>U: Phát cookie hoặc token theo chính sách
~~~

Trong luồng cơ sở này, hoàn tất recovery không phát session nghiệp vụ. Session chỉ được phát khi có sự kiện xác thực được chấp nhận sau đó.

Nếu recovery cần một số bước tiếp theo, có thể cấp context hoặc recovery session hẹp phục vụ các bước đó. Không gọi nó là session thông thường chỉ để tái sử dụng middleware hiện có.

### 4.2. Giao dịch hoàn tất recovery

Một mô hình cục bộ có thể commit cùng nhau:

1. Thay đổi trạng thái credential.
2. Đánh dấu recovery attempt đã hoàn tất.
3. Tiêu thụ grant hoàn tất.
4. Cập nhật trạng thái thu hồi và tăng `securityEpoch` theo chính sách.
5. Ghi giới hạn account và sự kiện outbox.

`securityEpoch` là số phiên bản bảo mật nội bộ trong ví dụ. Khi được tăng, các session hoặc grant mang phiên bản cũ không còn phù hợp nếu hệ thống kiểm tra phiên bản đó.

Không cần tăng epoch mỗi lần đăng nhập. Epoch được thay khi có sự kiện bảo mật cần vô hiệu hóa trạng thái cũ; session mới chỉ mang phiên bản hiện hành mà nó được phép sử dụng.

### 4.3. Giao dịch cấp session

Một giao dịch khác có thể tiêu thụ login grant nội bộ đã được tạo từ xác thực thành công, kiểm tra trạng thái account và lưu session mới. Grant này khác recovery token đã tiêu thụ.

Nếu session store, account store và hệ thống token ở các dịch vụ khác nhau, không được giả định một giao dịch SQL cục bộ bao phủ tất cả. Cần giao thức điều phối và kiểm tra trạng thái có thẩm quyền phù hợp.

Outbox hữu ích để gửi thông báo và lan truyền sự kiện có thể retry. Tuy nhiên, chỉ ghi một sự kiện “hãy thu hồi session” vào hàng đợi chưa chứng minh token cũ đã bị mọi API từ chối.

## 5. Nội dung session mới

### 5.1. Không sao chép nguyên session trước recovery

Khi cấp session mới, cần tạo định danh/secret mới, không nâng quyền trực tiếp trên cookie recovery hoặc giữ lại ID do client mang từ trước.

OWASP yêu cầu đổi session ID khi mức đặc quyền thay đổi để giảm nguy cơ session fixation; session ID cũ phải không còn được chấp nhận cho các tài nguyên được bảo vệ tương ứng. [OWASP — Renew the Session ID After Any Privilege Level Change](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#renew-the-session-id-after-any-privilege-level-change)

Nếu dùng framework, sử dụng cơ chế quản lý session và xác thực mà framework hỗ trợ, đồng thời hiểu rõ dữ liệu nào được di chuyển sang session mới. Đổi ID nhưng giữ nguyên các thuộc tính `mfaCompleted`, `rememberedDevice` hoặc `adminMode` cũ vẫn có thể duy trì quyền sai.

### 5.2. Các nhóm dữ liệu cần lưu

| Nhóm | Dữ liệu minh họa | Nguồn tin cậy |
| --- | --- | --- |
| Danh tính | Subject/account ID, tenant ID | Kết quả xác thực và account store |
| Phiên | Session ID hoặc digest, loại session, trạng thái | Session service |
| Xác thực | Authentication event ID, thời điểm, phương thức, mức đáp ứng chính sách | Verifier hoặc IdP đã được xác minh |
| Bảo mật | Security epoch, policy version, tham chiếu recovery đã commit | Account và policy store |
| Phân quyền | Scope/action được phép, giới hạn sau recovery | Chính sách hiện tại |
| Thời gian | CreatedAt, absoluteExpiresAt, idle timeout | Đồng hồ và chính sách server |
| Vòng đời | RevokedAt, refresh family nếu có, lý do kết thúc | Session/token service |

Không đưa bí mật recovery, mật khẩu, seed TOTP hoặc private key vào session. Tham chiếu recovery phục vụ kiểm soát và audit, không phải bằng chứng cho phép client tự nâng quyền.

### 5.3. Mô hình dữ liệu nội bộ minh họa

~~~json
{
  "subject": "server-resolved-account",
  "tenant": "server-resolved-tenant",
  "sessionClass": "POST_RECOVERY_RESTRICTED",
  "authenticationEventId": "verified-event-reference",
  "securityEpoch": 18,
  "recoveryCompletionId": "committed-recovery-reference",
  "authorizationProfile": "POST_RECOVERY_BASELINE",
  "refreshAllowed": false
}
~~~

Đây là bản mô tả dữ liệu nội bộ, không phải tập claim chuẩn bắt buộc của OAuth hoặc OpenID Connect. Một triển khai thực cần thêm thời điểm, giới hạn vòng đời và cơ chế bảo vệ tính toàn vẹn.

Không chỉ lưu một danh sách role rồi bỏ qua `sessionClass`. Mọi tài nguyên nhận session phải biết cách áp dụng giới hạn, hoặc session đó không được cấp quyền truy cập tài nguyên ấy.

## 6. Cấp session nguyên tử và chống sử dụng lại

### 6.1. Mã giả cho backend Java

Mẫu dưới minh họa một hệ thống có account store và session registry nằm trong cùng ranh giới giao dịch. Nó không phải mã triển khai hoàn chỉnh cho Spring Security, OAuth hoặc WebAuthn.

Login grant trong ví dụ đã được tạo từ một sự kiện xác thực hợp lệ sau recovery. Grant có account, tenant, client context, mục đích, thời hạn và phiên bản bảo mật; nó không phải recovery token.

~~~java
SessionEnvelope issuePostRecoverySession(VerifiedLoginContext context) {
    return transaction.execute(() -> {
        Account account = accounts.lock(context.accountId());
        LoginGrant grant = loginGrants.lock(context.loginGrantId());
        RecoveryCompletion completion =
            recoveries.requireCommitted(context.recoveryCompletionId());
        Instant now = clock.instant();

        requireBoundToSameAccountAndTenant(context, account, grant, completion);
        requireGrantPurpose(grant, "ISSUE_APPLICATION_SESSION");
        requireGrantClientContext(grant, context);
        requireValidUnusedGrant(grant, now);
        requireAuthenticationAfterRecovery(grant.authentication(), completion);
        requireCurrentSecurityEpoch(account, grant.securityEpoch());
        requireAuthenticationStillAccepted(grant.authentication(), account, now);

        IssuanceDecision decision =
            policy.evaluateCurrentSessionIssuance(account, completion, grant, now);
        requireIssuanceAllowed(decision);
        requireAllTargetServicesCanEnforce(decision);

        NewSessionSecret secret = sessionSecrets.generate();
        Session session = sessions.create(
            account.id(),
            account.tenantId(),
            secret.digest(),
            account.securityEpoch(),
            grant.authentication(),
            decision.sessionClass(),
            decision.permissions(),
            decision.deadlines(now)
        );

        grant.consumeFor(session.id(), now);
        recoverySessions.closeBoundContext(context, now);
        outbox.appendSessionCreated(account, session, completion);

        return SessionEnvelope.forDeliveryAfterCommit(
            session.id(), secret.value(), decision
        );
    });
}
~~~

Context đầu vào phải do backend xác minh. Không ánh xạ trực tiếp `accountId`, `securityEpoch`, `authentication` hoặc `sessionClass` do client khai báo vào các bản ghi được tin cậy.

Hàm `requireAuthenticationAfterRecovery` cần kiểm tra mối liên hệ với recovery đã commit và trạng thái credential/epoch, không chỉ so sánh hai timestamp. Đồng hồ lệch hoặc một timestamp giả không thể thay cho bằng chứng ceremony đúng và credential còn hợp lệ.

`sessionSecrets.generate()` nên dùng cơ chế framework hoặc bộ sinh số ngẫu nhiên mật mã phù hợp. Với opaque bearer secret tự quản lý, ví dụ có thể dùng 32 byte ngẫu nhiên và lưu digest/HMAC, không lưu raw secret vào log.

Nếu một thành phần trạng thái bắt buộc không khả dụng hoặc account đang bị hold, không cấp session rộng hơn để “cho người dùng vào trước”. Có thể trả trạng thái cần thử lại hoặc chuyển quy trình phù hợp.

### 6.2. Tiêu thụ grant và tạo session là một thay đổi

Nếu tiêu thụ grant trước rồi tạo session ở thao tác không thể rollback, lỗi giữa hai bước có thể làm người dùng mất grant nhưng chưa có session. Nếu tạo session trước mà grant chưa bị tiêu thụ, hai request đồng thời có thể tạo nhiều session.

Trong mô hình cục bộ, cần giao dịch hoặc cơ chế compare-and-set tương đương để cùng ghi nhận:

- Grant chuyển từ chưa dùng sang đã dùng.
- Grant gắn với đúng một kết quả phát hành.
- Session mới tồn tại với đúng account, quyền và thời hạn.
- Recovery context không còn quyền vượt quá phần còn được phép.

Trạng thái session đã tạo và trạng thái đã chuyển tới client là hai điều khác nhau. Không ghi audit “người dùng đã đăng nhập thành công trên trình duyệt” chỉ vì server đã tạo một hàng session trong cơ sở dữ liệu.

### 6.3. Mất phản hồi sau commit

Giả sử server đã commit session mới nhưng kết nối bị ngắt trước khi trình duyệt nhận `Set-Cookie`. Recovery vẫn đã hoàn tất; không đặt credential hoặc recovery attempt quay về trạng thái cũ.

Không giải quyết bằng cách cho client dùng lại recovery token đã tiêu thụ để xin một session khác. Cũng không trả raw secret chỉ vì client gửi đúng một idempotency key có thể đoán hoặc sao chép.

Có hai hướng thiết kế:

1. Có giao thức retry được ràng buộc với đúng client/context, trả lại cùng kết quả theo cơ chế bảo vệ đã thiết kế.
2. Không tái phát bí mật; ghi nhận kết quả chưa xác định việc chuyển tới client, thu hồi session mồ côi theo quy trình phù hợp và yêu cầu đăng nhập mới.

Nếu chỉ lưu digest của secret, server không thể đọc lại raw secret từ digest để gửi lần nữa. Thiết kế retry phải tính đến điều này từ đầu. Một lựa chọn đơn giản là chấp nhận đăng nhập lại và dọn session chưa được sử dụng, thay vì bổ sung kho lưu bí mật có thể giải mã mà chưa đánh giá rủi ro.

## 7. Thu hồi quyền cũ trước khi cho phép tiếp tục

### 7.1. Đổi credential không tự vô hiệu mọi session

Mật khẩu thường chỉ được kiểm tra khi đăng nhập, trong khi session cookie hoặc access token tiếp tục được dùng ở các request sau. Vì vậy, một session được cấp trước khi mật khẩu đổi có thể vẫn hoạt động nếu hệ thống không kiểm tra trạng thái thu hồi.

Cần xác định phạm vi theo sự cố:

| Tình huống | Phạm vi cần đánh giá |
| --- | --- |
| Quên mật khẩu, chưa có dấu hiệu bị lộ | Các session hiện có và lựa chọn/chính sách thu hồi của dịch vụ |
| Thiết bị bị mất | Session, refresh family và phương thức tin cậy gắn với thiết bị, trong giới hạn quan sát thực tế |
| Nghi chiếm đoạt tài khoản | Session trước sự kiện, refresh token, credential trái phép và quyền dài hạn liên quan |
| Recovery tài khoản đặc quyền | Session đặc quyền, token quản trị và các đường cấp quyền liên quan |

Không vô hiệu mọi session từ một yêu cầu recovery công khai chưa được xác minh. Quyền thay đổi trạng thái cần dựa trên bằng chứng hoặc quyết định bảo mật phù hợp để tránh gây từ chối dịch vụ.

### 7.2. Security epoch phải được kiểm tra ở cả sử dụng và refresh

Ví dụ:

~~~text
Trước recovery:
  Account.securityEpoch = 17
  Session cũ.epoch       = 17
  Refresh family cũ.epoch = 17

Sau khi recovery commit:
  Account.securityEpoch = 18

Sau xác thực mới:
  Session mới.epoch = 18
~~~

API hoặc session middleware chỉ chấp nhận session khi phiên bản của nó đáp ứng trạng thái account hiện hành và chưa bị thu hồi.

Một lỗi nghiêm trọng là refresh token cũ vẫn được chấp nhận, rồi server đọc epoch hiện tại và đóng dấu `18` vào access token mới. Cách đó biến một refresh token thuộc trạng thái đã bị thu hồi thành quyền hiện hành.

Đường refresh phải kiểm tra phiên bản, trạng thái và grant gốc của refresh family trước khi cấp token. Nếu family mang epoch cũ không còn hợp lệ, từ chối và yêu cầu xác thực lại; không tự nâng epoch, assurance hoặc scope cho family đó.

### 7.3. Giới hạn trong hệ thống phân tán

Tăng epoch chỉ có tác dụng ở nơi thực sự kiểm tra epoch. Một resource server chỉ xác minh chữ ký JWT và `exp` sẽ không tự biết recovery vừa xảy ra.

Các lựa chọn triển khai gồm kiểm tra trạng thái session tập trung, introspection, tra epoch có cơ chế nhất quán phù hợp, danh sách thu hồi hoặc access token ngắn hạn kết hợp thu hồi refresh token. Mỗi lựa chọn có độ trễ và tính khả dụng khác nhau.

Nếu resource server cache epoch trong 30 giây, phải tính đến cửa sổ chấp nhận trạng thái cũ tương ứng với cơ chế cache và cập nhật thực tế. Nếu chỉ dựa vào token hết hạn sau 5 phút, không tuyên bố thu hồi tức thời.

Đối với hành động có tác động lớn, có thể yêu cầu kiểm tra trạng thái có thẩm quyền tại thời điểm thực hiện. Việc phát session mới thành công không chứng minh mọi request cũ đang xử lý đã bị hủy; các thao tác đã commit trước mốc thu hồi không tự rollback.

Nếu chính sách yêu cầu một hàng rào thu hồi trước khi truy cập một tài nguyên, chỉ mở quyền đó khi điều kiện thực thi đã đạt. Gửi outbox bất đồng bộ rồi mở toàn bộ quyền ngay không thay thế hàng rào này.

### 7.4. Không chỉ xử lý cookie hiện tại

Một sự cố có thể liên quan đến refresh family trên ứng dụng di động, cookie SSO, token ứng dụng liên kết, cơ chế “nhớ thiết bị” hoặc API key. Các quyền này có vòng đời và chủ thể quản lý khác nhau.

Không tự thu hồi mọi thứ một cách mù quáng, nhưng phải có danh mục và quyết định phạm vi rõ ràng. Xóa cookie trên trình duyệt hiện tại không xóa được bản sao cookie bị đánh cắp hoặc một session trên máy khác.

## 8. Truyền session mới tới client

### 8.1. Web dùng cookie

Ví dụ header cho một ứng dụng trên một host riêng:

~~~http
Set-Cookie: __Host-account_session=<new-opaque-secret>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Cookie dùng tiền tố `__Host-` trong ví dụ không có thuộc tính `Domain`, có `Path=/` và `Secure`. Lựa chọn `SameSite` phải phù hợp với luồng thực tế; nó bổ sung cho các kiểm soát CSRF, không thay thế toàn bộ thiết kế chống CSRF.

Không đặt session secret vào query string, fragment, HTML hoặc thông báo email. Không để một redirect tùy ý nhận bearer secret hoặc mã đổi session.

Sau khi tạo session mới, cập nhật context CSRF cần thiết và thu hồi context recovery theo chính sách. Cookie recovery và cookie ứng dụng có thể có tên riêng để giảm nhầm lẫn, nhưng tách tên không thay cho kiểm tra quyền ở server.

Không mặc định kế thừa lựa chọn “ghi nhớ đăng nhập” trước recovery. Quyền truy cập dài hạn và cơ chế tin cậy thiết bị cần được đánh giá lại thay vì sao chép từ session đã mất độ tin cậy.

### 8.2. Native app và liên kết mở ứng dụng

Nếu recovery diễn ra trong trình duyệt nhưng ứng dụng native cần đăng nhập, không đặt access token hoặc refresh token trực tiếp vào liên kết mở app.

Dùng luồng xác thực/ủy quyền được hỗ trợ cho client, với mã ngắn hạn, redirect được xác định trước và các ràng buộc giao thức tương ứng. Với OAuth authorization code flow cho public client, áp dụng PKCE và các kiểm soát phù hợp; không biến recovery token thành một authorization code dùng được ở mọi client. [RFC 9700 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.1.1)

Việc liên kết mở đúng ứng dụng không tự chứng minh người cầm ứng dụng là chủ tài khoản. Server vẫn cần kết quả xác thực và context phát hành đúng.

### 8.3. Không tự động nối lại session khác

Sau khi A khôi phục tài khoản trong một tab, các tab cùng browser profile có thể dùng chung cookie mới. Không mô tả cookie như thể bị giới hạn theo từng tab.

Giao diện cần làm mới trạng thái account và quyền, tránh để một trang cũ hiển thị thông tin của B rồi gửi hành động bằng session mới của A. Những hành động nhạy cảm phải lấy account đích từ context đã xác thực và kiểm tra lại ở server.

Có thể giữ bản nháp giao diện không nhạy cảm để giảm gián đoạn, nhưng chỉ khôi phục dữ liệu vào đúng tài khoản sau khi đã xác định subject. Không di chuyển authentication context, quyền quản trị hoặc bí mật giữa hai session để giữ “liên tục”.

## 9. Thời hạn, refresh và độ mới xác thực

### 9.1. Tách các loại đồng hồ

| Mốc thời gian | Ý nghĩa |
| --- | --- |
| Recovery completed at | Thay đổi recovery được commit lúc nào |
| Authentication time | Người dùng thực hiện xác thực được chấp nhận lúc nào |
| Session created at | Bản ghi session được tạo lúc nào |
| Absolute expiry | Session hết hiệu lực muộn nhất lúc nào |
| Idle expiry | Session kết thúc sau bao lâu không có hoạt động được tính hợp lệ |
| Restriction ends at | Khi nào một điều kiện hạn chế có thể được xét gỡ |
| Access/refresh expiry | Từng token hoặc family có hiệu lực đến đâu |

Các mốc này không được thay thế cho nhau. Một request refresh vừa chạy không chứng minh người dùng vừa hoàn thành MFA. Một restriction hết thời gian cũng chưa chắc được gỡ nếu các điều kiện khác còn thiếu.

NIST phân biệt giới hạn tổng thời gian session với giới hạn không hoạt động. Hoạt động có thể cập nhật thời gian không hoạt động; việc tái xác thực mới là cơ sở đặt lại các giới hạn tương ứng theo chính sách. [NIST SP 800-63B-4 — Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b/session/#reauthentication)

### 9.2. Ví dụ chính sách ngắn hạn sau recovery

Một dịch vụ giả định có thể dùng:

- Login grant nội bộ chỉ đổi một lần trong 2 phút.
- Session `POST_RECOVERY_RESTRICTED` có absolute timeout 15 phút và idle timeout 3 phút.
- Không cấp refresh token cho session giới hạn này.
- Các thao tác xuất dữ liệu, tạo API key, đổi kênh recovery hoặc nâng quyền không nằm trong profile được phép.
- Muốn nhận session có quyền khác phải đáp ứng chính sách phát hành mới và các hạn chế account còn hiệu lực.

Các giá trị trên phục vụ minh họa. Session thông thường cần thời hạn phù hợp với mức bảo đảm, môi trường và loại ứng dụng; không lấy ví dụ này làm cấu hình bắt buộc cho mọi dịch vụ.

Không dùng hoạt động nền, heartbeat hoặc refresh để kéo dài vô hạn một session sau recovery. Nếu có reauthentication hợp lệ, cập nhật trạng thái theo kết quả thật và vẫn kiểm tra các giới hạn account.

### 9.3. Refresh token là quyết định riêng

RFC 9700 yêu cầu authorization server đánh giá rủi ro trước khi cấp refresh token. Với public client, phải dùng refresh token ràng buộc người gửi hoặc rotation để phát hiện replay. [RFC 9700 — Refresh Token Protection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2)

Nếu chính sách cho phép refresh sau recovery, phải tạo grant/family phù hợp với xác thực mới, scope mới và trạng thái account hiện hành. Không tiếp tục family cũ bị thu hồi chỉ để giảm thao tác đăng nhập.

Đường refresh cần giữ các hạn chế còn hiệu lực, không tự đổi `POST_RECOVERY_RESTRICTED` thành session đầy đủ. Rotation là kiểm soát vòng đời token; nó không nâng mức bảo đảm của bằng chứng recovery.

### 9.4. Claims phải phản ánh sự kiện thật

Trong OpenID Connect, `iat` là thời điểm phát hành JWT, còn `auth_time` là thời điểm xác thực người dùng. `amr` mô tả các phương thức xác thực, và `acr` mô tả lớp ngữ cảnh xác thực. Các giá trị phải xuất phát từ issuer và kết quả được xác minh, không phải cờ frontend. [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)

Không lấy thời điểm hoàn tất recovery làm `auth_time` mới nếu không có sự kiện xác thực tương ứng. Khi phát token mới qua refresh, cũng không đặt lại `auth_time` chỉ vì `iat` thay đổi.

Nếu hệ thống cần ghi lại nguồn gốc recovery, dùng trường nội bộ hoặc extension có hợp đồng rõ ràng, chẳng hạn tham chiếu recovery completion. Không sửa ý nghĩa claim chuẩn để giảm số trường dữ liệu.

## 10. SSO và nhiều ứng dụng liên kết

### 10.1. Session mới tại RP có thể đến từ xác thực cũ tại IdP

Một ứng dụng có thể xóa session cũ rồi chuyển người dùng sang IdP. Nếu IdP vẫn có SSO session từ trước recovery, IdP có thể trả về kết quả dựa trên session đó mà không yêu cầu người dùng thực hiện xác thực mới.

Tạo cookie mới tại RP trong trường hợp này chưa chứng minh đã có bằng chứng mới sau recovery. Nếu chính sách cần sự kiện xác thực mới, RP phải yêu cầu và kiểm tra độ mới theo giao thức cùng hợp đồng với IdP. Trong OpenID Connect, `max_age` có thể được dùng để yêu cầu giới hạn độ cũ của xác thực; client cần kiểm tra `auth_time` tương ứng và các yêu cầu context liên quan. [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)

Không chỉ kiểm tra token được phát sau recovery qua `iat`. Một token mới có thể mô tả sự kiện xác thực đã xảy ra trước đó.

Kiểm tra issuer, audience, subject, nonce/state và các ràng buộc của flow phải do thư viện/giao thức phù hợp thực hiện. Liên kết tài khoản dùng định danh ổn định theo hợp đồng với IdP; không tự gắn hai tài khoản chỉ vì có cùng email hiển thị.

### 10.2. Phạm vi recovery và phạm vi logout có thể khác nhau

Đặt lại mật khẩu cục bộ tại ứng dụng A không tự đặt lại credential ở IdP, không tự xóa SSO cookie và không tự đóng session tại ứng dụng B.

Khi có sự cố chiếm đoạt, cần xác định bên nào quản lý:

- Credential của người dùng.
- Session tại IdP.
- Session tại từng RP.
- Access token và refresh grant.
- Các quyền dài hạn hoặc kết nối được cấp trước đó.

Nếu hạ tầng hỗ trợ cơ chế truyền sự kiện hoặc logout liên kết, triển khai theo giao thức và theo dõi kết quả. Không dùng việc một trình duyệt vừa chuyển qua trang logout làm bằng chứng mọi session trên mọi thiết bị đã bị chấm dứt.

Khi thiếu khả năng thu hồi ở một thành phần, ghi rõ giới hạn thực thi và áp dụng chính sách truy cập phù hợp. Không phát session đầy đủ dựa vào giả định rằng thành phần khác chắc chắn đã đóng quyền cũ.

## 11. Audit, thông báo và vận hành

### 11.1. Ghi đúng mốc sự kiện

Một chuỗi audit hữu ích có thể gồm:

~~~text
RECOVERY_CREDENTIAL_CHANGE_COMMITTED
ACCOUNT_SECURITY_EPOCH_ADVANCED
AUTHENTICATION_SUCCEEDED
SESSION_ISSUANCE_ALLOWED hoặc SESSION_ISSUANCE_DENIED
SESSION_CREATED
LOGIN_GRANT_CONSUMED
SESSION_FIRST_VALID_USE
SESSION_REVOKED hoặc SESSION_EXPIRED
~~~

Các tên trên là ví dụ nội bộ. `SESSION_FIRST_VALID_USE` cho biết server đã nhận một request hợp lệ bằng session, không chứng minh người đang dùng chắc chắn là chủ tài khoản. Nếu secret bị đánh cắp sau khi phát hành, kẻ tấn công cũng có thể tạo request này.

Mỗi sự kiện cần account/tenant, tham chiếu recovery, authentication event, session reference, policy version, thời gian và kết quả phù hợp. Ghi lý do từ chối đủ để điều tra, nhưng giới hạn thông tin trả về cho bên chưa được xác thực.

Không ghi raw cookie, recovery token, access token, refresh token, mật khẩu hay seed MFA. Dùng tham chiếu hoặc giá trị tương quan không thể dùng trực tiếp để xác thực; bảo vệ cả dữ liệu audit khỏi sửa đổi và truy cập ngoài thẩm quyền.

### 11.2. Thông báo phải khớp với hành động đã xảy ra

Thông báo sau recovery nên nói rõ điều gì đã thay đổi và bước tiếp theo. Ví dụ:

> Phương thức xác thực của bạn đã được cập nhật. Hãy đăng nhập lại. Một số thay đổi bảo mật của tài khoản vẫn đang bị giới hạn theo thông tin hiển thị trong phần bảo mật.

Nếu đã cấp session mới, giao diện có thể hiển thị loại hạn chế và thời hạn phù hợp. Không nói “tài khoản đã hoàn toàn an toàn” chỉ vì recovery đã commit.

Gửi thông báo tới các kênh được thiết lập phù hợp từ trước, tránh chỉ dùng một địa chỉ mới do người yêu cầu cung cấp. Nếu gửi thông báo lỗi, retry qua cơ chế bền vững; không đảo ngược credential đã commit và không cấp lại grant tùy ý.

### 11.3. Chỉ số giúp phát hiện vấn đề ở khâu phát hành

| Chỉ số | Vấn đề có thể cần điều tra |
| --- | --- |
| Recovery commit thành công nhưng không có xác thực tiếp theo | Hướng dẫn khó hiểu, lỗi chuyển luồng hoặc người dùng không tiếp tục |
| Một login grant có nhiều lần đổi đồng thời | Retry lỗi, race condition hoặc replay |
| Session được tạo nhiều nhưng ít có request hợp lệ đầu tiên | Lỗi chuyển cookie/token hoặc session mồ côi |
| Refresh token epoch cũ vẫn xin được token mới | Lỗi kiểm tra phiên bản hoặc thu hồi |
| Session giới hạn gọi API ngoài scope | Middleware không thống nhất hoặc hành vi lạm dụng |
| Resource server tiếp tục chấp nhận token cũ quá cửa sổ đã thiết kế | Cache, hàng đợi hoặc cơ chế kiểm tra trạng thái gặp lỗi |
| Recovery liên tục dẫn tới session dài hạn trên client lạ | Cần xem lại chính sách phát hành và chất lượng bằng chứng |

Không dùng các chỉ số này để tự kết luận mọi trường hợp là tấn công. Chúng giúp xác định nơi cần kiểm tra trong chuỗi recovery, xác thực và session.

## 12. Các tình huống minh họa

### 12.1. Đặt lại mật khẩu nhưng chưa thực hiện MFA

Lan nhận liên kết đặt lại mật khẩu, nhập mật khẩu mới và lưu thành công. Tài khoản của Lan vẫn yêu cầu một factor MFA đã đăng ký.

Endpoint reset không phát session nghiệp vụ hoặc refresh token. Nó kết thúc quyền reset tương ứng và hướng Lan sang đăng nhập. Sau khi Lan hoàn tất mật khẩu và MFA theo chính sách, session service tạo session ID mới với trạng thái account hiện hành.

Nếu Lan cũng đã mất MFA, cần đi vào đường recovery MFA đủ điều kiện. Không dùng việc reset mật khẩu thành công để bỏ qua factor còn bắt buộc.

Điểm cần giữ: quyền thay mật khẩu và quyền đăng nhập là hai quyền khác nhau.

### 12.2. Session mới không được làm sống lại refresh family cũ

Minh khôi phục tài khoản sau nghi ngờ bị chiếm đoạt. Recovery commit nâng epoch từ 17 lên 18 và vô hiệu refresh family cũ theo chính sách.

Kẻ tấn công vẫn giữ một refresh token thuộc epoch 17. Endpoint refresh phải từ chối token đó dựa vào trạng thái family và phiên bản. Nó không được đọc account hiện tại rồi cấp access token mang epoch 18 cho token cũ.

Minh xác thực mới và có thể nhận session mang epoch 18. Resource server vẫn cần thực thi cơ chế kiểm tra trạng thái để token cũ không tiếp tục được chấp nhận ngoài cửa sổ đã thiết kế.

Điểm cần giữ: chỉ tăng số phiên bản trong cơ sở dữ liệu là chưa đủ; mọi đường cấp và dùng token phải kiểm tra phiên bản đúng.

### 12.3. Xác thực mạnh nhưng còn hạn chế sau recovery

Hà đã được cấp quyền khôi phục phù hợp, đăng ký passkey thay thế và sau đó hoàn thành đăng nhập bằng passkey. Tài khoản còn hạn chế thay đổi kênh recovery trong 24 giờ theo chính sách ứng dụng.

Hệ thống có thể cấp `POST_RECOVERY_RESTRICTED` session nếu các điều kiện khác đạt. Session đó vẫn bị chặn thao tác đổi kênh recovery. Đăng nhập lại từ trình duyệt khác hoặc đổi access token không được gỡ hạn chế ở cấp account.

Mốc 24 giờ chỉ là ví dụ. Khi đến thời điểm xét gỡ, hệ thống còn phải kiểm tra các điều kiện liên quan; một khoảng chờ tự nó không khắc phục bằng chứng thiếu hoặc security hold.

Điểm cần giữ: độ mạnh xác thực và quyền thực hiện hành động là hai chiều kiểm soát riêng.

### 12.4. Server đã commit session nhưng client mất kết nối

Quân hoàn tất xác thực mới. Server tiêu thụ login grant và lưu session, nhưng kết nối bị ngắt trước khi cookie tới trình duyệt.

Lần gọi lại không được tạo thêm session bằng recovery token cũ hoặc trả secret qua một request chỉ có mã giao dịch. Hệ thống thực hiện đường retry đã ràng buộc an toàn, hoặc hướng Quân đăng nhập lại và xử lý session mồ côi theo chính sách.

Credential mới và kết quả recovery vẫn được giữ. Lỗi chuyển phản hồi không làm recovery quay lại trạng thái chưa hoàn tất.

Điểm cần giữ: commit thay đổi, tạo session và chuyển secret tới client là những mốc khác nhau.

### 12.5. SSO trả token mới từ một session xác thực cũ

Ứng dụng của An yêu cầu đăng nhập sau recovery. IdP trả một ID Token có `iat` mới nhưng `auth_time` từ trước sự kiện cần tái xác thực.

Ứng dụng không được coi token đó là bằng chứng An vừa xác thực lại chỉ vì chữ ký hợp lệ và token chưa hết hạn. Nó kiểm tra yêu cầu độ mới và context theo chính sách, rồi yêu cầu ceremony phù hợp nếu chưa đạt.

Điểm cần giữ: phát token mới không đồng nghĩa thực hiện xác thực mới.

## 13. Các bất biến khi triển khai

- Hoàn tất recovery chỉ cấp các quyền đã được chính sách xác định; không mặc nhiên tạo session đầy đủ.
- Thay đổi credential và trạng thái bảo mật phải commit trước khi session dựa vào chúng được phát hành.
- Session mới gắn với đúng account, tenant, client context và kết quả xác thực còn hiệu lực.
- Session ID/secret mới không kế thừa quyền, assurance hoặc trạng thái tin cậy chưa được xác minh từ session cũ.
- Login grant dùng một lần khác với recovery token và bị tiêu thụ nhất quán với kết quả phát hành.
- Role, security epoch, hold và giới hạn account được kiểm tra tại thời điểm cấp và tại nơi thực thi quyền.
- Token cũ không được tự nâng epoch, scope hoặc độ mới xác thực qua refresh.
- Thu hồi chỉ có hiệu lực ở nơi kiểm tra trạng thái tương ứng; phải hiểu rõ cửa sổ chấp nhận token cũ.
- Các giới hạn sau recovery không bị gỡ bằng việc tạo session mới hoặc chuyển sang ứng dụng khác.
- Retry không tạo quyền ngoài dự kiến, không làm sống lại recovery grant đã dùng và không tiết lộ secret qua mã giao dịch.
- Audit phân biệt recovery đã commit, session đã tạo và request đầu tiên sử dụng session.

Phát hành session sau recovery là một quyết định xác thực và phân quyền mới, dựa trên trạng thái bảo mật hiện tại. Khi giữ rõ ranh giới này, dịch vụ có thể giúp người dùng tiếp tục sử dụng tài khoản mà vẫn chặn các session cũ, token bị lộ và quyền truy cập chưa đủ căn cứ.
