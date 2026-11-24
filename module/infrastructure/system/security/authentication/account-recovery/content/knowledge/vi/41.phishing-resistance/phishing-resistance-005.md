# Out of band confirmation

## 1. Xác nhận ngoài băng trong khôi phục tài khoản

**Out of band confirmation** là việc xác nhận một thao tác qua kênh tách khỏi kênh đang khởi tạo thao tác đó. Trong khôi phục tài khoản, trình duyệt có thể gửi yêu cầu thay MFA, còn một ứng dụng đã đăng ký trên thiết bị tin cậy nhận yêu cầu và cho chủ tài khoản xem xét.

Mục đích là tạo thêm một điểm kiểm soát: chiếm được trình duyệt, mật khẩu hoặc đường dẫn bắt đầu recovery chưa đủ để hoàn thành thay đổi nhạy cảm. Giá trị bảo vệ phụ thuộc vào kênh phụ có còn nằm dưới quyền kiểm soát của chủ tài khoản, dữ liệu phê duyệt có đúng với thao tác sẽ thực hiện và kết quả phê duyệt được trao cho ai.

Ví dụ: Lan mất điện thoại chứa ứng dụng TOTP nhưng vẫn còn máy tính bảng đã đăng ký. Một yêu cầu khôi phục có thể cần xác nhận trên máy tính bảng trước khi hệ thống cho đăng ký lại MFA. Nếu Lan mất cả hai thiết bị, hệ thống phải chuyển sang phương thức recovery khác đáp ứng chính sách của tài khoản; gửi thêm thông báo đến điện thoại đã mất không tạo ra bằng chứng mới.

Cần phân biệt ba loại thông điệp:

| Loại | Ý nghĩa | Có tự cấp quyền recovery không? |
| --- | --- | --- |
| Thông báo | Cho biết một yêu cầu hoặc thay đổi đã xảy ra | Không |
| Xác nhận giao dịch recovery | Người dùng chấp thuận một thay đổi được mô tả cụ thể | Chỉ là một điều kiện trong chính sách |
| Bằng chứng xác thực | Chứng minh quyền kiểm soát một authenticator hoặc bí mật | Phải được kiểm tra theo cơ chế và mức bảo đảm tương ứng |

Một email “MFA vừa được thay đổi” giúp phát hiện sự cố, nhưng không phải bước chặn thay đổi. Một nút “Tôi đồng ý” trên push cũng chưa chứng minh rằng chủ tài khoản đang kiểm soát trình duyệt sẽ nhận quyền truy cập.

## 2. Vì sao ngoài băng chưa đồng nghĩa chống phishing?

NIST SP 800-63B-4 không coi xác thực out-of-band là phishing-resistant. Mã nhập tay có thể bị chuyển tiếp qua trang giả; hai kênh truyền không tự tạo ràng buộc với đúng bên xác minh. NIST cũng phân biệt việc gửi mã recovery hoặc xác nhận địa chỉ email với out-of-band authentication: email không được dùng làm authenticator ngoài băng theo định nghĩa đó, dù vẫn có thể tham gia quy trình recovery. Xem [NIST — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).

Một tình huống điển hình:

1. Kẻ tấn công mở recovery trên dịch vụ thật bằng tên tài khoản của nạn nhân.
2. Trang giả yêu cầu nạn nhân nhập mã vừa nhận qua SMS.
3. Mã được chuyển ngay sang yêu cầu recovery do kẻ tấn công khởi tạo.
4. Máy chủ chấp nhận đúng mã, nhưng người được hưởng kết quả lại là kẻ tấn công.

Token dùng một lần và thời hạn ngắn có thể chặn phát lại sau đó, nhưng vẫn có thể bị sử dụng lần đầu bởi kẻ chuyển tiếp. Vì vậy phải tách các thuộc tính:

- **Chống phát lại:** bằng chứng đã dùng không dùng lại được.
- **Ràng buộc giao dịch:** bằng chứng chỉ có giá trị cho một yêu cầu và một tập thay đổi cụ thể.
- **Chống phishing:** cơ chế ngăn bên giả mạo thu thập rồi sử dụng bằng chứng ở bên xác minh thật.
- **Kiểm soát người nhận kết quả:** quyền vừa khôi phục được trao cho đúng chủ thể đã được xác minh.

Các thuộc tính này bổ sung cho nhau. Một chữ ký hợp lệ từ ứng dụng tin cậy có thể ràng buộc dữ liệu giao dịch, nhưng không tự ngăn người dùng bị lừa phê duyệt một giao dịch bất lợi.

## 3. Đánh giá tính độc lập của kênh

Đừng chỉ đếm số địa chỉ hoặc ứng dụng. Hãy xét đường đi mà kẻ tấn công có thể dùng để kiểm soát từng kênh.

| Kênh hoặc bằng chứng | Lợi ích có thể có | Giới hạn cần xét trong recovery |
| --- | --- | --- |
| Email đã đăng ký trước | Liên lạc khi mất một thiết bị, cảnh báo thay đổi | Hộp thư có thể bị chiếm; liên kết có thể bị chuyển tiếp |
| SMS/cuộc gọi đến số có sẵn | Có thể tiếp cận người dùng ngoài trình duyệt | Đổi SIM, chuyển mạng, số tái cấp và lừa lấy mã |
| Ứng dụng có khóa thiết bị đã liên kết | Có thể xác thực thiết bị và phê duyệt dữ liệu cụ thể | Thiết bị có thể bị mất hoặc nhiễm mã độc; người dùng có thể bị dụ bấm đồng ý |
| Mã recovery đã lưu riêng | Không cần thiết bị đang mất | Là bí mật có thể bị lấy cắp hoặc chia sẻ |
| Passkey hoặc security key dự phòng | Có thể xác thực bằng cơ chế chống phishing được triển khai đúng | Phải còn sử dụng được; không phải cứ là “kênh thứ hai” thì tự thành out-of-band authentication |

Ba câu hỏi thiết kế quan trọng:

1. **Kênh có được thiết lập từ trước không?** Địa chỉ do người yêu cầu vừa nhập chưa phải kênh tin cậy để cho phép thay MFA.
2. **Có cùng điểm thất bại không?** Email và ứng dụng cùng nằm trên điện thoại bị mất có thể không còn độc lập trong tình huống cần khôi phục.
3. **Có vòng phụ thuộc không?** Nếu email được khôi phục bằng chính số điện thoại đang nghi bị chiếm, dùng cả hai không nhất thiết tạo thêm bằng chứng độc lập.

Một tài khoản đồng bộ đám mây có thể là điểm kiểm soát chung của email, passkey đồng bộ và thông báo. Hai thiết bị vật lý khác nhau vẫn có thể chịu cùng một sự cố tài khoản.

Kênh cũ cũng không luôn an toàn. Nếu chủ tài khoản đã thay số vì số cũ bị chiếm, không tự đưa số cũ trở lại quy trình chỉ vì nó có lịch sử lâu hơn. Hệ thống cần trạng thái hiện hành, lý do thay đổi và bằng chứng về việc kênh còn đáng tin.

## 4. Xác nhận đúng thao tác mà người dùng sẽ cho phép

Đề xuất thiết kế trong bài này xem recovery như một giao dịch nhạy cảm. Ứng dụng xác nhận phải lấy nội dung từ máy chủ, thay vì tin mô tả do trình duyệt đang yêu cầu recovery gửi sang.

Một màn hình phê duyệt nên thể hiện:

- Tài khoản hoặc dịch vụ liên quan, với dữ liệu được che phù hợp.
- Thao tác chính xác: đặt lại mật khẩu, thay TOTP, thêm passkey hay đổi email recovery.
- Authenticator hoặc kênh nào bị thay, cái gì được thêm và hậu quả đối với phiên đăng nhập.
- Thời điểm yêu cầu, mã tham chiếu dễ đối chiếu và hạn xác nhận.
- Lựa chọn từ chối hoặc báo yêu cầu không do mình khởi tạo.

Ví dụ nội dung:

> Yêu cầu thay phương thức MFA của tài khoản l•••@example.com.
>
> Nếu được hoàn tất, TOTP trên thiết bị đã báo mất sẽ bị thu hồi. Việc đăng ký phương thức mới sẽ tiếp tục trong ứng dụng này.
>
> Chỉ xác nhận nếu bạn đang thực hiện yêu cầu này. Bộ phận hỗ trợ không yêu cầu bạn đọc mã hoặc phê duyệt thay họ.

Tên trình duyệt, IP và vị trí suy đoán chỉ là ngữ cảnh. Kẻ tấn công có thể bắt chước thiết bị hoặc dùng hạ tầng gần nạn nhân; không dùng những nhãn đó làm bằng chứng danh tính.

OWASP hướng dẫn việc phê duyệt giao dịch phải cho người dùng nhận biết dữ liệu quan trọng, và máy chủ phải bảo vệ dữ liệu đó khỏi thay đổi giữa lúc xác nhận và thực thi. Áp dụng nguyên tắc này vào recovery là lựa chọn thiết kế của bài: nếu tập thay đổi khác đi, phải tạo một giao dịch cần xác nhận mới. Xem [OWASP — Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

## 5. Luồng tham chiếu khi còn một thiết bị tin cậy

Luồng sau là mô hình minh họa cho hệ thống có ứng dụng đã liên kết khóa thiết bị. Nó không phải tuyên bố rằng một giao thức push tùy biến đáp ứng đầy đủ yêu cầu của NIST hoặc một mức AAL cụ thể.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt yêu cầu
    participant R as Recovery Service
    participant A as Ứng dụng đã liên kết
    participant P as Policy Engine
    B->>R: Bắt đầu recovery
    R->>P: Kiểm tra phương thức được phép
    R-->>B: Phản hồi chung, không cấp session
    R-->>A: Thông báo có yêu cầu đang chờ
    A->>R: Xác thực thiết bị, lấy nội dung từ máy chủ
    R-->>A: Challenge và tập thay đổi cố định
    A->>R: Chấp thuận hoặc từ chối, kèm bằng chứng
    R->>P: Kiểm tra lại rủi ro và điều kiện recovery
    R-->>A: Tiếp tục trong ngữ cảnh đã xác minh
    A->>R: Đăng ký authenticator mới theo quy trình riêng
    R->>R: Hoàn tất một lần, thu hồi quyền cũ theo chính sách
    R-->>B: Chỉ thông báo trạng thái phù hợp
~~~

### Bước 1 — Tiếp nhận nhưng chưa tin cậy

Endpoint bắt đầu recovery trả thông điệp chung, chẳng hạn “Nếu yêu cầu hợp lệ, hướng dẫn sẽ được gửi đến kênh đã đăng ký”. Không lộ việc tài khoản tồn tại, danh sách thiết bị, số điện thoại đầy đủ hoặc email recovery.

Một mã theo dõi yêu cầu không được tự trở thành vé hoàn tất recovery. Endpoint theo dõi cũng cần kiểm soát truy cập hoặc hạn chế thông tin để tránh tạo đường dò dữ liệu mới.

### Bước 2 — Chọn kênh theo chính sách

Máy chủ chọn từ những kênh đã được xác minh và còn hợp lệ. Người yêu cầu không được thay địa chỉ đích ngay trong cùng giao dịch rồi dùng địa chỉ mới để tự xác nhận.

Nếu thiết bị được khai báo mất, không gửi phê duyệt đến thiết bị đó như bằng chứng quyết định. Nếu kênh vừa thay đổi hoặc có tín hiệu chiếm đoạt, yêu cầu bằng chứng bổ sung hoặc chuyển quy trình khác.

### Bước 3 — Push chỉ là tín hiệu đánh thức

Payload push chỉ cần thông báo có yêu cầu. Ứng dụng mở kết nối được bảo vệ đến backend, xác thực bằng cơ chế đã liên kết và tải nội dung đang chờ.

Push token là địa chỉ phân phối thông báo, không phải bằng chứng sở hữu tài khoản. Không đặt recovery token, dữ liệu đầy đủ của tài khoản hay quyền phê duyệt vào thông báo trên màn hình khóa.

### Bước 4 — Phê duyệt có ràng buộc

Bằng chứng cần gắn với ít nhất yêu cầu, hành động, tập thay đổi, challenge ngẫu nhiên, thời hạn và thiết bị được phép xác nhận.

Mở khóa ứng dụng bằng PIN hoặc sinh trắc học có thể giúp bảo vệ thao tác cục bộ. Backend chỉ biết điều mà giao thức và authenticator thực sự chứng minh; không tin một trường JSON do client tự khai là “đã kiểm tra sinh trắc học”.

### Bước 5 — Kiểm tra lại trước khi hoàn tất

Phê duyệt không thay thế chính sách recovery. Backend vẫn phải kiểm tra bằng chứng khác, trạng thái kênh, các cảnh báo mới và việc yêu cầu đã bị hủy hay chưa.

Khoảng chờ nếu có phải được định nghĩa theo rủi ro. Nó tạo cơ hội phát hiện và phản đối, nhưng im lặng trong khoảng chờ không được tự chuyển thành sự đồng ý.

### Bước 6 — Trao kết quả cho đúng người

Trong ví dụ, người dùng tiếp tục đăng ký authenticator mới trong ứng dụng đã xác minh. Trình duyệt đã khởi tạo yêu cầu không tự nhận session đầy đủ.

Đây là điểm thường bị bỏ sót: một kẻ tấn công có thể sở hữu trình duyệt khởi tạo trong khi chính chủ vô tình phê duyệt trên thiết bị khác. Nếu chỉ thấy trạng thái APPROVED rồi cấp session cho trình duyệt đó, hệ thống đã trao tài khoản cho kẻ tấn công.

Nếu cần chuyển sang một thiết bị mới, thiết kế phải có bước chuyển giao được xác thực và bằng chứng kiểm soát khóa đích. Không phát bearer token có toàn quyền chỉ cho bên biết request ID. Ràng buộc với khóa đích giúp ngăn thay khóa sau phê duyệt, nhưng tự nó chưa chứng minh rằng khóa đích thuộc chủ tài khoản; quy trình chuyển giao vẫn phải giải quyết điều này.

## 6. Trạng thái và dữ liệu của yêu cầu

Một mô hình trạng thái minh họa:

~~~text
PENDING_CONFIRMATION
    -> CONFIRMED
    -> READY_TO_COMPLETE
    -> COMPLETED

Từ trạng thái chưa kết thúc:
    -> DENIED
    -> CANCELLED
    -> EXPIRED
~~~

CONFIRMED nghĩa là một điều kiện đã được đáp ứng. READY_TO_COMPLETE nghĩa là toàn bộ điều kiện hiện tại đã đạt, bao gồm khoảng chờ nếu chính sách có yêu cầu. COMPLETED là thay đổi đã được áp dụng.

| Trường | Vai trò trong mô hình |
| --- | --- |
| requestId | Định danh ngẫu nhiên của giao dịch |
| accountId | Chủ tài khoản mà máy chủ đã ánh xạ |
| action | Loại thao tác được cho phép |
| changeSetDigest | Dấu băm của tập thay đổi có định dạng chuẩn |
| challenge | Giá trị ngẫu nhiên mới cho lần xác nhận |
| eligibleDeviceId | Thiết bị được phép xác nhận |
| channelVersion | Phiên bản thông tin kênh tại lúc lập yêu cầu |
| createdAt / expiresAt | Giới hạn thời gian |
| confirmationConsumedAt | Thời điểm bằng chứng xác nhận đã được dùng |
| state / version | Trạng thái và kiểm soát cập nhật đồng thời |

Nếu có nhiều thiết bị hợp lệ, lưu danh sách và chính sách phê duyệt rõ ràng; không coi việc một thiết bị bất kỳ trả lời là đủ trong mọi trường hợp.

Máy chủ phải tự lấy accountId và tập thay đổi từ bản ghi chuẩn. Digest do client gửi chỉ dùng để đối chiếu, không làm nguồn dữ liệu thực thi. Dữ liệu ký cần có quy tắc chuẩn hóa, phiên bản và miền sử dụng riêng, chẳng hạn ACCOUNT_RECOVERY_CONFIRM_V1, để tránh nhầm với chữ ký dùng cho mục đích khác.

Không dùng một cờ account.recoveryApproved có hiệu lực cho mọi yêu cầu. Hai giao dịch cùng tài khoản vẫn là hai quyền khác nhau.

## 7. Minh họa xử lý phê duyệt phía Java

Đoạn mã dưới đây mô tả ranh giới trách nhiệm; các repository, policy và verifier là thành phần giả định. Phần xác thực thiết bị, xác minh mật mã và quản lý giao dịch cần được triển khai bằng cơ chế phù hợp của hệ thống.

~~~java
record Confirmation(
    String requestId,
    String challenge,
    String changeSetDigest,
    byte[] proof
) {}

void confirmRecovery(
    AuthenticatedDevice device,
    Confirmation input,
    Instant now
) {
    transactions.run(() -> {
        RecoveryRequest request =
            requests.findByIdForUpdate(input.requestId());

        if (request == null
                || request.state() != State.PENDING_CONFIRMATION
                || !now.isBefore(request.expiresAt())) {
            throw new InvalidRecoveryRequest();
        }

        // device được tạo từ lớp xác thực, không từ deviceId trong body.
        devices.requireEligibleAndNotRevoked(
            device, request.accountId(), request.eligibleDeviceId()
        );

        policy.requireConfirmationAllowed(request, device, now);

        if (!request.challenge().equals(input.challenge())
                || !request.changeSetDigest()
                    .equals(input.changeSetDigest())) {
            throw new InvalidRecoveryRequest();
        }

        // Dữ liệu xác minh do server tái tạo từ bản ghi chuẩn.
        deviceProofVerifier.verify(
            device,
            request.canonicalConfirmationBytes(),
            input.proof()
        );

        request.confirmOnce(device.id(), now);
        requests.saveWithVersionCheck(request);

        // Sự kiện được lưu cùng transaction để xử lý tin cậy sau commit.
        outbox.add(RecoveryConfirmed.from(request));
    });
}
~~~

Phương thức trên chỉ ghi nhận xác nhận, chưa thêm authenticator và chưa cấp session. Tác vụ hoàn tất cần một giao dịch riêng để kiểm tra lại trạng thái, điều kiện chính sách, bằng chứng đăng ký khóa mới và quyền của ngữ cảnh đang tiếp tục.

Khóa hàng hoặc compare-and-set với version phải bảo đảm hai phản hồi đồng thời không tạo hai kết quả. Khi mạng lỗi và client gửi lại cùng phản hồi, backend có thể trả kết quả đã ghi theo quy tắc idempotency; không phát hành thêm quyền recovery.

Nếu thay đổi authenticator và thu hồi session thuộc nhiều dịch vụ, cần cơ chế thực thi tin cậy. Trong khi việc thu hồi chưa đạt điều kiện bắt buộc, không báo recovery hoàn tất hoặc cấp quyền nhạy cảm vượt chính sách.

## 8. Chống lạm dụng và thao túng người dùng

### Giới hạn yêu cầu và thông báo

Áp dụng ngân sách theo tài khoản, thiết bị, nguồn yêu cầu và hệ thống phân phối. Chỉ giới hạn theo IP là chưa đủ khi yêu cầu đến từ nhiều nguồn.

Các yêu cầu giống nhau đang chờ có thể được gộp theo chính sách để tránh dội thông báo. Gửi lại thông báo không được âm thầm kéo dài thời hạn giao dịch hoặc làm sống lại challenge cũ.

Không khóa tài khoản chỉ vì có nhiều yêu cầu recovery từ bên ngoài. Biện pháp chống spam phải bảo vệ chủ tài khoản khỏi việc bị kẻ khác gây từ chối dịch vụ.

### Tránh phê duyệt mù

Thông điệp “Có phải bạn đang đăng nhập?” không đủ khi thao tác thật là thay MFA. Trình bày hành động recovery cụ thể, tránh tạo cảm giác đây chỉ là kiểm tra vô hại.

Nhập một giá trị liên kết phiên hoặc đối chiếu ngữ cảnh có thể tăng sự tham gia của người dùng, nhưng vẫn có thể bị hướng dẫn từ xa. Không quảng bá number matching, QR hay chữ ký ứng dụng tùy biến như bảo đảm chống phishing cho toàn luồng.

### Không biến hỗ trợ thành đường tắt

Người hỗ trợ không được yêu cầu đọc mã, chuyển tiếp link hoặc nhấn chấp thuận để “hủy” một yêu cầu. Việc từ chối phải là thao tác riêng, không cần trao bí mật recovery.

Nếu không còn kênh tin cậy, chọn phương thức recovery khác đã được thiết kế trước, thay vì hạ xuống câu hỏi cá nhân chỉ để đi tiếp. OWASP lưu ý rằng khôi phục MFA là phần cần được thiết kế từ đầu và có thể làm suy yếu toàn bộ MFA nếu xử lý sai. Xem [OWASP — Multifactor Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa).

## 9. Hoàn tất và kiểm soát quyền truy cập

Chính sách cần phân biệt việc quên mật khẩu với nghi ngờ chiếm đoạt tài khoản. Trong trường hợp nghi chiếm đoạt, cần xử lý cả phiên còn hiệu lực, authenticator trái phép và các thông tin recovery bị sửa; đổi mật khẩu đơn thuần có thể chưa đủ. OWASP cũng khuyến nghị thông báo cho người dùng qua những địa chỉ đã đăng ký còn phù hợp. Xem [OWASP — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

Trong mô hình của bài, bước hoàn tất phải quyết định rõ:

- Authenticator nào bị thu hồi, authenticator nào còn được giữ.
- Session và refresh token nào phải vô hiệu hóa theo tình huống.
- Các yêu cầu recovery đang chờ và quyền tạm nào cần hủy.
- Thông tin recovery nào cần chủ tài khoản xem lại.
- Người dùng phải đăng nhập lại bằng phương thức nào.
- Có hạn chế tạm thời đối với đổi kênh recovery hoặc thao tác nhạy cảm hay không.

Nếu dùng session tạm cho recovery, chỉ cấp các thao tác cần thiết, đặt thời hạn ngắn và kiểm tra quyền ở backend. Không cho session đó đọc toàn bộ dữ liệu hoặc dùng các API quản trị tài khoản như một session đăng nhập bình thường.

Thông báo sau hoàn tất cần cho biết thay đổi đã xảy ra và cách phản ánh nếu trái phép. Link báo sự cố không nên trở thành cơ chế tự động trao quyền khôi phục ngược cho bất kỳ ai đọc được email cũ.

Nhật ký có thể ghi request ID, loại thao tác, định danh thiết bị nội bộ, chuyển trạng thái, quyết định chính sách và thời gian. Không ghi OTP, recovery token, chữ ký/bằng chứng nhạy cảm hoặc URL chứa bí mật vào log, analytics và hệ thống theo dõi lỗi.

## 10. Ba tình huống để áp dụng mô hình

**Mất TOTP nhưng còn thiết bị tin cậy:** người dùng xem thao tác thay TOTP trong ứng dụng đã liên kết. Sau xác nhận và các điều kiện khác, đăng ký phương thức mới trong ngữ cảnh đã xác minh. Trình duyệt khởi tạo không tự được đăng nhập.

**Hộp thư có thể đã bị chiếm:** email xác nhận không còn là bằng chứng đủ cho thay MFA. Hệ thống dùng bằng chứng độc lập được thiết lập trước hoặc quy trình xác minh khác. Không coi việc trả lời được email là đã giải quyết rủi ro hộp thư.

**Không còn bất kỳ authenticator hay kênh an toàn nào:** không thể hoàn thành bước xác nhận ngoài băng bằng cách gửi lặp lại đến các kênh đã mất. Hệ thống cần quy trình khác phù hợp mức bảo đảm, có thể gồm mã recovery đã lưu riêng, xác minh danh tính hoặc hỗ trợ có kiểm soát. Một số trường hợp không thể tự phục vụ an toàn.

Khi thiết kế, hãy luôn nối bốn câu hỏi: **ai đang yêu cầu, ai đang xác nhận, chính xác điều gì được cho phép và ai sẽ nhận quyền sau cùng?** Out of band confirmation chỉ có ý nghĩa bảo vệ khi cả bốn câu trả lời nhất quán.
