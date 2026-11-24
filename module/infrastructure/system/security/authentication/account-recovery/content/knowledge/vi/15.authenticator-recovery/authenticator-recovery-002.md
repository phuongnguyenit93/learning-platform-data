# Authenticator seed replacement: Thay seed của ứng dụng xác thực

## 1. Thay seed là thay một bí mật xác thực lâu dài

Ứng dụng tạo mã TOTP thường giữ một bí mật dùng chung với máy chủ, gọi là **seed** hoặc **shared secret**. Từ bí mật đó và thời gian hiện tại, hai phía tính ra mã để đối chiếu. Seed không phải mã sáu chữ số đang hiển thị trên màn hình.

Khi người dùng mất điện thoại, nghi ngờ lộ mã QR thiết lập hoặc cần chuyển sang thiết bị mới, hệ thống có thể phải **thay seed**: tạo bí mật mới, gắn nó với tài khoản qua một quy trình được cấp quyền, xác nhận thiết bị mới sử dụng được và chấm dứt việc xác minh bằng bí mật cũ.

Phạm vi bài học là authenticator dựa trên bí mật đối xứng, chủ yếu là TOTP. Passkey sử dụng cơ chế khóa công khai khác; thay seed TOTP không phục hồi khóa riêng của passkey đã mất.

Cần phân biệt các thao tác dễ bị gọi chung là “khôi phục authenticator”:

| Thao tác | Seed có thay đổi không? | Hệ quả bảo mật |
| --- | --- | --- |
| Chép seed cũ sang điện thoại mới | Không | Thiết bị hoặc bản sao cũ vẫn có thể tạo mã |
| Khôi phục bản sao lưu ứng dụng chứa seed cũ | Không | Khôi phục khả năng tạo mã, chưa loại bỏ các bản sao trước đó |
| Thay bằng seed mới | Có | Có thể chấm dứt xác minh bằng seed cũ nếu máy chủ vô hiệu hóa đúng |
| Đổi khóa mã hóa lưu seed trên máy chủ | Không nhất thiết | Bảo vệ dữ liệu lưu trữ; không tự thay bí mật trong authenticator |
| Đăng ký một authenticator bổ sung | Tạo liên kết riêng theo thiết kế | Không đồng nghĩa đã thu hồi authenticator đang cần thay |

**Đổi tên thiết bị hoặc vẽ lại mã QR từ seed cũ không phải thay seed.**

RFC 6238 yêu cầu bí mật riêng cho từng prover và mô tả TOTP dựa trên HOTP với yếu tố thời gian. Tham khảo [RFC 6238, mục 3 và 4](https://www.rfc-editor.org/rfc/rfc6238.html#section-3). Trong thiết kế này, một liên kết authenticator mới được cấp một seed mới độc lập.

## 2. Xác định tình huống trước khi chọn thứ tự thay thế

### Chuyển thiết bị khi thiết bị cũ còn tin cậy

Lan vẫn sử dụng được authenticator cũ và muốn chuyển sang điện thoại mới. Hệ thống có thể yêu cầu xác thực lại phù hợp, tạo seed mới ở trạng thái chờ, rồi chỉ thay liên kết hoạt động khi Lan xác nhận bằng mã từ thiết bị mới.

Cách này giảm nguy cơ tự khóa tài khoản nếu Lan mở trang thiết lập nhưng chưa hoàn tất quét mã.

### Mất thiết bị hoặc nghi ngờ seed đã lộ

Nếu điện thoại bị đánh cắp hoặc mã QR thiết lập đã bị chụp lại, giữ seed cũ hoạt động trong lúc chờ người dùng hoàn tất có thể để lại đường truy cập cho đối tượng khác.

Trong tình huống này, sau khi có đủ thẩm quyền xác minh hoặc quyết định ứng phó được phép, hệ thống có thể cần thu hồi authenticator cũ ngay, rồi cho phép đăng ký mới qua một quyền khôi phục giới hạn.

Một yêu cầu công khai chỉ nói “tôi bị mất điện thoại” không đủ để vô hiệu hóa authenticator của bất kỳ tài khoản nào. Nếu làm vậy, người tấn công có thể gây từ chối dịch vụ cho chủ tài khoản.

| Tình huống | Thứ tự minh họa | Nếu thiết lập mới bị bỏ dở |
| --- | --- | --- |
| Thiết bị cũ còn tin cậy | Cấp seed chờ → xác nhận mới → thay và thu hồi cũ | Seed chờ hết hạn; liên kết cũ vẫn hoạt động |
| Thiết bị cũ mất hoặc nghi bị lộ | Xác minh thẩm quyền → thu hồi cũ theo chính sách → cấp và xác nhận mới | Không tự khôi phục seed cũ; tiếp tục qua phương thức còn tin cậy |
| Chưa đủ bằng chứng của người yêu cầu | Hoàn thành xác minh trước khi cấp quyền thay | Không phát seed và không đổi trạng thái chỉ từ lời khai |

Điểm chung là hành động cấp seed mới phải được cho phép. Thứ tự thu hồi seed cũ phụ thuộc tình huống rủi ro.

## 3. Cấp quyền thay authenticator trước khi phát seed

Thay authenticator là hành động có thể chuyển quyền kiểm soát tài khoản. Một session còn hiệu lực chưa chắc đủ, vì session đó có thể bị đánh cắp.

OWASP khuyến nghị xác thực lại khi thay yếu tố MFA, xét rủi ro và thông báo thay đổi qua kênh phù hợp; không chỉ dựa vào session đang mở. Xem [OWASP Multifactor Authentication Cheat Sheet, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

Có hai đường cấp quyền thường gặp:

- **Người dùng còn phương thức xác thực đủ mạnh:** xác thực lại bằng phương thức đang được chấp nhận cho hành động thay authenticator.
- **Người dùng mất phương thức cần dùng:** đi qua quy trình khôi phục đã được thiết kế, chẳng hạn dùng mã dự phòng, authenticator độc lập còn lại hoặc xác minh khác phù hợp.

Không tạo vòng lặp bắt người mất authenticator phải nhập mã từ chính thiết bị đã mất. Cũng không hạ yêu cầu thành “chỉ cần biết email” hoặc gửi mã tới một số điện thoại mới vừa khai báo.

NIST phân biệt việc gắn authenticator sau đăng ký với khôi phục khi mất quyền kiểm soát phương thức cần thiết. Xem [NIST SP 800-63B-4, Post-Enrollment Binding và Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#post-enrollment-binding). Yêu cầu cụ thể phải phù hợp mức bảo đảm mà hệ thống đặt ra.

### Quyền khôi phục chỉ phục vụ một mục đích

Một quyền thay seed có thể liên kết với:

- Tài khoản được khôi phục.
- Authenticator cũ được phép thay.
- Phiên hoặc ngữ cảnh khôi phục đã xác minh.
- Loại bằng chứng và thời điểm kiểm tra.
- Hành động được phép, thời hạn và trạng thái sử dụng.
- Phiên bản bảo mật của tài khoản lúc cấp quyền.

Quyền này cho phép chuẩn bị và xác nhận một authenticator mới. Nó không mặc nhiên cho phép đọc dữ liệu tài khoản, thay email, xóa các passkey khác hoặc đăng nhập toàn quyền.

Nếu mã dự phòng được dùng để cấp quyền khôi phục, mã đó phải được tiêu thụ theo cơ chế dùng một lần. Không chờ tới cuối thiết lập mới xử lý việc đã dùng mã nếu trong thời gian đó mã vẫn có thể mở thêm nhiều luồng độc lập.

## 4. Phân biệt quyền của người yêu cầu với khả năng sử dụng seed mới

Hai câu hỏi sau cần được kiểm tra riêng:

1. Người đang thao tác có được phép thay authenticator của tài khoản này không?
2. Thiết bị mới có tạo được mã từ seed đang chờ không?

Một mã TOTP đúng từ thiết bị mới chỉ hỗ trợ trả lời câu thứ hai. Bất kỳ ai đọc được seed mới đều có thể tạo mã của seed đó. Vì vậy, cho quét mã QR rồi nhập đúng OTP không tự chứng minh người quét là chủ tài khoản.

Ngược lại, một người đã xác minh danh tính nhưng chưa quét seed mới chưa chắc đã có thiết bị xác thực hoạt động. Nếu máy chủ kích hoạt ngay khi tạo QR, người dùng có thể bị mất đường đăng nhập vì ứng dụng chưa lưu được seed.

Thiết kế cần nối hai bằng chứng trong cùng ngữ cảnh được kiểm soát:

~~~text
Quyền thay authenticator hợp lệ
        +
Mã xác nhận từ đúng seed mới đang chờ
        +
Kiểm tra rủi ro và trạng thái còn hiệu lực
        =
Được phép hoàn tất thay liên kết authenticator
~~~

Tên tài khoản hoặc ID authenticator do trình duyệt gửi không thay thế kiểm tra quyền sở hữu trên máy chủ.

## 5. Mô hình trạng thái cho seed chờ và seed đang hoạt động

Một mô hình minh họa dùng các trạng thái:

| Trạng thái | Ý nghĩa | Có được dùng để đăng nhập thông thường không? |
| --- | --- | --- |
| PENDING | Seed đã cấp cho một thao tác thiết lập được phép | Không |
| ACTIVE | Seed đã xác nhận và được chính sách chấp nhận | Có, trong luồng xác thực tương ứng |
| REVOKED | Liên kết đã bị thu hồi | Không |
| EXPIRED | Thiết lập chờ hết hạn | Không |
| CANCELLED | Thiết lập chờ bị hủy hoặc thay thế | Không |

Sơ đồ cho trường hợp chuyển thiết bị khi authenticator cũ còn tin cậy:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as Dịch vụ khôi phục
    participant V as Kho authenticator
    participant A as Ứng dụng mới

    U->>R: Yêu cầu thay authenticator
    R->>R: Kiểm tra xác thực lại và quyền thay
    R->>V: Tạo authenticator mới PENDING
    R-->>U: Trình bày seed qua QR hoặc cách nhập thủ công
    U->>A: Quét hoặc nhập seed
    A-->>U: Tạo TOTP từ seed mới
    U->>R: Gửi mã xác nhận cùng ngữ cảnh thiết lập
    R->>R: Xác minh seed chờ, quyền và thời hạn
    R->>V: Atomically: mới ACTIVE, cũ REVOKED, hoàn tất quyền thay
    R-->>U: Thay authenticator thành công
~~~

Các bất biến của mô hình:

- Seed PENDING chỉ được kiểm tra ở endpoint xác nhận thiết lập, không đi vào tập seed dùng cho đăng nhập.
- Một candidate chỉ thuộc một tài khoản, một quyền thay và một mục đích.
- Xác nhận candidate của tài khoản A không được thay authenticator của tài khoản B.
- Hoàn tất thay thế không để liên kết cũ tiếp tục hoạt động ngoài chủ ý.
- Hủy hoặc hết hạn candidate không được tạo quyền truy cập mới.
- Không tự chuyển tài khoản sang chế độ không cần MFA chỉ vì đang thay seed.

Nếu hỗ trợ nhiều authenticator độc lập, thao tác thay phải xác định đúng liên kết cũ. Không thu hồi mọi authenticator của tài khoản chỉ vì giao diện ghi “thay điện thoại”, trừ khi đó là hành động đã được cho phép rõ ràng.

## 6. Tạo seed mới độc lập và lưu trữ đúng bản chất

### Sinh bí mật bằng nguồn ngẫu nhiên mật mã

Seed mới không nên được tạo từ email, tên đăng nhập, timestamp, số điện thoại hoặc chuỗi có thể đoán. Cũng không dùng lại seed cũ và chỉ đổi nhãn.

Ví dụ Java dưới đây chỉ minh họa sinh 20 byte ngẫu nhiên:

~~~java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
byte[] newSeed = new byte[20];
secureRandom.nextBytes(newSeed);
~~~

20 byte tương ứng 160 bit. RFC 4226 khuyến nghị độ dài bí mật 160 bit cho HOTP. Xem [RFC 4226, mục 4, yêu cầu R6](https://www.rfc-editor.org/rfc/rfc4226.html#section-4). Khi lựa chọn tham số cho TOTP, cần bảo đảm phù hợp thuật toán, thư viện và ứng dụng xác thực được hỗ trợ.

Đoạn Java không bao gồm mã hóa lưu trữ, cấp QR, kiểm soát quyền hoặc quản lý vòng đời. Không dùng một seed cố định từ tài liệu mẫu cho nhiều tài khoản.

### Seed không thể lưu giống bản băm mật khẩu

Với TOTP thông thường, máy chủ cần bí mật dùng chung hoặc một dịch vụ mật mã có khả năng thực hiện phép tính bằng bí mật đó. Chỉ giữ bản băm một chiều của seed không cho máy chủ tính các mã tương ứng.

Một thiết kế lưu trữ có thể dùng:

- Mã hóa seed bằng cơ chế xác thực tính toàn vẹn phù hợp.
- Quản lý khóa mã hóa riêng qua KMS hoặc hạ tầng bảo vệ khóa.
- Giới hạn thành phần có quyền giải mã.
- Gắn ciphertext với ngữ cảnh liên kết, tránh tráo seed giữa tài khoản.
- Lưu thuật toán, độ dài mã và tham số thời gian như dữ liệu được quản lý nhất quán.

Base32 chỉ là cách biểu diễn byte để cấp cho ứng dụng; nó không mã hóa bí mật. Một người có chuỗi Base32 đầy đủ có thể có khả năng nhân bản authenticator tương ứng.

Dữ liệu phục vụ audit thường chỉ cần mã liên kết, phiên bản, trạng thái và thời điểm thay đổi. Không cần lưu thêm bản seed rõ trong lịch sử.

## 7. Cấp seed qua QR mà không tạo thêm bản sao ngoài kiểm soát

Mã QR thiết lập thường biểu diễn dữ liệu để ứng dụng nhận seed và các tham số liên quan. Vì chứa bí mật lâu dài, QR này cần được bảo vệ chặt hơn một ảnh giao diện thông thường.

Một phương án cấp seed có các ràng buộc:

- Chỉ hiển thị sau khi kiểm tra quyền thay authenticator.
- Mỗi lần thiết lập có candidate ID và thời hạn riêng.
- Người đang xem chỉ truy cập được candidate thuộc đúng ngữ cảnh của họ.
- QR được tạo trong thành phần được kiểm soát; không chuyển seed sang dịch vụ tạo ảnh QR công khai.
- Không ghi seed, dữ liệu QR hoặc toàn bộ URI cấp seed vào log, analytics, session replay hay báo cáo lỗi.
- Không đưa seed vào URL điều hướng, query string hoặc tài nguyên có thể bị truy cập qua lịch sử và referrer.
- Phản hồi nhạy cảm dùng chính sách cache phù hợp, chẳng hạn Cache-Control: no-store.
- Sau hoàn tất, hủy hoặc hết hạn, giao diện không tiếp tục cung cấp seed của candidate đó.

Đường nhập seed thủ công cần được bảo vệ tương đương QR. Không nên mở một endpoint “xem lại seed hiện tại” chỉ để hỗ trợ người dùng chuyển máy nhanh hơn.

### Tải lại trang và tạo mã QR mới

Tải lại trang không nên vô tình tạo một candidate mới trong khi người dùng vừa quét candidate trước đó. Có thể tiếp tục candidate còn hợp lệ trong cùng phiên được cấp quyền, hoặc yêu cầu thao tác rõ ràng để hủy và tạo lại.

Nếu người dùng chọn “tạo mã QR khác”, seed chờ trước đó cần bị hủy theo chính sách. Nhắc người dùng quét mã mới nhất và không chấp nhận candidate đã bị thay thế.

Thời hạn của candidate và thời hạn của quyền thay là hai giới hạn riêng. Có seed chờ chưa hết hạn không cho phép hoàn tất nếu quyền thay đã bị thu hồi hoặc cần xác minh lại.

Nếu cho sao chép seed thủ công, cần giúp người dùng hiểu đây là bí mật dùng để tạo mã. Không gửi seed qua email hoặc yêu cầu đọc seed cho nhân viên hỗ trợ.

## 8. Xác nhận thiết bị mới bằng đúng candidate

Khi người dùng quét QR, ứng dụng mới tính TOTP từ seed được cấp. Máy chủ nhận mã xác nhận cần biết rõ đang kiểm tra candidate nào.

Không dùng logic “thử mã với mọi seed của tài khoản; nếu có seed nào đúng thì kích hoạt seed mới”. Mã từ authenticator cũ không xác nhận candidate mới.

Các bước kiểm tra gồm:

1. Lấy tài khoản và quyền thay từ ngữ cảnh đã được máy chủ xác thực.
2. Kiểm tra candidate thuộc quyền đó và đang PENDING.
3. Kiểm tra thời hạn của candidate, quyền thay và mức độ mới của bằng chứng.
4. Kiểm tra định dạng mã đúng với tham số đã lưu.
5. Xác minh mã bằng seed của candidate và cửa sổ thời gian được cấu hình.
6. Ghi nhận kết quả, bước thời gian đã dùng và ngân sách thử.
7. Chỉ kích hoạt nếu các điều kiện nghiệp vụ vẫn còn hợp lệ.

Mã cần được xử lý như chuỗi để giữ chữ số 0 ở đầu. Không tin các tham số như thuật toán hoặc độ dài mã do máy khách tự gửi để mở rộng điều kiện chấp nhận.

### Cửa sổ thời gian và chống dùng lại

Đồng hồ thiết bị có thể lệch. Máy chủ cần chính sách cửa sổ kiểm tra có giới hạn và hướng dẫn kiểm tra thời gian trên thiết bị khi cần. Không mở rộng cửa sổ tùy ý cho đến khi một mã khớp.

RFC 6238 yêu cầu không chấp nhận lần sử dụng tiếp theo của OTP đã xác minh thành công. Xem [RFC 6238, mục 5.2](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2). Trong thiết kế này, mã xác nhận kích hoạt cũng được ghi nhận với bước thời gian tương ứng để tránh dùng lại ngay sau đó trong cùng cơ chế kiểm tra.

Nếu ứng dụng chỉ lưu “OTP cuối cùng” mà không gắn với credential và bước thời gian, việc thay seed dễ làm sai phạm vi chống dùng lại. Trạng thái phải thuộc đúng liên kết authenticator.

Số lần thử cần bị giới hạn trên cả candidate và phạm vi tài khoản hoặc toàn thao tác. Tạo thêm QR không được trở thành cách lấy lại vô hạn lượt đoán mã.

### Nếu người dùng muốn xác nhận thêm một mã

Một sản phẩm có thể yêu cầu thêm mã ở bước thời gian tiếp theo để kiểm tra khả năng vận hành. Đây là lựa chọn thiết kế, không phải điều kiện chung cho mọi luồng thay seed.

Nếu áp dụng, cần giải thích việc chờ mã thay đổi, giữ quyền thay còn hợp lệ và tiếp tục giới hạn thử. Không coi hai mã từ cùng seed là hai yếu tố xác thực độc lập.

## 9. Hoàn tất thay thế bằng một chuyển trạng thái nguyên tử

Điểm nhạy cảm nhất là lúc seed mới trở thành ACTIVE và seed cũ chấm dứt quyền xác thực.

Trong trường hợp chuyển thiết bị có kế hoạch, các thay đổi cần được thực hiện nhất quán:

- Candidate mới chuyển thành ACTIVE.
- Authenticator cũ được chỉ định chuyển thành REVOKED.
- Quyền thay được đánh dấu đã hoàn tất.
- Trạng thái chống dùng lại của mã xác nhận được ghi nhận.
- Phiên bản bảo mật và các dữ liệu liên quan được cập nhật.
- Sự kiện cần thông báo được lưu bền vững.

Mã giả dưới đây minh họa trách nhiệm, không phải triển khai hoàn chỉnh:

~~~text
completeSeedReplacement(flow, operationId, candidateId, submittedCode):
    requireRequestProtection(flow)
    enforceReplacementRateLimits(flow, operationId)
    validateCodeFormat(submittedCode)

    atomically:
        operation = loadOperationForUpdate(operationId)
        requireAuthorizedFlow(operation, flow)
        requireUnexpiredAndUnused(operation)

        account = loadAccountForUpdate(operation.accountId)
        requireExpectedSecurityVersion(operation, account)

        candidate = loadCandidateForUpdate(candidateId)
        requirePendingCandidateOfOperation(candidate, operation)
        requireUnexpired(candidate)
        requireAttemptBudget(candidate, operation)

        result = verifyCandidateTotp(candidate, submittedCode)
        recordAttemptDurably(candidate, operation, result)

        if result is invalid or alreadyUsed:
            persistRejectionWithoutActivation()
            return CANNOT_CONFIRM

        oldAuthenticator = loadReplacementTargetForUpdate(operation)
        requireExpectedTargetState(oldAuthenticator, operation)

        activateCandidateWithUsedStep(candidate, result.timeStep)
        revokeTargetIfStillActive(oldAuthenticator)
        completeOperation(operation)
        advanceAccountSecurityVersion(account)
        invalidateConflictingPendingOperations(account)
        persistRequiredSessionRevocationState(account, operation)
        appendNotificationToOutbox(operation)

    return REPLACEMENT_COMPLETED
~~~

“Atomically” có thể được thực hiện bằng giao dịch và khóa hoặc cập nhật có điều kiện phù hợp. Không nhất thiết giữ khóa trong suốt quá trình người dùng quét QR.

Các lượt thử thất bại vẫn phải được lưu. Nếu trả lỗi bằng exception làm rollback luôn bộ đếm, giới hạn thử sẽ không hoạt động đúng.

Với trường hợp đã thu hồi thiết bị bị mất từ trước, thao tác hoàn tất phải chấp nhận đúng trạng thái cũ đã được ghi trong operation. Không kích hoạt lại seed cũ chỉ để ép mô hình đi qua nhánh “ACTIVE rồi REVOKED”.

### Xử lý hai tab cùng thay seed

Hai tab có thể cùng mở hai thao tác thay. Nếu cả hai dùng dữ liệu cũ rồi lần lượt ghi, thao tác hoàn tất sau có thể ghi đè kết quả mà người dùng vừa xác nhận.

Một lựa chọn là chỉ cho một operation thay cùng mục tiêu hoạt động tại một thời điểm. Dù chọn cách nào, cần kiểm tra phiên bản hoặc trạng thái kỳ vọng khi commit. Thao tác đã lỗi thời phải được từ chối hoặc bắt đầu lại có kiểm soát.

### Xử lý việc mất phản hồi

Giao dịch có thể đã hoàn tất trong khi trình duyệt chưa nhận được phản hồi. Gửi lại cùng yêu cầu không được cấp thêm seed, hoàn thành một operation khác hoặc tiêu thụ thêm quyền.

Có thể hỗ trợ truy vấn kết quả bằng chính phiên đã liên kết và mã thao tác. Kết quả trả về chỉ cần cho biết thao tác đã hoàn tất; không hiển thị lại seed hoặc tạo session đầy đủ chỉ vì có operation ID.

## 10. Seed cũ bị thu hồi nghĩa là máy chủ không còn tin liên kết cũ

Sau thay thế, điện thoại cũ vẫn có thể hiển thị mã. Ứng dụng trên điện thoại không cần liên lạc với máy chủ để tiếp tục tính TOTP từ seed mà nó giữ.

Máy chủ không thể bảo đảm xóa mọi bản sao seed khỏi thiết bị cũ, ảnh chụp QR hoặc bản sao lưu bên ngoài. Điều hệ thống có thể thực thi là ngừng dùng seed đó để xác minh cho liên kết đã thu hồi.

Do đó:

- Không dùng lại seed cũ trong một candidate mới.
- Không tự hoàn tác về seed cũ khi người dùng gặp khó với thiết lập mới.
- Mọi node xác thực phải tuân theo trạng thái thu hồi.
- Bộ nhớ đệm hoặc replica chậm không được tiếp tục chấp nhận liên kết cũ trái với cam kết của hệ thống.
- Quy trình phục hồi dữ liệu từ backup phải đối soát trạng thái thu hồi, tránh làm sống lại credential cũ.

Nếu kiến trúc có cache, cần thiết kế việc vô hiệu hóa và kiểm tra phiên bản đủ mạnh cho mức bảo đảm đã cam kết. Chỉ phát một thông báo bất đồng bộ mà không biết node nào vẫn còn tin seed cũ có thể để lại khoảng trống xác thực.

### Đừng kiểm tra thu hồi bằng cách so sánh hai chuỗi OTP

Không thể kết luận thay seed thất bại chỉ vì tại một thời điểm điện thoại cũ và mới hiện cùng sáu chữ số. Hai bí mật khác nhau có thể tạo ra cùng giá trị mã ngắn.

Tương tự, một chuỗi được người dùng đọc từ điện thoại cũ có thể tình cờ bằng mã hợp lệ của seed mới. Máy chủ xác minh giá trị đã gửi dưới liên kết mới, chứ không thể nhìn chuỗi số rồi biết nó được tạo trên thiết bị nào.

Điều cần chứng minh trong thiết kế là **seed cũ và credential cũ không còn được đưa vào đường xác minh được phép**, thay vì hứa rằng mọi chuỗi số từng xuất hiện trên thiết bị cũ đều sẽ bị từ chối.

## 11. Session, refresh token và thiết bị đã ghi nhớ cần được xử lý riêng

Thay seed chỉ thay cách tạo bằng chứng xác thực trong các lần kiểm tra tương ứng. Session đã cấp trước đó có thể vẫn còn hiệu lực nếu hệ thống không có cơ chế khác.

Vì vậy, cần xác định:

| Thành phần | Quyết định cần có |
| --- | --- |
| Session của thiết bị bị mất | Có phải thu hồi ngay khi xác định mất kiểm soát không? |
| Session khác đang hoạt động | Giữ lại hay yêu cầu xác thực lại theo tình huống rủi ro? |
| Refresh token | Có còn được cấp token mới sau thời điểm thay không? |
| Trình duyệt đã ghi nhớ MFA | Có tiếp tục được bỏ bước MFA không? |
| Quyền khôi phục đang mở | Quyền nào phải tiêu thụ, hủy hoặc yêu cầu kiểm tra lại? |
| Candidate khác | Có còn hợp lệ sau khi phiên bản bảo mật thay đổi không? |

Xóa cookie trên trình duyệt hiện tại không thu hồi session đang nằm trên thiết bị khác. Với token tự chứa, thay seed cũng không tự làm chữ ký token mất hiệu lực.

Tùy kiến trúc, hệ thống có thể dùng kho session, phiên bản bảo mật, cơ chế thu hồi hoặc thời hạn token kết hợp kiểm tra phía máy chủ. Cần nêu rõ thời điểm việc thu hồi có hiệu lực; không gọi là thu hồi ngay nếu thực tế phải chờ token hết hạn.

Nếu luồng khôi phục dùng một phiên giới hạn, sau thay seed phiên đó vẫn chỉ có quyền đã được thiết kế. Muốn cấp session đăng nhập thông thường phải hoàn tất chính sách xác thực và tạo hoặc thay định danh phiên phù hợp, tránh nâng quyền ngầm.

Không cần đặt lại mật khẩu chỉ vì người dùng thay điện thoại có kế hoạch, trừ khi có lý do hoặc chính sách tương ứng. Ngược lại, nếu có dấu hiệu tài khoản đã bị xâm phạm, phạm vi xử lý có thể phải bao gồm nhiều phương thức và session hơn một seed.

## 12. Mã dự phòng, thông báo và sự cố trong quá trình thay

### Mã dự phòng có vòng đời riêng

Thay seed TOTP không tự thay nội dung các mã dự phòng đã cấp. Hệ thống cần quyết định bộ mã cũ có còn phù hợp với mức rủi ro hiện tại không.

Nếu nghi ngờ các bí mật đã bị sao chép, có thể cần thu hồi bộ mã cũ và cấp bộ mới sau khi đủ điều kiện. Nếu chỉ đổi thiết bị trong một luồng đã xác thực tốt, chính sách có thể khác.

Không cấp và lưu trữ mã dự phòng giống seed TOTP. Mã dự phòng thường được kiểm tra bằng bản biểu diễn một chiều và tiêu thụ sau khi dùng; seed TOTP phục vụ tính mã qua nhiều bước thời gian.

Nếu cấp mã dự phòng mới, người dùng cần được hướng dẫn lưu ở nơi phù hợp, tránh chỉ giữ trong chính thiết bị vừa trở thành điểm phụ thuộc duy nhất.

### Thông báo thay đổi không chứa bí mật

Một thông báo có thể nêu:

- Thời điểm thay authenticator.
- Tên thiết bị hoặc liên kết theo cách không tiết lộ quá mức.
- Những phiên hoặc phương thức đã bị thu hồi.
- Cách báo cáo nếu người dùng không thực hiện thao tác.

Không gửi seed, ảnh QR hoặc mã dự phòng trong thông báo.

Nếu hệ thống dùng outbox, sự kiện thông báo được ghi cùng thay đổi nghiệp vụ, rồi gửi có retry. Việc gửi email lỗi không nên làm máy chủ tự kích hoạt lại seed cũ. Cần theo dõi lỗi thông báo như một vấn đề vận hành riêng.

### Candidate hết hạn hoặc dịch vụ mật mã lỗi

Nếu candidate hết hạn trước xác nhận, không kích hoạt nó từ một mã tới muộn. Người dùng cần thực hiện tiếp theo hướng dẫn, có thể phải xác minh lại trước khi tạo candidate khác.

Nếu KMS hoặc thành phần xác minh không truy cập được, không chuyển sang chế độ bỏ MFA để “cho người dùng vào trước”. Giữ trạng thái nhất quán và cung cấp đường tiếp tục phù hợp.

Nếu seed cũ đã bị thu hồi vì nghi lộ, lỗi thiết lập mới không phải căn cứ khôi phục niềm tin vào seed cũ.

## 13. Tình huống vận dụng và các lỗi thiết kế thường gặp

### Chuyển máy có kế hoạch

Lan xác thực lại bằng phương thức được chấp nhận, mở thiết lập trên dịch vụ thật và quét seed mới vào điện thoại mới.

Nếu Lan đóng trang trước xác nhận, candidate hết hạn và điện thoại cũ vẫn dùng được theo chính sách chuyển máy. Khi Lan hoàn tất xác nhận, dịch vụ thay liên kết và ngừng xác minh bằng seed cũ. Những phương thức độc lập không thuộc mục tiêu thay được giữ theo chính sách của chúng.

### Mất điện thoại và còn phương thức độc lập

Minh mất điện thoại chứa TOTP nhưng còn một passkey hợp lệ trên thiết bị khác. Nếu passkey đó đáp ứng yêu cầu hành động, hệ thống có thể dùng nó để cấp quyền thay seed.

Thiết bị cũ được thu hồi theo đánh giá mất kiểm soát. Minh thiết lập và xác nhận seed mới bằng quyền giới hạn. Việc session trên điện thoại mất có còn hiệu lực hay không phải được xử lý thêm, không giả định thu hồi seed đã giải quyết tất cả.

### Mất mọi phương thức

Hà không còn authenticator, mã dự phòng hoặc phương thức độc lập. Hệ thống phải đi theo quy trình khôi phục được phép. Nhân viên hỗ trợ không yêu cầu Hà gửi QR cũ, không tự cấp seed qua một địa chỉ mới chưa được tin cậy và không dùng việc trả lời thông tin công khai làm bằng chứng đủ.

Nếu chưa đủ căn cứ, chưa được cấp quyền thay seed. Khó khăn của tình huống này là lý do phải chuẩn bị phương thức dự phòng trước khi sự cố xảy ra.

| Lỗi thiết kế | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Hiển thị lại seed cũ để người dùng quét | Duy trì mọi bản sao cũ | Cấp seed mới độc lập khi mục tiêu là thay thế |
| Kích hoạt ngay khi tạo QR | Có thể thay sang thiết bị chưa thiết lập xong | Giữ PENDING đến khi xác nhận |
| Nhận mã từ bất kỳ seed nào của tài khoản | Không chứng minh candidate mới dùng được | Kiểm tra đúng seed chờ của operation |
| Chỉ có session là được thay MFA | Session bị đánh cắp có thể đổi yếu tố | Xác minh lại hoặc hoàn tất quy trình khôi phục phù hợp |
| Cả seed cũ và mới đều được chấp nhận không có giới hạn | Giữ đường truy cập ngoài ý muốn | Thực thi trạng thái và mục tiêu thay rõ ràng |
| Lưu seed bằng Base32 rồi gọi là đã mã hóa | Dữ liệu bị đọc có thể nhân bản authenticator | Bảo vệ seed bằng cơ chế mật mã và quản lý khóa |
| Chỉ sửa dữ liệu ở một node | Node khác có thể còn tin credential cũ | Đồng bộ và kiểm tra trạng thái thu hồi |
| Đặt cờ bỏ MFA trong thời gian khôi phục | Mở đường bỏ qua kiểm soát | Dùng quyền khôi phục giới hạn theo hành động |

Thay seed hoàn chỉnh gồm bốn trách nhiệm liên kết với nhau: **cấp quyền đúng người, tạo và bảo vệ bí mật mới, xác nhận trước khi kích hoạt, rồi chấm dứt niềm tin vào liên kết cũ**. Session và các phương thức dự phòng cần được quản lý theo chính sách riêng để việc thay seed đạt đúng mục tiêu khôi phục tài khoản.
