# Contact response integrity — Bảo đảm tính toàn vẹn phản hồi của người liên hệ

## 1. Phản hồi của người liên hệ chứng minh điều gì?

Trong luồng khôi phục tài khoản, dịch vụ có thể thu thập phản hồi từ một người liên hệ đáng tin cậy đã được thiết lập trước. Ví dụ, người đó xác nhận đã trao đổi với chủ tài khoản về việc mất thiết bị xác thực, hoặc báo rằng yêu cầu đang có dấu hiệu mạo danh.

Phản hồi này chỉ hữu ích khi dịch vụ biết được **ai đã phản hồi, phản hồi cho yêu cầu nào, nội dung có bị thay đổi không và phản hồi còn được phép sử dụng hay không**. Một ảnh chụp đoạn chat, tên người gửi email hoặc nút đồng ý đã được bấm không tự trả lời đủ các câu hỏi đó.

Contact response integrity là việc bảo vệ nguồn gốc, nội dung, ngữ cảnh và vòng đời của phản hồi. Trong thiết kế hệ thống, tính toàn vẹn cần đi cùng xác thực nguồn phản hồi, tính mới, chống phát lại và kiểm tra quyền tham gia của người liên hệ.

Ngay cả khi các thuộc tính kỹ thuật đều đạt, người liên hệ vẫn có thể bị lừa, bị chiếm tài khoản hoặc thông đồng với người yêu cầu. **Phản hồi nguyên vẹn không đồng nghĩa với lời xác nhận đúng sự thật; lời xác nhận đúng cũng chưa tự chứng minh đủ quyền khôi phục tài khoản.**

### Phạm vi của bài học

NIST SP 800-63B-4 mô tả recovery contacts là các địa chỉ của người quen đáng tin cậy được chỉ định để nhận mã khôi phục được cấp. Cơ chế đó có quy tắc riêng về mã và cách sử dụng. Bài này phân tích mô hình ứng dụng thu nhận ý kiến trực tiếp từ người liên hệ; không coi một cuộc bỏ phiếu đồng ý là tự động tương đương với cơ chế recovery contact của NIST hoặc đáp ứng một mức AAL cụ thể. [NIST SP 800-63B-4 — Recovery Contacts](https://pages.nist.gov/800-63-4/sp800-63b.html#recovery-contacts)

Nội dung tập trung vào việc bảo vệ phản hồi khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị. Không dùng số bạn bè, số lượt tương tác hay tài khoản mạng xã hội có tên giống nhau làm bằng chứng thay thế.

## 2. Những lớp tin cậy cần phân biệt

| Lớp cần xác định | Câu hỏi của hệ thống | Điều chưa thể suy ra |
| --- | --- | --- |
| Giao nhận | Thông báo có được gửi tới địa chỉ dự kiến không? | Người liên hệ đã đọc hoặc đồng ý |
| Quyền kiểm soát kênh | Ai đó có dùng được liên kết hoặc kênh đã đăng ký không? | Chắc chắn đó là người quen ban đầu |
| Xác thực người phản hồi | Phiên hoặc bằng chứng xác thực có gắn với đúng contact không? | Contact không bị lừa hoặc tài khoản không bị xâm phạm |
| Toàn vẹn ngữ cảnh | Phản hồi có gắn với đúng tài khoản, yêu cầu và hành động không? | Yêu cầu khôi phục đã đủ điều kiện |
| Điều kiện sử dụng | Contact còn đủ tư cách, phản hồi còn hạn và chưa bị thay thế không? | Phản hồi có thể dùng cho mọi thay đổi tiếp theo |
| Giá trị chứng cứ | Ý kiến đó có ý nghĩa gì theo chính sách khôi phục? | Người yêu cầu được phép bỏ qua bằng chứng khác |

Một callback có chữ ký từ nhà cung cấp email có thể chứng minh nhà cung cấp gửi sự kiện “đã phát thư”. Nó không biến sự kiện đó thành xác nhận có chủ ý của người liên hệ. Tương tự, một mã thông báo hợp lệ chứng minh quyền sở hữu mã trong phạm vi mà hệ thống thiết kế, không tự chứng minh quan hệ xã hội của người đang giữ mã.

## 3. Các nguy cơ làm sai lệch phản hồi

| Nguy cơ | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- |
| Giả nguồn | Người yêu cầu gửi email có tên hiển thị của bạn thân | Xác thực nguồn bằng giao thức phù hợp |
| Sửa nội dung | Đổi `UNKNOWN` thành `CONFIRM` khi gửi API | Xác thực yêu cầu và bảo vệ nội dung quyết định |
| Đổi mục tiêu | Dùng phản hồi cho tài khoản khác | Ràng buộc tài khoản và tenant ở phía máy chủ |
| Phát lại | Gửi lại phản hồi đã dùng từ hồ sơ cũ | Thời hạn, nonce và trạng thái sử dụng |
| Đếm trùng | Gửi lại callback hoặc đổi email alias để tăng số xác nhận | Định danh contact ổn định và ràng buộc duy nhất |
| Đánh tráo hành động | Giao diện nói xác nhận quen biết nhưng máy chủ dùng để bỏ MFA | Nội dung được xác nhận phải khớp phạm vi sử dụng |
| Tự động truy cập liên kết | Bộ quét thư mở URL đồng ý | Tách việc xem trang khỏi ghi nhận quyết định |
| Thay contact giữa chừng | Đổi địa chỉ sang địa chỉ của kẻ tấn công sau khi mở hồ sơ | Phiên bản đăng ký và kiểm tra thu hồi |
| Gây áp lực | Gửi nhiều lời mời để người liên hệ bấm cho xong | Giới hạn gửi, thông tin rõ ràng và lựa chọn từ chối |

Không có một trường `trusted=true` nào giải quyết tất cả các nguy cơ. Cần kiểm tra cả lịch sử đăng ký, thao tác hiện tại và trạng thái hồ sơ.

## 4. Thiết lập nguồn phản hồi đủ tin cậy

### 4.1. Contact phải được liên kết từ trước

Danh sách người liên hệ cần được thiết lập bằng một quy trình có xác thực và quản lý thay đổi phù hợp. Khi một yêu cầu khôi phục bắt đầu, người yêu cầu không được tùy ý thêm địa chỉ mới rồi dùng chính địa chỉ đó để xác nhận mình.

Hệ thống nên lưu định danh contact nội bộ, cách liên kết với tài khoản, địa chỉ đã được xác nhận, phiên bản đăng ký và trạng thái hiện tại. Việc contact vừa được thêm hoặc thay địa chỉ là thông tin liên quan đến rủi ro, không chỉ là một cập nhật sổ địa chỉ.

Khi mở hồ sơ, máy chủ tạo snapshot của những contact được phép tham gia và chính sách áp dụng. Snapshot giúp biết phản hồi dựa trên cấu hình nào, nhưng không có nghĩa bỏ qua thay đổi về an toàn sau đó. Nếu contact bị thu hồi hoặc được xác định đã bị xâm phạm, hệ thống phải đánh giá lại các phản hồi liên quan trước khi cấp quyền.

Đổi địa chỉ, thay định danh người liên hệ hoặc thay mục đích yêu cầu cần có quy tắc làm mất hiệu lực lời mời cũ. Không để một token gửi đến địa chỉ cũ tự có quyền xác nhận cho đăng ký mới.

### 4.2. Phân biệt hai cách thu nhận

**Contact có tài khoản riêng:** người liên hệ đăng nhập vào dịch vụ bằng tài khoản của họ. Máy chủ kiểm tra chủ thể đã xác thực có khớp contact trong lời mời hay không. Tùy rủi ro, thao tác xác nhận có thể cần tái xác thực phù hợp. Phiên đã đăng nhập của người yêu cầu khôi phục không được dùng thay cho phiên của contact.

**Contact chỉ có địa chỉ nhận lời mời:** dịch vụ gửi liên kết hoặc mã đến địa chỉ đã xác nhận từ trước. Phản hồi qua kênh này cần được ghi nhận đúng mức: có bằng chứng về quyền kiểm soát kênh hoặc token theo thiết kế, nhưng mức chắc chắn về con người có thể thấp hơn mô hình contact đăng nhập. Nếu tuyến khôi phục đòi hỏi mức mạnh hơn, không được lặng lẽ hạ yêu cầu để chấp nhận liên kết bearer.

Ở cả hai cách, không tin `contactId`, địa chỉ email hoặc tên người gửi do người yêu cầu tự khai. Máy chủ xác định contact từ lời mời và bằng chứng nguồn đã được xác minh.

### 4.3. Kênh trao đổi không thay thế giao thức xác nhận

Contact có thể cần trao đổi với chủ tài khoản qua kênh quen dùng đã có từ trước để hiểu tình huống. Không nên coi số điện thoại mới nằm trong lời nhắn của người yêu cầu là kênh độc lập đã được tin cậy.

Trao đổi riêng có thể hỗ trợ quyết định của contact, nhưng đoạn chat được chuyển tiếp không tự là phản hồi có thẩm quyền của dịch vụ. Quyết định cuối cùng của contact vẫn cần được gửi qua quy trình xác nhận mà hệ thống kiểm soát.

## 5. Ràng buộc nội dung với đúng ngữ cảnh

Một phản hồi cần gắn tối thiểu với các giá trị do máy chủ quản lý:

- Tenant và tài khoản đang được khôi phục.
- Yêu cầu khôi phục cùng phiên bản nội dung của yêu cầu.
- Contact và phiên bản liên kết của contact với tài khoản.
- Lời mời hoặc challenge cụ thể, thời điểm cấp và thời hạn.
- Loại phản hồi và mục đích mà phản hồi được dùng.
- Cơ chế xác thực nguồn phản hồi cùng trạng thái thu hồi, tiêu thụ hoặc thay thế.

Client có thể gửi định danh để định tuyến, nhưng định danh đó phải được đối chiếu với dữ liệu đã ràng buộc phía máy chủ. Việc một URL có `requestId` hợp lệ không chứng minh người đang truy cập có quyền phản hồi cho yêu cầu đó.

Ví dụ, contact xác nhận “tôi đã trao đổi với người này về việc họ mất thiết bị”. Hệ thống không được diễn giải thành “contact cho phép thay email khôi phục sang địa chỉ X”. Nếu mục tiêu hoặc hành động quan trọng thay đổi, cần phiên bản yêu cầu mới và xác nhận lại khi chính sách yêu cầu; không tái sử dụng ý kiến cũ cho ngữ cảnh mới.

Nguyên tắc hiển thị rõ dữ liệu quan trọng trước khi xác nhận tương ứng với hướng dẫn của OWASP về transaction authorization. Khi áp dụng vào bài toán này, nội dung contact nhìn thấy phải phù hợp với ý nghĩa mà máy chủ sẽ ghi nhận, thay vì dùng một nút đồng ý mơ hồ. [OWASP — Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)

### Thông tin contact nên nhìn thấy

Trang xác nhận có thể trình bày tên dịch vụ, tham chiếu tài khoản đã che bớt, mã hồ sơ để đối chiếu, loại yêu cầu và hệ quả của phản hồi. Chỉ hiển thị đủ thông tin để nhận biết tình huống, không cung cấp toàn bộ hồ sơ cá nhân hoặc thông tin của các contact khác.

Một diễn đạt phù hợp cho mô hình ý kiến phụ trợ:

> Bạn đang phản hồi cho yêu cầu hỗ trợ khôi phục tài khoản kết thúc bằng `…42`. Ý kiến của bạn được dùng để đánh giá yêu cầu này; thao tác này không đăng nhập thay người đó. Nếu không đủ thông tin, hãy chọn “Không xác định”.

Nếu có nội dung do người yêu cầu nhập, giao diện phải phân biệt với thông tin do dịch vụ xác lập và hiển thị an toàn. Một lời nhắn tự khai không được trông như chỉ dẫn chính thức của bộ phận an toàn.

## 6. Thiết kế token và hành động xác nhận

### 6.1. Token phải có phạm vi hẹp

Mỗi lời mời cần một challenge riêng. Nếu dùng token ngẫu nhiên, token phải được tạo bằng nguồn ngẫu nhiên phù hợp, có entropy đủ lớn cho trường hợp sử dụng và được lưu dưới dạng kiểm chứng phù hợp. Token không được sinh từ email, thời gian gửi hoặc số thứ tự có thể đoán.

Token của contact chỉ dùng cho mục đích phản hồi được chỉ định. Nó không phải token đặt lại mật khẩu, token bỏ MFA hoặc quyền đăng ký passkey mới.

Nếu dùng đối tượng có chữ ký hoặc MAC, cần kiểm tra thuật toán, khóa, bên phát hành, đối tượng nhận, mục đích và thời hạn theo định dạng đã chọn. Chữ ký bảo vệ nội dung khỏi sửa đổi trong phạm vi được ký. Nó không tự cung cấp sử dụng một lần, thu hồi hoặc xác nhận người giữ token là con người dự kiến.

Muốn chống phát lại cùng một token, hệ thống vẫn cần trạng thái hoặc cơ chế tương đương để biết token đã được tiêu thụ. Có thời hạn chỉ giới hạn khoảng thời gian phát lại; nó không ngăn phát lại trong khoảng đó.

### 6.2. Không đồng ý chỉ bằng cách mở liên kết

Liên kết trong email hoặc tin nhắn có thể bị phần mềm bảo mật, trình xem trước hoặc người dùng mở ngoài ý muốn. Do đó, thao tác đọc trang không được tự ghi nhận đồng ý, từ chối hoặc tiêu thụ quyền phản hồi.

Luồng phù hợp cho trang web là:

1. Mở trang chỉ để xem thông tin và hướng dẫn.
2. Thiết lập bằng chứng nguồn hoặc yêu cầu contact xác thực theo tuyến đã chọn.
3. Hiển thị nội dung cần xác nhận và các lựa chọn rõ ràng.
4. Gửi quyết định bằng yêu cầu thay đổi trạng thái có bảo vệ phù hợp.
5. Máy chủ kiểm tra lại các ràng buộc rồi mới ghi nhận phản hồi.

Với phiên dựa trên cookie, cần cơ chế chống CSRF phù hợp, chẳng hạn cơ chế sẵn có của framework và kiểm tra ở máy chủ. Dùng `POST` là chưa đủ để chống CSRF. OWASP khuyến nghị không dùng `GET` cho thao tác thay đổi trạng thái. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

Trang chứa dữ liệu nhạy cảm hoặc quyền phản hồi cần tránh rò token qua log, công cụ phân tích, tài nguyên bên thứ ba và thông tin referrer. Không dùng URL chuyển hướng tùy ý do người yêu cầu cung cấp làm đích sau xác nhận.

### 6.3. Không trộn hai loại mã

Một cơ chế recovery contact có thể chủ động yêu cầu contact chuyển mã khôi phục cho chủ tài khoản theo quy trình của nó. Trong mô hình phản hồi trực tiếp của bài này, token xác nhận của contact có mục đích khác và không nên được chuyển cho người yêu cầu để họ tự bấm thay.

Tài liệu hướng dẫn cần nói rõ loại nào được chuyển, cho ai và trong điều kiện nào. Không yêu cầu contact đưa mật khẩu, mã đăng nhập, mã MFA hoặc thông tin xác thực riêng của họ cho người yêu cầu hoặc nhân viên hỗ trợ.

## 7. Phân loại phản hồi và trạng thái xử lý

Không nên biểu diễn toàn bộ kết quả bằng một biến boolean `approved`. Hệ thống cần phân biệt quyết định mà contact đưa ra với tình trạng kỹ thuật của việc thu nhận.

| Giá trị | Ý nghĩa trong mô hình minh họa | Hướng xử lý |
| --- | --- | --- |
| `CONFIRM` | Contact đưa ra xác nhận trong phạm vi đã hiển thị | Có thể đưa vào đánh giá nếu mọi điều kiện sử dụng đạt |
| `DENY` | Contact không xác nhận hoặc nhận thấy dấu hiệu đáng ngờ | Giữ lại tín hiệu và đánh giá theo chính sách |
| `UNKNOWN` | Contact chưa đủ thông tin để kết luận | Không tính là xác nhận tích cực |
| `NO_RESPONSE` | Chưa có phản hồi có chủ ý được ghi nhận | Không suy thành đồng ý hoặc từ chối |
| `INVALID` | Chưa xác minh được nguồn, nội dung hoặc ràng buộc | Không đưa vào tập bằng chứng hợp lệ |
| `EXPIRED` / `REVOKED` | Quyền phản hồi hoặc điều kiện dùng đã hết hiệu lực | Không chấp nhận thành phản hồi mới |

`NO_RESPONSE` và `INVALID` là trạng thái xử lý, không phải lựa chọn mà contact nhất thiết phải thấy trên giao diện. Mô hình dữ liệu có thể tách chúng thành các trường khác nhau để tránh nhầm lẫn.

Không tự đổi timeout, lỗi giao nhận hoặc thất bại nhà cung cấp thành `CONFIRM`. Một sự kiện “đã đọc thông báo” cũng không được ánh xạ thành lựa chọn tích cực.

Một phản hồi `DENY` có thể khiến hồ sơ cần xem xét thêm, nhưng không nên tự trao cho bất kỳ contact nào quyền khóa vĩnh viễn tài khoản của người khác. Chính sách cần cân nhắc contact đã bị xâm phạm, tranh chấp hoặc hành vi gây từ chối dịch vụ.

## 8. Ghi nhận nguyên tử, chống đếm trùng và phát lại

### 8.1. Định danh người phản hồi, không đếm số tin nhắn

Một contact có thể gửi lại vì mất mạng, dùng nhiều thiết bị hoặc có nhiều địa chỉ liên lạc. Tất cả vẫn là một nguồn phản hồi theo định danh đã đăng ký, không phải nhiều người độc lập.

Cần ràng buộc duy nhất cho đóng góp của contact vào cùng phiên bản yêu cầu. Khóa theo `eventId` của nhà cung cấp chỉ giúp chống giao lặp sự kiện; nó không ngăn contact tạo nhiều sự kiện khác nhau để được đếm nhiều lần.

Khi gửi lại lời mời, dịch vụ phải xác định lời mời mới thay thế lời mời cũ hay dùng cùng quyền phản hồi. Dù lựa chọn nào, một contact không được có thêm số phiếu vì nhận thêm email.

### 8.2. Kiểm tra và tiêu thụ trong cùng ranh giới nguyên tử

Nếu hai node cùng thấy token chưa dùng rồi đều ghi nhận phản hồi, hệ thống có thể đếm trùng hoặc chấp nhận hai quyết định mâu thuẫn. Thao tác cần kiểm tra trạng thái hiện hành, ghi phản hồi và tiêu thụ challenge một cách nguyên tử trên trạng thái dùng chung.

Mã giả sau mô tả tuyến contact có tài khoản riêng; tuyến chỉ dùng quyền kiểm soát kênh cần kiểm tra riêng theo mức bằng chứng của nó:

```text
recordContactResponse(contactSession, token, decision, idempotencyKey):
    require validContactAuthentication(contactSession)
    require validStateChangingRequestProtection()
    require decision in {CONFIRM, DENY, UNKNOWN}

    challengeRef = resolveServerChallengeFromToken(token)

    return transaction:
        lockRequestContactAndChallengeInStableOrder(challengeRef)

        require challengeRef.contactSubject == contactSession.subject
        require currentContactEnrollmentIsEligible()
        require enrollmentVersionMatchesChallenge()
        require requestVersionAndPurposeMatchChallenge()

        previous = findIdempotentResponse(idempotencyKey, challengeRef)
        if previous exists:
            require previous.matches(decision, challengeRef.context)
            return authorizedViewOf(previous)

        require requestIsOpen()
        require challengeIsUnusedNotExpiredAndNotRevoked()
        require noEffectiveResponseFromThisContactForThisRequestVersion()

        response = insertUniqueBoundResponse(decision, challengeRef)
        markChallengeConsumed()
        invalidateSiblingInvitationsForSameContactContribution()
        appendDecisionEvaluationEventToOutbox(response)

        return RESPONSE_RECORDED
```

`RESPONSE_RECORDED` nghĩa là ý kiến đã được lưu, không có nghĩa yêu cầu khôi phục được duyệt. Sự kiện đánh giá tiếp theo cần được xử lý chống lặp; việc dùng outbox giúp gắn việc ghi dữ liệu với công việc cần phát đi mà không giả định mạng giao đúng một lần.

Một retry cùng nội dung trả trạng thái cũ theo quyền truy cập hiện tại. Cùng idempotency key nhưng đổi quyết định phải bị từ chối xung đột. Không cho sửa một phản hồi đã ghi bằng cách gửi lại cùng token với giá trị khác.

Nếu contact muốn thay đổi ý kiến, cần một thao tác có xác thực, ràng buộc ngữ cảnh và chính sách riêng. Giữ lại lịch sử, ghi bản thay thế và tính lại quyết định; không cộng cả bản cũ lẫn bản mới. Sau khi đã hoàn tất khôi phục, một thay đổi muộn cần đi vào quy trình xử lý sự cố phù hợp thay vì giả vờ đảo ngược mọi tác dụng đã xảy ra.

### 8.3. Đánh giá lại trước khi cấp quyền

Một phản hồi hợp lệ ở thời điểm nhận có thể không còn đủ điều kiện khi hệ thống chuẩn bị cấp quyền. Ví dụ, yêu cầu bị hủy, contact bị thu hồi hoặc phát hiện dấu hiệu xâm phạm trong thời gian chờ.

Bước quyết định cuối cùng phải kiểm tra trạng thái và phiên bản của tập bằng chứng mà nó dùng. Không dùng một cờ `quorumReached=true` cũ để bỏ qua thay đổi mới. Việc chốt quyết định và cấp quyền cần có ranh giới nguyên tử hoặc kiểm tra phiên bản tương đương để tránh cấp quyền dựa trên dữ liệu đã lỗi thời.

## 9. Phản hồi qua hệ thống trung gian

Một nhà cung cấp có thể gửi webhook về trạng thái lời mời hoặc quyết định của contact. Dịch vụ phải xác định rõ từng loại sự kiện thực sự biểu diễn điều gì.

- Sự kiện giao nhận chỉ cập nhật giao nhận.
- Sự kiện mở liên kết chỉ cập nhật thông tin truy cập nếu chính sách cho phép lưu.
- Sự kiện xác nhận chỉ được xem là phản hồi nếu hợp đồng tích hợp và bằng chứng đi kèm chứng minh đúng quy trình xác nhận đã thực hiện.

Với webhook, cần xác thực nguồn bằng cơ chế mà nhà cung cấp hỗ trợ; kiểm tra chữ ký hoặc MAC trên đúng dữ liệu được bảo vệ, các ràng buộc thời gian và chống phát lại phù hợp. Nếu giao thức ký trên byte gốc của body, không phân tích rồi tuần tự hóa lại trước khi kiểm chữ ký.

Sau bước xác thực nguồn, vẫn phải đối chiếu tenant, giao dịch, lời mời, contact, phiên bản yêu cầu và loại quyết định. Một webhook được xác thực từ nhà cung cấp không có quyền cập nhật bất kỳ hồ sơ nào chỉ vì body chứa một `requestId` tồn tại.

Không tin tên hiển thị email, trường `From`, ảnh chụp tin nhắn hoặc tên tài khoản mạng xã hội làm bằng chứng tương đương một phản hồi được xác thực. Nếu dùng tài liệu trao đổi làm thông tin cho nhân viên xem xét, cần ghi đúng nguồn và giới hạn của nó.

Khi lỗi xác thực nguồn hoặc không đối soát được ngữ cảnh, giữ sự kiện ở trạng thái không hợp lệ hoặc chờ xử lý. Không cho lỗi tích hợp tự trở thành đường bỏ qua kiểm tra.

## 10. Giá trị chứng cứ và giới hạn của việc tổng hợp

Tập phản hồi hợp lệ về kỹ thuật chỉ là đầu vào của quyết định khôi phục. Chính sách cần xét phản hồi nói điều gì, contact biết được thông tin bằng cách nào và có bằng chứng độc lập nào khác.

Hai contact không tự tương đương với hai yếu tố xác thực. Họ có thể dùng chung hộp thư, cùng bị tác động bởi một kẻ tấn công hoặc chỉ lặp lại lời kể của người yêu cầu. Hai email khác nhau cũng không chứng minh đó là hai con người khác nhau.

Nếu ứng dụng dùng điều kiện số lượng, cần định nghĩa rõ nguồn độc lập, tư cách contact và xử lý phản hồi mâu thuẫn. Không tự động loại bỏ một cảnh báo đáng tin chỉ vì có nhiều phản hồi đồng ý hơn. Điều kiện số lượng của ứng dụng không được gắn nhãn là đáp ứng một tiêu chuẩn bảo đảm danh tính nếu chưa thực sự đáp ứng các yêu cầu liên quan.

Không phản hồi không đồng nghĩa gian lận. Contact có thể mất thiết bị, không truy cập được địa chỉ cũ hoặc không biết tình huống. Khi không có đủ thông tin, cần tuyến thay thế phù hợp với mức rủi ro; không hạ tiêu chuẩn bằng cách yêu cầu tìm bất kỳ người nào sẵn sàng đồng ý.

## 11. Chống ép xác nhận và bảo vệ riêng tư

Một cuộc tấn công có thể gửi lặp lời mời cho đến khi contact bấm xác nhận để hết phiền. Dịch vụ cần giới hạn gửi theo hồ sơ, tài khoản mục tiêu, người nhận và nguồn yêu cầu; gửi lại không được mở rộng ngân sách hoặc tạo thêm đóng góp.

Giao diện cần có lựa chọn không xác định và báo đáng ngờ rõ ràng. Nếu contact không có đủ cơ sở, hệ thống không nên gây áp lực rằng chủ tài khoản chắc chắn mất quyền truy cập vĩnh viễn trừ khi họ đồng ý ngay.

Những nội dung nên được bảo vệ gồm danh sách contact, địa chỉ liên lạc, mối quan hệ, lời giải thích và lựa chọn cụ thể. Người yêu cầu không cần thấy toàn bộ contact đã phản hồi gì hoặc thông tin chi tiết có thể dùng để gây áp lực lên người từ chối.

Thông báo cho contact chỉ nên cung cấp lượng thông tin cần thiết để hiểu và xử lý lời mời. Không gửi toàn bộ dữ liệu định danh, bí mật tài khoản, mã MFA hoặc thông tin của những contact khác. Nội dung tự khai của người yêu cầu cần được hạn chế và hiển thị an toàn.

Sau khi xử lý, dữ liệu phải được lưu giữ và xóa theo chính sách đã xác định. Không nhân bản token, địa chỉ hoặc toàn bộ trao đổi sang mọi hệ thống log chỉ để tiện điều tra.

## 12. Dấu vết cần giữ để giải thích quyết định

Một bản ghi phản hồi có thể gồm:

| Nhóm dữ liệu | Ví dụ |
| --- | --- |
| Định danh nội bộ | Request ID, response ID, contact reference |
| Phiên bản | Phiên bản yêu cầu, đăng ký contact và chính sách |
| Nguồn đã xác minh | Loại kênh, chủ thể đã xác thực, tham chiếu giao dịch |
| Ngữ cảnh | Mục đích và phiên bản nội dung được xác nhận |
| Vòng đời | Thời điểm phát hành, phản hồi, tiêu thụ, thu hồi hoặc thay thế |
| Kết quả | Lựa chọn, trạng thái kỹ thuật, lý do đủ hoặc không đủ điều kiện |
| Tác động | Phản hồi được dùng trong quyết định nào, ở phiên bản nào |

Không ghi token nguyên văn, cookie, thông tin xác thực hoặc toàn bộ trao đổi nhạy cảm vào nhật ký thông thường. Nếu lưu giá trị kiểm chứng của token ngẫu nhiên đủ mạnh, vẫn cần giới hạn quyền truy cập và bảo vệ khóa liên quan nếu dùng MAC.

Khi phát hiện contact bị xâm phạm, hệ thống cần tìm được các phản hồi và hồ sơ phụ thuộc vào contact đó để đánh giá tác động. Lịch sử không nên bị xóa hoặc sửa thành trạng thái “chưa từng phản hồi” chỉ vì phát hiện vấn đề sau này.

## 13. Những tình huống áp dụng

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| Bộ quét email tự mở URL trong lời mời | Không ghi quyết định và không tiêu thụ quyền phản hồi chỉ bằng thao tác xem |
| Người yêu cầu lấy được liên kết nhưng đăng nhập bằng tài khoản khác contact | Tuyến yêu cầu contact đăng nhập phải từ chối vì chủ thể không khớp |
| Contact gửi lại cùng phản hồi vì không thấy thông báo thành công | Trả trạng thái đã ghi theo quyền hiện tại, không đếm thêm |
| Cùng token được gửi với cả `CONFIRM` và `DENY` | Chỉ thao tác được chấp nhận nguyên tử có hiệu lực; thay ý kiến dùng quy trình riêng |
| Callback được ký đúng nhưng thuộc tenant khác | Từ chối cập nhật hồ sơ vì ngữ cảnh không khớp |
| Hồ sơ thay đổi mục đích sau khi contact xác nhận | Đánh giá lại ràng buộc; không dùng xác nhận cũ cho phạm vi mới |
| Contact bị thu hồi trong thời gian chờ quyết định | Tính lại điều kiện sử dụng trước khi cấp quyền |
| Hai địa chỉ khác nhau cùng ánh xạ đến một contact | Không tính thành hai nguồn độc lập |
| Contact không phản hồi hoặc chọn không xác định | Không coi là đồng ý; dùng tuyến thay thế theo chính sách |
| Có cảnh báo đáng ngờ bên cạnh nhiều xác nhận tích cực | Đánh giá mâu thuẫn và rủi ro, không chỉ lấy đa số |

## 14. Ranh giới với bước hoàn tất khôi phục

Phản hồi của contact phải đi vào hồ sơ bằng chứng, không trực tiếp thành một session đầy đủ của tài khoản đang khôi phục. Contact cũng không được nhận quyền đăng nhập thay chủ tài khoản chỉ vì họ tham gia hỗ trợ.

Khi toàn bộ quy trình khôi phục đã đủ điều kiện, hệ thống mới cấp quyền có phạm vi cụ thể cho người được phép thực hiện hành động như đặt lại mật khẩu hoặc đăng ký yếu tố mới. Quyền đó cần thời hạn, ràng buộc với tài khoản và quyết định tương ứng, cùng kiểm soát sử dụng một lần. Xử lý session, refresh token và yếu tố xác thực nghi bị mất hoặc xâm phạm thuộc bước hoàn tất.

Một luồng bảo vệ tốt giữ được chuỗi liên kết: contact đã đăng ký → quyền phản hồi còn hiệu lực → ý kiến có chủ ý về đúng ngữ cảnh → bản ghi không bị sửa hoặc đếm trùng → đánh giá theo chính sách → quyết định khôi phục. Mỗi mắt xích có điều kiện riêng; chỉ biết rằng một người đã bấm đồng ý chưa đủ thay cho cả chuỗi đó.
